# SPDX-License-Identifier: GPL-3.0-or-later
"""Forms of the page Settings → Accounting: Lexware Office (DOK-011) and DATEV (DOK-012)."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any, ClassVar

from django import forms
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from rentalars.core.forms import StyledForm, StyledModelForm
from rentalars.core.money import decimal_separator
from rentalars.documents.models import (
    DEFAULT_REVENUE_ACCOUNTS,
    LEXWARE_INCOME_CATEGORY,
    AccountingSettings,
    rate_key,
)


def tax_rate_keys(accounting: AccountingSettings) -> list[str]:
    """The tax rates the mappings are shown for: those of the master data, the usual ones, those set already."""
    from rentalars.masterdata.models import TaxRate

    keys = {rate_key(rate) for rate in TaxRate.objects.values_list("rate", flat=True)}
    keys |= {key for chart in DEFAULT_REVENUE_ACCOUNTS.values() for key in chart}
    keys |= set(accounting.lexware_categories or {}) | set(accounting.datev_revenue_accounts or {})
    return sorted(keys, key=lambda key: -Decimal(key))


def _field_name(prefix: str, key: str) -> str:
    return f"{prefix}_{key.replace('.', '_')}"


def _rate_label(key: str) -> str:
    return _("%(rate)s %% tax") % {"rate": key.replace(".", ",")}


class LexwareSettingsForm(StyledModelForm):
    """Lexware Office: on or off, API key, at once or by hand, contact, posting categories (DOK-011).

    The key is never shown; an empty field keeps the stored one.
    """

    api_key = forms.CharField(
        label=gettext_lazy("API key"),
        required=False,
        strip=True,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text=gettext_lazy("Created in Lexware Office under Add-ons → Public API. Leave empty to keep the key."),
    )

    error_field_map: ClassVar[dict[str, str]] = {"lexware_enabled": "api_key"}

    class Meta:
        model = AccountingSettings
        fields = ["lexware_enabled", "lexware_automatic", "lexware_collective_contact"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        known = {choice["id"]: choice["name"] for choice in self.instance.lexware_category_choices or []}
        self.rate_fields: list[forms.BoundField] = []
        for key in tax_rate_keys(self.instance):
            current = (self.instance.lexware_categories or {}).get(key, "")
            # UIX-029: "Einnahmen" is the name of the category in Lexware Office.
            choices = [("", _("Default: income (Einnahmen)"))] + [
                (category_id, name) for category_id, name in known.items() if category_id != LEXWARE_INCOME_CATEGORY
            ]
            if current and current not in known:
                choices.append((current, current))
            name = _field_name("category", key)
            self.fields[name] = forms.ChoiceField(
                label=_rate_label(key), choices=choices, required=False, initial=current
            )
            self.rate_fields.append(self[name])

    def clean(self) -> dict[str, Any]:
        """Put key and categories on the settings, so that the rules of the model see them."""
        data = super().clean()
        if data.get("api_key"):
            self.instance.set_lexware_api_key(data["api_key"])
        self.instance.lexware_categories = {
            key: data[_field_name("category", key)]
            for key in tax_rate_keys(self.instance)
            if data.get(_field_name("category", key))
        }
        return data


class BooksSettingsForm(StyledModelForm):
    """The format of the e-invoice (DOK-049), the check (DOK-042), small business (DOK-045) and the archive (DOK-043)."""

    class Meta:
        model = AccountingSettings
        fields = [
            "invoice_format",
            "einvoice_blocks",
            "small_business",
            "retention_invoice_years",
            "retention_letter_years",
            "archive_check_days",
        ]


class DatevSettingsForm(StyledModelForm):
    """DATEV: consultant and client, fiscal year, accounts (DOK-012). Empty revenue accounts take the default."""

    class Meta:
        model = AccountingSettings
        fields = [
            "datev_consultant_number",
            "datev_client_number",
            "datev_fiscal_year_start",
            "datev_account_length",
            "datev_chart",
            "datev_debitor_mode",
            "datev_debitor_offset",
            "datev_collective_account",
        ]
        # UIX-029: the English texts of the fields come from the model.

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        months = [
            _("January"),
            _("February"),
            _("March"),
            _("April"),
            _("May"),
            _("June"),
            _("July"),
            _("August"),
            _("September"),
            _("October"),
            _("November"),
            _("December"),
        ]
        self.fields["datev_fiscal_year_start"].choices = list(enumerate(months, start=1))
        self.rate_fields: list[forms.BoundField] = []
        for key in tax_rate_keys(self.instance):
            name = _field_name("account", key)
            default = self.instance.default_revenue_account(key)
            self.fields[name] = forms.CharField(
                label=_("Revenue account %(rate)s %%") % {"rate": key.replace(".", decimal_separator())},
                required=False,
                max_length=8,
                initial=(self.instance.datev_revenue_accounts or {}).get(key, ""),
                help_text=_("Empty: %(account)s") % {"account": default} if default else _("No standard account."),
                widget=forms.TextInput(attrs={"inputmode": "numeric", "placeholder": default}),
            )
            self.rate_fields.append(self[name])

    def clean(self) -> dict[str, Any]:
        """Revenue accounts have exactly as many digits as the general ledger accounts."""
        data = super().clean()
        length = data.get("datev_account_length") or self.instance.datev_account_length
        accounts = {}
        for key in tax_rate_keys(self.instance):
            name = _field_name("account", key)
            account = (data.get(name) or "").strip()
            if not account:
                continue
            if not account.isdigit() or len(account) != length:
                self.add_error(name, _("A revenue account has exactly %(digits)d digits.") % {"digits": length})
                continue
            accounts[key] = account
        self.instance.datev_revenue_accounts = accounts
        return data


def last_month() -> tuple[datetime.date, datetime.date]:
    """The month before this one: the usual period of an export."""
    first_of_this = timezone.localdate().replace(day=1)
    last = first_of_this - datetime.timedelta(days=1)
    return last.replace(day=1), last


class DatevExportForm(StyledForm):
    """The period of a DATEV export (DOK-012)."""

    date_from = forms.DateField(label=gettext_lazy("From"))
    date_to = forms.DateField(label=gettext_lazy("Until"))

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        start, end = last_month()
        kwargs.setdefault("initial", {"date_from": start, "date_to": end})
        super().__init__(*args, **kwargs)
