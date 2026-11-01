# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser view for taking over a lighting plot from an MVR file into a project (PRJ-077, PRJ-086).

One page, two steps:

1. **Upload** the MVR file. It is read at once (``projects.mvr.read_plot``);
   the counted fixture types wait in the session. The file is
   kept in the files of the project as ``yyyymmdd-hhmmss_<name>.mvr``
   (``projects.mvr.keep_file``, PRJ-086); "Choose another file" removes it
   again. A file larger than files of projects may be is not kept – the
   import goes on, and a message says so.
2. **Assign** a product to every fixture type – the suggestions of
   ``projects.mvr.suggest`` are preselected – choose the group, and add the
   lines (``projects.mvr.take_over``). The planning page then shows them.

The page needs the same rights as adding a line on the planning page: write
access to projects and the right to edit this project (AUT-016, AUT-025).
The API offers the same at ``/api/v1/projects/{id}/mvr`` (``mvr_api``).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext

from rentalars.accounts.rights import Level, Module, module_required, request_rights
from rentalars.products.models import Product
from rentalars.projects import mvr
from rentalars.projects.access import ProjectAccess, project_for
from rentalars.projects.files import delete_file
from rentalars.projects.grouptree import GroupTree
from rentalars.projects.models import Project

#: What the group selection sends for "a new group".
NEW_GROUP = "new"


class MvrUploadForm(forms.Form):
    """Step 1: the MVR file."""

    file = forms.FileField(
        label=gettext_lazy("MVR file"),
        widget=forms.ClearableFileInput(attrs={"accept": ".mvr"}),
        help_text=gettext_lazy("Exported from Vectorworks, grandMA3, Capture, WYSIWYG and other programs."),
    )


def validate_mvr_upload(uploaded: Any) -> None:
    """Accept only files ending in ``.mvr`` up to :data:`mvr.MAX_UPLOAD_BYTES` (PRJ-077, NFA-007).

    Raises:
        ValidationError: Wrong type or too large.
    """
    if Path(getattr(uploaded, "name", "") or "").suffix.lower() != ".mvr":
        raise ValidationError(_("Choose a file ending in .mvr."), code="invalid_mvr")
    if (getattr(uploaded, "size", 0) or 0) > mvr.MAX_UPLOAD_BYTES:
        raise ValidationError(
            _("The file is too large (at most %(megabytes)d MB).") % {"megabytes": mvr.MAX_UPLOAD_BYTES >> 20},
            code="invalid_mvr",
        )


def _session_key(project: Project) -> str:
    return f"mvr_plot_{project.pk}"


def _file_key(project: Project) -> str:
    """Where the session remembers the file kept by the import that is going on (PRJ-086)."""
    return f"mvr_file_{project.pk}"


def _keep(request: HttpRequest, project: Project, uploaded: Any) -> None:
    """Keep the uploaded file in the files of the project; a file that cannot be kept stops nothing (PRJ-086)."""
    try:
        kept = mvr.keep_file(project, uploaded, user=request.user)
    except ValidationError as error:
        request.session.pop(_file_key(project), None)
        messages.warning(
            request,
            _("The MVR file was not kept in the files of the project: %(reason)s")
            % {"reason": " ".join(error.messages)},
        )
    else:
        request.session[_file_key(project)] = kept.pk


def _forget_kept_file(request: HttpRequest, project: Project) -> None:
    """On "Choose another file" the file of this import leaves the files of the project again (PRJ-086)."""
    file_id = request.session.pop(_file_key(project), None)
    kept = project.files.filter(pk=file_id).first() if file_id else None
    if kept is not None:
        delete_file(kept)


def _quantity(text: str, default: int) -> Decimal:
    try:
        quantity = Decimal((text or str(default)).replace(",", ".").strip())
    except InvalidOperation as error:
        raise ValidationError(_("“%(value)s” is not a number.") % {"value": text}) from error
    if quantity <= 0 or not quantity.is_finite():
        raise ValidationError(_("The quantity must be more than 0."))
    return quantity


def _rows(plot: mvr.Plot, data: Any | None) -> list[dict[str, Any]]:
    """One row per fixture type for the template, with the suggestions and what is chosen.

    Without ``data`` (the first showing) the preselected suggestion is
    chosen, or "skip" where nothing fits; with ``data`` (the form came back
    with an error) what was sent.
    """
    suggestions = mvr.suggest(plot.types)
    rows = []
    for index, fixture_type in enumerate(plot.types):
        offered = suggestions.get(fixture_type.key, [])
        preselected = mvr.preselection(offered)
        row: dict[str, Any] = {
            "index": index,
            "type": fixture_type,
            "suggestions": offered,
            "selected": str(preselected.product_id) if preselected else "skip",
            "quantity": fixture_type.count,
            "other_value": "",
            "other_label": "",
        }
        if data is not None:
            row["selected"] = data.get(f"choice_{index}", "skip")
            row["quantity"] = data.get(f"quantity_{index}", fixture_type.count)
            row["other_value"] = data.get(f"other_{index}", "")
            row["other_label"] = data.get(f"other_{index}_label", "")
        rows.append(row)
    return rows


def read_choices(plot: mvr.Plot, data: Any) -> tuple[dict[str, mvr.Choice], list[str]]:
    """The products and quantities chosen on the page; every problem as a message.

    Fields per type ``n``: ``key_n`` (the type the row was made for),
    ``choice_n`` (a product ID, ``other`` or ``skip``), ``other_n`` (the
    product found by the search field) and ``quantity_n``.
    """
    choices: dict[str, mvr.Choice] = {}
    problems: list[str] = []
    for index, fixture_type in enumerate(plot.types):
        if data.get(f"key_{index}") != fixture_type.key:
            return {}, [_("The page does not match the plot any more. Please choose the file again.")]
        choice = data.get(f"choice_{index}", "skip")
        if choice == "skip":
            continue
        product_id = data.get(f"other_{index}", "") if choice == "other" else choice
        product = Product.objects.filter(pk=int(product_id)).first() if str(product_id).isdigit() else None
        if product is None:
            problems.append(_("Choose a product for %(type)s, or do not take it over.") % {"type": fixture_type.label})
            continue
        try:
            quantity = _quantity(str(data.get(f"quantity_{index}", "")), fixture_type.count)
        except ValidationError as error:
            problems.append(f"{fixture_type.label}: {' '.join(error.messages)}")
            continue
        choices[fixture_type.key] = mvr.Choice(product=product, quantity=quantity)
    return choices, problems


@module_required(Module.PROJECTS, Level.WRITE)
def mvr_import(request: HttpRequest, pk: int) -> HttpResponse:
    """Take over a lighting plot from an MVR file into the project (PRJ-077)."""
    project = project_for(request, pk, ProjectAccess.EDIT)
    if project.is_locked:
        messages.error(request, _("This project is closed. Reopen it before making changes."))
        return redirect("projects:detail", pk=project.pk)
    key = _session_key(project)
    step = request.POST.get("step", "") if request.method == "POST" else ""
    context: dict[str, Any] = {"project": project, "tab": "planning"}

    if step == "upload":
        form = MvrUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded = form.cleaned_data["file"]
            try:
                validate_mvr_upload(uploaded)
                plot = mvr.read_plot(uploaded, uploaded.name)
            except ValidationError as error:
                form.add_error("file", error)
            else:
                request.session[key] = plot.as_dict()
                _keep(request, project, uploaded)
                return redirect("projects:mvr_import", pk=project.pk)
        return render(request, "projects/mvr_import.html", {**context, "upload_form": form})
    if step == "discard":
        request.session.pop(key, None)
        _forget_kept_file(request, project)
        return redirect("projects:mvr_import", pk=project.pk)

    stored = request.session.get(key)
    if not stored:
        return render(request, "projects/mvr_import.html", {**context, "upload_form": MvrUploadForm()})
    plot = mvr.Plot.from_dict(stored)
    # PRJ-037: also into a subgroup – offered in the order of the planning, named with their path.
    groups = GroupTree(project.groups.all()).ordered
    group_choice = request.POST.get("group", NEW_GROUP) if step == "apply" else NEW_GROUP
    group_name = request.POST.get("group_name", "") if step == "apply" else mvr.default_group_name(plot.file_name)

    if step == "apply":
        choices, problems = read_choices(plot, request.POST)
        group = next((group for group in groups if str(group.pk) == group_choice), None)
        if group_choice not in {NEW_GROUP, ""} and group is None:
            problems.append(_("Choose one of the groups of this project."))
        if group_choice == NEW_GROUP and not group_name.strip():
            problems.append(_("Give the group a name."))
        if not problems:
            try:
                result = mvr.take_over(
                    project,
                    plot,
                    choices,
                    rights=request_rights(request),
                    group=group,
                    new_group_name=group_name if group_choice == NEW_GROUP else "",
                )
            except ValidationError as error:
                problems.extend(error.messages)
            else:
                request.session.pop(key, None)
                count = len(result.lines)
                messages.success(
                    request,
                    ngettext("%(count)d line from %(file)s added.", "%(count)d lines from %(file)s added.", count)
                    % {"count": count, "file": plot.file_name},
                )
                file_id = request.session.pop(_file_key(project), None)
                kept = project.files.filter(pk=file_id).first() if file_id else None
                if kept is not None:
                    messages.info(
                        request, _("The MVR file is in the files of the project: %(name)s") % {"name": kept.label}
                    )
                for warning in result.warnings:
                    messages.warning(request, warning)
                return redirect("projects:detail", pk=project.pk)
        for problem in problems:
            messages.error(request, problem)

    context.update(
        plot=plot,
        rows=_rows(plot, request.POST if step == "apply" else None),
        groups=groups,
        group_choice=group_choice,
        group_name=group_name,
        new_group=NEW_GROUP,
    )
    return render(request, "projects/mvr_import.html", context)
