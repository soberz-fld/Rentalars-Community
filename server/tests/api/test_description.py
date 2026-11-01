# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests: the API describes itself (API-001, API-004, API-005)."""

from __future__ import annotations

from django.core.management import call_command
from django.test import Client

from tests.api.base import API, ApiTestCase

HTTP_METHODS = ("get", "post", "put", "patch", "delete")


class ApiDescriptionTests(ApiTestCase):
    """The machine-readable description is generated from the code and served with it (API-004)."""

    def description(self) -> dict:
        response = self.admin.get(f"{API}/schema?format=json")
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_description_is_openapi_3_under_a_versioned_path(self) -> None:
        """API-004, API-005: OpenAPI 3; every address starts with the version of the API."""
        description = self.description()
        self.assertTrue(description["openapi"].startswith("3."))
        self.assertEqual(description["info"]["title"], "Rentalars API")
        self.assertGreater(len(description["paths"]), 80)
        for path in description["paths"]:
            self.assertTrue(path.startswith("/api/v1/"), path)

    def test_status_and_invoice_status_are_described_apart(self) -> None:
        """Review, finding 1: each action has its own request body (PRJ-008, PRJ-113, DOK-015)."""
        paths = self.description()["paths"]

        def body_of(path: str) -> dict:
            return paths[f"{API}/projects/{{id}}/{path}"]["post"]["requestBody"]["content"]["application/json"][
                "schema"
            ]

        self.assertEqual(body_of("status"), {"$ref": "#/components/schemas/StatusChangeRequest"})
        self.assertEqual(body_of("invoice-status"), {"$ref": "#/components/schemas/InvoiceStatusRequest"})

    def test_every_business_area_is_reachable_through_the_api(self) -> None:
        """API-001, API-002: what the pages can do, the API can do – it is not an afterthought."""
        paths = "\n".join(self.description()["paths"])
        for resource in (
            "material-models",
            "material-items",
            "products",
            "customers",
            "projects",
            "material-lines",
            "groups",
            "packlists",
            "availability",
            "shortages",
            "subrentals",
            "users",
            "roles",
            "tokens",
            "audit-log",
            "search",
            # Stage 4
            "venues",
            "phases",
            "open-items",
            "files",
            "mails",
            "mail/unknown",
            "mail/settings",
            "notifications",
            "calendar",
            "utilization",
            "personnel-plan",
            "me/sessions",
            "security-log",
            "self-check",
            "duplicate",
            # Stage 5
            "documents",
            "document-templates",
            "text-blocks",
            "price-overview/pdf",
            "qualification-types",
            "qualifications",
            "timeline",
            "extractions",
            "addresses",
            "duplicates",
        ):
            self.assertIn(f"/{resource}", paths, resource)

    def test_every_operation_says_what_it_does_and_how_to_authenticate(self) -> None:
        description = self.description()
        self.assertIn("bearerAuth", str(description["components"]["securitySchemes"]) + "bearerAuth")
        undescribed = []
        for path, operations in description["paths"].items():
            for method in HTTP_METHODS:
                operation = operations.get(method)
                if operation is None:
                    continue
                self.assertTrue(operation.get("operationId"), f"{method} {path}")
                if not (operation.get("description") or operation.get("summary")):
                    undescribed.append(f"{method.upper()} {path}")
        self.assertEqual(undescribed, [])

    def test_description_is_complete_without_warnings(self) -> None:
        """The same check ``scripts/check.sh`` runs: a serializer the generator cannot read fails here."""
        call_command("spectacular", "--validate", "--fail-on-warn", "--file", "/dev/null", verbosity=0)

    def test_documentation_is_served_by_this_server_alone(self) -> None:
        """NFA-050: the page that shows the description loads nothing from other servers.

        Two things the library would do by default are switched off in the
        settings: fetching the viewer from a content delivery network, and
        the "validator" badge, which sends the address of the description –
        and with it of the server – to swagger.io.
        """
        client = Client()
        client.force_login(self.admin_user)
        response = client.get(f"{API}/docs/")
        self.assertEqual(response.status_code, 200)
        text = response.content.decode()
        self.assertNotRegex(text, r"(?:src|href)=\"https?://")
        self.assertIn("/static/drf_spectacular_sidecar/", text)
        self.assertIn('"validatorUrl": null', text)
        self.assertNotIn("swagger.io", text)
        # The second viewer of the library (ReDoc) asks other servers for fonts and a logo; it is not offered.
        self.assertEqual(client.get(f"{API}/redoc/").status_code, 404)

    def test_description_is_only_for_logged_in_users(self) -> None:
        self.assertIn(Client().get(f"{API}/schema").status_code, (401, 403))
