# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests, area "address": server address and certificate (ADM-016, API-014)."""

from __future__ import annotations

from django.conf import settings

from rentalars.accounts.models import Role
from rentalars.core.address_models import AddressChange, AddressChangeStatus
from tests.address_certificates import isolate_server_address, make_chain
from tests.api.base import API, ApiTestCase


class ServerAddressApiTests(ApiTestCase):
    """ADM-016: read the address, prepare a change, read and discard it – applying it needs root on the server."""

    def setUp(self) -> None:
        super().setUp()
        isolate_server_address(self, addresses=["203.0.113.10"])

    def prepare(self, **values: object) -> object:
        body = {"host": "neu.example.com", "certificate_kind": "selfsigned"}
        body.update(values)
        return self.admin.post(f"{API}/server-address/changes", body, format="json")

    def test_the_state(self) -> None:
        """ADM-016: GET /server-address."""
        response = self.admin.get(f"{API}/server-address")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # The address of the configuration in use (the development and the MariaDB test files differ).
        self.assertEqual(data["url"], str(settings.RENTALARS_URL))
        self.assertFalse(data["nginx_site"])
        self.assertEqual(data["certificate_kind"], "proxy")
        self.assertIsNone(data["change"])

    def test_prepare_read_and_discard(self) -> None:
        """ADM-016: POST, GET and DELETE /server-address/changes."""
        response = self.prepare(redirect_old=False)
        self.assertEqual(response.status_code, 201, response.content)
        change = response.json()
        self.assertEqual(change["host"], "neu.example.com")
        self.assertEqual(change["status"], "prepared")
        self.assertFalse(change["redirect_old"])
        self.assertEqual(change["command"], f"sudo rentalars address apply {change['token']}")
        self.assertTrue(change["steps"])
        self.assertEqual(change["prepared_by"], "admin")
        self.assertEqual(self.admin.get(f"{API}/server-address").json()["change"]["token"], change["token"])
        detail = self.admin.get(f"{API}/server-address/changes/{change['token']}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["checks"][0]["title"], "DNS von neu.example.com")
        self.assertEqual(self.admin.delete(f"{API}/server-address/changes/{change['token']}").status_code, 204)
        self.assertEqual(AddressChange.objects.get().status, AddressChangeStatus.DISCARDED)
        again = self.admin.delete(f"{API}/server-address/changes/{change['token']}")
        self.assert_error(again, 400, "validation_error", "status")
        self.assertEqual(self.admin.get(f"{API}/server-address/changes/{change['token']}").json()["command"], "")

    def test_an_own_certificate(self) -> None:
        """ADM-016: certificate and key as PEM text; a key that does not fit is refused."""
        chain = make_chain("neu.example.com")
        response = self.prepare(
            certificate_kind="own", certificate=chain.leaf_and_intermediate.decode(), private_key=chain.key.decode()
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["certificate"]["names"], ["neu.example.com"])
        self.assertNotIn("PRIVATE KEY", response.content.decode())
        wrong = self.prepare(
            certificate_kind="own",
            certificate=chain.leaf_and_intermediate.decode(),
            private_key=chain.other_key.decode(),
        )
        self.assert_error(wrong, 400, "validation_error", "certificate")

    def test_wrong_input(self) -> None:
        """ADM-016: errors name their field."""
        self.assert_error(self.prepare(host="10.1.2.3"), 400, "validation_error", "host")
        self.assert_error(self.prepare(certificate_kind="letsencrypt"), 400, "validation_error", "email")
        self.assert_error(self.prepare(certificate_kind="magic"), 400, "validation_error", "certificate_kind")
        self.assertFalse(AddressChange.objects.exists())

    def test_rights(self) -> None:
        """ADM-016: reading needs the settings, preparing their delete right."""
        Role.objects.create(name="Einstellungen schreiben", module_levels={"administration": 2})
        writer = self.client_for("wanda", "Einstellungen schreiben")
        self.assertEqual(writer.get(f"{API}/server-address").status_code, 200)
        refused = writer.post(
            f"{API}/server-address/changes",
            {"host": "neu.example.com", "certificate_kind": "selfsigned"},
            format="json",
        )
        self.assert_error(refused, 403, "permission_denied")
        crew = self.client_for("carla", "Crew")
        self.assert_error(crew.get(f"{API}/server-address"), 403, "permission_denied")
        self.assertFalse(AddressChange.objects.exists())
