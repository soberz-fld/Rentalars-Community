# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages, area "security": internal addresses in the forms (NFA-071) and the self-check (NFA-071,
NFA-073)."""

from __future__ import annotations

from django.test import override_settings
from django.urls import reverse

from rentalars.api.models import Webhook
from rentalars.personnel.models import Person
from tests.helpers import make_user
from tests.ui.base import UiTestCase, form_data

NOTHING_ALLOWED = override_settings(RENTALARS_NETWORK_ALLOW_INTERNAL=())


@NOTHING_ALLOWED
class InternalAddressFormTests(UiTestCase):
    """NFA-071: an internal address is refused at the field, with a text that says who can allow it."""

    def test_the_webhook_form(self) -> None:
        page = self.client.get(reverse("webhooks:create"))
        self.assertIn("Interne Adressen nur, wenn der Betreiber sie in der Konfigurationsdatei freigibt.", page.text)
        data = form_data(page, "url", url="http://192.168.1.20/rentalars", events=["project.created"])
        text = self.assert_ok(self.client.post(reverse("webhooks:create"), data))
        self.assertIn("Die Adresse führt in ein internes Netz.", text)
        self.assertIn("allow_internal", text)
        self.assertFalse(Webhook.objects.exists())

    def test_the_own_calendars(self) -> None:
        user = make_user("carla", roles=("Crew",))
        browser = self.browser_of(user)
        response = browser.post(
            reverse("personnel:own_feed"), {"url": "http://127.0.0.1:5232/carla.ics", "label": "Band"}, follow=True
        )
        self.assertIn("Die Adresse führt in ein internes Netz.", self.assert_ok(response))
        self.assertFalse(Person.objects.get(user=user).calendar_feeds.exists())


class SelfCheckPageTests(UiTestCase):
    """NFA-071, NFA-073: the self-check names settings that lead inside and the state of HTTPS."""

    @NOTHING_ALLOWED
    def test_settings_inside_are_named(self) -> None:
        user = make_user("carla", roles=("Crew",))
        Person.objects.filter(user=user).update(caldav_url="http://192.168.1.5/dav/")
        text = self.assert_ok(self.client.get("/administration/self-check/"))
        self.assertIn("Verbindungen zu anderen Servern", text)
        self.assertIn("192.168.1.5 – privates Netz", text)
        self.assertIn("keine ([network] allow_internal)", text)

    def test_http_allowed_on_purpose_is_a_warning(self) -> None:
        with override_settings(
            RENTALARS_IS_PRODUCTION=True, RENTALARS_URL="http://rentalars.lan", RENTALARS_ALLOW_HTTP=True
        ):
            text = self.assert_ok(self.client.get("/administration/self-check/"))
        self.assertIn("bewusst abgeschaltet (allow_http = yes)", text)
