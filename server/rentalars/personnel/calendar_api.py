# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the availability calendar and the calendar links (PER-021 to PER-023, PER-031).

The endpoints hang below ``/people/{id}``; ``{id}`` may be ``me`` for the
caller's own person. Who may do what:

=====================================  ==========================  ===============================
endpoint                               the person themselves       others
=====================================  ==========================  ===============================
``availability-marks`` (list, colour,  yes                         read: personnel read;
change, remove, clear),                                            change: personnel write
``availability-periods``,
``availability-series``
``calendars`` (linked calendars:       yes                         read: personnel read, without
state in ``feeds``)                                                the addresses
``calendars/feeds`` (list, link,       yes                         list: personnel read; link and
remove linked calendars)                                           remove: personnel write; the
                                                                   addresses stay hidden
``calendars`` (CalDAV fields)          yes                         no
``calendars/subscription``             yes                         no
``calendars/sync``                     linked calendars and        linked calendars, personnel
                                       CalDAV                      write
``calendars/deployments`` (.ics)       yes                         no
=====================================  ==========================  ===============================

A read-only token changes nothing, not even the caller's own data.

A person may link several calendars (PER-031): they are the list
``feeds`` and the endpoints ``calendars/feeds``. The single link
(``availability_feed_url`` and its state in ``calendars``) is gone; sending
it is refused with a hint.
"""

from __future__ import annotations

import datetime
from typing import Any, ClassVar

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Level, Module
from rentalars.api.permissions import WritableCaller
from rentalars.core.i18n import file_name
from rentalars.personnel import calendars
from rentalars.personnel import marks as availability_marks
from rentalars.personnel.models import (
    AvailabilityMark,
    AvailabilityRepeat,
    AvailabilitySeries,
    AvailabilitySource,
    AvailabilityState,
    CalendarFeed,
    Person,
)
from rentalars.projects.access import person_of

#: The path parameter of the person, which may also be ``me``.
PERSON = OpenApiParameter(
    "id", str, OpenApiParameter.PATH, description="ID of the person, or `me` for the caller's own person."
)
MARK = OpenApiParameter("mark_pk", int, OpenApiParameter.PATH, description="ID of the mark.")
SERIES = OpenApiParameter("series_pk", int, OpenApiParameter.PATH, description="ID of the series.")
FEED = OpenApiParameter("feed_pk", int, OpenApiParameter.PATH, description="ID of the linked calendar.")


class AvailabilityMarkSerializer(serializers.ModelSerializer):
    """A period the person marked green, yellow or red, or a busy time of the linked calendar (PER-021, PER-022).

    ``entered_at``: when the statement was made – an own entry when it was
    entered, a busy time when the appointment was last changed in the
    calendar (``null`` if it does not say). Where the two meet, the newer
    counts (PER-027). ``series``: the series the entry belongs to (PER-028).
    """

    class Meta:
        model = AvailabilityMark
        fields = ["id", "person", "start", "end", "state", "note", "source", "entered_at", "series"]
        read_only_fields = fields


class AvailabilityPeriodSerializer(serializers.Serializer):
    """The availability that counts in a stretch of time (PER-027): one at any moment."""

    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    state = serializers.ChoiceField(choices=AvailabilityState.choices)
    source = serializers.ChoiceField(choices=AvailabilitySource.choices)
    note = serializers.CharField()
    marks = serializers.ListField(
        child=serializers.IntegerField(), source="mark_ids", help_text="The own entries shown; empty for busy times."
    )
    series = serializers.ListField(child=serializers.IntegerField(), source="series_ids")


class AvailabilitySeriesInputSerializer(serializers.Serializer):
    """An availability that repeats (PER-028); the first occurrence is ``first_day`` to ``last_day``."""

    state = serializers.ChoiceField(choices=AvailabilityState.choices)
    note = serializers.CharField(max_length=250, required=False, allow_blank=True, default="")
    first_day = serializers.DateField()
    last_day = serializers.DateField(required=False, help_text="Last day of the first occurrence; default: the first.")
    start_time = serializers.TimeField(
        required=False, allow_null=True, default=None, help_text="With end_time: these times on each day."
    )
    end_time = serializers.TimeField(required=False, allow_null=True, default=None)
    repeat = serializers.ChoiceField(choices=AvailabilityRepeat.choices)
    interval = serializers.IntegerField(min_value=1, max_value=365, required=False, default=1)
    weekdays = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6),
        required=False,
        default=list,
        help_text="Weekly: the weekdays, Monday = 0; empty: the weekday of the first day.",
    )
    until = serializers.DateField(required=False, allow_null=True, default=None)
    count = serializers.IntegerField(min_value=1, max_value=366, required=False, allow_null=True, default=None)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """The last day defaults to the first day."""
        if "first_day" in attrs and not attrs.get("last_day"):
            attrs["last_day"] = attrs["first_day"]
        return attrs


class AvailabilitySeriesChangeSerializer(AvailabilitySeriesInputSerializer):
    """Change a series from a day on (PER-028); every field is optional."""

    from_day = serializers.DateField(required=False, help_text="The change counts from this day on; default: today.")


class AvailabilitySeriesSerializer(serializers.Serializer):
    """A series as it is stored, with its rule in words (PER-028)."""

    id = serializers.IntegerField()
    person = serializers.IntegerField(source="person_id")
    state = serializers.CharField()
    note = serializers.CharField()
    first_day = serializers.DateField()
    last_day = serializers.DateField()
    start_time = serializers.TimeField(allow_null=True)
    end_time = serializers.TimeField(allow_null=True)
    repeat = serializers.CharField()
    interval = serializers.IntegerField()
    weekdays = serializers.ListField(child=serializers.IntegerField(), source="weekday_numbers")
    until = serializers.DateField(allow_null=True)
    count = serializers.IntegerField(allow_null=True)
    description = serializers.SerializerMethodField()

    def get_description(self, series: AvailabilitySeries) -> str:
        """The rule in words, in the language of the request."""
        return availability_marks.describe_series(series)


class AvailabilityMarkInputSerializer(serializers.Serializer):
    """Colour a period; what the person entered in it before is replaced (PER-021)."""

    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    state = serializers.ChoiceField(choices=AvailabilityState.choices)
    note = serializers.CharField(max_length=250, required=False, allow_blank=True, default="")


class AvailabilityMarkChangeSerializer(serializers.Serializer):
    """Change period, colour or note of an own mark (PER-021)."""

    start = serializers.DateTimeField(required=False)
    end = serializers.DateTimeField(required=False)
    state = serializers.ChoiceField(choices=AvailabilityState.choices, required=False)
    note = serializers.CharField(max_length=250, required=False, allow_blank=True)


class PeriodSerializer(serializers.Serializer):
    """A period whose own marks are removed (PER-021)."""

    start = serializers.DateTimeField()
    end = serializers.DateTimeField()


class CalendarFeedSerializer(serializers.Serializer):
    """A linked calendar of a person (PER-022, PER-031); ``url`` only for the person themselves."""

    id = serializers.IntegerField(read_only=True)
    url = serializers.CharField(
        max_length=500,
        help_text="Address of an .ics calendar whose busy times count as not available. "
        "Only the person sees it; others get `host`.",
    )
    label = serializers.CharField(
        max_length=80, required=False, allow_blank=True, default="", help_text="A name to tell the calendars apart."
    )
    host = serializers.CharField(read_only=True, help_text="Only the server of the address.")
    checked_at = serializers.DateTimeField(read_only=True, allow_null=True, help_text="When it was last read.")
    error = serializers.CharField(read_only=True, help_text="What went wrong at the last reading; empty if nothing.")


def feed_document(feed: CalendarFeed, *, own: bool) -> dict[str, Any]:
    """A linked calendar as the API shows it; the address only to the person (PER-022, PER-031)."""
    document: dict[str, Any] = {
        "id": feed.pk,
        "label": feed.label,
        "host": feed.host,
        "checked_at": feed.checked_at,
        "error": feed.error,
    }
    if own:
        document["url"] = feed.url
    return document


class CalendarSettingsSerializer(serializers.Serializer):
    """The calendar links of a person (PER-022, PER-023, PER-031); every field is optional when changing.

    The linked calendars are listed in ``feeds``; they are linked and
    removed with ``calendars/feeds``.
    """

    feeds = CalendarFeedSerializer(many=True, read_only=True)
    caldav_url = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        help_text="Calendar (or server) the deployments are written into; empty switches writing off. Own person only.",
    )
    caldav_username = serializers.CharField(max_length=200, required=False, allow_blank=True)
    caldav_password = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        trim_whitespace=False,
        help_text="Stored encrypted and never delivered; leave out to keep the stored one.",
    )
    caldav_password_set = serializers.BooleanField(read_only=True)
    caldav_synced_at = serializers.DateTimeField(read_only=True, allow_null=True)
    caldav_error = serializers.CharField(read_only=True)
    subscription_url = serializers.CharField(read_only=True, help_text="The secret subscription link; own person only.")


class CalendarSyncSerializer(serializers.Serializer):
    """What to do now: read the linked calendars, write the CalDAV calendar, or both (default)."""

    what = serializers.ChoiceField(choices=["all", "feed", "caldav"], required=False, default="all")


def calendar_document(person: Person, *, own: bool) -> dict[str, Any]:
    """The calendar links of a person as the API shows them; secrets only to the person (PER-022, PER-023, PER-031)."""
    document: dict[str, Any] = {"feeds": [feed_document(feed, own=own) for feed in person.calendar_feeds.all()]}
    if own:
        document.update(
            {
                "caldav_url": person.caldav_url,
                "caldav_username": person.caldav_username,
                "caldav_password_set": bool(person.caldav_password_encrypted),
                "caldav_synced_at": person.caldav_synced_at,
                "caldav_error": person.caldav_error,
                "subscription_url": calendars.subscription_url(person),
            }
        )
    return document


class PersonCalendarActions:
    """The endpoints of PER-021 to PER-023 for :class:`~rentalars.personnel.api.PersonViewSet`.

    They decide about access themselves (see the module description): the
    person needs no right on the personnel module for their own data.
    """

    CALENDAR_ACTIONS: ClassVar[frozenset[str]] = frozenset(
        {
            "availability_marks",
            "availability_mark",
            "availability_clear",
            "availability_periods",
            "availability_series_list",
            "availability_series_detail",
            "calendars",
            "calendar_feeds",
            "calendar_feed",
            "calendar_subscription",
            "calendar_sync",
            "deployments_calendar",
        }
    )

    request: Any
    kwargs: dict[str, Any]
    rights: Any

    def get_permissions(self) -> list[Any]:
        """A login suffices to reach these endpoints; :meth:`_calendar_person` checks the rest."""
        if getattr(self, "action", None) in self.CALENDAR_ACTIONS:
            return [IsAuthenticated(), WritableCaller()]
        return super().get_permissions()  # type: ignore[misc]

    def _calendar_person(self, *, write: bool, own_only: bool = False) -> tuple[Person, bool]:
        """Return the person of the address and whether it is the caller's own.

        Raises:
            NotFound: No such person (or ``me`` without a person).
            PermissionDenied: The caller may not do this.
        """
        key = str(self.kwargs.get("pk", ""))
        own = person_of(self.request.user)
        if key == "me" or (own is not None and key == str(own.pk)):
            if own is None:
                raise NotFound
            token = getattr(self.request, "auth", None)
            if write and getattr(token, "read_only", False):
                raise PermissionDenied
            return own, True
        if not key.isdigit():
            raise NotFound
        if own_only or not self.rights.has_level(Module.PERSONNEL, Level.WRITE if write else Level.READ):
            raise PermissionDenied
        return get_object_or_404(Person, pk=int(key)), False

    # --- Availability (PER-021) -------------------------------------------------------------------

    @extend_schema(
        methods=["get"],
        parameters=[
            PERSON,
            OpenApiParameter("from", str, description="Begin of the period, ISO 8601; default: a month ago"),
            OpenApiParameter("to", str, description="End of the period, ISO 8601; default: a year ahead"),
        ],
        responses=AvailabilityMarkSerializer(many=True),
    )
    @extend_schema(
        methods=["post"],
        parameters=[PERSON],
        request=AvailabilityMarkInputSerializer,
        responses={201: AvailabilityMarkSerializer},
    )
    @action(detail=True, methods=["get", "post"], url_path="availability-marks")
    def availability_marks(self, request: Request, pk: str | None = None) -> Response:
        """The availability of a person: green, yellow and red periods and the busy times of the linked calendar.

        ``POST`` colours a period (PER-021). Whatever the person entered in
        it before is cut back or replaced. The busy times of the linked
        calendar (``source: feed``) are not touched. These are the stored
        entries; ``availability-periods`` gives what counts (PER-027).
        """
        if request.method == "POST":
            person, _own = self._calendar_person(write=True)
            serializer = AvailabilityMarkInputSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
            mark = availability_marks.mark_period(person, data["start"], data["end"], data["state"], data["note"])
            return Response(AvailabilityMarkSerializer(mark).data, status=status.HTTP_201_CREATED)
        person, _own = self._calendar_person(write=False)
        start, end = self._span(request)
        rows = person.availability_marks.filter(start__lt=end, end__gt=start).order_by("start", "pk")[:5000]
        return Response(AvailabilityMarkSerializer(rows, many=True).data)

    @extend_schema(
        methods=["patch"],
        parameters=[PERSON, MARK],
        request=AvailabilityMarkChangeSerializer,
        responses=AvailabilityMarkSerializer,
    )
    @extend_schema(methods=["delete"], parameters=[PERSON, MARK], responses={204: None})
    @action(detail=True, methods=["patch", "delete"], url_path=r"availability-marks/(?P<mark_pk>\d+)")
    def availability_mark(self, request: Request, pk: str | None = None, mark_pk: str | None = None) -> Response:
        """Change or remove an own mark (PER-021); busy times of the linked calendar cannot be changed."""
        person, _own = self._calendar_person(write=True)
        mark = get_object_or_404(person.availability_marks, pk=mark_pk)
        if request.method == "DELETE":
            availability_marks.delete_mark(mark)
            return Response(status=status.HTTP_204_NO_CONTENT)
        serializer = AvailabilityMarkChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        changed = availability_marks.change_mark(mark, **serializer.validated_data)
        return Response(AvailabilityMarkSerializer(changed).data)

    @extend_schema(
        parameters=[PERSON],
        request=PeriodSerializer,
        responses={200: inline_serializer("AvailabilityCleared", {"changed": serializers.IntegerField()})},
    )
    @action(detail=True, methods=["post"], url_path="availability-marks/clear")
    def availability_clear(self, request: Request, pk: str | None = None) -> Response:
        """Remove what the person entered in a period (PER-021); marks reaching out of it are cut back."""
        person, _own = self._calendar_person(write=True)
        serializer = PeriodSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        changed = availability_marks.clear_period(
            person, serializer.validated_data["start"], serializer.validated_data["end"]
        )
        return Response({"changed": changed})

    def _span(self, request: Request) -> tuple[datetime.datetime, datetime.datetime]:
        """The period of ``from`` and ``to``; by default a month back and a year ahead."""
        from rentalars.personnel.api import _moment

        now = timezone.now()
        start = _moment(request.query_params["from"], "from") if request.query_params.get("from") else None
        end = _moment(request.query_params["to"], "to") if request.query_params.get("to") else None
        start = start or now - datetime.timedelta(days=31)
        end = end or now + datetime.timedelta(days=366)
        if end <= start:
            raise ValidationError({"to": _("The end must be after the start.")})
        return start, end

    @extend_schema(
        parameters=[
            PERSON,
            OpenApiParameter("from", str, description="Begin of the period, ISO 8601; default: a month ago"),
            OpenApiParameter("to", str, description="End of the period, ISO 8601; default: a year ahead"),
        ],
        responses=AvailabilityPeriodSerializer(many=True),
    )
    @action(detail=True, methods=["get"], url_path="availability-periods")
    def availability_periods(self, request: Request, pk: str | None = None) -> Response:
        """The availability that counts, one at any moment (PER-027).

        Where an own entry and a busy time of the linked calendar meet, the
        newer statement counts – the own entry by when it was entered, the
        busy time by when the appointment was last changed; without that
        date the stricter one. Busy times that overlap or touch are one
        period, and so are neighbouring own entries of the same colour and
        note. Periods reaching over the edges of the span are not cut.
        """
        person, _own = self._calendar_person(write=False)
        start, end = self._span(request)
        periods = availability_marks.effective_periods([person.pk], start, end).get(person.pk, [])
        return Response(AvailabilityPeriodSerializer(periods, many=True).data)

    @extend_schema(methods=["get"], parameters=[PERSON], responses=AvailabilitySeriesSerializer(many=True))
    @extend_schema(
        methods=["post"],
        parameters=[PERSON],
        request=AvailabilitySeriesInputSerializer,
        responses={201: AvailabilitySeriesSerializer},
    )
    @action(detail=True, methods=["get", "post"], url_path="availability-series")
    def availability_series_list(self, request: Request, pk: str | None = None) -> Response:
        """The series of a person (PER-028); ``POST`` enters a new one and paints its occurrences.

        Daily every ``interval`` days, weekly on ``weekdays`` every
        ``interval`` weeks, monthly on the same day every ``interval``
        months; until ``until`` or ``count`` times, at most a year ahead.
        Each occurrence replaces what was entered then, like any entry.
        """
        if request.method == "POST":
            person, _own = self._calendar_person(write=True)
            serializer = AvailabilitySeriesInputSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            series = availability_marks.create_series(person, **serializer.validated_data)
            return Response(AvailabilitySeriesSerializer(series).data, status=status.HTTP_201_CREATED)
        person, _own = self._calendar_person(write=False)
        return Response(AvailabilitySeriesSerializer(person.availability_series.all(), many=True).data)

    @extend_schema(methods=["get"], parameters=[PERSON, SERIES], responses=AvailabilitySeriesSerializer)
    @extend_schema(
        methods=["patch"],
        parameters=[PERSON, SERIES],
        request=AvailabilitySeriesChangeSerializer,
        responses=AvailabilitySeriesSerializer,
    )
    @extend_schema(
        methods=["delete"],
        parameters=[
            PERSON,
            SERIES,
            OpenApiParameter("from", str, description="Remove from this day on (YYYY-MM-DD); default: all"),
        ],
        responses={204: None},
    )
    @action(detail=True, methods=["get", "patch", "delete"], url_path=r"availability-series/(?P<series_pk>\d+)")
    def availability_series_detail(
        self, request: Request, pk: str | None = None, series_pk: str | None = None
    ) -> Response:
        """One series (PER-028): ``PATCH`` changes it from a day on, ``DELETE`` removes it, all or from a day on.

        A change counts from ``from_day`` (default today): what lies before
        stays, the occurrences from then on are painted anew.
        """
        person, _own = self._calendar_person(write=request.method != "GET")
        series = get_object_or_404(person.availability_series, pk=series_pk)
        if request.method == "GET":
            return Response(AvailabilitySeriesSerializer(series).data)
        if request.method == "DELETE":
            text = request.query_params.get("from", "")
            from_day = parse_date(text) if text else None
            if text and from_day is None:
                raise ValidationError({"from": _("Enter a valid date.")})
            availability_marks.remove_series(series, from_day=from_day)
            return Response(status=status.HTTP_204_NO_CONTENT)
        serializer = AvailabilitySeriesChangeSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        from_day = values.pop("from_day", None)
        changed = availability_marks.change_series(series, from_day=from_day, **values)
        return Response(AvailabilitySeriesSerializer(changed).data)

    # --- Calendars (PER-022, PER-023) ---------------------------------------------------------------

    @extend_schema(methods=["get"], parameters=[PERSON], responses=CalendarSettingsSerializer)
    @extend_schema(
        methods=["patch"], parameters=[PERSON], request=CalendarSettingsSerializer, responses=CalendarSettingsSerializer
    )
    @action(detail=True, methods=["get", "patch"], url_path="calendars")
    def calendars(self, request: Request, pk: str | None = None) -> Response:
        """The calendar links of a person: the linked calendars with busy times, CalDAV, the subscription link.

        ``feeds`` are the linked calendars (PER-031); they are linked and
        removed with ``calendars/feeds``, and others than the person never
        see their addresses. ``PATCH`` changes the CalDAV calendar (the
        person only); it is used from the next run on (within a minute) –
        call ``calendars/sync`` to try it at once.
        """
        if request.method == "GET":
            person, own = self._calendar_person(write=False)
            return Response(calendar_document(person, own=own))
        person, own = self._calendar_person(write=True)
        if "availability_feed_url" in request.data:
            # The single link; a person may link several calendars (PER-031).
            raise ValidationError(
                {"availability_feed_url": _("Linked calendars are added and removed with calendars/feeds.")}
            )
        serializer = CalendarSettingsSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        caldav_fields = {"caldav_url", "caldav_username", "caldav_password"} & set(data)
        if caldav_fields and not own:
            raise PermissionDenied
        if caldav_fields:
            url = data.get("caldav_url", person.caldav_url)
            if url and not data.get("caldav_password") and not person.caldav_password_encrypted:
                raise ValidationError({"caldav_password": _("Enter the password for the calendar.")})
            calendars.set_caldav(
                person,
                url=url,
                username=data.get("caldav_username", person.caldav_username),
                password=data.get("caldav_password") or None,
            )
        return Response(calendar_document(person, own=own))

    @extend_schema(methods=["get"], parameters=[PERSON], responses=CalendarFeedSerializer(many=True))
    @extend_schema(
        methods=["post"], parameters=[PERSON], request=CalendarFeedSerializer, responses={201: CalendarFeedSerializer}
    )
    @action(detail=True, methods=["get", "post"], url_path="calendars/feeds")
    def calendar_feeds(self, request: Request, pk: str | None = None) -> Response:
        """The linked calendars of a person (PER-022, PER-031); ``POST`` links one more.

        Each is read every 30 minutes; their busy times together count as
        "not available" (one layer, PER-027). A new calendar is read with the
        next run (within a minute); call ``calendars/sync`` to read it at
        once. At most ten per person; the same address only once. Others
        than the person need personnel write to link one and never see the
        addresses (``url``), only ``host`` and ``label``.
        """
        if request.method == "POST":
            person, own = self._calendar_person(write=True)
            serializer = CalendarFeedSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            feed = calendars.add_feed(person, serializer.validated_data["url"], serializer.validated_data["label"])
            return Response(feed_document(feed, own=own), status=status.HTTP_201_CREATED)
        person, own = self._calendar_person(write=False)
        return Response([feed_document(feed, own=own) for feed in person.calendar_feeds.all()])

    @extend_schema(methods=["delete"], parameters=[PERSON, FEED], responses={204: None})
    @action(detail=True, methods=["delete"], url_path=r"calendars/feeds/(?P<feed_pk>\d+)")
    def calendar_feed(self, request: Request, pk: str | None = None, feed_pk: str | None = None) -> Response:
        """Remove a linked calendar with the busy times taken from it (PER-031)."""
        person, _own = self._calendar_person(write=True)
        calendars.remove_feed(get_object_or_404(person.calendar_feeds, pk=feed_pk))
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(methods=["post"], parameters=[PERSON], request=None, responses=CalendarSettingsSerializer)
    @extend_schema(methods=["delete"], parameters=[PERSON], responses={204: None})
    @action(detail=True, methods=["post", "delete"], url_path="calendars/subscription")
    def calendar_subscription(self, request: Request, pk: str | None = None) -> Response:
        """Create the secret subscription link of the own deployments, or a new one (``POST``); ``DELETE`` ends it.

        The link works without login; a new link ends the old one at once (PER-023).
        """
        person, _own = self._calendar_person(write=True, own_only=True)
        if request.method == "DELETE":
            calendars.revoke_calendar_token(person)
            return Response(status=status.HTTP_204_NO_CONTENT)
        calendars.renew_calendar_token(person)
        return Response(calendar_document(person, own=True))

    @extend_schema(
        parameters=[PERSON],
        request=CalendarSyncSerializer,
        responses={
            200: inline_serializer(
                "CalendarSync",
                {
                    "feed": serializers.CharField(allow_null=True),
                    "feeds": CalendarFeedSerializer(many=True),
                    "caldav": serializers.DictField(allow_null=True),
                },
            )
        },
    )
    @action(detail=True, methods=["post"], url_path="calendars/sync")
    def calendar_sync(self, request: Request, pk: str | None = None) -> Response:
        """Read the linked calendars and write the CalDAV calendar now instead of waiting for the next run.

        ``feed`` is ``read`` (all were read), ``failed`` (at least one could
        not be read) or ``null`` (nothing linked); ``feeds`` are the linked
        calendars afterwards, with the problem of each in ``error`` (PER-031).
        ``caldav`` tells what was written, or the problem (own person only).
        """
        person, own = self._calendar_person(write=True)
        serializer = CalendarSyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        what = serializer.validated_data["what"]
        if what == "caldav" and not own:
            raise PermissionDenied
        feed = None
        if what in ("all", "feed"):
            outcome = calendars.read_feeds(person, force=True)
            feed = {True: "read", False: "failed"}.get(outcome)
        caldav = None
        if own and what in ("all", "caldav") and person.caldav_url:
            result = calendars.push_deployments(person, force=True)
            if result is not None:
                caldav = {
                    "written": result.written,
                    "deleted": result.deleted,
                    "unchanged": result.unchanged,
                    "error": result.error,
                }
        feeds = [feed_document(item, own=own) for item in person.calendar_feeds.all()]
        return Response({"feed": feed, "feeds": feeds, "caldav": caldav})

    @extend_schema(parameters=[PERSON], responses={(200, "text/calendar"): bytes})
    @action(detail=True, methods=["get"], url_path="calendars/deployments")
    def deployments_calendar(self, request: Request, pk: str | None = None) -> HttpResponse:
        """The own deployments as an .ics calendar file (PER-023)."""
        person, _own = self._calendar_person(write=False, own_only=True)
        body, _etag = calendars.deployments_calendar(person)
        response = HttpResponse(body, content_type="text/calendar; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{file_name("deployments", extension="ics")}"'
        return response
