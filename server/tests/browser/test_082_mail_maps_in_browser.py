# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "mail-maps", in the browser: "übernehmen ab" and "nur ungelesene Mails" appear with the switch
"Mails ohne Projektkennung übernehmen" (EML-049); the map pictures are requested with the origin of the installation
as referrer (UIX-034); route links name no start (UIX-033) – and axe-core on all of it, wide and on a phone.

The map pictures come from this test server under another host name (``127.0.0.1`` instead of ``localhost``), so
that the request is cross-origin like one to the tile server of OpenStreetMap.
"""

from __future__ import annotations

from typing import Any
from unittest import SkipTest
from urllib.parse import urlsplit

from django.test import override_settings

from rentalars.config import MapsConfig
from rentalars.customers.models import Venue
from rentalars.mail.models import Mailbox
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.geocoder_fake import FakeGeocoder
from tests.mailbox import configure_mailbox

HALL = "Hallenweg 3, 12345 Musterstadt"


class MailMapsInBrowserTests(BrowserTestCase):
    """EML-049, UIX-033, UIX-034 where only a browser shows them; no finding of axe-core."""

    bypass_csp = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = _axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()

    def setUp(self) -> None:
        #: The tile requests with their Referer, as the browser sent them.
        self.tile_requests: list[tuple[str, str]] = []
        super().setUp()
        parts = urlsplit(self.live_server_url)
        self.tile_base = f"{parts.scheme}://127.0.0.1:{parts.port}"
        tiles = f"{self.tile_base}/static/img/favicon-32.png?{{z}}/{{x}}/{{y}}"
        self.enterContext(
            override_settings(RENTALARS_MAPS=MapsConfig(tile_url=tiles, geocoder_url="https://geo.example/search"))
        )
        self.enterContext(FakeGeocoder({HALL: ("52.0", "11.0")}))
        self.hall = Venue.objects.create(
            name="Stadthalle", street="Hallenweg 3", postal_code="12345", city="Musterstadt"
        )
        self.box = configure_mailbox(process_untagged=False)

    def _note_request(self, request: Any) -> None:
        """The tiles come from this server under its other name; everything else as in the base class."""
        if request.url.startswith(getattr(self, "tile_base", "\0")):
            self.tile_requests.append((request.url, request.all_headers().get("referer", "")))
            return
        super()._note_request(request)

    def axe_findings(self, within: str = "") -> list[str]:
        """What axe-core finds on the page, or only within the elements a selector names."""
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_function("() => document.getAnimations().every(a => a.playState !== 'running')")
        if not self.page.evaluate("() => typeof axe !== 'undefined'"):
            self.page.add_script_tag(path=str(self.axe))
        return self.page.evaluate(
            "async ([tags, within]) => (await axe.run(within ? {include: [[within]]} : document,"
            " {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            [WCAG_AA, within],
        )

    def both_themes(self, within: str = "") -> list[str]:
        """axe-core in the dark theme and – after switching, on the page's own content – in the light one."""
        findings = self.axe_findings(within)
        self.page.evaluate("() => document.documentElement.setAttribute('data-theme', 'light')")
        findings += [f"light: {finding}" for finding in self.axe_findings(within or "main")]
        self.page.evaluate("() => document.documentElement.setAttribute('data-theme', 'dark')")
        return findings

    def test_the_point_in_time_comes_with_the_switch(self) -> None:
        """EML-049: "übernehmen ab" and "nur ungelesene Mails" show only while the switch is on; saved, it is set."""
        self.open(f"/administration/mail/mailboxes/{self.box.pk}/")
        since = self.page.locator("#id_untagged_since")
        self.assertFalse(since.is_visible())
        self.page.locator("#id_process_untagged").check()
        self.assertTrue(since.is_visible())
        self.assertTrue(self.page.locator("#id_untagged_unread_only").is_visible())
        self.assertEqual(self.both_themes(), [])
        self.page.locator("#id_untagged_unread_only").check()
        self.page.locator("form.form button[type=submit]").click()
        self.page.wait_for_url("**/administration/mail/")
        box = Mailbox.objects.get(pk=self.box.pk)
        self.assertIsNotNone(box.untagged_since)
        self.assertTrue(box.untagged_unread_only)
        self.assertIn("nur ungelesene", self.page.inner_text("table.mailbox-list"))
        self.assertEqual(self.both_themes(), [])

    def test_tiles_carry_the_origin(self) -> None:
        """UIX-034: the tiles are asked for with the origin of the installation – never the path of the page."""
        self.open(f"/customers/venues/{self.hall.pk}/")
        self.settle()
        self.assertEqual(self.tile_requests, [])  # nothing before the click (NFA-050)
        self.page.get_by_role("button", name="Karte anzeigen").click()
        self.page.locator(".map-canvas.leaflet-container .map-pin").first.wait_for()
        self.page.locator(".leaflet-tile-loaded").first.wait_for()
        self.settle()
        self.assertTrue(self.tile_requests)
        self.assertEqual({referer for _url, referer in self.tile_requests}, {f"{self.live_server_url}/"})
        links = self.page.eval_on_selector_all("a.route-link", "links => links.map(a => a.href)")
        self.assertTrue(links)
        self.assertFalse([link for link in links if "origin=" in link])
        self.assertEqual(self.both_themes(".map-box"), [])


class MailMapsOnAPhoneTests(MailMapsInBrowserTests):
    """The same on a phone."""

    viewport = {"width": 360, "height": 740}
