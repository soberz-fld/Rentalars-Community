# SPDX-License-Identifier: GPL-3.0-or-later
"""Through the API, area "service": people taking part in a service case (PRJ-108), the way to work of a person
and its deduction from trips (ZEI-027), the switch of the hints at working times (ZEI-018).

Every new operation is called here at least once with success (API-014): ``GET``/``POST``
``/service-cases/{id}/participants``, ``PATCH``/``DELETE`` ``/service-cases/{id}/participants/{participant}``;
the new fields of service cases, people, expenses and settings, and ``taking_part``.
"""

from __future__ import annotations

import datetime
from decimal import Decimal as D  # noqa: N817

from rentalars.core.models import SystemSettings
from rentalars.notifications.models import Notification
from rentalars.projects import service_cases
from rentalars.projects.models import ServiceCaseParticipant
from tests.api.base import API, ApiTestCase
from tests.helpers import LATER, at, job_function, make_person, make_project, make_user, plan, record_time, set_clock

CASES = f"{API}/service-cases"


class ServiceApiCase(ApiTestCase):
    """Paula leads a service case; Kai (crew) is a lighting technician. Late March 2027."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.manager = self.client_of(self.paula)
        self.case = service_cases.create_case(name="Spot flackert", manager=self.paula, user=self.paula)
        self.kai_user = make_user("kai", roles=("Crew",))
        self.kai = make_person("Kai Kurz", user=self.kai_user)
        self.crew = self.client_of(self.kai_user)
        self.light = job_function("Lichttechnik")
        set_clock(LATER)


class ParticipantApiTests(ServiceApiCase):
    """PRJ-108: list, add, change, take off; the case names its participants."""

    def test_add_change_and_take_off(self) -> None:
        """PRJ-108, API-014."""
        url = f"{CASES}/{self.case.pk}/participants"
        added = self.manager.post(
            url, {"person": self.kai.pk, "job_function": self.light.pk, "note": "Leiter"}, format="json"
        )
        self.assertEqual(added.status_code, 201, added.content)
        self.assertEqual(
            (added.data["person_name"], added.data["job_function_name"], added.data["note"]),
            ("Kai Kurz", "Lichttechnik", "Leiter"),
        )
        self.assertTrue(Notification.objects.filter(user=self.kai_user).exists())
        again = self.manager.post(url, {"person": self.kai.pk, "note": "zwei Leitern"}, format="json")
        self.assertEqual(again.status_code, 200)
        self.assertEqual(ServiceCaseParticipant.objects.count(), 1)
        listed = self.manager.get(url)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual([row["note"] for row in listed.data], ["zwei Leitern"])
        one = f"{url}/{added.data['id']}"
        changed = self.manager.patch(one, {"job_function": self.light.pk}, format="json")
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual((changed.data["job_function"], changed.data["note"]), (self.light.pk, "zwei Leitern"))
        case = self.manager.get(f"{CASES}/{self.case.pk}")
        self.assertEqual([row["person"] for row in case.data["participants"]], [self.kai.pk])
        self.assertEqual(self.manager.delete(one).status_code, 204)
        self.assertFalse(ServiceCaseParticipant.objects.exists())

    def test_the_crew_reads_its_case_and_changes_nothing(self) -> None:
        """PRJ-108: taking part opens the case; ``taking_part`` lists one's own cases.

        AUT-033 (decided): crew taking part in a case may do everything needed to work on it – the crew taking
        part now adds people as well (projects/case_work.py). Tests: test_091_rights.
        """
        self.assertEqual(self.crew.get(f"{CASES}/{self.case.pk}").status_code, 404)
        service_cases.add_participant(self.case, self.kai, job_function=self.light, user=self.paula)
        service_cases.create_case(name="Nicht meiner")
        self.assertEqual(self.crew.get(f"{CASES}/{self.case.pk}").status_code, 200)
        self.assertEqual(self.crew.get(f"{CASES}/{self.case.pk}/participants").status_code, 200)
        mine = self.manager.get(CASES, {"taking_part": "true"})
        self.assertEqual(mine.data.get("results", mine.data), [])
        listed = self.crew.get(CASES, {"taking_part": "true"})
        rows = listed.data.get("results", listed.data)
        self.assertEqual([row["name"] for row in rows], ["Spot flackert"])
        works = self.crew.post(f"{CASES}/{self.case.pk}/participants", {"person": self.kai.pk}, format="json")
        self.assertEqual(works.status_code, 200, works.content)  # AUT-033: was 403 – Kai takes part already
        other = service_cases.create_case(name="Auch nicht meiner")
        refused = self.crew.post(f"{CASES}/{other.pk}/participants", {"person": self.kai.pk}, format="json")
        self.assertEqual(refused.status_code, 403)  # never another case

    def test_a_project_has_no_participants(self) -> None:
        """PRJ-108: only service cases."""
        project = make_project("Stadtfest")
        response = self.manager.post(f"{CASES}/{project.pk}/participants", {"person": self.kai.pk}, format="json")
        self.assertEqual(response.status_code, 404)


class CommuteApiTests(ServiceApiCase):
    """ZEI-027: the distance of a person, the deduction of a trip, the setting."""

    def test_person_expense_and_settings(self) -> None:
        """ZEI-027: ``commute_km`` of a person; ``commute_km`` and ``billable_kilometres`` of a trip."""
        changed = self.admin.patch(f"{API}/people/{self.kai.pk}", {"commute_km": "14"}, format="json")
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual(changed.data["commute_km"], "14.0")
        project = make_project("Stadtfest", start=at(10), end=at(12))
        plan(project, self.light, self.kai, start=at(9, 6), end=at(12, 23))
        trip = self.crew.post(
            f"{API}/expenses",
            {"project": project.pk, "kind": "travel", "date": "2027-03-10", "kilometres": "42"},
            format="json",
        )
        self.assertEqual(trip.status_code, 201, trip.content)
        self.assertEqual(
            (D(str(trip.data["commute_km"])), D(str(trip.data["billable_kilometres"])), D(str(trip.data["amount"]))),
            (D("28"), D("14"), D("4.20")),
        )
        settings = self.admin.get(f"{API}/settings")
        self.assertTrue(settings.data["system"]["expense_deduct_commute"])
        self.assertTrue(settings.data["system"]["time_hints_enabled"])


class HintSwitchApiTests(ServiceApiCase):
    """ZEI-018: switched off in the settings, the time entries of the API have no hints."""

    def test_no_hints_when_switched_off(self) -> None:
        """ZEI-018: with the switch off, the time entries of the API carry no hints."""
        project = make_project("Stadtfest", start=at(10), end=at(12))
        plan(project, self.light, self.kai, start=at(9, 6), end=at(12, 23))
        entry = record_time(self.kai, project, self.light, at(10, 7), at(10, 20), submit=True)
        self.assertTrue(self.crew.get(f"{API}/time-entries/{entry.pk}").data["hints"])
        settings = SystemSettings.load()
        settings.time_hints_enabled = False
        settings.save()
        self.assertEqual(self.crew.get(f"{API}/time-entries/{entry.pk}").data["hints"], [])
        self.assertEqual(datetime.date(2027, 3, 10), entry.start.date())
