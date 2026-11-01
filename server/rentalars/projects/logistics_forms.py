# SPDX-License-Identifier: GPL-3.0-or-later
"""Forms of the block "Logistik" of the planning (LOG-001 ff.).

Like the crew forms they do not save by themselves: ``changes()`` or
``values()`` give what the services in ``projects.logistics`` take – the same
functions the API calls (API-002).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.core.forms import RowLayoutMixin, StyledForm, mark_required
from rentalars.core.money import format_decimal
from rentalars.masterdata.models import Supplier, TaxRate
from rentalars.material.models import ARCHIVED_STATUSES, MaterialItem
from rentalars.products.models import Product, ProductKind
from rentalars.projects.forms import _period_of_phase, phase_field
from rentalars.projects.models import (
    Project,
    ProjectPhase,
    TripBilling,
    TripVehicle,
    VehicleBilling,
    VehicleLine,
    vehicle_name,
)


def fleet_choices(*, keep: VehicleLine | None = None) -> list[tuple[str, list[tuple[str, str]]]]:
    """The vehicles to book, grouped by product: each vehicle, and the product "still open" (LOG-002).

    Values are ``item-<id>`` for a vehicle and ``product-<id>`` for an open
    booking of the product. Archived vehicles are left out, deactivated
    products as well – except what ``keep`` books already.
    """
    products = Product.objects.filter(kind=ProductKind.VEHICLE).order_by("vehicle_type", "article_number")
    if keep is None:
        products = products.filter(is_active=True)
    else:
        products = products.filter(is_active=True) | Product.objects.filter(pk=keep.product_id)
    products = list(products.distinct())
    if not products:
        return []  # no fleet: one query, not two (NFA-014)
    items_by_product: dict[int, list[MaterialItem]] = {}
    items = (
        MaterialItem.objects.filter(
            material_model__default_product__kind=ProductKind.VEHICLE, product_override__isnull=True
        )
        | MaterialItem.objects.filter(product_override__kind=ProductKind.VEHICLE)
    ).exclude(status__in=ARCHIVED_STATUSES)
    for item in items.select_related("material_model__default_product", "product_override", "vehicle").order_by(
        "inventory_number"
    ):
        product = item.product
        if product is not None:
            items_by_product.setdefault(product.pk, []).append(item)
    groups = []
    for product in products:
        options = [(f"item-{item.pk}", vehicle_name(item)) for item in items_by_product.get(product.pk, [])]
        options.append((f"product-{product.pk}", str(_("still open, or from a supplier"))))
        groups.append((f"{product.article_number} {product.name} – {product.get_vehicle_type_display()}", options))
    return groups


def parse_fleet_choice(value: str) -> tuple[Product, MaterialItem | None]:
    """Read ``item-<id>`` or ``product-<id>`` back: the product and the vehicle, if one was chosen.

    Raises:
        forms.ValidationError: Nothing of the kind exists.
    """
    kind, _sep, number = (value or "").partition("-")
    if not number.isdigit():
        raise forms.ValidationError(_("Choose a vehicle or a trailer."))
    if kind == "item":
        item = (
            MaterialItem.objects.select_related("material_model__default_product", "product_override")
            .filter(pk=int(number))
            .first()
        )
        if item is None or item.product is None or item.product.kind != ProductKind.VEHICLE:
            raise forms.ValidationError(_("Choose a vehicle or a trailer."))
        return item.product, item
    product = Product.objects.filter(pk=int(number), kind=ProductKind.VEHICLE).first()
    if kind != "product" or product is None:
        raise forms.ValidationError(_("Choose a vehicle or a trailer."))
    return product, None


class VehicleAddForm(StyledForm):
    """The short form below the block "Logistik": which vehicle, for which phase or period (LOG-001)."""

    vehicle = forms.ChoiceField(label=_("Vehicle or trailer"))
    start = forms.DateTimeField(label=_("From"), required=False)
    end = forms.DateTimeField(label=_("Until"), required=False)

    def __init__(
        self,
        *args: Any,
        project: Project | None = None,
        phase: ProjectPhase | None = None,
        offer_new_phase: bool = False,
        **kwargs: Any,
    ) -> None:
        if project is not None:
            period = phase or project
            kwargs.setdefault("initial", {}).update(
                {"start": timezone.localtime(period.start), "end": timezone.localtime(period.end)}
            )
        kwargs.setdefault("auto_id", "vehicle-%s")
        super().__init__(*args, **kwargs)
        self.fields["vehicle"].choices = [("", _("– choose –")), *fleet_choices()]
        # Without a fleet the form is not shown – the phases are not looked up for nothing.
        self.fields["phase"] = (
            phase_field(project, offer_new=offer_new_phase)
            if self.has_fleet
            else forms.ChoiceField(label=_("Phase"), required=False, choices=[("", "")])
        )
        for field in self.fields.values():
            field.widget.attrs.setdefault("autocomplete", "off")

    @property
    def has_fleet(self) -> bool:
        """Whether there is anything to book: a vehicle product (LOG-002)."""
        return len(self.fields["vehicle"].choices) > 1

    @property
    def has_phases(self) -> bool:
        """Whether the project has phases to choose from (PRJ-080)."""
        return len(self.fields["phase"].choices) > 1

    @property
    def offers_new_phase(self) -> bool:
        """Whether the page script may offer "New phase …" in the list (PRJ-094)."""
        return "data-new-phase-url" in self.fields["phase"].widget.attrs

    def clean(self) -> dict[str, Any]:
        """The vehicle as product and item; a phase brings its period; the end after the start."""
        cleaned = super().clean() or {}
        if cleaned.get("vehicle"):
            try:
                cleaned["product"], cleaned["item"] = parse_fleet_choice(cleaned["vehicle"])
            except forms.ValidationError as error:
                self.add_error("vehicle", error)
        _period_of_phase(self, cleaned)
        if cleaned.get("start") and cleaned.get("end") and cleaned["end"] <= cleaned["start"]:
            self.add_error("end", _("The end must be after the start."))
        return cleaned


class VehicleLineForm(RowLayoutMixin, StyledForm):
    """Edit a booking in a dialog; prices need the price right, costs the right for purchase prices (AUT-019)."""

    vehicle = forms.ChoiceField(label=_("Vehicle or trailer"))
    title = forms.CharField(label=_("Title"), max_length=200)
    start = forms.DateTimeField(label=_("From"))
    end = forms.DateTimeField(label=_("Until"))
    supplier = forms.ModelChoiceField(
        label=_("From the supplier"),
        queryset=Supplier.objects.none(),
        required=False,
        empty_label=_("– own vehicle –"),
        help_text=_("Only for a vehicle that is rented in; its vehicle is then left empty."),
    )
    note = forms.CharField(label=_("Note"), required=False, widget=forms.Textarea(attrs={"rows": 2}))

    LAYOUT = (
        ("vehicle", "title"),
        ("phase",),
        ("start", "end"),
        ("billing", "only_trip_days"),
        ("price_per_km", "trailer_surcharge_per_km"),
        ("price_per_day", "rental_days"),
        ("discount_percent", "tax_rate"),
        ("supplier", "subrental_cost"),
        ("cost_per_km", "cost_per_day"),
        ("note",),
    )

    def __init__(
        self, *args: Any, line: VehicleLine, rights: Rights, offer_new_phase: bool = False, **kwargs: Any
    ) -> None:
        self.line = line
        names = ["title", "start", "end", "note", "supplier", "billing", "only_trip_days", "rental_days"]
        names += ["price_per_km", "trailer_surcharge_per_km", "price_per_day", "discount_percent", "tax_rate"]
        names += ["cost_per_km", "cost_per_day", "subrental_cost"]
        initial = kwargs.setdefault("initial", {})
        initial.update({name: getattr(line, name) for name in names})
        initial.update(
            {
                "phase": line.phase_id,
                "supplier": line.supplier_id,
                "tax_rate": line.tax_rate_id,
                "vehicle": f"item-{line.item_id}" if line.item_id else f"product-{line.product_id}",
                "start": timezone.localtime(line.start),
                "end": timezone.localtime(line.end),
            }
        )
        super().__init__(*args, **kwargs)
        self.fields["vehicle"].choices = fleet_choices(keep=line)
        if line.item_id and not any(
            value == f"item-{line.item_id}"
            for _group, options in self.fields["vehicle"].choices
            for value, _ in options
        ):
            # An archived vehicle stays shown for the booking it is in.
            self.fields["vehicle"].choices.append(
                (str(line.product), [(f"item-{line.item_id}", vehicle_name(line.item))])
            )
        self.fields["phase"] = phase_field(line.project, keep=line.phase, offer_new=offer_new_phase)
        suppliers = Supplier.objects.filter(is_active=True) | Supplier.objects.filter(pk=line.supplier_id or 0)
        self.fields["supplier"].queryset = suppliers.distinct().order_by("name")
        is_trailer = line.product.is_trailer
        if rights.has(SpecialRight.PRICES):
            if is_trailer:
                self.fields["billing"] = forms.ChoiceField(label=_("Billing"), choices=VehicleBilling.choices)
                self.fields["only_trip_days"] = forms.BooleanField(
                    label=_("Only days with trips"),
                    required=False,
                    help_text=_("Per day: count only the days on which the trailer drives, not the rental days."),
                )
                self.fields["price_per_day"] = forms.DecimalField(
                    label=_("Price per day (net)"), min_value=0, decimal_places=2
                )
                self.fields["rental_days"] = forms.IntegerField(
                    label=_("Rental days"),
                    min_value=1,
                    max_value=999,
                    required=False,
                    help_text=_("Empty: as material – the days of the booking's period, else the project's."),
                )
            self.fields["price_per_km"] = forms.DecimalField(
                label=_("Price per kilometre (net)"), min_value=0, decimal_places=2
            )
            if line.product.is_car:
                self.fields["trailer_surcharge_per_km"] = forms.DecimalField(
                    label=_("Trailer surcharge per kilometre (net)"),
                    min_value=0,
                    decimal_places=2,
                    help_text=_("Added on every trip on which it pulls a trailer."),
                )
            maximum = line.product.max_discount_percent
            self.fields["discount_percent"] = forms.DecimalField(
                label=_("Discount in percent"),
                min_value=0,
                max_value=100,
                decimal_places=2,
                required=False,
                help_text=(
                    _("The product allows at most %(percent)s %%.") % {"percent": format_decimal(maximum)}
                    if maximum is not None
                    else ""
                ),
            )
            rates = TaxRate.objects.filter(is_active=True) | TaxRate.objects.filter(pk=line.tax_rate_id)
            self.fields["tax_rate"] = forms.ModelChoiceField(
                label=_("Tax rate"), queryset=rates.distinct(), empty_label=None
            )
        if rights.has(SpecialRight.PURCHASE_PRICES):
            self.fields["cost_per_km"] = forms.DecimalField(
                label=_("Internal cost per kilometre"), min_value=0, decimal_places=2, required=False
            )
            if is_trailer:
                self.fields["cost_per_day"] = forms.DecimalField(
                    label=_("Internal cost per day"), min_value=0, decimal_places=2, required=False
                )
            self.fields["subrental_cost"] = forms.DecimalField(
                label=_("What the supplier charges"),
                min_value=0,
                decimal_places=2,
                required=False,
                help_text=_("For the whole booking; the cost instead of the costs per kilometre and day."),
            )
        self.style_fields()
        self.without_browser_history()

    def clean(self) -> dict[str, Any]:
        """The vehicle as product and item; the end after the start."""
        cleaned = super().clean() or {}
        if cleaned.get("vehicle"):
            try:
                cleaned["product"], cleaned["item"] = parse_fleet_choice(cleaned["vehicle"])
            except forms.ValidationError as error:
                self.add_error("vehicle", error)
        if cleaned.get("start") and cleaned.get("end") and cleaned["end"] <= cleaned["start"]:
            self.add_error("end", _("The end must be after the start."))
        return cleaned

    def changes(self) -> dict[str, Any]:
        """The submitted values that differ from the booking; an empty discount is none."""
        cleaned = dict(self.cleaned_data)
        cleaned.pop("vehicle", None)
        if "discount_percent" in cleaned and cleaned["discount_percent"] is None:
            cleaned["discount_percent"] = Decimal("0")
        phase = cleaned.get("phase")
        if phase is not None and phase.pk != self.line.phase_id:
            for name in ("start", "end"):
                if name not in self.changed_data:
                    cleaned.pop(name, None)
        return {name: value for name, value in cleaned.items() if getattr(self.line, name) != value}


class VehicleChoiceField(forms.ModelChoiceField):
    """A booking of the project, by its title and licence plate."""

    def label_from_instance(self, obj: Any) -> str:
        """The booking in short: "Sprinter (B-RL 123)"."""
        return obj.label


class TripVehicleForm(RowLayoutMixin, StyledForm):
    """A motor vehicle on a trip: trailer, kilometres, what is charged (LOG-006, LOG-007)."""

    trip_key = forms.ChoiceField(label=_("Trip"))
    vehicle_line = VehicleChoiceField(label=_("Vehicle"), queryset=VehicleLine.objects.none(), empty_label=None)
    trailer_line = VehicleChoiceField(
        label=_("Trailer"), queryset=VehicleLine.objects.none(), required=False, empty_label=_("– no trailer –")
    )
    planned_km = forms.DecimalField(label=_("Planned km"), min_value=0, decimal_places=1, required=False)
    driven_km = forms.DecimalField(label=_("Driven km"), min_value=0, decimal_places=1, required=False)
    note = forms.CharField(label=_("Note"), max_length=500, required=False)

    LAYOUT = (
        ("trip_key",),
        ("vehicle_line", "trailer_line"),
        ("planned_km", "driven_km"),
        ("billing", "flat_price"),
        ("note",),
    )

    def __init__(
        self,
        *args: Any,
        project: Project,
        trips: list[Any],
        rights: Rights,
        use: TripVehicle | None = None,
        trip_key: str = "",
        **kwargs: Any,
    ) -> None:
        self.use = use
        initial = kwargs.setdefault("initial", {})
        if use is not None:
            initial.update(
                {
                    name: getattr(use, name)
                    for name in ("trip_key", "planned_km", "driven_km", "billing", "flat_price", "note")
                }
            )
            initial.update({"vehicle_line": use.vehicle_line_id, "trailer_line": use.trailer_line_id})
        elif trip_key:
            initial["trip_key"] = trip_key
        super().__init__(*args, **kwargs)
        choices = [(trip.key, f"{timezone.localtime(trip.start):%d.%m. %H:%M} {trip.title}") for trip in trips]
        if use is not None and use.trip_key not in {key for key, _label in choices}:
            choices.append((use.trip_key, str(_("a trip that is gone"))))
        self.fields["trip_key"].choices = choices
        lines = project.vehicle_lines.select_related("product", "item__vehicle", "supplier")
        self.fields["vehicle_line"].queryset = lines.filter(product__vehicle_type="car")
        self.fields["trailer_line"].queryset = lines.filter(product__vehicle_type="trailer")
        if not self.fields["trailer_line"].queryset.exists():
            del self.fields["trailer_line"]
        if rights.has(SpecialRight.PRICES):
            self.fields["billing"] = forms.ChoiceField(
                label=_("Charged"),
                choices=TripBilling.choices,
                initial=TripBilling.DRIVEN,
                help_text=_("Driven kilometres: until they are entered, the planned ones stand in as an estimate."),
            )
            self.fields["flat_price"] = forms.DecimalField(
                label=_("Flat rate for the trip (net)"),
                min_value=0,
                decimal_places=2,
                required=False,
                help_text=_("Only with “flat rate”: vehicle, surcharge and a trailer per kilometre together."),
            )
            # UIX-051 (UIX-035): required with the flat rate (``clean``).
            mark_required(self.fields["flat_price"], f"{self.add_prefix('billing')}={TripBilling.FLAT}")
        self.style_fields()
        self.without_browser_history()

    def clean(self) -> dict[str, Any]:
        """A flat rate needs its price."""
        cleaned = super().clean() or {}
        if cleaned.get("billing") == TripBilling.FLAT and cleaned.get("flat_price") is None:
            self.add_error("flat_price", _("Enter the flat rate for the trip."))
        return cleaned

    def values(self) -> dict[str, Any]:
        """What the services take: for a new vehicle on a trip everything, for an existing one what changed."""
        cleaned = dict(self.cleaned_data)
        if self.use is None:
            return {name: value for name, value in cleaned.items() if value is not None or name == "trailer_line"}
        return {name: value for name, value in cleaned.items() if getattr(self.use, name) != value}
