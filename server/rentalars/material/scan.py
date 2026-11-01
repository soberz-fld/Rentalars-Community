# SPDX-License-Identifier: GPL-3.0-or-later
"""What a scanned or typed code stands for (scanning in the browser; MAT-027, UIX-006; PCK-010, PCK-011).

The requirement: barcode and QR scanning in the browser. A phone's camera (``static/js/scan.js``), a hand scanner that types
like a keyboard, and a person typing all deliver the same thing: a text. :func:`resolve` turns that text into what
the application knows under it – one function for the pages, the packing and the API (API-002):

====================  ====================================================================================
code                  result
====================  ====================================================================================
``0042``, ``42``,     the item with this ID (MAT-003, MAT-063); an item that holds other items is a
``#0042``             *case* (``is_case``)
``https://…/m/0042``  the QR code of a label: the address of Einstellungen → Etiketten with ``{id}`` as set
                      there, or the address of the application with ``/m/<ID>``
Code 128 of a label   the ID alone (the label prints the ID as bar code), see the first row
serial number         the item with this serial number (MAT-028); several items with the same serial number:
                      the one ``prefer`` names (the packing list), else the answer says it is ambiguous
GTIN / EAN            the product with this number (PRD-024) – with its material models and items
``01-A-1``            a storage spot (MAT-080): the items that lie there
name of a location    a storage location (MAT-018)
====================  ====================================================================================

Nothing here creates or changes anything. What the reader may see is decided by their rights: a code that leads to
something the reader may not read is answered like a code nobody knows ("none") – a scan must not tell whether
something exists.

The camera pictures never reach the server: the browser decodes them and sends only the text (UIX-006).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.urls import reverse
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Module, Rights
from rentalars.material import numbering
from rentalars.material.models import LabelSettings, MaterialItem
from rentalars.material.spots import normalise_spot

#: What a code can lead to.
ITEM = "item"
PRODUCT = "product"
SPOT = "spot"
LOCATION = "location"
NONE = "none"

#: The longest code taken seriously: a QR code with a long address; anything longer is no label of ours.
MAX_CODE_LENGTH = 300

#: A symbology identifier some scanners put in front (AIM, e.g. ``]Q1`` for a QR code, ``]C0`` for Code 128).
_SYMBOLOGY_PREFIX = re.compile(r"^\][A-Za-z][0-9A-Za-z]")

#: Control characters a scanner may add at the end (carriage return, line feed, tab, group separators).
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")

#: A storage spot such as ``01-A-1`` (normalised by :func:`~rentalars.material.spots.normalise_spot`).
_SPOT = re.compile(r"^\d{2}-[A-Z]-\d$")


@dataclass
class ScanResult:
    """What a code stands for.

    Attributes:
        kind: ``item``, ``product``, ``spot``, ``location`` or ``none``.
        code: The code as cleaned (what was looked up).
        title: What to call it: the ID and name of an item, the name of a product, the spot.
        detail: One line more: status, where it lies, what is in it.
        url: The page of the application for it (the item's page, the list for a spot).
        item: The item, for ``kind == item``.
        product: The product: that of the item, or the one the GTIN names.
        model: The material model of the item.
        count: For a spot or location: how many items lie there.
        contents: For an item: how many items are installed in it plus kinds of bulk material built into it.
        message: For ``none``: why nothing was found.
    """

    kind: str
    code: str
    title: str = ""
    detail: str = ""
    url: str = ""
    item: MaterialItem | None = None
    product: Any = None
    model: Any = None
    count: int = 0
    contents: int = 0
    message: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def found(self) -> bool:
        """Whether the code leads to something."""
        return self.kind != NONE

    @property
    def is_case(self) -> bool:
        """Whether the item holds other items or built-in bulk material (a case, rack or set)."""
        return self.kind == ITEM and self.contents > 0

    @property
    def plan_token(self) -> str:
        """What the product field of the planning takes (``12`` or ``12:i56``, PRJ-065); empty if it cannot be planned."""
        if self.product is None or not getattr(self.product, "is_active", False):
            return ""
        if self.kind == ITEM and self.item is not None:
            return f"{self.product.pk}:i{self.item.pk}"
        return str(self.product.pk)

    @property
    def plan_label(self) -> str:
        """The text the product field shows for :attr:`plan_token`."""
        if self.product is None:
            return ""
        return f"{self.product.article_number} {self.product.name}"


def clean_code(text: str | None) -> str:
    """What was scanned or typed, without the marks a scanner adds: control characters, a symbology prefix, spaces."""
    cleaned = _CONTROL.sub("", text or "").strip()
    cleaned = _SYMBOLOGY_PREFIX.sub("", cleaned)
    return cleaned.strip()[:MAX_CODE_LENGTH]


def _id_from_address(code: str) -> str | None:
    """The ID in the address of a QR code of a label, or ``None`` if the code is no address.

    The address set in Einstellungen → Etiketten (``qr_target`` with ``{id}``) is matched as a pattern first: the ID
    may stand anywhere in it. Else, as for the audit mode (:func:`~rentalars.material.audits.parse_scanned_id`), the
    last part of the path is taken.
    """
    if not re.match(r"^https?://", code, re.IGNORECASE):
        return None
    target = LabelSettings.load().qr_target
    if target and "{id}" in target:
        before, _separator, after = target.partition("{id}")
        match = re.match(rf"^{re.escape(before)}(.+?){re.escape(after)}$", code, re.IGNORECASE)
        if match:
            return match.group(1)
    path = code.split("?", 1)[0].split("#", 1)[0]
    parts = [part for part in path.split("/") if part]
    return parts[-1] if len(parts) > 1 else None


def _find_items(code: str) -> list[MaterialItem]:
    """The items for an ID, a number typed with ``#`` or a serial number: one for an ID, any number for a serial number."""
    queryset = MaterialItem.objects.select_related(
        "material_model", "material_model__default_product", "product_override", "storage_location", "installed_in"
    )
    try:
        number = numbering.parse_inventory_number(code)
    except ValidationError:
        number = None
    if number is not None:
        item = queryset.filter(inventory_number=number).first()
        if item is not None:
            return [item]
    # Serial numbers need not be unique: in a fixed order, and a few are enough to say "ambiguous".
    return list(queryset.filter(serial_number__iexact=code).order_by("inventory_number")[:6])


def _gtin_variants(code: str) -> list[str]:
    """The ways the same GTIN is written: 8, 12, 13 or 14 digits, with leading zeros (an EAN-13 is a GTIN-14 with 0)."""
    if not code.isdigit() or len(code) not in (8, 12, 13, 14):
        return []
    stripped = code.lstrip("0")
    return [code] + [stripped.zfill(length) for length in (8, 12, 13, 14) if stripped.zfill(length) != code]


def _item_result(item: MaterialItem, code: str) -> ScanResult:
    """The result for an item: its names, where it lies, what it holds."""
    from rentalars.material.installed_models import InstalledQuantity

    contents = item.contents.count() + InstalledQuantity.objects.filter(container=item).count()
    place = item.storage_location.name if item.storage_location_id else ""
    spot = item.effective_storage_spot
    if spot:
        place = f"{place} {spot}".strip()
    parts = [item.get_status_display()]
    if place:
        parts.append(place)
    if item.is_installed and item.installed_in is not None:
        parts.append(_("in %(container)s") % {"container": item.installed_in.display_id})
    if contents:
        parts.append(_("holds %(count)d") % {"count": contents})
    return ScanResult(
        kind=ITEM,
        code=code,
        title=f"{item.display_id} {item.material_model.display_short_name}",
        detail=", ".join(str(part) for part in parts),
        url=reverse("material:item_detail", args=[item.pk]),
        item=item,
        product=item.product,
        model=item.material_model,
        contents=contents,
    )


def resolve(
    text: str | None, rights: Rights | None = None, *, prefer: Callable[[MaterialItem], bool] | None = None
) -> ScanResult:
    """Find what a scanned or typed code stands for (MAT-027, UIX-006).

    Args:
        text: The code as delivered.
        rights: The rights of the reader; ``None`` checks nothing (code that has done its own check, e.g. the
            packing). Items, spots and locations need to read the material, products to read the products or
            the projects.
        prefer: Tells which of several items with the same serial number is meant (the packing passes "is on the
            packing list"). Without it, or when it names none or several, such a code is ambiguous:
            the answer is ``none`` and lists the IDs.

    Returns:
        The result; ``kind == "none"`` with a message if the code leads nowhere (or to something the reader may not
        see).
    """
    code = clean_code(text)
    if not code:
        return ScanResult(NONE, "", message=_("Nothing was entered."))

    def allowed(*modules: str) -> bool:
        return rights is None or any(rights.can_read(module) for module in modules)

    identifier = _id_from_address(code) or code
    # A long number that is a GTIN comes before an ID: IDs are short.
    gtins = _gtin_variants(identifier)
    if gtins and len(identifier) >= 8:
        from rentalars.products.models import Product

        product = Product.objects.filter(gtin__in=gtins).select_related("unit").order_by("-is_active", "pk").first()
        if product is not None and allowed(Module.PRODUCTS, Module.PROJECTS, Module.MATERIAL):
            return ScanResult(
                PRODUCT,
                code,
                title=f"{product.article_number} {product.name}",
                detail=product.get_kind_display(),
                url=reverse("products:detail", args=[product.pk]),
                product=product,
            )
    found = _find_items(identifier)
    if len(found) > 1 and prefer is not None:
        preferred = [candidate for candidate in found if prefer(candidate)]
        found = preferred if len(preferred) == 1 else found
    if len(found) > 1 and allowed(Module.MATERIAL):
        ids = ", ".join(candidate.display_id for candidate in found[:5])
        return ScanResult(
            NONE,
            code,
            message=_("Several items have the serial number “%(code)s” (%(ids)s). Scan the label with the ID instead.")
            % {"code": code[:60], "ids": ids},
        )
    item = found[0] if len(found) == 1 else None
    if item is not None and allowed(Module.MATERIAL):
        return _item_result(item, code)
    spot = normalise_spot(identifier)
    if _SPOT.match(spot) and allowed(Module.MATERIAL):
        count = MaterialItem.objects.filter(storage_spot=spot).count()
        if count:
            return ScanResult(
                SPOT,
                code,
                title=spot,
                detail=_("%(count)d items lie there") % {"count": count},
                url=f"{reverse('material:item_list')}?{urlencode({'q': spot})}",
                count=count,
            )
    if allowed(Module.MATERIAL):
        from rentalars.masterdata.models import StorageLocation

        location = StorageLocation.objects.filter(Q(name__iexact=identifier), is_active=True).first()
        if location is not None:
            count = MaterialItem.objects.filter(storage_location=location).count()
            return ScanResult(
                LOCATION,
                code,
                title=location.name,
                detail=_("%(count)d items lie there") % {"count": count},
                url=f"{reverse('material:item_list')}?{urlencode({'storage_location': location.pk})}",
                count=count,
            )
    return ScanResult(NONE, code, message=_("Nothing is known under “%(code)s”.") % {"code": code[:60]})


def result_document(result: ScanResult) -> dict[str, Any]:
    """The result as the endpoint of the pages and the API send it."""
    document: dict[str, Any] = {
        "kind": result.kind,
        "code": result.code,
        "title": result.title,
        "detail": result.detail,
        "url": result.url,
        "message": result.message,
        "count": result.count,
        "is_case": result.is_case,
        "contents": result.contents,
        "plan_token": result.plan_token,
        "plan_label": result.plan_label,
        "item": None,
        "product": None,
    }
    if result.item is not None:
        item = result.item
        document["item"] = {
            "id": item.pk,
            "display_id": item.display_id,
            "name": item.material_model.display_short_name,
            "status": item.status,
            "is_operational": item.is_operational,
            "is_bulk": item.material_model.is_bulk,
            "serial_number": item.serial_number,
        }
    if result.product is not None:
        document["product"] = {
            "id": result.product.pk,
            "article_number": result.product.article_number,
            "name": result.product.name,
        }
    return document
