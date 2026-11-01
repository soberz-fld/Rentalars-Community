# SPDX-License-Identifier: GPL-3.0-or-later
"""Customer material in projects (PRJ-096, PRD-043).

A service provider may keep the gear of a customer in the warehouse – the
mixing desk and the multicores of a band – and take it along to the
customer's events, where it is set up together with the provider's own
material. In the material management such gear is a product of a category
marked "customer material" (the start data has C "Fremdmaterial"), with the
customer as its owner (``Product.owner``), and with models and items like
any other material: weight, dimensions, storage location, IDs and labels.

In a project it is a line like any other, with these rules:

* **Only for its owner.** A line of customer material can only be planned
  in a project of the owner – a subproject has the customer of its whole
  project, so its parts count as well. Anywhere else it is refused,
  whether through the page, a template, a copy or the API.
* **Never charged.** The line has no price, no discount, and it cannot be
  optional or an alternative: it is taken along, that is all. The price
  calculation gives it the amount 0 and keeps it out of every sum, the
  shares of a group's flat price and the taxes (``projects.pricing``). The
  planning and the price overview show it without price columns, with the
  hint that it is the customer's own material; documents for the customer
  say the same and leave the price empty; the invoice leaves it out.
* **Counted like own material.** Its availability is checked as for any
  product with stock: it can be short when items are defective or out with
  another project of the same customer. A shortage is shown, but no
  subrental is suggested – nobody else can supply the customer's own gear.
* **Packed like own material.** The packlist lists it with weight, volume
  and storage location, marked as customer material; issue and return work
  as usual.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.utils.translation import gettext as _

from rentalars.products.models import BillingMode

if TYPE_CHECKING:
    from rentalars.products.models import Product
    from rentalars.projects.models import MaterialLine, Project

ZERO = Decimal("0")


def may_plan(product: Product, project: Project) -> bool:
    """Whether a product may be planned in a project as far as its owner goes (PRJ-096).

    Own material may be planned everywhere; customer material only in a
    project of its owner. A subproject always has the customer of its whole
    project (PRJ-045), so its own customer is the one to compare.
    """
    return product.owner_id is None or product.owner_id == project.customer_id


def refusal(product: Product) -> str:
    """The message for customer material planned in a project of somebody else (PRJ-096)."""
    return _("%(product)s is customer material of %(owner)s and can only be planned in projects of this customer.") % {
        "product": f"{product.article_number} {product.name}",
        "owner": product.owner.name,
    }


def clean_line(line: MaterialLine, errors: dict[str, Any]) -> None:
    """Check a line of customer material: the owner's project, no price, no discount, no option (PRJ-096).

    Called from ``MaterialLine.clean`` for a line whose product has an
    owner. Billing is set to "flat" so that no rental days or scale can
    enter the line. The messages name the field that is wrong.
    """
    product = line.product
    if line.project_id is not None and not may_plan(product, line.project):
        errors["product"] = refusal(product)
    line.billing_mode = BillingMode.FLAT
    line.scale_version = None
    if line.is_sale:
        errors["is_sale"] = _("Customer material cannot be sold.")
    if line.unit_price != ZERO or line.manual_scale_factor is not None or line.surcharge_percent is not None:
        errors["unit_price"] = _("Customer material is taken along without charge; it has no price.")
    if line.discount_percent:
        errors["discount_percent"] = _("Customer material is not charged, so it gets no discount.")
    if line.variant:
        errors["variant"] = _("Customer material is taken along; it cannot be optional or an alternative.")
