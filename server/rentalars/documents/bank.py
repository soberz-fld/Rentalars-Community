# SPDX-License-Identifier: GPL-3.0-or-later
"""Bank statement import with suggestions for matching payments (DOK-050).

The requirement: import of bank statements (CAMT.053, CSV) with suggestions for matching them to open items.

What is read
------------
* **CAMT.053** (ISO 20022 account statement, any version ``camt.053.001.xx``): every booked entry (``Ntry``) – day, amount
  with the sign of ``CdtDbtInd``, counterparty, its IBAN, purpose, end-to-end ID. An entry with several transactions that
  each name their amount is split.
* **CSV** as banks export it: the delimiter (``;`` ``,`` tab) and the encoding (UTF-8, else Windows-1252) are detected, lines
  before the header row are skipped, the columns are found by their usual German and English names.

XML with a document type declaration or entities is refused, like in the e-invoice reader. Nothing is stored of the file but
its checksum and the transactions: the same file is not read twice, and a transaction that an earlier, overlapping statement
held is not entered again (``fingerprint``).

What is suggested – and what never happens
------------------------------------------
For a transaction :func:`suggestions` ranks the open items it could belong to by what the transaction says:

* the **number** of the invoice in the purpose (the strongest sign),
* the **amount** equal to what is still open,
* the **name** of the customer or supplier.

Money in goes to an outgoing invoice (a customer pays) or to a credit balance with a supplier (a supplier pays back); money out
to an incoming invoice or to a credit balance with a customer (a refund). A suggestion is only a suggestion: the payment is
entered by a person with the right to do it (:func:`book`), with the usual rules of payments – and can be voided like any
other, which opens the transaction again.
"""

from __future__ import annotations

import csv
import datetime
import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Level, Module
from rentalars.core.audit import record_event
from rentalars.core.payment_base import PaymentMethod
from rentalars.core.tax_split import cents
from rentalars.documents import outgoing
from rentalars.documents import payments as outgoing_payments
from rentalars.documents.models import BankImport, BankTransaction
from rentalars.incoming import payments as incoming_payments
from rentalars.incoming.einvoice import EInvoiceError, _root_of
from rentalars.material.purchases import parse_amount

#: The largest file taken and the most transactions in one file.
MAX_BYTES = 8_000_000
MAX_ROWS = 20_000
#: Elements of a CAMT file: a statement with 20,000 entries has some 25 elements each.
MAX_XML_ELEMENTS = 1_000_000
#: The column holds 12 digits with 2 after the point.
MAX_AMOUNT = Decimal("1e10")
FORMAT_CAMT = "camt053"
FORMAT_CSV = "csv"

OUTGOING = "outgoing"  # a payment at an outgoing invoice
INCOMING = "incoming"  # a payment at an incoming invoice


def may_use(rights: Any) -> bool:
    """Whether the bank page is open to these rights: it shows both sides of the books, so both price rights and all projects."""
    from rentalars.incoming import access

    return outgoing.may_see(rights) and access.may_see(rights)


def may_change(rights: Any) -> bool:
    """Whether statements may be read in and transactions booked or set aside: both sides may enter payments."""
    from rentalars.incoming import access

    return may_use(rights) and rights.level_everywhere(Module.PROJECTS) >= Level.WRITE and access.may_change(rights)


class BankFileError(Exception):
    """The file is no bank statement we can read; ``str(error)`` says why, for the person."""


@dataclass
class Row:
    """One transaction as the file has it."""

    booked_on: datetime.date
    amount: Decimal
    currency: str = "EUR"
    counterparty: str = ""
    counterparty_iban: str = ""
    purpose: str = ""
    end_to_end_id: str = ""
    #: The own account the row belongs to – part of the fingerprint, so equal rows of two accounts stay two.
    account_iban: str = ""


@dataclass
class Statement:
    """What a file held."""

    file_format: str
    iban: str = ""
    rows: list[Row] = field(default_factory=list)


# --- CAMT.053 -----------------------------------------------------------------------------------------------------


def _name(element: ET.Element) -> str:
    """The tag without its namespace."""
    return element.tag.rsplit("}", 1)[-1]


def _child(element: ET.Element | None, *path: str) -> ET.Element | None:
    """The first element along a path of local names, ignoring namespaces."""
    current = element
    for step in path:
        if current is None:
            return None
        current = next((c for c in current if _name(c) == step), None)
    return current


def _children(element: ET.Element | None, name: str) -> list[ET.Element]:
    return [] if element is None else [c for c in element if _name(c) == name]


def _text_of(element: ET.Element | None, *path: str) -> str:
    found = _child(element, *path)
    return " ".join((found.text or "").split()) if found is not None else ""


def _iso_day(text: str) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(text[:10])
    except ValueError:
        return None


def _camt_amount(element: ET.Element | None) -> tuple[Decimal, str] | None:
    """The amount of an ``Amt`` element and its currency; ``None`` if there is none or it is no number."""
    if element is None or not (element.text or "").strip():
        return None
    try:
        value = Decimal(element.text.strip())
    except ArithmeticError:
        return None
    if not value.is_finite() or abs(value) >= MAX_AMOUNT:
        return None
    return value, (element.get("Ccy") or "EUR").upper()[:3]


def _camt_party(details: ET.Element | None, credit: bool) -> tuple[str, str]:
    """Name and IBAN of the other side: the debtor if money came in, else the creditor."""
    side, account = ("Dbtr", "DbtrAcct") if credit else ("Cdtr", "CdtrAcct")
    related = _child(details, "RltdPties")
    # camt.053.001.08 and later put the name one level down (Dbtr/Pty/Nm); older versions have Dbtr/Nm.
    name = _text_of(related, side, "Nm") or _text_of(related, side, "Pty", "Nm")
    return name, _text_of(related, account, "Id", "IBAN")


def _camt_rows(entry: ET.Element, booked_on: datetime.date) -> list[Row]:
    credit = _text_of(entry, "CdtDbtInd").upper() == "CRDT"
    # The movement of the account is CdtDbtInd alone. A reversal (RvslInd) is an entry of its own that moves the money back –
    # a returned direct debit is a debit with RvslInd true – so the flag does not turn the sign.
    sign = Decimal(1) if credit else Decimal(-1)
    total = _camt_amount(_child(entry, "Amt"))
    if total is None:
        raise BankFileError(_("An entry of the statement has no valid amount."))
    details_list = [d for block in _children(entry, "NtryDtls") for d in _children(block, "TxDtls")]
    split = [d for d in details_list if _camt_amount(_child(d, "AmtDtls", "TxAmt", "Amt")) is not None]
    if len(details_list) > 1 and len(split) == len(details_list):
        parts = [(d, *_camt_amount(_child(d, "AmtDtls", "TxAmt", "Amt"))) for d in split]  # type: ignore[misc]
    else:
        parts = [(details_list[0] if len(details_list) == 1 else None, *total)]
    rows: list[Row] = []
    for details, amount, currency in parts:
        purpose = " ".join(
            filter(None, (" ".join((u.text or "").split()) for u in _children(_child(details, "RmtInf"), "Ustrd")))
        )
        if not purpose:
            purpose = _text_of(entry, "AddtlNtryInf")
        name, iban = _camt_party(details, credit)
        end_to_end = _text_of(details, "Refs", "EndToEndId")
        rows.append(
            Row(
                booked_on,
                cents(sign * amount),
                currency,
                name[:200],
                iban.replace(" ", "")[:42],
                purpose[:500],
                "" if end_to_end.upper() == "NOTPROVIDED" else end_to_end[:140],
            )
        )
    return rows


def parse_camt(data: bytes) -> Statement:
    """Read a CAMT.053 statement (several accounts in one file: all their entries; the first IBAN is kept)."""
    head = data.upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in head:
        raise BankFileError(
            _(
                "The XML contains a document type declaration or entities. A bank statement has none; the file is not read."
            )
        )
    try:
        root = _root_of(data, max_elements=MAX_XML_ELEMENTS)
    except EInvoiceError as error:
        raise BankFileError(str(error)) from error
    if _name(root) != "Document" or "camt.053" not in root.tag:
        raise BankFileError(_("The XML is not a CAMT.053 account statement."))
    statement = Statement(FORMAT_CAMT)
    for message in root:
        for account_statement in _children(message, "Stmt"):
            iban = _text_of(account_statement, "Acct", "Id", "IBAN").replace(" ", "")
            statement.iban = statement.iban or iban
            for entry in _children(account_statement, "Ntry"):
                status = _text_of(entry, "Sts") or _text_of(entry, "Sts", "Cd")
                if status and status.upper() not in {"BOOK", "BOOKED"}:
                    continue  # pending or information entries are not on the account yet
                day = _iso_day(_text_of(entry, "BookgDt", "Dt") or _text_of(entry, "BookgDt", "DtTm"))
                day = day or _iso_day(_text_of(entry, "ValDt", "Dt"))
                if day is None:
                    raise BankFileError(_("An entry of the statement has no booking day."))
                for row in _camt_rows(entry, day):
                    row.account_iban = iban
                    statement.rows.append(row)
                if len(statement.rows) > MAX_ROWS:
                    raise BankFileError(_("The statement has too many transactions."))
    statement.rows = [row for row in statement.rows if row.amount != 0]  # an entry of 0.00 moves nothing
    if not statement.rows:
        raise BankFileError(_("The statement holds no booked transactions."))
    return statement


# --- CSV ----------------------------------------------------------------------------------------------------------

_COLUMNS = {
    "day": ("buchungstag", "buchungsdatum", "buchung", "datum", "booking date", "date", "bookingdate", "valuta"),
    "amount": ("betrag", "betrag (eur)", "umsatz", "amount", "betrag in eur"),
    "name": (
        "name zahlungsbeteiligter",
        "beguenstigter/zahlungspflichtiger",
        "begünstigter/zahlungspflichtiger",
        "zahlungsempfänger",
        "auftraggeber/zahlungsempfänger",
        "auftraggeber / begünstigter",
        "name",
        "counterparty",
        "payee",
        "zahlungspflichtiger",
        "empfänger",
    ),
    "iban": ("iban zahlungsbeteiligter", "kontonummer/iban", "iban", "iban/kontonummer", "counterparty iban"),
    "purpose": ("verwendungszweck", "buchungstext", "purpose", "reference", "betreff", "description"),
    "currency": ("währung", "waehrung", "currency", "ccy"),
    #: The own account of the row, where a bank names it (Sparkasse: "Auftragskonto").
    "account": ("auftragskonto", "iban auftragskonto", "konto-iban", "own iban", "account"),
    "end_to_end": (
        "kundenreferenz (end-to-end)",
        "end-to-end-referenz",
        "kundenreferenz",
        "end to end id",
        "endtoendid",
    ),
}
_DAY_FORMATS = ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y")


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise BankFileError(_("The file is not text."))  # pragma: no cover - cp1252 decodes nearly every byte


def _day(text: str) -> datetime.date | None:
    """A day as banks write it: ``01.03.2027``, ``01.03.27``, ``2027-03-01``, with a time after it if any."""
    text = text.strip()
    for part in (text, text.replace("T", " ").split(" ")[0]):
        for pattern in _DAY_FORMATS:
            try:
                return datetime.datetime.strptime(part, pattern).date()
            except ValueError:
                continue
    return None


def _csv_amount(text: str) -> Decimal | None:
    """An amount as banks write it: ``-12,50``, ``1.291,50``, ``12,50-`` and ``12,50 S`` (debit) / ``12,50 H`` (credit)."""
    text = text.strip()
    sign = Decimal(1)
    if re.search(r"\d\s*[SH]$", text):
        sign = Decimal(-1) if text[-1] == "S" else Decimal(1)
        text = text[:-1].strip()
    if text.endswith("-"):
        text = "-" + text[:-1].strip()
    value = parse_amount(text)
    if value is None or abs(value) >= MAX_AMOUNT:
        return None
    return sign * value


def _header_map(cells: list[str]) -> dict[str, int]:
    """Which column holds what, by the usual names; empty unless day and amount are both found."""
    names = [c.strip().strip('"').lower() for c in cells]
    found: dict[str, int] = {}
    for key, aliases in _COLUMNS.items():
        for alias in aliases:  # earlier aliases are the more specific ones
            if alias in names:
                found[key] = names.index(alias)
                break
    return found if "day" in found and "amount" in found else {}


def _find_table(lines: list[str]) -> tuple[list[list[str]], int, dict[str, int]]:
    """The rows split by the delimiter that shows a header row, the place of the header and its columns.

    The delimiter is the one under which a header row is found – ``;`` first, as German banks use it – and not the one that
    occurs most: a purpose with commas must not decide it.
    """
    for delimiter in (";", "\t", ",", "|"):
        rows = list(csv.reader(lines, delimiter=delimiter))
        for index, row in enumerate(rows):
            if columns := _header_map(row):
                return rows, index, columns
    raise BankFileError(_("No header row found. The file needs at least a column for the day and one for the amount."))


def parse_csv(data: bytes) -> Statement:
    """Read the CSV export of a bank.

    Rows before the header and rows that are no transactions (a closing balance: no date in the day column, or no amount)
    are skipped. A row with a date-like day cell and an amount cell that cannot be read is **not** skipped: the file is
    refused with the number of the line, so that no transaction is lost silently.
    """
    text = _decode(data)
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise BankFileError(_("The file is empty."))
    reader, header_at, columns = _find_table(lines)
    statement = Statement(FORMAT_CSV)

    def cell(row: list[str], key: str) -> str:
        index = columns.get(key)
        return row[index].strip() if index is not None and index < len(row) else ""

    for number, row in enumerate(reader[header_at + 1 :], start=header_at + 2):
        day_text, amount_text = cell(row, "day"), cell(row, "amount")
        if not amount_text or not any(ch.isdigit() for ch in day_text):
            continue  # a blank line, a closing balance ("Kontostand"), a note
        day, amount = _day(day_text), _csv_amount(amount_text)
        if day is None or amount is None:
            raise BankFileError(
                _("Line %(number)d of the file cannot be read (day “%(day)s”, amount “%(amount)s”).")
                % {"number": number, "day": day_text[:30], "amount": amount_text[:30]}
            )
        iban = cell(row, "iban").replace(" ", "")
        statement.rows.append(
            Row(
                day,
                cents(amount),
                (cell(row, "currency") or "EUR").upper()[:3],
                cell(row, "name")[:200],
                iban[:42] if re.fullmatch(r"[A-Za-z]{2}\d{2}[A-Za-z0-9]{10,30}", iban) else "",
                cell(row, "purpose")[:500],
                cell(row, "end_to_end")[:140],
                cell(row, "account").replace(" ", "")[:42],
            )
        )
        if len(statement.rows) > MAX_ROWS:
            raise BankFileError(_("The statement has too many transactions."))
    statement.rows = [row for row in statement.rows if row.amount != 0]
    if not statement.rows:
        raise BankFileError(_("The file holds no transactions."))
    statement.iban = next((row.account_iban for row in statement.rows if row.account_iban), "")
    return statement


def parse(data: bytes, name: str = "") -> Statement:
    """Read a bank file; CAMT.053 or CSV by what it looks like."""
    if len(data) > MAX_BYTES:
        raise BankFileError(_("The file is too large."))
    if data.lstrip(b"\xef\xbb\xbf \r\n\t")[:1] == b"<":
        return parse_camt(data)
    return parse_csv(data)


# --- Reading in ---------------------------------------------------------------------------------------------------


def _fingerprints(statement: Statement) -> list[str]:
    """One per row; the same row twice in a file gets a counter, so real repeats are not taken for duplicates."""
    seen: dict[str, int] = {}
    result = []
    for row in statement.rows:
        key = "|".join(
            (
                row.account_iban or statement.iban,
                row.booked_on.isoformat(),
                str(row.amount),
                row.currency,
                row.counterparty_iban,
                row.end_to_end_id,
                " ".join(row.purpose.lower().split()),
            )
        )
        index = seen.get(key, 0)
        seen[key] = index + 1
        result.append(hashlib.sha256(f"{key}|{index}".encode()).hexdigest())
    return result


@transaction.atomic
def import_file(data: bytes, name: str, *, user: Any = None) -> BankImport:
    """Read a bank file in. Raises ``BankFileError`` (no statement) or ``ValidationError`` (read in before)."""
    checksum = hashlib.sha256(data).hexdigest()
    if BankImport.objects.filter(sha256=checksum).exists():
        raise ValidationError(_("This file was read in before."))
    statement = parse(data, name)
    prints = _fingerprints(statement)
    known = set(BankTransaction.objects.filter(fingerprint__in=prints).values_list("fingerprint", flat=True))
    days = [r.booked_on for r in statement.rows]
    try:
        with transaction.atomic():
            created = BankImport.objects.create(
                name=name[:200] or "statement",
                sha256=checksum,
                file_format=statement.file_format,
                account_iban=statement.iban[:42],
                first_day=min(days),
                last_day=max(days),
                imported_by=user if getattr(user, "is_authenticated", False) else None,
            )
    except IntegrityError as error:  # the same file read in at the same moment by somebody else
        raise ValidationError(_("This file was read in before.")) from error
    new = [
        BankTransaction(
            bank_import=created,
            booked_on=row.booked_on,
            amount=row.amount,
            currency=row.currency,
            counterparty=row.counterparty,
            counterparty_iban=row.counterparty_iban,
            purpose=row.purpose,
            end_to_end_id=row.end_to_end_id,
            fingerprint=fingerprint,
        )
        for row, fingerprint in zip(statement.rows, prints, strict=True)
        if fingerprint not in known
    ]
    try:
        with transaction.atomic():
            BankTransaction.objects.bulk_create(new)
    except IntegrityError as error:  # pragma: no cover - two imports at the same moment
        raise ValidationError(_("This file was read in before.")) from error
    created.new_count = len(new)
    created.skipped_count = len(statement.rows) - len(new)
    created.save(update_fields=["new_count", "skipped_count"])
    record_event(created, "bank.imported", {"name": created.name, "new": created.new_count})
    return created


# --- Suggestions --------------------------------------------------------------------------------------------------

#: Scores: the number of the invoice in the purpose, the amount, the name; a suggestion needs at least this much.
SCORE_NUMBER = 60
SCORE_AMOUNT = 30
SCORE_NAME = 15
MINIMUM_SCORE = 30
#: A number shorter than this (letters and digits) is not searched for in the purpose.
MIN_NUMBER_LENGTH = 3
#: …and a number of digits only needs this many.
MIN_DIGITS_ONLY = 5
MAX_SUGGESTIONS = 5


@dataclass(frozen=True)
class Candidate:
    """An open item a transaction could be matched to."""

    side: str  # OUTGOING or INCOMING
    target: Any  # Document or IncomingInvoice
    number: str
    party: str
    #: What is still open, in the direction of the money: positive for something to receive or to pay, negative for a credit.
    remaining: Decimal
    #: The amount of the payment to enter for it (the sign convention of payments).
    credit: bool


@dataclass(frozen=True)
class Suggestion:
    """A candidate with its score, the payment amount that would be entered, and why it was suggested."""

    candidate: Candidate
    score: int
    amount: Decimal
    reasons: tuple[str, ...]

    @property
    def side(self) -> str:
        """Outgoing or incoming."""
        return self.candidate.side

    @property
    def target(self) -> Any:
        """The invoice."""
        return self.candidate.target


def _normal(text: str) -> str:
    return re.sub(r"[^a-z0-9äöüß]+", "", text.lower())


def number_in(text: str, number: str) -> bool:
    """Whether the invoice ``number`` stands in ``text`` as a whole number, whatever separators it is written with.

    ``RE-2027-0001`` is found in "Rechnung RE 2027 0001" and "RE20270001", but ``R4711`` is not found in "XR4711": the number
    must neither continue a longer run of letters and digits before it nor after it, and a number made of digits only is
    not found inside a date or an amount ("03/2027" in "01.03.2027", "119" in "119,00"). A number with fewer than three
    letters and digits, or digits only and fewer than five, says too little to be searched for.
    """
    chunks = re.findall(r"[a-z0-9äöüß]+", number.lower())
    plain = _normal(number)
    digits_only = plain.isdigit()
    if len(plain) < MIN_NUMBER_LENGTH or (digits_only and len(plain) < MIN_DIGITS_ONLY):
        return False
    alnum = r"[a-z0-9äöüß]"
    pattern = rf"(?<!{alnum})" + r"[^a-z0-9äöüß]*".join(re.escape(c) for c in chunks) + rf"(?!{alnum})"
    if digits_only:  # not the end of a longer number with a decimal point or comma, not the start of one
        pattern = r"(?<![0-9][.,])" + pattern + r"(?![.,][0-9])"
    return re.search(pattern, text.lower()) is not None


_NOISE = frozenset({"gmbh", "mbh", "gbr", "kommanditgesellschaft", "stiftung", "verein"})


def _words(text: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9äöüß]+", text.lower()) if len(w) >= 4 and w not in _NOISE}


def load_candidates() -> list[Candidate]:
    """Everything a transaction could belong to, read once for a whole page: open items and credit balances."""
    result: list[Candidate] = []
    for document, found in outgoing_payments.open_items():
        result.append(
            Candidate(
                OUTGOING,
                document,
                document.number,
                document.customer.name if document.customer_id else "",
                found.remaining,
                False,
            )
        )
    for document, found in outgoing_payments.credit_items():
        result.append(
            Candidate(
                OUTGOING,
                document,
                document.number,
                document.customer.name if document.customer_id else "",
                found.remaining,
                True,
            )
        )
    for invoice, found in incoming_payments.open_items():
        if invoice.currency != "EUR":
            continue  # the rest is in the currency of the invoice; a booking in euro cannot be compared with it
        result.append(
            Candidate(INCOMING, invoice, invoice.invoice_number, invoice.supplier_label, found.remaining, False)
        )
    for invoice, found in incoming_payments.credit_items():
        if invoice.currency != "EUR":
            continue
        result.append(
            Candidate(INCOMING, invoice, invoice.invoice_number, invoice.supplier_label, found.remaining, True)
        )
    return result


def _fits_direction(transaction_amount: Decimal, candidate: Candidate) -> bool:
    """Money in: a customer pays an invoice, or a supplier pays a credit back. Money out: the reverse."""
    money_in = transaction_amount > 0
    if candidate.side == OUTGOING:
        return money_in != candidate.credit
    return money_in == candidate.credit


def payment_amount(transaction_amount: Decimal, candidate: Candidate) -> Decimal:
    """The amount of the payment to enter: the sign convention of payments (a refund is a negative payment)."""
    # outgoing invoice: money in is a payment (+), money out a refund (-); incoming: money out is a payment (+), money in a refund (-)
    return transaction_amount if candidate.side == OUTGOING else -transaction_amount


def suggestions(tx: BankTransaction, candidates: list[Candidate]) -> list[Suggestion]:
    """The open items the transaction may belong to, best first; none if it says too little."""
    if tx.currency != "EUR" or tx.amount == 0:
        return []
    text = f"{tx.purpose} {tx.end_to_end_id}"
    words = _words(tx.counterparty)
    found: list[Suggestion] = []
    for candidate in candidates:
        if not _fits_direction(tx.amount, candidate):
            continue
        score, reasons = 0, []
        if number_in(text, candidate.number):
            score += SCORE_NUMBER
            reasons.append(_("The number is in the purpose."))
        if abs(candidate.remaining) == abs(tx.amount):
            score += SCORE_AMOUNT
            reasons.append(_("The amount is what is still open."))
        if words & _words(candidate.party):
            score += SCORE_NAME
            reasons.append(_("The name fits."))
        if score >= MINIMUM_SCORE:
            found.append(Suggestion(candidate, score, payment_amount(tx.amount, candidate), tuple(reasons)))
    found.sort(key=lambda s: (-s.score, s.candidate.number))
    return found[:MAX_SUGGESTIONS]


# --- Booking, ignoring ---------------------------------------------------------------------------------------------


def _locked(tx: BankTransaction) -> BankTransaction:
    return (
        BankTransaction.objects.select_for_update().select_related("outgoing_payment", "incoming_payment").get(pk=tx.pk)
    )


def _check_direction(tx: BankTransaction, side: str, target: Any, found: Any) -> None:
    """Refuse a booking that goes against the invoice: the suggestions never offer it, a hand-made request must not do it."""
    if found is None:
        return  # an incoming invoice without totals: ``record`` says what is missing
    candidate = Candidate(side, target, "", "", found.remaining, found.remaining < 0)
    if not _fits_direction(tx.amount, candidate):
        raise ValidationError(
            _(
                "The money goes the wrong way for this invoice: money received belongs to an invoice a customer has to pay "
                "or to a credit of a supplier, money paid to an invoice to pay or a refund to a customer. If it is right, "
                "enter the payment by hand at the invoice."
            )
        )


@transaction.atomic
def book(tx: BankTransaction, side: str, target_pk: int, *, user: Any = None) -> BankTransaction:
    """Enter the payment for a transaction at an invoice and link the two. Only a person calls this.

    A transaction is booked as a whole; a part payment is entered by hand at the invoice. Booking again after the payment
    was voided is possible: the transaction is open then.

    Raises:
        ValidationError: The transaction is not open, or the payment is refused (a future day, an invoice without totals …).
    """
    from rentalars.documents.models import Document
    from rentalars.incoming.models import IncomingInvoice

    tx = _locked(tx)
    if tx.state != "open":
        raise ValidationError(_("This transaction is booked or ignored already."))
    if tx.currency != "EUR":
        raise ValidationError(_("Only transactions in euro can be booked."))
    reference = (tx.end_to_end_id or tx.purpose)[:200]
    note = _("From the bank statement %(name)s") % {"name": tx.bank_import.name}
    tx.outgoing_payment = tx.incoming_payment = None
    if side == OUTGOING:
        document = Document.objects.filter(pk=target_pk).first()
        if document is None:
            raise ValidationError(_("The invoice does not exist."))
        _check_direction(tx, side, document, outgoing_payments.balance(document))
        tx.outgoing_payment = outgoing_payments.record(
            document, paid_on=tx.booked_on, amount=tx.amount, method=PaymentMethod.TRANSFER,
            reference=reference, note=note, user=user,
        )  # fmt: skip
    elif side == INCOMING:
        invoice = IncomingInvoice.objects.filter(pk=target_pk).first()
        if invoice is None:
            raise ValidationError(_("The invoice does not exist."))
        if invoice.currency != "EUR":
            raise ValidationError(_("Only invoices in euro can be matched. Enter the payment by hand at the invoice."))
        _check_direction(tx, side, invoice, incoming_payments.balance(invoice))
        tx.incoming_payment = incoming_payments.record(
            invoice, paid_on=tx.booked_on, amount=-tx.amount, method=PaymentMethod.TRANSFER,
            reference=reference, note=note, user=user,
        )  # fmt: skip
    else:
        raise ValidationError(_("Unknown side."))
    tx.matched_at = timezone.now()
    tx.matched_by = user if getattr(user, "is_authenticated", False) else None
    tx.save()
    return tx


@transaction.atomic
def ignore(tx: BankTransaction, *, reason: str, user: Any = None) -> BankTransaction:
    """Set a transaction aside (a private booking, a fee …); it stays in the list, with the reason."""
    tx = _locked(tx)
    if tx.state != "open":
        raise ValidationError(_("This transaction is booked or ignored already."))
    reason = reason.strip()
    if not reason:
        raise ValidationError({"reason": _("Say why the transaction is ignored.")})
    tx.ignored_at = timezone.now()
    tx.ignored_by = user if getattr(user, "is_authenticated", False) else None
    tx.ignore_reason = reason[:250]
    tx.save()
    return tx


@transaction.atomic
def restore(tx: BankTransaction) -> BankTransaction:
    """Take an ignored transaction back into the open ones."""
    tx = _locked(tx)
    if tx.ignored_at is None:
        raise ValidationError(_("This transaction is not ignored."))
    tx.ignored_at = None
    tx.ignored_by = None
    tx.ignore_reason = ""
    tx.save()
    return tx
