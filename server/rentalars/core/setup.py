# SPDX-License-Identifier: GPL-3.0-or-later
"""The first-run setup of a new installation (NFA-033).

The browser page collects company data, the first administrator, number
ranges and the standard tax rate; :func:`complete_setup` stores them in one
step. Until that happened, every request is redirected to the setup page.

On a server the setup page is protected by a one-time token that the
installation script prints. Otherwise whoever reaches the address first
could make himself administrator. Without a stored token the page stays
closed (NFA-064).
"""

from __future__ import annotations

import secrets
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import transaction

from rentalars.accounts.models import Role, User
from rentalars.core.audit import acting_as, record_event
from rentalars.core.defaults import install_defaults
from rentalars.core.i18n import installation_language, supported
from rentalars.core.models import CompanyProfile, NumberRange, NumberRangeKey, SystemSettings
from rentalars.core.start_data import localise
from rentalars.masterdata.models import TaxRate
from rentalars.projects.defaults import install_dry_hire_template


def setup_token_is_valid(candidate: str | None) -> bool:
    """Check the token from the setup link (NFA-033, NFA-064).

    The setup page creates the first administrator, so it must never be open
    to whoever finds it. If no token is stored – because the installation
    script has not got that far yet, or because somebody installed by hand
    and forgot ``prepare_setup`` – the answer is therefore "no", not "yes".
    The one exception is a developer's machine (``environment =
    development`` in the configuration file), which is not reachable by
    others and is set up again and again.

    The comparison takes the same time whether the token is nearly right or
    completely wrong, so it cannot be guessed character by character.
    """
    expected = SystemSettings.load().setup_token
    if not expected:
        return bool(settings.SETUP_OPEN_WITHOUT_TOKEN)
    if not candidate:
        return False
    return secrets.compare_digest(candidate.encode(), expected.encode())


@transaction.atomic
def complete_setup(data: dict[str, Any]) -> User:
    """Store the answers of the setup page and mark the setup as done.

    Args:
        data: The cleaned data of ``core.forms.SetupForm``.

    Returns:
        The administrator account that was created. It has the role
        "Administrator" and additionally all rights independent of roles, so
        that later changes to roles can never lock the company out.
    """
    install_defaults()
    with acting_as("system:setup"):
        company = CompanyProfile.load()
        company.name = data["company_name"]
        company.street = data.get("street", "")
        company.postal_code = data.get("postal_code", "")
        company.city = data.get("city", "")
        # UIX-029: the language chosen in the setup – of the documents and of the first administrator.
        language = supported(data.get("language", "")) or installation_language()
        company.document_language = language
        company.save()

        administrator = User.objects.create_superuser(
            username=data["username"],
            email=data["email"],
            password=data["password"],
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
        )
        administrator.language = language if language != installation_language() else ""
        administrator.save(update_fields=["language"])
        administrator.roles.set(Role.objects.filter(name="Administrator"))

        _set_number_range(
            NumberRangeKey.PROJECT, next_value=data["project_next"], prefix=data.get("project_prefix", "")
        )
        _set_number_range(NumberRangeKey.CUSTOMER, next_value=data["customer_next"])
        _set_number_range(NumberRangeKey.MATERIAL_ITEM, next_value=data["material_next"])
        _set_default_tax_rate(Decimal(data["default_tax_rate"]))
        # ADM-018: price and internal costs per hour of the job functions of the start data.
        _set_personnel_rates(data.get("personnel_price"), data.get("personnel_cost"))
        # PRJ-095: the project template "Dry Hire" – renting without crew.
        install_dry_hire_template()
        # UIX-029: the start data in the chosen language, as far as it still has its start names – nothing to do
        # for a German installation set up in German.
        if "en" in (language, installation_language()):
            localise(language)

        if data.get("with_demo_data"):
            from rentalars.core.demo import create_demo_data

            create_demo_data()

        system_settings = SystemSettings.load()
        system_settings.setup_completed = True
        system_settings.setup_token = ""
        system_settings.save()
        record_event(system_settings, "setup.completed")
    return administrator


def _set_number_range(key: str, *, next_value: int, prefix: str | None = None) -> None:
    """Apply the counter (and for projects the prefix) chosen in the setup."""
    number_range = NumberRange.objects.get(key=key)
    number_range.next_value = next_value
    number_range.start_value = 1 if number_range.reset_yearly else next_value
    if prefix is not None:
        number_range.prefix = prefix
    number_range.full_clean()
    number_range.save()


def _set_personnel_rates(price: Any, cost: Any) -> None:
    """ADM-018: give the job functions of the start data a customer price and internal costs per hour.

    Only functions still without them are touched – those of the start data
    (PER-037). The price is that of each function's service product (by the
    hour, PRD-044), the costs its guide value (PER-004). Both can be changed
    later under Personal → Funktionen, for each function on its own.
    """
    from rentalars.personnel.models import JobFunction

    for function in JobFunction.objects.select_related("service_product"):
        product = function.service_product
        if price is not None and product is not None and product.price is None:
            product.price = Decimal(price)
            product.save(update_fields=["price"])
        if cost is not None and function.guide_cost_rate is None:
            function.guide_cost_rate = Decimal(cost)
            function.save(update_fields=["guide_cost_rate"])


def _set_default_tax_rate(rate: Decimal) -> None:
    """Make the given percentage the default tax rate for new products (PRD-016)."""
    default = TaxRate.get_default()
    if default is not None and default.rate == rate:
        return
    name = f"{rate.normalize():f} %".replace(".", ",")
    tax_rate = TaxRate.objects.filter(rate=rate).first() or TaxRate(name=name, rate=rate)
    tax_rate.is_default = True
    tax_rate.save()
