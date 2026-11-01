# SPDX-License-Identifier: GPL-3.0-or-later
"""PRJ-131: a service case as a PDF for the customer – overview and open correspondence, stored under Documents.

The requirement: a PDF export of a service case (as a document for the customer) from the tabs "Überblick" and
"Korrespondenz" (messages without lock), stored automatically under "Dokumente".
"""

from __future__ import annotations

import io
import tempfile

from django.core.exceptions import ValidationError
from django.test import override_settings
from django.urls import reverse
from pypdf import PdfReader

from rentalars.core.models import AuditAction, AuditLogEntry
from rentalars.mail import notes
from rentalars.mail.models import MailAttachment, ProjectMail
from rentalars.projects import case_pdf
from rentalars.projects.models import ProjectFile
from tests.api.base import API, ApiTestCase
from tests.helpers import at, make_project
from tests.ui.base import UiTestCase
from tests.unit.test_092_lock import LockScene

MEDIA = tempfile.mkdtemp(prefix="rentalars-test-media-")


def text_of(project_file: ProjectFile) -> str:
    """The text of a stored PDF."""
    with project_file.file.open("rb") as handle:
        data = handle.read()
    assert data.startswith(b"%PDF")
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)


@override_settings(MEDIA_ROOT=MEDIA)
class CasePdfTests(LockScene, UiTestCase):
    """What the document holds, where it is stored and who may make it."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        self.case.notes = "Der Spot im Foyer flackert seit dem Umbau."
        self.case.save()
        # A note and an open automatic reply: not for the customer, whatever their lock says.
        self.case_note = notes.add_note(
            self.case, text="Intern: Netzteil tauschen", subject="Notiz Werkstatt", user=self.paula
        )
        ProjectMail.objects.filter(pk=self.case_note.pk).update(locked=False)
        ProjectMail.objects.create(
            project=self.case,
            direction="in",
            kind="auto_reply",
            message_key="case-auto",
            message_id="<auto@x.example>",
            subject="Abwesenheitsnotiz",
            sender_address="max@stadthalle.example",
            date=at(1, 7, 20),
            text_body="Ich bin nicht da.",
            locked=False,
        )
        MailAttachment.objects.create(mail=self.case_open, filename="foto-spot.jpg", content_type="image/jpeg", size=3)
        self.url = reverse("projects:case_customer_pdf", args=[self.case.pk])

    def test_the_document_holds_the_overview_and_only_the_open_messages(self) -> None:
        html = case_pdf.render_html(self.case, with_contacts=True)
        self.assertIn(self.case.number, html)
        self.assertIn("Spot flackert", html)
        self.assertIn("Der Spot im Foyer flackert", html)
        self.assertIn("Spot defekt", html)  # open
        self.assertIn("foto-spot.jpg", html)  # attachments by name
        self.assertNotIn("Reparatur kostet 300", html)  # with lock
        self.assertNotIn("Notiz Werkstatt", html)  # a note
        self.assertNotIn("Netzteil tauschen", html)
        self.assertNotIn("Abwesenheitsnotiz", html)  # automatic reply

    def test_the_export_stores_a_pdf_under_documents(self) -> None:
        response = self.client.post(self.url)
        self.assertRedirects(response, reverse("documents:list", args=[self.case.pk]), fetch_redirect_response=False)
        stored = ProjectFile.objects.get(project=self.case)
        self.assertTrue(stored.original_name.endswith(".pdf"))
        self.assertIn(self.case.number.lower(), stored.original_name.lower())
        self.assertFalse(stored.visible_to_crew)
        self.assertEqual(stored.uploaded_by, self.admin_user)
        text = text_of(stored)
        self.assertIn("Spot defekt", text)
        self.assertNotIn("Reparatur kostet", text)
        listed = self.client.get(reverse("documents:list", args=[self.case.pk])).content.decode()
        self.assertIn(stored.title, listed)  # the Documents tab shows it
        entry = AuditLogEntry.objects.filter(action=AuditAction.EVENT, event="case.customer_pdf_made").get()
        self.assertEqual(entry.object_id, str(self.case.pk))

    def test_every_export_is_a_new_file(self) -> None:
        self.client.post(self.url)
        self.client.post(self.url)
        stored = list(ProjectFile.objects.filter(project=self.case).order_by("pk"))
        self.assertEqual(len(stored), 2)
        self.assertNotEqual(stored[0].file.name, stored[1].file.name)

    def test_the_button_is_on_the_page_of_the_case(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:case_detail", args=[self.case.pk])))
        self.assertIn(self.url, page)
        self.assertIn("PDF für den Kunden", page)

    def test_who_may_make_it(self) -> None:
        # The person responsible (a crew role) works on the case, so he may – also without the price right.
        kai = self.browser_of(self.kai)
        self.assertEqual(kai.post(self.url).status_code, 302)
        self.assertEqual(ProjectFile.objects.filter(project=self.case).count(), 1)
        # Reading without the right to change: no.
        rita = self.browser_of(self.rita)
        self.assertIn(rita.post(self.url).status_code, (403, 404))
        # Carla, planned in a project but not working on the case, does not even see it.
        carla = self.browser_of(self.carla)
        self.assertIn(carla.post(self.url).status_code, (403, 404))
        self.assertEqual(ProjectFile.objects.filter(project=self.case).count(), 1)

    def test_a_get_does_nothing(self) -> None:
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertFalse(ProjectFile.objects.exists())

    def test_a_project_is_no_service_case(self) -> None:
        project = make_project("Stadtfest 2")
        self.assertEqual(self.client.post(reverse("projects:case_customer_pdf", args=[project.pk])).status_code, 404)
        with self.assertRaises(ValidationError):
            case_pdf.export_customer_pdf(project, user=self.admin_user)

    def test_contact_and_reporter_only_for_who_sees_customers(self) -> None:
        self.case.case_contact = "Max Mustermann"
        self.case.save()
        self.assertIn("Max Mustermann", case_pdf.render_html(self.case, with_contacts=True))
        self.assertNotIn("Max Mustermann", case_pdf.render_html(self.case, with_contacts=False))

    def test_a_long_message_is_cut_and_says_so(self) -> None:
        ProjectMail.objects.filter(pk=self.case_open.pk).update(text_body="x" * (case_pdf.MESSAGE_LIMIT + 50))
        message = case_pdf.messages_of(self.case)[-1]
        self.assertTrue(message.shortened)
        self.assertEqual(len(message.text), case_pdf.MESSAGE_LIMIT)

    def test_office_role_without_prices_is_enough_for_a_case_it_reads_and_changes(self) -> None:
        lena = self.browser_of(self.lena)
        self.assertEqual(lena.post(self.url).status_code, 302)


@override_settings(MEDIA_ROOT=MEDIA)
class CasePdfApiTests(LockScene, ApiTestCase):
    """``POST /service-cases/{id}/customer-pdf`` (API-002)."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        self.url = f"{API}/service-cases/{self.case.pk}/customer-pdf"

    def test_it_makes_the_file_and_names_it(self) -> None:
        response = self.client_of(self.paula).post(self.url, {}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        stored = ProjectFile.objects.get(pk=body["id"])
        self.assertEqual((stored.project_id, body["file_name"]), (self.case.pk, stored.original_name))
        self.assertEqual(body["messages"], 1)  # only the open one
        self.assertIn("Spot defekt", text_of(stored))
        self.assertNotIn("Reparatur kostet", text_of(stored))
        again = self.client_of(self.paula).post(self.url, {}, format="json")
        self.assertNotEqual(again.json()["id"], body["id"])

    def test_the_person_responsible_may_the_reader_may_not(self) -> None:
        self.assertEqual(self.client_of(self.kai).post(self.url, {}, format="json").status_code, 201)
        self.assertIn(self.client_of(self.rita).post(self.url, {}, format="json").status_code, (403, 404))
        self.assertIn(self.client_of(self.carla).post(self.url, {}, format="json").status_code, (403, 404))

    def test_a_project_is_not_found_as_a_case(self) -> None:
        url = f"{API}/service-cases/{self.project.pk}/customer-pdf"
        self.assertEqual(self.client_of(self.paula).post(url, {}, format="json").status_code, 404)
