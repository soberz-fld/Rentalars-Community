# SPDX-License-Identifier: GPL-3.0-or-later
"""Helpers for list pages: paging driven by the address (UIX-004).

All state of a list – filters, sort order, page, entries per page – lives in
the query string. A filtered view can therefore be bookmarked or sent to a
colleague as a link. Columns and sorting are the business of
:mod:`rentalars.core.tables` (UIX-015).
"""

from __future__ import annotations

import datetime
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.core.paginator import Page, Paginator
from django.db.models import QuerySet
from django.db.models.query import ModelIterable
from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.translation import gettext

from rentalars.core.money import group_thousands

DEFAULT_PAGE_SIZE = 50
#: The numbers of entries per page offered as links (UIX-012).
PAGE_SIZES = (25, 50, 100, 200)
#: UIX-050 (UIX-012): the bounds of a number typed by the user. Fewer than 5 rows make no
#: list; more than 1,000 rows on one page would be a simple way to keep the server busy.
MIN_PAGE_SIZE = 5
MAX_PAGE_SIZE = 1000
#: The parameter in the address that names the choice: ``?per_page=100``.
PAGE_SIZE_PARAMETER = "per_page"
#: The former cookie that remembered the last choice for every list of a browser. The choice is
#: remembered per user and list (UIX-050, ``TablePreference.page_size``); :class:`PageSizeMiddleware` removes the cookie.
PAGE_SIZE_COOKIE = "rentalars_page_size"


class LeanPaginator(Paginator):
    """A paginator that finds the rows of a page first and loads their details afterwards.

    A list of material items shows product, model, category, supplier and
    storage location of every row. Asked for "rows 1 to 50 with all of
    that, sorted by ID", the database joins all 20,000 items with their
    details before it picks the first 50. This paginator asks in two steps:

    1. the IDs of the rows of the page – only what filter and sort order need;
    2. those rows with everything the list declares (joins, annotations,
       prefetches) – for 50 IDs that is a matter of milliseconds.

    Both steps use the same filters and the same sort order, so the result
    is the same as that of a plain :class:`~django.core.paginator.Paginator`.
    Lists that are not model querysets (plain lists, ``values()``) are sliced
    as usual.
    """

    def page(self, number: int | str) -> Page[Any]:
        """Return the page with the given number (starting at 1)."""
        number = self.validate_number(number)
        bottom = (number - 1) * self.per_page
        top = bottom + self.per_page
        if top + self.orphans >= self.count:
            top = self.count
        rows = self.object_list
        if not (isinstance(rows, QuerySet) and issubclass(rows._iterable_class, ModelIterable)):
            return self._get_page(rows[bottom:top], number, self)
        ids = list(rows.select_related(None).prefetch_related(None).values_list("pk", flat=True)[bottom:top])
        by_id = {row.pk: row for row in rows.filter(pk__in=ids)}
        return self._get_page([by_id[pk] for pk in ids if pk in by_id], number, self)


def typed_page_size(value: str | None) -> int | None:
    """Read a number of entries per page: a whole number from 5 to 1,000, else ``None`` (UIX-050; UIX-012)."""
    try:
        size = int((value or "").strip())
    except ValueError:
        return None
    return size if MIN_PAGE_SIZE <= size <= MAX_PAGE_SIZE else None


def list_key(request: HttpRequest, prefix: str = "") -> str:
    """The name under which the choice of a list is remembered: the name of its page, and the prefix of the table.

    ``projects:list``; ``availability:shortages:bottlenecks_`` for the second table of a page (UIX-040).
    """
    match = getattr(request, "resolver_match", None)
    name = getattr(match, "view_name", "") or request.path
    return f"{name}:{prefix}" if prefix else name


def _account(request: HttpRequest) -> Any:
    """The logged-in user of a request, or ``None`` (an API call without a session, a test without a user)."""
    user = getattr(request, "user", None)
    return user if user is not None and user.is_authenticated else None


def remembered_page_size(request: HttpRequest, key: str) -> int | None:
    """The number of entries per page this user chose last for a list, or ``None`` (UIX-050).

    Kept with the user's column choices (``TablePreference.page_size``): on every device and after logging in again.
    """
    user = _account(request)
    if user is None:
        return None
    from rentalars.core.models import TablePreference

    size = TablePreference.page_size_of(user, key)
    return typed_page_size(str(size)) if size is not None else None


def remember_page_size(request: HttpRequest, key: str, size: int) -> None:
    """Remember the number of entries per page a user chose for a list (UIX-050)."""
    user = _account(request)
    if user is not None:
        from rentalars.core.models import TablePreference

        TablePreference.save_page_size(user, key, size)


@dataclass(frozen=True)
class PageSizeChoice:
    """How many entries a list shows per page for a request – and a number the user typed that was refused."""

    size: int
    #: Why a number in the address was refused, or ``""``.
    error: str = ""
    #: The refused number, to show it again in the field.
    refused: str = ""


def page_size_choice(
    request: HttpRequest, *, key: str = "", prefix: str = "", default: int = DEFAULT_PAGE_SIZE
) -> PageSizeChoice:
    """Work out how many entries a list shows per page (UIX-050; UIX-012).

    The address decides (``?per_page=100``, a number from 5 to 1,000), then
    what the user chose last for this list, then the default of the list
    (50). A number out of bounds is refused with a message, and the list
    keeps its length: a list of a million rows on one page would be a simple
    way to bring the server to its knees. A number accepted from the
    address of a page (GET) is remembered for the list.
    """
    key = key or list_key(request, prefix)
    asked = request.GET.get(f"{prefix}{PAGE_SIZE_PARAMETER}", "").strip()
    remembered = remembered_page_size(request, key)
    fallback = remembered or default
    if not asked:
        return PageSizeChoice(fallback)
    size = typed_page_size(asked)
    if size is None:
        message = gettext(
            "“%(number)s” cannot be used: please enter a whole number from %(min)s to %(max)s entries per page. "
            "The list shows %(size)s entries per page."
        ) % {"number": asked[:12], "min": MIN_PAGE_SIZE, "max": group_thousands(str(MAX_PAGE_SIZE)), "size": fallback}
        return PageSizeChoice(fallback, error=message, refused=asked[:12])
    if request.method == "GET" and size != remembered:
        remember_page_size(request, key, size)
    return PageSizeChoice(size)


def page_size(request: HttpRequest) -> int:
    """Return how many entries the list of this request shows per page (UIX-012), see :func:`page_size_choice`."""
    return page_size_choice(request).size


def _address(request: HttpRequest, changes: dict[str, Any], drop: tuple[str, ...] = ()) -> str:
    """The query string of the request with some parameters replaced and some dropped – for links of a list."""
    parameters = request.GET.copy()
    for name, value in changes.items():
        parameters[name] = value
    for name in drop:
        parameters.pop(name, None)
    return f"?{parameters.urlencode()}"


def paginate(
    request: HttpRequest,
    queryset: QuerySet[Any] | list[Any],
    *,
    key: str = "",
    prefix: str = "",
    default: int = DEFAULT_PAGE_SIZE,
) -> Page[Any]:
    """Return the page named by ``?page=``; out-of-range values give the nearest page.

    The number of entries per page is the user's choice, see
    :func:`page_size_choice`; ``key`` names the list for remembering it (by
    default the name of the page), ``prefix`` the parameters of the second
    paginated table of a page (``runs_page``, ``runs_per_page``; UIX-040),
    ``default`` the length of a list nobody chose one for.

    UIX-050: every list that pages with this
    function and shows ``core/_pagination.html`` offers 25, 50, 100 and 200
    entries per page and a field for any number from 5 to 1,000 – nothing
    else is needed. The paginator of the returned page carries what the
    template needs (``size_links``, ``size_param``, ``kept_parameters``,
    ``size_error`` …), the page the links to its neighbours.
    """
    choice = page_size_choice(request, key=key, prefix=prefix, default=default)
    page_param = f"{prefix}page"
    size_param = f"{prefix}{PAGE_SIZE_PARAMETER}"
    paginator = LeanPaginator(queryset, choice.size)
    paginator.size_options = PAGE_SIZES  # type: ignore[attr-defined]
    paginator.size_links = [  # type: ignore[attr-defined]
        (size, _address(request, {size_param: size}, (page_param,)), size == choice.size) for size in PAGE_SIZES
    ]
    paginator.size_param = size_param  # type: ignore[attr-defined]
    paginator.size_min = MIN_PAGE_SIZE  # type: ignore[attr-defined]
    paginator.size_max = MAX_PAGE_SIZE  # type: ignore[attr-defined]
    paginator.size_error = choice.error  # type: ignore[attr-defined]
    paginator.typed_size = choice.refused or ("" if choice.size in PAGE_SIZES else str(choice.size))  # type: ignore[attr-defined]
    paginator.size_field_id = f"per-page-{prefix.strip('_')}" if prefix else "per-page"  # type: ignore[attr-defined]
    # Another length means other rows on "page 3": the choice starts the list at page 1 again.
    paginator.kept_parameters = [  # type: ignore[attr-defined]
        (name, value)
        for name in request.GET
        for value in request.GET.getlist(name)
        if name not in (page_param, size_param)
    ]
    # A list that fits on the smallest page offers no choice – unless the user chose an even shorter page.
    paginator.offers_sizes = bool(choice.error) or paginator.count > min(PAGE_SIZES[0], choice.size)  # type: ignore[attr-defined]
    page = paginator.get_page(request.GET.get(page_param))
    page.previous_url = _address(request, {page_param: page.previous_page_number()}) if page.has_previous() else ""  # type: ignore[attr-defined]
    page.next_url = _address(request, {page_param: page.next_page_number()}) if page.has_next() else ""  # type: ignore[attr-defined]
    return page


class PageSizeMiddleware:
    """Remove the old cookie in which one number of entries per page was remembered for every list (UIX-012).

    UIX-050: the choice is remembered per user and
    list (:func:`page_size_choice`); a cookie left over would only
    lie around.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        """Store the next handler of the chain."""
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Pass the request on and delete the old cookie if the browser still sends it."""
        response = self.get_response(request)
        if PAGE_SIZE_COOKIE in request.COOKIES and PAGE_SIZE_COOKIE not in response.cookies:
            response.delete_cookie(PAGE_SIZE_COOKIE, samesite="Lax")
        return response


def placeholder_url(name: str, *leading_ids: int) -> str:
    """Return an address whose last ID is the placeholder 0, for tables with many rows.

    Example: ``placeholder_url("projects:line_edit", 5)`` gives
    ``/projects/5/lines/0/``. The template filter ``fill`` replaces the
    placeholder by the ID of each row. One lookup then serves the whole
    table, instead of one lookup per row.
    """
    from rentalars.core.templatetags.rentalars import URL_PLACEHOLDER_ID

    return reverse(name, args=[*leading_ids, URL_PLACEHOLDER_ID])


def query_date(value: str | None) -> datetime.date | None:
    """A date from the address (``?since=2027-03-01``), or ``None`` if it is missing or no real day.

    ``parse_date`` raises on a well-formed but impossible day such as
    2027-02-30; a hand-edited link must not end in a server error.
    """
    try:
        return parse_date(value or "")
    except ValueError:
        return None


def query_datetime(value: str | None) -> datetime.datetime | None:
    """A moment from the address, or ``None`` if it is missing or impossible (see :func:`query_date`)."""
    try:
        return parse_datetime(value or "")
    except ValueError:
        return None


def start_of_day(day: datetime.date) -> datetime.datetime:
    """Return the first moment of a calendar day in the local time zone.

    Date filters compare against these moments instead of asking the database
    for "the date of a timestamp". The database could only answer that with
    time zone tables installed, which MariaDB does not have by default; the
    filter would then silently find nothing.
    """
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time.min))


def end_of_day(day: datetime.date) -> datetime.datetime:
    """Return the first moment of the following day; use with "less than"."""
    return start_of_day(day + datetime.timedelta(days=1))
