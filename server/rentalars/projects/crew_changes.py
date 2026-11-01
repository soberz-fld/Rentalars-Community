# SPDX-License-Identifier: GPL-3.0-or-later
"""Planned firmly, and what the planned person is told about their deployment (PER-041, PRJ-118).

The requirement: personnel can also be planned firmly, without a request; the person concerned gets a notification of these changes.

Planned firmly (``RequestStatus.FIRM``, PER-016)
------------------------------------------------
A planner may plan a person without asking: when adding the line, in the dialog of the line, in its row and for
several chosen lines (``crew_bulk``). The line counts like an accepted request – "Meine Einsätze", the deployment
view and the calendars of the person show it as theirs, the personnel plan as planned – and the person is told. A
line accepted already stays "accepted". In the dialog "planned firmly" can be taken back; the line is then "not
asked" and can be asked.

New times of a line planned firmly never ask the person again – PER-034 asks again only lines that were asked or
accepted. The line stays planned firmly for its new times, and the person is told them.

What the person is told (``Kind.DEPLOYMENT_CHANGE``, "Änderung meines Einsatzes")
-------------------------------------------------------------------------------
* planned firmly – with meeting point and note;
* a change of times, meeting point, note, phase, job function or vehicle (:data:`NOTICED_FIELDS`), each with its
  value before – not hours, prices or rates, which the person does not plan by;
* taken off: the line deleted, or somebody else – or nobody – put on it.

Told is only a person with an active account, never the one who made the change, not about a cancelled project,
a deployment that is over or a line the person declined. A line asked again for its new times (PER-034) gets the
request instead, which names the other changes too. One notification per person and action: whatever runs inside
:func:`one_notice_per_person` – several lines changed at once, a phase moved with its crew – tells each person
once, naming all their lines.
"""

from __future__ import annotations

import datetime
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from django.urls import reverse
from django.utils import formats, timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from rentalars.core.i18n import for_user, local_pattern
from rentalars.projects.models import CrewLine, ProjectStatus, RequestStatus

#: What the person is told about when it changes; "times" stands for start and end together.
NOTICED_FIELDS = ("meeting_point", "note", "phase", "job_function", "vehicle_line", "is_driver")

#: The kinds of notice.
FIRM = "firm"
CHANGED = "changed"
REMOVED = "removed"


@dataclass(frozen=True)
class Change:
    """One thing that changed on a line: ``field`` is a name of :data:`NOTICED_FIELDS` or ``"times"``."""

    field: str
    old: Any
    new: Any


@dataclass
class Notice:
    """What to tell one person about one of their deployments."""

    kind: str
    person: Any
    project: Any
    #: The deployment as the person knows it now – for a line taken away as it was.
    function: str
    start: datetime.datetime
    end: datetime.datetime
    meeting_point: str = ""
    note: str = ""
    changes: list[Change] = field(default_factory=list)


def snapshot(line: CrewLine) -> dict[str, Any]:
    """The values of a line before a change: what is noticed, who is planned, how the request stands."""
    return {
        "pk": line.pk,
        "person": line.person if line.person_id else None,
        "project": line.project,
        "request_status": line.request_status,
        "start": line.start,
        "end": line.end,
        "title": line.title,
        **{name: _value(line, name) for name in NOTICED_FIELDS},
    }


def _value(line: CrewLine, name: str) -> Any:
    if name in ("phase", "vehicle_line"):
        return getattr(line, name) if getattr(line, f"{name}_id") else None
    return getattr(line, name)


def _key(value: Any) -> Any:
    return value.pk if hasattr(value, "pk") else value


def differences(before: dict[str, Any], line: CrewLine, *, times: bool = True) -> list[Change]:
    """What changed on a line that the person is told about; ``times=False`` leaves the times out."""
    changes: list[Change] = []
    if times and (before["start"], before["end"]) != (line.start, line.end):
        changes.append(Change("times", (before["start"], before["end"]), (line.start, line.end)))
    for name in NOTICED_FIELDS:
        new = _value(line, name)
        if _key(before[name]) != _key(new):
            changes.append(Change(name, before[name], new))
    return changes


def _moment(value: datetime.datetime) -> str:
    return formats.date_format(timezone.localtime(value), local_pattern("D d.m. H:i"))


def _period(start: datetime.datetime, end: datetime.datetime) -> str:
    return f"{_moment(start)} – {_moment(end)}"


def _shown(name: str, value: Any) -> str:
    if value is None or value == "":
        return ""
    if name == "phase":
        return value.label
    if name == "job_function":
        return value.name
    if name == "vehicle_line":
        return value.crew_label
    return str(value)


def change_texts(changes: Iterable[Change]) -> list[str]:
    """The changes as lines of text, in the active language: "Treffpunkt: Halle 3 (vorher: Tor 1)"."""
    labels = {
        "meeting_point": _("Meeting point"),
        "phase": _("Phase"),
        "job_function": _("Job function"),
        "vehicle_line": _("Vehicle"),
    }
    texts = []
    for change in changes:
        if change.field == "times":
            texts.append(
                _("New times: %(new)s (before: %(old)s)") % {"new": _period(*change.new), "old": _period(*change.old)}
            )
        elif change.field == "note":
            texts.append(_("New note: %(note)s") % {"note": change.new} if change.new else _("The note was removed."))
        elif change.field == "is_driver":
            texts.append(_("You drive the vehicle.") if change.new else _("You no longer drive the vehicle."))
        else:
            old, new = _shown(change.field, change.old), _shown(change.field, change.new)
            values = {"what": labels[change.field], "old": old, "new": new}
            if not new:
                texts.append(_("%(what)s removed (before: %(old)s)") % values)
            elif not old:
                texts.append(_("%(what)s: %(new)s") % values)
            else:
                texts.append(_("%(what)s: %(new)s (before: %(old)s)") % values)
    return texts


# --- Collecting and sending ------------------------------------------------------------------------------------

_pending: ContextVar[list[Notice] | None] = ContextVar("rentalars_crew_notices", default=None)


@contextmanager
def one_notice_per_person() -> Iterator[list[Notice]]:
    """Collect the notices of everything done inside, and tell each person once at the end.

    Nested blocks collect into the outermost one. Nothing is sent when the
    block fails. The list yielded is the collection: a caller that undoes
    one step (a line of several that was refused) removes its notices.
    """
    pending = _pending.get()
    if pending is not None:
        yield pending
        return
    collected: list[Notice] = []
    token = _pending.set(collected)
    try:
        yield collected
    finally:
        _pending.reset(token)
    send(collected)


def _account(person: Any) -> Any:
    account = getattr(person, "user", None) if person is not None else None
    return account if account is not None and account.is_active else None


def _report(notice: Notice, *, status: str, ends: Iterable[datetime.datetime]) -> None:
    """Keep a notice for the end of the action – or send it now – if it concerns the person at all."""
    if _account(notice.person) is None or status == RequestStatus.DECLINED:
        return
    if notice.project.status == ProjectStatus.CANCELLED or max(ends) < timezone.now():
        return  # no deployment any more, or one that is over
    pending = _pending.get()
    if pending is None:
        send([notice])
    else:
        pending.append(notice)


def _notice(kind: str, line: CrewLine, changes: list[Change] | None = None) -> Notice:
    return Notice(
        kind=kind,
        person=line.person,
        project=line.project,
        function=line.job_function.name,
        start=line.start,
        end=line.end,
        meeting_point=line.meeting_point,
        note=line.note,
        changes=changes or [],
    )


def note_firm(lines: Iterable[CrewLine]) -> None:
    """Tell the people of new lines planned firmly (``crew.add_crew_lines``)."""
    with one_notice_per_person():
        for line in lines:
            if line.person_id is not None:
                _report(_notice(FIRM, line), status=line.request_status, ends=[line.end])


def note_removed(before: dict[str, Any]) -> None:
    """Tell the person of a line deleted – or given to somebody else – that they are no longer planned."""
    person = before["person"]
    if person is None:
        return
    notice = Notice(
        kind=REMOVED,
        person=person,
        project=before["project"],
        function=before["job_function"].name,
        start=before["start"],
        end=before["end"],
    )
    _report(notice, status=before["request_status"], ends=[before["end"]])


def note_update(line: CrewLine, before: dict[str, Any]) -> None:
    """After a line was saved: tell whoever it concerns (see the module description).

    Called by ``crew.update_crew_line`` and ``crew.move_with_phase`` with
    the :func:`snapshot` taken before the change.
    """
    old_person = before["person"]
    if old_person is not None and old_person.pk != line.person_id:
        note_removed(before)
        if line.person_id is not None and line.request_status == RequestStatus.FIRM:
            _report(_notice(FIRM, line), status=line.request_status, ends=[line.end])
        return
    if line.person_id is None:
        return
    changes = differences(before, line)
    if before["request_status"] != RequestStatus.FIRM and line.request_status == RequestStatus.FIRM:
        _report(_notice(FIRM, line, changes), status=line.request_status, ends=[line.end])
        return
    if not changes or getattr(line, "asked_again", None) is not None:
        return  # nothing to tell – or the request for the new times tells it (PER-034)
    _report(_notice(CHANGED, line, changes), status=line.request_status, ends=[before["end"], line.end])


def _deployment(notice: Notice) -> str:
    """The deployment as the requests name it: "Stadtfest as Tontechnik, Mi 10.03. 08:00 – Mi 10.03. 18:00"."""
    return _("%(project)s as %(function)s, %(start)s – %(end)s") % {
        "project": notice.project,
        "function": notice.function,
        "start": _moment(notice.start),
        "end": _moment(notice.end),
    }


def _details(notice: Notice) -> list[str]:
    """The lines below a deployment: for "planned firmly" meeting point and note, else what changed."""
    if notice.kind == REMOVED:
        return []
    if notice.kind == FIRM:
        lines = [_("Meeting point: %(place)s") % {"place": notice.meeting_point}] if notice.meeting_point else []
        if notice.note:
            lines.append(notice.note)
        return lines + change_texts(
            change for change in notice.changes if change.field not in ("meeting_point", "note")
        )
    return change_texts(notice.changes)


def _title(kind: str, notices: list[Notice]) -> str:
    if len(notices) == 1:
        texts = {
            FIRM: _("Planned firmly: %(deployment)s"),
            CHANGED: _("Deployment changed: %(deployment)s"),
            REMOVED: _("No longer planned: %(deployment)s"),
        }
        return texts[kind] % {"deployment": _deployment(notices[0])}
    projects = ", ".join(dict.fromkeys(str(notice.project) for notice in notices))
    count = len(notices)
    if kind == FIRM:
        text = ngettext(
            "Planned firmly for %(count)d deployment: %(projects)s",
            "Planned firmly for %(count)d deployments: %(projects)s",
            count,
        )
    elif kind == REMOVED:
        text = ngettext(
            "No longer planned for %(count)d deployment: %(projects)s",
            "No longer planned for %(count)d deployments: %(projects)s",
            count,
        )
    else:
        text = ngettext(
            "%(count)d deployment changed: %(projects)s", "%(count)d deployments changed: %(projects)s", count
        )
    return text % {"count": count, "projects": projects}


def send(notices: list[Notice]) -> int:
    """Tell each person once about all their notices (``Kind.DEPLOYMENT_CHANGE``); returns how many were told.

    Written in the language of the person (UIX-029). The one who made the
    change is left out – a person changing their own line is not told.
    """
    from rentalars.notifications.models import Kind
    from rentalars.notifications.services import notify
    from rentalars.projects.crew import _acting_user

    by_person: dict[int, list[Notice]] = {}
    for notice in notices:
        by_person.setdefault(notice.person.pk, []).append(notice)
    if not by_person:
        return 0
    actor = _acting_user()
    told = 0
    for own in by_person.values():
        account = _account(own[0].person)
        if account is None or (actor is not None and account.pk == actor.pk):
            continue
        kinds = {notice.kind for notice in own}
        kind = own[0].kind if len(kinds) == 1 else CHANGED
        with for_user(account):
            title = _title(kind, own)
            if len(own) == 1:
                body = "\n".join(_details(own[0]))
            else:
                body = "\n\n".join("\n".join([_deployment(notice), *_details(notice)]) for notice in own)
        projects = {notice.project.pk for notice in own}
        project = own[0].project if len(projects) == 1 else None
        if project is not None and kind != REMOVED:
            url = reverse("projects:deployment", args=[project.pk])
        else:
            url = reverse("projects:my_deployments")  # taken off: the deployment view of the project is closed
        if notify([account], Kind.DEPLOYMENT_CHANGE, title, body=body, url=url, project=project):
            told += 1
    return told
