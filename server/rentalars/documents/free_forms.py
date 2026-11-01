# SPDX-License-Identifier: GPL-3.0-or-later
"""Forms of the outgoing documents without a project: the dialog "Neuer Ausgangsbeleg", the draft, its lines."""

from __future__ import annotations

import datetime
import json
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _

from rentalars.core.forms import StyledForm
from rentalars.customers.models import AddressKind, Contact, Customer, CustomerAddress
from rentalars.documents import free, services
from rentalars.documents.models import DocumentDraft, DocumentKind
from rentalars.masterdata.models import TaxRate, Unit
from rentalars.products.models import Product


def _customer_id(form: forms.BaseForm) -> int | None:
    """The customer the form is about: the one typed (bound), else the one given as initial value."""
    value = form.data.get("customer") if form.is_bound else form.initial.get("customer")
    if hasattr(value, "pk"):
        value = value.pk
    return int(value) if str(value or "").isdigit() else None


class NewDocumentForm(StyledForm):
    """The dialog "Neuer Ausgangsbeleg": kind and customer – and what is known right away.

    The customer is typed with suggestions (``customers:suggest``); the billing address and the contact follow the
    customer chosen (``dependants_for`` says which customer they were offered for, as in the form of a project).
    """

    kind = forms.ChoiceField(label=_("Document"))
    customer = forms.ModelChoiceField(label=_("Customer"), queryset=Customer.objects.none(), widget=forms.HiddenInput)
    dependants_for = forms.CharField(required=False, widget=forms.HiddenInput)
    billing_address = forms.ModelChoiceField(
        label=_("Billing address"),
        queryset=CustomerAddress.objects.none(),
        required=False,
        empty_label=_("– address of the customer –"),
    )
    contact = forms.ModelChoiceField(
        label=_("Contact"), queryset=Contact.objects.none(), required=False, empty_label=_("– nobody –")
    )
    issued_on = forms.DateField(label=_("Date"), required=False, help_text=_("Empty: the day the document is issued."))
    payment_terms_days = forms.IntegerField(
        label=_("Payment terms in days"),
        required=False,
        min_value=0,
        max_value=365,
        help_text=_("Empty: as for the customer, else as in the company settings."),
    )
    valid_until = forms.DateField(
        label=_("Valid until"), required=False, help_text=_("Empty: as many days as the template of the offer says.")
    )
    reference = forms.CharField(
        label=_("Reference"),
        required=False,
        max_length=200,
        help_text=_("Printed as subject line, e.g. “Hire of a PA system for the summer party”."),
    )
    print_product_descriptions = forms.BooleanField(
        label=_("Print the description of the products"),
        required=False,
        help_text=_("The description of each product stands under its position."),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        kinds = free.free_kinds()
        self.fields["kind"].choices = [(kind.value, capfirst(kind.label)) for kind in kinds]
        self.fields["customer"].queryset = Customer.objects.filter(is_active=True, anonymised_at__isnull=True)
        # The choice of each kind's template; the box starts with that of the kind shown first.
        defaults = {kind.value: services.template_for(kind.value).print_product_descriptions for kind in kinds}
        self.description_defaults = defaults
        wanted = self.data.get("kind") if self.is_bound else self.initial.get("kind")
        first = wanted or (kinds[0].value if kinds else "")
        box = self.fields["print_product_descriptions"]
        box.initial = defaults.get(first, False)
        box.widget.attrs["data-description-defaults"] = json.dumps(defaults)
        self.fields["issued_on"].initial = None
        customer_id = _customer_id(self)
        #: The customer whose addresses and contacts are offered; sent back as "dependants_for".
        self.dependants_for = customer_id or ""
        self.fields["dependants_for"].initial = self.dependants_for
        addresses = CustomerAddress.objects.filter(customer_id=customer_id, kind=AddressKind.BILLING)
        contacts = Contact.objects.filter(customer_id=customer_id)
        self.fields["billing_address"].queryset = addresses
        self.fields["contact"].queryset = contacts
        self.has_addresses = bool(customer_id) and addresses.exists()
        self.has_contacts = bool(customer_id) and contacts.exists()
        if not self.has_addresses:
            self.fields["billing_address"].widget = forms.HiddenInput()
        if not self.has_contacts:
            self.fields["contact"].widget = forms.HiddenInput()
        self._follow_customer(customer_id)

    def _follow_customer(self, customer_id: int | None) -> None:
        """A customer chosen later than the address and contact were offered: the customer's defaults take their place."""
        customer = Customer.objects.filter(pk=customer_id).first() if customer_id else None
        changed = str(self.data.get("dependants_for", "")) != str(customer_id or "")
        if self.is_bound and not changed:
            return
        if self.is_bound:
            self.data = self.data.copy()
        elif self.initial.get("dependants_for") and str(self.initial["dependants_for"]) == str(customer_id or ""):
            return  # the dialog is opened again for the same customer: what was chosen stays
        address = customer.default_address(AddressKind.BILLING) if customer is not None else None
        contact = customer.primary_contact if customer is not None else None
        target = self.data if self.is_bound else self.initial
        target["billing_address"] = str(address.pk) if address is not None else ""
        target["contact"] = str(contact.pk) if contact is not None else ""

    def clean(self) -> dict[str, Any]:
        """Check what depends on the kind, with the rules of the draft (``free``)."""
        cleaned = super().clean()
        customer = cleaned.get("customer")
        if customer is not None:
            try:
                free.check_customer(customer)
            except ValidationError as error:
                self.add_error("customer", error)
        kind = cleaned.get("kind")
        # The fields of other kinds are hidden by the page but still sent: what does not belong to the kind is left out.
        if kind != DocumentKind.INVOICE:
            cleaned["payment_terms_days"] = None
        if kind != DocumentKind.OFFER:
            cleaned["valid_until"] = None
        return cleaned

    def create(self, user: Any) -> DocumentDraft:
        """Make the draft of the cleaned data (``free.create_draft``).

        Raises:
            ValidationError: Something stops the draft; the view shows it on the form.
        """
        data = self.cleaned_data
        return free.create_draft(
            data["customer"],
            data["kind"],
            user=user,
            billing_address=data.get("billing_address"),
            contact=data.get("contact"),
            issued_on=data.get("issued_on"),
            payment_terms_days=data.get("payment_terms_days"),
            valid_until=data.get("valid_until"),
            reference=data.get("reference") or "",
            print_product_descriptions=bool(data.get("print_product_descriptions")),
        )

    @property
    def customer_text(self) -> str:
        """What the customer field shows: the name of the chosen customer."""
        customer_id = _customer_id(self)
        customer = Customer.objects.filter(pk=customer_id).first() if customer_id else None
        return customer.name if customer is not None else ""


class DraftForm(StyledForm):
    """The header and the texts of a draft: address, contact, date, terms, reference, texts, text blocks."""

    billing_address = forms.ModelChoiceField(
        label=_("Billing address"),
        queryset=CustomerAddress.objects.none(),
        required=False,
        empty_label=_("– address of the customer –"),
    )
    contact = forms.ModelChoiceField(
        label=_("Contact"), queryset=Contact.objects.none(), required=False, empty_label=_("– nobody –")
    )
    issued_on = forms.DateField(label=_("Date"), required=False, help_text=_("Empty: the day the document is issued."))
    payment_terms_days = forms.IntegerField(
        label=_("Payment terms in days"),
        required=False,
        min_value=0,
        max_value=365,
        help_text=_("Empty: as for the customer, else as in the company settings."),
    )
    valid_until = forms.DateField(
        label=_("Valid until"), required=False, help_text=_("Empty: as many days as the template of the offer says.")
    )
    service_start = forms.DateField(
        label=_("Service from"), required=False, help_text=_("Empty: the service is dated like the invoice.")
    )
    service_end = forms.DateField(label=_("Service until"), required=False)
    reference = forms.CharField(
        label=_("Reference"),
        required=False,
        max_length=200,
        help_text=_("Printed as subject line, e.g. “Hire of a PA system for the summer party”."),
    )
    introduction = forms.CharField(
        label=_("Introduction"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_("Placeholders: {customer}, {due_date}, {payment_terms}, {valid_until}."),
    )
    closing = forms.CharField(label=_("Closing text"), required=False, widget=forms.Textarea(attrs={"rows": 3}))
    text_blocks = forms.MultipleChoiceField(label=_("Text blocks"), required=False, widget=forms.CheckboxSelectMultiple)
    print_product_descriptions = forms.BooleanField(
        label=_("Print the description of the products"),
        required=False,
        help_text=_("The description of each product stands under its position."),
    )

    def __init__(self, *args: Any, draft: DocumentDraft, **kwargs: Any) -> None:
        self.draft = draft
        if not args and "initial" not in kwargs:
            kwargs["initial"] = {
                "billing_address": draft.billing_address_id,
                "contact": draft.contact_id,
                "issued_on": draft.issued_on,
                "payment_terms_days": draft.payment_terms_days,
                "valid_until": draft.valid_until,
                "service_start": draft.service_start,
                "service_end": draft.service_end,
                "reference": draft.reference,
                "introduction": draft.introduction,
                "closing": draft.closing,
                "text_blocks": [str(pk) for pk in draft.text_block_ids],
                "print_product_descriptions": draft.print_product_descriptions,
            }
        super().__init__(*args, **kwargs)
        self.fields["billing_address"].queryset = CustomerAddress.objects.filter(
            customer_id=draft.customer_id, kind=AddressKind.BILLING
        )
        self.fields["contact"].queryset = Contact.objects.filter(customer_id=draft.customer_id)
        blocks = services.text_blocks_for(draft.kind)
        self.fields["text_blocks"].choices = [(str(block.pk), block.name) for block in blocks]
        # Fields of other kinds are not shown.
        if draft.kind != DocumentKind.INVOICE:
            for name in ("payment_terms_days", "service_start", "service_end"):
                del self.fields[name]
        if draft.kind != DocumentKind.OFFER:
            del self.fields["valid_until"]
        if not self.fields["billing_address"].queryset.exists():
            del self.fields["billing_address"]
        if not self.fields["contact"].queryset.exists():
            del self.fields["contact"]
        if not blocks:
            del self.fields["text_blocks"]

    def save(self) -> DocumentDraft:
        """Write the cleaned data to the draft.

        Raises:
            ValidationError: A value does not fit (``free.update_draft``).
        """
        data = self.cleaned_data
        values = {name: data[name] for name in free.DRAFT_FIELDS if name in data and name != "text_blocks"}
        if "text_blocks" in data:
            values["text_block_ids"] = [int(pk) for pk in data["text_blocks"]]
        return free.update_draft(self.draft, **values)


class LineForm(StyledForm):
    """A free line, or the change of any line: title, note, quantity, unit, price, tax rate, discount."""

    title = forms.CharField(label=_("Title"), max_length=200)
    note = forms.CharField(
        label=_("Note"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text=_("Printed under the title."),
    )
    quantity = forms.DecimalField(label=_("Quantity"), min_value=0, max_digits=10, decimal_places=2, initial=1)
    unit = forms.ModelChoiceField(
        label=_("Unit"), queryset=Unit.objects.none(), required=False, empty_label=_("– without unit –")
    )
    unit_price = forms.DecimalField(
        label=_("Unit price (net)"), min_value=0, max_digits=10, decimal_places=2, initial=0
    )
    tax_rate = forms.ModelChoiceField(label=_("Tax rate"), queryset=TaxRate.objects.none(), empty_label=None)
    discount_percent = forms.DecimalField(
        label=_("Discount in percent"),
        required=False,
        min_value=0,
        max_value=100,
        max_digits=5,
        decimal_places=2,
        initial=0,
    )

    def __init__(self, *args: Any, line: Any = None, **kwargs: Any) -> None:
        self.line = line
        if line is not None and not args and "initial" not in kwargs:
            kwargs["initial"] = {
                "title": line.title,
                "note": line.note,
                "quantity": line.quantity,
                "unit": line.unit_id,
                "unit_price": line.unit_price,
                "tax_rate": line.tax_rate_id,
                "discount_percent": line.discount_percent,
            }
        super().__init__(*args, **kwargs)
        units = Unit.objects.filter(is_active=True)
        rates = TaxRate.objects.filter(is_active=True)
        if line is not None:
            units = units | Unit.objects.filter(pk=line.unit_id)
            rates = rates | TaxRate.objects.filter(pk=line.tax_rate_id)
        self.fields["unit"].queryset = units.distinct()
        self.fields["tax_rate"].queryset = rates.distinct()
        if line is None:
            default = TaxRate.get_default()
            if default is not None:
                self.fields["tax_rate"].initial = default.pk
        if line is not None and line.is_text:
            for name in ("quantity", "unit", "unit_price", "tax_rate", "discount_percent"):
                del self.fields[name]

    def values(self) -> dict[str, Any]:
        """The cleaned data as the arguments of ``free.add_line`` / ``free.update_line``."""
        data = dict(self.cleaned_data)
        if "discount_percent" in data and data["discount_percent"] is None:
            data["discount_percent"] = free.ZERO
        return data


class TextLineForm(StyledForm):
    """A line of text only: a heading or a remark between the positions."""

    title = forms.CharField(label=_("Text"), max_length=200)
    note = forms.CharField(label=_("Longer text"), required=False, widget=forms.Textarea(attrs={"rows": 2}))


class ProductLineForm(StyledForm):
    """A line from a product: the product and the quantity; the rest comes from the product."""

    product = forms.ModelChoiceField(
        label=_("Product"), queryset=Product.objects.none(), widget=forms.HiddenInput, required=True
    )
    quantity = forms.DecimalField(label=_("Quantity"), min_value=0, max_digits=10, decimal_places=2, initial=1)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(is_active=True, owner__isnull=True)


def today() -> datetime.date:
    """The day a document made now is dated."""
    return timezone.localdate()
