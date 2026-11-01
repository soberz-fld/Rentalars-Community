# SPDX-License-Identifier: GPL-3.0-or-later
"""Actions on the ticked rows of the lists of projects and service cases (``projects.bulk``).

The requirement: the actions cover the basics – for "Projekte" at least activating the follow-up, for "Servicefälle"
the follow-up, a change of status and the responsible person.
"""

from __future__ import annotations

import datetime

from django.core.exceptions import ValidationError
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module
from rentalars.projects import bulk, service_cases
from rentalars.projects.models import CaseStatus, Project
from tests.api.base import API, ApiTestCase
from tests.helpers import make_customer, make_project, make_user
from tests.ui.base import UiTestCase

DAY = datetime.date(2027, 3, 1)


def reader(name: str = "rita"):
    """A user who may read projects and their service cases, not write them."""
    user = make_user(name)
    user.roles.add(Role.objects.create(name=f"Leser {name}", module_levels={Module.PROJECTS: int(Level.READ)}))
    return user


def case(name: str, **fields) -> Project:
    """A service case of a new customer."""
    return service_cases.create_case(name=name, customer=make_customer(f"Kunde {name}"), **fields)


class BulkServiceTests(UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.rights = self.admin_user.rights
        self.one = make_project("Eins")
        self.two = make_project("Zwei")
        self.case_a = case("Spot defekt")
        self.case_b = case("Nebel stinkt")

    def change(self, ids, action, **values):
        return bulk.change(ids, action, rights=self.rights, user=self.admin_user, values=values)

    def test_the_follow_up_is_set_on_every_project(self) -> None:
        result = self.change(
            [self.one.pk, self.two.pk],
            "follow_up",
            on=DAY,
            at=datetime.time(9, 30),
            note="Nachfassen",
            user=self.admin_user,
        )
        self.assertEqual(sorted(result.changed_ids), sorted([self.one.pk, self.two.pk]))
        for project in (self.one, self.two):
            project.refresh_from_db()
            self.assertEqual((project.follow_up_on, project.follow_up_note), (DAY, "Nachfassen"))
            self.assertEqual(project.follow_up_user, self.admin_user)
        again = self.change(
            [self.one.pk], "follow_up", on=DAY, at=datetime.time(9, 30), note="Nachfassen", user=self.admin_user
        )
        self.assertEqual((again.changed, [p.pk for p in again.unchanged]), ([], [self.one.pk]))

    def test_the_follow_up_is_taken_off(self) -> None:
        self.change([self.one.pk], "follow_up", on=DAY, user=self.admin_user)
        result = self.change([self.one.pk, self.two.pk], "clear_follow_up")
        self.assertEqual(result.changed_ids, [self.one.pk])  # the second had none
        self.assertEqual([p.pk for p in result.unchanged], [self.two.pk])
        self.one.refresh_from_db()
        self.assertIsNone(self.one.follow_up_on)

    def test_a_missing_value_is_refused_before_anything_changes(self) -> None:
        with self.assertRaises(ValidationError):
            self.change([self.one.pk], "follow_up", user=self.admin_user)  # no day
        with self.assertRaises(ValidationError):
            self.change([], "follow_up", on=DAY, user=self.admin_user)
        with self.assertRaises(ValidationError):
            self.change([self.one.pk], "nonsense")
        with self.assertRaises(ValidationError):  # status is for service cases
            self.change([self.one.pk], "status", status="done")
        with self.assertRaises(ValidationError):
            self.change(range(1, bulk.MAX_PROJECTS + 5), "clear_follow_up")
        self.one.refresh_from_db()
        self.assertIsNone(self.one.follow_up_on)

    def test_the_status_of_service_cases_with_and_without_a_follow_up(self) -> None:
        done = bulk.change(
            [self.case_a.pk, self.case_b.pk], "status", rights=self.rights, user=self.admin_user,
            cases_only=True, values={"status": CaseStatus.DONE},
        )  # fmt: skip
        self.assertEqual(len(done.changed), 2)
        self.case_a.refresh_from_db()
        self.assertEqual(self.case_a.case_status, CaseStatus.DONE)
        # "waiting" needs the follow-up and what it waits for: refused once for all, nothing changed.
        with self.assertRaises(ValidationError) as caught:
            bulk.change(
                [self.case_a.pk], "status", rights=self.rights, user=self.admin_user,
                cases_only=True, values={"status": CaseStatus.WAITING},
            )  # fmt: skip
        self.assertEqual(set(caught.exception.message_dict), {"follow_up_on", "case_waiting_for"})
        waiting = bulk.change(
            [self.case_a.pk], "status", rights=self.rights, user=self.admin_user, cases_only=True,
            values={"status": CaseStatus.WAITING, "waiting_for": "reply", "on": DAY, "user": self.admin_user},
        )  # fmt: skip
        self.assertEqual(waiting.changed_ids, [self.case_a.pk])
        self.case_a.refresh_from_db()
        self.assertEqual((self.case_a.case_status, self.case_a.follow_up_on), (CaseStatus.WAITING, DAY))

    def test_a_project_is_skipped_by_a_case_action_and_an_unknown_key_is_named(self) -> None:
        result = bulk.change(
            [self.one.pk, 99999, self.case_a.pk], "manager", rights=self.rights, user=self.admin_user,
            cases_only=True, values={"manager": self.admin_user},
        )  # fmt: skip
        self.assertEqual(result.changed_ids, [self.case_a.pk])
        self.assertEqual({s.key: s.reason for s in result.skipped}.keys(), {self.one.pk, 99999})
        self.case_a.refresh_from_db()
        self.assertEqual(self.case_a.manager, self.admin_user)

    def test_who_may_not_change_a_project_gets_it_named_as_skipped(self) -> None:
        person = reader()
        self.change([self.one.pk], "follow_up", on=DAY, user=self.admin_user)
        result = bulk.change([self.one.pk], "clear_follow_up", rights=person.rights, user=person, values={})
        self.assertEqual(result.changed, [])
        self.assertEqual(len(result.skipped), 1)


class BulkPagesTests(UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.one = make_project("Eins")
        self.two = make_project("Zwei")
        self.case_a = case("Spot defekt")

    def test_the_list_of_projects_offers_the_follow_up(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:list")))
        self.assertIn('data-bulk-bar="sel_projects"', page)
        self.assertIn(f'name="sel_projects" value="{self.one.pk}"', page)
        self.assertIn("Wiedervorlage setzen", page)
        self.assertIn(reverse("projects:bulk_projects"), page)

    def test_the_follow_up_is_set_from_the_list(self) -> None:
        response = self.client.post(
            reverse("projects:bulk_projects"),
            {
                "table": "projects",
                "next": reverse("projects:list"),
                "sel_projects": [self.one.pk, self.two.pk],
                "action": "follow_up",
                "follow_up_on": "2027-03-01",
                "follow_up_note": "Angebot nachfassen",
            },
        )
        self.assertRedirects(response, reverse("projects:list"), fetch_redirect_response=False)
        self.one.refresh_from_db()
        self.assertEqual((self.one.follow_up_on, self.one.follow_up_user), (DAY, self.admin_user))
        texts = self.messages_of(self.client.get(reverse("projects:list")))
        self.assertTrue(any("2 geändert" in text for text in texts), texts)

    def test_nothing_ticked_and_a_missing_day_say_so(self) -> None:
        url = reverse("projects:bulk_projects")
        base = {
            "table": "projects",
            "next": reverse("projects:list"),
            "action": "follow_up",
            "follow_up_on": "2027-03-01",
        }
        self.client.post(url, base)
        self.assertTrue(
            any("mindestens eine Zeile" in t for t in self.messages_of(self.client.get(reverse("projects:list"))))
        )
        self.client.post(url, {**base, "sel_projects": [self.one.pk], "follow_up_on": ""})
        self.assertTrue(any("Tag" in t for t in self.messages_of(self.client.get(reverse("projects:list")))))
        self.one.refresh_from_db()
        self.assertIsNone(self.one.follow_up_on)

    def test_the_list_of_cases_offers_follow_up_status_and_person(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:cases")))
        for text in ("Status setzen", "Wiedervorlage setzen", "Zuständige setzen", "Auswahl als CSV herunterladen"):
            self.assertIn(text, page)

    def test_status_and_person_are_set_from_the_list_of_cases(self) -> None:
        url = reverse("projects:bulk_cases")
        common = {"table": "service_cases", "next": reverse("projects:cases"), "sel_service_cases": [self.case_a.pk]}
        self.client.post(url, {**common, "action": "status", "case_status": "in_progress"})
        self.client.post(url, {**common, "action": "manager", "manager": self.admin_user.pk})
        self.case_a.refresh_from_db()
        self.assertEqual((self.case_a.case_status, self.case_a.manager), ("in_progress", self.admin_user))

    def test_the_endpoints_refuse_a_foreign_table_and_a_reader(self) -> None:
        self.assertEqual(
            self.client.post(
                reverse("projects:bulk_projects"), {"table": "customers", "action": "follow_up"}
            ).status_code,
            403,
        )
        person_user = reader()
        person = self.browser_of(person_user)
        self.assertEqual(person.post(reverse("projects:bulk_projects"), {"table": "projects"}).status_code, 403)
        # Service cases: everybody who is a person may work on the cases of their own – the service decides per case.
        asked = person.post(
            reverse("projects:bulk_cases"),
            {
                "table": "service_cases",
                "sel_service_cases": [self.case_a.pk],
                "action": "manager",
                "manager": person_user.pk,
            },
        )
        self.assertEqual(asked.status_code, 302)
        self.case_a.refresh_from_db()
        self.assertNotEqual(self.case_a.manager, person_user)
        page = self.assert_ok(person.get(reverse("projects:list")))
        self.assertNotIn("Wiedervorlage setzen", page)  # no actions without writing – the CSV remains
        self.assertIn("Auswahl als CSV herunterladen", page)


class BulkApiTests(ApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.one = make_project("Eins")
        self.case_a = case("Spot defekt")

    def test_the_follow_up_of_projects(self) -> None:
        response = self.admin.post(
            f"{API}/projects/bulk",
            {"ids": [self.one.pk, 99999], "action": "follow_up", "follow_up_on": "2027-03-01", "follow_up_note": "x"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual((body["changed"], [s["project"] for s in body["skipped"]]), ([self.one.pk], [99999]))
        self.one.refresh_from_db()
        self.assertEqual(self.one.follow_up_on, DAY)
        cleared = self.admin.post(
            f"{API}/projects/bulk", {"ids": [self.one.pk], "action": "clear_follow_up"}, format="json"
        )
        self.assertEqual(cleared.json()["changed"], [self.one.pk])
        # Status is for service cases only.
        refused = self.admin.post(f"{API}/projects/bulk", {"ids": [self.one.pk], "action": "status"}, format="json")
        self.assertEqual(refused.status_code, 400)

    def test_status_and_manager_of_service_cases(self) -> None:
        status = self.admin.post(
            f"{API}/service-cases/bulk",
            {"ids": [self.case_a.pk, self.one.pk], "action": "status", "status": "done"},
            format="json",
        )
        self.assertEqual(status.status_code, 200, status.content)
        self.assertEqual(status.json()["changed"], [self.case_a.pk])
        self.assertEqual([s["project"] for s in status.json()["skipped"]], [self.one.pk])  # a project, not a case
        manager = self.admin.post(
            f"{API}/service-cases/bulk",
            {"ids": [self.case_a.pk], "action": "manager", "manager": self.admin_user.pk},
            format="json",
        )
        self.assertEqual(manager.json()["changed"], [self.case_a.pk])

    def test_bad_requests_and_missing_rights(self) -> None:
        self.assertEqual(
            self.admin.post(f"{API}/projects/bulk", {"ids": [], "action": "follow_up"}, format="json").status_code, 400
        )
        self.assertEqual(
            self.admin.post(
                f"{API}/projects/bulk", {"ids": [self.one.pk], "action": "follow_up"}, format="json"
            ).status_code,
            400,
        )
        person = self.client_of(reader())
        self.assertEqual(
            person.post(
                f"{API}/projects/bulk", {"ids": [self.one.pk], "action": "clear_follow_up"}, format="json"
            ).status_code,
            403,
        )
        # Service cases: whoever works on cases may call it (AUT-033, as in the browser); the service decides per case.
        answer = person.post(f"{API}/service-cases/bulk", {"ids": [1], "action": "clear_follow_up"}, format="json")
        self.assertEqual((answer.status_code, answer.json()["changed"]), (200, []))
        read_only = self.client_of(reader("rolf"), read_only=True)
        self.assertEqual(
            read_only.post(
                f"{API}/service-cases/bulk", {"ids": [1], "action": "clear_follow_up"}, format="json"
            ).status_code,
            403,
        )
