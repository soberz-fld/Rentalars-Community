# SPDX-License-Identifier: GPL-3.0-or-later
"""Forms of the custom fields (MAT-071, MAT-072, MAT-073).

* :class:`CustomFieldForm` and :class:`FieldsetForm` – Einstellungen → Eigene
  Felder and Feldsätze.
* :class:`FieldsetChoiceForm` – the fieldset in the form of a material model.
* :class:`CustomValuesForm` – the values of an item in the forms "Neue
  Exemplare" (also as a duplicate) and "Exemplar bearbeiten". It is a form
  of its own next to the item's form (prefix ``cf``), so that the forms of
  the material module stay as they are.

Required fields (UIX-035): editing an item, or creating one, needs every
required value. Creating several items at once may leave them empty – a
value typed applies to all new items; a unique field cannot be the same for
several items, so the page shows it only while one item is created
(``data-show-if="count=1"``).
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import Rights
from rentalars.core.forms import StyledForm, StyledModelForm, mark_required
from rentalars.customfields import services
from rentalars.customfields.models import (
    LONG_TEXT_LENGTH,
    TEXT_LENGTH,
    CustomField,
    Fieldset,
    FieldsetEntry,
    FieldType,
)
from rentalars.material.models import MaterialItem, MaterialModel

#: The condition under which the page script treats a required value as required: one item is created (UIX-035).
ONE_ITEM = "count=1"


class CustomFieldForm(StyledModelForm):
    """The definition of a custom field; the options of a choice list are typed one per line."""

    options = forms.CharField(
        label=_("Options"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text=_("For a choice list: one option per line, in the order the list offers them."),
    )

    class Meta:
        model = CustomField
        fields = [
            "name",
            "field_type",
            "unit",
            "options",
            "pattern",
            "help_text",
            "show_in_lists",
            "is_unique",
            "is_sensitive",
        ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["options"].initial = "\n".join(self.instance.choices or [])
        mark_required(self.fields["options"], "field_type=choice")
        self.fields["pattern"].widget.attrs.update({"spellcheck": "false", "autocomplete": "off"})
        self.style_fields()

    #: The model's errors about the options appear at the typed options.
    error_field_map = {"choices": "options"}

    def clean(self) -> dict[str, Any]:
        """The typed options become the list the field keeps; the model checks the rest, values included."""
        cleaned = super().clean() or {}
        lines = [line.strip() for line in (cleaned.get("options") or "").splitlines()]
        self.instance.choices = [line for line in lines if line]
        return cleaned


class FieldsetForm(StyledModelForm):
    """A fieldset: its name, and a row per custom field – part of it, its position, required."""

    class Meta:
        model = Fieldset
        fields = ["name", "description"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        existing = {entry.field_id: entry for entry in self.instance.entries.all()} if self.instance.pk else {}
        self.field_rows: list[dict[str, Any]] = []
        # The fields of the fieldset first, in their order; then the others by name.
        fields = sorted(
            CustomField.objects.order_by("name"),
            key=lambda field: (field.pk not in existing, existing[field.pk].position if field.pk in existing else 0),
        )
        for index, field in enumerate(fields, start=1):
            entry = existing.get(field.pk)
            use, position, required = f"use_{field.pk}", f"position_{field.pk}", f"required_{field.pk}"
            self.fields[use] = forms.BooleanField(label=field.name, required=False, initial=entry is not None)
            self.fields[position] = forms.IntegerField(
                label=_("Position of %(field)s") % {"field": field.name},
                min_value=1,
                max_value=999,
                required=False,
                initial=entry.position if entry is not None else index,
            )
            self.fields[required] = forms.BooleanField(
                label=_("%(field)s is required") % {"field": field.name},
                required=False,
                initial=entry.is_required if entry is not None else False,
            )
            self.field_rows.append({"field": field, "use": use, "position": position, "required": required})
        self.style_fields()

    @property
    def rows(self) -> list[dict[str, Any]]:
        """The rows of the table of fields, with their bound fields, for the template."""
        return [
            {
                "field": row["field"],
                "use": self[row["use"]],
                "position": self[row["position"]],
                "required": self[row["required"]],
            }
            for row in self.field_rows
        ]

    def save(self, commit: bool = True) -> Fieldset:
        """Save the fieldset and its fields: new ones are added, changed ones saved, removed ones deleted."""
        fieldset = super().save(commit=True)
        existing = {entry.field_id: entry for entry in fieldset.entries.all()}
        for row in self.field_rows:
            field = row["field"]
            entry = existing.get(field.pk)
            if not self.cleaned_data.get(row["use"]):
                if entry is not None:
                    entry.delete()
                continue
            position = self.cleaned_data.get(row["position"]) or 1
            required = bool(self.cleaned_data.get(row["required"]))
            if entry is None:
                FieldsetEntry.objects.create(fieldset=fieldset, field=field, position=position, is_required=required)
            elif (entry.position, entry.is_required) != (position, required):
                entry.position, entry.is_required = position, required
                entry.save()
        return fieldset


class FieldsetChoiceForm(StyledForm):
    """The fieldset in the form of a material model; a copy starts with that of its original (MAT-064)."""

    prefix = "cfs"

    fieldset = forms.ModelChoiceField(
        label=_("Fieldset"),
        queryset=Fieldset.objects.order_by("name"),
        required=False,
        empty_label=_("none"),
        help_text=_(
            "The custom fields every item of this model gets, e.g. MAC address or inspection sticker. "
            "Defined under Settings → Custom fields."
        ),
    )

    def __init__(
        self,
        *args: Any,
        material_model: MaterialModel | None = None,
        copy_of: MaterialModel | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        current = services.fieldset_of(material_model) or services.fieldset_of(copy_of)
        if current is not None:
            self.fields["fieldset"].initial = current.pk
        self.style_fields()

    @property
    def offered(self) -> bool:
        """Whether there is a fieldset to choose at all."""
        return Fieldset.objects.exists()

    def save(self, material_model: MaterialModel) -> bool:
        """Give the model the chosen fieldset; return whether it changed."""
        return services.assign_fieldset(material_model, self.cleaned_data.get("fieldset"))


def value_form_field(field: CustomField, *, required: bool) -> forms.Field:
    """The form field for the value of a custom field, by its type."""
    common: dict[str, Any] = {"label": field.label_with_unit, "required": required, "help_text": field.help_text}
    kind = field.field_type
    if kind == FieldType.CHOICE:
        return forms.ChoiceField(choices=[("", "–"), *[(option, option) for option in field.choices or []]], **common)
    if kind == FieldType.BOOLEAN:
        # "Not known" differs from "no", as with the category-specific fields (MAT-010).
        return forms.ChoiceField(choices=[("", "–"), ("yes", _("yes")), ("no", _("no"))], **common)
    if kind == FieldType.DATE:
        return forms.DateField(**common)
    if kind == FieldType.LONG_TEXT:
        return forms.CharField(max_length=LONG_TEXT_LENGTH, widget=forms.Textarea(attrs={"rows": 3}), **common)
    if kind == FieldType.NUMBER:
        return forms.CharField(max_length=60, widget=forms.TextInput(attrs={"inputmode": "decimal"}), **common)
    if kind == FieldType.URL:
        return forms.CharField(max_length=500, widget=forms.URLInput(), **common)
    if kind == FieldType.EMAIL:
        return forms.CharField(max_length=500, widget=forms.EmailInput(), **common)
    return forms.CharField(max_length=TEXT_LENGTH, **common)


class CustomValuesForm(StyledForm):
    """The values of an item's custom fields, next to the form of the item (prefix ``cf``).

    Args:
        material_model: The model of the item(s); its fieldset decides the fields.
        rights: The rights of the user: fields visible only with the right to see purchase prices are
            left out without it – and kept as they are (AUT-019).
        item: The item edited; ``None`` while items are created.
        copy_of: The item duplicated (MAT-064): its values fill the form, unique ones left out.
        several: The form for new items asks for a number of items (``count``): with more than one,
            required values may stay empty and unique ones must.
    """

    prefix = "cf"

    def __init__(
        self,
        data: Any = None,
        *args: Any,
        material_model: MaterialModel,
        rights: Rights,
        item: MaterialItem | None = None,
        copy_of: MaterialItem | None = None,
        several: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(data, *args, **kwargs)
        self.material_model = material_model
        self.item = item
        self.rights = rights
        self.several = several
        self.fieldset = services.fieldset_of(material_model)
        self.entries = services.visible_entries(material_model, rights)
        stored = services.stored_values(item) if item is not None else {}
        copied = services.stored_values(copy_of) if copy_of is not None else {}
        for entry in self.entries:
            field = entry.field
            name = self.field_name(field)
            form_field = value_form_field(field, required=entry.is_required and not several)
            if entry.is_required and several:
                mark_required(form_field, ONE_ITEM)  # the page script asks for it while one item is created
            text = stored.get(field.pk, "")
            if copy_of is not None and not field.is_unique:
                text = copied.get(field.pk, "")
            if text:
                form_field.initial = field.form_value(text)
            self.fields[name] = form_field
        self.style_fields()

    @staticmethod
    def field_name(field: CustomField) -> str:
        """The name of a field's input in the form (without the prefix)."""
        return f"f{field.pk}"

    @property
    def count(self) -> int:
        """How many items the form creates: the number typed in the item's form (``count``), else one."""
        if not self.several or not self.is_bound:
            return 1
        try:
            return max(1, int(str(self.data.get("count") or 1)))
        except (TypeError, ValueError):
            return 1

    @property
    def rows(self) -> list[dict[str, Any]]:
        """The fields for the template: bound field, definition, whether it shows only for one item."""
        return [
            {
                "field": self[self.field_name(entry.field)],
                "definition": entry.field,
                "wide": entry.field.field_type == FieldType.LONG_TEXT,
                "only_one": self.several and entry.field.is_unique,
            }
            for entry in self.entries
        ]

    def clean(self) -> dict[str, Any]:
        """Check each value against its field; required and unique values as the number of items allows."""
        cleaned = super().clean() or {}
        self.values: dict[CustomField, str] = {}
        many = self.count > 1
        for entry in self.entries:
            field = entry.field
            name = self.field_name(field)
            if name in self.errors:
                continue
            raw = cleaned.get(name)
            try:
                text = field.clean_value(raw)
                if many and field.is_unique and text:
                    raise ValidationError(
                        _("A unique field cannot get the same value for several items. Leave it empty here.")
                    )
                services.check_unique(field, text, item=self.item, rights=self.rights)
            except ValidationError as error:
                self.add_error(name, error)
                continue
            if entry.is_required and not text and not many:
                self.add_error(name, forms.Field.default_error_messages["required"])
                continue
            self.values[field] = text
        return cleaned

    def save(self, items: list[MaterialItem]) -> list[MaterialItem]:
        """Store the values for the items; return the items that still lack a required value.

        Only the fields of the form are touched: a sensitive field the user
        does not see keeps its value.
        """
        values = getattr(self, "values", {})
        if self.item is None:
            values = {field: text for field, text in values.items() if text}  # new items: nothing to empty
        missing = []
        for item in items:
            services.store_values(item, values)
            if services.missing_required(item):
                missing.append(item)
        return missing
