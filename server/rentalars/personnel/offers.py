# SPDX-License-Identifier: GPL-3.0-or-later
"""Price offers of freelancers for a deployment request – the rules (PER-038).

Browser views and API views both call these functions (API-002).

The story
---------
A freelancer is asked for a deployment (PER-016). If the company switched the feature on
(:class:`~rentalars.personnel.offer_models.OfferSettings`), the freelancer may answer with a price of
their own instead of "accept": an amount per hour, per day or in total, with an optional message and
an optional day until which it holds (:func:`make_offer`). The company accepts it
(:func:`accept_offer`), rejects it (:func:`reject_offer`) or counters (:func:`counter_offer`); a counter
is answered the same way by the freelancer. Each proposal is one row (``PriceOffer``); a negotiation
has at most ``OfferSettings.max_rounds`` proposals. A new request (``projects.crew.request_deployment``)
starts a new negotiation.

Accepting a proposal is a yes to the deployment at that price: the request is answered "accepted"
(``projects.crew.answer_deployment``, so the project's people are told as always) and the cost of
exactly this crew line follows the offer (:func:`apply_offer`):

=========  ==============================================================
per hour   ``CrewLine.hourly_rate`` = the amount (the rate from the hour limit follows it)
per day    ``CrewLine.daily_rate`` = the amount
in total   ``CrewLine.cost_flat_rate`` = the amount
=========  ==============================================================

The values the line had are kept on the offer. The price for the customer never changes. The line
carries a marker as long as the offer applies (:func:`applied_offer`); it stops applying when the
cost rate is changed by hand, the line gets another person or job function, or – for a total – new
times are asked for (:func:`after_line_update`, :func:`on_new_request`).

Rights (AUT-019)
----------------
Amounts are personnel costs. The freelancer acts on their own offers; whoever plans the crew of the
project and sees personnel costs acts for the company (:class:`Acting`). Everybody else sees nothing
of the amounts. The change log of an offer belongs to the person's history.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.core.audit import record_event
from rentalars.core.i18n import LazyCall, LocalText
from rentalars.core.money import format_money, money
from rentalars.personnel.models import EmploymentKind, Person
from rentalars.personnel.offer_models import (
    CURRENCY,
    MAX_ACTIONS_PER_HOUR,
    OfferSettings,
    OfferSide,
    OfferStatus,
    OfferUnit,
    PriceOffer,
    ReleaseReason,
)

if TYPE_CHECKING:
    from rentalars.projects.models import CrewLine

#: Events of the change log of a crew line (PER-038); the history view has their texts (``core.history``).
EVENT_APPLIED = "crew_line.offer_applied"
EVENT_RELEASED = "crew_line.offer_released"


# --- Who acts ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Acting:
    """Who answers or proposes, and for which side (PER-038, AUT-019).

    ``own``: the person of the crew line themself. ``planner``: somebody who plans the crew of the
    project *and* sees personnel costs – they act for the company, and may also enter what a freelancer
    said by phone or took back.
    """

    user: Any
    own: bool = False
    planner: bool = False

    @property
    def allowed(self) -> bool:
        """Whether this user has anything to do with the offers of the line."""
        return self.own or self.planner


def acting_for(user: Any, rights: Rights, project: Any, line: CrewLine) -> Acting:
    """Who the user is with regard to the offers of a crew line.

    ``project.access`` must have been noted (``projects.access.project_for`` does).
    """
    from rentalars.projects.access import may_plan_crew, person_of

    person = person_of(user)
    return Acting(
        user=user,
        own=person is not None and line.person_id == person.pk,
        planner=may_plan_crew(rights, project.access) and rights.has(SpecialRight.PERSONNEL_COSTS),
    )


# --- The switch and its limits --------------------------------------------------------------------------------------


def current_settings() -> OfferSettings:
    """The settings for price offers (read once per request)."""
    return OfferSettings.load()


def is_enabled() -> bool:
    """Whether freelancers may offer their own price at all (off unless the company switched it on)."""
    return current_settings().enabled


def person_may_offer(person: Person | None, offer_settings: OfferSettings | None = None) -> bool:
    """Whether an active person of a kind that may make offers: freelancers, temporary staff if the settings say so."""
    offer_settings = offer_settings or current_settings()
    if person is None or not offer_settings.enabled or not person.is_active:
        return False
    if person.kind == EmploymentKind.FREELANCER:
        return True
    return person.kind == EmploymentKind.TEMPORARY and offer_settings.also_temporary


def unit_choices(line: CrewLine) -> list[str]:
    """The units an offer for this line can be made in.

    The cost of a line billed per day is days × day rate, of any other line hours × hourly rate
    (PER-029); so those are the rates an offer can replace. A total replaces either.
    """
    from rentalars.projects.models import CrewBilling

    return [OfferUnit.DAY if line.billing == CrewBilling.DAY else OfferUnit.HOUR, OfferUnit.TOTAL]


def unit_label(unit: str) -> str:
    """``per hour``, ``per day``, ``in total`` in the active language."""
    return str(dict(OfferUnit.choices).get(unit, unit))


def reference_amount(line: CrewLine, unit: str) -> Decimal | None:
    """The rate the line has stored for the unit – what an offer is compared with; ``None`` if there is none.

    Per hour and per day: the rate fixed on the line, else the guide value of the job function – the
    rate the cost is calculated with. In total: the flat rate agreed, else what the line costs now.
    """
    from rentalars.projects import crew

    function = line.job_function
    if unit == OfferUnit.HOUR:
        found = line.hourly_rate if line.hourly_rate is not None else function.guide_cost_rate
    elif unit == OfferUnit.DAY:
        found = line.daily_rate if line.daily_rate is not None else function.guide_daily_cost_rate
    else:
        found = line.cost_flat_rate if line.cost_flat_rate is not None else crew.price_crew_line(line).cost
    return money(found) if found else None


def limits_for(
    line: CrewLine, unit: str, offer_settings: OfferSettings | None = None
) -> tuple[Decimal | None, Decimal | None]:
    """``(lowest, highest)`` an offer may name for the unit; ``None`` for no limit on that side."""
    offer_settings = offer_settings or current_settings()
    reference = reference_amount(line, unit)
    if reference is None:
        return None, None
    low = money(reference * offer_settings.min_percent / 100) if offer_settings.min_percent is not None else None
    high = money(reference * offer_settings.max_percent / 100) if offer_settings.max_percent is not None else None
    return low, high


def percent_of_reference(amount: Decimal, reference: Decimal | None) -> Decimal | None:
    """How much the amount is of the reference, in percent (``118.4``); ``None`` without reference."""
    if not reference:
        return None
    return (amount * 100 / reference).quantize(Decimal("0.1"))


def check_amount(line: CrewLine, unit: str, amount: Decimal, *, show_range: bool) -> None:
    """Refuse an amount outside the limits of the settings (they hold for both sides).

    ``show_range``: the person may name the limits – whoever sees their own rates (or the company);
    else the message does not give the stored rate away.
    """
    low, high = limits_for(line, unit)
    if (low is not None and amount < low) or (high is not None and amount > high):
        if show_range:
            lowest = format_money(low) if low is not None else "–"
            highest = format_money(high) if high is not None else "–"
            text = _("The amount must be between %(low)s and %(high)s for this deployment.") % {
                "low": lowest,
                "high": highest,
            }
        else:
            text = _("The amount is outside the range the company accepts for this deployment.")
        raise ValidationError({"amount": text})


# --- Reading the negotiation ----------------------------------------------------------------------------------------


def negotiation(line: CrewLine) -> list[PriceOffer]:
    """The proposals of the present request of the line, oldest first (a new request starts anew)."""
    if line.requested_at is None:
        return []
    return list(line.price_offers.filter(requested_at=line.requested_at).order_by("round", "id"))


def open_offer(line: CrewLine) -> PriceOffer | None:
    """The proposal that waits for an answer now (not expired), else ``None``."""
    for offer in reversed(negotiation(line)):
        if offer.status == OfferStatus.OPEN:
            return offer if not offer.has_run_out else None
    return None


def rounds_used(line: CrewLine) -> int:
    """How many proposals the present negotiation has."""
    if line.requested_at is None:
        return 0
    return line.price_offers.filter(requested_at=line.requested_at).count()


def applied_offer(line: CrewLine) -> PriceOffer | None:
    """The accepted offer that sets the cost rate of the line now, else ``None`` – the marker of the planning."""
    return line.price_offers.filter(applied=True).order_by("-id").first()


def blocker(line: CrewLine) -> str:
    """Why nobody can start an offer for this request now; empty if one can (PER-038).

    Starting is for the freelancer; the same conditions limit a counter, except the open proposal.
    """
    from rentalars.projects.models import ProjectStatus, RequestStatus

    offer_settings = current_settings()
    if line.person_id is None or not person_may_offer(line.person, offer_settings):
        return _("Price offers are not possible for this person.")
    if line.request_status != RequestStatus.REQUESTED:
        return _("A price offer is possible while the deployment request waits for an answer.")
    if line.project.status in (ProjectStatus.CANCELLED, ProjectStatus.CLOSED):
        return _("The project is closed.")
    if rounds_used(line) >= offer_settings.max_rounds:
        return _("The negotiation has reached its last round. The offer can only be accepted or rejected.")
    return ""


def may_start_offer(line: CrewLine) -> bool:
    """Whether a freelancer can make an offer for the line now: nothing in the way, and no proposal waits."""
    return not blocker(line) and open_offer(line) is None


# --- Making, answering, taking back -------------------------------------------------------------------------------


def _check_actions_per_hour(user: Any) -> None:
    """Protection against a runaway client (and a clicking frenzy): a user starts only so many proposals an hour."""
    if user is None or not getattr(user, "pk", None):
        return
    since = timezone.now() - datetime.timedelta(hours=1)
    if PriceOffer.objects.filter(author=user, created_at__gte=since).count() >= MAX_ACTIONS_PER_HOUR:
        raise ValidationError(_("Too many offers within the last hour. Please try again later."))


def _lock(line: CrewLine) -> CrewLine:
    """The line as it is in the database now, locked for the rest of the transaction (two answers at once)."""
    from rentalars.projects.models import CrewLine

    return CrewLine.objects.select_for_update().select_related("project", "person", "job_function").get(pk=line.pk)


def _new_proposal(
    line: CrewLine,
    acting: Acting,
    *,
    side: str,
    round_number: int,
    amount: Decimal,
    unit: str,
    message: str,
    valid_until: datetime.date | None,
    currency: str,
) -> PriceOffer:
    """Validate and store one proposal."""
    if unit not in unit_choices(line):
        raise ValidationError(
            {
                "unit": _("An offer for this deployment can be made per %(units)s.")
                % {"units": " / ".join(unit_label(choice) for choice in unit_choices(line))}
            }
        )
    amount = Decimal(amount)
    if not amount.is_finite():
        raise ValidationError({"amount": _("Enter a number.")})
    if amount != amount.quantize(Decimal("0.01")):
        raise ValidationError({"amount": _("The amount has at most two decimal places.")})
    show_range = side == OfferSide.COMPANY or acting.planner or may_know_own_rates(acting.user)
    offer = PriceOffer(
        line=line,
        person=line.person,
        round=round_number,
        side=side,
        author=acting.user if getattr(acting.user, "pk", None) else None,
        amount=amount,
        unit=unit,
        currency=(currency or CURRENCY).upper(),
        message=(message or "").strip(),
        valid_until=valid_until,
        reference_amount=reference_amount(line, unit),
        requested_at=line.requested_at,
    )
    offer.full_clean(exclude=["line", "person"])
    if side == OfferSide.FREELANCER:
        check_amount(line, unit, offer.amount, show_range=show_range)  # the limits bind the freelancer's side
    _check_actions_per_hour(acting.user)
    try:
        with transaction.atomic():
            offer.save()
    except IntegrityError as error:
        raise ValidationError(_("Somebody answered in the meantime. Reload the page.")) from error
    return offer


def may_know_own_rates(user: Any) -> bool:
    """Whether the user may see their own rates (the right, or the setting "people see their own rates")."""
    from rentalars.core.models import SystemSettings

    rights = getattr(user, "rights", None)
    return bool(rights and rights.has(SpecialRight.PERSONNEL_COSTS)) or SystemSettings.load().people_see_own_rates


def _decide(offer: PriceOffer, status: str, user: Any, note: str = "") -> None:
    offer.status = status
    offer.decided_at = timezone.now()
    offer.decided_by = user if getattr(user, "pk", None) else None
    offer.decision_note = note.strip()[:250]
    offer.save()


@transaction.atomic
def make_offer(
    line: CrewLine,
    *,
    acting: Acting,
    amount: Decimal,
    unit: str,
    message: str = "",
    valid_until: datetime.date | None = None,
    currency: str = CURRENCY,
) -> PriceOffer:
    """The freelancer answers the request with an offer of their own (PER-038).

    The person of the line makes it themself; a planner may enter an offer made by phone. The company
    is told.

    Raises:
        PermissionDenied: Neither the person themself nor a planner with the right for personnel costs.
        ValidationError: The feature is off, the person may not offer, the request does not wait, a proposal
            waits already, the rounds are used up, or the amount, unit, currency or day is invalid.
    """
    from rentalars.projects.services import ensure_editable

    if not acting.allowed:
        raise PermissionDenied
    line = _lock(line)
    ensure_editable(line.project)
    if reason := blocker(line):
        raise ValidationError(reason)
    if open_offer(line) is not None:
        raise ValidationError(_("An offer waits for an answer already."))
    offer = _new_proposal(
        line,
        acting,
        side=OfferSide.FREELANCER,
        round_number=rounds_used(line) + 1,
        amount=amount,
        unit=unit,
        message=message,
        valid_until=valid_until,
        currency=currency,
    )
    _tell_company(offer, acting, "offer")
    return offer


def _answerable(offer: PriceOffer, acting: Acting, *, who: str) -> CrewLine:
    """Lock the line of an open proposal and check that this user may answer it; return the line.

    ``who``: ``"other"`` – the opposite side answers (accept, reject, counter) – or ``"same"`` – the side that
    made it takes it back.
    """
    from rentalars.projects.models import RequestStatus
    from rentalars.projects.services import ensure_editable

    if not acting.allowed:
        raise PermissionDenied
    line = _lock(offer.line)
    offer.refresh_from_db()
    ensure_editable(line.project)
    if offer.status != OfferStatus.OPEN:
        raise ValidationError(_("This offer has been answered already."))
    if offer.has_run_out:
        raise ValidationError(_("This offer has run out."))
    if line.request_status != RequestStatus.REQUESTED or line.requested_at != offer.requested_at:
        raise ValidationError(_("The request has changed in the meantime; this offer no longer applies."))
    freelancers_turn = (offer.side == OfferSide.COMPANY) == (who == "other")
    # The freelancer answers a counter; the company answers an offer. A planner may stand in for the freelancer.
    if freelancers_turn:
        if not (acting.own or acting.planner):
            raise PermissionDenied
    elif not acting.planner:
        raise PermissionDenied
    offer.line = line
    return line


@transaction.atomic
def accept_offer(offer: PriceOffer, *, acting: Acting, note: str = "") -> PriceOffer:
    """Accept a proposal: the deployment is accepted at that price (PER-038).

    The cost rate of the crew line follows the offer (:func:`apply_offer`), the request is answered
    "accepted" like any acceptance, and the other side is told.
    """
    from rentalars.projects import crew

    line = _answerable(offer, acting, who="other")
    _decide(offer, OfferStatus.ACCEPTED, acting.user, note)
    # Every other proposal of the negotiation is settled by this one.
    for other in line.price_offers.filter(status=OfferStatus.OPEN).exclude(pk=offer.pk):
        _decide(other, OfferStatus.LAPSED, acting.user)
    apply_offer(offer)
    # The note of the answer is shown to everybody who sees the planning: it must not name the price.
    crew.answer_deployment(line, accept=True, note=_("Accepted after a price offer."), user=acting.user)
    _tell_answer(offer, acting, "accepted")
    return offer


@transaction.atomic
def reject_offer(offer: PriceOffer, *, acting: Acting, note: str = "") -> PriceOffer:
    """Reject a proposal; the request stays open and the freelancer can offer again while rounds are left."""
    _answerable(offer, acting, who="other")
    _decide(offer, OfferStatus.REJECTED, acting.user, note)
    _tell_answer(offer, acting, "rejected")
    return offer


@transaction.atomic
def counter_offer(
    offer: PriceOffer,
    *,
    acting: Acting,
    amount: Decimal,
    unit: str | None = None,
    message: str = "",
    valid_until: datetime.date | None = None,
    currency: str = CURRENCY,
) -> PriceOffer:
    """Answer a proposal with one of the own: the company counters an offer, the freelancer a counter (PER-038).

    Raises:
        ValidationError: The rounds are used up (only accepting or rejecting is left), or a value is invalid.
    """
    line = _answerable(offer, acting, who="other")
    if rounds_used(line) >= current_settings().max_rounds:
        raise ValidationError(
            _("The negotiation has reached its last round. The offer can only be accepted or rejected.")
        )
    _decide(offer, OfferStatus.COUNTERED, acting.user)
    side = OfferSide.COMPANY if offer.side == OfferSide.FREELANCER else OfferSide.FREELANCER
    counter = _new_proposal(
        line,
        acting,
        side=side,
        round_number=offer.round + 1,
        amount=amount,
        unit=unit or offer.unit,
        message=message,
        valid_until=valid_until,
        currency=currency,
    )
    if side == OfferSide.COMPANY:
        _tell_answer(counter, acting, "countered")
    else:
        _tell_company(counter, acting, "counter")
    return counter


@transaction.atomic
def withdraw_offer(offer: PriceOffer, *, acting: Acting) -> PriceOffer:
    """Take back a proposal that waits for an answer – the freelancer their offer, the company its counter."""
    _answerable(offer, acting, who="same")
    _decide(offer, OfferStatus.WITHDRAWN, acting.user)
    if offer.side == OfferSide.FREELANCER:
        _tell_company(offer, acting, "withdrawn")
    else:
        _tell_answer(offer, acting, "withdrawn")
    return offer


# --- What an accepted offer does to the line -----------------------------------------------------------------------


#: The fields of the line each unit replaces; the values before are kept on the offer.
_TOUCHED = {
    OfferUnit.HOUR: ("hourly_rate", "hourly_rate_above_limit", "cost_flat_rate"),
    OfferUnit.DAY: ("daily_rate", "cost_flat_rate"),
    OfferUnit.TOTAL: ("cost_flat_rate",),
}


def apply_offer(offer: PriceOffer) -> None:
    """Set the cost rate of the line from an accepted offer, keeping what it replaced (PER-038).

    An earlier offer of the line that still applies is taken back first, so that "what it was before"
    is always the rate stored for the person. The change goes through ``CrewLine.save``, so the change
    log of the line has it (the rates only for who sees personnel costs, AUT-019), next to an event
    without amounts.
    """
    line = offer.line
    for earlier in line.price_offers.filter(applied=True).exclude(pk=offer.pk):
        release_offer(earlier, reason=ReleaseReason.REVOKED, restore=True)
    for name in _TOUCHED[offer.unit]:
        setattr(offer, f"previous_{name}", getattr(line, name))
    if offer.unit == OfferUnit.HOUR:
        line.hourly_rate = offer.amount
        line.hourly_rate_above_limit = None  # the offered rate holds for every hour
        line.cost_flat_rate = None
    elif offer.unit == OfferUnit.DAY:
        line.daily_rate = offer.amount
        line.cost_flat_rate = None
    else:
        line.cost_flat_rate = offer.amount
    line.save()
    offer.applied = True
    offer.release_reason = ReleaseReason.NONE
    offer.save()
    record_event(line, EVENT_APPLIED, {"person": line.person.name, "unit": unit_label(offer.unit)})


def release_offer(offer: PriceOffer, *, reason: str, restore: bool) -> None:
    """The offer no longer sets the cost rate of its line; ``restore``: the rates before come back.

    Without ``restore`` the line keeps the rates it has (changed by hand, or re-copied for another person).
    """
    line = offer.line
    if restore:
        for name in _TOUCHED[offer.unit]:
            setattr(line, name, getattr(offer, f"previous_{name}"))
        line.save()
    offer.applied = False
    offer.release_reason = reason
    offer.save()
    record_event(
        line,
        EVENT_RELEASED,
        {"person": offer.person.name, "reason": str(dict(ReleaseReason.choices).get(reason, reason))},
    )


# --- Hooks of the crew planning (projects.crew) ---------------------------------------------------------------------


def lapse_open_offers(line: CrewLine) -> None:
    """The request was answered another way, sent again or taken back: waiting proposals are over."""
    for offer in line.price_offers.filter(status=OfferStatus.OPEN):
        _decide(offer, OfferStatus.LAPSED, None)


def on_new_request(line: CrewLine, *, times_changed: bool) -> None:
    """A new request (PER-016): proposals still waiting lapse; with new times a total offer no longer holds.

    A rate (per hour or day) stays after new times – it is the price of the person for this line; a total
    was agreed for the times as they were.
    """
    lapse_open_offers(line)
    if times_changed:
        for offer in line.price_offers.filter(applied=True, unit=OfferUnit.TOTAL):
            release_offer(offer, reason=ReleaseReason.TIMES, restore=True)


def after_line_update(line: CrewLine, *, person_or_function_changed: bool, cost_touched: bool) -> None:
    """A crew line was changed (PRJ-019): an accepted offer that no longer fits stops applying (PER-038)."""
    offer = applied_offer(line)
    if offer is None:
        return
    if person_or_function_changed or offer.person_id != line.person_id:
        release_offer(offer, reason=ReleaseReason.PERSON, restore=False)
    elif cost_touched or offer.unit not in unit_choices(line):
        release_offer(offer, reason=ReleaseReason.MANUAL, restore=False)


# --- Telling the people ----------------------------------------------------------------------------------------------


def offer_text(offer: PriceOffer) -> str:
    """``45,00 € per hour`` in the active language."""
    return f"{format_money(offer.amount)} {unit_label(offer.unit)}"


def _deployment(line: CrewLine) -> str:
    from rentalars.projects.crew import _deployment_text

    return _deployment_text(line)


def company_users(line: CrewLine, exclude: Any = None) -> list[Any]:
    """Who is told about an offer (AUT-019).

    The people who asked and run the project, and personnel planners – but only those who see personnel
    costs and the project: the amount is in the message.
    """
    from rentalars.notifications.services import personnel_planners, project_people
    from rentalars.projects.access import ProjectAccess, access_level

    candidates = [line.requested_by, *project_people(line.project), *personnel_planners()]
    chosen: list[Any] = []
    seen: set[int] = set()
    for user in candidates:
        if user is None or user.pk in seen or not user.is_active:
            continue
        seen.add(user.pk)
        if exclude is not None and user.pk == exclude.pk:
            continue
        rights = user.rights
        if rights.has(SpecialRight.PERSONNEL_COSTS) and access_level(rights, user, line.project) >= ProjectAccess.READ:
            chosen.append(user)
    return chosen


def _tell_company(offer: PriceOffer, acting: Acting, what: str) -> None:
    """The freelancer made, countered or withdrew an offer, or answered the counter: tell the company."""
    from rentalars.notifications.models import Kind
    from rentalars.notifications.services import notify

    line = offer.line
    titles = {
        "offer": gettext_lazy("Price offer from %(person)s: %(price)s – %(deployment)s"),
        "counter": gettext_lazy("Counter-offer from %(person)s: %(price)s – %(deployment)s"),
        "withdrawn": gettext_lazy("%(person)s withdrew the offer of %(price)s – %(deployment)s"),
    }
    notify(
        company_users(line, exclude=acting.user),
        Kind.PRICE_OFFER,
        LocalText(
            titles[what],
            person=line.person.name,
            price=LazyCall(offer_text, offer),
            deployment=LazyCall(_deployment, line),
        ),
        body=offer.message,
        url=reverse("projects:detail", args=[line.project_id]),
        project=line.project,
    )


def _tell_answer(offer: PriceOffer, acting: Acting, what: str) -> None:
    """The company answered the offer (or took back its counter): tell the freelancer.

    If the freelancer answered a counter-offer, the company is told instead.
    """
    from rentalars.notifications.models import Kind
    from rentalars.notifications.services import notify

    line = offer.line
    titles = {
        "accepted": gettext_lazy("Your offer of %(price)s was accepted – %(deployment)s"),
        "rejected": gettext_lazy("Your offer of %(price)s was rejected – %(deployment)s"),
        "countered": gettext_lazy("Counter-offer: %(price)s – %(deployment)s"),
        "withdrawn": gettext_lazy("The counter-offer of %(price)s was withdrawn – %(deployment)s"),
    }
    account = getattr(line.person, "user", None)
    # The answer to a counter-offer concerns the company, not the freelancer who gave it.
    if offer.side == OfferSide.COMPANY and what in ("accepted", "rejected"):
        company_titles = {
            "accepted": gettext_lazy("%(person)s accepted the counter-offer of %(price)s – %(deployment)s"),
            "rejected": gettext_lazy("%(person)s rejected the counter-offer of %(price)s – %(deployment)s"),
        }
        notify(
            company_users(line, exclude=acting.user),
            Kind.PRICE_OFFER,
            LocalText(
                company_titles[what],
                person=line.person.name,
                price=LazyCall(offer_text, offer),
                deployment=LazyCall(_deployment, line),
            ),
            body=offer.decision_note,
            url=reverse("projects:detail", args=[line.project_id]),
            project=line.project,
        )
        return
    notify(
        [account],
        Kind.PRICE_OFFER_ANSWER,
        LocalText(
            titles[what],
            price=LazyCall(offer_text, offer),
            deployment=LazyCall(_deployment, line),
        ),
        body=offer.decision_note if what == "rejected" else offer.message if what == "countered" else "",
        url=reverse("projects:deployment", args=[line.project_id]),
        project=line.project,
        exclude=acting.user,
    )
