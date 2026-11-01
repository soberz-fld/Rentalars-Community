# SPDX-License-Identifier: GPL-3.0-or-later
"""Calendars of a person: busy times in, deployments out (PER-022, PER-023; the feed of PER-017).

Three ways between Rentalars and the calendars people keep anyway:

Linked calendars (PER-022, PER-031)
    A person – or personnel planning for them – enters the addresses of
    .ics calendars, typically the private links of Google, Outlook or iCloud
    calendars (:class:`~rentalars.personnel.models.CalendarFeed`). Rentalars
    reads each every :data:`FEED_INTERVAL` and turns every busy appointment
    of the past month and the coming half year into a red mark
    (:class:`~rentalars.personnel.models.AvailabilityMark`, source "feed");
    repeating appointments are unfolded. Free (transparent) and cancelled
    appointments are left out, and so are the titles: planning learns
    *that* the person is busy, not *why*.

    The busy times of all calendars of a person are **one layer** ("busy in
    the linked calendar"): each mark belongs to its calendar, and a
    successful reading of a calendar replaces the marks of that calendar
    only. So the layer is always the union of the last good reading of every
    calendar: a calendar that cannot be read keeps its last busy times, notes
    the problem, and leaves those of the others alone. Overlapping busy times
    of different calendars are joined into one block when shown (PER-027,
    :func:`rentalars.personnel.marks.resolve`). Each mark keeps when its
    appointment was last changed: where it meets an own entry, the newer
    statement counts.

Deployments as a calendar (PER-023)
    :func:`deployments_calendar` writes the person's own crew lines as an
    .ics file – for downloading, and behind a secret subscription link
    (:func:`subscription_url`) that calendar programs read without a login.
    It holds what the person sees of a deployment anyway (AUT-023): job
    function, project number and name, place, meeting point, times and the
    note for the crew – no customer, no prices.

CalDAV (PER-023)
    Rentalars often runs on internal servers that phones cannot reach. It
    can therefore write the deployments into a calendar on the internet
    (Nextcloud, iCloud, mailbox.org, Posteo …): one event per crew line with
    a stable UID, written only when it changed (:class:`CalendarPush`
    remembers a digest and the ETag of each), and deleted when the
    deployment is gone. A change of a crew line marks its person "due"
    (:func:`crew_line_changed`); the periodic run writes within a minute,
    and every :data:`PUSH_INTERVAL` anyway.

The periodic run is :func:`run_due`, called every minute by the background
timer (``manage.py run_jobs``) and by hand with ``manage.py sync_calendars``.
It never raises: one person's broken calendar must not stop the others, nor
the other background tasks.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any, NamedTuple
from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from rentalars.core.crypto import SecretUnreadableError, decrypt_secret, encrypt_secret
from rentalars.personnel.calendar_client import CalDAVCalendar, CalendarHttpError, fetch_calendar, normalise_url
from rentalars.personnel.models import (
    AvailabilityMark,
    AvailabilitySource,
    AvailabilityState,
    CalendarFeed,
    CalendarPush,
    Person,
)

logger = logging.getLogger(__name__)

#: How often each linked calendar is read (PER-022, PER-031).
FEED_INTERVAL = datetime.timedelta(minutes=30)
#: How often the CalDAV calendar is compared even without a change of a crew line (PER-023).
PUSH_INTERVAL = datetime.timedelta(minutes=30)
#: Which appointments of a linked calendar count: the past month and the coming half year.
FEED_PAST = datetime.timedelta(days=31)
FEED_FUTURE = datetime.timedelta(days=183)
#: At most so many busy periods are kept from one calendar.
FEED_MAX_MARKS = 3000
#: Deployments in the calendar files: from this long ago on, and all coming ones.
DEPLOYMENTS_PAST = datetime.timedelta(days=60)
#: After so many failures in a row the person is told – once (about three hours at the intervals above).
FAILURES_BEFORE_NOTICE = 6
#: The periodic run starts no new reading or writing after this many seconds; the rest is due next minute.
RUN_BUDGET_SECONDS = 40


def _installation_language() -> Any:
    """Texts that are stored – errors, notifications – are written in the language of the installation.

    They are read later by whoever opens the page; the periodic run has no
    language of its own at all.
    """
    return translation.override(settings.LANGUAGE_CODE)


def _short(text: str) -> str:
    return text[:250]


# --- The linked calendar (PER-022) -------------------------------------------------------------------


def _as_moment(value: Any, *, zone: Any) -> datetime.datetime:
    """A start or end of an appointment as an aware moment; a day means its local midnight."""
    if isinstance(value, datetime.datetime):
        return value if timezone.is_aware(value) else timezone.make_aware(value, zone)
    return timezone.make_aware(datetime.datetime.combine(value, datetime.time()), zone)


class BusyPeriod(NamedTuple):
    """A busy appointment of a linked calendar (PER-022)."""

    start: datetime.datetime
    end: datetime.datetime
    #: The UID of the appointment with its start: repetitions share their UID.
    uid: str
    #: When the appointment was last changed (``LAST-MODIFIED``, else ``CREATED``), never later than
    #: now; ``None`` if the calendar does not say (PER-027).
    changed: datetime.datetime | None


def _changed(event: Any, *, now: datetime.datetime) -> datetime.datetime | None:
    """When an appointment was last changed, as the calendar says (PER-027).

    ``DTSTAMP`` does not count: many calendars set it to the moment the
    file was made, which would make every appointment brand-new.
    """
    for name in ("LAST-MODIFIED", "CREATED"):
        value = event.get(name)
        moment = getattr(value, "dt", None)
        if moment is None:
            continue
        if not isinstance(moment, datetime.datetime):
            moment = datetime.datetime.combine(moment, datetime.time())
        if timezone.is_naive(moment):
            moment = timezone.make_aware(moment, datetime.UTC)
        return min(moment, now)
    return None


def busy_periods(data: bytes, *, now: datetime.datetime | None = None) -> list[BusyPeriod]:
    """Find the busy appointments in an .ics calendar (PER-022).

    Busy is every appointment (VEVENT) that is not marked free
    (``TRANSP:TRANSPARENT``, Outlook's ``X-MICROSOFT-CDO-BUSYSTATUS:FREE``) and
    not cancelled – appointments over whole days and with times alike.
    Repeating appointments are unfolded for the period of
    :data:`FEED_PAST` before and :data:`FEED_FUTURE` after ``now``.

    Returns:
        A :class:`BusyPeriod` for each busy appointment, by start; at most
        :data:`FEED_MAX_MARKS`.

    Raises:
        ValueError: The data is no calendar.
    """
    import icalendar
    import recurring_ical_events

    now = now or timezone.now()
    try:
        calendar = icalendar.Calendar.from_ical(data)
    except Exception as error:  # the parser raises many kinds of errors for broken input
        raise ValueError("not a calendar") from error
    if getattr(calendar, "name", "") != "VCALENDAR":
        raise ValueError("not a calendar")
    zone = timezone.get_current_timezone()
    try:
        events = recurring_ical_events.of(calendar, skip_bad_series=True).between(now - FEED_PAST, now + FEED_FUTURE)
    except Exception as error:  # a broken repetition rule or time zone
        raise ValueError("unreadable appointments") from error
    periods = []
    for event in events:
        if str(event.get("TRANSP", "OPAQUE")).upper() == "TRANSPARENT":
            continue
        if str(event.get("X-MICROSOFT-CDO-BUSYSTATUS", "")).upper() == "FREE":
            continue
        if str(event.get("STATUS", "")).upper() == "CANCELLED":
            continue
        begin_property = event.get("DTSTART")
        if begin_property is None:
            continue
        begin_value = begin_property.dt
        end_property = event.get("DTEND")
        if end_property is not None:
            end_value = end_property.dt
        elif event.get("DURATION") is not None:
            end_value = begin_value + event.get("DURATION").dt
        elif isinstance(begin_value, datetime.datetime):
            continue  # a moment without length blocks nothing
        else:
            end_value = begin_value + datetime.timedelta(days=1)
        start, end = _as_moment(begin_value, zone=zone), _as_moment(end_value, zone=zone)
        if end <= start:
            continue
        uid = str(event.get("UID", ""))[:200]
        # A repeated appointment shares its UID with all its repetitions; the start tells them apart.
        periods.append(BusyPeriod(start, end, f"{uid}#{start.isoformat()}"[:255], _changed(event, now=now)))
    periods.sort(key=lambda period: (period.start, period.end, period.uid))
    return periods[:FEED_MAX_MARKS]


def _claim_feed(feed: CalendarFeed, *, force: bool) -> bool:
    """Mark the reading of a calendar as started, so that two runs never read the same calendar at once."""
    now = timezone.now()
    due = Q(checked_at__isnull=True) | Q(checked_at__lte=now - FEED_INTERVAL)
    if force:
        due = Q(checked_at__isnull=True) | Q(checked_at=feed.checked_at)
    claimed = CalendarFeed.objects.filter(due, pk=feed.pk).update(checked_at=now)
    feed.checked_at = now
    return bool(claimed)


def read_calendar(feed: CalendarFeed, *, force: bool = False) -> bool | None:
    """Read one linked calendar and replace the busy times taken from it (PER-022, PER-031).

    Args:
        feed: The calendar.
        force: Read now even if the last reading is recent ("read now").

    Returns:
        ``True`` if the reading succeeded, ``False`` if it failed, ``None``
        if there was nothing to read (not due, or another run is reading it
        right now). A failure is stored in ``feed.error`` – a short text
        without the address or anything the server answered – and the busy
        times of the last good reading of this calendar stay; those of the
        other calendars of the person are not touched either way.
    """
    url = feed.url
    if not url or not _claim_feed(feed, force=force):
        return None
    with _installation_language():
        try:
            data = fetch_calendar(url)
            try:
                periods = busy_periods(data)
            except ValueError:
                raise CalendarHttpError(_("The address does not deliver a calendar in the .ics format.")) from None
        except CalendarHttpError as error:
            _feed_failed(feed, str(error))
            return False
        except Exception:  # never let one calendar break the run
            logger.exception("Reading linked calendar %s of person %s failed.", feed.pk, feed.person_id)
            _feed_failed(feed, _("The calendar could not be read."))
            return False
    with transaction.atomic():
        # The row lock lets two readings of the same calendar follow each other instead of mixing.
        locked = CalendarFeed.objects.select_for_update().filter(pk=feed.pk, url=url).first()
        if locked is None:
            return None  # the calendar was removed meanwhile
        AvailabilityMark.objects.filter(feed=feed).delete()
        # Older busy times without their calendar would never be replaced otherwise.
        AvailabilityMark.objects.filter(
            person_id=feed.person_id, source=AvailabilitySource.FEED, feed__isnull=True
        ).delete()
        AvailabilityMark.objects.bulk_create(
            [
                AvailabilityMark(
                    person_id=feed.person_id,
                    start=period.start,
                    end=period.end,
                    state=AvailabilityState.UNAVAILABLE,
                    source=AvailabilitySource.FEED,
                    feed=feed,
                    # PER-031: the UID is unique within its calendar; the ID of the calendar keeps it unique for the person.
                    feed_uid=f"{feed.pk}:{period.uid}"[:255],
                    entered_at=period.changed,
                )
                for period in periods
            ],
            batch_size=500,
        )
        CalendarFeed.objects.filter(pk=feed.pk).update(error="", failures=0)
    feed.error, feed.failures = "", 0
    return True


def read_feeds(person: Person, *, force: bool = False) -> bool | None:
    """Read the linked calendars of a person – all of them with ``force`` ("read now", PER-022, PER-031).

    Returns:
        ``True`` if every calendar read was read, ``False`` if one of them
        failed (its problem is in its ``error``), ``None`` if nothing was
        read.
    """
    outcomes = [read_calendar(feed, force=force) for feed in person.calendar_feeds.all()]
    if False in outcomes:
        return False
    return True if True in outcomes else None


def _feed_failed(feed: CalendarFeed, message: str) -> None:
    message = _short(message)
    CalendarFeed.objects.filter(pk=feed.pk).update(error=message, failures=F("failures") + 1)
    feed.refresh_from_db(fields=["failures"])
    feed.error = message
    if feed.failures == FAILURES_BEFORE_NOTICE:
        title = (
            _("Your linked calendar “%(name)s” cannot be read") % {"name": feed.name}
            if feed.name
            else _("Your linked calendar cannot be read")
        )
        _tell(feed.person, title, message)


def _checked_url(url: str) -> str:
    """The address tidied and checked (PER-022).

    Raises:
        django.core.exceptions.ValidationError: The address cannot be used.
    """
    from django.core.exceptions import ValidationError

    from rentalars.personnel.calendar_client import check_url

    url = normalise_url(url)
    if not url:
        raise ValidationError({"url": _("Enter the address of the calendar.")})
    try:
        check_url(url)
    except CalendarHttpError as error:
        raise ValidationError({"url": str(error)}) from error
    if len(url) > CalendarFeed._meta.get_field("url").max_length:
        raise ValidationError({"url": _("The address is too long.")})
    return url


def add_feed(person: Person, url: str, label: str = "") -> CalendarFeed:
    """Link one more calendar to a person (PER-022, PER-031).

    It is read with the next run (within a minute); call
    :func:`read_calendar` with ``force`` to try it at once.

    Raises:
        django.core.exceptions.ValidationError: The address cannot be used,
            is linked already, or the person has :attr:`CalendarFeed.MAX_PER_PERSON`
            calendars.
    """
    from django.core.exceptions import ValidationError

    url = _checked_url(url)
    label = " ".join((label or "").split())[: CalendarFeed._meta.get_field("label").max_length]
    with transaction.atomic():
        # One at a time per person, so that the limit and the check for the same address hold.
        Person.objects.select_for_update().filter(pk=person.pk).first()
        feeds = CalendarFeed.objects.filter(person=person)
        if feeds.filter(url=url).exists():
            raise ValidationError({"url": _("This calendar is linked already.")})
        if feeds.count() >= CalendarFeed.MAX_PER_PERSON:
            raise ValidationError(
                {"url": _("At most %(count)d calendars can be linked.") % {"count": CalendarFeed.MAX_PER_PERSON}}
            )
        return CalendarFeed.objects.create(person=person, url=url, label=label)


def remove_feed(feed: CalendarFeed) -> None:
    """Remove a linked calendar and the busy times taken from it (PER-022, PER-031)."""
    feed.delete()


# --- Deployments as a calendar (PER-023) ---------------------------------------------------------------


def _host() -> str:
    return urlsplit(settings.RENTALARS_URL).hostname or "rentalars"


def deployment_uid(line_id: int) -> str:
    """The stable UID of the event of a crew line: ``rentalars-crewline-12@rentalars.example.de``."""
    return f"rentalars-crewline-{line_id}@{_host()}"


def deployment_lines(person: Person) -> list[Any]:
    """The crew lines of a person that belong into the calendar (PER-023).

    Those the person sees as "my deployments": not in cancelled projects,
    not declined, from :data:`DEPLOYMENTS_PAST` ago on.
    """
    from rentalars.projects.models import ProjectStatus, RequestStatus

    return list(
        person.crew_lines.filter(end__gte=timezone.now() - DEPLOYMENTS_PAST)
        .exclude(project__status=ProjectStatus.CANCELLED)
        .exclude(request_status=RequestStatus.DECLINED)
        .select_related("project", "project__venue_site", "project__parent", "job_function")
        .order_by("start", "pk")
    )


def _place(project: Any) -> str:
    if project.venue_site_id:
        site = project.venue_site
        parts = [site.name, *getattr(site, "address_lines", [])]
        if project.venue:
            parts.append(project.venue)
        return ", ".join(part for part in parts if part)
    return project.venue


def deployment_event(line: Any) -> Any:
    """The calendar event of one crew line (PER-023) – without DTSTAMP, see :func:`event_digest`."""
    import icalendar

    from rentalars.projects.family_labels import project_label
    from rentalars.projects.models import ProjectStatus, RequestStatus

    project = line.project
    # PRJ-048: a deployment in a part names the whole project: "2026-0042-1 Bühne Marktplatz (Stadtfest)".
    label = project_label(project)
    event = icalendar.Event()
    event.add("UID", deployment_uid(line.pk))
    event.add("SUMMARY", f"{line.job_function.name} – {label}")
    event.add("DTSTART", line.start.astimezone(datetime.UTC))
    event.add("DTEND", line.end.astimezone(datetime.UTC))
    place = _place(project)
    if place:
        event.add("LOCATION", place)
    details = [
        _("Project: %(project)s") % {"project": label},
        _("Job function: %(function)s") % {"function": line.job_function.name},
    ]
    if line.meeting_point:
        details.append(_("Meeting point: %(place)s") % {"place": line.meeting_point})
    if line.note:
        details.append(_("Note: %(note)s") % {"note": line.note})
    if line.request_status:
        details.append(_("Request: %(state)s") % {"state": line.get_request_status_display()})
    link = f"{settings.RENTALARS_URL}/projects/{project.pk}/deployment/"
    details.append(link)
    event.add("DESCRIPTION", "\n".join(details))
    event.add("URL", link)
    tentative = project.status in (ProjectStatus.INQUIRY, ProjectStatus.OPTION) or (
        line.request_status == RequestStatus.REQUESTED
    )
    event.add("STATUS", "TENTATIVE" if tentative else "CONFIRMED")
    event.add("TRANSP", "OPAQUE")
    return event


def _calendar(name: str) -> Any:
    import icalendar

    calendar = icalendar.Calendar()
    calendar.add("PRODID", f"-//Rentalars//{_host()}//DE")
    calendar.add("VERSION", "2.0")
    calendar.add("CALSCALE", "GREGORIAN")
    calendar.add("METHOD", "PUBLISH")
    calendar.add("X-WR-CALNAME", name)
    calendar.add("REFRESH-INTERVAL", datetime.timedelta(minutes=30), parameters={"VALUE": "DURATION"})
    # PER-023: as a duration ("PT30M") – a bare time span was written as "0:30:00", which calendar programs ignore.
    calendar.add("X-PUBLISHED-TTL", icalendar.vDuration(datetime.timedelta(minutes=30)))
    return calendar


def deployments_calendar(person: Person) -> tuple[bytes, str]:
    """The deployments of a person as an .ics file (PER-023).

    Returns:
        The file and its ETag. The ETag follows the deployments, not the
        moment the file was made, so that a calendar program that asks
        again gets "not modified" until something changed.
    """
    with translation.override(settings.LANGUAGE_CODE):
        calendar = _calendar(_("Deployments %(name)s") % {"name": person.name})
        events = [deployment_event(line) for line in deployment_lines(person)]
    fingerprint = hashlib.sha256(calendar.to_ical())
    stamp = timezone.now().astimezone(datetime.UTC)
    for event in events:
        fingerprint.update(event.to_ical())
        event.add("DTSTAMP", stamp)
        calendar.add_component(event)
    return calendar.to_ical(), f'"{fingerprint.hexdigest()[:32]}"'


def event_digest(event: Any) -> str:
    """A fingerprint of an event without its time stamp: equal digest, nothing to write."""
    return hashlib.sha256(event.to_ical()).hexdigest()


# --- The subscription link (PER-023) ----------------------------------------------------------------------


def renew_calendar_token(person: Person) -> str:
    """Create the secret of the subscription link, or a new one; the old link stops working (PER-023)."""
    token = secrets.token_urlsafe(32)
    Person.objects.filter(pk=person.pk).update(calendar_token=token)
    person.calendar_token = token
    return token


def revoke_calendar_token(person: Person) -> None:
    """Switch the subscription link off (PER-023)."""
    Person.objects.filter(pk=person.pk).update(calendar_token="")
    person.calendar_token = ""


def subscription_path(person: Person) -> str:
    """The path of the subscription link, or "" if none was created."""
    if not person.calendar_token:
        return ""
    return reverse("personnel:calendar_feed", args=[person.pk, person.calendar_token])


def subscription_url(person: Person) -> str:
    """The full subscription link for calendar programs, or "" if none was created (PER-023)."""
    path = subscription_path(person)
    return f"{settings.RENTALARS_URL}{path}" if path else ""


def person_for_token(pk: int, token: str) -> Person | None:
    """The person a subscription link belongs to, or ``None`` (PER-023).

    The token is compared in constant time, so that the time of the answer
    tells nothing about how much of a guess was right.
    """
    person = (
        Person.objects.filter(pk=pk, is_active=True, anonymised_at__isnull=True, user__is_active=True)
        .only("pk", "first_name", "last_name", "calendar_token")
        .first()
    )
    stored = person.calendar_token if person is not None else ""
    # Compare even without a person, so that unknown and wrong look alike.
    matches = hmac.compare_digest((stored or "-").encode(), (token or "").encode())
    return person if person is not None and stored and matches else None


# --- CalDAV (PER-023) -------------------------------------------------------------------------------------------


def set_caldav(person: Person, *, url: str, username: str, password: str | None) -> None:
    """Store the CalDAV calendar of a person (PER-023); ``password=None`` keeps the stored one.

    A different calendar starts afresh: what was written into the old one
    stays there, and everything is written into the new one with the next
    run. An empty address switches writing off.

    Raises:
        django.core.exceptions.ValidationError: The address cannot be used.
    """
    from django.core.exceptions import ValidationError

    from rentalars.personnel.calendar_client import check_url

    url = normalise_url(url)
    if url:
        try:
            check_url(url)
        except CalendarHttpError as error:
            raise ValidationError({"caldav_url": str(error)}) from error
    username = (username or "").strip()
    changes: dict[str, Any] = {"caldav_url": url, "caldav_username": username if url else ""}
    if not url:
        changes["caldav_password_encrypted"] = ""
    elif password is not None and password != "":
        changes["caldav_password_encrypted"] = encrypt_secret(password)
    moved = url != person.caldav_url or changes["caldav_username"] != person.caldav_username
    if moved or "caldav_password_encrypted" in changes:
        changes.update(caldav_error="", caldav_failures=0, caldav_checked_at=None, caldav_dirty=bool(url))
    if moved:
        changes["caldav_synced_at"] = None
    with transaction.atomic():
        if moved:
            CalendarPush.objects.filter(person=person).delete()
        Person.objects.filter(pk=person.pk).update(**changes)
    for name, value in changes.items():
        setattr(person, name, value)


@dataclass
class PushResult:
    """What one comparison with the CalDAV calendar did."""

    written: int = 0
    deleted: int = 0
    unchanged: int = 0
    #: ``False`` if the time ran out before everything was written; the rest follows with the next run.
    complete: bool = True
    #: The problem, if writing failed (also stored at the person).
    error: str = ""


def _file_name(uid: str) -> str:
    return "".join(char if char.isalnum() or char in "-._" else "_" for char in uid) + ".ics"


def _claim_push(person: Person, *, force: bool) -> bool:
    now = timezone.now()
    due = Q(caldav_checked_at__isnull=True) | Q(caldav_checked_at__lte=now - PUSH_INTERVAL)
    if not person.caldav_failures:
        due |= Q(caldav_dirty=True)
    if force:
        due = Q(caldav_checked_at__isnull=True) | Q(caldav_checked_at=person.caldav_checked_at)
    claimed = Person.objects.filter(due, pk=person.pk).update(caldav_checked_at=now, caldav_dirty=False)
    person.caldav_checked_at, person.caldav_dirty = now, False
    return bool(claimed)


def push_deployments(person: Person, *, force: bool = False, deadline: float | None = None) -> PushResult | None:
    """Bring the CalDAV calendar of a person up to date with the deployments (PER-023).

    Writes the events that are new or changed, deletes those of
    deployments that are gone, and leaves alone what is unchanged. A
    deployment that is merely older than :data:`DEPLOYMENTS_PAST` is not
    deleted: it stays in the calendar as what it was.

    Returns:
        What was done, or ``None`` if nothing was due, another run is
        writing right now, or the person has no CalDAV calendar. A failure
        comes back in :attr:`PushResult.error` and is stored in
        ``caldav_error``; what was written up to then is remembered.
    """
    if not person.caldav_url or not _claim_push(person, force=force):
        return None
    result = PushResult()
    with _installation_language():
        try:
            password = decrypt_secret(person.caldav_password_encrypted)
            calendar = CalDAVCalendar(person.caldav_url, person.caldav_username, password)
            if person.caldav_synced_at is None:
                # First contact with this calendar: find it (the address may be just the server), check the login.
                collection = calendar.find_collection()
                calendar.url = collection
                if collection != person.caldav_url:
                    Person.objects.filter(pk=person.pk).update(caldav_url=collection[:500])
                    person.caldav_url = collection
            _push(person, calendar, result, deadline)
        except SecretUnreadableError:
            result.error = _("The stored password can no longer be read. Enter it again.")
        except CalendarHttpError as error:
            result.error = str(error)
        except Exception:  # never let one calendar break the run
            logger.exception("Writing the CalDAV calendar of person %s failed.", person.pk)
            result.error = _("The calendar could not be written.")
        if result.error:
            _push_failed(person, result.error)
            return result
    now = timezone.now()
    changes: dict[str, Any] = {"caldav_synced_at": now, "caldav_error": "", "caldav_failures": 0}
    if not result.complete:
        changes["caldav_dirty"] = True
    Person.objects.filter(pk=person.pk).update(**changes)
    person.caldav_synced_at, person.caldav_error, person.caldav_failures = now, "", 0
    return result


def _push(person: Person, calendar: CalDAVCalendar, result: PushResult, deadline: float | None) -> None:
    from rentalars.projects.models import CrewLine

    with translation.override(settings.LANGUAGE_CODE):
        wanted = {deployment_uid(line.pk): deployment_event(line) for line in deployment_lines(person)}
    pushed = {push.uid: push for push in CalendarPush.objects.filter(person=person)}
    stamp = timezone.now().astimezone(datetime.UTC)
    for uid, event in wanted.items():
        digest = event_digest(event)
        known = pushed.get(uid)
        if known is not None and known.digest == digest:
            result.unchanged += 1
            continue
        if deadline is not None and time.monotonic() > deadline:
            result.complete = False
            return
        event.add("DTSTAMP", stamp)
        document = _calendar("Rentalars")
        document.add_component(event)
        name = known.href if known is not None else _file_name(uid)
        etag = calendar.put(name, document.to_ical(), etag=known.etag if known else "", new=known is None)
        CalendarPush.objects.update_or_create(
            person=person,
            uid=uid,
            defaults={"href": name, "etag": etag[:255], "digest": digest, "pushed_at": timezone.now()},
        )
        result.written += 1
    gone = [push for uid, push in pushed.items() if uid not in wanted]
    if not gone:
        return
    # A deployment that only grew older than the window stays in the calendar; only its row is forgotten.
    line_ids = {}
    for push in gone:
        tail = push.uid.split("@", 1)[0].rsplit("-", 1)[-1]
        if tail.isdigit():
            line_ids[push.uid] = int(tail)
    from rentalars.projects.models import ProjectStatus, RequestStatus

    aged = set(
        CrewLine.objects.filter(pk__in=line_ids.values(), person=person, end__lt=timezone.now() - DEPLOYMENTS_PAST)
        .exclude(project__status=ProjectStatus.CANCELLED)
        .exclude(request_status=RequestStatus.DECLINED)
        .values_list("pk", flat=True)
    )
    for push in gone:
        if line_ids.get(push.uid) in aged:
            push.delete()
            continue
        if deadline is not None and time.monotonic() > deadline:
            result.complete = False
            return
        calendar.delete(push.href, etag=push.etag)
        push.delete()
        result.deleted += 1


def _push_failed(person: Person, message: str) -> None:
    message = _short(message)
    Person.objects.filter(pk=person.pk).update(caldav_error=message, caldav_failures=F("caldav_failures") + 1)
    person.refresh_from_db(fields=["caldav_failures"])
    person.caldav_error = message
    if person.caldav_failures == FAILURES_BEFORE_NOTICE:
        _tell(person, gettext_lazy("Your deployments cannot be written into your calendar"), message)


def _tell(person: Person, title: Any, message: str) -> None:
    """Tell the person once that a calendar keeps failing (PER-022, PER-023)."""
    from rentalars.notifications.models import Kind
    from rentalars.notifications.services import notify

    try:
        notify(
            [person.user],
            Kind.CALENDAR_PROBLEM,
            title,
            body=message,
            url=reverse("personnel:own_availability") + "#calendars",
        )
    except Exception:  # a notification must not break the run either
        logger.exception("Telling person %s about the calendar failed.", person.pk)


# --- The hook and the periodic run --------------------------------------------------------------------------


def crew_line_changed(sender: Any, instance: Any, **kwargs: Any) -> None:
    """Mark the people of a crew line "due" for their CalDAV calendar (PER-023).

    Connected to saving and deleting crew lines. One small update, and only
    for people who have a CalDAV calendar; the writing itself happens in the
    periodic run, never in the request.
    """
    people = {instance.person_id}
    before = instance._audit_before() if hasattr(instance, "_audit_before") and instance.pk else None
    if before:
        people.add(before.get("person"))
    people.discard(None)
    if people:
        Person.objects.filter(pk__in=people).exclude(caldav_url="").update(caldav_dirty=True)


def connect_signals() -> None:
    """Connect :func:`crew_line_changed`; called once when the application starts."""
    from django.db.models.signals import post_delete, pre_save

    pre_save.connect(crew_line_changed, sender="projects.CrewLine", dispatch_uid="personnel.calendars.save")
    post_delete.connect(crew_line_changed, sender="projects.CrewLine", dispatch_uid="personnel.calendars.delete")


@dataclass
class RunResult:
    """What one periodic run did."""

    feeds_read: int = 0
    feeds_failed: int = 0
    calendars_written: int = 0
    calendars_failed: int = 0


def sync_person(person: Person, *, budget_seconds: float = RUN_BUDGET_SECONDS) -> tuple[bool | None, PushResult | None]:
    """Read the linked calendars and write the CalDAV calendar of a person now ("read now").

    Returns:
        The outcome of :func:`read_feeds` and of :func:`push_deployments`.
    """
    deadline = time.monotonic() + budget_seconds
    feed = read_feeds(person, force=True)
    push = push_deployments(person, force=True, deadline=deadline) if person.caldav_url else None
    return feed, push


def run_due(*, budget_seconds: float = RUN_BUDGET_SECONDS) -> RunResult:
    """Do what is due: read linked calendars, write CalDAV calendars (PER-022, PER-023, PER-031).

    Called every minute by the background timer. Every linked calendar is
    due :data:`FEED_INTERVAL` after its own last reading. Never raises;
    problems are logged and stored at the calendar or person they belong to.
    """
    result = RunResult()
    try:
        deadline = time.monotonic() + budget_seconds
        now = timezone.now()
        active = Person.objects.filter(is_active=True, anonymised_at__isnull=True)
        feeds = (
            CalendarFeed.objects.filter(person__in=active)
            .filter(Q(checked_at__isnull=True) | Q(checked_at__lte=now - FEED_INTERVAL))
            .select_related("person__user")
            .order_by(F("checked_at").asc(nulls_first=True), "pk")
        )
        for feed in feeds[:200]:
            if time.monotonic() > deadline:
                break
            outcome = read_calendar(feed)
            if outcome is True:
                result.feeds_read += 1
            elif outcome is False:
                result.feeds_failed += 1
        calendars = (
            active.exclude(caldav_url="")
            .filter(
                Q(caldav_checked_at__isnull=True)
                | Q(caldav_checked_at__lte=now - PUSH_INTERVAL)
                | Q(caldav_dirty=True, caldav_failures=0)
            )
            .order_by(F("caldav_checked_at").asc(nulls_first=True))
        )
        for person in calendars[:200]:
            if time.monotonic() > deadline:
                break
            pushed = push_deployments(person, deadline=deadline)
            if pushed is not None and pushed.error:
                result.calendars_failed += 1
            elif pushed is not None:
                result.calendars_written += 1
    except Exception:
        logger.exception("The periodic run of the calendars failed.")
    return result
