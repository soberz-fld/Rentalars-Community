# SPDX-License-Identifier: GPL-3.0-or-later
"""Booking in the goods of an incoming invoice: items and quantities of bulk material (DOK-023, DOK-024).

The requirement: items, or quantities of bulk material, can be created from incoming invoices – the goods
positions of an invoice become items of a model (an existing one, or a new one with its category), or – for a model
kept as a quantity – one row with the number of pieces added, exactly as "Kauf einpflegen" makes them
(:func:`rentalars.material.purchases.create_purchase`: consecutive IDs, the supplier, the invoice number and date, the
invoice file as a file of each item).

On top of that every item gets what the books need: its price net in euros, its share of the ancillary costs of the
invoice (:mod:`rentalars.incoming.costing`), their sum as the acquisition cost, the kind of asset – merchandise,
low-value asset (GWG), fixed asset – the useful life of a fixed asset in months, and the position it came from
(``MaterialItem.source_position``). The date of acquisition is ``purchase_date``: the invoice date.

Two steps, as the purchase page has them: :func:`plan` checks everything and says what would be made – nothing is
written –, :func:`book` makes it, all or nothing. A position that was booked in already is named in the plan and is
booked again only on the user's explicit word (``book_again``); the number of pieces defaults to what is left.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import transaction
from django.utils.translation import gettext as _

from rentalars.core.audit import record_event
from rentalars.core.money import money
from rentalars.incoming import services
from rentalars.incoming.costing import Costing, PositionCost, costing_of
from rentalars.incoming.models import IncomingInvoice, InvoicePosition
from rentalars.masterdata.models import StorageLocation
from rentalars.material import assets, purchases
from rentalars.material import services as material_services
from rentalars.material.models import AssetKind, MaterialItem, MaterialModel, TrackingMode


@dataclass
class Entry:
    """What the user decided for one goods position: which model, how many, where to, which serial numbers."""

    position: InvoicePosition
    model: MaterialModel | None = None
    new_model: purchases.NewModel | None = None
    #: How many pieces to make; ``None``: what is left of the position.
    count: int | None = None
    storage_location: StorageLocation | None = None
    serial_numbers: list[str] = field(default_factory=list)
    #: The user confirmed that a position booked in already may be booked once more.
    book_again: bool = False


@dataclass
class PlannedRow:
    """One position as it would be booked in: the figures of the preview."""

    entry: Entry
    cost: PositionCost
    #: How many pieces would be made, and from which piece of the position on (the ones booked before come first).
    count: int
    start: int
    #: Items already made of the position, and pieces (a bulk row counts its quantity).
    booked_rows: int
    booked_pieces: int
    is_bulk: bool
    #: Price net and share of the ancillary costs of these pieces together, in euros.
    price: Decimal
    share: Decimal
    kind: str
    useful_life: int | None
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def position(self) -> InvoicePosition:
        """The position."""
        return self.entry.position

    @property
    def total(self) -> Decimal:
        """Price plus share: the acquisition cost of the pieces together."""
        return self.price + self.share

    @property
    def per_piece(self) -> Decimal | None:
        """The acquisition cost of one piece, on average."""
        return self.total / self.count if self.count else None

    @property
    def kind_label(self) -> str:
        """The kind of asset as a word."""
        return str(AssetKind(self.kind).label) if self.kind else ""

    @property
    def model_name(self) -> str:
        """The model the pieces would belong to."""
        if self.entry.model is not None:
            return self.entry.model.name
        return self.entry.new_model.name if self.entry.new_model is not None else ""

    @property
    def is_new_model(self) -> bool:
        """Whether the model is made together with the items."""
        return self.entry.model is None and self.entry.new_model is not None


@dataclass
class Plan:
    """What booking in would make; ``problems`` stop it, ``warnings`` only inform."""

    invoice: IncomingInvoice
    costing: Costing
    rows: list[PlannedRow]
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Whether it can be booked: nothing stands in the way."""
        return not self.problems and all(not row.problems for row in self.rows) and bool(self.rows)

    @property
    def piece_count(self) -> int:
        """How many pieces would be made."""
        return sum(row.count for row in self.rows)


@dataclass
class Booked:
    """What booking in made."""

    items: list[MaterialItem]
    by_position: dict[int, list[MaterialItem]]
    new_models: list[MaterialModel]
    warnings: list[str]
    status: str
    ids: str


def goods_entries_default(invoice: IncomingInvoice) -> list[Entry]:
    """An entry for every goods position with the model of the proposal (if any) and what is left to book."""
    return [
        Entry(position=position, model=position.material_model)
        for position in invoice.positions.all()
        if position.is_goods
    ]


def _entry_is_bulk(entry: Entry) -> bool:
    """Whether the position becomes a quantity: an existing bulk model, or a new model kept as a quantity."""
    if entry.model is not None:
        return entry.model.is_bulk
    return entry.new_model is not None and entry.new_model.tracking_mode == TrackingMode.BULK


def _chosen_quantities(
    invoice: IncomingInvoice, entries: list[Entry], counts: dict[int, dict[str, int]]
) -> dict[int, Decimal]:
    """The number of pieces chosen at booking in where it is more than the quantity of a position not booked yet.

    A position typed by hand has the quantity 1 – the form asks for the net amount of the position, not for pieces. The
    number of pieces is chosen here; the position then keeps its net amount and the unit price follows
    (:func:`rentalars.incoming.services.split_amount`), so that three items do not cost three times the amount.
    """
    chosen: dict[int, Decimal] = {}
    lock = services.spread_lock(invoice)
    for entry in entries:
        position = entry.position
        if position.invoice_id != invoice.pk or entry.count is None or entry.count < 1:
            continue
        if counts.get(position.pk, {}).get("pieces", 0):
            continue  # booked already: its figures are frozen
        if "quantity" in lock.position_fields(position.position_type):
            continue  # ancillary costs were spread over booked items: the figures they were spread by stay
        if Decimal(entry.count) > position.quantity:  # fewer is a partial booking: the rest stays open
            chosen[position.pk] = Decimal(entry.count)
    return chosen


def plan(invoice: IncomingInvoice, entries: list[Entry], *, rights: Any) -> Plan:
    """Check what the user decided and work out what would be made, without writing anything.

    The checks are those of "Kauf einpflegen" (:func:`rentalars.material.purchases.check_positions`: customer
    material, the most items of one step, the price right) plus: the position belongs to the invoice and is goods, a
    model is named, the figures are complete, nothing is booked twice without ``book_again``, and ancillary costs
    can be spread.
    """
    counts = services.booked_counts(invoice)
    costing = costing_of(invoice, quantities=_chosen_quantities(invoice, entries, counts))
    result = Plan(invoice=invoice, costing=costing, rows=[])
    # Without an entered exchange rate ``costing`` has the problem "enter the exchange rate".
    result.problems.extend(costing.problems)
    if invoice.invoice_date is None:
        # R1-6: the date of the invoice is the date of acquisition; without it the depreciation cannot start.
        result.warnings.append(
            _(
                "The invoice has no date: the items get no date of acquisition, so no book value can be worked out "
                "for them. Enter the invoice date first, or set the date at each item later."
            )
        )
    seen: set[int] = set()
    for entry in entries:
        position = entry.position
        cost = costing.row_of(position)
        if cost is None or position.invoice_id != invoice.pk:
            result.problems.append(
                _("“%(name)s” is not a goods position of this invoice.") % {"name": position.description[:60]}
            )
            continue
        if position.pk in seen:
            result.problems.append(
                _("Position %(number)d is booked in twice in one step.") % {"number": position.place}
            )
            continue
        seen.add(position.pk)
        result.rows.append(_planned_row(entry, cost, counts.get(position.pk, {"rows": 0, "pieces": 0})))
    if not entries:
        result.problems.append(_("Choose at least one position to book in."))
    _check_purchase(result, rights)
    return result


def _planned_row(entry: Entry, cost: PositionCost, booked: dict[str, int]) -> PlannedRow:
    """The row of one entry: pieces, figures, kind and what is wrong with it."""
    position = entry.position
    pieces = cost.pieces
    done = booked["pieces"]
    left = max(pieces - done, 0)
    count = entry.count if entry.count is not None else (left or pieces)
    bulk = _entry_is_bulk(entry)
    start = min(done, pieces)
    row = PlannedRow(
        entry=entry,
        cost=cost,
        count=count,
        start=start,
        booked_rows=booked["rows"],
        booked_pieces=done,
        is_bulk=bulk,
        price=cost.slice_price(start, count) if cost.line is not None else Decimal("0.00"),
        share=cost.slice_share(start, count),
        kind=cost.kind,
        useful_life=cost.useful_life,
        problems=list(cost.problems),
    )
    place = position.place
    if entry.model is None and entry.new_model is None:
        row.problems.append(
            _("Position %(number)d: choose a model, or give the name and category of a new one.") % {"number": place}
        )
    elif entry.model is not None and purchases.is_customer_model(entry.model):
        row.problems.append(
            _("Position %(number)d: “%(model)s” is customer material: bought items cannot join it.")
            % {"number": place, "model": entry.model.name}
        )
    if count < 1:
        row.problems.append(_("Position %(number)d: the number of pieces must be at least 1.") % {"number": place})
    elif not bulk and count > material_services.MAX_ITEMS_PER_BATCH:
        row.problems.append(
            _("Between 1 and %(maximum)d items can be created in one step.")
            % {"maximum": material_services.MAX_ITEMS_PER_BATCH}
        )
    if done and not entry.book_again and (done >= pieces or count > left):
        row.problems.append(
            _(
                "Position %(number)d is booked in already (%(pieces)d of %(total)s pieces, %(rows)d items). Tick “book "
                "again” if you really want to make more."
            )
            % {"number": place, "pieces": done, "total": f"{position.quantity.normalize():f}", "rows": booked["rows"]}
        )
    elif done and count > left:
        row.warnings.append(
            _("Position %(number)d: more pieces than are left (%(left)d); the extra ones get the average cost.")
            % {"number": place, "left": left}
        )
    if row.kind and not position.asset_kind:
        # The limit of the settings only proposes; whether it is merchandise, a low-value or a fixed asset
        # is a decision of the books and has to be confirmed by choosing it (never by leaving the field empty).
        row.problems.append(
            _(
                "Position %(number)d: confirm the kind of asset. By the limit of the settings it would be “%(kind)s” – "
                "choose it (or merchandise, if the pieces are for sale) to book in."
            )
            % {"number": place, "kind": AssetKind(row.kind).label}
        )
    problem = assets.low_value_problem(row.kind, row.per_piece)
    if problem:
        row.problems.append(f"{_('Position %(number)d') % {'number': place}}: {problem}")
    if row.kind and row.kind == AssetKind.FIXED_ASSET and row.useful_life is None:
        row.problems.append(_("Position %(number)d: a fixed asset needs a useful life.") % {"number": place})
    if not bulk and entry.serial_numbers:
        try:
            material_services.check_serial_numbers(entry.serial_numbers, count)
        except ValidationError as error:
            row.problems.extend(
                f"{_('Position %(number)d') % {'number': place}}: {message}" for message in error.messages
            )
    return row


def _check_purchase(result: Plan, rights: Any) -> None:
    """The rules of the purchase (``check_positions``) for the rows that would be made; messages go to the plan."""
    rows = [row for row in result.rows if not row.problems]
    if not rows:
        return
    try:
        purchases.check_positions([_purchase_position(row) for row in rows], rights=rights)
    except ValidationError as error:
        result.problems.extend(message for messages in error.message_dict.values() for message in messages)
    result.warnings.extend(warning for row in result.rows for warning in row.warnings)
    result.warnings.extend(purchases.serial_warnings([_purchase_position(row) for row in rows]))


def _item_values(row: PlannedRow, price: Decimal, share: Decimal) -> dict[str, Any]:
    """The fields of one new item beyond the common ones: price, share, acquisition cost, kind, life, source."""
    return {
        "purchase_price": price,
        "ancillary_cost_net": share,
        "acquisition_cost_net": price + share,
        "asset_kind": row.kind,
        "useful_life_months": row.useful_life,
        "source_position": row.position,
        # R1-2: the pieces this row stands for when booked; building in and selling lower the quantity later.
        "source_quantity": row.count if row.is_bulk else 1,
    }


def _purchase_position(row: PlannedRow) -> purchases.Position:
    """The row as a position of :func:`rentalars.material.purchases.create_purchase`."""
    entry = row.entry
    if row.is_bulk:
        item_fields = [_item_values(row, row.price, row.share)]
    else:
        item_fields = [
            _item_values(row, price, share)
            for price, share in zip(
                row.cost.piece_price(row.start, row.count), row.cost.piece_share(row.start, row.count), strict=True
            )
        ]
    return purchases.Position(
        model=entry.model,
        new_model=entry.new_model,
        count=row.count,
        unit_price=money(row.price / row.count) if row.count else None,
        serial_numbers=[] if row.is_bulk else entry.serial_numbers,
        storage_location=entry.storage_location,
        supplier_article_number=entry.position.article_number,
        item_fields=item_fields,
    )


@transaction.atomic
def book(invoice: IncomingInvoice, entries: list[Entry], *, rights: Any, user: Any = None) -> Booked:
    """Make the items of the entries, all or nothing; the invoice file is attached to each of them.

    Raises:
        ValidationError: The plan has problems (:func:`plan`); nothing is made then.
    """
    invoice = IncomingInvoice.objects.select_for_update().get(pk=invoice.pk)
    checked = plan(invoice, entries, rights=rights)
    if not checked.ok:
        raise ValidationError(checked.problems or [message for row in checked.rows for message in row.problems])
    # The number of pieces chosen here is kept at the position, the unit price follows from its net amount.
    chosen = _chosen_quantities(invoice, entries, services.booked_counts(invoice))
    for row in checked.rows:
        if row.position.pk in chosen:
            # The position keeps the new quantity only if its amount divides into a unit price of four places; else
            # it stays as it is (the plan worked with the exact amount, the items have their prices).
            quantity, unit = services.split_amount(row.position.line_net, chosen[row.position.pk])
            if quantity == chosen[row.position.pk] and unit is not None:
                stored = InvoicePosition.objects.get(pk=row.position.pk)
                stored.quantity, stored.unit_price_net = quantity, unit
                stored.save(update_fields=["quantity", "unit_price_net"])
    head = purchases.Head(
        supplier_name=invoice.supplier_label,
        invoice_number=invoice.invoice_number,
        invoice_date=invoice.invoice_date,
    )
    with invoice.file.open("rb") as handle:
        stored = File(handle, name=invoice.original_name)
        purchase = purchases.create_purchase(
            head, [_purchase_position(row) for row in checked.rows], rights=rights, user=user, invoice=stored
        )
    by_position: dict[int, list[MaterialItem]] = {}
    for row, items in zip(checked.rows, purchase.by_position, strict=True):
        by_position[row.position.pk] = items
        model = items[0].material_model
        if row.position.material_model_id != model.pk:
            row.position.material_model = model
            row.position.save(update_fields=["material_model"])
    if purchase.supplier is not None and invoice.supplier_id != purchase.supplier.pk:
        invoice.supplier = purchase.supplier
        invoice.supplier_name = purchase.supplier.name
        invoice.save(update_fields=["supplier", "supplier_name"])
    services.mark_booked_in_when_complete(invoice)
    record_event(invoice, "incoming_invoice.booked", {"items": purchase.id_list})
    return Booked(
        items=purchase.items,
        by_position=by_position,
        new_models=purchase.new_models,
        warnings=[*checked.warnings, *purchase.warnings][:10],
        status=IncomingInvoice.objects.get(pk=invoice.pk).status,
        ids=purchase.id_list,
    )
