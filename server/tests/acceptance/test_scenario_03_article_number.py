# SPDX-License-Identifier: GPL-3.0-or-later
"""Acceptance scenario 3 – Artikelnummer (catalogue chapter 11)."""

from django.core.exceptions import ValidationError

from rentalars.masterdata.models import Category
from rentalars.products.services import suggest_article_number
from tests.helpers import RentalarsTestCase, category, make_product


class Scenario03ArticleNumber(RentalarsTestCase):
    """PRD-007, PRD-008, PRD-010, PRD-028."""

    def test_valid_numbers_are_accepted(self) -> None:
        # D-001 to D-008 are the services of the job functions of the start data (PER-037).
        for article_number in ("K-005", "L-0142", "D-100"):
            with self.subTest(article_number=article_number):
                self.assertEqual(make_product(article_number).article_number, article_number)

    def test_unknown_category_code_is_rejected_until_the_category_exists(self) -> None:
        with self.assertRaises(ValidationError) as rejected:
            make_product("X-001", category=category("K"))
        self.assertIn("article_number", rejected.exception.message_dict)

        printing = Category(name="3D-Druck", code="P")
        printing.full_clean()
        printing.save()

        self.assertEqual(make_product("P-001", category=printing).article_number, "P-001")

    def test_malformed_numbers_are_rejected_with_a_message(self) -> None:
        for article_number in ("K005", "K-05", "5-001", "-001"):
            with self.subTest(article_number=article_number):
                with self.assertRaises(ValidationError) as rejected:
                    make_product(article_number, category=category("K"))
                self.assertIn("article_number", rejected.exception.message_dict)

    def test_a_number_that_is_taken_is_rejected(self) -> None:
        make_product("K-005")
        with self.assertRaises(ValidationError) as rejected:
            make_product("K-005")
        self.assertIn("article_number", rejected.exception.message_dict)

    def test_number_must_match_the_category_of_the_product(self) -> None:
        with self.assertRaises(ValidationError):
            make_product("L-001", category=category("K"))

    def test_next_free_number_is_suggested(self) -> None:
        self.assertEqual(suggest_article_number(category("K")), "K-001")
        make_product("K-007")
        self.assertEqual(suggest_article_number(category("K")), "K-008")
        make_product("L-0142")
        self.assertEqual(suggest_article_number(category("L")), "L-0143")
