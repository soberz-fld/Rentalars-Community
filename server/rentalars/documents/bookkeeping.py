# SPDX-License-Identifier: GPL-3.0-or-later
"""What belongs to bookkeeping – and is hidden while Rentalars is not the accounting program (DOK-014, DOK-055).

The setting "Use Rentalars as accounting software" (``SystemSettings.invoices_enabled``) decides whether Rentalars
only plans and offers, or also keeps the books. Switched off:

* no invoice and no cancellation is made (:mod:`rentalars.documents.services`);
* the tabs of "Buchhaltung" that are bookkeeping are gone – the incoming invoices and their capture, the open
  invoices, the bank, the EÜR with the archive and the procedure documentation, the asset register and the sales from
  stock, and the import of old projects from invoices (:func:`tabs_off`, ``documents.outgoing.tabs``);
* so are the places that lead there – the card "Anlagevermögen" of an item, the offer to take a purchase over as an
  incoming invoice, the incoming invoices in the settings;
* an address of those pages or of the API is refused: the page leads back to the start page with a hint, the API
  answers 400 ``accounting_disabled`` (:class:`BookkeepingMiddleware`).

What stays: the outgoing documents (offers, order confirmations, delivery notes and the invoices made earlier), the
monthly statement of the service cases (it shows the values to copy into the other program), the mark "Invoice
issued" in a project, and the settings of Lexware Office and DATEV. Nothing is deleted: switched on again, everything
is there as it was.
"""

from __future__ import annotations

from collections.abc import Callable

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext as _

#: Names of the pages that are bookkeeping – ``namespace:name``; a name ending in ``*`` stands for all that begin so.
PAGES = frozenset(
    {
        "incoming:*",
        "documents:payments",
        "documents:open_items",
        "documents:bank*",
        "documents:euer",
        "documents:archive*",
        "documents:audit_export*",
        "documents:procedure",
        "material:asset_register",
        "material:sales",
        "material:sale_*",
        "material:item_asset",
        "material:item_sell",
        "projects:legacy*",
    }
)

#: The same for the API (``api:name``).
API = frozenset(
    {
        "api:incoming-*",
        "api:document-payments",
        "api:payment-void",
        "api:accounting-open-items",
        "api:accounting-bank-*",
        "api:accounting-euer",
        "api:accounting-archive*",
        "api:accounting-audit-export",
        "api:accounting-procedure",
        "api:material-item-asset",
        "api:material-item-sale-preview",
        "api:material-item-sell",
        "api:asset-register*",
        "api:stock-sale*",
        "api:legacy-import*",
    }
)


def is_bookkeeping(view_name: str) -> bool:
    """Whether the page or API address with this name (``namespace:name``) is bookkeeping."""
    for pattern in PAGES | API:
        if pattern.endswith("*"):
            if view_name.startswith(pattern[:-1]):
                return True
        elif view_name == pattern:
            return True
    return False


def bookkeeping_on() -> bool:
    """Whether Rentalars keeps the books: the setting "Use Rentalars as accounting software"."""
    from rentalars.documents.services import invoices_enabled

    return invoices_enabled()


def off_message() -> str:
    """What a refused page or call says."""
    return _(
        "Bookkeeping is not done in Rentalars: the setting “Use Rentalars as accounting software” is off "
        "(Settings → Company data and settings)."
    )


def _api_caller_known(request: HttpRequest, view_func: Callable[..., HttpResponse]) -> bool:
    """Whether the call of the API comes from a logged-in user or a valid token, judged as the view itself would."""
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return True
    if not request.headers.get("Authorization"):
        return False
    from rest_framework.request import Request

    view_class = getattr(view_func, "cls", None) or getattr(view_func, "view_class", None)
    if view_class is None:
        return False
    try:
        caller = Request(request, authenticators=view_class().get_authenticators())
        return bool(caller.user is not None and caller.user.is_authenticated)
    except Exception:  # AuthenticationFailed and the like: the view answers 401 itself
        return False


class BookkeepingMiddleware:
    """Refuse the pages and the API of bookkeeping while the setting is off (DOK-055)."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Nothing to do before the view is known."""
        return self.get_response(request)

    def process_view(
        self, request: HttpRequest, view_func: Callable[..., HttpResponse], view_args: tuple, view_kwargs: dict
    ) -> HttpResponse | None:
        """Answer instead of the view if it is bookkeeping and the books are not kept here."""
        match = request.resolver_match
        if match is None or not is_bookkeeping(match.view_name) or bookkeeping_on():
            return None
        if match.view_name.startswith("api:"):
            # Not logged in, or a token that does not hold: the API says so itself (401), not that a function is off.
            if not _api_caller_known(request, view_func):
                return None
            return JsonResponse({"error": {"code": "accounting_disabled", "message": off_message()}}, status=400)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None  # the login gate answers
        messages.info(request, off_message())
        if request.headers.get("HX-Request"):
            # A page that updates itself (a poll) would swap the start page into its place: leave the page instead.
            return HttpResponse(headers={"HX-Redirect": reverse("core:home")})
        return redirect(reverse("core:home"))
