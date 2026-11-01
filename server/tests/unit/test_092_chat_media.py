# SPDX-License-Identifier: GPL-3.0-or-later
"""Photos and videos in the chat, made smaller on the server (UIX-049; UIX-010).

The requirement: photos and videos can be included in the chat, compressed. Decided: they are made smaller on the
server.

* Photos: checked by their content, upright, at most 2048 pixels on the long
  side, JPEG without metadata (no GPS, no device); a preview for the chat.
* Videos: checked by their content (container and ffprobe), converted in
  the background with ffmpeg to at most 720p H.264/AAC – without metadata;
  "Video wird verkleinert …" until then; a failure discards the upload and
  says so. Without ffmpeg videos are refused, photos work; the self-check warns (NFA-076).
* Delivered only to whoever may read the chat – the crew in the deployment
  view and the people working on a service case included; deleted with
  their message or project.
* The API names the attachments of every message and takes files as
  ``multipart/form-data``; a notification names them ("1 Foto").
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from unittest import mock, skipUnless

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import ExifTags, Image

from rentalars.chat import media
from rentalars.chat import services as chat
from rentalars.chat.models import AttachmentKind, AttachmentState, ChatAttachment, ChatMessage
from rentalars.core import selfcheck
from rentalars.core.i18n import written_for
from rentalars.core.models import BackgroundJob, JobStatus
from rentalars.notifications.models import Kind, Notification
from rentalars.projects import service_cases
from tests.api.base import API, ApiTestCase
from tests.helpers import RentalarsTestCase, at, make_customer, make_person, make_project, make_user, plan, set_clock
from tests.ui.base import UiTestCase

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
NO_FFMPEG = "ffmpeg/ffprobe are not installed here: the real conversion is not tried (the mocked one is)."

RED, BLUE = (220, 20, 20), (20, 40, 220)


# --- Files made for the tests ---------------------------------------------------------------------------------


def photo(
    width: int = 4000, height: int = 3000, *, image_format: str = "JPEG", orientation: int | None = None
) -> bytes:
    """A photo as a phone writes it: blue with a red corner top left, with place, device, comment and XMP."""
    mode = "RGBA" if image_format == "PNG" else "RGB"
    image = Image.new(mode, (width, height), BLUE + ((255,) if mode == "RGBA" else ()))
    corner = (0, 0, width // 4, height // 4)
    image.paste(RED + ((255,) if mode == "RGBA" else ()), corner)
    stored = io.BytesIO()
    if image_format == "JPEG":
        exif = Image.Exif()
        exif[ExifTags.Base.Make] = "Testphone"
        if orientation:
            exif[ExifTags.Base.Orientation] = orientation
        gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
        gps[ExifTags.GPS.GPSLatitudeRef] = "N"
        gps[ExifTags.GPS.GPSLatitude] = (52.0, 31.0, 12.0)
        gps[ExifTags.GPS.GPSLongitudeRef] = "E"
        gps[ExifTags.GPS.GPSLongitude] = (13.0, 24.0, 18.0)
        gps[ExifTags.GPS.GPSAltitudeRef] = 0
        gps[ExifTags.GPS.GPSAltitude] = 34.0
        gps[ExifTags.GPS.GPSDateStamp] = "2027:03:01"  # the time of the place is not kept
        gps[ExifTags.GPS.GPSImgDirection] = 90.0
        image.save(stored, "JPEG", exif=exif, comment=b"Geheimer Kommentar", xmp=b"<x:xmpmeta>Ort</x:xmpmeta>")
    else:
        image.save(stored, image_format)
    return stored.getvalue()


def transparent_png() -> bytes:
    image = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
    image.paste((20, 40, 220, 255), (0, 0, 150, 200))
    stored = io.BytesIO()
    image.save(stored, "PNG")
    return stored.getvalue()


def upload(content: bytes, name: str = "IMG_0001.jpg", content_type: str = "image/jpeg") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type)


def video(folder: Path, *, size: str = "1920x1080", rotation: int | None = None, seconds: float = 2) -> bytes:
    """A short video with sound and the place a phone notes, made by ffmpeg."""
    plain = folder / "plain.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size={size}:rate=60:duration={seconds}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            "-metadata",
            "location=+52.5200+013.4050/",
            str(plain),
        ],
        check=True,
        timeout=120,
    )
    if rotation is None:
        return plain.read_bytes()
    rotated = folder / "rotated.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-display_rotation",
            str(rotation),
            "-i",
            str(plain),
            "-c",
            "copy",
            str(rotated),
        ],
        check=True,
        timeout=60,
    )
    return rotated.read_bytes()


def probe_file(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True,
        check=True,
        timeout=60,
    )
    return json.loads(result.stdout)


class FilesMixin:
    """Media and waiting videos in folders of the test; Rentalars delivers the files itself (no NGINX)."""

    def setUp(self) -> None:
        super().setUp()  # type: ignore[misc]
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)  # type: ignore[attr-defined]
        override = override_settings(DATA_DIR=folder, MEDIA_ROOT=str(folder / "media"), SERVE_MEDIA_VIA_NGINX=False)
        override.enable()
        self.addCleanup(override.disable)  # type: ignore[attr-defined]
        self.folder = folder
        self.media_root = folder / "media"
        self.work = folder / "work"
        self.work.mkdir()

    def stored(self, name: str) -> Path:
        return self.media_root / name

    def waiting(self) -> list[str]:
        return sorted(path.name for path in media.pending_directory().iterdir())


class ChatScene(FilesMixin):
    """A project with its manager Lena, Anna (Crew) planned in it, and Otto (Crew) who is not."""

    def make_scene(self) -> None:
        self.manager = make_user("lena", roles=("Projektleitung",))
        self.manager.first_name, self.manager.last_name = "Lena", "Krause"
        self.manager.save()
        self.project = make_project(manager=self.manager)
        self.crew_user = make_user("anna", roles=("Crew",))
        self.anna = make_person("Anna Becker", user=self.crew_user)
        self.crew_user.refresh_from_db()
        plan(self.project, "Tontechnik", self.anna)
        self.outsider = make_user("otto", roles=("Crew",))
        make_person("Otto Weber", user=self.outsider)
        self.url = f"/projects/{self.project.number}/chat/"


# --- Photos -------------------------------------------------------------------------------------------------------


class PhotoTests(FilesMixin, RentalarsTestCase):
    """Photos are made smaller at once: upright, at most 2048 pixels, with the place and without other metadata."""

    def test_upright_smaller_and_without_metadata(self) -> None:
        original = photo(4000, 3000, orientation=6)  # stored lying, to be turned 90° clockwise
        self.assertIn(b"Testphone", original)
        (prepared,) = media.prepare_files([upload(original)])
        self.assertEqual((prepared.kind, prepared.name, prepared.size), ("photo", "IMG_0001.jpg", len(original)))
        self.assertEqual((prepared.width, prepared.height), (1536, 2048))
        with Image.open(io.BytesIO(prepared.photo)) as image:
            self.assertEqual((image.format, image.size), ("JPEG", (1536, 2048)))
            # The place stays, nothing else: no device, no orientation, no comment, no XMP, no time of the place.
            self.assertEqual(set(image.getexif()) - {ExifTags.IFD.GPSInfo}, set())
            place = image.getexif().get_ifd(ExifTags.IFD.GPSInfo)
            self.assertEqual(
                {ExifTags.GPS(tag).name for tag in place},
                {"GPSLatitudeRef", "GPSLatitude", "GPSLongitudeRef", "GPSLongitude", "GPSAltitudeRef", "GPSAltitude"},
            )
            self.assertEqual((place[ExifTags.GPS.GPSLatitudeRef], place[ExifTags.GPS.GPSLongitudeRef]), ("N", "E"))
            self.assertEqual([float(part) for part in place[ExifTags.GPS.GPSLatitude]], [52.0, 31.0, 12.0])
            self.assertNotIn("comment", image.info)
            self.assertNotIn("xmp", image.info)
            # Turned: the red corner of the top left is now top right.
            rgb = image.convert("RGB")
            self.assertGreater(rgb.getpixel((1536 - 40, 40))[0], 180)
            self.assertLess(rgb.getpixel((40, 40))[0], 80)
        for secret in (b"Testphone", b"Geheimer Kommentar", b"<x:xmpmeta>", b"2027:03:01"):
            self.assertNotIn(secret, prepared.photo)
            self.assertNotIn(secret, prepared.thumbnail)
        with Image.open(io.BytesIO(prepared.thumbnail)) as preview:
            self.assertEqual(preview.size, (480, 640))
            # The preview carries nothing, not even the place.
            self.assertEqual(dict(preview.getexif()), {})

    def test_small_photos_stay_as_large_and_transparency_turns_white(self) -> None:
        (small,) = media.prepare_files([upload(photo(800, 600))])
        self.assertEqual((small.width, small.height), (800, 600))
        (png,) = media.prepare_files([upload(transparent_png(), "screenshot.png", "image/png")])
        with Image.open(io.BytesIO(png.photo)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.convert("RGB").getpixel((250, 100)), (255, 255, 255))
        (webp,) = media.prepare_files([upload(photo(1000, 500, image_format="WEBP"), "bild.webp", "image/webp")])
        self.assertEqual((webp.width, webp.height), (1000, 500))


class TypeCheckTests(FilesMixin, RentalarsTestCase):
    """The content decides, not the name: a renamed file is refused; limits are named constants.

    The self-check warns without ffmpeg and of an NGINX that takes smaller uploads than the chat (NFA-076).
    """

    def refused(self, *files: SimpleUploadedFile) -> str:
        with self.assertRaises(ValidationError) as caught:
            media.prepare_files(list(files))
        return " ".join(caught.exception.message_dict["files"])

    def test_a_fake_photo_and_formats_that_are_not_taken(self) -> None:
        self.assertEqual(
            self.refused(upload(b"<html><script>alert(1)</script></html>", "foto.jpg")),
            "„foto.jpg“: Das ist weder ein Foto noch ein Video.",
        )
        bmp = io.BytesIO()
        Image.new("RGB", (20, 20)).save(bmp, "BMP")
        self.assertIn("Fotos werden als JPEG, PNG, GIF oder WebP angenommen.", self.refused(upload(bmp.getvalue())))
        heic = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic" + b"\x00" * 64
        self.assertIn("HEIC oder AVIF", self.refused(upload(heic, "IMG_0002.HEIC", "image/heic")))
        self.assertIn("Die Datei ist leer.", self.refused(upload(b"", "leer.jpg")))
        self.assertEqual(self.waiting(), [])

    def test_a_fake_video(self) -> None:
        fake = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41" + b"kein Video " * 200
        with mock.patch.object(media, "videos_possible", return_value=True):
            text = self.refused(upload(fake, "film.mp4", "video/mp4"))
        if HAS_FFMPEG:
            self.assertEqual(text, "„film.mp4“: Das ist weder ein Foto noch ein Video.")
        else:
            self.assertIn("film.mp4", text)
        # A text with the name of a video is checked as what it is.
        self.assertIn("weder ein Foto noch ein Video", self.refused(upload(b"hallo", "film.mov", "video/quicktime")))
        self.assertEqual(self.waiting(), [], "nothing of a refused video is kept")

    def test_limits(self) -> None:
        with mock.patch.object(media, "MAX_PHOTO_BYTES", 1000):
            self.assertIn("Das Foto ist zu groß (höchstens 0 MB).", self.refused(upload(photo(400, 300))))
        too_many = [upload(photo(10, 10), f"{number}.jpg") for number in range(media.MAX_FILES + 1)]
        self.assertEqual(self.refused(*too_many), "Eine Nachricht darf höchstens 10 Dateien enthalten.")
        self.assertEqual((media.MAX_PHOTO_BYTES, media.MAX_VIDEO_BYTES), (25 * 1024**2, 200 * 1024**2))
        self.assertLessEqual(media.MAX_MESSAGE_BYTES, 510 * 1024**2, "NGINX takes 510 MB per request")

    def test_the_self_check_warns_of_an_nginx_too_small_for_videos(self) -> None:
        def findings(site: str) -> list[tuple[str, str]]:
            report = selfcheck.Report()
            selfcheck._nginx_body_size(report, "Sicherheit", site)
            return [(finding.state, finding.detail) for finding in report.findings]

        self.assertEqual(
            findings("client_max_body_size 100m;\n"),
            [
                (
                    selfcheck.WARNING,
                    "NGINX nimmt Anfragen bis 100 MB an, Videos im Chat dürfen bis 200 MB groß sein. Größere Dateien "
                    "scheitern beim Hochladen. Übernehmen mit: sudo rentalars nginx-site",
                )
            ],
        )
        template = (Path(__file__).resolve().parents[2] / "deploy" / "nginx" / "rentalars.conf").read_text()
        self.assertEqual(findings(template), [], "the template of this version takes the videos")

    def test_without_ffmpeg_videos_are_refused_and_photos_work(self) -> None:
        clip = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41" + b"\x00" * 100
        with mock.patch.object(media.shutil, "which", return_value=None):
            self.assertFalse(media.videos_possible())
            self.assertEqual(
                self.refused(upload(clip, "clip.mp4", "video/mp4")),
                "„clip.mp4“: Videos brauchen ffmpeg auf dem Server, und das ist nicht installiert. Bitte der "
                "Administration Bescheid geben; Fotos gehen trotzdem.",
            )
            self.assertEqual(len(media.prepare_files([upload(photo(100, 100))])), 1)
            report = selfcheck.Report()
            selfcheck._versions(report)
        found = {finding.title: finding for finding in report.findings}
        self.assertEqual(found["ffmpeg"].state, selfcheck.WARNING)
        self.assertIn("Videos im Chat werden abgelehnt, Fotos gehen.", found["ffmpeg"].detail)
        self.assertIn("sudo apt install ffmpeg", found["ffmpeg"].detail)

    @skipUnless(HAS_FFMPEG, NO_FFMPEG)
    def test_the_self_check_names_the_version_of_ffmpeg(self) -> None:
        report = selfcheck.Report()
        selfcheck._versions(report)
        finding = next(finding for finding in report.findings if finding.title == "ffmpeg")
        self.assertEqual(finding.state, selfcheck.OK)
        self.assertRegex(finding.detail, r"^\d")


# --- Videos ----------------------------------------------------------------------------------------------------


class FakeFfmpeg:
    """Stands in for ffmpeg and ffprobe: notes each call and writes what the real ones would write."""

    def __init__(self, *, fail_convert: bool = False) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self.fail_convert = fail_convert

    def __call__(self, command: list[str], **options: Any) -> subprocess.CompletedProcess[bytes]:
        self.calls.append((command, options))
        program = Path(next(part for part in command if "ff" in Path(part).name)).name
        if program == "ffprobe":
            answer = {
                "format": {"duration": "2.000", "format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
                "streams": [{"codec_type": "video", "width": 1280, "height": 720}, {"codec_type": "audio"}],
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(answer).encode(), b"")
        if "image2pipe" in command:
            frame = io.BytesIO()
            Image.new("RGB", (1280, 720), BLUE).save(frame, "JPEG")
            return subprocess.CompletedProcess(command, 0, frame.getvalue(), b"")
        if self.fail_convert:
            return subprocess.CompletedProcess(command, 1, b"", b"Invalid data found when processing input")
        Path(command[-1]).write_bytes(b"\x00\x00\x00\x20ftypisom converted")
        return subprocess.CompletedProcess(command, 0, b"", b"")


CLIP = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41" + b"\x01" * 2000


class VideoJobTests(ChatScene, RentalarsTestCase):
    """The task "chat_video": ffmpeg without shell, with -nostdin and a time limit; stored, or discarded."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()

    def post_with_fake(self, fake: FakeFfmpeg, text: str = "") -> ChatMessage:
        with (
            mock.patch.object(media.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"),
            mock.patch.object(media.subprocess, "run", side_effect=fake),
            self.captureOnCommitCallbacks(execute=True),
        ):
            return chat.post_message(
                self.project, user=self.crew_user, text=text, files=[upload(CLIP, "VID_0001.mp4", "video/mp4")]
            )

    def test_the_command_and_the_stored_video(self) -> None:
        fake = FakeFfmpeg()
        message = self.post_with_fake(fake)
        attachment = message.attachments.get()
        self.assertEqual((attachment.kind, attachment.state), (AttachmentKind.VIDEO, AttachmentState.READY))
        self.assertEqual((attachment.width, attachment.height, attachment.duration), (1280, 720, 2.0))
        self.assertTrue(attachment.file.name.startswith(f"chat/{self.project.pk}/"))
        self.assertTrue(attachment.file.name.endswith(".mp4"))
        self.assertTrue(self.stored(attachment.file.name).is_file())
        self.assertTrue(self.stored(attachment.thumbnail.name).is_file())
        self.assertEqual(attachment.source, "")
        self.assertEqual(self.waiting(), [], "the original and the temporary file are gone")
        message.refresh_from_db()
        self.assertEqual(message.revision, 1, "the chat of the readers fetches the message anew")
        convert = next(command for command, _options in fake.calls if "libx264" in command)
        options = next(options for command, options in fake.calls if "libx264" in command)
        self.assertIsInstance(convert, list)
        self.assertNotIn("shell", options)
        self.assertEqual(options["timeout"], media.CONVERT_TIMEOUT)
        self.assertEqual(options["stdin"], subprocess.DEVNULL)
        self.assertEqual(convert[:3], ["/usr/bin/nice", "-n", "10"])
        for expected in ("-nostdin", "+faststart", "yuv420p", "aac"):
            self.assertIn(expected, convert)
        self.assertEqual(convert[convert.index("-map_metadata") + 1], "-1")
        self.assertEqual(convert[convert.index("-crf") + 1], str(media.VIDEO_CRF))
        self.assertEqual(convert[convert.index("-fpsmax") + 1], "30")
        self.assertEqual(convert[convert.index("-f") + 1], "mov", "read with the demuxer the content showed")
        self.assertEqual(convert[convert.index("-protocol_whitelist") + 1], "file")
        self.assertIn("min(1280,iw)", convert[convert.index("-vf") + 1])
        self.assertTrue(convert[-1].startswith(str(self.folder / media.PENDING_FOLDER)))
        # Every call, ffprobe included, is a list without shell, with nothing on standard input.
        for command, options in fake.calls:
            self.assertIsInstance(command, list)
            self.assertIn("timeout", options)
        # No "Bereit" for every video: the task has no starter to tell.
        self.assertFalse(Notification.objects.filter(kind=Kind.JOB_FINISHED).exists())

    def test_a_failure_discards_the_upload_and_says_so(self) -> None:
        message = self.post_with_fake(FakeFfmpeg(fail_convert=True), text="Der Aufbau")
        attachment = message.attachments.get()
        self.assertEqual((attachment.state, attachment.failure), (AttachmentState.FAILED, "convert"))
        self.assertEqual((attachment.file.name, attachment.thumbnail.name, attachment.source), ("", "", ""))
        self.assertEqual(self.waiting(), [])
        self.assertEqual(attachment.failure_text, "Das Video ließ sich nicht verkleinern; es wurde verworfen.")
        notice = Notification.objects.get(user=self.crew_user, kind=Kind.JOB_FINISHED)
        self.assertEqual(notice.title, f"Video für den Chat von {self.project.number} fehlgeschlagen")
        self.assertEqual(notice.url, f"{self.url}#m{message.pk}")
        self.assertEqual(list(self.media_root.rglob("*.mp4")), [])

    def test_a_video_stuck_for_hours_counts_as_failed(self) -> None:
        with self.settings(JOBS_RUN_INLINE=False), self.captureOnCommitCallbacks(execute=False):
            message = self.post_with_fake(FakeFfmpeg())
        attachment = message.attachments.get()
        self.assertEqual(attachment.state, AttachmentState.PROCESSING)
        self.assertEqual(self.waiting(), [attachment.source])
        set_clock(at(1, 10))
        chat.messages_of(self.project)
        self.assertEqual(attachment.state, AttachmentState.PROCESSING)
        # Review (NFA-076): videos are converted one at a time, so a video whose task still waits in line
        # is not lost after 3 hours (tests/unit/test_092_review_media.py). Here its task is lost – as after a
        # restart with the timer off.
        BackgroundJob.objects.filter(kind="chat_video").update(status=JobStatus.FAILED)
        set_clock(at(1, 11, 30))
        chat.messages_of(self.project)
        attachment.refresh_from_db()
        self.assertEqual((attachment.state, attachment.failure), (AttachmentState.FAILED, "interrupted"))
        self.assertEqual(self.waiting(), [])

    @skipUnless(HAS_FFMPEG, NO_FFMPEG)
    def test_the_real_conversion(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            message = chat.post_message(
                self.project, user=self.crew_user, text="", files=[upload(video(self.work), "VID.mp4", "video/mp4")]
            )
        attachment = message.attachments.get()
        self.assertEqual(attachment.state, AttachmentState.READY, attachment.failure)
        self.assertEqual((attachment.width, attachment.height), (1280, 720))
        self.assertAlmostEqual(attachment.duration, 2.0, delta=0.2)
        found = probe_file(self.stored(attachment.file.name))
        streams = {stream["codec_type"]: stream for stream in found["streams"]}
        self.assertEqual((streams["video"]["codec_name"], streams["audio"]["codec_name"]), ("h264", "aac"))
        self.assertEqual(streams["video"]["avg_frame_rate"], "30/1")
        self.assertNotIn("location", found["format"].get("tags", {}))
        with Image.open(self.stored(attachment.thumbnail.name)) as poster:
            self.assertEqual((poster.format, max(poster.size)), ("JPEG", 640))
        self.assertEqual(self.waiting(), [])

    @skipUnless(HAS_FFMPEG, NO_FFMPEG)
    def test_an_upright_phone_video_stays_upright(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            message = chat.post_message(
                self.project,
                user=self.crew_user,
                text="",
                files=[upload(video(self.work, rotation=90, seconds=1), "hoch.mp4", "video/mp4")],
            )
        attachment = message.attachments.get()
        self.assertEqual((attachment.state, attachment.width, attachment.height), (AttachmentState.READY, 720, 1280))


# --- Rights, deletion, notifications -----------------------------------------------------------------------


class RightsAndDeletionTests(ChatScene, UiTestCase):
    """Whoever may read the chat gets its files – nobody else; they go with their message or project."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        with self.captureOnCommitCallbacks(execute=True):
            self.message = chat.post_message(
                self.project, user=self.manager, text="Bühne", files=[upload(photo(1200, 900))]
            )
        self.attachment = self.message.attachments.get()
        self.photo_url = f"{self.url}media/{self.attachment.pk}/"

    def test_the_crew_in_the_deployment_view_reads_the_files_others_do_not(self) -> None:
        crew = self.browser_of(self.crew_user)
        response = crew.get(self.photo_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertEqual(response["Content-Disposition"], f'inline; filename="Chat-Foto-{self.attachment.pk}.jpg"')
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["Cache-Control"], "private, max-age=86400")
        self.assertIn("sandbox", response["Content-Security-Policy"])
        with Image.open(io.BytesIO(b"".join(response.streaming_content))) as image:
            self.assertEqual(image.size, (1200, 900))
        small = crew.get(f"{self.photo_url}small/")
        with Image.open(io.BytesIO(b"".join(small.streaming_content))) as image:
            self.assertEqual(image.size, (640, 480))
        self.assertEqual(self.browser_of(self.outsider).get(self.photo_url).status_code, 404)
        self.assertEqual(self.browser_of(self.outsider).get(f"{self.photo_url}small/").status_code, 404)
        # Without the module "projects" not even the address answers – as the chat itself.
        self.assertEqual(self.browser_for("ohne").get(self.photo_url).status_code, 403)
        # Through another project's chat: not found.
        other = make_project("Anderes")
        self.assertEqual(self.client.get(f"/projects/{other.number}/chat/media/{self.attachment.pk}/").status_code, 404)

    def test_through_nginx(self) -> None:
        with self.settings(SERVE_MEDIA_VIA_NGINX=True):
            response = self.client.get(self.photo_url)
        self.assertEqual(response["X-Accel-Redirect"], f"/protected-media/{self.attachment.file.name}")
        self.assertNotIn("Content-Type", response)

    def test_the_people_working_on_a_service_case(self) -> None:
        paula = make_user("paula", roles=("Projektleitung",))
        kai_user = make_user("kai", roles=("Crew",))
        kai = make_person("Kai Kurz", user=kai_user)
        case = service_cases.create_case(name="Spot flackert", customer=make_customer(), manager=paula, user=paula)
        service_cases.add_participant(case, kai, user=paula)
        message = chat.post_message(case, user=paula, text="", files=[upload(photo(300, 200))])
        address = f"/projects/{case.number}/chat/media/{message.attachments.get().pk}/"
        self.assertEqual(self.browser_of(kai_user).get(address).status_code, 200)
        self.assertEqual(self.browser_of(self.crew_user).get(address).status_code, 404)

    def test_deleting_the_message_deletes_its_files(self) -> None:
        files = [self.stored(self.attachment.file.name), self.stored(self.attachment.thumbnail.name)]
        self.assertTrue(all(path.is_file() for path in files))
        with self.captureOnCommitCallbacks(execute=True):
            chat.delete_message(self.message, user=self.manager)
        self.assertFalse(any(path.exists() for path in files))
        self.assertFalse(ChatAttachment.objects.exists())

    def test_deleting_the_project_deletes_them_and_a_waiting_video(self) -> None:
        with (
            self.settings(JOBS_RUN_INLINE=False),
            mock.patch.object(media.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"),
            mock.patch.object(media.subprocess, "run", side_effect=FakeFfmpeg()),
            self.captureOnCommitCallbacks(execute=False),
        ):
            chat.post_message(self.project, user=self.manager, text="", files=[upload(CLIP, "a.mp4", "video/mp4")])
        self.assertEqual(len(self.waiting()), 1)
        files = [self.stored(self.attachment.file.name), self.stored(self.attachment.thumbnail.name)]
        with self.captureOnCommitCallbacks(execute=True):
            self.project.delete()
        self.assertFalse(any(path.exists() for path in files))
        self.assertEqual(self.waiting(), [])

    def test_the_backup_holds_them(self) -> None:
        # The files lie below MEDIA_ROOT, which the backup takes as a whole (deploy/backup.sh, core.backup).
        self.assertTrue(self.stored(self.attachment.file.name).is_relative_to(self.media_root / "chat"))


class NotificationTests(ChatScene, RentalarsTestCase):
    """A notification about a message names what it carries – instead of the text when there is none."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()

    def test_the_body(self) -> None:
        empty = ChatMessage(project=self.project, text="")
        self.assertEqual(written_for(chat.notification_body(empty, 1, 0), self.crew_user), "1 Foto")
        self.assertEqual(written_for(chat.notification_body(empty, 0, 1), self.crew_user), "1 Video")
        with_text = ChatMessage(project=self.project, text="Aufbau fertig")
        self.assertEqual(
            written_for(chat.notification_body(with_text, 2, 1), self.crew_user), "Aufbau fertig\n(2 Fotos, 1 Video)"
        )
        self.assertEqual(chat.notification_body(with_text), "Aufbau fertig")

    def test_a_mention_with_a_photo(self) -> None:
        chat.post_message(self.project, user=self.manager, text="@Anna Becker", files=[upload(photo(200, 100))])
        notice = Notification.objects.get(user=self.crew_user, kind=Kind.CHAT_MENTION)
        self.assertEqual(notice.body, "@Anna Becker\n(1 Foto)")

    def test_a_message_of_photos_only_may_lose_its_text_later(self) -> None:
        message = chat.post_message(self.project, user=self.manager, text="Bild", files=[upload(photo(200, 100))])
        chat.edit_message(message, user=self.manager, text="")
        self.assertEqual(message.text, "")
        plain = chat.post_message(self.project, user=self.manager, text="Nur Text")
        with self.assertRaises(ValidationError):
            chat.edit_message(plain, user=self.manager, text=" ")


# --- The page ----------------------------------------------------------------------------------------------------


class ChatMediaPageTests(ChatScene, UiTestCase):
    """The form takes photos and videos – on a phone also from the camera; the chat shows them inline."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()

    def test_the_form(self) -> None:
        text = self.assert_ok(self.client.get(self.url))
        self.assertIn('enctype="multipart/form-data"', text)
        self.assertIn('hx-encoding="multipart/form-data"', text)
        self.assertIn('<input id="chat-files" type="file" name="files" accept="image/*,video/*" multiple', text)
        self.assertIn('accept="image/*,video/*" capture="environment"', text)
        self.assertIn("Fotos oder Videos anhängen", text)
        self.assertIn("Foto oder Video aufnehmen", text)
        self.assertIn(
            "Fotos bis 25 MB, Videos bis 200 MB. Der Server verkleinert sie: Fotos auf 2048 Pixel ohne "
            "Standortdaten, Videos auf 720p.",
            text,
        )
        self.assertIn('data-max-video-mb="200"', text)
        with mock.patch.object(media.shutil, "which", return_value=None):
            text = self.assert_ok(self.client.get(self.url))
        self.assertIn("Videos gehen gerade nicht: Auf dem Server fehlt ffmpeg.", text)

    def test_send_a_photo_without_text_and_see_it(self) -> None:
        response = self.client.post(self.url, {"text": "", "files": [upload(photo(1600, 1200))]})
        message = ChatMessage.objects.get()
        self.assertRedirects(response, f"{self.url}#m{message.pk}", fetch_redirect_response=False)
        attachment = message.attachments.get()
        text = self.assert_ok(self.client.get(self.url))
        self.assertIn(
            f'<a href="{self.url}media/{attachment.pk}/" target="_blank" rel="noopener">'
            f'<img src="{self.url}media/{attachment.pk}/small/" alt="Foto – öffnet in voller Größe" '
            'width="1600" height="1200" loading="lazy"></a>',
            text,
        )
        self.assertNotIn('<div class="bubble-text">', text)
        # With htmx, the list comes back and the field is emptied.
        response = self.htmx("post", self.url, {"text": "Noch eins", "files": [upload(photo(300, 300), "b.png")]})
        self.assertEqual(response["HX-Trigger"], "chatSent")
        self.assertEqual(ChatAttachment.objects.count(), 2)

    def test_a_refused_file_is_named(self) -> None:
        response = self.htmx("post", self.url, {"text": "Hier", "files": [upload(b"MZ\x90\x00", "virus.jpg")]})
        self.assertNotIn("HX-Trigger", response)
        text = self.assert_ok(response)
        self.assertIn('role="alert"', text)
        self.assertIn("„virus.jpg“: Das ist weder ein Foto noch ein Video.", text)
        self.assertFalse(ChatMessage.objects.exists())
        text = self.assert_ok(self.client.post(self.url, {"text": "", "files": [upload(b"x", "a.jpg")]}))
        self.assertIn('<p class="note red" role="alert" data-chat-file-error>„a.jpg“', text)

    def test_videos_while_processing_ready_and_failed(self) -> None:
        message = ChatMessage.objects.create(project=self.project, author=self.crew_user, author_name="Anna", text="")
        waiting = ChatAttachment.objects.create(message=message, kind="video", state="processing")
        failed = ChatAttachment.objects.create(message=message, kind="video", state="failed", failure="timeout")
        ready = ChatAttachment.objects.create(
            message=message, kind="video", file="chat/1/x.mp4", thumbnail="chat/1/x.jpg", width=1280, height=720
        )
        text = self.assert_ok(self.client.get(self.url))
        self.assertIn("Video wird verkleinert …", text)
        self.assertIn("Das Verkleinern des Videos hat zu lange gedauert; es wurde verworfen.", text)
        self.assertIn(
            f'<video controls preload="metadata" playsinline width="1280" height="720" '
            f'poster="{self.url}media/{ready.pk}/small/" aria-label="Video">',
            text,
        )
        self.assertIn(f'<source src="{self.url}media/{ready.pk}/" type="video/mp4">', text)
        # Not ready: no file to fetch.
        self.assertEqual(self.client.get(f"{self.url}media/{waiting.pk}/").status_code, 404)
        self.assertEqual(self.client.get(f"{self.url}media/{failed.pk}/").status_code, 404)


# --- The API ------------------------------------------------------------------------------------------------------


class ChatMediaApiTests(ChatScene, ApiTestCase):
    """API-002/API-014: messages with attachments; multipart with files; the files and their previews."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        self.chat_url = f"{API}/projects/{self.project.pk}/chat"

    def test_write_with_photos_and_read_them(self) -> None:
        crew = self.client_of(self.crew_user)
        response = crew.post(
            self.chat_url,
            {"text": "", "files": [upload(photo(3000, 2000)), upload(photo(500, 400), "b.jpg")]},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual(data["text"], "")
        first, second = data["attachments"]
        self.assertEqual(
            {key: first[key] for key in ("kind", "state", "width", "height", "duration", "name", "failure")},
            {
                "kind": "photo",
                "state": "ready",
                "width": 2048,
                "height": 1365,
                "duration": None,
                "name": "IMG_0001.jpg",
                "failure": "",
            },
        )
        self.assertEqual(first["url"], f"{self.chat_url}/media/{first['id']}")
        self.assertEqual(first["thumbnail_url"], f"{self.chat_url}/media/{first['id']}/thumbnail")
        self.assertEqual(second["name"], "b.jpg")
        listed = crew.get(self.chat_url).json()
        self.assertEqual([item["id"] for item in listed[0]["attachments"]], [first["id"], second["id"]])
        self.assertEqual(crew.get(f"{self.chat_url}/{data['id']}").json()["attachments"][0]["id"], first["id"])
        content = crew.get(first["url"])
        self.assertEqual((content.status_code, content["Content-Type"]), (200, "image/jpeg"))
        thumbnail = crew.get(first["thumbnail_url"])
        with Image.open(io.BytesIO(b"".join(thumbnail.streaming_content))) as image:
            self.assertEqual(image.size, (640, 427))
        outsider = self.client_of(self.outsider)
        self.assertEqual(outsider.get(first["url"]).status_code, 404)
        self.assertEqual(outsider.get(first["thumbnail_url"]).status_code, 404)

    def test_refused_files_and_a_video_in_the_works(self) -> None:
        refused = self.admin.post(
            self.chat_url, {"text": "x", "files": [upload(b"<svg/>", "bild.jpg")]}, format="multipart"
        )
        self.assert_error(refused, 400, "validation_error", "files")
        self.assertFalse(ChatMessage.objects.exists())
        with (
            self.settings(JOBS_RUN_INLINE=False),
            mock.patch.object(media.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"),
            mock.patch.object(media.subprocess, "run", side_effect=FakeFfmpeg()),
            self.captureOnCommitCallbacks(execute=False),
        ):
            response = self.admin.post(
                self.chat_url, {"files": [upload(CLIP, "VID.mp4", "video/mp4")]}, format="multipart"
            )
        (attachment,) = response.json()["attachments"]
        self.assertEqual(
            (attachment["kind"], attachment["state"], attachment["url"], attachment["thumbnail_url"]),
            ("video", "processing", None, None),
        )
        self.assertEqual(attachment["duration"], 2.0)
        self.assertEqual(self.admin.get(f"{self.chat_url}/media/{attachment['id']}").status_code, 404)
        # A read-only token reads, but does not write (AUT-021).
        reader = self.client_of(self.crew_user, read_only=True)
        self.assertEqual(
            reader.post(self.chat_url, {"files": [upload(photo(10, 10))]}, format="multipart").status_code, 403
        )

    def test_the_schema_names_the_attachments(self) -> None:
        schema = self.admin.get(f"{API}/schema", {"format": "json"}).json()
        properties = schema["components"]["schemas"]["ChatMessage"]["properties"]
        self.assertIn("attachments", properties)
        attachment = schema["components"]["schemas"]["ChatAttachment"]["properties"]
        for name in ("kind", "state", "url", "thumbnail_url", "width", "height", "duration"):
            self.assertIn(name, attachment)
        self.assertTrue(any("/chat/media/" in path for path in schema["paths"]))
