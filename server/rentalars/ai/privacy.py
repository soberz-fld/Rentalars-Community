# SPDX-License-Identifier: GPL-3.0-or-later
"""What may go to a language model, and what may come back (information security of AI summaries; EML-056, NFA-079).

Two directions, both treated as hostile:

**Out (data minimisation).** The text of a summary is built from mails, notes
and chat messages. Before it is sent, :func:`prepare` removes what a summary
does not need and what would do harm elsewhere: bank data (IBAN, card
numbers), secrets (passwords, tokens, keys in links), e-mail addresses and
phone numbers. The texts are made plain first (:func:`sanitise`: invisible characters out, Unicode
compatibility form), so that nothing can be hidden from the filters by a zero-width space. Which classes are removed is a setting of the operator
(``AISettings.privacy_remove``); the defaults remove all of them. The
filters are heuristics for free text – they find what has a recognisable
shape (an IBAN is checked by its check digits, a card number by Luhn), not
a name or a street. What no filter can recognise stays: the operator
decides by the choice of the provider (a local model never leaves the
server).

The text between the delimiters of the prompts is data. A mail that writes
``>>>`` or ``<|im_start|>`` must not close the data block or open a role:
:func:`neutralise` takes those sequences apart, and strips invisible
characters (zero-width, bidirectional controls, "tag" characters) that are
used to hide instructions.

**In (untrusted output).** The model's answer is text from a system whose
input an attacker may have written. :func:`clean_output` makes it plain
text before it is stored: no HTML tags, no Markdown images or links (nothing
is fetched when somebody opens the page, an app or an export), no
``javascript:`` addresses, no control characters, and a length cap. The
pages show it escaped on top of that. No code reads the answer as a command.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field

#: The classes of data that can be removed from texts before they are sent (``AISettings.privacy_remove``).
IBAN = "iban"
CARD = "card"
SECRET = "secret"  # noqa: S105 - a name of a class, not a password
EMAIL = "email"
PHONE = "phone"
CLASSES = (IBAN, CARD, SECRET, EMAIL, PHONE)

#: Removed unless the operator switches a class off.
DEFAULT_REMOVE = [IBAN, CARD, SECRET, EMAIL, PHONE]

#: Longest summary kept (characters); the prompts ask for at most 350 words, about 2500 characters.
MAX_OUTPUT_CHARS = 8000
#: Longest project name put into a prompt.
MAX_NAME_CHARS = 120

REMOVED = {
    IBAN: "[IBAN removed]",
    CARD: "[card number removed]",
    SECRET: "[secret removed]",
    EMAIL: "[e-mail address removed]",
    PHONE: "[phone number removed]",
}


# --- Out ---------------------------------------------------------------------------------------------------


#: What may stand between the groups of an IBAN or a card number: blanks (the odd ones are made plain by NFKC
#: first), hyphens of every kind, dots and tabs – not a line break.
_SEPARATORS = " \\t.\\-\u2010-\u2015\u2212"
_IBAN = re.compile(rf"(?<![A-Za-z0-9])[A-Za-z]{{2}}\d{{2}}(?:[{_SEPARATORS}]?[A-Za-z0-9]){{11,30}}", re.IGNORECASE)
_CARD = re.compile(rf"(?<![\d.,])(?:\d[{_SEPARATORS}]?){{12,18}}\d(?![\d])")
_SECRET_LABEL = re.compile(
    r"(?i)\b(passwort|password|passwd|kennwort|pwd|pin|puk|zugangscode|zugangsdaten|access[ _-]?code|token|"
    r"api[ _-]?key|api[ _-]?schl\w+|secret|geheimzahl)\b(\s*[:=]\s*)(?!\[)(\S+)"
)
_SECRET_SENTENCE = re.compile(r"(?i)\b(passwort|password|kennwort)(\s+(?:ist|is|lautet)\s+)(?!\[)(\S+)")
_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{16,}")
_KEY_WORDS = re.compile(r"\b(?:sk|pk|rk|xox[abp]|ghp|glpat|AKIA)[-_][A-Za-z0-9_-]{12,}\b|\bAKIA[0-9A-Z]{16}\b")
_URL_SECRET = re.compile(
    r"(?i)([?&;](?:token|access_token|auth|key|api_key|apikey|password|passwd|pwd|secret|sig|signature|session|sid)=)"
    r"(?!\[)[^&\s#]+"
)
_OPAQUE = re.compile(
    r"(?<![A-Za-z0-9_-])(?=[A-Za-z0-9_-]*\d)(?=[A-Za-z0-9_-]*[A-Za-z])[A-Za-z0-9_-]{40,}(?![A-Za-z0-9_-])"
)
_ADDRESS_IN_BRACKETS = re.compile(r"\s*<[^<>\s@]+@[^<>\s@]+\.[^<>\s]+>")
_EMAIL = re.compile(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+")
#: Between the digits of a phone number: blanks, line breaks, dots, slashes, brackets and hyphens of every kind.
_PSEP = r"[\s./()\-\u2010-\u2015\u2212]"
_PHONE_INTERNATIONAL = re.compile(
    rf"(?<![\w+.])(?:\+|00)\d{{1,3}}{_PSEP}{{0,3}}(?:\(0\){_PSEP}{{0,3}})?\d(?:{_PSEP}{{0,3}}\d){{6,13}}"
)
_PHONE_NATIONAL = re.compile(rf"(?<![\w.,/+-])\(?0\d{{2,5}}\)?{_PSEP}{{0,3}}\d(?:{_PSEP}{{0,3}}\d){{4,10}}(?![\d])")


def _iban_valid(compact: str) -> bool:
    """The check digits of an IBAN (ISO 13616, modulo 97) – a random word with digits is not one."""
    if not 15 <= len(compact) <= 34 or not compact[:2].isalpha() or not compact[2:4].isdigit():
        return False
    moved = compact[4:] + compact[:4]
    digits = "".join(str(int(char, 36)) for char in moved)
    return int(digits) % 97 == 1


def _luhn_valid(digits: str) -> bool:
    """The Luhn check of card numbers."""
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2:
            value = value * 2 - 9 if value > 4 else value * 2
        total += value
    return total % 10 == 0


#: The length of an IBAN per country (ISO 13616); a country not listed is accepted at 15 to 34 characters.
_IBAN_LENGTH = {
    "AD": 24, "AE": 23, "AL": 28, "AT": 20, "AZ": 28, "BA": 20, "BE": 16, "BG": 22, "BH": 22, "BR": 29,
    "BY": 28, "CH": 21, "CR": 22, "CY": 28, "CZ": 24, "DE": 22, "DK": 18, "DO": 28, "EE": 20, "EG": 29,
    "ES": 24, "FI": 18, "FO": 18, "FR": 27, "GB": 22, "GE": 22, "GI": 23, "GL": 18, "GR": 27, "GT": 28,
    "HR": 21, "HU": 28, "IE": 22, "IL": 23, "IQ": 23, "IS": 26, "IT": 27, "JO": 30, "KW": 30, "KZ": 20,
    "LB": 28, "LC": 32, "LI": 21, "LT": 20, "LU": 20, "LV": 21, "MC": 27, "MD": 24, "ME": 22, "MK": 19,
    "MR": 27, "MT": 31, "MU": 30, "NL": 18, "NO": 15, "PK": 24, "PL": 28, "PS": 29, "PT": 25, "QA": 29,
    "RO": 24, "RS": 22, "SA": 24, "SC": 31, "SE": 24, "SI": 19, "SK": 24, "SM": 27, "TL": 23, "TN": 24,
    "TR": 26, "UA": 29, "VA": 22, "VG": 24, "XK": 20,
}  # fmt: skip


_SEPARATORS_SET = frozenset(" \t.-\u2010\u2011\u2012\u2013\u2014\u2015\u2212")


def _replace_ibans(text: str) -> tuple[str, int]:
    """Replace valid IBANs: the length of the country and the check digits must fit; the text after one stays."""
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        candidate = match.group(0)
        compact_chars = [(index, char) for index, char in enumerate(candidate) if char not in _SEPARATORS_SET]
        wanted = _IBAN_LENGTH.get(candidate[:2].upper())
        lengths = [wanted] if wanted else range(15, 35)
        for length in lengths:
            if length > len(compact_chars):
                continue
            end = compact_chars[length - 1][0] + 1
            compact = "".join(char for _index, char in compact_chars[:length]).upper()
            if _iban_valid(compact):
                count += 1
                return REMOVED[IBAN] + candidate[end:]
        return candidate

    return _IBAN.sub(replace, text), count


def _replace_cards(text: str) -> tuple[str, int]:
    """Replace numbers that pass the Luhn check and are 13 to 19 digits long."""
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        digits = re.sub(r"\D", "", match.group(0))
        if _luhn_valid(digits):
            count += 1
            return REMOVED[CARD]
        return match.group(0)

    return _CARD.sub(replace, text), count


def _replace_secrets(text: str) -> tuple[str, int]:
    """Values of "Passwort: …", bearer tokens, keys of known services, secrets in links, long opaque tokens."""
    count = 0

    def labelled(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return f"{match.group(1)}{match.group(2)}{REMOVED[SECRET]}"

    def whole(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return REMOVED[SECRET]

    def in_link(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return match.group(1) + "[secret removed]"

    text = _SECRET_LABEL.sub(labelled, text)
    text = _SECRET_SENTENCE.sub(labelled, text)
    text = _BEARER.sub(whole, text)
    text = _KEY_WORDS.sub(whole, text)
    text = _URL_SECRET.sub(in_link, text)
    text = _OPAQUE.sub(whole, text)
    return text, count


def _replace_emails(text: str) -> tuple[str, int]:
    """``Name <name@firma.example>`` becomes ``Name``; a bare address becomes a marker."""
    count = len(_ADDRESS_IN_BRACKETS.findall(text))
    text = _ADDRESS_IN_BRACKETS.sub("", text)
    text, more = _EMAIL.subn(REMOVED[EMAIL], text)
    return text, count + more


def _replace_phones(text: str) -> tuple[str, int]:
    """Phone numbers in the international (+49 …, 0049 …) and the national form (030 1234567)."""
    text, first = _PHONE_INTERNATIONAL.subn(REMOVED[PHONE], text)
    text, second = _PHONE_NATIONAL.subn(REMOVED[PHONE], text)
    return text, first + second


def redact(text: str, remove: Iterable[str]) -> tuple[str, dict[str, int]]:
    """The text without the classes named in ``remove``; and how often each class was found."""
    wanted = set(remove)
    found: dict[str, int] = {}
    steps = (
        (SECRET, _replace_secrets),
        (IBAN, _replace_ibans),
        (CARD, _replace_cards),
        (EMAIL, _replace_emails),
        (PHONE, _replace_phones),
    )
    for name, step in steps:
        if name in wanted and text:
            text, count = step(text)
            if count:
                found[name] = count
    return text, found


#: Invisible and control characters: zero-width, bidirectional controls, "tag" characters (category Cf), controls (Cc).
_KEEP = {"\n", "\t"}
_SPECIAL_TOKENS = re.compile(r"<\|[^|>]{0,40}\|>|\[/?INST\]|<</?SYS>>", re.IGNORECASE)
_OPEN = re.compile(r"<{3,}")
_CLOSE = re.compile(r">{3,}")


def strip_invisible(text: str) -> str:
    """Without control characters (but line breaks and tabs) and format characters (zero-width, bidi, tags)."""
    return "".join(
        char for char in text if char in _KEEP or unicodedata.category(char) not in {"Cc", "Cf", "Cs", "Co", "Cn"}
    )


def neutralise(text: str) -> str:
    """Take apart what could end the data block of a prompt or open a role of the chat template.

    ``<<<`` and ``>>>`` (the delimiters of the prompts) become ``‹‹‹`` and ``›››``; chat-template tokens such as
    ``<|im_start|>`` and ``[INST]`` lose their form; invisible characters are removed.
    """
    text = strip_invisible(text)
    text = _SPECIAL_TOKENS.sub(lambda match: "‹" + match.group(0)[1:-1] + "›", text)
    text = _OPEN.sub("‹‹‹", text)
    return _CLOSE.sub("›››", text)


def sanitise(text: str, remove: Iterable[str]) -> tuple[str, dict[str, int]]:
    """The one way a text becomes input for a model: invisible characters out, NFKC, data classes out, delimiters broken.

    The order matters: a zero-width space or a soft hyphen inside an address, a card number or
    the word "Passwort", or a full-width digit, must not keep a filter from seeing it – so the text is made
    plain *before* the filters look at it, and the delimiters are taken apart afterwards. Used for the
    summaries (:func:`prepare`), the drafts and the reading of old invoices.

    Returns:
        The text, and how often each class was removed.
    """
    text = unicodedata.normalize("NFKC", strip_invisible(text or ""))
    text, found = redact(text, remove)
    return neutralise(text), found


def one_line(text: str, limit: int = MAX_NAME_CHARS) -> str:
    """A user-written name as one short line for a prompt: no line breaks, no quotes, no delimiters."""
    text = " ".join(neutralise(text or "").split())
    text = text.replace("“", "'").replace("”", "'").replace('"', "'")
    return text[:limit].rstrip()


@dataclass
class Prepared:
    """The texts of a summary as they go to the model: cleaned, cut to the cap, with a hash of what was sent."""

    texts: list[str]
    input_hash: str
    #: How often each class was removed (the counts only, never the values).
    removed: dict[str, int] = field(default_factory=dict)
    #: Older entries left out because the whole text would be longer than the cap.
    dropped: int = 0

    @property
    def chars(self) -> int:
        """The characters that will be sent, at least."""
        return sum(len(text) for text in self.texts)


def prepare(rendered: list[str], *, remove: Iterable[str], max_chars: int, salt: str = "") -> Prepared:
    """Clean the rendered entries (oldest first); keep the newest ones that fit ``max_chars``.

    ``salt`` goes into the hash (scope, language): the same texts under another scope are another input.
    """
    import hashlib

    remove = list(remove)
    cleaned: list[str] = []
    removed: dict[str, int] = {}
    for text in rendered:
        text, found = sanitise(text, remove)
        for name, count in found.items():
            removed[name] = removed.get(name, 0) + count
        cleaned.append(text)
    kept: list[str] = []
    size = 0
    for text in reversed(cleaned):
        if kept and size + len(text) > max_chars:
            break
        kept.append(text)
        size += len(text) + 2
    kept.reverse()
    dropped = len(cleaned) - len(kept)
    digest = hashlib.sha256(salt.encode("utf-8"))
    for text in kept:
        digest.update(b"\x00")
        digest.update(text.encode("utf-8"))
    return Prepared(texts=kept, input_hash=digest.hexdigest(), removed=removed, dropped=dropped)


# --- In ----------------------------------------------------------------------------------------------------

_TAG = re.compile(r"</?[A-Za-z][^<>]{0,500}>|<!--.*?-->", re.DOTALL)
_IMAGE = re.compile(r"!\[([^\]\n]{0,200})\]\([^)\n]{0,2000}\)")
_LINK = re.compile(r"\[([^\]\n]{1,200})\]\(\s*([^)\s\n]{1,2000})[^)\n]*\)")
_REFERENCE = re.compile(r"^\s{0,3}\[[^\]\n]{1,100}\]:\s*\S+.*$", re.MULTILINE)
_BAD_SCHEME = re.compile(r"(?i)\b(javascript|vbscript)\s*:|\b(data)\s*:(?=\s*(?:text|image|application)/)")


def clean_output(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    """The model's answer as inert plain text.

    Whatever the answer contains – because an attacker wrote it into a mail –
    stays text: HTML tags are cut out, Markdown images are reduced to their
    description, links to "text (address)" so that no renderer turns them into
    something that is fetched or clicked, script-like addresses are broken up,
    control and invisible characters go, and the length is capped.
    """
    text = strip_invisible(text or "")
    text = _TAG.sub("", text)
    text = _IMAGE.sub(lambda match: match.group(1).strip() or "", text)
    text = _LINK.sub(lambda match: f"{match.group(1).strip()} ({match.group(2)})", text)
    text = _REFERENCE.sub("", text)
    text = _BAD_SCHEME.sub(lambda match: (match.group(1) or match.group(2)) + "∶", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text).strip()
    if len(text) > limit:
        text = text[: limit - 2].rstrip() + " …"
    return text
