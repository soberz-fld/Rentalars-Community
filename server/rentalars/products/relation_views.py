# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views to manage the accessories and replacements of a product (PRD-023, VFG-015).

The panel on the page of a product (and the read-only panel on the page of a material model) list them; these
views add, change, move and remove one. All of them call :mod:`rentalars.products.suggestions` – the API calls the
same functions (API-002). They answer with a redirect back to the panel.
"""

from __future__ import annotations

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, module_required
from rentalars.core.forms import StyledForm
from rentalars.products import suggestions
from rentalars.products.models import Product
from rentalars.products.relation_models import ProductRelation, RelationKind


class RelationForm(StyledForm):
    """Name an accessory or replacement of a product."""

    # (R3-5) All products: changing the note of an entry must not fail because its product was
    # deactivated since. Only naming a *new* one is limited to active products (``relation_add``).
    related_product = forms.ModelChoiceField(label=_("Product"), queryset=Product.objects.all())
    kind = forms.ChoiceField(label=_("Kind"), choices=RelationKind.choices)
    quantity_per_piece = forms.DecimalField(
        label=_("Pieces per piece"), min_value=0.01, max_digits=7, decimal_places=2, initial=1, localize=True
    )
    note = forms.CharField(label=_("Note"), max_length=250, required=False)
    is_required = forms.BooleanField(label=_("Required"), required=False)
    both_ways = forms.BooleanField(label=_("Also the other way round"), required=False)


def _redirect(product: Product) -> HttpResponse:
    response = redirect("products:detail", pk=product.pk)
    response["Location"] += "#relations"
    return response


@require_POST
@module_required(Module.PRODUCTS, Level.WRITE)
def relation_add(request: HttpRequest, pk: int) -> HttpResponse:
    """Name an accessory or replacement at the end of the list."""
    product = get_object_or_404(Product, pk=pk)
    form = RelationForm(request.POST)
    form.fields["related_product"].queryset = Product.objects.filter(is_active=True)
    if not form.is_valid():
        messages.error(request, _("Choose a product from the list and a kind."))
        return _redirect(product)
    data = form.cleaned_data
    try:
        suggestions.add_relation(
            product,
            data["related_product"],
            data["kind"],
            note=data["note"],
            is_required=data["is_required"],
            quantity_per_piece=data["quantity_per_piece"],
            both_ways=data["both_ways"],
        )
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, _("Saved."))
    return _redirect(product)


@require_POST
@module_required(Module.PRODUCTS, Level.WRITE)
def relation_update(request: HttpRequest, pk: int, relation_pk: int) -> HttpResponse:
    """Change the note, the pieces per piece and the flag of one entry."""
    relation = get_object_or_404(
        ProductRelation.objects.select_related("product", "related_product"), pk=relation_pk, product_id=pk
    )
    form = RelationForm(
        {
            "related_product": relation.related_product_id,
            "kind": relation.kind,
            "quantity_per_piece": request.POST.get("quantity_per_piece", ""),
            "note": request.POST.get("note", ""),
            "is_required": request.POST.get("is_required", ""),
        }
    )
    if not form.is_valid():
        messages.error(request, _("Enter a number of pieces above 0 and a note of at most 250 characters."))
        return _redirect(relation.product)
    data = form.cleaned_data
    try:
        suggestions.update_relation(
            relation,
            note=data["note"],
            is_required=data["is_required"],
            quantity_per_piece=data["quantity_per_piece"],
        )
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, _("Saved."))
    return _redirect(relation.product)


@require_POST
@module_required(Module.PRODUCTS, Level.WRITE)
def relation_move(request: HttpRequest, pk: int, relation_pk: int, direction: str) -> HttpResponse:
    """Move one entry up or down in its list."""
    relation = get_object_or_404(ProductRelation.objects.select_related("product"), pk=relation_pk, product_id=pk)
    if direction not in ("up", "down"):
        messages.error(request, _("Unknown direction."))
    else:
        suggestions.move_relation(relation, direction)
    return _redirect(relation.product)


@require_POST
@module_required(Module.PRODUCTS, Level.WRITE)
def relation_delete(request: HttpRequest, pk: int, relation_pk: int) -> HttpResponse:
    """Remove one entry."""
    relation = get_object_or_404(ProductRelation.objects.select_related("product"), pk=relation_pk, product_id=pk)
    suggestions.delete_relation(relation)
    messages.success(request, _("Removed."))
    return _redirect(relation.product)
