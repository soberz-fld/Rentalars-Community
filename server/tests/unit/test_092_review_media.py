# SPDX-License-Identifier: GPL-3.0-or-later
"""Review: custom fields, chat photos and videos, to-dos through the API (MAT-071, MAT-070, UIX-049, NFA-076, API-002).

Findings of the review, each with the test that failed before the fix:

* H2 (MAT-071): a custom field marked "only with the right to see purchase
  prices" after items had values – the history of the item (page and
  ``GET /material-items/{id}/history``) and the system-wide change log no
  longer show the old values to readers without that right; the entries
  that only moved a value to the protected column are shown to nobody.
* M6 (MAT-071): check patterns that can backtrack for minutes (ReDoS) are
  refused when saved – nested repetitions, alternatives in an open-ended
  repetition, back-references, more than 200 characters; a value is matched
  only up to 4000 characters and at most half a second ("Prüfmuster zu
  aufwendig"); a pattern stored before keeps working.
* L10 (MAT-071): a web address of a custom field is a link only with
  ``http``/``https``, an e-mail address only when it is one.
* M3 (UIX-049): a chat photo is checked by its size in bytes and pixels
  before it is decoded – PNG, GIF and WebP up to 16 megapixels; a JPEG is
  decoded at the smallest scale that keeps 2048 pixels on its long side.
* M4 (UIX-049, NFA-076): one chat video is converted at a time on a server;
  the others wait in line, nothing is lost when the converting process
  dies; a video larger than 4096 × 4096 pixels or with too many frames is
  refused, and the longer of stream and container decides the length.
  Videos left waiting by a crash go with the daily maintenance after two
  days, not only with the next upload.
* L11 (MAT-070, API-002): ``POST /material-todos/done`` ticks several to-dos
  done at once, as the page "Material mit To-Do" does.
"""

from __future__ import annotations

import io
import json
import os
import signal
import socket
import struct
import subprocess
import threading
import time
import zlib
from pathlib import Path
from typing import Any
from unittest import mock, skipUnless

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from PIL import Image, ImageFile
from PIL.JpegImagePlugin import JpegImageFile

from rentalars.accounts.rights import Level, Module, Rights, rights_of
from rentalars.chat import media
from rentalars.chat import services as chat
from rentalars.chat.models import AttachmentState, ChatAttachment, ChatMessage
from rentalars.core import jobs
from rentalars.core.models import BackgroundJob, JobStatus
from rentalars.customfields import patterns, services
from rentalars.customfields.models import CustomField, CustomFieldValue, FieldType, ModelFieldset
from rentalars.customfields.tables import value_html
from rentalars.material import audits
from rentalars.material.audit_models import ItemTodo
from rentalars.material.history import item_history
from tests.api.base import API, ApiTestCase
from tests.helpers import RentalarsTestCase, at, make_item, make_model, set_clock
from tests.ui.base import UiTestCase
from tests.unit.test_092_chat_media import (
    CLIP,
    HAS_FFMPEG,
    NO_FFMPEG,
    ChatScene,
    FakeFfmpeg,
    FilesMixin,
    photo,
    upload,
)
from tests.unit.test_092_customfields import make_field, make_fieldset, role, user_with

SECRET = "SECRET-1234"


# --- H2: custom fields made sensitive later ----------------------------------------------------------------


class SensitiveLaterMixin:
    """An item with a value in the field "PIN", which the administration marks sensitive afterwards."""

    def build_vault(self) -> None:
        self.reader = user_with("lager", role("Lager ohne EK", {Module.MATERIAL: Level.WRITE}))
        self.field = make_field("PIN")
        model = make_model("Tresor")
        ModelFieldset.objects.create(material_model=model, fieldset=make_fieldset("Tresor", self.field))
        self.item = make_item(model, 4711)
        services.store_values(self.item, {self.field: "OLD-0000"})
        services.store_values(self.item, {self.field: SECRET})
        self.mark_sensitive(self.field)

    @staticmethod
    def mark_sensitive(field: CustomField) -> CustomField:
        field = CustomField.objects.get(pk=field.pk)
        field.is_sensitive = True
        field.full_clean()
        field.save()
        return field

    @staticmethod
    def shown(rows: list[Any]) -> str:
        return str([(row.summary, [(change.old, change.new) for change in row.changes]) for row in rows])


class SensitiveLaterHistoryTests(SensitiveLaterMixin, ApiTestCase):
    """The history decides by the field's mark now, not by the column an entry names."""

    def setUp(self) -> None:
        super().setUp()
        self.build_vault()

    def test_the_item_history_hides_the_old_values(self) -> None:
        rows = [row for row in item_history(self.item, rights_of(self.reader)) if "PIN" in row.summary]
        self.assertNotIn(SECRET, self.shown(rows))
        self.assertNotIn("OLD-0000", self.shown(rows))
        # Filled in, then changed – the entry that only moved the value to the protected column is not shown.
        self.assertEqual(
            [(row.summary, [(change.old, change.new) for change in row.changes]) for row in rows],
            [
                ("Eigenes Feld „PIN“ geändert", [("…", "(nicht sichtbar)")]),
                ("Eigenes Feld „PIN“ eingetragen", [("–", "(nicht sichtbar)")]),
            ],
        )
        # Who may see purchase prices sees the values – and no "change" for the moved column either.
        everything = [row for row in item_history(self.item, Rights.everything()) if "PIN" in row.summary]
        self.assertEqual(len(everything), 2)
        self.assertIn(SECRET, self.shown(everything))

    def test_the_api_history_hides_them(self) -> None:
        url = f"{API}/material-items/{self.item.pk}/history"
        reader = self.client_of(self.reader).get(url)
        self.assertEqual(reader.status_code, 200)
        self.assertNotIn(SECRET, reader.content.decode())
        self.assertNotIn("OLD-0000", reader.content.decode())
        self.assertIn(SECRET, self.admin.get(url).content.decode())

    def test_the_system_change_log_hides_them(self) -> None:
        clerk = user_with("verwaltung", role("Verwaltung ohne EK", {Module.ADMINISTRATION: Level.READ}))
        url = f"{API}/audit-log"
        body = self.client_of(clerk).get(url, {"object_type": "customfields.customfieldvalue"}).content.decode()
        self.assertNotIn(SECRET, body)
        self.assertNotIn("OLD-0000", body)
        self.assertIn(SECRET, self.admin.get(url, {"object_type": "customfields.customfieldvalue"}).content.decode())

    def test_values_of_a_deleted_field_that_was_sensitive(self) -> None:
        plain = make_field("Firmware")
        fieldset = self.item.material_model.custom_fieldset.fieldset
        fieldset.entries.create(field=plain, position=2)
        services.store_values(self.item, {plain: "1.2"})
        services.delete_field(CustomField.objects.get(pk=self.field.pk), with_values=True)
        services.delete_field(plain, with_values=True)
        rows = item_history(self.item, rights_of(self.reader))
        self.assertNotIn(SECRET, self.shown(rows))
        self.assertNotIn("OLD-0000", self.shown(rows))
        # A field that never was sensitive is not hidden after it is gone.
        self.assertIn("1.2", self.shown(rows))


class SensitiveLaterPageTests(SensitiveLaterMixin, UiTestCase):
    """The pages: the history of the item and Einstellungen → Änderungsprotokoll."""

    def setUp(self) -> None:
        super().setUp()
        self.build_vault()

    def test_the_history_page_of_the_item(self) -> None:
        page = self.assert_ok(self.browser_of(self.reader).get(reverse("material:item_history", args=[self.item.pk])))
        self.assertIn("Eigenes Feld „PIN“ eingetragen", page)
        self.assertNotIn(SECRET, page)
        self.assertNotIn("OLD-0000", page)

    def test_the_system_change_log_page(self) -> None:
        clerk = user_with("verwaltung", role("Verwaltung ohne EK", {Module.ADMINISTRATION: Level.READ}))
        page = self.assert_ok(self.browser_of(clerk).get(reverse("core:audit_log")))
        self.assertIn("geändert (Einzelheiten nicht sichtbar)", page)
        self.assertNotIn(SECRET, page)
        self.assertNotIn("OLD-0000", page)
        self.assertIn(SECRET, self.assert_ok(self.client.get(reverse("core:audit_log"))))


# --- M6: check patterns without catastrophic backtracking ---------------------------------------------------


class PatternTests(RentalarsTestCase):
    """Refused when saved; matched within limits; a pattern stored before keeps working."""

    def refused(self, pattern: str) -> list[str]:
        started = time.monotonic()
        with self.assertRaises(ValidationError) as caught:
            make_field("Kennung", pattern=pattern)
        self.assertLess(time.monotonic() - started, 1, "refused without trying the pattern")
        return caught.exception.message_dict["pattern"]

    def test_patterns_that_can_backtrack_for_minutes_are_refused(self) -> None:
        for pattern in (r"(a+)+", r"(.*,){5}", r"(a?){25}a{25}", r"(x+x+)+y", r"([a-z]+-)*[a-z]+"):
            self.assertEqual(len(self.refused(pattern)), 1, pattern)
            self.assertTrue(
                self.refused(pattern)[0].startswith("Verschachtelte Wiederholungen wie (a+)+ oder (.*,){5} sind "),
                pattern,
            )
        self.assertIn("Die Wiederholung ausschreiben", self.refused(r"(a+)+")[0])
        self.assertTrue(self.refused(r"(ab|a)+")[0].startswith("Alternativen in einer offenen Wiederholung"))
        self.assertEqual(
            self.refused(r"(a)\1"), [r"Rückverweise wie \1 oder (?P=name) sind in einem Prüfmuster nicht erlaubt."]
        )
        self.assertEqual(self.refused("a" * 201), ["Ein Prüfmuster darf höchstens 200 Zeichen haben."])
        self.assertIn("kein gültiger regulärer Ausdruck", self.refused("[a-")[0])

    def test_useful_patterns_stay_allowed(self) -> None:
        for pattern in (
            r"[0-9A-F]{2}(:[0-9A-F]{2}){5}",  # the example of the help text: a fixed count inside
            r"(\d{1,3}\.){3}\d{1,3}",  # a small bounded nesting
            r"[A-Z]{2}-\d+",
            r"(ab)+",
            r"(a|b)+",  # one character each: a character class
            r"^\S+@\S+\.\S+$",
        ):
            self.assertEqual(patterns.pattern_problems(pattern), [], pattern)

    def test_a_slow_pattern_stored_before_is_stopped(self) -> None:
        field = make_field("Seriennummer")
        CustomField.objects.filter(pk=field.pk).update(pattern=r"(a+)+")  # stored before the check
        field.refresh_from_db()
        self.assertEqual(field.clean_value("aaaa"), "aaaa", "it keeps working")
        handler = signal.getsignal(signal.SIGALRM)
        started = time.monotonic()
        with self.assertRaises(ValidationError) as caught:
            field.clean_value("a" * 40 + "!")  # minutes – or longer – without the time limit
        self.assertLess(time.monotonic() - started, 3)
        self.assertEqual(
            caught.exception.messages,
            [
                "Prüfmuster zu aufwendig: Das Prüfen des Werts im Feld Seriennummer hat zu lange gedauert. Bitte das "
                "Prüfmuster unter Einstellungen → Eigene Felder vereinfachen."
            ],
        )
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0), "no timer is left running")
        self.assertIs(signal.getsignal(signal.SIGALRM), handler, "the handler is put back")
        # Edited, the definition must get a pattern that is allowed.
        field.help_text = "Neu"
        with self.assertRaises(ValidationError) as edited:
            field.full_clean()
        self.assertIn("pattern", edited.exception.message_dict)

    def test_checking_the_stored_values_stops_at_the_first_slow_one(self) -> None:
        field = make_field("Notiz lang", FieldType.LONG_TEXT)
        model = make_model("Kiste")
        for number in (1, 2, 3):
            CustomFieldValue.objects.create(item=make_item(model, number), field=field, value="ab" * 2000)
        field.pattern = r".*a.*b.*c"  # allowed, but cubic: about 4 seconds for each of these values
        started = time.monotonic()
        with self.assertRaises(ValidationError) as caught:
            field.full_clean()
        self.assertLess(time.monotonic() - started, 3, "half a second, not 12 – one value is enough")
        self.assertEqual(len(caught.exception.message_dict["pattern"]), 1)
        self.assertTrue(caught.exception.message_dict["pattern"][0].startswith("Prüfmuster zu aufwendig"))

    def test_values_are_matched_up_to_4000_characters(self) -> None:
        field = make_field("Zahl", FieldType.NUMBER, pattern=r"\d+")
        self.assertEqual(field.clean_value("1" * 40), "1" * 40)
        with self.assertRaises(ValidationError) as caught:
            field.clean_value("1" * 5000)
        self.assertEqual(caught.exception.messages, ["Der Wert des Feldes Zahl darf höchstens 4000 Zeichen haben."])

    def test_outside_the_main_thread_without_the_timer(self) -> None:
        field = make_field("Typ", pattern=r"[A-Z]{2}-\d+")
        results: list[Any] = []
        with mock.patch.object(patterns.signal, "setitimer", side_effect=AssertionError("no timer in a thread")):
            worker = threading.Thread(target=lambda: results.append(field.clean_value("AB-12")))
            worker.start()
            worker.join(10)
        self.assertEqual(results, ["AB-12"])


# --- L10: links only with a safe scheme --------------------------------------------------------------------


class LinkTests(UiTestCase):
    """A web address is a link only with http/https; anything else is plain text."""

    def setUp(self) -> None:
        super().setUp()
        self.url = make_field("Handbuch", FieldType.URL)
        self.mail = make_field("Support", FieldType.EMAIL)
        model = make_model("Pult")
        ModelFieldset.objects.create(material_model=model, fieldset=make_fieldset("Pult", self.url, self.mail))
        self.item = make_item(model, 77)

    def test_value_html(self) -> None:
        self.assertEqual(
            str(value_html(self.url, "https://example.com/a.pdf")),
            '<a href="https://example.com/a.pdf" rel="noopener noreferrer" target="_blank">https://example.com/a.pdf</a>',
        )
        for bad in (
            "javascript:alert(1)",
            "java\tscript:alert(1)",
            " JavaScript:alert(1)",
            "data:text/html,x",
            "https:x",
        ):
            self.assertNotIn("<a", str(value_html(self.url, bad)), repr(bad))
        self.assertEqual(
            str(value_html(self.mail, "support@example.com")),
            '<a href="mailto:support@example.com">support@example.com</a>',
        )
        self.assertEqual(str(value_html(self.mail, "javascript:alert(1)")), "javascript:alert(1)")

    def test_the_item_page(self) -> None:
        # Stored without the checks of today – by an older version or by hand in the database.
        CustomFieldValue.objects.create(item=self.item, field=self.url, value="javascript:alert(document.cookie)")
        CustomFieldValue.objects.create(item=self.item, field=self.mail, value="<b>x</b>@example.com")
        page = self.assert_ok(self.client.get(reverse("material:item_detail", args=[self.item.pk])))
        self.assertIn("javascript:alert(document.cookie)", page)
        self.assertNotIn('href="javascript:', page)
        self.assertNotIn('href="mailto:', page)
        self.assertNotIn("<b>x</b>", page)


# --- M3: chat photos checked before they are decoded ---------------------------------------------------------


def png_of(width: int, height: int) -> bytes:
    """A palette PNG of ``width`` × ``height`` black pixels: a few KB that decode to width × height bytes."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    compressor = zlib.compressobj(9)
    row = b"\x00" * (width + 1)
    data = b"".join(compressor.compress(row) for _row in range(height)) + compressor.flush()
    header = struct.pack(">IIBBBBB", width, height, 8, 3, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"PLTE", b"\x00\x00\x00")
        + chunk(b"IDAT", data)
        + chunk(b"IEND", b"")
    )


def jpeg_claiming(width: int, height: int) -> bytes:
    """A small JPEG whose header claims ``width`` × ``height`` pixels."""
    stored = io.BytesIO()
    Image.new("RGB", (16, 16)).save(stored, "JPEG")
    data = bytearray(stored.getvalue())
    start = data.index(b"\xff\xc0")
    data[start + 5 : start + 9] = struct.pack(">HH", height, width)
    return bytes(data)


def peak_rss_reset() -> bool:
    """Reset the peak memory of this process (Linux); ``False`` where that is not possible."""
    try:
        Path("/proc/self/clear_refs").write_text("5")
    except OSError:
        return False
    return True


def peak_rss_mb() -> int:
    """The peak memory of this process since the last reset, in MB."""
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmHWM:"):
            return int(line.split()[1]) // 1024
    return 0


class PhotoBombTests(FilesMixin, RentalarsTestCase):
    """Bytes and pixels are checked before anything is decoded; JPEGs are decoded small."""

    def refused(self, content: bytes, name: str = "bild.png") -> str:
        with self.assertRaises(ValidationError) as caught:
            media.prepare_files([upload(content, name, "image/png")])
        return " ".join(caught.exception.message_dict["files"])

    def test_a_small_png_with_huge_dimensions_is_refused_without_decoding(self) -> None:
        bomb = png_of(7070, 7070)  # the review's sample: 50 megapixels in a few KB, 593 MB when decoded
        self.assertLess(len(bomb), 100_000)
        measured = peak_rss_reset()
        before = peak_rss_mb()
        started = time.monotonic()
        with mock.patch.object(ImageFile.ImageFile, "load", side_effect=AssertionError("decoded")):
            text = self.refused(bomb)
        self.assertLess(time.monotonic() - started, 1)
        self.assertEqual(
            text,
            "„bild.png“: Das Foto hat zu viele Pixel: höchstens 16 Megapixel als PNG, GIF oder WebP. Größere Fotos "
            "bitte als JPEG senden.",
        )
        if measured:
            self.assertLess(peak_rss_mb() - before, 30, "nothing decoded")

    def test_limits_by_format(self) -> None:
        self.assertIn("höchstens 16 Megapixel", self.refused(png_of(5000, 3300)))
        self.assertEqual(
            self.refused(jpeg_claiming(13000, 12000), "riesig.jpg"),
            "„riesig.jpg“: Das Foto hat zu viele Pixel: höchstens 150 Megapixel.",
        )
        # Beyond Pillow's own limit (twice MAX_IMAGE_PIXELS) it refuses on its own.
        self.assertEqual(
            self.refused(jpeg_claiming(65000, 65000), "riesig.jpg"), "„riesig.jpg“: Das Foto hat zu viele Pixel."
        )

    def test_the_size_in_bytes_comes_first(self) -> None:
        with (
            mock.patch.object(media, "MAX_PHOTO_BYTES", 1000),
            mock.patch.object(Image, "open", side_effect=AssertionError("opened")),
        ):
            self.assertEqual(self.refused(photo(400, 300), "a.jpg"), "„a.jpg“: Das Foto ist zu groß (höchstens 0 MB).")

    def test_a_panorama_jpeg_is_decoded_at_a_fraction(self) -> None:
        decoded: list[tuple[int, int]] = []
        draft = JpegImageFile.draft

        def noting(image: JpegImageFile, mode: str, size: tuple[int, int]) -> Any:
            result = draft(image, mode, size)
            decoded.append(image.size)
            return result

        with mock.patch.object(JpegImageFile, "draft", noting):
            (prepared,) = media.prepare_files([upload(photo(4200, 1000), "pano.jpg")])
        # Half the size still has 2048 pixels on the long side; before, the short side kept it at full size.
        self.assertEqual(decoded, [(2100, 500)])
        self.assertEqual(prepared.width, 2048)
        self.assertIn(prepared.height, (487, 488))

    def test_draft_size(self) -> None:
        self.assertEqual(media.draft_size(4000, 3000), (2048, 1536))
        self.assertEqual(media.draft_size(8192, 6144), (2048, 1536))
        self.assertEqual(media.draft_size(1000, 5000), (409, 2048))
        self.assertEqual(media.draft_size(800, 600), (800, 600))


# --- M4: one video at a time, streams checked ----------------------------------------------------------------


class SlotNotingFfmpeg(FakeFfmpeg):
    """The fake ffmpeg, noting during each conversion whether another process could get the slot."""

    def __init__(self, **options: Any) -> None:
        super().__init__(**options)
        self.slot_free_while_converting: list[bool] = []

    def __call__(self, command: list[str], **options: Any) -> subprocess.CompletedProcess[bytes]:
        if "libx264" in command:
            with media.conversion_slot() as free:
                self.slot_free_while_converting.append(free)
        return super().__call__(command, **options)


class ProbingFfmpeg(FakeFfmpeg):
    """The fake ffmpeg whose ffprobe tells what the test wants."""

    def __init__(self, video: dict[str, Any], duration: str = "2.000") -> None:
        super().__init__()
        self.video, self.duration = video, duration

    def __call__(self, command: list[str], **options: Any) -> subprocess.CompletedProcess[bytes]:
        if Path(next(part for part in command if "ff" in Path(part).name)).name == "ffprobe":
            answer = {"format": {"duration": self.duration}, "streams": [{"codec_type": "video", **self.video}]}
            return subprocess.CompletedProcess(command, 0, json.dumps(answer).encode(), b"")
        return super().__call__(command, **options)


def echo_job(job: BackgroundJob) -> str:
    """A task of another kind, for :meth:`VideoQueueTests.test_other_kinds_of_tasks_do_not_wait`."""
    return "echo"


class VideoQueueTests(ChatScene, RentalarsTestCase):
    """At most one conversion at a time; the holder of the slot takes the waiting ones; nothing gets lost."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()

    def fakes(self, fake: FakeFfmpeg) -> None:
        """ffmpeg and ffprobe replaced by ``fake`` for the rest of the test."""
        for patch in (
            mock.patch.object(media.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"),
            mock.patch.object(media.subprocess, "run", side_effect=fake),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def post(self, name: str = "VID.mp4") -> ChatMessage:
        return chat.post_message(self.project, user=self.crew_user, text="", files=[upload(CLIP, name, "video/mp4")])

    def post_waiting(self, *names: str) -> list[ChatMessage]:
        """Post videos whose tasks are only stored – their processes did not start yet."""
        with self.settings(JOBS_RUN_INLINE=False), self.captureOnCommitCallbacks(execute=False):
            return [self.post(name) for name in names]

    def state_of(self, message: ChatMessage) -> str:
        return message.attachments.get().state

    def test_a_second_video_waits_while_one_is_converted(self) -> None:
        fake = SlotNotingFfmpeg()
        self.fakes(fake)
        with media.conversion_slot() as got:  # another process converts a video right now
            self.assertTrue(got)
            message = self.post()  # its task runs at once here – and finds the slot taken
            job = BackgroundJob.objects.get(kind="chat_video")
            self.assertEqual((job.status, job.started_at), (JobStatus.QUEUED, None))
            self.assertEqual(self.state_of(message), AttachmentState.PROCESSING)
            self.assertFalse(any("libx264" in command for command, _options in fake.calls))
        # The slot is free again: the timer runs what waits.
        self.assertEqual(jobs.run_waiting_jobs(), 1)
        self.assertEqual(self.state_of(message), AttachmentState.READY)
        self.assertEqual(fake.slot_free_while_converting, [False])
        convert = next(command for command, _options in fake.calls if "libx264" in command)
        self.assertEqual(convert[convert.index("-t") + 1], str(media.MAX_VIDEO_SECONDS))

    def test_the_holder_converts_the_waiting_ones_one_after_the_other(self) -> None:
        fake = SlotNotingFfmpeg()
        self.fakes(fake)
        messages = self.post_waiting("a.mp4", "b.mp4", "c.mp4")
        waiting = [message.attachments.get().source for message in messages]
        tasks = list(BackgroundJob.objects.filter(kind="chat_video").order_by("pk"))
        self.assertEqual(len(tasks), 3)
        # The process started for the first video ("run_jobs --job N") takes the others, too – in their order.
        self.assertEqual(jobs.run_job(tasks[0].pk).pk, tasks[0].pk)
        self.assertEqual([self.state_of(message) for message in messages], [AttachmentState.READY] * 3)
        self.assertEqual(set(BackgroundJob.objects.values_list("status", flat=True)), {JobStatus.DONE})
        self.assertEqual(fake.slot_free_while_converting, [False, False, False], "never two at once")
        converted = [Path(command[command.index("-i") + 1]).name for command, _o in fake.calls if "libx264" in command]
        self.assertEqual(converted, waiting)
        # The processes started for the others find nothing to do.
        self.assertIsNone(jobs.run_job(tasks[1].pk))

    def test_nothing_is_lost_when_the_converting_process_dies(self) -> None:
        fake = FakeFfmpeg()
        self.fakes(fake)
        first, second = self.post_waiting("a.mp4", "b.mp4")
        task = BackgroundJob.objects.filter(kind="chat_video").order_by("pk").first()
        # The process converting the first video died (the kernel let go of its lock): its task is "running".
        dead = subprocess.Popen(["true"])  # a process that is gone at once
        dead.wait()
        BackgroundJob.objects.filter(pk=task.pk).update(
            status=JobStatus.RUNNING,
            started_at=timezone.now(),
            params={**task.params, "worker": {"host": socket.gethostname(), "pid": dead.pid}},
        )
        # The timer starts the interrupted task again and runs the waiting one.
        jobs.run_waiting_jobs()
        self.assertEqual([self.state_of(first), self.state_of(second)], [AttachmentState.READY] * 2)

    def test_other_kinds_of_tasks_do_not_wait(self) -> None:
        jobs.register("review_echo", f"{__name__}:echo_job")
        self.addCleanup(jobs._RUNNERS.pop, "review_echo", None)
        with media.conversion_slot() as got:
            self.assertTrue(got)
            job = jobs.start_job("review_echo", {}, user=None, title="Echo")
        self.assertEqual((job.status, job.message), (JobStatus.DONE, "echo"))

    def test_a_video_waiting_in_line_is_not_lost_after_three_hours(self) -> None:
        self.fakes(FakeFfmpeg())
        (message,) = self.post_waiting("a.mp4")
        set_clock(at(1, 11, 30))
        chat.messages_of(self.project)
        self.assertEqual(self.state_of(message), AttachmentState.PROCESSING)
        set_clock(at(2, 8, 30))  # a day in line: lost after all (the timer is off)
        chat.messages_of(self.project)
        attachment = message.attachments.get()
        self.assertEqual((attachment.state, attachment.failure), (AttachmentState.FAILED, "interrupted"))


class VideoStreamTests(ChatScene, RentalarsTestCase):
    """What the picture stream says is checked before the video is accepted."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()

    def check(self, video: dict[str, Any], duration: str = "2.000") -> str:
        """The refusal of a video whose ffprobe says this; empty if it is accepted."""
        with (
            mock.patch.object(media.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"),
            mock.patch.object(media.subprocess, "run", side_effect=ProbingFfmpeg(video, duration)),
        ):
            try:
                prepared = media.prepare_files([upload(CLIP, "VID.mp4", "video/mp4")])
            except ValidationError as error:
                return " ".join(error.message_dict["files"])
        media.discard(prepared)
        return ""

    def test_the_picture_and_the_frames(self) -> None:
        phone = {"width": 3840, "height": 2160, "avg_frame_rate": "60/1", "duration": "120.0", "nb_frames": "7200"}
        self.assertEqual(self.check(phone, "120.0"), "")
        self.assertEqual(self.check({**phone, "width": 1080, "height": 1920, "avg_frame_rate": "240/1"}, "120.0"), "")
        self.assertEqual(
            self.check({**phone, "width": 8192, "height": 4320}, "120.0"),
            "„VID.mp4“: Das Bild des Videos ist zu groß: höchstens 4096 × 4096 Pixel.",
        )
        too_many = "„VID.mp4“: Das Video hat zu viele Einzelbilder: höchstens 20 Minuten bei 60 Bildern pro Sekunde."
        self.assertEqual(self.check({**phone, "avg_frame_rate": "1000/1", "nb_frames": "0"}, "10.0"), too_many)
        self.assertEqual(self.check({**phone, "nb_frames": "100000"}, "10.0"), too_many)
        self.assertEqual(self.check({**phone, "avg_frame_rate": "120/1", "nb_frames": "0"}, "1000.0"), too_many)

    def test_the_longer_of_stream_and_container(self) -> None:
        too_long = "„VID.mp4“: Das Video ist zu lang (höchstens 20 Minuten)."
        video = {"width": 1280, "height": 720, "avg_frame_rate": "1/1"}
        self.assertEqual(self.check({**video, "duration": "3600.0"}, "10.0"), too_long)
        self.assertEqual(self.check({**video, "tags": {"DURATION": "00:25:00.000000000"}}, "10.0"), too_long)
        self.assertEqual(self.check({**video, "tags": {"DURATION": "00:19:00.000000000"}}, "10.0"), "")

    @skipUnless(HAS_FFMPEG, NO_FFMPEG)
    def test_a_real_video_too_wide(self) -> None:
        wide = self.work / "breit.mp4"
        subprocess.run(  # a fixed list of arguments, ffmpeg of the test machine
            [
                "ffmpeg",
                "-nostdin",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc=size=4112x64:rate=5:duration=0.4",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                str(wide),
            ],
            check=True,
            timeout=120,
        )
        with self.assertRaises(ValidationError) as caught:
            media.prepare_files([upload(wide.read_bytes(), "breit.mp4", "video/mp4")])
        self.assertEqual(
            caught.exception.message_dict["files"],
            ["„breit.mp4“: Das Bild des Videos ist zu groß: höchstens 4096 × 4096 Pixel."],
        )
        self.assertEqual(self.waiting(), [])


class LeftoverVideoTests(ChatScene, RentalarsTestCase):
    """Waiting videos no attachment needs any more go with the daily maintenance after two days."""

    def test_the_daily_maintenance_removes_them(self) -> None:
        self.make_scene()
        folder = media.pending_directory()
        lost, waiting, fresh = (folder / f"{name * 24}.source" for name in "abc")
        for path in (lost, waiting, fresh):
            path.write_bytes(b"video")
        message = ChatMessage.objects.create(project=self.project, author=self.crew_user, text="")
        ChatAttachment.objects.create(message=message, kind="video", state="processing", source=waiting.name)
        past = time.time() - (media.PENDING_DAYS + 1) * 86400
        for path in (lost, waiting):
            os.utime(path, (past, past))
        output = io.StringIO()
        call_command("run_daily_maintenance", stdout=output)
        self.assertIn("Deleted 1 chat videos left waiting for their conversion.", output.getvalue())
        self.assertEqual(self.waiting(), sorted([waiting.name, fresh.name]))


# --- L11: several to-dos done through the API ---------------------------------------------------------------


class TodosDoneApiTests(ApiTestCase):
    """``POST /material-todos/done`` – the button of "Material mit To-Do" for programs."""

    def setUp(self) -> None:
        super().setUp()
        model = make_model("XLR-Kabel 10 m")
        self.cable, self.other = make_item(model, 428), make_item(model, 429)
        self.label = audits.add_todo(self.cable, "Label fehlt")
        self.velcro = audits.add_todo(self.cable, "Klett fehlt")
        self.clean = audits.add_todo(self.other, "Reinigen")
        self.done = audits.add_todo(self.other, "Stecker prüfen")
        audits.complete_todo(self.done)
        self.url = f"{API}/material-todos/done"

    def test_several_at_once(self) -> None:
        response = self.admin.post(
            self.url, {"todos": [self.label.pk, self.clean.pk, self.done.pk, 999999]}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {"done": 2, "already_done": 1, "not_found": [999999]})
        self.assertEqual(list(audits.open_todos()), [self.velcro])
        ticked = ItemTodo.objects.get(pk=self.label.pk)
        self.assertEqual((ticked.done_by, ticked.done_at), (self.admin_user, timezone.now()))
        again = self.admin.post(self.url, {"todos": [self.label.pk]}, format="json").json()
        self.assertEqual(again, {"done": 0, "already_done": 1, "not_found": []})

    def test_wrong_bodies(self) -> None:
        for body in ({}, {"todos": []}, {"todos": "12"}, {"todos": [True]}, {"todos": ["12"]}, {"todos": [1] * 2001}):
            self.assert_error(self.admin.post(self.url, body, format="json"), 400, "validation_error", "todos")
        self.assertEqual(len(audits.open_todos()), 3)

    def test_rights_as_on_the_page(self) -> None:
        reader = self.client_for("rita", "Nur-Lesen")
        self.assertEqual(reader.post(self.url, {"todos": [self.label.pk]}, format="json").status_code, 403)
        warehouse = self.client_for("luka", "Lager")
        self.assertEqual(warehouse.post(self.url, {"todos": [self.label.pk]}, format="json").json()["done"], 1)
        self.assertEqual(self.client_for("vera").post(self.url, {"todos": [self.clean.pk]}).status_code, 403)

    def test_the_description(self) -> None:
        schema = self.admin.get(f"{API}/schema", {"format": "json"}).json()
        operation = schema["paths"][f"{API}/material-todos/done"]["post"]
        self.assertIn("requestBody", operation)
        self.assertIn("200", operation["responses"])
