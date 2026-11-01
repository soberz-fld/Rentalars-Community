# SPDX-License-Identifier: GPL-3.0-or-later
"""The wishes through the API: offer options (DOK-013) and the deployment view as PDF (PRJ-081)."""

from __future__ import annotations

from tests.api.base import API, ApiTestCase
from tests.helpers import at, make_person, make_user, plan
from tests.unit.test_062_documents import stadtfest


class OfferOptionsApiTests(ApiTestCase):
    """DOK-013: level of detail and validity in days when an offer is made; the default in the template."""

    def setUp(self) -> None:
        super().setUp()
        self.project = stadtfest().project
        self.url = f"{API}/projects/{self.project.pk}/documents"

    def test_an_offer_with_only_groups_valid_for_30_days(self) -> None:
        response = self.admin.post(self.url, {"kind": "offer", "detail": "groups", "validity_days": 30}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        body = response.json()
        self.assertEqual(
            (body["detail"], body["valid_until"], body["validity_days"], body["net_total"]),
            ("groups", "2027-03-31", 30, "1848.00"),
        )
        detail = self.admin.get(f"{API}/documents/{body['id']}").json()
        self.assertEqual((detail["detail"], detail["validity_days"]), ("groups", 30))
        plain = self.admin.post(self.url, {"kind": "offer"}, format="json").json()
        self.assertEqual((plain["detail"], plain["valid_until"], plain["validity_days"]), ("lines", "2027-03-15", 14))
        invoice = self.admin.post(self.url, {"kind": "order_confirmation"}, format="json").json()
        self.assertEqual((invoice["detail"], invoice["validity_days"]), ("lines", None))

    def test_date_and_days_must_agree(self) -> None:
        both = self.admin.post(
            self.url, {"kind": "offer", "valid_until": "2027-03-21", "validity_days": 20}, format="json"
        )
        self.assertEqual(both.status_code, 201, both.data)
        self.assert_error(
            self.admin.post(
                self.url, {"kind": "offer", "valid_until": "2027-03-21", "validity_days": 30}, format="json"
            ),
            400,
            "validation_error",
            "validity_days",
        )
        self.assert_error(
            self.admin.post(self.url, {"kind": "offer", "validity_days": -1}, format="json"),
            400,
            "validation_error",
            "validity_days",
        )

    def test_only_an_offer_shows_groups_only(self) -> None:
        self.assert_error(
            self.admin.post(self.url, {"kind": "order_confirmation", "detail": "groups"}, format="json"),
            400,
            "validation_error",
            "detail",
        )
        self.assert_error(
            self.admin.post(self.url, {"kind": "offer", "detail": "pages"}, format="json"),
            400,
            "validation_error",
            "detail",
        )

    def test_the_draft_follows_the_options(self) -> None:
        preview = self.admin.post(
            f"{self.url}/preview", {"kind": "offer", "detail": "groups", "validity_days": 7}, format="json"
        )
        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview.content.startswith(b"%PDF"))

    def test_the_default_validity_in_the_template_of_the_offer(self) -> None:
        templates = {entry["kind"]: entry for entry in self.admin.get(f"{API}/document-templates").json()}
        self.assertEqual(templates["offer"]["validity_days"], 14)
        self.assertIsNone(templates["invoice"]["validity_days"])
        changed = self.admin.patch(
            f"{API}/document-templates/{templates['offer']['id']}", {"validity_days": 30}, format="json"
        )
        self.assertEqual(changed.json()["validity_days"], 30)
        offer = self.admin.post(self.url, {"kind": "offer"}, format="json").json()
        self.assertEqual(offer["valid_until"], "2027-03-31")
        self.assert_error(
            self.admin.patch(
                f"{API}/document-templates/{templates['invoice']['id']}", {"validity_days": 30}, format="json"
            ),
            400,
            "validation_error",
            "validity_days",
        )
        self.assert_error(
            self.admin.patch(
                f"{API}/document-templates/{templates['offer']['id']}", {"validity_days": None}, format="json"
            ),
            400,
            "validation_error",
            "validity_days",
        )


class DeploymentPdfApiTests(ApiTestCase):
    """PRJ-081: ``GET /projects/{id}/deployment/pdf`` – the deployment view of the caller as PDF."""

    def setUp(self) -> None:
        super().setUp()
        self.project = stadtfest().project
        self.url = f"{API}/projects/{self.project.pk}/deployment/pdf"

    def test_planners_and_planned_crew_get_the_pdf(self) -> None:
        response = self.admin.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(f"Einsatzuebersicht-{self.project.number}.pdf", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF"))
        user = make_user("ben", roles=("Freie Kraft",))
        plan(self.project, "Bühne", make_person("Ben Braun", user=user), start=at(10, 8), end=at(10, 12))
        crew = self.client_of(user)
        self.assertTrue(crew.get(self.url).content.startswith(b"%PDF"))
        self.assertEqual(self.client_for("otto", "Freie Kraft").get(self.url).status_code, 404)
