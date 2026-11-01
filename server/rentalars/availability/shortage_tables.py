# SPDX-License-Identifier: GPL-3.0-or-later
"""Planung → Fehlbestände as three tables: columns to choose, sorting, groups and CSV (VFG-013, PRJ-057, UIX-040).

The page shows three lists; each table has its own prefix in the address,
so that sorting one does not sort the others:

* :data:`BOTTLENECK_TABLE` (``bottlenecks_``) – the shortages by product;
* :data:`SHORTAGE_TABLE` (no prefix) – the open shortages, one per line;
* :data:`SUBRENTAL_TABLE` (``subrentals_``) – the subrentals of running and coming projects.

The first two are computed rows (sorted and grouped in Python), the third a queryset.
"""

from __future__ import annotations

from typing import Any

from django.urls import reverse
from django.utils import dateformat, timezone
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeString
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.core.i18n import local_pattern
from rentalars.core.money import format_money
from rentalars.core.tables import Column, TableDefinition, badge, natural_key
from rentalars.core.templatetags.rentalars import status_colour
from rentalars.projects import family_labels


def _product(product: Any) -> SafeString:
    return format_html('<span class="artno">{}</span> {}', product.article_number, product.name)


def _product_text(product: Any) -> str:
    return f"{product.article_number} {product.name}"


def _moment(value: Any, pattern: str = "d.m.Y H:i") -> str:
    return dateformat.format(timezone.localtime(value), local_pattern(pattern)) if value else ""


def _period(line: Any) -> str:
    return f"{_moment(line.start)} – {_moment(line.end)}"


def _project_link(project: Any) -> SafeString:
    link = format_html(
        '<a href="{}">{} {}</a>', reverse("projects:detail", args=[project.pk]), project.number, project.name
    )
    if project.parent_id:
        return format_html('{}<div class="muted small">{}</div>', link, family_labels.part_of(project))
    return link


def _missing(value: int) -> SafeString:
    return format_html('<span class="avail short">{}</span>', value)


# --- Bottlenecks by product ------------------------------------------------------------------------------


def _project_numbers_key(entry: dict[str, Any]) -> tuple[Any, ...]:
    """The numbers of the projects of a bottleneck in natural order – "2026-0009" before "2026-0010"."""
    return tuple(sorted(natural_key(project.number) for project in entry["projects"]))


def _projects(entry: dict[str, Any]) -> SafeString:
    return format_html_join(
        ", ",
        '<a href="{}"{}>{}</a>',
        (
            (
                reverse("projects:detail", args=[project.pk]),
                format_html(' title="{}"', family_labels.part_of(project)) if project.parent_id else "",
                project.number,
            )
            for project in entry["projects"]
        ),
    )


BOTTLENECK_TABLE = TableDefinition(
    "bottlenecks",
    [
        Column(
            "product",
            _("Product"),
            cell=lambda entry: _product(entry["product"]),
            text=lambda entry: _product_text(entry["product"]),
            sort=lambda entry: entry["product"].article_number,
            fixed=True,
        ),
        Column(
            "missing",
            _("Missing at most"),
            cell=lambda entry: _missing(entry["missing"]),
            text=lambda entry: entry["missing"],
            sort=lambda entry: entry["missing"],
            css="num",
        ),
        Column(
            "first",
            _("From"),
            cell=lambda entry: _moment(entry["first"], "D d.m.Y"),
            text=lambda entry: entry["first"],
            sort=lambda entry: entry["first"],
            css="nowrap",
            group=lambda entry: timezone.localdate(entry["first"]),
        ),
        Column(
            "projects",
            _("Projects"),
            cell=_projects,
            text=lambda entry: ", ".join(project.number for project in entry["projects"]),
            # UIX-015: by the project numbers as shown.
            sort=_project_numbers_key,
        ),
        Column(
            "category",
            _("Category"),
            cell=lambda entry: entry["product"].category.name if entry["product"].category_id else "",
            sort=lambda entry: entry["product"].category.name if entry["product"].category_id else "",
            default=False,
            group=lambda entry: entry["product"].category_id,
        ),
    ],
    default_sort="first",
    prefix="bottlenecks_",
)


# --- Open shortages ----------------------------------------------------------------------------------------


def _shortage_project(shortage: Any) -> SafeString:
    project = shortage.project
    return format_html(
        "{} {}",
        _project_link(project),
        badge(project.get_status_display(), status_colour(project.status)),
    )


def _shortage_product(shortage: Any) -> SafeString:
    parts = [_product(shortage.product)]
    if shortage.detail.via == "kit":
        parts.append(format_html(' <span class="muted small">({} {})</span>', gettext("in"), shortage.line.title))
    if shortage.product.owner_id:  # PRJ-096: nobody else can supply it
        parts.append(
            format_html(
                ' {}<div class="muted small">{}</div>',
                badge(gettext("customer material"), "accent"),
                gettext("Customer material cannot be subrented."),
            )
        )
    return format_html_join("", "{}", ((part,) for part in parts))


def _shortage_missing(shortage: Any) -> SafeString:
    cell = _missing(shortage.quantity)
    if shortage.held_by_other_parts:  # PRJ-047: other parts of the same whole project hold the material
        return format_html(
            '{}<a class="family-hint muted small" href="{}">{}</a>',
            cell,
            reverse("projects:family", args=[shortage.project.pk]),
            gettext("of these held by other subprojects: %(count)s") % {"count": shortage.held_by_other_parts},
        )
    return cell


SHORTAGE_TABLE = TableDefinition(
    "open_shortages",
    [
        Column(
            "project",
            _("Project"),
            cell=_shortage_project,
            text=lambda shortage: f"{shortage.project.number} {shortage.project.name}",
            sort=lambda shortage: shortage.project.number,
            fixed=True,
            group=lambda shortage: shortage.project.pk,
            group_label=lambda shortage: _project_link(shortage.project),
        ),
        Column(
            "product",
            _("Product"),
            cell=_shortage_product,
            text=lambda shortage: _product_text(shortage.product),
            sort=lambda shortage: shortage.product.article_number,
            group=lambda shortage: shortage.product.pk,
            group_label=lambda shortage: _product(shortage.product),
        ),
        Column(
            "period",
            _("Period"),
            cell=lambda shortage: _period(shortage.line),
            sort=lambda shortage: shortage.line.start,
            css="nowrap",
        ),
        Column(
            "missing",
            _("Missing"),
            cell=_shortage_missing,
            text=lambda shortage: shortage.quantity,
            sort=lambda shortage: shortage.quantity,
            css="num",
        ),
        Column(
            "status",
            _("Status"),
            cell=lambda shortage: badge(shortage.project.get_status_display(), status_colour(shortage.project.status)),
            text=lambda shortage: shortage.project.get_status_display(),
            sort=lambda shortage: shortage.project.status,
            default=False,
            group=lambda shortage: shortage.project.status,
        ),
    ],
    default_sort="period",
)


# --- Subrentals ------------------------------------------------------------------------------------------


def _what(line: Any) -> SafeString:
    what = format_html("{} × {}", line.quantity_display, line.title)
    if line.covers_line_id:
        return format_html("{} {}", what, badge(gettext("covers a shortage")))
    return what


def _supplier(line: Any) -> SafeString:
    if line.supplier_id:  # PRJ-106: the page of the subrentals at this supplier in this project
        return format_html(
            '<a href="{}">{}</a>', reverse("projects:subrental", args=[line.project, line.supplier_id]), line.supplier
        )
    return badge(gettext("open"), "yellow")


def _purchase_prices(rights: Rights) -> bool:
    return rights.has(SpecialRight.PURCHASE_PRICES)


SUBRENTAL_TABLE = TableDefinition(
    "subrentals",
    [
        Column(
            "project",
            _("Project"),
            cell=lambda line: _project_link(line.project),
            text=lambda line: f"{line.project.number} {line.project.name}",
            sort=("project__number", "start"),
            fixed=True,
            group="project",
            group_label=lambda line: _project_link(line.project),
        ),
        Column(
            "what",
            _("What"),
            cell=_what,
            text=lambda line: f"{line.quantity_display} × {line.title}",
            sort=("title", "start"),
        ),
        Column(
            "supplier",
            _("Supplier"),
            cell=_supplier,
            text=lambda line: str(line.supplier) if line.supplier_id else gettext("open"),
            sort=("supplier__name", "start"),
            group="supplier",
            group_label=lambda line: str(line.supplier) if line.supplier_id else gettext("open"),
        ),
        Column("period", _("Period"), cell=_period, sort="start", css="nowrap"),
        Column(
            "status",
            _("Status"),
            cell=lambda line: badge(line.get_subrental_status_display(), status_colour(line.subrental_status)),
            text=lambda line: line.get_subrental_status_display(),
            sort=("subrental_status", "start"),
            group="subrental_status",
        ),
        Column(
            "purchase_price",
            _("Purchase price"),
            cell=lambda line: format_money(line.purchase_price),
            text=lambda line: line.purchase_price,
            sort=("purchase_price", "start"),
            css="num",
            visible_if=_purchase_prices,
            group="purchase_price",  # UIX-044; "what" and "period" group by the text they show
        ),
    ],
    default_sort="period",
    prefix="subrentals_",
)
