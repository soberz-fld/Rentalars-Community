# SPDX-License-Identifier: GPL-3.0-or-later
"""The pages of the audits (MAT-067, MAT-068, MAT-069, MAT-070).

An audit is a short check of the material; it has a mode of its own.

* **Audit** (Materialverwaltung → Audit, :func:`audit_page`): IDs typed or
  scanned one after the other. Per item "In Ordnung" – or to-dos by quick
  pick ("Label fehlt", "Klett fehlt" …) and as free text, then "Audit
  speichern"; then the next ID. Plain forms, so it works without the page
  script and on a phone; the items of the round are listed on the page.
  (MAT-079) A compact overview of the item's master data shows what is
  documented and what is missing ("–"), with "Exemplar bearbeiten" that
  comes back to the audit.
* **The box "Audit und To-Dos"** on the page of an item: last and next audit,
  open to-dos with "erledigt", "To-Do notieren", the audits so far
  (:func:`audit_context`, :func:`item_todo_add`, :func:`todo_done`).
* **Offene Punkte**: the sub-tabs
  "Material ohne Produkt", "Material mit To-Do" and "Audit fällig".
* **Einstellungen → Audits**: the interval and the quick picks.

Recording audits and to-dos needs write access to the material, seeing them
read access – as for inspections (MAT-031).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, module_required, request_rights
from rentalars.core.forms import StyledModelForm
from rentalars.core.listing import paginate
from rentalars.masterdata.models import Category
from rentalars.material import audits
from rentalars.material.audit_models import TODO_MAX_LENGTH, AuditResult, AuditSettings, ItemTodo
from rentalars.material.audit_tables import AUDIT_DUE_TABLE, TODO_TABLE
from rentalars.material.filters import search_items
from rentalars.material.item_views import safe_next
from rentalars.material.models import MaterialItem
from rentalars.material.numbering import format_inventory_number

#: The items audited in this round, newest first – kept in the session of the user.
ROUND_SESSION_KEY = "material_audit_round"
ROUND_MAX_ITEMS = 200


# --- The audit mode -------------------------------------------------------------------------------


def _audit_url(display_id: str = "") -> str:
    """The address of the audit mode, with an ID to show."""
    base = reverse("material:audit")
    return f"{base}?{urlencode({'id': display_id})}" if display_id else base


def _round(request: HttpRequest) -> list[dict[str, Any]]:
    """The items audited in this round, as kept in the session, with the result in words."""
    rows = []
    for entry in request.session.get(ROUND_SESSION_KEY, []):
        result = entry.get("result", AuditResult.OK)
        label = AuditResult(result).label if result in AuditResult.values else result
        rows.append({**entry, "result_label": label, "is_ok": result == AuditResult.OK})
    return rows


def _remember(request: HttpRequest, item: MaterialItem, audit: Any, todo_count: int) -> None:
    """Put an audited item at the top of the round; an item audited again moves up."""
    entries = [entry for entry in request.session.get(ROUND_SESSION_KEY, []) if entry.get("pk") != item.pk]
    entries.insert(
        0,
        {
            "pk": item.pk,
            "id": item.display_id,
            "name": item.material_model.name,
            "result": audit.result,
            "todos": todo_count,
            "time": timezone.localtime(audit.audited_at).strftime("%H:%M"),
        },
    )
    request.session[ROUND_SESSION_KEY] = entries[:ROUND_MAX_ITEMS]


@module_required(Module.MATERIAL, Level.WRITE)
def audit_page(request: HttpRequest) -> HttpResponse:
    """Materialverwaltung → Audit: one item after the other by its ID (MAT-068).

    ``?id=`` takes the ID as the ID field does – ``0427``, ``427``,
    ``#0427`` – and the address a scanner reads from the QR code of a label
    (:func:`audits.parse_scanned_id`). An ID nobody has gives a message and
    the field again.
    """
    if request.method == "POST":
        return _audit_post(request)
    settings_row = audits.audit_settings()
    typed = request.GET.get("id", "").strip()
    item = None
    if typed:
        try:
            number = audits.parse_scanned_id(typed)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            item = audits.audit_item(number)
            if item is None:
                messages.error(
                    request, _("There is no item with the ID %(id)s.") % {"id": format_inventory_number(number)}
                )
    context: dict[str, Any] = {
        "tab": "audit",
        "typed": "" if item is not None else typed,
        "item": item,
        "round": _round(request),
        "quick_todos": settings_row.quick_todo_list,
        "settings_row": settings_row,
        "todo_max_length": TODO_MAX_LENGTH,
        "note_max_length": audits.NOTE_MAX_LENGTH,
    }
    if item is not None:
        context["state"] = audits.state_of(item, settings_row=settings_row)
        context["open_todos"] = list(item.todos.filter(done_at__isnull=True).select_related("created_by"))
        # MAT-079: what is documented of the item – "Exemplar bearbeiten" comes back here.
        context["master_data"] = audits.master_data(item, request_rights(request))
        edit_url = reverse("material:item_edit", args=[item.pk])
        context["edit_url"] = f"{edit_url}?{urlencode({'next': _audit_url(item.display_id)})}"
    return render(request, "material/audit.html", context)


def _audit_post(request: HttpRequest) -> HttpResponse:
    """Record the audit of one item – "in order", or with to-dos – or begin a new round."""
    action = request.POST.get("action", "")
    if action == "new_round":
        request.session.pop(ROUND_SESSION_KEY, None)
        messages.success(request, _("A new round begins."))
        return redirect("material:audit")
    item_id = request.POST.get("item", "")
    item = get_object_or_404(
        MaterialItem.objects.select_related("material_model"), pk=int(item_id) if item_id.isdigit() else 0
    )
    if action == "ok":
        todos: list[str] = []
        done: list[str] = []
    else:
        todos = [*request.POST.getlist("todo"), request.POST.get("todo_text", "")]
        done = request.POST.getlist("done")
    try:
        audit = audits.record_audit(item, todos=todos, done=done, note=request.POST.get("note", ""), user=request.user)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect(_audit_url(item.display_id))
    _remember(request, item, audit, audit.todos.count())
    messages.success(
        request, _("%(id)s audited: %(result)s.") % {"id": item.display_id, "result": audit.get_result_display()}
    )
    return redirect(_audit_url(request.POST.get("next", "").strip()[:200]))


# --- The box "Audit und To-Dos" on the page of an item --------------------------------------------


def audit_context(item: MaterialItem) -> dict[str, Any]:
    """What the box "Audit und To-Dos" of an item shows (MAT-069)."""
    settings_row = audits.audit_settings()
    todos = list(item.todos.select_related("created_by", "done_by", "audit"))
    done = sorted((todo for todo in todos if not todo.is_open), key=lambda todo: todo.done_at, reverse=True)
    return {
        "audit_state": audits.state_of(item, settings_row=settings_row),
        "open_todos": [todo for todo in todos if todo.is_open],
        "done_todos": done[:10],
        "audits": item.audits.select_related("audited_by").prefetch_related("todos")[:20],
        "quick_todos": settings_row.quick_todo_list,
        "todo_max_length": TODO_MAX_LENGTH,
    }


def _item_box(item: MaterialItem) -> str:
    return f"{reverse('material:item_detail', args=[item.pk])}#audit"


@require_POST
@module_required(Module.MATERIAL, Level.WRITE)
def item_todo_add(request: HttpRequest, pk: int) -> HttpResponse:
    """Note a to-do on an item, typed or by quick pick (MAT-069)."""
    item = get_object_or_404(MaterialItem.objects.select_related("material_model"), pk=pk)
    text = request.POST.get("pick") or request.POST.get("text", "")
    try:
        todo = audits.add_todo(item, text, user=request.user)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, _("To-do noted: %(text)s") % {"text": todo.text})
    return redirect(safe_next(request, _item_box(item)))


@require_POST
@module_required(Module.MATERIAL, Level.WRITE)
def todo_done(request: HttpRequest, pk: int) -> HttpResponse:
    """Tick one to-do done (MAT-069)."""
    todo = get_object_or_404(ItemTodo.objects.select_related("item"), pk=pk)
    audits.complete_todo(todo, user=request.user)
    messages.success(request, _("To-do done: %(text)s") % {"text": todo.text})
    return redirect(safe_next(request, _item_box(todo.item)))


@require_POST
@module_required(Module.MATERIAL, Level.WRITE)
def todos_done(request: HttpRequest) -> HttpResponse:
    """Tick the to-dos chosen in "Material mit To-Do" done, all at once (MAT-070)."""
    ids = [int(value) for value in request.POST.getlist("todos") if value.isdigit()]
    count = audits.complete_todos(
        ItemTodo.objects.filter(pk__in=ids, done_at__isnull=True).select_related("item"), user=request.user
    )
    if count:
        messages.success(request, ngettext("%(count)d to-do done.", "%(count)d to-dos done.", count) % {"count": count})
    else:
        messages.error(request, _("Tick the to-dos that are done."))
    return redirect(safe_next(request, reverse("material:open_todos")))


# --- Materialverwaltung → Offene Punkte -----------------------------------------------------------


def open_points_context(sub_tab: str) -> dict[str, Any]:
    """The tab "Offene Punkte" with its sub-tabs and their counts."""
    return {"tab": "open_points", "sub_tab": sub_tab, "open_counts": audits.open_point_counts()}


@module_required(Module.MATERIAL)
def open_without_product(request: HttpRequest) -> HttpResponse:
    """Offene Punkte → Material ohne Produkt: the items without product (PRD-005)."""
    from rentalars.material.views import item_list_page

    return item_list_page(request, open_points=True)


def _category_filter(request: HttpRequest, path: str) -> Q:
    """A chosen category with its subcategories (MAT-008), as a condition on ``path``; nothing chosen: all."""
    category_id = request.GET.get("category", "")
    if not category_id.isdigit():
        return Q()
    return Q(**{f"{path}__in": Category.objects.descendant_ids(int(category_id))})


def _search_todos(todos: QuerySet[ItemTodo], text: str) -> QuerySet[ItemTodo]:
    """Search the to-dos by their text, the article name and the ID of the item."""
    text = text.strip()
    if not text:
        return todos
    condition = (
        Q(text__icontains=text)
        | Q(item__material_model__name__icontains=text)
        | Q(item__material_model__short_name__icontains=text)
    )
    number = text.removeprefix("#").strip()
    if number.isdigit():
        condition |= Q(item__inventory_number=int(number))
    return todos.filter(condition)


@module_required(Module.MATERIAL)
def open_todos(request: HttpRequest) -> HttpResponse:
    """Offene Punkte → Material mit To-Do: one row per open to-do (MAT-070; UIX-015, UIX-040)."""
    todos = audits.open_todos().select_related(
        "item__material_model__category",
        "item__storage_location",
        "item__installed_in__storage_location",
        "created_by",
    )
    texts = sorted(set(todos.values_list("text", flat=True)), key=str.casefold)
    todos = _search_todos(todos, request.GET.get("q", "")).filter(
        _category_filter(request, "item__material_model__category_id")
    )
    chosen_text = request.GET.get("todo", "")
    if chosen_text:
        todos = todos.filter(text=chosen_text)
    table = TODO_TABLE.state(request)
    todos = table.order(todos)
    if table.wants_csv:
        return table.csv_response(todos, _("To-dos"))
    page = paginate(request, todos)
    context = open_points_context("todos")
    context.update(
        {
            "page": page,
            "table": table,
            "rows": table.rows(page),
            "texts": texts,
            "chosen_text": chosen_text,
            "categories": Category.objects.in_tree_order(),
        }
    )
    return render(request, "material/open_todos.html", context)


@module_required(Module.MATERIAL)
def open_audits(request: HttpRequest) -> HttpResponse:
    """Offene Punkte → Audit fällig: the items whose audit is due, oldest first (MAT-070)."""
    settings_row = audits.audit_settings()
    items = audits.due_items(
        MaterialItem.objects.select_related(
            "material_model__category", "storage_location", "installed_in__storage_location"
        ),
        settings_row=settings_row,
    )
    items = search_items(items, request.GET.get("q", "")).filter(
        _category_filter(request, "material_model__category_id")
    )
    table = AUDIT_DUE_TABLE.state(request)
    items = table.order(items)
    if table.wants_csv:
        return table.csv_response(items, _("Audits due"))
    page = paginate(request, items)
    context = open_points_context("audits")
    context.update(
        {
            "page": page,
            "table": table,
            "rows": table.rows(page),
            "settings_row": settings_row,
            "categories": Category.objects.in_tree_order(),
        }
    )
    return render(request, "material/open_audits.html", context)


# --- Einstellungen → Audits -----------------------------------------------------------------------


class AuditSettingsForm(StyledModelForm):
    """The interval and the quick picks (MAT-067)."""

    class Meta:
        model = AuditSettings
        fields = ["interval_months", "quick_todos"]
        widgets = {"quick_todos": forms.Textarea(attrs={"rows": 7})}


@module_required(Module.ADMINISTRATION)
def audit_settings_page(request: HttpRequest) -> HttpResponse:
    """Einstellungen → Audits: the interval (24 months; 0 is off) and the quick picks for to-dos.

    Read for who may read the settings, changed with write access to them –
    as Einstellungen → Etiketten (MAT-056).
    """
    can_write = request_rights(request).can_write(Module.ADMINISTRATION)
    form = AuditSettingsForm(request.POST or None, instance=AuditSettings.load())
    if request.method == "POST":
        if not can_write:
            raise PermissionDenied
        if form.is_valid():
            form.save()
            messages.success(request, _("Settings saved."))
            return redirect("material:audit_settings")
    return render(request, "material/audit_settings.html", {"form": form, "can_write": can_write})
