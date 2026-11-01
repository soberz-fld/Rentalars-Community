# SPDX-License-Identifier: GPL-3.0-or-later
"""Where automations hear of a status and of an answer, whichever way they were saved (ADM-013).

A project reaches a status by hand, through the API, or by packing ("out",
"returned", PCK-019); a deployment request is answered in the browser, by
reply mail (PER-032), through the API or entered by the planner. All of
these save the object, so a signal after saving notices every path – as for
the webhooks (``api.webhooks``). The values before the save come from the
change log's snapshot (``core.audit``), at no cost.

MAT-057: a defect report, wherever it was made – the item's page,
the return of a project, the API.

PRJ-112: a mail stored in a service case – received, sent or
assigned to it by hand – and a chat message written in one are "new
communication" for the rules of the service cases.

A mailbox can always be deleted (EML-046). The rules that answer only the
mails of that mailbox are switched off first – otherwise they would answer
the mails of every mailbox.
"""

from __future__ import annotations

from typing import Any


def _before(instance: Any) -> dict[str, Any] | None:
    """The logged values of an object before the current save; ``None`` for a hand-built object."""
    return instance._audit_before() if hasattr(instance, "_audit_before") else None


def _project_saved(sender: Any, instance: Any, created: bool = False, raw: bool = False, **kwargs: Any) -> None:
    """ADM-013: a project reached a status – also when it was created with it."""
    from rentalars.projects.legacy_quiet import is_quiet

    if raw or is_quiet():  # Legacy import: an old project taken over from an invoice is no news
        return
    update_fields = kwargs.get("update_fields")
    if update_fields is not None and "status" not in update_fields:
        return
    from rentalars.automations.engine import project_reached_status

    if created:
        project_reached_status(instance, None)
        return
    before = _before(instance)
    if not before or "status" not in before or before["status"] == instance.status:
        return
    project_reached_status(instance, before["status"])


def _crew_line_saved(sender: Any, instance: Any, created: bool = False, raw: bool = False, **kwargs: Any) -> None:
    """ADM-013: a deployment request was accepted or declined (PER-016)."""
    from rentalars.projects.models import RequestStatus

    if raw or created or instance.request_status not in (RequestStatus.ACCEPTED, RequestStatus.DECLINED):
        return
    update_fields = kwargs.get("update_fields")
    if update_fields is not None and "request_status" not in update_fields:
        return
    before = _before(instance)
    if not before or "request_status" not in before or before["request_status"] == instance.request_status:
        return
    from rentalars.automations.engine import crew_answer_arrived

    crew_answer_arrived(instance)


def _mail_saved(sender: Any, instance: Any, created: bool = False, raw: bool = False, **kwargs: Any) -> None:
    """PRJ-112: a mail of a service case – received, sent, or assigned to it by hand – is new communication.

    Automatic replies and delivery failures (``ProjectMail.kind``) are not;
    a mail saved again in the same case is no new event. EML-051: a
    note written into the correspondence is no communication either.
    """
    if raw or instance.kind or instance.is_note:
        return
    if not created:
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "project" not in update_fields:
            return
        before = _before(instance)
        if not before or before.get("project") == instance.project_id:
            return
    case = instance.project
    if not case.is_service_case:
        return
    from rentalars.automations.engine import case_communication
    from rentalars.automations.models import Communication
    from rentalars.mail.models import Direction

    sent = instance.direction == Direction.OUTGOING
    # UIX-029: the words around sender and subject are written later, in each reader's language.
    # EML-055: the subject of a mail with lock stays out of notifications and open items – the run keeps
    # only that it has a lock. The sender stays: the notification of an open mail names him as well.
    case_communication(
        case,
        kind=Communication.MAIL_OUT if sent else Communication.MAIL_IN,
        key=f"mail:{instance.pk}",
        who="" if sent else (instance.sender_address or instance.sender_name),
        text="" if instance.locked else instance.subject,
        locked=bool(instance.locked),
    )


def _chat_message_saved(sender: Any, instance: Any, created: bool = False, raw: bool = False, **kwargs: Any) -> None:
    """PRJ-112: a new chat message in a service case is new communication; changing one is not."""
    if raw or not created or not instance.project.is_service_case:
        return
    from django.utils.text import Truncator

    from rentalars.automations.engine import case_communication
    from rentalars.automations.models import Communication

    case_communication(
        instance.project,
        kind=Communication.CHAT,
        key=f"chat:{instance.pk}",
        who=instance.author_name,
        text=Truncator(" ".join(instance.text.split())).chars(80),
    )


def _defect_report_saved(sender: Any, instance: Any, created: bool = False, raw: bool = False, **kwargs: Any) -> None:
    """MAT-057: a defect was reported – whichever way; changing a report is no new event."""
    if raw or not created:
        return
    from rentalars.automations.engine import defect_reported

    defect_reported(instance)


def _mailbox_deleted(sender: Any, instance: Any, **kwargs: Any) -> None:
    """EML-046: the rules bound to a deleted mailbox are switched off, so that they answer no other mailbox."""
    from rentalars.automations.models import Automation

    for rule in Automation.objects.filter(mailbox=instance, is_active=True):
        rule.is_active = False
        rule.save()


def connect_signals() -> None:
    """Connect the signals; called once when the application starts."""
    from django.db.models.signals import post_save, pre_delete

    post_save.connect(_project_saved, sender="projects.Project", dispatch_uid="automations.project")
    post_save.connect(_crew_line_saved, sender="projects.CrewLine", dispatch_uid="automations.crew_line")
    pre_delete.connect(_mailbox_deleted, sender="mail.Mailbox", dispatch_uid="automations.mailbox")
    # PRJ-112: new communication in a service case.
    post_save.connect(_mail_saved, sender="mail.ProjectMail", dispatch_uid="automations.case_mail")
    post_save.connect(_chat_message_saved, sender="chat.ChatMessage", dispatch_uid="automations.case_chat")
    # MAT-057: a defect report.
    post_save.connect(_defect_report_saved, sender="material.DefectReport", dispatch_uid="automations.defect")
