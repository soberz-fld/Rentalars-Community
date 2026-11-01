# SPDX-License-Identifier: GPL-3.0-or-later
"""Static files get an address that changes with their content (NFA-065)."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from django.templatetags.static import static
from django.test import override_settings
from django.urls import reverse

from rentalars.core.staticfiles import fingerprint
from tests.helpers import RentalarsTestCase, make_user


class FingerprintTests(RentalarsTestCase):
    """After an update the browser must fetch the new style sheet, not use the one it kept."""

    def test_the_address_carries_a_fingerprint_of_the_content(self) -> None:
        address = static("css/app.css")
        self.assertRegex(address, r"^/static/css/app\.css\?v=[0-9a-f]{10}$")
        self.assertEqual(address, static("css/app.css"))  # the same file, the same address
        self.assertNotEqual(address.split("=")[1], static("js/app.js").split("=")[1])

    def test_a_changed_file_gets_a_new_address(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "css" / "app.css"
            path.parent.mkdir()
            path.write_text("body { color: black; }")
            with override_settings(STATIC_ROOT=folder, STATICFILES_DIRS=[]):
                before = static("css/app.css")
                path.write_text("body { color: white; }")
                os.utime(path, (path.stat().st_atime, path.stat().st_mtime + 5))
                after = static("css/app.css")
        self.assertRegex(before, r"\?v=[0-9a-f]{10}$")
        self.assertRegex(after, r"\?v=[0-9a-f]{10}$")
        self.assertNotEqual(before, after)

    def test_a_missing_file_keeps_its_plain_address(self) -> None:
        """A missing icon must not turn into a page that cannot be shown."""
        self.assertEqual(static("img/gibt-es-nicht.svg"), "/static/img/gibt-es-nicht.svg")
        self.assertEqual(fingerprint("/gibt/es/nicht"), "")

    def test_pages_ask_for_style_sheet_scripts_and_icons_by_fingerprint(self) -> None:
        self.client.force_login(make_user("admin", superuser=True))
        page = self.client.get(reverse("projects:list")).content.decode()
        for file in ("css/app.css", "js/app.js", "vendor/htmx.min.js", "img/icons.svg"):
            with self.subTest(file=file):
                self.assertRegex(page, re.escape(f"/static/{file}") + r"\?v=[0-9a-f]{10}")
        # An icon is a part of the icon file: the fingerprint comes before the name of the part.
        self.assertRegex(page, r'<use href="/static/img/icons\.svg\?v=[0-9a-f]{10}#\w+">')
