# SPDX-License-Identifier: GPL-3.0-or-later
"""The project list as a table with columns to choose (UIX-015, IMP-005).

Crew and freelancers see their deployments, but not who the customer is
(AUT-023): the customer columns are only offered to those who may read all
projects or the customers.

PRJ-085: columns with sums – planned man-hours, revenue of material and
personnel, net, gross, costs, profit – can be chosen; none is shown by
default. They follow the rights of the planning and are calculated only
when shown (``projects.list_sums``). UIX-015: they sort in Python,
for a list of at most ``core.tables.PYTHON_SORT_MAX_ROWS`` projects.
"""

from __future__ import annotations

from typing import Any

from django.urls import reverse
from django.utils import dateformat, timezone
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext, ngettext, pgettext
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import Level, Module, Rights, SpecialRight
from rentalars.core.i18n import local_pattern
from rentalars.core.money import format_decimal, format_money
from rentalars.core.tables import Column, TableDefinition, badge, date_text, grouped_by_day, link
from rentalars.core.templatetags.rentalars import status_colour


def may_see_customers(rights: Rights) -> bool:
    """Whether the reader may see who the customers of the projects are (AUT-023)."""
    return rights.level_everywhere(Module.PROJECTS) >= Level.READ or rights.can_read(Module.CUSTOMERS)


def _period(project: Any) -> str:
    """``Mo 01.03.27 08:00 – Mi 03.03.27 18:00``: with the weekday, as planners think in weeks."""

    def moment(value: Any) -> str:
        return dateformat.format(timezone.localtime(value), local_pattern("D d.m.Y H:i"))

    return f"{moment(project.start)} – {moment(project.end)}"


def _name(project: Any) -> Any:
    """Name and venue; for a whole project its parts, for a part its whole project (PRJ-044)."""
    name = link(reverse("projects:overview", args=[project.pk]), project.name)
    notes = [project.venue_label] if project.venue_label else []
    if project.parent_id:
        notes.append(
            gettext("part of %(number)s %(name)s") % {"number": project.parent.number, "name": project.parent.name}
        )
        name = format_html('<span class="part-of" aria-hidden="true">↳</span> {}', name)
    elif getattr(project, "part_count", 0):
        notes.append(
            ngettext("%(count)d subproject", "%(count)d subprojects", project.part_count)
            % {"count": project.part_count}
        )
    if project.follow_up_on and getattr(project, "shows_follow_up", False):
        notes.append(_follow_up(project))
    if notes:
        return format_html(
            "{}{}", name, format_html_join("", '<div class="muted small">{}</div>', ((note,) for note in notes))
        )
    return name


# --- Follow-up (PRJ-105) ------------------------------------------------------------------------


def _follow_up_text(project: Any) -> str:
    """``Wiedervorlage 20.10.2026 für Anna Becker – Angebot nachfassen``; empty without a follow-up."""
    if not project.follow_up_on:
        return ""
    text = gettext("Follow-up on %(day)s") % {"day": date_text(project.follow_up_on)}
    if project.follow_up_at:  # PRJ-109
        text += " " + gettext("at %(time)s") % {"time": project.follow_up_at.strftime("%H:%M")}
    if project.follow_up_user_id:
        text += " " + gettext("for %(user)s") % {"user": project.follow_up_user}
    if project.follow_up_note:
        text += f" – {project.follow_up_note}"
    return text


def _follow_up(project: Any) -> Any:
    """The follow-up with a mark when its day has come; shown in the cell of the name and as a column."""
    if not project.follow_up_on:
        return ""
    if project.follow_up_is_due:
        return format_html(
            '<span class="follow-up-mark is-due">{} <span class="badge yellow">{}</span></span>',
            _follow_up_text(project),
            pgettext("follow-up", "due"),
        )
    return format_html('<span class="follow-up-mark">{}</span>', _follow_up_text(project))


# --- Invoice (DOK-015) ------------------------------------------------------------------------


def _invoice_text(project: Any) -> str:
    """The invoice of a project as text: its number, "issued", "no invoice", "open" once closed; else empty."""
    from rentalars.projects.models import InvoiceMark, ProjectStatus

    if project.parent_id or project.is_internal or not project.customer_id or project.status == ProjectStatus.CANCELLED:
        return ""
    number = getattr(project, "invoice_number", None)
    if number:
        return number
    if project.invoice_status == InvoiceMark.ISSUED:
        return gettext("Invoice issued")
    if project.invoice_status == InvoiceMark.NOT_NEEDED:
        return gettext("No invoice")
    if project.invoice_status == InvoiceMark.EARLIER:
        return ""  # closed earlier: not followed
    return gettext("Invoice open") if project.status == ProjectStatus.CLOSED else ""


def _invoice(project: Any) -> Any:
    """The invoice as a badge: green once invoiced, yellow while a closed project has none."""
    from rentalars.projects.models import InvoiceMark

    text = _invoice_text(project)
    if not text:
        return ""
    if getattr(project, "invoice_number", None) or project.invoice_status == InvoiceMark.ISSUED:
        return badge(text, "green")
    if project.invoice_status == InvoiceMark.NOT_NEEDED:
        return badge(text, "")
    return badge(text, "yellow")


# --- Sums (PRJ-085): the rights as on the planning page (AUT-019) ---------------------------------


def _prices(rights: Rights) -> bool:
    return rights.has(SpecialRight.PRICES)


def _material_costs(rights: Rights) -> bool:
    return rights.has(SpecialRight.PRICES) and rights.has(SpecialRight.PURCHASE_PRICES)


def _personnel_costs(rights: Rights) -> bool:
    return rights.has(SpecialRight.PERSONNEL_COSTS)


def _profit(rights: Rights) -> bool:
    """The profit is net minus all costs; without one of the rights it would give that cost away."""
    return _material_costs(rights) and _personnel_costs(rights)


def _sum(project: Any, name: str) -> Any:
    """One of the sums noted by ``list_sums.attach_sums``; ``None`` where the user may not read the planning."""
    sums = getattr(project, "list_sums", None)
    return getattr(sums, name) if sums is not None else None


def _sums_for_sorting(projects: list[Any], request: Any) -> None:
    """UIX-015: the sums of every project of the list, a chunk at a time, before it is sorted by one."""
    from rentalars.accounts.rights import request_rights
    from rentalars.projects import list_sums

    rights = request_rights(request)
    for start in range(0, len(projects), list_sums.CHUNK):
        list_sums.attach_sums(projects[start : start + list_sums.CHUNK], rights=rights, user=request.user)


def _sum_column(key: str, label: Any, visible_if: Any, *, hours: bool = False) -> Column:
    """A column with a sum of the project (PRJ-085): not shown by default.

    UIX-015: sortable – in Python, as the sums are calculated, not stored; for lists of at most
    ``core.tables.PYTHON_SORT_MAX_ROWS`` projects.
    """
    if hours:

        def cell(project: Any) -> str:
            value = _sum(project, key)
            return format_decimal(value, max_places=2) if value is not None else ""
    else:

        def cell(project: Any) -> str:
            return format_money(_sum(project, key))

    return Column(
        key,
        label,
        cell=cell,
        text=lambda project: _sum(project, key),
        sort=lambda project: _sum(project, key),
        sort_prepare=_sums_for_sorting,
        css="num nowrap",
        default=False,
        visible_if=visible_if,
    )


PROJECT_TABLE = TableDefinition(
    "projects",
    [
        Column(
            "number",
            _("Number"),
            cell=lambda project: link(reverse("projects:overview", args=[project.pk]), project.number),
            text=lambda project: project.number,
            sort="number",
            css="nowrap",
            fixed=True,
            group="number",
        ),
        # UIX-044: every column groups – by its field, a moment or a period by the day it begins; the
        # rental days and the sums by what they show, for a list of at most 2,000 projects.
        Column(
            "name",
            _("Project"),
            cell=_name,
            text=lambda project: project.name,
            sort="name",
            group="name",
            group_label=lambda project: project.name,
        ),
        Column(
            "customer",
            _("Customer"),
            cell=lambda project: project.customer_name,  # PRJ-122: the name shows in every role
            sort=("customer__name", "start"),
            group="customer",
        ),
        Column("period", _("Period"), cell=_period, sort="start", css="nowrap", **grouped_by_day("start")),
        Column(
            "status",
            _("Status"),
            cell=lambda project: badge(project.get_status_display(), status_colour(project.status)),
            text=lambda project: project.get_status_display(),
            sort=("status", "start"),
            group="status",
        ),
        Column(
            "manager",
            _("Project manager"),
            cell=lambda project: project.manager or "",
            sort=("manager__last_name", "manager__username", "start"),
            group="manager",
        ),
        Column(
            "venue",
            _("Venue"),
            cell=lambda project: project.venue_label,
            sort=("venue_site__name", "venue", "start"),
            default=False,
            group="venue_site",
        ),
        Column(
            "start",
            _("Material out from"),
            cell=lambda project: date_text(project.start),
            text=lambda project: project.start,
            sort="start",
            css="nowrap",
            default=False,
            **grouped_by_day("start"),
        ),
        Column(
            "end",
            _("Material back by"),
            cell=lambda project: date_text(project.end),
            text=lambda project: project.end,
            sort="end",
            css="nowrap",
            default=False,
            **grouped_by_day("end"),
        ),
        Column(
            "event",
            _("Event"),
            cell=lambda project: (
                f"{date_text(project.event_start)} – {date_text(project.event_end)}" if project.event_start else ""
            ),
            sort=("event_start", "start"),
            css="nowrap",
            default=False,
            **grouped_by_day("event_start"),
        ),
        Column(
            "rental_days",
            _("Rental days"),
            cell=lambda project: format_decimal(project.effective_rental_days),
            text=lambda project: project.effective_rental_days,
            # UIX-015: the entered days or the suggestion from the period – worked out in Python.
            sort=lambda project: project.effective_rental_days,
            css="num",
            default=False,
        ),
        Column(
            "customer_number",
            _("Customer number"),
            cell=lambda project: project.customer.number if project.customer_id else "",
            sort=("customer__number", "start"),
            default=False,
            visible_if=may_see_customers,
            group="customer__number",
        ),
        Column(
            "contact",
            _("Contact"),
            cell=lambda project: project.contact or "",
            sort=("contact__name", "start"),
            default=False,
            visible_if=may_see_customers,
            group="contact",
        ),
        # PRJ-105: the follow-up, to sort by and for the file; the cell of the name shows it as well.
        Column(
            "follow_up",
            _("Follow-up"),
            cell=_follow_up,
            text=_follow_up_text,
            sort=("follow_up_on", "follow_up_at", "start"),
            default=False,
            visible_if=may_see_customers,
            group="follow_up_on",
            group_label=lambda project: date_text(project.follow_up_on),
        ),
        Column(
            "created",
            _("Created"),
            cell=lambda project: date_text(project.created_at),
            text=lambda project: project.created_at,
            sort="created_at",
            css="nowrap",
            default=False,
            **grouped_by_day("created_at"),
        ),
        # DOK-015: the invoice – its number, "issued" by hand, "no invoice" or "open"; for who may see prices.
        Column(
            "invoice",
            _("Invoice"),
            cell=_invoice,
            text=_invoice_text,
            sort=_invoice_text,
            default=False,
            visible_if=_prices,
        ),
        # PRJ-085: sums of the project; for a whole project with its parts (see ``projects.list_sums``).
        _sum_column("planned_hours", _("Planned man-hours"), None, hours=True),
        _sum_column("material_revenue", _("Material revenue"), _prices),
        _sum_column("personnel_revenue", _("Personnel revenue"), _prices),
        # LOG-009, LOG-010: vehicles and trailers – revenue with the prices, costs with the purchase prices.
        _sum_column("logistics_revenue", _("Logistics revenue"), _prices),
        _sum_column("net_total", _("Total net"), _prices),
        _sum_column("gross_total", _("Total gross"), _prices),
        _sum_column("material_cost", _("Material costs"), _material_costs),
        _sum_column("personnel_cost", _("Personnel costs"), _personnel_costs),
        _sum_column("logistics_cost", _("Logistics costs"), _material_costs),
        _sum_column("profit", _("Calculated profit"), _profit),
    ],
    default_sort="start",
)
