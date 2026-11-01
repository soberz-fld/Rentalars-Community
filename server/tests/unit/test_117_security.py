# SPDX-License-Identifier: GPL-3.0-or-later
"""The gaps closed after the security review (S1 – S11)."""

from __future__ import annotations

import io
from collections.abc import Iterator
from contextlib import contextmanager
from unittest import mock

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from tests.helpers import RentalarsTestCase


def picture(kind: str) -> bytes:
    """A small picture of the given format as Pillow writes it."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("1" if kind in {"XBM"} else "RGB", (8, 8)).save(buffer, format=kind)
    return buffer.getvalue()


@contextmanager
def decoders_forbidden(*names: str) -> Iterator[None]:
    """Fail the test when Pillow opens a file with the plugin of one of these formats."""
    from PIL import GifImagePlugin, TiffImagePlugin, XbmImagePlugin

    plugins = {
        "GIF": GifImagePlugin.GifImageFile,
        "TIFF": TiffImagePlugin.TiffImageFile,
        "XBM": XbmImagePlugin.XbmImageFile,
    }
    patches = [
        mock.patch.object(plugins[name], "_open", side_effect=AssertionError(f"{name} decoder was used"))
        for name in names
    ]
    for patch in patches:
        patch.start()
    try:
        yield
    finally:
        for patch in patches:
            patch.stop()


class OnlyTheExpectedPictureFormatsTests(RentalarsTestCase):
    """S1: a file named .png that is a GIF, XBM or TIFF is refused without that decoder reading it."""

    def upload(self, kind: str, name: str = "bild.png") -> SimpleUploadedFile:
        return SimpleUploadedFile(name, picture(kind), content_type="image/png")

    def test_logo_and_images(self) -> None:
        from rentalars.core.uploads import validate_image_upload

        for kind in ("GIF", "XBM", "TIFF"):
            with self.subTest(kind=kind), decoders_forbidden("GIF", "TIFF", "XBM"), self.assertRaises(ValidationError):
                validate_image_upload(self.upload(kind))
        validate_image_upload(self.upload("PNG"))

    def test_receipts_of_expenses(self) -> None:
        from rentalars.timetracking.expenses import prepare_receipt

        for kind in ("GIF", "XBM", "TIFF"):
            with self.subTest(kind=kind), decoders_forbidden("GIF", "TIFF", "XBM"), self.assertRaises(ValidationError):
                prepare_receipt(self.upload(kind))
        prepare_receipt(self.upload("PNG"))

    def test_the_picture_of_an_incoming_invoice(self) -> None:
        from rentalars.incoming.services import validate_invoice_file

        for kind in ("GIF", "XBM", "TIFF"):
            with self.subTest(kind=kind), decoders_forbidden("GIF", "TIFF", "XBM"), self.assertRaises(ValidationError):
                validate_invoice_file(self.upload(kind))

    def test_photos_of_the_chat(self) -> None:
        from rentalars.chat.media import prepare_files

        for kind in ("XBM", "TIFF"):  # a GIF is a photo in the chat
            with self.subTest(kind=kind), decoders_forbidden("TIFF", "XBM"), self.assertRaises(ValidationError):
                prepare_files([self.upload(kind)])
        self.assertEqual(len(prepare_files([self.upload("PNG")])), 1)

    def test_the_logo_on_a_label(self) -> None:
        from rentalars.material.label_layouts import print_logo

        with decoders_forbidden("GIF", "TIFF", "XBM"):
            for kind in ("GIF", "XBM", "TIFF"):
                self.assertEqual(print_logo(picture(kind), 100, 50), ("", 0, 0))
        self.assertNotEqual(print_logo(picture("PNG"), 100, 50)[0], "")


# --- S2: the sender of an answer by mail ------------------------------------------------------------------------

from rentalars.mail.models import CrewRequestMail, LogResult, MailLogEntry, MailSettings  # noqa: E402
from rentalars.projects.models import RequestStatus  # noqa: E402
from tests.unit.test_063_crewmail import CrewMailTestCase, answer_mail  # noqa: E402


class NoOtherReadersTests(RentalarsTestCase):
    """S1: code that calls ``Image.open`` without a list (Django's image field, WeasyPrint) gets only the five readers."""

    def test_pillow_knows_only_the_formats_of_the_program(self) -> None:
        from PIL import Image

        from rentalars.core.pictures import READABLE_FORMATS

        self.assertTrue(set(Image.OPEN) <= READABLE_FORMATS, sorted(set(Image.OPEN) - READABLE_FORMATS))
        self.assertTrue({"JPEG", "PNG", "GIF", "WEBP"} <= set(Image.OPEN))

    def test_a_picture_of_another_format_is_not_an_image_for_the_form_field_either(self) -> None:
        from django import forms

        field = forms.ImageField()
        for kind in ("TIFF", "XBM", "BMP"):
            with self.subTest(kind=kind), self.assertRaises(ValidationError):
                field.clean(SimpleUploadedFile("bild.png", picture(kind), content_type="image/png"))
        field.clean(SimpleUploadedFile("bild.png", picture("PNG"), content_type="image/png"))


class SenderOfAnAnswerTests(CrewMailTestCase):
    """S2: the sender is read from the structure of the header; strange spellings and forged lines do not count."""

    def setUp(self) -> None:
        super().setUp()
        self.ask()
        self.request = self.request_message()

    def answer_from(self, line: bytes, **kwargs: object) -> None:
        raw = answer_mail(self.request, **kwargs).replace(b"From: Anna Becker <anna@crew.example>", line, 1)
        self.fetch(raw)

    def assert_refused(self, detail: str = "accepted:sender") -> None:
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.REQUESTED)
        self.assertEqual(MailLogEntry.objects.get(result=LogResult.CREW_ANSWER).detail, detail)

    def test_a_quoted_text_is_no_address(self) -> None:
        self.answer_from(b'From: "anna@crew.example"')
        self.assert_refused()

    def test_an_encoded_word_without_an_address_is_no_address(self) -> None:
        self.answer_from(b"From: =?utf-8?b?YW5uYUBjcmV3LmV4YW1wbGU=?=")  # anna@crew.example
        self.assert_refused()

    def test_a_display_name_that_looks_like_an_address_does_not_count(self) -> None:
        self.answer_from(b'From: "anna@crew.example" <kollege@example.org>')
        self.assert_refused()

    def test_a_soft_hyphen_or_a_zero_width_space_in_the_domain(self) -> None:
        CrewRequestMail.objects.update(sent_to="anna@mail.example")
        for hidden in ("­", "​"):
            with self.subTest(character=hex(ord(hidden))):
                MailLogEntry.objects.all().delete()
                self.answer_from(f"From: Anna <anna@gm{hidden}ail.com>".encode())
                self.assert_refused()

    def test_dots_in_the_display_name_are_harmless(self) -> None:
        """``Dr. Anna Müller <…>`` is old but unambiguous syntax; it must not cost the crew their answers."""
        self.answer_from(b"From: Dr. Anna M. Becker <anna@crew.example>")
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.ACCEPTED)

    def test_a_clean_address_still_counts(self) -> None:
        self.fetch(answer_mail(self.request))
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.ACCEPTED)

    def test_an_address_with_raw_umlauts_in_the_domain_counts_for_the_same_domain(self) -> None:
        CrewRequestMail.objects.update(sent_to="anna@müller.example")
        self.answer_from("From: Anna <anna@müller.example>".encode())
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.ACCEPTED)


class ConfirmedSenderTests(CrewMailTestCase):
    """S2: with the mail server named in the settings only an answer that this server confirmed counts."""

    def setUp(self) -> None:
        super().setUp()
        self.ask()
        self.request = self.request_message()

    def trust(self, server: str = "mx.verleih.example") -> None:
        settings = MailSettings.load()
        settings.crew_answer_trusted_server = server
        settings.save()

    def answer(self, *results: str) -> str:
        """Send an answer with these ``Authentication-Results`` headers; the status of the line afterwards."""
        mail = answer_mail(self.request)
        for value in results:
            mail = f"Authentication-Results: {value}\r\n".encode() + mail
        self.fetch(mail)
        self.line.refresh_from_db()
        return self.line.request_status

    def test_without_a_server_named_nothing_changes(self) -> None:
        self.assertEqual(self.answer(), RequestStatus.ACCEPTED)

    def test_no_result_at_all_is_not_a_confirmation(self) -> None:
        self.trust()
        self.assertEqual(self.answer(), RequestStatus.REQUESTED)
        self.assertEqual(MailLogEntry.objects.get(result=LogResult.CREW_ANSWER).detail, "accepted:unconfirmed")
        (reply,) = self.replies()
        self.assertIn("bestätigt", reply.body)

    def test_dmarc_pass_of_the_own_server_counts(self) -> None:
        self.trust()
        self.assertEqual(self.answer("mx.verleih.example; spf=pass; dkim=pass; dmarc=pass"), RequestStatus.ACCEPTED)

    def test_a_version_number_after_the_name_is_allowed(self) -> None:
        self.trust()
        self.assertEqual(self.answer("MX.Verleih.Example 1; dmarc=pass"), RequestStatus.ACCEPTED)

    def test_a_pass_written_by_the_sender_is_not_believed(self) -> None:
        """The header can come with the mail: only the one of the own server counts."""
        self.trust()
        self.assertEqual(self.answer("evil.example; dmarc=pass"), RequestStatus.REQUESTED)

    def test_a_pass_of_the_sender_does_not_outweigh_a_fail_of_the_own_server(self) -> None:
        self.trust()
        status = self.answer("evil.example; dmarc=pass", "mx.verleih.example; dmarc=fail")
        self.assertEqual(status, RequestStatus.REQUESTED)

    def test_dkim_pass_for_the_domain_of_the_sender_counts(self) -> None:
        self.trust()
        self.assertEqual(
            self.answer("mx.verleih.example; dmarc=none; dkim=pass header.d=crew.example"), RequestStatus.ACCEPTED
        )

    def test_dkim_pass_of_another_domain_does_not(self) -> None:
        self.trust()
        status = self.answer("mx.verleih.example; dmarc=none; dkim=pass header.d=evil.example")
        self.assertEqual(status, RequestStatus.REQUESTED)

    def test_no_verdict_is_no_confirmation(self) -> None:
        self.trust()
        for result in (
            "mx.verleih.example; dmarc=none",
            "mx.verleih.example; dmarc=permerror",
            "mx.verleih.example; spf=pass",
        ):
            with self.subTest(result=result):
                MailLogEntry.objects.all().delete()
                self.assertEqual(self.answer(result), RequestStatus.REQUESTED)

    def test_a_forged_pass_below_the_header_of_the_own_server_does_not_count(self) -> None:
        """The sender can write a header with the name of the server (it is public); the server's own is on top."""
        self.trust()
        status = self.answer("mx.verleih.example; dmarc=pass", "mx.verleih.example; dmarc=none")
        self.assertEqual(status, RequestStatus.REQUESTED)

    def test_a_field_cannot_start_a_result(self) -> None:
        """Values that the sender influences (the envelope address, a comment) hold no results of their own."""
        self.trust()
        for result in (
            'mx.verleih.example; spf=none smtp.mailfrom="x;dmarc=pass"@evil.example; dmarc=none',
            "mx.verleih.example; spf=none (note; dmarc=pass) smtp.mailfrom=x@evil.example; dmarc=none",
            "mx.verleih.example; spf=none (a (nested; dmarc=pass) comment); dmarc=none",
        ):
            with self.subTest(result=result):
                MailLogEntry.objects.all().delete()
                self.assertEqual(self.answer(result), RequestStatus.REQUESTED)

    def test_dmarc_pass_must_be_for_the_domain_of_the_sender(self) -> None:
        self.trust()
        self.assertEqual(
            self.answer("mx.verleih.example; dmarc=pass header.from=evil.example"), RequestStatus.REQUESTED
        )
        MailLogEntry.objects.all().delete()
        self.assertEqual(self.answer("mx.verleih.example; dmarc=pass header.from=crew.example"), RequestStatus.ACCEPTED)

    def test_dkim_of_a_top_level_domain_alone_is_nothing(self) -> None:
        self.trust()
        self.assertEqual(
            self.answer("mx.verleih.example; dmarc=none; dkim=pass header.d=example"), RequestStatus.REQUESTED
        )

    def test_a_server_that_writes_one_header_per_check_is_understood(self) -> None:
        """A milter for DKIM and one for DMARC each prepend a header with the same name."""
        self.trust()
        status = self.answer("mx.verleih.example; dmarc=pass", "mx.verleih.example; dkim=pass header.d=other.example")
        self.assertEqual(status, RequestStatus.ACCEPTED)


class SelfCheckHintTests(CrewMailTestCase):
    """S2: the self-check says that the sender of an answer is not confirmed, as long as nothing is entered."""

    def notes(self) -> list[str]:
        from rentalars.core import selfcheck

        report = selfcheck.Report()
        selfcheck._mail(report)
        return [item.title for item in report.findings if "reply" in item.detail or "Antwortmail" in item.detail]

    def test_hint_until_the_server_is_named(self) -> None:
        self.assertEqual(len(self.notes()), 1)
        settings = MailSettings.load()
        settings.crew_answer_trusted_server = "mx.verleih.example"
        settings.save()
        self.assertEqual(self.notes(), [])

    def test_no_hint_when_answers_go_by_the_link_only(self) -> None:
        settings = MailSettings.load()
        settings.crew_answers = "link"
        settings.save()
        self.assertEqual(self.notes(), [])


# --- S4: the key of the example file ----------------------------------------------------------------------------


class PlaceholderSecretKeyTests(RentalarsTestCase):
    """S4: a server that was started with the example file as it is does not start."""

    def load(self, text: str):
        import tempfile
        from pathlib import Path

        from rentalars.config import load_config

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "rentalars.conf"
            path.write_text(text, encoding="utf-8")
            return load_config(path)

    def example(self) -> str:
        from pathlib import Path

        from django.conf import settings

        return (Path(settings.BASE_DIR) / "deploy" / "rentalars.conf.example").read_text(encoding="utf-8")

    def test_the_example_file_as_it_is_is_refused_in_production(self) -> None:
        from rentalars.config import ConfigurationError

        text = self.example()  # "production" unless it says otherwise
        with self.assertRaisesRegex(ConfigurationError, "secret_key.*placeholder"):
            self.load(text)

    def test_the_development_key_and_the_usual_words_are_refused(self) -> None:
        from rentalars.config import DEVELOPMENT_SECRET_KEY, ConfigurationError

        for key in (DEVELOPMENT_SECRET_KEY, "REPLACE-WITH-A-LONG-RANDOM-TEXT", "changeme", "a-long-random-string"):
            with self.subTest(key=key), self.assertRaises(ConfigurationError):
                self.load(f"[rentalars]\nsecret_key = {key}\nurl = https://x.example\n[database]\npassword = p\n")

    def test_a_real_key_is_accepted(self) -> None:
        config = self.load(
            "[rentalars]\nsecret_key = " + "ab12" * 24 + "\nurl = https://x.example\n[database]\npassword = p\n"
        )
        self.assertEqual(len(config.secret_key), 96)

    def test_the_development_mode_keeps_its_key(self) -> None:
        config = self.load(
            "[rentalars]\nenvironment = development\nsecret_key = REPLACE-WITH-A-LONG-RANDOM-TEXT\n[database]\nengine = sqlite\n"
        )
        self.assertTrue(config.secret_key)


# --- S7: an XLSX file with endless empty rows -------------------------------------------------------------------


class EmptyRowsOfAWorkbookTests(RentalarsTestCase):
    """S7: formatted empty rows are not read to the end of the sheet."""

    def workbook(self, data_rows: int, blank_rows: int, data_after: int = 0) -> io.BytesIO:
        from openpyxl import Workbook
        from openpyxl.cell import WriteOnlyCell

        book = Workbook(write_only=True)
        sheet = book.create_sheet()
        sheet.append(["Name"])
        for number in range(data_rows):
            sheet.append([f"Zeile {number}"])
        for _row in range(blank_rows):
            cell = WriteOnlyCell(sheet, value=None)
            cell.number_format = "0.00"  # a formatted, empty row: the file holds it
            sheet.append([cell])
        for number in range(data_after):
            sheet.append([f"Danach {number}"])
        buffer = io.BytesIO()
        book.save(buffer)
        buffer.seek(0)
        return buffer

    def test_empty_rows_in_between_are_still_skipped(self) -> None:
        from rentalars.core import tabular

        table = tabular.read_table(self.workbook(3, 10, data_after=2), "daten.xlsx")
        self.assertEqual(len(table.rows), 5)

    def test_not_more_rows_of_any_kind_than_the_limit(self) -> None:
        from rentalars.core import tabular

        with (
            mock.patch.object(tabular, "MAX_SCANNED_ROWS", 100),
            self.assertRaisesRegex(tabular.ImportFileError, "Leere Zeilen|empty|leere"),
        ):
            tabular.read_table(self.workbook(3, 200), "daten.xlsx")

    def test_a_workbook_of_very_many_empty_rows_is_refused_quickly(self) -> None:
        """Formatted empty rows beyond the limit: refused after the limit, not read to the end of the sheet."""
        import time

        from rentalars.core import tabular

        book = self.workbook(3, 60_000)
        started = time.monotonic()
        with mock.patch.object(tabular, "MAX_SCANNED_ROWS", 20_000), self.assertRaises(tabular.ImportFileError):
            tabular.read_table(book, "daten.xlsx")
        self.assertLess(time.monotonic() - started, 20)

    def test_a_wide_sheet_is_not_read_to_the_last_column(self) -> None:
        """The cost of an empty row is the width of the sheet: only MAX_COLUMNS cells of each row are looked at."""
        from rentalars.core import tabular

        table = tabular.read_table(self.workbook(2, 5), "daten.xlsx")
        self.assertEqual((table.headers, len(table.rows)), (["Name"], 2))
        with mock.patch.object(tabular, "MAX_COLUMNS", 3):
            book = io.BytesIO()
            from openpyxl import Workbook

            workbook = Workbook()
            workbook.active.append(["a", "b", "c", "d"])
            workbook.save(book)
            book.seek(0)
            with self.assertRaises(tabular.ImportFileError):
                tabular.read_table(book, "breit.xlsx")
