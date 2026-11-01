# SPDX-License-Identifier: GPL-3.0-or-later
"""Book values of items and the Anlagenspiegel: what an item is worth in the books ("Mit Restbuchwert"; MAT-086).

The pure arithmetic is :mod:`rentalars.material.depreciation`; this module reads the asset data of the items
(``asset_kind``, ``useful_life_months``, ``acquisition_cost_net``, the date of acquisition ``purchase_date``) and the
setting "memory value", and builds

* :func:`value_of` – the valuation of one item on a day (the card "Anlagevermögen" of the item page),
* :func:`set_asset_data` – recording an item as asset, or correcting its asset data (old items have none),
* :func:`register` – the rows and sums of the stock-wide report "Anlagenspiegel / Restbuchwerte", with its filters
  (shared by the page, the CSV file and the API).

Everything is for who may see purchase prices (``rentalars.incoming.access`` – the rights of the register): the
costs of an item are purchase prices. This is a simplified standard setting and no tax advice, see
:mod:`rentalars.material.depreciation`.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Exists, OuterRef, Q, QuerySet
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from rentalars.material import depreciation
from rentalars.material.asset_models import AssetSettings
from rentalars.material.depreciation import ZERO, Valuation
from rentalars.material.filters import search_items
from rentalars.material.models import ARCHIVED_STATUSES, AssetKind, MaterialItem
from rentalars.material.sale_models import SaleFromStock

#: The largest amount a cost field holds (``Decimal(10, 2)``).
MAX_COST = Decimal("99999999.99")

#: The largest ID a filter takes: a bigger number fits no row and overflows the integer of the database (R1-10).
MAX_ID = 2**31 - 1

# The filter "kind" of the register.
KIND_ASSETS = ""  #: fixed assets and low-value assets – the Anlagevermögen (the default)
KIND_ALL = "all"
KIND_UNCLASSIFIED = "unclassified"
KIND_CHOICES = (
    (KIND_ASSETS, gettext_lazy("Fixed and low-value assets")),
    (AssetKind.FIXED_ASSET.value, gettext_lazy("Fixed assets")),
    (AssetKind.LOW_VALUE.value, gettext_lazy("Low-value assets (GWG)")),
    (AssetKind.MERCHANDISE.value, gettext_lazy("Merchandise")),
    (KIND_UNCLASSIFIED, gettext_lazy("Not recorded as asset")),
    (KIND_ALL, gettext_lazy("Everything")),
)


def memory_value_on() -> bool:
    """Whether 1 € stays in the books of a fully depreciated fixed asset (Einstellungen → Eingangsrechnungen)."""
    return AssetSettings.load().keep_memory_value


def cost_of(item: MaterialItem) -> Decimal | None:
    """The acquisition cost of an item (net, whole row for bulk material): the recorded one, else the purchase price.

    ``None`` when neither is known (an item bought in a set has no price of its own).
    """
    if item.acquisition_cost_net is not None:
        return item.acquisition_cost_net
    if item.purchase_price is not None:
        return item.purchase_price + (item.ancillary_cost_net or ZERO)
    return None


def value_of(item: MaterialItem, as_of: datetime.date | None = None, *, memory: bool | None = None) -> Valuation:
    """The valuation of an item on a day (default today): cost, written off, book value, the yearly schedule.

    An item without a kind of asset has no book value; ``Valuation.state`` says what is missing.
    """
    return depreciation.valuation(
        item.asset_kind,
        cost_of(item),
        item.purchase_date,
        item.useful_life_months,
        as_of or timezone.localdate(),
        memory=memory_value_on() if memory is None else memory,
    )


def state_label(valued: Valuation) -> str:
    """The state of a valuation in words, for the card and the report."""
    labels = {
        depreciation.UNCLASSIFIED: _("not recorded as asset"),
        depreciation.MERCHANDISE: _("merchandise – not depreciated"),
        depreciation.NO_COST: _("no acquisition cost"),
        depreciation.NO_DATE: _("no date of purchase"),
        depreciation.NO_LIFE: _("no useful life"),
        depreciation.NOT_YET: _("not acquired yet"),
        depreciation.LOW_VALUE_OPEN: _("low-value asset – written off completely at the end of the year"),
        depreciation.WRITTEN_OFF: _("fully depreciated"),
    }
    if valued.state == depreciation.WRITTEN_OFF and valued.kind == depreciation.KIND_LOW_VALUE:
        return str(_("low-value asset – written off completely in the year of acquisition"))
    if valued.state == depreciation.RUNNING:
        return str(_("depreciating – %(months)d months left") % {"months": valued.months_left or 0})
    return str(labels.get(valued.state, ""))


# --- Recording an item as asset ----------------------------------------------------------------------------------


def _resolve_costs(
    item: MaterialItem, ancillary: Decimal | None, acquisition: Decimal | None
) -> tuple[Decimal | None, Decimal | None]:
    """The ancillary cost and the acquisition cost an item gets from what was named (R1-8, R1-9).

    A named acquisition cost is taken as it is – unless it is just the old total sent back with a new ancillary cost
    (the card sends all fields): then the total follows the share. Without an acquisition cost the total is the price
    plus the named ancillary cost; the price of an item that has none is what its acquisition cost says minus its old
    share. Without anything named the recorded cost stays, else price plus share.
    """
    share = item.ancillary_cost_net if ancillary is None else ancillary
    cost = acquisition
    if cost is not None and ancillary is not None and ancillary != item.ancillary_cost_net:
        if cost == item.acquisition_cost_net:
            cost = None
    if cost is not None:
        return share, cost
    base = item.purchase_price
    if base is None and item.acquisition_cost_net is not None:
        base = item.acquisition_cost_net - (item.ancillary_cost_net or ZERO)
    if ancillary is not None and base is not None:
        return share, base + ancillary
    if item.acquisition_cost_net is not None:
        return share, item.acquisition_cost_net
    if item.purchase_price is not None:
        return share, item.purchase_price + (share or ZERO)
    return share, None


def set_asset_data(
    item: MaterialItem,
    *,
    kind: str,
    useful_life_months: int | None = None,
    ancillary_cost_net: Decimal | None = None,
    acquisition_cost_net: Decimal | None = None,
) -> MaterialItem:
    """Record an item as merchandise, low-value or fixed asset, or correct what is recorded; the change log keeps it.

    A fixed asset gets the standard useful life of the settings when none is given; the other kinds have none.
    Without an acquisition cost the purchase price plus the ancillary cost is taken; a changed ancillary cost changes
    the acquisition cost with it. The ancillary cost may be negative (a share of a discount), the acquisition cost not.
    An empty ``kind`` takes the item out of the books again (kind and useful life are cleared); costs named with it are
    kept all the same – they are never ignored.

    Raises:
        ValidationError: An unknown kind, no acquisition cost to go by, an amount outside the field, an acquisition
            cost below 0.
    """
    errors: dict[str, str] = {}
    if kind not in ("", *AssetKind.values):
        raise ValidationError({"asset_kind": _("Choose merchandise, low-value asset (GWG) or fixed asset.")})
    if ancillary_cost_net is not None and not -MAX_COST <= ancillary_cost_net <= MAX_COST:
        errors["ancillary_cost_net"] = _("Enter an amount from %(min)s to %(max)s.") % {
            "min": -MAX_COST,
            "max": MAX_COST,
        }
    if acquisition_cost_net is not None and not ZERO <= acquisition_cost_net <= MAX_COST:
        errors["acquisition_cost_net"] = _("Enter an amount from 0 to %(max)s.") % {"max": MAX_COST}
    if useful_life_months is not None and not 1 <= useful_life_months <= 600:
        errors["useful_life_months"] = _("Enter a useful life from 1 to 600 months.")
    if errors:
        raise ValidationError(errors)
    share, cost = _resolve_costs(item, ancillary_cost_net, acquisition_cost_net)
    if cost is not None and not ZERO <= cost <= MAX_COST:
        raise ValidationError(
            {
                "acquisition_cost_net": _(
                    "The acquisition cost would be %(cost)s: it must be from 0 to %(max)s. A negative ancillary cost "
                    "cannot be larger than the price."
                )
                % {"cost": cost, "max": MAX_COST}
            }
        )
    if kind and cost is None:
        raise ValidationError(
            {"acquisition_cost_net": _("Enter the acquisition cost: the item has no purchase price to go by.")}
        )
    # The limit of a low-value asset is checked, not only proposed.
    from rentalars.material.assets import low_value_problem

    problem = low_value_problem(kind, cost, item.quantity if item.material_model.is_bulk else 1)
    if problem:
        raise ValidationError({"asset_kind": problem})
    if ancillary_cost_net is not None:
        item.ancillary_cost_net = share
    if cost is not None:
        item.acquisition_cost_net = cost
    item.asset_kind = kind
    if kind == AssetKind.FIXED_ASSET:
        item.useful_life_months = useful_life_months or AssetSettings.load().default_useful_life_months
    else:
        item.useful_life_months = None
    item.full_clean()
    item.save()
    return item


# --- The register (Anlagenspiegel) --------------------------------------------------------------------------------


@dataclass
class Filters:
    """What the register is narrowed to; empty values filter nothing."""

    kind: str = KIND_ASSETS
    location: int | None = None
    model: int | None = None
    text: str = ""
    #: The day the values are for; ``None``: today – or the end of ``year``.
    as_of: datetime.date | None = None
    year: int | None = None
    #: Also show items that left the stock (sold, retired, lost) – their value counts only until they left.
    left: bool = False
    #: What could not be read, by parameter – the API answers 400 with it; the page ignores the value.
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def day(self) -> datetime.date:
        """The day the values are for: ``as_of``, else 31 December of ``year``, else today."""
        if self.as_of is not None:
            return self.as_of
        if self.year is not None:
            return datetime.date(self.year, 12, 31)
        return timezone.localdate()


def parse(params: Any) -> Filters:
    """Read the filters from the address (``request.GET``, ``request.query_params``).

    ``kind`` (``fixed_asset``, ``low_value``, ``merchandise``, ``unclassified``, ``all``; none: fixed and low-value
    assets), ``location`` and ``model`` (IDs), ``q``, ``as_of`` (``YYYY-MM-DD``), ``year`` (the balance-sheet date
    of that year, 31 December, unless ``as_of`` is given) and ``left`` (``1``).
    """
    errors: dict[str, str] = {}
    kind = (params.get("kind") or "").strip()
    if kind not in {value for value, _label in KIND_CHOICES}:
        errors["kind"] = _("Unknown value “%(value)s”.") % {"value": kind}
        kind = KIND_ASSETS
    numbers: dict[str, int | None] = {}
    for name in ("location", "model"):
        text = (params.get(name) or "").strip()
        numbers[name] = None
        if text:
            if text.isdigit() and int(text) <= MAX_ID:
                numbers[name] = int(text)
            else:
                errors[name] = _("Enter the ID as a number.")
    as_of = None
    text = (params.get("as_of") or "").strip()
    if text:
        try:
            as_of = datetime.date.fromisoformat(text)
        except ValueError:
            errors["as_of"] = _("Enter the day as YYYY-MM-DD.")
    year = None
    text = (params.get("year") or "").strip()
    if text:
        if text.isdigit() and 1900 <= int(text) <= 2999:
            year = int(text)
        else:
            errors["year"] = _("Enter a year from 1900 to 2999.")
    left = str(params.get("left") or "").strip().lower() in {"1", "true", "yes", "on"}
    return Filters(
        kind=kind,
        location=numbers["location"],
        model=numbers["model"],
        text=" ".join((params.get("q") or "").split())[:100],
        as_of=as_of,
        year=year,
        left=left,
        errors=errors,
    )


def items_of(found: Filters) -> QuerySet[MaterialItem]:
    """The items the filters select – before the values are worked out; in the order of the IDs."""
    items = MaterialItem.objects.select_related("material_model__category", "storage_location", "installed_in")
    if found.kind == KIND_ASSETS:
        items = items.filter(asset_kind__in=[AssetKind.FIXED_ASSET, AssetKind.LOW_VALUE])
    elif found.kind == KIND_UNCLASSIFIED:
        items = items.filter(asset_kind="")
    elif found.kind != KIND_ALL:
        items = items.filter(asset_kind=found.kind)
    if found.location is not None:
        items = items.filter(storage_location_id=found.location)
    if found.model is not None:
        items = items.filter(material_model_id=found.model)
    if found.text:
        items = search_items(items, found.text)
    if not found.left:
        # What left the stock does not belong to the books of the day – but what was sold only after the day did.
        later = SaleFromStock.objects.filter(item=OuterRef("pk"), cancelled_at__isnull=True, sold_on__gt=found.day)
        items = items.filter(~Q(status__in=ARCHIVED_STATUSES) | Exists(later))
    return items.order_by("inventory_number")


@dataclass
class AssetRow:
    """One item of the register with its valuation on the day."""

    item: MaterialItem
    valued: Valuation
    #: When the item was sold (an active sale); ``None``.
    sold_on: datetime.date | None = None
    #: Whether the item counts in the sums: it was in the stock on the day and has a book value.
    counts: bool = False

    @property
    def pk(self) -> int:
        """The key of the item."""
        return self.item.pk

    @property
    def left_stock(self) -> bool:
        """Whether the item had left the stock on the day (sold on or before it, retired or lost)."""
        if not self.item.is_archived:
            return False  # a row of bulk material from which a part was sold is still in the stock
        if self.sold_on is not None:
            return self.sold_on <= (self.valued.as_of or self.sold_on)
        return True


@dataclass
class Sums:
    """The sums of the counted rows."""

    count: int = 0
    cost: Decimal = ZERO
    accumulated: Decimal = ZERO
    this_year: Decimal = ZERO
    opening_value: Decimal = ZERO
    book_value: Decimal = ZERO


@dataclass
class Summary:
    """The sums of a register: all counted rows, by kind, and what could not be counted."""

    total: Sums = field(default_factory=Sums)
    by_kind: dict[str, Sums] = field(default_factory=dict)
    #: Rows without a book value (kind but no cost, date or useful life).
    unvalued: int = 0
    #: Items acquired only after the day – left out of the rows.
    not_yet: int = 0
    #: Rows of items that had left the stock on the day (shown with "also left", not counted).
    left: int = 0


def register(found: Filters) -> tuple[list[AssetRow], Summary]:
    """The rows of the register and its sums, over the whole selection – not one page.

    Items acquired after the day are left out and counted (``Summary.not_yet``). Items that had left the stock count
    for nothing (``Summary.left``) but show when "also left" is chosen. A bulk row stands for all its pieces.
    """
    day = found.day
    memory = memory_value_on()
    items = list(items_of(found))
    sold: dict[int, datetime.date] = dict(
        SaleFromStock.objects.filter(item__in=[item.pk for item in items], cancelled_at__isnull=True)
        .order_by("sold_on")
        .values_list("item_id", "sold_on")
    )
    rows: list[AssetRow] = []
    summary = Summary()
    for item in items:
        valued = value_of(item, day, memory=memory)
        if valued.state == depreciation.NOT_YET:
            summary.not_yet += 1
            continue
        row = AssetRow(item, valued, sold.get(item.pk))
        if row.left_stock:
            summary.left += 1
        elif valued.book_value is None:
            summary.unvalued += 1
        else:
            row.counts = True
            _add(summary.total, valued)
            _add(summary.by_kind.setdefault(valued.kind, Sums()), valued)
        rows.append(row)
    return rows, summary


def _add(sums: Sums, valued: Valuation) -> None:
    """Add one valuation to sums."""
    sums.count += 1
    sums.cost += valued.cost or ZERO
    sums.accumulated += valued.accumulated or ZERO
    sums.this_year += valued.this_year or ZERO
    sums.opening_value += valued.opening_value or ZERO
    sums.book_value += valued.book_value or ZERO
