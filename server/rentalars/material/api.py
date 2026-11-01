# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the material module: models, items, history, import (chapter 8)."""

from __future__ import annotations

import datetime
from typing import Any, ClassVar

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Level, Module, SpecialRight
from rentalars.api.serializers import CleanModelSerializer, ExpandableFieldsMixin, RestrictedFieldsMixin
from rentalars.api.views import ModuleViewSet, body_of
from rentalars.customfields import api as custom
from rentalars.masterdata.api import CategorySerializer, SupplierSerializer
from rentalars.material import audits, partial_dates, services
from rentalars.material import serials as serial_check
from rentalars.material.filters import MaterialItemFilter
from rentalars.material.history import item_history
from rentalars.material.models import ConnectionType, MaterialItem, MaterialModel


class MaterialModelSerializer(ExpandableFieldsMixin, CleanModelSerializer):
    """A material model (the "model" level of MAT-011)."""

    category_specific_value = serializers.CharField(required=False, allow_blank=True)
    category_specific_display = serializers.CharField(read_only=True)
    item_count = serializers.IntegerField(read_only=True)
    field_values = serializers.DictField(
        child=serializers.CharField(allow_blank=True),
        required=False,
        help_text="All category-specific values by the ID of their field (MAT-010); an empty value removes one.",
    )
    volume_litres = serializers.DecimalField(max_digits=10, decimal_places=1, read_only=True)
    suggested_purchase = serializers.SerializerMethodField(help_text="Supplier of the item created last (MAT-014).")
    category_hint = serializers.SerializerMethodField(
        help_text="Set if the product is of another main category (PRD-032)."
    )
    # MAT-072: the ID of the model's fieldset, or null.
    fieldset = custom.FieldsetAssignmentField()
    pieces_per_product = serializers.SerializerMethodField(
        help_text="How many items of this model one piece of its product consists of (1 without product). "
        "Set at the product (``pieces_per_product``); read-only here."
    )

    expandable_fields = {"category": CategorySerializer}

    class Meta:
        model = MaterialModel
        fields = [
            "id",
            "name",
            "short_name",
            "category",
            "manufacturer",
            "specification",
            "category_specific_value",
            "category_specific_display",
            "field_values",
            "default_product",
            "tracking_mode",
            "weight_kg",
            "length_cm",
            "width_cm",
            "height_cm",
            "volume_litres",
            "power_w",
            "protection_class",  # MAT-077: I, II, III or empty
            "item_count",
            "suggested_purchase",
            "category_hint",
            "fieldset",
            "pieces_per_product",
        ]

    def get_pieces_per_product(self, model: MaterialModel) -> int:
        """The pieces of the model's product; one for a model without product."""
        return model.pieces_per_product

    def get_suggested_purchase(self, model: MaterialModel) -> dict[str, Any]:
        """Supplier and supplier's article number for the next item of this model (MAT-014)."""
        if self.context.get("view") is not None and getattr(self.context["view"], "action", None) == "list":
            return {}
        return services.suggested_purchase_fields(model)

    def get_category_hint(self, model: MaterialModel) -> str:
        """A hint if the product belongs to another main category (PRD-032)."""
        return services.category_mismatch(model.category, model.default_product)

    def _apply_fields(self, model: MaterialModel, values: dict[str, str] | None) -> None:
        """Store further category-specific values, each checked against its field (MAT-010)."""
        if not values:
            return
        fields = {str(field.pk): field for field in model.category.applicable_fields()}
        errors = {}
        for key, value in values.items():
            field = fields.get(str(key))
            if field is None:
                errors[str(key)] = _("The category has no such field.")
                continue
            try:
                model.set_field_value(field, value)
            except ValidationError as error:
                errors[str(key)] = " ".join(error.messages)
        if errors:
            raise ValidationError({"field_values": [f"{key}: {text}" for key, text in errors.items()]})

    def create(self, validated_data: dict[str, Any]) -> MaterialModel:
        """Create the model; the category-specific values are checked against their field types (MAT-009)."""
        specific = validated_data.pop("category_specific_value", None)
        values = validated_data.pop("field_values", None)
        fieldset = custom.take_fieldset(validated_data)  # MAT-072
        model = MaterialModel(**validated_data)
        if specific is not None:
            model.set_category_specific_value(specific)
        self._apply_fields(model, values)
        model.full_clean()
        model.save()
        custom.store_fieldset(model, fieldset)
        return model

    def update(self, instance: MaterialModel, validated_data: dict[str, Any]) -> MaterialModel:
        """Change the model."""
        specific = validated_data.pop("category_specific_value", None)
        values = validated_data.pop("field_values", None)
        fieldset = custom.take_fieldset(validated_data)  # MAT-072
        for name, value in validated_data.items():
            setattr(instance, name, value)
        if specific is not None:
            instance.set_category_specific_value(specific)
        self._apply_fields(instance, values)
        instance.full_clean()
        instance.save()
        custom.store_fieldset(instance, fieldset)
        return instance


class PriceEntryFieldsMixin(serializers.Serializer):
    """A purchase price sent net or gross (MAT-059; IMP-014).

    ``prices``: whether ``purchase_price`` is ``net`` (the default) or
    ``gross`` – the names of the choice of the material import;
    ``price_tax_rate``: the per cent a gross price includes, one of the
    active tax rates, by default the default tax rate. A gross price is
    stored net, rounded to cents; the answer shows the stored net price.
    Both need the right to see purchase prices, as the price itself.
    """

    prices = serializers.ChoiceField(
        choices=[("net", "net"), ("gross", "gross")],
        required=False,
        write_only=True,
        help_text="Whether purchase_price is net (default) or gross; a gross price is stored net.",
    )
    price_tax_rate = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        write_only=True,
        help_text="The tax rate in per cent a gross purchase_price includes; default: the default tax rate.",
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Take ``prices`` and ``price_tax_rate`` out of the values and turn a gross price into the net one."""
        attrs = super().validate(attrs)
        prices = attrs.pop("prices", "net")
        rate = attrs.pop("price_tax_rate", None)
        if attrs.get("purchase_price") is not None:
            attrs["purchase_price"] = services.entered_purchase_price(attrs["purchase_price"], prices, rate)
        return attrs


@extend_schema_field({"type": "string", "nullable": True, "example": "2015-00-00"})
class PurchaseDateField(serializers.Field):
    """Partial purchase date: the invoice date, of an old item with an unknown day or month.

    Sent and delivered as ISO text: ``2015-05-12``, ``2015-05-00`` (day unknown), ``2015-00-00`` (month and day
    unknown); also accepted: ``2015-05``, ``2015`` and the German ``12.05.2015``, ``00.05.2015``, ``00.00.2015``.
    A complete date reads exactly as before.
    """

    def get_attribute(self, instance: MaterialItem) -> MaterialItem:
        """Hand the whole item over: the date alone does not tell how much of it is known."""
        return instance

    def to_representation(self, value: MaterialItem) -> str | None:
        """The ISO text, or null without a date."""
        return value.purchase_date_iso or None

    def to_internal_value(self, data: Any) -> partial_dates.PartialDate:
        """The typed text as :class:`~rentalars.material.partial_dates.PartialDate`."""
        message = _("Enter a date like 2015-05-12, 2015-05-00 or 2015-00-00 (day and month unknown).")
        if not isinstance(data, str):
            raise serializers.ValidationError(message)
        try:
            return partial_dates.parse(data)
        except ValueError:
            raise serializers.ValidationError(message) from None


class PartialPurchaseDateMixin(serializers.Serializer):
    """``purchase_date`` as :class:`PurchaseDateField`; the values get ``purchase_date_precision`` next to the date."""

    purchase_date = PurchaseDateField(
        required=False,
        allow_null=True,
        help_text="The invoice date as 2015-05-12; of an old item 2015-05-00 or 2015-00-00 when the day or "
        "month is unknown (see purchase_date_precision).",
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Split the date from its precision for the model."""
        attrs = super().validate(attrs)
        if "purchase_date" in attrs:
            bought = attrs["purchase_date"]
            attrs["purchase_date"] = bought.date if bought is not None else None
            attrs["purchase_date_precision"] = bought.precision if bought is not None else partial_dates.DAY
        return attrs


#: The fields of :class:`PriceEntryFieldsMixin` need the right to see purchase prices (AUT-019).
PRICE_ENTRY_RIGHTS = {"prices": SpecialRight.PURCHASE_PRICES, "price_tax_rate": SpecialRight.PURCHASE_PRICES}


class MaterialItemSerializer(
    RestrictedFieldsMixin,
    ExpandableFieldsMixin,
    PriceEntryFieldsMixin,
    PartialPurchaseDateMixin,
    serializers.ModelSerializer,
):
    """A material item with the 13 fields of MAT-011 in one row (MAT-012).

    Fields of the model level (article name, category, specification,
    category-specific value) are delivered read-only next to the item's own
    fields. The purchase price needs its special right (AUT-019).

    ``status`` and ``status_reason`` belong together (MAT-044): a new status
    takes the reason sent with it, or none. "defective" needs a reason, and
    a defective item can only go to "in_repair", "retired" or "sold"
    (MAT-045).
    """

    inventory_number = serializers.IntegerField(required=False, min_value=1)
    display_id = serializers.CharField(read_only=True)
    name = serializers.CharField(source="material_model.name", read_only=True)
    category = serializers.IntegerField(source="material_model.category_id", read_only=True)
    category_name = serializers.CharField(source="material_model.category.path", read_only=True)
    specification = serializers.CharField(source="material_model.specification", read_only=True)
    category_specific = serializers.CharField(source="category_specific_display", read_only=True)
    effective_specification = serializers.CharField(read_only=True)
    effective_storage_location = serializers.SerializerMethodField()
    # MAT-080: the spot within the location – of the item's container for an installed one.
    effective_storage_spot = serializers.CharField(read_only=True)
    taken_out_of = serializers.PrimaryKeyRelatedField(read_only=True)
    product = serializers.SerializerMethodField()
    # MAT-069: the last audit, when the next one is due, whether it is due now, the open to-dos.
    last_audit = serializers.SerializerMethodField(help_text="When the item was last audited; null: never.")
    next_audit = serializers.SerializerMethodField(
        help_text="The day its next audit is due; null: never (audits off, archived, bulk material)."
    )
    audit_due = serializers.SerializerMethodField(help_text="Whether its audit is due today or earlier.")
    open_todos = serializers.SerializerMethodField(help_text="The number of its open to-dos.")
    # MAT-077: the protection class that applies – the item's own (protection_class_override), else its model's.
    effective_protection_class = serializers.CharField(read_only=True)

    # MAT-073: the values of the fields of the model's fieldset, by field name.
    custom_fields = custom.CustomValuesField()

    # Incoming invoices: what the item cost with its share of the ancillary costs and what it is for the books –
    # set when it is booked in from an incoming invoice, read-only here. The costs need the right to see purchase prices.
    asset_kind = serializers.CharField(
        read_only=True, help_text="merchandise, low_value (GWG) or fixed_asset; empty: not set (an older item)."
    )
    useful_life_months = serializers.IntegerField(
        read_only=True, help_text="Months of depreciation of a fixed asset; null for the others."
    )
    ancillary_cost_net = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True, help_text="Its share of the ancillary costs (freight …), net."
    )
    acquisition_cost_net = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True, help_text="Purchase price plus the share of ancillary costs."
    )
    source_position = serializers.PrimaryKeyRelatedField(
        read_only=True, help_text="The position of the incoming invoice it was made of."
    )
    source_invoice = serializers.SerializerMethodField(help_text="The incoming invoice it was made of.")

    purchase_date_precision = serializers.CharField(
        read_only=True,
        help_text="How much of purchase_date is known: day, month or year (then the day and month are 00).",
    )

    restricted_fields = {
        "purchase_price": SpecialRight.PURCHASE_PRICES,
        "purchase_price_in": SpecialRight.PURCHASE_PRICES,
        "ancillary_cost_net": SpecialRight.PURCHASE_PRICES,
        "acquisition_cost_net": SpecialRight.PURCHASE_PRICES,
        **PRICE_ENTRY_RIGHTS,  # MAT-059
    }
    expandable_fields = {"supplier": SupplierSerializer, "material_model": MaterialModelSerializer}

    class Meta:
        model = MaterialItem
        fields = [
            "id",
            "inventory_number",
            "display_id",
            "material_model",
            "name",
            "category",
            "category_name",
            "specification",
            "category_specific",
            "installed_in",
            "connection_type",
            "individually_rentable",
            "serial_number",
            "note",
            "purchase_date",
            "purchase_date_precision",
            "invoice_number",
            "purchase_note",
            "purchase_price",
            "purchase_price_in",
            "prices",
            "price_tax_rate",
            "supplier",
            "supplier_article_number",
            "status",
            "status_reason",
            "storage_location",
            "storage_spot",
            "quantity",
            "product_override",
            "product",
            "specification_override",
            "field_value_overrides",
            "effective_specification",
            "protection_class_override",
            "effective_protection_class",
            "effective_storage_location",
            "effective_storage_spot",
            "taken_out_of",
            "last_audit",
            "next_audit",
            "audit_due",
            "open_todos",
            "custom_fields",
            "asset_kind",
            "useful_life_months",
            "ancillary_cost_net",
            "acquisition_cost_net",
            "source_position",
            "source_invoice",
        ]

    def get_source_invoice(self, item: MaterialItem) -> int | None:
        """The incoming invoice the item was booked in from; null for an item entered otherwise."""
        return item.source_position.invoice_id if item.source_position_id else None

    def get_effective_storage_location(self, item: MaterialItem) -> int | None:
        """Where the item is kept; for an installed item, where its container is (MAT-038)."""
        location = item.effective_storage_location
        return location.pk if location is not None else None

    def validate_field_value_overrides(self, value: Any) -> dict[str, str]:
        """Own values for category-specific fields, by field ID (MAT-013)."""
        if not isinstance(value, dict):
            raise serializers.ValidationError(_("Expected an object of field IDs and values."))
        return {str(key): "" if text is None else str(text) for key, text in value.items()}

    def _apply_overrides(self, item: MaterialItem, values: dict[str, str] | None) -> None:
        if values is None:
            return
        fields = {str(field.pk): field for field in item.material_model.category.applicable_fields()}
        item.field_value_overrides = {}
        for key, text in values.items():
            field = fields.get(key)
            if field is None:
                raise ValidationError({"field_value_overrides": _("The category has no field %(id)s.") % {"id": key}})
            item.set_field_override(field, text)

    def get_last_audit(self, item: MaterialItem) -> datetime.datetime | None:
        """MAT-069: the moment of the last audit."""
        return audits.audit_fields(item)["last_audit"]

    def get_next_audit(self, item: MaterialItem) -> datetime.date | None:
        """MAT-069: the day the next audit is due."""
        return audits.audit_fields(item)["next_audit"]

    def get_audit_due(self, item: MaterialItem) -> bool:
        """MAT-069: whether the audit is due."""
        return audits.audit_fields(item)["audit_due"]

    def get_open_todos(self, item: MaterialItem) -> int:
        """MAT-069: how many to-dos are open."""
        return audits.audit_fields(item)["open_todos"]

    def get_product(self, item: MaterialItem) -> int | None:
        """The ID of the product the item belongs to (PRD-003)."""
        return item.product_override_id or item.material_model.default_product_id

    def create(self, validated_data: dict[str, Any]) -> MaterialItem:
        """Create one item; without ``inventory_number`` the next free ID is taken (MAT-003)."""
        material_model = validated_data.pop("material_model")
        inventory_number = validated_data.pop("inventory_number", None)
        validated_data.pop("field_value_overrides", None)
        values = custom.checked_values(self, validated_data, material_model, None, creating=True)  # MAT-073
        with transaction.atomic():
            item = services.create_items(material_model, 1, inventory_number=inventory_number, **validated_data)[0]
            custom.store_checked([item], values)
        self.context["warnings"] = services.serial_number_warnings(item)
        return item

    def update(self, instance: MaterialItem, validated_data: dict[str, Any]) -> MaterialItem:
        """Change an item; warnings (duplicate serial number, PRD-032) are added to the answer (MAT-004)."""
        new_status = validated_data.pop("status", instance.status)
        reason = validated_data.pop("status_reason", None)
        overrides = validated_data.pop("field_value_overrides", None)
        material_model = validated_data.get("material_model", instance.material_model)
        # MAT-073: the custom values, checked against the fieldset of the model.
        values = custom.checked_values(self, validated_data, material_model, instance, creating=False)
        for name, value in validated_data.items():
            setattr(instance, name, value)
        self._apply_overrides(instance, overrides)
        if new_status != instance.status:
            services.apply_status(instance, new_status, reason or "")
        elif reason is not None:
            instance.status_reason = reason
        with transaction.atomic():
            self.context["warnings"] = services.save_item(instance)
            custom.store_checked([instance], values)
        hint = services.category_mismatch(instance.material_model.category, instance.product_override)
        if hint:
            self.context["warnings"].append(hint)
        return instance

    def to_representation(self, instance: MaterialItem) -> dict[str, Any]:
        """Append non-blocking warnings after a write."""
        data = super().to_representation(instance)
        if self.context.get("warnings"):
            data["warnings"] = self.context["warnings"]
        # Duplicate serial numbers: several items created at once – the warnings of each one.
        elif self.context.get("item_warnings", {}).get(instance.pk):
            data["warnings"] = self.context["item_warnings"][instance.pk]
        return data


class BulkCreateSerializer(
    RestrictedFieldsMixin, PriceEntryFieldsMixin, PartialPurchaseDateMixin, serializers.ModelSerializer
):
    """Input for creating several items of a model in one step (MAT-006, MAT-050).

    ``start_number``: the first item gets this ID, each further one the next
    free ID after it; without it the next free IDs of the number range.
    ``serial_numbers``: one per item in the order of the IDs; an empty text
    leaves that item without one. MAT-059: ``prices`` and ``price_tax_rate``
    for a gross purchase price (:class:`PriceEntryFieldsMixin`).
    """

    count = serializers.IntegerField(min_value=1, max_value=services.MAX_ITEMS_PER_BATCH, default=1)
    start_number = serializers.IntegerField(min_value=1, required=False, help_text="MAT-050: the ID of the first item.")
    serial_numbers = serializers.ListField(
        child=serializers.CharField(allow_blank=True, max_length=120),
        required=False,
        max_length=services.MAX_ITEMS_PER_BATCH,
        help_text="MAT-050: one serial number per item, in the order of the IDs.",
    )
    price_for_set = serializers.BooleanField(
        default=False,
        help_text="MAT-054: the purchase price is that of all the items together; the first gets it, "
        "the others have it included in the first.",
    )
    # MAT-073: values for all new items; with several items required ones may stay empty.
    custom_fields = custom.CustomValuesField()
    restricted_fields = {"purchase_price": SpecialRight.PURCHASE_PRICES, **PRICE_ENTRY_RIGHTS}

    class Meta:
        model = MaterialItem
        fields = [
            "count",
            "start_number",
            "serial_numbers",
            "price_for_set",
            "purchase_date",
            "invoice_number",
            "purchase_note",
            "purchase_price",
            "prices",
            "price_tax_rate",
            "supplier",
            "supplier_article_number",
            "status",
            "storage_location",
            "storage_spot",
            "note",
            "quantity",
            "custom_fields",
        ]


class MaterialModelViewSet(ModuleViewSet):
    """``/material-models`` – the article types; their items live below ``/items``."""

    module = Module.MATERIAL
    queryset = (
        MaterialModel.objects.select_related("category", "manufacturer", "default_product", "custom_fieldset")
        .with_category_fields()
        .with_item_count()
        .order_by("name")
    )
    serializer_class = MaterialModelSerializer
    search_fields = ["name", "short_name", "specification"]
    filterset_fields = ["category", "manufacturer", "default_product", "tracking_mode"]
    ordering_fields = ["name"]

    @extend_schema(methods=["get"], responses=MaterialItemSerializer(many=True))
    @extend_schema(methods=["post"], request=BulkCreateSerializer, responses=MaterialItemSerializer(many=True))
    @action(detail=True, methods=["get", "post"])
    def items(self, request: Request, pk: str | None = None) -> Response:
        """List the items of a model, or create several at once with consecutive IDs (MAT-006).

        A serial number that another item has already (any model, retired and sold ones too) or that is given
        twice is no error; the item in the answer carries ``warnings`` (MAT-004).
        """
        material_model = self.get_object()
        context = self.get_serializer_context()
        if request.method == "POST":
            serializer = BulkCreateSerializer(data=request.data, context=context)
            serializer.is_valid(raise_exception=True)
            values = dict(serializer.validated_data)
            count = values.pop("count")
            custom_values = custom.checked_values(  # MAT-073
                serializer, values, material_model, None, creating=True, several=count > 1
            )
            try:
                with transaction.atomic():
                    created = services.create_items(
                        material_model,
                        count,
                        inventory_number=values.pop("start_number", None),
                        serial_numbers=values.pop("serial_numbers", None),
                        price_for_set=values.pop("price_for_set", False),
                        **values,
                    )
                    custom.store_checked(created, custom_values)
            except ValidationError as error:
                # MAT-050: the start ID is called "start_number" here.
                if hasattr(error, "error_dict") and "inventory_number" in error.error_dict:
                    error.error_dict["start_number"] = error.error_dict.pop("inventory_number")
                raise
            # A serial number that exists already (or is given twice) is a warning, named at the items.
            context["item_warnings"] = serial_check.for_items(created)
            return Response(
                MaterialItemSerializer(created, many=True, context=context).data, status=status.HTTP_201_CREATED
            )
        items = material_model.items.select_related("material_model__category", "supplier").with_category_fields()
        page = self.paginate_queryset(items)
        custom.load_page(page)  # MAT-073: the values of the page at once (NFA-012)
        return self.get_paginated_response(MaterialItemSerializer(page, many=True, context=context).data)

    @extend_schema(
        request=None,
        responses={201: inline_serializer("ProductFromModel", {"id": serializers.IntegerField()})},
    )
    @action(detail=True, methods=["post"], url_path="create-product")
    def create_product(self, request: Request, pk: str | None = None) -> Response:
        """MAT-051: a product of the same name for a model without product; the model is assigned to it.

        Needs write access to products as well. The answer is the product as
        ``/products/{id}`` returns it; its price is 0 until somebody sets it.
        """
        from rentalars.products.api import ProductSerializer

        if not self.rights.can_write(Module.PRODUCTS):
            raise PermissionDenied(_("Creating products needs write access to products."))
        product = services.create_product_from_model(self.get_object(), self.rights)
        return Response(ProductSerializer(product, context=self.get_serializer_context()).data, status=201)


class MaterialItemViewSet(ModuleViewSet):
    """``/material-items`` – search and filters as in MAT-028."""

    module = Module.MATERIAL
    queryset = MaterialItem.objects.select_related(
        "material_model",
        "material_model__category",
        "material_model__default_product",
        "supplier",
        "storage_location",
        "installed_in",
    ).with_category_fields()
    serializer_class = MaterialItemSerializer
    filterset_class = MaterialItemFilter
    #: Taking an item out of its container changes the item; it deletes nothing.
    action_levels: ClassVar[dict[str, int]] = {"remove_content": Level.WRITE}
    ordering_fields = ["inventory_number", "material_model__name", "status", "purchase_date", "serial_number"]
    ordering = ["inventory_number"]

    def get_queryset(self) -> Any:
        """The items with their last audit and open to-dos, read with the list (MAT-069)."""
        return audits.with_audit_fields(super().get_queryset())

    def paginate_queryset(self, queryset: Any) -> list[Any] | None:
        """MAT-073: the custom values of a page at once, not per item (NFA-012)."""
        page = super().paginate_queryset(queryset)
        custom.load_page(page)
        return page

    @extend_schema(
        responses={200: inline_serializer("ItemHistory", {"timestamp": serializers.DateTimeField()}, many=True)}
    )
    @action(detail=True)
    def history(self, request: Request, pk: str | None = None) -> Response:
        """Status changes, field changes and project deployments of an item (MAT-025)."""
        rows = item_history(self.get_object(), self.rights)
        return Response(
            [
                {
                    "timestamp": row.timestamp,
                    "kind": row.kind,
                    "summary": row.summary,
                    "user": row.user,
                    "changes": [
                        {"field": change.name, "label": change.label, "old": change.old, "new": change.new}
                        for change in row.changes
                    ],
                    "project": row.project_id,
                }
                for row in rows
            ]
        )

    def _contents_document(self, item: MaterialItem) -> dict[str, Any]:
        """What an item sits in and what sits in it, across all levels (MAT-035)."""
        context = self.get_serializer_context()
        tree = services.content_tree(item)
        return {
            "installed_in": MaterialItemSerializer(services.container_chain(item), many=True, context=context).data,
            "contents": [
                {"depth": depth, **MaterialItemSerializer(content, context=context).data}
                for depth, content in tree.depth_first
            ],
        }

    @extend_schema(
        methods=["get"],
        responses={200: inline_serializer("ItemContents", {"depth": serializers.IntegerField()}, many=True)},
    )
    @extend_schema(
        methods=["post"],
        request=inline_serializer(
            "ItemContentAdd",
            {
                "item": serializers.IntegerField(),
                "connection_type": serializers.ChoiceField(choices=ConnectionType.choices, required=False),
                "individually_rentable": serializers.BooleanField(required=False),
            },
        ),
        responses={200: inline_serializer("ItemContentsAfterAdd", {"depth": serializers.IntegerField()}, many=True)},
    )
    @action(detail=True, methods=["get", "post"])
    def contents(self, request: Request, pk: str | None = None) -> Response:
        """``GET``: everything installed in an item (MAT-035). ``POST``: put another item into it (MAT-046).

        The body of ``POST`` names the item by its database ID:
        ``{"item": 17, "connection_type": "loose"}``. The rules are those of
        "installed in": not into itself, no circle, not into archived or bulk
        material; an item that sits in another container is not moved.
        """
        container = self.get_object()
        if request.method == "POST":
            body = body_of(request)
            item = get_object_or_404(
                MaterialItem.objects.select_related("material_model", "installed_in"), pk=body.get("item") or 0
            )
            connection_type = body.get("connection_type") or ConnectionType.FIXED
            if connection_type not in ConnectionType.values:
                raise ValidationError({"connection_type": _("Unknown kind of connection.")})
            services.add_content(
                container,
                item,
                connection_type=connection_type,
                individually_rentable=bool(body.get("individually_rentable")),
            )
        return Response(self._contents_document(container))

    @extend_schema(
        responses={200: inline_serializer("ItemContentsAfterRemove", {"depth": serializers.IntegerField()}, many=True)}
    )
    @action(detail=True, methods=["delete"], url_path=r"contents/(?P<content_pk>\d+)")
    def remove_content(self, request: Request, pk: str | None = None, content_pk: str | None = None) -> Response:
        """``DELETE …/contents/{item}``: take an item out of this one (MAT-046)."""
        container = self.get_object()
        item = get_object_or_404(MaterialItem.objects.select_related("material_model"), pk=content_pk)
        services.remove_content(container, item)
        return Response(self._contents_document(container))

    @extend_schema(parameters=[OpenApiParameter("code", str, required=True)], responses=MaterialItemSerializer)
    @action(detail=False)
    def lookup(self, request: Request) -> Response:
        """Find one item by its ID or serial number – the entry point for a later scan (MAT-027)."""
        item = services.find_item_by_code(request.query_params.get("code", ""))
        if item is None:
            return Response(
                {"error": {"code": "not_found", "message": _("No item with this ID or serial number.")}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(self.get_serializer(self.get_queryset().get(pk=item.pk)).data)

    def perform_destroy(self, instance: MaterialItem) -> None:
        """Only items without any deployment can be deleted; all others are archived (MAT-022)."""
        services.delete_item(instance)
