# SPDX-License-Identifier: GPL-3.0-or-later
"""The page "About Rentalars" with the legal notices of the GPL, also without login (UIX-062, NFA-075)."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.test import Client
from django.urls import reverse

from tests.ui.base import UiTestCase


class AboutPageTests(UiTestCase):
    def test_the_notices_are_there_for_whoever_is_logged_in(self) -> None:
        page = self.assert_ok(self.client.get(reverse("core:about")))
        self.assertIn("Über Rentalars", page)
        self.assertIn("GNU General Public License", page)
        self.assertIn("ohne jede Gewährleistung", page)
        self.assertIn("fld-vt.de", page)

    def test_and_for_whoever_is_not(self) -> None:
        anonymous = Client()
        response = anonymous.get(reverse("core:about"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("GNU General Public License", response.content.decode())
        login = anonymous.get(reverse("accounts:login")).content.decode()
        self.assertIn(f'href="{reverse("core:about")}"', login)

    def test_the_menu_links_to_it(self) -> None:
        self.assertIn(f'href="{reverse("core:about")}"', self.assert_ok(self.client.get(reverse("core:home"))))

    def test_the_full_texts_are_served_as_plain_text(self) -> None:
        anonymous = Client()
        for name, start in (
            ("license", "GNU GENERAL PUBLIC LICENSE"),
            ("additional-terms", "# Additional terms"),
            ("third-party", "# Software von Dritten"),
        ):
            response = anonymous.get(reverse("core:about_text", args=[name]))
            self.assertEqual(response.status_code, 200, name)
            self.assertTrue(response["Content-Type"].startswith("text/plain"), name)
            self.assertIn(start, response.content.decode(), name)
        self.assertEqual(anonymous.get("/about/passwd.txt").status_code, 404)

    def test_the_additional_terms_do_not_reach_whoever_only_runs_rentalars(self) -> None:
        """NFA-075: the GPL binds conveying, not running; so the term does not name "over a network"."""
        text = (Path(settings.BASE_DIR) / "ADDITIONAL-TERMS.md").read_text(encoding="utf-8")
        self.assertNotIn("as their own service", text)
        self.assertNotIn("Dienst über das Netz –", text)
        self.assertIn("not apply to whoever only runs it", text)
