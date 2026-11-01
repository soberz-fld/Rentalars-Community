# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests of the settings wishes: ADM-008, ADM-009, ADM-010, AUT-028.

Everything the pages offer goes through the API as well: the resources of
the server in the self-check, the state of the encryption, a backup for
download, the access log – and reads through the API are logged too.
"""

from __future__ import annotations

import io
import tarfile

from rentalars.accounts.models import Role
from rentalars.core.models import AccessLogEntry, BackgroundJob, JobStatus, SystemSettings
from tests.api.base import API, ApiTestCase
from tests.helpers import assert_dumped, dumped_rows_visible, make_customer, make_project, make_user
from tests.unit.test_051_settings import BackupFolderMixin


class SelfCheckApiTests(ApiTestCase):
    def test_resources_as_numbers(self) -> None:
        """ADM-008: what the server has and uses, in bytes and seconds."""
        response = self.admin.get(f"{API}/self-check")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        resources = body["resources"]
        for key in ("cores", "load", "memory_total", "memory_available", "own_memory", "hostname", "interfaces"):
            self.assertIn(key, resources)
        self.assertIn("Server", {finding["group"] for finding in body["findings"]})
        self.assert_error(self.client_for("paula", "Projektleitung").get(f"{API}/self-check"), 403, "permission_denied")


class EncryptionApiTests(BackupFolderMixin, ApiTestCase):
    def test_state_and_command(self) -> None:
        """ADM-009: what is encrypted, and the command that switches it on."""
        body = self.admin.get(f"{API}/encryption").json()
        # SQLite says nothing; the MariaDB of the tests is not encrypted.
        self.assertEqual(body["database_encrypted"], None if dumped_rows_visible() else False)
        self.assertFalse(body["backups_encrypted"])
        self.assertFalse(body["complete"])
        self.assertEqual(body["command"], "sudo rentalars encryption enable")
        self.write_config(encrypt=True)
        body = self.admin.get(f"{API}/encryption").json()
        self.assertTrue(body["backups_encrypted"])
        self.assert_error(self.client_for("paula", "Projektleitung").get(f"{API}/encryption"), 403, "permission_denied")


class BackupApiTests(BackupFolderMixin, ApiTestCase):
    def test_start_status_download(self) -> None:
        """ADM-010: POST starts, /jobs/{id} tells the state, /jobs/{id}/result delivers the .tar.gz."""
        make_customer("Kulturverein Nordstadt")
        started = self.admin.post(f"{API}/backups")
        self.assertEqual(started.status_code, 202, started.content)
        body = started.json()
        self.assertIsNone(body["key"])
        self.assertFalse(body["encrypted"])
        job = self.admin.get(f"{API}/jobs/{body['id']}").json()
        self.assertEqual(job["status"], "done", job["message"])
        self.assertEqual(job["result_url"], f"/api/v1/jobs/{body['id']}/result")
        result = self.admin.get(job["result_url"])
        with tarfile.open(fileobj=io.BytesIO(b"".join(result.streaming_content)), mode="r:gz") as archive:
            names = archive.getnames()
            self.assertEqual(names[:3], ["database.sql", "rentalars.conf", "VERSION"])
            assert_dumped(self, archive.extractfile("database.sql").read().decode("utf-8"), "Kulturverein Nordstadt")
        listed = self.admin.get(f"{API}/backups").json()
        self.assertEqual([item["id"] for item in listed], [body["id"]])
        # AUT-028: the download through the API is in the access log.
        entry = AccessLogEntry.objects.get(object_type="backup")
        self.assertEqual((entry.action, entry.object_id), ("api", str(body["id"])))

    def test_encrypted_with_its_own_key(self) -> None:
        """ADM-010: with encrypted backups the answer carries the key of this backup."""
        self.write_config(encrypt=True)
        started = self.admin.post(f"{API}/backups").json()
        self.assertRegex(started["key"], r"^[0-9a-f]{4}(-[0-9a-f]{4}){9}$")
        self.assertTrue(started["encrypted"])
        self.assertTrue(started["result_name"].endswith(".tar.gz.enc"))
        listed = self.admin.get(f"{API}/backups").json()
        self.assertEqual(listed[0]["key"], started["key"])
        content = b"".join(self.admin.get(started["result_url"]).streaming_content)
        self.assertTrue(content.startswith(b"Salted__"))

    def test_rights_and_one_at_a_time(self) -> None:
        reader = self.client_for("nora", "Nur-Lesen")
        self.assert_error(reader.post(f"{API}/backups"), 403, "permission_denied")
        self.assert_error(reader.get(f"{API}/backups"), 403, "permission_denied")
        BackgroundJob.objects.create(
            kind="backup", title="Sicherung", status=JobStatus.RUNNING, created_by=self.admin_user
        )
        self.assert_error(self.admin.post(f"{API}/backups"), 400, "validation_error", "backup")
        # Somebody else's backup is not to be had.
        other = self.client_of(make_user("chefin", superuser=True))
        self.assertEqual(other.get(f"{API}/backups").json(), [])


class AccessLogApiTests(ApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.customer = make_customer("Kulturverein Nordstadt")

    def test_reads_through_the_api_are_logged(self) -> None:
        """AUT-028: a record read through the API; lists are not logged."""
        self.assertEqual(self.admin.get(f"{API}/customers").status_code, 200)
        self.assertFalse(AccessLogEntry.objects.exists())
        self.assertEqual(self.admin.get(f"{API}/customers/{self.customer.pk}").status_code, 200)
        self.assertEqual(self.admin.get(f"{API}/customers/{self.customer.pk}/contacts").status_code, 200)
        project = make_project("Stadtfest", customer=self.customer)
        self.assertEqual(self.admin.get(f"{API}/projects/{project.pk}/material-lines").status_code, 200)
        found = [(entry.object_type, entry.object_id, entry.action) for entry in AccessLogEntry.objects.order_by("id")]
        self.assertEqual(found, [("customer", str(self.customer.pk), "api"), ("project", str(project.pk), "api")])
        self.assertEqual(AccessLogEntry.objects.first().user_label, "admin")

    def test_the_log_with_filters(self) -> None:
        """AUT-028: GET /access-log – by user, object, kind of access, period and text."""
        lena = make_user("lena", superuser=True)
        self.client_of(lena).get(f"{API}/customers/{self.customer.pk}")
        other = make_customer("Stadtwerke")
        self.admin.get(f"{API}/customers/{other.pk}")

        def found(**params: object) -> list[str]:
            response = self.admin.get(f"{API}/access-log", params)
            self.assertEqual(response.status_code, 200, response.content)
            return [entry["label"] for entry in response.json()["results"]]

        everything = self.admin.get(f"{API}/access-log").json()
        self.assertEqual(everything["count"], 2)
        first = everything["results"][-1]
        self.assertEqual(
            {key: first[key] for key in ("username", "action", "object_type", "object_id", "ip_address")},
            {
                "username": "lena",
                "action": "api",
                "object_type": "customer",
                "object_id": str(self.customer.pk),
                "ip_address": "127.0.0.1",
            },
        )
        self.assertEqual(found(user=lena.pk), [f"{self.customer.number} Kulturverein Nordstadt"])
        self.assertEqual(found(object_type="customer", object_id=other.pk), [f"{other.number} Stadtwerke"])
        self.assertEqual(found(q="Kultur"), [f"{self.customer.number} Kulturverein Nordstadt"])
        self.assertEqual(found(action="view"), [])
        self.assertEqual(found(since="2027-03-02"), [])
        self.assertEqual(len(found(since="2027-03-01", until="2027-03-01T23:00")), 2)
        self.assert_error(self.admin.get(f"{API}/access-log", {"object_type": "planet"}), 400, "validation_error")
        self.assert_error(self.admin.get(f"{API}/access-log", {"action": "smell"}), 400, "validation_error")
        self.assert_error(self.admin.get(f"{API}/access-log", {"since": "gestern"}), 400, "validation_error")

    def test_read_right_of_the_settings_is_enough(self) -> None:
        role = Role.objects.create(name="Datenschutz", module_levels={"administration": 1})
        reader = self.client_of(make_user("dora", roles=(role.name,)))
        self.assertEqual(reader.get(f"{API}/access-log").status_code, 200)
        self.assert_error(self.client_for("nora", "Nur-Lesen").get(f"{API}/access-log"), 403, "permission_denied")


class RetentionApiTests(ApiTestCase):
    def test_retention_of_the_access_log(self) -> None:
        """AUT-028: the retention is one of the system settings; at least 30 days."""
        self.assertEqual(self.admin.get(f"{API}/settings").json()["system"]["retention_access_log_days"], 180)
        self.assert_error(
            self.admin.patch(f"{API}/settings", {"system": {"retention_access_log_days": 7}}, format="json"),
            400,
            "validation_error",
        )
        response = self.admin.patch(f"{API}/settings", {"system": {"retention_access_log_days": 60}}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(SystemSettings.load().retention_access_log_days, 60)
