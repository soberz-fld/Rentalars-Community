# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests of the protection against too many calls, repeated calls and overwriting (API-010, API-011)."""

from __future__ import annotations

import datetime

from django.utils import timezone

from rentalars.api.models import ApiCallCount, IdempotentCall
from rentalars.api.safeguards import delete_old_call_counts
from rentalars.core.models import SystemSettings
from rentalars.customers.models import Customer
from tests.api.base import API, ApiTestCase
from tests.helpers import make_customer


class RateLimitTests(ApiTestCase):
    """API-011."""

    def test_calls_per_token_and_minute(self) -> None:
        SystemSettings.objects.update(api_requests_per_minute=3)
        answers = [self.admin.get(f"{API}/customers") for _ in range(3)]
        self.assertEqual([answer.status_code for answer in answers], [200, 200, 200])
        self.assertEqual((answers[0]["X-RateLimit-Limit"], answers[2]["X-RateLimit-Remaining"]), ("3", "0"))
        refused = self.admin.get(f"{API}/customers")
        self.assert_error(refused, 429, "throttled")
        self.assertIn("Retry-After", refused)
        # Another token of the same user has a minute of its own.
        self.assertEqual(self.client_of(self.admin_user).get(f"{API}/customers").status_code, 200)
        # The browser (a session) is not counted.
        self.client.force_login(self.admin_user)
        self.assertEqual(self.client.get(f"{API}/customers").status_code, 200)
        SystemSettings.objects.update(api_requests_per_minute=0)
        self.assertEqual(self.admin.get(f"{API}/customers").status_code, 200)

    def test_old_counts_are_removed(self) -> None:
        self.admin.get(f"{API}/customers")
        ApiCallCount.objects.update(minute=timezone.now() - datetime.timedelta(hours=2))
        self.assertEqual(delete_old_call_counts(), 1)


class IdempotencyTests(ApiTestCase):
    """API-010: a changing call with an Idempotency-Key is carried out once."""

    def test_the_same_call_twice_creates_one_customer(self) -> None:
        body = {"name": "Kulturverein"}
        first = self.admin.post(f"{API}/customers", body, format="json", HTTP_IDEMPOTENCY_KEY="a1")
        second = self.admin.post(f"{API}/customers", body, format="json", HTTP_IDEMPOTENCY_KEY="a1")
        self.assertEqual((first.status_code, second.status_code), (201, 201))
        self.assertEqual(first.json(), second.json())
        self.assertEqual(second["Idempotent-Replayed"], "true")
        self.assertEqual(Customer.objects.count(), 1)
        # Without a key, or with a new one, every call counts.
        self.admin.post(f"{API}/customers", body, format="json", HTTP_IDEMPOTENCY_KEY="a2")
        self.assertEqual(Customer.objects.count(), 2)

    def test_misuse_of_keys(self) -> None:
        self.admin.post(f"{API}/customers", {"name": "A"}, format="json", HTTP_IDEMPOTENCY_KEY="k")
        reused = self.admin.post(f"{API}/customers", {"name": "B"}, format="json", HTTP_IDEMPOTENCY_KEY="k")
        # API-010: 409 for the same caller with another body (was 422).
        self.assert_error(reused, 409, "idempotency_key_reused")
        IdempotentCall.objects.create(scope=IdempotentCall.objects.get().scope, key="busy", fingerprint="x")
        busy = self.admin.post(f"{API}/customers", {"name": "C"}, format="json", HTTP_IDEMPOTENCY_KEY="busy")
        self.assert_error(busy, 409, "idempotency_key_in_progress")
        too_long = self.admin.post(f"{API}/customers", {"name": "D"}, format="json", HTTP_IDEMPOTENCY_KEY="x" * 101)
        self.assert_error(too_long, 400, "validation_error")
        # Another token has keys of its own.
        other = self.client_of(self.admin_user).post(
            f"{API}/customers", {"name": "B"}, format="json", HTTP_IDEMPOTENCY_KEY="k"
        )
        self.assertEqual(other.status_code, 201)
        # A refused call is answered the same way again.
        invalid = self.admin.post(f"{API}/customers", {"name": ""}, format="json", HTTP_IDEMPOTENCY_KEY="e")
        again = self.admin.post(f"{API}/customers", {"name": ""}, format="json", HTTP_IDEMPOTENCY_KEY="e")
        self.assertEqual((invalid.status_code, again.status_code, again["Idempotent-Replayed"]), (400, 400, "true"))


class VersionCheckTests(ApiTestCase):
    """API-010: ``ETag`` and ``If-Match`` keep two people from overwriting each other's changes."""

    def test_a_change_on_an_old_state_is_refused(self) -> None:
        customer = make_customer("Kulturverein")
        url = f"{API}/customers/{customer.pk}"
        fetched = self.admin.get(url)
        tag = fetched["ETag"]
        self.assertEqual(self.admin.get(url, HTTP_IF_NONE_MATCH=tag).status_code, 304)

        colleague = self.client_of(self.admin_user)
        changed = colleague.patch(url, {"city": "Dorf"}, format="json", HTTP_IF_MATCH=tag)
        self.assertEqual(changed.status_code, 200, changed.content)
        stale = self.admin.patch(url, {"city": "Stadt"}, format="json", HTTP_IF_MATCH=tag)
        self.assert_error(stale, 412, "precondition_failed")
        customer.refresh_from_db()
        self.assertEqual(customer.city, "Dorf")

        fresh = self.admin.get(url)["ETag"]
        self.assertNotEqual(fresh, tag)
        self.assertEqual(self.admin.patch(url, {"city": "Stadt"}, format="json", HTTP_IF_MATCH=fresh).status_code, 200)
        self.assertEqual(self.admin.patch(url, {"note": "x"}, format="json", HTTP_IF_MATCH="*").status_code, 200)
        self.assert_error(self.admin.delete(url, HTTP_IF_MATCH=fresh), 412, "precondition_failed")
        # Without If-Match a change goes through as before.
        self.assertEqual(self.admin.patch(url, {"note": "y"}, format="json").status_code, 200)
