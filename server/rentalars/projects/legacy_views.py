# SPDX-License-Identifier: GPL-3.0-or-later
"""The pages of "Altprojekte importieren" in Buchhaltung (legacy import; PRJ-130).

* the overview (``legacy``): upload one or several PDF invoices, the batches still to check, the batches taken over (with
  "Undo" for a week);
* the batch (``legacy_batch``): while the invoices are read, how far it got; then one card per invoice – customer,
  invoice data, positions, totals – to check and correct, with the plausibility checks next to the fields. "Check and
  continue" shows the confirmation (:func:`rentalars.projects.legacy_import.summary`: exactly what will be created);
  only "Take over" creates something;
* the progress block, the kept PDF for comparing, and "Undo".

Every button posts to the batch page, which saves what was typed first (nothing is created) and then does what the
button says; without JavaScript everything works the same (``action`` values ``save``, ``more-<id>``, ``skip-<id>``,
``read``, ``review``, ``confirm``).

The functions of :mod:`rentalars.projects.legacy_import` do the work; the API (``legacy_api``) uses the same ones.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_GET, require_POST

from rentalars.accounts.rights import Module, request_rights, require
from rentalars.core.money import format_decimal, format_money
from rentalars.documents import outgoing
from rentalars.projects import legacy_draft as drafts
from rentalars.projects import legacy_import
from rentalars.projects.legacy_draft import Draft, Line
from rentalars.projects.legacy_import import Issue, Report
from rentalars.projects.legacy_models import ItemState, LegacyImportBatch, LegacyImportItem


def _rights(request: HttpRequest) -> Any:
    """The rights of the user; "not allowed" unless they may use the import."""
    rights = request_rights(request)
    require(legacy_import.may_use(rights))
    return rights


def _batch(pk: int) -> LegacyImportBatch:
    return get_object_or_404(LegacyImportBatch.objects.select_related("job", "created_by"), pk=pk)


# --- The view model of the preview -----------------------------------------------------------------------------------


def _plain(value: Decimal | None, *, money: bool = False) -> str:
    """A number for a field of the page, in the language of the page."""
    if value is None:
        return ""
    return format_money(value, currency="") if money else format_decimal(value, max_places=2)


@dataclass
class LineView:
    """One position of the preview: the values for the fields and what the checks said."""

    index: int
    prefix: str
    line: Line
    title: str
    quantity: str
    unit: str
    unit_price: str
    discount: str
    tax: str
    errors: dict[str, str]
    issues: list[Issue]
    products: list[tuple[str, str, bool]]
    base: str
    printed: str
    #: The description of the position, its kind and what the kind needs (job function / vehicle / product).
    note: str = ""
    kind: str = "material"
    kinds: list[tuple[str, str, bool]] = field(default_factory=list)
    target_name: str = "product"
    target_label: str = ""
    targets: list[tuple[str, str, bool]] = field(default_factory=list)


@dataclass
class ItemView:
    """One invoice of the preview, ready for the template."""

    item: LegacyImportItem
    prefix: str
    draft: Draft
    report: Report
    values: dict[str, str]
    errors: dict[str, str]
    lines: list[LineView]
    customers: list[tuple[str, str, bool]]
    merge_options: list[tuple[str, str, bool]]
    tax_rates: list[tuple[str, str]]
    issues: dict[str, list[Issue]] = field(default_factory=dict)
    selected: bool = False
    candidates: list[Any] = field(default_factory=list)
    sums: dict[str, str] = field(default_factory=dict)
    merged: bool = False
    #: What was found about the customer, in a sentence ("An existing customer was recognised …").
    customer_status: str = ""

    @property
    def general(self) -> list[Issue]:
        """What concerns the invoice as a whole."""
        return self.issues.get("", [])


def _tax_options(draft: Draft) -> list[tuple[str, str]]:
    """The tax rates of the master data (percent as text, label), and the ones the draft has that are not there."""
    from rentalars.masterdata.models import TaxRate

    seen: dict[Decimal, str] = {}
    for rate in TaxRate.objects.filter(is_active=True).order_by("-is_default", "rate"):
        seen.setdefault(rate.rate, f"{format_decimal(rate.rate, max_places=2)} %")
    for line in draft.priced_lines:
        if line.tax_percent is not None and line.tax_percent not in seen:
            seen[line.tax_percent] = f"{format_decimal(line.tax_percent, max_places=2)} %"
    return [(format_decimal(rate, max_places=2), label) for rate, label in seen.items()]


def _customer_options(draft: Draft) -> tuple[list[tuple[str, str, bool]], list[Any]]:
    """The choices of the customer field: new, the candidates, and the customer chosen if it is none of them."""
    from rentalars.customers.models import Customer

    part = draft.customer
    candidates = drafts.customer_candidates(part)
    options = [("new", _("New customer (from the invoice)"), part.customer_id is None)]
    ids = set()
    for candidate in candidates:
        ids.add(candidate.customer_id)
        label = f"{candidate.name} ({candidate.number})" + (f", {candidate.place}" if candidate.place else "")
        options.append(
            (str(candidate.customer_id), f"{label} – {candidate.reason}", candidate.customer_id == part.customer_id)
        )
    if part.customer_id and part.customer_id not in ids:
        chosen = Customer.objects.filter(pk=part.customer_id).first()
        if chosen is not None:
            options.append((str(chosen.pk), f"{chosen.name} ({chosen.number})", True))
    return options, candidates


def _customer_status(draft: Draft, candidates: list[Any]) -> str:
    """What the reading found about the customer, as a sentence for the preview."""
    part = draft.customer
    if not (part.name or part.vat_id):
        return str(_("No customer was found on the invoice. Choose one or enter the data of a new customer."))
    chosen = next((entry for entry in candidates if entry.customer_id == part.customer_id), None)
    if part.customer_id is not None:
        label = f"{chosen.name} ({chosen.number})" if chosen is not None else ""
        return (
            str(_("The customer is an existing one: %(customer)s.") % {"customer": label})
            if label
            else str(_("The customer is an existing one."))
        )
    if candidates:
        return str(_("Customers that may be meant were found – check them, or take the data as a new customer."))
    return str(_("No existing customer matches. A new customer is created from the data of the invoice."))


def _view_of(
    item: LegacyImportItem,
    draft: Draft,
    report: Report,
    *,
    group: list[LegacyImportItem],
    selected: bool,
) -> ItemView:
    """Everything the template needs of one invoice."""
    prefix = f"i{item.pk}-"
    invoice, totals = draft.invoice, draft.totals
    typed = draft.typed_text

    def date(key: str, value: Any) -> str:
        return typed.get(key, value.isoformat() if value else "")

    values = {
        "number": invoice.number,
        "date": date("date", invoice.date),
        "service_start": date("service_start", invoice.service_start),
        "service_end": date("service_end", invoice.service_end),
        "event_name": invoice.event_name,
        "venue": invoice.venue,
        "paid_on": date("paid_on", invoice.paid_on),
        "total_net": typed.get("total_net", _plain(totals.net, money=True)),
        "total_tax": typed.get("total_tax", _plain(totals.tax, money=True)),
        "total_gross": typed.get("total_gross", _plain(totals.gross, money=True)),
    }
    issues: dict[str, list[Issue]] = {}
    for entry in [*report.errors, *report.warnings]:
        issues.setdefault(entry.key, []).append(entry)
    rates = _tax_options(draft)
    lines = []
    for index, line in enumerate(draft.lines):
        key = f"lines.{index}."
        errors = {name: kind for name, kind in draft.typed_errors.items() if name.startswith(key)}
        suggestions = [(str(entry.product_id), entry.label) for entry in line.suggestions]
        products = [("", _("Free text line"), line.product_id is None)]
        known = set()
        for value, label in suggestions:
            known.add(value)
            products.append((value, label, line.product_id is not None and str(line.product_id) == value))
        if line.product_id is not None and str(line.product_id) not in known:
            from rentalars.products.models import Product

            chosen = Product.objects.filter(pk=line.product_id).only("article_number", "name").first()
            products.append(
                (
                    str(line.product_id),
                    f"{chosen.article_number} {chosen.name}" if chosen else str(line.product_id),
                    True,
                )
            )
        kind = line.division
        kinds = [
            (value, label, value == kind)
            for value, label in (
                (drafts.KIND_MATERIAL, _("Material")),
                (drafts.KIND_CREW, _("Personnel")),
                (drafts.KIND_LOGISTICS, _("Logistics")),
            )
        ]
        target_name, target_label, targets = "product", _("Product"), []
        if kind == drafts.KIND_CREW:
            target_name, target_label = "job_function", _("Job function")
            targets = [("", _("– choose –"), line.job_function_id is None)]
            targets += [
                (str(function.pk), function.name, function.pk == line.job_function_id)
                for function, _score in drafts.job_functions_ranked(line.title)
            ]
        elif kind == drafts.KIND_LOGISTICS:
            target_label = _("Vehicle")
            targets = [("", _("– choose –"), line.product_id is None)]
            targets += [
                (str(product.pk), product.name, product.pk == line.product_id)
                for product, _score in drafts.vehicles_ranked(line.title)
            ]
        lines.append(
            LineView(
                note=typed.get(key + "note", line.note),
                kind=kind,
                kinds=kinds,
                target_name=target_name,
                target_label=str(target_label),
                targets=targets,
                index=index,
                prefix=f"{prefix}l{index}-",
                line=line,
                title=line.title,
                quantity=typed.get(key + "quantity", format_decimal(line.quantity, max_places=2)),
                unit=line.unit,
                unit_price=typed.get(key + "unit_price", _plain(line.unit_price, money=True)),
                discount=typed.get(key + "discount", _plain(line.discount) if line.discount else ""),
                tax=typed.get(key + "tax", _plain(line.tax_percent) if line.tax_percent is not None else ""),
                errors=errors,
                issues=[entry for entry in [*report.errors, *report.warnings] if entry.key.startswith(key)],
                products=products if len(products) > 1 else [],
                base=format_money(line.net, currency="") if not line.is_text else "",
                printed=format_money(line.amount, currency="") if line.amount is not None else "",
            )
        )
    options = [("", _("A project of its own"), item.merge_into_id is None)]
    for other in group:
        if other.pk != item.pk:
            options.append(
                (
                    str(other.pk),
                    _("Join to invoice %(number)s") % {"number": other.invoice_number or other.original_name},
                    other.pk == item.merge_into_id,
                )
            )
    customers, candidates = _customer_options(draft)
    customer_status = _customer_status(draft, candidates)
    sums = {
        "net": format_money(draft.net_total),
        "tax": format_money(draft.tax_total),
        "gross": format_money(draft.net_total + draft.tax_total),
    }
    return ItemView(
        item=item,
        prefix=prefix,
        draft=draft,
        report=report,
        values=values,
        errors=draft.typed_errors,
        lines=lines,
        customers=customers,
        merge_options=options,
        tax_rates=rates,
        issues=issues,
        selected=selected,
        candidates=candidates,
        sums=sums,
        merged=item.merge_into_id is not None,
        customer_status=customer_status,
    )


def _read_post(request: HttpRequest, items: list[LegacyImportItem]) -> dict[int, Draft]:
    """What the preview form sent, per invoice – kept with the record. Nothing is created."""
    result: dict[int, Draft] = {}
    open_pks = {item.pk for item in items}
    merges: dict[int, int | None] = {}
    for item in items:
        prefix = f"i{item.pk}-"
        if prefix + "lines-count" not in request.POST:
            continue
        draft = drafts.draft_from_post(request.POST, prefix, legacy_import.draft_of(item))
        result[item.pk] = draft
        choice = request.POST.get(prefix + "merge", "")
        merges[item.pk] = (
            int(choice) if choice.isdigit() and int(choice) in open_pks and int(choice) != item.pk else None
        )
    # A head is not joined itself (no chains).
    for pk, target in list(merges.items()):
        if target is not None and merges.get(target) is not None:
            merges[pk] = None
    by_pk = {item.pk: item for item in items}
    for pk, draft in result.items():
        target = by_pk.get(merges[pk]) if merges.get(pk) else None
        legacy_import.save_draft(by_pk[pk], draft, merge_into=target)
    return result


def _context(
    request: HttpRequest,
    batch: LegacyImportBatch,
    *,
    drafts_: dict[int, Draft] | None = None,
    selected: set[int] | None = None,
) -> dict[str, Any]:
    """The batch page: cards for the invoices to check, the others in a list."""
    rights = request_rights(request)
    items = list(batch.items.select_related("project", "customer", "document", "merge_into").order_by("position", "pk"))
    open_items = [item for item in items if item.state == ItemState.READ]
    views = []
    reports: dict[int, Report] = {}
    for item in open_items:
        reports[item.pk] = legacy_import.check(
            (drafts_ or {}).get(item.pk) or legacy_import.draft_of(item), item, rights=rights, siblings=open_items
        )
    for item in open_items:
        draft = (drafts_ or {}).get(item.pk) or legacy_import.draft_of(item)
        views.append(
            _view_of(
                item, draft, reports[item.pk], group=open_items, selected=selected is not None and item.pk in selected
            )
        )
    waiting = [item for item in items if item.state in {ItemState.UPLOADED, ItemState.READING}]
    job = batch.job
    return {
        **outgoing.tabs(rights),
        "tab": "legacy",
        "batch": batch,
        "views": views,
        "waiting": len(waiting),
        "job": job,
        "stuck": bool(waiting) and (job is None or job.is_finished),
        "done_items": [
            item
            for item in items
            if item.state in {ItemState.IMPORTED, ItemState.DUPLICATE, ItemState.SKIPPED, ItemState.UNDONE}
        ],
        "counts": legacy_import.batch_summary(batch),
        "undo_problems": legacy_import.undo_problems(batch, user=request.user, rights=rights)
        if any(item.state == ItemState.IMPORTED for item in items)
        else [],
        "ai_on": _ai_on(),
    }


def _ai_on() -> bool:
    from rentalars.ai.legacy_invoices import is_available

    return is_available()


# --- Overview and upload -----------------------------------------------------------------------------------------------


@require_GET
def _overview_get(request: HttpRequest) -> HttpResponse:
    rights = _rights(request)
    legacy_import.delete_old_files()
    open_batches = []
    for batch in (
        LegacyImportBatch.objects.filter(items__state__in=[ItemState.UPLOADED, ItemState.READING, ItemState.READ])
        .distinct()
        .select_related("created_by")
        .order_by("-created_at", "-pk")[:20]
    ):
        open_batches.append((batch, legacy_import.batch_summary(batch)))
    recent = []
    for batch in (
        LegacyImportBatch.objects.filter(items__state=ItemState.IMPORTED)
        .distinct()
        .select_related("created_by")
        .order_by("-created_at", "-pk")[:20]
    ):
        problems = legacy_import.undo_problems(batch, user=request.user, rights=rights)
        recent.append((batch, legacy_import.batch_summary(batch), problems))
    return render(
        request,
        "projects/legacy_overview.html",
        {
            **outgoing.tabs(rights),
            "tab": "legacy",
            "open_batches": open_batches,
            "recent": recent,
            "ai_on": _ai_on(),
            "max_files": legacy_import.MAX_FILES,
            "max_megabytes": legacy_import.MAX_FILE_BYTES // 1048576,
            "undo_days": legacy_import.UNDO_DAYS,
            "imported": legacy_import.imported_items()[:50],
        },
    )


def overview(request: HttpRequest) -> HttpResponse:
    """Buchhaltung → Altprojekte importieren: upload, open batches, what was taken over."""
    if request.method == "POST":
        return _upload(request)
    return _overview_get(request)


def _upload(request: HttpRequest) -> HttpResponse:
    _rights(request)
    files = request.FILES.getlist("invoices")
    if not files:
        messages.error(request, _("Choose one or more PDF invoices."))
        return redirect("projects:legacy")
    batch, rejected = legacy_import.add_files(files, user=request.user)
    for entry in rejected:
        messages.warning(request, f"{entry.name}: {entry.reason}")
    if batch is None:
        return redirect("projects:legacy")
    legacy_import.start_reading(batch, user=request.user)
    return redirect("projects:legacy_batch", pk=batch.pk)


# --- The batch ----------------------------------------------------------------------------------------------------------


def batch_page(request: HttpRequest, pk: int) -> HttpResponse:
    """The invoices of a batch: progress, then the preview to check; the buttons post here (see the module text)."""
    rights = _rights(request)
    batch = _batch(pk)
    if request.method != "POST":
        return render(request, "projects/legacy_batch.html", _context(request, batch))
    items = list(batch.items.filter(state=ItemState.READ).order_by("position", "pk"))
    posted = _read_post(request, items)
    action = request.POST.get("action", "save")
    selected = {int(value) for value in request.POST.getlist("take") if value.isdigit()}
    items = list(batch.items.filter(state=ItemState.READ).order_by("position", "pk"))
    if action.startswith("more-") and action[5:].isdigit():
        target = next((item for item in items if item.pk == int(action[5:])), None)
        if target is not None:
            draft = posted.get(target.pk) or legacy_import.draft_of(target)
            draft.lines.append(Line(title="", quantity=Decimal("1")))
            legacy_import.save_draft(target, draft, merge_into=target.merge_into)
            posted[target.pk] = draft
    elif action.startswith("skip-") and action[5:].isdigit():
        target = next((item for item in items if item.pk == int(action[5:])), None)
        if target is not None:
            legacy_import.skip(target)
            messages.success(
                request, _("The invoice %(name)s will not be taken over.") % {"name": target.original_name}
            )
            return redirect("projects:legacy_batch", pk=batch.pk)
    elif action == "read":
        if legacy_import.start_reading(batch, user=request.user) is not None:
            return redirect("projects:legacy_batch", pk=batch.pk)
    elif action in {"review", "confirm"}:
        return _review(request, batch, items, posted, selected, rights, confirm=action == "confirm")
    return render(
        request, "projects/legacy_batch.html", _context(request, batch, drafts_=posted or None, selected=selected)
    )


def _review(
    request: HttpRequest,
    batch: LegacyImportBatch,
    items: list[LegacyImportItem],
    posted: dict[int, Draft],
    selected: set[int],
    rights: Any,
    *,
    confirm: bool,
) -> HttpResponse:
    """Show the confirmation (“Check and continue”), or create the projects (“Take over”)."""
    chosen = [item for item in items if item.pk in selected]
    if not chosen:
        messages.error(request, _("Tick the invoices you want to take over."))
        return render(
            request, "projects/legacy_batch.html", _context(request, batch, drafts_=posted or None, selected=selected)
        )
    groups = legacy_import.groups_of(chosen)
    plans = [legacy_import.summary(head, members, rights=rights) for head, members in groups]
    if confirm:
        fingerprints = {
            int(key[3:]): value for key, value in request.POST.items() if re.fullmatch(r"fp-\d+", key) and value
        }
        outcomes = legacy_import.confirm(chosen, user=request.user, rights=rights, fingerprints=fingerprints)
        made = [outcome for outcome in outcomes if outcome.ok]
        for outcome in outcomes:
            if not outcome.ok:
                name = ", ".join(item.original_name for item in outcome.items)
                messages.error(request, f"{name}: " + " ".join(outcome.errors))
        if made:
            messages.success(
                request,
                ngettext(
                    "%(count)d old project was taken over (closed, with its invoice).",
                    "%(count)d old projects were taken over (closed, with their invoices).",
                    len(made),
                )
                % {"count": len(made)},
            )
        return redirect("projects:legacy_batch", pk=batch.pk)
    blocked = [plan for plan in plans if plan.errors]
    if blocked:
        messages.error(
            request,
            ngettext(
                "%(count)d project cannot be taken over yet. Correct what is marked below.",
                "%(count)d projects cannot be taken over yet. Correct what is marked below.",
                len(blocked),
            )
            % {"count": len(blocked)},
        )
        return render(
            request, "projects/legacy_batch.html", _context(request, batch, drafts_=posted or None, selected=selected)
        )
    rights_ = rights
    return render(
        request,
        "projects/legacy_confirm.html",
        {
            **outgoing.tabs(rights_),
            "tab": "legacy",
            "batch": batch,
            "plans": plans,
            "fingerprints": {item.pk: legacy_import.fingerprint(item) for plan in plans for item in plan.items},
            "chosen": [item.pk for plan in plans for item in plan.items],
        },
    )


@require_GET
def batch_progress(request: HttpRequest, pk: int) -> HttpResponse:
    """How far reading got – asked every two seconds by the page; when it is done the page reloads."""
    _rights(request)
    batch = _batch(pk)
    waiting = batch.items.filter(state__in=[ItemState.UPLOADED, ItemState.READING]).count()
    job = batch.job
    response = render(
        request,
        "projects/_legacy_progress.html",
        {"batch": batch, "job": job, "waiting": waiting, "counts": legacy_import.batch_summary(batch)},
    )
    if (job is not None and job.is_finished) or waiting == 0:
        response["HX-Refresh"] = "true"
    return response


@require_POST
def batch_undo(request: HttpRequest, pk: int) -> HttpResponse:
    """Take an import back (see :func:`rentalars.projects.legacy_import.undo`)."""
    rights = _rights(request)
    batch = _batch(pk)
    try:
        count = legacy_import.undo(batch, user=request.user, rights=rights)
    except ValidationError as error:
        for text in error.messages:
            messages.error(request, text)
    else:
        messages.success(
            request,
            ngettext(
                "The import was undone: %(count)d invoice with its project was removed.",
                "The import was undone: %(count)d invoices with their projects were removed.",
                count,
            )
            % {"count": count},
        )
    return redirect("projects:legacy_batch", pk=batch.pk)


@require_GET
def item_pdf(request: HttpRequest, pk: int) -> HttpResponse:
    """The kept PDF of an invoice that is not yet taken over, to compare with the preview (download, never shown inline)."""
    _rights(request)
    item = get_object_or_404(LegacyImportItem, pk=pk)
    try:
        path = legacy_import.stored_path(item)
    except FileNotFoundError:
        raise Http404 from None
    response = FileResponse(path.open("rb"), as_attachment=True, filename=item.original_name or "invoice.pdf")
    response["Content-Type"] = "application/pdf"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _unused() -> None:  # pragma: no cover
    _ = (PermissionDenied, reverse, Module)
