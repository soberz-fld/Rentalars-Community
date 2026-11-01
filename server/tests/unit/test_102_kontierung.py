# SPDX-License-Identifier: GPL-3.0-or-later
"""The Kontierung of an incoming invoice – tax accounts, the slim row, the sum while typing (DOK-023, DOK-024, DOK-026).

* the tax accounts are master data (SKR 03 start list, editable, a number once, digits only) and a position names one;
* a row asks for description, tax account, kind, net amount, tax rate; the kind of asset only for goods, the useful life
  only for a fixed asset (with the link to the AfA tables); article number, manufacturer and quantity are not asked;
* the net amount of a row is quantity × unit price: changed, the unit price follows;
* the sum under the rows is worked out while typing (an endpoint of its own, nothing is saved).
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse

from rentalars.incoming import services
from rentalars.incoming.forms import split_amount
from rentalars.incoming.models import IncomingInvoice, InvoiceStatus, PositionType
from rentalars.masterdata.models import TaxAccount
from rentalars.material import purchases
from rentalars.material.models import MaterialFile, MaterialFileKind, MaterialItem
from tests.api.base import API, ApiTestCase
from tests.helpers import ALL_RIGHTS, make_model
from tests.ui.base import UiTestCase, form_data
from tests.unit.test_091_purchase import FilesMixin
from tests.unit.test_100_incoming import add, make_invoice, upload

AFA_LINK = "bundesfinanzministerium.de"


class TaxAccountTests(UiTestCase):
    """Master data: the start list of SKR 03, the rules of an account number."""

    def test_the_start_list_is_there_in_german(self) -> None:
        self.assertGreaterEqual(TaxAccount.objects.count(), 30)
        self.assertEqual(TaxAccount.objects.get(number="3400").name, "Wareneingang 19 % Vorsteuer")

    def test_a_number_is_digits_and_exists_once(self) -> None:
        with self.assertRaises(ValidationError):
            TaxAccount(number="34a0", name="x").full_clean()
        with self.assertRaises(ValidationError):
            TaxAccount(number="34", name="x").full_clean()
        with self.assertRaises(ValidationError):
            TaxAccount(number="3400", name="doppelt").full_clean()
        TaxAccount(number="99999", name="Eigenes Konto").full_clean()

    def test_the_administration_links_the_accounts(self) -> None:
        page = self.assert_ok(self.client.get(reverse("core:administration")))
        self.assertIn("Steuerkonten", page)


class RowTests(UiTestCase):
    """The slim row and what it saves."""

    def setUp(self) -> None:
        super().setUp()
        self.invoice = make_invoice()
        self.url = reverse("incoming:detail", args=[self.invoice.pk])

    def test_split_amount_keeps_the_quantity_when_it_fits(self) -> None:
        self.assertEqual(split_amount(Decimal("297.00"), Decimal("3")), (Decimal("3"), Decimal("99.0000")))
        # The unit price would be 0.0000: the position is one piece at the amount.
        self.assertEqual(split_amount(Decimal("0.01"), Decimal("100000")), (Decimal("1"), Decimal("0.01")))
        self.assertEqual(split_amount(Decimal("10.00"), Decimal("0")), (Decimal("1"), Decimal("10.00")))
        self.assertEqual(split_amount(None, Decimal("3")), (Decimal("3"), None))

    def test_the_row_does_not_ask_for_article_quantity_or_manufacturer(self) -> None:
        add(self.invoice, "Shure SM58", "3", "99.00")
        page = self.assert_ok(self.client.get(self.url))
        for gone in ("-article_number", "-manufacturer", "-quantity", "-unit_price_net"):
            self.assertNotIn(gone, page)
        for there in ("-tax_account", "-amount_net", "-tax_rate", "-position_type", "-description"):
            self.assertIn(there, page)
        self.assertIn("Kontierung", page)
        self.assertIn("297,00", page.replace("\xa0", " "))

    def test_changing_the_amount_changes_the_unit_price_and_keeps_the_quantity(self) -> None:
        position = add(self.invoice, "Shure SM58", "3", "99.00")
        data = form_data(self.client.get(self.url), containing="invoice_number")
        data["pos-0-amount_net"] = "330,00"
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        position.refresh_from_db()
        self.assertEqual((position.quantity, position.unit_price_net), (Decimal("3.000"), Decimal("110.0000")))

    def test_the_tax_account_is_saved_and_shown(self) -> None:
        position = add(self.invoice, "Shure SM58", "3", "99.00")
        account = TaxAccount.objects.get(number="3400")
        data = form_data(self.client.get(self.url), containing="invoice_number")
        data["pos-0-tax_account"] = str(account.pk)
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        position.refresh_from_db()
        self.assertEqual(position.tax_account, account)
        self.assertIn("3400", self.assert_ok(self.client.get(self.url)))

    def test_an_inactive_account_is_not_offered_but_stays_where_it_is_used(self) -> None:
        account = TaxAccount.objects.get(number="3400")
        position = add(self.invoice, "Shure SM58", "3", "99.00", tax_account=account)
        other = TaxAccount.objects.get(number="3300")
        TaxAccount.objects.filter(pk__in=[account.pk, other.pk]).update(is_active=False)
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn(f'value="{account.pk}" selected', page)
        self.assertNotIn(f'value="{other.pk}"', page)
        position.refresh_from_db()
        self.assertEqual(position.tax_account, account)

    def test_the_kind_of_asset_and_useful_life_are_shown_by_their_conditions(self) -> None:
        add(self.invoice, "Mischpult", "1", "5000.00")
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn('data-show-if="pos-0-position_type=goods"', page)
        self.assertIn('data-show-if="pos-0-position_type=goods&amp;pos-0-asset_kind=fixed_asset"', page)
        self.assertIn(AFA_LINK, page)
        self.assertIn('rel="noopener"', page)
        # Not a fixed asset: the useful life is hidden when the page is built.
        self.assertRegex(page, r'field-slot hidden" data-show-if="pos-0-position_type=goods&amp;')

    def test_the_weight_is_asked_only_when_spreading_by_weight(self) -> None:
        add(self.invoice, "Mischpult", "1", "5000.00")
        page = self.assert_ok(self.client.get(self.url))
        self.assertRegex(page, r'field-slot hidden" data-show-if="allocation_key=weight"')
        services.update_head(self.invoice, {"allocation_key": "weight"})
        page = self.assert_ok(self.client.get(self.url))
        self.assertNotRegex(page, r'field-slot hidden" data-show-if="allocation_key=weight"')


class SumTests(UiTestCase):
    """The sum while typing."""

    def setUp(self) -> None:
        super().setUp()
        self.invoice = make_invoice()
        services.update_head(self.invoice, {"total_net": Decimal("377.00")})
        add(self.invoice, "Shure SM58", "3", "99.00", tax_rate=Decimal("19"))
        add(self.invoice, "Kabel", "2", "25.00", tax_rate=Decimal("19"))
        self.url = reverse("incoming:kontierung_sum", args=[self.invoice.pk])
        self.detail = reverse("incoming:detail", args=[self.invoice.pk])

    def data(self) -> dict[str, str]:
        return form_data(self.client.get(self.detail), containing="invoice_number")

    def test_the_sum_of_the_saved_lines_is_on_the_page(self) -> None:
        page = self.assert_ok(self.client.get(self.detail)).replace("\xa0", " ")
        self.assertIn("Die Kontierungen ergeben zusammen 347,00 € netto.", page)
        self.assertIn("Abweichung zur Summe netto: -30,00 €", page)

    def test_the_endpoint_works_out_what_is_typed(self) -> None:
        data = self.data()
        data["pos-1-amount_net"] = "80,00"
        text = self.assert_ok(self.client.post(self.url, data)).replace("\xa0", " ")
        self.assertIn("377,00 € netto", text)
        self.assertIn("Steuer 71,63 €, brutto 448,63 €", text)
        self.assertIn("Das ist die Summe netto der Rechnung.", text)
        self.assertIn('id="kontierung-sum"', text)

    def test_nothing_is_saved_by_asking(self) -> None:
        data = self.data()
        data["pos-0-amount_net"] = "1,00"
        self.client.post(self.url, data)
        self.assertEqual(self.invoice.positions.first().line_net, Decimal("297.00"))

    def test_unreadable_values_are_skipped_and_deleted_rows_do_not_count(self) -> None:
        data = self.data()
        data["pos-0-amount_net"] = "abc"
        data["pos-1-DELETE"] = "on"
        text = self.assert_ok(self.client.post(self.url, data)).replace("\xa0", " ")
        self.assertIn("0,00 € netto", text)

    def test_without_a_tax_rate_there_is_no_tax(self) -> None:
        data = self.data()
        data["pos-0-tax_rate"] = ""
        text = self.assert_ok(self.client.post(self.url, data))
        self.assertNotIn("brutto", text)

    def test_the_typed_total_is_compared(self) -> None:
        data = self.data()
        data["total_net"] = "100,00"
        text = self.assert_ok(self.client.post(self.url, data)).replace("\xa0", " ")
        self.assertIn("Abweichung zur Summe netto: 247,00 €", text)

    def test_the_form_asks_for_the_sum_while_typing(self) -> None:
        page = self.assert_ok(self.client.get(self.detail))
        self.assertIn(f'hx-post="{self.url}"', page)
        self.assertIn('hx-target="#kontierung-sum"', page)

    def test_a_get_is_refused(self) -> None:
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_the_pure_sum(self) -> None:
        total = services.kontierung_sum([(Decimal("10.00"), Decimal("19")), (None, None)], None)
        self.assertEqual(
            (total.net, total.tax, total.gross, total.difference),
            (Decimal("10.00"), Decimal("1.90"), Decimal("11.90"), None),
        )
        self.assertIsNone(services.kontierung_sum([(Decimal("10.00"), None)], Decimal("10.00")).tax)


class ApiTests(ApiTestCase):
    """The API names the tax account of a position, and the accounts are a resource."""

    def test_tax_account_of_a_position(self) -> None:
        invoice = make_invoice()
        account = TaxAccount.objects.get(number="4980")
        services.add_position(
            invoice,
            {
                "description": "Gaffa",
                "quantity": Decimal(1),
                "unit_price_net": Decimal(5),
                "tax_account": account,
                "position_type": PositionType.GOODS,
            },
        )
        shown = self.admin.get(f"{API}/incoming-invoices/{invoice.pk}").json()
        self.assertEqual(shown["positions"][0]["tax_account"], account.pk)
        listed = self.admin.get(f"{API}/tax-accounts").json()
        self.assertGreaterEqual(listed["count"], 30)

    def test_a_position_is_created_with_a_tax_account(self) -> None:
        invoice = make_invoice()
        account = TaxAccount.objects.get(number="3400")
        response = self.admin.post(
            f"{API}/incoming-invoices/{invoice.pk}/positions",
            {"description": "Kabel", "quantity": "2", "unit_price_net": "25.00", "tax_account": account.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(invoice.positions.get().tax_account, account)


class TabsTests(FilesMixin, UiTestCase):
    """Buchhaltung: "Beleg erfassen" takes the upload, "Eingangsbelege" is the register."""

    def test_the_tabs_are_there_in_this_order(self) -> None:
        page = self.assert_ok(self.client.get(reverse("incoming:list")))
        self.assertIn(reverse("incoming:capture"), page)
        nav = page[page.index('<nav class="tabs"') :]
        nav = nav[: nav.index("</nav>")]
        self.assertLess(nav.index("Beleg erfassen"), nav.index("Eingangsbelege"))

    def test_the_register_has_no_upload_any_more_but_the_new_boxes(self) -> None:
        make_invoice()
        page = self.assert_ok(self.client.get(reverse("incoming:list")))
        self.assertNotIn(reverse("incoming:upload"), page)
        self.assertIn("Summe der gefilterten Rechnungen", page)
        self.assertNotIn("Summen der gefilterten Rechnungen", page)

    def test_the_capture_page_has_the_upload_box(self) -> None:
        page = self.assert_ok(self.client.get(reverse("incoming:capture")))
        self.assertIn("Rechnung hochladen", page)
        self.assertIn(reverse("incoming:upload"), page)

    def test_a_refused_file_goes_back_to_the_capture_page(self) -> None:
        response = self.client.post(reverse("incoming:upload"), {})
        self.assertRedirects(response, reverse("incoming:capture"))

    def test_after_the_upload_the_question_for_the_material_management_is_asked(self) -> None:
        response = self.client.post(reverse("incoming:upload"), {"file": upload()}, follow=True)
        invoice = IncomingInvoice.objects.get()
        self.assertEqual(response.redirect_chain[-1][0], f"{reverse('incoming:detail', args=[invoice.pk])}?asked=book")
        page = self.assert_ok(response)
        self.assertIn("Auch in der Materialverwaltung einpflegen?", page)
        # No goods are known yet: the page says so; once there are goods, "yes" opens the booking page.
        add(invoice, "Shure SM58", "3", "99.00")
        page = self.assert_ok(self.client.get(f"{reverse('incoming:detail', args=[invoice.pk])}?asked=book"))
        self.assertIn(reverse("incoming:book", args=[invoice.pk]), page)
        plain = self.assert_ok(self.client.get(reverse("incoming:detail", args=[invoice.pk])))
        self.assertNotIn("Auch in der Materialverwaltung einpflegen?", plain)

    def test_the_capture_page_needs_the_right_to_change(self) -> None:
        self.client.logout()
        self.assertIn(self.client.get(reverse("incoming:capture")).status_code, (302, 403))


class RecordPurchaseTests(FilesMixin, UiTestCase):
    """The question after "Kauf einpflegen": the purchase becomes an incoming invoice too."""

    def setUp(self) -> None:
        super().setUp()
        self.mic = make_model("Shure SM58", category_code="T", manufacturer="Shure")
        self.cable = make_model("Kabelmeter", category_code="K")

    def purchase(self, *, invoice: bool = True) -> list[MaterialItem]:
        kept = purchases.keep_invoice(upload(), user=None) if invoice else None
        done = purchases.create_purchase(
            purchases.Head(supplier_name="Musikhaus Muster", invoice_number="RE-77"),
            [
                purchases.Position(model=self.mic, count=3, unit_price=Decimal("99.00")),
                purchases.Position(model=self.cable, count=2, unit_price=Decimal("25.00")),
            ],
            rights=ALL_RIGHTS,
            user=None,
            invoice=kept,
        )
        return done.items

    def ids(self, items: list[MaterialItem]) -> str:
        return purchases.compact_ids([item.inventory_number for item in items])

    def test_the_done_page_asks_and_posts_to_the_register(self) -> None:
        items = self.purchase()
        page = self.assert_ok(self.client.get(reverse("material:purchase_done"), {"items": self.ids(items)}))
        self.assertIn("Auch als Eingangsbeleg in der Buchhaltung erfassen?", page)
        self.assertIn(reverse("incoming:from_purchase"), page)

    def test_no_question_without_an_invoice_file(self) -> None:
        items = self.purchase(invoice=False)
        page = self.assert_ok(self.client.get(reverse("material:purchase_done"), {"items": self.ids(items)}))
        self.assertNotIn(reverse("incoming:from_purchase"), page)

    def test_yes_makes_an_invoice_with_the_positions_linked_to_the_items(self) -> None:
        items = self.purchase()
        response = self.client.post(reverse("incoming:from_purchase"), {"items": self.ids(items)})
        invoice = IncomingInvoice.objects.get()
        self.assertRedirects(response, reverse("incoming:detail", args=[invoice.pk]))
        self.assertEqual((invoice.invoice_number, invoice.supplier_label), ("RE-77", "Musikhaus Muster"))
        positions = list(invoice.positions.order_by("place"))
        self.assertEqual(
            sorted((p.description, p.quantity, p.unit_price_net) for p in positions),
            [("Kabelmeter", Decimal("2"), Decimal("25.00")), ("Shure SM58", Decimal("3"), Decimal("99.00"))],
        )
        self.assertTrue(all(MaterialItem.objects.get(pk=item.pk).source_position_id for item in items))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.BOOKED_IN)
        self.assertEqual(MaterialFile.objects.filter(item__in=items, kind=MaterialFileKind.INVOICE).count(), 5)

    def test_asking_twice_does_not_make_a_second_invoice(self) -> None:
        items = self.purchase()
        self.client.post(reverse("incoming:from_purchase"), {"items": self.ids(items)})
        self.client.post(reverse("incoming:from_purchase"), {"items": self.ids(items)})
        self.assertEqual(IncomingInvoice.objects.count(), 1)
        page = self.assert_ok(self.client.get(reverse("material:purchase_done"), {"items": self.ids(items)}))
        self.assertNotIn(reverse("incoming:from_purchase"), page)

    def test_the_same_file_in_the_register_is_not_made_again(self) -> None:
        existing = make_invoice()
        items = self.purchase()
        response = self.client.post(reverse("incoming:from_purchase"), {"items": self.ids(items)})
        self.assertRedirects(response, reverse("incoming:detail", args=[existing.pk]))
        self.assertEqual(IncomingInvoice.objects.count(), 1)

    def test_a_purchase_without_a_file_is_refused_with_a_message(self) -> None:
        items = self.purchase(invoice=False)
        response = self.client.post(reverse("incoming:from_purchase"), {"items": self.ids(items)}, follow=True)
        self.assertFalse(IncomingInvoice.objects.exists())
        self.assertTrue(self.messages_of(response))

    def test_nothing_named_is_a_message(self) -> None:
        response = self.client.post(reverse("incoming:from_purchase"), {"items": ""}, follow=True)
        self.assertTrue(self.messages_of(response))
