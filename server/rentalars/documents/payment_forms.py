# SPDX-License-Identifier: GPL-3.0-or-later
"""Forms of the payments (DOK-048): entering a payment, voiding one."""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rentalars.core.forms import StyledForm
from rentalars.core.payment_base import PaymentMethod
from rentalars.material.purchase_forms import AmountField


class PaymentForm(StyledForm):
    """A payment: the day, the amount (negative: a refund), how, the purpose."""

    paid_on = forms.DateField(label=_("Paid on"))
    amount = AmountField(
        label=_("Amount (gross)"),
        max_digits=12,
        decimal_places=2,
        help_text=_("As it came into or left the account. A negative amount is a refund."),
    )
    method = forms.ChoiceField(label=_("Method"), choices=PaymentMethod.choices, initial=PaymentMethod.TRANSFER)
    reference = forms.CharField(
        label=_("Reference"), required=False, max_length=200, help_text=_("The purpose of the payment.")
    )
    note = forms.CharField(label=_("Note"), required=False, max_length=250)

    def __init__(self, *args: Any, remaining: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial.setdefault("paid_on", timezone.localdate())
            if remaining is not None and remaining > 0:
                self.initial.setdefault("amount", remaining)


class VoidForm(StyledForm):
    """The reason to void a payment."""

    payment = forms.IntegerField(widget=forms.HiddenInput)
    reason = forms.CharField(label=_("Reason"), max_length=250)
