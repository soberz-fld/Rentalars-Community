# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages of the outgoing documents without a project: the dialog, the draft, the issued document.

The requirement: a way to create offers, invoices and so on independently of projects and service cases, for example
a button "Neuer Ausgangsbeleg" in Buchhaltung → Ausgangsbelege that opens a dialog.

* ``accounting/documents/new/`` – the dialog "Neuer Ausgangsbeleg" opened from the list (the same form stands on a
  page of its own without the script): kind and customer, billing address, contact, date, terms, reference. It
  makes the draft and leads to its page.
* ``accounting/documents/drafts/<id>/`` – "Ausgangsbeleg bearbeiten": the lines (free, from a product, text; move,
  change, remove), the head and the texts, the choice whether the descriptions of the products are printed; "Als PDF
  ansehen" (draft mark, nothing used up), "Ausstellen" (number, PDF, XRechnung), "Entwurf löschen".
* ``accounting/documents/<id>/`` – the issued document: facts, PDF, XRechnung, "Per E-Mail senden", cancellation,
  Lexware Office.

Rights: ``free.may_see`` to look, ``free.may_change`` to make, change, issue, send or cancel – as for the list.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Module, SpecialRight, module_required, request_rights
from rentalars.core.forms import add_validation_error
from rentalars.core.i18n import file_name
from rentalars.documents import einvoice_check, free, free_mail, outgoing, payment_views, services
from rentalars.documents.free_forms import DraftForm, LineForm, NewDocumentForm, ProductLineForm, TextLineForm
from rentalars.documents.lexware import transfer_of
from rentalars.documents.models import AccountingSettings, Document, DocumentDraft, DocumentKind, DraftLine


def _require(request: HttpRequest, *, change: bool) -> Any:
    """The rights of the user, refused unless they may look at – or, with ``change``, make – such documents."""
    rights = request_rights(request)
    if not (free.may_change(rights) if change else free.may_see(rights)):
        raise PermissionDenied
    return rights


def _draft(request: HttpRequest, pk: int, *, change: bool = True) -> DocumentDraft:
    """A draft the user may open – or, with ``change``, change."""
    _require(request, change=change)
    return get_object_or_404(DocumentDraft.objects.select_related("customer", "billing_address", "contact"), pk=pk)


def _back_to(request: HttpRequest, url: str) -> HttpResponse:
    """Back to a page – from a dialog by the page script (``HX-Redirect``), else by a redirect."""
    if request.headers.get("HX-Request"):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = url
        return response
    return redirect(url)


# --- The dialog "Neuer Ausgangsbeleg" ---------------------------------------------------------------------


@module_required(Module.PROJECTS)
def free_new(request: HttpRequest) -> HttpResponse:
    """The dialog "Neuer Ausgangsbeleg": kind and customer; makes the draft and leads to its page.

    ``?customer=`` (from the page of a customer) starts with that customer. A request of the customer field
    (``HX-Request`` with ``customer`` in the address) shows the billing addresses and contacts of the customer chosen.
    """
    _require(request, change=True)
    form: NewDocumentForm
    if request.method == "POST":
        form = NewDocumentForm(request.POST)
        if form.is_valid():
            try:
                draft = form.create(request.user)
            except ValidationError as error:
                add_validation_error(form, error)
            else:
                return _back_to(request, reverse("documents:free_edit", args=[draft.pk]))
    else:
        form = NewDocumentForm(initial={key: value for key, value in request.GET.dict().items() if value})
    template = "documents/_free_new.html" if request.headers.get("HX-Request") else "documents/free_new.html"
    return render(request, template, {"form": form, "refresh": reverse("documents:free_new")})


# --- The draft ----------------------------------------------------------------------------------------------


def _edit_context(draft: DocumentDraft, **forms: Any) -> dict[str, Any]:
    """What the page of a draft shows: the lines with their amounts, the forms, what stops issuing."""
    lines = free.lines_of(draft)
    calculation = free.calculate(lines)
    # An offer that is no longer valid cannot be put together; the page stays open to correct it (DOK-022).
    content, unbuildable = free.page_content(draft, calculation)
    problems = free.problems(draft, content)
    context: dict[str, Any] = {
        "draft": draft,
        "kind_label": DocumentKind(draft.kind).label,
        "calculation": calculation,
        "problems": problems + [message for message in unbuildable if message not in problems],
        "hints": free.placeholder_hints(draft),
        "has_lines": bool(lines),
        "descriptions": sum(
            1 for priced in calculation.lines if priced.line.product_id and priced.line.product.description
        ),
    }
    context["form"] = forms.get("form") or DraftForm(draft=draft)
    context["free_form"] = forms.get("free_form") or LineForm()
    context["product_form"] = forms.get("product_form") or ProductLineForm()
    context["text_form"] = forms.get("text_form") or TextLineForm()
    return context


@module_required(Module.PROJECTS)
def free_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """The page "Ausgangsbeleg bearbeiten": the lines, the head and the texts of a draft."""
    draft = _draft(request, pk, change=request.method == "POST")
    form = None
    if request.method == "POST":
        form = DraftForm(request.POST, draft=draft)
        if form.is_valid():
            try:
                form.save()
            except ValidationError as error:
                add_validation_error(form, error)
            else:
                messages.success(request, _("The draft was saved."))
                return redirect("documents:free_edit", pk=draft.pk)
    context = _edit_context(draft, form=form)
    context["may_change"] = free.may_change(request_rights(request))
    context["text_block_choices"] = free.text_blocks_for(draft.kind)
    return render(request, "documents/free_edit.html", context)


def _line_error(request: HttpRequest, draft: DocumentDraft, error: ValidationError, **forms: Any) -> HttpResponse:
    """A line that was refused: the page of the draft again, the message above the form that was sent."""
    messages.error(request, " ".join(error.messages))
    return redirect("documents:free_edit", pk=draft.pk)


@require_POST
@module_required(Module.PROJECTS)
def free_line_add(request: HttpRequest, pk: int) -> HttpResponse:
    """Add a line to a draft: ``mode`` is ``product``, ``free`` or ``text``."""
    draft = _draft(request, pk)
    mode = request.POST.get("mode", "free")
    try:
        if mode == "product":
            form = ProductLineForm(request.POST)
            if not form.is_valid():
                raise ValidationError(_("Choose a product from the list and enter a quantity."))
            free.add_line(draft, product=form.cleaned_data["product"], quantity=form.cleaned_data["quantity"])
        elif mode == "text":
            text = TextLineForm(request.POST)
            if not text.is_valid():
                raise ValidationError(_("Enter the text."))
            free.add_line(draft, title=text.cleaned_data["title"], note=text.cleaned_data["note"], is_text=True)
        else:
            line_form = LineForm(request.POST)
            if not line_form.is_valid():
                context = _edit_context(draft, free_form=line_form)
                context["may_change"] = True
                context["text_block_choices"] = free.text_blocks_for(draft.kind)
                context["open_form"] = "free"
                return render(request, "documents/free_edit.html", context, status=400)
            free.add_line(draft, **line_form.values())
    except ValidationError as error:
        return _line_error(request, draft, error)
    return redirect(reverse("documents:free_edit", args=[draft.pk]) + "#lines")


def _line(request: HttpRequest, pk: int, line_pk: int) -> DraftLine:
    """A line of a draft the user may change."""
    draft = _draft(request, pk)
    return get_object_or_404(
        DraftLine.objects.select_related("tax_rate", "unit", "product", "draft"), pk=line_pk, draft=draft
    )


@module_required(Module.PROJECTS)
def free_line_edit(request: HttpRequest, pk: int, line_pk: int) -> HttpResponse:
    """Change a line: texts, quantity, unit, price, tax rate, discount."""
    line = _line(request, pk, line_pk)
    form = LineForm(request.POST or None, line=line)
    if request.method == "POST" and form.is_valid():
        try:
            free.update_line(line, **form.values())
        except ValidationError as error:
            add_validation_error(form, error)
        else:
            return redirect(reverse("documents:free_edit", args=[line.draft_id]) + "#lines")
    return render(request, "documents/free_line_form.html", {"form": form, "line": line, "draft": line.draft})


@require_POST
@module_required(Module.PROJECTS)
def free_line_delete(request: HttpRequest, pk: int, line_pk: int) -> HttpResponse:
    """Take a line out of the draft."""
    line = _line(request, pk, line_pk)
    free.delete_line(line)
    return redirect(reverse("documents:free_edit", args=[line.draft_id]) + "#lines")


@require_POST
@module_required(Module.PROJECTS)
def free_line_move(request: HttpRequest, pk: int, line_pk: int) -> HttpResponse:
    """Move a line up or down (``direction``)."""
    line = _line(request, pk, line_pk)
    free.move_line(line, -1 if request.POST.get("direction") == "up" else 1)
    return redirect(reverse("documents:free_edit", args=[line.draft_id]) + "#lines")


@require_POST
@module_required(Module.PROJECTS)
def free_preview(request: HttpRequest, pk: int) -> HttpResponse:
    """The PDF as it would come out, marked as draft; no number is used up."""
    draft = _draft(request, pk, change=False)
    try:
        pdf = free.preview(draft)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect("documents:free_edit", pk=draft.pk)
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{file_name("draft", extension="pdf")}"'
    return response


@require_POST
@module_required(Module.PROJECTS)
def free_issue(request: HttpRequest, pk: int) -> HttpResponse:
    """Issue the draft ("Ausstellen"): number, PDF and XRechnung; the draft becomes a document for good."""
    draft = _draft(request, pk)
    try:
        document = free.issue(draft, user=request.user)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        if getattr(error, "code", None) == "already_issued":
            return redirect("documents:outgoing")  # the draft is gone: its page would be a 404
        return redirect("documents:free_edit", pk=draft.pk)
    messages.success(request, _("%(title)s %(number)s made.") % {"title": document.title, "number": document.number})
    return redirect("documents:free_document", pk=document.pk)


@require_POST
@module_required(Module.PROJECTS)
def free_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Throw a draft away; no number was used up."""
    draft = _draft(request, pk)
    free.delete_draft(draft)
    messages.success(request, _("The draft was deleted."))
    return redirect("documents:outgoing")


# --- The issued document --------------------------------------------------------------------------------------


def _document(request: HttpRequest, pk: int, *, change: bool = False) -> Document:
    """A document without a project the user may open – or, with ``change``, send or cancel."""
    _require(request, change=change)
    document = get_object_or_404(
        Document.objects.select_related("customer", "cancels", "cancelled_by", "created_by"),
        pk=pk,
        project__isnull=True,
    )
    return document


@module_required(Module.PROJECTS)
def free_document(request: HttpRequest, pk: int) -> HttpResponse:
    """A document made in Accounting: its facts and positions as stored, PDF, XRechnung, sending, cancelling."""
    document = _document(request, pk)
    rights = request_rights(request)
    invoices_on = services.invoices_enabled()
    document.accounting_transfer = transfer_of(document)
    positions = [
        {
            **position,
            "quantity": Decimal(str(position.get("quantity") or 0)),
            "amount": Decimal(str(position.get("amount") or 0)),
        }
        for section in document.content.get("sections", [])
        for position in section.get("positions", [])
    ]
    return render(
        request,
        "documents/free_document.html",
        {
            "document": document,
            "positions": positions,
            "content": document.content,
            "may_change": free.may_change(rights),
            "invoices_on": invoices_on,
            "lexware_on": invoices_on and AccountingSettings.load().lexware_enabled,
            "may_transfer": rights.has(SpecialRight.PRICES) and free.may_change(rights),
            # The payments of an invoice and the check of its e-invoice (DOK-048, DOK-042)
            "show_payments": invoices_on and document.kind == "invoice" and outgoing.may_see(rights),
            "check": einvoice_check.report_json(einvoice_check.check_of(document)),
            "check_url": reverse("documents:check", args=[document.pk]) if payment_views.may_enter(rights) else "",
        },
    )


@module_required(Module.PROJECTS)
def free_send(request: HttpRequest, pk: int) -> HttpResponse:
    """Send the document (and the XRechnung) to the customer by mail ("Per E-Mail senden"), noted as sent."""
    document = _document(request, pk, change=True)
    form = free_mail.SendForm(request.POST or None, initial=free_mail.initial_for(document), document=document)
    if request.method == "POST" and form.is_valid():
        try:
            free_mail.send_document_mail(
                document,
                to=form.cleaned_data["to"],
                cc=form.cleaned_data["cc"],
                bcc=form.cleaned_data["bcc"],
                subject=form.cleaned_data["subject"],
                body=form.cleaned_data["body"],
                with_signature=bool(form.cleaned_data.get("signature")),
                with_xml=bool(form.cleaned_data.get("xml")),
                user=request.user,
            )
        except ValidationError as error:
            add_validation_error(form, error)
        else:
            messages.success(request, _("The mail was sent."))
            return redirect("documents:free_document", pk=document.pk)
    return render(request, "documents/free_send.html", {"document": document, "form": form})


@require_POST
@module_required(Module.PROJECTS)
def free_cancel(request: HttpRequest, pk: int) -> HttpResponse:
    """Cancel a free invoice by a cancellation, which is a free document as well."""
    document = _document(request, pk, change=True)
    try:
        cancellation = services.cancel_invoice(document, user=request.user)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect("documents:free_document", pk=document.pk)
    messages.success(
        request,
        _("Invoice %(invoice)s is cancelled by %(number)s.")
        % {"invoice": document.number, "number": cancellation.number},
    )
    return redirect("documents:free_document", pk=cancellation.pk)
