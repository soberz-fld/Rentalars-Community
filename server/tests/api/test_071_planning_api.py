# SPDX-License-Identifier: GPL-3.0-or-later
"""API, planning: ``GET /personnel-plan`` lists every active person (VFG-023, fix).

No operation is new in this area; the personnel plan of the API follows the page, as API-002 asks.
"""

from __future__ import annotations

from rentalars.personnel.models import Absence, Person
from tests.api.base import API, ApiTestCase
from tests.helpers import at, make_person, make_user


class PersonnelPlanTests(ApiTestCase):
    """VFG-023: every active person; ``busy=1`` only those with deployments or absences in the span."""

    def test_every_active_person_or_only_the_busy(self) -> None:
        make_person("Anna Becker", rates={"Stagehand": "20.00"})
        office = make_user("buero").person  # no job function
        away = make_person("Carla Wolf")
        Absence.objects.create(person=away, start=at(9), end=at(10))
        gone = make_person("Dora Klein")
        Person.objects.filter(pk=gone.pk).update(is_active=False)
        rows = self.admin.get(f"{API}/personnel-plan", {"from": "2027-03-08", "weeks": 1}).json()
        names = [row["name"] for row in rows]
        for name in ("Anna Becker", office.name, "Carla Wolf", self.admin_user.person.name):
            self.assertIn(name, names)
        self.assertNotIn("Dora Klein", names)
        self.assertLess(names.index("Anna Becker"), names.index("Carla Wolf"))  # by last name
        busy = self.admin.get(f"{API}/personnel-plan", {"from": "2027-03-08", "weeks": 1, "busy": "1"}).json()
        self.assertEqual([row["name"] for row in busy], ["Carla Wolf"])
        self.assertEqual(busy[0]["entries"][0]["type"], "absence")
