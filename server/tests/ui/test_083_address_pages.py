# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages, area "address": Einstellungen → Serveradresse und Zertifikat (ADM-016)."""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from rentalars.accounts.models import Role
from rentalars.core import server_address
from rentalars.core.address_models import AddressChange, AddressChangeStatus
from tests.address_certificates import isolate_server_address, make_chain
from tests.helpers import make_user
from tests.ui.base import UiTestCase

PAGE = "/administration/server-address/"


class ServerAddressPageTests(UiTestCase):
    """ADM-016: the page shows the address, prepares a change and shows the one command."""

    def setUp(self) -> None:
        super().setUp()
        isolate_server_address(self, addresses=["203.0.113.10"])

    def test_the_link_and_the_current_address(self) -> None:
        self.assertIn(PAGE, self.assert_ok(self.client.get(reverse("core:administration"))))
        text = self.assert_ok(self.client.get(PAGE))
        self.assertIn("Serveradresse und Zertifikat", text)
        self.assertIn("Aktuelle Adresse", text)
        self.assertIn("keine NGINX-Konfiguration der Installation", text)
        self.assertIn("Änderung vorbereiten", text)
        self.assertNotIn("sudo rentalars address apply", text)

    def test_prepare_a_self_signed_certificate(self) -> None:
        response = self.client.post(
            PAGE, {"host": "neu.example.com", "certificate_kind": "selfsigned", "redirect_old": "on"}, follow=True
        )
        text = self.assert_ok(response)
        change = AddressChange.objects.get()
        self.assertIn("Die Änderung ist vorbereitet.", text)
        self.assertIn(f"sudo rentalars address apply {change.token}", text)
        self.assertIn(f"sudo rentalars address apply {change.token} --dry-run", text)
        self.assertIn("Erstellt ein selbst signiertes Zertifikat für neu.example.com", text)
        self.assertIn("DNS von neu.example.com", text)
        self.assertIn("wird auf die neue weitergeleitet", text)
        self.assertIn("Diese Änderung verwerfen", text)

    def test_prepare_an_own_certificate(self) -> None:
        chain = make_chain("neu.example.com")
        response = self.client.post(
            PAGE,
            {
                "host": "neu.example.com",
                "certificate_kind": "own",
                "certificate": SimpleUploadedFile("fullchain.pem", chain.leaf_and_intermediate),
                "private_key": SimpleUploadedFile("privkey.pem", chain.key),
            },
            follow=True,
        )
        text = self.assert_ok(response)
        change = AddressChange.objects.get()
        self.assertIn("Gilt für neu.example.com bis", text)
        self.assertIn("ausgestellt von Test Intermediate CA", text)
        self.assertTrue(server_address.files_dir(change).exists())
        self.assertNotIn("PRIVATE KEY", text)

    def test_a_key_that_does_not_fit_is_refused_at_the_field(self) -> None:
        chain = make_chain("neu.example.com")
        response = self.client.post(
            PAGE,
            {
                "host": "neu.example.com",
                "certificate_kind": "own",
                "certificate": SimpleUploadedFile("fullchain.pem", chain.leaf_and_intermediate),
                "private_key": SimpleUploadedFile("privkey.pem", chain.other_key),
            },
        )
        self.assertIn("Der Schlüssel gehört zu keinem Zertifikat der Datei.", self.assert_ok(response))
        self.assertFalse(AddressChange.objects.exists())

    def test_wrong_input(self) -> None:
        text = self.assert_ok(self.client.post(PAGE, {"host": "neu.example.com", "certificate_kind": "letsencrypt"}))
        self.assertIn("braucht eine E-Mail-Adresse für Hinweise zum Ablauf", text)
        text = self.assert_ok(self.client.post(PAGE, {"host": "10.0.0.5", "certificate_kind": "selfsigned"}))
        self.assertIn("Gib einen Namen ein, keine IP-Adresse.", text)
        self.assertFalse(AddressChange.objects.exists())

    def test_discard(self) -> None:
        change = server_address.prepare(self.admin_user, host="neu.example.com", kind="selfsigned")
        response = self.client.post(reverse("core:server_address_discard", args=[change.token]), follow=True)
        text = self.assert_ok(response)
        self.assertIn("Die vorbereitete Änderung wurde verworfen", text)
        self.assertNotIn(change.command, text)
        change.refresh_from_db()
        self.assertEqual(change.status, AddressChangeStatus.DISCARDED)

    def test_the_result_of_the_command(self) -> None:
        change = server_address.prepare(self.admin_user, host="neu.example.com", kind="selfsigned")
        server_address.record(change.token, applied=False, by="kai", message="NGINX nimmt die Konfiguration nicht an.")
        text = self.assert_ok(self.client.get(PAGE))
        self.assertIn("ausgeführt von kai", text)
        self.assertIn("NGINX nimmt die Konfiguration nicht an.", text)
        self.assertIn(change.command, text)  # a failed change can be run again
        server_address.record(change.token, applied=True, by="kai")
        text = self.assert_ok(self.client.get(PAGE))
        moment = timezone.localtime(AddressChange.objects.get().applied_at).strftime("%d.%m.%Y %H:%M")
        self.assertIn(f"Angewendet am {moment} von kai.", text)
        self.assertNotIn(change.command, text)

    def test_earlier_changes_are_listed(self) -> None:
        server_address.prepare(self.admin_user, host="eins.example.com", kind="selfsigned")
        server_address.prepare(self.admin_user, host="zwei.example.com", kind="selfsigned")
        text = self.assert_ok(self.client.get(PAGE))
        self.assertIn("Frühere Änderungen", text)
        self.assertIn("durch eine neuere ersetzt", text)


class ServerAddressRightsTests(UiTestCase):
    """ADM-016: reading needs the settings; preparing needs the delete right there."""

    def setUp(self) -> None:
        super().setUp()
        isolate_server_address(self)

    def test_reading_without_preparing(self) -> None:
        Role.objects.create(name="Einstellungen lesen", module_levels={"administration": 1})
        browser = self.browser_of(make_user("lea", roles=("Einstellungen lesen",)))
        text = self.assert_ok(browser.get(PAGE))
        self.assertNotIn("Änderung vorbereiten", text)
        response = browser.post(PAGE, {"host": "neu.example.com", "certificate_kind": "selfsigned"}, follow=True)
        self.assertIn("Eine Änderung bereiten nur Administratoren vor", self.assert_ok(response))
        self.assertFalse(AddressChange.objects.exists())

    def test_without_the_settings(self) -> None:
        browser = self.browser_of(make_user("carla", roles=("Crew",)))
        self.assertEqual(browser.get(PAGE).status_code, 403)
