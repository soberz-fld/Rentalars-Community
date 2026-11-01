# SPDX-License-Identifier: GPL-3.0-or-later
"""The stock of products, counted from the material items (PRD-006).

A product has no stock field of its own. Its stock is the number of material
items assigned to it – through their model or individually (PRD-003) – plus
the quantities of bulk material (MAT-005).

Three numbers are distinguished:

``total``
    Everything that is not archived (not retired, sold or lost).
``operational``
    Fit for use: status "available" or "in use" (MAT-021).
``plannable``
    Operational *and* not permanently installed in another item. A receiver
    that is screwed into a rack always travels with the rack; it is never
    free on its own (MAT-036, VFG-016).

Example (acceptance scenario 13): product T-050 has the items 0310, 0311 and
0312. 0310 is permanently installed in rack 0500. Then total = 3,
operational = 3, plannable = 2.

Products of several pieces: a product can stand for several items of
its material – "K-005, XLR cable 1.5 m, 10-pack" is ten cables
(``Product.pieces_per_product``). The three numbers above then count
*products*, rounded down: 105 cables fit for use are 10 packs. The items
themselves are still counted, as ``total_pieces``, ``operational_pieces`` and
``plannable_pieces``; with one piece per product they are the same numbers.
Everything that plans, reserves and packs counts in products, so it uses the
first three; whoever deals with the items (choosing them for a packlist,
marking sold ones) uses the pieces.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from django.db.models import BooleanField, ExpressionWrapper, OuterRef, Q, Subquery, Sum

from rentalars.material.models import (
    ARCHIVED_STATUSES,
    OPERATIONAL_STATUSES,
    ConnectionType,
    MaterialItem,
    MaterialModel,
)
from rentalars.products.models import Product


@dataclass(frozen=True)
class ProductStock:
    """The stock figures of one product; see the module description."""

    total: int = 0
    operational: int = 0
    plannable: int = 0
    #: How many items make up one product (``Product.pieces_per_product``); the three numbers above are
    #: counted in products, rounded down.
    pieces_per_product: int = 1
    #: The same three numbers in items; ``None``: as many as products (one piece per product).
    total_pieces: int = field(default=None)  # type: ignore[assignment]
    operational_pieces: int = field(default=None)  # type: ignore[assignment]
    plannable_pieces: int = field(default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        """Fill in the pieces where they were not given: one piece per product."""
        for name, products in (
            ("total_pieces", self.total),
            ("operational_pieces", self.operational),
            ("plannable_pieces", self.plannable),
        ):
            if getattr(self, name) is None:
                object.__setattr__(self, name, products * self.pieces_per_product)

    @classmethod
    def from_pieces(cls, total: int, operational: int, plannable: int, pieces_per_product: int = 1) -> ProductStock:
        """The stock of a product from the items counted: products are the items divided by the pieces, rounded down."""
        per = max(pieces_per_product, 1)
        return cls(
            total=total // per,
            operational=operational // per,
            plannable=plannable // per,
            pieces_per_product=per,
            total_pieces=total,
            operational_pieces=operational,
            plannable_pieces=plannable,
        )

    @property
    def consists_of_pieces(self) -> bool:
        """Whether one product stands for several items."""
        return self.pieces_per_product > 1

    @property
    def not_operational(self) -> int:
        """Pieces that exist but are defective, in repair or blocked."""
        return self.total - self.operational

    @property
    def fixed_installed(self) -> int:
        """Operational pieces that only travel with their container."""
        return self.operational - self.plannable

    @property
    def left_over_pieces(self) -> int:
        """Plannable items that do not make a whole product, e.g. 5 cables of 105 for 10-packs."""
        return self.plannable_pieces - self.plannable * self.pieces_per_product


NO_STOCK = ProductStock()


def stock_of_products(product_ids: Iterable[int] | None = None) -> dict[int, ProductStock]:
    """Count the stock of several products.

    Args:
        product_ids: The products to count. ``None`` counts all products that
            have any material assigned.

    Returns:
        A mapping from product ID to its stock. Products without material are
        missing from the mapping; use ``result.get(product_id, NO_STOCK)``.

    How the counting is done, and why this way: an item belongs to the product
    named on the item itself, otherwise to the product of its model
    (PRD-003). Asking the database for exactly that ("the first of the two
    that is set") makes it read every item for every question, because no
    index can answer it – 20,000 items for the stock of a single cable. So
    the question is asked in a form the indexes can answer:

    1. Which models lead to the wanted products? (a few rows)
    2. Count the items of those models, and the items that name one of the
       wanted products themselves – grouped by everything that matters for
       the three stock figures.
    3. Work out the product of each group here, with the rule from above.

    The number of queries is fixed (two); it does not grow with the number of
    products.
    """
    wanted = None if product_ids is None else set(product_ids)
    models = MaterialModel.objects.all()
    if wanted is not None:
        if not wanted:
            return {}
        models = models.filter(default_product_id__in=wanted)
    # The pieces per product come with the same queries (a join), not with one of their own.
    product_of_model: dict[int, int | None] = {}
    pieces_of_model: dict[int, int] = {}
    for model_id, product_id, model_pieces in models.values_list(
        "pk", "default_product_id", "default_product__pieces_per_product"
    ):
        product_of_model[model_id] = product_id
        pieces_of_model[model_id] = model_pieces or 1

    items = MaterialItem.objects.exclude(status__in=ARCHIVED_STATUSES)
    if wanted is not None:
        # Items of the models found, plus items that name a wanted product
        # themselves. An item of such a model that names *another* product
        # is sorted out in step 3.
        items = items.filter(Q(material_model_id__in=list(product_of_model)) | Q(product_override_id__in=wanted))

    # One row per combination of model, own product, status and kind of
    # installation, each with the number of pieces (bulk rows count their quantity).
    rows = (
        items.annotate(is_installed=ExpressionWrapper(Q(installed_in__isnull=False), output_field=BooleanField()))
        .values(
            "material_model_id",
            "product_override_id",
            "status",
            "is_installed",
            "connection_type",
            "individually_rentable",
        )
        .annotate(pieces=Sum("quantity"))
        # The pieces per product of the item's own product – asked per group after counting, which costs
        # nothing noticeable; a join to the products for each of 20,000 items would.
        .annotate(
            own_pieces=Subquery(
                Product.objects.filter(pk=OuterRef("product_override_id")).values("pieces_per_product")[:1]
            )
        )
        .order_by()
    )

    totals: dict[int, list[int]] = {}
    per_product: dict[int, int] = {}
    for row in rows:
        product_id = row["product_override_id"] or product_of_model.get(row["material_model_id"])
        if product_id is None or (wanted is not None and product_id not in wanted):
            continue
        per_product[product_id] = (
            row["own_pieces"] if row["product_override_id"] else pieces_of_model.get(row["material_model_id"], 1)
        ) or 1
        counters = totals.setdefault(product_id, [0, 0, 0])
        pieces = int(row["pieces"] or 0)
        counters[0] += pieces
        if row["status"] not in OPERATIONAL_STATUSES:
            continue
        counters[1] += pieces
        travels_only_with_container = (
            row["is_installed"] and row["connection_type"] == ConnectionType.FIXED and not row["individually_rentable"]
        )
        if not travels_only_with_container:
            counters[2] += pieces
    return {
        product_id: ProductStock.from_pieces(total, operational, plannable, per_product.get(product_id, 1))
        for product_id, (total, operational, plannable) in totals.items()
    }


def stock_of_product(product_id: int) -> ProductStock:
    """Count the stock of a single product."""
    return stock_of_products([product_id]).get(product_id, NO_STOCK)
