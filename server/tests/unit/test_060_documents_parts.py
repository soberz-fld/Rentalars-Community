# SPDX-License-Identifier: GPL-3.0-or-later
"""Prices and documents of a whole project with its subprojects (PRJ-045, PRJ-046, PRJ-049, PRJ-060).

The festival of the catalogue: the whole project "Stadtfest" keeps the central
power supply itself; the stage "Marktplatz" has the lighting and programme
booklets, the stage "Schlosspark" the sound desk and takes over the lighting
from the Marktplatz. Billing happens at the whole project: one offer, one
order confirmation, one invoice for everything.

    Stadtfest          power supply (19 %)                       500,00
    Marktplatz         "Licht": 6 spotlights 20,00, 10 % off     108,00
                       programme booklets 5 × 10,00 (7 %)         50,00
    Schlosspark        6 spotlights taken over                     0,00
                       "Ton": sound desk (19 %)                  300,00
    ----------------------------------------------------------------------
    net 958,00 · 19 % on 908,00 = 172,52 · 7 % on 50,00 = 3,50 · gross 1.134,02
"""

from __future__ import annotations

import datetime
import xml.etree.ElementTree as ET
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from django.core.exceptions import ValidationError

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, ProjectScope, SpecialRight, rights_of
from rentalars.documents import datev, lexware, services
from rentalars.documents.content import from_json
from rentalars.documents.models import AccountingSettings, Document, DocumentKind
from rentalars.documents.pdf import render_html
from rentalars.documents.xrechnung import NAMESPACES
from rentalars.masterdata.models import TaxRate
from rentalars.projects import services as project_services
from rentalars.projects.family_prices import family_prices, sum_prices
from rentalars.projects.models import Project, ProjectAccessLevel, ProjectMembership, ProjectStatus
from rentalars.projects.price_pdf import render_price_overview_csv, render_price_overview_html
from rentalars.projects.pricing import ProjectPrices, TaxLine
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_group,
    add_line,
    at,
    make_customer,
    make_items,
    make_model,
    make_product,
    make_project,
    make_user,
    ready_for_invoices,
)
from tests.lexware_fake import voucher_problems

CAC, CBC = "{" + NAMESPACES["cac"] + "}", "{" + NAMESPACES["cbc"] + "}"


def stock(article_number: str, count: int, name: str, price: str, **fields: Any) -> Any:
    """A product billed flat with ``count`` pieces in stock."""
    product = make_product(article_number, name, price=price, billing_mode="flat", **fields)
    make_items(make_model(f"Modell {article_number}", product), count)
    return product


def billing_family() -> SimpleNamespace:
    """The festival described at the top of the module, ready for invoices."""
    customer = ready_for_invoices(make_customer("Stadt Musterstadt"))
    seven = TaxRate.objects.create(name="7 %", rate=Decimal("7.00"))
    whole = make_project("Stadtfest", start=at(9, 12), end=at(14, 18), customer=customer)
    market = project_services.create_subproject(
        whole, name="Bühne Marktplatz", start=at(10, 8), end=at(12, 8), venue="Marktplatz"
    )
    park = project_services.create_subproject(whole, name="Bühne Schlosspark", start=at(12, 12), end=at(14, 12))
    add_line(whole, make_product("S-500", "Stromversorgung", price="500.00", billing_mode="flat"), 1)
    light = add_group(market, "Licht", discount_percent=Decimal("10"))
    spot = add_line(market, stock("L-100", 6, "PAR 64", "20.00"), 6, group=light).line
    add_line(market, make_product("L-020", "Programmheft", price="10.00", billing_mode="flat", tax_rate=seven), 5)
    taken = project_services.take_over_line(spot, park, rights=ALL_RIGHTS).line
    sound = add_group(park, "Ton")
    add_line(park, make_product("S-200", "Mischpult", price="300.00", billing_mode="flat"), 1, group=sound)
    return SimpleNamespace(
        customer=customer, seven=seven, whole=whole, market=market, park=park, spot=spot, taken=taken
    )


class BillingFamilyCase(RentalarsTestCase):
    """The festival, and a helper for the sections of a document."""

    def setUp(self) -> None:
        super().setUp()
        family = billing_family()
        self.whole, self.market, self.park = family.whole, family.market, family.park
        self.customer, self.seven, self.spot, self.taken = family.customer, family.seven, family.spot, family.taken
        self.user = make_user("luka")

    def content(self, kind: str = DocumentKind.OFFER, project: Project | None = None) -> Any:
        return services.build_content(project or self.whole, kind, number="X", issued_on=at(1).date())

    @staticmethod
    def outline(content: Any) -> list[tuple[str, str, str]]:
        """Each section as (part, subproject, title); the block of a part is marked with "block"."""
        return [
            ("block " + section.part if section.subproject_block else section.part, section.subproject, section.title)
            for section in content.sections
        ]


class WholeProjectDocumentTests(BillingFamilyCase):
    """PRJ-045, PRJ-046: offer, order confirmation and invoice of the whole project contain every part."""

    def test_the_whole_projects_own_lines_come_first_then_every_part_as_a_block(self) -> None:
        offer = self.content(DocumentKind.OFFER)
        whole, market, park = self.whole.number, self.market.number, self.park.number
        self.assertEqual(
            self.outline(offer),
            [
                ("", "", "Ohne Teilgruppe"),
                ("block opens", market, f"Teilprojekt {market} Bühne Marktplatz, 10.03.–12.03.2027"),
                ("", market, "Licht"),
                ("", market, "Ohne Teilgruppe"),
                ("block closes", market, f"Teilprojekt {market} Bühne Marktplatz"),
                ("block opens", park, f"Teilprojekt {park} Bühne Schlosspark, 12.03.–14.03.2027"),
                ("", park, "Ton"),
                ("block closes", park, f"Teilprojekt {park} Bühne Schlosspark"),
            ],
        )
        self.assertEqual(offer.project["number"], whole)
        # The venue of a part is named under its heading.
        self.assertEqual(offer.sections[1].description, "Veranstaltungsort: Marktplatz")
        self.assertEqual(offer.sections[5].description, "")
        # The subtotal of a part is its net amount; the heading carries none.
        self.assertEqual([offer.sections[1].subtotal, offer.sections[4].subtotal], [Decimal("0"), Decimal("158.00")])
        self.assertEqual(offer.sections[7].subtotal, Decimal("300.00"))

    def test_the_positions_are_numbered_straight_through(self) -> None:
        offer = self.content(DocumentKind.ORDER_CONFIRMATION)
        self.assertEqual(
            [(position.number, position.title) for position in offer.positions],
            [("1", "Stromversorgung"), ("2", "PAR 64"), ("3", "Programmheft"), ("4", "Mischpult")],
        )

    def test_the_sums_are_those_of_all_projects_together(self) -> None:
        invoice = self.content(DocumentKind.INVOICE)
        self.assertEqual(
            (invoice.net_total, invoice.tax_total, invoice.gross_total),
            (Decimal("958.00"), Decimal("176.02"), Decimal("1134.02")),
        )
        self.assertEqual(
            [(share.name, share.net, share.tax, share.positions_total) for share in invoice.taxes],
            [
                ("19 %", Decimal("908.00"), Decimal("172.52"), Decimal("920.00")),
                ("7 %", Decimal("50.00"), Decimal("3.50"), Decimal("50.00")),
            ],
        )
        # The service period runs from the first to the last day of all parts – here the whole project's.
        self.assertEqual((invoice.service_start, invoice.service_end), (at(9).date(), at(14).date()))

    def test_a_cancelled_part_is_left_out(self) -> None:
        project_services.change_status(self.park, ProjectStatus.CANCELLED, rights=ALL_RIGHTS)
        offer = self.content(DocumentKind.OFFER)
        self.assertNotIn(self.park.number, {section.subproject for section in offer.sections})
        self.assertEqual(offer.net_total, Decimal("658.00"))
        self.assertEqual([position.number for position in offer.positions], ["1", "2", "3"])

    def test_a_part_with_nothing_to_charge_is_left_out(self) -> None:
        empty = project_services.create_subproject(self.whole, name="Bühne Hof")
        offer = self.content(DocumentKind.OFFER)
        self.assertNotIn(empty.number, {section.subproject for section in offer.sections})

    def test_material_taken_over_from_another_part_is_not_charged(self) -> None:
        """PRJ-060: the pieces are charged once, on the Marktplatz; the Schlosspark lists only its sound desk."""
        invoice = self.content(DocumentKind.INVOICE)
        park = [section for section in invoice.sections if section.subproject == self.park.number]
        self.assertEqual([position.title for section in park for position in section.positions], ["Mischpult"])
        self.assertEqual(sum(1 for position in invoice.positions if position.title == "PAR 64"), 1)

    def test_optional_lines_of_a_part_appear_on_the_offer_and_stay_off_the_invoice(self) -> None:
        add_line(self.park, make_product("S-210", "Funkmikrofon", price="40.00", billing_mode="flat"), 2,
                 variant="optional")  # fmt: skip
        offer, invoice = self.content(DocumentKind.OFFER), self.content(DocumentKind.INVOICE)
        self.assertIn("Funkmikrofon", [position.title for section in offer.sections for position in section.positions])
        self.assertEqual(offer.optional_lines_total, Decimal("80.00"))
        self.assertNotIn("Funkmikrofon", [position.title for position in invoice.positions])
        self.assertEqual((offer.net_total, invoice.net_total), (Decimal("958.00"), Decimal("958.00")))

    def test_the_pdf_shows_a_heading_and_a_subtotal_per_part(self) -> None:
        offer = self.content(DocumentKind.OFFER)
        html = render_html(offer, services.template_for(DocumentKind.OFFER))
        market = self.market.number
        # No line of this offer has a discount, so the table has no column "Discount": colspan 4, not 5.
        self.assertIn(f'<tr class="subproject-head"><td></td><td colspan="4">Teilprojekt {market} Bühne Marktplatz, '
                      "10.03.–12.03.2027", html)  # fmt: skip
        self.assertIn(f"Summe Teilprojekt {market} Bühne Marktplatz</td>", html)
        self.assertIn("Zwischensumme Licht", html)
        self.assertLess(html.index(f"Teilprojekt {market}"), html.index("Zwischensumme Licht"))
        self.assertTrue(services.preview(self.whole, DocumentKind.OFFER).startswith(b"%PDF"))

    def test_a_project_without_parts_looks_as_before(self) -> None:
        alone = make_project("Firmenfeier", customer=self.customer, start=at(20, 8), end=at(21, 18))
        add_line(alone, make_product("S-300", "Bühnenpodest", price="80.00", billing_mode="flat"), 2)
        content = self.content(DocumentKind.INVOICE, alone)
        self.assertEqual(self.outline(content), [("", "", "Ohne Teilgruppe")])
        self.assertEqual((content.net_total, content.gross_total), (Decimal("160.00"), Decimal("190.40")))
        self.assertEqual((content.service_start, content.service_end), (at(20).date(), at(21).date()))


class InvoiceOfTheWholeProjectTests(BillingFamilyCase):
    """DOK-006, DOK-007: the invoice of a whole project, its XRechnung, its cancellation, one at a time."""

    def totals(self, document: Document) -> tuple[dict[str, str], ET.Element]:
        document.xml_file.open("rb")
        root = ET.fromstring(document.xml_file.read())
        return {child.tag.split("}")[1]: child.text for child in root.find(f"{CAC}LegalMonetaryTotal")}, root

    def assert_consistent(self, root: ET.Element, totals: dict[str, str]) -> None:
        """EN 16931: the totals follow from the lines, allowances and taxes (BR-CO-10, -13, -15, BR-S-08)."""
        lines = [Decimal(line.find(f"{CBC}LineExtensionAmount").text) for line in root.iter(f"{CAC}InvoiceLine")]
        allowances = charges = Decimal("0")
        for element in root.findall(f"{CAC}AllowanceCharge"):
            amount = Decimal(element.find(f"{CBC}Amount").text)
            if element.find(f"{CBC}ChargeIndicator").text == "true":
                charges += amount
            else:
                allowances += amount
        self.assertEqual(Decimal(totals["LineExtensionAmount"]), sum(lines, Decimal("0")))
        self.assertEqual(
            Decimal(totals["TaxExclusiveAmount"]), Decimal(totals["LineExtensionAmount"]) - allowances + charges
        )
        tax_total = Decimal(root.find(f"{CAC}TaxTotal/{CBC}TaxAmount").text)
        subtotals = list(root.iter(f"{CAC}TaxSubtotal"))
        self.assertEqual(tax_total, sum((Decimal(s.find(f"{CBC}TaxAmount").text) for s in subtotals), Decimal("0")))
        self.assertEqual(
            Decimal(totals["TaxExclusiveAmount"]),
            sum((Decimal(s.find(f"{CBC}TaxableAmount").text) for s in subtotals), Decimal("0")),
        )
        for subtotal in subtotals:
            taxable = Decimal(subtotal.find(f"{CBC}TaxableAmount").text)
            percent = Decimal(subtotal.find(f"{CAC}TaxCategory/{CBC}Percent").text)
            self.assertEqual(Decimal(subtotal.find(f"{CBC}TaxAmount").text), (taxable * percent / 100).quantize(
                Decimal("0.01")))  # fmt: skip
        self.assertEqual(Decimal(totals["TaxInclusiveAmount"]), Decimal(totals["TaxExclusiveAmount"]) + tax_total)
        self.assertEqual(totals["PayableAmount"], totals["TaxInclusiveAmount"])

    def test_the_xrechnung_adds_up_with_parts(self) -> None:
        invoice = services.create_document(self.whole, DocumentKind.INVOICE, user=self.user)
        self.assertEqual((invoice.project, invoice.net_total, invoice.gross_total),
                         (self.whole, Decimal("958.00"), Decimal("1134.02")))  # fmt: skip
        totals, root = self.totals(invoice)
        self.assertEqual(
            {key: totals[key] for key in ("LineExtensionAmount", "AllowanceTotalAmount", "TaxExclusiveAmount")},
            {"LineExtensionAmount": "970.00", "AllowanceTotalAmount": "12.00", "TaxExclusiveAmount": "958.00"},
        )
        self.assertEqual((totals["TaxInclusiveAmount"], totals["PayableAmount"]), ("1134.02", "1134.02"))
        self.assertEqual(
            [line.find(f"{CAC}Item/{CBC}Name").text for line in root.iter(f"{CAC}InvoiceLine")],
            ["Stromversorgung", "PAR 64", "Programmheft", "Mischpult"],
        )
        self.assertEqual(
            [(s.find(f"{CBC}TaxableAmount").text, s.find(f"{CBC}TaxAmount").text) for s in root.iter(f"{CAC}TaxSubtotal")],
            [("908.00", "172.52"), ("50.00", "3.50")],
        )  # fmt: skip
        period = root.find(f"{CAC}InvoicePeriod")
        self.assertEqual((period.find(f"{CBC}StartDate").text, period.find(f"{CBC}EndDate").text),
                         ("2027-03-09", "2027-03-14"))  # fmt: skip
        self.assertEqual(root.find(f"{CBC}BuyerReference").text, self.whole.number)
        self.assert_consistent(root, totals)

    def test_a_discount_in_every_part_still_adds_up(self) -> None:
        """Group discounts of several parts become allowances per tax rate; the sums still fit to the cent."""
        sound = self.park.groups.get(name="Ton")
        project_services.update_group(sound, rights=ALL_RIGHTS, discount_percent=Decimal("3.3"))
        booklet = self.market.material_lines.get(title="Programmheft")
        project_services.update_line(booklet, rights=ALL_RIGHTS, discount_percent=Decimal("12.5"))
        invoice = services.create_document(self.whole, DocumentKind.INVOICE)
        totals, root = self.totals(invoice)
        self.assert_consistent(root, totals)
        self.assertEqual(Decimal(totals["TaxInclusiveAmount"]), invoice.gross_total)

    def test_one_valid_invoice_at_a_time(self) -> None:
        invoice = services.create_document(self.whole, DocumentKind.INVOICE)
        with self.assertRaises(ValidationError) as caught:
            services.create_document(self.whole, DocumentKind.INVOICE)
        self.assertIn(f"Rechnung {invoice.number} dieses Projekts ist noch gültig.", str(caught.exception))
        cancellation = services.cancel_invoice(invoice)
        self.assertEqual(cancellation.gross_total, Decimal("-1134.02"))
        content = from_json(cancellation.content)
        closing = [section for section in content.sections if section.subproject_block and section.part == "closes"]
        self.assertEqual([section.subtotal for section in closing], [Decimal("-158.00"), Decimal("-300.00")])
        totals, root = self.totals(cancellation)
        self.assertEqual(totals["PayableAmount"], "-1134.02")
        self.assert_consistent(root, totals)
        self.assertEqual(services.create_document(self.whole, DocumentKind.INVOICE).gross_total, Decimal("1134.02"))

    def test_a_valid_invoice_a_part_has_from_before_stops_the_invoice_of_the_whole_project(self) -> None:
        """A project that became a part later may have been invoiced already: it would be charged twice."""
        earlier = make_project("Bühne Hof", customer=self.customer, start=at(10, 8), end=at(11, 8))
        add_line(earlier, make_product("S-400", "Bühnenpodest", price="80.00", billing_mode="flat"), 1)
        old = services.create_document(earlier, DocumentKind.INVOICE)
        Project.objects.filter(pk=earlier.pk).update(parent=self.whole, number=f"{self.whole.number}-3")
        with self.assertRaises(ValidationError) as caught:
            services.create_document(self.whole, DocumentKind.INVOICE)
        self.assertIn(
            f"Rechnung {old.number} des Teilprojekts {self.whole.number}-3 ist noch gültig. Storniere sie zuerst.",
            caught.exception.messages,
        )
        services.cancel_invoice(old)
        self.assertEqual(services.create_document(self.whole, DocumentKind.INVOICE).net_total, Decimal("1038.00"))


class PartDocumentTests(BillingFamilyCase):
    """PRJ-045, PRJ-048: a part makes no priced documents, but its own delivery notes and crew dispositions."""

    def test_offer_order_confirmation_and_invoice_are_refused_on_a_part(self) -> None:
        expected = (
            f"Angebot, Auftragsbestätigung und Rechnung entstehen am Gesamtprojekt {self.whole.number} – mit allen "
            "Teilprojekten."
        )
        for kind in (DocumentKind.OFFER, DocumentKind.ORDER_CONFIRMATION, DocumentKind.INVOICE):
            self.assertIn(expected, services.check_can_make(self.market, kind))
            with self.assertRaises(ValidationError) as caught:
                services.create_document(self.market, kind)
            self.assertEqual(caught.exception.messages[0], expected)
            with self.assertRaises(ValidationError):
                services.preview(self.market, kind)
        self.assertFalse(Document.objects.exists())

    def test_the_delivery_note_of_a_part_goes_to_its_own_address(self) -> None:
        note = services.create_document(self.market, DocumentKind.DELIVERY_NOTE)
        self.assertEqual(note.content["recipient"], ["Marktplatz"])
        self.assertEqual([row["title"] for row in note.content["delivery_rows"][0][1]], ["PAR 64", "Programmheft"])
        self.assertEqual(note.content["project"]["number"], self.market.number)

    def test_taken_over_pieces_are_on_the_delivery_note_of_the_taking_part(self) -> None:
        """PRJ-060: the Schlosspark gets the spotlights straight from the Marktplatz."""
        content = self.content(DocumentKind.DELIVERY_NOTE, self.park)
        rows = [row for _title, entries in content.delivery_rows for row in entries]
        spot = next(row for row in rows if row.article_number == "L-100")
        self.assertEqual(
            (spot.quantity, spot.taken_over_from), (Decimal("6"), f"{self.market.number} Bühne Marktplatz")
        )
        self.assertIn(
            f"Übernahme aus {self.market.number} Bühne Marktplatz",
            render_html(content, services.template_for(DocumentKind.DELIVERY_NOTE)),
        )
        source = next(row for _t, entries in self.content(DocumentKind.DELIVERY_NOTE, self.market).delivery_rows
                      for row in entries if row.article_number == "L-100")  # fmt: skip
        self.assertEqual(source.taken_over_from, "")

    def test_the_delivery_note_of_the_whole_project_holds_its_own_material(self) -> None:
        content = self.content(DocumentKind.DELIVERY_NOTE, self.whole)
        self.assertEqual(
            [row.article_number for _title, entries in content.delivery_rows for row in entries], ["S-500"]
        )

    def test_crew_dispositions_are_made_per_part(self) -> None:
        from tests.helpers import job_function, make_person, plan

        plan(self.park, job_function("Tontechnik"), make_person("Anna Beispiel"), start=at(12, 12), end=at(12, 23))
        sheet = services.create_document(self.park, DocumentKind.CREW_SHEET)
        self.assertEqual([row["person"] for row in sheet.content["crew_rows"]], ["Anna Beispiel"])
        with self.assertRaises(ValidationError):
            services.create_document(self.whole, DocumentKind.CREW_SHEET)  # nobody planned on the whole project


class AccessToPartsTests(BillingFamilyCase):
    """PRJ-049: whoever may not read every part makes no priced document of the whole project."""

    def setUp(self) -> None:
        super().setUp()
        Role.objects.create(
            name="Bühnenleitung extern",
            module_levels={Module.PROJECTS: int(Level.WRITE)},
            special_rights=[SpecialRight.PRICES],
            project_scope=ProjectScope.ASSIGNED,
        )
        self.external = make_user("erik", roles=("Bühnenleitung extern",))
        ProjectMembership.objects.create(project=self.whole, user=self.external, level=ProjectAccessLevel.EDIT)
        ProjectMembership.objects.create(project=self.park, user=self.external, level=ProjectAccessLevel.NONE)
        self.rights = rights_of(self.external)

    def test_priced_documents_need_every_part(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            services.create_document(self.whole, DocumentKind.INVOICE, user=self.external, rights=self.rights)
        self.assertIn(self.park.number, caught.exception.messages[0])
        with self.assertRaises(ValidationError):
            services.preview(self.whole, DocumentKind.OFFER, rights=self.rights, user=self.external)
        note = services.create_document(self.whole, DocumentKind.DELIVERY_NOTE, user=self.external, rights=self.rights)
        self.assertEqual(note.kind, DocumentKind.DELIVERY_NOTE)
        # A cancelled part is not on the document, so it does not matter.
        project_services.change_status(self.park, ProjectStatus.CANCELLED, rights=ALL_RIGHTS)
        offer = services.create_document(self.whole, DocumentKind.OFFER, user=self.external, rights=self.rights)
        self.assertEqual(offer.net_total, Decimal("658.00"))

    def test_the_price_overview_leaves_out_the_part_and_says_so(self) -> None:
        overview = family_prices(self.whole, rights=self.rights, user=self.external)
        self.assertEqual(([block.project for block in overview.blocks], overview.hidden),
                         ([self.whole, self.market], 1))  # fmt: skip
        self.assertEqual(overview.totals.net_total, Decimal("658.00"))
        text = render_price_overview_csv(self.whole, rights=self.rights, user=self.external)
        self.assertNotIn("Mischpult", text)
        self.assertIn("1 Teilprojekt ist nicht enthalten", text)


class AccountingWithPartsTests(BillingFamilyCase):
    """DOK-011, DOK-012: Lexware Office and DATEV take the invoice of a whole project as it is."""

    def test_the_lexware_voucher_has_the_amounts_of_all_parts_per_tax_rate(self) -> None:
        invoice = services.create_document(self.whole, DocumentKind.INVOICE, user=self.user)
        body = lexware.voucher_body(invoice, from_json(invoice.content), AccountingSettings.load(), contact_id="")
        self.assertEqual((body["totalGrossAmount"], body["totalTaxAmount"]), (1134.02, 176.02))
        self.assertEqual(
            [(item["amount"], item["taxAmount"], item["taxRatePercent"]) for item in body["voucherItems"]],
            [(908.0, 172.52, 19), (50.0, 3.5, 7)],
        )
        self.assertIn(f"Projekt {self.whole.number} „Stadtfest“", body["remark"])
        self.assertEqual(body["shippingDate"], "2027-03-14")
        self.assertEqual(voucher_problems(body, {}), [])

    def test_the_datev_bookings_have_the_gross_amounts_of_the_invoice(self) -> None:
        accounting = AccountingSettings.load()
        accounting.datev_consultant_number, accounting.datev_client_number = 29098, 55003
        accounting.save()
        invoice = services.create_document(self.whole, DocumentKind.INVOICE, user=self.user)
        result = datev.bookings_file(datetime.date(2027, 3, 1), datetime.date(2027, 3, 31), user=self.user)
        rows = [line.split(";") for line in result.content.decode("cp1252").removesuffix("\r\n").split("\r\n")[2:]]
        self.assertEqual([(row[0], row[7], row[10]) for row in rows],
                         [("1080,52", "8400", f'"{invoice.number}"'), ("53,50", "8300", f'"{invoice.number}"')])  # fmt: skip
        self.assertEqual(sum(Decimal(row[0].replace(",", ".")) for row in rows), invoice.gross_total)


class PriceOverviewOfTheFamilyTests(BillingFamilyCase):
    """PRJ-035, PRJ-036, DOK-009 with PRJ-046: the price overview of a whole project and of a part."""

    def test_the_whole_project_with_its_parts_and_the_sum_of_all(self) -> None:
        overview = family_prices(self.whole, rights=ALL_RIGHTS, user=None)
        self.assertEqual([block.project for block in overview.blocks], [self.whole, self.market, self.park])
        self.assertEqual([block.prices.net_total for block in overview.blocks],
                         [Decimal("500.00"), Decimal("158.00"), Decimal("300.00")])  # fmt: skip
        totals = overview.totals
        self.assertEqual((totals.net_total, totals.tax_total, totals.gross_total),
                         (Decimal("958.00"), Decimal("176.02"), Decimal("1134.02")))  # fmt: skip
        self.assertTrue(overview.has_parts)
        self.assertEqual(
            overview.parts[0].heading, f"Teilprojekt {self.market.number} Bühne Marktplatz, 10.03.–12.03.2027"
        )

    def test_a_part_shows_just_itself(self) -> None:
        overview = family_prices(self.market, rights=ALL_RIGHTS, user=None)
        self.assertEqual(([block.project for block in overview.blocks], overview.is_part, overview.has_parts),
                         ([self.market], True, False))  # fmt: skip
        html = render_price_overview_html(self.market)
        self.assertIn(f"Teil von {self.whole.number} Stadtfest; Summe aller Teile im Gesamtprojekt.", html)

    def test_csv_and_pdf_with_parts(self) -> None:
        project_services.change_status(
            project_services.create_subproject(self.whole, name="Bühne Hof"), ProjectStatus.CANCELLED,
            rights=ALL_RIGHTS,
        )  # fmt: skip
        rows = [row.split(";") for row in render_price_overview_csv(self.whole).lstrip("﻿").splitlines()]
        market = self.market.number
        sections = [row[0] for row in rows]
        self.assertIn(f"Gemeinsame Positionen des Gesamtprojekts {self.whole.number}", sections)
        self.assertIn(f"Teilprojekt {market} Bühne Marktplatz, 10.03.–12.03.2027", sections)
        self.assertIn(f"{market} › Licht", sections)
        self.assertIn([f"Summe Teilprojekt {market} Bühne Marktplatz", *[""] * 8, "158"], rows)
        taken = next(row for row in rows if row[0] == f"{self.park.number} › Ohne Teilgruppe" and row[1] == "L-100")
        self.assertEqual((taken[2], taken[9]), (f"PAR 64 (Übernahme aus {market})", "0"))
        self.assertIn(["Summe netto", *[""] * 8, "958"], rows)
        self.assertIn(["Steuer 19 %", *[""] * 8, "172,52"], rows)
        self.assertIn(["Summe brutto", *[""] * 8, "1134,02"], rows)
        self.assertTrue(rows[-1][0].startswith("Storniert, daher nicht enthalten: "))
        groups = [row.split(";") for row in render_price_overview_csv(self.whole, with_lines=False).splitlines()]
        self.assertTrue(all(len(row) == 3 for row in groups))
        html = render_price_overview_html(self.whole, with_lines=True)
        self.assertIn(f"Teilprojekt {market} Bühne Marktplatz, 10.03.–12.03.2027", html)
        self.assertIn(f"Summe Teilprojekt {market} Bühne Marktplatz", html)
        self.assertIn(f"Übernahme aus {market}, nicht berechnet", html)

    def test_the_tax_is_calculated_once_on_the_sum_of_each_rate(self) -> None:
        """Three cents at 19 % twice: 0,01 tax each, but 0,01 on the six cents together (EN 16931 BR-CO-17)."""
        rate = TaxRate.get_default()
        parts = [
            ProjectPrices(project=self.whole, net_total=Decimal("0.03"),
                          tax_lines=[TaxLine(tax_rate=rate, net=Decimal("0.03"), tax=Decimal("0.01"))])
            for _part in range(2)
        ]  # fmt: skip
        totals = sum_prices(parts)
        self.assertEqual((totals.net_total, totals.tax_total, totals.gross_total),
                         (Decimal("0.06"), Decimal("0.01"), Decimal("0.07")))  # fmt: skip
        self.assertEqual(len(totals.tax_lines), 1)
