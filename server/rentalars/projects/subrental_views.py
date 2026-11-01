# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views of subrentals per supplier (PRJ-101, PRJ-106).

* The supplier field of a subrental: suggestions while typing and a new
  supplier in a dialog (PRJ-101).
* The page "Zumietung bei …" of a project and a supplier: the subrental
  lines with status and purchase prices, the supplier's documents and the
  correspondence with the supplier (PRJ-106).
* Which supplier a mail of the project belongs to, set by hand (PRJ-106).

Rights: the page needs read access to the project; changing status, prices
or documents needs edit access, purchase prices their special right, the
mails the right to read (and to write) correspondence (AUT-019, EML-029).
"""

from __future__ import annotations

import json
from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from rentalars.accounts.rights import Level, Module, SpecialRight, module_required, request_rights, require
from rentalars.core.forms import add_validation_error
from rentalars.mail import mailboxes
from rentalars.mail import services as mail_services
from rentalars.mail.models import ProjectMail
from rentalars.mail.suppliers import set_supplier
from rentalars.masterdata.models import Supplier
from rentalars.projects import subrentals
from rentalars.projects.access import ProjectAccess, project_for
from rentalars.projects.models import Project
from rentalars.projects.subrental_forms import SubrentalLinesForm, SupplierDocumentForm, SupplierQuickForm


def _messages_of(error: ValidationError) -> str:
    return " ".join(error.messages)


# --- PRJ-101: the supplier field ---------------------------------------------------------------------


@require_GET
def supplier_suggest(request: HttpRequest) -> JsonResponse:
    """Suggestions for the supplier field of a subrental (PRJ-101), as JSON for ``data-typeahead``."""
    rights = request_rights(request)
    require(subrentals.may_see_suppliers(rights))
    return JsonResponse(subrentals.supplier_suggestions(request.GET.get("q", ""), rights=rights), safe=False)


def supplier_quick_create(request: HttpRequest) -> HttpResponse:
    """A new supplier in a dialog over the dialog of a subrental (PRJ-101).

    ``?name=`` takes over what was typed in the supplier field; ``?field=``
    names the field that receives the new supplier. Saved, the answer closes
    the dialog and names the supplier ("objectCreated"); the page script puts
    it into the field.
    """
    rights = request_rights(request)
    require(subrentals.may_create_supplier(rights))
    field = request.GET.get("field", "supplier")
    form = SupplierQuickForm(request.POST or None, initial={"name": request.GET.get("name", "")})
    if request.method == "POST" and form.is_valid():
        try:
            supplier = subrentals.create_supplier(form.save(commit=False))
        except ValidationError as error:
            add_validation_error(form, error)
        else:
            response = HttpResponse(status=204)
            response["HX-Trigger"] = json.dumps(
                {"closeDialog": True, "objectCreated": {"field": field, "id": supplier.pk, "label": supplier.name}}
            )
            return response
    return render(request, "projects/_supplier_quick_create.html", {"form": form, "action": request.get_full_path()})


# --- PRJ-106: the page per project and supplier ------------------------------------------------------


def _page_of(request: HttpRequest, pk: int, supplier_pk: int, level: ProjectAccess) -> tuple[Project, Supplier]:
    """The project – with the planning readable – and the supplier."""
    project = project_for(request, pk, level)
    supplier = get_object_or_404(Supplier, pk=supplier_pk)
    return project, supplier


def _page_url(project: Project, supplier: Supplier, anchor: str = "") -> str:
    return reverse("projects:subrental", args=[project.pk, supplier.pk]) + (f"#{anchor}" if anchor else "")


def _can_edit(project: Project) -> bool:
    return project.access >= ProjectAccess.EDIT and not project.is_locked


def _render_page(
    request: HttpRequest,
    project: Project,
    supplier: Supplier,
    *,
    lines_form: SubrentalLinesForm | None = None,
    document_form: SupplierDocumentForm | None = None,
) -> HttpResponse:
    rights = request_rights(request)
    page = subrentals.build_page(project, supplier, rights=rights)
    can_edit = _can_edit(project)
    with_prices = rights.has(SpecialRight.PURCHASE_PRICES)
    if can_edit and lines_form is None and page.rows:
        lines_form = SubrentalLinesForm(lines=[row.line for row in page.rows], with_prices=with_prices)
    if can_edit and lines_form is not None:
        for row in page.rows:
            if f"status_{row.line.pk}" in lines_form.fields:
                row.status_field = lines_form.status_field(row.line)
                row.price_field = lines_form.price_field(row.line)
                row.pickup_field = lines_form.pickup_field(row.line)  # PRJ-097
    if can_edit and document_form is None:
        document_form = SupplierDocumentForm()
    return render(
        request,
        "projects/subrental.html",
        {
            "project": project,
            "tab": "planning",
            "supplier": supplier,
            "page": page,
            "can_edit": can_edit,
            "lines_form": lines_form if can_edit else None,
            "document_form": document_form if can_edit else None,
            "with_prices": with_prices,
            "can_write_mail": mail_services.may_write_mail(rights) and mailboxes.can_send_correspondence(),
            "can_edit_supplier": rights.can_write(Module.ADMINISTRATION),
        },
    )


@module_required(Module.PROJECTS)
def subrental_page(request: HttpRequest, pk: int, supplier_pk: int) -> HttpResponse:
    """The page "Zumietung bei …": lines, documents and mails of one supplier in one project (PRJ-106)."""
    project, supplier = _page_of(request, pk, supplier_pk, ProjectAccess.READ)
    return _render_page(request, project, supplier)


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def subrental_lines_update(request: HttpRequest, pk: int, supplier_pk: int) -> HttpResponse:
    """Save status and purchase prices of the supplier's subrentals in the project at once (PRJ-106)."""
    project, supplier = _page_of(request, pk, supplier_pk, ProjectAccess.EDIT)
    if project.is_locked:
        raise Http404
    rights = request_rights(request)
    lines = list(subrentals.subrental_lines(project, supplier))
    form = SubrentalLinesForm(request.POST, lines=lines, with_prices=rights.has(SpecialRight.PURCHASE_PRICES))
    if form.is_valid():
        try:
            changed = subrentals.update_lines(project, supplier, form.values(), rights=rights)
        except ValidationError as error:
            form.add_error(None, _messages_of(error))
        else:
            if changed:
                messages.success(request, _("The subrentals were saved."))
            else:
                messages.info(request, _("Nothing changed."))
            return redirect(_page_url(project, supplier, "lines"))
    return _render_page(request, project, supplier, lines_form=form)


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def subrental_document_add(request: HttpRequest, pk: int, supplier_pk: int) -> HttpResponse:
    """Keep a document of the supplier with the project (PRJ-106)."""
    project, supplier = _page_of(request, pk, supplier_pk, ProjectAccess.EDIT)
    if project.is_locked:
        raise Http404
    form = SupplierDocumentForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            subrentals.add_document(
                project,
                supplier,
                form.cleaned_data["file"],
                kind=form.cleaned_data["kind"],
                title=form.cleaned_data["title"],
                user=request.user,
            )
        except ValidationError as error:
            form.add_error("file", _messages_of(error))
        else:
            messages.success(request, _("Document stored. It is among the files of the project as well."))
            return redirect(_page_url(project, supplier, "documents"))
    return _render_page(request, project, supplier, document_form=form)


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def mail_supplier(request: HttpRequest, pk: int, mail_pk: int) -> HttpResponse:
    """Say by hand which supplier's subrentals a mail of the project belongs to – or none (PRJ-106)."""
    project = project_for(request, pk, ProjectAccess.EDIT)
    mail_services.require_mail_read(request_rights(request))
    mail = get_object_or_404(ProjectMail, pk=mail_pk, project=project)
    from rentalars.mail.locks import correspondence_of

    if not correspondence_of(request, project).may_read(mail):
        raise Http404  # EML-055: a message with lock does not exist without the price right
    value = request.POST.get("supplier", "")
    supplier: Any = get_object_or_404(Supplier, pk=int(value)) if value.isdigit() else None
    set_supplier(mail, supplier)
    if supplier is not None:
        messages.success(request, _("The mail belongs to the subrental at %(name)s.") % {"name": supplier.name})
    else:
        messages.success(request, _("The mail belongs to no subrental any more."))
    return redirect("mail:detail", pk=project.pk, mail_pk=mail.pk)
