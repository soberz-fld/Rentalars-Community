# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views of the mail module (chapter 5.15).

* In the project: the correspondence as a list or as a conversation
  (EML-019, EML-036), one mail with its attachments in a compact view
  (EML-020, EML-021, EML-027, EML-036), writing and answering – also to
  everybody, with CC, BCC and address suggestions (EML-024, EML-025,
  EML-037) – and assigning to another project (EML-015).
* Under "Projects", in the tab "Inquiries": mails with an unknown tag and,
  from mailboxes that take them in, mails without a tag (EML-014, EML-041,
  EML-042). The tab belongs to the module "E-mail".
* In the settings ("administration/"): the mailboxes with their roles,
  state, "check connection" and "fetch now" (EML-002, EML-005, EML-032,
  EML-035, EML-041), the rules for all mailboxes, the signature (EML-034)
  and the mail log (EML-039).

The sender is chosen when writing, among the addresses the writer
may use (EML-052, ``mail.senders``); a mailbox may have a signature of its
own (EML-026); inquiries can be noted by hand – e.g. a phone call – under
Projekte → Anfragen (EML-053, ``mail.inquiries``).

EML-055: every message shows whether it has a lock; who may set it
changes it per message (:func:`mail_lock`) and chooses it when writing. The
crew reads the open messages of its projects; a message the user may not read
does not exist for him (``mail.locks``).

Rights: see ``mail.services`` (EML-029) and ``mail.locks``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.html import escape
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from rentalars.accounts.rights import Level, Module, module_required, request_rights
from rentalars.core.forms import add_validation_error
from rentalars.core.listing import paginate
from rentalars.core.redirects import safe_next_url
from rentalars.core.uploads import document_response
from rentalars.documents import free_mail
from rentalars.mail import crew_answers, inquiries, locks, mailboxes, notes, salutation, senders, services
from rentalars.mail.addresses import crew_recipients, customer_recipient, suggest_addresses
from rentalars.mail.aliases import delete_address, save_address, takes_untagged
from rentalars.mail.display import (
    clean_html,
    content_security_policy,
    frame_document,
    frame_size,
    html_to_text,
    split_quoted,
)
from rentalars.mail.fetching import assign_unknown, dismiss_waiting, fetch_mail
from rentalars.mail.forms import (
    AssignForm,
    AttachmentToFilesForm,
    ComposeForm,
    InquiryForm,
    MailboxAddressForm,
    MailboxForm,
    MailRulesForm,
    NoteForm,
    SignatureForm,
)
from rentalars.mail.imap import MailboxError
from rentalars.mail.log import filtered_entries
from rentalars.mail.log import retention_days as log_retention_days
from rentalars.mail.models import (
    Direction,
    InquirySource,
    LogKind,
    LogResult,
    MailAttachment,
    Mailbox,
    MailboxAddress,
    MailSettings,
    ProjectMail,
    UnknownTagMail,
)
from rentalars.mail.parsing import format_address
from rentalars.mail.sending import (
    chosen_attachments,
    document_choices,
    note_documents_sent,
    quoted,
    reply_recipients,
    reply_subject,
    send_project_mail,
)
from rentalars.mail.server import not_sent_text
from rentalars.mail.signature import (
    render_signature,
    sender_label,
    sender_name,
    shown_placeholders,
    signature_source,
)
from rentalars.mail.suppliers import supplier_from
from rentalars.mail.tables import DIRECTION_LABELS, INQUIRY_TABLE, MAIL_LOG_TABLE
from rentalars.mail.tags import current_prefix
from rentalars.projects.access import ProjectAccess, access_level, project_for, readable_projects
from rentalars.projects.case_work import case_work_required
from rentalars.projects.case_work import require as require_case_work
from rentalars.projects.files import add_file_from_attachment
from rentalars.projects.models import Project
from rentalars.projects.numbers import project_by_number
from rentalars.projects.subrentals import suppliers_of


def _project(request: HttpRequest, pk: int, level: ProjectAccess = ProjectAccess.READ) -> Project:
    """The project, for a user who may read its correspondence (EML-029).

    The project is looked up first: for a project the user may not see, the
    answer is "not found", whatever the other rights are (AUT-020).

    AUT-033 (PRJ-108): the correspondence of a service case is open to whoever
    works on it – they read the case (``project_for``) –; that of a project
    stays confidential: the special rights (``projects.case_work``).
    Operations that need edit access stay closed to them.

    EML-055: reading also opens to the crew planned in the project – the
    deployment view is enough – for the open messages (``mail.locks``).
    """
    project = project_for(request, pk, ProjectAccess.DEPLOYMENT if level <= ProjectAccess.READ else level)
    require_case_work(locks.correspondence_of(request, project).reads_any)
    return project


def _mail(request: HttpRequest, project: Project, mail_pk: int, **conditions: Any) -> ProjectMail:
    """A message of the project that the user reads; one with lock is "not found" without the right (EML-055)."""
    mail = get_object_or_404(ProjectMail, pk=mail_pk, project=project, **conditions)
    if not locks.correspondence_of(request, project).may_read(mail):
        raise Http404
    return mail


def _write(request: HttpRequest, project: Project) -> locks.Correspondence:
    """The correspondence for a user who writes in it; refused (403) otherwise (EML-024, AUT-033; EML-055)."""
    access = locks.correspondence_of(request, project)
    require_case_work(access.may_write)
    return access


#: The two ways to show the correspondence (EML-036); the choice is remembered for the session.
MAIL_VIEWS = ("list", "conversation")
#: Characters of a mail shown in the conversation; the whole mail is one click away.
CONVERSATION_TEXT_LIMIT = 4000


@dataclass
class ConversationEntry:
    """A mail as a message of the conversation (EML-036): what is new in it, and the rest folded away."""

    mail: ProjectMail
    text: str
    rest: str
    attachments: list[MailAttachment]

    @property
    def is_outgoing(self) -> bool:
        """Sent from Rentalars: shown on the right."""
        return self.mail.direction == Direction.OUTGOING


def conversation_entry(mail: ProjectMail) -> ConversationEntry:
    """Prepare a mail for the conversation: plain text, earlier mails and signature folded away (EML-036)."""
    text = mail.text_body.strip() or html_to_text(mail.html_body)
    new, rest = split_quoted(text)
    if len(new) > CONVERSATION_TEXT_LIMIT:
        new = new[:CONVERSATION_TEXT_LIMIT].rstrip() + " …"
    return ConversationEntry(
        mail=mail,
        text=new,
        rest=rest[:CONVERSATION_TEXT_LIMIT],
        attachments=[attachment for attachment in mail.attachments.all() if not attachment.is_inline],
    )


@case_work_required()  # AUT-033: also whoever works on the service case (PRJ-108)
def project_mails(request: HttpRequest, pk: int) -> HttpResponse:
    """The correspondence of a project: a list, newest first, or a conversation, oldest first (EML-019, EML-036).

    A whole project shows the mails of its parts as well – those the user
    may read – each marked with the number of its part (PRJ-044, PRJ-049).
    """
    project = _project(request, pk)
    access = locks.correspondence_of(request, project)
    view = request.GET.get("view", "")
    if view in MAIL_VIEWS:
        request.session["mail_view"] = view
    else:
        view = request.session.get("mail_view", "list")
        view = view if view in MAIL_VIEWS else "list"
    mails = project.mails.all()
    if project.parent_id is None and project.has_subprojects and access.basis:
        # EML-055: the parts as before – for the crew of the whole project only its own messages.
        parts = readable_projects(request_rights(request), request.user, Project.objects.filter(parent_id=project.pk))
        mails = ProjectMail.objects.filter(Q(project=project) | Q(project__in=parts.values("pk")))
    mails = access.readable(mails).prefetch_related("attachments").select_related("sent_by", "project")
    context: dict[str, Any] = {
        "project": project,
        "tab": "mails",
        "view": view,
        "can_write": access.may_write and mailboxes.can_send_from(project),
        # EML-051: notes need no mailbox – only the right to write correspondence.
        "can_note": access.may_write,
        # EML-055: the state of each message is shown; who may set the lock changes it here.
        "can_lock": access.may_lock,
        "reads_all": access.reads_all,
        "here": request.get_full_path(),
    }
    if view == "conversation":
        context["entries"] = [conversation_entry(mail) for mail in mails.order_by("date", "id")]
        context["has_mails"] = bool(context["entries"])
    else:
        context["mails"] = mails
        context["has_mails"] = mails.exists()
    return render(request, "mail/project_mails.html", context)


@case_work_required()  # AUT-033: also whoever works on the service case (PRJ-108)
def mail_detail(request: HttpRequest, pk: int, mail_pk: int) -> HttpResponse:
    """One mail: headers, text, attachments; answer, take over attachments, assign elsewhere.

    EML-051: a note shows its text, who wrote it and when – and, for
    who may change it, the form to change it (:func:`note_edit`).
    """
    project = _project(request, pk)
    mail = _mail(request, project, mail_pk)
    if mail.is_note:
        return _note_page(request, project, mail)
    access = locks.correspondence_of(request, project)
    allow_external = request.GET.get("external") == "1"
    blocked = 0
    if mail.html_body:
        _html, blocked = clean_html(mail.html_body, allow_external=False, cid_url=lambda _cid: None)
    reply_to, _reply_cc = reply_recipients(mail, everyone=False)
    all_to, all_cc = reply_recipients(mail, everyone=True)
    return render(
        request,
        "mail/mail_detail.html",
        {
            "project": project,
            "tab": "mails",
            "mail": mail,
            "attachments": [attachment for attachment in mail.attachments.all() if not attachment.is_inline],
            "blocked_images": blocked,
            "allow_external": allow_external,
            # EML-036: a one-liner gets a small frame, not half the screen.
            "frame_size": frame_size(mail.html_body, mail.text_body) if mail.html_body else "",
            # EML-037: "answer all" only where it reaches more people than "answer".
            "can_answer_all": (all_to, all_cc) != (reply_to, ""),
            "can_write": access.may_write and mailboxes.can_send_from(project),
            "can_edit": project.access >= ProjectAccess.EDIT and not project.is_locked,
            "can_lock": access.may_lock,  # EML-055
            "to_files_form": AttachmentToFilesForm(),
            "assign_form": AssignForm(),
            # PRJ-106: the suppliers of the project's subrentals the mail can belong to.
            "supplier_choices": suppliers_of(project),
        },
    )


@xframe_options_sameorigin
@case_work_required()  # AUT-033: also whoever works on the service case (PRJ-108)
def mail_body(request: HttpRequest, pk: int, mail_pk: int) -> HttpResponse:
    """The cleaned HTML of a mail, for the sandboxed frame of the mail page (EML-027)."""
    project = _project(request, pk)
    mail = _mail(request, project, mail_pk)
    allow_external = request.GET.get("external") == "1"
    inline = {attachment.content_id: attachment.pk for attachment in mail.attachments.all() if attachment.content_id}

    def cid_url(content_id: str) -> str | None:
        attachment_pk = inline.get(content_id)
        if attachment_pk is None:
            return None
        return reverse("mail:attachment", args=[project.pk, mail.pk, attachment_pk])

    body, _blocked = clean_html(mail.html_body, allow_external=allow_external, cid_url=cid_url)
    response = HttpResponse(frame_document(body))
    response["Content-Security-Policy"] = content_security_policy(allow_external=allow_external)
    response["Referrer-Policy"] = "no-referrer"
    return response


@case_work_required()  # AUT-033: also whoever works on the service case (PRJ-108)
def attachment(request: HttpRequest, pk: int, mail_pk: int, attachment_pk: int) -> HttpResponse:
    """An attachment, after the rights were checked (EML-020, NFA-007); it follows its message (EML-055)."""
    project = _project(request, pk)
    mail = _mail(request, project, mail_pk)
    stored = get_object_or_404(MailAttachment, pk=attachment_pk, mail=mail)
    return document_response(stored.file.name, stored.filename)


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def attachment_to_files(request: HttpRequest, pk: int, mail_pk: int, attachment_pk: int) -> HttpResponse:
    """Take an attachment over into the files of the project, with a document type (EML-021)."""
    project = _project(request, pk, ProjectAccess.EDIT)
    mail = _mail(request, project, mail_pk)  # EML-055: the attachment follows its message
    stored = get_object_or_404(MailAttachment, pk=attachment_pk, mail=mail)
    form = AttachmentToFilesForm(request.POST)
    document_type = form.cleaned_data["document_type"] if form.is_valid() else None
    try:
        add_file_from_attachment(stored, user=request.user, document_type=document_type)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, _("“%(name)s” is now among the files of the project.") % {"name": stored.filename})
    return redirect("mail:detail", pk=pk, mail_pk=mail_pk)


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def reassign(request: HttpRequest, pk: int, mail_pk: int) -> HttpResponse:
    """Move a mail to another project (EML-015)."""
    project = _project(request, pk, ProjectAccess.EDIT)
    mail = _mail(request, project, mail_pk)
    form = AssignForm(request.POST)
    target = (
        project_by_number(form.cleaned_data["project_number"])  # ADM-012, ADM-014: also a former number
        if form.is_valid()
        else None
    )
    rights = request_rights(request)
    if target is None or access_level(rights, request.user, target) < ProjectAccess.EDIT:
        messages.error(request, _("There is no project with this number that you may edit."))
        return redirect("mail:detail", pk=pk, mail_pk=mail_pk)
    services.reassign(mail, target, user=request.user)
    messages.success(request, _("The mail now belongs to %(project)s.") % {"project": target})
    return redirect("mail:detail", pk=target.pk, mail_pk=mail.pk)


# --- EML-051: notes in the correspondence --------------------------------------------------------


def _may_change_note(request: HttpRequest, project: Project, note: ProjectMail) -> bool:
    """Its writer, or who may edit the project – both with the right to write correspondence.

    AUT-033 (PRJ-108): in a service case also whoever works on it.
    """
    works = bool(getattr(project, "may_work_on_case", False))
    return locks.correspondence_of(request, project).may_write and notes.may_change(
        note, request.user, may_edit_project=project.access >= ProjectAccess.EDIT or works
    )


def _now_initial() -> Any:
    return timezone.localtime().replace(second=0, microsecond=0)


def _note_page(request: HttpRequest, project: Project, note: ProjectMail, form: Any = None) -> HttpResponse:
    may_change = _may_change_note(request, project, note)
    if form is None and may_change:
        form = NoteForm(
            initial={"date": timezone.localtime(note.date), "subject": note.subject, "text": note.text_body}
        )
    return render(
        request,
        "mail/note.html",
        {
            "project": project,
            "tab": "mails",
            "note": note,
            "form": form if may_change else None,
            "can_lock": locks.correspondence_of(request, project).may_lock,  # EML-055
        },
    )


@case_work_required()  # AUT-033: also whoever works on the service case (PRJ-108)
def note_create(request: HttpRequest, pk: int) -> HttpResponse:
    """Write a note into the correspondence – a phone call, a talk – with the time it happened (EML-051)."""
    project = _project(request, pk)
    access = _write(request, project)
    # EML-055: the lock starts with the default of the project or case.
    initial = {"date": _now_initial(), "locked": locks.default_lock(project)}
    form = NoteForm(request.POST or None, initial=initial, can_lock=access.may_lock)
    if request.method == "POST" and form.is_valid():
        try:
            notes.add_note(
                project,
                text=form.cleaned_data["text"],
                subject=form.cleaned_data["subject"],
                date=form.cleaned_data["date"],
                user=request.user,
                # EML-055: the choice of who may set the lock; else open.
                locked=access.new_lock(form.cleaned_data.get("locked", False) if access.may_lock else None, project),
            )
        except ValidationError as error:
            add_validation_error(form, error)
        else:
            messages.success(request, _("The note is in the correspondence."))
            return redirect("mail:project_mails", pk=project.pk)
    return render(
        request, "mail/note_form.html", {"project": project, "tab": "mails", "form": form, "can_lock": access.may_lock}
    )


@require_POST
@case_work_required()  # AUT-033: also whoever works on the service case (PRJ-108)
def note_edit(request: HttpRequest, pk: int, mail_pk: int) -> HttpResponse:
    """Change text, time or subject of a note (EML-051): its writer, or who may edit the project."""
    project = _project(request, pk)
    note = _mail(request, project, mail_pk, direction=Direction.NOTE)
    if not _may_change_note(request, project, note):
        raise PermissionDenied
    form = NoteForm(request.POST)
    if form.is_valid():
        try:
            notes.update_note(
                note,
                text=form.cleaned_data["text"],
                subject=form.cleaned_data["subject"],
                date=form.cleaned_data["date"],
            )
        except ValidationError as error:
            add_validation_error(form, error)
        else:
            messages.success(request, _("Note saved."))
            return redirect("mail:project_mails", pk=project.pk)
    return _note_page(request, project, note, form)


@case_work_required()  # AUT-033: also whoever works on the service case (PRJ-108)
def compose(request: HttpRequest, pk: int) -> HttpResponse:
    """Write a new mail from the project, or answer one – to the sender or to all (EML-024, EML-037).

    EML-043: next to "To", one button adds the crew of the project and one the
    customer, without reloading the page.

    EML-052: the sender is chosen among the addresses the writer may
    use – by default the project's (EML-047), for an answer the address the
    mail came in through, if the writer may use it. EML-026: the preview of
    the signature follows the address chosen.
    """
    project = _project(request, pk)
    rights = request_rights(request)
    access = _write(request, project)
    mail_settings = MailSettings.load()
    answer_to = None
    if request.GET.get("answer", "").isdigit():
        answer_to = _mail(request, project, int(request.GET["answer"]))
        if answer_to.is_note:
            answer_to = None  # EML-051: a note is answered by nobody – a new mail it is
    answer_all = answer_to is not None and request.GET.get("all") == "1"
    options = senders.allowed_senders(project, request.user)
    default = senders.default_choice(options, answer_to)
    sender_address = default.address if default is not None else ""
    supplier = supplier_from(request.GET.get("supplier", ""), answer_to)  # PRJ-106
    initial: dict[str, Any] = {}
    if answer_to is not None:
        to, cc = reply_recipients(answer_to, everyone=answer_all, own_address=sender_address)
        initial = {
            "to": to,
            "cc": cc,
            "subject": reply_subject(answer_to.subject),
            "body": quoted(answer_to),
        }
    elif supplier is not None:
        # PRJ-106: written from the page "Zumietung bei …" – to the supplier, about the subrental.
        to = format_address(supplier.contact, supplier.email) if supplier.email else ""
        initial = {"to": to, "subject": _("Subrental for %(project)s") % {"project": project.name}}
    elif project.contact_id and project.contact.email:
        initial = {"to": format_address(project.contact.name, project.contact.email), "subject": project.name}
    choices = document_choices(request_rights(request), project, request.user)
    wanted = request.GET.get("document", "")
    if wanted.isdigit() and f"doc:{wanted}" in dict(choices):
        # DOK-008: "send" on a document opens the mail with it attached.
        stored = project.documents.get(pk=int(wanted))
        initial["documents"] = [f"doc:{wanted}"] + ([f"xml:{wanted}"] if free_mail.xml_preselected(stored) else [])
        initial["subject"] = f"{stored.title} {stored.number} – {project.name}"
    initial["sender"] = sender_address
    # KND-004: a mail to a contact person starts with the greeting set for that contact.
    opening = salutation.opening_line(
        project, initial.get("to", ""), text_answered=(answer_to.text_body or "") if answer_to is not None else ""
    )
    if opening:
        initial["body"] = opening + (initial.get("body") or "\n\n")
    # EML-055: the default of the project or case – an answer to a message with lock starts with the lock,
    # as it quotes that message; who may set the lock can still take it off.
    initial["locked"] = locks.answer_lock(answer_to, project)
    # EML-026: the signature box where any address chosen has a signature – its own mailbox's or the common one.
    common = mail_settings.signature_html
    has_signature = bool(common) or any(signature_source(option.owner, common=common) for option in options)
    form = ComposeForm(
        request.POST or None,
        initial=initial,
        file_choices=[(str(item.pk), item.label) for item in project.files.all()],
        document_choices=choices,
        has_signature=has_signature,
        sender_choices=[(option.address, option.label) for option in options],
        signature_url=reverse("mail:compose_signature", args=[project.pk]),
        can_lock=access.may_lock,  # EML-055: "With lock", ticked at first
    )
    if request.method == "POST" and form.is_valid():
        chosen = senders.pick(options, form.cleaned_data.get("sender", "")) or default
        try:
            mail = send_project_mail(
                project,
                to=form.cleaned_data["to"],
                cc=form.cleaned_data["cc"],
                bcc=form.cleaned_data["bcc"],
                with_signature=bool(form.cleaned_data.get("signature")),
                subject=form.cleaned_data["subject"],
                body=form.cleaned_data["body"],
                attachments=chosen_attachments(
                    project,
                    rights=rights,
                    file_ids=form.cleaned_data.get("files", []),
                    documents=form.cleaned_data.get("documents", []),
                    uploads=request.FILES.getlist("uploads"),
                    user=request.user,
                ),
                answer_to=answer_to,
                user=request.user,
                supplier=supplier,
                sender=chosen,  # EML-052
                locked=access.new_lock(form.cleaned_data.get("locked", False) if access.may_lock else None, project),
            )
        except ValidationError as error:
            # ComposeForm is a plain form – no ``_update_errors``; the helper works for both kinds.
            add_validation_error(form, error)
        else:
            note_documents_sent(project, form.cleaned_data.get("documents", []), form.cleaned_data["to"])
            messages.success(request, _("The mail was sent and is stored with the project."))
            if supplier is not None and request.GET.get("supplier"):
                # PRJ-106: back to the page of the subrental it was written from.
                return redirect(reverse("projects:subrental", args=[project.pk, supplier.pk]) + "#mails")
            return redirect("mail:detail", pk=pk, mail_pk=mail.pk)
    return render(
        request,
        "mail/compose.html",
        {
            "project": project,
            "tab": "mails",
            "form": form,
            "answer_to": answer_to,
            "answer_all": answer_all,
            "settings": mail_settings,
            # EML-038: who the recipients see as sender; EML-052: the address is chosen below when there are several.
            "sender": sender_label(request.user, sender_address, mail_settings.sender_name),
            "sender_name": sender_name(request.user, mail_settings.sender_name),
            "has_signature": has_signature,
            # EML-026: the preview shows the signature of the default address's mailbox.
            "signature_mailbox": default.owner if default is not None else None,
            "supplier": supplier,  # PRJ-106
            "can_lock": access.may_lock,  # EML-055: without the right the page says the mail is open
            # EML-043: the addresses behind "add crew" and "add customer".
            **_quick_recipients(project, rights=rights, user=request.user),
        },
    )


def _quick_recipients(project: Project, *, rights: Any, user: Any) -> dict[str, Any]:
    """The addresses of the buttons "add crew" and "add customer", as lists and as JSON for the page (EML-043)."""
    crew = crew_recipients(project, rights=rights, user=user)
    customer = customer_recipient(project)
    return {
        "crew_recipients": crew,
        "crew_recipients_json": json.dumps(crew, ensure_ascii=False),
        "customer_recipient": customer,
        "customer_recipient_json": json.dumps([customer] if customer else [], ensure_ascii=False),
    }


@require_GET
@case_work_required()  # AUT-033: also whoever works on the service case (PRJ-108)
def compose_signature(request: HttpRequest, pk: int) -> HttpResponse:
    """The frame with the preview of the signature for the sender chosen while writing (EML-026, EML-052; htmx).

    Only an address the writer may use counts; another one shows the
    default's signature.
    """
    project = _project(request, pk)
    _write(request, project)
    options = senders.allowed_senders(project, request.user)
    chosen = senders.pick(options, request.GET.get("sender", "")) or senders.default_choice(options)
    return render(request, "mail/_signature_frame.html", {"signature_mailbox": chosen.owner if chosen else None})


@require_GET
def address_suggestions(request: HttpRequest) -> JsonResponse:
    """Addresses for the recipient fields while typing, within the rights of the user (EML-037)."""
    rights = request_rights(request)
    services.require_mail_write(rights)
    found = suggest_addresses(rights, request.GET.get("q", ""))
    return JsonResponse([suggestion.as_json() for suggestion in found], safe=False)


@require_POST
@case_work_required()  # AUT-033: notes – also whoever works on the service case (PRJ-108)
def mail_delete(request: HttpRequest, pk: int, mail_pk: int) -> HttpResponse:
    """Remove a mail from Rentalars (the mailbox is not touched) – or a note (EML-051), also by its writer."""
    project = _project(request, pk)
    mail = _mail(request, project, mail_pk)
    if mail.is_note:
        if not _may_change_note(request, project, mail):
            raise PermissionDenied
        services.delete_mail(mail)
        messages.success(request, _("The note was removed from the correspondence."))
        return redirect("mail:project_mails", pk=pk)
    # A mail: the right to delete in projects and to edit this one.
    if project.access < ProjectAccess.EDIT or not request_rights(request).can_delete(Module.PROJECTS):
        raise PermissionDenied
    services.require_mail_write(request_rights(request))
    services.delete_mail(mail)
    messages.success(request, _("The mail was removed from the project."))
    return redirect("mail:project_mails", pk=pk)


@require_POST
@case_work_required()  # AUT-033: also whoever works on the service case (PRJ-108)
def mail_lock(request: HttpRequest, pk: int, mail_pk: int) -> HttpResponse:
    """Put the lock on a message or take it away (EML-055): who may write and sees prices.

    ``locked`` is ``1`` or ``0``; ``next`` leads back to the page the button was on (the list, the conversation,
    the mail), else to the message.
    """
    project = _project(request, pk)
    mail = _mail(request, project, mail_pk)
    require_case_work(locks.correspondence_of(request, project).may_lock)
    wanted = request.POST.get("locked") == "1"
    if locks.set_lock(mail, wanted, user=request.user):
        if wanted:
            messages.success(request, _("The message has a lock now. Only those who may see prices read it."))
        else:
            messages.success(request, _("The lock is off. The crew of the project reads the message now as well."))
    next_url = request.POST.get("next", "")
    # EML-055: only a page of ours – "/\evil.example" or "https://evil.example" lead to the message.
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(next_url)
    return redirect("mail:detail", pk=project.pk, mail_pk=mail.pk)


# --- Projects → Inquiries (EML-014, EML-041, EML-042) -------------------------------------------------


@module_required(Module.EMAIL)
def unknown_list(request: HttpRequest) -> HttpResponse:
    """The tab "Inquiries" under Projects: mails that wait in an inbox to be taken over (EML-014, EML-042).

    Mails whose tag names no project, and – from mailboxes that take them in
    – mails without any tag (EML-041). They stay unchanged in the inbox until
    somebody takes them over or removes them from the list. The state of the
    fetch is shown in the settings, not here (EML-042).

    PRJ-107: a table with columns to choose, sorting and CSV; the
    project number is typed with suggestions; an inquiry becomes a project or
    a service case; a small trash-can button takes a mail off the list, and
    tick boxes take several off at once.

    EML-053: "Anfrage anlegen" notes an inquiry by hand; such an entry
    shows the badge „Notiert“, the caller's phone and address, and – for who
    noted it or may write in "E-mail" – "Edit".
    """
    rights = request_rights(request)
    correspondence = Mailbox.objects.filter(for_correspondence=True)
    filters = {
        "q": request.GET.get("q", "").strip(),
        "kind": request.GET.get("kind", ""),
        "mailbox": request.GET.get("mailbox", ""),
    }
    waiting = UnknownTagMail.objects.filter(resolved_at__isnull=True).select_related(
        "mailbox", "defect_report", "customer"
    )
    if filters["q"]:
        text = filters["q"]
        waiting = waiting.filter(
            Q(subject__icontains=text)
            | Q(sender__icontains=text)
            | Q(tag__icontains=text)
            # EML-053: what was noted by hand.
            | Q(phone__icontains=text)
            | Q(note__icontains=text)
            | Q(customer__name__icontains=text)
        )
    if filters["kind"] == "inquiry":
        waiting = waiting.filter(tag="", defect_report=None, source=InquirySource.TAKEN_IN)
    elif filters["kind"] == "unknown_tag":
        waiting = waiting.exclude(tag="")
    elif filters["kind"] == "defect":
        # MAT-057: defect reports an automation put here.
        waiting = waiting.filter(defect_report__isnull=False)
    elif filters["kind"] == "manual":
        waiting = waiting.filter(source=InquirySource.MANUAL)  # EML-053
    if filters["mailbox"].isdigit():
        waiting = waiting.filter(mailbox_id=int(filters["mailbox"]))
    table = INQUIRY_TABLE.state(request)
    waiting = table.order(waiting)
    if table.wants_csv:
        return table.csv_response(waiting, _("Inquiries"))
    page = paginate(request, waiting)
    items = list(page.object_list)
    for item in items:
        item.can_change = inquiries.may_change(item, request.user, rights)  # EML-053
    rows = table.rows(page)  # UIX-040: the page, so that each group counts its rows in the whole list
    can_assign = rights.can_write(Module.EMAIL)
    return render(
        request,
        "mail/unknown_list.html",
        {
            "tab": "inquiries",
            "page": page,
            "table": table,
            "entries": list(zip(rows, items, strict=True)),
            # UIX-040: a group heading spans the tick box and the actions as well.
            "group_span": len(table.columns) + (2 if can_assign else 0),
            "filters": filters,
            "filtered": any(filters.values()),
            "mailbox_choices": list(correspondence.values_list("pk", "name")) if correspondence.count() > 1 else [],
            "takes_untagged": any(takes_untagged(mailbox) for mailbox in correspondence.filter(is_active=True)),
            "can_assign": can_assign,
            "assign_form": AssignForm(),
            "tag_prefix": current_prefix(),
        },
    )


@require_GET
@module_required(Module.EMAIL)
def project_suggestions(request: HttpRequest) -> JsonResponse:
    """Projects for the field "Project number" while typing: number and name, those the user may see (PRJ-107).

    The answer is that of every type-ahead field: ``id`` is the project
    number, which the field sends; a former number finds the project too
    (ADM-012, ADM-014).
    """
    from rentalars.projects import numbers as project_numbers
    from rentalars.projects.access import visible_projects

    text = request.GET.get("q", "").strip()
    if not text:
        return JsonResponse([], safe=False)
    found = (
        visible_projects(request_rights(request), request.user)
        .filter(project_numbers.matching(text) | Q(name__icontains=text))
        .select_related("customer")
        .order_by("-start", "-pk")[:12]
    )
    return JsonResponse(
        [
            {
                "id": project.number,
                "label": f"{project.number} {project.name}",
                "hint": project.customer.name if project.customer_id else "",
            }
            for project in found
        ],
        safe=False,
    )


@require_POST
@module_required(Module.EMAIL, Level.WRITE)
def unknown_assign(request: HttpRequest, pk: int) -> HttpResponse:
    """Take a waiting mail – unknown tag or inquiry – into a project by hand (EML-014, EML-042)."""
    unknown = get_object_or_404(UnknownTagMail, pk=pk, resolved_at__isnull=True)
    # PRJ-107: the number comes from the suggestion chosen, else from what was typed ("2026-0042" or
    # "2026-0042 Stadtfest" – the first word); without scripts only the typed text arrives.
    typed = request.POST.get("project_text", "").split()
    number = request.POST.get("project_number", "").strip() or (typed[0] if typed else "")
    form = AssignForm({"project_number": number})
    project = (
        project_by_number(form.cleaned_data["project_number"])  # ADM-012, ADM-014: also a former number
        if form.is_valid()
        else None
    )
    if project is None or access_level(request_rights(request), request.user, project) < ProjectAccess.READ:
        messages.error(request, _("There is no project with this number that you may see."))
        return redirect("mail:unknown_list")
    try:
        mail = assign_unknown(unknown, project)
    except MailboxError as error:
        messages.error(request, str(error))
        return redirect("mail:unknown_list")
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))  # EML-053: an inquiry noted by hand, dealt with already
        return redirect("mail:unknown_list")
    if unknown.is_manual:
        # EML-053: no mail – the inquiry is a note in the correspondence now.
        messages.success(
            request, _("The inquiry is now a note in the correspondence of %(project)s.") % {"project": project}
        )
    else:
        messages.success(request, _("The mail was taken over into %(project)s.") % {"project": project})
    # EML-055: a mail taken over has the lock – its page only for who reads it.
    if services.may_read_all_mail(request_rights(request)):
        return redirect("mail:detail", pk=project.pk, mail_pk=mail.pk)
    return redirect("mail:unknown_list")


@require_POST
@module_required(Module.EMAIL, Level.WRITE)
def unknown_dismiss(request: HttpRequest, pk: int) -> HttpResponse:
    """Take a mail off the list; it stays in the inbox, as it was."""
    unknown = get_object_or_404(UnknownTagMail, pk=pk, resolved_at__isnull=True)
    unknown.resolved_at = timezone.now()
    unknown.save(update_fields=["resolved_at"])
    if unknown.is_manual:
        messages.success(request, _("The inquiry is off the list."))  # EML-053: there is no inbox
    else:
        messages.success(request, _("The mail is off the list. It is still in the inbox."))
    return _back(request, "mail:unknown_list")


# --- EML-053: inquiries noted by hand ------------------------------------------------------------


def _inquiry_values(form: InquiryForm) -> dict[str, Any]:
    return {name: form.cleaned_data.get(name) for name in inquiries.MANUAL_FIELDS}


@module_required(Module.EMAIL, Level.WRITE)
def inquiry_create(request: HttpRequest) -> HttpResponse:
    """Note an inquiry by hand – e.g. a phone call – for the office (EML-053).

    Needs write access to the module "E-mail", as taking inquiries over does.
    """
    form = InquiryForm(request.POST or None, initial={"date": _now_initial()})
    if request.method == "POST" and form.is_valid():
        try:
            inquiries.create_manual(user=request.user, **_inquiry_values(form))
        except ValidationError as error:
            add_validation_error(form, error)
        else:
            messages.success(request, _("The inquiry was noted. It waits here until somebody takes it over."))
            return redirect("mail:unknown_list")
    return render(request, "mail/inquiry_form.html", {"tab": "inquiries", "form": form, "inquiry": None})


def _manual_inquiry(request: HttpRequest, inquiry_pk: int) -> UnknownTagMail:
    """A waiting inquiry noted by hand that the user may change: who noted it, or who may write in "E-mail"."""
    inquiry = get_object_or_404(
        UnknownTagMail.objects.select_related("customer", "created_by"),
        pk=inquiry_pk,
        resolved_at__isnull=True,
        source=InquirySource.MANUAL,
    )
    if not inquiries.may_change(inquiry, request.user, request_rights(request)):
        raise PermissionDenied
    return inquiry


@module_required(Module.EMAIL)
def inquiry_edit(request: HttpRequest, inquiry_pk: int) -> HttpResponse:
    """Change an inquiry noted by hand (EML-053).

    ``inquiry_pk``, not ``pk``: below the mail module ``pk`` names a project (``core.changes``).
    """
    inquiry = _manual_inquiry(request, inquiry_pk)
    initial = {
        "date": timezone.localtime(inquiry.date) if inquiry.date else None,
        "contact_name": inquiry.contact_name,
        "phone": inquiry.phone,
        "contact_email": inquiry.contact_email,
        "customer": inquiry.customer_id,
        "subject": inquiry.subject,
        "note": inquiry.note,
    }
    form = InquiryForm(request.POST or None, initial=initial, current_customer=inquiry.customer)
    if request.method == "POST" and form.is_valid():
        try:
            inquiries.update_manual(inquiry, **_inquiry_values(form))
        except ValidationError as error:
            add_validation_error(form, error)
        else:
            messages.success(request, _("The inquiry was saved."))
            return redirect("mail:unknown_list")
    return render(request, "mail/inquiry_form.html", {"tab": "inquiries", "form": form, "inquiry": inquiry})


@require_POST
@module_required(Module.EMAIL)
def inquiry_delete(request: HttpRequest, inquiry_pk: int) -> HttpResponse:
    """Delete an inquiry noted by hand – who noted it, or who may write in "E-mail" (EML-053)."""
    inquiry = _manual_inquiry(request, inquiry_pk)
    inquiries.delete_manual(inquiry)
    messages.success(request, _("The inquiry was deleted."))
    return redirect("mail:unknown_list")


@require_POST
@module_required(Module.EMAIL, Level.WRITE)
def unknown_dismiss_many(request: HttpRequest) -> HttpResponse:
    """Take the ticked mails off the list at once; they stay in their inboxes (PRJ-107)."""
    chosen = [int(value) for value in request.POST.getlist("items") if value.isdigit()]
    count = dismiss_waiting(chosen)
    if count:
        messages.success(
            request,
            ngettext(
                "%(count)d mail is off the list. It is still in the inbox.",
                "%(count)d mails are off the list. They are still in the inbox.",
                count,
            )
            % {"count": count},
        )
    else:
        messages.info(request, _("Tick the mails to take off the list first."))
    return _back(request, "mail:unknown_list")


@require_POST
@module_required(Module.EMAIL)
def fetch_now(request: HttpRequest) -> HttpResponse:
    """Fetch every mailbox of the correspondence at once (EML-005, EML-041)."""
    result = fetch_mail(force=True)
    if result.skipped:
        messages.info(request, result.skipped)
    elif result.error:
        messages.error(request, _("Fetching failed: %(error)s") % {"error": result.error})
    else:
        counts = {
            "new": result.looked_at,
            "assigned": len(result.imported),
            "unknown": len(result.unknown),
            "inquiries": len(result.inquiries),
        }
        if result.inquiries:
            text = ngettext(
                "Looked at %(new)d new mail; %(assigned)d assigned, %(unknown)d with unknown tag, "
                "%(inquiries)d inquiries.",
                "Looked at %(new)d new mails; %(assigned)d assigned, %(unknown)d with unknown tag, "
                "%(inquiries)d inquiries.",
                counts["new"],
            )
        else:
            text = ngettext(
                "Looked at %(new)d new mail; %(assigned)d assigned, %(unknown)d with unknown tag.",
                "Looked at %(new)d new mails; %(assigned)d assigned, %(unknown)d with unknown tag.",
                counts["new"],
            )
        messages.success(request, text % counts)
        if result.crew_answers:
            # PER-032: answers to deployment requests by reply mail.
            messages.success(
                request,
                ngettext(
                    "%(count)d answer to a deployment request by mail.",
                    "%(count)d answers to deployment requests by mail.",
                    result.crew_answers,
                )
                % {"count": result.crew_answers},
            )
    return _back(request, "mail:unknown_list")


def _back(request: HttpRequest, default: str) -> HttpResponse:
    """Back to the page in ``next`` – only an address of this site – or to a default page."""
    return redirect(safe_next_url(request) or default)


# --- The settings: mailboxes, rules, signature (EML-041, EML-002, EML-034, EML-035) ----------------------


def mailbox_settings(request: HttpRequest) -> HttpResponse:
    """The mailboxes with roles and state, the rules for all of them and the signature (EML-041, EML-034).

    Passwords are never shown. Mailboxes and rules are changed with write
    access to the module "E-mail", the signature with write access to the
    administration; the page opens for either.
    """
    rights = request_rights(request)
    if not services.may_open_mail_settings(rights):
        raise PermissionDenied
    can_edit_mailbox = rights.can_write(Module.EMAIL)
    if request.method == "POST" and not can_edit_mailbox:
        raise PermissionDenied
    current = MailSettings.load()
    form = MailRulesForm(request.POST or None, instance=current)
    if request.method == "POST" and form.is_valid():
        services.save_settings(form.save(commit=False))
        messages.success(request, _("The rules for all mailboxes were saved."))
        return redirect("mail:settings")
    boxes = list(Mailbox.objects.prefetch_related("aliases"))  # EML-047: with their further addresses
    return render(
        request,
        "mail/settings.html",
        {
            "form": form,
            "settings": current,
            "mailboxes": boxes,
            # secret_key was changed: the stored passwords have to be entered again.
            "unreadable": [box for box in boxes if not box.password_readable],
            "system_mailbox": next((box for box in boxes if box.for_system and box.can_send), None),
            # EML-048: without a mail server system mails are not sent.
            "has_mail_server": mailboxes.has_mail_server(),
            "can_fetch": any(box.for_correspondence and box.can_fetch for box in boxes),
            "can_edit_mailbox": can_edit_mailbox,
            "can_delete_mailbox": rights.can_delete(Module.EMAIL),
            "can_edit_signature": services.may_edit_signature(rights),
            "has_signature": bool(current.signature_html),
            # EML-026: the mailboxes of the correspondence, each with its own signature or the common one.
            "signature_mailboxes": [box for box in boxes if box.for_correspondence],
            # PER-032: the mailbox the answers to deployment requests go to by mail, if one can take them.
            "crew_answer_mailbox": crew_answers.answer_mailbox(),
        },
    )


@module_required(Module.EMAIL, Level.WRITE)
def mailbox_edit(request: HttpRequest, mailbox_pk: int | None = None) -> HttpResponse:
    """Add or change a mailbox with its roles (EML-041). Passwords are only written, never shown (EML-002).

    The first mailbox is offered for the correspondence and for sending it.
    """
    if mailbox_pk is None:
        first = not Mailbox.objects.exists()
        mailbox = Mailbox(for_correspondence=first, is_outgoing=first)
    else:
        mailbox = get_object_or_404(Mailbox, pk=mailbox_pk)
    form = MailboxForm(request.POST or None, instance=mailbox)
    if request.method == "POST" and form.is_valid():
        try:
            notes = mailboxes.save_mailbox(
                form.save(commit=False),
                imap_password=form.cleaned_data["imap_password"],
                smtp_password=form.cleaned_data["smtp_password"],
            )
        except ValidationError as error:
            add_validation_error(form, error)
        else:
            form.save_m2m()  # EML-052: the roles that may send from the mailbox's address
            messages.success(request, _("The mailbox “%(name)s” was saved.") % {"name": mailbox})
            for note in notes:
                messages.info(request, note)
            return redirect("mail:settings")
    return render(
        request,
        "mail/mailbox_form.html",
        {
            "form": form,
            "mailbox": mailbox if mailbox.pk else None,
            # EML-047: the further addresses of the mailbox, each with its rule for mails without tag.
            "aliases": (
                list(mailbox.aliases.select_related("case_manager").prefetch_related("sender_roles"))
                if mailbox.pk
                else []
            ),
            "password_readable": mailbox.password_readable,
            "can_delete": request_rights(request).can_delete(Module.EMAIL),
            # EML-026: the signature of the mailbox is written by who may change the common one.
            "can_edit_signature": services.may_edit_signature(request_rights(request)),
        },
    )


@require_http_methods(["GET", "POST"])
@module_required(Module.EMAIL, Level.DELETE)
def mailbox_delete(request: HttpRequest, mailbox_pk: int) -> HttpResponse:
    """Delete a mailbox after a confirmation that says what follows – or only switch it off (EML-046).

    The page names the mails and log entries that keep the name of the
    mailbox, the inquiries that leave the list, the roles no mailbox has
    afterwards, and – if it sends the correspondence while others of the
    correspondence stay active – asks which one sends from now on.
    """
    mailbox = get_object_or_404(Mailbox, pk=mailbox_pk)
    error = ""
    if request.method == "POST":
        try:
            if request.POST.get("action") == "switch_off":
                mailboxes.switch_off_mailbox(mailbox)
                messages.success(request, _("The mailbox “%(name)s” was switched off.") % {"name": mailbox})
                return redirect("mail:settings")
            chosen = request.POST.get("successor", "")
            successor = Mailbox.objects.filter(pk=int(chosen)).first() if chosen.isdigit() else None
            notes = mailboxes.delete_mailbox(mailbox, successor=successor)
        except ValidationError as refused:
            error = " ".join(refused.messages)
            mailbox = get_object_or_404(Mailbox, pk=mailbox_pk)  # as stored: nothing was changed
        else:
            messages.success(request, _("The mailbox “%(name)s” was deleted.") % {"name": mailbox})
            for note in notes:
                messages.info(request, note)
            return redirect("mail:settings")
    return render(
        request,
        "mail/mailbox_delete.html",
        {"mailbox": mailbox, "deletion": mailboxes.deletion_of(mailbox), "error": error},
    )


@require_POST
@module_required(Module.EMAIL, Level.WRITE)
def mailbox_check(request: HttpRequest, mailbox_pk: int) -> HttpResponse:
    """Log in to the servers of a mailbox and tell how it went; nothing is changed or sent (EML-041)."""
    mailbox = get_object_or_404(Mailbox, pk=mailbox_pk)
    for check in mailboxes.check_connection(mailbox):
        text = f"{mailbox} – {check.part}: {check.text}" if check.part else f"{mailbox}: {check.text}"
        (messages.success if check.ok else messages.error)(request, text)
    return _back(request, "mail:settings")


# --- Further addresses of a mailbox (EML-047) ---------------------------------------------------------------


@module_required(Module.EMAIL, Level.WRITE)
def mailbox_address_edit(request: HttpRequest, mailbox_pk: int, address_pk: int | None = None) -> HttpResponse:
    """Add or change a further address (alias) of a mailbox, with its rule for mails without tag (EML-047)."""
    mailbox = get_object_or_404(Mailbox, pk=mailbox_pk)
    alias = (
        get_object_or_404(MailboxAddress, pk=address_pk, mailbox=mailbox)
        if address_pk is not None
        else MailboxAddress(mailbox=mailbox)
    )
    form = MailboxAddressForm(request.POST or None, instance=alias)
    if request.method == "POST" and form.is_valid():
        try:
            notes = save_address(form.save(commit=False))
        except ValidationError as error:
            add_validation_error(form, error)
        else:
            form.save_m2m()  # EML-052: the roles that may send from this address
            messages.success(request, _("The address %(address)s was saved.") % {"address": alias.address})
            for note in notes:
                messages.info(request, note)
            return redirect(reverse("mail:mailbox_edit", args=[mailbox.pk]) + "#addresses")
    return render(request, "mail/address_form.html", {"form": form, "mailbox": mailbox, "alias": alias})


@require_POST
@module_required(Module.EMAIL, Level.WRITE)
def mailbox_address_delete(request: HttpRequest, mailbox_pk: int, address_pk: int) -> HttpResponse:
    """Take an address off the list of a mailbox; its mails then follow the mailbox's own rule (EML-047)."""
    alias = get_object_or_404(MailboxAddress, pk=address_pk, mailbox_id=mailbox_pk)
    delete_address(alias)
    messages.success(request, _("The address %(address)s was removed from the list.") % {"address": alias.address})
    return redirect(reverse("mail:mailbox_edit", args=[mailbox_pk]) + "#addresses")


# --- The signature (EML-034) -------------------------------------------------------------------------


@module_required(Module.ADMINISTRATION, Level.WRITE)
def signature_edit(request: HttpRequest) -> HttpResponse:
    """Write the signature of everybody, with placeholders and a preview (EML-034)."""
    current = MailSettings.load()
    form = SignatureForm(request.POST or None, initial={"html": current.signature_html})
    if request.method == "POST" and form.is_valid():
        current.signature_html = form.cleaned_data["html"]
        current.save(update_fields=["signature_html"])
        messages.success(request, _("The signature was saved. It is added to every mail written in Rentalars."))
        return redirect("mail:settings")
    return render(request, "mail/signature.html", {"form": form, "placeholders": shown_placeholders()})


@module_required(Module.ADMINISTRATION, Level.WRITE)
def mailbox_signature_edit(request: HttpRequest, mailbox_pk: int) -> HttpResponse:
    """Write the signature of one mailbox – the same editor, placeholders and cleaning as the common one (EML-026).

    Mails sent from the mailbox's addresses carry it; empty, they carry the
    common signature. Changing it needs the right of the common signature.
    """
    mailbox = get_object_or_404(Mailbox, pk=mailbox_pk)
    form = SignatureForm(request.POST or None, initial={"html": mailbox.signature_html})
    if request.method == "POST" and form.is_valid():
        mailbox.signature_html = form.cleaned_data["html"]
        mailbox.save(update_fields=["signature_html"])
        if mailbox.signature_html:
            text = _("The signature of “%(name)s” was saved. Mails sent from its addresses carry it.")
        else:
            text = _("“%(name)s” has no signature of its own any more; its mails carry the common signature.")
        messages.success(request, text % {"name": mailbox.name})
        return redirect(reverse("mail:settings") + "#signature")
    return render(
        request, "mail/signature.html", {"form": form, "placeholders": shown_placeholders(), "mailbox": mailbox}
    )


def _preview_mailbox(request: HttpRequest) -> Mailbox | None:
    """EML-026: the mailbox named by ``mailbox`` in the address or the form, whose signature is shown."""
    value = str(request.GET.get("mailbox", "") or request.POST.get("mailbox", ""))
    return Mailbox.objects.filter(pk=int(value)).first() if value.isdigit() else None


@xframe_options_sameorigin
@require_http_methods(["GET", "POST"])
def signature_preview(request: HttpRequest) -> HttpResponse:
    """The signature with the data of the viewer, for a frame (EML-034).

    ``GET`` shows the stored signature – on the page that writes a mail and on
    the settings. ``POST`` shows a draft from the editor, for who may change it.

    EML-026: with ``mailbox`` the signature of that mailbox – its own,
    else the common one; a draft left empty for a mailbox shows the common one.
    """
    rights = request_rights(request)
    if not services.may_see_signature(rights):
        raise PermissionDenied
    mailbox = _preview_mailbox(request)
    if request.method == "POST":
        if not services.may_edit_signature(rights):
            raise PermissionDenied
        form = SignatureForm(request.POST)
        source = form.cleaned_data["html"] if form.is_valid() else ""
        if mailbox is not None and not source.strip():
            signature = render_signature(request.user)  # empty: the mailbox's mails carry the common one
        else:
            signature = render_signature(request.user, source)
    else:
        signature = render_signature(request.user, mailbox=mailbox)
    body = signature.html
    if request.GET.get("text") == "1" or request.POST.get("text") == "1":
        body += f'<hr><pre style="white-space: pre-wrap; font: 13px/1.4 monospace">{escape(signature.text)}</pre>'
    response = HttpResponse(frame_document(body))
    response["Content-Security-Policy"] = content_security_policy(allow_external=True)
    response["Referrer-Policy"] = "no-referrer"
    return response


# --- The mail log (EML-039) ----------------------------------------------------------------------------


@module_required(Module.ADMINISTRATION)
def mail_log(request: HttpRequest) -> HttpResponse:
    """Every mail that came in or went out, project and system mails, with what became of it (EML-039)."""
    filters = {
        "since": request.GET.get("since", ""),
        "until": request.GET.get("until", ""),
        "direction": request.GET.get("direction", ""),
        "kind": request.GET.get("kind", ""),
        "result": request.GET.get("result", ""),
        "q": request.GET.get("q", "").strip(),
    }
    entries = filtered_entries(
        since=parse_date(filters["since"]) if filters["since"] else None,
        until=parse_date(filters["until"]) if filters["until"] else None,
        direction=filters["direction"],
        kind=filters["kind"],
        result=filters["result"],
        text=filters["q"],
    )
    table = MAIL_LOG_TABLE.state(request)
    entries = table.order(entries)
    if table.wants_csv:
        return table.csv_response(entries, _("Mail log"))
    page = paginate(request, entries)
    return render(
        request,
        "mail/log.html",
        {
            "page": page,
            "table": table,
            "rows": table.rows(page),
            "filters": filters,
            "directions": list(DIRECTION_LABELS.items()),
            "kinds": LogKind.choices,
            "results": LogResult.choices,
            "retention_days": log_retention_days(),
            "has_mail_server": mailboxes.has_mail_server(),  # EML-048
            "not_sent_text": not_sent_text(),
        },
    )
