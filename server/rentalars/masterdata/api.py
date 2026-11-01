# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the master data: categories, units, tax rates, suppliers, rental scales (chapter 8).

Every logged-in user may read master data, because all forms need it.
Changing it requires the Administration module; manufacturers and suppliers
may also be maintained with write access to Material.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Module, SpecialRight
from rentalars.api.permissions import WritableCaller
from rentalars.api.serializers import CleanModelSerializer, RestrictedFieldsMixin
from rentalars.api.views import ModuleViewSet
from rentalars.masterdata.models import (
    Category,
    CategoryField,
    Manufacturer,
    RentalScale,
    RentalScaleRow,
    RentalScaleVersion,
    StorageLocation,
    Supplier,
    TaxAccount,
    TaxRate,
    Unit,
    remember_location_paths,
)


class UnitSerializer(CleanModelSerializer):
    """A unit of measure."""

    class Meta:
        model = Unit
        fields = ["id", "name", "abbreviation", "is_active"]


class TaxRateSerializer(CleanModelSerializer):
    """A tax rate (PRD-016)."""

    class Meta:
        model = TaxRate
        fields = ["id", "name", "rate", "valid_from", "is_default", "is_active"]


class TaxAccountSerializer(CleanModelSerializer):
    """A tax account, e.g. 3400 "Wareneingang 19 % Vorsteuer"."""

    class Meta:
        model = TaxAccount
        fields = ["id", "number", "name", "is_active"]


class ManufacturerSerializer(CleanModelSerializer):
    """A manufacturer (MAT-015)."""

    class Meta:
        model = Manufacturer
        fields = ["id", "name", "is_active"]


class SupplierSerializer(RestrictedFieldsMixin, CleanModelSerializer):
    """A supplier (MAT-019); PRJ-106: ``contact`` is the contact person, e-mail address and phone have fields.

    DOK-052: ``tax_office`` decides how the EÜR counts the payments to the supplier, so it is shown and set only to
    callers who may see the EÜR (``outgoing.may_see_euer``) – whoever may maintain suppliers with write access to Material
    must not be able to change the profit of a year.

    UIX-033, PRJ-097: its address, and ``route_url`` – the route in Google Maps from the
    viewer's current location.
    """

    route_url = serializers.SerializerMethodField()

    def _hidden_fields(self) -> set[str]:
        """``tax_office`` unless the caller may see the EÜR."""
        from rentalars.documents import outgoing

        hidden = super()._hidden_fields()
        if self.context.get("request") is not None and not outgoing.may_see_euer(self.rights):
            hidden.add("tax_office")
        return hidden

    class Meta:
        model = Supplier
        fields = [
            "id",
            "name",
            "contact",
            "email",
            "phone",
            "customer_number",
            "street",
            "postal_code",
            "city",
            "country",
            "route_url",
            "note",
            "tax_office",
            "is_active",
        ]

    def get_route_url(self, supplier: Supplier) -> str:
        """The link into the route planning of Google Maps, from the viewer's location; empty without an address."""
        from rentalars.core.maps import route_url

        return route_url(supplier.address_one_line)


class StorageLocationSerializer(CleanModelSerializer):
    """A storage location (MAT-018); ``is_default`` marks the one new items get (MAT-052)."""

    path = serializers.CharField(read_only=True)

    class Meta:
        model = StorageLocation
        fields = ["id", "name", "parent", "path", "is_active", "is_default"]


class CategoryFieldSerializer(CleanModelSerializer):
    """A category-specific field (MAT-009, MAT-010)."""

    class Meta:
        model = CategoryField
        fields = ["id", "category", "label", "field_type", "unit", "choices", "position"]


class CategorySerializer(CleanModelSerializer):
    """A category with its code and category-specific fields (PRD-009).

    ``is_customer_material`` marks a main category whose products belong to a customer (PRD-043).
    """

    path = serializers.CharField(read_only=True)
    effective_code = serializers.CharField(read_only=True)
    specific_fields = CategoryFieldSerializer(source="fields", many=True, read_only=True)

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "parent",
            "path",
            "code",
            "effective_code",
            "has_own_stock",
            "is_customer_material",
            "is_active",
            "buffer_before_hours",
            "buffer_after_hours",
            "default_product_kind",
            "default_unit",
            "default_tax_rate",
            "default_billing_mode",
            "rental_scale",
            "specific_fields",
        ]


class RentalScaleRowSerializer(serializers.ModelSerializer):
    """One row of a rental scale: days and factor."""

    class Meta:
        model = RentalScaleRow
        fields = ["days", "factor"]


class RentalScaleVersionSerializer(serializers.ModelSerializer):
    """One state of a rental scale table (PRD-037)."""

    rows = RentalScaleRowSerializer(many=True, read_only=True)

    class Meta:
        model = RentalScaleVersion
        fields = ["id", "number", "extra_day_increment", "created_at", "rows"]


class RentalScaleSerializer(CleanModelSerializer):
    """A rental scale with its current table (PRD-015)."""

    current_version = RentalScaleVersionSerializer(read_only=True)

    class Meta:
        model = RentalScale
        fields = ["id", "name", "is_default", "is_active", "current_version"]


class PublishScaleSerializer(serializers.Serializer):
    """Input for a new state of a rental scale table."""

    rows = RentalScaleRowSerializer(many=True)
    extra_day_increment = serializers.DecimalField(max_digits=7, decimal_places=3, min_value=Decimal("0"))


class MasterDataViewSet(ModuleViewSet):
    """Base for master data: everyone reads, administrators write."""

    module = Module.ADMINISTRATION
    read_for_all = True
    schema_tag = "masterdata"
    search_fields = ["name"]
    ordering_fields = ["name"]


class UnitViewSet(MasterDataViewSet):
    """``/units`` – units of measure."""

    queryset = Unit.objects.all()
    serializer_class = UnitSerializer
    filterset_fields = ["is_active"]


class TaxRateViewSet(MasterDataViewSet):
    """``/tax-rates`` – tax rates (PRD-016)."""

    queryset = TaxRate.objects.all()
    serializer_class = TaxRateSerializer
    filterset_fields = ["is_active"]


class TaxAccountViewSet(MasterDataViewSet):
    """``/tax-accounts`` – the tax accounts (Steuerkonten) of the chart of accounts, SKR 03 to begin with."""

    queryset = TaxAccount.objects.all()
    serializer_class = TaxAccountSerializer
    filterset_fields = ["is_active"]
    search_fields = ["number", "name"]
    ordering_fields = ["number", "name"]


class ManufacturerViewSet(MasterDataViewSet):
    """``/manufacturers`` – manufacturers of material (MAT-015)."""

    queryset = Manufacturer.objects.all()
    serializer_class = ManufacturerSerializer
    filterset_fields = ["is_active"]
    alternative_modules = (Module.MATERIAL,)


class SupplierViewSet(MasterDataViewSet):
    """``/suppliers`` – where material is bought and subrented (MAT-019)."""

    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    filterset_fields = ["is_active"]
    alternative_modules = (Module.MATERIAL,)


class StorageLocationViewSet(MasterDataViewSet):
    """``/storage-locations`` – storage locations as a tree (MAT-018)."""

    queryset = StorageLocation.objects.select_related("parent")
    serializer_class = StorageLocationSerializer
    filterset_fields = ["is_active", "parent"]

    def paginate_queryset(self, queryset: Any) -> list[Any] | None:
        """The paths of a page from one query, not one per location and level (NFA-012)."""
        page = super().paginate_queryset(queryset)
        if page is not None:
            remember_location_paths(page)
        return page


class CategoryViewSet(MasterDataViewSet):
    """``/categories`` – one classification for material and products (PRD-009)."""

    queryset = Category.objects.select_related("parent").prefetch_related("fields")
    serializer_class = CategorySerializer
    filterset_fields = ["is_active", "parent", "code", "has_own_stock", "is_customer_material"]
    search_fields = ["name", "code"]


class CategoryFieldViewSet(MasterDataViewSet):
    """``/category-fields`` – the category-specific fields (MAT-009)."""

    queryset = CategoryField.objects.select_related("category")
    serializer_class = CategoryFieldSerializer
    filterset_fields = ["category"]
    search_fields = ["label"]
    ordering_fields = ["position"]


class RentalScaleViewSet(MasterDataViewSet):
    """``/rental-scales`` – tables of rental days and factors (PRD-015).

    The table itself is changed with ``POST /rental-scales/{id}/publish``,
    which creates a new version (PRD-037) and needs the special right "edit
    rental scales".
    """

    queryset = RentalScale.objects.all()
    serializer_class = RentalScaleSerializer
    filterset_fields = ["is_active", "is_default"]

    @extend_schema(request=PublishScaleSerializer, responses=RentalScaleSerializer)
    @action(detail=True, methods=["post"])
    def publish(self, request: Request, pk: str | None = None) -> Response:
        """Store a new state of the table; existing project lines keep the old one."""
        if not self.rights.has(SpecialRight.EDIT_RENTAL_SCALES):
            raise PermissionDenied
        scale = self.get_object()
        serializer = PublishScaleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rows = [(row["days"], row["factor"]) for row in serializer.validated_data["rows"]]
        scale.publish(
            rows, extra_day_increment=serializer.validated_data["extra_day_increment"], created_by=request.user
        )
        return Response(RentalScaleSerializer(scale).data, status=status.HTTP_200_OK)

    def get_permissions(self) -> list[Any]:
        """Publishing is guarded by the special right, not by the module level."""
        if getattr(self, "action", None) == "publish":
            return [IsAuthenticated(), WritableCaller()]
        return super().get_permissions()

    def perform_destroy(self, instance: RentalScale) -> None:
        """A scale that project lines calculate with stays (ADM-006)."""
        if RentalScaleVersion.objects.filter(scale=instance, material_lines__isnull=False).exists():
            raise ValidationError(_("Project lines calculate with this scale. Deactivate it instead of deleting it."))
        instance.delete()
