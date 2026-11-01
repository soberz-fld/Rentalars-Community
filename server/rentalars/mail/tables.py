# SPDX-License-Identifier: GPL-3.0-or-later
"""The mail log and the inquiries as tables with columns to choose, sorting and CSV export.

EML-039, EML-041, UIX-015, IMP-005; the inquiries (PRJ-107).
"""

from __future__ import annotations

from typing import Any

from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.text import Truncator
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from rentalars.core.i18n import local_pattern
from rentalars.core.tables import Column, TableDefinition, badge, date_text, grouped_by_day, link
from rentalars.mail.models import Direction, LogResult, MailLogEntry, UnknownTagMail

#: The direction as the log says it: "incoming" and "outgoing" rather than "received" and "sent",
#: which would read like the result.
DIRECTION_LABELS = {
    Direction.INCOMING.value: pgettext_lazy("mail log", "incoming"),
    Direction.OUTGOING.value: pgettext_lazy("mail log", "outgoing"),
}

#: The colour of each result: green went well, yellow needs a look, red failed (UIX-008).
RESULT_COLOURS = {
    LogResult.ASSIGNED.value: "green",
    LogResult.SENT.value: "green",
    LogResult.UNKNOWN_TAG.value: "yellow",
    LogResult.INQUIRY.value: "yellow",
    LogResult.LEFT_IN_INBOX.value: "",
    LogResult.FAILED.value: "red",
    # EML-048: a system mail without a mail server went nowhere.
    LogResult.NOT_SENT.value: "red",
    # PER-032: an answer to a deployment request by mail; one that was not taken over shows yellow (``_result``).
    LogResult.CREW_ANSWER.value: "green",
}


def _time_text(entry: MailLogEntry) -> str:
    return timezone.localtime(entry.timestamp).strftime(local_pattern("%d.%m.%Y %H:%M:%S"))


def _direction(entry: MailLogEntry) -> Any:
    return badge(DIRECTION_LABELS.get(entry.direction, entry.direction), "outline")


def _recipients(entry: MailLogEntry) -> Any:
    short = Truncator(entry.recipients).chars(120)
    if short == entry.recipients:
        return entry.recipients
    return format_html('<span title="{}">{}</span>', entry.recipients, short)


def _project(entry: MailLogEntry) -> Any:
    if entry.project is None:
        return ""
    return link(reverse("projects:overview", args=[entry.project]), entry.project.number)


def _result(entry: MailLogEntry) -> Any:
    colour = RESULT_COLOURS.get(entry.result, "")
    if entry.result == LogResult.CREW_ANSWER and ":" in entry.detail:
        colour = "yellow"  # PER-032: the answer came, but was not taken over
    cell = badge(entry.get_result_display(), colour)
    detail = entry.detail_text
    if detail:
        return format_html('{}<div class="muted small">{}</div>', cell, Truncator(detail).chars(200))
    return cell


def _result_text(entry: MailLogEntry) -> str:
    detail = entry.detail_text
    return f"{entry.get_result_display()}: {detail}" if detail else str(entry.get_result_display())


MAIL_LOG_TABLE = TableDefinition(
    "mail_log",
    [
        Column(
            "time",
            pgettext_lazy("mail log", "Time"),
            cell=_time_text,
            text=lambda entry: entry.timestamp,
            sort="timestamp",
            css="nowrap",
            fixed=True,
            **grouped_by_day("timestamp"),  # UIX-044: every column groups, a moment by its day
        ),
        Column(
            "direction",
            _("Direction"),
            cell=_direction,
            text=lambda entry: DIRECTION_LABELS.get(entry.direction, entry.direction),
            sort=("direction", "-timestamp"),
            group="direction",
        ),
        Column(
            "kind",
            _("Kind"),
            cell=lambda entry: entry.get_kind_display(),
            sort=("kind", "-timestamp"),
            group="kind",
        ),
        Column("sender", _("From"), cell=lambda entry: entry.sender, sort=("sender", "-timestamp"), group="sender"),
        Column(
            "recipients",
            _("To"),
            cell=_recipients,
            text=lambda entry: entry.recipients,
            sort=("recipients", "-timestamp"),
            group="recipients",
        ),
        Column(
            "subject",
            _("Subject"),
            cell=lambda entry: entry.subject,
            sort=("subject", "-timestamp"),
            group="subject",
        ),
        Column(
            "project",
            _("Project"),
            cell=_project,
            text=lambda entry: entry.project.number if entry.project else "",
            sort=("project__number", "-timestamp"),
            group="project",
        ),
        Column(
            "result",
            _("Result"),
            cell=_result,
            text=_result_text,
            sort=("result", "-timestamp"),
            group="result",
        ),
        # EML-041: which mailbox the mail went through; empty for system mails sent through the configuration.
        # EML-046: a deleted mailbox by the name it had, marked as deleted.
        Column(
            "mailbox",
            _("Mailbox"),
            cell=lambda entry: entry.mailbox_label,
            sort=("mailbox_name", "-timestamp"),
            group="mailbox_name",
        ),
        Column(
            "user",
            _("Sent by"),
            cell=lambda entry: str(entry.user) if entry.user else "",
            sort=("user__last_name", "user__first_name", "user__username", "-timestamp"),
            default=False,
            group="user",
        ),
    ],
    default_sort="-time",
)


# --- Projekte → Anfragen (EML-014, EML-042, PRJ-107) ------------------------------------------------------


def _tag(item: UnknownTagMail) -> Any:
    if item.is_defect:
        # MAT-057: put here by an automation of a defect report.
        return badge(_("defect report"), "yellow")
    if item.is_manual:
        # EML-053: noted by hand, e.g. during a phone call.
        return badge(pgettext_lazy("inquiry badge", "Noted"), "outline")
    if item.is_inquiry:
        return badge(_("without tag"), "accent")
    return format_html("<code>{}</code>", item.tag)


def _tag_text(item: UnknownTagMail) -> Any:
    if item.is_defect:
        return _("defect report")
    if item.is_manual:
        return pgettext_lazy("inquiry badge", "Noted")
    return item.tag or _("without tag")


def _subject(item: UnknownTagMail) -> Any:
    if item.is_defect:
        return format_html(
            '<a href="{}">{}</a>', reverse("material:item_detail", args=[item.defect_report.item_id]), item.subject
        )
    if item.is_manual and item.note:
        # EML-053: the beginning of what was noted.
        return format_html('{}<div class="muted small">{}</div>', item.subject or "–", Truncator(item.note).chars(160))
    return item.subject or "–"


def _sender(item: UnknownTagMail) -> Any:
    if not item.is_manual:
        return item.sender
    # EML-053: the caller with phone, e-mail address and customer, as noted.
    details = [part for part in (item.phone, item.contact_email) if part]
    if item.customer_id is not None:
        details.append(item.customer.name)
    if not details:
        return item.contact_name or "–"
    return format_html('{}<div class="muted small">{}</div>', item.contact_name or "–", " · ".join(details))


#: PRJ-107: the mails waiting under Projekte → Anfragen as a table – columns to choose, sorting by a
#: click on a heading, CSV of the view and with all columns (UIX-015, IMP-005).
INQUIRY_TABLE = TableDefinition(
    "mail_inquiries",
    [
        Column(
            "subject",
            _("Subject"),
            cell=_subject,
            text=lambda item: item.subject,
            sort=("subject", "-date"),
            fixed=True,
            group="subject",  # UIX-044
        ),
        Column(
            "sender",
            _("Sender"),
            cell=_sender,
            # EML-053: the CSV names the caller with phone and customer as well.
            text=lambda item: " · ".join(
                part for part in (item.sender, item.phone, item.customer.name if item.customer_id else "") if part
            ),
            sort=("sender", "-date"),
            group="sender",
        ),
        Column(
            "date",
            _("Date"),
            cell=lambda item: date_text(item.date),
            text=lambda item: item.date,
            sort="date",
            css="nowrap",
            # UIX-040: grouped by the day the mail was written.
            group="date__date",
            group_value=lambda item: timezone.localdate(item.date) if item.date else None,
            group_label=lambda item: date_text(timezone.localdate(item.date)) if item.date else "",
        ),
        Column(
            "tag",
            _("Tag"),
            cell=_tag,
            text=_tag_text,
            sort=("tag", "-date"),
            group="tag",  # the mails without tag together, each unknown tag by itself
        ),
        Column(
            "mailbox",
            _("Mailbox"),
            cell=lambda item: str(item.mailbox) if item.mailbox_id else "–",
            text=lambda item: str(item.mailbox) if item.mailbox_id else "",
            sort=("mailbox__name", "-date"),
            group="mailbox",
        ),
        # EML-047: the address of the mailbox the mail went to (a listed alias, else the mailbox's own).
        Column(
            "address",
            _("To address"),
            cell=lambda item: item.address,
            sort=("address", "-date"),
            group="address",
            default=False,
        ),
        Column(
            "found",
            _("found"),
            cell=lambda item: date_text(item.first_seen_at),
            text=lambda item: item.first_seen_at,
            sort="first_seen_at",
            css="nowrap",
            default=False,
            **grouped_by_day("first_seen_at"),
        ),
    ],
    default_sort="-date",
)
