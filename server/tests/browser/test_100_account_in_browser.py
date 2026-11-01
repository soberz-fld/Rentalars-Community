# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "account", in a real browser: the table of API tokens stays inside its box (UIX). (UIX-057)

The requirement: the API token table under 'Mein Konto' does not exceed its box – a long name without spaces and the long
new key pushed the table out of the panel, and the page sideways, on a desk and on a phone.
"""

from __future__ import annotations

from rentalars.accounts.models import ApiToken, User
from tests.browser.test_081_ui_in_browser import UiInBrowserCase

LOOK = """() => {
  const panel = document.querySelector('#tokens').getBoundingClientRect();
  const table = document.querySelector('#tokens table').getBoundingClientRect();
  const key = document.querySelector('#tokens code.copy');
  const keyBox = key ? key.getBoundingClientRect() : null;
  return {
    panelRight: panel.right, tableRight: table.right, tableLeft: table.left, panelLeft: panel.left,
    panelOverflow: document.querySelector('#tokens').scrollWidth - document.querySelector('#tokens').clientWidth,
    keyRight: keyBox ? keyBox.right : null, page: document.scrollingElement.scrollWidth, viewport: innerWidth,
  };
}"""


class TokenTableTests(UiInBrowserCase):
    """The panel of the tokens, wide and narrow, with names that do not break by themselves."""

    def setUp(self) -> None:
        super().setUp()
        user = User.objects.get(username="anna")
        ApiToken.create_for_user(user, "W" * 80)
        ApiToken.create_for_user(user, "Buchhaltungsexport für die Steuerberatung Müller und Partner")
        ApiToken.create_for_user(user, "kurz", read_only=True)

    def assert_inside(self, look: dict) -> None:
        self.assertLessEqual(look["tableRight"], look["panelRight"] + 1)
        self.assertGreaterEqual(look["tableLeft"], look["panelLeft"] - 1)
        self.assertLessEqual(look["panelOverflow"], 1)
        self.assertLessEqual(look["page"], look["viewport"])  # no sideways scrolling of the page

    def test_the_table_stays_in_its_box_at_every_width(self) -> None:
        for width in (1360, 1000, 800, 360):
            with self.subTest(width=width):
                self.page.set_viewport_size({"width": width, "height": 800})
                self.open("/account/")
                self.assert_inside(self.page.evaluate(LOOK))

    def test_the_new_key_stays_in_its_box_on_a_phone(self) -> None:
        self.page.set_viewport_size({"width": 360, "height": 800})
        self.open("/account/")
        self.page.fill("#id_name", "Neuer")
        self.page.locator("#tokens button[type=submit]").click()
        self.page.wait_for_load_state()
        look = self.page.evaluate(LOOK)
        self.assertIsNotNone(look["keyRight"])
        self.assertLessEqual(look["keyRight"], look["panelRight"])
        self.assert_inside(look)
        self.axe()
