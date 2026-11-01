# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests, area "legacy import": the list of batches pages like every list of the API. (R4-7; API-007)"""

from __future__ import annotations

import datetime

from django.core.management import call_command
from django.utils import timezone

from rentalars.projects.legacy_models import LegacyImportBatch
from tests.api.base import API, ApiTestCase


class LegacyImportListPagingTests(ApiTestCase):
    """``GET /legacy-imports`` answers ``count``, ``next``, ``previous`` and ``results`` and takes ``page_size``."""

    def make_batches(self, count: int) -> list[LegacyImportBatch]:
        now = timezone.now()
        return [
            LegacyImportBatch.objects.create(created_by=self.admin_user, created_at=now - datetime.timedelta(hours=n))
            for n in range(count)
        ]

    def test_the_standard_envelope_and_the_pages(self) -> None:
        batches = self.make_batches(3)
        everything = self.admin.get(f"{API}/legacy-imports")
        self.assertEqual(everything.status_code, 200, everything.content)
        body = everything.json()
        self.assertEqual(set(body), {"count", "next", "previous", "results"})
        self.assertEqual(body["count"], 3)
        self.assertEqual([row["id"] for row in body["results"]], [batch.pk for batch in batches])  # newest first
        self.assertEqual(body["results"][0]["counts"]["total"], 0)
        first = self.admin.get(f"{API}/legacy-imports", {"page_size": 2}).json()
        self.assertEqual((len(first["results"]), first["count"]), (2, 3))
        self.assertIsNotNone(first["next"])
        self.assertIsNone(first["previous"])
        second = self.admin.get(f"{API}/legacy-imports", {"page_size": 2, "page": 2}).json()
        self.assertEqual([row["id"] for row in second["results"]], [batches[2].pk])
        self.assertIsNone(second["next"])

    def test_more_than_fifty_batches_are_not_cut_off(self) -> None:
        """Before: the list ended silently after 50 batches."""
        self.make_batches(52)
        body = self.admin.get(f"{API}/legacy-imports", {"page_size": 100}).json()
        self.assertEqual((body["count"], len(body["results"])), (52, 52))

    def test_the_schema_has_no_warnings(self) -> None:
        call_command("spectacular", "--validate", "--fail-on-warn", "--file", "/dev/null", verbosity=0)
