# SPDX-License-Identifier: GPL-3.0-or-later
"""API for lines of the planning: PRJ-072, PRJ-075, DOK-010, PER-026."""

from __future__ import annotations

from decimal import Decimal

from rentalars.accounts.models import Role
from rentalars.documents.models import Document
from rentalars.products.models import BillingMode
from rentalars.projects.models import LineVariant, MaterialLine, ProjectStatus
from rentalars.projects.services import update_line
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    ALL_RIGHTS,
    add_group,
    add_line,
    add_line_before_071,
    job_function,
    make_product,
    make_project,
    make_stock,
    plan,
    ready_for_invoices,
)

D = Decimal


def flat(article_number: str, price: str) -> object:
    """A product billed as a flat price."""
    return make_product(article_number, price=price, billing_mode=BillingMode.FLAT)


class LineVariantApiTests(ApiTestCase):
    """PRJ-075: the field ``variant`` and the copy of a line."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.group = add_group(self.project, "Licht")
        self.line = add_line(self.project, flat("L-010", "100.00"), 2, group=self.group).line
        self.base = f"{API}/projects/{self.project.pk}"

    def test_variant_is_written_and_read(self) -> None:
        changed = self.admin.patch(f"{self.base}/material-lines/{self.line.pk}", {"variant": "optional"}, format="json")
        self.assertEqual(changed.status_code, 200, changed.data)
        body = changed.json()
        self.assertEqual(body["variant"], "optional")
        self.assertFalse(body["price"]["counts_toward_total"])
        totals = self.admin.get(f"{self.base}/totals").json()
        self.assertEqual((totals["net_total"], totals["optional_lines_total"]), ("0.00", "200.00"))
        created = self.admin.post(
            f"{self.base}/material-lines",
            {"product": self.line.product_id, "quantity": "1", "variant": "alternative"},
            format="json",
        )
        self.assertEqual(created.json()["variant"], "alternative")
        self.assert_error(
            self.admin.patch(f"{self.base}/material-lines/{self.line.pk}", {"variant": "maybe"}, format="json"),
            400,
            "validation_error",
            "variant",
        )

    def test_price_overview_marks_the_variant(self) -> None:
        update_line(self.line, rights=ALL_RIGHTS, variant=LineVariant.ALTERNATIVE)
        overview = self.admin.get(f"{self.base}/price-overview").json()
        self.assertEqual(overview["groups"][0]["lines"][0]["variant"], "alternative")
        self.assertEqual(overview["totals"]["alternative_lines_total"], "200.00")

    def test_duplicate_a_line(self) -> None:
        response = self.admin.post(f"{self.base}/material-lines/{self.line.pk}/duplicate")
        self.assertEqual(response.status_code, 201, response.data)
        body = response.json()
        self.assertNotEqual(body["id"], self.line.pk)
        self.assertEqual((body["group"], body["quantity"], body["unit_price"]), (self.group.pk, "2.00", "100.00"))
        self.assertEqual(body["position"], self.line.position + 1)
        self.assertEqual(body["price"]["amount"], "200.00")
        self.assertEqual(MaterialLine.objects.count(), 2)

    def test_duplicating_needs_edit_access_and_a_line_of_the_project(self) -> None:
        reader = self.client_for("nora", "Nur-Lesen")
        self.assert_error(reader.post(f"{self.base}/material-lines/{self.line.pk}/duplicate"), 403, "permission_denied")
        other = make_project("Anderes")
        missing = self.admin.post(f"{API}/projects/{other.pk}/material-lines/{self.line.pk}/duplicate")
        self.assertEqual(missing.status_code, 404)


class OldPricesApiTests(ApiTestCase):
    """PRJ-072: list the old prices and take over the new ones."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(status=ProjectStatus.OPTION)
        self.lamp = flat("L-010", "20.00")
        self.line = add_line(self.project, self.lamp, 4).line
        self.hand = add_line(self.project, flat("L-020", "10.00"), 1).line
        update_line(self.hand, rights=ALL_RIGHTS, unit_price=D("8.00"))
        for product, price in ((self.lamp, "25.00"), (self.hand.product, "12.00")):
            product.price = D(price)  # type: ignore[attr-defined]
            product.save()  # type: ignore[attr-defined]
        self.url = f"{API}/projects/{self.project.pk}/old-prices"

    def test_list_and_take_over_those_not_set_by_hand(self) -> None:
        listing = self.admin.get(self.url).json()
        self.assertTrue(listing["shows_hint"])
        rows = {row["key"]: row for row in listing["lines"]}
        self.assertEqual(
            rows[f"m{self.line.pk}"],
            {
                "key": f"m{self.line.pk}",
                "kind": "material",
                "line": self.line.pk,
                "article_number": "L-010",
                "title": "Produkt L-010",
                "unit_price": "20.00",
                "list_price": "20.00",
                "new_price": "25.00",
                "set_by_hand": False,
            },
        )
        self.assertTrue(rows[f"m{self.hand.pk}"]["set_by_hand"])

        result = self.admin.post(self.url, {"take_over_all": "automatic"}, format="json").json()
        self.assertEqual((result["taken_over"], result["kept"]), (1, 0))
        self.assertEqual([row["key"] for row in result["lines"]], [f"m{self.hand.pk}"])

        result = self.admin.post(self.url, {"keep": [f"m{self.hand.pk}"]}, format="json").json()
        self.assertEqual((result["kept"], result["lines"]), (1, []))
        self.hand.refresh_from_db()
        self.assertEqual(self.hand.unit_price, D("8.00"))

    def test_all_and_single_keys(self) -> None:
        result = self.admin.post(self.url, {"take_over": [f"m{self.hand.pk}"]}, format="json").json()
        self.assertEqual(result["taken_over"], 1)
        result = self.admin.post(self.url, {"take_over_all": "all"}, format="json").json()
        self.assertEqual((result["taken_over"], result["lines"]), (1, []))

    def test_confirmed_project_answers_on_request(self) -> None:
        self.project.status = ProjectStatus.CONFIRMED
        self.project.save()
        listing = self.admin.get(self.url).json()
        self.assertFalse(listing["shows_hint"])
        self.assertEqual(len(listing["lines"]), 2)

    def test_needs_the_price_right(self) -> None:
        Role.objects.create(name="Planung ohne Preise", module_levels={"projects": 2})
        planner = self.client_for("paul", "Planung ohne Preise")
        self.assert_error(planner.get(self.url), 403, "permission_denied")
        self.assert_error(planner.post(self.url, {"take_over_all": "all"}, format="json"), 403, "permission_denied")

    def test_material_line_shows_its_list_price(self) -> None:
        body = self.admin.get(f"{API}/projects/{self.project.pk}/material-lines/{self.line.pk}").json()
        self.assertEqual(body["list_price"], "20.00")


class MaximumDiscountApiTests(ApiTestCase):
    """PER-026: the maximum on the job function, the discount on the crew line."""

    def setUp(self) -> None:
        super().setUp()
        self.stagehand = job_function("Stagehand", price="30.00")
        self.project = make_project()

    def test_job_function_carries_its_maximum_with_the_price_right(self) -> None:
        url = f"{API}/job-functions/{self.stagehand.pk}"
        changed = self.admin.patch(url, {"max_discount_percent": "5"}, format="json")
        self.assertEqual(changed.json()["max_discount_percent"], "5.00")
        self.assert_error(
            self.admin.patch(url, {"max_discount_percent": "120"}, format="json"),
            400,
            "validation_error",
            "max_discount_percent",
        )
        Role.objects.create(name="Personal ohne Preise", module_levels={"personnel": 3})
        planner = self.client_for("pia", "Personal ohne Preise")
        self.assertNotIn("max_discount_percent", planner.get(url).json())
        self.assert_error(
            planner.patch(url, {"max_discount_percent": "50"}, format="json"),
            400,
            "validation_error",
            "max_discount_percent",
        )

    def test_crew_line_discount_is_limited_in_the_answer(self) -> None:
        self.stagehand.max_discount_percent = D("5")
        self.stagehand.save()
        base = f"{API}/projects/{self.project.pk}/crew-lines"
        (created,) = self.admin.post(
            base, {"job_function": self.stagehand.pk, "planned_hours": "10", "discount_percent": "10"}, format="json"
        ).json()
        self.assertEqual(
            (
                created["discount_percent"],
                created["effective_discount_percent"],
                created["max_discount_percent"],
                created["discount_is_capped"],
                created["amount_before_discount"],
                created["discount"],
                created["amount"],
            ),
            ("10.00", "5.00", "5.00", True, "300.00", "15.00", "285.00"),
        )
        totals = self.admin.get(f"{API}/projects/{self.project.pk}/totals").json()
        self.assertEqual((totals["personnel_total"], totals["lines_with_limited_discount"]), ("285.00", 1))

    def test_service_product_line_in_a_group(self) -> None:
        engineer = self.stagehand.service_product  # PRD-044: every job function has its own
        engineer.price, engineer.billing_mode = D("100.00"), BillingMode.FLAT
        engineer.save()
        self.stagehand.max_discount_percent = D("5")
        self.stagehand.save()
        group = add_group(self.project, "Ton", discount_percent=D("10"))
        add_line(self.project, flat("T-030", "400.00"), 1, group=group)
        line = add_line_before_071(self.project, engineer, 1, group=group, discount_percent=D("8")).line
        planning = self.admin.get(f"{API}/projects/{self.project.pk}/planning").json()
        (group_document,) = planning["groups"]
        price = next(entry for entry in group_document["lines"] if entry["id"] == line.pk)["price"]
        self.assertEqual((price["discount_percent"], price["discount_is_capped"]), ("5.00", True))
        totals = planning["totals"]["groups"][0]
        self.assertEqual((totals["subtotal"], totals["discount_limited_by"]), ("455.00", "9.50"))

    def test_crew_discount_needs_the_price_right(self) -> None:
        line = plan(self.project, self.stagehand)
        Role.objects.create(name="Planung", module_levels={"projects": 2, "personnel": 2})
        planner = self.client_for("pia", "Planung")
        self.assert_error(
            planner.patch(
                f"{API}/projects/{self.project.pk}/crew-lines/{line.pk}", {"discount_percent": "5"}, format="json"
            ),
            400,
            "validation_error",
        )


class OfferApiTests(ApiTestCase):
    """DOK-010 through the API."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(customer=ready_for_invoices(), status=ProjectStatus.INQUIRY)
        add_line(self.project, make_stock("L-010", 6, price="20.00"), 4)
        self.url = f"{API}/projects/{self.project.pk}/documents"

    def test_make_offers_with_and_without_validity(self) -> None:
        first = self.admin.post(self.url, {"kind": "offer"}, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        body = first.json()
        self.assertEqual((body["kind"], body["number"], body["valid_until"]), ("offer", "AN-2027-0001", "2027-03-15"))
        self.assertEqual(body["xml_url"], "")
        second = self.admin.post(self.url, {"kind": "offer", "valid_until": "2027-04-01"}, format="json").json()
        self.assertEqual((second["number"], second["valid_until"]), ("AN-2027-0002", "2027-04-01"))
        self.assert_error(
            self.admin.post(self.url, {"kind": "offer", "valid_until": "2027-02-01"}, format="json"),
            400,
            "validation_error",
        )
        preview = self.admin.post(f"{self.url}/preview", {"kind": "offer"}, format="json")
        self.assertTrue(preview.content.startswith(b"%PDF"))
        self.assertEqual(Document.objects.count(), 2)

    def test_offers_need_the_price_right(self) -> None:
        Role.objects.create(name="Planung ohne Preise", module_levels={"projects": 2})
        planner = self.client_for("paul", "Planung ohne Preise")
        self.assert_error(planner.post(self.url, {"kind": "offer"}, format="json"), 403, "permission_denied")
        self.admin.post(self.url, {"kind": "offer"}, format="json")
        self.assertEqual(planner.get(self.url).json(), [])

    def test_template_of_the_offer(self) -> None:
        templates = self.admin.get(f"{API}/document-templates").json()
        offer = next(entry for entry in templates if entry["kind"] == "offer")
        self.assertEqual(offer["title"], "Angebot")
        self.assertIn("{valid_until}", offer["introduction"])
        ranges = {entry["key"]: entry for entry in self.admin.get(f"{API}/number-ranges").json()}
        self.assertEqual(ranges["offer"]["preview"], "AN-2027-0001")
        changed = self.admin.patch(
            f"{API}/number-ranges/{ranges['offer']['id']}", {"prefix": "ANG-{year}/"}, format="json"
        )
        self.assertEqual(changed.json()["preview"], "ANG-2027/0001")
