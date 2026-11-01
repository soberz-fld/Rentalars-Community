# SPDX-License-Identifier: GPL-3.0-or-later
"""Template tags of the correspondence (EML-055; EML-029, AUT-033).

``{% reads_correspondence project as reads %}`` – whether the user of the page
reads any of the correspondence of the project: the tab "Korrespondenz" of
the head of every project page. The answer is that of the pages themselves
(``mail.locks.correspondence_of``): the correspondence right with read
access, working on the service case – or (EML-055) being planned in the
crew, for the open messages.
"""

from __future__ import annotations

from typing import Any

from django import template

from rentalars.mail.locks import correspondence_of

register = template.Library()


@register.simple_tag(takes_context=True)
def reads_correspondence(context: Any, project: Any) -> bool:
    """Whether the user of the request reads any message of the project's correspondence."""
    request = context.get("request")
    if request is None or project is None or getattr(project, "pk", None) is None:
        return False
    return correspondence_of(request, project).reads_any
