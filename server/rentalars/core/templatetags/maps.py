# SPDX-License-Identifier: GPL-3.0-or-later
"""Template tags for addresses: the link into Google Maps (UIX-033) and the map after a click (UIX-034).

::

    {% load maps %}
    {% route_link venue_text %}
    {% map_box "venue" venue.pk %}

``map_box`` also widens the content security policy of the page by the tile
server (``core.middleware.ContentSecurityPolicyMiddleware``): the pictures of
the map are loaded by the browser from there, and only on pages that can
show a map.
"""

from __future__ import annotations

from typing import Any

from django import template
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString, mark_safe
from django.utils.translation import gettext as _

from rentalars.core import maps
from rentalars.core.templatetags.rentalars import icon

register = template.Library()


@register.simple_tag
def route_link(destination: str, label: str = "") -> SafeString:
    """The link "Route in Google Maps" to an address, opening in a new tab (UIX-033).

    Nothing is sent before the click: it is a plain link, without referrer.
    The route starts where the viewer is.
    """
    url = maps.route_url(destination or "")
    if not url:
        return mark_safe("")
    return format_html(
        '<a class="route-link" href="{}" target="_blank" rel="noopener noreferrer">{}{}'
        '<span class="visually-hidden"> {}</span></a>',
        url,
        icon("route"),
        label or _("Route in Google Maps"),
        _("(opens Google Maps in a new tab)"),
    )


@register.filter
def address_line(record: Any) -> str:
    """Street, postal code and city, country of a record in one line – for a route link."""
    if record is None:
        return ""
    return maps.one_line(
        getattr(record, "street", ""),
        f"{getattr(record, 'postal_code', '')} {getattr(record, 'city', '')}",
        getattr(record, "country", ""),
    )


@register.simple_tag(takes_context=True)
def map_box(context: Any, target: str, pk: Any = 1) -> SafeString:
    """The place of a map: the button "Karte anzeigen", or the map itself with "Karten sofort laden" (UIX-034).

    Empty when maps are switched off in the configuration file.
    """
    if not maps.maps_enabled():
        return mark_safe("")
    request = context.get("request")
    if request is not None:
        origin = maps.tile_origin()
        if origin:
            sources = getattr(request, "csp_image_sources", set())
            sources.add(origin)
            request.csp_image_sources = sources
    return mark_safe(  # noqa: S308 - rendered by a template with autoescaping
        render_to_string(
            "core/_map_box.html",
            {
                "target": target,
                "pk": pk,
                "url": reverse("core:map", args=[target, pk]),
                "at_once": maps.load_at_once(),
            },
            request=request,
        )
    )
