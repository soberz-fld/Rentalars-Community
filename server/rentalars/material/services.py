# SPDX-License-Identifier: GPL-3.0-or-later
"""Business logic for material: creating items, "installed in", history.

Browser views and API views both call these functions (API-002).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from rentalars.core.audit import record_event
from rentalars.core.i18n import LocalText, local_pattern
from rentalars.core.models import NumberRange, NumberRangeKey
from rentalars.core.photos import PhotoError, render_photo_upload
from rentalars.core.uploads import validate_document_upload
from rentalars.masterdata.models import Manufacturer, Supplier
from rentalars.material import serials as serial_check
from rentalars.material.models import (
    ConnectionType,
    DefectReport,
    Inspection,
    InspectionResult,
    InspectionType,
    ItemBlock,
    ItemStatus,
    MaterialFile,
    MaterialFileKind,
    MaterialItem,
    MaterialModel,
)
from rentalars.material.numbering import allocate_inventory_number

#: Upper limit for creating items in one step, as a guard against typos (MAT-006).
MAX_ITEMS_PER_BATCH = 500


@transaction.atomic
def create_items(
    material_model: MaterialModel,
    count: int = 1,
    *,
    inventory_number: int | None = None,
    serial_numbers: list[str] | None = None,
    price_for_set: bool = False,
    item_fields: list[dict[str, Any]] | None = None,
    **common_fields: Any,
) -> list[MaterialItem]:
    """Create one or several items of a model in one step (MAT-006, MAT-050).

    Args:
        material_model: The model the items belong to.
        count: How many items to create.
        inventory_number: The start ID (MAT-050): the first item gets it, each
            further item the next free ID after the one before. ``None`` lets
            the system assign the next free IDs of the number range (MAT-003).
        serial_numbers: One serial number per item, in the order of the IDs
            (MAT-050); fewer than ``count`` leave the last items without one,
            an empty text leaves that item without one.
        price_for_set: MAT-054: the purchase price is that of all the
            new items together – a set bought as one. The first item gets the
            price, the others have it included in the first one.
        item_fields: For incoming invoices: values of each item of its own, in the order of the IDs, on top of
            ``common_fields`` – the share of the acquisition cost of each piece.
        **common_fields: Values shared by all new items, e.g. invoice date and
            number, purchase price, supplier, status, storage location.

    Returns:
        The created items in ID order.

    Raises:
        ValidationError: The count is out of range, the start ID is taken,
            more serial numbers than items or one twice, or a field value is
            invalid.
    """
    if count < 1 or count > MAX_ITEMS_PER_BATCH:
        raise ValidationError(
            _("Between 1 and %(maximum)d items can be created in one step.") % {"maximum": MAX_ITEMS_PER_BATCH}
        )
    if material_model.is_bulk and count != 1:
        raise ValidationError(_("Bulk material is kept as one row with a quantity."))
    serials = check_serial_numbers(serial_numbers or [], count)
    if inventory_number is not None and MaterialItem.objects.filter(inventory_number=inventory_number).exists():
        raise ValidationError({"inventory_number": _("This ID is already taken.")})

    numbers = following_free_numbers(inventory_number, count) if inventory_number is not None else None
    items: list[MaterialItem] = []
    for index in range(count):
        number = numbers[index] if numbers is not None else allocate_inventory_number()
        own = item_fields[index] if item_fields and index < len(item_fields) else {}
        item = MaterialItem(material_model=material_model, inventory_number=number, **{**common_fields, **own})
        if index < len(serials) and serials[index]:
            item.serial_number = serials[index]
        if price_for_set and index > 0:
            # MAT-054: the price of the whole set is noted at the first item.
            item.purchase_price = None
            item.purchase_price_in = items[0]
        item.full_clean()
        item.save()
        items.append(item)
    if numbers is not None:
        NumberRange.ensure_next_is_above(NumberRangeKey.MATERIAL_ITEM, numbers[-1])
    return items


def following_free_numbers(start: int, count: int) -> list[int]:
    """The start ID and the next free IDs after it, ``count`` in all (MAT-050).

    Example: start 42 for three items while 43 is taken gives 42, 44, 45.
    The IDs in use are read in windows instead of one query per number.
    """
    numbers = [start]
    candidate = start
    window_end = start
    taken: set[int] = set()
    while len(numbers) < count:
        candidate += 1
        if candidate > window_end:
            window_end = candidate + count + 200
            taken = set(
                MaterialItem.objects.filter(inventory_number__range=(candidate, window_end)).values_list(
                    "inventory_number", flat=True
                )
            )
        if candidate not in taken:
            numbers.append(candidate)
    return numbers


def check_serial_numbers(serial_numbers: list[str], count: int) -> list[str]:
    """Clean the serial numbers of new items: at most one per item (MAT-050).

    Duplicate serial numbers: a number given twice is no error any more – it is a warning
    (:mod:`rentalars.material.serials`); the same number may be right at the models of two manufacturers.

    Returns:
        The serial numbers, stripped, with empty ones at the end removed.

    Raises:
        ValidationError: More serial numbers than items.
    """
    serials = [str(serial or "").strip()[:120] for serial in serial_numbers]
    while serials and not serials[-1]:
        serials.pop()
    if len(serials) > count:
        raise ValidationError(
            {
                "serial_numbers": _("%(serials)d serial numbers for %(count)d items. Give at most one per item.")
                % {"serials": len(serials), "count": count}
            }
        )
    return serials


def manufacturer_named(name: str) -> Manufacturer | None:
    """The manufacturer of this name; a new name creates it (MAT-048). Empty: none."""
    name = (name or "").strip()[:120]
    if not name:
        return None
    found = Manufacturer.objects.filter(name__iexact=name).order_by("-is_active", "pk").first()
    if found is not None:
        return found
    created = Manufacturer(name=name)
    created.full_clean()
    created.save()
    return created


def supplier_named(name: str) -> Supplier | None:
    """The supplier of this name; a new name creates it (MAT-050). Empty: none."""
    name = (name or "").strip()[:120]
    if not name:
        return None
    found = Supplier.objects.filter(name__iexact=name).order_by("-is_active", "pk").first()
    if found is not None:
        return found
    created = Supplier(name=name)
    created.full_clean()
    created.save()
    return created


def save_item(item: MaterialItem) -> list[str]:
    """Validate and save an item; return warnings that do not block saving.

    Returns:
        Human-readable warnings, currently only about duplicate serial
        numbers (MAT-004). As in the browser (MAT-084), only a new or
        changed serial number is asked about: one that was a duplicate before
        stays so without a warning at every change of something else.

    Raises:
        ValidationError: A rule is violated, e.g. a circular "installed in".
    """
    item.full_clean()
    installation_changed = _installation_changed(item)
    serial = (item.serial_number or "").strip()
    changed_serial = bool(serial) and _stored_serial_number(item) != serial
    item.save()
    if installation_changed:
        _log_installation_on_container(item, installation_changed)
    return serial_number_warnings(item) if changed_serial else []


def _stored_serial_number(item: MaterialItem) -> str | None:
    """The serial number the item has in the database; ``None`` for an item that is not saved yet."""
    if item.pk is None:
        return None
    return MaterialItem.objects.filter(pk=item.pk).values_list("serial_number", flat=True).first()


def _installation_changed(item: MaterialItem) -> tuple[int | None, int | None] | None:
    """Return ``(old container id, new container id)`` if the container changed."""
    if item.pk is None:
        return (None, item.installed_in_id) if item.installed_in_id else None
    stored = MaterialItem.objects.filter(pk=item.pk).values_list("installed_in_id", flat=True).first()
    if stored == item.installed_in_id:
        return None
    return stored, item.installed_in_id


def _log_installation_on_container(item: MaterialItem, change: tuple[int | None, int | None]) -> None:
    """Note installing and removing in the history of the container too.

    The item itself gets its entry from the normal field logging. The
    container did not change any of its own fields, so its entry is written
    here explicitly.
    """
    old_container_id, new_container_id = change
    if old_container_id:
        old_container = MaterialItem.objects.filter(pk=old_container_id).first()
        if old_container is not None:
            record_event(old_container, "item.content_removed", {"item": item.display_id})
    if new_container_id and item.installed_in is not None:
        record_event(item.installed_in, "item.content_added", {"item": item.display_id})


def serial_number_warnings(item: MaterialItem) -> list[str]:
    """MAT-004: warn if another item has the serial number; of any model, the same model worded stronger."""
    return serial_check.for_item(item)


def find_item_by_code(code: str) -> MaterialItem | None:
    """Find an item by its ID or, failing that, by its serial number.

    This is what a scan of a label will call later (MAT-027); today the
    global search and the "installed in" field use it.
    """
    from rentalars.material.numbering import parse_inventory_number

    code = code.strip()
    if not code:
        return None
    try:
        number = parse_inventory_number(code)
    except ValidationError:
        number = None
    if number is not None:
        item = MaterialItem.objects.filter(inventory_number=number).select_related("material_model").first()
        if item is not None:
            return item
    return MaterialItem.objects.filter(serial_number__iexact=code).select_related("material_model").first()


# --- Installed in (MAT-033 to MAT-041) ---------------------------------------


@dataclass
class ContentNode:
    """An item inside a container together with what is inside the item itself."""

    item: MaterialItem
    children: list[ContentNode] = field(default_factory=list)

    @property
    def depth_first(self) -> list[tuple[int, MaterialItem]]:
        """All items below this node as ``(depth, item)`` pairs, for indented lists."""
        result: list[tuple[int, MaterialItem]] = []
        pending = [(1, child) for child in reversed(self.children)]
        while pending:
            depth, node = pending.pop()
            result.append((depth, node.item))
            pending.extend((depth + 1, child) for child in reversed(node.children))
        return result


def container_chain(item: MaterialItem) -> list[MaterialItem]:
    """Return the containers around an item, from the nearest to the outermost (MAT-035).

    Example: a module in a device in a rack returns ``[device, rack]``.
    """
    chain: list[MaterialItem] = []
    seen = {item.pk}
    current = item.installed_in
    while current is not None and current.pk not in seen:
        chain.append(current)
        seen.add(current.pk)
        current = current.installed_in
    return chain


def content_tree(item: MaterialItem) -> ContentNode:
    """Return everything installed in an item, across all levels (MAT-035).

    The tree is loaded level by level, one query per level. Real cases have
    two or three levels (module in device in rack).
    """
    root = ContentNode(item=item)
    nodes = {item.pk: root}
    current_level = [item.pk]
    while current_level:
        children = list(
            MaterialItem.objects.filter(installed_in_id__in=current_level)
            .select_related("material_model", "material_model__default_product", "product_override")
            .order_by("inventory_number")
        )
        current_level = []
        for child in children:
            if child.pk in nodes:
                continue  # guards against a circle that slipped past validation
            node = ContentNode(item=child)
            nodes[child.pk] = node
            nodes[child.installed_in_id].children.append(node)
            current_level.append(child.pk)
    return root


def install_item(
    item: MaterialItem,
    container: MaterialItem | None,
    *,
    connection_type: str = ConnectionType.FIXED,
    individually_rentable: bool = False,
) -> list[str]:
    """Put an item into a container or take it out (``container=None``).

    Returns:
        Warnings as from :func:`save_item`.

    Raises:
        ValidationError: The container is not allowed (itself, a circle, an
            archived or bulk item – MAT-034).
    """
    item.installed_in = container
    item.connection_type = connection_type
    item.individually_rentable = individually_rentable
    return save_item(item)


def apply_status(item: MaterialItem, status: str, reason: str = "") -> None:
    """Put a new status and its reason on an item without saving it (MAT-044).

    The reason always belongs to the status it was given for: a change
    without a reason clears the old one, so that "in repair" never keeps
    saying why the item was "blocked" last year.

    Raises:
        ValidationError: The status does not exist.
    """
    if status not in ItemStatus.values:
        raise ValidationError(_("Unknown status."))
    if status == ItemStatus.IMPORT_ERROR and item.status != status and not item.by_import:
        raise ValidationError(_("The status “import error” is only reached through the import."))
    if status != item.status:
        item.status = status
        item.status_reason = reason.strip()[:250]
    elif reason.strip():
        item.status_reason = reason.strip()[:250]


def set_status(item: MaterialItem, status: str, *, reason: str = "") -> None:
    """Change the status of an item (MAT-020); the audit log records who, when and why.

    Args:
        item: The item.
        status: The new status.
        reason: Why. Required for "defective" (MAT-044).

    Raises:
        ValidationError: No reason was given for "defective"; a defective
            item is to go somewhere else than to repair or out of the stock
            (MAT-045); or other items are still installed in an item that is
            about to be archived (MAT-040). All three are checked in
            ``MaterialItem.clean``.
    """
    was_defective = item.status == ItemStatus.DEFECTIVE
    apply_status(item, status, reason)
    item.full_clean()
    item.save()
    if item.status == ItemStatus.DEFECTIVE and not was_defective:
        _report_defect(item, reason)


def _report_defect(item: MaterialItem, reason: str) -> None:
    """Tell the warehouse that an item is defective (UIX-005)."""
    from rentalars.accounts.models import User
    from rentalars.core.audit import get_current_actor
    from rentalars.notifications.models import Kind
    from rentalars.notifications.services import notify, warehouse_staff

    actor = get_current_actor()
    acting_user = User.objects.filter(pk=actor.user_id).first() if actor and actor.user_id else None
    notify(
        warehouse_staff(),
        Kind.DEFECT,
        LocalText(gettext_lazy("Defective: %(item)s"), item=item),  # UIX-029: in each reader's language
        body=reason,
        url=reverse("material:item_detail", args=[item.pk]),
        exclude=acting_user,
    )


# --- Contains (MAT-046) -------------------------------------------------------


def add_content(
    container: MaterialItem,
    item: MaterialItem,
    *,
    connection_type: str = ConnectionType.FIXED,
    individually_rentable: bool = False,
) -> list[str]:
    """Put an item into a container, said from the container's side (MAT-046).

    The same relation as "installed in" on the item (MAT-033), entered from
    the other end: on the page of the rack one adds the devices it holds.
    The same rules apply, because the same check runs
    (``MaterialItem.clean``): not into itself, no circle – a rack cannot
    contain the rack it stands in –, not into archived or bulk material.

    An item that already sits in *another* container is not moved from here.
    A mistyped ID would otherwise pull a device out of a rack it really is
    in; moving is done on the item itself, where the old container is in view.

    Returns:
        Warnings as from :func:`save_item`.

    Raises:
        ValidationError: One of the rules above is violated.
    """
    if item.pk == container.pk:
        raise ValidationError({"installed_in": _("An item cannot be installed in itself.")})
    if item.installed_in_id and item.installed_in_id != container.pk:
        raise ValidationError(
            _("%(item)s is already installed in %(other)s. Change “installed in” on the item itself to move it.")
            % {"item": item.display_id, "other": item.installed_in.display_id}
        )
    return install_item(item, container, connection_type=connection_type, individually_rentable=individually_rentable)


def remove_content(container: MaterialItem, item: MaterialItem) -> None:
    """Take an item out of a container, said from the container's side (MAT-046).

    Raises:
        ValidationError: The item is not (directly) installed in the container.
    """
    if item.installed_in_id != container.pk:
        raise ValidationError(
            _("%(item)s is not installed in %(container)s.")
            % {"item": item.display_id, "container": container.display_id}
        )
    install_item(item, None)


# --- Stage 5: defects, blocks, inspections, files, many items at once --------------------------


def report_defect(
    item: MaterialItem,
    description: str,
    *,
    photo: Any = None,
    context: str = "",
    user: Any = None,
) -> DefectReport:
    """Record a defect with description and photo, set the item to "defective", tell the warehouse (MAT-023).

    An item that is already defective gets the report all the same – a
    second fault found is worth knowing – but keeps its status.

    Raises:
        ValidationError: No description, an archived item, or the photo is
            not a picture.
    """
    description = (description or "").strip()
    if not description:
        raise ValidationError({"description": _("Describe what is defective.")})
    if item.is_archived:
        raise ValidationError(_("The item %(id)s is archived.") % {"id": item.display_id})
    rendered = None
    if photo:
        try:
            rendered = render_photo_upload(photo)  # Always made anew – smaller, with the place, nothing else
        except PhotoError as error:
            raise ValidationError({"photo": str(error)}) from error
    with transaction.atomic():
        report = DefectReport(item=item, description=description, context=context[:250], reported_by=user)
        if rendered is not None:
            report.photo.save("foto.jpg", ContentFile(rendered.photo), save=False)
        report.save()
        if item.status != ItemStatus.DEFECTIVE:
            set_status(item, ItemStatus.DEFECTIVE, reason=description[:250])
        else:
            record_event(item, "item.defect_reported", {"description": description[:250]})
    return report


def add_block(item: MaterialItem, start: Any, end: Any, reason: str, *, user: Any = None) -> ItemBlock:
    """Block an item for a period (MAT-024); its product is one piece short meanwhile.

    Raises:
        ValidationError: The end is not after the start, or no reason was given.
    """
    block = ItemBlock(item=item, start=start, end=end, reason=reason, created_by=user)
    block.full_clean()
    block.save()
    return block


def remove_block(block: ItemBlock) -> None:
    """Lift a block before its end."""
    block.delete()


def record_inspection(
    item: MaterialItem,
    inspection_type: InspectionType,
    *,
    date: Any,
    inspector: str,
    result: str,
    note: str = "",
    protocol: Any = None,
    user: Any = None,
    electrical: dict[str, Any] | None = None,
    plan: Any = None,
) -> Inspection:
    """Record an inspection of an item (MAT-031).

    A failed inspection sets the item to "defective" – with the inspection
    as reason – and the warehouse is told, as with every defect. This holds
    only if no later inspection of the same type is on record (L6):
    a failed one entered afterwards from the paper files is kept as history. The next
    due date follows from the inspection type (``material.inspections``).

    MAT-078: ``electrical`` holds what an electrical inspection measured
    (``material.dguv.ELECTRICAL_FIELDS``); the rules of ``dguv.clean_values``
    apply – among them "passed" against the measured values only with a
    reason in the note. Without a note, a failed one names the reasons as
    the reason for "defective".

    ``plan`` is the :class:`~rentalars.material.inspections.InspectionPlan` to ask which types apply; a caller
    recording many inspections hands in one, so that it is not built for every item.

    Raises:
        ValidationError: Missing inspector, a date in the future, an unknown
            result, a type that does not apply, a protocol of a type that
            is not accepted, or measured values against the rules.
    """
    from django.utils import timezone

    from rentalars.material import dguv
    from rentalars.material.inspections import InspectionPlan

    inspector = (inspector or "").strip()
    errors: dict[str, Any] = {}
    if not inspector:
        errors["inspector"] = _("Who inspected?")
    if date is None:
        errors["date"] = _("When was it inspected?")
    elif date > timezone.localdate():
        errors["date"] = _("An inspection cannot lie in the future.")
    if result not in InspectionResult.values:
        errors["result"] = _("Passed or failed?")
    plan = plan or InspectionPlan()
    applicable = {t.pk for t in plan.types_for(item.material_model_id, item.material_model.category_id)}
    if inspection_type.pk not in applicable:
        errors["inspection_type"] = _("This inspection does not apply to %(model)s.") % {"model": item.material_model}
    if protocol:
        try:
            validate_document_upload(protocol)
        except ValidationError as error:
            errors["protocol"] = error.messages
    measured: dict[str, Any] = {}
    try:
        measured = dguv.clean_values(inspection_type, electrical, result=result, note=note)
    except ValidationError as error:
        for name, messages in error.message_dict.items():
            errors.setdefault(name, messages)
    if errors:
        raise ValidationError(errors)
    with transaction.atomic():
        inspection = Inspection(
            item=item,
            inspection_type=inspection_type,
            date=date,
            inspector=inspector[:120],
            result=result,
            note=(note or "").strip(),
            recorded_by=user,
            **measured,
        )
        if protocol:
            inspection.protocol_name = protocol.name[:255]
            inspection.protocol.save(protocol.name, protocol, save=False)
        inspection.save()
        # L6: an old inspection entered afterwards does not decide – a later one of the type does.
        superseded = Inspection.objects.filter(item=item, inspection_type=inspection_type, date__gt=date).exists()
        if (
            result == InspectionResult.FAILED
            and item.status != ItemStatus.DEFECTIVE
            and not item.is_archived
            and not superseded
        ):
            reason = _("Inspection “%(type)s” failed on %(date)s") % {
                "type": inspection_type.name,
                "date": date.strftime(local_pattern("%d.%m.%Y")),
            }
            if note.strip():
                reason = f"{reason}: {note.strip()}"
            elif inspection.is_electrical and inspection.evaluation.reasons:
                # MAT-078: whoever repairs it learns what the measurement found.
                reason = f"{reason}: {' '.join(inspection.evaluation.reasons)}"
            set_status(item, ItemStatus.DEFECTIVE, reason=reason[:250])
    return inspection


@dataclass
class BatchEntry:
    """One item of a mass inspection and what was found at it (MAT-082).

    ``result`` left empty: an electrical inspection takes the one the measured values suggest
    (``dguv.Evaluation.suggested_result``); any other inspection needs a result.
    """

    item: MaterialItem
    result: str = ""
    note: str = ""
    electrical: dict[str, Any] | None = None


class BatchInspectionError(ValidationError):
    """A mass inspection that was refused: ``by_item`` has the errors of each item by its ID, ``common`` the others."""

    def __init__(self, by_item: dict[int, dict[str, list[str]]], common: dict[str, Any] | None = None) -> None:
        self.by_item = by_item
        self.common = common or {}
        super().__init__(
            {**self.common, "items": [_("%(count)d of the items have a problem.") % {"count": len(by_item)}]}
            if by_item
            else self.common
        )


def record_inspections(
    entries: list[BatchEntry],
    inspection_type: InspectionType,
    *,
    date: Any,
    inspector: str,
    test_device: str = "",
    user: Any = None,
) -> list[Inspection]:
    """Record one inspection of many items at once – same type, day, inspector and test device (MAT-082).

    The rules are those of :func:`record_inspection` for each item; all or nothing – if one item breaks
    a rule, nothing is recorded and the error names the items (:class:`BatchInspectionError`). The test
    device is written to every electrical inspection of the batch that names none of its own. An electrical
    entry that names no result takes the one its measured values suggest.

    Raises:
        BatchInspectionError: Something common to all (no items, too many, an inspector missing, a date in the
            future) or a problem of single items.
    """
    from django.utils import timezone

    from rentalars.material import dguv
    from rentalars.material.inspections import InspectionPlan

    if not entries:
        raise ValidationError({"items": _("Choose at least one item.")})
    if len(entries) > MAX_BULK_ITEMS:
        raise ValidationError(
            {"items": _("At most %(count)d items can be changed at once.") % {"count": MAX_BULK_ITEMS}}
        )
    common: dict[str, Any] = {}
    if not (inspector or "").strip():
        common["inspector"] = _("Who inspected?")
    if date is None:
        common["date"] = _("When was it inspected?")
    elif date > timezone.localdate():
        common["date"] = _("An inspection cannot lie in the future.")
    if common:
        raise BatchInspectionError({}, common)
    recorded: list[Inspection] = []
    problems: dict[int, dict[str, list[str]]] = {}
    plan = InspectionPlan()  # asked for every item, built once
    with transaction.atomic():
        for entry in entries:
            electrical = dict(entry.electrical) if entry.electrical is not None else None
            if electrical is not None and inspection_type.is_electrical:
                if not electrical.get("test_device"):
                    electrical["test_device"] = test_device
            result = entry.result
            if not result and electrical is not None and inspection_type.is_electrical:
                result = dguv.evaluate(electrical).suggested_result
            try:
                with transaction.atomic():
                    recorded.append(
                        record_inspection(
                            entry.item,
                            inspection_type,
                            date=date,
                            inspector=inspector,
                            result=result,
                            note=entry.note,
                            user=user,
                            electrical=electrical,
                            plan=plan,
                        )
                    )
            except ValidationError as error:
                problems[entry.item.pk] = {
                    name: [str(message) for message in messages] for name, messages in error.message_dict.items()
                }
        if problems:
            raise BatchInspectionError(problems)  # leaves the transaction: nothing of the batch is kept
    return recorded


_PICTURE_ENDINGS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp"})


def add_file(
    owner: MaterialModel | MaterialItem, uploaded: Any, *, kind: str, title: str = "", user: Any = None
) -> MaterialFile:
    """Attach a picture or document to a model or an item (MAT-017).

    Raises:
        ValidationError: The file type is not accepted or the file is too
            large (NFA-007); a picture is not a PNG or JPEG.
    """
    if kind not in MaterialFileKind.values:
        raise ValidationError({"kind": _("Unknown kind of file.")})
    rendered = None
    picture_name = Path(getattr(uploaded, "name", "") or "").suffix.lower() in _PICTURE_ENDINGS
    if kind == MaterialFileKind.PICTURE or (picture_name and kind != MaterialFileKind.INVOICE):
        # MAT-090: a photo is made anew – JPEG, at most 2048 pixels, with the place – and gets a preview;
        # so is a picture attached as a manual, protocol or other file (review). A copy of an invoice stays as it
        # was received: it is a document of proof.
        if kind != MaterialFileKind.PICTURE:
            validate_document_upload(uploaded)
        try:
            rendered = render_photo_upload(uploaded)
        except PhotoError as error:
            raise ValidationError({"file": str(error)}) from error
    else:
        validate_document_upload(uploaded)
    name = (uploaded.name or "datei")[:255]
    if rendered is not None:
        name = f"{Path(name).stem[:200] or 'foto'}.jpg"
    stored = MaterialFile(
        kind=kind,
        title=(title or "").strip()[:200],
        original_name=name,
        size=len(rendered.photo) if rendered is not None else getattr(uploaded, "size", 0) or 0,
        uploaded_by=user,
    )
    if isinstance(owner, MaterialItem):
        stored.item = owner
    else:
        stored.material_model = owner
    if rendered is not None:
        stored.file.save(name, ContentFile(rendered.photo), save=False)
        stored.thumbnail.save(name, ContentFile(rendered.thumbnail), save=False)
    else:
        stored.file.save(uploaded.name, uploaded, save=False)
    stored.save()
    return stored


def visible_files(files: Any, rights: Any) -> Any:
    """The files a user may see: the copy of an invoice shows the purchase prices, so it needs that right (R1-1).

    ``files`` is a queryset of :class:`MaterialFile`; the same rule holds for the pages, the file download and the API.
    """
    from rentalars.accounts.rights import SpecialRight

    if rights.has(SpecialRight.PURCHASE_PRICES):
        return files
    return files.exclude(kind=MaterialFileKind.INVOICE)


def may_add_file_of_kind(kind: str, rights: Any) -> bool:
    """Whether the user may attach a file of this kind: an invoice only with the right to see purchase prices (R1-1)."""
    from rentalars.accounts.rights import SpecialRight

    return kind != MaterialFileKind.INVOICE or rights.has(SpecialRight.PURCHASE_PRICES)


def delete_file(stored: MaterialFile) -> None:
    """Remove a file of a model or item, from the disk as well.

    MAT-061: the invoice of a purchase is stored once and
    listed with every item bought with it; the disk keeps it until the last
    of them is removed.
    """
    if not MaterialFile.objects.filter(file=stored.file.name).exclude(pk=stored.pk).exists():
        stored.file.delete(save=False)
    if stored.thumbnail:
        stored.thumbnail.delete(save=False)
    stored.delete()


def files_before_owner(sender: Any, instance: MaterialItem | MaterialModel, **kwargs: Any) -> None:
    """Delete the files of an item or model before it is deleted (see ``MaterialConfig.ready``)."""
    field = "item" if isinstance(instance, MaterialItem) else "material_model"
    MaterialFile.objects.filter(**{field: instance}).delete()


def file_row_deleted(sender: Any, instance: MaterialFile, **kwargs: Any) -> None:
    """Take the content of a deleted file row from the disk (MAT-090) – unless another row still shows it (MAT-061).

    ``delete_file`` does this for one file; the signal covers the rows that go with an item or a model.
    """
    names = [name for name in (instance.file.name, instance.thumbnail.name) if name]
    storage = instance.file.storage

    def remove() -> None:
        for name in names:
            if not MaterialFile.objects.filter(file=name).exists() and storage.exists(name):
                storage.delete(name)

    transaction.on_commit(remove)


def suggested_purchase_fields(material_model: MaterialModel) -> dict[str, Any]:
    """Supplier and supplier's article number of the item created last of a model (MAT-014).

    A second batch of the same cable usually comes from the same dealer.
    """
    latest = (
        MaterialItem.objects.filter(material_model=material_model)
        .exclude(supplier__isnull=True, supplier_article_number="")
        .order_by("-created_at", "-pk")
        .values("supplier_id", "supplier_article_number")
        .first()
    )
    if latest is None:
        return {}
    return {"supplier": latest["supplier_id"], "supplier_article_number": latest["supplier_article_number"]}


def category_mismatch(category: Any, product: Any) -> str:
    """A hint if material is given to a product of another main category (PRD-032); empty if fine.

    Not an error: a stand microphone set in "Ton" may honestly carry a
    stand from "Rigging". But often it is a slip of the mouse.
    """
    if product is None or category is None:
        return ""
    material_main = category.main_category
    product_main = product.category.main_category
    if material_main.pk == product_main.pk:
        return ""
    return _(
        "Note: the product %(product)s belongs to the main category %(product_category)s, "
        "the material to %(material_category)s."
    ) % {
        "product": f"{product.article_number} {product.name}",
        "product_category": product_main.name,
        "material_category": material_main.name,
    }


# --- Taking loose contents out and putting them back (MAT-043) ----------------------------------


def take_out(item: MaterialItem) -> None:
    """Take a loose item out of its container in one step (MAT-043).

    The container is remembered, so that :func:`put_back` needs no input.
    Both items note it in their history (MAT-039).

    Raises:
        ValidationError: The item is not in a container, or it is fixed
            there – a screwed-in receiver is removed by changing "installed
            in" on purpose, not by a quick tap.
    """
    if item.installed_in_id is None:
        raise ValidationError(_("%(item)s is not in a container.") % {"item": item.display_id})
    if item.connection_type != ConnectionType.LOOSE:
        raise ValidationError(
            _("%(item)s is permanently installed. Change “installed in” on the item to remove it.")
            % {"item": item.display_id}
        )
    container = item.installed_in
    item.installed_in = None
    save_item(item)
    MaterialItem.objects.filter(pk=item.pk).update(taken_out_of=container)
    item.taken_out_of = container
    record_event(item, "item.taken_out", {"container": container.display_id})


def put_back(item: MaterialItem) -> None:
    """Put an item back into the container it was taken out of (MAT-043).

    Raises:
        ValidationError: Nothing to put it back into, or the container no
            longer accepts it (archived, a circle).
    """
    container = item.taken_out_of
    if container is None or item.installed_in_id is not None:
        raise ValidationError(_("%(item)s was not taken out of a container.") % {"item": item.display_id})
    install_item(item, container, connection_type=ConnectionType.LOOSE)
    MaterialItem.objects.filter(pk=item.pk).update(taken_out_of=None)
    item.taken_out_of = None
    record_event(item, "item.put_back", {"container": container.display_id})


# --- Many items at once (MAT-029) ---------------------------------------------------------------

#: The most items changed in one step.
MAX_BULK_ITEMS = 1000

#: A value meaning "leave as it is" in :func:`bulk_update`.
UNCHANGED: Any = object()


@transaction.atomic
def bulk_update(
    items: list[MaterialItem],
    *,
    status: str | None = None,
    reason: str = "",
    storage_location: Any = UNCHANGED,
    product: Any = UNCHANGED,
    storage_spot: str | None = None,
) -> list[str]:
    """Change status, storage location, spot or product of many items at once (MAT-029, MAT-078).

    All or nothing: if one item breaks a rule – a defective item set to
    "available" (MAT-045) – nothing is changed and the error names the
    item. Every item gets its own entry in the change log.

    Args:
        items: The items.
        status: The new status, or ``None`` to leave it.
        reason: The reason for the status (required for "defective", MAT-044).
        storage_location: A location, ``None`` to remove it, or
            :data:`UNCHANGED`.
        product: A product the items belong to, ``None`` for "as the model",
            or :data:`UNCHANGED`.
        storage_spot: The new spot within the location, ``None`` to leave it.
            Moving to another location (or to none) without a spot removes
            the old one: ``01-A-1`` of the old place means nothing at the
            new one (MAT-078).

    Returns:
        Hints that do not stop the change: installed items whose location
        follows their container (MAT-038), products of another main category
        (PRD-032).

    Raises:
        ValidationError: Too many items, nothing to change, or a rule is broken.
    """
    if not items:
        raise ValidationError(_("Choose at least one item."))
    if len(items) > MAX_BULK_ITEMS:
        raise ValidationError(_("At most %(count)d items can be changed at once.") % {"count": MAX_BULK_ITEMS})
    if status is None and storage_location is UNCHANGED and product is UNCHANGED and not storage_spot:
        raise ValidationError(_("Choose what to change."))
    hints: list[str] = []
    installed: list[str] = []
    mismatched: set[int] = set()
    for item in items:
        was_defective = item.status == ItemStatus.DEFECTIVE
        if status is not None:
            apply_status(item, status, reason)
        if storage_location is not UNCHANGED:
            if storage_location != item.storage_location:
                item.storage_spot = ""
            item.storage_location = storage_location
            if item.installed_in_id:
                installed.append(item.display_id)
        if storage_spot:
            item.storage_spot = storage_spot
            if item.installed_in_id and item.display_id not in installed:
                installed.append(item.display_id)
        if product is not UNCHANGED:
            item.product_override = (
                product if product is None or product != item.material_model.default_product else None
            )
            if product is not None and item.material_model.category_id not in mismatched:
                hint = category_mismatch(item.material_model.category, product)
                if hint:
                    mismatched.add(item.material_model.category_id)
                    hints.append(hint)
        try:
            item.full_clean()
        except ValidationError as error:
            raise ValidationError(
                _("%(item)s: %(error)s") % {"item": item.display_id, "error": " ".join(error.messages)}
            ) from error
        item.save()
        if item.status == ItemStatus.DEFECTIVE and not was_defective:
            _report_defect(item, reason)
    if installed:
        hints.append(
            _("%(ids)s are installed in other items; their location follows the container.")
            % {"ids": ", ".join(installed[:10]) + (" …" if len(installed) > 10 else "")}
        )
    return hints


# --- Minimum stock of consumables (PRD-020) ----------------------------------------------------


@dataclass
class LowStock:
    """A product whose stock is below its minimum."""

    product: Any
    stock: int
    minimum: int


def low_stock_products() -> list[LowStock]:
    """Every active product with a minimum whose operational stock is below it (PRD-020)."""
    from rentalars.availability.stock import NO_STOCK, stock_of_products
    from rentalars.products.models import Product

    products = list(
        Product.objects.filter(is_active=True, minimum_stock__isnull=False, minimum_stock__gt=0).order_by(
            "article_number"
        )
    )
    if not products:
        return []
    stocks = stock_of_products([product.pk for product in products])
    result = []
    for product in products:
        stock = stocks.get(product.pk, NO_STOCK).operational
        if stock < product.minimum_stock:
            result.append(LowStock(product=product, stock=stock, minimum=product.minimum_stock))
    return result


def check_low_stock() -> int:
    """Tell the warehouse about products that fell below their minimum; each once (PRD-020).

    Run after every issue and by the daily maintenance. Returns how many
    products were reported now.
    """
    from rentalars.notifications.models import Kind, StockNotice
    from rentalars.notifications.services import notify, warehouse_staff

    low = low_stock_products()
    low_ids = {entry.product.pk for entry in low}
    StockNotice.objects.exclude(product_id__in=low_ids).delete()
    known = set(StockNotice.objects.values_list("product_id", flat=True))
    new = [entry for entry in low if entry.product.pk not in known]
    if not new:
        return 0
    recipients = warehouse_staff()
    for entry in new:
        StockNotice.objects.create(product=entry.product, stock=entry.stock)
        notify(
            recipients,
            Kind.LOW_STOCK,
            LocalText(
                gettext_lazy("Below the minimum: %(product)s"),
                product=f"{entry.product.article_number} {entry.product.name}",
            ),
            body=LocalText(
                gettext_lazy("Stock %(stock)d, minimum %(minimum)d."), stock=entry.stock, minimum=entry.minimum
            ),
            url=reverse("products:detail", args=[entry.product]),
        )
    return len(new)


# --- Models and products (MAT-051, PRD-046) -------------------------------------------------------


@transaction.atomic
def create_product_from_model(material_model: MaterialModel, rights: Any) -> Any:
    """Turn a model without product into a product of the same name, the model assigned (MAT-051).

    The product gets the category of the model, the next free article
    number and the presets of the category (PRD-030). Its kind is "sale"
    where the category presets sale products, otherwise "rental" – material
    is rented or sold, never a service. The price starts at 0; whoever may
    see prices sets it next.

    Raises:
        ValidationError: The model has a product already, or its category is
            one for customer material – such a product needs its owner, so
            it is made with the product form.
    """
    from rentalars.products import services as product_services
    from rentalars.products.models import DEFAULT_BILLING_MODE, STOCK_KINDS, Product, ProductKind

    material_model = MaterialModel.objects.select_for_update().select_related("category").get(pk=material_model.pk)
    if material_model.default_product_id is not None:
        raise ValidationError(
            _("%(model)s belongs to the product %(product)s already.")
            % {"model": material_model.name, "product": material_model.default_product}
        )
    category = material_model.category
    if category.holds_customer_material:
        raise ValidationError(
            _("Customer material needs its owner. Create the product with the form and choose the customer there.")
        )
    presets = product_services.presets_for_category(category)
    kind = ProductKind.SALE if presets["kind"] == ProductKind.SALE else ProductKind.RENTAL
    product = Product(
        category=category,
        article_number=presets["article_number"],
        name=material_model.name[:200],
        kind=kind,
        unit=presets["unit"],
        tax_rate=presets["tax_rate"],
        billing_mode=presets["billing_mode"] if presets["kind"] in STOCK_KINDS else DEFAULT_BILLING_MODE[kind],
    )
    if kind == ProductKind.SALE:
        product.sale_price = Decimal("0")
    else:
        product.price = Decimal("0")
    product_services.save_product(product, rights)
    material_model.default_product = product
    material_model.full_clean()
    material_model.save()
    return product


def assign_model_to_product(material_model: MaterialModel, product: Any) -> str:
    """Give a model without product to a product, from the product's page (PRD-046).

    Returns:
        A hint if the product belongs to another main category (PRD-032), else "".

    LOG-002: a vehicle product has material too – its items are
    the vehicles and trailers of the fleet.

    Raises:
        ValidationError: The model belongs to a product already, or the
            product has no stock of its own (a service, a kit …).
    """
    from rentalars.products.models import MATERIAL_KINDS

    if material_model.default_product_id is not None:
        raise ValidationError(
            _("%(model)s belongs to the product %(product)s already. Change it on the page of the model.")
            % {"model": material_model.name, "product": material_model.default_product}
        )
    if product.kind not in MATERIAL_KINDS:
        raise ValidationError(_("Only rental and sale products and vehicles have material."))
    material_model.default_product = product
    material_model.full_clean()
    material_model.save()
    return category_mismatch(material_model.category, product)


# --- MAT-059, MAT-064: purchase prices entered gross, duplicates of models ------------------------------


def gross_tax_rate(value: Any = None) -> Decimal:
    """The tax rate a gross purchase price includes (MAT-059; IMP-014).

    One of the active tax rates, as the import offers them; without a value the default tax rate.

    Raises:
        ValidationError: The rate is not an active tax rate, or there is no tax rate at all.
    """
    from rentalars.masterdata.models import TaxRate

    rates = set(TaxRate.objects.filter(is_active=True).values_list("rate", flat=True))
    if value in (None, ""):
        default = TaxRate.get_default()
        if default is None:
            raise ValidationError({"price_tax_rate": _("There is no tax rate. Enter the price net.")})
        return default.rate
    try:
        rate = Decimal(str(value).strip().replace(",", "."))
    except ArithmeticError:
        rate = None
    if rate is None or rate not in rates:
        raise ValidationError(
            {
                "price_tax_rate": _("Choose one of the active tax rates: %(rates)s.")
                % {"rates": ", ".join(f"{known.normalize():f}" for known in sorted(rates, reverse=True))}
            }
        )
    return rate


def net_from_gross(gross: Decimal, rate: Any) -> Decimal:
    """The net price of a gross price that includes ``rate`` per cent, rounded to cents (MAT-059; IMP-014).

    Rentalars keeps purchase prices net, as the import does: 119.00 at 19 % is 100.00, 10.00 is 8.40.
    """
    from rentalars.core.money import money
    from rentalars.material.importer import gross_factor

    return money(Decimal(gross) / gross_factor(rate))


def gross_from_net(net: Decimal, rate: Any) -> Decimal:
    """The gross price of a stored net one, for a form whose user enters gross prices (MAT-059).

    Net → gross → net gives the same cents again: rounding the gross price moves it by half a cent at most,
    and the division by 1 + rate makes that smaller still.
    """
    from rentalars.core.money import money
    from rentalars.material.importer import gross_factor

    return money(Decimal(net) * gross_factor(rate))


def entered_purchase_price(price: Decimal | None, prices: str = "net", rate: Any = None) -> Decimal | None:
    """The purchase price to store for one entered net or gross (MAT-059; IMP-014).

    ``prices`` is ``"net"`` or ``"gross"`` – the values of the choice of the material import; ``rate`` the
    tax rate a gross price includes, by default the default tax rate.

    Raises:
        ValidationError: A gross price with a rate that is not an active tax rate.
    """
    from rentalars.material.importer import PRICES_GROSS

    if price is None or prices != PRICES_GROSS:
        return price
    return net_from_gross(price, gross_tax_rate(rate))


def copy_name(name: str) -> str:
    """A free article name for the copy of a model: "… (Kopie)", then "… (Kopie 2)" … (MAT-064)."""
    limit = MaterialModel._meta.get_field("name").max_length or 200

    def candidate(number: int) -> str:
        pattern = _("%(name)s (copy)") if number == 1 else _("%(name)s (copy %(number)d)")
        suffix_length = len(pattern % {"name": "", "number": number})
        return pattern % {"name": name[: limit - suffix_length], "number": number}

    candidates = [candidate(number) for number in range(1, 100)]
    taken = set(MaterialModel.objects.filter(name__in=candidates).values_list("name", flat=True))
    return next((text for text in candidates if text not in taken), candidates[-1])


def copy_inspection_types(source: MaterialModel, target: MaterialModel) -> list[InspectionType]:
    """The inspection types that name ``source`` itself name ``target`` as well (MAT-064; MAT-030).

    Types that apply through a category need nothing: they reach every model of the category.
    """
    types = list(InspectionType.objects.filter(material_models=source))
    for inspection_type in types:
        inspection_type.material_models.add(target)
    return types


def delete_item(item: MaterialItem) -> None:
    """Delete an item that was created by mistake; used items are archived instead (MAT-022, MAT-040).

    L4: the page and the API both call this, so they refuse the same.

    Raises:
        ValidationError: The item was used in a project, booked as a vehicle, holds
            built-in bulk material or is built into another item, or other items are
            installed in it.
    """
    from django.db.models import ProtectedError

    if item.allocations.exists():
        raise ValidationError(_("This item was used in projects. Set it to “retired” instead of deleting it."))
    if item.vehicle_lines.exists():  # LOG-001: a vehicle booked in projects
        raise ValidationError(_("This vehicle is booked in projects. Set it to “retired” instead of deleting it."))
    if item.installed_quantities.exists() or item.installations.exists():  # MAT-040
        raise ValidationError(
            _("This item holds built-in bulk material or is itself built into other items. Take it out first.")
        )
    try:
        item.delete()
    except ProtectedError:
        raise ValidationError(_("Other items are installed in this item. Remove them first.")) from None
