# SPDX-License-Identifier: GPL-3.0-or-later
"""Login with LDAP / Active Directory and group-role assignment (AUT-029).

The requirement: LDAP is integrated, with an assignment of directory groups to roles.

* Operators log in with their directory account; the account is created at the first login if one of the
  user's groups has a role, names and roles follow the directory at every login.
* The directory never touches local (emergency) accounts, never deactivates the last administrator, and an
  administrator's own roles stay.
* Everything runs against ``ldap3``'s mock strategy (``tests/ldap_fake.py``): the search, filter, bind and
  result code of Rentalars is real, the network and TLS are not (see the module docstring there). The real
  connection factory is tested for what it builds (checked address, certificate name, TLS settings) without
  opening a connection, and once against a closed port on this machine.
* The pages and the API are in ``tests/unit/test_100_ldap_pages.py``.
"""

from __future__ import annotations

import datetime
import socket
import ssl
from typing import Any
from unittest import mock

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from django.contrib.auth import authenticate
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import RequestFactory, TransactionTestCase
from django.utils import timezone

from rentalars.accounts import ldap_client, ldap_sync, services
from rentalars.accounts.models import (
    LdapGroupMapping,
    LdapRoleAssignment,
    LdapSettings,
    Role,
    SecurityEvent,
    SecurityEventKind,
    User,
)
from rentalars.core import network
from rentalars.core.models import AuditLogEntry
from tests.helpers import PASSWORD, RentalarsTestCase, make_user
from tests.ldap_fake import BASE, SERVICE_DN, SERVICE_PASSWORD, FakeDirectory, standard_directory

ADMINS = f"cn=rentalars-admins,ou=groups,{BASE}"
PLANNERS = f"cn=rentalars-planners,ou=groups,{BASE}"
CREW = f"cn=rentalars-crew,ou=groups,{BASE}"


def configure(**changes: Any) -> LdapSettings:
    """Switch the directory on with the values of the fake directory; ``changes`` override single settings."""
    settings = LdapSettings.load()
    values: dict[str, Any] = {
        "enabled": True,
        "server_uris": "ldaps://fake-directory",
        "bind_dn": SERVICE_DN,
        "user_search_base": f"ou=people,{BASE}",
        "user_search_filter": "(&(objectClass=person)(sAMAccountName={username}))",
        "attribute_username": "sAMAccountName",
        "group_mode": "member_of",
        # (AUT-029) Linking existing accounts by name is off by default now. Most tests here are
        # about what happens once an account is linked, so they switch it on; ``tests/unit/test_100_fix_r2.py``
        # tests the default.
        "link_existing_accounts": True,
    }
    values.update(changes)
    for name, value in values.items():
        setattr(settings, name, value)
    settings.set_bind_password(SERVICE_PASSWORD)
    settings.save()
    return settings


def assign(group_name: str, *roles: str, **options: Any) -> LdapGroupMapping:
    """An assignment of the group ``cn=<group_name>,ou=groups,…`` to roles."""
    mapping = LdapGroupMapping.objects.create(group=f"cn={group_name},ou=groups,{BASE}", **options)
    mapping.roles.set(Role.objects.filter(name__in=roles))
    return mapping


def login(username: str, password: str) -> User | None:
    """What the login page does: ask the backends."""
    request = RequestFactory().post("/login/")
    request.META["REMOTE_ADDR"] = "10.0.0.5"
    request.session = {}  # type: ignore[assignment]
    user = authenticate(request, username=username, password=password)
    login.last_request = request  # type: ignore[attr-defined]
    return user


def role_names(user: User) -> list[str]:
    """The names of the roles of an account, sorted."""
    return sorted(user.roles.values_list("name", flat=True))


class DirectoryTestCase(RentalarsTestCase):
    """A fake directory, the settings switched on, three assignments."""

    def setUp(self) -> None:
        super().setUp()
        self.directory: FakeDirectory = standard_directory()
        self.enterContext(self.directory.active())
        self.settings = configure()
        assign("rentalars-admins", "Administrator")
        assign("rentalars-planners", "Projektleitung")
        assign("rentalars-crew", "Crew")


class LoginTests(DirectoryTestCase):
    """The first login creates the account; a wrong password or an unknown name gets nothing."""

    def test_first_login_creates_account_with_roles_from_the_groups(self) -> None:
        user = login("anna", "anna-pw")
        assert user is not None
        self.assertEqual(user.username, "anna")
        self.assertEqual((user.first_name, user.last_name, user.email), ("Anna", "Beispiel", "anna@example.com"))
        self.assertEqual(role_names(user), ["Administrator"])
        self.assertTrue(user.ldap_dn.startswith("cn=anna,"))
        self.assertFalse(user.has_usable_password())
        self.assertTrue(user.rights.can_write("administration"))
        self.assertTrue(hasattr(user, "person"))  # AUT-026: the account is a person
        self.assertEqual(LdapRoleAssignment.objects.filter(user=user).count(), 1)

    def test_roles_of_several_groups_are_united(self) -> None:
        user = login("bernd", "bernd-pw")
        assert user is not None
        self.assertEqual(role_names(user), ["Crew", "Projektleitung"])

    def test_wrong_password_unknown_name_and_empty_password(self) -> None:
        self.assertIsNone(login("anna", "wrong"))
        self.assertIsNone(login("nobody", "whatever"))
        self.assertIsNone(login("anna", ""))
        self.assertIsNone(login("", "x"))
        self.assertFalse(User.objects.filter(username="anna").exists())

    def test_an_empty_password_never_reaches_the_directory(self) -> None:
        """Many servers take a bind with a name and no password as an anonymous one and say yes."""
        dn = self.directory.add_user("emil", "emil-pw", groups=[CREW])
        self.directory.binds.clear()
        self.assertFalse(ldap_client.check_password(ldap_client.DirectoryConfig.from_settings(self.settings), dn, ""))
        self.assertEqual(self.directory.binds, [])

    def test_user_in_no_assigned_group_is_refused_and_nothing_is_created(self) -> None:
        self.assertIsNone(login("dieter", "dieter-pw"))
        self.assertFalse(User.objects.filter(username="dieter").exists())
        event = SecurityEvent.objects.get(kind=SecurityEventKind.LDAP_REFUSED)
        self.assertEqual(event.identifier, "dieter")
        self.assertIn("no group", event.detail)

    def test_no_accounts_are_created_when_that_is_switched_off(self) -> None:
        configure(auto_create_users=False)
        self.assertIsNone(login("anna", "anna-pw"))
        make_user("anna")  # created by hand: the first directory login links it
        user = login("anna", "anna-pw")
        assert user is not None
        self.assertTrue(user.ldap_dn)

    def test_switched_off_directory_is_not_asked(self) -> None:
        configure(enabled=False)
        self.assertIsNone(login("anna", "anna-pw"))
        self.assertEqual(self.directory.binds, [])

    def test_typed_name_is_brought_into_one_unicode_form(self) -> None:
        self.directory.add_user("jürgen", "j-pw", first="Jürgen", mail="juergen@example.com", groups=[CREW])
        user = login("jürgen", "j-pw")  # typed with a combining diaeresis
        assert user is not None
        self.assertEqual(user.username, "jürgen")

    def test_an_account_made_by_hand_is_found_without_regard_to_case(self) -> None:
        by_hand = make_user("ANNA")
        user = login("anna", "anna-pw")
        assert user is not None
        self.assertEqual(user.pk, by_hand.pk)
        self.assertEqual(User.objects.count(), 1)
        self.assertTrue(user.ldap_dn)
        self.assertTrue(user.roles.filter(name="Administrator").exists())

    def test_login_updates_names_and_roles_every_time(self) -> None:
        user = login("carla", "carla-pw")
        assert user is not None
        dn = user.ldap_dn
        self.directory.change(dn, "givenName", ["Karla"])
        self.directory.change(dn, "memberOf", [PLANNERS])
        user = login("carla", "carla-pw")
        assert user is not None
        self.assertEqual(user.first_name, "Karla")
        self.assertEqual(role_names(user), ["Projektleitung"])
        self.assertEqual(LdapRoleAssignment.objects.filter(user=user).count(), 1)

    def test_invalid_e_mail_address_is_left_out(self) -> None:
        self.directory.add_user("jürgen", "j-pw", mail="jürgen@example.com", groups=[CREW])
        user = login("jürgen", "j-pw")
        assert user is not None
        self.assertIsNone(user.email)

    def test_an_address_of_another_account_is_not_taken_over(self) -> None:
        make_user("someone", roles=("Crew",)).__class__.objects.filter(username="someone").update(
            email="carla@example.com"
        )
        user = login("carla", "carla-pw")
        assert user is not None
        self.assertIsNone(user.email)

    def test_a_username_rentalars_cannot_hold_is_refused(self) -> None:
        self.directory.add_user("frau mueller", "pw", groups=[CREW])
        self.assertIsNone(login("frau mueller", "pw"))
        self.assertIn("username not usable", SecurityEvent.objects.get(kind=SecurityEventKind.LDAP_REFUSED).detail)

    def test_login_sets_the_session_up_like_any_other_login(self) -> None:
        """The session of a directory login is loaded again by the local backend (``get_user``)."""
        self.client.post("/login/", {"username": "anna", "password": "anna-pw"})
        response = self.client.get("/")
        self.assertEqual(response.wsgi_request.user.username, "anna")
        self.assertTrue(SecurityEvent.objects.filter(kind=SecurityEventKind.LOGIN, user__username="anna").exists())


class InjectionTests(DirectoryTestCase):
    """The typed name never changes the filter."""

    def test_filter_characters_are_escaped(self) -> None:
        self.assertIsNone(login("*", "x"))
        self.assertIsNone(login("anna)(objectClass=*", "x"))
        self.assertIsNone(login("*)(uid=*))(|(uid=*", "x"))
        user_filters = [f for f in self.directory.filters if "sAMAccountName" in f]
        self.assertTrue(user_filters)
        for search_filter in user_filters:
            self.assertNotIn("=*)", search_filter)
        self.assertIn(r"(sAMAccountName=\2a)", user_filters[0])
        self.assertIn(r"anna\29\28objectClass=\2a", user_filters[1])

    def test_placeholders_are_replaced_in_one_pass_only(self) -> None:
        filled = ldap_client.fill_template(
            "(&(cn={username})(member={user_dn}))", username="{user_dn}", user_dn="cn=a,dc=x"
        )
        self.assertEqual(filled, "(&(cn={user_dn})(member=cn=a,dc=x))")

    def test_the_dn_in_a_group_filter_is_escaped_too(self) -> None:
        filled = ldap_client.fill_template("(member={user_dn})", user_dn="cn=a*b)(x,dc=y")
        self.assertEqual(filled, r"(member=cn=a\2ab\29\28x,dc=y)")

    def test_a_wildcard_name_does_not_log_in_as_somebody(self) -> None:
        self.assertIsNone(login("a*", "anna-pw"))
        self.assertIsNone(login("an*", "anna-pw"))


class ProtectedAccountTests(DirectoryTestCase):
    """Local (emergency) accounts, superusers and links to other entries are not the directory's."""

    def test_local_account_logs_in_with_its_own_password_and_the_directory_is_not_asked(self) -> None:
        local = make_user("anna", roles=("Administrator",))
        local.local_account = True
        local.save()
        self.assertIsNone(login("anna", "anna-pw"))
        # The directory is asked a dummy question, so that this name costs what any name costs.
        self.assertEqual(len(self.directory.binds), 2)
        self.assertEqual(login("anna", PASSWORD), local)

    def test_a_superuser_is_not_taken_over(self) -> None:
        boss = make_user("anna", superuser=True)
        self.assertIsNone(login("anna", "anna-pw"))
        self.assertEqual(len(self.directory.binds), 2)  # a dummy round trip, see above
        boss.refresh_from_db()
        self.assertEqual(boss.ldap_dn, "")

    def test_an_account_linked_to_another_entry_is_not_taken_over(self) -> None:
        make_user("bernd").__class__.objects.filter(username="bernd").update(ldap_dn=f"cn=bernd,ou=other,{BASE}")
        self.assertIsNone(login("bernd", "bernd-pw"))
        self.assertIn("must not be taken over", SecurityEvent.objects.get(kind=SecurityEventKind.LDAP_REFUSED).detail)

    def test_local_passwords_off_closes_ordinary_local_accounts_only(self) -> None:
        emergency = make_user("notfall", roles=("Administrator",))
        emergency.local_account = True
        emergency.save()
        make_user("bob", roles=("Crew",))
        configure(allow_local_login=False)
        self.assertIsNone(login("bob", PASSWORD))
        self.assertEqual(login("notfall", PASSWORD), emergency)
        user = login("anna", "anna-pw")  # the directory still works
        assert user is not None

    def test_local_passwords_stay_on_by_default(self) -> None:
        bob = make_user("bob", roles=("Crew",))
        self.assertEqual(login("bob", PASSWORD), bob)

    def test_local_passwords_cannot_be_switched_off_without_an_emergency_administrator(self) -> None:
        settings = configure()
        settings.allow_local_login = False
        with self.assertRaises(ValidationError) as caught:
            settings.full_clean()
        self.assertIn("allow_local_login", caught.exception.message_dict)
        emergency = make_user("notfall", roles=("Administrator",))
        emergency.local_account = True
        emergency.save()
        settings.full_clean()  # now it may be switched off
        # An emergency account without the right to change the settings does not count.
        emergency.roles.clear()
        with self.assertRaises(ValidationError):
            settings.full_clean()


class RoleTests(DirectoryTestCase):
    """Union, priority, "last match", manual roles, roles that cannot be taken away."""

    def test_a_role_the_group_no_longer_gives_is_taken_back(self) -> None:
        user = login("bernd", "bernd-pw")
        assert user is not None
        self.directory.change(user.ldap_dn, "memberOf", [PLANNERS])
        user = login("bernd", "bernd-pw")
        assert user is not None
        self.assertEqual(role_names(user), ["Projektleitung"])

    def test_manual_roles_stay(self) -> None:
        user = login("carla", "carla-pw")
        assert user is not None
        user.roles.add(Role.objects.get(name="Lager"))
        self.directory.change(user.ldap_dn, "memberOf", [PLANNERS])
        user = login("carla", "carla-pw")
        assert user is not None
        self.assertEqual(role_names(user), ["Lager", "Projektleitung"])

    def test_a_role_given_by_hand_and_by_the_directory_stays_when_the_directory_takes_it_back(self) -> None:
        by_hand = make_user("carla", roles=("Crew",))
        user = login("carla", "carla-pw")
        assert user is not None
        self.assertEqual(user.pk, by_hand.pk)
        self.assertTrue(LdapRoleAssignment.objects.get(user=user).also_manual)
        self.directory.change(user.ldap_dn, "memberOf", [PLANNERS])
        user = login("carla", "carla-pw")
        assert user is not None
        self.assertEqual(role_names(user), ["Crew", "Projektleitung"])
        self.assertEqual(
            list(LdapRoleAssignment.objects.filter(user=user).values_list("role__name", flat=True)), ["Projektleitung"]
        )

    def test_roles_of_the_directory_cannot_be_taken_away_by_hand(self) -> None:
        user = login("bernd", "bernd-pw")
        assert user is not None
        with self.assertRaises(ValidationError) as caught:
            services.set_user_roles(user, [])
        self.assertIn("Crew", str(caught.exception))
        crew, planner, store = (Role.objects.get(name=name) for name in ("Crew", "Projektleitung", "Lager"))
        services.set_user_roles(user, [crew, planner, store])  # adding one is fine
        self.assertEqual(role_names(user), ["Crew", "Lager", "Projektleitung"])

    def test_priority_orders_the_assignments_and_last_match_ends_the_list(self) -> None:
        LdapGroupMapping.objects.filter(group__icontains="rentalars-admins").update(priority=10, last_match=True)
        self.directory.add_user("erika", "erika-pw", groups=[ADMINS, CREW])
        user = login("erika", "erika-pw")
        assert user is not None
        self.assertEqual(role_names(user), ["Administrator"])  # "last match": the crew assignment does not apply
        LdapGroupMapping.objects.update(last_match=False)
        user = login("erika", "erika-pw")
        assert user is not None
        self.assertEqual(role_names(user), ["Administrator", "Crew"])

    def test_one_group_can_give_several_roles(self) -> None:
        LdapGroupMapping.objects.get(group__icontains="crew").roles.add(Role.objects.get(name="Lager"))
        user = login("carla", "carla-pw")
        assert user is not None
        self.assertEqual(role_names(user), ["Crew", "Lager"])

    def test_a_group_can_be_named_by_its_name_alone_and_without_regard_to_case_and_spacing(self) -> None:
        LdapGroupMapping.objects.all().delete()
        by_name = LdapGroupMapping.objects.create(group="RENTALARS-PLANNERS")
        by_name.roles.set(Role.objects.filter(name="Projektleitung"))
        by_dn = LdapGroupMapping.objects.create(group=" CN=Rentalars-Crew , OU=Groups , DC=example, DC=com ")
        by_dn.roles.set(Role.objects.filter(name="Crew"))
        user = login("bernd", "bernd-pw")
        assert user is not None
        self.assertEqual(role_names(user), ["Crew", "Projektleitung"])
        other_group = LdapGroupMapping.objects.create(group="cn=rentalars-admins,ou=elsewhere,dc=example,dc=com")
        other_group.roles.set(Role.objects.filter(name="Administrator"))
        self.assertIsNone(login("anna", "anna-pw"))  # the group of another place is not that group

    def test_groups_found_by_searching_the_groups(self) -> None:
        directory = FakeDirectory()
        planners = directory.add_group("planners")
        member = directory.add_user("fritz", "fritz-pw")
        directory.change(planners, "member", [member])
        directory.add(f"cn=unix-crew,ou=groups,{BASE}", objectClass=["posixGroup"], cn="unix-crew", memberUid=["fritz"])
        with directory.active():
            configure(
                group_mode="search",
                group_search_base=f"ou=groups,{BASE}",
                group_search_filter="(&(objectClass=groupOfNames)(member={user_dn}))",
            )
            LdapGroupMapping.objects.all().delete()
            LdapGroupMapping.objects.create(group="planners").roles.set(Role.objects.filter(name="Projektleitung"))
            user = login("fritz", "fritz-pw")
            assert user is not None
            self.assertEqual(role_names(user), ["Projektleitung"])
            self.assertIn(f"(member={member})", directory.filters[-1])
            # posixGroup: the group names the user by the login name, not by the DN.
            configure(
                group_mode="search",
                group_search_base=f"ou=groups,{BASE}",
                group_search_filter="(&(objectClass=posixGroup)(memberUid={username}))",
            )
            LdapGroupMapping.objects.create(group="unix-crew").roles.set(Role.objects.filter(name="Crew"))
            LdapGroupMapping.objects.filter(group="planners").delete()
            user = login("fritz", "fritz-pw")
            assert user is not None
            self.assertEqual(role_names(user), ["Crew"])

    def test_the_change_log_notes_what_the_directory_did(self) -> None:
        user = login("bernd", "bernd-pw")
        assert user is not None
        user_type = ContentType.objects.get_for_model(User)
        events = list(
            AuditLogEntry.objects.filter(content_type=user_type, object_id=str(user.pk)).values_list(
                "event", "actor_label"
            )
        )
        self.assertIn(("user.ldap_created", "system:ldap"), events)
        self.assertIn(("user.ldap_roles_changed", "system:ldap"), events)
        kinds = set(SecurityEvent.objects.values_list("kind", flat=True))
        self.assertTrue({SecurityEventKind.LDAP_ACCOUNT, SecurityEventKind.LDAP_ROLES} <= kinds)

    def test_group_assignments_are_unique_regardless_of_spelling(self) -> None:
        duplicate = LdapGroupMapping(group="CN=Rentalars-Crew,OU=Groups,DC=Example,DC=Com")
        with self.assertRaises(ValidationError):
            duplicate.full_clean()


class DeactivationTests(DirectoryTestCase):
    """Whoever is in no group with a role is deactivated; the last administrator is never locked out."""

    def leave_all_groups(self, user: User) -> None:
        self.directory.change(user.ldap_dn, "memberOf", [])

    def test_a_user_who_left_their_groups_is_deactivated_at_the_login_attempt_and_back_again_later(self) -> None:
        user = login("carla", "carla-pw")
        assert user is not None
        self.leave_all_groups(user)
        self.assertIsNone(login("carla", "carla-pw"))
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertIsNotNone(user.ldap_deactivated_at)
        self.assertTrue(AuditLogEntry.objects.filter(event="user.ldap_deactivated").exists())
        # Back in a group: the directory itself closed the account, so the directory opens it again.
        self.directory.change(user.ldap_dn, "memberOf", [CREW])
        again = login("carla", "carla-pw")
        assert again is not None
        self.assertTrue(again.is_active)
        self.assertIsNone(again.ldap_deactivated_at)
        self.assertTrue(AuditLogEntry.objects.filter(event="user.ldap_reactivated").exists())

    def test_an_account_an_administrator_deactivated_stays_closed(self) -> None:
        user = login("carla", "carla-pw")
        assert user is not None
        boss = make_user("boss", superuser=True)
        services.set_user_active(user, active=False, acting_user=boss)
        self.assertIsNone(login("carla", "carla-pw"))
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertIn(
            "deactivated by an administrator", SecurityEvent.objects.get(kind=SecurityEventKind.LDAP_REFUSED).detail
        )

    def test_reactivating_by_hand_clears_the_note_of_the_directory(self) -> None:
        user = login("carla", "carla-pw")
        assert user is not None
        self.leave_all_groups(user)
        login("carla", "carla-pw")
        user.refresh_from_db()
        services.set_user_active(user, active=True)
        user.refresh_from_db()
        self.assertIsNone(user.ldap_deactivated_at)

    def test_an_expired_account_is_refused(self) -> None:
        user = login("carla", "carla-pw")
        assert user is not None
        user.valid_until = timezone.localdate() - datetime.timedelta(days=1)
        user.save()
        self.assertIsNone(login("carla", "carla-pw"))

    def test_the_last_administrator_is_neither_deactivated_nor_stripped_of_the_role(self) -> None:
        anna = login("anna", "anna-pw")
        assert anna is not None
        self.leave_all_groups(anna)
        self.assertIsNone(login("anna", "anna-pw"))  # refused ...
        anna.refresh_from_db()
        self.assertTrue(anna.is_active)  # ... but not locked out of Rentalars for good
        self.directory.change(anna.ldap_dn, "memberOf", [CREW])
        again = login("anna", "anna-pw")
        assert again is not None
        self.assertEqual(role_names(again), ["Administrator"])  # the role stays: nobody else could change the settings
        self.assertTrue(
            SecurityEvent.objects.filter(
                kind=SecurityEventKind.LDAP_ROLES, detail__contains="last administrator"
            ).exists()
        )

    def test_with_another_administrator_around_the_directory_may_deactivate(self) -> None:
        anna = login("anna", "anna-pw")
        assert anna is not None
        make_user("boss", superuser=True)
        self.leave_all_groups(anna)
        self.assertIsNone(login("anna", "anna-pw"))
        anna.refresh_from_db()
        self.assertFalse(anna.is_active)

    def test_an_unlinked_local_account_is_not_deactivated_by_a_refused_login(self) -> None:
        bob = make_user("dieter", roles=("Crew",))
        self.assertIsNone(login("dieter", "dieter-pw"))  # in the directory, in no group
        bob.refresh_from_db()
        self.assertTrue(bob.is_active)
        self.assertEqual(bob.ldap_dn, "")

    def test_directory_accounts_have_no_password_to_reset_in_rentalars(self) -> None:
        user = login("carla", "carla-pw")
        assert user is not None
        self.assertTrue(services.password_is_external(user))
        with self.assertRaises(ValidationError):
            services.set_one_time_password(user)
        with self.assertRaises(ValidationError):
            services.send_invitation(user)
        from rentalars.accounts.forms import ResetPasswordForm

        self.assertEqual(list(ResetPasswordForm().get_users(user.email)), [])
        local = make_user("lokal")
        self.assertFalse(services.password_is_external(local))


class ErrorTests(DirectoryTestCase):
    """What goes wrong is told to the administrator in the security log, never to the user."""

    def test_directory_down_is_noted_and_the_login_fails_politely(self) -> None:
        self.directory.down = True
        self.assertIsNone(login("anna", "anna-pw"))
        self.assertTrue(login.last_request.directory_unavailable)  # type: ignore[attr-defined]
        event = SecurityEvent.objects.get(kind=SecurityEventKind.LDAP_ERROR)
        self.assertIn("unreachable", event.detail)
        self.assertEqual(event.identifier, "anna")

    def test_local_accounts_still_work_while_the_directory_is_down(self) -> None:
        bob = make_user("bob", roles=("Crew",))
        self.directory.down = True
        self.assertEqual(login("bob", PASSWORD), bob)

    def test_a_refused_search_account_is_reported_with_its_name_and_never_its_password(self) -> None:
        settings = configure()
        settings.set_bind_password("not-the-password")
        settings.save()
        self.assertIsNone(login("anna", "anna-pw"))
        event = SecurityEvent.objects.get(kind=SecurityEventKind.LDAP_ERROR)
        self.assertIn("service_bind", event.detail)
        self.assertNotIn("not-the-password", event.detail)

    def test_a_search_base_that_does_not_exist_is_named(self) -> None:
        configure(user_search_base=f"ou=nowhere,{BASE}")
        self.assertIsNone(login("anna", "anna-pw"))
        self.assertIn("ou=nowhere", SecurityEvent.objects.get(kind=SecurityEventKind.LDAP_ERROR).detail)

    def test_a_filter_that_finds_two_entries_is_an_error_not_a_guess(self) -> None:
        self.directory.add_user("anna", "other-pw", ou="people", first="Zweite")
        self.directory.add(
            f"cn=anna2,ou=people,{BASE}",
            objectClass=["person"],
            sAMAccountName="anna",
            userPassword="third",
        )
        self.assertIsNone(login("anna", "anna-pw"))
        self.assertIn("ambiguous", SecurityEvent.objects.get(kind=SecurityEventKind.LDAP_ERROR).detail)

    def test_an_unreadable_stored_password_is_an_error_for_the_administrator(self) -> None:
        settings = configure()
        settings.bind_password_encrypted = "not a token"
        settings.save()
        self.assertIsNone(login("anna", "anna-pw"))
        self.assertIn("nicht mehr lesbar", SecurityEvent.objects.get(kind=SecurityEventKind.LDAP_ERROR).detail)

    def test_no_password_is_ever_written_down(self) -> None:
        login("anna", "anna-pw")
        login("anna", "wrong-pw-1")
        self.directory.down = True
        login("bernd", "bernd-pw")
        dumps = [str(list(SecurityEvent.objects.values()))]
        dumps.append(str(list(AuditLogEntry.objects.values())))
        dumps.append(str(list(LdapSettings.objects.values())))
        from rentalars.accounts.models import LoginAttempt

        dumps.append(str(list(LoginAttempt.objects.values())))
        everything = " ".join(dumps)
        for secret in ("anna-pw", "wrong-pw-1", "bernd-pw", SERVICE_PASSWORD):
            self.assertNotIn(secret, everything)

    def test_the_service_password_is_stored_encrypted(self) -> None:
        stored = LdapSettings.load().bind_password_encrypted
        self.assertTrue(stored)
        self.assertNotIn(SERVICE_PASSWORD, stored)
        self.assertEqual(LdapSettings.load().bind_password, SERVICE_PASSWORD)


class ConnectionReportTests(DirectoryTestCase):
    """ "Test connection": step by step, whatever fails is a step."""

    def report(self) -> ldap_client.ConnectionReport:
        return ldap_client.check_connection(ldap_client.DirectoryConfig.from_settings(LdapSettings.load()))

    def test_everything_in_order(self) -> None:
        report = self.report()
        self.assertTrue(report.ok, report.steps)
        steps = {step["step"]: step for step in report.steps}
        self.assertTrue(steps["Server"]["ok"])
        self.assertEqual(steps["Verbindung und Suchkonto"]["detail"], SERVICE_DN)
        self.assertEqual(steps["Suchbasis für Nutzer"]["detail"], f"ou=people,{BASE}")

    def test_unencrypted_and_unchecked_are_problems(self) -> None:
        configure(server_uris="ldap://fake-directory")
        steps = {step["step"]: step for step in self.report().steps}
        self.assertFalse(steps["Verschlüsselung"]["ok"])
        self.assertIn("nicht verschlüsselt", steps["Verschlüsselung"]["detail"])
        configure(verify_certificate=False)
        self.assertFalse(self.report().ok)

    def test_a_wrong_search_base_and_a_down_server_and_a_wrong_password(self) -> None:
        configure(user_search_base=f"ou=nowhere,{BASE}")
        report = self.report()
        self.assertFalse(report.ok)
        self.assertIn("gibt es nicht", report.steps[-1]["detail"])
        self.directory.down = True
        report = self.report()
        self.assertFalse(report.ok)
        self.assertIn("nicht erreichbar", report.steps[-1]["detail"])
        self.directory.down = False
        settings = configure()
        settings.set_bind_password("wrong")
        settings.save()
        report = self.report()
        self.assertFalse(report.ok)
        self.assertNotIn("wrong", str(report.steps))

    def test_no_server_set(self) -> None:
        configure(server_uris="")
        self.assertFalse(self.report().ok)


class PreviewTests(DirectoryTestCase):
    """ "Test login for user X": found entry, attributes, groups, resulting roles – nothing written."""

    def test_preview_of_a_new_user_writes_nothing(self) -> None:
        accounts = User.objects.count()
        logged = AuditLogEntry.objects.count()
        events = SecurityEvent.objects.count()
        preview = ldap_sync.preview_login(LdapSettings.load(), "bernd")
        self.assertTrue(preview["found"])
        self.assertEqual(preview["action"], "create")
        self.assertEqual(preview["attributes"]["email"], "bernd@example.com")
        self.assertEqual(preview["roles_from_directory"], ["Crew", "Projektleitung"])
        self.assertEqual(
            sorted(preview["matched_assignments"]),
            sorted([f"cn=rentalars-crew,ou=groups,{BASE}", f"cn=rentalars-planners,ou=groups,{BASE}"]),
        )
        self.assertEqual(preview["roles_after"], ["Crew", "Projektleitung"])
        self.assertIsNone(preview["password_ok"])
        # Nothing of the accounts is written, but the use of the test is noted in the security log.
        self.assertEqual(
            (User.objects.count(), AuditLogEntry.objects.count(), SecurityEvent.objects.count()),
            (accounts, logged, events + 1),
        )
        self.assertEqual(SecurityEvent.objects.latest("pk").kind, SecurityEventKind.LDAP_TEST)

    def test_preview_with_a_password_checks_it_without_keeping_it(self) -> None:
        good = ldap_sync.preview_login(LdapSettings.load(), "anna", "anna-pw")
        bad = ldap_sync.preview_login(LdapSettings.load(), "anna", "nope")
        self.assertTrue(good["password_ok"])
        self.assertFalse(bad["password_ok"])
        self.assertNotIn("anna-pw", str(good))

    def test_preview_of_a_user_in_no_group_and_of_an_unknown_one(self) -> None:
        refused = ldap_sync.preview_login(LdapSettings.load(), "dieter")
        self.assertEqual((refused["action"], refused["reason"]), ("refuse", "no_group"))
        unknown = ldap_sync.preview_login(LdapSettings.load(), "gibtsnicht")
        self.assertFalse(unknown["found"])

    def test_preview_of_an_existing_account_shows_roles_before_and_after(self) -> None:
        make_user("carla", roles=("Lager",))
        preview = ldap_sync.preview_login(LdapSettings.load(), "carla")
        self.assertEqual(preview["action"], "link")
        self.assertEqual(preview["roles_before"], ["Lager"])
        self.assertEqual(preview["roles_after"], ["Crew", "Lager"])

    def test_preview_of_an_unusable_name_raises(self) -> None:
        with self.assertRaises(ValueError):
            ldap_sync.preview_login(LdapSettings.load(), "  ")


class SyncTests(DirectoryTestCase):
    """The comparison of all accounts, by hand and every night."""

    def setUp(self) -> None:
        super().setUp()
        make_user("boss", superuser=True)  # another administrator, so that anna may be deactivated
        for name in ("anna", "bernd", "carla"):
            assert login(name, f"{name}-pw") is not None

    def test_dry_run_changes_nothing(self) -> None:
        carla = User.objects.get(username="carla")
        self.directory.remove(carla.ldap_dn)
        self.directory.change(User.objects.get(username="bernd").ldap_dn, "memberOf", [PLANNERS])
        before = list(User.objects.order_by("pk").values_list("pk", "is_active", "last_name"))
        logged = AuditLogEntry.objects.count()
        report = ldap_sync.compare_accounts(LdapSettings.load())
        self.assertFalse(report.applied)
        self.assertEqual(report.counts.get("deactivate"), 1)
        self.assertEqual(report.counts.get("update"), 1)
        self.assertEqual(list(User.objects.order_by("pk").values_list("pk", "is_active", "last_name")), before)
        self.assertEqual(AuditLogEntry.objects.count(), logged)
        self.assertIsNone(LdapSettings.load().last_sync_at)

    def test_apply_writes_the_differences(self) -> None:
        carla = User.objects.get(username="carla")
        self.directory.remove(carla.ldap_dn)
        bernd = User.objects.get(username="bernd")
        self.directory.change(bernd.ldap_dn, "memberOf", [PLANNERS])
        self.directory.change(bernd.ldap_dn, "givenName", ["Berndt"])
        report = ldap_sync.compare_accounts(LdapSettings.load(), apply=True)
        self.assertTrue(report.applied)
        carla.refresh_from_db()
        bernd.refresh_from_db()
        self.assertFalse(carla.is_active)
        self.assertEqual((bernd.first_name, role_names(bernd)), ("Berndt", ["Projektleitung"]))
        settings = LdapSettings.load()
        self.assertIsNotNone(settings.last_sync_at)
        self.assertIn("deactivate", settings.last_sync_summary)
        self.assertTrue(SecurityEvent.objects.filter(kind=SecurityEventKind.LDAP_SYNC).exists())

    def test_nobody_is_created_by_the_comparison(self) -> None:
        count = User.objects.count()
        ldap_sync.compare_accounts(LdapSettings.load(), apply=True)
        self.assertEqual(User.objects.count(), count)

    def test_local_accounts_are_left_alone(self) -> None:
        emergency = make_user("notfall", roles=("Administrator",))
        emergency.ldap_dn = f"cn=notfall,ou=people,{BASE}"
        emergency.local_account = True
        emergency.save()
        ldap_sync.compare_accounts(LdapSettings.load(), apply=True)
        emergency.refresh_from_db()
        self.assertTrue(emergency.is_active)

    def test_a_comparison_that_would_close_most_accounts_stops(self) -> None:
        for number in range(5):
            self.directory.add_user(f"extra{number}", "pw", groups=[CREW])
            assert login(f"extra{number}", "pw") is not None
        for user in User.objects.exclude(ldap_dn="").exclude(username="anna"):
            self.directory.remove(user.ldap_dn)
        report = ldap_sync.compare_accounts(LdapSettings.load(), apply=True)
        self.assertTrue(report.stopped)
        self.assertFalse(report.applied)
        self.assertEqual(User.objects.filter(is_active=False).count(), 0)
        forced = ldap_sync.compare_accounts(LdapSettings.load(), apply=True, force=True)
        self.assertTrue(forced.applied)
        self.assertEqual(User.objects.filter(is_active=False).count(), 7)

    def test_a_directory_that_does_not_answer_changes_nothing(self) -> None:
        self.directory.down = True
        with self.assertRaises(ldap_client.DirectoryError):
            ldap_sync.compare_accounts(LdapSettings.load(), apply=True)
        self.assertEqual(User.objects.filter(is_active=False).count(), 0)

    def test_the_nightly_comparison_is_off_unless_switched_on(self) -> None:
        self.directory.remove(User.objects.get(username="carla").ldap_dn)
        self.assertIn("not switched on", ldap_sync.sync_nightly())
        self.assertTrue(User.objects.get(username="carla").is_active)
        configure(sync_daily=True)
        self.assertIn("deactivate", ldap_sync.sync_nightly())
        self.assertFalse(User.objects.get(username="carla").is_active)

    def test_the_nightly_comparison_survives_a_down_directory(self) -> None:
        configure(sync_daily=True)
        self.directory.down = True
        self.assertIn("failed", ldap_sync.sync_nightly())
        self.assertTrue(SecurityEvent.objects.filter(kind=SecurityEventKind.LDAP_ERROR).exists())

    def test_the_daily_maintenance_runs_the_comparison(self) -> None:
        configure(sync_daily=True)
        self.directory.remove(User.objects.get(username="carla").ldap_dn)
        out = self.call("run_daily_maintenance")
        self.assertIn("Directory (LDAP):", out)
        self.assertFalse(User.objects.get(username="carla").is_active)

    def call(self, *args: str) -> str:
        from io import StringIO

        out = StringIO()
        call_command(*args, stdout=out)
        return out.getvalue()

    def test_the_command_is_a_dry_run_unless_told_otherwise(self) -> None:
        self.directory.remove(User.objects.get(username="carla").ldap_dn)
        out = self.call("ldap_sync")
        self.assertIn("carla: deactivate", out)
        self.assertIn("Dry run", out)
        self.assertTrue(User.objects.get(username="carla").is_active)
        self.assertIn("Dry run", self.call("ldap_sync", "--dry-run"))
        out = self.call("ldap_sync", "--apply")
        self.assertIn("Applied", out)
        self.assertFalse(User.objects.get(username="carla").is_active)

    def test_the_command_refuses_contradictions_and_a_switched_off_directory(self) -> None:
        with self.assertRaises(CommandError):
            call_command("ldap_sync", "--apply", "--dry-run")
        configure(enabled=False)
        with self.assertRaises(CommandError):
            call_command("ldap_sync")

    def test_the_command_stops_on_a_directory_that_does_not_answer(self) -> None:
        self.directory.down = True
        with self.assertRaises(CommandError) as caught:
            call_command("ldap_sync", "--apply")
        self.assertIn("unreachable", str(caught.exception))


class HelperTests(RentalarsTestCase):
    """Names, filters, addresses and groups."""

    def test_usernames(self) -> None:
        self.assertEqual(ldap_client.normalise_username("  anna  "), "anna")
        for bad in ("", "   ", "a\x00b", "a\nb", "x" * 300):
            with self.assertRaises(ValueError):
                ldap_client.normalise_username(bad)

    def test_filters(self) -> None:
        ldap_client.validate_filter("(&(objectClass=person)(uid={username}))", {"{username}"})
        for bad in ("(&(objectClass=person)(uid={username})", "(uid={username}", "uid={username}", "(uid={nope})"):
            with self.assertRaises(ValidationError, msg=bad):
                ldap_client.validate_filter(bad, {"{username}"})
        with self.assertRaises(ValidationError):
            ldap_client.validate_filter("(objectClass=person)", {"{username}"})
        ldap_client.validate_group_filter("")
        ldap_client.validate_group_filter("(member={user_dn})")
        ldap_client.validate_group_filter("(memberUid={username})")
        with self.assertRaises(ValidationError):
            ldap_client.validate_group_filter("(member=fixed)")

    def test_server_addresses(self) -> None:
        ldap_client.validate_server_uris("ldaps://dc1.example.com\nldap://ldap.example.com:389\n\n")
        self.assertEqual(ldap_client.parse_uri("ldaps://dc1.example.com"), ("dc1.example.com", 636, True))
        self.assertEqual(ldap_client.parse_uri("ldap://ldap.example.com:1389/"), ("ldap.example.com", 1389, False))
        for bad in (
            "dc1.example.com",
            "http://dc1.example.com",
            "ldap://",
            "ldap://u:p@host",
            "ldap://host/ou=x",
            "ldap://host?x",
        ):
            with self.assertRaises(ValidationError, msg=bad):
                ldap_client.validate_server_uris(bad)

    def test_an_internal_address_needs_the_leave_of_the_operator(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            ldap_client.validate_server_uris("ldaps://10.1.2.3")
        self.assertIn("allow_internal", str(caught.exception))
        ldap_client.validate_server_uris("ldaps://127.0.0.1")  # the tests allow 127.0.0.0/8

    def test_pem(self) -> None:
        ldap_client.validate_pem("")
        with self.assertRaises(ValidationError):
            ldap_client.validate_pem("-----BEGIN CERTIFICATE-----\nnonsense\n-----END CERTIFICATE-----")
        ldap_client.validate_pem(certificate_pem())

    def test_group_keys(self) -> None:
        self.assertEqual(ldap_client.group_key("admins"), "name:admins")
        self.assertEqual(ldap_client.group_key("CN=Admins"), "name:admins")
        self.assertEqual(ldap_client.group_key("Domain  Admins"), "name:domain admins")
        self.assertEqual(
            ldap_client.group_key("CN=Smith\\, J, OU=Groups , DC=Example,DC=com"),
            ldap_client.group_key("cn=smith\\2c j,ou=groups,dc=example,dc=com"),
        )
        self.assertTrue(ldap_client.group_key("cn=a,dc=x").startswith("dn:"))

    def test_group_matching(self) -> None:
        by_name = ldap_client.group_key("Domain Admins")
        self.assertTrue(ldap_client.group_matches(by_name, "CN=Domain Admins,CN=Users,DC=corp,DC=example"))
        self.assertFalse(ldap_client.group_matches(by_name, "CN=Domain Users,CN=Users,DC=corp,DC=example"))
        # Only the first part counts for a name: "Users" is not "Domain Admins" in the container Users.
        self.assertFalse(ldap_client.group_matches(ldap_client.group_key("Users"), "CN=Domain Admins,CN=Users,DC=x"))
        by_dn = ldap_client.group_key("cn=a,ou=g,dc=x")
        self.assertTrue(ldap_client.group_matches(by_dn, "CN=A, OU=G, DC=X"))
        self.assertFalse(ldap_client.group_matches(by_dn, "cn=a,ou=h,dc=x"))
        self.assertTrue(ldap_client.group_matches(ldap_client.group_key("admins"), "admins"))  # a bare name


def certificate_pem() -> str:
    """A self-signed certificate for the tests of the certificate checks."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ldap.example.com")])
    now = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    return certificate.public_bytes(serialization.Encoding.PEM).decode()


def answer(host: str, port: int, address: str = "127.0.0.1") -> list[tuple[Any, ...]]:
    """What ``network.checked_addresses`` returns for a host."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]


class RealFactoryTests(RentalarsTestCase):
    """The real connection factory: built, not opened (the network guard, the certificate name, TLS, read-only)."""

    def config(self, **changes: Any) -> ldap_client.DirectoryConfig:
        settings = LdapSettings(
            server_uris="ldaps://ldap.example.com",
            bind_dn=SERVICE_DN,
            user_search_base=f"ou=people,{BASE}",
            **changes,
        )
        settings.set_bind_password(SERVICE_PASSWORD)
        return ldap_client.DirectoryConfig.from_settings(settings)

    def test_the_connection_goes_to_the_checked_address_and_the_certificate_is_checked_against_the_name(self) -> None:
        with mock.patch.object(network, "checked_addresses", return_value=answer("ldap.example.com", 636, "192.0.2.7")):
            connection = ldap_client._real_factory(self.config(), SERVICE_DN, SERVICE_PASSWORD)
        server = connection.server
        self.assertEqual((server.host, server.port, server.ssl), ("192.0.2.7", 636, True))
        self.assertEqual(server.tls.validate, ssl.CERT_REQUIRED)
        self.assertEqual(server.tls.valid_names, ["ldap.example.com"])
        self.assertEqual(server.tls.sni, "ldap.example.com")
        self.assertTrue(connection.read_only)
        self.assertFalse(connection.auto_referrals)
        self.assertEqual(connection.user, SERVICE_DN)

    def test_a_blocked_address_is_an_error_for_the_administrator(self) -> None:
        blocked = network.BlockedAddressError("ldap.example.com", "10.0.0.1")
        with (
            mock.patch.object(network, "checked_addresses", side_effect=blocked),
            self.assertRaises(ldap_client.DirectoryError) as caught,
        ):
            ldap_client._real_factory(self.config(), "", "")
        self.assertEqual(caught.exception.code, "blocked")
        self.assertIn("allow_internal", str(caught.exception))
        self.assertNotIn("10.0.0.1", str(caught.exception))

    def test_an_unknown_name_is_unreachable(self) -> None:
        with (
            mock.patch.object(network, "checked_addresses", side_effect=socket.gaierror("no such host")),
            self.assertRaises(ldap_client.DirectoryError) as caught,
        ):
            ldap_client._real_factory(self.config(), "", "")
        self.assertEqual(caught.exception.code, "unreachable")

    def test_ca_certificate_and_switched_off_check(self) -> None:
        pem = certificate_pem()
        with mock.patch.object(network, "checked_addresses", return_value=answer("ldap.example.com", 636)):
            connection = ldap_client._real_factory(self.config(ca_certificate_pem=pem), "", "")
            unchecked = ldap_client._real_factory(self.config(verify_certificate=False), "", "")
        self.assertEqual(connection.server.tls.ca_certs_data.strip(), pem.strip())
        self.assertEqual(unchecked.server.tls.validate, ssl.CERT_NONE)

    def test_several_servers_make_a_pool_and_ldap_with_starttls_has_tls_but_no_ssl(self) -> None:
        settings = LdapSettings(server_uris="ldap://one.example.com\nldap://two.example.com:1389", start_tls=True)
        config = ldap_client.DirectoryConfig.from_settings(settings)
        with mock.patch.object(network, "checked_addresses", side_effect=lambda host, port: answer(host, port)):
            connection = ldap_client._real_factory(config, "", "")
        self.assertEqual(len(connection.server_pool.servers), 2)
        first = connection.server_pool.servers[0]
        self.assertFalse(first.ssl)
        self.assertIsNotNone(first.tls)
        self.assertEqual(connection.server_pool.servers[1].port, 1389)

    def test_anonymous_search_when_no_account_is_set(self) -> None:
        settings = LdapSettings(server_uris="ldaps://ldap.example.com")
        config = ldap_client.DirectoryConfig.from_settings(settings)
        with mock.patch.object(network, "checked_addresses", return_value=answer("ldap.example.com", 636)):
            connection = ldap_client._real_factory(config, "", "")
        self.assertEqual(connection.authentication, "ANONYMOUS")

    def test_a_closed_port_is_unreachable_not_a_crash(self) -> None:
        """The one place the real network is used: a port on this machine where nobody listens."""
        settings = LdapSettings(server_uris="ldap://127.0.0.1:1", timeout_seconds=2)
        config = ldap_client.DirectoryConfig.from_settings(settings)
        with self.assertRaises(ldap_client.DirectoryError) as caught:
            ldap_client.open_service_connection(config)
        self.assertEqual(caught.exception.code, "unreachable")

    def test_starttls_that_the_server_refuses_is_an_error(self) -> None:
        class Stub:
            result = {"description": "protocolError"}

            def open(self) -> None: ...

            def start_tls(self) -> bool:
                return False

        config = self.config(start_tls=True)
        config = ldap_client.DirectoryConfig.from_settings(
            LdapSettings(server_uris="ldap://x.example.com", start_tls=True)
        )
        with self.assertRaises(ldap_client.DirectoryError) as caught:
            ldap_client._bind(Stub(), config)  # type: ignore[arg-type]
        self.assertEqual(caught.exception.code, "tls")

    def test_a_service_account_without_a_password_is_refused_before_anything_is_sent(self) -> None:
        settings = LdapSettings(server_uris="ldaps://ldap.example.com", bind_dn=SERVICE_DN)
        config = ldap_client.DirectoryConfig.from_settings(settings)
        with (
            mock.patch.object(ldap_client, "_factory") as factory,
            self.assertRaises(ldap_client.DirectoryError) as caught,
        ):
            ldap_client.open_service_connection(config)
        self.assertEqual(caught.exception.code, "service_bind")
        factory.assert_not_called()


class MigrationTests(TransactionTestCase):
    """The update: the LDAP tables and columns come with it and can be taken away again (reverse)."""

    before = [("accounts", "0009_role_defaults_094")]
    after = [("accounts", "0010_ldap_login_100")]

    def tearDown(self) -> None:
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def migrate(self, targets: list[tuple[str, str]]) -> Any:
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def columns(self, table: str) -> set[str]:
        with connection.cursor() as cursor:
            return {column.name for column in connection.introspection.get_table_description(cursor, table)}

    def test_forward_keeps_the_users_and_reverse_removes_the_tables(self) -> None:
        old = self.migrate(self.before)
        user_model = old.get_model("accounts", "User")
        user = user_model.objects.create(username="alt", email="alt@example.de", password="!")
        self.assertNotIn("ldap_dn", self.columns("accounts_user"))
        self.assertNotIn("accounts_ldapsettings", connection.introspection.table_names())
        new = self.migrate(self.after)
        found = new.get_model("accounts", "User").objects.get(pk=user.pk)
        self.assertEqual((found.ldap_dn, found.local_account, found.ldap_synced_at), ("", False, None))
        self.assertIn("ldap_dn", self.columns("accounts_user"))
        tables = connection.introspection.table_names()
        for table in ("accounts_ldapsettings", "accounts_ldapgroupmapping", "accounts_ldaproleassignment"):
            self.assertIn(table, tables)
        self.migrate(self.before)
        self.assertNotIn("accounts_ldapsettings", connection.introspection.table_names())
        self.assertEqual(old.get_model("accounts", "User").objects.get(pk=user.pk).username, "alt")
