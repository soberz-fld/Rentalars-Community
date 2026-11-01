# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the mail module (chapter 5.15, API-002).

In a project (rights: ``mail.services``, EML-029):

* ``GET  /projects/{id}/mails`` – the correspondence, newest first (EML-019)
* ``POST /projects/{id}/mails`` – write a mail or answer one (EML-024, EML-025); EML-052: ``sender``
  chooses the address among those the caller may use, 403 for another
* ``GET  /projects/{id}/mails/senders`` – EML-052: the addresses the caller may send from, the default
  marked (``?answer_to=`` for an answer)
* ``GET  /projects/{id}/mails/{mail}`` – one mail with its text (EML-020, EML-027)
* ``DELETE /projects/{id}/mails/{mail}`` – remove it from Rentalars
* ``POST /projects/{id}/mails/notes`` – EML-051: a note into the correspondence, with the time it
  happened (``direction`` "note" in the list); ``PATCH /projects/{id}/mails/{note}`` changes it – its writer, or
  who may edit the project; ``DELETE`` removes it, by the same people
* ``POST /projects/{id}/mails/{mail}/assign`` – move it to another project (EML-015)
* ``PATCH /projects/{id}/mails/{mail}/lock`` – EML-055: ``{"locked": true|false}`` puts the lock on a
  message or takes it away – who may write and sees prices. Every message carries ``locked``; the lists hold only
  the messages the caller reads (the crew of the project: the open ones); ``POST …/mails`` and ``…/mails/notes``
  take ``locked`` (default: the mail settings – projects with lock, service cases open; a caller who may not lock
  writes open messages and gets 403 for ``true``); ``/mail/settings`` has ``lock_new_in_projects`` and
  ``lock_new_in_cases``; S2: ``crew_answer_trusted_server`` names the own mail server in
  ``Authentication-Results`` – set, an answer by mail counts only if that server confirmed the sender
* ``GET  /projects/{id}/mails/{mail}/attachments/{a}`` – an attachment
* ``POST /projects/{id}/mails/{mail}/attachments/{a}/to-files`` – into the project files (EML-021)

The module "E-mail" (AUT-014):

* ``GET  /mail/unknown`` – inquiries and mails with a tag that names no project (EML-014, EML-041, EML-042)
* ``POST /mail/unknown`` – EML-053: note an inquiry by hand (e.g. a phone call);
  ``GET /mail/unknown/{id}`` one entry; ``PATCH``/``DELETE`` change or delete one noted by hand – by who noted it
  or who may write in "E-mail"
* ``POST /mail/unknown/{id}/assign`` and ``…/dismiss``; ``POST /mail/unknown/dismiss`` with ``ids`` for several
  at once (PRJ-107)
* ``POST /mail/fetch`` – fetch every mailbox of the correspondence at once (EML-005, EML-041)
* ``GET/POST /mail/mailboxes``, ``GET/PUT/PATCH/DELETE /mail/mailboxes/{id}`` – the mailboxes with their
  roles; passwords can be set, never read (EML-041, EML-002, EML-035); deleting keeps the name in mails and
  mail log (EML-046)
* ``POST /mail/mailboxes/{id}/check`` – log in to the servers of a mailbox (EML-041)
* ``GET/POST /mail/mailbox-addresses``, ``GET/PUT/PATCH/DELETE /mail/mailbox-addresses/{id}`` – further addresses
  (aliases) of the mailboxes with their rule for mails without tag (EML-047)
* ``GET/PATCH /mail/settings`` – the rules for all mailboxes; still with the fields of the legacy mailbox,
  which mean the mailbox that sends the correspondence; and with how
  deployment requests are answered (``crew_answers``, PER-032)
* ``GET  /mail/address-suggestions?q=`` – addresses for the recipient fields (EML-037)

The settings (administration):

* ``GET/PATCH /mail/signature`` – the signature of everybody (EML-034)
* ``GET  /mail/log`` – every mail in and out with its result (EML-039)
"""

from __future__ import annotations

import datetime
from typing import Any, ClassVar

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.translation import gettext as _
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Level, Module, request_rights
from rentalars.api.errors import error_response
from rentalars.api.permissions import AUTHENTICATED_ONLY
from rentalars.api.views import ModuleAPIView, ModuleViewSet, body_of
from rentalars.core.uploads import document_response
from rentalars.customers.models import Customer
from rentalars.mail import inquiries, locks, senders, services
from rentalars.mail.addresses import suggest_addresses
from rentalars.mail.aliases import save_address
from rentalars.mail.crew_answers import answer_mailbox
from rentalars.mail.display import clean_html
from rentalars.mail.fetching import assign_unknown, dismiss_waiting, fetch_mail
from rentalars.mail.forms import SIGNATURE_MAX_LENGTH
from rentalars.mail.imap import MailboxError
from rentalars.mail.log import filtered_entries
from rentalars.mail.mailboxes import check_connection, delete_mailbox, legacy_mailbox, save_mailbox
from rentalars.mail.models import (
    LOG_DIRECTIONS,
    AfterAssignment,
    CrewAnswerMode,
    LogKind,
    LogResult,
    MailAttachment,
    Mailbox,
    MailboxAddress,
    MailLogEntry,
    MailSettings,
    ProjectMail,
    UnknownTagMail,
)
from rentalars.mail.sending import chosen_attachments, reply_recipients, send_project_mail
from rentalars.mail.signature import clean_signature, render_signature, shown_placeholders
from rentalars.mail.suppliers import mails_with, set_supplier, supplier_from
from rentalars.masterdata.models import DocumentType, Supplier
from rentalars.projects.access import ProjectAccess, access_level, project_for
from rentalars.projects.case_work import CaseWorkPermission
from rentalars.projects.case_work import require as require_case_work
from rentalars.projects.files import add_file_from_attachment
from rentalars.projects.models import Project
from rentalars.projects.numbers import project_by_number

# --- Documents ----------------------------------------------------------------------------------


def attachment_document(attachment: MailAttachment) -> dict[str, Any]:
    """One attachment: name, type, size."""
    return {
        "id": attachment.pk,
        "filename": attachment.filename,
        "content_type": attachment.content_type,
        "size": attachment.size,
        "is_inline": attachment.is_inline,
    }


def mail_document(mail: ProjectMail, *, with_body: bool = False) -> dict[str, Any]:
    """One mail as JSON; the text only when asked for (it can be long)."""
    document: dict[str, Any] = {
        "id": mail.pk,
        "project": mail.project_id,
        "direction": mail.direction,
        "kind": mail.kind,
        "subject": mail.subject,
        "sender_name": mail.sender_name,
        "sender_address": mail.sender_address,
        "to": mail.to_addresses,
        "cc": mail.cc_addresses,
        # EML-037: blind copies only ever exist for mails sent from Rentalars.
        "bcc": mail.bcc_addresses,
        "date": mail.date,
        "assigned_by": mail.assigned_by,
        "sent_by": str(mail.sent_by) if mail.sent_by_id else None,
        "project_was_finished": mail.project_was_finished,
        "attachments_left_out": mail.attachments_note,
        "attachments": [attachment_document(item) for item in mail.attachments.all()],
        # PRJ-106: the supplier of subrentals the mail belongs to (``/projects/{id}/subrentals/{supplier}``).
        "supplier": mail.supplier_id,
        # EML-055: with lock only for who sees prices; open also for the crew of the project.
        "locked": mail.locked,
    }
    if mail.is_note:
        # EML-051: a note – who wrote it is ``sent_by``; nothing to answer, no HTML.
        if with_body:
            document["text"] = mail.text_body
            document["html"] = ""
            document["reply"] = document["reply_all"] = None
        return document
    if with_body:
        document["text"] = mail.text_body
        # The HTML part is cleaned like for the browser; external pictures stay blocked (EML-027).
        document["html"] = (
            clean_html(mail.html_body, allow_external=False, cid_url=lambda _cid: None)[0] if mail.html_body else ""
        )
        # EML-037: who an answer and an answer to all would go to.
        for key, everyone in (("reply", False), ("reply_all", True)):
            to, cc = reply_recipients(mail, everyone=everyone)
            document[key] = {"to": to, "cc": cc}
    return document


def _project(request: Request, project_pk: int, level: ProjectAccess = ProjectAccess.READ) -> Project:
    """The project, for a caller who may read its correspondence; the project is checked first (AUT-020).

    AUT-033 (PRJ-108): the correspondence of a service case is open to whoever works on it; that of a project stays
    confidential (``projects.case_work``).

    EML-055: reading also opens to the crew planned in the project, for the open messages (``mail.locks``).
    """
    project = project_for(request, project_pk, ProjectAccess.DEPLOYMENT if level <= ProjectAccess.READ else level)
    require_case_work(locks.correspondence_of(request, project).reads_any)
    return project


def _mail(request: Request, project: Project, mail_pk: Any, queryset: Any = None) -> ProjectMail:
    """A message of the project the caller reads; one with lock is "not found" without the right (EML-055)."""
    mail = get_object_or_404(ProjectMail.objects.all() if queryset is None else queryset, pk=mail_pk, project=project)
    if not locks.correspondence_of(request, project).may_read(mail):
        raise Http404
    return mail


def _writing(request: Request, project: Project) -> locks.Correspondence:
    """The correspondence for a caller who writes in it; 403 otherwise (EML-024, AUT-033; EML-055)."""
    access = locks.correspondence_of(request, project)
    require_case_work(access.may_write)
    return access


def _wanted_lock(
    access: locks.Correspondence, body: Any, project: Project, *, answer_to: ProjectMail | None = None
) -> bool:
    """EML-055: the lock of a new message – ``locked`` of the body; left out, the default of the project.

    A caller who may not set the lock writes open messages; asking for the lock is refused. Left out in an answer
    to a message with lock, the answer has the lock as well (``locks.answer_lock``) – ``locked: false`` takes it off.
    """
    value = body.get("locked")
    if value is None or value == "":
        wanted = None
    elif isinstance(value, bool):
        wanted = value
    else:
        wanted = str(value).strip().lower() in {"1", "true", "yes", "on"}
    if wanted and not access.may_lock:
        raise PermissionDenied(_("A lock is set only by those who may write correspondence and see prices."))
    if wanted is None and answer_to is not None and answer_to.locked:
        wanted = locks.answer_lock(answer_to, project)
    return access.new_lock(wanted, project)


class _CaseWork:
    """AUT-033 (PRJ-108): the correspondence of a service case is part of working on it (``projects.case_work``)."""

    permission_classes = (CaseWorkPermission,)
    case_work_actions = ("*",)
    case_work_kwarg = "project_pk"


def _target_project(request: Request, body: Any, minimum: ProjectAccess) -> Project:
    """The project named by ``project`` (ID) or ``project_number`` in a request.

    Raises:
        ValidationError: No such project, or the caller may not use it.
    """
    project = None
    if body.get("project"):
        project = Project.objects.filter(pk=body.get("project")).first()
    elif body.get("project_number"):
        # ADM-012, ADM-014: also a former number.
        project = project_by_number(str(body.get("project_number")))
    if project is None or access_level(request_rights(request), request.user, project) < minimum:
        raise ValidationError({"project": _("There is no such project that you may use.")})
    return project


# --- Correspondence of a project ----------------------------------------------------------------


class ProjectMailListView(_CaseWork, ModuleAPIView):
    """``/projects/{id}/mails`` – the correspondence of a project (EML-019, EML-024)."""

    module = Module.PROJECTS
    schema_tag = "mail"
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    # Sending needs the right to write correspondence, not write access to projects (EML-029),
    # as in the browser. A plain view has no named action: ``None`` stands for all its methods.
    action_levels = {None: Level.READ}

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "supplier",
                int,
                description="PRJ-106: only the mails with this supplier – linked to it, or from or to its address "
                "and linked to nobody (as on the page of the subrental).",
            )
        ],
        responses={200: inline_serializer("ProjectMails", {"id": serializers.IntegerField()}, many=True)},
    )
    def get(self, request: Request, project_pk: int) -> Response:
        """All mails of the project the caller reads, newest first (EML-055: the crew the open ones)."""
        project = _project(request, project_pk)
        mails = project.mails.all()
        wanted = str(request.query_params.get("supplier", ""))
        if wanted.isdigit():
            mails = mails_with(project, get_object_or_404(Supplier, pk=int(wanted)))
        mails = locks.correspondence_of(request, project).readable(mails)
        mails = mails.prefetch_related("attachments").select_related("sent_by").order_by("-date", "-id")
        return Response([mail_document(mail) for mail in mails])

    @extend_schema(
        request=inline_serializer(
            "MailOut",
            {
                "to": serializers.CharField(),
                "cc": serializers.CharField(required=False),
                "bcc": serializers.CharField(required=False),
                "subject": serializers.CharField(),
                "body": serializers.CharField(),
                "signature": serializers.BooleanField(required=False, default=True),
                "answer_to": serializers.IntegerField(required=False),
                # PRJ-106: written about the subrentals at this supplier; without it, found by the recipients.
                "supplier": serializers.IntegerField(required=False),
                # EML-052: the sender address, one of ``GET …/mails/senders``; the default when left out.
                "sender": serializers.EmailField(required=False),
                "files": serializers.ListField(child=serializers.IntegerField(), required=False),
                # EML-055: with lock or open; left out, as the mail settings say for project or case.
                "locked": serializers.BooleanField(required=False),
                "documents": serializers.ListField(
                    # PRJ-081: "deployment" – the deployment overview as PDF.
                    child=serializers.ChoiceField(choices=["packlist", "prices", "deployment"]),
                    required=False,
                ),
            },
        ),
        responses={201: inline_serializer("MailSent", {"id": serializers.IntegerField()})},
    )
    def post(self, request: Request, project_pk: int) -> Response:
        """Send a mail from the project; the project's tag is added to the subject (EML-011).

        ``cc`` and ``bcc`` take further recipients (EML-037). The company's
        signature is added unless ``signature`` is false (EML-034); the sender
        is the caller with the company name (EML-038). Further files can be
        sent along as ``uploads`` in a multipart request.

        EML-052: ``sender`` is the address it goes out with – one the
        caller may use (``GET …/mails/senders``), else 403. Left out, the
        project's default; for an answer the address the mail came in
        through, if the caller may use it. EML-026: the signature is that of
        the sender's mailbox, if it has one.

        EML-055: ``locked`` – with lock or open; left out, as the mail settings say for a project or a
        service case, and with lock for an answer to a message with lock. A caller who may not set the lock writes
        open messages, and ``locked: true`` is refused (403).
        """
        project = _project(request, project_pk)
        rights = request_rights(request)
        access = _writing(request, project)
        body = body_of(request)
        answer_to = None
        if body.get("answer_to"):
            answer_to = _mail(request, project, body.get("answer_to"))
            if answer_to.is_note:
                raise ValidationError({"answer_to": _("A note cannot be answered – write a new mail.")})
        # EML-055: an answer to a message with lock starts with the lock.
        locked = _wanted_lock(access, body, project, answer_to=answer_to)
        try:
            sender = senders.chosen_sender(project, request.user, str(body.get("sender") or ""), answer_to=answer_to)
        except PermissionDenied as refused:
            # A message that says which address is refused, not the general one.
            return error_response("permission_denied", str(refused), status.HTTP_403_FORBIDDEN)

        def listed(name: str) -> list[Any]:
            value = body.getlist(name) if hasattr(body, "getlist") else body.get(name, [])
            return list(value) if isinstance(value, list | tuple) else [value]

        with_signature = body.get("signature", True)
        if isinstance(with_signature, str):
            with_signature = with_signature.strip().lower() not in {"0", "false", "no", "off", ""}
        mail = send_project_mail(
            project,
            to=str(body.get("to", "")),
            cc=str(body.get("cc", "")),
            bcc=str(body.get("bcc", "")),
            with_signature=bool(with_signature),
            subject=str(body.get("subject", "")),
            body=str(body.get("body", "")),
            attachments=chosen_attachments(
                project,
                rights=rights,
                file_ids=listed("files"),
                documents=[str(item) for item in listed("documents")],
                uploads=request.FILES.getlist("uploads"),
                user=request.user,
            ),
            answer_to=answer_to,
            user=request.user,
            supplier=supplier_from(str(body.get("supplier") or ""), answer_to),
            sender=sender,
            locked=locked,
        )
        from rentalars.mail.sending import document_choices, note_documents_sent

        allowed = dict(document_choices(rights, project, request.user))
        chosen = [str(item) for item in listed("documents") if str(item) in allowed]
        note_documents_sent(project, chosen, str(body.get("to", "")))  # DOK-008
        return Response(mail_document(mail, with_body=True), status=status.HTTP_201_CREATED)


def sender_document(sender: senders.Sender, *, default_key: str) -> dict[str, Any]:
    """EML-052: one address a mail of the project can go out with."""
    return {
        "address": sender.address,
        "name": sender.name,
        "label": sender.label,
        "mailbox": sender.owner.pk,
        # The mailbox whose SMTP server sends: that of the address, or the outgoing one for an alias of a mailbox
        # that cannot send.
        "sends_through": sender.mailbox.pk,
        "is_alias": sender.alias is not None,
        "is_default": sender.key == default_key,
        # EML-026: the mails carry the signature of the mailbox instead of the common one.
        "own_signature": bool(sender.owner.signature_html.strip()),
    }


class ProjectMailSendersView(_CaseWork, ModuleAPIView):
    """``GET /projects/{id}/mails/senders`` – the addresses the caller may send a mail of the project from (EML-052)."""

    module = Module.PROJECTS
    schema_tag = "mail"
    # As for sending: the right to write correspondence and to read the project (EML-029).
    action_levels = {None: Level.READ}

    @extend_schema(
        operation_id="project_mail_senders",
        parameters=[
            OpenApiParameter(
                "answer_to",
                int,
                description="A mail of the project to be answered: the address it came in through is the default, "
                "if the caller may use it.",
            )
        ],
        responses={
            200: inline_serializer(
                "MailSenders",
                {
                    "address": serializers.CharField(),
                    "name": serializers.CharField(),
                    "label": serializers.CharField(),
                    "mailbox": serializers.IntegerField(),
                    "sends_through": serializers.IntegerField(),
                    "is_alias": serializers.BooleanField(),
                    "is_default": serializers.BooleanField(),
                    "own_signature": serializers.BooleanField(),
                },
                many=True,
            )
        },
    )
    def get(self, request: Request, project_pk: int) -> Response:
        """The addresses; ``is_default`` marks the one ``POST …/mails`` takes without ``sender``."""
        project = _project(request, project_pk)
        _writing(request, project)
        answer_to = None
        wanted = str(request.query_params.get("answer_to", ""))
        if wanted.isdigit():
            answer_to = _mail(request, project, int(wanted))
        options = senders.allowed_senders(project, request.user)
        default = senders.default_choice(options, answer_to)
        default_key = default.key if default is not None else ""
        return Response([sender_document(option, default_key=default_key) for option in options])


class NoteInSerializer(serializers.Serializer):
    """EML-051: a note in the correspondence."""

    text = serializers.CharField(max_length=10_000, help_text="What was said – a phone call, a talk, an agreement.")
    date = serializers.DateTimeField(
        required=False, help_text="When it happened (ISO 8601 with time zone); now when left out. Not in the future."
    )
    subject = serializers.CharField(required=False, allow_blank=True, max_length=200)
    # EML-055: with lock or open; left out, as the mail settings say for a project or a service case.
    locked = serializers.BooleanField(
        required=False, help_text="With lock or open; left out, the default of the mail settings for project or case."
    )


class NoteChangeSerializer(NoteInSerializer):
    """EML-051: what of a note changes – each field optional."""

    text = serializers.CharField(required=False, max_length=10_000)


def _may_change_note(request: Request, project: Project, note: ProjectMail) -> bool:
    from rentalars.mail.notes import may_change

    # AUT-033 (PRJ-108): in a service case also whoever works on it.
    works = bool(getattr(project, "may_work_on_case", False))
    return locks.correspondence_of(request, project).may_write and may_change(
        note, request.user, may_edit_project=project.access >= ProjectAccess.EDIT or works
    )


class ProjectMailNoteView(_CaseWork, ModuleAPIView):
    """``POST /projects/{id}/mails/notes`` – a note into the correspondence (EML-051)."""

    module = Module.PROJECTS
    schema_tag = "mail"
    # As for sending a mail: the right to write correspondence and to read the project (EML-029).
    action_levels = {None: Level.READ}

    @extend_schema(
        operation_id="project_mail_note_create",
        request=NoteInSerializer,
        responses={201: inline_serializer("MailNote", {"id": serializers.IntegerField()})},
    )
    def post(self, request: Request, project_pk: int) -> Response:
        """Write the note; it stands in the correspondence at ``date``. Nothing is sent."""
        from rentalars.mail.notes import add_note

        project = _project(request, project_pk)
        access = _writing(request, project)
        serializer = NoteInSerializer(data=body_of(request))
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        note = add_note(
            project,
            text=values["text"],
            subject=values.get("subject", ""),
            date=values.get("date"),
            user=request.user,
            locked=_wanted_lock(access, values, project),  # EML-055
        )
        return Response(mail_document(note, with_body=True), status=status.HTTP_201_CREATED)


class ProjectMailDetailView(_CaseWork, ModuleAPIView):
    """``/projects/{id}/mails/{mail}`` – one mail, or a note (EML-051)."""

    module = Module.PROJECTS
    schema_tag = "mail"
    # Each method checks what it needs: deleting a mail the right to delete in projects, a note its writer.
    action_levels = {None: Level.READ}

    @extend_schema(responses={200: inline_serializer("ProjectMail", {"id": serializers.IntegerField()})})
    def get(self, request: Request, project_pk: int, mail_pk: int) -> Response:
        """The mail with its text and the cleaned HTML part."""
        project = _project(request, project_pk)
        mail = _mail(request, project, mail_pk, ProjectMail.objects.prefetch_related("attachments"))
        return Response(mail_document(mail, with_body=True))

    @extend_schema(
        operation_id="project_mail_note_update",
        request=NoteChangeSerializer,
        responses={200: inline_serializer("MailNoteChanged", {"id": serializers.IntegerField()})},
    )
    def patch(self, request: Request, project_pk: int, mail_pk: int) -> Response:
        """EML-051: change text, time or subject of a note – a mail cannot be changed."""
        from rentalars.mail.notes import update_note

        project = _project(request, project_pk)
        mail = _mail(request, project, mail_pk)
        if not mail.is_note:
            raise ValidationError(_("This is a mail, not a note; a mail cannot be changed."))
        if not _may_change_note(request, project, mail):
            raise PermissionDenied(_("Only its writer, or who may edit the project, changes a note."))
        serializer = NoteChangeSerializer(data=body_of(request))
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        update_note(mail, text=values.get("text"), subject=values.get("subject"), date=values.get("date"))
        return Response(mail_document(mail, with_body=True))

    @extend_schema(responses={204: None})
    def delete(self, request: Request, project_pk: int, mail_pk: int) -> Response:
        """Remove the mail from Rentalars; the mailbox is not touched. A note: by its writer as well (EML-051)."""
        project = _project(request, project_pk)
        mail = _mail(request, project, mail_pk)
        rights = request_rights(request)
        if mail.is_note:
            if not _may_change_note(request, project, mail):
                raise PermissionDenied(_("Only its writer, or who may edit the project, removes a note."))
        else:
            if project.access < ProjectAccess.EDIT or not rights.can_delete(Module.PROJECTS):
                raise PermissionDenied
            services.require_mail_write(rights)
        services.delete_mail(mail)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectMailAssignView(ModuleAPIView):
    """``POST /projects/{id}/mails/{mail}/assign`` – move the mail to another project (EML-015)."""

    module = Module.PROJECTS
    schema_tag = "mail"

    @extend_schema(
        request=inline_serializer(
            "MailAssign",
            {
                "project": serializers.IntegerField(required=False),
                "project_number": serializers.CharField(required=False),
            },
        ),
        responses={200: inline_serializer("MailAssigned", {"id": serializers.IntegerField()})},
    )
    def post(self, request: Request, project_pk: int, mail_pk: int) -> Response:
        """Give the target as ``project`` (ID) or ``project_number``; both projects need edit access."""
        project = _project(request, project_pk, ProjectAccess.EDIT)
        mail = _mail(request, project, mail_pk)
        target = _target_project(request, body_of(request), ProjectAccess.EDIT)
        services.reassign(mail, target, user=request.user)
        return Response(mail_document(mail))


class ProjectMailSupplierView(ModuleAPIView):
    """``POST /projects/{id}/mails/{mail}/supplier`` – the supplier of subrentals the mail belongs to (PRJ-106)."""

    module = Module.PROJECTS
    schema_tag = "mail"

    @extend_schema(
        request=inline_serializer("MailSupplier", {"supplier": serializers.IntegerField(allow_null=True)}),
        responses={200: inline_serializer("MailWithSupplier", {"id": serializers.IntegerField()})},
    )
    def post(self, request: Request, project_pk: int, mail_pk: int) -> Response:
        """Link the mail to a supplier by hand – ``null`` removes the link. Needs edit access to the project."""
        project = _project(request, project_pk, ProjectAccess.EDIT)
        mail = _mail(request, project, mail_pk)
        value = body_of(request).get("supplier")
        if value not in (None, "") and not str(value).isdigit():
            raise ValidationError({"supplier": _("Unknown supplier.")})
        supplier = get_object_or_404(Supplier, pk=int(value)) if value not in (None, "") else None
        set_supplier(mail, supplier)
        return Response(mail_document(mail))


class ProjectMailLockView(_CaseWork, ModuleAPIView):
    """``PATCH /projects/{id}/mails/{mail}/lock`` – put the lock on a message or take it away (EML-055)."""

    module = Module.PROJECTS
    schema_tag = "mail"
    # As for writing: the right to write correspondence (and to see prices), not write access to projects.
    action_levels = {None: Level.READ}

    @extend_schema(
        operation_id="project_mail_lock",
        request=inline_serializer("MailLock", {"locked": serializers.BooleanField()}),
        responses={200: inline_serializer("MailLocked", {"id": serializers.IntegerField()})},
    )
    def patch(self, request: Request, project_pk: int, mail_pk: int) -> Response:
        """``locked`` true puts the lock on, false takes it away – who may write and sees prices; the crew is told."""
        project = _project(request, project_pk)
        mail = _mail(request, project, mail_pk, ProjectMail.objects.prefetch_related("attachments"))
        if not locks.correspondence_of(request, project).may_lock:
            raise PermissionDenied(_("A lock is set only by those who may write correspondence and see prices."))
        value = body_of(request).get("locked")
        if not isinstance(value, bool):
            raise ValidationError({"locked": _("Send true for a lock or false for an open message.")})
        locks.set_lock(mail, value, user=request.user)
        return Response(mail_document(mail))


class MailAttachmentView(_CaseWork, ModuleAPIView):
    """``GET /projects/{id}/mails/{mail}/attachments/{a}`` – an attachment, after the rights were checked."""

    module = Module.PROJECTS
    schema_tag = "mail"

    @extend_schema(responses={(200, "application/octet-stream"): bytes})
    def get(self, request: Request, project_pk: int, mail_pk: int, attachment_pk: int) -> Any:
        """The file – of a message the caller reads (EML-055: it follows its message)."""
        project = _project(request, project_pk)
        stored = get_object_or_404(MailAttachment, pk=attachment_pk, mail=_mail(request, project, mail_pk))
        return document_response(stored.file.name, stored.filename)


class MailAttachmentToFilesView(ModuleAPIView):
    """``POST …/attachments/{a}/to-files`` – take an attachment into the project files (EML-021)."""

    module = Module.PROJECTS
    schema_tag = "mail"

    @extend_schema(
        request=inline_serializer(
            "AttachmentToFiles",
            {
                "document_type": serializers.IntegerField(required=False, allow_null=True),
                "title": serializers.CharField(required=False),
            },
        ),
        responses={201: inline_serializer("AttachmentTaken", {"id": serializers.IntegerField()})},
    )
    def post(self, request: Request, project_pk: int, mail_pk: int, attachment_pk: int) -> Response:
        """Store the attachment as a file of the project, with a document type."""
        project = _project(request, project_pk, ProjectAccess.EDIT)
        stored = get_object_or_404(MailAttachment, pk=attachment_pk, mail=_mail(request, project, mail_pk))
        body = body_of(request)
        document_type = None
        if body.get("document_type"):
            document_type = DocumentType.objects.filter(pk=body.get("document_type"), is_active=True).first()
            if document_type is None:
                raise ValidationError({"document_type": _("Choose an active document type.")})
        project_file = add_file_from_attachment(
            stored, user=request.user, document_type=document_type, title=str(body.get("title", ""))
        )
        return Response(
            {"id": project_file.pk, "title": project_file.label, "visible_to_crew": project_file.visible_to_crew},
            status=status.HTTP_201_CREATED,
        )


# --- The module "E-mail" ------------------------------------------------------------------------------


def unknown_document(unknown: UnknownTagMail, *, user: Any = None, rights: Any = None) -> dict[str, Any]:
    """One mail of the list under Projects → Inquiries; ``tag`` is empty for an inquiry (EML-041).

    EML-053: the fields of an inquiry noted by hand follow those of
    earlier inquiries, which keep their meaning (the companion app reads them).
    """
    if unknown.is_manual:
        source = "manual"
    elif unknown.is_defect:
        source = "defect"
    else:
        source = "mail"
    return {
        "id": unknown.pk,
        "subject": unknown.subject,
        "sender": unknown.sender,
        "date": unknown.date,
        "tag": unknown.tag,
        "is_inquiry": unknown.is_inquiry,
        # MAT-057: an entry made of a defect report by an automation – no mail; it becomes a service case
        # (``POST /service-cases`` with ``inquiry``) or is dismissed.
        "defect_report": unknown.defect_report_id,
        "mailbox": unknown.mailbox_id,
        "mailbox_name": str(unknown.mailbox) if unknown.mailbox_id else None,
        "first_seen_at": unknown.first_seen_at,
        # EML-053: ``mail``, ``defect`` – or ``manual``: noted by hand, with what was noted.
        "source": source,
        "contact_name": unknown.contact_name,
        "contact_email": unknown.contact_email,
        "phone": unknown.phone,
        "customer": unknown.customer_id,
        "customer_name": unknown.customer.name if unknown.customer_id else None,
        "note": unknown.note,
        "created_by": unknown.created_by_id,
        "created_by_name": str(unknown.created_by) if unknown.created_by_id else None,
        "can_change": bool(user is not None and rights is not None and inquiries.may_change(unknown, user, rights)),
    }


class ManualInquirySerializer(serializers.Serializer):
    """EML-053: an inquiry noted by hand – who and when, what it is about.

    It needs someone to get back to (``contact_name``, ``phone``,
    ``contact_email`` or ``customer``) and something it is about (``subject``
    or ``note``); ``date`` is now when left out and never in the future.
    """

    date = serializers.DateTimeField(required=False, help_text="When the inquiry came in; now when left out.")
    contact_name = serializers.CharField(required=False, allow_blank=True, max_length=200, help_text="Who called.")
    phone = serializers.CharField(required=False, allow_blank=True, max_length=60)
    contact_email = serializers.EmailField(required=False, allow_blank=True)
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all(), required=False, allow_null=True)
    subject = serializers.CharField(required=False, allow_blank=True, max_length=inquiries.MAX_SUBJECT)
    note = serializers.CharField(required=False, allow_blank=True, max_length=inquiries.MAX_NOTE)


class UnknownTagListView(ModuleAPIView):
    """``GET /mail/unknown`` – mails waiting in an inbox to be taken over (EML-014, EML-041, EML-042).

    Mails whose tag names no project, and – from mailboxes that take them in –
    mails without a tag (inquiries, ``is_inquiry``). They stay in the inbox.

    EML-053: ``POST`` notes an inquiry by hand (``source`` "manual");
    it needs write access to "E-mail", as taking inquiries over does.
    """

    module = Module.EMAIL
    schema_tag = "mail"

    @extend_schema(responses={200: inline_serializer("UnknownTags", {"id": serializers.IntegerField()}, many=True)})
    def get(self, request: Request) -> Response:
        """The open entries, newest first."""
        waiting = UnknownTagMail.objects.filter(resolved_at__isnull=True).select_related(
            "mailbox", "customer", "created_by"
        )
        return Response([unknown_document(item, user=request.user, rights=self.rights) for item in waiting])

    @extend_schema(
        operation_id="mail_unknown_note",
        request=ManualInquirySerializer,
        responses={201: inline_serializer("UnknownNoted", {"id": serializers.IntegerField()})},
    )
    def post(self, request: Request) -> Response:
        """EML-053: note an inquiry by hand – e.g. a phone call. Nothing is sent, no automation runs."""
        serializer = ManualInquirySerializer(data=body_of(request))
        serializer.is_valid(raise_exception=True)
        inquiry = inquiries.create_manual(user=request.user, **serializer.validated_data)
        return Response(
            unknown_document(inquiry, user=request.user, rights=self.rights), status=status.HTTP_201_CREATED
        )


class UnknownTagDetailView(ModuleAPIView):
    """``/mail/unknown/{id}`` – one entry; an inquiry noted by hand is changed or deleted here (EML-053).

    Reading needs the module "E-mail"; changing and deleting an inquiry noted
    by hand who noted it or who may write in "E-mail". A mail or a defect
    report cannot be changed – it is taken over or dismissed.
    """

    module = Module.EMAIL
    schema_tag = "mail"
    # Changing and deleting are checked in the view: who noted the inquiry may, whatever the level.
    action_levels = {None: Level.READ}

    def _waiting(self, pk: int) -> UnknownTagMail:
        return get_object_or_404(
            UnknownTagMail.objects.select_related("mailbox", "customer", "created_by"), pk=pk, resolved_at__isnull=True
        )

    def _changeable(self, pk: int) -> UnknownTagMail:
        inquiry = self._waiting(pk)
        inquiries.ensure_manual(inquiry)
        if not inquiries.may_change(inquiry, self.request.user, self.rights):
            raise PermissionDenied
        return inquiry

    @extend_schema(
        operation_id="mail_unknown_entry",
        responses={200: inline_serializer("UnknownEntry", {"id": serializers.IntegerField()})},
    )
    def get(self, request: Request, pk: int) -> Response:
        """The waiting entry."""
        return Response(unknown_document(self._waiting(pk), user=request.user, rights=self.rights))

    @extend_schema(
        operation_id="mail_unknown_entry_update",
        request=ManualInquirySerializer,
        responses={200: inline_serializer("UnknownChanged", {"id": serializers.IntegerField()})},
    )
    def patch(self, request: Request, pk: int) -> Response:
        """Change an inquiry noted by hand; fields left out stay."""
        inquiry = self._changeable(pk)
        serializer = ManualInquirySerializer(data=body_of(request), partial=True)
        serializer.is_valid(raise_exception=True)
        inquiries.update_manual(inquiry, **serializer.validated_data)
        return Response(unknown_document(inquiry, user=request.user, rights=self.rights))

    @extend_schema(operation_id="mail_unknown_entry_delete", responses={204: None})
    def delete(self, request: Request, pk: int) -> Response:
        """Delete an inquiry noted by hand."""
        inquiries.delete_manual(self._changeable(pk))
        return Response(status=status.HTTP_204_NO_CONTENT)


class UnknownTagAssignView(ModuleAPIView):
    """``POST /mail/unknown/{id}/assign`` – take such a mail into a project by hand (EML-014, EML-042)."""

    module = Module.EMAIL
    schema_tag = "mail"

    @extend_schema(
        request=inline_serializer(
            "UnknownAssign",
            {
                "project": serializers.IntegerField(required=False),
                "project_number": serializers.CharField(required=False),
            },
        ),
        responses={200: inline_serializer("UnknownAssigned", {"mail": serializers.IntegerField()})},
    )
    def post(self, request: Request, pk: int) -> Response:
        """Fetch the mail from the inbox of its mailbox and store it with the project."""
        unknown = get_object_or_404(UnknownTagMail, pk=pk, resolved_at__isnull=True)
        project = _target_project(request, body_of(request), ProjectAccess.READ)
        try:
            mail = assign_unknown(unknown, project)
        except MailboxError as error:
            raise ValidationError(str(error)) from error
        return Response({"mail": mail.pk, "project": project.pk})


class UnknownTagDismissView(ModuleAPIView):
    """``POST /mail/unknown/{id}/dismiss`` – take a mail off the list; it stays in the inbox."""

    module = Module.EMAIL
    schema_tag = "mail"

    @extend_schema(request=None, responses={204: None})
    def post(self, request: Request, pk: int) -> Response:
        """Mark the entry as dealt with."""
        unknown = get_object_or_404(UnknownTagMail, pk=pk, resolved_at__isnull=True)
        unknown.resolved_at = timezone.now()
        unknown.save(update_fields=["resolved_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class UnknownTagDismissManyView(ModuleAPIView):
    """``POST /mail/unknown/dismiss`` – take several mails off the list at once; they stay in the inbox (PRJ-107)."""

    module = Module.EMAIL
    schema_tag = "mail"

    @extend_schema(
        operation_id="mail_unknown_dismiss_many",
        request=inline_serializer(
            "UnknownDismissMany", {"ids": serializers.ListField(child=serializers.IntegerField())}
        ),
        responses={200: inline_serializer("UnknownDismissed", {"dismissed": serializers.IntegerField()})},
    )
    def post(self, request: Request) -> Response:
        """Mark the entries as dealt with; ``dismissed`` says how many were still waiting."""
        ids = body_of(request).get("ids") or []
        if not isinstance(ids, list) or not all(isinstance(value, int) for value in ids):
            raise ValidationError({"ids": _("A list of IDs is expected.")})
        return Response({"dismissed": dismiss_waiting(ids)})


class FetchNowView(ModuleAPIView):
    """``POST /mail/fetch`` – fetch every mailbox of the correspondence at once (EML-005, EML-041).

    ``mailboxes`` tells per mailbox what happened; a mailbox that fails does
    not stop the others.
    """

    module = Module.EMAIL
    schema_tag = "mail"
    # Fetching is something everybody with the module may trigger, like the button.
    # A plain view has no named action: the key ``None`` stands for all its methods.
    action_levels = {None: Level.READ}

    @extend_schema(
        request=None,
        responses={200: inline_serializer("FetchResult", {"looked_at": serializers.IntegerField()})},
    )
    def post(self, request: Request) -> Response:
        """Fetch new mails and tell what happened."""
        result = fetch_mail(force=True)
        return Response(
            {
                "ok": result.ok,
                "looked_at": result.looked_at,
                "assigned": [mail.pk for mail in result.imported],
                "unknown": [item.pk for item in result.unknown],
                "inquiries": [item.pk for item in result.inquiries],
                "skipped": result.skipped,
                "error": result.error,
                "mailboxes": [
                    {
                        "id": part.mailbox.pk if part.mailbox is not None else None,
                        "name": str(part.mailbox) if part.mailbox is not None else "",
                        "looked_at": part.looked_at,
                        "assigned": [mail.pk for mail in part.imported],
                        "unknown": [item.pk for item in part.unknown],
                        "inquiries": [item.pk for item in part.inquiries],
                        "error": part.error,
                    }
                    for part in result.mailboxes
                ],
            }
        )


class MailboxSerializer(serializers.ModelSerializer):
    """A mailbox with its roles (EML-041). Passwords can be set (``imap_password``, ``smtp_password``), never read.

    Roles: ``for_correspondence`` – fetched and assigned by the tag;
    ``is_outgoing`` – sends the mails written in projects (exactly one active
    mailbox of the correspondence); ``for_system`` – sends invitations and
    notifications (at most one). Giving ``is_outgoing`` or ``for_system`` to a
    mailbox takes it from the mailbox that had it.

    Incoming: ``process_untagged`` takes in mails without tag as inquiries –
    EML-049: only those that arrived in the mailbox from
    ``untagged_since`` on (set to the moment of switching on when not sent;
    ``null`` while switched off) and, with ``untagged_unread_only``, only
    unread ones; the others stay in the inbox untouched.
    ``after_assignment`` is ``move`` (into ``done_folder``), ``delete`` or
    ``keep``. ``smtp_same_login`` sends with the IMAP user and password
    (EML-035). The state of the last fetch is read-only.

    EML-052: ``sender_roles`` – the IDs of the roles whose members may
    choose the mailbox's address as sender of a project mail (the mailbox
    that sends the correspondence is open to everybody who may write
    correspondence). EML-026: ``signature_html`` – the mailbox's own
    signature, cleaned like the common one; empty means the common one.
    Changing it needs the right of the common signature (write access to the
    administration).
    """

    imap_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    smtp_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    has_imap_password = serializers.SerializerMethodField()
    has_smtp_password = serializers.SerializerMethodField()
    # EML-047: the further addresses, read-only here; changed under /mail/mailbox-addresses.
    addresses = serializers.SerializerMethodField()
    signature_html = serializers.CharField(required=False, allow_blank=True, max_length=SIGNATURE_MAX_LENGTH)

    class Meta:
        model = Mailbox
        fields = [
            "id",
            "name",
            "address",
            "is_active",
            "for_correspondence",
            "is_outgoing",
            "for_system",
            "imap_host",
            "imap_port",
            "imap_security",
            "imap_user",
            "imap_password",
            "has_imap_password",
            "inbox_folder",
            "process_untagged",
            "untagged_since",
            "untagged_unread_only",
            "after_assignment",
            "done_folder",
            "smtp_host",
            "smtp_port",
            "smtp_security",
            "smtp_same_login",
            "smtp_user",
            "smtp_password",
            "has_smtp_password",
            "last_fetch_at",
            "last_success_at",
            "last_error",
            "last_error_at",
            "addresses",
            "sender_roles",  # EML-052
            "signature_html",  # EML-026
        ]
        read_only_fields = ["last_fetch_at", "last_success_at", "last_error", "last_error_at"]

    def get_has_imap_password(self, mailbox: Mailbox) -> bool:
        """Whether a password is stored."""
        return bool(mailbox.imap_password_encrypted)

    def get_has_smtp_password(self, mailbox: Mailbox) -> bool:
        """Whether an own SMTP password is stored."""
        return bool(mailbox.smtp_password_encrypted)

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_addresses(self, mailbox: Mailbox) -> list[dict[str, Any]]:
        """EML-047: the further addresses with their rule for mails without tag and their role."""
        return [MailboxAddressSerializer(alias).data for alias in mailbox.aliases.all()]


class MailboxAddressSerializer(serializers.ModelSerializer):
    """A further address (alias) of a mailbox (EML-047).

    ``untagged``: what becomes of a mail without project tag to this address –
    ``ignore`` (left in the inbox), ``inquiry`` (Projekte → Anfragen) or
    ``service_case`` (a service case is made at once, ``case_manager``
    responsible). ``for_service_cases``: mails written in a service case go
    out with this address as sender; giving it to an address takes it from
    the one that had it.

    EML-049: ``untagged_since`` and ``untagged_unread_only`` as for the
    mailbox, for the mails without tag this address takes in.

    EML-052: ``sender_roles`` – the IDs of the roles whose members may
    choose this address as sender of a project mail.
    """

    class Meta:
        model = MailboxAddress
        fields = [
            "id",
            "mailbox",
            "address",
            "untagged",
            "untagged_since",
            "untagged_unread_only",
            "for_service_cases",
            "case_manager",
            "sender_roles",  # EML-052
        ]
        # The address is compared in lower case below, and the error belongs to the field "address".
        validators: ClassVar[list[Any]] = []

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """One address only once per mailbox, in lower case."""
        attrs = super().validate(attrs)
        if "address" in attrs:
            attrs["address"] = attrs["address"].strip().lower()
        mailbox = attrs.get("mailbox") or getattr(self.instance, "mailbox", None)
        address = attrs.get("address") or getattr(self.instance, "address", "")
        if mailbox is not None and (
            MailboxAddress.objects.filter(mailbox=mailbox, address=address)
            .exclude(pk=getattr(self.instance, "pk", None))
            .exists()
        ):
            raise serializers.ValidationError({"address": _("This address is listed for the mailbox already.")})
        return attrs


class MailboxAddressViewSet(ModuleViewSet):
    """``/mail/mailbox-addresses`` – the further addresses of the mailboxes (EML-047); ``?mailbox=`` filters.

    Like the mailboxes themselves, reading and changing need write access to
    the module "E-mail", deleting needs delete access.
    """

    module = Module.EMAIL
    schema_tag = "mail"
    serializer_class = MailboxAddressSerializer
    queryset = MailboxAddress.objects.select_related("mailbox").order_by("mailbox_id", "address", "pk")
    action_levels: ClassVar[dict[str, int]] = {"list": Level.WRITE, "retrieve": Level.WRITE}

    def get_queryset(self) -> Any:
        """Optionally only the addresses of one mailbox."""
        queryset = super().get_queryset()
        mailbox = str(self.request.query_params.get("mailbox", ""))
        return queryset.filter(mailbox_id=int(mailbox)) if mailbox.isdigit() else queryset

    @transaction.atomic
    def perform_create(self, serializer: Any) -> None:
        """Store the address by the rule of its role; EML-052: with the roles that may send from it."""
        values = dict(serializer.validated_data)
        roles = values.pop("sender_roles", None)
        alias = MailboxAddress(**values)
        save_address(alias)
        if roles is not None:
            alias.sender_roles.set(roles)
        serializer.instance = alias

    @transaction.atomic
    def perform_update(self, serializer: Any) -> None:
        """Change the address by the rule of its role; EML-052: with the roles that may send from it."""
        alias = serializer.instance
        values = dict(serializer.validated_data)
        roles = values.pop("sender_roles", None)
        for name, value in values.items():
            setattr(alias, name, value)
        save_address(alias)
        if roles is not None:
            alias.sender_roles.set(roles)


@transaction.atomic
def _store_mailbox(mailbox: Mailbox, values: dict[str, Any], *, rights: Any = None) -> Mailbox:
    """Apply checked values to a mailbox and store it by the rules of ``mail.mailboxes`` (EML-041).

    EML-052, EML-026: the roles that may send from its address, and its signature – cleaned, and changed
    only with the right of the common signature.

    Raises:
        PermissionDenied: The signature is changed without that right.
    """
    values = dict(values)
    imap_password = values.pop("imap_password", "")
    smtp_password = values.pop("smtp_password", "")
    roles = values.pop("sender_roles", None)
    signature = values.pop("signature_html", None)
    if signature is not None:
        cleaned = clean_signature(signature)
        if cleaned != mailbox.signature_html and (rights is None or not services.may_edit_signature(rights)):
            raise PermissionDenied(_("Changing a signature needs write access to the settings."))
        mailbox.signature_html = cleaned
    for name, value in values.items():
        setattr(mailbox, name, value)
    save_mailbox(mailbox, imap_password=imap_password, smtp_password=smtp_password)
    if roles is not None:
        mailbox.sender_roles.set(roles)
    return mailbox


#: The outcome of a connection check, per side of the mailbox.
CHECK_SCHEMA = inline_serializer(
    "MailboxCheck",
    {"part": serializers.CharField(), "ok": serializers.BooleanField(), "text": serializers.CharField()},
    many=True,
)


class MailboxViewSet(ModuleViewSet):
    """``/mail/mailboxes`` – the mailboxes Rentalars fetches from and sends through (EML-041).

    Reading and changing need write access to the module "E-mail" (the access
    data are as sensitive as the mailbox itself), deleting needs delete
    access.

    EML-046: ``DELETE`` deletes the mailbox, also one through which mails
    came in or went out: the
    mails and the mail log keep its name (``mailbox_name``), waiting
    inquiries leave the list, and no mailbox has its roles afterwards. If it
    sends the correspondence while other mailboxes of the correspondence stay
    active, ``?successor=<id>`` names the one that sends from now on (needed
    when more than one can). To switch a mailbox off instead, ``PATCH`` it
    with ``is_active: false``.
    """

    module = Module.EMAIL
    schema_tag = "mail"
    serializer_class = MailboxSerializer
    queryset = Mailbox.objects.all()
    action_levels: ClassVar[dict[str, int]] = {"list": Level.WRITE, "retrieve": Level.WRITE, "check": Level.WRITE}

    def perform_create(self, serializer: Any) -> None:
        """Store a new mailbox by the rules of its roles."""
        serializer.instance = _store_mailbox(Mailbox(), serializer.validated_data, rights=self.rights)

    def perform_update(self, serializer: Any) -> None:
        """Change a mailbox; a password is only replaced when a new one is sent."""
        _store_mailbox(serializer.instance, serializer.validated_data, rights=self.rights)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "successor",
                int,
                description=(
                    "The mailbox that sends the correspondence from now on, when the deleted one did while other "
                    "mailboxes of the correspondence stay active (EML-046)."
                ),
            )
        ],
        responses={204: None},
    )
    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Delete the mailbox; mails and mail log keep its name (EML-046)."""
        mailbox = self.get_object()
        successor_id = str(request.query_params.get("successor", ""))
        successor = Mailbox.objects.filter(pk=int(successor_id)).first() if successor_id.isdigit() else None
        delete_mailbox(mailbox, successor=successor)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=None, responses=CHECK_SCHEMA)
    @action(detail=True, methods=["post"], filter_backends=[], pagination_class=None)
    def check(self, request: Request, pk: str | None = None) -> Response:
        """Log in to the IMAP and the SMTP server of the mailbox; nothing is changed or sent."""
        return Response(
            [{"part": item.part, "ok": item.ok, "text": item.text} for item in check_connection(self.get_object())]
        )


#: The rules for all mailboxes in ``/mail/settings``.
#: PER-032: ``crew_answers`` – how deployment requests are answered: ``link``, ``mail`` or ``both``.
RULE_FIELDS = (
    "sender_name",
    "interval_minutes",
    "max_message_mb",
    "retention_days",
    "crew_answers",
    # EML-055: how new messages start.
    "lock_new_in_projects",
    "lock_new_in_cases",
    # S2: the name of the own mail server in ``Authentication-Results``; set, only confirmed answers count.
    "crew_answer_trusted_server",
)


class MailSettingsSerializer(serializers.ModelSerializer):
    """The rules for all mailboxes, and the fields of the legacy mailbox.

    ``sender_name`` (only for mails without a known writer, EML-038),
    ``interval_minutes``, ``max_message_mb`` and ``retention_days`` hold for
    all mailboxes. The other fields are those of the one mailbox of before
    They now mean the mailbox that sends the correspondence (or the
    first of the correspondence), and changing them creates it if there is
    none yet. ``is_enabled`` is its ``is_active``, ``delete_after_import``
    its ``after_assignment`` = ``delete``. New clients use
    ``/mail/mailboxes`` (EML-041).

    PER-032: ``crew_answers`` says how deployment requests are answered –
    ``link``, ``mail`` (reply mail) or ``both``; ``crew_answer_address`` is
    the address of the mailbox the answers by mail go to, ``null`` if no
    mailbox that Rentalars fetches can take them (then only the link).
    """

    is_enabled = serializers.BooleanField(source="is_active", required=False)
    delete_after_import = serializers.BooleanField(required=False)
    imap_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    smtp_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    has_imap_password = serializers.SerializerMethodField()
    has_smtp_password = serializers.SerializerMethodField()
    sender_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    interval_minutes = serializers.IntegerField(min_value=1, max_value=60, required=False)
    max_message_mb = serializers.IntegerField(min_value=1, max_value=200, required=False)
    retention_days = serializers.IntegerField(min_value=0, required=False)
    crew_answers = serializers.ChoiceField(choices=CrewAnswerMode.choices, required=False)
    crew_answer_address = serializers.SerializerMethodField()
    # EML-055: whether new messages of projects, of service cases start with the lock.
    lock_new_in_projects = serializers.BooleanField(required=False)
    lock_new_in_cases = serializers.BooleanField(required=False)
    crew_answer_trusted_server = serializers.CharField(max_length=120, required=False, allow_blank=True)

    class Meta:
        model = Mailbox
        fields = [
            "is_enabled",
            "address",
            "sender_name",
            "imap_host",
            "imap_port",
            "imap_security",
            "imap_user",
            "imap_password",
            "has_imap_password",
            "smtp_host",
            "smtp_port",
            "smtp_security",
            "smtp_same_login",
            "smtp_user",
            "smtp_password",
            "has_smtp_password",
            "inbox_folder",
            "done_folder",
            "delete_after_import",
            "interval_minutes",
            "max_message_mb",
            "retention_days",
            "crew_answers",
            "crew_answer_address",
            "lock_new_in_projects",
            "lock_new_in_cases",
            "crew_answer_trusted_server",
            "last_fetch_at",
            "last_success_at",
            "last_error",
            "last_error_at",
        ]
        read_only_fields = ["last_fetch_at", "last_success_at", "last_error", "last_error_at"]

    def get_has_imap_password(self, mailbox: Mailbox) -> bool:
        """Whether a password is stored."""
        return bool(mailbox.imap_password_encrypted)

    def get_has_smtp_password(self, mailbox: Mailbox) -> bool:
        """Whether an own SMTP password is stored."""
        return bool(mailbox.smtp_password_encrypted)

    def get_crew_answer_address(self, mailbox: Mailbox) -> str | None:
        """PER-032: where the answers to deployment requests go by mail; ``null``: no mailbox can take them."""
        answers = answer_mailbox()
        return answers.address if answers is not None else None

    def to_representation(self, instance: Any) -> dict[str, Any]:
        """The mailbox fields of the mailbox, the rules from the mail settings."""
        rules = MailSettings.load()
        for name in RULE_FIELDS:
            setattr(instance, name, getattr(rules, name))
        return super().to_representation(instance)


def settings_document() -> dict[str, Any]:
    """``/mail/settings`` as read: the rules and the mailbox that sends the correspondence."""
    mailbox = legacy_mailbox() or Mailbox(is_active=False)
    return dict(MailSettingsSerializer(mailbox).data)


class MailSettingsView(ModuleAPIView):
    """``/mail/settings`` – the rules for all mailboxes, and the fields of the legacy mailbox (EML-002, EML-041).

    Reading and changing need write access.
    """

    module = Module.EMAIL
    schema_tag = "mail"

    def _require_write(self) -> None:
        if not self.rights.can_write(Module.EMAIL):
            raise PermissionDenied

    @extend_schema(responses=MailSettingsSerializer)
    def get(self, request: Request) -> Response:
        """The settings, without passwords."""
        self._require_write()
        return Response(settings_document())

    @extend_schema(request=MailSettingsSerializer, responses=MailSettingsSerializer)
    def patch(self, request: Request) -> Response:
        """Change single settings; a password is only replaced when a new one is sent."""
        self._require_write()
        serializer = MailSettingsSerializer(data=body_of(request), partial=True)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        rules_values = {name: values.pop(name) for name in RULE_FIELDS if name in values}
        with transaction.atomic():
            if rules_values:
                rules = MailSettings.load()
                for name, value in rules_values.items():
                    setattr(rules, name, value)
                services.save_settings(rules)
            if values:
                _store_legacy_mailbox(values)
        return Response(settings_document())


def _store_legacy_mailbox(values: dict[str, Any]) -> None:
    """Change the legacy mailbox – created for the correspondence if there is none (EML-041)."""
    mailbox = legacy_mailbox()
    if mailbox is None:
        mailbox = Mailbox(name=_("Projects"), for_correspondence=True, is_outgoing=True, is_active=False)
    delete = values.pop("delete_after_import", None)
    if delete:
        values["after_assignment"] = AfterAssignment.DELETE
    elif delete is not None and mailbox.after_assignment == AfterAssignment.DELETE:
        values["after_assignment"] = AfterAssignment.MOVE
    _store_mailbox(mailbox, values)


class AddressSuggestionsView(ModuleAPIView):
    """``GET /mail/address-suggestions?q=…`` – addresses for the recipient fields (EML-037).

    For who may write mails. Customers and their contacts are searched with
    read access to the customers, people with read access to the personnel;
    ``q`` needs at least three characters.
    """

    module = AUTHENTICATED_ONLY
    schema_tag = "mail"

    @extend_schema(
        parameters=[OpenApiParameter("q", str, description="Part of a name or address, at least three characters.")],
        responses={
            200: inline_serializer(
                "AddressSuggestions",
                {
                    "label": serializers.CharField(),
                    "name": serializers.CharField(),
                    "address": serializers.CharField(),
                    "hint": serializers.CharField(),
                    "detail": serializers.CharField(),
                },
                many=True,
            )
        },
    )
    def get(self, request: Request) -> Response:
        """Up to ten addresses that match ``q``."""
        services.require_mail_write(self.rights)
        found = suggest_addresses(self.rights, str(request.query_params.get("q", "")))
        return Response([suggestion.as_json() for suggestion in found])


def signature_document(request: Request) -> dict[str, Any]:
    """The stored signature, its placeholders, and how it looks with the caller's data (EML-034)."""
    rendered = render_signature(request.user)
    return {
        "html": MailSettings.load().signature_html,
        "placeholders": [{"token": item.token, "label": str(item.label)} for item in shown_placeholders()],
        "preview_html": rendered.html,
        "preview_text": rendered.text,
    }


class MailSignatureView(ModuleAPIView):
    """``/mail/signature`` – the signature of everybody (EML-034).

    Read by everybody who may write mails, set up the mailbox or read the
    settings; changed with write access to the administration. The HTML is
    cleaned on saving; placeholders such as ``{vorname}`` are filled with
    the data of whoever writes a mail.
    """

    module = Module.ADMINISTRATION
    schema_tag = "mail"
    # Reading is checked in the view: the right to write mails is no module level.
    read_for_all = True

    @extend_schema(
        responses={
            200: inline_serializer(
                "MailSignature",
                {
                    "html": serializers.CharField(),
                    "preview_html": serializers.CharField(),
                    "preview_text": serializers.CharField(),
                },
            )
        }
    )
    def get(self, request: Request) -> Response:
        """The signature as stored, and filled with the caller's data."""
        if not services.may_see_signature(self.rights):
            raise PermissionDenied
        return Response(signature_document(request))

    @extend_schema(
        request=inline_serializer("MailSignatureChange", {"html": serializers.CharField(allow_blank=True)}),
        responses={200: inline_serializer("MailSignatureChanged", {"html": serializers.CharField()})},
    )
    def patch(self, request: Request) -> Response:
        """Replace the signature; an empty text removes it."""
        if not services.may_edit_signature(self.rights):
            raise PermissionDenied
        body = body_of(request)
        source = body.get("html", "")
        if not isinstance(source, str):
            raise ValidationError({"html": _("Send the signature as text.")})
        if len(source) > SIGNATURE_MAX_LENGTH:
            raise ValidationError({"html": _("The signature is too long.")})
        current = MailSettings.load()
        current.signature_html = clean_signature(source)
        current.save(update_fields=["signature_html"])
        return Response(signature_document(request))


def log_document(entry: MailLogEntry) -> dict[str, Any]:
    """One entry of the mail log (EML-039)."""
    return {
        "id": entry.pk,
        "timestamp": entry.timestamp,
        "direction": entry.direction,
        "kind": entry.kind,
        "result": entry.result,
        "sender": entry.sender,
        "recipients": entry.recipients,
        "subject": entry.subject,
        "project": entry.project_id,
        "project_number": entry.project.number if entry.project is not None else None,
        "mail": entry.mail_id,
        "sent_by": str(entry.user) if entry.user_id else None,
        "detail": entry.detail_text,
        # EML-041: the mailbox the mail went through. EML-046: the name stays when the mailbox is deleted
        # (``mailbox`` is then ``null``).
        "mailbox": entry.mailbox_id,
        "mailbox_name": entry.mailbox_name or (str(entry.mailbox) if entry.mailbox_id else None),
        "mailbox_deleted": entry.mailbox_id is None and bool(entry.mailbox_name),
    }


class MailLogView(ModuleAPIView):
    """``GET /mail/log`` – every mail in and out with its result (EML-039).

    Filters: ``since`` and ``until`` (a day ``2027-03-01`` or an ISO time),
    ``direction`` (``in``/``out``), ``kind`` (``project``/``system``),
    ``result`` and ``q`` (address, subject, detail, project number, name of
    the mailbox). Newest first, 50 per page. Each entry names the mailbox it
    went through (EML-041). Needs read access to the administration.
    """

    module = Module.ADMINISTRATION
    schema_tag = "mail"

    @extend_schema(
        parameters=[
            OpenApiParameter("since", str, description="From this day or moment on."),
            OpenApiParameter("until", str, description="Up to and including this day, or up to this moment."),
            # The log knows received and sent mails only – no notes (EML-051).
            OpenApiParameter("direction", str, enum=[value for value, _label in LOG_DIRECTIONS]),
            OpenApiParameter("kind", str, enum=LogKind.values),
            OpenApiParameter("result", str, enum=LogResult.values),
            OpenApiParameter("q", str, description="Found in addresses, subject, detail, project number or mailbox."),
        ],
        responses={
            200: inline_serializer(
                "MailLog",
                {
                    "count": serializers.IntegerField(),
                    "results": inline_serializer(
                        "MailLogEntry",
                        {
                            "id": serializers.IntegerField(),
                            "timestamp": serializers.DateTimeField(),
                            "direction": serializers.CharField(),
                            "kind": serializers.CharField(),
                            "result": serializers.CharField(),
                            "subject": serializers.CharField(),
                        },
                        many=True,
                    ),
                },
            )
        },
    )
    def get(self, request: Request) -> Response:
        """The entries, paginated."""
        from rentalars.api.pagination import StandardPagination

        params = request.query_params
        entries = filtered_entries(
            since=_moment(params.get("since", "")),
            until=_moment(params.get("until", "")),
            direction=str(params.get("direction", "")),
            kind=str(params.get("kind", "")),
            result=str(params.get("result", "")),
            text=str(params.get("q", "")),
        ).order_by("-timestamp", "-id")
        paginator = StandardPagination()
        page = paginator.paginate_queryset(entries, request, view=self)
        return paginator.get_paginated_response([log_document(entry) for entry in page or []])


def _moment(value: str) -> datetime.date | datetime.datetime | None:
    """A day or a moment from a filter parameter.

    Raises:
        ValidationError: The value is neither.
    """
    value = (value or "").strip()
    if not value:
        return None
    moment = parse_datetime(value)
    if moment is not None:
        return moment if timezone.is_aware(moment) else timezone.make_aware(moment)
    day = parse_date(value)
    if day is None:
        raise ValidationError(_("Give a day as 2027-03-01 or a time as 2027-03-01T08:00."))
    return day
