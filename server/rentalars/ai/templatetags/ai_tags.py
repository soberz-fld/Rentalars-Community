# SPDX-License-Identifier: GPL-3.0-or-later
"""Template tags of the AI: the places on the mail pages where it appears (EML-040, ADM-017).

They let the pages of the mail module show the AI without the mail module
knowing about it:

* ``{% ai_summary_slot project %}`` – the block "Zusammenfassung" on the
  correspondence page, loaded after the page (it reads all mails);
* ``{% ai_draft_box project answer_to %}`` – "Entwurf vorschlagen" in the mail
  form, for who may write mails, when reply drafts are switched on.
"""

from __future__ import annotations

from typing import Any

from django import template

from rentalars.accounts.rights import request_rights
from rentalars.ai.client import is_switched_on
from rentalars.ai.models import Use
from rentalars.mail.services import may_read_all_mail, may_write_mail

register = template.Library()


@register.inclusion_tag("ai/_summary_slot.html", takes_context=True)
def ai_summary_slot(context: Any, project: Any) -> dict[str, Any]:
    """The place of the block "Zusammenfassung" (EML-050); empty for who may not read the correspondence.

    EML-055: overview and summary read every message – only for who reads those with lock as well.
    """
    request = context.get("request")
    allowed = request is not None and may_read_all_mail(request_rights(request))
    return {"project": project, "allowed": allowed}


@register.inclusion_tag("ai/_draft_box.html", takes_context=True)
def ai_draft_box(context: Any, project: Any, answer_to: Any = None) -> dict[str, Any]:
    """The button “Entwurf vorschlagen”, if reply drafts are switched on and the user may write mails (ADM-017).

    EML-055: the draft reads the thread with its messages with lock – only for who reads those as well.
    """
    request = context.get("request")
    rights = request_rights(request) if request is not None else None
    shown = rights is not None and may_write_mail(rights) and may_read_all_mail(rights) and is_switched_on(Use.DRAFT)
    return {"project": project, "answer_to": answer_to, "shown": shown}
