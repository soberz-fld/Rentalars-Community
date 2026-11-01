# SPDX-License-Identifier: GPL-3.0-or-later
"""Forms of the customers module."""

from __future__ import annotations

from typing import Any

from django import forms
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.core.forms import StyledModelForm
from rentalars.customers.models import Contact, Customer, CustomerAddress, Venue


class CustomerForm(StyledModelForm):
    """Master data of a customer (KND-003) with its commercial details (KND-006).

    The standard discount is a price detail: without the price right the
    field is not offered (AUT-019). When a customer is created, name and
    e-mail are checked against the existing customers while typing (KND-008).
    """

    confirm_duplicate = forms.BooleanField(
        label=_("Create anyway – it is a different customer"), required=False, widget=forms.CheckboxInput()
    )

    class Meta:
        model = Customer
        fields = [
            "kind",
            "name",
            "name_addition",
            "street",
            "postal_code",
            "city",
            "country",
            "email",
            "phone",
            "vat_id",
            "tax_number",
            "buyer_reference",
            "payment_terms_days",
            "default_discount_percent",
            "note",
            "is_active",
        ]
        widgets = {"note": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args: Any, rights: Rights, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not rights.has(SpecialRight.PRICES):
            del self.fields["default_discount_percent"]
        if self.instance.pk:
            del self.fields["confirm_duplicate"]
        else:
            # KND-008: a hint as soon as name or e-mail resemble an existing customer.
            check = {
                "hx-get": reverse("customers:duplicates"),
                "hx-trigger": "change, keyup changed delay:600ms",
                "hx-target": "#duplicates",
                "hx-include": "[name=name], [name=email]",
            }
            self.fields["name"].widget.attrs.update(check)
            self.fields["email"].widget.attrs.update(check)


class CustomerAddressForm(StyledModelForm):
    """A further billing or delivery address of a customer (KND-005)."""

    class Meta:
        model = CustomerAddress
        fields = ["kind", "label", "name", "name_addition", "street", "postal_code", "city", "country", "is_default"]


class ContactForm(StyledModelForm):
    """A contact person of a customer (KND-004).

    First and last name apart (the last name is needed), and the greeting of mails to this contact:
    "Sehr geehrte Frau Berg," – formal, "Hallo Anna," – personal, or an own text. The salutation offers
    suggestions but takes any text.
    """

    class Meta:
        model = Contact
        fields = [
            "salutation",
            "first_name",
            "last_name",
            "position",
            "email",
            "phone",
            "is_primary",
            "greeting_style",
            "greeting_text",
        ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["last_name"].required = True
        self.fields["salutation"].widget.attrs["list"] = "salutation-suggestions"
        self.fields["salutation"].widget.attrs["autocomplete"] = "off"
        self.fields["greeting_text"].required = False

    @property
    def salutation_suggestions(self) -> tuple[str, ...]:
        """The salutations the field suggests; any text can be typed (KND-004)."""
        return (str(_("Mr")), str(_("Ms")), "Dr.", "Prof.", "Prof. Dr.")


class VenueForm(StyledModelForm):
    """A venue with address, contact on site and notes (KND-009)."""

    class Meta:
        model = Venue
        fields = [
            "name",
            "street",
            "postal_code",
            "city",
            "country",
            "contact_name",
            "contact_phone",
            "contact_email",
            "access_notes",
            "power_notes",
            "notes",
            "hall_plan",
            "is_active",
        ]
        widgets = {
            "access_notes": forms.Textarea(attrs={"rows": 3}),
            "power_notes": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
