# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "projects": related projects, personnel for a phase by job function, persons dragged on the timeline.

1. PRJ-119: service cases and projects can be related to each other, with a link to the respective one; a project or
   a service case can be related to several service cases or projects.
2. PRJ-120: assigning personnel to phases asks first for job function(s), then per function for places, and then,
   as when items are created, for the persons (instead of asking for a person first and for "Plätze" below it).
   Creating a phase already allows naming job function(s) with places.
3. PRJ-121: in the time planning of a project the general period and the phases can be dragged on the timeline, and
   the persons can be as well. Changing the person changes the job function or phase along with it when the person
   is its only person.

* Related projects and cases hold both ways, are listed on the overview and the page of a case with number, name,
  kind, status and link – one the reader may not open as "Projekt 2027-0042 (kein Zugriff)" –, are linked and
  unlinked with edit access here and read access there, noted in both histories, and offered by the API
  (``/projects/{id}/relations``) and in the detail of a project or case (``related``).
* "Personal für diese Phase" asks for job functions with places, then one person per place; the open places of the
  phase are filled first. A new phase names job functions with places and gets that many open places.
* On "Zeitplanung" the crew bars are dragged; the phase whose only person is moved follows – else the open places of
  the person's job function with the same times –, as the dialog says.
"""

from __future__ import annotations

import json
from urllib.parse import urlencode

from django.core.exceptions import ValidationError
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, ProjectScope, Rights, rights_of
from rentalars.core.models import AuditLogEntry
from rentalars.notifications.models import Kind, Notification
from rentalars.projects import course, crew, logistics, relations, service_cases, services, staffing
from rentalars.projects.duplicate import duplicate_project
from rentalars.projects.models import (
    CrewLine,
    PhaseKind,
    Project,
    ProjectAccessLevel,
    ProjectMembership,
    ProjectRelation,
    ProjectStatus,
    RequestStatus,
)
from rentalars.schedule import moves
from tests.api.base import API, ApiTestCase
from tests.helpers import ALL_RIGHTS, RentalarsTestCase, at, job_function, make_person, make_project, make_user, plan
from tests.ui.base import UiTestCase, form_data
from tests.ui.test_accessibility import problems_of
from tests.unit.test_090_logistics import make_fleet


def events_of(project: Project) -> list[str]:
    """The business events in the history of a project, as their stored code and number."""
    return [
        f"{entry.event} {entry.changes.get('number', '')}".strip()
        for entry in AuditLogEntry.for_object(project).filter(event__startswith="project.").order_by("pk")
    ]


def limited_editor(username: str = "erik") -> object:
    """A user whose role edits projects – but only those assigned to them (AUT-017)."""
    Role.objects.get_or_create(
        name="Projektleitung extern",
        defaults={"module_levels": {Module.PROJECTS: int(Level.WRITE)}, "project_scope": ProjectScope.ASSIGNED},
    )
    return make_user(username, roles=("Projektleitung extern",))


def plain_planner(username: str = "pit") -> object:
    """A user who edits every project, without the right to plan outside the job functions (PER-006)."""
    Role.objects.get_or_create(name="Planung schlicht", defaults={"module_levels": {Module.PROJECTS: int(Level.WRITE)}})
    return make_user(username, roles=("Planung schlicht",))


# --- 1. Related projects and service cases ---------------------------------------------------------------------------


class RelationTestCase(RentalarsTestCase):
    """A project, a second one and a service case."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.fest = make_project("Stadtfest")
        self.gala = make_project("Firmengala", status=ProjectStatus.INQUIRY, start=at(20), end=at(21))
        self.case = service_cases.create_case(name="Beamer defekt", customer=self.fest.customer)


class RelationServiceTests(RelationTestCase):
    """Linking, unlinking, the rules and both histories."""

    def test_both_ways_stored_once_with_a_note(self) -> None:
        relation = relations.link(self.case, self.fest, note="  Reklamation   zum Stadtfest ", user=self.paula)
        self.assertEqual((relation.first, relation.second), (self.fest, self.case))  # the smaller ID first
        self.assertEqual(relation.note, "Reklamation zum Stadtfest")
        self.assertEqual(relation.created_by, self.paula)
        self.assertEqual(str(relation), f"{self.fest.number} ↔ {self.case.number}")
        relations.link(self.fest, self.gala)
        self.assertEqual(relations.related_ids(self.fest), {self.case.pk, self.gala.pk})
        self.assertEqual(relations.related_ids(self.case), {self.fest.pk})
        self.assertEqual(ProjectRelation.objects.count(), 2)
        # Both histories, with the number of the other side only.
        self.assertIn(f"project.related {self.fest.number}", events_of(self.case))
        self.assertIn(f"project.related {self.case.number}", events_of(self.fest))

    def test_refused(self) -> None:
        relations.link(self.fest, self.gala)
        with self.assertRaisesMessage(ValidationError, "ist schon verwandt"):
            relations.link(self.gala, self.fest)
        with self.assertRaisesMessage(ValidationError, "nicht mit sich selbst verwandt"):
            relations.link(self.fest, self.fest)
        part = services.create_subproject(self.fest, name="Bühne 2", start=at(10, 8), end=at(11, 8))
        with self.assertRaisesMessage(ValidationError, f"verknüpfe sein Gesamtprojekt {self.fest.number}"):
            relations.link(self.case, part)
        # A closed project can be related all the same: a complaint of today belongs to the job of last year.
        Project.objects.filter(pk=self.gala.pk).update(status=ProjectStatus.CLOSED)
        relations.link(self.case, Project.objects.get(pk=self.gala.pk))

    def test_unlink_and_delete_are_noted_on_both_sides(self) -> None:
        relation = relations.link(self.fest, self.gala)
        relations.unlink(relation, seen_from=self.gala)
        self.assertFalse(ProjectRelation.objects.exists())
        self.assertEqual(events_of(self.gala)[-1], f"project.unrelated {self.fest.number}")
        self.assertEqual(events_of(self.fest)[-1], f"project.unrelated {self.gala.number}")
        relations.link(self.fest, self.gala)
        number = self.gala.number
        services.delete_project(self.gala)  # an inquiry may be deleted
        self.assertFalse(ProjectRelation.objects.exists())
        self.assertEqual(events_of(self.fest)[-1], f"project.relation_deleted {number}")

    def test_the_history_names_the_number_only(self) -> None:
        relations.link(self.fest, self.gala)
        page = UiTestCase.client_class()
        page.force_login(make_user("chef", superuser=True))
        text = page.get(reverse("projects:history", args=[self.fest.pk])).content.decode()
        self.assertIn(f"Verwandt mit {self.gala.number}", text)
        self.assertNotIn("Firmengala", text)

    def test_converted_kept_duplicated_not_copied(self) -> None:
        relations.link(self.case, self.gala)
        project = service_cases.convert_to_project(self.case, start=at(15), end=at(16), customer=self.fest.customer)
        self.assertEqual(relations.related_ids(project), {self.gala.pk})
        copy = duplicate_project(
            self.gala,
            name="Firmengala 2028",
            start=at(20, year=2028),
            end=at(21, year=2028),
            rights=ALL_RIGHTS,
            user=self.paula,
        )
        self.assertEqual(relations.related_ids(copy), set())
        self.assertEqual(relations.related_ids(self.gala), {project.pk})

    def test_the_hidden_name(self) -> None:
        """AUT-016: a related project the reader may not open shows its number only – no name, status, note, link."""
        relations.link(self.fest, self.gala, note="Gleicher Kunde")
        erik = limited_editor()
        ProjectMembership.objects.create(project=self.fest, user=erik, level=ProjectAccessLevel.EDIT)
        (entry,) = relations.related_entries(self.fest, rights_of(erik), erik)
        self.assertFalse(entry.visible)
        self.assertEqual(entry.label, f"Projekt {self.gala.number} (kein Zugriff)")
        self.assertEqual((entry.name, entry.kind, entry.status, entry.note, entry.url), (None, None, None, "", ""))
        document = relations.entry_document(entry)
        self.assertEqual((document["project"], document["name"], document["accessible"]), (None, None, False))
        self.assertEqual(document["number"], self.gala.number)
        (full,) = relations.related_entries(self.fest, ALL_RIGHTS, self.paula)
        self.assertEqual(
            (full.label, full.kind_label, full.status_label), (f"{self.gala.number} Firmengala", "Projekt", "Anfrage")
        )
        self.assertEqual(full.url, reverse("projects:overview", args=[self.gala.pk]))  # (tab order; PRJ-125) adapted


class RelationPageTests(UiTestCase):
    """The box "Verwandt" on the overview and on the page of a case; "Verknüpfen", "Lösen", the suggestions."""

    def setUp(self) -> None:
        super().setUp()
        self.fest = make_project("Stadtfest")
        self.gala = make_project("Firmengala", start=at(20), end=at(21))
        self.case = service_cases.create_case(name="Beamer defekt", customer=self.fest.customer)
        self.overview = reverse("projects:deployment", args=[self.fest.pk])

    def test_link_from_the_overview_and_see_it_on_the_case(self) -> None:
        page = self.assert_ok(self.client.get(self.overview))
        self.assertIn('<h2 id="related-title">Verwandt</h2>', page)
        self.assertIn("Noch nichts verwandt.", page)
        self.assertIn(f'data-url="{reverse("projects:relation_suggest", args=[self.fest.pk])}"', page)
        self.assertEqual(problems_of(page), [])
        # Without the page script the number is typed in full – "2027-0003 Beamer" works as well.
        data = form_data(
            self.client.get(self.overview),
            containing="project_text",
            project_text=f"{self.case.number} Beamer",
            note="Reklamation",
        )
        response = self.client.post(reverse("projects:relation_add", args=[self.fest.pk]), data, follow=True)
        self.assertIn(f"Verwandt mit {self.case.number}.", self.messages_of(response))
        self.assertTrue(response.redirect_chain[-1][0].endswith("#related"))
        page = self.assert_ok(self.client.get(self.overview))
        self.assertIn(f'<a href="{reverse("projects:case_detail", args=[self.case.pk])}">{self.case.number}</a>', page)
        self.assertIn("Beamer defekt", page)
        self.assertIn("Servicefall", page)
        self.assertIn("Reklamation", page)
        case_page = self.assert_ok(self.client.get(reverse("projects:case_detail", args=[self.case.pk])))
        # (tab order; PRJ-125) adapted: the link opens the project on its overview.
        self.assertIn(f'<a href="{reverse("projects:overview", args=[self.fest.pk])}">Stadtfest</a>', case_page)
        self.assertIn("Bestätigt", case_page)
        self.assertEqual(problems_of(case_page), [])

    def test_link_with_the_suggestion_and_unlink(self) -> None:
        answer = json.loads(
            self.client.get(reverse("projects:relation_suggest", args=[self.case.pk]), {"q": "gala"}).content
        )
        self.assertEqual(
            answer,
            [{"id": self.gala.number, "label": f"{self.gala.number} Firmengala", "hint": self.gala.customer.name}],
        )
        self.client.post(
            reverse("projects:relation_add", args=[self.case.pk]),
            {"project_number": self.gala.number, "project_text": "Firmengala"},
        )
        relation = ProjectRelation.objects.get()
        # Related ones, the project itself and subprojects are not suggested.
        services.create_subproject(self.gala, name="Gala Teil", start=at(20, 8), end=at(20, 18))
        again = json.loads(
            self.client.get(reverse("projects:relation_suggest", args=[self.case.pk]), {"q": "gala"}).content
        )
        self.assertEqual(again, [])
        mine = json.loads(
            self.client.get(reverse("projects:relation_suggest", args=[self.case.pk]), {"q": "Beamer"}).content
        )
        self.assertEqual(mine, [])
        response = self.client.post(
            reverse("projects:relation_remove", args=[self.case.pk, relation.pk]), {"next": "/projects/x/"}, follow=True
        )
        self.assertIn(f"Nicht mehr verwandt mit {self.gala.number}.", self.messages_of(response))
        self.assertFalse(ProjectRelation.objects.exists())

    def test_errors_are_told(self) -> None:
        url = reverse("projects:relation_add", args=[self.fest.pk])
        response = self.client.post(url, {"project_text": "2099-9999"}, follow=True)
        self.assertIn(
            "Ein Projekt oder einen Servicefall mit dieser Nummer, das du sehen darfst, gibt es nicht.",
            self.messages_of(response),
        )
        response = self.client.post(url, {"project_text": self.fest.number}, follow=True)
        self.assertIn("Ein Projekt kann nicht mit sich selbst verwandt sein.", self.messages_of(response))

    def test_rights_and_the_hidden_name(self) -> None:
        """Edit access here and read access there; one that may not be opened shows its number only (AUT-016)."""
        relations.link(self.fest, self.gala, note="Gleicher Kunde")
        erik = limited_editor()
        ProjectMembership.objects.create(project=self.fest, user=erik, level=ProjectAccessLevel.EDIT)
        browser = self.browser_of(erik)
        page = self.assert_ok(browser.get(self.overview))
        self.assertIn(f"Projekt {self.gala.number} (kein Zugriff)", page)
        self.assertNotIn("Firmengala", page)
        self.assertNotIn("Gleicher Kunde", page)
        self.assertNotIn(reverse("projects:overview", args=[self.gala.pk]), page)  # (tab order; PRJ-125) adapted
        self.assertIn("Verknüpfen", page)  # erik edits the Stadtfest …
        self.assertNotIn("lösen", page)  # … but may not unlink what he cannot read
        relation = ProjectRelation.objects.get()
        self.assertEqual(
            browser.post(reverse("projects:relation_remove", args=[self.fest.pk, relation.pk])).status_code, 403
        )
        response = browser.post(
            reverse("projects:relation_add", args=[self.fest.pk]), {"project_text": self.case.number}, follow=True
        )
        self.assertIn(
            "Ein Projekt oder einen Servicefall mit dieser Nummer, das du sehen darfst, gibt es nicht.",
            self.messages_of(response),
        )
        self.assertEqual(
            json.loads(browser.get(reverse("projects:relation_suggest", args=[self.fest.pk]), {"q": "Beamer"}).content),
            [],
        )
        # Read access to the case: now he may link it and sees it.
        ProjectMembership.objects.create(project=self.case, user=erik, level=ProjectAccessLevel.READ)
        browser.post(reverse("projects:relation_add", args=[self.fest.pk]), {"project_text": self.case.number})
        self.assertEqual(relations.related_ids(self.fest), {self.gala.pk, self.case.pk})
        page = self.assert_ok(browser.get(self.overview))
        self.assertIn("Beamer defekt", page)
        # Reading the case only: the box without "Verknüpfen", and no way around it.
        case_page = self.assert_ok(browser.get(reverse("projects:case_detail", args=[self.case.pk])))
        self.assertIn("Stadtfest", case_page)
        self.assertNotIn("Verknüpfen", case_page)
        self.assertEqual(
            browser.post(
                reverse("projects:relation_add", args=[self.case.pk]), {"project_text": self.fest.number}
            ).status_code,
            403,
        )

    def test_not_with_the_deployment_view_only_nor_on_a_subproject(self) -> None:
        relations.link(self.fest, self.gala)
        freelancer = make_user("frei", roles=("Freie Kraft",))
        person = make_person("Frei Kraft", user=freelancer, rates={"Stagehand": "20.00"})
        plan(self.fest, "Stagehand", person)
        page = self.assert_ok(self.browser_of(freelancer).get(self.overview))
        self.assertNotIn("related-title", page)
        part = services.create_subproject(self.fest, name="Bühne 2", start=at(10, 8), end=at(11, 8))
        page = self.assert_ok(self.client.get(reverse("projects:deployment", args=[part.pk])))
        self.assertNotIn("related-title", page)


class RelationApiTests(ApiTestCase):
    """``/projects/{id}/relations`` – list, link, unlink – and ``related`` in the detail (companion app)."""

    def setUp(self) -> None:
        super().setUp()
        self.fest = make_project("Stadtfest")
        self.gala = make_project("Firmengala", start=at(20), end=at(21))
        self.case = service_cases.create_case(name="Beamer defekt", customer=self.fest.customer)
        self.url = f"{API}/projects/{self.fest.pk}/relations"

    def test_link_list_unlink(self) -> None:
        created = self.admin.post(self.url, {"project": self.case.pk, "note": "Reklamation"}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        document = created.json()
        self.assertEqual(
            {key: document[key] for key in ("project", "number", "name", "kind", "status", "accessible", "note")},
            {
                "project": self.case.pk,
                "number": self.case.number,
                "name": "Beamer defekt",
                "kind": "service_case",
                "status": "open",
                "accessible": True,
                "note": "Reklamation",
            },
        )
        by_number = self.admin.post(self.url, {"number": self.gala.number}, format="json")
        self.assertEqual(by_number.status_code, 201, by_number.content)
        listed = self.admin.get(self.url).json()
        self.assertEqual([row["number"] for row in listed], sorted([self.case.number, self.gala.number]))
        # The other side lists it too.
        self.assertEqual(
            [row["number"] for row in self.admin.get(f"{API}/projects/{self.case.pk}/relations").json()],
            [self.fest.number],
        )
        deleted = self.admin.delete(f"{self.url}/{document['id']}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual([row["number"] for row in self.admin.get(self.url).json()], [self.gala.number])

    def test_errors(self) -> None:
        self.assert_error(self.admin.post(self.url, {}, format="json"), 400, "validation_error", "project")
        self.assert_error(self.admin.post(self.url, {"number": "2099-0001"}, format="json"), 400, "validation_error")
        self.assert_error(self.admin.post(self.url, {"project": self.fest.pk}, format="json"), 400, "validation_error")
        self.admin.post(self.url, {"project": self.gala.pk}, format="json")
        self.assert_error(self.admin.post(self.url, {"project": self.gala.pk}, format="json"), 400, "validation_error")
        self.assertEqual(self.admin.delete(f"{self.url}/999999").status_code, 404)

    def test_rights_and_the_hidden_name(self) -> None:
        relations.link(self.fest, self.gala, note="Gleicher Kunde")
        erik = limited_editor()
        ProjectMembership.objects.create(project=self.fest, user=erik, level=ProjectAccessLevel.EDIT)
        client = self.client_of(erik)
        (row,) = client.get(self.url).json()
        self.assertEqual(
            row | {"id": 0, "created_at": ""},
            {
                "id": 0,
                "project": None,
                "number": self.gala.number,
                "name": None,
                "kind": None,
                "status": None,
                "status_label": None,
                "accessible": False,
                "note": "",
                "created_at": "",
            },
        )
        relation = ProjectRelation.objects.get()
        self.assert_error(client.delete(f"{self.url}/{relation.pk}"), 403, "permission_denied")
        self.assert_error(client.post(self.url, {"project": self.case.pk}, format="json"), 400, "validation_error")
        reader = self.client_for("nora", "Nur-Lesen")
        self.assertEqual(len(reader.get(self.url).json()), 1)
        self.assertEqual(reader.post(self.url, {"project": self.case.pk}, format="json").status_code, 403)

    def test_related_in_the_detail_of_a_project_and_a_case(self) -> None:
        relations.link(self.fest, self.case)
        detail = self.admin.get(f"{API}/projects/{self.fest.pk}").json()
        self.assertEqual([row["number"] for row in detail["related"]], [self.case.number])
        case = self.admin.get(f"{API}/service-cases/{self.case.pk}").json()
        self.assertEqual([row["name"] for row in case["related"]], ["Stadtfest"])
        listed = self.admin.get(f"{API}/projects").json()
        self.assertNotIn("related", listed["results"][0])  # not in lists (NFA-014)


# --- 2. Personnel for a phase by job function; a new phase with places ----------------------------------------------


class StaffingTestCase(UiTestCase):
    """A project with the setup on 10 March, 08–16; Anna and Ben are stagehands, Lea does the light."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest")
        self.setup = course.add_phase(self.project, kind=PhaseKind.SETUP, start=at(10, 8), end=at(10, 16))
        self.hand = job_function("Stagehand", price="20.00")
        self.light = job_function("Lichttechnik", price="40.00")
        self.anna = make_person("Anna Becker", rates={"Stagehand": "18.00"})
        self.ben = make_person("Ben Hart", rates={"Stagehand": "18.00"})
        self.lea = make_person("Lea Licht", rates={"Lichttechnik": "30.00"})
        self.url = reverse("projects:phase_crew_add", args=[self.project.pk, self.setup.pk])
        self.course_page = reverse("projects:course", args=[self.project.pk])


class StaffingServiceTests(StaffingTestCase):
    """``staffing.staff_phase``: open places are filled first; more places are added; empty ones stay open."""

    def test_fill_open_places_first(self) -> None:
        open_one, open_two = crew.add_crew_lines(
            self.project, rights=ALL_RIGHTS, job_function=self.hand, count=2, phase=self.setup
        )
        self.assertEqual([(row.job_function, row.places) for row in staffing.open_rows(self.setup)], [(self.hand, 2)])
        lines = staffing.staff_phase(
            self.setup,
            [
                staffing.FunctionPlaces(self.hand, 3, [self.anna, None, self.ben]),
                staffing.FunctionPlaces(self.light, 1, [self.lea]),
            ],
            rights=ALL_RIGHTS,
            firm=True,
        )
        self.assertEqual([line.pk for line in lines[:2]], [open_one.pk, open_two.pk])  # filled, not planned twice
        lines_of_phase = CrewLine.objects.filter(phase=self.setup)
        self.assertEqual(lines_of_phase.count(), 4)
        self.assertEqual(
            sorted((line.job_function.name, line.person.name if line.person else "") for line in lines_of_phase),
            [("Lichttechnik", "Lea Licht"), ("Stagehand", ""), ("Stagehand", "Anna Becker"), ("Stagehand", "Ben Hart")],
        )
        for line in lines_of_phase:
            self.assertEqual((line.start, line.end), (at(10, 8), at(10, 16)))
            if line.person_id:
                self.assertEqual(line.request_status, RequestStatus.FIRM)
                self.assertEqual(line.hourly_rate is not None, True)  # PRJ-021: the rate of the person
        # One message per person (PRJ-118).
        self.assertEqual(Notification.objects.filter(user=self.anna.user, kind=Kind.DEPLOYMENT_CHANGE).count(), 1)

    def test_open_places_the_rows_do_not_speak_for_stay(self) -> None:
        crew.add_crew_lines(self.project, rights=ALL_RIGHTS, job_function=self.hand, count=3, phase=self.setup)
        staffing.staff_phase(self.setup, [staffing.FunctionPlaces(self.hand, 1, [self.anna])], rights=ALL_RIGHTS)
        self.assertEqual(CrewLine.objects.filter(phase=self.setup).count(), 3)
        self.assertEqual(CrewLine.objects.filter(phase=self.setup, person__isnull=True).count(), 2)

    def test_rules(self) -> None:
        with self.assertRaisesMessage(ValidationError, "Anna Becker ist für Stagehand zweimal gewählt."):
            staffing.staff_phase(
                self.setup, [staffing.FunctionPlaces(self.hand, 2, [self.anna, self.anna])], rights=ALL_RIGHTS
            )
        with self.assertRaisesMessage(ValidationError, "Stagehand: mehr Personen als Plätze."):
            staffing.staff_phase(
                self.setup, [staffing.FunctionPlaces(self.hand, 1, [self.anna, self.ben])], rights=ALL_RIGHTS
            )
        with self.assertRaisesMessage(ValidationError, "Stagehand: zwischen 1 und 50 Plätzen."):
            staffing.staff_phase(self.setup, [staffing.FunctionPlaces(self.hand, 51)], rights=ALL_RIGHTS)
        with self.assertRaises(ValidationError):  # an open place is never planned firmly
            staffing.staff_phase(self.setup, [staffing.FunctionPlaces(self.hand, 2)], rights=ALL_RIGHTS, firm=True)
        # PER-006: Lea is no stagehand – refused, and nothing is planned.
        planner = Rights(module_levels={"projects": int(Level.WRITE)})
        with self.assertRaises(ValidationError):
            staffing.staff_phase(
                self.setup, [staffing.FunctionPlaces(self.hand, 2, [self.anna, self.lea])], rights=planner
            )
        self.assertFalse(CrewLine.objects.exists())

    def test_hints(self) -> None:
        other = make_project("Messe", start=at(10), end=at(11))
        plan(other, "Stagehand", self.ben, start=at(10, 9), end=at(10, 12))
        hints = staffing.person_hints(self.setup, self.hand, [self.anna, self.ben])
        self.assertEqual(hints[self.anna.pk], "")
        self.assertIn(f"Auch in Projekt {other.number} eingeplant", hints[self.ben.pk])


class StaffingDialogTests(StaffingTestCase):
    """The dialog: rows first, then one type-ahead per place; without the page script two steps with lists."""

    def test_the_dialog_starts_with_the_open_places(self) -> None:
        crew.add_crew_lines(self.project, rights=ALL_RIGHTS, job_function=self.hand, count=2, phase=self.setup)
        dialog = self.assert_ok(self.htmx("get", self.url))
        self.assertIn("Personal für Aufbau", dialog)
        self.assertIn("1. Funktionen und Plätze", dialog)
        self.assertIn(f'<option value="{self.hand.pk}" selected>Stagehand</option>', dialog)
        self.assertIn('name="places_0" value="2"', dialog)
        self.assertIn("Stagehand – 2 Plätze", dialog)
        self.assertIn(
            f'data-url="/projects/{self.project.number}/phases/{self.setup.pk}/people/?function={self.hand.pk}"', dialog
        )
        self.assertIn('name="person_0_1_text"', dialog)
        self.assertNotIn('name="person_0_2_text"', dialog)
        self.assertIn("Weiter zu den Personen", dialog)  # in <noscript> and as the default button
        self.assertEqual(problems_of(self.assert_ok(self.client.get(self.url))), [])  # the same form as a page

    def test_the_places_follow_the_rows(self) -> None:
        dialog = self.htmx("get", self.url)
        self.assertNotIn("2. Personen", self.assert_ok(dialog))  # no open places: one empty row
        data = form_data(dialog, function_0=str(self.light.pk), places_0="3", refresh="1")
        answer = self.assert_ok(self.htmx("post", self.url, data))
        self.assertIn("Lichttechnik – 3 Plätze", answer)
        self.assertIn('id="staff-person_0_2"', answer)
        self.assertFalse(CrewLine.objects.exists())
        # "Weitere Funktion" and "Entfernen": one row more, one less – the people move up with their row.
        data = form_data(dialog, function_0=str(self.light.pk), places_0="1", person_0_0=str(self.lea.pk), add_row="1")
        answer = self.htmx("post", self.url, data)
        self.assertIn('name="function_1"', self.assert_ok(answer))
        data = form_data(
            answer, function_1=str(self.hand.pk), places_1="2", person_1_1=str(self.ben.pk), remove_row="0"
        )
        data.pop("add_row", None)
        answer = self.assert_ok(self.htmx("post", self.url, data))
        self.assertNotIn('name="function_1"', answer)
        self.assertIn("Stagehand – 2 Plätze", answer)
        self.assertIn(f'name="person_0_1" value="{self.ben.pk}"', answer)
        self.assertIn('value="Hart, Ben (Stagehand)"', answer)
        self.assertNotIn("Dieses Feld", answer)  # no error for a form only sent back

    def test_plan_in_the_dialog(self) -> None:
        crew.add_crew_lines(self.project, rights=ALL_RIGHTS, job_function=self.hand, count=1, phase=self.setup)
        dialog = self.htmx("get", self.url)
        data = form_data(dialog, places_0="2", person_0_0=str(self.anna.pk), add_row="1")
        answer = self.htmx("post", self.url, data)
        data = form_data(answer, function_1=str(self.light.pk), places_1="1", person_1_0=str(self.lea.pk), save="1")
        data.pop("add_row", None)
        response = self.htmx("post", self.url, data)
        self.assertEqual((response.status_code, response["HX-Redirect"]), (204, f"{self.course_page}#phases"))
        self.assertEqual(CrewLine.objects.filter(phase=self.setup).count(), 3)
        self.assertEqual(CrewLine.objects.filter(phase=self.setup, person__isnull=True).count(), 1)
        page = self.client.get(self.course_page)
        self.assertIn("2 Personen eingeplant.", self.messages_of(page))
        self.assertIn("1 Platz ist offen.", self.messages_of(page))

    def test_errors_in_the_dialog(self) -> None:
        dialog = self.htmx("get", self.url)
        answer = self.assert_ok(self.htmx("post", self.url, form_data(dialog, save="1")))
        self.assertIn("Wähle mindestens eine Funktion.", answer)
        data = form_data(
            dialog,
            function_0=str(self.hand.pk),
            places_0="2",
            person_0_0=str(self.anna.pk),
            person_0_1=str(self.anna.pk),
            save="1",
        )
        answer = self.assert_ok(self.htmx("post", self.url, data))
        self.assertIn("Anna Becker ist für Stagehand zweimal gewählt.", answer)
        data = form_data(dialog, function_0=str(self.hand.pk), places_0="1", person_0_0="99999", save="1")
        self.assertIn("Bitte eine gültige Auswahl treffen", self.assert_ok(self.htmx("post", self.url, data)))
        # PER-006: without the right to plan outside the job functions Lea is no stagehand.
        planner = self.browser_of(plain_planner())
        data = form_data(dialog, function_0=str(self.hand.pk), places_0="1", person_0_0=str(self.lea.pk), save="1")
        self.assertIn("Bitte eine gültige Auswahl treffen", self.assert_ok(self.htmx("post", self.url, data, planner)))
        self.assertFalse(CrewLine.objects.exists())

    def test_without_the_script_two_steps(self) -> None:
        other = make_project("Messe", start=at(10), end=at(11))
        plan(other, "Stagehand", self.ben, start=at(10, 9), end=at(10, 12))
        page = self.client.get(self.url)
        text = self.assert_ok(page)
        self.assertIn("<h1>Aufbau</h1>", text)
        self.assertIn('<noscript><button type="submit" class="btn secondary small" name="step" value="people">', text)
        step = self.client.post(self.url, form_data(page, function_0=str(self.hand.pk), places_0="2", step="people"))
        text = self.assert_ok(step)
        self.assertIn("2. Personen", text)
        self.assertIn(f'<option value="{self.anna.pk}">Becker, Anna (Stagehand)</option>', text)
        self.assertIn(f"Hart, Ben (Stagehand) – Auch in Projekt {other.number} eingeplant", text)
        # Lea is no stagehand: offered after them, marked – the administrator may plan outside the functions (PER-025).
        self.assertIn("Licht, Lea (Lichttechnik) – Stagehand gehört nicht zu den Funktionen dieser Person.", text)
        data = form_data(step, person_0_1=str(self.ben.pk), firm="on", save="1")
        data.pop("step", None)
        response = self.client.post(self.url, data)
        self.assertRedirects(response, f"{self.course_page}#phases", fetch_redirect_response=False)
        line = CrewLine.objects.get(person=self.ben, project=self.project)
        self.assertEqual((line.phase, line.request_status), (self.setup, RequestStatus.FIRM))
        self.assertEqual(CrewLine.objects.filter(phase=self.setup, person__isnull=True).count(), 1)
        warned = self.messages_of(self.client.get(self.course_page))
        self.assertTrue(any(text.startswith("Ben Hart: Auch in Projekt") for text in warned), warned)

    def test_people_while_typing(self) -> None:
        other = make_project("Messe", start=at(10), end=at(11))
        plan(other, "Stagehand", self.ben, start=at(10, 9), end=at(10, 12))
        url = reverse("projects:phase_people", args=[self.project.pk, self.setup.pk])
        planner = self.browser_of(plain_planner())
        answer = json.loads(planner.get(url, {"function": self.hand.pk, "q": "a"}).content)
        self.assertEqual([row["label"] for row in answer], ["Becker, Anna (Stagehand)", "Hart, Ben (Stagehand)"])
        self.assertEqual(answer[0]["hint"], "kein Konflikt")
        self.assertIn(f"Projekt {other.number}", answer[1]["hint"])
        self.assertEqual(json.loads(planner.get(url, {"function": self.light.pk, "q": "Anna"}).content), [])
        self.assertEqual(json.loads(planner.get(url, {"q": "Anna"}).content), [])
        # With the right to plan outside the job functions the others follow, marked (PER-025).
        labels = [
            row["label"] for row in json.loads(self.client.get(url, {"function": self.light.pk, "q": "Anna"}).content)
        ]
        self.assertEqual(labels, ["Becker, Anna (Stagehand)"])

    def test_who_may_not_plan(self) -> None:
        warehouse = self.browser_for("luka", "Lager")
        self.assertEqual(warehouse.get(self.url).status_code, 403)
        url = reverse("projects:phase_people", args=[self.project.pk, self.setup.pk])
        self.assertEqual(warehouse.get(url, {"function": self.hand.pk, "q": "a"}).status_code, 403)
        # Personnel planning reads the project and plans its crew (catalogue chapter 4).
        planner = self.browser_for("pia", "Personaldisposition")
        self.assert_ok(planner.get(self.url))


class PhaseWithPlacesTests(StaffingTestCase):
    """A new phase with rows "Funktion + Plätze" – on the page, in the dialog of the planning, in the API service."""

    def test_on_the_page(self) -> None:
        url = reverse("projects:phase_create", args=[self.project.pk])
        page = self.client.get(url)
        text = self.assert_ok(page)
        self.assertIn("Personalplätze (optional)", text)
        self.assertIn('name="function_0"', text)
        self.assertEqual(problems_of(text), [])
        data = form_data(
            page,
            kind=PhaseKind.TEARDOWN,
            start="2027-03-12T08:00",
            end="2027-03-12T12:00",
            function_0=str(self.hand.pk),
            places_0="3",
            add_row="1",
        )
        more = self.client.post(url, data)
        self.assertIn('name="function_1"', self.assert_ok(more))
        self.assertEqual(self.project.phases.count(), 1)  # not saved yet
        data = form_data(more, function_1=str(self.light.pk), places_1="1")
        data.pop("add_row", None)
        response = self.client.post(url, data, follow=True)
        self.assertIn("4 offene Plätze in der Phase eingeplant.", self.messages_of(response))
        phase = self.project.phases.get(kind=PhaseKind.TEARDOWN)
        places = CrewLine.objects.filter(phase=phase)
        self.assertEqual(places.filter(job_function=self.hand, person__isnull=True).count(), 3)
        self.assertEqual(places.filter(job_function=self.light).count(), 1)
        self.assertEqual({(line.start, line.end) for line in places}, {(at(12, 8), at(12, 12))})
        # The dialog of the phase starts with them.
        dialog = self.assert_ok(self.htmx("get", reverse("projects:phase_crew_add", args=[self.project.pk, phase.pk])))
        self.assertIn("Stagehand – 3 Plätze", dialog)
        self.assertIn("Lichttechnik – 1 Platz", dialog)

    def test_without_rows_as_before_and_the_edit_form_has_none(self) -> None:
        url = reverse("projects:phase_create", args=[self.project.pk])
        data = form_data(self.client.get(url), kind=PhaseKind.EVENT, start="2027-03-11T18:00", end="2027-03-11T23:00")
        self.client.post(url, data)
        phase = self.project.phases.get(kind=PhaseKind.EVENT)
        self.assertFalse(phase.crew_lines.exists())
        edit = self.assert_ok(self.client.get(reverse("projects:phase_edit", args=[self.project.pk, phase.pk])))
        self.assertNotIn("Personalplätze", edit)

    def test_in_the_dialog_of_the_planning(self) -> None:
        url = reverse("projects:phase_dialog", args=[self.project.pk])
        dialog = self.htmx("get", url)
        self.assertIn('id="new-phase-function_0"', self.assert_ok(dialog))
        data = form_data(
            dialog,
            kind=PhaseKind.REHEARSAL,
            start="2027-03-11T10:00",
            end="2027-03-11T12:00",
            function_0=str(self.hand.pk),
            places_0="2",
        )
        # Over the planning the new places show at once: the crew lines (not the crew form) and the totals out of band.
        planning = f"http://testserver{reverse('projects:detail', args=[self.project.pk])}"
        response = self.client.post(url, data, HTTP_HX_REQUEST="true", HTTP_HX_CURRENT_URL=planning)
        self.assertEqual(
            (response.status_code, response["HX-Reswap"], response["HX-Retarget"]),
            (200, "none", "#planning-crew-lines"),
        )
        events = json.loads(response["HX-Trigger"])
        self.assertTrue(events["planningChanged"])
        phase = self.project.phases.get(pk=events["phaseCreated"]["id"])
        self.assertEqual(phase.crew_lines.filter(person__isnull=True).count(), 2)
        text = response.content.decode()
        self.assertIn('<div id="planning-crew-lines" hx-swap-oob="true">', text)
        self.assertIn("2 Plätze offen", text)
        self.assertIn('id="planning-totals" hx-swap-oob="true"', text)
        self.assertNotIn("crew-add", text)  # the crew form that opened the dialog keeps what was typed
        # Elsewhere – no planning underneath – the answer stays as it was.
        data["kind"] = PhaseKind.TEARDOWN
        response = self.htmx("post", url, data)
        self.assertEqual(response.status_code, 204)
        self.assertNotIn("planningChanged", response["HX-Trigger"])
        # A phase that cannot be saved plans nothing.
        bad = form_data(
            dialog,
            kind=PhaseKind.REHEARSAL,
            start="2027-03-11T12:00",
            end="2027-03-11T10:00",
            function_0=str(self.hand.pk),
            places_0="2",
        )
        self.assertIn("Das Ende muss nach dem Beginn liegen", self.assert_ok(self.htmx("post", url, bad)))
        self.assertEqual(CrewLine.objects.count(), 4)


class StaffingApiTests(ApiTestCase):
    """``POST /projects/{id}/phases`` with ``places``; ``/projects/{id}/phases/{phase}/staffing``."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest")
        self.hand = job_function("Stagehand", price="20.00")
        self.anna = make_person("Anna Becker", rates={"Stagehand": "18.00"})

    def test_a_phase_with_places_and_its_staffing(self) -> None:
        created = self.admin.post(
            f"{API}/projects/{self.project.pk}/phases",
            {
                "kind": "setup",
                "start": "2027-03-10T08:00:00+01:00",
                "end": "2027-03-10T16:00:00+01:00",
                "places": [{"job_function": self.hand.pk, "places": 2}],
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        phase_id = created.json()["id"]
        self.assertEqual(len(created.json()["crew_lines"]), 2)
        url = f"{API}/projects/{self.project.pk}/phases/{phase_id}/staffing"
        start = self.admin.get(url).json()
        self.assertEqual(start["functions"], [{"job_function": self.hand.pk, "name": "Stagehand", "open_places": 2}])
        staffed = self.admin.post(
            url, {"functions": [{"job_function": self.hand.pk, "places": 3, "people": [self.anna.pk]}]}, format="json"
        )
        self.assertEqual(staffed.status_code, 201, staffed.content)
        lines = staffed.json()["crew_lines"]
        self.assertEqual([line["person"] for line in lines], [self.anna.pk, None])
        self.assertEqual(CrewLine.objects.filter(phase_id=phase_id).count(), 3)

    def test_errors_and_rights(self) -> None:
        phase = course.add_phase(self.project, kind="setup", start=at(10, 8), end=at(10, 16))
        url = f"{API}/projects/{self.project.pk}/phases/{phase.pk}/staffing"
        self.assert_error(self.admin.post(url, {"functions": []}, format="json"), 400, "validation_error", "functions")
        self.assert_error(
            self.admin.post(
                url,
                {"functions": [{"job_function": self.hand.pk, "places": 1, "people": [self.anna.pk, self.anna.pk]}]},
                format="json",
            ),
            400,
            "validation_error",
        )
        warehouse = self.client_for("luka", "Lager")
        self.assertEqual(warehouse.get(url).status_code, 403)


# --- 3. Persons dragged on the timeline of "Zeitplanung" ------------------------------------------------------------


def move_url(project: Project, **query: object) -> str:
    """The dialog of a move, as the bars of the timeline ask for it."""
    return f"{reverse('schedule:move', args=[project.pk])}?{urlencode(query)}"


class TimelineMoveTestCase(UiTestCase):
    """The setup on 10 March, 14–20, with Anna alone in it; the project from 10 to 12 March."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Firmenfeier", start=at(10, 8), end=at(12, 18))
        self.setup = course.add_phase(self.project, kind=PhaseKind.SETUP, start=at(10, 14), end=at(10, 20))
        self.anna = make_person("Anna Becker", rates={"Stagehand": "20.00"})
        self.ben = make_person("Ben Hart", rates={"Stagehand": "20.00"})
        self.line = plan(self.project, "Stagehand", self.anna, phase=self.setup, firm=True)
        self.course_page = reverse("projects:course", args=[self.project.pk])

    def move(self, line: CrewLine, start: str, end: str, **options: object) -> object:
        """ "Verschieben" in the dialog of a crew bar on "Zeitplanung"."""
        data = {"what": "crew", "line": line.pk, "start": start, "end": end, "sent": "1", "from": "course", **options}
        return self.htmx("post", reverse("schedule:move", args=[self.project.pk]), data)


class TimelinePersonBarTests(TimelineMoveTestCase):
    """The crew bars of the timeline are dragged – for whoever may change the project, in hour columns."""

    def test_person_and_open_place_bars_can_be_moved(self) -> None:
        place = plan(self.project, "Stagehand", None, start=at(11, 9), end=at(11, 12))
        page = self.assert_ok(self.client.get(self.course_page))
        self.assertIn(
            f'data-tl-move="/schedule/move/{self.project.number}/?what=crew&amp;line={self.line.pk}&amp;from=course"',
            page,
        )
        self.assertIn(f'data-tl-key="crew-{self.line.pk}"', page)
        self.assertIn('data-tl-name="Einsatz von Anna Becker als Stagehand"', page)
        self.assertIn(f'data-tl-key="crew-{place.pk}"', page)
        self.assertIn('data-tl-name="Offener Platz als Stagehand"', page)
        # The exact times stay readable for screen readers.
        self.assertIn('<span class="visually-hidden"> – Anna Becker · Stagehand · Mi 10.03.', page)
        self.assertEqual(problems_of(page), [])

    def test_not_for_readers_nor_in_weeks(self) -> None:
        reader = self.browser_for("nora", "Nur-Lesen")
        self.assertNotIn(f'data-tl-key="crew-{self.line.pk}"', self.assert_ok(reader.get(self.course_page)))
        weeks = self.assert_ok(self.client.get(self.course_page, {"weeks": "2", "from": "2027-03-08"}))
        self.assertNotIn("data-tl-move", weeks)


class TimelineFollowTests(TimelineMoveTestCase):
    """What follows a person: the phase whose only person they are – else the open places of their job function."""

    def test_the_dialog_says_what_follows(self) -> None:
        url = move_url(
            self.project,
            what="crew",
            line=self.line.pk,
            start="2027-03-10T15:00",
            end="2027-03-10T21:00",
            **{"from": "course"},
        )
        dialog = self.assert_ok(self.htmx("get", url))
        self.assertIn("Einsatz von Anna Becker als Stagehand verschieben", dialog)
        self.assertIn("Die Phase „Aufbau“ wird mitverschoben, weil Anna Becker die einzige Person darin ist.", dialog)
        self.assertIn(
            '<input type="checkbox" name="follow" aria-describedby="move-follow-help" id="move-follow" checked>', dialog
        )
        self.assertIn("Phase „Aufbau“ mitverschieben", dialog)
        self.assertIn("Aufbau: bisher Mi 10.03. 14:00 – 20:00, jetzt Mi 10.03. 15:00 – 21:00", dialog)
        self.assertIn('<input type="hidden" name="from" value="course">', dialog)
        self.assertNotIn("die Phase behält ihre Zeiten", dialog)
        # Nothing changed by asking.
        self.setup.refresh_from_db()
        self.assertEqual(self.setup.start, at(10, 14))

    def test_the_phase_follows_with_its_vehicles(self) -> None:
        fleet = make_fleet()
        van = logistics.add_vehicle_line(
            self.project, rights=ALL_RIGHTS, product=fleet["car"], item=fleet["van"], phase=self.setup
        )
        place = plan(self.project, "Lichttechnik", None, phase=self.setup)  # an open place belongs to nobody
        Notification.objects.all().delete()
        done = self.assert_ok(self.move(self.line, "2027-03-10T15:00", "2027-03-10T21:00", follow="on"))
        self.assertIn("Aufbau: jetzt Mi 10.03. 15:00 – 21:00", done)
        self.assertIn("1 Personalposition wurde mitverschoben.", done)
        self.assertIn("1 Fahrzeugbuchung wurde mit der Phase verschoben.", done)
        for record in (self.setup, self.line, van, place):
            record.refresh_from_db()
            self.assertEqual((record.start, record.end), (at(10, 15), at(10, 21)), record)
        # PRJ-118: Anna, planned firmly, is told once.
        self.assertEqual(Notification.objects.filter(user=self.anna.user, kind=Kind.DEPLOYMENT_CHANGE).count(), 1)

    def test_a_deployment_with_times_of_its_own(self) -> None:
        line = plan(self.project, "Stagehand", self.ben, start=at(11, 9), end=at(11, 13))
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, start=at(10, 16), end=at(10, 18))
        line.delete()
        # Moved as a whole by an hour: the phase moves by as much.
        self.move(self.line, "2027-03-10T17:00", "2027-03-10T19:00", follow="on")
        self.setup.refresh_from_db()
        self.line.refresh_from_db()
        self.assertEqual((self.setup.start, self.setup.end), (at(10, 15), at(10, 21)))
        self.assertEqual((self.line.start, self.line.end), (at(10, 17), at(10, 19)))
        # Only its end changed: the phase stays – and the dialog does not offer it.
        url = move_url(
            self.project,
            what="crew",
            line=self.line.pk,
            start="2027-03-10T17:00",
            end="2027-03-10T20:00",
            **{"from": "course"},
        )
        self.assertNotIn("mitverschieben", self.assert_ok(self.htmx("get", url)))
        self.move(self.line, "2027-03-10T17:00", "2027-03-10T20:00", follow="on")
        self.setup.refresh_from_db()
        self.assertEqual((self.setup.start, self.setup.end), (at(10, 15), at(10, 21)))

    def test_a_following_phase_beyond_the_rental_period_asks_to_extend(self) -> None:
        """PRJ-100 as for a phase dragged itself: the box "extend", unticked; only a tick extends the rental period."""
        url = move_url(
            self.project,
            what="crew",
            line=self.line.pk,
            start="2027-03-10T06:00",
            end="2027-03-10T12:00",
            **{"from": "course"},
        )
        dialog = self.assert_ok(self.htmx("get", url))
        self.assertIn("Die Phase liegt dann außerhalb des Mietzeitraums (Mi 10.03. 08:00 – Fr 12.03. 18:00).", dialog)
        self.assertIn("Mietzeitraum auf Mi 10.03. 06:00 – Fr 12.03. 18:00 erweitern", dialog)
        self.assertIn(
            '<input type="checkbox" name="extend" aria-describedby="move-extend-help" id="move-extend">', dialog
        )
        # Without the tick: the phase follows, outside the rental period, which stays.
        self.move(self.line, "2027-03-10T06:00", "2027-03-10T12:00", follow="on")
        self.setup.refresh_from_db()
        self.project.refresh_from_db()
        self.assertEqual((self.setup.start, self.project.start), (at(10, 6), at(10, 8)))
        # With it: the rental period is extended, as the dialog of the phase does it.
        self.move(self.line, "2027-03-10T05:00", "2027-03-10T11:00", follow="on", extend="on")
        self.project.refresh_from_db()
        self.assertEqual((self.project.start, self.project.end), (at(10, 5), at(12, 18)))

    def test_a_planning_phase_never_asks(self) -> None:
        self.setup.kind = PhaseKind.PLANNING
        self.setup.save()
        url = move_url(
            self.project,
            what="crew",
            line=self.line.pk,
            start="2027-03-10T06:00",
            end="2027-03-10T12:00",
            **{"from": "course"},
        )
        dialog = self.assert_ok(self.htmx("get", url))
        self.assertIn("mitverschoben", dialog)
        self.assertNotIn("außerhalb des Mietzeitraums", dialog)
        self.move(self.line, "2027-03-10T06:00", "2027-03-10T12:00", follow="on", extend="on")
        self.project.refresh_from_db()
        self.assertEqual(self.project.start, at(10, 8))

    def test_unticked_only_the_person_moves(self) -> None:
        self.move(self.line, "2027-03-10T15:00", "2027-03-10T21:00")  # the box sends nothing
        self.setup.refresh_from_db()
        self.line.refresh_from_db()
        self.assertEqual((self.setup.start, self.line.start), (at(10, 14), at(10, 15)))

    def test_another_person_in_the_phase_the_open_places_of_the_function_follow(self) -> None:
        plan(self.project, "Lichttechnik", self.ben, phase=self.setup)
        hand_places = crew.add_crew_lines(
            self.project, rights=ALL_RIGHTS, job_function=job_function("Stagehand"), count=2, phase=self.setup
        )
        other_times = plan(self.project, "Stagehand", None, phase=self.setup, start=at(10, 18), end=at(10, 20))
        url = move_url(
            self.project,
            what="crew",
            line=self.line.pk,
            start="2027-03-10T15:00",
            end="2027-03-10T21:00",
            **{"from": "course"},
        )
        dialog = self.assert_ok(self.htmx("get", url))
        self.assertIn("Offene Plätze als Stagehand mitverschieben", dialog)
        self.assertIn(
            "Die 2 offenen Plätze als Stagehand werden mitverschoben, weil Anna Becker dort die einzige Person dieser "
            "Funktion ist.",
            dialog,
        )
        self.move(self.line, "2027-03-10T15:00", "2027-03-10T21:00", follow="on")
        self.setup.refresh_from_db()
        self.assertEqual(self.setup.start, at(10, 14))  # Ben is in the phase too: it stays
        for place in hand_places:
            place.refresh_from_db()
            self.assertEqual((place.start, place.end), (at(10, 15), at(10, 21)))
        other_times.refresh_from_db()
        self.assertEqual(other_times.start, at(10, 18))  # other times: not the same places
        # A second stagehand among them: nothing follows.
        crew.update_crew_line(hand_places[0], rights=ALL_RIGHTS, person=self.ben)
        self.assertIsNone(moves.followers_of(CrewLine.objects.get(pk=self.line.pk)))

    def test_not_in_the_personnel_plan(self) -> None:
        """VFG-031 as before: dragged in the personnel plan, the phase keeps its times – it is not in view there."""
        url = move_url(self.project, what="crew", line=self.line.pk, start="2027-03-10T15:00", end="2027-03-10T21:00")
        dialog = self.assert_ok(self.htmx("get", url))
        self.assertIn("Der Einsatz gehört zur Phase „Aufbau“; die Phase behält ihre Zeiten.", dialog)
        self.assertNotIn('name="follow"', dialog)
        data = {
            "what": "crew",
            "line": self.line.pk,
            "start": "2027-03-10T15:00",
            "end": "2027-03-10T21:00",
            "sent": "1",
            "follow": "on",
        }
        self.htmx("post", reverse("schedule:move", args=[self.project.pk]), data)
        self.setup.refresh_from_db()
        self.assertEqual(self.setup.start, at(10, 14))

    def test_an_open_place_moves_alone(self) -> None:
        place = plan(self.project, "Stagehand", None, start=at(11, 9), end=at(11, 12))
        self.assertIsNone(moves.followers_of(place))
        self.move(place, "2027-03-11T10:00", "2027-03-11T13:00", follow="on")
        place.refresh_from_db()
        self.assertEqual(place.start, at(11, 10))


class TimelineMoveApiTests(ApiTestCase):
    """``POST /projects/{id}/reschedule`` with ``follow`` (PRJ-121); the preview names what follows."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Firmenfeier", start=at(10, 8), end=at(12, 18))
        self.setup = course.add_phase(self.project, kind=PhaseKind.SETUP, start=at(10, 14), end=at(10, 20))
        self.line = plan(
            self.project, "Stagehand", make_person("Anna Becker", rates={"Stagehand": "20.00"}), phase=self.setup
        )
        self.body = {
            "what": "crew",
            "crew_line": self.line.pk,
            "start": "2027-03-10T15:00:00+01:00",
            "end": "2027-03-10T21:00:00+01:00",
        }

    def test_preview_and_move_with_follow(self) -> None:
        url = f"{API}/projects/{self.project.pk}/reschedule"
        preview = self.admin.post(f"{url}/preview", {**self.body, "follow": True}, format="json").json()
        self.assertEqual(preview["outcome"]["followers"]["phase"], self.setup.pk)
        self.assertIn("einzige Person", preview["outcome"]["followers"]["reason"])
        self.assertEqual([change["kind"] for change in preview["outcome"]["changes"]], ["crew", "phase"])
        # Without "follow" nothing follows.
        plain = self.admin.post(f"{url}/preview", self.body, format="json").json()
        self.assertIsNone(plain["outcome"]["followers"])
        moved = self.admin.post(url, {**self.body, "follow": True}, format="json")
        self.assertEqual(moved.status_code, 200, moved.content)
        self.setup.refresh_from_db()
        self.assertEqual((self.setup.start, self.setup.end), (at(10, 15), at(10, 21)))
