# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views of the documents: the tab "Documents" of a project (DOK-003 to DOK-008, DOK-010, DOK-011).

PRJ-045, PRJ-046: offer, order confirmation and invoice are made on the
whole project, with all its parts; the tab of a part says so and leads
there. Delivery notes and crew dispositions are made per part.

DOK-013: the options of an offer – every position or only the groups, the
validity as a date or in days. PRJ-081: the deployment view as PDF.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import capfirst
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Module, SpecialRight, module_required, request_rights
from rentalars.core.forms import StyledForm
from rentalars.core.i18n import file_name
from rentalars.core.uploads import document_response
from rentalars.documents import outgoing, services
from rentalars.documents.lexware import transfer_of
from rentalars.documents.models import (  # MAKEABLE: importable from here
    MAKEABLE,  # noqa: F401
    MAX_VALIDITY_DAYS,
    PRICED_KINDS,
    AccountingSettings,
    BillingType,
    Document,
    DocumentDetail,
    DocumentKind,
    TextBlock,
)
from rentalars.projects.access import ProjectAccess, project_for
from rentalars.projects.models import Project


class DocumentForm(StyledForm):
    """Which document, which text blocks, which packlist (DOK-005); until when an offer holds (DOK-010).

    DOK-013: an offer shows every position or only the groups with their
    sums, and its validity is given as a date or as a number of days – the
    page keeps the two in step (``static/js/app.js``). Without the script
    the field that was changed counts; see :meth:`options`.
    """

    kind = forms.ChoiceField(label=gettext_lazy("Document"))
    detail = forms.ChoiceField(
        label=gettext_lazy("Level of detail"),
        choices=DocumentDetail.choices,
        initial=DocumentDetail.LINES,
        required=False,
        widget=forms.RadioSelect,
        help_text=gettext_lazy("Only groups: every group with its description and sum, without the lines in it."),
    )
    valid_until = forms.DateField(
        label=gettext_lazy("Valid until"),
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        help_text=gettext_lazy("Until when the offer holds."),
    )
    validity_days = forms.IntegerField(
        label=gettext_lazy("Validity in days"),
        required=False,
        min_value=0,
        max_value=MAX_VALIDITY_DAYS,
        widget=forms.NumberInput(attrs={"data-validity-days": "", "inputmode": "numeric"}),
        help_text=gettext_lazy("Counted from today, the date of the offer."),
    )
    text_blocks = forms.MultipleChoiceField(
        label=gettext_lazy("Text blocks"), required=False, widget=forms.CheckboxSelectMultiple
    )
    packlist = forms.ChoiceField(label=gettext_lazy("Packing list"), required=False)
    #: Product descriptions: preset from the template of the kind; the script of the page follows the kind.
    print_product_descriptions = forms.BooleanField(
        label=gettext_lazy("Print the description of the products"),
        required=False,
        help_text=gettext_lazy("The description of each product stands under its position."),
    )

    #: Several invoices per project: which part of the project an invoice bills.
    billing_type = forms.ChoiceField(
        label=gettext_lazy("What the invoice bills"),
        required=False,
        choices=[
            ("", gettext_lazy("The whole project in one invoice")),
            (BillingType.ADVANCE, gettext_lazy("Advance invoice (payment on account)")),
            (BillingType.PARTIAL, gettext_lazy("Partial invoice")),
            (BillingType.FINAL, gettext_lazy("Final invoice (deducts the advance and partial invoices)")),
        ],
        help_text=gettext_lazy(
            "Several invoices for one project: advance and partial invoices bill an amount; the final invoice bills "
            "the whole project and deducts them."
        ),
    )
    billing_percent = forms.DecimalField(
        label=gettext_lazy("Percentage of the net total"),
        required=False,
        min_value=0,
        max_value=100,
        max_digits=5,
        decimal_places=2,
        localize=True,
    )
    billing_amount = forms.DecimalField(
        label=gettext_lazy("Net amount (€)"),
        required=False,
        min_value=0,
        max_digits=12,
        decimal_places=2,
        localize=True,
    )
    billing_note = forms.CharField(
        label=gettext_lazy("What is it for?"),
        required=False,
        max_length=200,
        help_text=gettext_lazy("Stands on the invoice, e.g. “Anzahlung bei Auftrag”."),
    )

    def __init__(self, *args: Any, project: Project, may_see_prices: bool, **kwargs: Any) -> None:
        from rentalars.documents.models import TextBlock
        from rentalars.packing.services import packlists_of

        # DOK-013: a new offer starts with the validity of the settings (template of the offer).
        days = services.default_validity_days()
        #: The date the validity is counted from: the date a document made now gets.
        self.issued_on = timezone.localdate()
        initial = kwargs.setdefault("initial", {})
        initial.setdefault("valid_until", self.issued_on + datetime.timedelta(days=days))
        initial.setdefault("validity_days", days)
        super().__init__(*args, **kwargs)
        # The script that keeps date and days in step finds the two fields by these marks (DOK-013).
        self.fields["valid_until"].widget.attrs["data-validity-date"] = ""
        # PRJ-045: a part gets its priced documents through its whole project.
        priced_allowed = may_see_prices and not project.parent_id
        # DOK-014: without the invoice while invoices are switched off.
        kinds = [kind for kind in services.makeable_kinds() if priced_allowed or kind not in PRICED_KINDS]
        self.fields["kind"].choices = [(kind.value, capfirst(kind.label)) for kind in kinds]
        self.fields["text_blocks"].choices = [
            (str(block.pk), block.name) for block in TextBlock.objects.filter(is_active=True)
        ]
        # The choice of each kind's template; the box starts with that of the kind shown first.
        defaults = {
            kind.value: services.template_for(kind.value).print_product_descriptions
            for kind in services.makeable_kinds()
        }
        self.description_defaults = defaults
        first = (self.initial.get("kind") or next(iter(self.fields["kind"].choices), ("",))[0]) or ""
        self.fields["print_product_descriptions"].initial = defaults.get(first, False)
        self.fields["print_product_descriptions"].widget.attrs["data-description-defaults"] = json.dumps(defaults)
        packlists = packlists_of(project)
        self.fields["packlist"].choices = [("", _("all packing lists"))] + [
            (str(packlist.pk), packlist.label) for packlist in packlists
        ]
        if len(packlists) < 2:
            self.fields["packlist"].widget = forms.HiddenInput()

    def options(self, project: Project) -> dict[str, Any]:
        """The arguments for ``services.create_document``."""
        from rentalars.packing.models import Packlist

        packlist_id = self.cleaned_data.get("packlist") or ""
        options: dict[str, Any] = {
            "print_product_descriptions": bool(self.cleaned_data.get("print_product_descriptions")),
            "text_block_ids": [int(value) for value in self.cleaned_data.get("text_blocks", [])],
            "packlist": Packlist.objects.filter(pk=int(packlist_id), project=project).first()
            if packlist_id.isdigit()
            else None,
        }
        if self.cleaned_data.get("kind") == DocumentKind.INVOICE and self.cleaned_data.get("billing_type"):
            from rentalars.documents.billing import Billing

            options["billing"] = Billing(
                type=self.cleaned_data["billing_type"],
                amount=self.cleaned_data.get("billing_amount"),
                percent=self.cleaned_data.get("billing_percent"),
                note=self.cleaned_data.get("billing_note") or "",
            )
        if self.cleaned_data.get("kind") == DocumentKind.OFFER:
            options["detail"] = self.cleaned_data.get("detail") or DocumentDetail.LINES
            # DOK-013: with the script both fields arrive in step. Without it only the changed one tells what
            # was meant; neither changed: the validity of the settings, counted from today.
            changed = set(self.changed_data) & {"valid_until", "validity_days"}
            if "valid_until" in changed:
                options["valid_until"] = self.cleaned_data.get("valid_until")
            if "validity_days" in changed:
                options["validity_days"] = self.cleaned_data.get("validity_days")
        return options


def _may_see(request: HttpRequest, document: Document) -> bool:
    return not document.is_priced or request_rights(request).has(SpecialRight.PRICES)


@module_required(Module.PROJECTS)
def document_list(request: HttpRequest, pk: int) -> HttpResponse:
    """The documents of a project, the form to make a new one (DOK-007) and the files (PRJ-079)."""
    project = project_for(
        request, pk, ProjectAccess.READ, queryset=Project.objects.select_related("customer", "parent")
    )
    return render_document_list(request, project)


def render_document_list(request: HttpRequest, project: Project, *, file_form: Any = None) -> HttpResponse:
    """The tab "Documents": documents and files of the project (PRJ-079).

    ``file_form`` is an upload form that came back with errors; without one
    the tab offers an empty one to whoever may change the project. ``?kind=``
    chooses the kind in "Make a document" – the button in the head of the
    project leads here with the suggested document (PRJ-078).
    """
    from rentalars.projects.course_views import files_of, new_file_form

    rights = request_rights(request)
    may_see_prices = rights.has(SpecialRight.PRICES)
    # DOK-016: a monthly invoice of service cases shows with every case it bills, not only with its own.
    listed = (
        Document.objects.filter(Q(project=project) | Q(billed_projects=project) | Q(cancels__billed_projects=project))
        .distinct()
        .select_related("created_by", "lexware_transfer", "project", "cancels", "credit_for")
    )
    # A monthly invoice only for who may read every case it bills (DOK-016, AUT-016).
    documents = [
        document
        for document in listed
        if _may_see(request, document) and services.may_open_billed(document, rights=rights, user=request.user)
    ]
    can_make = project.access >= ProjectAccess.EDIT
    invoices_on = services.invoices_enabled()
    # DOK-011: what went to Lexware Office, and who may hand an invoice over – whoever may make it.
    for document in documents:
        document.accounting_transfer = transfer_of(document)
    form = None
    billing_state = None
    if may_see_prices and invoices_on and not project.parent_id and not project.is_service_case:
        from rentalars.documents import billing

        # The "Abrechnungsstand" only where there is something to show (the calculation of the project is
        # not free): a valid advance or partial invoice or a credit note.
        if (
            billing.part_invoices(project).exists()
            or Document.objects.filter(
                Q(credit_for__project=project) | Q(cancels__project=project, billing_type=BillingType.CREDIT)
            ).exists()
        ):
            billing_state = billing.state_of(project)
    if can_make:
        form = DocumentForm(project=project, may_see_prices=may_see_prices)
        if billing_state is not None and billing_state.has_parts and not billing_state.complete:
            form.fields["billing_type"].initial = BillingType.FINAL  # the next step after advance invoices
        wanted = request.GET.get("kind", "")
        if wanted in dict(form.fields["kind"].choices):
            form.initial["kind"] = wanted
            form.fields["print_product_descriptions"].initial = form.description_defaults.get(wanted, False)
    return render(
        request,
        "documents/list.html",
        {
            "project": project,
            **_family_context(request, project),
            "documents": documents,
            "billing_state": billing_state,
            "form": form,
            "files": files_of(project),
            "file_form": file_form if file_form is not None else new_file_form(project),
            "text_blocks": list(TextBlock.objects.filter(is_active=True)) if can_make else [],
            "can_make": can_make,
            # DOK-014: with invoices switched off, nothing is cancelled or handed to Lexware Office here.
            "invoices_on": invoices_on,
            "lexware_on": invoices_on and AccountingSettings.load().lexware_enabled,
            "may_transfer": may_see_prices and (can_make or rights.can_write(Module.ADMINISTRATION)),
            # DOK-048: the payments of an invoice – for who sees the list of outgoing documents
            "show_payments": invoices_on and outgoing.may_see(rights),
            "tab": "documents",
        },
    )


def _family_context(request: HttpRequest, project: Project) -> dict[str, Any]:
    """What the tab says about the whole project and its parts (PRJ-045, PRJ-046).

    For a part: its whole project, linked if the user may read it. For a
    whole project: the parts its priced documents contain, and those left
    out because they are cancelled; each linked if the user may read it.
    """
    from rentalars.projects.access import access_level
    from rentalars.projects.family_prices import billed_parts

    rights = request_rights(request)

    def readable(member: Project) -> bool:
        return access_level(rights, request.user, member) >= ProjectAccess.READ

    if project.parent_id:
        whole = project.parent
        return {"whole": whole, "whole_readable": readable(whole)}
    parts, cancelled = billed_parts(project)
    return {
        "billed_parts": [(part, readable(part)) for part in parts],
        "cancelled_parts": [(part, readable(part)) for part in cancelled],
    }


def _form(request: HttpRequest, project: Project) -> DocumentForm:
    if request.POST.get("kind") in services.INVOICE_KINDS:
        services.check_invoices_enabled()  # DOK-014: said clearly, not as "not a valid choice"
    refusal = services.part_problem(project, request.POST.get("kind", ""))
    if refusal:
        raise ValidationError(refusal)  # PRJ-045: said clearly, not as "not a valid choice"
    may_see_prices = request_rights(request).has(SpecialRight.PRICES)
    form = DocumentForm(request.POST, project=project, may_see_prices=may_see_prices)
    if not form.is_valid():
        raise ValidationError(" ".join(message for errors in form.errors.values() for message in errors))
    return form


@require_POST
@module_required(Module.PROJECTS)
def document_preview(request: HttpRequest, pk: int) -> HttpResponse:
    """The PDF as it would come out, marked as draft; nothing is stored or counted."""
    project = project_for(request, pk, ProjectAccess.EDIT)
    try:
        form = _form(request, project)
        pdf = services.preview(
            project,
            form.cleaned_data["kind"],
            rights=request_rights(request),
            user=request.user,
            **form.options(project),
        )
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect("documents:list", pk=project.pk)
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{file_name("draft", extension="pdf")}"'
    return response


@require_POST
@module_required(Module.PROJECTS)
def document_create(request: HttpRequest, pk: int) -> HttpResponse:
    """Make the document and store it with the project for good (DOK-007)."""
    project = project_for(request, pk, ProjectAccess.EDIT)
    try:
        form = _form(request, project)
        document = services.create_document(
            project,
            form.cleaned_data["kind"],
            user=request.user,
            rights=request_rights(request),
            **form.options(project),
        )
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(
            request, _("%(title)s %(number)s made.") % {"title": document.title, "number": document.number}
        )
    return redirect("documents:list", pk=project.pk)


def _document(request: HttpRequest, pk: int, minimum: ProjectAccess = ProjectAccess.READ) -> Document:
    document = get_object_or_404(Document.objects.select_related("project", "cancels"), pk=pk)
    if document.project_id is None:
        # Free outgoing documents: no project to open – the rights of Buchhaltung → Ausgangsbelege.
        from rentalars.documents import free

        rights = request_rights(request)
        if not (free.may_change(rights) if minimum >= ProjectAccess.EDIT else free.may_see(rights)):
            raise PermissionDenied
    else:
        project_for(request, document.project_id, minimum)
    if not _may_see(request, document):
        raise PermissionDenied
    # DOK-016: a monthly invoice needs the same access to every case it bills – reading, cancelling.
    if not services.may_open_billed(document, rights=request_rights(request), user=request.user, minimum=minimum):
        raise PermissionDenied
    return document


#: The same checks for a document opened from outside this module (the download of chosen documents).
document_for = _document


@module_required(Module.PROJECTS)
def document_file(request: HttpRequest, pk: int) -> HttpResponse:
    """The stored PDF (DOK-007)."""
    document = _document(request, pk)
    return document_response(document.file.name, document.file_name)


@module_required(Module.PROJECTS)
def document_xml(request: HttpRequest, pk: int) -> HttpResponse:
    """The XRechnung of an invoice or cancellation (DOK-006)."""
    document = _document(request, pk)
    if not document.xml_file:
        raise PermissionDenied
    from rentalars.core.uploads import protected_file_response

    return protected_file_response(document.xml_file.name, download_name=f"{document.number}.xml")


@module_required(Module.PROJECTS)
def deployment_pdf(request: HttpRequest, pk: int) -> HttpResponse:
    """The deployment view as PDF "Einsatzübersicht", as the user sees the tab (PRJ-081, AUT-025).

    Whoever sees the deployment view may print it; it shows them what the
    tab shows them – never a price, a rate or the customer (AUT-023).
    """
    from rentalars.documents import deployment as sheet

    project = project_for(
        request,
        pk,
        ProjectAccess.DEPLOYMENT,
        queryset=Project.objects.select_related("contact", "manager", "venue_site", "parent"),
    )
    pdf = sheet.deployment_pdf(project, rights=request_rights(request), user=request.user)
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{sheet.file_name(project)}"'
    return response


@require_POST
@module_required(Module.PROJECTS)
def document_cancel(request: HttpRequest, pk: int) -> HttpResponse:
    """Cancel an invoice by a cancellation (DOK-006)."""
    document = _document(request, pk, ProjectAccess.EDIT)
    try:
        cancellation = services.cancel_invoice(document, user=request.user)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(
            request,
            _("Invoice %(invoice)s is cancelled by %(number)s.")
            % {"invoice": document.number, "number": cancellation.number},
        )
    if document.project_id is None:
        return redirect("documents:outgoing")  # Made in Accounting, without a project
    return redirect("documents:list", pk=document.project_id)


class CreditForm(StyledForm):
    """How much of an invoice is credited – a net amount or a percentage of what it still bills."""

    amount = forms.DecimalField(label=gettext_lazy("Net amount (€)"), required=False, min_value=0, decimal_places=2)
    percent = forms.DecimalField(label=gettext_lazy("Percentage"), required=False, min_value=0, max_value=100)
    note = forms.CharField(label=gettext_lazy("What is it for?"), required=False, max_length=200)


@require_POST
@module_required(Module.PROJECTS)
def document_credit(request: HttpRequest, pk: int) -> HttpResponse:
    """Credit a part of an invoice by a partial credit note (DOK-035)."""
    from rentalars.documents import billing

    document = _document(request, pk, ProjectAccess.EDIT)
    form = CreditForm(request.POST)
    try:
        if not form.is_valid():
            raise ValidationError(" ".join(message for errors in form.errors.values() for message in errors))
        credit = billing.credit_invoice(
            document,
            amount=form.cleaned_data["amount"],
            percent=form.cleaned_data["percent"],
            note=form.cleaned_data["note"],
            user=request.user,
        )
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(
            request,
            _("Invoice %(invoice)s is credited in part by %(number)s.")
            % {"invoice": document.number, "number": credit.number},
        )
    if document.project_id is None:
        return redirect("documents:outgoing")
    return redirect("documents:list", pk=document.project_id)


# --- DOK-015: "Rechnung gestellt" and "Keine Rechnung" ------------------------------------------


@require_POST
@module_required(Module.PROJECTS)
def invoice_mark(request: HttpRequest, pk: int) -> HttpResponse:
    """Tick "Rechnung gestellt", mark "Keine Rechnung", or take the mark away again (DOK-015).

    Needs the right to edit the project and to see prices – also on a closed
    project: the mark is bookkeeping, not a change of the project (PRJ-009).
    """
    from rentalars.documents.invoice_reminders import set_invoice_status
    from rentalars.projects.models import InvoiceMark

    project = project_for(request, pk, ProjectAccess.EDIT)
    if not request_rights(request).has(SpecialRight.PRICES):
        raise PermissionDenied
    status = request.POST.get("invoice_status", "")
    try:
        set_invoice_status(project, status, user=request.user)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(
            request,
            {
                InvoiceMark.ISSUED: _("Noted: the invoice of %(project)s is issued."),
                InvoiceMark.NOT_NEEDED: _("Noted: %(project)s gets no invoice."),
            }.get(status, _("The invoice of %(project)s is open again."))
            % {"project": project.number},
        )
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return redirect(target)
    return redirect("documents:list", pk=project.pk)
