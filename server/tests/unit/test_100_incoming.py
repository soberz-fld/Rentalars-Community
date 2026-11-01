# SPDX-License-Identifier: GPL-3.0-or-later
"""Incoming invoices – the register in Buchhaltung, items made from it, ancillary costs spread (ENG-100). (DOK-023, DOK-024)

The requirements: a management of incoming invoices (in Buchhaltung) including AI recognition of invoice number, date,
supplier, price, ... and a note; items or quantities of bulk material can be created from incoming invoices; transport
costs of purchase invoices are spread as ancillary acquisition costs (per position merchandise, GWG or fixed asset
with a useful life). Decided: with the book value of the asset kept open for the
books ("Mit Restbuchwert"); the tax account is only noted (``IncomingInvoice`` docstring), not built.

* The register: upload of a PDF or a picture (type and size checked), reading (text patterns; the AI if switched
  on), list with filters, detail with note and status, a downloadable original.
* Ancillary costs: positions marked as such are spread over the goods by value, quantity or weight, cent-exact; per
  position a kind of asset (merchandise, GWG, fixed asset) and a useful life, with the GWG limit of the settings.
* Booking in: preview, explicit confirmation, items with their acquisition cost and the position they came from;
  a position already booked in is not booked twice by accident.
* API: every operation of the pages (API-014).
"""

from __future__ import annotations

import datetime
import io
import json
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from rentalars.accounts.rights import Rights, rights_of
from rentalars.ai.models import AICall
from rentalars.core.models import AuditLogEntry
from rentalars.incoming import access, booking, costing, filters, reading, services
from rentalars.incoming.models import (
    AllocationKey,
    IncomingInvoice,
    InvoicePosition,
    InvoiceStatus,
    PositionType,
    ReadingState,
)
from rentalars.masterdata.models import Supplier
from rentalars.material import purchases
from rentalars.material.asset_models import AssetSettings
from rentalars.material.models import AssetKind, MaterialFile, MaterialItem, MaterialModel
from tests.api.base import API, ApiTestCase
from tests.helpers import ALL_RIGHTS, RentalarsTestCase, category, make_model, make_user
from tests.ui.base import UiTestCase, form_data
from tests.unit.test_091_purchase import AIMixin, FilesMixin, material_writer, pdf_of, scanned_pdf

INCOMING_LINES = (
    "Musikhaus Muster GmbH & Co. KG",
    "Hauptstraße 5, 12345 Musterstadt",
    "Rechnung Nr. RE-2027-0815",
    "Rechnungsdatum: 22.02.2027",
    "Fällig am: 22.03.2027",
    "Pos. Artikel Menge Einzelpreis",
    "1 Shure SM58 3 99,00 €",
    "2 Neutrik NL4 Kabel 10 m 2 25,00 €",
    "3 Fracht und Verpackung 1 30,00 €",
    "Summe netto 377,00 €",
    "Umsatzsteuer 19 % 71,63 €",
    "Summe brutto 448,63 €",
)


def upload(content: bytes | None = None, name: str = "rechnung.pdf") -> SimpleUploadedFile:
    """An uploaded invoice; by default the PDF above."""
    return SimpleUploadedFile(name, content if content is not None else pdf_of(INCOMING_LINES), "application/pdf")


def answer_of(**changes: object) -> str:
    """What a well-behaved model answers for the invoice above: two goods positions and the freight."""
    data: dict[str, object] = {
        "supplier": "Musikhaus Muster GmbH & Co. KG",
        "invoice_number": "RE-2027-0815",
        "invoice_date": "2027-02-22",
        "due_date": "2027-03-22",
        "total_net": 377.0,
        "total_tax": 71.63,
        "total_gross": 448.63,
        "prices_include_tax": False,
        "tax_rate": 19,
        "positions": [
            {"description": "Shure SM58", "manufacturer": "Shure", "article_number": "SM58-LCE", "quantity": 3,
             "unit_price_net": 99.0, "kind": "goods"},
            {"description": "Neutrik NL4 Kabel 10 m", "manufacturer": "Neutrik", "article_number": "NL4-10",
             "quantity": 2, "unit_price_net": 25.0, "kind": "goods"},
            {"description": "Fracht und Verpackung", "quantity": 1, "unit_price_net": 30.0, "kind": "cost"},
        ],
    }  # fmt: skip
    data.update(changes)
    return "```json\n" + json.dumps(data) + "\n```"


def make_invoice(*, read: bool = False) -> IncomingInvoice:
    """An invoice of the register, uploaded as the pages do it (not read unless ``read``)."""
    return services.create_from_upload(upload(), user=None, read=read)


def add(invoice: IncomingInvoice, description: str, quantity: str, price: str, **fields: object) -> InvoicePosition:
    """A position at the end of an invoice; a goods position is treated as a low-value asset unless told otherwise.

    Booking in needs the kind to be chosen – the limit of the settings only proposes – so the helper chooses.
    """
    if fields.get("position_type", PositionType.GOODS) == PositionType.GOODS:
        fields.setdefault("asset_kind", AssetKind.LOW_VALUE)
    return services.add_position(
        invoice, {"description": description, "quantity": Decimal(quantity), "unit_price_net": Decimal(price), **fields}
    )


def goods_invoice(
    *, freight: str | None = "30.00", key: str = "value"
) -> tuple[IncomingInvoice, InvoicePosition, InvoicePosition]:
    """3 microphones at 99.00 and 2 cables at 25.00 and, if wished, freight; ``key`` spreads the freight."""
    invoice = make_invoice()
    mic = add(invoice, "Shure SM58", "3", "99.00")
    cable = add(invoice, "Neutrik NL4 Kabel 10 m", "2", "25.00")
    if freight is not None:
        add(invoice, "Fracht und Verpackung", "1", freight, position_type=PositionType.ANCILLARY)
    services.update_head(invoice, {"allocation_key": key})
    return invoice, mic, cable


# --- Spreading the ancillary costs --------------------------------------------------------------------------------


class SpreadTests(RentalarsTestCase):
    """The shares are whole cents and add up exactly; the same for the pieces of a position."""

    def test_the_shares_add_up_exactly(self) -> None:
        shares = costing.spread(Decimal("30.00"), [Decimal("297"), Decimal("50")])
        self.assertEqual(shares, [Decimal("25.68"), Decimal("4.32")])
        thirds = costing.spread(Decimal("10.00"), [Decimal(1)] * 3)
        self.assertEqual(sum(thirds), Decimal("10.00"))
        self.assertEqual(sorted(thirds), [Decimal("3.33"), Decimal("3.33"), Decimal("3.34")])

    def test_a_discount_is_spread_negated_and_zero_weights_get_nothing(self) -> None:
        shares = costing.spread(Decimal("-10.00"), [Decimal(1), Decimal(0), Decimal(2)])
        self.assertEqual(shares, [Decimal("-3.33"), Decimal("0.00"), Decimal("-6.67")])
        with self.assertRaises(ValueError):
            costing.spread(Decimal("5.00"), [Decimal(0)])

    def test_the_pieces_of_a_position_get_the_odd_cents_first(self) -> None:
        pieces = costing.even_pieces(Decimal("10.00"), 3, 0, 3)
        self.assertEqual(pieces, [Decimal("3.34"), Decimal("3.33"), Decimal("3.33")])
        # Booked in two steps the pieces get what they would have got in one.
        later = costing.even_pieces(Decimal("10.00"), 3, 1, 2)
        self.assertEqual(later, pieces[1:])
        self.assertEqual(costing.from_cents(costing.even_slice_cents(1000, 3, 0, 2)), Decimal("6.67"))

    def test_a_large_quantity_needs_no_large_list(self) -> None:
        self.assertEqual(costing.even_slice_cents(10_000_000, 1_000_000, 0, 1_000_000), 10_000_000)
        self.assertEqual(costing.even_slice_cents(1_000_001, 1_000_000, 999_999, 1), 1)


class CostingTests(FilesMixin, RentalarsTestCase):
    """ENG-100: freight as ancillary acquisition cost; GWG or fixed asset with a useful life."""

    def test_by_value(self) -> None:
        invoice, mic, cable = goods_invoice()
        found = costing.costing_of(invoice)
        self.assertEqual(
            (found.ancillary_total, found.goods_total, found.total),
            (Decimal("30.00"), Decimal("347.00"), Decimal("377.00")),
        )
        rows = {row.position.pk: row for row in found.rows}
        self.assertEqual(
            (rows[mic.pk].share, rows[mic.pk].total, rows[mic.pk].per_piece),
            (Decimal("25.68"), Decimal("322.68"), Decimal("107.56")),
        )
        self.assertEqual((rows[cable.pk].share, rows[cable.pk].per_piece), (Decimal("4.32"), Decimal("27.16")))
        self.assertEqual(found.spread_total, Decimal("30.00"))
        self.assertEqual(found.problems, [])

    def test_by_quantity_and_by_weight(self) -> None:
        invoice, mic, cable = goods_invoice(freight="10.00")
        by_quantity = {row.position.pk: row.share for row in costing.costing_of(invoice, key="quantity").rows}
        self.assertEqual(by_quantity, {mic.pk: Decimal("6.00"), cable.pk: Decimal("4.00")})
        # Without weights the key weight says so and spreads nothing.
        missing = costing.costing_of(invoice, key="weight")
        self.assertTrue(any("weight" in problem.lower() or "Gewicht" in problem for problem in missing.problems))
        services.update_position(mic, {"weight_kg": Decimal("0.300")})
        services.update_position(cable, {"weight_kg": Decimal("1.000")})
        by_weight = {row.position.pk: row.share for row in costing.costing_of(invoice, key="weight").rows}
        self.assertEqual(by_weight, {mic.pk: Decimal("3.103448").quantize(Decimal("0.01")), cable.pk: Decimal("6.90")})
        # The key saved with the invoice is the default of the page.
        services.update_head(invoice, {"allocation_key": AllocationKey.QUANTITY})
        self.assertEqual(costing.costing_of(invoice).key, "quantity")

    def test_the_weight_of_the_model_counts_when_the_position_has_none(self) -> None:
        invoice, mic, _cable = goods_invoice(freight="10.00")
        model = make_model("Shure SM58", category_code="T")
        model.weight_kg = Decimal("0.500")
        model.save()
        services.update_position(mic, {"material_model": model})
        found = costing.costing_of(invoice, key="weight")
        self.assertEqual(next(row for row in found.rows if row.position.pk == mic.pk).weight, Decimal("1.500"))

    def test_a_discount_lowers_the_cost(self) -> None:
        invoice, _mic, _cable = goods_invoice(freight="-34.70")
        found = costing.costing_of(invoice)
        self.assertEqual((found.ancillary_total, found.total), (Decimal("-34.70"), Decimal("312.30")))

    def test_ancillary_costs_without_goods_or_value_are_a_problem(self) -> None:
        invoice = make_invoice()
        add(invoice, "Fracht", "1", "30.00", position_type=PositionType.ANCILLARY)
        self.assertTrue(costing.costing_of(invoice).problems)
        add(invoice, "Gratisprobe", "1", "0.00")
        self.assertTrue(costing.costing_of(invoice).problems)  # by value, the goods add up to nothing

    def test_the_gwg_limit_is_inclusive_and_set_in_the_settings(self) -> None:
        invoice = make_invoice()
        exactly = add(invoice, "Pult", "1", "800.00", asset_kind="")
        above = add(invoice, "Pult teuer", "1", "800.01", asset_kind="")
        kinds = {row.position.pk: row.kind for row in costing.costing_of(invoice).rows}
        self.assertEqual(kinds, {exactly.pk: AssetKind.LOW_VALUE, above.pk: AssetKind.FIXED_ASSET})
        settings = AssetSettings.load()
        settings.low_value_limit_net = Decimal("250.00")
        settings.save()
        kinds = {row.position.pk: row.kind for row in costing.costing_of(invoice).rows}
        self.assertEqual(set(kinds.values()), {AssetKind.FIXED_ASSET})

    def test_the_freight_can_lift_a_piece_over_the_limit(self) -> None:
        invoice = make_invoice()
        pult = add(invoice, "Pult", "1", "790.00", asset_kind="")
        add(invoice, "Fracht", "1", "20.00", position_type=PositionType.ANCILLARY)
        row = costing.costing_of(invoice).row_of(pult)
        assert row is not None
        self.assertEqual((row.per_piece, row.kind, row.useful_life), (Decimal("810.00"), AssetKind.FIXED_ASSET, 60))

    def test_the_kind_and_the_useful_life_can_be_chosen(self) -> None:
        invoice = make_invoice()
        cheap = add(invoice, "Kabel", "10", "5.00", asset_kind=AssetKind.MERCHANDISE)
        pult = add(invoice, "Pult", "1", "500.00", asset_kind=AssetKind.FIXED_ASSET, useful_life_months=36)
        found = costing.costing_of(invoice)
        self.assertEqual(found.row_of(cheap).kind, AssetKind.MERCHANDISE)  # type: ignore[union-attr]
        self.assertIsNone(found.row_of(cheap).useful_life)  # type: ignore[union-attr]
        self.assertEqual((found.row_of(pult).kind, found.row_of(pult).useful_life), (AssetKind.FIXED_ASSET, 36))  # type: ignore[union-attr]
        settings = AssetSettings.load()
        settings.default_useful_life_months = 48
        settings.save()
        services.update_position(pult, {"useful_life_months": None})
        self.assertEqual(costing.costing_of(invoice).row_of(pult).useful_life, 48)  # type: ignore[union-attr]

    def test_a_foreign_currency_is_converted(self) -> None:
        invoice, mic, _cable = goods_invoice(freight=None)
        services.update_head(invoice, {"currency": "USD", "exchange_rate": Decimal("0.5")})
        row = costing.costing_of(invoice).row_of(mic)
        assert row is not None
        self.assertEqual(row.line, Decimal("148.50"))

    def test_a_quantity_that_is_not_whole_cannot_be_booked(self) -> None:
        invoice = make_invoice()
        cable = add(invoice, "Kabel je Meter", "2.5", "3.00")
        row = costing.costing_of(invoice).row_of(cable)
        assert row is not None
        self.assertTrue(row.problems)


# --- The file and the reading ------------------------------------------------------------------------------------


class FileTests(FilesMixin, RentalarsTestCase):
    """Type and size of the file are checked; the file is stored like other documents."""

    def test_a_pdf_and_pictures_are_accepted(self) -> None:
        invoice = services.create_from_upload(upload(), user=None, read=False)
        self.assertEqual(
            (invoice.original_name, invoice.size > 0, len(invoice.content_hash)), ("rechnung.pdf", True, 64)
        )
        self.assertTrue(invoice.file.name.startswith("incoming/"))
        self.assertTrue((self.media / invoice.file.name).is_file())
        from PIL import Image

        for fmt, name in (("PNG", "scan.png"), ("JPEG", "scan.jpg"), ("WEBP", "scan.webp")):
            buffer = io.BytesIO()
            Image.new("RGB", (20, 20), "white").save(buffer, fmt)
            picture = services.create_from_upload(upload(buffer.getvalue(), name), user=None)
            self.assertEqual(picture.reading_state, ReadingState.FAILED)  # kept, but there is no text to read
            self.assertIn("PDF", picture.reading["error"])

    def test_wrong_files_are_refused(self) -> None:
        with self.assertRaises(ValidationError):
            services.create_from_upload(upload(b"hello", "rechnung.txt"), user=None)
        with self.assertRaises(ValidationError):
            services.create_from_upload(upload(b"<html>", "rechnung.pdf"), user=None)  # a PDF by name only
        with self.assertRaises(ValidationError):
            services.create_from_upload(upload(b"\x89PNG not really", "scan.png"), user=None)
        with self.assertRaises(ValidationError):
            services.create_from_upload(upload(b"", "leer.pdf"), user=None)
        self.assertFalse(IncomingInvoice.objects.exists())

    def test_a_file_that_is_too_large_is_refused(self) -> None:
        """The size limit is the one the administrators set for documents (NFA-007)."""
        from rentalars.core.models import SystemSettings

        limits = SystemSettings.load()
        limits.max_upload_mb = 1
        limits.save()
        big = pdf_of(INCOMING_LINES) + b"\n%" + b"x" * (1024 * 1024)
        with self.assertRaises(ValidationError) as caught:
            services.create_from_upload(upload(big), user=None)
        self.assertIn("zu groß", " ".join(caught.exception.messages))
        self.assertFalse(IncomingInvoice.objects.exists())
        self.assertTrue(services.create_from_upload(upload(), user=None).pk)

    def test_the_same_file_twice_is_noticed(self) -> None:
        first = services.create_from_upload(upload(), user=None)
        second = services.create_from_upload(upload(), user=None)
        self.assertEqual(services.duplicates(second), [first])
        # The same supplier and number are noticed without the same file.
        third = make_invoice()
        services.update_head(third, {"supplier_name": first.supplier_label, "invoice_number": first.invoice_number})
        self.assertIn(first, services.duplicates(third))


class ReadingTests(FilesMixin, AIMixin, RentalarsTestCase):
    """KI-Erkennung von Rechnungsnummer, -Datum, Lieferant, Preis: patterns without the AI, the model with it."""

    def test_the_text_gives_number_date_due_date_supplier_and_totals(self) -> None:
        Supplier.objects.create(name="Musikhaus Muster GmbH & Co. KG")
        invoice = services.create_from_upload(upload(), user=None)
        self.assertEqual(
            (invoice.invoice_number, invoice.invoice_date, invoice.due_date),
            ("RE-2027-0815", datetime.date(2027, 2, 22), datetime.date(2027, 3, 22)),
        )
        self.assertEqual(invoice.supplier.name, "Musikhaus Muster GmbH & Co. KG")
        self.assertEqual((invoice.total_net, invoice.total_gross), (Decimal("377.00"), Decimal("448.63")))
        self.assertEqual(
            (invoice.total_tax, invoice.reading_state, invoice.reading["source"]), (Decimal("71.63"), "done", "text")
        )
        self.assertFalse(invoice.positions.exists())  # the positions need the AI

    def test_an_unknown_supplier_is_proposed_by_name_and_created_on_request(self) -> None:
        invoice = services.create_from_upload(upload(), user=None)
        self.assertIsNone(
            invoice.supplier
        )  # only a supplier of the master data is found in the text; the AI names others
        services.update_head(invoice, {"supplier_name": "Musikhaus Muster GmbH & Co. KG"})
        self.assertIsNone(invoice.supplier)
        supplier = services.create_supplier(invoice)
        invoice.refresh_from_db()
        self.assertEqual((invoice.supplier, supplier.name), (supplier, "Musikhaus Muster GmbH & Co. KG"))
        self.assertEqual(Supplier.objects.filter(name=supplier.name).count(), 1)
        with self.assertRaises(ValidationError):
            services.create_supplier(IncomingInvoice(supplier_name=""))

    def test_a_scan_is_kept_and_says_why_it_is_not_read(self) -> None:
        invoice = services.create_from_upload(upload(scanned_pdf()), user=None)
        self.assertEqual(invoice.reading_state, ReadingState.FAILED)
        self.assertIn("Scan", invoice.reading["error"])
        self.assertTrue(invoice.file.name)

    def test_the_proposal_never_overwrites_what_was_typed(self) -> None:
        invoice = make_invoice()
        invoice.invoice_number = "MEINE-NR"
        invoice.save()
        reading.apply_proposal(invoice, reading.proposal_from_text(reading.text_of(invoice)))
        invoice.refresh_from_db()
        self.assertEqual((invoice.invoice_number, invoice.invoice_date), ("MEINE-NR", datetime.date(2027, 2, 22)))

    def test_ancillary_words_are_recognised(self) -> None:
        for word in ("Fracht", "Versandkosten", "Verpackung", "Zoll", "Shipping", "Porto"):
            self.assertTrue(reading.looks_like_ancillary(word), word)
        self.assertFalse(reading.looks_like_ancillary("Shure SM58"))
        self.assertEqual(reading.position_type_of("", "Versandkosten"), PositionType.ANCILLARY)
        self.assertEqual(reading.position_type_of("other", "Pfand"), PositionType.OTHER)

    def test_the_ai_reads_the_positions_and_marks_the_freight(self) -> None:
        """MAT-062 with the fake model: positions, quantities, prices, the freight as ancillary cost."""
        mic = make_model("Shure SM58", category_code="T", manufacturer="Shure")
        self.reading_on(answer_of())
        invoice = services.create_from_upload(upload(), user=None)
        invoice.refresh_from_db()
        self.assertEqual((invoice.reading_state, invoice.reading["source"]), ("done", "ai"))
        self.assertTrue(invoice.reading["ai"]["model"])
        rows = [
            (p.place, p.description, p.quantity, p.unit_price_net, p.position_type)
            for p in invoice.positions.order_by("place")
        ]
        self.assertEqual(
            rows,
            [
                (1, "Shure SM58", Decimal("3.000"), Decimal("99.0000"), PositionType.GOODS),
                (2, "Neutrik NL4 Kabel 10 m", Decimal("2.000"), Decimal("25.0000"), PositionType.GOODS),
                (3, "Fracht und Verpackung", Decimal("1.000"), Decimal("30.0000"), PositionType.ANCILLARY),
            ],
        )
        self.assertEqual(invoice.positions.get(place=1).material_model, mic)  # matched, not created
        self.assertEqual((invoice.invoice_number, invoice.total_net), ("RE-2027-0815", Decimal("377.00")))
        self.assertEqual(AICall.objects.count(), 1)  # one question, to the provider chosen for invoices
        # Reading again keeps what was corrected in the head and replaces the unbooked positions.
        services.update_head(invoice, {"note": "Mikrofone für die Sommertour"})
        services.start_reading(invoice, user=None)
        invoice.refresh_from_db()
        self.assertEqual(invoice.note, "Mikrofone für die Sommertour")
        self.assertEqual(invoice.positions.count(), 3)

    def test_an_answer_the_program_cannot_use_leaves_the_text_reading(self) -> None:
        self.reading_on("this is not json")
        invoice = services.create_from_upload(upload(), user=None)
        invoice.refresh_from_db()
        self.assertEqual(invoice.invoice_number, "RE-2027-0815")
        self.assertTrue(invoice.reading["error"])
        self.assertFalse(invoice.positions.exists())

    def test_a_booked_position_survives_a_new_reading(self) -> None:
        self.reading_on(answer_of())
        invoice = services.create_from_upload(upload(), user=None)
        invoice.refresh_from_db()
        mic_position = invoice.positions.get(place=1)
        services.update_position(mic_position, {"asset_kind": AssetKind.LOW_VALUE})
        model = make_model("Shure SM58", category_code="T")
        made = booking.book(invoice, [booking.Entry(position=mic_position, model=model)], rights=ALL_RIGHTS, user=None)
        self.assertEqual(len(made.items), 3)
        services.start_reading(invoice, user=None)
        invoice.refresh_from_db()
        self.assertTrue(InvoicePosition.objects.filter(pk=mic_position.pk).exists())
        self.assertEqual(MaterialItem.objects.filter(source_position=mic_position).count(), 3)


# --- Changing the register ---------------------------------------------------------------------------------------


class ChangeTests(FilesMixin, RentalarsTestCase):
    """Everything can be corrected; the note and the status are kept; a booked position keeps its values."""

    def test_the_head_can_be_corrected(self) -> None:
        invoice = make_invoice()
        services.update_head(
            invoice,
            {
                "supplier_name": "Neuer Händler",
                "invoice_number": "X-1",
                "invoice_date": datetime.date(2027, 3, 1),
                "due_date": datetime.date(2027, 3, 15),
                "total_net": Decimal("100.00"),
                "total_tax": Decimal("19.00"),
                "total_gross": Decimal("119.00"),
                "note": "Für die Messe",
                "status": InvoiceStatus.CHECKED,
                "currency": "eur",
            },
        )
        invoice.refresh_from_db()
        self.assertEqual(
            (invoice.supplier_name, invoice.note, invoice.status, invoice.currency),
            ("Neuer Händler", "Für die Messe", "checked", "EUR"),
        )
        with self.assertRaises(ValidationError):
            services.update_head(invoice, {"status": "nonsense"})
        with self.assertRaises(ValidationError):
            services.update_head(invoice, {"exchange_rate": Decimal("0")})
        with self.assertRaises(ValidationError):
            services.update_head(invoice, {"invoice_number": "x" * 61})  # MariaDB would refuse it; SQLite does not
        invoice.refresh_from_db()
        self.assertEqual(invoice.invoice_number, "X-1")

    def test_a_known_supplier_is_linked_by_name(self) -> None:
        supplier = Supplier.objects.create(name="Musikhaus Muster")
        invoice = make_invoice()
        services.update_head(invoice, {"supplier_name": "musikhaus muster"})
        self.assertEqual((invoice.supplier, invoice.supplier_label), (supplier, "Musikhaus Muster"))

    def test_positions_are_added_changed_and_removed(self) -> None:
        invoice = make_invoice()
        first = add(invoice, "Kabel", "2", "5.00")
        second = add(invoice, "Fracht", "1", "4.00", position_type=PositionType.ANCILLARY)
        self.assertEqual((first.place, second.place), (1, 2))
        services.update_position(first, {"quantity": Decimal("4"), "tax_rate": Decimal("19")})
        first.refresh_from_db()
        self.assertEqual((first.quantity, first.line_net), (Decimal("4.000"), Decimal("20.0000")))
        services.delete_position(first)
        second.refresh_from_db()
        self.assertEqual(second.place, 1)
        with self.assertRaises(ValidationError):
            add(invoice, "x" * 251, "1", "1.00")
        with self.assertRaises(ValidationError):
            add(invoice, "Rabatt", "1", "-1.00")  # only ancillary costs may be negative

    def test_at_most_a_hundred_positions(self) -> None:
        invoice = make_invoice()
        for number in range(100):
            InvoicePosition.objects.create(invoice=invoice, place=number + 1, description=f"P{number}")
        with self.assertRaises(ValidationError):
            add(invoice, "Zu viel", "1", "1.00")

    def test_a_booked_position_keeps_quantity_price_and_type(self) -> None:
        invoice, mic, _cable = goods_invoice()
        model = make_model("Shure SM58", category_code="T")
        booking.book(invoice, [booking.Entry(position=mic, model=model)], rights=ALL_RIGHTS, user=None)
        with self.assertRaises(ValidationError):
            services.update_position(mic, {"quantity": Decimal("5")})
        with self.assertRaises(ValidationError):
            services.update_position(mic, {"unit_price_net": Decimal("1.00")})
        with self.assertRaises(ValidationError):
            services.delete_position(mic)
        services.update_position(mic, {"description": "Shure SM58 LCE"})  # a description may be corrected
        with self.assertRaises(ValidationError):
            services.delete_invoice(invoice)
        self.assertTrue(IncomingInvoice.objects.filter(pk=invoice.pk).exists())

    def test_deleting_an_invoice_removes_its_file(self) -> None:
        invoice = make_invoice()
        add(invoice, "Kabel", "1", "1.00")
        stored = self.media / invoice.file.name
        self.assertTrue(stored.is_file())
        with self.captureOnCommitCallbacks(execute=True):
            services.delete_invoice(invoice)
        self.assertFalse(IncomingInvoice.objects.exists())
        self.assertFalse(InvoicePosition.objects.exists())
        self.assertFalse(stored.exists())

    def test_the_history_tells_what_happened(self) -> None:
        from rentalars.core.audit import acting_as

        user = make_user("anna")
        invoice = make_invoice()
        with acting_as(user):
            services.update_head(invoice, {"note": "Neu", "total_net": Decimal("12.00")})
            position = add(invoice, "Pult", "1", "12.00")
            model = make_model("Pult", category_code="T")
            booking.book(invoice, [booking.Entry(position=position, model=model)], rights=ALL_RIGHTS, user=user)
        entries = AuditLogEntry.for_object(invoice)
        changed = [entry for entry in entries if "note" in entry.changes]
        self.assertEqual(changed[0].changes["note"], ["", "Neu"])
        self.assertEqual(changed[0].actor, user)
        self.assertTrue(any(entry.event == "incoming_invoice.booked" for entry in entries))
        self.assertTrue(
            any(entry.object_repr.startswith("1. Pult") for entry in entries)
        )  # positions: in the invoice's history


# --- Booking in ---------------------------------------------------------------------------------------------------


class BookingTests(FilesMixin, RentalarsTestCase):
    """Items from the goods positions: preview, then the items with their acquisition cost and their origin."""

    def setUp(self) -> None:
        super().setUp()
        self.invoice, self.mic_position, self.cable_position = goods_invoice()
        services.update_head(
            self.invoice,
            {"supplier_name": "Musikhaus Muster", "invoice_number": "RE-9", "invoice_date": datetime.date(2027, 2, 22)},
        )
        self.mic = make_model("Shure SM58", category_code="T", manufacturer="Shure")

    def entries(self, **mic: object) -> list[booking.Entry]:
        return [booking.Entry(position=self.mic_position, model=self.mic, **mic)]

    def test_the_preview_shows_the_figures_and_creates_nothing(self) -> None:
        plan = booking.plan(self.invoice, self.entries(), rights=ALL_RIGHTS)
        self.assertTrue(plan.ok, plan.problems)
        row = plan.rows[0]
        self.assertEqual(
            (row.count, row.price, row.share, row.total), (3, Decimal("297.00"), Decimal("25.68"), Decimal("322.68"))
        )
        self.assertEqual((row.kind, row.useful_life, row.per_piece), (AssetKind.LOW_VALUE, None, Decimal("107.56")))
        self.assertEqual(plan.piece_count, 3)
        self.assertFalse(MaterialItem.objects.exists())

    def test_booking_creates_the_items_with_cost_kind_and_origin(self) -> None:
        made = booking.book(self.invoice, self.entries(serial_numbers=["A1", "A2", "A3"]), rights=ALL_RIGHTS, user=None)
        items = list(MaterialItem.objects.order_by("inventory_number"))
        self.assertEqual(len(items), 3)
        self.assertEqual(made.by_position[self.mic_position.pk], items)
        self.assertEqual([item.serial_number for item in items], ["A1", "A2", "A3"])
        # Documented fields the books build on: asset_kind, useful_life_months, acquisition_cost_net, purchase_date …
        self.assertEqual(sum(item.purchase_price for item in items), Decimal("297.00"))
        self.assertEqual(sum(item.ancillary_cost_net for item in items), Decimal("25.68"))
        self.assertEqual(sum(item.acquisition_cost_net for item in items), Decimal("322.68"))
        self.assertEqual([item.acquisition_cost_net for item in items], [Decimal("107.56")] * 3)
        for item in items:
            self.assertEqual((item.asset_kind, item.useful_life_months), (AssetKind.LOW_VALUE, None))
            self.assertEqual(
                (item.source_position, item.purchase_date), (self.mic_position, datetime.date(2027, 2, 22))
            )
            self.assertEqual((item.invoice_number, item.supplier.name), ("RE-9", "Musikhaus Muster"))
        # The original is attached to each item like the invoice of "Kauf einpflegen".
        self.assertEqual(MaterialFile.objects.filter(item=items[0]).count(), 1)
        self.assertEqual(self.invoice.positions.get(pk=self.mic_position.pk).items.count(), 3)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.supplier.name, "Musikhaus Muster")

    def test_odd_cents_stay_with_the_first_pieces(self) -> None:
        invoice = make_invoice()
        add(invoice, "Kabel", "3", "10.00")
        add(invoice, "Fracht", "1", "0.10", position_type=PositionType.ANCILLARY)
        position = invoice.positions.get(place=1)
        model = make_model("Kabel", category_code="K")
        booking.book(invoice, [booking.Entry(position=position, model=model)], rights=ALL_RIGHTS, user=None)
        shares = [item.ancillary_cost_net for item in MaterialItem.objects.order_by("inventory_number")]
        self.assertEqual(shares, [Decimal("0.04"), Decimal("0.03"), Decimal("0.03")])

    def test_a_fixed_asset_gets_a_useful_life(self) -> None:
        invoice = make_invoice()
        pult = add(invoice, "Mischpult", "1", "1500.00", asset_kind=AssetKind.FIXED_ASSET, useful_life_months=84)
        model = make_model("Mischpult", category_code="T")
        booking.book(invoice, [booking.Entry(position=pult, model=model)], rights=ALL_RIGHTS, user=None)
        item = MaterialItem.objects.get()
        self.assertEqual(
            (item.asset_kind, item.useful_life_months, item.acquisition_cost_net),
            (AssetKind.FIXED_ASSET, 84, Decimal("1500.00")),
        )

    def test_the_kind_of_asset_has_to_be_confirmed_and_the_limit_only_proposes(self) -> None:
        """Without a chosen kind the plan stops and names the proposal; with it the booking goes through."""
        invoice = make_invoice()
        pult = add(invoice, "Mischpult", "1", "1500.00", asset_kind="")
        model = make_model("Mischpult", category_code="T")
        entry = booking.Entry(position=pult, model=model)
        plan = booking.plan(invoice, [entry], rights=ALL_RIGHTS)
        self.assertFalse(plan.ok)
        self.assertIn("Art des Wirtschaftsguts", " ".join(plan.rows[0].problems))
        with self.assertRaises(ValidationError):
            booking.book(invoice, [entry], rights=ALL_RIGHTS, user=None)
        self.assertFalse(MaterialItem.objects.exists())
        services.update_position(pult, {"asset_kind": AssetKind.MERCHANDISE})
        self.assertTrue(booking.plan(invoice, [booking.Entry(position=pult, model=model)], rights=ALL_RIGHTS).ok)

    def test_a_new_model_is_created_with_its_category(self) -> None:
        entry = booking.Entry(
            position=self.cable_position,
            new_model=purchases.NewModel(name="Neutrik NL4 10 m", category=category("K"), manufacturer="Neutrik"),
        )
        made = booking.book(self.invoice, [entry], rights=ALL_RIGHTS, user=None)
        self.assertEqual([model.name for model in made.new_models], ["Neutrik NL4 10 m"])
        self.assertEqual(MaterialItem.objects.count(), 2)

    def test_bulk_material_becomes_one_row_with_a_quantity(self) -> None:
        bulk = make_model("Gaffa schwarz", category_code="K", bulk=True)
        invoice = make_invoice()
        tape = add(invoice, "Gaffa schwarz", "20", "6.00")
        add(invoice, "Fracht", "1", "12.00", position_type=PositionType.ANCILLARY)
        made = booking.book(invoice, [booking.Entry(position=tape, model=bulk)], rights=ALL_RIGHTS, user=None)
        item = MaterialItem.objects.get()
        self.assertEqual(made.items, [item])
        self.assertEqual(item.quantity, 20)
        self.assertEqual(
            (item.purchase_price, item.ancillary_cost_net, item.acquisition_cost_net),
            (Decimal("120.00"), Decimal("12.00"), Decimal("132.00")),
        )
        self.assertEqual(item.source_position, tape)

    def test_a_position_is_not_booked_twice_by_accident(self) -> None:
        booking.book(self.invoice, self.entries(), rights=ALL_RIGHTS, user=None)
        plan = booking.plan(self.invoice, self.entries(), rights=ALL_RIGHTS)
        self.assertFalse(plan.ok)
        self.assertTrue(
            any("3 of 3" in text or "3 von 3" in text for text in plan.rows[0].problems), plan.rows[0].problems
        )
        with self.assertRaises(ValidationError):
            booking.book(self.invoice, self.entries(), rights=ALL_RIGHTS, user=None)
        self.assertEqual(MaterialItem.objects.count(), 3)
        again = booking.book(self.invoice, self.entries(book_again=True, count=1), rights=ALL_RIGHTS, user=None)
        self.assertEqual(len(again.items), 1)
        self.assertEqual(MaterialItem.objects.count(), 4)

    def test_a_partial_booking_is_completed_later_with_the_cost_of_the_rest(self) -> None:
        first = booking.book(self.invoice, self.entries(count=1), rights=ALL_RIGHTS, user=None)
        self.assertEqual(len(first.items), 1)
        second = booking.book(self.invoice, self.entries(), rights=ALL_RIGHTS, user=None)  # the 2 pieces that are left
        self.assertEqual(len(second.items), 2)
        items = list(MaterialItem.objects.order_by("inventory_number"))
        self.assertEqual(sum(item.acquisition_cost_net for item in items), Decimal("322.68"))
        self.assertEqual([item.purchase_price for item in items], [Decimal("99.00")] * 3)

    def test_more_pieces_than_the_quantity_keep_the_amount_of_the_position(self) -> None:
        """A position typed by hand is one piece; the pieces chosen here share its net amount."""
        typed = add(self.invoice, "Mischpult", "1", "300.00")
        entry = booking.Entry(position=typed, model=self.mic, count=3)
        plan = booking.plan(self.invoice, [entry], rights=ALL_RIGHTS)
        self.assertEqual((plan.rows[0].count, plan.rows[0].price), (3, Decimal("300.00")))
        typed.refresh_from_db()
        self.assertEqual(
            (typed.quantity, typed.unit_price_net), (Decimal("1.000"), Decimal("300.00"))
        )  # a preview writes nothing
        booking.book(self.invoice, [entry], rights=ALL_RIGHTS, user=None)
        typed.refresh_from_db()
        self.assertEqual((typed.quantity, typed.unit_price_net), (Decimal("3.000"), Decimal("100.0000")))
        items = list(MaterialItem.objects.filter(source_position=typed))
        self.assertEqual([item.purchase_price for item in items], [Decimal("100.00")] * 3)

    def test_the_invoice_is_booked_in_when_all_goods_are(self) -> None:
        booking.book(self.invoice, self.entries(), rights=ALL_RIGHTS, user=None)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, InvoiceStatus.OPEN)  # the cables are still missing
        entry = booking.Entry(position=self.cable_position, model=make_model("Neutrik NL4 10 m", category_code="K"))
        booking.book(self.invoice, [entry], rights=ALL_RIGHTS, user=None)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, InvoiceStatus.BOOKED_IN)

    def test_problems_stop_the_booking_and_nothing_is_made(self) -> None:
        nothing = booking.plan(self.invoice, [], rights=ALL_RIGHTS)
        self.assertFalse(nothing.ok)
        no_model = booking.plan(self.invoice, [booking.Entry(position=self.mic_position)], rights=ALL_RIGHTS)
        self.assertFalse(no_model.ok)
        ancillary = self.invoice.positions.get(position_type=PositionType.ANCILLARY)
        wrong = booking.plan(self.invoice, [booking.Entry(position=ancillary, model=self.mic)], rights=ALL_RIGHTS)
        self.assertFalse(wrong.ok)
        twice = booking.plan(self.invoice, self.entries() + self.entries(), rights=ALL_RIGHTS)
        self.assertFalse(twice.ok)
        other = make_invoice()
        foreign = add(other, "Fremd", "1", "1.00")
        self.assertFalse(
            booking.plan(self.invoice, [booking.Entry(position=foreign, model=self.mic)], rights=ALL_RIGHTS).ok
        )
        with self.assertRaises(ValidationError):
            booking.book(self.invoice, [booking.Entry(position=self.mic_position)], rights=ALL_RIGHTS, user=None)
        self.assertFalse(MaterialItem.objects.exists())
        # A failure in the middle leaves nothing behind (all or nothing): the second row has no model.
        with self.assertRaises(ValidationError):
            booking.book(
                self.invoice,
                [*self.entries(), booking.Entry(position=self.cable_position)],
                rights=ALL_RIGHTS,
                user=None,
            )
        self.assertFalse(MaterialItem.objects.exists())

    def test_customer_material_is_refused(self) -> None:
        """The rule of "Kauf einpflegen" (PRD-043): what is bought is the company's, never customer material."""
        held = category("K")
        held.is_customer_material = True
        held.save()
        model = make_model("Kundenkabel", category_code="K")
        plan = booking.plan(self.invoice, [booking.Entry(position=self.cable_position, model=model)], rights=ALL_RIGHTS)
        self.assertFalse(plan.ok)
        self.assertTrue(any("Kundenmaterial" in problem for problem in plan.rows[0].problems), plan.rows[0].problems)

    def test_a_foreign_currency_costs_what_the_rate_says(self) -> None:
        services.update_head(self.invoice, {"currency": "USD", "exchange_rate": Decimal("0.5")})
        plan = booking.plan(self.invoice, self.entries(), rights=ALL_RIGHTS)
        self.assertEqual(plan.rows[0].price, Decimal("148.50"))
        services.update_head(self.invoice, {"exchange_rate": Decimal("1")})
        self.assertTrue(booking.plan(self.invoice, self.entries(), rights=ALL_RIGHTS).ok)

    def test_the_price_right_is_needed(self) -> None:
        rights = writer_without_prices()
        self.assertFalse(access.may_see(rights))
        plan = booking.plan(self.invoice, self.entries(), rights=rights)
        self.assertFalse(plan.ok)
        self.assertFalse(MaterialItem.objects.exists())


def writer_without_prices() -> Rights:
    """The rights of a user who writes the material but may not see purchase prices."""
    user = make_user("mw")
    user.roles.add(material_writer())
    return rights_of(user)


class FilterTests(FilesMixin, RentalarsTestCase):
    """Supplier, date range, status and text search – for the page and the API alike."""

    def setUp(self) -> None:
        super().setUp()
        self.muster = Supplier.objects.create(name="Musikhaus Muster")
        self.other = Supplier.objects.create(name="Kabel-Meyer")
        self.a = make_invoice()
        services.update_head(
            self.a,
            {
                "supplier_name": "Musikhaus Muster",
                "invoice_number": "A-1",
                "invoice_date": datetime.date(2027, 1, 10),
                "note": "Tournee",
            },
        )
        self.b = services.create_from_upload(
            upload(pdf_of(("Kabel-Meyer", "Rechnung Nr. B-2", "Rechnungsdatum: 05.03.2027"))), user=None
        )
        services.update_head(self.b, {"supplier_name": "Kabel-Meyer", "status": InvoiceStatus.CHECKED})
        add(self.b, "Mikrofonkabel", "1", "9.00")

    def found(self, **params: str) -> list[IncomingInvoice]:
        parsed = filters.parse(params)
        self.assertEqual(parsed.errors, {})
        return list(parsed.apply(filters.invoices()).order_by("pk"))

    def test_each_filter(self) -> None:
        self.assertEqual(self.found(), [self.a, self.b])
        self.assertEqual(self.found(supplier=str(self.muster.pk)), [self.a])
        self.assertEqual(self.found(status="checked"), [self.b])
        self.assertEqual(self.found(since="2027-02-01"), [self.b])
        self.assertEqual(self.found(until="2027-02-01"), [self.a])
        self.assertEqual(self.found(since="2027-03-05", until="2027-03-05"), [self.b])
        self.assertEqual(self.found(q="tournee"), [self.a])  # the note
        self.assertEqual(self.found(q="mikrofonkabel"), [self.b])  # a position, once even with several hits
        self.assertEqual(self.found(q="B-2"), [self.b])
        self.assertEqual(self.found(q="meyer", status="checked"), [self.b])
        self.assertEqual(self.found(q="meyer", status="open"), [])

    def test_bad_values_are_named(self) -> None:
        errors = filters.parse({"supplier": "x", "status": "?", "since": "yesterday"}).errors
        self.assertEqual(set(errors), {"supplier", "status", "since"})

    def test_totals_convert_other_currencies(self) -> None:
        services.update_head(
            self.a, {"total_net": Decimal("100.00"), "total_tax": Decimal("19.00"), "total_gross": Decimal("119.00")}
        )
        services.update_head(
            self.b,
            {
                "total_net": Decimal("10.00"),
                "total_tax": Decimal("1.90"),
                "total_gross": Decimal("11.90"),
                "currency": "USD",
                "exchange_rate": Decimal("0.5"),
            },
        )
        found = filters.totals(filters.invoices())
        self.assertEqual(
            (found.count, found.net, found.tax, found.gross, found.foreign),
            (2, Decimal("105.00"), Decimal("19.95"), Decimal("124.95"), 1),
        )

    def test_sums_say_when_they_leave_invoices_out(self) -> None:
        """A foreign currency without a rate and an invoice without amounts are named, not silently missing."""
        services.update_head(
            self.a, {"total_net": Decimal("100.00"), "total_tax": Decimal("19.00"), "total_gross": Decimal("119.00")}
        )
        found = filters.totals(filters.invoices())
        self.assertEqual((found.missing_rate, found.without_amount, found.incomplete), (0, 1, True))  # b has none
        services.update_head(
            self.b,
            {"total_net": Decimal("10.00"), "total_tax": Decimal("1.90"), "total_gross": Decimal("11.90"),
             "currency": "USD", "exchange_rate": None},
        )  # fmt: skip
        found = filters.totals(filters.invoices())
        self.assertEqual((found.missing_rate, found.without_amount, found.incomplete), (1, 0, True))
        self.assertEqual((found.count, found.net, found.foreign), (2, Decimal("100.00"), 1))
        services.update_head(self.b, {"exchange_rate": Decimal("0.5")})
        found = filters.totals(filters.invoices())
        self.assertEqual((found.missing_rate, found.without_amount, found.incomplete), (0, 0, False))


# --- The pages ----------------------------------------------------------------------------------------------------


class PagesTests(FilesMixin, AIMixin, UiTestCase):
    """The pages in Buchhaltung: list, upload, detail, ancillary costs, booking in, settings."""

    def setUp(self) -> None:
        super().setUp()
        self.mic = make_model("Shure SM58", category_code="T", manufacturer="Shure")

    def upload(self, name: str = "rechnung.pdf", content: bytes | None = None) -> object:
        return self.client.post(reverse("incoming:upload"), {"file": upload(content, name)}, follow=True)

    def test_upload_reads_and_opens_the_invoice(self) -> None:
        response = self.upload()
        invoice = IncomingInvoice.objects.get()
        self.assertEqual(response.redirect_chain[-1][0], f"{reverse('incoming:detail', args=[invoice.pk])}?asked=book")
        text = self.assert_ok(response)
        self.assertIn("RE-2027-0815", text)
        self.assertIn("aus dem Text gelesen", text)
        self.assertIn("377,00", text.replace("\xa0", " "))

    def test_wrong_files_are_refused_with_a_message(self) -> None:
        response = self.upload("rechnung.txt", b"hello")
        self.assertFalse(IncomingInvoice.objects.exists())
        self.assertTrue(self.messages_of(response))
        response = self.client.post(reverse("incoming:upload"), {}, follow=True)
        self.assertTrue(self.messages_of(response))

    def test_the_list_filters_and_shows_sums(self) -> None:
        self.upload()
        invoice = IncomingInvoice.objects.get()
        services.update_head(invoice, {"note": "Sommertour", "status": InvoiceStatus.CHECKED})
        other = make_invoice()
        services.update_head(
            other, {"supplier_name": "Anderer", "invoice_number": "ZZ-9", "invoice_date": datetime.date(2026, 1, 1)}
        )
        page = self.assert_ok(self.client.get(reverse("incoming:list")))
        self.assertIn("RE-2027-0815", page)
        self.assertIn("ZZ-9", page)
        only = self.assert_ok(self.client.get(reverse("incoming:list"), {"q": "Sommertour"}))
        self.assertIn("RE-2027-0815", only)
        self.assertNotIn("ZZ-9", only)
        by_status = self.assert_ok(self.client.get(reverse("incoming:list"), {"status": "open"}))
        self.assertIn("ZZ-9", by_status)
        self.assertNotIn("RE-2027-0815", by_status)
        by_date = self.assert_ok(
            self.client.get(reverse("incoming:list"), {"since": "2027-01-01", "until": "2027-12-31"})
        )
        self.assertNotIn("ZZ-9", by_date)
        self.assertIn("Sommertour", self.assert_ok(self.client.get(reverse("incoming:list"))))  # the note column

    def test_the_sums_say_when_they_are_incomplete(self) -> None:
        """An invoice in dollars without a rate is counted but not summed – and the page says so."""
        invoice = make_invoice()
        services.update_head(
            invoice, {"total_net": Decimal("10.00"), "total_tax": Decimal("1.90"), "total_gross": Decimal("11.90"),
                      "currency": "USD", "exchange_rate": None}
        )  # fmt: skip
        page = self.assert_ok(self.client.get(reverse("incoming:list")))
        self.assertIn("Die Summen sind unvollständig", page)
        self.assertIn("keinen Wechselkurs", page)
        services.update_head(invoice, {"exchange_rate": Decimal("0.5")})
        self.assertNotIn("Die Summen sind unvollständig", self.assert_ok(self.client.get(reverse("incoming:list"))))

    def test_the_original_can_be_downloaded(self) -> None:
        self.upload()
        invoice = IncomingInvoice.objects.get()
        response = self.client.get(reverse("incoming:file", args=[invoice.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("rechnung.pdf", response["Content-Disposition"])
        self.assertIn("sandbox", response["Content-Security-Policy"])

    def test_correct_the_head_note_status_and_positions(self) -> None:
        self.upload()
        invoice = IncomingInvoice.objects.get()
        url = reverse("incoming:detail", args=[invoice.pk])
        page = self.client.get(url)
        data = form_data(page, containing="invoice_number")
        data.update(
            {
                "invoice_number": "RE-KORRIGIERT",
                "note": "Mikrofone für die Sommertour",
                "status": "checked",
                "pos-TOTAL_FORMS": "0",
                "pos-INITIAL_FORMS": "0",
            }
        )
        response = self.client.post(url, data, follow=True)
        self.assertIn("Die Rechnung ist gespeichert.", self.messages_of(response))
        invoice.refresh_from_db()
        self.assertEqual(
            (invoice.invoice_number, invoice.note, invoice.status),
            ("RE-KORRIGIERT", "Mikrofone für die Sommertour", "checked"),
        )
        # "Another position" saves and shows an empty row; filling it adds a position.
        data["action"] = "add"
        self.client.post(url, data)
        page = self.client.get(url, {"new": "1"})
        data = form_data(page, containing="invoice_number")
        data.update(
            {
                "pos-0-description": "Shure SM58",
                "pos-0-amount_net": "297,00",
                "pos-0-position_type": "goods",
            }
        )
        self.assertEqual(self.client.post(url, data).status_code, 302)
        position = invoice.positions.get()
        # The row asks for the net amount of the position; a new one is one piece at that amount.
        self.assertEqual(
            (position.description, position.quantity, position.unit_price_net),
            ("Shure SM58", Decimal("1.000"), Decimal("297.00")),
        )

    def test_a_wrong_value_is_shown_and_nothing_is_saved(self) -> None:
        self.upload()
        invoice = IncomingInvoice.objects.get()
        url = reverse("incoming:detail", args=[invoice.pk])
        data = form_data(self.client.get(url), containing="invoice_number")
        data.update({"currency": "EURO", "pos-TOTAL_FORMS": "0", "pos-INITIAL_FORMS": "0"})
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("has-error", response.content.decode())
        invoice.refresh_from_db()
        self.assertEqual(invoice.currency, "EUR")

    def test_ancillary_costs_are_shown_and_the_key_changes_the_preview(self) -> None:
        invoice, _mic, _cable = goods_invoice(freight="10.00")
        page = self.assert_ok(self.client.get(reverse("incoming:detail", args=[invoice.pk])))
        self.assertIn("Anschaffungskosten", page)
        self.assertIn('hx-get="' + reverse("incoming:costing", args=[invoice.pk]) + '"', page)
        by_value = self.htmx("get", reverse("incoming:costing", args=[invoice.pk]), {"allocation_key": "value"})
        self.assertIn("8,56", by_value.content.decode().replace("\xa0", " "))  # 297/347 * 10
        by_quantity = self.htmx("get", reverse("incoming:costing", args=[invoice.pk]), {"allocation_key": "quantity"})
        self.assertIn("6,00", by_quantity.content.decode().replace("\xa0", " "))
        invoice.refresh_from_db()
        self.assertEqual(invoice.allocation_key, AllocationKey.VALUE)  # nothing was saved

    def test_book_in_with_preview_and_confirmation(self) -> None:
        invoice, mic_position, _cable = goods_invoice()
        url = reverse("incoming:book", args=[invoice.pk])
        page = self.client.get(url)
        data = form_data(page, containing="pos-0-position")
        self.assertEqual(data["pos-0-model_name"], "Shure SM58")
        data.pop("pos-1-include", None)
        data.update({"action": "preview"})
        preview = self.client.post(url, data)
        text = self.assert_ok(preview)
        self.assertIn("322,68", text.replace("\xa0", " "))
        self.assertIn("Ja, genau so einpflegen", text)
        self.assertFalse(MaterialItem.objects.exists())
        # Without the confirmation nothing is made.
        data.update({"action": "book"})
        refused = self.client.post(url, data)
        self.assertFalse(MaterialItem.objects.exists())
        self.assertTrue(any("Vorschau" in message for message in self.messages_of(refused)))
        data.update({"confirmed": "1"})
        done = self.client.post(url, data, follow=True)
        self.assertEqual(MaterialItem.objects.filter(source_position=mic_position).count(), 3)
        self.assertTrue(any("Eingepflegt" in message for message in self.messages_of(done)))
        # The detail page names the items made of the position, and a second go is stopped.
        self.assertIn("eingepflegt", self.assert_ok(self.client.get(reverse("incoming:detail", args=[invoice.pk]))))
        fresh = form_data(self.client.get(url), containing="pos-0-position")
        fresh.update({"action": "preview", "pos-0-include": "on"})
        fresh.pop("pos-1-include", None)
        self.assertIn("schon eingepflegt", self.client.post(url, fresh).content.decode())

    def test_an_item_shows_where_it_came_from(self) -> None:
        invoice, mic_position, _cable = goods_invoice()
        booking.book(invoice, [booking.Entry(position=mic_position, model=self.mic)], rights=ALL_RIGHTS, user=None)
        item = MaterialItem.objects.first()
        assert item is not None
        page = self.assert_ok(self.client.get(reverse("material:item_detail", args=[item.pk])))
        self.assertIn("107,56", page.replace("\xa0", " "))

    def test_status_and_delete(self) -> None:
        invoice = make_invoice()
        self.client.post(reverse("incoming:status", args=[invoice.pk]), {"status": "booked_in"})
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "booked_in")
        bad = self.client.post(reverse("incoming:status", args=[invoice.pk]), {"status": "nonsense"}, follow=True)
        self.assertTrue(self.messages_of(bad))
        self.assertEqual(self.client.get(reverse("incoming:delete", args=[invoice.pk])).status_code, 405)
        self.client.post(reverse("incoming:delete", args=[invoice.pk]))
        self.assertFalse(IncomingInvoice.objects.exists())

    def test_create_the_supplier(self) -> None:
        self.upload()
        invoice = IncomingInvoice.objects.get()
        services.update_head(invoice, {"supplier_name": "Neuer Händler GmbH"})
        self.assertIn(
            "Lieferanten anlegen", self.assert_ok(self.client.get(reverse("incoming:detail", args=[invoice.pk])))
        )
        self.client.post(reverse("incoming:create_supplier", args=[invoice.pk]))
        invoice.refresh_from_db()
        self.assertEqual(invoice.supplier.name, "Neuer Händler GmbH")

    def test_reading_with_the_ai_runs_as_a_job_and_the_page_polls(self) -> None:
        self.reading_on(answer_of())
        response = self.upload()
        invoice = IncomingInvoice.objects.get()
        self.assertEqual(invoice.positions.count(), 3)
        text = self.assert_ok(response)
        self.assertIn("von der KI gelesen", text)
        poll = self.htmx("get", reverse("incoming:reading", args=[invoice.pk]))
        self.assertEqual(poll.status_code, 200)
        read_again = self.client.post(reverse("incoming:read", args=[invoice.pk]), follow=True)
        self.assertEqual(read_again.status_code, 200)

    def test_settings(self) -> None:
        url = reverse("incoming:settings")
        page = self.assert_ok(self.client.get(url))
        self.assertIn("800,00", page.replace("\xa0", " "))
        data = form_data(self.client.get(url), containing="low_value_limit_net")
        data.update({"low_value_limit_net": "250,00", "default_useful_life_months": "36"})
        self.client.post(url, data)
        settings = AssetSettings.load()
        self.assertEqual((settings.low_value_limit_net, settings.default_useful_life_months), (Decimal("250.00"), 36))
        data.update({"default_useful_life_months": "0"})
        self.assertEqual(self.client.post(url, data).status_code, 200)

    def test_rights(self) -> None:
        invoice = make_invoice()
        reader = self.browser_for("paula", "Projektleitung")  # reads material and purchase prices, writes nothing
        for name, args, expected in (
            ("list", [], 200),
            ("detail", [invoice.pk], 200),
            ("file", [invoice.pk], 200),
            ("book", [invoice.pk], 403),
        ):
            self.assertEqual(reader.get(reverse(f"incoming:{name}", args=args)).status_code, expected, name)
        for name in ("upload", "read", "status", "delete", "create_supplier"):
            args = [] if name == "upload" else [invoice.pk]
            self.assertEqual(reader.post(reverse(f"incoming:{name}", args=args), {}).status_code, 403, name)
        self.assertEqual(reader.get(reverse("incoming:costing", args=[invoice.pk])).status_code, 200)
        # No material, or no purchase prices: not even the list.
        mats_user = make_user("mats")
        mats_user.roles.add(material_writer())  # writes the material but sees no purchase prices
        crew = self.browser_for("fritz", "Freie Kraft")
        for blind in (self.browser_of(mats_user), crew):
            for name, args in (
                ("list", []),
                ("detail", [invoice.pk]),
                ("file", [invoice.pk]),
                ("costing", [invoice.pk]),
            ):
                self.assertEqual(blind.get(reverse(f"incoming:{name}", args=args)).status_code, 403, name)
        warehouse = self.browser_for("luka", "Lager")  # writes the material: may upload and change, not delete
        self.assertEqual(warehouse.get(reverse("incoming:list")).status_code, 200)
        self.assertEqual(warehouse.get(reverse("incoming:book", args=[invoice.pk])).status_code, 200)
        self.assertEqual(warehouse.post(reverse("incoming:delete", args=[invoice.pk])).status_code, 403)
        self.assertEqual(warehouse.get(reverse("incoming:settings")).status_code, 403)  # settings: Administration
        self.assertTrue(IncomingInvoice.objects.filter(pk=invoice.pk).exists())
        self.assertEqual(self.client.get(reverse("incoming:detail", args=[999999])).status_code, 404)

    def test_the_navigation_of_buchhaltung_has_the_tab(self) -> None:
        page = self.assert_ok(self.client.get(reverse("incoming:list")))
        self.assertIn("Eingangsbelege", page)
        self.assertIn(reverse("incoming:list"), self.assert_ok(self.client.get(reverse("documents:outgoing"))))


# --- The API -------------------------------------------------------------------------------------------------------


class IncomingApiTests(FilesMixin, AIMixin, ApiTestCase):
    """API-014: every operation of the pages through the API, with rights and errors."""

    def setUp(self) -> None:
        super().setUp()
        self.luka = self.client_for("luka", "Lager")
        self.mic = make_model("Shure SM58", category_code="T", manufacturer="Shure")

    def post_invoice(self, client: object = None, **extra: object) -> dict:
        response = (client or self.luka).post(
            f"{API}/incoming-invoices", {"file": upload(), **extra}, format="multipart"
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_upload_read_and_show(self) -> None:
        Supplier.objects.create(name="Musikhaus Muster GmbH & Co. KG")
        body = self.post_invoice()
        self.assertEqual(
            (body["invoice_number"], body["invoice_date"], body["due_date"]),
            ("RE-2027-0815", "2027-02-22", "2027-03-22"),
        )
        self.assertEqual(
            (body["total_net"], body["total_tax"], body["total_gross"], body["currency"]),
            ("377.00", "71.63", "448.63", "EUR"),
        )
        self.assertEqual(
            (body["reading"]["source"], body["supplier_name"], body["status"]),
            ("text", "Musikhaus Muster GmbH & Co. KG", "open"),
        )
        shown = self.luka.get(f"{API}/incoming-invoices/{body['id']}").json()
        self.assertEqual(shown["positions"], [])
        self.assertEqual(shown["duplicates"], [])
        # Only kept: not read.
        kept = self.post_invoice(read="false")
        self.assertEqual(
            (kept["invoice_number"], kept["reading_state"], kept["duplicates"]), ("", "none", [body["id"]])
        )

    def test_the_file_is_downloadable_and_wrong_files_are_refused(self) -> None:
        body = self.post_invoice()
        response = self.luka.get(body["file_url"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(self.luka.post(f"{API}/incoming-invoices", {}, format="multipart").status_code, 400)
        bad = self.luka.post(f"{API}/incoming-invoices", {"file": upload(b"hello", "x.txt")}, format="multipart")
        self.assert_error(bad, 400, "validation_error", "file")
        fake = self.luka.post(f"{API}/incoming-invoices", {"file": upload(b"<html>", "x.pdf")}, format="multipart")
        self.assert_error(fake, 400, "validation_error", "file")

    def test_the_list_filters_sorts_and_totals(self) -> None:
        supplier = Supplier.objects.create(name="Kabel-Meyer")
        first = self.post_invoice()
        second = self.post_invoice(read="false")
        patched = self.luka.patch(
            f"{API}/incoming-invoices/{second['id']}",
            {
                "supplier_name": "Kabel-Meyer",
                "invoice_number": "B-2",
                "invoice_date": "2027-03-05",
                "total_net": "10.00",
                "total_tax": "1.90",
                "total_gross": "11.90",
                "status": "checked",
                "note": "Tourkabel",
            },
            format="json",
        )
        self.assertEqual(patched.status_code, 200, patched.content)
        listed = self.luka.get(f"{API}/incoming-invoices").json()
        self.assertEqual(
            [row["id"] for row in listed["results"]], [second["id"], first["id"]]
        )  # newest invoice date first
        self.assertEqual(listed["results"][0]["position_count"], 0)
        self.assertEqual(
            [r["id"] for r in self.luka.get(f"{API}/incoming-invoices?status=checked").json()["results"]],
            [second["id"]],
        )
        self.assertEqual(
            [r["id"] for r in self.luka.get(f"{API}/incoming-invoices?q=tourkabel").json()["results"]], [second["id"]]
        )
        self.assertEqual(
            [r["id"] for r in self.luka.get(f"{API}/incoming-invoices?until=2027-03-01").json()["results"]],
            [first["id"]],
        )
        by_number = self.luka.get(f"{API}/incoming-invoices?sort=-invoice_number").json()["results"]
        self.assertEqual([r["invoice_number"] for r in by_number], ["RE-2027-0815", "B-2"])
        self.assert_error(self.luka.get(f"{API}/incoming-invoices?sort=nonsense"), 400, "validation_error", "sort")
        self.assert_error(self.luka.get(f"{API}/incoming-invoices?since=gestern"), 400, "validation_error", "since")
        totals = self.luka.get(f"{API}/incoming-invoices/totals").json()
        self.assertEqual((totals["count"], totals["net_total"], totals["gross_total"]), (2, "387.00", "460.53"))
        by_supplier = self.luka.get(f"{API}/incoming-invoices?supplier={supplier.pk}").json()["results"]
        self.assertEqual([r["id"] for r in by_supplier], [second["id"]])

    def test_correct_everything_note_status_and_delete(self) -> None:
        body = self.post_invoice()
        url = f"{API}/incoming-invoices/{body['id']}"
        supplier = Supplier.objects.create(name="Musikhaus Muster")
        changed = self.luka.patch(
            url,
            {
                "supplier": supplier.pk,
                "invoice_number": "NEU",
                "currency": "usd",
                "exchange_rate": "0.9",
                "note": "Für Messe",
                "status": "checked",
                "allocation_key": "quantity",
                "due_date": None,
            },
            format="json",
        )
        self.assertEqual(changed.status_code, 200, changed.content)
        data = changed.json()
        self.assertEqual(
            (
                data["supplier"],
                data["invoice_number"],
                data["currency"],
                data["exchange_rate"],
                data["note"],
                data["status"],
                data["allocation_key"],
                data["due_date"],
            ),
            (supplier.pk, "NEU", "USD", "0.900000", "Für Messe", "checked", "quantity", None),
        )
        for bad in (
            {"status": "x"},
            {"currency": "EURO"},
            {"allocation_key": "x"},
            {"invoice_date": "morgen"},
            {"exchange_rate": "-1"},
        ):
            self.assertEqual(self.luka.patch(url, bad, format="json").status_code, 400, bad)
        self.assertEqual(self.admin.delete(url).status_code, 204)  # deleting needs the delete level
        self.assertEqual(self.luka.get(url).status_code, 404)

    def test_positions_and_ancillary_costs(self) -> None:
        body = self.post_invoice()
        url = f"{API}/incoming-invoices/{body['id']}"
        first = self.luka.post(
            f"{url}/positions",
            {"description": "Shure SM58", "quantity": "3", "unit_price_net": "99.00", "weight_kg": "0.3"},
            format="json",
        )
        self.assertEqual(first.status_code, 201, first.content)
        second = self.luka.post(
            f"{url}/positions",
            {"description": "Neutrik NL4 Kabel 10 m", "quantity": "2", "unit_price_net": "25.00"},
            format="json",
        ).json()
        freight = self.luka.post(
            f"{url}/positions",
            {"description": "Fracht", "unit_price_net": "30.00", "position_type": "ancillary"},
            format="json",
        ).json()
        self.assertEqual((first.json()["place"], second["place"], freight["place"]), (1, 2, 3))
        self.assertEqual(first.json()["line_net"], "297.00")
        self.assertEqual(len(self.luka.get(f"{url}/positions").json()), 3)
        one = self.luka.get(f"{url}/positions/{second['id']}").json()
        self.assertEqual(one["description"], "Neutrik NL4 Kabel 10 m")
        patched = self.luka.patch(
            f"{url}/positions/{second['id']}", {"asset_kind": "merchandise", "tax_rate": "19"}, format="json"
        )
        self.assertEqual((patched.json()["asset_kind"], patched.json()["tax_rate"]), ("merchandise", "19.00"))
        cost = self.luka.get(f"{url}/costing").json()
        self.assertEqual(
            (cost["allocation_key"], cost["ancillary_total"], cost["goods_total"], cost["total"]),
            ("value", "30.00", "347.00", "377.00"),
        )
        rows = {row["position"]: row for row in cost["positions"]}
        self.assertEqual(
            (
                rows[first.json()["id"]]["ancillary_share"],
                rows[first.json()["id"]]["per_piece"],
                rows[first.json()["id"]]["asset_kind"],
            ),
            ("25.68", "107.56", "low_value"),
        )
        self.assertEqual(rows[second["id"]]["asset_kind"], "merchandise")
        by_quantity = self.luka.get(f"{url}/costing?allocation_key=quantity").json()
        self.assertEqual(
            {row["position"]: row["ancillary_share"] for row in by_quantity["positions"]},
            {first.json()["id"]: "18.00", second["id"]: "12.00"},
        )
        self.assert_error(
            self.luka.get(f"{url}/costing?allocation_key=nonsense"), 400, "validation_error", "allocation_key"
        )
        self.assertEqual(self.luka.get(f"{url}").json()["allocation_key"], "value")  # the preview saved nothing
        for bad in (
            {"description": ""},
            {"description": "x", "quantity": "-1"},
            {"description": "x", "position_type": "?"},
            {"description": "x", "unit_price_net": "-1"},
        ):
            self.assertEqual(self.luka.post(f"{url}/positions", bad, format="json").status_code, 400, bad)
        self.assertEqual(self.luka.delete(f"{url}/positions/{freight['id']}").status_code, 204)
        self.assertEqual(self.luka.get(f"{url}/positions/{freight['id']}").status_code, 404)
        other = self.post_invoice()
        self.assertEqual(
            self.luka.get(f"{API}/incoming-invoices/{other['id']}/positions/{second['id']}").status_code, 404
        )

    def invoice_with_positions(self) -> tuple[str, dict]:
        invoice, mic, cable = goods_invoice()
        return f"{API}/incoming-invoices/{invoice.pk}", {"mic": mic.pk, "cable": cable.pk}

    def test_book_with_preview_and_confirmation(self) -> None:
        url, ids = self.invoice_with_positions()
        body = {
            "positions": [{"position": ids["mic"], "material_model": self.mic.pk, "serial_numbers": ["A", "B", "C"]}]
        }
        preview = self.luka.post(f"{url}/book", body, format="json")
        self.assertEqual(preview.status_code, 200, preview.content)
        data = preview.json()
        self.assertFalse(data["confirmed"])
        self.assertTrue(data["preview"]["ok"], data["preview"])
        row = data["preview"]["rows"][0]
        self.assertEqual(
            (row["count"], row["net"], row["ancillary_share"], row["acquisition_cost"], row["asset_kind"]),
            (3, "297.00", "25.68", "322.68", "low_value"),
        )
        self.assertFalse(MaterialItem.objects.exists())
        done = self.luka.post(f"{url}/book", {**body, "confirm": True}, format="json")
        self.assertEqual(done.status_code, 201, done.content)
        made = done.json()
        self.assertEqual([item["acquisition_cost_net"] for item in made["items"]], ["107.56"] * 3)
        self.assertEqual({item["position"] for item in made["items"]}, {ids["mic"]})
        self.assertEqual([p["booked_items"] for p in made["invoice"]["positions"]][:1], [3])
        # The item API shows the same figures, and the invoice it came from.
        item = self.luka.get(f"{API}/material-items/{made['items'][0]['id']}").json()
        self.assertEqual(
            (
                item["acquisition_cost_net"],
                item["ancillary_cost_net"],
                item["asset_kind"],
                item["source_position"],
                item["source_invoice"],
            ),
            ("107.56", "8.56", "low_value", ids["mic"], int(url.rsplit("/", 1)[1])),
        )
        # A second go is stopped in the preview and refused with the confirmation.
        again = self.luka.post(f"{url}/book", body, format="json").json()["preview"]
        self.assertFalse(again["ok"])
        self.assertEqual(self.luka.post(f"{url}/book", {**body, "confirm": True}, format="json").status_code, 400)
        self.assertEqual(MaterialItem.objects.count(), 3)
        forced = self.luka.post(
            f"{url}/book",
            {
                "positions": [{"position": ids["mic"], "material_model": self.mic.pk, "book_again": True, "count": 1}],
                "confirm": True,
            },
            format="json",
        )
        self.assertEqual(forced.status_code, 201)
        self.assertEqual(MaterialItem.objects.count(), 4)

    def test_book_a_new_model_a_kind_and_a_useful_life(self) -> None:
        url, ids = self.invoice_with_positions()
        body = {
            "positions": [
                {
                    "position": ids["cable"],
                    "new_model": {"name": "Neutrik NL4 10 m", "category": category("K").pk, "keep_as_quantity": True},
                    "asset_kind": "fixed_asset",
                    "useful_life_months": 24,
                }
            ],
            "confirm": True,
        }
        done = self.luka.post(f"{url}/book", body, format="json")
        self.assertEqual(done.status_code, 201, done.content)
        item = done.json()["items"][0]
        self.assertEqual(
            (item["asset_kind"], item["useful_life_months"], item["purchase_price"]), ("fixed_asset", 24, "50.00")
        )
        model = MaterialModel.objects.get(pk=done.json()["new_models"][0])
        self.assertTrue(model.is_bulk)
        self.assertEqual(MaterialItem.objects.get().quantity, 2)
        # The choice stays with the position.
        position = self.luka.get(f"{url}/positions/{ids['cable']}").json()
        self.assertEqual(
            (position["asset_kind"], position["useful_life_months"], position["booked_pieces"]), ("fixed_asset", 24, 2)
        )

    def test_book_refusals(self) -> None:
        url, ids = self.invoice_with_positions()
        _other, other_ids = self.invoice_with_positions()
        for body in (
            {"positions": []},
            {"positions": [{"position": ids["mic"]}]},
            {
                "positions": [
                    {
                        "position": ids["mic"],
                        "material_model": self.mic.pk,
                        "new_model": {"name": "X", "category": category("K").pk},
                    }
                ]
            },
            {"positions": [{"position": other_ids["mic"], "material_model": self.mic.pk}]},
            {"positions": [{"position": 999999, "material_model": self.mic.pk}]},
        ):
            self.assertEqual(
                self.luka.post(f"{url}/book", {**body, "confirm": True}, format="json").status_code, 400, body
            )
        ancillary = InvoicePosition.objects.get(position_type="ancillary", invoice_id=int(url.rsplit("/", 1)[1]))
        refused = self.luka.post(
            f"{url}/book",
            {"positions": [{"position": ancillary.pk, "material_model": self.mic.pk}], "confirm": True},
            format="json",
        )
        self.assertEqual(refused.status_code, 400)
        self.assertFalse(MaterialItem.objects.exists())
        # Items were made: neither the position nor the invoice can be deleted.
        self.luka.post(
            f"{url}/book",
            {"positions": [{"position": ids["mic"], "material_model": self.mic.pk}], "confirm": True},
            format="json",
        )
        self.assertEqual(self.luka.delete(f"{url}/positions/{ids['mic']}").status_code, 400)
        self.assertEqual(self.admin.delete(url).status_code, 400)
        self.assertEqual(
            self.luka.patch(f"{url}/positions/{ids['mic']}", {"quantity": "9"}, format="json").status_code, 400
        )

    def test_read_again_and_create_the_supplier(self) -> None:
        body = self.post_invoice()
        url = f"{API}/incoming-invoices/{body['id']}"
        self.assert_error(self.luka.post(f"{url}/supplier"), 400, "validation_error", "supplier_name")  # no name yet
        self.luka.patch(url, {"supplier_name": "Musikhaus Muster GmbH & Co. KG"}, format="json")
        created = self.luka.post(f"{url}/supplier")
        self.assertEqual(created.status_code, 200)
        supplier = created.json()["supplier"]
        self.assertEqual(Supplier.objects.get(pk=supplier).name, "Musikhaus Muster GmbH & Co. KG")
        self.reading_on(answer_of())
        again = self.luka.post(f"{url}/read")
        self.assertEqual(again.status_code, 200, again.content)
        self.assertEqual([p["position_type"] for p in again.json()["positions"]], ["goods", "goods", "ancillary"])
        self.assertEqual(again.json()["reading"]["source"], "ai")
        cost = self.luka.get(f"{url}/costing").json()
        self.assertEqual(cost["total"], "377.00")

    def test_reading_with_the_ai_through_the_api(self) -> None:
        self.reading_on(answer_of())
        body = self.post_invoice()
        self.assertEqual(body["reading_state"], "done")
        self.assertEqual(len(body["positions"]), 3)
        self.assertIsNotNone(body["reading_job"])
        job = self.luka.get(f"{API}/jobs/{body['reading_job']}").json()
        self.assertEqual(job["status"], "done")

    def test_settings(self) -> None:
        self.assertEqual(
            self.admin.get(f"{API}/incoming-settings").json(),
            {"low_value_limit_net": "800.00", "default_useful_life_months": 60, "keep_memory_value": False},
        )
        changed = self.admin.patch(f"{API}/incoming-settings", {"low_value_limit_net": "250.00"}, format="json")
        self.assertEqual(
            changed.json(),
            {"low_value_limit_net": "250.00", "default_useful_life_months": 60, "keep_memory_value": False},
        )
        self.assertEqual(
            self.admin.patch(f"{API}/incoming-settings", {"default_useful_life_months": 0}, format="json").status_code,
            400,
        )
        self.assertEqual(self.luka.get(f"{API}/incoming-settings").status_code, 403)  # Administration
        self.assertEqual(
            self.luka.patch(f"{API}/incoming-settings", {"low_value_limit_net": "1"}, format="json").status_code, 403
        )

    def test_rights(self) -> None:
        body = self.post_invoice()
        url = f"{API}/incoming-invoices/{body['id']}"
        reader = self.client_for("paula", "Projektleitung")  # reads material and purchase prices, writes nothing
        for path in (
            "",
            "/totals",
            f"/{body['id']}",
            f"/{body['id']}/file",
            f"/{body['id']}/costing",
            f"/{body['id']}/positions",
        ):
            self.assertEqual(reader.get(f"{API}/incoming-invoices{path}").status_code, 200, path)
        self.assertEqual(
            reader.post(f"{API}/incoming-invoices", {"file": upload()}, format="multipart").status_code, 403
        )
        for path in ("read", "supplier", "book", "positions"):
            self.assertEqual(reader.post(f"{url}/{path}", {}, format="json").status_code, 403, path)
        self.assertEqual(reader.patch(url, {"note": "x"}, format="json").status_code, 403)
        self.assertEqual(reader.delete(url).status_code, 403)
        # Without material or purchase prices nothing is open, not even to look at.
        mats_user = make_user("mats")
        mats_user.roles.add(material_writer())
        for blind in (self.client_of(mats_user), self.client_for("fritz", "Freie Kraft")):
            for path in (
                "",
                "/totals",
                f"/{body['id']}",
                f"/{body['id']}/file",
                f"/{body['id']}/costing",
                f"/{body['id']}/positions",
            ):
                self.assertEqual(blind.get(f"{API}/incoming-invoices{path}").status_code, 403, path)
            self.assertEqual(
                blind.post(f"{API}/incoming-invoices", {"file": upload()}, format="multipart").status_code, 403
            )
            self.assertEqual(blind.patch(url, {"note": "x"}, format="json").status_code, 403)
        # The warehouse changes but does not delete (AUT-036); an administrator does.
        self.assertEqual(self.luka.patch(url, {"note": "x"}, format="json").status_code, 200)
        self.assertEqual(self.luka.delete(url).status_code, 403)
        self.assertEqual(self.admin.delete(url).status_code, 204)
        self.assertEqual(Client().get(f"{API}/incoming-invoices").status_code, 401)

    def test_the_cost_fields_of_an_item_need_the_price_right(self) -> None:
        invoice = IncomingInvoice.objects.get(pk=self.post_invoice()["id"])
        add(invoice, "Shure SM58", "1", "99.00")
        booking.book(
            invoice, [booking.Entry(position=invoice.positions.get(), model=self.mic)], rights=ALL_RIGHTS, user=None
        )
        item = MaterialItem.objects.get()
        mats_user = make_user("mats")
        mats_user.roles.add(material_writer())
        seen = self.client_of(mats_user).get(f"{API}/material-items/{item.pk}").json()
        self.assertNotIn("acquisition_cost_net", seen)
        self.assertNotIn("ancillary_cost_net", seen)
        self.assertEqual((seen["asset_kind"], seen["source_invoice"]), ("low_value", invoice.pk))
        priced = self.luka.get(f"{API}/material-items/{item.pk}").json()
        self.assertEqual(priced["acquisition_cost_net"], "99.00")

    def test_a_reader_token_cannot_change(self) -> None:
        """A token restricted to reading may look but not change (API-006)."""
        user = make_user("tom", roles=("Lager",))
        readonly = self.client_of(user, read_only=True)
        body = self.post_invoice()
        self.assertEqual(readonly.get(f"{API}/incoming-invoices/{body['id']}").status_code, 200)
        self.assertEqual(
            readonly.patch(f"{API}/incoming-invoices/{body['id']}", {"note": "x"}, format="json").status_code, 403
        )

    def test_the_schema_describes_the_operations(self) -> None:
        schema = self.admin.get(f"{API}/schema?format=json")
        self.assertEqual(schema.status_code, 200)
        paths = json.loads(schema.content)["paths"]
        for path in (
            "/api/v1/incoming-invoices",
            "/api/v1/incoming-invoices/totals",
            "/api/v1/incoming-invoices/{id}",
            "/api/v1/incoming-invoices/{id}/file",
            "/api/v1/incoming-invoices/{id}/costing",
            "/api/v1/incoming-invoices/{id}/book",
            "/api/v1/incoming-invoices/{id}/positions/{position_pk}",
            "/api/v1/incoming-settings",
        ):
            self.assertIn(path, paths)
        self.assertEqual(set(paths["/api/v1/incoming-invoices/{id}"]) - {"parameters"}, {"get", "patch", "delete"})
