# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser pages of Buchhaltung → Eingangsrechnungen (DOK-023, DOK-024).

* ``accounting/incoming/`` – the register: every incoming invoice as a table (columns, sorting, groups, CSV), filters
  (supplier, status, dates, search) and the upload of a new invoice;
* ``accounting/incoming/<id>/`` – one invoice: file, head, note, status, positions, the ancillary costs spread over the
  goods with the acquisition cost of each position, what was booked in;
* ``accounting/incoming/<id>/book/`` – booking in the goods as items or quantities: a row per goods position, a preview
  of what would be made, and the explicit confirmation;
* ``administration/incoming-invoices/`` – the settings: limit of a low-value asset (GWG), standard useful life.

Rights: :mod:`rentalars.incoming.access` – purchase prices and read access to the material to look, write access to
the material to change and book in, the delete level to delete; the settings need the module "Administration".
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, module_required, request_rights
from rentalars.core.forms import add_validation_error
from rentalars.core.listing import paginate
from rentalars.core.uploads import document_response
from rentalars.incoming import access, booking, costing, filters, services
from rentalars.incoming.forms import (
    HeadForm,
    SettingsForm,
    UploadForm,
    booking_formset,
    position_formset,
)
from rentalars.incoming.models import IncomingInvoice, InvoicePosition, InvoiceStatus, ReadingState
from rentalars.incoming.tables import INCOMING_TABLE
from rentalars.masterdata.models import StorageLocation
from rentalars.material import purchases
from rentalars.material.models import MaterialItem
from rentalars.products.models import Product


def _invoice(pk: int) -> IncomingInvoice:
    """An invoice with its supplier, or 404."""
    return get_object_or_404(IncomingInvoice.objects.select_related("supplier", "reading_job"), pk=pk)


def outgoing_tabs(rights: Any) -> dict[str, Any]:
    """The tabs of Buchhaltung a user sees."""
    from rentalars.documents import outgoing

    return outgoing.tabs(rights)


def _tabs(rights: Any) -> dict[str, Any]:
    """The tabs of Buchhaltung and the one of this page."""
    return {**outgoing_tabs(rights), "tab": "incoming"}


# --- The register ----------------------------------------------------------------------------------------------


@module_required(Module.MATERIAL)
def invoice_list(request: HttpRequest) -> HttpResponse:
    """The register: the invoices filtered, sorted, grouped – or as CSV."""
    rights = request_rights(request)
    access.require_see(rights)
    found = filters.parse(request.GET)
    filtered = found.apply(filters.invoices())
    table = INCOMING_TABLE.state(request)
    rows = table.order(filtered)
    if table.wants_csv:
        return table.csv_response(rows, _("Incoming invoices"))
    page = paginate(request, rows)
    return render(
        request,
        "incoming/list.html",
        {
            **_tabs(rights),
            "page": page,
            "table": table,
            "rows": table.rows(page),
            "filters": found,
            "status_choices": filters.status_choices(),
            "suppliers": filters.suppliers_of_invoices(),
            "totals": filters.totals(filtered),
            "may_change": access.may_change(rights),
        },
    )


@module_required(Module.MATERIAL)
def invoice_capture(request: HttpRequest) -> HttpResponse:
    """Buchhaltung → Beleg erfassen: upload a new invoice; it is read at once and its page opens."""
    rights = request_rights(request)
    access.require_change(rights)
    return render(
        request,
        "incoming/capture.html",
        {**{**outgoing_tabs(rights), "tab": "capture"}, "upload_form": UploadForm(), "may_change": True},
    )


@module_required(Module.MATERIAL, Level.WRITE)
@require_POST
def invoice_from_purchase(request: HttpRequest) -> HttpResponse:
    """Record a purchase of the material management as an incoming invoice (the answer "yes" of the question).

    ``items`` names the items as the page "Purchase entered" does (``0042-0047,0050``).
    """
    from rentalars.material.purchase_views import _numbers

    rights = request_rights(request)
    access.require_change(rights)
    items = list(
        MaterialItem.objects.filter(inventory_number__in=_numbers(request.POST.get("items", "")))
        .select_related("material_model", "supplier")
        .order_by("inventory_number")
    )
    if not items:
        messages.error(request, _("No items were named."))
        return redirect("material:item_list")
    try:
        invoice, created = services.create_from_purchase(items, user=request.user)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect(f"{reverse('material:purchase_done')}?items={request.POST.get('items', '')}")
    if created:
        messages.success(
            request,
            _("The purchase is recorded as an incoming invoice. Enter the totals and the tax accounts of the invoice."),
        )
    else:
        messages.info(request, _("This invoice is in the register already."))
    return redirect("incoming:detail", pk=invoice.pk)


@module_required(Module.MATERIAL, Level.WRITE)
@require_POST
def invoice_upload(request: HttpRequest) -> HttpResponse:
    """Store an uploaded invoice, read it and open its page."""
    access.require_change(request_rights(request))
    form = UploadForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            invoice = services.create_from_upload(form.cleaned_data["file"], user=request.user)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            _tell_reading(request, invoice)
            return redirect(f"{reverse('incoming:detail', args=[invoice.pk])}?asked=book")
    else:
        for errors in form.errors.values():
            messages.error(request, " ".join(errors))
    return redirect("incoming:capture")


def _tell_reading(request: HttpRequest, invoice: IncomingInvoice) -> None:
    """Say what became of reading a new invoice."""
    state = invoice.reading_state
    error = (invoice.reading or {}).get("error")
    if state == ReadingState.FAILED:
        messages.warning(request, error or _("The invoice could not be read. Enter it by hand."))
    elif state == ReadingState.RUNNING:
        messages.info(
            request, _("The invoice is uploaded; the AI reads it now. You can correct everything afterwards.")
        )
    elif (invoice.reading or {}).get("source") == "einvoice":
        messages.success(request, _("The e-invoice was uploaded and read from its XML. Check every value."))
        if invoice.reading.get("einvoice", {}).get("warnings"):
            messages.warning(request, _("The file contradicts itself in places; see the notes under “File”."))
    else:
        messages.success(request, _("The invoice was uploaded and read. Check every value."))
        if error:
            messages.warning(request, error)


# --- One invoice -----------------------------------------------------------------------------------------------


def _booked_info(invoice: IncomingInvoice) -> dict[int, dict[str, Any]]:
    """Per position: the items made of it – rows, pieces and the IDs as a short text."""
    counts = services.booked_counts(invoice)
    info: dict[int, dict[str, Any]] = {}
    numbers: dict[int, list[int]] = {}
    for position_id, number in MaterialItem.objects.filter(source_position__invoice=invoice).values_list(
        "source_position", "inventory_number"
    ):
        numbers.setdefault(position_id, []).append(number)
    for position_id, found in counts.items():
        info[position_id] = {**found, "ids": purchases.compact_ids(numbers.get(position_id, []))}
    return info


def _detail_context(
    request: HttpRequest, invoice: IncomingInvoice, head: HeadForm, formset: Any, **extra: Any
) -> dict[str, Any]:
    """What the page of an invoice shows."""
    rights = request_rights(request)
    cost = costing.costing_of(invoice)
    booked = _booked_info(invoice)
    forms_with_cost = []
    for form in formset.forms:
        position = form.instance if form.instance.pk else None
        row = cost.row_of(position) if position is not None else None
        forms_with_cost.append(
            {"form": form, "position": position, "cost": row, "booked": booked.get(position.pk if position else 0)}
        )
    return {
        **_tabs(rights),
        "invoice": invoice,
        "head": head,
        "formset": formset,
        "rows": forms_with_cost,
        "costing": cost,
        "booked": booked,
        "has_goods": any(position.is_goods for position in invoice.positions.all()),
        "sum": services.kontierung_sum_of(invoice),
        "duplicates": services.duplicates(invoice),
        "may_change": access.may_change(rights),
        "check_url": reverse("incoming:check", args=[invoice.pk]) if access.may_change(rights) else "",
        "check_next": reverse("incoming:detail", args=[invoice.pk]) + "#incoming-einvoice",
        "may_delete": access.may_delete(rights) and not booked,
        "supplier_missing": bool(invoice.supplier_name) and not invoice.supplier_id,
        "job": invoice.reading_job if invoice.reading_state == ReadingState.RUNNING else None,
        "status_choices": InvoiceStatus.choices,
        "asked_book": request.GET.get("asked") == "book" and access.may_change(rights),
        **extra,
    }


@module_required(Module.MATERIAL)
def invoice_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """One invoice: head, note, status, positions, ancillary costs and acquisition cost, what was booked in."""
    rights = request_rights(request)
    access.require_see(rights)
    invoice = _invoice(pk)
    extra = 1 if request.GET.get("new") and access.may_change(rights) else 0
    if request.method == "POST":
        access.require_change(rights)
        head = HeadForm(request.POST, instance=invoice)
        formset = position_formset(invoice, request.POST)
        if head.is_valid() and formset.is_valid():
            try:
                _save(invoice.pk, head, formset)
            except ValidationError as error:
                add_validation_error(head, error)
            else:
                messages.success(request, _("The invoice was saved."))
                if request.POST.get("action") == "add":
                    return redirect(f"{reverse('incoming:detail', args=[pk])}?new=1#new-position")
                return redirect("incoming:detail", pk=pk)
        return render(request, "incoming/detail.html", _detail_context(request, _invoice(pk), head, formset))
    head = HeadForm(instance=invoice)
    formset = position_formset(invoice, extra=extra)
    return render(
        request, "incoming/detail.html", _detail_context(request, invoice, head, formset, new_row=bool(extra))
    )


def _typed_value(form: Any, name: str) -> Any:
    """The value of a field as typed, or ``None`` while it cannot be read (a disabled field keeps its initial value)."""
    field = form.fields[name]
    if field.disabled:
        return form.get_initial_for_field(field, name)
    raw = field.widget.value_from_datadict(form.data, form.files, form.add_prefix(name))
    try:
        return field.clean(raw)
    except ValidationError:
        return None


@module_required(Module.MATERIAL)
@require_POST
def kontierung_sum(request: HttpRequest, pk: int) -> HttpResponse:
    """The sum of the Kontierungen as typed – asked by the page while typing; nothing is saved."""
    access.require_see(request_rights(request))
    invoice = _invoice(pk)
    formset = position_formset(invoice, request.POST)
    total_net = invoice.total_net
    if "total_net" in request.POST and "total_net" not in services.spread_lock(invoice).head:
        try:
            total_net = HeadForm.fields_total_net().clean(request.POST["total_net"])
        except ValidationError:
            total_net = None
    lines = []
    for form in formset.forms:
        if form.data.get(form.add_prefix("DELETE")):
            continue
        lines.append((_typed_value(form, "amount_net"), _typed_value(form, "tax_rate")))
    return render(request, "incoming/_kontierung_sum.html", {"sum": services.kontierung_sum(lines, total_net)})


@transaction.atomic
def _save(pk: int, head: HeadForm, formset: Any) -> None:
    """Save the head and the positions of the sent form through the services (one logic for page and API)."""
    invoice = IncomingInvoice.objects.get(pk=pk)
    services.update_head(invoice, head.values())
    for form in formset.forms:
        position_pk = form.instance.pk
        if position_pk and form.cleaned_data.get("DELETE"):
            services.delete_position(InvoicePosition.objects.get(pk=position_pk))
        elif position_pk:
            if form.has_changed():
                services.update_position(InvoicePosition.objects.get(pk=position_pk), form.values())
        elif form.has_changed():
            services.add_position(invoice, form.values())


@module_required(Module.MATERIAL)
def invoice_file(request: HttpRequest, pk: int) -> HttpResponse:
    """The original file: a PDF or a picture shown in the browser, everything else downloaded (NFA-007)."""
    access.require_see(request_rights(request))
    invoice = _invoice(pk)
    return document_response(invoice.file.name, invoice.original_name)


@module_required(Module.MATERIAL)
def invoice_xml(request: HttpRequest, pk: int) -> HttpResponse:
    """The XML of an e-invoice (the uploaded file, or the one attached to the PDF) as a download."""
    access.require_see(request_rights(request))
    return services.xml_response(_invoice(pk))


@module_required(Module.MATERIAL)
def invoice_reading(request: HttpRequest, pk: int) -> HttpResponse:
    """How far reading the invoice got – asked every two seconds by the page; when done the page is loaded anew."""
    access.require_see(request_rights(request))
    invoice = _invoice(pk)
    job = invoice.reading_job
    finished = invoice.reading_state != ReadingState.RUNNING or job is None or job.is_finished
    response = render(request, "incoming/_reading.html", {"invoice": invoice, "job": job, "finished": finished})
    if finished and request.headers.get("HX-Request"):
        response["HX-Refresh"] = "true"
    return response


@module_required(Module.MATERIAL, Level.WRITE)
@require_POST
def invoice_read(request: HttpRequest, pk: int) -> HttpResponse:
    """Read the file again: the empty fields of the head are filled, the positions not booked in and not touched replaced."""
    access.require_change(request_rights(request))
    invoice = _invoice(pk)
    try:
        services.start_reading(invoice, user=request.user)
    except ValidationError as error:
        # A value of the reading that cannot be kept is a message, not an error page.
        messages.error(request, " ".join(error.messages))
        return redirect("incoming:detail", pk=pk)
    invoice.refresh_from_db()
    _tell_reading(request, invoice)
    return redirect("incoming:detail", pk=pk)


@module_required(Module.MATERIAL, Level.WRITE)
@require_POST
def invoice_create_supplier(request: HttpRequest, pk: int) -> HttpResponse:
    """Create the supplier named on the invoice in the master data and link it."""
    access.require_change(request_rights(request))
    invoice = _invoice(pk)
    try:
        supplier = services.create_supplier(invoice)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, _("The supplier “%(name)s” is in the master data.") % {"name": supplier.name})
    return redirect("incoming:detail", pk=pk)


@module_required(Module.MATERIAL, Level.WRITE)
@require_POST
def invoice_status(request: HttpRequest, pk: int) -> HttpResponse:
    """Set the status: open, checked or booked in."""
    access.require_change(request_rights(request))
    invoice = _invoice(pk)
    try:
        services.set_status(invoice, request.POST.get("status", ""))
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, _("The status is now “%(status)s”.") % {"status": invoice.get_status_display()})
    return redirect("incoming:detail", pk=pk)


@module_required(Module.MATERIAL, Level.DELETE)
@require_POST
def invoice_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete an invoice that nothing was booked in from."""
    access.require_change(request_rights(request))
    if not access.may_delete(request_rights(request)):
        raise PermissionDenied
    invoice = _invoice(pk)
    try:
        services.delete_invoice(invoice)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect("incoming:detail", pk=pk)
    messages.success(request, _("The invoice was deleted."))
    return redirect("incoming:list")


@module_required(Module.MATERIAL)
def invoice_costing(request: HttpRequest, pk: int) -> HttpResponse:
    """The ancillary costs spread by the key asked for (``allocation_key``) – a preview, nothing is saved."""
    access.require_see(request_rights(request))
    invoice = _invoice(pk)
    key = request.GET.get("allocation_key") or request.GET.get("key")
    return render(
        request,
        "incoming/_costing.html",
        {"invoice": invoice, "costing": costing.costing_of(invoice, key=key), "booked": _booked_info(invoice)},
    )


# --- Booking in ------------------------------------------------------------------------------------------------


def _initial_rows(invoice: IncomingInvoice, positions: list[InvoicePosition]) -> list[dict[str, Any]]:
    """The rows of the booking page: what the invoice knows about each goods position."""
    counts = services.booked_counts(invoice)
    default_location = StorageLocation.get_default()
    rows = []
    for position in positions:
        done = counts.get(position.pk, {}).get("pieces", 0)
        pieces = int(position.quantity) if position.quantity == int(position.quantity) else 0
        left = max(pieces - done, 0)
        suggestion = position.suggestion or {}
        model = position.material_model
        product_id = suggestion.get("product_id")
        product = Product.objects.filter(pk=product_id).first() if product_id else None
        rows.append(
            {
                "position": position.pk,
                "include": left > 0,
                "model_name": model.name if model is not None else position.description[:200],
                "category": str(suggestion["category_id"]) if suggestion.get("category_id") else "",
                "manufacturer_name": position.manufacturer,
                "product_text": purchases.product_label(product) if product is not None else "",
                "count": left or pieces or 1,
                "serial_numbers": position.serial_numbers,
                "storage_location": default_location.pk if default_location is not None else "",
                "article_number": position.article_number,
                "asset_kind": position.asset_kind,
                "useful_life_months": position.useful_life_months,
            }
        )
    return rows


def _book_context(
    request: HttpRequest, invoice: IncomingInvoice, formset: Any, positions: list[Any], **extra: Any
) -> dict[str, Any]:
    """What the booking page shows: the rows with their position and cost, the plan."""
    cost = costing.costing_of(invoice)
    counts = services.booked_counts(invoice)
    by_pk = {position.pk: position for position in positions}
    shown = []
    for form in formset.forms:
        raw = form["position"].value()
        position = by_pk.get(int(raw)) if str(raw or "").isdigit() else None
        shown.append(
            {
                "form": form,
                "position": position,
                "cost": cost.row_of(position) if position is not None else None,
                "booked": counts.get(position.pk if position else 0),
                "hints": (position.suggestion or {}).get("hints", []) if position is not None else [],
            }
        )
    return {
        **_tabs(request_rights(request)),
        "invoice": invoice,
        "formset": formset,
        "rows": shown,
        "costing": cost,
        **extra,
    }


def _persist_asset_choices(entries_forms: list[tuple[Any, Any]]) -> None:
    """Keep the kind of asset and the useful life chosen on the booking page with the positions."""
    for form, position in entries_forms:
        values = {
            "asset_kind": form.cleaned_data.get("asset_kind") or "",
            "useful_life_months": form.cleaned_data.get("useful_life_months"),
        }
        if position.asset_kind != values["asset_kind"] or position.useful_life_months != values["useful_life_months"]:
            services.update_position(position, values)


@module_required(Module.MATERIAL, Level.WRITE)
def invoice_book(request: HttpRequest, pk: int) -> HttpResponse:
    """Book in the goods positions as items or quantities: choose, look at the preview, confirm."""
    rights = request_rights(request)
    access.require_change(rights)
    invoice = _invoice(pk)
    positions = [position for position in invoice.positions.select_related("material_model") if position.is_goods]
    if request.method != "POST":
        formset = booking_formset(rights=rights, rows=_initial_rows(invoice, positions))
        return render(request, "incoming/book.html", _book_context(request, invoice, formset, positions, plan=None))
    formset = booking_formset(request.POST, rights=rights)
    by_pk = {position.pk: position for position in positions}
    if not formset.is_valid():
        return render(request, "incoming/book.html", _book_context(request, invoice, formset, positions, plan=None))
    entries = []
    chosen = []
    for form in formset.forms:
        position = by_pk.get(form.cleaned_data.get("position") or 0)
        if position is None or not form.cleaned_data.get("include"):
            continue
        chosen.append((form, position))
        entries.append(form.entry(position))
    _persist_asset_choices(chosen)
    invoice = _invoice(pk)
    result = booking.plan(invoice, entries, rights=rights)
    if request.POST.get("action") == "book" and request.POST.get("confirmed") and result.ok:
        try:
            made = booking.book(invoice, entries, rights=rights, user=request.user)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(
                request,
                _("Booked in: %(count)d items or pieces were made (%(ids)s).")
                % {"count": len(made.items), "ids": made.ids},
            )
            for warning in made.warnings:
                messages.warning(request, warning)
            return redirect("incoming:detail", pk=pk)
    elif request.POST.get("action") == "book" and not request.POST.get("confirmed"):
        messages.warning(request, _("Look at the preview and tick “Yes, book in exactly this” to book in."))
    return render(request, "incoming/book.html", _book_context(request, invoice, formset, positions, plan=result))


# --- Settings --------------------------------------------------------------------------------------------------


@module_required(Module.ADMINISTRATION)
def settings_page(request: HttpRequest) -> HttpResponse:
    """Einstellungen → Eingangsrechnungen: the limit of a low-value asset and the standard useful life.

    Read for who may read the settings, changed with write access to them.
    """
    from rentalars.material.asset_models import AssetSettings

    can_write = request_rights(request).can_write(Module.ADMINISTRATION)
    form = SettingsForm(request.POST or None, instance=AssetSettings.load())
    if request.method == "POST":
        if not can_write:
            raise PermissionDenied
        if form.is_valid():
            form.save()
            messages.success(request, _("Settings saved."))
            return redirect("incoming:settings")
    return render(request, "incoming/settings.html", {"form": form, "can_write": can_write})
