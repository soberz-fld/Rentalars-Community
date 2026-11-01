# SPDX-License-Identifier: GPL-3.0-or-later
"""The row of actions in the head of every project page (PRJ-078).

``{% load project_actions %}{% project_actions project %}`` renders, in this
order: "Projekt bearbeiten", the status as a drop-down list, the document
that usually comes next with the other kinds behind it, and then setting a
follow-up (PRJ-105), duplicating, saving as template and adding a
subproject. Everything follows the user's rights and access to this
project; nothing costs a database query – the head is on every tab, and the
planning page has a tight limit of queries (scenario 11).
"""

from __future__ import annotations

from typing import Any

from django import template

from rentalars.accounts.rights import Module, SpecialRight, request_rights
from rentalars.documents.models import PRICED_KINDS, DocumentKind
from rentalars.documents.services import makeable_kinds
from rentalars.projects.access import ProjectAccess
from rentalars.projects.models import ProjectStatus

register = template.Library()

#: PRJ-078: the document a project usually needs next in each status – "Anfrage: Angebot, Zurück: Rechnung".
NEXT_DOCUMENT = {
    ProjectStatus.INQUIRY: DocumentKind.OFFER,
    ProjectStatus.OPTION: DocumentKind.OFFER,
    ProjectStatus.CONFIRMED_OPEN: DocumentKind.ORDER_CONFIRMATION,
    ProjectStatus.CONFIRMED: DocumentKind.ORDER_CONFIRMATION,
    ProjectStatus.OUT: DocumentKind.DELIVERY_NOTE,
    ProjectStatus.RETURNED: DocumentKind.INVOICE,
    ProjectStatus.CLOSED: DocumentKind.INVOICE,
}


def suggested_document(status: str, kinds: list[DocumentKind]) -> DocumentKind | None:
    """The document to suggest for a project in this status, among the kinds the user may make (PRJ-078).

    Where the usual one is not possible – a subproject gets its offers,
    order confirmations and invoices through its whole project, without
    the price right there are no priced documents, and with invoices
    switched off (DOK-014) there is no invoice –, a confirmed or running
    project is offered its delivery note; otherwise nothing is suggested and
    all kinds stay in the list.
    """
    usual = NEXT_DOCUMENT.get(status)
    if usual in kinds:
        return usual
    if status in (ProjectStatus.CONFIRMED_OPEN, ProjectStatus.CONFIRMED, ProjectStatus.OUT):
        if DocumentKind.DELIVERY_NOTE in kinds:
            return DocumentKind.DELIVERY_NOTE
    return None


@register.inclusion_tag("projects/_head_actions.html", takes_context=True)
def project_actions(context: Any, project: Any) -> dict[str, Any]:
    """What the head of a project page offers this user (PRJ-078)."""
    request = context["request"]
    rights = request_rights(request)
    access = getattr(project, "access", ProjectAccess.NONE)
    plans = bool(project.shows_planning)
    edits = access >= ProjectAccess.EDIT
    if project.is_service_case:
        # PRJ-090: a service case is edited, followed up and turned into a project – no status list, no
        # documents to make, no copies, no subprojects. Its status is set on its page.
        changes = edits and plans and rights.can_write(Module.PROJECTS)
        # AUT-033 (PRJ-108): the person responsible and the people taking part work on it – not converting it.
        works = bool(getattr(project, "may_work_on_case", False))
        return {
            "request": request,
            "project": project,
            "plans": plans,
            "may_edit": changes or works,
            "may_convert": changes,
            "may_follow_up": (changes or works) and project.follow_up_on is None,
        }
    statuses: list[tuple[str, str]] = []
    kinds: list[DocumentKind] = []
    if edits and plans:
        statuses = [
            (status, str(ProjectStatus(status).label))
            for status in project.allowed_next_statuses
            if not (project.status == ProjectStatus.CLOSED and not rights.has(SpecialRight.REOPEN_PROJECTS))
        ]
        # PRJ-045: a part gets its priced documents through its whole project.
        priced_allowed = rights.has(SpecialRight.PRICES) and not project.parent_id
        # DOK-014: no invoice while invoices are switched off – nor its suggestion for a returned project.
        kinds = [kind for kind in makeable_kinds() if priced_allowed or kind not in PRICED_KINDS]
    suggested = suggested_document(project.status, kinds)
    writes = rights.can_write(Module.PROJECTS)
    return {
        "request": request,
        "project": project,
        "plans": plans,
        # The project itself only while it is not closed.
        "may_edit": edits and writes and not project.is_locked,
        "may_copy": plans and writes,
        "may_add_part": edits and writes and plans and not project.is_locked and not project.parent_id,
        # PRJ-105: in every status, a closed project too; shown while the project has no follow-up yet.
        "may_follow_up": edits and writes and plans and project.follow_up_on is None,
        "statuses": statuses,
        "suggested": suggested.value if suggested else "",
        "suggested_label": str(DocumentKind(suggested).label) if suggested else "",
        "other_kinds": [(kind.value, str(kind.label)) for kind in kinds if kind != suggested],
    }
