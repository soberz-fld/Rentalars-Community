# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages for the phases: the kinds of phases (PRJ-092), a new phase from the crew planning (PRJ-094) and
the project template "Dry Hire" (PRJ-095)."""

from __future__ import annotations

import json
import re

from django.urls import reverse

from rentalars.core.middleware import SetupRequiredMiddleware
from rentalars.core.models import SystemSettings
from rentalars.projects import course
from rentalars.projects.defaults import DRY_HIRE_NAME, install_dry_hire_template
from rentalars.projects.models import Project, ProjectPhase, ProjectStatus, ProjectTemplate
from tests.helpers import at, job_function, make_project, plan
from tests.ui.base import UiTestCase, form_data
from tests.ui.test_setup_and_login import SETUP_ANSWERS


class KindsOfPhasesPageTests(UiTestCase):
    """PRJ-092 on the pages."""

    def test_the_form_offers_the_kinds_in_their_order(self) -> None:
        project = make_project()
        page = self.assert_ok(self.client.get(reverse("projects:phase_create", args=[project.pk])))
        select = page[page.index('name="kind"') :]
        select = select[: select.index("</select>")]
        labels = re.findall(r'<option value="\w+"(?: selected)?>([^<]+)</option>', select)
        self.assertEqual(labels[:2], ["Planungen und Besprechungen", "Packen"])
        self.assertEqual(labels[-4:], ["Rückfahrt", "Nachbereitung", "Reinigung", "Sonstiges"])
        self.assertNotIn("Verladen", select)

    def test_an_empty_course_names_the_kinds(self) -> None:
        project = make_project()
        page = self.assert_ok(self.client.get(reverse("projects:course", args=[project.pk])))
        self.assertIn("Planungen und Besprechungen, Packen, Aufbau, Veranstaltung, Abbau, Nachbereitung", page)

    def test_a_planning_meeting_and_the_follow_up_work_are_saved_and_listed(self) -> None:
        project = make_project(start=at(10, 12), end=at(12, 12))
        url = reverse("projects:phase_create", args=[project.pk])
        for kind, start, end in (
            ("planning", "2027-03-03T10:00", "2027-03-03T11:30"),
            ("aftercare", "2027-03-12T08:00", "2027-03-12T12:00"),
        ):
            data = form_data(self.client.get(url), "kind", kind=kind, start=start, end=end, title="")
            self.assertRedirects(self.client.post(url, data), reverse("projects:course", args=[project.pk]))
        page = self.assert_ok(self.client.get(reverse("projects:course", args=[project.pk])))
        self.assertLess(page.index("Planungen und Besprechungen"), page.index("Nachbereitung"))

    def test_the_timeline_shows_a_meeting_before_the_rental_period(self) -> None:
        project = make_project("Stadtfest", start=at(22, 12), end=at(24, 12))
        course.add_phase(project, kind="planning", start=at(10, 10), end=at(10, 12))
        page = self.assert_ok(self.client.get(reverse("schedule:timeline"), {"from": "2027-03-08", "weeks": 1}))
        self.assertIn(project.number, page)
        self.assertIn('class="tl-bar phase"', page)
        self.assertIn("Planungen und Besprechungen", page)


class NewPhaseFromTheCrewPlanningTests(UiTestCase):
    """PRJ-094: "New phase …" in the list of phases of the crew forms, and the dialog behind it."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", start=at(12, 8), end=at(14, 20))
        self.planning = reverse("projects:detail", args=[self.project.pk])
        self.dialog = reverse("projects:phase_dialog", args=[self.project.pk])

    def crew_block(self, text: str) -> str:
        start = text.index('id="planning-crew"')
        return text[start : text.index("</section>", start)]

    def test_the_list_names_the_dialog_for_whoever_edits_the_project(self) -> None:
        course.add_phase(self.project, kind="setup", start=at(12, 8), end=at(12, 16))
        block = self.crew_block(self.assert_ok(self.client.get(self.planning)))
        self.assertIn(f'data-new-phase-url="{self.dialog}"', block)
        self.assertIn('data-new-phase-label="Neue Phase …"', block)
        # The entry itself comes from the page script: without it nothing is offered.
        self.assertNotIn(">Neue Phase …</option>", block)

    def test_without_phases_the_list_waits_hidden_for_the_script(self) -> None:
        block = self.crew_block(self.assert_ok(self.client.get(self.planning)))
        self.assertRegex(block, r'<div class="field" data-new-phase-field hidden><label for="crew-phase">')

    def test_the_dialog_of_a_crew_line_names_it_as_well(self) -> None:
        line = plan(self.project, job_function("Stagehand", price="28.00"))
        dialog = self.assert_ok(self.htmx("get", reverse("projects:crew_edit", args=[self.project.pk, line.pk])))
        self.assertIn(f'data-new-phase-url="{self.dialog}"', dialog)

    def test_personnel_planning_without_editing_the_project_gets_no_new_phase(self) -> None:
        planner = self.browser_for("dora", "Personaldisposition")
        line = plan(self.project, job_function("Stagehand", price="28.00"))
        block = self.crew_block(self.assert_ok(planner.get(self.planning)))
        self.assertIn("crew-add", block)  # the planner plans crew …
        self.assertNotIn("data-new-phase-url", block)  # … but creates no phases
        self.assertNotIn("data-new-phase-field", block)
        dialog = self.htmx("get", reverse("projects:crew_edit", args=[self.project.pk, line.pk]), client=planner)
        self.assertNotIn("data-new-phase-url", self.assert_ok(dialog))
        self.assertIn(self.htmx("get", self.dialog, client=planner).status_code, (403, 404))
        answer = self.htmx(
            "post",
            self.dialog,
            {"kind": "setup", "start": "2027-03-12T08:00", "end": "2027-03-12T12:00"},
            client=planner,
        )
        self.assertIn(answer.status_code, (403, 404))
        self.assertFalse(ProjectPhase.objects.exists())

    def test_a_closed_project_offers_nothing(self) -> None:
        Project.objects.filter(pk=self.project.pk).update(status=ProjectStatus.CLOSED)
        self.assertNotIn("data-new-phase-url", self.assert_ok(self.client.get(self.planning)))
        answer = self.htmx(
            "post", self.dialog, {"kind": "setup", "start": "2027-03-12T08:00", "end": "2027-03-12T12:00"}
        )
        self.assertIn("abgeschlossen", self.assert_ok(answer))
        self.assertFalse(ProjectPhase.objects.exists())

    def test_the_dialog_starts_with_the_period_typed_in_the_crew_form(self) -> None:
        page = self.assert_ok(self.htmx("get", self.dialog, {"start": "2027-03-13T09:00", "end": "2027-03-13T17:00"}))
        self.assertIn('id="phase-dialog-title"', page)
        self.assertIn('hx-target="closest dialog"', page)
        self.assertIn('value="2027-03-13T09:00"', page)
        self.assertIn('value="2027-03-13T17:00"', page)
        # IDs of its own: it may stand over the dialog of a crew line with fields of the same names.
        self.assertIn('id="new-phase-kind"', page)
        self.assertNotIn('id="id_start"', page)
        self.assertNotIn('name="notes"', page)

    def test_without_a_period_or_with_a_wrong_one_it_starts_with_the_project(self) -> None:
        for query in (
            {},
            {"start": "gestern", "end": "morgen"},
            {"start": "2027-02-30T10:00", "end": "2027-02-31T12:00"},
            {"start": "2027-03-13T17:00", "end": "2027-03-13T09:00"},
        ):
            with self.subTest(query=query):
                page = self.assert_ok(self.htmx("get", self.dialog, query))
                self.assertIn('value="2027-03-12T08:00"', page)
                # PRJ-116: over several days the guess is short.
                # (phase length; PRJ-124): eight hours.
                self.assertIn('value="2027-03-12T16:00"', page)
                self.assertNotIn('value="2027-03-14T20:00"', page)

    def test_saving_names_the_new_phase(self) -> None:
        page = self.htmx("get", self.dialog)
        data = form_data(
            page,
            kind="planning",
            title="Ortstermin",
            start="2027-03-05T10:00",
            end="2027-03-05T11:30",
            location="Rathaus",
        )
        answer = self.htmx("post", self.dialog, data)
        self.assertEqual(answer.status_code, 204)
        phase = ProjectPhase.objects.get()
        self.assertEqual(
            (phase.project, phase.kind, phase.title, phase.start, phase.end, phase.location),
            (self.project, "planning", "Ortstermin", at(5, 10), at(5, 11, 30), "Rathaus"),
        )
        created = json.loads(answer["HX-Trigger"])["phaseCreated"]
        self.assertEqual(
            created,
            {
                "id": phase.pk,
                "label": "Ortstermin (Fr 05.03. 10:00 – 11:30)",
                "start": "2027-03-05T10:00",
                "end": "2027-03-05T11:30",
            },
        )
        self.assertNotIn("closeDialog", answer["HX-Trigger"])
        # The crew forms of the planning offer it from now on.
        self.assertIn(
            "Ortstermin (Fr 05.03. 10:00 – 11:30)", self.crew_block(self.client.get(self.planning).content.decode())
        )

    def test_a_mistake_is_shown_in_the_dialog(self) -> None:
        answer = self.htmx(
            "post", self.dialog, {"kind": "setup", "start": "2027-03-12T12:00", "end": "2027-03-12T08:00"}
        )
        page = self.assert_ok(answer)
        self.assertIn("has-error", page)
        self.assertIn('id="phase-dialog-title"', page)
        self.assertFalse(ProjectPhase.objects.exists())

    def test_without_the_page_script_the_address_leads_to_the_page_for_a_new_phase(self) -> None:
        self.assertRedirects(self.client.get(self.dialog), reverse("projects:phase_create", args=[self.project.pk]))

    def test_a_crew_line_planned_for_the_new_phase(self) -> None:
        stagehand = job_function("Stagehand", price="28.00")
        answer = self.htmx(
            "post",
            self.dialog,
            {"kind": "loading", "title": "", "start": "2027-03-12T08:00", "end": "2027-03-12T11:00"},
        )
        phase_id = json.loads(answer["HX-Trigger"])["phaseCreated"]["id"]
        page = self.client.get(self.planning)
        data = form_data(page, containing="job_function", job_function=stagehand.pk, phase=phase_id)
        self.htmx("post", reverse("projects:crew_add", args=[self.project.pk]), data)
        line = self.project.crew_lines.get()
        self.assertEqual((line.phase_id, line.start, line.end), (phase_id, at(12, 8), at(12, 11)))


class DryHireTemplatePageTests(UiTestCase):
    """PRJ-095: the template is there after the first-run setup and fills a new project."""

    def test_after_the_first_run_setup(self) -> None:
        system_settings = SystemSettings.load()
        system_settings.setup_completed = False
        system_settings.save()
        SetupRequiredMiddleware.reset()
        self.addCleanup(SetupRequiredMiddleware.reset)
        self.client.logout()
        token = system_settings.new_setup_token()
        page = self.client.get(reverse("core:setup"), {"token": token})
        self.client.post(reverse("core:setup"), form_data(page, **SETUP_ANSWERS))
        self.assertTrue(SystemSettings.load().setup_completed)
        templates = self.assert_ok(self.client.get(reverse("projects:templates")))
        self.assertIn(DRY_HIRE_NAME, templates)
        self.assertIn("4 Phasen", templates)

    def test_a_new_project_from_the_template(self) -> None:
        template = install_dry_hire_template()
        customer = make_project().customer
        response = self.client.get(reverse("projects:create"))
        self.assertIn(DRY_HIRE_NAME, self.assert_ok(response))
        data = form_data(
            response,
            "name",
            name="Verleih Müller",
            template=str(template.pk),
            customer=str(customer.pk),
            start="2027-04-20T12:00",
            end="2027-04-22T12:00",
        )
        self.client.post(reverse("projects:create"), data)
        project = Project.objects.get(name="Verleih Müller")
        self.assertFalse(project.crew_lines.exists())
        self.assertFalse(project.material_lines.exists())
        self.assertIn("ohne Personal", project.notes)
        page = self.assert_ok(self.client.get(reverse("projects:course", args=[project.pk])))
        for text in ("Packen", "Übergabe an den Kunden (Abholung)", "Rücknahme", "Nachbereitung"):
            self.assertIn(text, page)
        self.assertEqual(ProjectTemplate.objects.count(), 1)
