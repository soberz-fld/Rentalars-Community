# SPDX-License-Identifier: GPL-3.0-or-later
"""Einstellungen → Automationen as two tables: the rules and their runs (ADM-013, UIX-040).

Both tables stand on one page; the runs carry the prefix ``runs_`` in the
address (``runs_sort``, ``runs_group`` …), so that sorting one does not sort
the other. The buttons "Ausschalten" and "Löschen" of a rule belong to small
forms below the table (``toggle-<id>``, ``delete-<id>``); the cells only hold
the buttons.

ADM-019: the buttons of a rule – "Bearbeiten", "Ausschalten"/"Einschalten",
"Löschen" – stand in one row of one height (``cell-buttons``), also on a
phone, where they may wrap; before, "Löschen" with its icon sat a few pixels
higher. A rule that came with Rentalars is marked "Standard", and "geändert"
when it differs from how it came (``automations.defaults``).
"""

from __future__ import annotations

from typing import Any

from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeString
from django.utils.text import Truncator, capfirst
from django.utils.translation import gettext, ngettext, pgettext, pgettext_lazy
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import Module, Rights
from rentalars.automations.models import CASE_TRIGGERS, Action, Recipient, RunStatus, Trigger
from rentalars.core.tables import Column, TableDefinition, badge, date_text, hidden_label, link
from rentalars.core.templatetags.rentalars import icon

#: The colour of the result of a run.
RUN_COLOURS = {RunStatus.DONE: "green", RunStatus.FAILED: "red", RunStatus.SKIPPED: "yellow"}


def _may_write(rights: Rights) -> bool:
    return rights.can_write(Module.ADMINISTRATION)


def _marks(rule: Any) -> SafeString:
    """Active or off; (ADM-019) "Standard" for a rule that came with Rentalars, "geändert" if changed."""
    marks = [badge(gettext("active"), "green") if rule.is_active else badge(gettext("off"))]
    if rule.is_default:
        marks.append(badge(pgettext("automation", "default"), "outline"))
        if rule.default_changed:
            marks.append(badge(pgettext("automation", "changed"), "outline"))
    return format_html_join(" ", "{}", ((mark,) for mark in marks))


def _name(rule: Any) -> SafeString:
    """The name – a link to the form for who may change it – and below it its marks."""
    name = (
        link(reverse("automations:edit", args=[rule.pk]), rule.name) if getattr(rule, "can_write", False) else rule.name
    )
    return format_html("{}<div>{}</div>", name, _marks(rule))


def _origin(rule: Any) -> str:
    """(ADM-019) The column "Herkunft": "Standard", "Standard, geändert" or empty."""
    if not rule.is_default:
        return ""
    if rule.default_changed:
        return f"{pgettext('automation', 'default')}, {pgettext('automation', 'changed')}"
    return pgettext("automation", "default")


def _condition(rule: Any) -> str:
    """The detail of the trigger: the mailbox, the status, the answer."""
    if rule.trigger == Trigger.INQUIRY:
        if rule.mailbox_id:
            return gettext("in the mailbox %(mailbox)s") % {"mailbox": rule.mailbox}
        return gettext("in every mailbox that takes them in")
    if rule.trigger == Trigger.PROJECT_STATUS:
        return rule.status_label
    if rule.trigger == Trigger.CREW_ANSWER:
        return str(rule.get_answer_display())
    if rule.trigger in CASE_TRIGGERS:
        # PRJ-112: "while “Waiting to close”" and, for communication, which kind counts.
        parts = [gettext("while “%(status)s”") % {"status": rule.status_label}] if rule.status else []
        if rule.trigger == Trigger.CASE_COMMUNICATION and rule.communication:
            parts.append(str(rule.get_communication_display()))
        return ", ".join(parts)
    return ""


def _if(rule: Any) -> SafeString:
    detail = _condition(rule)
    head = capfirst(rule.get_trigger_display())
    return format_html('{}<div class="muted small">{}</div>', head, detail) if detail else format_html("{}", head)


def _then_detail(rule: Any) -> str:
    if rule.action == Action.NOTIFY:
        return str(rule.user or "–") if rule.recipient == Recipient.USER else str(rule.get_recipient_display())
    if rule.action == Action.CASE_STATUS:
        return gettext("to “%(status)s”") % {"status": rule.new_case_status_label}  # PRJ-112
    if rule.action == Action.CREATE_CASE and rule.user_id:
        return gettext("responsible: %(name)s") % {"name": rule.user}  # MAT-057
    return Truncator(rule.subject or rule.text).chars(60)


def _then(rule: Any) -> SafeString:
    detail = _then_detail(rule)
    head = capfirst(rule.get_action_display())
    return format_html('{}<div class="muted small">{}</div>', head, detail) if detail else format_html("{}", head)


def _runs(rule: Any) -> SafeString:
    if not rule.run_count:
        return format_html('<span class="muted">{}</span>', gettext("not yet"))
    cell = format_html('<a href="?automation={}#runs">{}</a>', rule.pk, rule.run_count)
    if rule.failed_count:
        failed = ngettext("%(count)s failed", "%(count)s failed", rule.failed_count) % {"count": rule.failed_count}
        cell = format_html('{} <span class="badge red">{}</span>', cell, failed)
    last = gettext("last %(moment)s") % {"moment": date_text(rule.last_run)}
    return format_html('{}<div class="muted small">{}</div>', cell, last)


def _actions(rule: Any) -> SafeString:
    """Edit, switch on/off and delete – the same for the rules that came with Rentalars (ADM-019).

    The buttons send the forms below the table. ADM-019: they stand in one flex row (``cell-buttons``), so that all
    have one height and one line – a button whose first child is an icon otherwise sits on another baseline than
    one with text only. Only "Löschen" carries an icon, so that the three fit in one row on a phone of 390 px.
    """
    switch = gettext("Switch off") if rule.is_active else gettext("Switch on")
    question = gettext("Delete the automation “%(name)s”? Its runs stay listed.") % {"name": rule.name}
    if rule.is_default:
        question = f"{question} {gettext('“Restore default automations” brings it back as it came.')}"
    return format_html(
        '<div class="cell-buttons">'
        '<a class="btn secondary small" href="{}">{}</a>'
        '<button class="btn secondary small" type="submit" form="toggle-{}">{}</button>'
        '<button class="btn secondary small danger" type="submit" form="delete-{}" data-confirm="{}">{}{}</button>'
        "</div>",
        reverse("automations:edit", args=[rule.pk]),
        gettext("Edit"),
        rule.pk,
        switch,
        rule.pk,
        question,
        icon("trash"),
        gettext("Delete"),
    )


RULE_TABLE = TableDefinition(
    "automation_rules",
    [
        # UIX-044: the counted columns (annotations) group by the value they show – a handful of rules.
        Column("name", _("Automation"), cell=_name, text=lambda rule: rule.name, sort="name", fixed=True, group="name"),
        Column(
            "active",
            _("Active"),
            cell=lambda rule: gettext("active") if rule.is_active else gettext("off"),
            text=lambda rule: rule.is_active,
            sort=("-is_active", "name"),
            default=False,
            group="is_active",
        ),
        Column(
            "trigger",
            pgettext_lazy("automation", "If"),
            cell=_if,
            text=lambda rule: " – ".join(filter(None, [str(rule.get_trigger_display()), _condition(rule)])),
            sort=("trigger", "name"),
            group="trigger",
            group_label=lambda rule: capfirst(rule.get_trigger_display()),
        ),
        Column(
            "action",
            pgettext_lazy("automation", "Then"),
            cell=_then,
            text=lambda rule: " – ".join(filter(None, [str(rule.get_action_display()), _then_detail(rule)])),
            sort=("action", "name"),
            group="action",
            group_label=lambda rule: capfirst(rule.get_action_display()),
        ),
        # ADM-019: which rules came with Rentalars – also for the CSV and for grouping.
        Column(
            "origin",
            _("Origin"),
            cell=_origin,
            text=_origin,
            sort=("default_key", "name"),
            default=False,
        ),
        Column("runs", _("Runs"), cell=_runs, text=lambda rule: rule.run_count, sort=("run_count", "name")),
        Column(
            "failed",
            _("Failed runs"),
            cell=lambda rule: rule.failed_count or "",
            text=lambda rule: rule.failed_count,
            sort=("failed_count", "name"),
            css="num",
            default=False,
        ),
        Column(
            "last_run",
            _("Last run"),
            cell=lambda rule: date_text(rule.last_run),
            text=lambda rule: rule.last_run,
            sort=("last_run", "name"),
            css="nowrap",
            default=False,
        ),
        Column(
            "actions",
            hidden_label(_("Actions")),  # UIX-029: lazy, in the reader's language
            cell=_actions,
            css="nowrap no-print",
            visible_if=_may_write,
            fixed=True,
            export=False,
            unsortable="buttons",
        ),
    ],
    default_sort="name",
    row_css=lambda rule: "" if rule.is_active else "is-muted",
)


def _automation(run: Any) -> SafeString:
    name = format_html("{}", run.automation_name)
    if not run.automation_id:
        name = format_html('{} <span class="muted small">({})</span>', name, gettext("deleted"))
    return format_html('{}<div class="muted small">{}</div>', name, capfirst(run.get_action_display()))


def _event(run: Any) -> Any:
    if run.project_id:
        return link(reverse("projects:overview", args=[run.project_id]), run.event)
    return run.event


def _result(run: Any) -> SafeString:
    cell = badge(capfirst(run.get_status_display()), RUN_COLOURS.get(run.status, ""))
    return format_html('{}<div class="small">{}</div>', cell, run.detail) if run.detail else cell


RUN_TABLE = TableDefinition(
    "automation_runs",
    [
        Column(
            "time",
            pgettext_lazy("automation", "Time"),
            cell=lambda run: date_text(run.created_at),
            text=lambda run: run.created_at,
            sort="created_at",
            css="nowrap",
            fixed=True,
            group="created_at__date",
            group_value=lambda run: _local_day(run.created_at),
            group_label=lambda run: date_text(_local_day(run.created_at)),
        ),
        Column(
            "automation",
            _("Automation"),
            cell=_automation,
            text=lambda run: run.automation_name,
            sort=("automation_name", "-created_at"),
            group="automation_name",
            group_label=lambda run: run.automation_name,
        ),
        Column(
            "event",
            pgettext_lazy("automation", "Event"),
            cell=_event,
            text=lambda run: run.event,
            sort=("event", "-created_at"),
            group="event",  # UIX-044
        ),
        Column(
            "project",
            _("Project"),
            cell=lambda run: run.project.number if run.project_id else "",
            sort=("project__number", "-created_at"),
            default=False,
            group="project",
        ),
        Column(
            "result",
            _("Result"),
            cell=_result,
            text=lambda run: f"{run.get_status_display()}: {run.detail}" if run.detail else run.get_status_display(),
            sort=("status", "-created_at"),
            group="status",
            group_label=lambda run: badge(capfirst(run.get_status_display()), RUN_COLOURS.get(run.status, "")),
        ),
        Column(
            "recipient",
            _("Recipient"),
            cell=lambda run: run.recipient,
            sort=("recipient", "-created_at"),
            default=False,
            group="recipient",  # UIX-044
        ),
    ],
    default_sort="-time",
    prefix="runs_",
)


def _local_day(moment: Any) -> Any:
    return timezone.localdate(moment)
