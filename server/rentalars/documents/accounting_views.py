# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views of Settings → Accounting: Lexware Office (DOK-011) and the DATEV export (DOK-012).

Who may do what
---------------
* The page, the list of handings over and the DATEV export need read access
  to the settings (module "Administration") **and** the right to see prices:
  the export and the list are amounts of invoices (AUT-019).
* Changing the settings, checking the connection and handing over again from
  this page need write access to the settings.
* On the tab "Documents" of a project, an invoice is handed over by whoever
  may make it – write access to the project and the price right – or by
  whoever may change the settings and see prices.
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from rentalars.accounts.rights import Module, Rights, SpecialRight, request_rights
from rentalars.documents import datev, lexware
from rentalars.documents.accounting_forms import (
    BooksSettingsForm,
    DatevExportForm,
    DatevSettingsForm,
    LexwareSettingsForm,
    last_month,
)
from rentalars.documents.models import AccountingSettings, Document, LexwareTransfer, TransferState
from rentalars.documents.services import invoices_enabled
from rentalars.projects.access import ProjectAccess, access_level


def _accounting_rights(request: HttpRequest, *, write: bool = False) -> Rights:
    """Read (or write) access to the settings and the price right, else "not allowed" (DOK-011, DOK-012)."""
    rights = request_rights(request)
    allowed = rights.can_write(Module.ADMINISTRATION) if write else rights.can_read(Module.ADMINISTRATION)
    if not (allowed and rights.has(SpecialRight.PRICES)):
        raise PermissionDenied
    return rights


def may_transfer(request: HttpRequest, document: Document) -> bool:
    """Whether the user may hand this document to Lexware Office (DOK-011); see the module description."""
    rights = request_rights(request)
    if not document.is_bookable or not rights.has(SpecialRight.PRICES):
        return False
    if rights.can_write(Module.ADMINISTRATION):
        return True
    if document.project_id is None:
        from rentalars.documents.free import may_change  # A free document has no project to edit

        return may_change(rights)
    return access_level(rights, request.user, document.project) >= ProjectAccess.EDIT


def accounting(request: HttpRequest) -> HttpResponse:
    """The page: Lexware Office, the handings over that need attention, DATEV (DOK-011, DOK-012)."""
    rights = _accounting_rights(request, write=request.method == "POST")
    current = AccountingSettings.load()
    section = request.POST.get("section", "") if request.method == "POST" else ""
    lexware_form = LexwareSettingsForm(
        request.POST if section == "lexware" else None, instance=current, prefix="lexware"
    )
    datev_form = DatevSettingsForm(request.POST if section == "datev" else None, instance=current, prefix="datev")
    books_form = BooksSettingsForm(request.POST if section == "books" else None, instance=current, prefix="books")
    if section in {"lexware", "datev", "books"}:
        form = {"lexware": lexware_form, "datev": datev_form, "books": books_form}[section]
        if form.is_valid():
            form.save()
            messages.success(request, _("The settings were saved."))
            return redirect(reverse("documents:accounting") + f"#{section}")
    transfers = list(
        LexwareTransfer.objects.exclude(state=TransferState.DONE)
        .select_related("document", "document__project")
        .order_by("-updated_at")[:100]
    )
    return render(
        request,
        "documents/accounting.html",
        {
            "settings": current,
            "lexware_form": lexware_form,
            "datev_form": datev_form,
            "books_form": books_form,
            "export_form": DatevExportForm(),
            "transfers": transfers,
            "done_count": LexwareTransfer.objects.filter(state=TransferState.DONE).count(),
            "can_edit": rights.can_write(Module.ADMINISTRATION),
            "key_readable": _key_readable(current),
            "preview": _preview(*last_month()),
            # DOK-014: invoices switched off – Lexware Office and DATEV are hidden.
            "invoices_on": invoices_enabled(),
        },
    )


def _key_readable(current: AccountingSettings) -> bool:
    from rentalars.core.crypto import SecretUnreadableError

    try:
        return bool(current.lexware_api_key) or not current.has_lexware_api_key
    except SecretUnreadableError:
        return False


@require_POST
def lexware_check(request: HttpRequest) -> HttpResponse:
    """Ask Lexware Office whether the key works, and fetch the posting categories (DOK-011)."""
    _accounting_rights(request, write=True)
    try:
        result = lexware.check_connection()
    except lexware.LexwareError as error:
        messages.error(request, str(error))
    else:
        messages.success(
            request,
            _("Connected with Lexware Office: “%(organization)s”. %(count)d posting categories for income.")
            % {"organization": result.organization, "count": len(result.categories)},
        )
        if result.small_business:
            messages.warning(
                request,
                _("Lexware Office knows this company as a small business without VAT; check the tax rates."),
            )
    return redirect(reverse("documents:accounting") + "#lexware")


def _next_url(request: HttpRequest, fallback: str) -> str:
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return fallback


@require_POST
def lexware_transfer(request: HttpRequest, pk: int) -> HttpResponse:
    """Hand one invoice or cancellation to Lexware Office, in the background (DOK-011)."""
    document = get_object_or_404(Document.objects.select_related("project"), pk=pk)
    if not may_transfer(request, document):
        raise PermissionDenied
    fallback = (
        reverse("documents:list", args=[document.project_id]) if document.project_id else reverse("documents:outgoing")
    )
    try:
        transfer = lexware.request_transfer(
            document, user=request.user, new_contact=request.POST.get("new_contact") == "1"
        )
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        if transfer.state == TransferState.DONE:
            messages.success(request, _("%(number)s is in Lexware Office now.") % {"number": document.number})
        elif transfer.state == TransferState.FAILED:
            messages.error(
                request,
                _("%(number)s was not handed over: %(error)s") % {"number": document.number, "error": transfer.error},
            )
        else:
            messages.success(
                request,
                _("%(number)s is being handed to Lexware Office. You get a message when it is done.")
                % {"number": document.number},
            )
    return redirect(_next_url(request, fallback))


def _historic(request: HttpRequest) -> bool:
    """Legacy import: whether invoices taken over from an old system are part of the export (default: not)."""
    return request.GET.get("include_historic", "").lower() in {"1", "on", "true"}


def _period(request: HttpRequest) -> tuple[Any, Any]:
    form = DatevExportForm(request.GET)
    if not form.is_valid():
        return None, None
    return form.cleaned_data["date_from"], form.cleaned_data["date_to"]


@require_GET
def datev_export(request: HttpRequest) -> HttpResponse:
    """The Buchungsstapel – or with ``what=debitors`` the debitors – of a period as a file (DOK-012)."""
    _accounting_rights(request)
    date_from, date_to = _period(request)
    make = datev.debitors_file if request.GET.get("what") == "debitors" else datev.bookings_file
    try:
        if date_from is None:
            datev.check_period(AccountingSettings.load(), None, None)
        result = make(date_from, date_to, user=request.user, include_historic=_historic(request))
    except ValidationError as error:
        for message in error.messages:
            messages.error(request, message)
        return redirect(reverse("documents:accounting") + "#datev-export")
    response = HttpResponse(result.content, content_type="text/csv; charset=windows-1252")
    response["Content-Disposition"] = f'attachment; filename="{result.name}"'
    return response


def _preview(date_from: Any, date_to: Any, *, include_historic: bool = False) -> dict[str, Any]:
    """Which invoices and cancellations an export of the period holds."""
    if date_from is None or date_to is None or date_to < date_from:
        return {"documents": [], "invoices": 0, "cancellations": 0, "valid": False}
    documents = list(datev.documents_in(date_from, date_to, include_historic=include_historic))
    invoices = sum(1 for document in documents if document.kind == "invoice")
    return {
        "documents": documents,
        "invoices": invoices,
        "cancellations": len(documents) - invoices,
        "valid": True,
        "date_from": date_from,
        "date_to": date_to,
    }


@require_GET
def datev_preview(request: HttpRequest) -> HttpResponse:
    """The invoices an export of the chosen period holds, as a part of the page (DOK-012)."""
    _accounting_rights(request)
    return render(
        request,
        "documents/_datev_preview.html",
        {"preview": _preview(*_period(request), include_historic=_historic(request))},
    )
