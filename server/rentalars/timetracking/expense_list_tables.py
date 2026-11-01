# SPDX-License-Identifier: GPL-3.0-or-later
"""The lists of expenses as tables: columns to choose, sorting, groups and CSV (ZEI-019, UIX-040).

Two lists:

* :data:`EXPENSE_TABLE` – Personal → Spesen: every expense of the selection,
  with a tick box for "mark as reimbursed" for those who may.
* :data:`MY_EXPENSE_TABLE` – Mein Bereich → Meine Spesen: the own expenses of
  a month, with editing and deleting while they are not approved.

Both work on the list ``ExpenseReport.expenses`` (already narrowed to what the
reader may see), so they are sorted and grouped in Python.
"""

from __future__ import annotations

from typing import Any

from django.urls import reverse
from django.utils import dateformat
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeString
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from rentalars.core.i18n import local_pattern
from rentalars.core.money import format_decimal, format_money
from rentalars.core.tables import Column, TableDefinition, badge, date_text, hidden_label
from rentalars.core.templatetags.rentalars import icon, status_colour
from rentalars.timetracking import services

#: A heading only screen readers say – over tick boxes and buttons; lazy, in the reader's language (UIX-029).
_hidden = hidden_label


def _money_text(value: Any) -> str:
    return format_money(value, currency="").strip() if value is not None else ""


def _distance(expense: Any) -> str:
    """``42 km`` or – with the way to work deducted (ZEI-027) – the calculation."""
    label = getattr(expense, "distance_label", "")
    return label if isinstance(label, str) else ""


def _kind(expense: Any) -> SafeString:
    """The kind, for a trip by kilometre the calculation, and the link to the receipt."""
    parts = [format_html("{}", expense.get_kind_display())]
    if expense.is_by_kilometre:
        parts.append(
            format_html('<div class="muted small">{} × {}</div>', _distance(expense), format_money(expense.km_rate))
        )
    if expense.receipt:
        parts.append(
            format_html(
                '<div class="small"><a href="{}" target="_blank" rel="noopener">{}{}</a></div>',
                reverse("timetracking:expense_receipt", args=[expense.pk]),
                icon("file"),
                gettext("Receipt"),
            )
        )
    return format_html_join("", "{}", ((part,) for part in parts))


def _project(expense: Any) -> SafeString:
    if expense.note:
        return format_html('{}<div class="muted small">{}</div>', expense.project, expense.note)
    return format_html("{}", expense.project)


def _status(expense: Any) -> SafeString:
    cell = badge(expense.status_label, status_colour(expense.status_key))
    if expense.reimbursed_on:
        return format_html('{}<div class="muted small">{}</div>', cell, date_text(expense.reimbursed_on))
    return cell


def _month_label(expense: Any) -> str:
    return dateformat.format(expense.date, "F Y")


def _choose(expense: Any) -> SafeString:
    """A tick box for "mark as reimbursed" – only for an approved expense not paid out yet."""
    if expense.status != "approved" or expense.is_reimbursed:
        return SafeString("")
    label = gettext("Choose the expense of %(person)s of %(day)s") % {
        "person": expense.person.name,
        "day": date_text(expense.date),
    }
    return format_html('<input type="checkbox" name="expense" value="{}" aria-label="{}">', expense.pk, label)


def _report_actions(expense: Any) -> SafeString:
    """Take back a reimbursement or an approval; the forms are below the table (``reopen-<id>``)."""
    if expense.is_reimbursed:
        question, text = gettext("Take back the mark “reimbursed”?"), gettext("not reimbursed")
    elif expense.status == "approved":
        question = gettext("Take back the approval? The expense can then be corrected and must be approved again.")
        text = gettext("unlock")
    else:
        return SafeString("")
    return format_html(
        '<button class="link-btn" type="submit" form="reopen-{}" data-confirm="{}">{}</button>',
        expense.pk,
        question,
        text,
    )


def _may_manage(rights: Any) -> bool:
    return services.may_manage(rights)


def _common_columns() -> list[Column]:
    """Person, project, day, kind, amount, status and the details: the columns of both lists."""
    return [
        Column(
            "month",
            _("Month"),
            cell=_month_label,
            text=lambda expense: f"{expense.date:%m/%Y}",
            sort=lambda expense: expense.date.replace(day=1),
            default=False,
            group=lambda expense: expense.date.replace(day=1),
        ),
        Column(
            "person",
            _("Person"),
            cell=lambda expense: expense.person.sort_name,
            sort=lambda expense: expense.person.sort_name,
            group=lambda expense: expense.person_id,
        ),
        Column(
            "project_number",
            _("Project number"),
            cell=lambda expense: expense.project.number,
            sort=lambda expense: expense.project.number,
            default=False,
        ),
        Column(
            "project",
            _("Project"),
            cell=_project,
            text=lambda expense: expense.project.name,
            sort=lambda expense: expense.project.number,
            group=lambda expense: expense.project_id,
            group_label=lambda expense: str(expense.project),
        ),
        Column(
            "day",
            _("Day"),
            cell=lambda expense: dateformat.format(expense.date, local_pattern("D d.m.Y")),
            text=lambda expense: expense.date,
            sort="date",
            css="nowrap",
            group=lambda expense: expense.date,
        ),
        Column(
            "kind",
            _("Kind"),
            cell=_kind,
            text=lambda expense: expense.get_kind_display(),
            sort=lambda expense: str(expense.get_kind_display()),
            group="kind",
            group_label=lambda expense: expense.get_kind_display(),
        ),
        Column(
            "kilometres",
            _("Kilometres"),
            cell=lambda expense: _distance(expense),
            text=lambda expense: (
                format_decimal(expense.kilometres, max_places=1) if expense.kilometres is not None else ""
            ),
            sort="kilometres",
            css="num",
            default=False,
        ),
        Column(
            "commute",
            _("Way to work deducted (km)"),
            cell=lambda expense: format_decimal(expense.commute_km, max_places=1) if expense.commute_km else "",
            sort="commute_km",
            css="num",
            default=False,
        ),
        Column(
            "km_rate",
            _("Rate per kilometre"),
            cell=lambda expense: format_money(expense.km_rate) if expense.km_rate is not None else "",
            text=lambda expense: _money_text(expense.km_rate),
            sort="km_rate",
            css="num",
            default=False,
        ),
        Column(
            "amount",
            _("Amount"),
            cell=lambda expense: format_money(expense.amount),
            text=lambda expense: _money_text(expense.amount),
            sort="amount",
            css="num nowrap",
        ),
        Column("note", _("Note"), cell=lambda expense: expense.note, sort="note", default=False),
        Column(
            "receipt",
            _("Receipt"),
            cell=lambda expense: gettext("yes") if expense.receipt else gettext("no"),
            sort=lambda expense: bool(expense.receipt),
            default=False,
            group=lambda expense: bool(expense.receipt),
        ),
        Column(
            "status",
            _("Status"),
            cell=_status,
            text=lambda expense: expense.status_label,
            sort=lambda expense: expense.status_label,
            group=lambda expense: expense.status_key,
            group_label=lambda expense: badge(expense.status_label, status_colour(expense.status_key)),
        ),
        Column(
            "reimbursed_on",
            _("Reimbursed on"),
            cell=lambda expense: date_text(expense.reimbursed_on),
            text=lambda expense: expense.reimbursed_on,
            sort="reimbursed_on",
            css="nowrap",
            default=False,
        ),
    ]


EXPENSE_TABLE = TableDefinition(
    "expenses",
    [
        Column(
            "choose",
            _hidden(_("Choose")),
            cell=_choose,
            css="c-check",
            visible_if=_may_manage,
            fixed=True,
            export=False,
            unsortable="tick boxes",
        ),
        *_common_columns(),
        Column(
            "actions",
            _hidden(_("Actions")),
            cell=_report_actions,
            css="actions no-print",
            visible_if=_may_manage,
            fixed=True,
            export=False,
            unsortable="buttons",
        ),
    ],
    default_sort="day",
)


def _my_actions(expense: Any) -> SafeString:
    """Edit and delete an own expense while it is not approved. ``my_expense_month`` is set by the view."""
    if not (expense.is_editable and getattr(expense, "can_record", False)):
        return SafeString("")
    edit = format_html(
        '<button class="icon-btn" type="button" hx-get="{}" hx-target="#dialog" aria-label="{}" title="{}">{}</button>',
        reverse("timetracking:expense_edit", args=[expense.pk]),
        gettext("Edit expense"),
        gettext("Edit expense"),
        icon("edit"),
    )
    delete = format_html(
        '<form class="inline-form" method="post" action="{}"><input type="hidden" name="csrfmiddlewaretoken" value="{}">'
        '<input type="hidden" name="next" value="{}"><button class="icon-btn" type="submit" aria-label="{}" title="{}"'
        ' data-confirm="{}">{}</button></form>',
        reverse("timetracking:expense_delete", args=[expense.pk]),
        getattr(expense, "csrf_token", ""),
        getattr(expense, "back_to", ""),
        gettext("Delete expense"),
        gettext("Delete expense"),
        gettext("Delete this expense and its receipt?"),
        icon("trash"),
    )
    return format_html("{}{}", edit, delete)


MY_EXPENSE_TABLE = TableDefinition(
    "my_expenses",
    [
        *(column for column in _common_columns() if column.key not in {"person"}),
        Column(
            "actions",
            _hidden(_("Actions")),
            cell=_my_actions,
            css="actions no-print",
            fixed=True,
            export=False,
            unsortable="buttons",
        ),
    ],
    default_sort="day",
)
