# SPDX-License-Identifier: GPL-3.0-or-later
"""When each field of a project last changed – for the offline sync of the companion app (PRJ-113, PRJ-114).

The Android app (chapter 5.16) changes projects and service cases without
network and sends the changes later. The rule is that the younger
change wins: a change from the phone counts only if it was made later than
the last change of the same field on the server. For that the server notes,
for every field, when it last changed.

What is noted
-------------
``Project.field_changed_at`` maps a *key* to the moment of the last change
(UTC, ISO 8601). A key is the name the API uses for a field; two stand for
several fields of the model (:data:`TRACKED`):

* ``follow_up`` – day, time, note and user of the follow-up (PRJ-105, PRJ-109);
* ``case_status`` – the status of a service case together with what it waits
  for (PRJ-090, PRJ-112).

The API shows them as ``field_changed_at`` on ``/projects`` and
``/service-cases`` (:func:`times_of`); the ``case_status`` time of a service
case once more as ``case_status_changed_at``, the name the mobile app
uses – one value, two names. A key never noted (a project written with
``bulk_create``, such as the load test data) counts from ``created_at``.

Where it is noted
-----------------
In ``Project.save`` (:func:`stamp`), whatever way the change takes: forms in
the browser, the API, automations, imports, status actions, the follow-up
dialog, packing setting "out" or "returned", converting a service case. The
fields as they were loaded – or last saved – are compared with those being
saved; every key with a changed field gets the moment. A new project gets its
moment of creation for every key. Only ``QuerySet.update()`` bypasses
``save()``; no business code changes a tracked field that way (only the
bookkeeping field ``follow_up_notified_at``, which is not tracked).

The moment is the server's clock – unless a call of the API carries the
moment a change was made on the phone (:func:`changes_at`): the keys it
applies to get that moment, so that a change made on another device in
between still counts (as PCK-027). A stored moment never goes back.

The rule (:func:`judge`)
------------------------
* A sent field counts only if its moment is *later* than the stored moment of
  its key; at the same moment the server wins.
* A moment in the future counts as now – the clock read once the project is
  locked (the clock rule of PCK-027, ``packing.offline``).
* Comparing and writing happen under the write lock of the API (API-010): the
  lock row of the project and its own row (``SELECT … FOR UPDATE``), held
  until the change is committed (:func:`locked`).
* A field that counts is noted with its moment even if its value stays the
  same (:func:`note`): a later change counts from it.
"""

from __future__ import annotations

import datetime
import functools
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _

if TYPE_CHECKING:
    from rentalars.projects.models import Project

#: The keys and the fields of the model each stands for (PRJ-113: at least name, venue, start, end,
#: event_start, event_end, notes, status, follow_up; PRJ-114: case_status). Every field a call of the API can
#: change on a project or a service case has its key, so that ``changed_at`` can judge it.
TRACKED: dict[str, tuple[str, ...]] = {
    "name": ("name",),
    "customer": ("customer",),
    "is_internal": ("is_internal",),
    "contact": ("contact",),
    "billing_address": ("billing_address",),
    "delivery_address": ("delivery_address",),
    "venue_site": ("venue_site",),
    "venue": ("venue",),
    "manager": ("manager",),
    "start": ("start",),
    "end": ("end",),
    "event_start": ("event_start",),
    "event_end": ("event_end",),
    "rental_days": ("rental_days",),
    "notes": ("notes",),
    "status": ("status",),
    "follow_up": ("follow_up_on", "follow_up_at", "follow_up_note", "follow_up_user"),
    "overall_discount": ("overall_discount_percent", "overall_discount_amount"),  # PRJ-123
    "case_status": ("case_status", "case_waiting_for"),
    "case_contact": ("case_contact",),
}

#: The keys ``/projects`` shows.
PROJECT_KEYS = (
    "name",
    "customer",
    "is_internal",
    "contact",
    "billing_address",
    "delivery_address",
    "venue_site",
    "venue",
    "manager",
    "start",
    "end",
    "event_start",
    "event_end",
    "rental_days",
    "notes",
    "status",
    "follow_up",
    "overall_discount",
)

#: ``/projects`` shows these as well for a service case (read there, changed under ``/service-cases``).
CASE_EXTRA_KEYS = ("case_status", "case_contact")

#: The keys ``/service-cases`` shows (PRJ-114).
CASE_KEYS = ("name", "customer", "contact", "case_contact", "notes", "manager", "case_status", "follow_up")

#: The name of a field (in the model and in the API) → its key.
KEY_OF: dict[str, str] = {name: key for key, names in TRACKED.items() for name in names}

#: The moments of a change from the API: ``(project ID, {key: moment})`` while :func:`changes_at` holds.
_moments: ContextVar[tuple[int, dict[str, datetime.datetime]] | None] = ContextVar(
    "rentalars_field_moments", default=None
)


@functools.cache
def _attnames() -> dict[str, str]:
    """Field name → column attribute (``customer`` → ``customer_id``) of every tracked field."""
    from rentalars.projects.models import Project

    return {name: Project._meta.get_field(name).attname for names in TRACKED.values() for name in names}


def _text(moment: datetime.datetime) -> str:
    """How a moment is stored: UTC, ISO 8601, to the microsecond."""
    return moment.astimezone(datetime.UTC).isoformat()


def _parse(value: Any) -> datetime.datetime | None:
    """A stored moment; ``None`` for none (or one that cannot be read)."""
    if not value:
        return None
    try:
        moment = datetime.datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return moment if timezone.is_aware(moment) else timezone.make_aware(moment, datetime.UTC)


def _normal(name: str, value: Any) -> Any:
    """A value of a field in the form it is compared in: as the database returns it, naive moments made aware."""
    from rentalars.projects.models import Project

    try:
        value = Project._meta.get_field(name).to_python(value)
    except ValidationError:
        return value
    if isinstance(value, datetime.datetime) and timezone.is_naive(value):
        value = timezone.make_aware(value)
    return value


def values_of(project: Project) -> dict[str, Any]:
    """The tracked fields of a project as they are in memory (without fields not loaded)."""
    deferred = project.get_deferred_fields()
    return {attname: getattr(project, attname) for attname in _attnames().values() if attname not in deferred}


def known_values(project: Project) -> dict[str, Any] | None:
    """The fields as last loaded or saved; ``None`` if unknown (the project was built by hand)."""
    noted = getattr(project, "_field_values", None)
    if noted is not None:
        return noted
    loaded = getattr(project, "_audit_loaded", None)  # the raw values of the load (``core.audit``)
    if loaded is not None:
        return dict(zip(*loaded, strict=False))
    return None


def after_refresh(
    project: Project, before: dict[str, Any] | None, fields: Iterable[str] | None
) -> dict[str, Any] | None:
    """What the next save compares with after ``refresh_from_db``: the reloaded fields as stored now.

    A deferred field loaded on first use reloads that field only; changes of
    the others not saved yet still count as changes.
    """
    if fields is None:
        return values_of(project)
    if before is None:
        return None
    wanted = set(fields)
    current = values_of(project)
    reloaded = {attname for name, attname in _attnames().items() if name in wanted or attname in wanted}
    return {**before, **{attname: value for attname, value in current.items() if attname in reloaded}}


def _stored_row(project: Project) -> dict[str, Any] | None:
    """The tracked fields as the database holds them – for a project whose loaded values are not known."""
    from rentalars.projects.models import Project

    rows = Project._base_manager.using(project._state.db or "default").filter(pk=project.pk)
    return rows.values(*_attnames().values()).first()


def _saved_names(update_fields: Iterable[str] | None) -> list[str]:
    """The tracked fields a save writes: all, or those among ``update_fields`` (by name or attribute)."""
    attnames = _attnames()
    if update_fields is None:
        return list(attnames)
    wanted = set(update_fields)
    return [name for name, attname in attnames.items() if name in wanted or attname in wanted]


def _changed_keys(project: Project, names: list[str], before: dict[str, Any]) -> set[str]:
    """The keys of those fields whose value differs from ``before``."""
    attnames = _attnames()
    deferred = project.get_deferred_fields()
    keys: set[str] = set()
    for name in names:
        attname = attnames[name]
        if attname in deferred or KEY_OF[name] in keys:
            continue
        if attname not in before or _normal(name, before[attname]) != _normal(name, getattr(project, attname)):
            keys.add(KEY_OF[name])
    return keys


def stamp(project: Project, update_fields: Iterable[str] | None) -> tuple[Iterable[str] | None, dict[str, Any] | None]:
    """Note the moment of every key whose fields this save changes – called by ``Project.save`` (PRJ-113).

    Returns the ``update_fields`` to save with (``field_changed_at`` added
    where a partial save stamps something) and the tracked values after the
    save, which the next save compares with.
    """
    now = timezone.now()
    if project._state.adding or project.pk is None:
        project.field_changed_at = dict.fromkeys(TRACKED, _text(now))
        return update_fields, values_of(project)
    names = _saved_names(update_fields)
    before = known_values(project)
    if not names:
        return update_fields, before
    if before is None:
        before = _stored_row(project) or {}
    keys = _changed_keys(project, names, before)
    current = values_of(project)
    written = {_attnames()[name] for name in names}
    after = {**before, **{attname: value for attname, value in current.items() if attname in written}}
    if not keys:
        return update_fields, after
    if update_fields is None:
        times = dict(project.field_changed_at or {})
    else:
        # Only some fields are written: start from the moments as stored now, so that none of another
        # change in between goes back.
        from rentalars.projects.models import Project

        stored = Project._base_manager.using(project._state.db or "default").filter(pk=project.pk)
        times = dict(stored.values_list("field_changed_at", flat=True).first() or {})
    moments = _moments_for(project)
    for key in keys:
        moment = moments.get(key, now)
        noted = _parse(times.get(key))
        times[key] = _text(max(moment, noted) if noted is not None else moment)
    project.field_changed_at = times
    if update_fields is not None and "field_changed_at" not in update_fields:
        update_fields = [*update_fields, "field_changed_at"]
    return update_fields, after


def _moments_for(project: Project) -> dict[str, datetime.datetime]:
    """The moments a change from the API set for this project (:func:`changes_at`); empty otherwise."""
    current = _moments.get()
    if current is None or project.pk is None or current[0] != project.pk:
        return {}
    return current[1]


@contextmanager
def changes_at(project: Project, moments: Mapping[str, datetime.datetime]) -> Iterator[None]:
    """Let the changes of these keys of this project carry these moments instead of the server's clock.

    Every other key – and every other project, such as the parts a whole
    project takes along – is noted with the server's clock.
    """
    token = _moments.set((project.pk, dict(moments)))
    try:
        yield
    finally:
        _moments.reset(token)


def times_of(project: Project) -> dict[str, datetime.datetime]:
    """The moment of the last change of every key; ``created_at`` where none is noted."""
    stored = project.field_changed_at or {}
    return {key: _parse(stored.get(key)) or project.created_at for key in TRACKED}


def note(project: Project, moments: Mapping[str, datetime.datetime]) -> None:
    """Note these keys with at least these moments – also where the value did not change.

    A later change counts from the moment, as with PCK-027.
    """
    times = times_of(project)
    behind = {key: moment for key, moment in moments.items() if times[key] < moment}
    if not behind:
        return
    stored = dict(project.field_changed_at or {})
    stored.update({key: _text(moment) for key, moment in behind.items()})
    project.field_changed_at = stored
    project.save(update_fields=["field_changed_at"])


def judge(project: Project, moments: Mapping[str, datetime.datetime]) -> tuple[list[str], list[str]]:
    """Which keys count: those whose moment is later than the stored one (equal: the server wins).

    Returns:
        The keys that count and the keys that are older, each in the order of :data:`TRACKED`.
    """
    times = times_of(project)
    applied = [key for key in TRACKED if key in moments and moments[key] > times[key]]
    older = [key for key in TRACKED if key in moments and moments[key] <= times[key]]
    return applied, older


def ordered(keys: Iterable[str]) -> list[str]:
    """Keys in the order of :data:`TRACKED`, for the answer ``applied``."""
    wanted = set(keys)
    return [key for key in TRACKED if key in wanted]


def parse_moment(value: Any, name: str = "changed_at") -> datetime.datetime | None:
    """The moment a client sends (ISO 8601 with its time zone); ``None`` if none is sent.

    A ``+02:00`` in an address that was not encoded arrives as `` 02:00`` and is read as meant.

    Raises:
        ValidationError: The value is no moment, or has no time zone.
    """
    if isinstance(value, list | tuple):
        value = value[-1] if value else None
    if value in (None, ""):
        return None
    # The text of the packlist sync (PCK-027), so that the API says it in one way.
    message = _("Give the moment in ISO 8601 with a time zone, e.g. 2026-10-14T09:30:00+02:00.")
    if isinstance(value, datetime.datetime):
        moment: datetime.datetime | None = value
    else:
        text = str(value).strip()
        moment = _read(text)
        if moment is None and " " in text:
            head, _space, tail = text.rpartition(" ")
            moment = _read(f"{head}+{tail}")
    if moment is None or timezone.is_naive(moment):
        raise ValidationError({name: message})
    return moment


def _read(text: str) -> datetime.datetime | None:
    try:
        return parse_datetime(text)
    except ValueError:
        return None


@contextmanager
def locked(project: Project) -> Iterator[tuple[Project, datetime.datetime]]:
    """Compare and write under the write lock of the API (API-010); yields the project as stored now and the clock.

    The lock row of the project is the one ``If-Match`` takes – a change with
    ``If-Match`` and one with ``changed_at`` wait for each other – and the
    row of the project is locked as well, so that a change from the browser
    waits too. The clock is read once both are held: no change the server
    took before is later than it (PCK-027).
    """
    from rentalars.api.safeguards import _take_lock
    from rentalars.projects.models import Project

    with transaction.atomic():
        _take_lock(f"record:{Project._meta.label_lower}:{project.pk}")
        current = Project._base_manager.select_for_update().get(pk=project.pk)
        yield current, timezone.now()
