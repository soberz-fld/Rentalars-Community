# SPDX-License-Identifier: GPL-3.0-or-later
"""The lists of time entries in Personal → Freigeben and → Auswertung as tables (ZEI-013, ZEI-015, UIX-040).

* :data:`REPORT_ENTRY_TABLE` – "Die Einträge" below the sums of the hours report:
  columns to choose, sorting, groups and CSV like every list. Its parameters
  carry the prefix ``entries_`` (``entries_sort``, ``entries_format=csv`` …):
  the page's own ``?format=csv`` is the file of the report (ZEI-017) and
  ``group_by`` groups its sums.
* :data:`APPROVAL_TABLE` – the times waiting for approval. That page is a form,
  not a list to browse: one panel per project with its sum and the buttons
  "Freigeben" and "Zurückgeben" for the ticked rows of that project. So the
  rows stay grouped by project (no "Gruppieren nach"), and the parts of a
  period divided into job functions (ZEI-025) stay together whatever column
  sorts – they are approved together. Columns to choose, sorting within each
  project and the CSV of all waiting times are those of every table. Since
  ZEI-030: every row has "Korrigieren": corrected in a dialog and approved.

Both work on lists already prepared by the views (hints ZEI-018, parts ZEI-025),
so they sort in Python.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from django.urls import reverse
from django.utils import dateformat, timezone
from django.utils.functional import lazy
from django.utils.html import format_html, format_html_join
from django.utils.http import urlencode
from django.utils.safestring import SafeString
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.core.i18n import local_pattern
from rentalars.core.money import format_decimal, format_money
from rentalars.core.tables import Column, TableDefinition, badge, hidden_label
from rentalars.core.templatetags.rentalars import icon, status_colour
from rentalars.projects import family_labels

_hidden = hidden_label  # UIX-029: lazy, in the reader's language


def _local(moment: Any, pattern: str) -> str:
    return dateformat.format(timezone.localtime(moment), local_pattern(pattern)) if moment else ""


def _hints(entry: Any) -> SafeString:
    """ZEI-018: the hints of an entry, as ``timetracking/_hints.html`` shows them."""
    hints = getattr(entry, "hints", None) or []
    if not hints:
        return SafeString("")
    items = format_html_join(
        "",
        '<li class="time-hint">{}<span><span class="visually-hidden">{} </span>{}</span></li>',
        ((icon("alert"), gettext("Hint:"), hint.message) for hint in hints),
    )
    return format_html('<ul class="time-hints">{}</ul>', items)


def _part_of(entry: Any) -> SafeString:
    """ZEI-025: which part of a divided period a row is, as ``timetracking/_part_of.html`` shows it."""
    if not getattr(entry, "part_count", 0):
        return SafeString("")
    text = gettext("Part %(number)s of %(total)s of a period of %(hours)s h") % {
        "number": entry.part_number,
        "total": entry.part_count,
        "hours": format_decimal(entry.period_hours),
    }
    return format_html('<div class="muted small time-part-of">{}</div>', text)


def _time(entry: Any) -> SafeString:
    text = f"{_local(entry.start, 'H:i')} – {_local(entry.end, 'H:i')}"
    if getattr(entry, "break_minutes", 0):
        brk = gettext("%(minutes)s min break") % {"minutes": entry.break_minutes}
        return format_html('{} <span class="muted small">({})</span>{}', text, brk, _hints(entry))
    return format_html("{}{}", text, _hints(entry))


def _project_label(entry: Any) -> str:
    return family_labels.project_label(entry.project) if entry.project_id else entry.project_label


def _period_key(entry: Any) -> Any:
    return entry.period_key if getattr(entry, "period_key", None) is not None else ("entry", entry.pk)


def keep_periods_together(entries: list[Any]) -> list[Any]:
    """ZEI-025: after sorting, the parts of a period follow the first of them, in the order of the day."""
    parts: dict[Any, list[Any]] = {}
    for entry in sorted(entries, key=lambda entry: (entry.start, entry.pk)):
        parts.setdefault(_period_key(entry), []).append(entry)
    result: list[Any] = []
    placed: set[Any] = set()
    for entry in entries:
        key = _period_key(entry)
        if key not in placed:
            placed.add(key)
            result.extend(parts[key])
    return result


def _personnel_costs(rights: Rights) -> bool:
    return rights.has(SpecialRight.PERSONNEL_COSTS)


def _common() -> list[Column]:
    """Person, day, time, job function, project, hours: the columns of both lists."""
    return [
        Column(
            "person",
            _("Person"),
            cell=lambda entry: entry.person.name,
            sort=lambda entry: entry.person.sort_name,
            group=lambda entry: entry.person_id,
        ),
        Column(
            "day",
            _("Day"),
            cell=lambda entry: _local(entry.start, "D d.m.Y"),
            text=lambda entry: timezone.localdate(entry.start),
            sort=lambda entry: entry.start,
            css="nowrap",
            group=lambda entry: timezone.localdate(entry.start),
        ),
        Column(
            "time",
            _("Time"),
            cell=_time,
            text=lambda entry: f"{_local(entry.start, 'H:i')} – {_local(entry.end, 'H:i')}",
            sort=lambda entry: (timezone.localtime(entry.start).time(), entry.start),
            css="nowrap",
        ),
        Column(
            "job_function",
            _("Job function"),
            cell=lambda entry: entry.job_function.name if entry.job_function_id else "",
            sort=lambda entry: entry.job_function.name if entry.job_function_id else "",
            group=lambda entry: entry.job_function_id,
        ),
        Column(
            "project",
            _("Project"),
            cell=_project_label,
            sort=lambda entry: entry.project.number if entry.project_id else "",
            group=lambda entry: entry.project_id,
        ),
        Column(
            "hours",
            _("Hours"),
            cell=lambda entry: format_decimal(entry.hours, max_places=2),
            text=lambda entry: entry.hours,
            sort=lambda entry: entry.hours,
            css="num",
        ),
        Column(
            "break",
            _("Break (minutes)"),
            cell=lambda entry: entry.break_minutes or "",
            text=lambda entry: entry.break_minutes,
            sort=lambda entry: entry.break_minutes or 0,
            css="num",
            default=False,
        ),
        Column("note", _("Note"), cell=lambda entry: entry.note, sort=lambda entry: entry.note, default=False),
    ]


# --- Personal → Auswertung: "Die Einträge" ---------------------------------------------------------------


def _report_project(entry: Any) -> SafeString:
    details = ", ".join(part for part in (entry.job_function.name if entry.job_function_id else "", entry.note) if part)
    return format_html('{}<div class="muted small">{}</div>{}', entry.project_label, details, _part_of(entry))


def _report_actions(entry: Any) -> SafeString:
    """Unlock an approved entry, or edit one not approved yet – for who may manage times (set by the view)."""
    if not getattr(entry, "may_manage", False):
        return SafeString("")
    if entry.status == "approved":
        return format_html(
            '<form class="inline-form" method="post" action="{}"><input type="hidden" name="csrfmiddlewaretoken"'
            ' value="{}"><input type="hidden" name="next" value="{}"><button class="link-btn" type="submit"'
            ' data-confirm="{}">{}</button></form>',
            reverse("timetracking:entry_reopen", args=[entry.pk]),
            entry.csrf_token,
            entry.back_to,
            gettext("Take back the approval? The entry can then be corrected and must be approved again."),
            gettext("unlock"),
        )
    if entry.is_editable:
        label = gettext("Edit time")
        return format_html(
            '<button class="icon-btn" type="button" hx-get="{}" hx-target="#dialog" aria-label="{}" title="{}">{}</button>',
            reverse("timetracking:entry_edit", args=[entry.pk]),
            label,
            label,
            icon("edit"),
        )
    return SafeString("")


REPORT_ENTRY_TABLE = TableDefinition(
    "hours_report_entries",
    [
        *(column for column in _common() if column.key in {"day", "person"}),
        Column(
            "project",
            _("Project"),
            cell=_report_project,
            text=_project_label,
            sort=lambda entry: entry.project.number if entry.project_id else "",
            group=lambda entry: entry.project_id,
            group_label=_project_label,
        ),
        # The job function has its own column.
        *(
            replace(column, default=False) if column.key == "job_function" else column
            for column in _common()
            if column.key in {"job_function", "time", "hours", "break", "note"}
        ),
        Column(
            "status",
            _("Status"),
            cell=lambda entry: badge(entry.get_status_display(), status_colour(entry.status)),
            text=lambda entry: entry.get_status_display(),
            sort=lambda entry: entry.status,
            group=lambda entry: entry.status,
        ),
        Column(
            "amount",
            _("Amount"),
            cell=lambda entry: format_money(entry.amount),
            text=lambda entry: entry.amount,
            sort=lambda entry: entry.amount,
            css="num",
            default=False,
            visible_if=_personnel_costs,
        ),
        Column(
            "actions",
            _hidden(_("Actions")),
            cell=_report_actions,
            css="actions no-print",
            fixed=True,
            export=False,
            unsortable="buttons",
        ),
    ],
    default_sort="day",
    prefix="entries_",
)


#: UIX-015: the sums above the entries – one row per person, project, job function or day. A handful of
#: computed rows, sorted in Python; the first column keeps the order of the report (names, or days in order).
#: The page draws the headings itself (the first one is named after the grouping, the amount only where it is
#: shown) and adds the total row; no column chooser, no CSV of its own – the report has its file.
REPORT_SUM_TABLE = TableDefinition(
    "hours_report_sums",
    [
        Column("label", _("Group"), cell=lambda row: row.label, sort=lambda row: row.position, fixed=True),
        Column("entries", _("Entries"), cell=lambda row: len(row.entries), sort=lambda row: len(row.entries)),
        Column("hours", _("Hours"), cell=lambda row: format_decimal(row.hours), sort=lambda row: row.hours, css="num"),
        Column(
            "amount", _("Amount"), cell=lambda row: format_money(row.amount), sort=lambda row: row.amount, css="num"
        ),
    ],
    default_sort="label",
    prefix="sums_",
    # UIX-044: its rows are already the groups of the report ("group_by"), the page offers no "Group by".
    ungroupable="the rows are the sums of the report's own grouping",
)


# --- Personal → Freigeben -----------------------------------------------------------------------------------


def _all_boxes_html(label: Any) -> SafeString:
    return format_html('<input type="checkbox" data-select-all checked aria-label="{}" title="{}">', label, label)


#: The head of the column of tick boxes: one box for all rows of the table (V14); lazy, like ``hidden_label``.
_all_boxes = lazy(_all_boxes_html, SafeString)


def _choose(entry: Any) -> SafeString:
    """The tick for the whole period at its first part; the other parts say they are decided with it."""
    if getattr(entry, "part_number", 0) > 1:
        text = gettext("Decided with the first part of the period")
        return format_html(
            '<span class="muted small" title="{}">↳<span class="visually-hidden">{}</span></span>', text, text
        )
    return format_html(
        '<input type="checkbox" name="entry" value="{}" checked data-select-line aria-label="{}">',
        entry.pk,
        gettext("Choose"),
    )


def _approval_function(entry: Any) -> SafeString:
    name = entry.job_function.name if entry.job_function_id else ""
    parts = [format_html("{}", name)]
    if entry.project_id and not entry.crew_line_id and not entry.project.is_internal:
        parts.append(
            format_html(
                ' <span class="badge yellow" title="{}">{}</span>',
                gettext(
                    "Nobody was scheduled for this job function. After approval the time shows in the project and can"
                    " be put on a crew line."
                ),
                gettext("not planned"),
            )
        )
    if entry.note:
        parts.append(format_html('<div class="muted small">{}</div>', entry.note))
    parts.append(_part_of(entry))
    return format_html_join("", "{}", ((part,) for part in parts))


def _assign(entry: Any) -> SafeString:
    """ZEI-023: a project for an entry without one; the select and button belong to the form ``assign-<id>``."""
    if entry.project_id:
        return SafeString("")
    options = format_html_join(
        "",
        '<option value="{}">{}</option>',
        ((project.pk, family_labels.project_label(project)) for project in getattr(entry, "project_options", [])),
    )
    return format_html(
        '<select name="project" form="assign-{}" aria-label="{}" required><option value="">{}</option>{}</select> '
        '<button class="btn small secondary" type="submit" form="assign-{}">{}</button>',
        entry.pk,
        gettext("Project"),
        gettext("– choose –"),
        options,
        entry.pk,
        gettext("Assign"),
    )


def _correct(entry: Any) -> SafeString:
    """ZEI-030: "Korrigieren" – a dialog; without the page script a page of its own."""
    url = reverse("timetracking:entry_correct", args=[entry.pk])
    back = getattr(entry, "back_to", "")
    href = f"{url}?{urlencode({'next': back})}" if back else url
    label = gettext("Correct and approve: %(person)s, %(day)s") % {
        "person": entry.person.name,
        "day": _local(entry.start, "D d.m."),
    }
    return format_html(
        '<a class="icon-btn" href="{}" hx-get="{}" hx-target="#dialog" aria-haspopup="dialog" aria-label="{}"'
        ' title="{}">{}</a>',
        href,
        href,
        label,
        gettext("Correct and approve"),
        icon("edit"),
    )


APPROVAL_TABLE = TableDefinition(
    "time_approval",
    [
        Column(
            "choose",
            _all_boxes(_("Choose all")),
            cell=_choose,
            css="c-check",
            fixed=True,
            export=False,
            unsortable="tick boxes",
        ),
        # The approval keeps its grouping by project (one form per project): no column offers another one.
        *(replace(column, group=None) for column in _common() if column.key in {"person", "day", "time"}),
        Column(
            "job_function",
            _("Job function"),
            cell=_approval_function,
            text=lambda entry: entry.job_function.name if entry.job_function_id else "",
            sort=lambda entry: entry.job_function.name if entry.job_function_id else "",
        ),
        *(replace(column, group=None) for column in _common() if column.key in {"hours", "break", "note"}),
        Column(
            "amount",
            _("Amount"),
            cell=lambda entry: format_money(entry.amount),
            text=lambda entry: entry.amount,
            sort=lambda entry: entry.amount,
            css="num",
            visible_if=_personnel_costs,
        ),
        Column(
            "project",
            _("Project"),
            cell=_project_label,
            sort=lambda entry: entry.project.number if entry.project_id else "",
            default=False,
        ),
        Column(
            "assign",
            _("Project"),
            cell=_assign,
            css="assign",
            fixed=True,
            export=False,
            unsortable="a field to choose the project of an entry without one; the rows are grouped by project",
        ),
        # ZEI-030 (correction by the approver): correct the entry and approve it in one step.
        Column(
            "correct",
            _hidden(_("Correct")),
            cell=_correct,
            css="actions no-print",
            fixed=True,
            export=False,
            unsortable="a button",
        ),
    ],
    default_sort="day",
    # UIX-044: one form per project, the parts of a period together – the page offers no "Group by".
    ungroupable="the rows stay grouped by project: one form per project, approved together",
)
