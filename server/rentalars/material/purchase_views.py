# SPDX-License-Identifier: GPL-3.0-or-later
"""The page "Kauf einpflegen" (MAT-061; MAT-019, MAT-050).

One form: the head (supplier, invoice number and date, net or gross, start
ID, the invoice) and the positions. Its buttons:

* "Create items" (``action=save``) – checks everything and creates all
  items in one step (:func:`rentalars.material.purchases.create_purchase`),
  then shows what was created, with the labels to print;
* "Another position" (``more``) – the same page with one empty row more
  (MAT-075; three before); the page script adds the row at once instead;
* "Read the invoice" (``read``) – keeps the uploaded invoice and reads it:
  with AI in the background (the page asks every two seconds how far it
  got), without AI number, date and supplier from the text at once;
* "Fill in the AI proposal" (``apply``; MAT-075) – what the AI found goes into the empty fields of the head and
  into new rows, each to be checked; nothing is saved;
* "Remove the invoice" (``drop``).

Every button but "Create items" shows the page again with what was typed,
without complaining about what is not finished yet. Nothing is created
before "Create items".

MAT-075: below the positions the sum of what was typed, net
and gross, and the total of the read invoice with the difference
(:func:`rentalars.material.purchase_forms.purchase_sums`) – rendered on every
step, kept up to date by the page script while typing.

For who may write material; prices only with the right to see purchase
prices (AUT-019); the AI only if the settings switch it on (ADM-017).
"""

from __future__ import annotations

import re
from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Level, Module, SpecialRight, module_required, request_rights, require
from rentalars.core.forms import add_validation_error
from rentalars.core.models import BackgroundJob
from rentalars.material import purchases, serials
from rentalars.material.forms import PRICE_ENTRY_SESSION_KEY
from rentalars.material.models import MaterialFile, MaterialFileKind, MaterialItem, MaterialModel
from rentalars.material.numbering import parse_inventory_number
from rentalars.material.purchase_forms import (
    EMPTY_ROWS,
    PurchaseHeadForm,
    is_empty_row,
    position_formset,
    purchase_sums,
    rows_from_proposal,
    rows_of,
)

#: The kind of the background task that reads an invoice (``rentalars.ai.invoices``).
READING_JOB = "ai_invoice"
#: The fields of the head that are carried over when the page is shown again.
HEAD_FIELDS = (
    "supplier_name",
    "invoice_number",
    "purchase_date",
    "prices",
    "price_tax_rate",
    "inventory_number",
    "purchase_note",
    "invoice_total_net",
    "invoice_total_gross",
)


def _ai_switched_on() -> bool:
    from rentalars.ai.invoices import is_available

    return is_available()


def _invoice_of(request: HttpRequest) -> tuple[purchases.PendingInvoice | None, str]:
    """The invoice of the purchase: a file sent now – kept for the next steps –, else the one kept before.

    Returns:
        The kept invoice or ``None``, and a text if the file was refused or is gone.
    """
    earlier = None
    token = request.POST.get("upload", "")
    if token:
        try:
            earlier = purchases.pending_invoice(token, user=request.user)
        except ValidationError as error:
            if "invoice" not in request.FILES:
                return None, " ".join(error.messages)
    uploaded = request.FILES.get("invoice")
    if uploaded is None:
        return earlier, ""
    try:
        kept = purchases.keep_invoice(uploaded, user=request.user)
    except ValidationError as error:
        return earlier, " ".join(error.messages)
    if earlier is not None:
        purchases.discard_invoice(earlier)  # replaced by the new file
    return kept, ""


def _render(
    request: HttpRequest,
    head: PurchaseHeadForm,
    formset: Any,
    *,
    invoice: purchases.PendingInvoice | None,
    job: BackgroundJob | None = None,
    serial_warnings: list[str] | None = None,
) -> HttpResponse:
    rights = request_rights(request)
    return render(
        request,
        "material/purchase.html",
        {
            "serial_warnings": serial_warnings or [],  # Confirmed with "Create anyway"
            "serial_token": serials.token_of(serial_warnings or []),
            "form": head,
            "formset": formset,
            "invoice": invoice,
            "job": job,
            "ai_on": _ai_switched_on(),
            "with_prices": rights.has(SpecialRight.PURCHASE_PRICES),
            "sums": purchase_sums(head, formset),  # MAT-075
        },
    )


@module_required(Module.MATERIAL, Level.WRITE)
def purchase_page(request: HttpRequest) -> HttpResponse:
    """Kauf einpflegen: head and positions, filled from the invoice if wished; see the module text."""
    rights = request_rights(request)
    remembered = request.session.get(PRICE_ENTRY_SESSION_KEY)
    if request.method != "POST":
        rows: list[dict[str, Any]] = [{} for _row in range(EMPTY_ROWS)]
        model_id = request.GET.get("model", "")
        model = MaterialModel.objects.filter(pk=int(model_id)).first() if model_id.isdigit() else None
        if model is not None:
            rows[0] = {"model_name": model.name}  # from the page of a model: it stands in the first row
        return _render(
            request,
            PurchaseHeadForm(rights=rights, remembered=remembered),
            position_formset(rights=rights, rows=rows),
            invoice=None,
        )
    action = request.POST.get("action", "save")
    invoice, invoice_problem = _invoice_of(request)
    if action == "save":
        return _save(request, invoice, invoice_problem)

    # Every other button: the page again with what was typed, unchecked.
    head_values = {name: request.POST.get(name, "") for name in HEAD_FIELDS}
    rows = rows_of(position_formset(request.POST, rights=rights))
    job = None
    if invoice_problem:
        messages.error(request, invoice_problem)
    if action == "more":
        rows += [{} for _row in range(EMPTY_ROWS)]
    elif action == "drop" and invoice is not None:
        purchases.discard_invoice(invoice)
        invoice = None
        head_values["invoice_total_net"] = head_values["invoice_total_gross"] = ""  # MAT-075: totals go with it
    elif action == "read":
        job = _read(request, invoice, head_values, rows)
    elif action == "apply":
        job = BackgroundJob.objects.filter(
            pk=int(request.POST["job"]) if request.POST.get("job", "").isdigit() else 0,
            kind=READING_JOB,
            created_by=request.user,
        ).first()
        if job is not None and job.is_finished:
            _apply_job(request, job, head_values, rows)
            job = None
    head = PurchaseHeadForm(initial=head_values, rights=rights, remembered=remembered)
    formset = position_formset(rights=rights, rows=rows or [{} for _row in range(EMPTY_ROWS)])
    return _render(request, head, formset, invoice=invoice, job=job)


def _save(request: HttpRequest, invoice: purchases.PendingInvoice | None, invoice_problem: str) -> HttpResponse:
    """Check the whole form and create the items; on success show what was created."""
    from rentalars.material.views import remember_price_entry

    rights = request_rights(request)
    head = PurchaseHeadForm(request.POST, rights=rights, remembered=request.session.get(PRICE_ENTRY_SESSION_KEY))
    formset = position_formset(request.POST, rights=rights)
    head_valid = head.is_valid()
    if invoice_problem:
        head.add_error("invoice", invoice_problem)
    serial_warnings: list[str] = []
    if head_valid and formset.is_valid() and not invoice_problem:
        # Duplicate serial numbers: a number that exists already, or is given twice, is confirmed first.
        serial_warnings = purchases.serial_warnings(formset.positions())
        if serials.confirmed(request.POST, serial_warnings):
            serial_warnings = []
    if head_valid and formset.is_valid() and not invoice_problem and not serial_warnings:
        try:
            purchase = purchases.create_purchase(
                head.head(), formset.positions(), rights=rights, user=request.user, invoice=invoice
            )
        except ValidationError as error:
            add_validation_error(head, error)
        else:
            remember_price_entry(request, head)
            messages.success(
                request,
                _("Purchase entered: %(count)d items created.") % {"count": len(purchase.items)},
            )
            return redirect(f"{reverse('material:purchase_done')}?items={purchase.id_list}")
    return _render(request, head, formset, invoice=invoice, serial_warnings=serial_warnings)


def _read(
    request: HttpRequest,
    invoice: purchases.PendingInvoice | None,
    head_values: dict[str, Any],
    rows: list[dict[str, Any]],
) -> BackgroundJob | None:
    """Read the invoice: with AI start the task (its result is filled in when it is done), else read the head now."""
    if invoice is None:
        messages.error(request, _("Choose the invoice first."))
        return None
    if not invoice.is_pdf:
        messages.warning(request, _("Only PDF files with text can be read. The file is attached all the same."))
        return None
    if _ai_switched_on():
        from rentalars.ai.client import AIError
        from rentalars.ai.invoices import start

        try:
            job = start(invoice, user=request.user)
        except AIError as error:
            messages.warning(request, str(error))
        else:
            if not job.is_finished:
                return job
            _apply_job(request, job, head_values, rows)
            return None
    try:
        text = purchases.invoice_text(invoice.path)
    except purchases.InvoiceTextError as error:
        messages.error(request, str(error))
        return None
    _apply(request, purchases.proposal_from_text(text), head_values, rows)
    return None


def _apply_job(
    request: HttpRequest, job: BackgroundJob, head_values: dict[str, Any], rows: list[dict[str, Any]]
) -> None:
    """Fill in what the reading task found; say what went wrong, if anything."""
    result = job.result or {}
    if job.status != "done":
        messages.error(request, job.message or _("The invoice could not be read."))
        return
    if result.get("error"):
        messages.warning(request, result["error"])
    if result.get("proposal"):
        _apply(request, result["proposal"], head_values, rows)


def _apply(
    request: HttpRequest, proposal: dict[str, Any], head_values: dict[str, Any], rows: list[dict[str, Any]]
) -> None:
    """Put a proposal into the page: empty fields of the head, the positions as new rows to be checked.

    What was typed already stays; rows that are still empty make room for
    the positions of the invoice.
    """
    rights = request_rights(request)
    if proposal.get("note"):
        # Review (MAT-062): e.g. only the first pages of a long PDF were read.
        messages.warning(request, proposal["note"])
    if rights.has(SpecialRight.PURCHASE_PRICES):
        # MAT-075: the totals belong to the invoice just read – those of an earlier one go.
        head_values["invoice_total_net"] = proposal.get("total_net") or ""
        head_values["invoice_total_gross"] = proposal.get("total_gross") or ""
    filled = []
    supplier = proposal.get("supplier") or {}
    if supplier.get("name") and not str(head_values.get("supplier_name") or "").strip():
        head_values["supplier_name"] = supplier["name"]
        filled.append(_("supplier"))
        if not supplier.get("existing"):
            messages.info(
                request,
                _("The supplier “%(name)s” is not known yet: it is created when you save.")
                % {"name": supplier["name"]},
            )
    if proposal.get("invoice_number") and not str(head_values.get("invoice_number") or "").strip():
        head_values["invoice_number"] = proposal["invoice_number"]
        filled.append(_("invoice number"))
    if proposal.get("invoice_date") and not str(head_values.get("purchase_date") or "").strip():
        head_values["purchase_date"] = proposal["invoice_date"]
        filled.append(_("invoice date"))
    new_rows = rows_from_proposal(proposal, rights=rights)
    if new_rows:
        if rights.has(SpecialRight.PURCHASE_PRICES) and any(row.get("unit_price") for row in new_rows):
            head_values["prices"] = proposal.get("prices") or "net"
            if proposal.get("tax_rate"):
                head_values["price_tax_rate"] = proposal["tax_rate"]
        kept = [row for row in rows if not is_empty_row(row)]
        rows[:] = [*kept, *new_rows]
    if filled or new_rows:
        parts = list(filled)
        if new_rows:
            parts.append(_("%(count)d positions") % {"count": len(new_rows)})
        messages.success(
            request,
            _("Filled in from the invoice: %(parts)s. Check every value; tick each row from the invoice as checked.")
            % {"parts": ", ".join(parts)},
        )
    else:
        messages.warning(request, _("Nothing was found in the invoice that could be filled in."))


@module_required(Module.MATERIAL, Level.WRITE)
def purchase_reading(request: HttpRequest, job_pk: int) -> HttpResponse:
    """How far reading the invoice got – asked every two seconds by the page, for whoever started it."""
    job = get_object_or_404(BackgroundJob, pk=job_pk, kind=READING_JOB, created_by=request.user)
    return render(request, "material/_purchase_reading.html", {"job": job})


def _numbers(text: str) -> list[int]:
    """IDs as the summary link names them: ``0042-0047,0050``; at most the items of one step."""
    from rentalars.material.services import MAX_ITEMS_PER_BATCH

    numbers: list[int] = []
    for part in re.split(r"[\s,;]+", text.strip()):
        if not part:
            continue
        try:
            if "-" in part.strip("-"):
                first, last = (parse_inventory_number(value) for value in part.split("-", 1))
                numbers.extend(
                    range(min(first, last), min(max(first, last), min(first, last) + MAX_ITEMS_PER_BATCH) + 1)
                )
            else:
                numbers.append(parse_inventory_number(part))
        except ValidationError:
            continue
        if len(numbers) >= MAX_ITEMS_PER_BATCH:
            break
    return numbers[:MAX_ITEMS_PER_BATCH]


@module_required(Module.MATERIAL)
def purchase_done(request: HttpRequest) -> HttpResponse:
    """What a purchase created: the items with links, and the labels to print for them."""
    text = request.GET.get("items", "")
    items = list(
        MaterialItem.objects.filter(inventory_number__in=_numbers(text))
        .select_related("material_model", "supplier", "storage_location", "purchase_price_in")
        .order_by("inventory_number")
    )
    first = items[0] if items else None
    from rentalars.incoming import access as incoming_access
    from rentalars.incoming import services as incoming_services

    return render(
        request,
        "material/purchase_done.html",
        {
            "may_record_invoice": incoming_access.may_change(request_rights(request))
            and incoming_services.can_record_purchase(items),
            "items": items,
            "ids": purchases.compact_ids([item.inventory_number for item in items]),
            "first": first,
            "with_prices": request_rights(request).has(SpecialRight.PURCHASE_PRICES),
            "invoice_count": MaterialFile.objects.filter(item__in=items, kind=MaterialFileKind.INVOICE)
            .values("item")
            .distinct()
            .count(),
        },
    )


def purchase_model_suggest(request: HttpRequest) -> JsonResponse:
    """Suggestions for the model of a position: every model by name, short name or manufacturer; a new name last."""
    rights = request_rights(request)
    require(rights.can_read(Module.MATERIAL))
    text = request.GET.get("q", "").strip()
    models = MaterialModel.objects.select_related("category", "manufacturer")
    if text:
        models = models.filter(
            Q(name__icontains=text) | Q(short_name__icontains=text) | Q(manufacturer__name__icontains=text)
        )
    results: list[dict[str, Any]] = [
        {"id": model.name, "label": model.name, "hint": model.category.name} for model in models.order_by("name")[:12]
    ]
    if text and rights.can_write(Module.MATERIAL) and not MaterialModel.objects.filter(name__iexact=text).exists():
        results.append({"id": text, "label": text, "hint": _("new model"), "create": True})
    return JsonResponse(results, safe=False)
