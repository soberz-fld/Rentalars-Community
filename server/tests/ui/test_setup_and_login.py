# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser tests: first-run setup, login, lockout, password reset (NFA-033, AUT-001 to AUT-006)."""

from __future__ import annotations

import io
import re

from django.conf import settings
from django.core import mail
from django.core.management import call_command
from django.test import Client, override_settings
from django.urls import reverse

from rentalars.accounts.models import User
from rentalars.core.middleware import SetupRequiredMiddleware
from rentalars.core.models import CompanyProfile, NumberRange, NumberRangeKey, SystemSettings
from rentalars.masterdata.models import TaxRate
from rentalars.products.models import Product
from rentalars.projects.models import Project
from tests.helpers import PASSWORD, RentalarsTestCase, make_user
from tests.ui.base import form_data

SETUP_ANSWERS = {
    "company_name": "Lichtwerk Veranstaltungstechnik",
    "street": "Am Hafen 7",
    "postal_code": "12345",
    "city": "Musterstadt",
    "username": "anna",
    "first_name": "Anna",
    "last_name": "Admin",
    "email": "anna@example.de",
    "password": "Sehr-geheimes-Passwort-42",
    "password_repeat": "Sehr-geheimes-Passwort-42",
}


class SetupTests(RentalarsTestCase):
    """The first-run setup in the browser (NFA-033)."""

    def setUp(self) -> None:
        super().setUp()
        system_settings = SystemSettings.load()
        system_settings.setup_completed = False
        system_settings.save()
        SetupRequiredMiddleware.reset()
        self.addCleanup(SetupRequiredMiddleware.reset)
        # The one-time link from the installation; the browser keeps it for the following pages.
        self.token = system_settings.new_setup_token()
        self.client.get(reverse("core:setup"), {"token": self.token})

    def test_every_page_leads_to_the_setup_until_it_is_done(self) -> None:
        for address in ("/", "/login/", "/projects/"):
            self.assertRedirects(self.client.get(address), reverse("core:setup"), fetch_redirect_response=False)
        with self.assertLogs("django.request", "ERROR"):
            api = self.client.get("/api/v1/projects")
        self.assertEqual(api.status_code, 503)
        self.assertEqual(api.json()["error"]["code"], "setup_required")

    def test_setup_creates_company_administrator_and_number_ranges(self) -> None:
        page = self.client.get(reverse("core:setup"))
        self.assertEqual(page.status_code, 200)
        data = form_data(page, **SETUP_ANSWERS, project_next=42, customer_next=20001, default_tax_rate="19")

        response = self.client.post(reverse("core:setup"), data)

        self.assertRedirects(response, reverse("core:home"))
        self.assertEqual(CompanyProfile.load().name, "Lichtwerk Veranstaltungstechnik")
        administrator = User.objects.get(username="anna")
        self.assertTrue(administrator.is_superuser)
        self.assertTrue(administrator.check_password("Sehr-geheimes-Passwort-42"))
        self.assertEqual(list(administrator.roles.values_list("name", flat=True)), ["Administrator"])
        self.assertEqual(NumberRange.objects.get(key=NumberRangeKey.PROJECT).next_value, 42)
        self.assertEqual(NumberRange.objects.get(key=NumberRangeKey.CUSTOMER).next_value, 20001)
        self.assertTrue(SystemSettings.load().setup_completed)
        # The administrator is logged in at once and lands on the start page.
        self.assertEqual(self.client.get(reverse("core:home")).status_code, 200)
        self.assertFalse(Project.objects.exists())

    def test_setup_can_only_run_once(self) -> None:
        self.client.post(reverse("core:setup"), form_data(self.client.get(reverse("core:setup")), **SETUP_ANSWERS))
        stranger = Client()
        response = stranger.post(
            reverse("core:setup"), {**SETUP_ANSWERS, "username": "mallory", "email": "m@example.de"}
        )
        self.assertFalse(User.objects.filter(username="mallory").exists())
        self.assertIn(response.status_code, (302, 403, 404))

    def test_weak_or_mistyped_password_is_rejected(self) -> None:
        page = self.client.get(reverse("core:setup"))
        short = self.client.post(
            reverse("core:setup"), form_data(page, **{**SETUP_ANSWERS, "password": "kurz", "password_repeat": "kurz"})
        )
        self.assertEqual(short.status_code, 200)
        mistyped = self.client.post(
            reverse("core:setup"), form_data(page, **{**SETUP_ANSWERS, "password_repeat": "anders-getippt-99"})
        )
        self.assertEqual(mistyped.status_code, 200)
        self.assertFalse(User.objects.exists())
        self.assertFalse(SystemSettings.load().setup_completed)

    def test_sample_data_and_other_tax_rate_on_request(self) -> None:
        page = self.client.get(reverse("core:setup"))
        self.client.post(
            reverse("core:setup"), form_data(page, **SETUP_ANSWERS, with_demo_data="on", default_tax_rate="7")
        )
        self.assertTrue(Project.objects.exists())
        self.assertTrue(Product.objects.filter(article_number="K-005").exists())
        self.assertEqual(str(TaxRate.get_default().rate), "7.00")

    def test_on_a_server_the_setup_needs_the_one_time_link(self) -> None:
        """Whoever reaches the address first must not become administrator."""
        output = io.StringIO()
        call_command("prepare_setup", stdout=output)
        link = output.getvalue().strip()
        token = re.search(r"token=([\w-]+)", link).group(1)  # type: ignore[union-attr]

        locked = self.client.get(reverse("core:setup"))
        self.assertNotIn(b'name="company_name"', locked.content)
        refused = self.client.post(reverse("core:setup"), SETUP_ANSWERS)
        self.assertFalse(User.objects.exists(), refused.status_code)
        wrong = self.client.get(reverse("core:setup"), {"token": "falsch"})
        self.assertNotIn(b'name="company_name"', wrong.content)

        page = self.client.get(reverse("core:setup"), {"token": token})
        self.assertIn(b'name="company_name"', page.content)
        done = self.client.post(f"{reverse('core:setup')}?token={token}", form_data(page, **SETUP_ANSWERS))
        self.assertRedirects(done, reverse("core:home"))
        self.assertEqual(SystemSettings.load().setup_token, "")

        again = io.StringIO()
        call_command("prepare_setup", stdout=again)
        self.assertNotIn("token=", again.getvalue())


class SetupWithoutKeyTests(RentalarsTestCase):
    """NFA-064: a setup page without a key is closed, not open to whoever comes first."""

    def setUp(self) -> None:
        super().setUp()
        system_settings = SystemSettings.load()
        system_settings.setup_completed = False
        system_settings.setup_token = ""
        system_settings.save()
        SetupRequiredMiddleware.reset()
        self.addCleanup(SetupRequiredMiddleware.reset)

    @override_settings(SETUP_OPEN_WITHOUT_TOKEN=False)
    def test_on_a_server_nobody_gets_in_before_the_key_exists(self) -> None:
        """The moment between "the web server answers" and "the installation has made the key"."""
        for attempt in ({}, {"token": ""}, {"token": "geraten"}, {"token": "None"}):
            with self.subTest(query=attempt):
                page = self.client.get(reverse("core:setup"), attempt)
                self.assertEqual(page.status_code, 403)
                self.assertNotIn(b'name="company_name"', page.content)
                self.assertIn(b"sudo rentalars prepare_setup", page.content)
        taken = self.client.post(reverse("core:setup"), SETUP_ANSWERS)
        self.assertEqual(taken.status_code, 403)
        self.assertEqual(self.client.post(f"{reverse('core:setup')}?token=", SETUP_ANSWERS).status_code, 403)
        self.assertFalse(User.objects.exists())
        self.assertFalse(SystemSettings.load().setup_completed)

    @override_settings(SETUP_OPEN_WITHOUT_TOKEN=False)
    def test_a_key_with_unusual_characters_is_simply_wrong(self) -> None:
        SystemSettings.load().new_setup_token()
        for attempt in ("schlüssel-mit-ümläuten", "x" * 5000, "\x00"):
            with self.subTest(token=attempt[:12]):
                self.assertEqual(self.client.get(reverse("core:setup"), {"token": attempt}).status_code, 403)

    @override_settings(SETUP_OPEN_WITHOUT_TOKEN=True)
    def test_only_a_developers_machine_is_open_without_a_key(self) -> None:
        self.assertIn(b'name="company_name"', self.client.get(reverse("core:setup")).content)

    def test_the_door_is_only_open_in_the_development_environment(self) -> None:
        self.assertEqual(settings.SETUP_OPEN_WITHOUT_TOKEN, settings.RENTALARS_ENVIRONMENT == "development")


class LoginTests(RentalarsTestCase):
    """Login, logout and lockout in the browser (AUT-001 to AUT-006)."""

    def test_everything_needs_a_login(self) -> None:
        for address in ("/", "/projects/", "/material/", "/administration/", "/api/v1/docs/"):
            response = self.client.get(address)
            self.assertIn(response.status_code, (302, 401, 403), address)
            if response.status_code == 302:
                self.assertIn("/login/", response["Location"])

    def test_login_with_name_or_email_and_logout(self) -> None:
        make_user("berta")
        for identifier in ("berta", "berta@example.de", "BERTA@Example.de"):
            client = Client()
            response = client.post(reverse("accounts:login"), {"username": identifier, "password": PASSWORD})
            self.assertRedirects(response, reverse("core:home"), msg_prefix=identifier)
            self.assertEqual(client.post(reverse("accounts:logout")).status_code, 302)
            self.assertEqual(client.get(reverse("core:home")).status_code, 302)

    def test_login_returns_to_the_page_that_was_asked_for(self) -> None:
        make_user("berta", roles=("Lager",))
        response = self.client.post(
            f"{reverse('accounts:login')}?next=/material/", {"username": "berta", "password": PASSWORD}
        )
        self.assertRedirects(response, "/material/")
        outside = self.client.post(
            f"{reverse('accounts:login')}?next=https://evil.example/", {"username": "berta", "password": PASSWORD}
        )
        self.assertRedirects(outside, reverse("core:home"))

    def test_wrong_password_shows_one_neutral_message(self) -> None:
        make_user("berta")
        wrong = self.client.post(reverse("accounts:login"), {"username": "berta", "password": "nope"})
        unknown = self.client.post(reverse("accounts:login"), {"username": "nobody", "password": "nope"})
        self.assertEqual(wrong.status_code, 200)
        self.assertEqual(
            [str(error) for error in wrong.context["form"].non_field_errors()],
            [str(error) for error in unknown.context["form"].non_field_errors()],
        )

    def test_lockout_after_too_many_failures(self) -> None:
        """AUT-005."""
        make_user("berta")
        system_settings = SystemSettings.load()
        system_settings.login_max_attempts = 3
        system_settings.save()
        for _attempt in range(3):
            self.client.post(reverse("accounts:login"), {"username": "berta", "password": "nope"})
        locked = self.client.post(reverse("accounts:login"), {"username": "berta", "password": PASSWORD})
        self.assertEqual(locked.status_code, 200)
        self.assertEqual(self.client.get(reverse("core:home")).status_code, 302)

    def test_password_reset_by_mail(self) -> None:
        """AUT-004: the link works once and the old password stops working."""
        user = make_user("berta")
        self.client.post(reverse("accounts:password_reset"), {"email": "berta@example.de"})
        self.assertEqual(len(mail.outbox), 1)
        link = re.search(r"https?://\S+/password-reset/\S+", mail.outbox[0].body).group(0)  # type: ignore[union-attr]
        path = "/" + link.split("/", 3)[3]

        page = self.client.get(path, follow=True)
        self.assertEqual(page.status_code, 200)
        new_password = "Ein-ganz-neues-Passwort-77"
        done = self.client.post(
            page.redirect_chain[-1][0], {"new_password1": new_password, "new_password2": new_password}
        )
        self.assertRedirects(done, reverse("accounts:password_reset_complete"))
        user.refresh_from_db()
        self.assertTrue(user.check_password(new_password))
        self.assertFalse(user.check_password(PASSWORD))
        # The link cannot be used a second time.
        self.assertNotIn(b"new_password1", self.client.get(path, follow=True).content)

    def test_password_reset_does_not_reveal_unknown_addresses(self) -> None:
        response = self.client.post(reverse("accounts:password_reset"), {"email": "nobody@example.de"})
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_new_password_must_follow_the_password_rules(self) -> None:
        """AUT-003."""
        make_user("berta")
        self.client.post(reverse("accounts:password_reset"), {"email": "berta@example.de"})
        link = re.search(r"https?://\S+/password-reset/\S+", mail.outbox[0].body).group(0)  # type: ignore[union-attr]
        page = self.client.get("/" + link.split("/", 3)[3], follow=True)
        weak = self.client.post(page.redirect_chain[-1][0], {"new_password1": "kurz", "new_password2": "kurz"})
        self.assertEqual(weak.status_code, 200)
        self.assertTrue(weak.context["form"].errors)

    def test_pages_send_the_security_headers(self) -> None:
        """NFA-006: scripts only from the own server, no framing by other sites."""
        response = self.client.get(reverse("accounts:login"))
        policy = response["Content-Security-Policy"]
        self.assertIn("script-src 'self'", policy)
        self.assertNotIn("unsafe-inline", policy.split("script-src")[1].split(";")[0])
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
