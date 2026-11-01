# SPDX-License-Identifier: GPL-3.0-or-later
"""The manual in pages per chapter (UIX-029). (UIX-057)

The requirement: the manual is split into one page per chapter (/manual/1/, /manual/2/, ...); before, it loaded slowly
because all 18 chapters stood directly under /manual/.

* ``/manual/`` is the table of contents: the introduction, a search, every chapter with a short description.
* ``/manual/<n>/`` shows chapter *n* only, with the chapters and its sections beside it and "previous" / "next";
  an unknown number is a 404.
* An old address with an anchor (``/manual/#7-projekte-planen``) is forwarded by a small script that asks
  ``/manual/anchors/``; links between chapters point to the page of the chapter they name.
* Each chapter is rendered on its own, the first time it is asked for, and kept.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from rentalars.core import manual
from tests.ui.base import UiTestCase

GERMAN = (
    "# Handbuch\n\nRentalars, Version 1.\n\nEine Einleitung über das ganze Handbuch, lang genug.\n\n**Inhalt**\n\n"
    "1. [Anfang](#1-anfang)\n2. [Ende](#2-ende)\n\n---\n\n"
    "## 1. Anfang\n\nHier beginnt alles, mit einem ersten Absatz, der lang genug ist für eine Beschreibung.\n\n"
    "### Erste Schritte\n\nSiehe [das Ende](#2-ende), [Folgen](#folgen) und [hier](#1-anfang) und "
    "[die Anleitung](../betrieb/import.md).\n\n```\n## Das ist kein Kapitel\n```\n\n"
    "## 2. Ende\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n### Folgen\n\nSchluss. <script>alert(1)</script>\n"
)
ENGLISH = "# Manual\n\n## 1. Start\n\nThe start of everything, in a first paragraph long enough to describe it.\n"


def write_manuals(base: Path, *, english: bool = False) -> None:
    """A small manual in German – and, if asked, in English – under ``base``."""
    (base / "docs/handbuch").mkdir(parents=True, exist_ok=True)
    (base / "docs/handbuch/benutzerhandbuch.md").write_text(GERMAN, encoding="utf-8")
    if english:
        (base / "docs/en").mkdir(parents=True, exist_ok=True)
        (base / "docs/en/user-manual.md").write_text(ENGLISH, encoding="utf-8")


class SplitTests(SimpleTestCase):
    """The file becomes an introduction and chapters."""

    def load(self, **options: bool) -> manual.Manual:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        write_manuals(Path(folder.name), **options)
        with override_settings(BASE_DIR=Path(folder.name)):
            return manual.manual_for("de")

    def test_chapters_title_and_introduction(self) -> None:
        loaded = self.load()
        self.assertEqual([chapter.title for chapter in loaded.chapters], ["1. Anfang", "2. Ende"])
        self.assertEqual(loaded.title, "Handbuch")
        self.assertIn("Eine Einleitung", loaded.introduction)
        self.assertNotIn("Inhalt", loaded.introduction)  # the list of the file is replaced by the page's contents
        self.assertNotIn("1-anfang", loaded.introduction)

    def test_a_heading_inside_a_code_block_is_no_chapter(self) -> None:
        loaded = self.load()
        self.assertEqual(len(loaded.chapters), 2)
        self.assertIn("## Das ist kein Kapitel", loaded.chapters[0].markdown)
        self.assertNotIn("kein-kapitel", loaded.anchors())

    def test_chapter_numbers(self) -> None:
        loaded = self.load()
        self.assertEqual(loaded.chapter(1).title, "1. Anfang")
        for number in (0, 3, -1):
            self.assertIsNone(loaded.chapter(number))

    def test_descriptions_and_sections(self) -> None:
        loaded = self.load()
        self.assertTrue(loaded.chapters[0].description.startswith("Hier beginnt alles"))
        self.assertEqual(loaded.chapters[1].description, "")  # begins with a table
        self.assertEqual(loaded.chapters[0].section_names, ["Erste Schritte"])

    def test_the_anchors_know_their_chapter(self) -> None:
        self.assertEqual(
            {slug: number for slug, number in self.load().anchors().items() if slug != "handbuch"},
            {"1-anfang": 1, "erste-schritte": 1, "2-ende": 2, "folgen": 2},
        )

    def test_links_between_chapters_point_to_their_page(self) -> None:
        html = self.load().chapter(1).html
        self.assertIn('href="/manual/2/#2-ende"', html)  # another chapter
        self.assertIn('href="/manual/2/#folgen"', html)
        self.assertIn('href="#1-anfang"', html)  # the same page
        self.assertIn('id="erste-schritte"', html)
        self.assertNotIn("import.md", html)
        self.assertIn('<a href="/manual/guides/import/" rel="noopener noreferrer">die Anleitung</a>', html)

    def test_cleaned(self) -> None:
        html = self.load().chapter(2).html
        self.assertNotIn("<script", html)
        self.assertIn('<table tabindex="0">', html)

    def test_a_chapter_is_rendered_when_asked_for_and_once(self) -> None:
        loaded = self.load()
        self.assertTrue(all(chapter._html is None for chapter in loaded.chapters))
        first = loaded.chapter(2).html
        self.assertIsNone(loaded.chapter(1)._html)  # the other chapter was not touched
        self.assertIs(loaded.chapter(2).html, first)  # the same string: kept

    def test_the_cache_follows_the_file(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            write_manuals(base)
            with override_settings(BASE_DIR=base):
                first = manual.manual_for("de")
                self.assertIs(manual.manual_for("de"), first)
                path = base / "docs/handbuch/benutzerhandbuch.md"
                path.write_text(GERMAN.replace("## 2. Ende", "## 2. Schluss"), encoding="utf-8")
                import os

                os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 5_000_000_000))
                again = manual.manual_for("de")
                self.assertIsNot(again, first)
                self.assertEqual(again.chapter(2).title, "2. Schluss")

    def test_search(self) -> None:
        loaded = self.load()
        results = loaded.search("schluss")
        self.assertEqual([(hit["chapter"].number, hit["anchor"]) for hit in results], [(2, "folgen")])
        self.assertIn(("Schluss", True), results[0]["snippet"])
        self.assertEqual(loaded.search("schluss anfang"), [])  # every word must occur in the section
        self.assertEqual(loaded.search("   "), [])
        self.assertEqual([hit["heading"] for hit in loaded.search("Schritte")], ["Erste Schritte"])
        self.assertEqual(len(loaded.search("e" * 500)), 0)  # a long query is cut, not a problem


class ManualPagesTests(UiTestCase):
    """The pages of the real manual, in both languages."""

    def english(self) -> None:
        self.admin_user.language = "en"
        self.admin_user.save()

    def test_the_contents_page(self) -> None:
        page = self.assert_ok(self.client.get(reverse("core:manual")))
        self.assertIn("<h1>Handbuch</h1>", page)
        for number in range(1, 19):
            self.assertIn(f'href="{reverse("core:manual_chapter", args=[number])}"', page)
        self.assertIn("4. Material", page)
        self.assertIn("Dieses Handbuch erklärt die Arbeit mit Rentalars", page)
        self.assertIn('role="search"', page)
        # The text of the chapters is not on this page: it is a fraction of the 750 KB of the old one.
        self.assertLess(len(page), 120_000)
        self.assertNotIn('id="1-das-wichtigste-in-fünf-minuten"', page)

    def test_every_chapter_has_its_page_in_both_languages(self) -> None:
        for language in ("de", "en"):
            if language == "en":
                self.english()
            contents = self.assert_ok(self.client.get(reverse("core:manual")))
            for number in range(1, 19):
                with self.subTest(language=language, chapter=number):
                    url = reverse("core:manual_chapter", args=[number])
                    self.assertEqual(url, f"/manual/{number}/")
                    page = self.assert_ok(self.client.get(url))
                    self.assertIn(f'<h2 id="{number}-', page)  # the chapter's own heading
                    self.assertEqual(page.count('aria-current="page"'), 2)  # the menu entry and the chapter's
                    self.assertIn(f'lang="{"en-GB" if language == "en" else "de"}"', page)
                    self.assertEqual('rel="prev"' in page, number > 1)
                    self.assertEqual('rel="next"' in page, number < 18)
                    self.assertLess(len(page), 400_000)
                    self.assertIn(f'href="/manual/{number}/"', contents)

    def test_previous_and_next(self) -> None:
        page = self.assert_ok(self.client.get("/manual/4/"))
        self.assertIn('rel="prev" href="/manual/3/"', page)
        self.assertIn('rel="next" href="/manual/5/"', page)
        self.assertIn("3. Die ersten Schritte nach der Installation", page)
        self.assertIn("5. Produkte", page)
        first = self.assert_ok(self.client.get("/manual/1/"))
        self.assertNotIn('rel="prev"', first)
        self.assertIn('rel="next" href="/manual/2/"', first)

    def test_unknown_chapters_are_404(self) -> None:
        for url in ("/manual/0/", "/manual/19/", "/manual/999/", "/manual/abc/", "/manual/-1/"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_the_menu_entry_leads_to_the_contents_and_stays_marked_in_a_chapter(self) -> None:
        home = self.assert_ok(self.client.get(reverse("core:home")))
        self.assertIn(f'href="{reverse("core:manual")}"', home)
        chapter = self.assert_ok(self.client.get("/manual/7/"))
        self.assertRegex(chapter, r'<a href="/manual/"[^>]*aria-current="page"[^>]*>')

    def test_chapter_pages_need_a_login(self) -> None:
        from django.test import Client

        for url in ("/manual/", "/manual/3/", "/manual/anchors/"):
            with self.subTest(url=url):
                response = Client().get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/login/", response["Location"])

    def test_the_anchors_for_old_addresses(self) -> None:
        response = self.client.get(reverse("core:manual_anchors"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["language"], "de")
        self.assertEqual(data["chapters"]["4-material"], 4)
        self.assertEqual(data["chapters"]["7-projekte-planen"], 7)
        self.assertIn("private", response["Cache-Control"])
        # Every anchor of the file that has a chapter is there, the sections too.
        self.assertGreater(len(data["chapters"]), 150)
        self.english()
        data = self.client.get(reverse("core:manual_anchors")).json()
        self.assertEqual((data["language"], data["chapters"]["7-planning-projects"]), ("en", 7))

    def test_the_contents_page_carries_the_script_that_forwards_old_addresses(self) -> None:
        page = self.assert_ok(self.client.get(reverse("core:manual")))
        self.assertRegex(page, r'<script src="/static/js/manual\.js\?v=\w+" data-anchors="/manual/anchors/"')
        self.assertIn('data-anchors="/manual/anchors/"', page)
        source = (Path(__file__).resolve().parents[2] / "static/js/manual.js").read_text(encoding="utf-8")
        self.assertIn("window.location.replace", source)

    def test_every_link_of_every_chapter_leads_somewhere(self) -> None:
        """Links within the manual: to an id of the same page or to the page of the chapter that has it."""
        for language in ("de", "en"):
            loaded = manual.manual_for(language)
            ids = {
                chapter.number: set(re.findall(r'<h[1-6] id="([^"]+)"', chapter.html)) for chapter in loaded.chapters
            }
            for chapter in loaded.chapters:
                for href in re.findall(r'<a href="([^"]+)"', chapter.html):
                    with self.subTest(language=language, chapter=chapter.number, href=href):
                        if href.startswith("#"):
                            self.assertIn(href[1:], ids[chapter.number])
                        elif href.startswith("/manual/guides/"):
                            self.assertIn(href.split("/")[3], manual.GUIDES)  # An operating guide
                        elif href.startswith("/manual/"):
                            target, _hash, anchor = href[len("/manual/") :].partition("#")
                            self.assertIn(anchor, ids[int(target.rstrip("/"))])

    def test_the_search(self) -> None:
        page = self.assert_ok(self.client.get(reverse("core:manual"), {"q": "Rabatt"}))
        self.assertIn("<mark>", page)
        self.assertRegex(page, r'href="/manual/\d+/#[^"]+"')
        self.assertIn("Abschnitte für „Rabatt“", page)
        nothing = self.assert_ok(self.client.get(reverse("core:manual"), {"q": "qqqxyzzy"}))
        self.assertIn("Kein Abschnitt des Handbuchs enthält alle diese Wörter.", nothing)
        self.assertIn("4. Material", nothing)  # the chapters stay below

    def test_the_search_escapes_what_was_typed(self) -> None:
        page = self.assert_ok(self.client.get(reverse("core:manual"), {"q": "<script>alert(1)</script>"}))
        self.assertNotIn("<script>alert(1)", page)

    def test_a_language_without_a_manual_shows_the_german_one_with_a_note(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            write_manuals(Path(folder))
            with override_settings(BASE_DIR=Path(folder)):
                self.english()
                page = self.assert_ok(self.client.get("/manual/1/"))
                self.assertIn("Hier beginnt alles", page)
                self.assertIn("The English manual is not available yet", page)

    def test_without_any_manual_file_the_pages_are_404(self) -> None:
        with tempfile.TemporaryDirectory() as folder, override_settings(BASE_DIR=Path(folder)):
            for url in ("/manual/", "/manual/1/", "/manual/anchors/"):
                self.assertEqual(self.client.get(url).status_code, 404)


class GuideTests(UiTestCase):
    """The operating guides are part of the manual (Betriebsanleitungen im Handbuch direkt verlinken)."""

    def english(self) -> None:
        self.admin_user.language = "en"
        self.admin_user.save()

    def test_every_guide_has_its_page_in_both_languages(self) -> None:
        for language in ("de", "en"):
            if language == "en":
                self.english()
            contents = self.assert_ok(self.client.get(reverse("core:manual")))
            for key in manual.GUIDES:
                with self.subTest(language=language, key=key):
                    url = reverse("core:manual_guide", args=[key])
                    self.assertEqual(url, f"/manual/guides/{key}/")
                    page = self.assert_ok(self.client.get(url))
                    self.assertIn(f'data-guide="{key}"', page)
                    self.assertIn(f'lang="{"en-GB" if language == "en" else "de"}"', page)
                    self.assertIn(f'href="{url}"', contents)  # listed on the contents page
                    self.assertNotIn("The English manual is not available", page)

    def test_the_manual_links_to_the_guides(self) -> None:
        for language in ("de", "en"):
            html = " ".join(chapter.html for chapter in manual.manual_for(language).chapters)
            html += manual.manual_for(language).introduction_html
            with self.subTest(language=language):
                self.assertNotIn('class="manual-file"', html.replace('class="manual-file">THIRD', ""))
                for key in ("operation", "backup", "encryption", "import", "installation"):
                    self.assertIn(f'href="/manual/guides/{key}/', html)

    def test_links_inside_the_guides_lead_to_guides_or_to_the_manual(self) -> None:
        for language in ("de", "en"):
            for guide in manual.guides_for(language):
                ids = {}
                for other in manual.guides_for(language):
                    ids[other.key] = set(re.findall(r'<h[1-6] id="([^"]+)"', other.html))
                for href in re.findall(r'<a href="([^"]+)"', guide.html):
                    with self.subTest(language=language, guide=guide.key, href=href):
                        if href.startswith("/manual/guides/"):
                            target, _hash, anchor = href[len("/manual/guides/") :].partition("#")
                            self.assertIn(target.rstrip("/"), manual.GUIDES)
                            if anchor:
                                self.assertIn(anchor, ids[target.rstrip("/")])
                        elif href.startswith("#"):
                            self.assertIn(href[1:], ids[guide.key])
                        elif href.startswith("/manual/"):
                            self.assertEqual(href.split("#")[0], "/manual/")
                        else:
                            self.assertRegex(href, r"^(https?://|mailto:)")

    def test_an_unknown_guide_is_404_and_a_login_is_needed(self) -> None:
        from django.test import Client

        for key in ("nothing", "..", "sicherung"):
            with self.subTest(key=key):
                self.assertEqual(self.client.get(f"/manual/guides/{key}/").status_code, 404)
        response = Client().get("/manual/guides/backup/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_the_links_of_a_guide_to_the_manual(self) -> None:
        page = self.assert_ok(self.client.get("/manual/guides/operation/"))
        self.assertIn('href="/manual/"', page)
        self.assertIn('href="/manual/guides/backup/"', page)
