# SPDX-License-Identifier: GPL-3.0-or-later
"""Forms of the incoming invoices: upload, head, positions, booking in and the settings (DOK-023, DOK-024)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.forms import modelformset_factory
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import Rights
from rentalars.core.forms import StyledForm, StyledModelForm, mark_required
from rentalars.incoming import booking, services
from rentalars.incoming.models import (
    MAX_POSITIONS,
    IncomingInvoice,
    InvoicePosition,
    InvoiceStatus,
    PositionType,
)
from rentalars.incoming.services import split_amount
from rentalars.masterdata.models import TaxAccount
from rentalars.material import purchases
from rentalars.material.asset_models import AssetSettings
from rentalars.material.models import AssetKind, TrackingMode
from rentalars.material.purchase_forms import AmountField, PositionForm


def trimmed(value: Decimal | None, places: int = 2) -> Decimal | None:
    """A decimal without needless zeros but with at least ``places`` places: 99.0000 → 99.00, 2.500 → 2.50."""
    if value is None:
        return None
    text = format(value.normalize(), "f")
    have = len(text.partition(".")[2])
    return value.quantize(Decimal(1).scaleb(-max(have, places)))


class UploadForm(StyledForm):
    """The file of a new incoming invoice: a PDF or a picture."""

    file = forms.FileField(
        label=_("Invoice file"),
        help_text=_(
            "A PDF, a picture (PNG, JPEG, WEBP) or an XML e-invoice (XRechnung, ZUGFeRD / Factur-X). An e-invoice is "
            "read exactly; of a PDF only a text can be read, a scan or a picture is kept and entered by hand."
        ),
        widget=forms.ClearableFileInput(
            attrs={"accept": ".pdf,application/pdf,image/png,image/jpeg,image/webp,.xml,application/xml,text/xml"}
        ),
    )


class HeadForm(StyledModelForm):
    """The head of an invoice: supplier, number, dates, currency, amounts, how ancillary costs are spread, status, note."""

    supplier_name = forms.CharField(
        label=_("Supplier"),
        required=False,
        max_length=120,
        help_text=_("Choose a supplier or type the name: a name not in the master data can be created with one click."),
    )
    total_net = AmountField(label=_("Total net"), required=False, max_digits=12, decimal_places=2)
    total_tax = AmountField(label=_("Tax"), required=False, max_digits=12, decimal_places=2)
    total_gross = AmountField(label=_("Total gross"), required=False, max_digits=12, decimal_places=2)

    class Meta:
        model = IncomingInvoice
        fields = (
            "supplier_name",
            "invoice_number",
            "invoice_date",
            "due_date",
            "currency",
            "exchange_rate",
            "total_net",
            "total_tax",
            "total_gross",
            "allocation_key",
            "status",
            "note",
        )
        widgets = {"note": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["invoice_number"].widget.attrs["autocomplete"] = "off"
        self.fields["currency"].widget.attrs.update({"maxlength": 3, "autocapitalize": "characters"})
        self.fields["note"].label = _("Note")
        self.fields["note"].help_text = _("Free text for yourself and your colleagues, e.g. why it was bought.")
        if self.instance.pk:
            self.initial["supplier_name"] = self.instance.supplier_label
            # What the items were made with is shown, not changed (services.SpreadLock).
            for name in services.spread_lock(self.instance).head:
                self.fields[name].disabled = True
            # Changing the key shows the ancillary costs spread that way at once; nothing is saved by that.
            self.fields["allocation_key"].widget.attrs.update(
                {
                    "hx-get": reverse("incoming:costing", args=[self.instance.pk]),
                    "hx-trigger": "change",
                    "hx-target": "#costing",
                    "hx-swap": "outerHTML",
                }
            )

    @staticmethod
    def fields_total_net() -> AmountField:
        """The field that reads the total net as typed (the page asks for the sum while typing)."""
        return HeadForm.base_fields["total_net"]

    def clean_currency(self) -> str:
        """Three letters, upper case: EUR, USD."""
        text = (self.cleaned_data.get("currency") or "").strip().upper()
        if len(text) != 3 or not text.isalpha():
            raise forms.ValidationError(_("Enter the three-letter code of the currency, e.g. EUR."))
        return text

    def values(self) -> dict[str, Any]:
        """The checked values for :func:`rentalars.incoming.services.update_head`."""
        return {name: self.cleaned_data[name] for name in self.Meta.fields if name in self.cleaned_data}


class PositionRowForm(StyledModelForm):
    """One *Kontierung* of a document: description, tax account, kind, net amount, tax rate.

    The document is split over tax accounts by what its positions are. Quantity, article number and manufacturer are
    not asked here – they stay as the reading found them and are used and changed when the goods are booked
    in. The net amount is the amount of the whole position (quantity × unit price): changed, the unit price follows
    (:func:`split_amount`). The kind of asset belongs to goods only, the useful life to a fixed asset only.
    """

    amount_net = AmountField(
        label=_("Net amount"),
        required=False,
        max_digits=12,
        decimal_places=2,
        help_text=_("In the currency of the invoice. For ancillary cost: the amount; a discount is negative."),
    )
    tax_rate = AmountField(
        label=_("Tax rate (%)"), required=False, min_value=0, max_value=100, max_digits=5, decimal_places=2
    )
    weight_kg = AmountField(
        label=_("Weight of one piece (kg)"),
        required=False,
        min_value=0,
        max_digits=8,
        decimal_places=3,
        help_text=_("Only to spread ancillary costs by weight. Empty: the weight of the model."),
    )

    class Meta:
        model = InvoicePosition
        fields = (
            "description",
            "tax_account",
            "position_type",
            "tax_rate",
            "asset_kind",
            "useful_life_months",
            "weight_kg",
        )

    def __init__(self, *args: Any, lock: services.SpreadLock | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["asset_kind"].choices = [("", _("by the limit of the settings")), *AssetKind.choices]
        self.fields["asset_kind"].label = _("Treated as")
        self.fields["position_type"].label = _("Kind")
        accounts = TaxAccount.objects.filter(is_active=True)
        if self.instance.pk and self.instance.tax_account_id:
            accounts = TaxAccount.objects.filter(Q(is_active=True) | Q(pk=self.instance.tax_account_id))
        self.fields["tax_account"].queryset = accounts.order_by("number")
        self.fields["tax_account"].empty_label = _("– not chosen –")
        self.fields["tax_account"].required = False
        for name in ("tax_rate", "weight_kg"):
            instance = getattr(self.instance, name, None)
            if self.instance.pk and instance is not None:
                self.initial[name] = trimmed(instance, 0 if name == "weight_kg" else 2)
        if self.instance.pk and self.instance.line_net is not None:
            self.initial["amount_net"] = self.instance.line_net
        self.fields["description"].widget.attrs["autocomplete"] = "off"
        mark_required(self.fields["description"])
        locked: set[str] = set()
        if self.instance.pk and self.instance.items.exists():
            # The items were made with these values: they are shown, not changed (services.LOCKED_WHEN_BOOKED).
            locked |= {"quantity", "unit_price_net", "position_type"}
        if self.instance.pk and lock is not None:
            # The figures the ancillary costs were spread by stay once items were made.
            locked |= set(lock.position_fields(self.instance.position_type))
        for name in locked & set(self.fields):
            self.fields[name].disabled = True
        if locked & {"quantity", "unit_price_net"}:
            self.fields["amount_net"].disabled = True
        self.booked = bool(self.instance.pk and self.instance.items.exists())

    @property
    def shows_asset(self) -> bool:
        """Whether the kind of asset is offered: only for goods."""
        return (self["position_type"].value() or PositionType.GOODS) == PositionType.GOODS

    @property
    def shows_useful_life(self) -> bool:
        """Whether the useful life is offered: only where the kind of asset is “fixed asset” (and for goods)."""
        return self.shows_asset and self["asset_kind"].value() == AssetKind.FIXED_ASSET

    def values(self) -> dict[str, Any]:
        """The checked values for :func:`rentalars.incoming.services.update_position` and ``add_position``."""
        values = {name: self.cleaned_data[name] for name in self.Meta.fields if name in self.cleaned_data}
        if "amount_net" in self.changed_data and not self.fields["amount_net"].disabled:
            quantity = self.instance.quantity if self.instance.pk else Decimal("1")
            values["quantity"], values["unit_price_net"] = split_amount(self.cleaned_data.get("amount_net"), quantity)
        return values


class BasePositionFormSet(forms.BaseModelFormSet):
    """The positions of an invoice; at most :data:`MAX_POSITIONS`."""

    def clean(self) -> None:
        """Not more positions than an invoice may have."""
        super().clean()
        if len(self.forms) > MAX_POSITIONS:
            raise ValidationError(_("At most %(count)d positions per invoice.") % {"count": MAX_POSITIONS})


def position_formset(invoice: IncomingInvoice, data: Any = None, *, extra: int = 0) -> forms.BaseModelFormSet:
    """The positions of an invoice as a formset (prefix ``pos``), ``extra`` empty rows at the end."""
    factory = modelformset_factory(
        InvoicePosition,
        form=PositionRowForm,
        formset=BasePositionFormSet,
        extra=extra,
        can_delete=True,
        max_num=MAX_POSITIONS,
    )
    return factory(
        data,
        queryset=invoice.positions.order_by("place", "pk"),
        prefix="pos",
        form_kwargs={"lock": services.spread_lock(invoice)},
    )


class StatusForm(StyledForm):
    """The status of an invoice: open, checked, booked in."""

    status = forms.ChoiceField(label=_("Status"), choices=InvoiceStatus.choices)


# --- Booking in ---------------------------------------------------------------------------------------------------


class BookingRowForm(PositionForm):
    """One goods position when booking in: the model, how many, where to, the kind of asset and its useful life.

    It is the row of "Kauf einpflegen" (:class:`rentalars.material.purchase_forms.PositionForm`) without prices – they
    come from the invoice – and with the kind of asset, the useful life and the box "book again" for a position that
    is booked in already.
    """

    position = forms.IntegerField(widget=forms.HiddenInput)
    include = forms.BooleanField(label=_("Book in this position"), required=False, initial=True)
    book_again = forms.BooleanField(
        label=_("Book in again"),
        required=False,
        help_text=_("This position is booked in already. Tick to make more items of it."),
    )
    keep_as_quantity = forms.BooleanField(
        label=_("Keep as a quantity (bulk material)"),
        required=False,
        help_text=_("For a new model: one row with the number of pieces instead of single items."),
    )
    asset_kind = forms.ChoiceField(label=_("Kind of asset"), required=False)
    useful_life_months = forms.IntegerField(
        label=_("Useful life (months)"),
        required=False,
        min_value=1,
        max_value=600,
        help_text=_("For a fixed asset. Empty: the standard useful life of the settings."),
    )

    def __init__(self, *args: Any, rights: Rights, shared: dict[str, Any] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, rights=rights, shared=shared, **kwargs)
        for name in ("unit_price", "price_for_set", "confirmed", "source", "candidates", "hint"):
            self.fields.pop(name, None)
        self.fields["asset_kind"].choices = [("", _("– choose –")), *AssetKind.choices]
        self.fields["count"].label = _("Number of pieces")
        self.fields["count"].required = False

    def clean(self) -> dict[str, Any]:
        """A position that is not booked in is not checked; for the others the checks of the purchase row."""
        if not self.cleaned_data.get("include"):
            self.cleaned_data["model"] = None
            return self.cleaned_data
        cleaned = super().clean()
        cleaned["position_pk"] = cleaned.get("position")
        return cleaned

    def entry(self, position: Any) -> booking.Entry:
        """The decision of the row as an entry for :func:`rentalars.incoming.booking.plan`."""
        data = self.cleaned_data
        new_model = None
        if data.get("model") is None:
            new_model = purchases.NewModel(
                name=data["model_name"].strip(),
                category=data["category_object"],
                manufacturer=data.get("manufacturer_name", ""),
                product=data.get("product"),
                tracking_mode=TrackingMode.BULK if data.get("keep_as_quantity") else "",
            )
        return booking.Entry(
            position=position,
            model=data.get("model"),
            new_model=new_model,
            count=data.get("count"),
            storage_location=data.get("storage_location"),
            serial_numbers=data.get("serial_list") or [],
            book_again=bool(data.get("book_again")),
        )


class BaseBookingFormSet(forms.BaseFormSet):
    """The rows of the booking page; one per goods position, none added or removed."""

    def initial_form_count(self) -> int:
        """Every row is shown with its values as initial data."""
        return super().initial_form_count() if self.is_bound else len(self.initial or [])


def booking_formset(data: Any = None, *, rights: Rights, rows: list[dict[str, Any]] | None = None) -> forms.BaseFormSet:
    """The rows of the booking page, bound to what was sent or filled with ``rows``."""
    from rentalars.material.purchase_forms import shared_choices

    factory = forms.formset_factory(BookingRowForm, formset=BaseBookingFormSet, extra=0, max_num=MAX_POSITIONS)
    kwargs = {"rights": rights, "shared": shared_choices()}
    if data is not None:
        return factory(data, prefix="pos", form_kwargs=kwargs)
    return factory(initial=rows or [], prefix="pos", form_kwargs=kwargs)


class SettingsForm(StyledModelForm):
    """Einstellungen → Eingangsrechnungen: the limit of a low-value asset and the standard useful life."""

    low_value_limit_net = AmountField(
        label=_("Limit of a low-value asset (GWG), net"), min_value=0, max_digits=10, decimal_places=2
    )

    class Meta:
        model = AssetSettings
        fields = ("low_value_limit_net", "default_useful_life_months", "keep_memory_value")  # + memory value
