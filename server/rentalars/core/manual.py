# SPDX-License-Identifier: GPL-3.0-or-later
"""The user manual inside the application (UIX-029), one page per chapter (manual chapters; UIX-057).

"Handbuch" / "Manual" at the foot of the menu opens the user manual in the
language of the user: ``docs/handbuch/benutzerhandbuch.md`` in German,
``docs/en/user-manual.md`` in English. Both files are part of every
package. While the English manual is missing, the English pages show the
German one with a note.

``/manual/`` is the table of
contents (the introduction, a search field, every chapter with a short
description) and ``/manual/<n>/`` shows chapter ``n`` alone, with its
sections beside it, the list of all chapters and "previous" / "next".

* The file is split at its second-level headings (``## 4. Material``) –
  outside code blocks – into the introduction and the chapters. Chapter *n*
  is the *n*-th of them.
* Each chapter is rendered on its own with Python-Markdown, cleaned (nh3 –
  only formatting, tables, links and the anchors of the headings remain)
  and kept in memory per file and modification time. A request renders only
  the chapter it shows, and only the first time.
* The anchors of the headings are those GitHub makes ("#4-material",
  "#7-projekte-planen"). A link to an anchor in another chapter becomes a
  link to that chapter's page with the anchor (``/manual/7/#…``);
  :func:`anchor_chapters` says which chapter holds which anchor – the page
  ``/manual/`` uses it to forward an old address ``/manual/#7-projekte-planen``
  to ``/manual/7/#7-projekte-planen`` (the browser does not send the anchor
  to the server, so a small script does it).
* The operating guides (``docs/betrieb/`` and ``docs/en/operations/`` – installation, operation, update,
  backup, encryption, import) are part of the manual: ``/manual/guides/<key>/`` shows one in the language of the user,
  and a link to such a file – from the manual and from one guide to another – leads there (:data:`GUIDES`). The table of
  contents lists them. A link to the manual from a guide leads to ``/manual/``. Links to other files of the
  documentation are not served by the application and are shown as plain text.
* The search (``/manual/?q=…``) looks through all sections of the manual,
  every word of the query must occur, and shows where, with a few words
  around the place.
"""

from __future__ import annotations

import html as html_module
import re
import threading
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import nh3
from django.conf import settings

#: The manual per language, relative to the program folder.
MANUALS = {
    "de": Path("docs/handbuch/benutzerhandbuch.md"),
    "en": Path("docs/en/user-manual.md"),
}

#: The operating guides by key – the file name (without ``.md``) in German and in English.
GUIDES = {
    "installation": ("installation", "installation"),
    "operation": ("betrieb", "operation"),
    "update": ("aktualisierung", "updating"),
    "backup": ("sicherung", "backup"),
    "encryption": ("verschluesselung", "encryption"),
    "import": ("import", "import"),
}
#: The folder of the guides per language, relative to the program folder.
GUIDE_DIRS = {"de": Path("docs/betrieb"), "en": Path("docs/en/operations")}
_GUIDE_BY_NAME = {name: key for key, names in GUIDES.items() for name in names}
_MANUAL_FILES = ("benutzerhandbuch", "user-manual")

TAGS = {
    "h1", "h2", "h3", "h4", "h5", "h6", "p", "br", "hr", "strong", "em", "b", "i", "code", "pre", "blockquote",
    "ul", "ol", "li", "table", "thead", "tbody", "tr", "th", "td", "a", "span", "div", "dl", "dt", "dd", "sup", "sub",
    "kbd",
}  # fmt: skip
ATTRIBUTES = {
    "a": {"href", "title"},
    "h1": {"id"},
    "h2": {"id"},
    "h3": {"id"},
    "h4": {"id"},
    "h5": {"id"},
    "h6": {"id"},
    "th": {"align"},
    "td": {"align"},
    "div": {"class"},
    "span": {"class"},
}
_LINK = re.compile(r'<a href="(?P<href>[^"]*)"(?P<rest>[^>]*)>(?P<text>.*?)</a>', re.DOTALL)
_HEADING = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<text>.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s{0,3}(```|~~~)")
#: How long a description of a chapter on the table of contents may be, in characters.
DESCRIPTION_LENGTH = 220
#: How many section names of a chapter the table of contents lists under its description.
SECTIONS_SHOWN = 6
#: A first paragraph shorter than this says too little to serve as description (it is left out).
MIN_DESCRIPTION = 40
#: The search: longest query taken, most places shown, words around a place.
MAX_QUERY = 100
MAX_RESULTS = 30
SNIPPET_RADIUS = 80


def github_slug(value: str, separator: str = "-") -> str:
    """The anchor GitHub gives a heading: lower case, punctuation dropped, spaces as hyphens, umlauts kept."""
    value = unicodedata.normalize("NFC", re.sub(r"<[^>]+>", "", value)).strip().lower()
    value = "".join(char for char in value if char.isalnum() or char in " -_")
    return value.replace(" ", separator)


def _plain(markdown_text: str) -> str:
    """Markdown of a line or a paragraph as plain text: links by their text, no emphasis, no code marks."""
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", markdown_text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[`*]|(?<!\w)_|_(?!\w)", "", text)
    return html_module.unescape(" ".join(text.split()))


def _short(text: str, length: int = DESCRIPTION_LENGTH) -> str:
    """A text cut after a whole word (before ``length`` characters), with an ellipsis when something is left."""
    if len(text) <= length:
        return text
    cut = text[:length].rsplit(" ", 1)[0].rstrip(" ,;:–-")
    sentence = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if sentence > length // 2:
        return cut[: sentence + 1]
    return cut + "…"


@dataclass
class Chapter:
    """One chapter: its text as Markdown, and, once asked for, the same as cleaned HTML."""

    number: int
    title: str
    #: The id of the chapter's heading ("4-material").
    anchor: str
    markdown: str
    #: The first paragraph, as plain text, for the table of contents.
    description: str = ""
    #: The ids and texts of the second- and third-level headings, for the table beside the chapter.
    sections: list[dict[str, str]] = field(default_factory=list)
    #: The manual the chapter belongs to (its lock and its anchors); set when the manual is loaded.
    manual: Manual | None = field(default=None, repr=False, compare=False)
    _html: str | None = field(default=None, repr=False)
    _toc: list[dict[str, Any]] = field(default_factory=list, repr=False)

    @property
    def html(self) -> str:
        """The chapter as cleaned HTML – rendered the first time it is asked for, then kept."""
        self._render()
        return self._html or ""

    @property
    def toc(self) -> list[dict[str, Any]]:
        """The headings of the chapter as the Markdown converter found them, nested."""
        self._render()
        return self._toc

    @property
    def section_names(self) -> list[str]:
        """The names of the first sections (third-level headings) – a glimpse of what the chapter holds."""
        return [section["name"] for section in self.sections if section["level"] == "3"][:SECTIONS_SHOWN]

    def _render(self) -> None:
        """Render the chapter once; several requests at the same time wait for the first one."""
        if self._html is not None or self.manual is None:
            return
        with self.manual._lock:
            if self._html is None:
                self._html, self._toc = _to_html(self.markdown, self.manual.anchors(), current=self.number)


@dataclass
class Manual:
    """The manual of one language as a table of contents and chapters; cached per file and modification time."""

    language: str
    #: The title ("Benutzerhandbuch") and the introduction as plain Markdown, without the list of contents.
    title: str
    introduction: str
    chapters: list[Chapter]
    #: The language asked for has no manual yet; this is the German one.
    fallback: bool = False
    _intro_html: str | None = None
    _anchors: dict[str, int] | None = None
    _search_index: list[dict[str, Any]] | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def chapter(self, number: int) -> Chapter | None:
        """Chapter ``number`` (counted from 1), or ``None``."""
        return self.chapters[number - 1] if 1 <= number <= len(self.chapters) else None

    @property
    def introduction_html(self) -> str:
        """The introduction as cleaned HTML."""
        if self._intro_html is None:
            with self._lock:
                if self._intro_html is None:
                    self._intro_html = _to_html(self.introduction, self.anchors(), current=0)[0]
        return self._intro_html

    def anchors(self) -> dict[str, int]:
        """Which chapter holds which anchor: the ids of all headings, found without rendering anything.

        ``0`` is the introduction ("#benutzerhandbuch"). The first place wins when two headings have the same text.
        """
        if self._anchors is None:
            found: dict[str, int] = {}
            for slug in _heading_slugs(self.introduction):
                found.setdefault(slug, 0)
            for chapter in self.chapters:
                for slug in _heading_slugs(chapter.markdown):
                    found.setdefault(slug, chapter.number)
            self._anchors = found
        return self._anchors

    def search(self, query: str) -> list[dict[str, Any]]:
        """The sections of the manual that contain every word of ``query`` – most hits first.

        Each result has the chapter, the heading with its anchor and a snippet of the text around the first word
        found, as parts that are marked or not (``[(text, is_match), …]``) so that a template can highlight them
        without building HTML by hand.
        """
        words = [word for word in _plain(query[:MAX_QUERY]).casefold().split() if word]
        if not words:
            return []
        index = self._search_index
        if index is None:
            index = self._search_index = _build_search_index(self)
        results = []
        for section in index:
            haystack = section["text"]
            if not all(word in haystack for word in words):
                continue
            heading = section["heading"].casefold()
            score = sum(haystack.count(word) + 8 * heading.count(word) for word in words)
            results.append((score, section))
        results.sort(key=lambda item: (-item[0], item[1]["chapter"].number))
        return [
            {
                "chapter": section["chapter"],
                "heading": section["heading"],
                "anchor": section["anchor"],
                "snippet": _snippet(section["body"], words),
            }
            for _score, section in results[:MAX_RESULTS]
        ]


def _heading_slugs(markdown_text: str) -> list[str]:
    """The anchors of all headings of a Markdown text, outside code blocks."""
    return [github_slug(_plain(text)) for _level, text, _line in _headings(markdown_text)]


def _headings(markdown_text: str) -> list[tuple[int, str, int]]:
    """(level, text, line number) of every heading outside fenced code blocks."""
    found = []
    fence = ""
    for number, line in enumerate(markdown_text.split("\n")):
        marker = _FENCE.match(line)
        if marker:
            fence = "" if fence == marker.group(1) else (fence or marker.group(1))
            continue
        if fence:
            continue
        heading = _HEADING.match(line)
        if heading:
            found.append((len(heading.group("hashes")), heading.group("text"), number))
    return found


def _split(markdown_text: str) -> tuple[str, list[tuple[str, str]]]:
    """The text before the first ``##`` heading, and the chapters as (heading, text) – fenced code is left alone."""
    lines = markdown_text.split("\n")
    starts = [number for level, _text, number in _headings(markdown_text) if level == 2]
    if not starts:
        return markdown_text, []
    chapters = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(lines)
        chapters.append((_HEADING.match(lines[start]).group("text"), "\n".join(lines[start:end]).rstrip() + "\n"))  # type: ignore[union-attr]
    return "\n".join(lines[: starts[0]]), chapters


def _introduction(preamble: str) -> tuple[str, str]:
    """Title and introduction of the text before the first chapter: the list of contents and the rule are dropped.

    The contents of the manual's own are a bold line ("**Inhalt**") with a numbered list; the table of contents
    of the page takes its place.
    """
    title = ""
    kept: list[str] = []
    for line in preamble.split("\n"):
        heading = _HEADING.match(line)
        if heading and len(heading.group("hashes")) == 1 and not title:
            title = _plain(heading.group("text"))
            continue
        if re.match(r"^\*\*[^*]+\*\*\s*$", line):
            break  # "**Inhalt**": the list of contents of the file starts here
        kept.append(line)
    return title, "\n".join(kept).strip() + "\n"


def _describe(markdown_text: str) -> str:
    """The first paragraph of a chapter (after its heading) as short plain text; "" when it starts with a list."""
    lines = markdown_text.split("\n")[1:]
    paragraph: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if paragraph:
                break
            continue
        if stripped.startswith(("#", "|", ">", "```", "~~~", "<", "---")) or re.match(r"^([-*+]|\d+[.)])\s", stripped):
            if paragraph:
                break
            if stripped.startswith(("#", "|", "```", "~~~")):
                return ""  # the chapter begins with a table, a code block or a heading: nothing to say in short
            continue
        paragraph.append(stripped)
    text = _plain(" ".join(paragraph))
    return _short(text) if len(text) >= MIN_DESCRIPTION else ""


def _sections(markdown_text: str) -> list[dict[str, str]]:
    """The second- and third-level headings of a chapter as (id, name), in order."""
    return [
        {"id": github_slug(_plain(text)), "name": _plain(text), "level": str(level)}
        for level, text, _line in _headings(markdown_text)
        if level in (2, 3)
    ]


def _plain_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """An entry of the contents with its name as plain text – the template escapes it once."""
    return {
        "id": entry["id"],
        "name": html_module.unescape(entry["name"]),
        "children": [_plain_entry(child) for child in entry.get("children", [])],
    }


def _to_html(markdown_text: str, anchors: dict[str, int], *, current: int) -> tuple[str, list[dict[str, Any]]]:
    """Markdown as cleaned HTML and the nested headings; links to anchors of other chapters point to their page."""
    import markdown

    converter = markdown.Markdown(
        extensions=["toc", "tables", "fenced_code", "sane_lists"],
        extension_configs={"toc": {"slugify": github_slug, "toc_depth": "2-3"}},
        output_format="html",
    )
    raw = converter.convert(markdown_text)
    html = nh3.clean(
        _local_links(raw, anchors, current),
        tags=TAGS,
        attributes=ATTRIBUTES,
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer",
        strip_comments=True,
    )
    # Wide tables and code scroll on their own; a keyboard reaches them too (WCAG 2.1.1, axe "scrollable-region").
    html = html.replace("<table>", '<table tabindex="0">').replace("<pre>", '<pre tabindex="0">')
    toc = [_plain_entry(entry) for entry in getattr(converter, "toc_tokens", [])]
    return html, toc


def chapter_url(number: int, anchor: str = "") -> str:
    """The address of chapter ``number`` ("/manual/7/#anchor"); chapter 0 is the table of contents."""
    from django.urls import reverse

    base = reverse("core:manual_chapter", args=[number]) if number else reverse("core:manual")
    return f"{base}#{anchor}" if anchor else base


def _local_links(html: str, anchors: dict[str, int], current: int) -> str:
    """Links within the manual and to web addresses stay; links to other files become their text.

    A link to an anchor in another chapter points to that chapter's page.
    """

    def replace(match: re.Match[str]) -> str:
        href = match.group("href")
        if href.startswith(("http://", "https://", "mailto:")):
            return match.group(0)
        guide = _guide_link(html_module.unescape(href))
        if guide is not None:
            return f'<a href="{html_module.escape(guide)}"{match.group("rest")}>{match.group("text")}</a>'
        if href.startswith("#"):
            chapter = anchors.get(html_module.unescape(href[1:]))
            if chapter is None or chapter == current:
                return match.group(0)
            return f'<a href="{html_module.escape(chapter_url(chapter, href[1:]))}"{match.group("rest")}>{match.group("text")}</a>'
        return f'<span class="manual-file">{match.group("text")}</span>'

    return _LINK.sub(replace, html)


def _guide_link(href: str) -> str | None:
    """The address inside the application for a link to an operating guide or to the manual, else ``None``.

    ``../betrieb/import.md``, ``sicherung.md#anchor``, ``docs/en/operations/backup.md`` lead to the guide page;
    ``../handbuch/benutzerhandbuch.md`` (and the English file) to the manual.
    """
    from django.urls import reverse

    path, _hash, anchor = href.partition("#")
    if not path.endswith(".md"):
        return None
    name = Path(path).stem
    if name in _MANUAL_FILES:
        return reverse("core:manual") + (f"#{anchor}" if anchor else "")
    key = _GUIDE_BY_NAME.get(name)
    if key is None or "THIRD-PARTY" in path:
        return None
    return reverse("core:manual_guide", args=[key]) + (f"#{anchor}" if anchor else "")


@dataclass
class Guide:
    """One operating guide in a language: its title and its text; rendered once, on first use."""

    key: str
    title: str
    markdown: str
    language: str
    fallback: bool = False
    _html: str | None = field(default=None, repr=False)

    @property
    def html(self) -> str:
        """The guide as cleaned HTML; links to other guides and to the manual point to their pages."""
        if self._html is None:
            self._html = _to_html(self.markdown, {}, current=0)[0]
        return self._html


_guide_cache: dict[tuple[Path, str], tuple[int, Guide]] = {}


def guide_for(key: str, language: str) -> Guide | None:
    """The operating guide ``key`` in a language – the German one while that language has none; ``None`` if unknown."""
    names = GUIDES.get(key)
    if names is None:
        return None
    base = Path(settings.BASE_DIR)
    code = language if language in GUIDE_DIRS else "de"
    path = base / GUIDE_DIRS[code] / f"{names[0 if code == 'de' else 1]}.md"
    fallback = False
    if not path.is_file():
        code, fallback = "de", code != "de"
        path = base / GUIDE_DIRS["de"] / f"{names[0]}.md"
        if not path.is_file():
            return None
    modified = path.stat().st_mtime_ns
    with _cache_lock:
        cached = _guide_cache.get((path, language))
        if cached is not None and cached[0] == modified:
            return cached[1]
    text = path.read_text(encoding="utf-8")
    title = next((_plain(heading) for level, heading, _line in _headings(text) if level == 1), key)
    guide = Guide(key=key, title=title, markdown=text, language=code, fallback=fallback)
    with _cache_lock:
        _guide_cache[(path, language)] = (modified, guide)
    return guide


def guides_for(language: str) -> list[Guide]:
    """All operating guides that exist, in the order of :data:`GUIDES`."""
    found = (guide_for(key, language) for key in GUIDES)
    return [guide for guide in found if guide is not None]


def _build_search_index(manual: Manual) -> list[dict[str, Any]]:
    """Every section of the manual (heading level 2 to 4) with its text, lower case, for the search."""
    index = []
    for chapter in manual.chapters:
        lines = chapter.markdown.split("\n")
        headings = [(level, text, number) for level, text, number in _headings(chapter.markdown) if level <= 4]
        for position, (_level, text, start) in enumerate(headings):
            end = headings[position + 1][2] if position + 1 < len(headings) else len(lines)
            body = _plain(" ".join(lines[start + 1 : end]))
            heading = _plain(text)
            index.append(
                {
                    "chapter": chapter,
                    "heading": heading,
                    "anchor": github_slug(heading),
                    "body": body,
                    "text": f"{heading} {body}".casefold(),
                }
            )
    return index


def _snippet(body: str, words: list[str]) -> list[tuple[str, bool]]:
    """A few words of ``body`` around the first of ``words`` that occurs, as (text, is_match) parts."""
    lower = body.casefold()
    hits = [lower.find(word) for word in words if lower.find(word) >= 0]
    start = max(min(hits) - SNIPPET_RADIUS, 0) if hits else 0
    end = min(start + 2 * SNIPPET_RADIUS, len(body))
    if start:
        start = body.find(" ", start) + 1 or start  # begin at a word
    piece = body[start:end]
    prefix, suffix = ("… " if start else ""), (" …" if end < len(body) else "")
    pattern = re.compile("|".join(re.escape(word) for word in sorted(words, key=len, reverse=True)), re.IGNORECASE)
    parts: list[tuple[str, bool]] = []
    last = 0
    for match in pattern.finditer(piece):
        if match.start() > last:
            parts.append((piece[last : match.start()], False))
        parts.append((match.group(0), True))
        last = match.end()
    if last < len(piece):
        parts.append((piece[last:], False))
    if parts and prefix:
        parts[0] = (prefix + parts[0][0], parts[0][1])
    if parts and suffix:
        parts[-1] = (parts[-1][0] + suffix, parts[-1][1])
    return parts


#: Per file *and* language: the German file also serves a language that has none of its own (marked as fallback).
_cache: dict[tuple[Path, str, bool], tuple[int, Manual]] = {}
_cache_lock = threading.Lock()


def _load(path: Path, language: str, fallback: bool) -> Manual:
    """Read and split a manual file; nothing is rendered yet."""
    preamble, parts = _split(path.read_text(encoding="utf-8"))
    title, introduction = _introduction(preamble)
    chapters = []
    for number, (heading, text) in enumerate(parts, start=1):
        plain = _plain(heading)
        chapters.append(
            Chapter(
                number=number,
                title=plain,
                anchor=github_slug(plain),
                markdown=text,
                description=_describe(text),
                sections=_sections(text),
            )
        )
    manual = Manual(
        language="de" if fallback else language,
        title=title,
        introduction=introduction,
        chapters=chapters,
        fallback=fallback,
    )
    for chapter in chapters:
        chapter.manual = manual
    return manual


def manual_for(language: str) -> Manual:
    """The manual in a language; the German one, marked, while that language has none.

    Raises:
        FileNotFoundError: Not even the German manual is there.
    """
    base = Path(settings.BASE_DIR)
    path = base / MANUALS.get(language, MANUALS["de"])
    fallback = False
    if not path.is_file():
        path, fallback = base / MANUALS["de"], language != "de"
    modified = path.stat().st_mtime_ns
    with _cache_lock:
        cached = _cache.get((path, language, fallback))
        if cached is not None and cached[0] == modified:
            return cached[1]
    manual = _load(path, language, fallback)
    with _cache_lock:
        _cache[(path, language, fallback)] = (modified, manual)
    return manual


def _current_manual() -> Manual:
    """The manual in the language of the user; 404 when no manual file exists at all."""
    from django.http import Http404
    from django.utils.translation import get_language

    from rentalars.core.i18n import supported

    try:
        return manual_for(supported(get_language()) or "de")
    except FileNotFoundError as error:
        raise Http404 from error


def manual_view(request: Any) -> Any:
    """``/manual/`` – the table of contents of the user manual in the language of the user (UIX-029).

    ``?q=`` searches the manual. A script on the page forwards an old address with an anchor
    (``/manual/#7-projekte-planen``) to the page of its chapter.
    """
    from django.shortcuts import render

    manual = _current_manual()
    query = (request.GET.get("q") or "").strip()[:MAX_QUERY]
    return render(
        request,
        "core/manual.html",
        {
            "manual": manual,
            "query": query,
            "results": manual.search(query) if query else None,
            "guides": guides_for(manual.language if not manual.fallback else "de"),
        },
    )


def manual_chapter_view(request: Any, number: int) -> Any:
    """``/manual/<n>/`` – chapter ``n`` with its sections, the list of chapters and the way to the next."""
    from django.http import Http404
    from django.shortcuts import render

    manual = _current_manual()
    chapter = manual.chapter(number)
    if chapter is None:
        raise Http404("No such chapter.")
    return render(
        request,
        "core/manual_chapter.html",
        {
            "manual": manual,
            "chapter": chapter,
            "previous": manual.chapter(number - 1),
            "next": manual.chapter(number + 1),
        },
    )


def manual_guide_view(request: Any, key: str) -> Any:
    """``/manual/guides/<key>/`` – an operating guide inside the manual, in the language of the user."""
    from django.http import Http404
    from django.shortcuts import render
    from django.utils.translation import get_language

    from rentalars.core.i18n import supported

    language = supported(get_language()) or "de"
    guide = guide_for(key, language)
    if guide is None:
        raise Http404("No such guide.")
    return render(
        request,
        "core/manual_guide.html",
        {"guide": guide, "guides": guides_for(language), "language": language},
    )


def manual_anchors_view(request: Any) -> Any:
    """``/manual/anchors/`` – which chapter holds which anchor, as JSON, for forwarding old addresses.

    The answer is the same for everybody of a language and changes only with an update, so a browser may keep it for
    an hour.
    """
    from django.http import JsonResponse
    from django.utils.cache import patch_cache_control, patch_vary_headers

    manual = _current_manual()
    response = JsonResponse(
        {"chapters": {slug: number for slug, number in manual.anchors().items() if number}, "language": manual.language}
    )
    patch_cache_control(response, private=True, max_age=3600)
    patch_vary_headers(response, ["Cookie"])
    return response
