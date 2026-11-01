# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: Einstellungen → Gateway on a phone (GWL-011): pair an app, see the code, lock a device out.

Without horizontal scrolling and checked with axe-core (NFA-025).
"""

from __future__ import annotations

from unittest import SkipTest, mock

from rentalars.accounts.models import User
from rentalars.gateway_link import service
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.ui.test_1111_gateway_pages import connect_link, paired_device


class GatewayInTheBrowserTests(BrowserTestCase):
    """GWL-011: make a pairing code and lock a device out, on a phone."""

    bypass_csp = True

    def setUp(self) -> None:
        super().setUp()
        patcher = mock.patch.object(service.GatewayClient, "push_registry", return_value={})
        patcher.start()
        self.addCleanup(patcher.stop)
        connect_link()
        self.anna = User.objects.get(username="anna")
        paired_device(self.anna, "Pixel von Anna")

    def check_page(self, width: int) -> None:
        axe = _axe_path()
        if axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        self.assertLessEqual(self.page.evaluate("document.scrollingElement.scrollWidth"), width)
        self.page.add_script_tag(path=str(axe))
        findings = self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            WCAG_AA,
        )
        self.assertEqual(findings, [], "\n".join(findings))

    def test_pair_and_lock_out_on_a_phone(self) -> None:
        self.page.set_viewport_size({"width": 375, "height": 800})
        self.open("/administration/gateway/")
        self.page.get_by_role("heading", name="Gateway", exact=True).wait_for()
        self.check_page(375)
        self.page.select_option("select[name=user]", label="anna")
        self.page.fill("input[name=device_name]", "Pixel")
        with self.page.expect_navigation():
            self.page.get_by_role("button", name="Kopplungscode erzeugen").click()
        self.page.locator(".qr svg").wait_for()
        self.assertTrue(self.page.input_value("textarea[readonly]").startswith("RGW1:"))
        self.check_page(375)
        self.page.get_by_role("button", name="Sperren").click()
        with self.page.expect_navigation():
            self.confirm()
        self.assertIn("ist gesperrt", self.page.inner_text("main"))
        self.assertIn("1 gesperrtes Gerät", self.page.inner_text("main"))
