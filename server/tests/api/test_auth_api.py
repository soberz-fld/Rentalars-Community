# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests: login, own profile, tokens, users and roles (AUT, API-006)."""

from __future__ import annotations

import datetime

from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from rentalars.accounts.models import ApiToken, Role, User
from rentalars.core.models import SystemSettings
from tests.api.base import API, ApiTestCase
from tests.helpers import PASSWORD, make_user


class LoginTests(ApiTestCase):
    """Session login with name and password (AUT-002, AUT-005)."""

    def test_login_with_username_starts_a_session(self) -> None:
        make_user("berta", roles=("Lager",))
        client = APIClient()
        response = client.post(f"{API}/auth/login", {"username": "berta", "password": PASSWORD}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["username"], "berta")
        self.assertEqual(response.data["roles"], ["Lager"])
        # The session cookie now authenticates further calls.
        self.assertEqual(client.get(f"{API}/me").status_code, 200)

    def test_login_with_email_address_works_too(self) -> None:
        make_user("berta")
        response = APIClient().post(
            f"{API}/auth/login", {"username": "berta@example.de", "password": PASSWORD}, format="json"
        )
        self.assertEqual(response.status_code, 200)

    def test_wrong_password_is_rejected_without_saying_which_part_was_wrong(self) -> None:
        make_user("berta")
        client = APIClient()
        wrong_password = client.post(f"{API}/auth/login", {"username": "berta", "password": "nope"}, format="json")
        unknown_name = client.post(f"{API}/auth/login", {"username": "nobody", "password": "nope"}, format="json")
        self.assert_error(wrong_password, 400, "invalid_credentials")
        self.assertEqual(wrong_password.json(), unknown_name.json())

    def test_too_many_failures_lock_the_name_for_a_while(self) -> None:
        """AUT-005: after the configured number of failures even the right password is refused."""
        make_user("berta")
        system_settings = SystemSettings.load()
        system_settings.login_max_attempts = 3
        system_settings.save()
        client = APIClient()
        for _attempt in range(3):
            client.post(f"{API}/auth/login", {"username": "berta", "password": "nope"}, format="json")
        response = client.post(f"{API}/auth/login", {"username": "berta", "password": PASSWORD}, format="json")
        self.assert_error(response, 429, "locked_out")

    def test_deactivated_user_cannot_log_in(self) -> None:
        user = make_user("berta")
        user.is_active = False
        user.save()
        response = APIClient().post(f"{API}/auth/login", {"username": "berta", "password": PASSWORD}, format="json")
        self.assert_error(response, 400, "invalid_credentials")

    def test_logout_ends_the_session(self) -> None:
        make_user("berta")
        client = APIClient()
        client.post(f"{API}/auth/login", {"username": "berta", "password": PASSWORD}, format="json")
        self.assertEqual(client.post(f"{API}/auth/logout").status_code, 204)
        self.assert_error(client.get(f"{API}/me"), 401, "not_authenticated")

    def test_password_reset_answers_the_same_for_known_and_unknown_addresses(self) -> None:
        """AUT-004: nobody can find out through this endpoint who has an account."""
        make_user("berta")
        known = APIClient().post(f"{API}/auth/password-reset", {"email": "berta@example.de"}, format="json")
        unknown = APIClient().post(f"{API}/auth/password-reset", {"email": "nobody@example.de"}, format="json")
        self.assertEqual(known.status_code, 204)
        self.assertEqual(unknown.status_code, 204)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["berta@example.de"])


class ProfileAndTokenTests(ApiTestCase):
    """Own profile and personal API tokens (AUT-021)."""

    def test_calls_without_credentials_are_refused_with_401(self) -> None:
        response = APIClient().get(f"{API}/projects")
        self.assert_error(response, 401, "not_authenticated")
        self.assertIn("Bearer", response["WWW-Authenticate"])

    def test_invalid_token_is_refused(self) -> None:
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer rl_this-is-not-a-token")
        self.assert_error(client.get(f"{API}/me"), 401, "not_authenticated")

    def test_me_lists_roles_and_effective_rights(self) -> None:
        client = self.client_for("luka", "Lager")
        profile = client.get(f"{API}/me").data
        self.assertEqual(profile["username"], "luka")
        self.assertEqual(profile["module_levels"]["material"], 2)  # AUT-036: create and edit, not delete
        self.assertEqual(profile["module_levels"]["customers"], 0)
        self.assertIn("purchase_prices", profile["special_rights"])
        self.assertNotIn("prices", profile["special_rights"])

    def test_token_is_shown_once_and_only_its_hash_is_stored(self) -> None:
        response = self.admin.post(f"{API}/tokens", {"name": "Lagerscanner"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        key = response.data["key"]
        self.assertTrue(key.startswith("rl_"))
        token = ApiToken.objects.get(pk=response.data["id"])
        self.assertNotEqual(token.key_hash, key)
        self.assertNotIn("key", self.admin.get(f"{API}/tokens").data["results"][0])

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {key}")
        self.assertEqual(client.get(f"{API}/me").data["username"], "admin")

    def test_revoked_token_stops_working_at_once(self) -> None:
        user = make_user("berta", roles=("Lager",))
        token, key = ApiToken.create_for_user(user, "old")
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {key}")
        self.assertEqual(client.get(f"{API}/me").status_code, 200)
        own = self.client_of(user)
        self.assertEqual(own.delete(f"{API}/tokens/{token.pk}").status_code, 204)
        self.assert_error(client.get(f"{API}/me"), 401, "not_authenticated")

    def test_expired_token_is_refused(self) -> None:
        user = make_user("berta")
        client = self.client_of(user, expires_at=timezone.now() - datetime.timedelta(minutes=1))
        self.assert_error(client.get(f"{API}/me"), 401, "not_authenticated")

    def test_read_only_token_can_read_but_not_write(self) -> None:
        """AUT-021: a token can be narrower than its user, never wider."""
        client = self.client_of(self.admin_user, read_only=True)
        self.assertEqual(client.get(f"{API}/customers").status_code, 200)
        self.assert_error(
            client.post(f"{API}/customers", {"name": "Neu GmbH"}, format="json"), 403, "permission_denied"
        )

    def test_token_limited_to_modules_cannot_reach_others(self) -> None:
        client = self.client_of(self.admin_user, allowed_modules=["material"])
        self.assertEqual(client.get(f"{API}/material-items").status_code, 200)
        self.assert_error(client.get(f"{API}/customers"), 403, "permission_denied")

    def test_users_only_see_their_own_tokens(self) -> None:
        berta = make_user("berta")
        ApiToken.create_for_user(berta, "bertas token")
        names = [row["name"] for row in self.admin.get(f"{API}/tokens").data["results"]]
        self.assertEqual(names, ["test"])


class UserAndRoleTests(ApiTestCase):
    """User accounts and roles (AUT-009 to AUT-012)."""

    def test_new_user_is_invited_by_mail_and_gets_no_password_from_the_admin(self) -> None:
        """AUT-011: the invitation carries a link for setting the password."""
        role = Role.objects.get(name="Lager")
        response = self.admin.post(
            f"{API}/users",
            {
                "username": "luka",
                "email": "luka@example.de",
                "first_name": "Luka",
                "last_name": "Lager",
                "roles": [role.pk],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(response.data["has_password"])
        self.assertNotIn("password", response.data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/password-reset/", mail.outbox[0].body)
        self.assertEqual(list(User.objects.get(username="luka").roles.all()), [role])

    def test_users_are_deactivated_not_deleted(self) -> None:
        """AUT-009: history must keep pointing at the account."""
        user = make_user("berta")
        self.assertEqual(self.admin.delete(f"{API}/users/{user.pk}").status_code, 405)
        response = self.admin.post(f"{API}/users/{user.pk}/deactivate")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_active"])
        self.assertTrue(self.admin.post(f"{API}/users/{user.pk}/activate").data["is_active"])

    def test_nobody_can_deactivate_their_own_account(self) -> None:
        response = self.admin.post(f"{API}/users/{self.admin_user.pk}/deactivate")
        self.assert_error(response, 400, "validation_error")

    def test_changing_roles_changes_the_rights_at_once(self) -> None:
        user = make_user("berta", roles=("Nur-Lesen",))
        client = self.client_of(user)
        self.assert_error(
            client.post(f"{API}/customers", {"name": "Neu GmbH"}, format="json"), 403, "permission_denied"
        )
        role = Role.objects.get(name="Projektleitung")
        self.assertEqual(
            self.admin.patch(f"{API}/users/{user.pk}", {"roles": [role.pk]}, format="json").status_code, 200
        )
        self.assertEqual(client.post(f"{API}/customers", {"name": "Neu GmbH"}, format="json").status_code, 201)

    def test_roles_are_freely_definable(self) -> None:
        """AUT-010."""
        response = self.admin.post(
            f"{API}/roles",
            {"name": "Werkstatt", "module_levels": {"material": 2}, "special_rights": ["purchase_prices"]},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        client = self.client_for("willi", "Werkstatt")
        self.assertEqual(client.get(f"{API}/material-items").status_code, 200)
        self.assert_error(client.get(f"{API}/projects"), 403, "permission_denied")

    def test_role_with_unknown_module_or_right_is_rejected(self) -> None:
        response = self.admin.post(f"{API}/roles", {"name": "Kaputt", "module_levels": {"nonsense": 2}}, format="json")
        self.assert_error(response, 400, "validation_error", "module_levels")
        response = self.admin.post(f"{API}/roles", {"name": "Kaputt", "special_rights": ["everything"]}, format="json")
        self.assert_error(response, 400, "validation_error", "special_rights")

    def test_role_in_use_cannot_be_deleted(self) -> None:
        make_user("berta", roles=("Lager",))
        role = Role.objects.get(name="Lager")
        self.assert_error(self.admin.delete(f"{API}/roles/{role.pk}"), 400, "validation_error")

    def test_user_administration_needs_the_administration_module(self) -> None:
        client = self.client_for("paula", "Projektleitung")
        self.assert_error(client.get(f"{API}/users"), 403, "permission_denied")
        self.assert_error(client.get(f"{API}/roles"), 403, "permission_denied")

    def test_permission_catalogue_marks_modules_of_later_stages(self) -> None:
        catalogue = self.admin.get(f"{API}/permissions").data
        modules = {entry["value"]: entry["available"] for entry in catalogue["modules"]}
        self.assertTrue(modules["projects"])
        # Stage 3 brought personnel and time tracking, stage 4 e-mail, and the reports (PRJ-115).
        self.assertTrue(modules["personnel"])
        self.assertTrue(modules["time_tracking"])
        self.assertTrue(modules["email"])
        self.assertTrue(modules["reports"])
        self.assertIn("prices", [entry["value"] for entry in catalogue["special_rights"]])
