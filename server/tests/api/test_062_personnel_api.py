# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the requirements from the use for people.

* ``/people/{id}/job-functions`` without rate and day, with ``daily_rate``; ``guide_daily_cost_rate`` of the
  job functions (PER-029).
* ``/people/{id}/calendars/feeds`` – list, link and remove linked calendars (PER-031).
* ``/people/{id}/timeline`` with the availability (bug, PER-020).
"""

from __future__ import annotations

from decimal import Decimal

from rentalars.accounts.models import Role
from rentalars.personnel import calendars, services
from rentalars.personnel import marks as availability_marks
from rentalars.personnel.models import AvailabilityMark, AvailabilitySource, AvailabilityState, Person
from tests.api.base import API, ApiTestCase
from tests.helpers import at, job_function, make_person, make_user
from tests.unit.test_051_personnel_calendars import FEED, serve
from tests.unit.test_062_personnel import BAND

D = Decimal


class OptionalRatesApiTests(ApiTestCase):
    """PER-029: rates and day are optional; day rates next to hourly rates."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_person("Anna Becker")
        self.address = f"{API}/people/{self.anna.pk}/job-functions"
        self.sound = job_function("Tontechnik", guide="30.00")

    def test_without_the_cost_right_only_the_function(self) -> None:
        Role.objects.create(name="Personal ohne Kosten", module_levels={"personnel": 2})
        client = self.client_for("pit", "Personal ohne Kosten")
        services.set_rate(self.anna, self.sound, D("35.00"))
        hand = job_function("Stagehand")
        self.assertEqual(
            client.post(self.address, {"job_function": hand.pk, "hourly_rate": "1.00"}, format="json").status_code,
            403,
        )
        rows = client.post(self.address, {"job_function": hand.pk}, format="json").json()
        self.assertEqual(
            rows,
            [{"job_function": hand.pk, "name": "Stagehand"}, {"job_function": self.sound.pk, "name": "Tontechnik"}],
        )
        client.post(self.address, {"job_function": self.sound.pk}, format="json")
        self.assertEqual(services.rate_on(self.anna, self.sound), D("35.00"))  # untouched
        self.assertEqual(client.delete(f"{self.address}/{self.sound.pk}").status_code, 403)
        self.assertEqual(client.delete(f"{self.address}/{hand.pk}").status_code, 204)

    def test_assign_without_rate_then_rates_from_a_day_on(self) -> None:
        response = self.admin.post(self.address, {"job_function": self.sound.pk}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.json(),
            [
                {
                    "job_function": self.sound.pk,
                    "name": "Tontechnik",
                    "hourly_rate": None,
                    "daily_rate": None,
                    "hourly_rate_above_limit": None,  # PER-035
                    "valid_from": None,
                    "history": [
                        {"hourly_rate": None, "daily_rate": None, "hourly_rate_above_limit": None, "valid_from": None}
                    ],
                }
            ],
        )
        later = self.admin.post(
            self.address,
            {"job_function": self.sound.pk, "hourly_rate": None, "daily_rate": "280.00", "valid_from": "2027-02-01"},
            format="json",
        ).json()[0]
        self.assertEqual(
            (later["hourly_rate"], later["daily_rate"], later["valid_from"]), (None, "280.00", "2027-02-01")
        )
        self.assertEqual([step["valid_from"] for step in later["history"]], [None, "2027-02-01"])
        self.assertEqual(services.rate_for(self.anna, self.sound).hourly, D("30.00"))  # the guide value

    def test_day_rates_are_personnel_costs(self) -> None:
        services.set_rate(self.anna, self.sound, daily_rate=D("280.00"))
        Role.objects.create(name="Personal ohne Kosten", module_levels={"personnel": 2})
        client = self.client_for("pit", "Personal ohne Kosten")
        self.assertEqual(client.get(self.address).json(), [{"job_function": self.sound.pk, "name": "Tontechnik"}])
        self.assert_error(
            client.post(self.address, {"job_function": self.sound.pk, "daily_rate": "1.00"}, format="json"),
            403,
            "permission_denied",
        )
        refused = self.admin.post(self.address, {"job_function": self.sound.pk, "daily_rate": "-1"}, format="json")
        self.assert_error(refused, 400, "validation_error", "daily_rate")

    def test_the_guide_value_per_day_of_a_job_function(self) -> None:
        response = self.admin.patch(
            f"{API}/job-functions/{self.sound.pk}", {"guide_daily_cost_rate": "250.00"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["guide_daily_cost_rate"], "250.00")
        crew = self.client_for("carla", "Crew").get(f"{API}/job-functions").json()
        self.assertNotIn("guide_daily_cost_rate", next(row for row in crew if row["name"] == "Tontechnik"))


class LinkedCalendarsApiTests(ApiTestCase):
    """PER-031: ``calendars/feeds`` – several linked calendars; the addresses only for the person."""

    def setUp(self) -> None:
        super().setUp()
        self.server = serve(self)
        self.server.files["/private.ics"] = (200, {}, FEED)
        self.server.files["/band.ics"] = (200, {}, BAND)
        self.user = make_user("carla", roles=("Crew",))
        self.carla = Person.objects.get(user=self.user)
        self.client_ = self.client_of(self.user)
        self.feeds = f"{API}/people/me/calendars/feeds"

    def test_link_list_read_and_remove_own_calendars(self) -> None:
        first = self.client_.post(self.feeds, {"url": f"{self.server.url}/private.ics"}, format="json")
        self.assertEqual(first.status_code, 201, first.content)
        second = self.client_.post(self.feeds, {"url": f"{self.server.url}/band.ics", "label": "Band"}, format="json")
        self.assertEqual(
            {key: second.json()[key] for key in ("url", "label", "host", "checked_at", "error")},
            {
                "url": f"{self.server.url}/band.ics",
                "label": "Band",
                "host": "127.0.0.1",
                "checked_at": None,
                "error": "",
            },
        )
        listed = self.client_.get(self.feeds).json()
        self.assertEqual([item["label"] for item in listed], ["", "Band"])
        self.assertEqual(self.client_.get(f"{API}/people/me/calendars").json()["feeds"], listed)
        result = self.client_.post(f"{API}/people/me/calendars/sync", {"what": "feed"}, format="json").json()
        self.assertEqual(result["feed"], "read")
        self.assertTrue(all(item["checked_at"] for item in result["feeds"]))
        busy = AvailabilityMark.objects.filter(person=self.carla, source=AvailabilitySource.FEED)
        self.assertEqual(busy.count(), 7)
        self.assertEqual(self.client_.delete(f"{self.feeds}/{second.json()['id']}").status_code, 204)
        self.assertEqual(busy.count(), 6)
        self.assert_error(self.client_.delete(f"{self.feeds}/{second.json()['id']}"), 404, "not_found")

    def test_wrong_addresses_and_the_single_link_of_0_6_1_are_refused(self) -> None:
        self.assert_error(
            self.client_.post(self.feeds, {"url": "javascript:alert(1)"}, format="json"), 400, "validation_error", "url"
        )
        calendars.add_feed(self.carla, f"{self.server.url}/band.ics")
        self.assert_error(
            self.client_.post(self.feeds, {"url": f"{self.server.url}/band.ics"}, format="json"),
            400,
            "validation_error",
            "url",
        )
        self.assert_error(
            self.client_.patch(
                f"{API}/people/me/calendars", {"availability_feed_url": f"{self.server.url}/x.ics"}, format="json"
            ),
            400,
            "validation_error",
            "availability_feed_url",
        )
        read_only = self.client_of(self.user, read_only=True)
        self.assert_error(
            read_only.post(self.feeds, {"url": f"{self.server.url}/private.ics"}, format="json"),
            403,
            "permission_denied",
        )

    def test_personnel_planning_links_and_removes_but_never_sees_the_addresses(self) -> None:
        feeds = f"{API}/people/{self.carla.pk}/calendars/feeds"
        dispatcher = self.client_for("dora", "Personaldisposition")
        created = dispatcher.post(feeds, {"url": f"{self.server.url}/private.ics?token=very-secret"}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        self.assertNotIn("url", created.json())
        self.assertNotIn("very-secret", dispatcher.get(feeds).content.decode())
        self.assertNotIn("very-secret", dispatcher.get(f"{API}/people/{self.carla.pk}/calendars").content.decode())
        sync = dispatcher.post(f"{API}/people/{self.carla.pk}/calendars/sync", format="json")
        self.assertNotIn("very-secret", sync.content.decode())
        reader = self.client_for("paula", "Projektleitung")
        self.assertEqual(reader.get(feeds).status_code, 200)
        self.assert_error(
            reader.post(feeds, {"url": f"{self.server.url}/band.ics"}, format="json"), 403, "permission_denied"
        )
        self.assert_error(reader.delete(f"{feeds}/{created.json()['id']}"), 403, "permission_denied")
        self.assert_error(self.client_for("tim", "Crew").get(feeds), 403, "permission_denied")
        self.assertEqual(dispatcher.delete(f"{feeds}/{created.json()['id']}").status_code, 204)
        self.assertFalse(self.carla.calendar_feeds.exists())


class TimelineApiTests(ApiTestCase):
    """PER-020 with PER-027: ``/people/{id}/timeline`` has the availability as well (bug)."""

    def test_the_row_availability(self) -> None:
        anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        availability_marks.mark_period(anna, at(2), at(3), AvailabilityState.UNAVAILABLE, "Familienfeier")
        document = self.admin.get(f"{API}/people/{anna.pk}/timeline", {"from": "2027-03-01", "weeks": "1"}).json()
        row = next(row for row in document["rows"] if row["kind"] == "availability")
        self.assertEqual(
            [(bar["from"], bar["kind"], bar["label"]) for bar in row["bars"]],
            [("2027-03-02", "availability is-unavailable", "nicht verfügbar")],
        )
