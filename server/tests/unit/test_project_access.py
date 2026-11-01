# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests: who may see and change which project (AUT-016 to AUT-018, AUT-024, AUT-025)."""

from __future__ import annotations

import datetime
from types import SimpleNamespace

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils import timezone

from rentalars.accounts.models import Role, User
from rentalars.accounts.rights import Level, Module, ProjectScope, SpecialRight, rights_of
from rentalars.accounts.services import deactivate_expired_accounts
from rentalars.core.models import AuditLogEntry
from rentalars.projects.access import (
    ProjectAccess,
    access_level,
    access_of_many,
    assignment_of,
    may_plan_crew,
    module_level_in,
    packlist_project_for,
    project_for,
    readable_projects,
    visible_projects,
)
from rentalars.projects.models import Project, ProjectAccessLevel, ProjectMembership
from tests.helpers import ASSIGNED_READER, RentalarsTestCase, make_person, make_project, make_user, plan


def request_of(user: User) -> SimpleNamespace:
    """A stand-in for a request: all the access functions ask for is the user."""
    return SimpleNamespace(user=user, auth=None)


class RightsOfRolesTests(RentalarsTestCase):
    """AUT-017: a role covers all projects, or assigned projects only."""

    def test_role_for_all_projects_holds_everywhere(self) -> None:
        rights = rights_of(make_user("paula", roles=("Projektleitung",)))
        # AUT-036: project management creates and changes projects, it does not delete them.
        self.assertEqual(rights.level(Module.PROJECTS), Level.WRITE)
        self.assertEqual(rights.level_everywhere(Module.PROJECTS), Level.WRITE)
        self.assertFalse(rights.is_limited_to_assigned_projects())

    def test_role_for_assigned_projects_grants_nothing_everywhere(self) -> None:
        rights = rights_of(make_user("carla", roles=("Crew",)))
        self.assertEqual(rights.level(Module.PROJECTS), Level.READ)
        self.assertEqual(rights.level_everywhere(Module.PROJECTS), Level.NONE)
        self.assertEqual(rights.level_everywhere(Module.PACKING), Level.NONE)
        self.assertTrue(rights.is_limited_to_assigned_projects())
        # Modules that are not bound to projects are not touched by the scope.
        self.assertEqual(rights.level_everywhere(Module.TIME_TRACKING), Level.WRITE)

    def test_the_wider_role_wins_when_a_user_has_both(self) -> None:
        rights = rights_of(make_user("luka", roles=("Crew", "Lager")))
        self.assertEqual(rights.level_everywhere(Module.PROJECTS), Level.READ)
        self.assertEqual(rights.level_everywhere(Module.PACKING), Level.WRITE)
        self.assertFalse(rights.is_limited_to_assigned_projects())

    def test_a_token_narrows_both_views_of_the_rights(self) -> None:
        rights = rights_of(make_user("paula", roles=("Projektleitung",))).restricted(
            read_only=True, allowed_modules=[Module.PROJECTS]
        )
        self.assertEqual(rights.level(Module.PROJECTS), Level.READ)
        self.assertEqual(rights.level_everywhere(Module.PROJECTS), Level.READ)
        self.assertEqual(rights.level_everywhere(Module.PACKING), Level.NONE)

    def test_suggested_roles_carry_the_rights_of_stage_3(self) -> None:
        """Catalogue chapter 4: project management and personnel planning approve times."""
        for name in ("Projektleitung", "Personaldisposition"):
            rights = rights_of(make_user(name.lower(), roles=(name,)))
            self.assertTrue(rights.has(SpecialRight.APPROVE_TIMES), name)
            self.assertTrue(rights.has(SpecialRight.PLAN_ANY_JOB_FUNCTION), name)
        # AUT-031, AUT-032, AUT-036: "Crew" and "Freie Kraft" open the overview only and see no
        # availability of material; the crew reads correspondence, the freelancer nothing of the kind.
        crew = Role.objects.get(name="Crew")
        self.assertEqual(crew.project_scope, ProjectScope.DEPLOYMENT)
        self.assertEqual(crew.special_rights, [SpecialRight.CORRESPONDENCE_READ])
        freelancer = Role.objects.get(name="Freie Kraft")
        self.assertEqual(freelancer.project_scope, ProjectScope.DEPLOYMENT)
        self.assertEqual(freelancer.special_rights, [])
        self.assertEqual(
            freelancer.description, "Nur das Wichtigste: Eigene Einsätze und die Stundenerfassung, keine Projektinfos"
        )


class AccessLevelTests(RentalarsTestCase):
    """AUT-016, AUT-018, AUT-025: the level of one user in one project."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest")
        self.other = make_project("Jazznacht")
        self.freelancer = make_user("frieda", roles=(ASSIGNED_READER,))  # AUT-036
        self.person = make_person("Frieda Frei", rates={"Stagehand": "20.00"}, user=self.freelancer)

    def level(self, user: User, project: Project | None = None) -> ProjectAccess:
        return access_level(rights_of(user), user, project or self.project)

    def test_role_for_all_projects_needs_no_assignment(self) -> None:
        self.assertEqual(self.level(make_user("paula", roles=("Projektleitung",))), ProjectAccess.EDIT)
        self.assertEqual(self.level(make_user("luka", roles=("Lager",))), ProjectAccess.READ)

    def test_without_assignment_a_restricted_user_has_no_access(self) -> None:
        self.assertEqual(self.level(self.freelancer), ProjectAccess.NONE)

    def test_a_crew_line_gives_the_deployment_view_and_no_more(self) -> None:
        """AUT-018: the automatic assignment grants only the deployment view."""
        plan(self.project, "Stagehand", self.person)
        self.assertEqual(assignment_of(self.freelancer, self.project), ProjectAccess.DEPLOYMENT)
        self.assertEqual(self.level(self.freelancer), ProjectAccess.DEPLOYMENT)
        self.assertEqual(self.level(self.freelancer, self.other), ProjectAccess.NONE)

    def test_a_membership_names_its_level(self) -> None:
        ProjectMembership.objects.create(project=self.project, user=self.freelancer, level=ProjectAccessLevel.READ)
        self.assertEqual(self.level(self.freelancer), ProjectAccess.READ)

    def test_a_membership_never_gives_more_than_the_role_allows(self) -> None:
        """A role that reads assigned projects: a membership "edit" stays "read"."""
        ProjectMembership.objects.create(project=self.project, user=self.freelancer, level=ProjectAccessLevel.EDIT)
        self.assertEqual(self.level(self.freelancer), ProjectAccess.READ)

    def test_membership_and_crew_line_together_give_the_higher_level(self) -> None:
        plan(self.project, "Stagehand", self.person)
        ProjectMembership.objects.create(project=self.project, user=self.freelancer, level=ProjectAccessLevel.READ)
        self.assertEqual(self.level(self.freelancer), ProjectAccess.READ)

    def test_an_editing_role_for_assigned_projects_edits_where_it_is_member(self) -> None:
        Role.objects.create(
            name="Projektleitung extern",
            module_levels={Module.PROJECTS: int(Level.WRITE)},
            project_scope=ProjectScope.ASSIGNED,
        )
        external = make_user("erik", roles=("Projektleitung extern",))
        ProjectMembership.objects.create(project=self.project, user=external, level=ProjectAccessLevel.EDIT)
        self.assertEqual(self.level(external), ProjectAccess.EDIT)
        self.assertEqual(self.level(external, self.other), ProjectAccess.NONE)

    def test_a_user_without_the_projects_module_has_no_access_even_as_member(self) -> None:
        nobody = make_user("nora")
        ProjectMembership.objects.create(project=self.project, user=nobody, level=ProjectAccessLevel.EDIT)
        self.assertEqual(self.level(nobody), ProjectAccess.NONE)

    def test_packing_level_holds_where_the_user_is_assigned(self) -> None:
        rights = rights_of(self.freelancer)
        self.assertEqual(module_level_in(rights, self.freelancer, self.project, Module.PACKING), Level.NONE)
        plan(self.project, "Stagehand", self.person)
        self.assertEqual(module_level_in(rights, self.freelancer, self.project, Module.PACKING), Level.READ)
        self.assertEqual(module_level_in(rights, self.freelancer, self.other, Module.PACKING), Level.NONE)

    def test_levels_of_many_projects_cost_a_fixed_number_of_queries(self) -> None:
        """NFA-014: the project list asks once for all rows, not once per row."""
        plan(self.project, "Stagehand", self.person)
        third = make_project("Hochzeit")
        ProjectMembership.objects.create(project=third, user=self.freelancer, level=ProjectAccessLevel.READ)
        rights = rights_of(self.freelancer)
        ids = [self.project.pk, self.other.pk, third.pk]
        with self.assertNumQueries(4):  # the subprojects among them, the memberships, the person, the crew lines
            levels = access_of_many(rights, self.freelancer, ids)
        self.assertEqual(
            levels,
            {
                self.project.pk: ProjectAccess.DEPLOYMENT,
                self.other.pk: ProjectAccess.NONE,
                third.pk: ProjectAccess.READ,
            },
        )
        for project_id in ids:
            project = Project.objects.get(pk=project_id)
            self.assertEqual(levels[project_id], access_level(rights, self.freelancer, project))


class ProjectListsTests(RentalarsTestCase):
    """AUT-016: list, search and API show the same projects, because they ask the same function."""

    def setUp(self) -> None:
        super().setUp()
        self.planned = make_project("Stadtfest")
        self.member = make_project("Jazznacht")
        self.foreign = make_project("Hochzeit")
        self.user = make_user("frieda", roles=(ASSIGNED_READER,))  # AUT-036
        person = make_person("Frieda Frei", rates={"Stagehand": "20.00"}, user=self.user)
        plan(self.planned, "Stagehand", person)
        ProjectMembership.objects.create(project=self.member, user=self.user, level=ProjectAccessLevel.READ)

    def test_visible_are_the_assigned_projects_only(self) -> None:
        visible = visible_projects(rights_of(self.user), self.user)
        self.assertEqual(set(visible), {self.planned, self.member})

    def test_readable_excludes_projects_known_only_through_a_crew_line(self) -> None:
        """Lines and stock of a project are not part of the deployment view."""
        readable = readable_projects(rights_of(self.user), self.user)
        self.assertEqual(set(readable), {self.member})

    def test_a_role_for_all_projects_sees_all(self) -> None:
        manager = make_user("paula", roles=("Projektleitung",))
        self.assertEqual(visible_projects(rights_of(manager), manager).count(), 3)
        self.assertEqual(readable_projects(rights_of(manager), manager).count(), 3)

    def test_without_the_module_nothing_is_visible(self) -> None:
        nobody = make_user("nora")
        self.assertEqual(visible_projects(rights_of(nobody), nobody).count(), 0)

    def test_a_project_planned_twice_is_listed_once(self) -> None:
        plan(self.planned, "Stagehand", make_person("Kai Kurz", rates={"Stagehand": "18.00"}))
        plan(self.planned, "Lager", self.user.person, start=self.planned.start, end=self.planned.end)
        self.assertEqual(visible_projects(rights_of(self.user), self.user).count(), 2)


class ProjectForTests(RentalarsTestCase):
    """AUT-020: every page and endpoint gets its project from one function that asks the question."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest")
        self.user = make_user("frieda", roles=("Freie Kraft",))
        self.person = make_person("Frieda Frei", rates={"Stagehand": "20.00"}, user=self.user)

    def test_an_invisible_project_looks_like_a_missing_one(self) -> None:
        """A restricted user must not find out which project numbers exist."""
        with self.assertRaises(Http404):
            project_for(request_of(self.user), self.project.pk, ProjectAccess.DEPLOYMENT)
        with self.assertRaises(Http404):
            project_for(request_of(self.user), 999_999, ProjectAccess.DEPLOYMENT)

    def test_a_visible_project_refuses_what_is_above_the_level(self) -> None:
        plan(self.project, "Stagehand", self.person)
        project = project_for(request_of(self.user), self.project.pk, ProjectAccess.DEPLOYMENT)
        self.assertEqual(project.access, ProjectAccess.DEPLOYMENT)
        self.assertTrue(project.shows_deployment)
        self.assertFalse(project.shows_planning)
        self.assertFalse(project.shows_customer)
        self.assertFalse(project.is_editable_by_user)
        with self.assertRaises(PermissionDenied):
            project_for(request_of(self.user), self.project.pk, ProjectAccess.READ)

    def test_the_packlist_is_part_of_the_deployment_view(self) -> None:
        with self.assertRaises(Http404):
            packlist_project_for(request_of(self.user), self.project.pk)
        plan(self.project, "Stagehand", self.person)
        project = packlist_project_for(request_of(self.user), self.project.pk)
        self.assertEqual(project.packing_level, Level.READ)
        self.assertTrue(project.shows_customer)  # PRJ-122: the name in every role
        with self.assertRaises(PermissionDenied):
            packlist_project_for(request_of(self.user), self.project.pk, Level.WRITE)

    def test_a_warehouse_role_without_project_rights_still_works_on_every_packlist(self) -> None:
        Role.objects.create(name="Nur Packen", module_levels={Module.PACKING: int(Level.WRITE)})
        packer = make_user("pit", roles=("Nur Packen",))
        project = packlist_project_for(request_of(packer), self.project.pk, Level.WRITE)
        self.assertEqual(project.access, ProjectAccess.NONE)
        self.assertFalse(project.shows_deployment)
        self.assertTrue(project.shows_customer)
        with self.assertRaises(Http404):
            project_for(request_of(packer), self.project.pk, ProjectAccess.DEPLOYMENT)

    def test_crew_is_planned_by_those_who_edit_or_who_plan_personnel(self) -> None:
        manager = rights_of(make_user("paula", roles=("Projektleitung",)))
        planner = rights_of(make_user("dora", roles=("Personaldisposition",)))
        warehouse = rights_of(make_user("luka", roles=("Lager",)))
        self.assertTrue(may_plan_crew(manager, ProjectAccess.EDIT))
        self.assertTrue(may_plan_crew(planner, ProjectAccess.READ))
        self.assertFalse(may_plan_crew(warehouse, ProjectAccess.READ))
        self.assertFalse(may_plan_crew(planner, ProjectAccess.DEPLOYMENT))


class AccountExpiryTests(RentalarsTestCase):
    """AUT-024: an account can be limited in time and is deactivated when the time is up."""

    def test_account_is_usable_up_to_and_including_its_last_day(self) -> None:
        user = make_user("aushilfe", roles=("Crew",))
        user.valid_until = timezone.localdate()
        user.save()
        self.assertFalse(user.has_expired)
        self.assertFalse(user.deactivate_if_expired())
        self.assertTrue(User.objects.get(pk=user.pk).is_active)

    def test_expired_account_is_deactivated_and_the_reason_is_logged(self) -> None:
        user = make_user("aushilfe", roles=("Crew",))
        user.valid_until = timezone.localdate() - datetime.timedelta(days=1)
        user.save()
        self.assertEqual(deactivate_expired_accounts(), 1)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertTrue(AuditLogEntry.for_object(user).filter(event="user.expired").exists())
        # Running again finds nothing left to do.
        self.assertEqual(deactivate_expired_accounts(), 0)

    def test_expired_account_cannot_log_in_even_before_the_nightly_job_ran(self) -> None:
        user = make_user("aushilfe", roles=("Crew",))
        user.valid_until = timezone.localdate() - datetime.timedelta(days=1)
        user.save()
        self.assertFalse(self.client.login(username="aushilfe", password="correct horse battery staple"))
        self.assertFalse(User.objects.get(pk=user.pk).is_active)

    def test_account_without_limit_never_expires(self) -> None:
        user = make_user("anna")
        self.assertFalse(user.has_expired)
        self.assertEqual(deactivate_expired_accounts(), 0)
