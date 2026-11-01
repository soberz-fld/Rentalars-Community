# SPDX-License-Identifier: GPL-3.0-or-later
"""Template helper of the master data lists as tables (UIX-040, ``core.admin_tables``)."""

from __future__ import annotations

from typing import Any

from django import template

register = template.Library()


@register.filter
def item_at(items: Any, index: int) -> Any:
    """``items[index]``, or ``None`` past the end – the heading of the group of a row."""
    try:
        return items[index]
    except (IndexError, KeyError, TypeError):
        return None
