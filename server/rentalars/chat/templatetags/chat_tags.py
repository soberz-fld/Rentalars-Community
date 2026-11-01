# SPDX-License-Identifier: GPL-3.0-or-later
"""The text of a chat message as HTML (UIX-010): links, line breaks, mentions in bold."""

from __future__ import annotations

import re
from typing import Any

from django import template
from django.utils.html import urlize
from django.utils.safestring import SafeString, mark_safe

from rentalars.chat.services import display_name

register = template.Library()


@register.filter
def chat_text(message: Any) -> SafeString:
    """Escape the text, make addresses into links, mark the mentioned names and keep the line breaks."""
    html = urlize(message.text, nofollow=True, autoescape=True)
    names = sorted(
        {name for user in message.mentioned.all() for name in (display_name(user), user.username) if name},
        key=len,
        reverse=True,
    )
    if names:
        # Only an "@" at the start of a word: never inside a link or a mail address.
        pattern = re.compile(
            r"(?<![^\s(>])@(" + "|".join(re.escape(_escaped(name)) for name in names) + r")(?![\w])", re.IGNORECASE
        )
        html = pattern.sub(lambda hit: f'<strong class="mention">@{hit.group(1)}</strong>', html)
    return mark_safe(html.replace("\n", "<br>\n"))  # noqa: S308 – escaped by urlize above


def _escaped(name: str) -> str:
    from django.utils.html import escape

    return str(escape(name))
