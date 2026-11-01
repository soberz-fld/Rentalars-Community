# SPDX-License-Identifier: GPL-3.0-or-later
"""API, area "projects": dividing a project into subprojects (PRJ-050), service cases (PRJ-090) and show
files among the files of a project (PRJ-089)."""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile

from rentalars.mail.fetching import fetch_mail
from rentalars.mail.models import ProjectMail, UnknownTagMail
from rentalars.projects import service_cases
from rentalars.projects.models import CrewLine, MaterialLine, Project, ProjectFile
from rentalars.projects.showfiles import showfile_type
from tests.api.base import API, ApiTestCase
from tests.helpers import add_group, add_line, at, make_customer, make_person, make_project, make_stock, make_user, plan
from tests.mailbox import FakeMailbox, add_mailbox, configure_mailbox, mailboxes, make_mail


class SplitApiTests(ApiTestCase):
    """PRJ-050: ``GET`` and ``POST /projects/{id}/split``."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", start=at(10, 8), end=at(13, 20))
        spots = make_stock("L-010", 10, "Spot")
        self.market = add_group(self.project, "Bühne Marktplatz")
        self.park = add_group(self.project, "Bühne Schlosspark")
        self.line = add_line(self.project, spots, 2, group=self.market).line
        self.crew = plan(self.project, "Lichttechnik", start=at(10, 8), end=at(10, 18))
        self.url = f"{API}/projects/{self.project.pk}/split"

    def test_the_plan(self) -> None:
        response = self.admin.get(self.url)
        self.assertEqual(response.status_code, 200, response.content)
        plan_document = response.json()
        self.assertTrue(plan_document["possible"])
        self.assertEqual(plan_document["refusal"], "")
        market = plan_document["groups"][0]
        self.assertEqual(
            {key: market[key] for key in ("id", "name", "lines", "subgroups", "possible", "stays_a_group")},
            {
                "id": self.market.pk,
                "name": "Bühne Marktplatz",
                "lines": 1,
                "subgroups": 0,
                "possible": True,
                "stays_a_group": False,
            },
        )
        self.assertEqual([line["id"] for line in plan_document["crew_lines"]], [self.crew.pk])

    def test_divide(self) -> None:
        response = self.admin.post(
            self.url, {"groups": [self.market.pk], "crew": {str(self.crew.pk): self.market.pk}}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        (part,) = response.json()["parts"]
        self.assertEqual(
            (part["number"], part["name"], part["parent"]),
            (f"{self.project.number}-1", "Bühne Marktplatz", self.project.pk),
        )
        self.assertEqual(MaterialLine.objects.get(pk=self.line.pk).project_id, part["id"])
        self.assertEqual(CrewLine.objects.get(pk=self.crew.pk).project_id, part["id"])
        family = self.admin.get(f"{API}/projects/{self.project.pk}").json()
        self.assertEqual(family["subprojects"], [part["id"]])

    def test_refused(self) -> None:
        self.assert_error(self.admin.post(self.url, {"groups": []}, format="json"), 400, "validation_error")
        self.assert_error(self.admin.post(self.url, {"groups": "x"}, format="json"), 400, "validation_error")
        self.assert_error(
            self.admin.post(
                self.url, {"groups": [self.market.pk], "crew": {str(self.crew.pk): self.park.pk}}, format="json"
            ),
            400,
            "validation_error",
        )
        reader = self.client_for("lea", "Nur-Lesen")
        self.assertEqual(reader.get(self.url).status_code, 200)
        self.assertEqual(reader.post(self.url, {"groups": [self.market.pk]}, format="json").status_code, 403)
        self.assertFalse(self.project.subprojects.exists())


class ServiceCaseApiTests(ApiTestCase):
    """PRJ-090: ``/service-cases`` and the service cases in ``/projects``."""

    url = f"{API}/service-cases"

    def test_create_change_and_list(self) -> None:
        customer = make_customer("Stadtwerke")
        anna = make_user("anna", roles=("Projektleitung",))
        created = self.admin.post(
            self.url,
            {"name": "Spot flackert", "customer": customer.pk, "notes": "Bühne 2", "manager": anna.pk},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        case = created.json()
        self.assertEqual(case["case_status"], "open")
        self.assertEqual(case["mail_tag"], f"[RL#{case['number']}]")
        detail = f"{self.url}/{case['id']}"
        self.assertEqual(self.admin.get(detail).json()["name"], "Spot flackert")
        changed = self.admin.patch(detail, {"case_status": "in_progress", "case_contact": "Herr Meier"}, format="json")
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual((changed.json()["case_status"], changed.json()["case_contact"]), ("in_progress", "Herr Meier"))
        # PRJ-090: a case keeps its customer – taking it away is refused.
        self.assert_error(
            self.admin.put(detail, {"name": "Spot flackert, Bühne 2", "customer": None}, format="json"),
            400,
            "validation_error",
            "customer",
        )
        replaced = self.admin.put(detail, {"name": "Spot flackert, Bühne 2", "customer": customer.pk}, format="json")
        self.assertEqual(replaced.status_code, 200, replaced.content)
        listed = self.admin.get(self.url).json()
        self.assertEqual([row["id"] for row in listed["results"]], [case["id"]])
        self.admin.patch(detail, {"case_status": "done"}, format="json")
        self.assertEqual(self.admin.get(self.url).json()["results"], [])
        done = self.admin.get(f"{self.url}?status=done&manager={anna.pk}").json()["results"]
        self.assertEqual([row["id"] for row in done], [case["id"]])
        self.assert_error(self.admin.patch(detail, {"case_status": "closed"}, format="json"), 400, "validation_error")

    def test_cases_are_projects_but_not_in_the_list_of_projects(self) -> None:
        project = make_project("Stadtfest")
        case = service_cases.create_case(name="Störung")
        listed = self.admin.get(f"{API}/projects").json()["results"]
        self.assertEqual([row["id"] for row in listed], [project.pk])
        cases = self.admin.get(f"{API}/projects?kind=service_case").json()["results"]
        self.assertEqual([row["id"] for row in cases], [case.pk])
        detail = self.admin.get(f"{API}/projects/{case.pk}").json()
        self.assertEqual((detail["kind"], detail["case_status"]), ("service_case", "open"))
        self.assert_error(
            self.admin.post(f"{API}/projects/{case.pk}/status", {"status": "confirmed"}, format="json"),
            400,
            "validation_error",
        )
        self.assert_error(
            self.admin.post(
                f"{API}/projects/{case.pk}/material-lines",
                {"product": make_stock("L-010", 1).pk, "quantity": 1},
                format="json",
            ),
            400,
            "validation_error",
        )
        # A project is no service case.
        self.assertEqual(self.admin.get(f"{self.url}/{project.pk}").status_code, 404)

    def test_convert_and_delete(self) -> None:
        case = service_cases.create_case(name="Reparatur wird Vermietung")
        convert = f"{self.url}/{case.pk}/convert"
        self.assert_error(
            self.admin.post(convert, {"start": at(10).isoformat(), "end": at(12).isoformat()}, format="json"),
            400,
            "validation_error",
        )
        customer = make_customer("Stadtwerke")
        body = {"start": at(10).isoformat(), "end": at(12).isoformat(), "customer": customer.pk}
        response = self.admin.post(convert, body, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()["kind"], response.json()["status"]), ("project", "inquiry"))
        self.assertEqual(self.admin.get(f"{self.url}/{case.pk}").status_code, 404)
        other = service_cases.create_case(name="Frage")
        self.assertEqual(self.admin.delete(f"{self.url}/{other.pk}").status_code, 204)
        self.assertFalse(Project.objects.filter(pk=other.pk).exists())

    def test_rights(self) -> None:
        case = service_cases.create_case(name="Frage")
        reader = self.client_for("lea", "Nur-Lesen")
        self.assertEqual(reader.get(f"{self.url}/{case.pk}").status_code, 200)
        self.assertEqual(reader.patch(f"{self.url}/{case.pk}", {"case_status": "done"}, format="json").status_code, 403)
        self.assertEqual(reader.post(self.url, {"name": "Neu"}, format="json").status_code, 403)

    def test_from_an_inquiry(self) -> None:
        configure_mailbox()
        add_mailbox("Info", "info@verleih.example", process_untagged=True)
        raw = make_mail("Beamer defekt", message_id="<b@x.example>", sender="Max <max@example.org>")
        with mailboxes({"projekte@verleih.example": FakeMailbox(), "info@verleih.example": FakeMailbox(raw)}):
            fetch_mail(force=True)
        inquiry = UnknownTagMail.objects.get(tag="")
        with mailboxes({"projekte@verleih.example": FakeMailbox(), "info@verleih.example": FakeMailbox()}):
            customer = make_customer().pk  # PRJ-090
            gone = self.admin.post(
                self.url, {"name": "Beamer", "inquiry": inquiry.pk, "customer": customer}, format="json"
            )
        self.assert_error(gone, 400, "validation_error", "inquiry")
        self.assertFalse(Project.objects.filter(kind="service_case").exists())
        with mailboxes({"projekte@verleih.example": FakeMailbox(), "info@verleih.example": FakeMailbox(raw)}):
            # PRJ-090: the sender is no known customer – the customer is needed.
            refused = self.admin.post(self.url, {"name": "Beamer", "inquiry": inquiry.pk}, format="json")
            self.assert_error(refused, 400, "validation_error", "customer")
            body = {"name": "Beamer", "inquiry": inquiry.pk, "customer": customer}
            created = self.admin.post(self.url, body, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(ProjectMail.objects.get().project_id, created.json()["id"])
        self.assert_error(
            self.admin.post(self.url, {"name": "Noch mal", "inquiry": inquiry.pk}, format="json"),
            400,
            "validation_error",
            "inquiry",
        )


class ShowfileApiTests(ApiTestCase):
    """PRJ-089: show files through ``/projects/{id}/files`` and in the deployment view."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.base = f"{API}/projects/{self.project.pk}/files"

    def test_upload_and_mark(self) -> None:
        first = self.admin.post(
            self.base, {"file": SimpleUploadedFile("Gala.esf3d", b"show"), "show_version": "3.2.9"}, format="multipart"
        )
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(
            {
                key: first.json()[key]
                for key in ("document_type", "show_system", "show_version", "is_current_show", "visible_to_crew")
            },
            {
                "document_type": showfile_type().pk,
                "show_system": "ETC Eos",
                "show_version": "3.2.9",
                "is_current_show": True,
                "visible_to_crew": True,
            },
        )
        second = self.admin.post(
            self.base, {"file": SimpleUploadedFile("Gala-2.esf3d", b"show")}, format="multipart"
        ).json()
        self.assertFalse(ProjectFile.objects.get(pk=first.json()["id"]).is_current_show)
        back = self.admin.patch(f"{self.base}/{first.json()['id']}", {"is_current_show": True}, format="json")
        self.assertEqual(back.status_code, 200, back.content)
        self.assertTrue(back.json()["is_current_show"])
        self.assertFalse(ProjectFile.objects.get(pk=second["id"]).is_current_show)
        kept = self.admin.post(
            self.base,
            {"file": SimpleUploadedFile("Gala-3.esf3d", b"show"), "is_current_show": "false"},
            format="multipart",
        ).json()
        self.assertFalse(kept["is_current_show"])
        self.assert_error(
            self.admin.post(self.base, {"file": SimpleUploadedFile("run.exe", b"MZ")}, format="multipart"),
            400,
            "validation_error",
        )

    def test_the_crew_sees_it(self) -> None:
        self.admin.post(
            self.base, {"file": SimpleUploadedFile("FOH.dm7f", b"show"), "show_version": "1.60"}, format="multipart"
        )
        person = make_person(
            "Anna Becker", rates={"Tontechnik": "30.00"}, user=make_user("anna", roles=("Freie Kraft",))
        )
        plan(self.project, "Tontechnik", person)
        crew = self.client_of(person.user)
        deployment = crew.get(f"{API}/projects/{self.project.pk}/deployment").json()
        (show,) = deployment["files"]
        self.assertEqual(
            (show["title"], show["show_system"], show["show_version"], show["is_current_show"]),
            ("FOH.dm7f", "Yamaha DM7", "1.60", True),
        )
