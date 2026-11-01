# SPDX-License-Identifier: GPL-3.0-or-later
"""The way back: the page a user came from (UIX-011).

Every page below the start pages of the sections – a product, a material
item, a form – shows "Back" in its top left corner. It leads to the view the
user had before, exactly as it was: the list with its filter, its sort order
and its page, or the project the product was opened from.

The browser's own back button cannot do this reliably. After "open product,
edit, save" it leads back into the form; after a filter was changed three
times it needs three steps. The application therefore keeps the way itself,
as a short list of addresses called the trail:

* A **start page** (reached from the navigation, the search field or the tabs
  of a section) begins a new trail.
* A page that is **not yet on the trail** is added to its end.
* A page that **is on the trail already** cuts the trail back to itself. This
  is what makes "back" a way back and not a circle: list, product, model,
  the same product again – the trail is "list, product" once more.
* **The same page with another query string** (next page of a list, another
  filter) replaces its entry.
* **The tabs of a record** – a project, a person, a product, a material
  model or item – count as one page; "back" leaves the record.
* A **form that was sent and led on to another page** is taken off the trail:
  there is nothing to go back to in a form that has been saved.
* **The page a click comes from** (the ``Referer``) is where the trail ends before the new page is added
  (back in the browser; UIX-055). The browser's own back button brings a page back from its memory without asking
  the server (back/forward cache), so the trail still ends at the page the user has just left: list, product,
  browser back to the list, another product – "Back" would lead to the first product. The click on the second
  product says it comes from the list, and the trail is cut back to the list first.

"Back" then is simply the entry before the last one.

The trail lives in a signed cookie, not in the session: the session is a
database row, and writing it for every page a user looks at would be the
only write of an otherwise reading request. A cookie is per browser, so two
tabs share one trail. A link on a page is fixed when the page is delivered;
it stays right however the other tab moves on.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from typing import Any
from urllib.parse import unquote, urlsplit

from django.conf import settings
from django.core import signing
from django.http import HttpRequest, HttpResponse
from django.urls import Resolver404, ResolverMatch, resolve
from django.utils.encoding import escape_uri_path
from django.utils.http import url_has_allowed_host_and_scheme

COOKIE_NAME = "rentalars_trail"
_SALT = "rentalars.core.trail"
#: Longer ways are cut at their beginning; nobody walks nine steps back.
MAX_ENTRIES = 8
#: Addresses longer than this are kept without their query string, so that
#: the cookie stays far below the four kilobytes a browser accepts.
MAX_ADDRESS_LENGTH = 300

#: Pages that are reached from the parts of the screen that are always there:
#: the navigation, the search field, the tabs of a section. A trail starts
#: here, and these pages show no "Back".
START_PAGES = frozenset(
    {
        "core:home",
        "core:search",
        "core:administration",
        "accounts:account",
        # UIX-029: the manual, linked at the foot of the sidebar.
        "core:about",  # The notices of the licence are reached from the layout, like the manual.
        "core:manual",
        "core:manual_chapter",  # A chapter has its own way on – "previous", "next", the list of chapters.
        "projects:list",
        "projects:open_items",
        # UIX-041: every tab reached from the navigation is a start page – service cases, the expenses of
        # "Personnel" and "My expenses" among them. tests/ui/test_back_and_page_size.py walks
        # every entry of the navigation and every tab and fails for a page that is missing here.
        "projects:cases",
        # DOK-019: the tabs of "Buchhaltung" – "Ausgangsbelege" and "Monatsabrechnung" (DOK-016, in Projekte).
        "documents:outgoing",
        "documents:statements",
        # Depreciation, used sale from stock: the tabs "Anlagenspiegel" and "Verkäufe aus Bestand".
        "material:asset_register",
        "material:sales",
        # Incoming invoices, import of old projects: the tabs "Eingangsrechnungen" and "Altprojekte importieren".
        "incoming:list",
        "incoming:capture",  # The tab "Beleg erfassen"
        # DOK-048, DOK-045, DOK-043: the tabs "Offene Posten", "EÜR" and "Archiv".
        "documents:open_items",
        "documents:bank",  # DOK-050
        "documents:euer",
        "documents:archive",
        "projects:legacy",
        "timetracking:expense_report",
        "timetracking:my_expenses",
        # UIX-041: "Zeit erfassen" in the sidebar and the top bar opens the quick entry as a page without scripts.
        "timetracking:quick",
        "availability:shortages",
        "material:model_list",
        "material:item_list",
        "material:inspections",
        "material:fleet",  # LOG-002: the tab "Fuhrpark"
        # MAT-068, MAT-070: the tabs "Offene Punkte" with their sub-tabs and "Audit"
        "material:open_without_product",
        "material:open_todos",
        "material:open_audits",
        "material:audit",
        "material:import",
        "products:list",
        "customers:list",
        "customers:venue_list",
        "personnel:person_list",
        "personnel:availability",
        "personnel:job_function_list",
        # UIX-026: approving and the report are tabs of "Personnel"; the own times a tab of "My area".
        "timetracking:my_times",
        "timetracking:approval",
        "timetracking:report",
        # The tabs of "Planning" are sections of their own, reached from the navigation (UIX-022).
        "schedule:calendar",
        "schedule:timeline",
        "schedule:products",
        "schedule:personnel",
        "schedule:follow_ups",  # VFG-034
        # PRJ-115, MAT-053: the tabs of "Auswertung".
        "projects:report",
        "projects:report_material",
        "mail:unknown_list",
        "notifications:list",
        # The tabs of "My area" (UIX-026).
        "projects:my_deployments",  # UIX-043: the first tab
        "personnel:own_availability",
        "personnel:own_profile",
        "projects:my_cases",  # PRJ-108: the service cases one takes part in
    }
)

#: Tabs of one record. They share one place on the trail, so that "Back"
#: leaves the record instead of walking through its tabs.
TAB_GROUPS = {
    "projects:detail": "project",
    "projects:overview": "project",  # PRJ-104 (tab order; PRJ-125): the redirect that opens a project
    "projects:price_overview": "project",
    "projects:deployment": "project",
    "projects:members": "project",
    "projects:history": "project",
    "projects:family": "project",
    "projects:course": "project",
    "documents:list": "project",
    "mail:project_mails": "project",
    "packing:packlist": "project",
    "packing:family": "project",
    "chat:project": "project",  # UIX-010
    # The tabs of a person, a product, a material model and a material item (UIX-027).
    "personnel:person_detail": "person",
    "personnel:person_availability": "person",
    "personnel:person_timeline": "person",
    "products:detail": "product",
    "products:timeline": "product",
    "material:model_detail": "model",
    "material:model_files": "model",
    "material:model_timeline": "model",
    "material:item_detail": "item",
    "material:item_timeline": "item",
    "material:item_inspections": "item",
    "material:item_files": "item",
    "material:item_history": "item",
}

#: Parts of the site that are not pages of the application: the API answers
#: programs, Django's administration interface has its own navigation.
_IGNORED_NAMESPACES = frozenset({"admin", "api"})

Trail = list[tuple[str, str]]


def is_start_page(request: HttpRequest) -> bool:
    """Tell whether the requested page begins a trail (and shows no "Back")."""
    match = request.resolver_match
    return match is not None and match.view_name in START_PAGES


@lru_cache(maxsize=256)
def _resolve(path: str) -> ResolverMatch | None:
    """Resolve a path (back in the browser; UIX-055); the pages a click comes from are few and come again and again."""
    try:
        return resolve(path)
    except Resolver404:
        return None


def referring_page(request: HttpRequest) -> tuple[ResolverMatch, str] | None:
    """The page of this site a request was made from, with its address; ``None`` if there is none.

    The application sends ``Referrer-Policy: same-origin``, so a click from one of its pages names that page,
    query string and all. Anything else – no header, another site, an address that is no page, one that is longer
    than :data:`MAX_ADDRESS_LENGTH` even without its query – counts as none: eight entries of the trail stay far
    below the four kilobytes of a cookie. The address is kept in the form a link needs; the page is looked up by
    its decoded path, which is what ``request.path`` holds.
    """
    referer = request.META.get("HTTP_REFERER", "")
    if not referer:
        return None
    parts = urlsplit(referer)
    if parts.netloc and parts.netloc != request.get_host():
        return None
    if len(parts.path) > MAX_ADDRESS_LENGTH:
        return None
    path = escape_uri_path(unquote(parts.path))
    match = _resolve(unquote(parts.path))
    if match is None or _IGNORED_NAMESPACES.intersection(match.namespaces) or len(path) > MAX_ADDRESS_LENGTH:
        return None
    address = f"{path}?{parts.query}" if parts.query else path
    if len(address) > MAX_ADDRESS_LENGTH:
        address = path
    return match, address


def follow_referer(trail: Trail, referer: tuple[ResolverMatch, str] | None) -> Trail:
    """The trail as it stands in the browser: it ends at the page the user clicked on (back in the browser; UIX-055).

    A page restored by the browser's back button does not ask the server, so the trail may still end at a page
    the user has left meanwhile. If the page of the click is on the trail, everything after it goes; if it is a
    start page that is not, the trail begins there anew. Any other page that is not on the trail – a form that
    was saved, a page whose entry was cut – changes nothing.

    Example: the trail is "list, product 5"; the user is back on the list and opens product 7. The click comes
    from the list: the trail becomes "list", and product 7 is added to it.
    """
    if referer is None:
        return trail
    match, address = referer
    place = _place(match, unquote(urlsplit(address).path))  # the place of a page is its decoded path
    for index, (known, _address) in enumerate(trail):
        if known == place:
            return trail if index == len(trail) - 1 else [*trail[:index], (place, address)]
    if match.view_name in START_PAGES:
        return [(place, address)]
    return trail


def _place(match: ResolverMatch, path: str) -> str:
    """Name the place a page takes on the trail: its path, or the record its tab belongs to."""
    group = TAB_GROUPS.get(match.view_name)
    if group is not None:
        return f"{group}:{match.kwargs.get('pk')}"
    return path


def _read(request: HttpRequest) -> Trail:
    """Read the trail from the cookie; anything unexpected counts as no trail.

    The cookie is signed, so its content is what this application wrote.
    The addresses are checked all the same, because they end up in a link:
    only paths on this site pass.
    """
    raw = request.COOKIES.get(COOKIE_NAME)
    if not raw:
        return []
    try:
        entries = signing.loads(raw, salt=_SALT)
    except signing.BadSignature:
        return []
    trail: Trail = []
    if not isinstance(entries, list):
        return []
    for entry in entries[-MAX_ENTRIES:]:
        if not (isinstance(entry, list) and len(entry) == 2 and all(isinstance(part, str) for part in entry)):
            return []
        place, address = entry
        if not address.startswith("/") or not url_has_allowed_host_and_scheme(address, allowed_hosts=None):
            return []
        trail.append((place, address))
    return trail


def _write(response: HttpResponse, trail: Trail) -> None:
    """Store the trail in the cookie; it ends with the browser session."""
    response.set_cookie(
        COOKIE_NAME,
        signing.dumps([list(entry) for entry in trail], salt=_SALT, compress=True),
        secure=settings.SESSION_COOKIE_SECURE,
        httponly=True,
        samesite="Lax",
    )


def step(trail: Trail, place: str, address: str, *, starts_here: bool) -> Trail:
    """Return the trail after the user has arrived at a page.

    Args:
        trail: The trail so far.
        place: The place of the page, see :func:`_place`.
        address: Its address with the query string.
        starts_here: Whether the page is a start page.

    Example: on the trail "products (page 3), product 5, model 9" the user
    opens product 5 again. The result is "products (page 3), product 5".
    """
    if len(address) > MAX_ADDRESS_LENGTH:
        address = address.split("?", 1)[0]
    if starts_here:
        return [(place, address)]
    for index, (known, _address) in enumerate(trail):
        if known == place:
            return [*trail[:index], (place, address)]
    return [*trail, (place, address)][-MAX_ENTRIES:]


class TrailMiddleware:
    """Keep the trail up to date and tell each page where "Back" leads (UIX-011).

    Only pages count: a request of a logged-in user for a whole HTML page
    that was delivered. Parts of pages fetched by htmx, downloads, the API
    and error pages leave the trail as it is.

    The view finds the address for "Back" in ``request.back_url`` (``None``
    if there is no page before this one); the layout shows the link.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        """Store the next handler of the chain."""
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Pass the request on and store the trail if a page was delivered."""
        request.back_url = None  # type: ignore[attr-defined]
        response = self.get_response(request)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            if COOKIE_NAME in request.COOKIES:
                response.delete_cookie(COOKIE_NAME, samesite="Lax")
            return response
        arrived: Trail | None = getattr(request, "_trail_on_arrival", None)
        if arrived is not None and response.status_code == 200 and _is_html(response):
            if arrived != getattr(request, "_trail_before", None):
                _write(response, arrived)
        elif request.method == "POST" and 300 <= response.status_code < 400 and request.resolver_match is not None:
            # A form was sent and leads on: take it off the trail.
            trail = _read(request)
            if trail and trail[-1][0] == _place(request.resolver_match, request.path):
                _write(response, trail[:-1])
        return response

    def process_view(
        self, request: HttpRequest, view: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> None:
        """Work out, before the view runs, where "Back" leads from the requested page."""
        match = request.resolver_match
        user = getattr(request, "user", None)
        if (
            request.method != "GET"
            or match is None
            or user is None
            or not user.is_authenticated
            or request.headers.get("HX-Request")
            or _IGNORED_NAMESPACES.intersection(match.namespaces)
            or len(request.path) > MAX_ADDRESS_LENGTH  # An address that long is kept off the cookie
        ):
            return
        before = _read(request)
        followed = follow_referer(before, referring_page(request))  # The trail as the browser shows it
        arrived = step(
            followed, _place(match, request.path), request.get_full_path(), starts_here=is_start_page(request)
        )
        request._trail_before = before  # type: ignore[attr-defined]
        request._trail_on_arrival = arrived  # type: ignore[attr-defined]
        request.back_url = arrived[-2][1] if len(arrived) > 1 else None  # type: ignore[attr-defined]


def _is_html(response: HttpResponse) -> bool:
    """Tell whether a response is a page (and not a PDF, a JSON answer or a file)."""
    return response.get("Content-Type", "").startswith("text/html")
