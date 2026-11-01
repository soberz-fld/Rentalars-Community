# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages of stage 4 around a project: course, files, duplicating, venues, deployment requests.

PRJ-006, PRJ-007, PRJ-029, PRJ-059, KND-009, PER-016 and acceptance scenario 20 in the browser.
"""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from rentalars.customers.models import Venue
from rentalars.masterdata.models import DocumentType
from rentalars.notifications.models import Notification
from rentalars.projects.models import OpenItem, Project, ProjectFile, ProjectStatus
from tests.helpers import add_line, make_person, make_project, make_stock, make_user, plan
from tests.ui.base import UiTestCase, form_data

PDF = b"%PDF-1.4\n%%EOF\n"


class CoursePageTests(UiTestCase):
    """PRJ-006 phases and PRJ-059 open items on the page "Course"."""

    def test_scenario_20_in_the_browser(self) -> None:
        """Set "Confirmed – details open", note items, tick them off, confirm."""
        project = make_project(status=ProjectStatus.INQUIRY)
        response = self.client.post(f"/projects/{project.pk}/status/", {"status": "confirmed_open"}, follow=True)
        # The status leads to the course, where the open items are noted.
        self.assertEqual(response.redirect_chain[-1][0], f"/projects/{project.number}/course/")
        self.assertIn("Notiere unten, was noch offen ist", self.assert_ok(response))

        self.client.post(f"/projects/{project.pk}/open-items/add/", {"texts": "Bühnenmaße\n\nStrom klären\n"})
        first, second = OpenItem.objects.filter(project=project).order_by("id")
        self.assertEqual((first.text, second.text), ("Bühnenmaße", "Strom klären"))

        overview = self.assert_ok(self.client.get("/projects/open-items/"))
        self.assertIn("Bühnenmaße", overview)

        self.client.post(f"/projects/{project.pk}/open-items/{first.pk}/done/", {"done": "1"})
        response = self.client.post(f"/projects/{project.pk}/open-items/{second.pk}/done/", {"done": "1"}, follow=True)
        self.assertIn("kann jetzt auf „Bestätigt“ gesetzt werden", " ".join(self.messages_of(response)))
        self.assertIn("Alle offenen Punkte sind erledigt.", self.assert_ok(response))
        second.refresh_from_db()
        self.assertEqual((second.is_done, second.done_by), (True, self.admin_user))

        self.client.post(f"/projects/{project.pk}/status/", {"status": "confirmed"})
        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.CONFIRMED)

    def test_untick_and_remove_an_item(self) -> None:
        project = make_project()
        item = OpenItem.objects.create(project=project, text="Rider", is_done=True)
        self.client.post(f"/projects/{project.pk}/open-items/{item.pk}/done/", {"done": "0"})
        item.refresh_from_db()
        self.assertFalse(item.is_done)
        self.client.post(f"/projects/{project.pk}/open-items/{item.pk}/delete/")
        self.assertFalse(OpenItem.objects.exists())

    def test_add_change_and_remove_a_phase(self) -> None:
        project = make_project()
        venue = Venue.objects.create(name="Stadthalle", city="Musterstadt", power_notes="CEE 63 A")
        page = self.client.get(f"/projects/{project.pk}/phases/new/")
        data = form_data(page, "kind", kind="setup", venue_site=venue.pk, title="Aufbau Halle 3")
        response = self.client.post(f"/projects/{project.pk}/phases/new/", data, follow=True)
        text = self.assert_ok(response)
        self.assertIn("Aufbau Halle 3", text)
        phase = project.phases.get()

        page = self.client.get(f"/projects/{project.pk}/phases/{phase.pk}/")
        data = form_data(page, "kind", location="Bühne Nord", end=data["start"])
        response = self.client.post(f"/projects/{project.pk}/phases/{phase.pk}/", data)
        self.assertEqual(response.status_code, 200)  # the end is not after the start
        self.assertIn("Das Ende muss nach dem Beginn liegen", response.content.decode())

        self.client.post(f"/projects/{project.pk}/phases/{phase.pk}/delete/")
        self.assertFalse(project.phases.exists())

    def test_the_venue_shows_in_the_head_and_with_its_notes_in_the_overview(self) -> None:
        """PRJ-102: the page "Zeitplanung" has no box "Venue"."""
        venue = Venue.objects.create(name="Stadthalle", access_notes="Tor 3, Höhe 3,80 m")
        project = make_project(venue_site=venue)
        text = self.assert_ok(self.client.get(f"/projects/{project.pk}/course/"))
        self.assertIn(f'<a href="/customers/venues/{venue.pk}/">Stadthalle</a>', text)  # the head of the project
        self.assertNotIn("Tor 3, Höhe 3,80 m", text)
        overview = self.assert_ok(self.client.get(f"/projects/{project.pk}/deployment/"))
        self.assertIn("Tor 3, Höhe 3,80 m", overview)

    def test_readers_see_but_do_not_change(self) -> None:
        project = make_project()
        OpenItem.objects.create(project=project, text="Rider")
        browser = self.browser_for("lea", "Nur-Lesen")
        text = self.assert_ok(browser.get(f"/projects/{project.pk}/course/"))
        self.assertIn("Rider", text)
        self.assertNotIn("open-items/add/", text)
        self.assertEqual(browser.post(f"/projects/{project.pk}/open-items/add/", {"texts": "x"}).status_code, 403)


class FilePageTests(UiTestCase):
    """PRJ-007: upload, change, download, remove; the crew sees its files in the deployment view."""

    def test_files_from_upload_to_removal(self) -> None:
        project = make_project()
        stage_plan = DocumentType.objects.get(name="Bühnenplan")
        # PRJ-079: the files are on the tab "Documents"; the former address leads there.
        documents = reverse("documents:list", args=[project.pk])
        self.assertRedirects(
            self.client.get(f"/projects/{project.pk}/files/"), documents + "#files", fetch_redirect_response=False
        )
        page = self.client.get(documents)
        data = form_data(page, "title", title="Bühnenplan", document_type=stage_plan.pk)
        data["file"] = SimpleUploadedFile("buehne.pdf", PDF)
        response = self.client.post(f"/projects/{project.pk}/files/", data, follow=True)
        self.assertIn("Datei abgelegt.", self.messages_of(response))
        self.assertEqual(response.redirect_chain[-1][0], documents + "#files")
        self.assertIn("buehne.pdf", response.content.decode())
        project_file = ProjectFile.objects.get()
        self.assertTrue(project_file.visible_to_crew)

        download = self.client.get(f"/projects/{project.pk}/files/{project_file.pk}/")
        self.assertEqual(b"".join(download.streaming_content), PDF)

        page = self.client.get(f"/projects/{project.pk}/files/{project_file.pk}/edit/")
        self.client.post(
            f"/projects/{project.pk}/files/{project_file.pk}/edit/",
            form_data(page, "title", title="Bühnenplan v2", visible_to_crew=None),
        )
        project_file.refresh_from_db()
        self.assertEqual((project_file.title, project_file.visible_to_crew), ("Bühnenplan v2", False))

        self.client.post(f"/projects/{project.pk}/files/{project_file.pk}/delete/")
        self.assertFalse(ProjectFile.objects.exists())

    def test_a_forbidden_type_is_refused(self) -> None:
        project = make_project()
        response = self.client.post(
            f"/projects/{project.pk}/files/", {"file": SimpleUploadedFile("run.sh", b"#!/bin/sh"), "title": ""}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Dateien dieser Art", response.content.decode())
        # The page with the error is the tab "Documents" (PRJ-079).
        self.assertIn('id="make-document"', response.content.decode())

    def test_crew_files_in_the_deployment_view(self) -> None:
        project = make_project()
        ben = make_user("ben", roles=("Crew",))
        plan(project, "Stagehand", make_person("Ben Schmidt", user=ben))
        for name, crew in (("buehne.pdf", True), ("vertrag.pdf", False)):
            self.client.post(
                f"/projects/{project.pk}/files/",
                {"file": SimpleUploadedFile(name, PDF), "title": name, "visible_to_crew": "yes" if crew else "no"},
            )
        crew_file, contract = ProjectFile.objects.order_by("id")
        browser = self.browser_of(ben)
        text = self.assert_ok(browser.get(f"/projects/{project.pk}/deployment/"))
        self.assertIn("buehne.pdf", text)
        self.assertNotIn("vertrag.pdf", text)
        self.assertEqual(browser.get(f"/projects/{project.pk}/files/{crew_file.pk}/").status_code, 200)
        self.assertEqual(browser.get(f"/projects/{project.pk}/files/{contract.pk}/").status_code, 404)


class DuplicatePageTests(UiTestCase):
    """PRJ-029: a project for a new period."""

    def test_duplicate_a_project(self) -> None:
        source = make_project("Stadtfest 2027")
        add_line(source, make_stock("L-001", 10), 3)
        page = self.client.get(f"/projects/{source.pk}/duplicate/")
        data = form_data(page, "name", name="Stadtfest 2028", start="2028-03-08T08:00", end="2028-03-10T20:00")
        response = self.client.post(f"/projects/{source.pk}/duplicate/", data, follow=True)
        copy = Project.objects.get(name="Stadtfest 2028")
        self.assertEqual(response.redirect_chain[-1][0], f"/projects/{copy.number}/")
        self.assertEqual(copy.material_lines.get().quantity, 3)
        self.assertIn(f"aus {source.number} erstellt", " ".join(self.messages_of(response)))


class VenuePageTests(UiTestCase):
    """KND-009: venues as master data, with a hall plan."""

    def test_create_show_and_delete_a_venue(self) -> None:
        page = self.client.get("/customers/venues/new/")
        data = form_data(page, "name", name="Stadthalle", city="Musterstadt", power_notes="CEE 63 A")
        data["hall_plan"] = SimpleUploadedFile("halle.pdf", PDF)
        response = self.client.post("/customers/venues/new/", data, follow=True)
        venue = Venue.objects.get()
        self.assertIn("CEE 63 A", self.assert_ok(response))
        self.assertIn("Stadthalle", self.assert_ok(self.client.get("/customers/venues/", {"q": "stadt"})))
        plan_file = self.client.get(f"/customers/venues/{venue.pk}/hall-plan/")
        self.assertEqual(b"".join(plan_file.streaming_content), PDF)

        page = self.client.get(f"/customers/venues/{venue.pk}/edit/")
        self.client.post(f"/customers/venues/{venue.pk}/edit/", form_data(page, "name", contact_name="Herr Kurz"))
        venue.refresh_from_db()
        self.assertEqual(venue.contact_name, "Herr Kurz")

        self.client.post(f"/customers/venues/{venue.pk}/delete/")
        self.assertFalse(Venue.objects.exists())

    def test_a_venue_in_use_stays(self) -> None:
        venue = Venue.objects.create(name="Stadthalle")
        make_project(venue_site=venue)
        response = self.client.post(f"/customers/venues/{venue.pk}/delete/", follow=True)
        self.assertIn("Deaktiviere ihn", " ".join(self.messages_of(response)))
        self.assertTrue(Venue.objects.exists())


class DeploymentRequestPageTests(UiTestCase):
    """PER-016: ask the planned person; they answer on the start page or in the deployment view."""

    def test_ask_and_answer_in_the_browser(self) -> None:
        manager = make_user("paula", roles=("Projektleitung",))
        project = make_project(manager=manager)
        ben = make_user("ben", roles=("Crew",))
        line = plan(project, "Stagehand", make_person("Ben Schmidt", user=ben))
        response = self.htmx("post", f"/projects/{project.pk}/crew/{line.pk}/request/")
        self.assertEqual(response.status_code, 200)
        line.refresh_from_db()
        self.assertEqual(line.request_status, "requested")

        browser = self.browser_of(ben)
        home = self.assert_ok(browser.get("/"))
        self.assertIn("Du bist angefragt", home)
        response = browser.post(
            f"/projects/{project.pk}/crew/{line.pk}/answer/", {"answer": "decline", "note": "Urlaub"}, follow=True
        )
        self.assertIn("Die Antwort wurde weitergegeben.", self.messages_of(response))
        line.refresh_from_db()
        self.assertEqual((line.request_status, line.answer_note), ("declined", "Urlaub"))
        notice = Notification.objects.get(user=manager, kind="deployment_answer")
        self.assertIn("abgesagt", notice.title)

    def test_every_planned_person_can_be_asked(self) -> None:
        """AUT-026: every person has an account, so the request reaches everybody."""
        project = make_project()
        person = make_person("Neu Angelegt")
        line = plan(project, "Stagehand", person)
        response = self.client.post(f"/projects/{project.pk}/crew/{line.pk}/request/", follow=True)
        self.assertNotIn("hat kein Konto", " ".join(self.messages_of(response)))
        self.assertTrue(Notification.objects.filter(user=person.user, kind="deployment_request").exists())
        response = self.client.post(f"/projects/{project.pk}/crew/{line.pk}/answer/", {"answer": "accept"})
        line.refresh_from_db()
        self.assertEqual(line.request_status, "accepted")
