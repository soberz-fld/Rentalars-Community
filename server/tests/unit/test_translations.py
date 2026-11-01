# SPDX-License-Identifier: GPL-3.0-or-later
"""The German language file is complete and consistent (NFA-026)."""

from __future__ import annotations

import re
from pathlib import Path

import polib
from django.conf import settings
from django.test import SimpleTestCase
from django.utils import translation

CATALOGUE = Path(settings.BASE_DIR) / "locale" / "de" / "LC_MESSAGES" / "django.po"
PLACEHOLDER = re.compile(r"%\(\w+\)[sd]|%[sd]|\{\w*\}")


class GermanCatalogueTests(SimpleTestCase):
    """Every text of the user interface has a German translation."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.catalogue = polib.pofile(str(CATALOGUE))

    def test_nothing_is_untranslated_or_marked_as_doubtful(self) -> None:
        self.assertEqual([entry.msgid for entry in self.catalogue.untranslated_entries()], [])
        self.assertEqual([entry.msgid for entry in self.catalogue.fuzzy_entries()], [])
        self.assertGreater(len(self.catalogue), 1000)

    def test_placeholders_survive_the_translation(self) -> None:
        """A missing ``%(count)s`` would crash the page that shows the text."""
        for entry in self.catalogue:
            sources = [entry.msgid, entry.msgid_plural] if entry.msgid_plural else [entry.msgid]
            allowed = {match for source in sources for match in PLACEHOLDER.findall(source)}
            translations = list(entry.msgstr_plural.values()) if entry.msgid_plural else [entry.msgstr]
            for text in translations:
                used = set(PLACEHOLDER.findall(text))
                self.assertLessEqual(used, allowed, entry.msgid)
                if not entry.msgid_plural:
                    self.assertEqual(used, allowed, entry.msgid)

    def test_compiled_file_is_up_to_date(self) -> None:
        """The server reads the compiled file; it must contain what the source says."""
        compiled = polib.mofile(str(CATALOGUE.with_suffix(".mo")))
        compiled_texts = {(entry.msgctxt, entry.msgid): entry.msgstr or entry.msgstr_plural for entry in compiled}
        for entry in self.catalogue:
            if entry.obsolete:
                continue
            self.assertEqual(
                compiled_texts.get((entry.msgctxt, entry.msgid)),
                entry.msgstr or entry.msgstr_plural,
                f"Run 'manage.py compilemessages': {entry.msgid!r}",
            )

    def test_german_is_what_users_see(self) -> None:
        self.assertEqual(settings.LANGUAGE_CODE, "de")
        with translation.override("de"):
            self.assertEqual(translation.gettext("Projects"), "Projekte")
            self.assertEqual(translation.pgettext("contact", "position"), "Funktion")
            self.assertEqual(translation.gettext("position"), "Position")
            self.assertEqual(
                translation.ngettext("%(count)s row", "%(count)s rows", 3) % {"count": 3},
                "3 Zeilen",
            )

    def test_terms_of_the_catalogue_are_used(self) -> None:
        """The user interface speaks the language of the requirements catalogue (2.1)."""
        expected = {
            "kit": "Set",
            "subrental": "Zumietung",
            "rental scale": "Staffel",
            "Packing list": "Packliste",  # UIX-029: British English
            "Shortages": "Fehlbestände",
            "Material": "Material",
            "billing mode": "Abrechnungsart",
            "surcharge": "Aufpreis",
        }
        translations = {entry.msgid: entry.msgstr for entry in self.catalogue if not entry.msgctxt}
        for english, german in expected.items():
            self.assertEqual(translations.get(english), german, english)
