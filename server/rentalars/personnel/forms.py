# SPDX-License-Identifier: GPL-3.0-or-later
"""Forms of the personnel module."""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils import timezone
from django.utils.dates import WEEKDAYS
from django.utils.translation import gettext_lazy as _

from rentalars.core.forms import StyledForm, StyledModelForm
from rentalars.personnel.models import (
    Absence,
    AvailabilityRepeat,
    AvailabilitySeries,
    AvailabilityState,
    JobFunction,
    Person,
    Qualification,
    QualificationType,
)


class PersonForm(StyledModelForm):
    """Master data of a person (PER-002, PER-003, PER-024) and what colleagues may see (PER-019).

    The account comes with the person (AUT-026); username, roles and access
    are managed under Settings → Users.
    """

    class Meta:
        model = Person
        fields = [
            "first_name",
            "last_name",
            "kind",
            "position",
            "email",
            "phone",
            "commute_km",  # ZEI-027
            "note",
            "company",
            "street",
            "postal_code",
            "city",
            "tax_number",
            "vat_id",
            "share_phone",
            "share_email",
        ]
        widgets = {"note": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.instance.pk is None:
            self.fields["invite"] = forms.BooleanField(
                label=_("Send the invitation by e-mail now"),
                required=False,
                help_text=_(
                    "With the link the person chooses a password. Without an e-mail address: a one-time password."
                ),
            )


class JobFunctionForm(StyledModelForm):
    """A job function with the guide values for costs and the maximum discount.

    PER-004, PER-008, PRJ-052; the guide value per day comes with PER-029.
    The maximum discount (PER-026) is a price matter and needs the price
    right (AUT-019).

    PRD-044: the service product is not chosen – every function has
    its own, created with it under the same name. A new function can bring
    the price per hour for it (with the price right); afterwards price, tax
    rate and hour tiers are kept on the product, which the page links to.
    PER-035: the guide value per hour from the limit of hours per day.
    """

    price = forms.DecimalField(
        label=_("Price per hour for the customer (net)"),
        min_value=0,
        decimal_places=2,
        max_digits=10,
        required=False,
        help_text=_("Goes to the service product created with the job function. Empty: enter it there later."),
    )

    class Meta:
        model = JobFunction
        fields = [
            "name",
            "guide_cost_rate",
            "guide_cost_rate_above_limit",
            "guide_daily_cost_rate",
            "max_discount_percent",
            "is_active",
        ]

    def __init__(self, *args: Any, may_see_costs: bool, may_see_prices: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not may_see_prices:
            del self.fields["max_discount_percent"]
        if not may_see_prices or self.instance.pk:
            # PRD-044: the price of an existing function is kept on its service product.
            del self.fields["price"]
        else:
            self.order_fields(["name", "price"])
        if not may_see_costs:
            # AUT-019: without the right the fields do not even exist in the form.
            del self.fields["guide_cost_rate"]
            del self.fields["guide_cost_rate_above_limit"]
            del self.fields["guide_daily_cost_rate"]
        else:
            # Job function notes: these are costs of the company, not what the customer pays.
            self.fields["guide_cost_rate"].help_text = _(
                "Hourly wage of the planned crew (internal cost rate) – not the price for the customer. "
                "Used in the calculation while a crew line has no person yet, or the person has no own rate."
            )
            self.fields["guide_daily_cost_rate"].help_text = _(
                "Internal cost per day of the planned crew – not the price for the customer. "
                "Used for days while a crew line has no person yet, or the person has no day rate."
            )

    def save(self, commit: bool = True) -> JobFunction:
        """Save the function with its service product (PRD-044); renaming renames a product of the same name."""
        from rentalars.personnel.services import save_job_function

        return save_job_function(self.instance, price=self.cleaned_data.get("price"))


class RateForm(StyledForm):
    """Assign a job function to a person, or give it new rates from a day on (PER-005, PER-007, PER-029).

    Hourly rate, day rate and "valid from" are optional (PER-029): without a
    rate the guide value of the job function counts, without a day the rates
    count from always.
    """

    job_function = forms.ModelChoiceField(label=_("Job function"), queryset=JobFunction.objects.filter(is_active=True))
    hourly_rate = forms.DecimalField(
        label=_("Hourly rate"), min_value=0, decimal_places=2, max_digits=8, required=False
    )
    # PER-035: the cost of an hour beyond the limit of hours per day of the service product.
    hourly_rate_above_limit = forms.DecimalField(
        label=_("Hourly rate from the limit"), min_value=0, decimal_places=2, max_digits=8, required=False
    )
    daily_rate = forms.DecimalField(label=_("Day rate"), min_value=0, decimal_places=2, max_digits=8, required=False)
    valid_from = forms.DateField(
        label=_("Valid from"),
        required=False,
        help_text=_("Empty: always. A later day adds new rates and keeps the old ones for the time before."),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("autocomplete", "off")
        for name in ("hourly_rate", "daily_rate"):
            self.fields[name].widget.attrs.setdefault("placeholder", _("guide value"))
        self.fields["hourly_rate_above_limit"].widget.attrs.setdefault("placeholder", _("as the hourly rate"))


class AbsenceForm(StyledModelForm):
    """An absence with its period (PER-011)."""

    class Meta:
        model = Absence
        fields = ["kind", "start", "end", "note"]


class QualificationForm(StyledModelForm):
    """A qualification with expiry date and certificate (PER-014)."""

    upload = forms.FileField(
        label=_("Certificate"), required=False, help_text=_("PDF or picture; replaces the one stored.")
    )

    class Meta:
        model = Qualification
        fields = ["qualification_type", "detail", "acquired_on", "valid_until"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        types = QualificationType.objects.filter(is_active=True)
        if self.instance.pk:
            types = types | QualificationType.objects.filter(pk=self.instance.qualification_type_id)
        self.fields["qualification_type"].queryset = types.order_by("name")
        self.fields["valid_until"].help_text = _("Empty: does not expire, or as the type says from “acquired on”.")


class AvailabilityForm(StyledForm):
    """The question "who is free from … until … and can do X?" (VFG-010)."""

    start = forms.DateTimeField(label=_("From"))
    end = forms.DateTimeField(label=_("Until"))
    # VFG-038: "all people" – every active person, whatever their job functions.
    job_function = forms.ModelChoiceField(
        label=_("Job function"),
        queryset=JobFunction.objects.filter(is_active=True),
        required=False,
        empty_label=_("All people, whatever their job functions"),
    )

    def clean(self) -> dict[str, Any]:
        """The end must be after the start."""
        cleaned = super().clean() or {}
        if cleaned.get("start") and cleaned.get("end") and cleaned["end"] <= cleaned["start"]:
            self.add_error("end", _("The end must be after the start."))
        return cleaned


class OwnProfileForm(StyledModelForm):
    """What a person decides about their own data: what colleagues may see (PER-019)."""

    class Meta:
        model = Person
        fields = ["phone", "email", "share_phone", "share_email"]


# --- Availability and calendars (PER-021 to PER-023) ---------------------------------------------------


class AvailabilityMarkForm(StyledForm):
    """Colour days of the availability calendar, or clear them (PER-021); repeat them as a series (PER-028).

    Without times the days are coloured as a whole; with times the colour
    applies on each of the days between the two times
    (:func:`rentalars.personnel.marks.day_periods`). With a repetition the
    days are the first occurrence of a series
    (:func:`rentalars.personnel.marks.create_series`).
    """

    #: The value of the button that removes what was entered.
    CLEAR = "clear"

    start_day = forms.DateField(label=_("From"))
    end_day = forms.DateField(label=_("Until"), required=False, help_text=_("Empty: only the first day."))
    with_times = forms.BooleanField(label=_("Only at certain times"), required=False)
    start_time = forms.TimeField(label=_("from"), required=False)
    end_time = forms.TimeField(label=_("until"), required=False)
    note = forms.CharField(label=_("Note"), required=False, max_length=250)
    state = forms.ChoiceField(
        label=_("Availability"),
        choices=[*AvailabilityState.choices, (CLEAR, _("remove entry"))],
    )
    # PER-028: the repetition, like an appointment series in a calendar program.
    repeat = forms.ChoiceField(
        label=_("Repeat"), required=False, choices=[("", _("does not repeat")), *AvailabilityRepeat.choices]
    )
    interval = forms.IntegerField(label=_("every"), required=False, min_value=1, max_value=365, initial=1)
    weekdays = forms.TypedMultipleChoiceField(
        label=_("on"),
        required=False,
        coerce=int,
        choices=[(number, WEEKDAYS[number]) for number in range(7)],
        widget=forms.CheckboxSelectMultiple,
    )
    until = forms.DateField(label=_("ends on"), required=False)
    count = forms.IntegerField(label=_("or after"), required=False, min_value=1, max_value=366)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["note"].widget.attrs.update(
            {"placeholder": _("e.g. only until 18:00"), "autocomplete": "off", "maxlength": "250"}
        )
        self.fields["interval"].widget.attrs.update({"min": "1"})
        self.fields["count"].widget.attrs.update({"min": "1"})

    def clean(self) -> dict[str, Any]:
        """The last day defaults to the first; times count only when asked for; a series needs an end."""
        cleaned = super().clean() or {}
        if cleaned.get("start_day") and not cleaned.get("end_day"):
            cleaned["end_day"] = cleaned["start_day"]
        if cleaned.get("with_times"):
            if not cleaned.get("start_time") or not cleaned.get("end_time"):
                self.add_error("end_time", _("Give both times, or none for whole days."))
            elif cleaned["start_time"] == cleaned["end_time"]:
                self.add_error("end_time", _("The end must be after the start."))
        else:
            cleaned["start_time"] = cleaned["end_time"] = None
        if cleaned.get("repeat"):
            if cleaned.get("state") == self.CLEAR:
                self.add_error(
                    "repeat", _("A repetition can only be entered. To remove a series, use the list of series.")
                )
            if cleaned.get("until") and cleaned.get("count"):
                self.add_error("count", _("Give an end date or a number of times, not both."))
            elif not cleaned.get("until") and not cleaned.get("count"):
                self.add_error("until", _("Say until when the series repeats, or how often."))
            cleaned["interval"] = cleaned.get("interval") or 1
        return cleaned

    def series_values(self) -> dict[str, Any]:
        """The values of the series to create (PER-028); only with a valid form and a repetition."""
        data = self.cleaned_data
        return {
            "state": data["state"],
            "note": data["note"],
            "first_day": data["start_day"],
            "last_day": data["end_day"],
            "start_time": data["start_time"],
            "end_time": data["end_time"],
            "repeat": data["repeat"],
            "interval": data["interval"],
            "weekdays": data.get("weekdays") or [],
            "until": data.get("until"),
            "count": data.get("count"),
        }


class AvailabilitySeriesForm(AvailabilityMarkForm):
    """Change a series from a day on (PER-028): the same fields, and the day the change counts from."""

    from_day = forms.DateField(
        label=_("Change from"), help_text=_("What lies before stays as it is. Empty: from today.")
    )

    def __init__(self, *args: Any, series: AvailabilitySeries | None = None, **kwargs: Any) -> None:
        if series is not None and "initial" not in kwargs:
            kwargs["initial"] = {
                "start_day": series.first_day,
                "end_day": series.last_day,
                "with_times": series.start_time is not None,
                "start_time": series.start_time,
                "end_time": series.end_time,
                "note": series.note,
                "state": series.state,
                "repeat": series.repeat,
                "interval": series.interval,
                "weekdays": series.weekday_numbers,
                "until": series.until,
                "count": series.count,
                "from_day": max(timezone.localdate(), series.first_day),
            }
        super().__init__(*args, **kwargs)
        self.fields["state"].choices = AvailabilityState.choices
        self.fields["repeat"].choices = AvailabilityRepeat.choices
        self.fields["repeat"].required = True
        self.fields["from_day"].required = False

    def clean(self) -> dict[str, Any]:
        """Like entering, and the change counts from today unless a day is given."""
        cleaned = super().clean()
        cleaned["from_day"] = cleaned.get("from_day") or timezone.localdate()
        return cleaned


class FeedLinkForm(StyledForm):
    """One more linked calendar: its address and a name to tell it from the others (PER-022, PER-031)."""

    url = forms.CharField(
        label=_("Address of the calendar (ICS link)"),
        required=False,  # an empty address is told by ``calendars.add_feed``
        max_length=500,
        widget=forms.URLInput(attrs={"autocomplete": "off", "placeholder": "https://…/basic.ics"}),
    )
    label = forms.CharField(
        label=_("Name (optional)"),
        required=False,
        max_length=80,
        widget=forms.TextInput(attrs={"autocomplete": "off", "placeholder": _("e.g. Band")}),
    )


class CalDAVForm(StyledForm):
    """Where Rentalars writes the deployments of a person (PER-023)."""

    caldav_url = forms.CharField(
        label=_("Address of the CalDAV calendar or server"),
        required=False,
        max_length=500,
        widget=forms.URLInput(attrs={"autocomplete": "off", "placeholder": "https://cloud.example.de/remote.php/dav"}),
    )
    caldav_username = forms.CharField(
        label=_("Username"), required=False, max_length=200, widget=forms.TextInput(attrs={"autocomplete": "off"})
    )
    caldav_password = forms.CharField(
        label=_("Password"),
        required=False,
        strip=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text=_("Leave empty to keep the stored password."),
    )
