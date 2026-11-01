# SPDX-License-Identifier: GPL-3.0-or-later
"""Notes in the correspondence of a project (EML-051).

Not everything is said by mail: a phone call, a talk at the warehouse
counter, an agreement on site. A note writes it down *with the time it
happened*, so that it stands where it belongs in the chronology of the
correspondence – in the list, in the conversation, in the overview and in
what the AI summarises. The time is chosen when writing (now, by default) and
may lie in the past, never in the future.

A note is a ``ProjectMail`` with ``direction`` "note": it is listed, moved
to another project, deleted and – like the mails – removed after the
retention period (EML-031). It has no addresses and no Message-ID, cannot be
answered, and is no "new communication" for the automations of the service
cases (``automations.signals``).

Who may write one: who may write correspondence (``mail.services``) and read
the project – as for sending a mail; also in a closed project, where mails
still arrive. Changing or deleting it: its writer, or who may edit the
project.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.core.audit import record_event
from rentalars.mail.locks import default_lock
from rentalars.mail.models import AssignedBy, Direction, ProjectMail

#: The longest note – a long talk is summarised, not transcribed.
MAX_TEXT = 10_000
#: The longest subject of a note.
MAX_SUBJECT = 200
#: A clock a little ahead does not refuse "now".
FUTURE_TOLERANCE = datetime.timedelta(minutes=5)


def _writer(user: Any) -> str:
    if user is None:
        return ""
    return (user.get_full_name() or user.get_username())[:200]


def _check(text: str, subject: str, moment: datetime.datetime) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not text.strip():
        errors["text"] = _("Write what the note says.")
    elif len(text) > MAX_TEXT:
        errors["text"] = _("A note may have at most %(count)d characters.") % {"count": MAX_TEXT}
    if len(subject) > MAX_SUBJECT:
        errors["subject"] = _("The subject may have at most %(count)d characters.") % {"count": MAX_SUBJECT}
    if moment > timezone.now() + FUTURE_TOLERANCE:
        errors["date"] = _("A note records what happened – choose a time that has passed.")
    return errors


@transaction.atomic
def add_note(
    project: Any,
    *,
    text: str,
    user: Any,
    date: datetime.datetime | None = None,
    subject: str = "",
    locked: bool | None = None,
) -> ProjectMail:
    """Write a note into the correspondence of a project, at ``date`` (now if not given).

    EML-055: ``locked`` – with lock or open; ``None``: as the mail settings say for the project or case
    (``mail.locks.default_lock``). The caller decided what the writer may (``Correspondence.new_lock``).

    Raises:
        ValidationError: No text, too long, or a time in the future.
    """
    text = (text or "").strip()
    subject = " ".join((subject or "").split())
    moment = date or timezone.now()
    errors = _check(text, subject, moment)
    if errors:
        raise ValidationError(errors)
    note = ProjectMail.objects.create(
        project=project,
        direction=Direction.NOTE,
        message_key=f"note:{uuid.uuid4().hex}",
        message_id="",
        subject=subject,
        sender_name=_writer(user),
        date=moment,
        text_body=text,
        assigned_by=AssignedBy.NOTE,
        sent_by=user if getattr(user, "pk", None) else None,
        size=len(text.encode("utf-8")),
        locked=default_lock(project) if locked is None else bool(locked),
    )
    # EML-055: with the note's ID – the history shows the title only to who may read the note (mail.history).
    record_event(
        project, "mail.note_added", {"subject": note.note_title[:120], "date": moment.isoformat(), "mail": note.pk}
    )
    return note


def ensure_note(mail: ProjectMail) -> None:
    """Refuse a mail where a note is expected.

    Raises:
        ValidationError: It is a mail, not a note.
    """
    if not mail.is_note:
        raise ValidationError(_("This is a mail, not a note; a mail cannot be changed."))


@transaction.atomic
def update_note(
    note: ProjectMail,
    *,
    text: str | None = None,
    date: datetime.datetime | None = None,
    subject: str | None = None,
) -> ProjectMail:
    """Change text, time or subject of a note; what is left out stays.

    Raises:
        ValidationError: Not a note, no text, too long, or a time in the future.
    """
    ensure_note(note)
    new_text = note.text_body if text is None else text.strip()
    new_subject = note.subject if subject is None else " ".join(subject.split())
    new_date = note.date if date is None else date
    errors = _check(new_text, new_subject, new_date)
    if errors:
        raise ValidationError(errors)
    note.text_body, note.subject, note.date = new_text, new_subject, new_date
    note.size = len(new_text.encode("utf-8"))
    note.save(update_fields=["text_body", "subject", "date", "size"])
    return note


def may_change(note: ProjectMail, user: Any, *, may_edit_project: bool) -> bool:
    """Whether a user may change or delete a note: its writer, or who may edit the project."""
    return note.is_note and (may_edit_project or (note.sent_by_id is not None and note.sent_by_id == user.pk))
