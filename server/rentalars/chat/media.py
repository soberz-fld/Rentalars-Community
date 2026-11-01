# SPDX-License-Identifier: GPL-3.0-or-later
"""Photos and videos in the chat: checking, making smaller, storing, delivering (UIX-049; UIX-010).

The requirement: photos and videos in the chat, compressed. Decided:
the server makes them smaller and keeps only the small version.

Photos
------
Checked by their content with Pillow – JPEG (a phone's MPO is one), PNG,
GIF, WebP – and made smaller at once, in the request: the orientation the
camera noted is applied, the long side becomes at most
:data:`PHOTO_LONGEST_SIDE` pixels, and the photo is written as JPEG
*without* its metadata – no place (GPS), no device, no time. The chat shows
a preview of :data:`THUMBNAIL_LONGEST_SIDE` pixels that opens the photo.

Videos
------
Checked by their content as well: the container is recognised by its first
bytes (MP4/QuickTime, Matroska/WebM, AVI), and ``ffprobe`` reads it with
that demuxer only and the file protocol only – a playlist or anything else
that makes ffmpeg read further files never gets that far. The conversion
runs in the background (``core.jobs``, kind ``chat_video``): ``ffmpeg`` makes
H.264/AAC in MP4 of at most 720p (1280 × 720, upright 720 × 1280), at most
30 frames per second, CRF :data:`VIDEO_CRF`, with "faststart" so that
playing starts at once, and without metadata (the place a phone notes).
ffmpeg is called with a list of arguments – never through a shell –, with
``-nostdin``, a time limit and a lower priority; it writes to a temporary
file in ``DATA_DIR/chat-videos``, which is then moved into the media folder.
The original is deleted. One video is converted at a time on a server
(:func:`conversion_slot`); the others wait in line. Until then the message says "Video wird verkleinert
…"; if the conversion fails, it says so and the upload is discarded.

Without ffmpeg on the server, videos are refused with a clear message and
the self-check warns (``core.selfcheck``); photos work all the same.

Storage and access
------------------
The files lie in ``MEDIA_ROOT/chat/<project>/`` – in the backup like every
other stored file – and leave the server only through views that checked
that the user may read the chat (:func:`file_response`). Deleting a message
deletes its files, also when the whole project goes (:func:`files_deleted`).
Videos waiting for their conversion lie in ``DATA_DIR/chat-videos`` – not in
the backup, like the uploaded invoices of a purchase.
"""

from __future__ import annotations

import contextlib
import datetime
import fcntl
import io
import json
import logging
import re
import secrets
import shutil
import subprocess
import time
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile, File
from django.db import transaction
from django.db.models import F
from django.http import Http404, HttpResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.http import content_disposition_header
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext

from rentalars.chat.models import AttachmentKind, AttachmentState, ChatAttachment, ChatMessage
from rentalars.core.photos import (  # noqa: F401 - the photo code lives in core.photos; the names stay here
    MAX_JPEG_PIXELS,
    MAX_PHOTO_BYTES,
    MAX_PHOTO_PIXELS,
    PHOTO_FORMATS,
    PHOTO_LONGEST_SIDE,
    PHOTO_QUALITY,
    PICTURE_BRANDS,
    THUMBNAIL_LONGEST_SIDE,
    THUMBNAIL_QUALITY,
    PhotoError,
    draft_size,
    render_photo_upload,
    shrink_photo,
)
from rentalars.core.photos import (
    jpeg as _jpeg,
)
from rentalars.core.photos import (
    rgb as _rgb,
)
from rentalars.core.pictures import open_picture

if TYPE_CHECKING:
    from rentalars.core.models import BackgroundJob

logger = logging.getLogger(__name__)

# --- Limits ----------------------------------------------------------------------------------------------

#: The largest video that is accepted (before it is made smaller).
MAX_VIDEO_BYTES = 200 * 1024 * 1024
#: All files of one message together. NGINX takes requests of up to 510 MB (deploy/nginx/rentalars.conf).
MAX_MESSAGE_BYTES = 500 * 1024 * 1024
#: The most files one message may carry.
MAX_FILES = 10
#: The longest video, in seconds.
MAX_VIDEO_SECONDS = 20 * 60
#: The largest picture of a video, in pixels on either side (4K of a phone: 3840 × 2160, DCI: 4096 × 2160).
MAX_VIDEO_SIDE = 4096
#: The most frames per second a video may have (slow motion of a phone: 240) …
MAX_VIDEO_FPS = 240
#: … and in all: 20 minutes at 60 frames per second (NFA-076).
MAX_VIDEO_FRAMES = MAX_VIDEO_SECONDS * 60
# --- What is kept ------------------------------------------------------------------------------------------

#: The box a video is made to fit in: 1280 × 720 lying, 720 × 1280 upright – never larger than it was.
VIDEO_LONG_SIDE = 1280
VIDEO_SHORT_SIDE = 720
#: Quality of the video (H.264, lower is better and larger); 26 suits a chat.
VIDEO_CRF = 26
VIDEO_PRESET = "veryfast"
VIDEO_MAX_FPS = 30
VIDEO_MAX_RATE = "3M"
VIDEO_AUDIO_BITRATE = "128k"

# --- Running ffmpeg -----------------------------------------------------------------------------------------

#: Seconds ffprobe may take for a file, and ffmpeg for the poster frame.
PROBE_TIMEOUT = 60
#: Seconds ffmpeg may take to convert one video.
CONVERT_TIMEOUT = 60 * 60
#: A video still "processing" after this long lost its task (a restart, the timer off): it counts as failed.
STUCK_AFTER = datetime.timedelta(hours=3)
#: … unless its task still waits in line (one conversion at a time) or runs – then after this long.
STUCK_IN_LINE_AFTER = datetime.timedelta(hours=24)
#: Below ``DATA_DIR``: uploaded videos waiting for their conversion, and the conversion's temporary files.
PENDING_FOLDER = "chat-videos"
#: Below ``DATA_DIR``, next to :data:`PENDING_FOLDER` (whose clean-up removes unknown files): the lock that lets
#: one conversion run at a time.
CONVERSION_LOCK = "chat-videos.lock"
#: Waiting files no attachment needs any more are removed after this long.
PENDING_DAYS = 2

#: Why a video could not be converted, shown in the language of each reader.
FAILURES = {
    "convert": gettext_lazy("The video could not be made smaller; it was discarded."),
    "timeout": gettext_lazy("Making the video smaller took too long; it was discarded."),
    "ffmpeg": gettext_lazy("The server lacks ffmpeg; the video was discarded."),
    "interrupted": gettext_lazy("Making the video smaller was interrupted; the video was discarded."),
}

_PICTURE_BRANDS = PICTURE_BRANDS  # HEIC and AVIF are pictures, not videos
#: The name of a waiting video: ours, never anything a user typed.
_SOURCE_NAME = re.compile(r"^[0-9a-f]{24}\.source$")
#: The scale filter for the box of :data:`VIDEO_LONG_SIDE` × :data:`VIDEO_SHORT_SIDE`. The quotes protect the
#: commas inside the expressions from ffmpeg's filter syntax – there is no shell in between.
_SCALE = (
    f"scale=w='if(gte(iw,ih),min({VIDEO_LONG_SIDE},iw),min({VIDEO_SHORT_SIDE},iw))'"
    f":h='if(gte(iw,ih),min({VIDEO_SHORT_SIDE},ih),min({VIDEO_LONG_SIDE},ih))'"
    ":force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1"
)


class VideoError(Exception):
    """Converting a video failed; ``key`` names the reason in :data:`FAILURES`."""

    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key if key in FAILURES else "convert"


# --- ffmpeg on the server -------------------------------------------------------------------------------


def ffmpeg_binary() -> str | None:
    """Where ffmpeg is, or ``None``."""
    return shutil.which("ffmpeg")


def ffprobe_binary() -> str | None:
    """Where ffprobe is, or ``None``."""
    return shutil.which("ffprobe")


def videos_possible() -> bool:
    """Whether the server can take videos: ffmpeg and ffprobe are installed (Ubuntu package ``ffmpeg``)."""
    return bool(ffmpeg_binary() and ffprobe_binary())


def ffmpeg_version() -> str:
    """The version of the installed ffmpeg, e.g. ``6.1.1-3ubuntu5``; empty if it is missing or does not answer."""
    binary = ffmpeg_binary()
    if not binary:
        return ""
    try:
        result = subprocess.run(  # noqa: S603 - a list of arguments, no shell
            [binary, "-nostdin", "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    first = (result.stdout or "").splitlines()[0] if result.stdout else ""
    found = re.match(r"ffmpeg version (\S+)", first)
    return found.group(1) if found else first[:60]


def pending_directory() -> Path:
    """The folder of videos waiting for their conversion (not in the backup)."""
    directory = Path(settings.DATA_DIR) / PENDING_FOLDER
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _source_path(name: str) -> Path | None:
    """The waiting original of this name – ``None`` for a name that is not one of ours."""
    return pending_directory() / name if _SOURCE_NAME.match(name or "") else None


def _priority() -> list[str]:
    """Run ffmpeg with a lower priority, so that people working are not slowed down (as the task timer)."""
    nice = shutil.which("nice")
    return [nice, "-n", "10"] if nice else []


def _run(command: list[str], timeout: int) -> subprocess.CompletedProcess[bytes]:
    """Run ffmpeg or ffprobe: a list of arguments, no shell, nothing on standard input, a time limit.

    Raises:
        VideoError: The program is missing, took too long or failed.
    """
    try:
        result = subprocess.run(  # noqa: S603 - a list of arguments, no shell; the file names are ours
            command, capture_output=True, timeout=timeout, check=False, stdin=subprocess.DEVNULL
        )
    except subprocess.TimeoutExpired as error:
        raise VideoError("timeout") from error
    except OSError as error:
        raise VideoError("ffmpeg") from error
    if result.returncode != 0:
        logger.warning(
            "%s ended with %s: %s",
            next((Path(part).name for part in command if Path(part).name.startswith("ff")), command[0]),
            result.returncode,
            result.stderr[-600:].decode("utf-8", "replace"),
        )
        raise VideoError("convert")
    return result


def probe(path: Path, demuxer: str) -> dict[str, Any]:
    """What ffprobe reads from a video – with this demuxer and the file protocol only.

    Raises:
        VideoError: ffprobe is missing, failed or answered nonsense.
    """
    binary = ffprobe_binary()
    if not binary:
        raise VideoError("ffmpeg")
    result = _run(
        [
            binary,
            "-v",
            "error",
            "-protocol_whitelist",
            "file",
            "-f",
            demuxer,
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        PROBE_TIMEOUT,
    )
    try:
        found = json.loads(result.stdout or b"{}")
    except ValueError as error:
        raise VideoError("convert") from error
    return found if isinstance(found, dict) else {}


def _video_stream(found: dict[str, Any]) -> dict[str, Any] | None:
    """The first real picture stream – not the cover picture of a sound file."""
    for stream in found.get("streams") or []:
        if stream.get("codec_type") == "video" and not (stream.get("disposition") or {}).get("attached_pic"):
            return stream
    return None


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clock(value: Any) -> float:
    """Seconds of a duration as Matroska notes it per stream: ``00:01:02.500000000``."""
    hours, _colon, rest = str(value or "").rpartition(":")
    hours, _colon, minutes = hours.rpartition(":")
    try:
        return int(hours or 0) * 3600 + int(minutes or 0) * 60 + float(rest)
    except ValueError:
        return 0.0


def _duration(found: dict[str, Any], stream: dict[str, Any]) -> float:
    """The length of a video: the longer of what the container and the picture stream say.

    The container alone could claim a few seconds for a stream of an hour.
    """
    tags = {str(key).upper(): value for key, value in (stream.get("tags") or {}).items()}
    return max(
        _number((found.get("format") or {}).get("duration")),
        _number(stream.get("duration")),
        _clock(tags.get("DURATION")),
    )


def _frame_rate(stream: dict[str, Any]) -> float:
    """Frames per second of a picture stream – the average, else the nominal rate; 0 if unknown."""
    for key in ("avg_frame_rate", "r_frame_rate"):
        numerator, _slash, denominator = str(stream.get(key) or "").partition("/")
        rate = _number(numerator) / _number(denominator or 1) if _number(denominator or 1) else 0.0
        if rate > 0:
            return rate
    return 0.0


def stream_problem(found: dict[str, Any], stream: dict[str, Any]) -> str:
    """Why the picture stream of a video is refused before it is converted; empty if it is not (NFA-076, UIX-049).

    Review: a picture larger than :data:`MAX_VIDEO_SIDE` on a side, more
    than :data:`MAX_VIDEO_FPS` frames per second or more than
    :data:`MAX_VIDEO_FRAMES` frames in all – counted by the stream, by its
    rate and length, whichever is more – would keep the server busy for long.
    """
    width, height = int(_number(stream.get("width"))), int(_number(stream.get("height")))
    if width > MAX_VIDEO_SIDE or height > MAX_VIDEO_SIDE:
        return _("The picture of the video is too large: at most %(side)d × %(side)d pixels.") % {
            "side": MAX_VIDEO_SIDE
        }
    rate = _frame_rate(stream)
    frames = max(_number(stream.get("nb_frames")), rate * _duration(found, stream))
    if rate > MAX_VIDEO_FPS or frames > MAX_VIDEO_FRAMES:
        return _("The video has too many frames: at most %(minutes)d minutes at %(rate)d frames per second.") % {
            "minutes": MAX_VIDEO_SECONDS // 60,
            "rate": MAX_VIDEO_FRAMES // MAX_VIDEO_SECONDS,
        }
    return ""


# --- Checking uploads -----------------------------------------------------------------------------------


@dataclass
class Prepared:
    """An upload that passed the checks, ready to be attached to a message."""

    kind: str
    name: str
    size: int
    #: Photos: the smaller photo and its preview (JPEG), with the size of the photo.
    photo: bytes = b""
    thumbnail: bytes = b""
    width: int | None = None
    height: int | None = None
    #: Videos: the waiting original in :func:`pending_directory`, its demuxer and length.
    source: str = ""
    demuxer: str = ""
    duration: float | None = None


def _refused(name: str, problem: str) -> ValidationError:
    """A refusal that names the file."""
    return ValidationError({"files": _("“%(name)s”: %(problem)s") % {"name": name or "?", "problem": problem}})


def _megabytes(size: int) -> int:
    return size // (1024 * 1024)


def _container(head: bytes) -> str:
    """The demuxer of a video by its first bytes; ``"picture"`` for a HEIC or AVIF photo; empty otherwise."""
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return "picture" if head[8:12] in _PICTURE_BRANDS else "mov"
    if len(head) >= 8 and head[4:8] in {b"moov", b"mdat", b"wide", b"free", b"skip", b"pnot"}:
        return "mov"  # QuickTime of old cameras, without "ftyp"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "matroska"  # also WebM
    if head[:4] == b"RIFF" and head[8:12] == b"AVI ":
        return "avi"
    return ""


def prepare_files(files: Sequence[Any]) -> list[Prepared]:
    """Check uploaded files and make photos smaller; videos wait in :func:`pending_directory` (NFA-007).

    Raises:
        ValidationError: (key ``files``) too many, too large, neither photo
            nor video, a format that is not accepted – or a video while the
            server lacks ffmpeg. Nothing is kept then.
    """
    files = [uploaded for uploaded in files if uploaded]
    if len(files) > MAX_FILES:
        raise ValidationError({"files": _("A message may carry at most %(count)d files.") % {"count": MAX_FILES}})
    if sum(getattr(uploaded, "size", 0) or 0 for uploaded in files) > MAX_MESSAGE_BYTES:
        raise ValidationError(
            {
                "files": _("The files of one message may have at most %(megabytes)d MB together.")
                % {"megabytes": _megabytes(MAX_MESSAGE_BYTES)}
            }
        )
    prepared: list[Prepared] = []
    try:
        for uploaded in files:
            prepared.append(_prepare(uploaded))
    except BaseException:
        discard(prepared)
        raise
    return prepared


def discard(prepared: Iterable[Prepared]) -> None:
    """Remove the waiting videos of uploads that were not attached after all."""
    for item in prepared:
        path = _source_path(item.source)
        if path is not None:
            path.unlink(missing_ok=True)


def _prepare(uploaded: Any) -> Prepared:
    name = Path(getattr(uploaded, "name", "") or "").name[:255]
    size = int(getattr(uploaded, "size", 0) or 0)
    if size <= 0:
        raise _refused(name, _("The file is empty."))
    uploaded.seek(0)
    head = uploaded.read(64)
    uploaded.seek(0)
    container = _container(head)
    if container == "picture":
        raise _refused(
            name,
            _("Photos in HEIC or AVIF cannot be read. Please send them as JPEG – phones do so when sharing."),
        )
    if container:
        return _prepare_video(uploaded, name, size, container)
    return _prepare_photo(uploaded, name, size)


def _prepare_photo(uploaded: Any, name: str, size: int) -> Prepared:
    """A photo of a message: checked and made anew by :func:`rentalars.core.photos.render_photo_upload`."""
    try:
        rendered = render_photo_upload(
            uploaded, size=size, max_bytes=MAX_PHOTO_BYTES, not_a_photo=_("This is neither a photo nor a video.")
        )
    except PhotoError as error:
        raise _refused(name, str(error)) from error
    return Prepared(
        kind=AttachmentKind.PHOTO,
        name=name,
        size=size,
        photo=rendered.photo,
        thumbnail=rendered.thumbnail,
        width=rendered.width,
        height=rendered.height,
    )


def _keep_upload(uploaded: Any) -> str:
    """Put an uploaded video into the waiting folder under a name of ours; returns the name."""
    delete_old_sources()
    stored = f"{secrets.token_hex(12)}.source"
    uploaded.seek(0)
    with (pending_directory() / stored).open("wb") as target:
        for chunk in uploaded.chunks():
            target.write(chunk)
    return stored


def _prepare_video(uploaded: Any, name: str, size: int, demuxer: str) -> Prepared:
    if not videos_possible():
        raise _refused(
            name,
            _(
                "Videos need ffmpeg on the server, and it is not installed. Please tell the administration; "
                "photos work all the same."
            ),
        )
    if size > MAX_VIDEO_BYTES:
        raise _refused(
            name, _("The video is too large (at most %(megabytes)d MB).") % {"megabytes": _megabytes(MAX_VIDEO_BYTES)}
        )
    stored = _keep_upload(uploaded)
    path = pending_directory() / stored
    try:
        try:
            found = probe(path, demuxer)
        except VideoError as error:
            raise _refused(name, _("This is neither a photo nor a video.")) from error
        stream = _video_stream(found)
        if stream is None or not stream.get("width") or not stream.get("height"):
            raise _refused(name, _("This is neither a photo nor a video."))
        duration = _duration(found, stream)
        if duration <= 0:
            raise _refused(name, _("This is neither a photo nor a video."))
        if duration > MAX_VIDEO_SECONDS:
            raise _refused(
                name,
                _("The video is too long (at most %(minutes)d minutes).") % {"minutes": MAX_VIDEO_SECONDS // 60},
            )
        problem = stream_problem(found, stream)  # NFA-076
        if problem:
            raise _refused(name, problem)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return Prepared(
        kind=AttachmentKind.VIDEO, name=name, size=size, source=stored, demuxer=demuxer, duration=round(duration, 2)
    )


# --- Attaching -------------------------------------------------------------------------------------------


def _remove_files(names: Iterable[str | None]) -> None:
    storage = ChatAttachment._meta.get_field("file").storage
    for name in names:
        if name:
            storage.delete(name)


def remove_stored(attachments: Iterable[ChatAttachment]) -> None:
    """Remove the stored files of attachments whose message was not written after all."""
    _remove_files(name for attachment in attachments for name in (attachment.file.name, attachment.thumbnail.name))


def attach(message: ChatMessage, prepared: Sequence[Prepared]) -> list[ChatAttachment]:
    """Store the checked uploads at a message; videos start their conversion in the background.

    The caller holds the transaction of the new message. Should storing fail
    halfway, the files stored so far are removed again.
    """
    created: list[ChatAttachment] = []
    try:
        for position, item in enumerate(prepared):
            attachment = ChatAttachment(message=message, kind=item.kind, original_name=item.name, position=position)
            created.append(attachment)
            if item.kind == AttachmentKind.PHOTO:
                attachment.file.save("foto.jpg", ContentFile(item.photo), save=False)
                attachment.thumbnail.save("vorschau.jpg", ContentFile(item.thumbnail), save=False)
                attachment.size = len(item.photo)
                attachment.width, attachment.height = item.width, item.height
            else:
                attachment.state = AttachmentState.PROCESSING
                attachment.source = item.source
                attachment.duration = item.duration
                attachment.size = item.size
            attachment.save()
    except BaseException:
        remove_stored(created)
        raise
    for attachment in created:
        if attachment.state == AttachmentState.PROCESSING:
            _start_conversion(attachment, demuxer=prepared[attachment.position].demuxer)
    return created


def _start_conversion(attachment: ChatAttachment, *, demuxer: str) -> None:
    """Start the task that makes the video smaller (NFA-041).

    The task has no starter: the chat shows when the video is ready – no
    notification "Bereit" for every video –, and only a failure is told to
    the sender (:func:`_fail`).
    """
    from rentalars.core.jobs import start_job

    project = attachment.message.project
    start_job(
        "chat_video",
        {"attachment": attachment.pk, "demuxer": demuxer},
        user=None,
        title=_("Video for the chat of %(project)s") % {"project": project.number},
    )


def _touch(message_id: int) -> None:
    """Count a change of the message: the chat of everybody reading fetches it anew (UIX-020)."""
    ChatMessage.objects.filter(pk=message_id).update(revision=F("revision") + 1)


# --- Converting a video (the task) -------------------------------------------------------------------


class _Finished(File):
    """A file written next to the media folder: the storage moves it into place instead of copying it."""

    def temporary_file_path(self) -> str:
        """Where the file is now."""
        return str(self.name)


def _poster(binary: str, video: Path, duration: float) -> bytes:
    """The poster frame of a converted video as a preview (JPEG), taken from the first second."""
    at = min(1.0, duration / 3) if duration else 0.0
    result = _run(
        [
            *_priority(),
            binary,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-protocol_whitelist",
            "file",
            "-f",
            "mov",
            "-ss",
            f"{at:.2f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-c:v",
            "mjpeg",
            "-q:v",
            "3",
            "pipe:1",
        ],
        PROBE_TIMEOUT,
    )
    from PIL import Image

    with open_picture(io.BytesIO(result.stdout), ["JPEG"]) as frame:  # what ffmpeg was asked for (mjpeg)
        picture = _rgb(frame)
    picture.thumbnail((THUMBNAIL_LONGEST_SIDE, THUMBNAIL_LONGEST_SIDE), Image.Resampling.LANCZOS)
    return _jpeg(picture, THUMBNAIL_QUALITY, None)


def convert(source: Path, demuxer: str, output: Path) -> None:
    """Make a video smaller with ffmpeg: H.264/AAC in MP4, at most 720p and 30 frames per second.

    No metadata is taken over (``-map_metadata -1``): not the place a phone
    notes in a video. The phone's rotation is applied to the picture itself.

    Raises:
        VideoError: ffmpeg is missing, took longer than :data:`CONVERT_TIMEOUT` or failed.
    """
    binary = ffmpeg_binary()
    if not binary:
        raise VideoError("ffmpeg")
    # fmt: off
    command = [
        *_priority(), binary, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-protocol_whitelist", "file", "-f", demuxer, "-i", str(source),
        "-map", "0:v:0", "-map", "0:a:0?", "-map_metadata", "-1", "-map_chapters", "-1", "-sn", "-dn",
        "-vf", _SCALE, "-fpsmax", str(VIDEO_MAX_FPS),
        "-c:v", "libx264", "-preset", VIDEO_PRESET, "-crf", str(VIDEO_CRF),
        "-maxrate", VIDEO_MAX_RATE, "-bufsize", "6M", "-pix_fmt", "yuv420p", "-profile:v", "high",
        "-c:a", "aac", "-b:a", VIDEO_AUDIO_BITRATE, "-ac", "2",
        "-t", str(MAX_VIDEO_SECONDS),  # Review: never more than the longest video allowed, whatever was claimed
        "-movflags", "+faststart", "-f", "mp4", str(output),
    ]
    # fmt: on
    _run(command, CONVERT_TIMEOUT)


@contextlib.contextmanager
def conversion_slot() -> Iterator[bool]:
    """The gate of the task ``chat_video``: one conversion at a time on this server (NFA-076).

    Yields whether this process got the slot – a lock file in ``DATA_DIR``
    held with ``flock``, without waiting. Every conversion takes one or two
    cores and a lot of memory for up to an hour; ten videos at once would
    halt the server. The kernel lets go of the lock when the process ends,
    also by a crash: the timer then runs the videos left waiting
    (``core.jobs.run_waiting_jobs``).
    """
    path = Path(settings.DATA_DIR) / CONVERSION_LOCK
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _demuxer_of(path: Path) -> str:
    with path.open("rb") as handle:
        return _container(handle.read(64))


def run_job(job: BackgroundJob) -> str:
    """The task ``chat_video``: convert the video of an attachment, store it, delete the original.

    A failure is not a failed task – the video was what it was: the
    attachment says so, the original is discarded, the sender is told. Only
    a disk that cannot be written to is an error for the operators.
    """
    attachment = (
        ChatAttachment.objects.select_related("message__project", "message__author")
        .filter(pk=job.params.get("attachment"))
        .first()
    )
    if attachment is None or attachment.state != AttachmentState.PROCESSING:
        return _("The video is no longer waiting.")
    source = _source_path(attachment.source)
    output = pending_directory() / f"{secrets.token_hex(12)}.mp4.part"
    started = time.monotonic()
    try:
        if source is None or not source.is_file():
            raise VideoError("interrupted")
        demuxer = str(job.params.get("demuxer") or "") or _demuxer_of(source)
        if demuxer not in {"mov", "matroska", "avi"}:
            raise VideoError("convert")
        convert(source, demuxer, output)
        found = probe(output, "mov")
        stream = _video_stream(found)
        if stream is None or not stream.get("width") or not stream.get("height"):
            raise VideoError("convert")
        duration = _duration(found, stream)
        size = output.stat().st_size
        _store(attachment, output, _poster_or_none(output, duration), stream, duration, size)
    except VideoError as error:
        _fail(attachment, error.key)
        return str(FAILURES[error.key])
    except OSError:
        logger.exception("Storing the converted video of chat attachment %s failed.", attachment.pk)
        _fail(attachment, "convert")
        return str(FAILURES["convert"])
    finally:
        output.unlink(missing_ok=True)
    logger.info(
        "Chat video %s: %s MB made %s MB in %.0f s.",
        attachment.pk,
        _megabytes(attachment.size),
        _megabytes(size),
        time.monotonic() - started,
    )
    return _("The video is in the chat.")


def _poster_or_none(output: Path, duration: float) -> bytes:
    """The poster frame, or nothing if ffmpeg found no picture to take: the video plays all the same."""
    binary = ffmpeg_binary()
    if not binary:
        return b""
    try:
        return _poster(binary, output, duration)
    except (VideoError, OSError, SyntaxError, ValueError):
        return b""


def _store(
    attachment: ChatAttachment, output: Path, poster: bytes, stream: dict[str, Any], duration: float, size: int
) -> None:
    """Move the converted video and its poster frame into the media folder and mark the attachment ready.

    If the message was deleted meanwhile, the files go again.
    """
    try:
        with output.open("rb") as handle:
            attachment.file.save("video.mp4", _Finished(handle, name=str(output)), save=False)
        if poster:
            attachment.thumbnail.save("poster.jpg", ContentFile(poster), save=False)
    except BaseException:
        _remove_files([attachment.file.name, attachment.thumbnail.name])
        raise
    width, height = int(stream["width"]), int(stream["height"])
    updated = ChatAttachment.objects.filter(pk=attachment.pk, state=AttachmentState.PROCESSING).update(
        state=AttachmentState.READY,
        file=attachment.file.name,
        thumbnail=attachment.thumbnail.name,
        width=width,
        height=height,
        duration=round(duration, 2),
        size=size,
        source="",
    )
    if not updated:
        _remove_files([attachment.file.name, attachment.thumbnail.name])
        return
    path = _source_path(attachment.source)
    if path is not None:
        path.unlink(missing_ok=True)
    _touch(attachment.message_id)


def _fail(attachment: ChatAttachment, key: str, *, tell: bool = True) -> None:
    """Mark a video as failed: the original is discarded, the chat says why, the sender is told."""
    updated = ChatAttachment.objects.filter(pk=attachment.pk, state=AttachmentState.PROCESSING).update(
        state=AttachmentState.FAILED, failure=key, source=""
    )
    path = _source_path(attachment.source)
    if path is not None:
        path.unlink(missing_ok=True)
    attachment.state, attachment.failure, attachment.source = AttachmentState.FAILED, key, ""
    if not updated:
        return
    _touch(attachment.message_id)
    message = attachment.message
    if tell and message.author_id:
        from rentalars.core.i18n import LocalText
        from rentalars.notifications.models import Kind
        from rentalars.notifications.services import notify

        project = message.project
        notify(
            [message.author],
            Kind.JOB_FINISHED,
            LocalText(gettext_lazy("Video for the chat of %(project)s failed"), project=project.number),
            body=LocalText(FAILURES[key]),
            url=reverse("chat:project", args=[project]) + f"#m{message.pk}",
            project=project,
        )


def expire_stuck(messages: Iterable[ChatMessage]) -> None:
    """Videos "processing" for longer than :data:`STUCK_AFTER` lost their task: they count as failed.

    Looks only at the attachments already loaded with the messages – no query
    unless one is found.
    """
    limit = timezone.now() - STUCK_AFTER
    for message in messages:
        for attachment in message.attachments.all():
            if attachment.state == AttachmentState.PROCESSING and attachment.created_at < limit:
                if _in_line(attachment):
                    continue
                attachment.message = message
                _fail(attachment, "interrupted", tell=False)


def _in_line(attachment: ChatAttachment) -> bool:
    """Whether the task of a video still waits for its turn or runs – not longer than :data:`STUCK_IN_LINE_AFTER`.

    Review: one video is converted at a time, so a video may wait for
    others for longer than :data:`STUCK_AFTER` without being lost.
    """
    from rentalars.core.models import BackgroundJob, JobStatus

    if attachment.created_at < timezone.now() - STUCK_IN_LINE_AFTER:
        return False
    return BackgroundJob.objects.filter(
        kind="chat_video", status__in=[JobStatus.QUEUED, JobStatus.RUNNING], params__attachment=attachment.pk
    ).exists()


def delete_old_sources(days: int = PENDING_DAYS) -> int:
    """Remove waiting files that no video waits for any more – left by a crash; returns how many."""
    limit = time.time() - days * 86400
    waiting = set(
        ChatAttachment.objects.filter(state=AttachmentState.PROCESSING)
        .exclude(source="")
        .values_list("source", flat=True)
    )
    count = 0
    for path in pending_directory().iterdir():
        try:
            if path.is_file() and path.name not in waiting and path.stat().st_mtime < limit:
                path.unlink()
                count += 1
        except OSError:
            continue
    return count


def files_deleted(sender: Any, instance: ChatAttachment, **kwargs: Any) -> None:
    """``post_delete`` of an attachment: its files go once the deletion is committed – also with the project."""
    names = [field.name for field in (instance.file, instance.thumbnail) if field]
    source = instance.source

    def remove() -> None:
        _remove_files(names)
        path = _source_path(source)
        if path is not None:
            path.unlink(missing_ok=True)

    transaction.on_commit(remove)


# --- Showing ---------------------------------------------------------------------------------------------


def summary(photos: int, videos: int) -> str:
    """What a message carries, in the active language: "1 Foto", "2 Fotos, 1 Video"."""
    parts = []
    if photos:
        parts.append(ngettext("%(count)d photo", "%(count)d photos", photos) % {"count": photos})
    if videos:
        parts.append(ngettext("%(count)d video", "%(count)d videos", videos) % {"count": videos})
    return ", ".join(parts)


def download_name(attachment: ChatAttachment, *, small: bool = False) -> str:
    """The name a file is shown or saved under: ``Chat-Foto-17.jpg``, ``Chat-Video-18.mp4``."""
    extension = Path((attachment.thumbnail if small else attachment.file).name or "").suffix.lower() or ".jpg"
    kind = "Video" if attachment.kind == AttachmentKind.VIDEO else "Foto"
    return f"Chat-{kind}-{attachment.pk}{'-klein' if small else ''}{extension}"


def file_response(attachment: ChatAttachment, *, small: bool = False) -> HttpResponse:
    """Deliver the photo or video of an attachment – or its preview – after the caller checked the rights.

    Shown in the browser, not downloaded; through NGINX on a server, which
    also answers the range requests a video player makes (NFA-007). The
    files never change: the browser may keep them for a day.
    """
    from rentalars.core.uploads import protected_file_response

    field = attachment.thumbnail if small else attachment.file
    if not attachment.is_ready or not field.name:
        raise Http404
    response = protected_file_response(field.name)
    response["Content-Disposition"] = (
        content_disposition_header(False, download_name(attachment, small=small)) or "inline"
    )
    response["Content-Security-Policy"] = "sandbox; default-src 'none'; img-src 'self'; media-src 'self'"
    response["Cache-Control"] = "private, max-age=86400"
    return response
