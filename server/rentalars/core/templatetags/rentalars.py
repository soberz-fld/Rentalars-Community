# SPDX-License-Identifier: GPL-3.0-or-later
"""Template helpers shared by all pages: money, quantities, icons, list links."""

from __future__ import annotations

import functools
from decimal import Decimal
from typing import Any

from django import template
from django.forms import BoundField, CheckboxInput
from django.templatetags.static import static
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.utils.translation import ngettext

from rentalars.core.money import format_decimal, format_money, group_thousands

register = template.Library()


@register.filter
def css_string(value: Any) -> SafeString:
    r"""Text for a CSS string such as ``content: "…"`` of a PDF's page margin (PCK-005).

    Every character but letters, digits and spaces is written as a CSS escape (``&`` → ``\26 ``), so that
    quotes, backslashes, line breaks and HTML end nothing. ``escapejs`` wrote ``\u0026``, which CSS reads as
    the letters "u0026".
    """
    text = "" if value is None else str(value)
    return SafeString("".join(char if char.isalnum() or char == " " else f"\\{ord(char):x} " for char in text))


@register.filter
def money(value: Decimal | None) -> str:
    """Format an amount as ``1.234,50 €`` (English ``€1,234.50``); nothing for ``None``."""
    return format_money(value)


@register.filter
def money_plain(value: Decimal | None) -> str:
    """Format an amount without currency sign, e.g. for copying into a quote: ``1.234,50``."""
    return format_money(value, currency="").strip()


@register.filter
def number(value: Decimal | int | None) -> str:
    """Format a number without needless zeros: ``1,5`` or ``12``."""
    return format_decimal(value)


@register.filter
def days(value: int | None) -> str:
    """Write a number of rental days with its unit: ``1 Tag``, ``2 Tage`` (PRJ-063)."""
    if value is None:
        return ""
    return ngettext("%(count)d day", "%(count)d days", value) % {"count": value}


@register.filter
def thousands(value: int | None) -> str:
    """Write a count with separators between the thousands: German ``20.115``, English ``20,115``.

    Only for numbers people read. An ID or anything a form sends back must
    stay as it is (see ``USE_THOUSAND_SEPARATOR`` in the settings).
    """
    if value is None:
        return ""
    number = int(value)
    # UIX-029: "20,115" in English.
    return ("-" if number < 0 else "") + group_thousands(str(abs(number)))


@register.filter
def item_id(number_value: int | None) -> str:
    """Format an inventory number with leading zeros (MAT-003)."""
    from rentalars.material.numbering import format_inventory_number

    return format_inventory_number(number_value) if number_value else ""


@functools.cache
def _icon_markup(name: str) -> SafeString:
    """Build the markup of an icon once per process; it never changes while the server runs."""
    return format_html(
        '<svg class="icon" aria-hidden="true"><use href="{}#{}"></use></svg>', static("img/icons.svg"), name
    )


@register.simple_tag
def icon(name: str) -> SafeString:
    """Render an icon from ``static/img/icons.svg`` by its name."""
    return _icon_markup(name)


#: The record ID that addresses with a placeholder are built with, see ``fill``.
URL_PLACEHOLDER_ID = 0


@register.filter
def fill(address: str, record_id: int) -> str:
    """Put a record ID into an address that was built with a placeholder.

    A table with hundreds of rows needs the same address for every row, only
    with a different ID. Looking each one up by name costs more time than
    everything else in the row together. The view therefore looks the
    address up once with the placeholder ID 0 (see ``placeholder_url``) and
    the template fills in the real ID::

        {{ urls.line_edit|fill:line.pk }}   →   /projects/5/lines/731/
    """
    return address.replace(f"/{URL_PLACEHOLDER_ID}/", f"/{record_id}/", 1)


@register.simple_tag(takes_context=True)
def query(context: dict[str, Any], **changes: Any) -> str:
    """Return the current query string with some parameters replaced.

    Lets paging and sorting links keep the active filters, so that every
    filtered view has an address that can be shared (UIX-004). Passing an
    empty value removes a parameter.

    Example: ``<a href="?{% query page=3 %}">`` on ``?status=out&page=2``
    gives ``?status=out&page=3``.
    """
    request = context["request"]
    parameters = request.GET.copy()
    for name, value in changes.items():
        if value in (None, ""):
            parameters.pop(name, None)
        else:
            parameters[name] = value
    return parameters.urlencode()


@register.filter
def is_checkbox(field: BoundField) -> bool:
    """Whether a form field is a single checkbox (it is laid out differently)."""
    return isinstance(field.field.widget, CheckboxInput)


@register.filter
def required_condition(field: BoundField) -> str:
    """UIX-035: whether a field must be filled in – ``"always"``, a condition, or ``""``.

    "Always" for a required form field, and for one the rules of the model
    require although the form field is optional (``core.forms.mark_required``
    sets ``aria-required``). A condition in the form of ``data-show-if``
    ("kind=rental|kit") for a field required only while it holds
    (``data-require-if``).
    """
    attrs = field.field.widget.attrs
    if field.field.required or attrs.get("aria-required") == "true":
        return "always"
    return str(attrs.get("data-require-if", ""))


@register.filter
def condition_holds(field: BoundField, condition: str) -> bool:
    """UIX-035: whether a condition such as "kind=rental|kit" holds for the values the form shows now.

    The page script checks the same while the user changes the form; this is
    the state it starts from. "a=x&b=y": both; "a=x;b=y": one of them. A part
    naming a field the form does not have holds.
    """

    def holds(part: str) -> bool:
        name, _separator, values = part.partition("=")
        if name not in field.form.fields:
            return True
        other = field.form[name]
        value = other.value()
        if isinstance(other.field.widget, CheckboxInput):
            value = "on" if value else ""
        return str(value if value is not None else "") in values.split("|")

    return any(all(holds(part) for part in alternative.split("&")) for alternative in condition.split(";"))


@register.filter
def marks_required(form: Any) -> bool:
    """UIX-035: whether a form marks a field as required – it then explains the asterisk once."""
    try:
        fields = form.visible_fields()
    except AttributeError:
        return False
    return any(required_condition(field) for field in fields)


@register.filter
def get_item(mapping: Any, key: Any) -> Any:
    """Look up ``mapping[key]`` in a template; nothing if the key is missing."""
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.filter
def percent_of(part: Any, whole: Any) -> int:
    """Return ``part`` as a whole percentage of ``whole`` (0 to 100), e.g. for bar widths."""
    try:
        if not whole:
            return 0
        return max(0, min(100, round(float(part) * 100 / float(whole))))
    except (TypeError, ValueError):
        return 0


@register.filter
def column_sample(rows: list[list[Any]], index: int) -> str:
    """Return the first non-empty values of one column, for the import preview."""
    values = []
    for row in rows:
        if index < len(row) and row[index] not in (None, ""):
            values.append(str(row[index]))
    return ", ".join(values[:3])


#: Badge colours for the statuses shown all over the application.
STATUS_COLOURS = {
    # material items
    "available": "green",
    "in_use": "accent",
    "defective": "red",
    "in_repair": "yellow",
    "blocked": "yellow",
    "retired": "",
    "sold": "",
    "lost": "",
    "import_error": "red",
    # projects
    "inquiry": "outline",
    "option": "yellow",
    "confirmed_open": "accent",
    "confirmed": "accent",
    "out": "solid",
    "returned": "green",
    "closed": "",
    "cancelled": "",
    # packlists
    "open": "outline",
    "in_progress": "yellow",
    "packed": "accent",
    "partly_issued": "yellow",  # PCK-025: something is out, the rest is still to go
    "issued": "solid",
    # time entries
    "recorded": "outline",
    "submitted": "yellow",
    "approved": "green",
    "rejected": "red",
    # subrentals
    "requested": "yellow",
    "ordered": "accent",
    "received": "green",
}


@register.filter
def status_colour(status: str) -> str:
    """Return the badge colour class for a status value."""
    return STATUS_COLOURS.get(status, "")


@register.filter
def field_value(material_model: Any, field: Any) -> str:
    """The value of a category-specific field of a material model, for people (MAT-010)."""
    try:
        return material_model.field_display(field)
    except AttributeError:
        return ""


class FilterPanelNode(template.Node):
    """The fields of a filter bar behind a "Filter" button, see :func:`filterpanel`."""

    def __init__(self, key: template.base.FilterExpression, nodelist: template.NodeList) -> None:
        self.key = key
        self.nodelist = nodelist

    def render(self, context: template.Context) -> str:
        """Render the button, the summary of the active filters and the fields."""
        key = str(self.key.resolve(context))
        fields = self.nodelist.render(context)
        with context.push(filter_key=key, filter_fields=SafeString(fields)):
            return context.template.engine.get_template("core/_filter_panel.html").render(context)


@register.tag
def filterpanel(parser: template.base.Parser, token: template.base.Token) -> FilterPanelNode:
    """Put the fields of a filter bar behind a button that folds them away (UIX-030).

    One pattern for every list: the search field stays in front of the tag,
    the other filters and the button that applies them go inside::

        <form method="get" class="filters">
          <div class="field grow">… search …</div>
          {% filterpanel "projects" %}
            <div class="field">… status …</div>
            <button class="btn secondary" type="submit">…</button>
          {% endfilterpanel %}
        </form>

    The key names the list: it makes the IDs of the page and the place where
    the browser remembers whether the filters of this list are open.
    Without scripts the button is not shown and every field is.
    """
    bits = token.split_contents()
    if len(bits) != 2:
        raise template.TemplateSyntaxError("filterpanel takes one argument: the key of the list")
    key = parser.compile_filter(bits[1])
    nodelist = parser.parse(("endfilterpanel",))
    parser.delete_first_token()
    return FilterPanelNode(key, nodelist)
