# SPDX-License-Identifier: GPL-3.0-or-later
"""Acceptance scenario 18 – Eingeschränktes Konto und Freigabe (catalogue chapter 11)."""

from decimal import Decimal

from django.urls import reverse

from rentalars.projects import crew
from rentalars.timetracking.models import TimeEntry
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    LATER,
    add_group,
    add_line,
    at,
    job_function,
    make_person,
    make_product,
    make_project,
    make_user,
    plan,
    set_clock,
)
from tests.ui.base import form_data

D = Decimal


class Scenario18RestrictedAccountAndApproval(ApiTestCase):
    """AUT-023, AUT-025, PER-019, ZEI-012, ZEI-013, ZEI-021."""

    def setUp(self) -> None:
        super().setUp()
        set_clock(LATER)  # the hours of 10 March are recorded afterwards (ZEI-022)
        self.hand = job_function("Stagehand", price="28.00")
        self.project = make_project("Stadtfest", venue="Marktplatz Musterstadt")
        self.other = make_project("Jazznacht")
        front = add_group(self.project, "Licht Front-Traverse")
        add_line(self.project, make_product("L-010", "LED-Scheinwerfer", price="23.45"), 4, group=front, rental_days=1)

        # A freelancer with an account of her own, planned as stagehand.
        self.user = make_user("frieda", roles=("Freie Kraft",))
        self.freelancer = make_person("Frieda Frei", kind="freelancer", rates={"Stagehand": "20.00"}, user=self.user)
        self.line = plan(
            self.project, self.hand, self.freelancer, start=at(10, 8), end=at(10, 16), meeting_point="Rampe"
        )
        # Two colleagues: one released her phone number, the other did not.
        anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"}, phone="0170 5550101", share_phone=True)
        tom = make_person("Tom Richter", rates={"Lichttechnik": "38.00"}, phone="0171 5550102")
        plan(self.project, "Tontechnik", anna, start=at(10, 8), end=at(10, 22))
        plan(self.project, "Lichttechnik", tom, start=at(10, 8), end=at(10, 22))

        self.client.force_login(self.user)
        self.manager = make_user("paula", roles=("Projektleitung",))

    def test_project_list_shows_only_projects_she_is_planned_in(self) -> None:
        page = self.client.get(reverse("projects:list")).content.decode()
        self.assertIn("Stadtfest", page)
        self.assertNotIn("Jazznacht", page)
        self.assertIn("Stadtwerke", page)  # PRJ-122: the customer's name shows in every role
        self.assertNotIn("/customers/", page)  # … as text, no link
        self.assertEqual(self.client.get(reverse("projects:detail", args=[self.other.pk])).status_code, 404)
        api = self.client_of(self.user).get(f"{API}/projects").json()["results"]
        self.assertEqual([row["name"] for row in api], ["Stadtfest"])

    def test_in_the_project_she_sees_time_place_and_job_function_and_nothing_else(self) -> None:
        # The planning page leads her to the deployment view.
        response = self.client.get(reverse("projects:detail", args=[self.project.pk]), follow=True)
        self.assertEqual(response.redirect_chain[-1][0], reverse("projects:deployment", args=[self.project.pk]))
        page = response.content.decode()
        for shown in (
            "Marktplatz Musterstadt",
            "Stagehand",
            "Rampe",
            "10.03.2027 08:00",
            "Mein Stundensatz hier: 20,00",
        ):
            self.assertIn(shown, page)
        # No prices, no rates of others, no planning – the customer's name, yes (PRJ-122).
        self.assertIn("Stadtwerke", page)
        for hidden in (
            "23,45",
            "93,80",
            "35,00",
            "38,00",
            "28,00",
            "LED-Scheinwerfer",
            "Preisübersicht",
            "Verlauf",
        ):
            self.assertNotIn(hidden, page)
        for name in ("projects:price_overview", "projects:history", "projects:members", "projects:edit"):
            self.assertEqual(self.client.get(reverse(name, args=[self.project.pk])).status_code, 403, name)

    def test_her_times_are_submitted_until_project_management_approves_them(self) -> None:
        quick = reverse("timetracking:quick")
        dialog = self.client.get(quick, {"project": self.project.pk}, HTTP_HX_REQUEST="true")
        saved = self.client.post(
            quick,
            form_data(dialog, day="2027-03-10", begin="08:00", end="16:30", break_minutes="30"),
            HTTP_HX_REQUEST="true",
        )
        self.assertIn("Zur Freigabe eingereicht", saved.content.decode())
        entry = TimeEntry.objects.get()
        self.assertEqual((entry.status, entry.hours), ("submitted", D("8.00")))
        self.assertIn(
            "eingereicht", self.client.get(reverse("timetracking:my_times"), {"week": "2027-03-10"}).content.decode()
        )
        # Not approved yet: the times do not count in the project.
        self.assertEqual(crew.price_crew_lines(self.project)[0].approved_hours, D("0"))
        # She cannot approve them herself.
        self.assertEqual(self.client.get(reverse("timetracking:approval")).status_code, 403)

        office = self.client_class()
        office.force_login(self.manager)
        waiting = office.get(reverse("timetracking:approval"))
        self.assertIn("Frieda Frei", waiting.content.decode())
        office.post(reverse("timetracking:decide"), form_data(waiting, containing="entry") | {"decision": "approve"})

        # Afterwards they are locked …
        entry.refresh_from_db()
        self.assertEqual(entry.status, "approved")
        self.assertTrue(entry.is_locked)
        locked = self.client_of(self.user).patch(
            f"{API}/time-entries/{entry.pk}", {"note": "doch länger"}, format="json"
        )
        self.assert_error(locked, 400, "validation_error")
        self.assertEqual(self.client.post(reverse("timetracking:entry_delete", args=[entry.pk])).status_code, 302)
        self.assertTrue(TimeEntry.objects.filter(pk=entry.pk).exists())
        # … and count in the comparison of planned and actual hours and in the costs of the project.
        price = next(price for price in crew.price_crew_lines(self.project) if price.line == self.line)
        self.assertEqual(
            (price.planned_hours, price.approved_hours, price.actual_cost), (D("8.00"), D("8.00"), D("160.00"))
        )

    def test_she_sees_the_packlist_and_the_names_of_her_colleagues(self) -> None:
        packlist = self.client.get(reverse("packing:packlist", args=[self.project.pk]))
        self.assertEqual(packlist.status_code, 200)
        text = packlist.content.decode()
        self.assertIn("LED-Scheinwerfer", text)
        self.assertIn("Stadtwerke", text)  # PRJ-122
        self.assertNotIn("23,45", text)
        # Reading only: issue and return are not hers.
        self.assertEqual(self.client.post(reverse("packing:action", args=[self.project.pk, "issue"])).status_code, 403)
        self.assertEqual(self.client.get(reverse("packing:packlist", args=[self.other.pk])).status_code, 404)

        page = self.client.get(reverse("projects:deployment", args=[self.project.pk])).content.decode()
        self.assertIn("Anna Becker", page)
        self.assertIn("Tom Richter", page)

    def test_a_colleagues_phone_number_shows_only_if_released(self) -> None:
        """PER-019."""
        page = self.client.get(reverse("projects:deployment", args=[self.project.pk])).content.decode()
        self.assertIn("0170 5550101", page)
        self.assertNotIn("0171 5550102", page)
        self.assertIn("nicht freigegeben", page)
        # Project management sees the number in any case.
        office = self.client_class()
        office.force_login(self.manager)
        self.assertIn(
            "0171 5550102", office.get(reverse("projects:deployment", args=[self.project.pk])).content.decode()
        )
