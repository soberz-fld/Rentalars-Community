# SPDX-License-Identifier: GPL-3.0-or-later
"""The page parts and steps for bulk material built into an item (built-in quantity material; MAT-040).

On the page of an item: a case, rack or vehicle shows what is built into it and lets a person build in bulk
material (by its ID and a quantity) or take it out; a bulk row shows where it is built in and how much of it is
free. The rules live in ``material.installations``; the API calls the same functions (API-002).
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, module_required
from rentalars.core.forms import StyledForm
from rentalars.material import installations
from rentalars.material.models import MaterialItem
from rentalars.material.numbering import parse_inventory_number


class BuiltInForm(StyledForm):
    """Build a quantity of bulk material into the item whose page it is."""

    material_number = forms.CharField(label=gettext_lazy("Bulk material (ID)"))
    quantity = forms.IntegerField(label=gettext_lazy("Quantity"), min_value=1, max_value=10_000_000, initial=1)
    note = forms.CharField(label=gettext_lazy("Note"), max_length=250, required=False)

    def clean_material_number(self) -> MaterialItem:
        """Turn the typed ID into the bulk row; unknown IDs are rejected."""
        text = self.cleaned_data.get("material_number", "").strip()
        try:
            number = parse_inventory_number(text)
        except ValidationError as error:
            raise forms.ValidationError(error.messages) from error
        row = MaterialItem.objects.filter(inventory_number=number).select_related("material_model").first()
        if row is None:
            raise forms.ValidationError(_("There is no item with the ID %(id)s.") % {"id": text})
        return row


def installed_context(item: MaterialItem) -> dict[str, Any]:
    """What the box “Built-in bulk material” of an item's page shows (MAT-040)."""
    is_bulk = item.material_model.is_bulk
    context: dict[str, Any] = {
        "built_in_is_bulk": is_bulk,
        "built_in_form": BuiltInForm(),
        "can_build_in": not is_bulk and not item.is_archived,
    }
    if is_bulk:
        places = installations.installed_places(item)
        context["built_places"] = places
        context["built_total"] = sum(place.quantity for place in places)
    else:
        context["built_in"] = installations.installed_in(item)
    return context


@require_POST
@module_required(Module.MATERIAL, Level.WRITE)
def built_in_add(request: HttpRequest, pk: int) -> HttpResponse:
    """Build bulk material into an item from the item's page (MAT-040)."""
    container = get_object_or_404(MaterialItem.objects.select_related("material_model"), pk=pk)
    form = BuiltInForm(request.POST)
    if not form.is_valid():
        messages.error(request, " ".join(message for errors in form.errors.values() for message in errors))
        return redirect(reverse("material:item_detail", args=[container.pk]) + "#built-in")
    material = form.cleaned_data["material_number"]
    try:
        installations.install_quantity(
            container,
            material,
            form.cleaned_data["quantity"],
            user=request.user,
            note=form.cleaned_data["note"],
        )
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(
            request,
            _("%(quantity)s × %(material)s built into %(container)s.")
            % {
                "quantity": form.cleaned_data["quantity"],
                "material": material.display_id,
                "container": container.display_id,
            },
        )
    return redirect(reverse("material:item_detail", args=[container.pk]) + "#built-in")


@require_POST
@module_required(Module.MATERIAL, Level.WRITE)
def built_in_remove(request: HttpRequest, pk: int, material_pk: int) -> HttpResponse:
    """Take built-in bulk material out of an item again – all of it, or the quantity typed (MAT-040)."""
    container = get_object_or_404(MaterialItem.objects.select_related("material_model"), pk=pk)
    material = get_object_or_404(MaterialItem.objects.select_related("material_model"), pk=material_pk)
    text = request.POST.get("quantity", "").strip()
    try:
        quantity = int(text) if text else None
        taken = installations.remove_quantity(container, material, quantity, user=request.user)
    except ValueError:
        messages.error(request, _("Enter a whole number."))
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(
            request,
            _("%(quantity)s × %(material)s taken out of %(container)s. They are free stock again.")
            % {"quantity": taken, "material": material.display_id, "container": container.display_id},
        )
    return redirect(reverse("material:item_detail", args=[container.pk]) + "#built-in")
