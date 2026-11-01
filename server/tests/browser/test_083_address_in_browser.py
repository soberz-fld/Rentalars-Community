# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser, area "address": Einstellungen → Serveradresse und Zertifikat (ADM-016).

On a phone without horizontal scrolling and checked with axe-core (NFA-025): an own certificate is uploaded,
the page shows the checks, the one command with its copy button and what the command does.
"""

from __future__ import annotations

from unittest import SkipTest

from tests.address_certificates import isolate_server_address, make_chain
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path


class ServerAddressInTheBrowserTests(BrowserTestCase):
    """ADM-016: prepare a change of the address on a phone and copy the command."""

    bypass_csp = True

    def setUp(self) -> None:
        super().setUp()
        isolate_server_address(self, addresses=["203.0.113.10"])

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

    def test_prepare_an_own_certificate_on_a_phone(self) -> None:
        chain = make_chain("neu.example.com")
        self.page.set_viewport_size({"width": 375, "height": 800})
        self.open("/administration/server-address/")
        self.page.get_by_role("heading", name="Serveradresse und Zertifikat").wait_for()
        self.check_page(375)
        self.page.fill("input[name=host]", "neu.example.com")
        self.page.check("input[name=certificate_kind][value=own]")
        self.page.set_input_files(
            "input[name=certificate]",
            {"name": "fullchain.pem", "mimeType": "application/x-pem-file", "buffer": chain.leaf_and_intermediate},
        )
        self.page.set_input_files(
            "input[name=private_key]",
            {"name": "privkey.pem", "mimeType": "application/x-pem-file", "buffer": chain.key},
        )
        with self.page.expect_navigation():
            self.page.get_by_role("button", name="Prüfen und vorbereiten").click()
        command = self.page.locator("#address-command")
        command.wait_for()
        self.assertRegex(command.inner_text(), r"^sudo rentalars address apply [0-9a-f]{16}$")
        self.assertIn("Gilt für neu.example.com bis", self.page.inner_text("main"))
        self.assertIn("Was der Befehl tut", self.page.inner_text("main"))
        self.page.get_by_role("button", name="Kopieren").click()
        status = self.page.locator("[data-copy-status]")
        self.page.wait_for_function("document.querySelector('[data-copy-status]').textContent.length > 0")
        self.assertIn(status.text_content(), ("Kopiert", "Kopieren hat nicht geklappt."))
        self.check_page(375)

    def test_the_page_on_a_wide_screen(self) -> None:
        self.open("/administration/server-address/")
        self.page.fill("input[name=host]", "neu.example.com")
        self.page.check("input[name=certificate_kind][value=selfsigned]")
        with self.page.expect_navigation():
            self.page.get_by_role("button", name="Prüfen und vorbereiten").click()
        self.page.locator("#address-command").wait_for()
        self.check_page(1360)
