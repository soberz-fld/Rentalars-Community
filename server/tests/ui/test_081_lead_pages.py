# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages after the independent check.

An update logged the service product of crew lines and job functions as readable text
("D-001 …") instead of an ID. The change log and the histories showed a server error for those
entries (ADM-005).
"""

from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from rentalars.core.history import _Lookup
from rentalars.core.models import AuditAction, AuditLogEntry
from rentalars.products.models import Product
from rentalars.projects.models import CrewLine, Project
from tests.helpers import job_function, make_person, make_project, make_user, plan
from tests.ui.base import UiTestCase


class TextInsteadOfIdTests(UiTestCase):
    """ADM-005: an entry whose reference holds a text shows the text."""

    def test_lookup(self) -> None:
        lookup = _Lookup()
        self.assertEqual(lookup.name_of(Product, "D-001 Techniker"), "D-001 Techniker")
        self.assertEqual(lookup.name_of(Product, 987654), "#987654")

    def test_change_log_and_history_open(self) -> None:
        project = make_project("Stadtfest")
        line = plan(project, job_function("Licht"))
        AuditLogEntry.objects.create(
            content_type=ContentType.objects.get_for_model(CrewLine),
            object_id=str(line.pk),
            action=AuditAction.UPDATED,
            actor_label="Aktualisierung 0.7.1",
            object_repr=str(line),
            changes={"service_product": ["D-001", "D-902 Licht"]},
            parent_content_type=ContentType.objects.get_for_model(Project),
            parent_object_id=str(project.pk),
        )
        response = self.client.get("/administration/audit-log/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "D-902 Licht")
        response = self.client.get(reverse("projects:history", args=[project.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "D-902 Licht")


class ReviewFixesTests(UiTestCase):
    """Findings of the independent check and their fixes."""

    def test_record_time_from_the_service_case(self) -> None:
        """ZEI-024: a time on an open case from its page and from Mein Bereich → Servicefälle."""
        from rentalars.projects.models import CaseStatus
        from rentalars.projects.service_cases import add_participant, create_case, set_case_status

        case = create_case(user=self.admin_user, name="Beamer flackert")
        quick = f"/times/quick/?project={case.pk}"
        self.assertContains(self.client.get(reverse("projects:case_detail", args=[case])), quick)
        person = make_person("Tom Richter", user=self.admin_user)
        add_participant(case, person, user=self.admin_user)
        mine = self.client.get(reverse("projects:my_cases"))
        self.assertContains(mine, quick)
        self.assertContains(mine, f"Zeit auf {case.number} erfassen")
        self.assertContains(self.client.get(quick), "Beamer flackert")
        set_case_status(case, CaseStatus.DONE)
        self.assertNotContains(self.client.get(reverse("projects:case_detail", args=[case])), f'hx-get="{quick}"')

    def test_people_added_to_a_case_get_their_own_notification(self) -> None:
        """PRJ-108, UIX-039: its own kind – by mail and in the app unless switched off."""
        from rentalars.notifications.categories import category_of
        from rentalars.notifications.models import COMPANION_BY_DEFAULT, EMAIL_BY_DEFAULT, Kind, Notification
        from rentalars.projects.service_cases import add_participant, create_case

        case = create_case(user=self.admin_user, name="Funkstrecke rauscht")
        anna = make_user("anna")
        add_participant(case, make_person("Anna Becker", user=anna), user=self.admin_user)
        notice = Notification.objects.get(user=anna)
        self.assertEqual(notice.kind, Kind.SERVICE_CASE)
        self.assertTrue(notice.companion)
        self.assertIn(Kind.SERVICE_CASE, EMAIL_BY_DEFAULT)
        self.assertIn(Kind.SERVICE_CASE, COMPANION_BY_DEFAULT)
        self.assertEqual(category_of(Kind.SERVICE_CASE), "project")
        self.assertContains(self.client.get("/account/notifications/"), "Zu einem Servicefall hinzugefügt")

    def test_no_requirement_id_in_the_role_form(self) -> None:
        """A help text of the role form named "AUT-006"; texts in the interface never name requirement IDs."""
        self.assertNotContains(self.client.get("/administration/roles/new/"), "AUT-006")

    def test_the_mail_settings_have_one_name(self) -> None:
        """The settings list them as "Postfächer und Signatur" – the page and its breadcrumbs say the same."""
        page = self.client.get("/administration/mail/")
        self.assertContains(page, "<title>Postfächer und Signatur – Rentalars</title>", html=False)
        self.assertContains(page, "<h1>Postfächer und Signatur</h1>", html=False)
