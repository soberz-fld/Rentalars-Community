# SPDX-License-Identifier: GPL-3.0-or-later
"""API for accessories, replacements and the suggestions made from them (PRD-023, VFG-015).

The same functions as the pages (API-002), in :mod:`rentalars.products.suggestions`:

* ``GET  /products/{id}/relations`` – the accessories and replacements of a product, each in its order
* ``POST /products/{id}/relations`` – name one: ``{"related_product": 7, "kind": "accessory", "quantity_per_piece":
  "1", "note": "", "is_required": false, "both_ways": false}``
* ``PATCH /products/{id}/relations/{relation}`` – change ``note``, ``is_required``, ``quantity_per_piece``
* ``POST /products/{id}/relations/{relation}/move`` – ``{"direction": "up"}`` or ``"down"``
* ``POST /products/{id}/relations/{relation}/remove`` – remove it
* ``GET  /projects/{id}/suggestions`` – what the planning of a project suggests: accessories not planned yet and,
  for who may see availability, replacements for short lines with the free pieces of each
* ``POST /projects/{id}/suggestions/{relation}/add`` – take a suggestion into the planning: ``{"line": 5,
  "quantity": 4}`` (both optional)
* ``POST /projects/{id}/suggestions/dismiss`` – ``{"relations": [3, 4]}``; ``POST .../restore`` brings them back

A suggestion is only a hint: nothing is added without the ``add`` call.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Module, SpecialRight
from rentalars.api.inputs import int_or_400, str_or_400
from rentalars.api.views import ModuleAPIView, body_of
from rentalars.products import suggestions
from rentalars.products.models import Product
from rentalars.products.relation_models import ProductRelation, RelationKind
from rentalars.projects.access import ProjectAccess, project_for


def relation_document(relation: ProductRelation) -> dict[str, Any]:
    """One accessory or replacement as the API shows it."""
    related = relation.related_product
    return {
        "id": relation.pk,
        "product": relation.product_id,
        "related_product": related.pk,
        "article_number": related.article_number,
        "name": related.name,
        "kind": relation.kind,
        "position": relation.position,
        "quantity_per_piece": relation.quantity_per_piece,
        "note": relation.note,
        "is_required": relation.is_required,
    }


def relations_document(product: Product) -> dict[str, Any]:
    """All accessories and replacements of a product."""
    grouped = suggestions.relations_of(product)
    return {
        "product": product.pk,
        "accessories": [relation_document(row) for row in grouped[RelationKind.ACCESSORY]],
        "replacements": [relation_document(row) for row in grouped[RelationKind.REPLACEMENT]],
    }


def suggestions_document(found: suggestions.Suggestions, *, sees_availability: bool) -> dict[str, Any]:
    """The suggestions of a project; numbers of availability only for who may see them (AUT-032)."""
    accessories = []
    for entry in found.accessories:
        accessories.append(
            {
                "relation": entry.relation.pk,
                # (R3-4) every relation that names the accessory at a product of the planning
                "relations": [named.pk for named in entry.relations],
                "product": entry.product.pk,
                "line": entry.line.pk,
                "accessory": entry.accessory.pk,
                "article_number": entry.accessory.article_number,
                "name": entry.accessory.name,
                "quantity": entry.quantity,
                "planned": entry.planned,
                "is_required": entry.is_required,
                "note": entry.relation.note,
                "free": entry.free if sees_availability else None,
            }
        )
    replacements = [
        {
            "relation": entry.relation.pk,
            "product": entry.relation.product_id,
            "line": entry.line.pk,
            "line_title": entry.line.title,
            "reason": entry.reason,
            "missing": entry.missing,
            "replacement": entry.replacement.pk,
            "article_number": entry.replacement.article_number,
            "name": entry.replacement.name,
            "quantity": entry.quantity,
            "free": entry.free,
            "covers": entry.covers,
            "note": entry.relation.note,
        }
        for entry in found.replacements
    ]
    return {
        "accessories": accessories,
        "replacements": replacements,
        "dismissed": [row.pk for row in found.dismissed],
    }


def _relation(product_pk: Any, relation_pk: Any) -> ProductRelation:
    return get_object_or_404(
        ProductRelation.objects.select_related("product", "related_product", "related_product__unit"),
        pk=relation_pk,
        product_id=product_pk,
    )


class ProductRelationsView(ModuleAPIView):
    """``/products/{id}/relations``: the accessories and replacements of a product (PRD-023, VFG-015)."""

    module = Module.PRODUCTS

    @extend_schema(responses={200: inline_serializer("ProductRelations", {"product": serializers.IntegerField()})})
    def get(self, request: Request, pk: int) -> Response:
        """List the accessories and replacements of the product."""
        return Response(relations_document(get_object_or_404(Product, pk=pk)))

    @extend_schema(
        request=inline_serializer(
            "ProductRelationAdd",
            {
                "related_product": serializers.IntegerField(),
                "kind": serializers.ChoiceField(choices=RelationKind.values),
                "quantity_per_piece": serializers.DecimalField(max_digits=7, decimal_places=2, required=False),
                "note": serializers.CharField(required=False),
                "is_required": serializers.BooleanField(required=False),
                "both_ways": serializers.BooleanField(required=False),
            },
        ),
        responses={201: inline_serializer("ProductRelationAdded", {"product": serializers.IntegerField()})},
    )
    def post(self, request: Request, pk: int) -> Response:
        """Name an accessory or replacement at the end of the list."""
        product = get_object_or_404(Product, pk=pk)
        body = body_of(request)
        # (hostile input; R4-2c) A product that is no whole number is a 400, never a 500.
        related_pk = int_or_400(body.get("related_product"), "related_product", default=0)
        related = Product.objects.filter(pk=related_pk, is_active=True).first()
        if related is None:
            raise ValidationError({"related_product": _("Choose a product from the list.")})
        try:
            suggestions.add_relation(
                product,
                related,
                str(body.get("kind") or ""),
                note=str_or_400(body.get("note"), "note"),
                is_required=bool(body.get("is_required")),
                quantity_per_piece=body.get("quantity_per_piece") or 1,
                both_ways=bool(body.get("both_ways")),
            )
        except ArithmeticError as error:  # an unreadable number
            raise ValidationError({"quantity_per_piece": _("Enter a number.")}) from error
        return Response(relations_document(product), status=status.HTTP_201_CREATED)


class ProductRelationView(ModuleAPIView):
    """``/products/{id}/relations/{relation}``: change one accessory or replacement."""

    module = Module.PRODUCTS

    @extend_schema(
        request=inline_serializer(
            "ProductRelationChange",
            {
                "quantity_per_piece": serializers.DecimalField(max_digits=7, decimal_places=2, required=False),
                "note": serializers.CharField(required=False),
                "is_required": serializers.BooleanField(required=False),
            },
        ),
        responses={200: inline_serializer("ProductRelationChanged", {"product": serializers.IntegerField()})},
    )
    def patch(self, request: Request, pk: int, relation_pk: int) -> Response:
        """Change the note, the flag or the number of pieces per piece."""
        relation = _relation(pk, relation_pk)
        body = body_of(request)
        changes = {name: body[name] for name in ("note", "is_required", "quantity_per_piece") if name in body}
        if "note" in changes:  # (hostile input; R4-2d) a note that is no text is a 400, never a 500
            changes["note"] = str_or_400(changes["note"], "note")
        try:
            suggestions.update_relation(relation, **changes)
        except ArithmeticError as error:
            raise ValidationError({"quantity_per_piece": _("Enter a number.")}) from error
        return Response(relations_document(relation.product))


class ProductRelationMoveView(ModuleAPIView):
    """``/products/{id}/relations/{relation}/move``: one place up or down in its list."""

    module = Module.PRODUCTS

    @extend_schema(
        request=inline_serializer(
            "ProductRelationMove", {"direction": serializers.ChoiceField(choices=["up", "down"])}
        ),
        responses={200: inline_serializer("ProductRelationMoved", {"product": serializers.IntegerField()})},
    )
    def post(self, request: Request, pk: int, relation_pk: int) -> Response:
        """Move the entry."""
        relation = _relation(pk, relation_pk)
        direction = str(body_of(request).get("direction") or "")
        if direction not in ("up", "down"):
            raise ValidationError({"direction": _("Unknown direction.")})
        suggestions.move_relation(relation, direction)
        return Response(relations_document(relation.product))


class ProductRelationRemoveView(ModuleAPIView):
    """``/products/{id}/relations/{relation}/remove``: remove an accessory or replacement."""

    module = Module.PRODUCTS

    @extend_schema(
        request=None,
        responses={200: inline_serializer("ProductRelationRemoved", {"product": serializers.IntegerField()})},
    )
    def post(self, request: Request, pk: int, relation_pk: int) -> Response:
        """Remove the entry; it is no longer suggested."""
        relation = _relation(pk, relation_pk)
        product = relation.product
        suggestions.delete_relation(relation)
        return Response(relations_document(product))


class ProjectSuggestionsView(ModuleAPIView):
    """``/projects/{id}/suggestions``: what the planning of a project suggests (PRD-023, VFG-015)."""

    module = Module.PROJECTS

    @extend_schema(responses={200: inline_serializer("ProjectSuggestions", {"accessories": serializers.ListField()})})
    def get(self, request: Request, project_pk: int) -> Response:
        """Accessories not planned yet and replacements for short lines (the latter with the right to see availability)."""
        project = project_for(request, project_pk, ProjectAccess.READ)
        found = suggestions.suggestions_for_project(
            project, rights=self.rights, include_dismissed=request.query_params.get("dismissed") == "1"
        )
        return Response(suggestions_document(found, sees_availability=self.rights.has(SpecialRight.AVAILABILITY)))


class ProjectSuggestionAddView(ModuleAPIView):
    """``/projects/{id}/suggestions/{relation}/add``: take a suggestion into the planning."""

    module = Module.PROJECTS

    @extend_schema(
        request=inline_serializer(
            "ProjectSuggestionAdd",
            {"line": serializers.IntegerField(required=False), "quantity": serializers.IntegerField(required=False)},
        ),
        responses={201: inline_serializer("ProjectSuggestionAdded", {"line": serializers.IntegerField()})},
    )
    def post(self, request: Request, project_pk: int, relation_pk: int) -> Response:
        """Add the accessory or replacement as a new line (in the group of the line it belongs to)."""
        project = project_for(request, project_pk, ProjectAccess.EDIT)
        body = body_of(request)
        try:
            quantity = None if body.get("quantity") in (None, "") else int(body["quantity"])
            line_id = None if body.get("line") in (None, "") else int(body["line"])
        except (TypeError, ValueError) as error:
            raise ValidationError(_("Enter whole numbers.")) from error
        result = suggestions.accept(project, relation_pk, rights=self.rights, line_id=line_id, quantity=quantity)
        sees = self.rights.has(SpecialRight.AVAILABILITY)
        return Response(
            {
                "line": result.line.pk,
                "title": result.line.title,
                "quantity": result.line.quantity,
                "availability": result.availability.status if sees else None,
                "missing": result.availability.shortage_total if sees else None,
            },
            status=status.HTTP_201_CREATED,
        )


class ProjectSuggestionDismissView(ModuleAPIView):
    """``/projects/{id}/suggestions/dismiss``: do not make these suggestions again in this project."""

    module = Module.PROJECTS

    @extend_schema(
        request=inline_serializer(
            "ProjectSuggestionDismiss", {"relations": serializers.ListField(child=serializers.IntegerField())}
        ),
        responses={200: inline_serializer("ProjectSuggestionDismissed", {"dismissed": serializers.IntegerField()})},
    )
    def post(self, request: Request, project_pk: int) -> Response:
        """Dismiss the named accessories and replacements here."""
        project = project_for(request, project_pk, ProjectAccess.EDIT)
        raw = body_of(request).get("relations")
        if not isinstance(raw, list) or not all(isinstance(value, int) for value in raw):
            raise ValidationError({"relations": _("Send a list of IDs.")})
        return Response({"dismissed": suggestions.dismiss(project, raw, user=request.user)})


class ProjectSuggestionRestoreView(ModuleAPIView):
    """``/projects/{id}/suggestions/restore``: bring dismissed suggestions back."""

    module = Module.PROJECTS

    @extend_schema(
        request=None,
        responses={200: inline_serializer("ProjectSuggestionRestored", {"restored": serializers.IntegerField()})},
    )
    def post(self, request: Request, project_pk: int) -> Response:
        """Bring back all suggestions dismissed in this project."""
        project = project_for(request, project_pk, ProjectAccess.EDIT)
        return Response({"restored": suggestions.restore(project)})
