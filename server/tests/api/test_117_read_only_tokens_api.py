# SPDX-License-Identifier: GPL-3.0-or-later
"""S9 of the security review: a read-only token changes nothing, not even the settings of its user."""

from __future__ import annotations

from django.utils import timezone

from rentalars.accounts.models import ApiToken, UserSession
from rentalars.notifications.models import Kind, Notification
from tests.api.base import API, ApiTestCase
from tests.helpers import make_user


class ReadOnlyTokenTests(ApiTestCase):
    """The endpoints that only ask for a login also refuse a read-only token to change something."""

    def setUp(self) -> None:
        super().setUp()
        self.reader = self.client_for("lesen", "Projektleitung", read_only=True)
        self.writer = self.client_for("schreiben", "Projektleitung")
        self.reader_user = ApiToken.objects.filter(read_only=True).get().user

    def test_tokens_are_not_revoked(self) -> None:
        other, _key = ApiToken.create_for_user(self.reader_user, "Laptop")
        self.assert_error(self.reader.delete(f"{API}/tokens/{other.pk}"), 403, "permission_denied")
        other.refresh_from_db()
        self.assertIsNone(other.revoked_at)
        self.assertEqual(self.reader.get(f"{API}/tokens").status_code, 200)

    def test_sessions_are_not_ended(self) -> None:
        session = UserSession.objects.create(user=self.reader_user, session_key="abc", last_activity=timezone.now())
        self.assert_error(self.reader.delete(f"{API}/me/sessions/{session.pk}"), 403, "permission_denied")
        self.assertTrue(UserSession.objects.filter(pk=session.pk).exists())
        self.assertEqual(self.reader.get(f"{API}/me/sessions").status_code, 200)

    def test_notification_choices_are_not_changed(self) -> None:
        url = f"{API}/notifications/preferences"
        before = self.reader.get(url).json()
        kind = before[0]["kind"]
        body = [{"kind": kind, "in_app": not before[0]["in_app"], "by_email": not before[0]["by_email"]}]
        self.assert_error(self.reader.put(url, body, format="json"), 403, "permission_denied")
        self.assertEqual(self.reader.get(url).json(), before)

    def test_notifications_are_not_marked_as_read(self) -> None:
        note = Notification.objects.create(user=self.reader_user, kind=Kind.values[0], title="x")
        self.assert_error(self.reader.post(f"{API}/notifications/read", {}, format="json"), 403, "permission_denied")
        note.refresh_from_db()
        self.assertIsNone(note.read_at)

    def test_a_token_that_may_write_still_can(self) -> None:
        url = f"{API}/notifications/preferences"
        before = self.writer.get(url).json()
        body = [{"kind": before[0]["kind"], "in_app": not before[0]["in_app"], "by_email": before[0]["by_email"]}]
        self.assertEqual(self.writer.put(url, body, format="json").status_code, 200)
        self.assertEqual(self.writer.post(f"{API}/notifications/read", {}, format="json").status_code, 200)


class SupplierMapsTests(ApiTestCase):
    """S10: Crew and Freie Kräfte read projects, but suppliers are not theirs to see."""

    def setUp(self) -> None:
        super().setUp()
        from rentalars.masterdata.models import Supplier

        self.supplier = Supplier.objects.create(name="Nord Verleih", street="Verleihstraße 9", city="Nordstadt")

    def test_crew_and_free_workers_get_403_on_both_addresses(self) -> None:
        from django.urls import reverse

        for role in ("Crew", "Freie Kraft"):
            with self.subTest(role=role):
                person = make_user(role.replace(" ", "").lower(), roles=(role,))
                client = self.client_of(person)
                self.assert_error(client.get(f"{API}/maps/supplier/{self.supplier.pk}"), 403, "permission_denied")
                self.client.force_login(person)
                url = reverse("core:map", args=["supplier", self.supplier.pk])
                self.assertEqual(self.client.get(url).status_code, 403)
                suggest = self.client.get(reverse("projects:supplier_suggest"), {"q": "Nord"})
                self.assertEqual(suggest.status_code, 403)
                self.assertNotIn("Nord Verleih", suggest.content.decode())

    def test_those_who_plan_or_keep_the_material_still_see_it(self) -> None:
        for role in ("Projektleitung", "Nur-Lesen"):
            with self.subTest(role=role):
                client = self.client_for(role.lower(), role)
                self.assertEqual(client.get(f"{API}/maps/supplier/{self.supplier.pk}").status_code, 200)
        self.assertEqual(self.admin.get(f"{API}/maps/supplier/{self.supplier.pk}").status_code, 200)
