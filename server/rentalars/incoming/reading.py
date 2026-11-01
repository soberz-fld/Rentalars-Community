# SPDX-License-Identifier: GPL-3.0-or-later
"""Reading an incoming invoice: the text of the file, a proposal from it, and putting the proposal into the invoice (DOK-023, DOK-024).

The requirement: AI recognition of invoice number, date, supplier, price and so on – the same reading as "Kauf einpflegen" (MAT-062,
MAT-076): the text of a PDF with a text layer (:func:`rentalars.material.purchases.invoice_text`; scans and
pictures are not read, there is no text recognition) goes, if the AI is switched on for reading invoices, to the
provider chosen for that (:mod:`rentalars.ai.invoices`) – nowhere else; without it number, date, supplier and totals
are taken from the text by simple patterns.

What comes out is a *proposal*, one dictionary (:func:`proposal_from_text`, :func:`rentalars.ai.invoices.register_proposal`)::

    {"source": "ai"|"text", "supplier": {"name", "id", "existing"}, "invoice_number", "invoice_date", "due_date",
     "currency", "total_net", "total_tax", "total_gross", "note",
     "positions": [{"description", "article_number", "manufacturer", "quantity", "unit_price_net", "tax_rate",
                    "kind" ("goods"|"cost"|"other"), "weight_kg", "serial_numbers", "model_id", "category_id",
                    "product_id", "candidates", "hints"}]}

:func:`apply_proposal` writes it into the invoice: the head fields that are still empty and – for an AI reading –
the positions. The user corrects everything afterwards; nothing is booked in. The functions here are public so that
the import of old projects can read the text of an invoice PDF the same way (read-only).
"""

from __future__ import annotations

import datetime
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.core.money import money
from rentalars.incoming.models import MAX_POSITIONS, IncomingInvoice, InvoicePosition, PositionType, ReadingState
from rentalars.masterdata.models import Supplier
from rentalars.material import purchases
from rentalars.material.models import MaterialModel

#: The words of positions that are ancillary costs, not goods – for a reading that does not say (``kind`` missing).
_ANCILLARY_WORDS = re.compile(
    r"(?i)\b(fracht\w*|versand\w*|transport\w*|porto|speditions?\w*|verpackung\w*|zoll\w*|einfuhr\w*|lieferpauschale|"
    r"liefer(?:ung|kosten)|nachnahme\w*|shipping|freight|packag\w*|packing|postage|handling|customs|delivery charge)\b"
)
_DUE_LABEL = re.compile(
    r"(?i)(?:f(?:ä|ae)llig(?:\s+am|\s+bis)?|zahlbar\s+bis|zahlungsziel|zahlung\s+bis|due\s+date|payment\s+due|due\s+on)"
    r"\s*[:.]?\s*(?P<value>.*)"
)


def looks_like_ancillary(description: str) -> bool:
    """Whether a description names freight, packaging, customs and the like rather than goods."""
    return bool(_ANCILLARY_WORDS.search(description or ""))


def due_date_in(text: str) -> datetime.date | None:
    """The due date after "fällig am", "zahlbar bis", "Zahlungsziel", "due date" in a text; ``None`` if there is none."""
    lines = (text or "").splitlines()
    for index, line in enumerate(lines):
        match = _DUE_LABEL.search(line)
        if match is None:
            continue
        found = purchases._date_in(match["value"] or "") or (
            purchases._date_in(lines[index + 1]) if index + 1 < len(lines) else None
        )
        if found is not None:
            return found
    return None


def text_of(invoice: IncomingInvoice) -> purchases.InvoiceText:
    """The text of the file of an invoice (a PDF with a text layer); the note says if only the first pages were read.

    Raises:
        purchases.InvoiceTextError: The file is no PDF, has no text or cannot be read; ``str(error)`` says why.
    """
    if not invoice.is_pdf:
        raise purchases.InvoiceTextError(
            _("Only PDF files with text can be read. The file is kept all the same – enter the invoice by hand.")
        )
    return purchases.invoice_text(Path(invoice.file.path))


def _to_register(proposal: dict[str, Any], text: str) -> dict[str, Any]:
    """The proposal of ``purchases`` (head only) in the form of this module: due date, tax, no positions."""
    total_net, total_gross = proposal.get("total_net") or "", proposal.get("total_gross") or ""
    tax = ""
    if total_net and total_gross:
        difference = Decimal(total_gross) - Decimal(total_net)
        tax = f"{difference:.2f}" if difference >= 0 else ""
    due = due_date_in(text)
    return {
        "source": "text",
        "supplier": proposal["supplier"],
        "invoice_number": proposal["invoice_number"],
        "invoice_date": proposal["invoice_date"],
        "due_date": due.isoformat() if due else "",
        "currency": proposal.get("currency") or "",
        "total_net": total_net,
        "total_tax": tax,
        "total_gross": total_gross,
        "note": proposal.get("note") or "",
        "positions": [],
    }


def proposal_from_text(text: str) -> dict[str, Any]:
    """The proposal without AI: invoice number, date, due date, a known supplier, the totals and the currency (MAT-062)."""
    return _to_register(purchases.proposal_from_text(text), text)


# --- Putting a proposal into the invoice -----------------------------------------------------------------------


def _decimal(value: Any, places: int | None = None) -> Decimal | None:
    """A decimal from a proposal (text or number); ``None`` if it is none."""
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    if not number.is_finite():
        return None
    return money(number) if places == 2 else number


#: The largest amount the total fields hold (12 digits, 2 of them after the point).
_MAX_TOTAL = Decimal("10000000000")


def _date(value: Any) -> datetime.date | None:
    """A day from a proposal (``YYYY-MM-DD``); ``None`` if it is none."""
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value or ""))
    except ValueError:
        return None


def position_type_of(kind: str, description: str) -> str:
    """The type of a position from what the reading said ("goods", "cost", "other"); by its words if it said nothing."""
    if kind == "cost":
        return PositionType.ANCILLARY
    if kind == "other":
        return PositionType.OTHER
    if kind == "goods":
        return PositionType.GOODS
    return PositionType.ANCILLARY if looks_like_ancillary(description) else PositionType.GOODS


def _position_from(row: dict[str, Any], place: int) -> InvoicePosition:
    """An unsaved position from a row of a proposal; values that do not fit are left empty."""
    quantity = _decimal(row.get("quantity")) or Decimal(1)
    if quantity <= 0 or quantity >= Decimal("1000000"):
        quantity = Decimal(1)
    model_id = row.get("model_id")
    model = MaterialModel.objects.filter(pk=model_id).first() if isinstance(model_id, int) else None
    price = _decimal(row.get("unit_price_net"))
    if price is not None and abs(price) >= Decimal("100000000"):
        price = None
    kind = position_type_of(str(row.get("kind") or ""), str(row.get("description") or ""))
    hints = [str(hint) for hint in (row.get("hints") or [])][:5]
    if price is not None and price < 0 and kind != PositionType.ANCILLARY:
        # Only an ancillary cost can be negative (a discount). Goods with a negative price would
        # fail at booking in without saying why: the price is left empty and the position says so.
        price = None
        hints = [*hints[:4], _("The reading found a negative price for this position; it was left empty. Check it.")]
    rate = _decimal(row.get("tax_rate"))
    weight = _decimal(row.get("weight_kg"))
    return InvoicePosition(
        place=place,
        description=str(row.get("description") or "")[:250],
        article_number=str(row.get("article_number") or "")[:120],
        manufacturer=str(row.get("manufacturer") or "")[:120],
        quantity=quantity.quantize(Decimal("0.001")),
        unit_price_net=price.quantize(Decimal("0.0001")) if price is not None else None,
        tax_rate=rate if rate is not None and 0 <= rate <= 100 else None,
        position_type=kind,
        weight_kg=weight.quantize(Decimal("0.001")) if weight is not None and 0 <= weight < Decimal("100000") else None,
        material_model=model,
        serial_numbers="\n".join(str(serial)[:120] for serial in (row.get("serial_numbers") or []))[:4000],
        suggestion={
            "category_id": row.get("category_id"),
            "product_id": row.get("product_id"),
            "candidates": row.get("candidates") or [],
            "hints": hints,
        },
    )


@transaction.atomic
def apply_proposal(
    invoice: IncomingInvoice,
    proposal: dict[str, Any],
    *,
    replace_positions: bool = False,
    ai: dict[str, Any] | None = None,
    error: str = "",
) -> IncomingInvoice:
    """Put a proposal into an invoice: the empty head fields, and the positions if there are none (or ``replace_positions``).

    What the user typed stays: only fields that are still empty are filled. Positions are replaced only while none of
    them has been booked in; a booked position is never touched. Of the unbooked ones only those the reading made
    itself are replaced: a position a person typed or corrected (``user_edited``) stays, also when the reading ran
    in the background while the person worked (R1-5; DOK-023). A value that does not fit the invoice
    (a total with too many digits) is left out and named in the note of the reading (R1-18).

    Args:
        invoice: The saved invoice.
        proposal: As in the module description.
        replace_positions: Replace the existing unbooked positions by those of the proposal (a new reading).
        ai: Who read it (``model``, ``provider``, ``is_local``) for an AI reading.
        error: What went wrong with the AI, shown with the reading; the proposal is then the one of the text.
    """
    if invoice.pk:
        # Serialise with a person saving the same invoice and start from what is stored now: a reading that took
        # minutes must not overwrite what was typed meanwhile (R1-5).
        fresh = IncomingInvoice.objects.select_for_update().get(pk=invoice.pk)
        for column in invoice._meta.concrete_fields:
            setattr(invoice, column.attname, getattr(fresh, column.attname))
    notes: list[str] = []
    before = {name: getattr(invoice, name) for name in _HEAD_FILLED}
    supplier = proposal.get("supplier") or {}
    if not invoice.supplier_id and not invoice.supplier_name and supplier.get("name"):
        invoice.supplier_name = str(supplier["name"])[:120]
        found = Supplier.objects.filter(pk=supplier["id"]).first() if supplier.get("id") else None
        if found is not None:
            invoice.supplier = found
            invoice.supplier_name = found.name
    if not invoice.invoice_number and proposal.get("invoice_number"):
        invoice.invoice_number = str(proposal["invoice_number"])[:60]
    if invoice.invoice_date is None:
        invoice.invoice_date = _date(proposal.get("invoice_date"))
    if invoice.due_date is None:
        invoice.due_date = _date(proposal.get("due_date"))
    if proposal.get("currency") and not (invoice.reading or {}).get("source"):
        invoice.currency = str(proposal["currency"])[:3].upper()  # the first reading names it; later ones leave it
    for name in ("total_net", "total_tax", "total_gross"):
        if getattr(invoice, name) is None:
            value = _decimal(proposal.get(name), 2)
            if value is not None and abs(value) >= _MAX_TOTAL:
                value = None
                notes.append(_("An amount of the invoice is too large to be right: it was left empty."))
            setattr(invoice, name, value)
    invoice.reading = {
        "source": proposal.get("source") or "",
        "ai": ai,
        "error": error,
        "note": proposal.get("note") or "",
        "at": timezone.now().isoformat(),
    }
    if proposal.get("einvoice"):
        invoice.reading["einvoice"] = proposal["einvoice"]  # What the file says about itself
    invoice.reading_state = ReadingState.DONE
    try:
        invoice.full_clean(exclude=["file"])
    except ValidationError as failed:
        # A value of the reading that does not fit is left out; what a person typed is never touched here.
        for name in failed.message_dict:
            if name in before:
                setattr(invoice, name, before[name])
                notes.append(_("A value of the reading did not fit (%(field)s) and was left out.") % {"field": name})
        invoice.full_clean(exclude=["file"])
    if notes:
        invoice.reading["note"] = " ".join(part for part in (invoice.reading["note"], *notes) if part)
    invoice.save()
    rows = proposal.get("positions") or []
    if rows and (replace_positions or not invoice.positions.exists()):
        if not invoice.positions.filter(items__isnull=False).exists():
            cut = _replace_positions(invoice, rows)
            if cut:
                message = _(
                    "The invoice has more positions than fit (%(max)d): %(count)d were left out. "
                    "Discounts and surcharges are kept; check the sums."
                ) % {"max": MAX_POSITIONS, "count": cut}
                invoice.reading["note"] = " ".join(part for part in (invoice.reading.get("note", ""), message) if part)
                invoice.save(update_fields=["reading"])
    return invoice


#: The fields of the head a reading fills when they are empty.
_HEAD_FILLED = (
    "supplier",
    "supplier_name",
    "invoice_number",
    "invoice_date",
    "due_date",
    "currency",
    "total_net",
    "total_tax",
    "total_gross",
)


def _same_position(position: InvoicePosition, other: InvoicePosition) -> bool:
    """Whether a position of the reading is one a person has already (same article number, else same description)."""
    if position.article_number and position.article_number.strip().lower() == other.article_number.strip().lower():
        return True
    return " ".join(position.description.lower().split()) == " ".join(other.description.lower().split())


def _replace_positions(invoice: IncomingInvoice, rows: list[dict[str, Any]]) -> int:
    """Put the positions of a reading into the invoice, keeping every position a person typed or corrected.

    Only positions the reading itself made and nobody touched (``user_edited`` false) are replaced. A row of the
    reading that matches a kept position is not added a second time (R1-5; DOK-023). A kept position
    stands for **one** row of the reading: two rows with the same article number or text are two positions, so a row
    is not lost because its twin was corrected. If there is no room for all rows, discounts and
    surcharges are kept first.

    Returns:
        How many rows were left out for lack of room.
    """
    for old_position in list(invoice.positions.filter(user_edited=False)):
        old_position.delete()
    kept = list(invoice.positions.all())
    place = max((position.place for position in kept), default=0)
    room = MAX_POSITIONS - len(kept)
    free = list(kept)  # each kept position takes over one row only
    created: list[tuple[InvoicePosition, bool]] = []
    for row in rows:
        if not row.get("description"):
            continue
        position = _position_from(row, place + 1)
        twin = next((other for other in free if _same_position(position, other)), None)
        if twin is not None:
            free.remove(twin)
            continue
        place += 1
        created.append((position, bool(row.get("charge"))))
    room = max(room, 0)
    cut = max(len(created) - room, 0)
    if cut:
        lines = [entry for entry in created if not entry[1]]
        for entry in lines[len(lines) - cut :] if cut <= len(lines) else lines:
            created.remove(entry)
        created = created[:room]
    for position, _charge in created:
        position.invoice = invoice
        position.save()
    return cut
