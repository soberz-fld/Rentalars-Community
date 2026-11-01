# SPDX-License-Identifier: GPL-3.0-or-later
"""The browser address that tells what a scanned code stands for (MAT-027, UIX-006; PCK-010, PCK-011).

``GET /material/scan/?code=…`` answers with JSON (:func:`rentalars.material.scan.result_document`). The widget
``static/js/scan.js`` asks it after the camera read a code or a code was typed; the API has the same answer under
``/api/v1/scan/resolve`` (API-002). Only the decoded text is sent – never a picture.
"""

from __future__ import annotations

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

from rentalars.accounts.rights import Module, request_rights, require
from rentalars.material import scan


def may_scan(rights: object) -> bool:
    """Whether the reader may read anything a code can lead to: material, products, projects or the packing."""
    return any(
        rights.can_read(module)  # type: ignore[attr-defined]
        for module in (Module.MATERIAL, Module.PRODUCTS, Module.PROJECTS, Module.PACKING)
    )


@require_GET
def scan_resolve(request: HttpRequest) -> JsonResponse:
    """What a code stands for, as far as the reader may see it."""
    rights = request_rights(request)
    require(may_scan(rights))
    result = scan.resolve(request.GET.get("code", ""), rights)
    return JsonResponse(scan.result_document(result))
