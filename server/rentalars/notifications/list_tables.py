# SPDX-License-Identifier: GPL-3.0-or-later
"""The notifications as a table: columns to choose, sorting, groups and CSV (UIX-005, UIX-039, UIX-040).

Unread notifications are rows in bold (``unread``); the title leads to where
the notification points and marks it as read.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Case, IntegerField, Value, When
from django.urls import reverse
from django.utils import dateformat, timezone
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from rentalars.core.i18n import local_pattern
from rentalars.core.tables import Column, TableDefinition, date_text, grouped_by_day, plain_text, text_lines
from rentalars.notifications.categories import CATEGORIES, category_label, category_of
from rentalars.notifications.models import Kind


def _title(item: Any) -> SafeString:
    title = format_html(
        '<a href="{}"><strong>{}</strong></a>', reverse("notifications:open", args=[item.pk]), item.title
    )
    if item.body:
        # UIX-005: plain text with its line breaks, without "<p>…</p>" around it.
        return format_html('{}<div class="muted small">{}</div>', title, text_lines(item.body))
    return title


def _read_on(item: Any) -> str:
    """UIX-044: the heading of a group of the column "Read" – the day, or "unread"."""
    return date_text(timezone.localdate(item.read_at)) if item.read_at else gettext("unread")


#: The place of each notification's category among the categories, worked out from its kind by the database.
CATEGORY_ORDER = Case(
    *(When(kind=kind, then=Value(CATEGORIES.index(category_of(kind)))) for kind in Kind.values),
    default=Value(0),
    output_field=IntegerField(),
)


NOTIFICATION_TABLE = TableDefinition(
    "notifications",
    [
        # UIX-044: every column groups; the category (worked out from the kind) by what it shows.
        Column(
            "title",
            _("Notification"),
            cell=_title,
            text=lambda item: item.title,
            sort="title",
            fixed=True,
            group="title",
            group_label=lambda item: item.title,
        ),
        # UIX-005: the text on its own, as plain text – for the CSV file ("CSV with all columns").
        Column(
            "text",
            _("Text"),
            cell=lambda item: text_lines(item.body),
            text=lambda item: plain_text(item.body),
            sort="body",
            default=False,
        ),
        Column(
            "category",
            _("Category"),
            cell=lambda item: category_label(category_of(item.kind)),
            # UIX-015: the category follows from the kind – in the order of the categories.
            sort=(CATEGORY_ORDER, "kind", "-created_at"),
        ),
        Column(
            "kind",
            _("Kind"),
            cell=lambda item: item.get_kind_display(),
            sort=("kind", "-created_at"),
            group="kind",
            group_label=lambda item: item.get_kind_display(),
        ),
        Column(
            "time",
            _("Time"),
            cell=lambda item: dateformat.format(timezone.localtime(item.created_at), local_pattern("D d.m.Y H:i")),
            text=lambda item: item.created_at,
            sort="created_at",
            css="nowrap",
            group="created_at__date",
            group_value=lambda item: timezone.localdate(item.created_at),
            group_label=lambda item: date_text(timezone.localdate(item.created_at)),
        ),
        Column(
            "read",
            _("Read"),
            cell=lambda item: date_text(item.read_at) if item.read_at else gettext("unread"),
            text=lambda item: item.read_at,
            sort=("read_at", "-created_at"),
            default=False,
            **{**grouped_by_day("read_at"), "group_label": _read_on},
        ),
    ],
    default_sort="-time",
    row_css=lambda item: "" if item.read_at else "unread",
)
