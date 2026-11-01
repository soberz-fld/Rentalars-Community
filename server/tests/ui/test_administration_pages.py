# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser tests: start page, search, own account, users, roles, settings, change log (ADM, AUT, UIX)."""

from __future__ import annotations

import datetime
import io
import tempfile

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from rentalars.accounts.models import ApiToken, LoginAttempt, Role, User
from rentalars.core.models import CompanyProfile, NumberRange, NumberRangeKey, SystemSettings
from rentalars.customers.models import Customer
from rentalars.projects.models import Project
from tests.helpers import (
    PASSWORD,
    add_line,
    make_customer,
    make_item,
    make_model,
    make_product,
    make_project,
    make_stock,
    make_user,
)
from tests.ui.base import UiTestCase, form_data


def png(width: int = 40, height: int = 20) -> bytes:
    """A small valid PNG image."""
    stream = io.BytesIO()
    Image.new("RGB", (width, height), "#ffc20e").save(stream, "PNG")
    return stream.getvalue()


class HomeAndSearchTests(UiTestCase):
    """Start page and global search (UIX-001, UIX-002)."""

    def test_start_page_shows_what_comes_up_and_what_is_out(self) -> None:
        now = timezone.now()
        make_project("Stadtfest", start=now + datetime.timedelta(days=2), end=now + datetime.timedelta(days=4))
        out = make_project("Jazznacht", start=now - datetime.timedelta(days=1), end=now + datetime.timedelta(days=1))
        Project.objects.filter(pk=out.pk).update(status="out")

        page = self.assert_ok(self.client.get(reverse("core:home")))

        self.assertIn("Stadtfest", page)
        self.assertIn("Jazznacht", page)
        self.assertLess(page.index("Steht an"), page.index("Stadtfest"))
        self.assertLess(page.index("Gerade unterwegs"), page.index("Jazznacht", page.index("Gerade unterwegs")))

    def test_search_finds_projects_customers_products_and_material(self) -> None:
        customer = make_customer("Kabelwerk Nord")
        make_project("Kabelsalat Open Air", customer=customer)
        cable = make_product("K-005", "Kabel XLR 5 m")
        make_item(make_model("Kabeltrommel 50 m", cable), 77, serial_number="KT-1")

        page = self.assert_ok(self.client.get(reverse("core:search"), {"q": "kabel"}))
        for text in ("Kabelwerk Nord", "Kabelsalat Open Air", "K-005", "0077"):
            self.assertIn(text, page)
        by_id = self.assert_ok(self.client.get(reverse("core:search"), {"q": "0077"}))
        self.assertIn("Kabeltrommel 50 m", by_id)
        by_serial = self.assert_ok(self.client.get(reverse("core:search"), {"q": "KT-1"}))
        self.assertIn("0077", by_serial)
        nothing = self.assert_ok(self.client.get(reverse("core:search"), {"q": "gibtesnicht"}))
        self.assertIn("Nichts gefunden", nothing)

    def test_search_leaves_out_modules_the_user_may_not_read(self) -> None:
        make_customer("Kabelwerk Nord")
        make_product("K-005", "Kabel XLR 5 m")
        warehouse = self.browser_for("luka", "Lager")
        page = self.assert_ok(warehouse.get(reverse("core:search"), {"q": "kabel"}))
        self.assertIn("K-005", page)
        self.assertNotIn("Kabelwerk Nord", page)

    def test_shortage_page_lists_shortages_and_subrentals(self) -> None:
        """PRJ-057."""
        cable = make_stock("K-005", 2, "XLR-Kabel 5 m")
        project = make_project("Stadtfest")
        add_line(project, cable, 5)
        page = self.assert_ok(self.client.get(reverse("availability:shortages")))
        self.assertIn("Stadtfest", page)
        self.assertIn("K-005", page)
        self.assertIn("Offene Fehlbestände", page)

    def test_unknown_address_shows_the_friendly_404_page(self) -> None:
        response = self.client.get("/gibt/es/nicht/")
        self.assertEqual(response.status_code, 404)
        self.assertIn("Seite nicht gefunden", response.content.decode())


class AccountPageTests(UiTestCase):
    """The own account: password and API tokens (AUT-003, AUT-021)."""

    def test_change_password(self) -> None:
        user = make_user("berta")
        browser = self.browser_of(user)
        new_password = "Ein-ganz-neues-Passwort-77"
        response = browser.post(
            reverse("accounts:account"),
            {
                "form": "password",
                "old_password": PASSWORD,
                "new_password1": new_password,
                "new_password2": new_password,
            },
        )
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.check_password(new_password))
        # The browser that changed the password stays logged in.
        self.assertEqual(browser.get(reverse("accounts:account")).status_code, 200)

    def test_token_is_shown_once_and_can_be_revoked(self) -> None:
        response = self.client.post(
            reverse("accounts:account"), {"form": "token", "name": "Lagerscanner", "read_only": "on"}, follow=True
        )
        page = self.assert_ok(response)
        token = ApiToken.objects.get(user=self.admin_user)
        self.assertTrue(token.read_only)
        self.assertIn(token.key_prefix, page)
        self.assertIn("rl_", page)
        again = self.assert_ok(self.client.get(reverse("accounts:account")))
        self.assertNotIn("kopiere es jetzt", again)

        self.client.post(reverse("accounts:token_revoke", args=[token.pk]))
        token.refresh_from_db()
        self.assertIsNotNone(token.revoked_at)

    def test_tokens_of_other_users_cannot_be_revoked(self) -> None:
        other, _key = ApiToken.create_for_user(make_user("berta"), "fremd")
        response = self.client.post(reverse("accounts:token_revoke", args=[other.pk]))
        self.assertEqual(response.status_code, 404)


class UserAndRolePageTests(UiTestCase):
    """Users and roles (AUT-009 to AUT-015)."""

    def test_invite_edit_deactivate(self) -> None:
        role = Role.objects.get(name="Lager")
        url = reverse("accounts:user_create")
        response = self.client.post(
            url,
            form_data(
                self.client.get(url), username="luka", email="luka@example.de", first_name="Luka", roles=[role.pk]
            ),
        )
        self.assertRedirects(response, reverse("accounts:user_list"))
        user = User.objects.get(username="luka")
        self.assertFalse(user.has_usable_password())
        self.assertEqual(mail.outbox[-1].to, ["luka@example.de"])
        self.assertIn("eingeladen", self.assert_ok(self.client.get(reverse("accounts:user_list"))))

        edit = reverse("accounts:user_edit", args=[user.pk])
        manager = Role.objects.get(name="Projektleitung")
        self.client.post(edit, form_data(self.client.get(edit), roles=[role.pk, manager.pk], last_name="Lager"))
        self.assertEqual(set(user.roles.all()), {role, manager})

        self.client.post(reverse("accounts:user_send_invitation", args=[user.pk]))
        self.assertEqual(len(mail.outbox), 2)
        self.client.post(reverse("accounts:user_set_active", args=[user.pk]), {"active": "0"})
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertIn("deaktiviert", self.assert_ok(self.client.get(reverse("accounts:user_list"), {"q": "luka"})))

    def test_nobody_locks_himself_out(self) -> None:
        response = self.client.post(
            reverse("accounts:user_set_active", args=[self.admin_user.pk]), {"active": "0"}, follow=True
        )
        self.admin_user.refresh_from_db()
        self.assertTrue(self.admin_user.is_active)
        self.assertTrue(self.messages_of(response))

    def test_role_matrix(self) -> None:
        """AUT-010, AUT-015: one level per module plus special rights."""
        url = reverse("accounts:role_create")
        page = self.client.get(url)
        data = form_data(
            page, name="Werkstatt", module_material="2", module_products="1", special_rights=["purchase_prices"]
        )

        self.assertRedirects(self.client.post(url, data), reverse("accounts:role_list"))

        role = Role.objects.get(name="Werkstatt")
        self.assertEqual(role.module_levels["material"], 2)
        self.assertEqual(role.module_levels["products"], 1)
        self.assertEqual(role.module_levels.get("customers", 0), 0)
        self.assertEqual(role.special_rights, ["purchase_prices"])
        self.assertIn("Werkstatt", self.assert_ok(self.client.get(reverse("accounts:role_list"))))

        make_user("willi", roles=("Werkstatt",))
        blocked = self.client.post(reverse("accounts:role_delete", args=[role.pk]), follow=True)
        self.assertTrue(Role.objects.filter(pk=role.pk).exists())
        self.assertTrue(self.messages_of(blocked))
        User.objects.get(username="willi").roles.clear()
        self.client.post(reverse("accounts:role_delete", args=[role.pk]))
        self.assertFalse(Role.objects.filter(pk=role.pk).exists())

    def test_administration_is_closed_to_everyone_else(self) -> None:
        manager = self.browser_for("paula", "Projektleitung")
        for name in (
            "core:administration",
            "accounts:user_list",
            "accounts:role_list",
            "core:company_settings",
            "core:number_ranges",
            "core:audit_log",
        ):
            self.assertEqual(manager.get(reverse(name)).status_code, 403, name)
        self.assertEqual(manager.get("/administration/masterdata/").status_code, 302)


class SettingsPageTests(UiTestCase):
    """Company data, settings, number ranges, master data and the change log (ADM-001 to ADM-006)."""

    def test_company_data_with_logo(self) -> None:
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media, SERVE_MEDIA_VIA_NGINX=False):
            url = reverse("core:company_settings")
            data = form_data(self.client.get(url), containing="company-name")
            data.update(
                {
                    "form": "company",
                    "company-name": "Lichtwerk GmbH",
                    "company-logo": SimpleUploadedFile("logo.png", png(), "image/png"),
                }
            )

            self.assertRedirects(self.client.post(url, data), url)

            company = CompanyProfile.load()
            self.assertEqual(company.name, "Lichtwerk GmbH")
            self.assertTrue(company.logo.name.startswith("company/"))
            delivered = self.client.get(reverse("core:media", args=[company.logo.name]))
            self.assertEqual(delivered.status_code, 200)
            self.assertEqual(b"".join(delivered.streaming_content), png())
            # Files are only handed out to logged-in users, and only from known folders.
            self.client.logout()
            self.assertEqual(self.client.get(reverse("core:media", args=[company.logo.name])).status_code, 302)
            self.client.force_login(self.admin_user)
            self.assertEqual(self.client.get("/media/../../etc/passwd").status_code, 404)
            self.assertEqual(self.client.get("/media/imports/x.xlsx").status_code, 404)

    def test_logo_must_be_a_real_image(self) -> None:
        """NFA-042: the content counts, not the file name."""
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            url = reverse("core:company_settings")
            data = form_data(self.client.get(url), containing="company-name")
            script = SimpleUploadedFile("logo.png", b"<html><script>alert(1)</script></html>", "image/png")
            response = self.client.post(url, {**data, "form": "company", "company-logo": script})
            self.assertEqual(response.status_code, 200)
            self.assertIn("company-logo", [f"company-{name}" for name in response.context["company_form"].errors])
            svg = SimpleUploadedFile("logo.svg", b'<svg xmlns="http://www.w3.org/2000/svg"/>', "image/svg+xml")
            response = self.client.post(url, {**data, "form": "company", "company-logo": svg})
            self.assertTrue(response.context["company_form"].errors)
            self.assertFalse(CompanyProfile.load().logo)

    def test_system_settings(self) -> None:
        url = reverse("core:company_settings")
        data = form_data(self.client.get(url), containing="system-buffer_before_hours")
        data.update(
            {
                "form": "system",
                "system-buffer_before_hours": "4",
                "system-buffer_after_hours": "24",
                "system-password_min_length": "14",
            }
        )
        self.assertRedirects(self.client.post(url, data), url)
        system_settings = SystemSettings.load()
        self.assertEqual((system_settings.buffer_before_hours, system_settings.buffer_after_hours), (4, 24))
        self.assertEqual(system_settings.password_min_length, 14)

    def test_number_range_with_preview(self) -> None:
        """ADM-003."""
        number_range = NumberRange.objects.get(key=NumberRangeKey.CUSTOMER)
        url = reverse("core:number_ranges")
        page = self.assert_ok(self.client.get(url))
        self.assertIn(number_range.preview, page)
        prefix = f"range{number_range.pk}"
        data = {
            "range": number_range.pk,
            f"{prefix}-prefix": "KD-",
            f"{prefix}-min_digits": 6,
            f"{prefix}-next_value": 500,
        }
        self.assertRedirects(self.client.post(url, data), url)
        self.assertIn("KD-000500", self.assert_ok(self.client.get(url)))
        self.assertEqual(make_customer("Neu GmbH").number, "KD-000500")

    def test_master_data_is_maintained_in_the_administration_area(self) -> None:
        """ADM-002: categories, units, tax rates and so on."""
        index = self.assert_ok(self.client.get("/administration/masterdata/"))
        for text in ("Kategorien", "Einheiten", "Steuerarten", "Hersteller", "Lagerorte"):
            self.assertIn(text, index)
        add = "/administration/masterdata/masterdata/unit/add/"
        response = self.client.post(add, form_data(self.client.get(add), name="Palette", abbreviation="Pal."))
        self.assertEqual(response.status_code, 302)
        self.assertIn("Palette", self.assert_ok(self.client.get("/administration/masterdata/masterdata/unit/")))

    def test_change_log_filters(self) -> None:
        """ADM-005."""
        customer = make_customer("Stadtwerke")
        customer.city = "Musterstadt"
        customer.save()
        url = reverse("core:audit_log")
        page = self.assert_ok(self.client.get(url, {"q": "Stadtwerke"}))
        self.assertIn("Stadtwerke", page)
        self.assertIn("Musterstadt", page)
        today = timezone.localdate()
        self.assertIn(
            "Stadtwerke", self.assert_ok(self.client.get(url, {"since": today.isoformat(), "until": today.isoformat()}))
        )
        tomorrow = today + datetime.timedelta(days=1)
        self.assertNotIn("Stadtwerke", self.assert_ok(self.client.get(url, {"since": tomorrow.isoformat()})))
        self.assertNotIn("Stadtwerke", self.assert_ok(self.client.get(url, {"user": self.admin_user.pk})))


class CommandTests(UiTestCase):
    """The commands an administrator runs on the server."""

    def test_sample_data_is_created_once(self) -> None:
        """NFA-017."""
        first, second = io.StringIO(), io.StringIO()
        call_command("create_demo_data", stdout=first)
        projects = Project.objects.count()
        self.assertGreater(projects, 0)
        self.assertGreater(Customer.objects.count(), 0)
        call_command("create_demo_data", stdout=second)
        self.assertEqual(Project.objects.count(), projects)
        # The sample data includes a shortage, so the red light can be seen at once.
        self.assertIn(
            "Fehlmenge",
            self.assert_ok(self.client.get(reverse("projects:list")))
            + self.assert_ok(self.client.get(reverse("availability:shortages"))),
        )

    def test_daily_maintenance_removes_old_login_attempts(self) -> None:
        old = LoginAttempt.objects.create(identifier="berta", ip_address="127.0.0.1", successful=False)
        LoginAttempt.objects.filter(pk=old.pk).update(timestamp=timezone.now() - datetime.timedelta(days=400))
        LoginAttempt.objects.create(identifier="berta", ip_address="127.0.0.1", successful=False)
        output = io.StringIO()
        call_command("run_daily_maintenance", stdout=output)
        self.assertEqual(LoginAttempt.objects.count(), 1)
