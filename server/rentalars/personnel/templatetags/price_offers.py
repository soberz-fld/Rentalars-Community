# SPDX-License-Identifier: GPL-3.0-or-later
"""Template tags of the price offers of freelancers (PER-038).

* ``{% offer_box line %}`` – in the deployment view: the freelancer's own offers for a line, and what they can do.
* ``{% offer_hint line %}`` – on the start page: the link to make an offer, or the note that a counter-offer waits.
* ``{% offer_planning line %}`` – in the planning: what the company sees of the negotiation, and its buttons
  (nothing at all for whoever lacks the right for personnel costs).
* ``{% offer_mark line %}`` – in the planning, next to the costs: the marker "price offer" of a line whose cost rate
  an accepted offer sets.
* ``{% price_offers_on %}`` – whether the feature is switched on (for the tab and the links).

Amounts are personnel costs: ``offer_planning`` and ``offer_mark`` show them only to whoever sees them (AUT-019),
``offer_box`` and ``offer_hint`` only to the person the line is for. The offers of a project are read in one query per
request, whatever the number of lines.
"""

from __future__ import annotations

from typing import Any

from django import template
from django.http import HttpRequest
from django.urls import reverse

from rentalars.accounts.rights import SpecialRight, request_rights
from rentalars.personnel import offers
from rentalars.personnel.offer_models import OfferSide, OfferStatus, PriceOffer

register = template.Library()


def _by_line(request: HttpRequest, project_id: int) -> dict[int, list[PriceOffer]]:
    """The offers of all lines of a project, by line – read once per request."""
    cache = request.__dict__.setdefault("_price_offers", {})
    if project_id not in cache:
        found: dict[int, list[PriceOffer]] = {}
        for offer in PriceOffer.objects.filter(line__project_id=project_id).order_by("round", "id"):
            found.setdefault(offer.line_id, []).append(offer)
        cache[project_id] = found
    return cache[project_id]


def _current(request: HttpRequest, line: Any) -> list[PriceOffer]:
    """The proposals of the present request of a line, oldest first."""
    if line.requested_at is None:
        return []
    return [
        offer
        for offer in _by_line(request, line.project_id).get(line.pk, [])
        if offer.requested_at == line.requested_at
    ]


def _open(rows: list[PriceOffer]) -> PriceOffer | None:
    """The proposal that waits for an answer, if it has not run out."""
    for offer in reversed(rows):
        if offer.status == OfferStatus.OPEN:
            return offer if not offer.has_run_out else None
    return None


def _applied(request: HttpRequest, line: Any) -> PriceOffer | None:
    for offer in reversed(_by_line(request, line.project_id).get(line.pk, [])):
        if offer.applied:
            return offer
    return None


@register.simple_tag
def price_offers_on() -> bool:
    """Whether freelancers may offer their own price (the company switched it on)."""
    return offers.is_enabled()


@register.inclusion_tag("personnel/_offer_box.html", takes_context=True)
def offer_box(context: dict[str, Any], line: Any) -> dict[str, Any]:
    """The own offers for a line in the deployment view and what the freelancer can do now (PER-038)."""
    from rentalars.projects.access import person_of

    request = context["request"]
    person = person_of(request.user)
    if person is None or line.person_id != person.pk:
        return {"show": False}
    rows = _current(request, line)
    settings = offers.current_settings()
    if not offers.person_may_offer(person, settings) and not rows:
        return {"show": False}
    waiting = _open(rows)
    applied = _applied(request, line)
    blocker = offers.blocker(line) if settings.enabled else "-"
    return {
        "show": bool(rows) or not blocker,
        "request": request,
        "csrf_token": context.get("csrf_token"),
        "line": line,
        "rows": rows,
        "own_offer": waiting if waiting is not None and waiting.side == OfferSide.FREELANCER else None,
        "counter": waiting if waiting is not None and waiting.side == OfferSide.COMPANY else None,
        "can_start": not blocker and waiting is None,
        "can_counter": len(rows) < settings.max_rounds,
        "applied": applied,
        "show_reference": offers.may_know_own_rates(request.user),
        "next": request.get_full_path(),
    }


@register.inclusion_tag("personnel/_offer_hint.html", takes_context=True)
def offer_hint(context: dict[str, Any], line: Any) -> dict[str, Any]:
    """On the start page, beside the answer to a request: make an offer, or a counter-offer waits (PER-038)."""
    request = context["request"]
    if not offers.is_enabled():
        return {"show": False}
    rows = _current(request, line)
    waiting = _open(rows)
    return {
        "show": True,
        "line": line,
        "can_start": offers.may_start_offer(line),
        "counter": waiting if waiting is not None and waiting.side == OfferSide.COMPANY else None,
    }


@register.inclusion_tag("personnel/_offer_planning.html", takes_context=True)
def offer_planning(context: dict[str, Any], line: Any) -> dict[str, Any]:
    """In the planning, under the request of a line: the negotiation and the buttons of the company (PER-038, AUT-019)."""
    request = context["request"]
    rows = _current(request, line)
    if not rows:
        return {"show": False}
    waiting = _open(rows)
    sees_amounts = request_rights(request).has(SpecialRight.PERSONNEL_COSTS)
    if not sees_amounts:
        # Offers are personnel costs (AUT-019): without the right nobody learns even that one exists.
        return {"show": False}
    latest = waiting or rows[-1]
    return {
        "show": True,
        "csrf_token": context.get("csrf_token"),
        "project": context.get("project"),
        "line": line,
        "rows": rows,
        "latest": latest,
        "waiting": waiting,
        "waiting_for_company": waiting is not None and waiting.side == OfferSide.FREELANCER,
        "waiting_for_freelancer": waiting is not None and waiting.side == OfferSide.COMPANY,
        "percent": offers.percent_of_reference(latest.amount, latest.reference_amount),
        "can_decide": bool(context.get("can_plan_crew")),
        "can_counter": len(rows) < offers.current_settings().max_rounds,
        "next": reverse("projects:detail", args=[line.project_id]),
    }


@register.inclusion_tag("personnel/_offer_mark.html", takes_context=True)
def offer_mark(context: dict[str, Any], line: Any) -> dict[str, Any]:
    """Next to the costs of a line: the marker when an accepted price offer sets its cost rate (PER-038)."""
    request = context["request"]
    applied = _applied(request, line)
    if applied is None:
        return {"applied": None}
    return {"applied": applied, "text": offers.offer_text(applied), "reference": applied.reference_amount}
