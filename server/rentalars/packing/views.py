# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views of the packing module: the packlists on screen and as PDF (chapter 5.8).

A project's first packlist opens under ``/projects/<id>/packlist/``; further
packlists (PCK-008) under ``/projects/<id>/packlists/<packlist>/``. Every
step exists for both addresses, so links of earlier versions keep working.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Exists, OuterRef
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, module_required, request_rights
from rentalars.core.forms import StyledForm
from rentalars.packing import services, subprojects
from rentalars.packing.models import OUT_STATUSES, Extraction, Handover, Packlist, PacklistStatus
from rentalars.packing.pdf import packing_list_name, render_family_pdf, render_packlist_pdf
from rentalars.projects.access import packlist_project_for
from rentalars.projects.family import members
from rentalars.projects.grouptree import GroupTree
from rentalars.projects.models import Project, ProjectStatus


class PacklistForm(StyledForm):
    """Title, loading time and note of a further packlist (PCK-008)."""

    title = forms.CharField(label=gettext_lazy("Title"), max_length=120, help_text=gettext_lazy("e.g. “Truck 2”"))
    loading_at = forms.DateTimeField(label=gettext_lazy("Loading"), required=False)
    note = forms.CharField(label=gettext_lazy("Note"), max_length=250, required=False)


def _project(request: HttpRequest, pk: int, level: int = Level.READ) -> Project:
    """Load the project of a packlist page for a user who may see its packlist (AUT-016, AUT-025).

    The packlist is part of the deployment view: crew planned in a project
    may read it. Ticking, issue and return need write access to packing *in
    this project* – from a role for all projects, or from one for assigned
    projects where the user is assigned.

    Raises:
        Http404: The project does not exist or is not visible to the user.
        PermissionDenied: The user may not do this with the packlist.
    """
    projects = Project.objects.select_related("customer", "contact", "manager", "venue_site").annotate(
        parts_exist=Exists(Project.objects.filter(parent_id=OuterRef("pk")))
    )
    project = packlist_project_for(request, pk, level, queryset=projects)
    # PRJ-048, PRJ-060: whether the project has parts comes with the same query; the packlist asks it
    # twice (link to the whole project, takeover rows) and stays within its queries (NFA-014).
    project.__dict__["has_subprojects"] = project.parent_id is None and project.parts_exist
    return project


def _packlist(project: Project, packlist_pk: int | None) -> Packlist:
    """The packlist from the address, or the project's main one."""
    if packlist_pk is None:
        return services.get_packlist(project)
    packlist = get_object_or_404(Packlist, pk=packlist_pk, project=project)
    packlist.project = project
    return packlist


def _view_options(request: HttpRequest) -> tuple[str, bool]:
    """Order of the rows and whether contents are listed (PCK-004, MAT-037); remembered for the session."""
    order = request.GET.get("order") or request.POST.get("order") or ""
    if order in services.ORDERS:
        request.session["packlist_order"] = order
    else:
        order = request.session.get("packlist_order", services.ORDER_GROUPS)
        order = order if order in services.ORDERS else services.ORDER_GROUPS
    contents = request.GET.get("contents") or request.POST.get("contents") or ""
    if contents in {"0", "1"}:
        request.session["packlist_contents"] = contents == "1"
    return order, bool(request.session.get("packlist_contents", False))


def _mode(request: HttpRequest, packlist: Packlist) -> str:
    """``pack`` or ``return``; a partly issued packlist can show either (PCK-018)."""
    if packlist.status in {PacklistStatus.ISSUED, PacklistStatus.RETURNED}:
        return "return"
    if packlist.status == PacklistStatus.PARTLY_ISSUED:
        wanted = request.GET.get("mode") or request.POST.get("view_mode") or ""
        return "return" if wanted == "return" else "pack"
    return "pack"


def _context(request: HttpRequest, project: Project, packlist: Packlist) -> dict[str, Any]:
    """Everything the packlist block needs."""
    order, with_contents = _view_options(request)
    overview = services.build_overview(packlist, order=order, with_contents=with_contents)
    packlists = services.packlists_of(project)
    return {
        "project": project,
        "packlist": packlist,
        "packlists": packlists,
        "is_main": packlists[0].pk == packlist.pk,
        "overview": overview,
        "bar": overview.bar,
        "order": order,
        "with_contents": with_contents,
        "mode": _mode(request, packlist),
        "can_pack": project.packing_level >= Level.WRITE,
        # PCK-013: adding material has a financial effect – not for everybody who may pack.
        "can_add_material": project.packing_level >= Level.WRITE
        and services.may_add_material(request_rights(request), request.user, project),
        "is_fragment": bool(request.headers.get("HX-Request")),
        "tab": "packlist",
        "packlist_form": PacklistForm(),
        # LOG-001: the vehicles of the project's logistics a packing list can be loaded into.
        "vehicle_choices": list(project.vehicle_lines.select_related("item__vehicle", "supplier").order_by("position")),
        "base": _base(project, packlist),
        "defect_items": services.defect_candidates(packlist) if packlist.is_issued else [],
        # After "complete the return" was refused, the rows that stand in the
        # way are marked (PCK-023). The mark travels along with every tick.
        "highlight_open": (request.GET.get("open") or request.POST.get("open")) == "1",
        "packlist_tabs": packlist_tabs(request, project, packlists, current=packlist),
    }


@dataclass
class PacklistTab:
    """One sub-tab above a packlist: a packlist of the project, another part, or all parts together (PCK-030)."""

    label: str
    url: str
    current: bool = False
    #: The packlist the tab opens, for its status badge; none for other parts and for all parts together.
    packlist: Packlist | None = None


def packlist_tabs(
    request: HttpRequest, project: Project, packlists: list[Packlist], *, current: Packlist | None
) -> list[PacklistTab]:
    """The sub-tabs of the packlist page (PCK-008, PCK-030).

    A project on its own has one tab per packlist. A whole project and its
    parts show the whole family, in the order of their numbers: the
    project being looked at with a tab per packlist, every other part (and
    the whole project) with one tab that opens its packlist, and "all
    together" – the packlist of the whole project with all its parts
    (PRJ-048). Parts whose packlist the user may not see are left out
    (PRJ-049). ``current`` is ``None`` on the page of all parts together.
    """
    own = [
        PacklistTab(
            label=(str(_("Packing list")) if index == 0 and not packlist.title else packlist.label),
            url=(
                reverse("packing:packlist_detail", args=[project.pk, packlist.pk])
                if index
                else reverse("packing:packlist", args=[project.pk])
            ),
            current=current is not None and packlist.pk == current.pk,
            packlist=packlist,
        )
        for index, packlist in enumerate(packlists)
    ]
    if not project.is_in_family:
        return own
    rights = request_rights(request)
    family = members(project)
    whole = family[0]
    tabs: list[PacklistTab] = []
    for member in family:
        if member.pk == project.pk:
            for tab in own:
                tab.label = member.name if len(own) == 1 else f"{member.name}: {tab.label}"
            tabs += own
        elif subprojects.packing_level_in(rights, request.user, member) >= Level.READ:
            tabs.append(PacklistTab(label=member.name, url=reverse("packing:packlist", args=[member.pk])))
    if subprojects.packing_level_in(rights, request.user, whole) >= Level.READ:
        tabs.append(
            PacklistTab(
                label=str(_("All parts together")),
                url=reverse("packing:family", args=[whole.pk]),
                current=current is None,
            )
        )
    return tabs


def _base(project: Project, packlist: Packlist) -> str:
    """The address of a packlist; the main one keeps its short address."""
    if services.is_main(packlist):
        return reverse("packing:packlist", args=[project.pk])
    return reverse("packing:packlist_detail", args=[project.pk, packlist.pk])


@module_required(Module.PACKING)
def packlist(request: HttpRequest, pk: int, packlist_pk: int | None = None) -> HttpResponse:
    """A packlist of a project: tick while packing, issue, tick the return (PCK-009, PCK-016)."""
    project = _project(request, pk)
    current = _packlist(project, packlist_pk)
    template = "packing/_packlist.html" if request.headers.get("HX-Request") else "packing/packlist.html"
    return render(request, template, _context(request, project, current))


@module_required(Module.PACKING)
def packlist_pdf(request: HttpRequest, pk: int, packlist_pk: int | None = None) -> HttpResponse:
    """The packlist as a printable PDF with boxes to tick (PCK-003), in the chosen order (PCK-004)."""
    project = _project(request, pk)
    current = _packlist(project, packlist_pk)
    order, with_contents = _view_options(request)
    overview = services.build_overview(current, order=order, with_contents=with_contents)
    # PRJ-122: the customer's name in every role.
    pdf = render_packlist_pdf(overview, show_customer=project.shows_customer)
    response = HttpResponse(pdf, content_type="application/pdf")
    suffix = f"-{current.pk}" if not services.is_main(current) else ""
    response["Content-Disposition"] = f'inline; filename="{packing_list_name(project, suffix)}"'
    return response


def _family_view(request: HttpRequest) -> str:
    """Part by part or summed up per article (PRJ-048); remembered for the session."""
    view = request.GET.get("view") or ""
    if view in subprojects.VIEWS:
        request.session["packlist_family_view"] = view
        return view
    view = request.session.get("packlist_family_view", subprojects.VIEW_PARTS)
    return view if view in subprojects.VIEWS else subprojects.VIEW_PARTS


@module_required(Module.PACKING)
def family_packlist(request: HttpRequest, pk: int) -> HttpResponse:
    """The packlist of a whole project with all its parts, read-only (PRJ-048).

    Packing, issue and return stay on the packlist of each part; this page
    shows them together, part by part or summed up per article, with the
    progress of every part. Parts whose packlist the user may not see are
    left out, and the page says how many (PRJ-049). Opened for a part, it
    shows the part's whole project.
    """
    project = _project(request, pk)
    if project.parent_id:
        return redirect("packing:family", pk=project.parent_id)
    family = subprojects.build_family_packlist(project, rights=request_rights(request), user=request.user)
    return render(
        request,
        "packing/family.html",
        {
            "project": project,
            "family": family,
            "view": _family_view(request),
            "tab": "packlist",
            # PCK-030: the parts as sub-tabs, as on every packlist of the family.
            "packlist_tabs": packlist_tabs(request, project, services.packlists_of(project), current=None),
        },
    )


@module_required(Module.PACKING)
def family_packlist_pdf(request: HttpRequest, pk: int) -> HttpResponse:
    """The packlist of the whole project with all its parts as a PDF to print (PRJ-048, PCK-003)."""
    project = _project(request, pk)
    if project.parent_id:
        return redirect("packing:family_pdf", pk=project.parent_id)
    family = subprojects.build_family_packlist(project, rights=request_rights(request), user=request.user)
    # PRJ-122: the customer's name in every role.
    pdf = render_family_pdf(family, view=_family_view(request), show_customer=project.shows_customer)
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{packing_list_name(project, whole=True)}"'
    return response


@require_POST
@module_required(Module.PACKING, Level.WRITE)
def packlist_row(request: HttpRequest, pk: int, packlist_pk: int | None = None) -> HttpResponse:
    """Tick one row as packed or returned, with one tap or with a typed quantity (PCK-009, PCK-012)."""
    project = _project(request, pk, Level.WRITE)
    current = _packlist(project, packlist_pk)
    try:
        line_id = int(request.POST.get("line", ""))
        product_id = int(request.POST.get("product", ""))
        quantity = Decimal(request.POST.get("quantity", "0").replace(",", ".") or "0")
        if request.POST.get("mode") == "return":
            services.set_returned(current, line_id, product_id, quantity, user=request.user)
        else:
            services.set_packed(current, line_id, product_id, quantity, user=request.user)
    except (ValueError, InvalidOperation):
        messages.error(request, _("Enter a number."))
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    current.refresh_from_db()
    return render(request, "packing/_packlist.html", {**_context(request, project, current), "is_fragment": True})


@module_required(Module.PACKING, Level.WRITE)
def packlist_items(request: HttpRequest, pk: int, packlist_pk: int | None = None) -> HttpResponse:
    """The items one may choose for a row, as a dialog (PCK-022)."""
    project = _project(request, pk, Level.WRITE)
    current = _packlist(project, packlist_pk)
    overview = services.build_overview(current)
    try:
        row = services.find_row(overview, int(request.GET.get("line", "0")), int(request.GET.get("product", "0")))
    except (ValueError, ValidationError):
        return HttpResponse(status=404)
    chosen = {item.item_id for item in row.chosen}
    choices = [(item, note, free, item.pk in chosen) for item, note, free in services.item_choices(current, row)]
    return render(
        request,
        "packing/_item_chooser.html",
        {"project": project, "packlist": current, "row": row, "choices": choices, "base": _base(project, current)},
    )


#: The steps of :func:`packlist_action`; the others are reserved for forms of their own.
_REDIRECTING = {
    "issue",
    "issue-rest",
    "take-back",
    "complete-return",
    "undo-issue",
    "delete",
    "report-defect",
    "add-material",
}


@require_POST
@module_required(Module.PACKING, Level.WRITE)
def packlist_action(request: HttpRequest, pk: int, action: str, packlist_pk: int | None = None) -> HttpResponse:
    """Run one step: tick all, issue, take back, return all, clarify, complete, choose items, add (PCK-013 ff.)."""
    project = _project(request, pk, Level.WRITE)
    current = _packlist(project, packlist_pk)
    base = _base(project, current)
    try:
        base = _run_action(request, project, current, action) or base
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    if action == "delete" and not Packlist.objects.filter(pk=current.pk).exists():
        return redirect("packing:packlist", pk=project.pk)
    current.refresh_from_db()
    if action == "complete-return" and current.status in OUT_STATUSES:
        # Refused: show the packlist with the rows that are not back marked.
        return redirect(base + "?open=1&mode=return")
    if action == "take-back" and current.status == PacklistStatus.PARTLY_ISSUED:
        return redirect(base + "?mode=return")  # PCK-028: stay with the return
    if action == "scan" and not request.headers.get("HX-Request"):
        return redirect(
            f"{base}?mode={'return' if request.POST.get('mode') == 'return' else 'pack'}"
        )  # without scripts
    if action in _REDIRECTING or not request.headers.get("HX-Request"):
        return redirect(base)
    context = {**_context(request, project, current), "is_fragment": True}
    outcome = getattr(request, "scan_outcome", None)
    context["scan_row"] = outcome.row if outcome else ""  # The row a scan changed or meant
    response = render(request, "packing/_packlist.html", context)
    if outcome:
        # The scan dialog lies over the list: it says what happened (static/js/scan.js). ASCII-only JSON for the header.
        answer = {"level": outcome.level, "message": " ".join([outcome.message, *outcome.warnings])}
        response["HX-Trigger"] = json.dumps({"scanResult": answer})
    return response


def _run_action(request: HttpRequest, project: Project, current: Packlist, action: str) -> str | None:
    """Carry out one packlist step; may return another address to go to."""
    post = request.POST
    if action == "pack-all":
        services.pack_all(current, user=request.user)
    elif action in {"issue", "issue-rest"}:
        # PCK-025: "issue" books what is ticked; "issue everything" sends only_packed=0.
        hints = services.issue(current, user=request.user, only_packed=post.get("only_packed", "1") != "0")
        current.refresh_from_db()
        project.refresh_from_db(fields=["status"])
        if current.status == PacklistStatus.PARTLY_ISSUED:
            messages.success(request, _("The ticked material is issued; the rest can follow."))
        elif project.status == ProjectStatus.OUT:
            messages.success(request, _("The material is issued. The project is now “out”."))
        else:
            messages.success(
                request,
                _("The material of this packing list is issued. The project becomes “out” once everything is issued."),
            )
        for hint in hints:
            messages.warning(request, hint)
    elif action == "undo-issue":
        services.undo_issue(current)
        messages.success(request, _("The issue was taken back."))
    elif action == "return-all":
        services.return_all(current, user=request.user)
    elif action == "take-back":
        # PCK-028: book what is ticked as back; once nothing is out and nothing waits, the return is complete.
        booked = services.take_back(current, user=request.user)
        current.refresh_from_db()
        if current.status == PacklistStatus.RETURNED:
            messages.success(request, _("Everything is back. The return is complete."))
        else:
            messages.success(
                request,
                ngettext("%(count)s piece is taken back.", "%(count)s pieces are taken back.", int(booked))
                % {"count": services._number(booked)},
            )
    elif action == "resolve-missing":
        hint = services.resolve_missing(
            current, int(post.get("line", "0")), int(post.get("product", "0")), post.get("note", ""), user=request.user
        )
        if hint:
            messages.warning(request, hint)
    elif action == "complete-return":
        services.complete_return(current, user=request.user)
        messages.success(request, _("The return is complete."))
    elif action == "acknowledge-changes":
        services.acknowledge_changes(current, user=request.user)
    elif action == "choose-items":
        warnings = services.choose_items(
            current,
            int(post.get("line", "0")),
            int(post.get("product", "0")),
            [int(value) for value in post.getlist("items") if value.isdigit()],
            user=request.user,
        )
        for warning in warnings:
            messages.warning(request, warning)
    elif action == "scan":
        _scan(request, current)
    elif action == "add-material":
        _add_material(request, current)
    elif action == "handover":
        _hand_over(request, current)
    elif action == "undo-handover":
        handover = Handover.objects.filter(pk=_int(post.get("handover")), target__packlist=current).first()
        if handover is None:
            raise ValidationError(_("This handover does not exist (any more)."))
        subprojects.undo_handover(handover, user=request.user, rights=request_rights(request))
        messages.success(request, _("The handover was taken back."))
    elif action == "report-defect":
        _report_defect(request, current)
    elif action == "edit":
        form = PacklistForm(post)
        if not form.is_valid():
            raise ValidationError(" ".join(message for errors in form.errors.values() for message in errors))
        services.update_packlist(current, **form.cleaned_data)
    elif action == "vehicle":
        # LOG-001: the vehicle of the logistics this list is loaded into – for every packing list.
        chosen = _int(post.get("vehicle_line"))
        vehicle_line = current.project.vehicle_lines.filter(pk=chosen).first() if chosen else None
        services.update_packlist(current, vehicle_line=vehicle_line)
    elif action == "delete":
        services.delete_packlist(current)
        messages.success(request, _("The packing list was deleted; its lines are on the first packing list again."))
    else:
        messages.error(request, _("Unknown packing step."))
    return None


def _scan(request: HttpRequest, current: Packlist) -> None:
    """PCK-010, PCK-011, PCK-016: an item scanned or typed – pack it or count it back, and say what happened."""
    from rentalars.packing import scan

    code = request.POST.get("code", "")
    if request.POST.get("mode") == "return":
        outcome = scan.scan_return(current, code, user=request.user, rights=request_rights(request))
    else:
        outcome = scan.scan_pack(current, code, user=request.user, rights=request_rights(request))
    request.scan_outcome = outcome  # type: ignore[attr-defined]
    show = {scan.SUCCESS: messages.success, scan.WARNING: messages.warning}.get(outcome.level, messages.error)
    show(request, outcome.message)
    for warning in outcome.warnings:
        messages.warning(request, warning)


def _add_material(request: HttpRequest, current: Packlist) -> None:
    """PCK-013: a product and a quantity from the form, as an addendum."""
    from rentalars.products.models import Product

    try:
        product = Product.objects.get(pk=int(request.POST.get("product", "0")))
        quantity = Decimal(request.POST.get("quantity", "1").replace(",", ".") or "1")
    except (ValueError, InvalidOperation, Product.DoesNotExist) as error:
        raise ValidationError(_("Choose a product and a quantity.")) from error
    warnings = services.add_material(current, product, quantity, user=request.user, rights=request_rights(request))
    messages.success(request, _("%(product)s added as addendum.") % {"product": product.article_number})
    for warning in warnings:
        messages.warning(request, warning)


def _int(value: Any) -> int:
    """A whole number from the form; 0 if there is none."""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _hand_over(request: HttpRequest, current: Packlist) -> None:
    """PRJ-060: pieces taken over from another subproject arrived – all expected ones, or as many as typed."""
    raw = (request.POST.get("quantity") or "").replace(",", ".").strip()
    try:
        quantity = Decimal(raw) if raw else None
    except InvalidOperation as error:
        raise ValidationError(_("Enter a number.")) from error
    handover = subprojects.hand_over(
        current,
        _int(request.POST.get("line")),
        _int(request.POST.get("product")),
        quantity,
        user=request.user,
        rights=request_rights(request),
    )
    messages.success(
        request,
        _("%(quantity)s × %(product)s from %(project)s handed over.")
        % {
            "quantity": services._number(handover.quantity),
            "product": handover.target.product.article_number,
            "project": handover.source.packlist.project.number,
        },
    )


def _report_defect(request: HttpRequest, current: Packlist) -> None:
    """PCK-017: the ID of the item, what is wrong, a photo."""
    from rentalars.material.services import find_item_by_code

    item = find_item_by_code(request.POST.get("item", "").strip())
    if item is None:
        raise ValidationError(_("No item with this ID."))
    services.report_return_defect(
        current, item, request.POST.get("description", ""), photo=request.FILES.get("photo"), user=request.user
    )
    messages.success(request, _("Defect of %(id)s reported. The warehouse was told.") % {"id": item.display_id})


@require_POST
@module_required(Module.PACKING, Level.WRITE)
def packlist_create(request: HttpRequest, pk: int) -> HttpResponse:
    """Add a packlist to the project (PCK-008); the lines are given to it afterwards."""
    project = _project(request, pk, Level.WRITE)
    form = PacklistForm(request.POST)
    if not form.is_valid():
        messages.error(request, " ".join(message for errors in form.errors.values() for message in errors))
        return redirect("packing:packlist", pk=project.pk)
    try:
        created = services.create_packlist(project, **form.cleaned_data)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect("packing:packlist", pk=project.pk)
    messages.success(request, _("Packing list “%(title)s” created. Now give it its lines.") % {"title": created.title})
    return redirect("packing:packlist_lines", pk=project.pk)


@module_required(Module.PACKING, Level.WRITE)
def packlist_lines(request: HttpRequest, pk: int) -> HttpResponse:
    """Distribute the lines of a project among its packlists (PCK-008)."""
    project = _project(request, pk, Level.WRITE)
    packlists = services.packlists_of(project)
    if request.method == "POST":
        moves: dict[int, list[int]] = {}
        known = {packlist.pk: packlist for packlist in packlists}
        for name, value in request.POST.items():
            if name.startswith("line-") and value.isdigit() and int(value) in known:
                moves.setdefault(int(value), []).append(int(name.removeprefix("line-")))
        try:
            moved = sum(services.assign_lines(known[target], ids, user=request.user) for target, ids in moves.items())
        except (ValueError, ValidationError) as error:
            messages.error(request, " ".join(getattr(error, "messages", [str(error)])))
        else:
            messages.success(
                request, ngettext("%(count)d line moved.", "%(count)d lines moved.", moved) % {"count": moved}
            )
            return redirect("packing:packlist", pk=project.pk)
    lines = []
    # PRJ-037: in the order of the planning, a subgroup after its parent, named with its path.
    tree = GroupTree(project.groups.all())
    for line in sorted(
        project.material_lines.filter(product__isnull=False).select_related("product"),
        key=lambda line: (tree.index.get(line.group_id, -1), line.position, line.pk),
    ):
        if line.product.kind in services.PACKABLE_KINDS:
            line.group = tree.by_id.get(line.group_id) if line.group_id else None
            lines.append((line, services.packlist_of_line(line)))
    return render(
        request,
        "packing/packlist_lines.html",
        {"project": project, "packlists": packlists, "lines": lines, "tab": "packlist"},
    )


# --- Taking loose contents out for a project (MAT-042) ------------------------------------------


@require_POST
@module_required(Module.PACKING, Level.WRITE)
def extract(request: HttpRequest, item_pk: int) -> HttpResponse:
    """Take a loose item out of its container for a project (MAT-042)."""
    from rentalars.material.models import MaterialItem

    item = get_object_or_404(MaterialItem.objects.select_related("installed_in", "material_model"), pk=item_pk)
    try:
        project = _project(request, int(request.POST.get("project", "0")), Level.WRITE)
        services.extract(project, item, user=request.user)
    except ValueError:
        messages.error(request, _("Choose a project."))
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(
            request,
            _("%(item)s stays behind for %(project)s and is free for others meanwhile.")
            % {"item": item.display_id, "project": project.number},
        )
    return redirect("material:item_detail", pk=item.pk)


@require_POST
@module_required(Module.PACKING, Level.WRITE)
def extraction_cancel(request: HttpRequest, pk: int) -> HttpResponse:
    """The item travels with its container again (MAT-042)."""
    extraction = get_object_or_404(Extraction.objects.select_related("item"), pk=pk)
    _project(request, extraction.project_id, Level.WRITE)
    services.cancel_extraction(extraction)
    messages.success(request, _("%(item)s travels with its container again.") % {"item": extraction.item.display_id})
    from rentalars.material.item_views import safe_next

    return redirect(safe_next(request, reverse("material:item_detail", args=[extraction.item_id])))
