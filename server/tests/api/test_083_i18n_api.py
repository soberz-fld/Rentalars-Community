# SPDX-License-Identifier: GPL-3.0-or-later
"""API, area "i18n": the language of a user and of the documents, and errors in the caller's language
(UIX-029).
"""

from __future__ import annotations

from rentalars.accounts.models import User
from rentalars.core.models import CompanyProfile
from tests.api.base import API, ApiTestCase
from tests.helpers import make_user


class OwnLanguageApiTests(ApiTestCase):
    """UIX-029: ``/me`` names and changes the own language."""

    def test_read_and_change(self) -> None:
        me = self.admin.get(f"{API}/me").json()
        self.assertEqual((me["language"], me["effective_language"]), ("", "de"))
        response = self.admin.patch(f"{API}/me", {"language": "en"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()["language"], response.json()["effective_language"]), ("en", "en"))
        self.assertEqual(User.objects.get(pk=self.admin_user.pk).language, "en")
        self.assertEqual(self.admin.patch(f"{API}/me", {"language": ""}, format="json").json()["language"], "")

    def test_refused(self) -> None:
        self.assert_error(
            self.admin.patch(f"{API}/me", {"language": "fr"}, format="json"), 400, "validation_error", "language"
        )
        self.assert_error(
            self.admin.patch(f"{API}/me", {"username": "x"}, format="json"), 400, "validation_error", "username"
        )
        reader = self.client_of(make_user("rita"), read_only=True)
        self.assert_error(reader.patch(f"{API}/me", {"language": "en"}, format="json"), 403, "permission_denied")


class ErrorLanguageTests(ApiTestCase):
    """UIX-029: error messages in the caller's language – the user's choice, else Accept-Language."""

    def test_the_users_choice(self) -> None:
        user = make_user("eve", superuser=True)
        user.language = "en"
        user.save()
        client = self.client_of(user)
        error = self.assert_error(client.get(f"{API}/projects/999999", HTTP_ACCEPT_LANGUAGE="de"), 404, "not_found")
        self.assertEqual(error["message"], "The requested record does not exist.")

    def test_accept_language_without_a_choice(self) -> None:
        error = self.assert_error(
            self.admin.get(f"{API}/projects/999999", HTTP_ACCEPT_LANGUAGE="en-GB"), 404, "not_found"
        )
        self.assertEqual(error["message"], "The requested record does not exist.")
        error = self.assert_error(
            self.admin.get(f"{API}/projects/999999", HTTP_ACCEPT_LANGUAGE="de-DE"), 404, "not_found"
        )
        self.assertEqual(error["message"], "Den angeforderten Datensatz gibt es nicht.")
        error = self.assert_error(self.admin.get(f"{API}/projects/999999"), 404, "not_found")
        self.assertEqual(error["message"], "Den angeforderten Datensatz gibt es nicht.")  # the installation's

    def test_validation_messages(self) -> None:
        response = self.admin.post(f"{API}/customers", {"name": ""}, format="json", HTTP_ACCEPT_LANGUAGE="en")
        error = self.assert_error(response, 400, "validation_error")
        self.assertEqual(error["message"], "The input is invalid.")

    def test_invalid_token_in_the_browsers_language(self) -> None:
        from rest_framework.test import APIClient

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer rl_nothing")
        error = self.assert_error(client.get(f"{API}/me", HTTP_ACCEPT_LANGUAGE="en"), 401, "not_authenticated")
        self.assertIn("token", error["message"].lower())


class UserAndCompanyLanguageApiTests(ApiTestCase):
    """UIX-029: the language of a user in ``/users``; the language of the documents in ``/settings``."""

    def test_users(self) -> None:
        response = self.admin.post(
            f"{API}/users", {"username": "kim", "email": "kim@example.com", "language": "en"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["language"], "en")
        user = User.objects.get(username="kim")
        self.assertEqual(user.language, "en")
        response = self.admin.patch(f"{API}/users/{user.pk}", {"language": "de"}, format="json")
        self.assertEqual(response.json()["language"], "de")
        self.assert_error(
            self.admin.patch(f"{API}/users/{user.pk}", {"language": "fr"}, format="json"),
            400,
            "validation_error",
            "language",
        )

    def test_document_language(self) -> None:
        self.assertEqual(self.admin.get(f"{API}/settings").json()["company"]["document_language"], "de")
        response = self.admin.patch(f"{API}/settings", {"company": {"document_language": "en"}}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(CompanyProfile.load().document_language, "en")
