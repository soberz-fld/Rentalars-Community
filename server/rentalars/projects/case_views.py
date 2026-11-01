# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages of the service cases (PRJ-090): the list, a new case, the page of a case, its status, the conversion.

A service case is a project of its own kind (``projects.service_cases``);
the tabs it shares with a project – documents and files, correspondence,
access, history – are the project's own pages. Its planning page, schedule
and deployment view lead to the page of the case.
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from rentalars.accounts.rights import Level, Module, module_required, request_rights
from rentalars.core.forms import add_validation_error
from rentalars.core.listing import paginate
from rentalars.mail.mailboxes import can_send_from
from rentalars.projects import case_pdf, service_cases
from rentalars.projects.access import ProjectAccess, project_for, visible_projects
from rentalars.projects.case_forms import CaseStatusFollowUpForm, CaseStatusForm, ParticipantForm, ServiceCaseForm
from rentalars.projects.case_list_table import CASE_TABLE, without_contacts
from rentalars.projects.case_work import (
    case_work_required,
    may_change_case,
    may_read_correspondence,
    may_write_correspondence,
)
from rentalars.projects.forms import OpenItemsForm, ProjectForm, default_period
from rentalars.projects.models import CaseStatus, Project, ProjectAccessLevel, ProjectMembership
from rentalars.projects.tables import may_see_customers


def _case_for(
    request: HttpRequest, pk: Any, minimum: ProjectAccess = ProjectAccess.READ, *, case_work: bool = True
) -> Project:
    """A service case the user may open; a project is not one (404).

    AUT-033 (PRJ-108): ``case_work`` – the person responsible and the people taking part may do this in their
    case (``projects.case_work``); ``False`` for what is not part of that work, such as turning it into a project.
    """
    case = project_for(
        request,
        pk,
        minimum,
        queryset=Project.objects.select_related("customer", "contact", "manager"),
        case_work=case_work,
    )
    if not case.is_service_case:
        raise Http404
    return case


def _may_change(request: HttpRequest, case: Project) -> bool:
    """Edit access with the right to write projects – or working on the case (AUT-033, PRJ-108)."""
    return may_change_case(request, case)


def _bulk_context(request: HttpRequest) -> dict[str, Any]:
    """The bar under a list of cases offers follow-up, status and person responsible (``projects.bulk``)."""
    from rentalars.projects import bulk_views

    if not bulk_views.may_change_cases(request):
        return {}
    return {"bulk_may": True, "bulk_fields": bulk_views.empty_bar()}


@module_required(Module.PROJECTS)
def case_list(request: HttpRequest) -> HttpResponse:
    """Projekte → Servicefälle: the cases that still need somebody, or those of a status (PRJ-090).

    Filters: status (default: every case not done – PRJ-112: the backlog too), "mine" (the user is
    responsible) and a text that searches number, subject, customer, who
    reported it and the description.
    """
    rights = request_rights(request)
    statuses = [status for status in request.GET.getlist("status") if status in CaseStatus.values]
    text = request.GET.get("q", "").strip()
    mine = request.GET.get("mine") == "1"
    sees_customers = may_see_customers(rights)
    found = service_cases.case_list(
        visible_projects(rights, request.user),
        statuses=statuses,
        text=text,
        manager=request.user if mine else None,
        with_contacts=sees_customers,  # PRJ-122: the customer's name in every role, the reporter's only here
    )
    # UIX-040: columns to choose, sorting by a heading, groups and CSV.
    table = CASE_TABLE.state(request)
    found = table.order(found)
    if table.wants_csv:
        return table.csv_response(found if sees_customers else without_contacts(found), _("Service cases"))
    page = paginate(request, found)
    if not sees_customers:
        list(without_contacts(page))  # the rows of the page, without contact and reporter
    return render(
        request,
        "projects/cases.html",
        {
            "tab": "cases",
            "page": page,
            "table": table,
            "rows": table.rows(page),
            "statuses": statuses,
            "status_choices": CaseStatus.choices,
            "q": text,
            "mine": mine,
            "show_customers": sees_customers,
            "can_create": rights.can_write(Module.PROJECTS),
            **_bulk_context(request),
        },
    )


@module_required(Module.PROJECTS, Level.WRITE)
def case_create(request: HttpRequest) -> HttpResponse:
    """A new service case – from scratch, or from an inquiry without project tag (``?inquiry=``, PRJ-090).

    From an inquiry the form starts with the subject and with the customer
    and contact the sender's address belongs to; saving takes the mail out
    of its inbox into the case. That needs the right to write e-mail, as
    taking a mail over by hand does (EML-042).

    MAT-057: from a defect report (``?defect=``, on the item's page;
    or an entry under Anfragen an automation made of one) the form starts with
    what the report says – internal, or for the owner of customer material –
    and saving puts the photo of the report into the case.
    """
    from rentalars.mail.imap import MailboxError
    from rentalars.mail.models import UnknownTagMail
    from rentalars.material.models import DefectReport
    from rentalars.projects import defect_cases

    rights = request_rights(request)
    unknown = None
    defect = None
    initial: dict[str, Any] = {"manager": request.user}
    inquiry = request.GET.get("inquiry", "") or request.POST.get("inquiry", "")
    defect_value = request.GET.get("defect", "") or request.POST.get("defect", "")
    if inquiry:
        if not rights.can_write(Module.EMAIL) or not inquiry.isdigit():
            raise Http404
        unknown = get_object_or_404(UnknownTagMail, pk=int(inquiry), resolved_at__isnull=True)
        initial.update(service_cases.suggestions_from_inquiry(unknown))
        defect = unknown.defect_report if unknown.is_defect else None
    elif defect_value:
        if not rights.can_read(Module.MATERIAL) or not defect_value.isdigit():
            raise Http404
        defect = get_object_or_404(DefectReport.objects.select_related("item__material_model"), pk=int(defect_value))
        existing = defect_cases.case_of(defect)
        if existing is not None:
            messages.info(
                request,
                _("The service case %(number)s was made of this defect report already.") % {"number": existing.number},
            )
            return redirect("projects:case_detail", pk=existing.pk)
        initial.update(defect_cases.suggestions(defect))
    if request.GET.get("customer", "").isdigit():
        # The type-ahead asks for the contacts of the customer just chosen (PRJ-070).
        initial["customer"] = int(request.GET["customer"])
    form = ServiceCaseForm(request.POST or None, initial=initial, rights=rights)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                if unknown is not None:
                    case = service_cases.create_from_inquiry(unknown, user=request.user, **form.cleaned_data)
                elif defect is not None:
                    case = defect_cases.create_from_defect(defect, user=request.user, **form.cleaned_data)
                else:
                    case = service_cases.create_case(user=request.user, customer_required=True, **form.cleaned_data)
                if rights.is_limited_to_assigned_projects(Module.PROJECTS):
                    # AUT-016: without a membership the creator could not open the new case.
                    ProjectMembership.objects.get_or_create(
                        project=case, user=request.user, defaults={"level": ProjectAccessLevel.EDIT}
                    )
        except ValidationError as error:
            add_validation_error(form, error)
        except MailboxError as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, _("Service case %(number)s created.") % {"number": case.number})
            if unknown is not None and unknown.is_manual:
                # EML-053: an inquiry noted by hand is a note in the correspondence now.
                messages.success(request, _("The inquiry is a note in the correspondence of the service case now."))
            elif unknown is not None and defect is None:
                messages.success(request, _("The mail is in the service case now."))
            return redirect("projects:case_detail", pk=case.pk)
    return render(
        request,
        "projects/case_form.html",
        {"form": form, "case": None, "unknown": unknown, "defect": defect, "tab": "cases"},
    )


@case_work_required()
def case_detail(request: HttpRequest, pk: Any) -> HttpResponse:
    """The page of a service case: what it is about, its status, open items and the latest mails (PRJ-090).

    AUT-033: the person responsible and the people taking part open it and work on it, its mails included.
    """
    case = _case_for(request, pk)
    rights = request_rights(request)
    may_change = _may_change(request, case)
    reads_mail = may_read_correspondence(request, case)
    # EML-055: the latest messages the user reads – without the price right the open ones.
    from rentalars.mail.locks import correspondence_of

    shown_mails = correspondence_of(request, case).readable(case.mails.all()) if reads_mail else None
    return render(
        request,
        "projects/case_detail.html",
        {
            "project": case,
            "case": case,
            "tab": "case",
            "can_edit": may_change,
            "can_customer_pdf": may_change and reads_mail,  # PRJ-131
            "status_form": CaseStatusForm(initial={"case_status": case.case_status}) if may_change else None,
            "open_items": case.open_items.select_related("done_by"),
            "items_form": OpenItemsForm() if may_change else None,
            "mails": list(shown_mails.order_by("-date", "-pk")[:5]) if shown_mails is not None else None,
            "mail_count": shown_mails.count() if shown_mails is not None else 0,
            "reads_all_mail": correspondence_of(request, case).reads_all,  # EML-055
            # EML-050: the same rule as the tab "Korrespondenz" – the rights and a mailbox that sends.
            "may_write_mail": may_write_correspondence(request, case) and can_send_from(case),
            "show_customer": may_see_customers(rights),
            # PRJ-108: who takes part, and the form to add somebody.
            "participants": list(service_cases.participants_of(case)),
            "participant_form": ParticipantForm(auto_id="participant_%s") if may_change else None,
        },
    )


@require_POST
@case_work_required(Level.WRITE)
def case_customer_pdf(request: HttpRequest, pk: Any) -> HttpResponse:
    """Make the PDF for the customer – overview and open correspondence – and store it under "Documents" (PRJ-131).

    Whoever may change the case and read its correspondence (AUT-033: also the person responsible and those taking
    part); the messages with lock are not in it, whatever the price right of the user is.
    """
    case = _case_for(request, pk, ProjectAccess.EDIT)
    if not may_read_correspondence(request, case):
        raise PermissionDenied
    try:
        stored = case_pdf.export_customer_pdf(
            case, user=request.user, with_contacts=may_see_customers(request_rights(request))
        )
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect("projects:case_detail", pk=case.pk)
    messages.success(
        request,
        _("The PDF for the customer was made and stored under “Documents”: %(name)s.") % {"name": stored.original_name},
    )
    return redirect(reverse("documents:list", args=[case.pk]))


@case_work_required(Level.WRITE)
def case_edit(request: HttpRequest, pk: Any) -> HttpResponse:
    """Change subject, customer, contact, description or the person responsible of a case (PRJ-090).

    AUT-033: also the person responsible and the people taking part (PRJ-108).
    AUT-033, AUT-034: who may not see customers – as the page of the case hides them – gets no
    customer, contact or who reported it, not even through ``?customer=``; what is posted of them is ignored.
    """
    case = _case_for(request, pk, ProjectAccess.EDIT)
    customer_fields = may_see_customers(request_rights(request))
    initial: dict[str, Any] = {}
    if customer_fields and request.GET.get("customer", "").isdigit():
        initial["customer"] = int(request.GET["customer"])
    form = ServiceCaseForm(
        request.POST or None,
        instance=case,
        initial=initial,
        customer_fields=customer_fields,
        rights=request_rights(request),
    )
    if request.method == "POST" and form.is_valid():
        try:
            service_cases.update_case(
                Project.objects.get(pk=case.pk),
                user=request.user,
                **{name: form.cleaned_data[name] for name in form.Meta.fields if name in form.fields},
            )
        except ValidationError as error:
            add_validation_error(form, error)
        else:
            messages.success(request, _("Service case %(number)s saved.") % {"number": case.number})
            return redirect("projects:case_detail", pk=case.pk)
    return render(request, "projects/case_form.html", {"form": form, "case": case, "unknown": None, "tab": "case"})


def _status_done(request: HttpRequest, case: Project) -> HttpResponse:
    """Back to the page of the case – with htmx by ``HX-Redirect``, which also closes the dialog."""
    messages.success(request, _("The service case is “%(status)s” now.") % {"status": case.case_status_label})
    target = reverse("projects:case_detail", args=[case])
    if request.headers.get("HX-Request"):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = target
        return response
    return redirect(target)


def _status_dialog(request: HttpRequest, case: Project, form: CaseStatusFollowUpForm) -> HttpResponse:
    """PRJ-112: the follow-up dialog for a status that needs one – over the page, or as a page of its own."""
    context = {"project": case, "case": case, "form": form, "status": form["case_status"].value()}
    if request.headers.get("HX-Request"):
        return render(request, "projects/_case_status_form.html", context)
    return render(request, "projects/case_status_form.html", context)


@require_http_methods(["GET", "POST"])
@case_work_required(Level.WRITE)
def case_status(request: HttpRequest, pk: Any) -> HttpResponse:
    """Set the status of a case (PRJ-090).

    PRJ-112: waiting, waiting to close and backlog open the
    follow-up dialog ("Wiedervorlage") first – a ``POST`` from the list of
    statuses (or ``GET ?status=``) answers with the dialog, and the status is
    saved only when the dialog is sent with its follow-up
    (``with_follow_up``). With htmx the dialog opens over the page; without
    the page script it is a page of its own.
    """
    case = _case_for(request, pk, ProjectAccess.EDIT)
    data = request.POST if request.method == "POST" else request.GET
    status = data.get("case_status") or data.get("status") or ""
    if status not in CaseStatus.values:
        if request.method == "GET":
            raise Http404
        messages.error(request, _("Choose a status."))
        return redirect("projects:case_detail", pk=case.pk)
    if status not in service_cases.FOLLOW_UP_STATUSES:
        if request.method == "GET":
            return redirect("projects:case_detail", pk=case.pk)
        service_cases.set_case_status(case, status, by=request.user)
        return _status_done(request, case)
    if request.method == "GET" or not request.POST.get("with_follow_up"):
        # The dialog, with the follow-up there is – or the user, for the day still to choose.
        initial = {
            "case_status": status,
            "case_waiting_for": case.case_waiting_for,
            "follow_up_on": case.follow_up_on,
            "follow_up_at": case.follow_up_at,
            "follow_up_user": case.follow_up_user_id or request.user.pk,
            "follow_up_note": case.follow_up_note,
        }
        return _status_dialog(request, case, CaseStatusFollowUpForm(initial=initial))
    form = CaseStatusFollowUpForm(request.POST)
    if form.is_valid():
        try:
            service_cases.set_case_status(
                case,
                status,
                waiting_for=form.cleaned_data.get("case_waiting_for", ""),
                follow_up=form.follow_up(),
                by=request.user,
            )
        except ValidationError as error:
            add_validation_error(form, error)
        else:
            return _status_done(request, case)
    return _status_dialog(request, case, form)


@module_required(Module.PROJECTS, Level.WRITE)
def case_convert(request: HttpRequest, pk: Any) -> HttpResponse:
    """Turn a service case into a project (PRJ-090): the project form, with the periods still to choose.

    The project keeps its number, mails, files, open items and history and
    starts as an inquiry.
    """
    case = _case_for(request, pk, ProjectAccess.EDIT, case_work=False)  # AUT-033: not part of working on it
    start, end = default_period()
    initial: dict[str, Any] = {"start": start, "end": end}
    if request.GET.get("customer", "").isdigit():
        initial["customer"] = int(request.GET["customer"])
    form = ProjectForm(request.POST or None, instance=case, initial=initial, rights=request_rights(request))
    if request.method == "POST" and form.is_valid():
        data = dict(form.cleaned_data)
        data.pop("template", None)
        for name in ("billing_address", "delivery_address"):
            if name in form.fields and form.fields[name].widget.is_hidden:
                data.pop(name, None)
        try:
            project = service_cases.convert_to_project(Project.objects.get(pk=case.pk), **data)
        except ValidationError as error:
            add_validation_error(form, error)
        else:
            messages.success(
                request,
                _("Service case %(number)s is a project now. Plan its material and crew.") % {"number": project.number},
            )
            return redirect("projects:detail", pk=project.pk)
    return render(request, "projects/form.html", {"form": form, "project": case, "parent": None, "converting": True})


# --- PRJ-108: people taking part ---------------------------------------------------------------


@require_POST
@case_work_required(Level.WRITE)
def participant_add(request: HttpRequest, pk: Any) -> HttpResponse:
    """Add a person to the case – or change function and note of somebody taking part (PRJ-108)."""
    case = _case_for(request, pk, ProjectAccess.EDIT)
    form = ParticipantForm(request.POST, auto_id="participant_%s")
    if not form.is_valid():
        messages.error(request, " ".join(message for errors in form.errors.values() for message in errors))
        return redirect(f"{reverse('projects:case_detail', args=[case])}#participants")
    person = form.cleaned_data["person"]
    known = case.participants.filter(person=person).exists()
    try:
        service_cases.add_participant(
            case,
            person,
            job_function=form.cleaned_data["job_function"],
            note=form.cleaned_data["note"],
            user=request.user,
        )
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        if known:
            messages.success(request, _("%(person)s: function and note saved.") % {"person": person})
        else:
            messages.success(request, _("%(person)s takes part in the case now.") % {"person": person})
    return redirect(f"{reverse('projects:case_detail', args=[case])}#participants")


@require_POST
@case_work_required(Level.WRITE)
def participant_remove(request: HttpRequest, pk: Any, participant_pk: int) -> HttpResponse:
    """Take a person off the case (PRJ-108); their times on it stay."""
    case = _case_for(request, pk, ProjectAccess.EDIT)
    participation = get_object_or_404(case.participants.select_related("person"), pk=participant_pk)
    service_cases.remove_participant(participation)
    messages.success(request, _("%(person)s no longer takes part in the case.") % {"person": participation.person})
    return redirect(f"{reverse('projects:case_detail', args=[case])}#participants")


def my_cases(request: HttpRequest) -> HttpResponse:
    """My area → Service cases: the cases one takes part in or is responsible for (PRJ-108).

    AUT-033: for every account that is a person – working on the own cases needs no module right.

    Not done unless "done" is asked for too, the backlog only once its follow-up is due or on request
    (PRJ-112); only cases the user
    may open (AUT-016). A table of ``core.tables``: columns, sorting, CSV,
    grouping by status.
    """
    from django.db.models import BooleanField, ExpressionWrapper, Q

    from rentalars.projects.access import person_of
    from rentalars.projects.case_tables import MY_CASES_TABLE

    person = person_of(request.user)
    if person is None:
        raise PermissionDenied
    rights = request_rights(request)
    with_done = request.GET.get("done") == "1"
    # PRJ-112: the backlog only on request, until its follow-up is due.
    with_backlog = request.GET.get("backlog") == "1"
    statuses = list(CaseStatus.values) if with_done else []
    found = service_cases.cases_of(person, request.user, statuses=statuses, with_backlog=with_backlog).filter(
        pk__in=visible_projects(rights, request.user).values("pk")
    )
    found = found.annotate(
        viewer_is_manager=ExpressionWrapper(Q(manager_id=request.user.pk), output_field=BooleanField())
    )
    table = MY_CASES_TABLE.state(request)
    found = table.order(found)
    if table.wants_csv:
        return table.csv_response(found, _("My service cases"))
    page = paginate(request, found)
    return render(
        request,
        "projects/my_cases.html",
        {
            "table": table,
            "page": page,
            "rows": table.rows(page),
            "with_done": with_done,
            "with_backlog": with_backlog,
            "tab": "cases",
            **_bulk_context(request),
        },
    )
