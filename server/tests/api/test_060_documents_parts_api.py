# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the prices and documents of a whole project with subprojects (PRJ-045, PRJ-046, PRJ-049, PRJ-060).

The festival of ``tests.unit.test_060_documents_parts``: the whole project
"Stadtfest" with the stages "Marktplatz" and "Schlosspark".
"""

from __future__ import annotations

from typing import Any

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, ProjectScope, SpecialRight
from rentalars.documents.models import Document
from rentalars.projects import services as project_services
from rentalars.projects.models import ProjectAccessLevel, ProjectMembership, ProjectStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import ALL_RIGHTS, make_user
from tests.unit.test_060_documents_parts import billing_family


def body_of(response: Any) -> bytes:
    """The body of a file response, streamed or not."""
    streamed = getattr(response, "streaming_content", None)
    return b"".join(streamed) if streamed is not None else response.content


class FamilyApiCase(ApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        family = billing_family()
        self.whole, self.market, self.park = family.whole, family.market, family.park

    def external(self) -> Any:
        """A client of somebody limited to assigned projects: the whole project, but not the Schlosspark."""
        Role.objects.create(
            name="Bühnenleitung extern",
            module_levels={Module.PROJECTS: int(Level.WRITE)},
            special_rights=[SpecialRight.PRICES],
            project_scope=ProjectScope.ASSIGNED,
        )
        user = make_user("erik", roles=("Bühnenleitung extern",))
        ProjectMembership.objects.create(project=self.whole, user=user, level=ProjectAccessLevel.EDIT)
        ProjectMembership.objects.create(project=self.park, user=user, level=ProjectAccessLevel.NONE)
        return self.client_of(user)


class PriceOverviewApiTests(FamilyApiCase):
    """PRJ-035, DOK-009 with PRJ-046: ``price-overview`` brings the parts and the sum of all."""

    def test_the_whole_project_with_its_parts(self) -> None:
        cancelled = project_services.create_subproject(self.whole, name="Bühne Hof")
        project_services.change_status(cancelled, ProjectStatus.CANCELLED, rights=ALL_RIGHTS)
        response = self.admin.get(f"{API}/projects/{self.whole.pk}/price-overview")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        # The top level is the whole project's own, as for every project.
        self.assertEqual([line["title"] for line in data["without_group"]["lines"]], ["Stromversorgung"])
        self.assertEqual((data["totals"]["net_total"], data["part_of"]), ("500.00", None))
        self.assertEqual(
            [(part["number"], part["name"], part["heading"]) for part in data["parts"]],
            [
                (self.market.number, "Bühne Marktplatz",
                 f"Teilprojekt {self.market.number} Bühne Marktplatz, 10.03.–12.03.2027"),
                (self.park.number, "Bühne Schlosspark",
                 f"Teilprojekt {self.park.number} Bühne Schlosspark, 12.03.–14.03.2027"),
            ],
        )  # fmt: skip
        market, park = data["parts"]
        self.assertEqual((market["venue"], market["status"]), ("Marktplatz", "confirmed_open"))
        self.assertEqual([(group["name"], group["subtotal"]) for group in market["groups"]], [("Licht", "108.00")])
        self.assertEqual((market["totals"]["net_total"], park["totals"]["net_total"]), ("158.00", "300.00"))
        # PRJ-060: the taken-over spotlights name where they come from and cost nothing here.
        taken = park["without_group"]["lines"][0]
        self.assertEqual((taken["title"], taken["amount"]), ("PAR 64", "0.00"))
        self.assertEqual(taken["taken_over_from"]["project"], self.market.number)
        self.assertIsNone(market["groups"][0]["lines"][0]["taken_over_from"])
        totals = data["family_totals"]
        self.assertEqual(totals["projects"], [self.whole.number, self.market.number, self.park.number])
        self.assertEqual(
            (totals["net_total"], totals["tax_total"], totals["gross_total"]), ("958.00", "176.02", "1134.02")
        )
        self.assertEqual([(tax["net"], tax["tax"]) for tax in totals["tax"]], [("908.00", "172.52"), ("50.00", "3.50")])
        self.assertEqual((data["hidden_parts"], data["cancelled_parts"]), (0, [cancelled.number]))
        groups_only = self.admin.get(f"{API}/projects/{self.whole.pk}/price-overview", {"detail": "groups"}).json()
        self.assertNotIn("lines", groups_only["parts"][1]["groups"][0])
        self.assertEqual(groups_only["parts"][1]["groups"][0]["summary"], "1 × Mischpult")

    def test_a_part_names_its_whole_project(self) -> None:
        data = self.admin.get(f"{API}/projects/{self.market.pk}/price-overview").json()
        self.assertEqual(data["part_of"], {"project": self.whole.pk, "number": self.whole.number, "name": "Stadtfest"})
        self.assertEqual((data["parts"], data["family_totals"]["net_total"]), ([], "158.00"))
        alone = self.admin.get(f"{API}/projects/{self.park.pk}/price-overview").json()
        self.assertEqual(alone["family_totals"]["gross_total"], alone["totals"]["gross_total"])

    def test_parts_the_caller_may_not_read_are_left_out(self) -> None:
        data = self.external().get(f"{API}/projects/{self.whole.pk}/price-overview").json()
        self.assertEqual([part["number"] for part in data["parts"]], [self.market.number])
        self.assertEqual((data["hidden_parts"], data["family_totals"]["net_total"]), (1, "658.00"))

    def test_pdf_and_csv_with_the_parts(self) -> None:
        csv = self.admin.get(f"{API}/projects/{self.whole.pk}/price-overview/csv").content.decode()
        self.assertIn(f"Summe Teilprojekt {self.park.number} Bühne Schlosspark;;;;;;;;;300", csv)
        self.assertIn("Summe brutto;;;;;;;;;1134,02", csv)
        hidden = self.external().get(f"{API}/projects/{self.whole.pk}/price-overview/csv").content.decode()
        self.assertNotIn("Schlosspark", hidden)
        pdf = self.admin.get(f"{API}/projects/{self.whole.pk}/price-overview/pdf", {"detail": "groups"})
        self.assertTrue(pdf.content.startswith(b"%PDF"))


class DocumentsApiTests(FamilyApiCase):
    """PRJ-045: the priced documents at the whole project; a part makes its delivery notes."""

    def test_a_part_refuses_priced_documents_and_makes_its_delivery_note(self) -> None:
        url = f"{API}/projects/{self.market.pk}/documents"
        expected = (
            f"Angebot, Auftragsbestätigung und Rechnung entstehen am Gesamtprojekt {self.whole.number} – mit allen "
            "Teilprojekten."
        )
        for kind in ("offer", "order_confirmation", "invoice"):
            error = self.assert_error(self.admin.post(url, {"kind": kind}, format="json"), 400, "validation_error")
            self.assertIn(expected, error["message"])
            self.assert_error(self.admin.post(f"{url}/preview", {"kind": kind}, format="json"), 400, "validation_error")
        made = self.admin.post(url, {"kind": "delivery_note"}, format="json")
        self.assertEqual(made.status_code, 201, made.content)
        self.assertEqual((made.json()["project"], made.json()["number"]), (self.market.pk, "LS-2027-0001"))

    def test_the_invoice_of_the_whole_project_holds_every_part(self) -> None:
        url = f"{API}/projects/{self.whole.pk}/documents"
        draft = self.admin.post(f"{url}/preview", {"kind": "order_confirmation"}, format="json")
        self.assertTrue(draft.content.startswith(b"%PDF"))
        made = self.admin.post(url, {"kind": "invoice"}, format="json")
        self.assertEqual(made.status_code, 201, made.content)
        invoice = made.json()
        self.assertEqual((invoice["net_total"], invoice["gross_total"]), ("958.00", "1134.02"))
        xml = body_of(self.admin.get(invoice["xml_url"]))
        self.assertIn(b'<cbc:TaxExclusiveAmount currencyID="EUR">958.00</cbc:TaxExclusiveAmount>', xml)
        self.assertEqual(xml.count(b"<cac:InvoiceLine>"), 4)
        self.assert_error(self.admin.post(url, {"kind": "invoice"}, format="json"), 400, "validation_error")

    def test_who_may_not_read_every_part_gets_no_priced_document(self) -> None:
        external = self.external()
        url = f"{API}/projects/{self.whole.pk}/documents"
        error = self.assert_error(external.post(url, {"kind": "offer"}, format="json"), 400, "validation_error")
        self.assertIn(self.park.number, error["message"])
        self.assert_error(external.post(f"{url}/preview", {"kind": "offer"}, format="json"), 400, "validation_error")
        self.assertFalse(Document.objects.exists())
        self.assertEqual(external.post(url, {"kind": "delivery_note"}, format="json").status_code, 201)
