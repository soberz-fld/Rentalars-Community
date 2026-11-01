# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests, area "surcharges": the rules and own holidays of the surcharges (PER-040, API-014)."""

from __future__ import annotations

from decimal import Decimal

from rentalars.core.models import AuditLogEntry, OwnHoliday, TimeSurchargeRule, TimeSurchargeSettings
from tests.api.base import API, ApiTestCase

D = Decimal
URL = f"{API}/settings/surcharges"


class RulesApiTests(ApiTestCase):
    """``GET/PATCH /settings/surcharges`` with ``rules`` and ``own_holidays``, ``POST …/section-3b`` (PER-040)."""

    def test_read_the_rules_of_the_law(self) -> None:
        response = self.admin.get(URL)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["german_holidays"])
        rules = response.data["rules"]
        self.assertEqual(len(rules), 9)
        self.assertEqual(
            [(rule["code"], rule["kind"], rule["position"]) for rule in rules[:3]],
            [("night", "time", 1), ("night_after_midnight", "time", 2), ("sunday", "weekday", 3)],
        )
        self.assertEqual(rules[2]["weekdays"], [7])
        self.assertTrue(rules[1]["begun_before_midnight"])
        self.assertEqual(response.data["own_holidays"], [])

    def test_replace_the_list_change_add_remove_and_order(self) -> None:
        rules = self.admin.get(URL).data["rules"]
        night, sunday = rules[0], rules[2]
        night["price_percent"] = "30.00"
        saturday = {
            "name": "Samstag",
            "kind": "weekday",
            "weekdays": [6],
            "time_from": "13:00",
            "price_percent": "25",
            "cost_percent": "20",
        }
        changed = self.admin.patch(URL, {"rules": [sunday, saturday, night]}, format="json")
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertEqual(
            [(rule["name"], rule["position"]) for rule in changed.data["rules"]],
            [("Sonntag", 1), ("Samstag", 2), ("Nacht", 3)],
        )
        self.assertEqual(TimeSurchargeRule.objects.count(), 3)
        self.assertEqual(TimeSurchargeRule.objects.get(code="night").price_percent, D("30"))
        self.assertEqual(TimeSurchargeRule.objects.get(name="Samstag").weekdays, "6")
        # Every change is in the change log, in the history of the settings.
        self.assertEqual(
            AuditLogEntry.objects.filter(content_type__model="timesurchargerule", action="deleted").count(), 7
        )
        self.assertTrue(AuditLogEntry.objects.filter(parent_object_id="1", object_repr="Samstag").exists())

    def test_own_holidays_and_the_holidays_of_a_year(self) -> None:
        changed = self.admin.patch(
            URL,
            {
                "german_holidays": False,
                "own_holidays": [
                    {"name": "Nationalfeiertag", "kind": "yearly", "day": 26, "month": 10},
                    {"name": "Ostermontag", "kind": "easter", "easter_offset": 1},
                ],
            },
            format="json",
        )
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertEqual(
            [holiday["name"] for holiday in changed.data["own_holidays"]], ["Nationalfeiertag", "Ostermontag"]
        )
        holidays = self.admin.get(f"{API}/holidays", {"year": "2027"})
        self.assertEqual(holidays.status_code, 200, holidays.data)
        self.assertFalse(holidays.data["german_holidays"])
        self.assertEqual(
            [(str(day["date"]), day["name"], day["key"], day["own"]) for day in holidays.data["holidays"]],
            [("2027-03-29", "Ostermontag", "own", True), ("2027-10-26", "Nationalfeiertag", "own", True)],
        )
        # With a state given: its statutory holidays and the own ones.
        bavaria = self.admin.get(f"{API}/holidays", {"year": "2027", "state": "BY"})
        self.assertEqual(len(bavaria.data["holidays"]), 15)
        # Left out: deleted.
        keep = changed.data["own_holidays"][1]
        self.assertEqual(self.admin.patch(URL, {"own_holidays": [keep]}, format="json").status_code, 200)
        self.assertEqual(list(OwnHoliday.objects.values_list("name", flat=True)), ["Ostermontag"])

    def test_wrong_lists_are_refused(self) -> None:
        self.assert_error(
            self.admin.patch(URL, {"rules": [{"id": 999999, "name": "x", "kind": "holiday"}]}, format="json"),
            400,
            "validation_error",
            "rules.0.id",
        )
        self.assert_error(
            self.admin.patch(URL, {"rules": [{"name": "Samstag", "kind": "weekday"}]}, format="json"),
            400,
            "validation_error",
            "rules.0.weekdays",
        )
        self.assert_error(
            self.admin.patch(URL, {"own_holidays": [{"name": "x", "kind": "once"}]}, format="json"),
            400,
            "validation_error",
            "own_holidays.0.date",
        )
        self.assertEqual(TimeSurchargeRule.objects.count(), 9)

    def test_set_the_rules_of_section_3b(self) -> None:
        self.admin.patch(URL, {"rules": [], "state": "BY", "next_day_until": None}, format="json")
        self.assertEqual(TimeSurchargeRule.objects.count(), 0)
        response = self.admin.post(f"{URL}/section-3b")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["rules"]), 9)
        self.assertEqual((response.data["state"], response.data["next_day_until"]), ("BY", "04:00:00"))

    def test_only_the_administration(self) -> None:
        planner = self.client_for("pia", "Projektleitung")
        self.assertEqual(planner.post(f"{URL}/section-3b").status_code, 403)
        self.assertEqual(planner.patch(URL, {"rules": []}, format="json").status_code, 403)
        self.assertTrue(TimeSurchargeSettings.load().rules_set_up)
        self.assertEqual(TimeSurchargeRule.objects.count(), 9)
