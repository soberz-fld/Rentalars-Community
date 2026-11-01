# SPDX-License-Identifier: GPL-3.0-or-later
"""API, area "planning" (API-014): moving appointments (VFG-026), invoices switched off (DOK-014).

* VFG-026: ``POST /projects/{id}/reschedule/preview`` says what moving the rental period, the event or a phase
  would do – nothing changes; ``POST /projects/{id}/reschedule`` moves.
* DOK-014: ``system.invoices_enabled`` of ``/settings``; while it is off, invoices, cancellations, handing over to
  Lexware Office and the DATEV export answer 400, and what was made before can still be read.
"""

from __future__ import annotations

from rentalars.core.models import SystemSettings
from rentalars.documents import services as documents
from rentalars.documents.models import AccountingSettings, DocumentKind
from rentalars.projects import course
from rentalars.projects import services as project_services
from rentalars.projects.models import CrewLine, PhaseKind, Project, ProjectStatus, RequestStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import add_line, at, make_person, make_project, make_stock, plan, ready_for_invoices


class RescheduleApiTests(ApiTestCase):
    """VFG-026 through the API."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(start=at(10, 8), end=at(12, 18), event_start=at(11, 18), event_end=at(11, 23))
        self.phase = course.add_phase(self.project, kind=PhaseKind.SETUP, start=at(10, 14), end=at(10, 20))
        self.anna = make_person("Anna Becker", rates={"Stagehand": "20.00"})
        self.line = plan(self.project, "Stagehand", self.anna, phase=self.phase)
        CrewLine.objects.filter(pk=self.line.pk).update(
            request_status=RequestStatus.ACCEPTED, requested_start=at(10, 14), requested_end=at(10, 20)
        )
        self.url = f"{API}/projects/{self.project.pk}/reschedule"

    def test_preview_of_a_phase_changes_nothing(self) -> None:
        body = {
            "what": "phase",
            "phase": self.phase.pk,
            "start": "2027-03-10T15:00+01:00",
            "end": "2027-03-10T21:00+01:00",
        }
        response = self.admin.post(f"{self.url}/preview", body, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertTrue(data["possible"])
        self.assertEqual(data["errors"], [])
        self.assertIsNone(data["rental_period_suggestion"])
        self.assertFalse(data["offers_with_schedule"])
        crew = data["outcome"]["crew_lines"]
        self.assertEqual([line["crew_line"] for line in crew], [self.line.pk])
        self.assertIsNotNone(crew[0]["asked_again"])  # PER-034: asked again
        self.assertEqual(crew[0]["new_start"], "2027-03-10T15:00:00+01:00")
        self.assertEqual(data["outcome"]["changes"][0]["kind"], "phase")
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.start, at(10, 14))
        self.assertEqual(CrewLine.objects.get(pk=self.line.pk).request_status, RequestStatus.ACCEPTED)

    def test_move_a_phase_beyond_the_rental_period(self) -> None:
        body = {
            "what": "phase",
            "phase": self.phase.pk,
            "start": "2027-03-09T18:00+01:00",
            "end": "2027-03-10T02:00+01:00",
        }
        preview = self.admin.post(f"{self.url}/preview", body, format="json").json()
        self.assertEqual(preview["rental_period_suggestion"]["start"], "2027-03-09T18:00:00+01:00")
        self.assertIsNone(preview["rental_period_suggestion"]["blocked_by"])
        self.assertEqual(preview["outcome"]["shortage_after"], 0)
        response = self.admin.post(self.url, {**body, "extend_rental_period": True, "move_crew": False}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertTrue(data["rental_period_extended"])
        self.assertEqual(data["crew_lines"], [])
        self.project.refresh_from_db()
        self.assertEqual(self.project.start, at(9, 18))
        self.assertEqual(CrewLine.objects.get(pk=self.line.pk).start, at(10, 14))

    def test_move_the_rental_period_as_a_whole(self) -> None:
        stock = make_stock("L-092", 2)
        add_line(self.project, stock, 1)
        body = {"what": "period", "start": "2027-03-11T08:00+01:00", "end": "2027-03-13T18:00+01:00"}
        preview = self.admin.post(f"{self.url}/preview", body, format="json").json()
        self.assertTrue(preview["offers_with_schedule"])
        self.assertEqual([change["kind"] for change in preview["outcome"]["changes"]], ["period", "event", "phase"])
        response = self.admin.post(self.url, body, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["material_lines"], 1)
        self.assertEqual((data["shortage_before"], data["shortage_after"]), (0, 0))
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.start, at(11, 14))
        self.project.refresh_from_db()
        self.assertEqual(self.project.event_start, at(12, 18))

    def test_move_the_event(self) -> None:
        body = {"what": "event", "start": "2027-03-11T19:00+01:00", "end": "2027-03-11T23:30+01:00"}
        response = self.admin.post(self.url, body, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.project.refresh_from_db()
        self.assertEqual((self.project.event_start, self.project.start), (at(11, 19), at(10, 8)))

    def test_refusals(self) -> None:
        part = project_services.create_subproject(self.project, name="Bühne 2", start=at(11, 8), end=at(12, 12))
        response = self.admin.post(
            f"{API}/projects/{part.pk}/reschedule",
            {"what": "period", "start": "2027-03-12T08:00+01:00", "end": "2027-03-13T12:00+01:00"},
            format="json",
        )
        self.assert_error(response, 400, "validation_error")
        preview = self.admin.post(
            f"{API}/projects/{part.pk}/reschedule/preview",
            {"what": "period", "start": "2027-03-12T08:00+01:00", "end": "2027-03-13T12:00+01:00"},
            format="json",
        ).json()
        self.assertFalse(preview["possible"])
        self.assertTrue(preview["errors"])
        self.assert_error(
            self.admin.post(
                self.url,
                {"what": "phase", "start": "2027-03-10T15:00+01:00", "end": "2027-03-10T21:00+01:00"},
                format="json",
            ),
            400,
            "validation_error",
            "phase",
        )
        self.assert_error(
            self.admin.post(
                self.url,
                {"what": "period", "start": "2027-03-12T15:00+01:00", "end": "2027-03-10T21:00+01:00"},
                format="json",
            ),
            400,
            "validation_error",
        )
        other = make_project("Messe")
        foreign = course.add_phase(other, kind=PhaseKind.SETUP, start=at(10, 8), end=at(10, 9))
        body = {
            "what": "phase",
            "phase": foreign.pk,
            "start": "2027-03-10T15:00+01:00",
            "end": "2027-03-10T21:00+01:00",
        }
        self.assert_error(self.admin.post(self.url, body, format="json"), 404, "not_found")
        Project.objects.filter(pk=self.project.pk).update(status=ProjectStatus.CLOSED)
        body["phase"] = self.phase.pk
        self.assert_error(self.admin.post(self.url, body, format="json"), 400, "validation_error")

    def test_rights(self) -> None:
        body = {
            "what": "phase",
            "phase": self.phase.pk,
            "start": "2027-03-10T15:00+01:00",
            "end": "2027-03-10T21:00+01:00",
        }
        reader = self.client_for("rita", "Nur-Lesen")
        self.assert_error(reader.post(self.url, body, format="json"), 403, "permission_denied")
        self.assert_error(reader.post(f"{self.url}/preview", body, format="json"), 403, "permission_denied")
        crew = self.client_for("chris", "Crew")
        self.assertIn(crew.post(self.url, body, format="json").status_code, (403, 404))


class InvoicesSwitchedOffApiTests(ApiTestCase):
    """DOK-014 through the API."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(customer=ready_for_invoices(), status=ProjectStatus.RETURNED)
        add_line(self.project, make_stock("L-093", 2), 1)
        self.invoice = documents.create_document(self.project, DocumentKind.INVOICE)

    def test_the_setting(self) -> None:
        self.assertIs(self.admin.get(f"{API}/settings").json()["system"]["invoices_enabled"], True)
        response = self.admin.patch(f"{API}/settings", {"system": {"invoices_enabled": False}}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIs(response.json()["system"]["invoices_enabled"], False)
        self.assertFalse(SystemSettings.load().invoices_enabled)

    def test_off(self) -> None:
        self.admin.patch(f"{API}/settings", {"system": {"invoices_enabled": False}}, format="json")
        documents_url = f"{API}/projects/{self.project.pk}/documents"
        error = self.assert_error(
            self.admin.post(documents_url, {"kind": "invoice"}, format="json"), 400, "validation_error"
        )
        self.assertIn("Rentalars als Buchhaltungsprogramm verwenden", error["message"])
        self.assert_error(
            self.admin.post(f"{documents_url}/preview", {"kind": "invoice"}, format="json"), 400, "validation_error"
        )
        self.assert_error(self.admin.post(f"{API}/documents/{self.invoice.pk}/cancel"), 400, "validation_error")
        accounting = AccountingSettings.load()
        accounting.set_lexware_api_key("key")
        accounting.lexware_enabled = True
        accounting.datev_consultant_number, accounting.datev_client_number = 1001, 1
        accounting.save()
        self.assert_error(
            self.admin.post(f"{API}/documents/{self.invoice.pk}/lexware", {}, format="json"), 400, "validation_error"
        )
        self.assert_error(
            self.admin.get(f"{API}/accounting/datev/bookings?from=2027-03-01&to=2027-03-31"), 400, "validation_error"
        )
        # Other documents as before; the invoice made before stays readable.
        self.assertEqual(self.admin.post(documents_url, {"kind": "offer"}, format="json").status_code, 201)
        listed = self.admin.get(documents_url).json()
        self.assertIn(self.invoice.pk, [document["id"] for document in listed])
        self.assertEqual(self.admin.get(f"{API}/documents/{self.invoice.pk}/pdf").status_code, 200)
        # A project is closed without an invoice.
        project = make_project("Ohne Rechnung", status=ProjectStatus.RETURNED)
        response = self.admin.post(f"{API}/projects/{project.pk}/status", {"status": "closed"}, format="json")
        self.assertIn(response.status_code, (200, 204), response.content)
        self.assertEqual(Project.objects.get(pk=project.pk).status, ProjectStatus.CLOSED)
