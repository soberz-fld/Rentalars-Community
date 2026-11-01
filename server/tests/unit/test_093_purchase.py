# SPDX-License-Identifier: GPL-3.0-or-later
""" "Kauf einpflegen" – one row to start with, the sum of the positions, "KI-Vorschlag eintragen", and what
the AI reads from the invoice (MAT-075, MAT-076; MAT-061, MAT-062, MAT-059).

* The requirement: by default "Kauf einpflegen" shows only one position, more are added by the AI or the user – one row; "Weitere Position" adds one (without the script by a step that keeps everything); reading
  the invoice adds as many rows as it has positions.
* The requirement: "Kauf einpflegen" shows at the bottom, for cross-checking, the sum (net and gross) of the entered
  positions – net and gross, prices typed net or gross, rows without price counted as 0 and named; next to it the total of
  the invoice and the difference.
* The requirement: after the AI has read the invoice the button is called "KI-Vorschlag eintragen" (not "Vorschlag
  übernehmen"), so that it is clear that nothing is saved at once – the button, a line saying nothing is saved,
  a preview of what was found.
* The requirement: the AI enters serial numbers, category and product, and reads a purchase price like 1.072,50
  correctly (not as 1,07) – serial
  numbers into the row, category and product of a new model from the existing ones (exact or unambiguous only),
  amounts read robustly in the style of the invoice – also without AI.
"""

from __future__ import annotations

import json
from decimal import Decimal

from django.urls import reverse

from rentalars.ai import invoices
from rentalars.masterdata.models import Category
from rentalars.material import purchases
from rentalars.material.models import MaterialItem, MaterialModel
from rentalars.material.purchases import NumberLiteral
from tests.api.base import API, ApiTestCase
from tests.helpers import RentalarsTestCase, category, make_model, make_product, make_user
from tests.ui.base import UiTestCase, form_data
from tests.unit.test_091_purchase import AIMixin, FilesMixin, material_writer, pdf_of, upload

#: An invoice with serial numbers, a price above a thousand and its totals.
INVOICE_LINES = (
    "Musikhaus Muster GmbH & Co. KG",
    "Rechnung Nr. RE-2027-0999",
    "Rechnungsdatum: 22.02.2027",
    "Pos. Artikel Menge Einzelpreis Gesamt",
    "1 Shure SM58 2 99,00 € 198,00 €",
    "SN: SM-001, SM-002",
    "2 Yamaha DM3 Digitalpult 1 1.072,50 € 1.072,50 €",
    "SN: DM3-77",
    "3 Neutrik NL4 Kabel 10 m 2 25,00 € 50,00 €",
    "Nettobetrag 1.320,50 €",
    "MwSt 19 % 250,90 €",
    "Gesamtbetrag 1.571,40 €",
)
INVOICE_TEXT = "\n".join(INVOICE_LINES)


def invoice_upload() -> object:
    return upload(pdf_of(INVOICE_LINES))


def answer(**changes: object) -> str:
    """What a model answers for the invoice above, as the prompt asks: amounts as written."""
    data: dict[str, object] = {
        "supplier": "Musikhaus Muster GmbH & Co. KG",
        "invoice_number": "RE-2027-0999",
        "invoice_date": "2027-02-22",
        "currency": "EUR",
        "prices_include_tax": False,
        "tax_rate": 19,
        "total_net": "1.320,50",
        "total_gross": "1.571,40",
        "positions": [
            {"description": "Shure SM58", "manufacturer": "Shure", "quantity": 2, "unit_price_net": "99,00",
             "serial_numbers": ["SM-001", "SM-002"], "category": "Ton", "product": None},
            {"description": "Yamaha DM3 Digitalpult", "manufacturer": "Yamaha", "quantity": 1,
             "unit_price_net": "1.072,50", "serial_numbers": ["DM3-77"], "category": "Ton > Mischpulte",
             "product": "T-200"},
            {"description": "Neutrik NL4 Kabel 10 m", "manufacturer": "Neutrik", "quantity": 2,
             "unit_price_net": "25,00", "serial_numbers": [], "category": "kabel", "product": "K-999"},
        ],
    }  # fmt: skip
    data.update(changes)
    return json.dumps(data)


# --- Reading amounts ------------------------------------------------------------------------------------------


class AmountTests(RentalarsTestCase):
    """(c) "1.072,50" is 1072.50: German and English amounts, currencies, the ambiguous point (MAT-076)."""

    def test_amounts_in_both_styles(self) -> None:
        cases = [
            # value, German style, English style
            ("1.072,50", "1072.50", "1072.50"),
            ("1072,50", "1072.50", "1072.50"),
            ("1,072.50", "1072.50", "1072.50"),
            ("1072.50", "1072.50", "1072.50"),
            (1072.5, "1072.5", "1072.5"),
            (99, "99", "99"),
            (NumberLiteral("1072.5"), "1072.5", "1072.5"),
            ("1.072,50 €", "1072.50", "1072.50"),
            ("EUR 1.072,50", "1072.50", "1072.50"),
            ("€1,072.50", "1072.50", "1072.50"),
            ("1072.50EUR", "1072.50", "1072.50"),
            ("1 072,50", "1072.50", "1072.50"),
            ("1.072,-", "1072", "1.072"),
            ("1.234.567,89", "1234567.89", "1234567.89"),
            ("1,234,567.89", "1234567.89", "1234567.89"),
            ("12,5", "12.5", "12.5"),
            ("0.125", "0.125", "0.125"),  # a leading zero groups no thousands
            ("1072.505", "1072.505", "1072.505"),  # four digits in front: no thousands group either
            ("-5,00", "-5.00", "-5.00"),
            # Ambiguous: a point or a comma before exactly three digits – the style decides.
            ("1.072", "1072", "1.072"),
            ("1,072", "1.072", "1072"),
            (NumberLiteral("1.072"), "1072", "1.072"),
            ("12.500", "12500", "12.5"),
            # A model that put a point for the comma, or several thousands groups.
            ("1.072.50", "1072.50", "1072.50"),
            ("1.072.500", "1072500", "1072500"),
        ]
        for value, german, english in cases:
            with self.subTest(value=value):
                self.assertEqual(purchases.parse_amount(value), Decimal(german))
                self.assertEqual(purchases.parse_amount(value, decimal_comma=False), Decimal(english))

    def test_no_amount(self) -> None:
        for value in (None, True, "", "abc", "ca. 5", "1e400", "10.72,50", "1,072.5,0", "1.0.0,5", "5.", [], {}):
            with self.subTest(value=value):
                self.assertIsNone(purchases.parse_amount(value))
        self.assertEqual(purchases.parse_decimal_text("1.072,50"), Decimal("1072.50"))  # the old name, in cents

    def test_the_style_of_an_invoice(self) -> None:
        cases = [
            # text, currency, samples, German?
            ("", "", ["99,00"], True),
            ("", "", ["99.00", "1,072.50"], False),
            ("", "", [NumberLiteral("99.0")], True),  # a JSON number says nothing; German by default
            ("Total 1,190.00\nNet 1,000.00", "", [], False),
            ("Gesamtbetrag 1.190,00", "", [], True),
            ("Total due 5", "USD", [], False),
            ("Total due 5 $", "", [], False),
            ("Invoice total 5", "EUR", [], True),  # euro: a point before three digits groups thousands
            ("Invoice quantity unit price total amount due", "", [], False),
            ("Rechnung Menge Einzelpreis", "", [], True),
            ("Gesamtbetrag 1.190,00", "", ["1,072.50"], False),  # the answer's own amounts decide for the answer
        ]
        for text, currency, samples, german in cases:
            with self.subTest(text=text, samples=samples):
                numbers = purchases.invoice_numbers(text, currency=currency, samples=samples)
                self.assertEqual(numbers.decimal_comma, german)

    def test_amounts_are_checked_against_the_invoice(self) -> None:
        numbers = purchases.invoice_numbers(INVOICE_TEXT)
        self.assertEqual(
            numbers.amounts,
            {Decimal(value) for value in ("99", "198", "1072.50", "25", "50", "1320.50", "250.90", "1571.40")},
        )
        cases = [
            ("1.072,50", "1072.50"),
            ("1072,50", "1072.50"),
            (NumberLiteral("1072.5"), "1072.50"),
            (NumberLiteral("1.072"), "1072.50"),  # the cents dropped: the only amount on the invoice with 1072 euros
            (NumberLiteral("1.0725"), "1072.50"),  # the comma dropped: the same digits
            ("1,072.50", "1072.50"),
            (NumberLiteral("99.0"), "99.0"),
            (NumberLiteral("1.07"), "1.07"),  # nothing on the invoice fits better: as read
            ("1.072", "1072.50"),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(numbers.amount(value), Decimal(expected))
        # Two amounts that fit: as read. Without text: as read.
        both = purchases.invoice_numbers("1.072,50\n1.072,90")
        self.assertEqual(both.amount(NumberLiteral("1.072")), Decimal("1072"))
        self.assertEqual(purchases.InvoiceNumbers().amount(NumberLiteral("1.0725")), Decimal("1.0725"))


class TotalsInTextTests(FilesMixin, RentalarsTestCase):
    """The totals of the invoice without AI – the same reading of amounts (MAT-076)."""

    def test_totals_by_their_labels(self) -> None:
        cases = [
            (INVOICE_TEXT, "1320.50", "1571.40"),
            ("Invoice\nSubtotal 1,000.00\nVAT 190.00\nTotal 1,190.00 USD", "1000.00", "1190.00"),
            ("Rechnungsbetrag\n2.380,00 €\nSumme netto 2.000,00 €", "2000.00", "2380.00"),  # the amount on its own line
            ("Pos. Artikel Menge Einzelpreis Gesamt\n1 Mikrofon 2 99,00 € 198,00 €", None, None),  # a heading only
            ("Netto 500,00\nBrutto 100,00", "500.00", None),  # less to pay than net: no amount to pay
            ("Rechnung ohne Summen 22.02.2027", None, None),
        ]
        for text, net, gross in cases:
            with self.subTest(text=text):
                totals = purchases.totals_in_text(text)
                self.assertEqual(totals["net"], Decimal(net) if net else None)
                self.assertEqual(totals["gross"], Decimal(gross) if gross else None)

    def test_the_proposal_without_ai_names_the_totals(self) -> None:
        user = make_user("luka", roles=("Lager",))
        text = purchases.invoice_text(purchases.keep_invoice(invoice_upload(), user=user).path)
        proposal = purchases.proposal_from_text(text)
        self.assertEqual(
            (proposal["total_net"], proposal["total_gross"], proposal["currency"], proposal["invoice_number"]),
            ("1320.50", "1571.40", "EUR", "RE-2027-0999"),
        )
        self.assertEqual(purchases.without_prices(proposal)["total_gross"], "")


# --- The answer of the AI ---------------------------------------------------------------------------------------


class ParseAnswerTests(RentalarsTestCase):
    """(a)–(c): serial numbers, category, product and amounts from the answer, checked strictly (MAT-076)."""

    def test_prices_as_the_invoice_writes_them(self) -> None:
        found = invoices.parse_answer(answer(), invoice_text=INVOICE_TEXT)
        self.assertEqual(
            [position["net"] for position in found["positions"]], [Decimal("99"), Decimal("1072.50"), Decimal("25")]
        )
        self.assertEqual(
            (found["total_net"], found["total_gross"], found["currency"]),
            (Decimal("1320.50"), Decimal("1571.40"), "EUR"),
        )
        self.assertEqual(found["tax_rate"], Decimal("19"))

    def test_the_wrong_reading_of_the_wish(self) -> None:
        """The model wrote 1.072 or 1.0725 as JSON numbers – the invoice says 1.072,50."""
        for literal in ("1.072", "1.0725", "1072.5", '"1.072,50"', '"1072,50"', '"1,072.50"'):
            with self.subTest(literal=literal):
                # Written by hand, to keep the JSON numbers as the model wrote them.
                text = (
                    f'{{"positions": [{{"description": "Yamaha DM3", "quantity": 1, "unit_price_net": {literal}}}, '
                    '{"description": "Shure SM58", "quantity": 2, "unit_price_net": 99.0}]}'
                )
                found = invoices.parse_answer(text, invoice_text=INVOICE_TEXT)
                self.assertEqual(found["positions"][0]["net"], Decimal("1072.50"))
                self.assertEqual(found["positions"][1]["net"], Decimal("99.00"))
        # Without the invoice text a German "1.072" is still one thousand and seventy-two, never 1,07.
        found = invoices.parse_answer('{"positions": [{"description": "X", "unit_price_net": "1.072"}]}')
        self.assertEqual(found["positions"][0]["net"], Decimal("1072.00"))
        found = invoices.parse_answer(
            '{"currency": "USD", "positions": [{"description": "X", "unit_price_net": "1,072"}, '
            '{"description": "Y", "unit_price_net": "5.50"}]}'
        )
        self.assertEqual(found["positions"][0]["net"], Decimal("1072.00"))

    def test_serial_numbers_category_and_product(self) -> None:
        found = invoices.parse_answer(
            answer(
                positions=[
                    {"description": "Shure SM58", "serial_numbers": ["SM-001", "sm-001", " SM-002 ", "XX-999", 77777, None]},
                    {"description": "Yamaha DM3", "serial_numbers": "DM3-77; DM3-78", "category": "Ton\u0000 > Mischpulte",
                     "product": {"x": 1}},
                    {"description": "Kabel", "serial_numbers": {"a": "b"}, "category": 7},
                ]
            ),
            invoice_text=INVOICE_TEXT,
        )  # fmt: skip
        first, second, third = found["positions"]
        self.assertEqual((first["serial_numbers"], first["serials_left_out"]), (["SM-001", "SM-002"], 2))
        self.assertEqual((second["serial_numbers"], second["serials_left_out"]), (["DM3-77"], 1))
        self.assertEqual((second["category"], second["product"]), ("Ton > Mischpulte", ""))
        self.assertEqual((third["serial_numbers"], third["category"]), ([], "7"))
        # Without the invoice text nothing is left out.
        found = invoices.parse_answer(answer(positions=[{"description": "X", "serial_numbers": ["A", "B"]}]))
        self.assertEqual(found["positions"][0]["serial_numbers"], ["A", "B"])

    def test_the_prompt_asks_for_the_fields(self) -> None:
        for key in ("serial_numbers", "category", "product", "total_net", "total_gross", "currency"):
            self.assertIn(f'"{key}"', invoices.SYSTEM_PROMPT)
        self.assertIn("exactly as the invoice writes it", invoices.SYSTEM_PROMPT)
        Category.objects.create(name="Mikrofone", parent=category("T"))
        make_product("T-100", "Funkstrecke SLX")
        categories, products = invoices.catalogue("Funkstrecke")
        self.assertIn("- Ton (T)", categories)
        self.assertIn("- Ton > Mikrofone", categories)
        self.assertNotIn("Veranstaltungstechnik-Dienstleistung", categories)  # no stock of its own
        self.assertNotIn("Fremdmaterial", categories)  # customer material (PRD-043)
        self.assertIn("- T-100 Funkstrecke SLX", products)
        # Many products: only those that share words with the invoice.
        for number in range(invoices.MAX_PRODUCTS + 5):
            make_product(f"K-{number:03d}", f"Kabel {number}")
        _categories, products = invoices.catalogue("Eine Funkstrecke")
        self.assertEqual(products, "- T-100 Funkstrecke SLX")
        self.assertEqual(invoices.catalogue("nichts davon")[1], "(none)")


class ProposalMatchingTests(RentalarsTestCase):
    """(b) Category and product of a new model: only an existing one, named exactly or unambiguously (MAT-076)."""

    def setUp(self) -> None:
        super().setUp()
        self.sound = category("T")
        self.mixers = Category.objects.create(name="Mischpulte", parent=self.sound)
        self.sound_parts = Category.objects.create(name="Zubehör", parent=self.sound)
        self.light_parts = Category.objects.create(name="Zubehör", parent=category("L"))
        self.desk = make_product("T-200", "Digitalpult DM3")
        make_product("T-300", "Kabeltrommel")
        make_product("L-300", "Kabeltrommel")

    def test_categories(self) -> None:
        cases = [
            ("Ton > Mischpulte", self.mixers, ""),
            ("ton/mischpulte", self.mixers, ""),
            ("Ton » Mischpulte", self.mixers, ""),
            ("Mischpulte", self.mixers, ""),
            ("T", self.sound, ""),
            ("Ton (T)", self.sound, ""),
            ("Ton", self.sound, ""),
            ("Zubehör", None, "ambiguous"),
            ("Ton > Zubehör", self.sound_parts, ""),
            ("Mischpult", None, "unknown"),
            ("Fremdmaterial", None, "unknown"),  # not offered: customer material
            ("", None, ""),
        ]
        for text, expected, why in cases:
            with self.subTest(text=text):
                self.assertEqual(purchases.match_category(text), (expected, why))

    def test_products(self) -> None:
        cases = [
            ("T-200", self.desk, ""),
            ("t-200", self.desk, ""),
            ("T-200 Digitalpult DM3", self.desk, ""),
            ("T-200: Digitalpult", self.desk, ""),
            ("Digitalpult DM3", self.desk, ""),
            ("Kabeltrommel", None, "ambiguous"),
            ("K-999", None, "unknown"),
            (None, None, ""),
        ]
        for text, expected, why in cases:
            with self.subTest(text=text):
                self.assertEqual(purchases.match_product(text), (expected, why))
        self.desk.is_active = False
        self.desk.save()
        self.assertEqual(purchases.match_product("T-200"), (None, "unknown"))

    def test_the_proposal(self) -> None:
        mic = make_model("Shure SM58", make_product("T-100", "Gesangsmikrofon"), category_code="T")
        found = invoices.parse_answer(answer(), invoice_text=INVOICE_TEXT)
        found["positions"][0]["serial_numbers"].append("SM-003")  # as if one more was read
        proposal = invoices.proposal_from_answer(found, purchases.proposal_from_text(INVOICE_TEXT))
        first, second, third = proposal["positions"]
        # An existing model brings its category and product, whatever the AI said.
        self.assertEqual(
            (first["model_id"], first["category_id"], first["product"]),
            (mic.pk, self.sound.pk, "T-100 Gesangsmikrofon"),
        )
        self.assertEqual(first["serial_numbers"], ["SM-001", "SM-002", "SM-003"])
        # A new model: what the AI proposed, if it names an existing one.
        self.assertEqual(
            (second["new_model"], second["category"], second["product_id"]), (True, "Ton > Mischpulte", self.desk.pk)
        )
        self.assertEqual((second["unit_price"], second["hints"]), ("1072.50", []))
        self.assertEqual((third["category_id"], third["product_id"]), (category("K").pk, None))
        self.assertEqual(
            third["hints"],
            ["Die KI hat das Produkt „K-999“ vorgeschlagen, das es nicht gibt: Wähle eines oder lass das Feld leer."],
        )
        self.assertEqual((proposal["total_net"], proposal["total_gross"]), ("1320.50", "1571.40"))
        # Totals the model did not read come from the labels of the text.
        found = invoices.parse_answer(answer(total_net=None, total_gross="unknown"), invoice_text=INVOICE_TEXT)
        proposal = invoices.proposal_from_answer(found, purchases.proposal_from_text(INVOICE_TEXT))
        self.assertEqual((proposal["total_net"], proposal["total_gross"]), ("1320.50", "1571.40"))
        # An ambiguous category, serial numbers left out.
        found = invoices.parse_answer(
            answer(positions=[{"description": "Neu", "category": "Zubehör", "serial_numbers": ["XX-1"]}]),
            invoice_text=INVOICE_TEXT,
        )
        hints = purchases.build_proposal(positions=found["positions"])["positions"][0]["hints"]
        self.assertEqual(
            hints,
            [
                "Die KI hat die Kategorie „Zubehör“ vorgeschlagen, die auf mehrere Kategorien passt: Wähle eine selbst.",
                "1 Seriennummer der KI steht nicht auf der Rechnung und wurde weggelassen.",
            ],
        )


# --- The page ---------------------------------------------------------------------------------------------------


class PurchasePageTests(FilesMixin, UiTestCase):
    """One row, "Weitere Position", the sum of the positions (MAT-075; MAT-076)."""

    def setUp(self) -> None:
        super().setUp()
        self.mic = make_model("Shure SM58", category_code="T", manufacturer="Shure")
        self.ties = make_model("Kabelbinder 200 mm", category_code="K", bulk=True)
        self.luka = make_user("luka", roles=("Lager",))
        self.browser = self.browser_of(self.luka)
        self.url = reverse("material:purchase")

    def row(self, index: int, **values: object) -> dict[str, object]:
        return {f"pos-{index}-{name}": value for name, value in values.items()}

    def test_one_row_and_another_position(self) -> None:
        response = self.browser.get(self.url)
        page = self.assert_ok(response)
        data = form_data(response, containing="pos-TOTAL_FORMS")
        self.assertEqual(data["pos-TOTAL_FORMS"], "1")
        self.assertIn("Position 1", page)
        self.assertNotIn("Position 2", page)
        self.assertEqual(page.count("Weitere Position"), 2)  # the script's button and the one that sends the form
        # Without the script: one row more, everything typed and the chosen invoice kept.
        data.update(
            supplier_name="Musikhaus Muster", invoice_number="RE-7", **self.row(0, model_name="Shure SM58", count="2")
        )
        again = self.browser.post(self.url, {**data, "action": "more", "invoice": upload()})
        data = form_data(again, containing="pos-TOTAL_FORMS")
        self.assertEqual(data["pos-TOTAL_FORMS"], "2")
        self.assertEqual(
            (data["supplier_name"], data["invoice_number"], data["pos-0-count"]), ("Musikhaus Muster", "RE-7", "2")
        )
        self.assertTrue(data["upload"])
        self.assertIn("rechnung.pdf", self.assert_ok(again))
        self.assertFalse(MaterialItem.objects.exists())

    def test_the_sum_net_and_gross(self) -> None:
        page = self.assert_ok(self.browser.get(self.url))
        self.assertIn("Summe der Positionen:", page)
        self.assertIn("<span data-sum-net>0,00 €</span> netto", page)
        self.assertIn("<span data-sum-gross>0,00 €</span> brutto", page)
        self.assertIn("mit Steuersatz <span data-sum-rate>19</span> %", page)
        data = form_data(self.browser.get(self.url), containing="pos-TOTAL_FORMS")
        data.update(
            {"pos-TOTAL_FORMS": "5"},
            **self.row(0, model_name="Shure SM58", count="2", unit_price="1.072,50"),  # with thousands separator
            **self.row(1, model_name="Neues Pult", count="1"),  # no price: counts 0
            **self.row(2, model_name="Shure SM58", count="3", unit_price="300,00", price_for_set="on"),  # a set: once
            **self.row(3, model_name="Kabelbinder 200 mm", count="100", unit_price="0,10"),  # bulk: per piece
            **self.row(4, count="1"),  # nobody typed in it: not counted
        )
        page = self.assert_ok(self.browser.post(self.url, {**data, "action": "more"}))
        # 2 × 1.072,50 + 300,00 + 100 × 0,10 = 2.455,00 net; gross with 19 %, rounded once: 2.921,45.
        self.assertIn("<span data-sum-net>2.455,00 €</span> netto", page)
        self.assertIn("<span data-sum-gross>2.921,45 €</span> brutto", page)
        self.assertIn("1 Position ohne Preis – sie zählt mit 0.", page)
        self.assertNotIn("Rechnung:", page)  # no invoice read
        # Prices typed gross (MAT-059): the gross sum adds them, the net one what is stored – each price net.
        data = form_data(self.browser.get(self.url), containing="pos-TOTAL_FORMS")
        data.update(
            {"pos-TOTAL_FORMS": "3", "prices": "gross", "price_tax_rate": "19"},
            **self.row(0, model_name="Shure SM58", count="3", unit_price="10,00"),
            **self.row(1, model_name="Neues Pult"),
            **self.row(2, model_name="Neues Licht", unit_price="abc"),  # no price the form takes
        )
        response = self.browser.post(self.url, {**data, "action": "more"})
        page = self.assert_ok(response)
        self.assertIn("<span data-sum-net>25,20 €</span> netto", page)  # 3 × 8,40
        self.assertIn("<span data-sum-gross>30,00 €</span> brutto", page)
        self.assertIn("2 Positionen ohne Preis – sie zählen mit 0.", page)
        self.assertIn('data-unpriced-one="{count} Position ohne Preis – sie zählt mit 0."', page)
        # The sum stands on the page after a refused save as well.
        data = form_data(response, containing="pos-TOTAL_FORMS")
        page = self.assert_ok(self.browser.post(self.url, {**data, "action": "save"}))
        self.assertIn("<span data-sum-gross>30,00 €</span> brutto", page)

    def test_a_price_with_thousands_separator_is_saved(self) -> None:
        data = form_data(self.browser.get(self.url), containing="pos-TOTAL_FORMS")
        data.update(self.row(0, model_name="Shure SM58", unit_price="1.072,50 €"))
        self.assertEqual(self.browser.post(self.url, {**data, "action": "save"}).status_code, 302)
        self.assertEqual(MaterialItem.objects.get().purchase_price, Decimal("1072.50"))
        data.update(self.row(0, unit_price="1,0725"))
        page = self.assert_ok(self.browser.post(self.url, {**data, "action": "save"}))
        self.assertIn("höchstens 2 Dezimalstellen", page)  # four decimal places: refused, not rounded

    def test_without_the_right_to_purchase_prices_no_sum(self) -> None:
        user = make_user("mats")
        user.roles.add(material_writer())
        browser = self.browser_of(user)
        page = self.assert_ok(browser.get(self.url))
        self.assertNotIn("Summe der Positionen", page)
        data = form_data(browser.get(self.url), containing="pos-TOTAL_FORMS")
        response = browser.post(self.url, {**data, "action": "read", "invoice": invoice_upload()})
        page = self.assert_ok(response)
        self.assertNotIn("1.571,40", page)
        self.assertNotIn("invoice_total_gross", page)

    def test_the_totals_of_the_invoice_read_without_ai(self) -> None:
        data = form_data(self.browser.get(self.url), containing="pos-TOTAL_FORMS")
        response = self.browser.post(self.url, {**data, "action": "read", "invoice": invoice_upload()})
        page = self.assert_ok(response)
        self.assertIn("1.320,50 € netto · 1.571,40 € brutto", page)
        self.assertIn('data-invoice-gross="1571.40"', page)  # for the page script, not in the German format
        self.assertIn("-1.571,40 €</span>", page)  # nothing typed yet
        self.assertIn(
            "Versand, Rabatte und Pfand der Rechnung sind keine Positionen: Sie können eine Differenz erklären.", page
        )
        data = form_data(response, containing="pos-TOTAL_FORMS")
        self.assertEqual((data["invoice_total_net"], data["invoice_total_gross"]), ("1320.50", "1571.40"))
        data.update(
            {"pos-TOTAL_FORMS": "3"},
            **self.row(0, model_name="Shure SM58", count="2", unit_price="99,00"),
            **self.row(1, model_name="Yamaha DM3", unit_price="1.072,50"),
            **self.row(2, model_name="Neutrik NL4", count="2", unit_price="25"),
        )
        response = self.browser.post(self.url, {**data, "action": "more"})
        self.assertIn('class="purchase-sum-ok">stimmt überein</span>', self.assert_ok(response))
        # Removing the invoice takes its totals along.
        data = form_data(response, containing="pos-TOTAL_FORMS")
        response = self.browser.post(self.url, {**data, "action": "drop"})
        self.assertNotIn("Rechnung:", self.assert_ok(response))
        self.assertEqual(form_data(response, containing="pos-TOTAL_FORMS")["invoice_total_gross"], "")


class AIReadingPageTests(AIMixin, FilesMixin, UiTestCase):
    """The AI fills as many rows as the invoice has, with serial numbers, category and product (MAT-076; MAT-075)."""

    def setUp(self) -> None:
        super().setUp()
        self.mic = make_model("Shure SM58", make_product("T-100", "Gesangsmikrofon"), category_code="T")
        self.mixers = Category.objects.create(name="Mischpulte", parent=category("T"))
        self.desk = make_product("T-200", "Digitalpult DM3")
        self.luka = make_user("luka", roles=("Lager",))
        self.browser = self.browser_of(self.luka)
        self.url = reverse("material:purchase")

    def row(self, index: int, **values: object) -> dict[str, object]:
        return {f"pos-{index}-{name}": value for name, value in values.items()}

    def test_the_ai_fills_the_rows(self) -> None:
        self.reading_on(answer())
        data = form_data(self.browser.get(self.url), containing="pos-TOTAL_FORMS")
        response = self.browser.post(self.url, {**data, "action": "read", "invoice": invoice_upload()})
        page = self.assert_ok(response)
        data = form_data(response, containing="pos-TOTAL_FORMS")
        self.assertEqual(data["pos-TOTAL_FORMS"], "3")  # as many rows as positions, the empty one gave way
        self.assertEqual(MaterialItem.objects.count(), 0)
        # The existing model: category and product of the model; the serial numbers of the invoice.
        self.assertEqual((data["pos-0-model_name"], data["pos-0-category"]), ("Shure SM58", str(category("T").pk)))
        self.assertEqual(data["pos-0-product_text"], "T-100 Gesangsmikrofon")
        self.assertEqual(data["pos-0-serial_numbers"].strip().splitlines(), ["SM-001", "SM-002"])
        # A new model: category and product as proposed; the price 1.072,50 as 1072,50, not 1,07.
        self.assertEqual(
            (data["pos-1-model_name"], data["pos-1-category"], data["pos-1-product_text"], data["pos-1-unit_price"]),
            ("Yamaha DM3 Digitalpult", str(self.mixers.pk), "T-200 Digitalpult DM3", "1072,50"),
        )
        self.assertEqual(data["pos-1-serial_numbers"].strip(), "DM3-77")
        # A product that does not exist: left empty, and the row says why.
        self.assertEqual((data["pos-2-category"], data["pos-2-product_text"]), (str(category("K").pk), ""))
        self.assertIn("Die KI hat das Produkt „K-999“ vorgeschlagen, das es nicht gibt", page)
        self.assertIn("Yamaha DM3 Digitalpult · 1 × 1.072,50", page)  # what the invoice said, as it writes it
        # The sum matches the invoice.
        self.assertIn("<span data-sum-net>1.320,50 €</span> netto", page)
        self.assertIn('class="purchase-sum-ok">stimmt überein</span>', page)
        # The prompt named the categories and products to choose from.
        prompt = self.fake.chats[-1]["messages"][-1]["content"]
        self.assertIn("- Ton > Mischpulte", prompt)
        self.assertIn("- T-200 Digitalpult DM3", prompt)
        # Checked and saved: serial numbers, the new model with category and product, the price.
        data.update(self.row(0, confirmed="on"), **self.row(1, confirmed="on"), **self.row(2, confirmed="on"))
        self.assertEqual(self.browser.post(self.url, {**data, "action": "save"}).status_code, 302)
        items = list(MaterialItem.objects.order_by("inventory_number"))
        self.assertEqual([item.serial_number for item in items[:3]], ["SM-001", "SM-002", "DM3-77"])
        desk = MaterialModel.objects.get(name="Yamaha DM3 Digitalpult")
        self.assertEqual((desk.category, desk.default_product), (self.mixers, self.desk))
        self.assertEqual(items[2].purchase_price, Decimal("1072.50"))

    def test_the_preview_and_the_button(self) -> None:
        self.reading_on(answer())
        job = invoices.start(purchases.keep_invoice(invoice_upload(), user=self.luka), user=self.luka)
        page = self.assert_ok(self.browser.get(reverse("material:purchase_reading", args=[job.pk])))
        self.assertIn("Gefunden:</strong> 3 Positionen · Rechnung RE-2027-0999 · Summe 1.571,40 € brutto", page)
        self.assertIn("KI-Vorschlag eintragen", page)
        self.assertNotIn("Vorschlag übernehmen", page)
        self.assertIn("gespeichert wird erst mit „Exemplare anlegen“", page)
        self.assertIn('aria-describedby="purchase-apply-help"', page)
        # Without AI answer: what the text gave, named as such.
        self.reading_on("no json")
        job = invoices.start(purchases.keep_invoice(invoice_upload(), user=self.luka), user=self.luka)
        page = self.assert_ok(self.browser.get(reverse("material:purchase_reading", args=[job.pk])))
        self.assertIn("Gefundenes eintragen", page)
        self.assertIn("0 Positionen · Rechnung RE-2027-0999 · Summe 1.571,40 € brutto", page)
        # Without the right to see purchase prices: no total.
        user = make_user("mats")
        user.roles.add(material_writer())
        self.reading_on(answer())
        job = invoices.start(purchases.keep_invoice(invoice_upload(), user=user), user=user)
        page = self.assert_ok(self.browser_of(user).get(reverse("material:purchase_reading", args=[job.pk])))
        self.assertIn("3 Positionen · Rechnung RE-2027-0999</p>", page)
        self.assertNotIn("1.571,40", page)


class PurchaseInvoiceApiTests(AIMixin, FilesMixin, ApiTestCase):
    """The proposal of the API names totals, serial numbers, category and product (MAT-076; API-002)."""

    def setUp(self) -> None:
        super().setUp()
        Category.objects.create(name="Mischpulte", parent=category("T"))
        self.desk = make_product("T-200", "Digitalpult DM3")
        self.user = make_user("luka", roles=("Lager",))
        self.luka = self.client_of(self.user)

    def test_the_proposal(self) -> None:
        body = self.luka.post(f"{API}/purchases/invoices", {"file": invoice_upload()}, format="multipart").json()
        self.assertEqual((body["proposal"]["total_net"], body["proposal"]["total_gross"]), ("1320.50", "1571.40"))
        self.reading_on(answer())
        body = self.luka.post(f"{API}/purchases/invoices", {"file": invoice_upload()}, format="multipart").json()
        proposal = self.luka.get(f"{API}/jobs/{body['job']}").json()["result"]["proposal"]
        desk = proposal["positions"][1]
        self.assertEqual(
            (desk["unit_price"], desk["serial_numbers"], desk["category"], desk["product_id"]),
            ("1072.50", ["DM3-77"], "Ton > Mischpulte", self.desk.pk),
        )
        self.assertEqual(proposal["total_gross"], "1571.40")
        # AUT-019: without the right to see purchase prices no totals, neither from the text nor from the AI.
        user = make_user("mats")
        user.roles.add(material_writer())
        mats = self.client_of(user)
        body = mats.post(f"{API}/purchases/invoices", {"file": invoice_upload()}, format="multipart").json()
        self.assertEqual((body["proposal"]["total_net"], body["proposal"]["total_gross"]), ("", ""))
        proposal = mats.get(f"{API}/jobs/{body['job']}").json()["result"]["proposal"]
        self.assertEqual((proposal["total_gross"], proposal["positions"][1]["unit_price"]), ("", ""))
        self.assertEqual(proposal["positions"][1]["serial_numbers"], ["DM3-77"])
