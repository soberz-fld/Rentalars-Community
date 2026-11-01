# SPDX-License-Identifier: GPL-3.0-or-later
"""The export for an audit: tables, vouchers and checksums in one ZIP (DOK-046).

"Datenzugriff" (GoBD Rz. 158 ff.): a tax auditor may ask for the data in a machine-readable form. The ZIP holds

* ``index.xml`` – a description of the tables and columns in the manner of the *Beschreibungsstandard* (GDPdU), so that an
  analysis tool can read the CSV files; **not** checked with an audit program (see the notes of the procedure documentation),
* ``tabellen/*.csv`` – outgoing documents, payments received, incoming invoices, payments made, the lines of the EÜR, the
  asset register and the archive log (UTF-8, ``;``, decimal point),
* ``belege/ausgang/…`` and ``belege/eingang/…`` – the vouchers as stored (PDF, XML),
* ``SHA256SUMS`` – the checksum of every file of the ZIP, and ``LIESMICH.txt``.

The period is a calendar year (vouchers by their date, payments by the day paid) or everything.
"""

from __future__ import annotations

import csv
import datetime
import hashlib
import io
import re
import shutil
import tempfile
import zipfile
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from django.db.models import F, Q, QuerySet
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.core.i18n import local_pattern
from rentalars.core.tables import formula_safe
from rentalars.documents import euer
from rentalars.documents.models import ArchiveRecord, Document, OutgoingPayment
from rentalars.documents.outgoing import CUSTOMER_KINDS
from rentalars.incoming.models import IncomingInvoice, IncomingPayment
from rentalars.material import book_values

# (file name, columns, rows) – the columns are (name, type, description).
Table = tuple[str, list[tuple[str, str, str]], list[list[Any]]]


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "beleg"


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime.datetime):
        return timezone.localtime(value).isoformat(timespec="seconds")
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return str(formula_safe(str(value)) if isinstance(value, str) else value)


def _incoming_in(start: datetime.date, end: datetime.date) -> QuerySet[IncomingInvoice]:
    """The incoming invoices of a period: by the invoice date, else by the day they came in (as the archive does)."""
    # The day of arrival is compared as a moment, not with a date function of the database: MariaDB converts to the local
    # day only when its time-zone tables are loaded, and answers NULL (so: nothing) when they are not.
    first = timezone.make_aware(datetime.datetime.combine(start, datetime.time.min))
    after = timezone.make_aware(datetime.datetime.combine(end + datetime.timedelta(days=1), datetime.time.min))
    return IncomingInvoice.objects.filter(
        Q(invoice_date__range=(start, end)) | Q(invoice_date__isnull=True, created_at__gte=first, created_at__lt=after)
    )


def _period(year: int | None) -> tuple[datetime.date, datetime.date]:
    if year is None:
        return datetime.date(1900, 1, 1), datetime.date(2999, 12, 31)
    return datetime.date(year, 1, 1), datetime.date(year, 12, 31)


def tables(year: int | None) -> list[Table]:
    """The tables of the export."""
    start, end = _period(year)
    documents = (
        Document.objects.filter(kind__in=CUSTOMER_KINDS, issued_on__range=(start, end))
        .select_related("customer", "project")
        .order_by("issued_on", "number")
    )
    out_docs = [
        [
            d.number,
            d.kind,
            d.issued_on,
            d.title,
            d.customer.name if d.customer_id else "",
            d.project.number if d.project_id else "",
            d.net_total,
            d.gross_total,
            d.due_on,
            d.cancels.number if d.cancels_id else "",
            d.sha256,
        ]
        for d in documents
    ]
    out_pay = [
        [p.document.number, p.paid_on, p.amount, p.method, p.reference, p.created_at, p.voided_at or "", p.void_reason]
        for p in OutgoingPayment.objects.filter(paid_on__range=(start, end))
        .select_related("document")
        .order_by("paid_on", "id")
    ]
    invoices = (
        _incoming_in(start, end)
        .select_related("supplier")
        .order_by(F("invoice_date").asc(nulls_last=True), "created_at", "id")
    )
    in_docs = [
        [
            i.pk,
            i.invoice_number,
            i.invoice_date,
            i.supplier_label,
            i.currency,
            format(i.exchange_rate, "f") if i.exchange_rate else "",
            i.total_net,
            i.total_tax,
            i.total_gross,
            i.due_date,
            i.original_name,
        ]
        for i in invoices
    ]
    in_pay = [
        [
            p.invoice_id,
            p.invoice.invoice_number,
            p.paid_on,
            p.amount,
            p.invoice.currency,
            p.method,
            p.reference,
            p.created_at,
            p.voided_at or "",
            p.void_reason,
        ]
        for p in IncomingPayment.objects.filter(paid_on__range=(start, end))
        .select_related("invoice")
        .order_by("paid_on", "id")
    ]
    lines = euer.csv_rows(euer.compute(year)) if year else []
    euer_rows = lines[1:] if lines else []
    assets = [
        [
            r.item.inventory_number,
            str(r.item.material_model),
            r.item.asset_kind,
            r.item.purchase_date,
            r.valued.cost,
            r.valued.accumulated,
            r.valued.book_value,
        ]
        for r in book_values.register(book_values.Filters(year=year))[0]
    ]
    log = [
        [
            a.source,
            a.reference,
            a.voucher_date,
            a.retain_until,
            a.status,
            a.last_checked_at or "",
            a.finding,
            ";".join(f"{f['name']}={f['sha256']}" for f in a.files),
        ]
        for a in ArchiveRecord.objects.order_by("id")
    ]
    return [
        (
            "ausgangsbelege.csv",
            [
                ("Nummer", "text", "Belegnummer"),
                ("Art", "text", "Belegart"),
                ("Datum", "date", "Belegdatum"),
                ("Titel", "text", ""),
                ("Kunde", "text", ""),
                ("Projekt", "text", ""),
                ("Netto", "decimal", ""),
                ("Brutto", "decimal", ""),
                ("Faellig", "date", ""),
                ("Storno_von", "text", ""),
                ("SHA256", "text", "Pruefsumme der PDF"),
            ],
            out_docs,
        ),
        (
            "zahlungen_ausgang.csv",
            [
                ("Rechnung", "text", ""),
                ("Gezahlt_am", "date", ""),
                ("Betrag", "decimal", "brutto, negativ = Rueckzahlung"),
                ("Zahlart", "text", ""),
                ("Verwendungszweck", "text", ""),
                ("Erfasst", "datetime", ""),
                ("Storniert", "datetime", ""),
                ("Stornogrund", "text", ""),
            ],
            out_pay,
        ),
        (
            "eingangsrechnungen.csv",
            [
                ("ID", "text", ""),
                ("Nummer", "text", ""),
                ("Datum", "date", ""),
                ("Lieferant", "text", ""),
                ("Waehrung", "text", ""),
                ("Kurs", "decimal", ""),
                ("Netto", "decimal", ""),
                ("Steuer", "decimal", ""),
                ("Brutto", "decimal", ""),
                ("Faellig", "date", ""),
                ("Datei", "text", ""),
            ],
            in_docs,
        ),
        (
            "zahlungen_eingang.csv",
            [
                ("Rechnung_ID", "text", ""),
                ("Rechnungsnummer", "text", ""),
                ("Gezahlt_am", "date", ""),
                ("Betrag", "decimal", "brutto in der Waehrung der Rechnung"),
                ("Waehrung", "text", ""),
                ("Zahlart", "text", ""),
                ("Verwendungszweck", "text", ""),
                ("Erfasst", "datetime", ""),
                ("Storniert", "datetime", ""),
                ("Stornogrund", "text", ""),
            ],
            in_pay,
        ),
        (
            "euer_buchungen.csv",
            [
                (n, "text", "")
                for n in (
                    "Art",
                    "Tag",
                    "Nummer",
                    "Partei",
                    "Kategorie",
                    "Netto",
                    "Steuer",
                    "Brutto",
                    "Quelle",
                    "Hinweis",
                )
            ],
            euer_rows,
        ),
        (
            "anlagenspiegel.csv",
            [
                ("Inventarnummer", "text", ""),
                ("Modell", "text", ""),
                ("Art", "text", ""),
                ("Anschaffung", "date", ""),
                ("Kosten", "decimal", ""),
                ("Abschreibung_kumuliert", "decimal", ""),
                ("Buchwert", "decimal", ""),
            ],
            assets,
        ),
        (
            "archivprotokoll.csv",
            [
                ("Quelle", "text", ""),
                ("Nummer", "text", ""),
                ("Belegdatum", "date", ""),
                ("Aufbewahren_bis", "date", ""),
                ("Status", "text", ""),
                ("Zuletzt_geprueft", "datetime", ""),
                ("Befund", "text", ""),
                ("Dateien", "text", "Name=SHA-256"),
            ],
            log,
        ),
    ]


def _csv_bytes(columns: list[tuple[str, str, str]], rows: list[list[Any]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow([name for name, _t, _d in columns])
    for row in rows:
        writer.writerow([_text(value) for value in row])
    return buffer.getvalue().encode("utf-8")


def index_xml(items: list[tuple[str, list[tuple[str, str, str]]]]) -> bytes:
    """A description of the tables in the manner of the Beschreibungsstandard (GDPdU); not validated by an audit program."""
    types = {
        "text": "<AlphaNumeric/>",
        "date": "<Date><Format>YYYY-MM-DD</Format></Date>",
        "datetime": "<AlphaNumeric/>",
        "decimal": "<Numeric><AccuracyOrigin>2</AccuracyOrigin></Numeric>",
    }
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<DataSet><Version>1.0</Version><DataSupplier><Name>Rentalars</Name><Location/><Comment>"
        + escape(str(_("Export for an audit")))
        + "</Comment></DataSupplier><Media><Name>1</Name>",
    ]
    for name, columns in items:
        parts.append(
            f"<Table><URL>tabellen/{escape(name)}</URL><Name>{escape(name[:-4])}</Name><Description>{escape(name[:-4])}</Description>"
        )
        parts.append("<UTF8/><DecimalSymbol>.</DecimalSymbol><DigitGroupingSymbol/><Range><From>2</From></Range>")
        parts.append(
            '<VariableLength><ColumnDelimiter>;</ColumnDelimiter><RecordDelimiter>&#13;&#10;</RecordDelimiter><TextEncapsulator>"</TextEncapsulator>'
        )
        for column, kind, description in columns:
            parts.append(
                f"<VariableColumn><Name>{escape(column)}</Name><Description>{escape(description or column)}</Description>{types[kind]}</VariableColumn>"
            )
        parts.append("</VariableLength></Table>")
    parts.append("</Media></DataSet>")
    return "".join(parts).encode("utf-8")


def _read(storage: Any, name: str) -> bytes | None:
    try:
        with storage.open(name, "rb") as handle:
            return handle.read()
    except (OSError, ValueError):
        return None


def build(year: int | None, progress: Callable[[int], None] | None = None) -> tempfile.SpooledTemporaryFile:  # type: ignore[type-arg]
    """The ZIP as a temporary file, rewound; ``year`` ``None``: everything.

    ``progress`` (the task in the background) is called with the percent done, as far as it can be told.
    """
    start, end = _period(year)

    def report(percent: int) -> None:
        if progress is not None:
            progress(percent)

    out = tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024)  # noqa: SIM115 - returned to the caller, which closes it
    sums: list[tuple[str, str]] = []
    missing: list[str] = []

    used: set[str] = set()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:

        def put(path: str, data: bytes) -> None:
            if path in used:  # "A/1" and "A_1" are one name once made safe; neither may shadow the other
                stem, dot, suffix = path.rpartition(".")
                count = 2
                while f"{stem}_{count}{dot}{suffix}" in used:
                    count += 1
                path = f"{stem}_{count}{dot}{suffix}"
            used.add(path)
            archive.writestr(path, data)
            sums.append((hashlib.sha256(data).hexdigest(), path))

        report(5)
        listing = tables(year)
        report(30)
        for name, columns, rows in listing:
            put(f"tabellen/{name}", _csv_bytes(columns, rows))
        put("index.xml", index_xml([(name, columns) for name, columns, _rows in listing]))
        documents = list(
            Document.objects.filter(kind__in=CUSTOMER_KINDS, issued_on__range=(start, end)).order_by("number")
        )
        for position, document in enumerate(documents):
            if position % 25 == 0:
                report(35 + 30 * position // max(len(documents), 1))
            for stored, suffix in (
                (document.file.name, "pdf"),
                (document.xml_file.name if document.xml_file else "", "xml"),
            ):
                if not stored:
                    continue
                data = _read(document.file.storage, stored)
                if data is None:
                    missing.append(stored)
                    continue
                put(f"belege/ausgang/{_safe(document.number)}.{suffix}", data)
        incoming = list(_incoming_in(start, end).order_by("id"))
        for position, invoice in enumerate(incoming):
            if position % 25 == 0:
                report(65 + 30 * position // max(len(incoming), 1))
            for stored in (invoice.file.name, invoice.xml_file.name if invoice.xml_file else ""):
                if not stored:
                    continue
                data = _read(invoice.file.storage, stored)
                if data is None:
                    missing.append(stored)
                    continue
                put(f"belege/eingang/{invoice.pk}_{_safe(stored.rsplit('/', 1)[-1])}", data)
        note = [
            str(
                _("Export for an audit, made by Rentalars on %(date)s.")
                % {"date": timezone.localtime().strftime(local_pattern("%d.%m.%Y %H:%M"))}
            ),
            str(_("Period: %(period)s") % {"period": year if year else _("all")}),
            "",
            str(_("tabellen/ holds the data as CSV (UTF-8, semicolon, decimal point); index.xml describes it.")),
            str(_("belege/ holds the vouchers as stored; SHA256SUMS holds the checksum of every file.")),
            str(_("The description index.xml has not been tested with an audit program.")),
        ]
        if missing:
            note += ["", str(_("Files that could not be read:")), *missing]
        put("LIESMICH.txt", ("\r\n".join(note) + "\r\n").encode("utf-8"))
        archive.writestr("SHA256SUMS", "".join(f"{digest}  {path}\n" for digest, path in sums))
    out.seek(0)
    return out


# --- As a task in the background (DOK-054) ----------------------------------------------------------------------


def year_param(year: int | None) -> str:
    """The period as the task keeps it: the year, or ``"all"``."""
    return "all" if year is None else str(year)


def file_name(year: int | None) -> str:
    """The name of the ZIP."""
    return f"pruefexport-{year if year else 'alle'}.zip"


def start(year: int | None, *, user: Any) -> Any:
    """Make the export as a task in the background; returns the task. The result is for the one who started it."""
    from rentalars.core.jobs import start_job

    title = _("Export for an audit: %(period)s") % {"period": year if year else _("all")}
    return start_job("audit_export", {"year": year_param(year)}, user=user, title=title)


def run_job(job: Any) -> tuple[Path, str]:
    """The task: write the ZIP into a temporary file the task moves into place."""
    from rentalars.core.jobs import report_progress

    raw = str((job.params or {}).get("year", "all"))
    year = None if raw == "all" else euer.parse_year(raw, timezone.localdate().year)
    handle = tempfile.NamedTemporaryFile(prefix="rentalars-audit-", suffix=".zip", delete=False)  # noqa: SIM115
    target = Path(handle.name)
    try:
        with build(year, progress=lambda percent: report_progress(job, percent)) as body:
            shutil.copyfileobj(body, handle)
        handle.close()
    except BaseException:
        handle.close()
        target.unlink(missing_ok=True)
        raise
    return target, file_name(year)
