# SPDX-License-Identifier: GPL-3.0-or-later
"""The kind of an asset and its useful life, as the settings say (incoming invoices; MAT-086).

The fields of a booked-in item – ``asset_kind``, ``useful_life_months``, ``acquisition_cost_net``,
``ancillary_cost_net`` and, as the date of acquisition, ``purchase_date`` – are filled by
:mod:`rentalars.incoming.booking`; what the kind is when nobody names one is worked out here.
"""

from __future__ import annotations

from decimal import Decimal

from django.utils.translation import gettext as _

from rentalars.core.money import money
from rentalars.material.asset_models import AssetSettings
from rentalars.material.models import AssetKind


def low_value_limit() -> Decimal:
    """The limit up to which a piece is a low-value asset (GWG), net (Einstellungen → Eingangsrechnungen)."""
    return AssetSettings.load().low_value_limit_net


def low_value_problem(kind: str, cost: Decimal | None, pieces: int = 1) -> str:
    """Why an asset of this cost cannot be a low-value asset (GWG): empty if it can.

    A piece costing more than the limit of the settings (net, 800 € by default) is a fixed asset. The cost is that of the
    whole row; ``pieces`` is how many pieces the row stands for.
    """
    if kind != AssetKind.LOW_VALUE or cost is None:
        return ""
    each = cost / max(pieces, 1)
    limit = low_value_limit()
    if each <= limit:
        return ""
    return str(
        _("A low-value asset (GWG) costs at most %(limit)s net per piece; this one %(cost)s. Choose fixed asset.")
        % {"limit": money(limit), "cost": money(each)}
    )


def default_useful_life() -> int:
    """The useful life of a fixed asset that names none, in months."""
    return AssetSettings.load().default_useful_life_months


def kind_for(cost_per_piece: Decimal | None, chosen: str = "") -> str:
    """The kind of asset of a piece: the chosen one, else by the limit; empty when there is neither.

    Up to the limit – inclusive: 800 € is still a low-value asset – a piece is a low-value asset, above it a fixed
    asset. Merchandise is never guessed: it has to be chosen.
    """
    if chosen in AssetKind.values:
        return chosen
    if cost_per_piece is None:
        return ""
    return AssetKind.LOW_VALUE if cost_per_piece <= low_value_limit() else AssetKind.FIXED_ASSET


def life_for(kind: str, chosen: int | None = None) -> int | None:
    """The useful life of an asset in months: for a fixed asset the chosen one, else the standard; none otherwise.

    A low-value asset is written off at once and merchandise not at all – a useful life named for them is not kept
    (R1-18: it would only mislead, e.g. when the kind is changed later).
    """
    if kind != AssetKind.FIXED_ASSET:
        return None
    return chosen or default_useful_life()
