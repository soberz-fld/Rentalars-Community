# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser pages of the depreciation and the used sale from stock ("Mit Restbuchwert"; MAT-086).

* The card "Anlagevermögen" on the page of an item (:func:`asset_context`, :func:`item_asset_edit`): kind, useful life,
  acquisition cost, depreciation, book value, the schedule per year – and recording an old item as an asset.
* ``accounting/assets/`` – Buchhaltung → Anlagenspiegel / Restbuchwerte: every asset with its book value on a day, filters,
  sums, CSV. There is no DATEV export for it (decided).
* ``material/items/<id>/sell/`` – "Gebrauchtverkauf aus Bestand": preview with book value and gain or loss, then the
  explicit sale.
* ``accounting/assets/sales/`` and ``…/<id>/`` – Verkäufe aus Bestand: the list with the gain or loss per year, one sale
  with its reversal (Storno) and the button "Rechnung dazu erstellen".

Rights: purchase prices and read access to the material to look; write access to the material to record, sell and reverse
(``rentalars.incoming.access`` – the same as the register of incoming invoices, whose costs these are).
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, module_required, request_rights
from rentalars.core.forms import add_validation_error
from rentalars.core.listing import paginate
from rentalars.documents import outgoing
from rentalars.incoming import access
from rentalars.masterdata.models import StorageLocation, remember_location_paths
from rentalars.material import book_values, depreciation, sales
from rentalars.material.asset_forms import AssetDataForm, SaleForm
from rentalars.material.asset_tables import ASSET_TABLE, SALES_TABLE
from rentalars.material.models import MaterialItem, MaterialModel
from rentalars.material.sale_models import SaleFromStock


def _tabs(rights: Any, tab: str) -> dict[str, Any]:
    """The tabs of Buchhaltung and the one of this page."""
    return {**outgoing.tabs(rights), "tab": tab}


# --- The card on the page of an item --------------------------------------------------------------------------------


def asset_context(request: HttpRequest, item: MaterialItem) -> dict[str, Any]:
    """What the card "Anlagevermögen" of an item page shows; nothing without the right to see purchase prices.

    The valuation is of today; the card also offers the form to record the item as an asset and, for an item that is in
    the stock, the way to sell it.
    """
    rights = request_rights(request)
    if not access.may_see(rights):
        return {}
    valued = book_values.value_of(item)
    may_change = access.may_change(rights)
    return {
        "asset": valued,
        "asset_state": book_values.state_label(valued),
        "asset_cost": book_values.cost_of(item),
        "asset_form": AssetDataForm(item=item) if may_change else None,
        "asset_may_change": may_change,
        "asset_may_sell": may_change and not item.is_archived,
        "asset_sales": item.stock_sales.select_related("customer").order_by("-sold_on", "-id")[:5],
    }


@module_required(Module.MATERIAL, Level.WRITE)
@require_POST
def item_asset_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """Record an item as merchandise, low-value or fixed asset, or correct its asset data."""
    access.require_change(request_rights(request))
    item = get_object_or_404(MaterialItem, pk=pk)
    form = AssetDataForm(request.POST, item=item)
    if form.is_valid():
        data = form.cleaned_data
        try:
            book_values.set_asset_data(
                item,
                kind=data["asset_kind"],
                useful_life_months=data["useful_life_months"],
                ancillary_cost_net=data["ancillary_cost_net"],
                acquisition_cost_net=data["acquisition_cost_net"],
            )
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, _("The asset data of %(id)s were saved.") % {"id": item.display_id})
    else:
        for errors in form.errors.values():
            messages.error(request, " ".join(errors))
    return redirect(f"{reverse('material:item_detail', args=[item.pk])}#asset")


# --- The Anlagenspiegel ---------------------------------------------------------------------------------------------


def _years() -> list[int]:
    """The years of the choice "balance-sheet date": those of purchases and this one, newest first."""
    years = {
        day.year
        for day in MaterialItem.objects.exclude(asset_kind="")
        .exclude(purchase_date=None)
        .values_list("purchase_date", flat=True)
    }
    years.add(timezone.localdate().year)
    return sorted(years, reverse=True)


@module_required(Module.MATERIAL)
def asset_register(request: HttpRequest) -> HttpResponse:
    """Buchhaltung → Anlagenspiegel / Restbuchwerte: the assets with their book value on a day – or as CSV.

    Filters: kind, storage location, model, search, the day (``as_of``) or a balance-sheet year, "also what left the
    stock". The sums cover the whole selection, not one page. There is no DATEV export.
    """
    rights = request_rights(request)
    access.require_see(rights)
    found = book_values.parse(request.GET)
    rows, summary = book_values.register(found)
    # (MAT-086) The paths of all storage locations from one query, not one per row and level.
    remember_location_paths(row.item.effective_storage_location for row in rows)
    table = ASSET_TABLE.state(request)
    ordered = table.order(rows)
    if table.wants_csv:
        return table.csv_response(ordered, _("Asset register"))
    page = paginate(request, ordered)
    day = found.day
    models = MaterialModel.objects.filter(
        pk__in=MaterialItem.objects.exclude(asset_kind="").values("material_model")
    ).order_by("name")
    return render(
        request,
        "material/asset_register.html",
        {
            **_tabs(rights, "assets"),
            "page": page,
            "table": table,
            "rows": table.rows(page),
            "filters": found,
            "day": day,
            "year": day.year,
            "summary": summary,
            "kind_sums": [
                (kind, label, summary.by_kind[kind])
                for kind, label in (
                    (depreciation.KIND_FIXED_ASSET, _("Fixed assets")),
                    (depreciation.KIND_LOW_VALUE, _("Low-value assets (GWG)")),
                    (depreciation.KIND_MERCHANDISE, _("Merchandise")),
                )
                if kind in summary.by_kind
            ],
            "kind_choices": book_values.KIND_CHOICES,
            "locations": remember_location_paths(StorageLocation.objects.filter(is_active=True)),
            "models": models,
            "years": _years(),
            "memory": book_values.memory_value_on(),
            "may_sell": access.may_change(rights),
        },
    )


# --- Selling an item ------------------------------------------------------------------------------------------------


@module_required(Module.MATERIAL, Level.WRITE)
def item_sell(request: HttpRequest, pk: int) -> HttpResponse:
    """Sell from stock ("Gebrauchtverkauf aus Bestand"): day, buyer, price, a preview with book value and gain or loss, the sale.

    One form with two buttons: "Preview" shows what the sale would be, "Sell" does it. Whatever stops the sale (an
    allocation to a project, a status, something installed in the item) is shown instead of the button; what should
    give pause (the item is wished for by a project) needs a tick.
    """
    rights = request_rights(request)
    access.require_change(rights)
    item = get_object_or_404(
        MaterialItem.objects.select_related("material_model__category", "installed_in", "storage_location"), pk=pk
    )
    form = SaleForm(request.POST or None, item=item, rights=rights)
    plan = None
    if request.method == "POST" and form.is_valid():
        values = form.values()
        plan = sales.preview(item, **values)
        if request.POST.get("step") == "sell" and plan.ok:
            try:
                sale = sales.sell(
                    item,
                    **values,
                    **form.buyer(),
                    note=form.cleaned_data["note"],
                    user=request.user,
                    accept_warnings=form.cleaned_data["accept_warnings"],
                )
            except ValidationError as error:
                add_validation_error(form, error)
            else:
                messages.success(request, _("%(id)s was sold.") % {"id": item.display_id})
                return redirect("material:sale_detail", pk=sale.pk)
    blocked = sales.problems_of(item, 1 if not item.material_model.is_bulk else item.quantity, None)
    return render(
        request,
        "material/sale_form.html",
        {
            "item": item,
            "tab": "item",
            "form": form,
            "plan": plan,
            "blocked": blocked if request.method == "GET" else [],
            "valued": book_values.value_of(item),
        },
    )


# --- The sales ------------------------------------------------------------------------------------------------------


@module_required(Module.MATERIAL)
def sales_list(request: HttpRequest) -> HttpResponse:
    """Buchhaltung → Verkäufe aus Bestand: every sale with its gain or loss, the sums per year – or as CSV."""
    rights = request_rights(request)
    access.require_see(rights)
    found = sales.parse_filters(request.GET)
    filtered = found.apply(sales.sales())
    table = SALES_TABLE.state(request)
    ordered = table.order(filtered)
    if table.wants_csv:
        return table.csv_response(ordered, _("Sales from stock"))
    page = paginate(request, ordered)
    return render(
        request,
        "material/sales.html",
        {
            **_tabs(rights, "sales"),
            "page": page,
            "table": table,
            "rows": table.rows(page),
            "filters": found,
            "years": sales.years_with_sales(),
            "by_year": sales.sums_by_year(found.apply(sales.sales())),
        },
    )


def _sale(pk: int) -> SaleFromStock:
    """A sale with what its page shows, or 404."""
    return get_object_or_404(sales.sales().select_related("item__material_model__category", "contact"), pk=pk)


@module_required(Module.MATERIAL)
def sale_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """One sale: facts, the book value and the gain or loss, the reversal, the way to an invoice."""
    from rentalars.documents import free

    rights = request_rights(request)
    access.require_see(rights)
    sale = _sale(pk)
    return render(
        request,
        "material/sale_detail.html",
        {
            **_tabs(rights, "sales"),
            "sale": sale,
            "buyer": sales.buyer_label(sale),
            "may_change": access.may_change(rights),
            "may_invoice": free.may_change(rights) and sale.customer_id is not None and not sale.is_cancelled,
            "basis_unknown": sale.book_value_basis == "unknown",
            "invoice": sales.invoice_of(sale),  # The invoice or the draft of it is shown at the sale
            "invoice_draft": sales.open_invoice_draft(sale),
        },
    )


@module_required(Module.MATERIAL, Level.WRITE)
@require_POST
def sale_cancel(request: HttpRequest, pk: int) -> HttpResponse:
    """Reverse a sale (Storno) with a reason; the item is in the stock again."""
    access.require_change(request_rights(request))
    sale = _sale(pk)
    try:
        sales.cancel(sale, reason=request.POST.get("reason", ""), user=request.user)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(
            request, _("The sale was reversed: %(id)s is in the stock again.") % {"id": sale.item.display_id}
        )
    return redirect("material:sale_detail", pk=sale.pk)


@module_required(Module.MATERIAL, Level.WRITE)
@require_POST
def sale_invoice(request: HttpRequest, pk: int) -> HttpResponse:
    """Make a draft of an invoice for the buyer with the sale as its line ("Rechnung dazu erstellen"), then open it."""
    from rentalars.documents import free

    rights = request_rights(request)
    access.require_change(rights)
    if not free.may_change(rights):
        raise PermissionDenied
    sale = _sale(pk)
    try:
        draft = sales.invoice_draft(sale, user=request.user)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect("material:sale_detail", pk=sale.pk)
    messages.success(request, _("The draft of the invoice is made. Check it, then issue it."))
    return redirect("documents:free_edit", pk=draft.pk)
