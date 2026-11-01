# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the webhooks (API-012): ``/webhooks`` and what belongs to them.

=============================================  ==========================================
``GET/POST /webhooks``                         list, create (answers with the secret once)
``GET/PUT/PATCH/DELETE /webhooks/{id}``        read, change, delete
``GET /webhooks/events``                       the events with description and example
``GET /webhooks/{id}/deliveries``              the deliveries, newest first
``POST /webhooks/{id}/test``                   send a ``ping`` now
``GET/POST /webhooks/{id}/secret``             show the secret, or replace it
``POST /webhooks/{id}/deliveries/{d}/redeliver``  send a failed delivery again
=============================================  ==========================================

Rights: the module "Administration" – read to see, write to change, test,
send again and see the secret, delete to delete.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Level, Module
from rentalars.api import webhooks
from rentalars.api.models import DeliveryStatus, Webhook, WebhookDelivery
from rentalars.api.views import ModuleViewSet
from rentalars.api.webhook_events import EVENTS, SUBSCRIBABLE
from rentalars.core.crypto import SecretUnreadableError


class SecretUnreadable(APIException):
    """The stored secret was encrypted with another key of the installation."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "secret_unreadable"
    default_detail = "The secret cannot be read."


class WebhookSerializer(serializers.ModelSerializer):
    """A webhook (API-012). The secret is never part of it; see ``/webhooks/{id}/secret``."""

    events = serializers.ListField(
        child=serializers.ChoiceField(choices=SUBSCRIBABLE),
        allow_empty=False,
        help_text="The events the webhook is told about; see /webhooks/events.",
    )

    class Meta:
        model = Webhook
        fields = [
            "id",
            "url",
            "description",
            "events",
            "is_active",
            "created_by",
            "created_at",
            "secret_created_at",
            "failures_in_a_row",
            "switched_off_at",
        ]
        read_only_fields = ["created_by", "created_at", "secret_created_at", "failures_in_a_row", "switched_off_at"]

    def create(self, validated_data: dict[str, Any]) -> Webhook:
        """Create with a new secret (see :meth:`WebhookViewSet.create` for the answer that shows it)."""
        request = self.context.get("request")
        webhook, _secret = webhooks.create_webhook(user=getattr(request, "user", None), **validated_data)
        return webhook

    def update(self, instance: Webhook, validated_data: dict[str, Any]) -> Webhook:
        """Change; switched on again, the webhook starts afresh."""
        return webhooks.update_webhook(instance, **validated_data)


class NewWebhookSerializer(WebhookSerializer):
    """A webhook just created, with its secret – shown this once; later only through ``/secret``."""

    secret = serializers.CharField(read_only=True)

    class Meta(WebhookSerializer.Meta):
        fields = [*WebhookSerializer.Meta.fields, "secret"]


class WebhookDeliverySerializer(serializers.ModelSerializer):
    """One delivery of an event to a webhook with the outcome of its last attempt (API-012).

    ``payload`` is exactly what is sent; ``delivery_id`` is its ``id`` and the
    header ``X-Rentalars-Delivery``.
    """

    delivery_id = serializers.UUIDField(source="uuid", read_only=True)
    payload = serializers.JSONField(source="envelope", read_only=True)

    class Meta:
        model = WebhookDelivery
        fields = [
            "id",
            "delivery_id",
            "event",
            "status",
            "attempts",
            "created_at",
            "next_attempt_at",
            "last_attempt_at",
            "last_status_code",
            "last_error",
            "last_response",
            "last_duration_ms",
            "delivered_at",
            "payload",
        ]
        read_only_fields = fields


#: The secret of a webhook, the key of its signature.
SECRET_SCHEMA = inline_serializer("WebhookSecret", {"secret": serializers.CharField()})

#: The events a webhook can be told about.
EVENTS_SCHEMA = inline_serializer(
    "WebhookEvent",
    {
        "event": serializers.CharField(),
        "label": serializers.CharField(),
        "description": serializers.CharField(),
        "example": serializers.JSONField(help_text="An example of the field “data” of this event."),
    },
    many=True,
)


class WebhookViewSet(ModuleViewSet):
    """``/webhooks`` – addresses of other systems that are told about events (API-012).

    Every event is sent by ``POST`` as JSON: ``{"version": 1, "id", "event",
    "timestamp", "data"}``. The headers ``X-Rentalars-Event`` and
    ``X-Rentalars-Delivery`` repeat event and ID; ``X-Rentalars-Signature:
    sha256=<hex>`` is the HMAC-SHA256 of the raw body with the webhook's
    secret. Any 2xx answer counts as delivered; otherwise the delivery is
    tried again after 1 min, 5 min, 30 min, 2 h and 12 h. Redirections are
    not followed. After 10 deliveries in a row that failed for good, the
    webhook is switched off and the administrators are told.

    ``GET /webhooks/events`` lists the events with an example of their
    ``data``. Events carry no prices and personal data only where they are
    about a person; more comes from the API address in ``api_url``.
    """

    module = Module.ADMINISTRATION
    schema_tag = "webhooks"
    serializer_class = WebhookSerializer
    queryset = Webhook.objects.all()
    #: Seeing the secret is as much as changing the webhook.
    action_levels: ClassVar[dict[str, int]] = {"secret": Level.WRITE}

    @extend_schema(responses={201: NewWebhookSerializer})
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Create a webhook. The answer carries its secret, this one time."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        webhook, secret = webhooks.create_webhook(user=request.user, **serializer.validated_data)
        data = dict(self.get_serializer(webhook).data)
        data["secret"] = secret
        return Response(data, status=status.HTTP_201_CREATED)

    @extend_schema(responses=EVENTS_SCHEMA)
    @action(detail=False, pagination_class=None, filter_backends=[])
    def events(self, request: Request) -> Response:
        """The events a webhook can be told about, each with an example of its ``data``."""
        return Response(
            [
                {
                    "event": event.name,
                    "label": str(event.label),
                    "description": event.description,
                    "example": event.example,
                }
                for event in EVENTS.values()
            ]
        )

    @extend_schema(
        parameters=[
            OpenApiParameter("status", str, enum=DeliveryStatus.values, description="Only deliveries in this state."),
            OpenApiParameter("event", str, description="Only deliveries of this event."),
        ],
        responses=WebhookDeliverySerializer(many=True),
    )
    @action(detail=True, filter_backends=[])
    def deliveries(self, request: Request, pk: str | None = None) -> Response:
        """The deliveries of a webhook, newest first; kept for 30 days."""
        deliveries = self.get_object().deliveries.all()
        if request.query_params.get("status") in DeliveryStatus.values:
            deliveries = deliveries.filter(status=request.query_params["status"])
        if request.query_params.get("event"):
            deliveries = deliveries.filter(event=request.query_params["event"])
        page = self.paginate_queryset(deliveries)
        return self.get_paginated_response(WebhookDeliverySerializer(page, many=True).data)

    @extend_schema(request=None, responses={201: WebhookDeliverySerializer})
    @action(detail=True, methods=["post"])
    def test(self, request: Request, pk: str | None = None) -> Response:
        """Send a ``ping`` now; the answer tells how the receiver answered (``status`` ``delivered`` or ``failed``)."""
        delivery = webhooks.send_test(self.get_object())
        return Response(WebhookDeliverySerializer(delivery).data, status=status.HTTP_201_CREATED)

    @extend_schema(methods=["get"], responses=SECRET_SCHEMA)
    @extend_schema(methods=["post"], request=None, responses=SECRET_SCHEMA)
    @action(detail=True, methods=["get", "post"])
    def secret(self, request: Request, pk: str | None = None) -> Response:
        """``GET`` shows the secret; ``POST`` replaces it by a new one, which is valid at once.

        Needs write access to the administration. A receiver that still
        checks the old secret refuses the deliveries until it gets the new one.
        """
        webhook = self.get_object()
        if request.method == "POST":
            return Response({"secret": webhooks.renew_secret(webhook)})
        try:
            return Response({"secret": webhooks.secret_of(webhook)})
        except SecretUnreadableError as error:
            raise SecretUnreadable(
                _("The secret cannot be read any more (was the key of the installation changed?). Create a new one.")
            ) from error

    @extend_schema(
        parameters=[OpenApiParameter("delivery_pk", int, OpenApiParameter.PATH, description="ID of the delivery.")],
        request=None,
        responses=WebhookDeliverySerializer,
    )
    @action(
        detail=True,
        methods=["post"],
        url_path=r"deliveries/(?P<delivery_pk>[0-9]+)/redeliver",
        url_name="redeliver",
    )
    def redeliver(self, request: Request, pk: str | None = None, delivery_pk: str | None = None) -> Response:
        """Send a failed delivery again, now, with the same delivery ID; the answer tells the outcome."""
        delivery = get_object_or_404(self.get_object().deliveries, pk=delivery_pk)
        webhooks.redeliver(delivery)
        return Response(WebhookDeliverySerializer(delivery).data)
