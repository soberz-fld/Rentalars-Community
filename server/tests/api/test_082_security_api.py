# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests, area "security": API-010 (idempotency bound to caller and rights), NFA-071 (internal
addresses in webhooks, calendars and mailboxes through the API), NFA-073 (the self-check)."""

from __future__ import annotations

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from rentalars.accounts.models import ApiToken, Role
from rentalars.api.models import IdempotentCall, Webhook
from rentalars.customers.models import Customer
from rentalars.personnel.models import Person
from tests.api.base import API, ApiTestCase
from tests.helpers import make_customer, make_project, make_user
from tests.mailbox import configure_mailbox

NOTHING_ALLOWED = override_settings(RENTALARS_NETWORK_ALLOW_INTERNAL=())


class IdempotencyBoundToTheCallerTests(ApiTestCase):
    """API-010: a stored answer only after login and the current rights – and only for its caller."""

    def setUp(self) -> None:
        super().setUp()
        Role.objects.create(name="Kundenpflege", module_levels={"customers": 2})
        self.user = make_user("kai", roles=("Kundenpflege",))
        self.token, self.key = ApiToken.create_for_user(self.user, "app")
        self.client_ = APIClient()
        self.client_.credentials(HTTP_AUTHORIZATION=f"Bearer {self.key}")

    def create(self, client: APIClient, name: str = "Kulturverein", key: str = "k-1") -> object:
        return client.post(f"{API}/customers", {"name": name}, format="json", HTTP_IDEMPOTENCY_KEY=key)

    def test_a_revoked_token_does_not_get_the_stored_answer(self) -> None:
        """API-010: the security fix – the stored answer does not come without a login check."""
        self.assertEqual(self.create(self.client_).status_code, 201)
        ApiToken.objects.filter(pk=self.token.pk).update(revoked_at=timezone.now())
        again = self.create(self.client_)
        self.assert_error(again, 401, "not_authenticated")
        self.assertNotIn("Idempotent-Replayed", again)
        self.assertNotIn(b"Kulturverein", again.content)

    def test_a_caller_who_lost_the_right_gets_the_refusal(self) -> None:
        """API-010: the rights are those of now, as for a new call."""
        self.assertEqual(self.create(self.client_).status_code, 201)
        self.user.roles.clear()
        again = self.create(self.client_)
        self.assert_error(again, 403, "permission_denied")
        self.assertNotIn("Idempotent-Replayed", again)

    def test_another_caller_never_gets_it(self) -> None:
        """API-010: another token of the same user, another user, a browser session – each has keys of its own."""
        first = self.create(self.client_)
        self.assertEqual(first.status_code, 201)
        other_token, other_key = ApiToken.create_for_user(self.user, "second")
        others = [APIClient(), self.admin]
        others[0].credentials(HTTP_AUTHORIZATION=f"Bearer {other_key}")
        session = APIClient()
        session.force_login(self.admin_user)
        for client in (*others, session):
            answer = self.create(client)
            self.assertEqual(answer.status_code, 201, answer.content)
            self.assertNotIn("Idempotent-Replayed", answer)
            self.assertNotEqual(answer.json()["id"], first.json()["id"])
        self.assertEqual(Customer.objects.filter(name="Kulturverein").count(), 4)
        scopes = set(IdempotentCall.objects.values_list("scope", flat=True))
        self.assertEqual(len(scopes), 4)
        self.assertTrue({f"token:{self.token.pk}", f"token:{other_token.pk}", f"user:{self.admin_user.pk}"} <= scopes)

    def test_the_same_caller_with_another_body_gets_409(self) -> None:
        self.create(self.client_)
        other = self.create(self.client_, name="Anderer Verein")
        self.assert_error(other, 409, "idempotency_key_reused")
        self.assertEqual(Customer.objects.count(), 1)
        # The same body to another address is another call as well.
        moved = self.client_.post(
            f"{API}/customers?x=1", {"name": "Kulturverein"}, format="json", HTTP_IDEMPOTENCY_KEY="k-1"
        )
        self.assert_error(moved, 409, "idempotency_key_reused")

    def test_the_repetition_works_as_before(self) -> None:
        """The case of a lost answer: the answer is lost on the way and the call sent again."""
        first = self.create(self.client_)
        again = self.create(self.client_)
        self.assertEqual((again.status_code, again["Idempotent-Replayed"]), (201, "true"))
        self.assertEqual(again.json(), first.json())
        self.assertEqual(Customer.objects.count(), 1)

    def test_without_login_a_key_changes_nothing(self) -> None:
        answer = APIClient().post(f"{API}/customers", {"name": "X"}, format="json", HTTP_IDEMPOTENCY_KEY="k-1")
        self.assert_error(answer, 401, "not_authenticated")
        self.assertFalse(IdempotentCall.objects.exists())


class IfMatchWithKeyTests(ApiTestCase):
    """API-010: a change with ``If-Match`` and a key, sent again, gets its answer – not 412 for its own change."""

    def test_repeating_a_change_with_if_match(self) -> None:
        customer = make_customer("Kulturverein")
        url = f"{API}/customers/{customer.pk}"
        tag = self.admin.get(url)["ETag"]
        first = self.admin.patch(url, {"city": "Dorf"}, format="json", HTTP_IF_MATCH=tag, HTTP_IDEMPOTENCY_KEY="p-1")
        self.assertEqual(first.status_code, 200, first.content)
        again = self.admin.patch(url, {"city": "Dorf"}, format="json", HTTP_IF_MATCH=tag, HTTP_IDEMPOTENCY_KEY="p-1")
        self.assertEqual((again.status_code, again["Idempotent-Replayed"]), (200, "true"))
        stale = self.admin.patch(url, {"city": "Stadt"}, format="json", HTTP_IF_MATCH=tag, HTTP_IDEMPOTENCY_KEY="p-2")
        self.assert_error(stale, 412, "precondition_failed")
        # A deleted record: the repetition of the DELETE gets its 204 again.
        fresh = self.admin.get(url)["ETag"]
        deleted = self.admin.delete(url, HTTP_IF_MATCH=fresh, HTTP_IDEMPOTENCY_KEY="d-1")
        self.assertEqual(deleted.status_code, 204, deleted.content)
        repeated = self.admin.delete(url, HTTP_IF_MATCH=fresh, HTTP_IDEMPOTENCY_KEY="d-1")
        self.assertEqual((repeated.status_code, repeated["Idempotent-Replayed"]), (204, "true"))


@NOTHING_ALLOWED
class InternalAddressesThroughTheApiTests(ApiTestCase):
    """NFA-071: webhooks, calendars and mailboxes through the API."""

    def test_a_webhook_to_an_internal_address(self) -> None:
        body = {"url": "http://192.168.1.20/rentalars", "events": ["project.created"]}
        refused = self.admin.post(f"{API}/webhooks", body, format="json", HTTP_ACCEPT_LANGUAGE="de")
        error = self.assert_error(refused, 400, "validation_error", "url")
        self.assertIn("internes Netz", error["fields"]["url"][0]["message"])
        self.assertFalse(Webhook.objects.exists())
        with override_settings(RENTALARS_NETWORK_ALLOW_INTERNAL=("192.168.1.0/24",)):
            created = self.admin.post(f"{API}/webhooks", body, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        changed = self.admin.patch(
            f"{API}/webhooks/{created.json()['id']}", {"url": "http://10.0.0.1/x"}, format="json"
        )
        self.assert_error(changed, 400, "validation_error", "url")

    def test_calendar_addresses_inside(self) -> None:
        user = make_user("carla", roles=("Crew",))
        client = self.client_of(user)
        settings = f"{API}/people/me/calendars"
        feed = client.post(f"{settings}/feeds", {"url": "http://127.0.0.1:5232/carla.ics"}, format="json")
        self.assert_error(feed, 400, "validation_error", "url")
        caldav = client.patch(
            settings,
            {"caldav_url": "http://localhost:5232/", "caldav_username": "carla", "caldav_password": "x"},
            format="json",
        )
        self.assert_error(caldav, 400, "validation_error", "caldav_url")
        self.assertEqual(Person.objects.get(user=user).caldav_url, "")

    def test_checking_a_mailbox_inside(self) -> None:
        mailbox = configure_mailbox()
        mailbox.imap_host = mailbox.smtp_host = "10.0.0.25"
        mailbox.save()
        answer = self.admin.post(f"{API}/mail/mailboxes/{mailbox.pk}/check", HTTP_ACCEPT_LANGUAGE="de")
        self.assertEqual(answer.status_code, 200, answer.content)
        texts = str(answer.json())
        self.assertIn("internes Netz", texts)

    def test_the_self_check_names_them(self) -> None:
        user = make_user("carla", roles=("Crew",))
        Person.objects.filter(user=user).update(caldav_url="http://192.168.1.5/dav/")
        findings = self.admin.get(f"{API}/self-check", HTTP_ACCEPT_LANGUAGE="de").json()["findings"]
        internal = next(item for item in findings if item["title"] == "Interne Adressen")
        self.assertEqual(internal["state"], "warning")
        self.assertIn("192.168.1.5", internal["detail"])


class ReplayAfterProjectAccessWasRemovedTests(ApiTestCase):
    """API-010 (review): handlers that check the project only inside are covered as well."""

    def setUp(self) -> None:
        super().setUp()
        from rentalars.projects.models import ProjectMembership

        Role.objects.create(name="Freie Planung", module_levels={"projects": 4}, project_scope="assigned")
        self.user = make_user("frieda", roles=("Freie Planung",))
        self.project = make_project("Stadtfest")
        self.membership = ProjectMembership.objects.create(project=self.project, user=self.user, level="edit")
        self.client_ = self.client_of(self.user)

    def call(self, path: str, body: dict[str, object], key: str) -> object:
        return self.client_.post(path, body, format="json", HTTP_IDEMPOTENCY_KEY=key)

    def test_a_trip_is_not_answered_once_the_membership_is_gone(self) -> None:
        """The case from the review: ``trips`` checks the project inside its handler (``project_for``)."""
        path = f"{API}/projects/{self.project.pk}/trips"
        body = {"start": "2027-03-10T10:00:00+01:00", "origin": "Lager A", "destination": "Halle B"}
        self.assertEqual(self.call(path, body, "t-1").status_code, 201)
        self.membership.delete()
        self.assert_error(self.call(path, body, "t-2"), 404, "not_found")  # a new call
        again = self.call(path, body, "t-1")
        self.assert_error(again, 404, "not_found")
        self.assertNotIn("Idempotent-Replayed", again)

    def test_less_access_than_the_call_relied_on_is_refused(self) -> None:
        path = f"{API}/projects/{self.project.pk}/groups"
        self.assertEqual(self.call(path, {"name": "Bühne"}, "g-1").status_code, 201)
        self.membership.level = "read"
        self.membership.save()
        self.assert_error(self.call(path, {"name": "Bühne"}, "g-1"), 403, "permission_denied")
        self.membership.level = "edit"
        self.membership.save()
        again = self.call(path, {"name": "Bühne"}, "g-1")
        self.assertEqual((again.status_code, again["Idempotent-Replayed"]), (201, "true"))
