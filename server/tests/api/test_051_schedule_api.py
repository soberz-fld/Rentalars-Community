# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the planning overviews: spans of days, availability and warnings (VFG-022, VFG-023)."""

from __future__ import annotations

from rentalars.personnel.models import Absence, AvailabilityMark
from tests.api.base import API, ApiTestCase
from tests.helpers import at, make_person, make_project, make_user, plan


class SpanOfDaysTests(ApiTestCase):
    """VFG-022: ``days`` asks for single days, as the zoom levels of the pages do."""

    def test_calendar_of_one_day(self) -> None:
        make_project("Vortrag", start=at(10, 8), end=at(10, 12))
        make_project("Kinderfest", start=at(11, 8), end=at(11, 12))
        rows = self.admin.get(f"{API}/calendar", {"from": "2027-03-10", "days": 1}).json()
        self.assertEqual([row["name"] for row in rows], ["Vortrag"])
        rows = self.admin.get(f"{API}/calendar", {"from": "2027-03-10", "days": 2}).json()
        self.assertEqual([row["name"] for row in rows], ["Vortrag", "Kinderfest"])
        # Weeks keep their meaning without "days".
        self.assertEqual(len(self.admin.get(f"{API}/calendar", {"from": "2027-03-08", "weeks": 1}).json()), 2)

    def test_a_wrong_number_of_days_is_an_error(self) -> None:
        self.assert_error(self.admin.get(f"{API}/calendar", {"days": "zwei"}), 400, "validation_error", "days")


class PersonnelPlanTests(ApiTestCase):
    """VFG-023: availability entries, named warnings; every active person (fix)."""

    def test_availability_and_warnings(self) -> None:
        anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        plan(make_project("Stadtfest"), "Tontechnik", anna, start=at(10, 8), end=at(10, 18))
        plan(make_project("Weinfest"), "Tontechnik", anna, start=at(10, 14), end=at(10, 22))
        AvailabilityMark.objects.create(person=anna, start=at(10), end=at(11), state="unavailable", source="feed")
        AvailabilityMark.objects.create(person=anna, start=at(11), end=at(12), state="limited", note="nur abends")
        Absence.objects.create(person=anna, kind="vacation", start=at(13), end=at(14))
        # Every active person is listed (VFG-023), the accounts of the test as well.
        rows = self.admin.get(f"{API}/personnel-plan", {"from": "2027-03-10", "days": 7}).json()
        (row,) = [row for row in rows if row["person"] == anna.pk]
        self.assertEqual(row["warnings"], ["double_booking", "unavailable"])
        self.assertTrue(row["conflict"])
        kinds = [(entry["type"], entry.get("state", "")) for entry in row["entries"]]
        self.assertEqual(
            kinds,
            [
                ("availability", "unavailable"),
                ("deployment", ""),
                ("deployment", ""),
                ("availability", "limited"),
                ("absence", ""),
            ],
        )
        self.assertEqual(row["entries"][0]["source"], "feed")
        self.assertEqual(row["entries"][3]["note"], "nur abends")

    def test_every_active_person_is_listed(self) -> None:
        """VFG-023, fix: every active person, also without a job function; ``busy=1`` only the busy."""
        make_person("Anna Becker", rates={"Stagehand": "20.00"})
        office = make_user("buero").person  # an office account: a person without a job function (AUT-026)
        ben = make_person("Ben Schmidt")  # no job function, but deployed in the span
        plan(make_project("Stadtfest"), "Stagehand", ben, start=at(10, 8), end=at(10, 18))
        names = [row["name"] for row in self.admin.get(f"{API}/personnel-plan", {"from": "2027-03-08"}).json()]
        self.assertIn("Anna Becker", names)
        self.assertIn("Ben Schmidt", names)
        self.assertIn(office.name, names)
        busy = self.admin.get(f"{API}/personnel-plan", {"from": "2027-03-08", "busy": "1"}).json()
        self.assertEqual([row["name"] for row in busy], ["Ben Schmidt"])
