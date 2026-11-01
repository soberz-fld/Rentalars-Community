# SPDX-License-Identifier: GPL-3.0-or-later
"""API, area "notify" (API-014): UIX-039, PRJ-109.

* UIX-039: ``GET /notifications`` gives every notification its ``category``
  and ``companion``; ``?category=`` and ``?companion=1`` filter;
  ``/notifications/preferences`` reads and stores ``companion`` and names the
  category. The token of the companion app reaches all of it.
* PRJ-109: ``follow_up_at`` – set with ``PUT /projects/{id}/follow-up``, read
  with the project and the service case.

VFG-034 has no operation of its own: ``GET /projects?follow_up=…`` lists the
follow-ups (PRJ-105); its filter ``due`` honours the time now.
"""

from __future__ import annotations

import datetime

from rentalars.accounts.rights import Module
from rentalars.notifications import services
from rentalars.notifications.models import Kind, Preference
from rentalars.projects import service_cases
from rentalars.projects.follow_up import set_follow_up
from rentalars.projects.models import ProjectStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import make_project, make_user, set_clock

NOTIFICATIONS = f"{API}/notifications"
PREFERENCES = f"{API}/notifications/preferences"

#: What the companion app's token may reach (APP-001).
APP_MODULES = [Module.PACKING, Module.PROJECTS, Module.TIME_TRACKING]


class NotificationCategoryApiTests(ApiTestCase):
    """UIX-039: category and companion flag with every notification; filters."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        services.notify([self.paula], Kind.FOLLOW_UP, "Wiedervorlage: Firmenfeier")
        services.notify([self.paula], Kind.PROJECT_CHANGE, "Firmenfeier geändert")
        services.notify([self.paula], Kind.LOW_STOCK, "Kabel unter Mindestbestand")
        self.client = self.client_of(self.paula, allowed_modules=APP_MODULES)

    def test_each_notification_names_category_and_app(self) -> None:
        response = self.client.get(NOTIFICATIONS)
        self.assertEqual(response.status_code, 200, response.content)
        rows = {row["kind"]: row for row in response.json()["results"]}
        self.assertEqual(rows["follow_up"]["category"], "project")
        self.assertTrue(rows["follow_up"]["companion"])
        self.assertEqual(rows["low_stock"]["category"], "material")
        self.assertFalse(rows["project_change"]["companion"])

    def test_filters(self) -> None:
        kinds = [row["kind"] for row in self.client.get(f"{NOTIFICATIONS}?category=material").json()["results"]]
        self.assertEqual(kinds, ["low_stock"])
        kinds = [row["kind"] for row in self.client.get(f"{NOTIFICATIONS}?companion=1").json()["results"]]
        self.assertEqual(kinds, ["follow_up"])
        kinds = [row["kind"] for row in self.client.get(f"{NOTIFICATIONS}?category=system").json()["results"]]
        self.assertEqual(kinds, [])
        self.assert_error(self.client.get(f"{NOTIFICATIONS}?category=weather"), 400, "validation_error", "category")


class NotificationPreferenceApiTests(ApiTestCase):
    """UIX-039: the choice "In der App" in the preferences."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.client = self.client_of(self.paula, allowed_modules=APP_MODULES)

    def test_read_sorted_by_category(self) -> None:
        rows = self.client.get(PREFERENCES).json()
        self.assertEqual(rows[0]["kind"], "deployment_request")
        self.assertEqual(rows[0]["category"], "project")
        self.assertTrue(rows[0]["companion"])
        self.assertEqual(rows[-1]["category"], "system")
        self.assertEqual(
            {"kind", "label", "category", "category_label", "in_app", "by_email", "companion"}, set(rows[0])
        )

    def test_store_with_and_without_companion(self) -> None:
        response = self.client.put(
            PREFERENCES,
            [{"kind": "project_change", "in_app": True, "by_email": False, "companion": True}],
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        row = next(row for row in response.json() if row["kind"] == "project_change")
        self.assertEqual((row["in_app"], row["by_email"], row["companion"]), (True, False, True))
        # As a client sends it without "companion": the choice stays.
        response = self.client.put(
            PREFERENCES, [{"kind": "project_change", "in_app": False, "by_email": True}], format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        stored = Preference.objects.get(user=self.paula, kind=Kind.PROJECT_CHANGE)
        self.assertEqual((stored.in_app, stored.by_email, stored.companion), (False, True, True))
        # The category is read only.
        response = self.client.put(
            PREFERENCES,
            [{"kind": "follow_up", "in_app": True, "by_email": True, "companion": False, "category": "system"}],
            format="json",
        )
        row = next(row for row in response.json() if row["kind"] == "follow_up")
        self.assertEqual((row["category"], row["companion"]), ("project", False))


class FollowUpTimeApiTests(ApiTestCase):
    """PRJ-109: ``follow_up_at`` in ``PUT /projects/{id}/follow-up`` and with the project."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.project = make_project("Firmenfeier", status=ProjectStatus.INQUIRY, manager=self.paula)
        self.url = f"{API}/projects/{self.project.pk}/follow-up"

    def test_set_read_and_due(self) -> None:
        response = self.admin.put(
            self.url,
            {"follow_up_on": "2027-03-01", "follow_up_at": "14:30", "follow_up_user": self.paula.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual((data["follow_up_on"], data["follow_up_at"]), ("2027-03-01", "14:30:00"))
        self.assertFalse(data["follow_up_is_due"])  # 08:00 on the clock of the tests
        due = [row["id"] for row in self.admin.get(f"{API}/projects?follow_up=due").json()["results"]]
        self.assertNotIn(self.project.pk, due)
        set_clock(datetime.datetime(2027, 3, 1, 14, 30, tzinfo=self.project.start.tzinfo))
        self.assertTrue(self.admin.get(f"{API}/projects/{self.project.pk}").json()["follow_up_is_due"])
        due = [row["id"] for row in self.admin.get(f"{API}/projects?follow_up=due").json()["results"]]
        self.assertIn(self.project.pk, due)

    def test_without_a_time_as_before(self) -> None:
        set_follow_up(self.project, on=datetime.date(2027, 3, 4), at=datetime.time(9), by=self.paula)
        response = self.admin.put(self.url, {"follow_up_on": "2027-03-04"}, format="json")
        self.assertIsNone(response.json()["follow_up_at"])
        response = self.admin.put(self.url, {"follow_up_on": "2027-03-04", "follow_up_at": None}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        response = self.admin.put(self.url, {"follow_up_on": "2027-03-04", "follow_up_at": "25:00"}, format="json")
        self.assert_error(response, 400, "validation_error", "follow_up_at")
        # Not through the project itself.
        self.admin.patch(f"{API}/projects/{self.project.pk}", {"follow_up_at": "10:00"}, format="json")
        self.project.refresh_from_db()
        self.assertIsNone(self.project.follow_up_at)
        response = self.admin.delete(self.url)
        self.assertIsNone(response.json()["follow_up_at"])

    def test_service_case_shows_it(self) -> None:
        case = service_cases.create_case(name="Reparatur", manager=self.paula)
        set_follow_up(case, on=datetime.date(2027, 3, 4), at=datetime.time(11, 0), by=self.paula)
        data = self.admin.get(f"{API}/service-cases/{case.pk}").json()
        self.assertEqual((data["follow_up_on"], data["follow_up_at"]), ("2027-03-04", "11:00:00"))
