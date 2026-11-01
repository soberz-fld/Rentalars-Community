# SPDX-License-Identifier: GPL-3.0-or-later
"""The box "Kalender-Link" on the pages of products, material models and items (VFG-040).

::

    {% load calendar_links %}
    {% calendar_link_box product as calendar %}

used by ``templates/schedule/_calendar_link.html``, which each of the three
pages includes with ``subject=…`` – the views of the pages need not know
about calendar links. Shown to whoever may see whether a link is active
(``calendar_links.may_see``); the address and the buttons only to whoever may
change it (``calendar_links.may_manage``; a reader would keep an
address that works without login and that he cannot end).
A product without stock of its own gets no box, unless an old link is still
to be deactivated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django import template
from django.urls import reverse

from rentalars.accounts.rights import request_rights
from rentalars.schedule import calendar_links
from rentalars.schedule.models import CalendarLink

register = template.Library()


@dataclass
class CalendarLinkBox:
    """What the box shows."""

    shown: bool
    kind: str = ""
    link: CalendarLink | None = None
    #: The address for calendar programs – only for whoever may change the link (VFG-040).
    url: str = ""
    shows: str = ""
    #: Why no link can be created, e.g. for a deactivated product; empty if one can.
    unavailable: str = ""
    may_manage: bool = False
    action: str = ""


@register.simple_tag(takes_context=True)
def calendar_link_box(context: Any, subject: Any) -> CalendarLinkBox:
    """The state of the calendar link of a product, material model or item, as the reader may see it."""
    request = context.get("request")
    if request is None or subject is None:
        return CalendarLinkBox(shown=False)
    kind = calendar_links.kind_of(subject)
    rights = request_rights(request)
    if not calendar_links.may_see(rights, kind):
        return CalendarLinkBox(shown=False)
    link = calendar_links.link_of(subject)
    unavailable = calendar_links.unavailable_reason(subject)
    if link is None and kind == calendar_links.PRODUCT and not subject.tracks_stock and subject.is_active:
        return CalendarLinkBox(shown=False)
    may_manage = calendar_links.may_manage(rights, kind)
    return CalendarLinkBox(
        shown=True,
        kind=kind,
        link=link,
        # A reader learns that a link is active, not its address (VFG-040).
        url=calendar_links.feed_url(link) if link is not None and may_manage else "",
        shows=calendar_links.shows(kind),
        unavailable=unavailable,
        may_manage=may_manage,
        action=reverse("schedule:calendar_link_change", args=[kind, subject.pk]),
    )
