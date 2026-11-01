# SPDX-License-Identifier: GPL-3.0-or-later
"""Forms of subrentals: the supplier field (PRJ-101) and the page "Zumietung bei …" (PRJ-106).

The supplier of a subrental is chosen by typing, with suggestions, like the
customer of a project (PRJ-070). :class:`SupplierTypeahead` renders the text
field and the hidden field the page script (``data-typeahead`` in
``static/js/app.js``) works with; the last suggestion creates a supplier of
the typed name in a dialog (:class:`SupplierQuickForm`). Inside the dialog of
a line, that dialog opens over it.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django import forms
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from rentalars.core.forms import StyledForm, StyledModelForm
from rentalars.masterdata.models import Supplier
from rentalars.projects.models import MaterialLine, SubrentalStatus, SupplierDocumentKind


class SupplierTypeahead(forms.Widget):
    """A supplier, typed with suggestions instead of chosen from a long list (PRJ-101).

    The label of the field points to the visible text field; the ID of the
    supplier goes in the hidden field of the same name as the form field.
    """

    #: The address of the suggestions, as a URL name.
    url_name = "projects:supplier_suggest"

    def id_for_label(self, id_: str | None) -> str | None:
        """The label belongs to the text field the user types in."""
        return f"{id_}_text" if id_ else id_

    def value_from_datadict(self, data: Any, files: Any, name: str) -> Any:
        """The ID from the hidden field."""
        return data.get(name)

    def format_value(self, value: Any) -> str:
        """The ID of the supplier, or nothing."""
        if value in (None, ""):
            return ""
        return str(getattr(value, "pk", value))

    def render(self, name: str, value: Any, attrs: dict[str, Any] | None = None, renderer: Any = None) -> str:
        """The text field with the name of the supplier and the hidden field with its ID."""
        final = self.build_attrs(self.attrs, attrs)
        element_id = final.get("id") or f"id_{name}"
        pk = self.format_value(value)
        text = Supplier.objects.filter(pk=int(pk)).values_list("name", flat=True).first() if pk.isdigit() else ""
        described = format_html(' aria-describedby="{}_help"', element_id) if final.get("data-described") else ""
        return format_html(
            '<div class="typeahead" data-typeahead data-url="{url}">'
            '<input type="search" id="{id}_text" data-typeahead-input value="{text}" placeholder="{placeholder}"'
            ' autocomplete="off"{described}>'
            '<input type="hidden" name="{name}" id="{id}" value="{pk}" data-typeahead-value>'
            "</div>",
            url=reverse(self.url_name),
            id=element_id,
            text=text or "",
            placeholder=_("Name, contact or e-mail"),
            described=described,
            name=name,
            pk=pk,
        )


def supplier_field(current: Supplier | None) -> forms.ModelChoiceField:
    """The supplier of a subrental: an active one, or the one the line has (PRJ-101)."""
    queryset = Supplier.objects.filter(is_active=True)
    if current is not None:
        queryset = queryset | Supplier.objects.filter(pk=current.pk)
    return forms.ModelChoiceField(
        label=_("Supplier"),
        queryset=queryset,
        required=False,
        widget=SupplierTypeahead(attrs={"data-described": "1"}),
        help_text=_("Type to search. A supplier not known yet can be created right there."),
    )


def subrental_status_field(*, required: bool = True) -> forms.ChoiceField:
    """The field "Status" of a subrental, "open" first (PRJ-101)."""
    return forms.ChoiceField(
        label=_("Status"),
        choices=SubrentalStatus.choices,
        required=required,
        initial=SubrentalStatus.OPEN,
        help_text=_("Without a supplier it stays “open”."),
    )


def check_subrental_status(form: forms.Form, name: str) -> None:
    """PRJ-101: every status but "open" needs a supplier – the error stands at the status."""
    status = form.cleaned_data.get(name)
    if status and status != SubrentalStatus.OPEN and form.cleaned_data.get("supplier") is None:
        if "supplier" not in form.errors:
            form.add_error(name, _("Without a supplier the status can only be “open”."))


class SupplierQuickForm(StyledModelForm):
    """A new supplier in a dialog, from the supplier field of a subrental (PRJ-101)."""

    class Meta:
        model = Supplier
        fields = ["name", "contact", "email", "phone", "customer_number"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("autocomplete", "off")
        self.fields["email"].widget.attrs["autocomplete"] = "off"

    def clean_name(self) -> str:
        """A supplier of the same name – also in other case – exists only once."""
        name = (self.cleaned_data.get("name") or "").strip()
        if Supplier.objects.filter(name__iexact=name).exists():
            raise forms.ValidationError(_("There is a supplier of this name already."))
        return name


class SupplierDocumentForm(StyledForm):
    """Upload a document of the supplier: offer, order confirmation, delivery note, invoice … (PRJ-106)."""

    file = forms.FileField(label=_("File"))
    kind = forms.ChoiceField(label=_("Kind of document"), choices=SupplierDocumentKind.choices)
    title = forms.CharField(label=_("Title"), max_length=200, required=False)


class SubrentalLinesForm(StyledForm):
    """Status and purchase price of every subrental of a supplier in a project, at once (PRJ-106).

    PRJ-097: and whether it is picked up at the supplier – then the trips of
    the project fetch it at packing and bring it back at the follow-up work.
    """

    def __init__(self, *args: Any, lines: list[MaterialLine], with_prices: bool, **kwargs: Any) -> None:
        self.lines = lines
        super().__init__(*args, **kwargs)
        for line in lines:
            what = f"{line.quantity_display} × {line.title}"
            self.fields[f"status_{line.pk}"] = forms.ChoiceField(
                label=_("Status"),
                choices=SubrentalStatus.choices,
                initial=line.subrental_status or SubrentalStatus.OPEN,
                widget=forms.Select(attrs={"aria-label": f"{_('Status')}: {what}"}),
            )
            self.fields[f"pickup_{line.pk}"] = forms.BooleanField(
                label=_("Picked up at the supplier"),
                required=False,
                initial=line.picked_up_at_supplier,
                widget=forms.CheckboxInput(attrs={"aria-label": f"{_('Picked up at the supplier')}: {what}"}),
            )
            if with_prices:
                self.fields[f"price_{line.pk}"] = forms.DecimalField(
                    label=_("Purchase price per unit"),
                    min_value=0,
                    decimal_places=2,
                    required=False,
                    initial=line.purchase_price,
                    widget=forms.TextInput(attrs={"aria-label": f"{_('Purchase price per unit')}: {what}"}),
                )
        self.style_fields()
        for field in self.fields.values():
            field.widget.attrs.setdefault("autocomplete", "off")

    def status_field(self, line: MaterialLine) -> forms.BoundField:
        """The status field of a line."""
        return self[f"status_{line.pk}"]

    def pickup_field(self, line: MaterialLine) -> forms.BoundField:
        """PRJ-097: the field "picked up at the supplier" of a line."""
        return self[f"pickup_{line.pk}"]

    def price_field(self, line: MaterialLine) -> forms.BoundField | None:
        """The purchase price field of a line, if the user may see purchase prices."""
        name = f"price_{line.pk}"
        return self[name] if name in self.fields else None

    def values(self) -> dict[int, dict[str, Any]]:
        """Per line status, pickup and – if shown – the purchase price, as ``update_lines`` takes them."""
        result: dict[int, dict[str, Any]] = {}
        for line in self.lines:
            wanted: dict[str, Any] = {
                "subrental_status": self.cleaned_data[f"status_{line.pk}"],
                "picked_up_at_supplier": self.cleaned_data[f"pickup_{line.pk}"],
            }
            if f"price_{line.pk}" in self.cleaned_data:
                price: Decimal | None = self.cleaned_data[f"price_{line.pk}"]
                wanted["purchase_price"] = price
            result[line.pk] = wanted
        return result
