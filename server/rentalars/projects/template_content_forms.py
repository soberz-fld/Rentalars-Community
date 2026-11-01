# SPDX-License-Identifier: GPL-3.0-or-later
"""Forms for editing the content of a project template (PRJ-135).

One form for each section of the content (``projects.template_content``). A form is built for a template's content and,
when an entry is changed, for that entry; ``values()`` gives what the service takes, ``initial_for()`` turns an entry back
into field values. Fields the form does not show (a line's preferred model, for one) are carried over from the entry by the
view, so that changing one thing never loses another.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django import forms
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from rentalars.core.forms import StyledForm
from rentalars.customers.models import Venue
from rentalars.personnel.models import JobFunction
from rentalars.products.models import Product
from rentalars.projects import template_content as tc
from rentalars.projects.models import GroupKind, LineVariant, PhaseKind

_HOUR = 3600

PERIOD_CHOICES = [
    ("project", _("the whole project")),
    ("start", _("counted from the start of the project")),
    ("end", _("counted back from the end of the project")),
]


class _Form(StyledForm):
    """A form for one entry. ``content`` is the whole content (for choices), ``entry`` the entry being changed."""

    def __init__(
        self,
        *args: Any,
        content: dict[str, Any],
        entry: dict[str, Any] | None = None,
        prices: bool = False,
        **kwargs: Any,
    ) -> None:
        self.content = content
        self.entry = entry
        self.prices = prices
        if entry is not None and (not args or args[0] is None) and "initial" not in kwargs:
            kwargs["initial"] = self.initial_for(entry)
        super().__init__(*args, **kwargs)
        self.setup()

    def setup(self) -> None:
        """Adjust the fields to the content (choices, rights)."""

    def initial_for(self, entry: dict[str, Any]) -> dict[str, Any]:
        """The field values of an entry."""
        return {name: ("" if value is None else value) for name, value in entry.items() if name != "key"}

    def values(self) -> dict[str, Any]:
        """What the service takes."""
        values = dict(self.cleaned_data)
        for name, value in list(values.items()):
            if hasattr(value, "pk"):
                values[name] = value.pk
        return values


# --- Times ----------------------------------------------------------------------------------------------------------


class _PeriodForm(_Form):
    """The period of an entry: the project's, or hours from its start, or hours back from its end."""

    #: A phase always has a period of its own.
    always_own = False
    error_field_map = {"start": "from_hours", "end": "to_hours"}

    period = forms.ChoiceField(label=_("Period"), choices=PERIOD_CHOICES, initial="project")
    from_hours = forms.DecimalField(
        label=_("From (hours)"),
        required=False,
        min_value=Decimal("0"),
        max_digits=8,
        decimal_places=2,
        help_text=_(
            "After the start of the project; counted back from its end: how many hours before the end it begins."
        ),
    )
    to_hours = forms.DecimalField(
        label=_("Until (hours)"), required=False, min_value=Decimal("0"), max_digits=8, decimal_places=2
    )

    def setup(self) -> None:
        """Fill in the choices of the fields from the content."""
        if self.always_own:
            self.fields["period"].choices = PERIOD_CHOICES[1:]
            self.fields["period"].initial = "start"
        super().setup()

    def initial_for(self, entry: dict[str, Any]) -> dict[str, Any]:
        initial = super().initial_for(entry)
        if not entry.get("own_period"):
            initial["period"] = "project" if not self.always_own else "start"
            return initial
        start, end = Decimal(str(entry.get("start", 0))) / _HOUR, Decimal(str(entry.get("end", 0))) / _HOUR
        if entry.get("anchor") == "end":
            initial.update(period="end", from_hours=-start, to_hours=-end)
        else:
            initial.update(period="start", from_hours=start, to_hours=end)
        for name in ("from_hours", "to_hours"):
            initial[name] = initial[name].quantize(Decimal("0.01")).normalize()
        return initial

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        period = cleaned.get("period")
        if period in ("start", "end"):
            first, last = cleaned.get("from_hours"), cleaned.get("to_hours")
            if first is None:
                self.add_error("from_hours", gettext("This field is required."))
            if last is None:
                self.add_error("to_hours", gettext("This field is required."))
            if first is not None and last is not None:
                if period == "start" and last <= first:
                    self.add_error("to_hours", gettext("The end must be after the start."))
                if period == "end" and first <= last:
                    self.add_error(
                        "from_hours", gettext("It must begin earlier (more hours before the end) than it ends.")
                    )
        return cleaned

    def values(self) -> dict[str, Any]:
        """What the service takes."""
        values = super().values()
        period = values.pop("period", "project")
        first, last = values.pop("from_hours", None), values.pop("to_hours", None)
        if period == "project":
            values["own_period"] = False
        elif period == "start":
            values.update(own_period=True, anchor="start", start=round(first * _HOUR), end=round(last * _HOUR))
        else:
            values.update(own_period=True, anchor="end", start=-round(first * _HOUR), end=-round(last * _HOUR))
        return values


# --- Groups ---------------------------------------------------------------------------------------------------------


def group_choices(content: dict[str, Any], *, without: int | None = None) -> list[tuple[Any, str]]:
    """The groups as choices, indented by depth; ``without`` leaves out a group and everything below it."""
    groups = content.get(tc.GROUPS, [])
    by_key = {entry["key"]: entry for entry in groups}
    excluded: set[int] = set()
    if without is not None:
        excluded.add(without)
        grew = True
        while grew:
            grew = False
            for entry in groups:
                if entry.get("parent") in excluded and entry["key"] not in excluded:
                    excluded.add(entry["key"])
                    grew = True
    choices: list[tuple[Any, str]] = [("", "–")]
    for entry in groups:
        if entry["key"] in excluded:
            continue
        depth = 0
        parent = entry.get("parent")
        seen: set[int] = set()
        while parent in by_key and parent not in seen:
            seen.add(parent)
            depth += 1
            parent = by_key[parent].get("parent")
        choices.append((entry["key"], " " * depth + entry["name"]))
    return choices


class GroupForm(_Form):
    """A group: name, place in the tree, kind, rental days, and – with the price right – its discount."""

    name = forms.CharField(label=_("Name"), max_length=120)
    description = forms.CharField(label=_("Description"), required=False, widget=forms.Textarea(attrs={"rows": 2}))
    parent = forms.TypedChoiceField(label=_("Inside the group"), required=False, coerce=int, empty_value=None)
    kind = forms.ChoiceField(label=_("Counts towards the total"), choices=GroupKind.choices, initial=GroupKind.NORMAL)
    alternative_to = forms.TypedChoiceField(
        label=_("Replaces the group"),
        required=False,
        coerce=int,
        empty_value=None,
        help_text=_("Only for an alternative group."),
    )
    rental_days = forms.IntegerField(label=_("Rental days"), required=False, min_value=1, max_value=999)
    discount_percent = forms.DecimalField(
        label=_("Discount in percent"), required=False, min_value=0, max_value=100, max_digits=5, decimal_places=2
    )
    discount_amount = forms.DecimalField(
        label=_("Discount as amount"), required=False, min_value=0, max_digits=10, decimal_places=2
    )
    flat_price = forms.DecimalField(label=_("Flat price"), required=False, min_value=0, max_digits=10, decimal_places=2)

    def setup(self) -> None:
        """Parent and alternative choices without the group itself and what is below it."""
        own = self.entry["key"] if self.entry else None
        self.fields["parent"].choices = group_choices(self.content, without=own)
        targets = [
            (entry["key"], entry["name"])
            for entry in self.content.get(tc.GROUPS, [])
            if entry["key"] != own and entry.get("kind") != GroupKind.ALTERNATIVE.value
        ]
        self.fields["alternative_to"].choices = [("", "–"), *targets]
        if not self.prices:
            for name in ("discount_percent", "discount_amount", "flat_price"):
                del self.fields[name]


# --- Lines ----------------------------------------------------------------------------------------------------------


class _LineForm(_PeriodForm):
    group = forms.TypedChoiceField(label=_("Inside the group"), required=False, coerce=int, empty_value=None)
    note = forms.CharField(label=_("Note"), required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def setup(self) -> None:
        """Fill in the choices of the fields from the content."""
        self.fields["group"].choices = group_choices(self.content)
        super().setup()


class ProductLineForm(_LineForm):
    """A line of a product from the product list."""

    product = forms.IntegerField(label=_("Product"), widget=forms.HiddenInput)
    quantity = forms.DecimalField(
        label=_("Quantity"), min_value=Decimal("0.01"), max_digits=10, decimal_places=2, initial=1
    )
    is_sale = forms.BooleanField(label=_("Sell instead of rent"), required=False)
    variant = forms.ChoiceField(label=_("Counts towards the total"), choices=LineVariant.choices, required=False)
    alternative_to = forms.TypedChoiceField(
        label=_("Replaces the line"),
        required=False,
        coerce=int,
        empty_value=None,
        help_text=_("Only for an alternative line."),
    )
    rental_days = forms.IntegerField(label=_("Rental days"), required=False, min_value=1, max_value=999)
    quantity_is_estimate = forms.BooleanField(label=_("The quantity is an estimate"), required=False)

    kind = "product"

    def setup(self) -> None:
        """Fill in the choices of the fields from the content."""
        own = self.entry["key"] if self.entry else None
        targets = [
            (line["key"], self.line_label(line))
            for line in self.content.get(tc.LINES, [])
            if line["key"] != own and line.get("variant") != LineVariant.ALTERNATIVE.value and not line.get("is_text")
        ]
        self.fields["alternative_to"].choices = [("", "–"), *targets]
        super().setup()

    def line_label(self, line: dict[str, Any]) -> str:
        """A line as a choice for "replaces the line"."""
        if line.get("product"):
            name = Product.objects.filter(pk=line["product"]).values_list("name", flat=True).first()
            return f"{name or '?'} × {line['quantity']}"
        return f"{line.get('title') or '?'} × {line['quantity']}"

    def product_name(self) -> str:
        """The name of the chosen product, for the search field."""
        value = self["product"].value()
        if not str(value or "").isdigit():
            return ""
        return Product.objects.filter(pk=int(value)).values_list("name", flat=True).first() or ""


class FreeLineForm(ProductLineForm):
    """A line without a product: a title and, with the price right, a price."""

    product = None  # type: ignore[assignment]
    title = forms.CharField(label=_("Title"), max_length=200)
    unit_price = forms.DecimalField(
        label=_("Unit price (net)"), required=False, min_value=0, max_digits=10, decimal_places=2
    )
    is_sale = None  # type: ignore[assignment]

    kind = "free"

    def setup(self) -> None:
        """Fill in the choices of the fields from the content."""
        super().setup()
        if not self.prices:
            del self.fields["unit_price"]


class TextLineForm(_Form):
    """A line that only carries a text: a heading or a remark."""

    title = forms.CharField(label=_("Text"), max_length=200)
    note = forms.CharField(label=_("Note"), required=False, widget=forms.Textarea(attrs={"rows": 2}))
    group = forms.TypedChoiceField(label=_("Inside the group"), required=False, coerce=int, empty_value=None)

    kind = "text"

    def setup(self) -> None:
        """Fill in the choices of the fields from the content."""
        self.fields["group"].choices = group_choices(self.content)

    def values(self) -> dict[str, Any]:
        """What the service takes."""
        return {**super().values(), "is_text": True}


def line_form_for(entry: dict[str, Any] | None, mode: str) -> type[_Form]:
    """The form class for a line: by the entry when it is changed, else by the ``as`` the page was opened with."""
    if entry is not None:
        mode = "text" if entry.get("is_text") else ("product" if entry.get("product") else "free")
    return {"product": ProductLineForm, "free": FreeLineForm, "text": TextLineForm}.get(mode, ProductLineForm)


# --- Crew places, vehicles, phases, open items, notes ---------------------------------------------------------------


def phase_choices(content: dict[str, Any]) -> list[tuple[Any, str]]:
    """The phases of the template by their place (the number the crew places and bookings name them with)."""
    choices: list[tuple[Any, str]] = [("", "–")]
    for index, phase in enumerate(content.get(tc.PHASES, [])):
        label = phase.get("title") or str(PhaseKind(phase["kind"]).label)
        choices.append((index, label))
    return choices


class CrewForm(_PeriodForm):
    """A crew place: job function, period, meeting point, phase."""

    job_function = forms.ModelChoiceField(label=_("Job function"), queryset=JobFunction.objects.none())
    planned_hours = forms.DecimalField(
        label=_("Planned hours"),
        required=False,
        min_value=0,
        max_digits=8,
        decimal_places=2,
        help_text=_("Only with a period of its own; otherwise the hours follow from the period."),
    )
    meeting_point = forms.CharField(label=_("Meeting point"), required=False, max_length=200)
    note = forms.CharField(label=_("Note"), required=False, widget=forms.Textarea(attrs={"rows": 2}))
    phase = forms.TypedChoiceField(label=_("Phase"), required=False, coerce=int, empty_value=None)

    def setup(self) -> None:
        """Fill in the choices of the fields from the content."""
        self.fields["job_function"].queryset = JobFunction.objects.filter(is_active=True).order_by("name")
        self.fields["phase"].choices = phase_choices(self.content)
        super().setup()


class VehicleForm(_PeriodForm):
    """A vehicle booking: the vehicle, period, phase."""

    product = forms.ModelChoiceField(label=_("Vehicle"), queryset=Product.objects.none())
    title = forms.CharField(label=_("Title"), required=False, max_length=200)
    note = forms.CharField(label=_("Note"), required=False, widget=forms.Textarea(attrs={"rows": 2}))
    only_trip_days = forms.BooleanField(label=_("Only days with trips (trailer)"), required=False)
    phase = forms.TypedChoiceField(label=_("Phase"), required=False, coerce=int, empty_value=None)

    def setup(self) -> None:
        """Fill in the choices of the fields from the content."""
        from rentalars.products.models import ProductKind

        self.fields["product"].queryset = Product.objects.filter(kind=ProductKind.VEHICLE, is_active=True).order_by(
            "name"
        )
        self.fields["phase"].choices = phase_choices(self.content)
        super().setup()


class PhaseForm(_PeriodForm):
    """A phase: its kind and place; it always has a period."""

    always_own = True

    kind = forms.ChoiceField(label=_("Phase"), choices=PhaseKind.choices)
    title = forms.CharField(label=_("Label"), required=False, max_length=120)
    location = forms.CharField(label=_("Place"), required=False, max_length=250)
    venue_site = forms.ModelChoiceField(
        label=_("Venue from the master data"), required=False, queryset=Venue.objects.none()
    )
    notes = forms.CharField(label=_("Notes"), required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def setup(self) -> None:
        """Fill in the choices of the fields from the content."""
        self.fields["venue_site"].queryset = Venue.objects.order_by("name")
        super().setup()


class OpenItemForm(_Form):
    """An open item: its text."""

    text = forms.CharField(label=_("Open item"), max_length=250)


class NotesForm(_Form):
    """The notes a new project gets and the default rental days."""

    notes = forms.CharField(
        label=_("Notes for the new project"), required=False, widget=forms.Textarea(attrs={"rows": 6})
    )
    rental_days = forms.IntegerField(
        label=_("Rental days"),
        required=False,
        min_value=1,
        max_value=999,
        help_text=_("Empty: the days follow from the period."),
    )


FORMS: dict[str, type[_Form]] = {
    tc.GROUPS: GroupForm,
    tc.CREW: CrewForm,
    tc.VEHICLES: VehicleForm,
    tc.PHASES: PhaseForm,
    tc.OPEN_ITEMS: OpenItemForm,
}
