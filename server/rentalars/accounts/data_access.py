# SPDX-License-Identifier: GPL-3.0-or-later
"""What an account may see of finances, personnel data and customer data (AUT-034; AUT-019, NFA-010).

The requirement: a column in both lists that shows whether the person may see financial details (material prices), personnel data and customer data (data protection).

Three optional columns of both lists (``core.tables``), computed from the
roles of the account (``accounts.rights``) – exactly what the pages and the
API ask:

Finances ("Finanzen")
    the special rights "See prices and calculation" (prices) and "See purchase
    prices" – which of them.
Personnel data ("Personaldaten")
    the module "Personnel" (the people with their contact data and addresses)
    and the special right "See hourly rates and personnel costs" – which of
    them.
Customer data ("Kundendaten")
    the module "Customers": read, or change as well.

"No access" for an account that cannot log in – deactivated, past its "valid
until" (AUT-024), or without a password yet (every person has an account,
AUT-026; a person never invited has no login) – and for a person without an
account. An account with all
rights has every right. The API delivers the same as ``data_access`` of
``/users`` and ``/people``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from rentalars.accounts.rights import Level, Module, Rights, SpecialRight, rights_of
from rentalars.core.tables import Column, badge

#: The values of a column: key → label; the order is the order of sorting.
FINANCES = {
    "none": pgettext_lazy("data access", "no"),
    "purchase_prices": _("purchase prices"),
    "prices": _("prices"),
    "both": _("prices and purchase prices"),
}
PERSONNEL_DATA = {
    "none": pgettext_lazy("data access", "no"),
    "rates": _("hourly rates"),
    "people": _("people"),
    "both": _("people and hourly rates"),
}
CUSTOMER_DATA = {
    "none": pgettext_lazy("data access", "no"),
    "read": pgettext_lazy("data access", "read"),
    "change": pgettext_lazy("data access", "change"),
}
#: A person without an account, or a deactivated account. The legend below the lists:
#: ``templates/accounts/_data_access_legend.html``.
NO_ACCESS = "no_access"
NO_ACCESS_LABEL = pgettext_lazy("data access", "no access")


@dataclass(frozen=True)
class DataAccess:
    """The three answers for one account; each a key of its mapping above, or :data:`NO_ACCESS`."""

    finances: str
    personnel_data: str
    customer_data: str

    def as_document(self) -> dict[str, str]:
        """For the API: the three keys."""
        return {
            "finances": self.finances,
            "personnel_data": self.personnel_data,
            "customer_data": self.customer_data,
        }


NONE_AT_ALL = DataAccess(NO_ACCESS, NO_ACCESS, NO_ACCESS)


def _pair(first: bool, second: bool, *, both: str, one: str, other: str) -> str:
    if first and second:
        return both
    if first:
        return one
    if second:
        return other
    return "none"


def of_rights(rights: Rights) -> DataAccess:
    """The answers for these rights."""
    customers = rights.level(Module.CUSTOMERS)
    return DataAccess(
        finances=_pair(
            rights.has(SpecialRight.PRICES),
            rights.has(SpecialRight.PURCHASE_PRICES),
            both="both",
            one="prices",
            other="purchase_prices",
        ),
        personnel_data=_pair(
            rights.can_read(Module.PERSONNEL),
            rights.has(SpecialRight.PERSONNEL_COSTS),
            both="both",
            one="people",
            other="rates",
        ),
        customer_data="change" if customers >= Level.WRITE else ("read" if customers >= Level.READ else "none"),
    )


def can_log_in(user: Any) -> bool:
    """Whether an account can log in: active, with a password, and not past the day it is valid until.

    Every person gets an account (AUT-026), but a login only with a password (an invitation not taken up yet
    counts as none). AUT-024: an account past its "valid until" is closed at the next login or by the nightly job –
    until then it counts as closed already (AUT-035: the tab "Zugriff" asks the same).
    """
    return (
        user is not None
        and bool(getattr(user, "is_active", False))
        and user.has_usable_password()
        and not getattr(user, "has_expired", False)
    )


def of_user(user: Any) -> DataAccess:
    """The answers for an account (``None``: no account).

    "No access" for an account that cannot log in (:func:`can_log_in`): deactivated, expired, or without a
    password yet.
    """
    if not can_log_in(user):
        return NONE_AT_ALL
    return of_rights(rights_of(user))


def label(value: str, mapping: dict[str, Any]) -> Any:
    """The label of one answer."""
    return NO_ACCESS_LABEL if value == NO_ACCESS else mapping[value]


def _rank(value: str, mapping: dict[str, Any]) -> int:
    """The place of an answer when sorting: no access first, then from little to much."""
    return -1 if value == NO_ACCESS else list(mapping).index(value)


#: The colour of an answer in the list: much access stands out (yellow), none is plain.
_COLOURS = {"both": "yellow", "prices": "yellow", "people": "yellow", "change": "yellow"}


def columns(user_of: Callable[[Any], Any]) -> list[Column]:
    """The three columns for a list whose rows lead to an account through ``user_of`` (the row → user or ``None``)."""

    def column(key: str, heading: Any, attribute: str, mapping: dict[str, Any]) -> Column:
        def value(row: Any) -> str:
            return getattr(of_user(user_of(row)), attribute)

        def cell(row: Any) -> Any:
            answer = value(row)
            if answer in ("none", NO_ACCESS):
                return label(answer, mapping)
            return badge(label(answer, mapping), _COLOURS.get(answer, ""))

        return Column(
            key,
            heading,
            cell=cell,
            text=lambda row: str(label(value(row), mapping)),
            sort=lambda row: _rank(value(row), mapping),
            default=False,
        )

    return [
        column("finances", _("Finances"), "finances", FINANCES),
        column("personnel_data", _("Personnel data"), "personnel_data", PERSONNEL_DATA),
        column("customer_data", _("Customer data"), "customer_data", CUSTOMER_DATA),
    ]


#: The keys of the columns, for the templates (the legend shows when one of them is shown).
COLUMN_KEYS = ("finances", "personnel_data", "customer_data")
