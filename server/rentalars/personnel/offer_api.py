# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the price offers of freelancers (PER-038; API-002).

=================================================================  ====================================================
``GET/POST /projects/{id}/crew-lines/{line}/offers``              the exchange about the price of a deployment; make an
                                                                   offer (the freelancer themself; a planner who sees
                                                                   personnel costs enters one made by phone)
``POST …/offers/{offer}/accept|reject|counter|withdraw``          answer a proposal – see below
``GET /price-offers``                                              the negotiations of all projects the caller reads,
                                                                   with the stored rate next to the offer
``GET/PATCH /settings/price-offers``                               the switch, the limits, the rounds (Einstellungen)
``GET /people/me/offers``                                          the caller's own negotiations over all deployments
=================================================================  ====================================================

Who may do what
---------------
The person planned sees and answers their own offers (``own``); whoever plans the crew of the project *and* has the
right "see hourly rates and personnel costs" acts for the company (``planner``). Everybody else gets 403 – the
amounts are personnel costs (AUT-019). A proposal of the freelancer is answered by the company (accept, reject,
counter); a counter-offer of the company by the freelancer. The stored rate (``reference_amount``,
``percent_of_reference``) is delivered to the company and to a person who may see their own rates only.

An accepted offer answers the deployment request "accepted" and sets the cost rate of exactly that crew line; the
line's ``cost`` and rates in ``/projects/{id}/crew-lines`` follow; ``applied`` on the proposal says that it sets them.
Every call changing something counts as one of the 30 offers an hour a user can make; the API as a whole is
rate-limited per token (API-011).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, ClassVar

from django.core.exceptions import PermissionDenied
from django.db.models import F
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Level, Module, SpecialRight, request_rights
from rentalars.api.permissions import AUTHENTICATED_ONLY
from rentalars.api.serializers import CleanModelSerializer
from rentalars.api.views import ModuleAPIView, body_of
from rentalars.personnel import offers
from rentalars.personnel.offer_forms import SETTING_FIELDS
from rentalars.personnel.offer_models import (
    CURRENCY,
    MAX_AMOUNT,
    OfferSettings,
    OfferStatus,
    OfferUnit,
    PriceOffer,
)
from rentalars.projects.access import (
    ProjectAccess,
    access_of_many,
    may_plan_crew,
    person_of,
    project_for,
    readable_projects,
)
from rentalars.projects.models import CrewLine

#: How many negotiations ``GET /price-offers`` delivers at most.
LIMIT = 200


def offer_document(offer: PriceOffer, *, with_reference: bool) -> dict[str, Any]:
    """One proposal as JSON.

    ``with_reference``: also the stored rate when it was made and the offer in percent of it – for the company and for
    a person who may see their own rates; else both are ``null``.
    """
    reference = offer.reference_amount if with_reference else None
    return {
        "id": offer.pk,
        "crew_line": offer.line_id,
        "person": offer.person_id,
        "round": offer.round,
        "side": offer.side,
        "amount": offer.amount,
        "unit": offer.unit,
        "currency": offer.currency,
        "message": offer.message,
        "valid_until": offer.valid_until,
        "status": offer.status,
        "expired": offer.has_run_out and offer.status == OfferStatus.OPEN,
        "decided_at": offer.decided_at,
        "decision_note": offer.decision_note,
        "reference_amount": reference,
        "percent_of_reference": offers.percent_of_reference(offer.amount, reference) if reference else None,
        "applied": offer.applied,
        "release_reason": offer.release_reason,
        "made_at": offer.created_at,
    }


class OfferInputSerializer(serializers.Serializer):
    """An offer or a counter-offer: amount, for what, message, until when."""

    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
        max_value=MAX_AMOUNT,
        help_text="In euros, without VAT: per hour, per day or in total (``unit``).",
    )
    unit = serializers.ChoiceField(
        choices=OfferUnit.choices,
        required=False,
        help_text="hour, day or total. A crew line billed per day takes day or total, any other hour or total. "
        "Required when making an offer; a counter-offer takes the unit of the proposal it answers by default.",
    )
    currency = serializers.CharField(max_length=3, required=False, default=CURRENCY, help_text="Only EUR.")
    message = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    valid_until = serializers.DateField(
        required=False, allow_null=True, default=None, help_text="Until the end of this day the offer can be accepted."
    )


class DecisionInputSerializer(serializers.Serializer):
    """A reason for rejecting, or a note to accepting."""

    note = serializers.CharField(max_length=250, required=False, allow_blank=True, default="")


class OfferSettingsSerializer(CleanModelSerializer):
    """The settings for price offers (PER-038).

    ``enabled`` (default false), ``also_temporary``, the limits ``min_percent`` and ``max_percent`` of the stored rate
    (null: none) and ``max_rounds`` (1 to 10 proposals per request).
    """

    class Meta:
        model = OfferSettings
        fields = SETTING_FIELDS


def _acting(view: ModuleAPIView, request: Request, project_pk: int, pk: int) -> tuple[Any, CrewLine, offers.Acting]:
    """The project, the crew line and who the caller is for its offers; 403 for anybody with nothing to do with them."""
    project = project_for(request, project_pk, ProjectAccess.DEPLOYMENT)
    line = get_object_or_404(
        CrewLine.objects.select_related("person", "job_function", "project"), pk=pk, project_id=project.pk
    )
    acting = offers.acting_for(request.user, view.rights, project, line)
    if not acting.allowed:
        raise PermissionDenied
    return project, line, acting


def _seen_by(acting: offers.Acting, request: Request) -> bool:
    """Whether the stored rate may be shown to the caller."""
    return acting.planner or offers.may_know_own_rates(request.user)


class CrewLineOffersView(ModuleAPIView):
    """``GET/POST /projects/{id}/crew-lines/{line}/offers`` – the exchange about the price of a deployment (PER-038)."""

    module = Module.PROJECTS
    # The person planned is crew and reads projects at most as far as the deployment; who may do what follows from the line.
    action_levels: ClassVar[dict[Any, int]] = {None: Level.READ}
    schema_tag = "personnel"

    @extend_schema(
        responses=inline_serializer(
            "CrewLineOffers",
            {
                "enabled": serializers.BooleanField(),
                "can_offer": serializers.BooleanField(),
                "units": serializers.ListField(child=serializers.CharField()),
                "rounds_used": serializers.IntegerField(),
                "max_rounds": serializers.IntegerField(),
                "offers": serializers.ListField(child=serializers.DictField()),
            },
        )
    )
    def get(self, request: Request, project_pk: int, pk: int) -> Response:
        """The proposals of the present request, oldest first, and whether the freelancer can offer now.

        ``can_offer`` is true if the feature is on, the person may offer, the request waits for an answer, rounds are
        left and no proposal waits. ``units`` are those an offer for this line can be made in.
        """
        _project, line, acting = _acting(self, request, project_pk, pk)
        settings = offers.current_settings()
        with_reference = _seen_by(acting, request)
        return Response(
            {
                "enabled": settings.enabled,
                "can_offer": offers.may_start_offer(line),
                "units": offers.unit_choices(line),
                "rounds_used": offers.rounds_used(line),
                "max_rounds": settings.max_rounds,
                "offers": [offer_document(offer, with_reference=with_reference) for offer in offers.negotiation(line)],
            }
        )

    @extend_schema(
        request=OfferInputSerializer,
        responses={201: inline_serializer("PriceOfferMade", {"id": serializers.IntegerField()})},
    )
    def post(self, request: Request, project_pk: int, pk: int) -> Response:
        """Make an offer for the deployment request (the freelancer), or enter one made by phone (a planner).

        400: the feature is off, the person may not offer, the request does not wait for an answer, an offer waits
        already, the rounds are used up, or the amount is outside the limits of the settings, has more than two
        decimals, or the unit, currency or day is invalid. The company is told.
        """
        _project, line, acting = _acting(self, request, project_pk, pk)
        serializer = OfferInputSerializer(data=body_of(request))
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if "unit" not in data:
            raise serializers.ValidationError({"unit": "This field is required."})
        offer = offers.make_offer(line, acting=acting, **data)
        return Response(offer_document(offer, with_reference=_seen_by(acting, request)), status=status.HTTP_201_CREATED)


class OfferActionView(ModuleAPIView):
    """``POST …/offers/{offer}/accept|reject|counter|withdraw`` – answer a proposal (PER-038)."""

    module = Module.PROJECTS
    action_levels: ClassVar[dict[Any, int]] = {None: Level.READ}
    schema_tag = "personnel"
    #: Set by the routes: ``accept``, ``reject``, ``counter`` or ``withdraw``.
    action_name: ClassVar[str] = ""

    @extend_schema(
        request=OfferInputSerializer,
        responses={200: inline_serializer("PriceOfferAnswered", {"id": serializers.IntegerField()})},
    )
    def post(self, request: Request, project_pk: int, pk: int, offer_pk: int) -> Response:
        """Accept (the deployment is accepted at the price; the cost rate of the line follows), reject, counter or withdraw.

        ``accept`` and ``reject`` take an optional ``note``; ``counter`` the fields of an offer (``unit`` defaults to
        that of the proposal); ``withdraw`` nothing. 400: the proposal was answered already, has run out, the request
        has changed, or the rounds are used up (``counter``).
        """
        _project, line, acting = _acting(self, request, project_pk, pk)
        offer = get_object_or_404(line.price_offers.select_related("person"), pk=offer_pk)
        body = body_of(request)
        with_reference = _seen_by(acting, request)
        if self.action_name == "counter":
            serializer = OfferInputSerializer(data=body)
            serializer.is_valid(raise_exception=True)
            result = offers.counter_offer(offer, acting=acting, **serializer.validated_data)
        elif self.action_name == "withdraw":
            result = offers.withdraw_offer(offer, acting=acting)
        else:
            decision = DecisionInputSerializer(data=body)
            decision.is_valid(raise_exception=True)
            note = decision.validated_data["note"]
            if self.action_name == "accept":
                result = offers.accept_offer(offer, acting=acting, note=note)
            else:
                result = offers.reject_offer(offer, acting=acting, note=note)
        line.refresh_from_db()
        return Response(
            {**offer_document(result, with_reference=with_reference), "request_status": line.request_status}
        )


class AcceptOfferView(OfferActionView):
    """``POST …/offers/{offer}/accept``."""

    action_name = "accept"

    @extend_schema(
        request=DecisionInputSerializer,
        responses={200: inline_serializer("PriceOfferAccept", {"id": serializers.IntegerField()})},
        description="Accept the proposal: the deployment is accepted at its price and the cost rate of the line follows. Optional ``note``.",
    )
    def post(self, request: Request, project_pk: int, pk: int, offer_pk: int) -> Response:
        """Accept the proposal: the deployment is accepted at its price and the cost rate of the line follows. Optional ``note``."""
        return super().post(request, project_pk, pk, offer_pk)


class RejectOfferView(OfferActionView):
    """``POST …/offers/{offer}/reject``."""

    action_name = "reject"

    @extend_schema(
        request=DecisionInputSerializer,
        responses={200: inline_serializer("PriceOfferReject", {"id": serializers.IntegerField()})},
        description="Reject the proposal; the request stays open. Optional ``note`` (the reason).",
    )
    def post(self, request: Request, project_pk: int, pk: int, offer_pk: int) -> Response:
        """Reject the proposal; the request stays open. Optional ``note`` (the reason)."""
        return super().post(request, project_pk, pk, offer_pk)


class CounterOfferView(OfferActionView):
    """``POST …/offers/{offer}/counter``."""

    action_name = "counter"

    @extend_schema(
        request=OfferInputSerializer,
        responses={200: inline_serializer("PriceOfferCounter", {"id": serializers.IntegerField()})},
        description="Answer the proposal with a proposal of the own (``amount``, ``unit``, ``message``, ``valid_until``); 400 once the rounds are used up.",
    )
    def post(self, request: Request, project_pk: int, pk: int, offer_pk: int) -> Response:
        """Answer the proposal with a proposal of the own (``amount``, ``unit``, ``message``, ``valid_until``); 400 once the rounds are used up."""
        return super().post(request, project_pk, pk, offer_pk)


class WithdrawOfferView(OfferActionView):
    """``POST …/offers/{offer}/withdraw``."""

    action_name = "withdraw"

    @extend_schema(
        request=None,
        responses={200: inline_serializer("PriceOfferWithdraw", {"id": serializers.IntegerField()})},
        description="Take back the own proposal that waits for an answer.",
    )
    def post(self, request: Request, project_pk: int, pk: int, offer_pk: int) -> Response:
        """Take back the own proposal that waits for an answer."""
        return super().post(request, project_pk, pk, offer_pk)


def negotiations(rights: Any, user: Any, *, everything: bool, person: Any = None) -> list[dict[str, Any]]:
    """The negotiations of the present requests, newest first: ``[{"line": …, "offers": [PriceOffer …]}]``.

    ``person``: only that person's (``/people/me/offers``); else those of the projects the user reads.
    """
    found = PriceOffer.objects.filter(line__requested_at__isnull=False, requested_at=F("line__requested_at"))
    if person is not None:
        found = found.filter(person=person)
    else:
        found = found.filter(line__project__in=readable_projects(rights, user))
    grouped: dict[int, list[PriceOffer]] = {}
    for offer in found.select_related("line__project", "line__job_function", "person").order_by("-id")[: LIMIT * 5]:
        grouped.setdefault(offer.line_id, []).append(offer)
    result = []
    for rounds in grouped.values():
        rounds.sort(key=lambda item: item.round)
        waiting = rounds[-1].status == OfferStatus.OPEN and not rounds[-1].has_run_out
        if everything or waiting:
            result.append({"line": rounds[-1].line, "offers": rounds, "waiting": waiting})
    return result[:LIMIT]


def negotiation_document(
    item: dict[str, Any], *, with_reference: bool, can_decide: bool | None = None
) -> dict[str, Any]:
    """One negotiation: the line it is about and its proposals."""
    line = item["line"]
    document = {
        "crew_line": line.pk,
        "project": line.project_id,
        "project_number": line.project.number,
        "project_name": line.project.name,
        "job_function": line.job_function.name,
        "person": line.person_id,
        "person_name": line.person.name if line.person_id else None,
        "start": line.start,
        "end": line.end,
        "request_status": line.request_status,
        "waiting": item["waiting"],
        "offers": [offer_document(offer, with_reference=with_reference) for offer in item["offers"]],
    }
    if can_decide is not None:
        document["can_decide"] = can_decide
    return document


class PriceOffersView(ModuleAPIView):
    """``GET /price-offers`` – the negotiations about prices, with the stored rate next to the offer (PER-038).

    Needs read access to personnel and the right to see hourly rates and personnel costs (AUT-019). ``?show=all``
    adds the negotiations that nothing waits for; by default only those waiting for an answer. Only projects the
    caller reads. ``can_decide`` says whether the caller may answer in that project.
    """

    module = Module.PERSONNEL
    schema_tag = "personnel"

    @extend_schema(
        parameters=[OpenApiParameter("show", str, description="all – also the negotiations nothing waits for")],
        responses={
            200: inline_serializer("PriceOfferNegotiations", {"crew_line": serializers.IntegerField()}, many=True)
        },
    )
    def get(self, request: Request) -> Response:
        """The negotiations, newest first, at most 200."""
        if not self.rights.has(SpecialRight.PERSONNEL_COSTS):
            raise PermissionDenied
        items = negotiations(self.rights, request.user, everything=request.query_params.get("show") == "all")
        levels = access_of_many(self.rights, request.user, sorted({item["line"].project_id for item in items}))
        return Response(
            [
                negotiation_document(
                    item,
                    with_reference=True,
                    can_decide=may_plan_crew(self.rights, levels[item["line"].project_id])
                    and not item["line"].project.is_locked,
                )
                for item in items
            ]
        )


class OwnOffersView(ModuleAPIView):
    """``GET /people/me/offers`` – the caller's own negotiations over all deployments (PER-038).

    No right on a module is needed – everybody keeps their own data; an account that is not a person gets 404.
    ``?show=all`` adds the negotiations nothing waits for.
    """

    module = AUTHENTICATED_ONLY
    schema_tag = "personnel"

    @extend_schema(
        parameters=[OpenApiParameter("show", str, description="all – also the negotiations nothing waits for")],
        responses={200: inline_serializer("OwnPriceOffers", {"crew_line": serializers.IntegerField()}, many=True)},
    )
    def get(self, request: Request) -> Response:
        """The own negotiations, newest first."""
        person = person_of(request.user)
        if person is None:
            raise NotFound
        items = negotiations(
            request_rights(request), request.user, everything=request.query_params.get("show") == "all", person=person
        )
        with_reference = offers.may_know_own_rates(request.user)
        return Response([negotiation_document(item, with_reference=with_reference) for item in items])


class OfferSettingsView(ModuleAPIView):
    """``GET/PATCH /settings/price-offers`` – whether freelancers may offer their own price, and within which limits.

    Needs the module "Einstellungen". ``enabled`` is false until the company switches the feature on.
    """

    module = Module.ADMINISTRATION
    schema_tag = "settings"

    @extend_schema(responses=OfferSettingsSerializer)
    def get(self, request: Request) -> Response:
        """Return the settings."""
        return Response(OfferSettingsSerializer(OfferSettings.load()).data)

    @extend_schema(request=OfferSettingsSerializer, responses=OfferSettingsSerializer)
    def patch(self, request: Request) -> Response:
        """Change the values that were sent; everything else stays as it is."""
        serializer = OfferSettingsSerializer(OfferSettings.load(), data=body_of(request), partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(OfferSettingsSerializer(OfferSettings.objects.get(pk=1)).data)
