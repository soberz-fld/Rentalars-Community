# SPDX-License-Identifier: GPL-3.0-or-later
"""The rights model: modules, access levels and special rights (AUT-013 ff.).

A user's rights come from the roles assigned to the user. A role grants

* an **access level per module** (none, read, write, delete – AUT-015),
* any number of **special rights** that are deliberately independent of the
  module levels (AUT-019): seeing prices, seeing purchase prices, reading
  correspondence and so on, and
* a **project scope** (AUT-017): whether its rights on projects and
  packlists hold for all projects or only for the projects the user is
  assigned to – or (AUT-031) for assigned projects with the overview
  only (the role "Crew": no planning, whatever a membership says).

If a user has several roles, the highest level per module counts and the
special rights add up.

Rights on single projects (AUT-016)
-----------------------------------
A role limited to "assigned projects only" does not say *which* projects;
that is decided per project, by a membership or by a crew line of the
user's person. This module therefore knows two levels for the modules whose
records belong to a project:

``rights.level(module)``
    the highest level the user has in *any* project – "may the user edit
    projects at all?". Decides whether the module shows up.

``rights.level_everywhere(module)``
    the level that holds in *every* project, assigned or not.

What a user may do in one given project is answered by
``rentalars.projects.access``, which combines the two with the assignment.

Example::

    rights = rights_of(user)
    rights.can_write(Module.PROJECTS)      # may the user edit projects?
    rights.has(SpecialRight.PRICES)        # may the user see prices?

Both the browser views and the API ask this module, so the two can never
disagree about what a user may do (AUT-020, API-006).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from functools import wraps
from typing import TYPE_CHECKING, Any

from django.core.exceptions import PermissionDenied
from django.db import models
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from rentalars.accounts.models import User


class Module(models.TextChoices):
    """The business areas rights are granted for (AUT-013, AUT-014).

    "Packing and issue" is an addition to the list in the catalogue: warehouse
    staff must be able to work through packlists without the right to edit
    projects, and crew may look at a packlist without touching it.
    """

    MATERIAL = "material", _("Material")
    PRODUCTS = "products", _("Products")
    CUSTOMERS = "customers", _("Customers")
    PROJECTS = "projects", _("Projects")
    PACKING = "packing", _("Packing and issue")
    PERSONNEL = "personnel", _("Personnel")
    TIME_TRACKING = "time_tracking", _("Time tracking")
    EMAIL = "email", _("E-mail")
    REPORTS = "reports", _("Reports")
    ADMINISTRATION = "administration", _("Settings")


#: Modules whose functions arrive in a later stage. Roles can already carry
#: rights for them, so that no role has to be reworked when the stage arrives.
#: The last one, "Reports" (PRJ-115: "Auswertungen"), has arrived.
FUTURE_MODULES: frozenset[str] = frozenset()


class Level(models.IntegerChoices):
    """Access levels of a module; each level includes the ones below (AUT-015)."""

    NONE = 0, _("no access")
    READ = 1, _("read")
    WRITE = 2, _("create and edit")
    DELETE = 3, _("delete")


class SpecialRight(models.TextChoices):
    """Rights that are always granted separately from module access (AUT-019)."""

    PRICES = "prices", _("See prices and calculation")
    PURCHASE_PRICES = "purchase_prices", _("See purchase prices")
    PERSONNEL_COSTS = "personnel_costs", _("See hourly rates and personnel costs")
    CORRESPONDENCE_READ = "correspondence_read", _("Read correspondence")
    CORRESPONDENCE_WRITE = "correspondence_write", _("Write and send correspondence")
    REOPEN_PROJECTS = "reopen_projects", _("Reopen closed projects")
    CHANGE_ARTICLE_NUMBERS = "change_article_numbers", _("Change article numbers that are in use")
    EDIT_RENTAL_SCALES = "edit_rental_scales", _("Edit rental scales")
    APPROVE_TIMES = "approve_times", _("Approve times and record them for others")
    PLAN_ANY_JOB_FUNCTION = "plan_any_job_function", _("Plan people in job functions they are not assigned to")
    #: AUT-032: the traffic lights of the planning and the line dialog, the
    #: availability of a product with its timeline, the material utilization, the shortages – on the pages, in
    #: the API and in the notifications. Not the stock of a product, not the vehicles of the fleet (LOG-001).
    AVAILABILITY = "availability", _("See availability of material")


class ProjectScope(models.TextChoices):
    """Which projects the project rights of a role cover (AUT-017).

    AUT-031 (Crew; AUT-025): "assigned projects, overview only" is "assigned
    projects only" with a ceiling: in its projects the role opens the
    deployment view ("Überblick") with the packing list and the chat, never
    the planning, the schedule, the access or the history – whatever level a
    membership names. The module "projects" still shows up, so that the own
    projects can be listed.
    """

    ALL = "all", _("all projects")
    ASSIGNED = "assigned", _("assigned projects only")
    DEPLOYMENT = "deployment", _("assigned projects only, overview without planning")


#: Modules whose records belong to a project. A role limited to "assigned
#: projects only" reaches them only through an assignment (AUT-017).
PROJECT_BOUND_MODULES = frozenset({Module.PROJECTS.value, Module.PACKING.value})


@dataclass(frozen=True)
class Rights:
    """The effective rights of one user (or of one API token of that user)."""

    #: The highest level per module the user has anywhere.
    module_levels: Mapping[str, int] = field(default_factory=dict)
    special_rights: frozenset[str] = frozenset()
    #: For the modules in ``PROJECT_BOUND_MODULES``: the level that holds in
    #: every project. ``None`` means "no difference": all levels hold everywhere.
    everywhere_levels: Mapping[str, int] | None = None
    #: AUT-031 (AUT-025): the highest level of the module "projects" among the roles that open the planning –
    #: every role but those for "assigned projects, overview only" (``ProjectScope.DEPLOYMENT``). ``None``: every
    #: role opens it, the level of the module counts.
    planning_level: int | None = None
    #: AUT-033 (PRJ-108): what working on the own service cases – as the person responsible or as
    #: somebody taking part – allows this login: "create and edit" for a session, "read" for a read-only token,
    #: nothing for a token without the module "projects" (see ``projects.case_work``).
    case_work: int = Level.NONE

    def level(self, module: str) -> int:
        """Return the access level for a module (``Level.NONE`` if not granted).

        For projects and packlists this is the highest level the user has in
        any project; see :meth:`level_everywhere`.
        """
        return int(self.module_levels.get(str(module), Level.NONE))

    def level_everywhere(self, module: str) -> int:
        """Return the level that holds for every project, assigned or not (AUT-017).

        For modules that are not bound to projects this is simply the level.

        Example: the role "Crew" reads projects, but only assigned ones.
        ``level("projects")`` is "read", ``level_everywhere("projects")`` is
        "no access".
        """
        if self.everywhere_levels is None or str(module) not in PROJECT_BOUND_MODULES:
            return self.level(module)
        return int(self.everywhere_levels.get(str(module), Level.NONE))

    def is_limited_to_assigned_projects(self, module: str = "projects") -> bool:
        """Whether some of the user's rights in the module depend on being assigned to the project."""
        return self.level(module) > self.level_everywhere(module)

    def level_of_planning(self) -> int:
        """The level of "projects" with which the planning of a project opens (AUT-031; AUT-025).

        Example: the role "Crew" reads projects for "assigned projects, overview only":
        ``level("projects")`` is "read", ``level_of_planning()`` is "no access".
        """
        if self.planning_level is None:
            return self.level(Module.PROJECTS)
        return min(int(self.planning_level), self.level(Module.PROJECTS))

    @property
    def reads_planning(self) -> bool:
        """Whether the user may read the planning of any project at all (AUT-031; AUT-025).

        Pages that sum up the planning of projects – "Offene Punkte", the shortages – are for those only.
        """
        return self.level_of_planning() >= Level.READ

    def can_read(self, module: str) -> bool:
        """Whether the module is visible at all."""
        return self.level(module) >= Level.READ

    def can_write(self, module: str) -> bool:
        """Whether objects of the module may be created and edited."""
        return self.level(module) >= Level.WRITE

    def can_delete(self, module: str) -> bool:
        """Whether objects of the module may be deleted."""
        return self.level(module) >= Level.DELETE

    def has(self, special_right: str) -> bool:
        """Whether a special right such as ``SpecialRight.PRICES`` is granted."""
        return str(special_right) in self.special_rights

    def has_level(self, module: str, level: int) -> bool:
        """Whether the module is granted at ``level`` or above."""
        return self.level(module) >= level

    @property
    def readable_modules(self) -> list[str]:
        """All modules with at least read access."""
        return [module for module in Module.values if self.can_read(module)]

    def restricted(self, *, read_only: bool, allowed_modules: Iterable[str]) -> Rights:
        """Return a narrowed copy for an API token (AUT-021).

        A token can only ever have fewer rights than its user, never more.

        Args:
            read_only: Cap every module at read access.
            allowed_modules: If not empty, keep access only to these modules.
        """
        allowed = {str(module) for module in allowed_modules}

        def narrowed(source: Mapping[str, int]) -> dict[str, int]:
            return {
                module: min(level, Level.READ) if read_only else level
                for module, level in source.items()
                if not allowed or module in allowed
            }

        levels = narrowed(self.module_levels)
        everywhere = narrowed(self.everywhere_levels) if self.everywhere_levels is not None else None
        projects_kept = not allowed or Module.PROJECTS.value in allowed
        # AUT-031, AUT-033: the planning and the work on the own service cases are narrowed like the module "projects".
        planning = self.planning_level
        if planning is not None:
            planning = (min(planning, Level.READ) if read_only else planning) if projects_kept else int(Level.NONE)
        case_work = (min(self.case_work, Level.READ) if read_only else self.case_work) if projects_kept else 0
        special = self.special_rights
        if read_only:
            # Rights that only make sense for changing data are dropped.
            special = special - {
                SpecialRight.CORRESPONDENCE_WRITE,
                SpecialRight.REOPEN_PROJECTS,
                SpecialRight.CHANGE_ARTICLE_NUMBERS,
                SpecialRight.EDIT_RENTAL_SCALES,
                SpecialRight.APPROVE_TIMES,
                SpecialRight.PLAN_ANY_JOB_FUNCTION,
            }
        return Rights(
            module_levels=levels,
            special_rights=frozenset(special),
            everywhere_levels=everywhere,
            planning_level=planning,
            case_work=int(case_work),
        )

    @classmethod
    def everything(cls) -> Rights:
        """All modules at the highest level and all special rights."""
        return cls(
            module_levels=dict.fromkeys(Module.values, int(Level.DELETE)),
            special_rights=frozenset(SpecialRight.values),
            case_work=int(Level.WRITE),
        )


NO_RIGHTS = Rights()


def rights_of(user: User | Any) -> Rights:
    """Compute the effective rights of a user from the user's roles.

    Inactive and anonymous users have no rights. A superuser has all rights;
    that account type exists so that nobody can lock the whole company out by
    editing roles.

    The result is cached on the user object for the duration of a request.
    """
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return NO_RIGHTS
    cached = getattr(user, "_rights_cache", None)
    if cached is not None:
        return cached

    if user.is_superuser:
        rights = Rights.everything()
    else:
        levels: dict[str, int] = {}
        everywhere: dict[str, int] = {}
        planning = 0
        special: set[str] = set()
        roles = getattr(user, "_roles_cache", None)
        if roles is None:
            roles = list(user.roles.all())
            user._roles_cache = roles
        for role in roles:
            for module, level in role.module_levels.items():
                levels[module] = max(levels.get(module, 0), int(level))
                if module in PROJECT_BOUND_MODULES and role.project_scope == ProjectScope.ALL:
                    # Only a role for "all projects" grants something in a
                    # project the user is not assigned to (AUT-017).
                    everywhere[module] = max(everywhere.get(module, 0), int(level))
                if module == Module.PROJECTS and role.project_scope != ProjectScope.DEPLOYMENT:
                    # AUT-031: a role for "overview only" never opens the planning.
                    planning = max(planning, int(level))
            special.update(role.special_rights)
        rights = Rights(
            module_levels=levels,
            special_rights=frozenset(special),
            everywhere_levels=everywhere,
            planning_level=planning,
            # AUT-033 (PRJ-108): working on the own service cases needs no module right.
            case_work=int(Level.WRITE),
        )
    user._rights_cache = rights
    return rights


def request_rights(request: HttpRequest | Any) -> Rights:
    """Return the rights that apply to a request.

    For a browser session these are the rights of the user. For an API call
    with a token they may be narrower, see :meth:`Rights.restricted`.
    """
    cached = getattr(request, "_rentalars_rights", None)
    if cached is not None:
        return cached
    rights = rights_of(request.user)
    token = getattr(request, "auth", None)
    if token is not None and hasattr(token, "restrict"):
        rights = token.restrict(rights)
    request._rentalars_rights = rights
    return rights


def module_required(module: str, level: int = Level.READ) -> Callable[..., Any]:
    """Decorate a browser view so that it needs a module access level.

    A user without the right receives the "not allowed" page (HTTP 403).
    Hiding the link in the navigation is not enough (AUT-020).

    Example::

        @module_required(Module.MATERIAL, Level.WRITE)
        def item_edit(request, pk): ...
    """

    def decorator(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
            if not request_rights(request).has_level(module, level):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def require(condition: bool) -> None:
    """Raise "not allowed" unless ``condition`` holds; for checks inside a view."""
    if not condition:
        raise PermissionDenied
