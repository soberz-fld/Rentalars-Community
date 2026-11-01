# SPDX-License-Identifier: GPL-3.0-or-later
"""Page tests, area "companion": changes in the browser and by automations note their moment (PRJ-113).

The companion app judges its offline changes against these moments
(``field_changed_at``); a change in the browser must count as much as one
through the API, or the phone would overwrite it.
"""

from __future__ import annotations

import datetime

from django.urls import reverse

from rentalars.projects import field_changes, service_cases
from rentalars.projects.models import CaseStatus, Project, ProjectStatus
from tests.helpers import NOW, at, make_customer, make_project, make_user, set_clock
from tests.ui.base import UiTestCase, form_data

LATER = NOW + datetime.timedelta(hours=2)


def times(project: Project) -> dict[str, datetime.datetime]:
    return field_changes.times_of(Project.objects.get(pk=project.pk))


class BrowserChangesNoteTheirMomentTests(UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.project = make_project("Stadtfest", venue="Marktplatz", status=ProjectStatus.INQUIRY)
        set_clock(LATER)
        self.client.force_login(self.admin_user)  # again: the clock moved past the idle time of the session

    def test_the_form_of_the_project(self) -> None:
        url = reverse("projects:edit", args=[self.project.pk])
        self.client.post(url, form_data(self.client.get(url), containing="start", venue="Rathaus"))
        self.assertEqual(Project.objects.get(pk=self.project.pk).venue, "Rathaus")
        stored = times(self.project)
        self.assertEqual((stored["venue"], stored["name"], stored["start"], stored["notes"]), (LATER, NOW, NOW, NOW))

    def test_the_status_action_and_the_follow_up_dialog(self) -> None:
        self.client.post(reverse("projects:set_status", args=[self.project.pk]), {"status": ProjectStatus.OPTION})
        dialog = reverse("projects:follow_up", args=[self.project.pk])
        set_clock(LATER + datetime.timedelta(minutes=5))
        self.client.post(dialog, form_data(self.client.get(dialog), "follow_up_on", follow_up_on="2027-03-08"))
        project = Project.objects.get(pk=self.project.pk)
        self.assertEqual((project.status, project.follow_up_on), (ProjectStatus.OPTION, datetime.date(2027, 3, 8)))
        stored = times(self.project)
        self.assertEqual(
            (stored["status"], stored["follow_up"], stored["name"]),
            (LATER, LATER + datetime.timedelta(minutes=5), NOW),
        )
        # The API shows the same moments.
        detail = self.client.get(f"/api/v1/projects/{self.project.pk}").json()
        self.assertEqual(datetime.datetime.fromisoformat(detail["field_changed_at"]["status"]), LATER)

    def test_the_status_of_a_service_case(self) -> None:
        case = service_cases.create_case(name="Spot flackert", customer=make_customer("Theater"))
        set_clock(LATER + datetime.timedelta(minutes=5))
        self.client.post(reverse("projects:case_status", args=[case]), {"case_status": CaseStatus.IN_PROGRESS})
        self.assertEqual(Project.objects.get(pk=case.pk).case_status, CaseStatus.IN_PROGRESS)
        self.assertEqual(times(case)["case_status"], LATER + datetime.timedelta(minutes=5))

    def test_an_automation_closing_a_case(self) -> None:
        """ADM-013, PRJ-112: the default rule closes a case waiting to close – a change like any other."""
        from rentalars.projects.follow_up import notify_due_follow_ups

        case = service_cases.create_case(name="Spot flackert", customer=make_customer("Theater"))
        service_cases.set_case_status(
            case,
            CaseStatus.CLOSING,
            follow_up={"on": datetime.date(2027, 3, 3), "at": datetime.time(14, 30), "user": self.paula},
        )
        set_clock(at(3, 14, 30))
        with self.captureOnCommitCallbacks(execute=True):
            notify_due_follow_ups()
        closed = Project.objects.get(pk=case.pk)
        self.assertEqual(closed.case_status, CaseStatus.DONE)
        stored = times(case)
        self.assertEqual((stored["case_status"], stored["follow_up"]), (at(3, 14, 30), at(3, 14, 30)))
