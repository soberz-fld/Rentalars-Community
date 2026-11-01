# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views of the calendar links of products, models and items (VFG-040).

Two views:

* ``POST /schedule/calendar-links/<kind>/<id>/`` – "Kalender-Link erstellen",
  "Neuen Link erstellen" and "Link deaktivieren" in the box on the page of the
  record (``templates/schedule/_calendar_link.html``); back to that page;
* ``GET /calendar-feed/<kind>/<id>/<token>.ics`` – the calendar itself, for
  calendar programs, without login: the token is the key. Answered like the
  subscription link of a person's deployments (PER-023): guessing is slowed
  down per client address, a link read far more often than calendar programs do
  waits, an unchanged calendar is "304 not modified".
"""

from __future__ import annotations

from django.contrib import messages
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST, require_safe

from rentalars.accounts.rights import request_rights, require
from rentalars.personnel.calendar_views import (
    FEED_READINGS_PER_LINK,
    FEED_WINDOW_SECONDS,
    count_feed_failure,
    feed_failures_key,
    feed_refused,
)
from rentalars.schedule import calendar_links
from rentalars.schedule.calendar_links import ITEM, MODEL, PRODUCT

#: The page of a record of each kind, where the box of its calendar link is.
_PAGES = {PRODUCT: "products:detail", MODEL: "material:model_detail", ITEM: "material:item_detail"}


@require_POST
def calendar_link_change(request: HttpRequest, kind: str, pk: int) -> HttpResponse:
    """Create, renew or deactivate the calendar link of a record (``action``: ``create``, ``renew``, ``deactivate``).

    Needs write access to the module of the record, and what seeing the
    calendar needs (``calendar_links.may_manage``).
    """
    if kind not in calendar_links.KINDS:
        raise Http404
    require(calendar_links.may_manage(request_rights(request), kind))
    subject = calendar_links.subject_for(kind, pk)
    action = request.POST.get("action")
    if action == "deactivate":
        if calendar_links.deactivate_link(subject):
            messages.success(request, _("The calendar link is deactivated; its address no longer works."))
    elif action != "renew" and calendar_links.link_of(subject) is not None:
        # "Create" sent twice, or from a page shown before someone else created one: the address stays.
        messages.info(request, _("A calendar link is already active; “Create a new link” replaces it."))
    else:
        try:
            _link, renewed = calendar_links.create_link(subject, user=request.user)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(
                request,
                _("A new calendar link was created; the old address no longer works.")
                if renewed
                else _("The calendar link was created."),
            )
    # A product is addressed by its article number (UIX-024), models and items by their key.
    return redirect(f"{reverse(_PAGES[kind], args=[subject if kind == PRODUCT else subject.pk])}#calendar-link")


# --- The calendar, without login ------------------------------------------------------------------------------


def _count(key: str) -> int:
    """Count one event in the cache for :data:`FEED_WINDOW_SECONDS`; returns the count."""
    if cache.add(key, 1, FEED_WINDOW_SECONDS):
        return 1
    try:
        return cache.incr(key)
    except ValueError:  # expired between the two calls
        cache.set(key, 1, FEED_WINDOW_SECONDS)
        return 1


def _too_many() -> HttpResponse:
    """The answer "too many requests", with the time to wait."""
    response = HttpResponse(_("Too many requests. Try again later."), status=429, content_type="text/plain")
    response["Retry-After"] = str(FEED_WINDOW_SECONDS)
    return response


@require_safe
def calendar_link_feed(request: HttpRequest, kind: str, pk: int, token: str) -> HttpResponse:
    """The calendar of a product, model or item for calendar programs, with the token instead of a login.

    Guessing is pointless (256 random bits, compared in constant time) and
    slowed down anyway: wrong links count per client address together with
    those of the personal subscription links (PER-023), and a client with too
    many waits – only that client: the address comes from NGINX as for the
    login (``calendar_views.feed_failures_key``; one counter for
    everybody). An unknown or deactivated link, and the link of a record out of
    use, is "not found".
    """
    failures_key = feed_failures_key(request)
    if feed_refused(failures_key):
        return _too_many()
    link = calendar_links.link_for_token(kind, pk, token)
    if link is None:
        count_feed_failure(failures_key)
        return HttpResponse(_("Not found."), status=404, content_type="text/plain")
    if _count(f"rentalars:calendar-link:readings:{link.pk}") > FEED_READINGS_PER_LINK:
        return _too_many()
    body, etag = calendar_links.calendar_of(link)
    if etag in request.headers.get("If-None-Match", ""):
        response = HttpResponse(status=304)
    else:
        response = HttpResponse(body, content_type="text/calendar; charset=utf-8")
        response["Content-Disposition"] = f'inline; filename="rentalars-{kind}-{pk}.ics"'
    response["ETag"] = etag
    response["Cache-Control"] = "private, max-age=900"
    response["X-Robots-Tag"] = "noindex, nofollow"
    response["Referrer-Policy"] = "no-referrer"
    return response
