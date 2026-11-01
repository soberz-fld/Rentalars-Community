# SPDX-License-Identifier: GPL-3.0-or-later
"""Base class for the API tests (API-014).

Every test talks to the API the way another program would: with a personal
token in the ``Authorization`` header and JSON in both directions. Nothing in
these tests calls a service directly to *do* the thing under test; services
are only used to prepare data.
"""

from __future__ import annotations

from typing import Any

from rest_framework.test import APIClient

from rentalars.accounts.models import ApiToken, User
from tests.helpers import RentalarsTestCase, make_user

API = "/api/v1"


class ApiTestCase(RentalarsTestCase):
    """Provides clients for typical users.

    ``self.admin`` is a client of an administrator who may do everything.
    Other users are created with :meth:`client_for`.
    """

    def setUp(self) -> None:
        super().setUp()
        self.admin_user = make_user("admin", superuser=True)
        self.admin = self.client_of(self.admin_user)

    def client_of(self, user: User, **token_options: Any) -> APIClient:
        """Return a client that authenticates with a fresh token of ``user``."""
        _token, key = ApiToken.create_for_user(user, "test", **token_options)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {key}")
        return client

    def client_for(self, username: str, *roles: str, **token_options: Any) -> APIClient:
        """Create a user with the named roles and return a client for that user."""
        return self.client_of(make_user(username, roles=roles), **token_options)

    def assert_error(self, response: Any, status: int, code: str, field: str | None = None) -> dict[str, Any]:
        """Check status and the uniform error format (API-008); return the error body."""
        self.assertEqual(response.status_code, status, getattr(response, "data", response.content))
        error = response.json()["error"]
        self.assertEqual(error["code"], code)
        self.assertIsInstance(error["message"], str)
        self.assertTrue(error["message"])
        if field is not None:
            self.assertIn(field, error["fields"])
            first = error["fields"][field][0]
            self.assertIn("code", first)
            self.assertIn("message", first)
        return error
