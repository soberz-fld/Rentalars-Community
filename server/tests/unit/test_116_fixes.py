# SPDX-License-Identifier: GPL-3.0-or-later
"""The fixes after the review before publishing (docstrings name the requirement each belongs to)."""

from __future__ import annotations

import datetime
import io
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone

from rentalars.core.models import NumberRange, NumberRangeKey
from rentalars.documents import cii as cii_module
from rentalars.documents import einvoice_rules, euer, free, payments, xrechnung
from rentalars.documents.content import from_json
from rentalars.documents.datev import _eu_vat_id
from rentalars.documents.models import DocumentKind
from rentalars.material import book_values, depreciation, sales
from rentalars.material import services as material_services
from rentalars.material.models import ItemStatus, MaterialItem
from tests.helpers import RentalarsTestCase, make_customer, make_item, make_model
from tests.unit.test_060_accounting import AccountingCase

D = Decimal


class NumberRangeTests(RentalarsTestCase):
    """ADM-003: a counter that restarts every year keeps the number somebody entered."""

    def invoice_range(self) -> NumberRange:
        return NumberRange.objects.get(key=NumberRangeKey.INVOICE)

    def test_the_first_number_after_entering_the_counter_is_that_number(self) -> None:
        number_range = self.invoice_range()
        self.assertTrue(number_range.reset_yearly)
        number_range.current_year = None
        number_range.next_value = 154
        number_range.save()
        value, text = NumberRange.allocate(NumberRangeKey.INVOICE)
        self.assertEqual(value, 154)
        self.assertTrue(text.endswith("-0154"), text)
        self.assertEqual(NumberRange.allocate(NumberRangeKey.INVOICE)[0], 155)

    def test_a_counter_set_in_the_middle_of_the_year_is_not_thrown_away(self) -> None:
        number_range = self.invoice_range()
        number_range.current_year = timezone.localdate().year - 1
        number_range.save()
        number_range.next_value = 154
        number_range.save()  # an administrator entering the next number: it belongs to this year
        self.assertEqual(NumberRange.allocate(NumberRangeKey.INVOICE)[0], 154)

    def test_the_counter_of_an_earlier_year_still_starts_again(self) -> None:
        number_range = self.invoice_range()
        NumberRange.objects.filter(pk=number_range.pk).update(
            current_year=timezone.localdate().year - 1, next_value=99, start_value=1
        )
        self.assertEqual(NumberRange.allocate(NumberRangeKey.INVOICE)[0], 1)


class FreeDocumentDateTests(RentalarsTestCase):
    """DOK-040: a document without a project gets today's number – so its date lies in this year and not ahead."""

    def test_a_date_of_last_year_or_the_future_is_refused(self) -> None:
        customer = make_customer()
        today = timezone.localdate()
        for date in (datetime.date(today.year - 1, 12, 31), today + datetime.timedelta(days=1)):
            with self.subTest(date=date), self.assertRaises(ValidationError) as caught:
                free.create_draft(customer, DocumentKind.OFFER, issued_on=date)
            self.assertIn("issued_on", caught.exception.message_dict)

    def test_today_and_earlier_this_year_are_fine(self) -> None:
        customer = make_customer()
        today = timezone.localdate()
        free.create_draft(customer, DocumentKind.OFFER, issued_on=today)
        free.create_draft(customer, DocumentKind.OFFER, issued_on=datetime.date(today.year, 1, 1))

    def test_a_draft_that_waited_over_the_turn_of_the_year_cannot_be_issued_with_its_old_date(self) -> None:
        customer = make_customer()
        draft = free.create_draft(customer, DocumentKind.OFFER, issued_on=timezone.localdate())
        free.DocumentDraft.objects.filter(pk=draft.pk).update(
            issued_on=datetime.date(timezone.localdate().year - 1, 12, 30)
        )
        draft.refresh_from_db()
        self.assertTrue(any("laufenden Jahr" in text for text in free.problems(draft)))


class EuerSurplusTests(AccountingCase):
    """DOK-045: the surplus counts the turnover tax; the result without it stays beside."""

    def test_the_surplus_has_the_turnover_tax_of_the_payments_in_it(self) -> None:
        invoice = self.invoice()  # 291,50 = 250,00 + 41,50 turnover tax
        payments.record(invoice, paid_on=datetime.date(2027, 3, 1), amount=D("291.50"), user=self.user)
        result = euer.compute(2027)
        self.assertEqual(result.profit, D("250.00"))
        self.assertEqual(result.vat_still_owed, D("41.50"))
        self.assertEqual(result.surplus, D("291.50"))
        self.assertEqual(result.as_json()["surplus"], "291.50")

    def test_a_small_business_has_the_profit_as_surplus(self) -> None:
        from rentalars.documents.models import AccountingSettings

        settings = AccountingSettings.load()
        settings.small_business = True
        settings.save()
        payments.record(self.invoice(), paid_on=datetime.date(2027, 3, 1), amount=D("291.50"), user=self.user)
        result = euer.compute(2027)
        self.assertEqual(result.surplus, result.profit)


def asset_item(number: int, quantity: int = 1, cost: str = "1000.00", kind: str = "fixed_asset") -> MaterialItem:
    model = make_model(f"Anlage {number}", category_code="T", bulk=quantity > 1)
    item = make_item(model, number, quantity=quantity) if quantity > 1 else make_item(model, number)
    MaterialItem.objects.filter(pk=item.pk).update(
        asset_kind=kind,
        acquisition_cost_net=D(cost),
        purchase_price=D(cost),
        ancillary_cost_net=D("0.00"),
        purchase_date=datetime.date(2026, 1, 15),
        useful_life_months=60 if kind == "fixed_asset" else None,
    )
    item.refresh_from_db()
    return item


class EuerAssetTests(RentalarsTestCase):
    """DOK-045: what was written off stays written off; an asset that is gone stops depreciating."""

    def test_selling_part_of_a_row_leaves_the_years_before_alone(self) -> None:
        row = asset_item(7001, quantity=10)
        before = euer.compute(2026).depreciation.net
        self.assertGreater(before, D("0"))
        sales.sell(row, sold_on=datetime.date(2027, 2, 15), net_price=D("400.00"), quantity=5, buyer_name="X")
        row.refresh_from_db()
        self.assertEqual(row.acquisition_cost_net, D("500.00"))
        self.assertEqual(euer.compute(2026).depreciation.net, before)  # the sale does not rewrite the year before

    def test_everything_is_written_off_exactly_once(self) -> None:
        row = asset_item(7002, quantity=10)
        sales.sell(row, sold_on=datetime.date(2027, 2, 15), net_price=D("400.00"), quantity=5, buyer_name="X")
        row.refresh_from_db()
        expensed = sum(
            (euer.compute(year).depreciation.net + euer.compute(year).disposals.net for year in (2026, 2027)), D("0")
        )
        left = book_values.value_of(row, datetime.date(2027, 12, 31)).book_value
        self.assertAlmostEqual(expensed + left, D("1000.00"), delta=D("0.02"))

    def test_the_pieces_sold_are_written_off_until_the_day_of_the_sale(self) -> None:
        row = asset_item(7003, quantity=10)
        sales.sell(row, sold_on=datetime.date(2027, 2, 15), net_price=D("400.00"), quantity=5, buyer_name="X")
        part = euer.compute(2027)
        own = [e for e in part.entries if e.kind == euer.DEPRECIATION and "Verkauf" in e.note]
        self.assertEqual(len(own), 1)
        expected = depreciation.valuation(
            "fixed_asset", D("500.00"), datetime.date(2026, 1, 15), 60, datetime.date(2027, 2, 15)
        )
        self.assertEqual(own[0].net, expected.this_year)

    def test_a_lost_asset_stops_depreciating_and_its_book_value_goes_out(self) -> None:
        item = asset_item(7004, cost="1200.00")
        material_services.set_status(item, ItemStatus.LOST, reason="")
        gone_on = timezone.localdate()
        year = gone_on.year
        result = euer.compute(year)
        disposals = [e for e in result.entries if e.kind == euer.DISPOSAL and e.source == "item"]
        self.assertEqual(len(disposals), 1)
        valued = book_values.value_of(item, gone_on)
        self.assertEqual(disposals[0].net, valued.book_value)
        self.assertEqual(euer.compute(year + 1).depreciation.net, D("0.00"))
        self.assertEqual(euer.compute(year + 1).disposals.net, D("0.00"))


class LowValueLimitTests(RentalarsTestCase):
    """MAT-086: a low-value asset (GWG) costs at most the limit of the settings per piece."""

    def test_a_piece_above_the_limit_cannot_be_recorded_as_gwg(self) -> None:
        item = make_item(make_model("Pult", category_code="T"), 7101)
        with self.assertRaises(ValidationError) as caught:
            book_values.set_asset_data(item, kind="low_value", acquisition_cost_net=D("800.01"))
        self.assertIn("asset_kind", caught.exception.message_dict)
        book_values.set_asset_data(item, kind="low_value", acquisition_cost_net=D("800.00"))

    def test_the_limit_is_per_piece_not_per_row(self) -> None:
        model = make_model("Schrauben", category_code="K", bulk=True)
        row = material_services.create_items(model, 1, quantity=10, purchase_date=datetime.date(2026, 1, 15))[0]
        book_values.set_asset_data(row, kind="low_value", acquisition_cost_net=D("5000.00"))  # 500 each
        with self.assertRaises(ValidationError):
            book_values.set_asset_data(row, kind="low_value", acquisition_cost_net=D("9000.00"))  # 900 each


class ReverseChargeTests(AccountingCase):
    """DOK-005: a customer in another EU country owes the tax; the invoice says so and the e-invoice names category AE."""

    def zero_rated(self, vat_id: str):
        if not hasattr(self, "_document"):
            self._document = self.invoice()
        content = from_json(self._document.content)
        for share in content.taxes:
            share.category, share.percent, share.tax = "E", D("0"), D("0.00")
        for position in content.positions:
            position.tax_percent = D("0")
        content.customer_vat_id = vat_id
        return content

    def test_the_rule_is_one_for_the_invoice_and_the_booking(self) -> None:
        self.assertEqual(_eu_vat_id("atu 1234 5678"), "ATU12345678")
        self.assertEqual(_eu_vat_id("DE123456789"), "")
        self.assertEqual(_eu_vat_id(""), "")

    def test_an_eu_customer_without_tax_is_reverse_charge_in_both_formats(self) -> None:
        content = self.zero_rated("ATU12345678")
        self.assertTrue(content.reverse_charge)
        for data in (xrechnung.build_xml(content), cii_module.build_cii(content)):
            text = data.decode("utf-8")
            self.assertIn(">AE<", text)
            self.assertNotIn(">E<", text)
            self.assertIn(
                "Reverse charge", text.replace("Steuerschuldnerschaft des Leistungsempfängers", "Reverse charge")
            )
            report = einvoice_rules.check(data)
            self.assertNotIn("BR-AE-02", {finding.rule for finding in report.findings})

    def test_a_german_or_unknown_customer_stays_exempt(self) -> None:
        for vat_id in ("", "DE123456789"):
            content = self.zero_rated(vat_id)
            self.assertFalse(content.reverse_charge)
            self.assertIn(">E<", xrechnung.build_xml(content).decode("utf-8"))

    def test_a_small_business_has_no_reverse_charge(self) -> None:
        content = self.zero_rated("ATU12345678")
        content.small_business = True
        self.assertFalse(content.reverse_charge)
        self.assertIn(">E<", xrechnung.build_xml(content).decode("utf-8"))

    def test_northern_ireland_is_not_the_eu_for_a_service(self) -> None:
        self.assertEqual(_eu_vat_id("XI123456789"), "")
        self.assertFalse(self.zero_rated("XI123456789").reverse_charge)

    def test_a_stored_document_from_before_keeps_what_it_was(self) -> None:
        document = self.invoice()
        data = dict(document.content)
        data.pop("small_business", None)
        content = from_json(data)
        content.customer_vat_id = "ATU12345678"
        for share in content.taxes:
            share.category = "E"
        self.assertFalse(content.reverse_charge)

    def test_the_seller_needs_a_vat_id_when_the_customer_owes_the_tax(self) -> None:
        content = self.zero_rated("ATU12345678")
        content.company["vat_id"] = ""
        self.assertTrue(any("USt-IdNr" in item for item in xrechnung.missing_data(content)))


class ETaxRateTextTests(AccountingCase):
    """XRechnung and ZUGFeRD: rates without decimals keep their zeros; equal percentages become one sub-total."""

    def test_a_rate_of_twenty_or_a_hundred_percent_is_not_cut(self) -> None:
        from rentalars.core.money import plain_decimal

        self.assertEqual(
            [plain_decimal(value) for value in (D("20"), D("20.00"), D("7.50"), D("100"), D("0.00"), D("19"))],
            ["20", "20", "7.5", "100", "0", "19"],
        )
        content = from_json(self.invoice().content)
        for share in content.taxes:
            share.percent = D("20")
        for position in content.positions:
            position.tax_percent = D("20")
        text = xrechnung.build_xml(content).decode("utf-8")
        self.assertIn("<cbc:Percent>20<", text)
        self.assertNotIn("<cbc:Percent>2<", text)

    def test_two_rates_with_the_same_percentage_give_one_subtotal(self) -> None:
        self.invoice_json = self.invoice().content
        content = from_json(self.invoice_json)
        first = content.taxes[0]
        second = from_json(self.invoice_json).taxes[0]
        second.name = "Umsatzsteuer 19 % (Konto 8401)"
        content.taxes = [first, second]
        self.assertEqual(len(content.tax_groups), 1)
        self.assertEqual(content.tax_groups[0].net, first.net + second.net)
        for data in (xrechnung.build_xml(content), cii_module.build_cii(content)):
            rules = {finding.rule for finding in einvoice_rules.check(data).findings}
            self.assertNotIn("BR-CO-17", rules)
        self.assertEqual(xrechnung.build_xml(content).decode("utf-8").count("<cac:TaxSubtotal>"), 1)


class BookkeepingOffTests(AccountingCase):
    """With "Use Rentalars as accounting software" off nothing of the books runs at night or from the queue."""

    def switch_off(self) -> None:
        from rentalars.core.models import SystemSettings

        row = SystemSettings.load()
        row.invoices_enabled = False
        row.save()

    def test_the_nightly_archive_is_skipped(self) -> None:
        import io

        from django.core.management import call_command

        self.invoice()
        self.switch_off()
        out = io.StringIO()
        call_command("run_daily_maintenance", stdout=out)
        self.assertIn("Archive skipped", out.getvalue())
        self.assertNotIn("Archived", out.getvalue())

    def test_a_transfer_queued_before_does_not_go_out(self) -> None:
        from types import SimpleNamespace

        from rentalars.documents import lexware
        from rentalars.documents.models import LexwareTransfer, TransferState

        document = self.invoice()
        transfer = LexwareTransfer.objects.create(document=document, state=TransferState.QUEUED)
        self.switch_off()
        job = SimpleNamespace(params={"transfer": transfer.pk}, created_by_id=None)
        with self.assertRaises(lexware.LexwareError):
            lexware.run_transfer_job(job)
        transfer.refresh_from_db()
        self.assertEqual((transfer.state, transfer.error_code), (TransferState.FAILED, "switched_off"))


class RentalDaysAcrossClockChangeTests(RentalarsTestCase):
    """Rental days count the hours of the clock, also when the clocks change."""

    def test_a_day_across_the_end_of_summer_time_is_one_day(self) -> None:
        """Saturday 10:00 to Sunday 10:00 on 24/25 October 2026 (25 hours) is 1 rental day, not 2."""
        from zoneinfo import ZoneInfo

        from rentalars.projects.models import started_days

        zone = ZoneInfo("Europe/Berlin")
        begin = datetime.datetime(2026, 10, 24, 10, 0, tzinfo=zone)
        finish = datetime.datetime(2026, 10, 25, 10, 0, tzinfo=zone)
        self.assertEqual(started_days(begin, finish), 1)
        # as read from the database: both values in UTC, or only one of them
        self.assertEqual(started_days(begin.astimezone(datetime.UTC), finish.astimezone(datetime.UTC)), 1)
        self.assertEqual(started_days(begin, finish.astimezone(datetime.UTC)), 1)

    def test_values_without_a_zone_count_as_wall_clock_times(self) -> None:
        from rentalars.projects.models import started_days

        begin = datetime.datetime(2026, 10, 24, 10, 0)
        self.assertEqual(started_days(begin, datetime.datetime(2026, 10, 25, 10, 0)), 1)
        self.assertEqual(started_days(begin, datetime.datetime(2026, 10, 25, 10, 1)), 2)

    def test_a_day_across_the_start_of_summer_time_is_one_day(self) -> None:
        """Saturday 10:00 to Sunday 10:00 on 28/29 March 2026 (23 hours) is 1 rental day."""
        from zoneinfo import ZoneInfo

        from rentalars.projects.models import started_days

        zone = ZoneInfo("Europe/Berlin")
        begin = datetime.datetime(2026, 3, 28, 10, 0, tzinfo=zone)
        finish = datetime.datetime(2026, 3, 29, 10, 0, tzinfo=zone)
        self.assertEqual(started_days(begin.astimezone(datetime.UTC), finish.astimezone(datetime.UTC)), 1)

    def test_one_minute_more_starts_a_new_day(self) -> None:
        """A started day still counts: 10:01 the next day is 2 days."""
        from zoneinfo import ZoneInfo

        from rentalars.projects.models import started_days

        zone = ZoneInfo("Europe/Berlin")
        begin = datetime.datetime(2026, 10, 24, 10, 0, tzinfo=zone)
        finish = datetime.datetime(2026, 10, 25, 10, 1, tzinfo=zone)
        self.assertEqual(started_days(begin.astimezone(datetime.UTC), finish.astimezone(datetime.UTC)), 2)


class LdapNestedGroupFilterTests(RentalarsTestCase):
    """Nested Active Directory groups: the chain rule is a usable group filter (AUT-029)."""

    FILTER = "(&(objectClass=group)(member:1.2.840.113556.1.4.1941:={user_dn}))"

    def test_the_chain_filter_is_accepted_and_escapes_the_distinguished_name(self) -> None:
        """The filter passes the check of the form and takes the DN of the user, brackets escaped."""
        from rentalars.accounts import ldap_client

        ldap_client.validate_filter(self.FILTER, {"{user_dn}"})
        filled = ldap_client.fill_template(self.FILTER, user_dn="CN=Anna (Lager),OU=Leute,DC=firma,DC=example")
        self.assertEqual(
            filled,
            "(&(objectClass=group)(member:1.2.840.113556.1.4.1941:=CN=Anna \\28Lager\\29,OU=Leute,DC=firma,DC=example))",
        )

    def test_without_the_outer_brackets_the_filter_is_refused(self) -> None:
        from rentalars.accounts import ldap_client

        with self.assertRaises(ValidationError):
            ldap_client.validate_filter("member:1.2.840.113556.1.4.1941:={user_dn}", {"{user_dn}"})


class TableLimitTests(RentalarsTestCase):
    """A file that is small as a ZIP but huge once read is refused early."""

    def workbook(self, rows: int) -> io.BytesIO:
        from openpyxl import Workbook

        book = Workbook(write_only=True)
        sheet = book.create_sheet()
        sheet.append(["Name"])
        for number in range(rows):
            sheet.append([f"Zeile {number}"])
        buffer = io.BytesIO()
        book.save(buffer)
        buffer.seek(0)
        return buffer

    def test_too_many_rows_are_refused_while_reading(self) -> None:
        from unittest import mock

        from rentalars.core import tabular

        with mock.patch.object(tabular, "MAX_TABLE_ROWS", 50), self.assertRaises(tabular.ImportFileError) as caught:
            tabular.read_table(self.workbook(60), "daten.xlsx")
        self.assertIn("too big", str(caught.exception).lower().replace("zu groß", "too big"))

    def test_the_limit_of_a_request_stops_the_reading_at_once(self) -> None:
        from rentalars.core import tabular

        with self.assertRaises(tabular.ImportFileError):
            tabular.read_table(self.workbook(30), "daten.xlsx", max_rows=10)

    def test_a_normal_file_is_read_as_before(self) -> None:
        from rentalars.core import tabular

        table = tabular.read_table(self.workbook(30), "daten.xlsx")
        self.assertEqual((len(table.rows), table.headers), (30, ["Name"]))

    def test_empty_formatted_cells_to_the_right_are_not_counted(self) -> None:
        from unittest import mock

        from openpyxl import Workbook

        from rentalars.core import tabular

        book = Workbook()
        sheet = book.active
        sheet.append(["Name", "Preis"])
        for number in range(20):
            sheet.append([f"Zeile {number}", 5])
        sheet["XFD1"].number_format = "0.00"  # formatting only: the row reaches column 16384 in the file
        sheet["XFD3"] = None
        buffer = io.BytesIO()
        book.save(buffer)
        buffer.seek(0)
        with mock.patch.object(tabular, "MAX_TABLE_CELLS", 100):
            table = tabular.read_table(buffer, "daten.xlsx")
        self.assertEqual((len(table.rows), table.headers), (20, ["Name", "Preis"]))

    def test_a_file_that_unpacks_to_too_much_is_refused(self) -> None:
        from unittest import mock

        from rentalars.core import tabular

        with mock.patch.object(tabular, "MAX_UNPACKED_BYTES", 100), self.assertRaises(tabular.ImportFileError):
            tabular.read_table(self.workbook(5), "daten.xlsx")


class StartPageStatusBadgeTests(RentalarsTestCase):
    """A long status on the start page wraps; it must not push the table out of its card."""

    def test_the_badge_in_a_table_of_the_start_page_may_wrap(self) -> None:
        from pathlib import Path

        css = (Path(__file__).resolve().parents[2] / "static" / "css" / "app.css").read_text(encoding="utf-8")
        self.assertIn(".dashboard .table td .badge { white-space: normal;", css)
