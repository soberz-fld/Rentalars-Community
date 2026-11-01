# SPDX-License-Identifier: GPL-3.0-or-later
"""What "My times" shows besides hours: the rate of each entry and the text to copy (ZEI-026).

Rate and amount
---------------
An entry carries the hourly rate fixed when it was recorded (ZEI-008), and
its amount is hours × that rate. A deployment billed "per day" (PER-029)
with a day rate of the person on its crew line is paid by the day, not by
the hour: such an entry shows "Tagessatz" and the day rate, and the day
rate is its amount – once per calendar day and crew line; further entries
of the same day and line show that they are covered by it. The sum of the
week adds what the rows show. Reports, exports and project costs are not
touched by this: they keep hours × rate (ZEI-015, PRJ-025).

ZEI-028: a deployment with a flat rate for the person
(``CrewLine.cost_flat_rate`` on the person's own crew line, PER-018) is
paid once per deployment. Its first finished entry – by begin, in whatever
week it lies – shows "Pauschale" and carries the flat rate as its amount;
every further entry of the deployment shows "in der Pauschale" with the
amount 0. A deployment that spans weeks therefore counts in the week of its
first entry. The hours count as hours as always. The API names the same
(``pay_kind: flat``, ``in_flat_rate``), as the companion app gets it.

Copying to the clipboard
------------------------
An approved time can be copied as a block for a timesheet or invoice of
the person's own, one block per part of a period (ZEI-025)::

    <name of the service product of the job function>
    <TAB>Datum: 2026.10.16
    <TAB>Projekt: 2026-0042 - Stadtfest
    <TAB>Aktivität: Aufbau

The service product is the crew line's, else the job function's; without
one, the job function's name. The activity is the phase of the crew line
(PRJ-080), else empty.
"""

from __future__ import annotations

import datetime
from collections.abc import Iterable, Sequence
from decimal import Decimal
from typing import Any

from django.db.models import Q, prefetch_related_objects
from django.utils import timezone
from django.utils.translation import pgettext

from rentalars.core.listing import end_of_day, start_of_day
from rentalars.core.money import ZERO, money
from rentalars.projects.models import CrewBilling
from rentalars.timetracking.models import TimeEntry, TimeEntryStatus

#: How the rate of an entry is paid.
HOURLY = "hourly"
DAILY = "daily"
#: API-016: the deployment is paid with a flat rate for the person (``CrewLine.cost_flat_rate``, PER-018).
FLAT = "flat"


def day_rate_of(entry: TimeEntry) -> Decimal | None:
    """The day rate an entry is paid with, or ``None`` if it is paid by the hour (PER-029, ZEI-026).

    Only the person's own day rate fixed on a crew line billed per day; a
    guide value of the job function is never shown as somebody's pay.
    """
    line = entry.crew_line
    if line is None or line.billing != CrewBilling.DAY or line.person_id != entry.person_id:
        return None
    return line.daily_rate


def flat_rate_of(entry: TimeEntry) -> Decimal | None:
    """The flat rate an entry's deployment is paid with, or ``None`` (PER-018, API-016, ZEI-028).

    Only the person's own crew line with a flat rate for the person
    (``cost_flat_rate``); it comes before a day rate, as in the costs of
    the line (``projects.crew``).
    """
    line = entry.crew_line
    if line is None or line.person_id != entry.person_id:
        return None
    return line.cost_flat_rate


#: The first finished entry ``(start, pk)`` of a day or a deployment, by its key.
FirstEntries = dict[tuple[Any, ...], tuple[Any, int]]


def _day_key(entry: TimeEntry) -> tuple[int, int | None, datetime.date]:
    """Person, crew line and local day of an entry – what one day rate covers (PER-029)."""
    return entry.person_id, entry.crew_line_id, timezone.localtime(entry.start).date()


def _deployment_key(entry: TimeEntry) -> tuple[int, int | None]:
    """Person and crew line of an entry – what one flat rate covers (ZEI-028)."""
    return entry.person_id, entry.crew_line_id


def first_entries(
    days: set[tuple[int, int | None, datetime.date]], deployments: set[tuple[int, int | None]]
) -> tuple[FirstEntries, FirstEntries]:
    """The first finished entry of each day on a line paid per day and of each deployment paid flat.

    "First" is by begin, then by ID, among the finished entries of the
    person on the line: of that calendar day for a day rate (ZEI-026), of
    the whole deployment – in whatever week they lie – for a flat rate
    (ZEI-028). One query for both; none if there is neither.
    """
    first_day: FirstEntries = {}
    first_deployment: FirstEntries = {}
    if not days and not deployments:
        return first_day, first_deployment
    condition = Q()
    if days:
        condition |= Q(
            person_id__in={key[0] for key in days},
            crew_line_id__in={key[1] for key in days},
            start__gte=start_of_day(min(key[2] for key in days)),
            start__lt=end_of_day(max(key[2] for key in days)),
        )
    if deployments:
        condition |= Q(person_id__in={key[0] for key in deployments}, crew_line_id__in={key[1] for key in deployments})
    for pk, person_id, line_id, start in TimeEntry.objects.filter(condition, end__isnull=False).values_list(
        "pk", "person_id", "crew_line_id", "start"
    ):
        for key, keys, first in (
            ((person_id, line_id, timezone.localtime(start).date()), days, first_day),
            ((person_id, line_id), deployments, first_deployment),
        ):
            if key in keys and (key not in first or (start, pk) < first[key]):
                first[key] = (start, pk)
    return first_day, first_deployment


def _is_further(key: tuple[Any, ...], entry: TimeEntry, first: FirstEntries) -> bool:
    """Whether an entry comes after the first entry of its day or deployment – and is covered by its rate."""
    earliest = first.get(key)
    return earliest is not None and earliest < (entry.start, entry.pk)


def attach_pay(entries: Iterable[TimeEntry]) -> Decimal:
    """Note on every entry how it is paid; return the sum of what the rows show (ZEI-026, ZEI-028).

    Sets ``pay_kind`` (:data:`HOURLY`, :data:`DAILY` or :data:`FLAT`),
    ``pay_rate`` (the hourly rate, the day rate or the flat rate),
    ``pay_amount`` (the amount the row shows), ``pay_in_day_rate`` (a
    further entry of a day already paid by its day rate) and
    ``pay_in_flat_rate`` (a further entry of a deployment whose flat rate
    its first entry carries – see the module description). The entries come
    in the order of their start.
    """
    entries = list(entries)
    _days, first = first_entries(
        set(), {_deployment_key(entry) for entry in entries if flat_rate_of(entry) is not None}
    )
    total = ZERO
    paid_days: set[tuple[int, Any]] = set()
    for entry in entries:
        flat = flat_rate_of(entry)
        daily = day_rate_of(entry) if flat is None else None
        entry.pay_in_day_rate = entry.pay_in_flat_rate = False
        if flat is not None:
            entry.pay_kind, entry.pay_rate = FLAT, flat
            if _is_further(_deployment_key(entry), entry, first):
                entry.pay_amount, entry.pay_in_flat_rate = ZERO, True
            else:
                entry.pay_amount = money(flat)
        elif daily is None:
            entry.pay_kind, entry.pay_rate, entry.pay_amount = HOURLY, entry.hourly_rate, entry.amount
        else:
            entry.pay_kind, entry.pay_rate = DAILY, daily
            day = (entry.crew_line_id, timezone.localtime(entry.start).date())
            if day in paid_days:
                entry.pay_amount, entry.pay_in_day_rate = ZERO, True
            else:
                paid_days.add(day)
                entry.pay_amount = money(daily)
        total += entry.pay_amount
    return money(total)


def pay_kind_of(entry: TimeEntry) -> str:
    """How the person is paid for an entry: :data:`HOURLY`, :data:`DAILY` or :data:`FLAT` (ZEI-026, API-016).

    :data:`FLAT` – the entry's crew line is the person's own and carries a
    flat rate for the person – comes first, as in the costs of the line
    (``projects.crew``). "My times" in the browser shows it as
    the API names it (ZEI-028, :func:`attach_pay`).
    """
    if flat_rate_of(entry) is not None:
        return FLAT
    return HOURLY if day_rate_of(entry) is None else DAILY


def attach_pay_kinds(entries: Sequence[TimeEntry]) -> None:
    """Note ``pay_kind``, ``pay_in_day_rate`` and ``pay_in_flat_rate`` on entries of any choice (API-016, ZEI-028).

    The rules of :func:`attach_pay` – of the finished entries of a person on
    one crew line paid per day and one calendar day, the first by its begin
    is paid with the day rate, the others are in it; of a deployment paid
    flat, the first finished entry carries the flat rate, the others are in
    it – also where the list does not hold the whole day or deployment (a
    page, one entry): the first entries are looked up, with one query for
    all of them (:func:`first_entries`). The crew lines are fetched with
    one query where they are not loaded yet.
    """
    prefetch_related_objects([entry for entry in entries if entry.crew_line_id], "crew_line")
    for entry in entries:
        entry.pay_kind = pay_kind_of(entry)
        entry.pay_in_day_rate = entry.pay_in_flat_rate = False
    daily = [entry for entry in entries if entry.pay_kind == DAILY]
    flat = [entry for entry in entries if entry.pay_kind == FLAT]
    first_day, first_deployment = first_entries(
        {_day_key(entry) for entry in daily}, {_deployment_key(entry) for entry in flat}
    )
    for entry in daily:
        entry.pay_in_day_rate = _is_further(_day_key(entry), entry, first_day)
    for entry in flat:
        entry.pay_in_flat_rate = _is_further(_deployment_key(entry), entry, first_deployment)


def product_name_of(entry: TimeEntry) -> str:
    """The name of the service product an entry is worked in: the crew line's, the job function's, its name."""
    line = entry.crew_line
    if line is not None and line.service_product_id:
        return line.service_product.name
    function = entry.job_function
    if function.service_product_id:
        return function.service_product.name
    return function.name


def clipboard_block(entry: TimeEntry) -> str:
    """The block of one entry or part to copy (ZEI-026) – lines indented by a real tab character."""
    project = entry.project
    project_text = f"{project.number} - {project.name}" if project is not None else ""
    line = entry.crew_line
    activity = line.phase.label if line is not None and line.phase_id else ""
    # The labels outside the f-strings: makemessages does not find texts inside them.
    date_label = pgettext("clipboard", "Date")
    project_label = pgettext("clipboard", "Project")
    activity_label = pgettext("clipboard", "Activity")
    return "\n".join(
        [
            product_name_of(entry),
            f"\t{date_label}: {timezone.localtime(entry.start):%Y.%m.%d}",
            f"\t{project_label}: {project_text}",
            f"\t{activity_label}: {activity}",
        ]
    )


def clipboard_text(parts: Sequence[TimeEntry]) -> str:
    """The text to copy for an entry, or for all parts of a period – one block each (ZEI-025, ZEI-026)."""
    return "\n".join(clipboard_block(part) for part in parts)


def attach_clipboard(entries: Sequence[TimeEntry]) -> None:
    """Note ``copy_text`` on the approved entries; for a divided period on its first part only (ZEI-026).

    The other parts of the period are expected among ``entries``: they share
    its begin, so they lie in the same week.
    """
    periods: dict[Any, list[TimeEntry]] = {}
    for entry in entries:
        entry.copy_text = ""
        if entry.period_key is not None:
            periods.setdefault(entry.period_key, []).append(entry)
    for entry in entries:
        if entry.status != TimeEntryStatus.APPROVED:
            continue
        if entry.period_key is None:
            entry.copy_text = clipboard_text([entry])
        else:
            parts = periods[entry.period_key]
            if parts[0] is entry and all(part.status == TimeEntryStatus.APPROVED for part in parts):
                entry.copy_text = clipboard_text(parts)


def mark_periods(entries: Sequence[TimeEntry]) -> None:
    """ZEI-025: note ``part_number`` and ``part_count`` on the parts of divided periods in a list.

    Lists show each part as a row; the first part of a period carries the
    actions that act on the whole period (approving, copying), the others
    say which part they are.
    """
    counts: dict[Any, int] = {}
    for entry in entries:
        if entry.period_key is not None:
            counts[entry.period_key] = counts.get(entry.period_key, 0) + 1
    seen: dict[Any, int] = {}
    for entry in entries:
        if entry.period_key is None:
            entry.part_number, entry.part_count = 0, 0
            continue
        seen[entry.period_key] = seen.get(entry.period_key, 0) + 1
        entry.part_number, entry.part_count = seen[entry.period_key], counts[entry.period_key]
