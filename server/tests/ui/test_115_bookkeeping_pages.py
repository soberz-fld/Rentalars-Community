# SPDX-License-Identifier: GPL-3.0-or-later
"""In the pages: without "Rentalars als Buchhaltungsprogramm verwenden" the bookkeeping is gone (DOK-055)."""

from __future__ import annotations

from django.urls import reverse

from rentalars.core.models import SystemSettings
from tests.ui.base import UiTestCase

#: The tabs that are bookkeeping, by the address they lead to.
BOOKKEEPING_LINKS = (
    "/accounting/incoming/",
    "/accounting/incoming/capture/",
    "/accounting/assets/",
    "/accounting/assets/sales/",
    "/accounting/open-items/",
    "/accounting/bank/",
    "/accounting/euer/",
    "/accounting/archive/",
    "/accounting/legacy/",
)
STAYING_LINKS = ("/accounting/documents/", "/accounting/monthly/")


def switch(on: bool) -> None:
    settings = SystemSettings.load()
    settings.invoices_enabled = on
    settings.save()


class TabsTests(UiTestCase):
    def test_on_all_tabs_are_there(self) -> None:
        page = self.assert_ok(self.client.get(reverse("documents:outgoing")))
        for link in BOOKKEEPING_LINKS + STAYING_LINKS:
            self.assertIn(f'href="{link}"', page, link)

    def test_off_only_the_documents_and_the_statements_stay(self) -> None:
        switch(False)
        page = self.assert_ok(self.client.get(reverse("documents:outgoing")))
        for link in BOOKKEEPING_LINKS:
            self.assertNotIn(f'href="{link}"', page, link)
        for link in STAYING_LINKS:
            self.assertIn(f'href="{link}"', page, link)

    def test_off_the_other_places_that_lead_there_are_gone(self) -> None:
        administration = self.assert_ok(self.client.get(reverse("core:administration")))
        self.assertIn(reverse("incoming:settings"), administration)
        switch(False)
        administration = self.assert_ok(self.client.get(reverse("core:administration")))
        self.assertNotIn(reverse("incoming:settings"), administration)
        self.assertIn(reverse("documents:accounting"), administration)  # Lexware Office and DATEV: their own page


class DirectAddressTests(UiTestCase):
    def test_off_every_page_of_bookkeeping_leads_back_with_a_hint(self) -> None:
        switch(False)
        for link in (*BOOKKEEPING_LINKS, reverse("incoming:settings")):
            response = self.client.get(link, follow=True)
            self.assertEqual(response.redirect_chain[-1][0], "/", link)
            self.assertTrue(
                any("In Rentalars wird keine Buchhaltung geführt" in text for text in self.messages_of(response)), link
            )

    def test_a_page_that_updates_itself_is_left_by_htmx(self) -> None:
        switch(False)
        response = self.client.get(reverse("incoming:list"), headers={"HX-Request": "true"})
        self.assertEqual((response.status_code, response["HX-Redirect"]), (200, "/"))

    def test_off_a_change_is_refused_too(self) -> None:
        switch(False)
        response = self.client.post(reverse("documents:bank_upload"), {}, follow=True)
        self.assertEqual(response.redirect_chain[-1][0], "/")

    def test_on_again_everything_is_there_as_before(self) -> None:
        switch(False)
        switch(True)
        for link in BOOKKEEPING_LINKS:
            self.assertEqual(self.client.get(link).status_code, 200, link)

    def test_the_staying_pages_work_while_off(self) -> None:
        switch(False)
        for link in (*STAYING_LINKS, reverse("documents:accounting")):
            self.assertEqual(self.client.get(link).status_code, 200, link)

    def test_not_logged_in_the_login_page_answers(self) -> None:
        switch(False)
        self.client.logout()
        response = self.client.get("/accounting/incoming/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])


class SettingsPageTests(UiTestCase):
    def test_the_switch_has_its_own_box(self) -> None:
        page = self.assert_ok(self.client.get(reverse("core:company_settings")))
        box = page[page.index('id="accounting"') :]
        box = box[: box.index("</section>")]
        self.assertIn("Buchhaltung und Rechnungswesen", box)
        self.assertIn("Rentalars als Buchhaltungsprogramm verwenden", box)
        self.assertIn('name="accounting-invoices_enabled"', box)
        # ... and no longer among the other settings.
        rest = page.replace(box, "")
        self.assertNotIn("invoices_enabled", rest)

    def test_saving_the_box_changes_only_the_switch(self) -> None:
        before = SystemSettings.load().buffer_before_hours
        response = self.client.post(reverse("core:company_settings"), {"form": "accounting"}, follow=True)
        self.assertIn("Einstellungen gespeichert.", self.messages_of(response))
        settings = SystemSettings.load()
        self.assertFalse(settings.invoices_enabled)
        self.assertEqual(settings.buffer_before_hours, before)
        self.client.post(reverse("core:company_settings"), {"form": "accounting", "accounting-invoices_enabled": "on"})
        self.assertTrue(SystemSettings.load().invoices_enabled)

    def test_the_other_settings_form_keeps_the_switch(self) -> None:
        """Saving the other settings must not switch bookkeeping off because its field is no longer in that form."""
        switch(True)
        page = self.client.get(reverse("core:company_settings"))
        from tests.ui.base import form_data

        data = form_data(page, "system-crew_answers")
        self.assertNotIn("system-invoices_enabled", data)
        self.client.post(reverse("core:company_settings"), data)
        self.assertTrue(SystemSettings.load().invoices_enabled)
