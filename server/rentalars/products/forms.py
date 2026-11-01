# SPDX-License-Identifier: GPL-3.0-or-later
"""Forms of the products module."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.core.forms import StyledForm, StyledModelForm, mark_required
from rentalars.customers.models import Customer
from rentalars.masterdata.models import Category, RentalScale, TaxRate, Unit
from rentalars.products.models import (
    DEFAULT_BILLING_MODE,
    STOCK_KINDS,
    Product,
    ProductKind,
    ScaleMode,
    SurchargeType,
    TrailerBilling,
    VehicleType,
)

#: AUT-019: fields only somebody with the price right sees; the maximum discount is one of them (PRD-041), the hour
#: tiers of a service too (PER-035), and whether its lines get surcharges for night, Sunday and holidays (PER-009).
#: LOG-005, LOG-006: the rates of a vehicle per kilometre as well.
PRICE_FIELDS = (
    "price",
    "sale_price",
    "calculation_note",
    "surcharge_percent",
    "max_discount_percent",
    "hours_limit",
    "price_above_limit",
    "time_surcharges",
    "price_per_km",
    "trailer_surcharge_per_km",
)

#: LOG-010, AUT-019: the internal costs of a vehicle – only with the right to see purchase prices.
COST_FIELDS = ("cost_per_km", "cost_per_day")

#: LOG-005: the fields of a vehicle; dropped for every other kind of product.
VEHICLE_FIELDS = (
    "vehicle_type",
    "trailer_billing",
    "price_per_km",
    "trailer_surcharge_per_km",
    "cost_per_km",
    "cost_per_day",
)

#: The kinds that are not vehicles, for the conditions of ``data-show-if`` and ``data-require-if``.
_NOT_VEHICLE = "|".join(kind for kind in ProductKind.values if kind != ProductKind.VEHICLE)

#: PRD-047: the kinds asked for the price – not a sale product (its sale price) or a vehicle.
_WITH_PRICE = "|".join(kind for kind in ProductKind.values if kind not in (ProductKind.VEHICLE, ProductKind.SALE))


def _is_number(text: str) -> bool:
    """Whether the text is a whole number of ASCII digits (``"²".isdigit()`` is true, ``int("²")`` fails)."""
    return text.isascii() and text.isdigit()


class ProductForm(StyledModelForm):
    """A product with article number, prices and billing (PRD-012 ff.).

    PRD-043: in a category for customer material the form asks for the owner
    instead of prices; the page shows the one or the other depending on the
    chosen category (``customer_material_categories``). What the page hid is
    not taken over: an owner outside such a category, prices inside one.

    LOG-002, LOG-005: a vehicle asks whether it is a motor vehicle or
    a trailer and for its rates – a motor vehicle per kilometre with the
    surcharge for trips with a trailer, a trailer per day (the price, with the
    rental scale) or per kilometre. The internal costs (LOG-010) need the
    right to see purchase prices.
    """

    class Meta:
        model = Product
        fields = [
            "category",
            "article_number",
            "name",
            "owner",
            "kind",
            "gtin",
            "unit",
            "tax_rate",
            "price",
            "sale_price",
            "billing_mode",
            "rental_scale_mode",
            "rental_scale",
            "surcharge_type",
            "surcharge_percent",
            "max_discount_percent",
            "hours_limit",
            "price_above_limit",
            "time_surcharges",
            "vehicle_type",
            "trailer_billing",
            "price_per_km",
            "trailer_surcharge_per_km",
            "cost_per_km",
            "cost_per_day",
            "buffer_before_hours",
            "buffer_after_hours",
            "minimum_stock",
            "pieces_per_product",
            "description",
            "note",
            "calculation_note",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "note": forms.Textarea(attrs={"rows": 2}),
            "calculation_note": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args: Any, rights: Rights, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.rights = rights
        self.fields["category"].queryset = Category.objects.filter(is_active=True)
        self.fields["category"].choices = Category.objects.choices()
        self.fields["unit"].queryset = Unit.objects.filter(is_active=True)
        self.fields["tax_rate"].queryset = TaxRate.objects.filter(is_active=True)
        # PRD-052: a form that does not send the number of pieces (older scripts) leaves it as it was, or one.
        self.fields["pieces_per_product"].required = False
        self.fields["rental_scale"].queryset = RentalScale.objects.filter(is_active=True)
        # PRD-043: chosen by typing (customers:suggest); the current owner stays choosable when deactivated since.
        owners = Customer.objects.filter(is_active=True)
        if self.instance.owner_id:
            owners = owners | Customer.objects.filter(pk=self.instance.owner_id)
        self.fields["owner"].queryset = owners
        self.fields["owner"].widget = forms.HiddenInput()
        self.customer_material_categories = [
            category.pk
            for category in Category.objects.in_tree_order(only_active=True)
            if category.holds_customer_material
        ]
        if not rights.has(SpecialRight.PRICES):
            # AUT-019: without the price right the price fields are not part of the form.
            for name in PRICE_FIELDS:
                del self.fields[name]
        if not rights.has(SpecialRight.PURCHASE_PRICES):
            # LOG-010: the internal costs of a vehicle only with the right to see purchase prices.
            for name in COST_FIELDS:
                del self.fields[name]
        # LOG-005: only shown for a trailer; a hidden select still sends "per day", a missing one is that too.
        self.fields["trailer_billing"].required = False
        self._mark_required()
        # PRD-046: the kind is asked first; choosing it reloads a new product's form (static/js/app.js).
        if self.instance.pk is None:
            self.fields["kind"].widget.attrs["data-reload-fields"] = "kind owner"

    @property
    def category_groups(self) -> list[tuple[str, list[tuple[Any, str]]]]:
        """The categories for the select, those that preset the chosen kind first (PRD-046).

        Returns ``(group label, [(value, label), …])`` pairs; without a
        chosen kind one group without label holds them all in tree order.
        """
        choices = [(value, label) for value, label in self.fields["category"].choices if value != ""]
        kind = self["kind"].value()
        if kind not in ProductKind.values:
            return [("", choices)]
        presets = {
            category.pk: category.main_category.default_product_kind
            for category in Category.objects.in_tree_order(only_active=True)
        }
        matching = [(value, label) for value, label in choices if presets.get(value) == kind]
        others = [(value, label) for value, label in choices if presets.get(value) != kind]
        if not matching:
            return [("", others)]
        groups = [(str(_("Categories for “%(kind)s”") % {"kind": ProductKind(kind).label}), matching)]
        if others:
            groups.append((str(_("Other categories")), others))
        return groups

    def _mark_required(self) -> None:
        """UIX-035: mark what the rules of the product require, as far as the choices made so far go.

        The price fields are optional in the form because which one is
        needed depends on the kind (PRD-013, ``Product._check_prices``): the
        price for everything but sale products and percentage surcharges,
        the sale price for sale products, the percentage for a percentage
        surcharge. The owner is needed in a category for customer material
        (PRD-043) – which then asks for no price –, a scale of its own when
        the product uses one.
        """
        # PER-037: a service may wait for its price – the job functions of the start data come without one.
        # LOG-005: a vehicle needs the price (per day) only as a trailer billed per day; a motor vehicle and a
        # trailer billed per kilometre need the price per kilometre instead.
        priced = "|".join(
            kind
            for kind in ProductKind.values
            if kind not in (ProductKind.SALE, ProductKind.SERVICE, ProductKind.VEHICLE)
        )
        car = f"kind={ProductKind.VEHICLE}&vehicle_type={VehicleType.CAR}"
        trailer = f"kind={ProductKind.VEHICLE}&vehicle_type={VehicleType.TRAILER}"
        conditions = {
            "price": f"kind={priced};{trailer}&trailer_billing={TrailerBilling.DAY}",
            "price_per_km": f"{car};{trailer}&trailer_billing={TrailerBilling.KM}",
            "vehicle_type": f"kind={ProductKind.VEHICLE}",
            "sale_price": f"kind={ProductKind.SALE}",
            "surcharge_percent": f"surcharge_type={SurchargeType.PERCENT}",
            "owner": self.customer_material_condition,
            "rental_scale": f"rental_scale_mode={ScaleMode.CUSTOM}",
        }
        for name, condition in conditions.items():
            if name in self.fields:
                mark_required(self.fields[name], condition)

    @property
    def owner_text(self) -> str:
        """What the owner field shows: the name of the chosen customer (PRD-043)."""
        value = self.data.get("owner") if self.is_bound else self.initial.get("owner", self.instance.owner_id)
        if hasattr(value, "pk"):
            return value.name
        owner = Customer.objects.filter(pk=value).first() if _is_number(str(value or "")) else None
        return owner.name if owner is not None else ""

    @property
    def shows_customer_material(self) -> bool:
        """Whether the category chosen now is one for customer material: the page asks for the owner (PRD-043)."""
        value = self["category"].value()
        return str(value or "") in {str(pk) for pk in self.customer_material_categories}

    @property
    def customer_material_condition(self) -> str:
        """``category=4|9`` for ``data-show-if``: the owner is asked for in these categories (PRD-043)."""
        # Without such a category a value no select can have, so that the owner is never asked for.
        return "category=" + ("|".join(str(pk) for pk in self.customer_material_categories) or "-")

    @property
    def own_material_condition(self) -> str:
        """``category=|1|2|…`` for ``data-show-if``: prices are asked for in every other category (PRD-043)."""
        others = [pk for pk, _label in self.fields["category"].choices if pk not in self.customer_material_categories]
        return "category=" + "|".join(str(pk) for pk in others)

    @property
    def vehicle_conditions(self) -> dict[str, str]:
        """LOG-005: ``data-show-if`` of the fields that depend on the kind "vehicle" and its type."""
        vehicle = f"kind={ProductKind.VEHICLE}"
        car = f"{vehicle}&vehicle_type={VehicleType.CAR}"
        trailer = f"{vehicle}&vehicle_type={VehicleType.TRAILER}"
        return {
            "vehicle": vehicle,
            "car": car,
            "trailer": trailer,
            # The price is the day price of a trailer; a motor vehicle has none. Surcharges: a fixed amount only.
            # PRD-047: a sale product has its sale price only.
            "price": f"surcharge_type={SurchargeType.FIXED}&kind={_WITH_PRICE};{trailer}",
            # A vehicle is billed by its rates, not by the billing mode; a trailer's day price takes the rental scale.
            "billing_mode": f"kind={_NOT_VEHICLE}",
            "rental_scale_mode": f"billing_mode=daily_piece|daily_kit&kind={_NOT_VEHICLE};{trailer}",
        }

    def clean(self) -> dict[str, Any]:
        """PRD-043: drop what the page hid for the chosen category – the owner, or the prices.

        LOG-005: the same for the kind: the rates of a vehicle for
        every other kind, and for a vehicle what its type does not have – the
        price (per day) and the internal cost per day of a motor vehicle, the
        trailer surcharge of a trailer, the sale price of both. A vehicle is
        billed as its kind presets: the day price of a trailer per day, with
        the rental scale.

        PRD-047: a sale product keeps its sale price
        only, every other product its price only – the page shows just that one.
        """
        cleaned = super().clean() or {}
        self._clean_vehicle(cleaned)
        if cleaned.get("kind") not in STOCK_KINDS and "pieces_per_product" in cleaned:
            # The page shows the number of pieces for rental and sale products only; for others it is one.
            cleaned["pieces_per_product"] = 1
        elif "pieces_per_product" in cleaned and cleaned["pieces_per_product"] is None:
            cleaned["pieces_per_product"] = self.instance.pieces_per_product if self.instance.pk else 1
        hidden_price = "price" if cleaned.get("kind") == ProductKind.SALE else "sale_price"
        if hidden_price in cleaned:
            cleaned[hidden_price] = None
        if cleaned.get("kind") != ProductKind.SERVICE:
            # PER-035: the hour tiers are shown for services only.
            for name in ("hours_limit", "price_above_limit"):
                if name in cleaned:
                    cleaned[name] = None
            # PER-009: so is the switch of the surcharges – only crew lines get them; the value stays.
            cleaned.pop("time_surcharges", None)
        category = cleaned.get("category")
        if category is None:
            return cleaned
        if category.holds_customer_material:
            for name in ("price", "sale_price", "surcharge_percent", "max_discount_percent"):
                if name in cleaned:
                    cleaned[name] = None
        else:
            cleaned["owner"] = None
        return cleaned

    def _clean_vehicle(self, cleaned: dict[str, Any]) -> None:
        """LOG-005: keep the rates of a vehicle only for a vehicle, and only those of its type."""
        if not cleaned.get("trailer_billing"):
            cleaned["trailer_billing"] = TrailerBilling.DAY
        if cleaned.get("kind") != ProductKind.VEHICLE:
            for name in VEHICLE_FIELDS:
                if name in cleaned:
                    cleaned[name] = "" if name == "vehicle_type" else None
            cleaned["trailer_billing"] = TrailerBilling.DAY
            return
        dropped = ["sale_price"]
        if cleaned.get("vehicle_type") == VehicleType.CAR:
            dropped += ["price", "cost_per_day"]
        elif cleaned.get("vehicle_type") == VehicleType.TRAILER:
            dropped += ["trailer_surcharge_per_km"]
        for name in dropped:
            if name in cleaned:
                cleaned[name] = None
        if "billing_mode" in cleaned:
            cleaned["billing_mode"] = DEFAULT_BILLING_MODE[ProductKind.VEHICLE]


class KitComponentForm(StyledForm):
    """Add one component to a kit (PRD-022)."""

    component = forms.ModelChoiceField(label=_("Product"), queryset=Product.objects.filter(is_active=True))
    quantity = forms.IntegerField(label=_("Quantity"), min_value=1, initial=1)


class AvailabilityQueryForm(StyledForm):
    """The period for the availability query on the product page (VFG-011)."""

    start = forms.DateTimeField(label=_("From"))
    end = forms.DateTimeField(label=_("Until"))

    def clean(self) -> dict[str, Any]:
        """The end must be after the start."""
        cleaned = super().clean() or {}
        if cleaned.get("start") and cleaned.get("end") and cleaned["end"] <= cleaned["start"]:
            self.add_error("end", _("The end must be after the start."))
        return cleaned


#: Number of empty rows offered below the existing rows of a scale.
EXTRA_SCALE_ROWS = 4


class RentalScaleForm(StyledForm):
    """A rental scale as an editable table of days and factors (PRD-015)."""

    name = forms.CharField(label=_("Name"), max_length=80)
    is_default = forms.BooleanField(
        label=_("Default scale"),
        required=False,
        help_text=_("Applies wherever neither product nor category name another scale."),
    )
    is_active = forms.BooleanField(label=_("Active"), required=False, initial=True)
    extra_day_increment = forms.DecimalField(
        label=_("Increment per further day"),
        min_value=0,
        decimal_places=3,
        initial=Decimal("0.5"),
        help_text=_("Added to the last factor for every rental day beyond the last row."),
    )

    def __init__(self, *args: Any, instance: RentalScale | None = None, **kwargs: Any) -> None:
        self.instance = instance or RentalScale()
        version = instance.current_version if instance else None
        rows = list(version.rows.all()) if version else []
        initial = kwargs.setdefault("initial", {})
        if instance is not None:
            initial.update(name=instance.name, is_default=instance.is_default, is_active=instance.is_active)
        if version is not None:
            initial["extra_day_increment"] = version.extra_day_increment
        super().__init__(*args, **kwargs)
        self.row_count = len(rows) + EXTRA_SCALE_ROWS
        for index in range(self.row_count):
            row = rows[index] if index < len(rows) else None
            self.fields[f"days_{index}"] = forms.IntegerField(
                label=_("Rental days"), min_value=1, required=False, initial=row.days if row else None
            )
            self.fields[f"factor_{index}"] = forms.DecimalField(
                label=_("Factor"), min_value=0, decimal_places=3, required=False, initial=row.factor if row else None
            )
        self.style_fields()

    @property
    def row_fields(self) -> list[tuple[forms.BoundField, forms.BoundField]]:
        """The table rows as pairs of (days field, factor field)."""
        return [(self[f"days_{index}"], self[f"factor_{index}"]) for index in range(self.row_count)]

    def clean_name(self) -> str:
        """Scale names are unique."""
        name = self.cleaned_data["name"].strip()
        if RentalScale.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(_("A rental scale with this name already exists."))
        return name

    def clean(self) -> dict[str, Any]:
        """Collect the filled rows; a row needs both days and factor."""
        cleaned = super().clean() or {}
        rows: list[tuple[int, Decimal]] = []
        for index in range(self.row_count):
            days = cleaned.get(f"days_{index}")
            factor = cleaned.get(f"factor_{index}")
            if days is None and factor is None:
                continue
            if days is None or factor is None:
                self.add_error(f"days_{index}", _("Fill in both rental days and factor, or leave the row empty."))
                continue
            rows.append((days, factor))
        if not rows and not self.errors:
            raise forms.ValidationError(_("A rental scale needs at least one row."))
        if len({days for days, _factor in rows}) != len(rows):
            raise forms.ValidationError(_("Every number of rental days may appear only once."))
        cleaned["rows"] = rows
        return cleaned
