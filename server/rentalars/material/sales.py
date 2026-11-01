# SPDX-License-Identifier: GPL-3.0-or-later
"""Used sale from stock: an item – or a quantity of bulk material – leaves the stock for a price (MAT-087).

The requirement: used sale from stock as well – decided together with the book value ("Mit Restbuchwert"): the sale shows the
book value on the day of the sale and the gain or loss against it (Veräußerungsgewinn/-verlust); no DATEV export.

The way
-------
1. :func:`preview` works out what the sale would be – book value, gain or loss, and what stops or should give pause –
   without changing anything.
2. :func:`sell` does it, all or nothing: the item gets the status "sold" with the existing status mechanics
   (``material.services.set_status`` – so the rules of archiving apply: nothing may be installed in it), or, for a
   part of a bulk row, the quantity and the cost of the row are reduced by that part. A record
   (:class:`~rentalars.material.sale_models.SaleFromStock`) keeps the sale with the book value as it was, and an event
   is written to the history of the item (without amounts: the history is read by everyone who reads the material).
3. :func:`cancel` reverses a sale (Storno): the item gets its former status back (or the part is put back into the
   row); the record stays, marked as reversed with who, when and why.

What stops a sale (``problems``)
    The item has left the stock already (sold, lost), is in use, is installed in another item or holds items or bulk
    material itself, is chosen, packed or out for a project (an open allocation), the day lies in the future or before
    the purchase, the quantity does not fit (for bulk material: more than is free – what projects have out comes back
    to the row and is not free, R1-13), the price is below 0, or the buyer is missing.
What asks for a confirmation (``warnings``)
    The item is wished for by a line of a project that is not finished, is booked as a vehicle in one (R1-14), or is
    blocked for a coming period.
What is only said (``notes``)
    The item is no asset in the books (or lacks cost, date or useful life): its book value is set to 0 €.

The book value of a bulk row is that of the whole row at the sale day, taken in proportion to the pieces sold.

Rights are those of the register (``rentalars.incoming.access``): purchase prices and write access to the material;
the pages and the API check them.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, QuerySet, Sum
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from rentalars.core.audit import record_event
from rentalars.core.i18n import local_pattern
from rentalars.core.money import money, percentage_of
from rentalars.customers.models import Contact, Customer
from rentalars.masterdata.models import TaxRate
from rentalars.material import book_values, depreciation, installations, services
from rentalars.material.depreciation import ZERO, scale
from rentalars.material.installed_models import InstalledQuantity
from rentalars.material.models import ARCHIVED_STATUSES, ItemStatus, MaterialItem
from rentalars.material.sale_models import BASIS_CALCULATED, BASIS_UNKNOWN, SaleFromStock

MAX_AMOUNT = Decimal("9999999999.99")


def pieces_of(item: MaterialItem) -> int:
    """How many pieces the row stands for: 1 for an item; for bulk material the free quantity plus what is built in."""
    if not item.material_model.is_bulk:
        return 1
    built_in = InstalledQuantity.objects.filter(material=item).aggregate(total=Sum("quantity"))["total"] or 0
    return item.quantity + built_in


@dataclass
class Preview:
    """What a sale would be; nothing is changed by looking at it."""

    item: MaterialItem
    quantity: int
    sold_on: datetime.date | None
    net_price: Decimal | None
    tax_percent: Decimal
    #: The pieces of the row; the sale is complete when ``quantity`` equals it.
    pieces: int = 1
    valued: depreciation.Valuation | None = None
    cost: Decimal | None = None
    accumulated: Decimal | None = None
    book_value: Decimal = ZERO
    basis: str = BASIS_CALCULATED
    gain_loss: Decimal | None = None
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Whether nothing stops the sale."""
        return not self.problems

    @property
    def complete(self) -> bool:
        """Whether the whole row leaves the stock (always for an item)."""
        return self.quantity == self.pieces

    @property
    def tax_amount(self) -> Decimal | None:
        """The tax on the price."""
        return percentage_of(self.net_price, self.tax_percent) if self.net_price is not None else None

    @property
    def gross_price(self) -> Decimal | None:
        """The price with tax."""
        return self.net_price + self.tax_amount if self.net_price is not None and self.tax_amount is not None else None

    @property
    def is_gain(self) -> bool:
        """Whether the sale makes a gain (or breaks even)."""
        return self.gain_loss is not None and self.gain_loss >= 0


def tax_percent_of(tax_rate: TaxRate | None) -> Decimal:
    """The percentage of a tax rate; the default tax rate when none is given, 0 when there is none at all."""
    chosen = tax_rate or TaxRate.get_default()
    return chosen.rate if chosen is not None else Decimal("0")


# --- What stops a sale ---------------------------------------------------------------------------------------------


def problems_of(item: MaterialItem, quantity: int, sold_on: datetime.date | None) -> list[str]:
    """What stops the sale of this item (see the module docstring)."""
    found: list[str] = []
    if item.status in (ItemStatus.SOLD, ItemStatus.LOST):
        found.append(
            _("%(id)s has already left the stock (%(status)s).")
            % {"id": item.display_id, "status": item.get_status_display()}
        )
        return found
    if item.status == ItemStatus.IN_USE:
        found.append(_("%(id)s is in use. Set it to another status first.") % {"id": item.display_id})
    bulk = item.material_model.is_bulk
    if bulk:
        # What projects have out comes back to the row, so it is not free to sell.
        free = installations.free_quantity(item)
        if quantity < 1 or quantity > free:
            found.append(
                _("Enter a quantity from 1 to %(free)s – so many pieces of %(id)s are free.")
                % {"free": free, "id": item.display_id}
            )
    elif quantity != 1:
        found.append(_("An item is sold one at a time: the quantity is 1."))
    if item.installed_in_id is not None:
        found.append(
            _("%(id)s is installed in %(container)s. Take it out first.")
            % {"id": item.display_id, "container": item.installed_in.display_id}
        )
    if not bulk and (item.contents.exists() or item.installed_quantities.exists()):
        found.append(
            _("Other items or bulk material are installed in %(id)s. Take them out first.") % {"id": item.display_id}
        )
    found.extend(_allocation_problems(item))
    if sold_on is not None:
        if sold_on > timezone.localdate():
            found.append(_("The day of the sale lies in the future."))
        elif item.purchase_date is not None and sold_on < item.purchase_date:
            found.append(
                _("The day of the sale lies before the purchase (%(date)s).") % {"date": item.purchase_date_text}
            )
    return found


def _allocation_problems(item: MaterialItem) -> list[str]:
    """Open allocations: the item is chosen or packed for a project, or out with one."""
    from rentalars.packing.models import Allocation

    found = []
    open_ones = Allocation.objects.filter(item=item, returned_at__isnull=True).select_related(
        "entry__packlist__project"
    )
    for allocation in open_ones:
        project = allocation.entry.packlist.project
        text = (
            _("%(id)s is chosen or packed for project %(project)s.")
            if allocation.issued_at is None
            else _("%(id)s is out with project %(project)s.")
        )
        found.append(text % {"id": item.display_id, "project": f"{project.number} {project.name}"})
    return found


def warnings_of(item: MaterialItem) -> list[str]:
    """What should give pause: wished for by a project that is not finished, blocked for a coming period."""
    from django.db.models import Q

    from rentalars.projects.models import FINISHED_STATUSES, MaterialLine, VehicleLine

    found = []
    wishing = (
        MaterialLine.objects.filter(Q(preferred_item=item) | Q(further_preferred_items=item))
        .exclude(project__status__in=FINISHED_STATUSES)
        .select_related("project")
        .distinct()
    )
    projects = sorted({f"{line.project.number} {line.project.name}" for line in wishing})
    if projects:
        found.append(
            _("%(id)s is wished for by the planning of: %(projects)s.")
            % {"id": item.display_id, "projects": ", ".join(projects)}
        )
    # A vehicle booked under "Logistik" of a project that is not finished (deleting it is refused).
    booked = (
        VehicleLine.objects.filter(item=item)
        .exclude(project__status__in=FINISHED_STATUSES)
        .select_related("project")
        .distinct()
    )
    booked_in = sorted({f"{line.project.number} {line.project.name}" for line in booked})
    if booked_in:
        found.append(
            _("%(id)s is booked as a vehicle in: %(projects)s.")
            % {"id": item.display_id, "projects": ", ".join(booked_in)}
        )
    coming = item.blocks.filter(end__gt=timezone.now()).count()
    if coming:
        found.append(_("%(id)s has blocked periods that have not ended yet.") % {"id": item.display_id})
    return found


# --- Preview and sale ----------------------------------------------------------------------------------------------


def preview(
    item: MaterialItem,
    *,
    quantity: int = 1,
    sold_on: datetime.date | None = None,
    net_price: Decimal | None = None,
    tax_rate: TaxRate | None = None,
) -> Preview:
    """What the sale of this item (or of ``quantity`` pieces of a bulk row) on a day for a price would be.

    The book value is the one of the day of the sale; the gain or loss is the price minus the book value.
    Everything that stops the sale is in ``problems``; the preview is made even then, as far as it goes.
    """
    pieces = pieces_of(item)
    result = Preview(
        item=item, quantity=quantity, sold_on=sold_on, net_price=net_price, tax_percent=tax_percent_of(tax_rate),
        pieces=pieces,
    )  # fmt: skip
    result.problems = problems_of(item, quantity, sold_on)
    if net_price is not None and not ZERO <= net_price <= MAX_AMOUNT:
        result.problems.append(_("Enter a price from 0 to %(max)s.") % {"max": MAX_AMOUNT})
    if net_price is None:
        result.problems.append(_("Enter the price (net)."))
    if sold_on is None:
        result.problems.append(_("Enter the day of the sale."))
        return result
    result.warnings = warnings_of(item)
    valued = book_values.value_of(item, sold_on)
    result.valued = valued
    part = quantity if 1 <= quantity <= pieces else pieces
    if valued.book_value is None:
        result.basis = BASIS_UNKNOWN
        result.book_value = ZERO
        result.cost = scale(book_values.cost_of(item), part, pieces) if book_values.cost_of(item) is not None else None
        result.notes.append(
            _("The book value is not known (%(reason)s): it is set to 0 €, so the whole price is a gain.")
            % {"reason": book_values.state_label(valued)}
        )
    else:
        result.cost = scale(valued.cost or ZERO, part, pieces)
        result.accumulated = scale(valued.accumulated or ZERO, part, pieces)
        result.book_value = scale(valued.book_value, part, pieces)
    if net_price is not None:
        result.gain_loss = money(net_price) - result.book_value
    return result


def resolve_buyer(customer: Customer | None, contact: Contact | None, name: str) -> tuple[Customer | None, str]:
    """The customer and the name of the buyer: a customer or contact chosen, or a name typed (kept as written).

    Raises:
        ValidationError: A contact of another customer, an anonymised customer, no name at all or a name over 200.
    """
    name = " ".join((name or "").split())
    if contact is not None:
        if customer is not None and contact.customer_id != customer.pk:
            raise ValidationError({"contact": _("This contact belongs to another customer.")})
        customer = contact.customer
    if customer is not None and customer.is_anonymised:
        raise ValidationError({"customer": _("This customer was anonymised and cannot buy.")})
    if customer is not None and not customer.is_active:
        raise ValidationError({"customer": _("This customer is not active and cannot buy.")})
    if not name:
        if contact is not None:
            name = f"{contact.name} ({contact.customer.name})"
        elif customer is not None:
            name = customer.name
    if not name:
        raise ValidationError({"buyer_name": _("Say who buys: choose a customer or type a name.")})
    if len(name) > 200:
        raise ValidationError({"buyer_name": _("The name of the buyer can have 200 characters at most.")})
    return customer, name


@transaction.atomic
def sell(
    item: MaterialItem,
    *,
    sold_on: datetime.date,
    net_price: Decimal,
    quantity: int = 1,
    tax_rate: TaxRate | None = None,
    customer: Customer | None = None,
    contact: Contact | None = None,
    buyer_name: str = "",
    note: str = "",
    user: Any = None,
    accept_warnings: bool = False,
) -> SaleFromStock:
    """Sell an item (or a quantity of bulk material) out of the stock; all or nothing.

    Raises:
        ValidationError: Something stops the sale (the messages of :func:`preview`), the warnings are not accepted
            (code ``needs_confirmation``), or the buyer is missing.
    """
    customer, buyer = resolve_buyer(customer, contact, buyer_name)
    row = MaterialItem.objects.select_for_update().select_related("material_model", "installed_in").get(pk=item.pk)
    plan = preview(row, quantity=quantity, sold_on=sold_on, net_price=net_price, tax_rate=tax_rate)
    if plan.problems:
        raise ValidationError(plan.problems)
    if plan.warnings and not accept_warnings:
        raise ValidationError(
            [
                ValidationError(text, code="needs_confirmation")
                for text in (*plan.warnings, _("Confirm that you want to sell it anyway."))
            ]
        )
    sale = SaleFromStock(
        item=row,
        quantity=quantity,
        sold_on=sold_on,
        customer=customer,
        contact=contact,
        buyer_name=buyer,
        net_price=money(net_price),
        tax_rate=tax_rate or TaxRate.get_default(),
        tax_percent=plan.tax_percent,
        note=(note or "").strip(),
        asset_kind=row.asset_kind,
        cost=plan.cost,
        accumulated_depreciation=plan.accumulated,
        book_value=plan.book_value,
        book_value_basis=plan.basis,
        gain_loss=plan.gain_loss,
        previous_status=row.status,
        previous_reason=row.status_reason,
        row_quantity_before=row.quantity,
        item_left=plan.complete,
        sold_by=user if getattr(user, "pk", None) else None,
    )
    if plan.complete:
        services.set_status(
            row,
            ItemStatus.SOLD,
            # No buyer here – the reason is read by everyone who reads the material.
            reason=_("Sold on %(date)s") % {"date": sold_on.strftime(local_pattern("%d.%m.%Y"))},
        )
    else:
        _reduce_row(row, sale, plan)
    sale.full_clean(exclude=["item"])
    sale.save()
    record_event(row, "item.sold_from_stock", {"date": sold_on.isoformat(), "quantity": quantity})
    item.refresh_from_db()
    return sale


def _reduce_row(row: MaterialItem, sale: SaleFromStock, plan: Preview) -> None:
    """A part of a bulk row is sold: fewer pieces, and the cost of the pieces leaves with them.

    The acquisition cost of the part is the price part plus the ancillary part when the row's cost is price plus
    share (R1-7): rounded one by one they could differ by a cent. The ancillary cost may be negative
    (a share of a discount, R1-8): it is not held at 0.
    """
    row.quantity -= plan.quantity
    parts: dict[str, Decimal | None] = {}
    consistent = (
        row.purchase_price is not None
        and row.ancillary_cost_net is not None
        and row.acquisition_cost_net == row.purchase_price + row.ancillary_cost_net
    )
    for name in ("purchase_price", "ancillary_cost_net"):
        value = getattr(row, name)
        if value is None:
            parts[name] = None
            continue
        part = scale(value, plan.quantity, plan.pieces)
        parts[name] = part
        setattr(row, name, value - part if name == "ancillary_cost_net" else max(value - part, ZERO))
    cost = row.acquisition_cost_net
    if cost is None:
        parts["acquisition_cost_net"] = None
    else:
        if consistent:
            part = (parts["purchase_price"] or ZERO) + (parts["ancillary_cost_net"] or ZERO)
        else:
            part = scale(cost, plan.quantity, plan.pieces)
        parts["acquisition_cost_net"] = part
        row.acquisition_cost_net = max(cost - part, ZERO)
    sale.price_part = parts["purchase_price"]
    sale.ancillary_part = parts["ancillary_cost_net"]
    sale.cost = parts["acquisition_cost_net"] if parts["acquisition_cost_net"] is not None else sale.cost
    row.full_clean()
    row.save()


@transaction.atomic
def cancel(sale: SaleFromStock, *, reason: str, user: Any = None) -> SaleFromStock:
    """Reverse a sale (Storno): the item is in the stock again, the record stays, marked as reversed.

    A sold item gets the status it had before; a part of a bulk row is put back into the row with its cost. The
    reason is required.

    Raises:
        ValidationError: No reason; the sale is reversed already; the item was changed since (its status is no longer
            "sold", or the bulk row left the stock).
    """
    reason = " ".join((reason or "").split())
    if not reason:
        raise ValidationError({"reason": _("Say why the sale is reversed.")})
    sale = SaleFromStock.objects.select_for_update().select_related("item__material_model").get(pk=sale.pk)
    if sale.is_cancelled:
        raise ValidationError(_("This sale was reversed already."))
    issued = invoice_of(sale)
    if issued is not None:
        # Reversing the sale alone would leave an invoice for goods that were never sold.
        raise ValidationError(
            _(
                "The invoice %(number)s was made for this sale. Cancel the invoice first (Accounting → Outgoing "
                "documents), then reverse the sale."
            )
            % {"number": issued.number}
        )
    draft = open_invoice_draft(sale)
    if draft is not None:
        from rentalars.documents import free

        free.delete_draft(draft)  # a draft for a sale that is reversed is of no use
        SaleFromStock.objects.filter(pk=sale.pk).update(invoice_draft_id=None)
    row = MaterialItem.objects.select_for_update().select_related("material_model").get(pk=sale.item_id)
    if sale.item_left:
        if row.status != ItemStatus.SOLD:
            raise ValidationError(
                _("%(id)s is not “sold” any more (%(status)s). Set the status to what it should be instead.")
                % {"id": row.display_id, "status": row.get_status_display()}
            )
        row.by_import = sale.previous_status == ItemStatus.IMPORT_ERROR  # it was flagged before the sale: back to that
        services.set_status(
            row,
            sale.previous_status,
            reason=sale.previous_reason or (_("Sale reversed") if sale.previous_status == ItemStatus.DEFECTIVE else ""),
        )
    else:
        if row.status in ARCHIVED_STATUSES:
            raise ValidationError(
                _("%(id)s has left the stock (%(status)s): the sale cannot be reversed.")
                % {"id": row.display_id, "status": row.get_status_display()}
            )
        row.quantity += sale.quantity
        for name, part in (
            ("purchase_price", sale.price_part),
            ("ancillary_cost_net", sale.ancillary_part),
            ("acquisition_cost_net", sale.cost),
        ):
            if part is not None and getattr(row, name) is not None:
                setattr(row, name, getattr(row, name) + part)
        row.full_clean()
        row.save()
    sale.cancelled_at = timezone.now()
    sale.cancelled_by = user if getattr(user, "pk", None) else None
    sale.cancel_reason = reason[:250]
    sale.save()
    record_event(row, "item.sale_reversed", {"date": sale.sold_on.isoformat()})
    return sale


def buyer_label(sale: SaleFromStock) -> str:
    """The buyer as shown: the name kept with the sale; the name of the customer once he was anonymised."""
    if sale.customer_id is not None and sale.customer.is_anonymised:
        return sale.customer.name
    return sale.buyer_name


def _sold_reasons(day: datetime.date, buyer: str) -> list[tuple[str, str]]:
    """The reason of the status "sold" as older versions wrote it (with the buyer) and as it is written now, per language.

    Older versions wrote the date in the German pattern in every language, newer ones in the pattern of the language;
    both are looked for (the second must not make the first unfindable).
    """
    found = []
    for code, _name in settings.LANGUAGES:
        with translation.override(code):
            for pattern in dict.fromkeys(["%d.%m.%Y", local_pattern("%d.%m.%Y")]):
                date_text = day.strftime(pattern)
                found.append(
                    (
                        _("Sold on %(date)s to %(buyer)s") % {"date": date_text, "buyer": buyer},
                        _("Sold on %(date)s") % {"date": date_text},
                    )
                )
    return found


def forget_customer(customer: Customer) -> int:
    """Erase the name of a customer from the sales he bought in (GDPR, with ``anonymise_customer``).

    The sales stay – they are bookkeeping records –, the buyer is the anonymised customer; the change log of the
    sales loses the old name as well. Returns the number of sales.

    Older versions wrote the buyer into the history of the item (the events "sold" and "reversed" and the reason of the
    status "sold"; newer versions do not). Those places are found through the sales of this customer
    and changed where they hold exactly what was written then – the buyer field of the event, the whole reason – and
    nowhere else: no text search over the log, so a short name cannot damage somebody else's text.
    """
    from django.contrib.contenttypes.models import ContentType

    from rentalars.core.models import AuditAction, AuditLogEntry

    sold = SaleFromStock.objects.filter(customer=customer)
    made = list(sold.values_list("pk", "item_id", "sold_on", "buyer_name"))
    if not made:
        return 0
    ids = [str(pk) for pk, _item, _day, _name in made]
    item_ids = sorted({item_id for _pk, item_id, _day, _name in made})
    names = {name for _pk, _item, _day, name in made if name}
    sold.update(buyer_name=customer.name, contact=None)
    for entry in AuditLogEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(SaleFromStock), object_id__in=ids
    ):
        changes = entry.changes if isinstance(entry.changes, dict) else {}
        changes.pop("buyer_name", None)
        entry.changes = changes
        entry.object_repr = customer.name
        entry.save(update_fields=["changes", "object_repr"])
    legacy = {reason: neutral for _pk, _item, day, name in made for reason, neutral in _sold_reasons(day, name) if name}
    for entry in AuditLogEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(MaterialItem), object_id__in=[str(pk) for pk in item_ids]
    ):
        changes = entry.changes if isinstance(entry.changes, dict) else {}
        if entry.action == AuditAction.EVENT:
            if entry.event in ("item.sold_from_stock", "item.sale_reversed") and changes.get("buyer") in names:
                changes["buyer"] = customer.name
                entry.changes = changes
                entry.save(update_fields=["changes"])
            continue
        reason = changes.get("status_reason")
        if isinstance(reason, list) and any(value in legacy for value in reason):
            changes["status_reason"] = [legacy.get(value, value) for value in reason]
            entry.changes = changes
            entry.save(update_fields=["changes"])
    for item in MaterialItem.objects.filter(pk__in=item_ids, status=ItemStatus.SOLD, status_reason__in=list(legacy)):
        MaterialItem.objects.filter(pk=item.pk).update(status_reason=legacy[item.status_reason])
    return len(ids)


def invoice_draft(sale: SaleFromStock, *, user: Any = None) -> Any:
    """The draft of an outgoing invoice for a sale to a customer: one line with the price and the tax rate of the sale.

    "Rechnung dazu erstellen" – the draft is made in Buchhaltung → Ausgangsbelege like any other (``documents.free``);
    the person checks it and issues it there. The draft is not linked to the sale: it is a document of the customer.

    Raises:
        ValidationError: The sale was reversed, the buyer is no customer of the master data, or the customer cannot get a
            document.
    """
    from rentalars.core.i18n import for_documents, local_pattern
    from rentalars.documents import free
    from rentalars.documents.models import DocumentKind

    if sale.is_cancelled:
        raise ValidationError(_("This sale was reversed. No invoice is made for it."))
    if sale.customer_id is None:
        raise ValidationError(
            _(
                "The buyer is not a customer of the master data. Create the customer first, or make the invoice in "
                "Accounting → Outgoing documents."
            )
        )
    item = sale.item
    with transaction.atomic():
        sale = SaleFromStock.objects.select_for_update().get(pk=sale.pk)
        # One invoice for a sale. An open draft is the answer to "make an invoice" again; an invoice that
        # stands (not cancelled) is a reason to refuse – a second one would bill the sale twice.
        existing = open_invoice_draft(sale)
        if existing is not None:
            return existing
        issued = invoice_of(sale)
        if issued is not None:
            raise ValidationError(
                _(
                    "The invoice %(number)s was made for this sale already. Cancel it in Accounting → Outgoing "
                    "documents first if a new one is needed."
                )
                % {"number": issued.number}
            )
        draft = free.create_draft(sale.customer, DocumentKind.INVOICE, user=user, contact=sale.contact)
        with for_documents():
            title = _("Used equipment: %(name)s (%(id)s)") % {"name": item.material_model.name, "id": item.display_id}
            day = sale.sold_on.strftime(local_pattern("%d.%m.%Y"))
            note = _("Sold from stock on %(date)s.") % {"date": day}
            if sale.quantity > 1:
                note = f"{sale.quantity} × {item.material_model.name}. {note}"
        free.add_line(draft, title=title, note=note, unit_price=sale.net_price, tax_rate=sale.tax_rate)
        SaleFromStock.objects.filter(pk=sale.pk).update(invoice_draft_id=draft.pk, document=None)
    return draft


def open_invoice_draft(sale: SaleFromStock) -> Any:
    """The draft of the invoice of this sale, if it is still a draft; ``None`` if there is none (or it was thrown away)."""
    from rentalars.documents.models import DocumentDraft

    if sale.invoice_draft_id is None:
        return None
    return DocumentDraft.objects.filter(pk=sale.invoice_draft_id).first()


def invoice_of(sale: SaleFromStock) -> Any:
    """The invoice issued for this sale if it stands, ``None`` if there is none or it was cancelled."""
    document = sale.document
    if document is None or document.is_cancelled:
        return None
    return document


def link_issued_invoice(draft_id: int, document: Any) -> None:
    """The draft of a sale was issued – the invoice takes its place at the sale (called by ``documents.free.issue``)."""
    SaleFromStock.objects.filter(invoice_draft_id=draft_id).update(invoice_draft_id=None, document=document)


# --- The list of sales ---------------------------------------------------------------------------------------------


@dataclass
class Filters:
    """What the list of sales is narrowed to; empty values filter nothing."""

    year: int | None = None
    since: datetime.date | None = None
    until: datetime.date | None = None
    text: str = ""
    #: Also the reversed sales (they never count in the sums).
    reversed: bool = False
    errors: dict[str, str] = field(default_factory=dict)

    def apply(self, queryset: QuerySet[SaleFromStock]) -> QuerySet[SaleFromStock]:
        """Narrow the sales."""
        if self.year is not None:
            queryset = queryset.filter(sold_on__year=self.year)
        if self.since is not None:
            queryset = queryset.filter(sold_on__gte=self.since)
        if self.until is not None:
            queryset = queryset.filter(sold_on__lte=self.until)
        if self.text:
            from django.db.models import Q

            queryset = queryset.filter(
                Q(buyer_name__icontains=self.text)
                | Q(note__icontains=self.text)
                | Q(item__material_model__name__icontains=self.text)
                | Q(item__serial_number__icontains=self.text)
                | (Q(item__inventory_number=int(self.text)) if self.text.isdigit() else Q(pk__in=[]))
            )
        if not self.reversed:
            queryset = queryset.filter(cancelled_at__isnull=True)
        return queryset


def parse_filters(params: Any) -> Filters:
    """Read the filters from the address: ``year``, ``since`` and ``until`` (``YYYY-MM-DD``), ``q``, ``reversed`` (1)."""
    errors: dict[str, str] = {}
    year = None
    text = (params.get("year") or "").strip()
    if text:
        if text.isdigit() and 1900 <= int(text) <= 2999:
            year = int(text)
        else:
            errors["year"] = _("Enter a year from 1900 to 2999.")
    days: dict[str, datetime.date | None] = {}
    for name in ("since", "until"):
        value = (params.get(name) or "").strip()
        days[name] = None
        if value:
            try:
                days[name] = datetime.date.fromisoformat(value)
            except ValueError:
                errors[name] = _("Enter the day as YYYY-MM-DD.")
    flag = str(params.get("reversed") or "").strip().lower() in {"1", "true", "yes", "on"}
    return Filters(
        year=year,
        since=days["since"],
        until=days["until"],
        text=" ".join((params.get("q") or "").split())[:100],
        reversed=flag,
        errors=errors,
    )


def sales() -> QuerySet[SaleFromStock]:
    """Every sale with what a row shows, in no particular order."""
    return SaleFromStock.objects.select_related(
        "item__material_model", "customer", "tax_rate", "sold_by", "cancelled_by"
    )


@dataclass
class YearSums:
    """Count and sums of the (not reversed) sales of a year."""

    year: int
    count: int = 0
    net: Decimal = ZERO
    book_value: Decimal = ZERO
    gain: Decimal = ZERO
    loss: Decimal = ZERO

    @property
    def result(self) -> Decimal:
        """Gains minus losses."""
        return self.gain + self.loss


def sums_by_year(queryset: QuerySet[SaleFromStock]) -> list[YearSums]:
    """Per year: the number of sales, the net prices, the book values and the gains and losses, newest year first.

    Reversed sales do not count. Gains and losses are summed per sale, not netted before: ``result`` is their sum.
    """
    by_year: dict[int, YearSums] = {}
    for sold_on, net, book, gain in queryset.filter(cancelled_at__isnull=True).values_list(
        "sold_on", "net_price", "book_value", "gain_loss"
    ):
        sums = by_year.setdefault(sold_on.year, YearSums(sold_on.year))
        sums.count += 1
        sums.net += net
        sums.book_value += book
        if gain >= 0:
            sums.gain += gain
        else:
            sums.loss += gain
    return [by_year[year] for year in sorted(by_year, reverse=True)]


def years_with_sales() -> list[int]:
    """The years that have sales, newest first – the choices of the filter."""
    return sorted({day.year for day in SaleFromStock.objects.values_list("sold_on", flat=True)}, reverse=True)


def count_open(queryset: QuerySet[SaleFromStock]) -> int:
    """How many sales of the queryset were not reversed."""
    return queryset.filter(cancelled_at__isnull=True).aggregate(n=Count("pk"))["n"]
