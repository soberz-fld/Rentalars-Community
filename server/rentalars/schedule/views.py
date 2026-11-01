# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views of the planning overviews (PRJ-028, VFG-012, VFG-014, VFG-020 to VFG-023).

* Calendar: the projects of a month as continuous bars (VFG-020), or a week
  as a time grid (VFG-021).
* Timeline: the projects of some weeks as bars, with their phases; or of
  one to ten days in hour columns (VFG-022, VFG-024).
* Material utilization: products of a category day by day, or in hours of
  one to ten days – how much is reserved; the search field suggests
  products while typing (VFG-025, VFG-029).
* Personnel plan: every active person, with availability, deployments and
  absences (VFG-014, VFG-023), in weeks or hours.

The shortage list (VFG-013) lives in ``availability.views`` and is one more
tab of this section.
"""

from __future__ import annotations

import datetime
from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from rentalars.accounts.rights import Module, SpecialRight, module_required, request_rights, require
from rentalars.core.listing import query_date
from rentalars.masterdata.models import Category
from rentalars.personnel.models import AvailabilityState, Person
from rentalars.products.models import Product, ProductKind
from rentalars.projects.access import visible_projects
from rentalars.projects.models import ProjectStatus
from rentalars.schedule import calendars, moves, services
from rentalars.schedule.follow_ups import visible_follow_ups

#: Statuses shown unless the user asks for the finished ones too.
_HIDDEN_BY_DEFAULT = (ProjectStatus.CANCELLED,)

#: Product kinds without a utilization: the search of the utilization does not suggest them (VFG-025).
_WITHOUT_STOCK = sorted(set(ProductKind.values) - services.UTILIZATION_KINDS)


def _projects(request: HttpRequest) -> Any:
    # PRJ-090: service cases are no projects of the calendar or the timelines.
    projects = visible_projects(request_rights(request), request.user).exclude(kind="service_case")
    if not request.GET.get("all"):
        projects = projects.exclude(status__in=_HIDDEN_BY_DEFAULT)
    return projects


#: The two views of the calendar (PRJ-067).
CALENDAR_VIEWS = ("month", "week")

#: VFG-028: the calendar opens with the week unless the session remembers another choice.
DEFAULT_CALENDAR_VIEW = "week"

#: VFG-039: what the calendar shows besides the projects, and whether it does so by default –
#: the phases of the projects (as) and the follow-ups (PRJ-105, PRJ-109).
CALENDAR_OPTIONS = {"phases": True, "follow_ups": False}

#: VFG-039: the session key under which the options chosen last are kept.
_CALENDAR_OPTIONS_KEY = "calendar_options"


def calendar_options(request: HttpRequest) -> dict[str, bool]:
    """Whether the calendar shows the phases and the follow-ups (VFG-039).

    The address decides – ``?phases=0`` or ``1``, ``?follow_ups=0`` or ``1``; the form sends a hidden ``0``
    before each tick box, so the last value counts – then what the user chose last (kept in the session,
    like the view of the calendar), then :data:`CALENDAR_OPTIONS`. A choice in the address is remembered.
    """
    remembered = request.session.get(_CALENDAR_OPTIONS_KEY)
    remembered = remembered if isinstance(remembered, dict) else {}
    options = {}
    for name, default in CALENDAR_OPTIONS.items():
        asked = request.GET.get(name)
        if asked in ("0", "1"):
            options[name] = asked == "1"
        else:
            value = remembered.get(name)
            options[name] = value if isinstance(value, bool) else default
    if any(request.GET.get(name) in ("0", "1") for name in CALENDAR_OPTIONS):
        _remember(request, _CALENDAR_OPTIONS_KEY, options)
    return options


@module_required(Module.PROJECTS)
def calendar(request: HttpRequest) -> HttpResponse:
    """The projects of a month or of a week in a calendar (PRJ-028, PRJ-067).

    ``?view=week`` or ``?view=month`` switches between the two; the choice is
    remembered for the session, so the calendar opens as it was left.

    VFG-028: without a choice the calendar opens with the week.
    An address with ``month`` or ``week`` but without ``view``
    shows what it names.

    VFG-039: two tick boxes choose whether the phases of the
    projects and the follow-ups are shown (:func:`calendar_options`).
    """
    today = timezone.localdate()
    view = request.GET.get("view", "")
    if view in CALENDAR_VIEWS:
        if request.session.get("calendar_view") != view:
            request.session["calendar_view"] = view
    elif "month" in request.GET or "week" in request.GET:
        view = "month" if "month" in request.GET else "week"
    else:
        view = request.session.get("calendar_view", DEFAULT_CALENDAR_VIEW)
        view = view if view in CALENDAR_VIEWS else DEFAULT_CALENDAR_VIEW
    # VFG-039: phases of the projects and follow-ups – only those the user may see.
    options = calendar_options(request)
    shown = {
        "phases": options["phases"],
        "follow_ups": visible_follow_ups(request_rights(request), request.user) if options["follow_ups"] else None,
    }
    common = {
        "tab": "calendar",
        "view": view,
        "weekdays": services.day_range(services.monday_of(today), 7),
        "options": options,
    }
    if view == "week":
        first = query_date(request.GET.get("week")) or today
        monday = services.monday_of(first)
        return render(
            request,
            "schedule/calendar.html",
            {
                **common,
                "grid": calendars.week_grid(_projects(request), monday, **shown),
                "monday": monday,
                "sunday": monday + datetime.timedelta(days=6),
                "week_number": monday.isocalendar().week,
                "previous": monday - datetime.timedelta(days=7),
                "following": monday + datetime.timedelta(days=7),
                "this_week": services.monday_of(today),
                "legend": _status_legend(bool(request.GET.get("all"))),
            },
        )
    try:
        year, month = (int(part) for part in request.GET.get("month", "").split("-", 1))
        datetime.date(year, month, 1)
    except ValueError:
        year, month = today.year, today.month
    current = datetime.date(year, month, 1)
    previous = (current - datetime.timedelta(days=1)).replace(day=1)
    following = (current + datetime.timedelta(days=32)).replace(day=1)
    return render(
        request,
        "schedule/calendar.html",
        {
            **common,
            "weeks": calendars.month_weeks(_projects(request), year, month, **shown),
            "legend": _status_legend(bool(request.GET.get("all"))),
            "month": current,
            "previous": previous,
            "following": following,
            "this_month": today.replace(day=1),
        },
    )


#: The session key under which the number of days chosen last is kept (VFG-024).
_DAYS_KEY = "schedule_days"

#: VFG-028: the session key under which "days" or "weeks", chosen last, is kept.
_SPAN_KEY = "schedule_span"


def _remember(request: HttpRequest, key: str, value: Any) -> None:
    """Keep a choice for the session – writing the session only when it changes."""
    if request.session.get(key) != value:
        request.session[key] = value


def _scale(request: HttpRequest, *, default_weeks: int) -> tuple[services.Scale, dict[str, Any]]:
    """The columns asked for, and the number of days the switch to days offers (VFG-024, VFG-028).

    Like the view of the calendar (PRJ-067), the number of days chosen last
    is remembered for the session: switching from weeks back to days shows
    as many days as before.

    VFG-028: an address without ``days`` and ``weeks`` – the tab, the
    navigation – shows days in hours: as many as chosen last, else
    :data:`services.DEFAULT_DAYS` (four). Whoever switched to weeks in this
    session gets weeks again. The timeline, the material utilization and
    the personnel plan share these choices.
    """
    remembered = services.day_count_of(request.session.get(_DAYS_KEY)) or services.DEFAULT_DAYS
    default_days = 0 if request.session.get(_SPAN_KEY) == "weeks" else remembered
    scale, navigation = services.scale_from_request(request, default_weeks=default_weeks, default_days=default_days)
    if navigation["zoom"]:
        if "days" in request.GET:
            _remember(request, _DAYS_KEY, navigation["zoom"])
            _remember(request, _SPAN_KEY, "days")
    else:
        navigation["day_count"] = remembered
        if "weeks" in request.GET:
            _remember(request, _SPAN_KEY, "weeks")
    return scale, navigation


@module_required(Module.PROJECTS)
def timeline(request: HttpRequest) -> HttpResponse:
    """The projects of some weeks, or of one to ten days in hours, as bars (PRJ-028, VFG-022, VFG-024).

    VFG-026: in hours, whoever may change a project drags its rental period
    and its phases to other times (``schedule.moves``).
    """
    scale, navigation = _scale(request, default_weeks=4)
    rights = request_rights(request)
    rows = services.project_timeline(
        _projects(request), scale, movable=lambda shown: moves.movable_project_ids(rights, request.user, shown)
    )
    return render(
        request,
        "schedule/timeline.html",
        {
            "tab": "timeline",
            "scale": scale,
            "days": scale.days,
            "rows": rows,
            "can_move": any(bar.move for _project, bars in rows for bar in bars),
            **navigation,
        },
    )


@module_required(Module.PROJECTS)
def products(request: HttpRequest) -> HttpResponse:
    """How much of the products of a category is reserved, day by day (VFG-012).

    For users whose project rights hold in all projects: the utilization
    sums up every project, also those the user could not open otherwise.

    VFG-025: the field for name or article number suggests products while
    typing; choosing one sends ``product`` and shows just that product. Text
    sent without choosing (``q``) still finds every product that contains
    it. Category and search are two forms, so that a chosen product never
    stands against a category chosen afterwards.

    VFG-029: the same span as the timeline and the personnel plan – one to
    ten days in hour columns (four unless chosen otherwise, VFG-028) or one
    to twelve weeks of days – with the same switch and the same way of
    moving on (:func:`_scale`).

    VFG-037: kits – the category "Sets" – can be
    chosen as well. A kit's row tells how many complete kits are free; its
    components unfold below it (``services.UtilizationRow``). A kit chosen
    alone, e.g. by the link of its product page, shows them unfolded.
    """
    rights = request_rights(request)
    require(not rights.is_limited_to_assigned_projects(Module.PROJECTS) and rights.can_read(Module.PRODUCTS))
    require(rights.has(SpecialRight.AVAILABILITY))  # AUT-032: availability as a special right
    scale, navigation = _scale(request, default_weeks=2)
    categories = Category.objects.in_tree_order(only_active=True)
    chosen = request.GET.get("category", "")
    text = request.GET.get("q", "").strip()
    product_id = request.GET.get("product", "")
    product_id = product_id if product_id.isdigit() else ""
    shown_products = Product.objects.filter(kind__in=services.UTILIZATION_KINDS, is_active=True)
    if product_id:
        shown_products = shown_products.filter(pk=int(product_id))
    else:
        if chosen.isdigit():
            shown_products = shown_products.filter(category_id__in=Category.objects.descendant_ids(int(chosen)))
        if text:
            shown_products = shown_products.filter(name__icontains=text) | shown_products.filter(
                article_number__icontains=text
            )
    limited = bool(product_id) or chosen.isdigit() or bool(text)
    product_list = list(shown_products.order_by("article_number")[:60]) if limited else []
    rows = services.utilization_rows(product_list, scale)
    return render(
        request,
        "schedule/products.html",
        {
            "tab": "products",
            "scale": scale,
            "days": scale.days,
            "rows": rows,
            "categories": categories,
            "chosen": chosen,
            "q": text,
            "product_id": product_id,
            # VFG-025: suggestions only of products that have a utilization: rental and sale products, kits (VFG-037).
            "suggest_url": reverse("products:suggest") + "?exclude_kind=" + ",".join(_WITHOUT_STOCK),
            "limited": limited,
            "has_kits": any(row.is_kit for row in rows),
            "kits_unfolded": bool(product_id),
            **navigation,
        },
    )


@module_required(Module.PERSONNEL)
def personnel(request: HttpRequest) -> HttpResponse:
    """Every active person, with availability, deployments and absences (VFG-014, VFG-023).

    VFG-023: without "Only people with deployments or
    absences" every active person is in the plan – also people without
    a job function (see ``services.people_in_plan``).

    VFG-031: in hours, whoever may change a project drags the deployments of
    its crew to other times, as the phases on the timeline (``schedule.moves``).
    """
    scale, navigation = _scale(request, default_weeks=2)
    start, end = services.bounds(scale.days)
    people = services.people_in_plan(
        Person.objects.filter(is_active=True), start, end, busy_only=bool(request.GET.get("busy"))
    )
    rights = request_rights(request)
    rows = services.personnel_rows(
        people.order_by("last_name", "first_name"),
        scale,
        movable=lambda shown: moves.movable_project_ids(rights, request.user, shown),
    )
    return render(
        request,
        "schedule/personnel.html",
        {
            "tab": "personnel",
            "scale": scale,
            "days": scale.days,
            "rows": rows,
            "busy_only": bool(request.GET.get("busy")),
            "can_move": any(bar.move for row in rows for bar in row.bars),
            "availability_legend": AvailabilityState.choices,
            **navigation,
        },
    )


def _status_legend(with_cancelled: bool) -> list[tuple[str, str]]:
    """The colours of the project statuses for the legend of the calendar (VFG-020).

    Statuses that share a colour share an entry; cancelled projects only
    appear when they are shown.
    """
    groups = [
        ("inquiry", [ProjectStatus.INQUIRY]),
        ("option", [ProjectStatus.OPTION]),
        ("confirmed", [ProjectStatus.CONFIRMED_OPEN, ProjectStatus.CONFIRMED]),
        ("out", [ProjectStatus.OUT]),
        ("returned", [ProjectStatus.RETURNED, ProjectStatus.CLOSED]),
    ]
    if with_cancelled:
        groups.append(("cancelled", [ProjectStatus.CANCELLED]))
    return [(css, " / ".join(str(status.label) for status in statuses)) for css, statuses in groups]
