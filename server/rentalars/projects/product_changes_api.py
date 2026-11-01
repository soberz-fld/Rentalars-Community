# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the changes of products in projects that are not fully confirmed yet (PRJ-072).

Not fully confirmed: inquiry, option, and "confirmed – details open".

* ``/projects/{id}/product-changes`` - the lines of a project whose products changed since they were planned, and
  taking the changes over or keeping the own values. Succeeds the prices-only ``/projects/{id}/old-prices``, which
  stays as it is.
* ``/products/{id}/unconfirmed-projects`` - the same seen from the product: the projects not confirmed yet in which
  it is planned with old values, and taking the changes over in several of them at once.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Module
from rentalars.api.views import ModuleAPIView
from rentalars.products.models import Product
from rentalars.projects.access import ProjectAccess, access_level, project_for, readable_projects
from rentalars.projects.price_updates import shows_price_hint
from rentalars.projects.product_changes import (
    LineChange,
    changes_of_product,
    product_changes,
    take_over_changes,
)


class FieldChangeSerializer(serializers.Serializer):
    """One part of a line (not the price) whose product has another value now."""

    field = serializers.ChoiceField(choices=["name", "unit", "tax_rate", "billing_mode"])
    old = serializers.CharField(help_text="What the line has.")
    new = serializers.CharField(help_text="What the product has today.")
    by_hand = serializers.BooleanField(
        help_text="The line differs from what it took over (or it is not known what it took over)."
    )


class PriceChangeSerializer(serializers.Serializer):
    """The price of the product changed (only with the price right)."""

    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="The price the line charges.")
    list_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        allow_null=True,
        help_text="The price of the product when the line took it over; null if not known.",
    )
    new_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    set_by_hand = serializers.BooleanField()


class LineChangeSerializer(serializers.Serializer):
    """A line whose product changed since the line took it over."""

    key = serializers.CharField(help_text="Names the line: m<id> for a material line, c<id> for a crew line.")
    kind = serializers.CharField(help_text="material or crew.")
    line = serializers.IntegerField()
    article_number = serializers.CharField()
    title = serializers.CharField()
    set_by_hand = serializers.BooleanField(help_text='True: "take over all" leaves the line alone.')
    changes = FieldChangeSerializer(many=True, help_text="The parts besides the price that changed.")
    price = PriceChangeSerializer(allow_null=True)


class ProjectChangesSerializer(serializers.Serializer):
    """The changes of products in a project, and whether its pages point them out."""

    shows_hint = serializers.BooleanField(
        help_text="True while the project is not fully confirmed (inquiry, option, confirmed with details open): its pages point the changes out."
    )
    lines = LineChangeSerializer(many=True)


class TakeOverRequestSerializer(serializers.Serializer):
    """Which lines take over the values of their products, and which keep their own."""

    take_over = serializers.ListField(
        child=serializers.CharField(), required=False, help_text="Keys of the lines that take over the new values."
    )
    take_over_all = serializers.ChoiceField(
        choices=["automatic", "all"],
        required=False,
        help_text="automatic: every line without a value set by hand; all: every changed line.",
    )
    keep = serializers.ListField(
        child=serializers.CharField(), required=False, help_text="Keys of the lines that keep their own values."
    )


class TakeOverResultSerializer(ProjectChangesSerializer):
    """What was done, and what is still outdated."""

    taken_over = serializers.IntegerField()
    kept = serializers.IntegerField()


class ProductProjectSerializer(serializers.Serializer):
    """A project not fully confirmed yet whose lines have not taken over the changes of a product."""

    project = serializers.IntegerField()
    number = serializers.CharField()
    name = serializers.CharField()
    status = serializers.CharField()
    can_edit = serializers.BooleanField(help_text="The caller may take the changes over in this project.")
    lines = LineChangeSerializer(many=True)


class ProductChangesSerializer(serializers.Serializer):
    """The projects behind a product."""

    projects = ProductProjectSerializer(many=True)


class ProductTakeOverRequestSerializer(serializers.Serializer):
    """The projects to take the changes over in."""

    projects = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text="IDs of the projects; without it every project the caller may edit.",
    )


class ProductTakeOverResultSerializer(serializers.Serializer):
    """How many lines in how many projects took the changes over."""

    lines = serializers.IntegerField()
    projects = serializers.IntegerField()


def change_document(change: LineChange) -> dict[str, Any]:
    """A changed line as the API shows it."""
    price = change.price
    return {
        "key": change.key,
        "kind": "crew" if change.is_crew else "material",
        "line": change.line.pk,
        "article_number": change.article_number,
        "title": change.title,
        "set_by_hand": change.set_by_hand,
        "changes": [
            {"field": part.field, "old": part.old, "new": part.new, "by_hand": part.by_hand} for part in change.fields
        ],
        "price": None
        if price is None
        else {
            "unit_price": price.unit_price,
            "list_price": price.list_price,
            "new_price": price.new_price,
            "set_by_hand": price.set_by_hand,
        },
    }


class ProjectProductChangesView(ModuleAPIView):
    """``/projects/{id}/product-changes`` - what the products of the lines changed since they were planned (PRJ-072).

    The list is delivered for every project, confirmed or not; ``shows_hint`` tells whether its pages point the
    changes out (only before the project is confirmed). Prices are part of it only for who has the price right
    (AUT-019); taking over leaves prices out without that right.
    """

    module = Module.PROJECTS

    def _document(self, project: Any) -> dict[str, Any]:
        return {
            "shows_hint": shows_price_hint(project),
            "lines": [change_document(change) for change in product_changes(project, self.rights)],
        }

    @extend_schema(responses=ProjectChangesSerializer)
    def get(self, request: Request, project_pk: int) -> Response:
        """The lines whose product changed since they took it over, with old and new values."""
        project = project_for(request, project_pk, ProjectAccess.READ)
        return Response(self._document(project))

    @extend_schema(request=TakeOverRequestSerializer, responses=TakeOverResultSerializer)
    def post(self, request: Request, project_pk: int) -> Response:
        """Take over the changes - of named lines, of all without a value set by hand, or of all - or keep the own values."""
        project = project_for(request, project_pk, ProjectAccess.EDIT)
        serializer = TakeOverRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        scope = data.get("take_over_all")
        result = take_over_changes(
            project,
            rights=self.rights,
            keys=data.get("take_over", []),
            automatic=scope == "automatic",
            everything=scope == "all",
            keep=data.get("keep", []),
        )
        return Response({"taken_over": result.taken_over, "kept": result.kept, **self._document(project)})


class ProductUnconfirmedProjectsView(ModuleAPIView):
    """``/products/{id}/unconfirmed-projects`` - the projects not fully confirmed yet that are behind this product (PRJ-072).

    Only projects the caller may read are named (AUT-016). Taking over leaves lines with a value set by hand alone.
    """

    module = Module.PRODUCTS

    def _entries(self, request: Request, product: Product) -> list[dict[str, Any]]:
        found = changes_of_product(product, self.rights)
        if not found:
            return []
        visible = set(
            readable_projects(self.rights, request.user)
            .filter(pk__in=[project.pk for project in found])
            .values_list("pk", flat=True)
        )
        return [
            {
                "project": project.pk,
                "number": project.number,
                "name": project.name,
                "status": project.status,
                "can_edit": not project.is_locked
                and access_level(self.rights, request.user, project) >= ProjectAccess.EDIT,
                "lines": [change_document(change) for change in changes],
            }
            for project, changes in found.items()
            if project.pk in visible
        ]

    @extend_schema(responses=ProductChangesSerializer)
    def get(self, request: Request, pk: int) -> Response:
        """The projects in which the product is planned with old values, with the lines concerned."""
        product = get_object_or_404(Product, pk=pk)
        return Response({"projects": self._entries(request, product)})

    @extend_schema(request=ProductTakeOverRequestSerializer, responses=ProductTakeOverResultSerializer)
    def post(self, request: Request, pk: int) -> Response:
        """Take the changes of the product over in the named projects, or in all the caller may edit."""
        product = get_object_or_404(Product, pk=pk)
        serializer = ProductTakeOverRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        wanted = set(serializer.validated_data.get("projects", []))
        lines = projects = 0
        for entry in self._entries(request, product):
            if not entry["can_edit"] or (wanted and entry["project"] not in wanted):
                continue
            project = project_for(request, entry["project"], ProjectAccess.EDIT)
            try:
                result = take_over_changes(project, rights=self.rights, automatic=True, only_product=product)
            except ValidationError:
                continue
            if result.taken_over:
                projects += 1
                lines += result.taken_over
        return Response({"lines": lines, "projects": projects})
