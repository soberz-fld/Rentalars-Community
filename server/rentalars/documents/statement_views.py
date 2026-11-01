# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages of the monthly statements of service cases: Buchhaltung → Monatsabrechnung (DOK-016).

DOK-019: a tab of the main entry "Buchhaltung" below ``/accounting/monthly/`` (NFA-074).

* The overview of a month (:func:`statement_overview`): per customer the
  service cases to bill – hours, net sum – and the statements made, with
  "Entwurf anlegen" or "Entwurf öffnen". The month is chosen; the previous
  one is shown first.
* The statement (:func:`statement_detail`): per case its activity text and
  its positions, editable; free positions; the totals. With "Rechnungen in
  Rentalars erstellen" on (DOK-014) a preview and "Rechnung erstellen";
  off, the values to copy into the other program – each by a click, as in
  the price overview (PRJ-035), and all at once as a table – and "Als
  abgerechnet markieren".

One form holds everything of a draft: every button saves what was typed
before it does its part (``action``), so no change is lost. Without the price
right (AUT-019) nothing of it opens; changing needs write access to projects
and edit access to every case, as making an invoice does.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Module, SpecialRight, module_required, request_rights
from rentalars.core.i18n import file_name
from rentalars.core.money import format_decimal, format_money, parse_decimal
from rentalars.core.tables import csv_text
from rentalars.documents import outgoing, statements
from rentalars.documents.models import MonthlyStatement, StatementStatus
from rentalars.documents.services import invoices_enabled


def _require_use(request: HttpRequest) -> Any:
    rights = request_rights(request)
    if not statements.may_use(rights):
        raise PermissionDenied
    return rights


def _statement(request: HttpRequest, pk: int, *, edit: bool = False) -> MonthlyStatement:
    """A statement the user may open – or, with ``edit``, change: every case readable, editable (AUT-016)."""
    rights = _require_use(request)
    if edit and not statements.may_change(rights):
        raise PermissionDenied
    statement = get_object_or_404(MonthlyStatement.objects.select_related("customer", "invoice"), pk=pk)
    statements.check_cases(statement.cases.all(), rights=rights, user=request.user, edit=edit)
    return statements.prune(statement)


def _months(selected: Any) -> list[tuple[str, str]]:
    """The months to choose from: two years back from the current month, and the one chosen."""
    month = statements.first_of_month(timezone.localdate())
    found = []
    for _index in range(25):
        found.append(month)
        month = statements.previous_month(month)
    if selected not in found:
        found.append(selected)
    return [(statements.month_key(month), statements.month_label(month)) for month in sorted(found, reverse=True)]


@module_required(Module.PROJECTS)
def statement_overview(request: HttpRequest) -> HttpResponse:
    """Buchhaltung → Monatsabrechnung: per customer the service cases of a month to bill (DOK-016)."""
    rights = _require_use(request)
    month = statements.parse_month(request.GET.get("month")) or statements.previous_month()
    rows = statements.overview(month, rights=rights, user=request.user)
    return render(
        request,
        "documents/statements.html",
        {
            **outgoing.tabs(rights),  # DOK-019: the tabs of "Buchhaltung"
            "tab": "statements",
            "month": month,
            "month_value": statements.month_key(month),
            "month_label": statements.month_label(month),
            "months": _months(month),
            "previous": statements.month_key(statements.previous_month(month)),
            "next": statements.month_key(statements.next_month(month)),
            "rows": rows,
            "invoices_on": invoices_enabled(),
            "may_change": statements.may_change(rights),
            # ZEI-023: times without a project belong to no case – named to who can assign them.
            "without_project": statements.times_without_project(month) if rights.has(SpecialRight.APPROVE_TIMES) else 0,
        },
    )


@require_POST
@module_required(Module.PROJECTS)
def statement_create(request: HttpRequest) -> HttpResponse:
    """Make the draft of a customer and month ("Entwurf anlegen") – or open the one there is (DOK-016)."""
    from rentalars.customers.models import Customer

    rights = _require_use(request)
    if not statements.may_change(rights):
        raise PermissionDenied
    month = statements.parse_month(request.POST.get("month")) or statements.previous_month()
    customer_id = request.POST.get("customer", "")
    customer = get_object_or_404(Customer, pk=int(customer_id)) if customer_id.isdigit() else None
    if customer is None:
        raise Http404
    try:
        statement, created = statements.create_statement(customer, month, user=request.user, rights=rights)
    except (ValidationError, PermissionDenied) as error:
        # A case the user may not edit (AUT-016) is said like a check that failed: the statement is not made.
        messages.error(request, " ".join(error.messages) if isinstance(error, ValidationError) else str(error))
        return redirect(f"{reverse('documents:statements')}?month={statements.month_key(month)}")
    if created:
        messages.success(
            request,
            _("Draft of the monthly statement of %(customer)s for %(month)s made.")
            % {"customer": customer.name, "month": statements.month_label(month)},
        )
    return redirect("documents:statement", pk=statement.pk)


# --- The statement ------------------------------------------------------------------------------------------


def _number(value: str) -> Any:
    """A number typed on the page, in the format of the language (``1,5``); the text itself if it is none."""
    try:
        return parse_decimal(value)
    except (InvalidOperation, ValueError):
        return value


#: The fields of a position on the page.
POSITION_FIELDS = ("title", "quantity", "unit", "unit_price", "tax_rate")
NUMBER_FIELDS = frozenset({"quantity", "unit_price"})


def _form_changes(statement: MonthlyStatement, data: Any, action: str) -> dict[str, Any]:
    """What the form of the page says, as ``statements.update_statement`` takes it – with the action's part."""
    kind, _sep, target = action.partition(":")
    changes: dict[str, Any] = {}
    if "introduction" in data:
        changes["introduction"] = data.get("introduction", "")
    cases = []
    for entry in statement.content.get("cases", []):
        case_id = int(entry["case"])
        case_changes: dict[str, Any] = {"id": case_id, "positions": []}
        if f"activity-{case_id}" in data:
            case_changes["activity"] = data.get(f"activity-{case_id}", "")
        for position in entry.get("positions", []):
            prefix = f"pos-{case_id}-{position['key']}-"
            fields = {
                name: (_number(data[prefix + name]) if name in NUMBER_FIELDS else data[prefix + name])
                for name in POSITION_FIELDS
                if prefix + name in data
            }
            if kind in ("remove", "restore") and target == f"{case_id}:{position['key']}":
                fields["removed"] = kind == "remove"
            if fields:
                case_changes["positions"].append({"key": position["key"], **fields})
        if kind == "add" and target == str(case_id):
            prefix = f"new-{case_id}-"
            new = {
                name: (_number(data.get(prefix + name, "")) if name in NUMBER_FIELDS else data.get(prefix + name, ""))
                for name in (*POSITION_FIELDS, "article_number")
            }
            for name in NUMBER_FIELDS:
                if new[name] == "":
                    new[name] = None
            case_changes["add"] = [new]
        if kind == "remove_case" and target == str(case_id):
            case_changes["remove"] = True
        cases.append(case_changes)
    changes["cases"] = cases
    return changes


def _plain(value: Decimal) -> str:
    """An amount without currency, as the price overview copies it: ``1.234,50`` (PRJ-035)."""
    return format_money(value, currency="").strip()


def _copy_rows(statement: MonthlyStatement) -> list[list[str]]:
    """The positions as rows of text – case, title, quantity, unit, unit price, tax, amount – to copy (DOK-014 off).

    Each cell as a list exports it (``core.tables.csv_text``): on one line, and a formula made harmless.
    """
    rows = [
        [
            _("Service case"),
            _("Title"),
            _("Quantity"),
            _("Unit"),
            _("Unit price"),
            _("Tax"),
            _("Amount"),
        ]
    ]
    for entry in statement.content.get("cases", []):
        for position in statements.live_positions(entry):
            rows.append(
                [
                    entry["number"],
                    position["title"],
                    format_decimal(Decimal(position["quantity"])),
                    position.get("unit", ""),
                    _plain(Decimal(position["unit_price"])),
                    f"{format_decimal(Decimal(position.get('tax_percent') or 0), max_places=2)} %",
                    _plain(statements.amount_of(position)),
                ]
            )
    # Pasted into a spreadsheet: a title such as "=HYPERLINK(…)" must not become a formula ("CSV injection").
    return [[csv_text(cell) for cell in row] for row in rows]


def _context(request: HttpRequest, statement: MonthlyStatement) -> dict[str, Any]:
    """Everything the page of a statement shows."""
    from rentalars.masterdata.models import TaxRate

    rights = request_rights(request)
    may_change = statements.may_change(rights)
    try:
        statements.check_cases(statement.cases.all(), rights=rights, user=request.user, edit=True)
    except PermissionDenied:
        may_change = False
    editable = statement.is_draft and may_change
    hints = statements.case_hints(statement) if statement.is_draft else {}
    cases = []
    number = 0
    for entry in sorted(statement.content.get("cases", []), key=lambda entry: entry["number"]):
        positions = []
        for position in entry.get("positions", []):
            if not position.get("removed"):
                number += 1
            positions.append(
                {
                    **position,
                    "pos": number if not position.get("removed") else "",
                    "amount": statements.amount_of(position),
                    "quantity_value": Decimal(position["quantity"]),
                    "unit_price_value": Decimal(position["unit_price"]),
                    "tax_percent_value": Decimal(position.get("tax_percent") or 0),
                }
            )
        cases.append(
            {
                **entry,
                "positions": [position for position in positions if not position.get("removed")],
                "removed_positions": [position for position in positions if position.get("removed")],
                "total": statements.case_total(entry),
                "hints": hints.get(int(entry["case"]), []),
            }
        )
    ai_on, endpoint = statements.ai_available() if editable else (False, None)
    tax_rates = list(TaxRate.objects.filter(is_active=True))
    used = {position.get("tax_rate") for entry in cases for position in entry["positions"]} - {
        rate.pk for rate in tax_rates
    }
    tax_rates += list(TaxRate.objects.filter(pk__in=[pk for pk in used if pk]))
    rows = _copy_rows(statement)
    invoices_on = invoices_enabled()
    first = statements.ordered_cases(statement)[:1]
    return {
        **outgoing.tabs(rights),  # DOK-019: the tabs of "Buchhaltung"
        "tab": "statements",
        "statement": statement,
        "month_label": statements.month_label(statement.month),
        "month_value": statements.month_key(statement.month),
        "cases": cases,
        "totals": statements.totals_of(statement.content),
        "editable": editable,
        "may_delete": editable and rights.can_delete(Module.PROJECTS),
        "may_unmark": may_change and statement.status == StatementStatus.MARKED,
        "invoices_on": invoices_on,
        "first_case": first[0] if first else None,
        "tax_rates": tax_rates,
        # EML-040: the AI follows its rights – who may read the correspondence –, and only while it can be reached.
        "ai_on": ai_on and rights.has(SpecialRight.CORRESPONDENCE_READ),
        "ai_local": bool(endpoint and endpoint.is_local),
        "job": _job_of(request, statement),
        "copy_rows": rows if not invoices_on else [],
        "copy_text": "\n".join("\t".join(row) for row in rows),
        "cancelled_invoices": statement.content.get("cancelled_invoices") or [],
    }


def _job_of(request: HttpRequest, statement: MonthlyStatement) -> Any:
    """The AI summary the user started for this statement and is waiting for (``?job=``)."""
    from rentalars.core.models import BackgroundJob

    value = request.GET.get("job", "")
    if not value.isdigit():
        return None
    return BackgroundJob.objects.filter(
        pk=int(value), kind=statements.JOB_KIND, created_by=request.user, params__statement=statement.pk
    ).first()


@module_required(Module.PROJECTS)
def statement_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """The statement of a customer and month: check, change, then invoice or mark (DOK-016).

    POST saves the form and does what its button says (``action``): ``save``,
    ``refresh``, ``add:<case>``, ``remove:<case>:<key>``,
    ``restore:<case>:<key>``, ``remove_case:<case>``, ``ai:<case>``,
    ``preview``, ``invoice``, ``mark`` – and, of a marked statement, ``unmark``.
    """
    if request.method != "POST":
        statement = _statement(request, pk)
        return render(request, "documents/statement.html", _context(request, statement))
    statement = _statement(request, pk, edit=True)
    rights = request_rights(request)
    action = request.POST.get("action", "save")
    if action.startswith("ai:") and not rights.has(SpecialRight.CORRESPONDENCE_READ):
        raise PermissionDenied  # EML-040: the AI reads the correspondence – for who may read it (EML-029)
    target = reverse("documents:statement", args=[statement.pk])
    try:
        if action == "unmark":
            statements.unmark(statement, user=request.user, rights=rights)
            messages.success(request, _("The mark is taken back: the statement is a draft again."))
            return redirect(target)
        statement = statements.update_statement(
            statement, _form_changes(statement, request.POST, action), user=request.user
        )
        kind, _sep, value = action.partition(":")
        if kind == "refresh":
            for line in statements.refresh(statement, user=request.user, rights=rights) or [
                _("Nothing new to collect.")
            ]:
                messages.info(request, line)
        elif kind == "preview":
            pdf = statements.preview(statement)
            response = HttpResponse(pdf, content_type="application/pdf")
            response["Content-Disposition"] = f'inline; filename="{file_name("draft", extension="pdf")}"'
            return response
        elif kind == "invoice":
            document = statements.create_invoice(statement, user=request.user, rights=rights)
            messages.success(
                request, _("%(title)s %(number)s made.") % {"title": document.title, "number": document.number}
            )
        elif kind == "mark":
            statements.mark(statement, user=request.user, rights=rights)
            messages.success(request, _("Marked as invoiced: the service cases count as invoiced."))
        elif kind == "ai":
            return _start_ai(request, statement, value, target)
        elif kind == "remove_case":
            messages.success(request, _("The service case is no longer in the statement."))
        elif kind == "save":
            messages.success(request, _("Saved."))
        if kind in ("add", "remove", "restore", "remove_case") and value:
            target += f"#case-{value.split(':')[0]}"
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    except PermissionDenied as error:
        # Collecting again found a new case the user may not edit (AUT-016): nothing is added.
        messages.error(request, str(error) or _("You do not have the right to do this."))
    return redirect(target)


def _start_ai(request: HttpRequest, statement: MonthlyStatement, value: str, target: str) -> HttpResponse:
    """Start the AI summary of a case's activity (EML-040) – for who may read the correspondence."""
    from rentalars.ai.client import AIError

    if not value.isdigit():
        raise Http404
    try:
        job = statements.start_summary(statement, int(value), user=request.user)
    except AIError as error:
        messages.error(request, str(error))
        return redirect(f"{target}#case-{value}")
    if not job.is_finished:
        messages.info(request, _("The AI is summarising the activity. You can go on working meanwhile."))
    elif job.status == "failed":
        messages.error(request, job.message or _("The summary did not work."))
    return redirect(f"{target}?job={job.pk}#case-{value}")


@module_required(Module.PROJECTS)
def statement_job(request: HttpRequest, pk: int, job_pk: int) -> HttpResponse:
    """How far the AI summary got; once it is done the page loads again with the new text (EML-040)."""
    from rentalars.core.models import BackgroundJob

    statement = _statement(request, pk)
    job = get_object_or_404(
        BackgroundJob, pk=job_pk, kind=statements.JOB_KIND, created_by=request.user, params__statement=statement.pk
    )
    if job.is_finished and request.headers.get("HX-Request"):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = (
            f"{reverse('documents:statement', args=[statement.pk])}#case-{job.params.get('case', '')}"
        )
        return response
    return render(request, "documents/_statement_job.html", {"statement": statement, "job": job})


@require_POST
@module_required(Module.PROJECTS)
def statement_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Discard a draft – needs the right to delete in projects, as deleting through the API (AUT-015)."""
    statement = _statement(request, pk, edit=True)
    if not request_rights(request).can_delete(Module.PROJECTS):
        raise PermissionDenied
    month = statements.month_key(statement.month)
    try:
        statements.delete_statement(statement)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect("documents:statement", pk=statement.pk)
    messages.success(request, _("The draft is deleted; its service cases are free again."))
    return redirect(f"{reverse('documents:statements')}?month={month}")
