# SPDX-License-Identifier: GPL-3.0-or-later
"""Several projects or service cases at once ("Massenaktionen in allen Tabellenansichten").

The requirement: tick boxes in every table, with the most basic actions – for the list of projects at
least the follow-up (*Wiedervorlage*), for the service cases the follow-up, the status and the person responsible.
The rows ticked in the list – or named in ``POST /projects/bulk`` and ``POST /service-cases/bulk`` (API-002) – get one
action:

``follow_up``
    Set the same follow-up (day, time, for whom, note) on every project (``follow_up.set_follow_up``).
``clear_follow_up``
    Take the follow-up off ("done"; ``follow_up.clear_follow_up``).
``status`` *(service cases)*
    Set the status (``service_cases.set_case_status``): *waiting*, *waiting to close* and *backlog* need the
    follow-up fields of the same request, *waiting* what the case waits for.
``manager`` *(service cases)*
    Set the person responsible (``service_cases.update_case``); the person is told as with a single case.

Every record goes through the same service function as a single one, in a step of its own, with its rules and its
entry in the change log: a project the service refuses is left as it is and named with the reason, the others are
changed. Who may: whoever may edit the project – or, for a service case, works on it as the person responsible or
taking part (AUT-033, ``projects.case_work``). A project the user may not see is reported as not found, as for a
single one.
"""

from __future__ import annotations

import datetime
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Level, Rights
from rentalars.projects import follow_up, service_cases
from rentalars.projects.access import (
    ProjectAccess,
    access_of_many,
    note_used_access,
    visible_projects,
    works_on_case,
)
from rentalars.projects.models import Project

#: The most records one action works on – the pages hold at most 1,000 rows.
MAX_PROJECTS = 1000


class BulkAction:
    """What can be done with several projects or service cases at once."""

    FOLLOW_UP = "follow_up"
    CLEAR_FOLLOW_UP = "clear_follow_up"
    STATUS = "status"
    MANAGER = "manager"

    PROJECTS = (FOLLOW_UP, CLEAR_FOLLOW_UP)
    CASES = (FOLLOW_UP, CLEAR_FOLLOW_UP, STATUS, MANAGER)


@dataclass
class Skipped:
    """A project the action left as it was, with the reason."""

    project: Project | None
    key: int
    reason: str

    @property
    def label(self) -> str:
        """``number name`` of the project, else its key."""
        return f"{self.project.number} {self.project.name}".strip() if self.project is not None else str(self.key)


@dataclass
class BulkResult:
    """What an action did: the projects it changed, those it left as they were, and why."""

    action: str
    changed: list[Project] = field(default_factory=list)
    unchanged: list[Project] = field(default_factory=list)
    skipped: list[Skipped] = field(default_factory=list)

    @property
    def changed_ids(self) -> list[int]:
        """The keys of the changed projects."""
        return [project.pk for project in self.changed]


def _reason(error: ValidationError) -> str:
    """The text of a refusal in one line."""
    return " ".join(error.messages)


def change(
    ids: Iterable[int],
    action: str,
    *,
    rights: Rights,
    user: Any,
    cases_only: bool = False,
    values: dict[str, Any] | None = None,
) -> BulkResult:
    """Do ``action`` with every project in ``ids`` that the user may change; see the module.

    Args:
        ids: Keys of the projects (or cases); repeats count once.
        action: One of :class:`BulkAction`.
        rights: The rights of the user.
        user: The user (``by`` of the changes).
        cases_only: The action is on service cases (``POST /service-cases/bulk``): a project that is none is skipped.
        values: ``on``, ``at``, ``note``, ``user`` (the follow-up), ``status``, ``waiting_for``, ``manager``.

    Raises:
        ValidationError: An unknown action, nothing chosen, too many projects, or a value the action needs is missing
            (the same for every project, so it is refused before anything is changed).
    """
    values = dict(values or {})
    keys = list(dict.fromkeys(int(pk) for pk in ids))
    allowed = BulkAction.CASES if cases_only else BulkAction.PROJECTS
    if action not in allowed:
        raise ValidationError({"action": _("Unknown action “%(action)s”.") % {"action": action}})
    if not keys:
        raise ValidationError({"ids": _("Choose at least one row.")})
    if len(keys) > MAX_PROJECTS:
        raise ValidationError({"ids": _("At most %(count)d at once.") % {"count": MAX_PROJECTS}})
    _check_values(action, values)
    found = {
        project.pk: project
        for project in visible_projects(rights, user).filter(pk__in=keys).select_related("follow_up_user", "manager")
    }
    levels = access_of_many(rights, user, list(found))
    for found_key, found_project in found.items():
        # API-010: a stored answer of this call (with an Idempotency-Key) is repeated only while the caller still has
        # the access it relied on – it names the skipped projects.
        note_used_access(user, found_project, levels.get(found_key, ProjectAccess.NONE))
    result = BulkResult(action=action)
    for key in keys:
        project = found.get(key)
        if project is None:
            result.skipped.append(Skipped(None, key, _("Not found.")))
            continue
        if cases_only and not project.is_service_case:
            result.skipped.append(Skipped(project, key, _("This is a project, not a service case.")))
            continue
        may = levels.get(key, ProjectAccess.NONE) >= ProjectAccess.EDIT or (
            project.is_service_case and rights.case_work >= Level.WRITE and works_on_case(user, project)
        )
        if not may:
            result.skipped.append(Skipped(project, key, _("You may not change this one.")))
            continue
        try:
            with transaction.atomic():
                did = _apply(project, action, values, by=user)
        except ValidationError as error:
            result.skipped.append(Skipped(project, key, _reason(error)))
            continue
        (result.changed if did else result.unchanged).append(project)
    return result


def _check_values(action: str, values: dict[str, Any]) -> None:
    """What the whole action needs, refused before any project is changed."""
    errors: dict[str, str] = {}
    if action == BulkAction.FOLLOW_UP:
        if not isinstance(values.get("on"), datetime.date):
            errors["follow_up_on"] = _("Choose the day of the follow-up.")
        if values.get("user") is None:
            errors["follow_up_user"] = _("Choose who the follow-up is for.")
    elif action == BulkAction.STATUS:
        status = values.get("status")
        if not status:
            errors["case_status"] = _("Choose the status.")
        elif status in service_cases.FOLLOW_UP_STATUSES:
            # What the status needs is the same for every case: refuse once, not once per case.
            if not isinstance(values.get("on"), datetime.date):
                errors["follow_up_on"] = _("Choose the day of the follow-up – this status needs one.")
            if status == "closing" and values.get("at") is None:
                errors["follow_up_at"] = _("Choose the time at which the service case is closed.")
            if status == "waiting" and not values.get("waiting_for"):
                errors["case_waiting_for"] = _("Choose what the service case is waiting for.")
    elif action == BulkAction.MANAGER and values.get("manager") is None:
        errors["manager"] = _("Choose the person responsible.")
    if errors:
        raise ValidationError(errors)


def _apply(project: Project, action: str, values: dict[str, Any], *, by: Any) -> bool:
    """Do the action with one project; whether anything was changed."""
    if action == BulkAction.FOLLOW_UP:
        before = (project.follow_up_on, project.follow_up_at, project.follow_up_note, project.follow_up_user_id)
        follow_up.set_follow_up(
            project,
            on=values["on"],
            at=values.get("at"),
            note=values.get("note") or "",
            user=values["user"],
            by=by,
        )
        return before != (project.follow_up_on, project.follow_up_at, project.follow_up_note, project.follow_up_user_id)
    if action == BulkAction.CLEAR_FOLLOW_UP:
        return follow_up.clear_follow_up(project)
    if action == BulkAction.STATUS:
        before_status = (project.case_status, project.case_waiting_for)
        # Only a status that needs a follow-up takes the fields of one: in the bar they are the fields of the other
        # action, and a day left in them must not set a follow-up with "in progress".
        needs_follow_up = values["status"] in service_cases.FOLLOW_UP_STATUSES
        chosen = {
            "on": values.get("on"),
            "at": values.get("at"),
            "note": values.get("note") or "",
            "user": values.get("user"),
        }
        service_cases.set_case_status(
            project,
            values["status"],
            waiting_for=values.get("waiting_for") or "",
            follow_up=chosen if needs_follow_up and chosen["on"] is not None else None,
            by=by,
        )
        return before_status != (project.case_status, project.case_waiting_for) or needs_follow_up
    # BulkAction.MANAGER
    if project.manager_id == values["manager"].pk:
        return False
    service_cases.update_case(project, user=by, manager=values["manager"])
    return True


def summary(result: BulkResult) -> list[tuple[str, str]]:
    """The messages after an action in the browser: ``(level, text)`` – what changed, then each refusal."""
    messages_out: list[tuple[str, str]] = []
    if result.changed:
        messages_out.append(("success", _("%(count)d changed.") % {"count": len(result.changed)}))
    if result.unchanged:
        messages_out.append(("info", _("%(count)d were that way already.") % {"count": len(result.unchanged)}))
    for skipped in result.skipped[:10]:
        messages_out.append(("warning", f"{skipped.label}: {skipped.reason}"))
    if len(result.skipped) > 10:
        messages_out.append(("warning", _("And %(count)d more were skipped.") % {"count": len(result.skipped) - 10}))
    return messages_out
