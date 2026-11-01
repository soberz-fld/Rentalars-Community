# SPDX-License-Identifier: GPL-3.0-or-later
"""Master data in Django's administration interface (ADM-007).

Categories, units, tax rates, manufacturers, suppliers and storage locations
are maintained here instead of in masks of their own. Three things make sure
the administration cannot bypass the business rules:

* Only users with access to the Administration module get in at all; the
  module level decides between looking, editing and deleting
  (see ``accounts.models.User.has_perm``).
* Forms run the same ``clean()`` methods of the models as the rest of the
  application.
* Deleting many rows at once is switched off: it would skip the checks and
  the change log that deleting a single row goes through.
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.contrib import admin
from django.forms import BoundField
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from rentalars.core.admin_tables import TableAdminMixin, tree_path_order
from rentalars.masterdata.models import (
    Category,
    CategoryField,
    DocumentType,
    Manufacturer,
    StorageLocation,
    Supplier,
    TaxAccount,
    TaxRate,
    Unit,
)
from rentalars.material.models import InspectionType
from rentalars.personnel.models import QualificationType

admin.site.site_header = _("Rentalars master data")
admin.site.site_title = _("Rentalars master data")
admin.site.index_title = _("Master data")
admin.site.site_url = "/administration/"
admin.site.disable_action("delete_selected")


class _HelpInHeadField(BoundField):
    """A field of a tabular inline: its help text stands in the column head, without an id (NFA-025).

    Django points ``aria-describedby`` to ``<id>_helptext``, which the inline does not render; the field names its
    help itself (``aria-description``) and refers only to its errors.
    """

    @property
    def aria_describedby(self) -> str | None:
        """Only the errors – they are on the page."""
        return f"{self.auto_id}_error" if self.auto_id and self.errors else None


class CategoryFieldForm(forms.ModelForm):
    """A category field; the options of a choice are typed one per line instead of as JSON (MAT-010)."""

    bound_field_class = _HelpInHeadField

    options = forms.CharField(
        label=_("options"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "cols": 24}),
        help_text=_("For the type “choice”: one option per line."),
    )

    class Meta:
        model = CategoryField
        fields = ["position", "label", "field_type", "unit"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["options"].initial = "\n".join(self.instance.choices or [])
        for field in self.fields.values():
            if field.help_text:
                field.widget.attrs["aria-description"] = str(field.help_text)

    def save(self, commit: bool = True) -> CategoryField:
        """Store the typed options as the list the field expects."""
        lines = [line.strip() for line in self.cleaned_data.get("options", "").splitlines()]
        self.instance.choices = [line for line in lines if line]
        return super().save(commit)


class CategoryFieldInline(admin.TabularInline):
    """The category-specific fields, edited together with their category (MAT-009, MAT-010).

    The first field is "the" category-specific value of MAT-009; further
    fields appear in the form of the material model and as columns of the
    item list.
    """

    model = CategoryField
    form = CategoryFieldForm
    extra = 0
    fields = ["position", "label", "field_type", "unit", "options"]


@admin.register(Category)
class CategoryAdmin(TableAdminMixin, admin.ModelAdmin):
    """Categories with code, stock flag, buffer times and presets (PRD-009, PRD-027).

    PRD-043: a main category can be marked for customer material ("Fremdmaterial").
    """

    list_display = ["path", "code", "has_own_stock", "is_customer_material", "is_active"]
    list_filter = ["is_active", "has_own_stock", "is_customer_material"]
    search_fields = ["name", "code"]
    inlines = [CategoryFieldInline]

    @admin.display(description=_("Name"), ordering=tree_path_order())
    def path(self, category: Category) -> str:
        """UIX-015: the full name, sortable – every category below its main category."""
        return category.path

    fieldsets = [
        (None, {"fields": ["name", "parent", "code", "has_own_stock", "is_customer_material", "is_active"]}),
        (_("Availability"), {"fields": ["buffer_before_hours", "buffer_after_hours"]}),
        (
            _("Presets for new products"),
            {
                "fields": [
                    "default_product_kind",
                    "default_unit",
                    "default_tax_rate",
                    "default_billing_mode",
                    "rental_scale",
                ]
            },
        ),
    ]

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """PRD-029: a category whose code is in use can only be deactivated."""
        if obj is not None and obj.parent_id is None and obj.code and Category.has_article_numbers(obj.code):
            return False
        return super().has_delete_permission(request, obj)


@admin.register(Unit)
class UnitAdmin(TableAdminMixin, admin.ModelAdmin):
    """Units of measure."""

    list_display = ["name", "abbreviation", "is_active"]


@admin.register(TaxRate)
class TaxRateAdmin(TableAdminMixin, admin.ModelAdmin):
    """Tax rates (PRD-016)."""

    list_display = ["name", "rate", "valid_from", "is_default", "is_active"]


@admin.register(Manufacturer)
class ManufacturerAdmin(TableAdminMixin, admin.ModelAdmin):
    """Manufacturers."""

    list_display = ["name", "is_active"]
    search_fields = ["name"]


@admin.register(Supplier)
class SupplierAdmin(TableAdminMixin, admin.ModelAdmin):
    """Suppliers (MAT-019).

    PRJ-106: with e-mail address and phone of their own; the subrentals of the
    supplier are one click away (Planung → Fehlbestände, for this supplier).
    """

    list_display = ["name", "contact", "email", "phone", "city", "customer_number", "is_active"]
    search_fields = ["name", "contact", "email", "city"]
    # UIX-033, PRJ-097: the address – for the route link and the pickups of subrentals.
    fields = [
        "name",
        "contact",
        "email",
        "phone",
        "customer_number",
        "street",
        "postal_code",
        "city",
        "country",
        "route",
        "note",
        "tax_office",
        "is_active",
        "subrentals",
    ]
    readonly_fields = ["route", "subrentals"]

    @admin.display(description=_("route"))
    def route(self, supplier: Supplier) -> str:
        """UIX-033: the link into the route planning of Google Maps, from the viewer's location; nothing leaves before the click."""
        from rentalars.core.maps import route_url

        url = route_url(supplier.address_one_line) if supplier.pk else ""
        if not url:
            return "–"
        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>', url, _("Route in Google Maps")
        )

    @admin.display(description=_("subrentals"))
    def subrentals(self, supplier: Supplier) -> str:
        """The way to the supplier's subrentals of running and coming projects (PRJ-106)."""
        if supplier.pk is None:
            return "–"
        address = reverse("availability:shortages") + f"?supplier={supplier.pk}#subrentals"
        return format_html('<a href="{}">{}</a>', address, _("Show the subrentals at this supplier"))


@admin.register(StorageLocation)
class StorageLocationAdmin(TableAdminMixin, admin.ModelAdmin):
    """Storage locations; one of them can be the default for new items (MAT-052)."""

    list_display = ["path", "is_default", "is_active"]
    search_fields = ["name"]

    @admin.display(description=_("Name"), ordering=tree_path_order())
    def path(self, location: StorageLocation) -> str:
        """UIX-015: the full name, sortable – every location below the one it is part of."""
        return location.path


@admin.register(DocumentType)
class DocumentTypeAdmin(TableAdminMixin, admin.ModelAdmin):  # type: ignore[type-arg]
    """Kinds of project documents: stage plan, rider, contract … (PRJ-007, EML-021)."""

    list_display = ["name", "visible_to_crew", "position", "is_active"]
    list_editable = ["position"]
    ordering = ["position", "name"]


@admin.register(TaxAccount)
class TaxAccountAdmin(TableAdminMixin, admin.ModelAdmin):  # type: ignore[type-arg]
    """The tax accounts (Steuerkonten) the positions of an incoming document are booked to (SKR 03 to begin with)."""

    list_display = ["number", "name", "is_active"]
    search_fields = ["number", "name"]
    ordering = ["number"]


@admin.register(InspectionType)
class InspectionTypeAdmin(TableAdminMixin, admin.ModelAdmin):  # type: ignore[type-arg]
    """Inspection types with interval and what they apply to (MAT-030).

    An inspection applies to all items of the chosen models and of the
    models in the chosen categories, subcategories included.
    """

    list_display = ["name", "interval_months", "is_electrical", "is_active"]  # MAT-078: is_electrical
    search_fields = ["name"]
    filter_horizontal = ["categories", "material_models"]


@admin.register(QualificationType)
class QualificationTypeAdmin(TableAdminMixin, admin.ModelAdmin):  # type: ignore[type-arg]
    """Kinds of qualifications and certificates of people: licences, platforms, first aid (PER-014)."""

    # LOG-012: the driving licence classes a licence covers.
    list_display = ["name", "validity_months", "licence_classes", "is_active"]
    search_fields = ["name"]


# UIX-040: Django's own list of groups (django.contrib.auth) – under the same address as the master data –
# gets columns, CSV and groups as well.
def _table_group_admin() -> None:
    from django.contrib.auth.admin import GroupAdmin
    from django.contrib.auth.models import Group

    if admin.site.is_registered(Group):
        admin.site.unregister(Group)
        # UIX-015: the name as a column of its own – Django's default column (the text of the group)
        # cannot be sorted.
        admin.site.register(Group, type("GroupAdmin", (TableAdminMixin, GroupAdmin), {"list_display": ["name"]}))


_table_group_admin()
