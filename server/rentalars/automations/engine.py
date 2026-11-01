# SPDX-License-Identifier: GPL-3.0-or-later
"""Running automations: events, conditions, actions, protection against loops (ADM-013).

Recording
---------
Where something happens, an *event* is handed to :func:`fire`:

* ``mail.fetching`` – a mail without project tag was taken in as an inquiry
  (:func:`inquiry_arrived`);
* ``automations.signals`` – a project was saved with another status, a crew
  line with an answer (:func:`project_reached_status`,
  :func:`crew_answer_arrived`); whichever way it was saved – by hand, by
  packing, by mail, through the API;
* ``projects.follow_up.notify_due_follow_ups`` – a follow-up is due
  (:func:`follow_up_due`); for a service case also :func:`case_follow_up_due`
  (PRJ-112), with the status of the case as condition;
* ``automations.signals`` – a mail of a service case was stored (received,
  sent, or assigned to it by hand) or a chat message written in it
  (:func:`case_communication`, PRJ-112);
* ``automations.signals`` – MAT-057: a defect was reported, on the
  item's page, on return or through the API (:func:`defect_reported`); the
  actions make a service case of it (:func:`_create_case`) or put it under
  Projekte → Anfragen (:func:`_create_inquiry`) – once per report.

Loop protection for the service cases (PRJ-112): setting a status is no
event, and what happens while a rule is carried out – a mail it sends, an open
item it notes – is not "new communication" (:func:`automation_running`);
automatic replies and delivery failures are not communication either.

:func:`fire` looks for the active rules of the trigger whose condition holds
and writes one :class:`~rentalars.automations.models.AutomationRun` per rule,
**in the transaction of the change**: a change that is rolled back runs
nothing. ``event_key`` names the event, so that no rule runs twice for it –
the same mail fetched from two mailboxes is one event. Recording never
raises: a problem is logged and the change goes on.

Running
-------
Once the change is committed, the runs are carried out at once
(:func:`run_pending`); the minute timer (``run_jobs``) takes what is left –
e.g. after a restart. A run is *claimed* before it is carried out, so two
processes never carry out the same. A run that was interrupted is marked as
failed, never repeated: an answer by mail must not go out twice.

Every run ends as *done*, *left out* (with the reason) or *failed* (with the
error) and is listed under Einstellungen → Automationen.

The answer by mail – and why it cannot loop
-------------------------------------------
EML-030 says that Rentalars answers no mail by itself. ADM-013 makes the
deliberate exception: a rule may answer a mail without project tag, e.g.
with a confirmation of receipt. So that automatic answers cannot set each
other off, a mail is *never* answered when

* it is marked as sent automatically – ``Auto-Submitted`` (other than
  ``no``), ``Precedence: bulk/junk/list``, ``List-Id``, ``List-Unsubscribe``,
  ``X-Autoreply``, ``X-Autorespond``, ``X-Auto-Response-Suppress``, an empty
  ``Return-Path``, a delivery report (``mail.parsing.automatic_reason``);
* its sender is a mail system or does not take answers – ``mailer-daemon``,
  ``postmaster``, ``no-reply``/``noreply``, ``bounce`` …;
* its sender is one of Rentalars' own addresses – a mailbox, the sender of
  the system mails, the company's address;
* the same rule answered the same sender today already (at most one
  automatic answer per sender, rule and day).

The answer itself carries ``Auto-Submitted: auto-replied`` and
``X-Auto-Response-Suppress: All``, refers to the mail (``In-Reply-To``),
goes to ``Reply-To`` or else the sender, and ends with the footer of every
mail Rentalars sends by itself (EML-045). It goes out through the mailbox the
mail came into – or, if that one cannot send, through the mailbox that sends
the correspondence – and is noted in the mail log as "automatic answer".

Placeholders
------------
Texts may contain ``{name}``-style placeholders, German like those of the
signature (EML-034); :data:`PLACEHOLDERS` lists which trigger offers which.
An unknown placeholder stays as it is.
"""

from __future__ import annotations

import contextvars
import datetime
import logging
import re
import uuid
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr, formatdate, getaddresses, make_msgid, parseaddr
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import formats, timezone, translation
from django.utils.text import capfirst
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from rentalars.automations.models import (
    CASE_TRIGGERS,
    OPEN_ITEM_LENGTH,
    Action,
    Automation,
    AutomationRun,
    CrewAnswer,
    Recipient,
    RunStatus,
    Trigger,
)
from rentalars.core.i18n import LazyCall, LocalText, local_pattern

if TYPE_CHECKING:
    from rentalars.mail.models import Mailbox, UnknownTagMail
    from rentalars.mail.parsing import Headers
    from rentalars.material.models import DefectReport
    from rentalars.projects.models import CrewLine, Project

logger = logging.getLogger(__name__)

#: Runs carried out at most in one go.
RUN_LIMIT = 100

#: A run still "running" after this long was interrupted.
STALE_AFTER = datetime.timedelta(minutes=10)

#: Local parts of addresses that never get an automatic answer.
_NO_ANSWER_LOCAL = re.compile(
    r"^(mailer-daemon|postmaster|no[-_.]?reply|do[-_.]?not[-_.]?reply|bounces?|daemon|listserv|majordomo)"
    r"([-+_.].*)?$",
    re.IGNORECASE,
)

#: The placeholders per trigger: token and what it stands for (for the form and the manual).
PLACEHOLDERS: dict[str, list[tuple[str, Any]]] = {
    "all": [
        ("{firma}", gettext_lazy("company name")),
        ("{datum}", gettext_lazy("today's date")),
    ],
    Trigger.INQUIRY: [
        ("{name}", gettext_lazy("name of the sender, else the address")),
        ("{absender}", gettext_lazy("address of the sender")),
        ("{betreff}", gettext_lazy("subject of the mail")),
        ("{postfach}", gettext_lazy("mailbox")),
        # KND-004: the greeting set for the contact with that address; "Guten Tag," for anybody else.
        ("{anrede}", gettext_lazy("greeting of the sender")),
    ],
    "project": [
        ("{projekt}", gettext_lazy("number and name of the project")),
        ("{projektnummer}", gettext_lazy("project number")),
        ("{projektname}", gettext_lazy("project name")),
        ("{status}", gettext_lazy("status of the project")),
        ("{projektleitung}", gettext_lazy("project manager")),
        ("{link}", gettext_lazy("address of the project in Rentalars")),
    ],
    Trigger.CREW_ANSWER: [
        ("{person}", gettext_lazy("person who answered")),
        ("{antwort}", gettext_lazy("acceptance or refusal")),
        ("{funktion}", gettext_lazy("job function")),
        ("{einsatz}", gettext_lazy("period of the deployment")),
        ("{anmerkung}", gettext_lazy("note of the answer")),
    ],
    Trigger.FOLLOW_UP: [
        ("{wiedervorlage}", gettext_lazy("day of the follow-up")),
        ("{notiz}", gettext_lazy("note of the follow-up")),
        ("{fuer}", gettext_lazy("whom the follow-up is for")),
    ],
    # PRJ-112: ``{status}`` is the status of the service case.
    Trigger.CASE_COMMUNICATION: [
        ("{kommunikation}", gettext_lazy("the mail or chat message, in a few words")),
    ],
}
PLACEHOLDERS[Trigger.CASE_FOLLOW_UP] = PLACEHOLDERS[Trigger.FOLLOW_UP]
# MAT-057: a defect report – no project.
PLACEHOLDERS[Trigger.DEFECT] = [
    ("{id}", gettext_lazy("ID of the item")),
    ("{modell}", gettext_lazy("material model")),
    ("{kurzname}", gettext_lazy("short name of the model")),
    ("{produkt}", gettext_lazy("product")),
    ("{seriennummer}", gettext_lazy("serial number")),
    ("{beschreibung}", gettext_lazy("what is defective")),
    ("{gefunden}", gettext_lazy("where it was found, e.g. on return of a project")),
    ("{gemeldet_von}", gettext_lazy("who reported it")),
    ("{gemeldet_am}", gettext_lazy("when it was reported")),
    ("{link}", gettext_lazy("address of the item in Rentalars")),
]

#: The triggers without a project: their placeholders are their own and the common ones.
_WITHOUT_PROJECT = (Trigger.INQUIRY, Trigger.DEFECT)

#: UIX-029: the English names of the placeholders; both names work in every text, in either language.
ENGLISH_PLACEHOLDERS = {
    "company": "firma",
    "date": "datum",
    "sender": "absender",
    "subject": "betreff",
    "mailbox": "postfach",
    "greeting": "anrede",
    "project": "projekt",
    "project_number": "projektnummer",
    "project_name": "projektname",
    "project_manager": "projektleitung",
    "answer": "antwort",
    "job_function": "funktion",
    "deployment": "einsatz",
    "note": "anmerkung",
    "follow_up": "wiedervorlage",
    "follow_up_note": "notiz",
    "for": "fuer",
    "communication": "kommunikation",
    # MAT-057
    "model": "modell",
    "short_name": "kurzname",
    "product": "produkt",
    "serial_number": "seriennummer",
    "description": "beschreibung",
    "found": "gefunden",
    "reported_by": "gemeldet_von",
    "reported_at": "gemeldet_am",
}
_GERMAN_TO_ENGLISH = {german: english for english, german in ENGLISH_PLACEHOLDERS.items()}


def shown_token(token: str) -> str:
    """A placeholder as the form offers it: ``{firma}`` in German, ``{company}`` in English (UIX-029)."""
    from rentalars.core.i18n import is_english

    name = token.strip("{}")
    return "{" + _GERMAN_TO_ENGLISH.get(name, name) + "}" if is_english() else token


def placeholders_of(trigger: str) -> list[tuple[str, Any]]:
    """The placeholders a trigger offers, the common ones last."""
    own = list(PLACEHOLDERS.get(trigger, []))
    if trigger not in _WITHOUT_PROJECT:
        own = PLACEHOLDERS["project"] + own
    return [(shown_token(token), label) for token, label in own + PLACEHOLDERS["all"]]


_TOKEN = re.compile(r"\{(\w+)\}")


def fill(text: str, values: dict[str, str]) -> str:
    """Put the values into the placeholders of a text; unknown placeholders stay.

    UIX-029: the English names (``{company}``, ``{date}`` …, :data:`ENGLISH_PLACEHOLDERS`) work as well.
    """

    def value(hit: re.Match[str]) -> str:
        name = hit.group(1).lower()
        if name not in values:
            name = ENGLISH_PLACEHOLDERS.get(name, name)
        return str(values.get(name, hit.group(0)))

    return _TOKEN.sub(value, text or "")


# --- Events ----------------------------------------------------------------------------------------


@dataclass
class Event:
    """Something that happened, as the rules and the runs need it."""

    trigger: str
    #: Names the event: no rule runs twice for the same key.
    key: str
    #: In a few words, for the list of runs.
    summary: str
    project: Project | None = None
    mailbox_id: int | None = None
    status: str = ""
    answer: str = ""
    #: PRJ-112: the kind of communication in a service case (``Communication``).
    communication: str = ""
    #: The values of the placeholders.
    values: dict[str, str] = field(default_factory=dict)
    #: What else the actions need: the address to answer, the user who asked …
    data: dict[str, Any] = field(default_factory=dict)


def _matches(rule: Automation, event: Event) -> bool:
    """Whether the condition of a rule holds for an event."""
    if rule.trigger == Trigger.INQUIRY:
        return rule.mailbox_id is None or rule.mailbox_id == event.mailbox_id
    if rule.trigger == Trigger.PROJECT_STATUS:
        return rule.status == event.status
    if rule.trigger == Trigger.CREW_ANSWER:
        return rule.answer in (CrewAnswer.ANY, event.answer)
    if rule.trigger in CASE_TRIGGERS:
        # PRJ-112: the status of the case when it happened (empty: any), and the kind of communication.
        if rule.status and rule.status != event.status:
            return False
        return rule.trigger != Trigger.CASE_COMMUNICATION or rule.communication in ("", event.communication)
    return True


def fire(event: Event) -> list[AutomationRun]:
    """Record a run for every active rule the event starts; carried out once the change is committed.

    Never raises: a problem is logged, and the change goes on.
    """
    try:
        rules = [
            rule for rule in Automation.objects.filter(is_active=True, trigger=event.trigger) if _matches(rule, event)
        ]
        if not rules:
            return []
        runs = []
        for rule in rules:
            run = AutomationRun(
                automation=rule,
                automation_name=rule.name[:120],
                trigger=event.trigger,
                action=rule.action,
                event_key=event.key[:120],
                project=event.project if getattr(event.project, "pk", None) else None,
                event=event.summary[:300],
                data={"values": event.values, **event.data},
            )
            try:
                # A savepoint: the same event a second time is refused by the database and skipped here.
                with transaction.atomic():
                    run.save()
            except IntegrityError:
                continue
            runs.append(run)
        if runs:
            ids = [run.pk for run in runs]
            transaction.on_commit(lambda: run_pending(ids))
        return runs
    except Exception:
        logger.exception("The automations of the event %s could not be recorded.", event.key)
        return []


def _language() -> str:
    """UIX-029: the language the automations write in – that of the company's documents, as they write to customers."""
    from rentalars.core.i18n import document_language

    return document_language()


def _base_values() -> dict[str, str]:
    from rentalars.core.models import CompanyProfile

    return {
        "firma": CompanyProfile.load().name,
        "datum": formats.date_format(timezone.localdate(), local_pattern("d.m.Y")),
    }


def _project_values(project: Project) -> dict[str, str]:
    from rentalars.projects.models import ProjectStatus

    manager = project.manager if project.manager_id else None
    values = {
        "projekt": f"{project.number} {project.name}",
        "projektnummer": project.number,
        "projektname": project.name,
        "status": str(ProjectStatus(project.status).label)
        if project.status in ProjectStatus.values
        else project.status,
        "projektleitung": (manager.get_full_name() or manager.username) if manager is not None else "",
        "link": f"{settings.RENTALARS_URL}{reverse('projects:overview', args=[project.pk])}",
    }
    if project.is_service_case:
        # PRJ-112: a service case has a status of its own and a page of its own.
        values["status"] = project.case_status_label
        values["link"] = f"{settings.RENTALARS_URL}{reverse('projects:case_detail', args=[project.pk])}"
    return values


def _has_rules(trigger: str) -> bool:
    return Automation.objects.filter(is_active=True, trigger=trigger).exists()


def _greeting_of_sender(address: str) -> str:
    """The greeting for the sender of an inquiry: that of its contact (KND-004), else a plain "Guten Tag,"."""
    from rentalars.customers import greetings

    return greetings.greeting_for_address(address) or greetings.generic_greeting()


def inquiry_arrived(
    waiting: UnknownTagMail, headers: Headers, mailbox: Mailbox, *, project: Project | None = None, address: str = ""
) -> list[AutomationRun]:
    """A mail without project tag was taken in by a mailbox (EML-041, EML-042).

    EML-047: ``address`` – the further address of the mailbox the mail
    went to, if one is listed; an answer goes out from it. ``project`` – the
    service case made of the mail at once, if its address is set so.
    """
    if not _has_rules(Trigger.INQUIRY):
        return []
    own_address = address
    with translation.override(_language()):
        name, address = parseaddr(headers.sender)
        reply_pairs = [pair for pair in getaddresses([headers.reply_to]) if pair[1]] if headers.reply_to else []
        reply_name, reply_address = reply_pairs[0] if reply_pairs else (name, address)
        values = {
            **_base_values(),
            "name": name or address,
            "absender": address,
            "betreff": headers.subject,
            "postfach": mailbox.name,
            "anrede": _greeting_of_sender(address),
        }
        event = Event(
            trigger=Trigger.INQUIRY,
            key=f"mail:{headers.key}",
            summary=_("Mail from %(sender)s: %(subject)s") % {"sender": address or "?", "subject": headers.subject},
            mailbox_id=mailbox.pk,
            project=project,
            values=values,
            data={
                "own_address": own_address,
                "sender": address,
                "answer_to": reply_address,
                "answer_name": reply_name or name,
                "subject": headers.subject,
                "message_id": headers.message_id,
                "references": headers.references,
                "automatic": headers.automatic,
                "mailbox": mailbox.pk,
                "waiting": waiting.pk,
            },
        )
    return fire(event)


def project_reached_status(project: Project, old_status: str | None) -> list[AutomationRun]:
    """A project was saved with another status – or created with one (PRJ-008)."""
    if not _has_rules(Trigger.PROJECT_STATUS):
        return []
    from rentalars.projects.models import ProjectStatus

    with translation.override(_language()):
        values = {**_base_values(), **_project_values(project)}
        old = str(ProjectStatus(old_status).label) if old_status in ProjectStatus.values else ""
        summary = (
            f"{project.number} {project.name}: {old} → {values['status']}"
            if old
            else f"{project.number} {project.name}: {values['status']}"
        )
        event = Event(
            trigger=Trigger.PROJECT_STATUS,
            # Every save that changes the status is an event of its own.
            key=f"status:{project.pk}:{project.status}:{timezone.now().isoformat()}:{uuid.uuid4().hex[:12]}",
            summary=summary,
            project=project,
            status=project.status,
            values=values,
            data={"old_status": old_status or ""},
        )
    return fire(event)


def crew_answer_arrived(line: CrewLine) -> list[AutomationRun]:
    """A deployment request was accepted or declined – in the browser, by mail, through the API (PER-016, PER-032)."""
    if not _has_rules(Trigger.CREW_ANSWER):
        return []
    from rentalars.projects.models import RequestStatus

    project = line.project
    with translation.override(_language()):
        accepted = line.request_status == RequestStatus.ACCEPTED
        answer = _("acceptance") if accepted else _("refusal")
        person = line.person.name if line.person_id else ""
        values = {
            **_base_values(),
            **_project_values(project),
            "person": person,
            "antwort": capfirst(answer),
            "funktion": line.job_function.name if line.job_function_id else "",
            "einsatz": "{} – {}".format(
                formats.date_format(timezone.localtime(line.start), local_pattern("D d.m.Y H:i")),
                formats.date_format(timezone.localtime(line.end), local_pattern("D d.m.Y H:i")),
            ),
            "anmerkung": line.answer_note,
        }
        moment = line.answered_at or timezone.now()
        event = Event(
            trigger=Trigger.CREW_ANSWER,
            key=f"answer:{line.pk}:{line.request_status}:{moment.isoformat()}",
            summary=f"{project.number} {project.name}: {capfirst(answer)} – {person}",
            project=project,
            answer=line.request_status,
            values=values,
            data={"asked_by": line.requested_by_id, "line": line.pk},
        )
    return fire(event)


def follow_up_due(project: Project) -> list[AutomationRun]:
    """A follow-up of a project is due: its day – with a time (PRJ-109), that time – has come (PRJ-105)."""
    if not _has_rules(Trigger.FOLLOW_UP):
        return []
    from rentalars.projects.follow_up import when_text

    with translation.override(_language()):
        user = project.follow_up_user
        values = {
            **_base_values(),
            **_project_values(project),
            # PRJ-109: "Mo 20.10.2026 um 14:30" when the follow-up has a time.
            "wiedervorlage": when_text(project),
            "notiz": project.follow_up_note,
            "fuer": (user.get_full_name() or user.username) if user is not None else "",
        }
        # PRJ-109: a follow-up moved to another time of the same day is a new event; without a time the key has no time part.
        time_key = f":{project.follow_up_at:%H%M}" if project.follow_up_at else ""
        event = Event(
            trigger=Trigger.FOLLOW_UP,
            key=f"follow_up:{project.pk}:{project.follow_up_on}:{project.follow_up_user_id or 0}{time_key}",
            summary=_("%(project)s: follow-up of %(day)s")
            % {"project": f"{project.number} {project.name}", "day": values["wiedervorlage"]},
            project=project,
            values=values,
            data={"follow_up_user": project.follow_up_user_id},
        )
    return fire(event)


# --- PRJ-112: service cases ------------------------------------------------------------------

#: Set while a rule is carried out: what happens then is the automation's own doing, not new communication.
_RUNNING: contextvars.ContextVar[bool] = contextvars.ContextVar("automation_running", default=False)


def automation_running() -> bool:
    """Whether a rule is being carried out in this thread right now (loop protection, PRJ-112)."""
    return _RUNNING.get()


def case_follow_up_due(case: Project) -> list[AutomationRun]:
    """The follow-up of a service case is due (PRJ-112) – with the status of the case as condition.

    Called with :func:`follow_up_due` by ``notify_due_follow_ups``, once per
    follow-up; its key names day, time and user like that one.
    """
    if not case.is_service_case or not _has_rules(Trigger.CASE_FOLLOW_UP):
        return []
    from rentalars.projects.follow_up import when_text

    with translation.override(_language()):
        user = case.follow_up_user
        values = {
            **_base_values(),
            **_project_values(case),
            "wiedervorlage": when_text(case),
            "notiz": case.follow_up_note,
            "fuer": (user.get_full_name() or user.username) if user is not None else "",
        }
        time_key = f":{case.follow_up_at:%H%M}" if case.follow_up_at else ""
        data = {
            "follow_up_user": case.follow_up_user_id,
            "case": f"{case.number} {case.name}",
            "case_status": case.case_status,
            "waiting_for": case.case_waiting_for,
            "follow_up_on": str(case.follow_up_on or ""),
            "follow_up_at": f"{case.follow_up_at:%H:%M}" if case.follow_up_at else "",
        }
        event = Event(
            trigger=Trigger.CASE_FOLLOW_UP,
            key=f"case_follow_up:{case.pk}:{case.follow_up_on}:{case.follow_up_user_id or 0}{time_key}",
            summary=str(case_event_text(Trigger.CASE_FOLLOW_UP, data)),
            project=case,
            status=case.case_status,
            values=values,
            data=data,
        )
    return fire(event)


def case_communication(
    case: Project, *, kind: str, key: str, who: str = "", text: str = "", locked: bool = False
) -> list[AutomationRun]:
    """New communication in a service case: a mail received or sent, a chat message (PRJ-112).

    ``kind`` is a ``Communication`` value, ``key`` names the mail or message
    (with the case, so that a mail moved to another case is a new event),
    ``who`` and ``text`` are the sender or author and the subject or the
    beginning of the message. Ignored while a rule is carried out – the
    automation's own doings are no new communication.

    EML-055: ``locked`` – a mail with lock; its subject is never part of the run, so neither of a
    notification nor of an open item ("Mail von … (mit Schloss)").
    """
    if automation_running() or not case.is_service_case or not _has_rules(Trigger.CASE_COMMUNICATION):
        return []
    data = {
        "case": f"{case.number} {case.name}",
        "case_status": case.case_status,
        "waiting_for": case.case_waiting_for,
        "communication": kind,
        "who": who[:200],
        "text": "" if locked else text[:200],
    }
    if locked:
        data["locked"] = True
    with translation.override(_language()):
        values = {**_base_values(), **_project_values(case), "kommunikation": str(_communication_text(data))}
        event = Event(
            trigger=Trigger.CASE_COMMUNICATION,
            key=f"case_communication:{case.pk}:{key}",
            summary=str(case_event_text(Trigger.CASE_COMMUNICATION, data)),
            project=case,
            status=case.case_status,
            communication=kind,
            values=values,
            data=data,
        )
    return fire(event)


def defect_reported(report: DefectReport) -> list[AutomationRun]:
    """MAT-057: a defect was reported – on the item's page, on return of a project or through the API.

    Called by ``automations.signals`` when a ``material.DefectReport`` is
    created; one event per report.
    """
    if not _has_rules(Trigger.DEFECT):
        return []
    from django.utils.text import Truncator

    from rentalars.projects.defect_cases import values_of

    with translation.override(_language()):
        values = {**_base_values(), **values_of(report)}
        event = Event(
            trigger=Trigger.DEFECT,
            key=f"defect:{report.pk}",
            summary=_("Defect of %(id)s: %(description)s")
            % {"id": values["id"], "description": Truncator(" ".join(report.description.split())).chars(120)},
            values=values,
            data={"defect": report.pk, "item": report.item_id},
        )
    return fire(event)


def _case_status_text(status: str, waiting_for: str) -> str:
    """The status of a case as shown, in the active language – "wartet auf Rückmeldung"."""
    from rentalars.projects.models import CASE_WAITING_LABELS, CaseStatus

    if status == CaseStatus.WAITING and waiting_for in CASE_WAITING_LABELS:
        return str(CASE_WAITING_LABELS[waiting_for])
    return str(CaseStatus(status).label) if status in CaseStatus.values else status


def _follow_up_text(day: str, time: str) -> str:
    """The day (and time) of a follow-up as ``when_text`` writes it, in the active language."""
    from types import SimpleNamespace

    from rentalars.projects.follow_up import when_text

    if not day:
        return ""
    moment = SimpleNamespace(
        follow_up_on=datetime.date.fromisoformat(day),
        follow_up_at=datetime.time.fromisoformat(time) if time else None,
    )
    return when_text(moment)  # type: ignore[arg-type]


def _communication_text(data: dict[str, Any]) -> LocalText:
    """The mail or chat message in a few words, in the reader's language (PRJ-112, UIX-029)."""
    from rentalars.automations.models import Communication

    kind = data.get("communication", "")
    if data.get("locked") and kind in (Communication.MAIL_OUT, Communication.MAIL_IN):
        # EML-055: a mail with lock – without its subject.
        if kind == Communication.MAIL_OUT:
            return LocalText(gettext_lazy("Mail sent (with lock)"))
        return LocalText(gettext_lazy("Mail from %(sender)s (with lock)"), sender=data.get("who") or "?")
    if kind == Communication.MAIL_OUT:
        return LocalText(gettext_lazy("Mail sent: %(subject)s"), subject=data.get("text") or "–")
    if kind == Communication.MAIL_IN:
        return LocalText(
            gettext_lazy("Mail from %(sender)s: %(subject)s"),
            sender=data.get("who") or "?",
            subject=data.get("text") or "–",
        )
    return LocalText(
        gettext_lazy("Chat message from %(author)s: %(text)s"), author=data.get("who") or "?", text=data.get("text", "")
    )


def case_event_text(trigger: str, data: dict[str, Any]) -> LocalText:
    """What happened to a service case, written in the language of whoever reads it (PRJ-112, UIX-029).

    Built from the run's ``data`` – the list of runs keeps it in the
    installation's language, a notification without a title of its own is
    written for each recipient.
    """
    status = LazyCall(_case_status_text, data.get("case_status", ""), data.get("waiting_for", ""))
    if trigger == Trigger.CASE_COMMUNICATION:
        return LocalText(
            gettext_lazy("%(project)s (%(status)s): %(what)s"),
            project=data.get("case", ""),
            status=status,
            what=_communication_text(data),
        )
    return LocalText(
        gettext_lazy("%(project)s (%(status)s): follow-up of %(day)s"),
        project=data.get("case", ""),
        status=status,
        day=LazyCall(_follow_up_text, data.get("follow_up_on", ""), data.get("follow_up_at", "")),
    )


# --- Carrying out ----------------------------------------------------------------------------------


@dataclass
class Outcome:
    """How a run ended."""

    status: str
    detail: str = ""
    recipient: str = ""


def run_pending(ids: list[int] | None = None, *, limit: int = RUN_LIMIT) -> int:
    """Carry out waiting runs – these, or all; returns how many. Never raises."""
    try:
        _give_up_stale()
        rows = AutomationRun.objects.filter(status=RunStatus.PENDING)
        if ids is not None:
            rows = rows.filter(pk__in=ids)
        count = 0
        for run in rows.select_related("automation", "project").order_by("pk")[:limit]:
            # Claim it: should another process have it already, this one leaves it.
            if not AutomationRun.objects.filter(pk=run.pk, status=RunStatus.PENDING).update(status=RunStatus.RUNNING):
                continue
            _carry_out(run)
            count += 1
        return count
    except Exception:
        logger.exception("The automations could not be carried out.")
        return 0


def _give_up_stale() -> None:
    """Runs left "running" by a process that ended are failed – never repeated (an answer must not go twice)."""
    stale = AutomationRun.objects.filter(status=RunStatus.RUNNING, created_at__lt=timezone.now() - STALE_AFTER)
    if not stale.exists():
        return
    with translation.override(_language()):
        detail = _("Interrupted. Not repeated, so that nothing goes out twice.")
    stale.update(status=RunStatus.FAILED, finished_at=timezone.now(), detail=detail)


def _carry_out(run: AutomationRun) -> None:
    from rentalars.core.audit import acting_as

    rule = run.automation
    with translation.override(_language()):
        if rule is None or not rule.is_active:
            outcome = Outcome(RunStatus.SKIPPED, _("The automation was deleted or switched off in the meantime."))
        else:
            token = _RUNNING.set(True)  # PRJ-112: what the rule does is no new communication
            try:
                with acting_as(_("Automation “%(name)s”") % {"name": rule.name}):
                    outcome = _ACTIONS[run.action](run, rule)
            except Exception as error:
                logger.exception("The automation %s failed.", rule.pk)
                outcome = Outcome(RunStatus.FAILED, str(error) or error.__class__.__name__)
            finally:
                _RUNNING.reset(token)
    run.status = outcome.status
    run.detail = outcome.detail
    run.recipient = outcome.recipient[:300]
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "detail", "recipient", "finished_at"])


def _values(run: AutomationRun) -> dict[str, str]:
    return dict(run.data.get("values") or {})


# --- Action: answer the mail ---------------------------------------------------------------------------


def own_addresses() -> set[str]:
    """Rentalars' own addresses, lower case: the mailboxes, the sender of system mails, the company."""
    from rentalars.core.models import CompanyProfile
    from rentalars.mail.mailboxes import own_addresses as mailbox_addresses

    addresses = set(mailbox_addresses())
    for text in (settings.DEFAULT_FROM_EMAIL, settings.SERVER_EMAIL, CompanyProfile.load().email):
        address = parseaddr(text or "")[1].strip().lower()
        if address:
            addresses.add(address)
    return addresses


def no_answer_reason(data: dict[str, Any]) -> str:
    """Why a mail gets no automatic answer; empty if it may get one (see the module description)."""
    if data.get("automatic"):
        return _("The mail is marked as sent automatically (%(header)s).") % {"header": data["automatic"]}
    for address in (data.get("sender", ""), data.get("answer_to", "")):
        address = (address or "").strip().lower()
        if not address:
            continue
        local = address.rsplit("@", 1)[0]
        if _NO_ANSWER_LOCAL.match(local):
            return _("The sender %(address)s is a mail system or takes no answers.") % {"address": address}
        if address in own_addresses():
            return _("The sender %(address)s is an address of Rentalars itself.") % {"address": address}
    if not (data.get("answer_to") or "").strip():
        return _("The mail names no sender to answer.")
    return ""


def answered_today(rule: Automation, address: str) -> bool:
    """Whether this rule answered this address today already (at most one answer per sender, rule and day)."""
    midnight = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return AutomationRun.objects.filter(
        automation=rule,
        action=Action.REPLY,
        status=RunStatus.DONE,
        recipient__iexact=address,
        finished_at__gte=midnight,
    ).exists()


def _sending_mailbox(mailbox_id: int | None) -> Mailbox | None:
    """The mailbox the mail came into if it can send, else the one that sends the correspondence."""
    from rentalars.mail.mailboxes import outgoing_mailbox
    from rentalars.mail.models import Mailbox

    own = Mailbox.objects.filter(pk=mailbox_id).first() if mailbox_id else None
    if own is not None and own.can_send:
        return own
    other = outgoing_mailbox()
    return other if other is not None and other.can_send else None


def reply_subject(subject: str) -> str:
    """The default subject of an answer: "AW: …"."""
    from rentalars.mail.sending import reply_subject as answer_subject

    return answer_subject(subject or "")


def _reply(run: AutomationRun, rule: Automation) -> Outcome:
    from rentalars.core.models import CompanyProfile
    from rentalars.mail import log, sending
    from rentalars.mail.footer import footer_text, with_text_footer
    from rentalars.mail.models import Direction, LogKind, LogResult, MailSettings, message_key

    data = run.data
    reason = no_answer_reason(data)
    if reason:
        return Outcome(RunStatus.SKIPPED, reason)
    address = data["answer_to"].strip()
    if answered_today(rule, address):
        return Outcome(
            RunStatus.SKIPPED,
            _("%(address)s got an answer of this automation today already.") % {"address": address},
            address,
        )
    mailbox = _sending_mailbox(data.get("mailbox"))
    if mailbox is None:
        return Outcome(
            RunStatus.FAILED,
            _(
                "No mailbox can send: the mailbox of the mail and the one that sends the correspondence lack an SMTP server or an address."
            ),
            address,
        )
    values = _values(run)
    subject = " ".join(fill(rule.subject, values).split())[:250] or reply_subject(data.get("subject", ""))
    body = fill(rule.text, values)
    sender_name = MailSettings.load().sender_name or CompanyProfile.load().name or mailbox.name
    message = EmailMessage()
    # EML-047: from the address the mail went to, when it is a listed address of that mailbox.
    own_address = data.get("own_address") or ""
    if not (own_address and mailbox.pk == data.get("mailbox") and mailbox.aliases.filter(address=own_address).exists()):
        own_address = mailbox.address
    message["From"] = formataddr((sender_name, own_address))
    message["To"] = formataddr((data.get("answer_name") or "", address))
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain=mailbox.address.rsplit("@", 1)[-1])
    if data.get("message_id"):
        message["In-Reply-To"] = data["message_id"]
        message["References"] = f"{data.get('references', '')} {data['message_id']}".strip()
    # RFC 3834: an automatic answer says so – and asks other systems not to answer it automatically again.
    message["Auto-Submitted"] = "auto-replied"
    message["X-Auto-Response-Suppress"] = "All"
    # EML-045: like every mail Rentalars sends by itself, it says so at its end.
    message.set_content(with_text_footer(body, footer_text()))
    note = {
        "direction": Direction.OUTGOING,
        "kind": LogKind.AUTOMATIC,
        "sender": message["From"],
        "recipients": [address],
        "subject": subject,
        "mailbox": mailbox,
        "message_key": message_key(message["Message-ID"]),
    }
    try:
        sending._send(mailbox, message)
    except ValidationError as error:
        text = " ".join(error.messages)
        log.record(result=LogResult.FAILED, detail=f"{rule.name}: {text}", **note)
        return Outcome(RunStatus.FAILED, text, address)
    log.record(result=LogResult.SENT, detail=rule.name, **note)
    return Outcome(
        RunStatus.DONE, _("Answered through the mailbox “%(mailbox)s”.") % {"mailbox": mailbox.name}, address
    )


# --- Action: notify a person -----------------------------------------------------------------------------


def _recipients(run: AutomationRun, rule: Automation) -> list[Any]:
    from rentalars.accounts.models import User

    project = run.project
    if rule.recipient == Recipient.MANAGER:
        return [project.manager] if project is not None and project.manager_id else []
    if rule.recipient == Recipient.ASKED_BY:
        return list(User.objects.filter(pk=run.data.get("asked_by") or 0))
    if rule.recipient == Recipient.FOLLOW_UP_USER:
        return list(User.objects.filter(pk=run.data.get("follow_up_user") or 0))
    return [rule.user] if rule.user_id else []


def _notify(run: AutomationRun, rule: Automation) -> Outcome:
    from rentalars.notifications.models import Kind
    from rentalars.notifications.services import notify

    users = [user for user in _recipients(run, rule) if user is not None and user.is_active]
    if not users:
        return Outcome(RunStatus.SKIPPED, _("Nobody to notify: the person is not set or no longer active."))
    values = _values(run)
    title: Any = " ".join(fill(rule.subject, values).split()) or run.event
    if not rule.subject.strip() and run.trigger in CASE_TRIGGERS and run.data.get("case"):
        # PRJ-112, UIX-029: what happened to the case, in each recipient's language.
        title = case_event_text(run.trigger, run.data)
    project = run.project
    if project is not None:
        url = reverse("projects:overview", args=[project.pk])
    elif run.trigger == Trigger.INQUIRY:
        url = reverse("mail:unknown_list")
    elif run.trigger == Trigger.DEFECT and run.data.get("item"):
        url = reverse("material:item_files", args=[run.data["item"]])  # MAT-057: the item's defect reports
    else:
        url = ""
    notify(
        users,
        Kind.AUTOMATION,
        title if isinstance(title, LocalText) else title[:250],
        body=fill(rule.text, values),
        url=url,
        project=project,
    )
    names = ", ".join(user.get_full_name() or user.username for user in users)
    return Outcome(RunStatus.DONE, _("Notified: %(names)s") % {"names": names}, names)


# --- Action: an open item ---------------------------------------------------------------------------------


def _open_item(run: AutomationRun, rule: Automation) -> Outcome:
    from rentalars.projects import course

    project = run.project
    if project is None:
        return Outcome(RunStatus.SKIPPED, _("The project no longer exists."))
    text = " ".join(fill(rule.text, _values(run)).split())[:OPEN_ITEM_LENGTH] or rule.name
    try:
        course.add_open_items(project, [text])
    except ValidationError as error:
        return Outcome(RunStatus.SKIPPED, " ".join(error.messages))
    return Outcome(RunStatus.DONE, _("Open item noted: %(text)s") % {"text": text}, f"{project.number}")


# --- Action: the status of a service case (PRJ-112) --------------------------------------------------------


def _case_status(run: AutomationRun, rule: Automation) -> Outcome:
    """Set the status of the service case – if it is still as the condition found it.

    Between the event and this moment somebody may have changed the case:
    another status, or – for a due follow-up – a follow-up moved to a new
    day or time. Then the run is left out with the reason. A case closed
    because its follow-up was due loses that follow-up: it has done its job.
    Setting a status is no event of its own, so rules cannot set each other
    off.
    """
    from rentalars.projects import service_cases
    from rentalars.projects.follow_up import clear_follow_up
    from rentalars.projects.models import CaseStatus, Project

    case = Project.objects.filter(pk=run.project_id).first() if run.project_id else None
    if case is None or not case.is_service_case:
        return Outcome(RunStatus.SKIPPED, _("The service case no longer exists or is a project now."))
    found = run.data.get("case_status", "")
    if case.case_status != found:
        return Outcome(
            RunStatus.SKIPPED,
            _("The service case is “%(now)s” now, no longer “%(then)s”.")
            % {"now": case.case_status_label, "then": CaseStatus(found).label if found in CaseStatus.values else found},
            case.number,
        )
    if run.trigger == Trigger.CASE_FOLLOW_UP:
        moment = (str(case.follow_up_on or ""), f"{case.follow_up_at:%H:%M}" if case.follow_up_at else "")
        if moment != (run.data.get("follow_up_on", ""), run.data.get("follow_up_at", "")):
            return Outcome(RunStatus.SKIPPED, _("The follow-up was moved or removed in the meantime."), case.number)
    if case.case_status == rule.new_case_status:
        return Outcome(RunStatus.SKIPPED, _("The service case has this status already."), case.number)
    before = case.case_status_label
    service_cases.set_case_status(case, rule.new_case_status)
    if run.trigger == Trigger.CASE_FOLLOW_UP and rule.new_case_status == CaseStatus.DONE:
        clear_follow_up(case)
    return Outcome(
        RunStatus.DONE,
        _("Status of %(number)s: %(before)s → %(after)s")
        % {"number": case.number, "before": before, "after": case.case_status_label},
        case.number,
    )


# --- Actions of a defect report (MAT-057) -----------------------------------------------------------


def _defect_of(run: AutomationRun) -> DefectReport | None:
    from rentalars.material.models import DefectReport

    return (
        DefectReport.objects.select_related("item__material_model", "reported_by")
        .filter(pk=run.data.get("defect") or 0)
        .first()
    )


def _create_case(run: AutomationRun, rule: Automation) -> Outcome:
    """Make a service case of the defect report – internal, or for the owner of customer material.

    Title and description are the rule's subject and text with the
    placeholders filled, else what the report says; the rule's user is
    responsible (``projects.defect_cases``). One report makes one case.
    """
    from rentalars.projects import defect_cases

    report = _defect_of(run)
    if report is None:
        return Outcome(RunStatus.SKIPPED, _("The defect report no longer exists."))
    existing = defect_cases.case_of(report)
    if existing is not None:
        return Outcome(
            RunStatus.SKIPPED,
            _("The service case %(number)s was made of this defect report already.") % {"number": existing.number},
            existing.number,
        )
    values = _values(run)
    fields: dict[str, Any] = {}
    title = " ".join(fill(rule.subject, values).split())[: defect_cases.TITLE_LENGTH]
    if title:
        fields["name"] = title
    text = fill(rule.text, values).strip()
    if text:
        fields["notes"] = text
    if rule.user_id and rule.user.is_active:
        fields["manager"] = rule.user
    try:
        case = defect_cases.create_from_defect(report, **fields)
    except ValidationError as error:
        return Outcome(RunStatus.SKIPPED, " ".join(error.messages))
    run.project = case
    run.save(update_fields=["project"])
    return Outcome(RunStatus.DONE, _("Service case %(number)s created.") % {"number": case.number}, case.number)


def _create_inquiry(run: AutomationRun, rule: Automation) -> Outcome:
    """Put the defect report under Projekte → Anfragen, where it becomes a service case by hand or is taken off."""
    from django.utils.text import Truncator

    from rentalars.mail.models import UnknownTagMail
    from rentalars.projects import defect_cases

    report = _defect_of(run)
    if report is None:
        return Outcome(RunStatus.SKIPPED, _("The defect report no longer exists."))
    existing = defect_cases.case_of(report)
    if existing is not None:
        return Outcome(
            RunStatus.SKIPPED,
            _("The service case %(number)s was made of this defect report already.") % {"number": existing.number},
            existing.number,
        )
    if defect_cases.inquiry_of(report) is not None:
        return Outcome(RunStatus.SKIPPED, _("The defect report is under Projects → Inquiries already."))
    subject = " ".join(fill(rule.subject, _values(run)).split())
    if not subject:
        description = Truncator(" ".join(report.description.split())).chars(150)
        subject = f"{defect_cases.default_title(report)}: {description}"
    reporter = report.reported_by
    UnknownTagMail.objects.create(
        message_key=f"defect:{report.pk}",
        subject=subject[:500],
        sender=(reporter.get_full_name() or reporter.username) if reporter is not None else "",
        date=report.reported_at,
        defect_report=report,
    )
    return Outcome(RunStatus.DONE, _("Put under Projects → Inquiries: %(subject)s") % {"subject": subject[:200]})


_ACTIONS = {
    Action.REPLY: _reply,
    Action.NOTIFY: _notify,
    Action.OPEN_ITEM: _open_item,
    Action.CASE_STATUS: _case_status,
    Action.CREATE_CASE: _create_case,  # MAT-057
    Action.CREATE_INQUIRY: _create_inquiry,  # MAT-057
}


def delete_old_runs() -> int:
    """Remove runs after :data:`~rentalars.automations.models.RUN_RETENTION_DAYS` days (daily maintenance)."""
    from rentalars.automations.models import RUN_RETENTION_DAYS

    limit = timezone.now() - datetime.timedelta(days=RUN_RETENTION_DAYS)
    deleted, _details = AutomationRun.objects.filter(created_at__lt=limit).delete()
    return deleted


def forget_name(old_name: str, new_name: str) -> int:
    """NFA-009: runs that name an anonymised person name the new name and keep no values of their texts."""
    if not old_name:
        return 0
    from django.db.models import Value
    from django.db.models.functions import Replace

    return AutomationRun.objects.filter(event__contains=old_name).update(
        event=Replace("event", Value(old_name), Value(new_name)), data={}
    )
