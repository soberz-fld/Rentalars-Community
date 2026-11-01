# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings for assets booked in from incoming invoices: the limit of a low-value asset, the usual useful life (MAT-086).

The requirement: on purchase invoices, spread transport costs as ancillary acquisition costs; mark each position as
goods, low-value asset (GWG) or fixed asset with a depreciation period. The limit up to which a piece counts as a low-value asset (GWG; 800 € net in Germany) and
the useful life a fixed asset gets when nobody names one are set here, once for the company
(Einstellungen → Eingangsrechnungen). Imported at the end of ``rentalars/material/models.py`` so that Django finds
the table.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from rentalars.core.models import SingletonModel

#: A piece up to 800 € net (acquisition cost with ancillary costs) is a low-value asset (§ 6 Abs. 2 EStG).
DEFAULT_LOW_VALUE_LIMIT = Decimal("800.00")
#: Five years – the usual useful life of event technology in the depreciation tables of many tax advisers.
DEFAULT_USEFUL_LIFE_MONTHS = 60
MAX_USEFUL_LIFE_MONTHS = 600


class AssetSettings(SingletonModel):
    """Einstellungen → Eingangsrechnungen: GWG limit and standard useful life (incoming invoices).

    ``material.assets`` reads them when the kind of an item is worked out; the depreciation of items builds on the
    fields of the item, not on these settings.
    """

    low_value_limit_net = models.DecimalField(
        _("limit of a low-value asset (GWG), net"),
        max_digits=10,
        decimal_places=2,
        default=DEFAULT_LOW_VALUE_LIMIT,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_(
            "A piece whose acquisition cost – price plus its share of the ancillary costs – does not exceed this "
            "amount counts as a low-value asset, a more expensive one as a fixed asset, unless you choose otherwise. "
            "In Germany the limit is 800 € net."
        ),
    )
    default_useful_life_months = models.PositiveSmallIntegerField(
        _("standard useful life (months)"),
        default=DEFAULT_USEFUL_LIFE_MONTHS,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_USEFUL_LIFE_MONTHS)],
        help_text=_("A fixed asset without a useful life of its own gets this one. 60 months are five years."),
    )
    # Depreciation, "Mit Restbuchwert": leave 1 € of a fully depreciated fixed asset in the books.
    keep_memory_value = models.BooleanField(
        _("keep a memory value of 1 €"),
        default=False,
        help_text=_(
            "A fixed asset that is fully depreciated stays in the books with 1 € (Erinnerungswert) until it is sold or "
            "retired. Off: the book value goes down to 0 €."
        ),
    )

    class Meta:
        verbose_name = _("asset settings")
        verbose_name_plural = _("asset settings")

    def __str__(self) -> str:
        return str(_("Asset settings"))
