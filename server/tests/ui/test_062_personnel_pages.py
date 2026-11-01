# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages of the requirements for people.

* "Assign a job function" without rate and day, day rates on the person's page, the own profile and the
  job functions (PER-029).
* The week of the availability calendar on both pages (PER-030).
* Several linked calendars on "My area → Availability" and on the tab of the person (PER-031).
* The timeline of a person shows the availability (bug, PER-020).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.core.models import SystemSettings
from rentalars.personnel import calendars, services
from rentalars.personnel import marks as availability_marks
from rentalars.personnel.models import AvailabilityMark, AvailabilitySource, AvailabilityState, Person
from tests.helpers import at, job_function, make_person, make_project, make_user, plan
from tests.ui.base import UiTestCase, form_data
from tests.unit.test_051_personnel_calendars import FEED, serve
from tests.unit.test_062_personnel import BAND

GREEN, YELLOW, RED = AvailabilityState.AVAILABLE, AvailabilityState.LIMITED, AvailabilityState.UNAVAILABLE
D = Decimal


# --- PER-029 ------------------------------------------------------------------------------------------------


class AssignWithoutCostRightPageTests(UiTestCase):
    """PER-029, AUT-019: whoever plans people but does not see their costs assigns functions without rates."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        self.detail = reverse("personnel:person_detail", args=[self.anna.pk])
        self.sound, self.hand = job_function("Tontechnik"), job_function("Stagehand")
        Role.objects.create(name="Personal ohne Kosten", module_levels={"personnel": 2})
        self.browser = self.browser_for("pit", "Personal ohne Kosten")

    def test_the_form_has_only_the_job_function(self) -> None:
        page = self.assert_ok(self.browser.get(self.detail))
        data = form_data(self.browser.get(self.detail), containing="job_function")
        self.assertEqual(set(data) - {"csrfmiddlewaretoken"}, {"job_function"})
        self.assertIn("Sätze trägt ein, wer Personalkosten sehen darf", page)
        done = self.browser.post(
            reverse("personnel:rate_set", args=[self.anna.pk]), {**data, "job_function": self.hand.pk}, follow=True
        )
        self.assertIn(
            "Stagehand: ohne eigene Sätze zugeordnet; es gelten die Richtwerte der Funktion.", self.messages_of(done)
        )
        self.assertTrue(self.anna.rates.filter(job_function=self.hand, hourly_rate__isnull=True).exists())

    def test_assigning_again_keeps_the_rates(self) -> None:
        done = self.browser.post(
            reverse("personnel:rate_set", args=[self.anna.pk]), {"job_function": self.sound.pk}, follow=True
        )
        self.assertIn("Tontechnik: Die Person hat diese Funktion schon.", self.messages_of(done))
        self.assertEqual(services.rate_on(self.anna, self.sound), D("35.00"))

    def test_only_a_function_without_own_rates_can_be_taken_away(self) -> None:
        services.set_rate(self.anna, self.hand)
        page = self.assert_ok(self.browser.get(self.detail))
        self.assertIn(reverse("personnel:rate_remove", args=[self.anna.pk, self.hand.pk]), page)
        self.assertNotIn(reverse("personnel:rate_remove", args=[self.anna.pk, self.sound.pk]), page)
        self.assertEqual(
            self.browser.post(reverse("personnel:rate_remove", args=[self.anna.pk, self.sound.pk])).status_code, 403
        )
        self.browser.post(reverse("personnel:rate_remove", args=[self.anna.pk, self.hand.pk]))
        self.assertFalse(self.anna.rates.filter(job_function=self.hand).exists())


class AssignFunctionPageTests(UiTestCase):
    """PER-029: "Assign a job function" asks neither for a rate nor for a day."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_person("Anna Becker")
        self.detail = reverse("personnel:person_detail", args=[self.anna.pk])
        self.sound = job_function("Tontechnik", guide="30.00")
        self.sound.guide_daily_cost_rate = D("250.00")
        self.sound.save()

    def assign(self, **values: object) -> object:
        page = self.client.get(self.detail)
        data = form_data(page, containing="hourly_rate", job_function=self.sound.pk, **values)
        return self.client.post(reverse("personnel:rate_set", args=[self.anna.pk]), data, follow=True)

    def test_assign_without_rate_and_day(self) -> None:
        page = self.assert_ok(self.client.get(self.detail))
        self.assertIn("Funktion zuordnen", page)
        self.assertIn('name="daily_rate"', page)
        self.assertNotIn('name="valid_from" value=', page)  # no day is suggested any more
        response = self.assign(hourly_rate="", daily_rate="", valid_from="")
        self.assertIn(
            "Tontechnik: ohne eigene Sätze zugeordnet; es gelten die Richtwerte der Funktion.",
            self.messages_of(response),
        )
        self.assertEqual(response.redirect_chain[-1][0], f"/personnel/people/{self.anna.pk}/#rates")
        (row,) = self.anna.rates.all()
        self.assertEqual((row.hourly_rate, row.daily_rate, row.valid_from), (None, None, None))
        text = self.assert_ok(response)
        self.assertIn("immer", text)
        self.assertIn('30,00 € <span class="small">(Richtwert)</span>', text)
        self.assertIn('250,00 € <span class="small">(Richtwert)</span>', text)

    def test_hourly_and_day_rate_from_a_day_on_with_the_history(self) -> None:
        self.assign(hourly_rate="", daily_rate="")
        response = self.assign(hourly_rate="35,00", daily_rate="280,00", valid_from="2027-02-01")
        self.assertIn("Tontechnik: Satz gespeichert", " ".join(self.messages_of(response)))
        rate = services.rate_for(self.anna, self.sound, datetime.date(2027, 3, 1))
        self.assertEqual((rate.own_hourly, rate.own_daily), (D("35.00"), D("280.00")))
        text = self.assert_ok(response)
        self.assertIn("280,00", text)
        self.assertIn("01.02.2027", text)
        self.assertIn("Alle Sätze mit Datum", text)
        self.assertIn("Tagessatz –", text)  # the row without a date in the history

    def test_day_rates_need_the_cost_right(self) -> None:
        services.set_rate(self.anna, self.sound, D("35.00"), daily_rate=D("281.00"))
        Role.objects.create(name="Personal ohne Kosten", module_levels={"personnel": 2})
        browser = self.browser_for("pit", "Personal ohne Kosten")
        page = self.assert_ok(browser.get(self.detail))
        self.assertIn("Tontechnik", page)
        self.assertNotIn("281,00", page)
        self.assertNotIn("Tagessatz", page)
        refused = browser.post(
            reverse("personnel:rate_set", args=[self.anna.pk]), {"job_function": self.sound.pk, "daily_rate": "1"}
        )
        self.assertEqual(refused.status_code, 403)


class OwnRatesPageTests(UiTestCase):
    """PER-010, PER-029: "My job functions" with hourly and day rate, if the person may see them."""

    def setUp(self) -> None:
        super().setUp()
        self.user = make_user("carla", roles=("Crew",))
        self.browser = self.browser_of(self.user)
        self.carla = Person.objects.get(user=self.user)
        services.set_rate(self.carla, job_function("Stagehand"), D("18.00"), daily_rate=D("144.00"))
        services.set_rate(self.carla, job_function("Licht", guide="25.00"))
        self.url = reverse("personnel:own_profile")

    def test_hourly_and_day_rate_or_only_the_functions(self) -> None:
        text = self.assert_ok(self.browser.get(self.url))
        self.assertIn("Mein Tagessatz", text)
        self.assertIn("144,00", text)
        self.assertNotIn("25,00", text)  # a guide value is no own rate and stays hidden
        settings = SystemSettings.load()
        settings.people_see_own_rates = False
        settings.save()
        text = self.assert_ok(self.browser.get(self.url))
        self.assertIn("Stagehand", text)
        self.assertIn("Licht", text)
        self.assertNotIn("144,00", text)
        self.assertNotIn("Mein Tagessatz", text)
        self.assertIn("Stundensätze werden hier nicht angezeigt", text)


class JobFunctionDayGuidePageTests(UiTestCase):
    """PER-029: the guide value per day of a job function, with the cost right only."""

    def test_form_and_list(self) -> None:
        sound = job_function("Tontechnik")
        url = reverse("personnel:job_function_edit", args=[sound.pk])
        page = self.client.get(url)
        self.assertIn('name="guide_daily_cost_rate"', self.assert_ok(page))
        self.client.post(url, form_data(page, containing="name", guide_daily_cost_rate="260,00"))
        sound.refresh_from_db()
        self.assertEqual(sound.guide_daily_cost_rate, D("260.00"))
        listed = self.assert_ok(self.client.get(reverse("personnel:job_function_list")))
        self.assertIn("Richtwert je Tag", listed)
        self.assertIn("260,00", listed)
        Role.objects.create(name="Personal ohne Kosten", module_levels={"personnel": 2})
        browser = self.browser_for("pit", "Personal ohne Kosten")
        self.assertNotIn("guide_daily_cost_rate", self.assert_ok(browser.get(url)))
        self.assertNotIn("260,00", self.assert_ok(browser.get(reverse("personnel:job_function_list"))))


# --- PER-030 ------------------------------------------------------------------------------------------------


class WeekViewPageTests(UiTestCase):
    """PER-030: "Month | Week" on "My area → Availability" and on the tab of a person."""

    def setUp(self) -> None:
        super().setUp()
        self.user = make_user("carla", roles=("Crew",))
        self.browser = self.browser_of(self.user)
        self.carla = Person.objects.get(user=self.user)
        services.set_rate(self.carla, job_function("Stagehand"))
        self.own = reverse("personnel:own_availability")

    def test_the_week_with_bands_deployments_and_heads_to_tap(self) -> None:
        availability_marks.mark_period(self.carla, at(10, 18), at(10, 23), RED, "Probe")
        AvailabilityMark.objects.create(
            person=self.carla, start=at(11, 9), end=at(11, 12), state=RED, source=AvailabilitySource.FEED
        )
        plan(make_project("Stadtfest", start=at(10, 8), end=at(10, 20)), "Stagehand", self.carla)
        text = self.assert_ok(self.browser.get(self.own, {"view": "week", "week": "2027-03-10"}))
        self.assertIn("KW 10", text)
        self.assertIn("08.03. – 14.03.2027", text)
        self.assertEqual(text.count('class="wk-dayhead avail-dayhead'), 7)
        self.assertIn('data-avail-day="2027-03-14"', text)
        self.assertIn('class="wk-band unavailable"', text)
        self.assertIn('class="wk-band unavailable feed"', text)
        self.assertIn("Probe", text)
        self.assertIn("wk-event avail-deploy status-", text)
        self.assertIn(" clash", text)  # the deployment reaches into the red evening
        self.assertIn("Stagehand · ", text)
        self.assertIn("?view=week&amp;week=2027-03-01#availability", text)  # the week before
        self.assertIn("?view=week&amp;week=2027-03-15#availability", text)
        self.assertIn('name="view" value="week"', text)
        self.assertIn("Einträge in dieser Woche", text)

    def test_the_view_is_remembered_and_colouring_comes_back_to_the_week(self) -> None:
        self.assert_ok(self.browser.get(self.own, {"view": "week", "week": "2027-03-17"}))
        text = self.assert_ok(self.browser.get(self.own))  # without anything: the week, as chosen last
        self.assertIn("wk-dayhead avail-dayhead", text)
        page = self.browser.get(self.own, {"week": "2027-03-17"})
        data = form_data(page, containing="start_day", start_day="2027-03-17", state=YELLOW)
        response = self.browser.post(self.own, data, follow=True)
        self.assertEqual(response.redirect_chain[-1][0], "/me/availability/?view=week&week=2027-03-15#availability")
        self.assertTrue(AvailabilityMark.objects.filter(person=self.carla, state=YELLOW).exists())
        text = self.assert_ok(self.browser.get(self.own, {"view": "month", "month": "2027-03"}))
        self.assertIn("avail-grid", text)
        self.assertNotIn("wk-dayhead", text)
        self.assertIn("?view=week&amp;week=2027-03-01#availability", text)  # "Week" opens the first week of March

    def test_personnel_planning_sees_the_week_without_foreign_projects(self) -> None:
        anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        project = make_project("Geheimprojekt", start=at(10, 8), end=at(10, 18))
        plan(project, "Tontechnik", anna)
        tab = reverse("personnel:person_availability", args=[anna.pk])
        dispatcher = self.browser_for("dora", "Personaldisposition")
        text = self.assert_ok(dispatcher.get(tab, {"view": "week", "week": "2027-03-10"}))
        self.assertIn('button type="button" class="wk-dayhead avail-dayhead', text)
        self.assertIn(f"Tontechnik · {project.number} Geheimprojekt", text)  # the dispatcher may open all
        Role.objects.create(name="Personal lesen", module_levels={"personnel": 1})
        reader = self.browser_for("paula", "Personal lesen")  # sees no projects (AUT-016)
        text = self.assert_ok(reader.get(tab, {"view": "week", "week": "2027-03-10"}))
        self.assertIn('<div class="wk-dayhead avail-dayhead', text)  # reading only: nothing to tap
        self.assertNotIn("data-avail-day", text)
        self.assertNotIn("Geheimprojekt", text)
        self.assertIn("Tontechnik · eingeplant", text)


# --- PER-031 ------------------------------------------------------------------------------------------------


class SeveralCalendarsPageTests(UiTestCase):
    """PER-031: a list of linked calendars on both pages; the addresses only for the person."""

    def setUp(self) -> None:
        super().setUp()
        self.server = serve(self)
        self.server.files["/private.ics"] = (200, {"Content-Type": "text/calendar"}, FEED)
        self.server.files["/band.ics"] = (200, {"Content-Type": "text/calendar"}, BAND)
        self.user = make_user("carla", roles=("Crew",))
        self.browser = self.browser_of(self.user)
        self.carla = Person.objects.get(user=self.user)

    def test_the_person_links_two_calendars_and_removes_one(self) -> None:
        own = reverse("personnel:own_feed")
        self.browser.post(own, {"url": f"{self.server.url}/private.ics"})
        response = self.browser.post(own, {"url": f"{self.server.url}/band.ics", "label": "Band"}, follow=True)
        self.assertIn("Der Kalender ist verknüpft.", self.messages_of(response))
        text = self.assert_ok(response)
        self.assertIn("Belegte Zeiten aus deinen Kalendern", text)
        self.assertIn(f"{self.server.url}/band.ics", text)  # the person sees the own addresses
        self.assertIn(">Band<", text)
        self.assertEqual(text.count('class="feed-row"'), 2)
        self.assertIn("Weiteren Kalender verknüpfen", text)
        busy = AvailabilityMark.objects.filter(person=self.carla, source=AvailabilitySource.FEED)
        self.assertEqual(busy.count(), 7)
        response = self.browser.post(reverse("personnel:own_calendar_sync"), {"what": "feed"}, follow=True)
        self.assertIn("Der Kalender wurde gelesen.", self.messages_of(response))
        band = self.carla.calendar_feeds.get(label="Band")
        self.browser.post(reverse("personnel:own_feed_remove", args=[band.pk]))
        self.assertEqual(busy.count(), 6)
        self.assertEqual(self.carla.calendar_feeds.count(), 1)
        # Somebody else's calendar cannot be removed.
        other = calendars.add_feed(make_person("Tom Richter"), f"{self.server.url}/band.ics")
        self.assertEqual(self.browser.post(reverse("personnel:own_feed_remove", args=[other.pk])).status_code, 404)

    def test_a_failing_calendar_is_named_when_reading_now(self) -> None:
        calendars.add_feed(self.carla, f"{self.server.url}/private.ics")
        calendars.add_feed(self.carla, f"{self.server.url}/gone.ics", "Verein")
        response = self.browser.post(reverse("personnel:own_calendar_sync"), {"what": "feed"}, follow=True)
        (message,) = self.messages_of(response)
        self.assertTrue(message.startswith("Verein: "))
        text = self.assert_ok(response)
        self.assertIn("Problem", text)
        self.assertIn("zuletzt gelesen", text)

    def test_personnel_planning_links_and_removes_without_seeing_the_addresses(self) -> None:
        tab = reverse("personnel:person_availability", args=[self.carla.pk])
        dispatcher = self.browser_for("dora", "Personaldisposition")
        add = reverse("personnel:person_feed", args=[self.carla.pk])
        dispatcher.post(add, {"url": f"{self.server.url}/private.ics?token=very-secret"})
        response = dispatcher.post(add, {"url": f"{self.server.url}/band.ics", "label": "Band"}, follow=True)
        text = self.assert_ok(response)
        self.assertNotIn("very-secret", text)
        self.assertNotIn("/band.ics", text)
        self.assertIn("verknüpft, von 127.0.0.1", text)
        self.assertIn('Band <span class="muted small">von 127.0.0.1</span>', text)
        band = self.carla.calendar_feeds.get(label="Band")
        remove = reverse("personnel:person_feed_remove", args=[self.carla.pk, band.pk])
        reader = self.browser_for("paula", "Projektleitung")
        self.assertNotIn(remove, self.assert_ok(reader.get(tab)))
        self.assertEqual(reader.post(remove).status_code, 403)
        dispatcher.post(remove)
        self.assertEqual(self.carla.calendar_feeds.count(), 1)


# --- The timeline of a person ---------------------------------------------------------------------------------


class TimelineAvailabilityPageTests(UiTestCase):
    """PER-020 with PER-027: the timeline shows the availability with its legend (bug)."""

    def test_the_row_and_the_legend(self) -> None:
        anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        availability_marks.mark_period(anna, at(2), at(3), RED, "Familienfeier")
        page = self.assert_ok(
            self.client.get(reverse("personnel:person_timeline", args=[anna.pk]), {"from": "2027-03-01"})
        )
        self.assertIn('tl-label availability">Verfügbarkeit', page)
        self.assertIn('class="tl-bar availability is-unavailable"', page)
        self.assertIn("Familienfeier", page)
        self.assertIn("tl-bar legend availability is-available", page)
        self.assertIn("belegt im verknüpften Kalender", page)
