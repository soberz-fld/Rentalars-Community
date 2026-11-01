# SPDX-License-Identifier: GPL-3.0-or-later
"""API of "Kauf einpflegen" (MAT-061, MAT-062; MAT-019, MAT-050; API-002).

* ``POST /purchases`` – enter a purchase: head (supplier, invoice number and
  date, net or gross, start ID, note) and positions (an existing model or a
  new one, number, price per piece, set, serial numbers, storage location,
  supplier's article number). All items are created in one step with
  consecutive IDs; the invoice kept by ``/purchases/invoices`` is attached
  to each of them (``invoice_upload``). Prices need the right to see
  purchase prices – without it they are refused (AUT-019).
* ``POST /purchases/invoices`` – upload an invoice (multipart, ``file``). It
  is kept for two days for the purchase (the answer's ``upload``) and read
  unless ``read`` is false: invoice number, date and a known supplier from
  the text at once (``proposal``); with AI switched on for reading invoices,
  the positions as well – then ``job`` names the task, and its proposal
  arrives in ``result.proposal`` of ``/jobs/{id}``. Nothing is created.
  MAT-076: a proposal names the totals of the invoice (``total_net``,
  ``total_gross``, ``currency``; with the right to see purchase prices) and
  per position the serial numbers, the category and the product
  (``serial_numbers``, ``category_id``/``category``, ``product_id``/
  ``product``, ``hints`` when a proposal of the AI was not taken).

For who may write material, as the page.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.core.exceptions import ValidationError
from django.urls import reverse
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Module, SpecialRight
from rentalars.api.serializers import RestrictedFieldsMixin
from rentalars.api.views import ModuleAPIView
from rentalars.masterdata.models import Category, StorageLocation
from rentalars.material import purchases, services
from rentalars.material.api import MaterialItemSerializer
from rentalars.material.forms import stock_products
from rentalars.material.models import MaterialModel


class NewModelSerializer(serializers.Serializer):
    """A model that does not exist yet: created with the items of its position (MAT-048)."""

    name = serializers.CharField(max_length=200)
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.filter(is_active=True))
    manufacturer = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    product = serializers.PrimaryKeyRelatedField(
        queryset=stock_products(), required=False, allow_null=True, default=None
    )


class PositionSerializer(RestrictedFieldsMixin, serializers.Serializer):
    """One position: ``material_model`` (an existing model) or ``new_model``, and how many of it."""

    material_model = serializers.PrimaryKeyRelatedField(
        queryset=MaterialModel.objects.all(), required=False, allow_null=True, default=None
    )
    new_model = NewModelSerializer(required=False, allow_null=True, default=None)
    count = serializers.IntegerField(min_value=1, max_value=services.MAX_ITEMS_PER_BATCH, default=1)
    unit_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        required=False,
        allow_null=True,
        default=None,
        help_text="Price of one piece, net or gross as the purchase says; with price_for_set that of all pieces.",
    )
    price_for_set = serializers.BooleanField(
        default=False, help_text="MAT-054: the price is that of all pieces together; the first item gets it."
    )
    serial_numbers = serializers.ListField(
        child=serializers.CharField(allow_blank=True, max_length=120),
        required=False,
        default=list,
        max_length=services.MAX_ITEMS_PER_BATCH,
        help_text="MAT-050: one serial number per item, in the order of the IDs.",
    )
    storage_location = serializers.PrimaryKeyRelatedField(
        queryset=StorageLocation.objects.filter(is_active=True), required=False, allow_null=True, default=None
    )
    supplier_article_number = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")

    restricted_fields = {"unit_price": SpecialRight.PURCHASE_PRICES, "price_for_set": SpecialRight.PURCHASE_PRICES}

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Either an existing model or a new one."""
        if (attrs.get("material_model") is None) == (attrs.get("new_model") is None):
            raise serializers.ValidationError({"material_model": ["Name either material_model or new_model."]})
        return attrs

    def position(self, values: dict[str, Any]) -> purchases.Position:
        """The checked values as a position of :func:`rentalars.material.purchases.create_purchase`."""
        new = values.get("new_model")
        return purchases.Position(
            model=values.get("material_model"),
            new_model=purchases.NewModel(
                name=new["name"],
                category=new["category"],
                manufacturer=new.get("manufacturer", ""),
                product=new.get("product"),
            )
            if new
            else None,
            count=values.get("count", 1),
            unit_price=values.get("unit_price"),
            price_for_set=bool(values.get("price_for_set")),
            serial_numbers=list(values.get("serial_numbers") or []),
            storage_location=values.get("storage_location"),
            supplier_article_number=values.get("supplier_article_number", ""),
        )


class PurchaseSerializer(RestrictedFieldsMixin, serializers.Serializer):
    """A purchase: the head and its positions (MAT-061)."""

    supplier = serializers.CharField(
        max_length=120,
        required=False,
        allow_blank=True,
        default="",
        help_text="The supplier's name: an existing supplier (any case) or a new one, created with the items.",
    )
    invoice_number = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    invoice_date = serializers.DateField(required=False, allow_null=True, default=None)
    prices = serializers.ChoiceField(
        choices=["net", "gross"], default="net", help_text="IMP-014: gross prices are stored net."
    )
    price_tax_rate = serializers.CharField(
        required=False, allow_blank=True, default="", help_text="The tax rate gross prices include; empty: the default."
    )
    start_number = serializers.IntegerField(min_value=1, required=False, allow_null=True, default=None)
    purchase_note = serializers.CharField(max_length=250, required=False, allow_blank=True, default="")
    invoice_upload = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="The upload of POST /purchases/invoices: attached to every item.",
    )
    positions = PositionSerializer(many=True, allow_empty=False, max_length=purchases.MAX_POSITIONS)

    restricted_fields = {"prices": SpecialRight.PURCHASE_PRICES, "price_tax_rate": SpecialRight.PURCHASE_PRICES}


class PurchaseView(ModuleAPIView):
    """``POST /purchases`` – enter a purchase: many items of several models in one step (MAT-061)."""

    module = Module.MATERIAL

    @extend_schema(
        request=PurchaseSerializer,
        responses={201: inline_serializer("PurchaseCreated", {"items": MaterialItemSerializer(many=True)})},
    )
    def post(self, request: Request) -> Response:
        """Create the items of every position, all or nothing; the answer lists them with their IDs."""
        context = {"request": request, "view": self}
        serializer = PurchaseSerializer(data=request.data, context=context)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        gross_rate = None
        if values.get("prices") == "gross":
            gross_rate = services.gross_tax_rate(values.get("price_tax_rate"))
        invoice = None
        if values.get("invoice_upload"):
            try:
                invoice = purchases.pending_invoice(values["invoice_upload"], user=request.user)
            except ValidationError as error:
                raise ValidationError({"invoice_upload": error.messages}) from error
        head = purchases.Head(
            supplier_name=values.get("supplier", ""),
            invoice_number=values.get("invoice_number", ""),
            invoice_date=values.get("invoice_date"),
            gross_rate=gross_rate,
            start_number=values.get("start_number"),
            purchase_note=values.get("purchase_note", ""),
        )
        maker = PositionSerializer(context=context)
        positions = [maker.position(position) for position in values["positions"]]
        purchase = purchases.create_purchase(head, positions, rights=self.rights, user=request.user, invoice=invoice)
        return Response(
            {
                "items": MaterialItemSerializer(purchase.items, many=True, context=context).data,
                "new_models": [model.pk for model in purchase.new_models],
                "supplier": purchase.supplier.pk if purchase.supplier is not None else None,
                "supplier_created": purchase.supplier_created,
                "invoice_attached": purchase.invoice_attached,
                "ids": purchase.id_list,
                "labels_url": f"{reverse('material:labels')}?items={purchase.id_list}",
                "warnings": purchase.warnings,
            },
            status=status.HTTP_201_CREATED,
        )


class PurchaseInvoiceView(ModuleAPIView):
    """``POST /purchases/invoices`` – keep an uploaded invoice and read it: a proposal, nothing created."""

    module = Module.MATERIAL
    parser_classes: ClassVar[list[Any]] = [MultiPartParser, FormParser]

    @extend_schema(
        request=inline_serializer(
            "PurchaseInvoiceUpload",
            {"file": serializers.FileField(), "read": serializers.BooleanField(required=False, default=True)},
        ),
        responses={201: inline_serializer("PurchaseInvoiceRead", {"upload": serializers.CharField()})},
    )
    def post(self, request: Request) -> Response:
        """Keep the invoice; read the head now, and with AI start reading the positions (``job``)."""
        uploaded = request.FILES.get("file")
        if uploaded is None:
            raise ValidationError({"file": "Choose a file."})
        invoice = purchases.keep_invoice(uploaded, user=request.user)
        answer: dict[str, Any] = {
            "upload": invoice.token,
            "name": invoice.name,
            "size": invoice.size,
            "proposal": None,
            "text_error": "",
            "job": None,
            "ai": "off",
            "ai_error": "",
        }
        if str(request.data.get("read", "true")).lower() in {"0", "false", "no", "off"}:
            return Response(answer, status=status.HTTP_201_CREATED)
        try:
            text = purchases.invoice_text(invoice.path)
        except purchases.InvoiceTextError as error:
            answer["text_error"] = str(error)
            return Response(answer, status=status.HTTP_201_CREATED)
        answer["proposal"] = purchases.proposal_from_text(text)
        if not self.rights.has(SpecialRight.PURCHASE_PRICES):
            purchases.without_prices(answer["proposal"])  # AUT-019: the totals are purchase prices (MAT-076)
        from rentalars.ai import invoices
        from rentalars.ai.client import AIError

        if invoices.is_available():
            try:
                job = invoices.start(invoice, user=request.user)
            except AIError as error:
                answer.update(ai="unavailable", ai_error=str(error))
            else:
                answer.update(ai="started", job=job.pk)
        return Response(answer, status=status.HTTP_201_CREATED)
