# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views of the material module: lists, detail pages, forms, import."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import ProtectedError, Q
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, SpecialRight, module_required, request_rights, require
from rentalars.core.forms import add_validation_error
from rentalars.core.listing import paginate
from rentalars.customfields.forms import CustomValuesForm, FieldsetChoiceForm
from rentalars.masterdata.models import Category, Manufacturer, StorageLocation, Supplier, remember_location_paths
from rentalars.material import dguv, numbering, scan, serials, services
from rentalars.material.filters import MaterialItemFilter, search_items
from rentalars.material.forms import (
    PRICE_ENTRY_SESSION_KEY,
    BlockForm,
    BulkEditForm,
    ContentAddForm,
    InstallForm,
    ItemCreateForm,
    MaterialItemForm,
    MaterialModelForm,
    StatusChangeForm,
    SupplierDialogForm,
    item_copy_initial,
)
from rentalars.material.models import ARCHIVED_STATUSES, ItemStatus, MaterialFileKind, MaterialItem, MaterialModel
from rentalars.material.numbering import format_inventory_number
from rentalars.material.photo_views import head_picture, photo_context
from rentalars.material.tables import ITEM_TABLE, MODEL_TABLE
from rentalars.products.models import Product

ITEM_SORTS = {
    "id": "inventory_number",
    "name": ("material_model__name", "inventory_number"),
    "category": ("material_model__category__name", "inventory_number"),
    "status": ("status", "inventory_number"),
    "serial": "serial_number",
    "purchased": "purchase_date",
    "supplier": "supplier__name",
}


# --- Items -------------------------------------------------------------------------


@module_required(Module.MATERIAL)
def item_list(request: HttpRequest) -> HttpResponse:
    """All items, one row each with the 13 fields of MAT-011 (MAT-012, MAT-028).

    The columns can be chosen and sorted (UIX-015); the filtered view can be
    downloaded as CSV (IMP-005); chosen items can be changed together or get
    their labels (MAT-029, MAT-026).
    """
    return item_list_page(request)


def item_list_page(request: HttpRequest, *, open_points: bool = False) -> HttpResponse:
    """The list of items; with ``open_points`` the items without product, under Offene Punkte (MAT-070).

    The items without product are the sub-tab
    "Material ohne Produkt" of "Offene Punkte" (MAT-070, PRD-005) at an address of their own
    (NFA-074). ``?without_product=`` still filters the list of items.
    """
    items = MaterialItem.objects.select_related(
        "material_model",
        "material_model__category__parent",
        "material_model__manufacturer",
        "material_model__default_product",
        "product_override",
        "supplier",
        "installed_in",
        "installed_in__storage_location",
        "storage_location",
        "purchase_price_in",  # MAT-054: "#0851" in the column of the purchase price
    ).with_category_fields()
    parameters = request.GET.copy()
    if open_points:
        parameters["without_product"] = "true"
    if "archived" not in parameters and not parameters.getlist("status"):
        # Archived items stay out of the everyday list unless asked for (MAT-022).
        items = items.exclude(status__in=ARCHIVED_STATUSES)
    filtered = MaterialItemFilter(parameters, queryset=items, request=request)  # MAT-073: custom filter rights
    table = ITEM_TABLE.state(request)
    items = table.order(filtered.qs)
    if table.wants_csv:
        # UIX-015: sorted by a computed column, the rows are already a list.
        rows = items.iterator(chunk_size=2000) if hasattr(items, "iterator") else items
        return table.csv_response(rows, _("Material"))
    page = paginate(request, items)
    context: dict[str, Any] = {}
    if open_points:
        from rentalars.material.audit_views import open_points_context

        context = open_points_context("without_product")
    return render(
        request,
        "material/item_list.html",
        {
            **context,
            "open_points": open_points,
            "page": page,
            "table": table,
            "rows": table.rows(page),
            "filter": filtered,
            "categories": Category.objects.in_tree_order(),
            "suppliers": Supplier.objects.all(),
            "locations": remember_location_paths(StorageLocation.objects.all()),
            "statuses": ItemStatus.choices,
            "selected_statuses": request.GET.getlist("status"),
            "without_product_count": MaterialItem.objects.without_product().not_archived().count(),
            "bulk_form": BulkEditForm() if request_rights(request).can_write(Module.MATERIAL) else None,
        },
    )


@require_POST
@module_required(Module.MATERIAL, Level.WRITE)
def item_bulk_update(request: HttpRequest) -> HttpResponse:
    """Change status, storage location or product of the chosen items (MAT-029)."""
    from rentalars.material.item_views import safe_next

    target = safe_next(request, reverse("material:item_list"))
    ids = [
        int(value) for value in request.POST.getlist("items") if value.isascii() and value.isdigit() and len(value) < 18
    ]
    if request.POST.get("action") == "labels":
        # The same choice, for printing labels (MAT-026).
        numbers = (
            MaterialItem.objects.filter(pk__in=ids)
            .order_by("inventory_number")
            .values_list("inventory_number", flat=True)
        )
        chosen = ",".join(format_inventory_number(number) for number in numbers)
        return redirect(f"{reverse('material:labels')}?items={chosen}")
    form = BulkEditForm(request.POST)
    if not form.is_valid():
        messages.error(request, " ".join(message for errors in form.errors.values() for message in errors))
        return redirect(target)
    items = list(
        MaterialItem.objects.filter(pk__in=ids).select_related(
            "material_model__category", "material_model__default_product"
        )
    )
    try:
        hints = services.bulk_update(items, **form.changes())
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        for hint in hints:
            messages.warning(request, hint)
        messages.success(
            request,
            ngettext("%(count)d item changed.", "%(count)d items changed.", len(items)) % {"count": len(items)},
        )
    return redirect(target)


@module_required(Module.MATERIAL)
def inspection_overview(request: HttpRequest) -> HttpResponse:
    """Items whose inspection is overdue or due soon (MAT-032)."""
    from rentalars.material.inspections import SOON_DAYS, InspectionPlan
    from rentalars.material.models import InspectionType

    plan = InspectionPlan()
    try:
        within = max(0, min(365, int(request.GET.get("days", SOON_DAYS))))
    except ValueError:
        within = SOON_DAYS
    type_id = request.GET.get("type", "")
    due = plan.due_rows(within_days=within, type_id=int(type_id) if type_id.isdigit() else None)
    state = request.GET.get("state", "")
    if state in {"overdue", "soon"}:
        due = [(item_id, item_due) for item_id, item_due in due if item_due.state == state]
    # UIX-040: columns, sorting, groups and CSV (material/inspection_tables.py); the file holds every row.
    from rentalars.material.inspection_tables import INSPECTION_TABLE

    table = INSPECTION_TABLE.state(request)
    if table.wants_csv:
        from rentalars.material.inspection_tables import DueRow as CsvRow

        every = [CsvRow(row) for row in plan.with_items(due)]  # a row knows its item: ?only= can narrow the file
        remember_location_paths(item.effective_storage_location for item, _due in every)
        return table.csv_response(table.order(every), _("Inspections"))
    # Only the rows shown become objects; there may be thousands (NFA-012).
    from rentalars.material.inspection_tables import DueRow

    rows = table.order([DueRow(row) for row in plan.with_items(due[:500])])
    remember_location_paths(item.effective_storage_location for item, _due in rows)
    page = table.paginate(rows)  # UIX-050: the (at most 500) rows page by page
    return render(
        request,
        "material/inspections.html",
        {
            "tab": "inspections",
            "rows": rows,
            "table": table,
            "table_rows": table.rows(page),
            "page": page,
            "row_count": len(due),
            "types": InspectionType.objects.filter(is_active=True),
            "type_id": type_id,
            "can_batch": request_rights(request).can_write(Module.MATERIAL),  # MAT-082
            "within": within,
            # UIX-030: the number of days without a filter is not counted as an active filter.
            "soon_days": SOON_DAYS,
            "state": state,
            "has_types": not plan.is_empty,
        },
    )


@dataclass
class BatchRow:
    """One item of the form of a mass inspection: its row form and the tick of its visual inspection (MAT-082)."""

    item: MaterialItem
    form: Any
    visual: bool


@require_POST
@module_required(Module.MATERIAL, Level.WRITE)
def inspection_batch(request: HttpRequest) -> HttpResponse:
    """MAT-082: one inspection for several items – chosen in Materialverwaltung → Prüfungen.

    Day, inspector and – for an electrical inspection – the test device are asked once; each item gets its
    result, a note and its measured values. The first request (``items``) shows the form; the form sends
    itself with ``save``. All or nothing (``services.record_inspections``).
    """
    from rentalars.material.forms import BatchInspectionForm, BatchRowForm
    from rentalars.material.inspections import InspectionPlan

    back = reverse("material:inspections")
    wanted = {
        int(value) for value in request.POST.getlist("items") if value.isascii() and value.isdigit() and len(value) < 18
    }
    items = list(
        MaterialItem.objects.filter(pk__in=wanted)
        .select_related("material_model__category", "material_model__manufacturer")
        .order_by("inventory_number")
    )
    if not items:
        messages.error(request, _("Choose at least one item."))
        return redirect(back)
    if len(items) > services.MAX_BULK_ITEMS:
        messages.error(
            request, _("At most %(count)d items can be changed at once.") % {"count": services.MAX_BULK_ITEMS}
        )
        return redirect(back)
    plan = InspectionPlan()
    common: set[int] | None = None
    types_by_id = {}
    for item in items:
        applicable = plan.types_for(item.material_model_id, item.material_model.category_id)
        types_by_id.update({t.pk: t for t in applicable})
        common = {t.pk for t in applicable} if common is None else common & {t.pk for t in applicable}
    types = sorted((types_by_id[pk] for pk in common or ()), key=lambda inspection_type: inspection_type.name)
    if not types:
        messages.error(request, _("The chosen items have no inspection in common."))
        return redirect(back)
    saving = "save" in request.POST
    form = BatchInspectionForm(
        request.POST if saving else None, types=types, user=request.user, preselect=request.POST.get("type")
    )
    ticked = set(request.POST.getlist("visual")) if saving else set()
    field_cache: dict[int, list[Any]] = {}  # the length field of a category, asked for once (not per item)
    rows = [
        BatchRow(
            item=item,
            form=BatchRowForm(
                request.POST if saving else None,
                prefix=f"i{item.pk}",
                item=item,
                electrical_first=form.preselected_electrical,
                fields_by_category=field_cache,
            ),
            visual=str(item.pk) in ticked,
        )
        for item in items
    ]
    if saving and form.is_valid() and all(row.form.is_valid() for row in rows):
        inspection_type = form.cleaned_data["inspection_type"]
        entries = [
            services.BatchEntry(
                item=row.item,
                result=row.form.cleaned_data["result"] or ("" if inspection_type.is_electrical else "passed"),
                note=row.form.cleaned_data["note"],
                electrical=row.form.electrical_values(visual=row.visual) if inspection_type.is_electrical else None,
            )
            for row in rows
        ]
        try:
            recorded = services.record_inspections(
                entries,
                inspection_type,
                date=form.cleaned_data["date"],
                inspector=form.cleaned_data["inspector"],
                test_device=form.cleaned_data.get("test_device", ""),
                user=request.user,
            )
        except services.BatchInspectionError as error:
            for name, message in error.common.items():
                form.add_error(name if name in form.fields else None, message)
            for row in rows:
                for name, texts in error.by_item.get(row.item.pk, {}).items():
                    row.form.add_error(name if name in row.form.fields else None, texts)
            if not error.by_item and not error.common:
                form.add_error(None, error)
        else:
            messages.success(
                request,
                ngettext("%(count)d inspection recorded.", "%(count)d inspections recorded.", len(recorded))
                % {"count": len(recorded)},
            )
            return redirect(back)
    return render(
        request,
        "material/inspection_batch.html",
        {
            "tab": "inspections",
            "form": form,
            "rows": rows,
            "types": types,
            "saving": saving,
            "type_id": request.POST.get("type", ""),
            "item_ids": [item.pk for item in items],
            "measurements": dguv.MEASUREMENTS,
        },
    )


@module_required(Module.MATERIAL)
def item_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """One item: its data, what it is installed in, what is installed in it, its history."""
    item = get_object_or_404(
        MaterialItem.objects.select_related(
            "material_model__category",
            "material_model__manufacturer",
            "material_model__default_product",
            "product_override",
            "supplier",
            "storage_location",
            "installed_in__material_model",
            "purchase_price_in",  # MAT-054
        ),
        pk=pk,
    )
    from rentalars.material.item_views import item_context
    from rentalars.packing.services import extraction_choices
    from rentalars.projects.access import may_see_reports

    context = item_context(request, item, "item")
    # MAT-090: the photos of the item – and those of its model.
    context.update(photo_context(item, request_rights(request)))
    context["upload_url"] = reverse("material:item_photos", args=[item.pk])
    context.update(
        {
            "containers": services.container_chain(item),
            "contents": services.content_tree(item).depth_first,
            "status_form": StatusChangeForm(item=item),
            "content_form": ContentAddForm(),
            "install_form": InstallForm(),
            "block_form": BlockForm(),
            "blocks": item.blocks.filter(end__gt=timezone.now()).order_by("start"),
            "can_contain": not item.material_model.is_bulk and not item.is_archived,
            "extractions": item.extractions.select_related("project", "container"),
            "extraction_projects": extraction_choices(item, request_rights(request), request.user),
            # MAT-053: what the item earned sums up every project – a report, for who may see the reports.
            "show_revenue": may_see_reports(request_rights(request)),
        }
    )
    # LOG-002, LOG-004: a vehicle of the fleet – its data and its bookings.
    from rentalars.material.fleet_views import vehicle_context

    context.update(vehicle_context(request, item))
    # MAT-069: the box "Audit und To-Dos" – last and next audit, open to-dos, the audits so far.
    from rentalars.material.audit_views import audit_context

    context.update(audit_context(item))
    # MAT-040 (built-in quantity material): bulk material built into a case, rack or vehicle – or where a bulk row is built in.
    from rentalars.material.installed_views import installed_context

    context.update(installed_context(item))
    # Depreciation, used sale from stock: the card "Anlagevermögen" – only for who sees purchase prices.
    from rentalars.material.asset_views import asset_context

    context.update(asset_context(request, item))
    return render(request, "material/item_detail.html", context)


@module_required(Module.MATERIAL, Level.WRITE)
def item_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit an item, including "installed in" (MAT-033 ff.).

    (MAT-079) ``?next=`` – an address on this server – is
    where saving and "Abbrechen" lead, e.g. back to the audit mode.
    """
    from rentalars.material.item_views import safe_next

    item = get_object_or_404(MaterialItem.objects.select_related("material_model", "installed_in"), pk=pk)
    back = safe_next(request, reverse("material:item_detail", args=[item.pk]))
    form = MaterialItemForm(
        request.POST or None,
        instance=item,
        rights=request_rights(request),
        remembered=request.session.get(PRICE_ENTRY_SESSION_KEY),  # MAT-059: net or gross, as chosen last time
    )
    # MAT-073: the values of the fields of the model's fieldset, a form of their own next to the item's.
    values_form = CustomValuesForm(
        request.POST or None, material_model=item.material_model, item=item, rights=request_rights(request)
    )
    # Duplicate serial numbers: a serial number changed to one another item has is confirmed first.
    serial_warnings: list[str] = []
    if request.method == "POST" and form.is_valid() and values_form.is_valid():
        serial_warnings = form.serial_warnings()
        if serials.confirmed(request.POST, serial_warnings):
            serial_warnings = []
    if request.method == "POST" and form.is_valid() and values_form.is_valid() and not serial_warnings:
        edited = form.save(commit=False)
        try:
            with transaction.atomic():
                services.save_item(edited)
                values_form.save([edited])
        except ValidationError as error:
            form.add_error(None, error)
        else:
            remember_price_entry(request, form)
            hint = form.product_hint()
            if hint:
                messages.warning(request, hint)
            messages.success(request, _("Item %(id)s saved.") % {"id": edited.display_id})
            return redirect(back)
    return render(
        request,
        "material/item_form.html",
        {
            "form": form,
            "item": item,
            "values_form": values_form,
            "back": back,
            "serial_warnings": serial_warnings,
            "serial_token": serials.token_of(serial_warnings),
        },
    )


@require_POST
@module_required(Module.MATERIAL, Level.WRITE)
def item_set_status(request: HttpRequest, pk: int) -> HttpResponse:
    """Change the status of an item and note the reason (MAT-020, MAT-044, MAT-045)."""
    item = get_object_or_404(MaterialItem, pk=pk)
    try:
        services.set_status(item, request.POST.get("status", ""), reason=request.POST.get("reason", ""))
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, _("Status of %(id)s changed.") % {"id": item.display_id})
    return redirect("material:item_detail", pk=item.pk)


@require_POST
@module_required(Module.MATERIAL, Level.WRITE)
def item_content_add(request: HttpRequest, pk: int) -> HttpResponse:
    """Put another item into this one, from the container's page (MAT-046)."""
    container = get_object_or_404(MaterialItem.objects.select_related("material_model"), pk=pk)
    form = ContentAddForm(request.POST)
    if not form.is_valid():
        messages.error(request, " ".join(message for errors in form.errors.values() for message in errors))
        return redirect("material:item_detail", pk=container.pk)
    item = form.cleaned_data["item_number"]
    try:
        warnings = services.add_content(
            container,
            item,
            connection_type=form.cleaned_data["connection_type"],
            individually_rentable=form.cleaned_data["individually_rentable"],
        )
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        for warning in warnings:
            messages.warning(request, warning)
        messages.success(
            request,
            _("%(item)s is now installed in %(container)s.")
            % {"item": item.display_id, "container": container.display_id},
        )
    return redirect("material:item_detail", pk=container.pk)


@require_POST
@module_required(Module.MATERIAL, Level.WRITE)
def item_install(request: HttpRequest, pk: int) -> HttpResponse:
    """Install this item into another one, from the item's page (MAT-047) – the counterpart of "Install here"."""
    item = get_object_or_404(MaterialItem.objects.select_related("material_model"), pk=pk)
    form = InstallForm(request.POST)
    if not form.is_valid():
        messages.error(request, " ".join(message for errors in form.errors.values() for message in errors))
        return redirect("material:item_detail", pk=item.pk)
    container = form.cleaned_data["container_number"]
    try:
        warnings = services.add_content(container, item, connection_type=form.cleaned_data["connection_type"])
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        for warning in warnings:
            messages.warning(request, warning)
        messages.success(
            request,
            _("%(item)s is now installed in %(container)s.")
            % {"item": item.display_id, "container": container.display_id},
        )
    return redirect("material:item_detail", pk=item.pk)


@require_POST
@module_required(Module.MATERIAL, Level.WRITE)
def item_content_remove(request: HttpRequest, pk: int, content_pk: int) -> HttpResponse:
    """Take an item out of this one, from the container's page (MAT-046)."""
    container = get_object_or_404(MaterialItem, pk=pk)
    item = get_object_or_404(MaterialItem.objects.select_related("material_model"), pk=content_pk)
    try:
        services.remove_content(container, item)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(
            request,
            _("%(item)s was taken out of %(container)s.")
            % {"item": item.display_id, "container": container.display_id},
        )
    return redirect("material:item_detail", pk=container.pk)


@require_POST
@module_required(Module.MATERIAL, Level.DELETE)
def item_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete an item that was created by mistake; used items are archived instead (MAT-022)."""
    item = get_object_or_404(MaterialItem, pk=pk)
    model_pk = item.material_model_id
    try:
        services.delete_item(item)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect("material:item_detail", pk=item.pk)
    messages.success(request, _("Item deleted."))
    return redirect("material:model_detail", pk=model_pk)


def item_suggest(request: HttpRequest) -> JsonResponse:
    """Suggestions for fields that ask for one item: by ID, name or serial number.

    Used for "installed in" and "contains" on the item page (MAT-034,
    MAT-046) and, narrowed to one product with ``?product=``, for the wish
    for a specific item on a project line (PRJ-064) – for which read access
    to projects is enough.
    """
    rights = request_rights(request)
    require(rights.can_read(Module.MATERIAL) or rights.can_read(Module.PROJECTS))
    text = request.GET.get("q", "")
    candidates = MaterialItem.objects.select_related("material_model", "installed_in").exclude(
        status__in=ARCHIVED_STATUSES
    )
    product_id = request.GET.get("product", "")
    if product_id.isdigit():
        candidates = candidates.for_product(int(product_id))
    if request.GET.get("kind") == "bulk":  # Built-in quantity material; MAT-040: bulk rows with a free stock
        candidates = candidates.filter(material_model__tracking_mode="bulk", quantity__gt=0)
    elif request.GET.get("kind") == "container":  # … and the items that can take them
        candidates = candidates.exclude(material_model__tracking_mode="bulk")
    container_id = request.GET.get("not_in", "")
    if container_id.isdigit():
        # For "contains": the container itself and what already sits in it are no candidates.
        candidates = candidates.exclude(pk=int(container_id)).exclude(installed_in_id=int(container_id))
    id_range = numbering.id_range_for_prefix(text)
    if id_range is not None:
        # While an ID is being typed, offer every ID that starts with the digits so far.
        items = candidates.filter(inventory_number__range=id_range).order_by("inventory_number")[:10]
    else:
        items = search_items(candidates, text)[:10]
    return JsonResponse(
        [
            {
                "id": item.display_id,
                "label": f"{item.display_id} {item.material_model.name}",
                "hint": (
                    _("%(free)s free") % {"free": item.quantity}  # MAT-040: a bulk row shows its free stock
                    if request.GET.get("kind") == "bulk"
                    else _("in %(container)s")
                    % {"container": format_inventory_number(item.installed_in.inventory_number)}
                    if item.installed_in_id
                    else item.get_status_display()
                ),
            }
            for item in items
        ],
        safe=False,
    )


@module_required(Module.MATERIAL)
def item_jump(request: HttpRequest) -> HttpResponse:
    """Open an item by its ID, from the field in the head of the material management (MAT-063).

    ``?id=`` takes the ID as it is typed or copied from a list: ``0427``,
    ``427`` or ``#0427`` (IMP-015). An ID nobody has – or a text that is no
    ID at all – leads to the list of items, filtered by what was typed, with
    a message.
    """
    text = request.GET.get("id", "").strip()
    items_url = reverse("material:item_list")
    if not text:
        return redirect(items_url)
    # MAT-027: a scanner types what the label's code holds – the ID, the address of the QR code, a serial number,
    # a GTIN, a storage spot – the same function as the scan widget and the API (material.scan).
    found = scan.resolve(text, request_rights(request))
    if found.found:
        return redirect(found.url)
    try:
        number = numbering.parse_inventory_number(text)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect(f"{items_url}?{urlencode({'q': text})}")
    item = MaterialItem.objects.filter(inventory_number=number).only("pk").first()
    if item is None:
        shown = format_inventory_number(number)
        messages.error(request, _("There is no item with the ID %(id)s.") % {"id": shown})
        return redirect(f"{items_url}?{urlencode({'q': shown})}")
    return redirect("material:item_detail", pk=item.pk)


def remember_price_entry(request: HttpRequest, form: Any) -> None:
    """Keep the choice "net or gross" of a saved form for the next form of this user (MAT-059)."""
    choice = getattr(form, "price_entry", None)
    if choice is not None and request.session.get(PRICE_ENTRY_SESSION_KEY) != choice:
        request.session[PRICE_ENTRY_SESSION_KEY] = choice


# --- Models ------------------------------------------------------------------------


@module_required(Module.MATERIAL)
def model_list(request: HttpRequest) -> HttpResponse:
    """All material models with the number of their items."""
    models = (
        MaterialModel.objects.select_related("category__parent", "manufacturer", "default_product")
        .with_category_fields()
        .with_item_count()
    )
    text = request.GET.get("q", "").strip()
    if text:
        models = models.filter(name__icontains=text) | models.filter(short_name__icontains=text)
    category_id = request.GET.get("category", "")
    if category_id.isdigit():
        models = models.filter(category_id__in=Category.objects.descendant_ids(int(category_id)))
    if request.GET.get("without_product"):
        models = models.filter(default_product__isnull=True)
    table = MODEL_TABLE.state(request)
    models = table.order(models)
    if table.wants_csv:
        return table.csv_response(models, _("Material models"))
    page = paginate(request, models)
    return render(
        request,
        "material/model_list.html",
        {
            "page": page,
            "table": table,
            "rows": table.rows(page),
            "q": text,
            "categories": Category.objects.in_tree_order(),
            "category_id": category_id,
        },
    )


def _load_model(pk: int) -> MaterialModel:
    return get_object_or_404(MaterialModel.objects.select_related("category", "manufacturer", "default_product"), pk=pk)


def _model_context(request: HttpRequest, material_model: MaterialModel, tab: str) -> dict[str, Any]:
    from rentalars.material.fleet import transition_problem
    from rentalars.material.inspections import InspectionPlan

    types = InspectionPlan().types_for(material_model.pk, material_model.category_id)
    picture = head_picture(material_model, request_rights(request))
    return {
        "model": material_model,
        "tab": tab,
        "inspection_types": types,
        "picture": picture,
        # LOG-016: whether the model can be taken into the fleet.
        "can_join_fleet": not transition_problem(material_model),
    }


@module_required(Module.MATERIAL)
def model_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """One material model with its items."""
    material_model = _load_model(pk)
    items = material_model.items.select_related(
        "supplier", "installed_in", "product_override", "storage_location", "installed_in__storage_location"
    ).order_by("inventory_number")
    from rentalars.projects.access import may_see_reports

    context = _model_context(request, material_model, "model")
    # MAT-090: the photos of the model.
    context.update(photo_context(material_model, request_rights(request)))
    context["upload_url"] = reverse("material:model_photos", args=[material_model.pk])
    context["page"] = paginate(request, items)
    # MAT-058: what the model's items earned – a report, for who may see the reports (as MAT-053).
    context["show_revenue"] = may_see_reports(request_rights(request))
    if material_model.is_bulk:
        # MAT-040 (built-in quantity material): free stock against the quantity built into other items.
        from rentalars.material.installations import installed_totals

        built = installed_totals([row.pk for row in context["page"]])
        for row in context["page"]:
            row.built_in_total = built.get(row.pk, 0)
    return render(request, "material/model_detail.html", context)


@module_required(Module.MATERIAL)
def model_timeline(request: HttpRequest, pk: int) -> HttpResponse:
    """How free the model's product is and what each item does, day by day (VFG-019)."""
    from rentalars.projects.access import visible_projects
    from rentalars.schedule.services import span_from_request
    from rentalars.schedule.timelines import model_timeline as build

    require(request_rights(request).has(SpecialRight.AVAILABILITY))  # AUT-032: availability as a special right
    material_model = _load_model(pk)
    days, navigation = span_from_request(request, default_weeks=4)
    visible = set(visible_projects(request_rights(request), request.user).values_list("pk", flat=True))
    context = _model_context(request, material_model, "timeline")
    context.update({"timeline": build(material_model, days, visible), **navigation})
    return render(request, "material/model_timeline.html", context)


@module_required(Module.MATERIAL)
def model_files(request: HttpRequest, pk: int) -> HttpResponse:
    """Pictures, manuals and other documents of a model (MAT-017)."""
    from rentalars.material.forms import MaterialFileForm

    material_model = _load_model(pk)
    rights = request_rights(request)
    form = MaterialFileForm(
        request.POST or None, request.FILES or None, may_add_invoice=rights.has(SpecialRight.PURCHASE_PRICES)
    )
    if request.method == "POST":
        require(rights.can_write(Module.MATERIAL))
        if form.is_valid():
            try:
                services.add_file(
                    material_model,
                    form.cleaned_data["file"],
                    kind=form.cleaned_data["kind"],
                    title=form.cleaned_data["title"],
                    user=request.user,
                )
            except ValidationError as error:
                form.add_error("file", error)
            else:
                messages.success(request, _("File stored."))
                return redirect("material:model_files", pk=material_model.pk)
    context = _model_context(request, material_model, "files")
    # The copy of an invoice only with the right to see purchase prices.
    context.update(
        {
            "form": form,
            # MAT-090: photos have their own panel on the page of the model.
            "files": services.visible_files(material_model.files.exclude(kind=MaterialFileKind.PICTURE), rights),
        }
    )
    return render(request, "material/model_files.html", context)


def model_copy(original: MaterialModel) -> MaterialModel:
    """An unsaved copy of a model for the form of a new one (MAT-064).

    Its values – category with the category-specific values, manufacturer,
    product, description, weight, dimensions and power – under a free name
    "… (Kopie)"; not its items and not its files.
    """
    return MaterialModel(
        name=services.copy_name(original.name),
        short_name=original.short_name,
        category=original.category,
        manufacturer=original.manufacturer,
        specification=original.specification,
        field_values=dict(original.field_values or {}),
        default_product=original.default_product,
        tracking_mode=original.tracking_mode,
        weight_kg=original.weight_kg,
        length_cm=original.length_cm,
        width_cm=original.width_cm,
        height_cm=original.height_cm,
        power_w=original.power_w,
        protection_class=original.protection_class,  # MAT-077
    )


@module_required(Module.MATERIAL, Level.WRITE)
def model_edit(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    """Create or edit a material model.

    MAT-064: ``?copy=`` names a model whose values the new one
    starts with (:func:`model_copy`); its inspection types can be taken over.
    """
    material_model = get_object_or_404(MaterialModel, pk=pk) if pk else None
    initial: dict[str, Any] = {}
    original = None
    instance = material_model
    if material_model is None and request.GET.get("copy", "").isdigit():
        original = _load_model(int(request.GET["copy"]))
        instance = model_copy(original)
    elif material_model is None and request.GET.get("product", "").isdigit():
        product = Product.objects.filter(pk=int(request.GET["product"])).first()
        if product is not None:
            initial = {"default_product": product, "category": product.category, "name": product.name}
    form = MaterialModelForm(request.POST or None, instance=instance, initial=initial, copy_of=original)
    # MAT-072: the fieldset of the model – a copy starts with that of its original.
    fieldset_form = FieldsetChoiceForm(request.POST or None, material_model=material_model, copy_of=original)
    if request.method == "POST" and form.is_valid() and fieldset_form.is_valid():
        with transaction.atomic():
            saved = form.save()
            fieldset_form.save(saved)
        hint = form.product_hint()
        if hint:
            messages.warning(request, hint)
        messages.success(request, _("Material model saved."))
        return redirect("material:model_detail", pk=saved.pk)
    return render(
        request,
        "material/model_form.html",
        {"form": form, "model": material_model, "original": original, "fieldset_form": fieldset_form},
    )


@require_POST
@module_required(Module.MATERIAL, Level.DELETE)
def model_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a material model that has no items."""
    material_model = get_object_or_404(MaterialModel, pk=pk)
    try:
        material_model.delete()
    except ProtectedError:
        messages.error(request, _("This model still has items and cannot be deleted."))
        return redirect("material:model_detail", pk=pk)
    messages.success(request, _("Material model deleted."))
    return redirect("material:model_list")


@module_required(Module.MATERIAL, Level.WRITE)
def item_create(request: HttpRequest, model_pk: int) -> HttpResponse:
    """Create one or several items of a model (MAT-006, MAT-050).

    MAT-050: from a start ID on, with a serial number per item, the
    supplier typed (and created if new), invoice number and invoice date.

    MAT-059: the purchase price net or gross, as the user chose last time; ``?copy=`` names an item of the
    model whose purchase data and storage location the form starts with (duplicate).
    """
    material_model = get_object_or_404(MaterialModel, pk=model_pk)
    rights = request_rights(request)
    copy_id = request.GET.get("copy", "")
    original = (
        MaterialItem.objects.select_related("supplier", "material_model", "storage_location", "installed_in")
        .filter(pk=int(copy_id), material_model=material_model)
        .first()
        if copy_id.isdigit()
        else None
    )
    form = ItemCreateForm(
        request.POST or None,
        material_model=material_model,
        rights=rights,
        initial=item_copy_initial(original, rights) if original is not None else None,
        remembered=request.session.get(PRICE_ENTRY_SESSION_KEY),
    )
    # MAT-073: the values for all new items; a duplicate starts with those of its original, unique
    # ones left out. With several items at once required values may stay empty.
    values_form = CustomValuesForm(
        request.POST or None,
        material_model=material_model,
        rights=rights,
        copy_of=original,
        several=not material_model.is_bulk,
    )
    # Duplicate serial numbers: a serial number that exists already is a warning the user confirms with
    # "create anyway"; the form is shown again with it first.
    serial_warnings: list[str] = []
    if request.method == "POST" and form.is_valid() and values_form.is_valid():
        serial_warnings = form.serial_warnings()
        if serials.confirmed(request.POST, serial_warnings):
            serial_warnings = []
    if request.method == "POST" and form.is_valid() and values_form.is_valid() and not serial_warnings:
        remember_price_entry(request, form)
        try:
            with transaction.atomic():
                created = services.create_items(
                    material_model,
                    form.cleaned_data.get("count") or 1,
                    inventory_number=form.cleaned_data["inventory_number"],
                    serial_numbers=form.cleaned_data["serial_list"],
                    price_for_set=bool(form.cleaned_data.get("price_for_set")),  # MAT-054
                    **form.item_fields(),
                )
                lacking = values_form.save(created)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            if lacking:
                messages.warning(
                    request,
                    ngettext(
                        "%(count)d new item lacks a required value of a custom field; fill it in per item.",
                        "%(count)d new items lack a required value of a custom field; fill it in per item.",
                        len(lacking),
                    )
                    % {"count": len(lacking)},
                )
            if len(created) == 1:
                messages.success(request, _("Item %(id)s created.") % {"id": created[0].display_id})
            else:
                messages.success(
                    request,
                    _("%(count)d items created: %(first)s to %(last)s.")
                    % {"count": len(created), "first": created[0].display_id, "last": created[-1].display_id},
                )
            return redirect("material:model_detail", pk=material_model.pk)
    return render(
        request,
        "material/item_create.html",
        {
            "form": form,
            "model": material_model,
            "original": original,
            "values_form": values_form,
            "serial_warnings": serial_warnings,
            "serial_token": serials.token_of(serial_warnings),
        },
    )


@require_POST
@module_required(Module.MATERIAL, Level.WRITE)
def model_create_product(request: HttpRequest, pk: int) -> HttpResponse:
    """MAT-051: turn a model without product into a product of the same name and open it."""
    rights = request_rights(request)
    require(rights.can_write(Module.PRODUCTS))
    material_model = _load_model(pk)
    try:
        product = services.create_product_from_model(material_model, rights)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect("material:model_detail", pk=material_model.pk)
    if rights.has(SpecialRight.PRICES):
        messages.success(
            request,
            _("Product %(number)s created with the model. Enter its price.") % {"number": product.article_number},
        )
        return redirect("products:edit", pk=product.pk)
    messages.success(
        request,
        _("Product %(number)s created with the model. Its price is 0; somebody with the price right enters it.")
        % {"number": product.article_number},
    )
    return redirect("products:detail", pk=product.pk)


@require_POST
@module_required(Module.MATERIAL, Level.WRITE)
def model_assign(request: HttpRequest) -> HttpResponse:
    """PRD-046: give an existing model without product to a product, from the product's page."""
    product = get_object_or_404(
        Product, pk=request.POST.get("product") if request.POST.get("product", "").isdigit() else 0
    )
    model_id = request.POST.get("material_model", "")
    material_model = (
        MaterialModel.objects.select_related("category").filter(pk=int(model_id)).first()
        if model_id.isdigit()
        else None
    )
    if material_model is None:
        messages.error(request, _("Choose a model from the suggestions."))
        return redirect("products:detail", pk=product.pk)
    try:
        hint = services.assign_model_to_product(material_model, product)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        if hint:
            messages.warning(request, hint)
        messages.success(
            request,
            _("%(model)s now belongs to %(product)s.")
            % {"model": material_model.name, "product": product.article_number},
        )
    return redirect("products:detail", pk=product.pk)


# --- Suggestions for typed fields (MAT-048, MAT-050, PRD-046) -------------------------------------

#: How many suggestions a typed field gets.
SUGGESTIONS = 12


def _name_suggestions(queryset: Any, text: str, new_hint: str, can_create: bool) -> list[dict[str, Any]]:
    """Names for a field that takes the typed text itself; a new name is offered last (MAT-048, MAT-050).

    The value of a suggestion is the name: choosing it puts the name into the
    field, and saving finds the record by its name – or creates it.
    """
    text = text.strip()
    names = list(
        queryset.filter(is_active=True, name__icontains=text)
        .order_by("name")
        .values_list("name", flat=True)[:SUGGESTIONS]
    )
    results: list[dict[str, Any]] = [{"id": name, "label": name} for name in names]
    if text and can_create and not queryset.filter(name__iexact=text).exists():
        results.append({"id": text, "label": text, "hint": new_hint, "create": True})
    return results


def manufacturer_suggest(request: HttpRequest) -> JsonResponse:
    """Suggestions for the manufacturer of a model; a name not known yet is offered as new (MAT-048)."""
    rights = request_rights(request)
    require(rights.can_read(Module.MATERIAL))
    results = _name_suggestions(
        Manufacturer.objects.all(), request.GET.get("q", ""), _("new manufacturer"), rights.can_write(Module.MATERIAL)
    )
    return JsonResponse(results, safe=False)


def supplier_suggest(request: HttpRequest) -> JsonResponse:
    """Suggestions for "bought from" of an item; a name not known yet is offered as new (MAT-050).

    MAT-060: choosing "new supplier" opens the form of the supplier's master data in a dialog
    (``create_url``, :func:`supplier_create`); for who may create suppliers with their master data.
    """
    rights = request_rights(request)
    require(rights.can_read(Module.MATERIAL))
    results = _name_suggestions(
        Supplier.objects.all(), request.GET.get("q", ""), _("new supplier"), rights.can_write(Module.MATERIAL)
    )
    if may_create_supplier(rights):
        for result in results:
            if result.get("create"):
                result["create_url"] = f"{reverse('material:supplier_create')}?{urlencode({'name': result['id']})}"
    return JsonResponse(results, safe=False)


def may_create_supplier(rights: Any) -> bool:
    """Who may create a supplier with its master data (MAT-060): as through the API (``/suppliers``, MAT-019).

    Suppliers belong to the master data – write access to the Administration –, but who keeps the material may
    maintain them, too (``masterdata.api.SupplierViewSet``).
    """
    return rights.can_write(Module.MATERIAL) or rights.can_write(Module.ADMINISTRATION)


def supplier_create(request: HttpRequest) -> HttpResponse:
    """A new supplier with its master data, in a dialog over the form that asks for one (MAT-060).

    Opened by "new supplier" of a supplier field (``create_url`` of
    :func:`supplier_suggest`) or by a link with ``hx-get`` into the dialog of
    the page. ``?name=`` takes over what was typed; ``?field=`` names the
    field that receives the supplier. Saved, the answer (204) names the
    supplier with the event ``supplierCreated`` – ``{"id", "name", "label",
    "field"}`` – and closes the dialog; the page script puts the name into
    the field the dialog came from, and the form underneath keeps what was
    typed. With ``field`` the answer carries ``objectCreated`` as well, for a
    type-ahead field that takes the supplier's ID (PRJ-070).
    """
    rights = request_rights(request)
    require(may_create_supplier(rights))
    from rentalars.projects.subrentals import create_supplier

    field = request.GET.get("field", "")
    if not re.fullmatch(r"[\w-]{1,80}", field):
        field = ""  # the name of a form field, nothing else: the page script looks for it
    form = SupplierDialogForm(request.POST or None, initial={"name": request.GET.get("name", "").strip()[:120]})
    if request.method == "POST" and form.is_valid():
        try:
            supplier = create_supplier(form.save(commit=False))
        except ValidationError as error:
            add_validation_error(form, error)
        else:
            answer: dict[str, Any] = {
                "supplierCreated": {"id": supplier.pk, "name": supplier.name, "label": supplier.name, "field": field}
            }
            if field:
                answer["objectCreated"] = {"field": field, "id": supplier.pk, "label": supplier.name}
            answer["closeDialog"] = True
            response = HttpResponse(status=204)
            response["HX-Trigger"] = json.dumps(answer)
            return response
    return render(request, "material/_supplier_dialog.html", {"form": form, "action": request.get_full_path()})


def product_suggest(request: HttpRequest) -> JsonResponse:
    """Products a model can belong to – rental and sale products, vehicles (LOG-002) – by number or name (MAT-048).

    Review (MAT-076, PRD-043): ``?for=purchase`` – the row of a purchase – offers no customer material.
    """
    from rentalars.material.purchases import purchase_products
    from rentalars.products.models import MATERIAL_KINDS

    require(request_rights(request).can_read(Module.MATERIAL))
    text = request.GET.get("q", "").strip()
    if request.GET.get("for") == "purchase":
        products = purchase_products().select_related("owner")
    else:
        products = Product.objects.filter(kind__in=MATERIAL_KINDS, is_active=True).select_related("owner")
    if text:
        products = products.filter(Q(article_number__icontains=text) | Q(name__icontains=text))
    results = []
    for product in products.order_by("article_number")[:SUGGESTIONS]:
        hint = product.get_kind_display()
        if product.owner_id:
            hint = _("customer material of %(owner)s") % {"owner": product.owner.name}  # PRD-043
        results.append({"id": product.pk, "label": f"{product.article_number} {product.name}", "hint": hint})
    return JsonResponse(results, safe=False)


def _model_search_filter(text: str) -> Q:
    """Every word of the text must be found in the name, short name, manufacturer or category of a model."""
    condition = Q()
    for word in text.split():
        condition &= (
            Q(name__icontains=word)
            | Q(short_name__icontains=word)
            | Q(manufacturer__name__icontains=word)
            | Q(category__name__icontains=word)
        )
    return condition


def model_suggest(request: HttpRequest) -> JsonResponse:
    """Models without product, by words of the name, short name, manufacturer or category (PRD-046).

    Model search: "Martin MAC" finds "MAC Aura" of the manufacturer Martin – the words may be spread over
    the fields – and an empty text lists the first models (the field suggests when it is entered). Models that match
    but belong to a product already are named last, as rows that cannot be chosen, and a search without any hit says
    so.
    """
    rights = request_rights(request)
    require(rights.can_read(Module.MATERIAL))
    sees_products = rights.can_read(Module.PRODUCTS)  # (R3-10) article numbers are the products' data
    text = request.GET.get("q", "").strip()
    models = MaterialModel.objects.select_related("category", "manufacturer", "default_product")
    if text:
        models = models.filter(_model_search_filter(text))
    results: list[dict[str, Any]] = []
    for model in models.filter(default_product__isnull=True).order_by("name")[:SUGGESTIONS]:
        results.append(
            {
                "id": model.pk,
                "label": model.name,
                "detail": model.manufacturer.name if model.manufacturer_id else "",
                "hint": model.category.name,
            }
        )
    if text and len(results) < SUGGESTIONS:
        taken = models.filter(default_product__isnull=False).order_by("name")[: min(3, SUGGESTIONS - len(results))]
        for model in taken:
            results.append(
                {
                    "id": "",
                    "label": model.name,
                    "hint": (
                        _("belongs to %(product)s already") % {"product": model.default_product.article_number}
                        if sees_products
                        else _("belongs to a product already")
                    ),
                    "disabled": True,
                }
            )
    if text and not results:
        results.append(
            {"id": "", "label": _("No model found. Only models without product can be assigned."), "disabled": True}
        )
    elif not results:
        results.append({"id": "", "label": _("All models belong to a product already."), "disabled": True})
    return JsonResponse(results, safe=False)


# --- Import (IMP-002, IMP-003) ------------------------------------------------------


@module_required(Module.MATERIAL, Level.WRITE)
def material_import(request: HttpRequest) -> HttpResponse:
    """Import the material list: file, column mapping with dry run, import (``core.import_views``)."""
    from rentalars.core.import_views import import_page

    return import_page(request, "material")


@module_required(Module.MATERIAL)
def item_by_code(request: HttpRequest, code: str) -> HttpResponse:
    """``/m/0042``: where the QR code on a label leads – the item's page (MAT-026, MAT-027)."""
    item = services.find_item_by_code(code)
    if item is None:
        raise Http404
    return redirect("material:item_detail", pk=item.pk)
