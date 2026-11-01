# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser, area "security": NFA-071, NFA-073.

On a phone without horizontal scrolling and checked with axe-core (NFA-025):

* the webhook form with the refusal of an internal address at the field (NFA-071),
* the self-check with the group "Verbindungen zu anderen Servern" that names a setting leading inside
  (NFA-071) and the state of HTTPS (NFA-073).
"""

from __future__ import annotations

from unittest import SkipTest

from django.test import override_settings

from rentalars.personnel.models import Person
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.helpers import make_user


@override_settings(RENTALARS_NETWORK_ALLOW_INTERNAL=())
class SecurityOnAPhoneTests(BrowserTestCase):
    """NFA-071, NFA-073: the pages on a phone, with axe-core."""

    bypass_csp = True

    def check(self, path: str, *, then: object = None) -> None:
        axe = _axe_path()
        if axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        self.page.set_viewport_size({"width": 375, "height": 800})
        self.open(path)
        self.page.wait_for_load_state("networkidle")
        if callable(then):
            then()
        width = self.page.evaluate("document.scrollingElement.scrollWidth")
        self.assertLessEqual(width, 375, path)
        self.page.add_script_tag(path=str(axe))
        findings = self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            WCAG_AA,
        )
        self.assertEqual(findings, [], "\n".join(findings))

    def test_the_webhook_form_refuses_an_internal_address(self) -> None:
        def send_an_internal_address() -> None:
            self.page.fill("input[name=url]", "http://192.168.1.20/rentalars")
            self.page.locator("input[name=events]").first.check()
            with self.page.expect_navigation():
                self.page.locator("form button[type=submit]").last.click()
            self.page.get_by_text("Die Adresse führt in ein internes Netz.").first.wait_for()

        self.check("/administration/webhooks/new/", then=send_an_internal_address)

    def test_the_self_check_names_settings_inside(self) -> None:
        user = make_user("carla", roles=("Crew",))
        Person.objects.filter(user=user).update(caldav_url="http://192.168.1.5/dav/")

        def look() -> None:
            self.page.get_by_text("Verbindungen zu anderen Servern").first.wait_for()
            self.assertIn("192.168.1.5 – privates Netz", self.page.content())

        self.check("/administration/self-check/", then=look)
