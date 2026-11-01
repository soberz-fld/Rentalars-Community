# SPDX-License-Identifier: GPL-3.0-or-later
"""Entering a purchase: many items of different models from one invoice (MAT-061; MAT-019, MAT-050).

The requirement: "Kauf einpflegen" – supplier, invoice number and invoice date are
asked once, then a list of positions: model, number of items, price per
piece, serial numbers, storage location. Saving creates every item in one
transaction with consecutive IDs, as "Neue Exemplare" does (MAT-050), and
hangs the invoice on each of them as a file of the kind "invoice" (MAT-017).

Filling it from the invoice (the AI reads the invoice): the uploaded PDF is kept for a while (:func:`keep_invoice`), its
text is read (:func:`invoice_text`; only PDFs with a text layer, no scans).
Without AI only the head is found in the text (:func:`head_from_text`); with
AI (:mod:`rentalars.ai.invoices`) the positions as well. Either way the
result is a *proposal* (:func:`build_proposal`): suppliers and models are
matched against the existing ones, but a model is only filled in where the
match is certain – every row taken from the invoice is checked by the user
before anything is created.

MAT-076: amounts are read as invoices write them – German
"1.072,50", English "1,072.50", an ambiguous "1.072" by the style of the
invoice and checked against the amounts of its text (:func:`parse_amount`,
:class:`InvoiceNumbers`) – with AI and without; the totals of the invoice are
found by their labels (:func:`totals_in_text`) for the user to compare with
the sum of the positions; a new model gets the category and product the AI
proposed only if they name an existing one exactly or unambiguously
(:func:`match_category`, :func:`match_product`).

Browser views and API views both call these functions (API-002).
"""

from __future__ import annotations

import contextlib
import datetime
import math
import re
import secrets
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from decimal import ROUND_FLOOR, Decimal, InvalidOperation
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from rentalars.accounts.rights import SpecialRight
from rentalars.core.money import money
from rentalars.core.uploads import validate_document_upload
from rentalars.masterdata.models import Category, StorageLocation, Supplier
from rentalars.material import serials as serial_check
from rentalars.material import services
from rentalars.material.models import MaterialFile, MaterialFileKind, MaterialItem, MaterialModel, TrackingMode
from rentalars.material.numbering import format_inventory_number
from rentalars.products.models import Product

#: The most positions of one purchase – a guard against a runaway invoice or answer.
MAX_POSITIONS = 100
#: How long an uploaded invoice is kept for the purchase that is being entered (it is attached on saving).
PENDING_DAYS = 2
#: Of a PDF only the first pages are read; an invoice is short.
MAX_PDF_PAGES = 20
#: The most characters of invoice text that are worked with.
MAX_TEXT_CHARS = 60_000
#: Less text than this: a scan without text layer.
MIN_TEXT_CHARS = 20
#: What reading the pages of a PDF may cost at most, counted in the bytes pypdf parses for them: the content of
#: each page, the forms it draws as often as it draws them, the character maps of its fonts (MAT-062).
#: pypdf needs 1–5 s per MB whatever the bytes draw, and a file of a few KB can hold MBs (one large stream drawn on
#: every page). A real invoice page needs 5–80 KB (measured: LibreOffice 15 KB, TeX 4–20 KB, dense pages 70 KB);
#: this reads ten pages or more – more text than the AI is given – in well under a second.
MAX_PDF_WORK_BYTES = 256 * 1024
#: After this many seconds no further page is read: the safety net for what the bytes do not count.
MAX_PDF_SECONDS = 1.0
#: What a font costs before any of its streams: pypdf builds it anew for every page that has it (about 0.25 ms).
_FONT_WORK_BYTES = 256
#: Forms drawn in forms drawn in … deeper than this are not read; no invoice nests them so.
_MAX_FORM_DEPTH = 5
#: pypdf's own limits while an invoice is read – far below its defaults (75 MB per stream, 5,000 forms drawn per
#: page, 100,000 pages), which no invoice comes near.
_PDF_LIMITS = {
    "zlib_maximum_output_length": 8_000_000,
    "lzw_maximum_output_length": 8_000_000,
    "run_length_maximum_output_length": 8_000_000,
    "brotli_maximum_output_length": 8_000_000,
    "array_based_stream_maximum_output_length": 8_000_000,
    "stream_decoding_work_maximum_length": 32_000_000,
    "xform_maximum_invocations_per_extraction": 100,
    "page_tree_maximum_entries": 10_000,
}
#: A name in a content stream, delimited as pypdf reads it (``NameObject.delimiter_pattern``).
_PDF_NAME = re.compile(rb"/[^\s()<>\[\]{}/%]*")

_SALT = "rentalars.material.purchase-invoice"
_PENDING_NAME = re.compile(r"^[0-9a-f]{32}\.[a-z0-9]{1,10}$")


# --- What a purchase consists of -------------------------------------------------------------------


@dataclass
class NewModel:
    """A model that is not there yet: created together with the items of its position."""

    name: str
    category: Category
    manufacturer: str = ""
    product: Product | None = None
    #: Incoming invoices: ``"bulk"`` makes a model of bulk material (a quantity); empty: individual items.
    tracking_mode: str = ""


@dataclass
class Position:
    """One position of the invoice: items of one model.

    ``unit_price`` is the price of one piece as typed – net, or gross if the
    head says so (IMP-014). With ``price_for_set`` it is the price of all
    pieces of the position together (MAT-054). For bulk material the
    position becomes one row with the count as quantity (MAT-005).
    """

    model: MaterialModel | None = None
    new_model: NewModel | None = None
    count: int = 1
    unit_price: Decimal | None = None
    price_for_set: bool = False
    serial_numbers: list[str] = field(default_factory=list)
    storage_location: StorageLocation | None = None
    supplier_article_number: str = ""
    #: Incoming invoices: values of each new item of the position, in the order of the IDs – the acquisition
    #: cost, kind and useful life, the invoice position it came from. One entry for a bulk row; fewer entries than
    #: items leave the last items without.
    item_fields: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Head:
    """What the whole purchase shares: supplier, invoice, how the prices are meant, the start ID."""

    supplier_name: str = ""
    invoice_number: str = ""
    invoice_date: datetime.date | None = None
    #: IMP-014: the prices are gross and include this rate in percent; ``None``: net.
    gross_rate: Decimal | None = None
    start_number: int | None = None
    purchase_note: str = ""


@dataclass
class Purchase:
    """What saving a purchase created."""

    items: list[MaterialItem]
    new_models: list[MaterialModel]
    supplier: Supplier | None
    supplier_created: bool
    invoice_attached: bool
    warnings: list[str]
    #: Incoming invoices: the new items by position, in the order of the positions.
    by_position: list[list[MaterialItem]] = field(default_factory=list)

    @property
    def id_list(self) -> str:
        """The IDs of the new items in short, e.g. ``0042-0047,0050`` – for labels and the summary."""
        return compact_ids([item.inventory_number for item in self.items])


def compact_ids(numbers: list[int]) -> str:
    """IDs as the labels page reads them: runs of consecutive IDs as ranges (``0042-0047,0050``)."""
    parts: list[str] = []
    ordered = sorted(set(numbers))
    index = 0
    while index < len(ordered):
        end = index
        while end + 1 < len(ordered) and ordered[end + 1] == ordered[end] + 1:
            end += 1
        first, last = format_inventory_number(ordered[index]), format_inventory_number(ordered[end])
        parts.append(first if index == end else f"{first}-{last}")
        index = end + 1
    return ",".join(parts)


def net_price(price: Decimal | None, gross_rate: Decimal | None) -> Decimal | None:
    """IMP-014: the net price of a price as typed; a gross price is divided by 1 + rate, rounded to cents.

    The same rounding as the other price forms (``services.net_from_gross``, MAT-059).
    """
    if price is None or gross_rate is None:
        return price
    return services.net_from_gross(price, gross_rate)


# --- Saving -------------------------------------------------------------------------------------------


def _model_of(position: Position, index: int) -> tuple[MaterialModel, bool]:
    """The model of a position; a new one is created – once, even if two positions name it (MAT-048)."""
    if position.model is not None:
        return position.model, False
    new = position.new_model
    if new is None or not (new.name or "").strip():
        raise ValidationError(_("Position %(number)d: choose a model.") % {"number": index})
    name = new.name.strip()[:200]
    existing = MaterialModel.objects.filter(name__iexact=name).first()
    if existing is not None:
        return existing, False
    model = MaterialModel(
        name=name,
        category=new.category,
        manufacturer=services.manufacturer_named(new.manufacturer),
        default_product=new.product,
        tracking_mode=new.tracking_mode or TrackingMode.ITEMS,
    )
    try:
        model.full_clean()
    except ValidationError as error:
        raise ValidationError(
            _("Position %(number)d: %(error)s") % {"number": index, "error": " ".join(error.messages)}
        ) from error
    model.save()
    return model, True


def is_customer_model(model: MaterialModel) -> bool:
    """Whether a material model is customer material: its category holds it, or its product has an owner (PRD-043).

    MAT-076: a purchase never adds items to such a model – neither typed nor matched.
    """
    product = model.default_product
    return bool(model.category.holds_customer_material or (product is not None and product.owner_id is not None))


def check_positions(positions: list[Position], *, rights: Any) -> None:
    """The rules for the whole purchase, before anything is written.

    Raises:
        ValidationError: No position, too many positions or items, a price
            without the right to see purchase prices (AUT-019), a new model of
            a customer's product (PRD-043).
    """
    if not positions:
        raise ValidationError({"positions": _("Enter at least one position.")})
    for index, position in enumerate(positions, start=1):
        # Review (MAT-076, PRD-043): what is bought is the company's – never a piece of customer material.
        product = position.new_model.product if position.new_model is not None else None
        if product is not None and product.owner_id is not None:
            raise ValidationError(
                {
                    "positions": _("Position %(number)d: %(error)s")
                    % {"number": index, "error": customer_product_error(product)}
                }
            )
        if position.model is not None and is_customer_model(position.model):
            raise ValidationError(
                {
                    "positions": _("Position %(number)d: %(error)s")
                    % {
                        "number": index,
                        "error": _("“%(model)s” is customer material: bought items cannot join it.")
                        % {"model": position.model.name},
                    }
                }
            )
    if len(positions) > MAX_POSITIONS:
        raise ValidationError({"positions": _("At most %(count)d positions per purchase.") % {"count": MAX_POSITIONS}})
    total = sum(
        1 if (position.model is not None and position.model.is_bulk) else position.count for position in positions
    )
    if total > services.MAX_ITEMS_PER_BATCH:
        raise ValidationError(
            {
                "positions": _("Between 1 and %(maximum)d items can be created in one step.")
                % {"maximum": services.MAX_ITEMS_PER_BATCH}
            }
        )
    if not rights.has(SpecialRight.PURCHASE_PRICES) and any(
        position.unit_price is not None or position.price_for_set for position in positions
    ):
        raise ValidationError({"unit_price": _("You do not have the right to set this field.")})


def serial_warnings(positions: list[Position]) -> list[str]:
    """Warnings about the serial numbers of the positions: given twice in the purchase, or already an item's.

    Retired and sold items count. The same number at the model of another manufacturer may be right, so nothing is
    refused: the page asks the user to confirm, the API names the warnings in its answer.
    """
    entries = [
        (serial, position.model.pk if position.model is not None else None)
        for position in positions
        for serial in position.serial_numbers
    ]
    return serial_check.entry_warnings(entries)


@transaction.atomic
def create_purchase(
    head: Head,
    positions: list[Position],
    *,
    rights: Any,
    user: Any = None,
    invoice: PendingInvoice | Any = None,
) -> Purchase:
    """Create the items of every position in one step, all or nothing (MAT-061; MAT-050).

    Each item gets the supplier (created if new, MAT-050), invoice number,
    invoice date and its net purchase price (IMP-014). The IDs follow each
    other across the positions: from the start ID on, each position takes the
    next free IDs after the one before; without a start ID the next free IDs
    of the number range (MAT-003). The invoice – a kept upload
    (:class:`PendingInvoice`) or an uploaded file – is stored once and listed
    with every new item as a file of the kind "invoice" (MAT-017).

    Args:
        head: Supplier, invoice, how prices are meant, start ID.
        positions: The positions in the order of the invoice.
        rights: The rights of the caller: prices need the right to see purchase prices.
        user: Who uploads the invoice.
        invoice: The invoice, or ``None``.

    Raises:
        ValidationError: A rule of the purchase, of an item (MAT-050) or of a
            new model is broken; nothing is created then.
    """
    check_positions(positions, rights=rights)
    warnings = serial_warnings(positions)  # Before the new items exist, so that they do not warn about each other
    if head.start_number is not None and MaterialItem.objects.filter(inventory_number=head.start_number).exists():
        raise ValidationError({"start_number": _("This ID is already taken.")})
    supplier_name = (head.supplier_name or "").strip()
    supplier_created = bool(supplier_name) and not Supplier.objects.filter(name__iexact=supplier_name).exists()
    supplier = services.supplier_named(supplier_name)
    common: dict[str, Any] = {}
    if supplier is not None:
        common["supplier"] = supplier
    if head.invoice_number:
        common["invoice_number"] = head.invoice_number.strip()[:60]
    if head.invoice_date:
        common["purchase_date"] = head.invoice_date
    if head.purchase_note:
        common["purchase_note"] = head.purchase_note.strip()[:250]

    items: list[MaterialItem] = []
    by_position: list[list[MaterialItem]] = []
    new_models: list[MaterialModel] = []
    next_number = head.start_number
    for index, position in enumerate(positions, start=1):
        model, created = _model_of(position, index)
        if created:
            new_models.append(model)
        fields = dict(common)
        if position.storage_location is not None:
            fields["storage_location"] = position.storage_location
        if position.supplier_article_number:
            fields["supplier_article_number"] = position.supplier_article_number.strip()[:120]
        price = net_price(position.unit_price, head.gross_rate)
        count = position.count
        price_for_set = position.price_for_set and count > 1
        if model.is_bulk:
            # MAT-005: bulk material is one row with the number as its quantity, and the price of the whole row.
            fields["quantity"] = count
            if price is not None and not position.price_for_set:
                price = (price * count).quantize(Decimal("0.01"))
            count, price_for_set = 1, False
        if price is not None:
            fields["purchase_price"] = price
        try:
            created_items = services.create_items(
                model,
                count,
                inventory_number=next_number,
                serial_numbers=position.serial_numbers,
                price_for_set=price_for_set,
                item_fields=position.item_fields,
                **fields,
            )
        except ValidationError as error:
            raise ValidationError(
                _("Position %(number)d: %(error)s") % {"number": index, "error": " ".join(error.messages)}
            ) from error
        items.extend(created_items)
        by_position.append(created_items)
        if next_number is not None:
            # The next position goes on with the next free ID after this one's last (MAT-050).
            next_number = services.following_free_numbers(created_items[-1].inventory_number, 2)[1]

    attached = False
    if invoice is not None and items:
        title = _("Invoice %(number)s") % {"number": head.invoice_number} if head.invoice_number else _("Invoice")
        attach_invoice(items, invoice, title=title, user=user)
        attached = True
    return Purchase(
        items=items,
        new_models=new_models,
        supplier=supplier,
        supplier_created=supplier_created,
        invoice_attached=attached,
        warnings=warnings[:10],
        by_position=by_position,
    )


def attach_invoice(items: list[MaterialItem], invoice: Any, *, title: str, user: Any = None) -> list[MaterialFile]:
    """Store the invoice once and list it with each item as a file of the kind "invoice" (MAT-017).

    The file is written once; the further items point to the same stored
    file. :func:`rentalars.material.services.delete_file` removes it from
    the disk only with the last item that lists it.

    Raises:
        ValidationError: The file type is not accepted or it is too large (NFA-007).
    """
    if isinstance(invoice, PendingInvoice):
        handle = invoice.path.open("rb")
        uploaded: Any = File(handle, name=invoice.name)
    else:
        handle = None
        uploaded = invoice
    try:
        first = services.add_file(items[0], uploaded, kind=MaterialFileKind.INVOICE, title=title, user=user)
    finally:
        if handle is not None:
            handle.close()
    stored = [first]
    for item in items[1:]:
        copy = MaterialFile(
            item=item,
            kind=MaterialFileKind.INVOICE,
            title=first.title,
            file=first.file.name,
            original_name=first.original_name,
            size=first.size,
            uploaded_by=user if getattr(user, "pk", None) else None,
        )
        copy.save()
        stored.append(copy)
    if isinstance(invoice, PendingInvoice):
        # Removed once the items are really there; if saving fails, the upload is still there to try again.
        transaction.on_commit(lambda: discard_invoice(invoice))
    return stored


# --- The uploaded invoice between the steps ------------------------------------------------------------


@dataclass(frozen=True)
class PendingInvoice:
    """An uploaded invoice kept for the purchase being entered, named by a signed token.

    The token names the stored file, its original name and the user who
    uploaded it; it cannot be forged, it is good for :data:`PENDING_DAYS`
    days and only for that user – the page sends it back as a hidden field,
    the API as ``invoice_upload``.
    """

    token: str
    stored: str
    name: str
    size: int

    @property
    def path(self) -> Path:
        """Where the file is."""
        return pending_directory() / self.stored

    @property
    def is_pdf(self) -> bool:
        """Whether it can be read: only PDFs are."""
        return self.stored.endswith(".pdf")


def pending_directory() -> Path:
    """The folder of uploaded invoices that are not attached yet."""
    directory = Path(settings.DATA_DIR) / "purchase-invoices"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def keep_invoice(uploaded: Any, *, user: Any) -> PendingInvoice:
    """Keep an uploaded invoice for the purchase being entered; old ones of unfinished purchases are removed.

    Raises:
        ValidationError: The file type is not accepted or it is too large (NFA-007).
    """
    validate_document_upload(uploaded)
    delete_old_invoices()
    extension = Path(uploaded.name or "").suffix.lower()[:10] or ".bin"
    if not re.fullmatch(r"\.[a-z0-9]{1,9}", extension):
        extension = ".bin"
    stored = secrets.token_hex(16) + extension
    size = 0
    with (pending_directory() / stored).open("wb") as target:
        for chunk in uploaded.chunks():
            size += len(chunk)
            target.write(chunk)
    name = Path(uploaded.name or "rechnung").name[:200]
    token = signing.dumps({"f": stored, "n": name, "s": size, "u": getattr(user, "pk", None)}, salt=_SALT)
    return PendingInvoice(token=token, stored=stored, name=name, size=size)


def pending_invoice(token: str, *, user: Any) -> PendingInvoice:
    """The kept invoice a token names, for the user who uploaded it.

    Raises:
        ValidationError: The token is not valid, too old, of another user, or the file is gone.
    """
    gone = ValidationError(_("The uploaded invoice is no longer there. Please upload it again."))
    try:
        data = signing.loads(str(token or ""), salt=_SALT, max_age=datetime.timedelta(days=PENDING_DAYS))
    except signing.BadSignature as error:
        raise gone from error
    if not isinstance(data, dict) or data.get("u") != getattr(user, "pk", None):
        raise gone
    stored = str(data.get("f", ""))
    if not _PENDING_NAME.match(stored) or not (pending_directory() / stored).is_file():
        raise gone
    return PendingInvoice(
        token=str(token), stored=stored, name=str(data.get("n", ""))[:200], size=int(data.get("s", 0))
    )


def discard_invoice(invoice: PendingInvoice) -> None:
    """Remove a kept invoice."""
    (pending_directory() / invoice.stored).unlink(missing_ok=True)


def delete_old_invoices(days: int = PENDING_DAYS) -> int:
    """Remove kept invoices of purchases that were never saved; returns how many."""
    limit = time.time() - days * 86400
    count = 0
    for path in pending_directory().iterdir():
        if path.is_file() and _PENDING_NAME.match(path.name) and path.stat().st_mtime < limit:
            path.unlink(missing_ok=True)
            count += 1
    return count


# --- The text of the invoice -----------------------------------------------------------------------------


class InvoiceTextError(Exception):
    """The invoice cannot be read; ``str(error)`` says why, for the user."""


class InvoiceText(str):
    """The text of an invoice – a ``str``; ``note`` says, for the user, when only its first part was read."""

    note = ""


def invoice_text(path: Path) -> InvoiceText:
    """The text of a PDF invoice – only PDFs with a text layer; a scan is not read (no OCR, MAT-062).

    What reading costs is bounded (a PDF of a few KB kept a worker busy for many seconds): the pages
    are read in order, at most :data:`MAX_PDF_PAGES`, and reading stops before a page that would bring the work
    beyond :data:`MAX_PDF_WORK_BYTES` (:func:`_page_work`), once :data:`MAX_TEXT_CHARS` characters are there, or
    after :data:`MAX_PDF_SECONDS`. ``note`` of the result then says that only the first pages were read.

    Raises:
        InvoiceTextError: pypdf is missing, the file is no readable PDF, it has no text, or its first page alone
            is too much to read.
    """
    try:
        from pypdf import PdfReader, apply_configuration
    except ImportError as error:  # pragma: no cover - pypdf is part of the requirements
        raise InvoiceTextError(_("This server cannot read PDF files. Enter the purchase by hand.")) from error
    if path.suffix.lower() != ".pdf":
        raise InvoiceTextError(_("Only PDF files with text can be read. The file is attached all the same."))
    started = time.monotonic()
    budget = MAX_PDF_WORK_BYTES
    room = MAX_TEXT_CHARS
    lines: list[str] = []
    known_files: set[int] = set()
    read = total = 0
    cut = too_much = False
    try:
        with apply_configuration(**_PDF_LIMITS):
            reader = PdfReader(str(path))
            if reader.is_encrypted:
                reader.decrypt("")
            total = len(reader.pages)
            for index in range(min(total, MAX_PDF_PAGES)):
                page = reader.pages[index]
                work = _page_work(page, budget, known_files)
                too_much = work > budget or (index > 0 and time.monotonic() - started > MAX_PDF_SECONDS)
                if too_much:
                    break
                budget -= work
                raw = page.extract_text() or ""
                read += 1
                # At most MAX_TEXT_CHARS characters are looked at, over all pages, before they are cleaned.
                cut = len(raw) > room
                raw = raw[:room]
                room -= len(raw)
                lines.extend(cleaned for line in raw.splitlines() if (cleaned := " ".join(_printable(line).split())))
                if room <= 0:
                    break
    except Exception as error:  # pypdf raises many kinds of errors on broken files
        raise InvoiceTextError(_("The file could not be read as a PDF.")) from error
    text = InvoiceText("\n".join(lines)[:MAX_TEXT_CHARS])
    if len(text) < MIN_TEXT_CHARS:
        if too_much:
            raise InvoiceTextError(
                _("The PDF holds too much to be read. Enter the purchase by hand – the file is attached all the same.")
            )
        raise InvoiceTextError(
            _("The PDF has no text – probably a scan. Scans are not read; enter the purchase by hand.")
        )
    if read < total:
        text.note = ngettext(
            "Only the first page of %(total)d was read: the invoice is too long. Enter the positions of the other "
            "pages by hand.",
            "Only the first %(count)d of %(total)d pages were read: the invoice is too long. Enter the positions of "
            "the other pages by hand.",
            read,
        ) % {"count": read, "total": total}
    elif cut:
        text.note = end_not_read_note()
    return text


def end_not_read_note() -> str:
    """The note that the end of an invoice was not read – here, or by the AI (MAT-076)."""
    return _("The invoice is too long: its end was not read. Enter the last positions by hand.")


def _printable(text: str) -> str:
    """The text without control characters."""
    return "".join(character for character in text if unicodedata.category(character)[0] != "C" or character == "\n")


def _page_work(page: Any, limit: int, known_files: set[int]) -> int:
    """What extracting the text of a page costs, in bytes pypdf parses for it; above ``limit`` counting stops.

    Review (MAT-062): its content stream(s), the fonts of the page and every form it draws, as often as it
    draws it – pypdf parses a form and builds the fonts anew each time. A stream drawn on several pages counts on
    each, as its text is extracted on each; it is decompressed only once (pypdf keeps the result). A stream that
    does not even decompress within pypdf's limits (:data:`_PDF_LIMITS`) is too much.
    """
    from pypdf.errors import LimitReachedError

    try:
        data = _stream_data(page.get("/Contents"), limit)
        return _drawing_work(data, page.get("/Resources"), limit, known_files, {}, 0)
    except LimitReachedError:
        return limit + 1


def _resolved(value: Any) -> Any:
    """A PDF object with its reference followed."""
    return value.get_object() if value is not None and hasattr(value, "get_object") else value


def _stream_data(value: Any, limit: int) -> bytes:
    """The decompressed data of a stream or of an array of streams (a page's content); stops once above ``limit``."""
    from pypdf.generic import StreamObject

    value = _resolved(value)
    data = bytearray()
    for part in value if isinstance(value, list) else [value]:
        part = _resolved(part)
        if isinstance(part, StreamObject):
            data += part.get_data()
            if len(data) > limit:
                break
    return bytes(data)


def _drawing_work(
    data: bytes, resources: Any, limit: int, known_files: set[int], forms_done: dict[int, int], depth: int
) -> int:
    """The work of a content stream (of a page or a form): its bytes, its fonts, the forms it draws, recursively.

    A form is counted as often as its name stands in the stream – each mention a drawing, which can only count
    too much. ``forms_done`` keeps the work of each form already counted for the page.
    """
    from pypdf.generic import StreamObject

    resources = _resolved(resources)
    if not isinstance(resources, dict):
        return len(data)
    work = len(data) + _fonts_work(_resolved(resources.get("/Font")), limit, known_files)
    xobjects = _resolved(resources.get("/XObject"))
    if work > limit or not isinstance(xobjects, dict):
        return work
    forms = {}
    for key, value in xobjects.items():
        value = _resolved(value)
        if isinstance(value, StreamObject) and value.get("/Subtype") != "/Image":  # images are not read
            forms[str(key)] = value
    if not forms:
        return work
    for key, count in _names_in(data, set(forms)).items():
        form = forms[key]
        each = forms_done.get(id(form))
        if each is None:
            if depth >= _MAX_FORM_DEPTH:
                return limit + 1
            forms_done[id(form)] = limit + 1  # a form that draws itself is no invoice
            each = _drawing_work(
                _stream_data(form, limit), form.get("/Resources"), limit, known_files, forms_done, depth + 1
            )
            forms_done[id(form)] = each
        work += count * each
        if work > limit:
            break
    return work


def _fonts_work(fonts: Any, limit: int, known_files: set[int]) -> int:
    """The work of the fonts of a page or form: each font, its character map; a font program read once only.

    pypdf reads the program of a Type 1 font without character map (``/ToUnicode``) for its encoding, once for
    the whole file (``known_files``).
    """
    from pypdf.generic import StreamObject

    if not isinstance(fonts, dict):
        return 0
    work = 0
    for value in fonts.values():
        font = _resolved(value)
        if not isinstance(font, dict):
            continue
        work += _FONT_WORK_BYTES
        to_unicode = _resolved(font.get("/ToUnicode"))
        for stream in (to_unicode, _resolved(font.get("/Encoding"))):
            if isinstance(stream, StreamObject):
                work += len(stream.get_data())
        descriptor = _resolved(font.get("/FontDescriptor"))
        if to_unicode is None and isinstance(descriptor, dict):
            for key in ("/FontFile", "/FontFile3"):
                program = _resolved(descriptor.get(key))
                if isinstance(program, StreamObject) and id(program) not in known_files:
                    known_files.add(id(program))
                    work += len(program.get_data())
        if work > limit:
            break
    return work


def _names_in(data: bytes, wanted: set[str]) -> dict[str, int]:
    """How often each of the ``wanted`` names (``/X0``) stands in a content stream – escapes (``/X#30``) decoded."""
    from pypdf.generic import NameObject

    found: dict[str, int] = {}
    for token, count in Counter(_PDF_NAME.findall(data)).items():
        raw = NameObject.unnumber(token)
        name = None
        for charset in NameObject.CHARSETS:
            with contextlib.suppress(UnicodeDecodeError):
                name = raw.decode(charset)
                break
        if name is None:
            name = raw.decode("charmap", errors="replace")
        if name in wanted:
            found[name] = found.get(name, 0) + count
    return found


# --- Head data from the text, without AI ---------------------------------------------------------------------

_NUMBER_LABEL = re.compile(
    r"(?:rechnungs?[\s-]*(?:nummer|nr\.?|no\.?)|rechnung\s*(?:nummer|nr\.?|no\.?|#)|invoice\s*(?:number|no\.?|#))"
    r"\s*[:#.]?\s*(?P<value>[A-Za-z0-9][A-Za-z0-9\-/._]{0,59})?",
    re.IGNORECASE,
)
_DATE_LABEL = re.compile(
    r"(?:rechnungsdatum|belegdatum|invoice\s*date|datum|date)\s*[:.]?\s*(?P<value>[^\s].*)?", re.IGNORECASE
)
_DATE_DE = re.compile(r"\b(?P<d>\d{1,2})\.\s?(?P<m>\d{1,2})\.\s?(?P<y>\d{4}|\d{2})\b")
_DATE_ISO = re.compile(r"\b(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})\b")


def _date_in(text: str) -> datetime.date | None:
    """The first plausible date in a text: ``22.02.2027``, ``22.2.27`` or ``2027-02-22``."""
    for pattern in (_DATE_DE, _DATE_ISO):
        for match in pattern.finditer(text or ""):
            year = int(match["y"])
            year = year + 2000 if year < 100 else year
            with contextlib.suppress(ValueError):
                found = datetime.date(year, int(match["m"]), int(match["d"]))
                if plausible_date(found):
                    return found
    return None


def plausible_date(value: datetime.date) -> bool:
    """An invoice date between 1990 and a year from today."""
    today = timezone.localdate()
    return datetime.date(1990, 1, 1) <= value <= today + datetime.timedelta(days=366)


def head_from_text(text: str) -> dict[str, Any]:
    """Invoice number, invoice date and supplier found in the text by simple patterns – the way without AI (MAT-062).

    * the number after "Rechnungsnummer", "Rechnung Nr.", "Invoice No." –
      on the same line or the next;
    * the date after "Rechnungsdatum", "Datum", "Invoice date", else the
      first date of the text;
    * the supplier: an existing supplier whose name stands in the text,
      the first lines (the letterhead) first;
    * MAT-076: the net total and the amount to pay after their
      labels (:func:`totals_in_text`), read as the invoice writes its amounts
      (:func:`invoice_numbers`, the same reading as the answer of the AI), and
      the currency.

    Returns:
        ``{"supplier": Supplier | None, "invoice_number": str, "invoice_date": date | None,
        "total_net": Decimal | None, "total_gross": Decimal | None, "currency": str}``
    """
    lines = (text or "").splitlines()
    number = ""
    for index, line in enumerate(lines):
        match = _NUMBER_LABEL.search(line)
        if match is None:
            continue
        value = match["value"] or ""
        if not value and index + 1 < len(lines):
            value = (lines[index + 1].split() or [""])[0]
        value = value.strip(".:,;")
        if value and any(character.isdigit() for character in value):
            number = value[:60]
            break
    date = None
    for index, line in enumerate(lines):
        match = _DATE_LABEL.search(line)
        if match is None:
            continue
        date = _date_in(match["value"] or "") or (_date_in(lines[index + 1]) if index + 1 < len(lines) else None)
        if date is not None:
            break
    if date is None:
        date = _date_in(text)
    totals = totals_in_text(text)
    return {
        "supplier": supplier_in_text(lines),
        "invoice_number": number,
        "invoice_date": date,
        "total_net": totals["net"],
        "total_gross": totals["gross"],
        "currency": _currency_in(text or ""),
    }


# --- Matching suppliers and models ------------------------------------------------------------------------

#: Parts of company names that say nothing about which company it is.
_LEGAL_WORDS = frozenset(
    {"gmbh", "mbh", "ag", "kg", "ohg", "gbr", "ug", "ek", "e", "k", "co", "inc", "ltd", "llc", "se", "kgaa",
     "haftungsbeschränkt", "und", "and", "the"}
)  # fmt: skip
#: Words of invoice positions that say nothing about the article.
_FILLER_WORDS = frozenset({"stk", "stück", "st", "pcs", "x", "mit", "für", "und", "inkl", "the", "and", "with", "for"})


def normalised(text: str) -> str:
    """A name for comparing: lower case, without punctuation, legal forms and double spaces."""
    text = unicodedata.normalize("NFKC", text or "").casefold().replace("ß", "ss")
    words = re.sub(r"[^\w]+", " ", text).split()
    return " ".join(word for word in words if word not in _LEGAL_WORDS)


def _words(text: str) -> list[str]:
    """The words of an article description that carry meaning."""
    return [word for word in normalised(text).split() if word not in _FILLER_WORDS and len(word) > 1]


def match_supplier(name: str) -> Supplier | None:
    """The existing supplier meant by a name read from an invoice – exact, or nearly so; else ``None`` (MAT-062).

    "fuzzy-light": the same name in any case, the same name without legal
    form and punctuation ("Musikhaus Muster GmbH & Co. KG" = "Musikhaus
    Muster"), one name inside the other, or names that differ by a letter or
    two. Never a guess beyond that: a new name becomes a new supplier.
    """
    name = (name or "").strip()
    if not name:
        return None
    exact = Supplier.objects.filter(name__iexact=name).order_by("-is_active", "pk").first()
    if exact is not None:
        return exact
    target = normalised(name)
    if not target:
        return None
    best: tuple[float, Supplier] | None = None
    for supplier in Supplier.objects.order_by("-is_active", "pk").only("pk", "name", "is_active"):
        other = normalised(supplier.name)
        if not other:
            continue
        if other == target:
            score = 1.0
        elif min(len(other), len(target)) >= 5 and (f" {other} " in f" {target} " or f" {target} " in f" {other} "):
            score = 0.95
        else:
            score = SequenceMatcher(None, other, target).ratio()
        if score >= 0.88 and (best is None or score > best[0]):
            best = (score, supplier)
    return best[1] if best else None


def supplier_in_text(lines: list[str]) -> Supplier | None:
    """An existing supplier whose name stands in the text – the letterhead (first lines) first.

    The company's own name is no supplier (it stands in the address of
    every invoice it receives); the longest name found wins.
    """
    from rentalars.core.models import CompanyProfile

    own = normalised(CompanyProfile.load().name or "")
    suppliers = [
        (normalised(supplier.name), supplier) for supplier in Supplier.objects.filter(is_active=True).only("pk", "name")
    ]
    suppliers = [(name, supplier) for name, supplier in suppliers if len(name) >= 3 and name != own]
    for part in (lines[:15], lines):
        text = f" {normalised(' '.join(part))} "
        found = [(len(name), supplier) for name, supplier in suppliers if f" {name} " in text]
        if found:
            return max(found, key=lambda pair: pair[0])[1]
    return None


@dataclass
class Candidate:
    """A model that may be meant by a position of the invoice."""

    model: MaterialModel
    score: float

    @property
    def certain(self) -> bool:
        """The same name, or the supplier's article number of an item of it: filled in (still to be checked)."""
        return self.score >= 0.999


def model_candidates(
    description: str,
    *,
    manufacturer: str = "",
    article_number: str = "",
    supplier: Supplier | None = None,
    limit: int = 3,
) -> list[Candidate]:
    """Existing models that may be meant by a position – the best first; certain ones only for an exact match.

    Certain: a model of exactly this name (also with the manufacturer in
    front), or a model of which an item was bought with this article number
    of the supplier. Otherwise similar names, offered as suggestions only.
    """
    description = (description or "").strip()
    found: dict[int, Candidate] = {}

    def note(model: MaterialModel, score: float) -> None:
        if is_customer_model(model):
            return  # MAT-076 (PRD-043): bought items never join customer material
        if model.pk not in found or found[model.pk].score < score:
            found[model.pk] = Candidate(model, score)

    if article_number.strip():
        items = MaterialItem.objects.filter(supplier_article_number__iexact=article_number.strip())
        if supplier is not None:
            items = items.filter(supplier=supplier)
        for model in MaterialModel.objects.filter(pk__in=items.values("material_model_id"))[:5]:
            note(model, 1.0)
    names = {description}
    if manufacturer.strip() and not normalised(description).startswith(normalised(manufacturer)):
        names.add(f"{manufacturer.strip()} {description}")
    for name in names:
        if name:
            for model in MaterialModel.objects.filter(Q(name__iexact=name) | Q(short_name__iexact=name))[:3]:
                note(model, 1.0)
    words = sorted(set(_words(f"{manufacturer} {description}")), key=len, reverse=True)[:5]
    words = [word for word in words if len(word) >= 3]
    if words:
        query = Q()
        for word in words:
            query |= Q(name__icontains=word) | Q(short_name__icontains=word) | Q(manufacturer__name__icontains=word)
        wanted = set(words)
        target = normalised(description)
        for model in MaterialModel.objects.filter(query).select_related("manufacturer")[:300]:
            label = f"{model.manufacturer.name if model.manufacturer_id else ''} {model.name}"
            own = set(_words(label))
            overlap = len(own & wanted) / max(1, len(own | wanted))
            ratio = SequenceMatcher(None, normalised(model.name), target).ratio()
            score = min(0.98, max(ratio, overlap))
            if score >= 0.5:
                note(model, score)
    return sorted(found.values(), key=lambda candidate: (-candidate.score, candidate.model.name))[:limit]


# --- The proposal for the page and the API -------------------------------------------------------------------


def _money_text(value: Decimal | None) -> str:
    return "" if value is None else f"{value:.2f}"


def _proposed_hints(category_text: str, why_category: str, product_text: str, why_product: str) -> list[str]:
    """What the user should know about a category or product the AI proposed and Rentalars did not fill in."""
    hints = []
    if why_category == "ambiguous":
        hints.append(
            _("The AI proposed the category “%(name)s”, which fits several categories: choose one yourself.")
            % {"name": category_text}
        )
    elif why_category == "unknown":
        hints.append(
            _("The AI proposed the category “%(name)s”, which does not exist: choose the category yourself.")
            % {"name": category_text}
        )
    if why_product == "ambiguous":
        hints.append(
            _("The AI proposed the product “%(name)s”, which fits several products: choose one or leave it empty.")
            % {"name": product_text}
        )
    elif why_product == "unknown":
        hints.append(
            _("The AI proposed the product “%(name)s”, which does not exist: choose one or leave it empty.")
            % {"name": product_text}
        )
    return hints


def build_proposal(
    *,
    supplier_name: str = "",
    supplier: Supplier | None = None,
    invoice_number: str = "",
    invoice_date: datetime.date | None = None,
    positions: list[dict[str, Any]] | None = None,
    prices: str = "net",
    tax_rate: str = "",
    source: str = "text",
    note: str = "",
    total_net: Decimal | None = None,
    total_gross: Decimal | None = None,
    currency: str = "",
) -> dict[str, Any]:
    """What the page fills in and the API returns: head and positions, matched against what exists.

    ``positions`` are plain values already checked (``description``,
    ``quantity``, ``unit_price``, ``manufacturer``, ``article_number``;
    ``serial_numbers``, ``category`` and ``product`` as the AI proposed
    them (MAT-076), ``serials_left_out``). The supplier is matched
    (:func:`match_supplier`); each position gets the models that may be
    meant, but a model only where it is certain (:func:`model_candidates`) –
    otherwise the description as the name of a new model, to be checked.
    ``note``: what the user should know about the reading, e.g. that only the
    first pages were read (:class:`InvoiceText`).

    MAT-076: an existing model brings its category and product;
    for a new model the category and product the AI proposed are filled in
    only if they name an existing one exactly or unambiguously
    (:func:`match_category`, :func:`match_product`) – otherwise ``hints`` say
    why the field stayed empty. ``total_net`` and ``total_gross`` of the
    invoice, for the user to compare with the sum of the positions.
    """
    if supplier is None and supplier_name:
        supplier = match_supplier(supplier_name)
    categories: list[Category] | None = None
    rows = []
    for raw in (positions or [])[:MAX_POSITIONS]:
        description = str(raw.get("description") or "")[:200]
        candidates = model_candidates(
            description,
            manufacturer=str(raw.get("manufacturer") or ""),
            article_number=str(raw.get("article_number") or ""),
            supplier=supplier,
        )
        certain = candidates[0].model if candidates and candidates[0].certain else None
        hints: list[str] = []
        if certain is not None:
            category, product = certain.category, certain.default_product
        else:
            if categories is None:
                categories = purchase_categories()
            category_text = str(raw.get("category") or "")[:200]
            product_text = str(raw.get("product") or "")[:250]
            category, why_category = match_category(category_text, categories)
            product, why_product = match_product(product_text)
            hints = _proposed_hints(category_text, why_category, product_text, why_product)
        left_out = int(raw.get("serials_left_out") or 0)
        if left_out:
            hints.append(
                ngettext(
                    "%(count)d serial number of the AI is not on the invoice and was left out.",
                    "%(count)d serial numbers of the AI are not on the invoice and were left out.",
                    left_out,
                )
                % {"count": left_out}
            )
        rows.append(
            {
                "description": description,
                "quantity": int(raw.get("quantity") or 1),
                "unit_price": _money_text(raw.get("unit_price")),
                "manufacturer": str(raw.get("manufacturer") or "")[:120],
                "article_number": str(raw.get("article_number") or "")[:120],
                "model": certain.name if certain else description[:200],
                "model_id": certain.pk if certain else None,
                "new_model": certain is None,
                "candidates": [
                    {"id": candidate.model.pk, "name": candidate.model.name, "score": round(candidate.score, 2)}
                    for candidate in candidates
                ],
                "serial_numbers": [str(serial)[:120] for serial in raw.get("serial_numbers") or []][
                    : services.MAX_ITEMS_PER_BATCH
                ],
                "category_id": category.pk if category is not None else None,
                "category": category.path if category is not None else "",
                "product_id": product.pk if product is not None else None,
                "product": product_label(product) if product is not None else "",
                "hints": hints,
            }
        )
    return {
        "source": source,
        "supplier": {
            "name": supplier.name if supplier is not None else (supplier_name or "")[:120],
            "read_as": (supplier_name or "")[:120],
            "id": supplier.pk if supplier is not None else None,
            "existing": supplier is not None,
        },
        "invoice_number": (invoice_number or "")[:60],
        "invoice_date": invoice_date.isoformat() if invoice_date else "",
        "prices": prices if prices in {"net", "gross"} else "net",
        "tax_rate": tax_rate,
        "total_net": _money_text(total_net),
        "total_gross": _money_text(total_gross),
        "currency": currency,
        "positions": rows,
        "note": note,
    }


def proposal_from_text(text: str) -> dict[str, Any]:
    """The proposal without AI: only the head, found by patterns (:func:`head_from_text`).

    The ``note`` of a text of:func:`invoice_text` goes along (only the first pages read); since
    MAT-076: the totals of the invoice as well.
    """
    head = head_from_text(text)
    supplier = head["supplier"]
    return build_proposal(
        supplier_name=supplier.name if supplier is not None else "",
        supplier=supplier,
        invoice_number=head["invoice_number"],
        invoice_date=head["invoice_date"],
        source="text",
        note=getattr(text, "note", ""),
        total_net=head["total_net"],
        total_gross=head["total_gross"],
        currency=head["currency"],
    )


def parse_decimal_text(value: Any) -> Decimal | None:
    """A price from an answer or a form: ``12.5``, ``"1.234,56"``, ``"12,50 €"``; ``None`` if it is none.

    Rounded to cents. The same reading as :func:`parse_amount` (MAT-076), German style.
    """
    number = parse_amount(value)
    return None if number is None else money(number)


def without_prices(proposal: dict[str, Any]) -> dict[str, Any]:
    """AUT-019: a proposal for who may not see purchase prices – no prices, no invoice totals (MAT-076)."""
    proposal["prices"] = "net"
    proposal["total_net"] = proposal["total_gross"] = ""
    for position in proposal.get("positions") or []:
        position["unit_price"] = ""
    return proposal


# --- Amounts as invoices and answers write them (MAT-076; MAT-062) --------------------------------------
#
# The problem: the AI read a price of 1.072,50 as 1,07. German invoices write "1.072,50", English ones
# "1,072.50"; a model asked for "numbers with a dot" wrote 1.072 or 1.0725. Rentalars now asks for amounts as
# written and reads them itself: the form of the number, the style of the invoice and its text decide.

#: Currency signs and codes around an amount – they say nothing about its value.
_CURRENCY = re.compile(r"(?i)€|(?<![a-z])(?:euros?|eur|usd|gbp|chf)(?![a-z])|us\$|\$|£")
#: Spaces of all kinds and apostrophes (Swiss "1'072.50") inside an amount.
_GAPS = re.compile(r"[\s   '’]")
#: What remains of an amount: digits with dots and commas.
_AMOUNT_SHAPE = re.compile(r"\d[\d.,]*|[.,]\d+")
#: An amount with cents in a text ("1.072,50", "99,00", "1,072.50"); dates and article numbers have none.
_MONEY_TOKEN = re.compile(r"\d[\d.,']*\d")
#: Words of German and English invoices – the language decides the style when the amounts do not.
_GERMAN_WORDS = frozenset(
    {"rechnung", "rechnungsnummer", "rechnungsdatum", "menge", "einzelpreis", "gesamtpreis", "mwst", "ust",
     "netto", "brutto", "betrag", "summe", "gesamt", "lieferschein", "bankverbindung", "zahlbar", "stück"}
)  # fmt: skip
_ENGLISH_WORDS = frozenset(
    {"invoice", "quantity", "qty", "unit", "price", "vat", "total", "amount", "subtotal", "due", "payment",
     "delivery", "description", "pcs"}
)  # fmt: skip


class NumberLiteral(str):
    """A number as the JSON of an answer wrote it (``1.072``), kept as text so that its form can be judged (MAT-076).

    ``json.loads(…, parse_float=NumberLiteral)``: a JSON number always has a decimal point, so it says nothing
    about the style of the invoice – but "1.072" may still be a German 1072 the model copied.
    """


def _amount_text(value: Any) -> str | None:
    """The bare amount of a value – currency, spaces and a closing ",-" removed; ``None`` if it cannot be one."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value) if math.isfinite(value) else None
    if isinstance(value, Decimal):
        return format(value, "f") if value.is_finite() else None
    if not isinstance(value, str):
        return None
    # A currency and spaces may stand around the number; anything else makes it no amount ("1e400", "ca. 5").
    text = re.sub(r"[.,]-{1,2}$", "", _GAPS.sub("", _CURRENCY.sub("", value[:40])))
    body = text[1:] if text[:1] in "+-" else text
    return text if len(body) <= 30 and _AMOUNT_SHAPE.fullmatch(body) else None


def _grouped(text: str, mark: str) -> bool:
    """Whether digits are grouped in thousands by ``mark`` (``1.072.500``): a first group of 1 to 3, then threes."""
    first, *groups = text.split(mark)
    return (
        bool(groups)
        and re.fullmatch(r"[1-9]\d{0,2}", first) is not None
        and all(len(group) == 3 and group.isdigit() for group in groups)
    )


def _ambiguous_pair(whole: str, fraction: str) -> bool:
    """``1.072``: one mark with exactly three digits behind it and 1 to 3 in front – 1072 or 1.072."""
    return len(fraction) == 3 and fraction.isdigit() and re.fullmatch(r"[1-9]\d{0,2}", whole) is not None


def _ambiguous(text: str) -> bool:
    """Whether an amount reads differently in German and English style (``1.072``, ``1,072``)."""
    body = text.lstrip("+-")
    marks = [character for character in body if character in ".,"]
    if len(marks) != 1:
        return False
    whole, _mark, fraction = body.partition(marks[0])
    return _ambiguous_pair(whole, fraction)


def _plain_number(text: str, decimal_comma: bool) -> str | None:
    """The digits of an amount without sign with a decimal point only (``1072.50``); ``None`` if malformed."""
    dots, commas = text.count("."), text.count(",")
    if not dots and not commas:
        return text
    if dots and commas:
        # Both marks: the last one is the decimal mark, the other groups the thousands ("1.072,50", "1,072.50").
        point = "." if text.rfind(".") > text.rfind(",") else ","
        group = "," if point == "." else "."
        whole, _mark, fraction = text.rpartition(point)
        if point in whole or not fraction or not _grouped(whole, group):
            return None
        return whole.replace(group, "") + "." + fraction
    mark = "." if dots else ","
    parts = text.split(mark)
    if len(parts) > 2:
        if _grouped(text, mark):
            return "".join(parts)  # 1.072.500
        if 1 <= len(parts[-1]) <= 2 and _grouped(mark.join(parts[:-1]), mark):
            return "".join(parts[:-1]) + "." + parts[-1]  # 1.072.50: a model put a point for the comma
        return None
    whole, fraction = parts
    if not fraction:
        return None
    if _ambiguous_pair(whole, fraction) and mark == ("." if decimal_comma else ","):
        return whole + fraction  # 1.072 on a German invoice: one thousand and seventy-two
    return (whole or "0") + "." + fraction


def parse_amount(value: Any, *, decimal_comma: bool = True) -> Decimal | None:
    """An amount as an invoice, an answer or a person writes it; ``None`` if it is none (MAT-076).

    German ``1.072,50`` and ``1072,50``, English ``1,072.50`` and ``1072.50``, a JSON number ``1072.5``, with
    "€", "EUR" and spaces around it, ``1.072,-``. Only one mark followed by exactly three digits is ambiguous –
    ``1.072`` is 1072 in German and 1.072 in English: ``decimal_comma`` (the style of the invoice, see
    :func:`invoice_numbers`) decides; by default German, so on a euro invoice a point before three digits groups
    the thousands. The value is not rounded.
    """
    text = _amount_text(value)
    if text is None:
        return None
    sign = text[0] if text[:1] in "+-" else ""
    plain = _plain_number(text.lstrip("+-"), decimal_comma)
    if plain is None:
        return None
    try:
        number = Decimal(sign + plain)
    except InvalidOperation:
        return None
    if not number.is_finite() or abs(number) >= Decimal("1e15"):
        return None
    return number


def _style_vote(value: Any) -> int:
    """+1 if an amount shows the German style (``1.072,50``, ``99,00``), -1 the English one, 0 if it shows none."""
    if isinstance(value, NumberLiteral) or not isinstance(value, str):
        return 0  # a JSON number always has a point
    text = _amount_text(value)
    if not text:
        return 0
    body = text.lstrip("+-")
    dots, commas = body.count("."), body.count(",")
    if dots and commas:
        return 1 if body.rfind(",") > body.rfind(".") else -1
    if not dots and not commas:
        return 0
    mark = "." if dots else ","
    parts = body.split(mark)
    if len(parts) > 2:
        return (1 if mark == "." else -1) if _grouped(body, mark) else 0
    if 1 <= len(parts[1]) <= 2:
        return 1 if mark == "," else -1
    return 0


def currency_code(text: Any) -> str:
    """A currency as its code: "€", "Euro" → ``EUR``; "$" → ``USD``; "£" → ``GBP``; other codes as they are."""
    value = str(text or "").strip().casefold()
    for code, names in (
        ("EUR", {"€", "eur", "euro", "euros"}),
        ("USD", {"$", "usd", "us$", "dollar"}),
        ("GBP", {"£", "gbp", "pound"}),
        ("CHF", {"chf", "fr.", "franken"}),
    ):
        if value in names:
            return code
    return value.upper() if re.fullmatch(r"[a-z]{3}", value) else ""


def _currency_in(text: str) -> str:
    """The currency an invoice text names most often; ``""`` if none."""
    counts = {
        "EUR": text.count("€") + len(re.findall(r"(?i)(?<![a-z])eur(?:o|os)?(?![a-z])", text)),
        "USD": text.count("$") + len(re.findall(r"(?i)(?<![a-z])usd(?![a-z])", text)),
        "GBP": text.count("£") + len(re.findall(r"(?i)(?<![a-z])gbp(?![a-z])", text)),
        "CHF": len(re.findall(r"(?i)(?<![a-z])chf(?![a-z])", text)),
    }
    code, count = max(counts.items(), key=lambda pair: pair[1])
    return code if count else ""


def _money_tokens(text: str) -> list[str]:
    """The amounts with cents in a text, as written: "1.072,50", "99,00" – no dates, no plain numbers."""
    return [token for token in _MONEY_TOKEN.findall(text or "") if re.search(r"[.,]\d{2}$", token)]


def _text_style(text: str, currency: str = "") -> bool:
    """Whether an invoice text writes its amounts the German way: by its amounts, its currency, its language."""
    vote = sum(_style_vote(token) for token in _money_tokens(text))
    if vote:
        return vote > 0
    currency = currency or _currency_in(text or "")
    if currency in {"USD", "GBP", "CHF"}:
        return False
    if currency == "EUR":
        return True
    words = set(normalised(text or "").split())
    german, english = len(words & _GERMAN_WORDS), len(words & _ENGLISH_WORDS)
    return german >= english


def _digit_key(text: str) -> str:
    """The digits of an amount without leading and trailing zeros: "1.0725" and "1.072,50" both ``10725``."""
    return re.sub(r"\D", "", text).strip("0")


@dataclass(frozen=True)
class InvoiceNumbers:
    """How the amounts of one invoice are written, and which amounts its text holds (MAT-076).

    ``decimal_comma``: German style (``1.072,50``), else English (``1,072.50``). ``amounts``: every amount with
    cents in the invoice text – what an amount of the answer is checked against (:meth:`amount`).
    """

    decimal_comma: bool = True
    amounts: frozenset[Decimal] = frozenset()

    def amount(self, value: Any) -> Decimal | None:
        """An amount of the answer, read in this style and – where its form leaves doubt – checked with the text.

        "1.072" that is not on the invoice while "1.072,50" is (a model that dropped the cents, or read the point
        the English way): 1072.50. "1.0725" (a model that dropped the comma) with "1.072,50" on the invoice:
        1072.50 as well. Only one amount of the text may fit; otherwise the amount stays as read.
        """
        parsed = parse_amount(value, decimal_comma=self.decimal_comma)
        if parsed is None or not self.amounts:
            return parsed
        exact = parsed == money(parsed)
        if exact and parsed in self.amounts:
            return parsed
        text = _amount_text(value) or ""
        options: set[Decimal] = set()
        if _ambiguous(text):
            readings = {
                reading for style in (True, False) if (reading := parse_amount(value, decimal_comma=style)) is not None
            }
            options |= readings
            thousands = max(readings)
            options |= {amount for amount in self.amounts if amount.to_integral_value(ROUND_FLOOR) == thousands}
        if not exact:
            key = _digit_key(text)
            options |= {amount for amount in self.amounts if _digit_key(f"{amount:.2f}") == key}
        found = {option for option in options if option in self.amounts}
        return found.pop() if len(found) == 1 else parsed


def invoice_numbers(text: str = "", *, currency: str = "", samples: Any = ()) -> InvoiceNumbers:
    """The style of an invoice's amounts and the amounts of its text (MAT-076; MAT-062).

    The style of the answer's amounts, by the first of these that says something: the amounts in ``samples``
    written as text ("99,00" German, "1,072.50" English; JSON numbers say nothing), the amounts of the invoice
    text, the currency (``currency`` or the signs in the text: euro German; dollar, pound, franc English), the
    language of the text; else German. The amounts of the text are read in the style of the text itself.
    """
    text_style = _text_style(text, currency)
    amounts = frozenset(
        money(amount)
        for token in _money_tokens(text)
        if (amount := parse_amount(token, decimal_comma=text_style)) is not None and amount >= 0
    )
    vote = sum(_style_vote(sample) for sample in samples)
    return InvoiceNumbers(decimal_comma=vote > 0 if vote else text_style, amounts=amounts)


# --- The totals of an invoice from its text, without AI (MAT-076) ---------------------------------------

#: A line with the net total: "Nettobetrag", "Summe netto", "Zwischensumme", "Subtotal", "Total net".
_TOTAL_NET = re.compile(r"(?i)\b(?:netto|nettobetrag|nettosumme|warenwert|zwischensumme|sub-?total|net)\b")
#: A line with the amount to pay: "Gesamtbetrag", "Rechnungsbetrag", "zu zahlen", "Brutto", "Total", "Amount due".
_TOTAL_GROSS = re.compile(
    r"(?i)\b(?:gesamtbetrag|rechnungsbetrag|endbetrag|bruttobetrag|bruttosumme|gesamtsumme|zahlbetrag|"
    r"zu\s+zahlen|brutto|gesamt|total|amount\s+due|balance\s+due)\b"
)


def totals_in_text(text: str, numbers: InvoiceNumbers | None = None) -> dict[str, Decimal | None]:
    """The net total and the amount to pay of an invoice, found by their labels (MAT-076).

    The amount stands on the line of its label – the last one there – or alone on the next line. Of several
    such lines the largest amount wins (a page's subtotal is smaller). An amount to pay below the net total
    is no amount to pay.

    Returns:
        ``{"net": Decimal | None, "gross": Decimal | None}``
    """
    numbers = numbers or invoice_numbers(text)
    lines = (text or "").splitlines()
    found: dict[str, list[Decimal]] = {"net": [], "gross": []}
    for index, line in enumerate(lines):
        kind = "net" if _TOTAL_NET.search(line) else "gross" if _TOTAL_GROSS.search(line) else ""
        if not kind:
            continue
        tokens = _money_tokens(line)
        if not tokens and index + 1 < len(lines):
            following = _money_tokens(lines[index + 1])
            if len(following) == 1 and _amount_text(lines[index + 1]) is not None:
                tokens = following  # the label on one line, the amount alone on the next
        amount = parse_amount(tokens[-1], decimal_comma=numbers.decimal_comma) if tokens else None
        if amount is not None and 0 <= amount < Decimal("1e9"):
            found[kind].append(money(amount))
    net = max(found["net"], default=None)
    gross = max(found["gross"], default=None)
    if net is not None and gross is not None and gross < net:
        gross = None
    return {"net": net, "gross": gross}


# --- Categories and products for new models (MAT-076; MAT-048) -----------------------------------------


def purchase_categories() -> list[Category]:
    """The categories a bought model may get – the list the AI chooses from (MAT-076).

    Active, in tree order, of a main category with stock of its own that is not customer material (PRD-043).
    """
    return [
        category
        for category in Category.objects.in_tree_order(only_active=True)
        if category.main_category.has_own_stock and not category.main_category.is_customer_material
    ]


def _category_key(text: str) -> str:
    """A category name or path for comparing: case, spaces, the separator and a code in brackets do not matter."""
    text = unicodedata.normalize("NFKC", text or "").casefold().replace("ß", "ss")
    text = re.sub(r"\s*\([^()]*\)\s*$", "", text)  # "Ton (T)" as the list names a main category
    parts = (" ".join(part.split()) for part in re.split(r"[>»/|\\]", text))
    return " > ".join(part for part in parts if part)


def match_category(text: str, categories: list[Category] | None = None) -> tuple[Category | None, str]:
    """The existing category a proposal names – exactly or unambiguously – else ``None`` and why (MAT-076).

    Exactly: its path ("Ton > Mikrofone", in any case, any separator) or the code of a main category ("T").
    Unambiguously: the name of one category alone ("Mikrofone"). Why not: ``"unknown"`` or ``"ambiguous"``;
    ``""`` when nothing was proposed.
    """
    text = " ".join(str(text or "").split())
    if not text:
        return None, ""
    categories = purchase_categories() if categories is None else categories
    key = _category_key(text)
    for found in (
        [category for category in categories if _category_key(category.path) == key],
        [
            category
            for category in categories
            if not category.parent_id and category.code and category.code.casefold() == key
        ],
        [category for category in categories if _category_key(category.name) == key],
    ):
        if len(found) == 1:
            return found[0], ""
        if found:
            return None, "ambiguous"
    return None, "unknown"


def purchase_products() -> Any:
    """The products a bought model may belong to: active rental and sale products, vehicles (MAT-048, LOG-002).

    Review (MAT-076, PRD-043): never customer material – what is bought is the company's, and the names of
    a customer's products do not go to the AI that reads the invoice (:func:`rentalars.ai.invoices.catalogue`).
    """
    from rentalars.products.models import MATERIAL_KINDS

    return Product.objects.filter(kind__in=MATERIAL_KINDS, is_active=True, owner__isnull=True)


def customer_product_error(product: Product) -> str:
    """Why a bought model cannot belong to this product of a customer (MAT-076, PRD-043)."""
    return _(
        "“%(product)s” is customer material of %(owner)s: bought material cannot belong to it. Choose one of your "
        "own products or leave the field empty."
    ) % {"product": product_label(product), "owner": product.owner.name if product.owner_id else ""}


def product_label(product: Product) -> str:
    """A product as the field "Produkt" takes it: its article number in front of its name ("K-005 XLR 5 m")."""
    return f"{product.article_number} {product.name}"


def match_product(text: str) -> tuple[Product | None, str]:
    """The existing product a proposal names – exactly or unambiguously – else ``None`` and why (MAT-076).

    Its article number, alone or in front of its name ("K-005 XLR 5 m"), or its name if no other product has
    it. Why not: ``"unknown"`` or ``"ambiguous"``; ``""`` when nothing was proposed.
    """
    text = " ".join(str(text or "").split())
    if not text:
        return None, ""
    products = purchase_products()
    first = text.split()[0].rstrip(":,;")
    for query in (Q(article_number__iexact=text), Q(article_number__iexact=first), Q(name__iexact=text)):
        found = list(products.filter(query)[:2])
        if len(found) == 1:
            return found[0], ""
        if found:
            return None, "ambiguous"
    return None, "unknown"
