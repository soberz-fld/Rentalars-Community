# SPDX-License-Identifier: GPL-3.0-or-later
"""On the page of a service case: the monthly statements it is in (DOK-016).

``{% load statements %}{% statement_hint case %}`` shows, to whoever may see
prices (AUT-019), "Abgerechnet mit der Monatsrechnung RE-2027-0012 (März
2027)", "Als abgerechnet markiert mit der Monatsabrechnung März 2027" or "In
der Monatsabrechnung März 2027 (Entwurf)" – linked to the statement for who
may open it.

DOK-015, DOK-016 (as the head of the case): the number of the
monthly invoice only for whoever may open it – read access to its project and
to every case it bills (``invoices._may_open``); otherwise "Abgerechnet mit
einer Monatsrechnung (März 2027)" without the number.
"""

from __future__ import annotations

from typing import Any

from django import template

from rentalars.accounts.rights import SpecialRight, request_rights
from rentalars.documents.templatetags.invoices import _may_open

register = template.Library()


@register.inclusion_tag("documents/_statement_hint.html", takes_context=True)
def statement_hint(context: Any, case: Any) -> dict[str, Any]:
    """The statements of a case, newest month first – nothing without the price right or for a project."""
    from rentalars.documents import statements

    request = context["request"]
    rights = request_rights(request)
    if not rights.has(SpecialRight.PRICES) or not getattr(case, "is_service_case", False):
        return {"shown": False}
    found = statements.statements_of(case)
    return {
        "shown": bool(found),
        "items": [
            {
                "statement": statement,
                "month": statements.month_label(statement.month),
                # The number names an invoice that also bills cases the user may not see.
                "number_shown": statement.invoice_id is not None and _may_open(request, rights, statement.invoice),
            }
            for statement in found
        ],
        "may_open": statements.may_use(rights),
    }
