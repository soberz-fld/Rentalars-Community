# SPDX-License-Identifier: GPL-3.0-or-later
"""Working on a service case as the person responsible or as somebody taking part (AUT-033; PRJ-090, PRJ-108).

The problem: a service case assigned to a person with the role crew told the person that they are responsible, but they could neither see nor open it. Decided: the crew taking part can do everything needed to work on it (correspondence, chat, status). Important: correspondence in projects is always confidential, in service cases normally not, because there it is more about fixing the fault.

The rule
--------
The person responsible for a service case (its ``manager``) and the people
taking part in it (PRJ-108) work on that case – whatever their roles say,
also without the module "projects" and without the correspondence rights:

* they open it (``projects.access``: *read*): the page of the case, its
  documents, chat, correspondence, access and history as far as these pages
  show them to readers;
* they change it: subject, customer, contact, description and the person
  responsible, the status with its follow-up, the people taking part, the
  open items, the follow-up;
* they read and write its chat and its correspondence: read, write and
  answer mails, write and change notes.

Not part of it: turning the case into a project, deleting it or its mails,
its members, prices (only through the price right), any other case or
project. Correspondence of projects stays confidential: it needs the special
rights, as before. A read-only API token only reads; a token without the
module "projects" gets nothing of it (``Rights.case_work``).

EML-055 (``mail.locks``): what is written here is the *basis* of reading
the correspondence. Of its messages, those with lock need the price right in
addition – without it, whoever works on the case reads and answers its open
messages; the crew planned in a project reads the open messages of the project.

Each page and endpoint that is part of this work loads the case with
``project_for(..., case_work=True)`` and asks the helpers here; at the door
:func:`case_work_required` (pages) and :class:`CaseWorkPermission` (API)
take the place of the plain module check.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest
from rest_framework.permissions import SAFE_METHODS

from rentalars.accounts.rights import Level, Module, SpecialRight, request_rights
from rentalars.api.permissions import ModulePermission
from rentalars.projects.access import ProjectAccess, note_case_work, works_on_case
from rentalars.projects.models import Project, ProjectKind


def _case_of(pk: Any) -> Project | None:
    """The service case with this key, with what :func:`works_on_case` needs; ``None`` for anything else."""
    if pk is None:
        return None
    pk = getattr(pk, "pk", pk)
    if not str(pk).isdigit():
        return None
    return Project.objects.filter(pk=int(pk), kind=ProjectKind.SERVICE_CASE).only("pk", "kind", "manager_id").first()


def works_on(request: HttpRequest | Any, pk: Any, *, change: bool = False) -> bool:
    """Whether the user of the request works on the service case with this key – and may change it (``change``)."""
    rights = request_rights(request)
    needed = Level.WRITE if change else Level.READ
    if rights.case_work < needed:
        return False
    case = _case_of(pk)
    return case is not None and works_on_case(request.user, case)


def _ensure_noted(request: HttpRequest | Any, project: Project) -> None:
    if not hasattr(project, "may_work_on_case"):
        note_case_work(project, request_rights(request), request.user)


def may_change_case(request: HttpRequest | Any, case: Project) -> bool:
    """Whether the user may change the service case: edit it with the right to write projects, or work on it."""
    _ensure_noted(request, case)
    rights = request_rights(request)
    if getattr(case, "access", ProjectAccess.NONE) >= ProjectAccess.EDIT and rights.can_write(Module.PROJECTS):
        return True
    return bool(case.may_work_on_case)


def may_read_correspondence(request: HttpRequest | Any, project: Project) -> bool:
    """Whether the user may read the correspondence of this project (EML-029; AUT-033 for service cases).

    Projects: the special right. Service cases: the special right, or working on the case.
    """
    if request_rights(request).has(SpecialRight.CORRESPONDENCE_READ):
        return True
    if not project.is_service_case:
        return False
    _ensure_noted(request, project)
    return bool(project.works_on_case)


def may_write_correspondence(request: HttpRequest | Any, project: Project) -> bool:
    """Whether the user may write mails and notes in this project (EML-024, EML-051; AUT-033 for service cases).

    Projects: both correspondence rights. Service cases: those, or working on the case.
    """
    rights = request_rights(request)
    if rights.has(SpecialRight.CORRESPONDENCE_READ) and rights.has(SpecialRight.CORRESPONDENCE_WRITE):
        return True
    if not project.is_service_case:
        return False
    _ensure_noted(request, project)
    return bool(project.may_work_on_case)


def require(condition: bool) -> None:
    """Refuse (HTTP 403) unless ``condition`` holds."""
    if not condition:
        raise PermissionDenied


def case_work_required(level: int = Level.READ, *, kwarg: str = "pk") -> Callable[..., Any]:
    """Decorate a page of a project that is part of working on a service case.

    Lets the request in if the user has the module "projects" at ``level`` –
    or if the project in the address (``kwarg``) is a service case the user
    works on: reading for ``Level.READ``, changing for more. The view then
    loads the project with ``project_for(..., case_work=True)``.
    """

    def decorator(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
            if not request_rights(request).has_level(Module.PROJECTS, level) and not works_on(
                request, kwargs.get(kwarg), change=level > Level.READ
            ):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


class CaseWorkPermission(ModulePermission):
    """The module check of an API view – or, for the operations named, working on the case (AUT-033).

    A view names in ``case_work_actions`` the actions (or, for an ``APIView``,
    ``"*"``) that are part of working on a service case, and in
    ``case_work_kwarg`` the name of the key of the project in the address
    (default ``pk``). A list without a project in the address (``GET
    /service-cases``) lets in whoever may work on cases at all; the view's
    queryset then holds the cases (``visible_projects``).
    """

    def has_permission(self, request: Any, view: Any) -> bool:
        """The module level, or working on the case of the address."""
        if super().has_permission(request, view):
            return True
        if not request.user or not request.user.is_authenticated:
            return False
        actions = getattr(view, "case_work_actions", ())
        action = getattr(view, "action", None) or "*"
        if action not in actions and "*" not in actions:
            return False
        pk = view.kwargs.get(getattr(view, "case_work_kwarg", "pk"))
        if pk is None:
            return action == "list" and request_rights(request).case_work >= Level.READ
        return works_on(request, pk, change=request.method not in SAFE_METHODS)
