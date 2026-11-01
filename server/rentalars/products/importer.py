# SPDX-License-Identifier: GPL-3.0-or-later
"""Import of products from a spreadsheet (IMP-001, IMP-003, IMP-004).

One row per product. The article number is the key: a product that exists
is updated, a new one is created (IMP-004). The letter part of the article
number names the main category (PRD-008); the column "Category" can name a
subcategory of it. Unit, tax rate, kind and billing mode are looked up by
name; what the file leaves out comes from the presets of the category, as
for a product created by hand (PRD-030).

Customer material (PRD-043) names its owner in the column "Owner"
("Eigentümer"): the customer number or the name of the customer. An empty
cell leaves a product without owner – its category decides whether it needs
one.

Prices and the maximum discount (PRD-041) are only imported by somebody who
may see prices (AUT-017). PRD-047: "Preis" is the one
price of a product – for a sale product its sale price, as the exported list
shows it; "Verkaufspreis" is still read for sale products, and ignored with a
warning for every other product. Only the fields a column was assigned to are
written; everything else keeps what is in the database. The columns of the exported product list (IMP-005) are
recognised, so a list can be exported, changed and imported again.

IMP-011: the report names what becomes of every row – new, changed
with every field old → new, unchanged, or the errors of the row. Prices are
shown only to those who may see them.

LOG-002, LOG-005: a vehicle of the fleet has the kind "Fahrzeug";
the columns "Fahrzeugart" (KFZ or Anhänger), "Preis je km",
"Anhängerzuschlag je km", "Anhänger abrechnen" (je Tag or nach Kilometern)
carry its rates – with the price right –, "Interne Kosten je km" and
"Interne Kosten je Tag" its internal costs, with the right to see purchase
prices (LOG-010). The day price of a trailer is the column "Preis".
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from rentalars.accounts.rights import SpecialRight
from rentalars.core.audit import acting_as, record_event
from rentalars.core.import_rows import CHANGED, NEW, UNCHANGED, cells_by_number, label_from, snapshot
from rentalars.core.models import SystemSettings
from rentalars.core.tabular import (
    ImportField,
    ImportIssue,
    ImportReport,
    Progress,
    Table,
    cell_text,
    choice_of,
    messages_of,
    missing_required,
    no_progress,
    normalise,
    parse_bool,
    parse_decimal,
)
from rentalars.customers.models import Customer
from rentalars.masterdata.models import Category, TaxRate, Unit
from rentalars.products.models import (
    ARTICLE_NUMBER_PATTERN,
    BillingMode,
    Product,
    ProductKind,
    TrailerBilling,
    VehicleType,
)
from rentalars.products.services import check_service_function, link_service_function, presets_for_category

IMPORT_FIELDS: tuple[ImportField, ...] = (
    ImportField(
        "article_number", "Art.-Nr.", True, ("artikelnummer", "art.-nr", "art-nr", "artikel-nr.", "article no.")
    ),
    ImportField("name", "Name", True, ("artikelname", "bezeichnung", "produkt")),
    ImportField("category", "Kategorie", False, ("unterkategorie", "category")),
    ImportField("kind", "Art", False, ("produktart", "kind")),
    ImportField("price", "Preis", False, ("mietpreis", "preis (netto)", "tagespreis", "price")),
    ImportField("sale_price", "Verkaufspreis", False, ("verkaufspreis (netto)", "vk", "sale price")),
    # PRD-041: the heading of the column "Maximum discount" of the exported list.
    ImportField(
        "max_discount",
        "Höchstrabatt",
        False,
        ("höchster rabatt", "höchster rabatt in prozent", "max. rabatt", "maximaler rabatt", "maximum discount"),
    ),
    ImportField("unit", "Einheit", False, ("unit",)),
    ImportField("tax_rate", "Steuerart", False, ("steuersatz", "mwst", "ust", "tax rate")),
    ImportField("billing_mode", "Abrechnungsart", False, ("abrechnung", "billing mode")),
    ImportField("gtin", "GTIN/EAN", False, ("gtin", "ean", "barcode")),
    ImportField("description", "Beschreibung", False, ("description",)),
    ImportField("note", "Interne Notiz", False, ("notiz", "bemerkung", "note")),
    ImportField("minimum_stock", "Mindestbestand", False, ("minimum stock",)),
    # How many items one piece of the product consists of; empty leaves the value as it is.
    ImportField(
        "pieces_per_product",
        "Stück je Produkt",
        False,
        ("stück pro produkt", "exemplare je produkt", "pieces per product"),
    ),
    ImportField("active", "Aktiv", False, ("active",)),
    # PRD-043: the owner of customer material, by customer number or name.
    ImportField("owner", "Eigentümer", False, ("eigentum", "eigentümerin", "kunde", "owner")),
    # LOG-002, LOG-005, LOG-010: the type and the rates of a vehicle; the headings of the exported list.
    ImportField("vehicle_type", "Fahrzeugart", False, ("fahrzeugtyp", "vehicle type")),
    ImportField("price_per_km", "Preis je km", False, ("preis pro km", "km-preis", "price per km")),
    ImportField(
        "trailer_surcharge",
        "Anhängerzuschlag je km",
        False,
        ("anhängerzuschlag", "anhängerzuschlag pro km", "trailer surcharge per km"),
    ),
    ImportField("trailer_billing", "Anhänger abrechnen", False, ("anhänger abgerechnet", "trailer billed")),
    ImportField("cost_per_km", "Interne Kosten je km", False, ("interne kosten pro km", "internal cost per km")),
    ImportField("cost_per_day", "Interne Kosten je Tag", False, ("interne kosten pro tag", "internal cost per day")),
)

LABELS = {import_field.key: import_field.label for import_field in IMPORT_FIELDS}

#: Further words for the kinds and billing modes, besides their stored values and labels.
KIND_WORDS = {
    "miete": ProductKind.RENTAL,
    "mietprodukt": ProductKind.RENTAL,
    "verkauf": ProductKind.SALE,
    "verbrauch": ProductKind.SALE,
    "verbrauchsmaterial": ProductKind.SALE,
    "dienstleistung": ProductKind.SERVICE,
    # PRD-045: transport, travel costs, fees.
    "nebenkosten": ProductKind.INCIDENTAL,
    "set": ProductKind.KIT,
    "aufpreis": ProductKind.SURCHARGE,
    "zuschlag": ProductKind.SURCHARGE,
    "zumietung": ProductKind.SUBRENTAL,
    # LOG-002: vehicles and trailers of the fleet.
    "fahrzeug": ProductKind.VEHICLE,
    "fuhrpark": ProductKind.VEHICLE,
}
#: LOG-002: further words for the type of a vehicle.
VEHICLE_WORDS = {
    "kfz": VehicleType.CAR,
    "pkw": VehicleType.CAR,
    "lkw": VehicleType.CAR,
    "transporter": VehicleType.CAR,
    "anhänger": VehicleType.TRAILER,
    "kfz-anhänger": VehicleType.TRAILER,
    "hänger": VehicleType.TRAILER,
}
#: LOG-005: further words for how a trailer is billed.
TRAILER_BILLING_WORDS = {
    "pro tag": TrailerBilling.DAY,
    "je tag": TrailerBilling.DAY,
    "tag": TrailerBilling.DAY,
    "tagesmiete": TrailerBilling.DAY,
    "pro km": TrailerBilling.KM,
    "je km": TrailerBilling.KM,
    "km": TrailerBilling.KM,
    "pro kilometer": TrailerBilling.KM,
}
BILLING_WORDS = {
    "pro tag": BillingMode.DAILY_PER_PIECE,
    "täglich": BillingMode.DAILY_PER_PIECE,
    "pauschal": BillingMode.FLAT,
    "pauschale": BillingMode.FLAT,
    "pro stunde": BillingMode.HOURLY,
    "stündlich": BillingMode.HOURLY,
    "nach aufwand": BillingMode.EFFORT,
}

PRICE_FIELDS = frozenset({"price", "sale_price", "max_discount", "price_per_km", "trailer_surcharge"})

#: LOG-010: columns that need the right to see purchase prices.
COST_FIELDS = frozenset({"cost_per_km", "cost_per_day"})

#: LOG-005: the columns of the rates and costs of a vehicle and the product fields they fill.
VEHICLE_AMOUNTS = {
    "price_per_km": "price_per_km",
    "trailer_surcharge": "trailer_surcharge_per_km",
    "cost_per_km": "cost_per_km",
    "cost_per_day": "cost_per_day",
}


class _Lookup:
    """Units, tax rates and categories by the names a file may use."""

    def __init__(self) -> None:
        # By name, by abbreviation, by name without its addition in brackets ("Stück" for "Stück (Miete)").
        self.units: tuple[dict[str, list[Unit]], ...] = ({}, {}, {})
        for unit in Unit.objects.all():
            by_name, by_abbreviation, by_base = self.units
            by_name.setdefault(normalise(unit.name), []).append(unit)
            by_abbreviation.setdefault(normalise(unit.abbreviation), []).append(unit)
            base = unit.name.split(" (", 1)[0]
            if base != unit.name:
                by_base.setdefault(normalise(base), []).append(unit)
        self.tax_rates: dict[str, TaxRate] = {}
        for tax_rate in TaxRate.objects.all():
            self.tax_rates[normalise(tax_rate.name)] = tax_rate
            self.tax_rates.setdefault(normalise(f"{tax_rate.rate.normalize():f}"), tax_rate)
        self.main_categories = {
            category.code.upper(): category
            for category in Category.objects.filter(parent__isnull=True)
            if category.code
        }
        self.categories = list(Category.objects.exclude(parent__isnull=True))
        self._preset_units: dict[int, Unit | None] = {}
        self._owners: dict[str, Customer] = {}

    def unit(self, text: str, preferred: Unit | None = None) -> Unit:
        """The unit a file names, by name, abbreviation or name without its addition (ADM-011).

        "Stk." or "Stück" fit "Stück (Miete)" and "Stück (Verkauf)" alike;
        then the unit the category presets (``preferred``) wins if it is one
        of them, else the first by name.
        """
        key = normalise(text)
        candidates = next((found[key] for found in self.units if key in found), [])
        if not candidates:
            raise ValueError(_("There is no unit “%(value)s”.") % {"value": text})
        return preferred if preferred in candidates else candidates[0]

    def preset_unit(self, category: Category) -> Unit | None:
        """The unit a category presets (PRD-030), looked up once per category."""
        if category.pk not in self._preset_units:
            chain = reversed(category.ancestors_and_self())
            self._preset_units[category.pk] = next((c.default_unit for c in chain if c.default_unit_id), None)
        return self._preset_units[category.pk]

    def tax_rate(self, text: str) -> TaxRate:
        key = normalise(text.replace("%", "").replace(",", "."))
        key = key.rstrip("0").rstrip(".") if "." in key else key
        tax_rate = self.tax_rates.get(normalise(text)) or self.tax_rates.get(key)
        if tax_rate is None:
            raise ValueError(_("There is no tax rate “%(value)s”.") % {"value": text})
        return tax_rate

    def owner(self, text: str) -> Customer:
        """PRD-043: the customer a file names as owner – by customer number, else by name (case ignored)."""
        key = normalise(text)
        if key not in self._owners:
            found = list(Customer.objects.filter(number=text.strip())[:1]) or list(
                Customer.objects.filter(name__iexact=text.strip())[:2]
            )
            if not found:
                raise ValueError(_("There is no customer “%(value)s”.") % {"value": text})
            if len(found) > 1:
                raise ValueError(
                    _("Several customers are called “%(value)s”. Enter the customer number instead.") % {"value": text}
                )
            self._owners[key] = found[0]
        return self._owners[key]

    def category(self, code: str, text: str) -> Category:
        main = self.main_categories.get(code)
        if main is None:
            raise ValueError(_("There is no category with the code %(code)s.") % {"code": code})
        if not text or normalise(text) in {normalise(main.name), normalise(main.code)}:
            return main
        for category in self.categories:
            if category.main_category.pk == main.pk and normalise(text) in {
                normalise(category.name),
                normalise(category.path),
            }:
                return category
        raise ValueError(
            _("The category %(main)s has no subcategory “%(value)s”.") % {"main": main.name, "value": text}
        )


def import_products(
    table: Table,
    mapping: dict[str, int | None],
    *,
    dry_run: bool,
    rights: Any,
    actor: Any = "system:import",
    progress: Progress = no_progress,
) -> ImportReport:
    """Import products, or only report what the import would do (IMP-001).

    Args:
        table: The file content.
        mapping: Which column feeds which field.
        dry_run: ``True`` checks everything and writes nothing.
        rights: The rights of the one importing; prices need the price right.
        actor: Recorded in the change log.
        progress: Told how far the import got.

    Returns:
        The report. If ``report.ok`` is false, nothing was written.
    """
    report = ImportReport(dry_run=dry_run, rows_read=len(table.rows))
    # IMP-011: the outcome of every row; prices only for those who may see them.
    report.log.rights = rights
    report.log.use_labels(cells_by_number(table), label_from(mapping, "article_number", "name"))
    report.errors.extend(missing_required(mapping, IMPORT_FIELDS))
    mapped = {key for key, index in mapping.items() if index is not None}
    if mapped & PRICE_FIELDS and not rights.has(SpecialRight.PRICES):
        report.errors.append(ImportIssue(None, "", _("Importing prices needs the right to see prices.")))
    if mapped & COST_FIELDS and not rights.has(SpecialRight.PURCHASE_PRICES):
        report.errors.append(
            ImportIssue(None, "", _("Importing internal costs needs the right to see purchase prices."))
        )
    if report.errors:
        return report

    with acting_as(actor), transaction.atomic():
        lookup = _Lookup()
        seen: dict[str, int] = {}
        for position, (number, row) in enumerate(table.numbered_rows()):
            if position % 50 == 0:
                progress(10 + 80 * position // max(len(table.rows), 1))
            _import_row(number, row, mapping, mapped, lookup, seen, report)
        if not report.errors and not dry_run:
            record_event(
                SystemSettings.load(),
                "import.records",
                {"kind": _("products"), "created": report.created, "updated": report.updated, "rows": report.rows_read},
            )
        if dry_run or report.errors:
            transaction.set_rollback(True)
    report.errors.sort(key=lambda issue: issue.row or 0)
    return report


def _import_row(
    number: int,
    row: list[Any],
    mapping: dict[str, int | None],
    mapped: set[str],
    lookup: _Lookup,
    seen: dict[str, int],
    report: ImportReport,
) -> None:
    """Check and write one row; problems go to the report."""

    def cell(key: str) -> Any:
        index = mapping.get(key)
        return row[index] if index is not None and index < len(row) else None

    def problem(key: str, message: str) -> None:
        report.errors.append(ImportIssue(number, LABELS.get(key, ""), message))

    errors_before = len(report.errors)
    article_number = cell_text(cell("article_number")).upper().replace(" ", "")
    if not ARTICLE_NUMBER_PATTERN.match(article_number):
        problem(
            "article_number",
            _("“%(value)s” is not an article number such as K-005.") % {"value": article_number},
        )
        return
    if article_number in seen:
        problem(
            "article_number",
            _("The article number %(number)s already occurs in row %(row)s.")
            % {"number": article_number, "row": seen[article_number]},
        )
        return
    seen[article_number] = number
    code = article_number.split("-", 1)[0]

    product = Product.objects.filter(article_number=article_number).first()
    is_new = product is None
    before = _snapshot(product) if product is not None else None
    try:
        category = (
            lookup.category(code, cell_text(cell("category"))) if "category" in mapped or is_new else product.category  # type: ignore[union-attr]
        )
    except ValueError as error:
        problem("category", str(error))
        return
    if product is None:
        presets = presets_for_category(category)
        product = Product(
            article_number=article_number,
            category=category,
            kind=presets["kind"],
            unit=presets["unit"],
            tax_rate=presets["tax_rate"],
            billing_mode=presets["billing_mode"],
        )
    else:
        product.category = category

    name = cell_text(cell("name"))
    if not name:
        problem("name", _("The name is missing."))
    product.name = name or product.name
    for key in ("description", "note", "gtin"):
        if key in mapped:
            setattr(product, key, cell_text(cell(key)))
    try:
        if "kind" in mapped and cell_text(cell("kind")):
            product.kind = choice_of(cell("kind"), KIND_WORDS, ProductKind.choices)
            if is_new:
                from rentalars.products.models import DEFAULT_BILLING_MODE

                product.billing_mode = DEFAULT_BILLING_MODE[product.kind]
    except ValueError as error:
        problem("kind", str(error))
    try:
        if "billing_mode" in mapped and cell_text(cell("billing_mode")):
            product.billing_mode = choice_of(cell("billing_mode"), BILLING_WORDS, BillingMode.choices)
    except ValueError as error:
        problem("billing_mode", str(error))
    text = cell_text(cell("unit"))
    if "unit" in mapped and text:
        try:
            product.unit = lookup.unit(text, lookup.preset_unit(category))
        except ValueError as error:
            problem("unit", str(error))
    text = cell_text(cell("tax_rate"))
    if "tax_rate" in mapped and text:
        try:
            product.tax_rate = lookup.tax_rate(text)
        except ValueError as error:
            problem("tax_rate", str(error))
    _import_price(cell, mapped, product, problem, report, number)
    _import_vehicle(cell, mapped, product, problem)
    if "max_discount" in mapped:
        # PRD-041: an empty cell is no limit; the model checks 0 to 100.
        try:
            product.max_discount_percent = parse_decimal(
                cell("max_discount"), negative=_("A maximum discount must not be negative.")
            )
        except ValueError as error:
            problem("max_discount", str(error))
    if "minimum_stock" in mapped:
        text = cell_text(cell("minimum_stock"))
        if text and not (text.isascii() and text.isdigit()):
            problem("minimum_stock", _("“%(value)s” is not a whole number.") % {"value": text})
        else:
            product.minimum_stock = int(text) if text and int(text) else None
    if "pieces_per_product" in mapped:
        text = cell_text(cell("pieces_per_product"))
        if text and (not (text.isascii() and text.isdigit()) or int(text) < 1):
            problem("pieces_per_product", _("“%(value)s” is not a whole number above zero.") % {"value": text})
        elif text:
            product.pieces_per_product = int(text)
    if "owner" in mapped:
        text = cell_text(cell("owner"))
        try:
            product.owner = lookup.owner(text) if text else None
        except ValueError as error:
            problem("owner", str(error))
    if "active" in mapped:
        try:
            active = parse_bool(cell("active"))
        except ValueError as error:
            problem("active", str(error))
        else:
            if active is not None:
                product.is_active = active
    if len(report.errors) > errors_before:
        return

    try:
        with transaction.atomic():
            product.full_clean()
            after = _snapshot(product)
            if is_new:
                # PRD-044: a service brings its job function of the same name.
                old_name = check_service_function(product)
                product.save()
                link_service_function(product, old_name)
                outcome = NEW
            elif after != before:
                old_name = check_service_function(product)
                product.save()
                link_service_function(product, old_name)
                outcome = CHANGED
            else:
                outcome = UNCHANGED
    except ValidationError as error:
        for message in messages_of(error, _field_labels()):
            report.errors.append(ImportIssue(number, "", message))
        return
    # IMP-011: counted only now, when nothing can fail any more.
    if outcome == NEW:
        report.created += 1
    elif outcome == CHANGED:
        report.updated += 1
    else:
        report.unchanged += 1
    report.log.record(number, f"{article_number} {product.name}", outcome)
    if outcome == CHANGED and before is not None:
        report.log.compare(number, Product, before, after)


def _import_price(
    cell: Any, mapped: set[str], product: Product, problem: Any, report: ImportReport, number: int
) -> None:
    """The one price of the product from "Preis" – or "Verkaufspreis" (PRD-047).

    A sale product takes its sale price from "Verkaufspreis", else from
    "Preis" – the column the exported list shows it in; every other product
    its price from "Preis". A sale price of another product, as files from
    Carry it for rental products, is not imported: the row gets
    a warning, the rest of it is imported.
    """
    values: dict[str, Any] = {}
    for key in ("price", "sale_price"):
        if key in mapped:
            try:
                values[key] = parse_decimal(cell(key), negative=_("A price must not be negative."))
            except ValueError as error:
                problem(key, str(error))
                return
    if not values:
        return
    if product.kind == ProductKind.SALE:
        if values.get("sale_price") is not None or "price" not in values:
            product.sale_price = values.get("sale_price")
        else:
            product.sale_price = values["price"]
        product.price = None
        return
    if "price" in values:
        product.price = values["price"]
    if values.get("sale_price") is not None:
        report.warnings.append(
            ImportIssue(
                number,
                LABELS["sale_price"],
                _("Only sale products have a sale price; it is not imported. To sell it, create a sale product."),
            )
        )
    product.sale_price = None


def _import_vehicle(cell: Any, mapped: set[str], product: Product, problem: Any) -> None:
    """LOG-002, LOG-005: the type, the rates and the costs of a vehicle from their columns."""
    try:
        if "vehicle_type" in mapped:
            product.vehicle_type = choice_of(cell("vehicle_type"), VEHICLE_WORDS, VehicleType.choices) or ""
    except ValueError as error:
        problem("vehicle_type", str(error))
    try:
        if "trailer_billing" in mapped and cell_text(cell("trailer_billing")):
            product.trailer_billing = choice_of(cell("trailer_billing"), TRAILER_BILLING_WORDS, TrailerBilling.choices)
    except ValueError as error:
        problem("trailer_billing", str(error))
    for key, name in VEHICLE_AMOUNTS.items():
        if key in mapped:
            try:
                setattr(product, name, parse_decimal(cell(key), negative=_("A price must not be negative.")))
            except ValueError as error:
                problem(key, str(error))


#: The fields the import can change (IMP-004); IMP-011: they are compared for the preview.
SNAPSHOT_FIELDS = (
    "name",
    "category",
    "kind",
    "price",
    "sale_price",
    "unit",
    "tax_rate",
    "billing_mode",
    "gtin",
    "description",
    "note",
    "minimum_stock",
    "pieces_per_product",
    "max_discount_percent",
    "is_active",
    "owner",
    "vehicle_type",
    "price_per_km",
    "trailer_surcharge_per_km",
    "trailer_billing",
    "cost_per_km",
    "cost_per_day",
)


def _snapshot(product: Product) -> dict[str, Any]:
    """The values the import can change by field name, to tell an update from an unchanged row and show it."""
    return snapshot(product, SNAPSHOT_FIELDS)


def _field_labels() -> dict[str, str]:
    return {model_field.name: str(model_field.verbose_name) for model_field in Product._meta.fields}


def run_import(table: Table, mapping: dict[str, int | None], **options: Any) -> ImportReport:
    """The product import as registered in ``core.imports``."""
    return import_products(table, mapping, **options)


#: For the import page.
TITLE = gettext_lazy("Import products")
INTRODUCTION = gettext_lazy(
    "One row per product with a heading row. The article number decides: a product that exists is updated, "
    "a new one is created. Its letters name the main category; the column “Category” can name a subcategory. "
    "A list exported from the product list can be imported again."
)
