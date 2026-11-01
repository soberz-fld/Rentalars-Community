# SPDX-License-Identifier: GPL-3.0-or-later
"""The layout of the PDF documents (DOK-005, DOK-013, PRJ-037). (DOK-025)

Three requirements:

* In PDF documents the column "Rabatt" is hidden when no line has a discount.
* In PDF documents the headings of the columns line up with their content.
* The hierarchy is clearer: the top level is Material + Personal + Logistik, the level below Material starts with the
  subgroups.

The column "Discount" appears only when a position shown has a discount; every row of the table has as many cells as
the heading has columns, and the headings of the number columns are aligned like their figures. The document has
three top levels – Material (the groups with their subgroups, then the lines without group), Personnel, Logistics –
each with its sum; the sums are those of the price calculation, nothing is priced differently.
"""

from __future__ import annotations

import datetime
import re
from decimal import Decimal
from html.parser import HTMLParser

from rentalars.documents import content as builder
from rentalars.documents import services
from rentalars.documents.models import DocumentDetail, DocumentKind
from rentalars.documents.pdf import render_html, render_pdf
from rentalars.projects.models import LineVariant
from tests.helpers import RentalarsTestCase, add_group, add_line, make_product, make_project, ready_for_invoices
from tests.unit.test_062_documents import flat, stadtfest

D = Decimal
ISSUED = datetime.date(2027, 3, 1)


class Table(HTMLParser):
    """The positions table of a document: the heading cells and, per body row, (class, colspan) of its cells."""

    def __init__(self, html: str) -> None:
        super().__init__()
        self.heading: list[str] = []
        self.rows: list[tuple[str, list[tuple[str, int]]]] = []
        self._in_table = False
        self._in_head = False
        self._row_class = ""
        self._cells: list[tuple[str, int]] | None = None
        self.feed(html)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = values.get("class") or ""
        if tag == "table" and "positions" in classes.split() and not self._in_table and not self.heading:
            self._in_table = True
        if not self._in_table:
            return
        if tag == "thead":
            self._in_head = True
        elif tag == "tr" and not self._in_head:
            self._row_class, self._cells = classes, []
        elif tag == "th":
            self.heading.append(classes)
        elif tag == "td" and self._cells is not None:
            self._cells.append((classes, int(values.get("colspan") or 1)))

    def handle_endtag(self, tag: str) -> None:
        if tag == "thead":
            self._in_head = False
        elif tag == "tr" and self._cells is not None:
            self.rows.append((self._row_class, self._cells))
            self._cells = None
        elif tag == "table":
            self._in_table = False


def offer_html(content: builder.DocumentContent) -> str:
    """The HTML of an offer made from ``content``."""
    return render_html(content, services.template_for(DocumentKind.OFFER))


def build(project, kind: str = DocumentKind.OFFER, **fields):
    """The content of a document of the project."""
    return builder.build_priced(project, kind, title="Angebot", number="AN-1", issued_on=ISSUED, **fields)


class DiscountColumnTests(RentalarsTestCase):
    """The column "Discount" only where a line has a discount."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", customer=ready_for_invoices())
        self.group = add_group(self.project, "Licht")

    def test_no_discount_no_column(self) -> None:
        add_line(self.project, flat("L-100", "PAR 64", "20.00"), 6, group=self.group)
        content = build(self.project)
        self.assertFalse(content.has_discounts)
        table = Table(offer_html(content))
        self.assertEqual(len(table.heading), 5)
        self.assertNotIn("Rabatt", "".join(re.findall(r"<thead>.*?</thead>", offer_html(content), re.S)))

    def test_a_discount_brings_the_column(self) -> None:
        add_line(self.project, flat("L-100", "PAR 64", "20.00"), 6, group=self.group, discount_percent=D("10"))
        add_line(self.project, flat("L-101", "PAR 56", "15.00"), 2, group=self.group)
        content = build(self.project)
        self.assertTrue(content.has_discounts)
        html = offer_html(content)
        self.assertEqual(len(Table(html).heading), 6)
        self.assertIn("Rabatt", re.search(r"<thead>.*?</thead>", html, re.S).group(0))
        self.assertIn("10 %", html)

    def test_a_group_discount_is_a_row_not_a_column(self) -> None:
        self.group.discount_percent = D("10")
        self.group.save()
        add_line(self.project, flat("L-100", "PAR 64", "20.00"), 6, group=self.group)
        content = build(self.project)
        self.assertFalse(content.has_discounts)
        html = offer_html(content)
        self.assertEqual(len(Table(html).heading), 5)
        self.assertIn("Rabatt 10 %", html)  # the row below the group's lines
        self.assertIn("-12,00", html)

    def test_the_groups_only_offer_asks_for_the_lines_it_shows(self) -> None:
        """The lines summed up in a group are not printed, so their discounts need no column."""
        add_line(self.project, flat("L-100", "PAR 64", "20.00"), 6, group=self.group, discount_percent=D("10"))
        shortened = builder.only_groups(build(self.project))
        self.assertFalse(shortened.has_discounts)
        self.assertEqual(len(Table(offer_html(shortened)).heading), 5)
        optional = add_line(
            self.project, flat("L-200", "Nebel", "50.00"), 1, group=self.group, variant=LineVariant.OPTIONAL
        )
        optional.line.discount_percent = D("20")
        optional.line.save()
        self.assertTrue(builder.only_groups(build(self.project)).has_discounts)  # an optional line stays listed

    def test_a_cancellation_has_the_same_columns(self) -> None:
        add_line(self.project, flat("L-100", "PAR 64", "20.00"), 6, group=self.group)
        invoice = services.create_document(self.project, DocumentKind.INVOICE)
        cancellation = builder.negated(
            builder.from_json(invoice.content), title="Storno", number="ST-1", issued_on=ISSUED
        )
        self.assertFalse(cancellation.has_discounts)
        self.assertEqual(len(Table(offer_html(cancellation)).heading), 5)

    def test_every_row_has_as_many_cells_as_the_heading(self) -> None:
        """Header and body of the table line up: with and without the column, with subgroups, text and other levels."""
        for discount in (False, True):
            with self.subTest(discount=discount):
                project = make_project("Fest", customer=self.project.customer)
                bottom = add_group(project, "Licht")
                sub = add_group(project, "Front", parent=bottom)
                add_line(project, flat(f"L-30{int(discount)}", "Traverse", "12.00"), 6, group=sub)
                add_line(
                    project,
                    flat(f"L-31{int(discount)}", "Kabel", "2.00"),
                    6,
                    discount_percent=D("10") if discount else D("0"),
                )
                from rentalars.projects import services as project_services

                project_services.add_text_line(project, title="Aufbau ab 14 Uhr", note="Tor 2", group=bottom)
                table = Table(offer_html(build(project)))
                columns = len(table.heading)
                self.assertEqual(columns, 6 if discount else 5)
                for row_class, cells in table.rows:
                    self.assertEqual(sum(span for _class, span in cells), columns, row_class)

    def test_headings_of_number_columns_are_aligned_like_the_figures(self) -> None:
        add_line(self.project, flat("L-100", "PAR 64", "20.00"), 6, group=self.group, discount_percent=D("10"))
        html = offer_html(build(self.project))
        table = Table(html)
        position_row = next(cells for _class, cells in table.rows if len(cells) == len(table.heading))
        numbers = [cell_class.split() for cell_class, _span in position_row]
        for heading_class, cell_class in zip(table.heading, numbers, strict=True):
            self.assertEqual("num" in heading_class.split(), "num" in cell_class)
        # The heading rule is as specific as the rule for all headings, else the left alignment wins (the old fault).
        self.assertIn("table.positions th.num, table.positions td.num { text-align: right; }", html)

    def test_the_pdf_is_made(self) -> None:
        add_line(self.project, flat("L-100", "PAR 64", "20.00"), 6, group=self.group, discount_percent=D("10"))
        content = build(self.project)
        self.assertTrue(render_pdf(content, services.template_for(DocumentKind.OFFER)).startswith(b"%PDF"))

    def test_a_free_document_has_the_same_rule(self) -> None:
        """A document without a project has one plain section; the discount column follows its lines too."""
        from rentalars.documents.content import Position, Section

        def free(discount: str) -> builder.DocumentContent:
            position = Position(
                number="1", title="Beratung", quantity=D("1"), unit="h", unit_price=D("50"), amount=D("50")
            )
            position.discount_percent = D(discount)
            return builder.DocumentContent(
                kind="free_invoice",
                title="Rechnung",
                number="R-1",
                issued_on=ISSUED,
                company=builder.company_data(),
                recipient=[],
                project={},
                sections=[Section(title="", positions=[position], subtotal=D("50"), plain=True)],
            )

        self.assertEqual(len(Table(offer_html(free("0"))).heading), 5)
        self.assertEqual(len(Table(offer_html(free("10"))).heading), 6)


class HierarchyTests(RentalarsTestCase):
    """Top level Material / Personnel / Logistics, below Material the groups, below them the lines."""

    def setUp(self) -> None:
        super().setUp()
        self.fest = stadtfest()
        self.project = self.fest.project

    def test_the_sections_know_their_top_level(self) -> None:
        content = build(self.project)
        self.assertEqual(
            [(section.title, section.division) for section in content.sections],
            [
                ("Licht", "material"),
                ("Ton", "material"),  # opens: the group with subgroups
                ("Mikrofone", "material"),
                ("Ton", "material"),  # closes
                ("Ohne Teilgruppe", "material"),
                ("Personal", "personnel"),
            ],
        )
        self.assertEqual([s.division_start for s in content.sections], [True, False, False, False, False, True])
        self.assertEqual([s.division_end for s in content.sections], [False, False, False, False, True, True])

    def test_the_sum_of_material_is_the_sum_of_the_groups_and_the_lines_without_group(self) -> None:
        content = build(self.project)
        material = next(
            section for section in content.sections if section.division_end and section.division == "material"
        )
        # Licht 108 + Ton with subgroup 400 + Transport 80 + LED-Wand 900 = 1.488; personnel 360.
        self.assertEqual(material.division_total, D("1488.00"))
        personnel = next(section for section in content.sections if section.division == "personnel")
        self.assertEqual(personnel.subtotal, D("360.00"))
        self.assertEqual(material.division_total + personnel.subtotal, content.net_total)

    def test_the_sums_are_those_of_the_price_calculation(self) -> None:
        from rentalars.projects.pricing import compute_project_prices

        prices = compute_project_prices(self.project)
        content = build(self.project)
        material = next(
            section for section in content.sections if section.division_end and section.division == "material"
        )
        self.assertEqual(material.division_total, prices.groups_total + prices.ungrouped_total)
        self.assertEqual(content.net_total, prices.net_total)

    def test_the_page_shows_the_levels_in_order(self) -> None:
        html = offer_html(build(self.project))
        order = [
            '<tr class="division-head division-material"><td></td><td colspan="4">Material</td></tr>',
            '<tr class="section"><td></td><td colspan="4">Licht<',
            "Zwischensumme Licht<",
            "Zwischensumme Ton mit Untergruppen<",
            "Ohne Teilgruppe",
            "Summe Material</td>",
            '<tr class="division-head division-personnel"><td></td><td colspan="4">Personal',
            "Summe Personal</td>",
            "Summe netto",
        ]
        positions = [html.index(text) for text in order]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("1.488,00", html[html.index("Summe Material") :])
        self.assertNotIn("Zwischensumme Personal", html)  # the top level has its sum, not a subtotal as well

    def test_subgroups_and_lines_are_indented_by_their_level(self) -> None:
        html = offer_html(build(self.project))
        self.assertIn('<tr class="section level-1"><td></td><td colspan="4">Mikrofone', html)
        self.assertRegex(html, r'<tr class="\s*lvl-1">\s*<td class="pos">\d+</td>\s*<td>Funkmikrofon')

    def test_only_the_levels_that_are_there_are_shown(self) -> None:
        project = make_project("Firmenfeier", customer=self.project.customer)
        add_line(project, flat("K-200", "Kabel", "2.00"), 5)
        html = offer_html(build(project))
        self.assertIn("division-material", html)
        self.assertNotIn("division-personnel", html)
        self.assertNotIn("division-logistics", html)
        # Lines without any group stand under "Material" without a row "Ohne Teilgruppe" of their own.
        self.assertNotIn("Ohne Teilgruppe", html)
        self.assertIn("Summe Material</td><td", html)

    def test_a_project_with_personnel_only_has_no_material(self) -> None:
        from tests.helpers import job_function, make_person, plan

        project = make_project("Technik", customer=self.project.customer)
        plan(
            project, job_function("Tontechnik", price="45.00"), make_person("Ben Meyer", rates={"Tontechnik": "30.00"})
        )
        html = offer_html(build(project))
        self.assertNotIn("division-material", html)
        self.assertIn("division-personnel", html)

    def test_the_offer_with_groups_only_keeps_the_levels(self) -> None:
        shortened = builder.only_groups(build(self.project))
        html = offer_html(shortened)
        self.assertIn("division-material", html)
        self.assertIn("division-personnel", html)
        self.assertIn("1.488,00", html)
        self.assertEqual(shortened.net_total, build(self.project).net_total)

    def test_a_stored_document_is_read_back_and_a_cancellation_negates_the_sum(self) -> None:
        invoice = services.create_document(self.project, DocumentKind.INVOICE)
        stored = builder.from_json(invoice.content)
        self.assertEqual([s.division_total for s in stored.sections if s.division_total], [D("1488.00")])
        cancellation = builder.negated(stored, title="Storno", number="ST-1", issued_on=ISSUED)
        self.assertEqual([s.division_total for s in cancellation.sections if s.division_total], [D("-1488.00")])
        self.assertIn("-1.488,00", offer_html(cancellation))

    def test_a_document_made_before_0_10_0_prints_as_before(self) -> None:
        """No top levels stored: the old look, nothing is lost and nothing breaks."""
        data = build(self.project).as_json()
        for section in data["sections"]:
            for key in ("division", "division_start", "division_end", "division_total"):
                section.pop(key)
        old = builder.from_json(data)
        html = offer_html(old)
        self.assertNotIn("division-", html.split("</style>")[1])
        self.assertIn("Zwischensumme Personal", html)
        self.assertIn("Zwischensumme Ton mit Untergruppen", html)

    def test_surcharges_and_the_overall_discount_stand_after_the_levels(self) -> None:
        self.project.overall_discount_percent = D("10")
        self.project.save()
        content = build(self.project)
        html = offer_html(content)
        self.assertLess(html.index("Summe Personal"), html.index("Gesamtrabatt"))
        self.assertEqual(content.net_total, D("1663.20"))  # (1.488 + 360) less 10 %

    def test_the_invoice_pdf_is_made(self) -> None:
        document = services.create_document(self.project, DocumentKind.INVOICE)
        self.assertTrue(document.file.read().startswith(b"%PDF"))
        self.assertTrue(
            services.preview(self.project, DocumentKind.OFFER, detail=DocumentDetail.GROUPS).startswith(b"%PDF")
        )


class FreeAndOtherDocumentsTests(RentalarsTestCase):
    """The delivery note and the crew sheet: their number columns are aligned as well."""

    def test_the_delivery_note_table_has_aligned_headings(self) -> None:
        project = make_project("Stadtfest", customer=ready_for_invoices())
        add_line(project, make_product("L-100", "PAR 64", price="20.00"), 6)
        note = builder.build_delivery_note(project, title="Lieferschein", number="LS-1", issued_on=ISSUED)
        html = render_html(note, services.template_for(DocumentKind.DELIVERY_NOTE))
        self.assertIn('<th class="num">Menge</th>', html)
        self.assertIn("table.positions th.num, table.positions td.num { text-align: right; }", html)
