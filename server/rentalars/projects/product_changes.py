# SPDX-License-Identifier: GPL-3.0-or-later
"""Changes of a product that its lines in projects that are not fully confirmed yet have not taken over (PRJ-072).

A line copies name, unit, tax rate, billing mode and price from its product when it is created and keeps them
when the product changes later (PRJ-015): what was quoted stays quoted. For a project that is not fully confirmed yet –
an inquiry, an option, or "Confirmed – details open" – the change is usually wanted, though.
Every project page says so, the planning lists old and new values and takes
them over, and the people of the project are told (``notifications``, kind ``product_change``).

What counts as a change?
    Every line remembers what it took over from its product: the price in ``list_price``, name,
    unit, tax rate and billing mode in ``product_seen``. A part of a line is outdated when the
    product has another value than the one the line remembers.

Set by hand
    A value the planner changed on the line itself – a special price, an own title – differs from the one the
    line remembers. "Take over everything that is not set by hand" leaves such lines alone; the planner decides
    line by line, either taking over the product's value or keeping the own one. Keeping notes the product's
    value as seen, so that the hint goes away until the product changes again. Where a line has no memory of a
    part (older lines that differed from their product when the update ran) it is not known whether
    the product changed or the line was edited; that counts as set by hand, as with ``list_price`` before.

Rights
    Prices are only looked at – and only taken over – with the price right (AUT-019). Everything else is shown to
    whoever reads the planning and taken over by who may edit the project.

Not looked at: lines without product, text lines, subrentals that only cover a shortage (PRJ-055), the billing mode
of sold lines and percentage surcharges.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.projects.models import CrewLine, MaterialLine, Project
from rentalars.projects.price_updates import (
    CHANGE_NOTICE_STATUSES,
    OldPrice,
    apply_new_price,
    find_old_prices,
    keep_own_price,
    shows_price_hint,
)
from rentalars.projects.services import defaults_from_product, ensure_editable

__all__ = [
    "FIELD_LABELS",
    "ChangeResult",
    "FieldChange",
    "LineChange",
    "changes_of_product",
    "count_changes",
    "find_changes",
    "product_changes",
    "shows_price_hint",
    "take_over_changes",
]

#: The parts of a material line (besides the price) that follow the product, in the order they are listed.
FIELD_LABELS = {
    "name": gettext_lazy("Name"),
    "unit": gettext_lazy("Unit"),
    "tax_rate": gettext_lazy("Tax rate"),
    "billing_mode": gettext_lazy("Billing mode"),
    #: A percentage surcharge: the percentage is its price, so it follows the price right.
    "surcharge_percent": gettext_lazy("Surcharge in percent"),
}


@dataclass
class FieldChange:
    """One part of a line (not the price) whose product has another value now."""

    field: str
    #: What the line has, as text.
    old: str
    #: What the product has today, as text.
    new: str
    #: The line differs from what it took over (or does not know what it took over).
    by_hand: bool

    @property
    def label(self) -> str:
        """The name of the part, in the language of the reader."""
        return str(FIELD_LABELS[self.field])


@dataclass
class LineChange:
    """A line whose product changed since the line took it over (PRJ-072)."""

    line: MaterialLine | CrewLine
    fields: list[FieldChange] = field(default_factory=list)
    price: OldPrice | None = None

    @property
    def is_crew(self) -> bool:
        """Whether this is a crew line (only its price follows the service product)."""
        return isinstance(self.line, CrewLine)

    @property
    def key(self) -> str:
        """Names the line in forms and API calls: ``m12`` for material line 12, ``c5`` for crew line 5."""
        return f"{'c' if self.is_crew else 'm'}{self.line.pk}"

    @property
    def title(self) -> str:
        """The title of the line."""
        return self.line.title

    @property
    def article_number(self) -> str:
        """The article number of the product."""
        product = self.line.service_product if self.is_crew else self.line.product
        return product.article_number if product is not None else ""

    @property
    def set_by_hand(self) -> bool:
        """Whether a part of the line was set by hand (or it is not known whether it was)."""
        return any(part.by_hand for part in self.fields) or (self.price is not None and self.price.set_by_hand)

    @property
    def field_names(self) -> list[str]:
        """The parts besides the price that changed, e.g. ``["name", "unit"]``."""
        return [part.field for part in self.fields]


def _same(name: str, first: Any, second: Any) -> bool:
    """Whether two values of a part are the same; percentages are compared as numbers (stored as text)."""
    if name == "surcharge_percent":
        return (Decimal(str(first)) if first is not None else None) == (
            Decimal(str(second)) if second is not None else None
        )
    return bool(first == second)


def _field_values(line: MaterialLine, *, with_prices: bool) -> dict[str, tuple[Any, Any]]:
    """For each part that follows the product: (value of the line, value of the product).

    The ids of unit and tax rate are compared; their texts are only fetched for a part that changed.
    """
    product = line.product
    values: dict[str, tuple[Any, Any]] = {
        "name": (line.title, product.name),
        "unit": (line.unit_id, product.unit_id),
        "tax_rate": (line.tax_rate_id, product.tax_rate_id),
    }
    if not line.is_sale and not line.is_percent_surcharge:
        values["billing_mode"] = (line.billing_mode, product.billing_mode)
    if with_prices and line.is_percent_surcharge:
        values["surcharge_percent"] = (line.surcharge_percent, product.surcharge_percent)
    return values


def _line_text(name: str, line: MaterialLine, which: str) -> str:
    """The text of a value; units and tax rates are looked up now (only for parts that changed)."""
    from rentalars.products.models import BillingMode

    if name == "unit":
        unit = line.unit if which == "line" else line.product.unit
        return str(unit) if unit is not None else "–"
    if name == "tax_rate":
        return str(line.tax_rate if which == "line" else line.product.tax_rate)
    if name == "name":
        return line.title if which == "line" else line.product.name
    if name == "surcharge_percent":
        value = line.surcharge_percent if which == "line" else line.product.surcharge_percent
        return f"{Decimal(str(value)).normalize():f} %" if value is not None else "–"
    value = line.billing_mode if which == "line" else line.product.billing_mode
    return str(BillingMode(value).label) if value in BillingMode.values else str(value)


def _field_changes(line: MaterialLine, *, with_prices: bool) -> list[FieldChange]:
    """The parts of a material line (not the price) that differ from the state of its product."""
    seen = line.product_seen if isinstance(line.product_seen, dict) else {}
    found: list[FieldChange] = []
    for name, (own, current) in _field_values(line, with_prices=with_prices).items():
        if _same(name, own, current):
            continue  # the line has what the product has (e.g. the same new name typed by hand)
        if name in seen:
            remembered = seen[name]
            if _same(name, remembered, current):
                continue
            by_hand = not _same(name, own, remembered)
        else:
            by_hand = True
        found.append(
            FieldChange(
                field=name,
                old=_line_text(name, line, "line"),
                new=_line_text(name, line, "product"),
                by_hand=by_hand,
            )
        )
    return found


def _looked_at(line: MaterialLine) -> bool:
    """Whether the line follows a product at all."""
    return line.product_id is not None and not line.is_text and not line.is_covering_subrental


def find_changes(
    material_lines: Iterable[MaterialLine], crew_lines: Iterable[CrewLine] = (), *, with_prices: bool = True
) -> list[LineChange]:
    """Pick out the lines whose product changed since they took it over.

    Args:
        material_lines: Material lines with their products loaded.
        crew_lines: Crew lines with their service products loaded; only their price follows the product.
        with_prices: Whether prices are looked at (the caller has the price right).

    Returns:
        The lines with something to take over, material lines first, each in the order given.
    """
    material = [line for line in material_lines if _looked_at(line)]
    prices: dict[str, OldPrice] = {}
    if with_prices:
        for old in find_old_prices(material, crew_lines):
            prices[old.key] = old
    found: list[LineChange] = []
    for line in material:
        parts = _field_changes(line, with_prices=with_prices)
        price = prices.pop(f"m{line.pk}", None)
        if parts or price is not None:
            found.append(LineChange(line=line, fields=parts, price=price))
    # The rest are crew lines (find_old_prices only knows lines it was given).
    found.extend(LineChange(line=old.line, price=old) for old in prices.values() if old.is_crew)
    return found


def _lines_of(project: Project) -> tuple[Iterable[MaterialLine], Iterable[CrewLine]]:
    material = project.material_lines.select_related(
        "product", "product__unit", "product__tax_rate", "unit", "tax_rate"
    ).order_by("group__position", "position", "id")
    crew = project.crew_lines.select_related("service_product").order_by("start", "position", "id")
    return material, crew


def product_changes(project: Project, rights: Rights | None = None) -> list[LineChange]:
    """The lines of a project with changes of their products to take over (PRJ-072).

    Args:
        project: The project; changes are listed for every project, ``shows_price_hint`` tells whether the
            pages point them out.
        rights: The rights of the reader; prices are only looked at with the price right. ``None``: no prices.
    """
    material, crew = _lines_of(project)
    return find_changes(material, crew, with_prices=rights is not None and rights.has(SpecialRight.PRICES))


def count_changes(project: Project, rights: Rights | None = None) -> int:
    """How many lines a project page points out – 0 for a project that is confirmed (a quick exit)."""
    if project.status not in CHANGE_NOTICE_STATUSES:
        return 0
    return len(product_changes(project, rights))


def changes_of_product(
    product: Any, rights: Rights | None = None, *, with_prices: bool | None = None
) -> dict[Project, list[LineChange]]:
    """The not yet confirmed projects with lines of this product that have not taken its changes over.

    Args:
        product: The product (a rental, sale or service product).
        rights: The rights of the reader; prices are only looked at with the price right.
        with_prices: Overrides ``rights``: ``True`` looks at prices whatever the rights (to count, not to show).

    Returns:
        Project → its changed lines of this product, projects in the order of their start.
    """
    if with_prices is None:
        with_prices = rights is not None and rights.has(SpecialRight.PRICES)
    material = list(
        MaterialLine.objects.filter(product=product, project__status__in=CHANGE_NOTICE_STATUSES)
        .select_related("project", "product", "product__unit", "product__tax_rate", "unit", "tax_rate")
        .order_by("project__start", "project_id", "position", "id")
    )
    crew = (
        list(
            CrewLine.objects.filter(service_product=product, project__status__in=CHANGE_NOTICE_STATUSES)
            .select_related("project", "service_product")
            .order_by("project__start", "project_id", "start", "id")
        )
        if with_prices
        else []
    )
    result: dict[Project, list[LineChange]] = {}
    for change in find_changes(material, crew, with_prices=with_prices):
        result.setdefault(change.line.project, []).append(change)
    return result


@dataclass
class ChangeResult:
    """What :func:`take_over_changes` did."""

    taken_over: int = 0
    kept: int = 0


def _take_over_fields(line: MaterialLine, change: LineChange) -> None:
    """Give the line the product's values for the parts that changed; ``product_seen`` follows. Does not save."""
    product = line.product
    seen = dict(line.product_seen) if isinstance(line.product_seen, dict) else {}
    for part in change.fields:
        if part.field == "name":
            line.title = product.name
            seen["name"] = product.name
        elif part.field == "unit":
            line.unit = product.unit
            seen["unit"] = product.unit_id
        elif part.field == "tax_rate":
            line.tax_rate = product.tax_rate
            seen["tax_rate"] = product.tax_rate_id
        elif part.field == "billing_mode":
            seen["billing_mode"] = product.billing_mode
            try:
                values = defaults_from_product(product, is_sale=line.is_sale)
            except ValidationError:
                continue  # e.g. the product has no rental price any more: the line keeps what it has - and stops asking
            for name in ("billing_mode", "scale_version", "quantity_is_estimate"):
                setattr(line, name, values[name])
        elif part.field == "surcharge_percent":
            line.surcharge_percent = product.surcharge_percent
            seen["surcharge_percent"] = str(product.surcharge_percent)
    line.product_seen = seen


def _keep_fields(line: MaterialLine, change: LineChange) -> None:
    """Note the product's values as seen and leave the line as it is. Does not save."""
    product = line.product
    current = {
        "name": product.name,
        "unit": product.unit_id,
        "tax_rate": product.tax_rate_id,
        "billing_mode": product.billing_mode,
        "surcharge_percent": str(product.surcharge_percent),
    }
    seen = dict(line.product_seen) if isinstance(line.product_seen, dict) else {}
    for part in change.fields:
        seen[part.field] = current[part.field]
    line.product_seen = seen


@transaction.atomic
def take_over_changes(
    project: Project,
    *,
    rights: Rights,
    keys: Iterable[str] = (),
    automatic: bool = False,
    everything: bool = False,
    keep: Iterable[str] = (),
    only_product: Any = None,
) -> ChangeResult:
    """Bring lines up to date with their products, or keep them knowingly (PRJ-072).

    Taking over gives a line the product's name, unit, tax rate, billing mode and – with the price right – price of
    today; the discount, quantity, period and note of the line stay. Keeping notes the product's values as seen and
    leaves the line as it is, so that the hint is gone until the product changes again.

    Args:
        project: The project; a confirmed one is refused (PRJ-015) – before, the API took the changes over
            there as well and overwrote the prices that were agreed.
        rights: The rights of the caller. Without the price right the prices are left out: they are neither
            taken over nor kept, and so still show for who has that right.
        keys: The lines to take over, by :attr:`LineChange.key`.
        automatic: Take over every line without a part set by hand.
        everything: Take over every changed line.
        keep: The lines whose own values stay, by key.
        only_product: Look only at the lines of this product (the product page takes its changes over in many
            projects at once).

    Returns:
        How many lines were taken over and kept. Lines without a change (any more) are passed over silently:
        pressing a button twice does no harm.

    Raises:
        ValidationError: The project is closed or confirmed, or a line is named to be taken over and kept at once.
    """
    ensure_editable(project)
    if not shows_price_hint(project):
        raise ValidationError(_("This project is confirmed; its lines keep the values that were agreed."))
    take, kept_keys = set(keys), set(keep)
    if take & kept_keys:
        raise ValidationError(_("A line cannot take over the new values and keep its own at the same time."))
    result = ChangeResult()
    for change in product_changes(project, rights):
        line = change.line
        if only_product is not None:
            own_product_id = line.service_product_id if change.is_crew else line.product_id
            if own_product_id != only_product.pk:
                continue
        if change.key in kept_keys:
            if change.price is not None:
                keep_own_price(change.price)
            if not change.is_crew:
                _keep_fields(line, change)
            line.save()
            result.kept += 1
        elif everything or change.key in take or (automatic and not change.set_by_hand):
            if change.price is not None:
                apply_new_price(change.price)
            if not change.is_crew:
                _take_over_fields(line, change)
            line.save()
            result.taken_over += 1
    return result
