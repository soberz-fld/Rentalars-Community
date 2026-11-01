# SPDX-License-Identifier: GPL-3.0-or-later
"""Business logic of the incoming invoices: upload, head, positions, status, supplier, deleting (DOK-023, DOK-024).

Browser views and API views both call these functions (API-002); the rights are checked by them
(:mod:`rentalars.incoming.access`).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from rentalars.core.pictures import open_picture
from rentalars.core.uploads import max_upload_bytes
from rentalars.incoming import einvoice, reading
from rentalars.incoming.models import (
    MAX_POSITIONS,
    AllocationKey,
    IncomingInvoice,
    InvoicePosition,
    InvoiceStatus,
    PositionType,
    ReadingState,
)
from rentalars.masterdata.models import Supplier
from rentalars.material import purchases
from rentalars.material import services as material_services
from rentalars.material.models import MaterialItem

#: The file types of an invoice: a PDF with text can be read, a picture is only kept; an XML e-invoice
#: (XRechnung, ZUGFeRD / Factur-X as XML) is read exactly, a PDF with an XML attached as well.
INVOICE_EXTENSIONS = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".webp", ".xml"})
#: The formats a picture may really have – decided by its content, not by its name.
PICTURE_FORMATS = frozenset({"PNG", "JPEG", "WEBP"})

#: The fields of the head that may be changed.
HEAD_FIELDS = (
    "supplier_name",
    "invoice_number",
    "invoice_date",
    "due_date",
    "currency",
    "exchange_rate",
    "total_net",
    "total_tax",
    "total_gross",
    "allocation_key",
    "note",
)
#: The fields of a position that may be changed.
POSITION_FIELDS = (
    "description",
    "article_number",
    "manufacturer",
    "quantity",
    "unit_price_net",
    "tax_rate",
    "tax_account",
    "position_type",
    "asset_kind",
    "useful_life_months",
    "weight_kg",
    "serial_numbers",
    "material_model",
)
#: What cannot change at a position that is booked in: the items were made with these.
LOCKED_WHEN_BOOKED = ("quantity", "unit_price_net", "position_type")


# --- The file ----------------------------------------------------------------------------------------------------


def validate_invoice_file(uploaded: Any) -> None:
    """Accept a PDF, a picture (PNG, JPEG, WEBP) or an XML e-invoice up to the configured size; the content must be what the name says.

    An XML must be an e-invoice we can read (UBL or CII, without a DTD): other XML is of no use as a document.

    Raises:
        ValidationError: The type is not accepted, the file is too large or empty, or it is not what its name says.
    """
    name = getattr(uploaded, "name", "") or ""
    extension = Path(name).suffix.lower()
    if extension not in INVOICE_EXTENSIONS:
        raise ValidationError(
            _("An invoice is a PDF, a picture or an XML e-invoice: %(types)s.")
            % {"types": ", ".join(sorted(INVOICE_EXTENSIONS))}
        )
    size = getattr(uploaded, "size", 0) or 0
    if size <= 0:
        raise ValidationError(_("The file is empty."))
    limit = max_upload_bytes()
    if size > limit:
        raise ValidationError(_("The file is too large (at most %(megabytes)d MB).") % {"megabytes": limit // 1048576})
    uploaded.seek(0)
    head = uploaded.read(1024)
    uploaded.seek(0)
    if extension == ".pdf":
        if b"%PDF-" not in head:
            raise ValidationError(_("The file is not a valid PDF."))
        return
    if extension == ".xml":
        try:
            einvoice.parse(uploaded.read())
        except einvoice.EInvoiceError as error:
            raise ValidationError(str(error)) from error
        finally:
            uploaded.seek(0)
        return
    from PIL import Image, UnidentifiedImageError

    try:
        with open_picture(uploaded, PICTURE_FORMATS) as picture:
            picture_format = picture.format
            picture.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as error:
        raise ValidationError(_("The file is not a valid image.")) from error
    finally:
        uploaded.seek(0)
    if picture_format not in PICTURE_FORMATS:
        raise ValidationError(_("Only PNG, JPEG and WEBP pictures are allowed."))


def _hash_of(uploaded: Any) -> str:
    """The SHA-256 of an uploaded file."""
    digest = hashlib.sha256()
    uploaded.seek(0)
    for chunk in uploaded.chunks():
        digest.update(chunk)
    uploaded.seek(0)
    return digest.hexdigest()


@transaction.atomic
def create_from_upload(uploaded: Any, *, user: Any, read: bool = True) -> IncomingInvoice:
    """Store an uploaded invoice as a new invoice of the register and read it (number, date, supplier, amounts …).

    Reading: a PDF with text yields number, date, due date, a known supplier and the totals at once; with the AI
    switched on for reading invoices it goes on in the background and also finds the positions
    (:func:`start_reading`). A picture or a scan is kept and not read. Nothing is booked in.

    Raises:
        ValidationError: The file is not accepted (:func:`validate_invoice_file`).
    """
    validate_invoice_file(uploaded)
    invoice = IncomingInvoice(
        original_name=Path(uploaded.name or "invoice").name[:255],
        size=uploaded.size or 0,
        content_hash=_hash_of(uploaded),
        created_by=user if getattr(user, "pk", None) else None,
    )
    invoice.file.save(uploaded.name or "invoice", uploaded, save=False)
    _note_einvoice(invoice, uploaded)
    invoice.save()
    if read:
        start_reading(invoice, user=user)
        invoice.refresh_from_db()
    return invoice


def _note_einvoice(invoice: IncomingInvoice, uploaded: Any) -> None:
    """Remember what kind of e-invoice the file is; a PDF's attached XML is stored as a file of its own."""
    from django.core.files.base import ContentFile

    if invoice.is_xml:
        uploaded.seek(0)
        invoice.einvoice_format = einvoice.parse(uploaded.read()).syntax
        uploaded.seek(0)
        return
    if not invoice.is_pdf:
        return
    uploaded.seek(0)
    xml = einvoice.xml_in_pdf(uploaded.read())
    uploaded.seek(0)
    if xml is None:
        return
    invoice.xml_file.save("einvoice.xml", ContentFile(xml), save=False)
    try:
        invoice.einvoice_format = einvoice.parse(xml).syntax
    except einvoice.EInvoiceError:
        invoice.einvoice_format = ""  # kept as the PDF's attachment; reading says what is wrong with it


def invoice_file_of(items: list[MaterialItem]) -> Any:
    """The first invoice file attached to these items (a ``MaterialFile``), or ``None``."""
    from rentalars.material.models import MaterialFile, MaterialFileKind

    return (
        MaterialFile.objects.filter(item__in=items, kind=MaterialFileKind.INVOICE)
        .order_by("item__inventory_number", "pk")
        .first()
    )


def can_record_purchase(items: list[MaterialItem]) -> bool:
    """Whether the items of a purchase can be recorded as an incoming invoice: an invoice file, items not linked yet."""
    return any(item.source_position_id is None for item in items) and invoice_file_of(items) is not None


@transaction.atomic
def create_from_purchase(items: list[MaterialItem], *, user: Any) -> tuple[IncomingInvoice, bool]:
    """Record a purchase entered in the material management as an incoming invoice (the reverse of "Book in goods").

    The invoice file of the purchase is stored as an incoming invoice; supplier, number and date are taken from the
    items; the positions are made from the items – one for each model and price, the quantity the number of items (for
    bulk material its quantity) – and the items are linked to them, so the invoice shows as booked in. The totals are
    left empty: the person types them from the invoice (the sum under the Kontierung then shows the difference).
    If the same file is in the register already, that invoice is returned and nothing is made.

    Returns:
        ``(invoice, created)``.

    Raises:
        ValidationError: No item is left to record, or the purchase has no invoice file.
    """
    from django.core.files.uploadedfile import SimpleUploadedFile

    free = [item for item in items if item.source_position_id is None]
    stored = invoice_file_of(items)
    if not free or stored is None:
        raise ValidationError(
            _("This purchase has no invoice file, or its items belong to an incoming invoice already.")
        )
    with stored.file.open("rb") as handle:
        content = handle.read()
    uploaded = SimpleUploadedFile(stored.original_name or "invoice.pdf", content)
    same = IncomingInvoice.objects.filter(content_hash=_hash_of(uploaded)).first()
    if same is not None:
        return same, False
    invoice = create_from_upload(uploaded, user=user, read=False)
    first = free[0]
    head: dict[str, Any] = {"invoice_number": first.invoice_number, "invoice_date": first.purchase_date}
    if first.supplier_id:
        head["supplier"] = first.supplier
        head["supplier_name"] = first.supplier.name
    update_head(invoice, {name: value for name, value in head.items() if value})
    groups: dict[tuple[int, Decimal | None], list[MaterialItem]] = {}
    for item in sorted(free, key=lambda entry: entry.inventory_number):
        groups.setdefault((item.material_model_id, item.purchase_price), []).append(item)
    for (_model_id, price), members in groups.items():
        model = members[0].material_model
        pieces = sum((item.quantity if model.is_bulk else 1) for item in members)
        # The price of an item is its own; that of a bulk row is the price of the whole row: either way the amount of
        # the position is the sum of the prices, and the unit price follows from it.
        amount = sum((item.purchase_price for item in members if item.purchase_price is not None), Decimal("0.00"))
        quantity, unit_price = split_amount(amount if price is not None else None, Decimal(pieces))
        values: dict[str, Any] = {
            "description": model.name[:250],
            "manufacturer": model.manufacturer.name[:120] if getattr(model, "manufacturer", None) else "",
            "quantity": quantity,
            "unit_price_net": unit_price,
            "position_type": PositionType.GOODS,
            "material_model": model,
        }
        if members[0].asset_kind:
            values["asset_kind"] = members[0].asset_kind
            values["useful_life_months"] = members[0].useful_life_months
        position = add_position(invoice, values)
        for item in members:
            MaterialItem.objects.filter(pk=item.pk).update(
                source_position=position, source_quantity=item.quantity if model.is_bulk else 1
            )
    invoice.refresh_from_db()
    mark_booked_in_when_complete(invoice)
    return invoice, True


def start_reading(invoice: IncomingInvoice, *, user: Any, use_ai: bool = True) -> IncomingInvoice:
    """Read the file: the head from the text at once, with the AI the positions too, in the background.

    A scan or picture has no text: the invoice then says so (``reading['error']``) and is entered by hand. A reading
    that is still running is not started a second time.
    """
    from rentalars.ai import invoices as ai_invoices
    from rentalars.ai.client import AIError

    if invoice.reading_state == ReadingState.RUNNING and invoice.reading_job_id:
        job = invoice.reading_job
        if job is not None and not job.is_finished:
            return invoice
    structured_error = ""
    if invoice.is_xml or invoice.is_pdf:
        done, structured_error = _read_structured(invoice)
        if done:
            return invoice
    try:
        text = reading.text_of(invoice)
    except purchases.InvoiceTextError as error:
        invoice.reading_state = ReadingState.FAILED
        invoice.reading = {
            "source": "",
            "ai": None,
            "error": " ".join([structured_error, str(error)]).strip(),
            "note": "",
        }
        invoice.save(update_fields=["reading_state", "reading"])
        return invoice
    reading.apply_proposal(invoice, reading.proposal_from_text(text), error=structured_error)
    if use_ai and ai_invoices.is_available():
        invoice.reading_state = ReadingState.RUNNING
        invoice.save(update_fields=["reading_state"])
        try:
            job = ai_invoices.start_register(invoice, user=user)
        except AIError as error:
            invoice.reading_state = ReadingState.DONE
            invoice.reading = {**invoice.reading, "error": str(error)}
            invoice.save(update_fields=["reading_state", "reading"])
        else:
            IncomingInvoice.objects.filter(pk=invoice.pk).update(reading_job=job)
            invoice.refresh_from_db()
    return invoice


def xml_response(invoice: IncomingInvoice) -> Any:
    """The XML of an e-invoice as a download: never shown in the browser, with a ``sandbox`` policy besides.

    Raises:
        Http404: The invoice is no e-invoice with an XML.
    """
    from django.http import Http404

    from rentalars.core.uploads import protected_file_response, safe_download_name

    if not invoice.xml_name:
        raise Http404
    base = Path(invoice.original_name).stem or "einvoice"
    response = protected_file_response(invoice.xml_name, download_name=safe_download_name(f"{base}.xml"))
    response["Content-Security-Policy"] = "sandbox; default-src 'none'"
    return response


def _read_structured(invoice: IncomingInvoice) -> tuple[bool, str]:
    """Read the XML of an e-invoice exactly – no AI, no text patterns (DOK-040, DOK-041).

    The XML is the file itself or the one attached to the PDF (a PDF uploaded earlier is looked at now and its
    XML kept). Returns ``(done, error)``: ``done`` when the invoice is read from the XML; ``error`` says why a PDF's
    attachment could not be used (the PDF is then read as before).
    """
    from django.core.files.base import ContentFile

    xml_name = invoice.xml_name
    if not xml_name and invoice.is_pdf:
        with invoice.file.open("rb") as handle:
            found = einvoice.xml_in_pdf(handle.read())
        if found is None:
            return False, ""
        invoice.xml_file.save("einvoice.xml", ContentFile(found), save=False)
        invoice.save(update_fields=["xml_file"])
        xml_name = invoice.xml_name
    try:
        with invoice.file.storage.open(xml_name, "rb") as handle:
            data = handle.read()
        parsed = einvoice.parse(data)
    except (einvoice.EInvoiceError, OSError) as error:
        message = str(error) if isinstance(error, einvoice.EInvoiceError) else _("The e-invoice file cannot be opened.")
        if invoice.is_xml:
            invoice.reading_state = ReadingState.FAILED
            invoice.reading = {"source": "", "ai": None, "error": message, "note": ""}
            invoice.save(update_fields=["reading_state", "reading"])
            return True, message
        return False, _("The XML attached to the PDF could not be used (%(reason)s); the PDF is read as a PDF.") % {
            "reason": message
        }
    invoice.einvoice_format = parsed.syntax
    invoice.save(update_fields=["einvoice_format"])
    from rentalars.documents.einvoice_check import store_incoming

    store_incoming(invoice, data)  # DOK-042: the check against the rules; a finding refuses nothing
    reading.apply_proposal(invoice, einvoice.proposal(parsed), replace_positions=True)
    return True, ""


# --- The head ----------------------------------------------------------------------------------------------------


def link_supplier(invoice: IncomingInvoice, name: str) -> None:
    """Name the supplier of an invoice: an existing supplier of this name (any case) is linked, else only the name stays.

    A supplier that is not in the master data yet is created by :func:`create_supplier`, on the user's word.
    """
    name = " ".join((name or "").split())[:120]
    found = Supplier.objects.filter(name__iexact=name).order_by("-is_active", "pk").first() if name else None
    invoice.supplier = found
    invoice.supplier_name = found.name if found is not None else name


def create_supplier(invoice: IncomingInvoice) -> Supplier:
    """Create the supplier named on the invoice in the master data and link it (a name that exists is just linked).

    Raises:
        ValidationError: The invoice names no supplier.
    """
    if not invoice.supplier_name.strip():
        raise ValidationError({"supplier_name": _("Name the supplier first.")})
    supplier = material_services.supplier_named(invoice.supplier_name)
    assert supplier is not None
    invoice.supplier = supplier
    invoice.supplier_name = supplier.name
    invoice.save(update_fields=["supplier", "supplier_name"])
    return supplier


def has_booked_items(invoice: IncomingInvoice) -> bool:
    """Whether items or bulk rows were made from this invoice."""
    return bool(invoice.pk) and MaterialItem.objects.filter(source_position__invoice=invoice).exists()


def _has_ancillary(invoice: IncomingInvoice) -> bool:
    """Whether the invoice has positions of ancillary cost."""
    return invoice.pk is not None and invoice.positions.filter(position_type=PositionType.ANCILLARY).exists()


@dataclass(frozen=True)
class SpreadLock:
    """What of an invoice is frozen because items were made from it (R1-3).

    The ancillary costs are spread over *all* goods of the invoice, and every item is made with its share at the time
    of booking in. Changing the currency, the rate, the key or a figure the shares are worked out from, after some
    items exist, would give the rest of the goods shares that no longer add up to the ancillary costs of the invoice.
    The simpler and safer way is to lock these values (instead of storing shares and keeping them in step).
    """

    #: Items were made from the invoice.
    booked: bool = False
    #: The invoice has ancillary cost positions.
    ancillary: bool = False
    #: The key the costs are spread by.
    key: str = AllocationKey.VALUE

    @property
    def head(self) -> frozenset[str]:
        """The fields of the head that cannot change."""
        if not self.booked:
            return frozenset()
        return frozenset({"currency", "exchange_rate"} | ({"allocation_key"} if self.ancillary else set()))

    def position_fields(self, position_type: str) -> frozenset[str]:
        """The fields of a position of this type that cannot change (the goods and the ancillary cost positions)."""
        if not self.booked:
            return frozenset()
        if position_type == PositionType.ANCILLARY or (self.ancillary and position_type == PositionType.GOODS):
            fields = {"quantity", "unit_price_net", "position_type"}
            if self.key == AllocationKey.WEIGHT:
                fields |= {"weight_kg", "material_model"}
            return frozenset(fields)
        # Something else (a deposit, a service) takes no part in the spread; it only may not become part of it.
        return frozenset({"position_type"})

    def may_add_or_remove(self, position_type: str) -> bool:
        """Whether a position of this type can be added or removed: not while it would shift the spread."""
        if not self.booked:
            return True
        return not (position_type == PositionType.ANCILLARY or (self.ancillary and position_type == PositionType.GOODS))


def spread_lock(invoice: IncomingInvoice) -> SpreadLock:
    """The lock of an invoice: nothing once no item was made from it."""
    if not has_booked_items(invoice):
        return SpreadLock()
    return SpreadLock(booked=True, ancillary=_has_ancillary(invoice), key=invoice.allocation_key)


_SPREAD_LOCKED_HEAD = gettext_lazy(
    "Items were booked in from this invoice already: they were made with the currency, the exchange rate and the "
    "way the ancillary costs were spread. Change these only before booking in."
)
_SPREAD_LOCKED_POSITION = gettext_lazy(
    "Items were booked in from this invoice already: the ancillary costs were spread over its goods when they were "
    "made, so this cannot be changed, added or removed any more."
)


@transaction.atomic
def update_head(invoice: IncomingInvoice, values: dict[str, Any]) -> IncomingInvoice:
    """Change the head of an invoice; only the fields of :data:`HEAD_FIELDS` and the status are taken.

    ``supplier_name`` links the supplier of the master data of this name if there is one. Values are checked as the
    model does; nothing is saved when one is wrong. Once items were made from the invoice the currency, the exchange
    rate and (with ancillary costs) the key cannot change (:class:`SpreadLock`). A new currency without a new rate
    forgets the old rate: a rate belongs to one currency.

    Raises:
        ValidationError: A value is wrong, the status is unknown, or the value is locked by items made already.
    """
    lock = spread_lock(invoice)
    errors: dict[str, Any] = {}
    for name in lock.head:
        if name not in values:
            continue
        new = values[name]
        if name == "currency":
            new = (new or "EUR").strip().upper()
        if new != getattr(invoice, name) and not (name == "currency" and not new):
            errors[name] = _SPREAD_LOCKED_HEAD
    if errors:
        raise ValidationError(errors)
    was_currency = (invoice.currency or "EUR").upper()
    was_rate = invoice.exchange_rate
    for name in HEAD_FIELDS:
        if name in values and name != "supplier_name":
            setattr(invoice, name, values[name])
    if "supplier_name" in values:
        link_supplier(invoice, values["supplier_name"])
    if values.get("currency") is not None:
        invoice.currency = (invoice.currency or "EUR").strip().upper()
        if invoice.currency != was_currency and invoice.exchange_rate == was_rate:
            invoice.exchange_rate = None  # R1-4: the old rate was for the old currency
    if "status" in values:
        if values["status"] not in InvoiceStatus.values:
            raise ValidationError({"status": _("Unknown status.")})
        invoice.status = values["status"]
    invoice.full_clean(exclude=["file"])
    invoice.save()
    return invoice


def set_status(invoice: IncomingInvoice, status: str) -> IncomingInvoice:
    """Set the status of an invoice: open, checked or booked in (a hand mark for invoices without material)."""
    return update_head(invoice, {"status": status})


# --- The positions -----------------------------------------------------------------------------------------------


def _check_position(
    position: InvoicePosition, *, changed: set[str], was_type: str | None = None, lock: SpreadLock | None = None
) -> None:
    """The rules of a position: goods are not negative; booked positions keep their figures.

    ``was_type`` is the type before the change (of a position that is changed); ``lock`` the lock of the invoice, if
    the caller has it already (R1-3: after items were made, the figures the spread is worked out from are frozen).
    """
    errors: dict[str, Any] = {}
    if position.pk and position.items.exists():
        locked = [name for name in LOCKED_WHEN_BOOKED if name in changed]
        for name in locked:
            errors[name] = _("The position is booked in already: the items were made with this value.")
    if position.pk and changed:
        lock = lock or spread_lock(position.invoice)
        frozen = lock.position_fields(was_type or position.position_type) | lock.position_fields(position.position_type)
        for name in sorted(frozen & changed):
            errors.setdefault(name, _SPREAD_LOCKED_POSITION)
    account = position.tax_account
    if account is not None and not account.is_active and (not position.pk or "tax_account" in changed):
        errors["tax_account"] = _("This tax account is not in use any more. Choose another one.")
    if position.position_type != PositionType.ANCILLARY and position.unit_price_net is not None:
        if position.unit_price_net < 0:
            errors["unit_price_net"] = _("Only an ancillary cost can be negative (a discount).")
    if errors:
        raise ValidationError(errors)


@transaction.atomic
def add_position(invoice: IncomingInvoice, values: dict[str, Any]) -> InvoicePosition:
    """Add a position at the end of an invoice.

    A position a person adds is marked (``user_edited``): a new reading of the file keeps it (R1-5).

    Raises:
        ValidationError: A value is wrong, the invoice has the most positions already, or items were made from the
            invoice and the position would shift the spread of its ancillary costs (R1-3).
    """
    if invoice.positions.count() >= MAX_POSITIONS:
        raise ValidationError(_("At most %(count)d positions per invoice.") % {"count": MAX_POSITIONS})
    last = invoice.positions.order_by("-place").values_list("place", flat=True).first() or 0
    position = InvoicePosition(invoice=invoice, place=last + 1, user_edited=True)
    for name in POSITION_FIELDS:
        if name in values:
            setattr(position, name, values[name])
    if not spread_lock(invoice).may_add_or_remove(position.position_type):
        raise ValidationError(_SPREAD_LOCKED_POSITION)
    _check_position(position, changed=set())
    position.full_clean()
    position.save()
    return position


@transaction.atomic
def update_position(position: InvoicePosition, values: dict[str, Any], *, by_person: bool = True) -> InvoicePosition:
    """Change a position; a booked one keeps quantity, price and type.

    A change marks the position as touched by a person (``user_edited``) unless ``by_person`` is false: a new reading
    of the file does not replace it any more (R1-5).

    Raises:
        ValidationError: A value is wrong, or it is a locked value of a booked position, or a figure the spread of the
            ancillary costs is worked out from after items were made (R1-3).
    """
    was_type = position.position_type
    changed = set()
    for name in POSITION_FIELDS:
        if name in values and getattr(position, name) != values[name]:
            setattr(position, name, values[name])
            changed.add(name)
    _check_position(position, changed=changed, was_type=was_type)
    if changed and by_person:
        position.user_edited = True
    position.full_clean()
    position.save()
    return position


@transaction.atomic
def delete_position(position: InvoicePosition) -> None:
    """Remove a position that is not booked in; the rest keep their order.

    Raises:
        ValidationError: Items were made from the position, or from the invoice and the position is part of the
            spread of its ancillary costs (R1-3).
    """
    if position.items.exists():
        raise ValidationError(_("The position is booked in: its items stay. It cannot be removed."))
    invoice = position.invoice
    if not spread_lock(invoice).may_add_or_remove(position.position_type):
        raise ValidationError(_SPREAD_LOCKED_POSITION)
    position.delete()
    renumber(invoice)


def renumber(invoice: IncomingInvoice) -> None:
    """Number the positions 1, 2, 3 … in their order."""
    for place, position in enumerate(invoice.positions.order_by("place", "pk"), start=1):
        if position.place != place:
            position.place = place
            position.save(update_fields=["place"])


# --- What was made of the positions ---------------------------------------------------------------------------


def booked_counts(invoice: IncomingInvoice) -> dict[int, dict[str, int]]:
    """Per position: the rows (items) and pieces made of it so far – ``{pk: {"rows": n, "pieces": n}}``.

    A bulk row counts the pieces it was booked in with (``source_quantity``), not its quantity now: building in and
    selling lower the quantity, but the pieces of the position stay booked (R1-2). An individual item
    is one piece.
    """
    rows = (
        MaterialItem.objects.filter(source_position__invoice=invoice)
        .values("source_position")
        .annotate(rows=Count("pk"), pieces=Sum(Coalesce("source_quantity", "quantity")))
    )
    return {row["source_position"]: {"rows": row["rows"], "pieces": row["pieces"] or 0} for row in rows}


def duplicates(invoice: IncomingInvoice) -> list[IncomingInvoice]:
    """Other invoices that may be the same: the same file, or the same supplier and invoice number."""
    condition = Q(content_hash=invoice.content_hash) if invoice.content_hash else Q(pk__in=[])
    if invoice.invoice_number:
        same_number = Q(invoice_number__iexact=invoice.invoice_number)
        if invoice.supplier_id:
            condition |= same_number & Q(supplier_id=invoice.supplier_id)
        elif invoice.supplier_name:
            condition |= same_number & Q(supplier_name__iexact=invoice.supplier_name)
    return list(IncomingInvoice.objects.filter(condition).exclude(pk=invoice.pk).select_related("supplier")[:5])


def positions_net(invoice: IncomingInvoice) -> Decimal:
    """The net amounts of all positions together, in the currency of the invoice (a discount counts negative)."""
    return sum((position.line_net or Decimal(0) for position in invoice.positions.all()), Decimal("0.00"))


def split_amount(amount: Decimal | None, quantity: Decimal) -> tuple[Decimal, Decimal | None]:
    """Quantity and net unit price for a net amount typed for a whole position.

    The form of a document shows a position as one amount; the quantity of the reading stays (it is what "Book in
    goods" makes the pieces from): the unit price becomes amount ÷ quantity, to four places. If that does not give the
    amount back to the cent, the position is one piece at the amount.

    Returns:
        ``(quantity, unit price)``; the price is ``None`` for no amount.
    """
    from rentalars.core.money import money

    if amount is None:
        return quantity, None
    if quantity and quantity > 0:
        unit = (amount / quantity).quantize(Decimal("0.0001"))
        if money(quantity * unit) == amount:
            return quantity, unit
    return Decimal("1"), amount


@dataclass(frozen=True)
class KontierungSum:
    """What the Kontierungen of an invoice add up to, shown under the rows and while typing.

    ``tax`` and ``gross`` are ``None`` while a line with an amount has no tax rate; ``difference`` is ``None`` while
    the invoice has no total net, else the sum minus the total net (0.00 when they agree).
    """

    net: Decimal
    tax: Decimal | None
    gross: Decimal | None
    difference: Decimal | None


def kontierung_sum(lines: list[tuple[Decimal | None, Decimal | None]], total_net: Decimal | None) -> KontierungSum:
    """Add up ``(net amount, tax rate)`` of the lines; a line without an amount counts nothing."""
    from rentalars.core.money import money

    net = Decimal("0.00")
    tax: Decimal | None = Decimal("0.00")
    for amount, rate in lines:
        if amount is None:
            continue
        net += amount
        if rate is None:
            tax = None
        elif tax is not None:
            tax += money(amount * rate / 100)
    net = money(net)
    return KontierungSum(
        net=net,
        tax=tax,
        gross=None if tax is None else net + tax,
        difference=None if total_net is None else net - total_net,
    )


def kontierung_sum_of(invoice: IncomingInvoice) -> KontierungSum:
    """The sum of the saved Kontierungen of an invoice."""
    return kontierung_sum(
        [(position.line_net, position.tax_rate) for position in invoice.positions.all()], invoice.total_net
    )


def mark_booked_in_when_complete(invoice: IncomingInvoice) -> bool:
    """Set the status "booked in" once every goods position is booked with its whole quantity; returns whether it was set."""
    counts = booked_counts(invoice)
    goods = [position for position in invoice.positions.all() if position.is_goods]
    if not goods or invoice.status == InvoiceStatus.BOOKED_IN:
        return False
    if all(counts.get(position.pk, {}).get("pieces", 0) >= position.quantity for position in goods):
        invoice.status = InvoiceStatus.BOOKED_IN
        invoice.save(update_fields=["status"])
        return True
    return False


@transaction.atomic
def delete_invoice(invoice: IncomingInvoice) -> None:
    """Delete an invoice with its positions and its file; refused once items were made of it.

    Raises:
        ValidationError: Items were made from the invoice; they keep the link to it; or it is archived and its retention
            period has not ended (DOK-043).
    """
    if MaterialItem.objects.filter(source_position__invoice=invoice).exists():
        raise ValidationError(_("Items were booked in from this invoice: it cannot be deleted."))
    from rentalars.documents import archive  # DOK-043: an archived voucher is kept for its retention period

    archive.guard_deletion(invoice)
    stored = [name for name in (invoice.file.name, invoice.xml_file.name) if name]
    for position in list(invoice.positions.all()):
        position.delete()
    invoice.delete()
    for name in stored:
        # Only once the deletion is committed; the file is the only copy of the original.
        transaction.on_commit(lambda name=name: invoice.file.storage.delete(name))
