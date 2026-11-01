# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests, area "surcharges": surcharges for night, Sunday and holidays (PER-009, API-014).

Saturday, 13 March 2027, 18:00 to Sunday 02:00 at 45.00 an hour and a cost of 30.00: 360.00 and 126.00 surcharges
on the price, 240.00 and 84.00 on the costs.
"""

from __future__ import annotations

from decimal import Decimal

from rentalars.core.models import TimeSurchargeSettings
from rentalars.projects.models import CrewLine
from tests.api.base import API, ApiTestCase
from tests.helpers import at, job_function, make_person, make_project, plan

D = Decimal
URL = f"{API}/settings/surcharges"


def switch_on() -> None:
    """Switch the surcharges on for new crew lines."""
    settings = TimeSurchargeSettings.load()
    settings.on_price = settings.on_costs = True
    settings.save()


class SettingsApiTests(ApiTestCase):
    """``GET/PATCH /settings/surcharges`` (PER-009)."""

    def test_read_and_change(self) -> None:
        response = self.admin.get(URL)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            (response.data["on_price"], response.data["on_costs"], response.data["state"]), (False, False, "")
        )
        # PER-040: the rates of § 3b EStG are rules.
        night, high = response.data["rules"][0], response.data["rules"][-1]
        self.assertEqual((night["price_percent"], high["cost_percent"]), ("25.00", "150.00"))
        self.assertEqual((night["time_from"], night["time_until"]), ("20:00:00", "06:00:00"))
        self.assertEqual(response.data["next_day_until"], "04:00:00")
        changed = self.admin.patch(URL, {"on_price": True, "state": "BY"}, format="json")
        self.assertEqual(changed.status_code, 200, changed.data)
        settings = TimeSurchargeSettings.load()
        self.assertEqual((settings.on_price, settings.on_costs, settings.state), (True, False, "BY"))

    def test_wrong_values_are_refused(self) -> None:
        self.assert_error(self.admin.patch(URL, {"state": "XX"}, format="json"), 400, "validation_error", "state")
        # PER-040: a rule with a percentage beyond 500, a night without length.
        rules = self.admin.get(URL).data["rules"]
        rules[3]["price_percent"] = "501"
        error = self.assert_error(self.admin.patch(URL, {"rules": rules}, format="json"), 400, "validation_error")
        self.assertIn("rules.3.price_percent", error["fields"])
        rules = self.admin.get(URL).data["rules"]
        rules[0]["time_until"] = "20:00"
        error = self.assert_error(self.admin.patch(URL, {"rules": rules}, format="json"), 400, "validation_error")
        self.assertIn("rules.0.time_until", error["fields"])
        self.assertEqual(self.admin.get(URL).data["rules"][0]["time_until"], "06:00:00")

    def test_only_the_administration(self) -> None:
        planner = self.client_for("pia", "Projektleitung")
        self.assertEqual(planner.get(URL).status_code, 403)
        self.assertEqual(planner.patch(URL, {"on_price": True}, format="json").status_code, 403)
        self.assertFalse(TimeSurchargeSettings.load().on_price)


class HolidaysApiTests(ApiTestCase):
    """``GET /holidays`` (PER-009)."""

    def test_the_holidays_of_a_year_and_state(self) -> None:
        response = self.admin.get(f"{API}/holidays", {"year": "2026", "state": "BY"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data["year"], response.data["state"]), (2026, "BY"))
        self.assertEqual(len(response.data["holidays"]), 13)
        corpus_christi = next(day for day in response.data["holidays"] if day["key"] == "corpus_christi")
        self.assertEqual((str(corpus_christi["date"]), corpus_christi["name"]), ("2026-06-04", "Fronleichnam"))

    def test_by_default_this_year_and_the_state_of_the_settings(self) -> None:
        settings = TimeSurchargeSettings.load()
        settings.state = "SN"
        settings.save()
        crew_member = self.client_for("chris", "Crew")  # holidays are for everybody logged in
        response = crew_member.get(f"{API}/holidays")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data["year"], response.data["state"]), (2027, "SN"))
        self.assertIn("repentance_day", {day["key"] for day in response.data["holidays"]})
        everywhere = crew_member.get(f"{API}/holidays", {"state": ""})
        self.assertEqual(len(everywhere.data["holidays"]), 9)

    def test_wrong_questions(self) -> None:
        self.assert_error(self.admin.get(f"{API}/holidays", {"year": "zwei"}), 400, "validation_error", "year")
        self.assert_error(self.admin.get(f"{API}/holidays", {"year": "1800"}), 400, "validation_error", "year")
        self.assert_error(self.admin.get(f"{API}/holidays", {"state": "XX"}), 400, "validation_error", "state")
        self.assertIn(self.client.get(f"{API}/holidays").status_code, (401, 403))


class CrewLineApiTests(ApiTestCase):
    """``/projects/{id}/crew-lines`` and the price overview with the surcharges (PER-009)."""

    def setUp(self) -> None:
        super().setUp()
        switch_on()
        self.project = make_project(start=at(13), end=at(15))
        self.function = job_function("Tontechnik", price="45.00", guide="30.00")
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "30.00"})
        self.url = f"{API}/projects/{self.project.pk}/crew-lines"

    def test_a_new_line_takes_them_and_shows_the_split(self) -> None:
        created = self.admin.post(
            self.url,
            {
                "job_function": self.function.pk,
                "person": self.anna.pk,
                "start": at(13, 18).isoformat(),
                "end": at(14, 2).isoformat(),
                "billing": "plan",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        line = created.data[0]
        self.assertEqual((line["time_surcharges_on_price"], line["time_surcharges_on_cost"]), (True, True))
        self.assertEqual(
            [(part["kind"], part["percent"], part["hours"], part["amount"]) for part in line["time_surcharges"]],
            [
                ("night", D("25"), D("4.00"), D("45.00")),
                ("night_after_midnight", D("40"), D("2.00"), D("36.00")),
                ("sunday", D("50"), D("2.00"), D("45.00")),
            ],
        )
        self.assertEqual(line["time_surcharges"][0]["label"], "Nacht")
        self.assertEqual(
            (line["time_surcharge_amount"], line["amount_before_discount"], line["amount"]),
            (D("126.00"), D("486.00"), D("486.00")),
        )
        self.assertEqual((line["cost_time_surcharge_amount"], line["cost"]), (D("84.00"), D("324.00")))
        self.assertEqual(line["actual_cost_time_surcharges"], [])
        listed = self.admin.get(self.url)
        self.assertEqual(listed.data[0]["time_surcharge_amount"], D("126.00"))

    def test_the_switches_can_be_set_and_need_their_rights(self) -> None:
        line = plan(self.project, self.function, self.anna, start=at(13, 18), end=at(14, 2), billing="plan")
        url = f"{self.url}/{line.pk}"
        changed = self.admin.patch(url, {"time_surcharges_on_price": False}, format="json")
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertEqual((changed.data["amount"], changed.data["time_surcharges"]), (D("360.00"), []))
        self.assertEqual(changed.data["cost"], D("324.00"))
        planner = self.client_for("pia", "Personaldisposition")  # personnel costs, no prices
        self.assert_error(
            planner.patch(url, {"time_surcharges_on_price": True}, format="json"), 400, "validation_error"
        )
        changed = planner.patch(url, {"time_surcharges_on_cost": False}, format="json")
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertNotIn("time_surcharges", changed.data)  # no prices for this account
        self.assertEqual((changed.data["cost"], changed.data["cost_time_surcharges"]), (D("240.00"), []))
        line.refresh_from_db()
        self.assertEqual((line.time_surcharges_on_price, line.time_surcharges_on_cost), (False, False))

    def test_the_price_overview(self) -> None:
        plan(self.project, self.function, self.anna, start=at(13, 18), end=at(14, 2), billing="plan")
        response = self.admin.get(f"{API}/projects/{self.project.pk}/price-overview")
        self.assertEqual(response.status_code, 200, response.data)
        personnel = response.data["personnel"]
        self.assertEqual(personnel["subtotal"], D("486.00"))
        self.assertEqual(personnel["lines"][0]["time_surcharge_amount"], D("126.00"))
        self.assertEqual(len(personnel["lines"][0]["time_surcharges"]), 3)
        self.assertEqual(response.data["totals"]["personnel_time_surcharges"], D("126.00"))

    def test_the_product_can_exclude_its_lines(self) -> None:
        url = f"{API}/products/{self.function.service_product_id}"
        self.assertTrue(self.admin.get(url).data["time_surcharges"])
        changed = self.admin.patch(url, {"time_surcharges": False}, format="json")
        self.assertEqual(changed.status_code, 200, changed.data)
        created = self.admin.post(
            self.url,
            {"job_function": self.function.pk, "start": at(13, 18).isoformat(), "end": at(14, 2).isoformat()},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertFalse(CrewLine.objects.get(pk=created.data[0]["id"]).time_surcharges_on_price)
        warehouse = self.client_for("luka", "Lager")  # reads products, no price right
        self.assertNotIn("time_surcharges", warehouse.get(url).data)
