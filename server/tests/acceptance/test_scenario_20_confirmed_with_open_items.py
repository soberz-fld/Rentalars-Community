# SPDX-License-Identifier: GPL-3.0-or-later
"""Acceptance scenario 20 – Bestätigt mit offenen Punkten (catalogue chapter 11)."""

from rentalars.availability.engine import AvailabilityEngine
from rentalars.projects import course
from rentalars.projects.access import readable_projects
from rentalars.projects.models import Project, ProjectStatus
from rentalars.projects.services import change_status
from tests.helpers import ALL_RIGHTS, RentalarsTestCase, add_line, make_project, make_stock, make_user


class Scenario20ConfirmedWithOpenItems(RentalarsTestCase):
    """PRJ-008, PRJ-059."""

    def setUp(self) -> None:
        super().setUp()
        self.speaker = make_stock("L-001", 6, "Topteil")
        self.project = make_project(status=ProjectStatus.OPTION)
        add_line(self.project, self.speaker, 4)
        change_status(self.project, ProjectStatus.CONFIRMED_OPEN, rights=ALL_RIGHTS)
        (self.item,) = course.add_open_items(self.project, ["Aufbauzeiten"])

    def test_the_material_is_firmly_reserved(self) -> None:
        other = make_project("Weinfest", status=ProjectStatus.OPTION)
        line = add_line(other, self.speaker, 4).line
        availability = AvailabilityEngine().line_availability(line)
        self.assertEqual(availability.shortage_total, 2)

    def test_the_project_is_in_the_overview_of_open_items(self) -> None:
        user = make_user("paula", roles=("Projektleitung",))
        listed = course.projects_with_open_items(readable_projects(ALL_RIGHTS, user))
        self.assertEqual([(project.pk, project.open_count) for project in listed], [(self.project.pk, 1)])

    def test_when_done_the_change_to_confirmed_is_suggested(self) -> None:
        self.assertFalse(course.suggests_confirmation(self.project))
        course.set_open_item_done(self.item, done=True, user=None)
        self.assertTrue(course.suggests_confirmation(self.project))
        change_status(self.project, ProjectStatus.CONFIRMED, rights=ALL_RIGHTS)
        self.assertEqual(Project.objects.get(pk=self.project.pk).status, ProjectStatus.CONFIRMED)
        self.assertFalse(course.suggests_confirmation(self.project))
