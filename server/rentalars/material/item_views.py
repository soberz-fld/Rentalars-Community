# SPDX-License-Identifier: GPL-3.0-or-later
"""The pages of a single item beyond its data: timeline, inspections, files, defects, blocks (stage 5).

Each page shows the head of the item with its tabs (``material/_item_head.html``).
The business rules live in ``material.services``; the API calls the same
functions (API-002).
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, SpecialRight, module_required, request_rights, require
from rentalars.core.uploads import document_response
from rentalars.material import services
from rentalars.material.forms import BlockForm, DefectReportForm, InspectionForm, MaterialFileForm
from rentalars.material.history import item_history
from rentalars.material.inspections import OVERDUE, InspectionPlan
from rentalars.material.models import (
    DefectReport,
    Inspection,
    ItemBlock,
    ItemStatus,
    MaterialFile,
    MaterialFileKind,
    MaterialItem,
)


def safe_next(request: HttpRequest, default: str) -> str:
    """The address to go back to after a form: ``next`` if it stays on this server, else ``default``."""
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=False):
        return target
    return default


def _load_item(pk: int) -> MaterialItem:
    return get_object_or_404(
        MaterialItem.objects.select_related(
            "material_model__category",
            "material_model__manufacturer",
            "material_model__default_product",
            "product_override",
            "supplier",
            "storage_location",
            "installed_in__material_model",
            "installed_in__storage_location",
            "taken_out_of",
            "purchase_price_in",  # MAT-054
        ),
        pk=pk,
    )


def item_context(
    request: HttpRequest, item: MaterialItem, tab: str, plan: InspectionPlan | None = None
) -> dict[str, Any]:
    """What every page of an item needs: the item, the tab, due inspections, problems of its contents (MAT-038)."""
    plan = plan or InspectionPlan()
    dues = plan.dues_for([item]).get(item.pk, [])
    contents = list(MaterialItem.objects.filter(installed_in=item).select_related("material_model__category"))
    problems = []
    for content in contents:
        if content.status == ItemStatus.DEFECTIVE:
            problems.append(_("%(id)s inside is defective") % {"id": content.display_id})
    overdue = plan.dues_for(contents) if contents else {}
    for content in contents:
        if any(due.state == OVERDUE for due in overdue.get(content.pk, [])):
            problems.append(_("%(id)s inside: inspection overdue") % {"id": content.display_id})
    from rentalars.material.audits import head_badges

    # MAT-069: "Audit fällig" and the open to-dos as badges in the head of every tab of the item.
    from rentalars.material.photo_views import head_picture

    # MAT-090: the first photo of the item – else that of its model – shows in the head.
    picture = head_picture(item, request_rights(request))
    return {
        "item": item,
        "tab": tab,
        "inspection_dues": dues,
        "content_problems": problems,
        "picture": picture,
        **head_badges(item),
    }


# --- Timeline (VFG-019) ------------------------------------------------------------------------


@module_required(Module.MATERIAL)
def item_timeline(request: HttpRequest, pk: int) -> HttpResponse:
    """When is the item out, wished for, blocked, due for inspection? (VFG-019)."""
    from rentalars.projects.access import visible_projects
    from rentalars.schedule.services import span_from_request
    from rentalars.schedule.timelines import item_timeline as build

    require(request_rights(request).has(SpecialRight.AVAILABILITY))  # AUT-032: availability as a special right
    item = _load_item(pk)
    days, navigation = span_from_request(request, default_weeks=4)
    visible = set(visible_projects(request_rights(request), request.user).values_list("pk", flat=True))
    plan = InspectionPlan()
    context = item_context(request, item, "timeline", plan)
    context.update({"timeline": build(item, days, visible, plan), **navigation})
    return render(request, "material/item_timeline.html", context)


# --- History (MAT-025) --------------------------------------------------------------------------


@module_required(Module.MATERIAL)
def item_history_page(request: HttpRequest, pk: int) -> HttpResponse:
    """Status, changes, installations and deployments of the item (MAT-025, MAT-039)."""
    item = _load_item(pk)
    context = item_context(request, item, "history")
    context["history"] = item_history(item, request_rights(request))
    return render(request, "material/item_history.html", context)


# --- Defects (MAT-023) --------------------------------------------------------------------------


@module_required(Module.MATERIAL, Level.WRITE)
def item_defect(request: HttpRequest, pk: int) -> HttpResponse:
    """Report a defect with description and photo – made for a phone in the warehouse (MAT-023)."""
    item = _load_item(pk)
    form = DefectReportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.report_defect(
                item,
                form.cleaned_data["description"],
                photo=form.cleaned_data.get("photo"),
                context=request.POST.get("context", "")[:250],
                user=request.user,
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, _("Defect of %(id)s reported. The warehouse was told.") % {"id": item.display_id})
            return redirect(safe_next(request, reverse("material:item_files", args=[item.pk])))
    context = item_context(request, item, "files")
    context["form"] = form
    return render(request, "material/item_defect.html", context)


@module_required(Module.MATERIAL)
def defect_photo(request: HttpRequest, pk: int) -> HttpResponse:
    """The photo of a defect report, after the rights were checked (NFA-007)."""
    report = get_object_or_404(DefectReport, pk=pk)
    if not report.photo:
        raise Http404
    return document_response(report.photo.name, f"defekt-{report.item.display_id}.jpg")


# --- Blocks (MAT-024) ---------------------------------------------------------------------------


@require_POST
@module_required(Module.MATERIAL, Level.WRITE)
def item_block_add(request: HttpRequest, pk: int) -> HttpResponse:
    """Block the item for a period (MAT-024)."""
    item = _load_item(pk)
    form = BlockForm(request.POST)
    if form.is_valid():
        try:
            services.add_block(
                item,
                form.cleaned_data["start"],
                form.cleaned_data["end"],
                form.cleaned_data["reason"],
                user=request.user,
            )
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, _("%(id)s is blocked for that period.") % {"id": item.display_id})
    else:
        messages.error(request, " ".join(message for errors in form.errors.values() for message in errors))
    return redirect("material:item_detail", pk=item.pk)


@require_POST
@module_required(Module.MATERIAL, Level.WRITE)
def item_block_delete(request: HttpRequest, pk: int, block_pk: int) -> HttpResponse:
    """Lift a block (MAT-024)."""
    block = get_object_or_404(ItemBlock, pk=block_pk, item_id=pk)
    services.remove_block(block)
    messages.success(request, _("Block lifted."))
    return redirect("material:item_detail", pk=pk)


# --- Taking out and putting back (MAT-043) ------------------------------------------------------


@require_POST
@module_required(Module.MATERIAL, Level.WRITE)
def item_take_out(request: HttpRequest, pk: int) -> HttpResponse:
    """Take a loose item out of its case in one step (MAT-043)."""
    item = _load_item(pk)
    container = item.installed_in
    try:
        services.take_out(item)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(
            request,
            _("%(item)s taken out of %(container)s.") % {"item": item.display_id, "container": container.display_id},
        )
    return redirect(safe_next(request, reverse("material:item_detail", args=[item.pk])))


@require_POST
@module_required(Module.MATERIAL, Level.WRITE)
def item_put_back(request: HttpRequest, pk: int) -> HttpResponse:
    """Put a loose item back where it was taken out (MAT-043)."""
    item = _load_item(pk)
    container = item.taken_out_of
    try:
        services.put_back(item)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(
            request,
            _("%(item)s is back in %(container)s.") % {"item": item.display_id, "container": container.display_id},
        )
    return redirect(safe_next(request, reverse("material:item_detail", args=[item.pk])))


# --- Inspections (MAT-031) ----------------------------------------------------------------------


@module_required(Module.MATERIAL)
def item_inspections(request: HttpRequest, pk: int) -> HttpResponse:
    """The inspections of an item: what is due, what was done, record a new one (MAT-031)."""
    item = _load_item(pk)
    plan = InspectionPlan()
    types = plan.types_for(item.material_model_id, item.material_model.category_id)
    form = InspectionForm(request.POST or None, request.FILES or None, types=types, item=item, user=request.user)
    if request.method == "POST":
        if not request_rights(request).can_write(Module.MATERIAL):
            raise Http404
        if form.is_valid():
            try:
                services.record_inspection(
                    item,
                    form.cleaned_data["inspection_type"],
                    date=form.cleaned_data["date"],
                    inspector=form.cleaned_data["inspector"],
                    result=form.cleaned_data["result"],
                    note=form.cleaned_data["note"],
                    protocol=form.cleaned_data.get("protocol"),
                    user=request.user,
                    electrical=form.electrical_values(),  # MAT-078
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, _("Inspection recorded."))
                return redirect("material:item_inspections", pk=item.pk)
    context = item_context(request, item, "inspections", plan)
    inspections = list(item.inspections.select_related("inspection_type").order_by("-date", "-id"))
    context.update(
        {
            "form": form,
            "types": types,
            "inspections": inspections,
            # MAT-078: the column of measured values only where an electrical inspection was recorded.
            "has_measurements": any(inspection.is_electrical for inspection in inspections),
        }
    )
    return render(request, "material/item_inspections.html", context)


@require_POST
@module_required(Module.MATERIAL, Level.WRITE)
def inspection_check(request: HttpRequest, pk: int) -> HttpResponse:
    """MAT-078: the values of the form so far against their limits, with the suggested result.

    Asked by the form of an electrical inspection while values are typed (htmx); the answer replaces the
    suggestion and, out of band, the limit and verdict next to every value. Nothing is stored. Without
    scripts the same appears when the form is sent.
    """
    item = _load_item(pk)
    types = InspectionPlan().types_for(item.material_model_id, item.material_model.category_id)
    form = InspectionForm(request.POST, types=types, item=item)
    if not form.electrical_type_ids:
        raise Http404
    return render(request, "material/_dguv_check.html", {"form": form, "item": item, "out_of_band": True})


@module_required(Module.MATERIAL)
def inspection_protocol(request: HttpRequest, pk: int) -> HttpResponse:
    """The protocol of an inspection (MAT-031), after the rights were checked."""
    inspection = get_object_or_404(Inspection, pk=pk)
    if not inspection.protocol:
        raise Http404
    return document_response(inspection.protocol.name, inspection.protocol_name or "protokoll.pdf")


@module_required(Module.MATERIAL)
def inspection_report(request: HttpRequest, pk: int) -> HttpResponse:
    """MAT-078: the printable protocol of an electrical inspection as PDF – the values with limits and verdicts."""
    from rentalars.material.inspection_report import render_report_pdf, report_file_name

    inspection = get_object_or_404(
        Inspection.objects.select_related("item__material_model__manufacturer", "inspection_type", "recorded_by"),
        pk=pk,
    )
    if not inspection.is_electrical:
        raise Http404
    response = HttpResponse(render_report_pdf(inspection), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{report_file_name(inspection)}"'
    return response


# --- Files (MAT-017) ----------------------------------------------------------------------------


@module_required(Module.MATERIAL)
def item_files(request: HttpRequest, pk: int) -> HttpResponse:
    """Pictures and documents of the item and of its model, and its defect reports (MAT-017, MAT-023)."""
    item = _load_item(pk)
    rights = request_rights(request)
    form = MaterialFileForm(
        request.POST or None, request.FILES or None, may_add_invoice=rights.has(SpecialRight.PURCHASE_PRICES)
    )
    if request.method == "POST":
        if not rights.can_write(Module.MATERIAL):
            raise Http404
        if form.is_valid():
            try:
                services.add_file(
                    item,
                    form.cleaned_data["file"],
                    kind=form.cleaned_data["kind"],
                    title=form.cleaned_data["title"],
                    user=request.user,
                )
            except ValidationError as error:
                form.add_error("file", error)
            else:
                messages.success(request, _("File stored."))
                return redirect("material:item_files", pk=item.pk)
    context = item_context(request, item, "files")
    context.update(
        {
            "form": form,
            # The copy of an invoice shows the purchase prices – only with that right.
            # MAT-090: photos have their own panel on the page of the item.
            "files": services.visible_files(item.files.exclude(kind=MaterialFileKind.PICTURE), rights),
            "model_files": services.visible_files(
                item.material_model.files.exclude(kind=MaterialFileKind.PICTURE), rights
            ),
            # MAT-057: with the service case made of each report, if any.
            "defects": item.defect_reports.select_related("reported_by").prefetch_related("service_cases"),
        }
    )
    return render(request, "material/item_files.html", context)


@module_required(Module.MATERIAL)
def material_file(request: HttpRequest, pk: int) -> HttpResponse:
    """A file of a model or item, after the rights were checked (NFA-007)."""
    stored = get_object_or_404(services.visible_files(MaterialFile.objects.all(), request_rights(request)), pk=pk)
    return document_response(stored.file.name, stored.original_name)


@module_required(Module.MATERIAL)
def material_file_small(request: HttpRequest, pk: int) -> HttpResponse:
    """The preview of a photo (MAT-090); an older picture has none and is delivered whole."""
    stored = get_object_or_404(services.visible_files(MaterialFile.objects.all(), request_rights(request)), pk=pk)
    return document_response((stored.thumbnail or stored.file).name, stored.original_name)


@require_POST
@module_required(Module.MATERIAL, Level.DELETE)
def material_file_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Remove a file of a model or item."""
    stored = get_object_or_404(services.visible_files(MaterialFile.objects.all(), request_rights(request)), pk=pk)
    # MAT-090: a photo is removed from the page where it is shown, a document from the tab "Files".
    picture = stored.kind == MaterialFileKind.PICTURE
    if stored.item_id:
        target = reverse("material:item_detail" if picture else "material:item_files", args=[stored.item_id])
    else:
        target = reverse(
            "material:model_detail" if picture else "material:model_files", args=[stored.material_model_id]
        )
    if picture:
        target += "#photos"
    services.delete_file(stored)
    messages.success(request, _("Photo removed.") if picture else _("File removed."))
    return redirect(target)
