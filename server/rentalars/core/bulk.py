# SPDX-License-Identifier: GPL-3.0-or-later
"""Acting on ticked rows of a table.

Every table of records (``core/_table.html``) lets rows be ticked and shows a bar under the list
(``core/_table_bulk.html``). The one action every table has is *Download chosen as CSV*: :func:`bulk_csv` does not
read any data itself – it turns the ticked keys into ``?format=csv&only=1,2,3`` on the very address of the list and
redirects there, so the CSV file is made by the list's own view, with its filters, rights and shown columns
(``TableState.selected_ids``). Further actions belong to the page of the list and use the helpers here
(:func:`chosen_ids`, :func:`back`): the follow-up of projects, status and person responsible of service cases, the
download of chosen outgoing documents.
"""

from __future__ import annotations

import re
import secrets
from urllib.parse import urlsplit

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, HttpResponseRedirect, QueryDict
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from rentalars.core.tables import BULK_MAX_ROWS

#: From this many keys on, they wait in the session and the address names only a token: a web server refuses addresses
#: of more than about four thousand bytes, and a page of a thousand rows has them.
LONG_SELECTION = 150
SESSION_KEY = "bulk_selections"
_KEPT_SELECTIONS = 5


def keep_selection(request: HttpRequest, ids: list[int]) -> str:
    """Put a long selection into the session; returns the token for ``?only=t:<token>``."""
    store = dict(request.session.get(SESSION_KEY) or {})
    token = secrets.token_hex(6)
    store[token] = ids
    while len(store) > _KEPT_SELECTIONS:
        store.pop(next(iter(store)))
    request.session[SESSION_KEY] = store
    return token


def kept_selection(request: HttpRequest, token: str) -> list[int]:
    """The keys behind a token of :func:`keep_selection`; empty if the session does not know it."""
    session = getattr(request, "session", None)
    store = session.get(SESSION_KEY) if session is not None else None
    found = (store or {}).get(token) or []
    return [int(pk) for pk in found if isinstance(pk, int)][:BULK_MAX_ROWS]


#: A key of a table and the prefix of its parameters are plain words.
_WORD = re.compile(r"^[a-z0-9_]{0,40}$")


def chosen_ids(request: HttpRequest, table_key: str) -> list[int]:
    """The keys ticked in the table with this key (``sel_<key>``), without repeats, at most :data:`BULK_MAX_ROWS`."""
    found: list[int] = []
    for value in request.POST.getlist(f"sel_{table_key}"):
        if value.isascii() and value.isdigit() and len(value) < 12 and int(value) not in found:
            found.append(int(value))
        if len(found) >= BULK_MAX_ROWS:
            break
    return found


def back(request: HttpRequest, default: str = "/") -> str:
    """The page to return to: the address the bar was on (``next``), when it is one of ours."""
    target = request.POST.get("next") or ""
    # Only an address on this server that begins with "/" ("?q=1" or "foo" are no address a redirect can use).
    if target.startswith("/") and url_has_allowed_host_and_scheme(target, {request.get_host()}, request.is_secure()):
        return target
    return default


@require_POST
def bulk_csv(request: HttpRequest) -> HttpResponse:
    """Turn the ticked rows into the address of the CSV file of the list they are in, and go there."""
    table_key = request.POST.get("table", "")
    prefix = request.POST.get("prefix", "")
    # Plain words only: the table need not be known to this process (a list module is loaded with its first page).
    if not _WORD.match(table_key) or not table_key or not _WORD.match(prefix):
        return HttpResponseBadRequest(_("Unknown table."))
    target = back(request)
    ids = chosen_ids(request, table_key)
    if not ids:
        messages.warning(request, _("Tick at least one row first."))
        return redirect(target)
    parts = urlsplit(target)
    query = QueryDict(parts.query, mutable=True)
    for name in ("page", f"{prefix}page"):
        query.pop(name, None)
    query[f"{prefix}format"] = "csv"
    query[f"{prefix}only"] = (
        f"t:{keep_selection(request, ids)}" if len(ids) > LONG_SELECTION else ",".join(map(str, ids))
    )
    return HttpResponseRedirect(f"{parts.path}?{query.urlencode()}")
