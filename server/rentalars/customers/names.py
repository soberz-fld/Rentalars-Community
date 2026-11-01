# SPDX-License-Identifier: GPL-3.0-or-later
"""First and last name of a contact person (KND-004, KND-011: contact names split).

``Contact.name`` stays the full display name ("Anna Berg"); it is
derived from ``first_name`` and ``last_name``. Where only a whole name is
known – older contacts, old API clients, import files with one
name column – :func:`split_name` finds the two parts with a conservative rule:

* "Berg, Anna" (one word before the comma) is last name Berg, first name Anna;
* otherwise the last word is the last name and everything before it the first
  name: "Anna Maria Berg" is ("Anna Maria", "Berg");
* the particles "von", "van", "de", "der", "zu", "zur" … stay with the last
  name: "Jan van der Berg" is ("Jan", "van der Berg");
* one word is a last name only: "Berg" is ("", "Berg").

Titles are not cut off: "Dr. Anna Berg" is ("Dr. Anna", "Berg").
:func:`first_name_for_greeting` leaves them out where a first name is
used alone ("Hallo Anna,").

Noise around the name (:func:`parse_name`, which :func:`split_name` is the short form of):

* text in parentheses is cut: "Anna Berg (Technik)" is Anna Berg;
* trailing commas go: "Berg," is the last name Berg;
* a comma that follows a whole name starts a remark: in "Anna Berg, Technik" the name is "Anna Berg" and "Technik" is
  neither part – it is the position of the contact when that is empty (``Contact.tidy_names``, the import);
* a leading Frau, Herr, Fr., Hr., Mr, Ms, Mrs or Miss is a salutation, not a first name: it goes to the salutation of
  the contact when that is empty and is dropped otherwise ("Frau Anna Berg" is Anna Berg with the salutation Frau).
  A word alone ("Herr") stays what it is, a name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Words in front of a last name that belong to it ("von Berg", "van der Berg").
PARTICLES = frozenset(
    {
        "von", "vom", "van", "de", "den", "der", "zu", "zur", "zum", "ten", "ter", "da", "di", "du", "la", "le",
        "del", "della", "dos", "das", "af", "el", "al", "bin", "ibn", "y",
    }
)  # fmt: skip

#: Academic titles; they are not a first name ("Dr." in "Dr. Anna").
TITLE_WORDS = frozenset(
    {"dr", "prof", "mag", "dipl", "ing", "med", "dent", "rer", "nat", "jur", "phil", "pol", "mult", "hc", "mba",
     "msc", "bsc", "ma", "ba", "phd", "fh", "univ", "habil", "pd"}
)  # fmt: skip

#: Words that address a person and are no first name when they stand in front of a name (compared in lower case).
SALUTATION_WORDS = frozenset({"frau", "fr", "herr", "hr", "mr", "ms", "mrs", "miss"})

_SPACES = re.compile(r"\s+")
_PARENTHESES = re.compile(r"\([^)]*\)?")


def tidy(text: str) -> str:
    """A name with single spaces and without spaces at both ends."""
    return _SPACES.sub(" ", text or "").strip()


def join_name(first_name: str, last_name: str) -> str:
    """The full name: first name, a space, last name; ``Anna Berg``."""
    return " ".join(part for part in (tidy(first_name), tidy(last_name)) if part)


def _is_particle(word: str) -> bool:
    return word.casefold() in PARTICLES


def _last_name_start(words: list[str]) -> int:
    """The index of the first word of the last name: the last word, and the particles in front of it."""
    index = len(words) - 1
    while index > 0 and _is_particle(words[index - 1]):
        index -= 1
    return index


@dataclass(frozen=True)
class ParsedName:
    """What :func:`parse_name` finds in a text: the two parts, a leading salutation and a remark."""

    first_name: str = ""
    last_name: str = ""
    salutation: str = ""
    remark: str = ""


def _is_surname_first(words: list[str]) -> bool:
    """Whether words before a comma read as a last name ("Berg", "von Berg") – so "Berg, Anna" is Anna Berg."""
    return bool(words) and all(_is_particle(word) for word in words[:-1])


def parse_name(name: str) -> ParsedName:
    """Find first and last name in a whole name, and set aside the salutation and remark around it.

    >>> parse_name("Frau Anna Berg (Technik)")
    ParsedName(first_name='Anna', last_name='Berg', salutation='Frau', remark='')
    >>> parse_name("Anna Berg, Technik")
    ParsedName(first_name='Anna', last_name='Berg', salutation='', remark='Technik')
    """
    text = _PARENTHESES.sub(" ", name or "")
    segments = [part for part in (tidy(segment) for segment in text.split(",")) if part]
    if not segments:
        return ParsedName()
    words = segments[0].split()
    salutation = ""
    if len(words) > 1 and words[0].rstrip(".").casefold() in SALUTATION_WORDS:
        salutation = words.pop(0)
    rest = segments[1:]
    if rest and _is_surname_first(words):
        # "Berg, Anna" and "von Berg, Anna, Technik": last name, first name, anything after is a remark.
        return ParsedName(rest[0], " ".join(words), salutation, ", ".join(rest[1:]))
    # "Anna Berg, Technik": a comma after a whole name starts a remark.
    start = _last_name_start(words)
    return ParsedName(" ".join(words[:start]), " ".join(words[start:]), salutation, ", ".join(rest))


def split_name(name: str) -> tuple[str, str]:
    """Split a full name into (first name, last name); see the module description for the rule.

    >>> split_name("Anna Berg")
    ('Anna', 'Berg')
    >>> split_name("Berg, Anna")
    ('Anna', 'Berg')
    >>> split_name("Jan van der Berg")
    ('Jan', 'van der Berg')
    """
    parsed = parse_name(name)
    return parsed.first_name, parsed.last_name


def is_title(word: str) -> bool:
    """Whether a word is an academic title such as "Dr.", "Prof." or "Dipl.-Ing."."""
    parts = [part for part in re.split(r"[.\-]+", word.casefold()) if part]
    return bool(parts) and all(part in TITLE_WORDS for part in parts)


def first_name_for_greeting(first_name: str) -> str:
    """The first name without leading titles: "Dr. Anna" gives "Anna"; "Dr." alone gives ""."""
    words = tidy(first_name).split()
    while words and is_title(words[0]):
        words.pop(0)
    return " ".join(words)
