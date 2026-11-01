# SPDX-License-Identifier: GPL-3.0-or-later
"""The overall discount of a project (PRJ-123).

The requirement: an overall discount in projects, as a percentage or in euros.

* A project can carry one discount on the whole: a percentage or an amount, never both. It is taken off the net
  total of the project – after groups, personnel, vehicles and surcharges – and lowers every tax rate in the same
  proportion, so net, tax and gross keep fitting together.
* It is set in a dialog of the planning page (who may edit the project and set prices), through the API
  (`overall_discount_percent` / `overall_discount_amount` of `/projects`), shown in the totals, the price overview
  (page, PDF, CSV) and on offers, order confirmations and invoices, and copied with a duplicate.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.accounts.rights import ProjectScope, Rights, rights_of
from rentalars.documents import content as builder
from rentalars.documents import services as document_services
from rentalars.documents import xrechnung
from rentalars.masterdata.models import TaxRate
from rentalars.projects import services
from rentalars.projects.duplicate import duplicate_project
from rentalars.projects.models import Project, ProjectStatus
from rentalars.projects.price_pdf import render_price_overview_csv
from rentalars.projects.pricing import compute_project_prices
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_group,
    add_line,
    at,
    make_product,
    make_project,
    ready_for_invoices,
)
from tests.ui.base import UiTestCase

D = Decimal


def mixed_project(**fields: object) -> Project:
    """100,00 at 19 % and 50,00 tax free: net 150,00."""
    project = make_project(rental_days=1, **fields)
    tax_free = TaxRate.objects.get(rate=0)
    add_line(project, make_product("L-001", price="100.00", billing_mode="flat"), 1)
    add_line(project, make_product("L-002", price="50.00", billing_mode="flat", tax_rate=tax_free), 1)
    return project


def no_price_rights() -> Rights:
    """The rights of a user who plans projects but may not see or set prices."""
    from tests.helpers import make_user

    Role.objects.get_or_create(
        name="Planung ohne Preise", defaults={"module_levels": {"projects": 2}, "special_rights": []}
    )
    return rights_of(make_user("ohnepreise", roles=("Planung ohne Preise",)))


class CalculationTests(RentalarsTestCase):
    """The sums."""

    def test_nothing_without_a_discount(self) -> None:
        prices = compute_project_prices(mixed_project())
        self.assertEqual(
            (prices.overall_discount, prices.net_total, prices.net_before_overall_discount),
            (D(0), D("150.00"), D("150.00")),
        )

    def test_percent_is_taken_off_the_whole_sum(self) -> None:
        project = mixed_project(overall_discount_percent=D("10"))
        prices = compute_project_prices(project)
        self.assertEqual(
            (prices.net_before_overall_discount, prices.overall_discount, prices.net_total),
            (D("150.00"), D("15.00"), D("135.00")),
        )
        # Every tax rate carries its share: 90,00 at 19 % and 45,00 tax free.
        by_rate = {str(line.tax_rate.rate): (line.net, line.tax) for line in prices.tax_lines}
        self.assertEqual(by_rate, {"19.00": (D("90.00"), D("17.10")), "0.00": (D("45.00"), D("0.00"))})
        self.assertEqual((prices.tax_total, prices.gross_total), (D("17.10"), D("152.10")))

    def test_amount_is_taken_as_it_is_and_never_more_than_the_sum(self) -> None:
        project = mixed_project(overall_discount_amount=D("30.00"))
        prices = compute_project_prices(project)
        self.assertEqual((prices.overall_discount, prices.net_total), (D("30.00"), D("120.00")))
        self.assertEqual(sum(line.net for line in prices.tax_lines), D("120.00"))
        project.overall_discount_amount = D("500.00")
        prices = compute_project_prices(project)
        self.assertEqual((prices.overall_discount, prices.net_total), (D("150.00"), D("0.00")))
        self.assertEqual(prices.gross_total, D("0.00"))

    def test_it_comes_after_group_discounts_and_surcharges(self) -> None:
        project = make_project(rental_days=1, overall_discount_percent=D("10"))
        group = add_group(project, "Licht", discount_percent=D("20"))
        add_line(project, make_product("L-001", price="100.00", billing_mode="flat"), 1, group=group)
        add_line(project, make_product("T-001", price="50.00", billing_mode="flat"), 1)
        prices = compute_project_prices(project)
        # 100 − 20 % = 80, plus 50 = 130; then 10 % of 130.
        self.assertEqual(
            (prices.net_before_overall_discount, prices.overall_discount, prices.net_total),
            (D("130.00"), D("13.00"), D("117.00")),
        )
        # The margin follows the net.
        self.assertEqual(prices.margin_before_expenses, D("117.00"))

    def test_the_rounding_of_the_shares_keeps_net_and_tax_together(self) -> None:
        project = make_project(rental_days=1, overall_discount_percent=D("33.33"))
        tax_free = TaxRate.objects.get(rate=0)
        for number in range(1, 4):
            add_line(project, make_product(f"L-00{number}", price="33.33", billing_mode="flat"), 1)
            add_line(project, make_product(f"F-00{number}", price="10.01", billing_mode="flat", tax_rate=tax_free), 1)
        prices = compute_project_prices(project)
        self.assertEqual(sum(line.net for line in prices.tax_lines), prices.net_total)
        self.assertEqual(prices.gross_total, prices.net_total + prices.tax_total)

    def test_a_sum_of_zero_gets_no_discount(self) -> None:
        project = make_project(rental_days=1, overall_discount_percent=D("10"))
        self.assertEqual(compute_project_prices(project).overall_discount, D(0))


class ModelAndServiceTests(RentalarsTestCase):
    """Only one of the two; rights; closed projects and cases."""

    def test_percent_or_amount_not_both(self) -> None:
        project = mixed_project()
        project.overall_discount_percent, project.overall_discount_amount = D("5"), D("10")
        with self.assertRaises(ValidationError) as caught:
            project.full_clean()
        self.assertIn("overall_discount_amount", caught.exception.message_dict)
        project.overall_discount_percent = D("101")
        project.overall_discount_amount = None
        with self.assertRaises(ValidationError):
            project.full_clean()

    def test_the_service_sets_and_removes(self) -> None:
        project = mixed_project()
        services.set_overall_discount(project, rights=ALL_RIGHTS, percent=D("7.5"))
        project.refresh_from_db()
        self.assertEqual((project.overall_discount_percent, project.overall_discount_amount), (D("7.50"), None))
        services.set_overall_discount(project, rights=ALL_RIGHTS, amount=D("20"))
        project.refresh_from_db()
        self.assertEqual((project.overall_discount_percent, project.overall_discount_amount), (None, D("20.00")))
        services.set_overall_discount(project, rights=ALL_RIGHTS)
        project.refresh_from_db()
        self.assertEqual((project.overall_discount_percent, project.overall_discount_amount), (None, None))
        with self.assertRaises(ValidationError):
            services.set_overall_discount(project, rights=ALL_RIGHTS, percent=D("5"), amount=D("5"))

    def test_without_the_price_right_it_is_refused(self) -> None:
        project = mixed_project()
        with self.assertRaises(ValidationError):
            services.set_overall_discount(project, rights=no_price_rights(), percent=D("5"))

    def test_a_closed_project_is_locked(self) -> None:
        project = mixed_project()
        project.status = ProjectStatus.CLOSED
        project.save()
        with self.assertRaises(ValidationError):
            services.set_overall_discount(project, rights=ALL_RIGHTS, percent=D("5"))

    def test_the_change_is_in_the_log(self) -> None:
        from rentalars.core.models import AuditLogEntry

        project = mixed_project()
        services.set_overall_discount(project, rights=ALL_RIGHTS, percent=D("5"))
        entry = AuditLogEntry.objects.filter(object_id=str(project.pk)).order_by("-pk").first()
        self.assertIn("overall_discount_percent", str(entry.changes))


class DocumentTests(RentalarsTestCase):
    """Offer and invoice show the row; the electronic invoice carries it in the allowances."""

    def setUp(self) -> None:
        super().setUp()
        ready_for_invoices()
        self.project = mixed_project(overall_discount_percent=D("10"))

    def build(self, kind: str = "invoice") -> builder.DocumentContent:
        return builder.build_priced(
            self.project, kind, title="Dokument", number="X-1", issued_on=datetime.date(2027, 3, 1)
        )

    def test_the_row_and_the_sums(self) -> None:
        content = self.build()
        [row] = [section for section in content.sections if section.overall_discount]
        self.assertEqual((row.title, row.subtotal), ("Gesamtrabatt 10 %", D("-15.00")))
        self.assertEqual(content.net_total, D("135.00"))
        self.assertEqual(
            [(share.net, share.positions_total, share.allowance) for share in content.taxes],
            [(D("90.00"), D("100.00"), D("10.00")), (D("45.00"), D("50.00"), D("5.00"))],
        )
        self.assertEqual(content.positions[-1].title, "Produkt L-002")

    def test_offer_and_order_confirmation_as_well(self) -> None:
        for kind in ("offer", "order_confirmation"):
            with self.subTest(kind):
                self.assertTrue(any(section.overall_discount for section in self.build(kind).sections))

    def test_stored_read_again_and_cancelled(self) -> None:
        content = self.build()
        again = builder.from_json(content.as_json())
        self.assertTrue(any(section.overall_discount for section in again.sections))
        self.assertEqual(again.net_total, D("135.00"))
        cancelled = builder.negated(content, title="Storno", number="S-1", issued_on=datetime.date(2027, 3, 2))
        [row] = [section for section in cancelled.sections if section.overall_discount]
        self.assertEqual(row.subtotal, D("15.00"))

    def test_the_pdf_shows_the_row(self) -> None:
        from rentalars.documents.pdf import render_html

        html = render_html(self.build(), document_services.template_for("invoice"))
        self.assertIn("Gesamtrabatt 10 %", html)
        self.assertIn("135,00", html)

    def test_the_electronic_invoice_adds_up(self) -> None:
        xml = xrechnung.build_xml(self.build()).decode()
        self.assertIn('<cbc:TaxExclusiveAmount currencyID="EUR">135.00</cbc:TaxExclusiveAmount>', xml)
        self.assertIn('<cbc:AllowanceTotalAmount currencyID="EUR">15.00</cbc:AllowanceTotalAmount>', xml)

    def test_a_whole_project_with_a_part_keeps_each_discount_in_its_block(self) -> None:
        part = services.create_subproject(
            self.project, name="Bühne", start=at(10), end=at(12), overall_discount_amount=D("20.00")
        )
        add_line(part, make_product("L-003", price="200.00", billing_mode="flat"), 1)
        content = self.build()
        self.assertEqual(sum(1 for section in content.sections if section.overall_discount), 2)
        self.assertEqual(content.net_total, D("135.00") + D("180.00"))


class DuplicateTests(RentalarsTestCase):
    def test_the_copy_has_the_discount(self) -> None:
        source = mixed_project(overall_discount_percent=D("10"))
        copy = duplicate_project(source, start=at(20), end=at(22), name="Wieder", rights=ALL_RIGHTS, user=None)
        self.assertEqual(copy.overall_discount_percent, D("10.00"))

    def test_not_without_the_price_right(self) -> None:
        source = mixed_project(overall_discount_amount=D("10"))
        copy = duplicate_project(source, start=at(20), end=at(22), name="Wieder", rights=no_price_rights(), user=None)
        self.assertIsNone(copy.overall_discount_amount)


class PagesTests(UiTestCase):
    """The dialog and the displays."""

    def setUp(self) -> None:
        super().setUp()
        self.project = mixed_project()

    def test_set_change_and_remove_in_the_dialog(self) -> None:
        url = reverse("projects:overall_discount", args=[self.project.pk])
        dialog = self.assert_ok(self.client.get(url))
        self.assertIn("Gesamtrabatt in Prozent", dialog)
        self.assertIn("Gesamtrabatt als Betrag", dialog)
        self.client.post(url, {"percent": "10", "amount": ""})
        self.project.refresh_from_db()
        self.assertEqual(self.project.overall_discount_percent, D("10.00"))
        planning = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.project.pk])))
        self.assertIn("Gesamtrabatt 10 %", planning)
        self.assertIn("Gesamtrabatt ändern", planning)
        # Discount target: the percentage that is only shown again (10, as stored) is not "typed"; a changed
        # percentage next to an amount is still refused.
        both = self.client.post(url, {"percent": "12", "amount": "5"})
        self.assertIn("Nur eines von beiden", both.content.decode())
        self.client.post(url, {"percent": "", "amount": "25,50"})
        self.project.refresh_from_db()
        self.assertEqual(
            (self.project.overall_discount_percent, self.project.overall_discount_amount), (None, D("25.50"))
        )
        self.client.post(url, {"percent": "", "amount": ""})
        self.project.refresh_from_db()
        self.assertEqual((self.project.overall_discount_percent, self.project.overall_discount_amount), (None, None))
        planning = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.project.pk])))
        self.assertIn("Gesamtrabatt festlegen", planning)

    def test_the_price_overview_shows_it(self) -> None:
        services.set_overall_discount(self.project, rights=ALL_RIGHTS, percent=D("10"))
        page = self.assert_ok(self.client.get(reverse("projects:price_overview", args=[self.project.pk])))
        self.assertIn("Gesamtrabatt", page)
        self.assertIn("− 15,00", page)
        csv_text = render_price_overview_csv(self.project, with_lines=False, rights=ALL_RIGHTS, user=None)
        self.assertIn("Gesamtrabatt 10 %", csv_text)
        self.assertIn("-15", csv_text)
        pdf = self.client.get(reverse("projects:price_overview_pdf", args=[self.project.pk]))
        self.assertEqual(pdf.status_code, 200)

    def test_a_user_without_the_price_right_is_refused(self) -> None:
        from tests.helpers import PASSWORD, make_user

        Role.objects.create(
            name="Planung ohne Preise", module_levels={"projects": 2}, special_rights=[], project_scope=ProjectScope.ALL
        )
        make_user("planer", roles=("Planung ohne Preise",))
        self.client.logout()
        self.client.login(username="planer", password=PASSWORD)
        url = reverse("projects:overall_discount", args=[self.project.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {"percent": "10"}).status_code, 403)


class ApiTests(ApiTestCase):
    """The fields of /projects and the sums."""

    def test_set_through_the_api_and_the_sums(self) -> None:
        project = mixed_project()
        base = f"{API}/projects/{project.pk}"
        patched = self.admin.patch(base, {"overall_discount_percent": "10"}, format="json")
        self.assertEqual(patched.status_code, 200, patched.content)
        # Discount target: the percentage has six decimals now.
        self.assertEqual(patched.json()["overall_discount_percent"], "10.000000")
        totals = self.admin.get(f"{base}/totals").json()
        self.assertEqual(
            (totals["net_before_overall_discount"], totals["overall_discount"], totals["net_total"]),
            ("150.00", "15.00", "135.00"),
        )
        # Naming the other one clears the first.
        again = self.admin.patch(base, {"overall_discount_amount": "20"}, format="json")
        self.assertEqual(
            (again.json()["overall_discount_percent"], again.json()["overall_discount_amount"]), (None, "20.00")
        )
        both = self.admin.patch(base, {"overall_discount_percent": "5", "overall_discount_amount": "5"}, format="json")
        self.assert_error(both, 400, "validation_error")
        gone = self.admin.patch(base, {"overall_discount_amount": None}, format="json")
        self.assertEqual(
            (gone.json()["overall_discount_percent"], gone.json()["overall_discount_amount"]), (None, None)
        )

    def test_a_new_project_with_a_discount(self) -> None:
        customer = make_project().customer
        created = self.admin.post(
            f"{API}/projects",
            {
                "name": "Neu",
                "customer": customer.pk,
                "start": "2027-04-01T10:00:00+02:00",
                "end": "2027-04-02T10:00:00+02:00",
                "overall_discount_percent": "12.5",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(Project.objects.get(pk=created.json()["id"]).overall_discount_percent, D("12.50"))

    def test_hidden_and_refused_without_the_price_right(self) -> None:
        project = mixed_project(overall_discount_percent=D("10"))
        Role.objects.create(
            name="Planung ohne Preise", module_levels={"projects": 2}, special_rights=[], project_scope=ProjectScope.ALL
        )
        client = self.client_for("planer", "Planung ohne Preise")
        shown = client.get(f"{API}/projects/{project.pk}").json()
        self.assertNotIn("overall_discount_percent", shown)
        self.assertNotIn("overall_discount_amount", shown)
        refused = client.patch(f"{API}/projects/{project.pk}", {"overall_discount_percent": "50"}, format="json")
        self.assert_error(refused, 400, "validation_error")
        project.refresh_from_db()
        self.assertEqual(project.overall_discount_percent, D("10.00"))
