# SPDX-License-Identifier: GPL-3.0-or-later
"""Custom fields in tables: the settings lists and the columns of the item list (MAT-071, MAT-072, MAT-073; UIX-015).

Every custom field marked "choosable as a column in lists" is a column of
the item list (``material.tables.ITEM_TABLE``) – off until the user switches
it on, sorted by the database (a number as a number, a date as a date),
filtered by text (``?cf<id>=…``, :mod:`rentalars.customfields.filters`) and
part of the CSV file in clear text (IMP-005). A field visible only with the
right to see purchase prices is a column only for who has it (AUT-019).
"""

from __future__ import annotations

import threading
from typing import Any
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db.models import DecimalField, OuterRef, Subquery, TextField, Value
from django.db.models.functions import Cast, NullIf
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeString
from django.utils.text import capfirst
from django.utils.translation import gettext, ngettext
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.core.tables import Column, TableDefinition, badge, link
from rentalars.customfields import services
from rentalars.customfields.models import CustomField, CustomFieldValue, FieldType

#: The prefix of the key of a custom field's column in the item list: ``cf7`` for the field with the ID 7.
COLUMN_PREFIX = "cf"


def column_key(field: CustomField) -> str:
    """The key of a field's column in the item list and of its filter in the address, e.g. ``cf7``."""
    return f"{COLUMN_PREFIX}{field.pk}"


#: The schemes a web address may have to become a link (MAT-071) – never ``javascript:`` or ``data:``.
LINK_SCHEMES = frozenset({"http", "https"})


def _is_web_address(stored: str) -> bool:
    r"""Whether a stored web address may be a link: ``http`` or ``https`` with a host.

    ``urlsplit`` drops what browsers drop – leading spaces and control
    characters, tabs and line breaks inside – so ``java\tscript:`` is read
    as the browser would read it.
    """
    try:
        parts = urlsplit(stored)
    except ValueError:
        return False
    return parts.scheme.lower() in LINK_SCHEMES and bool(parts.netloc)


def _is_mail_address(stored: str) -> bool:
    """Whether a stored e-mail address may follow ``mailto:``."""
    try:
        EmailValidator()(stored)
    except ValidationError:
        return False
    return True


def value_html(field: CustomField, stored: str) -> SafeString:
    """A value as HTML: a web address as a link, an e-mail address as a mail link, long text with line breaks.

    MAT-071: only an ``http``/``https`` address becomes a link, only a valid e-mail address a
    mail link; anything else – a value stored before a check, or by hand – is shown as plain text.
    """
    text = field.display_value(stored)
    if not text:
        return format_html("")
    if field.field_type == FieldType.URL and _is_web_address(stored):
        return format_html('<a href="{}" rel="noopener noreferrer" target="_blank">{}</a>', stored, text)
    if field.field_type == FieldType.EMAIL and _is_mail_address(stored):
        return format_html('<a href="mailto:{}">{}</a>', stored, text)
    if field.field_type == FieldType.LONG_TEXT:
        return format_html_join(format_html("<br>"), "{}", ((line,) for line in text.splitlines()))
    return format_html("{}", text)


def _sort_expression(field: CustomField) -> Any:
    """The value of the field for each item as the database sorts it: numbers as numbers, empty as nothing."""
    stored = Subquery(
        CustomFieldValue.objects.filter(item=OuterRef("pk"), field_id=field.pk).values(field.column)[:1],
        output_field=TextField(),
    )
    value = NullIf(stored, Value(""))
    if field.field_type == FieldType.NUMBER:
        return Cast(value, DecimalField(max_digits=30, decimal_places=10))
    return value


def _sensitive_visible(rights: Rights) -> bool:
    return rights.has(SpecialRight.PURCHASE_PRICES)


def list_column(field: CustomField) -> Column:
    """The column of one custom field in the item list."""

    def stored(item: Any) -> str:
        return services.stored_values(item).get(field.pk, "")

    return Column(
        column_key(field),
        field.label_with_unit,
        cell=lambda item: value_html(field, stored(item)),
        text=lambda item: field.typed_value(stored(item)),
        sort=(_sort_expression(field), "inventory_number"),
        css="num" if field.field_type == FieldType.NUMBER else "",
        default=False,
        visible_if=_sensitive_visible if field.is_sensitive else None,
    )


#: The fields the item list asked for last in this thread – its rows are prepared right after (``TableState``).
_seen = threading.local()


def list_columns() -> list[Column]:
    """The columns of all custom fields marked "in lists", by name (registered in ``apps.py``)."""
    fields = services.list_fields()
    _seen.fields = fields
    return [list_column(field) for field in fields]


def prepare_list_values(items: list[Any]) -> None:
    """Load the custom values of the shown items with one query – only if there are custom columns at all.

    The table asked for its columns a moment ago (``TableDefinition.state``); without custom columns
    then, preparing its rows asks the database nothing more (NFA-012).
    """
    fields = getattr(_seen, "fields", None)
    if fields is None:
        fields = services.list_fields()
    if fields:
        services.load_values(items, with_entries=False)


# --- Einstellungen → Eigene Felder, Feldsätze ----------------------------------------------------------


def _field_name(field: Any) -> SafeString:
    """The name; a link to the form for who may change the definitions."""
    if getattr(field, "can_write", False):
        return link(reverse("customfields:field_edit", args=[field.pk]), field.name)
    return format_html("{}", field.name)


def _type_text(field: CustomField) -> str:
    """The type with what qualifies it: the unit, the options."""
    text = capfirst(str(field.get_field_type_display()))
    if field.field_type == FieldType.NUMBER and field.unit:
        return f"{text} ({field.unit})"
    if field.field_type == FieldType.CHOICE:
        return f"{text}: {', '.join(field.choices or [])}"
    return text


def _marks(field: CustomField) -> SafeString:
    marks = []
    if field.show_in_lists:
        marks.append(badge(gettext("in lists")))
    if field.is_unique:
        marks.append(badge(gettext("unique")))
    if field.is_sensitive:
        marks.append(badge(gettext("with purchase price right"), "yellow"))
    if field.pattern:
        marks.append(badge(gettext("check pattern")))
    return format_html_join(" ", "{}", ((mark,) for mark in marks))


def _marks_text(field: CustomField) -> str:
    parts = []
    if field.show_in_lists:
        parts.append(gettext("in lists"))
    if field.is_unique:
        parts.append(gettext("unique"))
    if field.is_sensitive:
        parts.append(gettext("with purchase price right"))
    if field.pattern:
        parts.append(gettext("check pattern"))
    return ", ".join(parts)


def _fieldset_names(field: Any) -> str:
    return ", ".join(
        f"{entry.fieldset.name}{' *' if entry.is_required else ''}" for entry in field.fieldset_entries.all()
    )


FIELD_TABLE = TableDefinition(
    "customfields_fields",
    [
        Column(
            "name", _("Name"), cell=_field_name, text=lambda field: field.name, sort="name", fixed=True, group="name"
        ),
        Column(
            "type",
            _("Type"),
            cell=_type_text,
            sort=("field_type", "name"),
            group="field_type",
            group_label=lambda field: capfirst(str(field.get_field_type_display())),
        ),
        Column("marks", _("Properties"), cell=_marks, text=_marks_text, sort=lambda field: _marks_text(field)),
        Column(
            "fieldsets",
            _("Fieldsets"),
            cell=_fieldset_names,
            sort=lambda field: _fieldset_names(field).casefold(),
        ),
        Column(
            "values",
            _("Items with a value"),
            cell=lambda field: field.value_total or "",
            text=lambda field: field.value_total,
            sort=("value_total", "name"),
            css="num",
        ),
        Column(
            "help_text",
            _("Help text"),
            cell=lambda field: field.help_text,
            sort=("help_text", "name"),
            default=False,
            group="help_text",
        ),
    ],
    default_sort="name",
)


def _fieldset_name(fieldset: Any) -> SafeString:
    """The name; a link to the form for who may change the definitions."""
    if getattr(fieldset, "can_write", False):
        return link(reverse("customfields:fieldset_edit", args=[fieldset.pk]), fieldset.name)
    return format_html("{}", fieldset.name)


def _entries_text(fieldset: Any) -> str:
    return ", ".join(
        f"{entry.field.name}{' *' if entry.is_required else ''}"
        for entry in sorted(fieldset.entries.all(), key=lambda entry: (entry.position, entry.field.name))
    )


def _models_cell(fieldset: Any) -> str:
    count = fieldset.model_total
    if not count:
        return ""
    return ngettext("%(count)s material model", "%(count)s material models", count) % {"count": count}


FIELDSET_TABLE = TableDefinition(
    "customfields_fieldsets",
    [
        Column(
            "name",
            _("Name"),
            cell=_fieldset_name,
            text=lambda fieldset: fieldset.name,
            sort="name",
            fixed=True,
            group="name",
        ),
        Column("fields", _("Fields"), cell=_entries_text, sort=lambda fieldset: _entries_text(fieldset).casefold()),
        Column(
            "models",
            _("Material models"),
            cell=_models_cell,
            text=lambda fieldset: fieldset.model_total,
            sort=("model_total", "name"),
            css="num",
        ),
        Column(
            "description",
            _("Description"),
            cell=lambda fieldset: fieldset.description,
            sort=("description", "name"),
            group="description",
        ),
    ],
    default_sort="name",
)
