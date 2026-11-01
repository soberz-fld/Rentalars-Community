# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the products module: products, kits, availability (chapter 8)."""

from __future__ import annotations

import datetime
from typing import Any

from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field, inline_serializer
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Module, SpecialRight, require
from rentalars.api.serializers import ExpandableFieldsMixin, RestrictedFieldsMixin
from rentalars.api.views import ModuleAPIView, ModuleViewSet
from rentalars.availability.engine import AvailabilityEngine, ProductAvailability
from rentalars.availability.stock import NO_STOCK, stock_of_products
from rentalars.masterdata.api import CategorySerializer
from rentalars.masterdata.models import Category
from rentalars.material.models import MaterialItem, MaterialModel
from rentalars.products import services
from rentalars.products.models import KitComponent, Product, ProductKind


class KitComponentSerializer(serializers.ModelSerializer):
    """One component of a kit (PRD-022)."""

    article_number = serializers.CharField(source="component.article_number", read_only=True)
    name = serializers.CharField(source="component.name", read_only=True)

    class Meta:
        model = KitComponent
        fields = ["component", "article_number", "name", "quantity"]


class ProductSerializer(RestrictedFieldsMixin, ExpandableFieldsMixin, serializers.ModelSerializer):
    """A product (PRD-012). Prices need the price right (AUT-019).

    ``max_discount_percent`` is the highest discount a line of the product
    gets (PRD-041): ``null`` no limit, ``0`` never discounted. It needs the
    price right as well.

    ``owner`` is the customer that customer material belongs to (PRD-043):
    required in a category marked ``is_customer_material``, empty in every
    other. Such a product has no price, sale price or surcharge; it is billed
    flat without a scale and planned only in projects of its owner.

    ``kind`` "incidental" – incidental costs such as transport
    (PRD-045). A service (``kind`` "service") belongs to exactly one job
    function, ``job_function`` (PRD-044): creating a service creates its job
    function of the same name, renaming it renames a function of the same
    name; it may have no price yet. Services are planned only through the
    crew lines, never as material lines. ``hours_limit`` and
    ``price_above_limit`` (PER-035, price right): from this many hours of
    one day on, an hour of the service costs the higher price.

    ``time_surcharges`` (PER-009, price right) – off: the crew
    lines of this service get no surcharges for night, Sunday and holidays.
    It is ``null`` for every product that is not a service: only
    crew lines ever get these surcharges, so no other product has the switch;
    sent for one, it is ignored.

    ``kind`` "vehicle" – a vehicle or trailer of the fleet,
    planned under "Logistik", never as a material line (LOG-001, LOG-002);
    its items are the vehicles (``/vehicles``). ``vehicle_type`` is ``car``
    (billed per kilometre: ``price_per_km``, plus ``trailer_surcharge_per_km``
    on trips with a trailer) or ``trailer`` (billed as ``trailer_billing``
    says: ``day`` – ``price`` is the day price, with the rental scale – or
    ``km`` – ``price_per_km``). The rates need the price right; the internal
    costs ``cost_per_km`` and ``cost_per_day`` (trailers only) the right to
    see purchase prices (LOG-010). Every other kind has none of them.

    PRD-047: a product has one price. A sale
    product (``kind`` "sale") has ``sale_price`` and ``price`` null; every
    other product ``price`` and ``sale_price`` null. Sending the other one
    is refused (400). The update removed the second price of existing
    products (``products/0009_one_price_091``). Material lines that sold a
    rental product before keep their own price; a new sale of a rental
    product is refused – what is sold is a sale product.
    """

    stock = serializers.SerializerMethodField()
    stock_pieces = serializers.SerializerMethodField()
    # PER-009: the switch of a service only – null elsewhere, never a hint that other lines get surcharges.
    time_surcharges = serializers.BooleanField(
        required=False,
        allow_null=True,
        help_text=(
            "Services only: false – the crew lines of this service get no surcharges for night, Sunday and "
            "holidays. Null for every other product, whose lines never get them; sent for one, it is ignored."
        ),
    )
    components = KitComponentSerializer(many=True, read_only=True)
    job_function = serializers.SerializerMethodField()

    restricted_fields = {
        "price": SpecialRight.PRICES,
        "sale_price": SpecialRight.PRICES,
        "calculation_note": SpecialRight.PRICES,
        "surcharge_percent": SpecialRight.PRICES,
        "max_discount_percent": SpecialRight.PRICES,
        "hours_limit": SpecialRight.PRICES,
        "price_above_limit": SpecialRight.PRICES,
        "time_surcharges": SpecialRight.PRICES,
        # LOG-005, LOG-010: the rates of a vehicle; its internal costs with the purchase prices.
        "price_per_km": SpecialRight.PRICES,
        "trailer_surcharge_per_km": SpecialRight.PRICES,
        "cost_per_km": SpecialRight.PURCHASE_PRICES,
        "cost_per_day": SpecialRight.PURCHASE_PRICES,
    }
    expandable_fields = {"category": CategorySerializer}

    class Meta:
        model = Product
        fields = [
            "id",
            "article_number",
            "category",
            "gtin",
            "name",
            "description",
            "note",
            "unit",
            "tax_rate",
            "kind",
            "price",
            "sale_price",
            "calculation_note",
            "billing_mode",
            "rental_scale_mode",
            "rental_scale",
            "surcharge_type",
            "surcharge_percent",
            "max_discount_percent",
            "hours_limit",
            "price_above_limit",
            "time_surcharges",
            "vehicle_type",
            "price_per_km",
            "trailer_surcharge_per_km",
            "trailer_billing",
            "cost_per_km",
            "cost_per_day",
            "buffer_before_hours",
            "buffer_after_hours",
            "minimum_stock",
            "pieces_per_product",
            "is_active",
            "owner",
            "job_function",
            "stock",
            "stock_pieces",
            "components",
        ]
        # The model's own checks give better messages than the generic
        # "already exists" of the framework, so its validators are not used.
        extra_kwargs = {"article_number": {"validators": []}}

    def get_stock(self, product: Product) -> dict[str, int]:
        """Total, operational and plannable stock, counted from the material (PRD-006)."""
        stocks = self.context.get("stocks")
        stock = (
            stocks.get(product.pk, NO_STOCK)
            if stocks is not None
            else stock_of_products([product.pk]).get(product.pk, NO_STOCK)
        )
        return {"total": stock.total, "operational": stock.operational, "plannable": stock.plannable}

    def get_stock_pieces(self, product: Product) -> dict[str, int]:
        """The stock of :meth:`get_stock` in items – the same numbers for a product of one piece.

        For a product of several pieces ("10-pack") ``stock`` counts products, rounded down: 105 cables fit for
        use are 10 there and 105 here.
        """
        stocks = self.context.get("stocks")
        stock = (
            stocks.get(product.pk, NO_STOCK)
            if stocks is not None
            else stock_of_products([product.pk]).get(product.pk, NO_STOCK)
        )
        return {
            "total": stock.total_pieces,
            "operational": stock.operational_pieces,
            "plannable": stock.plannable_pieces,
        }

    @extend_schema_field(
        inline_serializer(
            "ServiceJobFunction",
            {"id": serializers.IntegerField(), "name": serializers.CharField()},
            allow_null=True,
        )
    )
    def get_job_function(self, product: Product) -> dict[str, Any] | None:
        """PRD-044: the job function a service belongs to; ``null`` for every other product."""
        if product.kind != "service":
            return None
        function = product.service_job_function
        return {"id": function.pk, "name": function.name} if function is not None else None

    def to_representation(self, instance: Product) -> dict[str, Any]:
        """PER-009: ``time_surcharges`` only for a service, ``null`` for every other product."""
        data = super().to_representation(instance)
        if "time_surcharges" in data and instance.kind != ProductKind.SERVICE:
            data["time_surcharges"] = None
        return data

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """PER-009: ``time_surcharges`` is taken for a service only; ``null`` changes nothing."""
        attrs = super().validate(attrs)
        kind = attrs.get("kind", self.instance.kind if self.instance is not None else None)
        if attrs.get("time_surcharges") is None or kind != ProductKind.SERVICE:
            attrs.pop("time_surcharges", None)
        return attrs

    def create(self, validated_data: dict[str, Any]) -> Product:
        """Create the product with all rules of PRD-007 ff."""
        return services.save_product(Product(**validated_data), self.rights)

    def update(self, instance: Product, validated_data: dict[str, Any]) -> Product:
        """Change the product; a used article number is protected (PRD-011)."""
        for name, value in validated_data.items():
            setattr(instance, name, value)
        return services.save_product(instance, self.rights)


def parse_period(request: Request) -> tuple[datetime.datetime, datetime.datetime]:
    """Read ``from`` and ``to`` from the query string (ISO 8601 with time).

    Raises:
        ValidationError: A value is missing, malformed, or the end is not
            after the start.
    """
    values = []
    for name in ("from", "to"):
        text = request.query_params.get(name, "")
        moment = parse_datetime(text) if text else None
        if moment is None:
            raise ValidationError({name: _("Enter date and time in ISO format, e.g. 2027-03-10T08:00:00+01:00.")})
        if moment.tzinfo is None:
            raise ValidationError({name: _("The time needs a time zone, e.g. +01:00 or Z.")})
        values.append(moment)
    if values[1] <= values[0]:
        raise ValidationError({"to": _("The end must be after the start.")})
    return values[0], values[1]


def availability_document(answer: ProductAvailability) -> dict[str, Any]:
    """Turn an availability answer into the JSON of the API (VFG-003, VFG-011)."""
    return {
        "product": answer.product_id,
        "checked": answer.checked,
        "stock": answer.stock.plannable,
        "stock_total": answer.stock.total,
        # Stock, firm and free count products; one product is this many items.
        "pieces_per_product": answer.stock.pieces_per_product,
        "firm": answer.firm,
        "optional": answer.optional,
        "free": answer.free,
        "free_after_optional": answer.free_after_optional,
        "occupied_by": [
            {
                "project": demand.project_id,
                "project_number": demand.project_number,
                "project_name": demand.project_name,
                "quantity": demand.quantity,
                "from": demand.start,
                "to": demand.end if demand.end.year < 9999 else None,
                "firm": demand.firmness.name == "FIRM",
                "via": demand.via,
            }
            for demand in answer.occupiers
        ],
    }


PERIOD_PARAMETERS = [
    OpenApiParameter("from", str, required=True, description="Start, ISO 8601 with time zone"),
    OpenApiParameter("to", str, required=True, description="End, ISO 8601 with time zone"),
    OpenApiParameter("exclude_project", int, description="Ignore the reservations of this project"),
]


class ProductViewSet(ModuleViewSet):
    """``/products`` – search by article number, name, GTIN and category (PRD-025)."""

    module = Module.PRODUCTS
    queryset = Product.objects.select_related("category", "unit", "tax_rate", "job_function").prefetch_related(
        "components__component"
    )
    serializer_class = ProductSerializer
    search_fields = ["article_number", "name", "gtin", "category__name"]
    filterset_fields = ["kind", "is_active", "unit", "tax_rate", "billing_mode", "owner"]
    ordering_fields = ["article_number", "name"]

    @extend_schema(
        parameters=[
            OpenApiParameter("category", int, description="Including subcategories."),
            OpenApiParameter(
                "below_minimum", bool, description="Only products whose stock is below their minimum (PRD-020)."
            ),
        ]
    )
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """All products, with stock."""
        return super().list(request, *args, **kwargs)

    def get_queryset(self) -> Any:
        """Add the category filter, which includes subcategories, and "below the minimum stock"."""
        queryset = super().get_queryset()
        category_id = self.request.query_params.get("category")
        if category_id and category_id.isascii() and category_id.isdigit():
            queryset = queryset.filter(category_id__in=Category.objects.descendant_ids(int(category_id)))
        if self.request.query_params.get("below_minimum") in {"true", "1"}:
            from rentalars.material.services import low_stock_products

            queryset = queryset.filter(pk__in=[entry.product.pk for entry in low_stock_products()])
        return queryset

    @extend_schema(
        parameters=[OpenApiParameter("from", datetime.date), OpenApiParameter("weeks", int)],
        responses=inline_serializer("ProductTimeline", {"days": serializers.ListField(child=serializers.DateField())}),
    )
    @action(detail=True)
    def timeline(self, request: Request, pk: str | None = None) -> Response:
        """Free pieces per day, which project takes how many (VFG-019); AUT-032: needs the right to see availability."""
        from rentalars.projects.access import visible_projects
        from rentalars.schedule.services import span_from_request
        from rentalars.schedule.timelines import product_timeline, timeline_document

        require(self.rights.has(SpecialRight.AVAILABILITY))
        days, _navigation = span_from_request(request, default_weeks=4)
        visible = set(visible_projects(self.rights, request.user).values_list("pk", flat=True))
        return Response(timeline_document(product_timeline(self.get_object(), days, visible)))

    def get_serializer_context(self) -> dict[str, Any]:
        """Count the stock of all listed products with one query."""
        context = super().get_serializer_context()
        if getattr(self, "action", None) == "list":
            context["stocks"] = stock_of_products(None)
        return context

    def perform_destroy(self, instance: Product) -> None:
        """Products that are in use are deactivated, not deleted (PRD-024); a service goes with its function (PRD-044)."""
        if instance.is_used_in_projects() or instance.material_models.exists() or instance.override_items.exists():
            raise ValidationError(_("This product is in use. Deactivate it instead of deleting it."))
        function = instance.service_job_function
        if function is not None:
            raise ValidationError(
                _(
                    "This is the service product of the job function %(function)s. Delete the job function under "
                    "Personnel → Job functions; its service product goes with it."
                )
                % {"function": function.name}
            )
        instance.delete()

    @extend_schema(
        parameters=[
            OpenApiParameter("category", int, required=True),
            OpenApiParameter(
                "product",
                int,
                description=(
                    "A product moving to the category – its own article number is kept while it fits the "
                    "category, as the product form does when the category changes."
                ),
            ),
        ],
        responses={200: inline_serializer("ArticleNumberSuggestion", {"article_number": serializers.CharField()})},
    )
    @action(detail=False, url_path="suggest-article-number")
    def suggest_article_number(self, request: Request) -> Response:
        """The next free article number and the presets of a category (PRD-010, PRD-030; PRD-049)."""
        category = Category.objects.filter(pk=request.query_params.get("category") or 0).first()
        if category is None:
            raise ValidationError({"category": _("Unknown category.")})
        presets = services.presets_for_category(category)
        product_id = request.query_params.get("product", "")
        product = (
            Product.objects.filter(pk=int(product_id)).first()
            if product_id.isascii() and product_id.isdigit()
            else None
        )
        return Response(
            {
                "article_number": services.article_number_for(category, product)
                if product is not None
                else presets["article_number"],
                "kind": presets["kind"],
                "unit": presets["unit"].pk if presets["unit"] else None,
                "tax_rate": presets["tax_rate"].pk if presets["tax_rate"] else None,
                "billing_mode": presets["billing_mode"],
            }
        )

    @extend_schema(request=ProductSerializer, responses={201: ProductSerializer})
    @action(detail=True, methods=["post"])
    def duplicate(self, request: Request, pk: str | None = None) -> Response:
        """A new product made from this one – the "Duplizieren" of the product page (PRD-048).

        The copy takes over what describes the product, with the next free
        article number of its category; prices only with the price right,
        internal costs only with the right to see purchase prices. Not taken
        over: GTIN, material, "inactive". The body may set any field of a
        product, e.g. ``name`` or ``article_number``. A kit's components are
        copied when the copy is a kit too.
        """
        source = self.get_object()
        draft = Product(**services.duplicate_values(source, self.rights))
        serializer = self.get_serializer(draft, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for name, value in serializer.validated_data.items():
            setattr(draft, name, value)
        product = services.save_duplicate(draft, source, self.rights)
        return Response(self.get_serializer(product).data, status=201)

    @extend_schema(responses={200: inline_serializer("ProductMaterials", {"models": serializers.ListField()})})
    @action(detail=True)
    def materials(self, request: Request, pk: str | None = None) -> Response:
        """The material models and items assigned to a product (PRD-026)."""
        product = self.get_object()
        models = MaterialModel.objects.filter(default_product=product).select_related("manufacturer")
        items = (
            MaterialItem.objects.for_product(product.pk).select_related("material_model").order_by("inventory_number")
        )
        return Response(
            {
                "models": [
                    {"id": m.pk, "name": m.name, "manufacturer": m.manufacturer.name if m.manufacturer else None}
                    for m in models
                ],
                "items": [
                    {
                        "id": item.pk,
                        "display_id": item.display_id,
                        "material_model": item.material_model_id,
                        "status": item.status,
                        "quantity": item.quantity,
                        "installed_in": item.installed_in_id,
                    }
                    for item in items
                ],
            }
        )

    @extend_schema(methods=["get"], responses=KitComponentSerializer(many=True))
    @extend_schema(
        methods=["put"], request=KitComponentSerializer(many=True), responses=KitComponentSerializer(many=True)
    )
    @action(detail=True, methods=["get", "put"])
    def components(self, request: Request, pk: str | None = None) -> Response:
        """Read or replace the components of a kit (PRD-022)."""
        kit = self.get_object()
        if request.method == "PUT":
            serializer = KitComponentSerializer(data=request.data, many=True)
            serializer.is_valid(raise_exception=True)
            services.set_kit_components(kit, [(row["component"], row["quantity"]) for row in serializer.validated_data])
        return Response(KitComponentSerializer(kit.components.select_related("component"), many=True).data)

    @extend_schema(
        parameters=PERIOD_PARAMETERS,
        responses={200: inline_serializer("Availability", {"free": serializers.IntegerField()})},
    )
    @action(detail=True)
    def availability(self, request: Request, pk: str | None = None) -> Response:
        """Stock, reservations and reserving projects of one product in a period (VFG-011).

        AUT-032: 403 without the special right to see the availability of material.
        """
        require(self.rights.has(SpecialRight.AVAILABILITY))
        product = self.get_object()
        start, end = parse_period(request)
        exclude = request.query_params.get("exclude_project")
        answer = AvailabilityEngine().availability(
            [product.pk],
            start,
            end,
            exclude_project_id=int(exclude) if exclude and exclude.isascii() and exclude.isdigit() else None,
        )[product.pk]
        return Response(availability_document(answer))


class AvailabilityView(ModuleAPIView):
    """``GET /availability?from=&to=&products=1,2,3`` – one query for several products (API-009)."""

    module = Module.PRODUCTS
    alternative_modules = (Module.PROJECTS,)
    schema_tag = "availability"

    @extend_schema(
        parameters=[
            *PERIOD_PARAMETERS,
            OpenApiParameter("products", str, required=True, description="Comma-separated product IDs"),
        ],
        responses={200: inline_serializer("AvailabilityList", {"free": serializers.IntegerField()}, many=True)},
    )
    def get(self, request: Request) -> Response:
        """Answer "what is free?" for the given products and period (VFG-001).

        AUT-032: 403 without the special right to see the availability of material.
        """
        require(self.rights.has(SpecialRight.AVAILABILITY))
        start, end = parse_period(request)
        raw_ids = [part.strip() for part in request.query_params.get("products", "").split(",") if part.strip()]
        if not raw_ids or not all(part.isascii() and part.isdigit() for part in raw_ids):
            raise ValidationError({"products": _("Enter the product IDs separated by commas.")})
        product_ids = list(Product.objects.filter(pk__in=[int(part) for part in raw_ids]).values_list("pk", flat=True))
        exclude = request.query_params.get("exclude_project")
        answers = AvailabilityEngine().availability(
            product_ids,
            start,
            end,
            exclude_project_id=int(exclude) if exclude and exclude.isascii() and exclude.isdigit() else None,
        )
        return Response([availability_document(answers[product_id]) for product_id in product_ids])
