# SPDX-License-Identifier: GPL-3.0-or-later
"""Profitability (PRJ-115), what an item earned (MAT-053), the three labels (MAT-056), the setup (ADM-018).

* The requirement: a way to keep an eye on profitability.
* The requirement: per item an overview of how much money the item itself brought in and its share of the purchase
  price.
* The requirement: three kinds of labels are available by default and can be printed directly from the browser –
  logo, name, QR code, phone, address and text configurable.
* The requirement: the setup asks which value is used for the personnel products as internal prices / costs and
  which as customer prices.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.core.models import CompanyProfile
from rentalars.material import labels
from rentalars.material.models import LabelSettings, MaterialItem
from rentalars.projects import profitability
from rentalars.projects.list_sums import _prices_of
from rentalars.projects.models import Project, ProjectStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import RentalarsTestCase, add_line, make_item, make_model, make_project, make_stock
from tests.ui.base import UiTestCase

MARCH = (datetime.date(2027, 3, 1), datetime.date(2027, 3, 31))


def net_of(project: Project) -> Decimal:
    return _prices_of([project])[project.pk][0].net_total


class EarningCase(RentalarsTestCase):
    """Two cables S-100 (10 € each), both out in the Stadtfest; 0001 bought for 100 € with 0002 in its price."""

    def setUp(self) -> None:
        super().setUp()
        self.product = make_stock("S-100", 2)
        self.first, self.second = MaterialItem.objects.order_by("inventory_number")
        self.first.purchase_price = Decimal("100.00")
        self.first.save()
        self.second.purchase_price_in = self.first
        self.second.save()
        self.project = make_project("Stadtfest")
        add_line(self.project, self.product, 2)
        Project.objects.filter(pk=self.project.pk).update(status=ProjectStatus.CLOSED)
        self.project.refresh_from_db()
        self.net = net_of(self.project)


class ProfitabilityTests(EarningCase):
    def test_the_report_of_the_projects(self) -> None:
        self.assertGreater(self.net, 0)
        report = profitability.project_report(Project.objects.all(), *MARCH)
        self.assertEqual(report.total.projects, 1)
        self.assertEqual(report.total.revenue, self.net)
        self.assertEqual(report.total.material_revenue, self.net)
        self.assertEqual(report.total.margin, self.net)  # no crew, no subrental
        self.assertEqual([row.project for row in report.rows], [self.project])
        self.assertEqual(len(report.months), 1)
        # Cancelled projects and inquiries do not count; another period neither.
        make_project("Anfrage", status=ProjectStatus.INQUIRY)
        self.assertEqual(profitability.project_report(Project.objects.all(), *MARCH).total.projects, 1)
        self.assertEqual(
            profitability.project_report(
                Project.objects.all(), datetime.date(2027, 4, 1), datetime.date(2027, 4, 30)
            ).total.projects,
            0,
        )

    def test_what_each_item_earned(self) -> None:
        """MAT-053: no item chosen when packing – the line is shared evenly (estimated)."""
        revenue = profitability.item_revenue(self.second)
        self.assertEqual(revenue.direct, 0)
        self.assertEqual(revenue.total, (self.net / 2).quantize(Decimal("0.01")))
        self.assertEqual(revenue.projects, 1)
        # MAT-054: bought as a set – the set is compared with the price of the set.
        self.assertEqual(revenue.purchase_price, Decimal("100.00"))
        self.assertEqual([item.pk for item in revenue.set_items], [self.first.pk, self.second.pk])
        self.assertEqual(revenue.set_revenue, self.net)
        self.assertEqual(revenue.share_percent, (self.net * 100 / 100).quantize(Decimal("0.1")))

    def test_the_report_of_the_material(self) -> None:
        (row,) = profitability.product_report()
        self.assertEqual((row.product, row.items), (self.product, 2))
        self.assertEqual(row.purchase_total, Decimal("100.00"))
        self.assertEqual(row.revenue, self.net)


class ReportPageTests(UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        product = make_stock("S-100", 2)
        project = make_project("Stadtfest")
        add_line(project, product, 2)
        Project.objects.filter(pk=project.pk).update(status=ProjectStatus.CLOSED)
        self.item = MaterialItem.objects.order_by("inventory_number").first()

    def test_the_pages(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:report"), {"year": "2027"}))
        self.assertIn("Profitabilität", page)
        self.assertIn("Stadtfest", page)
        response = self.client.get(reverse("projects:report"), {"year": "2027", "format": "csv"})
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("Stadtfest", response.content.decode("utf-8-sig"))
        page = self.assert_ok(self.client.get(reverse("projects:report_material")))
        self.assertIn("S-100", page)
        part = self.assert_ok(self.client.get(reverse("projects:item_revenue", args=[self.item.pk])))
        self.assertIn("Kalkuliert mit diesem Exemplar eingenommen", part)
        detail = self.assert_ok(self.client.get(reverse("material:item_detail", args=[self.item.pk])))
        self.assertIn(reverse("projects:item_revenue", args=[self.item.pk]), detail)

    def test_only_who_reads_every_project_and_sees_prices(self) -> None:
        crew = self.browser_for("kai", "Crew")
        self.assertEqual(crew.get(reverse("projects:report")).status_code, 403)
        page = self.assert_ok(crew.get(reverse("core:home")))
        self.assertNotIn(reverse("projects:report"), page)
        lager = self.browser_for("luka", "Lager")
        self.assertEqual(lager.get(reverse("projects:item_revenue", args=[self.item.pk])).status_code, 403)

    def test_assigned_projects_only_see_no_sums_over_all(self) -> None:
        """What an item earned sums up every project – not for a project manager of assigned projects only."""
        Role.objects.create(
            name="Projektleitung extern",
            module_levels={"projects": 3, "material": 1, "reports": 1},
            special_rights=["prices", "purchase_prices"],
            project_scope="assigned",
        )
        erik = self.browser_for("erik", "Projektleitung extern")
        self.assertEqual(erik.get(reverse("projects:item_revenue", args=[self.item.pk])).status_code, 403)
        detail = self.assert_ok(erik.get(reverse("material:item_detail", args=[self.item.pk])))
        self.assertNotIn(reverse("projects:item_revenue", args=[self.item.pk]), detail)
        self.assertEqual(erik.get(reverse("projects:report")).status_code, 403)

    def test_the_module_reports_decides(self) -> None:
        """AUT-014, AUT-015: without the module "Auswertungen" neither the entry nor the pages."""
        Role.objects.create(
            name="Büro",
            module_levels={"projects": 1, "material": 1, "reports": 0},
            special_rights=["prices", "purchase_prices", "personnel_costs"],
        )
        office = self.browser_for("olga", "Büro")
        self.assertEqual(office.get(reverse("projects:report")).status_code, 403)
        self.assertEqual(office.get(reverse("projects:report_material")).status_code, 403)
        self.assertEqual(office.get(reverse("projects:item_revenue", args=[self.item.pk])).status_code, 403)
        self.assertNotIn('href="/reports/"', self.assert_ok(office.get(reverse("core:home"))))
        Role.objects.filter(name="Büro").update(module_levels={"projects": 1, "material": 1, "reports": 1})
        self.assertIn('href="/reports/"', self.assert_ok(office.get(reverse("core:home"))))
        self.assert_ok(office.get(reverse("projects:report")))

    def test_no_formula_in_the_csv(self) -> None:
        Project.objects.filter(name="Stadtfest").update(name='=HYPERLINK("http://evil.example","Stadtfest")')
        response = self.client.get(reverse("projects:report"), {"year": "2027", "format": "csv"})
        text = response.content.decode("utf-8-sig")
        self.assertIn('"\'=HYPERLINK(""http://evil.example"",""Stadtfest"")"', text)
        self.assertNotIn('"=HYPERLINK', text)


class ReportApiTests(ApiTestCase):
    def test_reports_and_item_revenue(self) -> None:
        product = make_stock("S-100", 2)
        project = make_project("Stadtfest")
        add_line(project, product, 2)
        Project.objects.filter(pk=project.pk).update(status=ProjectStatus.CLOSED)
        project.refresh_from_db()
        net = net_of(project)
        data = self.admin.get(f"{API}/reports/profitability", {"year": 2027}).json()
        self.assertEqual(data["total"]["revenue"], str(net))
        self.assertEqual(data["total"]["margin"], str(net))
        self.assertEqual([row["number"] for row in data["projects"]], [project.number])
        rows = self.admin.get(f"{API}/reports/material").json()
        self.assertEqual(rows[0]["article_number"], "S-100")
        item = MaterialItem.objects.order_by("inventory_number").first()
        revenue = self.admin.get(f"{API}/material-items/{item.pk}/revenue").json()
        self.assertEqual(revenue["projects"], 1)
        self.assertEqual(revenue["direct"], "0.00")
        crew = self.client_for("kai", "Crew")
        self.assertEqual(crew.get(f"{API}/reports/profitability").status_code, 403)
        self.assertEqual(crew.get(f"{API}/reports/material").status_code, 403)
        # Without the right to see purchase prices: no costs, no margin.
        planner = self.client_for("pia", "Personaldisposition")
        self.assertEqual(planner.get(f"{API}/reports/profitability").status_code, 403)


class LabelSettingsTests(RentalarsTestCase):
    """MAT-056: what the labels say – the company's data where a field is empty."""

    def test_defaults_from_the_company(self) -> None:
        company = CompanyProfile.load()
        company.name, company.phone, company.website = (
            "Lichtwerk GmbH",
            "0170 1234567",
            "https://www.lichtwerk.example/",
        )
        company.save()
        row = LabelSettings.load()
        self.assertEqual(
            (row.printed_name, row.printed_cable_name, row.printed_phone, row.printed_url, row.printed_wrap_text),
            ("Lichtwerk GmbH", "Lichtwerk GmbH", "0170 1234567", "www.lichtwerk.example", "www.lichtwerk.example"),
        )
        self.assertEqual(row.qr_content("0042"), f"{settings.RENTALARS_URL}/m/0042")
        row.qr_target = "https://equip.lichtwerk.example/id/{id}"
        row.cable_name = "Lichtwerk"
        self.assertEqual(row.qr_content("0042"), "https://equip.lichtwerk.example/id/0042")
        self.assertEqual(row.printed_cable_name, "Lichtwerk")

    def test_the_target_needs_the_id_and_a_web_address(self) -> None:
        row = LabelSettings.load()
        row.qr_target = "https://equip.example.de/"
        with self.assertRaises(ValidationError) as caught:
            row.full_clean()
        self.assertIn("qr_target", caught.exception.message_dict)
        row.qr_target = "equip.example.de/{id}"
        with self.assertRaises(ValidationError):
            row.full_clean()

    def test_the_three_labels(self) -> None:
        item = make_item(make_model("Shure SM58"), 42)
        for kind, size in (("small", "54mm 17mm"), ("large", "90mm 29mm"), ("cable", "29mm")):
            html = labels.render_labels_html([item], label_format=kind, for_browser=True)
            self.assertIn("0042", html, kind)
            self.assertIn(f"@page {{ size: {size}", html, kind)
            self.assertIn("data-print-on-load", html)
        self.assertEqual(labels.default_format(), "small")


class LabelPageTests(UiTestCase):
    def test_print_from_the_browser_and_the_settings(self) -> None:
        make_item(make_model("Shure SM58"), 42)
        page = self.assert_ok(self.client.get(reverse("material:labels")))
        self.assertIn("Klein, 17 × 54 mm", page)
        response = self.client.get(reverse("material:labels_print"), {"items": "0042", "label_format": "large"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("0042", response.content.decode())
        settings_page = self.assert_ok(self.client.get(reverse("material:label_settings")))
        self.assertIn("Vorschau", settings_page)
        self.assertIn("0427", settings_page)
        response = self.client.post(
            reverse("material:label_settings"),
            {
                "company_name": "XYZ",
                "cable_name": "XYZ",
                "phone_caption": "Telefon:",
                "phone": "0100 5550123",
                "id_caption": "ID:",
                "url": "BSP.TEST",
                "wrap_text": "EQUIP.BSP.TEST",
                "notice": "Gefunden? Bitte melden.",
                "qr_target": "http://equip.bsp.test/id/{id}",
                "default_kind": "cable",
                "cable_length_mm": "90",
            },
        )
        self.assertRedirects(response, reverse("material:label_settings"))
        row = LabelSettings.objects.get()
        self.assertEqual((row.company_name, row.default_kind, row.wrap_text), ("XYZ", "cable", "EQUIP.BSP.TEST"))
        # Reading only: the page, no saving.
        reader = self.browser_for("nora", "Nur-Lesen")
        self.assertEqual(reader.post(reverse("material:label_settings"), {"company_name": "x"}).status_code, 403)


class LabelApiTests(ApiTestCase):
    def test_settings_and_pdf(self) -> None:
        data = self.admin.get(f"{API}/label-settings").json()
        self.assertEqual(data["default_kind"], "small")
        self.assertFalse(data["has_logo"])
        response = self.admin.patch(
            f"{API}/label-settings", {"company_name": "XYZ", "qr_target": "https://e.example/id/{id}"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["printed"]["qr_example"], "https://e.example/id/0042")
        response = self.admin.patch(f"{API}/label-settings", {"qr_target": "https://e.example/"}, format="json")
        self.assert_error(response, 400, "validation_error", "qr_target")
        self.assertEqual(self.client_for("kai", "Crew").get(f"{API}/label-settings").status_code, 403)
        item = make_item(make_model("Shure SM58"), 42)
        response = self.admin.post(f"{API}/labels", {"items": [item.pk], "format": "cable"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")


class SetupRateTests(RentalarsTestCase):
    """ADM-018: the job functions of the start data get the price and the costs per hour asked for in the setup."""

    def test_rates_of_the_setup(self) -> None:
        from rentalars.core.forms import SetupForm
        from rentalars.core.setup import _set_personnel_rates
        from rentalars.personnel.models import JobFunction

        functions = list(JobFunction.objects.select_related("service_product"))
        self.assertTrue(functions, "the start data have job functions")
        for function in functions:
            function.guide_cost_rate = None
            function.save()
            function.service_product.price = None
            function.service_product.save()
        kept = functions[0]
        kept.guide_cost_rate = Decimal("25.00")
        kept.save()
        _set_personnel_rates(Decimal("48.00"), Decimal("31.50"))
        for function in JobFunction.objects.select_related("service_product"):
            self.assertEqual(function.service_product.price, Decimal("48.00"))
            expected = Decimal("25.00") if function.pk == kept.pk else Decimal("31.50")
            self.assertEqual(function.guide_cost_rate, expected)
        form = SetupForm()
        self.assertEqual(form.fields["personnel_price"].initial, Decimal("45.00"))
        self.assertEqual(form.fields["personnel_cost"].initial, Decimal("30.00"))


class ShellTests(UiTestCase):
    """UIX-047: the foot of the sidebar; UIX-048: the bar of the chosen items only while some are ticked."""

    def test_sidebar_and_bulk_bar(self) -> None:
        make_stock("S-100", 2)
        page = self.assert_ok(self.client.get(reverse("material:item_list")))
        self.assertIn('<ul class="sidebar-links">', page)
        for word in ("Mein Konto", "Handbuch", "Abmelden"):
            self.assertIn(word, page)
        self.assertIn('data-bulk-bar="items"', page)
        self.assertIn("Auswahl aufheben", page)
        # Hidden until a box is ticked – but shown without scripts, which could never tick it awake (review, 6).
        self.assertRegex(page, r'<form [^>]*data-bulk-bar="items"[^>]* hidden>')
        self.assertIn("<noscript><style>.bulk-bar[hidden] { display: flex; }</style></noscript>", page)
