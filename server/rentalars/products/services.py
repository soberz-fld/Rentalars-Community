# SPDX-License-Identifier: GPL-3.0-or-later
"""Business logic for products: article numbers, kits, presets.

Browser views and API views both call these functions (API-002).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.masterdata.models import Category, TaxRate, Unit
from rentalars.products.models import (
    DEFAULT_BILLING_MODE,
    BillingMode,
    KitComponent,
    Product,
    ProductKind,
)

if TYPE_CHECKING:
    from rentalars.availability.stock import ProductStock

#: ``{kit product id: [(component product id, quantity), …]}``
KitStructure = dict[int, list[tuple[int, int]]]


# --- Kits (PRD-022) -----------------------------------------------------------


def load_kit_structure() -> KitStructure:
    """Load which kit consists of which components, for all kits at once.

    The result is small (one entry per kit) and is passed to the functions
    below, so that resolving many kits costs two queries in total instead of
    one per kit.
    """
    structure: KitStructure = {
        kit_id: [] for kit_id in Product.objects.filter(kind=ProductKind.KIT).values_list("pk", flat=True)
    }
    for kit_id, component_id, quantity in KitComponent.objects.values_list("kit_id", "component_id", "quantity"):
        structure.setdefault(kit_id, []).append((component_id, quantity))
    return structure


def flatten_kit(product_id: int, structure: KitStructure, _path: frozenset[int] = frozenset()) -> dict[int, int]:
    """Resolve a product into the base products it finally consists of.

    A product that is not a kit resolves to itself with quantity 1. A kit
    resolves to its components; kits inside kits are resolved further and
    their quantities multiplied.

    Example: kit A = 2 × kit B + 1 × cable; kit B = 1 × speaker + 1 × cable.
    ``flatten_kit(A)`` returns ``{speaker: 2, cable: 3}``.

    Args:
        product_id: The product to resolve.
        structure: The result of :func:`load_kit_structure`.
        _path: Kits currently being resolved; protects against endless loops
            should a circular kit ever exist despite the validation.
    """
    if product_id not in structure:
        return {product_id: 1}
    if product_id in _path:
        return {}
    totals: dict[int, int] = {}
    for component_id, quantity in structure[product_id]:
        for base_id, base_quantity in flatten_kit(component_id, structure, _path | {product_id}).items():
            totals[base_id] = totals.get(base_id, 0) + quantity * base_quantity
    return totals


def kit_contains(kit_id: int, product_id: int, structure: KitStructure | None = None) -> bool:
    """Tell whether ``product_id`` appears anywhere inside the kit ``kit_id``."""
    if structure is None:
        structure = load_kit_structure()
    pending = [component_id for component_id, _quantity in structure.get(kit_id, [])]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if current == product_id:
            return True
        if current in seen:
            continue
        seen.add(current)
        pending.extend(component_id for component_id, _quantity in structure.get(current, []))
    return False


@transaction.atomic
def set_kit_components(kit: Product, components: Iterable[tuple[Product, int]]) -> None:
    """Replace the components of a kit.

    Args:
        kit: A product of the kind "kit".
        components: Pairs of ``(product, quantity)``. A product listed twice
            is merged into one component with the summed quantity.

    Raises:
        ValidationError: A component is not allowed, e.g. the kit itself.
    """
    wanted: dict[int, tuple[Product, int]] = {}
    for product, quantity in components:
        if quantity < 1:
            raise ValidationError(_("Component quantities start at 1."))
        _existing, previous = wanted.get(product.pk, (product, 0))
        wanted[product.pk] = (product, previous + quantity)

    existing = {component.component_id: component for component in kit.components.all()}
    for component_id, component in existing.items():
        if component_id not in wanted:
            component.delete()
    for position, (product, quantity) in enumerate(wanted.values()):
        component = existing.get(product.pk) or KitComponent(kit=kit, component=product)
        component.quantity = quantity
        component.position = position
        component.full_clean(exclude=["kit"] if kit.pk is None else None)
        component.save()


# --- Article numbers (PRD-007 to PRD-011) ------------------------------------


def suggest_article_number(category: Category) -> str:
    """Suggest the next free article number of a category (PRD-010).

    The suggestion continues after the highest number in use and keeps the
    width of that number, with a minimum of three digits.

    Example: with ``K-001`` to ``K-007`` in use the suggestion is ``K-008``;
    with ``L-0142`` as the highest it is ``L-0143``.
    """
    code = category.effective_code
    if not code:
        return ""
    highest_number = 0
    width = 3
    prefix = f"{code}-"
    for article_number in Product.objects.filter(article_number__startswith=prefix).values_list(
        "article_number", flat=True
    ):
        digits = article_number[len(prefix) :]
        if digits.isascii() and digits.isdigit() and int(digits) >= highest_number:
            highest_number = int(digits)
            width = max(3, len(digits))
    return f"{prefix}{highest_number + 1:0{width}d}"


def article_number_for(category: Category, product: Product | None = None) -> str:
    """The article number a product gets in this category (PRD-049; PRD-010).

    The number the product has stays as long as it fits the category – its
    letters are the category's code (PRD-008) –, so that choosing another
    category and then the first one again gives the old number back. Else,
    and for a new product, the next free number of the category.

    Example: K-012 moved to the category L gets L-008 if L-007 is the
    highest; moved back to K, it is K-012 again.
    """
    if product is not None and product.pk is not None:
        stored = Product.objects.filter(pk=product.pk).values_list("article_number", flat=True).first() or ""
        if category.effective_code and stored.split("-", 1)[0] == category.effective_code:
            return stored
    return suggest_article_number(category)


def check_article_number_change(product: Product, rights: Rights) -> None:
    """PRD-011: an article number used in projects is protected.

    Documents and packlists that were already printed carry the old number.
    Changing it therefore needs the special right "change article numbers
    that are in use".

    Raises:
        ValidationError: The number was changed without that right.
    """
    if product.pk is None:
        return
    stored = Product.objects.filter(pk=product.pk).values_list("article_number", flat=True).first()
    if stored is None or stored == product.article_number:
        return
    if product.is_used_in_projects() and not rights.has(SpecialRight.CHANGE_ARTICLE_NUMBERS):
        raise ValidationError(
            {"article_number": _("This article number is used in projects. Changing it requires a special right.")}
        )


@transaction.atomic
def save_product(product: Product, rights: Rights) -> Product:
    """Validate and save a product, including the rule of PRD-011 and – PRD-044 – the job function of a service.

    Raises:
        ValidationError: A rule is violated; the error names the field.
    """
    product.full_clean()
    check_article_number_change(product, rights)
    old_name = check_service_function(product)
    product.save()
    link_service_function(product, old_name)
    return product


#: PRD-044: the longest name of a service – it is also the name of its job function.
SERVICE_NAME_LENGTH = 80


def check_service_function(product: Product) -> str | None:
    """PRD-044: before a service is saved – can it be the service product of a job function of its name?

    A service product belongs to exactly one job function. A new one – or a
    product that becomes a service – brings its function along, named like
    the product; so the name must be free among the job functions and fit
    one. Returns the name the product had before, for
    :func:`link_service_function`.

    Raises:
        ValidationError: The name does not fit or belongs to another job function.
    """
    from rentalars.personnel.models import JobFunction

    old_name = Product.objects.filter(pk=product.pk).values_list("name", flat=True).first() if product.pk else None
    if product.kind != ProductKind.SERVICE:
        return old_name
    function = product.service_job_function
    renames_function = function is not None and old_name is not None and function.name == old_name
    if function is not None and not renames_function:
        return old_name
    if len(product.name) > SERVICE_NAME_LENGTH:
        raise ValidationError(
            {
                "name": _("The name of a service is also the name of its job function: at most %(count)d characters.")
                % {"count": SERVICE_NAME_LENGTH}
            }
        )
    others = JobFunction.objects.filter(name__iexact=product.name)
    if function is not None:
        others = others.exclude(pk=function.pk)
    other = others.select_related("service_product").first()
    if other is not None:
        raise ValidationError(
            {
                "name": _(
                    "The job function %(function)s exists already, with its service product %(product)s. "
                    "Choose another name, or change that product."
                )
                % {"function": other.name, "product": other.service_product.article_number}
            }
        )
    return old_name


def link_service_function(product: Product, old_name: str | None) -> None:
    """PRD-044: after a service was saved – give it its job function, or rename the function along.

    A service without job function gets one of its name. A service renamed
    renames its function along, as long as the two had the same name.
    """
    from rentalars.personnel.models import JobFunction

    if product.kind != ProductKind.SERVICE:
        return
    function = product.service_job_function
    if function is None:
        function = JobFunction(name=product.name, service_product=product)
        function.full_clean()
        function.save()
        product.job_function = function
    elif old_name is not None and old_name != product.name and function.name == old_name:
        function.name = product.name
        function.full_clean()
        function.save()


# --- Presets for new products (PRD-030) --------------------------------------


def presets_for_category(category: Category) -> dict[str, Any]:
    """Return the values a new product of this category starts with.

    The nearest category in the tree that sets a preset wins; the system
    defaults (default tax rate, unit "piece") fill what no category sets.
    """
    chain = list(reversed(category.ancestors_and_self()))
    main = category.main_category
    kind = main.default_product_kind or ProductKind.RENTAL
    unit = (
        next((c.default_unit for c in chain if c.default_unit_id), None)
        or Unit.objects.filter(is_active=True).order_by("id").first()
    )
    tax_rate = next((c.default_tax_rate for c in chain if c.default_tax_rate_id), None) or TaxRate.get_default()
    billing_mode = next((c.default_billing_mode for c in chain if c.default_billing_mode), "")
    if billing_mode not in BillingMode.values:
        billing_mode = DEFAULT_BILLING_MODE[kind]
    if main.is_customer_material:
        billing_mode = BillingMode.FLAT  # PRD-043: customer material is never charged
    return {
        "kind": kind,
        "unit": unit,
        "tax_rate": tax_rate,
        "billing_mode": billing_mode,
        "article_number": suggest_article_number(category),
    }


def presets_for_kind(kind: str, category: Category | None) -> dict[str, Any]:
    """PRD-046: the kind is chosen before the category and stays when the category brings its presets.

    The billing mode follows the kind unless the category presets this kind
    itself, with a billing mode of its own (PRD-030); customer material is
    always billed flat (PRD-043).
    """
    presets: dict[str, Any] = {"kind": kind}
    if category is not None and category.main_category.default_product_kind == kind:
        return presets
    if category is not None and category.holds_customer_material:
        presets["billing_mode"] = BillingMode.FLAT
    else:
        presets["billing_mode"] = DEFAULT_BILLING_MODE.get(kind, BillingMode.FLAT)
    return presets


def presets_for_owner(customer_id: int, category: Category | None) -> dict[str, Any]:
    """PRD-043: a new product of customer material for this customer – in the chosen category or the first for it.

    Returns nothing for an unknown customer, and only the owner if no
    category for customer material exists.
    """
    from rentalars.customers.models import Customer

    owner = Customer.objects.filter(pk=customer_id).first()
    if owner is None:
        return {}
    if category is not None and category.holds_customer_material:
        return {"owner": owner}
    found = Category.objects.filter(parent__isnull=True, is_customer_material=True, is_active=True).order_by("code")
    first = found.first()
    if first is None:
        return {"owner": owner}
    return {"category": first, **presets_for_category(first), "owner": owner}


# --- Duplicating a product (PRD-048) ----------------------------------

#: PRD-048: what a copy takes over as it is – everything that describes the product.
DUPLICATED_FIELDS = (
    "category",
    "name",
    "owner",
    "kind",
    "unit",
    "tax_rate",
    "billing_mode",
    "rental_scale_mode",
    "rental_scale",
    "surcharge_type",
    "vehicle_type",
    "trailer_billing",
    "buffer_before_hours",
    "buffer_after_hours",
    "minimum_stock",
    "pieces_per_product",
    "description",
    "note",
)

#: AUT-019: taken over only for somebody with the price right – the fields the product form shows with it.
DUPLICATED_PRICE_FIELDS = (
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

#: LOG-010: taken over only for somebody who may see purchase prices.
DUPLICATED_COST_FIELDS = ("cost_per_km", "cost_per_day")


def duplicate_values(source: Product, rights: Rights) -> dict[str, Any]:
    """The values a new product made from ``source`` starts with (PRD-048).

    Everything that describes the product, and the next free article number
    of its category (PRD-010). Prices only for somebody with the price right
    (AUT-019), internal costs only for somebody who may see purchase prices
    (LOG-010) – exactly what the product form shows them. Not taken over:
    the GTIN (it names one article in trade), the material (a model belongs
    to one product, PRD-002) and "deactivated" (a copy starts active). The
    components of a kit are copied when the copy is saved
    (:func:`save_duplicate`).
    """
    names = list(DUPLICATED_FIELDS)
    if rights.has(SpecialRight.PRICES):
        names += DUPLICATED_PRICE_FIELDS
    if rights.has(SpecialRight.PURCHASE_PRICES):
        names += DUPLICATED_COST_FIELDS
    values = {name: getattr(source, name) for name in names}
    values["article_number"] = suggest_article_number(source.category)
    return values


@transaction.atomic
def save_duplicate(product: Product, source: Product, rights: Rights) -> Product:
    """Save a new product made from ``source``, with the components of a kit (PRD-048).

    The components are taken over when both are kits – the copy may have
    become another kind in the form. A component the copy may not hold
    (customer material of another owner, PRD-043) stops the saving.

    Raises:
        ValidationError: The product or a component breaks a rule.
    """
    save_product(product, rights)
    if source.kind == ProductKind.KIT and product.kind == ProductKind.KIT:
        set_kit_components(
            product, [(part.component, part.quantity) for part in source.components.select_related("component")]
        )
    return product


# --- Customer material (PRD-043) ---------------------------------------------


@dataclass
class OwnedProduct:
    """A product of customer material with its stock and where it is kept (PRD-043)."""

    product: Product
    stock: ProductStock
    #: Storage locations with the most pieces first, e.g. ``["Halle 1 > Regal B", "Bandraum"]``.
    locations: list[str] = field(default_factory=list)


def customer_material(customer: Any) -> list[OwnedProduct]:
    """The products a customer keeps here, with stock and storage locations – for the customer's page (PRD-043).

    A fixed number of queries, however much material the customer has: the
    products, their stock, the places of their items and the paths of the
    storage locations. An item installed in a container is where its
    container is (MAT-038, one level).
    """
    from rentalars.availability.stock import NO_STOCK, stock_of_products
    from rentalars.masterdata.models import location_paths
    from rentalars.material.models import MaterialItem

    products = list(
        Product.objects.filter(owner=customer).select_related("category", "unit").order_by("article_number")
    )
    if not products:
        return []
    ids = [product.pk for product in products]
    stocks = stock_of_products(ids)
    places: dict[int, Counter[int | None]] = defaultdict(Counter)
    rows = (
        MaterialItem.objects.not_archived()
        # As ``for_product``: a filter the indexes serve, not one on the annotation (NFA-012).
        .filter(
            Q(product_override_id__in=ids)
            | Q(product_override__isnull=True, material_model__default_product_id__in=ids)
        )
        .with_product_id()
        .values_list("effective_product_id", "storage_location_id", "installed_in__storage_location_id", "quantity")
    )
    for product_id, own, container, quantity in rows:
        places[product_id][own or container] += quantity or 1
    paths = location_paths() if places else {}
    return [
        OwnedProduct(
            product=product,
            stock=stocks.get(product.pk, NO_STOCK),
            locations=[paths.get(pk, "") for pk, _count in places[product.pk].most_common() if pk in paths],
        )
        for product in products
    ]
