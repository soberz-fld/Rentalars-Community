# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the phases: the kinds of phases (PRJ-092), the list of phases of the crew forms with
"New phase …" (PRJ-094) and the project template "Dry Hire" (PRJ-095)."""

from __future__ import annotations

import datetime

from django.utils import translation

from rentalars.core.demo import create_demo_data
from rentalars.core.setup import complete_setup
from rentalars.projects import course
from rentalars.projects.defaults import (
    DRY_HIRE_DESCRIPTION,
    DRY_HIRE_NAME,
    dry_hire_content,
    install_dry_hire_template,
)
from rentalars.projects.forms import CrewAddForm, CrewLineForm
from rentalars.projects.models import CrewLine, PhaseKind, Project, ProjectStatus, ProjectTemplate
from rentalars.projects.project_templates import apply_template
from rentalars.schedule.services import day_range, project_timeline
from tests.helpers import ALL_RIGHTS, RentalarsTestCase, at, job_function, make_project, plan

HOUR = datetime.timedelta(hours=1)


class PhaseKindTests(RentalarsTestCase):
    """PRJ-092: "Planungen und Besprechungen" first, "Packen" instead of "Verladen", "Nachbereitung" after the return."""

    def test_the_kinds_in_the_order_of_a_project(self) -> None:
        self.assertEqual(
            PhaseKind.values,
            [
                "planning",
                "loading",
                "travel",
                "setup",
                "rehearsal",
                "event",
                "teardown",
                "return",
                "aftercare",
                "cleaning",
                "other",
            ],
        )

    def test_the_german_names(self) -> None:
        with translation.override("de"):
            labels = {value: str(label) for value, label in PhaseKind.choices}
            self.assertEqual(labels["planning"], "Planungen und Besprechungen")
            self.assertEqual(labels["loading"], "Packen")
            self.assertEqual(labels["aftercare"], "Nachbereitung")
            self.assertNotIn("Verladen", labels.values())
            # The loading time of a packlist is something else and keeps its name.
            self.assertEqual(translation.gettext("Loading"), "Verladen")

    def test_a_phase_of_kind_packing_keeps_its_stored_value(self) -> None:
        project = make_project()
        phase = course.add_phase(project, kind=PhaseKind.LOADING, start=at(10, 8), end=at(10, 10))
        phase.refresh_from_db()
        self.assertEqual(phase.kind, "loading")
        with translation.override("de"):
            self.assertEqual(phase.label, "Packen")

    def test_the_new_kinds_can_be_planned_and_lie_outside_the_rental_period(self) -> None:
        project = make_project(start=at(10, 12), end=at(12, 12))
        meeting = course.add_phase(project, kind="planning", title="Ortstermin", start=at(3, 10), end=at(3, 11))
        aftercare = course.add_phase(project, kind="aftercare", start=at(12, 13), end=at(12, 17))
        self.assertEqual(list(project.phases.all()), [meeting, aftercare])


class TimelineTests(RentalarsTestCase):
    """PRJ-092: a phase outside the rental period appears in the timeline, in the row of its project."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", start=at(22, 12), end=at(24, 12))
        self.meeting = course.add_phase(
            self.project, kind="planning", title="Ortstermin", start=at(10, 10), end=at(10, 12)
        )

    def test_a_planning_meeting_weeks_before_has_a_row(self) -> None:
        rows = project_timeline(Project.objects.all(), day_range(datetime.date(2027, 3, 8), 7))
        self.assertEqual(len(rows), 1)
        project, bars = rows[0]
        self.assertEqual(project, self.project)
        self.assertEqual([(bar.label, bar.css) for bar in bars], [("Ortstermin", "phase")])

    def test_a_week_with_neither_period_nor_phase_has_no_row(self) -> None:
        self.assertEqual(project_timeline(Project.objects.all(), day_range(datetime.date(2027, 3, 1), 7)), [])

    def test_two_queries_whatever_the_number_of_projects(self) -> None:
        for number in range(3):
            other = make_project(f"Messe {number}", start=at(22, 12), end=at(24, 12))
            course.add_phase(other, kind="aftercare", start=at(11, 8), end=at(11, 9))
        with self.assertNumQueries(2):
            rows = project_timeline(Project.objects.all(), day_range(datetime.date(2027, 3, 8), 7))
        self.assertEqual(len(rows), 4)


class DemoDataTests(RentalarsTestCase):
    """PRJ-092: the sample festival shows the course from the site visit to the follow-up work."""

    def test_the_festival_has_its_phases(self) -> None:
        create_demo_data()
        festival = Project.objects.get(name="Stadtfest Hauptbühne")
        kinds = list(festival.phases.values_list("kind", flat=True))
        self.assertEqual(kinds, ["planning", "loading", "setup", "event", "teardown", "aftercare"])
        meeting = festival.phases.get(kind="planning")
        self.assertLess(meeting.end, festival.start)
        self.assertEqual(festival.phases.get(kind="aftercare").end, festival.end)


class NewPhaseInTheListTests(RentalarsTestCase):
    """PRJ-094: the list of phases names the dialog for a new phase – only when asked to."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()

    def test_the_add_form_offers_it_when_asked(self) -> None:
        form = CrewAddForm(project=self.project, offer_new_phase=True)
        self.assertTrue(form.offers_new_phase)
        attrs = form.fields["phase"].widget.attrs
        self.assertEqual(attrs["data-new-phase-url"], f"/projects/{self.project.number}/phases/new/dialog/")
        with translation.override("de"):
            self.assertEqual(str(attrs["data-new-phase-label"]), "Neue Phase …")

    def test_not_by_default(self) -> None:
        self.assertFalse(CrewAddForm(project=self.project).offers_new_phase)
        line = plan(self.project, job_function("Stagehand", price="28.00"))
        form = CrewLineForm(line=CrewLine.objects.get(pk=line.pk), rights=ALL_RIGHTS)
        self.assertNotIn("data-new-phase-url", form.fields["phase"].widget.attrs)

    def test_the_dialog_of_a_crew_line_offers_it_when_asked(self) -> None:
        line = plan(self.project, job_function("Stagehand", price="28.00"))
        form = CrewLineForm(line=CrewLine.objects.get(pk=line.pk), rights=ALL_RIGHTS, offer_new_phase=True)
        self.assertIn("data-new-phase-url", form.fields["phase"].widget.attrs)


SETUP_DATA = {
    "company_name": "Lichtwerk",
    "username": "chef",
    "email": "chef@example.de",
    "password": "Sehr-geheimes-Passwort-42",
    "project_next": 1,
    "customer_next": 10001,
    "material_next": 1,
    "default_tax_rate": "19",
}


class DryHireTemplateTests(RentalarsTestCase):
    """PRJ-095: the template "Dry Hire" of the start data."""

    def test_the_first_run_setup_creates_it(self) -> None:
        complete_setup(dict(SETUP_DATA))
        template = ProjectTemplate.objects.get(name=DRY_HIRE_NAME)
        self.assertEqual(template.description, DRY_HIRE_DESCRIPTION)
        self.assertEqual(template.counts, {"groups": 0, "lines": 0, "crew": 0, "phases": 4, "open_items": 0})

    def test_the_setup_keeps_a_template_of_the_same_name(self) -> None:
        own = ProjectTemplate.objects.create(name="DRY HIRE (vermietung ohne personal)", description="unsere")
        complete_setup(dict(SETUP_DATA))
        self.assertEqual(list(ProjectTemplate.objects.all()), [own])
        own.refresh_from_db()
        self.assertEqual(own.description, "unsere")

    def test_installing_twice_makes_one(self) -> None:
        self.assertIsNotNone(install_dry_hire_template())
        self.assertIsNone(install_dry_hire_template())
        self.assertEqual(ProjectTemplate.objects.filter(name=DRY_HIRE_NAME).count(), 1)

    def test_no_crew_no_lines_and_four_phases(self) -> None:
        content = dry_hire_content()
        self.assertEqual((content["groups"], content["lines"], content["crew"]), ([], [], []))
        self.assertEqual(
            [(phase["kind"], phase["title"]) for phase in content["phases"]],
            [
                ("loading", ""),
                ("other", "Übergabe an den Kunden (Abholung)"),
                ("return", "Rücknahme"),
                ("aftercare", ""),
            ],
        )
        # A copy each time: changing one does not change the start data.
        content["phases"].clear()
        self.assertEqual(len(dry_hire_content()["phases"]), 4)

    def apply(self, start: datetime.datetime, end: datetime.datetime) -> Project:
        project = make_project("Verleih Müller", start=start, end=end, status=ProjectStatus.INQUIRY)
        result = apply_template(install_dry_hire_template(), project, rights=ALL_RIGHTS)
        self.assertEqual((result.lines, result.crew, result.phases, result.left_out), (0, 0, 4, []))
        project.refresh_from_db()
        return project

    def periods(self, project: Project) -> list[tuple[str, datetime.datetime, datetime.datetime]]:
        return [(phase.kind, phase.start, phase.end) for phase in project.phases.order_by("start", "id")]

    def test_a_rental_from_noon_to_noon(self) -> None:
        project = self.apply(at(10, 12), at(11, 12))
        self.assertEqual(
            self.periods(project),
            [
                ("loading", at(10, 12), at(10, 14)),
                ("other", at(10, 14), at(10, 15)),
                ("return", at(11, 9), at(11, 10)),
                ("aftercare", at(11, 10), at(11, 12)),
            ],
        )
        self.assertFalse(project.crew_lines.exists())
        self.assertFalse(project.material_lines.exists())
        self.assertIn("Der Kunde holt das Material im Lager ab", project.notes)
        self.assertEqual(set(project.phases.values_list("location", flat=True)), {"Lager"})

    def test_the_return_stays_at_the_end_of_a_longer_rental(self) -> None:
        project = self.apply(at(10, 12), at(15, 12))
        periods = self.periods(project)
        self.assertEqual(periods[1], ("other", at(10, 14), at(10, 15)))
        self.assertEqual(periods[2], ("return", at(15, 9), at(15, 10)))
        self.assertEqual(periods[3], ("aftercare", at(15, 10), at(15, 12)))

    def test_a_short_rental_cuts_the_phases_to_its_period(self) -> None:
        project = self.apply(at(10, 8), at(10, 12))
        for kind, start, end in self.periods(project):
            with self.subTest(kind=kind):
                self.assertTrue(at(10, 8) <= start < end <= at(10, 12))

    def test_notes_of_the_project_stay(self) -> None:
        project = make_project("Verleih", start=at(10, 12), end=at(11, 12), notes="Kunde zahlt bar.")
        apply_template(install_dry_hire_template(), project, rights=ALL_RIGHTS)
        project.refresh_from_db()
        self.assertEqual(project.notes, "Kunde zahlt bar.")
