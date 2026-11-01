# SPDX-License-Identifier: GPL-3.0-or-later
"""One price per product (one price per product; PRD-013, PRD-017).

The requirement: a rental product has one price only. The duplication of "price" and "sale price" is removed; whoever sells something creates a sale product.

* Every product that is not a sale product loses its sale price – in
  practice the rental products, the only other kind that could have one.
  No sale product is created in its place (decided).
* A rental product with a sale price but without a price – data from
  before the rule "Enter the price" – has only one price already: it becomes a sale product and keeps
  its sale price. Its lines were sales anyway (``defaults_from_product``
  sold "products without rental price"). Billed per day, it is billed flat
  from now on, as a sale product is (DEFAULT_BILLING_MODE); its lines were
  flat already. Its material models, items, kits and lines stay as they
  are: a sale product has stock (STOCK_KINDS) and may be part of a kit,
  availability and packing count it as before, and its lines stay sales.
  Customer material is never converted (it is never a sale product,
  PRD-043) – it just loses the sale price it must not have.
* Every sale product loses its price (the rental price a sale product could
  carry as well): it keeps its sale price, which it always had.

Each change is written to the change log of its product as
"Aktualisierung": a removed price with the value it had, a converted
product with its kind (rental → sale) and billing mode. Project lines are
not touched: a line keeps the price it took over (PRJ-015) – also a line
that sold a rental product, which stays a sale.

Reverse: the step cannot bring the prices back – the removed values are only
in the change log of the products, from where they can be entered again by
hand. Converted products stay sale products. Going back leaves the
products with their one price.
"""

from django.db import migrations
from django.utils import timezone

ACTOR = "Aktualisierung 0.9.1"


#: The billing modes of a daily rental; a converted product is billed flat instead, as a sale product is.
DAILY_MODES = ("daily_piece", "daily_kit")


def _log(apps, content_type, product, changes):
    """Write what changed of one product to its change log: ``{field: [old, new]}``."""
    apps.get_model("core", "AuditLogEntry").objects.create(
        timestamp=timezone.now(),
        actor_label=ACTOR,
        action="updated",
        content_type=content_type,
        object_id=str(product.pk),
        object_repr=f"{product.article_number} {product.name}"[:200],
        changes=changes,
    )


def remove_second_prices(apps, schema_editor):
    """The data step: convert rental products with a sale price only, then remove every second price."""
    product_model = apps.get_model("products", "Product")
    only_sale_price = list(
        product_model.objects.filter(kind="rental", price__isnull=True, sale_price__isnull=False, owner__isnull=True)
    )
    converted = {product.pk for product in only_sale_price}
    with_sale_price = list(
        product_model.objects.exclude(kind="sale").filter(sale_price__isnull=False).exclude(pk__in=converted)
    )
    with_price = list(product_model.objects.filter(kind="sale", price__isnull=False))
    if not only_sale_price and not with_sale_price and not with_price:
        return
    content_type = apps.get_model("contenttypes", "ContentType").objects.get_or_create(
        app_label="products", model="product"
    )[0]
    for product in only_sale_price:
        changes = {"kind": ["rental", "sale"]}
        if product.billing_mode in DAILY_MODES:
            changes["billing_mode"] = [product.billing_mode, "flat"]
            product.billing_mode = "flat"
        product_model.objects.filter(pk=product.pk).update(kind="sale", billing_mode=product.billing_mode)
        _log(apps, content_type, product, changes)
    for product in with_sale_price:
        _log(apps, content_type, product, {"sale_price": [str(product.sale_price), None]})
    for product in with_price:
        _log(apps, content_type, product, {"price": [str(product.price), None]})
    product_model.objects.filter(pk__in=[product.pk for product in with_sale_price]).update(sale_price=None)
    product_model.objects.filter(pk__in=[product.pk for product in with_price]).update(price=None)


class Migration(migrations.Migration):
    """The data step only – no field changes."""

    dependencies = [
        ("products", "0008_vehicles_090"),
        ("core", "0001_initial"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    # Reverse: nothing is restored – the removed prices are in the change log only (see above).
    operations = [migrations.RunPython(remove_second_prices, migrations.RunPython.noop)]
