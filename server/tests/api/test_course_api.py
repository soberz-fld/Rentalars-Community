# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests of stage 4 around a project: venues, phases, open items, files, duplicating, requests.

KND-009, PRJ-006, PRJ-007, PRJ-029, PRJ-059, PER-016 and acceptance scenario 20 through the API.
"""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile

from rentalars.masterdata.models import DocumentType
from rentalars.notifications.models import Notification
from rentalars.projects.models import Project, ProjectStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import add_line, make_person, make_project, make_stock, make_user, plan

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


class VenueApiTests(ApiTestCase):
    """KND-009: venues are master data with address, contact on site and notes."""

    def test_create_change_list_and_delete_a_venue(self) -> None:
        created = self.admin.post(
            f"{API}/venues",
            {
                "name": "Stadthalle Musterstadt",
                "street": "Am Markt 1",
                "postal_code": "12345",
                "city": "Musterstadt",
                "contact_name": "Hausmeister Kurz",
                "contact_phone": "0171 1234567",
                "access_notes": "Zufahrt über Hof, Tor 3",
                "power_notes": "CEE 63 A Bühne links",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        venue = created.json()
        self.assertFalse(venue["has_hall_plan"])

        changed = self.admin.patch(f"{API}/venues/{venue['id']}", {"notes": "Ladezone max. 7,5 t"}, format="json")
        self.assertEqual(changed.json()["notes"], "Ladezone max. 7,5 t")
        replaced = self.admin.put(
            f"{API}/venues/{venue['id']}", {**changed.json(), "contact_phone": "0171 7654321"}, format="json"
        )
        self.assertEqual(replaced.json()["contact_phone"], "0171 7654321")
        listed = self.admin.get(f"{API}/venues", {"search": "Stadthalle"}).json()
        self.assertEqual([row["id"] for row in listed["results"]], [venue["id"]])
        self.assertEqual(self.admin.get(f"{API}/venues/{venue['id']}").json()["city"], "Musterstadt")

        self.assertEqual(self.admin.delete(f"{API}/venues/{venue['id']}").status_code, 204)

    def test_a_venue_in_use_is_deactivated_not_deleted(self) -> None:
        venue = self.admin.post(f"{API}/venues", {"name": "Halle 3"}, format="json").json()
        project = make_project()
        project.venue_site_id = venue["id"]
        project.save()
        self.assert_error(self.admin.delete(f"{API}/venues/{venue['id']}"), 400, "validation_error")

    def test_venues_need_the_customer_module(self) -> None:
        crew = self.client_for("ben", "Crew")
        self.assert_error(crew.get(f"{API}/venues"), 403, "permission_denied")


class PhaseApiTests(ApiTestCase):
    """PRJ-006: a project consists of phases with time and place."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.base = f"{API}/projects/{self.project.pk}/phases"

    def test_add_change_list_and_remove_phases(self) -> None:
        venue = self.admin.post(f"{API}/venues", {"name": "Stadthalle"}, format="json").json()
        setup = self.admin.post(
            self.base,
            {
                "kind": "setup",
                "start": "2027-03-10T08:00:00+01:00",
                "end": "2027-03-10T18:00:00+01:00",
                "venue_site": venue["id"],
            },
            format="json",
        )
        self.assertEqual(setup.status_code, 201, setup.data)
        event = self.admin.post(
            self.base,
            {
                "kind": "event",
                "title": "Konzert",
                "start": "2027-03-11T18:00:00+01:00",
                "end": "2027-03-11T23:30:00+01:00",
                "location": "Marktplatz",
            },
            format="json",
        ).json()
        listed = self.admin.get(self.base).json()
        self.assertEqual([row["label"] for row in listed], ["Aufbau", "Konzert"])

        changed = self.admin.patch(f"{self.base}/{event['id']}", {"end": "2027-03-12T00:30:00+01:00"}, format="json")
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertEqual(self.admin.get(f"{self.base}/{event['id']}").json()["location"], "Marktplatz")
        replaced = self.admin.put(
            f"{self.base}/{event['id']}",
            {**changed.json(), "location": "Marktplatz, Bühne Nord", "venue_site": None},
            format="json",
        )
        self.assertEqual(replaced.json()["location"], "Marktplatz, Bühne Nord")
        self.assertEqual(self.admin.delete(f"{self.base}/{setup.json()['id']}").status_code, 204)
        self.assertEqual(len(self.admin.get(self.base).json()), 1)

    def test_the_end_follows_the_start(self) -> None:
        response = self.admin.post(
            self.base,
            {"kind": "setup", "start": "2027-03-10T18:00:00+01:00", "end": "2027-03-10T08:00:00+01:00"},
            format="json",
        )
        self.assert_error(response, 400, "validation_error", "end")

    def test_a_closed_project_cannot_be_changed(self) -> None:
        self.project.status = ProjectStatus.CLOSED
        self.project.save()
        response = self.admin.post(
            self.base,
            {"kind": "setup", "start": "2027-03-10T08:00:00+01:00", "end": "2027-03-10T18:00:00+01:00"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)


class OpenItemApiTests(ApiTestCase):
    """PRJ-059 and acceptance scenario 20: confirmed with open items."""

    def test_scenario_20_confirmed_with_open_items(self) -> None:
        """Note two items, tick them off; then "Confirmed" is suggested and can be set."""
        project = make_project(status=ProjectStatus.CONFIRMED_OPEN)
        base = f"{API}/projects/{project.pk}/open-items"
        created = self.admin.post(
            base, {"texts": ["Bühnenmaße vom Kunden", "Stromanschluss klären", " "]}, format="json"
        )
        self.assertEqual(created.status_code, 201, created.data)
        first, second = created.json()

        overview = self.admin.get(f"{API}/open-items").json()
        self.assertEqual([row["number"] for row in overview], [project.number])
        self.assertEqual(overview[0]["open_count"], 2)

        done = self.admin.patch(f"{base}/{first['id']}", {"is_done": True}, format="json").json()
        self.assertTrue(done["is_done"])
        self.assertEqual(done["done_by"], "admin")
        self.assertFalse(done["suggest_confirmation"])
        done = self.admin.patch(f"{base}/{second['id']}", {"is_done": True}, format="json").json()
        self.assertTrue(done["suggest_confirmation"])
        self.assertTrue(self.admin.get(f"{API}/open-items").json()[0]["suggest_confirmation"])

        status = self.admin.post(f"{API}/projects/{project.pk}/status", {"status": "confirmed"}, format="json")
        self.assertEqual(status.json()["status"], "confirmed")
        self.assertEqual(self.admin.get(f"{API}/open-items").json(), [])

    def test_change_read_and_remove_an_item(self) -> None:
        project = make_project()
        base = f"{API}/projects/{project.pk}/open-items"
        item = self.admin.post(base, {"text": "Rider fehlt"}, format="json").json()[0]
        changed = self.admin.put(f"{base}/{item['id']}", {"text": "Rider der Band fehlt"}, format="json")
        self.assertEqual(changed.json()["text"], "Rider der Band fehlt")
        self.assertEqual([row["text"] for row in self.admin.get(base).json()], ["Rider der Band fehlt"])
        self.assertFalse(self.admin.get(f"{base}/{item['id']}").json()["is_done"])
        self.assertEqual(self.admin.delete(f"{base}/{item['id']}").status_code, 204)

    def test_nothing_to_note_is_an_error(self) -> None:
        project = make_project()
        response = self.admin.post(f"{API}/projects/{project.pk}/open-items", {"texts": ["", "  "]}, format="json")
        self.assert_error(response, 400, "validation_error")


class ProjectFileApiTests(ApiTestCase):
    """PRJ-007: files of a project; the crew sees only the files marked for them (AUT-023)."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.base = f"{API}/projects/{self.project.pk}/files"
        self.stage_plan = DocumentType.objects.get(name="Bühnenplan")
        self.contract = DocumentType.objects.get(name="Vertrag")

    def upload(self, name: str, document_type: DocumentType, data: bytes = PDF, **fields: str) -> dict:
        response = self.admin.post(
            self.base,
            {"file": SimpleUploadedFile(name, data), "document_type": document_type.pk, **fields},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response.json()

    def test_upload_list_read_change_and_delete(self) -> None:
        plan_file = self.upload("buehne.pdf", self.stage_plan, title="Bühnenplan Halle 3")
        self.assertTrue(plan_file["visible_to_crew"])  # as the document type says
        contract = self.upload("vertrag.pdf", self.contract)
        self.assertFalse(contract["visible_to_crew"])
        self.assertEqual(len(self.admin.get(self.base).json()), 2)
        self.assertEqual(self.admin.get(f"{self.base}/{plan_file['id']}").json()["original_name"], "buehne.pdf")

        content = self.admin.get(f"{self.base}/{plan_file['id']}/content")
        self.assertEqual(content.status_code, 200)
        self.assertEqual(b"".join(content.streaming_content), PDF)
        self.assertIn("sandbox", content["Content-Security-Policy"])

        changed = self.admin.patch(f"{self.base}/{contract['id']}", {"title": "Mietvertrag"}, format="json")
        self.assertEqual(changed.json()["title"], "Mietvertrag")
        replaced = self.admin.put(
            f"{self.base}/{contract['id']}", {"title": "Vertrag", "visible_to_crew": False}, format="json"
        )
        self.assertEqual(replaced.status_code, 200, replaced.data)
        self.assertEqual(self.admin.delete(f"{self.base}/{contract['id']}").status_code, 204)
        self.assertEqual([row["id"] for row in self.admin.get(self.base).json()], [plan_file["id"]])

    def test_unknown_file_types_are_refused(self) -> None:
        response = self.admin.post(self.base, {"file": SimpleUploadedFile("tool.exe", b"MZ")}, format="multipart")
        self.assert_error(response, 400, "validation_error")

    def test_the_crew_sees_only_files_for_the_crew(self) -> None:
        plan_file = self.upload("buehne.pdf", self.stage_plan)
        contract = self.upload("vertrag.pdf", self.contract)
        ben = make_user("ben", roles=("Crew",))
        plan(self.project, "Stagehand", make_person("Ben Schmidt", user=ben))
        crew = self.client_of(ben)
        self.assertEqual([row["id"] for row in crew.get(self.base).json()], [plan_file["id"]])
        self.assertEqual(crew.get(f"{self.base}/{plan_file['id']}/content").status_code, 200)
        self.assert_error(crew.get(f"{self.base}/{contract['id']}/content"), 404, "not_found")
        self.assert_error(
            crew.post(self.base, {"file": SimpleUploadedFile("x.pdf", PDF)}, format="multipart"),
            403,
            "permission_denied",
        )
        deployment = crew.get(f"{API}/projects/{self.project.pk}/deployment").json()
        self.assertEqual([row["id"] for row in deployment["files"]], [plan_file["id"]])


class DuplicateApiTests(ApiTestCase):
    """PRJ-029: a project is copied for a new period, with phases and material."""

    def test_duplicate_with_material_and_crew(self) -> None:
        source = make_project("Stadtfest 2027")
        add_line(source, make_stock("L-001", 10), 4)
        plan(source, "Stagehand", make_person("Ben Schmidt"))
        self.admin.post(
            f"{API}/projects/{source.pk}/phases",
            {"kind": "setup", "start": "2027-03-10T08:00:00+01:00", "end": "2027-03-10T18:00:00+01:00"},
            format="json",
        )
        response = self.admin.post(
            f"{API}/projects/{source.pk}/duplicate",
            {
                "name": "Stadtfest 2028",
                "start": "2028-03-08T00:00:00+01:00",
                "end": "2028-03-10T00:00:00+01:00",
                "with_crew": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        copy = Project.objects.get(pk=response.json()["id"])
        self.assertEqual((copy.name, copy.status), ("Stadtfest 2028", ProjectStatus.INQUIRY))
        self.assertEqual(copy.material_lines.get().quantity, 4)
        crew_line = copy.crew_lines.get()
        self.assertIsNone(crew_line.person)  # an open place: people are asked again
        phase = copy.phases.get()
        self.assertEqual((phase.start.year, phase.start.month, phase.start.day), (2028, 3, 8))

    def test_the_new_period_must_make_sense(self) -> None:
        source = make_project()
        response = self.admin.post(
            f"{API}/projects/{source.pk}/duplicate",
            {"start": "2028-03-10T00:00:00+01:00", "end": "2028-03-08T00:00:00+01:00"},
            format="json",
        )
        self.assert_error(response, 400, "validation_error", "end")


class DeploymentRequestApiTests(ApiTestCase):
    """PER-016: a planned person is asked and answers; the project manager hears of it."""

    def test_ask_and_answer(self) -> None:
        manager = make_user("paula", roles=("Projektleitung",))
        project = make_project(manager=manager)
        ben = make_user("ben", roles=("Crew",))
        line = plan(project, "Stagehand", make_person("Ben Schmidt", user=ben))
        base = f"{API}/projects/{project.pk}/crew-lines/{line.pk}"

        asked = self.client_of(manager).post(f"{base}/request")
        self.assertEqual(asked.status_code, 200, asked.data)
        self.assertEqual(
            asked.json(), {"notified": True, "request_status": "requested", "mail_sent": True, "mail_reason": ""}
        )
        self.assertTrue(Notification.objects.filter(user=ben, kind="deployment_request").exists())

        crew = self.client_of(ben)
        mine = [row for row in crew.get(f"{API}/projects/{project.pk}/deployment").json()["crew"] if row["is_me"]]
        self.assertEqual(mine[0]["request_status"], "requested")
        answered = crew.post(f"{base}/answer", {"accept": True, "note": "Bin dabei"}, format="json")
        self.assertEqual(answered.status_code, 200, answered.data)
        self.assertEqual(answered.json()["request_status"], "accepted")
        self.assertTrue(Notification.objects.filter(user=manager, kind="deployment_answer").exists())

    def test_others_cannot_answer_for_a_person(self) -> None:
        project = make_project()
        ben = make_user("ben", roles=("Crew",))
        carla = make_user("carla", roles=("Crew",))
        line = plan(project, "Stagehand", make_person("Ben Schmidt", user=ben))
        plan(project, "Stagehand", make_person("Carla Wolf", user=carla))
        self.admin.post(f"{API}/projects/{project.pk}/crew-lines/{line.pk}/request")
        response = self.client_of(carla).post(
            f"{API}/projects/{project.pk}/crew-lines/{line.pk}/answer", {"accept": False}, format="json"
        )
        self.assert_error(response, 403, "permission_denied")

    def test_an_open_place_cannot_be_asked(self) -> None:
        project = make_project()
        line = plan(project, "Stagehand")
        response = self.admin.post(f"{API}/projects/{project.pk}/crew-lines/{line.pk}/request")
        self.assert_error(response, 400, "validation_error")
