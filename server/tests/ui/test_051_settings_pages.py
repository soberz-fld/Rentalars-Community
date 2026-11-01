# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser tests of the settings wishes: ADM-008, ADM-009, ADM-010, AUT-028.

* ADM-008 – the self-check shows the server.
* ADM-009 – the requirement: a place that tells where the encryption of the database is switched on: a place in
  the settings that shows the state and explains the command on the server.
* ADM-010 – "Sicherung jetzt erstellen": a backup for download, only for the
  one who made it.
* AUT-028 – the access log: what is logged when people use the pages, and the
  page with its filters and CSV.
"""

from __future__ import annotations

import datetime
import tarfile
import tempfile
from io import BytesIO

from django.core.files.base import ContentFile
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.core.models import AccessAction, AccessKind, AccessLogEntry, BackgroundJob, SystemSettings
from rentalars.personnel.models import Person
from tests.helpers import NOW, dumped_rows_visible, make_customer, make_project, make_user, set_clock
from tests.ui.base import UiTestCase, form_data
from tests.unit.test_051_settings import BackupFolderMixin


def settings_reader(username: str) -> object:
    """A user who may read the settings, but neither change nor delete there."""
    role = Role.objects.create(name="Datenschutz", module_levels={"administration": 1})
    return make_user(username, roles=(role.name,))


class SelfCheckPageTests(UiTestCase):
    def test_the_server_is_shown(self) -> None:
        """ADM-008: processors, memory, host name and running time on the page."""
        page = self.assert_ok(self.client.get(reverse("core:self_check")))
        self.assertIn("<h2>Server</h2>", page)
        for title in ("Prozessoren", "Arbeitsspeicher", "Rechnername", "Speicher von Rentalars"):
            self.assertIn(title, page)
        self.assertIn(reverse("core:backup"), page)


class BackupPageTests(BackupFolderMixin, UiTestCase):
    def test_the_place_is_easy_to_find(self) -> None:
        """ADM-009, ADM-010, AUT-028: the settings lead to backup, encryption and the access log."""
        page = self.assert_ok(self.client.get(reverse("core:administration")))
        self.assertIn(f'href="{reverse("core:backup")}#encryption">Verschlüsselung</a>', page)
        self.assertIn(f'href="{reverse("core:backup")}#backup">Sicherung</a>', page)
        self.assertIn(f'href="{reverse("core:access_log")}">Zugriffsprotokoll</a>', page)

    def test_encryption_is_explained_with_its_command(self) -> None:
        """ADM-009: the state, the command on the server, the recovery key, and why there is no button."""
        page = self.assert_ok(self.client.get(reverse("core:backup")))
        self.assertIn('id="encryption"', page)
        self.assertIn("nicht verschlüsselt", page)
        self.assertIn('data-copy="sudo rentalars encryption enable"', page)
        self.assertIn("Wiederherstellungsschlüssel", page)
        self.assertIn("Warum es dafür keinen Knopf gibt", page)
        self.assertIn("nur root lesen darf", page)
        self.assertIn("docs/betrieb/verschluesselung.md", page)
        self.assertNotIn('<a href="docs/', page)

        self.write_config(encrypt=True)
        page = self.assert_ok(self.client.get(reverse("core:backup")))
        if dumped_rows_visible():
            # On SQLite there is no database server to encrypt: with the backups everything is done.
            self.assertIn("Datenbank und Sicherungen sind verschlüsselt.", page)
            self.assertNotIn("So schaltest du sie ein", page)
        else:
            self.assertIn("So schaltest du sie ein", page)  # the MariaDB of the tests is not encrypted

    def test_back_up_now_and_download(self) -> None:
        """ADM-010: the button, the task, the file – for the one who made it."""
        make_customer("Kulturverein Nordstadt")
        page = self.assert_ok(self.client.get(reverse("core:backup")))
        self.assertIn("Sicherung jetzt erstellen", page)
        self.assertIn("sudo rentalars restore DATEI", page)
        response = self.client.post(reverse("core:backup_start"), follow=True)
        self.assertRedirects(response, reverse("core:backup"))
        self.assertTrue(self.messages_of(response)[0].startswith("Die Sicherung wird geschrieben."))
        job = BackgroundJob.objects.get(kind="backup")
        self.assertEqual(job.status, "done", job.message)
        page = self.assert_ok(response)
        self.assertIn("Deine Sicherungen aus dem Browser", page)
        self.assertIn(reverse("core:job_result", args=[job.pk]), page)
        self.assertIn(job.result_name, page)

        download = self.client.get(reverse("core:job_result", args=[job.pk]))
        self.assertEqual(download.status_code, 200)
        self.assertIn("attachment", download["Content-Disposition"])
        with tarfile.open(fileobj=BytesIO(b"".join(download.streaming_content)), mode="r:gz") as archive:
            self.assertIn("database.sql", archive.getnames())
        # AUT-028: the download of a backup is in the access log.
        entry = AccessLogEntry.objects.get(object_type=AccessKind.BACKUP)
        self.assertEqual((entry.action, entry.object_id, entry.user_id), ("download", str(job.pk), self.admin_user.pk))

        # Another administrator gets neither the file nor the block of the page.
        other = self.browser_of(make_user("chefin", superuser=True))
        self.assertEqual(other.get(reverse("core:job_result", args=[job.pk])).status_code, 404)
        self.assertEqual(other.get(reverse("core:backup_job", args=[job.pk])).status_code, 404)
        self.assertNotIn(job.result_name, self.assert_ok(other.get(reverse("core:backup"))))

    def test_an_encrypted_backup_shows_its_key(self) -> None:
        """ADM-010: with encrypted backups the page explains the own key and shows it when ready."""
        self.write_config(encrypt=True)
        page = self.assert_ok(self.client.get(reverse("core:backup")))
        self.assertIn("bekommt eine Sicherung aus dem Browser einen eigenen Schlüssel", page)
        self.client.post(reverse("core:backup_start"))
        job = BackgroundJob.objects.get(kind="backup")
        from rentalars.core.backup import key_of

        key = key_of(job)
        page = self.assert_ok(self.client.get(reverse("core:backup")))
        self.assertIn(f'data-copy="{key}"', page)
        self.assertIn(".tar.gz.enc", page)
        # The block of the page, as htmx asks for it while the backup is written.
        block = self.assert_ok(self.htmx("get", reverse("core:backup_job", args=[job.pk])))
        self.assertIn(key, block)
        self.assertNotIn("<html", block)
        # The general page of the task says where the key is, but does not show it.
        task = self.assert_ok(self.client.get(reverse("core:job", args=[job.pk])))
        self.assertIn("Einstellungen → Sicherung und Verschlüsselung", task)
        self.assertNotIn(key, task)

    def test_only_one_backup_at_a_time(self) -> None:
        BackgroundJob.objects.create(kind="backup", title="Sicherung", status="running", created_by=self.admin_user)
        page = self.assert_ok(self.client.get(reverse("core:backup")))
        self.assertIn("Gerade wird eine Sicherung geschrieben.", page)
        response = self.client.post(reverse("core:backup_start"), follow=True)
        self.assertIn(
            "Es wird schon eine Sicherung geschrieben. Warte, bis sie fertig ist.", self.messages_of(response)
        )
        self.assertEqual(BackgroundJob.objects.filter(kind="backup").count(), 1)

    def test_rights(self) -> None:
        """ADM-010: backups like the full export – only who may delete in the settings."""
        reader = self.browser_of(settings_reader("dora"))
        page = self.assert_ok(reader.get(reverse("core:backup")))
        self.assertIn("Warum es dafür keinen Knopf gibt", page)
        self.assertNotIn("Sicherung jetzt erstellen", page)
        self.assertEqual(reader.post(reverse("core:backup_start")).status_code, 403)
        manager = self.browser_for("paula", "Projektleitung")
        self.assertEqual(manager.get(reverse("core:backup")).status_code, 403)
        self.assertFalse(BackgroundJob.objects.filter(kind="backup").exists())


class AccessLoggingTests(UiTestCase):
    """AUT-028: what using the pages leaves in the access log."""

    def entries(self, **filters: object) -> list[AccessLogEntry]:
        return list(AccessLogEntry.objects.filter(**filters).order_by("id"))

    def test_a_customer_is_logged_once_per_five_minutes(self) -> None:
        customer = make_customer("Kulturverein Nordstadt")
        url = reverse("customers:detail", args=[customer.pk])
        self.assert_ok(self.client.get(url))
        self.assert_ok(self.client.get(reverse("customers:edit", args=[customer.pk])))
        (entry,) = self.entries()
        self.assertEqual(
            (entry.object_type, entry.object_id, entry.action, entry.ip_address, entry.user_label, entry.path),
            ("customer", str(customer.pk), "view", "127.0.0.1", "admin", url),
        )
        self.assertEqual(entry.label, f"{customer.number} Kulturverein Nordstadt")
        set_clock(NOW + datetime.timedelta(minutes=6))
        self.assert_ok(self.client.get(url))
        self.assertEqual(len(self.entries()), 2)

    def test_what_is_not_logged(self) -> None:
        """AUT-028: lists without export, fragments of htmx, failed requests, the own person."""
        customer = make_customer("Kulturverein Nordstadt")
        self.assert_ok(self.client.get(reverse("customers:list")))
        self.htmx("get", reverse("customers:detail", args=[customer.pk]))
        self.assertEqual(self.client.get(reverse("customers:detail", args=[customer.pk + 1000])).status_code, 404)
        own = Person.objects.get(user=self.admin_user)
        self.assert_ok(self.client.get(reverse("personnel:person_detail", args=[own.pk])))
        self.assert_ok(self.client.get(reverse("personnel:own_profile")))
        self.assertEqual(self.entries(), [])
        # Somebody without the right gets nothing – and leaves nothing.
        crew = self.browser_for("carl", "Crew")
        self.assertIn(crew.get(reverse("customers:detail", args=[customer.pk])).status_code, (403, 404))
        self.assertEqual(self.entries(), [])

    def test_people_and_their_information(self) -> None:
        other = Person.objects.get(user=make_user("rita"))
        self.assert_ok(self.client.get(reverse("personnel:person_detail", args=[other.pk])))
        export = self.client.get(reverse("personnel:person_export", args=[other.pk]))
        self.assertEqual(export.status_code, 200)
        actions = [(entry.object_type, entry.action) for entry in self.entries()]
        self.assertEqual(actions, [("person", "view"), ("person", "export")])

    def test_a_project_its_tabs_files_mails_and_documents(self) -> None:
        from rentalars.mail.models import MailAttachment, ProjectMail
        from rentalars.projects.models import ProjectFile

        project = make_project("Stadtfest")
        with tempfile.TemporaryDirectory() as media, self.settings(MEDIA_ROOT=media, SERVE_MEDIA_VIA_NGINX=False):
            stored = ProjectFile.objects.create(project=project, original_name="Rider.pdf", size=4)
            stored.file.save("Rider.pdf", ContentFile(b"%PDF"), save=True)
            mail = ProjectMail.objects.create(
                project=project,
                message_key="k1",
                message_id="<1@example>",
                subject="Bühnenanweisung",
                text_body="Hallo",
            )
            attachment = MailAttachment.objects.create(mail=mail, filename="Plan.pdf", size=4)
            attachment.file.save("Plan.pdf", ContentFile(b"%PDF"), save=True)
            for name in ("projects:detail", "projects:price_overview", "projects:history", "documents:list"):
                self.assert_ok(self.client.get(reverse(name, args=[project.pk])))
            self.assertEqual(
                self.client.get(reverse("projects:file_download", args=[project.pk, stored.pk])).status_code, 200
            )
            self.assert_ok(self.client.get(reverse("mail:detail", args=[project.pk, mail.pk])))
            self.assertEqual(
                self.client.get(reverse("mail:attachment", args=[project.pk, mail.pk, attachment.pk])).status_code, 200
            )
            csv = self.client.get(reverse("projects:price_overview_csv", args=[project.pk]))
            self.assertEqual(csv.status_code, 200)
        found = [(entry.object_type, entry.action, entry.parent_id) for entry in self.entries()]
        project_id = str(project.pk)
        self.assertEqual(
            found,
            [
                ("project", "view", ""),  # four tabs, one entry
                ("project_file", "download", project_id),
                ("mail", "view", project_id),
                ("attachment", "download", project_id),
                ("project", "export", ""),
            ],
        )
        self.assertEqual(self.entries(object_type="mail")[0].label, f"{project.number}: Bühnenanweisung")
        # The filter by project finds everything that belongs to it.
        page = self.assert_ok(self.client.get(reverse("core:access_log"), {"type": "project", "object": project_id}))
        for label in ("Rider.pdf", "Bühnenanweisung", "Plan.pdf"):
            self.assertIn(label, page)

    def test_a_document_download(self) -> None:
        from rentalars.documents import services
        from rentalars.documents.models import DocumentKind
        from tests.helpers import add_line, make_stock, ready_for_invoices

        project = make_project("Stadtfest", customer=ready_for_invoices())
        add_line(project, make_stock("L-010", 6, "PAR 64", price="20.00"), 4)
        with tempfile.TemporaryDirectory() as media, self.settings(MEDIA_ROOT=media, SERVE_MEDIA_VIA_NGINX=False):
            document = services.create_document(project, DocumentKind.ORDER_CONFIRMATION)
            self.assertEqual(self.client.get(reverse("documents:file", args=[document.pk])).status_code, 200)
        (entry,) = self.entries()
        self.assertEqual((entry.object_type, entry.action, entry.parent_id), ("document", "download", str(project.pk)))
        self.assertIn(document.number, entry.label)

    def test_csv_exports_of_lists_and_the_full_export(self) -> None:
        make_customer("Kulturverein Nordstadt")
        export = self.client.get(reverse("customers:list"), {"format": "csv", "q": "Kultur"})
        self.assertEqual(export.status_code, 200)
        (entry,) = self.entries()
        self.assertEqual((entry.object_type, entry.object_id, entry.action), ("list", "customers:list", "export"))
        self.assertTrue(entry.label.endswith(".csv"), entry.label)
        self.assertIn("format=csv", entry.path)
        self.assertIn("q=Kultur", entry.path)

        with tempfile.TemporaryDirectory() as media, self.settings(MEDIA_ROOT=media, SERVE_MEDIA_VIA_NGINX=False):
            self.client.post(reverse("core:full_export"))
            job = BackgroundJob.objects.get(kind="export")
            download = self.client.get(reverse("core:job_result", args=[job.pk]))
            b"".join(download.streaming_content)
        entry = self.entries(object_type=AccessKind.FULL_EXPORT)[0]
        self.assertEqual((entry.action, entry.object_id), (AccessAction.DOWNLOAD, str(job.pk)))


class AccessLogPageTests(UiTestCase):
    """AUT-028: the page "Zugriffsprotokoll" with its filters and CSV."""

    def setUp(self) -> None:
        super().setUp()
        self.customer = make_customer("Kulturverein Nordstadt")
        self.other = make_customer("Stadtwerke")
        self.lena = make_user("lena", superuser=True)
        browser = self.browser_of(self.lena)
        browser.get(reverse("customers:detail", args=[self.customer.pk]))
        self.client.get(reverse("customers:detail", args=[self.other.pk]))

    def test_page_and_filters(self) -> None:
        page = self.assert_ok(self.client.get(reverse("core:access_log")))
        self.assertIn("<h1>Zugriffsprotokoll</h1>", page)
        self.assertIn("Aufbewahrt wird 180 Tage lang.", page)
        self.assertIn("Kulturverein Nordstadt", page)
        self.assertIn("Stadtwerke", page)
        # Every entry links to the log of its object.
        self.assertIn(f"?type=customer&amp;object={self.customer.pk}", page)

        def shown(**filters: object) -> str:
            return self.assert_ok(self.client.get(reverse("core:access_log"), filters))

        page = shown(user=self.lena.pk)
        self.assertIn("Kulturverein Nordstadt", page)
        self.assertNotIn("Stadtwerke", page)
        page = shown(type="customer", object=self.other.pk)
        self.assertIn("Nur dieses Objekt", page)
        self.assertNotIn("Kulturverein Nordstadt", page)
        self.assertIn("Kulturverein Nordstadt", shown(q="Kultur"))
        self.assertNotIn("Stadtwerke", shown(q="Kultur"))
        self.assertIn("Keine Einträge.", shown(action="download"))
        self.assertIn("Keine Einträge.", shown(type="person"))
        self.assertIn("Keine Einträge.", shown(since="2027-03-02"))
        self.assertIn("Stadtwerke", shown(since="2027-03-01", until="2027-03-01"))

    def test_csv(self) -> None:
        response = self.client.get(reverse("core:access_log"), {"format": "csv", "user": self.lena.pk})
        self.assertEqual(response.status_code, 200)
        text = response.content.decode("utf-8-sig")
        header, row = text.splitlines()[:2]
        self.assertEqual(header, "Zeitpunkt;Nutzer;Zugriff;Art des Objekts;Objekt;IP-Adresse")
        self.assertIn("lena;geöffnet;Kunde;", row)
        # Exporting the log is itself in the log.
        self.assertTrue(AccessLogEntry.objects.filter(object_type="list", object_id="core:access_log").exists())

    def test_rights(self) -> None:
        reader = self.browser_of(settings_reader("dora"))
        self.assert_ok(reader.get(reverse("core:access_log")))
        self.assertEqual(self.browser_for("paula", "Projektleitung").get(reverse("core:access_log")).status_code, 403)


class RetentionSettingTests(UiTestCase):
    def test_the_retention_is_set_with_the_others(self) -> None:
        """AUT-028: "keep the access log" among the retention periods; at least 30 days."""
        url = reverse("core:company_settings")
        page = self.client.get(url)
        self.assertIn("Zugriffsprotokoll aufbewahren (Tage)", self.assert_ok(page))
        data = form_data(page, containing="system-retention_access_log_days")
        response = self.client.post(url, {**data, "system-retention_access_log_days": "10", "form": "system"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SystemSettings.load().retention_access_log_days, 180)
        self.client.post(url, {**data, "system-retention_access_log_days": "90", "form": "system"})
        self.assertEqual(SystemSettings.objects.get(pk=1).retention_access_log_days, 90)
