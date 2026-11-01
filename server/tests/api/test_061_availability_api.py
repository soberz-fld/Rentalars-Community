# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the availability that counts and of series (PER-027, PER-028).

Below ``/people/{id}``, where ``{id}`` may be ``me``:

* ``availability-periods`` – one availability at any moment;
* ``availability-series`` – list and enter series; one series: read, change from a day on, remove.
"""

from __future__ import annotations

from rentalars.personnel import marks as availability_marks
from rentalars.personnel.models import (
    AvailabilityMark,
    AvailabilitySeries,
    AvailabilitySource,
    AvailabilityState,
    Person,
)
from tests.api.base import API, ApiTestCase
from tests.helpers import at, make_person, make_user

RED, YELLOW, GREEN = AvailabilityState.UNAVAILABLE, AvailabilityState.LIMITED, AvailabilityState.AVAILABLE


class AvailabilityPeriodsApiTests(ApiTestCase):
    """PER-027: the stored entries, and the availability that counts."""

    def setUp(self) -> None:
        super().setUp()
        self.user = make_user("carla", roles=("Crew",))
        self.carla = Person.objects.get(user=self.user)
        self.client_ = self.client_of(self.user)

    def test_one_availability_at_any_moment(self) -> None:
        AvailabilityMark.objects.create(
            person=self.carla, start=at(10, 9), end=at(10, 12), state=RED, source=AvailabilitySource.FEED,
            entered_at=at(1, 9),
        )  # fmt: skip
        AvailabilityMark.objects.create(
            person=self.carla, start=at(10, 11), end=at(10, 14), state=RED, source=AvailabilitySource.FEED
        )
        availability_marks.mark_period(self.carla, at(10), at(11), GREEN, "gern")
        marks = self.client_.get(f"{API}/people/me/availability-marks").json()
        self.assertEqual(len(marks), 3)
        own = next(mark for mark in marks if mark["source"] == "own")
        self.assertEqual((own["series"], own["entered_at"] is not None), (None, True))
        response = self.client_.get(
            f"{API}/people/me/availability-periods", {"from": at(9).isoformat(), "to": at(12).isoformat()}
        )
        self.assertEqual(response.status_code, 200, response.content)
        periods = [(item["state"], item["source"], item["note"]) for item in response.json()]
        # The busy times are one block, and newer than the green entry.
        self.assertEqual(periods, [(GREEN, "own", "gern"), (RED, "feed", ""), (GREEN, "own", "gern")])
        self.assertEqual(response.json()[1]["start"][:16], "2027-03-10T09:00")
        self.assertEqual(response.json()[1]["end"][:16], "2027-03-10T14:00")
        self.assertEqual(response.json()[0]["marks"], [own["id"]])

    def test_others_need_the_personnel_right(self) -> None:
        anna = make_person("Anna Becker")
        url = f"{API}/people/{anna.pk}/availability-periods"
        self.assert_error(self.client_.get(url), 403, "permission_denied")
        self.assertEqual(self.client_for("dora", "Personaldisposition").get(url).status_code, 200)


class AvailabilitySeriesApiTests(ApiTestCase):
    """PER-028: series through the API, for oneself and – with the personnel right – for others."""

    def setUp(self) -> None:
        super().setUp()
        self.user = make_user("carla", roles=("Crew",))
        self.carla = Person.objects.get(user=self.user)
        self.client_ = self.client_of(self.user)
        self.url = f"{API}/people/me/availability-series"

    def create(self, **values: object) -> dict:
        body = {
            "state": RED,
            "note": "Chor",
            "first_day": "2027-03-02",
            "start_time": "18:00",
            "end_time": "22:00",
            "repeat": "weekly",
            "weekdays": [1, 3],
            "count": 4,
            **values,
        }
        response = self.client_.post(self.url, body, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_enter_list_read_change_and_remove(self) -> None:
        series = self.create()
        self.assertEqual((series["weekdays"], series["last_day"], series["count"]), ([1, 3], "2027-03-02", 4))
        self.assertIn("wöchentlich am Di, Do", series["description"])
        starts = [mark.start for mark in self.carla.availability_marks.order_by("start")]
        self.assertEqual(starts, [at(2, 18), at(4, 18), at(9, 18), at(11, 18)])
        self.assertEqual([item["id"] for item in self.client_.get(self.url).json()], [series["id"]])
        detail = f"{self.url}/{series['id']}"
        self.assertEqual(self.client_.get(detail).json()["note"], "Chor")
        changed = self.client_.patch(detail, {"state": YELLOW, "from_day": "2027-03-09"}, format="json")
        self.assertEqual(changed.status_code, 200, changed.content)
        states = [mark.state for mark in self.carla.availability_marks.order_by("start")]
        self.assertEqual(states, [RED, RED, YELLOW, YELLOW])
        self.assertEqual(self.client_.delete(f"{detail}?from=2027-03-10").status_code, 204)
        self.assertEqual(self.carla.availability_marks.count(), 3)
        self.assertEqual(self.client_.delete(detail).status_code, 204)
        self.assertFalse(AvailabilitySeries.objects.exists())
        self.assertFalse(self.carla.availability_marks.exists())

    def test_a_rule_out_of_range_is_refused(self) -> None:
        response = self.client_.post(
            self.url, {"state": RED, "first_day": "2027-03-02", "repeat": "weekly"}, format="json"
        )
        self.assert_error(response, 400, "validation_error", "until")
        response = self.client_.post(
            self.url, {"state": RED, "first_day": "2027-03-02", "repeat": "weekly", "count": 2, "interval": 60},
            format="json",
        )  # fmt: skip
        self.assert_error(response, 400, "validation_error", "interval")
        series = self.create()
        self.assert_error(
            self.client_.delete(f"{self.url}/{series['id']}?from=morgen"), 400, "validation_error", "from"
        )

    def test_others_need_the_personnel_right(self) -> None:
        anna = make_person("Anna Becker")
        url = f"{API}/people/{anna.pk}/availability-series"
        self.assert_error(self.client_.get(url), 403, "permission_denied")
        reader = self.client_for("paula", "Projektleitung")
        self.assertEqual(reader.get(url).status_code, 200)
        body = {"state": RED, "first_day": "2027-03-02", "repeat": "daily", "count": 2}
        self.assert_error(reader.post(url, body, format="json"), 403, "permission_denied")
        dispatcher = self.client_for("dora", "Personaldisposition")
        self.assertEqual(dispatcher.post(url, body, format="json").status_code, 201)
        series = AvailabilitySeries.objects.get(person=anna)
        self.assertEqual(self.client_.get(f"{self.url}/{series.pk}").status_code, 404)

    def test_a_read_only_token_changes_nothing(self) -> None:
        series = self.create()
        reading = self.client_of(self.user, read_only=True)
        self.assertEqual(reading.get(self.url).status_code, 200)
        self.assert_error(reading.delete(f"{self.url}/{series['id']}"), 403, "permission_denied")
