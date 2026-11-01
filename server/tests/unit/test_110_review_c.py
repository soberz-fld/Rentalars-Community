# SPDX-License-Identifier: GPL-3.0-or-later
"""What the independent review of the e-invoice, the backup and the media view found."""

from __future__ import annotations

import io
import tarfile
from decimal import Decimal as D  # noqa: N817
from pathlib import Path

from django.conf import settings
from django.test import override_settings

from rentalars.core import backup
from rentalars.incoming import einvoice, filters, reading, services
from rentalars.incoming.models import MAX_POSITIONS, IncomingInvoice
from tests.helpers import RentalarsTestCase
from tests.ui.base import UiTestCase
from tests.unit.test_110_einvoice_in import ubl, xml_upload


def rows_of(count: int, *, charges: int = 0, article: str = "") -> list[dict]:
    rows = [
        {"description": f"Kabel {n}", "article_number": article or f"A-{n}", "quantity": "1", "unit_price_net": "1.00"}
        for n in range(count)
    ]
    rows += [
        {"description": f"Rabatt {n}", "quantity": "1", "unit_price_net": "-1.00", "kind": "cost", "charge": True}
        for n in range(charges)
    ]
    return rows


class MediaViewTests(UiTestCase):
    def test_dots_in_the_path_do_not_leave_the_folder(self) -> None:
        folder = Path(settings.MEDIA_ROOT) / "incoming"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "geheim.xml").write_text("<x/>", encoding="utf-8")
        for path in (
            "company/../incoming/geheim.xml",
            "company/%2e%2e/incoming/geheim.xml",
            "labels/./../incoming/geheim.xml",
            "company//x",
        ):
            self.assertEqual(self.client.get("/media/" + path).status_code, 404, path)


class EInvoiceNumbersTests(RentalarsTestCase):
    def row(self, quantity: str, price: str, net: str) -> dict:
        line = einvoice.Line(name="Teil", quantity=D(quantity), unit_price=D(price), net=D(net))
        return einvoice._row_of_line(line, False)

    def test_a_price_that_does_not_fit_four_places_keeps_the_net_of_the_file(self) -> None:
        for quantity, price, net in (("30000", "0.00333", "100.00"), ("100", "0.1049", "10.50")):
            row = self.row(quantity, price, net)
            total = D(row["quantity"]) * D(row["unit_price_net"])
            self.assertEqual(total.quantize(D("0.01")), D(net), (quantity, price))
            self.assertTrue(row["hints"])

    def test_a_price_that_fits_is_left_alone(self) -> None:
        row = self.row("3", "99.00", "297.00")
        self.assertEqual((row["quantity"], row["unit_price_net"], row["hints"]), ("3", "99.0000", []))

    def test_absurd_numbers_are_no_numbers(self) -> None:
        self.assertIsNone(einvoice._decimal("9E+9999999"))
        self.assertIsNone(einvoice._decimal("12345678901234567890"))
        self.assertEqual(einvoice._decimal("12345.67"), D("12345.67"))

    def test_an_unknown_encoding_is_refused_not_a_server_error(self) -> None:
        data = b'<?xml version="1.0" encoding="UTF-7"?><Invoice/>'
        with self.assertRaises(einvoice.EInvoiceError):
            einvoice.parse(data)


class ReadAgainTests(RentalarsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.invoice = services.create_from_upload(xml_upload(ubl()), user=None)
        self.invoice.positions.all().delete()

    def test_two_rows_with_the_same_article_stay_two_positions_when_read_again(self) -> None:
        rows = [
            {"description": "Kabel", "article_number": "K-1", "quantity": "3", "unit_price_net": "99.00"},
            {"description": "Kabel", "article_number": "K-1", "quantity": "2", "unit_price_net": "25.00"},
        ]
        reading.apply_proposal(self.invoice, {"positions": rows}, replace_positions=True)
        first = self.invoice.positions.order_by("place").first()
        first.user_edited = True
        first.save()
        reading.apply_proposal(self.invoice, {"positions": rows}, replace_positions=True)
        self.assertEqual(self.invoice.positions.count(), 2)
        self.assertEqual(
            sorted(p.quantity * p.unit_price_net for p in self.invoice.positions.all()), [D("50.00"), D("297.00")]
        )

    def test_discounts_survive_when_there_are_too_many_positions(self) -> None:
        reading.apply_proposal(
            self.invoice, {"positions": rows_of(MAX_POSITIONS + 7, charges=2)}, replace_positions=True
        )
        self.invoice.refresh_from_db()
        names = list(self.invoice.positions.values_list("description", flat=True))
        self.assertEqual(len(names), MAX_POSITIONS)
        self.assertIn("Rabatt 0", names)
        self.assertIn("Rabatt 1", names)
        self.assertRegex(self.invoice.reading["note"], r"\b9\b")  # how many were left out


class TotalsTests(RentalarsTestCase):
    def test_a_credit_note_is_taken_off(self) -> None:
        services.create_from_upload(xml_upload(ubl()), user=None)
        credit = services.create_from_upload(xml_upload(ubl()), user=None)
        IncomingInvoice.objects.filter(pk=credit.pk).update(
            reading={**credit.reading, "einvoice": {"credit_note": True}}
        )
        totals = filters.totals(IncomingInvoice.objects.all())
        self.assertEqual((totals.net, totals.tax, totals.gross), (D("0.00"), D("0.00"), D("0.00")))


class BackupTests(RentalarsTestCase):
    def media(self, root: Path) -> None:
        for name in (
            "company/logo.png",
            "jobs/backups/1.tar.gz",
            ".deleted/2026-10-20/jobs/backups/2.tar.gz",
            ".deleted/2026-10-20/incoming/a.pdf",
        ):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x")

    def test_backups_in_the_trash_are_not_carried_along(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            self.media(Path(folder))
            names = {name for _path, name in backup._media_files()}
        self.assertIn("media/company/logo.png", names)
        self.assertIn("media/.deleted/2026-10-20/incoming/a.pdf", names)
        self.assertFalse([n for n in names if "jobs/backups" in n and not n.endswith("/jobs")], names)

    def test_a_file_deleted_while_the_archive_is_written_is_found_in_the_trash(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            root = Path(folder)
            self.media(root)
            work = root.parent / "work-test"
            work.mkdir(exist_ok=True)
            (work / "database.sql").write_text("-- dump", encoding="utf-8")
            calls = {"n": 0}
            original = backup._media_files

            def moving():
                calls["n"] += 1
                if calls["n"] == 2:  # the second walk (after the loop) sees the file in the trash
                    path = root / ".deleted" / "2026-10-23" / "company" / "late.png"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"late")
                yield from original()

            backup._media_files = moving
            try:
                output = io.BytesIO()
                backup.write_archive(output, work)
            finally:
                backup._media_files = original
            output.seek(0)
            with tarfile.open(fileobj=output, mode="r:gz") as archive:
                names = archive.getnames()
        self.assertIn("media/.deleted/2026-10-23/company/late.png", names)
