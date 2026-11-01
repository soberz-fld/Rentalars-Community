# SPDX-License-Identifier: GPL-3.0-or-later
"""Template tags for accessories and replacements (PRD-023, VFG-015)."""

from __future__ import annotations

from typing import Any

from django import template

from rentalars.products import suggestions
from rentalars.products.relation_models import SUGGESTIBLE_KINDS, RelationKind

register = template.Library()


@register.inclusion_tag("products/_relations.html", takes_context=True)
def product_relations(context: template.Context, product: Any, *, editable: bool = True) -> dict[str, Any]:
    """The panel with the accessories and replacements of a product.

    On the page of a product they can be changed (``editable`` and the right to write products); on the page of
    a material model the panel only shows them.
    """
    request = context.get("request")
    can = context.get("can") or {}
    write = bool(editable and can.get("write", {}).get("products"))
    relations = suggestions.relations_of(product)
    used_as = suggestions.used_as_relation(product)
    return {
        "product": product,
        "accessories": relations[RelationKind.ACCESSORY],
        "replacements": relations[RelationKind.REPLACEMENT],
        "used_as": used_as,
        "can_write": write,
        "suggestible": product.kind in SUGGESTIBLE_KINDS,
        "show": product.kind in SUGGESTIBLE_KINDS
        and (
            write
            or bool(relations[RelationKind.ACCESSORY])
            or bool(relations[RelationKind.REPLACEMENT])
            or bool(used_as)
        ),
        "csrf_token": context.get("csrf_token"),
        "request": request,
        "can": can,
        "is_kit": product.is_kit,
        "editable": editable,
        "may_write_products": bool(can.get("write", {}).get("products")),
    }


@register.inclusion_tag("projects/_suggestions_slot.html", takes_context=True)
def suggestions_slot(context: template.Context, project: Any, *, offer: bool = False) -> dict[str, Any]:
    """The slot in the planning (or the offer step) that fetches the suggestions of a project.

    Renders nothing at all as long as no accessory or replacement is named anywhere (one cheap query), so a
    shop that does not use the feature sees no change.
    """
    return {"project": project, "offer": offer, "show": suggestions.has_relations()}
