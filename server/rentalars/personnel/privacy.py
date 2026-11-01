# SPDX-License-Identifier: GPL-3.0-or-later
"""Privacy for people: tell what is stored, and erase it (NFA-009).

Two rights of the persons concerned are served here:

**Information** – :func:`export_person` collects everything the system holds
about a person in one document: master data, job functions and rates,
absences, deployments, time entries. An administrator hands it over as a
file.

**Erasure** – :func:`anonymise_person` overwrites what identifies the person
and keeps what the company must keep: that *somebody* worked 8 hours on a
project still matters for the calculation of that project and for the books.
The name becomes "Anonymisiert (17)", contact data and notes are emptied,
absences and qualifications are deleted, the user account is unlinked, closed and stripped of
its name as well (``accounts.services.anonymise_user``). The step cannot be
undone.

A person who was never planned and never recorded a time can simply be
deleted (``personnel.services.delete_person``).
"""

from __future__ import annotations

from typing import Any

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.core.audit import AuditedModel, record_event
from rentalars.core.models import AuditLogEntry
from rentalars.personnel.models import (
    Absence,
    AvailabilityMark,
    CalendarFeed,
    CalendarPush,
    Person,
    PersonJobFunction,
    PriceOffer,
    Qualification,
)
from rentalars.personnel.services import rate_history

#: Text that replaces the last name of an anonymised person.
ANONYMISED_NAME = "Anonymisiert"

#: Free texts on crew lines and time entries; somebody may have written the person's name into them.
FREE_TEXT_FIELDS = frozenset(
    {"note", "meeting_point", "rejection_reason", "answer_note"}
)  # L11: the answer to a request

#: Events of the change log whose details contain the name of a person (see ``projects.crew``).
EVENTS_NAMING_A_PERSON = (
    "crew_line.times_assigned",
    "crew_line.adopted_from_times",
    "crew_line.offer_applied",  # PER-038
    "crew_line.offer_released",
)


def export_person(person: Person) -> dict[str, Any]:
    """Collect everything stored about a person as one JSON-compatible document (NFA-009).

    The document is meant for the person concerned, so it contains the
    person's own hourly rates as well.
    """
    crew_line_model = apps.get_model("projects", "CrewLine")
    entry_model = apps.get_model("timetracking", "TimeEntry")
    lines = crew_line_model.objects.filter(person=person).select_related("project", "job_function").order_by("start")
    entries = entry_model.objects.filter(person=person).select_related("project", "job_function").order_by("start")
    expense_model = apps.get_model("timetracking", "Expense")
    expenses = expense_model.objects.filter(person=person).select_related("project").order_by("date", "id")
    return {
        "exported_at": timezone.now().isoformat(),
        "person": {
            "id": person.pk,
            "first_name": person.first_name,
            "last_name": person.last_name,
            "kind": person.get_kind_display(),
            "email": person.email,
            "phone": person.phone,
            "note": person.note,
            "company": person.company,
            "street": person.street,
            "postal_code": person.postal_code,
            "city": person.city,
            # ZEI-027: the distance home – company, deducted from trips.
            "distance_home_company_km": str(person.commute_km) if person.commute_km is not None else None,
            "tax_number": person.tax_number,
            "vat_id": person.vat_id,
            "colleagues_may_see_phone": person.share_phone,
            "colleagues_may_see_email": person.share_email,
            "active": person.is_active,
            "created_at": person.created_at.isoformat(),
            "position": person.position,
            "user_account": person.user.username,
        },
        # PER-029: rates and "valid from" are optional; ``None`` is no own rate, or from always.
        "job_functions": [
            {
                "job_function": rate.job_function.name,
                "hourly_rate": str(rate.hourly_rate) if rate.hourly_rate is not None else None,
                "daily_rate": str(rate.daily_rate) if rate.daily_rate is not None else None,
                # PER-035: the rate of an hour beyond the limit of hours per day.
                "hourly_rate_above_limit": (
                    str(rate.hourly_rate_above_limit) if rate.hourly_rate_above_limit is not None else None
                ),
                "valid_from": rate.valid_from.isoformat() if rate.valid_from else None,
            }
            for rate in rate_history(person)
        ],
        "qualifications": [
            {
                "qualification": qualification.qualification_type.name,
                "details": qualification.detail,
                "acquired_on": qualification.acquired_on.isoformat() if qualification.acquired_on else None,
                "valid_until": qualification.valid_until.isoformat() if qualification.valid_until else None,
                "certificate": qualification.document_name or None,
            }
            for qualification in person.qualifications.select_related("qualification_type")
        ],
        "absences": [
            {
                "kind": absence.get_kind_display(),
                "from": absence.start.isoformat(),
                "until": absence.end.isoformat(),
                "note": absence.note,
            }
            for absence in person.absences.order_by("start")
        ],
        # PER-021 to PER-023: what the person said about their availability, and their calendar links
        # (without the secrets: the password is not even readable here).
        "availability": [
            {
                "state": mark.get_state_display(),
                "source": mark.get_source_display(),
                "from": mark.start.isoformat(),
                "until": mark.end.isoformat(),
                "note": mark.note,
            }
            for mark in person.availability_marks.order_by("start")
        ],
        "calendars": {
            # PER-031: every linked calendar, with the address – the document is for the person.
            "linked_calendars": [
                {
                    "name": feed.label,
                    "address": feed.url,
                    "last_read": feed.checked_at.isoformat() if feed.checked_at else None,
                }
                for feed in person.calendar_feeds.all()
            ],
            "caldav_calendar": person.caldav_url,
            "caldav_username": person.caldav_username,
            "subscription_link_active": bool(person.calendar_token),
        },
        "deployments": [
            {
                "project": line.project.number,
                "project_name": line.project.name,
                "job_function": line.job_function.name,
                "from": line.start.isoformat(),
                "until": line.end.isoformat(),
                "planned_hours": str(line.planned_hours),
                "hourly_rate": str(line.hourly_rate) if line.hourly_rate is not None else None,
                "flat_rate": str(line.cost_flat_rate) if line.cost_flat_rate is not None else None,
                "meeting_point": line.meeting_point,
                "note": line.note,
            }
            for line in lines
        ],
        "time_entries": [
            {
                "project": entry.project.number if entry.project_id else None,
                "job_function": entry.job_function.name,
                "start": entry.start.isoformat(),
                "end": entry.end.isoformat() if entry.end else None,
                "break_minutes": entry.break_minutes,
                "hours": str(entry.hours),
                "hourly_rate": str(entry.hourly_rate),
                "status": entry.get_status_display(),
                "note": entry.note,
            }
            for entry in entries
        ],
        # ZEI-019: expenses and travel costs; the receipts themselves are files of the company's books.
        "expenses": [
            {
                "project": expense.project.number,
                "kind": expense.get_kind_display(),
                "date": expense.date.isoformat(),
                "kilometres": str(expense.kilometres) if expense.kilometres is not None else None,
                "rate_per_kilometre": str(expense.km_rate) if expense.km_rate is not None else None,
                "amount": str(expense.amount),
                "note": expense.note,
                "receipt": bool(expense.receipt),
                "status": expense.status_label,
                "reimbursed_on": expense.reimbursed_on.isoformat() if expense.reimbursed_on else None,
            }
            for expense in expenses
        ],
        # PER-038: the price offers and counter-offers about the person's deployments – the document is for
        # the person, who sees their own amounts.
        "price_offers": [
            {
                "project": offer.line.project.number,
                "job_function": offer.line.job_function.name,
                "round": offer.round,
                "made_by": offer.get_side_display(),
                "amount": str(offer.amount),
                "unit": offer.get_unit_display(),
                "currency": offer.currency,
                "message": offer.message,
                "valid_until": offer.valid_until.isoformat() if offer.valid_until else None,
                "status": offer.get_status_display(),
                "made_at": offer.created_at.isoformat(),
                "decision_note": offer.decision_note,
            }
            for offer in person.price_offers.select_related("line__project", "line__job_function").order_by("id")
        ],
        # PRJ-108: the service cases the person takes part in.
        "service_cases": [
            {
                "service_case": participation.project.number,
                "job_function": participation.job_function.name if participation.job_function_id else None,
                "note": participation.note,
                "added": participation.created_at.isoformat(),
            }
            for participation in person.service_case_participations.select_related("project", "job_function")
        ],
    }


@transaction.atomic
def anonymise_person(person: Person) -> None:
    """Erase what identifies a person and keep the deployments and times (NFA-009).

    * Name, contact data, address, tax data and note are overwritten.
    * Absences and qualifications with their certificates are deleted; notes on the person's crew lines and time entries
      are emptied, because free text may name the person.
    * The user account – every person has one (AUT-026) – is closed and
      anonymised itself. An account with all rights is refused.
    * The availability marks and the calendar links with their secrets are
      erased (PER-021 to PER-023).
    * The change log would still contain the old values, so the logged field
      values of the person, of their rates and of their absences are removed,
      and the name disappears from the events that mention it.

    Crew lines and time entries stay, with their hours and rates: the
    calculation of old projects must remain complete.
    """
    if person.user.is_superuser:
        # Erasing the personnel data of the boss must not lock the company out of its own system.
        raise ValidationError(
            _("An account with all rights cannot be anonymised. Take the right away first (Settings → Users).")
        )
    person_type = ContentType.objects.get_for_model(Person)
    rate_type = ContentType.objects.get_for_model(PersonJobFunction)
    absence_type = ContentType.objects.get_for_model(Absence)
    qualification_type = ContentType.objects.get_for_model(Qualification)
    rate_ids = [str(pk) for pk in person.rates.values_list("pk", flat=True)]
    absence_ids = [str(pk) for pk in person.absences.values_list("pk", flat=True)]
    qualification_ids = [str(pk) for pk in person.qualifications.values_list("pk", flat=True)]
    offer_ids = [str(pk) for pk in person.price_offers.values_list("pk", flat=True)]

    # Removed without individual log entries: they would repeat what is being erased.
    Absence.objects.filter(person=person).delete()
    # PER-021 to PER-023, PER-031: availability, the calendar links and their secrets.
    AvailabilityMark.objects.filter(person=person).delete()
    CalendarFeed.objects.filter(person=person).delete()
    CalendarPush.objects.filter(person=person).delete()
    for qualification in person.qualifications.all():
        # PER-014: certificates are personal documents; they go with the file.
        if qualification.document:
            qualification.document.delete(save=False)
    Qualification.objects.filter(person=person).delete()
    apps.get_model("projects", "CrewLine").objects.filter(person=person).update(
        note="", meeting_point="", answer_note=""
    )
    apps.get_model("timetracking", "TimeEntry").objects.filter(person=person).update(note="", rejection_reason="")
    # ZEI-019: the notes of expenses as well; amounts and receipts stay – they belong to the books.
    apps.get_model("timetracking", "Expense").objects.filter(person=person).update(note="", rejection_reason="")
    # PER-038: the messages and reasons of price offers; the amounts stay – they belong to the books.
    person.price_offers.update(message="", decision_note="")
    # PRJ-108: the notes on taking part in service cases; the person stays a participant.
    apps.get_model("projects", "ServiceCaseParticipant").objects.filter(person=person).update(note="")

    user = person.user
    old_name = person.name
    person.first_name = ""
    person.last_name = f"{ANONYMISED_NAME} ({person.pk})"
    for name in (
        "email",
        "phone",
        "position",
        "note",
        "company",
        "street",
        "postal_code",
        "city",
        "tax_number",
        "vat_id",
    ):
        setattr(person, name, "")
    for name in (
        "calendar_token",
        "caldav_url",
        "caldav_username",
        "caldav_password_encrypted",
        "caldav_error",
    ):
        setattr(person, name, "")
    person.commute_km = None  # ZEI-027: where somebody lives, roughly
    person.share_phone = False
    person.share_email = False
    person.is_active = False
    person.anonymised_at = timezone.now()
    # Skip the field-by-field log for this save; an event is logged instead.
    super(AuditedModel, person).save()
    person._audit_snapshot = person._audit_values()

    # The account says who it was, too.
    from rentalars.accounts.services import anonymise_user

    anonymise_user(user)
    # AUT-028: the access log names neither the person nor, as a reader, their account.
    from rentalars.core.access_log import forget_person

    forget_person(person)
    # UIX-010, ADM-013: the chats and the runs of automations no longer name the person either.
    from rentalars.automations.engine import forget_name
    from rentalars.chat.services import forget_author

    forget_author(user, person.last_name)
    forget_name(old_name, person.last_name)

    AuditLogEntry.objects.filter(content_type=person_type, object_id=str(person.pk)).update(
        changes={}, object_repr=person.last_name
    )
    AuditLogEntry.objects.filter(content_type=rate_type, object_id__in=rate_ids).update(object_repr=ANONYMISED_NAME)
    AuditLogEntry.objects.filter(content_type=absence_type, object_id__in=absence_ids).update(
        changes={}, object_repr=ANONYMISED_NAME
    )
    AuditLogEntry.objects.filter(content_type=qualification_type, object_id__in=qualification_ids).update(
        changes={}, object_repr=ANONYMISED_NAME
    )
    # PER-038: the log of the offers kept their messages.
    AuditLogEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(PriceOffer), object_id__in=offer_ids
    ).update(changes={}, object_repr=ANONYMISED_NAME)
    # The log names crew lines and time entries by the person ("Tontechnik: Anna Beispiel"),
    # and it kept the free texts that were just emptied.
    for model_name, app_label in (("CrewLine", "projects"), ("TimeEntry", "timetracking"), ("Expense", "timetracking")):
        model = apps.get_model(app_label, model_name)
        ids = [str(pk) for pk in model.objects.filter(person=person).values_list("pk", flat=True)]
        logged = AuditLogEntry.objects.filter(content_type=ContentType.objects.get_for_model(model), object_id__in=ids)
        logged.update(object_repr=ANONYMISED_NAME)
        for entry in logged:
            if FREE_TEXT_FIELDS & set(entry.changes):
                entry.changes = {name: value for name, value in entry.changes.items() if name not in FREE_TEXT_FIELDS}
                entry.save(update_fields=["changes"])
    # Two events keep the name of the person whose times were moved; it goes too.
    named = AuditLogEntry.objects.filter(event__in=EVENTS_NAMING_A_PERSON, changes__person=old_name)
    for entry in named:
        entry.changes = {**entry.changes, "person": ANONYMISED_NAME}
        entry.save(update_fields=["changes"])
    record_event(person, "person.anonymised")
