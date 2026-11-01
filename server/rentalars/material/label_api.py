# SPDX-License-Identifier: GPL-3.0-or-later
"""API of Einstellungen → Etiketten (MAT-056; API-002).

* ``GET/PATCH /label-settings`` – the names, phone, web address, texts, the
  target of the QR code, the label suggested and the length of the cable
  label; ``printed`` shows what is printed where a field is empty (the
  company's data). The logo is uploaded in the browser, as the company's
  logo (ADM-001); ``has_logo`` says whether there is one.

Reading needs the module "administration", changing write access to it – as
on the page.
"""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Module
from rentalars.api.serializers import CleanModelSerializer
from rentalars.api.views import ModuleAPIView, body_of
from rentalars.material.label_settings import LabelSettings


class LabelSettingsSerializer(CleanModelSerializer):
    """What the three labels show."""

    has_logo = serializers.SerializerMethodField()
    printed = serializers.SerializerMethodField()

    class Meta:
        model = LabelSettings
        fields = [
            "company_name",
            "cable_name",
            "phone_caption",
            "phone",
            "id_caption",
            "url",
            "wrap_text",
            "notice",
            "qr_target",
            "default_kind",
            "cable_length_mm",
            "has_logo",
            "printed",
        ]

    def get_has_logo(self, row: LabelSettings) -> bool:
        """Whether a logo for labels was uploaded."""
        return bool(row.logo)

    def get_printed(self, row: LabelSettings) -> dict[str, str]:
        """What is printed – the company's data where a field is empty – and the QR code of item 0042."""
        return {
            "name": row.printed_name,
            "cable_name": row.printed_cable_name,
            "phone": row.printed_phone,
            "url": row.printed_url,
            "wrap_text": row.printed_wrap_text,
            "qr_example": row.qr_content("0042"),
        }


class LabelSettingsView(ModuleAPIView):
    """``GET/PATCH /label-settings`` – MAT-056."""

    module = Module.ADMINISTRATION
    schema_tag = "settings"

    @extend_schema(responses=LabelSettingsSerializer)
    def get(self, request: Request) -> Response:
        """The settings of the labels."""
        return Response(LabelSettingsSerializer(LabelSettings.load()).data)

    @extend_schema(request=LabelSettingsSerializer, responses=LabelSettingsSerializer)
    def patch(self, request: Request) -> Response:
        """Change the fields sent; ``qr_target`` needs ``{id}`` and http(s)."""
        serializer = LabelSettingsSerializer(LabelSettings.load(), data=body_of(request), partial=True)
        serializer.is_valid(raise_exception=True)
        row: Any = serializer.save()
        return Response(LabelSettingsSerializer(row).data)
