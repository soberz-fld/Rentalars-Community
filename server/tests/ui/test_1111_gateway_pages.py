# SPDX-License-Identifier: GPL-3.0-or-later
"""Einstellungen → Gateway – pair an app, list the devices, lock one out, all in the browser (GWL-011)."""

from __future__ import annotations

from unittest import mock

from django.utils import timezone

from rentalars.accounts.models import Role
from rentalars.core.models import AuditLogEntry
from rentalars.gateway_link import protocol, service
from rentalars.gateway_link.models import GatewayDevice, GatewayLink, GatewayPairing
from tests.helpers import make_user
from tests.ui.base import UiTestCase

PAGE = "/administration/gateway/"


def connect_link() -> GatewayLink:
    """A connected link with real keys (the pairing offer needs the public key of the server)."""
    link = GatewayLink(
        gateway_url="https://gateway.example:8799",
        gateway_fingerprint="ab" * 32,
        enrolled_at=timezone.now(),
        last_poll_at=timezone.now(),
    )
    link.set_link_key_pem(protocol.private_to_pem(protocol.generate_private_key()))
    link.set_e2e_key_pem(protocol.private_to_pem(protocol.generate_private_key()))
    link.save()
    return link


def paired_device(user: object, name: str = "Telefon", number: int = 1) -> GatewayDevice:
    return GatewayDevice.objects.create(
        device_id=f"{number:032x}", public_key="04" + f"{number:0128x}", name=name, platform="android", user=user
    )


class GatewayPageTests(UiTestCase):
    """GWL-011: the page of the settings."""

    def setUp(self) -> None:
        super().setUp()
        patcher = mock.patch.object(service.GatewayClient, "push_registry", return_value={})
        self.pushed = patcher.start()
        self.addCleanup(patcher.stop)
        self.anna = make_user("anna")

    def test_the_link_in_the_settings(self) -> None:
        self.assertIn(PAGE, self.assert_ok(self.client.get("/administration/")))

    def test_without_a_gateway_the_command_is_shown(self) -> None:
        text = self.assert_ok(self.client.get(PAGE))
        self.assertIn("Es ist kein Gateway verbunden", text)
        self.assertIn("sudo rentalars gateway connect", text)
        self.assertNotIn("Kopplungscode erzeugen", text)

    def test_the_state_of_the_link(self) -> None:
        connect_link()
        text = self.assert_ok(self.client.get(PAGE))
        self.assertIn("https://gateway.example:8799", text)
        self.assertIn("verbunden", text)
        GatewayLink.objects.update(last_poll_at=timezone.now() - timezone.timedelta(minutes=5))
        text = self.assert_ok(self.client.get(PAGE))
        self.assertIn("nicht verbunden", text)
        self.assertIn("rentalars-gateway-link", text)

    def test_pair_an_app_shows_code_and_qr_once(self) -> None:
        connect_link()
        response = self.client.post(PAGE, {"user": self.anna.pk, "device_name": "Pixel", "minutes": "5"})
        text = self.assert_ok(response)
        self.assertIn("Kopplungscode für anna", text)
        self.assertIn("<svg", text)
        self.assertIn("RGW1:", text)
        self.assertIn("no-store", response.headers.get("Cache-Control", ""))
        offer = GatewayPairing.objects.get()
        self.assertEqual((offer.user, offer.created_by, offer.device_name), (self.anna, self.admin_user, "Pixel"))
        self.assertLessEqual(offer.expires_at - int(timezone.now().timestamp()), 300)
        self.pushed.assert_called()
        # The page does not show it again.
        self.assertNotIn("RGW1:", self.assert_ok(self.client.get(PAGE)))

    def test_pairing_is_written_to_the_change_log(self) -> None:
        connect_link()
        self.client.post(PAGE, {"user": self.anna.pk, "device_name": "Pixel", "minutes": "10"})
        entry = AuditLogEntry.objects.get(event="gateway.pairing_offered")
        self.assertEqual(entry.object_id, str(self.anna.pk))
        self.assertNotIn("RGW1", str(entry.changes))
        log = self.assert_ok(self.client.get("/administration/audit-log/"))
        self.assertIn("Kopplungscode für eine App erzeugt (Pixel, gültig 10 Minuten)", log)

    def test_an_inactive_account_gets_no_code(self) -> None:
        connect_link()
        self.anna.is_active = False
        self.anna.save()
        text = self.assert_ok(self.client.post(PAGE, {"user": self.anna.pk, "minutes": "10"}))
        self.assertIn("errorlist", text)
        self.assertNotIn("Kopplungscode für anna", text)
        self.assertFalse(GatewayPairing.objects.exists())

    def test_a_gateway_that_does_not_answer(self) -> None:
        connect_link()
        self.pushed.side_effect = OSError("connection refused")
        text = self.assert_ok(self.client.post(PAGE, {"user": self.anna.pk, "minutes": "10"}))
        self.assertIn("Der Code ließ sich nicht erzeugen", text)
        self.assertIn("connection refused", text)
        self.assertFalse(GatewayPairing.objects.exists())

    def test_without_a_gateway_nothing_is_made(self) -> None:
        response = self.client.post(PAGE, {"user": self.anna.pk, "minutes": "10"}, follow=True)
        self.assertIn("Es ist kein Gateway verbunden", self.assert_ok(response))
        self.assertFalse(GatewayPairing.objects.exists())

    def test_the_devices_are_listed(self) -> None:
        connect_link()
        paired_device(self.anna, "Pixel von Anna")
        GatewayDevice.objects.filter(name="Pixel von Anna").update(last_seen_at=timezone.now())
        text = self.assert_ok(self.client.get(PAGE))
        self.assertIn("Pixel von Anna", text)
        self.assertIn("anna", text)
        self.assertIn("Sperren", text)

    def test_lock_a_device_out(self) -> None:
        connect_link()
        device = paired_device(self.anna)
        response = self.client.post(f"{PAGE}devices/{device.device_id}/revoke/", follow=True)
        text = self.assert_ok(response)
        device.refresh_from_db()
        self.assertIsNotNone(device.revoked_at)
        self.assertEqual(device.revoked_by, self.admin_user)
        self.assertIn("ist gesperrt", text)
        self.assertIn("1 gesperrtes Gerät", text)
        self.pushed.assert_called()
        entry = AuditLogEntry.objects.get(event="gateway.device_revoked")
        self.assertEqual(entry.object_id, str(device.pk))
        self.assertIn(
            "App Telefon von anna für das Gateway gesperrt",
            self.assert_ok(self.client.get("/administration/audit-log/")),
        )

    def test_locking_out_twice_changes_nothing(self) -> None:
        connect_link()
        device = paired_device(self.anna)
        self.client.post(f"{PAGE}devices/{device.device_id}/revoke/")
        first = GatewayDevice.objects.get(pk=device.pk).revoked_at
        self.client.post(f"{PAGE}devices/{device.device_id}/revoke/")
        self.assertEqual(GatewayDevice.objects.get(pk=device.pk).revoked_at, first)
        self.assertEqual(AuditLogEntry.objects.filter(event="gateway.device_revoked").count(), 1)

    def test_a_device_is_locked_out_even_if_the_gateway_is_down(self) -> None:
        connect_link()
        device = paired_device(self.anna)
        self.pushed.side_effect = OSError("down")
        text = self.assert_ok(self.client.post(f"{PAGE}devices/{device.device_id}/revoke/", follow=True))
        self.assertIsNotNone(GatewayDevice.objects.get(pk=device.pk).revoked_at)
        self.assertIn("das Gateway ließ sich nicht benachrichtigen", text)

    def test_revoking_needs_a_post(self) -> None:
        connect_link()
        device = paired_device(self.anna)
        self.assertEqual(self.client.get(f"{PAGE}devices/{device.device_id}/revoke/").status_code, 405)

    def test_an_unknown_device(self) -> None:
        self.assertEqual(self.client.post(f"{PAGE}devices/{'f' * 32}/revoke/").status_code, 404)


class GatewayRightsTests(UiTestCase):
    """GWL-011: reading needs the settings, pairing and locking out need the delete right there."""

    def setUp(self) -> None:
        super().setUp()
        patcher = mock.patch.object(service.GatewayClient, "push_registry", return_value={})
        patcher.start()
        self.addCleanup(patcher.stop)
        connect_link()
        self.anna = make_user("anna")
        Role.objects.create(name="Einstellungen lesen", module_levels={"administration": 1})
        self.reader = self.browser_of(make_user("lea", roles=("Einstellungen lesen",)))

    def test_a_reader_sees_but_cannot_pair(self) -> None:
        text = self.assert_ok(self.reader.get(PAGE))
        self.assertNotIn("Kopplungscode erzeugen", text)
        response = self.reader.post(PAGE, {"user": self.anna.pk, "minutes": "10"}, follow=True)
        self.assertIn("nur Administratoren", self.assert_ok(response))
        self.assertFalse(GatewayPairing.objects.exists())

    def test_a_reader_cannot_lock_out(self) -> None:
        device = paired_device(self.anna)
        response = self.reader.post(f"{PAGE}devices/{device.device_id}/revoke/", follow=True)
        self.assertIn("nur Administratoren", self.assert_ok(response))
        self.assertIsNone(GatewayDevice.objects.get(pk=device.pk).revoked_at)

    def test_without_the_settings(self) -> None:
        browser = self.browser_of(make_user("ben"))
        self.assertEqual(browser.get(PAGE).status_code, 403)
        self.assertEqual(browser.post(PAGE, {"user": self.anna.pk, "minutes": "10"}).status_code, 403)
        self.assertFalse(GatewayPairing.objects.exists())
