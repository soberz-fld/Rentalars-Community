# SPDX-License-Identifier: GPL-3.0-or-later
"""Showing the HTML of a mail safely (EML-027).

A mail is written by somebody outside. Its HTML is therefore

1. **cleaned** with ``nh3`` (the HTML sanitiser "ammonia"): scripts, event
   handlers, forms, frames, styles that load anything are removed; only
   formatting stays;
2. stripped of **external pictures** until the reader asks for them: a
   picture from a foreign server tells its sender when and where the mail
   was read. They are counted, and the page offers to load them;
3. shown in a **sandboxed frame** with a policy of its own
   (``CONTENT_SECURITY_POLICY``): even if something slipped through the
   cleaning, the browser runs no script and – unless allowed – loads
   nothing from outside.

Pictures inside the mail (``cid:``) are its attachments and are shown from
Rentalars itself.

For the conversation of a project (EML-036) and the text part of sent mails
(EML-034) there are plain-text helpers at the end: :func:`html_to_text`,
:func:`split_quoted` and :func:`frame_size`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from html.parser import HTMLParser

import nh3

TAGS = {
    "a", "abbr", "b", "blockquote", "br", "caption", "center", "cite", "code", "col", "colgroup", "dd", "del",
    "div", "dl", "dt", "em", "font", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "ins", "kbd", "li",
    "ol", "p", "pre", "q", "s", "small", "span", "strike", "strong", "sub", "sup", "table", "tbody", "td",
    "tfoot", "th", "thead", "tr", "u", "ul",
}  # fmt: skip

ATTRIBUTES = {
    "*": {"align", "valign", "width", "height", "bgcolor", "color", "dir", "title", "style", "border"},
    "a": {"href"},
    "img": {"src", "alt"},
    "font": {"color", "face", "size"},
    "table": {"cellpadding", "cellspacing"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
}

#: CSS properties kept in ``style``; anything that can load something (``url(…)``) is not among them.
STYLE_PROPERTIES = {
    "color", "background-color", "font-weight", "font-style", "font-size", "font-family", "text-align",
    "text-decoration", "vertical-align", "line-height", "white-space", "width", "height", "max-width",
    "margin", "margin-top", "margin-bottom", "margin-left", "margin-right",
    "padding", "padding-top", "padding-bottom", "padding-left", "padding-right",
    "border", "border-top", "border-bottom", "border-left", "border-right", "border-collapse", "border-color",
    "border-width", "border-style", "display",
}  # fmt: skip

_EXTERNAL_IMAGE = re.compile(r'(<img\b[^>]*?)\ssrc="(https?://[^"]*)"', re.IGNORECASE)
_CID_IMAGE = re.compile(r'src="cid:([^"]+)"', re.IGNORECASE)


def content_security_policy(*, allow_external: bool) -> str:
    """The policy of the frame that shows a mail."""
    images = "'self' data: https: http:" if allow_external else "'self' data:"
    return (
        f"default-src 'none'; img-src {images}; style-src 'unsafe-inline'; font-src 'none'; "
        "frame-ancestors 'self'; base-uri 'none'; form-action 'none'"
    )


def clean_html(html: str, *, allow_external: bool, cid_url: Callable[[str], str | None]) -> tuple[str, int]:
    """Clean the HTML of a mail for display.

    Args:
        html: The HTML as received.
        allow_external: Keep pictures from other servers.
        cid_url: Returns the address of an attachment for a ``cid:``
            reference, or ``None`` if there is no such attachment.

    Returns:
        The cleaned HTML and the number of external pictures that were held back.
    """
    cleaned = nh3.clean(
        html,
        tags=TAGS,
        attributes=ATTRIBUTES,
        url_schemes={"http", "https", "mailto", "cid"},
        link_rel="noopener noreferrer nofollow",
        filter_style_properties=STYLE_PROPERTIES,
        set_tag_attribute_values={"a": {"target": "_blank"}},
        strip_comments=True,
    )

    def inline_picture(match: re.Match[str]) -> str:
        url = cid_url(match.group(1).strip("<>"))
        return f'src="{url}"' if url else 'src=""'

    cleaned = _CID_IMAGE.sub(inline_picture, cleaned)
    blocked = 0
    if not allow_external:

        def hold_back(match: re.Match[str]) -> str:
            nonlocal blocked
            blocked += 1
            return f'{match.group(1)} data-blocked-src="{match.group(2)}" alt="▢"'

        cleaned = _EXTERNAL_IMAGE.sub(hold_back, cleaned)
    return cleaned, blocked


def frame_document(body: str) -> str:
    """The page shown in the frame: the cleaned mail with plain readable defaults."""
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>body{font:15px/1.45 system-ui,sans-serif;color:#1d1d1d;background:#fff;margin:12px;"
        "word-wrap:break-word}img{max-width:100%;height:auto}"
        "img[data-blocked-src]{display:inline-block;min-width:24px;min-height:16px;background:#ddd}"
        "table{max-width:100%}blockquote{border-left:3px solid #ccc;margin-left:0;padding-left:10px;color:#555}"
        "</style></head><body>" + body + "</body></html>"
    )


# --- Plain text of a mail: for the text part of sent mails and for the conversation (EML-034, EML-036) ---

#: Elements that start a line of their own.
_LINE_ELEMENTS = {
    "address", "article", "blockquote", "center", "dd", "div", "dl", "dt", "footer", "h1", "h2", "h3", "h4",
    "h5", "h6", "header", "hr", "ol", "pre", "section", "table", "tr", "ul",
}  # fmt: skip
#: Elements whose content is no text at all.
_HIDDEN_ELEMENTS = {"head", "script", "style", "title"}


class _TextMaker(HTMLParser):
    """Collects the text of HTML with line breaks where the browser would break lines."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0
        self.links: list[tuple[str, int]] = []

    def _break(self, count: int = 1) -> None:
        self.parts.append("\n" * count)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _HIDDEN_ELEMENTS:
            self.hidden += 1
        elif self.hidden:
            return
        elif tag == "br":
            self._break()
        elif tag == "p":
            self._break(2)
        elif tag == "li":
            self._break()
            self.parts.append("- ")
        elif tag in _LINE_ELEMENTS:
            self._break()
        elif tag in {"td", "th"}:
            self.parts.append(" ")
        elif tag == "a":
            self.links.append((dict(attrs).get("href") or "", len(self.parts)))
        elif tag == "img":
            alt = (dict(attrs).get("alt") or "").strip()
            if alt and alt != "▢":
                self.parts.append(alt)

    def handle_endtag(self, tag: str) -> None:
        if tag in _HIDDEN_ELEMENTS:
            self.hidden = max(0, self.hidden - 1)
        elif self.hidden:
            return
        elif tag == "p":
            self._break(2)
        elif tag in _LINE_ELEMENTS or tag == "li":
            self._break()
        elif tag == "a" and self.links:
            href, start = self.links.pop()
            label = " ".join("".join(self.parts[start:]).split())
            target = href[7:] if href.lower().startswith("mailto:") else href
            # A link whose text is not its address shows the address too, as mail programs do.
            if target and label and target.lower() != label.lower() and not href.lower().startswith(("tel:", "#")):
                self.parts.append(f" <{target}>")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(re.sub(r"\s+", " ", data))

    def text(self) -> str:
        lines = [line.strip() for line in "".join(self.parts).split("\n")]
        result: list[str] = []
        for line in lines:
            if not line and (not result or not result[-1]):
                continue
            result.append(line)
        return "\n".join(result).strip()


def html_to_text(html: str) -> str:
    """The text of some HTML, with line breaks and link addresses kept (EML-034, EML-036)."""
    maker = _TextMaker()
    maker.feed(html or "")
    maker.close()
    return maker.text()


_QUOTE_HEADER = re.compile(r"^(am|on)\b.{0,250}\b(schrieb|wrote)\b.{0,250}:$", re.IGNORECASE)
_SEPARATOR = re.compile(
    r"^(-{2,}\s*(original message|ursprüngliche nachricht|originalnachricht|forwarded message|"
    r"weitergeleitete nachricht)\s*-{2,}|_{10,})$",
    re.IGNORECASE,
)
_OUTLOOK_FROM = re.compile(r"^(from|von):\s*\S", re.IGNORECASE)
_OUTLOOK_FIELD = re.compile(r"^(sent|gesendet|date|datum|to|an|subject|betreff):", re.IGNORECASE)


def _starts_quote(lines: list[str], index: int) -> bool:
    line = lines[index].strip()
    if lines[index].rstrip() == "--" or line.startswith(">") or _SEPARATOR.match(line):
        return True
    if line.lower().startswith(("am ", "on ")):
        # Some programs break the line "On …, X <x@y> wrote:" in two.
        following = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if _QUOTE_HEADER.match(line) or _QUOTE_HEADER.match(f"{line} {following}"):
            return True
    if _OUTLOOK_FROM.match(line):
        return any(_OUTLOOK_FIELD.match(other.strip()) for other in lines[index + 1 : index + 4])
    return False


def split_quoted(text: str) -> tuple[str, str]:
    """Split a mail text into what is new and the rest – signature and quoted earlier mails (EML-036).

    The rest starts at the signature line ``-- ``, at a quoted line (``> …``),
    at "On … wrote:" / "Am … schrieb:", or at a separator such as "-----
    Original Message -----" or Outlook's "From: … Sent: …". A text without
    anything new of its own is returned whole.

    Returns:
        ``(new text, rest)``; the rest is empty if nothing was found.
    """
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for index in range(len(lines)):
        if _starts_quote(lines, index):
            new = "\n".join(lines[:index]).strip()
            if not new:
                break
            return new, "\n".join(lines[index:]).strip("\n")
    return "\n".join(lines).strip(), ""


#: Lines of text up to which the frame of a mail is short or medium (EML-036).
SHORT_FRAME_LINES = 10
MEDIUM_FRAME_LINES = 30


def frame_size(html: str, text: str = "") -> str:
    """How tall the frame of an HTML mail is drawn: ``"short"``, ``"medium"`` or ``""`` (tall) (EML-036).

    The frame cannot measure its content (it runs no scripts), so the size
    is estimated from the text: a one-liner should not take half the screen.
    """
    plain = text.strip() or html_to_text(html)
    lines = sum(max(1, -(-len(line) // 90)) for line in plain.splitlines()) if plain else 1
    weight = lines + 6 * len(re.findall(r"<img\b", html or "", re.IGNORECASE))
    if weight <= SHORT_FRAME_LINES:
        return "short"
    if weight <= MEDIUM_FRAME_LINES:
        return "medium"
    return ""
