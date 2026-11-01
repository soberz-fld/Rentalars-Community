# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests: the packlist of the whole project and handovers between subprojects (PRJ-048, PRJ-060)."""

from __future__ import annotations

from typing import Any

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, ProjectScope
from rentalars.packing.models import Handover
from rentalars.projects import services
from rentalars.projects.models import Project, ProjectAccessLevel, ProjectMembership
from tests.api.base import API, ApiTestCase
from tests.helpers import ALL_RIGHTS, add_line, at, make_customer, make_project, make_stock, make_user


class PartsApiTestCase(ApiTestCase):
    """A festival with two stages; the six spots of the first go on to the second."""

    def setUp(self) -> None:
        super().setUp()
        self.whole = make_project("Stadtfest", start=at(9, 12), end=at(14, 18), customer=make_customer("Stadt"))
        self.market = services.create_subproject(self.whole, name="Bühne Marktplatz", start=at(10, 8), end=at(12, 8))
        self.park = services.create_subproject(self.whole, name="Bühne Schlosspark", start=at(12, 12), end=at(14, 12))
        self.spot = make_stock("L-100", 6, "Spot")
        self.cable = make_stock("K-005", 20, "XLR-Kabel 5 m")
        add_line(self.whole, make_stock("S-100", 1, "Stromverteiler"), 1)
        self.source = add_line(self.market, self.spot, 6).line
        add_line(self.market, self.cable, 10)
        self.taking = services.take_over_line(self.source, self.park, rights=ALL_RIGHTS).line
        add_line(self.park, self.cable, 4)
        self.a = self.packlist_url(self.market)
        self.b = self.packlist_url(self.park)

    def packlist_url(self, project: Project) -> str:
        listing = self.admin.get(f"{API}/projects/{project.pk}/packlists").json()
        return f"{API}/projects/{project.pk}/packlists/{listing[0]['id']}"

    def rows(self, url: str) -> dict[str, dict[str, Any]]:
        """The rows of a packlist by article number."""
        document = self.admin.get(url).json()
        return {row["article_number"]: row for section in document["sections"] for row in section["rows"]}

    def book(self, client: Any = None, **body: Any) -> Any:
        return (client or self.admin).post(
            f"{self.b}/handovers", {"line": self.taking.pk, "product": self.spot.pk, **body}, format="json"
        )


class TakeoverRowsApiTests(PartsApiTestCase):
    """PRJ-060: both packlists name the other stage; the takeover is not issued from the warehouse."""

    def test_rows_name_where_the_pieces_come_from_and_go(self) -> None:
        spot = self.rows(self.a)["L-100"]
        self.assertIsNone(spot["taken_over_from"])
        self.assertEqual(
            spot["passes_on"],
            [
                {
                    "line": self.taking.pk,
                    "project": {"id": self.park.pk, "number": self.park.number, "name": "Bühne Schlosspark"},
                    "planned": "6.00",
                    "handed_over": "0.00",
                }
            ],
        )
        taking = self.rows(self.b)["L-100"]
        self.assertEqual(taking["taken_over_from"]["project"]["id"], self.market.pk)
        self.assertEqual(taking["awaiting_handover"], "6.00")
        document = self.admin.get(self.b).json()
        self.assertEqual((document["takeover_total"], document["awaiting_handover_total"]), ("6.00", "6.00"))

    def test_issuing_the_later_stage_leaves_the_takeover_alone(self) -> None:
        issued = self.admin.post(f"{self.b}/issue", {"only_packed": False}, format="json")  # PCK-025: everything
        self.assertEqual(issued.status_code, 200, issued.content)
        self.assertEqual(issued.json()["status"], "issued")
        self.assertEqual(self.rows(self.b)["L-100"]["issued"], "0.00")
        self.assertEqual(self.rows(self.b)["L-100"]["allocated_items"], [])


class HandoverApiTests(PartsApiTestCase):
    """PRJ-060: book, list and take back handovers."""

    def setUp(self) -> None:
        super().setUp()
        self.admin.post(f"{self.a}/issue", {"only_packed": False}, format="json")  # PCK-025: everything

    def test_book_partly_list_and_take_back(self) -> None:
        response = self.book(quantity="4")
        self.assertEqual(response.status_code, 201, response.content)
        document = response.json()
        self.assertEqual(document["handover"]["quantity"], "4.00")
        self.assertEqual(document["handover"]["from_project"]["id"], self.market.pk)
        self.assertEqual(document["status"], "partly_issued")
        self.assertEqual(document["awaiting_handover_total"], "2.00")
        self.assertEqual(self.rows(self.a)["L-100"]["handed_over"], "4.00")
        self.assertEqual(self.rows(self.a)["L-100"]["missing"], "2.00")
        rest = self.book()
        self.assertEqual(rest.json()["handover"]["quantity"], "2.00")
        listing = self.admin.get(f"{self.b}/handovers")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual([row["quantity"] for row in listing.json()], ["4.00", "2.00"])
        last = rest.json()["handover"]["id"]
        self.assertEqual(self.admin.delete(f"{self.b}/handovers/{last}").status_code, 204)
        self.assertEqual(self.admin.delete(f"{self.b}/handovers/{last}").status_code, 404)
        self.assertEqual(self.rows(self.b)["L-100"]["issued"], "4.00")
        # PCK-025: the cables of the Schlosspark are still in the warehouse – the stage keeps its status.
        self.assertEqual(Project.objects.get(pk=self.park.pk).status, "confirmed_open")

    def test_errors_in_the_uniform_format(self) -> None:
        self.assert_error(self.book(quantity="7"), 400, "validation_error", "quantity")
        self.assert_error(self.book(line="x"), 400, "validation_error")
        cables = self.rows(self.b)["K-005"]
        self.assert_error(self.book(line=cables["line"], product=cables["product"]), 400, "validation_error")
        first = self.book(quantity="4").json()["handover"]["id"]
        self.book()
        self.assert_error(self.admin.delete(f"{self.b}/handovers/{first}"), 400, "validation_error")

    def test_the_packlist_of_the_earlier_stage_must_be_writable_too(self) -> None:
        Role.objects.create(
            name="Bühnencrew",
            module_levels={Module.PROJECTS: int(Level.READ), Module.PACKING: int(Level.WRITE)},
            project_scope=ProjectScope.ASSIGNED,
        )
        crew = make_user("bert", roles=("Bühnencrew",))
        ProjectMembership.objects.create(project=self.park, user=crew, level=ProjectAccessLevel.READ)
        client = self.client_of(crew)
        self.assert_error(self.book(client), 400, "validation_error")
        self.assertFalse(Handover.objects.exists())

    def test_the_earlier_stage_is_returned_without_the_pieces_handed_on(self) -> None:
        self.book()
        self.admin.post(f"{self.a}/return-all")
        done = self.admin.post(f"{self.a}/complete-return")
        self.assertEqual(done.status_code, 200, done.content)
        self.assertEqual(done.json()["status"], "returned")
        self.assertEqual(done.json()["handed_over_total"], "6.00")


class FamilyPacklistApiTests(PartsApiTestCase):
    """PRJ-048: the whole project with all its parts, read-only."""

    def test_part_by_part_and_per_article(self) -> None:
        response = self.admin.get(f"{API}/projects/{self.whole.pk}/packlists/family")
        self.assertEqual(response.status_code, 200, response.content)
        document = response.json()
        self.assertEqual(document["whole_project"]["id"], self.whole.pk)
        self.assertEqual(document["hidden_parts"], 0)
        self.assertEqual(
            [(part["project"]["id"], part["project"]["is_whole"]) for part in document["parts"]],
            [(self.whole.pk, True), (self.market.pk, False), (self.park.pk, False)],
        )
        self.assertEqual(document["parts"][2]["figures"]["taken_over"], "6.00")
        self.assertEqual(document["figures"]["required"], "21.00")
        articles = {article["article_number"]: article for article in document["articles"]}
        self.assertEqual((articles["L-100"]["from_warehouse"], articles["L-100"]["taken_over"]), ("6.00", "6.00"))
        self.assertEqual(articles["K-005"]["from_warehouse"], "14.00")
        self.assertNotIn("price", response.content.decode())
        # A part answers for its whole project.
        from_part = self.admin.get(f"{API}/projects/{self.park.pk}/packlists/family").json()
        self.assertEqual(from_part["whole_project"]["id"], self.whole.pk)

    def test_a_hidden_part_is_left_out(self) -> None:
        Role.objects.create(
            name="Bühnenleitung extern",
            module_levels={Module.PROJECTS: int(Level.READ), Module.PACKING: int(Level.READ)},
            project_scope=ProjectScope.ASSIGNED,
        )
        external = make_user("erik", roles=("Bühnenleitung extern",))
        ProjectMembership.objects.create(project=self.whole, user=external, level=ProjectAccessLevel.READ)
        ProjectMembership.objects.create(project=self.park, user=external, level=ProjectAccessLevel.NONE)
        document = self.client_of(external).get(f"{API}/projects/{self.whole.pk}/packlists/family").json()
        self.assertEqual(document["hidden_parts"], 1)
        self.assertEqual([part["project"]["id"] for part in document["parts"]], [self.whole.pk, self.market.pk])
        self.assertEqual(
            self.client_of(external).get(f"{API}/projects/{self.park.pk}/packlists/family").status_code, 404
        )

    def test_printed(self) -> None:
        for view in ("parts", "articles"):
            response = self.admin.get(f"{API}/projects/{self.whole.pk}/packlists/family/pdf?view={view}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "application/pdf")
            self.assertTrue(response.content.startswith(b"%PDF"))
        wrong = self.admin.get(f"{API}/projects/{self.whole.pk}/packlists/family/pdf?view=trucks")
        self.assert_error(wrong, 400, "validation_error", "view")
