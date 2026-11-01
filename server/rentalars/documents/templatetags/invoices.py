# SPDX-License-Identifier: GPL-3.0-or-later
"""The state of the invoice of a project, in its head and on the tab "Dokumente" (DOK-015).

``{% load invoices %}{% invoice_state project %}`` shows, to whoever may see
prices, whether the project is invoiced: the invoice made in Rentalars,
"Rechnung gestellt" ticked by hand, "Keine Rechnung" – or that it is still
open, with the tick box "Rechnung gestellt" where invoices are written in
another program. In the head it shows from "Wieder im Lager" on (a service
case: done), so that the head of a planned project costs no query for it;
``elsewhere`` shows it in the statuses the head does not (the tab
"Dokumente", which has the head above it).
"""

from __future__ import annotations

from typing import Any

from django import template

from rentalars.accounts.rights import SpecialRight, request_rights
from rentalars.documents import invoice_reminders
from rentalars.projects.access import ProjectAccess
from rentalars.projects.models import CaseStatus, ProjectStatus

register = template.Library()

#: In the head the state shows once the material is back – or a service case is done.
_SHOWN_IN_HEAD = (ProjectStatus.RETURNED, ProjectStatus.CLOSED)


@register.inclusion_tag("documents/_invoice_state.html", takes_context=True)
def invoice_state(context: Any, project: Any, elsewhere: bool = False) -> dict[str, Any]:
    """What the invoice of a project is, and what this user may do about it (DOK-015)."""
    request = context["request"]
    rights = request_rights(request)
    hidden = {"shown": False}
    if not rights.has(SpecialRight.PRICES) or not getattr(project, "shows_planning", True):
        return hidden
    if project.is_service_case:
        in_head = project.case_status == CaseStatus.DONE
    else:
        in_head = project.status in _SHOWN_IN_HEAD
    if in_head == elsewhere:
        return hidden
    if not invoice_reminders.gets_invoice(project):
        return hidden
    # DOK-016: also the monthly invoice that bills a service case.
    invoice = invoice_reminders.invoices_of(project).order_by("-created_at").first()
    state = invoice_reminders.state_of(project, has_invoice=invoice is not None)
    if state == invoice_reminders.InvoiceState.NONE:
        return hidden  # closed earlier: its invoice is not followed
    if invoice is not None and not _may_open(request, rights, invoice):
        # DOK-015 (DOK-016): a monthly invoice also bills other cases; whoever may not open all of
        # them sees "Rechnung gestellt", not its number – as on the tab "Dokumente".
        invoice = None
    access = getattr(project, "access", ProjectAccess.NONE)
    return {
        "shown": True,
        "request": request,
        "project": project,
        "state": state,
        "invoice": invoice,
        "mark": project.invoice_status,
        "invoices_on": invoice_reminders.invoices_on(),
        "finished": invoice_reminders.is_finished(project),
        "may_change": access >= ProjectAccess.EDIT,
    }


def _may_open(request: Any, rights: Any, invoice: Any) -> bool:
    """Whether the user may open the invoice: read access to its project and to every case it bills (DOK-016)."""
    from rentalars.documents.services import billed_ids
    from rentalars.projects.access import access_of_many

    projects = {invoice.project_id, *billed_ids(invoice)}
    levels = access_of_many(rights, request.user, sorted(projects))
    return all(levels.get(pk, ProjectAccess.NONE) >= ProjectAccess.READ for pk in projects)
