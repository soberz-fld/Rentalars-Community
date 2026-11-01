# SPDX-License-Identifier: GPL-3.0-or-later
"""The lists of people and job functions as tables with columns to choose (UIX-015, IMP-005).

Phone, e-mail and address of people are personnel data: the lists live in the
personnel module, which only those with personnel rights open (NFA-010).
"""

from __future__ import annotations

from typing import Any

from django.db.models import OuterRef
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from rentalars.accounts import data_access
from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.core.i18n import local_pattern
from rentalars.core.money import format_decimal, format_money
from rentalars.core.tables import Column, TableDefinition, badge, first_value, link
from rentalars.personnel.models import PersonJobFunction, Qualification


def _costs(rights: Rights) -> bool:
    return rights.has(SpecialRight.PERSONNEL_COSTS)


def _prices(rights: Rights) -> bool:
    return rights.has(SpecialRight.PRICES)


def _muted(record: Any) -> str:
    return "" if record.is_active else "is-muted"


def _person_name(person: Any) -> Any:
    name = link(reverse("personnel:person_detail", args=[person.pk]), person.sort_name)
    if not person.is_active:
        name = format_html('{} <span class="badge">{}</span>', name, _("deactivated"))
    if person.company:
        return format_html('{}<div class="muted small">{}</div>', name, person.company)
    return name


def _functions(person: Any) -> list[str]:
    """The job functions of a person, each once (the rates are a history per function)."""
    names = {rate.job_function.name for rate in person.rates.all()}
    return sorted(names, key=str.lower)


def _contact(person: Any) -> Any:
    parts = [part for part in (person.phone, person.email) if part]
    return format_html_join(format_html("<br>"), "{}", ((part,) for part in parts))


def _qualifications(person: Any) -> Any:
    """Qualifications as small badges, coloured by how long they are still valid (PER-014)."""
    today = timezone.localdate()
    entries = []
    for qualification in person.qualifications.all():
        colour = ""
        if qualification.valid_until is not None:
            colour = "red" if qualification.valid_until < today else ("yellow" if qualification.state == "soon" else "")
        entries.append(badge(qualification.qualification_type.name, colour))
    return format_html_join(" ", "{}", ((entry,) for entry in entries))


def _qualification_text(person: Any) -> str:
    return ", ".join(
        f"{q.qualification_type.name} ({q.valid_until:{local_pattern('%d.%m.%Y')}})"
        if q.valid_until
        else q.qualification_type.name
        for q in person.qualifications.all()
    )


PERSON_TABLE = TableDefinition(
    "people",
    [
        Column(
            "name",
            _("Name"),
            cell=_person_name,
            text=lambda person: person.sort_name,
            sort=("last_name", "first_name"),
            fixed=True,
        ),
        Column(
            "kind",
            _("Kind"),
            cell=lambda person: capfirst(person.get_kind_display()),
            sort=("kind", "last_name"),
            group="kind",
        ),
        Column(
            "functions",
            _("Job functions"),
            cell=lambda person: format_html_join(
                " ", '<span class="badge">{}</span>', ((name,) for name in _functions(person))
            ),
            text=lambda person: ", ".join(_functions(person)),
            # UIX-015: by the first of the functions in the alphabet.
            sort=(
                first_value(PersonJobFunction.objects.filter(person=OuterRef("pk")), "job_function__name"),
                "last_name",
                "first_name",
            ),
        ),
        Column(
            "contact",
            pgettext_lazy("contact data", "Contact"),
            cell=_contact,
            text=lambda person: ", ".join(part for part in (person.phone, person.email) if part),
            sort=("phone", "email", "last_name"),
        ),
        Column(
            "account",
            _("Account"),
            cell=lambda person: person.user.username if person.user_id else format_html('<span class="muted">–</span>'),
            text=lambda person: person.user.username if person.user_id else "",
            sort=("user__username", "last_name"),
            group="user",
        ),
        Column(
            "qualifications",
            _("Qualifications"),
            cell=_qualifications,
            text=_qualification_text,
            sort=(
                first_value(Qualification.objects.filter(person=OuterRef("pk")), "qualification_type__name"),
                "last_name",
                "first_name",
            ),
            default=False,
        ),
        Column(
            "email",
            _("E-mail"),
            cell=lambda person: person.email,
            sort=("email", "last_name"),
            default=False,
            group="email",
        ),
        Column(
            "phone",
            _("Phone"),
            cell=lambda person: person.phone,
            sort=("phone", "last_name"),
            default=False,
            group="phone",
        ),
        Column(
            "company",
            _("Company"),
            cell=lambda person: person.company,
            sort=("company", "last_name"),
            default=False,
            group="company",
        ),
        Column(
            "street",
            _("Street"),
            cell=lambda person: person.street,
            sort=("street", "last_name"),
            default=False,
            group="street",
        ),
        Column(
            "postal_code",
            _("Postal code"),
            cell=lambda person: person.postal_code,
            sort=("postal_code", "last_name"),
            default=False,
            group="postal_code",
        ),
        Column(
            "city",
            _("City"),
            cell=lambda person: person.city,
            sort=("city", "last_name"),
            default=False,
            group="city",
        ),
        Column(
            "active",
            _("Active"),
            cell=lambda person: _("yes") if person.is_active else _("no"),
            text=lambda person: person.is_active,
            sort=("is_active", "last_name"),
            default=False,
            group="is_active",
        ),
        # AUT-034: finances, personnel data, customer data – what the account may see (accounts/data_access.py).
        *data_access.columns(lambda person: person.user if person.user_id else None),
    ],
    default_sort="name",
    row_css=_muted,
)


def _function_name(function: Any) -> Any:
    name = function.name
    if getattr(function, "may_edit", False):
        name = link(reverse("personnel:job_function_edit", args=[function.pk]), function.name)
    if not function.is_active:
        return format_html('{} <span class="badge">{}</span>', name, _("deactivated"))
    return name


def _service_product(function: Any) -> Any:
    """PER-037: the service product, linked to its page for whoever may read products (PRD-044: always one)."""
    product = function.service_product
    if product is None:
        return ""
    label = format_html('<span class="artno">{}</span> {}', product.article_number, product.name)
    if getattr(function, "may_open_product", False):
        return link(reverse("products:detail", args=[product.pk]), label)
    return label


def _customer_price(function: Any) -> Any:
    """The price per hour of the service product; PER-035 with the price from the limit; a hint without price."""
    product = function.service_product
    if product is None:
        return ""
    if product.price is None:
        return badge(_("no price yet"), "yellow")
    if product.hours_limit is not None and product.price_above_limit is not None:
        return format_html(
            '{}<div class="sub">{}</div>',
            format_money(product.price),
            _("from %(limit)s h a day: %(price)s")
            % {"limit": format_decimal(product.hours_limit), "price": format_money(product.price_above_limit)},
        )
    return format_money(product.price)


JOB_FUNCTION_TABLE = TableDefinition(
    "job_functions",
    [
        # UIX-044: every column groups – by its field; the price and the number of people by what they show.
        Column(
            "name",
            _("Job function"),
            cell=_function_name,
            text=lambda function: function.name,
            sort="name",
            fixed=True,
            group="name",
            group_label=lambda function: function.name,
        ),
        Column(
            "service_product",
            _("Service product"),
            cell=_service_product,
            text=lambda function: (
                f"{function.service_product.article_number} {function.service_product.name}"
                if function.service_product_id
                else ""
            ),
            sort=("service_product__article_number", "name"),
            group="service_product",
        ),
        Column(
            "price",
            _("Price for the customer"),
            cell=_customer_price,
            text=lambda function: function.service_product.price if function.service_product_id else None,
            sort=("service_product__price", "name"),
            css="num",
            visible_if=_prices,
        ),
        Column(
            "guide_cost_rate",
            _("Guide value for costs"),
            cell=lambda function: format_money(function.guide_cost_rate) or "–",
            text=lambda function: function.guide_cost_rate,
            sort=("guide_cost_rate", "name"),
            css="num",
            visible_if=_costs,
            group="guide_cost_rate",
        ),
        Column(
            # PER-029: the guide value per day, for crew lines charged per day.
            "guide_daily_cost_rate",
            _("Guide value per day"),
            cell=lambda function: format_money(function.guide_daily_cost_rate) or "–",
            text=lambda function: function.guide_daily_cost_rate,
            sort=("guide_daily_cost_rate", "name"),
            css="num",
            visible_if=_costs,
            group="guide_daily_cost_rate",
        ),
        Column(
            # PER-026: empty is no limit, 0 never discounted.
            "max_discount",
            _("Maximum discount"),
            cell=lambda function: (
                f"{format_decimal(function.max_discount_percent)} %"
                if function.max_discount_percent is not None
                else "–"
            ),
            text=lambda function: function.max_discount_percent,
            sort=("max_discount_percent", "name"),
            css="num",
            visible_if=_prices,
            group="max_discount_percent",
        ),
        Column(
            "people",
            _("People"),
            cell=lambda function: function.people_count,
            sort=("people_count", "name"),
            css="num",
            default=False,
        ),
    ],
    default_sort="name",
    row_css=_muted,
)
