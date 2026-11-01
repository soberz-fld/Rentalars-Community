# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views of the price offers of freelancers (PER-038).

* The freelancer makes an offer for a deployment request (:func:`offer_make`) and answers a counter-offer;
  they find the buttons in the deployment view and on the start page.
* The company – whoever plans the crew of the project and sees personnel costs (AUT-019) – accepts, rejects or
  counters in the planning (:func:`offer_accept` and the others) and finds all negotiations under Personnel →
  Price offers (:func:`offer_list`).
* Einstellungen → Preisangebote (:func:`offer_settings`).

All of them call ``personnel.offers``, which the API calls too (API-002).
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import F
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Module, SpecialRight, module_required, request_rights
from rentalars.personnel import offers
from rentalars.personnel.offer_forms import DecisionForm, OfferForm, OfferSettingsForm
from rentalars.personnel.offer_models import OfferSettings, OfferSide, OfferStatus, PriceOffer
from rentalars.projects.access import ProjectAccess, access_of_many, may_plan_crew, project_for, readable_projects

#: How many negotiations the overview shows at most.
OVERVIEW_LIMIT = 200


def _error_text(error: ValidationError) -> str:
    """One readable sentence for a message."""
    if hasattr(error, "error_dict"):
        return " ".join(m for errors in error.error_dict.values() for single in errors for m in single.messages)
    return " ".join(error.messages)


def _line_and_acting(request: HttpRequest, pk: int, line_pk: int) -> tuple[Any, Any, offers.Acting]:
    """The project, the crew line and who the user is for its offers; refuses a user with nothing to do with them.

    The person planned answers for themselves, which the deployment view allows (as ``crew_answer``).
    """
    project = project_for(request, pk, ProjectAccess.DEPLOYMENT)
    line = get_object_or_404(project.crew_lines.select_related("person", "job_function", "project"), pk=line_pk)
    acting = offers.acting_for(request.user, request_rights(request), project, line)
    if not acting.allowed:
        raise PermissionDenied
    return project, line, acting


def _offer_of(line: Any, offer_pk: int) -> PriceOffer:
    return get_object_or_404(line.price_offers.select_related("person"), pk=offer_pk)


def _next_url(request: HttpRequest, default: str) -> str:
    """Where to go after an action: the address in ``next`` if it is one of this site."""
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return default


def _after(request: HttpRequest, project: Any, acting: offers.Acting) -> HttpResponse:
    """Answer an action: the refreshed planning for htmx from the planning, else back where the user came from."""
    if request.headers.get("HX-Request") and acting.planner and not acting.own:
        from rentalars.projects.crew_views import _crew_response

        return _crew_response(request, project)
    default = (
        reverse("projects:deployment", args=[project.pk])
        if acting.own
        else reverse("projects:detail", args=[project.pk])
    )
    return redirect(_next_url(request, default))


def _may_see_reference(request: HttpRequest, acting: offers.Acting) -> bool:
    """Whether the stored rate may be shown: to the company, and to who sees their own rates."""
    return acting.planner or offers.may_know_own_rates(request.user)


def _form_page(
    request: HttpRequest,
    project: Any,
    line: Any,
    acting: offers.Acting,
    form: OfferForm,
    *,
    countering: PriceOffer | None,
) -> HttpResponse:
    """The page with the form of an offer or a counter-offer, the stored rate (where allowed) and the exchange so far."""
    unit = (
        (form["unit"].value() or offers.unit_choices(line)[0])
        if form.is_bound
        else (countering.unit if countering else offers.unit_choices(line)[0])
    )
    show_reference = _may_see_reference(request, acting)
    low, high = offers.limits_for(line, unit)
    return render(
        request,
        "personnel/offer_form.html",
        {
            "project": project,
            "line": line,
            "form": form,
            "countering": countering,
            "log": offers.negotiation(line),
            "show_reference": show_reference,
            "reference": offers.reference_amount(line, unit) if show_reference else None,
            "low": low if show_reference else None,
            "high": high if show_reference else None,
            "unit": unit,
            "settings": offers.current_settings(),
            "next": _next_url(request, ""),
            "as_company": acting.planner and not acting.own,
        },
    )


def offer_make(request: HttpRequest, pk: int, line_pk: int) -> HttpResponse:
    """The freelancer makes an offer for the deployment they were asked for (PER-038); a planner enters one made by phone."""
    project, line, acting = _line_and_acting(request, pk, line_pk)
    if reason := offers.blocker(line) or (
        _("An offer waits for an answer already.") if offers.open_offer(line) else ""
    ):
        messages.error(request, reason)
        return redirect(_next_url(request, reverse("projects:deployment", args=[project.pk])))
    form = OfferForm(request.POST or None, line=line)
    if request.method == "POST" and form.is_valid():
        try:
            offers.make_offer(line, acting=acting, **_values(form))
        except ValidationError as error:
            _add_errors(form, error)
        else:
            messages.success(request, _("The offer was passed on."))
            return _after(request, project, acting)
    return _form_page(request, project, line, acting, form, countering=None)


def _values(form: OfferForm) -> dict[str, Any]:
    data = form.cleaned_data
    return {
        "amount": data["amount"],
        "unit": data["unit"],
        "message": data["message"],
        "valid_until": data["valid_until"],
    }


def _add_errors(form: OfferForm, error: ValidationError) -> None:
    """Show what the service refused at the field it belongs to, else at the top of the form."""
    if hasattr(error, "error_dict"):
        for name, errors in error.error_dict.items():
            for single in errors:
                form.add_error(name if name in form.fields else None, single)
    else:
        form.add_error(None, error)


@require_POST
def offer_accept(request: HttpRequest, pk: int, line_pk: int, offer_pk: int) -> HttpResponse:
    """Accept a proposal: the deployment is accepted at its price (PER-038)."""
    project, line, acting = _line_and_acting(request, pk, line_pk)
    try:
        offers.accept_offer(_offer_of(line, offer_pk), acting=acting, note=request.POST.get("note", ""))
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, _("The offer was accepted."))
    return _after(request, project, acting)


@require_POST
def offer_reject(request: HttpRequest, pk: int, line_pk: int, offer_pk: int) -> HttpResponse:
    """Reject a proposal; the request stays open (PER-038)."""
    project, line, acting = _line_and_acting(request, pk, line_pk)
    form = DecisionForm(request.POST)
    try:
        offers.reject_offer(
            _offer_of(line, offer_pk), acting=acting, note=form.cleaned_data.get("note", "") if form.is_valid() else ""
        )
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, _("The offer was rejected."))
    return _after(request, project, acting)


@require_POST
def offer_withdraw(request: HttpRequest, pk: int, line_pk: int, offer_pk: int) -> HttpResponse:
    """Take back an own proposal that waits for an answer (PER-038)."""
    project, line, acting = _line_and_acting(request, pk, line_pk)
    try:
        offers.withdraw_offer(_offer_of(line, offer_pk), acting=acting)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, _("The offer was withdrawn."))
    return _after(request, project, acting)


def offer_counter(request: HttpRequest, pk: int, line_pk: int, offer_pk: int) -> HttpResponse:
    """Answer a proposal with one of the own: the company counters an offer, the freelancer a counter (PER-038)."""
    project, line, acting = _line_and_acting(request, pk, line_pk)
    offer = _offer_of(line, offer_pk)
    if not offer.is_open:
        messages.error(request, _("This offer has been answered already."))
        return _after(request, project, acting)
    form = OfferForm(request.POST or None, line=line, initial={"unit": offer.unit})
    if request.method == "POST" and form.is_valid():
        try:
            offers.counter_offer(offer, acting=acting, **_values(form))
        except ValidationError as error:
            _add_errors(form, error)
        else:
            messages.success(request, _("The counter-offer was passed on."))
            return _after(request, project, acting)
    return _form_page(request, project, line, acting, form, countering=offer)


@module_required(Module.PERSONNEL)
def offer_list(request: HttpRequest) -> HttpResponse:
    """All negotiations about prices of deployments, with the stored rate next to the offer (PER-038).

    Only for whoever sees personnel costs (AUT-019) – the page is made of amounts. By default the negotiations
    that wait for the company; ``?show=all`` shows the others too.
    """
    rights = request_rights(request)
    if not rights.has(SpecialRight.PERSONNEL_COSTS):
        raise PermissionDenied
    everything = request.GET.get("show") == "all"
    current = (
        PriceOffer.objects.filter(line__requested_at__isnull=False, requested_at=F("line__requested_at"))
        .filter(line__project__in=readable_projects(rights, request.user))
        .select_related("line__project", "line__job_function", "person")
        .order_by("-id")
    )
    grouped: dict[int, list[PriceOffer]] = {}
    for offer in current[: OVERVIEW_LIMIT * 5]:
        grouped.setdefault(offer.line_id, []).append(offer)
    rows = []
    for rounds in grouped.values():
        rounds.sort(key=lambda item: item.round)
        latest = rounds[-1]
        waiting = latest.status == OfferStatus.OPEN and not latest.has_run_out
        if not waiting and not everything:
            continue
        rows.append({"line": latest.line, "rounds": rounds, "latest": latest, "waiting": waiting})
    rows = rows[:OVERVIEW_LIMIT]
    levels = access_of_many(rights, request.user, sorted({row["line"].project_id for row in rows}))
    for row in rows:
        latest = row["latest"]
        row["percent"] = offers.percent_of_reference(latest.amount, latest.reference_amount)
        row["can_decide"] = may_plan_crew(rights, levels[row["line"].project_id]) and not row["line"].project.is_locked
        row["waiting_for_company"] = row["waiting"] and latest.side == OfferSide.FREELANCER
    return render(
        request,
        "personnel/offer_list.html",
        {
            "rows": rows,
            "everything": everything,
            "settings": offers.current_settings(),
            "limited": len(grouped) > OVERVIEW_LIMIT,
        },
    )


@module_required(Module.ADMINISTRATION)
def offer_settings(request: HttpRequest) -> HttpResponse:
    """Einstellungen → Preisangebote: the switch, who may offer, the limits and the rounds (PER-038)."""
    can_write = request_rights(request).can_write(Module.ADMINISTRATION)
    current = OfferSettings.load()
    form = OfferSettingsForm(request.POST if request.method == "POST" else None, instance=current)
    if request.method == "POST":
        if not can_write:
            return render(request, "403.html", status=403)
        if form.is_valid():
            form.save()
            messages.success(request, _("Settings saved."))
            return redirect("personnel:offer_settings")
    return render(request, "personnel/offer_settings.html", {"form": form, "can_write": can_write})
