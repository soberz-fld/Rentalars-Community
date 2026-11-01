# SPDX-License-Identifier: GPL-3.0-or-later
"""Through the API, area "cases": further statuses of a service case (PRJ-112) and the rules for them
(ADM-013).

Every new or changed operation is called here at least once with success (API-014): ``PATCH
/service-cases/{id}`` with the new statuses and the follow-up fields, ``POST /service-cases`` with a follow-up,
``GET /service-cases`` with its new default, and ``/automations`` with the new trigger, condition and action.
"""

from __future__ import annotations

import datetime

from rentalars.automations.models import Automation
from rentalars.projects import service_cases
from rentalars.projects.models import CaseStatus, Project
from tests.api.base import API, ApiTestCase
from tests.helpers import make_customer, make_user

CASES = f"{API}/service-cases"


class CaseStatusApiTests(ApiTestCase):
    """PRJ-112: the statuses in between only with the follow-up in the same request – else 400."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.manager = self.client_of(self.paula)
        self.customer = make_customer()
        self.case = service_cases.create_case(name="Spot flackert", customer=self.customer, manager=self.paula)
        self.url = f"{CASES}/{self.case.pk}"

    def reload(self) -> Project:
        return Project.objects.get(pk=self.case.pk)

    def test_waiting_with_and_without_follow_up(self) -> None:
        """PRJ-112, API-014: 400 without the follow-up or the reason; saved together with them."""
        error = self.assert_error(
            self.manager.patch(self.url, {"case_status": "waiting", "case_waiting_for": "action"}, format="json"),
            400,
            "validation_error",
            "follow_up_on",
        )
        self.assertIn("Wiedervorlage", error["fields"]["follow_up_on"][0]["message"])
        self.assert_error(
            self.manager.patch(self.url, {"case_status": "waiting", "follow_up_on": "2027-03-05"}, format="json"),
            400,
            "validation_error",
            "case_waiting_for",
        )
        self.assertEqual(self.reload().case_status, CaseStatus.OPEN)
        response = self.manager.patch(
            self.url,
            {
                "case_status": "waiting",
                "case_waiting_for": "action",
                "follow_up_on": "2027-03-05",
                "follow_up_note": "Kunde prüft Sicherung",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            (response.data["case_status"], response.data["case_waiting_for"], response.data["case_status_label"]),
            ("waiting", "action", "wartet auf Aktion"),
        )
        self.assertEqual(
            (response.data["follow_up_on"], response.data["follow_up_user"]), ("2027-03-05", self.paula.pk)
        )
        self.assertEqual(response.data["follow_up_note"], "Kunde prüft Sicherung")

    def test_closing_needs_the_time_and_backlog_a_day(self) -> None:
        """PRJ-112: "closing" with day and time; "backlog" with a day."""
        self.assert_error(
            self.manager.patch(self.url, {"case_status": "closing", "follow_up_on": "2027-03-05"}, format="json"),
            400,
            "validation_error",
            "follow_up_at",
        )
        response = self.manager.patch(
            self.url,
            {"case_status": "closing", "follow_up_on": "2027-03-05", "follow_up_at": "16:00"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.reload().follow_up_at, datetime.time(16, 0))
        self.assert_error(
            self.manager.patch(self.url, {"case_status": "backlog"}, format="json"), 400, "validation_error"
        )
        response = self.manager.patch(self.url, {"case_status": "backlog", "follow_up_on": "2027-04-01"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.reload().case_status, CaseStatus.BACKLOG)

    def test_the_reason_alone_and_the_follow_up_alone(self) -> None:
        """PRJ-112: the reason only with the status; the follow-up fields alone set the follow-up."""
        self.assert_error(
            self.manager.patch(self.url, {"case_waiting_for": "reply"}, format="json"),
            400,
            "validation_error",
            "case_waiting_for",
        )
        response = self.manager.patch(self.url, {"follow_up_on": "2027-03-08", "follow_up_at": "09:15"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        case = self.reload()
        self.assertEqual((case.case_status, case.follow_up_on), (CaseStatus.OPEN, datetime.date(2027, 3, 8)))

    def test_create_with_follow_up_and_the_list(self) -> None:
        """PRJ-112: a new case is open, a follow-up given is set; the list shows every case not done by default."""
        response = self.manager.post(
            CASES,
            {"name": "Kabel", "customer": self.customer.pk, "case_status": "backlog", "follow_up_on": "2027-03-09"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual((response.data["case_status"], response.data["follow_up_on"]), ("open", "2027-03-09"))
        service_cases.set_case_status(
            self.case, CaseStatus.BACKLOG, follow_up={"on": datetime.date(2027, 3, 9), "user": self.paula}
        )
        listed = self.manager.get(CASES)
        self.assertEqual({row["name"] for row in listed.data["results"]}, {"Kabel", "Spot flackert"})
        listed = self.manager.get(f"{CASES}?status=backlog")
        self.assertEqual([row["name"] for row in listed.data["results"]], ["Spot flackert"])

    def test_errors_in_english_for_an_english_caller(self) -> None:
        """PRJ-112: the messages are English UI text (UIX-029)."""
        response = self.manager.patch(
            self.url, {"case_status": "closing", "follow_up_on": "2027-03-05"}, format="json", HTTP_ACCEPT_LANGUAGE="en"
        )
        error = self.assert_error(response, 400, "validation_error", "follow_up_at")
        self.assertEqual(
            error["fields"]["follow_up_at"][0]["message"], "Choose the time at which the service case is closed."
        )


class AutomationApiTests(ApiTestCase):
    """ADM-013: the new trigger, condition and action through ``/automations``."""

    def test_create_and_refuse(self) -> None:
        """ADM-013, API-014."""
        url = f"{API}/automations"
        listed = self.admin.get(url)
        self.assertEqual(
            # Adds the rule of the defect reports (tests/unit/test_085_defects.py).
            {
                (rule["trigger"], rule["status"], rule["new_case_status"])
                for rule in listed.data
                if rule["trigger"] != "defect"
            },
            {
                ("case_follow_up", "closing", "done"),
                ("case_communication", "closing", "open"),
                ("case_follow_up", "backlog", "open"),
            },
        )
        body = {
            "name": "Wartet: Antwort öffnet",
            "trigger": "case_communication",
            "status": "waiting",
            "communication": "mail_in",
            "action": "case_status",
            "new_case_status": "open",
            "subject": "dropped",
        }
        created = self.admin.post(url, body, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual((created.data["communication"], created.data["subject"]), ("mail_in", ""))
        self.assert_error(
            self.admin.post(url, {**body, "new_case_status": "backlog"}, format="json"),
            400,
            "validation_error",
            "new_case_status",
        )
        self.assert_error(
            self.admin.post(url, {**body, "status": "confirmed"}, format="json"), 400, "validation_error", "status"
        )
        rule = Automation.objects.get(pk=created.data["id"])
        changed = self.admin.patch(f"{url}/{rule.pk}", {"is_active": False}, format="json")
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual(changed.data["new_case_status"], "open")
