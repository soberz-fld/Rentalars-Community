# SPDX-License-Identifier: GPL-3.0-or-later
"""The head of a project (PRJ-078) and the tab "Documents" with the files (PRJ-079)."""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.documents.models import MAKEABLE, PRICED_KINDS, DocumentKind
from rentalars.projects import services as project_services
from rentalars.projects.models import ProjectFile, ProjectStatus
from rentalars.projects.templatetags.project_actions import suggested_document
from tests.helpers import make_project
from tests.ui.base import UiTestCase, form_data

ALL_KINDS = list(MAKEABLE)
UNPRICED_KINDS = [kind for kind in MAKEABLE if kind not in PRICED_KINDS]


class SuggestedDocumentTests(SimpleTestCase):
    """PRJ-078: "Anfrage: Angebot, Zurück: Rechnung" – the document a project usually needs next."""

    def test_the_usual_document_of_each_status(self) -> None:
        expected = {
            ProjectStatus.INQUIRY: DocumentKind.OFFER,
            ProjectStatus.OPTION: DocumentKind.OFFER,
            ProjectStatus.CONFIRMED_OPEN: DocumentKind.ORDER_CONFIRMATION,
            ProjectStatus.CONFIRMED: DocumentKind.ORDER_CONFIRMATION,
            ProjectStatus.OUT: DocumentKind.DELIVERY_NOTE,
            ProjectStatus.RETURNED: DocumentKind.INVOICE,
            ProjectStatus.CLOSED: DocumentKind.INVOICE,
            ProjectStatus.CANCELLED: None,
        }
        for status, kind in expected.items():
            with self.subTest(status=status):
                self.assertEqual(suggested_document(status, ALL_KINDS), kind)

    def test_without_priced_documents_a_running_project_gets_its_delivery_note(self) -> None:
        # Without the price right, or in a subproject (PRJ-045).
        self.assertEqual(suggested_document(ProjectStatus.CONFIRMED, UNPRICED_KINDS), DocumentKind.DELIVERY_NOTE)
        self.assertEqual(suggested_document(ProjectStatus.OUT, UNPRICED_KINDS), DocumentKind.DELIVERY_NOTE)
        self.assertIsNone(suggested_document(ProjectStatus.INQUIRY, UNPRICED_KINDS))
        self.assertIsNone(suggested_document(ProjectStatus.RETURNED, UNPRICED_KINDS))
        self.assertIsNone(suggested_document(ProjectStatus.CONFIRMED, []))


class HeadActionTests(UiTestCase):
    """PRJ-078: "Projekt bearbeiten" first, the status as a list, the next document, then the rest – on every tab."""

    def actions_of(self, page: str) -> str:
        start = page.index('class="actions project-actions')
        return page[start : page.index("</nav>", start)]

    def test_the_order_of_the_actions(self) -> None:
        project = make_project(status=ProjectStatus.INQUIRY)
        actions = self.actions_of(self.assert_ok(self.client.get(reverse("projects:detail", args=[project.pk]))))
        order = [
            actions.index("Projekt bearbeiten"),
            actions.index('<select id="status-choice" name="status"'),
            actions.index("Angebot erstellen"),
            actions.index("Weitere Dokumente"),
            actions.index("Duplizieren"),
            actions.index("Als Vorlage speichern"),
        ]
        self.assertEqual(order, sorted(order))
        documents = reverse("documents:list", args=[project.pk])
        self.assertIn(f'href="{documents}?kind=offer#make-document"', actions)
        # The other kinds sit behind the arrow; the suggested one is not repeated there.
        menu = actions[actions.index('class="menu-list"') :]
        self.assertNotIn("?kind=offer", menu)
        self.assertIn("?kind=invoice", menu)
        self.assertNotIn("?kind=cancellation", menu)

    def test_the_status_is_a_list_of_the_allowed_next_statuses(self) -> None:
        project = make_project(status=ProjectStatus.OUT)
        actions = self.actions_of(self.assert_ok(self.client.get(reverse("projects:detail", args=[project.pk]))))
        select = actions[actions.index("<select") : actions.index("</select>")]
        self.assertIn('<option value="">Status ändern auf …</option>', select)
        self.assertEqual(select.count("<option"), 1 + len(project.allowed_next_statuses))
        for status in project.allowed_next_statuses:
            self.assertIn(f'<option value="{status}">{ProjectStatus(status).label}</option>', select)
        self.assertIn(">Status ändern</button>", actions)
        # The suggestion follows the status: what is out needs its delivery note.
        self.assertIn("Lieferschein erstellen", actions)

    def test_the_actions_are_on_every_tab(self) -> None:
        project = make_project()
        for name in ("projects:detail", "documents:list", "projects:course", "projects:history", "packing:packlist"):
            with self.subTest(tab=name):
                actions = self.actions_of(self.assert_ok(self.client.get(reverse(name, args=[project.pk]))))
                self.assertIn("Projekt bearbeiten", actions)
                self.assertIn("Auftragsbestätigung erstellen", actions)

    def test_changing_the_status_stays_on_the_tab(self) -> None:
        project = make_project(status=ProjectStatus.INQUIRY)
        documents = reverse("documents:list", args=[project.pk])
        page = self.client.get(documents)
        data = form_data(page, "status", status=ProjectStatus.OPTION)
        self.assertEqual(data["next"], documents)
        response = self.client.post(reverse("projects:set_status", args=[project.pk]), data)
        self.assertRedirects(response, documents, fetch_redirect_response=False)
        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.OPTION)

    def test_a_foreign_address_is_not_followed(self) -> None:
        project = make_project(status=ProjectStatus.INQUIRY)
        response = self.client.post(
            reverse("projects:set_status", args=[project.pk]),
            {"status": ProjectStatus.OPTION, "next": "https://example.org/"},
        )
        self.assertRedirects(response, reverse("projects:detail", args=[project.pk]), fetch_redirect_response=False)

    def test_cancelling_asks_first(self) -> None:
        project = make_project()
        actions = self.actions_of(self.assert_ok(self.client.get(reverse("projects:detail", args=[project.pk]))))
        self.assertIn('data-cancel-confirm="Dieses Projekt stornieren?', actions)

    def test_reading_only_shows_no_actions_that_change(self) -> None:
        project = make_project()
        browser = self.browser_for("lena", "Lager")
        actions = self.actions_of(self.assert_ok(browser.get(reverse("projects:detail", args=[project.pk]))))
        for text in ("Projekt bearbeiten", "status-choice", "erstellen", "Duplizieren"):
            self.assertNotIn(text, actions)

    def test_without_the_price_right_no_priced_documents(self) -> None:
        project = make_project()
        Role.objects.create(name="Planung", module_levels={"projects": 2})
        actions = self.actions_of(
            self.assert_ok(self.browser_for("ben", "Planung").get(reverse("projects:detail", args=[project.pk])))
        )
        self.assertIn("Projekt bearbeiten", actions)
        self.assertIn("Lieferschein erstellen", actions)
        for kind in PRICED_KINDS:
            self.assertNotIn(f"?kind={kind}", actions)

    def test_a_subproject_suggests_its_delivery_note(self) -> None:
        whole = make_project()
        part = project_services.create_subproject(whole, name="Bühne 2")
        actions = self.actions_of(self.assert_ok(self.client.get(reverse("projects:detail", args=[part.pk]))))
        self.assertIn("Lieferschein erstellen", actions)
        self.assertNotIn("?kind=offer", actions)
        self.assertNotIn("?kind=invoice", actions)
        self.assertNotIn("Teilprojekt anlegen", actions)
        # The whole project offers to add one, and its parts follow its status if wanted.
        actions = self.actions_of(self.assert_ok(self.client.get(reverse("projects:detail", args=[whole.pk]))))
        self.assertIn("Teilprojekt anlegen", actions)
        self.assertIn('name="with_parts" value="1" checked', actions)


class DocumentsAndFilesTests(UiTestCase):
    """PRJ-079: documents and files on one tab; "Make a document" stays there besides the button in the head."""

    def test_one_tab_for_documents_and_files(self) -> None:
        project = make_project()
        page = self.assert_ok(self.client.get(reverse("documents:list", args=[project.pk])))
        tabs = page[page.index('<nav class="tabs"') : page.index("</nav>", page.index('<nav class="tabs"'))]
        documents = reverse("documents:list", args=[project.pk])
        self.assertIn(f'href="{documents}" aria-current="page">Dokumente</a>', tabs)
        self.assertNotIn(">Dateien</a>", tabs)
        self.assertNotIn(reverse("projects:files", args=[project.pk]), tabs)
        for text in ('id="make-document"', "Dokument erstellen", 'id="files"', "Datei hochladen"):
            self.assertIn(text, page)
        self.assertLess(page.index('id="make-document"'), page.index('id="files"'))

    def test_the_kind_comes_from_the_button_in_the_head(self) -> None:
        project = make_project()
        url = reverse("documents:list", args=[project.pk])
        self.assertEqual(form_data(self.client.get(url + "?kind=delivery_note"), "kind")["kind"], "delivery_note")
        # Something unknown is left alone: the list starts with the offer as always.
        self.assertEqual(form_data(self.client.get(url + "?kind=nonsense"), "kind")["kind"], "offer")

    def test_upload_and_change_lead_back_to_the_files(self) -> None:
        project = make_project()
        url = reverse("documents:list", args=[project.pk])
        data = form_data(self.client.get(url), "title", title="Rider")
        data["file"] = SimpleUploadedFile("rider.pdf", b"%PDF-1.4 test")
        response = self.client.post(reverse("projects:files", args=[project.pk]), data)
        self.assertRedirects(response, url + "#files", fetch_redirect_response=False)
        stored = ProjectFile.objects.get(project=project)
        edit = reverse("projects:file_edit", args=[project.pk, stored.pk])
        page = self.assert_ok(self.client.get(edit))
        self.assertIn(f'href="{url}#files"', page)
        response = self.client.post(edit, form_data(self.client.get(edit), "title", title="Rider 2"))
        self.assertRedirects(response, url + "#files", fetch_redirect_response=False)
        response = self.client.post(reverse("projects:file_delete", args=[project.pk, stored.pk]))
        self.assertRedirects(response, url + "#files", fetch_redirect_response=False)

    def test_reading_only_lists_the_files_without_upload(self) -> None:
        project = make_project()
        stored = ProjectFile.objects.create(project=project, original_name="Plan.pdf", size=4)
        stored.file.save("Plan.pdf", SimpleUploadedFile("Plan.pdf", b"%PDF"), save=True)
        page = self.assert_ok(self.browser_for("lena", "Lager").get(reverse("documents:list", args=[project.pk])))
        self.assertIn("Plan.pdf", page)
        self.assertNotIn("Datei hochladen", page)
        self.assertNotIn("Datei endgültig entfernen", page)
