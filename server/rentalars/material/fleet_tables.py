# SPDX-License-Identifier: GPL-3.0-or-later
"""Materialverwaltung → Fuhrpark as a table: columns to choose, sorting, groups and CSV (LOG-002, UIX-040).

The rows are the items of vehicle products, loaded as a list – a fleet has
tens of vehicles, not thousands – with what ``material.fleet.attach`` hangs
on them: the vehicle data, the most urgent inspection (LOG-014) and the
current or next booking (LOG-004). So every column sorts and groups in
Python.
"""

from __future__ import annotations

import datetime
from typing import Any

from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from rentalars.core.tables import Column, TableDefinition, badge, date_text, link
from rentalars.core.templatetags.rentalars import status_colour
from rentalars.material.fleet import seats_missing


def _vehicle(item: Any, name: str) -> Any:
    vehicle = item.fleet_vehicle
    return getattr(vehicle, name) if vehicle is not None else None


def _plate(item: Any) -> str:
    return _vehicle(item, "licence_plate") or ""


def _type(item: Any) -> str:
    product = item.product
    return str(product.get_vehicle_type_display()) if product is not None and product.vehicle_type else ""


def _product(item: Any) -> Any:
    product = item.product
    if product is None:
        return ""
    return link(reverse("products:detail", args=[product.pk]), f"{product.article_number} {product.name}")


def _product_text(item: Any) -> str:
    product = item.product
    return f"{product.article_number} {product.name}" if product is not None else ""


def _seats_text(item: Any) -> str:
    vehicle = item.fleet_vehicle
    return vehicle.seats_text if vehicle is not None else ""


def _seats(item: Any) -> Any:
    """LOG-003: "2–9", or the hint that a motor vehicle lacks its seats."""
    if seats_missing(item, item.fleet_vehicle):
        return badge(gettext("seats missing"), "yellow")
    return _seats_text(item)


def _seats_sort(item: Any) -> Any:
    return _vehicle(item, "seats_max")


def _due(item: Any) -> SafeString | str:
    """LOG-014: the most urgent inspection – overdue in red, soon in yellow, as in the inspection lists."""
    due = item.fleet_due
    if due is None:
        return ""
    when = date_text(due.due_date) if due.due_date else gettext("never inspected")
    text = f"{due.inspection_type.name}: {when}"
    if due.state == "overdue":
        return badge(text, "red")
    if due.state == "soon":
        return badge(text, "yellow")
    return text


def _due_text(item: Any) -> str:
    due = item.fleet_due
    if due is None:
        return ""
    return f"{due.inspection_type.name}: {date_text(due.due_date) if due.due_date else gettext('never inspected')}"


def _due_sort(item: Any) -> Any:
    due = item.fleet_due
    return due.sort_key if due is not None else None


def _booking(item: Any) -> SafeString | str:
    """LOG-004: the booking that runs now or comes next; overlapping bookings in red."""
    booking = item.fleet_booking
    if booking is None:
        return ""
    period = f"{date_text(booking.start)} – {date_text(booking.end)}"
    name = link(booking.url, booking.label) if booking.url else booking.label
    text = format_html('{} <span class="muted small">{}</span>', name, period)
    if booking.is_current:
        text = format_html("{} {}", badge(gettext("now"), "accent"), text)
    if item.fleet_overlap:
        text = format_html("{} {}", text, badge(gettext("overlapping bookings"), "red"))
    return text


def _booking_text(item: Any) -> str:
    booking = item.fleet_booking
    if booking is None:
        return ""
    return f"{booking.label} {date_text(booking.start)} – {date_text(booking.end)}"


def _booking_sort(item: Any) -> Any:
    booking = item.fleet_booking
    return booking.start if booking is not None else None


def _weight(item: Any) -> Any:
    return _vehicle(item, "gross_weight_kg")


def _towing(item: Any) -> Any:
    return _vehicle(item, "towing_capacity_kg")


FLEET_TABLE = TableDefinition(
    "fleet",
    [
        Column(
            "id",
            _("ID"),
            cell=lambda item: link(reverse("material:item_detail", args=[item.pk]), item.display_id, "tape"),
            text=lambda item: item.display_id,
            sort="inventory_number",
            fixed=True,
        ),
        Column("plate", _("Licence plate"), cell=_plate, sort=_plate, css="nowrap"),
        Column("type", _("Type"), cell=_type, sort=_type),
        Column(
            "model",
            _("Model"),
            cell=lambda item: link(
                reverse("material:model_detail", args=[item.material_model_id]), item.material_model.name
            ),
            text=lambda item: item.material_model.name,
            sort=lambda item: item.material_model.name,
            group=lambda item: item.material_model_id,
        ),
        Column("product", _("Product"), cell=_product, text=_product_text, sort=_product_text),
        Column("seats", _("Seats"), cell=_seats, text=_seats_text, sort=_seats_sort, css="nowrap"),
        Column(
            "licence_class",
            _("Driving licence class"),
            cell=lambda item: _vehicle(item, "licence_class") or "",
            sort=lambda item: _vehicle(item, "licence_class") or "",
        ),
        Column(
            "status",
            _("Status"),
            cell=lambda item: badge(item.get_status_display(), status_colour(item.status)),
            text=lambda item: item.get_status_display(),
            sort=lambda item: str(item.get_status_display()),
            group="status",
            group_label=lambda item: badge(item.get_status_display(), status_colour(item.status)),
        ),
        Column(
            "due",
            _("Next inspection"),
            cell=_due,
            text=_due_text,
            sort=_due_sort,
            group=lambda item: item.fleet_due.state if item.fleet_due is not None else "",
            group_label=lambda item: item.fleet_due.state_label if item.fleet_due is not None else "–",
        ),
        Column("booking", _("Current or next booking"), cell=_booking, text=_booking_text, sort=_booking_sort),
        Column(
            "towing",
            _("Towing capacity (kg)"),
            cell=lambda item: _towing(item) if _towing(item) is not None else "",
            text=_towing,
            sort=_towing,
            css="num",
            default=False,
        ),
        Column(
            "weight",
            _("Permissible total weight (kg)"),
            cell=lambda item: _weight(item) if _weight(item) is not None else "",
            text=_weight,
            sort=_weight,
            css="num",
            default=False,
        ),
        Column(
            "serial",
            _("Serial number"),
            cell=lambda item: item.serial_number,
            sort=lambda item: item.serial_number,
            default=False,
        ),
        Column(
            "purchased",
            _("Invoice date"),
            cell=lambda item: item.purchase_date_text,  # "2015" / "05.2015" when day or month are unknown
            text=lambda item: item.purchase_date if item.purchase_date_precision == "day" else item.purchase_date_text,
            sort=lambda item: (
                item.purchase_date or datetime.date.min,
                -["day", "month", "year"].index(item.purchase_date_precision),
            ),
            css="nowrap",
            default=False,
        ),
    ],
    default_sort="id",
)
