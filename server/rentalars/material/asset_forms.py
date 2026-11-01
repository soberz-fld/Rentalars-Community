# SPDX-License-Identifier: GPL-3.0-or-later
"""Forms of the asset data of an item and of the sale from stock (MAT-086)."""

from __future__ import annotations

import datetime
from typing import Any

from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import Module, Rights
from rentalars.core.forms import StyledForm
from rentalars.customers.models import Customer
from rentalars.masterdata.models import TaxRate
from rentalars.material.models import AssetKind, MaterialItem
from rentalars.material.purchase_forms import AmountField

#: The kinds an item can be recorded as; empty takes the item out of the books.
KIND_CHOICES = [("", _("– not recorded as asset –")), *AssetKind.choices]


class AssetDataForm(StyledForm):
    """Record an item as merchandise, low-value asset (GWG) or fixed asset, with its useful life and acquisition cost."""

    asset_kind = forms.ChoiceField(label=_("Kind of asset"), choices=KIND_CHOICES, required=False)
    useful_life_months = forms.IntegerField(
        label=_("Useful life (months)"),
        required=False,
        min_value=1,
        max_value=600,
        help_text=_("Only for a fixed asset. Empty: the standard useful life of the settings."),
    )
    ancillary_cost_net = AmountField(
        label=_("Ancillary acquisition cost (net)"),
        required=False,
        max_digits=10,
        decimal_places=2,
        help_text=_("Freight, packaging, customs … that belong to this item; a share of a discount is negative."),
    )
    acquisition_cost_net = AmountField(
        label=_("Acquisition cost (net)"),
        required=False,
        min_value=0,
        max_digits=10,
        decimal_places=2,
        help_text=_("Purchase price plus ancillary cost. Empty: worked out from the purchase price of the item."),
    )

    def __init__(self, *args: Any, item: MaterialItem, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.item = item
        if not self.is_bound:
            self.initial = {
                "asset_kind": item.asset_kind,
                "useful_life_months": item.useful_life_months,
                "ancillary_cost_net": item.ancillary_cost_net,
                "acquisition_cost_net": item.acquisition_cost_net if item.acquisition_cost_net is not None else None,
            }


class SaleForm(StyledForm):
    """Sell an item – or a quantity of bulk material – out of the stock: day, buyer, net price, tax rate, note."""

    sold_on = forms.DateField(label=_("Day of the sale"))
    quantity = forms.IntegerField(
        label=_("Quantity"), min_value=1, initial=1, help_text=_("How many pieces of this bulk material are sold.")
    )
    customer = forms.ModelChoiceField(
        label=_("Customer"),
        queryset=Customer.objects.none(),
        required=False,
        widget=forms.HiddenInput,
        help_text=_("A customer of the master data – or type the name of the buyer below."),
    )
    buyer_name = forms.CharField(
        label=_("Name of the buyer"),
        required=False,
        max_length=200,
        help_text=_("Empty: the name of the customer. A name typed here is kept as written."),
    )
    net_price = AmountField(label=_("Price (net)"), min_value=0, max_digits=12, decimal_places=2)
    tax_rate = forms.ModelChoiceField(label=_("Tax rate"), queryset=TaxRate.objects.none(), empty_label=None)
    note = forms.CharField(label=_("Note"), required=False, widget=forms.Textarea(attrs={"rows": 3}))
    accept_warnings = forms.BooleanField(label=_("Sell it anyway"), required=False)

    def __init__(self, *args: Any, item: MaterialItem, rights: Rights, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.item = item
        self.fields["tax_rate"].queryset = TaxRate.objects.filter(is_active=True)
        if not self.is_bound:
            self.initial.setdefault("sold_on", timezone.localdate())
            default = TaxRate.get_default()
            if default is not None:
                self.initial.setdefault("tax_rate", default.pk)
        if rights.can_read(Module.CUSTOMERS):
            self.fields["customer"].queryset = Customer.objects.filter(is_active=True)
        else:
            del self.fields["customer"]  # the names of customers are not for who may not read them
        if not item.material_model.is_bulk:
            del self.fields["quantity"]
        self.fields["note"].help_text = _("For yourself and your colleagues, e.g. why it was sold.")

    @property
    def customer_text(self) -> str:
        """What the customer field shows: the name of the chosen customer."""
        customer = self.initial.get("customer") if not self.is_bound else self.data.get("customer")
        if isinstance(customer, Customer):
            return customer.name
        if customer and str(customer).isdigit():
            found = Customer.objects.filter(pk=int(customer)).first()
            return found.name if found else ""
        return ""

    def clean_sold_on(self) -> datetime.date:
        """A day of the past or today."""
        day = self.cleaned_data["sold_on"]
        if day > timezone.localdate():
            raise forms.ValidationError(_("The day of the sale lies in the future."))
        return day

    def clean(self) -> dict[str, Any]:
        """The buyer: a customer chosen or a name typed."""
        cleaned = super().clean() or {}
        if not (cleaned.get("buyer_name") or "").strip() and not cleaned.get("customer"):
            self.add_error("buyer_name", _("Say who buys: choose a customer or type a name."))
        return cleaned

    def values(self) -> dict[str, Any]:
        """The checked values for :func:`rentalars.material.sales.preview` and ``sell``."""
        cleaned = self.cleaned_data
        return {
            "sold_on": cleaned["sold_on"],
            "quantity": cleaned.get("quantity") or 1,
            "net_price": cleaned["net_price"],
            "tax_rate": cleaned["tax_rate"],
        }

    def buyer(self) -> dict[str, Any]:
        """The buyer for :func:`rentalars.material.sales.sell`."""
        cleaned = self.cleaned_data
        return {"customer": cleaned.get("customer"), "buyer_name": cleaned.get("buyer_name") or ""}
