# SPDX-License-Identifier: GPL-3.0-or-later
"""Acceptance scenario 7 – Packliste (catalogue chapter 11)."""

import io

from pypdf import PdfReader

from rentalars.packing.pdf import render_packlist_pdf
from rentalars.packing.services import build_overview, get_packlist
from tests.helpers import RentalarsTestCase, add_group, add_line, make_product, make_project

#: Three groups with four lines each: article number, name, quantity, price.
GROUPS = {
    "Licht Front-Traverse": [
        ("L-010", "LED-Scheinwerfer RGBW", 8, "20.10"),
        ("L-020", "Moving Head Spot", 4, "45.20"),
        ("R-010", "Traverse 4-Punkt 2 m", 6, "9.30"),
        ("K-020", "Schuko-Verlängerung 10 m", 10, "2.40"),
    ],
    "Ton FOH": [
        ("T-030", "Digitalmischpult 32 Kanal", 1, "120.50"),
        ("T-010", "Aktivbox 12 Zoll", 4, "30.60"),
        ("S-020", "Boxenstativ", 4, "5.70"),
        ("K-005", "XLR-Kabel 5 m", 12, "1.80"),
    ],
    "Bühne": [
        ("S-100", "Bühnenpodest 2 x 1 m", 16, "12.90"),
        ("S-110", "Podestfuß 60 cm", 64, "1.15"),
        ("S-120", "Treppe 3 Stufen", 2, "18.25"),
        ("K-030", "Kabelbrücke 5 Kanal", 7, "6.35"),
    ],
}


class Scenario07Packlist(RentalarsTestCase):
    """PCK-002, PCK-003, PCK-007, DOK-001."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest Hauptbühne")
        for group_name, lines in GROUPS.items():
            group = add_group(self.project, group_name)
            for article_number, name, quantity, price in lines:
                add_line(self.project, make_product(article_number, name, price=price), quantity, group=group)
        pdf = render_packlist_pdf(build_overview(get_packlist(self.project)))
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.pages = [page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages]
        self.text = "\n".join(self.pages)

    def test_pdf_lists_all_twelve_lines_with_article_number_name_and_quantity(self) -> None:
        for lines in GROUPS.values():
            for article_number, name, quantity, _price in lines:
                with self.subTest(article_number=article_number):
                    self.assertIn(article_number, self.text)
                    self.assertIn(name, self.text)
                    # Quantity, unit and article number stand next to each other in a row.
                    row = next(line for line in self.text.splitlines() if article_number in line)
                    self.assertIn(str(quantity), row.split(article_number)[0])

    def test_lines_are_grouped_in_the_order_of_the_planning(self) -> None:
        positions = [self.text.index(name) for name in GROUPS]
        self.assertEqual(positions, sorted(positions))
        for group_name, lines in GROUPS.items():
            start = self.text.index(group_name)
            later_groups = [self.text.index(other) for other in GROUPS if self.text.index(other) > start]
            end = min(later_groups) if later_groups else len(self.text)
            for article_number, _name, _quantity, _price in lines:
                self.assertTrue(
                    start < self.text.index(article_number) < end, f"{article_number} is not below {group_name}"
                )

    def test_pdf_shows_no_prices(self) -> None:
        for lines in GROUPS.values():
            for _article_number, _name, _quantity, price in lines:
                self.assertNotIn(price, self.text)
                self.assertNotIn(price.replace(".", ","), self.text)
        self.assertNotIn("€", self.text)

    def test_pdf_carries_project_and_page_numbers(self) -> None:
        self.assertIn(self.project.number, self.text)
        self.assertIn("Stadtfest Hauptbühne", self.text)
        self.assertIn("Packliste", self.text)
        self.assertIn(f"1 / {len(self.pages)}", self.text)
