# SPDX-License-Identifier: GPL-3.0-or-later
"""Everybody with access on the tab "Zugriff" (AUT-035; AUT-016, AUT-018) – "available" from an acceptance
(PER-042; PER-016, PER-021).

The requirement: in a project the tab "Zugriff" also lists the people who have access to the project through the
assignment of a job function.

The requirement: accepting an invitation for a period in which the own calendar says "Nicht verfügbar" automatically
creates a "Verfügbar" for the period of the accepted job function.

* The tab lists members, the crew planned with an account ("eingeplant als Tontechnik") and the people of a service
  case – each with the access the pages really give (``projects.access.access_level``), found for all of them at
  once – as many queries for 15 as for 3; only members are changed.
* Accepting a request where the own calendar says "not available" enters "available" for exactly the period of the
  line – whichever way the answer comes; linked calendars, firm planning and refusals change nothing.
"""

from __future__ import annotations

import datetime

from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, ProjectScope, rights_of
from rentalars.mail import crew_answers
from rentalars.personnel import marks
from rentalars.personnel.models import AvailabilityMark, AvailabilityRepeat, AvailabilitySource, AvailabilityState
from rentalars.projects import crew, service_cases
from rentalars.projects.access import ProjectAccess, access_level
from rentalars.projects.access_rows import access_rows
from rentalars.projects.models import ProjectMembership, RequestStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import ASSIGNED_READER, RentalarsTestCase, at, make_person, make_project, make_user, plan
from tests.ui.base import UiTestCase

RED, GREEN, YELLOW = AvailabilityState.UNAVAILABLE, AvailabilityState.AVAILABLE, AvailabilityState.LIMITED


# --- Requirement 2: the tab "Zugriff" ---------------------------------------------------------------------------------


class AccessScene:
    """Stadtfest with a member, a planned crew member, a crew member who is a member too, a planned project manager,
    a planned account that is switched off and one never invited."""

    def make_scene(self) -> None:
        self.project = make_project("Stadtfest")
        self.frieda = make_user("frieda", roles=(ASSIGNED_READER,))
        make_person("Frieda Frei", user=self.frieda)
        ProjectMembership.objects.create(project=self.project, user=self.frieda, level="read")
        self.carla = make_user("carla", roles=("Crew",))
        self.carla_person = make_person("Carla Crew", user=self.carla)
        plan(self.project, "Tontechnik", self.carla_person, start=at(10, 8), end=at(10, 16))
        plan(self.project, "Stagehand", self.carla_person, start=at(11, 8), end=at(11, 16))
        self.conny = make_user("conny", roles=("Crew",))
        conny_person = make_person("Conny Crew", user=self.conny)
        plan(self.project, "Lichttechnik", conny_person, start=at(10, 8), end=at(10, 16))
        ProjectMembership.objects.create(project=self.project, user=self.conny, level="edit")
        self.paula = make_user("paula", roles=("Projektleitung",))
        plan(self.project, "Tontechnik", make_person("Paula Plan", user=self.paula), start=at(10, 8), end=at(10, 16))
        self.olaf = make_user("olaf", roles=("Crew",))
        plan(self.project, "Stagehand", make_person("Olaf Off", user=self.olaf), start=at(10, 8), end=at(10, 16))
        self.olaf.is_active = False
        self.olaf.save()
        self.nina = make_user("nina", roles=("Crew",))
        self.nina.set_unusable_password()
        self.nina.save()
        plan(self.project, "Stagehand", make_person("Nina Neu", user=self.nina), start=at(10, 8), end=at(10, 16))
        plan(self.project, "Stagehand", make_person("Ohne Konto"), start=at(10, 8), end=at(10, 16))


class AccessRowTests(AccessScene, RentalarsTestCase):
    """The rows and the access each one names – the same as the pages give."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()

    def rows(self, project: object = None) -> dict[str, object]:
        return {row.user.username: row for row in access_rows(project or self.project)}

    def test_who_and_why(self) -> None:
        rows = self.rows()
        self.assertLessEqual({"frieda", "carla", "conny", "paula", "olaf", "nina"}, set(rows))
        carla = rows["carla"]
        self.assertEqual(carla.sources, ["crew"])
        self.assertEqual(carla.reason, "eingeplant als Tontechnik, Stagehand")
        self.assertEqual(carla.access_label, "Einsatzsicht")
        self.assertTrue(carla.from_planning_only)
        self.assertEqual(carla.fixed_note, "Aus der Planung – ändert sich mit der Personalposition.")
        self.assertEqual(rows["frieda"].reason, "Mitglied: lesen")
        self.assertEqual(rows["frieda"].access_label, "lesen")
        # AUT-031: a membership "edit" gives the role "Crew" the overview only – the row says what holds.
        self.assertEqual(rows["conny"].reason, "Mitglied: bearbeiten; eingeplant als Lichttechnik")
        self.assertEqual(rows["conny"].access_label, "Einsatzsicht")
        self.assertEqual(rows["paula"].reason, "eingeplant als Tontechnik; Rolle für alle Projekte")
        self.assertEqual(rows["paula"].access_label, "bearbeiten")
        for username in ("olaf", "nina"):
            self.assertEqual(rows[username].access_label, "kein Zugang – kann sich nicht anmelden", username)

    def test_the_rows_never_disagree_with_the_pages(self) -> None:
        for row in access_rows(self.project):
            user = type(row.user).objects.get(pk=row.user.pk)
            expected = access_level(rights_of(user), user, self.project) if row.can_log_in else ProjectAccess.NONE
            self.assertEqual(row.access, expected, user.username)

    def test_service_case_people(self) -> None:
        manager = make_user("kai", roles=("Crew",))
        make_person("Kai Kurz", user=manager)
        ben_user = make_user("ben", roles=("Crew",))
        ben = make_person("Ben Bau", user=ben_user)
        case = service_cases.create_case(name="Spot flackert", manager=manager, user=self.paula)
        service_cases.add_participant(case, ben, user=self.paula)
        rows = self.rows(case)
        self.assertEqual(rows["kai"].reason, "zuständig für den Servicefall")
        self.assertEqual(rows["ben"].reason, "beteiligt am Servicefall")
        self.assertEqual({rows["kai"].access_label, rows["ben"].access_label}, {"lesen"})
        for row in rows.values():  # the same as the pages
            user = type(row.user).objects.get(pk=row.user.pk)
            self.assertEqual(row.access, access_level(rights_of(user), user, case), user.username)
        self.assertEqual(rows["ben"].fixed_note, "Aus dem Servicefall – ändert sich dort.")

    def test_a_part_names_the_members_of_the_whole_project(self) -> None:
        from rentalars.projects import services as project_services

        Role.objects.create(
            name="Bauleitung extern",
            module_levels={Module.PROJECTS: int(Level.WRITE)},
            project_scope=ProjectScope.ASSIGNED,
        )
        erik = make_user("erik", roles=("Bauleitung extern",))
        ProjectMembership.objects.create(project=self.project, user=erik, level="edit")
        part = project_services.create_subproject(self.project, name="Bühne 2", start=at(10, 8), end=at(11, 8))
        row = self.rows(part)["erik"]
        self.assertEqual(row.reason, f"Mitglied des Gesamtprojekts {self.project.number}: bearbeiten")
        self.assertEqual(row.access, ProjectAccess.EDIT)


def add_crew(project: object, count: int, first: int = 0) -> None:
    """Plan ``count`` people of the role "Crew" with accounts on the project."""
    for index in range(first, first + count):
        user = make_user(f"crew{index}", roles=("Crew",))
        plan(project, "Stagehand", make_person(f"Crew Nummer{index}", user=user), start=at(10, 8), end=at(10, 16))


class AccessQueryTests(UiTestCase):
    """No query per row: 3 or 15 crew members cost the same number of queries – the rows and the whole tab."""

    def test_rows_and_page(self) -> None:
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        project = make_project("Jazznacht")
        frieda = make_user("frieda", roles=(ASSIGNED_READER,))
        ProjectMembership.objects.create(project=project, user=frieda, level="read")
        url = reverse("projects:members", args=[project.pk])
        add_crew(project, 3)
        self.assert_ok(self.client.get(url))  # warm: settings, sessions, caches
        with CaptureQueriesContext(connection) as few_rows:
            self.assertEqual(len(access_rows(project)), 4)
        with CaptureQueriesContext(connection) as few_page:
            self.assert_ok(self.client.get(url))
        add_crew(project, 12, first=3)
        with CaptureQueriesContext(connection) as many_rows:
            self.assertEqual(len(access_rows(project)), 16)
        with CaptureQueriesContext(connection) as many_page:
            page = self.assert_ok(self.client.get(url))
        self.assertIn("Crew Nummer14", page)
        self.assertEqual(len(many_rows), len(few_rows))
        self.assertEqual(len(many_page), len(few_page))


class AccessPageTests(AccessScene, UiTestCase):
    """The tab "Zugriff"."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        self.url = reverse("projects:members", args=[self.project.pk])

    def test_one_list_with_access_and_reason(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn("Wer Zugriff hat", page)
        for text in ("Carla Crew", "eingeplant als Tontechnik, Stagehand", "Einsatzsicht", "Mitglied: lesen"):
            self.assertIn(text, page)
        # Only memberships have "entfernen": two members, two buttons.
        self.assertEqual(page.count("entfernen<span"), 2)
        self.assertIn("Mitglied hinzufügen", page)

    def test_a_reader_sees_the_list_without_changing_it(self) -> None:
        page = self.assert_ok(self.browser_of(self.frieda).get(self.url))
        self.assertIn("eingeplant als Tontechnik", page)
        self.assertNotIn("entfernen<span", page)
        self.assertNotIn("Mitglied hinzufügen", page)


class AccessApiTests(AccessScene, ApiTestCase):
    """``GET /projects/{id}/access`` – the same rows; ``/members`` stays the memberships."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()

    def test_the_rows(self) -> None:
        response = self.admin.get(f"{API}/projects/{self.project.pk}/access")
        self.assertEqual(response.status_code, 200, response.content)
        rows = {row["username"]: row for row in response.json()}
        self.assertEqual(rows["carla"]["sources"], ["crew"])
        self.assertEqual(rows["carla"]["access"], "deployment")
        self.assertEqual(rows["carla"]["job_functions"], ["Tontechnik", "Stagehand"])
        self.assertFalse(rows["carla"]["editable"])
        self.assertEqual(rows["frieda"]["sources"], ["membership"])
        self.assertTrue(rows["frieda"]["editable"])
        self.assertEqual(rows["conny"]["access"], "deployment")
        self.assertEqual(rows["conny"]["membership_level"], "edit")
        self.assertEqual(rows["olaf"]["access"], "none")
        self.assertFalse(rows["olaf"]["can_log_in"])
        members = self.admin.get(f"{API}/projects/{self.project.pk}/members").json()
        self.assertEqual({row["username"] for row in members}, {"frieda", "conny"})

    def test_the_crew_does_not_read_it(self) -> None:
        crew = self.client_of(self.carla)
        self.assert_error(crew.get(f"{API}/projects/{self.project.pk}/access"), 403, "permission_denied")
        self.assertEqual(self.client_of(self.frieda).get(f"{API}/projects/{self.project.pk}/access").status_code, 200)


# --- Requirement 3: "available" from an acceptance --------------------------------------------------------------------


class AcceptScene:
    """Anna (Crew) asked as Tontechnik on Wednesday 10 March 2027, 08:00–16:00."""

    def make_scene(self) -> None:
        self.anna_user = make_user("anna", roles=("Crew",))
        self.anna = make_person("Anna Becker", user=self.anna_user, email="anna@example.de")
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.project = make_project("Stadtfest", manager=self.paula)
        self.line = plan(self.project, "Tontechnik", self.anna, start=at(10, 8), end=at(10, 16))
        crew.request_deployment(self.line, user=self.paula)

    def own_marks(self) -> list[tuple[datetime.datetime, datetime.datetime, str]]:
        return list(
            AvailabilityMark.objects.filter(person=self.anna, source=AvailabilitySource.OWN)
            .order_by("start")
            .values_list("start", "end", "state")
        )


class AcceptServiceTests(AcceptScene, RentalarsTestCase):
    """The service: exactly the period of the line, only over "not available", whichever way."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()

    def accept(self) -> object:
        return crew.answer_deployment(self.line, accept=True, user=self.anna_user).marked_available

    def test_a_week_not_available(self) -> None:
        marks.mark_period(self.anna, at(9), at(12), RED, "Urlaub")
        mark = self.accept()
        self.assertEqual((mark.start, mark.end, mark.state), (at(10, 8), at(10, 16), GREEN))
        self.assertEqual(mark.note, f"Zugesagt: {self.project.number} Stadtfest – Tontechnik")
        self.assertEqual(mark.source, AvailabilitySource.OWN)
        self.assertEqual(
            self.own_marks(), [(at(9), at(10, 8), RED), (at(10, 8), at(10, 16), GREEN), (at(10, 16), at(12), RED)]
        )
        periods = marks.effective_periods([self.anna.pk], at(10, 8), at(10, 16))[self.anna.pk]
        self.assertEqual([period.state for period in periods], [GREEN])
        self.assertEqual(
            crew.available_text(self.line), "Für Mi 10.03. 08:00 – Mi 10.03. 16:00 ist jetzt „verfügbar“ eingetragen."
        )
        self.assertEqual(
            crew.available_text(self.line, own=False),
            "Für Mi 10.03. 08:00 – Mi 10.03. 16:00 ist bei Anna Becker jetzt „verfügbar“ eingetragen.",
        )

    def test_partly_not_available(self) -> None:
        marks.mark_period(self.anna, at(10, 12), at(10, 20), RED)
        self.accept()
        self.assertEqual(self.own_marks(), [(at(10, 8), at(10, 16), GREEN), (at(10, 16), at(10, 20), RED)])

    def test_no_overlap_changes_nothing(self) -> None:
        marks.mark_period(self.anna, at(20), at(21), RED)
        marks.mark_period(self.anna, at(10, 6), at(10, 18), YELLOW)  # "with limits" is no "not available"
        self.assertIsNone(self.accept())
        self.assertEqual(self.own_marks(), [(at(10, 6), at(10, 18), YELLOW), (at(20), at(21), RED)])
        self.assertEqual(crew.available_text(self.line), "")

    def test_a_series(self) -> None:
        series = marks.create_series(
            self.anna,
            state=RED,
            first_day=datetime.date(2027, 3, 3),  # Wednesdays
            last_day=datetime.date(2027, 3, 3),
            repeat=AvailabilityRepeat.WEEKLY,
            count=3,
        )
        self.accept()
        own = AvailabilityMark.objects.filter(person=self.anna, source=AvailabilitySource.OWN).order_by("start")
        self.assertEqual(
            [(mark.start, mark.end, mark.state, mark.series_id) for mark in own],
            [
                (at(3), at(4), RED, series.pk),
                (at(10), at(10, 8), RED, series.pk),
                (at(10, 8), at(10, 16), GREEN, None),
                (at(10, 16), at(11), RED, series.pk),
                (at(17), at(18), RED, series.pk),
            ],
        )

    def test_the_linked_calendar_is_not_changed(self) -> None:
        from rentalars.personnel.models import CalendarFeed

        feed = CalendarFeed.objects.create(person=self.anna, url="https://cal.example/anna.ics")
        AvailabilityMark.objects.create(
            person=self.anna, start=at(10, 7), end=at(10, 17), state=RED, source=AvailabilitySource.FEED, feed=feed
        )
        self.assertIsNone(self.accept())  # a busy time of a linked calendar is not the own calendar
        self.assertEqual(AvailabilityMark.objects.filter(source=AvailabilitySource.FEED).count(), 1)
        marks.mark_period(self.anna, at(10), at(11), RED)
        self.line.request_status = RequestStatus.REQUESTED
        self.line.save()
        self.accept()
        busy = AvailabilityMark.objects.get(source=AvailabilitySource.FEED)
        self.assertEqual((busy.start, busy.end, busy.state), (at(10, 7), at(10, 17), RED))

    def test_declining_and_firm_planning_change_nothing(self) -> None:
        marks.mark_period(self.anna, at(9), at(12), RED)
        crew.answer_deployment(self.line, accept=False, user=self.anna_user)
        self.assertIsNone(self.line.marked_available)
        firm = plan(self.project, "Stagehand", self.anna, start=at(11, 8), end=at(11, 16), firm=True)
        self.assertEqual(firm.request_status, RequestStatus.FIRM)
        self.assertEqual(self.own_marks(), [(at(9), at(12), RED)])

    def test_the_reply_mail_says_it(self) -> None:
        marks.mark_period(self.anna, at(9), at(12), RED)
        self.accept()
        reply = crew_answers.reply_message(
            self.anna, self.line, accept=True, reason="", note="", sender="anna@example.de"
        )
        self.assertIn("ist jetzt „verfügbar“ eingetragen", reply.body)


class AcceptPageTests(AcceptScene, UiTestCase):
    """The confirmation on the page – the person, or a planner who enters the answer."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        marks.mark_period(self.anna, at(9), at(12), RED)
        self.url = reverse("projects:crew_answer", args=[self.project, self.line.pk])

    def test_the_person_accepts(self) -> None:
        done = self.browser_of(self.anna_user).post(self.url, {"answer": "accept"}, follow=True)
        texts = " ".join(self.messages_of(done))
        self.assertIn("Für Mi 10.03. 08:00 – Mi 10.03. 16:00 ist jetzt „verfügbar“ eingetragen.", texts)
        self.assertIn((at(10, 8), at(10, 16), GREEN), self.own_marks())

    def test_a_planner_enters_it(self) -> None:
        done = self.browser_of(self.paula).post(self.url, {"answer": "accept"}, follow=True)
        self.assertIn("ist bei Anna Becker jetzt „verfügbar“ eingetragen", " ".join(self.messages_of(done)))


class AcceptApiTests(AcceptScene, ApiTestCase):
    """The answer through the API – the companion app – says what was entered."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()

    def test_answer(self) -> None:
        marks.mark_period(self.anna, at(9), at(12), RED)
        url = f"{API}/projects/{self.project.pk}/crew-lines/{self.line.pk}/answer"
        response = self.client_of(self.anna_user).post(url, {"accept": True}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["availability_marked"]["state"], "available")
        self.assertEqual(body["message"], "Für Mi 10.03. 08:00 – Mi 10.03. 16:00 ist jetzt „verfügbar“ eingetragen.")

    def test_answer_without_anything_to_enter(self) -> None:
        url = f"{API}/projects/{self.project.pk}/crew-lines/{self.line.pk}/answer"
        body = self.client_of(self.anna_user).post(url, {"accept": True}, format="json").json()
        self.assertEqual((body["availability_marked"], body["message"]), (None, ""))
