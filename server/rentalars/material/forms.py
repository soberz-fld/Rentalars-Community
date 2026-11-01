# SPDX-License-Identifier: GPL-3.0-or-later
"""Forms of the material module."""

from __future__ import annotations

import copy
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.core.forms import StyledForm, StyledModelForm, mark_required
from rentalars.core.money import decimal_separator
from rentalars.masterdata.models import (
    Category,
    StorageLocation,
    Supplier,
    location_paths,
    remember_location_paths,
)
from rentalars.material import dguv, partial_dates, serials
from rentalars.material.models import (
    ARCHIVED_STATUSES,
    SELECTABLE_STATUS_CHOICES,
    ConnectionType,
    InspectionResult,
    InspectionType,
    ItemStatus,
    MaterialFileKind,
    MaterialItem,
    MaterialModel,
    ProtectionClass,
    Vehicle,
)
from rentalars.material.numbering import parse_inventory_number
from rentalars.material.services import MAX_ITEMS_PER_BATCH
from rentalars.material.spots import SPOT_LENGTH, normalise_spot
from rentalars.products.models import MATERIAL_KINDS, Product, TrailerBilling, VehicleType


def category_form_field(field: Any, initial: str = "") -> forms.Field:
    """A form field for a category-specific field of the given type (MAT-010).

    Choices become a selection, yes/no a selection with an empty choice –
    "not known" is different from "no" –, everything else a text field that
    the category field itself checks (``CategoryField.clean_value``).
    """
    from rentalars.masterdata.models import FieldType

    if field.field_type == FieldType.CHOICE and field.choices:
        return forms.ChoiceField(
            label=field.label_with_unit,
            required=False,
            choices=[("", "–"), *[(choice, choice) for choice in field.choices]],
            initial=initial,
        )
    if field.field_type == FieldType.BOOLEAN:
        return forms.ChoiceField(
            label=field.label, required=False, choices=[("", "–"), ("yes", _("yes")), ("no", _("no"))], initial=initial
        )
    display = initial.replace(".", decimal_separator()) if field.field_type == FieldType.NUMBER else initial
    return forms.CharField(label=field.label_with_unit, required=False, initial=display, max_length=200)


def stock_products() -> Any:
    """Products that material can be assigned to: those with stock of their own, and vehicles (LOG-002)."""
    return Product.objects.filter(kind__in=MATERIAL_KINDS).order_by("article_number")


#: (MAT-059) Where the last choice "net or gross" of a user is kept in the session.
PRICE_ENTRY_SESSION_KEY = "material_price_entry"


class PriceEntryMixin:
    """A purchase price entered net or gross (MAT-059; IMP-014).

    Next to the price the form asks whether it is net or gross and, for a gross price, which tax rate it
    includes – the default tax rate unless another one is chosen. A gross price is stored net, rounded to
    cents, as the material import does. Only a form that shows the purchase price (AUT-019) gets the choice;
    it starts as the user chose last time (``remembered``, kept in the session by the view). A price the form
    shows already (editing, duplicating) is shown gross then, too.
    """

    fields: dict[str, forms.Field]
    initial: dict[str, Any]

    def add_price_entry(self, remembered: dict[str, str] | None = None) -> None:
        """Add the choice "net or gross" and the tax rate next to the price; call at the end of ``__init__``."""
        from rentalars.material.importer import PRICES_GROSS, PRICES_NET, default_tax_rate, tax_rate_choices
        from rentalars.material.services import gross_from_net

        rates = tax_rate_choices()
        if "purchase_price" not in self.fields or not rates:
            return  # without the right no price; without any tax rate only net prices, as before
        remembered = remembered if isinstance(remembered, dict) else {}
        prices = PRICES_GROSS if remembered.get("prices") == PRICES_GROSS else PRICES_NET
        rate = remembered.get("price_tax_rate")
        if rate not in dict(rates):
            rate = default_tax_rate() or rates[0][0]
        price = self.fields["purchase_price"]
        price.label = _("Purchase price")
        price.help_text = _("Stored net: a gross price is converted with the tax rate it includes, rounded to cents.")
        self.fields["prices"] = forms.ChoiceField(
            label=_("The price is"),
            choices=[(PRICES_NET, _("net")), (PRICES_GROSS, _("gross"))],
            initial=prices,
            required=False,
        )
        self.fields["price_tax_rate"] = forms.ChoiceField(
            label=_("The gross price includes"),
            choices=rates,
            initial=rate,
            required=False,
            help_text=_("Only for gross prices."),
        )
        if prices == PRICES_GROSS and self.initial.get("purchase_price") is not None:
            self.initial["purchase_price"] = gross_from_net(self.initial["purchase_price"], rate)

    def clean_price_entry(self, cleaned: dict[str, Any]) -> None:
        """Turn a gross price into the net one that is stored; call from ``clean``."""
        from rentalars.material.services import entered_purchase_price

        if "prices" not in self.fields or cleaned.get("purchase_price") is None:
            return
        try:
            cleaned["purchase_price"] = entered_purchase_price(
                cleaned["purchase_price"], cleaned.get("prices") or "net", cleaned.get("price_tax_rate")
            )
        except ValidationError as error:
            self.add_error("price_tax_rate", error.message_dict.get("price_tax_rate", error.messages))  # type: ignore[attr-defined]

    @property
    def price_entry(self) -> dict[str, str] | None:
        """The choice made, for the view to remember it in the session; ``None`` without the choice."""
        cleaned = getattr(self, "cleaned_data", None)
        if "prices" not in self.fields or cleaned is None:
            return None
        return {"prices": cleaned.get("prices") or "net", "price_tax_rate": cleaned.get("price_tax_rate") or ""}


class LocationChoiceField(forms.ModelChoiceField):
    """A storage location, offered by its full path; the paths come from one query (MAT-018)."""

    def label_from_instance(self, obj: Any) -> str:
        """The full path of the location, e.g. ``Halle 1 > Regal A > Fach 3``."""
        paths = self.__dict__.get("_paths")
        if paths is None:
            paths = self.__dict__["_paths"] = location_paths()
        return paths.get(obj.pk, obj.name)


class MaterialModelForm(StyledModelForm):
    """A material model (the "model" level of MAT-011).

    MAT-048: the manufacturer is typed with suggestions; a name that is not
    among them creates the manufacturer when the model is saved. The product
    is chosen by typing, too (``material:product_suggest``).

    MAT-049: weight, dimensions and power belong to the form – all fields of
    the form are shown, so that saving never empties one the page left out.
    """

    category_specific = forms.CharField(
        label=_("Category-specific value"),
        required=False,
        help_text=_("What it means depends on the category, e.g. the length of a cable."),
    )
    manufacturer_name = forms.CharField(
        label=_("Manufacturer"),
        required=False,
        max_length=120,
        help_text=_("Choose from the suggestions or type a new name: the manufacturer is created with the model."),
    )

    class Meta:
        model = MaterialModel
        fields = [
            "name",
            "short_name",
            "category",
            "category_specific",
            "manufacturer_name",
            "default_product",
            "tracking_mode",
            "specification",
            "weight_kg",
            "length_cm",
            "width_cm",
            "height_cm",
            "power_w",
            "protection_class",  # MAT-077
        ]
        widgets = {"specification": forms.Textarea(attrs={"rows": 3}), "default_product": forms.HiddenInput()}

    def __init__(self, *args: Any, copy_of: MaterialModel | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(is_active=True)
        self.fields["category"].choices = Category.objects.choices()
        self.fields["default_product"].queryset = stock_products()
        self.fields["default_product"].help_text = _("Empty: the model cannot be planned yet.")
        self.fields["protection_class"].choices = [("", "–"), *ProtectionClass.choices]  # MAT-077
        if self.instance.manufacturer_id:
            self.fields["manufacturer_name"].initial = self.instance.manufacturer.name
        # MAT-064: a copy of ``copy_of`` – an unsaved model with its values – may take over the
        # inspection types that name the original itself (MAT-030).
        self.copy_of = copy_of
        if copy_of is not None:
            names = list(InspectionType.objects.filter(material_models=copy_of).values_list("name", flat=True))
            if names:
                self.fields["copy_inspection_types"] = forms.BooleanField(
                    label=_("The copy gets the inspection types of the original, too: %(types)s")
                    % {"types": ", ".join(names)},
                    required=False,
                    initial=True,
                    help_text=_("Inspection types of the category apply to every model of it anyway."),
                )
        self.extra_fields: list[Any] = []
        # A copy (MAT-064) starts with the category of its original, and with all its category-specific values.
        if self.instance.pk or self.instance.category_id:
            self.fields["category_specific"].initial = self.instance.category_specific_value
            fields = self.instance.category.applicable_fields()
            if fields:
                self.fields["category_specific"].label = fields[0].label_with_unit
            # MAT-010: the further fields of the category, after the first one.
            for field in fields[1:]:
                self.fields[f"field_{field.pk}"] = category_form_field(
                    field, self.instance.field_values.get(str(field.pk), "")
                )
                self.extra_fields.append(field)
        self.style_fields()

    @property
    def extra_bound_fields(self) -> list[forms.BoundField]:
        """The further category-specific fields (MAT-010), for the template."""
        return [self[f"field_{field.pk}"] for field in self.extra_fields]

    @property
    def product_text(self) -> str:
        """What the product field shows: article number and name of the chosen product (MAT-048)."""
        value = self["default_product"].value()
        if hasattr(value, "pk"):
            return str(value)
        product = Product.objects.filter(pk=value).first() if str(value or "").isdigit() else None
        return str(product) if product is not None else ""

    def clean(self) -> dict[str, Any]:
        """Check the category-specific values against the types their category defines (MAT-009, MAT-010)."""
        cleaned = super().clean() or {}
        category = cleaned.get("category")
        if category is not None:
            self.instance.category = category
            try:
                self.instance.set_category_specific_value(cleaned.get("category_specific", ""))
            except ValidationError as error:
                self.add_error("category_specific", error)
            if category.pk == self.initial.get("category"):
                for field in self.extra_fields:
                    try:
                        self.instance.set_field_value(field, cleaned.get(f"field_{field.pk}", ""))
                    except ValidationError as error:
                        self.add_error(f"field_{field.pk}", error)
        return cleaned

    def product_hint(self) -> str:
        """A hint if the product belongs to another main category (PRD-032)."""
        from rentalars.material.services import category_mismatch

        return category_mismatch(self.instance.category, self.instance.default_product)

    def save(self, commit: bool = True) -> MaterialModel:
        """Save the model; a manufacturer typed for the first time is created on the way (MAT-048).

        MAT-064 (duplicate): a copy takes over the inspection types of its original if so chosen.
        """
        from rentalars.material.services import copy_inspection_types, manufacturer_named

        self.instance.manufacturer = manufacturer_named(self.cleaned_data.get("manufacturer_name", ""))
        saved = super().save(commit)
        if commit and self.copy_of is not None and self.cleaned_data.get("copy_inspection_types"):
            copy_inspection_types(self.copy_of, saved)
        return saved


class MaterialItemForm(PriceEntryMixin, StyledModelForm):
    """A material item (the "item" level of MAT-011).

    "Installed in" is typed as the ID of the other item (MAT-034); the form
    resolves it and reports IDs that do not exist.

    The status is not part of this form: it is changed on the item page,
    where the reason is asked for (MAT-044).

    MAT-059: the purchase price may be entered gross (:class:`PriceEntryMixin`).
    """

    installed_in_number = forms.CharField(
        label=_("Installed in (ID)"),
        required=False,
        help_text=_("ID of the item this one sits in. Empty: not installed."),
    )
    # MAT-054: bought as a set – the price is noted at another item.
    purchase_price_in_number = forms.CharField(
        label=_("Price included in (ID)"),
        required=False,
        help_text=_("Bought as a set: the ID of the item whose purchase price includes this one. Empty: bought alone."),
    )
    # MAT-050: typed with suggestions, as in the form for new items; a new name creates the supplier.
    supplier_name = forms.CharField(
        label=_("Bought from"),
        required=False,
        max_length=120,
        help_text=_("Choose from the suggestions or type a new name: the supplier is created when you save."),
    )

    # Errors the model reports for "installed_in" appear at the typed ID; MAT-054: "price included in" as well.
    error_field_map = {"installed_in": "installed_in_number", "purchase_price_in": "purchase_price_in_number"}

    class Meta:
        model = MaterialItem
        fields = [
            "serial_number",
            "storage_location",
            "storage_spot",
            "quantity",
            "product_override",
            "installed_in_number",
            "connection_type",
            "individually_rentable",
            "note",
            "supplier_name",
            "supplier_article_number",
            "invoice_number",
            "purchase_date",
            "purchase_price",
            "purchase_price_in_number",
            "purchase_note",
            "specification_override",
            "protection_class_override",  # MAT-077
        ]
        widgets = {
            "note": forms.Textarea(attrs={"rows": 3}),
            "specification_override": forms.Textarea(attrs={"rows": 2}),
        }
        # Partial purchase date: the date may lack its day or month ("00.00.2015").
        field_classes = {"storage_location": LocationChoiceField, "purchase_date": partial_dates.PartialDateField}

    def __init__(self, *args: Any, rights: Rights, remembered: dict[str, str] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # The date with its precision, so that "2015" is shown – and kept – as typed.
        self.initial["purchase_date"] = partial_dates.of(
            self.instance.purchase_date, self.instance.purchase_date_precision
        )
        if self.instance.supplier_id:
            self.fields["supplier_name"].initial = self.instance.supplier.name
        self.fields["storage_location"].queryset = StorageLocation.objects.filter(is_active=True)
        self.fields["product_override"].queryset = stock_products()
        if not rights.has(SpecialRight.PURCHASE_PRICES):
            # AUT-019: without the right the field does not even exist in the form – nor the set it was bought in
            # (MAT-054), which tells about prices too.
            del self.fields["purchase_price"]
            del self.fields["purchase_price_in_number"]
        if not self.instance.material_model.is_bulk:
            del self.fields["quantity"]
        if self.instance.purchase_price_in_id and "purchase_price_in_number" in self.fields:
            self.fields["purchase_price_in_number"].initial = self.instance.purchase_price_in.display_id
        if self.instance.installed_in_id:
            self.fields["installed_in_number"].initial = self.instance.installed_in.display_id
            # MAT-038: the location of an installed item is that of its container.
            self.fields["storage_location"].help_text = _("Installed items are where their container is.")
            self.fields["storage_spot"].help_text = _("Installed items have the spot of their container.")
        model = self.instance.material_model
        self.fields["specification_override"].help_text = _("Empty: as the model – %(text)s") % {
            "text": (model.specification[:80] or "–")
        }
        # MAT-077: a protection class of its own, empty means "as the model".
        self.fields["protection_class_override"].choices = [("", _("as the model")), *ProtectionClass.choices]
        self.fields["protection_class_override"].help_text = _("Empty: as the model – %(text)s") % {
            "text": model.get_protection_class_display() or "–"
        }
        # MAT-013: own values for the category-specific fields, empty means "as the model".
        self.override_fields: list[Any] = []
        overrides = self.instance.field_value_overrides or {}
        for field in model.category.applicable_fields():
            name = f"override_{field.pk}"
            self.fields[name] = category_form_field(field, overrides.get(str(field.pk), ""))
            model_value = model.field_display(field)
            self.fields[name].help_text = _("Empty: as the model – %(text)s") % {"text": model_value or "–"}
            self.override_fields.append(field)
        self.style_fields()
        self.add_price_entry(remembered)  # MAT-059

    def clean_installed_in_number(self) -> MaterialItem | None:
        """Turn the typed ID into the item; unknown IDs are rejected (MAT-034)."""
        text = self.cleaned_data.get("installed_in_number", "").strip()
        if not text:
            return None
        try:
            number = parse_inventory_number(text)
        except ValidationError as error:
            raise forms.ValidationError(error.messages) from error
        container = MaterialItem.objects.filter(inventory_number=number).select_related("material_model").first()
        if container is None:
            raise forms.ValidationError(_("There is no item with the ID %(id)s.") % {"id": text})
        return container

    def clean_purchase_price_in_number(self) -> MaterialItem | None:
        """MAT-054: turn the typed ID of the item with the price of the set into that item."""
        text = self.cleaned_data.get("purchase_price_in_number", "").strip()
        if not text:
            return None
        try:
            number = parse_inventory_number(text)
        except ValidationError as error:
            raise forms.ValidationError(error.messages) from error
        head = MaterialItem.objects.filter(inventory_number=number).select_related("purchase_price_in").first()
        if head is None:
            raise forms.ValidationError(_("There is no item with the ID %(id)s.") % {"id": text})
        return head

    def clean(self) -> dict[str, Any]:
        """Apply the container and the own values before the model validates; a gross price becomes net (MAT-059)."""
        cleaned = super().clean() or {}
        self.clean_price_entry(cleaned)
        partial_dates.split_into(self, cleaned)  # The date and its precision
        if "installed_in_number" in cleaned:
            self.instance.installed_in = cleaned["installed_in_number"]
        if "purchase_price_in_number" in cleaned:
            self.instance.purchase_price_in = cleaned["purchase_price_in_number"]
        for field in self.override_fields:
            try:
                self.instance.set_field_override(field, cleaned.get(f"override_{field.pk}", ""))
            except ValidationError as error:
                self.add_error(f"override_{field.pk}", error)
        return cleaned

    @property
    def override_bound_fields(self) -> list[forms.BoundField]:
        """The item's own values for the category-specific fields (MAT-013), for the template."""
        return [self[f"override_{field.pk}"] for field in self.override_fields]

    def serial_warnings(self) -> list[str]:
        """Warning if the serial number was changed to one another item has (MAT-004).

        Call after ``is_valid()``. Only a changed serial number is asked about: one that was a duplicate before
        stays so without nagging at every edit. Retired and sold items count.
        """
        if "serial_number" not in self.changed_data:
            return []
        serial = (self.cleaned_data.get("serial_number") or "").strip()
        return serials.entry_warnings([(serial, self.instance.material_model_id)], exclude=[self.instance.pk])

    def product_hint(self) -> str:
        """A hint if the chosen product belongs to another main category (PRD-032)."""
        from rentalars.material.services import category_mismatch

        return category_mismatch(self.instance.material_model.category, self.instance.product_override)

    def save(self, commit: bool = True) -> MaterialItem:
        """Save is done by the view through the service; here only the supplier is resolved (MAT-050)."""
        from rentalars.material.services import supplier_named

        self.instance.supplier = supplier_named(self.cleaned_data.get("supplier_name", ""))
        return super().save(commit)


class StatusChangeForm(StyledForm):
    """Change the status of an item and say why (MAT-044, MAT-045)."""

    status = forms.ChoiceField(label=_("New status"))
    reason = forms.CharField(
        label=_("Reason"),
        required=False,
        max_length=250,
        help_text=_("Required for “defective”: what is broken? Shown on the item and kept in its history."),
    )

    def __init__(self, *args: Any, item: MaterialItem, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = [
            (value, label[:1].upper() + label[1:]) for value, label in item.selectable_statuses
        ]
        # The browser asks for the reason as soon as "defective" is chosen; the
        # rule itself is checked on the server (MaterialItem.clean).
        self.fields["reason"].widget.attrs["data-require-if"] = f"status={ItemStatus.DEFECTIVE.value}"
        self.fields["reason"].widget.attrs["autocomplete"] = "off"


class InstallForm(StyledForm):
    """Install this item into another one, from the item's own page (MAT-047)."""

    container_number = forms.CharField(label=_("Install in"))
    connection_type = forms.ChoiceField(
        label=_("Kind of connection"), choices=ConnectionType.choices, initial=ConnectionType.LOOSE
    )

    def clean_container_number(self) -> MaterialItem:
        """Turn the typed ID into the container; unknown IDs are rejected."""
        text = self.cleaned_data.get("container_number", "").strip()
        try:
            number = parse_inventory_number(text)
        except ValidationError as error:
            raise forms.ValidationError(error.messages) from error
        container = MaterialItem.objects.filter(inventory_number=number).select_related("material_model").first()
        if container is None:
            raise forms.ValidationError(_("There is no item with the ID %(id)s.") % {"id": text})
        return container


class ContentAddForm(StyledForm):
    """Add an item to a container from the container's page (MAT-046)."""

    item_number = forms.CharField(label=_("Item (ID)"))
    connection_type = forms.ChoiceField(label=_("Kind of connection"), choices=ConnectionType.choices)
    individually_rentable = forms.BooleanField(
        label=_("can be rented on its own"),
        required=False,
        help_text=_("For permanently installed items that are taken out when needed."),
    )

    def clean_item_number(self) -> MaterialItem:
        """Turn the typed ID into the item; unknown IDs are rejected."""
        text = self.cleaned_data.get("item_number", "").strip()
        try:
            number = parse_inventory_number(text)
        except ValidationError as error:
            raise forms.ValidationError(error.messages) from error
        item = (
            MaterialItem.objects.filter(inventory_number=number)
            .select_related("material_model", "installed_in")
            .first()
        )
        if item is None:
            raise forms.ValidationError(_("There is no item with the ID %(id)s.") % {"id": text})
        return item


class ItemCreateForm(PriceEntryMixin, StyledForm):
    """Create one or several items of a model in one step (MAT-006, MAT-050).

    MAT-050: the first item gets the start ID, each further one the next free
    ID after it; one serial number per item, typed one per line (the page
    script shows a field per item); the supplier is typed with suggestions
    and created if new; invoice number and invoice date. MAT-052: the
    default storage location is preselected.

    MAT-059: the purchase price may be entered gross (:class:`PriceEntryMixin`);
    a duplicated item fills the form (:func:`item_copy_initial`).
    """

    count = forms.IntegerField(label=_("Number of items"), min_value=1, max_value=MAX_ITEMS_PER_BATCH, initial=1)
    inventory_number = forms.CharField(
        label=_("Start ID"),
        required=False,
        help_text=_(
            "Empty: the next free IDs. Otherwise the first item gets this ID, each further one the next free ID after it."
        ),
    )
    quantity = forms.IntegerField(label=_("Quantity"), min_value=0, initial=1, required=False)
    status = forms.ChoiceField(
        label=_("Status"),
        choices=[choice for choice in SELECTABLE_STATUS_CHOICES if choice[0] not in ARCHIVED_STATUSES],
        initial=ItemStatus.AVAILABLE,
    )
    storage_location = LocationChoiceField(
        label=_("Storage location"), queryset=StorageLocation.objects.filter(is_active=True), required=False
    )
    # MAT-080: the place within the location, for all items of this batch.
    storage_spot = forms.CharField(
        label=_("Storage spot"),
        max_length=SPOT_LENGTH,
        required=False,
        help_text=_("The place in the storage location, e.g. 01-A-1: shelf or area, bay (letter), height."),
    )
    serial_numbers = forms.CharField(
        label=_("Serial numbers"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_("One per line, in the order of the IDs. An empty line: that item has none."),
    )
    supplier_name = forms.CharField(
        label=_("Bought from"),
        required=False,
        max_length=120,
        help_text=_("Choose from the suggestions or type a new name: the supplier is created with the items."),
    )
    supplier_article_number = forms.CharField(label=_("Supplier's article number"), max_length=120, required=False)
    invoice_number = forms.CharField(label=_("Invoice number"), max_length=60, required=False)
    # Partial purchase date: the day or month may be unknown ("00.00.2015").
    purchase_date = partial_dates.PartialDateField(label=_("Invoice date"), required=False)
    purchase_price = forms.DecimalField(label=_("Purchase price (net)"), min_value=0, decimal_places=2, required=False)
    # MAT-054: several items bought as one set for one price.
    price_for_set = forms.BooleanField(
        label=_("The price is that of all these items together (a set)"),
        required=False,
        help_text=_("The first item gets the price; the others have it included in the first one."),
    )
    purchase_note = forms.CharField(label=_("Purchase note"), max_length=250, required=False)

    def __init__(
        self,
        *args: Any,
        material_model: MaterialModel,
        rights: Rights,
        remembered: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.material_model = material_model
        # MAT-014: the supplier of the item created last of this model, as a suggestion.
        from rentalars.material.services import suggested_purchase_fields

        suggested = suggested_purchase_fields(material_model)
        if suggested.get("supplier"):
            self.fields["supplier_name"].initial = (
                Supplier.objects.filter(pk=suggested["supplier"]).values_list("name", flat=True).first() or ""
            )
        self.fields["supplier_article_number"].initial = suggested.get("supplier_article_number", "")
        # MAT-052: new items go to the default storage location unless somebody chooses another one.
        default_location = StorageLocation.get_default()
        if default_location is not None:
            self.fields["storage_location"].initial = default_location.pk
        if not rights.has(SpecialRight.PURCHASE_PRICES):
            del self.fields["purchase_price"]
            del self.fields["price_for_set"]
        if material_model.is_bulk:
            # Bulk material is one row with a quantity (MAT-005).
            del self.fields["count"]
            self.fields.pop("price_for_set", None)
            self.fields["inventory_number"].label = _("ID")
            self.fields["inventory_number"].help_text = _("Empty: the next free ID.")
            self.fields["serial_numbers"].label = _("Serial number")
            self.fields["serial_numbers"].help_text = ""
        else:
            del self.fields["quantity"]
        self.add_price_entry(remembered)  # MAT-059

    def clean_inventory_number(self) -> int | None:
        """Parse a typed start ID and make sure it is free."""
        text = self.cleaned_data.get("inventory_number", "").strip()
        if not text:
            return None
        try:
            number = parse_inventory_number(text)
        except ValidationError as error:
            raise forms.ValidationError(error.messages) from error
        if MaterialItem.objects.filter(inventory_number=number).exists():
            raise forms.ValidationError(_("This ID is already taken."))
        return number

    def clean(self) -> dict[str, Any]:
        """One serial number per item at most (MAT-050); a gross price becomes net (MAT-059)."""
        cleaned = super().clean() or {}
        self.clean_price_entry(cleaned)
        from rentalars.material.services import check_serial_numbers

        lines = (cleaned.get("serial_numbers") or "").splitlines()
        try:
            cleaned["serial_list"] = check_serial_numbers(lines, cleaned.get("count") or 1)
        except ValidationError as error:
            self.add_error("serial_numbers", error.message_dict["serial_numbers"])
        return cleaned

    @property
    def serial_count(self) -> int:
        """How many serial number fields the page script shows at first: the number of items (MAT-050)."""
        value = self["count"].value() if "count" in self.fields else 1
        try:
            return max(1, min(MAX_ITEMS_PER_BATCH, int(value or 1)))
        except (TypeError, ValueError):
            return 1

    def serial_warnings(self) -> list[str]:
        """Warnings about the serial numbers: given twice in this entry, or an item has them already.

        Call after ``is_valid()``. Retired and sold items count. Nothing is refused: the page shows the warnings
        and creates the items when the user confirms (:func:`rentalars.material.serials.confirmed`).
        """
        entries = [(serial, self.material_model.pk) for serial in self.cleaned_data.get("serial_list") or []]
        return serials.entry_warnings(entries)

    def item_fields(self) -> dict[str, Any]:
        """The values shared by all new items, as the service expects them; a new supplier is created here."""
        from rentalars.material.services import supplier_named

        names = [
            "status",
            "storage_location",
            "storage_spot",
            "purchase_date",
            "purchase_price",
            "purchase_note",
            "supplier_article_number",
            "invoice_number",
            "quantity",
        ]
        fields = {name: self.cleaned_data[name] for name in names if self.cleaned_data.get(name) not in (None, "")}
        bought = fields.get("purchase_date")
        if isinstance(bought, partial_dates.PartialDate):  # The date and how much of it is known
            fields["purchase_date"], fields["purchase_date_precision"] = bought.date, bought.precision
        supplier = supplier_named(self.cleaned_data.get("supplier_name", ""))
        if supplier is not None:
            fields["supplier"] = supplier
        return fields


def item_copy_initial(item: MaterialItem, rights: Rights) -> dict[str, Any]:
    """What the form for new items starts with when ``item`` is duplicated (MAT-064; MAT-050).

    The purchase data, the storage location and – for bulk material – the
    quantity; the status "available" whatever the original's; neither its
    serial number nor its ID. The purchase price only for who may see it
    (AUT-019), and not of an item bought in a set: its price is noted at
    another item (MAT-054).
    """
    location = item.effective_storage_location
    initial: dict[str, Any] = {
        "status": ItemStatus.AVAILABLE,
        "supplier_name": item.supplier.name if item.supplier_id else "",
        "supplier_article_number": item.supplier_article_number,
        "invoice_number": item.invoice_number,
        "purchase_date": partial_dates.of(item.purchase_date, item.purchase_date_precision),
        "purchase_note": item.purchase_note,
    }
    if location is not None:
        initial["storage_location"] = location.pk
        initial["storage_spot"] = item.effective_storage_spot
    if item.material_model.is_bulk:
        initial["quantity"] = item.quantity
    if rights.has(SpecialRight.PURCHASE_PRICES) and item.purchase_price_in_id is None:
        initial["purchase_price"] = item.purchase_price
    return initial


class SupplierDialogForm(StyledModelForm):
    """A new supplier with its master data, in a dialog over a form that asks for one (MAT-060).

    The fields of the supplier in the master data (MAT-019, PRJ-106, UIX-033:
    ``masterdata.admin.SupplierAdmin``) but "active" – a new supplier is.
    A name that exists already, in whatever case, is refused: the form would
    find that supplier by its name anyway (MAT-050).
    """

    class Meta:
        model = Supplier
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
            "note",
        ]
        widgets = {"note": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # The dialog stands over a form that may have fields of the same names ("note"); IDs must be unique (NFA-025).
        kwargs.setdefault("auto_id", "supplier_%s")
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("autocomplete", "off")
        # The dialog opens with the cursor in the name, not on its close button.
        self.fields["name"].widget.attrs["autofocus"] = True

    def clean_name(self) -> str:
        """A supplier of the same name – also in other case – exists only once."""
        name = (self.cleaned_data.get("name") or "").strip()
        if Supplier.objects.filter(name__iexact=name).exists():
            raise forms.ValidationError(pgettext_lazy("material", "There is a supplier of this name already."))
        return name


# --- Stage 5 -------------------------------------------------------------------------------------


class DefectReportForm(StyledForm):
    """Report a defect, with a photo taken on the spot (MAT-023)."""

    description = forms.CharField(label=_("What is defective?"), widget=forms.Textarea(attrs={"rows": 3}))
    photo = forms.ImageField(
        label=_("Photo"),
        required=False,
        help_text=_("Optional. On a phone the camera opens."),
        widget=forms.ClearableFileInput(
            attrs={"accept": "image/jpeg,image/png,image/webp,image/gif", "capture": "environment"}
        ),
    )


class BlockForm(StyledForm):
    """Block an item for a period (MAT-024)."""

    start = forms.DateTimeField(label=_("From"))
    end = forms.DateTimeField(label=_("Until"))
    reason = forms.CharField(label=_("Reason"), max_length=250, help_text=_("e.g. “in repair at the manufacturer”"))

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # The item page also has the status form with a field "reason"; IDs must be unique (NFA-025).
        kwargs.setdefault("auto_id", "block_%s")
        super().__init__(*args, **kwargs)

    def clean(self) -> dict[str, Any]:
        """The end lies after the start."""
        cleaned = super().clean() or {}
        if cleaned.get("start") and cleaned.get("end") and cleaned["end"] <= cleaned["start"]:
            self.add_error("end", _("The end must lie after the start."))
        return cleaned


#: MAT-078: the answers to "passed?" of the function test in the form (the visual inspection is a tick, MAT-081).
_YES_NO = {"yes": True, "no": False}


def inspector_name(user: Any) -> str:
    """How a user is written down as the one who inspected (MAT-081): the full name, else the user name."""
    return (user.get_full_name() or user.get_username()).strip()


class InspectionForm(StyledForm):
    """Record an inspection of an item (MAT-031).

    MAT-078: for an electrical inspection type (``InspectionType.is_electrical``) the form asks for the
    measured values as well (``material.dguv``). They start with the protection class of the item and the
    length of its cord (category-specific "Länge") and with the test device the user named last. The page
    shows them only while such a type is chosen; values sent with another type are ignored.
    """

    inspection_type = forms.ModelChoiceField(label=_("Inspection"), queryset=InspectionType.objects.none())
    date = forms.DateField(label=_("Date"))
    inspector = forms.CharField(label=_("Inspected by"), max_length=120)
    result = forms.ChoiceField(label=_("Result"), choices=InspectionResult.choices, initial=InspectionResult.PASSED)
    note = forms.CharField(label=_("Note"), required=False, widget=forms.Textarea(attrs={"rows": 2}))
    protocol = forms.FileField(label=_("Protocol"), required=False)
    # MAT-078: the fields of an electrical inspection (dguv.ELECTRICAL_FIELDS).
    protection_class = forms.ChoiceField(
        label=_("Protection class"), required=False, choices=[("", "–"), *ProtectionClass.choices]
    )
    cord_length_m = forms.DecimalField(
        label=_("Cord length (m)"),
        required=False,
        min_value=0,
        max_digits=6,
        decimal_places=2,
        help_text=_("For the limit of the protective conductor resistance. Empty: up to 5 m."),
    )
    test_device = forms.CharField(
        label=_("Test device"), required=False, max_length=120, help_text=_("e.g. “Benning ST 760, SN 12345”")
    )
    # MAT-081: a tick, not a choice – ticked: passed. Not ticked records "not passed", which fails the
    # inspection unless the note gives a reason (``dguv.clean_values``).
    visual_check_passed = forms.BooleanField(label=_("Visual inspection passed"), required=False)
    pe_resistance_ohm = forms.DecimalField(required=False, min_value=0, max_digits=7, decimal_places=3)
    insulation_resistance_mohm = forms.DecimalField(required=False, min_value=0, max_digits=9, decimal_places=3)
    pe_current_ma = forms.DecimalField(required=False, min_value=0, max_digits=7, decimal_places=3)
    touch_current_ma = forms.DecimalField(required=False, min_value=0, max_digits=7, decimal_places=3)
    function_test_passed = forms.ChoiceField(
        label=_("Function test"),
        required=False,
        choices=[("", _("does not apply")), ("yes", _("passed")), ("no", _("not passed"))],
    )

    def __init__(
        self, *args: Any, types: list[InspectionType], item: MaterialItem | None = None, user: Any = None, **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        # MAT-081: today and the user, who changes them where it was another day or another person.
        self.fields["date"].initial = timezone.localdate()
        if getattr(user, "pk", None) is not None:
            self.fields["inspector"].initial = inspector_name(user)
        self.fields["inspection_type"].queryset = InspectionType.objects.filter(pk__in=[t.pk for t in types])
        if len(types) == 1:
            self.fields["inspection_type"].initial = types[0].pk
        # MAT-078: the types that ask for measured values; without one the form has no such fields.
        self.electrical_type_ids = [t.pk for t in types if t.is_electrical]
        if not self.electrical_type_ids:
            for name in dguv.ELECTRICAL_FIELDS:
                del self.fields[name]
            return
        #: ``data-show-if`` of the fields of an electrical inspection.
        self.electrical_condition = "inspection_type=" + "|".join(str(pk) for pk in self.electrical_type_ids)
        mark_required(self.fields["protection_class"], self.electrical_condition)
        for measurement in dguv.MEASUREMENTS:
            field = self.fields[measurement.name]
            field.label = f"{measurement.label} {measurement.symbol} ({measurement.unit})"
            # The limit and the verdict next to the field (``material/_dguv_fields.html``) describe it.
            field.widget.attrs.update({"aria-describedby": f"dguv-{measurement.name}", "autocomplete": "off"})
        if item is not None:
            self.fields["protection_class"].initial = item.effective_protection_class
            self.fields["cord_length_m"].initial = dguv.cord_length_of(item)
        if getattr(user, "pk", None) is not None:
            from rentalars.material.models import Inspection

            self.fields["test_device"].initial = (
                Inspection.objects.filter(recorded_by=user)
                .exclude(test_device="")
                .order_by("-recorded_at", "-id")
                .values_list("test_device", flat=True)
                .first()
            )

    def _is_electrical(self, inspection_type: InspectionType | None) -> bool:
        """Whether the chosen type asks for measured values."""
        return inspection_type is not None and inspection_type.pk in self.electrical_type_ids

    def clean(self) -> dict[str, Any]:
        """MAT-078: the fields of an electrical inspection count only for an electrical type."""
        cleaned = super().clean() or {}
        if self.electrical_type_ids and not self._is_electrical(cleaned.get("inspection_type")):
            for name in dguv.ELECTRICAL_FIELDS:
                self._errors.pop(name, None)
                cleaned.pop(name, None)
        return cleaned

    @staticmethod
    def _typed(name: str, value: Any) -> Any:
        """A value of the form as ``dguv`` takes it: yes/no as ``True``/``False``, empty as ``None``."""
        if name == "visual_check_passed":
            return None if value is None else bool(value)  # MAT-081: a tick; never answered while the form is new
        if name == "function_test_passed":
            return _YES_NO.get(value or "")
        if name in ("protection_class", "test_device"):
            return value or ""
        return value

    def electrical_values(self) -> dict[str, Any] | None:
        """What an electrical inspection measured, for ``services.record_inspection``; ``None`` for another type."""
        if not self.electrical_type_ids or not self._is_electrical(self.cleaned_data.get("inspection_type")):
            return None
        return {name: self._typed(name, self.cleaned_data.get(name)) for name in dguv.ELECTRICAL_FIELDS}

    def evaluation(self) -> dguv.Evaluation | None:
        """The values as typed so far against their limits – for the page and its live check (MAT-078).

        A sent form is judged by what it sent, whatever errors it has: a field that is not a number counts
        as not measured. A new form is judged by its initial values.
        """
        if not self.electrical_type_ids:
            return None
        if getattr(self, "_evaluation", None) is not None:
            return self._evaluation
        values = {}
        for name in dguv.ELECTRICAL_FIELDS:
            field = self.fields[name]
            if self.is_bound:
                try:
                    value = field.clean(self[name].data)
                except ValidationError:
                    value = None
            else:
                value = self.get_initial_for_field(field, name)
            values[name] = self._typed(name, value)
        self._evaluation: dguv.Evaluation | None = dguv.evaluate(values)
        return self._evaluation

    def measurement_rows(self) -> list[tuple[forms.BoundField, dguv.ValueCheck]]:
        """Each measured value's field with its limit and verdict, in the order of the standard."""
        evaluation = self.evaluation()
        if evaluation is None:
            return []
        return [(self[check.measurement.name], check) for check in evaluation.checks]


class BatchInspectionForm(StyledForm):
    """The part of a mass inspection that holds for all items: type, day, inspector and test device (MAT-082).

    The types offered are those that apply to every chosen item. Day and inspector start with today and the
    user, the test device with the one the user named last – an electrical inspection needs it once for all.
    """

    inspection_type = forms.ModelChoiceField(label=_("Inspection"), queryset=InspectionType.objects.none())
    date = forms.DateField(label=_("Date"))
    inspector = forms.CharField(label=_("Inspected by"), max_length=120)
    test_device = forms.CharField(
        label=_("Test device"),
        required=False,
        max_length=120,
        help_text=_("For all electrical inspections of this list, e.g. “Benning ST 760, SN 12345”."),
    )

    def __init__(
        self, *args: Any, types: list[InspectionType], user: Any = None, preselect: Any = None, **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self.fields["inspection_type"].queryset = InspectionType.objects.filter(pk__in=[t.pk for t in types])
        self.fields["inspection_type"].empty_label = None if len(types) == 1 else "–"
        chosen = next((t for t in types if str(t.pk) == str(preselect)), types[0] if len(types) == 1 else None)
        if chosen is not None:
            self.fields["inspection_type"].initial = chosen.pk
        self.fields["date"].initial = timezone.localdate()
        self.electrical_type_ids = [t.pk for t in types if t.is_electrical]
        #: ``data-show-if`` of what only an electrical inspection needs; ``None``: no such type among the choices.
        self.electrical_condition = (
            "inspection_type=" + "|".join(str(pk) for pk in self.electrical_type_ids)
            if self.electrical_type_ids
            else None
        )
        if not self.electrical_type_ids:
            del self.fields["test_device"]
        if getattr(user, "pk", None) is not None:
            self.fields["inspector"].initial = inspector_name(user)
            if "test_device" in self.fields:
                from rentalars.material.models import Inspection

                self.fields["test_device"].initial = (
                    Inspection.objects.filter(recorded_by=user)
                    .exclude(test_device="")
                    .order_by("-recorded_at", "-id")
                    .values_list("test_device", flat=True)
                    .first()
                )
        self.preselected_electrical = chosen is not None and chosen.is_electrical
        if self.is_bound:
            # After an error the type that was sent counts – without scripts the block would stay hidden otherwise.
            sent = str(self.data.get(self.add_prefix("inspection_type"), ""))
            self.preselected_electrical = sent in {str(pk) for pk in self.electrical_type_ids}


class BatchRowForm(StyledForm):
    """What was found at one item of a mass inspection: its result, a note and – electrical – the values (MAT-082).

    The rows have a prefix of their own (``i<id>``). The visual inspection is a column of ticks outside this
    form: a box per item named ``visual``, so that one tick in the heading ticks them all.
    """

    result = forms.ChoiceField(
        label=_("Result"),
        required=False,
        choices=[
            ("passed", _("passed")),
            ("failed", _("failed")),
            ("", _("by the values (electrical)")),
        ],
    )
    note = forms.CharField(label=_("Note"), required=False, max_length=250)
    protection_class = copy.deepcopy(InspectionForm.base_fields["protection_class"])
    cord_length_m = copy.deepcopy(InspectionForm.base_fields["cord_length_m"])
    pe_resistance_ohm = copy.deepcopy(InspectionForm.base_fields["pe_resistance_ohm"])
    insulation_resistance_mohm = copy.deepcopy(InspectionForm.base_fields["insulation_resistance_mohm"])
    pe_current_ma = copy.deepcopy(InspectionForm.base_fields["pe_current_ma"])
    touch_current_ma = copy.deepcopy(InspectionForm.base_fields["touch_current_ma"])
    function_test_passed = copy.deepcopy(InspectionForm.base_fields["function_test_passed"])

    def __init__(
        self,
        *args: Any,
        item: MaterialItem,
        electrical_first: bool = False,
        fields_by_category: dict[int, list[Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.item = item
        self.fields["result"].initial = "" if electrical_first else "passed"
        self.fields["protection_class"].initial = item.effective_protection_class
        self.fields["cord_length_m"].initial = dguv.cord_length_of(item, fields_by_category=fields_by_category)
        for name in ("protection_class", "cord_length_m", "pe_resistance_ohm", "insulation_resistance_mohm"):
            self.fields[name].help_text = ""
        for measurement in dguv.MEASUREMENTS:
            self.fields[measurement.name].label = f"{measurement.label} {measurement.symbol}"
        self.fields["cord_length_m"].label = _("Cord length (m)")
        # The table heading names the column; the box names it for a screen reader together with the item.
        for field in self.fields.values():
            field.widget.attrs["aria-label"] = f"{field.label} {item.display_id}"
            field.widget.attrs.setdefault("autocomplete", "off")

    @property
    def measurement_fields(self) -> list[forms.BoundField]:
        """The bound fields of the measurements, in the order of ``dguv.MEASUREMENTS``."""
        return [self[measurement.name] for measurement in dguv.MEASUREMENTS]

    def electrical_values(self, *, visual: bool) -> dict[str, Any]:
        """The values as ``services.record_inspections`` takes them; ``visual`` is the tick of the item."""
        data = self.cleaned_data
        return {
            "protection_class": data.get("protection_class") or "",
            "cord_length_m": data.get("cord_length_m"),
            "visual_check_passed": visual,
            **{name: data.get(name) for name in dguv.MEASUREMENTS_BY_NAME},
            "function_test_passed": _YES_NO.get(data.get("function_test_passed") or ""),
        }


class MaterialFileForm(StyledForm):
    """Attach a picture or document to a model or item (MAT-017)."""

    file = forms.FileField(label=_("File"))
    kind = forms.ChoiceField(label=_("Kind"), choices=MaterialFileKind.choices, initial=MaterialFileKind.MANUAL)
    title = forms.CharField(label=_("Title"), required=False, max_length=200)

    def __init__(self, *args: Any, may_add_invoice: bool = False, **kwargs: Any) -> None:
        """Offer the kind "invoice" only to users who may see purchase prices (R1-1).

        Photos are not added here (MAT-090): they have their own panel with their own upload on the page of
        the model or item, where they are made anew.
        """
        super().__init__(*args, **kwargs)
        hidden = {MaterialFileKind.PICTURE} | (set() if may_add_invoice else {MaterialFileKind.INVOICE})
        self.fields["kind"].choices = [choice for choice in MaterialFileKind.choices if choice[0] not in hidden]


class BulkEditForm(StyledForm):
    """Change status, storage location or product of the chosen items (MAT-029)."""

    KEEP = ""
    status = forms.ChoiceField(label=_("Status"), required=False)
    reason = forms.CharField(label=_("Reason"), required=False, max_length=250)
    storage_location = forms.ChoiceField(label=_("Storage location"), required=False)
    # MAT-080: empty leaves the spots as they are; the spot is removed by moving to "no storage location".
    storage_spot = forms.CharField(label=_("Storage spot"), required=False, max_length=SPOT_LENGTH)
    product = forms.ChoiceField(label=_("Product"), required=False)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        keep = ("", _("– leave as it is –"))
        self.fields["status"].choices = [
            keep,
            *[(value, capfirst(str(label))) for value, label in SELECTABLE_STATUS_CHOICES],
        ]
        self.fields["storage_location"].choices = [
            keep,
            ("none", _("no storage location")),
            *[
                (str(location.pk), location.path)
                for location in remember_location_paths(StorageLocation.objects.filter(is_active=True))
            ],
        ]
        self.fields["product"].choices = [
            keep,
            ("model", _("as the model")),
            *[(str(product.pk), f"{product.article_number} {product.name}") for product in stock_products()],
        ]
        self.fields["reason"].widget.attrs["data-require-if"] = f"status={ItemStatus.DEFECTIVE.value}"

    def changes(self) -> dict[str, Any]:
        """What to change, as :func:`material.services.bulk_update` expects it."""
        from rentalars.material.services import UNCHANGED

        data = self.cleaned_data
        changes: dict[str, Any] = {"status": data.get("status") or None, "reason": data.get("reason", "")}
        location = data.get("storage_location", "")
        changes["storage_location"] = (
            UNCHANGED if not location else None if location == "none" else StorageLocation.objects.get(pk=location)
        )
        changes["storage_spot"] = normalise_spot(data.get("storage_spot", "")) or None
        product = data.get("product", "")
        changes["product"] = (
            UNCHANGED if not product else None if product == "model" else Product.objects.get(pk=product)
        )
        return changes


# --- The fleet (LOG-002, LOG-003, LOG-016) ----------------------------------------------------------------


class VehicleForm(StyledModelForm):
    """The vehicle data of an item of a vehicle product (LOG-002, LOG-003, LOG-012, LOG-013).

    A motor vehicle has its seats as minimum and maximum – both required, the
    same for a fixed number – and how much it may tow; a trailer has neither,
    so the form leaves those fields out for it.
    """

    class Meta:
        model = Vehicle
        fields = ["licence_plate", "seats_min", "seats_max", "licence_class", "towing_capacity_kg", "gross_weight_kg"]

    def __init__(self, *args: Any, item: MaterialItem, **kwargs: Any) -> None:
        kwargs.setdefault("instance", Vehicle.objects.filter(item=item).first() or Vehicle(item=item))
        super().__init__(*args, **kwargs)
        self.item = item
        product = item.product
        self.is_car = product is not None and product.is_car
        if self.is_car:
            for name in ("seats_min", "seats_max"):
                mark_required(self.fields[name])
        else:
            # A trailer has no seats and tows nothing: what the page cannot show is not kept either.
            for name in ("seats_min", "seats_max", "towing_capacity_kg"):
                del self.fields[name]
                setattr(self.instance, name, None)
        self.fields["licence_plate"].widget.attrs["autocomplete"] = "off"

    def changes(self) -> dict[str, Any]:
        """The values for :func:`material.fleet.save_vehicle`."""
        return {name: self.cleaned_data[name] for name in self.fields}


class FleetTransitionForm(StyledForm):
    """Take a model planned as material into the fleet: type and rates of the new vehicle product (LOG-016).

    The rates need the price right, the internal costs the right to see
    purchase prices (AUT-019, LOG-010); without them the fields are not part
    of the form. The day price of a trailer starts as the price of the
    model's product so far.
    """

    vehicle_type = forms.ChoiceField(label=_("Vehicle type"), choices=VehicleType.choices)
    price_per_km = forms.DecimalField(
        label=_("Price per kilometre (net)"), required=False, min_value=0, max_digits=8, decimal_places=2
    )
    trailer_surcharge_per_km = forms.DecimalField(
        label=_("Trailer surcharge per kilometre (net)"),
        required=False,
        min_value=0,
        max_digits=8,
        decimal_places=2,
        help_text=_("Added to the price per kilometre on trips with a trailer."),
    )
    trailer_billing = forms.ChoiceField(
        label=_("Trailer billed"), choices=TrailerBilling.choices, initial=TrailerBilling.DAY, required=False
    )
    price = forms.DecimalField(
        label=_("Price per day (net)"), required=False, min_value=0, max_digits=10, decimal_places=2
    )
    cost_per_km = forms.DecimalField(
        label=_("Internal cost per kilometre"), required=False, min_value=0, max_digits=8, decimal_places=2
    )
    cost_per_day = forms.DecimalField(
        label=_("Internal cost per day"), required=False, min_value=0, max_digits=8, decimal_places=2
    )

    def __init__(self, *args: Any, material_model: MaterialModel, rights: Rights, **kwargs: Any) -> None:
        old = material_model.default_product
        initial = kwargs.setdefault("initial", {})
        initial.setdefault("vehicle_type", VehicleType.CAR)
        if old is not None and old.price is not None:
            initial.setdefault("price", old.price)
        super().__init__(*args, **kwargs)
        self.material_model = material_model
        if not rights.has(SpecialRight.PRICES):
            for name in ("price_per_km", "trailer_surcharge_per_km", "price"):
                del self.fields[name]
        if not rights.has(SpecialRight.PURCHASE_PRICES):
            for name in ("cost_per_km", "cost_per_day"):
                del self.fields[name]
        car = f"vehicle_type={VehicleType.CAR}"
        trailer = f"vehicle_type={VehicleType.TRAILER}"
        if "price_per_km" in self.fields:
            mark_required(self.fields["price_per_km"], f"{car};{trailer}&trailer_billing={TrailerBilling.KM}")
        if "price" in self.fields:
            mark_required(self.fields["price"], f"{trailer}&trailer_billing={TrailerBilling.DAY}")
        #: ``data-show-if`` of the fields that depend on the type (LOG-005).
        self.conditions = {"car": car, "trailer": trailer}

    def values(self) -> dict[str, Any]:
        """The values for :func:`material.fleet.move_model_to_fleet` – only those of the chosen type."""
        data = self.cleaned_data
        is_car = data["vehicle_type"] == VehicleType.CAR
        values: dict[str, Any] = {
            "vehicle_type": data["vehicle_type"],
            "trailer_billing": data.get("trailer_billing") or TrailerBilling.DAY,
        }
        for name in ("price_per_km", "cost_per_km"):
            if name in self.fields:
                values[name] = data.get(name)
        if is_car and "trailer_surcharge_per_km" in self.fields:
            values["trailer_surcharge_per_km"] = data.get("trailer_surcharge_per_km")
        if not is_car:
            for name in ("price", "cost_per_day"):
                if name in self.fields:
                    values[name] = data.get(name)
        return values
