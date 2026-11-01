# SPDX-License-Identifier: GPL-3.0-or-later
"""Buchhaltung → Ausgangsbelege as a table: columns to choose, sorting, groups and CSV (DOK-020).

UIX-015, UIX-040, UIX-044: every column sorts by the database and groups – by
the field it shows (kind, dates, project, customer, amounts, Lexware Office,
created by), else in Python by what it shows, for lists of at most
``core.tables.PYTHON_SORT_MAX_ROWS`` rows (status, tax, recipient, monthly
statement, month); a longer list says so. The amounts are those stored with
the document when it was made (DOK-007), never calculated again; the tax is
gross minus net of the stored totals – which is how they were made
(``documents.content``: gross = net + tax).

A page of rows costs a fixed number of queries, however many documents there
are (NFA-012): the related rows come with the documents, the monthly
statements and billed cases of a page in two queries (:func:`_prepare`).
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from django.db.models import Case, DecimalField, ExpressionWrapper, F, IntegerField, OuterRef, Subquery, Value, When
from django.urls import reverse
from django.utils.html import format_html
from django.utils.text import capfirst
from django.utils.translation import gettext, ngettext, pgettext
from django.utils.translation import gettext_lazy as _

from rentalars.core.money import format_money
from rentalars.core.tables import Column, TableDefinition, badge, date_text, grouped_by_day, link
from rentalars.documents import outgoing
from rentalars.documents.models import BOOKABLE_KINDS, Document, DocumentKind, MonthlyStatement, TransferState

#: The kinds in the order of a project (offer first), for sorting by the column "Kind".
KIND_ORDER = Case(
    *(When(kind=kind, then=Value(index)) for index, kind in enumerate(outgoing.CUSTOMER_KINDS)),
    default=Value(len(outgoing.CUSTOMER_KINDS)),
    output_field=IntegerField(),
)

#: The states in the order of :data:`outgoing.STATE_LABELS`, for sorting by the column "Status".
STATE_ORDER = Case(
    When(kind=DocumentKind.CANCELLATION, then=Value(3)),
    When(cancelled_by__isnull=False, then=Value(2)),
    When(sent_at__isnull=False, then=Value(1)),
    default=Value(0),
    output_field=IntegerField(),
)

#: The tax of the stored totals.
TAX = ExpressionWrapper(F("gross_total") - F("net_total"), output_field=DecimalField(max_digits=12, decimal_places=2))

#: The month of the monthly statement an invoice was made of (DOK-016).
STATEMENT_MONTH = Subquery(MonthlyStatement.objects.filter(invoice=OuterRef("pk")).values("month")[:1])

STATE_COLOURS = {
    outgoing.STATE_NOT_SENT: "yellow",
    outgoing.STATE_SENT: "green",
    outgoing.STATE_CANCELLED: "",
    outgoing.STATE_CANCELLATION: "red",
}

LEXWARE_COLOURS = {TransferState.DONE: "green", TransferState.FAILED: "red"}


def _prepare(documents: list[Document]) -> None:
    """Load the monthly statements and the billed cases of the rows in two queries (DOK-016)."""
    if not documents:
        return
    ids = [document.pk for document in documents]
    statements = {
        invoice: (pk, month)
        for invoice, pk, month in MonthlyStatement.objects.filter(invoice_id__in=ids).values_list(
            "invoice_id", "pk", "month"
        )
    }
    sources = {document.pk: document.cancels_id or document.pk for document in documents}
    through = Document.billed_projects.through
    billed = Counter(
        through.objects.filter(document_id__in=set(sources.values())).values_list("document_id", flat=True)
    )
    for document in documents:
        document.statement_of = statements.get(document.pk)
        document.billed_count = billed.get(sources[document.pk], 0)


def _number(document: Document) -> Any:
    """The number, linked to the stored PDF; an invoice's XRechnung after it (DOK-006, DOK-007)."""
    pdf = format_html(
        '<a href="{}" target="_blank" rel="noopener" title="{}">{}</a>',
        reverse("documents:file", args=[document.pk]),
        gettext("Open the PDF"),
        document.number,
    )
    if document.xml_file:
        return format_html(
            '{} <a class="small" href="{}">XRechnung</a>', pdf, reverse("documents:xml", args=[document.pk])
        )
    return pdf


def _kind(document: Document) -> str:
    """The kind as a word: "Rechnung", "Abschlagsrechnung", "Schlussrechnung", "Teilgutschrift"."""
    if document.billing_type:
        return capfirst(document.get_billing_type_display())
    return capfirst(document.get_kind_display())


def _project_text(document: Document) -> str:
    """The project as text: number and name; "without project" for a document made in Accounting."""
    project = document.project
    if project is None:
        return gettext("without project")
    return f"{project.number} {project.name}"


def _project(document: Document) -> Any:
    """The project, linked to its tab "Documents" – of a monthly invoice its first case (DOK-016).

    Free outgoing documents: a document made in Accounting has none; the reference stands instead.
    """
    project = document.project
    if project is None:
        return format_html(
            '{}<div class="muted small">{}</div>',
            link(reverse("documents:free_document", args=[document.pk]), gettext("without project")),
            document.reference,
        )
    return format_html(
        '{}<div class="muted small">{}</div>',
        # The project itself, not its key: the address takes its number without a query (UIX-024, NFA-012).
        link(reverse("documents:list", args=[project]), project.number),
        project.name,
    )


def _customer_name(document: Document) -> str:
    """The customer of the document; internal projects and cases without customer as the project names them."""
    if document.customer_id:
        return document.customer.name
    return document.project.customer_name if document.project_id else ""


def _customer(document: Document) -> Any:
    """The customer with the customer number below."""
    if document.customer_id:
        return format_html('{}<div class="muted small">{}</div>', document.customer.name, document.customer.number)
    return _customer_name(document)


def _money(value: Any) -> str:
    """An amount as ``238,00 €``; nothing for a document without amounts (a delivery note)."""
    return format_money(value) if value is not None else ""


def _tax(document: Document) -> Any:
    """The tax: gross minus net of the stored totals – how they were made; ``None`` without amounts."""
    if document.net_total is None or document.gross_total is None:
        return None
    return document.gross_total - document.net_total


def _state_label(document: Document) -> str:
    """The word of the state, e.g. "gesendet" or "storniert"."""
    return str(outgoing.STATE_LABELS[outgoing.state_of(document)])


def _state(document: Document) -> Any:
    """Sent, not sent, cancelled – with the other document of a cancellation; sent with the day."""
    state = outgoing.state_of(document)
    label = badge(_state_label(document), STATE_COLOURS[state])
    if state == outgoing.STATE_CANCELLATION and document.cancels_number:
        note = gettext("cancels %(number)s") % {"number": document.cancels_number}
    elif state == outgoing.STATE_CANCELLED and document.cancelled_by_number:
        note = pgettext("cancelled", "by %(number)s") % {"number": document.cancelled_by_number}
    elif state == outgoing.STATE_SENT:
        note = date_text(document.sent_at)
    else:
        note = ""
    return format_html('{}<div class="muted small">{}</div>', label, note) if note else label


def _state_text(document: Document) -> str:
    """The state for the CSV file, with the other document of a cancellation."""
    state = outgoing.state_of(document)
    if state == outgoing.STATE_CANCELLATION and document.cancels_number:
        return gettext("cancels %(number)s") % {"number": document.cancels_number}
    if state == outgoing.STATE_CANCELLED and document.cancelled_by_number:
        return f"{_state_label(document)} ({document.cancelled_by_number})"
    return _state_label(document)


def _sent(document: Document) -> Any:
    """When the document was sent, and to whom."""
    if not document.sent_at:
        return ""
    return format_html('{}<div class="muted small">{}</div>', date_text(document.sent_at), document.sent_to)


def _lexware_text(document: Document) -> str:
    """DOK-011: handed over, waiting, failed; nothing for a document the accounting does not get."""
    state = outgoing.lexware_state(document)
    if state:
        return str(TransferState(state).label)
    return gettext("not handed over") if document.kind in BOOKABLE_KINDS else ""


def _lexware(document: Document) -> Any:
    """DOK-011: the state in Lexware Office as a badge, with the moment it was handed over."""
    state = outgoing.lexware_state(document)
    text = _lexware_text(document)
    if not state:
        return format_html('<span class="muted">{}</span>', text) if text else ""
    if state == TransferState.DONE and document.lexware_transfer.transferred_at:
        return format_html(
            '{}<div class="muted small">{}</div>',
            badge(text, LEXWARE_COLOURS[state]),
            date_text(document.lexware_transfer.transferred_at),
        )
    return badge(text, LEXWARE_COLOURS.get(state, "yellow"))


def _statement_text(document: Document) -> str:
    """DOK-016: the month of the statement an invoice was made of; else how many cases a monthly invoice bills."""
    from rentalars.documents.statements import month_label

    found = getattr(document, "statement_of", None)
    if found is not None:
        return month_label(found[1])
    count = getattr(document, "billed_count", 0)
    if count:
        return ngettext(
            "monthly invoice of %(count)s service case", "monthly invoice of %(count)s service cases", count
        ) % {"count": count}
    return ""


def _statement(document: Document) -> Any:
    """The month of the statement, linked to it (DOK-016); else as :func:`_statement_text`."""
    found = getattr(document, "statement_of", None)
    if found is not None:
        return link(reverse("documents:statement", args=[found[0]]), _statement_text(document))
    return _statement_text(document)


def _user(document: Document) -> str:
    """Who made the document."""
    user = document.created_by
    if user is None:
        return ""
    return user.get_full_name() or user.username


OUTGOING_TABLE = TableDefinition(
    "outgoing_documents",
    [
        Column(
            "number",
            _("Number"),
            cell=_number,
            text=lambda document: document.number,
            sort="number",
            css="nowrap",
            fixed=True,
            group="number",
            group_label=lambda document: document.number,
        ),
        Column("kind", _("Kind"), cell=_kind, text=_kind, sort=(KIND_ORDER, "-issued_on"), group="kind"),
        Column(
            "title",
            _("Title"),
            cell=lambda document: document.title,
            sort=("title", "-issued_on"),
            default=False,
            group="title",
        ),
        # Free outgoing documents: the subject line of a document made without a project.
        Column(
            "reference",
            _("Reference"),
            cell=lambda document: document.reference,
            sort=("reference", "-issued_on"),
            default=False,
            group="reference",
        ),
        Column(
            "issued_on",
            _("Date"),
            cell=lambda document: date_text(document.issued_on),
            text=lambda document: document.issued_on,
            sort=("issued_on", "number"),
            css="nowrap",
            group="issued_on",
        ),
        # Grouped by the month in Python: a path of the database would put March of every year together.
        Column(
            "month",
            _("Month"),
            cell=lambda document: _month(document),
            sort=("issued_on", "number"),
            default=False,
            group=lambda document: document.issued_on.replace(day=1),
            group_label=lambda document: _month(document),
        ),
        Column(
            "project",
            _("Project"),
            cell=_project,
            text=_project_text,
            sort=("project__number", "-issued_on"),
            group="project",
            group_label=_project_text,
        ),
        Column(
            "customer",
            _("Customer"),
            cell=_customer,
            text=_customer_name,
            sort=("customer__name", "project__number", "-issued_on"),
            group="customer",
            group_label=_customer_name,
        ),
        # The customer as printed on the document: its first line of the address (DOK-007).
        Column(
            "recipient",
            _("Recipient"),
            cell=lambda document: document.recipient_name or "",
            sort=(outgoing.RECIPIENT, "-issued_on"),
            default=False,
        ),
        Column(
            "net",
            _("Net"),
            cell=lambda document: _money(document.net_total),
            text=lambda document: document.net_total,
            sort=("net_total", "number"),
            css="num nowrap",
            group="net_total",
        ),
        Column(
            "tax",
            _("Tax"),
            cell=lambda document: _money(_tax(document)),
            text=_tax,
            sort=(TAX, "number"),
            css="num nowrap",
        ),
        Column(
            "gross",
            _("Gross"),
            cell=lambda document: _money(document.gross_total),
            text=lambda document: document.gross_total,
            sort=("gross_total", "number"),
            css="num nowrap",
            group="gross_total",
        ),
        Column(
            "due_on",
            _("Due on"),
            cell=lambda document: date_text(document.due_on),
            text=lambda document: document.due_on,
            sort=("due_on", "number"),
            css="nowrap",
            default=False,
            group="due_on",
        ),
        Column(
            "state",
            _("Status"),
            cell=_state,
            text=_state_text,
            sort=(STATE_ORDER, "-issued_on"),
            group=outgoing.state_of,
            group_label=lambda document: badge(_state_label(document), STATE_COLOURS[outgoing.state_of(document)]),
        ),
        Column(
            "sent",
            _("Sent"),
            cell=_sent,
            text=lambda document: document.sent_at,
            sort=("sent_at", "number"),
            css="nowrap",
            default=False,
            **grouped_by_day("sent_at"),
        ),
        Column(
            "lexware",
            _("Lexware Office"),
            cell=_lexware,
            text=_lexware_text,
            sort=("lexware_transfer__state", "-issued_on"),
            default=False,
            group="lexware_transfer__state",
            group_label=_lexware_text,
        ),
        Column(
            "statement",
            _("Monthly statement"),
            cell=_statement,
            text=_statement_text,
            sort=(STATEMENT_MONTH, "-issued_on"),
            default=False,
        ),
        Column(
            "created_by",
            _("Created by"),
            cell=_user,
            sort=("created_by__last_name", "created_by__first_name", "created_by__username", "-issued_on"),
            default=False,
            group="created_by",
        ),
    ],
    default_sort="-issued_on",
    row_css=lambda document: "is-muted" if document.cancelled_by_id else "",
    prepare=_prepare,
)


def _month(document: Document) -> str:
    """The month of the document date: "Februar 2027"."""
    from rentalars.documents.statements import month_label

    return month_label(document.issued_on.replace(day=1))
