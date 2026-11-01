# SPDX-License-Identifier: GPL-3.0-or-later
"""Values every template can use: rights, navigation, version."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.http import HttpRequest
from django.utils import timezone
from django.utils.functional import SimpleLazyObject

from rentalars import CREDIT_NAME, CREDIT_URL
from rentalars.accounts.rights import Module, SpecialRight, request_rights
from rentalars.core.changes import watch_keys
from rentalars.core.models import CompanyProfile
from rentalars.core.navigation import current_entry, entries_for
from rentalars.core.trail import is_start_page
from rentalars.documents.bookkeeping import bookkeeping_on
from rentalars.notifications.services import unread_count
from rentalars.projects.access import person_of


def application(request: HttpRequest) -> dict[str, Any]:
    """Provide rights and navigation to all templates.

    ``rights`` is the same object the views check, so a template can never
    show a link the view behind it would refuse – and hiding a link is never
    the only protection (AUT-020).
    """
    # UIX-031: who made Rentalars, under the version in the menu and below the login.
    credit = {"name": CREDIT_NAME, "url": CREDIT_URL}
    if not hasattr(request, "user") or not request.user.is_authenticated:
        return {"rentalars_version": settings.RENTALARS_VERSION, "rentalars_credit": credit}
    rights = request_rights(request)
    # UIX-026: "My area" with the own pages is for accounts that are a person. The person comes
    # with the user in the same query (accounts.backends), so asking costs nothing.
    own_person = person_of(request.user)
    # DOK-055: without "Use Rentalars as accounting software" the sections of bookkeeping are left out.
    books = bookkeeping_on()
    entries = entries_for(rights, has_person=own_person is not None, bookkeeping=books)
    current = current_entry(entries, request.path)
    # UIX-011: "Back" leads to the view the user came from. Whoever arrives
    # without a way behind them – through a bookmark or a link in a mail –
    # is offered the start page of the section instead.
    back_url = getattr(request, "back_url", None)
    if back_url is None and current is not None and not is_start_page(request):
        start = current.start_for(request.path)
        if start != request.path:
            back_url = start
    return {
        "rentalars_version": settings.RENTALARS_VERSION,
        "rentalars_credit": credit,
        "bookkeeping_on": books,  # DOK-055: templates leave out the places that lead to bookkeeping
        "company_name": _company_name(request),
        "rights": rights,
        "navigation": entries,
        "current_navigation": current,
        "own_person": own_person,
        "back_url": back_url,
        # ZEI-003: the quick entry is offered on every page to everybody who records times.
        "can_record_time": rights.can_write(Module.TIME_TRACKING),
        "can_see_prices": rights.has(SpecialRight.PRICES),
        # Lists over all projects (stock, shortages) only make sense to those who see them all (AUT-017).
        "all_projects_visible": not rights.is_limited_to_assigned_projects(Module.PROJECTS),
        # UIX-005: the count on the bell.
        "unread_notifications": unread_count(request.user),
        # UIX-020: what the page shows, so that it can follow changes.
        "watch_keys": ",".join(watch_keys(request)),
        "today": timezone.localdate(),
        "can_see_purchase_prices": rights.has(SpecialRight.PURCHASE_PRICES),
        # Templates cannot call methods with arguments, so the answers are
        # prepared: {% if can.write.projects %} … {% endif %}
        "can": {
            "read": {module: rights.can_read(module) for module in Module.values},
            "write": {module: rights.can_write(module) for module in Module.values},
            "delete": {module: rights.can_delete(module) for module in Module.values},
            "special": {right: rights.has(right) for right in SpecialRight.values},
            # AUT-031: whether the planning of any project opens – "Offene Punkte" and the shortages need it.
            "planning": rights.reads_planning,
        },
    }


def _company_name(request: HttpRequest) -> Any:
    """The company under the name in the menu (UIX-032).

    The user of the session brings it along in the same query
    (``accounts.backends``). A user that came another way reads it once,
    and only on a page that shows the menu.
    """
    if hasattr(request.user, "menu_company_name"):
        return request.user.menu_company_name or ""
    return SimpleLazyObject(lambda: CompanyProfile.load().name)
