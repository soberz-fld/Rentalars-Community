# SPDX-License-Identifier: GPL-3.0-or-later
"""Who reaches one project, and why – the tab "Zugriff" (AUT-035; AUT-016, AUT-018, AUT-025).

The requirement: the access list of a project also shows the people who have access through the assignment of a function.

One row per user who is assigned to the project in any way:

* a **membership** of the project – the only rows that are changed here;
* a membership of the **whole project** that holds in this part (PRJ-049);
* a **crew line** of the user's person – "eingeplant als Tontechnik" (AUT-018);
* in a service case: the **person responsible** and the people **taking part** (PRJ-108, AUT-033).

Each row names the access the user *really* has in this project – by the rules of
``projects.access.access_level``, the function every page and endpoint asks, with the user's own rights, for all
listed users at once (``access_of_users``; the tests compare the two) – and why. A role for all projects is named as a reason where it gives more than the assignment; an account that
cannot log in – deactivated, past its "valid until", without a password (``accounts.data_access.can_log_in``) – has
no access, whatever it is assigned to. Rows from the planning or the case cannot be changed
here: they change with the crew line or the case.

Users whose role covers all projects and who are not assigned are not listed, as before: they need no entry.

The API delivers the same rows: ``GET /projects/{id}/access`` (:class:`ProjectAccessListView`); the members
alone stay ``/projects/{id}/members``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, ClassVar

from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.data_access import can_log_in
from rentalars.accounts.models import User
from rentalars.accounts.rights import Level, Module, rights_of
from rentalars.api.views import ModuleAPIView
from rentalars.projects.access import ProjectAccess, access_of_users, project_for
from rentalars.projects.models import Project, ProjectAccessLevel, ProjectMembership

#: The access as the API names it – the values of the membership levels.
ACCESS_KEYS = {
    ProjectAccess.NONE: ProjectAccessLevel.NONE.value,
    ProjectAccess.DEPLOYMENT: ProjectAccessLevel.DEPLOYMENT.value,
    ProjectAccess.READ: ProjectAccessLevel.READ.value,
    ProjectAccess.EDIT: ProjectAccessLevel.EDIT.value,
}

#: Where a row comes from, in the order the reasons are named.
SOURCES = ("membership", "inherited", "crew", "case_manager", "case_participant", "role")


@dataclass
class AccessRow:
    """One user with access to the project: from where, and the access that holds (AUT-035)."""

    user: User
    #: The membership of this project, if any – the only thing changed on the tab.
    membership: ProjectMembership | None = None
    #: The membership of the whole project that holds here (PRJ-049).
    inherited: ProjectMembership | None = None
    #: The job functions of the user's crew lines in the project, and the lines.
    job_functions: list[str] = field(default_factory=list)
    crew_lines: list[int] = field(default_factory=list)
    is_case_manager: bool = False
    is_case_participant: bool = False
    #: Set by :func:`access_rows`.
    access: ProjectAccess = ProjectAccess.NONE
    by_role: bool = False
    can_log_in: bool = True

    @property
    def name(self) -> str:
        """The name of the user as lists show it."""
        return str(self.user)

    @property
    def sources(self) -> list[str]:
        """Where the row comes from (:data:`SOURCES`)."""
        found = []
        if self.membership is not None:
            found.append("membership")
        if self.inherited is not None:
            found.append("inherited")
        if self.job_functions:
            found.append("crew")
        if self.is_case_manager:
            found.append("case_manager")
        if self.is_case_participant:
            found.append("case_participant")
        if self.by_role:
            found.append("role")
        return found

    @property
    def from_planning_only(self) -> bool:
        """Whether nothing of the row can be changed on the tab: it comes from the planning or the case."""
        return self.membership is None

    @property
    def fixed_note(self) -> str:
        """For a row without a membership of its own: where it changes – the planning, the case, the whole project."""
        if self.membership is not None:
            return ""
        if self.job_functions:
            return _("From the planning – changes with the crew line.")
        if self.is_case_manager or self.is_case_participant:
            return _("From the service case – changes there.")
        if self.inherited is not None:
            return _("From the whole project – a membership here replaces it.")
        return ""

    @property
    def access_label(self) -> str:
        """The access that holds, in words – those of the membership levels ("Einsatzsicht", "lesen" …)."""
        if not self.can_log_in:
            return _("no access – cannot log in")
        return str(ProjectAccessLevel(ACCESS_KEYS[self.access]).label)

    @property
    def reasons(self) -> list[str]:
        """Why the user is listed, in words – "eingeplant als Tontechnik", "Mitglied: lesen"."""
        texts = []
        if self.membership is not None:
            texts.append(_("member: %(level)s") % {"level": self.membership.get_level_display()})
        if self.inherited is not None:
            texts.append(
                _("member of the whole project %(number)s: %(level)s")
                % {"number": self.inherited.project.number, "level": self.inherited.get_level_display()}
            )
        if self.job_functions:
            texts.append(_("planned as %(functions)s") % {"functions": ", ".join(self.job_functions)})
        if self.is_case_manager:
            texts.append(_("responsible for the service case"))
        if self.is_case_participant:
            texts.append(_("takes part in the service case"))
        if self.by_role:
            texts.append(_("role for all projects"))
        return texts

    @property
    def reason(self) -> str:
        """The reasons as one text."""
        return "; ".join(self.reasons)


def access_rows(project: Project) -> list[AccessRow]:
    """Everybody assigned to the project, with the access that holds for each (AUT-035).

    The access is that of :func:`~rentalars.projects.access.access_level` with the user's own rights – what the
    pages and the API let him do –, found for all users together (``access_of_users``): the number of queries does
    not grow with the number of rows. Ordered by name.
    """
    rows: dict[int, AccessRow] = {}

    def row_of(user: User) -> AccessRow:
        if user.pk not in rows:
            rows[user.pk] = AccessRow(user=user)
        return rows[user.pk]

    for membership in project.memberships.select_related("user", "project"):
        row_of(membership.user).membership = membership
    if project.parent_id:
        own = set(rows)
        for membership in project.parent.memberships.select_related("user", "project"):
            if membership.user_id not in own:
                row_of(membership.user).inherited = membership
    functions: dict[int, list[str]] = defaultdict(list)
    for line in (
        project.crew_lines.filter(person__user__isnull=False)
        .select_related("person__user", "job_function")
        .order_by("start", "position", "pk")
    ):
        row = row_of(line.person.user)
        row.crew_lines.append(line.pk)
        if line.job_function.name not in functions[line.person.user.pk]:
            functions[line.person.user.pk].append(line.job_function.name)
    for user_pk, names in functions.items():
        rows[user_pk].job_functions = names
    if project.is_service_case:
        if project.manager_id is not None:
            manager = User.objects.filter(pk=project.manager_id).first()
            if manager is not None:
                row_of(manager).is_case_manager = True
        for participant in project.participants.filter(person__user__isnull=False).select_related("person__user"):
            row_of(participant.person.user).is_case_participant = True
    if not rows:
        return []
    # The listed users with their people and roles in two queries; then the access of all of them at once.
    users = {
        user.pk: user
        for user in User.objects.filter(pk__in=list(rows)).select_related("person").prefetch_related("roles")
    }
    for user in users.values():
        user._roles_cache = list(user.roles.all())
        user._person_cache = getattr(user, "person", None)
    levels = access_of_users(project, list(users.values()))
    for user_pk, row in rows.items():
        user = users[user_pk]
        row.user = user
        # AUT-035: the rule of the column "Daten" in the lists of users – an expired account as well.
        row.can_log_in = can_log_in(user)
        rights = rights_of(user)
        row.access = levels[user_pk] if row.can_log_in else ProjectAccess.NONE
        row.by_role = row.can_log_in and rights.level_everywhere(Module.PROJECTS) >= Level.READ
    return sorted(rows.values(), key=lambda row: (row.name.lower(), row.user.pk))


def row_document(row: AccessRow) -> dict[str, Any]:
    """One row for the API."""
    return {
        "user": row.user.pk,
        "username": row.user.username,
        "name": row.name,
        "access": ACCESS_KEYS[row.access],
        "can_log_in": row.can_log_in,
        "sources": row.sources,
        "membership": row.membership.pk if row.membership is not None else None,
        "membership_level": row.membership.level if row.membership is not None else None,
        "inherited_level": row.inherited.level if row.inherited is not None else None,
        "job_functions": row.job_functions,
        "crew_lines": row.crew_lines,
        "reason": row.reason,
        # Changed only through ``/members`` – rows of the planning or the case change with the crew line or the case.
        "editable": not row.from_planning_only,
    }


class ProjectAccessListView(ModuleAPIView):
    """``GET /projects/{id}/access`` – everybody assigned to the project with the access that holds (AUT-035).

    As the tab "Zugriff": read access to the project. Each row names its ``sources`` – ``membership``,
    ``inherited``, ``crew``, ``case_manager``, ``case_participant``, ``role`` – and ``access``, the level the user
    really has (``none``, ``deployment``, ``read``, ``edit``). Only memberships are changed, at ``/members``.
    """

    module = Module.PROJECTS
    schema_tag = "projects"
    action_levels: ClassVar[dict[Any, int]] = {None: Level.READ}

    @extend_schema(
        operation_id="project_access_list",
        responses={
            200: inline_serializer(
                "ProjectAccessRow",
                {
                    "user": serializers.IntegerField(),
                    "access": serializers.CharField(),
                    "sources": serializers.ListField(child=serializers.CharField()),
                    "reason": serializers.CharField(),
                    "editable": serializers.BooleanField(),
                },
                many=True,
            )
        },
    )
    def get(self, request: Request, project_pk: int) -> Response:
        """The rows, ordered by name."""
        project = project_for(request, project_pk, ProjectAccess.READ)
        return Response([row_document(row) for row in access_rows(project)])
