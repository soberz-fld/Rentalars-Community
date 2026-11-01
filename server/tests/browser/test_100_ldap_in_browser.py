# SPDX-License-Identifier: GPL-3.0-or-later
"""The directory login (LDAP) in a real browser (AUT-029): settings page, tests, assignments, a phone.

The administrator opens "Einstellungen → Verzeichnis (LDAP)", tries the connection and a login of a user (a dry
run: nothing is written), compares the accounts and adds a group assignment. Every page of the way is checked with
axe-core (WCAG 2.1 A/AA, see ``tests.browser.test_accessibility_in_browser``) and the page fits a phone. The
directory is the fake one (``ldap3`` mock strategy, ``tests/ldap_fake.py``); the browser part is real.
"""

from __future__ import annotations

from typing import Any
from unittest import SkipTest

from rentalars.accounts.models import LdapGroupMapping, Role, User
from tests.browser import test_accessibility_in_browser as accessibility
from tests.browser.base import BrowserTestCase
from tests.ldap_fake import standard_directory
from tests.unit.test_100_ldap import assign, configure


class LdapBase(BrowserTestCase):
    """The fake directory, switched on, with two assignments; axe for the pages."""

    bypass_csp = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = accessibility._axe_path()
        super().setUpClass()

    def setUp(self) -> None:
        super().setUp()
        self.directory = standard_directory()
        self.enterContext(self.directory.active())
        configure()
        assign("rentalars-planners", "Projektleitung")
        assign("rentalars-crew", "Crew")

    def findings(self) -> list[str]:
        """The findings of axe on the page as it is now."""
        if self.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        self.page.wait_for_load_state("networkidle")
        self.page.add_script_tag(path=str(self.axe))
        return self.page.evaluate(  # type: ignore[no-any-return]
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            accessibility.WCAG_AA,
        )


class LdapSettingsInBrowserTests(LdapBase):
    """The way an administrator does it."""

    def test_settings_tests_comparison_and_a_new_assignment(self) -> None:
        findings: dict[str, list[str]] = {}
        self.open("/administration/ldap/")
        self.page.wait_for_selector("h1:has-text('Verzeichnis (LDAP)')")
        self.assertEqual(self.page.input_value("textarea[name='server_uris']"), "ldaps://fake-directory")
        self.assertEqual(self.page.input_value("input[name='bind_password']"), "")  # never filled in
        findings["settings"] = self.findings()

        # Test connection
        self.page.click("button:has-text('Verbindung testen')")
        self.page.wait_for_selector("text=Ergebnis des Verbindungstests")
        self.assertIn("alles in Ordnung", self.page.inner_text("body"))
        findings["connection test"] = self.findings()

        # Test login for a user: nothing is written.
        self.page.fill("input[name='try-username']", "bernd")
        self.page.click("button:has-text('Anmeldung testen')")
        self.page.wait_for_selector("text=Ergebnis für „bernd“")
        body = self.page.inner_text("body")
        self.assertIn("Crew, Projektleitung", body)
        self.assertIn("ein neues Konto anlegen", body)
        self.assertFalse(User.objects.filter(username="bernd").exists())
        findings["login test"] = self.findings()

        # Compare the accounts (nobody has logged in yet: no differences).
        self.page.click("button:has-text('Unterschiede anzeigen')")
        self.page.wait_for_selector("text=Keine Unterschiede")
        findings["comparison"] = self.findings()

        # A new assignment.
        self.page.click("a:has-text('Neue Zuordnung')")
        self.page.wait_for_selector("h1:has-text('Neue Zuordnung')")
        self.page.fill("input[name='group']", "rentalars-warehouse")
        self.page.get_by_label("Lager", exact=True).check()
        findings["assignment form"] = self.findings()
        self.page.click("button:has-text('Zuordnung speichern')")
        self.page.wait_for_selector("text=Die Zuordnung wurde gespeichert.")
        mapping = LdapGroupMapping.objects.get(group="rentalars-warehouse")
        self.assertEqual(list(mapping.roles.values_list("name", flat=True)), ["Lager"])
        findings["settings with three assignments"] = self.findings()
        found = [f"{page}: {finding}" for page, items in findings.items() for finding in items]
        self.assertEqual(found, [], "\n".join(found))

    def test_a_wrong_input_is_explained_and_the_password_stays_empty(self) -> None:
        self.open("/administration/ldap/")
        self.page.fill("textarea[name='server_uris']", "dc1.example.com")
        self.page.fill("input[name='bind_password']", "geheim-123")
        self.page.click("button:has-text('Einstellungen speichern')")
        self.page.wait_for_selector("text=ldaps://")
        self.assertEqual(self.page.input_value("input[name='bind_password']"), "")
        self.assertNotIn("geheim-123", self.page.content())
        found = self.findings()
        self.assertEqual(found, [], "\n".join(found))

    def test_the_password_of_a_directory_account_cannot_be_changed_here(self) -> None:
        from tests.unit.test_100_ldap import login

        carla = login("carla", "carla-pw")
        assert carla is not None
        # The administrator looks at the account: roles from the directory are listed, not ticked.
        self.open(f"/administration/users/{carla.pk}/")
        self.page.wait_for_selector("text=aus dem Verzeichnis")
        self.assertIn(Role.objects.get(name="Crew").name, self.page.inner_text("body"))
        found = self.findings()
        self.assertEqual(found, [], "\n".join(found))


class LdapOnAPhoneTests(LdapBase):
    """The page, with the test results, fits the width of a phone."""

    viewport: Any = {"width": 360, "height": 740}

    def test_the_settings_page_fits_the_width(self) -> None:
        self.open("/administration/ldap/")
        self.page.fill("input[name='try-username']", "bernd")
        self.page.click("button:has-text('Anmeldung testen')")
        self.page.wait_for_selector("text=Ergebnis für „bernd“")
        self.settle()  # Measured while the result was swapped in, the width was 369 or 702 on one run in three
        self.assertLessEqual(self.page.evaluate("document.scrollingElement.scrollWidth"), 360)
        self.page.click("button:has-text('Verbindung testen')")
        self.page.wait_for_selector("text=Ergebnis des Verbindungstests")
        self.settle()
        self.assertLessEqual(self.page.evaluate("document.scrollingElement.scrollWidth"), 360)
