# SPDX-License-Identifier: GPL-3.0-or-later
"""Change log: who changed what and when (ADM-005, MAT-025, PRJ-009, PRJ-032).

How it works
------------
Every model that inherits from :class:`AuditedModel` writes a row into
``AuditLogEntry`` whenever an object is created, changed or deleted through
``save()`` or ``delete()``. The row stores the old and the new value of every
changed field.

*Who* made the change is not passed around as a parameter. A middleware (for
browser and API requests) or a ``with acting_as(...)`` block (for commands and
imports) remembers the current actor in a context variable, and the log reads
it from there. The benefit: no code path can forget to log, including the
administration interface (ADM-007).

Known trap: ``QuerySet.update()`` and ``bulk_create()`` bypass ``save()`` and
therefore the log. Business code uses them only where the log is written
explicitly or deliberately not wanted (generated load-test data).

Example::

    with acting_as("system:import"):
        item.status = ItemStatus.DEFECTIVE
        item.save()      # logs {"status": ["available", "defective"]}
"""

from __future__ import annotations

import copy
import datetime
import decimal
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from django.conf import settings
from django.db import models
from django.utils import translation

if TYPE_CHECKING:
    from rentalars.accounts.models import User
    from rentalars.core.models import AuditLogEntry


@dataclass(frozen=True)
class Actor:
    """The user or background job responsible for the current changes."""

    user_id: int | None
    label: str


_current_actor: ContextVar[Actor | None] = ContextVar("rentalars_current_actor", default=None)


def _to_actor(user_or_label: User | str | None) -> Actor | None:
    """Turn a user object or a job label into an :class:`Actor`."""
    if user_or_label is None:
        return None
    if isinstance(user_or_label, str):
        return Actor(user_id=None, label=user_or_label)
    if not getattr(user_or_label, "is_authenticated", False):
        return None
    return Actor(user_id=user_or_label.pk, label=str(user_or_label))


def set_current_actor(user_or_label: User | str | None) -> None:
    """Remember the actor for the rest of the current request or task."""
    _current_actor.set(_to_actor(user_or_label))


def get_current_actor() -> Actor | None:
    """Return the actor remembered for the current request or task."""
    return _current_actor.get()


@contextmanager
def acting_as(user_or_label: User | str | None) -> Iterator[None]:
    """Attribute all changes inside the ``with`` block to the given actor.

    Args:
        user_or_label: A user object, or a text such as ``"system:import"``
            for jobs that run without a user.
    """
    token = _current_actor.set(_to_actor(user_or_label))
    try:
        yield
    finally:
        _current_actor.reset(token)


def _serialise(value: Any) -> Any:
    """Convert a field value into something JSON can store.

    Decimals and dates become text so that no precision is lost; ``Decimal("20.00")``
    is stored as ``"20.00"``, never as the float ``20.0`` (NFA-003).
    """
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, datetime.datetime | datetime.date | datetime.time):
        return value.isoformat()
    if isinstance(value, models.fields.files.FieldFile):
        return value.name or ""
    return value


class AuditedModel(models.Model):
    """Base class for all models whose changes must be traceable.

    Subclasses may set:

    ``audit_exclude``
        Field names that are never logged, for example password hashes or
        timestamps that change on every save.
    ``audit_sensitive``
        Maps a field name to the special right (``SpecialRight`` value) a
        reader needs to see its values in the log. Prices stay hidden from
        users without the price right even in the history (AUT-019).

    Subclasses may override :meth:`audit_parent` so that the entry also shows
    up in the history of a parent object, e.g. a material line in the history
    of its project (PRJ-032).
    """

    audit_exclude: ClassVar[frozenset[str]] = frozenset()
    audit_sensitive: ClassVar[dict[str, str]] = {}

    #: The comparable field values as of the last load or save, see ``_audit_before``.
    _audit_snapshot: dict[str, Any] | None = None
    #: The raw values the object was loaded with: ``(column names, values)``.
    _audit_loaded: tuple[Any, Any] | None = None

    class Meta:
        abstract = True

    @classmethod
    def from_db(cls, db: Any, field_names: Any, values: Any) -> Any:
        """Remember the loaded values to compare against when saving.

        Only the raw values are kept here. Turning them into a comparable
        snapshot is left to :meth:`_audit_before`, which runs when the object
        is saved. Most objects are loaded to be shown, not to be changed; a
        planning page with 500 lines would otherwise spend a third of its
        time on snapshots nobody reads.
        """
        instance = super().from_db(db, field_names, values)
        if any(type(value) in (dict, list) for value in values):
            # JSON values can be changed in place; keep an independent copy.
            values = [copy.deepcopy(value) if type(value) in (dict, list) else value for value in values]
        instance._audit_loaded = (field_names, values)
        instance._audit_snapshot = None
        return instance

    def refresh_from_db(self, *args: Any, **kwargs: Any) -> None:
        """Reload the object; what is in the database now is the new starting point."""
        super().refresh_from_db(*args, **kwargs)
        self._audit_loaded = None
        self._audit_snapshot = self._audit_values()

    def _is_logged(self, field: Any) -> bool:
        """Whether changes of a field are written to the log."""
        if field.primary_key:
            return False
        return field.name not in self.audit_exclude and field.attname not in self.audit_exclude

    def _audit_before(self) -> dict[str, Any] | None:
        """Return the logged field values as they were before the current changes.

        ``None`` means the object was never loaded from the database (it is
        new, or was built by hand), so there is nothing to compare with.
        """
        if self._audit_snapshot is not None:
            return self._audit_snapshot
        if self._audit_loaded is None:
            return None
        loaded = dict(zip(*self._audit_loaded, strict=False))
        return {
            field.name: _serialise(loaded[field.attname])
            for field in self._meta.concrete_fields
            if field.attname in loaded and self._is_logged(field)
        }

    def _audit_values(self) -> dict[str, Any]:
        """Return the current values of all logged fields.

        Deferred fields (not loaded from the database) are skipped; reading
        them would trigger one query per field.
        """
        deferred = self.get_deferred_fields()
        return {
            field.name: _serialise(getattr(self, field.attname))
            for field in self._meta.concrete_fields
            if field.attname not in deferred and self._is_logged(field)
        }

    def audit_parent(self) -> models.Model | None:
        """Return the object in whose history this entry should also appear."""
        return None

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save the object and log what changed."""
        from rentalars.core.models import AuditAction

        is_new = self._state.adding
        before = self._audit_before()
        super().save(*args, **kwargs)
        after = self._audit_values()

        if is_new:
            changes = {name: [None, value] for name, value in after.items() if value not in (None, "")}
            _write_entry(self, AuditAction.CREATED, changes=changes)
        elif before is not None:
            changes = {
                name: [before.get(name), value]
                for name, value in after.items()
                if name in before and before[name] != value
            }
            if changes:
                _write_entry(self, AuditAction.UPDATED, changes=changes)
        self._audit_snapshot = after
        self._audit_loaded = None

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        """Log the deletion, then delete the object."""
        from rentalars.core.models import AuditAction

        # The entry must be written first: afterwards the primary key is gone.
        _write_entry(self, AuditAction.DELETED, changes={})
        return super().delete(*args, **kwargs)


def record_event(
    instance: models.Model,
    event: str,
    details: dict[str, Any] | None = None,
) -> AuditLogEntry:
    """Log a business event that is more than a field change.

    Args:
        instance: The object the event belongs to.
        event: A stable code such as ``"packlist.issued"``. The history view
            translates the code into a readable sentence.
        details: Extra values to keep with the event (JSON-compatible).

    Returns:
        The log entry that was written.
    """
    from rentalars.core.models import AuditAction

    return _write_entry(instance, AuditAction.EVENT, changes=details or {}, event=event)


def create_in_bulk(objects: list[AuditedModel]) -> list[AuditedModel]:
    """Create new objects of one model in two queries and log each creation as ``save()`` would.

    ``bulk_create`` skips ``save()`` and with it the change log. This writes
    the objects and their "created" entries in one query each, for a list
    that would otherwise cost two queries per object (NFA-014). The
    database returns the new primary keys (MariaDB 10.5 and later, SQLite
    3.35 and later).

    Returns:
        The created objects, with their primary keys.
    """
    from rentalars.core.models import AuditAction, AuditLogEntry

    if not objects:
        return []
    created = type(objects[0]).objects.bulk_create(objects)
    entries = []
    for instance in created:
        after = instance._audit_values()
        changes = {name: [None, value] for name, value in after.items() if value not in (None, "")}
        entries.append(_entry_for(instance, AuditAction.CREATED, changes=changes))
        instance._audit_snapshot = after
        instance._audit_loaded = None
    AuditLogEntry.objects.bulk_create(entries)
    return created


def _write_entry(
    instance: models.Model,
    action: str,
    *,
    changes: dict[str, Any],
    event: str = "",
) -> AuditLogEntry:
    """Create the log row for ``instance`` with the current actor."""
    entry = _entry_for(instance, action, changes=changes, event=event)
    entry.save()
    return entry


def _entry_for(
    instance: models.Model,
    action: str,
    *,
    changes: dict[str, Any],
    event: str = "",
) -> AuditLogEntry:
    """Build, without saving, the log row for ``instance`` with the current actor."""
    from django.contrib.contenttypes.models import ContentType

    from rentalars.core.models import AuditLogEntry

    actor = get_current_actor()
    parent = instance.audit_parent() if isinstance(instance, AuditedModel) else None
    # The name of the record is stored as text. It is written in the language
    # of the installation, whoever acts: "migrate", for one, runs without any
    # language, and the log would otherwise say "System settings" in German pages.
    with translation.override(settings.LANGUAGE_CODE):
        object_repr = str(instance)[:200]
    entry = AuditLogEntry(
        actor_id=actor.user_id if actor else None,
        actor_label=(actor.label if actor else "system")[:150],
        action=action,
        event=event,
        content_type=ContentType.objects.get_for_model(instance, for_concrete_model=True),
        object_id=str(instance.pk),
        object_repr=object_repr,
        changes=changes,
    )
    if parent is not None and parent.pk is not None:
        entry.parent_content_type = ContentType.objects.get_for_model(parent, for_concrete_model=True)
        entry.parent_object_id = str(parent.pk)
    return entry


def delete_old_entries() -> int:
    """Remove entries of the change log after the retention period (NFA-011); 0 keeps them for good."""
    from django.utils import timezone

    from rentalars.core.models import AuditLogEntry, SystemSettings

    days = SystemSettings.load().retention_change_log_days
    if not days:
        return 0
    limit = timezone.now() - datetime.timedelta(days=days)
    deleted, _details = AuditLogEntry.objects.filter(timestamp__lt=limit).delete()
    return deleted
