# SPDX-License-Identifier: GPL-3.0-or-later
"""Einstellungen → Mietstaffeln as a table: columns to choose, sorting, groups and CSV (PRD-015, UIX-040).

The scales are rows, the factors of the current version one cell ("1 Tag: 1 · 2 Tage:
1,6 · … · jeder weitere Tag: + 0,4"). Editing a scale shows the full table as before.
"""

from __future__ import annotations

from typing import Any

from django.db.models import OuterRef, Subquery
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeString
from django.utils.translation import gettext, ngettext
from django.utils.translation import gettext_lazy as _

from rentalars.core.money import format_decimal
from rentalars.core.tables import Column, TableDefinition, badge, date_text, first_value, link
from rentalars.masterdata.models import Category, RentalScaleVersion


def _prepare(scales: list[Any]) -> None:
    """The current version of each scale with its rows – once per row of the page."""
    for scale in scales:
        scale.shown_version = scale.current_version
        scale.shown_rows = list(scale.shown_version.rows.order_by("days")) if scale.shown_version else []


def _name(scale: Any) -> SafeString:
    name = (
        link(reverse("products:scale_edit", args=[scale.pk]), scale.name)
        if getattr(scale, "can_edit", False)
        else format_html("{}", scale.name)
    )
    marks = []
    if scale.is_default:
        marks.append(badge(gettext("default"), "accent"))
    if not scale.is_active:
        marks.append(badge(gettext("deactivated")))
    return format_html("{} {}", name, format_html_join(" ", "{}", ((mark,) for mark in marks)))


def _factors(scale: Any) -> str:
    if scale.shown_version is None:
        return gettext("This scale has no table yet.")
    parts = [
        ngettext("%(days)s day: %(factor)s", "%(days)s days: %(factor)s", row.days)
        % {"days": row.days, "factor": format_decimal(row.factor)}
        for row in scale.shown_rows
    ]
    parts.append(
        gettext("each further day: + %(increment)s")
        % {"increment": format_decimal(scale.shown_version.extra_day_increment)}
    )
    return " · ".join(parts)


def _version(scale: Any) -> str:
    version = scale.shown_version
    if version is None:
        return ""
    return gettext("Version %(number)s of %(date)s") % {"number": version.number, "date": date_text(version.created_at)}


def _prepare_for_sorting(scales: list[Any], request: Any) -> None:
    _prepare(scales)


def _factor_key(scale: Any) -> tuple[Any, ...] | None:
    """The factors of the current version in the order of the days, then the increment of each further day."""
    version = getattr(scale, "shown_version", None)
    if version is None:
        return None
    return (*(row.factor for row in scale.shown_rows), version.extra_day_increment)


SCALE_TABLE = TableDefinition(
    "rental_scales",
    [
        # UIX-044: factors, categories and version group by what they show – a handful of scales.
        Column("name", _("Name"), cell=_name, text=lambda scale: scale.name, sort="name", fixed=True, group="name"),
        # UIX-015: by the factors of the current version, day by day – a handful of scales, in Python.
        Column("factors", _("Factors"), cell=_factors, sort=_factor_key, sort_prepare=_prepare_for_sorting),
        Column(
            "categories",
            _("Used by the categories"),
            cell=lambda scale: ", ".join(category.name for category in scale.categories.all()),
            sort=(first_value(Category.objects.filter(rental_scale=OuterRef("pk")), "name"), "name"),
        ),
        Column(
            "version",
            _("Version"),
            cell=_version,
            # The day of the current (newest) version.
            sort=(
                Subquery(
                    RentalScaleVersion.objects.filter(scale=OuterRef("pk")).order_by("-number").values("created_at")[:1]
                ),
                "name",
            ),
            default=False,
        ),
        Column(
            "default",
            _("Default scale"),
            cell=lambda scale: gettext("yes") if scale.is_default else gettext("no"),
            text=lambda scale: scale.is_default,
            sort=("-is_default", "name"),
            default=False,
            group="is_default",
        ),
        Column(
            "active",
            _("Active"),
            cell=lambda scale: gettext("yes") if scale.is_active else gettext("no"),
            text=lambda scale: scale.is_active,
            sort=("-is_active", "name"),
            default=False,
            group="is_active",
            group_label=lambda scale: gettext("active") if scale.is_active else gettext("deactivated"),
        ),
    ],
    default_sort="name",
    prepare=_prepare,
    row_css=lambda scale: "" if scale.is_active else "is-muted",
)
