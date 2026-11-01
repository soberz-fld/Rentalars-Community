# SPDX-License-Identifier: GPL-3.0-or-later
"""The Einnahmen-Überschuss-Rechnung of a calendar year – prepared, not filed (DOK-045).

The EÜR counts what flowed in and out (§ 11 EStG, *Zufluss/Abfluss*), not what was invoiced:

* **Income** – the payments received on outgoing invoices, split over the tax rates of the invoice (``core.tax_split``), and
  the sales from stock that have no invoice (counted on the day of the sale). A refund is a negative payment.
* **Expenses** – the payments made on incoming invoices (in euros by the exchange rate of the invoice), split over the tax
  accounts of their positions. What is booked in the stock as fixed asset or low-value asset is *not* an expense of the day of
  payment: it comes in as depreciation (AfA) – a low-value asset (GWG) completely in the year of acquisition. The input tax
  is an expense with the payment, whatever was bought.
* **Depreciation** – from the asset data of the items (``material.book_values``): each year its share until the item left;
  with a sale the book value at the sale leaves as an expense (*Restbuchwert*).
* **Turnover tax** is shown apart: collected, input tax, balance. Payments to and from the tax office are recognised by the
  supplier (``Supplier.tax_office``, DOK-052): what is paid to a tax office for turnover tax is no expense, it is set
  against the balance of the turnover tax; income tax and other private taxes are no operating expense either and are shown
  apart. A refund is a negative payment. Trade tax is an expense like any other: its supplier is not marked.
* A **small business** (§ 19 UStG) has no turnover tax; its amounts count gross.
* ``profit`` is the result without turnover tax; ``surplus`` is the figure the EÜR counts for a business with
  turnover tax (turnover tax received is income, input tax and the payments to the tax office are expenses). The rule of
  ten days around the turn of the year (§ 11 (1) sentence 2 EStG, recurring payments) is **not** applied: the notes name
  the payments to a tax office in those days. An asset that is lost or retired depreciates until then and its book value
  leaves as an expense; of a bulk row of which a part was sold, the earlier years keep what the whole row was written off
  (the pieces sold are valued at their own cost until the day of the sale).

This prepares the figures for the tax adviser. It is no tax advice and no filing; the notes of the result say what was
approximated. Every figure traces back to a line (:class:`Entry`), which the CSV file and the audit export give out.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.core.tax_split import ZERO, cents, split
from rentalars.documents import payments as outgoing_payments
from rentalars.documents.content import from_json
from rentalars.documents.models import AccountingSettings, Document, DocumentKind, OutgoingPayment
from rentalars.incoming.models import IncomingInvoice, IncomingPayment, PositionType
from rentalars.material import assets, book_values, depreciation
from rentalars.material.models import AssetKind, ItemStatus, MaterialItem
from rentalars.material.sale_models import SaleFromStock

INCOME = "income"
EXPENSE = "expense"
DEPRECIATION = "depreciation"
DISPOSAL = "disposal"
#: DOK-052: payments to a tax office – not part of the profit.
TAX_VAT = "tax_vat"
TAX_INCOME = "tax_income"

KIND_LABELS = {
    INCOME: _("income"),
    EXPENSE: _("expense"),
    DEPRECIATION: _("depreciation"),
    DISPOSAL: _("book value at sale"),
    TAX_VAT: _("payment to the tax office – turnover tax"),
    TAX_INCOME: _("payment to the tax office – income tax and the like"),
}

#: Years that can be asked for.
FIRST_YEAR = 2000
LAST_YEAR = 2100

_ASSET_KINDS = (AssetKind.FIXED_ASSET.value, AssetKind.LOW_VALUE.value)


@dataclass
class Entry:
    """One line behind the figures: a payment (part), a depreciation, a sale."""

    kind: str
    day: datetime.date | None
    number: str
    party: str
    category: str
    net: Decimal
    tax: Decimal
    rate: Decimal | None = None
    source: str = ""
    source_id: int | None = None
    note: str = ""

    @property
    def gross(self) -> Decimal:
        """Net plus tax."""
        return self.net + self.tax


@dataclass
class Row:
    """A line of the result: income by tax rate, expense by account, depreciation."""

    label: str
    net: Decimal = ZERO
    tax: Decimal = ZERO
    count: int = 0


@dataclass
class Euer:
    """The EÜR of one year."""

    year: int
    small_business: bool
    income: list[Row] = field(default_factory=list)
    expenses: list[Row] = field(default_factory=list)
    depreciation: Row = field(default_factory=lambda: Row(""))
    disposals: Row = field(default_factory=lambda: Row(""))
    #: DOK-052: paid to (negative: refunded by) the tax office; no expense.
    tax_office_vat: Row = field(default_factory=lambda: Row(""))
    tax_office_income: Row = field(default_factory=lambda: Row(""))
    entries: list[Entry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def income_net(self) -> Decimal:
        """Operating income without turnover tax (gross for a small business)."""
        return sum((row.net for row in self.income), ZERO)

    @property
    def expense_net(self) -> Decimal:
        """Operating expenses without input tax, depreciation and the book value of assets sold."""
        return sum((row.net for row in self.expenses), ZERO)

    @property
    def total_expense(self) -> Decimal:
        """Expenses, depreciation and book values at sale."""
        return self.expense_net + self.depreciation.net + self.disposals.net

    @property
    def profit(self) -> Decimal:
        """Income less expenses, depreciation and book values at sale – without turnover tax."""
        return self.income_net - self.total_expense

    @property
    def surplus(self) -> Decimal:
        """The surplus as the EÜR of a business with turnover tax counts it.

        Turnover tax received is income; input tax and what is paid to the tax office for turnover tax are expenses
        (a refund is income). That is the profit without turnover tax plus the turnover tax still owed (or less what is to come back). For
        a small business the amounts count gross and the surplus is the profit.
        """
        return self.profit + self.vat_still_owed

    @property
    def tax_collected(self) -> Decimal:
        """Turnover tax received with the payments."""
        return sum((row.tax for row in self.income), ZERO)

    @property
    def input_tax(self) -> Decimal:
        """Input tax paid with the payments."""
        return sum((row.tax for row in self.expenses), ZERO)

    @property
    def tax_balance(self) -> Decimal:
        """Turnover tax collected less input tax – what the year owes the tax office, before its own payments."""
        return self.tax_collected - self.input_tax

    @property
    def vat_still_owed(self) -> Decimal:
        """The balance of the turnover tax less what was paid to the tax office for it (negative: refund to come).

        A small business (§ 19 UStG) has no turnover tax balance; what it paid to a tax office for turnover tax is shown as
        paid and nothing is "owed" or "to come".
        """
        if self.small_business:
            return ZERO
        return self.tax_balance - self.tax_office_vat.net

    def as_json(self) -> dict[str, Any]:
        """The result for the API."""

        def rows(values: list[Row]) -> list[dict[str, Any]]:
            return [{"label": r.label, "net": str(r.net), "tax": str(r.tax), "count": r.count} for r in values]

        return {
            "year": self.year,
            "small_business": self.small_business,
            "income": rows(self.income),
            "expenses": rows(self.expenses),
            "depreciation": {"net": str(self.depreciation.net), "count": self.depreciation.count},
            "disposals": {"net": str(self.disposals.net), "count": self.disposals.count},
            "income_net": str(self.income_net),
            "expense_net": str(self.expense_net),
            "total_expense": str(self.total_expense),
            "profit": str(self.profit),
            "surplus": str(self.surplus),
            "tax_collected": str(self.tax_collected),
            "input_tax": str(self.input_tax),
            "tax_balance": str(self.tax_balance),
            "tax_office_vat": str(self.tax_office_vat.net),
            "tax_office_income": str(self.tax_office_income.net),
            "vat_still_owed": str(self.vat_still_owed),
            "warnings": list(self.warnings),
            "entry_count": len(self.entries),
        }


def parse_year(value: Any, default: int | None = None) -> int:
    """The year of a request: a number in range, else ``default`` or the current year."""
    try:
        year = int(str(value).strip())
    except (TypeError, ValueError):
        year = 0
    if FIRST_YEAR <= year <= LAST_YEAR:
        return year
    return default or timezone.localdate().year


# --- Income --------------------------------------------------------------------------------------------------------


def _parts_of(doc: Document) -> list[tuple[Decimal | None, Decimal, Decimal]]:
    """Net and tax per rate of one document (the booked taxes; else the totals without a rate)."""
    try:
        taxes = from_json(doc.content).booked_taxes
        parts = [(share.percent, share.net, share.tax) for share in taxes]
    except (KeyError, TypeError, ValueError, AttributeError):
        parts = []
    if not parts and doc.gross_total is not None:
        net = doc.net_total if doc.net_total is not None else doc.gross_total
        parts = [(None, net, doc.gross_total - net)]
    return parts


def _sum_shares(documents: list[Document]) -> list[tuple[Decimal | None, Decimal, Decimal]]:
    shares: dict[Decimal | None, list[Decimal]] = {}
    for doc in documents:
        for percent, net, tax in _parts_of(doc):
            row = shares.setdefault(percent, [ZERO, ZERO])
            row[0] += net
            row[1] += tax
    return [(key, cents(net), cents(tax)) for key, (net, tax) in shares.items()]


def _shares_of(
    document: Document, on: datetime.date | None = None, *, refund: bool = False
) -> list[tuple[Decimal | None, Decimal, Decimal]]:
    """Net and tax per rate that a payment on ``on`` consists of.

    A payment pays what was payable on its day: the invoice with the credit notes and the cancellation issued until then.
    A refund (a negative payment) gives back what the credit notes and the cancellation took off, so it follows their
    rates, not those of the invoice – otherwise a credit note on the 0 % line would be refunded on the 19 % line.
    """
    later = [c for c in document.partial_credits.all() if on is None or c.issued_on <= on]
    cancel = document.cancelled_by
    if cancel is not None and (on is None or cancel.issued_on <= on):
        later.append(cancel)
    if refund and later:
        taken = _sum_shares(later)
        if any(net + tax for _key, net, tax in taken):
            return taken
    result = _sum_shares([document, *later])
    if not any(net + tax for _key, net, tax in result):
        result = _sum_shares([document])
    return result


def _party(document: Document) -> str:
    customer = document.customer
    return str(customer) if customer is not None else ""


def _income_from_payments(result: Euer, year: int) -> None:
    start, end = datetime.date(year, 1, 1), datetime.date(year, 12, 31)
    paid = (
        OutgoingPayment.objects.filter(paid_on__range=(start, end), voided_at__isnull=True)
        .select_related("document__customer", "document__cancelled_by")
        .prefetch_related("document__partial_credits")
        .order_by("paid_on", "id")
    )
    for payment in paid:
        document = payment.document
        parts = split(payment.amount, _shares_of(document, payment.paid_on, refund=payment.amount < 0))
        if not parts:
            result.warnings.append(
                _(
                    "The payment of %(amount)s on invoice %(number)s could not be split over tax rates; it is not counted."
                )
                % {"amount": payment.amount, "number": document.number}
            )
            continue
        for percent, net, tax in parts:
            result.entries.append(
                Entry(
                    INCOME,
                    payment.paid_on,
                    document.number,
                    _party(document),
                    _rate_label(percent),
                    net,
                    tax,
                    percent,
                    "payment",
                    payment.pk,
                )
            )
    # Old invoices that the import knows as paid and that have no payment: counted on the day the import knows.
    legacy = (
        Document.objects.filter(kind=DocumentKind.INVOICE, legacy_item__paid=True, gross_total__isnull=False)
        .select_related("customer", "cancelled_by", "legacy_item")
        .prefetch_related("partial_credits", "payments")
    )
    for document in legacy:
        if any(p.voided_at is None for p in document.payments.all()):
            continue
        day = document.legacy_item.paid_on
        if day is None:
            result.warnings.append(
                _("Invoice %(number)s of the old system is paid, but the day is not known; it is not counted.")
                % {"number": document.number}
            )
            continue
        if not start <= day <= end:
            continue
        amount = outgoing_payments.payable_of(document)
        for percent, net, tax in split(amount, _shares_of(document, day)):
            result.entries.append(
                Entry(
                    INCOME,
                    day,
                    document.number,
                    _party(document),
                    _rate_label(percent),
                    net,
                    tax,
                    percent,
                    "legacy",
                    document.pk,
                    _("paid in the old system"),
                )
            )


def _rate_label(percent: Decimal | None) -> str:
    if percent is None:
        return str(_("tax rate not known"))
    return str(_("%(rate)s %% turnover tax") % {"rate": f"{percent.normalize():f}"})


def _income_from_sales(result: Euer, year: int) -> None:
    sales = (
        SaleFromStock.objects.filter(sold_on__year=year, cancelled_at__isnull=True, document__isnull=True)
        .select_related("item")
        .order_by("sold_on", "id")
    )
    for sale in sales:
        net = cents(sale.net_price)
        tax = cents(net * sale.tax_percent / 100)
        result.entries.append(
            Entry(
                INCOME,
                sale.sold_on,
                f"#{sale.pk}",
                sale.buyer_name,
                _rate_label(sale.tax_percent),
                net,
                tax,
                sale.tax_percent,
                "sale",
                sale.pk,
                _("sale from stock without an invoice"),
            )
        )
    count = sales.count()
    if count:
        result.warnings.append(
            _("%(count)d sales from stock have no invoice; they count on the day of the sale.") % {"count": count}
        )


# --- Expenses ------------------------------------------------------------------------------------------------------


def _asset_cost_by_position(invoice: IncomingInvoice) -> dict[int, Decimal]:
    """Acquisition cost (euros, ancillary share included) of the assets booked in from each position of the invoice."""
    costs: dict[int, Decimal] = {}
    items = MaterialItem.objects.filter(source_position__invoice=invoice, asset_kind__in=_ASSET_KINDS)
    for item in items:
        cost = book_values.cost_of(item) or ZERO
        costs[item.source_position_id] = costs.get(item.source_position_id, ZERO) + cost
    return costs


def _category_of(position: Any) -> str:
    account = position.tax_account
    if account is not None:
        return f"{account.number} {account.name}"
    labels = {
        PositionType.GOODS: _("material without a tax account"),
        PositionType.ANCILLARY: _("ancillary costs without a tax account"),
    }
    return str(labels.get(position.position_type, _("other without a tax account")))


ASSET_KEY = "\0asset"


def _expense_shares(invoice: IncomingInvoice, rate: Decimal) -> list[tuple[str, Decimal, Decimal]]:
    """The invoice in euros as (category, net, tax); what is booked in as asset is one share apart (``ASSET_KEY``)."""
    asset_costs = _asset_cost_by_position(invoice)
    lines: list[tuple[str, Decimal, Decimal, str]] = []  # category, net, tax, "asset" | "ancillary" | "other"
    for position in invoice.positions.all():
        line = position.line_net
        if line is None:
            continue
        net = cents(line * rate)
        tax = cents(net * (position.tax_rate or ZERO) / 100)
        category = _category_of(position)
        if position.pk in asset_costs:
            # only what is booked in is an asset: 2 of 5 pieces booked in leave the other 3 as an expense
            asset_part = min(net, asset_costs[position.pk])
            asset_tax = cents(tax * asset_part / net) if net else tax
            lines.append((category, asset_part, asset_tax, "asset"))
            if net - asset_part or tax - asset_tax:
                lines.append((category, net - asset_part, tax - asset_tax, "other"))
            continue
        part = "ancillary" if position.position_type == PositionType.ANCILLARY else "other"
        lines.append((category, net, tax, part))
    if not lines:
        if invoice.total_net is None or invoice.total_gross is None:
            return []
        net = cents(invoice.total_net * rate)
        return [(str(_("without positions")), net, cents((invoice.total_gross - invoice.total_net) * rate))]
    asset_net = sum((net for _c, net, _t, part in lines if part == "asset"), ZERO)
    asset_tax = sum((tax for _c, _n, tax, part in lines if part == "asset"), ZERO)
    anc_net = sum((net for _c, net, _t, part in lines if part == "ancillary"), ZERO)
    # The ancillary costs that belong to the assets are part of their cost: they leave the expenses.
    moved = ZERO
    if asset_net and anc_net:
        moved = max(min(sum(asset_costs.values(), ZERO) - asset_net, anc_net), ZERO)
    keep = Decimal(1) - (moved / anc_net if anc_net else ZERO)
    rows: dict[str, list[Decimal]] = {}
    for category, net, tax, part in lines:
        if part == "asset":
            continue
        scale = keep if part == "ancillary" else Decimal(1)
        row = rows.setdefault(category, [ZERO, ZERO])
        kept_net, kept_tax = cents(net * scale), cents(tax * scale)
        row[0] += kept_net
        row[1] += kept_tax
        if part == "ancillary":
            asset_net += net - kept_net
            asset_tax += tax - kept_tax
    shares = [(category, net, tax) for category, (net, tax) in rows.items()]
    if asset_net or asset_tax:
        shares.append((ASSET_KEY, asset_net, asset_tax))
    return shares


def _expenses_from_payments(result: Euer, year: int) -> None:
    start, end = datetime.date(year, 1, 1), datetime.date(year, 12, 31)
    paid = (
        IncomingPayment.objects.filter(paid_on__range=(start, end), voided_at__isnull=True)
        .select_related("invoice__supplier")
        .prefetch_related("invoice__positions__tax_account")
        .order_by("paid_on", "id")
    )
    missing_rate = unbooked = 0
    limit = assets.low_value_limit()
    for payment in paid:
        invoice = payment.invoice
        rate = invoice.rate
        if rate is None:
            missing_rate += 1
            continue
        amount = cents(payment.amount * rate)
        supplier = invoice.supplier_label
        office = invoice.supplier.tax_office if invoice.supplier_id else ""
        if office:
            # DOK-052: a payment to the tax office is no expense – turnover tax is set against the balance, the rest is apart.
            kind = TAX_VAT if office == "vat" else TAX_INCOME
            result.entries.append(
                Entry(
                    kind,
                    payment.paid_on,
                    invoice.invoice_number,
                    supplier,
                    str(KIND_LABELS[kind]),
                    amount,
                    ZERO,
                    None,
                    "incoming_payment",
                    payment.pk,
                )
            )
            continue
        shares = _expense_shares(invoice, rate)
        parts = split(amount, shares)
        if not parts:
            result.warnings.append(
                _("The payment of %(amount)s on incoming invoice %(number)s could not be split; it is not counted.")
                % {"amount": payment.amount, "number": invoice.invoice_number or invoice.pk}
            )
            continue
        for position in invoice.positions.all():
            if (
                position.position_type == PositionType.GOODS
                and position.unit_price_net is not None
                and position.unit_price_net * rate > limit
                and not position.items.exists()
            ):
                unbooked += 1
                break
        for category, net, tax in parts:
            if category == ASSET_KEY:
                result.entries.append(
                    Entry(
                        EXPENSE,
                        payment.paid_on,
                        invoice.invoice_number,
                        supplier,
                        str(_("asset – see depreciation")),
                        ZERO,
                        tax,
                        None,
                        "incoming_payment",
                        payment.pk,
                        _("net amount comes in as depreciation"),
                    )
                )
                continue
            result.entries.append(
                Entry(
                    EXPENSE,
                    payment.paid_on,
                    invoice.invoice_number,
                    supplier,
                    category,
                    net,
                    tax,
                    None,
                    "incoming_payment",
                    payment.pk,
                )
            )
    if missing_rate:
        result.warnings.append(
            _("%(count)d payments on invoices in a foreign currency without an exchange rate are not counted.")
            % {"count": missing_rate}
        )
    if unbooked:
        result.warnings.append(
            _(
                "%(count)d paid invoices have material above the limit of a low-value asset that is not booked in the stock; "
                "it counts as an expense now and becomes depreciation once it is booked in."
            )
            % {"count": unbooked}
        )


# --- Depreciation and disposals -----------------------------------------------------------------------------------


def _leaving_dates() -> dict[int, tuple[datetime.date, str]]:
    """The day an asset was lost or retired, from the change log: ``{item id: (day, status)}``.

    Only items that are lost or retired now count; the day is that of the newest change of the status to the one it has.
    Where the log has no such entry (cleared by the retention) the item is missing here and has to be noted by the caller.
    """
    from django.contrib.contenttypes.models import ContentType

    from rentalars.core.models import AuditAction, AuditLogEntry
    from rentalars.material.models import ItemStatus

    items = list(
        MaterialItem.objects.filter(
            asset_kind__in=_ASSET_KINDS, status__in=[ItemStatus.LOST.value, ItemStatus.RETIRED.value]
        )
    )
    if not items:
        return {}
    content_type = ContentType.objects.get_for_model(MaterialItem)
    found: dict[int, tuple[datetime.date, str]] = {}
    entries = AuditLogEntry.objects.filter(
        content_type=content_type, object_id__in=[str(item.pk) for item in items], action=AuditAction.UPDATED
    ).order_by("-timestamp", "-id")
    status_of = {str(item.pk): item.status for item in items}
    for entry in entries.iterator():
        if int(entry.object_id) in found:
            continue
        change = (entry.changes or {}).get("status")
        if isinstance(change, list) and len(change) == 2 and change[1] == status_of[entry.object_id]:
            found[int(entry.object_id)] = (timezone.localtime(entry.timestamp).date(), status_of[entry.object_id])
    return found


def _depreciation(result: Euer, year: int) -> None:
    year_start = datetime.date(year, 1, 1)
    year_end = datetime.date(year, 12, 31)
    memory = book_values.memory_value_on()
    sold: dict[int, datetime.date] = {}
    for item_id, day in (
        SaleFromStock.objects.filter(cancelled_at__isnull=True, item_left=True)
        .order_by("sold_on")
        .values_list("item_id", "sold_on")
    ):
        sold.setdefault(item_id, day)
    # Of a bulk row of which a part was sold, the row keeps the cost of the pieces left only. The years before
    # the sale were written off on the whole row, and the pieces sold are written off at their own cost until the sale.
    parts: dict[int, list[SaleFromStock]] = {}
    for part in SaleFromStock.objects.filter(
        cancelled_at__isnull=True, item_left=False, asset_kind__in=_ASSET_KINDS, cost__isnull=False
    ).order_by("sold_on", "id"):
        parts.setdefault(part.item_id, []).append(part)
    gone = _leaving_dates()
    unvalued = unknown_day = 0
    for item in MaterialItem.objects.filter(asset_kind__in=_ASSET_KINDS).order_by("inventory_number"):
        left = sold.get(item.pk)
        lost = gone.get(item.pk)
        if left is None and lost is not None:
            left = lost[0]
        elif left is None and item.status in (ItemStatus.LOST.value, ItemStatus.RETIRED.value):
            unknown_day += 1
        if left is not None and left < year_start:
            continue
        day = left if left is not None and left <= year_end else year_end
        cost = book_values.cost_of(item)
        if cost is not None:
            cost += sum((p.cost for p in parts.get(item.pk, []) if p.sold_on > year_end), ZERO)
        valued = depreciation.valuation(
            item.asset_kind, cost, item.purchase_date, item.useful_life_months, day, memory=memory
        )
        if valued.state == "not_yet":
            pass
        elif valued.this_year is None:
            unvalued += 1
        else:
            if valued.this_year:
                result.entries.append(
                    Entry(
                        DEPRECIATION,
                        year_end if day == year_end else day,
                        item.inventory_number or str(item.pk),
                        str(item.material_model),
                        str(AssetKind(item.asset_kind).label),
                        cents(valued.this_year),
                        ZERO,
                        None,
                        "item",
                        item.pk,
                    )
                )
            if lost is not None and year_start <= lost[0] <= year_end and valued.book_value:
                # Lost or scrapped: what was not written off yet leaves as an expense on that day.
                result.entries.append(
                    Entry(
                        DISPOSAL,
                        lost[0],
                        item.inventory_number or str(item.pk),
                        str(ItemStatus(lost[1]).label),
                        str(_("book value at loss or retirement")),
                        cents(valued.book_value),
                        ZERO,
                        None,
                        "item",
                        item.pk,
                    )
                )
        for part in parts.get(item.pk, []):
            if not year_start <= part.sold_on <= year_end:
                continue
            valued_part = depreciation.valuation(
                item.asset_kind, part.cost, item.purchase_date, item.useful_life_months, part.sold_on, memory=memory
            )
            if valued_part.this_year:
                result.entries.append(
                    Entry(
                        DEPRECIATION,
                        part.sold_on,
                        item.inventory_number or str(item.pk),
                        str(item.material_model),
                        str(AssetKind(item.asset_kind).label),
                        cents(valued_part.this_year),
                        ZERO,
                        None,
                        "item",
                        item.pk,
                        _("pieces sold from the row: until the day of the sale"),
                    )
                )
    if unvalued:
        result.warnings.append(
            _("%(count)d assets lack cost, date or useful life; they have no depreciation in the figures.")
            % {"count": unvalued}
        )
    if unknown_day:
        result.warnings.append(
            _(
                "%(count)d assets are lost or retired, but the change log does not say when; they keep depreciating "
                "in the figures."
            )
            % {"count": unknown_day}
        )
    for sale in SaleFromStock.objects.filter(
        sold_on__year=year, cancelled_at__isnull=True, asset_kind__in=_ASSET_KINDS
    ).select_related("item"):
        if sale.book_value:
            result.entries.append(
                Entry(
                    DISPOSAL,
                    sale.sold_on,
                    sale.item.inventory_number or str(sale.item_id),
                    sale.buyer_name,
                    str(_("book value at sale")),
                    cents(sale.book_value),
                    ZERO,
                    None,
                    "sale",
                    sale.pk,
                )
            )


# --- The result ------------------------------------------------------------------------------------------------------


def compute(year: int) -> Euer:
    """The EÜR of a calendar year."""
    small = AccountingSettings.load().small_business
    result = Euer(year=year, small_business=small)
    _income_from_payments(result, year)
    _income_from_sales(result, year)
    _expenses_from_payments(result, year)
    _depreciation(result, year)
    income: dict[str, Row] = {}
    expenses: dict[str, Row] = {}
    for entry in result.entries:
        net, tax = (entry.net + entry.tax, ZERO) if small else (entry.net, entry.tax)
        if entry.kind == INCOME:
            row = income.setdefault(entry.category, Row(entry.category))
        elif entry.kind == EXPENSE:
            row = expenses.setdefault(entry.category, Row(entry.category))
        elif entry.kind == TAX_VAT:
            row = result.tax_office_vat
            row.label = str(KIND_LABELS[TAX_VAT])
        elif entry.kind == TAX_INCOME:
            row = result.tax_office_income
            row.label = str(KIND_LABELS[TAX_INCOME])
        elif entry.kind == DEPRECIATION:
            row = result.depreciation
            row.label = str(_("depreciation (AfA, GWG)"))
        else:
            row = result.disposals
            row.label = str(_("book value of assets sold"))
        row.net += net
        row.tax += tax
        row.count += 1
    result.income = sorted(income.values(), key=lambda r: r.label)
    result.expenses = sorted(expenses.values(), key=lambda r: r.label)
    result.tax_office_vat.label = result.tax_office_vat.label or str(KIND_LABELS[TAX_VAT])
    result.tax_office_income.label = result.tax_office_income.label or str(KIND_LABELS[TAX_INCOME])
    if not result.depreciation.label:
        result.depreciation.label = str(_("depreciation (AfA, GWG)"))
    if not result.disposals.label:
        result.disposals.label = str(_("book value of assets sold"))
    if small:
        result.warnings.append(_("Small business: the amounts count gross, without turnover tax and input tax."))
    _ten_day_rule(result, year)
    return result


def _ten_day_rule(result: Euer, year: int) -> None:
    """Name the payments to a tax office around the turn of the year: the rule of ten days is not applied.

    Recurring payments that are due and paid within ten days of the turn of the year belong to the year they are
    for (§ 11 (1) sentence 2 EStG) – a turnover tax prepayment due on 10 January and paid on 8 January counts for the
    old year. Rentalars counts every payment on the day it was made; the tax adviser decides.
    """
    windows = [
        (datetime.date(year, 1, 1), datetime.date(year, 1, 10)),
        (datetime.date(year, 12, 22), datetime.date(year + 1, 1, 10)),
    ]
    found = 0
    for start, end in windows:
        found += (
            IncomingPayment.objects.filter(paid_on__range=(start, end), voided_at__isnull=True)
            .exclude(invoice__supplier__tax_office="")
            .exclude(invoice__supplier__isnull=True)
            .count()
        )
    if found:
        result.warnings.append(
            _(
                "%(count)d payments to a tax office lie within ten days of the turn of the year. The rule of ten days "
                "(§ 11 EStG, recurring payments) is not applied: every payment counts on the day it was made. Ask your tax "
                "adviser whether one belongs to the other year."
            )
            % {"count": found}
        )


def csv_rows(result: Euer) -> list[list[str]]:
    """The lines behind the figures, for the CSV file: kind, day, number, party, category, net, tax, gross, source."""
    rows = [
        [
            str(h)
            for h in (
                _("kind"),
                _("day"),
                _("number"),
                _("party"),
                _("category"),
                _("net"),
                _("tax"),
                _("gross"),
                _("source"),
                _("note"),
            )
        ]
    ]
    for entry in sorted(result.entries, key=lambda e: (e.kind, e.day or datetime.date.min, e.number)):
        rows.append(
            [
                str(KIND_LABELS.get(entry.kind, entry.kind)),
                entry.day.isoformat() if entry.day else "",
                entry.number,
                entry.party,
                entry.category,
                f"{entry.net:.2f}",
                f"{entry.tax:.2f}",
                f"{entry.gross:.2f}",
                f"{entry.source}:{entry.source_id}" if entry.source_id is not None else entry.source,
                entry.note,
            ]
        )
    return rows
