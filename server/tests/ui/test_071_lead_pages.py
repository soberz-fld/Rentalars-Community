# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages after the independent check: an impossible day in the address is no server error (UIX-004).

A hand-edited link such as ``/projects/?since=2027-02-30`` is well formed but names no real day; Django's
``parse_date`` raises for it. Every page that reads a date from the address treats it like a missing one
(``core.listing.query_date``).
"""

from __future__ import annotations

from django.urls import reverse

from rentalars.core.listing import query_date, query_datetime
from tests.helpers import make_project
from tests.ui.base import UiTestCase


class ImpossibleDaysTests(UiTestCase):
    """UIX-004: filters live in the address – and a wrong one only filters nothing."""

    def test_helpers(self) -> None:
        self.assertIsNone(query_date("2027-02-30"))
        self.assertIsNone(query_date(None))
        self.assertEqual(str(query_date("2027-02-28")), "2027-02-28")
        self.assertIsNone(query_datetime("2027-02-30T10:00"))
        self.assertIsNone(query_datetime("2027-03-01T25:00"))

    def test_pages_answer(self) -> None:
        project = make_project("Stadtfest")
        for url in (
            "/projects/?since=2027-02-30&until=2027-13-01",
            "/schedule/?view=week&week=2027-02-30",
            "/schedule/timeline/?from=2027-02-30",
            "/schedule/personnel/?from=2027-02-31",
            "/schedule/products/?from=2027-04-31",
            "/times/?week=2027-02-30",
            "/administration/audit-log/?since=2027-02-30",
            reverse("projects:line_availability", args=[project.pk]) + "?start=2027-02-30T10:00&end=2027-03-01T25:00",
        ):
            with self.subTest(url=url):
                self.assertLess(self.client.get(url).status_code, 400)
