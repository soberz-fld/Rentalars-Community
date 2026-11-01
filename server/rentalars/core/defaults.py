# SPDX-License-Identifier: GPL-3.0-or-later
"""Start data of a fresh installation (PRD-015, PRD-016, PRD-027, ADM-003, chapter 4).

The start data is installed exactly once, right after the database tables
were created. A marker in the system settings remembers that this happened;
later runs of ``migrate`` leave everything alone, so that rows an
administrator changed or removed do not come back.

Each module describes its own start data in a ``defaults`` module with an
``install()`` function; this module only decides *when* they run.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from rentalars.core.audit import acting_as

#: The number ranges of the documents of stage 5 (DOK-005) and of the offer (DOK-010); a new database gets them
#: from the migrations of ``core`` and ``documents`` already, existing installations got them with their updates.
DOCUMENT_NUMBER_RANGES: dict[str, dict[str, Any]] = {
    "offer": {"prefix": "AN-{year}-", "min_digits": 4, "reset_yearly": True},
    "order_confirmation": {"prefix": "AB-{year}-", "min_digits": 4, "reset_yearly": True},
    "delivery_note": {"prefix": "LS-{year}-", "min_digits": 4, "reset_yearly": True},
    "invoice": {"prefix": "RE-{year}-", "min_digits": 4, "reset_yearly": True},
    "crew_sheet": {"prefix": "CD-{year}-", "min_digits": 4, "reset_yearly": True},
}

#: ADM-014: the prefix of the project numbers of a new installation – 2026-0042, without "P-" (ADM-012).
PROJECT_PREFIX = "{year}-"


def install_number_ranges() -> None:
    """Create the number ranges with the defaults of ADM-003."""
    from rentalars.core.models import NumberRange, NumberRangeKey

    defaults: dict[str, dict[str, Any]] = {
        # Project number: year and running number, e.g. 2026-0042 (ADM-014).
        NumberRangeKey.PROJECT: {"prefix": PROJECT_PREFIX, "min_digits": 4, "reset_yearly": True},
        NumberRangeKey.CUSTOMER: {"prefix": "", "min_digits": 5, "start_value": 10001, "next_value": 10001},
        # Material ID: four digits, consecutive (MAT-003).
        NumberRangeKey.MATERIAL_ITEM: {"prefix": "", "min_digits": 4},
        NumberRangeKey.DOCUMENT: {"prefix": "{year}-", "min_digits": 4, "reset_yearly": True},
        **DOCUMENT_NUMBER_RANGES,
    }
    for key, values in defaults.items():
        if not NumberRange.objects.filter(key=key).exists():
            NumberRange(key=key, **values).save()


@transaction.atomic
def install_defaults() -> bool:
    """Install the start data of all modules unless that already happened.

    Returns:
        ``True`` if the data was installed now, ``False`` if it was there.
    """
    from rentalars.accounts import defaults as account_defaults
    from rentalars.core.models import SystemSettings
    from rentalars.masterdata import defaults as masterdata_defaults
    from rentalars.personnel import defaults as personnel_defaults
    from rentalars.products import defaults as product_defaults

    system_settings = SystemSettings.load()
    if system_settings.defaults_installed:
        return False
    with acting_as("system:setup"):
        install_number_ranges()
        masterdata_defaults.install()
        product_defaults.install()
        # PER-037: the job functions with their service products – after the categories and tax rates.
        personnel_defaults.install()
        account_defaults.install()
        # UIX-029: in English for an installation whose language is English.
        from rentalars.core.i18n import installation_language
        from rentalars.core.start_data import localise

        if installation_language() != "de":
            localise(installation_language())
        system_settings.defaults_installed = True
        system_settings.save()
    return True


def install_defaults_after_migrate(sender: Any, **kwargs: Any) -> None:
    """Signal handler: runs after ``migrate`` finished creating the tables."""
    install_defaults()
