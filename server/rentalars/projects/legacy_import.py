# SPDX-License-Identifier: GPL-3.0-or-later
"""Taking over old projects from their invoices: checks, confirmation, traceability and undo (legacy import; PRJ-130).

The requirement: import of old projects based on invoices – own *outgoing* invoices of past projects, as PDFs from the old system.
The way, which mirrors "Kauf einpflegen" (``material.purchases``, MAT-061/MAT-062):

1. **Upload** (:func:`add_files`): one or several PDFs form a *batch*. Each file is checked (type, size, number of files),
   kept under ``DATA_DIR/legacy-invoices`` and fingerprinted (SHA-256) – a file that was imported before, or that is in
   the upload twice, is marked as a duplicate at once and never read.
2. **Reading** (:func:`start_reading`): a background task reads the text of every PDF and structures it
   (:mod:`rentalars.ai.legacy_invoices` with AI, :mod:`rentalars.projects.legacy_text` by patterns without) into a
   :class:`~rentalars.projects.legacy_draft.Draft`; customer and products are matched against the master data
   (:func:`prepare`). Nothing is created.
3. **Preview and checks** (:func:`check`): the draft is edited on the page; plausibility checks show *warnings* (the sum of
   the positions against the totals, the VAT, the printed amounts against quantity × price …) and *errors* that block
   taking the invoice over (no number, a number that exists, a number inside the live range, an unknown tax rate …).
4. **Confirmation** (:func:`summary`, :func:`confirm`): the page shows exactly what will be created; only then
   :func:`confirm` creates, per project and in one transaction: the customer if the user chose "new", a **closed** project
   with the positions as free lines, and the **historic invoice** (a ``documents.Document`` of the kind invoice with
   number, date, totals and the original PDF). Several invoices can be joined to one project.

What taking over does *not* do (the decisions taken for this feature): it sends no mail, makes no task or notification, reserves no
stock and touches no availability (a closed project reserves nothing), fires no automation and no webhook
(:mod:`rentalars.projects.legacy_quiet`), hands nothing to Lexware Office, takes no number from the live number ranges
(the number of the historic invoice stays as it was; ``NumberRange`` is not touched) and is left out of the DATEV export
unless the export is asked to include it.

Traceability: the record of the invoice (``LegacyImportItem``) names the customer, project and document, the user, the
time and the checksum; the project's notes and history say "Imported from invoice … on … by …"; a customer made by the
import has it in its note. **Undo** (:func:`undo_problems`, :func:`undo`): within :data:`UNDO_DAYS` days, if nothing was
changed since – nothing in the change log after the import, no document, mail, file, time … added to what the import
created – the batch's projects, invoices and customers are removed again.

Browser views and API views both call these functions (API-002).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import re
import secrets
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from rentalars.accounts.rights import Level, Module
from rentalars.core.i18n import local_pattern
from rentalars.core.money import format_money, money
from rentalars.documents import content as builder
from rentalars.projects import legacy_draft as drafts
from rentalars.projects.legacy_draft import Draft, Line
from rentalars.projects.legacy_models import ItemState, LegacyImportBatch, LegacyImportItem
from rentalars.projects.legacy_quiet import quiet

logger = logging.getLogger(__name__)

#: The most PDFs of one upload.
MAX_FILES = 30
#: The largest PDF; an invoice is short (the reading cuts it further, see ``purchases.MAX_PDF_PAGES``).
MAX_FILE_BYTES = 10 * 1024 * 1024
#: The most bytes of one upload together.
MAX_BATCH_BYTES = 120 * 1024 * 1024
#: How long a file that was not taken over is kept for the preview (days).
PENDING_DAYS = 14
#: How long an import can be undone, if nothing was changed since (days).
UNDO_DAYS = 7
#: The prefix of the numbers of imported projects: they must not use up the live project numbers.
PROJECT_PREFIX = "ALT"

_STORED = re.compile(r"^[0-9a-f]{32}\.pdf$")


# --- Rights -----------------------------------------------------------------------------------------------------------


def may_use(rights: Any) -> bool:
    """Whether these rights may open and use "Altprojekte importieren": the rights to make documents of Buchhaltung.

    As the free outgoing documents (``documents.free.may_change``): prices, read access to every project (the list of
    outgoing documents) and write access to every project – old invoices are historic documents of projects.
    """
    from rentalars.documents import outgoing

    return outgoing.may_see(rights) and rights.level_everywhere(Module.PROJECTS) >= Level.WRITE


def may_create_customers(rights: Any) -> bool:
    """Whether new customers may be made by the import: write access to the customers."""
    return rights.level(Module.CUSTOMERS) >= Level.WRITE


def may_see_records(rights: Any) -> bool:
    """Whether the list of imported invoices may be read: whoever may read the outgoing documents."""
    from rentalars.documents import outgoing

    return outgoing.may_see(rights)


# --- Files --------------------------------------------------------------------------------------------------------------


def pending_directory() -> Path:
    """The folder of uploaded invoices that are not taken over yet."""
    directory = Path(settings.DATA_DIR) / "legacy-invoices"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def stored_path(item: LegacyImportItem) -> Path:
    """Where the kept PDF of an item is.

    Raises:
        FileNotFoundError: The name is not one this module made, or the file is gone.
    """
    if not _STORED.match(item.stored_name or ""):
        raise FileNotFoundError(item.stored_name)
    path = pending_directory() / item.stored_name
    if not path.is_file():
        raise FileNotFoundError(item.stored_name)
    return path


def drop_file(item: LegacyImportItem) -> None:
    """Remove the kept PDF of an item (the invoice was taken over, skipped or expired)."""
    if _STORED.match(item.stored_name or ""):
        (pending_directory() / item.stored_name).unlink(missing_ok=True)
    item.stored_name = ""


@dataclass
class Rejection:
    """A file of an upload that was refused, and why."""

    name: str
    reason: str


def _same_file_taken_over(sha256: str) -> LegacyImportItem | Any | None:
    """The record of an invoice with this checksum that was taken over – or a document of Rentalars with this PDF."""
    from rentalars.documents.models import Document

    item = LegacyImportItem.objects.filter(sha256=sha256, state=ItemState.IMPORTED).select_related("document").first()
    if item is not None:
        return item
    return Document.objects.filter(sha256=sha256).first()


def add_files(uploaded: list[Any], *, user: Any) -> tuple[LegacyImportBatch | None, list[Rejection]]:
    """Keep the uploaded PDFs of one go as a batch; refuse what is no PDF, too large or too many.

    A file that is the same as one taken over before, or that stands in the upload twice, is kept as a record marked
    "already imported" so that the page can say so – it is never read or taken over.

    Returns:
        The batch (``None`` if no file was accepted) and the files that were refused.
    """
    delete_old_files()
    rejected: list[Rejection] = []
    batch: LegacyImportBatch | None = None
    seen: dict[str, str] = {}
    total = 0
    for number, file in enumerate(uploaded):
        name = Path(getattr(file, "name", "") or "rechnung.pdf").name[:200] or "rechnung.pdf"
        if number >= MAX_FILES:
            rejected.append(
                Rejection(name, _("Too many files: at most %(count)d invoices at a time.") % {"count": MAX_FILES})
            )
            continue
        problem = _file_problem(file)
        if problem:
            rejected.append(Rejection(name, problem))
            continue
        if total + file.size > MAX_BATCH_BYTES:
            rejected.append(Rejection(name, _("The files together are too large for one upload.")))
            continue
        digest, stored = _keep(file)
        total += file.size
        if batch is None:
            batch = LegacyImportBatch.objects.create(created_by=user)
        record = LegacyImportItem(
            batch=batch, position=number, original_name=name, sha256=digest, size=file.size, stored_name=stored
        )
        before = _same_file_taken_over(digest)
        if before is not None:
            record.state = ItemState.DUPLICATE
            record.message = _("This PDF was imported before (invoice %(number)s).") % {
                "number": getattr(before, "invoice_number", None) or getattr(before, "number", "")
            }
        elif digest in seen:
            record.state = ItemState.DUPLICATE
            record.message = _("The same file is in this upload twice (%(name)s).") % {"name": seen[digest]}
        else:
            seen[digest] = name
        if record.state == ItemState.DUPLICATE:
            (pending_directory() / stored).unlink(missing_ok=True)
            record.stored_name = ""
        record.save()
    return batch, rejected


def _file_problem(file: Any) -> str:
    """Why an uploaded file is refused: not a PDF, too large, empty; ``""`` if it is fine."""
    name = (getattr(file, "name", "") or "").lower()
    size = getattr(file, "size", 0) or 0
    if not name.endswith(".pdf"):
        return _("Only PDF files can be imported.")
    if size <= 0:
        return _("The file is empty.")
    if size > MAX_FILE_BYTES:
        return _("The file is too large (at most %(megabytes)d MB).") % {"megabytes": MAX_FILE_BYTES // 1048576}
    file.seek(0)
    head = file.read(5)
    file.seek(0)
    if head != b"%PDF-":
        return _("The file is not a PDF.")
    return ""


def _keep(file: Any) -> tuple[str, str]:
    """Store an accepted file under a name of its own and return its checksum and stored name."""
    stored = secrets.token_hex(16) + ".pdf"
    digest = hashlib.sha256()
    file.seek(0)
    with (pending_directory() / stored).open("wb") as target:
        for chunk in file.chunks():
            digest.update(chunk)
            target.write(chunk)
    return digest.hexdigest(), stored


def delete_old_files(days: int = PENDING_DAYS) -> int:
    """Remove the files of invoices that were uploaded but never taken over; returns how many records ended."""
    limit = timezone.now() - datetime.timedelta(days=days)
    ended = 0
    for item in LegacyImportItem.objects.filter(
        batch__created_at__lt=limit, state__in=[ItemState.UPLOADED, ItemState.READING, ItemState.READ]
    ):
        drop_file(item)
        item.state = ItemState.SKIPPED
        item.message = _("The invoice was not taken over in time and was dropped.")
        item.save(update_fields=["stored_name", "state", "message"])
        ended += 1
    return ended


def start_reading(batch: LegacyImportBatch, *, user: Any) -> Any:
    """Start the task that reads the invoices of a batch that wait to be read.

    Returns:
        The background task (``None`` if there is nothing to read).
    """
    from rentalars.ai.summary import language_code
    from rentalars.core.jobs import start_job

    if not batch.items.filter(state=ItemState.UPLOADED).exists():
        return None
    job = start_job(
        "legacy_invoices",
        {"batch": batch.pk, "language": language_code()},
        user=user,
        title=_("Reading old invoices"),
    )
    LegacyImportBatch.objects.filter(pk=batch.pk).update(job=job)
    batch.job = job
    return job


# --- What reading hands over --------------------------------------------------------------------------------------------


def prepare(draft: Draft) -> Draft:
    """Match a freshly read draft against the master data: the customer that surely is meant, suggestions for products.

    A customer is chosen beforehand only when the VAT ID or the whole name is the same as one existing customer's – the
    user still sees and confirms it. Products are suggested per position; one is chosen beforehand only when the
    article number stands in the text or the names are almost equal.
    """
    if draft.customer.customer_id is None and (draft.customer.name or draft.customer.vat_id):
        best = drafts.best_customer(draft.customer)
        if best is not None:
            draft.customer.customer_id = best.customer_id
    drafts.suggest_for_lines(draft.lines)
    return draft


def store_reading(item: LegacyImportItem, draft: Draft, message: str) -> None:
    """Keep the proposal with the record of its invoice; the invoice now waits to be checked."""
    item.proposal = draft.to_json()
    item.invoice_number = draft.invoice.number
    item.invoice_date = draft.invoice.date
    item.source = draft.source
    item.message = (message or "")[:500]
    item.state = ItemState.READ
    item.save(update_fields=["proposal", "invoice_number", "invoice_date", "source", "message", "state"])


def save_draft(item: LegacyImportItem, draft: Draft, *, merge_into: LegacyImportItem | None = None) -> None:
    """Keep the proposal as it was edited in the preview (the checks look at the kept version)."""
    item.proposal = draft.to_json()
    item.invoice_number = draft.invoice.number
    item.invoice_date = draft.invoice.date
    item.merge_into = merge_into
    item.save(update_fields=["proposal", "invoice_number", "invoice_date", "merge_into"])


def draft_of(item: LegacyImportItem) -> Draft:
    """The kept proposal of an item, read strictly."""
    return Draft.from_json(item.proposal)


def fingerprint(item: LegacyImportItem) -> str:
    """A checksum of what would be taken over from an item.

    The confirmation page sends it back, so that a proposal that was changed in between (another tab, another user)
    is not taken over unseen.
    """
    payload = json.dumps([item.proposal, item.merge_into_id], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


# --- Checks -------------------------------------------------------------------------------------------------------------


@dataclass
class Issue:
    """One thing the checks found: ``key`` names the field of the preview it belongs to ("" for the invoice as a whole)."""

    key: str
    message: str
    level: str = "error"


@dataclass
class Report:
    """What the checks of one invoice found: ``errors`` block taking it over, ``warnings`` only want to be read."""

    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Whether nothing blocks taking the invoice over."""
        return not self.errors

    def error(self, key: str, message: Any) -> None:
        """Note an error."""
        self.errors.append(Issue(key, str(message)))

    def warn(self, key: str, message: Any) -> None:
        """Note a warning."""
        self.warnings.append(Issue(key, str(message), "warning"))

    def of(self, key: str) -> list[Issue]:
        """The errors and warnings of one field."""
        return [issue for issue in [*self.errors, *self.warnings] if issue.key == key]

    def messages(self) -> list[str]:
        """The texts of the errors, for an API answer or a message."""
        return [issue.message for issue in self.errors]


def tolerance(lines: int) -> Decimal:
    """How far sums of rounded amounts may differ from the totals of an invoice: 2 cents and 1 cent per position, at most 1 €."""
    return min(Decimal("0.02") + Decimal("0.01") * lines, Decimal("1.00"))


def range_collision(number: str) -> bool:
    """Whether an invoice number lies where the live invoice numbers still will go (it would collide one day).

    The live range counts up from ``next_value`` (``RE-2027-0042``, 0043 …) and a number is taken only once: an old
    number of the shape of the range at or beyond the counter would meet it later (``Document.number`` is unique).
    Numbers behind the counter, of earlier years of a yearly range, or of a different shape are safe.
    """
    from rentalars.core.models import NumberRange, NumberRangeKey

    number_range = NumberRange.objects.filter(key=NumberRangeKey.INVOICE).first()
    if number_range is None or not number:
        return False
    parts = number_range.prefix.split("{year}")
    pattern = (
        r"(?P<year>\d{4})".join(re.escape(part) for part in parts) + rf"(?P<value>\d{{{number_range.min_digits},}})"
    )
    match = re.fullmatch(pattern, number.strip(), re.IGNORECASE)
    if match is None:
        return False
    value = int(match["value"])
    today_year = timezone.localdate().year
    if "year" in match.groupdict() and match["year"] is not None and number_range.reset_yearly:
        year = int(match["year"])
        counter_year = number_range.current_year or today_year
        if year < counter_year:
            return False
        next_value = number_range.next_value if year == counter_year else number_range.start_value
        return value >= next_value
    return value >= number_range.next_value


def _customer_issues(draft: Draft, report: Report, rights: Any) -> None:
    """Checks of the customer part."""
    from rentalars.customers.models import VAT_ID_PATTERN, Customer

    part = draft.customer
    if part.customer_id is not None:
        customer = Customer.objects.filter(pk=part.customer_id).first()
        if customer is None or customer.anonymised_at is not None:
            report.error(
                "customer", _("The chosen customer does not exist (any more). Choose another or make a new one.")
            )
            return
        if part.vat_id and customer.vat_id and part.vat_id != customer.vat_id:
            report.warn(
                "customer",
                _("The VAT ID on the invoice (%(invoice)s) differs from that of the customer (%(customer)s).")
                % {"invoice": part.vat_id, "customer": customer.vat_id},
            )
        if not customer.is_active:
            report.warn("customer", _("The customer is deactivated."))
        return
    if not part.name:
        report.error("customer_name", _("Enter the name of the customer, or choose an existing customer."))
        return
    if not rights_can_create(rights):
        report.error("customer", _("You may not create customers. Choose an existing customer."))
    if part.vat_id and not VAT_ID_PATTERN.match(part.vat_id):
        report.error("customer_vat_id", _("A VAT ID starts with the country code and has no spaces, e.g. DE123456789."))
    certain = [candidate for candidate in drafts.customer_candidates(part) if candidate.certain]
    if certain and not part.allow_duplicate:
        first = certain[0]
        report.error(
            "customer",
            _(
                "A customer with the same %(why)s exists already: %(name)s (%(number)s). Choose it, or confirm that you want a new one."
            )
            % {"why": first.reason, "name": first.name, "number": first.number},
        )


def rights_can_create(rights: Any) -> bool:
    """Whether the rights allow making customers; ``None`` rights (a check without a user) allow it."""
    return True if rights is None else may_create_customers(rights)


def check(
    draft: Draft,
    item: LegacyImportItem | None = None,
    *,
    rights: Any = None,
    siblings: list[LegacyImportItem] | None = None,
) -> Report:
    """All checks of one invoice: plausibility (warnings) and what blocks taking it over (errors); see the module text.

    ``item`` is the record the draft belongs to (its checksum and its place in the batch); ``siblings`` the other
    invoices of the batch that are still open – the same number twice is noticed.
    """
    report = Report()
    for key, kind in draft.typed_errors.items():
        report.error(
            key,
            _("This is not a date.") if kind == "date" else _("This is not a number."),
        )
    _head_issues(draft, report, item, siblings or [])
    _customer_issues(draft, report, rights)
    _line_issues(draft, report)
    _range_issues(draft, report)
    _sum_issues(draft, report)
    return report


def _head_issues(draft: Draft, report: Report, item: LegacyImportItem | None, siblings: list[LegacyImportItem]) -> None:
    """Checks of the invoice head: number, date, period, currency, duplicates, the live number range."""
    from rentalars.documents.models import Document

    invoice = draft.invoice
    if not invoice.number:
        report.error("number", _("Enter the invoice number."))
    else:
        if range_collision(invoice.number):
            report.error(
                "number",
                _(
                    "This number lies in the number range of the invoices made in Rentalars and would meet it later. "
                    "Change the number (for example “ALT-…”) or move the counter of the range behind it."
                ),
            )
        existing = Document.objects.filter(number__iexact=invoice.number).first()
        if existing is not None:
            same = LegacyImportItem.objects.filter(document=existing, state=ItemState.IMPORTED).first()
            report.error(
                "number",
                _("An invoice with this number exists already: it was imported on %(date)s.")
                % {"date": same.imported_at.strftime(local_pattern("%d.%m.%Y"))}
                if same is not None and same.imported_at
                else _("A document with this number exists already."),
            )
        for other in siblings:
            if other.pk != (item.pk if item else None) and other.invoice_number.casefold() == invoice.number.casefold():
                report.warn(
                    "number",
                    _("The invoice %(number)s is in the file %(name)s as well.")
                    % {"number": invoice.number, "name": other.original_name},
                )
    if item is not None and item.sha256:
        before = _same_file_taken_over(item.sha256)
        if before is not None and getattr(before, "pk", None) != item.pk:
            report.error("", _("This PDF was imported before."))
    today = timezone.localdate()
    if invoice.date is None:
        report.error("date", _("Enter the invoice date."))
    elif invoice.date > today:
        report.error("date", _("The invoice date lies in the future."))
    if invoice.currency != "EUR":
        report.error(
            "currency",
            _("The invoice is in %(currency)s. Only invoices in euro can be imported.")
            % {"currency": invoice.currency},
        )
    if invoice.service_start and invoice.service_end and invoice.service_end < invoice.service_start:
        report.error("service_end", _("The end of the service period is before its start."))
    if invoice.service_start and invoice.date and invoice.service_start > invoice.date + datetime.timedelta(days=366):
        report.warn("service_start", _("The service period starts long after the invoice date."))
    if invoice.paid_on and invoice.date and invoice.paid_on < invoice.date:
        report.warn("paid_on", _("The invoice was paid before its date."))


def _line_issues(draft: Draft, report: Report) -> None:
    """Checks of the positions: at least one, text, quantity, tax rate in the master data, printed amount."""
    from rentalars.products.models import Product

    if not draft.priced_lines:
        report.error("lines", _("Add at least one position with a price."))
    when = draft.invoice.date
    for index, line in enumerate(draft.lines):
        key = f"lines.{index}."
        if not line.title:
            report.error(key + "title", _("Enter the text of the position."))
        if line.is_text:
            continue
        if line.quantity <= 0:
            report.error(key + "quantity", _("The quantity must be greater than zero."))
        if line.tax_percent is None:
            report.error(key + "tax", _("Enter the tax rate of the position."))
        elif drafts.tax_rate_for(line.tax_percent, when) is None:
            report.error(
                key + "tax",
                _("There is no tax rate of %(rate)s %% in the master data. Create it there first.")
                % {"rate": str(line.tax_percent.normalize())},
            )
        if line.division in (drafts.KIND_CREW, drafts.KIND_LOGISTICS) and (line.unit_price < 0 or line.base < 0):
            report.error(
                key + "unit_price",
                _("A personnel or logistics position cannot have a negative price. Set the kind to material."),
            )
        if line.division == drafts.KIND_CREW:
            _crew_issues(line, key, report)
        elif line.division == drafts.KIND_LOGISTICS:
            _logistics_issues(line, key, report)
        elif line.product_id is not None:
            product = Product.objects.filter(pk=line.product_id, is_active=True, owner__isnull=True).first()
            if product is None:
                report.error(key + "product", _("The chosen product does not exist (any more)."))
            elif (product.tracks_stock or product.is_kit) and line.quantity != line.quantity.to_integral_value():
                report.error(key + "quantity", _("This product is planned in whole pieces."))
        if line.amount is not None and abs(line.net - line.amount) > Decimal("0.05"):
            report.warn(
                key + "amount",
                _("Quantity × price makes %(computed)s, the invoice prints %(printed)s for this position.")
                % {"computed": format_money(line.net), "printed": format_money(line.amount)},
            )


def _crew_issues(line: drafts.Line, key: str, report: Report) -> None:
    """A position of personnel becomes a crew line: it needs a job function; its unit says how it is billed."""
    from rentalars.personnel.models import JobFunction

    if line.job_function_id is None:
        report.error(key + "job_function", _("Choose the job function of this personnel position."))
    elif not JobFunction.objects.filter(pk=line.job_function_id).exists():
        report.error(key + "job_function", _("The chosen job function does not exist (any more)."))
    if _crew_billing(line) == "flat":
        report.warn(
            key + "unit",
            _("The unit “%(unit)s” is neither hours nor days: the position is taken over as a flat rate.")
            % {"unit": line.unit or "–"},
        )


def _logistics_issues(line: drafts.Line, key: str, report: Report) -> None:
    """A position of logistics becomes a vehicle booking with a trip at a flat rate: it needs a motor vehicle."""
    from rentalars.products.models import Product, ProductKind, VehicleType

    if line.product_id is None:
        report.error(
            key + "product",
            _("Choose the vehicle of this logistics position – or set the kind of the position to material."),
        )
    elif not Product.objects.filter(
        pk=line.product_id, kind=ProductKind.VEHICLE, vehicle_type=VehicleType.CAR, is_active=True, owner__isnull=True
    ).exists():
        report.error(key + "product", _("Choose a motor vehicle of the fleet."))


def _crew_billing(line: drafts.Line) -> str:
    """How a personnel position is billed once it is a crew line: ``plan`` (hours), ``day`` (whole days) or ``flat``."""
    unit = drafts.clip(line.unit, drafts.LIMITS["unit"]).strip(". ").casefold()
    if unit in drafts.HOUR_UNITS and line.quantity <= Decimal("99999.99"):
        return "plan"
    if (
        unit in {"tag", "tage", "day", "days", "d", "manntag", "manntage"}
        and line.quantity == line.quantity.to_integral_value()
        and 1 <= line.quantity <= 999
    ):
        return "day"
    return "flat"


def _range_issues(draft: Draft, report: Report) -> None:
    """Amounts too large to be stored are an error with the row they come from (review: MariaDB would refuse them)."""
    for key, kind in draft.range_problems():
        report.error(
            key,
            _("This amount is too large: a position or an invoice cannot hold more than %(limit)s.")
            % {"limit": format_money(drafts.MAX_TOTAL)}
            if kind == "line"
            else _("The sum is too large: an invoice cannot hold more than %(limit)s.")
            % {"limit": format_money(drafts.MAX_TOTAL)},
        )


def _sum_issues(draft: Draft, report: Report) -> None:
    """Checks of the sums: the positions against the totals of the invoice, the tax, net + tax = gross."""
    totals = draft.totals
    count = len(draft.priced_lines)
    allowed = tolerance(count)
    net, tax = draft.net_total, draft.tax_total
    if totals.net is None and totals.gross is None:
        if draft.priced_lines:
            report.warn(
                "total_net", _("No totals were read: the sum of the positions cannot be compared with the invoice.")
            )
        return
    if totals.net is not None and abs(net - totals.net) > allowed:
        report.warn(
            "total_net",
            _("The positions add up to %(sum)s net, the invoice states %(total)s.")
            % {"sum": format_money(net), "total": format_money(totals.net)},
        )
    if totals.tax is not None and abs(tax - totals.tax) > allowed:
        report.warn(
            "total_tax",
            _("The tax of the positions is %(sum)s, the invoice states %(total)s.")
            % {"sum": format_money(tax), "total": format_money(totals.tax)},
        )
    base_net = totals.net if totals.net is not None else net
    base_tax = totals.tax if totals.tax is not None else tax
    if totals.gross is not None and abs(base_net + base_tax - totals.gross) > allowed:
        report.warn(
            "total_gross",
            _("Net plus tax makes %(sum)s, the invoice states %(total)s to pay.")
            % {"sum": format_money(base_net + base_tax), "total": format_money(totals.gross)},
        )
    if any(line.tax_percent is None for line in draft.priced_lines):
        return
    rates = {line.tax_percent for line in draft.priced_lines}
    if totals.net and totals.tax is not None and rates:
        implied = (totals.tax / totals.net * 100) if totals.net else Decimal(0)
        if min(abs(implied - (rate or 0)) for rate in rates) > Decimal("0.6") and len(rates) == 1:
            report.warn(
                "total_tax",
                _("The tax of the invoice is %(implied)s %% of its net total, the positions have %(rate)s %%.")
                % {"implied": str(implied.quantize(Decimal("0.1"))), "rate": str(next(iter(rates)).normalize())},
            )


def group_report(head: LegacyImportItem, members: list[LegacyImportItem], *, rights: Any) -> dict[int, Report]:
    """The checks of every invoice of a project, each with the rules of the project they are joined in.

    Joined invoices share the customer of the first one; the others are checked against it (it must be the same
    customer, not a different one).
    """
    reports: dict[int, Report] = {}
    first = draft_of(head)
    siblings = [head, *members]
    for item in siblings:
        draft = draft_of(item)
        if item is not head:
            draft.customer = first.customer
        reports[item.pk] = check(draft, item, rights=rights, siblings=siblings)
        if item is not head:
            own = draft_of(item).customer
            if (own.customer_id or own.name) and not _same_customer(own, first.customer):
                reports[item.pk].error(
                    "merge_into",
                    _("This invoice names another customer (%(name)s) than the invoice it is joined to.")
                    % {"name": own.name or str(own.customer_id)},
                )
    return reports


def _same_customer(first: drafts.CustomerPart, second: drafts.CustomerPart) -> bool:
    """Whether two customer parts name the same customer: the same customer of the system, or the same VAT ID / name."""
    from rentalars.customers.services import normalised_name

    if first.customer_id and second.customer_id:
        return first.customer_id == second.customer_id
    if first.vat_id and second.vat_id:
        return first.vat_id == second.vat_id
    return bool(normalised_name(first.name)) and normalised_name(first.name) == normalised_name(second.name)


# --- The summary and the confirmation ---------------------------------------------------------------------------------


@dataclass
class Plan:
    """Exactly what taking a group of invoices over will create – shown before the user confirms."""

    head: LegacyImportItem
    members: list[LegacyImportItem]
    customer_name: str
    customer_new: bool
    project_name: str
    period: tuple[datetime.date, datetime.date]
    venue: str
    invoices: list[dict[str, Any]]
    free_lines: int
    product_lines: int
    text_lines: int
    reports: dict[int, Report]
    #: The lines of personnel (crew lines) and of logistics (vehicle bookings).
    crew_lines: int = 0
    vehicle_lines: int = 0

    @property
    def items(self) -> list[LegacyImportItem]:
        """The head and the invoices joined to it."""
        return [self.head, *self.members]

    @property
    def errors(self) -> list[str]:
        """Everything that blocks, of all invoices of the group."""
        return [issue.message for report in self.reports.values() for issue in report.errors]


def groups_of(items: list[LegacyImportItem]) -> list[tuple[LegacyImportItem, list[LegacyImportItem]]]:
    """The chosen invoices as projects: a head and the invoices joined to it (those that are open); order kept.

    Choosing an invoice that is joined to another chooses the other one too – the project is made as a whole.
    """
    groups: list[tuple[LegacyImportItem, list[LegacyImportItem]]] = []
    seen: set[int] = set()
    for item in items:
        head = item.merge_into if item.merge_into_id and item.merge_into.is_open else item
        if head.pk in seen:
            continue
        seen.add(head.pk)
        members = list(head.joined.filter(state=ItemState.READ).order_by("position", "pk"))
        groups.append((head, members))
    return groups


def project_period(drafts_: list[Draft]) -> tuple[datetime.date, datetime.date]:
    """The days of the project: from the earliest start to the latest end of the service periods (else the invoice date)."""
    starts, ends = [], []
    for draft in drafts_:
        start = draft.invoice.service_start or draft.invoice.date
        end = draft.invoice.service_end or draft.invoice.service_start or draft.invoice.date
        if start:
            starts.append(start)
        if end:
            ends.append(end)
    today = timezone.localdate()
    first = min(starts) if starts else today
    last = max(ends) if ends else first
    return first, max(first, last)


def summary(head: LegacyImportItem, members: list[LegacyImportItem], *, rights: Any) -> Plan:
    """What would be created for a group of invoices – the confirmation page shows this and nothing else."""
    from rentalars.customers.models import Customer

    first = draft_of(head)
    all_drafts = [first, *(draft_of(member) for member in members)]
    reports = group_report(head, members, rights=rights)
    customer = Customer.objects.filter(pk=first.customer.customer_id).first() if first.customer.customer_id else None
    lines = [line for draft in all_drafts for line in draft.lines]
    invoices = [
        {
            "item": item,
            "number": draft.invoice.number,
            "date": draft.invoice.date,
            "net": draft.totals.net if draft.totals.net is not None else draft.net_total,
            "gross": draft.totals.gross if draft.totals.gross is not None else draft.net_total + draft.tax_total,
            "paid": draft.invoice.paid,
            "paid_on": draft.invoice.paid_on,
            "name": item.original_name,
        }
        for item, draft in zip([head, *members], all_drafts, strict=True)
    ]
    return Plan(
        head=head,
        members=members,
        customer_name=customer.name if customer else first.customer.name,
        customer_new=customer is None,
        project_name=_project_name(first),
        period=project_period(all_drafts),
        venue=first.invoice.venue,
        invoices=invoices,
        free_lines=sum(
            1
            for line in lines
            if not line.is_text and line.division == drafts.KIND_MATERIAL and line.product_id is None
        ),
        product_lines=sum(
            1
            for line in lines
            if not line.is_text and line.division == drafts.KIND_MATERIAL and line.product_id is not None
        ),
        crew_lines=sum(1 for line in lines if not line.is_text and line.division == drafts.KIND_CREW),
        vehicle_lines=sum(1 for line in lines if not line.is_text and line.division == drafts.KIND_LOGISTICS),
        text_lines=sum(1 for line in lines if line.is_text),
        reports=reports,
    )


def _project_name(draft: Draft) -> str:
    """The name of the project made from an invoice: the event, else "Old project, invoice …"."""
    if draft.invoice.event_name:
        return draft.invoice.event_name
    return _("Old project, invoice %(number)s") % {"number": draft.invoice.number}


@dataclass
class Outcome:
    """What taking over one group created – or why it did not."""

    items: list[LegacyImportItem]
    project: Any = None
    customer: Any = None
    customer_created: bool = False
    documents: list[Any] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Whether the group was taken over."""
        return not self.errors


def confirm(
    chosen: list[LegacyImportItem],
    *,
    user: Any,
    rights: Any,
    fingerprints: dict[int, str] | None = None,
) -> list[Outcome]:
    """Take the chosen invoices over – per project, each in one transaction, so one that fails does not stop the others.

    ``fingerprints`` (item → :func:`fingerprint`) are those the confirmation page showed; an invoice whose proposal was
    changed since is not taken over.

    Raises:
        PermissionDenied: Not a user of the import.
    """
    from django.core.exceptions import PermissionDenied

    if not may_use(rights):
        raise PermissionDenied
    outcomes: list[Outcome] = []
    for head, members in groups_of(chosen):
        group = [head, *members]
        try:
            if fingerprints is not None:
                stale = [item for item in group if fingerprints.get(item.pk) not in (None, fingerprint(item))]
                if stale:
                    raise ValidationError(
                        _("The proposal of the invoice %(name)s was changed in the meantime. Check it again.")
                        % {"name": stale[0].original_name}
                    )
            outcomes.append(_take_over(head, members, user=user, rights=rights))
        except ValidationError as error:
            outcomes.append(Outcome(items=group, errors=error.messages))
    return outcomes


def _reuse_customer_of_batch(head: LegacyImportItem) -> None:
    """Invoices of one customer taken over together: the customer the first one made is the one of the next.

    A draft that names a new customer whose VAT ID or name is the same as that of a customer *this batch made a moment
    ago* gets that customer – otherwise the second invoice would be refused as a duplicate of the first one's customer.
    A customer that existed before is never chosen here: the user chooses it in the preview.
    """
    draft = draft_of(head)
    part = draft.customer
    if part.customer_id is not None or part.allow_duplicate or not (part.name or part.vat_id):
        return
    certain = [candidate for candidate in drafts.customer_candidates(part) if candidate.certain]
    if len(certain) != 1:
        return
    made = LegacyImportItem.objects.filter(
        batch_id=head.batch_id, customer_id=certain[0].customer_id, customer_created=True, state=ItemState.IMPORTED
    )
    if made.exists():
        part.customer_id = certain[0].customer_id
        save_draft(head, draft, merge_into=head.merge_into)


def _next_project_number(year: int) -> str:
    """The next number ``ALT-2025-0007`` of the imported projects of a year; the live project numbers stay untouched."""
    from rentalars.projects.models import Project

    prefix = f"{PROJECT_PREFIX}-{year}-"
    last = (
        Project.objects.filter(number__startswith=prefix).order_by("-number").values_list("number", flat=True).first()
    )
    tail = (last or "")[len(prefix) :]
    number = int(tail) + 1 if tail.isdigit() else 1
    while Project.objects.filter(Q(number=f"{prefix}{number:04d}") | Q(former_number=f"{prefix}{number:04d}")).exists():
        number += 1
    return f"{prefix}{number:04d}"


def _midnight(day: datetime.date, *, end: bool = False) -> datetime.datetime:
    """The start (00:00) or the end (23:59) of a day in the time zone of the installation."""
    moment = datetime.datetime.combine(day, datetime.time(23, 59) if end else datetime.time(0, 0))
    return timezone.make_aware(moment)


def _provenance(item: LegacyImportItem, user: Any) -> str:
    """The sentence that goes into the notes: imported from invoice … on … by …."""
    return _("Imported from invoice %(number)s of %(date)s on %(today)s by %(user)s.") % {
        "number": item.invoice_number,
        "date": item.invoice_date.strftime(local_pattern("%d.%m.%Y")) if item.invoice_date else "–",
        "today": timezone.localdate().strftime(local_pattern("%d.%m.%Y")),
        "user": user.get_full_name() or user.get_username() if user is not None else "–",
    }


@transaction.atomic
def _take_over(head: LegacyImportItem, members: list[LegacyImportItem], *, user: Any, rights: Any) -> Outcome:
    """Create customer (if new), the closed project, its lines and the historic invoices of a group – all or nothing."""
    from rentalars.core.audit import record_event
    from rentalars.core.models import AuditLogEntry
    from rentalars.customers.models import Customer
    from rentalars.customers.services import save_customer
    from rentalars.projects.models import ProjectStatus

    group = list(
        LegacyImportItem.objects.select_for_update()
        .filter(pk__in=[item.pk for item in [head, *members]])
        .order_by("position", "pk")
    )
    by_pk = {item.pk: item for item in group}
    head, members = by_pk[head.pk], [by_pk[member.pk] for member in members if member.pk in by_pk]
    if any(item.state != ItemState.READ for item in group):
        raise ValidationError(_("This invoice was taken over or dropped in the meantime."))
    _reuse_customer_of_batch(head)
    reports = group_report(head, members, rights=rights)
    problems = [issue.message for report in reports.values() for issue in report.errors]
    if problems:
        raise ValidationError(problems)
    group_drafts = {item.pk: draft_of(item) for item in group}
    first = group_drafts[head.pk]
    outcome = Outcome(items=[head, *members])
    with quiet():
        # --- the customer ---
        if first.customer.customer_id:
            customer = Customer.objects.get(pk=first.customer.customer_id)
        else:
            part = first.customer
            customer = Customer(
                name=part.name,
                name_addition=part.name_addition,
                street=part.street,
                postal_code=part.postal_code,
                city=part.city,
                country=part.country,
                vat_id=part.vat_id,
                email=part.email,
                note=_provenance(head, user),
            )
            save_customer(customer)
            outcome.customer_created = True
        outcome.customer = customer
        # --- the project ---
        period = project_period(list(group_drafts.values()))
        project = _create_project(first, group, customer, period, user)
        outcome.project = project
        # --- the positions, then one historic invoice per PDF ---
        position = 0
        number = 0
        for item in [head, *members]:
            draft = group_drafts[item.pk]
            lines = _create_lines(project, draft, period, position)
            position += len(draft.lines)
            number += len(lines)
        for item in [head, *members]:
            draft = group_drafts[item.pk]
            document = _create_document(item, draft, project, customer, user)
            outcome.documents.append(document)
            item.document = document
        now = timezone.now()
        record_event(
            project,
            "project.legacy_imported",
            {"invoices": ", ".join(item.invoice_number for item in group), "user": str(user) if user else ""},
        )
        mark = AuditLogEntry.objects.order_by("-pk").values_list("pk", flat=True).first() or 0
        for item in group:
            draft = group_drafts[item.pk]
            item.state = ItemState.IMPORTED
            item.customer = customer
            item.customer_created = outcome.customer_created and item is head
            item.project = project
            item.invoice_number = draft.invoice.number
            item.invoice_date = draft.invoice.date
            item.paid = draft.invoice.paid
            item.paid_on = draft.invoice.paid_on if draft.invoice.paid else None
            item.imported_at = now
            item.imported_by = user
            item.audit_mark = mark
            item.message = ""
            transaction.on_commit(
                lambda stored=item.stored_name: (pending_directory() / stored).unlink(missing_ok=True)
            )
            item.stored_name = ""
            item.save()
    project.refresh_from_db()
    if ProjectStatus(project.status) != ProjectStatus.CLOSED:  # pragma: no cover - guard against a changed default
        raise ValidationError(_("The project could not be closed."))
    return outcome


def _create_project(
    draft: Draft, group: list[LegacyImportItem], customer: Any, period: tuple[datetime.date, datetime.date], user: Any
) -> Any:
    """The closed project of an old invoice: no stock reserved, no planning, the provenance in its notes."""
    from rentalars.projects.models import InvoiceMark, Project, ProjectStatus

    notes = "\n".join(_provenance(item, user) for item in group)
    for attempt in range(5):
        project = Project(
            number=_next_project_number(period[0].year),
            name=_project_name(draft),
            customer=customer,
            status=ProjectStatus.CLOSED,
            start=_midnight(period[0]),
            end=_midnight(period[1], end=True),
            event_start=_midnight(period[0]),
            event_end=_midnight(period[1], end=True),
            venue=draft.invoice.venue,
            notes=notes,
            # DOK-015: the invoice exists (it is registered with the project) – no reminder to invoice it.
            invoice_status=InvoiceMark.ISSUED,
        )
        project.full_clean()
        try:
            with transaction.atomic():
                project.save()
        except IntegrityError:
            if attempt == 4:
                raise
            continue
        return project
    raise ValidationError(_("The project could not be created."))  # pragma: no cover


def _create_lines(project: Any, draft: Draft, period: tuple[datetime.date, datetime.date], offset: int) -> list[Any]:
    """The positions of an invoice as lines of the project: material, personnel and logistics, text lines.

    Plain model writes, not the planning services: those would check the availability and reserve – a closed
    project reserves nothing, and the lines are history. The price is the price of the invoice (flat billing, no rental
    scale), the product only names what was meant.

    * material: a free line, or a line of the product chosen;
    * personnel: a crew line without a person in the job function chosen – billed by hours (hours × price), per day, or
      as a flat rate, as the unit of the position says;
    * logistics: a booking of the motor vehicle chosen with a trip of its own that is charged at a flat rate.
    """
    from rentalars.masterdata.models import TaxRate
    from rentalars.products.models import BillingMode, Product
    from rentalars.projects.models import MaterialLine

    start, end = project.start, project.end
    default_rate = TaxRate.get_default()
    created = []
    for index, line in enumerate(draft.lines):
        if line.is_text:
            record = MaterialLine(
                project=project,
                title=line.title,
                note=line.note,
                quantity=Decimal("0"),
                start=start,
                end=end,
                position=offset + index,
                tax_rate=default_rate,
                billing_mode=BillingMode.FLAT,
                unit_price=Decimal("0"),
                is_text=True,
            )
        elif line.division == drafts.KIND_CREW:
            record = _create_crew_line(project, line, draft, offset + index)
            created.append(record)
            continue
        elif line.division == drafts.KIND_LOGISTICS:
            record = _create_vehicle_line(project, line, draft, offset + index)
            created.append(record)
            continue
        else:
            product = Product.objects.filter(pk=line.product_id).first() if line.product_id else None
            record = MaterialLine(
                project=project,
                product=product,
                title=line.title,
                note=line.note,
                quantity=line.quantity,
                unit=drafts.unit_for(line.unit),
                start=start,
                end=end,
                position=offset + index,
                tax_rate=drafts.tax_rate_for(line.tax_percent, draft.invoice.date),
                billing_mode=BillingMode.FLAT,
                unit_price=line.unit_price,
                discount_percent=line.discount,
            )
        record.clean_fields()
        record.save()
        created.append(record)
    return created


def _create_crew_line(project: Any, line: drafts.Line, draft: Draft, position: int) -> Any:
    """A personnel position as a crew line without a person (an open place, history): hours, days or a flat rate."""
    from rentalars.personnel.models import JobFunction
    from rentalars.projects.models import CrewBilling, CrewLine

    function = JobFunction.objects.select_related("service_product").get(pk=line.job_function_id)
    billing = _crew_billing(line)
    values: dict[str, Any] = {}
    if billing == "plan":
        values.update(billing=CrewBilling.PLAN, planned_hours=line.quantity, unit_price=line.unit_price)
    elif billing == "day":
        values.update(billing=CrewBilling.DAY, days=int(line.quantity), unit_price=line.unit_price)
    else:  # the price of the whole deployment is quantity × price
        values.update(billing=CrewBilling.FLAT, unit_price=line.base)
    record = CrewLine(
        project=project,
        job_function=function,
        service_product=function.service_product,
        title=line.title,
        note=line.note,
        start=project.start,
        end=project.end,
        position=position,
        tax_rate=drafts.tax_rate_for(line.tax_percent, draft.invoice.date),
        discount_percent=line.discount,
        **values,
    )
    record.clean_fields()
    record.save()
    return record


def _create_vehicle_line(project: Any, line: drafts.Line, draft: Draft, position: int) -> Any:
    """A logistics position as a booking of a motor vehicle with a trip of its own at the flat rate of the position."""
    from rentalars.products.models import Product
    from rentalars.projects.models import TripAdjustment, TripBilling, TripVehicle, VehicleBilling, VehicleLine

    product = Product.objects.get(pk=line.product_id)
    record = VehicleLine(
        project=project,
        product=product,
        title=line.title,
        note=line.note,
        start=project.start,
        end=project.end,
        position=position,
        billing=VehicleBilling.KM,
        tax_rate=drafts.tax_rate_for(line.tax_percent, draft.invoice.date),
        discount_percent=line.discount,
    )
    record.clean_fields()
    record.save()
    trip = TripAdjustment(
        project=project,
        trip_key="",
        title=line.title[:120],
        start=project.start,
        origin=str(_("Warehouse")),
        destination=(draft.invoice.venue or line.title)[:250],
        stops=[],
    )
    trip.save()
    use = TripVehicle(
        project=project,
        trip_key=f"own-{trip.pk}",
        vehicle_line=record,
        billing=TripBilling.FLAT,
        flat_price=line.base,
    )
    use.clean_fields()
    use.save()
    return record


def _create_document(item: LegacyImportItem, draft: Draft, project: Any, customer: Any, user: Any) -> Any:
    """The historic invoice: a document of the kind invoice with the numbers and amounts of the old invoice and its PDF.

    Not made like a new invoice – no number is taken from the range, no PDF is rendered, no XML, no handing over to the
    accounting – but stored as every document is (``Document``, never changed afterwards).
    """
    from rentalars.core.i18n import for_documents
    from rentalars.documents import services as document_services
    from rentalars.documents.models import Document, DocumentKind

    data = stored_path(item).read_bytes()
    if hashlib.sha256(data).hexdigest() != item.sha256:
        raise ValidationError(
            _("The kept PDF of the invoice %(name)s was changed. Upload it again.") % {"name": item.original_name}
        )
    with for_documents():
        template = document_services.template_for(DocumentKind.INVOICE)
        content = _content(item, draft, project, customer, template)
    document = Document(
        project=project,
        customer=customer,
        kind=DocumentKind.INVOICE,
        number=draft.invoice.number,
        title=template.title[:120],
        issued_on=draft.invoice.date,
        created_by=user,
        content=content.as_json(),
        net_total=content.net_total,
        gross_total=content.gross_total,
        due_on=draft.invoice.due_on,
        reference=draft.invoice.event_name[:200],
        sha256=item.sha256,
    )
    document.file.save(f"{draft.invoice.number}.pdf", ContentFile(data), save=False)
    document.save()
    return document


#: The division of an invoice document (DOK-025) that holds the positions of a kind.
_DIVISION_OF_KIND = {
    drafts.KIND_MATERIAL: "material",
    drafts.KIND_CREW: "personnel",
    drafts.KIND_LOGISTICS: "logistics",
}


def _divisions_of(draft: Draft) -> list[tuple[drafts.Line, str]]:
    """Every position with the division it is printed under; a text line goes with the position that follows it.

    A heading or remark of the old invoice stands above what it belongs to; one at the very end goes with the last
    position before it.
    """
    result: list[tuple[drafts.Line, str]] = []
    following = ""
    for line in reversed(draft.lines):
        if not line.is_text:
            following = line.division
        result.append((line, line.division if not line.is_text else following))
    result.reverse()
    fallback = next((line.division for line in reversed(draft.lines) if not line.is_text), drafts.KIND_MATERIAL)
    return [(line, division or fallback) for line, division in result]


def _content(
    item: LegacyImportItem, draft: Draft, project: Any, customer: Any, template: Any
) -> builder.DocumentContent:
    """The content stored with the historic invoice: the positions and totals of the old invoice in the frozen form."""
    by_division: dict[str, list[tuple[drafts.Line, bool]]] = {name: [] for name in drafts.KINDS}
    for line, division in _divisions_of(draft):
        by_division[division].append((line, line.is_text))
    counter = 0
    sections = []
    titles = {
        drafts.KIND_MATERIAL: _("Without group"),
        drafts.KIND_CREW: _("Personnel"),
        drafts.KIND_LOGISTICS: _("Logistics"),
    }
    for name in drafts.KINDS:
        positions = []
        net = Decimal("0")
        for line, is_text in by_division[name]:
            if is_text:
                positions.append(builder.Position(number="", title=line.title, details=line.note, is_text=True))
                continue
            counter += 1
            base = line.base
            discount = money(base * line.discount / Decimal(100))
            rate = drafts.tax_rate_for(line.tax_percent, draft.invoice.date)
            unit = drafts.unit_for(line.unit)
            net += line.net
            positions.append(
                builder.Position(
                    number=str(counter),
                    title=line.title,
                    quantity=line.quantity,
                    unit=unit.abbreviation if unit else line.unit,
                    unit_code=builder.unit_code(unit.abbreviation if unit else line.unit),
                    details=line.note,
                    unit_price=line.unit_price,
                    discount_percent=line.discount,
                    base_amount=base,
                    discount_amount=discount,
                    amount=base - discount,
                    tax_name=rate.name if rate else "",
                    tax_percent=line.tax_percent or Decimal("0"),
                )
            )
        if positions:
            sections.append(
                builder.Section(
                    title=str(titles[name]), positions=positions, subtotal=net, division=_DIVISION_OF_KIND[name]
                )
            )
    # The same divisions as a document made in Rentalars (DOK-025): Material, Personnel, Logistics, each with its sum.
    builder.mark_divisions(
        sections, material_total=sum((s.subtotal for s in sections if s.division == "material"), Decimal("0"))
    )
    shares = [
        builder.TaxShare(
            name=(drafts.tax_rate_for(rate, draft.invoice.date).name if rate is not None else ""),
            percent=rate or Decimal("0"),
            category=builder.tax_category(rate or Decimal("0")),
            net=net,
            tax=tax,
            positions_total=net,
        )
        for rate, net, tax in draft.tax_shares()
    ]
    net_total = draft.totals.net if draft.totals.net is not None else draft.net_total
    tax_total = draft.totals.tax if draft.totals.tax is not None else draft.tax_total
    gross_total = draft.totals.gross if draft.totals.gross is not None else net_total + tax_total
    part = draft.customer
    recipient = [
        value
        for value in [
            customer.name,
            customer.name_addition,
            customer.street,
            f"{customer.postal_code} {customer.city}".strip(),
            customer.country,
        ]
        if value
    ]
    return builder.DocumentContent(
        kind="invoice",
        title=template.title,
        number=draft.invoice.number,
        issued_on=draft.invoice.date,
        company=builder.company_data(),
        recipient=recipient,
        project=builder.project_data(project),
        recipient_email=customer.email,
        customer_number=customer.number,
        customer_vat_id=customer.vat_id or part.vat_id,
        buyer_reference=customer.buyer_reference or customer.number,
        service_start=draft.invoice.service_start,
        service_end=draft.invoice.service_end or draft.invoice.service_start,
        sections=sections,
        taxes=shares,
        net_total=net_total,
        tax_total=tax_total,
        gross_total=gross_total,
        due_on=draft.invoice.due_on,
        reference=draft.invoice.event_name,
    )


# --- Skipping --------------------------------------------------------------------------------------------------------


def skip(item: LegacyImportItem) -> None:
    """Drop an invoice of the preview: it is not taken over, its file goes (the record stays as a trace)."""
    if not item.is_open:
        raise ValidationError(_("This invoice was taken over or dropped already."))
    drop_file(item)
    item.state = ItemState.SKIPPED
    item.merge_into = None
    item.message = _("Skipped.")
    item.save(update_fields=["stored_name", "state", "merge_into", "message"])
    item.joined.update(merge_into=None)


# --- Undo --------------------------------------------------------------------------------------------------------------

#: What may stand next to a project the import made: its own lines and the invoices of the import (checked separately).
_PROJECT_OWN = frozenset(
    {
        "material_lines",
        "crew_lines",
        "vehicle_lines",
        "trip_adjustments",
        "trip_vehicles",
        "documents",
        "legacy_items",
        "subprojects_of_nothing",
    }
)


def _related_rows(instance: Any, allowed: frozenset[str]) -> list[str]:
    """The names of the relations of an object (apart from ``allowed``) that hold rows – things added after the import."""
    found = []
    for relation in instance._meta.related_objects:
        name = relation.get_accessor_name()
        if name in allowed or name.endswith("+"):
            continue
        model = relation.related_model
        if relation.many_to_many:
            exists = getattr(instance, name).exists()
        else:
            exists = model._default_manager.filter(**{relation.field.name: instance}).exists()
        if exists:
            found.append(str(model._meta.verbose_name))
    return found


def undo_problems(batch: LegacyImportBatch, *, user: Any = None, rights: Any = None) -> list[str]:
    """Why an import cannot be undone (empty: it can); see the module text for the rule.

    * within :data:`UNDO_DAYS` days of the import, by whoever made it (or write access to the settings);
    * the change log has no entry after the import for the project (with its lines) and a customer the import made;
    * no document but the historic invoices, no mail, file, time, packing list … on the project; the invoices not sent,
      cancelled or handed to the accounting; the customer made by the import has no other project or document.
    """
    from rentalars.documents.models import Document

    items = list(batch.items.filter(state=ItemState.IMPORTED).select_related("project", "customer", "document"))
    if not items:
        return [_("Nothing of this upload was taken over (or it was undone already).")]
    problems: list[str] = []
    if user is not None and batch.created_by_id != getattr(user, "pk", None):
        if rights is None or not rights.can_write(Module.ADMINISTRATION):
            problems.append(_("Only the user who imported the invoices (or an administrator) can undo it."))
    limit = timezone.now() - datetime.timedelta(days=UNDO_DAYS)
    if any(item.imported_at is None or item.imported_at < limit for item in items):
        problems.append(
            ngettext(
                "The import can be undone for one day only.",
                "The import can be undone for %(days)d days only.",
                UNDO_DAYS,
            )
            % {"days": UNDO_DAYS}
        )
    from rentalars.core.models import AuditLogEntry

    projects = {item.project_id: item.project for item in items if item.project_id}
    for project in projects.values():
        mark = max(item.audit_mark for item in items if item.project_id == project.pk)
        own = {item.document_id for item in items if item.project_id == project.pk and item.document_id}
        if AuditLogEntry.for_object(project).filter(pk__gt=mark).exists():
            problems.append(_("The project %(number)s was changed since the import.") % {"number": project.number})
            continue
        extra = _related_rows(project, _PROJECT_OWN)
        if extra or Document.objects.filter(project=project).exclude(pk__in=own).exists():
            problems.append(
                _("The project %(number)s has been worked on since the import (%(what)s).")
                % {"number": project.number, "what": ", ".join(sorted(set(extra))) or _("documents")}
            )
    for item in items:
        document = item.document
        if document is not None and (
            document.sent_at or document.cancelled_by_id or hasattr(document, "lexware_transfer")
        ):
            problems.append(
                _("The invoice %(number)s was sent, cancelled or handed to the accounting.")
                % {"number": document.number}
            )
        customer = item.customer
        if item.customer_created and customer is not None:
            if AuditLogEntry.for_object(customer).filter(pk__gt=item.audit_mark).exists():
                problems.append(_("The customer %(name)s was changed since the import.") % {"name": customer.name})
            else:
                taken = set(projects)
                if (
                    customer.projects.exclude(pk__in=taken).exists()
                    or customer.outgoing_documents.exclude(
                        pk__in=[i.document_id for i in items if i.document_id]
                    ).exists()
                    or _related_rows(customer, frozenset({"projects", "outgoing_documents", "legacy_items"}))
                ):
                    problems.append(
                        _("The customer %(name)s has been worked with since the import.") % {"name": customer.name}
                    )
    return sorted(set(problems), key=problems.index)


@transaction.atomic
def undo(batch: LegacyImportBatch, *, user: Any, rights: Any) -> int:
    """Take an import back: remove the projects, their invoices and the customers the import made; returns the invoices.

    The records stay, marked "import undone" (and can be imported again: the checksum no longer counts). The numbers of
    the customers made stay used.

    Raises:
        ValidationError: :func:`undo_problems` says why not.
    """
    from rentalars.documents.models import Document

    if not may_use(rights):
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied
    problems = undo_problems(batch, user=user, rights=rights)
    if problems:
        raise ValidationError(problems)
    items = list(
        batch.items.select_for_update()
        .filter(state=ItemState.IMPORTED)
        .select_related("project", "customer", "document")
    )
    projects = {item.project_id: item.project for item in items if item.project_id}
    created_customers = {
        item.customer_id: item.customer for item in items if item.customer_created and item.customer_id
    }
    now = timezone.now()
    with quiet():
        documents = [item.document for item in items if item.document_id]
        for document in documents:
            name = document.file.name
            xml = document.xml_file.name
            # A document is never deleted through the model (DOK-007); a historic invoice that is taken back is the
            # one case, and it is removed with the queryset – its through rows with it.
            Document.objects.filter(pk=document.pk).delete()
            for path in (name, xml):
                if path:
                    document.file.storage.delete(path)
        for item in items:
            item.state = ItemState.UNDONE
            item.undone_at = now
            item.document = None
            item.message = _("Import undone by %(user)s.") % {"user": user.get_username()}
            item.save(update_fields=["state", "undone_at", "document", "message"])
        for project in projects.values():
            project.delete()
        for customer in created_customers.values():
            customer.delete()
    return len(documents)


# --- Lists --------------------------------------------------------------------------------------------------------------


def imported_items() -> Any:
    """The invoices that were taken over (and not undone), newest first – the list of historic invoices."""
    return (
        LegacyImportItem.objects.filter(state=ItemState.IMPORTED)
        .select_related("customer", "project", "document", "imported_by", "batch")
        .order_by("-imported_at", "-pk")
    )


def is_historic(document: Any) -> bool:
    """Whether a document is a historic invoice taken over by the import (``Document.legacy_item``)."""
    return LegacyImportItem.objects.filter(document=document, state=ItemState.IMPORTED).exists()


def batch_summary(batch: LegacyImportBatch) -> dict[str, int]:
    """How many invoices of a batch are in which state – for the progress line of the page and the API."""
    counts = {state.value: 0 for state in ItemState}
    for state in batch.items.values_list("state", flat=True):
        counts[state] = counts.get(state, 0) + 1
    counts["total"] = sum(counts.values())
    counts["finished"] = counts["total"] - counts["uploaded"] - counts["reading"]
    return counts


def _unused() -> None:  # pragma: no cover - keeps imports that the type checkers want in one place
    _ = (time, Line)
