# SPDX-License-Identifier: GPL-3.0-or-later
"""Einstellungen → Eigene Felder and Feldsätze (MAT-071, MAT-072).

The definitions are master data like the categories (ADM-002, ADM-007):
reading needs the module "Settings" (administration), creating and changing
needs write access to it, deleting the level "delete". The values of items
are entered in the forms of the items (material write).
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Prefetch, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, module_required, request_rights
from rentalars.customfields import services
from rentalars.customfields.forms import CustomFieldForm, FieldsetForm
from rentalars.customfields.models import CustomField, Fieldset, FieldsetEntry
from rentalars.customfields.tables import FIELD_TABLE, FIELDSET_TABLE


def _fields() -> object:
    return CustomField.objects.prefetch_related(
        Prefetch(
            "fieldset_entries", queryset=FieldsetEntry.objects.select_related("fieldset").order_by("fieldset__name")
        )
    ).annotate(value_total=Count("values", filter=~Q(values__value="", values__protected_value=""), distinct=True))


@module_required(Module.ADMINISTRATION)
def field_list(request: HttpRequest) -> HttpResponse:
    """All custom fields with type, marks, fieldsets and how many items have a value."""
    table = FIELD_TABLE.state(request)
    fields = table.order(_fields())
    if table.wants_csv:
        return table.csv_response(fields, _("Custom fields"))
    page = table.paginate(fields)  # UIX-050: the choice of entries per page, as every table
    can_write = request_rights(request).can_write(Module.ADMINISTRATION)
    for field in page:
        field.can_write = can_write
    return render(
        request,
        "customfields/field_list.html",
        {"table": table, "page": page, "rows": table.rows(page), "tab": "fields"},
    )


@module_required(Module.ADMINISTRATION, Level.WRITE)
def field_edit(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    """Create or change a custom field; a change must fit the values items already have."""
    field = get_object_or_404(CustomField, pk=pk) if pk is not None else None
    form = CustomFieldForm(request.POST or None, instance=field)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        messages.success(request, _("The custom field “%(name)s” is saved.") % {"name": saved.name})
        return redirect("customfields:field_list")
    return render(
        request,
        "customfields/field_form.html",
        {
            "form": form,
            "field": field,
            "value_count": services.value_count(field) if field is not None else 0,
            "fieldsets": [entry.fieldset for entry in field.fieldset_entries.select_related("fieldset")]
            if field is not None
            else [],
        },
    )


@require_POST
@module_required(Module.ADMINISTRATION, Level.DELETE)
def field_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a custom field; if items have values, only after "delete the values, too" was confirmed."""
    field = get_object_or_404(CustomField, pk=pk)
    name = field.name
    try:
        count = services.delete_field(field, with_values=request.POST.get("with_values") == "1")
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect("customfields:field_edit", pk=pk)
    if count:
        messages.success(
            request,
            ngettext(
                "The custom field “%(name)s” and the value of %(count)s item are deleted.",
                "The custom field “%(name)s” and the values of %(count)s items are deleted.",
                count,
            )
            % {"name": name, "count": count},
        )
    else:
        messages.success(request, _("The custom field “%(name)s” is deleted.") % {"name": name})
    return redirect("customfields:field_list")


def _fieldsets() -> object:
    return Fieldset.objects.prefetch_related(
        Prefetch("entries", queryset=FieldsetEntry.objects.select_related("field"))
    ).annotate(model_total=Count("assignments", distinct=True))


@module_required(Module.ADMINISTRATION)
def fieldset_list(request: HttpRequest) -> HttpResponse:
    """All fieldsets with their fields (required ones marked) and how many material models have each."""
    table = FIELDSET_TABLE.state(request)
    fieldsets = table.order(_fieldsets())
    if table.wants_csv:
        return table.csv_response(fieldsets, _("Fieldsets"))
    page = table.paginate(fieldsets)  # UIX-050: the choice of entries per page, as every table
    can_write = request_rights(request).can_write(Module.ADMINISTRATION)
    for fieldset in page:
        fieldset.can_write = can_write
    return render(
        request,
        "customfields/fieldset_list.html",
        {
            "table": table,
            "page": page,
            "rows": table.rows(page),
            "tab": "fieldsets",
            "has_fields": CustomField.objects.exists(),
        },
    )


@module_required(Module.ADMINISTRATION, Level.WRITE)
def fieldset_edit(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    """Create or change a fieldset: name, description, and which fields it has in which order."""
    fieldset = get_object_or_404(Fieldset, pk=pk) if pk is not None else None
    form = FieldsetForm(request.POST or None, instance=fieldset)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        messages.success(request, _("The fieldset “%(name)s” is saved.") % {"name": saved.name})
        return redirect("customfields:fieldset_list")
    models = (
        list(fieldset.assignments.select_related("material_model").order_by("material_model__name"))
        if fieldset is not None
        else []
    )
    return render(
        request, "customfields/fieldset_form.html", {"form": form, "fieldset": fieldset, "assignments": models}
    )


@require_POST
@module_required(Module.ADMINISTRATION, Level.DELETE)
def fieldset_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a fieldset no material model has; its fields and the values of items stay."""
    fieldset = get_object_or_404(Fieldset, pk=pk)
    name = fieldset.name
    try:
        services.delete_fieldset(fieldset)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect("customfields:fieldset_edit", pk=pk)
    messages.success(request, _("The fieldset “%(name)s” is deleted.") % {"name": name})
    return redirect("customfields:fieldset_list")
