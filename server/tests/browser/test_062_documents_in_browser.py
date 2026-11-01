# SPDX-License-Identifier: GPL-3.0-or-later
"""Wishes in a real browser: the validity of an offer as date and days (DOK-013), the deployment view on
paper (PRJ-081)."""

from __future__ import annotations

from tests.browser.base import BrowserTestCase


class OfferValidityInBrowserTests(BrowserTestCase):
    """DOK-013: changing the date changes the days, and the other way round – at once, without a request."""

    def test_date_and_days_follow_each_other(self) -> None:
        self.open(f"/projects/{self.project.pk}/documents/")
        self.page.select_option("#id_kind", "delivery_note")
        self.assertFalse(self.page.is_visible("#id_validity_days"))
        self.page.select_option("#id_kind", "offer")
        self.assertTrue(self.page.is_visible("#id_validity_days"))
        self.assertTrue(self.page.is_visible("#id_detail_1"))
        self.assertEqual(self.page.input_value("#id_validity_days"), "14")
        self.assertEqual(self.page.input_value("#id_valid_until"), "2027-03-15")

        self.page.fill("#id_validity_days", "30")
        self.assertEqual(self.page.input_value("#id_valid_until"), "2027-03-31")
        self.page.fill("#id_valid_until", "2027-04-10")
        self.assertEqual(self.page.input_value("#id_validity_days"), "40")
        self.page.fill("#id_validity_days", "0")
        self.assertEqual(self.page.input_value("#id_valid_until"), "2027-03-01")


class DeploymentOnPaperInBrowserTests(BrowserTestCase):
    """PRJ-081: printed, the deployment view shows what and who – no tabs, no buttons, no forms."""

    def test_print_style_of_the_deployment_view(self) -> None:
        self.open(f"/projects/{self.project.pk}/deployment/")
        button = self.page.locator(".deployment-tools a.btn")
        self.assertEqual(button.inner_text().strip(), "Drucken / PDF")
        self.assertTrue(button.get_attribute("href").endswith("/deployment/pdf/"))
        self.page.emulate_media(media="print")
        self.assertFalse(self.page.is_visible("nav.tabs"))
        self.assertFalse(self.page.is_visible(".deployment-tools"))
        self.assertTrue(self.page.is_visible(".deployment-view .panel"))
        self.page.emulate_media(media="screen")
        self.assertTrue(self.page.is_visible("nav.tabs"))
