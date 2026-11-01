# SPDX-License-Identifier: GPL-3.0-or-later
"""Messages of the correspondence in the history of a project (EML-055; PRJ-032, API-002).

The history of a project lists the changes of its mails and notes – they name the project as their parent in the
change log, with the subject as the name of the record – and the events "note added", "mail removed" and "mail
moved", which keep the subject in their details. Changing the lock adds an entry, too.

A message a reader may not read does not exist for him, so neither does its subject in the history. The rule is
applied when the history is shown, so it covers older entries as well:

* An entry about a message that is still in this project shows its subject (or the title of a note) to who reads
  that message by the rule of ``mail.locks``.
* An entry about a message that was removed or moved on to another project shows it only to who reads the messages
  with lock here – the correspondence and the price right.
* Everybody else – and whoever reads no correspondence at all – sees a neutral wording: "Nachricht" or "Notiz" with
  direction and date where they are known, without the subject and without old and new subjects.

The messages named on a page are loaded together, so the number of queries does not grow with the page
(:func:`hide_unreadable`).
"""

from __future__ import annotations

import datetime
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.utils import formats, timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _
from django.utils.translation import pgettext

from rentalars.core.history import HistoryItem
from rentalars.core.models import AuditAction
from rentalars.mail.locks import Correspondence
from rentalars.mail.models import Direction, ProjectMail

#: The events on the project that name a message by its subject (``mail.notes``, ``mail.services``).
NOTE_ADDED = "mail.note_added"
DELETED = "mail.deleted"
REASSIGNED = "mail.reassigned"
MAIL_EVENTS = frozenset({NOTE_ADDED, DELETED, REASSIGNED})

#: The fields of a message whose values are the subject.
_SUBJECT_FIELDS = frozenset({"subject"})

#: What is loaded of a message to decide and to name it neutrally.
_FIELDS = ("pk", "project_id", "locked", "direction", "date")


def _moment(value: Any) -> datetime.datetime | None:
    """A moment stored in the change log (ISO text), or ``None``."""
    if isinstance(value, datetime.datetime):
        return value
    moment = parse_datetime(str(value)) if value else None
    return moment


def _date_text(moment: datetime.datetime | None) -> str:
    """A moment as the history shows dates – "01.03.2027 08:00"; empty if unknown."""
    if moment is None:
        return ""
    if timezone.is_aware(moment):
        moment = timezone.localtime(moment)
    return formats.date_format(moment, "SHORT_DATETIME_FORMAT")


def neutral_name(direction: str, moment: datetime.datetime | None) -> str:
    """A message without its subject: "Notiz vom …", "Nachricht, eingegangen am …" (EML-055)."""
    date = _date_text(moment)
    if direction == Direction.NOTE:
        return _("Note of %(date)s") % {"date": date} if date else _("Note")
    if not date:
        return pgettext("correspondence", "Message")
    if direction == Direction.INCOMING:
        return _("Message received on %(date)s") % {"date": date}
    if direction == Direction.OUTGOING:
        return _("Message sent on %(date)s") % {"date": date}
    return _("Message of %(date)s") % {"date": date}


def neutral_event(event: str, details: dict[str, Any]) -> str:
    """An event about a message without its subject (EML-055)."""
    date = _date_text(_moment(details.get("date")))
    if event == NOTE_ADDED:
        return _("Note in the correspondence of %(date)s") % {"date": date} if date else _("Note in the correspondence")
    if event == DELETED:
        if date:
            return _("Message of %(date)s removed from the correspondence") % {"date": date}
        return _("Message removed from the correspondence")
    return _("Message moved from %(from)s to %(to)s") % {
        "from": details.get("from") or "–",
        "to": details.get("to") or "–",
    }


def _mail_id(value: Any) -> int | None:
    """The ID of a message as the change log keeps it (text or number); ``None`` if it is none."""
    text = str(value) if value is not None else ""
    return int(text) if text.isdigit() else None


def _details(item: HistoryItem) -> dict[str, Any]:
    """The details of an event, or the changes of an entry."""
    return item.entry.changes if isinstance(item.entry.changes, dict) else {}


def hide_unreadable(items: list[HistoryItem], correspondence: Correspondence, project: Any) -> list[HistoryItem]:
    """Take the subjects of the messages a reader may not read out of a page of a project's history.

    Args:
        items: The page, prepared by ``core.history.describe``; changed in place and returned.
        correspondence: What the reader may do with the correspondence of the project (``mail.locks``).
        project: The project whose history it is.

    At most two queries, whatever the size of the page: the messages named on it, and – for notes added earlier,
    whose event does not name the note – the notes of the project at the times named.
    """
    if correspondence.reads_all or not items:
        # Reads every message here; a message removed or moved away is for him, too.
        return items
    mail_type = ContentType.objects.get_for_model(ProjectMail)
    about_mail = [item for item in items if item.entry.content_type_id == mail_type.pk]
    events = [item for item in items if item.entry.action == AuditAction.EVENT and item.entry.event in MAIL_EVENTS]
    if not about_mail and not events:
        return items
    ids = {_mail_id(item.entry.object_id) for item in about_mail}
    ids |= {_mail_id(_details(item).get("mail")) for item in events}
    ids.discard(None)
    mails = {mail.pk: mail for mail in ProjectMail.objects.filter(pk__in=ids).only(*_FIELDS)} if ids else {}
    old_notes = _old_notes(project, events)

    def readable(mail: ProjectMail | None) -> bool:
        """Whether the reader may see the subject: a message here by the rule; else gone for him."""
        if mail is None or mail.project_id != project.pk:
            return correspondence.reads_all
        return correspondence.may_read(mail)

    for item in about_mail:
        mail = mails.get(_mail_id(item.entry.object_id) or 0)
        if not readable(mail):
            _neutral_entry(item, mail)
    for item in events:
        details = _details(item)
        mail_id = _mail_id(details.get("mail"))
        if mail_id is not None:
            visible = readable(mails.get(mail_id))
        elif item.entry.event == NOTE_ADDED:
            found = old_notes.get(_note_key(details), [])
            visible = bool(found) and all(readable(note) for note in found)
        else:
            visible = correspondence.reads_all  # moved or removed earlier: the message is not named
        if not visible:
            item.summary = neutral_event(item.entry.event, details)
    return items


def _note_key(details: dict[str, Any]) -> tuple[datetime.datetime | None, str]:
    """How an older event "note added" names its note: the time and the title."""
    return _moment(details.get("date")), str(details.get("subject") or "")


def _old_notes(project: Any, events: list[HistoryItem]) -> dict[tuple[datetime.datetime | None, str], list[Any]]:
    """The notes of the project that events "note added" without the note's ID name by time and title."""
    wanted = {
        _note_key(_details(item))
        for item in events
        if item.entry.event == NOTE_ADDED and _mail_id(_details(item).get("mail")) is None
    }
    moments = {moment for moment, _title in wanted if moment is not None}
    if not moments or project.pk is None:
        return {}
    found: dict[tuple[datetime.datetime | None, str], list[Any]] = {}
    for note in ProjectMail.objects.filter(project_id=project.pk, direction=Direction.NOTE, date__in=moments).only(
        *_FIELDS, "subject", "text_body"
    ):
        key = (note.date, note.note_title[:120])
        found.setdefault(key, []).append(note)
    return {key: found.get(key, []) for key in wanted}


def _neutral_entry(item: HistoryItem, mail: ProjectMail | None) -> None:
    """An entry about a message without its subject: a neutral name, no subject among the changes."""
    changes = _details(item)
    if mail is not None:
        direction, moment = mail.direction, mail.date
    else:
        # Removed: what the entry itself knows – the entry of its creation names direction and date.
        direction = _new_value(changes.get("direction"))
        moment = _moment(_new_value(changes.get("date")))
    item.shown_name = neutral_name(str(direction or ""), moment)
    item.changes = [change for change in item.changes if change.name not in _SUBJECT_FIELDS]
    if item.entry.action == AuditAction.UPDATED and not item.changes and changes:
        item.summary = _("changed (details not visible)")


def _new_value(values: Any) -> Any:
    """The new value of a change ``[old, new]``; ``None`` otherwise."""
    return values[1] if isinstance(values, list) and len(values) == 2 else None
