# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests: projects, groups, lines, prices, shortages and subrental (PRJ, PRD-031 ff.)."""

from __future__ import annotations

from decimal import Decimal

from rentalars.accounts.models import Role
from rentalars.masterdata.models import RentalScale, Supplier
from rentalars.projects.models import MaterialLine, Project
from tests.api.base import API, ApiTestCase
from tests.helpers import add_group, add_line, at, make_customer, make_product, make_project, make_stock


class ProjectTests(ApiTestCase):
    """Projects and their status (PRJ-001 to PRJ-009, PRJ-027)."""

    def setUp(self) -> None:
        super().setUp()
        self.customer = make_customer("Stadt Musterstadt, Kulturamt")

    def body(self, **fields: object) -> dict[str, object]:
        """The smallest valid body for a project."""
        body: dict[str, object] = {
            "name": "Stadtfest Hauptbühne",
            "customer": self.customer.pk,
            "start": at(10, 8).isoformat(),
            "end": at(12, 18).isoformat(),
        }
        body.update(fields)
        return body

    def test_project_gets_a_number_and_starts_as_inquiry(self) -> None:
        """PRJ-002, PRJ-008."""
        response = self.admin.post(f"{API}/projects", self.body(), format="json")
        self.assertEqual(response.status_code, 201, response.json())
        self.assertRegex(response.json()["number"], r"^\d{4}-\d{4}$")  # ADM-014: without "P-" again
        self.assertEqual(response.json()["status"], "inquiry")
        self.assertIn("option", response.json()["allowed_next_statuses"])

    def test_end_must_be_after_start(self) -> None:
        response = self.admin.post(f"{API}/projects", self.body(end=at(9).isoformat()), format="json")
        self.assert_error(response, 400, "validation_error", "end")

    def test_rental_days_are_suggested_from_the_event_period(self) -> None:
        """PRD-034: the suggestion can be overwritten."""
        created = self.admin.post(
            f"{API}/projects",
            self.body(event_start=at(11, 10).isoformat(), event_end=at(12, 23).isoformat()),
            format="json",
        ).json()
        self.assertEqual(created["suggested_rental_days"], 2)
        self.assertEqual(created["effective_rental_days"], 2)
        changed = self.admin.patch(f"{API}/projects/{created['id']}", {"rental_days": 1}, format="json").json()
        self.assertEqual(changed["effective_rental_days"], 1)

    def test_status_follows_the_allowed_steps_and_is_logged(self) -> None:
        """PRJ-008, PRJ-009."""
        project = make_project(status="inquiry", customer=self.customer)
        url = f"{API}/projects/{project.pk}/status"
        self.assertEqual(self.admin.post(url, {"status": "confirmed"}, format="json").json()["status"], "confirmed")
        self.assert_error(self.admin.post(url, {"status": "closed"}, format="json"), 400, "validation_error")
        self.assert_error(self.admin.post(url, {"status": "nonsense"}, format="json"), 400, "validation_error")
        history = self.admin.get(f"{API}/projects/{project.pk}/history").json()["results"]
        status_changes = [change for row in history for change in row["changes"] if change["field"] == "status"]
        self.assertEqual(len(status_changes), 1)

    def test_status_cannot_be_set_through_the_normal_update(self) -> None:
        project = make_project(status="inquiry", customer=self.customer)
        self.admin.patch(f"{API}/projects/{project.pk}", {"status": "closed"}, format="json")
        self.assertEqual(Project.objects.get(pk=project.pk).status, "inquiry")

    def test_closed_project_is_locked_and_reopening_needs_a_special_right(self) -> None:
        """PRJ-009."""
        project = make_project(customer=self.customer)
        for status in ("out", "returned", "closed"):
            self.assertEqual(
                self.admin.post(f"{API}/projects/{project.pk}/status", {"status": status}, format="json").status_code,
                200,
            )
        locked = self.admin.patch(f"{API}/projects/{project.pk}", {"name": "Anders"}, format="json")
        self.assert_error(locked, 400, "validation_error")
        manager = self.client_for("paula", "Projektleitung")
        refused = manager.post(f"{API}/projects/{project.pk}/status", {"status": "returned"}, format="json")
        self.assert_error(refused, 400, "validation_error")
        reopened = self.admin.post(f"{API}/projects/{project.pk}/status", {"status": "returned"}, format="json")
        self.assertEqual(reopened.json()["status"], "returned")

    def test_only_projects_in_planning_can_be_deleted(self) -> None:
        confirmed = make_project(customer=self.customer)
        self.assert_error(self.admin.delete(f"{API}/projects/{confirmed.pk}"), 400, "validation_error")
        inquiry = make_project("Anfrage", status="inquiry", customer=self.customer)
        self.assertEqual(self.admin.delete(f"{API}/projects/{inquiry.pk}").status_code, 204)

    def test_list_filters(self) -> None:
        """PRJ-027: status, period, customer, search."""
        make_project("Stadtfest", start=at(10), end=at(12), customer=self.customer)
        make_project("Jazznacht", start=at(20), end=at(21), status="option", customer=make_customer("Jazzclub"))

        def names(**params: object) -> list[str]:
            return [row["name"] for row in self.admin.get(f"{API}/projects", params).json()["results"]]

        self.assertEqual(names(status="option"), ["Jazznacht"])
        self.assertEqual(sorted(names(status=["option", "confirmed"])), ["Jazznacht", "Stadtfest"])
        self.assertEqual(names(customer=self.customer.pk), ["Stadtfest"])
        self.assertEqual(names(q="jazz"), ["Jazznacht"])
        self.assertEqual(names(since=at(15).isoformat()), ["Jazznacht"])
        self.assertEqual(names(until=at(15).isoformat()), ["Stadtfest"])
        self.assertEqual(names(ordering="-start"), ["Jazznacht", "Stadtfest"])
        expanded = self.admin.get(f"{API}/projects", {"expand": "customer", "q": "Stadtfest"}).json()["results"][0]
        self.assertEqual(expanded["customer"]["name"], "Stadt Musterstadt, Kulturamt")


class GroupAndLineTests(ApiTestCase):
    """Groups and material lines (PRJ-010 to PRJ-016, PRJ-039 to PRJ-041)."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(start=at(10, 8), end=at(12, 18), rental_days=1)
        self.lamp = make_stock("L-010", 6, "LED-Scheinwerfer", price="20.00")
        self.base = f"{API}/projects/{self.project.pk}"

    def test_line_is_prefilled_from_the_product_and_reports_availability(self) -> None:
        """PRJ-011, PRJ-012, PRJ-015."""
        response = self.admin.post(
            f"{self.base}/material-lines", {"product": self.lamp.pk, "quantity": "4"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.json())
        self.assertEqual(response.json()["title"], "LED-Scheinwerfer")
        self.assertEqual(response.json()["unit_price"], "20.00")
        self.assertEqual(response.json()["billing_mode"], "daily_piece")
        self.assertEqual(response.json()["availability"]["status"], "ok")
        self.assertEqual(response.json()["price"]["amount"], "80.00")
        self.assertEqual(Decimal(response.json()["price"]["scale_factor"]), Decimal("1"))

    def test_line_period_defaults_to_the_project_and_can_differ(self) -> None:
        """PRJ-013."""
        default = self.admin.post(f"{self.base}/material-lines", {"product": self.lamp.pk}, format="json").json()
        self.assertEqual(MaterialLine.objects.get(pk=default["id"]).start, self.project.start)
        own = self.admin.post(
            f"{self.base}/material-lines",
            {"product": self.lamp.pk, "start": at(11, 8).isoformat(), "end": at(11, 20).isoformat()},
            format="json",
        )
        self.assertEqual(own.status_code, 201, own.json())
        self.assertEqual(MaterialLine.objects.get(pk=own.json()["id"]).start, at(11, 8))

    def test_shortage_is_reported_but_the_line_is_saved(self) -> None:
        """PRJ-012, VFG-005: the system warns, it does not block."""
        response = self.admin.post(
            f"{self.base}/material-lines", {"product": self.lamp.pk, "quantity": "8"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.json())
        self.assertEqual(response.json()["availability"]["status"], "short")
        self.assertEqual(response.json()["availability"]["shortage"], 2)
        self.assertEqual(self.admin.get(f"{self.base}/planning").json()["shortage_total"], 2)

    def test_product_of_a_line_cannot_be_changed(self) -> None:
        line = add_line(self.project, self.lamp, 2).line
        other = make_product("L-020")
        response = self.admin.patch(f"{self.base}/material-lines/{line.pk}", {"product": other.pk}, format="json")
        self.assert_error(response, 400, "validation_error", "product")

    def test_free_line_without_product(self) -> None:
        """PRJ-016."""
        response = self.admin.post(
            f"{self.base}/material-lines",
            {"title": "Sonderbau Bühnenkante", "quantity": "1", "unit_price": "250.00", "billing_mode": "flat"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.json())
        self.assertIsNone(response.json()["product"])
        self.assertEqual(response.json()["price"]["amount"], "250.00")
        self.assertEqual(response.json()["availability"]["status"], "unchecked")
        missing_title = self.admin.post(f"{self.base}/material-lines", {"quantity": "1"}, format="json")
        self.assert_error(missing_title, 400, "validation_error")

    def test_deactivated_product_cannot_be_added(self) -> None:
        self.lamp.is_active = False
        self.lamp.save()
        response = self.admin.post(f"{self.base}/material-lines", {"product": self.lamp.pk}, format="json")
        self.assert_error(response, 400, "validation_error")

    def test_groups_with_subtotals_discount_and_optional_groups(self) -> None:
        """PRJ-014, PRJ-024, PRJ-039, PRJ-040."""
        front = self.admin.post(f"{self.base}/groups", {"name": "Licht Front-Traverse"}, format="json")
        self.assertEqual(front.status_code, 201, front.json())
        rear = self.admin.post(
            f"{self.base}/groups", {"name": "Licht Rear-Traverse", "discount_percent": "10"}, format="json"
        ).json()
        fog = self.admin.post(f"{self.base}/groups", {"name": "Nebel", "kind": "optional"}, format="json").json()
        for group, quantity in ((front.json(), 2), (rear, 2), (fog, 1)):
            created = self.admin.post(
                f"{self.base}/material-lines",
                {"product": self.lamp.pk, "quantity": str(quantity), "group": group["id"]},
                format="json",
            )
            self.assertEqual(created.status_code, 201, created.json())
        totals = self.admin.get(f"{self.base}/totals").json()
        subtotals = {group["name"]: group["subtotal"] for group in totals["groups"]}
        self.assertEqual(subtotals, {"Licht Front-Traverse": "40.00", "Licht Rear-Traverse": "36.00", "Nebel": "20.00"})
        self.assertEqual(totals["net_total"], "76.00")
        self.assertEqual(totals["optional_total"], "20.00")
        self.assertEqual(totals["discount_total"], "4.00")
        self.assertEqual(totals["tax"][0]["tax"], "14.44")
        self.assertEqual(totals["gross_total"], "90.44")

    def test_group_accepts_only_one_kind_of_price_adjustment(self) -> None:
        response = self.admin.post(
            f"{self.base}/groups", {"name": "Licht", "discount_percent": "10", "flat_price": "100.00"}, format="json"
        )
        self.assert_error(response, 400, "validation_error")

    def test_group_of_another_project_is_rejected(self) -> None:
        foreign = add_group(make_project("Anderes"), "Fremd")
        response = self.admin.post(
            f"{self.base}/material-lines", {"product": self.lamp.pk, "group": foreign.pk}, format="json"
        )
        self.assert_error(response, 400, "validation_error", "group")

    def test_lines_and_groups_can_be_rearranged(self) -> None:
        """PRJ-014: sorting by dragging stores the new order."""
        front = add_group(self.project, "Front")
        rear = add_group(self.project, "Rear")
        first = add_line(self.project, self.lamp, 1, group=front).line
        second = add_line(self.project, self.lamp, 1, group=front).line
        layout = [{"group": rear.pk, "lines": [second.pk, first.pk]}, {"group": front.pk, "lines": []}]
        self.assertEqual(self.admin.post(f"{self.base}/arrange", {"layout": layout}, format="json").status_code, 204)
        planning = self.admin.get(f"{self.base}/planning").json()
        by_name = {group["name"]: [line["id"] for line in group["lines"]] for group in planning["groups"]}
        self.assertEqual(by_name, {"Front": [], "Rear": [second.pk, first.pk]})

        self.assertEqual(
            self.admin.post(f"{self.base}/groups/reorder", {"groups": [rear.pk, front.pk]}, format="json").status_code,
            204,
        )
        self.assertEqual([group["name"] for group in self.admin.get(f"{self.base}/groups").json()], ["Rear", "Front"])

    def test_group_can_be_copied_into_another_project(self) -> None:
        """PRJ-041."""
        front = add_group(self.project, "Front")
        add_line(self.project, self.lamp, 3, group=front)
        target = make_project("Jazznacht", start=at(20), end=at(21))
        response = self.admin.post(f"{self.base}/groups/{front.pk}/copy", {"target_project": target.pk}, format="json")
        self.assertEqual(response.status_code, 201, response.json())
        copied = MaterialLine.objects.get(project=target)
        self.assertEqual(copied.quantity, 3)
        self.assertEqual(copied.start, target.start)

    def test_deleting_a_group_keeps_its_lines_unless_asked_otherwise(self) -> None:
        front = add_group(self.project, "Front")
        line = add_line(self.project, self.lamp, 1, group=front).line
        self.assertEqual(self.admin.delete(f"{self.base}/groups/{front.pk}").status_code, 204)
        self.assertIsNone(MaterialLine.objects.get(pk=line.pk).group)
        rear = add_group(self.project, "Rear")
        add_line(self.project, self.lamp, 1, group=rear)
        self.assertEqual(self.admin.delete(f"{self.base}/groups/{rear.pk}?lines=delete").status_code, 204)
        self.assertEqual(MaterialLine.objects.filter(project=self.project).count(), 1)


class PriceRightTests(ApiTestCase):
    """Prices have their own right, whatever the module rights are (AUT-019)."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(rental_days=1)
        self.lamp = make_stock("L-010", 6, price="20.00")
        self.line = add_line(self.project, self.lamp, 2).line
        # AUT-032: availability is a special right of its own – this planner has it, prices not.
        Role.objects.create(
            name="Planung", module_levels={"projects": 2, "products": 1}, special_rights=["availability"]
        )
        self.planner = self.client_for("pia", "Planung")
        self.base = f"{API}/projects/{self.project.pk}"

    def test_planning_is_delivered_without_any_amount(self) -> None:
        planning = self.planner.get(f"{self.base}/planning")
        self.assertEqual(planning.status_code, 200)
        self.assertNotIn("totals", planning.json())
        line = planning.json()["without_group"][0]
        for hidden in ("unit_price", "discount_percent", "price", "purchase_price", "billing_mode"):
            self.assertNotIn(hidden, line)
        self.assertEqual(line["availability"]["status"], "ok")
        self.assertNotIn("20.00", planning.content.decode())

    def test_totals_and_price_overview_are_refused(self) -> None:
        self.assert_error(self.planner.get(f"{self.base}/totals"), 403, "permission_denied")
        self.assert_error(self.planner.get(f"{self.base}/price-overview"), 403, "permission_denied")

    def test_lines_can_be_planned_but_prices_cannot_be_set(self) -> None:
        created = self.planner.post(
            f"{self.base}/material-lines", {"product": self.lamp.pk, "quantity": "1"}, format="json"
        )
        self.assertEqual(created.status_code, 201, created.json())
        self.assertNotIn("price", created.json())
        # The price was still copied from the product for those who may see it.
        self.assertEqual(MaterialLine.objects.get(pk=created.json()["id"]).unit_price, Decimal("20.00"))
        refused = self.planner.patch(
            f"{self.base}/material-lines/{self.line.pk}", {"unit_price": "1.00"}, format="json"
        )
        self.assert_error(refused, 400, "validation_error", "unit_price")
        discount = self.planner.post(f"{self.base}/groups", {"name": "Licht", "discount_percent": "50"}, format="json")
        self.assert_error(discount, 400, "validation_error", "discount_percent")

    def test_history_hides_price_changes(self) -> None:
        self.admin.patch(f"{self.base}/material-lines/{self.line.pk}", {"unit_price": "25.00"}, format="json")
        visible = self.admin.get(f"{self.base}/history").content.decode()
        self.assertIn("25,00", visible)
        hidden = self.planner.get(f"{self.base}/history").content.decode()
        self.assertNotIn("25,00", hidden)


class RentalScaleAndSurchargeTests(ApiTestCase):
    """Rental days, scale and surcharges through the API (PRD-031 to PRD-039)."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(rental_days=2)
        self.lamp = make_stock("L-010", 6, price="20.00")
        self.base = f"{API}/projects/{self.project.pk}"

    def test_line_shows_days_factor_and_amount(self) -> None:
        """PRD-035."""
        line = self.admin.post(
            f"{self.base}/material-lines", {"product": self.lamp.pk, "quantity": "4"}, format="json"
        ).json()
        self.assertEqual(line["price"]["rental_days"], 2)
        self.assertEqual(Decimal(line["price"]["scale_factor"]), Decimal("1.5"))
        self.assertEqual(line["price"]["amount"], "120.00")
        one_day = self.admin.patch(f"{self.base}/material-lines/{line['id']}", {"rental_days": 1}, format="json").json()
        self.assertEqual(one_day["price"]["amount"], "80.00")

    def test_changed_scale_applies_only_after_switching(self) -> None:
        """PRD-037."""
        line = self.admin.post(
            f"{self.base}/material-lines", {"product": self.lamp.pk, "quantity": "4"}, format="json"
        ).json()
        scale = RentalScale.objects.get(is_default=True)
        self.admin.post(
            f"{API}/rental-scales/{scale.pk}/publish",
            {"rows": [{"days": 1, "factor": "1.0"}, {"days": 2, "factor": "2.0"}], "extra_day_increment": "1.0"},
            format="json",
        )
        totals = self.admin.get(f"{self.base}/totals").json()
        self.assertEqual(totals["net_total"], "120.00")
        self.assertEqual(totals["lines_with_outdated_scale"], 1)
        self.assertEqual(self.admin.post(f"{self.base}/refresh-scales").json(), {"changed_lines": 1})
        refreshed = self.admin.get(f"{self.base}/material-lines").json()
        self.assertEqual(refreshed[0]["id"], line["id"])
        self.assertEqual(refreshed[0]["price"]["amount"], "160.00")

    def test_percentage_surcharge_refers_to_chosen_groups(self) -> None:
        """PRD-031, PRJ-058: the surcharge moves to the project block and follows its base."""
        front = add_group(self.project, "Front")
        rear = add_group(self.project, "Rear")
        add_line(self.project, self.lamp, 2, group=front)
        add_line(self.project, self.lamp, 1, group=rear)
        night = make_product(
            "A-002", "Nachtzuschlag", kind="surcharge", surcharge_type="percent", surcharge_percent="10", price=None
        )
        line = self.admin.post(f"{self.base}/material-lines", {"product": night.pk}, format="json")
        self.assertEqual(line.status_code, 201, line.json())
        targets = [{"type": "group", "id": front.pk}, {"type": "group", "id": rear.pk}]
        saved = self.admin.put(
            f"{self.base}/material-lines/{line.json()['id']}/surcharge-targets", targets, format="json"
        )
        self.assertEqual(saved.status_code, 200, saved.json())
        self.assertEqual(len(saved.json()), 2)

        planning = self.admin.get(f"{self.base}/planning").json()
        self.assertEqual([row["id"] for row in planning["surcharges"]], [line.json()["id"]])
        self.assertEqual(planning["surcharges"][0]["price"]["surcharge_base"], "90.00")
        self.assertEqual(planning["surcharges"][0]["price"]["amount"], "9.00")
        self.assertEqual(planning["totals"]["net_total"], "99.00")

    def test_surcharge_cannot_refer_to_another_surcharge(self) -> None:
        express = make_product("A-001", "Expresszuschlag", kind="surcharge", price="50.00", billing_mode="flat")
        fixed = add_line(self.project, express, 1).line
        night = make_product(
            "A-002", "Nachtzuschlag", kind="surcharge", surcharge_type="percent", surcharge_percent="10", price=None
        )
        percent = add_line(self.project, night, 1).line
        response = self.admin.put(
            f"{self.base}/material-lines/{percent.pk}/surcharge-targets",
            [{"type": "line", "id": fixed.pk}],
            format="json",
        )
        self.assert_error(response, 400, "validation_error")

    def test_price_overview_in_two_levels_of_detail(self) -> None:
        """PRJ-036, DOK-009."""
        front = add_group(self.project, "Front")
        add_line(self.project, self.lamp, 2, group=front)
        add_line(self.project, self.lamp, 1)
        detailed = self.admin.get(f"{self.base}/price-overview").json()
        self.assertTrue(detailed["internal_working_document"])
        self.assertEqual(detailed["groups"][0]["lines"][0]["article_number"], "L-010")
        self.assertEqual(detailed["groups"][0]["lines"][0]["amount"], "60.00")
        self.assertEqual(detailed["without_group"]["lines"][0]["amount"], "30.00")
        self.assertEqual(detailed["totals"]["net_total"], "90.00")
        compact = self.admin.get(f"{self.base}/price-overview", {"detail": "groups"}).json()
        self.assertNotIn("lines", compact["groups"][0])
        self.assertEqual(compact["groups"][0]["subtotal"], "60.00")
        self.assertNotIn("subrental_cost", compact["totals"])
        # PRJ-066: what each block contains, in one line.
        self.assertEqual(compact["groups"][0]["summary"], f"2 × {self.lamp.name}")
        self.assertEqual(compact["without_group"]["summary"], f"1 × {self.lamp.name}")
        self.assertEqual(compact["personnel"]["summary"], "")


class ShortageAndSubrentalTests(ApiTestCase):
    """Shortages, the subrental suggestion and costs (PRJ-017, PRJ-018, PRJ-054 to PRJ-057)."""

    def setUp(self) -> None:
        super().setUp()
        self.cable = make_stock("K-005", 9, "XLR-Kabel 5 m", price="1.50")
        first = make_project("P1", start=at(10), end=at(12))
        add_line(first, self.cable, 6)
        self.project = make_project("P2", start=at(11), end=at(13), rental_days=1)
        self.line = add_line(self.project, self.cable, 4).line
        self.base = f"{API}/projects/{self.project.pk}"

    def test_shortage_lists_and_suggestion(self) -> None:
        own = self.admin.get(f"{self.base}/shortages").json()
        self.assertEqual(len(own), 1)
        self.assertEqual(own[0]["shortage"], 1)
        self.assertEqual(own[0]["suggestion"], {"line": self.line.pk, "product": self.cable.pk, "quantity": 1})
        # One cable is missing while both projects are out. It is reported for
        # each of them: either project can solve it (decision in docs/dev/decisions.md).
        overview = self.admin.get(f"{API}/shortages").json()
        self.assertEqual(
            [(row["project_name"], row["article_number"], row["shortage"]) for row in overview],
            [("P1", "K-005", 1), ("P2", "K-005", 1)],
        )

    def test_accepting_the_suggestion_covers_the_shortage_without_changing_the_price(self) -> None:
        """PRJ-054, PRJ-055."""
        before = self.admin.get(f"{self.base}/totals").json()["net_total"]
        supplier = Supplier.objects.create(name="Verleih Nord")
        response = self.admin.post(
            f"{self.base}/shortages/accept",
            {
                "line": self.line.pk,
                "product": self.cable.pk,
                "quantity": 1,
                "supplier": supplier.pk,
                "purchase_price": "4.00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.json())
        self.assertEqual(response.json()["kind"], "subrental")
        self.assertEqual(response.json()["covers_line"], self.line.pk)
        # PRJ-101: without a status sent, a subrental starts "open" – also with a supplier.
        self.assertEqual(response.json()["subrental_status"], "open")

        self.assertEqual(self.admin.get(f"{self.base}/shortages").json(), [])
        self.assertEqual(self.admin.get(f"{API}/shortages").json(), [])
        totals = self.admin.get(f"{self.base}/totals").json()
        self.assertEqual(totals["net_total"], before)
        self.assertEqual(totals["subrental_cost"], "4.00")
        self.assertEqual(Decimal(totals["contribution_margin"]), Decimal(before) - Decimal("4.00"))

        subrentals = self.admin.get(f"{API}/subrentals").json()
        self.assertEqual(len(subrentals), 1)
        self.assertEqual(subrentals[0]["supplier_name"], "Verleih Nord")
        self.assertEqual(subrentals[0]["purchase_price"], "4.00")

    def test_subrental_status_can_be_followed(self) -> None:
        """PRJ-057: requested, ordered, received; PRJ-101: with the supplier."""
        supplier = Supplier.objects.create(name="Verleih Nord")
        subrental = self.admin.post(
            f"{self.base}/shortages/accept",
            {"line": self.line.pk, "product": self.cable.pk, "quantity": 1, "supplier": supplier.pk},
            format="json",
        ).json()
        changed = self.admin.patch(
            f"{self.base}/material-lines/{subrental['id']}", {"subrental_status": "ordered"}, format="json"
        )
        self.assertEqual(changed.status_code, 200, changed.json())
        self.assertEqual(self.admin.get(f"{API}/subrentals").json()[0]["status"], "ordered")

    def test_costs_need_the_purchase_price_right(self) -> None:
        self.admin.post(
            f"{self.base}/shortages/accept",
            {"line": self.line.pk, "product": self.cable.pk, "quantity": 1, "purchase_price": "4.00"},
            format="json",
        )
        Role.objects.create(name="Vertrieb", module_levels={"projects": 2}, special_rights=["prices"])
        sales = self.client_for("vera", "Vertrieb")
        totals = sales.get(f"{self.base}/totals").json()
        self.assertNotIn("subrental_cost", totals)
        self.assertNotIn("contribution_margin", totals)
        self.assertNotIn("purchase_price", sales.get(f"{API}/subrentals").json()[0])
        self.assertNotIn("purchase_price", sales.get(f"{self.base}/material-lines").json()[0])

    def test_suggestion_cannot_be_accepted_for_a_foreign_line(self) -> None:
        other = make_project("P3", start=at(20), end=at(21))
        foreign = add_line(other, self.cable, 1).line
        response = self.admin.post(
            f"{self.base}/shortages/accept",
            {"line": foreign.pk, "product": self.cable.pk, "quantity": 1},
            format="json",
        )
        self.assert_error(response, 404, "not_found")
