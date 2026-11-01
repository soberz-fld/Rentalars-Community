# SPDX-License-Identifier: GPL-3.0-or-later
"""Buchhaltung → Ausgangsbelege: every document that went to a customer, as one list (DOK-020).

The requirement: a menu entry Buchhaltung, and a table overview of all outgoing documents.

* **Which documents.** Those a customer gets (:data:`CUSTOMER_KINDS`): offers,
  order confirmations, delivery notes, invoices and cancellations. A crew
  disposition goes to the crew, never to a customer, and is left out.
* **Who sees them.** Whoever may see prices (AUT-019) and read every project
  (AUT-017) – as "Auswertungen" (PRJ-115): a list over the documents of all
  customers is nothing for somebody who reads some projects only, and most
  of the documents show prices. For these rights every document opens as on
  the tab "Documents" of its project: priced documents need the price right,
  a monthly invoice read access to every service case it bills
  (``services.may_open_billed``) – both hold for every document here.
* **Without a project.** A document made in Accounting (``documents.free``) belongs to a customer and no
  project: the column "Projekt" says so, the filter "Zuordnung" finds them, the sums count them. They open with
  the same rights as every document here (prices and every project); making one needs write access to every
  project (``free.may_change``).
* **What it shows.** What is stored with the document when it was made
  (DOK-007): number, date, the totals – never calculated again –, the
  recipient as printed; and what is noted later: sent, cancelled, handed to
  Lexware Office (DOK-011), the monthly statement it came from (DOK-016).

The filters (:class:`Filters`) are shared by the page (``outgoing_views``)
and the API (``outgoing_api``); so are the sums (:func:`totals`).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.db.models import Count, Exists, F, OuterRef, Q, QuerySet, Sum
from django.db.models.fields.json import KeyTextTransform, KeyTransform
from django.db.models.functions import Coalesce
from django.utils.text import capfirst
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from rentalars.accounts.rights import Level, Module, SpecialRight
from rentalars.documents.models import BOOKABLE_KINDS, Document, DocumentKind, TransferState

#: The kinds of documents a customer gets, in the order a project needs them. A crew disposition (DOK-004)
#: goes to the crew and is not listed. A new kind is added here only once it is decided that it goes out.
CUSTOMER_KINDS: tuple[str, ...] = (
    DocumentKind.OFFER,
    DocumentKind.ORDER_CONFIRMATION,
    DocumentKind.DELIVERY_NOTE,
    DocumentKind.INVOICE,
    DocumentKind.CANCELLATION,
)

#: The filter "kind": a kind of :data:`CUSTOMER_KINDS`, or one of these groups.
KIND_BOOKABLE = "bookable"
KIND_MONTHLY = "monthly"

#: The filter "state" (and the column "Status").
STATE_NOT_SENT = "not_sent"
STATE_SENT = "sent"
STATE_CANCELLED = "cancelled"
STATE_CANCELLATION = "cancellation"
STATE_NOT_CANCELLED = "not_cancelled"

#: Free outgoing documents: the filter "origin" – made on a project, or in Accounting without one.
ORIGIN_PROJECT = "project"
ORIGIN_FREE = "free"

#: The filter "Lexware Office" (DOK-011).
LEXWARE_DONE = "done"
LEXWARE_FAILED = "failed"
LEXWARE_MISSING = "missing"

#: The words of the states, in the order the column sorts them.
STATE_LABELS = {
    STATE_NOT_SENT: gettext_lazy("not sent"),
    STATE_SENT: gettext_lazy("sent"),
    STATE_CANCELLED: gettext_lazy("cancelled"),
    STATE_CANCELLATION: gettext_lazy("cancellation"),
}

#: The first line of the recipient as stored with the document – the customer as printed (``content.recipient``).
RECIPIENT = KeyTextTransform("0", KeyTransform("recipient", "content"))


def may_see(rights: Any) -> bool:
    """Whether the list of outgoing documents is open to these rights: prices and every project (DOK-020)."""
    return rights.has(SpecialRight.PRICES) and rights.level_everywhere(Module.PROJECTS) >= Level.READ


def may_use_statements(rights: Any) -> bool:
    """Whether the tab "Monatsabrechnung" is open to these rights (DOK-016) – ``statements.may_use``."""
    from rentalars.documents import statements

    return statements.may_use(rights)


def _may_use_legacy(rights: Any) -> bool:
    """Whether the tab "Altprojekte importieren" is open to these rights (``projects.legacy_import.may_use``)."""
    from rentalars.projects import legacy_import

    return legacy_import.may_use(rights)


def _may_see_bank(rights: Any) -> bool:
    """Whether the tab "Bank" is open to these rights (``bank.may_use``)."""
    from rentalars.documents import bank

    return bank.may_use(rights)


def may_see_euer(rights: Any) -> bool:
    """Whether the EÜR, the archive and the audit export are open to these rights (DOK-045, DOK-043, DOK-046).

    They add up the incomes and the expenses of the company: the settings (module "Administration", read) and both
    price rights – the sale prices and the purchase prices.
    """
    return (
        rights.can_read(Module.ADMINISTRATION)
        and rights.has(SpecialRight.PRICES)
        and rights.has(SpecialRight.PURCHASE_PRICES)
    )


def tabs(rights: Any) -> dict[str, bool]:
    """The tabs of "Buchhaltung" a user sees, for ``documents/_accounting_tabs.html`` (DOK-019).

    DOK-055: the tabs that are bookkeeping are left out while Rentalars is not the accounting program.
    """
    from rentalars.documents.bookkeeping import bookkeeping_on
    from rentalars.incoming import access as incoming_access  # The tab "Eingangsrechnungen"

    books = bookkeeping_on()
    return {
        "may_see_outgoing": may_see(rights),
        "may_use_statements": may_use_statements(rights),
        "may_see_incoming": books and incoming_access.may_see(rights),
        "may_capture": books and incoming_access.may_change(rights),  # The tab "Beleg erfassen"
        # The tabs "Anlagenspiegel", "Verkäufe aus Bestand"
        "may_see_assets": books and incoming_access.may_see(rights),
        "may_use_legacy": books and _may_use_legacy(rights),  # The tab "Altprojekte importieren"
        # The tabs "Offene Posten" (customers' invoices, or, with the purchase prices, supplier's) and "EÜR"
        "may_see_open_items": books and (may_see(rights) or incoming_access.may_see(rights)),
        "may_see_euer": books and may_see_euer(rights),
        # DOK-050: the tab "Bank" – bank statements and the matching of payments
        "may_see_bank": books and _may_see_bank(rights),
    }


def documents() -> QuerySet[Document]:
    """Every outgoing document, without crew dispositions; in no particular order."""
    return Document.objects.filter(kind__in=CUSTOMER_KINDS)


def for_list(queryset: QuerySet[Document]) -> QuerySet[Document]:
    """The documents with what a row shows, in a fixed number of queries (NFA-012).

    The stored content is not loaded – it holds every position; only the
    first line of the recipient is read from it, by the database.
    """
    return (
        queryset.select_related("project", "customer", "created_by", "lexware_transfer")
        .defer("content")
        .annotate(
            recipient_name=RECIPIENT,
            cancels_number=Coalesce(
                F("cancels__number"), F("credit_for__number")
            ),  # A partial credit names its invoice
            cancelled_by_number=F("cancelled_by__number"),
        )
    )


def _billed(path: str) -> Exists:
    """Whether the document named by ``path`` bills projects – a monthly invoice of service cases (DOK-016)."""
    through = Document.billed_projects.through
    return Exists(through.objects.filter(document_id=OuterRef(path)))


def monthly_condition() -> Q:
    """Monthly invoices of service cases and their cancellations (DOK-016)."""
    return Q(_billed("pk")) | Q(_billed("cancels_id"))


def state_of(document: Document) -> str:
    """The state of a document as the column "Status" names it."""
    if document.kind == DocumentKind.CANCELLATION:
        return STATE_CANCELLATION
    if document.cancelled_by_id:
        return STATE_CANCELLED
    return STATE_SENT if document.sent_at else STATE_NOT_SENT


def lexware_state(document: Document) -> str:
    """What became of the document in Lexware Office (DOK-011): a ``TransferState``, or "" without handing over."""
    transfer = getattr(document, "lexware_transfer", None)
    return transfer.state if transfer is not None else ""


@dataclass
class Filters:
    """What the list is narrowed to; empty values filter nothing."""

    #: Kinds of :data:`CUSTOMER_KINDS`, or :data:`KIND_BOOKABLE`, :data:`KIND_MONTHLY`.
    kinds: list[str] = field(default_factory=list)
    state: str = ""
    lexware: str = ""
    customer: int | None = None
    project: int | None = None
    #: ``ORIGIN_PROJECT`` – made on a project –, ``ORIGIN_FREE`` – made in Accounting without one; "" both.
    origin: str = ""
    since: datetime.date | None = None
    until: datetime.date | None = None
    #: Searched in the number, title and reference of the document, number and name of the project, the customer's name.
    text: str = ""
    #: What could not be read, by parameter – the API answers 400 with it; the page ignores the value.
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def kind(self) -> str:
        """The one kind chosen on the page; "" for none or several."""
        return self.kinds[0] if len(self.kinds) == 1 else ""

    def apply(self, queryset: QuerySet[Document]) -> QuerySet[Document]:
        """Narrow the documents; conditions on related rows are ``EXISTS``, so no row comes twice."""
        if self.kinds:
            condition = Q()
            for kind in self.kinds:
                if kind == KIND_BOOKABLE:
                    condition |= Q(kind__in=BOOKABLE_KINDS)
                elif kind == KIND_MONTHLY:
                    condition |= monthly_condition()
                else:
                    condition |= Q(kind=kind)
            queryset = queryset.filter(condition)
        if self.state == STATE_SENT:
            queryset = queryset.filter(sent_at__isnull=False)
        elif self.state == STATE_NOT_SENT:
            queryset = queryset.filter(sent_at__isnull=True)
        elif self.state == STATE_CANCELLED:
            queryset = queryset.filter(cancelled_by__isnull=False)
        elif self.state == STATE_NOT_CANCELLED:
            # The documents that stand: no cancelled invoice, and no cancellation – it only cancels.
            queryset = queryset.filter(cancelled_by__isnull=True).exclude(kind=DocumentKind.CANCELLATION)
        if self.lexware == LEXWARE_DONE:
            queryset = queryset.filter(lexware_transfer__state=TransferState.DONE)
        elif self.lexware == LEXWARE_FAILED:
            queryset = queryset.filter(lexware_transfer__state=TransferState.FAILED)
        elif self.lexware == LEXWARE_MISSING:
            # Legacy import: an invoice taken over from an old system was booked there – never "missing".
            queryset = queryset.filter(kind__in=BOOKABLE_KINDS, legacy_item__isnull=True).exclude(
                lexware_transfer__state=TransferState.DONE
            )
        if self.origin == ORIGIN_FREE:
            queryset = queryset.filter(project__isnull=True)
        elif self.origin == ORIGIN_PROJECT:
            queryset = queryset.filter(project__isnull=False)
        if self.customer is not None:
            queryset = queryset.filter(customer_id=self.customer)
        if self.project is not None:
            # DOK-016: a monthly invoice belongs to its first case and bills the others – it counts for each.
            through = Document.billed_projects.through
            billed = through.objects.filter(project_id=self.project)
            queryset = queryset.filter(
                Q(project_id=self.project)
                | Q(Exists(billed.filter(document_id=OuterRef("pk"))))
                | Q(Exists(billed.filter(document_id=OuterRef("cancels_id"))))
            )
        if self.since is not None:
            queryset = queryset.filter(issued_on__gte=self.since)
        if self.until is not None:
            queryset = queryset.filter(issued_on__lte=self.until)
        if self.text:
            queryset = queryset.filter(
                Q(number__icontains=self.text)
                | Q(title__icontains=self.text)
                | Q(reference__icontains=self.text)
                | Q(project__number__icontains=self.text)
                | Q(project__name__icontains=self.text)
                | Q(customer__name__icontains=self.text)
            )
        return queryset


def kind_choices() -> list[tuple[str, str]]:
    """The choices of the filter "kind": the groups first, then every kind."""
    return [
        (KIND_BOOKABLE, _("Invoices and cancellations")),
        (KIND_MONTHLY, _("Monthly invoices of service cases")),
        *((str(kind), capfirst(DocumentKind(kind).label)) for kind in CUSTOMER_KINDS),
    ]


def state_choices() -> list[tuple[str, str]]:
    """The choices of the filter "state"."""
    return [
        (STATE_NOT_SENT, _("not sent")),
        (STATE_SENT, _("sent")),
        (STATE_CANCELLED, _("cancelled")),
        (STATE_NOT_CANCELLED, _("not cancelled")),
    ]


def origin_choices() -> list[tuple[str, str]]:
    """The choices of the filter "origin"."""
    return [(ORIGIN_PROJECT, _("with a project")), (ORIGIN_FREE, _("without a project"))]


def lexware_choices() -> list[tuple[str, str]]:
    """The choices of the filter "Lexware Office" (DOK-011)."""
    return [
        (LEXWARE_DONE, _("handed over")),
        (LEXWARE_FAILED, _("failed")),
        (LEXWARE_MISSING, _("not handed over")),
    ]


def _date(params: Any, name: str, errors: dict[str, str]) -> datetime.date | None:
    """A day from the address (``2027-03-01``); a wrong one is noted in ``errors``."""
    text = (params.get(name) or "").strip()
    if not text:
        return None
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        errors[name] = _("Enter the day as YYYY-MM-DD.")
        return None


def _key(params: Any, name: str, errors: dict[str, str]) -> int | None:
    """An ID from the address; a wrong one is noted in ``errors``."""
    text = (params.get(name) or "").strip()
    if not text:
        return None
    if not text.isdigit():
        errors[name] = _("Enter the ID as a number.")
        return None
    return int(text)


def _choice(params: Any, name: str, choices: list[tuple[str, str]], errors: dict[str, str]) -> str:
    """One of ``choices`` from the address, or ""; an unknown value is noted in ``errors``."""
    value = (params.get(name) or "").strip()
    if value and value not in dict(choices):
        errors[name] = _("Unknown value “%(value)s”.") % {"value": value}
        return ""
    return value


def parse(params: Any) -> Filters:
    """Read the filters from the address (``request.GET``, ``request.query_params``).

    ``kind`` may be given several times or as a comma-separated list
    (``kind=invoice,cancellation``); ``since`` and ``until`` are days of the
    document date, both included.
    """
    errors: dict[str, str] = {}
    known = dict(kind_choices())
    kinds: list[str] = []
    for value in params.getlist("kind") if hasattr(params, "getlist") else [params.get("kind", "")]:
        for kind in (part.strip() for part in (value or "").split(",")):
            if not kind:
                continue
            if kind in known:
                kinds.append(kind)
            else:
                errors["kind"] = _("Unknown value “%(value)s”.") % {"value": kind}
    filters = Filters(
        kinds=list(dict.fromkeys(kinds)),
        state=_choice(params, "state", state_choices(), errors),
        lexware=_choice(params, "lexware", lexware_choices(), errors),
        customer=_key(params, "customer", errors),
        project=_key(params, "project", errors),
        origin=_choice(params, "origin", origin_choices(), errors),
        since=_date(params, "since", errors),
        until=_date(params, "until", errors),
        text=" ".join((params.get("q") or "").split())[:100],
    )
    filters.errors = errors
    return filters


# --- Sums ------------------------------------------------------------------------------------------------


@dataclass
class KindSum:
    """Count and totals of some documents, as stored with them (DOK-007)."""

    label: str
    count: int = 0
    net: Decimal = Decimal("0")
    gross: Decimal = Decimal("0")
    #: Documents with totals – a delivery note has none.
    priced: int = 0
    kind: str = ""

    @property
    def tax(self) -> Decimal:
        """The tax: gross minus net, as the stored totals are made (``documents.content``)."""
        return self.gross - self.net


@dataclass
class Totals:
    """The sums of the filtered documents: per kind, and invoices with their cancellations together."""

    kinds: list[KindSum]
    #: Invoices and cancellations together – what was billed after cancelling; ``None`` without both.
    bookable: KindSum | None
    count: int


def totals(queryset: QuerySet[Document]) -> Totals:
    """Count, net and gross of the documents per kind – one query over the whole filtered list (DOK-020).

    Sums over offers and invoices together would mean nothing; per kind they
    do. Cancellations carry the negated amounts of their invoice, so
    invoices and cancellations together are what stays billed.
    """
    rows = (
        Document.objects.filter(pk__in=queryset.order_by().values("pk"))
        .order_by()
        .values("kind")
        .annotate(
            rows=Count("pk"),
            priced=Count("net_total"),
            net=Sum("net_total"),
            gross=Sum("gross_total"),
        )
    )
    by_kind = {row["kind"]: row for row in rows}
    kinds = []
    for kind in CUSTOMER_KINDS:
        row = by_kind.get(kind)
        if row is None:
            continue
        kinds.append(
            KindSum(
                label=capfirst(DocumentKind(kind).label),
                count=row["rows"],
                net=row["net"] or Decimal("0"),
                gross=row["gross"] or Decimal("0"),
                priced=row["priced"],
                kind=str(kind),
            )
        )
    bookable_rows = [entry for entry in kinds if entry.kind in BOOKABLE_KINDS]
    bookable = None
    if len(bookable_rows) == len(BOOKABLE_KINDS):
        bookable = KindSum(
            label=_("Invoices and cancellations together"),
            count=sum(entry.count for entry in bookable_rows),
            net=sum((entry.net for entry in bookable_rows), Decimal("0")),
            gross=sum((entry.gross for entry in bookable_rows), Decimal("0")),
            priced=sum(entry.priced for entry in bookable_rows),
            kind=KIND_BOOKABLE,
        )
    return Totals(kinds=kinds, bookable=bookable, count=sum(entry.count for entry in kinds))
