# SPDX-License-Identifier: GPL-3.0-or-later
"""Who may see and change which project (AUT-016 to AUT-018, AUT-025).

Module rights say what a user may do with projects *in general*
(``accounts.rights``). This module answers the question for *one* project.

The four levels (AUT-025)
-------------------------
==============  ==========================================================
no access       the project does not exist for the user
deployment      the deployment view: time, place, job function, on-site
                contact, colleagues, the packlist, the user's own times
read            the planning page, read-only
edit            planning, groups, lines, status
==============  ==========================================================

None of the levels includes prices, costs or correspondence. Those come only
through the special rights of the role (AUT-019).

How the level of a user in a project comes about
------------------------------------------------
1. A role for **all projects** (AUT-017) gives its level in every project:
   "read" gives *read*, "create and edit" or more gives *edit*.

2. A role for **assigned projects only** gives its level only where the user
   is assigned, and there only up to the level of the assignment:

   * a **membership** (``ProjectMembership``) names its level itself:
     deployment, read or edit;
   * a **crew line** of the person linked to the user is an assignment by
     itself and gives the *deployment* view (AUT-018);
   * **taking part** in a service case (``ServiceCaseParticipant``,
     PRJ-108) gives *read* in that case – a case has no deployment
     view, its page is what the person works with.

   AUT-031 (requirement for the role "Crew"): a role for **assigned
   projects, overview only** (``ProjectScope.DEPLOYMENT``) gives at most the
   *deployment* view there, whatever level a membership names – the
   overview with the phases, the packing list and the chat; never the
   planning, the schedule, the access or the history (:func:`role_limit`).

3. The highest result counts.

4. AUT-033: **working on a service case.** The person responsible for a case
   and the people taking part in it always open that case – *read*, whatever
   their roles say, even without the module "projects" – and may work on it
   where a page or an endpoint allows it (``projects.case_work``): status,
   fields, open items, follow-up, chat and the correspondence of the case.
   Nothing of other cases or projects.

Subprojects (PRJ-049)
---------------------
A membership of a whole project holds in all its subprojects. A membership
of a subproject replaces it there – for more or for less, down to "no
access". A crew line counts in the project it belongs to: crew planned on
stage 2 sees the deployment view of stage 2, even where a membership of
the stage says "no access". A membership of a subproject alone does not
open the whole project or the other parts.

Roles for all projects are not touched by any of this: they hold in every
project and every part.

Examples: a freelancer with the role "Freie Kraft" (reads assigned projects)
who is planned as stagehand sees the deployment view of that project and
nothing of any other. Give the same person a membership "edit" and it is
still only *read*, because the role reads and does not edit. A project
manager with a role for all projects needs no assignment at all.

Every browser view and every API endpoint that shows something of a project
gets the project from here (``project_for``), so no page can forget the
question (AUT-020).
"""

from __future__ import annotations

import contextlib
import contextvars
import enum
from collections.abc import Collection, Iterator
from typing import Any

from django.core.exceptions import PermissionDenied
from django.db.models import Q, QuerySet
from django.http import Http404, HttpRequest

from rentalars.accounts.rights import Level, Module, Rights, SpecialRight, request_rights
from rentalars.projects.models import Project, ProjectAccessLevel, ProjectMembership, with_parts_flag


class ProjectAccess(enum.IntEnum):
    """What a user may do in one project (AUT-025); higher includes lower."""

    NONE = 0
    DEPLOYMENT = 1
    READ = 2
    EDIT = 3


#: The level a membership grants, as an access level.
_MEMBERSHIP_ACCESS = {
    ProjectAccessLevel.NONE.value: ProjectAccess.NONE,
    ProjectAccessLevel.DEPLOYMENT.value: ProjectAccess.DEPLOYMENT,
    ProjectAccessLevel.READ.value: ProjectAccess.READ,
    ProjectAccessLevel.EDIT.value: ProjectAccess.EDIT,
}


#: The membership levels that open a project at all.
_GRANTING_LEVELS = (ProjectAccessLevel.DEPLOYMENT.value, ProjectAccessLevel.READ.value, ProjectAccessLevel.EDIT.value)


def _from_module_level(level: int) -> ProjectAccess:
    """Translate a level of the module "projects" into what it allows in a project."""
    if level >= Level.WRITE:
        return ProjectAccess.EDIT
    if level >= Level.READ:
        return ProjectAccess.READ
    return ProjectAccess.NONE


def role_limit(rights: Rights) -> ProjectAccess:
    """The most the roles give in a project the user is assigned to (AUT-025).

    AUT-031 (Crew): a role for "assigned projects, overview only" reads the
    module, but opens no planning – it gives the deployment view at most.
    """
    limit = _from_module_level(rights.level_of_planning())
    if limit < ProjectAccess.DEPLOYMENT and rights.can_read(Module.PROJECTS):
        limit = ProjectAccess.DEPLOYMENT
    return limit


def works_on_case(user: Any, project: Project) -> bool:
    """Whether the user is responsible for the service case or takes part in it (AUT-033; PRJ-090, PRJ-108).

    Always ``False`` for a project that is no service case. Asked anew each
    time (one query at most), as assignments are: somebody added a moment ago
    counts at once.
    """
    if not project.is_service_case or not getattr(user, "is_authenticated", False) or project.pk is None:
        return False
    if project.manager_id is not None and project.manager_id == user.pk:
        return True
    person = person_of(user)
    return person is not None and project.participants.filter(person=person).exists()


def case_work_filter(user: Any) -> Q:
    """The database condition "a service case the user is responsible for or takes part in" (AUT-033; PRJ-108).

    Without a logged-in user (``None`` – the system, demo data) the condition holds for no project.
    """
    from rentalars.projects.models import ProjectKind, ServiceCaseParticipant

    if not getattr(user, "is_authenticated", False) or getattr(user, "pk", None) is None:
        return Q(pk__in=[])
    condition = Q(kind=ProjectKind.SERVICE_CASE, manager_id=user.pk)
    person = person_of(user)
    if person is not None:
        condition |= Q(
            pk__in=ServiceCaseParticipant.objects.filter(person=person, project__kind=ProjectKind.SERVICE_CASE).values(
                "project_id"
            )
        )
    return condition


def person_of(user: Any) -> Any:
    """Return the person linked to a user account, or ``None`` (AUT-012).

    The answer is remembered on the user object for the request.
    """
    if not getattr(user, "is_authenticated", False):
        return None
    if not hasattr(user, "_person_cache"):
        from rentalars.personnel.models import Person

        user._person_cache = Person.objects.filter(user_id=user.pk).first()
    return user._person_cache


def assignment_of(user: Any, project: Project) -> ProjectAccess:
    """Return the level the user's *assignment* to a project carries (AUT-018).

    ``NONE`` means: not assigned. A membership names its level; a crew line
    of the user's person gives the deployment view. If both exist, the
    higher one counts.
    """
    if not getattr(user, "is_authenticated", False):
        return ProjectAccess.NONE
    if project.parent_id:
        # PRJ-049: the subproject's own membership, else the one of the whole project.
        levels = dict(
            ProjectMembership.objects.filter(project_id__in=[project.pk, project.parent_id], user=user).values_list(
                "project_id", "level"
            )
        )
        level = levels.get(project.pk, levels.get(project.parent_id))
    else:
        level = ProjectMembership.objects.filter(project=project, user=user).values_list("level", flat=True).first()
    access = _MEMBERSHIP_ACCESS.get(level or "", ProjectAccess.NONE)
    if access < ProjectAccess.READ and project.is_service_case:
        # PRJ-108: taking part in a service case opens it for reading.
        person = person_of(user)
        if person is not None and project.participants.filter(person=person).exists():
            return ProjectAccess.READ
    if access < ProjectAccess.DEPLOYMENT:
        person = person_of(user)
        if person is not None and project.crew_lines.filter(person=person).exists():
            access = ProjectAccess.DEPLOYMENT
    return access


def access_level(rights: Rights, user: Any, project: Project) -> ProjectAccess:
    """Return what a user may do in a project; see the rules at the top of this module.

    A superuser needs no special case: the rights of a superuser hold for
    all projects (``Rights.everything``). API-010: while a call with
    an ``Idempotency-Key`` runs, every level found for its caller is noted
    (:func:`recording_project_access`).
    """
    everywhere = _from_module_level(rights.level_everywhere(Module.PROJECTS))
    if not rights.is_limited_to_assigned_projects(Module.PROJECTS):
        level = everywhere
    else:
        assigned = min(role_limit(rights), assignment_of(user, project))
        level = max(everywhere, assigned)
    if level < ProjectAccess.READ and rights.case_work >= Level.READ and works_on_case(user, project):
        # AUT-033: the own service case opens, whatever the roles say (PRJ-108).
        level = ProjectAccess.READ
    note_used_access(user, project, level)
    return level


# --- API-010: which project access a call relied on --------------------------------------

#: While a call with an ``Idempotency-Key`` runs: the ID of its user and, per project, the highest level found.
_used_access: contextvars.ContextVar[tuple[int, dict[int, int]] | None] = contextvars.ContextVar(
    "rentalars_used_project_access", default=None
)


def note_used_access(user: Any, project: Project, level: ProjectAccess) -> None:
    """Note the level a call relied on for a project (API-010); :func:`access_level` does it, a bulk call for many."""
    noted = _used_access.get()
    if noted is None or level == ProjectAccess.NONE or project.pk is None:
        return
    user_pk, levels = noted
    # Only the caller's own access: a notification to others asks for theirs in the same call.
    if getattr(user, "pk", None) == user_pk:
        levels[project.pk] = max(levels.get(project.pk, 0), int(level))


@contextlib.contextmanager
def recording_project_access(user: Any) -> Iterator[dict[int, int]]:
    """Note the access to projects the caller's call relies on (API-010).

    Every check of a project goes through :func:`access_level` – that of
    :func:`project_for`, of :func:`packlist_project_for` and the ones made
    inline – so the levels noted here are those the call was allowed by. A
    stored answer to a repeated call goes out only if the caller still has
    them (``api.safeguards``).

    Yields:
        Project ID → the highest level found for the caller.
    """
    levels: dict[int, int] = {}
    token = _used_access.set((user.pk, levels))
    try:
        yield levels
    finally:
        _used_access.reset(token)


def module_level_in(rights: Rights, user: Any, project: Project, module: str) -> int:
    """Return the level of a project-bound module (e.g. packing) inside one project.

    A level from a role for all projects holds everywhere; a level from a
    role for assigned projects only holds where the user is assigned.
    """
    everywhere = rights.level_everywhere(module)
    if rights.level(module) > everywhere and assignment_of(user, project) > ProjectAccess.NONE:
        return rights.level(module)
    return everywhere


def _membership_filter(user: Any, levels: Collection[str]) -> Q:
    """The database condition "a membership with one of these levels holds for the project" (PRJ-049).

    Either the project's own membership has such a level, or the project is
    a subproject without a membership of its own and that of its whole
    project has.
    """
    own = ProjectMembership.objects.filter(user=user)
    with_level = own.filter(level__in=list(levels)).values("project_id")
    return Q(pk__in=with_level) | (Q(parent_id__in=with_level) & ~Q(pk__in=own.values("project_id")))


def assigned_filter(user: Any) -> Q:
    """The database condition "the user is assigned to the project" (AUT-018, PRJ-049)."""
    condition = _membership_filter(user, _GRANTING_LEVELS)
    person = person_of(user)
    if person is not None:
        from rentalars.projects.models import CrewLine, ProjectKind, ServiceCaseParticipant

        condition |= Q(pk__in=CrewLine.objects.filter(person=person).values("project_id"))
        # PRJ-108: the service cases the person takes part in.
        condition |= Q(
            pk__in=ServiceCaseParticipant.objects.filter(person=person, project__kind=ProjectKind.SERVICE_CASE).values(
                "project_id"
            )
        )
    return condition


def visible_projects(rights: Rights, user: Any, queryset: QuerySet[Project] | None = None) -> QuerySet[Project]:
    """Narrow a list of projects to those the user may see at all (AUT-016).

    Used by the project list, the search, the start page and the API, so
    that all of them show the same projects (acceptance scenario 6).
    """
    projects = Project.objects.all() if queryset is None else queryset
    if rights.can_read(Module.PROJECTS) and rights.level_everywhere(Module.PROJECTS) >= Level.READ:
        return projects
    # AUT-033: the own service cases are visible to everybody who works on them (nobody without a login).
    working = rights.case_work >= Level.READ and getattr(user, "is_authenticated", False)
    worked = case_work_filter(user) if working else None
    if not rights.can_read(Module.PROJECTS):
        return (
            projects.none() if worked is None else projects.filter(pk__in=Project.objects.filter(worked).values("pk"))
        )
    condition = assigned_filter(user) if worked is None else assigned_filter(user) | worked
    assigned = Project.objects.filter(condition).values("pk")
    return projects.filter(pk__in=assigned)


def may_see_reports(rights: Rights) -> bool:
    """Whether "Auswertungen" are open to these rights (PRJ-115, MAT-053).

    The module "Reports" (AUT-014), the price right, and reading every project:
    the figures sum up projects of all customers – over the assigned projects
    only they would mislead.
    """
    return (
        rights.can_read(Module.REPORTS)
        and rights.has(SpecialRight.PRICES)
        and rights.level_everywhere(Module.PROJECTS) >= Level.READ
    )


def readable_projects(rights: Rights, user: Any, queryset: QuerySet[Project] | None = None) -> QuerySet[Project]:
    """Narrow a list of projects to those whose *planning* the user may read.

    Stricter than :func:`visible_projects`: a project the user only knows
    through a crew line (deployment view) is not part of it. Used where lines
    and stock of projects are shown, e.g. the list of shortages.

    AUT-031: a role for "overview only" reads no planning, whatever its
    memberships say; the own service cases are part of it (case work).
    """
    projects = Project.objects.all() if queryset is None else queryset
    if rights.level_everywhere(Module.PROJECTS) >= Level.READ:
        return projects
    working = rights.case_work >= Level.READ and getattr(user, "is_authenticated", False)
    worked = case_work_filter(user) if working else None
    if not rights.reads_planning:
        return (
            projects.none() if worked is None else projects.filter(pk__in=Project.objects.filter(worked).values("pk"))
        )
    condition = _membership_filter(user, [ProjectAccessLevel.READ, ProjectAccessLevel.EDIT])
    if worked is not None:
        condition |= Q(pk__in=Project.objects.filter(worked).values("pk"))
    return projects.filter(condition)


def project_for(
    request: HttpRequest | Any,
    pk: int | str,
    minimum: ProjectAccess = ProjectAccess.READ,
    *,
    queryset: QuerySet[Project] | None = None,
    case_work: bool = False,
) -> Project:
    """Load a project for a request, or refuse (AUT-016, AUT-020).

    Args:
        request: The request; its user and rights are asked.
        pk: The ID of the project.
        minimum: The access level the page or operation needs.
        queryset: Projects to load from, e.g. with ``select_related``.
        case_work: AUT-033 (PRJ-108): the operation is part of working on a
            service case – the person responsible and the people taking part
            may do it in their case even where ``minimum`` asks for more than
            their roles give (``projects.case_work``).

    Returns:
        The project. Its attribute ``access`` holds the user's level, so that
        the caller can decide what to show; ``works_on_case`` and
        ``may_work_on_case`` say whether the user reads and may work on the
        service case as somebody working on it (AUT-033).

    Raises:
        Http404: The project does not exist – or the user has no access to it
            at all. Both look the same on purpose: a user limited to assigned
            projects must not be able to find out which numbers exist.
        PermissionDenied: The user may see the project, but not do this.
    """
    projects = Project.objects.all() if queryset is None else queryset
    # PRJ-044: the head of every project page asks whether the project has parts.
    # PRJ-105: and names the user of the follow-up.
    project = with_parts_flag(projects).select_related("follow_up_user").filter(pk=pk).first()
    if project is None:
        raise Http404
    rights = request_rights(request)
    access = access_level(rights, request.user, project)
    if access == ProjectAccess.NONE:
        raise Http404
    note_case_work(project, rights, request.user)
    if access < minimum and not (case_work and _case_work_reaches(project, minimum)):
        raise PermissionDenied
    note_access(project, access)
    return project


def note_case_work(project: Project, rights: Rights, user: Any) -> None:
    """Write onto a project whether the user works on it as a service case (AUT-033; PRJ-108).

    ``works_on_case``: responsible or taking part, and the login may read it;
    ``may_work_on_case``: and may change it (not with a read-only token).
    """
    works = rights.case_work >= Level.READ and works_on_case(user, project)
    project.works_on_case = works
    project.may_work_on_case = works and rights.case_work >= Level.WRITE


def _case_work_reaches(project: Project, minimum: ProjectAccess) -> bool:
    """Whether working on the case covers an operation that needs ``minimum`` (AUT-033)."""
    if minimum >= ProjectAccess.EDIT:
        return bool(getattr(project, "may_work_on_case", False))
    return bool(getattr(project, "works_on_case", False))


def note_access(project: Project, access: ProjectAccess) -> None:
    """Write the user's level onto a project object, in the forms pages ask for it.

    ``project.access`` for code; ``project.shows_planning`` and
    ``project.is_editable_by_user`` for templates, which cannot compare
    against named levels.
    """
    project.access = access
    project.shows_deployment = access >= ProjectAccess.DEPLOYMENT
    project.shows_planning = access >= ProjectAccess.READ
    project.shows_customer = access >= ProjectAccess.READ
    project.is_editable_by_user = access >= ProjectAccess.EDIT


def packlist_project_for(
    request: HttpRequest | Any,
    pk: int | str,
    level: int = Level.READ,
    *,
    queryset: QuerySet[Project] | None = None,
) -> Project:
    """Load a project for its packlist, or refuse (AUT-016, AUT-025).

    The packlist has two ways in. It is part of the deployment view, so
    whoever sees the project sees its packlist as far as the role reads
    "packing". And a role with "packing" for all projects – the warehouse –
    works on every packlist, whether or not it reads the planning.

    Args:
        request: The request; its user and rights are asked.
        pk: The ID of the project.
        level: The level of the module "packing" the page or operation
            needs *in this project*: read to look, write to tick, issue and
            take back.
        queryset: Projects to load from, e.g. with ``select_related``.

    Returns:
        The project with ``access`` and the flags of :func:`note_access`, and
        with ``packing_level``, the user's level of "packing" in it.

    Raises:
        Http404: The project does not exist or the user has no way to it.
        PermissionDenied: The user may see the packlist, but not do this.
    """
    rights = request_rights(request)
    projects = Project.objects.all() if queryset is None else queryset
    # PRJ-105: the head of the page names the user of the follow-up.
    project = projects.select_related("follow_up_user").filter(pk=pk).first()
    if project is None:
        raise Http404
    access = access_level(rights, request.user, project)
    everywhere = rights.level_everywhere(Module.PACKING)
    if access == ProjectAccess.NONE and everywhere < Level.READ:
        raise Http404
    packing = module_level_in(rights, request.user, project, Module.PACKING)
    if packing < level:
        raise PermissionDenied
    note_access(project, access)
    project.packing_level = packing
    # PRJ-122: the packing list names the customer in every role – the name only (AUT-023).
    project.shows_customer = True
    return project


def may_plan_crew(rights: Rights, access: ProjectAccess) -> bool:
    """Whether a user may add and change crew lines of a project.

    Those who edit the project may; so may personnel planning: whoever
    reads the project and maintains the personnel data (role
    "Personaldisposition", catalogue chapter 4).
    """
    if access >= ProjectAccess.EDIT:
        return True
    return access >= ProjectAccess.READ and rights.can_write(Module.PERSONNEL)


def may_plan_logistics(rights: Rights, access: ProjectAccess) -> bool:
    """LOG-001: whether a user may book vehicles of a project and put them on its trips.

    Those who edit the project may; so may whoever reads the project and
    maintains the material – the fleet is part of it (LOG-002).
    """
    if access >= ProjectAccess.EDIT:
        return True
    return access >= ProjectAccess.READ and rights.can_write(Module.MATERIAL)


def access_of_many(rights: Rights, user: Any, project_ids: list[int]) -> dict[int, ProjectAccess]:
    """Return the access level of a user for several projects with two queries (NFA-014).

    For lists: the API delivers the level with every project, and asking
    :func:`access_level` once per row would cost two queries per row. With
    subprojects (PRJ-049) a third query finds their whole projects – and
    the service cases the user is responsible for (AUT-033).
    """
    everywhere = _from_module_level(rights.level_everywhere(Module.PROJECTS))
    user_pk = getattr(user, "pk", None) if getattr(user, "is_authenticated", False) else None
    case_work = rights.case_work >= Level.READ and user_pk is not None
    limited = rights.is_limited_to_assigned_projects(Module.PROJECTS)
    if not limited and (everywhere >= ProjectAccess.READ or not case_work):
        return dict.fromkeys(project_ids, everywhere)
    limit = role_limit(rights) if limited else ProjectAccess.NONE
    from rentalars.projects.models import ProjectKind

    # One query for the subprojects and – AUT-033 – the service cases the user is responsible for.
    parents: dict[int, int] = {}
    worked: set[int] = set()
    for project_id, parent_id, kind, manager_id in (
        Project.objects.filter(pk__in=project_ids)
        .filter(Q(parent__isnull=False) | Q(kind=ProjectKind.SERVICE_CASE, manager_id=user_pk))
        .values_list("pk", "parent_id", "kind", "manager_id")
    ):
        if parent_id:
            parents[project_id] = parent_id
        if kind == ProjectKind.SERVICE_CASE and user_pk is not None and manager_id == user_pk:
            worked.add(project_id)
    levels = dict(
        ProjectMembership.objects.filter(project_id__in={*project_ids, *parents.values()}, user=user).values_list(
            "project_id", "level"
        )
    )
    assigned: dict[int, ProjectAccess] = {}
    for project_id in project_ids:
        level = levels.get(project_id, levels.get(parents.get(project_id, 0)))
        if level is not None:
            assigned[project_id] = _MEMBERSHIP_ACCESS.get(level, ProjectAccess.NONE)
    person = person_of(user)
    if person is not None:
        from django.db.models import IntegerField, Value

        from rentalars.projects.models import CrewLine, ServiceCaseParticipant

        # One query for both: crew lines give the deployment view, taking part in a service case
        # gives read (PRJ-108).
        crew = (
            CrewLine.objects.filter(project_id__in=project_ids, person=person)
            .order_by()
            .annotate(level=Value(int(ProjectAccess.DEPLOYMENT), output_field=IntegerField()))
            .values_list("project_id", "level")
        )
        taking_part = (
            ServiceCaseParticipant.objects.filter(
                project_id__in=project_ids, person=person, project__kind=ProjectKind.SERVICE_CASE
            )
            .order_by()
            .annotate(level=Value(int(ProjectAccess.READ), output_field=IntegerField()))
            .values_list("project_id", "level")
        )
        for project_id, level in crew.union(taking_part):
            assigned[project_id] = max(assigned.get(project_id, ProjectAccess.NONE), ProjectAccess(level))
            if level == ProjectAccess.READ:
                worked.add(project_id)  # taking part: working on the case (AUT-033)
    result: dict[int, ProjectAccess] = {}
    for project_id in project_ids:
        level = max(everywhere, min(limit, assigned.get(project_id, ProjectAccess.NONE)))
        if case_work and project_id in worked:
            level = max(level, ProjectAccess.READ)  # AUT-033: the own service case (PRJ-108)
        result[project_id] = level
    return result


def access_of_users(project: Project, users: Collection[Any]) -> dict[int, ProjectAccess]:
    """Return what each of several users may do in one project, with three queries whatever their number (AUT-035).

    The counterpart of :func:`access_of_many` for the tab "Zugriff" (``projects.access_rows``): the same rules as
    :func:`access_level` – :func:`assignment_of`, :func:`role_limit`, working on the case – asked once for all
    users: their memberships of the project and its whole project, their crew lines and their part in a service
    case. Each user's rights are ``rights_of(user)``; load the users with their roles (``prefetch_related``) and
    their person (``select_related("person")``), else those cost a query each.
    """
    from rentalars.accounts.rights import rights_of
    from rentalars.projects.models import CrewLine, ServiceCaseParticipant

    users = [user for user in users if getattr(user, "is_authenticated", False) and user.pk is not None]
    if not users:
        return {}
    user_ids = [user.pk for user in users]
    levels: dict[tuple[int, int], str] = {
        (user_id, project_id): level
        for user_id, project_id, level in ProjectMembership.objects.filter(
            project_id__in=[pk for pk in (project.pk, project.parent_id) if pk], user_id__in=user_ids
        ).values_list("user_id", "project_id", "level")
    }
    people = {user.pk: person_of(user) for user in users}
    person_ids = [person.pk for person in people.values() if person is not None]
    crew = set(CrewLine.objects.filter(project=project, person_id__in=person_ids).values_list("person_id", flat=True))
    taking_part: set[int] = set()
    if project.is_service_case:
        taking_part = set(
            ServiceCaseParticipant.objects.filter(project=project, person_id__in=person_ids).values_list(
                "person_id", flat=True
            )
        )
    result: dict[int, ProjectAccess] = {}
    for user in users:
        rights = rights_of(user)
        person = people[user.pk]
        person_id = person.pk if person is not None else None
        # As assignment_of: the own membership, else that of the whole project (PRJ-049) …
        level = levels.get((user.pk, project.pk), levels.get((user.pk, project.parent_id or 0)))
        assigned = _MEMBERSHIP_ACCESS.get(level or "", ProjectAccess.NONE)
        if assigned < ProjectAccess.READ and project.is_service_case and person_id in taking_part:
            assigned = ProjectAccess.READ  # PRJ-108: taking part opens the case for reading
        elif assigned < ProjectAccess.DEPLOYMENT and person_id in crew:
            assigned = ProjectAccess.DEPLOYMENT  # AUT-018: a crew line
        # … and as access_level: the roles for all projects, the ceiling of the roles, working on the case.
        everywhere = _from_module_level(rights.level_everywhere(Module.PROJECTS))
        if not rights.is_limited_to_assigned_projects(Module.PROJECTS):
            access = everywhere
        else:
            access = max(everywhere, min(role_limit(rights), assigned))
        works = project.is_service_case and (project.manager_id == user.pk or person_id in taking_part)
        if access < ProjectAccess.READ and rights.case_work >= Level.READ and works:
            access = ProjectAccess.READ  # AUT-033: the own service case (PRJ-108)
        result[user.pk] = access
    return result
