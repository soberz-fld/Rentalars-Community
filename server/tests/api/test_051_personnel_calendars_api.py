# SPDX-License-Identifier: GPL-3.0-or-later
"""API of availability and calendars (PER-021, PER-022, PER-023).

Below ``/people/{id}``, where ``{id}`` may be ``me``:

* ``availability-marks`` – list, colour, change, remove, clear (PER-021);
* ``calendars`` – linked calendar (PER-022), CalDAV and subscription link (PER-023);
* ``calendars/sync`` and ``calendars/deployments``.

The person needs no right on the personnel module for their own data;
personnel planning reads with read access and changes with write access,
but never sees the secret links or touches the CalDAV settings.
"""

from __future__ import annotations

from rentalars.core.crypto import decrypt_secret
from rentalars.personnel import calendars
from rentalars.personnel import marks as availability_marks
from rentalars.personnel.models import AvailabilityMark, AvailabilitySource, AvailabilityState, Person
from tests.api.base import API, ApiTestCase
from tests.helpers import at, make_person, make_user
from tests.unit.test_051_personnel_calendars import FEED, serve

RED, YELLOW, GREEN = AvailabilityState.UNAVAILABLE, AvailabilityState.LIMITED, AvailabilityState.AVAILABLE


class OwnAvailabilityApiTests(ApiTestCase):
    """PER-021: a person colours the own availability through the API, without personnel rights."""

    def setUp(self) -> None:
        super().setUp()
        self.user = make_user("carla", roles=("Crew",))
        self.carla = Person.objects.get(user=self.user)
        self.client_ = self.client_of(self.user)
        self.marks = f"{API}/people/me/availability-marks"

    def test_colour_list_change_and_remove(self) -> None:
        response = self.client_.post(
            self.marks,
            {"start": at(10).isoformat(), "end": at(13).isoformat(), "state": RED, "note": "Messe"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        mark = response.json()
        self.assertEqual(
            (mark["state"], mark["note"], mark["source"], mark["person"]), (RED, "Messe", "own", self.carla.pk)
        )
        listed = self.client_.get(self.marks).json()
        self.assertEqual([item["id"] for item in listed], [mark["id"]])
        changed = self.client_.patch(f"{self.marks}/{mark['id']}", {"state": YELLOW}, format="json")
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual((changed.json()["state"], changed.json()["note"]), (YELLOW, "Messe"))
        new_id = changed.json()["id"]
        self.assertEqual(self.client_.delete(f"{self.marks}/{new_id}").status_code, 204)
        self.assertEqual(self.client_.get(self.marks).json(), [])

    def test_colouring_replaces_and_clearing_cuts(self) -> None:
        self.client_.post(
            self.marks, {"start": at(10).isoformat(), "end": at(20).isoformat(), "state": RED}, format="json"
        )
        self.client_.post(
            self.marks, {"start": at(12).isoformat(), "end": at(14).isoformat(), "state": GREEN}, format="json"
        )
        states = [item["state"] for item in self.client_.get(self.marks).json()]
        self.assertEqual(states, [RED, GREEN, RED])
        response = self.client_.post(
            f"{self.marks}/clear", {"start": at(11).isoformat(), "end": at(19).isoformat()}, format="json"
        )
        self.assertEqual(response.json(), {"changed": 3})
        periods = [(item["start"], item["end"]) for item in self.client_.get(self.marks).json()]
        self.assertEqual(len(periods), 2)

    def test_the_own_id_works_like_me(self) -> None:
        availability_marks.mark_period(self.carla, at(10), at(11), RED)
        response = self.client_.get(f"{API}/people/{self.carla.pk}/availability-marks")
        self.assertEqual(len(response.json()), 1)

    def test_a_period_can_be_asked_for(self) -> None:
        availability_marks.mark_period(self.carla, at(10), at(11), RED)
        availability_marks.mark_period(self.carla, at(20), at(21), GREEN)
        response = self.client_.get(self.marks, {"from": "2027-03-15", "to": "2027-03-31"})
        self.assertEqual([item["state"] for item in response.json()], [GREEN])
        self.assert_error(
            self.client_.get(self.marks, {"from": "2027-03-15", "to": "2027-03-01"}), 400, "validation_error"
        )

    def test_wrong_input(self) -> None:
        response = self.client_.post(
            self.marks, {"start": at(13).isoformat(), "end": at(10).isoformat(), "state": RED}, format="json"
        )
        self.assert_error(response, 400, "validation_error", "end")
        response = self.client_.post(
            self.marks, {"start": at(10).isoformat(), "end": at(13).isoformat(), "state": "purple"}, format="json"
        )
        self.assert_error(response, 400, "validation_error", "state")

    def test_busy_times_of_the_linked_calendar_stay(self) -> None:
        busy = AvailabilityMark.objects.create(
            person=self.carla, start=at(10), end=at(11), state=RED, source=AvailabilitySource.FEED
        )
        self.assert_error(
            self.client_.patch(f"{self.marks}/{busy.pk}", {"state": GREEN}, format="json"), 400, "validation_error"
        )
        self.assert_error(self.client_.delete(f"{self.marks}/{busy.pk}"), 400, "validation_error")

    def test_a_read_only_token_changes_nothing(self) -> None:
        reader = self.client_of(self.user, read_only=True)
        self.assertEqual(reader.get(self.marks).status_code, 200)
        response = reader.post(
            self.marks, {"start": at(10).isoformat(), "end": at(11).isoformat(), "state": RED}, format="json"
        )
        self.assert_error(response, 403, "permission_denied")
        self.assert_error(reader.post(f"{API}/people/me/calendars/subscription"), 403, "permission_denied")

    def test_without_login_nothing(self) -> None:
        from rest_framework.test import APIClient

        self.assertEqual(APIClient().get(self.marks).status_code, 401)


class OthersAvailabilityApiTests(ApiTestCase):
    """PER-021: personnel planning reads with read access and colours with write access."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        availability_marks.mark_period(self.anna, at(10), at(11), RED, "Familienfeier")
        self.marks = f"{API}/people/{self.anna.pk}/availability-marks"

    def test_who_may_do_what(self) -> None:
        crew = self.client_for("carla", "Crew")
        self.assert_error(crew.get(self.marks), 403, "permission_denied")
        reader = self.client_for("paula", "Projektleitung")
        self.assertEqual(reader.get(self.marks).json()[0]["note"], "Familienfeier")
        payload = {"start": at(20).isoformat(), "end": at(21).isoformat(), "state": YELLOW}
        self.assert_error(reader.post(self.marks, payload, format="json"), 403, "permission_denied")
        dispatcher = self.client_for("dora", "Personaldisposition")
        created = dispatcher.post(self.marks, payload, format="json")
        self.assertEqual(created.status_code, 201)
        self.assertEqual(dispatcher.delete(f"{self.marks}/{created.json()['id']}").status_code, 204)
        self.assert_error(dispatcher.get(f"{API}/people/999999/availability-marks"), 404, "not_found")

    def test_the_overview_tells_what_people_said(self) -> None:
        """VFG-009 with PER-021: red counts as absent; the marks come along."""
        tom = make_person("Tom Richter", rates={"Tontechnik": "30.00"})
        availability_marks.mark_period(tom, at(10), at(11), YELLOW, "ab 14 Uhr")
        rows = self.admin.get(
            f"{API}/people/availability", {"from": "2027-03-10T09:00", "to": "2027-03-10T18:00"}
        ).json()
        by_name = {row["name"]: row for row in rows}
        self.assertEqual(by_name["Anna Becker"]["status"], "absent")
        self.assertEqual(by_name["Anna Becker"]["availability_marks"][0]["note"], "Familienfeier")
        self.assertEqual(by_name["Tom Richter"]["status"], "free")
        self.assertEqual(by_name["Tom Richter"]["availability_marks"][0]["state"], YELLOW)


class CalendarSettingsApiTests(ApiTestCase):
    """PER-022, PER-023: the calendar links through the API."""

    def setUp(self) -> None:
        super().setUp()
        self.server = serve(self)
        self.server.files["/carla.ics"] = (200, {}, FEED)
        self.user = make_user("carla", roles=("Crew",))
        self.carla = Person.objects.get(user=self.user)
        self.carla.first_name, self.carla.last_name = "Carla", "Weber"
        self.carla.save()
        self.client_ = self.client_of(self.user)
        self.settings = f"{API}/people/me/calendars"

    def test_link_a_calendar_and_read_it_now(self) -> None:
        # Linked calendars are a list of their own (PER-031).
        response = self.client_.post(f"{self.settings}/feeds", {"url": f"{self.server.url}/carla.ics"}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["url"], f"{self.server.url}/carla.ics")
        self.assertEqual(response.json()["host"], "127.0.0.1")
        result = self.client_.post(f"{self.settings}/sync", {"what": "feed"}, format="json").json()
        self.assertEqual((result["feed"], result["caldav"]), ("read", None))
        self.assertEqual(AvailabilityMark.objects.filter(person=self.carla, source=AvailabilitySource.FEED).count(), 6)
        busy = self.client_.get(f"{API}/people/me/availability-marks").json()
        self.assertTrue(all(item["source"] == "feed" and item["note"] == "" for item in busy))
        self.server.files.pop("/carla.ics")
        result = self.client_.post(f"{self.settings}/sync", format="json").json()
        self.assertEqual(result["feed"], "failed")
        self.assertTrue(self.client_.get(self.settings).json()["feeds"][0]["error"])
        self.assert_error(
            self.client_.post(f"{self.settings}/feeds", {"url": "javascript:alert(1)"}, format="json"),
            400,
            "validation_error",
            "url",
        )

    def test_caldav_with_a_password_that_is_never_delivered(self) -> None:
        response = self.client_.patch(self.settings, {"caldav_url": f"{self.server.url}/"}, format="json")
        self.assert_error(response, 400, "validation_error", "caldav_password")
        response = self.client_.patch(
            self.settings,
            {"caldav_url": f"{self.server.url}/", "caldav_username": "anna", "caldav_password": "geheim"},
            format="json",
        )
        document = response.json()
        self.assertTrue(document["caldav_password_set"])
        self.assertNotIn("caldav_password", document)
        self.assertNotIn("geheim", response.content.decode())
        self.carla.refresh_from_db()
        self.assertEqual(decrypt_secret(self.carla.caldav_password_encrypted), "geheim")
        result = self.client_.post(f"{self.settings}/sync", {"what": "caldav"}, format="json").json()
        self.assertEqual(result["caldav"], {"written": 0, "deleted": 0, "unchanged": 0, "error": ""})
        self.assertIn("/cal/anna/rentalars-", self.client_.get(self.settings).json()["caldav_url"])

    def test_subscription_link_and_download(self) -> None:
        document = self.client_.post(f"{self.settings}/subscription").json()
        self.assertIn(f"/calendar-feed/{self.carla.pk}/", document["subscription_url"])
        self.assertEqual(self.client_.delete(f"{self.settings}/subscription").status_code, 204)
        self.assertEqual(self.client_.get(self.settings).json()["subscription_url"], "")
        response = self.client_.get(f"{self.settings}/deployments")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/calendar"))
        self.assertIn(b"BEGIN:VCALENDAR", response.content)

    def test_personnel_planning_never_sees_the_secrets(self) -> None:
        feed = calendars.add_feed(self.carla, f"{self.server.url}/carla.ics")
        calendars.set_caldav(self.carla, url="https://cloud.example.org/dav/", username="carla", password="geheim")
        calendars.renew_calendar_token(self.carla)
        settings = f"{API}/people/{self.carla.pk}/calendars"
        dispatcher = self.client_for("dora", "Personaldisposition")
        document = dispatcher.get(settings).json()
        self.assertEqual(document["feeds"][0]["host"], "127.0.0.1")
        self.assertNotIn("url", document["feeds"][0])
        for secret in ("caldav_url", "caldav_username", "subscription_url"):
            self.assertNotIn(secret, document)
        self.assertEqual(dispatcher.post(f"{settings}/sync", format="json").json()["feed"], "read")
        self.assert_error(
            dispatcher.post(f"{settings}/sync", {"what": "caldav"}, format="json"), 403, "permission_denied"
        )
        self.assert_error(
            dispatcher.patch(settings, {"caldav_url": "https://evil.example.org/"}, format="json"),
            403,
            "permission_denied",
        )
        self.assert_error(dispatcher.post(f"{settings}/subscription"), 403, "permission_denied")
        self.assert_error(dispatcher.get(f"{settings}/deployments"), 403, "permission_denied")
        reader = self.client_for("paula", "Projektleitung")
        self.assertEqual(reader.get(settings).status_code, 200)
        self.assert_error(reader.delete(f"{settings}/feeds/{feed.pk}"), 403, "permission_denied")
        self.assertEqual(dispatcher.delete(f"{settings}/feeds/{feed.pk}").status_code, 204)
        self.assertFalse(self.carla.calendar_feeds.exists())
        self.assert_error(self.client_for("tim", "Crew").get(settings), 403, "permission_denied")
