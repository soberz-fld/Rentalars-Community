# SPDX-License-Identifier: GPL-3.0-or-later
"""The colours of the interface: dark theme in the house colours, readable, with a light theme prepared (UIX-008)."""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

STYLESHEET = Path(settings.BASE_DIR) / "static" / "css" / "app.css"
TOKEN = re.compile(r"--([\w-]+):\s*([^;]+);")
COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)")


def tokens_of(block: str) -> dict[str, str]:
    """Read the tokens of one ``:root { … }`` block: colours and the shadow built from one."""
    return {name: value.strip() for name, value in TOKEN.findall(block)}


def luminance(colour: str) -> float:
    """Relative luminance of a ``#rrggbb`` colour as WCAG 2 defines it."""
    channels = [int(colour[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(first: str, second: str) -> float:
    """Contrast ratio of two colours, from 1 (the same) to 21 (black on white)."""
    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


class ThemeTests(SimpleTestCase):
    """UIX-008."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.css = STYLESHEET.read_text(encoding="utf-8")
        dark_start = cls.css.index("/* The dark theme: the default. */")
        light_start = cls.css.index(':root[data-theme="light"] {')
        cls.dark = tokens_of(cls.css[dark_start:light_start])
        cls.light = tokens_of(cls.css[light_start : cls.css.index("}", light_start)])
        print_start = cls.css.index("@media print {")
        cls.printed = tokens_of(cls.css[print_start : cls.css.index("}", print_start)])
        cls.rules = cls.css[cls.css.index("/* ---------- 2. Base") : print_start]

    def test_the_house_colours_are_the_base_of_the_dark_theme(self) -> None:
        self.assertEqual(self.dark["accent"], "#ee591f")
        self.assertEqual(self.dark["ink"], "#eeeeee")
        self.assertEqual(self.dark["line-strong"], "#727272")
        self.assertEqual(self.dark["tape"], "#eeeeee")

    def test_the_application_runs_in_the_dark_theme(self) -> None:
        self.assertIn("color-scheme: dark;", self.css[: self.css.index(':root[data-theme="light"]')])
        for name in ("base.html", "base_public.html"):
            page = (Path(settings.BASE_DIR) / "templates" / name).read_text(encoding="utf-8")
            self.assertIn('data-theme="dark"', page, name)
        # The dark surfaces really are dark, the text on them light.
        for name in ("paper", "surface", "surface-raised", "field", "nav"):
            self.assertLess(luminance(self.dark[name]), 0.03, name)

    def test_a_light_theme_only_needs_the_second_table(self) -> None:
        """Every colour is a token, and both themes define the same tokens."""
        self.assertEqual(set(self.light), set(self.dark))
        self.assertEqual(COLOUR.findall(self.rules), [], "a colour is written out instead of using a token")
        self.assertEqual(re.findall(r"var\(--([\w-]+)\)", self.rules).count("blue"), 0)
        used = set(re.findall(r"var\(--([\w-]+)\)", self.rules))
        self.assertLessEqual({name for name in used if name in self.dark or name in self.light}, set(self.dark))
        undefined = {name for name in used if name not in self.dark and not name.startswith(("font", "space"))}
        self.assertEqual(undefined - {"radius", "control-height", "nav-width"}, set())
        for name, value in self.dark.items():
            self.assertTrue(COLOUR.search(value), f"--{name} is not a colour")

    def test_paper_is_printed_with_the_light_theme(self) -> None:
        self.assertEqual(self.printed, self.light)

    def assert_readable(self, theme: dict[str, str], text: str, background: str, minimum: float) -> None:
        ratio = contrast(theme[text], theme[background])
        self.assertGreaterEqual(ratio, minimum, f"{text} on {background}: {ratio:.2f}:1")

    def test_text_is_readable_in_both_themes(self) -> None:
        """WCAG 2 AA: 4.5:1 for text, 3:1 for the borders of controls."""
        for theme in (self.dark, self.light):
            for background in ("paper", "surface", "surface-raised", "hover", "field"):
                self.assert_readable(theme, "ink", background, 7)
                self.assert_readable(theme, "ink-soft", background, 4.5)
                self.assert_readable(theme, "accent-text", background, 4.5)
                self.assert_readable(theme, "line-strong", background, 3)
            for text, background in (
                ("accent-ink", "accent"),
                ("accent-ink", "accent-strong"),
                ("tape-ink", "tape"),
                ("solid-ink", "solid"),
                ("green-ink", "green"),
                ("red-ink", "red"),
                ("nav-ink", "nav"),
                ("nav-ink-strong", "nav-raised"),
                ("accent-text", "accent-tint"),
                ("green", "green-tint"),
                ("green", "surface"),
                ("yellow-ink", "yellow-tint"),
                ("yellow-ink", "surface"),
                ("red", "red-tint"),
                ("red", "surface"),
                ("ink", "green-tint"),
                ("ink", "yellow-tint"),
                ("ink", "red-tint"),
                ("ink", "accent-tint"),
            ):
                self.assert_readable(theme, text, background, 4.5)

    def test_white_on_orange_would_not_be_readable(self) -> None:
        """Why buttons carry dark text: the house orange is too light for white lettering."""
        self.assertLess(contrast("#ffffff", self.dark["accent"]), 4.5)
        self.assertGreater(contrast(self.dark["accent-ink"], self.dark["accent"]), 4.5)

    def test_running_text_is_never_set_in_the_house_grey_on_dark(self) -> None:
        """#727272 on the dark surfaces reaches about 3.6:1 – enough for a border, not for text."""
        self.assertLess(contrast("#727272", self.dark["surface"]), 4.5)
        self.assertNotEqual(self.dark["ink-soft"], "#727272")

    def test_the_red_of_a_shortage_is_not_taken_for_the_orange_of_a_button(self) -> None:
        def hue(colour: str) -> float:
            import colorsys

            red, green, blue = (int(colour[index : index + 2], 16) / 255 for index in (1, 3, 5))
            return colorsys.rgb_to_hsv(red, green, blue)[0] * 360

        distance = abs(hue(self.dark["red"]) - hue(self.dark["accent"]))
        self.assertGreater(min(distance, 360 - distance), 25)

    def test_the_master_data_pages_share_the_theme(self) -> None:
        admin = (Path(settings.BASE_DIR) / "static" / "css" / "admin.css").read_text(encoding="utf-8")
        self.assertIn("--primary: #ee591f;", admin)
        self.assertIn("--body-bg: #141414;", admin)
        template = (Path(settings.BASE_DIR) / "templates" / "admin" / "base_site.html").read_text(encoding="utf-8")
        self.assertIn("css/admin.css", template)
        self.assertNotIn("theme.js", template)
