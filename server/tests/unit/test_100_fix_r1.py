# SPDX-License-Identifier: GPL-3.0-or-later
"""Review round 1 (R1): accounting and material – the findings that were confirmed and fixed.

Every test names its finding as ``R1-<number>``. They protect: the copy of an invoice (purchase prices), the pieces
booked of a position, the lock of the spread of the ancillary costs, the exchange rate, a new reading of an invoice, the
date of the invoice, the cost of a part sale, negative shares, asset data without a kind, overflowing filters, ambiguous
serial numbers, built-in and sold bulk material, vehicles in projects, what a packing scan tells, the buyer in the
history, and the reading of negative prices and huge totals.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, SpecialRight, rights_of
from rentalars.core.audit import record_event
from rentalars.core.models import AuditLogEntry
from rentalars.customers.models import Customer
from rentalars.incoming import booking, filters, forms, reading, services
from rentalars.incoming.models import IncomingInvoice, InvoicePosition, PositionType
from rentalars.material import book_values, installations, sales, scan
from rentalars.material import services as material_services
from rentalars.material.asset_forms import AssetDataForm
from rentalars.material.history import item_history
from rentalars.material.models import AssetKind, ItemStatus, MaterialFile, MaterialFileKind, MaterialItem
from rentalars.packing import scan as packing_scan
from rentalars.packing import services as packing
from rentalars.projects.logistics import add_vehicle_line
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_line,
    make_item,
    make_model,
    make_product,
    make_project,
    make_user,
)
from tests.ui.base import UiTestCase
from tests.unit.test_091_purchase import FilesMixin, pdf_of
from tests.unit.test_100_incoming import add, goods_invoice, make_invoice, upload

D = Decimal


def role_with(name: str, *, prices: bool) -> Role:
    """A role that keeps the material (up to deleting), with or without the right to see purchase prices."""
    role = Role.objects.create(name=name, module_levels={Module.MATERIAL: int(Level.DELETE)})
    if prices:
        role.special_rights = [SpecialRight.PURCHASE_PRICES]
        role.save()
    return role


def user_with(name: str, *, prices: bool):
    """A user who writes the material, with or without the right to see purchase prices."""
    user = make_user(name)
    user.roles.add(role_with(f"Rolle {name}", prices=prices))
    return user


def book_one(invoice: IncomingInvoice, position: InvoicePosition, model, **entry: object) -> None:
    """Book a position in with all rights."""
    booking.book(invoice, [booking.Entry(position=position, model=model, **entry)], rights=ALL_RIGHTS, user=None)


# --- R1-1: the copy of an invoice needs the right to see purchase prices ------------------------------------------


class InvoiceCopyRightsTests(FilesMixin, UiTestCase):
    """(R1-1) The invoice copy of an item shows the purchase prices: not for who may not see them."""

    def setUp(self) -> None:
        super().setUp()
        invoice = make_invoice()
        position = add(invoice, "Mic", "1", "99.00")
        self.model = make_model("Mic", category_code="T")
        book_one(invoice, position, self.model)
        self.item = MaterialItem.objects.get()
        self.copy = MaterialFile.objects.get(item=self.item, kind=MaterialFileKind.INVOICE)
        self.manual = material_services.add_file(
            self.item, SimpleUploadedFile("a.pdf", pdf_of(("Handbuch",)), "application/pdf"), kind="manual"
        )
        self.reader = Client()
        self.reader.force_login(user_with("ohne", prices=False))
        self.owner = Client()
        self.owner.force_login(user_with("mit", prices=True))

    def test_download_and_list_of_the_page(self) -> None:
        self.assertEqual(self.reader.get(reverse("material:file", args=[self.copy.pk])).status_code, 404)
        self.assertEqual(self.owner.get(reverse("material:file", args=[self.copy.pk])).status_code, 200)
        self.assertEqual(self.reader.get(reverse("material:file", args=[self.manual.pk])).status_code, 200)
        page = self.reader.get(reverse("material:item_files", args=[self.item.pk])).content.decode()
        self.assertIn(reverse("material:file", args=[self.manual.pk]), page)
        self.assertNotIn(reverse("material:file", args=[self.copy.pk]), page)
        self.assertNotIn('value="invoice"', page)  # the kind cannot be chosen either
        shown = self.owner.get(reverse("material:item_files", args=[self.item.pk])).content.decode()
        self.assertIn(reverse("material:file", args=[self.copy.pk]), shown)
        self.assertEqual(self.reader.post(reverse("material:file_delete", args=[self.copy.pk])).status_code, 404)
        self.assertTrue(MaterialFile.objects.filter(pk=self.copy.pk).exists())

    def test_the_files_of_the_model_page_too(self) -> None:
        stored = material_services.add_file(
            self.model, SimpleUploadedFile("r.pdf", pdf_of(("Rechnung",)), "application/pdf"), kind="invoice"
        )
        page = self.reader.get(reverse("material:model_files", args=[self.model.pk])).content.decode()
        self.assertNotIn(reverse("material:file", args=[stored.pk]), page)
        self.assertEqual(self.reader.get(reverse("material:file", args=[stored.pk])).status_code, 404)


class InvoiceCopyApiTests(FilesMixin, ApiTestCase):
    """(R1-1) The same through the API."""

    def test_list_description_content_and_upload(self) -> None:
        invoice = make_invoice()
        position = add(invoice, "Mic", "1", "99.00")
        book_one(invoice, position, make_model("Mic", category_code="T"))
        item = MaterialItem.objects.get()
        copy = MaterialFile.objects.get(item=item, kind=MaterialFileKind.INVOICE)
        reader = self.client_of(user_with("ohne", prices=False))
        owner = self.client_of(user_with("mit", prices=True))
        self.assertEqual(len(owner.get(f"{API}/material-items/{item.pk}/files").json()), 1)
        self.assertEqual(reader.get(f"{API}/material-items/{item.pk}/files").json(), [])
        for path in ("", "/content"):
            self.assertEqual(owner.get(f"{API}/material-files/{copy.pk}{path}").status_code, 200)
            self.assertEqual(reader.get(f"{API}/material-files/{copy.pk}{path}").status_code, 404)
        self.assertEqual(reader.delete(f"{API}/material-files/{copy.pk}").status_code, 404)
        sent = reader.post(
            f"{API}/material-items/{item.pk}/files",
            {"file": SimpleUploadedFile("r.pdf", pdf_of(("x",)), "application/pdf"), "kind": "invoice"},
            format="multipart",
        )
        self.assertEqual(sent.status_code, 403)
        self.assertEqual(owner.delete(f"{API}/material-files/{copy.pk}").status_code, 204)


# --- R1-2: the pieces of a position stay booked when bulk material is built in or sold ------------------------------


class BookedPiecesTests(FilesMixin, RentalarsTestCase):
    """(R1-2) Building in or selling lowers the quantity of the row, not the pieces booked."""

    def setUp(self) -> None:
        super().setUp()
        self.invoice = make_invoice()
        self.position = add(self.invoice, "Kabel 10 m", "10", "2.00")
        self.model = make_model("Kabel", category_code="K", bulk=True)
        self.case = make_item(make_model("Case", category_code="T"), 900)

    def test_install_does_not_make_the_position_look_half_booked(self) -> None:
        book_one(self.invoice, self.position, self.model)
        row = MaterialItem.objects.get(source_position=self.position)
        installations.install_quantity(self.case, row, 4)
        self.assertEqual(services.booked_counts(self.invoice)[self.position.pk], {"rows": 1, "pieces": 10})
        plan = booking.plan(self.invoice, [booking.Entry(position=self.position, model=self.model)], rights=ALL_RIGHTS)
        self.assertFalse(plan.ok)  # booked in twice by accident: refused
        self.assertTrue(plan.rows[0].problems)

    def test_a_sale_of_a_part_does_not_either(self) -> None:
        book_one(self.invoice, self.position, self.model)
        row = MaterialItem.objects.get(source_position=self.position)
        sales.sell(row, sold_on=datetime.date(2027, 2, 1), net_price=D("5.00"), quantity=3, buyer_name="X")
        self.assertEqual(services.booked_counts(self.invoice)[self.position.pk]["pieces"], 10)

    def test_the_second_step_gets_the_right_slice_of_the_price(self) -> None:
        book_one(self.invoice, self.position, self.model, count=6)
        row = MaterialItem.objects.get(source_position=self.position)
        installations.install_quantity(self.case, row, 5)
        plan = booking.plan(self.invoice, [booking.Entry(position=self.position, model=self.model)], rights=ALL_RIGHTS)
        self.assertTrue(plan.ok, plan.problems)
        self.assertEqual((plan.rows[0].start, plan.rows[0].count, plan.rows[0].price), (6, 4, D("8.00")))
        book_one(self.invoice, self.position, self.model)
        total = sum(item.purchase_price for item in MaterialItem.objects.filter(source_position=self.position))
        self.assertEqual(total, D("20.00"))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "booked_in")


# --- R1-3: what the ancillary costs were spread by is frozen once items exist ---------------------------------------


class SpreadLockTests(FilesMixin, RentalarsTestCase):
    """(R1-3) Key, currency, rate and the figures of the spread cannot change after the first booking."""

    def setUp(self) -> None:
        super().setUp()
        self.invoice, self.mic, self.cable = goods_invoice(freight="30.00", key="value")
        self.freight = self.invoice.positions.get(position_type=PositionType.ANCILLARY)
        self.m1 = make_model("Shure", category_code="T")
        self.m2 = make_model("Neutrik", category_code="T")

    def test_the_key_cannot_change(self) -> None:
        book_one(self.invoice, self.mic, self.m1)
        with self.assertRaises(ValidationError) as caught:
            services.update_head(self.invoice, {"allocation_key": "quantity"})
        self.assertIn("allocation_key", caught.exception.message_dict)
        services.update_head(self.invoice, {"allocation_key": "value", "note": "same key is fine"})
        book_one(self.invoice, self.cable, self.m2)
        total = sum(item.ancillary_cost_net for item in MaterialItem.objects.all())
        self.assertEqual(total, D("30.00"))

    def test_the_freight_is_frozen(self) -> None:
        book_one(self.invoice, self.mic, self.m1)
        with self.assertRaises(ValidationError):
            services.update_position(self.freight, {"unit_price_net": D("60.00")})
        with self.assertRaises(ValidationError):
            services.delete_position(self.freight)
        with self.assertRaises(ValidationError):
            add(self.invoice, "More freight", "1", "5.00", position_type=PositionType.ANCILLARY)
        with self.assertRaises(ValidationError):  # nor a goods position whose price the shares are worked out from
            services.update_position(self.cable, {"unit_price_net": D("50.00")})
        with self.assertRaises(ValidationError):
            add(self.invoice, "Another good", "1", "5.00")
        services.update_position(self.cable, {"description": "Cable, renamed", "article_number": "NL4"})  # allowed

    def test_without_ancillary_costs_goods_stay_free(self) -> None:
        invoice, mic, cable = goods_invoice(freight=None)
        book_one(invoice, mic, self.m1)
        services.update_position(cable, {"unit_price_net": D("50.00")})
        add(invoice, "Another good", "1", "5.00")
        with self.assertRaises(ValidationError):  # but no ancillary cost can come later
            add(invoice, "Freight", "1", "5.00", position_type=PositionType.ANCILLARY)

    def test_the_weight_counts_with_the_key_weight(self) -> None:
        services.update_head(self.invoice, {"allocation_key": "weight"})
        services.update_position(self.mic, {"weight_kg": D("1.000")})
        services.update_position(self.cable, {"weight_kg": D("1.000")})
        book_one(self.invoice, self.mic, self.m1)
        with self.assertRaises(ValidationError):
            services.update_position(self.cable, {"weight_kg": D("9.000")})

    def test_the_forms_show_it(self) -> None:
        book_one(self.invoice, self.mic, self.m1)
        head = forms.HeadForm(instance=self.invoice)
        self.assertTrue(head.fields["allocation_key"].disabled)
        self.assertTrue(head.fields["currency"].disabled)
        self.assertTrue(head.fields["exchange_rate"].disabled)
        formset = forms.position_formset(self.invoice)
        by_place = {form.instance.pk: form for form in formset.forms}
        # A row asks for the net amount of the position; quantity and unit price are not on the form any more.
        self.assertTrue(by_place[self.freight.pk].fields["amount_net"].disabled)
        self.assertTrue(by_place[self.cable.pk].fields["amount_net"].disabled)
        self.assertFalse(by_place[self.cable.pk].fields["description"].disabled)
        fresh, _mic, _cable = goods_invoice(freight="30.00")
        self.assertFalse(forms.HeadForm(instance=fresh).fields["allocation_key"].disabled)


# --- R1-4: a foreign currency is never booked 1:1 -------------------------------------------------------------------


class ExchangeRateTests(FilesMixin, ApiTestCase):
    """(R1-4) The rate is entered on purpose."""

    def test_booking_waits_for_the_rate(self) -> None:
        invoice = make_invoice()
        self.assertIsNone(invoice.exchange_rate)
        services.update_head(invoice, {"currency": "USD"})
        position = add(invoice, "Mic", "1", "100.00")
        model = make_model("Mic", category_code="T")
        plan = booking.plan(invoice, [booking.Entry(position=position, model=model)], rights=ALL_RIGHTS)
        self.assertFalse(plan.ok)
        self.assertTrue(any("Umrechnungskurs" in p for p in plan.problems), plan.problems)
        with self.assertRaises(ValidationError):
            book_one(invoice, position, model)
        self.assertFalse(MaterialItem.objects.exists())
        services.update_head(invoice, {"exchange_rate": D("0.9")})
        book_one(invoice, position, model)
        self.assertEqual(MaterialItem.objects.get().purchase_price, D("90.00"))

    def test_a_new_currency_forgets_the_old_rate(self) -> None:
        invoice = make_invoice()
        services.update_head(invoice, {"currency": "USD", "exchange_rate": D("0.9")})
        services.update_head(invoice, {"currency": "GBP", "exchange_rate": D("0.9")})
        invoice.refresh_from_db()
        self.assertEqual((invoice.currency, invoice.exchange_rate), ("GBP", None))
        services.update_head(invoice, {"currency": "EUR"})
        self.assertEqual(invoice.rate, D("1"))

    def test_totals_and_the_api_cope_with_an_empty_rate(self) -> None:
        client = self.client_for("luka", "Lager")
        body = client.post(f"{API}/incoming-invoices", {"file": upload()}, format="multipart").json()
        self.assertIsNone(body["exchange_rate"])
        patched = client.patch(f"{API}/incoming-invoices/{body['id']}", {"currency": "USD"}, format="json")
        self.assertEqual(patched.status_code, 200, patched.content)
        totals = client.get(f"{API}/incoming-invoices/totals").json()
        self.assertEqual((totals["count"], totals["foreign_currency"], totals["net_total"]), (1, 1, "0.00"))
        self.assertEqual((totals["complete"], totals["missing_exchange_rate"]), (False, 1))
        cleared = client.patch(f"{API}/incoming-invoices/{body['id']}", {"exchange_rate": None}, format="json")
        self.assertEqual(cleared.status_code, 200, cleared.content)
        costing = client.get(f"{API}/incoming-invoices/{body['id']}/costing").json()
        self.assertTrue(any("Umrechnungskurs" in p for p in costing["problems"]))


# --- R1-5: a new reading keeps what a person typed ------------------------------------------------------------------


class RereadTests(FilesMixin, RentalarsTestCase):
    """(R1-5) Positions typed or corrected by hand are never replaced by a reading."""

    PROPOSAL = {
        "source": "ai",
        "positions": [
            {"description": "AI row", "quantity": "1.000", "unit_price_net": "1.0000", "kind": "goods"},
            {"description": "typed by hand", "quantity": "3", "unit_price_net": "9.00", "kind": "goods"},
        ],
    }

    def test_typed_and_corrected_positions_stay(self) -> None:
        invoice = make_invoice()
        typed = add(invoice, "typed by hand", "3", "10.00")
        read = reading._position_from(self.PROPOSAL["positions"][0], 2)
        read.invoice = invoice
        read.save()  # what a reading made earlier: not touched by anyone
        self.assertTrue(typed.user_edited)
        self.assertFalse(read.user_edited)
        services.update_position(typed, {"description": "corrected by user", "unit_price_net": D("12.50")})
        added = add(invoice, "added by hand", "1", "5.00")
        reading.apply_proposal(invoice, self.PROPOSAL, replace_positions=True, ai={"model": "x"})
        names = sorted(position.description for position in invoice.positions.all())
        self.assertEqual(names, ["AI row", "added by hand", "corrected by user", "typed by hand"])
        self.assertTrue(InvoicePosition.objects.filter(pk=added.pk).exists())
        self.assertEqual(InvoicePosition.objects.get(pk=typed.pk).unit_price_net, D("12.5000"))

    def test_positions_of_the_reading_alone_are_replaced(self) -> None:
        invoice = make_invoice()
        reading.apply_proposal(invoice, self.PROPOSAL, replace_positions=True)
        self.assertEqual(invoice.positions.count(), 2)
        reading.apply_proposal(invoice, self.PROPOSAL, replace_positions=True)
        self.assertEqual(invoice.positions.count(), 2)  # replaced, not doubled
        self.assertFalse(invoice.positions.filter(user_edited=True).exists())

    def test_a_reading_that_ran_in_the_meantime_does_not_overwrite_the_head(self) -> None:
        invoice = make_invoice()
        stale = IncomingInvoice.objects.get(pk=invoice.pk)  # what the job loaded when it started
        services.update_head(invoice, {"invoice_number": "TYPED-1", "supplier_name": "Eigener Lieferant"})
        proposal = {"source": "ai", "invoice_number": "FROM-AI", "supplier": {"name": "AI Lieferant"}, "positions": []}
        reading.apply_proposal(stale, proposal, replace_positions=True)
        invoice.refresh_from_db()
        self.assertEqual((invoice.invoice_number, invoice.supplier_name), ("TYPED-1", "Eigener Lieferant"))

    def test_a_position_typed_while_the_reading_ran_stays(self) -> None:
        invoice = make_invoice()
        stale = IncomingInvoice.objects.get(pk=invoice.pk)
        add(invoice, "typed meanwhile", "1", "5.00")
        reading.apply_proposal(stale, self.PROPOSAL, replace_positions=True)
        self.assertTrue(invoice.positions.filter(description="typed meanwhile", user_edited=True).exists())


# --- R1-6: the invoice date ------------------------------------------------------------------------------------------


class InvoiceDateWarningTests(FilesMixin, RentalarsTestCase):
    """(R1-6) Booking in without an invoice date warns: no book value can be worked out."""

    def test_warning(self) -> None:
        invoice = make_invoice()
        position = add(invoice, "Mischpult", "1", "700.00")  # below the limit of a GWG (800)
        entry = booking.Entry(position=position, model=make_model("Pult", category_code="T"))
        plan = booking.plan(invoice, [entry], rights=ALL_RIGHTS)
        self.assertTrue(plan.ok, [row.problems for row in plan.rows])
        self.assertTrue(any("Rechnung hat kein Datum" in warning for warning in plan.warnings), plan.warnings)
        services.update_head(invoice, {"invoice_date": datetime.date(2027, 2, 1)})
        self.assertFalse(booking.plan(invoice, [entry], rights=ALL_RIGHTS).warnings)


# --- R1-7, R1-8, R1-9, R1-12: costs of items ----------------------------------------------------------------------


def bulk_row(quantity: int, price: str, share: str, cost: str, **fields: object) -> MaterialItem:
    """A bulk row with all its cost fields set."""
    model = make_model("Schrauben", category_code="K", bulk=True)
    return material_services.create_items(
        model,
        1,
        quantity=quantity,
        purchase_price=D(price),
        ancillary_cost_net=D(share),
        acquisition_cost_net=D(cost),
        asset_kind="low_value",
        purchase_date=datetime.date(2026, 1, 15),
        **fields,
    )[0]


class PartSaleCostTests(RentalarsTestCase):
    """(R1-7, R1-8) The cost of a part is price part plus share part, also for a negative share."""

    def test_no_drift(self) -> None:
        row = bulk_row(3, "10.01", "0.02", "10.03")
        sale = sales.sell(row, sold_on=datetime.date(2027, 2, 1), net_price=D("1.00"), quantity=1, buyer_name="X")
        row.refresh_from_db()
        self.assertEqual(sale.cost, sale.price_part + sale.ancillary_part)
        self.assertEqual(row.acquisition_cost_net, row.purchase_price + row.ancillary_cost_net)
        sales.cancel(sale, reason="x")
        row.refresh_from_db()
        self.assertEqual(
            (row.purchase_price, row.ancillary_cost_net, row.acquisition_cost_net), (D("10.01"), D("0.02"), D("10.03"))
        )

    def test_a_negative_share_is_not_held_at_zero(self) -> None:
        row = bulk_row(4, "100.00", "-8.00", "92.00")
        sale = sales.sell(row, sold_on=datetime.date(2027, 2, 1), net_price=D("1.00"), quantity=1, buyer_name="X")
        row.refresh_from_db()
        self.assertEqual((row.ancillary_cost_net, row.acquisition_cost_net), (D("-6.00"), D("69.00")))
        self.assertEqual((sale.price_part, sale.ancillary_part, sale.cost), (D("25.00"), D("-2.00"), D("23.00")))
        sales.cancel(sale, reason="x")
        row.refresh_from_db()
        self.assertEqual((row.ancillary_cost_net, row.acquisition_cost_net), (D("-8.00"), D("92.00")))


class AssetDataTests(FilesMixin, ApiTestCase):
    """(R1-8, R1-9) Negative shares can be saved; costs without a kind are applied, the cost follows."""

    def item(self, number: int = 700, **fields: object) -> MaterialItem:
        return make_item(make_model(f"Mic {number}", category_code="T"), number, **fields)

    def test_a_negative_share_form_and_service(self) -> None:
        item = self.item(purchase_price=D("100.00"), ancillary_cost_net=D("-3.00"), acquisition_cost_net=D("97.00"),
                         asset_kind="low_value")  # fmt: skip
        form = AssetDataForm(
            {"asset_kind": "low_value", "useful_life_months": "", "ancillary_cost_net": "-3,00", "acquisition_cost_net": "97,00"},
            item=item,
        )  # fmt: skip
        self.assertTrue(form.is_valid(), form.errors)
        book_values.set_asset_data(item, kind="low_value", ancillary_cost_net=D("-5.00"))
        item.refresh_from_db()
        self.assertEqual((item.ancillary_cost_net, item.acquisition_cost_net), (D("-5.00"), D("95.00")))
        with self.assertRaises(ValidationError) as caught:
            book_values.set_asset_data(item, kind="low_value", ancillary_cost_net=D("-150.00"))
        self.assertIn("acquisition_cost_net", caught.exception.message_dict)

    def test_costs_without_a_kind_are_not_ignored(self) -> None:
        item = self.item(purchase_price=D("100.00"))
        book_values.set_asset_data(item, kind="", ancillary_cost_net=D("5.00"))
        item.refresh_from_db()
        self.assertEqual(
            (item.asset_kind, item.ancillary_cost_net, item.acquisition_cost_net), ("", D("5.00"), D("105.00"))
        )
        book_values.set_asset_data(item, kind="", acquisition_cost_net=D("120.00"))
        item.refresh_from_db()
        self.assertEqual(item.acquisition_cost_net, D("120.00"))

    def test_the_cost_follows_a_changed_share_even_when_the_card_sends_the_old_total(self) -> None:
        item = self.item(purchase_price=D("100.00"), ancillary_cost_net=D("10.00"), acquisition_cost_net=D("110.00"),
                         asset_kind="low_value")  # fmt: skip
        book_values.set_asset_data(
            item, kind="low_value", ancillary_cost_net=D("20.00"), acquisition_cost_net=D("110.00")
        )
        item.refresh_from_db()
        self.assertEqual((item.ancillary_cost_net, item.acquisition_cost_net), (D("20.00"), D("120.00")))
        book_values.set_asset_data(
            item, kind="low_value", ancillary_cost_net=D("20.00"), acquisition_cost_net=D("130.00")
        )
        item.refresh_from_db()
        self.assertEqual(item.acquisition_cost_net, D("130.00"))  # a total that was changed on purpose is taken

    def test_the_api(self) -> None:
        item = self.item(purchase_price=D("100.00"))
        url = f"{API}/material-items/{item.pk}/asset"
        done = self.admin.patch(url, {"ancillary_cost_net": "-4.00"}, format="json")  # no kind yet
        self.assertEqual(done.status_code, 200, done.content)
        item.refresh_from_db()
        self.assertEqual((item.ancillary_cost_net, item.acquisition_cost_net), (D("-4.00"), D("96.00")))
        refused = self.admin.patch(url, {"asset_kind": "low_value", "ancillary_cost_net": "-400.00"}, format="json")
        self.assertEqual(refused.status_code, 400)

    def test_an_edited_purchase_price_changes_the_cost(self) -> None:
        item = self.item(purchase_price=D("100.00"), ancillary_cost_net=D("10.00"), acquisition_cost_net=D("110.00"),
                         asset_kind="low_value")  # fmt: skip
        item = MaterialItem.objects.get(pk=item.pk)
        item.purchase_price = D("120.00")
        item.save()
        item.refresh_from_db()
        self.assertEqual(item.acquisition_cost_net, D("130.00"))
        self.assertEqual(book_values.cost_of(item), D("130.00"))
        # a cost that was set on purpose (differs from price plus share) is left alone
        item.acquisition_cost_net = D("500.00")
        item.save()
        item = MaterialItem.objects.get(pk=item.pk)
        item.purchase_price = D("90.00")
        item.save()
        item.refresh_from_db()
        self.assertEqual(item.acquisition_cost_net, D("500.00"))
        # also through the API
        other = self.item(701, purchase_price=D("50.00"), ancillary_cost_net=D("5.00"), acquisition_cost_net=D("55.00"))
        response = self.admin.patch(f"{API}/material-items/{other.pk}", {"purchase_price": "60.00"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        other.refresh_from_db()
        self.assertEqual(other.acquisition_cost_net, D("65.00"))


# --- R1-10: filters that overflow ----------------------------------------------------------------------------------


class FilterOverflowTests(FilesMixin, ApiTestCase):
    """(R1-10) A number beyond 2^31-1 is no ID: ignored on the page, 400 in the API."""

    HUGE = "9" * 40

    def test_parse(self) -> None:
        found = book_values.parse({"location": self.HUGE, "model": str(2**31)})
        self.assertEqual((found.location, found.model), (None, None))
        self.assertEqual(set(found.errors), {"location", "model"})
        self.assertEqual(book_values.parse({"model": str(2**31 - 1)}).model, 2**31 - 1)
        found = filters.parse({"supplier": self.HUGE})
        self.assertEqual((found.supplier, set(found.errors)), (None, {"supplier"}))

    def test_pages_and_api(self) -> None:
        page = Client()
        page.force_login(make_user("chef", superuser=True))
        for name, key in (("material:asset_register", "location"), ("material:asset_register", "model"),
                          ("incoming:list", "supplier")):  # fmt: skip
            self.assertEqual(page.get(reverse(name), {key: self.HUGE}).status_code, 200, (name, key))
        for path, key in (("asset-register", "location"), ("incoming-invoices", "supplier")):
            response = self.admin.get(f"{API}/{path}", {key: self.HUGE})
            self.assertEqual(response.status_code, 400, (path, response.content))


# --- R1-11: serial numbers that are not unique ----------------------------------------------------------------------


class AmbiguousSerialTests(RentalarsTestCase):
    """(R1-11) A serial number of several items is ambiguous – unless the packing list names one."""

    def setUp(self) -> None:
        super().setUp()
        self.product = make_product("L-010", "PAR 64")
        self.other_product = make_product("L-011", "Spot")
        self.par = make_item(make_model("PAR 64", self.product, category_code="L"), 10, serial_number="SN-1")
        self.spot = make_item(make_model("Spot", self.other_product, category_code="L"), 11, serial_number="sn-1")

    def test_the_resolver_says_ambiguous(self) -> None:
        result = scan.resolve("SN-1")
        self.assertEqual(result.kind, scan.NONE)
        self.assertIn("0010", result.message)
        self.assertIn("0011", result.message)
        self.assertEqual(scan.resolve("0010").item, self.par)  # the ID is unique
        chosen = scan.resolve("SN-1", prefer=lambda item: item.pk == self.spot.pk)
        self.assertEqual(chosen.item, self.spot)
        self.assertEqual(
            scan.resolve("SN-1", prefer=lambda item: True).kind, scan.NONE
        )  # both preferred: still ambiguous
        # nobody without the right to read the material is told the IDs
        self.assertEqual(scan.resolve("SN-1", rights=rights_of(make_user("niemand"))).kind, scan.NONE)

    def test_the_packing_prefers_the_item_of_the_list(self) -> None:
        project = make_project("Stadtfest")
        add_line(project, self.other_product, 1)
        packlist = packing.get_packlist(project)
        outcome = packing_scan.scan_pack(packlist, "SN-1")
        self.assertEqual((outcome.status, outcome.item), ("packed", "0011"))


# --- R1-13: bulk material built in or sold ---------------------------------------------------------------------------


class BulkChecksTests(RentalarsTestCase):
    """(R1-13) The locked row decides, and what projects have out is not free."""

    def setUp(self) -> None:
        super().setUp()
        self.product = make_product("K-600", "Kabel")
        self.row = make_item(make_model("Kabel", self.product, bulk=True), 600, quantity=10)
        self.case = make_item(make_model("Case", category_code="T"), 900)

    def test_the_status_is_taken_from_the_locked_row(self) -> None:
        stale = MaterialItem.objects.get(pk=self.row.pk)
        MaterialItem.objects.filter(pk=self.row.pk).update(status=ItemStatus.DEFECTIVE)
        with self.assertRaises(ValidationError):
            installations.install_quantity(self.case, stale, 2)
        self.assertEqual(MaterialItem.objects.get(pk=self.row.pk).quantity, 10)

    def test_what_is_out_with_a_project_is_not_free(self) -> None:
        project = make_project("Stadtfest")
        add_line(project, self.product, 6)
        packlist = packing.get_packlist(project)
        packing.pack_all(packlist)
        packing.issue(packlist)
        self.assertEqual(installations.free_quantity(MaterialItem.objects.get(pk=self.row.pk)), 4)
        with self.assertRaises(ValidationError) as caught:
            installations.install_quantity(self.case, self.row, 5)
        self.assertIn("4", " ".join(caught.exception.message_dict["quantity"]))
        problems = sales.preview(
            MaterialItem.objects.get(pk=self.row.pk), quantity=5, sold_on=datetime.date(2027, 3, 1), net_price=D("1")
        ).problems
        self.assertTrue(problems)
        installations.install_quantity(self.case, self.row, 4)


class BulkApiTests(ApiTestCase):
    """(R1-13) 3.9 is no quantity."""

    def test_a_fraction_is_refused_not_cut(self) -> None:
        row = make_item(make_model("Kabel", category_code="K", bulk=True), 600, quantity=10)
        case = make_item(make_model("Case", category_code="T"), 900)
        url = f"{API}/material-items/{case.pk}/built-in"
        for bad in (3.9, "3.9", True, "x"):
            response = self.admin.post(url, {"material": row.pk, "quantity": bad}, format="json")
            self.assertEqual(response.status_code, 400, (bad, response.content))
        self.assertEqual(MaterialItem.objects.get(pk=row.pk).quantity, 10)
        for good in (3, "3", 3.0):
            response = self.admin.post(url, {"material": row.pk, "quantity": good}, format="json")
            self.assertEqual(response.status_code, 201, (good, response.content))
        self.assertEqual(MaterialItem.objects.get(pk=row.pk).quantity, 1)
        bad = self.admin.post(f"{url}/{row.pk}/remove", {"quantity": 1.5}, format="json")
        self.assertEqual(bad.status_code, 400)


# --- R1-14: a vehicle booked in a project --------------------------------------------------------------------------


class VehicleSaleTests(RentalarsTestCase):
    """(R1-14) Selling a vehicle that a project has booked asks for confirmation."""

    def test_warning(self) -> None:
        from rentalars.products.models import ProductKind, VehicleType

        product = make_product(
            "S-900",
            "Sprinter",
            price=None,
            kind=ProductKind.VEHICLE,
            vehicle_type=VehicleType.CAR,
            price_per_km=D("0.80"),
        )
        van = make_item(make_model("Sprinter", product), 801)
        project = make_project("Tour")
        add_vehicle_line(project, rights=ALL_RIGHTS, product=product, item=van)
        warnings = sales.warnings_of(van)
        self.assertTrue(any(project.number in warning for warning in warnings), warnings)
        with self.assertRaises(ValidationError):
            sales.sell(van, sold_on=datetime.date(2027, 3, 1), net_price=D("100"), buyer_name="X")
        sale = sales.sell(
            van, sold_on=datetime.date(2027, 3, 1), net_price=D("100"), buyer_name="X", accept_warnings=True
        )
        self.assertEqual(sale.item.status, ItemStatus.SOLD)


# --- R1-15: what a packing scan tells ---------------------------------------------------------------------------------


class PackingScanSecrecyTests(RentalarsTestCase):
    """(R1-15) Someone who may pack but not read the material learns nothing of other items."""

    def setUp(self) -> None:
        super().setUp()
        self.product = make_product("L-010", "PAR 64")
        self.on_list = make_item(make_model("PAR 64", self.product, category_code="L"), 1)
        self.secret_product = make_product("L-099", "Geheimes Gerät")
        self.secret = make_item(
            make_model("Geheim", self.secret_product, category_code="L"), 2, status=ItemStatus.DEFECTIVE
        )
        self.loose = make_item(make_model("Lose", category_code="L"), 3)
        project = make_project("Stadtfest")
        add_line(project, self.product, 1)
        self.packlist = packing.get_packlist(project)
        crew = make_user("crew")
        role = Role.objects.create(name="Packen", module_levels={Module.PROJECTS: int(Level.READ)})
        crew.roles.add(role)
        self.crew = rights_of(crew)
        self.assertFalse(self.crew.can_read(Module.MATERIAL))

    def test_items_outside_the_list_are_unknown(self) -> None:
        for code in ("0002", "0003", "L-099"):
            outcome = packing_scan.scan_pack(self.packlist, code, rights=self.crew)
            self.assertEqual(outcome.status, "unknown", code)
            self.assertNotIn("Geheim", outcome.message)
            self.assertNotIn("defekt", outcome.message.lower())
        again = packing_scan.scan_pack(self.packlist, "9999", rights=self.crew)
        self.assertEqual(
            again.message.replace("9999", "0002"),
            packing_scan.scan_pack(self.packlist, "0002", rights=self.crew).message,
        )
        # Whoever reads the material still gets the reason; the item of the list works for the crew as well.
        self.assertEqual(packing_scan.scan_pack(self.packlist, "0002", rights=ALL_RIGHTS).status, "not_on_list")
        self.assertEqual(packing_scan.scan_pack(self.packlist, "0001", rights=self.crew).status, "packed")
        self.assertEqual(packing_scan.scan_return(self.packlist, "0002", rights=self.crew).status, "unknown")


# --- R1-16: the buyer in the history ----------------------------------------------------------------------------------


class BuyerPrivacyTests(RentalarsTestCase):
    """(R1-16) The history and the reason of the status name no buyer; forgetting works by exact places."""

    def sell_to(self, number: int, customer: Customer, name: str = "") -> sales.SaleFromStock:
        item = make_item(make_model(f"Pult {number}", category_code="T"), number, purchase_price=D("100"))
        return sales.sell(
            item, sold_on=datetime.date(2027, 3, 1), net_price=D("50"), customer=customer, buyer_name=name
        )

    def test_no_buyer_in_the_history_or_the_reason(self) -> None:
        customer = Customer.objects.create(name="Hans Meier")
        sale = self.sell_to(30, customer)
        item = MaterialItem.objects.get(pk=sale.item_id)
        self.assertNotIn("Meier", item.status_reason)
        texts = [row.summary for row in item_history(item, rights_of(make_user("leser")))]
        self.assertTrue(texts)
        self.assertFalse([text for text in texts if "Meier" in text], texts)
        for entry in AuditLogEntry.for_object(item, include_children=False):
            self.assertNotIn("Meier", str(entry.changes))
        sales.cancel(sale, reason="x")
        self.assertFalse([row.summary for row in item_history(item, ALL_RIGHTS) if "Meier" in row.summary])

    def test_forgetting_replaces_exact_places_only(self) -> None:
        customer = Customer.objects.create(name="Max")
        sale = self.sell_to(31, customer)
        item = MaterialItem.objects.get(pk=sale.item_id)
        # What an older version wrote: the buyer in the event and in the reason of the status.
        legacy = "Verkauft am 01.03.2027 an Max"
        item.status_reason = legacy
        item.save()
        record_event(item, "item.sold_from_stock", {"buyer": "Max", "date": "2027-03-01", "quantity": 1})
        other = make_item(make_model("Andere", category_code="T"), 32, status_reason="Max Mustermann ist schuld")
        other.save()
        record_event(other, "item.sold_from_stock", {"buyer": "Maxim", "date": "2027-03-01", "quantity": 1})
        customer.name = "Anonym 7"
        sales.forget_customer(customer)
        item.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(item.status_reason, "Verkauft am 01.03.2027")
        self.assertEqual(other.status_reason, "Max Mustermann ist schuld")  # a substring is no buyer
        events = {
            entry.object_id: entry.changes["buyer"]
            for entry in AuditLogEntry.objects.filter(
                event="item.sold_from_stock", object_id__in=[str(item.pk), str(other.pk)]
            )
            if "buyer" in entry.changes  # the event of the sale itself (since the review) names no buyer
        }
        self.assertEqual(events, {str(item.pk): "Anonym 7", str(other.pk): "Maxim"})
        logged = [str(entry.changes) for entry in AuditLogEntry.for_object(item, include_children=False)]
        self.assertFalse([text for text in logged if "an Max" in text], logged)


class SaleCustomerTests(ApiTestCase):
    """(R1-18) Only an active customer can buy."""

    def test_api_and_service(self) -> None:
        inactive = Customer.objects.create(name="Alt GmbH", is_active=False)
        item = make_item(make_model("Pult", category_code="T"), 40, purchase_price=D("100"))
        body = {"sold_on": "2027-03-01", "net_price": "10.00", "customer": inactive.pk}
        response = self.admin.post(f"{API}/material-items/{item.pk}/sell", body, format="json")
        self.assertEqual(response.status_code, 400, response.content)
        with self.assertRaises(ValidationError):
            sales.resolve_buyer(inactive, None, "")


# --- R1-18: reading ----------------------------------------------------------------------------------------------------


class ReadingLimitsTests(FilesMixin, UiTestCase):
    """(R1-18) Negative goods prices, huge totals and the useful life of a low-value asset."""

    def test_a_negative_goods_price_is_dropped_with_a_note(self) -> None:
        invoice = make_invoice()
        proposal = {
            "source": "ai",
            "positions": [
                {"description": "Rabatt", "quantity": "1", "unit_price_net": "-5.00", "kind": "goods"},
                {"description": "Nachlass", "quantity": "1", "unit_price_net": "-3.00", "kind": "cost"},
            ],
        }
        reading.apply_proposal(invoice, proposal, replace_positions=True)
        goods, cost = invoice.positions.order_by("place")
        self.assertIsNone(goods.unit_price_net)
        self.assertTrue(goods.suggestion["hints"])
        self.assertEqual((cost.position_type, cost.unit_price_net), (PositionType.ANCILLARY, D("-3.0000")))

    def test_a_huge_total_is_left_out(self) -> None:
        invoice = make_invoice()
        reading.apply_proposal(invoice, {"source": "text", "total_net": "123456789012.00", "positions": []})
        invoice.refresh_from_db()
        self.assertIsNone(invoice.total_net)
        self.assertTrue(invoice.reading["note"])

    def test_the_pages_and_the_api_answer_no_error_page(self) -> None:
        lines = (
            "Firma X GmbH",
            "Rechnung Nr. R-1",
            "Summe netto 12.345.678.901.234,00 €",
            "Summe brutto 12.345.678.901.234,00 €",
        )
        invoice = services.create_from_upload(SimpleUploadedFile("r.pdf", pdf_of(lines), "application/pdf"), user=None)
        self.assertIsNone(invoice.total_net)
        page = self.client.post(reverse("incoming:read", args=[invoice.pk]))
        self.assertEqual(page.status_code, 302)

    def test_the_useful_life_belongs_to_fixed_assets(self) -> None:
        invoice = make_invoice()
        add(invoice, "Kabel", "10", "5.00", asset_kind="", useful_life_months=24)
        add(invoice, "Pult", "1", "1500.00", asset_kind="", useful_life_months=24)
        from rentalars.incoming import costing

        rows = {row.position.description: row for row in costing.costing_of(invoice).rows}
        self.assertEqual((rows["Kabel"].kind, rows["Kabel"].useful_life), (AssetKind.LOW_VALUE, None))
        self.assertEqual((rows["Pult"].kind, rows["Pult"].useful_life), (AssetKind.FIXED_ASSET, 24))


class ReadingApiTests(FilesMixin, ApiTestCase):
    """(R1-18) Reading again through the API answers 200, not a server error."""

    def test_the_api_answers_no_error_either(self) -> None:
        lines = (
            "Firma X GmbH",
            "Rechnung Nr. R-1",
            "Summe netto 12.345.678.901.234,00 €",
            "Summe brutto 12.345.678.901.234,00 €",
        )
        invoice = services.create_from_upload(
            SimpleUploadedFile("r.pdf", pdf_of(lines), "application/pdf"), user=None, read=False
        )
        answer = self.admin.post(f"{API}/incoming-invoices/{invoice.pk}/read", {}, format="json")
        self.assertEqual(answer.status_code, 200, answer.content)
