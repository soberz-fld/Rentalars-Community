# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views of the availability calendar and the calendar links (PER-021 to PER-023).

Two audiences:

* **the person** on the tab "Availability" of "My area" (``/me/availability/``,
  UIX-026): colours the own availability, enters series (PER-028), links
  calendars with busy times (PER-031), downloads or subscribes to the own
  deployments, and sets up a CalDAV calendar – no right on the personnel
  module needed;
* **personnel planning** on the tab "Availability" of a person: sees the
  calendar (read access) and, with write access, colours it and links or
  removes calendars for the person – without ever seeing their addresses.
  The CalDAV settings and the subscription link stay the person's own
  business.

Both see the availability as a month or as a week with hours (PER-030).

And one view without login: the subscription link itself (``/calendar-feed/``),
which works with its secret token only.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any

from django.contrib import messages
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.dates import WEEKDAYS_ABBR
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from rentalars.accounts.rights import Level, Module, module_required, request_rights
from rentalars.core.i18n import file_name, local_pattern
from rentalars.personnel import calendars
from rentalars.personnel import marks as availability_marks
from rentalars.personnel.availability_week import parse_week, week_calendar
from rentalars.personnel.forms import AvailabilityMarkForm, AvailabilitySeriesForm, CalDAVForm, FeedLinkForm
from rentalars.personnel.models import AvailabilitySeries, AvailabilityState, Person
from rentalars.projects.access import person_of, visible_projects

#: Wrong subscription links from one address before it has to wait (PER-023).
FEED_FAILURES_PER_ADDRESS = 20
#: Readings of one subscription link in :data:`FEED_WINDOW_SECONDS`; calendar programs ask every 15 minutes or less often.
FEED_READINGS_PER_LINK = 60
FEED_WINDOW_SECONDS = 600


def _own_person(request: HttpRequest) -> Person:
    """Return the person of the logged-in user, or refuse (AUT-012)."""
    person = person_of(request.user)
    if person is None:
        raise PermissionDenied
    return person


def _error_text(error: ValidationError) -> str:
    return " ".join(error.messages)


def _form_errors(form: Any) -> str:
    return " ".join(message for errors in form.errors.values() for message in errors)


# --- Month or week (PER-030) ----------------------------------------------------------------------------

#: The two views of the availability calendar; the choice is remembered for the session.
CALENDAR_VIEWS = ("month", "week")


@dataclass(frozen=True)
class Place:
    """What the availability calendar shows: a month or a week (PER-030)."""

    view: str
    month: datetime.date
    monday: datetime.date

    @property
    def query(self) -> str:
        """The query string that shows the same again."""
        if self.view == "week":
            return f"?view=week&week={self.monday:%Y-%m-%d}"
        return f"?month={self.month:%Y-%m}"


def calendar_place(request: HttpRequest, data: Any) -> Place:
    """Read month or week from the address (or the hidden fields of a form); remember the view (PER-030).

    ``view`` says month or week; without it a ``week`` means the week and a
    ``month`` the month, and with neither the view chosen last in the
    session counts. A week without a day of its own is the first week of the
    month asked for, or this week; a month without one is the month of the
    week.
    """
    view = data.get("view", "")
    if view not in CALENDAR_VIEWS:
        view = "week" if data.get("week") else "month" if data.get("month") else ""
    if view and request.method in ("GET", "HEAD") and request.session.get("availability_view") != view:
        request.session["availability_view"] = view
    if not view:
        view = request.session.get("availability_view", "month")
        view = view if view in CALENDAR_VIEWS else "month"
    month = availability_marks.parse_month(data.get("month"))
    if data.get("week"):
        monday = parse_week(data.get("week"))
        if not data.get("month"):
            month = (monday + datetime.timedelta(days=3)).replace(day=1)
    elif data.get("month") and month != timezone.localdate().replace(day=1):
        monday = parse_week(month.isoformat())
    else:
        monday = parse_week(None)
    return Place(view=view, month=month, monday=monday)


def _back(path: str, place: Place, anchor: str) -> HttpResponse:
    return redirect(f"{path}{place.query}#{anchor}")


# --- Shared parts of the pages ---------------------------------------------------------------------------


@dataclass
class SeriesRow:
    """A series in the list under the calendar (PER-028)."""

    series: AvailabilitySeries
    description: str
    #: The day "remove from" suggests: today, or the first day of a series still to come.
    from_day: datetime.date


def availability_context(request: HttpRequest, person: Person, *, editable: bool, own: bool) -> dict[str, Any]:
    """What the availability calendar needs: a month, or a week with hours (PER-021, PER-027, PER-028, PER-030).

    ``shown_periods`` are the periods of the month or week for the list
    under the calendar.
    """
    today = timezone.localdate()
    place = calendar_place(request, request.GET)
    series = [
        SeriesRow(item, availability_marks.describe_series(item), max(today, item.first_day))
        for item in person.availability_series.all()
        if availability_marks.series_limit(item) >= today - datetime.timedelta(days=31)
    ]
    context: dict[str, Any] = {
        "place": place,
        "mark_form": AvailabilityMarkForm(initial={"state": AvailabilityState.AVAILABLE, "interval": 1}),
        "availability_editable": editable,
        "availability_own": own,
        "weekdays": [WEEKDAYS_ABBR[number] for number in range(7)],
        "series_rows": series,
        "this_week": parse_week(None),
        "this_month": today.replace(day=1),
    }
    if place.view == "week":
        visible = None
        if not own:
            # AUT-016: deployments in projects the reader may not open are named by their job function only.
            visible = set(visible_projects(request_rights(request), request.user).values_list("pk", flat=True))
        week = week_calendar(person, place.monday, own=own, visible_ids=visible)
        context.update({"week": week, "shown_periods": week.periods})
    else:
        calendar = availability_marks.month_calendar(person, place.month)
        context.update({"calendar": calendar, "shown_periods": calendar.month_periods})
    return context


def own_calendar_context(request: HttpRequest, person: Person) -> dict[str, Any]:
    """Everything the own profile shows about availability and calendars (PER-021 to PER-023, PER-030, PER-031)."""
    context = availability_context(request, person, editable=True, own=True)
    context.update(
        {
            "feeds": list(person.calendar_feeds.all()),
            "feed_form": FeedLinkForm(),
            "caldav_form": CalDAVForm(
                initial={"caldav_url": person.caldav_url, "caldav_username": person.caldav_username}
            ),
            "caldav_password_set": bool(person.caldav_password_encrypted),
            "subscription_url": calendars.subscription_url(person),
        }
    )
    return context


def _mark(request: HttpRequest, person: Person) -> Place:
    """Read the form of the calendar and colour or clear the days, or enter a series; returns month or week shown."""
    month = calendar_place(request, request.POST)
    form = AvailabilityMarkForm(request.POST)
    if not form.is_valid():
        messages.error(request, _form_errors(form))
        return month
    data = form.cleaned_data
    state = None if data["state"] == AvailabilityMarkForm.CLEAR else data["state"]
    try:
        if data.get("repeat"):
            # PER-028: the chosen days are the first occurrence of a series.
            series = availability_marks.create_series(person, **form.series_values())
            count = len(availability_marks.series_occurrences(series))
            messages.success(
                request,
                ngettext("Series entered: %(count)d time.", "Series entered: %(count)d times.", count)
                % {"count": count},
            )
            return month
        availability_marks.mark_days(
            person,
            data["start_day"],
            data["end_day"],
            state,
            note=data["note"],
            start_time=data["start_time"],
            end_time=data["end_time"],
        )
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, _("Availability saved.") if state else _("Entries removed."))
    return month


def _moment(text: str) -> datetime.datetime | None:
    value = parse_datetime(text or "")
    if value is None:
        return None
    return value if timezone.is_aware(value) else timezone.make_aware(value)


def _remove(request: HttpRequest, person: Person) -> None:
    """Remove what the person entered in the period of a row of the list (PER-021)."""
    start, end = _moment(request.POST.get("start", "")), _moment(request.POST.get("end", ""))
    if start is None or end is None:
        messages.error(request, _("The period is missing."))
        return
    try:
        availability_marks.clear_period(person, start, end)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, _("Entries removed."))


def _remove_series(request: HttpRequest, person: Person, series_pk: int) -> None:
    """Remove a series, all of it or from a day on (PER-028)."""
    series = get_object_or_404(person.availability_series, pk=series_pk)
    from_day = None if request.POST.get("all") else parse_date(request.POST.get("from_day", "") or "")
    if not request.POST.get("all") and from_day is None:
        messages.error(request, _("Choose the day from which the series is removed."))
        return
    availability_marks.remove_series(series, from_day=from_day)
    messages.success(
        request,
        _("Series removed.")
        if from_day is None
        else _("Series removed from %(date)s on.") % {"date": f"{from_day:{local_pattern('%d.%m.%Y')}}"},
    )


def _series_page(request: HttpRequest, person: Person, series_pk: int, *, back: str, own: bool) -> HttpResponse:
    """Change a series from a day on (PER-028): the form, and saving it."""
    series = get_object_or_404(person.availability_series, pk=series_pk)
    form = AvailabilitySeriesForm(request.POST or None, series=series)
    if request.method == "POST" and form.is_valid():
        values = form.series_values()
        try:
            availability_marks.change_series(series, from_day=form.cleaned_data["from_day"], **values)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, _("Series changed."))
            return redirect(f"{back}?month={form.cleaned_data['from_day']:%Y-%m}#availability")
    return render(
        request,
        "personnel/series_form.html",
        {
            "person": person,
            "series": series,
            "description": availability_marks.describe_series(series),
            "form": form,
            "availability_own": own,
            "back": back,
        },
    )


def _add_feed(request: HttpRequest, person: Person) -> None:
    """Link one more calendar from the form and read it at once (PER-022, PER-031)."""
    form = FeedLinkForm(request.POST)
    if not form.is_valid():
        messages.error(request, _form_errors(form))
        return
    try:
        feed = calendars.add_feed(person, form.cleaned_data["url"], form.cleaned_data["label"])
    except ValidationError as error:
        messages.error(request, _error_text(error))
        return
    # Read at once, so that the person sees whether the link works.
    if calendars.read_calendar(feed, force=True) is False:
        messages.warning(request, feed.error)
    else:
        messages.success(request, _("The calendar is linked."))


def _remove_feed(request: HttpRequest, person: Person, feed_pk: int) -> None:
    """Remove one linked calendar with its busy times (PER-031)."""
    calendars.remove_feed(get_object_or_404(person.calendar_feeds, pk=feed_pk))
    messages.success(request, _("The link to the calendar is removed."))


def _read_feed_now(request: HttpRequest, person: Person) -> None:
    """Read every linked calendar of the person now; a problem is told per calendar (PER-031)."""
    outcome = calendars.read_feeds(person, force=True)
    if outcome is True:
        messages.success(request, _("The calendar was read."))
    elif outcome is False:
        for feed in person.calendar_feeds.exclude(error=""):
            messages.error(request, f"{feed.name}: {feed.error}")


# --- The own profile (PER-021 to PER-023) ---------------------------------------------------------------------


#: The tab "Availability" of "My area" (UIX-026).
OWN_AVAILABILITY = reverse_lazy("personnel:own_availability")


@require_http_methods(["GET", "HEAD", "POST"])
def own_availability(request: HttpRequest) -> HttpResponse:
    """The tab "Availability" of "My area": the own calendar and the calendar links (PER-021 to PER-023, PER-028).

    ``POST`` colours or clears days, or enters a series. Needs no right on
    the personnel module: everybody enters their own availability.
    """
    person = _own_person(request)
    if request.method == "POST":
        return _back(OWN_AVAILABILITY, _mark(request, person), "availability")
    return render(
        request, "personnel/my_availability.html", {"person": person, **own_calendar_context(request, person)}
    )


@require_POST
def own_availability_remove(request: HttpRequest) -> HttpResponse:
    """Remove what one entered in a period (PER-021)."""
    person = _own_person(request)
    _remove(request, person)
    return _back(OWN_AVAILABILITY, calendar_place(request, request.POST), "availability")


def own_series(request: HttpRequest, series_pk: int) -> HttpResponse:
    """Change an own series from a day on (PER-028)."""
    return _series_page(request, _own_person(request), series_pk, back=OWN_AVAILABILITY, own=True)


@require_POST
def own_series_remove(request: HttpRequest, series_pk: int) -> HttpResponse:
    """Remove an own series, all of it or from a day on (PER-028)."""
    person = _own_person(request)
    _remove_series(request, person, series_pk)
    return _back(OWN_AVAILABILITY, calendar_place(request, request.POST), "availability")


@require_POST
def own_feed(request: HttpRequest) -> HttpResponse:
    """Link one more own calendar with busy times (PER-022, PER-031)."""
    _add_feed(request, _own_person(request))
    return redirect(f"{OWN_AVAILABILITY}#calendars")


@require_POST
def own_feed_remove(request: HttpRequest, feed_pk: int) -> HttpResponse:
    """Remove one of the own linked calendars (PER-031)."""
    _remove_feed(request, _own_person(request), feed_pk)
    return redirect(f"{OWN_AVAILABILITY}#calendars")


@require_POST
def own_calendar_sync(request: HttpRequest) -> HttpResponse:
    """Read the linked calendars and write the CalDAV calendar now (PER-022, PER-023, PER-031)."""
    person = _own_person(request)
    what = request.POST.get("what", "")
    if what in ("", "feed"):
        _read_feed_now(request, person)
    if what in ("", "caldav") and person.caldav_url:
        result = calendars.push_deployments(person, force=True, deadline=None)
        if result is not None and result.error:
            messages.error(request, result.error)
        elif result is not None:
            messages.success(
                request,
                _("Calendar compared: %(written)d written, %(deleted)d removed.")
                % {"written": result.written, "deleted": result.deleted},
            )
    return redirect(f"{OWN_AVAILABILITY}#calendars")


@require_POST
def own_caldav(request: HttpRequest) -> HttpResponse:
    """Set up, change or remove the own CalDAV calendar (PER-023)."""
    person = _own_person(request)
    form = CalDAVForm(request.POST)
    if not form.is_valid():
        messages.error(request, _form_errors(form))
        return redirect(f"{OWN_AVAILABILITY}#calendars")
    data = form.cleaned_data
    removing = bool(request.POST.get("remove"))
    if not removing and data["caldav_url"] and not data["caldav_password"] and not person.caldav_password_encrypted:
        messages.error(request, _("Enter the password for the calendar."))
        return redirect(f"{OWN_AVAILABILITY}#calendars")
    try:
        calendars.set_caldav(
            person,
            url="" if removing else data["caldav_url"],
            username=data["caldav_username"],
            password=data["caldav_password"] or None,
        )
    except ValidationError as error:
        messages.error(request, _error_text(error))
        return redirect(f"{OWN_AVAILABILITY}#calendars")
    if removing or not person.caldav_url:
        messages.success(request, _("Rentalars no longer writes into a calendar."))
        return redirect(f"{OWN_AVAILABILITY}#calendars")
    # Try at once, so that a wrong address or password shows now and not in half an hour.
    result = calendars.push_deployments(person, force=True, deadline=None)
    if result is not None and result.error:
        messages.warning(request, result.error)
    else:
        messages.success(request, _("Saved. Your deployments are written into the calendar."))
    return redirect(f"{OWN_AVAILABILITY}#calendars")


@require_POST
def own_subscription(request: HttpRequest) -> HttpResponse:
    """Create the subscription link of the own deployments, or a new one, or switch it off (PER-023)."""
    person = _own_person(request)
    if request.POST.get("remove"):
        calendars.revoke_calendar_token(person)
        messages.success(request, _("The subscription link is switched off."))
    else:
        renewing = bool(person.calendar_token)
        calendars.renew_calendar_token(person)
        messages.success(
            request,
            _("A new subscription link was created; the old one no longer works.")
            if renewing
            else _("The subscription link was created."),
        )
    return redirect(f"{OWN_AVAILABILITY}#calendars")


@require_safe
def own_deployments_ics(request: HttpRequest) -> HttpResponse:
    """The own deployments as an .ics file to download (PER-023)."""
    body, _etag = calendars.deployments_calendar(_own_person(request))
    response = HttpResponse(body, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{file_name("deployments", extension="ics")}"'
    return response


# --- Personnel planning (PER-021, PER-022) ----------------------------------------------------------------------


@module_required(Module.PERSONNEL)
def person_availability(request: HttpRequest, pk: int) -> HttpResponse:
    """The tab "Availability" of a person: the calendar and the linked calendars (PER-021, PER-022, PER-030, PER-031).

    The linked calendars show with their name, server and state; their
    addresses stay the person's secret (PER-022).
    """
    person = get_object_or_404(Person.objects.select_related("user"), pk=pk)
    editable = request_rights(request).can_write(Module.PERSONNEL) and not person.anonymised_at
    context = availability_context(request, person, editable=editable, own=False)
    context.update(
        {
            "person": person,
            "tab": "availability",
            "feeds": list(person.calendar_feeds.all()),
            "feed_form": FeedLinkForm(),
        }
    )
    return render(request, "personnel/person_availability.html", context)


def _planned_person(pk: int) -> Person:
    person = get_object_or_404(Person, pk=pk)
    if person.anonymised_at:
        raise PermissionDenied
    return person


@require_POST
@module_required(Module.PERSONNEL, Level.WRITE)
def person_availability_mark(request: HttpRequest, pk: int) -> HttpResponse:
    """Colour or clear days of a person's availability for them (PER-021)."""
    person = _planned_person(pk)
    return _back(reverse("personnel:person_availability", args=[pk]), _mark(request, person), "availability")


@require_POST
@module_required(Module.PERSONNEL, Level.WRITE)
def person_availability_remove(request: HttpRequest, pk: int) -> HttpResponse:
    """Remove what a person entered in a period (PER-021)."""
    person = _planned_person(pk)
    _remove(request, person)
    return _back(
        reverse("personnel:person_availability", args=[pk]), calendar_place(request, request.POST), "availability"
    )


@module_required(Module.PERSONNEL, Level.WRITE)
def person_series(request: HttpRequest, pk: int, series_pk: int) -> HttpResponse:
    """Change a series of a person from a day on (PER-028)."""
    person = _planned_person(pk)
    return _series_page(request, person, series_pk, back=reverse("personnel:person_availability", args=[pk]), own=False)


@require_POST
@module_required(Module.PERSONNEL, Level.WRITE)
def person_series_remove(request: HttpRequest, pk: int, series_pk: int) -> HttpResponse:
    """Remove a series of a person, all of it or from a day on (PER-028)."""
    person = _planned_person(pk)
    _remove_series(request, person, series_pk)
    return _back(
        reverse("personnel:person_availability", args=[pk]), calendar_place(request, request.POST), "availability"
    )


@require_POST
@module_required(Module.PERSONNEL, Level.WRITE)
def person_feed(request: HttpRequest, pk: int) -> HttpResponse:
    """Link one more calendar with busy times for a person, or read them all now (PER-022, PER-031)."""
    person = _planned_person(pk)
    if request.POST.get("read"):
        _read_feed_now(request, person)
    else:
        _add_feed(request, person)
    return redirect(reverse("personnel:person_availability", args=[pk]) + "#calendar")


@require_POST
@module_required(Module.PERSONNEL, Level.WRITE)
def person_feed_remove(request: HttpRequest, pk: int, feed_pk: int) -> HttpResponse:
    """Remove a linked calendar of a person with its busy times (PER-031)."""
    _remove_feed(request, _planned_person(pk), feed_pk)
    return redirect(reverse("personnel:person_availability", args=[pk]) + "#calendar")


# --- The subscription link, without login (PER-023) ----------------------------------------------------------------


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
    response = HttpResponse(_("Too many requests. Try again later."), status=429, content_type="text/plain")
    response["Retry-After"] = str(FEED_WINDOW_SECONDS)
    return response


def feed_failures_key(request: HttpRequest) -> str | None:
    """The cache key that counts the wrong calendar links of the client of a request; ``None`` without an address.

    PER-023, VFG-040 (review: one counter for everybody): counted per
    client address as the login counts it (``accounts.services.client_ip``).
    Behind NGINX on a socket ``REMOTE_ADDR`` is empty and the address is in
    ``X-Forwarded-For`` (``deploy/nginx/rentalars-proxy.conf``); keyed on
    ``REMOTE_ADDR`` alone, every client shared one counter, and one calendar
    program asking for a renewed link locked out every calendar. Without a
    known address nothing is counted, for the same reason – guessing 256
    random bits is pointless anyway. Shared by the subscription links of
    people and the calendar links of products, models and items: a wrong link
    of either kind counts, an unknown record as a wrong token.
    """
    import ipaddress

    from rentalars.accounts.services import client_ip

    try:
        address = ipaddress.ip_address(client_ip(request) or "")
    except ValueError:
        return None
    return f"rentalars:calendar-feed:failures:{address.compressed}"


def feed_refused(failures_key: str | None) -> bool:
    """Whether the client of this key had too many wrong links in :data:`FEED_WINDOW_SECONDS` (PER-023, VFG-040)."""
    return failures_key is not None and (cache.get(failures_key) or 0) >= FEED_FAILURES_PER_ADDRESS


def count_feed_failure(failures_key: str | None) -> None:
    """Count one wrong link of the client of this key; nothing without a known address (PER-023, VFG-040)."""
    if failures_key is not None:
        _count(failures_key)


@require_safe
def calendar_feed(request: HttpRequest, pk: int, token: str) -> HttpResponse:
    """The deployments of a person for calendar programs, with the secret token instead of a login (PER-023).

    Guessing is pointless (256 random bits, compared in constant time) and
    is slowed down anyway: a client address with many wrong links waits
    (:func:`feed_failures_key` – per client, so that the wrong links of
    others never block a correct one). A correct link that is read far more
    often than calendar programs do waits as well. An unchanged calendar is
    answered with "304 not modified".
    """
    failures_key = feed_failures_key(request)
    if feed_refused(failures_key):
        return _too_many()
    person = calendars.person_for_token(pk, token)
    if person is None:
        count_feed_failure(failures_key)
        return HttpResponse(_("Not found."), status=404, content_type="text/plain")
    if _count(f"rentalars:calendar-feed:readings:{person.pk}") > FEED_READINGS_PER_LINK:
        return _too_many()
    body, etag = calendars.deployments_calendar(person)
    if etag in request.headers.get("If-None-Match", ""):
        response = HttpResponse(status=304)
    else:
        response = HttpResponse(body, content_type="text/calendar; charset=utf-8")
        response["Content-Disposition"] = f'inline; filename="{file_name("deployments", extension="ics")}"'
    response["ETag"] = etag
    response["Cache-Control"] = "private, max-age=900"
    response["X-Robots-Tag"] = "noindex, nofollow"
    response["Referrer-Policy"] = "no-referrer"
    return response
