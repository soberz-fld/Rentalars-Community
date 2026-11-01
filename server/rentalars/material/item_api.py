# SPDX-License-Identifier: GPL-3.0-or-later
"""API of stage 5 for material: defects, blocks, inspections, files, many items, labels, timelines.

The same services as the pages (API-002). The addresses:

* ``/material-items/{id}/defects`` – ``GET`` the reports, ``POST`` a new one with photo (MAT-023)
* ``/material-items/{id}/blocks`` and ``/material-items/{id}/blocks/{block}`` (MAT-024)
* ``/material-items/{id}/inspections`` – due and done, ``POST`` records one (MAT-031)
* ``/material-items/{id}/inspections/check`` – measured values against their limits (MAT-078)
* ``/inspections/{id}/report`` – the printable protocol of an electrical inspection (MAT-078)
* ``/material-items/{id}/files``, ``/material-models/{id}/files``, ``/material-files/{id}`` (MAT-017)
* ``/material-items/{id}/take-out`` and ``/put-back`` (MAT-043)
* ``/material-items/bulk-update`` (MAT-029)
* ``/material-items/{id}/timeline``, ``/material-models/{id}/timeline`` (VFG-019)
* ``/inspection-types`` (MAT-030), ``/inspections/due`` (MAT-032)
* ``/labels`` – the PDF of labels (MAT-026)
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field, inline_serializer
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Level, Module, SpecialRight, require
from rentalars.api.serializers import CleanModelSerializer
from rentalars.api.views import ModuleAPIView, ModuleViewSet, body_of
from rentalars.core.i18n import file_name
from rentalars.core.uploads import document_response
from rentalars.material import dguv, labels, services
from rentalars.material.inspections import InspectionPlan
from rentalars.material.models import (
    SELECTABLE_STATUS_CHOICES,
    DefectReport,
    Inspection,
    InspectionResult,
    InspectionType,
    ItemBlock,
    MaterialFile,
    MaterialFileKind,
    MaterialItem,
    MaterialModel,
    ProtectionClass,
)
from rentalars.material.spots import normalise_spot


def _item(pk: Any) -> MaterialItem:
    return get_object_or_404(
        MaterialItem.objects.select_related("material_model__category", "installed_in", "taken_out_of"), pk=pk
    )


# --- Defects (MAT-023) --------------------------------------------------------------------------


class DefectReportSerializer(serializers.ModelSerializer):
    """A defect report; the photo is delivered as an address."""

    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = DefectReport
        fields = ["id", "item", "description", "context", "reported_by", "reported_at", "photo_url"]
        read_only_fields = fields

    def get_photo_url(self, report: DefectReport) -> str:
        """Where the photo can be fetched, if there is one."""
        return reverse("material:defect_photo", args=[report.pk]) if report.photo else ""


class ItemDefectsView(ModuleAPIView):
    """``/material-items/{id}/defects`` (MAT-023)."""

    module = Module.MATERIAL
    parser_classes: ClassVar[list[Any]] = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(responses=DefectReportSerializer(many=True))
    def get(self, request: Request, pk: int) -> Response:
        """The defect reports of an item, newest first."""
        item = _item(pk)
        return Response(DefectReportSerializer(item.defect_reports.all(), many=True).data)

    @extend_schema(
        request=inline_serializer(
            "DefectReportCreate",
            {
                "description": serializers.CharField(),
                "photo": serializers.ImageField(required=False),
                "context": serializers.CharField(required=False),
            },
        ),
        responses={201: DefectReportSerializer},
    )
    def post(self, request: Request, pk: int) -> Response:
        """Report a defect: sets the item to "defective" and tells the warehouse."""
        item = _item(pk)
        report = services.report_defect(
            item,
            str(request.data.get("description", "")),
            photo=request.FILES.get("photo"),
            context=str(request.data.get("context", "")),
            user=request.user,
        )
        return Response(DefectReportSerializer(report).data, status=status.HTTP_201_CREATED)


# --- Blocks (MAT-024) ---------------------------------------------------------------------------


class ItemBlockSerializer(serializers.ModelSerializer):
    """A blocked period of an item."""

    class Meta:
        model = ItemBlock
        fields = ["id", "item", "start", "end", "reason", "created_at"]
        read_only_fields = ["id", "item", "created_at"]


class ItemBlocksView(ModuleAPIView):
    """``/material-items/{id}/blocks`` (MAT-024)."""

    module = Module.MATERIAL

    @extend_schema(responses=ItemBlockSerializer(many=True))
    def get(self, request: Request, pk: int) -> Response:
        """The blocks of an item, past ones included."""
        return Response(ItemBlockSerializer(_item(pk).blocks.all(), many=True).data)

    @extend_schema(request=ItemBlockSerializer, responses={201: ItemBlockSerializer})
    def post(self, request: Request, pk: int) -> Response:
        """Block the item for a period; its product is one piece short meanwhile."""
        item = _item(pk)
        serializer = ItemBlockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        block = services.add_block(item, data["start"], data["end"], data["reason"], user=request.user)
        return Response(ItemBlockSerializer(block).data, status=status.HTTP_201_CREATED)


class ItemBlockDetailView(ModuleAPIView):
    """``/material-items/{id}/blocks/{block}``: lift a block."""

    module = Module.MATERIAL
    action_levels: ClassVar[dict[Any, int]] = {None: Level.WRITE}

    @extend_schema(responses={204: None})
    def delete(self, request: Request, pk: int, block_pk: int) -> Response:
        """Lift the block before its end."""
        services.remove_block(get_object_or_404(ItemBlock, pk=block_pk, item_id=pk))
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- Inspections (MAT-030 to MAT-032) -----------------------------------------------------------


class InspectionTypeSerializer(CleanModelSerializer):
    """An inspection type with its interval and what it applies to (MAT-030).

    MAT-078: ``is_electrical`` – recording asks for the measured values of DIN VDE 0701-0702.
    """

    class Meta:
        model = InspectionType
        fields = [
            "id",
            "name",
            "interval_months",
            "description",
            "categories",
            "material_models",
            "is_active",
            "is_electrical",
        ]


class InspectionTypeViewSet(ModuleViewSet):
    """``/inspection-types`` (MAT-030)."""

    module = Module.MATERIAL
    queryset = InspectionType.objects.prefetch_related("categories", "material_models").order_by("name")
    serializer_class = InspectionTypeSerializer

    def perform_destroy(self, instance: InspectionType) -> None:
        """An inspection type with recorded inspections is deactivated, not deleted."""
        if instance.inspections.exists():
            raise ValidationError(_("Inspections of this type were recorded. Deactivate it instead."))
        instance.delete()


class InspectionSerializer(serializers.ModelSerializer):
    """A recorded inspection; the protocol is delivered as an address.

    MAT-078: an electrical inspection with its measured values, their limits and verdicts
    (``evaluation``) and the address of its printable protocol (``report_url``).
    """

    protocol_url = serializers.SerializerMethodField()
    evaluation = serializers.SerializerMethodField(
        help_text="An electrical inspection's values with limit and verdict, the suggested result and its "
        "reasons; null for other inspections."
    )
    report_url = serializers.SerializerMethodField(
        help_text="The printable protocol of an electrical inspection (PDF); empty for other inspections."
    )

    class Meta:
        model = Inspection
        fields = [
            "id",
            "item",
            "inspection_type",
            "date",
            "inspector",
            "result",
            "note",
            "protocol_url",
            "recorded_at",
            *dguv.ELECTRICAL_FIELDS,
            "evaluation",
            "report_url",
        ]
        read_only_fields = fields

    def get_protocol_url(self, inspection: Inspection) -> str:
        """Where the protocol can be fetched, if there is one."""
        return reverse("material:inspection_protocol", args=[inspection.pk]) if inspection.protocol else ""

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_evaluation(self, inspection: Inspection) -> dict[str, Any] | None:
        """The values against their limits (``material.dguv``)."""
        return inspection.evaluation.as_dict() if inspection.is_electrical else None

    def get_report_url(self, inspection: Inspection) -> str:
        """Where the printable protocol can be fetched."""
        return f"/api/v1/inspections/{inspection.pk}/report" if inspection.is_electrical else ""


class ElectricalValuesSerializer(serializers.Serializer):
    """MAT-078: what an electrical inspection measured – leave out or send null what was not measured.

    ``protection_class`` and ``cord_length_m`` left out take the values of the item: its protection class
    (its own, else its model's) and the length of its cord (category-specific "Länge"), as the page fills
    them in.
    """

    protection_class = serializers.ChoiceField(
        choices=ProtectionClass.choices,
        required=False,
        allow_blank=True,
        help_text="I, II or III; left out: that of the item. The limits depend on it.",
    )
    cord_length_m = serializers.DecimalField(
        max_digits=6,
        decimal_places=2,
        min_value=0,
        required=False,
        allow_null=True,
        help_text="For the limit of R_PE; left out: the category-specific length of the item; null: up to 5 m.",
    )
    test_device = serializers.CharField(max_length=120, required=False, allow_blank=True)
    visual_check_passed = serializers.BooleanField(required=False, allow_null=True, help_text="Required.")
    pe_resistance_ohm = serializers.DecimalField(
        max_digits=7, decimal_places=3, min_value=0, required=False, allow_null=True, help_text="R_PE in Ω, class I."
    )
    insulation_resistance_mohm = serializers.DecimalField(
        max_digits=9, decimal_places=3, min_value=0, required=False, allow_null=True, help_text="R_ISO in MΩ."
    )
    pe_current_ma = serializers.DecimalField(
        max_digits=7, decimal_places=3, min_value=0, required=False, allow_null=True, help_text="I_PE in mA, class I."
    )
    touch_current_ma = serializers.DecimalField(
        max_digits=7,
        decimal_places=3,
        min_value=0,
        required=False,
        allow_null=True,
        help_text="I_B in mA, classes I and II.",
    )
    function_test_passed = serializers.BooleanField(
        required=False, allow_null=True, help_text="null or left out: does not apply."
    )


def _electrical_input(request: Request, item: MaterialItem, *, electrical: bool) -> dict[str, Any] | None:
    """The measured values of a request; for an electrical inspection with the item's values where left out."""
    serializer = ElectricalValuesSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = dict(serializer.validated_data)
    if not electrical:
        return values or None  # the service refuses values for another inspection
    if "protection_class" not in request.data:
        values["protection_class"] = item.effective_protection_class
    if "cord_length_m" not in request.data:
        values["cord_length_m"] = dguv.cord_length_of(item)
    return values


class InspectionCreateSerializer(ElectricalValuesSerializer):
    """What ``POST /material-items/{id}/inspections`` takes (the description of the API)."""

    inspection_type = serializers.IntegerField()
    date = serializers.DateField()
    inspector = serializers.CharField()
    result = serializers.ChoiceField(choices=InspectionResult.choices)
    note = serializers.CharField(
        required=False, help_text="Required for “passed” although the measured values speak for “failed”."
    )
    protocol = serializers.FileField(required=False)


def _due_document(due: Any) -> dict[str, Any]:
    return {
        "inspection_type": due.inspection_type.pk,
        "name": due.inspection_type.name,
        "last_date": due.last_date,
        "last_passed": due.last_passed,
        "due_date": due.due_date,
        "state": due.state,
    }


class ItemInspectionsView(ModuleAPIView):
    """``/material-items/{id}/inspections`` (MAT-031)."""

    module = Module.MATERIAL
    parser_classes: ClassVar[list[Any]] = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(responses={200: inline_serializer("ItemInspections", {"due": serializers.ListField()})})
    def get(self, request: Request, pk: int) -> Response:
        """What is due, and what was done."""
        item = _item(pk)
        dues = InspectionPlan().dues_for([item]).get(item.pk, [])
        return Response(
            {
                "due": [_due_document(due) for due in dues],
                "done": InspectionSerializer(item.inspections.all(), many=True).data,
            }
        )

    @extend_schema(request=InspectionCreateSerializer, responses={201: InspectionSerializer})
    def post(self, request: Request, pk: int) -> Response:
        """Record an inspection; a failed one sets the item to "defective".

        MAT-078: an electrical inspection takes the measured values as well; "passed" although a value
        is outside its limit (or the visual inspection or function test did not pass) needs a ``note``.
        """
        item = _item(pk)
        inspection_type = get_object_or_404(InspectionType, pk=request.data.get("inspection_type") or 0)
        inspection = services.record_inspection(
            item,
            inspection_type,
            date=parse_date(str(request.data.get("date", ""))),
            inspector=str(request.data.get("inspector", "")),
            result=str(request.data.get("result", "")),
            note=str(request.data.get("note", "")),
            protocol=request.FILES.get("protocol"),
            user=request.user,
            electrical=_electrical_input(request, item, electrical=inspection_type.is_electrical),
        )
        return Response(InspectionSerializer(inspection).data, status=status.HTTP_201_CREATED)


class ItemInspectionCheckView(ModuleAPIView):
    """``/material-items/{id}/inspections/check`` – measured values against their limits (MAT-078).

    What the form shows while values are typed: every value with its limit and verdict and the suggested
    result with its reasons. Nothing is stored; the rights are those of recording an inspection.
    """

    module = Module.MATERIAL
    parser_classes: ClassVar[list[Any]] = [JSONParser, MultiPartParser, FormParser]

    @extend_schema(
        request=ElectricalValuesSerializer,
        responses={200: inline_serializer("InspectionCheck", {"suggested_result": serializers.CharField()})},
    )
    def post(self, request: Request, pk: int) -> Response:
        """The evaluation of the values sent, with the item's protection class and cord length where left out."""
        item = _item(pk)
        values = _electrical_input(request, item, electrical=True) or {}
        evaluation = dguv.evaluate(values)
        if not evaluation.complete:
            raise ValidationError({"protection_class": _("Choose the protection class: the limits depend on it.")})
        return Response(evaluation.as_dict())


class BatchEntrySerializer(ElectricalValuesSerializer):
    """One item of a mass inspection (MAT-082): what was found at it."""

    item = serializers.IntegerField(min_value=1, max_value=2**62, help_text="The ID (database key) of the item.")
    result = serializers.ChoiceField(
        choices=InspectionResult.choices,
        required=False,
        allow_blank=True,
        help_text="Left out for an electrical inspection: the result the measured values suggest.",
    )
    note = serializers.CharField(required=False, allow_blank=True)


class BatchInspectionCreateSerializer(serializers.Serializer):
    """What ``POST /material-items/inspections/batch`` takes (MAT-082)."""

    inspection_type = serializers.IntegerField(min_value=1, max_value=2**62)
    date = serializers.DateField()
    inspector = serializers.CharField()
    test_device = serializers.CharField(
        max_length=120,
        required=False,
        allow_blank=True,
        help_text="For every electrical inspection of the batch that names none of its own.",
    )
    items = BatchEntrySerializer(many=True, max_length=services.MAX_BULK_ITEMS)


class BatchInspectionView(ModuleAPIView):
    """``/material-items/inspections/batch`` – the same inspection of many items at once (MAT-082)."""

    module = Module.MATERIAL
    parser_classes: ClassVar[list[Any]] = [JSONParser]

    @extend_schema(request=BatchInspectionCreateSerializer, responses={201: InspectionSerializer(many=True)})
    def post(self, request: Request) -> Response:
        """All or nothing: the inspections of every item, or the errors per item (``items``: one object each).

        Date, inspector and type are common; every item has its own result, note and – for an electrical
        inspection – measured values (protection class and cord length from the item where left out).
        """
        from rest_framework.exceptions import ValidationError as ApiValidationError

        serializer = BatchInspectionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        inspection_type = get_object_or_404(InspectionType, pk=data["inspection_type"])
        ids = [entry["item"] for entry in data["items"]]
        if len(set(ids)) != len(ids):
            raise ApiValidationError({"items": [_("An item appears twice.")]})
        found = {
            item.pk: item for item in MaterialItem.objects.filter(pk__in=ids).select_related("material_model__category")
        }
        if len(found) != len(set(ids)):
            raise ApiValidationError({"items": [_("Some of the items do not exist.")]})
        raw = request.data.get("items") or []
        field_cache: dict[int, list[Any]] = {}  # the length field of a category, asked for once (not per item)
        entries = []
        for entry, given in zip(data["items"], raw, strict=True):
            item = found[entry["item"]]
            values = {name: value for name, value in entry.items() if name in dguv.ELECTRICAL_FIELDS}
            electrical: dict[str, Any] | None = None
            if inspection_type.is_electrical:
                electrical = values
                if "protection_class" not in given:
                    electrical["protection_class"] = item.effective_protection_class
                if "cord_length_m" not in given:
                    electrical["cord_length_m"] = dguv.cord_length_of(item, fields_by_category=field_cache)
            elif values:
                electrical = values  # the service refuses values for another inspection
            entries.append(
                services.BatchEntry(
                    item=item, result=entry.get("result", ""), note=entry.get("note", ""), electrical=electrical
                )
            )
        try:
            inspections = services.record_inspections(
                entries,
                inspection_type,
                date=data["date"],
                inspector=data["inspector"],
                test_device=data.get("test_device", ""),
                user=request.user,
            )
        except services.BatchInspectionError as error:
            if error.by_item:
                raise ApiValidationError(
                    {"items": [error.by_item.get(entry.item.pk, {}) for entry in entries]}
                ) from error
            raise ApiValidationError({name: [str(message)] for name, message in error.common.items()}) from error
        return Response(InspectionSerializer(inspections, many=True).data, status=status.HTTP_201_CREATED)


class InspectionReportView(ModuleAPIView):
    """``/inspections/{id}/report`` – the printable protocol of an electrical inspection as PDF (MAT-078)."""

    module = Module.MATERIAL

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def get(self, request: Request, pk: int) -> HttpResponse:
        """The protocol: company, item, date, inspector, test device, values with limits and verdicts, result."""
        from rentalars.material.inspection_report import render_report_pdf, report_file_name

        inspection = get_object_or_404(
            Inspection.objects.select_related("item__material_model__manufacturer", "inspection_type"), pk=pk
        )
        if not inspection.is_electrical:
            raise Http404
        response = HttpResponse(render_report_pdf(inspection), content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{report_file_name(inspection)}"'
        return response


class DueInspectionsView(ModuleAPIView):
    """``/inspections/due`` – overdue and soon due inspections of all items (MAT-032)."""

    module = Module.MATERIAL

    @extend_schema(
        parameters=[OpenApiParameter("days", int), OpenApiParameter("type", int)],
        responses={200: inline_serializer("DueInspection", {"item": serializers.IntegerField()}, many=True)},
    )
    def get(self, request: Request) -> Response:
        """Most urgent first; ``days`` widens "soon" (default 30)."""
        try:
            within = max(0, min(365, int(request.query_params.get("days", 30))))
        except ValueError:
            within = 30
        type_id = request.query_params.get("type", "")
        plan = InspectionPlan()
        rows = plan.with_items(
            plan.due_rows(within_days=within, type_id=int(type_id) if type_id.isdigit() else None)[:2000]
        )
        return Response([{"item": item.pk, "display_id": item.display_id, **_due_document(due)} for item, due in rows])


# --- Files (MAT-017) ----------------------------------------------------------------------------


class MaterialFileSerializer(serializers.ModelSerializer):
    """A picture or document of a model or item."""

    url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = MaterialFile
        fields = [
            "id",
            "material_model",
            "item",
            "kind",
            "title",
            "original_name",
            "size",
            "uploaded_at",
            "url",
            "thumbnail_url",
        ]
        read_only_fields = fields

    def get_url(self, stored: MaterialFile) -> str:
        """Where the content can be fetched."""
        return f"/api/v1/material-files/{stored.pk}/content"

    def get_thumbnail_url(self, stored: MaterialFile) -> str | None:
        """Where the preview of a photo can be fetched (MAT-090); ``null`` for a document."""
        return f"/api/v1/material-files/{stored.pk}/thumbnail" if stored.kind == MaterialFileKind.PICTURE else None


_FILE_UPLOAD = inline_serializer(
    "MaterialFileUpload",
    {
        "file": serializers.FileField(),
        "kind": serializers.ChoiceField(choices=MaterialFileKind.choices),
        "title": serializers.CharField(required=False),
    },
)


class _FilesView(ModuleAPIView):
    module = Module.MATERIAL
    parser_classes: ClassVar[list[Any]] = [MultiPartParser, FormParser]

    def owner(self, pk: int) -> MaterialModel | MaterialItem:
        raise NotImplementedError

    @extend_schema(responses=MaterialFileSerializer(many=True))
    def get(self, request: Request, pk: int) -> Response:
        """The files."""
        # The copy of an invoice shows the purchase prices – only with that right.
        return Response(
            MaterialFileSerializer(services.visible_files(self.owner(pk).files.all(), self.rights), many=True).data
        )

    @extend_schema(request=_FILE_UPLOAD, responses={201: MaterialFileSerializer})
    def post(self, request: Request, pk: int) -> Response:
        """Upload a file (multipart)."""
        uploaded = request.FILES.get("file")
        if uploaded is None:
            raise ValidationError({"file": _("Choose a file.")})
        kind = str(request.data.get("kind", MaterialFileKind.OTHER))
        if not services.may_add_file_of_kind(kind, self.rights):
            raise PermissionDenied
        stored = services.add_file(
            self.owner(pk),
            uploaded,
            kind=kind,
            title=str(request.data.get("title", "")),
            user=request.user,
        )
        return Response(MaterialFileSerializer(stored).data, status=status.HTTP_201_CREATED)


class ItemFilesView(_FilesView):
    """``/material-items/{id}/files`` (MAT-017)."""

    def owner(self, pk: int) -> MaterialItem:
        """The item."""
        return _item(pk)


class ModelFilesView(_FilesView):
    """``/material-models/{id}/files`` (MAT-017)."""

    def owner(self, pk: int) -> MaterialModel:
        """The model."""
        return get_object_or_404(MaterialModel, pk=pk)


class MaterialFileDetailView(ModuleAPIView):
    """``/material-files/{id}``: describe or remove a file."""

    module = Module.MATERIAL

    @extend_schema(responses=MaterialFileSerializer)
    def get(self, request: Request, pk: int) -> Response:
        """The description of the file."""
        return Response(MaterialFileSerializer(self.stored(pk)).data)

    def stored(self, pk: int) -> MaterialFile:
        """The file, if the caller may see it (an invoice copy needs the right to see purchase prices; R1-1)."""
        return get_object_or_404(services.visible_files(MaterialFile.objects.all(), self.rights), pk=pk)

    @extend_schema(responses={204: None})
    def delete(self, request: Request, pk: int) -> Response:
        """Remove the file."""
        services.delete_file(self.stored(pk))
        return Response(status=status.HTTP_204_NO_CONTENT)


class MaterialFileContentView(ModuleAPIView):
    """``/material-files/{id}/content``: the file itself."""

    module = Module.MATERIAL

    @extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY})
    def get(self, request: Request, pk: int) -> HttpResponse:
        """The content, shown or downloaded depending on its type."""
        stored = get_object_or_404(services.visible_files(MaterialFile.objects.all(), self.rights), pk=pk)
        return document_response(stored.file.name, stored.original_name)


class MaterialFileThumbnailView(ModuleAPIView):
    """``/material-files/{id}/thumbnail``: the preview of a photo (MAT-090)."""

    module = Module.MATERIAL

    @extend_schema(responses={(200, "image/jpeg"): OpenApiTypes.BINARY})
    def get(self, request: Request, pk: int) -> HttpResponse:
        """The preview; an older picture has none and is delivered whole."""
        stored = get_object_or_404(services.visible_files(MaterialFile.objects.all(), self.rights), pk=pk)
        if stored.kind != MaterialFileKind.PICTURE:
            raise Http404
        return document_response((stored.thumbnail or stored.file).name, stored.original_name)


# --- Taking out, putting back (MAT-043); many items (MAT-029) ----------------------------------


class ItemTakeOutView(ModuleAPIView):
    """``/material-items/{id}/take-out``: take a loose item out of its container (MAT-043)."""

    module = Module.MATERIAL

    @extend_schema(
        request=None, responses={200: inline_serializer("ItemMoved", {"taken_out_of": serializers.IntegerField()})}
    )
    def post(self, request: Request, pk: int) -> Response:
        """Take it out; the container is remembered for putting it back."""
        item = _item(pk)
        services.take_out(item)
        return Response({"id": item.pk, "installed_in": None, "taken_out_of": item.taken_out_of_id})


class ItemPutBackView(ModuleAPIView):
    """``/material-items/{id}/put-back``: put it back where it was taken out (MAT-043)."""

    module = Module.MATERIAL

    @extend_schema(
        request=None, responses={200: inline_serializer("ItemPutBack", {"installed_in": serializers.IntegerField()})}
    )
    def post(self, request: Request, pk: int) -> Response:
        """Put it back."""
        item = _item(pk)
        services.put_back(item)
        return Response({"id": item.pk, "installed_in": item.installed_in_id, "taken_out_of": None})


class BulkUpdateView(ModuleAPIView):
    """``/material-items/bulk-update``: change many items at once (MAT-029)."""

    module = Module.MATERIAL

    @extend_schema(
        request=inline_serializer(
            "ItemBulkUpdate",
            {
                "items": serializers.ListField(child=serializers.IntegerField()),
                "status": serializers.ChoiceField(choices=SELECTABLE_STATUS_CHOICES, required=False),
                "status_reason": serializers.CharField(required=False),
                "storage_location": serializers.IntegerField(required=False, allow_null=True),
                "storage_spot": serializers.CharField(required=False, allow_blank=True, max_length=12),
                "product_override": serializers.IntegerField(required=False, allow_null=True),
            },
        ),
        responses={200: inline_serializer("ItemBulkUpdated", {"changed": serializers.IntegerField()})},
    )
    def post(self, request: Request) -> Response:
        """All or nothing. ``storage_location`` / ``product_override`` ``null`` remove the value; left out keeps it.

        ``storage_spot`` (MAT-080): a new spot for all of them; a move to another location without one removes the old spot.
        """
        from rentalars.masterdata.models import StorageLocation
        from rentalars.products.models import Product

        body = body_of(request)
        ids = body.get("items") or []
        if not isinstance(ids, list):
            raise ValidationError({"items": _("Expected a list of IDs.")})
        items = list(MaterialItem.objects.filter(pk__in=ids).select_related("material_model__category"))
        if len(items) != len(set(ids)):
            raise ValidationError({"items": _("Some of the items do not exist.")})
        changes: dict[str, Any] = {"status": body.get("status") or None, "reason": str(body.get("status_reason", ""))}
        if "storage_location" in body:
            value = body["storage_location"]
            changes["storage_location"] = get_object_or_404(StorageLocation, pk=value) if value else None
        if "product_override" in body:
            value = body["product_override"]
            changes["product"] = get_object_or_404(Product, pk=value) if value else None
        if body.get("storage_spot"):
            changes["storage_spot"] = normalise_spot(str(body["storage_spot"]))
        hints = services.bulk_update(items, **changes)
        return Response({"changed": len(items), "warnings": hints})


# --- Timelines (VFG-019) ------------------------------------------------------------------------


_TIMELINE_PARAMETERS = [OpenApiParameter("from", OpenApiTypes.DATE), OpenApiParameter("weeks", int)]
_TIMELINE_RESPONSE = inline_serializer("Timeline", {"days": serializers.ListField(child=serializers.DateField())})


def _visible(request: Request) -> set[int]:
    from rentalars.accounts.rights import request_rights
    from rentalars.projects.access import visible_projects

    return set(visible_projects(request_rights(request), request.user).values_list("pk", flat=True))


class ItemTimelineView(ModuleAPIView):
    """``/material-items/{id}/timeline`` (VFG-019)."""

    module = Module.MATERIAL

    @extend_schema(parameters=_TIMELINE_PARAMETERS, responses=_TIMELINE_RESPONSE)
    def get(self, request: Request, pk: int) -> Response:
        """Deployments, wishes, blocks, inspections of the item and the free pieces of its product.

        AUT-032: needs the special right to see the availability of material.
        """
        from rentalars.schedule.services import span_from_request
        from rentalars.schedule.timelines import item_timeline, timeline_document

        require(self.rights.has(SpecialRight.AVAILABILITY))
        days, _navigation = span_from_request(request, default_weeks=4)
        return Response(timeline_document(item_timeline(_item(pk), days, _visible(request))))


class ModelTimelineView(ModuleAPIView):
    """``/material-models/{id}/timeline`` (VFG-019)."""

    module = Module.MATERIAL

    @extend_schema(parameters=_TIMELINE_PARAMETERS, responses=_TIMELINE_RESPONSE)
    def get(self, request: Request, pk: int) -> Response:
        """The free pieces of the model's product and one row per item; AUT-032: needs the right to see availability."""
        from rentalars.schedule.services import span_from_request
        from rentalars.schedule.timelines import model_timeline, timeline_document

        require(self.rights.has(SpecialRight.AVAILABILITY))
        days, _navigation = span_from_request(request, default_weeks=4)
        return Response(
            timeline_document(model_timeline(get_object_or_404(MaterialModel, pk=pk), days, _visible(request)))
        )


# --- Labels (MAT-026) ---------------------------------------------------------------------------


class LabelsView(ModuleAPIView):
    """``/labels``: the labels of some items as PDF (MAT-026).

    MAT-056: ``format`` is also ``small``, ``large`` or ``cable`` – the
    labels of Einstellungen → Etiketten; without it, the one suggested there.
    ``code`` and ``skip`` matter only for the sheets and the roll.
    """

    module = Module.MATERIAL
    #: Making a PDF changes nothing; reading material is enough.
    action_levels: ClassVar[dict[Any, int]] = {None: Level.READ}

    @extend_schema(
        request=inline_serializer(
            "LabelRequest",
            {
                "items": serializers.ListField(child=serializers.IntegerField()),
                "format": serializers.ChoiceField(
                    choices=["small", "large", "cable", *labels.FORMATS],
                    required=False,
                    help_text="small, large, cable: the labels of Einstellungen → Etiketten (always with a QR "
                    "code). Without it the A4 sheet of 24.",
                ),
                "code": serializers.ChoiceField(choices=labels.CODE_CHOICES, required=False),
                "skip": serializers.IntegerField(required=False),
            },
        ),
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    def post(self, request: Request) -> HttpResponse:
        """The labels of the items with these database IDs, as PDF.

        Up to 240 labels come at once; more are made in the background and the
        answer names the task (``202``, ``/api/v1/jobs/{id}``).
        """
        from rentalars.core.jobs import start_job

        body = body_of(request)
        ids = body.get("items") or []
        if not isinstance(ids, list) or not ids:
            raise ValidationError({"items": _("Expected a list of item IDs.")})
        if len(ids) > labels.MAX_LABELS:
            raise ValidationError({"items": _("At most %(count)d labels at once.") % {"count": labels.MAX_LABELS}})
        order = {pk: index for index, pk in enumerate(ids)}
        items = sorted(
            MaterialItem.objects.filter(pk__in=ids).select_related("material_model"), key=lambda item: order[item.pk]
        )
        # A program that names no format gets the sheet, not the new default
        # of the pages (Einstellungen → Etiketten).
        wanted = str(body.get("format") or labels.DEFAULT_FORMAT)
        if wanted not in labels.all_formats():
            raise ValidationError(
                {"format": _("Choose one of: %(values)s.") % {"values": ", ".join(labels.all_formats())}}
            )
        options = {
            "label_format": wanted,
            "code": str(body.get("code", labels.CODE_QR)),
            "skip": int(body.get("skip", 0) or 0),
        }
        if len(items) > labels.MAX_LABELS_DIRECT:
            job = start_job(
                "labels",
                {"numbers": [item.inventory_number for item in items], **options},
                user=request.user,
                title=_("Labels for %(count)d items") % {"count": len(items)},
            )
            return Response({"job": job.pk, "status": job.status}, status=status.HTTP_202_ACCEPTED)
        response = HttpResponse(labels.render_labels_pdf(items, **options), content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{file_name("labels", extension="pdf")}"'
        return response
