# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the packing module: packlist, ticking, issue, return (chapter 8)."""

from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field, inline_serializer
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Level, Module, request_rights
from rentalars.api.errors import error_response
from rentalars.api.permissions import level_for_method
from rentalars.api.views import ModuleAPIView, body_of
from rentalars.packing import offline, services, subprojects
from rentalars.packing.models import Extraction, Handover, Packlist
from rentalars.packing.pdf import packing_list_name, render_family_pdf, render_packlist_pdf
from rentalars.projects.access import packlist_project_for
from rentalars.projects.models import Project, VehicleLine


def packlist_summary(packlist: Packlist, *, is_main: bool | None = None) -> dict[str, Any]:
    """Title, loading time and state of a packlist (PCK-008, PCK-014); ``is_main`` if known already."""
    return {
        "id": packlist.pk,
        "project": packlist.project_id,
        "title": packlist.title,
        "is_main": services.is_main(packlist) if is_main is None else is_main,
        "loading_at": packlist.loading_at,
        "note": packlist.note,
        # LOG-001: the vehicle booking of the project's logistics it is loaded into, or null.
        "vehicle_line": packlist.vehicle_line_id,
        "status": packlist.status,
        "packing_started_at": packlist.packing_started_at,
        "issued_at": packlist.issued_at,
        "returned_at": packlist.returned_at,
    }


TWO_PLACES = Decimal("0.01")


def _quantity(value: Decimal) -> Decimal:
    """A quantity with two decimals, as stored (NFA-003)."""
    return Decimal(value).quantize(TWO_PLACES)


def _project_ref(project: Project) -> dict[str, Any]:
    """ID, number and name of a project."""
    return {"id": project.pk, "number": project.number, "name": project.name}


def handover_document(handover: Handover) -> dict[str, Any]:
    """One booked handover between two subprojects (PRJ-060)."""
    source, target = handover.source, handover.target
    return {
        "id": handover.pk,
        "quantity": _quantity(handover.quantity),
        "handed_over_at": handover.handed_over_at,
        "handed_over_by": str(handover.handed_over_by) if handover.handed_over_by_id else None,
        "line": target.line_id,
        "product": target.product_id,
        "from_project": _project_ref(source.packlist.project),
        "from_packlist": source.packlist_id,
        "from_line": source.line_id,
    }


def _takeover_fields(row: services.PackRow) -> dict[str, Any]:
    """PRJ-060: where the pieces of a row come from, and where they go on to."""
    source = row.takeover_from
    return {
        "taken_over_from": (
            {"line": source.pk, "project": _project_ref(source.project)} if source is not None else None
        ),
        "awaiting_handover": _quantity(row.awaiting_handover),
        "handovers": [
            {
                "id": booking.handover_id,
                "quantity": _quantity(booking.quantity),
                "handed_over_at": booking.at,
                "from_project": _project_ref(booking.from_project),
            }
            for booking in row.handovers
        ],
        "handed_over": _quantity(row.handed_over),
        "passes_on": [
            {
                "line": passing.line.pk,
                "project": _project_ref(passing.project),
                "planned": _quantity(passing.planned),
                "handed_over": _quantity(passing.handed),
            }
            for passing in row.passes_on
        ],
    }


def _optional_quantity(value: Decimal | None) -> Decimal | None:
    """A quantity with two decimals, or ``None``."""
    return None if value is None else _quantity(value)


def overview_document(overview: services.PackOverview) -> dict[str, Any]:
    """A packlist with its rows and progress as JSON (PCK-002, PCK-014). No prices (PCK-007).

    Every quantity is text with two decimals (NFA-003). Each row says when its
    packed and its returned quantity last changed (PCK-027), so that the app
    can tell which of its changes are later; the ETag changes with them.
    """
    packlist = overview.packlist
    bar = overview.bar
    return {
        **packlist_summary(packlist),
        "order": overview.order,
        "progress_percent": overview.progress_percent,
        "return_percent": overview.return_percent,
        # PCK-025: what "issue" books (ticked, not issued yet), and what is still in the warehouse.
        "ready_to_issue": _quantity(overview.ready_total),
        "not_issued": _quantity(overview.not_issued_total),
        "weight_kg": overview.weight_kg,
        "volume_litres": overview.volume_litres,
        "rows_without_weight": overview.rows_without_weight,
        "has_changes": overview.has_changes,
        # PRJ-060: pieces from other subprojects, not from the warehouse; pieces gone on to other subprojects.
        "takeover_total": _quantity(overview.takeover_total),
        "awaiting_handover_total": _quantity(overview.awaiting_handover_total),
        "handed_over_total": _quantity(overview.handed_over_total),
        # PCK-028: what "take-back" books (ticked as back, not booked yet), what is booked back, what is out.
        "ready_to_take_back": _quantity(overview.ready_back_total),
        "taken_back": _quantity(overview.taken_back_total),
        "still_out": _quantity(overview.still_out_total),
        # PCK-029: the pieces in the five states of the bar on the packlist page.
        "bar": {name: _quantity(getattr(bar, name)) for name in services.ProgressBar.NAMES},
        "removed_rows": [
            {
                "title": removed.title,
                "article_number": removed.article_number,
                "was_required": _optional_quantity(removed.was_required),
            }
            for removed in overview.removed
        ],
        "extracted": overview.extracted,
        "sections": [
            {
                "group": section.group.pk if section.group else None,
                "name": section.title or (section.group.name if section.group else None),
                "rows": [
                    {
                        "line": row.line.pk,
                        "product": row.product.pk,
                        "article_number": row.product.article_number,
                        "title": row.title,
                        "kit": row.kit_title or None,
                        "required": _quantity(row.required),
                        "unit": row.product.unit.abbreviation,
                        "note": row.line.note,
                        "wish": row.wish or None,
                        "preferred_item": row.line.preferred_item_id if not row.kit_title else None,
                        # Piece share: every wished item – each covers one piece of the line.
                        "preferred_items": [wished.item_id for wished in row.wished],
                        "preferred_model": row.line.preferred_model_id if not row.kit_title else None,
                        "packed": _quantity(row.packed),
                        "issued": _quantity(row.issued),
                        # PCK-028: ticked as back; "taken_back" is what is booked back into the warehouse.
                        "returned": _quantity(row.returned),
                        "taken_back": _quantity(row.taken_back),
                        "ready_to_issue": _quantity(row.ready_to_issue),
                        "ready_to_take_back": _quantity(row.ready_to_take_back),
                        "still_out": _quantity(row.still_out),
                        # PCK-027: when the two ticked quantities last changed, on whatever way.
                        "packed_changed_at": row.packed_changed_at,
                        "returned_changed_at": row.returned_changed_at,
                        # PCK-027: counts their changes; the sync takes it as "base_version".
                        "version": row.version,
                        "missing": _quantity(row.missing),
                        "return_state": row.return_state,
                        "missing_resolved": row.missing_resolved,
                        "missing_note": row.missing_note,
                        "is_subrental": row.is_subrental,
                        "supplier": row.line.supplier.name if row.is_subrental and row.line.supplier else None,
                        "is_sale": row.is_sale,
                        "is_bulk": row.is_bulk,
                        # Products of several pieces: "required" counts products; each is this many items.
                        "pieces_per_unit": row.pieces_per_unit,
                        "pieces_required": row.pieces_required,
                        "pieces_chosen": row.pieces_chosen,
                        "units_chosen": row.units_chosen,
                        "allocated_items": row.allocated_ids,
                        "chosen_items": [
                            {
                                "allocation": chosen.allocation_id,
                                "item": chosen.item_id,
                                "display_id": chosen.display_id,
                                "issued": chosen.is_issued,
                                "returned": chosen.is_returned,
                                "inspection_overdue": chosen.inspection_overdue,
                                "spot": chosen.spot or None,
                            }
                            for chosen in row.chosen
                        ],
                        "change": row.change or None,
                        "was_required": _optional_quantity(row.was_required),
                        "is_addendum": row.line.is_addendum,
                        "hints": row.hints,
                        "location": row.location or None,
                        "weight_kg": row.weight_kg,
                        "volume_litres": row.volume_litres,
                        "contents": [
                            {
                                "depth": content.depth,
                                "display_id": content.display_id,
                                "name": content.name,
                                "state": content.state,
                            }
                            for content in row.contents
                        ],
                        **_takeover_fields(row),
                    }
                    for row in section.rows
                ],
            }
            for section in overview.sections
        ],
    }


def _flag(value: Any, *, default: bool) -> bool:
    """A yes/no value from a JSON or form body; ``default`` if it is missing."""
    if value is None or value == "":
        return default
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def _decimal(value: Any, name: str) -> Decimal:
    """Read a quantity from the request body."""
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValidationError({name: _("Enter a number.")}) from error


class PacklistView(ModuleAPIView):
    """Base for all packlist endpoints: finds the project and its packlist."""

    module = Module.PACKING

    @property
    def action_levels(self) -> dict[Any, int]:
        """``DELETE`` here is a step of packing – a further packing list, a handover, an extraction.

        As in the browser it needs write on packing, not the level "delete"
        that ``DELETE`` asks of other modules: crew packs (accounts/0007), and
        none of these steps has a financial effect.
        """
        request = getattr(self, "request", None)
        return {None: Level.WRITE} if request is not None and request.method == "DELETE" else {}

    def get_packlist(self, project_pk: int, packlist_pk: int | None = None) -> Packlist:
        """Return the packlist from the address; the project's single one if no ID is given.

        The caller must see the project (the deployment view is enough,
        AUT-025) and have the needed level of "packing" *in this project*:
        read to look, write to tick, issue and return (AUT-016).
        """
        needed = level_for_method(self.request.method or "GET")
        project = packlist_project_for(
            self.request,
            project_pk,
            min(needed, Level.WRITE),
            queryset=Project.objects.select_related("customer", "manager"),
        )
        packlist = (
            services.get_packlist(project)
            if packlist_pk is None
            else get_object_or_404(Packlist, pk=packlist_pk, project=project)
        )
        # PRJ-122: the printed packlist names the customer in every role.
        packlist.shows_customer = project.shows_customer
        return packlist

    def overview(self, packlist: Packlist) -> services.PackOverview:
        """The rows in the order asked for with ``?order=`` and ``?contents=1`` (PCK-004, MAT-037)."""
        order = self.request.query_params.get("order", services.ORDER_GROUPS)
        contents = self.request.query_params.get("contents") in {"1", "true"}
        return services.build_overview(packlist, order=order, with_contents=contents)


_OVERVIEW_PARAMETERS = [
    OpenApiParameter("order", str, enum=list(services.ORDERS), description="Order of the rows (PCK-004)."),
    OpenApiParameter("contents", bool, description="List what is inside allocated containers (MAT-037)."),
]


class PacklistFieldsSerializer(serializers.Serializer):
    """Title, loading time and note of a packlist (PCK-008)."""

    title = serializers.CharField(max_length=120)
    loading_at = serializers.DateTimeField(required=False, allow_null=True)
    note = serializers.CharField(max_length=250, required=False, allow_blank=True)
    # LOG-001: a vehicle booked in the project's logistics, or null.
    vehicle_line = serializers.PrimaryKeyRelatedField(
        queryset=VehicleLine.objects.all(), required=False, allow_null=True
    )


class PacklistListView(PacklistView):
    """``/projects/{id}/packlists`` – the packlists of a project, the main one first (PCK-001, PCK-008)."""

    @extend_schema(
        responses={200: inline_serializer("PacklistSummary", {"status": serializers.CharField()}, many=True)}
    )
    def get(self, request: Request, project_pk: int) -> Response:
        """Return title and state of every packlist of the project."""
        main = self.get_packlist(project_pk)
        return Response([packlist_summary(packlist) for packlist in services.packlists_of(main.project)])

    @extend_schema(
        request=PacklistFieldsSerializer,
        responses={201: inline_serializer("PacklistCreated", {"id": serializers.IntegerField()})},
    )
    def post(self, request: Request, project_pk: int) -> Response:
        """Add a packlist – per truck, trade or loading date; give it lines with ``…/lines``."""
        main = self.get_packlist(project_pk)
        serializer = PacklistFieldsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        created = services.create_packlist(main.project, **serializer.validated_data)
        return Response(packlist_summary(created), status=status.HTTP_201_CREATED)


class PacklistDetailView(PacklistView):
    """``/projects/{id}/packlists/{packlist_id}`` – rows and progress (PCK-002)."""

    @extend_schema(
        parameters=_OVERVIEW_PARAMETERS,
        responses={200: inline_serializer("PacklistDetail", {"status": serializers.CharField()})},
    )
    def get(self, request: Request, project_pk: int, packlist_pk: int) -> Response:
        """Return the packlist with all rows, weight and volume (PCK-006), changes (PCK-015) and hints."""
        return Response(overview_document(self.overview(self.get_packlist(project_pk, packlist_pk))))

    @extend_schema(
        request=PacklistFieldsSerializer,
        responses={200: inline_serializer("PacklistChanged", {"id": serializers.IntegerField()})},
    )
    def patch(self, request: Request, project_pk: int, packlist_pk: int) -> Response:
        """Change title, loading time or note."""
        packlist = self.get_packlist(project_pk, packlist_pk)
        serializer = PacklistFieldsSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return Response(packlist_summary(services.update_packlist(packlist, **serializer.validated_data)))

    @extend_schema(responses={204: None})
    def delete(self, request: Request, project_pk: int, packlist_pk: int) -> Response:
        """Delete a further packlist that was not issued; its lines go back to the main packlist."""
        services.delete_packlist(self.get_packlist(project_pk, packlist_pk))
        return Response(status=status.HTTP_204_NO_CONTENT)


class PacklistLinesView(PacklistView):
    """``POST /projects/{id}/packlists/{packlist_id}/lines`` – put lines on this packlist (PCK-008)."""

    @extend_schema(
        request=inline_serializer("PacklistLines", {"lines": serializers.ListField(child=serializers.IntegerField())}),
        responses={200: inline_serializer("PacklistLinesMoved", {"moved": serializers.IntegerField()})},
    )
    def post(self, request: Request, project_pk: int, packlist_pk: int) -> Response:
        """Move the named material lines here; ticks of moved lines on their old packlist are dropped."""
        packlist = self.get_packlist(project_pk, packlist_pk)
        lines = body_of(request).get("lines")
        if not isinstance(lines, list) or not all(isinstance(line, int) for line in lines):
            raise ValidationError({"lines": _("Expected a list of line IDs.")})
        return Response({"moved": services.assign_lines(packlist, lines, user=request.user)})


class PacklistItemsView(PacklistView):
    """``…/packlists/{packlist_id}/items`` – choose the items of a row beforehand (PCK-022)."""

    @extend_schema(
        parameters=[OpenApiParameter("line", int, required=True), OpenApiParameter("product", int, required=True)],
        responses={200: inline_serializer("ItemChoice", {"id": serializers.IntegerField()}, many=True)},
    )
    def get(self, request: Request, project_pk: int, packlist_pk: int) -> Response:
        """The items one could choose for a row, with notes; ``free`` is false for items with another project."""
        packlist = self.get_packlist(project_pk, packlist_pk)
        try:
            row = services.find_row(
                services.build_overview(packlist),
                int(request.query_params.get("line", "0")),
                int(request.query_params.get("product", "0")),
            )
        except ValueError as error:
            raise ValidationError(_("Name the row by its line and product.")) from error
        chosen = {item.item_id for item in row.chosen}
        return Response(
            [
                {"id": item.pk, "display_id": item.display_id, "note": note, "free": free, "chosen": item.pk in chosen}
                for item, note, free in services.item_choices(packlist, row)
            ]
        )

    @extend_schema(
        request=inline_serializer(
            "ItemChoiceSet",
            {
                "line": serializers.IntegerField(),
                "product": serializers.IntegerField(),
                "items": serializers.ListField(child=serializers.IntegerField()),
            },
        ),
        responses={200: inline_serializer("PacklistAfterChoice", {"status": serializers.CharField()})},
    )
    def put(self, request: Request, project_pk: int, packlist_pk: int) -> Response:
        """Replace the chosen items of a row; warnings name items with an overdue inspection (MAT-032)."""
        packlist = self.get_packlist(project_pk, packlist_pk)
        body = body_of(request)
        try:
            line_id, product_id = int(body.get("line")), int(body.get("product"))
            items = [int(item) for item in body.get("items") or []]
        except (TypeError, ValueError) as error:
            raise ValidationError(_("Name the row by its line and product.")) from error
        warnings = services.choose_items(packlist, line_id, product_id, items, user=request.user)
        packlist.refresh_from_db()
        document = overview_document(services.build_overview(packlist))
        document["warnings"] = warnings
        return Response(document)


class PacklistRowView(PacklistView):
    """``PATCH …/packlists/{id}/rows`` – tick one row as packed or returned (PCK-009, PCK-016).

    Body: ``{"line": 12, "product": 5, "packed": 3}`` or ``{"line": 12,
    "product": 5, "returned": 3}``. Quantities are plain numbers; no item has
    to be chosen (PCK-020). Like ``packed``, ``returned`` is a tick: the action
    ``take-back`` books it (PCK-028). It cannot go below what is taken back.
    """

    @extend_schema(
        request=inline_serializer(
            "PackRowUpdate",
            {
                "line": serializers.IntegerField(),
                "product": serializers.IntegerField(),
                "packed": serializers.DecimalField(10, 2, required=False),
                "returned": serializers.DecimalField(10, 2, required=False),
            },
        ),
        responses={200: inline_serializer("PacklistAfterRow", {"status": serializers.CharField()})},
    )
    def patch(self, request: Request, project_pk: int, packlist_pk: int) -> Response:
        """Store the packed or returned quantity of a row."""
        packlist = self.get_packlist(project_pk, packlist_pk)
        try:
            line_id = int(body_of(request).get("line"))
            product_id = int(body_of(request).get("product"))
        except (TypeError, ValueError) as error:
            raise ValidationError(_("Name the row by its line and product.")) from error
        if "packed" in body_of(request):
            services.set_packed(
                packlist, line_id, product_id, _decimal(body_of(request)["packed"], "packed"), user=request.user
            )
        elif "returned" in body_of(request):
            services.set_returned(
                packlist, line_id, product_id, _decimal(body_of(request)["returned"], "returned"), user=request.user
            )
        else:
            raise ValidationError(_("Send either “packed” or “returned”."))
        packlist.refresh_from_db()
        return Response(overview_document(services.build_overview(packlist)))


class PacklistActionView(PacklistView):
    """``POST …/packlists/{id}/{action}`` – the steps of packing, issue and return.

    ============================  =================================================
    action                        effect
    ============================  =================================================
    ``pack-all``                  tick every row as packed
    ``issue``                     book what is ticked out of the warehouse, with
                                  the ticked quantities (PCK-025);
                                  ``{"only_packed": false}`` issues every row in
                                  full ("issue everything", PCK-014)
    ``undo-issue``                take back an issue booked by mistake
    ``return-all``                tick everything issued as back (PCK-016);
                                  books nothing yet (PCK-028)
    ``take-back``                 book what is ticked as back into the
                                  warehouse, with the ticked quantities
                                  (PCK-028); completes the return once
                                  nothing is out and nothing waits
    ``resolve-missing``           clarify missing parts of a row; body
                                  ``{"line", "product", "note"}`` (PCK-019)
    ``complete-return``           book what is ticked and finish the return;
                                  project becomes "returned" once no packlist
                                  is out any more
    ``acknowledge-changes``       take the changed planning as the packlist's
                                  new state (PCK-015)
    ``add-material``              add material while packing as an addendum;
                                  body ``{"product", "quantity"}`` (PCK-013)
    ``report-defect``             report a defect on return; multipart
                                  ``item``, ``description``, ``photo`` (PCK-017)
    ``scan``                      an item read from its label; body
                                  ``{"code", "mode"}`` with mode ``pack`` (default)
                                  or ``return``. Chooses the item for its row and
                                  counts the row up (PCK-010, PCK-011), or counts it
                                  back (PCK-016). The answer has a ``scan`` part:
                                  ``status``, ``level``, ``message``, ``warnings``,
                                  ``row``, ``done``, ``required``
    ============================  =================================================

    ``issue`` leaves the packlist *partly issued* while something of it is
    not issued yet; it can be packed further and issued again (PCK-018). The
    project becomes "out" only once everything of it is out (PCK-025).

    The return works like the issue (PCK-028): ``returned`` of a
    row is what is ticked as back, ``take-back`` books it. A piece taken back
    is done for the project; what was not issued yet can still be issued.

    ``add-material`` makes a charged line of the project, so it needs,
    besides write on packing, write on the project or packing for all
    projects; else 403 with the code ``needs_project_write`` (crew packs what
    is planned). Every other step needs write on packing only.
    """

    parser_classes: ClassVar[list[Any]] = [JSONParser, MultiPartParser, FormParser]

    @extend_schema(
        operation_id="projects_packlists_action",
        request=inline_serializer(
            "PacklistAction",
            {
                "only_packed": serializers.BooleanField(
                    required=False,
                    default=True,
                    help_text="issue: only what is ticked (default); false issues every row in full (PCK-025).",
                ),
                "line": serializers.IntegerField(required=False),
                "product": serializers.IntegerField(required=False),
                "note": serializers.CharField(required=False),
                "quantity": serializers.DecimalField(10, 2, required=False),
                "item": serializers.IntegerField(required=False),
                "description": serializers.CharField(required=False),
                "photo": serializers.ImageField(required=False),
                "code": serializers.CharField(required=False, help_text="scan: the text of the label's code."),
                "mode": serializers.ChoiceField(choices=["pack", "return"], required=False, help_text="scan."),
            },
        ),
        responses={200: inline_serializer("PacklistAfterAction", {"status": serializers.CharField()})},
    )
    def post(self, request: Request, project_pk: int, packlist_pk: int, action: str) -> Response:
        """Run one packing step and return the packlist afterwards."""
        packlist = self.get_packlist(project_pk, packlist_pk)
        hints: list[str] = []
        scan_answer: dict[str, Any] | None = None
        if action == "pack-all":
            services.pack_all(packlist, user=request.user)
        elif action == "issue":
            only_packed = _flag(body_of(request).get("only_packed"), default=True)  # PCK-025
            hints = services.issue(packlist, user=request.user, only_packed=only_packed)
        elif action == "undo-issue":
            services.undo_issue(packlist)
        elif action == "return-all":
            services.return_all(packlist, user=request.user)
        elif action == "take-back":
            services.take_back(packlist, user=request.user)  # PCK-028
        elif action == "resolve-missing":
            try:
                line_id = int(body_of(request).get("line"))
                product_id = int(body_of(request).get("product"))
            except (TypeError, ValueError) as error:
                raise ValidationError(_("Name the row by its line and product.")) from error
            hint = services.resolve_missing(
                packlist, line_id, product_id, str(body_of(request).get("note", "")), user=request.user
            )
            hints = [hint] if hint else []
        elif action == "complete-return":
            services.complete_return(packlist, user=request.user)
        elif action == "acknowledge-changes":
            services.acknowledge_changes(packlist, user=request.user)
        elif action == "add-material":
            from rentalars.products.models import Product

            if not services.may_add_material(self.rights, request.user, packlist.project):
                # PCK-013: a charged line of the project – not for whoever packs only where assigned.
                return error_response(
                    offline.NEEDS_PROJECT_WRITE, services.may_not_add_material_text(), status.HTTP_403_FORBIDDEN
                )
            product = get_object_or_404(Product, pk=body_of(request).get("product") or 0)
            hints = services.add_material(
                packlist,
                product,
                _decimal(body_of(request).get("quantity", 1), "quantity"),
                user=request.user,
                rights=request_rights(request),
            )
        elif action == "report-defect":
            from rentalars.material.models import MaterialItem

            item = get_object_or_404(MaterialItem, pk=request.data.get("item") or 0)
            services.report_return_defect(
                packlist,
                item,
                str(request.data.get("description", "")),
                photo=request.FILES.get("photo"),
                user=request.user,
            )
        elif action == "scan":
            # PCK-010, PCK-011, PCK-016: an item read from its label packs or counts back its row.
            from rentalars.packing import scan

            body = body_of(request)
            code = str(body.get("code") or "")
            rights = request_rights(request)
            outcome = (
                scan.scan_return(packlist, code, user=request.user, rights=rights)
                if body.get("mode") == "return"
                else scan.scan_pack(packlist, code, user=request.user, rights=rights)
            )
            scan_answer = dataclasses.asdict(outcome) | {"changed": outcome.changed}
        else:
            raise ValidationError(_("Unknown packing step."))
        packlist.refresh_from_db()
        document = overview_document(services.build_overview(packlist))
        document["hints"] = hints
        if scan_answer is not None:
            document["scan"] = scan_answer
        return Response(document)


class PacklistPdfView(PacklistView):
    """``GET …/packlists/{id}/pdf`` – the printable packlist (PCK-003, DOK-001)."""

    @extend_schema(parameters=_OVERVIEW_PARAMETERS, responses={(200, "application/pdf"): bytes})
    def get(self, request: Request, project_pk: int, packlist_pk: int) -> HttpResponse:
        """Return the packlist as a PDF file."""
        packlist = self.get_packlist(project_pk, packlist_pk)
        pdf = render_packlist_pdf(self.overview(packlist), show_customer=packlist.shows_customer)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{packing_list_name(packlist.project)}"'
        return response


# --- The app: packlists without network (PCK-026, PCK-027) --------------------------------------

#: A moment before this is no moment of a change on a phone (and could not be stored everywhere).
_EARLIEST_CHANGE = datetime.datetime(2000, 1, 1, tzinfo=datetime.UTC)


@extend_schema_field(OpenApiTypes.DATETIME)
class ChangeMomentField(serializers.Field):
    """A moment in ISO 8601 *with* time zone, e.g. ``2026-10-14T09:30:00+02:00`` (PCK-027).

    A moment without zone is refused: the phone keeps the time of the server
    (APP-005), and a time without zone would be read in the zone of the
    server. So is a moment that does not exist (month 13, hour 25).
    """

    def to_internal_value(self, data: Any) -> datetime.datetime:
        """Read the moment; refuse anything else."""
        try:
            value = parse_datetime(data.strip()) if isinstance(data, str) else None
        except (ValueError, OverflowError):
            value = None  # well formed, but no real moment: month 13, an offset of 25 hours
        if value is None or timezone.is_naive(value):
            raise serializers.ValidationError(
                _("Give the moment in ISO 8601 with a time zone, e.g. 2026-10-14T09:30:00+02:00."), code="invalid"
            )
        if value < _EARLIEST_CHANGE:
            raise serializers.ValidationError(_("The moment lies before the year 2000."), code="too_early")
        return value

    def to_representation(self, value: datetime.datetime) -> str:
        """The moment in ISO 8601."""
        return value.isoformat()


class SyncChangeSerializer(serializers.Serializer):
    """One change from the phone (PCK-027)."""

    line = serializers.IntegerField(min_value=1, max_value=2**63 - 1)
    product = serializers.IntegerField(min_value=1, max_value=2**63 - 1)
    field = serializers.ChoiceField(choices=list(offline.FIELDS), help_text="packed or returned")
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"))
    changed_at = ChangeMomentField(help_text="When the change was made, in the time of the server, with zone.")
    # PCK-027: both optional – older apps send neither.
    base_version = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=0,
        max_value=2**31 - 1,
        help_text="The row's version the phone saw; with it, the version decides instead of the moment.",
    )
    change_id = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=offline.MAX_CHANGE_ID,
        help_text="The phone's ID of the change (e.g. a UUID); sent again, it gets the same outcome.",
    )


class SyncSerializer(serializers.Serializer):
    """The changes of one sync, at most 1000 (PCK-027)."""

    changes = SyncChangeSerializer(many=True, max_length=offline.MAX_CHANGES)


class PacklistSyncView(PacklistView):
    """``POST …/packlists/{id}/sync`` – take over what was ticked on the phone (PCK-027).

    Body ``{"changes": [{"line", "product", "field", "quantity",
    "changed_at"}]}`` with ``field`` ``packed`` or ``returned`` and
    ``changed_at`` in ISO 8601 with time zone – at most 1000 changes. Input
    that is not valid is refused as a whole (400); nothing is taken over.

    The changes are taken in the order of their moments; a moment in the
    future counts as now. A change counts only if it is later than the last
    change of the same quantity on the server (at the same moment the server
    wins) – ``older`` otherwise. It must keep the limits of ticking in the
    browser (PCK-028), else it is ``refused`` with the reason. What counts is
    stored with its moment. The answer has the ``results`` in the order of
    the request, the whole packlist as ``GET`` delivers it, and the
    ``server_time``. Needs write access to the packlist; a read-only token
    gets 403. The sync never issues and never books a return.

    In addition, a change may carry ``base_version`` (the ``version``
    of the row the phone saw) – then the version decides: unchanged since,
    the change counts; changed, the outcome is ``conflict`` and the server's
    state stays. And ``change_id`` (e.g. a UUID): a change sent again with
    an ID already judged for the caller gets the same outcome, with
    ``replayed`` true, and is not judged again; the same ID with any other
    row, field, quantity or ``base_version`` is ``refused`` with ``reason``
    ``change_id_reused`` and nothing is applied. Each result also names the
    ``change_id``, the row's ``version`` and its ``server`` state of the
    quantity (``quantity``, ``changed_at``) after the sync. See
    ``packing.offline`` for the clock rule without ``base_version``.

    A packed quantity above the packing list, refused as before, has
    the ``reason`` ``needs_project_write`` for a caller who may not add
    material (crew packs what is planned; the message says who may) and
    ``above_packing_list`` for one who may (``…/add-material`` first). The
    other changes of the sync are taken over all the same.
    """

    @extend_schema(
        operation_id="projects_packlists_sync",
        request=SyncSerializer,
        responses={
            200: inline_serializer(
                "PacklistSyncResult",
                {
                    "results": inline_serializer(
                        "PacklistSyncChangeResult",
                        {
                            "line": serializers.IntegerField(),
                            "product": serializers.IntegerField(),
                            "field": serializers.CharField(),
                            "outcome": serializers.ChoiceField(choices=list(offline.OUTCOMES)),
                            "message": serializers.CharField(),
                            "change_id": serializers.CharField(allow_null=True),
                            "replayed": serializers.BooleanField(),
                            "reason": serializers.CharField(allow_null=True),
                            "version": serializers.IntegerField(),
                            "server": inline_serializer(
                                "PacklistSyncServerState",
                                {
                                    "quantity": serializers.DecimalField(max_digits=10, decimal_places=2),
                                    "changed_at": serializers.DateTimeField(allow_null=True),
                                },
                            ),
                        },
                        many=True,
                    ),
                    "packlist": inline_serializer("PacklistAfterSync", {"status": serializers.CharField()}),
                    "server_time": serializers.DateTimeField(),
                },
            )
        },
    )
    def post(self, request: Request, project_pk: int, packlist_pk: int) -> Response:
        """Judge and take over the changes; answer with the result of each and the packlist."""
        packlist = self.get_packlist(project_pk, packlist_pk)
        serializer = SyncSerializer(data=body_of(request))
        serializer.is_valid(raise_exception=True)
        changes = [offline.Change(**change) for change in serializer.validated_data["changes"]]
        results = offline.apply_changes(
            packlist,
            changes,
            user=request.user,
            # Names the reason of a packed quantity above the packing list.
            may_add_material=services.may_add_material(self.rights, request.user, packlist.project),
        )
        packlist.refresh_from_db()
        return Response(
            {
                "results": [
                    {
                        "line": result.line,
                        "product": result.product,
                        "field": result.field,
                        "outcome": result.outcome,
                        "message": result.message,
                        # PCK-027: in addition to what older apps read.
                        "change_id": result.change_id or None,
                        "replayed": result.replayed,
                        # "change_id_reused": the ID belongs to a different change; nothing was applied.
                        "reason": result.reason or None,
                        "version": result.version,
                        "server": {
                            "quantity": _quantity(result.server_quantity),
                            "changed_at": result.server_changed_at,
                        },
                    }
                    for result in results
                ],
                "packlist": overview_document(services.build_overview(packlist)),
                "server_time": timezone.now().astimezone(datetime.UTC),
            }
        )


class OfflinePacklistsView(ModuleAPIView):
    """``GET /offline/packlists`` – the packlists to take along on the phone (PCK-026).

    The confirmed projects that are not finished yet (``confirmed_open``,
    ``confirmed``, ``out``) whose packlist the caller may see – by the rule
    of opening a packlist, also for rights in assigned projects only. Per
    project: ``id``, ``number``, ``name``, ``status``, ``start``, ``end``,
    ``venue``, ``customer`` (the name; ``null`` with the deployment view
    only, AUT-023), ``can_write`` and its ``packlists`` as in
    ``/projects/{id}/packlists``. The rows come with ``GET`` of each
    packlist. ``server_time`` is the time of the server (APP-005).

    Reading creates nothing. A project gets its main packlist when it
    becomes confirmed (``packing.offline``); one that has none is listed
    with an empty ``packlists``.

    ``can_add_material`` – whether the caller may add material while
    packing (``…/add-material``): with write on the project, or packing for
    all projects. Crew, which packs only in its own projects, packs what is
    planned (``false``).
    """

    module = Module.PACKING

    @extend_schema(
        operation_id="offline_packlists",
        responses={
            200: inline_serializer(
                "OfflinePacklists",
                {
                    "projects": inline_serializer(
                        "OfflineProject",
                        {
                            "id": serializers.IntegerField(),
                            "number": serializers.CharField(),
                            "name": serializers.CharField(),
                            "status": serializers.CharField(),
                            "start": serializers.DateTimeField(),
                            "end": serializers.DateTimeField(),
                            "venue": serializers.CharField(),
                            "customer": serializers.CharField(allow_null=True),
                            "can_write": serializers.BooleanField(),
                            "can_add_material": serializers.BooleanField(),
                            "packlists": inline_serializer(
                                "OfflinePacklist", {"id": serializers.IntegerField()}, many=True
                            ),
                        },
                        many=True,
                    ),
                    "server_time": serializers.DateTimeField(),
                },
            )
        },
    )
    def get(self, request: Request) -> Response:
        """The projects with their packlists, earliest first."""
        found = offline.offline_projects(request_rights(request), request.user)
        return Response(
            {
                "projects": [
                    {
                        "id": entry.project.pk,
                        "number": entry.project.number,
                        "name": entry.project.name,
                        "status": entry.project.status,
                        "start": entry.project.start,
                        "end": entry.project.end,
                        "venue": entry.project.venue_label,
                        "customer": entry.project.customer_name if entry.shows_customer else None,
                        "can_write": entry.can_write,
                        "can_add_material": entry.can_add_material,  # PCK-013
                        "packlists": [
                            packlist_summary(packlist, is_main=index == 0)
                            for index, packlist in enumerate(entry.packlists)
                        ],
                    }
                    for entry in found
                ],
                "server_time": timezone.now().astimezone(datetime.UTC),
            }
        )


# --- Whole projects and their subprojects (PRJ-048, PRJ-060) ------------------------------------


def _figures_document(figures: subprojects.PackFigures) -> dict[str, Any]:
    """The progress of one part, or of all of them (PRJ-048)."""
    return {
        "required": _quantity(figures.required),
        "packed": _quantity(figures.packed),
        "issued": _quantity(figures.issued),
        "out": _quantity(figures.out),
        "back": _quantity(figures.back),
        "taken_over": _quantity(figures.taken_over),
        "handed_in": _quantity(figures.handed_in),
        "passing_on": _quantity(figures.passing_on),
        "handed_on": _quantity(figures.handed_on),
        "packed_percent": figures.packed_percent,
        "issued_percent": figures.issued_percent,
        "back_percent": figures.back_percent,
    }


def family_document(family: subprojects.FamilyPacklist) -> dict[str, Any]:
    """The packlists of a whole project and its parts as JSON, part by part and per article (PRJ-048)."""
    return {
        "whole_project": _project_ref(family.whole),
        "hidden_parts": family.hidden,
        "figures": _figures_document(family.figures),
        "parts": [
            {
                "project": {
                    **_project_ref(part.project),
                    "is_whole": part.is_whole,
                    "status": part.project.status,
                    "start": part.project.start,
                    "end": part.project.end,
                },
                "figures": _figures_document(part.figures),
                "packlists": [overview_document(overview) for overview in part.overviews],
            }
            for part in family.parts
        ],
        "articles": [
            {
                "product": article.product.pk,
                "article_number": article.product.article_number,
                "name": article.product.name,
                "unit": article.product.unit.abbreviation,
                "category": article.product.category.path,
                "from_warehouse": _quantity(article.from_warehouse),
                "taken_over": _quantity(article.taken_over),
                "packed": _quantity(article.packed),
                "issued": _quantity(article.issued),
                "returned": _quantity(article.returned),
                "parts": [
                    {
                        "project": share.project.pk,
                        "number": share.project.number,
                        "quantity": _quantity(share.quantity),
                        "is_takeover": share.is_takeover,
                    }
                    for share in article.shares
                ],
            }
            for article in family.articles
        ],
    }


class FamilyPacklistView(PacklistView):
    """``GET /projects/{id}/packlists/family`` – the whole project with all its parts, read-only (PRJ-048).

    Every row of the whole project's own packlists and of every part's
    packlists, part by part (``parts``) and summed up per article
    (``articles``), with the progress of each part. Parts whose packlist the
    caller may not see are left out; ``hidden_parts`` says how many
    (PRJ-049). The ID of a part answers for its whole project. Packing,
    issue and return stay on the packlists of the parts.
    """

    def get_family(self, project_pk: int) -> tuple[Project, subprojects.FamilyPacklist]:
        """The whole project, seen through its packlist, and the packlists of its parts."""
        project = self.get_packlist(project_pk).project
        if project.parent_id:
            project = self.get_packlist(project.parent_id).project
        return project, subprojects.build_family_packlist(
            project, rights=request_rights(self.request), user=self.request.user
        )

    @extend_schema(
        operation_id="projects_packlists_family",
        responses={200: inline_serializer("FamilyPacklist", {"hidden_parts": serializers.IntegerField()})},
    )
    def get(self, request: Request, project_pk: int) -> Response:
        """Return the packlists of the whole project and of every part the caller may see."""
        _project, family = self.get_family(project_pk)
        return Response(family_document(family))


class FamilyPacklistPdfView(FamilyPacklistView):
    """``GET /projects/{id}/packlists/family/pdf`` – the packlist of the whole project to print (PRJ-048)."""

    @extend_schema(
        operation_id="projects_packlists_family_pdf",
        parameters=[
            OpenApiParameter(
                "view",
                str,
                enum=list(subprojects.VIEWS),
                description="Part by part (default) or summed up per article.",
            )
        ],
        responses={(200, "application/pdf"): bytes},
    )
    def get(self, request: Request, project_pk: int) -> HttpResponse:
        """Return the packlist of the whole project with all its parts as a PDF file."""
        project, family = self.get_family(project_pk)
        view = request.query_params.get("view") or subprojects.VIEW_PARTS
        if view not in subprojects.VIEWS:
            raise ValidationError({"view": _("Choose “parts” or “articles”.")})
        pdf = render_family_pdf(family, view=view, show_customer=project.shows_customer)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{packing_list_name(project, whole=True)}"'
        return response


class HandoverListView(PacklistView):
    """``/projects/{id}/packlists/{packlist_id}/handovers`` – pieces taken over from other subprojects (PRJ-060).

    A row whose line takes over the pieces of a line of another subproject
    is not packed or issued in the warehouse. When the pieces arrive, the
    handover is booked here: for the other subproject they count as back,
    for this one as issued. Booking needs write access to both packlists.
    """

    @extend_schema(
        operation_id="projects_packlists_handovers_list",
        responses={200: inline_serializer("Handover", {"id": serializers.IntegerField()}, many=True)},
    )
    def get(self, request: Request, project_pk: int, packlist_pk: int) -> Response:
        """The handovers booked into this packlist, oldest first."""
        packlist = self.get_packlist(project_pk, packlist_pk)
        handovers = Handover.objects.filter(target__packlist=packlist).select_related(
            "source__packlist__project", "target", "handed_over_by"
        )
        return Response([handover_document(handover) for handover in handovers])

    @extend_schema(
        operation_id="projects_packlists_handovers_create",
        request=inline_serializer(
            "HandoverCreate",
            {
                "line": serializers.IntegerField(),
                "product": serializers.IntegerField(),
                "quantity": serializers.DecimalField(10, 2, required=False),
            },
        ),
        responses={201: inline_serializer("PacklistAfterHandover", {"status": serializers.CharField()})},
    )
    def post(self, request: Request, project_pk: int, packlist_pk: int) -> Response:
        """Book pieces of a takeover row as arrived; without ``quantity`` all that are expected and still out."""
        packlist = self.get_packlist(project_pk, packlist_pk)
        body = body_of(request)
        try:
            line_id, product_id = int(body.get("line")), int(body.get("product"))
        except (TypeError, ValueError) as error:
            raise ValidationError(_("Name the row by its line and product.")) from error
        quantity = _decimal(body["quantity"], "quantity") if body.get("quantity") is not None else None
        handover = subprojects.hand_over(
            packlist, line_id, product_id, quantity, user=request.user, rights=request_rights(request)
        )
        packlist.refresh_from_db()
        document = overview_document(services.build_overview(packlist))
        document["handover"] = handover_document(handover)
        return Response(document, status=status.HTTP_201_CREATED)


class HandoverDetailView(PacklistView):
    """``/projects/{id}/packlists/{packlist_id}/handovers/{handover_id}`` – take a handover back (PRJ-060)."""

    @extend_schema(operation_id="projects_packlists_handovers_destroy", responses={204: None})
    def delete(self, request: Request, project_pk: int, packlist_pk: int, handover_pk: int) -> Response:
        """Take back a handover booked by mistake; the pieces are with the other subproject again."""
        packlist = self.get_packlist(project_pk, packlist_pk)
        handover = get_object_or_404(Handover, pk=handover_pk, target__packlist=packlist)
        subprojects.undo_handover(handover, user=request.user, rights=request_rights(request))
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- Taking loose contents out for a project (MAT-042) ------------------------------------------


def _extraction_document(extraction: Extraction) -> dict[str, Any]:
    return {
        "id": extraction.pk,
        "project": extraction.project_id,
        "item": extraction.item_id,
        "display_id": extraction.item.display_id,
        "container": extraction.container_id,
        "container_display_id": extraction.container.display_id if extraction.container else None,
        "created_at": extraction.created_at,
    }


class ExtractionListView(PacklistView):
    """``/projects/{id}/extractions`` – loose items that stay behind for this project (MAT-042)."""

    @extend_schema(responses={200: inline_serializer("Extraction", {"id": serializers.IntegerField()}, many=True)})
    def get(self, request: Request, project_pk: int) -> Response:
        """The items taken out of their containers for the project."""
        project = self.get_packlist(project_pk).project
        rows = project.extractions.select_related("item", "container").order_by("item__inventory_number")
        return Response([_extraction_document(extraction) for extraction in rows])

    @extend_schema(
        request=inline_serializer("ExtractionCreate", {"item": serializers.IntegerField()}),
        responses={201: inline_serializer("ExtractionCreated", {"id": serializers.IntegerField()})},
    )
    def post(self, request: Request, project_pk: int) -> Response:
        """Take a loose item out of its container for this project; it is free for others meanwhile."""
        from rentalars.material.models import MaterialItem

        project = self.get_packlist(project_pk).project
        item = get_object_or_404(
            MaterialItem.objects.select_related("installed_in"), pk=body_of(request).get("item") or 0
        )
        extraction = services.extract(project, item, user=request.user)
        return Response(_extraction_document(extraction), status=status.HTTP_201_CREATED)


class ExtractionDetailView(PacklistView):
    """``/projects/{id}/extractions/{extraction_id}`` – the item travels with its container again."""

    @extend_schema(responses={204: None})
    def delete(self, request: Request, project_pk: int, extraction_pk: int) -> Response:
        """Cancel the extraction."""
        project = self.get_packlist(project_pk).project
        services.cancel_extraction(get_object_or_404(Extraction, pk=extraction_pk, project=project))
        return Response(status=status.HTTP_204_NO_CONTENT)
