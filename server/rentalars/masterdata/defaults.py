# SPDX-License-Identifier: GPL-3.0-or-later
"""Start data for master data: units, tax rates, categories, rental scale (ADM-011).

The lists include the category C
"Fremdmaterial" for customer material (PRD-043), the default
storage location "Hauptlager" (MAT-052) and the category FZ "Fuhrpark"
(LOG-002).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from rentalars.masterdata.models import (
    Category,
    CategoryField,
    FieldType,
    ProductKindDefault,
    RentalScale,
    StorageLocation,
    TaxRate,
    Unit,
)

#: PRD-012, ADM-011: the units offered for products, with abbreviations in the style of the earlier ones
#: ("Stk.", "Std.", "psch.") and the symbols where there are some ("km", "l", "m", "kg"). Pieces and sets
#: come twice, for renting and for selling; the documents show the abbreviation. "Stück (Miete)" comes first:
#: it is the unit of a new product whose category presets none.
UNITS = [
    ("Stück (Miete)", "Stk."),
    ("Stück (Verkauf)", "Stk."),
    ("Set (Miete)", "Set"),
    ("Set (Verkauf)", "Set"),
    ("Stunde", "Std."),
    ("Tag", "Tag"),
    ("Kilometer", "km"),
    ("Pauschal", "psch."),
    ("Angefangener Liter", "l"),
    ("Angefangener Meter", "m"),
    ("Angefangenes Kilogramm", "kg"),
]

#: PRD-027, ADM-011: code, name, has own stock, preset product kind, preset unit. E and D keep their
#: meaning: E is where subrentals go (the general product E-001 "Zumietung", PRD-040), D the services.
MAIN_CATEGORIES = [
    ("T", "Ton", True, ProductKindDefault.RENTAL, "Stück (Miete)"),
    ("L", "Licht", True, ProductKindDefault.RENTAL, "Stück (Miete)"),
    ("M", "Video/Medien", True, ProductKindDefault.RENTAL, "Stück (Miete)"),
    ("R", "Rigging/Traverse", True, ProductKindDefault.RENTAL, "Stück (Miete)"),
    ("K", "Kabel", True, ProductKindDefault.RENTAL, "Stück (Miete)"),
    ("V", "Verkauf", True, ProductKindDefault.SALE, "Stück (Verkauf)"),
    ("E", "Extern zugemietetes Material", False, ProductKindDefault.SUBRENTAL, "Stück (Miete)"),
    ("D", "Veranstaltungstechnik-Dienstleistung", False, ProductKindDefault.SERVICE, "Stunde"),
    # PRD-043: material of customers stored here, e.g. the gear of a band – with an owner, never with a price.
    ("C", "Fremdmaterial", True, ProductKindDefault.RENTAL, "Stück (Miete)"),
    # PRD-045: transport, travel costs, fees – planned like material, without stock.
    ("N", "Nebenkosten", False, ProductKindDefault.INCIDENTAL, "Pauschal"),
    # LOG-002: vehicles and trailers of the fleet – items of their own, billed per kilometre and day,
    # planned under "Logistik".
    ("FZ", "Fuhrpark", True, ProductKindDefault.VEHICLE, "Stück (Miete)"),
]

#: PRD-043: the main categories whose products belong to a customer.
CUSTOMER_MATERIAL_CODES = frozenset({"C"})

#: MAT-009: the category-specific value of some start categories. MAT-049: the power is a field of every material model.
CATEGORY_FIELDS = {
    "K": ("Länge", FieldType.NUMBER, "m"),
}

#: MAT-052: the storage location new items get unless somebody chooses another one.
DEFAULT_STORAGE_LOCATION = "Hauptlager"

#: PRD-015, ADM-011: the delivered rental scale "Standardstaffel" – 1 day 1.0 up to 7 days 3.5; every further
#: day adds 0.3 to the factor of the last row (PRD-038: the increment per further day).
DEFAULT_SCALE_NAME = "Standardstaffel"
DEFAULT_SCALE_ROWS = [
    (1, Decimal("1.0")),
    (2, Decimal("1.5")),
    (3, Decimal("1.75")),
    (4, Decimal("2.0")),
    (5, Decimal("2.4")),
    (6, Decimal("2.75")),
    (7, Decimal("3.5")),
]
DEFAULT_SCALE_INCREMENT = Decimal("0.3")


def install() -> None:
    """Create units, tax rates, the main categories and the default rental scale (ADM-011).

    Whatever exists already – a unit or scale of the same name, a main
    category with the same code or name – is kept as it is.
    """
    units = {}
    for name, abbreviation in UNITS:
        unit = Unit.objects.filter(name__iexact=name).first()
        if unit is None:
            unit = Unit(name=name, abbreviation=abbreviation)
            unit.save()
        units[name] = unit

    # PRD-016: 19 % is the default for new products; tax-free is the alternative.
    if not TaxRate.objects.exists():
        TaxRate(name="19 %", rate=Decimal("19.00"), valid_from=datetime.date(2007, 1, 1), is_default=True).save()
        TaxRate(name="steuerfrei", rate=Decimal("0.00"), valid_from=datetime.date(2007, 1, 1)).save()

    if not RentalScale.objects.filter(name__iexact=DEFAULT_SCALE_NAME).exists():
        scale = RentalScale(
            name=DEFAULT_SCALE_NAME, is_default=not RentalScale.objects.filter(is_default=True).exists()
        )
        scale.save()
        scale.publish(DEFAULT_SCALE_ROWS, extra_day_increment=DEFAULT_SCALE_INCREMENT)

    main = Category.objects.filter(parent__isnull=True)
    for code, name, has_own_stock, kind, unit_name in MAIN_CATEGORIES:
        if main.filter(code=code).exists() or main.filter(name__iexact=name).exists():
            continue
        category = Category(
            name=name,
            code=code,
            has_own_stock=has_own_stock,
            default_product_kind=kind,
            default_unit=units[unit_name],
            is_customer_material=code in CUSTOMER_MATERIAL_CODES,
        )
        category.save()
        if code in CATEGORY_FIELDS:
            label, field_type, unit = CATEGORY_FIELDS[code]
            CategoryField(category=category, label=label, field_type=field_type, unit=unit, position=1).save()

    # MAT-052: "Hauptlager" as the default storage location, unless there are locations of one's own.
    if not StorageLocation.objects.exists():
        StorageLocation(name=DEFAULT_STORAGE_LOCATION, is_default=True).save()
