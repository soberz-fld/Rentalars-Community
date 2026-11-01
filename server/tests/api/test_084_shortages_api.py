# SPDX-License-Identifier: GPL-3.0-or-later
"""API, area "shortages" (API-014): ``GET/PATCH /settings/notifications`` (VFG-036).

When, how often and how far ahead shortages are reported, and whether known ones are reported again – for the whole
company. The notifications themselves stay as they were: ``/notifications`` and ``/notifications/preferences``, which
the companion app uses, do not change.
"""

from __future__ import annotations

from rentalars.core.models import NotificationSettings, ShortageInterval
from tests.api.base import API, ApiTestCase
from tests.helpers import at

URL = f"{API}/settings/notifications"
APP_MODULES = ["packing", "projects", "time_tracking", "email"]


class NotificationSettingsApiTests(ApiTestCase):
    """VFG-036: read and change the settings of the shortage notifications."""

    def test_read_the_defaults(self) -> None:
        NotificationSettings.objects.filter(pk=1).update(shortage_last_run=at(1, 4, 15))
        response = self.admin.get(URL)
        self.assertEqual(response.status_code, 200, response.data)
        # The reminders of invoices (DOK-015) are in the same settings – tested in test_085_invoices.
        self.assertEqual(
            {name: value for name, value in response.json().items() if name.startswith("shortage_")},
            {
                "shortage_interval": "daily",
                "shortage_weekday": 1,
                "shortage_time": "04:15:00",
                "shortage_lead_weeks": 4,
                "shortage_repeat": True,  # VFG-036: on by default (tests/unit/test_093_notifications.py)
                "shortage_checked_at": None,
                "shortage_reported": 0,
                "shortage_next_check": "2027-03-02T04:15:00+01:00",
            },
        )

    def test_change_to_working_days(self) -> None:
        NotificationSettings.objects.filter(pk=1).update(
            shortage_last_run=at(1, 4, 15), shortage_checked_at=at(1, 4, 15), shortage_reported=2
        )
        response = self.admin.patch(
            URL,
            {"shortage_interval": "workdays", "shortage_time": "06:30", "shortage_lead_weeks": 10},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["shortage_interval"], "workdays")
        self.assertEqual(response.data["shortage_lead_weeks"], 10)
        self.assertEqual(response.data["shortage_checked_at"], "2027-03-01T04:15:00+01:00")
        self.assertEqual(response.data["shortage_reported"], 2)
        self.assertEqual(response.data["shortage_next_check"], "2027-03-02T06:30:00+01:00")
        settings = NotificationSettings.objects.get(pk=1)
        self.assertEqual((settings.shortage_interval, settings.shortage_lead_weeks), (ShortageInterval.WORKDAYS, 10))
        # The new time counts from its next moment.
        self.assertEqual(settings.shortage_last_run, at(1, 8))

    def test_repetition_and_lead_time_keep_the_schedule(self) -> None:
        NotificationSettings.objects.filter(pk=1).update(shortage_last_run=at(1, 4, 15))
        response = self.admin.patch(URL, {"shortage_repeat": True, "shortage_lead_weeks": 2}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        settings = NotificationSettings.objects.get(pk=1)
        self.assertEqual((settings.shortage_repeat, settings.shortage_last_run), (True, at(1, 4, 15)))

    def test_switch_off(self) -> None:
        response = self.admin.patch(URL, {"shortage_interval": "off"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data["shortage_next_check"])

    def test_wrong_values_are_refused(self) -> None:
        self.assert_error(
            self.admin.patch(URL, {"shortage_lead_weeks": 27}, format="json"),
            400,
            "validation_error",
            "shortage_lead_weeks",
        )
        self.assert_error(
            self.admin.patch(URL, {"shortage_interval": "hourly"}, format="json"),
            400,
            "validation_error",
            "shortage_interval",
        )
        self.assert_error(
            self.admin.patch(URL, {"shortage_weekday": 8}, format="json"), 400, "validation_error", "shortage_weekday"
        )
        self.assert_error(
            self.admin.patch(URL, {"shortage_time": "25:00"}, format="json"), 400, "validation_error", "shortage_time"
        )
        # Read only: the bookkeeping of the check.
        self.admin.patch(
            URL, {"shortage_reported": 9, "shortage_checked_at": "2027-03-01T04:15:00+01:00"}, format="json"
        )
        settings = NotificationSettings.objects.get(pk=1)
        self.assertEqual((settings.shortage_reported, settings.shortage_checked_at), (0, None))
        self.assertEqual(settings.shortage_lead_weeks, 4)

    def test_only_the_module_settings(self) -> None:
        planner = self.client_for("pia", "Projektleitung")
        self.assertEqual(planner.get(URL).status_code, 403)
        self.assertEqual(planner.patch(URL, {"shortage_interval": "off"}, format="json").status_code, 403)
        reader = self.client_of(self.admin_user, read_only=True)
        self.assertEqual(reader.get(URL).status_code, 200)
        self.assertEqual(reader.patch(URL, {"shortage_interval": "off"}, format="json").status_code, 403)
        self.assertEqual(NotificationSettings.objects.get(pk=1).shortage_interval, ShortageInterval.DAILY)

    def test_the_token_of_the_companion_app(self) -> None:
        """Not for the app's token – its notifications and their settings work as before."""
        app = self.client_of(self.admin_user, allowed_modules=APP_MODULES)
        self.assertEqual(app.get(URL).status_code, 403)
        self.assertEqual(app.get(f"{API}/notifications").status_code, 200)
        preferences = app.get(f"{API}/notifications/preferences")
        self.assertEqual(preferences.status_code, 200)
        self.assertIn("shortage", [item["kind"] for item in preferences.data])
