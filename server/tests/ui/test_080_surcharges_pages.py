# SPDX-License-Identifier: GPL-3.0-or-later
"""In the pages, area "surcharges": surcharges for night, Sunday and holidays (PER-009).

Saturday, 13 March 2027, 18:00 to Sunday 02:00 at 45.00 an hour: 360.00 and 126.00 surcharges (night 4 h × 25 %,
night 0–4 2 h × 40 %, Sunday 2 h × 50 %).
"""

from __future__ import annotations

from decimal import Decimal

from django.urls import reverse

from rentalars.core.models import TimeSurchargeRule, TimeSurchargeSettings
from rentalars.projects.models import CrewBilling, CrewLine
from tests.helpers import at, job_function, make_person, make_project, plan
from tests.ui.base import UiTestCase, form_data

D = Decimal


def switch_on(**values: object) -> None:
    """Switch the surcharges on for new crew lines."""
    settings = TimeSurchargeSettings.load()
    settings.on_price = settings.on_costs = True
    for name, value in values.items():
        setattr(settings, name, value)
    settings.save()


class SettingsPageTests(UiTestCase):
    """PER-009: Einstellungen → Zuschläge."""

    url = reverse("core:time_surcharges")

    def test_the_administration_links_the_page(self) -> None:
        page = self.assert_ok(self.client.get(reverse("core:administration")))
        self.assertIn(f'href="{self.url}"', page)
        self.assertIn("Zuschläge", page)

    def test_the_page_shows_the_defaults_of_the_law_and_the_holidays(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn("Zuschläge für Nacht, Sonn- und Feiertage", page)
        self.assertIn("§ 3b EStG", page)
        # PER-040: the rates of the law are a list of rules.
        for name in ("Nacht", "Nacht 0–4 Uhr", "Sonntag", "Feiertag", "Weihnachten und 1. Mai"):
            self.assertIn(f'value="{name}"', page)
        self.assertIn('name="rules-0-price_percent" value="25"', page)
        self.assertIn('name="rules-8-cost_percent" value="150"', page)
        self.assertIn('name="rules-0-time_from" value="20:00"', page)
        # Without a state the holidays of the whole country, this year and the next (the clock stands in 2027).
        self.assertIn("Feiertage 2027 und 2028", page)
        self.assertIn("nur die bundesweiten Feiertage", page)
        self.assertIn("Ostermontag", page)
        self.assertNotIn("Fronleichnam", page.split('id="holidays"')[1])

    def test_saving_the_settings(self) -> None:
        response = self.client.get(self.url)
        data = form_data(
            response,
            containing="rules-0-price_percent",
            on_price="on",
            on_costs="on",
            state="BY",
            next_day_until="",
            **{"rules-0-time_from": "22:00", "rules-0-price_percent": "30", "rules-2-cost_percent": "0"},
        )
        response = self.client.post(self.url, data, follow=True)
        self.assertIn("Einstellungen gespeichert.", self.messages_of(response))
        settings = TimeSurchargeSettings.load()
        self.assertEqual(
            (settings.on_price, settings.on_costs, settings.state, settings.next_day_until), (True, True, "BY", None)
        )
        night, sunday = TimeSurchargeRule.objects.get(code="night"), TimeSurchargeRule.objects.get(code="sunday")
        self.assertEqual((night.price_percent, sunday.cost_percent, night.time_from.hour), (D("30"), D("0"), 22))
        page = self.assert_ok(response)
        self.assertIn("Fronleichnam", page)  # the holidays of Bavaria
        self.assertIn("Mariä Himmelfahrt", page)

    def test_wrong_values_are_refused(self) -> None:
        response = self.client.get(self.url)
        data = form_data(
            response, containing="rules-0-time_until", **{"rules-0-time_until": "20:00", "rules-3-price_percent": "600"}
        )
        page = self.assert_ok(self.client.post(self.url, data))
        self.assertIn("Die Regel muss zu einer anderen Uhrzeit enden, als sie beginnt.", page)
        self.assertEqual(TimeSurchargeRule.objects.get(code="holiday", kind="holiday").price_percent, D("125"))

    def test_only_the_administration_may_open_it(self) -> None:
        for role in ("Projektleitung", "Nur-Lesen"):
            with self.subTest(role=role):
                browser = self.browser_for(role.lower(), role)
                self.assertEqual(browser.get(self.url).status_code, 403)
                self.assertEqual(browser.post(self.url, {"on_price": "on"}).status_code, 403)
        self.assertFalse(TimeSurchargeSettings.load().on_price)


class PlanningPagesTests(UiTestCase):
    """PER-009 on the planning page, in the dialog of a crew line, the price overview and the product."""

    def setUp(self) -> None:
        super().setUp()
        switch_on()
        self.project = make_project(start=at(13), end=at(15))
        self.function = job_function("Tontechnik", price="45.00", guide="30.00")
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "30.00"})
        self.line = plan(
            self.project, self.function, self.anna, start=at(13, 18), end=at(14, 2), billing=CrewBilling.PLAN
        )

    def test_the_planning_shows_the_surcharges_on_price_and_costs(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.project.pk])))
        self.assertIn("486,00", page)
        self.assertIn("inkl. Zuschläge 126,00 €", page)
        for part in ("Nacht 25 % auf 4 Std.", "Nacht 0–4 Uhr 40 % auf 2 Std.", "Sonntag 50 % auf 2 Std."):
            self.assertIn(f'<span class="time-surcharge-part">{part}', page)
        self.assertIn("inkl. Zuschläge 84,00 €", page)  # on the costs

    def test_the_dialog_switches_them_per_line(self) -> None:
        url = reverse("projects:crew_edit", args=[self.project.pk, self.line.pk])
        dialog = self.htmx("get", url)
        page = self.assert_ok(dialog)
        self.assertIn('name="time_surcharges_on_price"', page)
        self.assertIn('name="time_surcharges_on_cost"', page)
        self.assertIn("Zuschläge für Nacht, Sonn- und Feiertage im Preis", page)
        data = form_data(dialog, containing="time_surcharges_on_price", time_surcharges_on_price=None)
        self.assert_ok(self.htmx("post", url, data))
        line = CrewLine.objects.get(pk=self.line.pk)
        self.assertEqual((line.time_surcharges_on_price, line.time_surcharges_on_cost), (False, True))
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.project.pk])))
        self.assertNotIn("inkl. Zuschläge 126,00 €", page)
        self.assertIn("inkl. Zuschläge 84,00 €", page)

    def test_the_dialog_offers_each_switch_only_with_its_right(self) -> None:
        url = reverse("projects:crew_edit", args=[self.project.pk, self.line.pk])
        planner = self.browser_for("pia", "Personaldisposition")  # personnel costs, no prices
        page = self.assert_ok(planner.get(url, HTTP_HX_REQUEST="true"))
        self.assertNotIn('name="time_surcharges_on_price"', page)
        self.assertIn('name="time_surcharges_on_cost"', page)

    def test_the_price_overview_names_them(self) -> None:
        url = reverse("projects:price_overview", args=[self.project.pk])
        page = self.assert_ok(self.client.get(url))
        self.assertIn("486,00", page)
        self.assertIn("inkl. Zuschläge 126,00 €", page)
        self.assertIn("Nacht 25 % auf 4 Std.", page)
        self.assertIn("Darin: Zuschläge für Nacht, Sonn- und Feiertage von 126,00 € (vor Rabatten).", page)
        for query in ({"detail": "groups"}, {"crew": "phases"}):
            with self.subTest(query=query):
                page = self.assert_ok(self.client.get(url, query))
                self.assertIn("Darin: Zuschläge für Nacht, Sonn- und Feiertage von 126,00 € (vor Rabatten).", page)
        csv = self.client.get(reverse("projects:price_overview_csv", args=[self.project.pk]))
        self.assertEqual(csv.status_code, 200)
        self.assertIn("Tontechnik, Stunde (inkl. Zuschläge 126,00 €)", csv.content.decode())

    def test_the_product_of_a_service_can_exclude_its_lines(self) -> None:
        product = self.function.service_product
        url = reverse("products:edit", args=[product.pk])
        form = self.client.get(url)
        page = self.assert_ok(form)
        self.assertIn('name="time_surcharges"', page)
        response = self.client.post(url, form_data(form, containing="time_surcharges", time_surcharges=None))
        self.assertEqual(response.status_code, 302, response.context and response.context["form"].errors)
        product.refresh_from_db()
        self.assertFalse(product.time_surcharges)
        detail = self.assert_ok(self.client.get(reverse("products:detail", args=[product.pk])))
        self.assertIn("keine für Nacht, Sonn- und Feiertage", detail)
        line = plan(self.project, self.function, self.anna, start=at(13, 18), end=at(14, 2))
        self.assertFalse(line.time_surcharges_on_price)
