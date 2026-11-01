# SPDX-License-Identifier: GPL-3.0-or-later
"""The correspondence of a project as the AI and the short overview read it (EML-040, EML-044).

Which mails: those of the correspondence page – the project's own and, for a
whole project, those of the parts the reader may read (PRJ-044), with the
notes written between them (EML-051) – and, when asked for, the
messages of the project's chat (UIX-010). Of each mail
only what is new in it counts: quoted earlier mails and what follows them
are cut off as on the conversation view (EML-036).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any

from django.db.models import Count, Max, QuerySet

from rentalars.mail.display import html_to_text, split_quoted
from rentalars.mail.models import Direction, MailKind, ProjectMail
from rentalars.projects.models import Project

#: Characters of one mail that count; a longer mail is cut (the rest is mostly quotes and footers).
MAX_MAIL_CHARS = 6000


def project_ids_for(rights: Any, user: Any, project: Project) -> list[int]:
    """The projects whose mails a reader sees on the correspondence page of ``project`` (PRJ-044)."""
    from rentalars.projects.access import readable_projects

    ids = [project.pk]
    if project.parent_id is None and project.has_subprojects:
        parts = readable_projects(rights, user, Project.objects.filter(parent_id=project.pk))
        ids += sorted(parts.values_list("pk", flat=True))
    return ids


def mails_of(project_ids: list[int]) -> QuerySet[ProjectMail]:
    """The mails of these projects."""
    return ProjectMail.objects.filter(project_id__in=project_ids)


@dataclass(frozen=True)
class State:
    """How far the correspondence goes: to tell whether a summary is out of date."""

    mail_count: int
    newest_mail_id: int
    newest_mail_date: datetime.datetime | None
    newest_chat_id: int


def state_of(project_ids: list[int]) -> State:
    """The number of mails, the newest of them and the newest chat message of these projects."""
    from rentalars.chat.models import ChatMessage

    mails = mails_of(project_ids)
    totals = mails.aggregate(count=Count("id"), newest_date=Max("date"))
    newest = mails.order_by("-date", "-id").values_list("pk", flat=True).first()
    chat = ChatMessage.objects.filter(project_id__in=project_ids).aggregate(newest=Max("id"))
    return State(
        mail_count=totals["count"] or 0,
        newest_mail_id=newest or 0,
        newest_mail_date=totals["newest_date"],
        newest_chat_id=chat["newest"] or 0,
    )


def readable_count(project_ids: list[int], *, include_notes: bool, include_locked: bool) -> int:
    """How many mails and notes of these projects a reader with this scope can read."""
    mails = mails_of(project_ids).exclude(kind=MailKind.BOUNCE)
    if not include_locked:
        mails = mails.filter(locked=False)
    if not include_notes:
        mails = mails.exclude(direction=Direction.NOTE)
    return mails.count()


@dataclass
class Entry:
    """One mail or chat message, as plain text."""

    kind: str  # "mail", "note" (EML-051) or "chat"
    date: datetime.datetime
    incoming: bool
    writer: str
    recipients: str = ""
    subject: str = ""
    text: str = ""
    attachments: list[str] = field(default_factory=list)
    mail: ProjectMail | None = None


def new_text_of(mail: ProjectMail, limit: int = MAX_MAIL_CHARS) -> str:
    """What is new in a mail: its text without quoted earlier mails (EML-036), cut at ``limit``."""
    text = (mail.text_body or "").strip() or html_to_text(mail.html_body or "")
    new, _rest = split_quoted(text)
    new = new.strip()
    if len(new) > limit:
        new = new[:limit].rstrip() + " …"
    return new


def writer_of(mail: ProjectMail) -> str:
    """Who wrote a mail: the sender, or for a sent mail – and a note (EML-051) – the user who wrote it."""
    if mail.direction in (Direction.OUTGOING, Direction.NOTE) and mail.sent_by_id:
        name = mail.sent_by.get_full_name() if hasattr(mail.sent_by, "get_full_name") else ""
        return name or str(mail.sent_by)
    return mail.sender_label or mail.sender_address or "?"


def entries(
    project_ids: list[int],
    *,
    include_chat: bool = False,
    newest: int | None = None,
    include_notes: bool = True,
    include_locked: bool = True,
) -> list[Entry]:
    """The correspondence, oldest first – the newest ``newest`` mails only, if given.

    ``include_notes`` and ``include_locked`` are the scope of whoever reads (``ai.summary.Scope``): the
    nightly job has no user and reads the open mails only, unless an administrator allows more.
    """
    mails = (
        mails_of(project_ids)
        .exclude(kind=MailKind.BOUNCE)
        .select_related("sent_by")
        .prefetch_related("attachments")
        .order_by("-date", "-id")
    )
    if not include_locked:
        mails = mails.filter(locked=False)
    if not include_notes:
        mails = mails.exclude(direction=Direction.NOTE)
    if newest is not None:
        mails = mails[:newest]
    found = [
        Entry(
            kind="note" if mail.is_note else "mail",
            date=mail.date,
            incoming=mail.direction == Direction.INCOMING,
            writer=writer_of(mail),
            recipients=", ".join(part for part in (mail.to_addresses, mail.cc_addresses) if part),
            subject=mail.subject,
            text=new_text_of(mail),
            attachments=[item.filename for item in mail.attachments.all() if not item.is_inline],
            mail=mail,
        )
        for mail in mails
    ]
    if include_chat:
        from rentalars.chat.models import ChatMessage

        for message in ChatMessage.objects.filter(project_id__in=project_ids).order_by("id"):
            found.append(
                Entry(
                    kind="chat",
                    date=message.created_at,
                    incoming=False,
                    writer=message.author_name or "?",
                    text=message.text,
                )
            )
    found.sort(key=lambda entry: entry.date)
    return found
