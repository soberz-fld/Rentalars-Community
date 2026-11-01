# SPDX-License-Identifier: GPL-3.0-or-later
"""Acceptance scenario 15 – Personal über Dienstleistungsprodukt (catalogue chapter 11)."""

from decimal import Decimal

from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.products.models import BillingMode
from rentalars.projects import crew
from rentalars.projects.models import CrewBilling
from rentalars.projects.pricing import compute_project_prices
from tests.helpers import (
    ALL_RIGHTS,
    add_group,
    add_line,
    at,
    job_function,
    make_person,
    make_product,
    make_project,
    plan,
    record_time,
)
from tests.ui.base import UiTestCase

D = Decimal


class Scenario15PersonnelThroughServiceProduct(UiTestCase):
    """PER-008, PER-018, PRJ-038, PRJ-051, PRJ-061, AUT-019."""

    def setUp(self) -> None:
        super().setUp()
        # Given: the job function Tontechnik is linked to its service product "Tontechniker, Stunde" at 45.00 …
        # (every job function has its own, PRD-044; the start data numbers them D-001 to D-008).
        self.sound = job_function("Tontechnik")
        self.product = self.sound.service_product
        self.product.name, self.product.price, self.product.billing_mode = (
            "Tontechniker, Stunde",
            D("45.00"),
            BillingMode.HOURLY,
        )
        self.product.save()
        # … and person A has the hourly rate 35.00 for Tontechnik.
        self.person = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        self.project = make_project("Stadtfest")
        group = add_group(self.project, "Ton FOH")
        add_line(self.project, make_product("T-030", "Digitalmischpult", price="120.00"), 1, group=group, rental_days=1)
        # A is planned for 8 hours – by plan (a new line is billed by effort, PER-036).
        self.line = plan(
            self.project,
            self.sound,
            self.person,
            start=at(10, 8),
            end=at(10, 20),
            planned_hours=D("8"),
            billing=CrewBilling.PLAN,
        )

    def price(self) -> crew.CrewPrice:
        return crew.price_crew_lines(self.project)[0]

    def test_eight_hours_show_a_price_of_360_and_internal_costs_of_280(self) -> None:
        self.assertEqual((self.price().amount, self.price().cost), (D("360.00"), D("280.00")))
        planning = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.project.pk])))
        block = planning[planning.index('id="planning-crew"') :]
        self.assertIn(self.product.article_number, block)
        self.assertIn("360,00", block)
        self.assertIn("280,00", block)

    def test_costs_show_only_with_the_right_for_personnel_costs(self) -> None:
        """AUT-019: the price right alone shows the price, not what the person earns."""
        Role.objects.create(name="Vertrieb", module_levels={"projects": 2}, special_rights=["prices"])
        page = self.assert_ok(
            self.browser_for("vera", "Vertrieb").get(reverse("projects:detail", args=[self.project.pk]))
        )
        block = page[page.index('id="planning-crew"') :]
        self.assertIn("360,00", block)
        self.assertNotIn("280,00", page)
        self.assertNotIn("35,00", page)

    def test_price_overview_lists_the_360_in_the_block_personnel_not_in_a_group(self) -> None:
        prices = compute_project_prices(self.project)
        self.assertEqual(prices.personnel_total, D("360.00"))
        self.assertEqual([group.subtotal for group in prices.groups], [D("120.00")])
        self.assertEqual(prices.net_total, D("480.00"))

        overview = self.assert_ok(self.client.get(reverse("projects:price_overview", args=[self.project.pk])))
        group = overview[overview.index("Ton FOH") : overview.index("Personal")]
        self.assertNotIn("Tontechniker", group)
        personnel = overview[overview.index("Personal") :]
        self.assertIn("Tontechniker, Stunde", personnel)
        self.assertIn("360,00", personnel)
        # The hourly rate of A does not appear there – for nobody, whatever their rights.
        self.assertNotIn("35,00", overview)
        self.assertNotIn("280,00", overview)

    def test_with_an_agreed_flat_rate_the_costs_are_300_whatever_the_hours(self) -> None:
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, cost_flat_rate=D("300.00"))
        self.assertEqual((self.price().amount, self.price().cost), (D("360.00"), D("300.00")))
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, planned_hours=D("12"))
        self.assertEqual((self.price().amount, self.price().cost), (D("540.00"), D("300.00")))

    def test_by_effort_and_9_5_approved_hours_the_price_is_427_50(self) -> None:
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, billing=CrewBilling.EFFORT)
        # Until the approval, the 360.00 stand as an estimate – marked as such.
        self.assertEqual((self.price().amount, self.price().is_estimate), (D("360.00"), True))
        planning = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.project.pk])))
        block = planning[planning.index('id="planning-crew"') :]
        self.assertIn("Schätzung", block)
        self.assertIn("enthält Schätz", planning)
        self.assertTrue(compute_project_prices(self.project).has_estimates)

        entry = record_time(self.person, self.project, self.sound, at(10, 8), at(10, 18), break_minutes=30, submit=True)
        self.assertEqual(entry.hours, D("9.50"))
        self.assertEqual(self.price().amount, D("360.00"))  # handed in is not approved

        from rentalars.timetracking import services as times

        times.approve_entries([entry], rights=ALL_RIGHTS, user=self.admin_user)
        self.assertEqual((self.price().amount, self.price().is_estimate), (D("427.50"), False))
        self.assertEqual(compute_project_prices(self.project).personnel_total, D("427.50"))
