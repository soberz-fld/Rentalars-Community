# SPDX-License-Identifier: GPL-3.0-or-later
"""Forms of the price offers: making and countering an offer, a decision, the settings (PER-038)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from rentalars.core.forms import StyledForm, StyledModelForm
from rentalars.personnel import offers
from rentalars.personnel.offer_models import MAX_AMOUNT, OfferSettings, OfferUnit

#: The fields of the settings page, in order – the API has the same.
SETTING_FIELDS = ["enabled", "also_temporary", "min_percent", "max_percent", "max_rounds"]


class OfferSettingsForm(StyledModelForm):
    """Einstellungen → Preisangebote."""

    class Meta:
        model = OfferSettings
        fields = SETTING_FIELDS

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["max_rounds"].widget.attrs.update({"min": 1, "max": 10})


class OfferForm(StyledForm):
    """An offer or a counter-offer: amount, for what, message, until when (PER-038)."""

    amount = forms.DecimalField(
        label=_("Amount"),
        min_value=Decimal("0.01"),
        max_value=MAX_AMOUNT,
        decimal_places=2,
        max_digits=10,
        help_text=_("In euros, without VAT."),
    )
    unit = forms.ChoiceField(label=_("Per"), choices=OfferUnit.choices)
    message = forms.CharField(
        label=pgettext_lazy("offer", "Message"),
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_("Optional, for the other side. At most 500 characters."),
    )
    valid_until = forms.DateField(
        label=_("Valid until"),
        required=False,
        help_text=_("Optional. Until the end of this day the offer can be accepted."),
    )

    def __init__(self, *args: Any, line: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        choices = offers.unit_choices(line)
        self.fields["unit"].choices = [(value, label) for value, label in OfferUnit.choices if value in choices]
        self.fields["amount"].widget.attrs.setdefault("autocomplete", "off")


class DecisionForm(StyledForm):
    """A reason for rejecting, or a note to accepting (PER-038); optional."""

    note = forms.CharField(label=_("Reason"), max_length=250, required=False)
