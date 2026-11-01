# SPDX-License-Identifier: GPL-3.0-or-later
"""Einstellungen → Zuschläge: the surcharges for night, Sunday and holidays (PER-009, PER-040).

One page with the switches for price and costs, the list of rules (add,
remove, order; each with its percentage for price and costs), the holidays –
the statutory ones of a German federal state and/or the company's own ones –
with a list of them for this year and the next, so that they can be checked,
and the button "Nach § 3b EStG einstellen". The calculation is
``projects.time_surcharges``; the API is ``core.surcharge_api``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django import forms
from django.contrib import messages
from django.db import transaction
from django.db.models import Max
from django.forms import BaseModelFormSet, modelformset_factory
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Module, module_required, request_rights
from rentalars.core.forms import StyledModelForm
from rentalars.core.holidays import holiday_rows, state_label
from rentalars.core.models import (
    WEEKDAY_CHOICES,
    OwnHoliday,
    TimeSurchargeRule,
    TimeSurchargeSettings,
)
from rentalars.core.surcharges import ensure_rules, forget_cached_rules, set_section_3b

#: The fields of the settings in the order of the page (PER-009, PER-040); the API has the same.
SETTING_FIELDS = ["on_price", "on_costs", "german_holidays", "state", "next_day_until"]
#: The fields of a rule (PER-040).
RULE_FIELDS = [
    "position",
    "name",
    "kind",
    "time_from",
    "time_until",
    "weekdays",
    "day",
    "month",
    "begun_before_midnight",
    "price_percent",
    "cost_percent",
]
#: The fields of an own holiday (PER-040).
HOLIDAY_FIELDS = ["name", "kind", "day", "month", "date", "easter_offset"]


class TimeSurchargeForm(StyledModelForm):
    """The switches, the holidays and the next day of the surcharges (PER-009, PER-040)."""

    class Meta:
        model = TimeSurchargeSettings
        fields = SETTING_FIELDS

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # PER-009: the switches name the crew lines – no other line of a project ever gets surcharges.
        self.fields["on_price"].label = gettext_lazy("Surcharges on the price of crew lines")
        self.fields["on_costs"].label = gettext_lazy("Surcharges on the personnel costs of crew lines")


class SurchargeRuleForm(StyledModelForm):
    """One rule of the surcharges in the list of the page (PER-040)."""

    weekdays = forms.MultipleChoiceField(
        label=gettext_lazy("weekdays"), choices=WEEKDAY_CHOICES, required=False, widget=forms.CheckboxSelectMultiple
    )

    class Meta:
        model = TimeSurchargeRule
        fields = RULE_FIELDS

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["weekdays"] = list(self.instance.weekdays)
            # "25" rather than "25,00": whole percentages are the rule.
            for name in ("price_percent", "cost_percent"):
                value = getattr(self.instance, name)
                if value is not None and value == value.to_integral_value():
                    self.initial[name] = value.quantize(Decimal("1"))
        position = self.fields["position"]
        position.required = False
        position.widget.attrs.update({"data-surcharge-order": "", "min": "0", "class": "order-input"})
        for name in ("day", "month"):
            self.fields[name].widget.attrs["class"] = "short-input"
        # Explained once above the list, not in each of the rows.
        self.fields["name"].help_text = ""
        self.fields["begun_before_midnight"].help_text = ""
        # Short labels: the fields of a rule stand side by side in one row.
        self.fields["price_percent"].label = gettext_lazy("Price in %")
        self.fields["cost_percent"].label = gettext_lazy("Costs in %")

    def has_changed(self) -> bool:
        """A new row whose place alone changed (moved with the arrows) is still an empty row."""
        if self.instance.pk is None:
            return any(name != "position" for name in self.changed_data)
        return super().has_changed()

    def clean_weekdays(self) -> str:
        """The chosen ISO weekdays as one string ("67")."""
        return "".join(sorted(self.cleaned_data.get("weekdays") or []))


class OwnHolidayForm(StyledModelForm):
    """One own holiday in the list of the page (PER-040)."""

    class Meta:
        model = OwnHoliday
        fields = HOLIDAY_FIELDS

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for name in ("day", "month", "easter_offset"):
            self.fields[name].widget.attrs["class"] = "short-input"


class _OrderedFormSet(BaseModelFormSet):
    """A list of rows where an untouched new row is simply left out."""

    def save_rows(self) -> None:
        """Save changed and new rows, delete the rows marked for it – each in the change log."""
        deleted = self.deleted_forms
        for form in self.forms:
            if form in deleted:
                if form.instance.pk:
                    form.instance.delete()
            elif form.has_changed():
                form.save()


RuleFormSet = modelformset_factory(
    TimeSurchargeRule, form=SurchargeRuleForm, formset=_OrderedFormSet, extra=1, can_delete=True
)
HolidayFormSet = modelformset_factory(
    OwnHoliday, form=OwnHolidayForm, formset=_OrderedFormSet, extra=1, can_delete=True
)


def _place_new_rules(formset: Any) -> None:
    """A new rule without a place goes to the end of the list."""
    last = TimeSurchargeRule.objects.aggregate(last=Max("position"))["last"] or 0
    for form in formset.forms:
        if form.instance.pk is None and form.has_changed() and not form.cleaned_data.get("position"):
            last += 1
            form.instance.position = last


@module_required(Module.ADMINISTRATION)
def time_surcharges(request: HttpRequest) -> HttpResponse:
    """Show and change the surcharges: switches, rules, holidays (PER-009, PER-040)."""
    can_write = request_rights(request).can_write(Module.ADMINISTRATION)
    current = ensure_rules()
    data = request.POST if request.method == "POST" else None
    form = TimeSurchargeForm(data, instance=current)
    rules = RuleFormSet(data, prefix="rules", queryset=TimeSurchargeRule.objects.order_by("position", "id"))
    holidays = HolidayFormSet(data, prefix="holidays", queryset=OwnHoliday.objects.order_by("id"))
    if request.method == "POST":
        if not can_write:
            return render(request, "403.html", status=403)
        if form.is_valid() and rules.is_valid() and holidays.is_valid():
            with transaction.atomic():
                form.save()
                _place_new_rules(rules)
                rules.save_rows()
                holidays.save_rows()
            forget_cached_rules()
            messages.success(request, _("Settings saved."))
            return redirect("core:time_surcharges")
    year = timezone.localdate().year
    own = tuple(holiday.spec() for holiday in OwnHoliday.objects.order_by("id"))
    return render(
        request,
        "core/time_surcharges.html",
        {
            "form": form,
            "rules": rules,
            "holidays": holidays,
            "can_write": can_write,
            "holiday_rows": holiday_rows([year, year + 1], current.state, current.german_holidays, own),
            "holiday_years": (year, year + 1),
            "state_label": state_label(current.state) if current.german_holidays else "",
        },
    )


@require_POST
@module_required(Module.ADMINISTRATION)
def time_surcharges_section_3b(request: HttpRequest) -> HttpResponse:
    """The button "Nach § 3b EStG einstellen": the rules of the law replace the list (PER-040)."""
    if not request_rights(request).can_write(Module.ADMINISTRATION):
        return render(request, "403.html", status=403)
    set_section_3b()
    messages.success(request, _("The rules of § 3b EStG are set. The holidays stayed as they were."))
    return redirect("core:time_surcharges")
