# SPDX-License-Identifier: GPL-3.0-or-later
"""The default texts of the document templates in English or German (DOK-018).

The requirement: a button that takes over the English default texts of the templates (and back to German); own texts
are shown beforehand, nothing is overwritten without confirmation.

The page Settings → Document templates → "Template texts in English or
German" and ``/document-templates/defaults`` compare the templates with the
default texts of a language (``services.DEFAULT_TEMPLATES``,
``services.DEFAULT_TEMPLATES_ENGLISH``): for every kind, which of heading,
introduction and closing text would change. A field that holds neither the
German nor the English default text is an *own text*. It is shown like the
others, but only taken over when it is chosen on the page or asked for with
``include_own`` in the API. Footer, logo and the validity of the offer are
never touched. Nothing is written before the page's button is pressed (or
``POST`` is sent); the change log keeps the previous texts, because
:class:`~rentalars.documents.models.DocumentTemplate` is audited.

The language of the documents (``CompanyProfile.document_language``, UIX-029)
is a setting of its own: it decides the fixed texts of the documents –
column heads, dates, amounts –, while the templates hold the company's own
texts. Taking over the texts switches it too only when asked for
(``document_language``), never by itself.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from django.db import transaction

from rentalars.documents.models import DocumentKind, DocumentTemplate
from rentalars.documents.services import DEFAULT_TEMPLATES, DEFAULT_TEMPLATES_ENGLISH, template_for

#: The fields that have default texts; footer, logo and validity are the company's alone.
TEXT_FIELDS = ("title", "introduction", "closing")
#: The languages with default texts.
LANGUAGES = ("de", "en")


def defaults_of(language: str) -> dict[str, dict[str, Any]]:
    """The default texts of a language, by kind."""
    return DEFAULT_TEMPLATES_ENGLISH if language == "en" else DEFAULT_TEMPLATES


def fingerprint(text: str) -> str:
    """A short sign of a text, to see whether it changed since a page showed it."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass
class FieldChange:
    """One field of a template that the default text of the language would change."""

    kind: str
    name: str
    current: str
    new: str
    #: Neither the German nor the English default text: written by the company.
    own: bool

    @property
    def key(self) -> str:
        """``<kind>:<field>`` – the value of its tick box and its name in the API."""
        return f"{self.kind}:{self.name}"

    @property
    def label(self) -> str:
        """The name of the field, e.g. "Introduction"."""
        text = str(DocumentTemplate._meta.get_field(self.name).verbose_name)
        return text[:1].upper() + text[1:]

    @property
    def seen(self) -> str:
        """The :func:`fingerprint` of the current text."""
        return fingerprint(self.current)

    def document(self) -> dict[str, Any]:
        """As JSON for the API."""
        return {"field": self.name, "current": self.current, "new": self.new, "own": self.own}


@dataclass
class Comparison:
    """A template and the fields the default texts of the language would change."""

    template: DocumentTemplate
    changes: list[FieldChange] = field(default_factory=list)

    @property
    def kind(self) -> str:
        """The kind of document."""
        return self.template.kind

    @property
    def label(self) -> str:
        """The kind as a name, e.g. "Offer"."""
        return self.template.get_kind_display()

    @property
    def has_own(self) -> bool:
        """Whether one of the fields holds an own text."""
        return any(change.own for change in self.changes)


@dataclass
class Result:
    """What taking over the default texts did."""

    language: str
    #: The fields overwritten with the default text.
    changed: list[FieldChange] = field(default_factory=list)
    #: Own texts left as they are, because they were not chosen.
    kept_own: list[FieldChange] = field(default_factory=list)
    #: Fields changed since the page showed them – not overwritten (nothing without confirmation).
    stale: list[FieldChange] = field(default_factory=list)
    #: Whether the language of the documents was switched as well.
    document_language_changed: bool = False

    @property
    def templates(self) -> int:
        """How many templates got new texts."""
        return len({change.kind for change in self.changed})


def compare(language: str) -> list[Comparison]:
    """Every kind of document with the fields the default texts of ``language`` would change (DOK-018).

    A template that does not exist yet is created with the start texts
    first, as everywhere else (``services.template_for``).
    """
    if language not in LANGUAGES:
        raise ValueError(language)
    comparisons = []
    for kind in DocumentKind.values:
        template = template_for(kind)
        german, english = DEFAULT_TEMPLATES[DocumentKind(kind)], DEFAULT_TEMPLATES_ENGLISH[DocumentKind(kind)]
        wanted = english if language == "en" else german
        comparison = Comparison(template)
        for name in TEXT_FIELDS:
            current = getattr(template, name)
            if current == wanted[name]:
                continue
            own = current not in (german[name], english[name])
            comparison.changes.append(FieldChange(kind, name, current, wanted[name], own))
        comparisons.append(comparison)
    return comparisons


def suggested_language() -> str:
    """The language a page offers first: the other one than the texts are in now.

    The language whose default texts more fields already hold is the one
    the templates are in; with as many of each (all own texts, say) the
    other one than the language of the documents.
    """
    from rentalars.core.i18n import document_language

    held = dict.fromkeys(LANGUAGES, 0)
    for template in DocumentTemplate.objects.all():
        for language in LANGUAGES:
            texts = defaults_of(language).get(template.kind) or {}
            held[language] += sum(1 for name in TEXT_FIELDS if getattr(template, name) == texts.get(name))
    if held["de"] != held["en"]:
        return "en" if held["de"] > held["en"] else "de"
    return "de" if document_language() == "en" else "en"


def take_over(
    language: str,
    *,
    chosen: Iterable[str] | None = None,
    seen: dict[str, str] | None = None,
    kinds: Iterable[str] | None = None,
    include_own: bool = False,
    document_language: bool = False,
) -> Result:
    """Overwrite heading, introduction and closing text with the default texts of ``language`` (DOK-018).

    Args:
        language: "de" or "en".
        chosen: The keys (``<kind>:<field>``) ticked on the page; ticking an
            own text is the confirmation to replace it. ``None``: every field
            of ``kinds`` that would change, own texts only with ``include_own``.
        seen: For ``chosen``: the :func:`fingerprint` of each text when the
            page showed it. A text changed since is not overwritten.
        kinds: The kinds of document; ``None``: all.
        include_own: Without ``chosen``: replace own texts too.
        document_language: Switch the language of the documents to
            ``language`` as well (``CompanyProfile.document_language``).

    Footer, logo and validity stay as they are. Each changed template is
    saved once and logged with its previous texts.
    """
    chosen_keys = set(chosen) if chosen is not None else None
    wanted_kinds = set(kinds) if kinds is not None else None
    result = Result(language=language)
    with transaction.atomic():
        for comparison in compare(language):
            if wanted_kinds is not None and comparison.kind not in wanted_kinds:
                continue
            taken = []
            for change in comparison.changes:
                if chosen_keys is not None:
                    if change.key not in chosen_keys:
                        if change.own:
                            result.kept_own.append(change)
                        continue
                    if seen is not None and seen.get(change.key) != change.seen:
                        result.stale.append(change)
                        continue
                elif change.own and not include_own:
                    result.kept_own.append(change)
                    continue
                taken.append(change)
            if taken:
                for change in taken:
                    setattr(comparison.template, change.name, change.new)
                comparison.template.save(update_fields=[change.name for change in taken])
                result.changed.extend(taken)
        if document_language:
            result.document_language_changed = _switch_document_language(language)
    return result


def _switch_document_language(language: str) -> bool:
    """Set the language of the documents (UIX-029); return whether it changed. Logged as a change of the company."""
    from rentalars.core.models import CompanyProfile

    company = CompanyProfile.load()
    if company.document_language == language:
        return False
    company.document_language = language
    company.save(update_fields=["document_language"])
    return True
