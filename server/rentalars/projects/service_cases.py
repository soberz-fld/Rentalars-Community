# SPDX-License-Identifier: GPL-3.0-or-later
"""Service cases ("Servicefälle", PRJ-090).

A service case is the quick answer to a call or a mail that needs no
planning: a spotlight that flickers, a question about a manual, a repair.
It is a project of the kind ``service_case`` (``Project.kind``), so that it

* takes its number from the range of the projects – 2026-0042 may be a
  project, 2026-0043 a service case (PRJ-003);
* has the mail tag of a project: replies with ``[RL#2026-0043]`` in the
  subject land in the case, mails are written from it, and the
  correspondence is in one place (EML-009 ff.);
* has files, open items, a follow-up (PRJ-105), access and history like a
  project.

What makes it a case:

* It is created with a few fields: what it is about, the customer
  (required, as for a project – see :func:`require_customer`),
  who reported it, a description (optional) and who is responsible
  (``Project.manager``). From scratch, or from an inquiry without project
  tag under Projekte → Anfragen: the mail goes into the case.
* Statuses of its own (``Project.case_status``): open, in progress, done –
  and waiting (PRJ-112; for a reply, an action or a delivery),
  waiting to close and backlog, each set only together with a follow-up
  (:data:`FOLLOW_UP_STATUSES`, :func:`set_case_status`). A case in the backlog
  stays off the dashboards until its follow-up is due (:func:`off_dashboards`);
  it is listed under Projekte → Servicefälle. The project status stays
  "inquiry" and is not used.
* No planning: no material lines, no crew, no phases. It is therefore not
  in the availability, the calendar, the timelines and the shortages, and
  not in the list of projects; it has a list of its own (Projekte →
  Servicefälle).
* People can take part in it ("Beteiligte", PRJ-108): person,
  optional job function, note. They see the case under "My area", are
  told when added and record their times on it (ZEI-024). This is not
  crew planning – see ``add_participant``.
* It can be turned into a normal project – a repair that becomes a rental,
  say. It keeps its number, mails, files and history and starts as an
  inquiry with the periods given then.

The rental period of a project is required; a case gets one hour from its
creation as a stand-in. It is never shown, and the conversion asks for the
real periods.
"""

from __future__ import annotations

import datetime
import re
from email.utils import parseaddr
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Max, Q, QuerySet
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from rentalars.core.audit import record_event
from rentalars.core.i18n import LocalText
from rentalars.projects.models import CaseStatus, CaseWaitingFor, Project, ProjectKind, ProjectStatus

#: What can be set on a case when it is created or changed (PRJ-090).
#: MAT-057: ``is_internal`` – a case about the company's own material, without customer.
CASE_FIELDS = ("name", "customer", "is_internal", "contact", "case_contact", "notes", "manager")

#: The statuses the lists show unless asked otherwise: every case not done (PRJ-112: the backlog too – on the
#: dashboards :func:`off_dashboards` leaves it out until its follow-up is due).
ACTIVE_STATUSES = (
    CaseStatus.OPEN.value,
    CaseStatus.IN_PROGRESS.value,
    CaseStatus.WAITING.value,
    CaseStatus.CLOSING.value,
    CaseStatus.BACKLOG.value,
)

#: PRJ-112: the statuses that are set only together with a follow-up ("Wiedervorlage").
FOLLOW_UP_STATUSES = (CaseStatus.WAITING.value, CaseStatus.CLOSING.value, CaseStatus.BACKLOG.value)

#: "Re:", "AW:", "Fwd:" … in front of a subject, for the name of a case made from a mail.
_REPLY_PREFIX = re.compile(r"^\s*((re|aw|wg|fw|fwd|antw)\s*:\s*)+", re.IGNORECASE)


def stand_in_period() -> tuple[datetime.datetime, datetime.datetime]:
    """The rental period a case is stored with: one hour from now, to the minute. It is never shown."""
    start = timezone.now().replace(second=0, microsecond=0)
    return start, start + datetime.timedelta(hours=1)


def cases(queryset: QuerySet[Project] | None = None) -> QuerySet[Project]:
    """The service cases among the projects."""
    projects = Project.objects.all() if queryset is None else queryset
    return projects.filter(kind=ProjectKind.SERVICE_CASE)


def without_cases(queryset: QuerySet[Project]) -> QuerySet[Project]:
    """The projects without the service cases – for the lists, calendars and timelines of projects (PRJ-090)."""
    return queryset.exclude(kind=ProjectKind.SERVICE_CASE)


def off_dashboards(now: datetime.datetime | None = None) -> Q:
    """The cases in the backlog whose follow-up is not due yet (PRJ-112) – to exclude on the dashboards.

    The start page (its blocks and "My service cases"), My area → Service
    cases and Planning → Follow-ups leave them out by default; Projekte →
    Servicefälle lists them. From the moment the follow-up is due they show
    again (the default automation sets them to "open" then, ADM-013).
    """
    from rentalars.projects.follow_up import due_condition

    return Q(kind=ProjectKind.SERVICE_CASE, case_status=CaseStatus.BACKLOG) & ~due_condition(now)


def case_list(
    queryset: QuerySet[Project],
    *,
    statuses: list[str] | None = None,
    text: str = "",
    manager: Any = None,
    with_contacts: bool = True,
) -> QuerySet[Project]:
    """The cases for the list: by status (default: all not done, PRJ-112), text and the person responsible.

    Each case comes with ``mail_count`` and ``last_mail_at`` – one query for the page. PRJ-122: the text
    searches the customer's name in every role, who reported the case (``with_contacts``) only for who may see it.
    """
    from rentalars.projects import numbers as project_numbers

    found = cases(queryset)
    wanted = [status for status in (statuses or []) if status in CaseStatus.values]
    found = found.filter(case_status__in=wanted or ACTIVE_STATUSES)
    if text:
        condition = (
            project_numbers.matching(text)
            | Q(name__icontains=text)
            | Q(customer__name__icontains=text)
            | Q(notes__icontains=text)
        )
        if with_contacts:
            condition |= Q(case_contact__icontains=text)
        found = found.filter(condition)
    if manager is not None:
        found = found.filter(manager=manager)
    return (
        found.select_related("customer", "contact", "manager")
        .annotate(mail_count=Count("mails", distinct=True), last_mail_at=Max("mails__date"))
        .order_by("-created_at", "-pk")
    )


def _notify_responsible(case: Project, *, actor: Any) -> None:
    """Tell the person responsible that a case is theirs now – unless they did it themselves."""
    from rentalars.notifications.models import Kind
    from rentalars.notifications.services import notify

    if case.manager_id is None:
        return
    notify(
        [case.manager],
        Kind.PROJECT_CHANGE,
        # UIX-029: in the language of the one who reads it.
        LocalText(gettext_lazy("Service case %(number)s %(name)s is yours now"), number=case.number, name=case.name),
        url=reverse("projects:case_detail", args=[case]),
        project=case,
        exclude=actor,
    )


def require_customer(case: Project) -> None:
    """A service case needs a customer, like a project (PRJ-090).

    Checked when a case is created in the form or through the API – also
    from an inquiry – and whenever it is edited. Older cases
    without a customer stay valid until they are edited; the form then asks
    for one. A case that the mail fetching makes of a mail to an address set
    up so (EML-047) is still made when the sender is no known customer: an
    automation must not stop because of it; the person responsible chooses
    the customer when editing the case.

    MAT-057: an *internal* case – a repair of the company's own
    material, e.g. of a defect report – needs none; it has none, like an
    internal project.

    Raises:
        ValidationError: The case has no customer and is not internal.
    """
    if case.is_internal:
        case.customer = None
        case.contact = None
        return
    if case.customer_id is None:
        raise ValidationError({"customer": _("Choose the customer of the service case.")})


@transaction.atomic
def create_case(*, user: Any = None, customer_required: bool = False, **fields: Any) -> Project:
    """Create a service case with the next project number (PRJ-090, PRJ-003).

    Args:
        user: Who creates it; the person responsible is told unless it is them.
        customer_required: Refuse a case without customer (:func:`require_customer`);
            the form and the API ask for it, the mail fetching (EML-047) does not.
        **fields: ``name`` (required), ``customer``, ``is_internal``
            (MAT-057), ``contact``, ``case_contact``, ``notes``,
            ``manager``.

    Raises:
        ValidationError: A value is missing or invalid.
    """
    from rentalars.projects.services import _next_free_number

    unknown = set(fields) - set(CASE_FIELDS)
    if unknown:
        raise ValidationError(_("A service case has no field %(names)s.") % {"names": ", ".join(sorted(unknown))})
    start, end = stand_in_period()
    case = Project(
        kind=ProjectKind.SERVICE_CASE,
        case_status=CaseStatus.OPEN,
        status=ProjectStatus.INQUIRY,
        start=start,
        end=end,
        **fields,
    )
    if customer_required or case.is_internal:
        require_customer(case)
    case.number = _next_free_number()
    case.full_clean()
    case.save()
    _notify_responsible(case, actor=user)
    return case


def _ensure_case(case: Project) -> None:
    if not case.is_service_case:
        raise ValidationError(_("This is a project, not a service case."))


@transaction.atomic
def update_case(case: Project, *, user: Any = None, **changes: Any) -> Project:
    """Change what a case is about, its customer, contact, description or the person responsible (PRJ-090).

    An edited case needs a customer (:func:`require_customer`) –
    also a case of an earlier version that has none yet.
    """
    _ensure_case(case)
    unknown = set(changes) - set(CASE_FIELDS)
    if unknown:
        raise ValidationError(_("A service case has no field %(names)s.") % {"names": ", ".join(sorted(unknown))})
    old_manager = case.manager_id
    if "customer" in changes and changes["customer"] != case.customer and "contact" not in changes:
        # A contact of the former customer does not fit the new one.
        changes["contact"] = None
    if changes.get("customer") is not None and "is_internal" not in changes:
        # A customer chosen for an internal case – e.g. by a program that does not know
        # "intern" yet – makes it the customer's case instead of being dropped silently.
        changes["is_internal"] = False
    for name, value in changes.items():
        setattr(case, name, value)
    require_customer(case)
    case.full_clean()
    case.save()
    if case.manager_id != old_manager:
        _notify_responsible(case, actor=user)
    return case


@transaction.atomic
def set_case_status(
    case: Project,
    status: str,
    *,
    waiting_for: str = "",
    follow_up: dict[str, Any] | None = None,
    by: Any = None,
) -> Project:
    """Set the status of a case; any order is allowed (PRJ-090). The change log notes it.

    PRJ-112: *waiting*, *waiting to close* and *backlog*
    (:data:`FOLLOW_UP_STATUSES`) are set only together with a follow-up –
    ``follow_up`` with ``on`` (the day), ``at`` (the time), ``user`` (for
    whom; ``by`` when left out) and ``note``, as ``follow_up.set_follow_up``
    takes them. *Waiting* needs ``waiting_for`` (a reply, an action, a
    delivery); *waiting to close* needs the time as well – the case is closed
    then unless something happens before (ADM-013 default rules). Both are
    saved in one transaction: a refused follow-up keeps the old status. For
    the other statuses a follow-up given is set as well; one already there
    stays.

    Raises:
        ValidationError: Not a case, an unknown status, or – for the statuses
            above – no follow-up, no time, nothing to wait for, or a follow-up
            that ``set_follow_up`` refuses.
    """
    from rentalars.projects.follow_up import set_follow_up

    _ensure_case(case)
    if status not in CaseStatus.values:
        raise ValidationError(_("Unknown status of a service case."))
    follow_up = dict(follow_up or {})
    errors: dict[str, str] = {}
    if (status in FOLLOW_UP_STATUSES or follow_up) and follow_up.get("on") is None:
        errors["follow_up_on"] = _("Choose the day of the follow-up – this status needs one.")
    if status == CaseStatus.CLOSING and follow_up.get("at") is None:
        errors["follow_up_at"] = _("Choose the time at which the service case is closed.")
    if status == CaseStatus.WAITING and waiting_for not in CaseWaitingFor.values:
        errors["case_waiting_for"] = _("Choose what the service case is waiting for.")
    if errors:
        raise ValidationError(errors)
    if follow_up.get("on") is not None:
        set_follow_up(
            case,
            on=follow_up["on"],
            at=follow_up.get("at"),
            note=follow_up.get("note", ""),
            user=follow_up.get("user"),
            by=by,
            case_status=status,
        )
    waiting_for = waiting_for if status == CaseStatus.WAITING else ""
    if (case.case_status, case.case_waiting_for) != (status, waiting_for):
        case.case_status = status
        case.case_waiting_for = waiting_for
        case.save(update_fields=["case_status", "case_waiting_for"])
    return case


@transaction.atomic
def convert_to_project(case: Project, **fields: Any) -> Project:
    """Turn a service case into a normal project (PRJ-090).

    The project keeps number, mails, files, open items, follow-up and
    history; it starts as an inquiry. ``fields`` are those of the project
    form – the customer is needed now (or "internal"), and the rental period.

    Raises:
        ValidationError: It is not a service case, or a value is missing or invalid.
    """
    from rentalars.projects import services

    _ensure_case(case)
    case.kind = ProjectKind.PROJECT
    case.case_status = ""
    case.case_waiting_for = ""  # PRJ-112
    case.status = ProjectStatus.INQUIRY
    project = services.update_project(case, **fields)
    record_event(project, "service_case.converted", {"number": project.number})
    return project


# --- From an inquiry (Projekte → Anfragen, EML-041, EML-042) ---------------------------------------


def suggestions_from_inquiry(unknown: Any) -> dict[str, Any]:
    """What a mail without project tag suggests for a new case: the subject, and who sent it.

    A sender whose address is that of a contact of a customer brings the
    customer and the contact; another one is noted as "reported by".

    MAT-057: an entry made of a defect report suggests what the
    report says (``projects.defect_cases.suggestions``).

    EML-053: an inquiry noted by hand suggests its customer, the
    caller and its subject (``mail.inquiries.manual_suggestions``); taking it
    over makes it a note in the correspondence (``create_from_inquiry``).
    """
    from rentalars.customers.models import Contact, Customer

    if getattr(unknown, "defect_report_id", None):
        from rentalars.projects.defect_cases import suggestions

        return suggestions(unknown.defect_report)
    if getattr(unknown, "is_manual", False):
        from rentalars.mail.inquiries import manual_suggestions

        return manual_suggestions(unknown)

    name = _REPLY_PREFIX.sub("", unknown.subject or "").strip()[:200] or _("Inquiry by mail")
    display, address = parseaddr(unknown.sender or "")
    initial: dict[str, Any] = {"name": name}
    contact = (
        Contact.objects.filter(email__iexact=address).select_related("customer").order_by("pk").first()
        if address
        else None
    )
    if contact is not None:
        initial.update(customer=contact.customer, contact=contact)
        return initial
    customer = Customer.objects.filter(email__iexact=address).order_by("pk").first() if address else None
    if customer is not None:
        initial["customer"] = customer
    initial["case_contact"] = (f"{display} <{address}>" if display and address else (unknown.sender or ""))[:250]
    return initial


def create_from_inquiry(unknown: Any, *, user: Any = None, opener: Any = None, **fields: Any) -> Project:
    """Create a case and take the waiting mail into it (PRJ-090, EML-042).

    Both or neither: if the mail cannot be fetched from its mailbox, no case
    is created. MAT-057: of an entry made of a defect report the
    case takes the report and its photo; there is no mail to fetch.

    Raises:
        ValidationError: A value of the case is invalid.
        MailboxError: The mail is no longer in the inbox, or the mailbox cannot be reached.
    """
    from rentalars.mail.fetching import assign_unknown

    if getattr(unknown, "defect_report_id", None):
        from rentalars.projects.defect_cases import create_from_defect

        return create_from_defect(unknown.defect_report, user=user, **fields)
    with transaction.atomic():
        # PRJ-090: the customer is suggested from the sender's address, and is required.
        case = create_case(user=user, customer_required=True, **fields)
        assign_unknown(unknown, case, opener=opener)
    return case


# --- PRJ-108: people taking part in a case ------------------------------------------------------
#
# Not crew planning: a participant has no period, gets no deployment request,
# is not checked against availability and costs nothing in the plan. The
# person sees the case under "My area", is told when added, and finds the
# case first among the projects to record times on (ZEI-024). With a role for
# assigned projects only, taking part opens the case for reading
# (``projects.access``).


def _notify_participant(participation: Any, *, actor: Any) -> None:
    """Tell the person added that they take part in the case – unless they added themselves."""
    from rentalars.notifications.models import Kind
    from rentalars.notifications.services import notify

    case = participation.project
    person = participation.person
    if not person.user_id:
        return
    # UIX-029: in the language of the one who reads it; the note stays as typed.
    details: list[Any] = []
    if participation.job_function_id:
        details.append(LocalText(gettext_lazy("As: %(function)s"), function=participation.job_function.name))
    if participation.note:
        details.append(participation.note)
    body: Any = ""
    for line in details:
        body = line if body == "" else body + "\n" + line
    notify(
        [person.user],
        Kind.SERVICE_CASE,  # its own kind since the review: by mail and in the app by default
        LocalText(
            gettext_lazy("You take part in service case %(number)s %(name)s"), number=case.number, name=case.name
        ),
        body=body,
        url=reverse("projects:case_detail", args=[case]),
        project=case,
        exclude=actor,
    )


def _check_participant(case: Project, person: Any) -> None:
    _ensure_case(case)
    if person is None:
        raise ValidationError({"person": _("Choose the person.")})
    if not person.is_active or person.anonymised_at:
        raise ValidationError({"person": _("%(person)s is deactivated.") % {"person": person}})


@transaction.atomic
def add_participant(case: Project, person: Any, *, job_function: Any = None, note: str = "", user: Any = None) -> Any:
    """Add a person to a service case, or change function and note if the person takes part already (PRJ-108).

    The person is told about it unless they added themselves. The change
    log notes it in the history of the case (person and function as IDs).

    Raises:
        ValidationError: Not a service case, or the person or function is deactivated.
    """
    from rentalars.projects.models import ServiceCaseParticipant

    _check_participant(case, person)
    participation = ServiceCaseParticipant.objects.filter(project=case, person=person).first()
    if participation is not None:
        return update_participant(participation, job_function=job_function, note=note)
    if job_function is not None and not job_function.is_active:
        raise ValidationError({"job_function": _("This job function is deactivated.")})
    participation = ServiceCaseParticipant(
        project=case,
        person=person,
        job_function=job_function,
        note=(note or "").strip(),
        added_by=user if getattr(user, "is_authenticated", False) else None,
    )
    participation.full_clean()
    participation.save()
    _notify_participant(participation, actor=user)
    return participation


def update_participant(participation: Any, *, job_function: Any = None, note: str = "") -> Any:
    """Change the job function and the note of a person taking part (PRJ-108)."""
    if job_function is not None and job_function.pk != participation.job_function_id and not job_function.is_active:
        raise ValidationError({"job_function": _("This job function is deactivated.")})
    participation.job_function = job_function
    participation.note = (note or "").strip()
    participation.full_clean()
    participation.save()
    return participation


def remove_participant(participation: Any) -> None:
    """Take a person off a service case (PRJ-108). Their times on the case stay."""
    participation.delete()


def participants_of(case: Project) -> QuerySet[Any]:
    """The people taking part in a case, in the order they were added."""
    return case.participants.select_related("person", "job_function", "added_by")


def cases_of(
    person: Any, user: Any = None, *, statuses: list[str] | None = None, with_backlog: bool = False
) -> QuerySet[Project]:
    """The service cases a person takes part in – and, with ``user``, those that user is responsible for (PRJ-108).

    Default: every case not done, without those in the backlog whose
    follow-up is not due yet (PRJ-112, :func:`off_dashboards`) unless
    ``with_backlog``. Each case comes with ``my_participation`` (a list of at
    most one ``ServiceCaseParticipant``) for the job function and note of the
    person.
    """
    from django.db.models import Prefetch

    from rentalars.projects.models import ServiceCaseParticipant

    condition = Q(participants__person=person) if person is not None else Q(pk__in=[])
    if user is not None and getattr(user, "is_authenticated", False):
        condition |= Q(manager=user)
    wanted = [status for status in (statuses or []) if status in CaseStatus.values] or list(ACTIVE_STATUSES)
    found = cases().filter(condition, case_status__in=wanted).distinct()
    if not with_backlog:
        found = found.exclude(off_dashboards())
    return found.select_related("customer", "manager").prefetch_related(
        Prefetch(
            "participants",
            queryset=ServiceCaseParticipant.objects.filter(person=person).select_related("job_function"),
            to_attr="my_participation",
        )
    )
