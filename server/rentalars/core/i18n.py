# SPDX-License-Identifier: GPL-3.0-or-later
"""German and English (UIX-029).

Rentalars speaks German and English. The English texts are the message IDs of
the translation files; German comes from ``locale/de``.

Which language holds where
--------------------------
* **The interface** follows the user: ``User.language`` ("Deutsch" or
  "English"); empty means the language of the installation (``language`` in
  the configuration file). The login page and every other page without a
  logged-in user follow the browser (``Accept-Language``: German or English,
  anything else the installation's language). :class:`LanguageMiddleware`
  switches the language for each request – pages, htmx partials, messages,
  PDFs a user downloads for himself and the errors of the API. A request
  with an API token gets the token owner's language once the token is known
  (``accounts.authentication``).
* **Mails and notifications to a user** are written in that user's
  language: :func:`for_user`; background tasks run in the language of the
  user who started them.
* **Documents to customers** – offers, order confirmations, delivery notes,
  invoices, cancellations, packing lists – and the mails Rentalars writes to
  customers by itself follow one setting of the company,
  ``CompanyProfile.document_language``: :func:`for_documents`. Texts the
  company typed (templates, text blocks, product names) stay as typed.

Formats
-------
German stays as it was: ``16.10.2026``, ``14:30``, ``1.234,50 €``. English
is British: ``16/10/2026``, 24-hour time, ``€1,234.50``. Templates and code
write dates with the German patterns they always had (``|date:"d.m.Y"``,
``strftime("%d.%m.%Y")``); :func:`local_pattern` turns such a pattern into
its English form while English is active. The template filters ``date`` and
``time`` do that for every template (``core.templatetags.local_dates``, a
built-in library), code calls :func:`local_pattern` around the pattern.
Numbers: ``core.money``. Django's own formats (form fields, ``SHORT_DATE_FORMAT``)
come from ``rentalars/core/formats/en``.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.utils import translation
from django.utils.cache import patch_vary_headers
from django.utils.translation import pgettext_lazy

#: The languages of the interface and of documents, each named in its own language.
LANGUAGE_CHOICES = (("de", "Deutsch"), ("en", "English"))
SUPPORTED = frozenset(code for code, _name in LANGUAGE_CHOICES)
#: The language tag of English pages: British English (dates as 16/10/2026).
HTML_LANG = {"de": "de", "en": "en-GB"}


def supported(code: str | None) -> str:
    """The supported language a code stands for ("en-GB" → "en"); "" for none."""
    base = (code or "").strip().lower().replace("_", "-").split("-", 1)[0]
    return base if base in SUPPORTED else ""


def installation_language() -> str:
    """The language of the installation: ``language`` of the configuration file, German if it names another."""
    return supported(settings.LANGUAGE_CODE) or "de"


def user_language(user: Any) -> str:
    """The interface language of a user; the installation's when the user chose none (or for nobody)."""
    return supported(getattr(user, "language", "")) or installation_language()


def browser_language(request: HttpRequest) -> str:
    """The first language of ``Accept-Language`` Rentalars speaks; else the installation's."""
    header = request.META.get("HTTP_ACCEPT_LANGUAGE", "")
    ranked: list[tuple[float, int, str]] = []
    for position, part in enumerate(header.split(",")):
        tag, _separator, parameters = part.strip().partition(";")
        quality = 1.0
        match = re.search(r"q\s*=\s*([0-9.]+)", parameters)
        if match:
            try:
                quality = float(match.group(1))
            except ValueError:
                quality = 0.0
        code = supported(tag)
        if code and quality > 0:
            ranked.append((-quality, position, code))
    return min(ranked)[2] if ranked else installation_language()


def api_language(user: Any, request: HttpRequest) -> str:
    """The language of an API call: the one the user chose, else the one the client asks for (``Accept-Language``)."""
    return supported(getattr(user, "language", "")) or browser_language(request)


def request_language(request: HttpRequest) -> str:
    """The language of a request: the logged-in user's, else the browser's.

    A user who chose no language gets the installation's in the browser; a
    program calling the API gets the one it asks for in ``Accept-Language``.
    """
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        if request.path.startswith("/api/"):
            return api_language(user, request)
        return user_language(user)
    return browser_language(request)


def document_language() -> str:
    """The language of documents to customers – one setting for the whole company."""
    from rentalars.core.models import CompanyProfile

    return supported(CompanyProfile.load().document_language) or installation_language()


@contextmanager
def for_user(user: Any) -> Iterator[str]:
    """Write something for one user – a mail, a notification – in that user's language."""
    language = user_language(user)
    with translation.override(language):
        yield language


@contextmanager
def for_documents() -> Iterator[str]:
    """Write a document or a mail to a customer in the language of the company's documents."""
    language = document_language()
    with translation.override(language):
        yield language


def is_english() -> bool:
    """Whether English is the active language."""
    return supported(translation.get_language()) == "en"


def html_lang() -> str:
    """The ``lang`` attribute for the active language ("de", "en-GB")."""
    return HTML_LANG.get(supported(translation.get_language()) or installation_language(), "de")


# --- Dates ---------------------------------------------------------------------------------------------------------

#: German date patterns and their British form – Django's (``d.m.Y``) and ``strftime``'s (``%d.%m.%Y``).
_ENGLISH_PATTERNS = (
    (re.compile(r"(?<![\\%])j\. F"), "j F"),
    (re.compile(r"(?<![\\%])([dj])\.([mn])\.([Yy])"), r"\1/\2/\3"),
    (re.compile(r"(?<![\\%])([dj])\.([mn])\."), r"\1/\2"),
    (re.compile(r"^j\.$"), "j"),
    (re.compile(r"%d\.%m\.%([Yy])"), r"%d/%m/%\1"),
    (re.compile(r"%d\.%m\."), "%d/%m"),
)


def local_pattern(pattern: str) -> str:
    """A German date pattern in the form of the active language.

    German keeps it as it is. English writes the day before the month with
    slashes (British): ``d.m.Y`` → ``d/m/Y``, ``D d.m. H:i`` → ``D d/m H:i``,
    ``%d.%m.%Y %H:%M`` → ``%d/%m/%Y %H:%M``. Any other pattern (``Y-m-d``,
    ``H:i``, ``F Y``) is the same in both.
    """
    if not pattern or not is_english():
        return pattern
    for search, replacement in _ENGLISH_PATTERNS:
        pattern = search.sub(replacement, pattern)
    return pattern


def format_date(value: Any, pattern: str = "d.m.Y") -> str:
    """A date or time written with a (German) Django pattern in the active language; "" for nothing."""
    if value is None or value == "":
        return ""
    from django.utils import dateformat

    return dateformat.format(value, local_pattern(pattern))


# --- Names of files to download --------------------------------------------------------------------------------

#: The names of files Rentalars offers for download, without umlauts (``Packliste-2026-0042.pdf``).
FILE_NAMES = {
    "hours": pgettext_lazy("file name", "Hours"),
    "timesheet": pgettext_lazy("file name", "Timesheet"),
    "expenses": pgettext_lazy("file name", "Expenses"),
    "price_overview": pgettext_lazy("file name", "Price-overview"),
    "labels": pgettext_lazy("file name", "Labels"),
    "packing_list": pgettext_lazy("file name", "Packing-list"),
    "deployments": pgettext_lazy("file name", "rentalars-deployments"),
    "draft": pgettext_lazy("file name", "Draft"),
    "deployment_view": pgettext_lazy("file name", "Deployment-overview"),
    "whole": pgettext_lazy("file name", "complete"),
    "list": pgettext_lazy("file name", "list"),
}


def file_name(key: str, *parts: Any, extension: str) -> str:
    """The name of a download in the active language: ``file_name("packing_list", "2026-0042", extension="pdf")``."""
    words = [str(FILE_NAMES[key]), *(str(part) for part in parts if part)]
    return "-".join(words) + "." + extension


# --- Texts written later for each reader -------------------------------------------------------------------------


class LocalText:
    """A text with values, put together in the language of whoever reads it (UIX-029).

    A notification goes to several users, each in his own language: the
    caller passes ``LocalText(gettext_lazy("Ready: %(task)s"), task=title)``
    and ``notifications.services.notify`` writes it for each user. Values may
    be lazy texts or ``LocalText`` themselves; they are written in the same
    language. ``str()`` gives the text in the active language.
    """

    def __init__(self, message: Any, /, **values: Any) -> None:  # a value may be called "message" too
        self.message = message
        self.values = values

    def __str__(self) -> str:
        if not self.values:
            return str(self.message)
        # ``message % values`` and not ``str(message) % values``: a plural text (``ngettext_lazy(..., "count")``)
        # takes the number from the values (B2).
        return str(
            self.message
            % {name: value if isinstance(value, int | float) else str(value) for name, value in self.values.items()}
        )

    def __add__(self, other: Any) -> LocalText:
        return _Joined((self, other))

    def __radd__(self, other: Any) -> LocalText:
        return _Joined((other, self))


class _Joined(LocalText):
    """Several texts after one another, each written in the reader's language."""

    def __init__(self, parts: tuple[Any, ...]) -> None:
        super().__init__("")
        self.parts = parts

    def __str__(self) -> str:
        return "".join(str(part) for part in self.parts)


class LazyCall:
    """A value of a :class:`LocalText` that is worked out in the reader's language, e.g. a period with weekdays."""

    def __init__(self, function: Any, *args: Any, **kwargs: Any) -> None:
        self.function = function
        self.args = args
        self.kwargs = kwargs

    def __str__(self) -> str:
        return str(self.function(*self.args, **self.kwargs))


def written_for(text: Any, user: Any) -> str:
    """A text (plain, lazy or :class:`LocalText`) as the user reads it."""
    if isinstance(text, str):
        return text
    with for_user(user):
        return str(text)


# --- The language of each request --------------------------------------------------------------------------------


class LanguageMiddleware:
    """Switch to the language of the request: the user's, on pages without login the browser's (UIX-029).

    Placed after the authentication, so that the user is known. Everything
    the request renders – the page, an htmx partial, a message, a PDF, an
    error of the API – is in that language. Pages for visitors without login
    differ by ``Accept-Language``, which the answer says in ``Vary``.
    """

    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Answer the request in its language."""
        language = request_language(request)
        request.LANGUAGE_CODE = language  # type: ignore[attr-defined]
        with translation.override(language):
            response = self.get_response(request)
            if not response.has_header("Content-Language"):
                response["Content-Language"] = language
        patch_vary_headers(response, ("Accept-Language",))
        return response


def plural_of(value: Any) -> int:
    """The number that decides singular or plural for ``ngettext`` (B2).

    Whole numbers decide themselves – 1 is singular –; a number with decimals (2.5 pieces) is plural, and a
    value that is not a number at all is read as plural.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 2
    return int(number) if number == int(number) else 2
