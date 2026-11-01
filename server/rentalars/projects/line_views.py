# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views for lines of the planning (PRJ-072, PRJ-075, PRJ-082, PRJ-083).

Like the other requests of the planning page they answer with the refreshed
planning (see ``views._planning_response``) and call the same services as the
API (API-002).

Lines can be chosen on the planning and changed together
(:func:`lines_bulk`, PRJ-082), and every line has buttons "optional" and
"Alternative" next to edit, copy and delete (PRJ-083): "optional" sends the
same request as the choice for several lines, "Alternative" opens the dialog
of :func:`lines_alternative`, which asks for the line it could replace.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, QueryDict
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, SpecialRight, module_required, request_rights
from rentalars.core.i18n import plural_of
from rentalars.core.money import format_decimal
from rentalars.projects.access import ProjectAccess, project_for
from rentalars.projects.forms import LineAlternativeForm, TextLineForm
from rentalars.projects.lines import BulkAction, BulkResult, change_lines, duplicate_line, line_label
from rentalars.projects.models import Project
from rentalars.projects.price_updates import shows_price_hint
from rentalars.projects.product_changes import take_over_changes
from rentalars.projects.services import add_text_line
from rentalars.projects.views import Touched, _error_text, _planning_response


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def line_duplicate(request: HttpRequest, pk: int, line_pk: int) -> HttpResponse:
    """Put a copy of a line right below it (PRJ-075)."""
    project = project_for(request, pk, ProjectAccess.EDIT)
    line = get_object_or_404(project.material_lines.select_related("product", "covers_line"), pk=line_pk)
    touched = Touched()
    try:
        result = duplicate_line(line, rights=request_rights(request))
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        touched.add(result.line)
        if result.availability.status == "short" and request_rights(request).has(SpecialRight.AVAILABILITY):
            # PRJ-013: saved all the same, but with a clear warning. AUT-032: for who may see availability.
            messages.warning(
                request,
                ngettext(
                    "%(title)s was added, but %(count)d piece is missing in this period.",
                    "%(title)s was added, but %(count)d pieces are missing in this period.",
                    plural_of(result.availability.shortage_total),
                )
                % {"title": result.line.title, "count": result.availability.shortage_total},
            )
    return _planning_response(request, project, touched=touched)


@module_required(Module.PROJECTS, Level.WRITE)
def text_line_add(request: HttpRequest, pk: int) -> HttpResponse:
    """Add a text line – a heading or a remark without product, quantity and price – in a dialog.

    ``?group=<id>`` offers that group; the line goes to the end of the chosen group. It is printed on offers,
    order confirmations, invoices and the price overview as a row of text (see ``MaterialLine.is_text``).
    """
    project = project_for(request, pk, ProjectAccess.EDIT)
    initial = {}
    wanted = request.GET.get("group", "")
    if wanted.isascii() and wanted.isdigit() and project.groups.filter(pk=int(wanted)).exists():
        initial["group"] = int(wanted)
    form = TextLineForm(request.POST or None, project=project, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            result = add_text_line(
                project,
                title=form.cleaned_data["title"],
                note=form.cleaned_data["note"],
                group=form.cleaned_data["group"],
            )
        except ValidationError as error:
            form.add_error(None, _error_text(error))
        else:
            touched = Touched()
            touched.add(result.line)
            return _planning_response(request, project, close_dialog=True, touched=touched)
    return render(
        request,
        "projects/_dialog_form.html",
        {"form": form, "title": _("Insert text line"), "action": request.path, "submit_label": _("Insert text")},
    )


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def changes_update(request: HttpRequest, pk: int) -> HttpResponse:
    """Take over what the products changed since the lines took it over, or keep the own values (PRJ-072).

    The form sends ``scope=automatic`` (every line without a value set by hand), ``take_over`` with the keys of
    single lines, or ``keep``. Prices come along only for who has the price right.
    """
    project = project_for(request, pk, ProjectAccess.EDIT)
    if not shows_price_hint(project):
        # A page opened before the project was confirmed: what was agreed stays agreed (PRJ-015).
        messages.error(request, _("This project is confirmed; its lines keep the values that were agreed."))
        return _planning_response(request, project)
    try:
        result = take_over_changes(
            project,
            rights=request_rights(request),
            keys=request.POST.getlist("take_over"),
            automatic=request.POST.get("scope") == "automatic",
            keep=request.POST.getlist("keep"),
        )
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        if result.taken_over:
            messages.success(
                request,
                ngettext(
                    "%(count)d line now has the current values of its product.",
                    "%(count)d lines now have the current values of their products.",
                    result.taken_over,
                )
                % {"count": result.taken_over},
            )
        if result.kept:
            messages.success(
                request,
                ngettext("%(count)d line keeps its own values.", "%(count)d lines keep their own values.", result.kept)
                % {"count": result.kept},
            )
    return _planning_response(request, project)


# --- Several lines at once (PRJ-082) and alternatives (PRJ-083) --------------------------------


def _is_number(text: str) -> bool:
    """Whether the text is a whole number of ASCII digits (``"²".isdigit()`` is true, ``int("²")`` fails)."""
    return text.isascii() and text.isdigit()


def chosen_line_ids(data: QueryDict) -> list[int]:
    """The IDs of the lines a request names in ``lines`` (one value per line)."""
    return [int(value) for value in data.getlist("lines") if _is_number(str(value).strip())]


def _bulk_values(data: QueryDict, project: Project, action: str) -> dict[str, Any]:
    """What an action needs besides the lines: the line to replace, the group, the discount."""
    values: dict[str, Any] = {}
    if action == BulkAction.ALTERNATIVE:
        target = data.get("alternative_to", "")
        values["alternative_to"] = project.material_lines.filter(pk=int(target)).first() if _is_number(target) else None
    if action == BulkAction.MOVE:
        # "none" is "without group"; nothing chosen is a mistake, not "without group".
        target = data.get("group", "").strip()
        values["group"] = project.groups.filter(pk=int(target)).first() if _is_number(target) else None
        if target != "none" and values["group"] is None:
            raise ValidationError(_("Choose the group the lines go to."))
    if action == BulkAction.DISCOUNT:
        text = (data.get("discount_percent") or "").strip().replace(",", ".")
        try:
            values["discount_percent"] = Decimal(text) if text else None
        except InvalidOperation as error:
            raise ValidationError(_("“%(value)s” is not a number.") % {"value": text}) from error
    return values


def _success_text(result: BulkResult, count: int) -> str:
    """The message about the lines changed, in the words of the action."""
    action = result.action
    if action == BulkAction.OPTIONAL:
        return ngettext("%(count)d line is now optional.", "%(count)d lines are now optional.", count) % {
            "count": count
        }
    if action == BulkAction.NORMAL:
        return ngettext("%(count)d line counts again.", "%(count)d lines count again.", count) % {"count": count}
    if action == BulkAction.ALTERNATIVE:
        target = result.changed[0].alternative_to
        return ngettext(
            "%(count)d line is now an alternative to “%(line)s”.",
            "%(count)d lines are now an alternative to “%(line)s”.",
            count,
        ) % {"count": count, "line": line_label(target) if target else ""}
    if action == BulkAction.MOVE:
        group = result.changed[0].group
        return ngettext("%(count)d line moved to “%(group)s”.", "%(count)d lines moved to “%(group)s”.", count) % {
            "count": count,
            "group": group.path if group else _("Without group"),
        }
    if action == BulkAction.DISCOUNT:
        return ngettext(
            "%(count)d line now has a discount of %(percent)s %%.",
            "%(count)d lines now have a discount of %(percent)s %%.",
            count,
        ) % {"count": count, "percent": format_decimal(result.changed[0].discount_percent)}
    return ngettext("%(count)d line deleted.", "%(count)d lines deleted.", count) % {"count": count}


def report_bulk_result(request: HttpRequest, result: BulkResult) -> None:
    """Tell what was done, and name every line that was left as it was, with the reason (PRJ-082)."""
    if result.changed:
        messages.success(request, _success_text(result, len(result.changed)))
    elif not result.skipped:
        messages.info(request, _("Nothing to change: the chosen lines are like that already."))
    for warning in result.warnings:
        messages.warning(request, warning)  # A discount above the maximum of some lines
    if result.skipped:
        messages.warning(
            request,
            _("Left as they are: %(lines)s")
            % {"lines": "; ".join(f"{skipped.label} ({skipped.reason})" for skipped in result.skipped)},
        )


def _touched_by(result: BulkResult) -> Touched:
    """The parts of the planning the change can show differently: the groups and products of the lines."""
    touched = Touched()
    touched.group_ids.update(result.group_ids)
    touched.product_ids.update(result.product_ids)
    return touched


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def lines_bulk(request: HttpRequest, pk: int) -> HttpResponse:
    """Do one thing with the lines chosen on the planning (PRJ-082).

    The form sends ``lines`` (one value per line), ``action`` – ``optional``,
    ``normal``, ``alternative``, ``move``, ``discount`` or ``delete`` – and
    what the action needs: ``alternative_to``, ``group`` (``none``: without
    group) or ``discount_percent``. The buttons "optional" of single lines
    (PRJ-083) send the same with one line. One request, one refreshed
    planning; lines the action cannot be done with are named with the reason.
    """
    project = project_for(request, pk, ProjectAccess.EDIT)
    action = request.POST.get("action", "")
    touched = Touched()
    try:
        values = _bulk_values(request.POST, project, action)
        result = change_lines(project, chosen_line_ids(request.POST), action, rights=request_rights(request), **values)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        touched = _touched_by(result)
        report_bulk_result(request, result)
    return _planning_response(request, project, touched=touched)


@module_required(Module.PROJECTS, Level.WRITE)
def lines_alternative(request: HttpRequest, pk: int) -> HttpResponse:
    """The dialog "Alternative to …" for one line or for the lines chosen on the planning (PRJ-083, PRJ-082).

    ``lines`` names the lines (in the address when the dialog is opened, in
    the form when it is sent). The dialog offers the other lines of the
    project, in the order of the planning, and the choice is required.
    """
    project = project_for(request, pk, ProjectAccess.EDIT)
    data = request.POST if request.method == "POST" else request.GET
    lines = list(project.material_lines.filter(pk__in=chosen_line_ids(data)).order_by("position", "id"))
    if not lines:
        messages.error(request, _("Choose at least one line."))
        return _planning_response(request, project, touched=Touched())
    form = LineAlternativeForm(request.POST or None, project=project, lines=lines)
    if request.method == "POST" and form.is_valid():
        try:
            result = change_lines(
                project,
                [line.pk for line in lines],
                BulkAction.ALTERNATIVE,
                rights=request_rights(request),
                alternative_to=form.cleaned_data["alternative_to"],
            )
        except ValidationError as error:
            form.add_error(None, _error_text(error))
        else:
            report_bulk_result(request, result)
            return _planning_response(request, project, close_dialog=True, touched=_touched_by(result))
    return render(
        request,
        "projects/_line_alternative.html",
        {"form": form, "lines": lines, "labels": [line_label(line) for line in lines], "action": request.path},
    )
