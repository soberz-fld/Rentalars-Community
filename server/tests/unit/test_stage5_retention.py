# SPDX-License-Identifier: GPL-3.0-or-later
"""NFA-011: retention periods set in the administration."""

from __future__ import annotations

import datetime
import io

from django.core.management import call_command
from django.urls import reverse

from rentalars.accounts.models import SecurityEvent
from rentalars.core.audit import record_event
from rentalars.core.models import AuditLogEntry, BackgroundJob, JobStatus, SystemSettings
from rentalars.notifications.models import Notification
from tests.helpers import RentalarsTestCase, clock, make_user
from tests.ui.base import UiTestCase, form_data


class RetentionTests(RentalarsTestCase):
    def test_the_periods_of_the_settings_apply(self) -> None:
        now = clock()
        anna = make_user("anna")
        SystemSettings.objects.update(
            retention_security_log_days=30,
            retention_change_log_days=90,
            retention_notifications_days=7,
            retention_jobs_days=2,
        )
        SecurityEvent.objects.create(kind="login", user=anna, timestamp=now - datetime.timedelta(days=40))
        SecurityEvent.objects.create(kind="login", user=anna, timestamp=now - datetime.timedelta(days=20))
        record_event(SystemSettings.load(), "test.old", {})
        record_event(SystemSettings.load(), "test.new", {})
        AuditLogEntry.objects.filter(event="test.old").update(timestamp=now - datetime.timedelta(days=100))
        Notification.objects.create(user=anna, kind="defect", title="alt", created_at=now - datetime.timedelta(days=8))
        Notification.objects.create(user=anna, kind="defect", title="neu", created_at=now - datetime.timedelta(days=6))
        BackgroundJob.objects.create(
            kind="labels", title="alt", status=JobStatus.DONE, finished_at=now - datetime.timedelta(days=3)
        )
        BackgroundJob.objects.create(
            kind="labels", title="neu", status=JobStatus.DONE, finished_at=now - datetime.timedelta(days=1)
        )

        output = io.StringIO()
        call_command("run_daily_maintenance", stdout=output)
        self.assertEqual(SecurityEvent.objects.count(), 1)
        self.assertEqual(
            list(AuditLogEntry.objects.filter(event__startswith="test.").values_list("event", flat=True)),
            ["test.new"],
        )
        self.assertEqual(list(Notification.objects.values_list("title", flat=True)), ["neu"])
        self.assertEqual(list(BackgroundJob.objects.values_list("title", flat=True)), ["neu"])
        self.assertIn("change log entries", output.getvalue())

    def test_zero_keeps_the_change_log_for_good(self) -> None:
        record_event(SystemSettings.load(), "test.ancient", {})
        AuditLogEntry.objects.update(timestamp=clock() - datetime.timedelta(days=9000))
        call_command("run_daily_maintenance", stdout=io.StringIO())
        self.assertTrue(AuditLogEntry.objects.filter(event="test.ancient").exists())


class RetentionSettingsPageTests(UiTestCase):
    def test_periods_and_api_limit_are_set_in_the_administration(self) -> None:
        url = reverse("core:company_settings")
        page = self.client.get(url)
        self.assertIn("Sicherheitsprotokoll aufbewahren (Tage)", self.assert_ok(page))
        data = form_data(page, containing="system-retention_jobs_days")
        data.update({"system-retention_jobs_days": "14", "system-api_requests_per_minute": "120", "form": "system"})
        self.client.post(url, data)
        settings = SystemSettings.load()
        self.assertEqual((settings.retention_jobs_days, settings.api_requests_per_minute), (14, 120))
        data["system-retention_security_log_days"] = "5"
        self.assertIn("größer oder gleich 30", self.assert_ok(self.client.post(url, data)))
