# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages: "My area", the tabs of "Personnel", uniform tabs, series (UIX-026, UIX-027, PER-028)."""

from __future__ import annotations

import datetime
import re

from django.urls import reverse

from rentalars.customers.models import Venue
from rentalars.personnel import marks as availability_marks
from rentalars.personnel.models import AvailabilityRepeat, AvailabilitySeries, AvailabilityState, Person
from tests.helpers import at, make_person, make_user
from tests.ui.base import UiTestCase, form_data

RED, YELLOW = AvailabilityState.UNAVAILABLE, AvailabilityState.LIMITED


def navigation(text: str) -> list[str]:
    """The labels of the main navigation of a page."""
    nav = text.split('<ul class="nav">', 1)[1].split("</ul>", 1)[0]
    return [re.sub(r"<[^>]+>", "", item).strip() for item in nav.split("<li>")[1:]]


def tabs(text: str) -> list[str]:
    """The labels of the first tab bar of a page."""
    bar = text.split('<nav class="tabs"', 1)[1].split("</nav>", 1)[0]
    return [re.sub(r"<[^>]+>", "", label).strip() for label in re.findall(r"<a [^>]*>(.*?)</a>", bar, re.S)]


class MyAreaTests(UiTestCase):
    """UIX-026: "My area" holds what everybody does for themselves; approving and the report are in "Personnel".

    ZEI-019: "My area" has "Meine Spesen", "Personnel" the tab "Spesen" (the report of expenses).
    """

    def test_crew_find_availability_times_and_their_data_in_my_area(self) -> None:
        crew = self.browser_for("carla", "Crew")
        text = self.assert_ok(crew.get(reverse("personnel:own_availability")))
        self.assertIn("Mein Bereich", navigation(text))
        self.assertNotIn("Zeiterfassung", navigation(text))
        self.assertNotIn("Personal", navigation(text))
        # The own service cases (PRJ-108); "Meine Einsätze" first (UIX-043).
        self.assertEqual(
            tabs(text),
            [
                "Meine Einsätze",
                "Verfügbarkeit",
                "Meine Zeiten",
                "Meine Spesen",
                "Auswertung",
                "Servicefälle",
                "Personaldaten",
            ],
        )
        self.assertIn('href="/me/availability/" aria-current="page"', text)
        # The own report of hours is a tab of "My area" for those who see only their own times.
        report = self.assert_ok(crew.get(reverse("timetracking:report")))
        self.assertIn("<h1>Mein Bereich</h1>", report)
        self.assertEqual(
            tabs(report),
            [
                "Meine Einsätze",
                "Verfügbarkeit",
                "Meine Zeiten",
                "Meine Spesen",
                "Auswertung",
                "Servicefälle",
                "Personaldaten",
            ],
        )
        profile = self.assert_ok(crew.get(reverse("personnel:own_profile")))
        self.assertNotIn("data-avail-calendar", profile)
        self.assertIn("Kontaktdaten", profile)

    def test_approving_and_the_report_are_tabs_of_personnel(self) -> None:
        dispatcher = self.browser_for("dora", "Personaldisposition")
        for name in ("timetracking:approval", "timetracking:report"):
            with self.subTest(page=name):
                text = self.assert_ok(dispatcher.get(reverse(name)))
                self.assertIn("<h1>Personal</h1>", text)
                self.assertEqual(
                    tabs(text), ["Personen", "Verfügbarkeit", "Funktionen", "Freigeben", "Auswertung", "Spesen"]
                )
                self.assertIn('aria-current="page"><svg', text.split('<ul class="nav">')[1].split("Personal")[0])
        mine = self.assert_ok(dispatcher.get(reverse("timetracking:my_times")))
        # The own service cases (PRJ-108).
        self.assertEqual(
            tabs(mine),
            ["Meine Einsätze", "Verfügbarkeit", "Meine Zeiten", "Meine Spesen", "Servicefälle", "Personaldaten"],
        )
        self.assertEqual(
            tabs(self.assert_ok(dispatcher.get(reverse("personnel:person_list")))),
            ["Personen", "Verfügbarkeit", "Funktionen", "Freigeben", "Auswertung", "Spesen"],
        )

    def test_the_old_profile_address_still_works_and_leads_to_the_calendar(self) -> None:
        crew = self.browser_for("carla", "Crew")
        text = self.assert_ok(crew.get(reverse("personnel:own_profile")))
        self.assertIn(reverse("personnel:own_availability"), text)


class UniformTabsTests(UiTestCase):
    """UIX-027: pages of tabs show no "Back"; the pages below them do; leads stand below the tabs."""

    def test_pages_of_tabs_have_no_back_link(self) -> None:
        for name in (
            "customers:venue_list",
            "material:inspections",
            "projects:open_items",
            "personnel:own_availability",
            "timetracking:approval",
            "notifications:list",
        ):
            with self.subTest(page=name):
                text = self.assert_ok(self.client.get(reverse(name)))
                self.assertNotIn('class="back-link', text)

    def test_pages_below_have_one(self) -> None:
        self.client.get(reverse("notifications:list"))
        text = self.assert_ok(self.client.get(reverse("notifications:preferences")))
        self.assertIn('class="back-link no-print" href="/notifications/"', text)

    def test_on_the_phone_back_is_always_at_the_top(self) -> None:
        tab_page = self.assert_ok(self.client.get(reverse("customers:venue_list")))
        self.assertIn('class="icon-btn topbar-back" href="/" data-history-back', tab_page)
        self.client.get(reverse("notifications:list"))
        below = self.assert_ok(self.client.get(reverse("notifications:preferences")))
        self.assertIn('class="icon-btn topbar-back" href="/notifications/"', below)
        self.assertNotIn("topbar-back", self.assert_ok(self.client.get(reverse("core:home"))))

    def test_the_lead_of_shortages_stands_below_the_tabs(self) -> None:
        text = self.assert_ok(self.client.get(reverse("availability:shortages")))
        head = text.split('<div class="page-head">', 1)[1].split('<nav class="tabs"', 1)[0]
        self.assertNotIn('class="lead"', head)
        self.assertIn('<p class="tab-lead">Wo laufende', text)

    def test_the_tabs_of_a_person_are_one_place_on_the_way_back(self) -> None:
        anna = make_person("Anna Becker")
        self.client.get(reverse("personnel:person_list"))
        self.client.get(reverse("personnel:person_detail", args=[anna.pk]))
        text = self.assert_ok(self.client.get(reverse("personnel:person_availability", args=[anna.pk])))
        self.assertIn('class="back-link no-print" href="/personnel/"', text)


class SeriesPagesTests(UiTestCase):
    """PER-028: entering, changing and removing a series on "My area → Availability"."""

    def setUp(self) -> None:
        super().setUp()
        self.user = make_user("carla", roles=("Crew",))
        self.browser = self.browser_of(self.user)
        self.carla = Person.objects.get(user=self.user)

    def test_enter_a_series(self) -> None:
        page = self.browser.get(reverse("personnel:own_availability"))
        data = form_data(page, containing="start_day", start_day="2027-03-02", state=RED, note="Chor")
        data.update(with_times="on", start_time="18:00", end_time="22:00", repeat="weekly", interval="1")
        data.update(weekdays=["1", "3"], until="2027-03-14")
        response = self.browser.post(reverse("personnel:own_availability"), data, follow=True)
        self.assertIn("Serie eingetragen: 4 Termine.", self.messages_of(response))
        series = AvailabilitySeries.objects.get(person=self.carla)
        self.assertEqual((series.weekdays, series.note), ("1,3", "Chor"))
        text = self.assert_ok(response)
        self.assertIn("wöchentlich am Di, Do, 18:00–22:00, ab 02.03.2027, bis 14.03.2027", text)
        self.assertIn(reverse("personnel:own_series", args=[series.pk]), text)

    def test_a_series_needs_an_end(self) -> None:
        page = self.browser.get(reverse("personnel:own_availability"))
        data = form_data(page, containing="start_day", start_day="2027-03-02", state=RED, repeat="daily")
        response = self.browser.post(reverse("personnel:own_availability"), data, follow=True)
        self.assertIn("Gib an, bis wann sich die Serie wiederholt oder wie oft.", " ".join(self.messages_of(response)))
        self.assertFalse(AvailabilitySeries.objects.exists())

    def test_change_and_remove_a_series(self) -> None:
        series = availability_marks.create_series(
            self.carla, state=RED, first_day=datetime.date(2027, 3, 2), last_day=datetime.date(2027, 3, 2),
            repeat=AvailabilityRepeat.WEEKLY, count=4,
        )  # fmt: skip
        url = reverse("personnel:own_series", args=[series.pk])
        page = self.browser.get(url)
        text = self.assert_ok(page)
        self.assertIn("Serie ändern", text)
        self.assertIn('class="back-link', text)
        data = form_data(page, containing="from_day", state=YELLOW, from_day="2027-03-09")
        response = self.browser.post(url, data)
        self.assertRedirects(response, "/me/availability/?month=2027-03#availability", fetch_redirect_response=False)
        states = [mark.state for mark in self.carla.availability_marks.order_by("start")]
        self.assertEqual(states, [RED, YELLOW, YELLOW, YELLOW])
        remove = reverse("personnel:own_series_remove", args=[series.pk])
        self.browser.post(remove, {"from_day": "2027-03-16"})
        self.assertEqual(self.carla.availability_marks.count(), 2)
        self.browser.post(remove, {"all": "1"})
        self.assertFalse(AvailabilitySeries.objects.exists())

    def test_others_series_are_out_of_reach(self) -> None:
        anna = make_person("Anna Becker")
        series = availability_marks.create_series(
            anna, state=RED, first_day=datetime.date(2027, 3, 2), last_day=datetime.date(2027, 3, 2),
            repeat=AvailabilityRepeat.DAILY, count=2,
        )  # fmt: skip
        self.assertEqual(self.browser.get(reverse("personnel:own_series", args=[series.pk])).status_code, 404)
        self.browser.post(reverse("personnel:own_series_remove", args=[series.pk]), {"all": "1"})
        self.assertTrue(AvailabilitySeries.objects.filter(pk=series.pk).exists())
        dispatcher = self.browser_for("dora", "Personaldisposition")
        page = dispatcher.get(reverse("personnel:person_availability", args=[anna.pk]), {"month": "2027-03"})
        self.assertIn(reverse("personnel:person_series", args=[anna.pk, series.pk]), self.assert_ok(page))
        dispatcher.post(reverse("personnel:person_series_remove", args=[anna.pk, series.pk]), {"all": "1"})
        self.assertFalse(AvailabilitySeries.objects.filter(pk=series.pk).exists())

    def test_busy_times_and_entries_are_one_list(self) -> None:
        availability_marks.mark_period(self.carla, at(10), at(11), RED, "Familienfeier")
        text = self.assert_ok(self.browser.get(reverse("personnel:own_availability"), {"month": "2027-03"}))
        self.assertIn("Familienfeier", text)
        self.assertIn("eingetragen", text)


class VenueTests(UiTestCase):
    """KND-009: the plan of a venue is a "site or hall plan"."""

    def test_the_plan_is_called_lageplan_hallenplan(self) -> None:
        venue = Venue.objects.create(name="Stadthalle", city="Musterstadt")
        text = self.assert_ok(self.client.get(reverse("customers:venue_edit", args=[venue.pk])))
        self.assertIn("Lageplan/Hallenplan", text)
