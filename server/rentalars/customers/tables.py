# SPDX-License-Identifier: GPL-3.0-or-later
"""The customer and venue lists as tables with columns to choose (UIX-015, IMP-005)."""

from __future__ import annotations

from typing import Any

from django.db.models import Case, Value, When
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.core.money import format_decimal
from rentalars.core.tables import Column, TableDefinition, date_text, grouped_by_day, link

#: UIX-015: whether a venue has a hall plan, for sorting by the column "Hall plan".
HAS_HALL_PLAN = Case(When(hall_plan="", then=Value(0)), When(hall_plan__isnull=True, then=Value(0)), default=Value(1))


def _prices(rights: Rights) -> bool:
    return rights.has(SpecialRight.PRICES)


def _muted(record: Any) -> str:
    return "" if record.is_active else "is-muted"


def _customer_name(customer: Any) -> Any:
    name = link(reverse("customers:detail", args=[customer.pk]), customer.name)
    if not customer.is_active:
        return format_html('{} <span class="badge">{}</span>', name, _("deactivated"))
    return name


def _contact(customer: Any) -> str:
    return ", ".join(part for part in (customer.email, customer.phone) if part)


CUSTOMER_TABLE = TableDefinition(
    "customers",
    [
        # UIX-044: every column groups – by its field; contact and the number of projects by what they show.
        Column(
            "name",
            _("Name"),
            cell=_customer_name,
            text=lambda customer: customer.name,
            sort="name",
            fixed=True,
            group="name",
        ),
        Column("number", _("Number"), cell=lambda customer: customer.number, sort="number", group="number"),
        Column(
            "city",
            _("City"),
            cell=lambda customer: customer.city,
            sort=("city", "name"),
            group="city",
        ),
        Column("contact", pgettext_lazy("contact data", "Contact"), cell=_contact, sort=("email", "phone", "name")),
        Column(
            "projects", _("Projects"), cell=lambda customer: customer.project_count, sort="project_count", css="num"
        ),
        Column(
            "kind",
            _("Kind"),
            cell=lambda customer: customer.get_kind_display(),
            sort=("kind", "name"),
            default=False,
            group="kind",
        ),
        Column(
            "street",
            _("Street"),
            cell=lambda customer: customer.street,
            sort=("street", "name"),
            default=False,
            group="street",
        ),
        Column(
            "postal_code",
            _("Postal code"),
            cell=lambda customer: customer.postal_code,
            sort=("postal_code", "name"),
            default=False,
            group="postal_code",
        ),
        Column(
            "country",
            _("Country"),
            cell=lambda customer: customer.country,
            sort=("country", "name"),
            default=False,
            group="country",
        ),
        Column(
            "email",
            _("E-mail"),
            cell=lambda customer: customer.email,
            sort=("email", "name"),
            default=False,
            group="email",
        ),
        Column(
            "phone",
            _("Phone"),
            cell=lambda customer: customer.phone,
            sort=("phone", "name"),
            default=False,
            group="phone",
        ),
        Column(
            "vat_id",
            _("VAT ID"),
            cell=lambda customer: customer.vat_id,
            sort=("vat_id", "name"),
            default=False,
            group="vat_id",
        ),
        Column(
            "tax_number",
            _("Tax number"),
            cell=lambda customer: customer.tax_number,
            sort=("tax_number", "name"),
            default=False,
            group="tax_number",
        ),
        Column(
            "payment_terms",
            _("Payment terms (days)"),
            cell=lambda customer: customer.payment_terms_days if customer.payment_terms_days is not None else "",
            text=lambda customer: customer.payment_terms_days,
            sort=("payment_terms_days", "name"),
            css="num",
            default=False,
            group="payment_terms_days",
        ),
        Column(
            "discount",
            _("Default discount %"),
            cell=lambda customer: (
                format_decimal(customer.default_discount_percent) if customer.default_discount_percent else ""
            ),
            text=lambda customer: customer.default_discount_percent,
            sort=("default_discount_percent", "name"),
            css="num",
            default=False,
            visible_if=_prices,
            group="default_discount_percent",
        ),
        Column(
            "created",
            _("Created"),
            cell=lambda customer: date_text(customer.created_at),
            text=lambda customer: customer.created_at,
            sort="created_at",
            css="nowrap",
            default=False,
            **grouped_by_day("created_at"),
        ),
    ],
    default_sort="name",
    row_css=_muted,
)


def _venue_name(venue: Any) -> Any:
    name = link(reverse("customers:venue_detail", args=[venue.pk]), venue.name)
    if not venue.is_active:
        name = format_html('{} <span class="badge">{}</span>', name, _("deactivated"))
    if venue.street:
        return format_html('{}<div class="muted small">{}</div>', name, venue.street)
    return name


def _on_site(venue: Any) -> Any:
    if venue.contact_phone:
        return format_html('{}<div class="muted small">{}</div>', venue.contact_name, venue.contact_phone)
    return venue.contact_name


VENUE_TABLE = TableDefinition(
    "venues",
    [
        # UIX-044: every column groups – by its field; contact, projects and hall plan by what they show.
        Column(
            "name", _("Name"), cell=_venue_name, text=lambda venue: venue.name, sort="name", fixed=True, group="name"
        ),
        Column(
            "city",
            _("City"),
            cell=lambda venue: f"{venue.postal_code} {venue.city}".strip(),
            sort=("city", "name"),
            group="city",
        ),
        Column(
            "contact",
            _("Contact on site"),
            cell=_on_site,
            text=lambda venue: ", ".join(part for part in (venue.contact_name, venue.contact_phone) if part),
            sort=("contact_name", "contact_phone", "name"),
        ),
        Column("projects", _("Projects"), cell=lambda venue: venue.project_count, sort="project_count", css="num"),
        Column(
            "street",
            _("Street"),
            cell=lambda venue: venue.street,
            sort=("street", "name"),
            default=False,
            group="street",
        ),
        Column(
            "country",
            _("Country"),
            cell=lambda venue: venue.country,
            sort=("country", "name"),
            default=False,
            group="country",
        ),
        Column(
            "email",
            _("E-mail on site"),
            cell=lambda venue: venue.contact_email,
            sort=("contact_email", "name"),
            default=False,
            group="contact_email",
        ),
        Column(
            "access",
            _("Access and loading"),
            cell=lambda venue: venue.access_notes,
            sort=("access_notes", "name"),
            default=False,
            group="access_notes",
        ),
        Column(
            "power",
            _("Power"),
            cell=lambda venue: venue.power_notes,
            sort=("power_notes", "name"),
            default=False,
            group="power_notes",
        ),
        Column(
            "hall_plan",
            _("Hall plan"),
            cell=lambda venue: _("yes") if venue.hall_plan else "",
            text=lambda venue: bool(venue.hall_plan),
            # UIX-015: venues with a plan first when descending, those without when ascending.
            sort=(HAS_HALL_PLAN, "name"),
            default=False,
        ),
    ],
    default_sort="name",
    row_css=_muted,
)
