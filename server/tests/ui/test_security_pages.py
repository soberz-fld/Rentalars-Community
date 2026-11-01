# SPDX-License-Identifier: GPL-3.0-or-later
"""Two-factor login, sessions, idle timeout and the security log in the browser.

AUT-006, AUT-008, AUT-022, NFA-049.
"""

from __future__ import annotations

import datetime
import re

from django.test import Client
from django.utils import timezone

from rentalars.accounts import twofactor
from rentalars.accounts.models import Role, SecurityEvent, User, UserSession
from rentalars.core.models import SystemSettings
from tests.helpers import PASSWORD, make_user, set_clock
from tests.ui.base import UiTestCase


def secret_from_page(text: str) -> str:
    """The key shown under the QR code, for people who cannot scan."""
    match = re.search(r'<p class="secret">([A-Z2-7 ]+)</p>', text)
    assert match is not None, "no key on the page"
    return match.group(1).replace(" ", "")


class TwoFactorPageTests(UiTestCase):
    """AUT-006: set up with the app, log in with a code, recovery codes, switch off."""

    def setUp(self) -> None:
        super().setUp()
        self.ben = make_user("ben")
        self.browser = self.browser_of(self.ben)

    def set_up(self) -> tuple[str, list[str]]:
        page = self.browser.get("/account/two-factor/")
        text = self.assert_ok(page)
        self.assertIn("<svg", text)  # the QR code, made on the server (NFA-050)
        secret = secret_from_page(text)
        wrong = self.browser.post("/account/two-factor/", {"code": "123456"})
        self.assertIn("Der Code passt nicht", wrong.content.decode())
        response = self.browser.post(
            "/account/two-factor/", {"code": twofactor.code_at(secret, twofactor.current_step())}
        )
        codes = re.findall(r"<li>([a-z0-9]{4}-[a-z0-9]{4})</li>", response.content.decode())
        self.assertEqual(len(codes), 10)
        return secret, codes

    def login(self, client: Client) -> object:
        return client.post("/login/", {"username": "ben", "password": PASSWORD})

    def test_set_up_and_log_in_with_a_code(self) -> None:
        secret, _codes = self.set_up()
        self.ben.refresh_from_db()
        self.assertTrue(self.ben.has_two_factor)
        self.assertNotIn(secret, self.ben.totp_secret_encrypted)

        client = Client()
        response = self.login(client)
        self.assertEqual(response["Location"], "/login/code/")
        self.assertEqual(client.get("/").status_code, 302)  # not logged in yet
        code = twofactor.code_at(secret, twofactor.current_step() + 1)
        response = client.post("/login/code/", {"code": code})
        self.assertEqual(response["Location"], "/")
        self.assertEqual(client.get("/").status_code, 200)

    def test_a_recovery_code_works_once(self) -> None:
        _secret, codes = self.set_up()
        client = Client()
        self.login(client)
        self.assertEqual(client.post("/login/code/", {"code": codes[0].upper()})["Location"], "/")
        other = Client()
        self.login(other)
        self.assertEqual(other.post("/login/code/", {"code": codes[0]}).status_code, 200)  # refused
        self.assertTrue(SecurityEvent.objects.filter(kind="recovery_code").exists())

    def test_too_many_wrong_codes_end_the_attempt(self) -> None:
        self.set_up()
        client = Client()
        self.login(client)
        for _attempt in range(twofactor.MAX_CODE_ATTEMPTS - 1):
            self.assertEqual(client.post("/login/code/", {"code": "000000"}).status_code, 200)
        response = client.post("/login/code/", {"code": "000000"})
        self.assertEqual(response["Location"], "/login/")
        self.assertEqual(SecurityEvent.objects.filter(kind="2fa_failed").count(), 5)

    def test_a_login_by_e_mail_address_clears_the_count_of_that_name(self) -> None:
        """AUT-005: the success counts for the name as typed, as the failed passwords did."""
        from rentalars.accounts.models import LoginAttempt

        secret, _codes = self.set_up()
        client = Client()
        typed = self.ben.email
        self.assertTrue(typed)
        client.post("/login/", {"username": typed, "password": PASSWORD})
        right = twofactor.code_at(secret, twofactor.current_step() + 1)
        self.assertEqual(client.post("/login/code/", {"code": right})["Location"], "/")
        names = set(LoginAttempt.objects.filter(successful=True).values_list("identifier", flat=True))
        self.assertEqual(names, {self.ben.username.lower(), typed.lower()})

    def test_new_sessions_do_not_give_new_guesses(self) -> None:
        """AUT-005: the wrong codes are counted for the name, not only for the session."""
        secret, _codes = self.set_up()
        for _round in range(twofactor.MAX_CODE_ATTEMPTS):
            client = Client()
            self.login(client)
            client.post("/login/code/", {"code": "000000"})
        client = Client()
        self.login(client)
        right = twofactor.code_at(secret, twofactor.current_step() + 1)
        response = client.post("/login/code/", {"code": right})
        self.assertEqual(response["Location"], "/login/")  # locked out, even with the right code

    def test_switch_off_with_the_password(self) -> None:
        self.set_up()
        self.browser.post("/account/two-factor/off/", {"password": "wrong"})
        self.ben.refresh_from_db()
        self.assertTrue(self.ben.has_two_factor)
        self.browser.post("/account/two-factor/off/", {"password": PASSWORD})
        self.ben.refresh_from_db()
        self.assertFalse(self.ben.has_two_factor)

    def test_administrators_reset_it_for_a_lost_phone(self) -> None:
        self.set_up()
        response = self.client.post(f"/administration/users/{self.ben.pk}/two-factor/reset/", follow=True)
        self.assertIn("ist ausgeschaltet", " ".join(self.messages_of(response)))
        self.ben.refresh_from_db()
        self.assertFalse(self.ben.has_two_factor)

    def test_a_role_requires_it(self) -> None:
        """Whoever must use it can do nothing else until it is set up."""
        role = Role.objects.create(name="Streng", requires_two_factor=True)
        anna = make_user("anna", roles=(role.name,))
        client = Client()
        client.post("/login/", {"username": "anna", "password": PASSWORD})
        self.assertEqual(client.get("/projects/")["Location"], "/account/two-factor/")
        self.assertIn("Deine Rolle schreibt", self.assert_ok(client.get("/account/two-factor/")))
        self.assertEqual(client.post("/account/two-factor/off/", {"password": PASSWORD}).status_code, 302)
        anna.refresh_from_db()
        self.assertFalse(anna.has_two_factor)

    def test_the_setting_for_administrators(self) -> None:
        """NFA-049: two-factor login can be required for everybody who administers."""
        settings = SystemSettings.load()
        settings.two_factor_for_administrators = True
        settings.save()
        client = Client()
        client.post("/login/", {"username": "admin", "password": PASSWORD})
        self.assertEqual(client.get("/administration/")["Location"], "/account/two-factor/")
        self.assertEqual(self.browser.get("/account/").status_code, 200)  # ben administers nothing


class SessionPageTests(UiTestCase):
    """AUT-008: sessions end after inactivity, and can be ended from elsewhere."""

    def test_idle_sessions_end(self) -> None:
        settings = SystemSettings.load()
        settings.session_idle_minutes = 30
        settings.save()
        ben = make_user("ben")
        client = Client()
        client.post("/login/", {"username": "ben", "password": PASSWORD})
        self.assertEqual(client.get("/").status_code, 200)
        set_clock(timezone.now() + datetime.timedelta(minutes=29))
        self.assertEqual(client.get("/").status_code, 200)
        set_clock(timezone.now() + datetime.timedelta(minutes=31))
        response = client.get("/projects/", follow=True)
        self.assertEqual(response.redirect_chain[0][0], "/login/?next=/projects/")
        self.assertIn("nach einer Zeit ohne Aktivität abgemeldet", " ".join(self.messages_of(response)))
        self.assertTrue(SecurityEvent.objects.filter(kind="timeout", user=ben).exists())

    def test_list_and_end_sessions(self) -> None:
        ben = make_user("ben")
        laptop, phone = Client(), Client()
        laptop.force_login(ben)
        phone.force_login(ben)
        text = self.assert_ok(laptop.get("/account/sessions/"))
        self.assertIn("dieser Browser", text)
        phone_session = UserSession.objects.get(session_key=phone.session.session_key)
        laptop.post("/account/sessions/", {"session": phone_session.pk})
        self.assertEqual(phone.get("/").status_code, 302)
        third = Client()
        third.force_login(ben)
        laptop.post("/account/sessions/", {"all": "1"})
        self.assertEqual(third.get("/").status_code, 302)
        self.assertEqual(laptop.get("/").status_code, 200)

    def test_the_current_session_is_not_ended_from_the_list(self) -> None:
        ben = make_user("ben")
        client = Client()
        client.force_login(ben)
        own = UserSession.objects.get(user=ben)
        response = client.post("/account/sessions/", {"session": own.pk}, follow=True)
        self.assertIn("Melde dich stattdessen ab.", " ".join(self.messages_of(response)))


class SecurityLogPageTests(UiTestCase):
    """AUT-022: the security log for administrators."""

    def test_the_log_shows_logins_and_failures(self) -> None:
        make_user("ben")
        Client().post("/login/", {"username": "ben", "password": "falsch"})
        Client().post("/login/", {"username": "ben", "password": PASSWORD})
        text = self.assert_ok(self.client.get("/administration/security-log/"))
        self.assertIn("Anmeldung fehlgeschlagen", text)
        filtered = self.assert_ok(self.client.get("/administration/security-log/", {"kind": "login_failed"}))
        self.assertNotIn("<td>angemeldet</td>", filtered)
        self.assertEqual(
            self.browser_for("paula", "Projektleitung").get("/administration/security-log/").status_code, 403
        )

    def test_password_changes_are_logged(self) -> None:
        ben = make_user("ben")
        browser = self.browser_of(ben)
        browser.post(
            "/account/",
            {
                "form": "password",
                "old_password": PASSWORD,
                "new_password1": "neu-und-lang-123",
                "new_password2": "neu-und-lang-123",
            },
        )
        self.assertTrue(SecurityEvent.objects.filter(kind="password_changed", user=ben).exists())
        self.assertTrue(User.objects.get(pk=ben.pk).check_password("neu-und-lang-123"))
