# SPDX-License-Identifier: GPL-3.0-or-later
"""The page "About Rentalars" with the Appropriate Legal Notices (UIX-062).

Section 5 d of the GPL asks an interactive program to show its legal notices: that there is no warranty, that it is
free software, under which licence, and how to see the licence. A link next to the author attribution (under the version
in the menu, in the foot of the login page) leads here. The page works without login, like the login page itself.

* ``/about/`` – the notices, the author attribution, the additional term, and the links below;
* ``/about/<name>/`` – a full text as a page of its own (in the layout of the program, readable on a phone);
* ``/about/<name>.txt`` – the full texts as plain text: the licence (``LICENSE``), the additional terms
  (``ADDITIONAL-TERMS.md``) and the libraries of others (``THIRD-PARTY.md``); they are part of every package.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _lazy

from rentalars import COPYRIGHT_HOLDER, COPYRIGHT_YEAR, PLACEHOLDER_HOLDER

#: The texts that can be read: the name in the address -> the file in the program folder.
TEXTS = {
    "license": "LICENSE",
    "additional-terms": "ADDITIONAL-TERMS.md",
    "third-party": "THIRD-PARTY.md",
}


#: The titles of the pages of the full texts.
ABOUT_TITLES = (
    ("license", _lazy("GNU General Public License, version 3")),
    ("additional-terms", _lazy("Additional terms")),
    ("third-party", _lazy("Libraries and programs of others")),
)


def _read(name: str) -> str | None:
    path = Path(settings.BASE_DIR) / TEXTS[name]
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _holder() -> str:
    """The holder of the rights; the placeholder is a sentence of the house and is translated, a name is left as it is."""
    if COPYRIGHT_HOLDER == PLACEHOLDER_HOLDER:
        return str(_("the authors of Rentalars"))
    return COPYRIGHT_HOLDER


def about_view(request: HttpRequest) -> HttpResponse:
    """``/about/`` – the notices of the licence, for anybody."""
    shown: dict[str, Any] = {
        "base_template": "base.html" if request.user.is_authenticated else "base_public.html",
        "public": not request.user.is_authenticated,
        "copyright": f"© {COPYRIGHT_YEAR} {_holder()}",
        "texts": [(key, key.replace("-", " ")) for key in TEXTS if _read(key) is not None],
        "title": _("About Rentalars"),
    }
    # No "Back": the page is an entry of the navigation (the link below the version), and those pages have none.
    return render(request, "core/about.html", shown)


def about_text_view(request: HttpRequest, name: str) -> HttpResponse:
    """``/about/<name>.txt`` – one of the full texts as plain text."""
    if name not in TEXTS:
        raise Http404
    text = _read(name)
    if text is None:
        raise Http404
    return HttpResponse(text, content_type="text/plain; charset=utf-8")


def about_text_page(request: HttpRequest, name: str) -> HttpResponse:
    """``/about/<name>/`` – one of the full texts in the layout of the program (V21).

    The licence is shown as it is, in lines that wrap; the two Markdown files are set as pages (headings, lists,
    tables). The plain text stays at ``/about/<name>.txt``.
    """
    if name not in TEXTS:
        raise Http404
    text = _read(name)
    if text is None:
        raise Http404
    shown: dict[str, Any] = {
        "base_template": "base.html" if request.user.is_authenticated else "base_public.html",
        "public": not request.user.is_authenticated,
        "name": name,
        "title": dict(ABOUT_TITLES)[name],
        "plain": text if name == "license" else "",
    }
    if name != "license":
        from rentalars.core.manual import _to_html

        shown["html"], _toc = _to_html(text, {}, current=0)
    if request.user.is_authenticated:
        request.back_url = reverse("core:about")  # type: ignore[attr-defined]
    return render(request, "core/about_text.html", shown)
