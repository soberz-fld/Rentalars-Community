# SPDX-License-Identifier: GPL-3.0-or-later
"""The old invoices – descriptions of the positions, material / personnel / logistics, customers (PRJ-130).

* The description of a position is taken over: the AI answer's ``details``, the lines below a position in the text, and
  the part of a long first line that does not fit the title.
* A position is material, personnel or logistics: the AI says it, else words and unit guess it; the preview shows it
  and changes it. Personnel becomes a crew line (hours, days or a flat rate), logistics a vehicle booking with a trip at
  a flat rate, and the historic invoice is printed in the divisions Material, Personnel, Logistics.
* Customers are recognised by the VAT ID, the name, and now the address with a similar name.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from django.urls import reverse

from rentalars.ai.legacy_invoices import parse_answer
from rentalars.customers.models import Customer
from rentalars.documents.models import Document
from rentalars.projects import legacy_draft as drafts
from rentalars.projects import legacy_import, legacy_text
from rentalars.projects.legacy_draft import CustomerPart, Draft, Line
from rentalars.projects.legacy_models import LegacyImportBatch
from rentalars.projects.models import CrewBilling, Project
from tests.helpers import job_function, make_customer, ready_for_invoices
from tests.ui.base import UiTestCase, forms_of
from tests.unit.test_100_legacy_import import AIMixin, FilesMixin, ImportCase, invoice_pdf, upload


def answer(positions: list[dict[str, Any]]) -> str:
    """An answer of the model with the given positions."""
    return json.dumps(
        {
            "customer": {"name": "Beispielburg Stadtwerke AG"},
            "invoice_number": "2023-0042",
            "invoice_date": "2023-06-15",
            "currency": "EUR",
            "tax_rate": 19,
            "total_net": "1.000,00",
            "positions": positions,
        }
    )


def make_vehicle(name: str = "Sprinter") -> Any:
    """A motor vehicle of the fleet (a vehicle product)."""
    from rentalars.products.models import ProductKind, VehicleType
    from tests.helpers import make_product

    return make_product(
        "V-901",
        name,
        price=None,
        kind=ProductKind.VEHICLE,
        vehicle_type=VehicleType.CAR,
        price_per_km=Decimal("1.00"),
    )


class DescriptionTests(ImportCase):
    """The text of a position is not lost."""

    def test_the_details_of_the_answer_are_the_description(self) -> None:
        draft = parse_answer(
            answer(
                [
                    {
                        "description": "Funkmikrofon-Set",
                        "details": "Sennheiser EW 100\ninkl. Akkus",
                        "quantity": "2",
                        "unit": "Stk",
                        "unit_price": "500,00",
                        "amount": "1.000,00",
                    }
                ]
            )
        )
        (line,) = draft.lines
        self.assertEqual((line.title, line.note), ("Funkmikrofon-Set", "Sennheiser EW 100\ninkl. Akkus"))

    def test_a_description_in_the_first_line_goes_to_the_note_and_nothing_is_cut(self) -> None:
        long_text = "Funkmikrofon-Set " + "mit Zubehör und allem was dazugehört " * 12
        draft = parse_answer(
            answer([{"description": long_text + "\nZweite Zeile", "unit_price": "10,00", "amount": "10,00"}])
        )
        (line,) = draft.lines
        self.assertLessEqual(len(line.title), 200)
        self.assertTrue(line.title.startswith("Funkmikrofon-Set"))
        joined = " ".join((line.title + " " + line.note).split())
        self.assertIn("Zweite Zeile", line.note)
        self.assertEqual(joined.replace("Zweite Zeile", "").strip(), " ".join(long_text.split()))

    def test_title_and_details_splits_lines_and_a_long_first_line(self) -> None:
        self.assertEqual(drafts.title_and_details("A\n\n B \nC"), ("A", "B\nC"))
        self.assertEqual(drafts.title_and_details(None), ("", ""))
        title, rest = drafts.title_and_details("wort " * 60, 30)
        self.assertLessEqual(len(title), 30)
        self.assertEqual(" ".join((title + " " + rest).split()), ("wort " * 60).strip())

    def test_lines_below_a_position_in_the_text_are_its_description(self) -> None:
        text = (
            "Bezeichnung Menge Einzelpreis Gesamt\n"
            "Funkmikrofon-Set 2 Stk 500,00 1.000,00\n"
            "Sennheiser EW 100 mit Handsender\n"
            "inkl. Akkus, Ladegerät und Koffer, Frequenzabstimmung vor Ort durch den Techniker, "
            + "Abstimmung mit dem Veranstaltungsort. "
            * 4
            + "\n"
            "Summe netto 1.000,00\n"
        )
        (line,) = legacy_text.positions_from_text(text)
        self.assertIn("Sennheiser EW 100", line.note)
        self.assertIn("Akkus", line.note)

    def test_the_description_is_edited_in_the_preview_and_kept_on_a_changed_title(self) -> None:
        previous = Draft(lines=[Line(title="Alt", note="Beschreibung", unit_price=Decimal("1"))])
        data = {
            "i1-lines-count": "1",
            "i1-l0-title": "Neu",
            "i1-l0-note": "Geänderte Beschreibung\nzweite Zeile",
            "i1-l0-quantity": "1",
            "i1-l0-unit_price": "1",
        }
        line = drafts.draft_from_post(data, "i1-", previous).lines[0]
        self.assertEqual(line.note, "Geänderte Beschreibung\nzweite Zeile")
        del data["i1-l0-note"]  # a form without the field keeps what was read
        self.assertEqual(drafts.draft_from_post(data, "i1-", previous).lines[0].note, "Beschreibung")

    def test_the_description_reaches_the_line_and_the_invoice_document(self) -> None:
        (item,) = self.items(self.batch_of(invoice_pdf()))
        draft = legacy_import.draft_of(item)
        draft.lines[0].note = "Mit Haltebügeln\nund Sicherungsseilen"
        legacy_import.save_draft(item, draft)
        (outcome,) = self.take(item)
        self.assertTrue(outcome.ok, outcome.errors)
        self.assertEqual(
            outcome.project.material_lines.order_by("position")[0].note, "Mit Haltebügeln\nund Sicherungsseilen"
        )
        content = Document.objects.get().content
        details = [
            position["details"]
            for section in content["sections"]
            for position in section["positions"]
            if position["details"]
        ]
        self.assertEqual(details, ["Mit Haltebügeln\nund Sicherungsseilen"])


class KindTests(ImportCase):
    """Material, personnel or logistics."""

    def test_words_and_units_guess_the_kind(self) -> None:
        guess = drafts.guess_kind
        self.assertEqual(guess("LED Scheinwerfer PAR 64", "Stk"), "material")
        self.assertEqual(guess("Tontechniker FOH", "Std"), "crew")
        self.assertEqual(guess("Helfer", "h"), "crew")
        self.assertEqual(guess("Transport Hin- und Rückfahrt", "pauschal"), "logistics")
        self.assertEqual(guess("Anfahrt", "km"), "logistics")
        self.assertEqual(guess("Mischpult, 3 Tage", "Tag"), "material")  # a rental per day is no hint
        self.assertEqual(guess("Sennheiser Funkstrecke", ""), "material")

    def test_the_answer_says_the_kind_and_a_wrong_word_is_ignored(self) -> None:
        draft = parse_answer(
            answer(
                [
                    {"description": "A", "kind": "personnel", "unit_price": "10,00", "amount": "10,00"},
                    {"description": "B", "kind": "Logistik", "unit_price": "10,00", "amount": "10,00"},
                    {"description": "C", "kind": "weird", "unit_price": "10,00", "amount": "10,00"},
                    {"description": "D", "unit_price": "10,00", "amount": "10,00"},
                ]
            )
        )
        self.assertEqual([line.kind for line in draft.lines], ["crew", "logistics", "", ""])

    def test_reading_proposes_kind_job_function_and_vehicle(self) -> None:
        function = job_function("Tontechniker", price="60.00")
        vehicle = make_vehicle()
        draft = Draft(
            lines=[
                Line(title="Tontechniker FOH", unit="Std", quantity=Decimal("8"), unit_price=Decimal("60")),
                Line(title="Transport zum Veranstaltungsort", unit="pauschal", unit_price=Decimal("150")),
                Line(title="Funkmikrofon", unit="Stk", unit_price=Decimal("20")),
                Line(title="Hinweis", is_text=True),
            ]
        )
        legacy_import.prepare(draft)
        crew, transport, material, text = draft.lines
        self.assertEqual((crew.kind, crew.job_function_id), ("crew", function.pk))
        self.assertEqual((transport.kind, transport.product_id), ("logistics", vehicle.pk))  # the only vehicle
        self.assertEqual((material.kind, material.job_function_id), ("material", None))
        self.assertEqual(text.kind, "")

    def test_the_kind_is_stored_and_changing_it_clears_what_was_chosen_for_the_old_one(self) -> None:
        function = job_function("Tontechniker", price="60.00")
        previous = Draft(
            lines=[Line(title="Aufbau", kind="crew", job_function_id=function.pk, unit_price=Decimal("1"))]
        )
        self.assertEqual(Draft.from_json(previous.to_json()).lines[0].job_function_id, function.pk)
        same = {
            "i1-lines-count": "1",
            "i1-l0-title": "Aufbau",
            "i1-l0-kind": "crew",
            "i1-l0-job_function": str(function.pk),
            "i1-l0-unit_price": "1",
        }
        self.assertEqual(drafts.draft_from_post(same, "i1-", previous).lines[0].job_function_id, function.pk)
        changed = {**same, "i1-l0-kind": "material"}
        line = drafts.draft_from_post(changed, "i1-", previous).lines[0]
        self.assertEqual((line.kind, line.job_function_id), ("material", None))

    def test_checks_ask_for_the_job_function_and_the_vehicle(self) -> None:
        make_vehicle()
        job_function("Tontechniker", price="60.00")
        (item,) = self.items(self.batch_of(invoice_pdf()))
        draft = legacy_import.draft_of(item)
        draft.lines[0].kind, draft.lines[0].job_function_id = "crew", None
        draft.lines[1].kind, draft.lines[1].product_id = "logistics", None
        report = legacy_import.check(draft, item, rights=self.rights, siblings=[item])
        keys = {issue.key for issue in report.errors}
        self.assertIn("lines.0.job_function", keys)
        self.assertIn("lines.1.product", keys)
        draft.lines[1].product_id = draft.lines[0].product_id = 999999  # not a vehicle
        draft.lines[0].kind = "logistics"
        report = legacy_import.check(draft, item, rights=self.rights, siblings=[item])
        self.assertEqual(
            {issue.key for issue in report.errors if issue.key.endswith("product")},
            {"lines.0.product", "lines.1.product"},
        )

    def test_personnel_hours_days_and_a_flat_rate(self) -> None:
        function = job_function("Tontechniker", price="60.00")
        (item,) = self.items(self.batch_of(invoice_pdf()))
        draft = legacy_import.draft_of(item)
        draft.lines = [
            Line(
                title="Tontechniker",
                note="FOH und Monitor",
                unit="Std",
                quantity=Decimal("8"),
                unit_price=Decimal("60"),
                tax_percent=Decimal("19"),
                kind="crew",
                job_function_id=function.pk,
            ),
            Line(
                title="Helfer",
                unit="Tag",
                quantity=Decimal("2"),
                unit_price=Decimal("300"),
                tax_percent=Decimal("19"),
                kind="crew",
                job_function_id=function.pk,
            ),
            Line(
                title="Betreuung",
                unit="pauschal",
                quantity=Decimal("3"),
                unit_price=Decimal("100"),
                discount=Decimal("10"),
                tax_percent=Decimal("19"),
                kind="crew",
                job_function_id=function.pk,
            ),
        ]
        draft.totals = drafts.Totals()
        legacy_import.save_draft(item, draft)
        report = legacy_import.check(draft, item, rights=self.rights, siblings=[item])
        self.assertTrue(any(issue.key == "lines.2.unit" for issue in report.warnings))  # a flat rate is pointed out
        (outcome,) = self.take(item)
        self.assertTrue(outcome.ok, outcome.errors)
        hours, days, flat = outcome.project.crew_lines.order_by("position")
        self.assertEqual(
            (hours.billing, hours.planned_hours, hours.unit_price, hours.note, hours.person, hours.job_function),
            (CrewBilling.PLAN, Decimal("8.00"), Decimal("60.00"), "FOH und Monitor", None, function),
        )
        self.assertEqual((days.billing, days.days, days.unit_price), (CrewBilling.DAY, 2, Decimal("300.00")))
        self.assertEqual(
            (flat.billing, flat.unit_price, flat.discount_percent),
            (CrewBilling.FLAT, Decimal("300.00"), Decimal("10.00")),
        )
        self.assertEqual(outcome.project.material_lines.count(), 0)

    def test_words_that_only_contain_a_staff_or_transport_word_are_material(self) -> None:
        """A desk ("Regiepult") and a case ("Transportcase") give no hint for personnel or logistics."""
        guess = drafts.guess_kind
        for title in ("Regiepult 32 Kanäle", "Transportcase für Lichtpult", "Personalcomputer", "Anhängerkupplung"):
            self.assertEqual(guess(title, "Stk"), "material", title)
        self.assertEqual(guess("Tag Miete Mischpult", "Tag"), "material")  # "per day" is no hint

    def test_a_negative_price_is_no_crew_or_logistics_line(self) -> None:
        """A credit has no crew billing; the preview says so instead of the import failing."""
        function = job_function("Techniker", price="55.00")
        vehicle = make_vehicle()
        (item,) = self.items(self.batch_of(invoice_pdf()))
        draft = legacy_import.draft_of(item)
        draft.lines = [
            Line(
                title="Gutschrift Personal",
                unit="Std",
                quantity=Decimal("2"),
                unit_price=Decimal("-50"),
                tax_percent=Decimal("19"),
                kind="crew",
                job_function_id=function.pk,
            ),
            Line(
                title="Gutschrift Transport",
                unit="pauschal",
                quantity=Decimal("1"),
                unit_price=Decimal("-80"),
                tax_percent=Decimal("19"),
                kind="logistics",
                product_id=vehicle.pk,
            ),
        ]
        draft.totals = drafts.Totals()
        report = legacy_import.check(draft, item, rights=self.rights, siblings=[item])
        self.assertEqual(
            sorted(issue.key for issue in report.errors if issue.key.endswith("unit_price")),
            ["lines.0.unit_price", "lines.1.unit_price"],
        )

    def test_logistics_is_a_vehicle_booking_with_a_flat_trip(self) -> None:
        from rentalars.projects import logistics
        from rentalars.projects.models import TripBilling

        vehicle = make_vehicle()
        (item,) = self.items(self.batch_of(invoice_pdf()))
        draft = legacy_import.draft_of(item)
        draft.lines = [
            Line(
                title="Transport hin und zurück",
                note="Sprinter mit Fahrer",
                unit="pauschal",
                quantity=Decimal("2"),
                unit_price=Decimal("150"),
                tax_percent=Decimal("19"),
                kind="logistics",
                product_id=vehicle.pk,
            )
        ]
        draft.totals = drafts.Totals()
        legacy_import.save_draft(item, draft)
        (outcome,) = self.take(item)
        self.assertTrue(outcome.ok, outcome.errors)
        project = outcome.project
        (booking,) = project.vehicle_lines.all()
        self.assertEqual(
            (booking.product, booking.title, booking.note), (vehicle, "Transport hin und zurück", "Sprinter mit Fahrer")
        )
        (use,) = project.trip_vehicles.all()
        self.assertEqual((use.billing, use.flat_price), (TripBilling.FLAT, Decimal("300.00")))
        self.assertTrue(use.trip_key.startswith("own-"))
        (price,) = logistics.price_logistics(project, logistics.load_logistics(project), {})
        self.assertEqual(price.base_amount, Decimal("300.00"))
        self.assertEqual(project.material_lines.count(), 0)

    def test_the_historic_invoice_has_the_three_divisions_and_the_import_can_be_undone(self) -> None:
        function = job_function("Techniker", price="55.00")
        vehicle = make_vehicle()
        (item,) = self.items(self.batch_of(invoice_pdf()))
        draft = legacy_import.draft_of(item)
        draft.lines = [
            Line(title="Hinweis zum Aufbau", is_text=True),
            Line(
                title="Mischpult",
                unit="Stk",
                quantity=Decimal("1"),
                unit_price=Decimal("180"),
                tax_percent=Decimal("19"),
            ),
            Line(
                title="Techniker",
                unit="Std",
                quantity=Decimal("6"),
                unit_price=Decimal("55"),
                tax_percent=Decimal("19"),
                kind="crew",
                job_function_id=function.pk,
            ),
            Line(
                title="Transport",
                unit="pauschal",
                quantity=Decimal("1"),
                unit_price=Decimal("100"),
                tax_percent=Decimal("19"),
                kind="logistics",
                product_id=vehicle.pk,
            ),
        ]
        draft.totals = drafts.Totals()
        legacy_import.save_draft(item, draft)
        (outcome,) = self.take(item)
        self.assertTrue(outcome.ok, outcome.errors)
        content = Document.objects.get().content
        sections = content["sections"]
        self.assertEqual(
            [(section["division"], [p["title"] for p in section["positions"]]) for section in sections],
            [
                ("material", ["Hinweis zum Aufbau", "Mischpult"]),
                ("personnel", ["Techniker"]),
                ("logistics", ["Transport"]),
            ],
        )
        self.assertEqual([section["subtotal"] for section in sections], ["180.00", "330.00", "100.00"])
        self.assertEqual(
            [p["number"] for section in sections for p in section["positions"] if not p.get("is_text")], ["1", "2", "3"]
        )
        # What the import made is its own: it can be taken back.
        batch = outcome.items[0].batch
        self.assertEqual(legacy_import.undo_problems(batch, user=self.user, rights=self.rights), [])
        legacy_import.undo(batch, user=self.user, rights=self.rights)
        self.assertFalse(Project.objects.exists())


class CustomerTests(ImportCase):
    """A customer is recognised – or created."""

    def test_the_same_address_and_a_similar_name_is_a_safe_match(self) -> None:
        customer = make_customer("Beispielburg Stadtwerke AG")
        customer.street, customer.postal_code, customer.city = "Rathausplatz 2", "54321", "Beispielburg"
        customer.save()
        part = CustomerPart(
            name="Stadtwerke Beispielburg", street="Rathausplatz 2", postal_code="54321", city="Beispielburg"
        )
        candidates = drafts.customer_candidates(part)
        self.assertEqual([(entry.customer_id, entry.certain) for entry in candidates], [(customer.pk, True)])
        self.assertEqual(drafts.best_customer(part).customer_id, customer.pk)

    def test_a_similar_name_elsewhere_is_only_offered(self) -> None:
        customer = make_customer("Beispielburg Stadtwerke AG")
        part = CustomerPart(name="Beispielburg Stadtwerke GmbH", street="Hauptstr. 1", postal_code="11111", city="X")
        candidates = drafts.customer_candidates(part)
        self.assertEqual([(entry.customer_id, entry.certain) for entry in candidates][:1], [(customer.pk, True)])
        other = CustomerPart(name="Beispielburg Stadtbetriebe", street="Hauptstr. 1", postal_code="11111", city="X")
        self.assertFalse(any(entry.certain for entry in drafts.customer_candidates(other)))

    def test_an_unknown_customer_is_created_from_the_invoice(self) -> None:
        self.assertFalse(Customer.objects.filter(name="Beispielburg Stadtwerke AG").exists())
        (item,) = self.items(self.batch_of(invoice_pdf()))
        self.assertIsNone(legacy_import.draft_of(item).customer.customer_id)
        (outcome,) = self.take(item)
        self.assertTrue(outcome.customer_created)
        self.assertEqual(outcome.customer.name, "Beispielburg Stadtwerke AG")


class PreviewPageTests(AIMixin, FilesMixin, UiTestCase):
    """The preview shows the description, the kind with what it needs, and what was found about the customer."""

    def setUp(self) -> None:
        super().setUp()
        ready_for_invoices()
        self.url = reverse("projects:legacy")

    def preview(self) -> tuple[str, LegacyImportBatch]:
        response = self.client.post(self.url, {"invoices": [upload("re.pdf", invoice_pdf())]}, follow=True)
        return self.assert_ok(response), LegacyImportBatch.objects.latest("pk")

    def form(self, batch: LegacyImportBatch, **changes: Any) -> dict[str, Any]:
        response = self.client.get(reverse("projects:legacy_batch", args=[batch.pk]))
        for candidate in forms_of(response):
            if any(key.endswith("lines-count") for key in candidate.data):
                data = {key: value for key, value in candidate.data.items() if key != "csrfmiddlewaretoken"}
                data.update(changes)
                return data
        raise AssertionError("No preview form on the page.")

    def test_description_kind_and_customer_are_on_the_page(self) -> None:
        page, batch = self.preview()
        self.assertIn(f'name="i{batch.items.get().pk}-l0-note"', page)
        self.assertIn(f'name="i{batch.items.get().pk}-l2-kind"', page)
        self.assertIn("Personal", page)
        self.assertIn("Kein bestehender Kunde passt. Aus den Daten der Rechnung wird ein neuer Kunde angelegt.", page)
        # "Techniker Aufbau, 6 Std" is personnel: the job function is offered, not a product
        self.assertIn(f'name="i{batch.items.get().pk}-l2-job_function"', page)

    def test_changing_the_kind_offers_what_the_new_kind_needs(self) -> None:
        _page, batch = self.preview()
        item = batch.items.get()
        make_vehicle()
        path = reverse("projects:legacy_batch", args=[batch.pk])
        data = self.form(batch)
        data[f"i{item.pk}-l0-kind"] = "logistics"
        data[f"i{item.pk}-l0-note"] = "Sprinter, 2 Fahrten"
        page = self.assert_ok(self.client.post(path, {**data, "action": "save"}, follow=True))
        self.assertIn(f'name="i{item.pk}-l0-product"', page)
        self.assertIn("Sprinter, 2 Fahrten", page)
        item.refresh_from_db()
        line = legacy_import.draft_of(item).lines[0]
        self.assertEqual((line.kind, line.note), ("logistics", "Sprinter, 2 Fahrten"))
        self.assertIsNotNone(line.product_id)  # the only vehicle is proposed
