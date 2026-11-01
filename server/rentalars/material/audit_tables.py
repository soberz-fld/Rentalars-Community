# SPDX-License-Identifier: GPL-3.0-or-later
"""Materialverwaltung → Offene Punkte as tables: open to-dos and due audits (MAT-070; UIX-015, UIX-040).

* ``material_todos`` – one row per open to-do, so that the same to-do of many
  items ("Label fehlt" on 20 cables) can be grouped and ticked done at once.
* ``material_audits_due`` – one row per item whose audit is due, oldest first.

Both are querysets: the database sorts and groups; the storage location (where
the outermost container is, MAT-038) is computed and sorts in Python.
"""

from __future__ import annotations

import datetime
from typing import Any

from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import Module, Rights
from rentalars.core.tables import Column, TableDefinition, badge, date_text, grouped_by_day, hidden_label, link
from rentalars.core.templatetags.rentalars import status_colour
from rentalars.masterdata.models import remember_location_paths
from rentalars.material.audits import audit_settings, due_date_for


def _item_link(item: Any) -> SafeString:
    return link(f"{reverse('material:item_detail', args=[item.pk])}#audit", item.display_id, "tape")


def _location(item: Any) -> str:
    location = item.effective_storage_location
    if location is None:
        return ""
    spot = item.effective_storage_spot
    return f"{location.path} {spot}" if spot else location.path


def _status(item: Any) -> SafeString:
    return badge(item.get_status_display(), status_colour(item.status))


def _prepare_todos(todos: list[Any]) -> None:
    """The paths of the storage locations of a page from one query (MAT-038)."""
    remember_location_paths(todo.item.effective_storage_location for todo in todos)


def _prepare_items(items: list[Any]) -> None:
    remember_location_paths(item.effective_storage_location for item in items)


def _may_write(rights: Rights) -> bool:
    return rights.can_write(Module.MATERIAL)


TODO_TABLE = TableDefinition(
    "material_todos",
    [
        Column(
            "id",
            _("ID"),
            cell=lambda todo: _item_link(todo.item),
            text=lambda todo: todo.item.display_id,
            sort="item__inventory_number",
            fixed=True,
            group="item",
            group_label=lambda todo: format_html("{} {}", _item_link(todo.item), todo.item.material_model.name),
        ),
        Column(
            "name",
            _("Article name"),
            cell=lambda todo: todo.item.material_model.name,
            sort=("item__material_model__name", "item__inventory_number"),
            group="item__material_model",
        ),
        Column("todo", _("To-do"), cell=lambda todo: todo.text, sort="text", group="text"),
        Column(
            "noted",
            _("Noted"),
            cell=lambda todo: date_text(todo.created_at),
            text=lambda todo: todo.created_at,
            sort="created_at",
            **grouped_by_day("created_at"),
        ),
        Column(
            "noted_by",
            _("Noted by"),
            cell=lambda todo: str(todo.created_by) if todo.created_by_id else "",
            sort="created_by__username",
            group="created_by",
        ),
        Column(
            "location",
            _("Storage location"),
            cell=lambda todo: _location(todo.item),
            sort=lambda todo: _location(todo.item),
            sort_prepare=lambda todos, request: _prepare_todos(todos),
        ),
        Column(
            "status",
            _("Status"),
            cell=lambda todo: _status(todo.item),
            text=lambda todo: todo.item.get_status_display(),
            sort=("item__status", "item__inventory_number"),
            group="item__status",
        ),
        Column(
            "category",
            _("Category"),
            cell=lambda todo: todo.item.material_model.category.name,
            sort=("item__material_model__category__name", "item__inventory_number"),
            group="item__material_model__category",
            default=False,
        ),
    ],
    default_sort="id",
    prepare=_prepare_todos,
)


def _last_audit(item: Any) -> SafeString:
    if item.last_audit_at is None:
        return format_html('<span class="muted">{}</span>', gettext("never"))
    return format_html("{}", date_text(timezone.localdate(item.last_audit_at)))


def _due_day(item: Any) -> datetime.date | None:
    return due_date_for(item, item.last_audit_at, audit_settings())


def _audit_button(item: Any) -> SafeString:
    """The way to the audit mode with this item, its ID read out after "Audit" for a screen reader."""
    return format_html(
        '<a class="btn secondary small" href="{}?{}">{}<span class="visually-hidden"> {}</span></a>',
        reverse("material:audit"),
        f"id={item.display_id}",
        gettext("Audit"),
        item.display_id,
    )


AUDIT_DUE_TABLE = TableDefinition(
    "material_audits_due",
    [
        Column(
            "id",
            _("ID"),
            cell=_item_link,
            text=lambda item: item.display_id,
            sort="inventory_number",
            fixed=True,
            group="inventory_number",
        ),
        Column(
            "name",
            _("Article name"),
            cell=lambda item: item.material_model.name,
            sort=("material_model__name", "inventory_number"),
            group="material_model",
        ),
        Column(
            "last",
            _("Last audit"),
            cell=_last_audit,
            text=lambda item: timezone.localdate(item.last_audit_at) if item.last_audit_at else None,
            sort="last_audit_at",
        ),
        Column(
            "due",
            _("Due since"),
            cell=lambda item: badge(date_text(_due_day(item)), "red"),
            text=_due_day,
            sort="audit_reference",
        ),
        Column(
            "todos",
            _("Open to-dos"),
            cell=lambda item: item.open_todo_count or "",
            text=lambda item: item.open_todo_count,
            sort="open_todo_count",
            css="num",
        ),
        Column(
            "location",
            _("Storage location"),
            cell=_location,
            sort=_location,
            sort_prepare=lambda items, request: _prepare_items(items),
        ),
        Column(
            "status",
            _("Status"),
            cell=_status,
            text=lambda item: item.get_status_display(),
            sort=("status", "inventory_number"),
            group="status",
        ),
        Column(
            "category",
            _("Category"),
            cell=lambda item: item.material_model.category.name,
            sort=("material_model__category__name", "inventory_number"),
            group="material_model__category",
            default=False,
        ),
        Column(
            "audit",
            hidden_label(_("Actions")),
            cell=_audit_button,
            css="actions no-print",
            visible_if=_may_write,
            fixed=True,
            export=False,
            unsortable="a button",
        ),
    ],
    default_sort="due",
    prepare=_prepare_items,
)
