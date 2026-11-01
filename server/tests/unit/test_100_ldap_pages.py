# SPDX-License-Identifier: GPL-3.0-or-later
"""The pages and the API of the directory login (AUT-029; API-002, API-014).

The requirement: LDAP is integrated, with an assignment of directory groups to roles.

The settings page, the table of group assignments, the tests ("Test connection", "Test login for user"), the
comparison of the accounts, the login itself through the login page (with two-factor login) and the same
functions through the API. The directory is the fake one of ``tests/ldap_fake.py`` (``ldap3`` mock strategy).
"""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from rentalars.accounts import twofactor
from rentalars.accounts.models import (
    LdapGroupMapping,
    LdapSettings,
    Role,
    SecurityEvent,
    SecurityEventKind,
    User,
)
from rentalars.core.models import AuditLogEntry
from tests.api.base import API, ApiTestCase
from tests.helpers import PASSWORD, make_user
from tests.ldap_fake import BASE, SERVICE_DN, SERVICE_PASSWORD, FakeDirectory, standard_directory
from tests.ui.base import UiTestCase, form_data
from tests.unit.test_100_ldap import CREW, PLANNERS, assign, configure, role_names

SETTINGS_URL = "accounts:ldap_settings"


class DirectoryPagesCase(UiTestCase):
    """A browser of the administrator, the fake directory switched on, three assignments."""

    def setUp(self) -> None:
        super().setUp()
        self.directory: FakeDirectory = standard_directory()
        self.enterContext(self.directory.active())
        self.settings = configure()
        assign("rentalars-admins", "Administrator")
        assign("rentalars-planners", "Projektleitung")
        assign("rentalars-crew", "Crew")

    def reader(self) -> Any:
        """A browser of somebody who may look at the administration but not change it."""
        role = Role.objects.create(name="Admin-Leser", module_levels={"administration": 1})
        user = make_user("leser")
        user.roles.add(role)
        return self.browser_of(user)

    def writer(self) -> Any:
        """A browser of somebody who may change the administration but not delete there."""
        role = Role.objects.create(name="Admin-Schreiber", module_levels={"administration": 2})
        user = make_user("schreiber")
        user.roles.add(role)
        return self.browser_of(user)


class SettingsPageTests(DirectoryPagesCase):
    """Looking at and changing the settings."""

    def test_page_shows_the_settings_and_never_the_password(self) -> None:
        response = self.client.get(reverse(SETTINGS_URL))
        text = self.assert_ok(response)
        self.assertIn("Verzeichnis (LDAP)", text)
        self.assertIn("ldaps://fake-directory", text)
        self.assertIn("Ein Passwort ist gespeichert", text)
        self.assertNotIn(SERVICE_PASSWORD, text)
        self.assertNotIn(self.settings.bind_password_encrypted, text)
        self.assertIn("rentalars-admins", text)

    def test_the_link_in_the_administration_leads_here(self) -> None:
        text = self.assert_ok(self.client.get(reverse("core:administration")))
        self.assertIn(reverse(SETTINGS_URL), text)

    def test_save_changes_and_keep_the_password(self) -> None:
        response = self.client.get(reverse(SETTINGS_URL))
        data = form_data(response, containing="server_uris", user_search_base=f"ou=staff,{BASE}")
        data["bind_password"] = ""
        done = self.client.post(reverse(SETTINGS_URL), data, follow=True)
        self.assertIn(
            "Die Einstellungen der Anmeldung über das Verzeichnis wurden gespeichert.", self.messages_of(done)
        )
        settings = LdapSettings.load()
        self.assertEqual(settings.user_search_base, f"ou=staff,{BASE}")
        self.assertEqual(settings.bind_password, SERVICE_PASSWORD)
        self.assertTrue(
            AuditLogEntry.objects.filter(
                action="updated", object_id=str(settings.pk), changes__has_key="user_search_base"
            ).exists()
        )

    def test_a_new_password_is_stored_encrypted(self) -> None:
        data = form_data(self.client.get(reverse(SETTINGS_URL)), containing="server_uris")
        data["bind_password"] = "a-new-secret"
        self.client.post(reverse(SETTINGS_URL), data)
        settings = LdapSettings.load()
        self.assertEqual(settings.bind_password, "a-new-secret")
        self.assertNotIn("a-new-secret", settings.bind_password_encrypted)
        self.assertTrue(AuditLogEntry.objects.filter(event="ldap.bind_password_stored").exists())
        self.assertNotIn("a-new-secret", str(list(AuditLogEntry.objects.values())))

    def test_the_password_can_be_removed(self) -> None:
        data = form_data(self.client.get(reverse(SETTINGS_URL)), containing="server_uris", remove_bind_password="on")
        self.client.post(reverse(SETTINGS_URL), data)
        self.assertFalse(LdapSettings.load().has_bind_password)
        self.assertTrue(AuditLogEntry.objects.filter(event="ldap.bind_password_removed").exists())

    def test_the_password_is_never_sent_to_another_server(self) -> None:
        """A new server (or search account) without a new password drops the stored one."""
        data = form_data(self.client.get(reverse(SETTINGS_URL)), containing="server_uris")
        data["server_uris"] = "ldaps://other-directory.example.com"
        done = self.client.post(reverse(SETTINGS_URL), data, follow=True)
        self.assertFalse(LdapSettings.load().has_bind_password)
        self.assertTrue(any("nie an einen anderen Server" in message for message in self.messages_of(done)))
        self.assertTrue(AuditLogEntry.objects.filter(event="ldap.bind_password_removed_moved").exists())

    def test_wrong_input_is_explained_on_the_page(self) -> None:
        data = form_data(self.client.get(reverse(SETTINGS_URL)), containing="server_uris")
        data["server_uris"] = "dc1.example.com"
        data["user_search_filter"] = "(uid=nobody)"
        data["ca_certificate_pem"] = "nonsense"
        response = self.client.post(reverse(SETTINGS_URL), data)
        text = self.assert_ok(response)
        self.assertIn("ldaps://", text)
        self.assertIn("{username}", text)
        self.assertEqual(LdapSettings.load().server_uris, "ldaps://fake-directory")

    def test_a_server_on_the_internal_network_needs_the_leave_of_the_operator(self) -> None:
        data = form_data(self.client.get(reverse(SETTINGS_URL)), containing="server_uris")
        data["server_uris"] = "ldaps://10.1.2.3"
        text = self.assert_ok(self.client.post(reverse(SETTINGS_URL), data))
        self.assertIn("allow_internal", text)

    def test_the_proposals_fill_in_the_form(self) -> None:
        text = self.assert_ok(self.client.get(reverse(SETTINGS_URL) + "?preset=ad"))
        self.assertIn("sAMAccountName", text)
        text = self.assert_ok(self.client.get(reverse(SETTINGS_URL) + "?preset=openldap"))
        self.assertIn("inetOrgPerson", text)

    def test_switching_the_local_passwords_off_needs_an_emergency_administrator(self) -> None:
        data = form_data(self.client.get(reverse(SETTINGS_URL)), containing="server_uris", allow_local_login=None)
        self.assert_ok(self.client.post(reverse(SETTINGS_URL), data))
        self.assertTrue(LdapSettings.load().allow_local_login)  # refused: no local administrator
        emergency = make_user("notfall", roles=("Administrator",))
        emergency.local_account = True
        emergency.save()
        self.client.post(reverse(SETTINGS_URL), data)
        self.assertFalse(LdapSettings.load().allow_local_login)

    def test_somebody_who_may_only_look_cannot_change(self) -> None:
        reader = self.reader()
        text = self.assert_ok(reader.get(reverse(SETTINGS_URL)))
        self.assertNotIn("Einstellungen speichern", text)
        self.assertNotIn("Neue Zuordnung", text)
        self.assertEqual(reader.post(reverse(SETTINGS_URL), {}).status_code, 403)
        self.assertEqual(reader.post(reverse("accounts:ldap_test_connection")).status_code, 403)
        self.assertEqual(reader.post(reverse("accounts:ldap_test_login"), {"try-username": "anna"}).status_code, 403)
        self.assertEqual(reader.post(reverse("accounts:ldap_sync"), {"mode": "apply"}).status_code, 403)
        self.assertEqual(reader.get(reverse("accounts:ldap_mapping_create")).status_code, 403)

    def test_somebody_without_the_right_sees_nothing(self) -> None:
        crew = self.browser_for("crewmitglied", "Crew")
        self.assertEqual(crew.get(reverse(SETTINGS_URL)).status_code, 403)
        self.assertEqual(Client_anonymous().get(reverse(SETTINGS_URL)).status_code, 302)

    def test_the_changes_show_in_the_change_log_of_the_settings_without_the_secret(self) -> None:
        data = form_data(self.client.get(reverse(SETTINGS_URL)), containing="server_uris", start_tls="on")
        self.client.post(reverse(SETTINGS_URL), data)
        log = self.assert_ok(self.client.get(reverse("accounts:security_log")))
        self.assertNotIn(SERVICE_PASSWORD, log)

    def test_hints_for_the_administrator(self) -> None:
        LdapGroupMapping.objects.all().delete()
        text = self.assert_ok(self.client.get(reverse(SETTINGS_URL)))
        self.assertIn("Noch keine Gruppe hat Rollen", text)
        self.assertIn("Noch keine Zuordnung", text)
        self.assertIn("kein lokales (Notfall-)Konto", text)
        settings = LdapSettings.load()
        settings.bind_password_encrypted = "garbage"
        settings.save()
        self.assertIn("nicht mehr lesbar", self.assert_ok(self.client.get(reverse(SETTINGS_URL))))


def Client_anonymous() -> Any:
    """A browser nobody is logged in with."""
    from django.test import Client

    return Client()


class MappingPageTests(DirectoryPagesCase):
    """The table "group → roles"."""

    def test_create_change_and_delete(self) -> None:
        crew, store = (Role.objects.get(name=name).pk for name in ("Crew", "Lager"))
        done = self.client.post(
            reverse("accounts:ldap_mapping_create"),
            {"group": "Lagerteam", "roles": [store], "priority": "5", "note": "Lager"},
            follow=True,
        )
        self.assertIn("Die Zuordnung wurde gespeichert.", self.messages_of(done))
        mapping = LdapGroupMapping.objects.get(group="Lagerteam")
        self.assertEqual(sorted(mapping.roles.values_list("name", flat=True)), ["Lager"])
        self.assertTrue(AuditLogEntry.objects.filter(event="ldap_mapping.roles_changed").exists())
        page = self.client.get(reverse("accounts:ldap_mapping_edit", args=[mapping.pk]))
        data = form_data(page, containing="group", roles=[store, crew])
        self.client.post(reverse("accounts:ldap_mapping_edit", args=[mapping.pk]), data)
        self.assertEqual(sorted(mapping.roles.values_list("name", flat=True)), ["Crew", "Lager"])
        done = self.client.post(reverse("accounts:ldap_mapping_delete", args=[mapping.pk]), follow=True)
        self.assertFalse(LdapGroupMapping.objects.filter(pk=mapping.pk).exists())
        self.assertTrue(any("zurückgenommen" in message for message in self.messages_of(done)))

    def test_a_group_twice_and_no_roles_are_refused(self) -> None:
        response = self.client.post(
            reverse("accounts:ldap_mapping_create"),
            {"group": f"CN=Rentalars-Crew,OU=Groups,{BASE}", "roles": [Role.objects.get(name="Crew").pk]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(LdapGroupMapping.objects.count(), 3)
        response = self.client.post(reverse("accounts:ldap_mapping_create"), {"group": "Neue Gruppe", "priority": "0"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(LdapGroupMapping.objects.count(), 3)

    def test_deleting_needs_the_right_to_delete(self) -> None:
        mapping = LdapGroupMapping.objects.first()
        assert mapping is not None
        schreiber = self.writer()
        self.assertEqual(schreiber.post(reverse("accounts:ldap_mapping_delete", args=[mapping.pk])).status_code, 403)
        text = self.assert_ok(schreiber.get(reverse(SETTINGS_URL)))
        self.assertNotIn(reverse("accounts:ldap_mapping_delete", args=[mapping.pk]), text)
        self.assertEqual(schreiber.get(reverse("accounts:ldap_mapping_edit", args=[mapping.pk])).status_code, 200)

    def test_a_missing_assignment_is_a_404(self) -> None:
        self.assertEqual(self.client.get(reverse("accounts:ldap_mapping_edit", args=[9999])).status_code, 404)
        self.assertEqual(self.client.post(reverse("accounts:ldap_mapping_delete", args=[9999])).status_code, 404)


class TestToolPageTests(DirectoryPagesCase):
    """ "Test connection", "Test login for user", comparison."""

    def test_connection_test(self) -> None:
        text = self.assert_ok(self.client.post(reverse("accounts:ldap_test_connection")))
        self.assertIn("Ergebnis des Verbindungstests", text)
        self.assertIn("alles in Ordnung", text)
        self.directory.down = True
        text = self.assert_ok(self.client.post(reverse("accounts:ldap_test_connection")))
        self.assertIn("Probleme gefunden", text)
        self.assertIn("nicht erreichbar", text)
        self.assertNotIn(SERVICE_PASSWORD, text)

    def test_connection_test_without_settings_says_what_is_missing(self) -> None:
        configure(server_uris="")
        done = self.client.post(reverse("accounts:ldap_test_connection"), follow=True)
        self.assertTrue(any("Server" in message for message in self.messages_of(done)))

    def test_login_test_shows_entry_groups_and_roles_and_writes_nothing(self) -> None:
        accounts = User.objects.count()
        text = self.assert_ok(
            self.client.post(reverse("accounts:ldap_test_login"), {"try-username": "bernd", "try-password": ""})
        )
        self.assertIn("Ergebnis für „bernd“", text)
        self.assertIn(f"cn=bernd,ou=people,{BASE}", text)
        self.assertIn("Crew, Projektleitung", text)
        self.assertIn("ein neues Konto anlegen", text)
        self.assertEqual(User.objects.count(), accounts)

    def test_login_test_with_password(self) -> None:
        text = self.assert_ok(
            self.client.post(reverse("accounts:ldap_test_login"), {"try-username": "anna", "try-password": "falsch"})
        )
        self.assertIn("vom Verzeichnis abgewiesen", text)
        self.assertNotIn("falsch</", text)
        text = self.assert_ok(
            self.client.post(reverse("accounts:ldap_test_login"), {"try-username": "anna", "try-password": "anna-pw"})
        )
        self.assertIn("vom Verzeichnis angenommen", text)

    def test_login_test_of_a_user_in_no_group_and_of_nobody(self) -> None:
        text = self.assert_ok(self.client.post(reverse("accounts:ldap_test_login"), {"try-username": "dieter"}))
        self.assertIn("abgewiesen", text)
        self.assert_ok(self.client.post(reverse("accounts:ldap_test_login"), {"try-username": "niemand"}))
        text = self.assert_ok(self.client.post(reverse("accounts:ldap_test_login"), {"try-username": ""}))
        self.assertIn("Gib den Benutzernamen ein", text)

    def test_login_test_when_the_directory_is_down(self) -> None:
        self.directory.down = True
        text = self.assert_ok(self.client.post(reverse("accounts:ldap_test_login"), {"try-username": "anna"}))
        self.assertIn("nicht erreichbar", text)

    def test_comparison_first_a_preview_then_apply(self) -> None:
        make_user("boss", superuser=True)
        carla = self.log_in_through_the_directory("carla", "carla-pw")
        self.directory.remove(carla.ldap_dn)
        text = self.assert_ok(self.client.post(reverse("accounts:ldap_sync"), {"mode": "preview"}))
        self.assertIn("carla", text)
        self.assertIn("deaktivieren", text)
        self.assertIn("Diese Änderungen anwenden", text)
        self.assertTrue(User.objects.get(username="carla").is_active)
        done = self.client.post(reverse("accounts:ldap_sync"), {"mode": "apply"}, follow=True)
        self.assertFalse(User.objects.get(username="carla").is_active)
        self.assertTrue(any("abgeglichen" in message for message in self.messages_of(done)))

    def test_comparison_with_the_directory_down(self) -> None:
        self.directory.down = True
        done = self.client.post(reverse("accounts:ldap_sync"), {"mode": "preview"}, follow=True)
        self.assertTrue(any("nicht erreichbar" in message for message in self.messages_of(done)))

    def log_in_through_the_directory(self, name: str, password: str) -> User:
        from tests.unit.test_100_ldap import login

        user = login(name, password)
        assert user is not None
        return user


class LoginPageTests(DirectoryPagesCase):
    """The way a colleague uses it: the login page."""

    def setUp(self) -> None:
        super().setUp()
        from django.test import Client

        self.visitor = Client()

    def test_login_through_the_page_and_the_next_request_still_knows_the_user(self) -> None:
        response = self.visitor.post(reverse("accounts:login"), {"username": "bernd", "password": "bernd-pw"})
        self.assertRedirects(response, reverse("core:home"), fetch_redirect_response=False)
        page = self.visitor.get(reverse("core:home"))
        self.assertEqual(page.wsgi_request.user.username, "bernd")
        self.assertEqual(role_names(page.wsgi_request.user), ["Crew", "Projektleitung"])
        self.assertEqual(SecurityEvent.objects.filter(kind=SecurityEventKind.LOGIN, user__username="bernd").count(), 1)
        # and the role works: a planner may use the projects
        self.assertEqual(self.visitor.get(reverse("projects:list")).status_code, 200)

    def test_wrong_password_and_unknown_name_get_the_same_text(self) -> None:
        wrong = self.visitor.post(reverse("accounts:login"), {"username": "anna", "password": "x"})
        unknown = self.visitor.post(reverse("accounts:login"), {"username": "nobody", "password": "x"})
        self.assertContains(wrong, "Name oder Passwort stimmen nicht.")
        self.assertContains(unknown, "Name oder Passwort stimmen nicht.")
        self.assertNotContains(wrong, "Firmenverzeichnis")

    def test_directory_down_gives_a_hint_but_not_the_reason(self) -> None:
        self.directory.down = True
        response = self.visitor.post(reverse("accounts:login"), {"username": "anna", "password": "anna-pw"})
        self.assertContains(response, "Name oder Passwort stimmen nicht.")
        self.assertContains(response, "Firmenverzeichnis")
        self.assertNotContains(response, "fake-directory")
        self.assertNotContains(response, "connection refused")

    def test_failed_attempts_lock_the_name_like_any_other_login(self) -> None:
        for _attempt in range(30):
            self.visitor.post(reverse("accounts:login"), {"username": "anna", "password": "wrong"})
        response = self.visitor.post(reverse("accounts:login"), {"username": "anna", "password": "anna-pw"})
        self.assertContains(response, "Zu viele Fehlversuche")
        self.assertFalse(User.objects.filter(username="anna").exists())

    def test_two_factor_login_asks_for_the_code_after_the_directory_password(self) -> None:
        self.visitor.post(reverse("accounts:login"), {"username": "carla", "password": "carla-pw"})
        carla = User.objects.get(username="carla")
        secret = twofactor.new_secret()
        step = twofactor.current_step()
        twofactor.enable(carla, secret, twofactor.code_at(secret, step))
        self.visitor.post(reverse("accounts:logout"))
        # A wrong directory password never gets to the code.
        wrong = self.visitor.post(reverse("accounts:login"), {"username": "carla", "password": "wrong"})
        self.assertEqual(wrong.status_code, 200)
        response = self.visitor.post(reverse("accounts:login"), {"username": "carla", "password": "carla-pw"})
        self.assertRedirects(response, reverse("accounts:login_code"), fetch_redirect_response=False)
        self.assertEqual(self.visitor.get(reverse("core:home")).status_code, 302)  # not yet in
        bad = self.visitor.post(reverse("accounts:login_code"), {"code": "000000"})
        self.assertEqual(bad.status_code, 200)
        done = self.visitor.post(reverse("accounts:login_code"), {"code": twofactor.code_at(secret, step + 1)})
        self.assertRedirects(done, reverse("core:home"), fetch_redirect_response=False)
        page = self.visitor.get(reverse("core:home"))
        self.assertEqual(page.wsgi_request.user.username, "carla")

    def test_a_directory_account_has_no_password_form_and_switches_two_factor_off_with_a_code(self) -> None:
        self.visitor.post(reverse("accounts:login"), {"username": "carla", "password": "carla-pw"})
        text = self.assert_ok(self.visitor.get(reverse("accounts:account")))
        self.assertIn("Firmenverzeichnis", text)
        self.assertNotIn('name="new_password', text)
        carla = User.objects.get(username="carla")
        secret = twofactor.new_secret()
        step = twofactor.current_step()
        twofactor.enable(carla, secret, twofactor.code_at(secret, step))
        page = self.assert_ok(self.visitor.get(reverse("accounts:two_factor_setup")))
        self.assertIn('name="code"', page)
        self.assertNotIn('name="password"', page)
        wrong = self.visitor.post(reverse("accounts:two_factor_disable"), {"code": "000000"}, follow=True)
        self.assertTrue(User.objects.get(username="carla").has_two_factor)
        self.assertTrue(wrong.redirect_chain)
        self.visitor.post(reverse("accounts:two_factor_disable"), {"code": twofactor.code_at(secret, step + 1)})
        self.assertFalse(User.objects.get(username="carla").has_two_factor)

    def test_a_local_user_still_logs_in_with_the_local_password(self) -> None:
        make_user("lokal", roles=("Crew",))
        response = self.visitor.post(reverse("accounts:login"), {"username": "lokal", "password": PASSWORD})
        self.assertRedirects(response, reverse("core:home"), fetch_redirect_response=False)
        self.assertNotIn(SERVICE_DN, self.directory.binds[1:])  # asked the directory? no: only the local backend ran

    def test_the_user_list_and_the_user_form_show_what_comes_from_the_directory(self) -> None:
        self.visitor.post(reverse("accounts:login"), {"username": "bernd", "password": "bernd-pw"})
        bernd = User.objects.get(username="bernd")
        page = self.client.get(reverse("accounts:user_edit", args=[bernd.pk]))
        text = self.assert_ok(page)
        self.assertIn("aus dem Verzeichnis", text)
        self.assertIn(bernd.ldap_dn, text)
        # The roles of the directory cannot be unticked: the form does not offer them, the roles stay.
        data = form_data(page, containing="username", roles=None)
        self.client.post(reverse("accounts:user_edit", args=[bernd.pk]), data)
        self.assertEqual(role_names(User.objects.get(pk=bernd.pk)), ["Crew", "Projektleitung"])
        self.assertNotContains(page, "Einladung")
        # An administrator adds a role by hand: it stays when the directory changes.
        lager = Role.objects.get(name="Lager").pk
        data = form_data(page, containing="username", roles=[lager])
        self.client.post(reverse("accounts:user_edit", args=[bernd.pk]), data)
        self.assertEqual(role_names(User.objects.get(pk=bernd.pk)), ["Crew", "Lager", "Projektleitung"])
        self.directory.change(bernd.ldap_dn, "memberOf", [PLANNERS])
        self.visitor.post(reverse("accounts:logout"))
        self.visitor.post(reverse("accounts:login"), {"username": "bernd", "password": "bernd-pw"})
        self.assertEqual(role_names(User.objects.get(pk=bernd.pk)), ["Lager", "Projektleitung"])
        self.assertNotIn(CREW, "")  # (the crew group is gone from the directory entry above)

    def test_the_local_flag_can_be_set_on_the_user_form(self) -> None:
        self.visitor.post(reverse("accounts:login"), {"username": "carla", "password": "carla-pw"})
        carla = User.objects.get(username="carla")
        page = self.client.get(reverse("accounts:user_edit", args=[carla.pk]))
        data = form_data(page, containing="username", local_account="on")
        self.client.post(reverse("accounts:user_edit", args=[carla.pk]), data)
        self.assertTrue(User.objects.get(pk=carla.pk).local_account)


class LdapApiTests(ApiTestCase):
    """Every operation of the API (API-002, API-014)."""

    def setUp(self) -> None:
        super().setUp()
        self.directory = standard_directory()
        self.enterContext(self.directory.active())
        configure()
        assign("rentalars-admins", "Administrator")
        assign("rentalars-planners", "Projektleitung")
        assign("rentalars-crew", "Crew")

    def test_settings_get_and_patch(self) -> None:
        got = self.admin.get(f"{API}/ldap/settings")
        self.assertEqual(got.status_code, 200)
        body = got.json()
        self.assertTrue(body["has_bind_password"])
        self.assertNotIn("bind_password", body)
        self.assertNotIn(SERVICE_PASSWORD, got.content.decode())
        changed = self.admin.patch(f"{API}/ldap/settings", {"timeout_seconds": 20, "sync_daily": True}, format="json")
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual(changed.json()["timeout_seconds"], 20)
        self.assertTrue(LdapSettings.load().sync_daily)
        self.assertEqual(LdapSettings.load().bind_password, SERVICE_PASSWORD)

    def test_the_password_is_write_only_and_follows_the_servers(self) -> None:
        self.admin.patch(f"{API}/ldap/settings", {"bind_password": "neu"}, format="json")
        self.assertEqual(LdapSettings.load().bind_password, "neu")
        moved = self.admin.patch(
            f"{API}/ldap/settings", {"server_uris": "ldaps://elsewhere.example.com"}, format="json"
        )
        self.assertEqual(moved.status_code, 200, moved.content)
        self.assertFalse(moved.json()["has_bind_password"])
        self.assertIn("password_notice", moved.json())
        self.admin.patch(f"{API}/ldap/settings", {"bind_password": "neu2"}, format="json")
        removed = self.admin.patch(f"{API}/ldap/settings", {"remove_bind_password": True}, format="json")
        self.assertFalse(removed.json()["has_bind_password"])

    def test_settings_are_validated(self) -> None:
        self.assert_error(
            self.admin.patch(f"{API}/ldap/settings", {"server_uris": "no-scheme.example.com"}, format="json"),
            400,
            "validation_error",
            "server_uris",
        )
        self.assert_error(
            self.admin.patch(f"{API}/ldap/settings", {"user_search_filter": "(uid=x)"}, format="json"),
            400,
            "validation_error",
            "user_search_filter",
        )

    def test_mappings(self) -> None:
        roles = {name: Role.objects.get(name=name).pk for name in ("Crew", "Lager")}
        listed = self.admin.get(f"{API}/ldap/mappings")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["count"], 3)
        created = self.admin.post(
            f"{API}/ldap/mappings", {"group": "Lagerteam", "roles": [roles["Lager"]], "priority": 7}, format="json"
        )
        self.assertEqual(created.status_code, 201, created.content)
        pk = created.json()["id"]
        self.assertEqual(self.admin.get(f"{API}/ldap/mappings/{pk}").json()["group"], "Lagerteam")
        put = self.admin.put(
            f"{API}/ldap/mappings/{pk}",
            {"group": "Lagerteam", "roles": [roles["Lager"], roles["Crew"]], "priority": 8},
            format="json",
        )
        self.assertEqual(put.status_code, 200, put.content)
        # (review R4) last_match is read only: the table decides by priority, a client cannot set it.
        patched = self.admin.patch(f"{API}/ldap/mappings/{pk}", {"last_match": True}, format="json")
        self.assertEqual(patched.status_code, 200, patched.content)
        self.assertFalse(patched.json()["last_match"])
        self.assertEqual(
            sorted(LdapGroupMapping.objects.get(pk=pk).roles.values_list("name", flat=True)), ["Crew", "Lager"]
        )
        self.assertEqual(self.admin.delete(f"{API}/ldap/mappings/{pk}").status_code, 204)
        self.assertFalse(LdapGroupMapping.objects.filter(pk=pk).exists())

    def test_mappings_are_validated(self) -> None:
        crew = Role.objects.get(name="Crew").pk
        self.assert_error(
            self.admin.post(f"{API}/ldap/mappings", {"group": "x", "roles": []}, format="json"),
            400,
            "validation_error",
            "roles",
        )
        duplicate = self.admin.post(
            f"{API}/ldap/mappings", {"group": f"CN=RENTALARS-CREW,OU=Groups,{BASE}", "roles": [crew]}, format="json"
        )
        self.assertEqual(duplicate.status_code, 400)

    def test_connection_test(self) -> None:
        answer = self.admin.post(f"{API}/ldap/test-connection")
        self.assertEqual(answer.status_code, 200, answer.content)
        self.assertTrue(answer.json()["ok"])
        self.directory.down = True
        answer = self.admin.post(f"{API}/ldap/test-connection")
        self.assertFalse(answer.json()["ok"])

    def test_connection_test_without_settings_is_a_400(self) -> None:
        configure(server_uris="")
        self.assertEqual(self.admin.post(f"{API}/ldap/test-connection").status_code, 400)

    def test_login_test(self) -> None:
        answer = self.admin.post(f"{API}/ldap/test-login", {"username": "bernd"}, format="json")
        self.assertEqual(answer.status_code, 200, answer.content)
        body = answer.json()
        self.assertEqual(body["roles_from_directory"], ["Crew", "Projektleitung"])
        self.assertEqual(body["action"], "create")
        checked = self.admin.post(
            f"{API}/ldap/test-login", {"username": "anna", "password": "anna-pw"}, format="json"
        ).json()
        self.assertTrue(checked["password_ok"])
        self.assertNotIn("anna-pw", str(checked))
        self.assertEqual(User.objects.filter(username__in=["anna", "bernd"]).count(), 0)
        self.assert_error(
            self.admin.post(f"{API}/ldap/test-login", {"username": ""}, format="json"),
            400,
            "validation_error",
            "username",
        )

    def test_login_test_directory_down_is_a_502(self) -> None:
        self.directory.down = True
        answer = self.admin.post(f"{API}/ldap/test-login", {"username": "anna"}, format="json")
        self.assertEqual(answer.status_code, 502)

    def test_comparison_is_a_dry_run_unless_told_otherwise(self) -> None:
        make_user("boss", superuser=True)
        from tests.unit.test_100_ldap import login

        carla = login("carla", "carla-pw")
        assert carla is not None
        self.directory.remove(carla.ldap_dn)
        dry = self.admin.post(f"{API}/ldap/sync", {}, format="json")
        self.assertEqual(dry.status_code, 200, dry.content)
        self.assertFalse(dry.json()["applied"])
        self.assertTrue(User.objects.get(username="carla").is_active)
        done = self.admin.post(f"{API}/ldap/sync", {"dry_run": False}, format="json")
        self.assertTrue(done.json()["applied"])
        self.assertFalse(User.objects.get(username="carla").is_active)

    def test_comparison_with_the_directory_down_is_a_502(self) -> None:
        self.directory.down = True
        self.assertEqual(self.admin.post(f"{API}/ldap/sync", {}, format="json").status_code, 502)

    def test_nothing_without_the_right(self) -> None:
        crew = self.client_for("crewmitglied", "Crew")
        for method, path in (
            ("get", "/ldap/settings"),
            ("patch", "/ldap/settings"),
            ("get", "/ldap/mappings"),
            ("post", "/ldap/mappings"),
            ("post", "/ldap/test-connection"),
            ("post", "/ldap/test-login"),
            ("post", "/ldap/sync"),
        ):
            answer = (
                getattr(crew, method)(f"{API}{path}", {}, format="json")
                if method != "get"
                else crew.get(f"{API}{path}")
            )
            self.assertEqual(answer.status_code, 403, (method, path))
        reader = Role.objects.create(name="Admin-Leser", module_levels={"administration": 1})
        looker = make_user("leser")
        looker.roles.add(reader)
        client = self.client_of(looker)
        self.assertEqual(client.get(f"{API}/ldap/settings").status_code, 200)
        self.assertEqual(client.patch(f"{API}/ldap/settings", {"enabled": False}, format="json").status_code, 403)
        self.assertEqual(client.post(f"{API}/ldap/sync", {}, format="json").status_code, 403)

    def test_users_api_shows_directory_roles_and_refuses_taking_them_away(self) -> None:
        from tests.unit.test_100_ldap import login

        bernd = login("bernd", "bernd-pw")
        assert bernd is not None
        shown = self.admin.get(f"{API}/users/{bernd.pk}").json()
        self.assertEqual(sorted(shown["directory_roles"]), sorted(shown["directory_roles"]))
        self.assertTrue(shown["ldap_dn"])
        self.assertFalse(shown["local_account"])
        refused = self.admin.patch(f"{API}/users/{bernd.pk}", {"roles": []}, format="json")
        self.assertEqual(refused.status_code, 400, refused.content)
        flagged = self.admin.patch(f"{API}/users/{bernd.pk}", {"local_account": True}, format="json")
        self.assertEqual(flagged.status_code, 200, flagged.content)
        self.assertTrue(User.objects.get(pk=bernd.pk).local_account)

    def test_login_over_the_api_with_directory_credentials(self) -> None:
        from rest_framework.test import APIClient

        anonymous = APIClient()
        done = anonymous.post(f"{API}/auth/login", {"username": "carla", "password": "carla-pw"}, format="json")
        self.assertEqual(done.status_code, 200, done.content)
        wrong = anonymous.post(f"{API}/auth/login", {"username": "carla", "password": "x"}, format="json")
        self.assert_error(wrong, 400, "invalid_credentials")
        self.directory.down = True
        down = anonymous.post(f"{API}/auth/login", {"username": "carla", "password": "x"}, format="json")
        self.assertIn("Firmenverzeichnis", down.json()["error"]["message"])
        self.assertNotIn("fake-directory", down.content.decode())
