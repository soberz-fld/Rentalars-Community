# SPDX-License-Identifier: GPL-3.0-or-later
"""API for lines of the planning (PRJ-072, PRJ-075, PRJ-082, PRJ-083).

``POST /projects/{id}/material-lines/{line}/duplicate``
    A copy of the line directly below it (PRJ-075).

``GET /projects/{id}/old-prices``, ``POST /projects/{id}/old-prices``
    The lines whose product asks a different price than when they took it
    over, and taking over the new prices or keeping the own ones (PRJ-072).

``POST /projects/{id}/material-lines/bulk``
    One thing done with several lines at once, as on the planning page
    (PRJ-082): optional, normal again, alternative to a line, into a group,
    a discount, or delete. Lines the action cannot be done with are left as
    they are and named with the reason.

Optional and alternative lines (PRJ-075) need no endpoint of their own: the
fields ``variant`` and ``alternative_to`` of a material line
say it (PRJ-083).
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Module, SpecialRight
from rentalars.api.views import ModuleAPIView
from rentalars.projects.access import ProjectAccess, project_for
from rentalars.projects.api import MaterialLineSerializer
from rentalars.projects.lines import BulkAction, change_lines, duplicate_line
from rentalars.projects.price_updates import OldPrice, old_prices, shows_price_hint, take_over_new_prices
from rentalars.projects.pricing import compute_project_prices


class DuplicateLineView(ModuleAPIView):
    """``POST /projects/{id}/material-lines/{line}/duplicate`` – a copy right below the line (PRJ-075)."""

    module = Module.PROJECTS

    @extend_schema(request=None, responses={201: MaterialLineSerializer})
    def post(self, request: Request, project_pk: int, pk: int) -> Response:
        """Duplicate the line: same product, quantity, period, prices and note, in the same group."""
        project = project_for(request, project_pk, ProjectAccess.EDIT)
        line = get_object_or_404(project.material_lines.select_related("product"), pk=pk)
        result = duplicate_line(line, rights=self.rights)
        context: dict[str, Any] = {
            "request": request,
            "project": project,
            "availability": {result.line.pk: result.availability},
        }
        if self.rights.has(SpecialRight.PRICES):
            context["prices"] = compute_project_prices(project)
        return Response(MaterialLineSerializer(result.line, context=context).data, status=status.HTTP_201_CREATED)


class OldPriceSerializer(serializers.Serializer):
    """A line whose product asks a different price now (PRJ-072)."""

    key = serializers.CharField(help_text="Names the line: m<id> for a material line, c<id> for a crew line.")
    kind = serializers.ChoiceField(choices=["material", "crew"])
    line = serializers.IntegerField()
    article_number = serializers.CharField()
    title = serializers.CharField()
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    list_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        allow_null=True,
        help_text="The price of the product when the line took it over; null if not known.",
    )
    new_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    set_by_hand = serializers.BooleanField()


class OldPricesSerializer(serializers.Serializer):
    """The old prices of a project, and whether its planning points them out."""

    shows_hint = serializers.BooleanField(
        help_text="True while the project is not fully confirmed (inquiry, option, confirmed with details open): the planning points out old prices."
    )
    lines = OldPriceSerializer(many=True)


class PriceUpdateRequestSerializer(serializers.Serializer):
    """Which lines take over the new price of their product, and which keep their own (PRJ-072)."""

    take_over = serializers.ListField(
        child=serializers.CharField(), required=False, help_text="Keys of the lines that take over the new price."
    )
    take_over_all = serializers.ChoiceField(
        choices=["automatic", "all"],
        required=False,
        help_text="automatic: every line whose price was not set by hand; all: every outdated line.",
    )
    keep = serializers.ListField(
        child=serializers.CharField(), required=False, help_text="Keys of the lines that keep their own price."
    )


class PriceUpdateResultSerializer(serializers.Serializer):
    """What was done, and what is still outdated."""

    taken_over = serializers.IntegerField()
    kept = serializers.IntegerField()
    shows_hint = serializers.BooleanField()
    lines = OldPriceSerializer(many=True)


def _old_price_document(old: OldPrice) -> dict[str, Any]:
    return {
        "key": old.key,
        "kind": "crew" if old.is_crew else "material",
        "line": old.line.pk,
        "article_number": old.article_number,
        "title": old.title,
        "unit_price": old.unit_price,
        "list_price": old.list_price,
        "new_price": old.new_price,
        "set_by_hand": old.set_by_hand,
    }


class OldPricesView(ModuleAPIView):
    """``/projects/{id}/old-prices`` – prices of products that changed since the lines took them over (PRJ-072).

    The list is delivered for every project, confirmed or not; ``shows_hint``
    tells whether the planning points the old prices out (only before the
    project is confirmed). Both directions need the price right (AUT-019).
    """

    module = Module.PROJECTS

    def _require_prices(self) -> None:
        if not self.rights.has(SpecialRight.PRICES):
            raise PermissionDenied

    @extend_schema(responses=OldPricesSerializer)
    def get(self, request: Request, project_pk: int) -> Response:
        """The lines whose product asks a different price now, with old and new price."""
        self._require_prices()
        project = project_for(request, project_pk, ProjectAccess.READ)
        return Response(
            {
                "shows_hint": shows_price_hint(project),
                "lines": [_old_price_document(old) for old in old_prices(project)],
            }
        )

    @extend_schema(request=PriceUpdateRequestSerializer, responses=PriceUpdateResultSerializer)
    def post(self, request: Request, project_pk: int) -> Response:
        """Take over the new prices – of named lines, of all not set by hand, or of all – or keep the own ones."""
        self._require_prices()
        project = project_for(request, project_pk, ProjectAccess.EDIT)
        serializer = PriceUpdateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        scope = data.get("take_over_all")
        result = take_over_new_prices(
            project,
            rights=self.rights,
            keys=data.get("take_over", []),
            automatic=scope == "automatic",
            everything=scope == "all",
            keep=data.get("keep", []),
        )
        return Response(
            {
                "taken_over": result.taken_over,
                "kept": result.kept,
                "shows_hint": shows_price_hint(project),
                "lines": [_old_price_document(old) for old in old_prices(project)],
            }
        )


class BulkRequestSerializer(serializers.Serializer):
    """One thing to do with several lines of the planning (PRJ-082)."""

    lines = serializers.ListField(child=serializers.IntegerField(), allow_empty=False, help_text="IDs of the lines.")
    action = serializers.ChoiceField(
        choices=list(BulkAction.ALL),
        help_text=(
            "optional; normal (no longer optional or an alternative); alternative (needs alternative_to); "
            "move (into group, null: without group); discount (needs discount_percent and the price right); delete."
        ),
    )
    alternative_to = serializers.IntegerField(
        required=False, allow_null=True, help_text="For alternative: the line the others could replace (PRJ-083)."
    )
    group = serializers.IntegerField(
        required=False, allow_null=True, help_text="For move: the group the lines go to; null: without group."
    )
    discount_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, allow_null=True, help_text="For discount: 0 to 100."
    )


class SkippedLineSerializer(serializers.Serializer):
    """A line the action was not done with."""

    line = serializers.IntegerField()
    title = serializers.CharField(help_text="Quantity and title, e.g. “8 × LED-Scheinwerfer”.")
    reason = serializers.CharField()


class BulkResultSerializer(serializers.Serializer):
    """What was done with the lines."""

    action = serializers.CharField()
    changed = serializers.ListField(child=serializers.IntegerField(), help_text="IDs of the lines changed or deleted.")
    unchanged = serializers.ListField(child=serializers.IntegerField(), help_text="Lines that were like that already.")
    skipped = SkippedLineSerializer(many=True)
    warnings = serializers.ListField(
        child=serializers.CharField(),
        help_text="E.g. that the discount is above the maximum of some lines; the maximum is applied there.",
    )


class BulkLinesView(ModuleAPIView):
    """``POST /projects/{id}/material-lines/bulk`` – one thing done with several lines at once (PRJ-082).

    The same as choosing lines on the planning page: each line goes through
    the service for a single line, with its rules and its entry in the
    history; lines the action cannot be done with – material already issued,
    pieces taken over by another subproject, a subrental that covers a
    shortage – are left as they are and named in ``skipped``. Needs the right
    to edit the project; a discount also the price right.
    """

    module = Module.PROJECTS

    @extend_schema(request=BulkRequestSerializer, responses=BulkResultSerializer)
    def post(self, request: Request, project_pk: int) -> Response:
        """Do the action with every line named; answer which lines changed and which were skipped, and why."""
        project = project_for(request, project_pk, ProjectAccess.EDIT)
        serializer = BulkRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        values: dict[str, Any] = {}
        if data.get("alternative_to") is not None:
            values["alternative_to"] = get_object_or_404(project.material_lines, pk=data["alternative_to"])
        if data.get("group") is not None:
            values["group"] = get_object_or_404(project.groups, pk=data["group"])
        if data.get("discount_percent") is not None:
            values["discount_percent"] = data["discount_percent"]
        result = change_lines(project, data["lines"], data["action"], rights=self.rights, **values)
        return Response(
            {
                "action": result.action,
                "changed": result.changed_ids,
                "unchanged": [line.pk for line in result.unchanged],
                "skipped": [
                    {"line": skipped.line.pk, "title": skipped.label, "reason": skipped.reason}
                    for skipped in result.skipped
                ],
                "warnings": result.warnings,
            }
        )
