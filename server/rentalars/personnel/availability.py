# SPDX-License-Identifier: GPL-3.0-or-later
"""Who is free when? The availability of people (VFG-009, VFG-010, PER-021).

For every person and every period the answer is one of three (VFG-009):

*absent*
    an absence (holiday, sick, not available) overlaps the period – or the
    person said "not available" for a part of it (PER-021): marked red in
    the own availability calendar, or busy in the linked calendar (PER-022);
*planned*
    a crew line of a project that is not cancelled overlaps the period;
*free*
    neither.

Absence outranks planning: somebody who is on holiday and still stands in a
crew line is a problem the planner has to see (PRJ-022 warns about it at the
line).

What the person said about the period comes along as well (PER-021): "with
limits" (yellow) is a hint and does not change the status; "available"
(green) puts the person to the front among the free ones.

Unlike material, people are not counted. Two overlapping crew lines are not
"one person short" but a double booking of that one person.
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from django.db.models import QuerySet
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.core.i18n import local_pattern
from rentalars.personnel.marks import AvailabilityPeriod, effective_periods
from rentalars.personnel.models import (
    Absence,
    AvailabilityMark,
    AvailabilitySource,
    AvailabilityState,
    JobFunction,
    Person,
)

#: A stored entry, or the availability that counts in a period (PER-027): both have the same fields.
Statement = AvailabilityMark | AvailabilityPeriod


class AvailabilityHint(str):
    """A note for the planner that is quieter than a warning (PER-021).

    Lists of warnings are lists of texts; a hint is a text too, so every
    place that shows warnings shows it. Templates that want to set it apart
    ask ``warning.is_hint`` – plain texts do not have that attribute.
    """

    is_hint = True


def period_text(start: datetime.datetime, end: datetime.datetime) -> str:
    """Describe a period briefly: ``12.11.``, ``12.11.–14.11.`` or ``12.11. 18:00–23:00``.

    Whole days (midnight to midnight) are named by their dates; the end of
    such a period is the midnight after the last day.
    """
    begin, finish = timezone.localtime(start), timezone.localtime(end)
    midnight = datetime.time(0, 0)
    if begin.time() == midnight and finish.time() == midnight:
        last = (finish - datetime.timedelta(days=1)).date()
        if last <= begin.date():
            return f"{begin:{local_pattern('%d.%m.')}}"
        return f"{begin:{local_pattern('%d.%m.')}}–{last:{local_pattern('%d.%m.')}}"
    if begin.date() == finish.date():
        return f"{begin:{local_pattern('%d.%m. %H:%M')}}–{finish:%H:%M}"
    return f"{begin:{local_pattern('%d.%m. %H:%M')}} – {finish:{local_pattern('%d.%m. %H:%M')}}"


def describe_marks(marks: list[Statement], *, limit: int = 3) -> str:
    """Name the periods of some marks in one line, at most ``limit`` and "+N" for the rest."""
    ordered = sorted(marks, key=lambda mark: mark.start)
    texts = []
    for mark in ordered[:limit]:
        text = period_text(mark.start, mark.end)
        if mark.note:
            text = f"{text} ({mark.note})"
        texts.append(text)
    if len(ordered) > limit:
        texts.append(_("+%(count)d more") % {"count": len(ordered) - limit})
    return ", ".join(texts)


def mark_messages(marks: list[Statement]) -> list[str]:
    """Turn the marks that overlap a deployment into warnings and hints for the planner (PER-021, PER-022).

    * red marks entered by the person: a warning "not available";
    * busy times of the linked calendar: a warning of its own, without the
      titles of the appointments, which the person keeps to themselves;
    * yellow marks: a quieter :class:`AvailabilityHint`.

    Green marks say nothing a planner must know here.
    """
    own_red = [
        mark for mark in marks if mark.state == AvailabilityState.UNAVAILABLE and mark.source != AvailabilitySource.FEED
    ]
    feed_red = [
        mark for mark in marks if mark.state == AvailabilityState.UNAVAILABLE and mark.source == AvailabilitySource.FEED
    ]
    yellow = [mark for mark in marks if mark.state == AvailabilityState.LIMITED]
    found: list[str] = []
    if own_red:
        found.append(_("Not available by own statement: %(periods)s.") % {"periods": describe_marks(own_red)})
    if feed_red:
        found.append(_("Busy in the own calendar: %(periods)s.") % {"periods": describe_marks(feed_red)})
    if yellow:
        found.append(
            AvailabilityHint(_("Available with limits only: %(periods)s.") % {"periods": describe_marks(yellow)})
        )
    return found


@dataclass
class PersonAvailability:
    """How one person stands in a period (VFG-009)."""

    person: Person
    #: Crew lines that overlap the period, with their projects.
    deployments: list[Any] = field(default_factory=list)
    absences: list[Absence] = field(default_factory=list)
    #: What counts of what the person said about the period, red, yellow or green (PER-021, PER-022, PER-027).
    marks: list[AvailabilityPeriod] = field(default_factory=list)

    @property
    def unavailable(self) -> list[AvailabilityPeriod]:
        """Red marks: entered "not available", or busy in the linked calendar (PER-022)."""
        return [mark for mark in self.marks if mark.state == AvailabilityState.UNAVAILABLE]

    @property
    def limited(self) -> list[AvailabilityPeriod]:
        """Yellow marks: available with limits – a hint, no obstacle (PER-021)."""
        return [mark for mark in self.marks if mark.state == AvailabilityState.LIMITED]

    @property
    def said_available(self) -> bool:
        """Whether the person marked a part of the period green (PER-021)."""
        return any(mark.state == AvailabilityState.AVAILABLE for mark in self.marks)

    @property
    def status(self) -> str:
        """``absent``, ``planned`` or ``free`` – see the module description."""
        if self.absences or self.unavailable:
            return "absent"
        if self.deployments:
            return "planned"
        return "free"


def people_availability(
    start: datetime.datetime,
    end: datetime.datetime,
    *,
    job_function: JobFunction | None = None,
    people: QuerySet[Person] | None = None,
) -> list[PersonAvailability]:
    """Tell for each person whether they are free, planned or absent in a period (VFG-009).

    With ``job_function`` only people who have that function are looked at –
    the search "who is free in the period and can do X" (VFG-010). Without
    it every active person is looked at, whatever their job functions – also
    one without any (VFG-038, "Alle" in Personal → Verfügbarkeit: everybody who
    is available, regardless of the assigned job functions). The free ones come first,
    and among them those who said they are available (PER-021) before those
    who said nothing and those with limits.

    The number of database queries does not depend on the number of people.

    Args:
        start: Begin of the period asked about.
        end: End of the period.
        job_function: Only people with this job function.
        people: The people to look at; default: all active ones.
    """
    from rentalars.projects.models import CrewLine, ProjectStatus, RequestStatus

    # VFG-038: every active person – also one without job function, e.g. an office
    # account (every account is a person, AUT-026), who can be planned with the right to plan outside the job
    # functions (PER-006).
    candidates = Person.objects.filter(is_active=True) if people is None else people
    if job_function is not None:
        candidates = candidates.filter(rates__job_function=job_function).distinct()
    persons = list(candidates.order_by("last_name", "first_name"))
    ids = [person.pk for person in persons]

    deployments: dict[int, list[Any]] = defaultdict(list)
    lines = (
        CrewLine.objects.filter(person_id__in=ids, start__lt=end, end__gt=start)
        .exclude(project__status=ProjectStatus.CANCELLED)
        .exclude(request_status=RequestStatus.DECLINED)  # L14: who said no is not planned
        .select_related("project__parent", "job_function")
        .order_by("start")
    )
    for line in lines:
        deployments[line.person_id].append(line)

    absences: dict[int, list[Absence]] = defaultdict(list)
    for absence in Absence.objects.filter(person_id__in=ids, start__lt=end, end__gt=start).order_by("start"):
        absences[absence.person_id].append(absence)

    # PER-027: the availability that counts – one at any moment, busy times of the calendar as blocks.
    marks = effective_periods(ids, start, end)

    result = [
        PersonAvailability(
            person=person,
            deployments=deployments[person.pk],
            absences=absences[person.pk],
            marks=marks.get(person.pk, []),
        )
        for person in persons
    ]
    order = {"free": 0, "planned": 1, "absent": 2}

    def said(row: PersonAvailability) -> int:
        # PER-021: among equals, "available" first and "with limits" last.
        if row.limited:
            return 2
        return 0 if row.said_available else 1

    result.sort(key=lambda row: (order[row.status], said(row), row.person.sort_name.lower()))
    return result


__all__ = [
    "AvailabilityHint",
    "PersonAvailability",
    "describe_marks",
    "mark_messages",
    "people_availability",
    "period_text",
]
