# SPDX-License-Identifier: GPL-3.0-or-later
"""What the independent review of the tick boxes, the actions and the PDF of a case found."""

from __future__ import annotations

import datetime
import re
from unittest import mock

from django.core.exceptions import ValidationError
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module
from rentalars.mail.models import Direction, MailKind, ProjectMail
from rentalars.projects import bulk, case_pdf, follow_up, service_cases
from rentalars.projects.models import CaseStatus, ProjectMembership
from tests.api.base import API, ApiTestCase
from tests.helpers import make_customer, make_project, make_user
from tests.ui.base import UiTestCase
from tests.unit.test_092_lock import LockScene
from tests.unit.test_093_dguv import setup_dguv

DAY = datetime.date(2027, 3, 1)


class SelectionTests(UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.customers = [make_customer(f"Kunde {n}") for n in range(4)]
        self.data = {
            "table": "customers",
            "prefix": "",
            "next": reverse("customers:list"),
            "sel_customers": [str(c.pk) for c in self.customers],
        }

    def test_a_long_selection_waits_in_the_session_and_the_address_stays_short(self) -> None:
        with mock.patch("rentalars.core.bulk.LONG_SELECTION", 2):
            response = self.client.post(reverse("core:bulk_csv"), self.data)
        self.assertLess(len(response["Location"]), 200)
        self.assertIn("only=t%3A", response["Location"])
        text = self.client.get(response["Location"]).content.decode("utf-8")
        for customer in self.customers:
            self.assertIn(customer.name, text)

    def test_a_token_of_another_session_chooses_nothing(self) -> None:
        text = self.client.get(reverse("customers:list"), {"format": "csv", "only": "t:feedfeed"}).content.decode()
        self.assertNotIn("Kunde 0", text)

    def test_odd_digits_and_odd_next_addresses_are_no_server_error(self) -> None:
        for value in ("²", "٣", "1e3"):
            response = self.client.post(reverse("core:bulk_csv"), {**self.data, "sel_customers": [value]})
            self.assertEqual(response.status_code, 302, value)
            self.assertEqual(
                self.client.get(reverse("customers:list"), {"format": "csv", "only": value}).status_code, 200
            )
        for target in ("?q=1", "foo", "foo?bar", "//evil.example/x", "/\\evil"):
            response = self.client.post(reverse("core:bulk_csv"), {**self.data, "next": target})
            self.assertEqual(response.status_code, 302, target)
            self.assertTrue(response["Location"].startswith("/") and not response["Location"].startswith("//"), target)


class InspectionCsvTests(UiTestCase):
    def test_the_csv_of_the_inspections_can_be_narrowed_to_the_chosen_rows(self) -> None:
        setup_dguv(self)
        user = make_user("matread")
        user.roles.add(
            Role.objects.create(
                name="MatLeser", module_levels={Module.MATERIAL: int(Level.READ), Module.PROJECTS: int(Level.READ)}
            )
        )
        browser = self.browser_of(user)  # with write access the page has the bar of its own (items)
        page = browser.get(reverse("material:inspections")).content.decode()
        keys = re.findall(r'name="sel_[a-z_]+" value="(\d+)"', page)
        self.assertTrue(keys)
        full = browser.get(reverse("material:inspections"), {"format": "csv"}).content.decode().strip().splitlines()
        only = (
            browser.get(reverse("material:inspections"), {"format": "csv", "only": keys[0]})
            .content.decode()
            .strip()
            .splitlines()
        )
        self.assertGreater(len(only), 1)  # not only the head line
        self.assertLessEqual(len(only), len(full))


class CaseWorkerTests(LockScene, UiTestCase):
    def test_the_person_responsible_without_a_person_may_use_the_bar(self) -> None:
        self.make_scene()
        nobody = make_user("ohne-person", roles=("Crew",))
        case = service_cases.create_case(name="Ohne Person", customer=self.customer, manager=nobody, user=self.paula)
        response = self.browser_of(nobody).post(
            reverse("projects:bulk_cases"),
            {
                "table": "service_cases",
                "sel_service_cases": [case.pk],
                "action": "status",
                "case_status": "in_progress",
            },
        )
        self.assertEqual(response.status_code, 302)
        case.refresh_from_db()
        self.assertEqual(case.case_status, CaseStatus.IN_PROGRESS)


class CaseWorkerApiTests(LockScene, ApiTestCase):
    def test_a_case_worker_may_use_the_api_as_in_the_browser(self) -> None:
        self.make_scene()
        client = self.client_of(self.kai)
        single = client.patch(f"{API}/service-cases/{self.case.pk}", {"case_status": "in_progress"}, format="json")
        self.assertEqual(single.status_code, 200)
        response = client.post(
            f"{API}/service-cases/bulk", {"ids": [self.case.pk], "action": "status", "status": "open"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["changed"], [self.case.pk])
        # the projects endpoint stays closed to him
        closed = client.post(
            f"{API}/projects/bulk", {"ids": [self.project.pk], "action": "clear_follow_up"}, format="json"
        )
        self.assertEqual(closed.status_code, 403)


class ReplayTests(ApiTestCase):
    def test_a_stored_answer_is_not_repeated_after_the_access_is_gone(self) -> None:
        role = Role.objects.create(name="Zugewiesen schreiben", module_levels={Module.PROJECTS: int(Level.WRITE)})
        user = make_user("eve")
        user.roles.add(role)
        project = make_project("Geheimprojekt Alpha")
        membership = ProjectMembership.objects.create(project=project, user=user, level="read")
        client = self.client_of(user)
        body = {"ids": [project.pk], "action": "clear_follow_up"}
        first = client.post(f"{API}/projects/bulk", body, format="json", HTTP_IDEMPOTENCY_KEY="k1")
        self.assertEqual(first.status_code, 200)
        membership.delete()
        again = client.post(f"{API}/projects/bulk", body, format="json", HTTP_IDEMPOTENCY_KEY="k1")
        self.assertNotIn("Geheimprojekt", again.content.decode())


class FollowUpAndStatusTests(UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.rights = self.admin_user.rights
        self.case = service_cases.create_case(name="Spot defekt", customer=make_customer("Kunde"))

    def change(self, ids, action, **values):
        return bulk.change(ids, action, rights=self.rights, user=self.admin_user, cases_only=True, values=values)

    def test_taking_off_a_note_alone_counts_as_a_change(self) -> None:
        project = make_project("Mit Notiz")
        project.follow_up_note = "nur eine Notiz"
        project.save()
        result = bulk.change([project.pk], "clear_follow_up", rights=self.rights, user=self.admin_user)
        self.assertEqual(result.changed_ids, [project.pk])
        project.refresh_from_db()
        self.assertEqual(project.follow_up_note, "")
        self.assertFalse(follow_up.clear_follow_up(project))

    def test_a_status_that_needs_a_day_is_refused_once_for_all(self) -> None:
        for status in ("waiting", "closing", "backlog"):
            with self.assertRaises(ValidationError) as caught:
                self.change([self.case.pk], "status", status=status, waiting_for="reply")
            self.assertIn("follow_up_on", caught.exception.message_dict, status)
        with self.assertRaises(ValidationError) as caught:
            self.change([self.case.pk], "status", status="waiting", on=DAY, user=self.admin_user)
        self.assertIn("case_waiting_for", caught.exception.message_dict)
        with self.assertRaises(ValidationError) as caught:
            self.change([self.case.pk], "status", status="closing", on=DAY, user=self.admin_user)
        self.assertIn("follow_up_at", caught.exception.message_dict)

    def test_the_follow_up_fields_left_in_the_bar_do_not_set_a_follow_up_with_another_status(self) -> None:
        result = self.change([self.case.pk], "status", status="in_progress", on=DAY, note="alt", user=self.admin_user)
        self.assertEqual(result.changed_ids, [self.case.pk])
        self.case.refresh_from_db()
        self.assertEqual(self.case.case_status, CaseStatus.IN_PROGRESS)
        self.assertIsNone(self.case.follow_up_on)


class CasePdfTextTests(UiTestCase):
    def test_a_mail_with_html_only_comes_as_text(self) -> None:
        case = service_cases.create_case(name="HTML-Mail", customer=make_customer("Kunde"))
        mail = ProjectMail(
            project=case,
            direction=Direction.INCOMING,
            kind=MailKind.NORMAL,
            subject="Preis",
            text_body="",
            html_body="<style>p{color:red}</style><p>Preis &amp; Leistung&nbsp;ok</p><script>alert(1)</script>",
        )
        text = case_pdf._text_of(mail)
        self.assertIn("Preis & Leistung", text)
        self.assertNotIn("color:red", text)
        self.assertNotIn("alert(1)", text)
        self.assertNotIn("&amp;", text)
