# SPDX-License-Identifier: GPL-3.0-or-later
"""Start data for products: the general subrental product (PRD-040)."""

from __future__ import annotations

from decimal import Decimal

from rentalars.masterdata.models import Category, TaxRate, Unit
from rentalars.products.models import BillingMode, Product, ProductKind


def install() -> None:
    """Create ``E-001 Zumietung``, the product behind subrental suggestions (PRJ-054).

    One general product is enough: title, supplier and prices are set on each
    project line (PRD-040).
    """
    category = Category.objects.filter(parent__isnull=True, code="E").first()
    # ADM-011: the unit the category presets ("Stück (Miete)").
    unit = (
        (category.default_unit if category is not None else None)
        or Unit.objects.filter(name__in=("Stück (Miete)", "Stück")).order_by("-name").first()
        or Unit.objects.first()
    )
    tax_rate = TaxRate.get_default()
    if category is None or unit is None or tax_rate is None:
        return
    if Product.objects.filter(kind=ProductKind.SUBRENTAL).exists():
        return
    Product(
        article_number="E-001",
        category=category,
        name="Zumietung",
        unit=unit,
        tax_rate=tax_rate,
        kind=ProductKind.SUBRENTAL,
        billing_mode=BillingMode.FLAT,
        price=Decimal("0.00"),
        note="Allgemeines Produkt für zugemietetes Material. Bezeichnung, Lieferant und Preise stehen an der Position.",
    ).save()
