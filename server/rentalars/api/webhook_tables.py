# SPDX-License-Identifier: GPL-3.0-or-later
"""Einstellungen → Webhooks as a table: columns to choose, sorting, groups and CSV (API-012, UIX-040)."""

from __future__ import annotations

from typing import Any

from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeString
from django.utils.translation import gettext, ngettext
from django.utils.translation import gettext_lazy as _

from rentalars.api import webhook_events
from rentalars.core.tables import Column, TableDefinition, badge, date_text, link


def _title(hook: Any) -> str:
    return hook.description or f"{gettext('Webhook')} {hook.pk}"


def _events(hook: Any) -> str:
    labels = dict(webhook_events.choices())
    return ", ".join(str(labels.get(name, name)) for name in hook.events or [])


def _status_text(hook: Any) -> str:
    if hook.is_active:
        return gettext("active")
    return gettext("switched off automatically") if hook.switched_off_at else gettext("off")


def _status(hook: Any) -> SafeString:
    colour = "green" if hook.is_active else ("red" if hook.switched_off_at else "")
    return badge(_status_text(hook), colour)


def _deliveries(hook: Any) -> SafeString:
    marks = []
    if hook.failed:
        marks.append(
            badge(ngettext("%(count)s failed", "%(count)s failed", hook.failed) % {"count": hook.failed}, "red")
        )
    if hook.waiting:
        marks.append(
            badge(ngettext("%(count)s waiting", "%(count)s waiting", hook.waiting) % {"count": hook.waiting}, "yellow")
        )
    if hook.last_delivered:
        last = gettext("last delivered %(moment)s") % {"moment": date_text(hook.last_delivered)}
    else:
        last = gettext("nothing delivered yet")
    return format_html(
        '{}<div class="muted small">{}</div>', format_html_join(" ", "{}", ((mark,) for mark in marks)), last
    )


WEBHOOK_TABLE = TableDefinition(
    "webhooks",
    [
        Column(
            "webhook",
            _("Webhook"),
            cell=lambda hook: format_html(
                '{}<div class="muted small webhook-url">{}</div>',
                link(reverse("webhooks:detail", args=[hook.pk]), _title(hook)),
                hook.url,
            ),
            text=_title,
            sort=("description", "url"),
            fixed=True,
        ),
        # UIX-044: the other columns group by the value they show (a handful of webhooks, counts annotated).
        Column("url", _("Address (URL)"), cell=lambda hook: hook.url, sort="url", default=False, group="url"),
        # UIX-015: the events are a list stored as JSON – by their text, a handful of webhooks.
        Column("events", _("Events"), cell=_events, sort=_events),
        Column(
            "status",
            _("Status"),
            cell=_status,
            text=_status_text,
            sort=("-is_active", "description"),
            group="is_active",
            group_label=lambda hook: gettext("active") if hook.is_active else gettext("off"),
        ),
        Column(
            "deliveries",
            _("Deliveries"),
            cell=_deliveries,
            text=lambda hook: hook.last_delivered,
            sort=("last_delivered", "description"),
        ),
        Column("failed", _("Failed"), cell=lambda hook: hook.failed, sort="failed", css="num", default=False),
        Column("waiting", _("Waiting"), cell=lambda hook: hook.waiting, sort="waiting", css="num", default=False),
    ],
    default_sort="webhook",
    row_css=lambda hook: "" if hook.is_active else "is-muted",
)
