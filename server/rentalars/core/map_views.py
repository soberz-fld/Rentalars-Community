# SPDX-License-Identifier: GPL-3.0-or-later
"""The map of an address in the page (UIX-034).

``GET /maps/<target>/<id>/`` answers with the map as a part of a page: the
places with their route links and the data the page script draws the map
with. It is fetched by the button "Karte anzeigen" (or right away with the
setting "Karten sofort laden") – only then are missing positions asked for
(``core.maps.locate``).

``POST /maps/<target>/<id>/position/`` sets the position of one address by
hand, or forgets it so that the geocoder is asked again; the answer is the
map again.
"""

from __future__ import annotations

import json

from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from rentalars.core import maps


def _render(request: HttpRequest, page: maps.MapPage, *, errors: dict[str, str] | None = None) -> HttpResponse:
    return render(
        request,
        "core/_map.html",
        {
            "page": page,
            "prefix": f"{page.target}-{page.pk}",
            "data": json.dumps(maps.map_data(page)),
            "errors": errors or {},
            "posted_key": request.POST.get("key", "") if errors else "",
        },
    )


def _page(request: HttpRequest, target: str, pk: int) -> maps.MapPage:
    if target not in maps.TARGETS or not maps.maps_enabled():
        raise Http404
    return maps.map_for(request, target, pk)


@require_GET
def map_part(request: HttpRequest, target: str, pk: int) -> HttpResponse:
    """The map of a venue, customer, supplier, the company or a project (UIX-034, PRJ-097)."""
    page = _page(request, target, pk)
    maps.locate(page)
    return _render(request, page)


@require_POST
def map_position(request: HttpRequest, target: str, pk: int) -> HttpResponse:
    """Set the position of an address by hand – or forget it, so that it is looked up again (UIX-034)."""
    page = _page(request, target, pk)
    key = request.POST.get("key", "")
    errors: dict[str, str] = {}
    try:
        if request.POST.get("action") == "forget":
            maps.forget_position(page, key, user=request.user)
        else:
            maps.set_position(
                page, key, request.POST.get("latitude", ""), request.POST.get("longitude", ""), user=request.user
            )
    except ValidationError as error:
        if hasattr(error, "error_dict"):
            errors = {name: " ".join(messages) for name, messages in error.message_dict.items()}
        else:
            errors = {"form": " ".join(error.messages)}
    maps.locate(page)
    if not errors:
        page.problems.insert(
            0,
            _("The position was forgotten and looked up again.")
            if request.POST.get("action") == "forget"
            else _("The position was saved. It holds for every record with this address."),
        )
    return _render(request, page, errors=errors)
