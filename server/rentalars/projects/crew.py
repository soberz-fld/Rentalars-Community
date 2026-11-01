# SPDX-License-Identifier: GPL-3.0-or-later
"""Crew lines: planning people on projects (PRJ-019 to PRJ-023, PRJ-051, PRJ-052, PRJ-061).

Browser views and API views both call these functions (API-002). Every
function that changes a project first checks that the project is not closed
(PRJ-009).

The module also answers the three questions the planning page asks about
crew lines:

* What does a line cost the customer, and what does it cost us?
  (:func:`price_crew_lines`)
* Is anything wrong with the plan? A person booked twice, on holiday, or in
  a job function the person does not have (:func:`crew_warnings`, PRJ-022).
* Which approved times belong to no line? (:func:`unassigned_time_entries`,
  ZEI-021)

Phases, billing per day and breakdown:

* A line can belong to a phase of its project (PRJ-080). Planned with a
  phase and without a period of its own, it takes the phase's period; when
  the phase moves, its lines can move along (:func:`move_with_phase`).
* A line can be billed "per day" (PER-029): days × price per day for the
  customer, days × the person's day rate as cost (:func:`price_crew_line`).
* The price overview breaks the personnel down by phase and job function
  (:func:`breakdown_by_phase`, PRJ-088).

Asking again:

* A line remembers the period the person was asked for. "Ask again" is
  offered – and accepted – for an answered line only once its times changed
  since (PER-033, :func:`request_deployment`).
* New times of a line that was asked for or accepted bring a new request by
  themselves, unless switched off in the settings (PER-034,
  :func:`ask_again_for_new_times`).

Service products and hour tiers:

* Every job function has its service product (PRD-044); a new line takes
  price, unit, tax rate and the hour tiers from it, and names it.
* A new line of a service billed by the hour is billed "by effort" (PER-036).
* Hour tiers per day (PER-035): the hours of one day beyond the limit of the
  service product cost the price from the limit, and the person's rate from
  the limit as cost (:func:`price_crew_line`, ``projects.hour_tiers``).

Surcharges:

* Surcharges for night, Sunday and holidays (PER-009) on the price and on
  the costs of a line billed by the hour, each switched on the line
  (:func:`price_crew_line`, ``projects.time_surcharges``).

Firm planning and notifications (PER-041, PRJ-117, PRJ-118):

* A person can be planned firmly, without request (``firm`` of
  :func:`add_crew_lines` and :func:`update_crew_line`); new times of such a
  line are told, never asked (``projects.crew_changes``).
* The planned person is told what changed on their line and when they are
  taken off it – one notification per person and action
  (``projects.crew_changes``); several lines are changed at once by
  ``projects.crew_bulk``.
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, NamedTuple

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Sum
from django.urls import reverse
from django.utils import formats, timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.core.audit import record_event
from rentalars.core.i18n import LazyCall, LocalText, for_user, local_pattern
from rentalars.core.money import ZERO, format_decimal, money, percentage_of
from rentalars.masterdata.models import TaxRate
from rentalars.personnel import offers as price_offers  # PER-038
from rentalars.personnel.models import Absence, JobFunction, Person
from rentalars.personnel.services import has_job_function, rate_for
from rentalars.products.models import BillingMode
from rentalars.projects.discounts import limited_percent
from rentalars.projects.hour_tiers import (
    HourSplit,
    actual_cost_with_limit,
    approved_hours_per_day,
    planned_hours_per_day,
    split_at_limit,
)
from rentalars.projects.models import CrewBilling, CrewLine, Project, ProjectPhase, ProjectStatus, RequestStatus
from rentalars.projects.services import ensure_editable, ensure_plannable, moved, wall_clock_shift
from rentalars.projects.time_surcharges import (
    COST,
    PRICE,
    SurchargePart,
    SurchargeRules,
    WorkPiece,
    current_rules,
    entry_pieces,
    planned_pieces,
    surcharge_parts,
    total_of,
)

#: Fields of a crew line that need the price right (AUT-019); the discount (PER-026), the hour
#: tiers (PER-035), the surcharges for night, Sunday and holidays (PER-009).
PRICE_FIELDS = frozenset(
    {
        "unit_price",
        "billing",
        "tax_rate",
        "discount_percent",
        "hours_limit",
        "unit_price_above_limit",
        "time_surcharges_on_price",
    }
)

#: Fields that need the right to see hourly rates and personnel costs (AUT-019, PRJ-021); the day rate (PER-029),
#: the rate from the limit (PER-035), the surcharges on the costs (PER-009).
COST_FIELDS = frozenset(
    {"hourly_rate", "daily_rate", "cost_flat_rate", "hourly_rate_above_limit", "time_surcharges_on_cost"}
)

#: Fields a caller may change through :func:`update_crew_line`; the phase and the days, the vehicle and
#: whether the person drives it (LOG-008).
EDITABLE_FIELDS = (
    frozenset(
        {
            "job_function",
            "person",
            "start",
            "end",
            "planned_hours",
            "meeting_point",
            "note",
            "title",
            "phase",
            "days",
            "vehicle_line",
            "is_driver",
        }
    )
    | PRICE_FIELDS
    | COST_FIELDS
)

#: How many open places can be created in one step ("6 × stagehand").
MAX_LINES_PER_STEP = 50


def _check_rights(changes: Any, rights: Rights) -> None:
    """AUT-019: prices and costs can only be set by those who may see them."""
    touched = set(changes)
    if touched & PRICE_FIELDS and not rights.has(SpecialRight.PRICES):
        raise ValidationError(_("You do not have the right to set prices or discounts."))
    if touched & COST_FIELDS and not rights.has(SpecialRight.PERSONNEL_COSTS):
        raise ValidationError(_("You do not have the right to set hourly rates and personnel costs."))


def defaults_from_job_function(job_function: JobFunction) -> dict[str, Any]:
    """Return the values a new crew line copies from its job function (PER-008, PRJ-051, PRD-044).

    The price for the customer is that of the service product – every job function has one (PRD-044). A service product billed "flat"
    makes the line a flat-rate line (PER-018), one billed as daily rental a
    line billed per day (PER-029); one billed by the hour a line billed "by
    effort" (PER-036; "by plan" before) – the approved times are
    charged, until then the planned hours as an estimate. The hour tiers of
    the product come along (PER-035). A product without price yet gives a line
    with price 0. ``list_price`` remembers the product's price, so that a later
    change of it can be pointed out (PRJ-072).

    PER-009: the surcharges for night, Sunday and holidays are switched
    on for the price and for the costs as the settings say for new lines –
    unless the service product excludes them.
    """
    from rentalars.core.models import TimeSurchargeSettings

    surcharge_settings = TimeSurchargeSettings.load()
    product = job_function.service_product
    if product is None:  # only for a function not saved yet; a saved one always has its product
        return {
            "service_product": None,
            "title": job_function.name,
            "unit_price": ZERO,
            "list_price": None,
            "tax_rate": TaxRate.get_default(),
            "billing": CrewBilling.EFFORT,
            "hours_limit": None,
            "unit_price_above_limit": None,
            "time_surcharges_on_price": surcharge_settings.on_price,
            "time_surcharges_on_cost": surcharge_settings.on_costs,
        }
    if product.billing_mode == BillingMode.FLAT:
        billing = CrewBilling.FLAT
    elif product.billing_mode in BillingMode.daily_modes():
        billing = CrewBilling.DAY
    else:
        billing = CrewBilling.EFFORT  # PER-036: by the hour – the hours worked
    tiers = product.hours_limit is not None and product.price_above_limit is not None
    return {
        "service_product": product,
        "title": product.name,
        "unit_price": product.price or ZERO,
        "list_price": product.price,
        "tax_rate": product.tax_rate,
        "billing": billing,
        "hours_limit": product.hours_limit if tiers else None,
        "unit_price_above_limit": product.price_above_limit if tiers else None,
        # PER-009: the service product may exclude its lines from the surcharges.
        "time_surcharges_on_price": surcharge_settings.on_price and product.time_surcharges,
        "time_surcharges_on_cost": surcharge_settings.on_costs and product.time_surcharges,
    }


def _check_person(person: Person, job_function: JobFunction, rights: Rights) -> None:
    """PER-006: a person is planned only in job functions the person has – unless the planner may deviate."""
    if not person.is_active:
        raise ValidationError({"person": _("%(person)s is deactivated and cannot be planned.") % {"person": person}})
    if not has_job_function(person, job_function) and not rights.has(SpecialRight.PLAN_ANY_JOB_FUNCTION):
        raise ValidationError(
            {
                "person": _(
                    "%(person)s is not assigned to the job function %(function)s. "
                    "Assign it in the personnel data, or ask somebody with the right to plan outside the job functions."
                )
                % {"person": person, "function": job_function}
            }
        )


@transaction.atomic
def add_crew_lines(
    project: Project,
    *,
    rights: Rights,
    job_function: JobFunction,
    person: Person | None = None,
    count: int = 1,
    start: datetime.datetime | None = None,
    end: datetime.datetime | None = None,
    phase: ProjectPhase | None = None,
    firm: bool = False,
    **overrides: Any,
) -> list[CrewLine]:
    """Plan people, or open places, on a project (PRJ-019, PRJ-020).

    PER-041 (firm planning): ``firm=True`` plans the person firmly, without
    request; the person is told (``projects.crew_changes``).

    Args:
        project: The project.
        rights: The rights of the caller.
        job_function: What is to be done.
        person: Who does it; ``None`` plans an open place to be filled later.
        count: How many open places to create ("2 × stagehand"). With a
            person it must be 1: a person is in one place at a time.
        start: Begin of the deployment; default is the phase's, or without
            a phase the project's.
        end: End of the deployment; default as ``start``.
        phase: The phase of the project the lines belong to (PRJ-080).
        firm: Plan the person firmly, without request (PER-041); needs a person.
        **overrides: Further values: ``planned_hours`` (default: what
            ``models.suggested_hours`` makes of the period – its whole
            length, PRJ-073), ``days`` (PER-029; default: the calendar days
            of the period), ``meeting_point``, ``note``, and – with the
            matching rights – ``unit_price``, ``billing``, ``hourly_rate``,
            ``daily_rate``, ``cost_flat_rate``.

    Returns:
        The created lines.

    Raises:
        ValidationError: The project is closed, the person does not have the
            job function (PER-006), the phase belongs to another project, or
            a value is invalid.
    """
    ensure_editable(project)
    ensure_plannable(project)  # PRJ-090: no crew in a service case
    _check_rights(overrides.keys(), rights)
    if count < 1 or count > MAX_LINES_PER_STEP:
        raise ValidationError(
            {
                "count": _("Between 1 and %(maximum)d places can be planned in one step.")
                % {"maximum": MAX_LINES_PER_STEP}
            }
        )
    if person is not None and count != 1:
        raise ValidationError({"count": _("A person can only fill one place. Plan the other places without person.")})
    if firm and person is None:
        raise ValidationError({"firm": _("Plan a person first; an open place cannot be planned firmly.")})
    if not job_function.is_active:
        raise ValidationError({"job_function": _("This job function is deactivated.")})
    if person is not None:
        _check_person(person, job_function, rights)

    values = defaults_from_job_function(job_function)
    values.update(overrides)
    # PRJ-080: planned for a phase, the lines take its period unless they are given one of their own.
    default_start, default_end = (phase.start, phase.end) if phase is not None else (project.start, project.end)
    start, end = start or default_start, end or default_end
    rate = rate_for(person, job_function, start) if person is not None else None
    last = project.crew_lines.aggregate(last=Max("position"))["last"] or 0
    lines: list[CrewLine] = []
    for offset in range(1, count + 1):
        line = CrewLine(
            project=project,
            job_function=job_function,
            person=person,
            start=start,
            end=end,
            phase=phase,
            position=last + offset,
            **values,
        )
        if "planned_hours" not in overrides:
            line.planned_hours = line.period_hours
        if rate is not None:
            # PRJ-021, PER-029: the person's own rates of the day, fixed on the line; PER-035 the one from the limit.
            if "hourly_rate" not in overrides:
                line.hourly_rate = rate.own_hourly
            if "daily_rate" not in overrides:
                line.daily_rate = rate.own_daily
            if "hourly_rate_above_limit" not in overrides:
                line.hourly_rate_above_limit = rate.own_above_limit
        if firm:
            _set_firm(line)  # PER-041
        line.full_clean()
        line.save()
        lines.append(line)
    if firm:
        from rentalars.projects import crew_changes

        crew_changes.note_firm(lines)
    return lines


@transaction.atomic
def update_crew_line(line: CrewLine, *, rights: Rights, **changes: Any) -> CrewLine:
    """Change a crew line (PRJ-019 to PRJ-023).

    Rules:

    * A **new person** brings the person's hourly rate and day rate for the
      job function (PRJ-021, PER-029), unless a rate is passed along. Taking
      the person away empties the rates: an open place has no rate, only the
      guide values of its function (PRJ-052).
    * A **new job function** brings the price of its service product and, if
      a person is planned, that person's rate for the new function – again
      unless given explicitly.
    * Changing the period does *not* change the rate that is already fixed
      on the line.
    * A **new period** brings new planned hours, as long as the hours were
      the ones suggested for the old period and are not passed along
      (PRJ-023). Hours somebody entered by hand stay.
    * A **new phase** given without a period brings the period of the phase
      (PRJ-080) – as choosing the phase in the dialog fills in its period.
      Taking the phase away keeps the period.
    * **New times** of a line that was asked for or accepted ask the person
      again (PER-034, :func:`ask_again_for_new_times`); the line then
      carries ``asked_again``. A new person starts without request.
    * ``firm=True`` (PER-041) plans the person firmly, without
      request – a line accepted already stays as it is; ``firm=False`` takes
      "planned firmly" back: the line is "not asked" again and can be asked.
      New times of a line planned firmly ask nobody; the person is told.
    * PRJ-118: the person is told what changed – new times, meeting point,
      note, phase, job function, vehicle – and the person taken off the line
      that they are no longer planned (``projects.crew_changes``): one
      notification per person, also for several lines changed at once.

    Raises:
        ValidationError: The project is closed, a field is not editable, a
            right is missing, the person does not have the job function
            (PER-006), the phase belongs to another project, or a value is
            invalid.
    """
    from rentalars.projects import crew_changes

    ensure_editable(line.project)
    vars(line).pop("asked_again", None)  # what an earlier change of the same object did is no longer news
    firm = changes.pop("firm", None)  # PER-041: not a field – the request status "planned firmly"
    unknown = set(changes) - EDITABLE_FIELDS
    if unknown:
        raise ValidationError(_("These fields cannot be changed: %(fields)s") % {"fields": ", ".join(sorted(unknown))})
    _check_rights(changes.keys(), rights)

    new_function = changes.get("job_function", line.job_function)
    new_person = changes.get("person", line.person)
    function_changed = new_function.pk != line.job_function_id
    person_changed = (new_person.pk if new_person else None) != line.person_id
    new_phase = changes.get("phase", line.phase)
    if (
        new_phase is not None
        and new_phase.pk != line.phase_id
        and "start" not in changes
        and "end" not in changes
        and new_phase.project_id == line.project_id
    ):
        changes = {**changes, "start": new_phase.start, "end": new_phase.end}

    if function_changed and not new_function.is_active:
        raise ValidationError({"job_function": _("This job function is deactivated.")})
    if new_person is not None and (person_changed or function_changed):
        _check_person(new_person, new_function, rights)

    if firm and new_person is None:
        raise ValidationError({"firm": _("Plan a person first; an open place cannot be planned firmly.")})
    if firm and not new_person.is_active:
        raise ValidationError(
            {"person": _("%(person)s is deactivated and cannot be planned.") % {"person": new_person}}
        )

    old_period = (line.start, line.end)
    before = crew_changes.snapshot(line)
    hours_follow_period = (
        ("start" in changes or "end" in changes)
        and "planned_hours" not in changes
        and line.planned_hours == line.period_hours
    )
    if function_changed:
        for name, value in defaults_from_job_function(new_function).items():
            if name not in changes:
                setattr(line, name, value)
    for name, value in changes.items():
        setattr(line, name, value)
    if line.vehicle_line_id is None:
        line.is_driver = False  # LOG-008: nobody drives without a vehicle
    if hours_follow_period:
        line.planned_hours = line.period_hours
    if person_changed or function_changed:
        rate = rate_for(new_person, new_function, line.start) if new_person is not None else None
        if "hourly_rate" not in changes:
            line.hourly_rate = rate.own_hourly if rate is not None else None
        if "daily_rate" not in changes:
            line.daily_rate = rate.own_daily if rate is not None else None
        if "hourly_rate_above_limit" not in changes:
            line.hourly_rate_above_limit = rate.own_above_limit if rate is not None else None
    if person_changed and new_person is None and "cost_flat_rate" not in changes:
        line.cost_flat_rate = None  # a flat rate is agreed with a person, not with a place
    if person_changed:
        # A request was made to the person before; it does not hold for another one (PER-016).
        _clear_request(line)
    if firm and line.request_status not in (RequestStatus.FIRM, RequestStatus.ACCEPTED):
        _set_firm(line)  # PER-041: planned firmly, without request
    elif firm is False and line.request_status == RequestStatus.FIRM:
        _clear_request(line)  # PER-041: no longer firm – "not asked", to be asked
    elif line.request_status == RequestStatus.FIRM:
        # PER-041: planned firmly for the times as they are now – new times are told, not asked (see below).
        line.requested_start, line.requested_end = line.start, line.end
    line.full_clean()
    line.save()
    if person_changed or function_changed or set(changes) & (COST_FIELDS | {"billing"}):
        # PER-038: an accepted price offer that no longer fits stops applying.
        price_offers.after_line_update(
            line,
            person_or_function_changed=person_changed or function_changed,
            cost_touched=bool(set(changes) & COST_FIELDS),
        )
    if person_changed:
        _attribute_entries_to(line)
    elif (line.start, line.end) != old_period:
        # PER-034: the person agrees to the new times, or not – told what else changed in the same request.
        ask_again_for_new_times(line, also_changed=crew_changes.differences(before, line, times=False))
    crew_changes.note_update(line, before)
    return line


def _clear_request(line: CrewLine) -> None:
    """Forget the request of a line, or its firm planning: "not asked" (PER-016)."""
    if line.pk:
        price_offers.lapse_open_offers(line)  # PER-038
    line.request_status = RequestStatus.NONE
    line.requested_at = line.answered_at = None
    line.requested_by = None
    line.answer_note = ""
    line.requested_start = line.requested_end = None


def _set_firm(line: CrewLine) -> None:
    """PER-041: mark the line "planned firmly" for its present times – not saved here.

    ``requested_at`` and ``requested_by`` say when and by whom; the period
    is kept like the period of a request (PER-033).
    """
    if line.pk:
        price_offers.lapse_open_offers(line)  # PER-038: planned firmly – no request, no offer
    line.request_status = RequestStatus.FIRM
    line.requested_at = timezone.now()
    line.requested_by = _acting_user()
    line.answered_at = None
    line.answer_note = ""
    line.requested_start, line.requested_end = line.start, line.end


# --- Deployment requests (PER-016) -----------------------------------------------------


def _deployment_text(line: CrewLine) -> str:
    # The weekday in the language of the page ("Mi"), no longer the English one of ``strftime``.
    return _("%(project)s as %(function)s, %(start)s – %(end)s") % {
        "project": line.project,
        "function": line.job_function.name,
        "start": formats.date_format(timezone.localtime(line.start), local_pattern("D d.m. H:i")),
        "end": formats.date_format(timezone.localtime(line.end), local_pattern("D d.m. H:i")),
    }


def period_text(start: datetime.datetime, end: datetime.datetime) -> str:
    """``Mi 10.03. 08:00 – Fr 12.03. 18:00`` – a period in local time with German weekdays (PER-034)."""
    return f"{formats.date_format(timezone.localtime(start), local_pattern('D d.m. H:i'))} – " + formats.date_format(
        timezone.localtime(end), local_pattern("D d.m. H:i")
    )


def new_times_text(line: CrewLine, previous: tuple[datetime.datetime, datetime.datetime]) -> str:
    """``New times: Mi 10.03. 10:00 – Fr 12.03. 18:00 (before: Mi 10.03. 08:00 – Fr 12.03. 18:00)`` (PER-034)."""
    return _("New times: %(new)s (before: %(old)s)") % {
        "new": period_text(line.start, line.end),
        "old": period_text(*previous),
    }


def request_deployment(line: CrewLine, *, user: Any, also_changed: Iterable[Any] = ()) -> bool:
    """Ask the planned person whether they take the deployment (PER-016).

    A person with an account gets the request as a notification and answers
    in the application. For a person without an account the line is marked
    "asked" all the same – asked by phone – and the answer is entered by the
    planner.

    PER-032: with answers by reply mail (``MailSettings.crew_answers``) and a
    mailbox that Rentalars fetches, the mail of the request is one with the
    buttons "Accept" and "Decline" (``mail.crew_answers``) instead of the
    plain mail of the notification – also for a person who cannot log in.

    PER-033: the line remembers the period it was asked for
    (``requested_start``, ``requested_end``). An answered line – accepted or
    declined – is asked again only after its times changed; for the same
    times there is nothing new to answer, and the request is refused. A
    request still waiting may be sent again, e.g. after the address of the
    person was corrected. Asked again with other times, the notification
    and the mail name them: "New times: … (before: …)" (PER-034).

    PER-041: a line planned firmly is not asked – "planned firmly" is taken back
    first. ``also_changed`` – what else changed with the new times (meeting
    point, note …, see ``crew_changes.differences``) – is named in the
    notification too, so that the person gets one message, not two.

    Returns:
        Whether the person was told: by a notification or by the request mail.

    Raises:
        ValidationError: No person is planned, the project is closed, the
            person answered for these times already, or is planned firmly.
    """
    from rentalars.mail import crew_answers
    from rentalars.notifications.models import Kind
    from rentalars.notifications.services import notify
    from rentalars.projects.crew_changes import change_texts

    ensure_editable(line.project)
    if line.person_id is None:
        raise ValidationError(_("Plan a person first; an open place cannot be asked."))
    if line.request_status == RequestStatus.FIRM:
        raise ValidationError(
            _("%(person)s is planned firmly. Take “planned firmly” back in the crew line to ask instead.")
            % {"person": line.person.name}
        )
    if line.request_status in (RequestStatus.ACCEPTED, RequestStatus.DECLINED) and not line.times_changed_since_request:
        if line.request_status == RequestStatus.ACCEPTED:
            text = _("%(person)s has accepted for these times already. Ask again once the times change.")
        else:
            text = _("%(person)s has declined for these times already. Ask again once the times change.")
        raise ValidationError(text % {"person": line.person.name})
    previous = None
    if line.request_status and line.requested_start is not None and line.requested_end is not None:
        if (line.requested_start, line.requested_end) != (line.start, line.end):
            previous = (line.requested_start, line.requested_end)
    line.request_status = RequestStatus.REQUESTED
    line.requested_at = timezone.now()
    line.requested_by = user if getattr(user, "pk", None) else None
    line.answered_at = None
    line.answer_note = ""
    line.requested_start, line.requested_end = line.start, line.end
    line.save()
    # PER-038: a new request starts a new negotiation; with new times a total offer no longer holds.
    price_offers.on_new_request(line, times_changed=previous is not None)
    if previous is not None:
        record_event(
            line,
            "crew_line.asked_again_new_times",
            {"person": line.person.name, "new": period_text(line.start, line.end), "old": period_text(*previous)},
        )
    answer_mailbox = crew_answers.mailbox_for_request(line)
    account = getattr(line.person, "user", None)
    notified = False
    if account is not None and account.is_active:
        # UIX-029: in the language of the person asked.
        with for_user(account):
            if previous is not None:
                title = _("Deployment request with new times: %(deployment)s")
                body = "\n\n".join(part for part in (new_times_text(line, previous), line.note) if part)
            else:
                title, body = _("Deployment request: %(deployment)s"), line.note
            title = title % {"deployment": _deployment_text(line)}
            # PRJ-118: what else changed; the note is in the body already.
            others = [change for change in also_changed if change.field != "note"]
            body = "\n".join(part for part in (body, *change_texts(others)) if part)
        notify(
            [account],
            Kind.DEPLOYMENT_REQUEST,
            title,
            body=body,
            url="/",
            project=line.project,
            email=answer_mailbox is None,
        )
        notified = True
    if answer_mailbox is not None:
        crew_answers.send_request_mail(line, answer_mailbox, previous=previous)
        notified = True
    return notified


def _acting_user() -> Any:
    """The user whose request changes the line now, for "asked by" (PER-034); ``None`` for a command."""
    from rentalars.accounts.models import User
    from rentalars.core.audit import get_current_actor

    actor = get_current_actor()
    if actor is None or actor.user_id is None:
        return None
    return User.objects.filter(pk=actor.user_id).first()


def ask_again_for_new_times(line: CrewLine, *, user: Any = None, also_changed: Iterable[Any] = ()) -> bool | None:
    """Ask the person again after the times of a line changed – the automation of PER-034.

    Called by every service that changes the period of a line: editing it
    (:func:`update_crew_line`, browser and API) and moving a phase with its
    crew (:func:`move_with_phase`). Asked again is a line that

    * was asked for and is still waiting, or was accepted – a declined line
      is not asked again by itself; the planner may do it ("ask again"),
    * has times other than those the person was asked for, and
    * belongs to a project that is not cancelled, with a person still active,

    as long as the setting "ask again when the times change" is on
    (``SystemSettings.ask_again_on_new_times``, default on). The request is
    the one a planner makes (:func:`request_deployment`), naming the new and
    the former times; the line shows "asked" until the answer comes. "Asked
    by" is whoever changed the times – or, in a command, who asked before.

    PER-041: a line planned firmly is never asked again – the person is told
    the new times instead (``crew_changes.note_update``), as is a line not
    asked again for any other reason. ``also_changed`` goes into the request
    (:func:`request_deployment`).

    Returns:
        ``None`` if the line was not asked again; else whether the person
        was told (see :func:`request_deployment`). The line carries the
        same value as ``asked_again`` for the views.
    """
    from rentalars.core.models import SystemSettings

    if line.request_status not in (RequestStatus.REQUESTED, RequestStatus.ACCEPTED):
        return None
    if not line.times_changed_since_request or line.person_id is None or not line.person.is_active:
        return None
    if line.project.status == ProjectStatus.CANCELLED or not SystemSettings.load().ask_again_on_new_times:
        return None
    asker = user or _acting_user() or line.requested_by
    told = request_deployment(line, user=asker, also_changed=also_changed)
    line.asked_again = told  # type: ignore[attr-defined]
    return told


def answer_deployment(line: CrewLine, *, accept: bool, note: str = "", user: Any) -> CrewLine:
    """Accept or decline a deployment (PER-016).

    The person answers for themselves; a planner may enter the answer given
    by phone. The project manager and whoever asked are told.

    PER-042 (PER-021): an acceptance for a period in which the person's
    own availability calendar says "not available" enters "available" for
    exactly the period of the line (:func:`mark_available_for`) – whichever
    way the answer comes: the page, a planner, the API, the reply mail. The
    line carries the new entry as ``marked_available`` (else ``None``) for the
    confirmation. A line planned firmly (PER-041) is no acceptance and changes
    nothing.

    Raises:
        ValidationError: The line was not asked, is planned firmly without
            request (PER-041), or the project is closed.
    """
    from rentalars.notifications.models import Kind
    from rentalars.notifications.services import notify, project_people

    ensure_editable(line.project)
    if line.request_status in (RequestStatus.NONE, RequestStatus.FIRM) or line.person_id is None:
        raise ValidationError(_("This deployment was not asked for."))
    line.request_status = RequestStatus.ACCEPTED if accept else RequestStatus.DECLINED
    line.answered_at = timezone.now()
    line.answer_note = note.strip()[:250]
    line.save()
    price_offers.lapse_open_offers(line)  # PER-038: answered the plain way – no offer waits any more
    line.marked_available = mark_available_for(line) if accept else None  # type: ignore[attr-defined]
    verdict = gettext_lazy("accepted") if accept else gettext_lazy("declined")
    notify(
        [line.requested_by, *project_people(line.project)],
        Kind.DEPLOYMENT_ANSWER,
        # UIX-029: written for each recipient in his language.
        LocalText(
            gettext_lazy("%(person)s has %(verdict)s: %(deployment)s"),
            person=line.person.name,
            verdict=verdict,
            deployment=LazyCall(_deployment_text, line),
        ),
        body=line.answer_note,
        url=reverse("projects:overview", args=[line.project_id]),
        project=line.project,
        exclude=user,
    )
    return line


def mark_available_for(line: CrewLine) -> Any:
    """Enter "available" for the period of an accepted line where the person said "not available" (PER-042).

    The entry notes the deployment – "Zugesagt: P-2027-0001 Stadtfest – Tontechnik" in the person's language –
    and is an own entry of the person (``personnel.marks.mark_available_for_deployment``).

    Returns:
        The new ``AvailabilityMark``, or ``None`` if nothing changed.
    """
    from rentalars.personnel.marks import mark_available_for_deployment

    person = line.person
    with for_user(getattr(person, "user", None)):
        note = _("Accepted: %(deployment)s") % {
            "deployment": f"{line.project.number} {line.project.name} – {line.job_function.name}"
        }
    return mark_available_for_deployment(person, line.start, line.end, note)


def available_text(line: CrewLine, *, own: bool = True) -> str:
    """The sentence of the confirmation when "available" was entered (PER-042); empty when nothing was.

    ``own``: said to the person ("Für … ist jetzt „verfügbar“ eingetragen."), else to the planner who entered the
    answer for them, naming the person.
    """
    mark = getattr(line, "marked_available", None)
    if mark is None:
        return ""
    period = period_text(mark.start, mark.end)
    if own:
        return _("For %(period)s, “available” is entered now.") % {"period": period}
    return _("For %(period)s, “available” is entered now for %(person)s.") % {"period": period, "person": line.person}


def open_requests_of(person: Person) -> Any:
    """The deployments the person was asked for and has not answered yet."""
    return (
        person.crew_lines.filter(request_status=RequestStatus.REQUESTED, end__gte=timezone.now())
        .exclude(project__status__in=[ProjectStatus.CANCELLED, ProjectStatus.CLOSED])
        .select_related("project__parent", "job_function")
        .order_by("start")
    )


def delete_crew_line(line: CrewLine) -> None:
    """Delete a crew line.

    Time entries that were counted towards the line stay; they show up in the
    project again as times without crew line (ZEI-021).

    PRJ-118: the person of the line is told that they are no longer planned
    (``projects.crew_changes``).

    Raises:
        ValidationError: The project is closed.
    """
    from rentalars.projects import crew_changes

    ensure_editable(line.project)
    before = crew_changes.snapshot(line)
    line.delete()
    crew_changes.note_removed(before)


def move_with_phase(phase: ProjectPhase, old_start: datetime.datetime, old_end: datetime.datetime) -> list[CrewLine]:
    """Move the crew lines of a phase along after the phase's period changed (PRJ-080).

    Called by ``projects.course.update_phase`` when the planner keeps the box
    "move the crew of this phase along" ticked.

    * A line that had **exactly the old period** of the phase gets the new
      one – also when the phase only got longer or shorter.
    * Any **other** line of the phase is shifted by the change of the
      phase's start, as the clock on the wall sees it (as in duplicating,
      PRJ-029), and keeps its length: "setup 08–20, Anna 14–18" moved to
      10–22 puts Anna at 16–20. A phase that only changes its end leaves
      these lines where they are.
    * Such a line cannot end before it starts, as it keeps its length. Only
      in the hour skipped when summer time begins could the clock times come
      out reversed; the line then keeps its length in hours.
    * Nothing is cut or refused: neither crew lines nor phases are bound to
      the rental period of their project, of a subproject (PRJ-044) or of
      the phase. A line that now sticks out of the phase shows its own
      period on the page "Zeitplanung".
    * **Planned hours** follow the new period where they were the
      suggestion for the old one (PRJ-023, PRJ-073); typed-in hours stay.
      Days not typed in follow the period by themselves (PER-029). Rates
      stay, as for any change of the period (PRJ-021).

    Warnings – double booking, absence, availability (PRJ-022) – are not
    stored; they are found again for the moved lines wherever lines are
    shown, and the browser view reports them at once.

    PER-034: a moved line that was asked for or accepted asks its person
    again (:func:`ask_again_for_new_times`); such a line carries
    ``asked_again``. PRJ-118: the people of the other lines – planned firmly
    or not asked yet – are told the new times, one notification per person.

    Returns:
        The lines that moved.
    """
    from rentalars.projects import crew_changes

    ensure_editable(phase.project)
    shift = wall_clock_shift(phase.start, old_start)
    changed: list[CrewLine] = []
    with crew_changes.one_notice_per_person():
        for line in phase.crew_lines.select_related(
            "job_function", "person", "project", "service_product", "phase"
        ).order_by("start", "id"):
            line.phase = phase
            if (line.start, line.end) == (old_start, old_end):
                start, end = phase.start, phase.end
            else:
                start, end = moved(line.start, shift), moved(line.end, shift)
                if end <= start:
                    end = start + (line.end - line.start)
            if (start, end) == (line.start, line.end):
                continue
            before = crew_changes.snapshot(line)
            hours_follow_period = line.planned_hours == line.period_hours
            line.start, line.end = start, end
            if hours_follow_period:
                line.planned_hours = line.period_hours
            if line.request_status == RequestStatus.FIRM:
                line.requested_start, line.requested_end = start, end  # PER-041: firm for the new times, told
            line.full_clean()
            line.save()
            ask_again_for_new_times(line)
            crew_changes.note_update(line, before)
            changed.append(line)
    return changed


# --- Prices and costs (PRJ-051, PRJ-052, PRJ-061, PER-018) --------------------------


@dataclass
class CrewPrice:
    """What one crew line costs the customer and the company."""

    line: CrewLine
    planned_hours: Decimal
    #: Approved hours counted towards the line (ZEI-021).
    approved_hours: Decimal = ZERO
    #: The hours that are charged: planned, or approved for "by effort". ``None`` for a flat rate.
    charged_hours: Decimal | None = None
    #: Net amount for the customer.
    amount: Decimal = ZERO
    #: The amount before the discount, and the discount (PER-026).
    base_amount: Decimal = ZERO
    discount_amount: Decimal = ZERO
    #: The discount in percent as it applies: the line's, cut to the maximum of its job function (PER-026).
    discount_percent: Decimal = ZERO
    #: The maximum discount of the job function; ``None``: no limit (PER-026).
    max_discount_percent: Decimal | None = None
    #: ``True`` if the maximum cut the discount of the line (PER-026).
    discount_is_capped: bool = False
    #: ``True`` while a line billed by effort has no approved hours yet (PRJ-061).
    is_estimate: bool = False
    #: The days charged for a line billed per day (PER-029); ``None`` for any other line.
    days: int | None = None
    #: Planned internal cost: flat rate, days × day rate, or planned hours × hourly rate.
    cost: Decimal = ZERO
    #: ``True`` if the cost is the guide value of the job function, because nobody is planned yet (PRJ-052).
    cost_is_guide: bool = False
    #: The rate the cost was calculated with, per day or per hour; ``None`` for a flat rate or without any rate.
    cost_rate: Decimal | None = None
    #: ``True`` if the cost is days × day rate (PER-029); else hours × hourly rate or a flat rate.
    cost_per_day: bool = False
    #: What the approved times actually cost: hours × the rate fixed on each entry.
    actual_cost: Decimal = ZERO
    #: PER-035: the limit of hours per day if the line has hour tiers and is billed by the hour; else ``None``.
    hours_limit: Decimal | None = None
    #: PER-035: of the charged hours, those beyond the limit of their day – charged at ``unit_price_above_limit``.
    hours_above_limit: Decimal = ZERO
    unit_price_above_limit: Decimal | None = None
    #: PER-035: of the planned hours, those beyond the limit – costed at ``cost_rate_above_limit``.
    cost_hours_above_limit: Decimal = ZERO
    cost_rate_above_limit: Decimal | None = None
    #: PER-009: the surcharges for night, Sunday and holidays on the price, by kind – part of ``base_amount``.
    time_surcharges: list[SurchargePart] = field(default_factory=list)
    time_surcharge_amount: Decimal = ZERO
    #: PER-009: the surcharges on the planned cost, by kind – part of ``cost``.
    cost_time_surcharges: list[SurchargePart] = field(default_factory=list)
    cost_time_surcharge_amount: Decimal = ZERO
    #: PER-009: the surcharges on what the approved times cost – part of ``actual_cost``.
    actual_cost_time_surcharges: list[SurchargePart] = field(default_factory=list)
    actual_cost_time_surcharge_amount: Decimal = ZERO

    @property
    def has_hours_above_limit(self) -> bool:
        """PER-035: whether some charged hours are beyond the limit of their day."""
        return self.hours_above_limit > ZERO

    @property
    def normal_hours(self) -> Decimal | None:
        """PER-035: the charged hours up to the limit of their day; ``None`` without charged hours."""
        return self.charged_hours - self.hours_above_limit if self.charged_hours is not None else None

    @property
    def amount_above_limit(self) -> Decimal:
        """PER-035: what the hours beyond the limit cost before the discount."""
        if not self.hours_above_limit or self.unit_price_above_limit is None:
            return ZERO
        return money(self.hours_above_limit * self.unit_price_above_limit)

    @property
    def has_time_surcharges(self) -> bool:
        """PER-009: whether the price includes surcharges for night, Sunday or holidays."""
        return bool(self.time_surcharges)

    @property
    def amount_before_time_surcharges(self) -> Decimal:
        """PER-009: the amount for the hours alone, before surcharges and discount."""
        return self.base_amount - self.time_surcharge_amount

    @property
    def unit_kind(self) -> str:
        """What the customer is charged by: ``"hour"``, ``"day"`` (PER-029) or ``"flat"``."""
        if self.days is not None:
            return "day"
        return "flat" if self.charged_hours is None else "hour"

    @property
    def quantity(self) -> Decimal:
        """The charged quantity: hours, days, or 1 for a flat rate – for documents and exports."""
        if self.days is not None:
            return Decimal(self.days)
        return self.charged_hours if self.charged_hours is not None else Decimal("1")


class ApprovedTimes(NamedTuple):
    """The approved times counted towards one crew line (ZEI-021), with the entries for the hour tiers (PER-035)."""

    hours: Decimal = ZERO
    #: Hours × the rate fixed on each entry, without hour tiers.
    cost: Decimal = ZERO
    #: ``(local day of the start, hours, hourly rate)`` of each entry, in the order of their start.
    entries: tuple[tuple[datetime.date, Decimal, Decimal], ...] = ()
    #: PER-009: ``(start, end)`` of each entry, in the same order – for the surcharges for night, Sunday and holidays.
    periods: tuple[tuple[datetime.datetime, datetime.datetime | None], ...] = ()


#: A line without approved times.
NO_TIMES = ApprovedTimes()


def approved_times(entries: Any) -> dict[int, ApprovedTimes]:
    """Collect approved time entries by crew line – one query (ZEI-021, PER-035).

    Args:
        entries: A queryset of time entries, already narrowed to the
            approved ones with a crew line.
    """
    collected: dict[int, list[tuple[datetime.date, Decimal, Decimal]]] = defaultdict(list)
    periods: dict[int, list[tuple[datetime.datetime, datetime.datetime | None]]] = defaultdict(list)
    for line_id, hours, rate, start, end in entries.order_by("start", "pk").values_list(
        "crew_line_id", "hours", "hourly_rate", "start", "end"
    ):
        collected[line_id].append((timezone.localtime(start).date(), hours, rate))
        periods[line_id].append((start, end))  # PER-009
    return {
        line_id: ApprovedTimes(
            hours=sum((hours for _day, hours, _rate in rows), ZERO),
            cost=money(sum((hours * rate for _day, hours, rate in rows), ZERO)),
            entries=tuple(rows),
            periods=tuple(periods[line_id]),
        )
        for line_id, rows in collected.items()
    }


def approved_hours_by_line(project: Project) -> dict[int, ApprovedTimes]:
    """Return, per crew line of a project, the approved hours and what they cost (ZEI-021).

    Returns:
        ``{crew line id: ApprovedTimes}`` – unpacked like ``(hours, cost,
        entries)``; lines without approved times are missing.

    The time entries live in the module ``timetracking``, which builds on
    projects. To keep the dependency pointing one way only, the model is
    looked up by name here instead of being imported at the top.
    """
    entry_model = apps.get_model("timetracking", "TimeEntry")
    return approved_times(entry_model.objects.filter(project=project, status="approved", crew_line__isnull=False))


def price_crew_line(
    line: CrewLine,
    approved: ApprovedTimes | tuple[Decimal, Decimal] = NO_TIMES,
    rules: SurchargeRules | None = None,
) -> CrewPrice:
    """Calculate price and cost of one crew line (PRJ-051, PRJ-061, PER-018, PER-029).

    ===========  =======================================  ======================
    billing      amount for the customer                  example (45.00 / hour)
    ===========  =======================================  ======================
    by plan      planned hours × price                    8 h → 360.00
    flat rate    the price                                300.00
    by effort    approved hours × price; without          9.5 h → 427.50
                 approved hours: planned hours × price,   (before: 360.00,
                 marked as an estimate                    estimate)
    per day      days × price (the price is per day)      2 days at 400.00
                                                          → 800.00
    ===========  =======================================  ======================

    The days of a line per day are those typed in on the line, else the
    calendar days its period touches: Monday 08:00 to Tuesday 20:00 is 2.

    The discount of the line is taken off; it never exceeds the maximum
    discount of the job function (PER-026): with a maximum of 5 %, a line
    with 10 % discount gets 5 %.

    Cost: the flat rate agreed with the person if there is one (PER-018).
    Else, for a line billed per day, days × the day rate fixed on the line –
    or, without one, the day guide value of the job function (PER-029).
    Where there is no day rate at all, and for every other line, planned
    hours × the hourly rate fixed on the line (PRJ-021). An open place costs
    the guide values of its job function (PRJ-052). No query is needed: the
    job function comes with the line.

    Example (acceptance scenario 15): sound engineer, product D-001 at 45.00,
    person A with 35.00, 8 hours planned → price 360.00, cost 280.00. Per
    day: 2 days at 400.00 with a day rate of 280.00 → price 800.00, cost
    560.00.

    PER-035, hour tiers per day: on a line billed by plan or by
    effort with a limit of hours per day, the hours of one day beyond the
    limit cost the price from the limit – the planned hours per calendar
    day, or the approved times per day they start on (``projects.hour_tiers``).
    The cost of those planned hours is the rate from the limit: the person's
    own, else the person's hourly rate; for an open place or a person
    without own rate the guide value from the limit of the function, else its
    guide value per hour. The approved times cost the rate fixed on each
    entry, beyond the limit the rate from the limit of the line. Example:
    limit 10, 45.00 and 55.00 from the limit, 12 hours on one day → 10 ×
    45.00 + 2 × 55.00 = 560.00.
    """
    approved_hours, actual_cost, *rest = approved
    entries = rest[0] if rest else ()
    periods = rest[1] if len(rest) > 1 else ()
    price = CrewPrice(
        line=line, planned_hours=line.planned_hours, approved_hours=approved_hours, actual_cost=actual_cost
    )
    tiers = line.has_hour_tiers and line.unit_price_above_limit is not None
    planned_split = (
        split_at_limit(
            planned_hours_per_day(line.start, line.end, line.planned_hours, line.period_hours), line.hours_limit
        )
        if tiers
        else HourSplit(normal=line.planned_hours)
    )
    if tiers:
        price.hours_limit, price.unit_price_above_limit = line.hours_limit, line.unit_price_above_limit

    # PER-009: surcharges for night, Sunday and holidays – only for lines billed by the hour, as the hour tiers.
    by_hour = line.billing in (CrewBilling.PLAN, CrewBilling.EFFORT)
    surcharge_price = by_hour and line.time_surcharges_on_price
    surcharge_cost = by_hour and line.time_surcharges_on_cost and line.cost_flat_rate is None
    if (surcharge_price or surcharge_cost) and rules is None:
        rules = current_rules()
    limit = line.hours_limit if tiers else None
    timed = [(start, end, hours, rate) for (_day, hours, rate), (start, end) in zip(entries, periods, strict=False)]
    planned_cache: list[list[WorkPiece]] = []

    def planned() -> list[WorkPiece]:
        if not planned_cache:
            planned_cache.append(
                planned_pieces(line.start, line.end, line.planned_hours, line.period_hours, rules, limit)  # type: ignore[arg-type]
            )
        return planned_cache[0]

    def charge(split: HourSplit) -> Decimal:
        price.hours_above_limit = split.above
        above_price = line.unit_price_above_limit if line.unit_price_above_limit is not None else line.unit_price
        return money(split.normal * line.unit_price + split.above * above_price)

    def add_price_surcharges(pieces: list[WorkPiece]) -> None:
        if not surcharge_price:
            return
        above_price = line.unit_price_above_limit if line.unit_price_above_limit is not None else line.unit_price
        parts = surcharge_parts(
            pieces,
            PRICE,  # PER-040: the percentages of the rules for the price
            lambda piece: above_price if piece.above_limit else line.unit_price,
        )
        price.time_surcharges, price.time_surcharge_amount = parts, total_of(parts)
        price.base_amount += price.time_surcharge_amount

    if line.billing == CrewBilling.FLAT:
        price.base_amount = money(line.unit_price)
    elif line.billing == CrewBilling.DAY:
        price.days = line.effective_days
        price.base_amount = money(price.days * line.unit_price)
    elif line.billing == CrewBilling.EFFORT and approved_hours > ZERO:
        price.charged_hours = approved_hours
        if tiers and entries:
            price.base_amount = charge(split_at_limit(approved_hours_per_day(entries), line.hours_limit))
        else:
            price.base_amount = money(approved_hours * line.unit_price)
        if surcharge_price:
            add_price_surcharges(entry_pieces(timed, rules, limit))  # type: ignore[arg-type]
    else:
        price.charged_hours = line.planned_hours
        price.base_amount = charge(planned_split) if tiers else money(line.planned_hours * line.unit_price)
        price.is_estimate = line.billing == CrewBilling.EFFORT
        if surcharge_price:
            add_price_surcharges(planned())
    price.max_discount_percent = line.job_function.max_discount_percent
    price.discount_percent = limited_percent(line.discount_percent, price.max_discount_percent)
    price.discount_is_capped = price.discount_percent < line.discount_percent
    price.discount_amount = percentage_of(price.base_amount, price.discount_percent)
    price.amount = price.base_amount - price.discount_amount

    if line.cost_flat_rate is not None:
        price.cost = money(line.cost_flat_rate)
        return price
    if price.days is not None:
        # PER-029: per day the day rate – the person's own, else the day guide value of the function.
        own_daily = line.daily_rate if line.person_id is not None else None
        daily = own_daily if own_daily is not None else line.job_function.guide_daily_cost_rate
        if daily is not None:
            price.cost_per_day, price.cost_rate, price.cost_is_guide = True, daily, own_daily is None
            price.cost = money(price.days * daily)
            return price
    function = line.job_function
    if line.person_id is None or line.hourly_rate is None:
        # PER-029: a person without an own hourly rate costs the guide value, like an open place.
        rate = function.guide_cost_rate
        above = function.guide_cost_rate_above_limit if function.guide_cost_rate_above_limit is not None else rate
        price.cost_is_guide = True
    else:
        rate = line.hourly_rate
        above = line.hourly_rate_above_limit if line.hourly_rate_above_limit is not None else rate
    price.cost_rate = rate
    if rate is None:
        price.cost = ZERO
    elif tiers and planned_split.above > ZERO:
        # PER-035: the planned hours beyond the limit of their day at the rate from the limit.
        price.cost_hours_above_limit, price.cost_rate_above_limit = planned_split.above, above
        price.cost = money(planned_split.normal * rate + planned_split.above * above)
    else:
        price.cost = money(line.planned_hours * rate)
    if surcharge_cost and rate is not None:
        # PER-009: the planned hours at night, on Sundays and holidays – a percentage of the rate of their hour.
        parts = surcharge_parts(
            planned(),
            COST,  # PER-040: the percentages of the rules for the costs
            lambda piece: above if piece.above_limit else rate,
        )
        price.cost_time_surcharges, price.cost_time_surcharge_amount = parts, total_of(parts)
        price.cost += price.cost_time_surcharge_amount
    if tiers and entries:
        price.actual_cost = actual_cost_with_limit(entries, line.hours_limit, _actual_rate_above_limit(line))
    if surcharge_cost and timed:
        # PER-009: what the approved times cost more – of the rate fixed on each entry, beyond the limit of the
        # rate from the limit.
        rate_above = _actual_rate_above_limit(line) if tiers else None
        parts = surcharge_parts(
            entry_pieces(timed, rules, limit),  # type: ignore[arg-type]
            COST,
            lambda piece: rate_above if piece.above_limit and rate_above is not None else piece.rate,
        )
        price.actual_cost_time_surcharges, price.actual_cost_time_surcharge_amount = parts, total_of(parts)
        price.actual_cost += price.actual_cost_time_surcharge_amount
    return price


def _actual_rate_above_limit(line: CrewLine) -> Decimal | None:
    """PER-035: what an approved hour beyond the limit costs – ``None``: the rate fixed on the entry."""
    if line.person_id is not None and line.hourly_rate_above_limit is not None:
        return line.hourly_rate_above_limit
    if line.person_id is None or line.hourly_rate is None:
        return line.job_function.guide_cost_rate_above_limit
    return None


def load_crew_lines(project: Project) -> list[CrewLine]:
    """Load the crew lines of a project with everything the planning shows about them – the phase too (PRJ-080)."""
    return list(
        project.crew_lines.select_related("job_function", "person", "service_product", "tax_rate", "phase").order_by(
            "start", "position", "id"
        )
    )


def needs_surcharge_rules(lines: Iterable[CrewLine]) -> bool:
    """PER-009: whether one of the lines has surcharges switched on and is billed by the hour."""
    return any(
        line.billing in (CrewBilling.PLAN, CrewBilling.EFFORT)
        and (line.time_surcharges_on_price or line.time_surcharges_on_cost)
        for line in lines
    )


def surcharge_rules_for(lines: Iterable[CrewLine]) -> SurchargeRules | None:
    """PER-009: the settings of the surcharges, read once – only if one of the lines needs them."""
    return current_rules() if needs_surcharge_rules(lines) else None


def price_crew_lines(project: Project, lines: list[CrewLine] | None = None) -> list[CrewPrice]:
    """Calculate price and cost of all crew lines of a project, in display order.

    The settings of the surcharges are read once, and only if a line needs them (PER-009).
    """
    if lines is None:
        lines = load_crew_lines(project)
    if not lines:
        return []
    approved = approved_hours_by_line(project)
    rules = surcharge_rules_for(lines)
    return [price_crew_line(line, approved.get(line.pk, NO_TIMES), rules) for line in lines]


# --- Personnel by phase and job function (PRJ-088) ------------------------------------------


@dataclass
class FunctionShare:
    """One job function within a phase: how many places, how many hours or days, what for (PRJ-088)."""

    job_function: JobFunction
    places: int = 0
    #: Charged hours of the lines billed per hour (by plan, by effort).
    hours: Decimal = ZERO
    #: Charged days of the lines billed per day (PER-029).
    days: int = 0
    #: How many of the places are charged at a flat rate.
    flat: int = 0
    amount: Decimal = ZERO
    cost: Decimal = ZERO

    @property
    def margin(self) -> Decimal:
        """What remains of the amount after the cost (PRJ-025)."""
        return self.amount - self.cost

    @property
    def scope(self) -> str:
        """Hours and days in words: "16 Std.", "2 Tage", "pauschal" – or several of them."""
        parts = []
        if self.hours or not (self.days or self.flat):
            parts.append(f"{format_decimal(self.hours, max_places=2)} {_('h')}")
        if self.days:
            parts.append(ngettext("%(count)d day", "%(count)d days", self.days) % {"count": self.days})
        if self.flat:
            parts.append(_("flat"))
        return ", ".join(parts)


@dataclass
class PhaseShare:
    """The personnel of one phase, by job function – or of the lines without phase (PRJ-088)."""

    phase: ProjectPhase | None
    functions: list[FunctionShare] = field(default_factory=list)

    @property
    def amount(self) -> Decimal:
        """The subtotal of the phase for the customer."""
        return sum((share.amount for share in self.functions), ZERO)

    @property
    def cost(self) -> Decimal:
        """The planned cost of the phase."""
        return sum((share.cost for share in self.functions), ZERO)

    @property
    def margin(self) -> Decimal:
        """What remains of the subtotal after the cost."""
        return self.amount - self.cost

    @property
    def places(self) -> int:
        """How many crew lines the phase has."""
        return sum(share.places for share in self.functions)

    @property
    def label(self) -> str:
        """The name of the phase, or "Without phase"."""
        return self.phase.label if self.phase is not None else str(_("Without phase"))


def breakdown_by_phase(prices: Iterable[CrewPrice]) -> list[PhaseShare]:
    """Break the personnel down by phase and job function, for the price overview (PRJ-088).

    One block per phase that has crew lines, in the order of time, each with
    one row per job function (in the order of their names): the number of
    places, the charged hours or days, the amount and the cost. The lines
    without phase come last. The amounts of all blocks add up to the
    personnel total; nothing is looked up – the lines bring their phases
    along (:func:`load_crew_lines`).

    Example: setup with 2 stagehands of 8 hours at 28.00 and the event with 1
    sound engineer for 2 days at 400.00 give the blocks "Setup: Stagehand,
    2 places, 16 h, 448.00" and "Event: Tontechnik, 1 place, 2 days, 800.00".
    """
    blocks: dict[int | None, PhaseShare] = {}
    rows: dict[tuple[int | None, int], FunctionShare] = {}
    for price in prices:
        line = price.line
        phase = line.phase if line.phase_id else None
        block = blocks.get(line.phase_id)
        if block is None:
            block = blocks[line.phase_id] = PhaseShare(phase=phase)
        row = rows.get((line.phase_id, line.job_function_id))
        if row is None:
            row = rows[(line.phase_id, line.job_function_id)] = FunctionShare(job_function=line.job_function)
            block.functions.append(row)
        row.places += 1
        if price.days is not None:
            row.days += price.days
        elif price.charged_hours is None:
            row.flat += 1
        else:
            row.hours += price.charged_hours
        row.amount += price.amount
        row.cost += price.cost
    for block in blocks.values():
        block.functions.sort(key=lambda share: (share.job_function.name.lower(), share.job_function.pk))
    phased = [block for key, block in blocks.items() if key is not None and block.phase is not None]
    phased.sort(key=lambda block: (block.phase.start, block.phase.pk))  # type: ignore[union-attr]
    return phased + ([blocks[None]] if None in blocks else [])


# --- Conflicts (PRJ-022) ---------------------------------------------------------------


def crew_warnings(lines: list[CrewLine]) -> dict[int, list[str]]:
    """Find what is wrong with the planned people (PRJ-022).

    Three checks per line with a person:

    * **Double booking** – the person is planned somewhere else at the same
      time: in another line of this project or in another project that is
      not cancelled.
    * **Absence** – the period overlaps a holiday, a sick note or another
      absence of the person.
    * **Job function** – the person is planned in a function that is not
      among the person's own (possible with a special right, PER-006).
    * **Own availability** – the person marked the period "not available"
      or is busy in the linked calendar (PER-021, PER-022). "Available with
      limits" comes last, as a quieter hint (``warning.is_hint``).

    Nothing is blocked: the planner decides. The number of database queries
    does not grow with the number of lines (NFA-014).

    Returns:
        ``{crew line id: [warning, …]}`` for the lines that have warnings.
    """
    from rentalars.personnel.availability import mark_messages
    from rentalars.personnel.marks import effective_periods
    from rentalars.personnel.models import AvailabilityState

    staffed = [line for line in lines if line.person_id]
    if not staffed:
        return {}
    person_ids = {line.person_id for line in staffed}
    earliest = min(line.start for line in staffed)
    latest = max(line.end for line in staffed)

    elsewhere: dict[int, list[CrewLine]] = defaultdict(list)
    others = (
        CrewLine.objects.filter(person_id__in=person_ids, start__lt=latest, end__gt=earliest)
        .exclude(project__status=ProjectStatus.CANCELLED)
        .exclude(request_status=RequestStatus.DECLINED)  # L14: who said no is not planned elsewhere
        .select_related("project", "job_function")
    )
    for other in others:
        elsewhere[other.person_id].append(other)

    absences: dict[int, list[Absence]] = defaultdict(list)
    for absence in Absence.objects.filter(person_id__in=person_ids, start__lt=latest, end__gt=earliest):
        absences[absence.person_id].append(absence)

    # PER-027: one availability at any moment – where an own entry and a busy time meet, the newer counts.
    marks = {
        person_id: [
            period for period in periods if period.state in (AvailabilityState.UNAVAILABLE, AvailabilityState.LIMITED)
        ]
        for person_id, periods in effective_periods(person_ids, earliest, latest).items()
    }

    own_functions: set[tuple[int, int]] = set(
        apps.get_model("personnel", "PersonJobFunction")
        .objects.filter(person_id__in=person_ids)
        .values_list("person_id", "job_function_id")
    )

    warnings: dict[int, list[str]] = {}
    for line in staffed:
        found: list[str] = []
        for other in elsewhere[line.person_id]:
            if other.pk == line.pk or not (other.start < line.end and line.start < other.end):
                continue
            if other.project_id == line.project_id:
                found.append(
                    _("Planned twice in this project at the same time (also as %(function)s).")
                    % {"function": other.job_function}
                )
            else:
                # Only the number: the reader may not be allowed to open the other project (AUT-016).
                found.append(
                    _("Also scheduled for project %(number)s from %(start)s to %(end)s.")
                    % {
                        "number": other.project.number,
                        "start": timezone.localtime(other.start).strftime(local_pattern("%d.%m. %H:%M")),
                        "end": timezone.localtime(other.end).strftime(local_pattern("%d.%m. %H:%M")),
                    }
                )
        for absence in absences[line.person_id]:
            if absence.start < line.end and line.start < absence.end:
                found.append(
                    _("Absent (%(kind)s) from %(start)s to %(end)s.")
                    % {
                        "kind": absence.get_kind_display(),
                        "start": timezone.localtime(absence.start).strftime(local_pattern("%d.%m.%Y")),
                        "end": timezone.localtime(absence.end).strftime(local_pattern("%d.%m.%Y")),
                    }
                )
        said = mark_messages(
            [mark for mark in marks.get(line.person_id, []) if mark.start < line.end and line.start < mark.end]
        )
        found.extend(text for text in said if not getattr(text, "is_hint", False))
        if (line.person_id, line.job_function_id) not in own_functions:
            found.append(_("%(function)s is not among this person's job functions.") % {"function": line.job_function})
        found.extend(text for text in said if getattr(text, "is_hint", False))
        if found:
            warnings[line.pk] = found
    return warnings


# --- Times and crew lines (ZEI-021) --------------------------------------------------------


def matching_crew_line(
    project: Project, person: Person, job_function: JobFunction, start: datetime.datetime
) -> CrewLine | None:
    """Find the crew line a time entry counts towards (ZEI-021).

    That is the line of the same person and job function in the project. If
    there are several – the person works two days in the same function –
    the one whose period contains the start of the entry is taken, else the
    one that begins nearest to it.
    """
    candidates = list(project.crew_lines.filter(person=person, job_function=job_function))
    if not candidates:
        return None
    containing = [line for line in candidates if line.start <= start <= line.end]
    pool = containing or candidates
    return min(pool, key=lambda line: abs((line.start - start).total_seconds()))


def _attribute_entries_to(line: CrewLine) -> None:
    """After a person was put on a line: count that person's loose times in the project towards it."""
    if line.person_id is None:
        return
    entry_model = apps.get_model("timetracking", "TimeEntry")
    entry_model.objects.filter(
        project_id=line.project_id,
        person_id=line.person_id,
        job_function_id=line.job_function_id,
        crew_line__isnull=True,
    ).update(crew_line=line)


@dataclass
class LooseTimes:
    """Approved times of one person in one job function that belong to no crew line (ZEI-021)."""

    person: Person
    job_function: JobFunction
    hours: Decimal
    entry_ids: list[int] = field(default_factory=list)
    earliest: datetime.datetime | None = None
    latest: datetime.datetime | None = None

    @property
    def key(self) -> str:
        """Identifies the bundle in forms and API calls: ``<person id>-<job function id>``."""
        return f"{self.person.pk}-{self.job_function.pk}"


def unassigned_times(project: Project) -> list[LooseTimes]:
    """Return the approved times of a project that count towards no crew line (ZEI-021).

    They are shown in the project so that nothing worked is forgotten. Each
    bundle – one person in one job function – can be put on an existing line
    (:func:`assign_times`) or become a line of its own
    (:func:`adopt_times_as_line`).
    """
    entry_model = apps.get_model("timetracking", "TimeEntry")
    entries = (
        entry_model.objects.filter(project=project, status="approved", crew_line__isnull=True)
        .select_related("person", "job_function")
        .order_by("start")
    )
    bundles: dict[tuple[int, int], LooseTimes] = {}
    for entry in entries:
        key = (entry.person_id, entry.job_function_id)
        bundle = bundles.get(key)
        if bundle is None:
            bundle = bundles[key] = LooseTimes(person=entry.person, job_function=entry.job_function, hours=ZERO)
        bundle.hours += entry.hours
        bundle.entry_ids.append(entry.pk)
        bundle.earliest = min(bundle.earliest or entry.start, entry.start)
        bundle.latest = max(bundle.latest or entry.end, entry.end)
    return sorted(bundles.values(), key=lambda bundle: (bundle.person.sort_name.lower(), bundle.job_function.name))


@transaction.atomic
def assign_times(project: Project, person: Person, job_function: JobFunction, line: CrewLine) -> int:
    """Count the loose approved times of a person and job function towards a crew line (ZEI-021).

    Returns:
        The number of time entries that now belong to the line.

    Raises:
        ValidationError: The line belongs to another project or to another person.
    """
    ensure_editable(project)
    if line.project_id != project.pk:
        raise ValidationError(_("The crew line belongs to a different project."))
    if line.person_id is not None and line.person_id != person.pk:
        raise ValidationError(_("The crew line is planned for another person."))
    entry_model = apps.get_model("timetracking", "TimeEntry")
    changed = entry_model.objects.filter(
        project=project, person=person, job_function=job_function, status="approved", crew_line__isnull=True
    ).update(crew_line=line)
    record_event(line, "crew_line.times_assigned", {"person": person.name, "entries": changed})
    return changed


@transaction.atomic
def adopt_times_as_line(project: Project, person: Person, job_function: JobFunction, *, rights: Rights) -> CrewLine:
    """Turn loose approved times into a crew line of their own (ZEI-021).

    The new line covers the time from the first to the last entry, plans the
    hours that were worked, and is billed by effort: it exists because
    somebody worked, not because somebody planned.

    Raises:
        ValidationError: There are no loose times for this person and job function.
    """
    bundle = next(
        (
            bundle
            for bundle in unassigned_times(project)
            if bundle.person.pk == person.pk and bundle.job_function.pk == job_function.pk
        ),
        None,
    )
    if bundle is None:
        raise ValidationError(_("There are no approved times without crew line for this person and job function."))
    values = defaults_from_job_function(job_function)
    values["billing"] = CrewBilling.EFFORT
    last = project.crew_lines.aggregate(last=Max("position"))["last"] or 0
    rate = rate_for(person, job_function, bundle.earliest)
    line = CrewLine(
        project=project,
        job_function=job_function,
        person=person,
        start=bundle.earliest,
        end=bundle.latest,
        planned_hours=bundle.hours,
        hourly_rate=rate.own_hourly,
        daily_rate=rate.own_daily,
        position=last + 1,
        **values,
    )
    ensure_editable(project)
    line.full_clean()
    line.save()
    apps.get_model("timetracking", "TimeEntry").objects.filter(pk__in=bundle.entry_ids).update(crew_line=line)
    record_event(line, "crew_line.adopted_from_times", {"person": person.name, "hours": str(bundle.hours)})
    return line


def planned_and_actual(project: Project) -> list[dict[str, Any]]:
    """Compare planned and recorded hours per job function and person (PRJ-026).

    Returns:
        One row per job function and person (``person`` is ``None`` for open
        places) with ``planned``, ``approved`` and ``pending`` hours –
        pending being recorded or submitted, not yet approved.
    """
    entry_model = apps.get_model("timetracking", "TimeEntry")
    rows: dict[tuple[int, int | None], dict[str, Any]] = {}

    def row(job_function: JobFunction, person: Person | None) -> dict[str, Any]:
        key = (job_function.pk, person.pk if person else None)
        if key not in rows:
            rows[key] = {
                "job_function": job_function,
                "person": person,
                "planned": ZERO,
                "approved": ZERO,
                "pending": ZERO,
            }
        return rows[key]

    for line in project.crew_lines.select_related("job_function", "person"):
        row(line.job_function, line.person)["planned"] += line.planned_hours
    sums = (
        entry_model.objects.filter(project=project)
        .exclude(status="rejected")
        .values("job_function_id", "person_id", "status")
        .annotate(total=Sum("hours"))
    )
    functions = JobFunction.objects.in_bulk({entry["job_function_id"] for entry in sums})
    people = Person.objects.in_bulk({entry["person_id"] for entry in sums})
    for entry in sums:
        target = row(functions[entry["job_function_id"]], people[entry["person_id"]])
        target["approved" if entry["status"] == "approved" else "pending"] += entry["total"] or ZERO
    return sorted(
        rows.values(),
        key=lambda item: (
            item["job_function"].name.lower(),
            item["person"].sort_name.lower() if item["person"] else "",
        ),
    )
