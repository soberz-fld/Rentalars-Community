# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "ui": the rules behind the hour lines (VFG-033), the breakpoint of the phone menu (UIX-045) and the
texts of the first tab of a service case (PRJ-090) and of the block "Zusammenfassung" (EML-050)."""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.utils import translation

ROOT = Path(settings.BASE_DIR)
CSS = (ROOT / "static/css/app.css").read_text(encoding="utf-8")
JS = (ROOT / "static/js/app.js").read_text(encoding="utf-8")


def _block(text: str, title: str) -> str:
    """The block of a requirement appended to a shared file: from its heading to the next one."""
    start = text.index(title)
    following = text.find("/* ==== ", start + len(title))
    return text[start : following if following != -1 else len(text)]


class HourLinesStyleTests(SimpleTestCase):
    """VFG-033 (amended)."""

    def test_lines_are_not_tiles_of_the_row(self) -> None:
        """A tile is sized in 1/64 px and its error adds up along the row; the rows draw one gradient each."""
        block = _block(CSS, "==== VFG-033: the lines")
        row = re.search(r"\.timeline\.is-hourly \.tl-row \{(.*?)\}", block, re.S).group(1)
        self.assertEqual(row.count("repeating-linear-gradient("), 3)  # days, columns, hours
        self.assertIn("background-size: 100% 100%", row)
        self.assertIn("calc(100% / (var(--days) * 24))", row)
        # The head: one layer over the whole row of hours, under the labels; the cells draw no lines of their own.
        self.assertIn(".timeline.is-hourly .tl-hours-head::after", block)
        self.assertIn("grid-row: 2; grid-column: 1 / -1", block)
        self.assertRegex(block, r"\.timeline\.is-hourly \.tl-hour \{[^}]*z-index: 1;[^}]*background-image: none;")

    def test_the_block_comes_after_the_rules_it_replaces(self) -> None:
        self.assertLess(CSS.index("==== VFG-031, VFG-032, VFG-033, PER-039"), CSS.index("==== VFG-033: the lines"))


class PhoneMenuRulesTests(SimpleTestCase):
    """UIX-045: only where the side navigation turns into the top bar."""

    def test_one_breakpoint_in_style_sheet_and_script(self) -> None:
        """The top bar appears at 900 px (UIX-017); the drawer and its listeners use the same width."""
        self.assertIn(
            "@media (max-width: 900px) {\n  .app { grid-template-columns: 1fr; }\n  .topbar { display: flex;", CSS
        )
        style = _block(CSS, "==== UIX-045: on the phone")
        script = _block(JS, "==== UIX-045: on the phone")
        self.assertIn('window.matchMedia("(max-width: 900px)")', script)
        self.assertEqual(set(re.findall(r"@media \(max-width: (\d+)px\)", style)), {"900"})

    def test_nothing_of_it_outside_the_phone(self) -> None:
        """Above 900 px only "display: none" for the close button and the backdrop; every other rule is inside."""
        style = _block(CSS, "==== UIX-045: on the phone")
        outside = style[: style.index("@media")]
        rules = [line for line in outside.splitlines() if "{" in line and not line.lstrip().startswith(("/*", "*"))]
        self.assertEqual(
            rules,
            [
                ":root { --nav-scrim: rgba(0, 0, 0, 0.55); --nav-duration: 220ms; }",
                ".nav-close, .nav-scrim { display: none; }",
            ],
        )

    def test_as_in_the_app(self) -> None:
        """Width, dimming and speed of the companion app's drawer (BaseActivity): from the right."""
        style = _block(CSS, "==== UIX-045: on the phone")
        self.assertIn("width: min(300px, 86vw)", style)
        self.assertIn("inset: 0 0 0 auto", style)  # at the right edge
        self.assertIn("transform: translateX(100%)", style)
        self.assertIn("cubic-bezier(0, 0, 0.2, 1)", style)  # slowing down at the end
        self.assertIn("prefers-reduced-motion: no-preference", style)
        script = _block(JS, "==== UIX-045: on the phone")
        self.assertIn("var DURATION = 220;", script)
        self.assertIn("{ passive: false }", script)  # a swipe can stop the page from scrolling


class TextsTests(SimpleTestCase):
    """PRJ-090, EML-050, UIX-045: the English msgids and their German texts."""

    def test_german(self) -> None:
        with translation.override("de"):
            self.assertEqual(translation.pgettext("service case tab", "Overview"), "Überblick")
            self.assertEqual(translation.gettext("Summary"), "Zusammenfassung")
            self.assertEqual(translation.gettext("Summary by AI"), "Zusammenfassung durch KI")
            self.assertEqual(translation.gettext("Loading the summary …"), "Die Zusammenfassung wird geladen …")
            self.assertEqual(translation.gettext("Close menu"), "Menü schließen")
