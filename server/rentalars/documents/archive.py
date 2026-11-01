# SPDX-License-Identifier: GPL-3.0-or-later
"""The archive of vouchers for the GoBD: checksums, retention, nightly check (DOK-043).

Every outgoing document and every incoming invoice has an :class:`ArchiveRecord`: its files with SHA-256 and size, the day
the retention period ends (the end of the calendar year of the voucher plus eight years for accounting vouchers, six for
business letters – both set in Settings → Accounting) and what the last check found.

* The nightly maintenance **registers** what has no record yet and **checks** a part of the archive, so that every file is
  checked within ``archive_check_days``. A file that is gone or no longer matches its checksum is a *finding*: the self-check
  turns it red and the operators hear of it (``core.selfcheck``).
* A voucher is **kept**: an outgoing document cannot be deleted at all (``Document.delete``); an incoming invoice that was
  archived cannot be deleted before its retention period ended. A new upload has one day to be deleted when it was a mistake
  (nothing is archived before that).
* After the retention period the voucher may be deleted; its record stays with the status "deleted after the retention
  period", so that the log of the archive stays complete.

This is the technical part of the procedure documentation; it does not make a company GoBD-compliant by itself. Rentalars
makes no claim of certification.
"""

from __future__ import annotations

import datetime
import hashlib
import math
from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, QuerySet
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.core.i18n import local_pattern
from rentalars.documents.models import (
    AccountingSettings,
    ArchiveRecord,
    ArchiveSource,
    ArchiveStatus,
    Document,
    DocumentKind,
)
from rentalars.documents.outgoing import CUSTOMER_KINDS
from rentalars.incoming.models import IncomingInvoice

#: How long a new upload may still be deleted: the archive takes an incoming invoice only after this.
GRACE = datetime.timedelta(days=1)

_CHUNK = 1024 * 1024
_ACCOUNTING_KINDS = {DocumentKind.INVOICE, DocumentKind.CANCELLATION}


@dataclass
class Result:
    """What one run did."""

    registered: int = 0
    checked: int = 0
    problems: int = 0
    deleted: int = 0


def retain_until(voucher_date: datetime.date, years: int) -> datetime.date:
    """The end of the retention period: 31 December of the year of the voucher plus ``years``."""
    return datetime.date(voucher_date.year + years, 12, 31)


def _hash(storage: Any, name: str) -> tuple[str, int] | None:
    """SHA-256 and size of a stored file; ``None`` if it cannot be read."""
    digest = hashlib.sha256()
    size = 0
    try:
        with storage.open(name, "rb") as handle:
            while chunk := handle.read(_CHUNK):
                digest.update(chunk)
                size += len(chunk)
    except (OSError, ValueError):
        return None
    return digest.hexdigest(), size


def _files_of(source: str, voucher: Document | IncomingInvoice) -> list[dict[str, Any]]:
    """The files a voucher consists of, with their checksums as they are now."""
    entries: list[dict[str, Any]] = []
    names = [("pdf" if source == ArchiveSource.DOCUMENT else "original", voucher.file.name)]
    xml = voucher.xml_file.name if voucher.xml_file else ""
    if xml:
        names.append(("xml", xml))
    for role, name in names:
        if not name:
            continue
        found = _hash(voucher.file.storage, name)
        entries.append(
            {"role": role, "name": name, "sha256": found[0] if found else "", "size": found[1] if found else 0}
        )
    return entries


def _years_for(voucher: Document | IncomingInvoice, settings: AccountingSettings) -> int:
    if isinstance(voucher, Document) and voucher.kind not in _ACCOUNTING_KINDS:
        return settings.retention_letter_years
    return settings.retention_invoice_years


def _details(source: str, voucher: Document | IncomingInvoice) -> tuple[str, str, datetime.date]:
    if isinstance(voucher, Document):
        return voucher.number, voucher.title[:160], voucher.issued_on
    day = voucher.invoice_date or timezone.localtime(voucher.created_at).date()
    return voucher.invoice_number or voucher.original_name[:80], voucher.supplier_label[:160], day


def _retention_base(voucher: Document | IncomingInvoice, day: datetime.date) -> datetime.date:
    """The day the retention period counts from: the later of the voucher date and the day it came in.

    The date of an incoming invoice is typed in or read from the file; a typo (2015 instead of 2025) or an invoice
    from December that arrives in January must not shorten the period.
    """
    if isinstance(voucher, IncomingInvoice):
        return max(day, timezone.localtime(voucher.created_at).date())
    return day


def register(source: str, voucher: Document | IncomingInvoice) -> ArchiveRecord:
    """Put a voucher into the archive (once); an existing record is returned as it is."""
    existing = ArchiveRecord.objects.filter(source=source, source_id=voucher.pk).first()
    if existing is not None:
        return existing
    settings = AccountingSettings.load()
    reference, title, day = _details(source, voucher)
    files = _files_of(source, voucher)
    record = ArchiveRecord(
        source=source,
        source_id=voucher.pk,
        reference=reference[:80],
        title=title,
        voucher_date=day,
        files=files,
        retain_until=retain_until(_retention_base(voucher, day), _years_for(voucher, settings)),
        last_checked_at=timezone.now(),
    )
    problem = _compare(record, voucher, files)
    if isinstance(voucher, Document) and files and files[0]["sha256"] and files[0]["sha256"] != voucher.sha256:
        record.status = ArchiveStatus.CHANGED
        record.finding = _("The PDF does not match the checksum stored with the document.")
    elif problem:
        record.status, record.finding = problem
    try:
        with transaction.atomic():
            record.save()
    except IntegrityError:  # the nightly run and a manual check registered it at the same moment
        return ArchiveRecord.objects.get(source=source, source_id=voucher.pk)
    return record


def _compare(record: ArchiveRecord, voucher: Any, current: list[dict[str, Any]]) -> tuple[str, str] | None:
    """Compare the recorded files with the current ones: a status and a sentence, or ``None`` if all is well."""
    for entry in current:
        if not entry["sha256"]:
            return ArchiveStatus.MISSING, _("The file %(name)s cannot be read.") % {"name": entry["name"]}
    return None


def verify(record: ArchiveRecord) -> ArchiveRecord:
    """Check one record against the files now: unchanged, changed, missing; or deleted after its retention period."""
    voucher = _voucher_of(record)
    today = timezone.localdate()
    status, finding = ArchiveStatus.OK, ""
    if voucher is None:
        if record.retain_until < today:
            status = ArchiveStatus.DELETED
        else:
            status, finding = ArchiveStatus.MISSING, _("The voucher was deleted before its retention period ended.")
    else:
        for known in record.files:
            found = _hash(voucher.file.storage, known["name"])
            if found is None:
                status, finding = (
                    ArchiveStatus.MISSING,
                    _("The file %(name)s cannot be read.") % {"name": known["name"]},
                )
                break
            if found[0] != known["sha256"]:
                status, finding = ArchiveStatus.CHANGED, _("The file %(name)s was changed.") % {"name": known["name"]}
                break
            if known.get("role") == "pdf" and isinstance(voucher, Document) and found[0] != voucher.sha256:
                # a file that was already altered when it was registered must stay a finding, night after night
                status, finding = (
                    ArchiveStatus.CHANGED,
                    _("The PDF does not match the checksum stored with the document."),
                )
                break
    record.status = status
    record.finding = str(finding)[:250]
    record.last_checked_at = timezone.now()
    record.save(update_fields=["status", "finding", "last_checked_at"])
    return record


def _voucher_of(record: ArchiveRecord) -> Document | IncomingInvoice | None:
    model: Any = Document if record.source == ArchiveSource.DOCUMENT else IncomingInvoice
    return model.objects.filter(pk=record.source_id).first()


def register_missing() -> int:
    """Register what has no record: the documents a customer gets and the incoming invoices older than the grace time."""
    count = 0
    known = set(ArchiveRecord.objects.filter(source=ArchiveSource.DOCUMENT).values_list("source_id", flat=True))
    for document in Document.objects.filter(kind__in=CUSTOMER_KINDS).exclude(pk__in=known).iterator():
        register(ArchiveSource.DOCUMENT, document)
        count += 1
    known = set(ArchiveRecord.objects.filter(source=ArchiveSource.INCOMING).values_list("source_id", flat=True))
    cutoff = timezone.now() - GRACE
    for invoice in IncomingInvoice.objects.filter(created_at__lte=cutoff).exclude(pk__in=known).iterator():
        register(ArchiveSource.INCOMING, invoice)
        count += 1
    return count


def due_for_check(*, everything: bool = False) -> QuerySet[ArchiveRecord]:
    """The records the next run checks: the longest unchecked first, so many that all are seen within ``archive_check_days``."""
    records = ArchiveRecord.objects.exclude(status=ArchiveStatus.DELETED).order_by(
        F("last_checked_at").asc(nulls_first=True), "id"
    )
    if everything:
        return records
    total = records.count()
    days = AccountingSettings.load().archive_check_days
    share = max(1, math.ceil(total / max(days, 1)))
    ids = list(records.values_list("pk", flat=True)[:share])
    return ArchiveRecord.objects.filter(pk__in=ids).order_by(F("last_checked_at").asc(nulls_first=True), "id")


def run(*, everything: bool = False) -> Result:
    """Register what is new and check a part (or, with ``everything``, all) of the archive."""
    result = Result(registered=register_missing())
    for record in due_for_check(everything=everything):
        verify(record)
        result.checked += 1
        if record.status == ArchiveStatus.DELETED:
            result.deleted += 1
    result.problems = problems().count()
    return result


def problems() -> QuerySet[ArchiveRecord]:
    """The records whose last check found a file changed or missing."""
    return ArchiveRecord.objects.filter(status__in=[ArchiveStatus.CHANGED, ArchiveStatus.MISSING])


def record_of(source: str, voucher_id: int) -> ArchiveRecord | None:
    """The record of a voucher, if there is one."""
    return ArchiveRecord.objects.filter(source=source, source_id=voucher_id).first()


def guard_deletion(invoice: IncomingInvoice) -> None:
    """Refuse to delete an archived incoming invoice before its retention period ended.

    Raises:
        ValidationError: The invoice is archived and has to be kept until the end of the retention period.
    """
    record = record_of(ArchiveSource.INCOMING, invoice.pk)
    if record is None and invoice.created_at <= timezone.now() - GRACE:
        # not registered yet (the nightly job has not run, or failed): register it now, then the rule below holds
        record = register(ArchiveSource.INCOMING, invoice)
    if record is not None and record.is_retained:
        raise ValidationError(
            _("This invoice is archived and has to be kept until %(date)s (retention).")
            % {"date": record.retain_until.strftime(local_pattern("%d.%m.%Y"))}
        )


def summary() -> dict[str, Any]:
    """Numbers for the page and the API."""
    records = ArchiveRecord.objects
    last = (
        records.exclude(last_checked_at__isnull=True)
        .order_by("-last_checked_at")
        .values_list("last_checked_at", flat=True)
        .first()
    )
    return {
        "total": records.count(),
        "documents": records.filter(source=ArchiveSource.DOCUMENT).count(),
        "incoming": records.filter(source=ArchiveSource.INCOMING).count(),
        "ok": records.filter(status=ArchiveStatus.OK).count(),
        "changed": records.filter(status=ArchiveStatus.CHANGED).count(),
        "missing": records.filter(status=ArchiveStatus.MISSING).count(),
        "deleted": records.filter(status=ArchiveStatus.DELETED).count(),
        "unchecked": records.filter(last_checked_at__isnull=True).count(),
        "last_checked_at": last,
        "pending": IncomingInvoice.objects.exclude(
            pk__in=records.filter(source=ArchiveSource.INCOMING).values("source_id")
        ).count()
        + Document.objects.filter(kind__in=CUSTOMER_KINDS)
        .exclude(pk__in=records.filter(source=ArchiveSource.DOCUMENT).values("source_id"))
        .count(),
    }
