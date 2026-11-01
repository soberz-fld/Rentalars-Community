# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the server address and its certificate (ADM-016).

``GET /server-address``
    The current address, the names and the certificate NGINX presents, and
    the newest prepared change with its command.
``POST /server-address/changes``
    Prepare a change: host name, where the certificate comes from, for your
    own certificate the PEM texts of certificate and key. The answer carries
    the one command to run on the server (``sudo rentalars address apply …``);
    nothing changes before. Administrators with the delete right only.
``GET /server-address/changes/{token}``, ``DELETE /server-address/changes/{token}``
    One prepared change; discard it while it is open.

Like the encryption (ADM-009) the API cannot apply the change: that needs
root on the server, which the application deliberately does not have.
"""

from __future__ import annotations

from typing import Any

from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Module
from rentalars.api.views import ModuleAPIView, body_of
from rentalars.core import server_address
from rentalars.core.address_models import AddressChange, CertificateKind


class AddressChangeSerializer(serializers.Serializer):
    """A prepared change of the address, with its command and what the command will do."""

    token = serializers.CharField()
    status = serializers.CharField()
    host = serializers.CharField()
    url = serializers.CharField()
    certificate_kind = serializers.CharField()
    email = serializers.CharField()
    redirect_old = serializers.BooleanField()
    previous_url = serializers.CharField()
    certificate = serializers.JSONField(
        source="certificate_info", help_text="Names, issuer, expiry of an own certificate."
    )
    checks = serializers.JSONField(help_text='What the application could check: [{"state", "title", "detail"}].')
    command = serializers.SerializerMethodField(help_text="The command to run on the server; empty once it is done.")
    steps = serializers.SerializerMethodField()
    prepared_by = serializers.SerializerMethodField()
    prepared_at = serializers.DateTimeField()
    applied_at = serializers.DateTimeField(allow_null=True)
    applied_by = serializers.CharField()
    result_message = serializers.CharField()

    def get_command(self, change: AddressChange) -> str:
        """The command while the change is open."""
        return change.command if change.is_open else ""

    def get_steps(self, change: AddressChange) -> list[str]:
        """What the command will do, in order."""
        return server_address.steps(change) if change.is_open else []

    def get_prepared_by(self, change: AddressChange) -> str:
        """Who prepared it."""
        return str(change.prepared_by or "")


def _state_document() -> dict[str, Any]:
    current = server_address.current_state()
    change = server_address.latest()
    return {
        "url": current.url,
        "host": current.host,
        "nginx_site": current.site.found,
        "server_names": current.site.server_names,
        "certificate_kind": current.kind,
        "certificate": current.certificate,
        "note": current.note,
        "change": AddressChangeSerializer(change).data if change else None,
    }


class ServerAddressView(ModuleAPIView):
    """``GET /server-address`` – address and certificate now, and the newest prepared change (ADM-016)."""

    module = Module.ADMINISTRATION
    schema_tag = "administration"

    @extend_schema(
        responses={
            200: inline_serializer(
                "ServerAddress",
                {
                    "url": serializers.CharField(),
                    "host": serializers.CharField(),
                    "nginx_site": serializers.BooleanField(),
                    "server_names": serializers.ListField(child=serializers.CharField()),
                    "certificate_kind": serializers.CharField(),
                    "certificate": serializers.JSONField(allow_null=True),
                    "note": serializers.CharField(),
                    "change": AddressChangeSerializer(allow_null=True),
                },
            )
        }
    )
    def get(self, request: Request) -> Response:
        """The current state."""
        return Response(_state_document())


class AddressChangeListView(ModuleAPIView):
    """``POST /server-address/changes`` – prepare a change of the address (ADM-016)."""

    module = Module.ADMINISTRATION
    schema_tag = "administration"

    @extend_schema(
        request=inline_serializer(
            "AddressChangeRequest",
            {
                "host": serializers.CharField(),
                "certificate_kind": serializers.ChoiceField(choices=CertificateKind.values),
                "email": serializers.CharField(required=False, help_text="For Let's Encrypt."),
                "certificate": serializers.CharField(
                    required=False, help_text="For an own certificate: the certificate with its chain, PEM."
                ),
                "private_key": serializers.CharField(
                    required=False, help_text="For an own certificate: the private key, PEM, without password."
                ),
                "redirect_old": serializers.BooleanField(required=False, default=True),
            },
        ),
        responses={201: AddressChangeSerializer},
    )
    def post(self, request: Request) -> Response:
        """Check and store the change; the answer names the command."""
        if not self.rights.can_delete(Module.ADMINISTRATION):
            raise PermissionDenied
        body = body_of(request)
        redirect_old = body.get("redirect_old", True)
        try:
            change = server_address.prepare(
                request.user,
                host=str(body.get("host") or ""),
                kind=str(body.get("certificate_kind") or ""),
                email=str(body.get("email") or ""),
                redirect_old=redirect_old not in (False, "false", "0", 0),
                certificate=str(body.get("certificate") or "").encode("utf-8"),
                private_key=str(body.get("private_key") or "").encode("utf-8"),
            )
        except server_address.AddressError as error:
            raise ValidationError(error.errors) from error
        return Response(AddressChangeSerializer(change).data, status=status.HTTP_201_CREATED)


class AddressChangeDetailView(ModuleAPIView):
    """``/server-address/changes/{token}`` – one prepared change; ``DELETE`` discards it (ADM-016)."""

    module = Module.ADMINISTRATION
    schema_tag = "administration"

    @extend_schema(responses=AddressChangeSerializer)
    def get(self, request: Request, token: str) -> Response:
        """The change."""
        return Response(AddressChangeSerializer(get_object_or_404(AddressChange, token=token)).data)

    @extend_schema(responses={204: None})
    def delete(self, request: Request, token: str) -> Response:
        """Discard an open change; its command then refuses to run."""
        change = get_object_or_404(AddressChange, token=token)
        if not change.is_open:
            raise ValidationError({"status": [_("Only a prepared change that has not been applied can be discarded.")]})
        server_address.discard(change)
        return Response(status=status.HTTP_204_NO_CONTENT)


#: Wired into ``rentalars/api/urls.py``.
urlpatterns = [
    path("server-address", ServerAddressView.as_view(), name="server-address"),
    path("server-address/changes", AddressChangeListView.as_view(), name="server-address-changes"),
    path("server-address/changes/<slug:token>", AddressChangeDetailView.as_view(), name="server-address-change-detail"),
]
