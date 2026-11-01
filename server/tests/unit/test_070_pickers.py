# SPDX-License-Identifier: GPL-3.0-or-later
"""Pickers: extending the rental period for a phase (PRJ-100) and the periods marked in the calendars (PRJ-099)."""

from __future__ import annotations

import json

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError

from rentalars.core.models import AuditLogEntry
from rentalars.projects import course, services
from rentalars.projects.models import Project, ProjectStatus
from rentalars.projects.templatetags.period_marks import form_period_marks, project_period_marks
from tests.helpers import RentalarsTestCase, add_line, at, make_project, make_stock


class RentalPeriodSuggestionTests(RentalarsTestCase):
    """PRJ-100: what is suggested after saving a phase."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(start=at(12, 12), end=at(14, 18))

    def test_a_phase_within_the_rental_period_asks_nothing(self) -> None:
        for start, end in ((at(12, 12), at(14, 18)), (at(13, 8), at(13, 20))):
            phase = course.add_phase(self.project, kind="setup", start=start, end=end)
            self.assertFalse(course.lies_outside_rental_period(phase))
            self.assertIsNone(course.rental_period_suggestion(phase))

    def test_an_earlier_start_a_later_end_or_both(self) -> None:
        for start, end, expected in (
            (at(11, 14), at(11, 20), (at(11, 14), at(14, 18))),  # setup the evening before
            (at(14, 16), at(15, 10), (at(12, 12), at(15, 10))),  # teardown into the next morning
            (at(11, 8), at(15, 8), (at(11, 8), at(15, 8))),
            (at(11, 20), at(12, 14), (at(11, 20), at(14, 18))),  # only partly outside
        ):
            with self.subTest(start=start, end=end):
                phase = course.add_phase(self.project, kind="setup", start=start, end=end)
                self.assertTrue(course.lies_outside_rental_period(phase))
                suggestion = course.rental_period_suggestion(phase)
                self.assertEqual((suggestion.start, suggestion.end), expected)
                self.assertIsNone(suggestion.blocked_by)

    def test_planning_and_meetings_never_ask(self) -> None:
        """A site visit weeks before must not block material (decided)."""
        phase = course.add_phase(self.project, kind="planning", start=at(1, 10), end=at(1, 12))
        self.assertTrue(course.lies_outside_rental_period(phase))
        self.assertIsNone(course.rental_period_suggestion(phase))
        self.assertIsNone(course.extend_rental_period(phase))
        self.project.refresh_from_db()
        self.assertEqual((self.project.start, self.project.end), (at(12, 12), at(14, 18)))

    def test_a_subproject_beyond_its_whole_project_names_the_whole_project(self) -> None:
        part = services.create_subproject(self.project, name="Bühne", start=at(13, 8), end=at(14, 12))
        inside = course.add_phase(part, kind="setup", start=at(12, 14), end=at(12, 20))
        self.assertIsNone(course.rental_period_suggestion(inside).blocked_by)
        beyond = course.add_phase(part, kind="setup", start=at(11, 14), end=at(11, 20))
        self.assertEqual(course.rental_period_suggestion(beyond).blocked_by, self.project)


class ExtendingTheRentalPeriodTests(RentalarsTestCase):
    """PRJ-100: "Extend" runs the usual checks of a changed rental period."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(start=at(12, 12), end=at(14, 18))

    def test_the_period_grows_and_lines_with_the_former_period_follow(self) -> None:
        product = make_stock("S-001", 4)
        follows = add_line(self.project, product, 1).line
        own = add_line(self.project, product, 1, start=at(13, 8), end=at(13, 20)).line
        phase = course.add_phase(self.project, kind="setup", start=at(11, 14), end=at(11, 20))
        extended = course.extend_rental_period(phase)
        self.project.refresh_from_db()
        self.assertEqual((extended.start, extended.end), (at(11, 14), at(14, 18)))
        self.assertEqual((self.project.start, self.project.end), (at(11, 14), at(14, 18)))
        follows.refresh_from_db()
        own.refresh_from_db()
        self.assertEqual((follows.start, follows.end), (at(11, 14), at(14, 18)))
        self.assertEqual((own.start, own.end), (at(13, 8), at(13, 20)))  # PRJ-011: set by hand, kept
        # Logged like any change of the project.
        entry = AuditLogEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(Project), object_id=str(self.project.pk)
        ).last()
        self.assertIn("start", entry.changes)

    def test_nothing_to_extend_within_the_period(self) -> None:
        phase = course.add_phase(self.project, kind="setup", start=at(13, 8), end=at(13, 12))
        self.assertIsNone(course.extend_rental_period(phase))

    def test_a_closed_project_refuses(self) -> None:
        phase = course.add_phase(self.project, kind="setup", start=at(11, 14), end=at(11, 20))
        Project.objects.filter(pk=self.project.pk).update(status=ProjectStatus.CLOSED)
        self.project.refresh_from_db()
        with self.assertRaises(ValidationError):
            course.extend_rental_period(phase, self.project)

    def test_a_subproject_stays_within_its_whole_project(self) -> None:
        part = services.create_subproject(self.project, name="Bühne", start=at(13, 8), end=at(14, 12))
        within = course.add_phase(part, kind="setup", start=at(12, 14), end=at(12, 20))
        course.extend_rental_period(within, part)
        part.refresh_from_db()
        self.assertEqual(part.start, at(12, 14))
        beyond = course.add_phase(part, kind="setup", start=at(11, 14), end=at(11, 20))
        with self.assertRaises(ValidationError):
            course.extend_rental_period(beyond, part)
        part.refresh_from_db()
        self.assertEqual(part.start, at(12, 14))

    def test_the_parts_of_a_whole_project_stay_inside(self) -> None:
        part = services.create_subproject(self.project, name="Bühne")
        phase = course.add_phase(self.project, kind="teardown", start=at(14, 16), end=at(15, 10))
        course.extend_rental_period(phase)
        part.refresh_from_db()
        self.project.refresh_from_db()
        self.assertEqual(self.project.end, at(15, 10))
        self.assertEqual((part.start, part.end), (at(12, 12), at(14, 18)))  # within the longer period


class PeriodMarksTests(RentalarsTestCase):
    """PRJ-099: the periods the calendars hatch."""

    def test_the_saved_periods_of_a_project(self) -> None:
        project = make_project(start=at(12, 12), end=at(14, 18))
        marks = json.loads(project_period_marks(project))
        self.assertEqual(
            marks, [{"kind": "rental", "label": "Mietzeitraum", "start": "2027-03-12T12:00", "end": "2027-03-14T18:00"}]
        )
        project.event_start, project.event_end = at(13, 10), at(13, 23)
        marks = json.loads(project_period_marks(project))
        self.assertEqual(
            marks[1],
            {"kind": "event", "label": "Veranstaltung", "start": "2027-03-13T10:00", "end": "2027-03-13T23:00"},
        )

    def test_the_project_form_names_its_fields(self) -> None:
        marks = json.loads(form_period_marks())
        self.assertEqual([mark["fields"] for mark in marks], [["start", "end"], ["event_start", "event_end"]])
        self.assertEqual([mark["kind"] for mark in marks], ["rental", "event"])
