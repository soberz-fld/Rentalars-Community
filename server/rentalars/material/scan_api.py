# SPDX-License-Identifier: GPL-3.0-or-later
"""API: what a scanned or typed code stands for (MAT-027, UIX-006; PCK-010, PCK-011).

``GET /scan/resolve?code=0042`` – the same answer the pages' scan widget gets (API-002): ``kind`` (``item``,
``product``, ``spot``, ``location``, ``none``), the names, the address of the page and, for an item, its status and
whether it holds other items (``is_case``). A hand scanner or a program that reads labels uses this to turn the text
of a code into a record. A code that leads to something the caller may not read is answered like an unknown one.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Module
from rentalars.api.views import ModuleAPIView
from rentalars.material import scan


class ScanResolveView(ModuleAPIView):
    """``/scan/resolve``: the item, product, storage spot or location a code stands for."""

    module = Module.MATERIAL
    alternative_modules = (Module.PRODUCTS, Module.PROJECTS, Module.PACKING)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "code", str, description="The scanned or typed text: an ID, the address of a QR code, a GTIN …"
            )
        ],
        responses={
            200: inline_serializer("ScanResult", {"kind": serializers.CharField(), "code": serializers.CharField()})
        },
    )
    def get(self, request: Request) -> Response:
        """Resolve one code."""
        result = scan.resolve(request.query_params.get("code", ""), self.rights)
        return Response(scan.result_document(result))
