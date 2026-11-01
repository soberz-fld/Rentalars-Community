# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages for editing the content of a project template (PRJ-135).

``/projects/templates/<id>/content/`` shows what a project made from the template will get – groups with their lines,
crew places, vehicle bookings, phases, open items, notes – and changes it entry by entry. The work is done by
``projects.template_content``; these views only read the forms, show what is wrong, and say when an entry was changed or
removed by somebody else in the meantime.
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, SpecialRight, module_required, request_rights
from rentalars.core.forms import add_validation_error
from rentalars.personnel.models import JobFunction
from rentalars.products.models import Product
from rentalars.projects import template_content as tc
from rentalars.projects.models import GroupKind, LineVariant, PhaseKind, ProjectTemplate
from rentalars.projects.template_content_forms import (
    FORMS,
    NotesForm,
    OpenItemForm,
    line_form_for,
)

#: What the pages call the sections (``section`` in the addresses is the content's own name).
SECTION_TITLES = {
    tc.GROUPS: gettext_lazy("Groups"),
    tc.LINES: gettext_lazy("Lines"),
    tc.CREW: gettext_lazy("Crew places"),
    tc.VEHICLES: gettext_lazy("Vehicle bookings"),
    tc.PHASES: gettext_lazy("Phases"),
    tc.OPEN_ITEMS: gettext_lazy("Open items"),
}


def _template(template_pk: int) -> ProjectTemplate:
    return get_object_or_404(ProjectTemplate, pk=template_pk)


def _section(section: str) -> str:
    if section not in tc.SECTIONS:
        raise Http404
    return section


def _back(template: ProjectTemplate, section: str | None = None) -> HttpResponse:
    address = redirect("projects:template_content", template.pk).url
    return redirect(f"{address}#{section}" if section else address)


def _prices(request: HttpRequest) -> bool:
    return request_rights(request).has(SpecialRight.PRICES)


def _stale(request: HttpRequest, template: ProjectTemplate, section: str) -> HttpResponse:
    messages.warning(request, _("This entry was changed or removed by somebody else. Please check the list."))
    return _back(template, section)


# --- The overview ---------------------------------------------------------------------------------------------------


def _labels(content: dict[str, Any]) -> dict[str, dict[Any, str]]:
    """Names for the ids the content holds, read once."""
    product_ids = [e["product"] for e in (*content[tc.LINES], *content[tc.VEHICLES]) if e.get("product")]
    products = dict(Product.objects.filter(pk__in=product_ids).values_list("pk", "name"))
    functions = dict(
        JobFunction.objects.filter(pk__in=[e["job_function"] for e in content[tc.CREW]]).values_list("pk", "name")
    )
    return {"product": products, "function": functions}


def _overview_rows(content: dict[str, Any]) -> dict[str, Any]:
    labels = _labels(content)
    phases = content[tc.PHASES]

    def phase_name(entry: dict[str, Any]) -> str:
        index = entry.get("phase")
        if index is None or index >= len(phases):
            return ""
        return phases[index].get("title") or str(PhaseKind(phases[index]["kind"]).label)

    rows = []
    for row in tc.outline(content):
        entry = row["entry"]
        if row["type"] == "group":
            rows.append(
                {**row, "name": entry["name"], "kind": GroupKind(entry["kind"]).label, "kind_value": entry["kind"]}
            )
            continue
        if entry.get("is_text"):
            name = entry["title"]
        elif entry.get("product"):
            name = labels["product"].get(entry["product"], "?")
        else:
            name = entry["title"]
        rows.append(
            {
                **row,
                "name": name,
                "variant": LineVariant(entry["variant"]).label if entry.get("variant") else "",
                "period": tc.describe_period(entry) if entry.get("own_period") else "",
            }
        )
    return {
        "rows": rows,
        "crew": [
            {
                "entry": e,
                "name": labels["function"].get(e["job_function"], "?"),
                "period": tc.describe_period(e),
                "phase": phase_name(e),
            }
            for e in content[tc.CREW]
        ],
        "vehicles": [
            {
                "entry": e,
                "name": e.get("title") or labels["product"].get(e["product"], "?"),
                "period": tc.describe_period(e),
                "phase": phase_name(e),
            }
            for e in content[tc.VEHICLES]
        ],
        "phases": [
            {
                "entry": e,
                "name": e.get("title") or str(PhaseKind(e["kind"]).label),
                "period": tc.describe_period(e),
            }
            for e in phases
        ],
        "open_items": list(enumerate(content[tc.OPEN_ITEMS])),
    }


@module_required(Module.PROJECTS, Level.WRITE)
def template_content(request: HttpRequest, template_pk: int) -> HttpResponse:
    """What a project made from this template gets, with the buttons to change it."""
    template = _template(template_pk)
    content = tc.open_for_editing(template)
    context = {
        "template": template,
        "content": content,
        "notes": content.get("notes", ""),
        "rental_days": content.get("rental_days"),
        "length_seconds": content.get("length_seconds"),
        "has_prices": _prices(request),
        **_overview_rows(content),
    }
    return render(request, "projects/template_content.html", context)


# --- Add and change --------------------------------------------------------------------------------------------------


def _form_class(section: str, entry: dict[str, Any] | None, mode: str):
    if section == tc.LINES:
        return line_form_for(entry, mode)
    return FORMS[section]


def _open_item_form(request: HttpRequest, template: ProjectTemplate, key: int | None, expect: str | None):
    """Add or change an open item: its place is its address, its old text guards against a changed list."""
    content = tc.open_for_editing(template)
    items = content[tc.OPEN_ITEMS]
    if key is not None and (key >= len(items) or (expect is not None and items[key] != expect)):
        raise KeyError(key)
    entry = {"text": items[key]} if key is not None else None
    form = OpenItemForm(request.POST or None, content=content, entry=entry)
    return entry, form


@module_required(Module.PROJECTS, Level.WRITE)
def entry_form(request: HttpRequest, template_pk: int, section: str, key: int | None = None) -> HttpResponse:
    """Add an entry (``key`` is None) or change one."""
    template = _template(template_pk)
    section = _section(section)
    if section == tc.OPEN_ITEMS:
        return _open_item_page(request, template, key)
    content = tc.open_for_editing(template)
    entry = None
    if key is not None:
        try:
            entry = content[section][tc.index_of(content, section, key)]
        except KeyError:
            return _stale(request, template, section)
    mode = request.GET.get("as", "product") if request.method == "GET" else request.POST.get("as", "product")
    cls = _form_class(section, entry, mode)
    prices = _prices(request)
    form = cls(request.POST or None, content=content, entry=entry, prices=prices)
    if request.method == "POST" and form.is_valid():
        data = form.values()
        try:
            if key is None:
                tc.add_entry(template, section, data, rights=request_rights(request), user=request.user)
                messages.success(request, _("Entry added."))
            else:
                # What the form does not show (a line's preferred model, its hours) stays as it was.
                merged = {**(entry or {}), **data}
                tc.update_entry(template, section, key, merged, rights=request_rights(request), user=request.user)
                messages.success(request, _("Entry saved."))
        except ValidationError as error:
            add_validation_error(form, error)
        except KeyError:
            return _stale(request, template, section)
        else:
            return _back(template, section)
    return render(
        request,
        "projects/template_content_form.html",
        {
            "template": template,
            "form": form,
            "section": section,
            "section_title": SECTION_TITLES[section],
            "entry": entry,
            "mode": getattr(form, "kind", ""),
            "has_period": "period" in form.fields,
        },
    )


def _open_item_page(request: HttpRequest, template: ProjectTemplate, key: int | None) -> HttpResponse:
    expect = (request.POST.get("expect") if request.method == "POST" else request.GET.get("expect")) or None
    try:
        entry, form = _open_item_form(request, template, key, expect)
    except KeyError:
        return _stale(request, template, tc.OPEN_ITEMS)
    if request.method == "POST" and form.is_valid():
        try:
            text = form.cleaned_data["text"]
            if key is None:
                tc.add_entry(template, tc.OPEN_ITEMS, {"text": text}, rights=request_rights(request), user=request.user)
                messages.success(request, _("Entry added."))
            else:
                tc.update_entry(
                    template,
                    tc.OPEN_ITEMS,
                    key,
                    {"text": text},
                    rights=request_rights(request),
                    user=request.user,
                    expect=expect,
                )
                messages.success(request, _("Entry saved."))
        except ValidationError as error:
            add_validation_error(form, error)
        except KeyError:
            return _stale(request, template, tc.OPEN_ITEMS)
        else:
            return _back(template, tc.OPEN_ITEMS)
    return render(
        request,
        "projects/template_content_form.html",
        {
            "template": template,
            "form": form,
            "section": tc.OPEN_ITEMS,
            "section_title": SECTION_TITLES[tc.OPEN_ITEMS],
            "entry": entry,
            "expect": entry["text"] if entry else "",
            "mode": "",
            "has_period": False,
        },
    )


# --- Delete and move -------------------------------------------------------------------------------------------------


@module_required(Module.PROJECTS, Level.WRITE)
def entry_delete(request: HttpRequest, template_pk: int, section: str, key: int) -> HttpResponse:
    """Delete an entry. A group asks first what happens to what is in it."""
    template = _template(template_pk)
    section = _section(section)
    content = tc.open_for_editing(template)
    group = None
    if section == tc.GROUPS:
        try:
            group = content[tc.GROUPS][tc.index_of(content, tc.GROUPS, key)]
        except KeyError:
            return _stale(request, template, section)
        if request.method == "GET":
            lines = sum(1 for line in content[tc.LINES] if line.get("group") == key)
            subgroups = sum(1 for other in content[tc.GROUPS] if other.get("parent") == key)
            return render(
                request,
                "projects/template_content_group_delete.html",
                {"template": template, "group": group, "lines": lines, "subgroups": subgroups},
            )
    if request.method != "POST":
        return _back(template, section)
    try:
        tc.delete_entry(
            template,
            section,
            key,
            user=request.user,
            with_content=bool(request.POST.get("with_content")) and section == tc.GROUPS,
            expect=request.POST.get("expect") or None,
        )
    except KeyError:
        return _stale(request, template, section)
    messages.success(request, _("Entry deleted."))
    return _back(template, section)


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def entry_move(request: HttpRequest, template_pk: int, section: str, key: int) -> HttpResponse:
    """Move an entry one place up or down."""
    template = _template(template_pk)
    section = _section(section)
    direction = -1 if request.POST.get("direction") == "up" else 1
    try:
        tc.open_for_editing(template)
        tc.move_entry(template, section, key, direction, user=request.user, expect=request.POST.get("expect") or None)
    except KeyError:
        return _stale(request, template, section)
    return _back(template, section)


# --- Notes -----------------------------------------------------------------------------------------------------------


@module_required(Module.PROJECTS, Level.WRITE)
def notes_form(request: HttpRequest, template_pk: int) -> HttpResponse:
    """The notes a new project gets, and its default rental days."""
    template = _template(template_pk)
    content = tc.open_for_editing(template)
    form = NotesForm(
        request.POST or None,
        content=content,
        initial={"notes": content.get("notes", ""), "rental_days": content.get("rental_days")},
    )
    if request.method == "POST" and form.is_valid():
        try:
            tc.set_notes(
                template,
                notes=form.cleaned_data["notes"],
                rental_days=form.cleaned_data["rental_days"],
                user=request.user,
            )
        except ValidationError as error:
            add_validation_error(form, error)
        else:
            messages.success(request, _("Entry saved."))
            return _back(template)
    return render(
        request,
        "projects/template_content_form.html",
        {
            "template": template,
            "form": form,
            "section": "notes",
            "section_title": gettext_lazy("Notes"),
            "entry": {"notes": True},
            "mode": "",
            "has_period": False,
        },
    )
