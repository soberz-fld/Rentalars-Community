# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages of the availability calendar and the calendar links (PER-021, PER-022, PER-023).

* "My area → Availability" (``/me/availability/``): colour the
  own availability, link a calendar with busy times, download and subscribe
  to the own deployments, write them into a CalDAV calendar – without any
  right on the personnel module.
* The tab "Availability" of a person for personnel planning.
* The subscription link without login (``/calendar-feed/``).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import icalendar
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

from rentalars.personnel import calendars, services
from rentalars.personnel import marks as availability_marks
from rentalars.personnel.models import AvailabilityMark, AvailabilitySource, AvailabilityState, Person
from tests.helpers import at, job_function, make_person, make_project, make_user, plan
from tests.ui.base import UiTestCase, form_data
from tests.unit.test_051_personnel_calendars import FEED, serve

RED, YELLOW = AvailabilityState.UNAVAILABLE, AvailabilityState.LIMITED


class OwnAvailabilityPageTests(UiTestCase):
    """PER-021: a person colours the own availability on "My area → Availability"."""

    def setUp(self) -> None:
        super().setUp()
        self.user = make_user("carla", roles=("Crew",))
        self.browser = self.browser_of(self.user)
        self.carla = Person.objects.get(user=self.user)

    def colour(self, **values: str) -> object:
        page = self.browser.get(reverse("personnel:own_availability"))
        data = form_data(page, containing="start_day", **values)
        return self.browser.post(reverse("personnel:own_availability"), data, follow=True)

    def test_the_tab_availability_shows_the_calendar_and_the_links(self) -> None:
        text = self.assert_ok(self.browser.get(reverse("personnel:own_availability")))
        self.assertIn("data-avail-calendar", text)
        self.assertIn('data-avail-day="2027-03-10"', text)
        self.assertIn("Meine Verfügbarkeit", text)
        self.assertIn("März 2027", text)
        self.assertIn(reverse("personnel:own_feed"), text)
        self.assertIn(reverse("personnel:own_caldav"), text)
        self.assertIn(reverse("personnel:own_deployments_ics"), text)

    def test_colour_days(self) -> None:
        response = self.colour(start_day="2027-03-10", end_day="2027-03-12", state=RED, note="Messe in Köln")
        text = self.assert_ok(response)
        self.assertEqual(response.redirect_chain[-1][0], "/me/availability/?month=2027-03#availability")
        self.assertIn("Verfügbarkeit gespeichert.", self.messages_of(response))
        (mark,) = AvailabilityMark.objects.filter(person=self.carla)
        self.assertEqual((mark.start, mark.end, mark.state, mark.note), (at(10), at(13), RED, "Messe in Köln"))
        self.assertIn("avail-day unavailable", text)
        self.assertIn("Messe in Köln", text)

    def test_one_day_and_times_on_each_day(self) -> None:
        self.colour(start_day="2027-03-20", state=YELLOW)
        self.assertEqual(AvailabilityMark.objects.get(person=self.carla).end, at(21))
        self.colour(
            start_day="2027-03-10", end_day="2027-03-12", with_times="on", start_time="18:00", end_time="23:00",
            state=RED,
        )  # fmt: skip
        evenings = AvailabilityMark.objects.filter(person=self.carla, state=RED).order_by("start")
        self.assertEqual(
            [(mark.start, mark.end) for mark in evenings], [(at(day, 18), at(day, 23)) for day in (10, 11, 12)]
        )

    def test_clear_and_remove(self) -> None:
        self.colour(start_day="2027-03-10", end_day="2027-03-20", state=YELLOW)
        response = self.colour(start_day="2027-03-12", end_day="2027-03-13", state="clear")
        self.assertIn("Einträge entfernt.", self.messages_of(response))
        self.assertEqual(AvailabilityMark.objects.filter(person=self.carla).count(), 2)
        # "remove" in the list removes what was entered in the period of its row.
        page = self.browser.get(reverse("personnel:own_availability"), {"month": "2027-03"})
        data = form_data(page, containing="start")
        self.assertEqual((data["start"], data["end"]), (at(10).isoformat(), at(12).isoformat()))
        self.browser.post(reverse("personnel:own_availability_remove"), data)
        self.assertEqual(AvailabilityMark.objects.filter(person=self.carla).count(), 1)

    def test_wrong_input_is_told(self) -> None:
        response = self.colour(start_day="2027-03-12", end_day="2027-03-10", state=RED)
        self.assertTrue(self.messages_of(response))
        response = self.colour(start_day="2027-03-12", with_times="on", start_time="18:00", end_time="", state=RED)
        self.assertIn("Gib beide Uhrzeiten an oder keine für ganze Tage.", " ".join(self.messages_of(response)))
        self.assertFalse(AvailabilityMark.objects.filter(person=self.carla).exists())

    def test_months_can_be_browsed(self) -> None:
        text = self.assert_ok(self.browser.get(reverse("personnel:own_availability"), {"month": "2027-11"}))
        self.assertIn("November 2027", text)
        self.assertIn('data-avail-day="2027-11-30"', text)
        self.assertIn("?month=2027-12#availability", text)

    def test_only_own_entries_can_be_removed(self) -> None:
        other = make_person("Tom Richter")
        mark = availability_marks.mark_period(other, at(10), at(11), RED)
        busy = AvailabilityMark.objects.create(
            person=self.carla, start=at(10), end=at(11), state=RED, source=AvailabilitySource.FEED
        )
        period = {"start": at(10).isoformat(), "end": at(11).isoformat(), "month": "2027-03"}
        self.browser.post(reverse("personnel:own_availability_remove"), period)
        self.assertTrue(AvailabilityMark.objects.filter(pk=mark.pk).exists())
        self.assertTrue(AvailabilityMark.objects.filter(pk=busy.pk).exists())
        # A busy time has no "remove" in the list.
        text = self.assert_ok(self.browser.get(reverse("personnel:own_availability"), {"month": "2027-03"}))
        self.assertNotIn(reverse("personnel:own_availability_remove"), text)

    def test_deployments_show_in_the_calendar(self) -> None:
        services.set_rate(self.carla, job_function("Stagehand"), Decimal("18.00"), datetime.date(2027, 1, 1))
        plan(make_project("Stadtfest"), "Stagehand", self.carla)
        text = self.assert_ok(self.browser.get(reverse("personnel:own_availability")))
        self.assertIn("planned-dot", text)


class OwnCalendarLinksTests(UiTestCase):
    """PER-022, PER-023: linking a calendar, the subscription link, the download, CalDAV."""

    def setUp(self) -> None:
        super().setUp()
        cache.clear()
        self.server = serve(self)
        self.server.files["/carla.ics"] = (200, {"Content-Type": "text/calendar"}, FEED)
        self.user = make_user("carla", roles=("Crew",))
        self.browser = self.browser_of(self.user)
        self.carla = Person.objects.get(user=self.user)
        self.carla.first_name, self.carla.last_name = "Carla", "Weber"
        self.carla.save()
        services.set_rate(self.carla, job_function("Stagehand"), Decimal("18.00"), datetime.date(2027, 1, 1))
        self.project = make_project("Stadtfest", venue="Marktplatz")
        plan(self.project, "Stagehand", self.carla, meeting_point="Bühneneingang")

    def test_link_a_calendar_and_read_it_at_once(self) -> None:
        # One of possibly several linked calendars (PER-031).
        response = self.browser.post(
            reverse("personnel:own_feed"), {"url": f"{self.server.url}/carla.ics"}, follow=True
        )
        self.assertIn("Der Kalender ist verknüpft.", self.messages_of(response))
        self.assertEqual(AvailabilityMark.objects.filter(person=self.carla, source=AvailabilitySource.FEED).count(), 6)
        text = self.assert_ok(response)
        self.assertIn("zuletzt gelesen", text)
        self.assertIn(f"{self.server.url}/carla.ics", text)  # the person sees the own link
        response = self.browser.post(reverse("personnel:own_calendar_sync"), {"what": "feed"}, follow=True)
        self.assertIn("Der Kalender wurde gelesen.", self.messages_of(response))
        feed = self.carla.calendar_feeds.get()
        self.browser.post(reverse("personnel:own_feed_remove", args=[feed.pk]), follow=True)
        self.assertFalse(AvailabilityMark.objects.filter(person=self.carla).exists())

    def test_a_broken_link_shows_the_problem(self) -> None:
        response = self.browser.post(
            reverse("personnel:own_feed"), {"url": f"{self.server.url}/nothing.ics"}, follow=True
        )
        (message,) = self.messages_of(response)
        self.assertIn("abgelehnt", message)
        self.assertIn("Problem", self.assert_ok(response))
        response = self.browser.post(reverse("personnel:own_feed"), {"url": "ftp://x.example/a.ics"}, follow=True)
        self.assertIn("https://", " ".join(self.messages_of(response)))

    def test_the_subscription_link(self) -> None:
        response = self.browser.post(reverse("personnel:own_subscription"), follow=True)
        self.assertIn("Der Abo-Link ist erzeugt.", self.messages_of(response))
        self.carla.refresh_from_db()
        path = calendars.subscription_path(self.carla)
        self.assertIn(path, self.assert_ok(response))
        anonymous = Client()
        answer = anonymous.get(path)
        self.assertEqual(answer.status_code, 200)
        self.assertTrue(answer["Content-Type"].startswith("text/calendar"))
        (event,) = icalendar.Calendar.from_ical(answer.content).walk("VEVENT")
        self.assertTrue(str(event["SUMMARY"]).startswith("Stagehand – "))
        self.assertEqual(str(event["LOCATION"]), "Marktplatz")
        self.assertIn("Treffpunkt: Bühneneingang", str(event["DESCRIPTION"]))
        self.assertEqual(anonymous.get(path, HTTP_IF_NONE_MATCH=answer["ETag"]).status_code, 304)
        self.browser.post(reverse("personnel:own_subscription"))
        self.assertEqual(anonymous.get(path).status_code, 404)
        self.carla.refresh_from_db()
        renewed = calendars.subscription_path(self.carla)
        self.assertEqual(anonymous.get(renewed).status_code, 200)
        self.browser.post(reverse("personnel:own_subscription"), {"remove": "1"})
        self.assertEqual(anonymous.get(renewed).status_code, 404)

    def test_guessing_and_hammering_wait(self) -> None:
        token = calendars.renew_calendar_token(self.carla)
        anonymous = Client()
        for attempt in range(25):
            answer = anonymous.get(f"/calendar-feed/{self.carla.pk}/wrong{attempt}.ics")
        self.assertEqual(answer.status_code, 429)
        self.assertEqual(anonymous.get(f"/calendar-feed/{self.carla.pk}/{token}.ics").status_code, 429)
        cache.clear()
        statuses = {anonymous.get(f"/calendar-feed/{self.carla.pk}/{token}.ics").status_code for _ in range(61)}
        self.assertEqual(statuses, {200, 429})

    def test_without_login_only_the_subscription_link(self) -> None:
        anonymous = Client()
        self.assertEqual(anonymous.get("/me/").status_code, 302)
        self.assertEqual(anonymous.get(reverse("personnel:own_deployments_ics")).status_code, 302)
        self.assertEqual(anonymous.get(f"/calendar-feed/{self.carla.pk}/nothing.ics").status_code, 404)

    def test_download(self) -> None:
        response = self.browser.get(reverse("personnel:own_deployments_ics"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(b"BEGIN:VEVENT", response.content)

    def test_set_up_a_caldav_calendar(self) -> None:
        url = reverse("personnel:own_caldav")
        self.server.credentials = ("anna", "Kw-81x!q")
        response = self.browser.post(url, {"caldav_url": f"{self.server.url}/", "caldav_username": "anna"}, follow=True)
        self.assertIn("Gib das Passwort für den Kalender an.", self.messages_of(response))
        response = self.browser.post(
            url,
            {"caldav_url": f"{self.server.url}/", "caldav_username": "anna", "caldav_password": "Kw-81x!q"},
            follow=True,
        )
        self.assertIn("Gespeichert. Deine Einsätze werden in den Kalender geschrieben.", self.messages_of(response))
        text = self.assert_ok(response)
        self.assertNotIn("Kw-81x!q", text)
        self.assertIn("Ein Passwort ist gespeichert.", text)
        self.assertEqual(len(self.server.events), 1)
        self.carla.refresh_from_db()
        self.assertIn("/cal/anna/rentalars-", self.carla.caldav_url)
        # Changing the username keeps the stored password.
        response = self.browser.post(
            url, {"caldav_url": self.carla.caldav_url, "caldav_username": "anna", "caldav_password": ""}, follow=True
        )
        self.carla.refresh_from_db()
        self.assertTrue(self.carla.caldav_password_encrypted)
        response = self.browser.post(reverse("personnel:own_calendar_sync"), {"what": "caldav"}, follow=True)
        self.assertIn("Kalender abgeglichen: 0 geschrieben, 0 entfernt.", self.messages_of(response))
        response = self.browser.post(url, {"remove": "1", "caldav_url": self.carla.caldav_url}, follow=True)
        self.assertIn("Rentalars schreibt in keinen Kalender mehr.", self.messages_of(response))
        self.carla.refresh_from_db()
        self.assertEqual((self.carla.caldav_url, self.carla.caldav_password_encrypted), ("", ""))

    def test_a_refused_login_shows_at_once(self) -> None:
        response = self.browser.post(
            reverse("personnel:own_caldav"),
            {"caldav_url": f"{self.server.url}/", "caldav_username": "anna", "caldav_password": "falsch"},
            follow=True,
        )
        self.assertIn("Anmeldung abgelehnt", " ".join(self.messages_of(response)))
        self.assertIn("Problem", self.assert_ok(response))


class PlannerAvailabilityTabTests(UiTestCase):
    """PER-021, PER-022 for personnel planning: the tab "Availability" of a person."""

    def setUp(self) -> None:
        super().setUp()
        self.server = serve(self)
        self.server.files["/anna.ics"] = (200, {}, FEED)
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        self.tab = reverse("personnel:person_availability", args=[self.anna.pk])
        self.dispatcher = self.browser_for("dora", "Personaldisposition")
        self.reader = self.browser_for("paula", "Projektleitung")

    def test_readers_see_writers_change(self) -> None:
        availability_marks.mark_period(self.anna, at(10), at(11), RED, "Familienfeier")
        text = self.assert_ok(self.reader.get(self.tab))
        self.assertIn("Familienfeier", text)
        self.assertNotIn('name="start_day"', text)
        self.assertEqual(
            self.reader.post(reverse("personnel:person_availability_mark", args=[self.anna.pk])).status_code, 403
        )
        text = self.assert_ok(self.dispatcher.get(self.tab))
        self.assertIn('name="start_day"', text)
        data = form_data(self.dispatcher.get(self.tab), containing="start_day", start_day="2027-03-20", state=YELLOW)
        self.dispatcher.post(reverse("personnel:person_availability_mark", args=[self.anna.pk]), data)
        self.assertTrue(AvailabilityMark.objects.filter(person=self.anna, state=YELLOW).exists())
        mark = AvailabilityMark.objects.get(person=self.anna, state=RED)
        period = {"start": mark.start.isoformat(), "end": mark.end.isoformat()}
        self.dispatcher.post(reverse("personnel:person_availability_remove", args=[self.anna.pk]), period)
        self.assertFalse(AvailabilityMark.objects.filter(pk=mark.pk).exists())

    def test_crew_does_not_see_others(self) -> None:
        crew_browser = self.browser_for("carla", "Crew")
        self.assertEqual(crew_browser.get(self.tab).status_code, 403)

    def test_the_tab_is_on_the_person_page(self) -> None:
        text = self.assert_ok(self.reader.get(reverse("personnel:person_detail", args=[self.anna.pk])))
        self.assertIn(self.tab, text)

    def test_the_link_stays_hidden(self) -> None:
        calendars.add_feed(self.anna, "https://calendar.example.org/private/very-secret-token/basic.ics")
        text = self.assert_ok(self.dispatcher.get(self.tab))
        self.assertIn("calendar.example.org", text)
        self.assertNotIn("very-secret-token", text)

    def test_link_read_and_remove_for_the_person(self) -> None:
        url = reverse("personnel:person_feed", args=[self.anna.pk])
        response = self.dispatcher.post(url, {"url": f"{self.server.url}/anna.ics"}, follow=True)
        self.assertIn("Der Kalender ist verknüpft.", self.messages_of(response))
        self.assertEqual(AvailabilityMark.objects.filter(person=self.anna, source=AvailabilitySource.FEED).count(), 6)
        response = self.dispatcher.post(url, {"url": ""}, follow=True)
        self.assertIn("Gib die Adresse des Kalenders an.", self.messages_of(response))
        self.assertEqual(self.anna.calendar_feeds.count(), 1)
        response = self.dispatcher.post(url, {"read": "1"}, follow=True)
        self.assertIn("Der Kalender wurde gelesen.", self.messages_of(response))
        # Each linked calendar is removed on its own (PER-031).
        feed = self.anna.calendar_feeds.get()
        self.dispatcher.post(reverse("personnel:person_feed_remove", args=[self.anna.pk, feed.pk]))
        self.assertFalse(self.anna.calendar_feeds.exists())
        self.assertEqual(self.reader.post(url, {"read": "1"}).status_code, 403)

    def test_the_planning_and_the_overview_tell(self) -> None:
        project = make_project("Stadtfest")
        plan(project, "Tontechnik", self.anna)
        availability_marks.mark_period(self.anna, at(11), at(12), RED, "Familienfeier")
        tom = make_person("Tom Richter", rates={"Tontechnik": "30.00"})
        availability_marks.mark_period(tom, at(10, 14), at(10, 20), YELLOW, "ab 14 Uhr")
        text = self.assert_ok(self.client.get(reverse("projects:detail", args=[project.pk])))
        self.assertIn("Laut eigener Angabe nicht verfügbar: 11.03. (Familienfeier).", text)
        text = self.assert_ok(
            self.client.get(reverse("personnel:availability"), {"start": "2027-03-10T09:00", "end": "2027-03-11T18:00"})
        )
        self.assertIn("Nicht verfügbar (eigene Angabe)", text)
        self.assertIn("ab 14 Uhr", text)
