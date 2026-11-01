# SPDX-License-Identifier: GPL-3.0-or-later
"""In the pages, area "surcharges": Einstellungen → Zuschläge as a list of rules with own holidays (PER-040)."""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.urls import reverse

from rentalars.core.models import AuditLogEntry, OwnHoliday, TimeSurchargeRule, TimeSurchargeSettings
from rentalars.core.surcharges import load_rule_set
from tests.ui.base import UiTestCase, form_data

D = Decimal


class RulesPageTests(UiTestCase):
    """PER-040: the rules as an editable list – add, remove, order –, the holidays and the button for § 3b EStG."""

    url = reverse("core:time_surcharges")

    def setUp(self) -> None:
        super().setUp()
        load_rule_set()

    def page_data(self, **changes: object) -> dict:
        return form_data(self.client.get(self.url), containing="rules-TOTAL_FORMS", **changes)

    def test_the_page_shows_the_rules_holidays_and_the_button(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn('name="rules-TOTAL_FORMS" value="10"', page)  # nine rules and an empty one
        self.assertIn("Nach § 3b EStG einstellen", page)
        self.assertIn(f'action="{reverse("core:time_surcharges_section_3b")}"', page)
        self.assertIn("data-confirm=", page)
        for text in ("Regeln", "Eigene Feiertage", "Gesetzliche Feiertage in Deutschland", "Regel hinzufügen"):
            self.assertIn(text, page)
        self.assertIn('data-show-if="rules-0-kind=time"', page)
        self.assertIn("<template data-formset-empty>", page)
        self.assertIn('name="rules-__prefix__-name"', page)
        self.assertIn("kein Dienst im Internet", page)
        # The fields of one rule stand in one grid, the percentages with short labels.
        self.assertIn('<label for="id_rules-0-price_percent">Preis in %', page)
        self.assertIn('<label for="id_rules-0-cost_percent">Kosten in %', page)
        self.assertNotIn("Sätze in Prozent", page)

    def test_adding_a_rule_with_the_empty_row(self) -> None:
        data = self.page_data(
            **{
                "rules-9-name": "Samstag",
                "rules-9-kind": "weekday",
                "rules-9-weekdays": ["6"],
                "rules-9-time_from": "13:00",
                "rules-9-price_percent": "25",
                "rules-9-cost_percent": "20",
            }
        )
        response = self.client.post(self.url, data, follow=True)
        self.assertIn("Einstellungen gespeichert.", self.messages_of(response))
        saturday = TimeSurchargeRule.objects.get(name="Samstag")
        self.assertEqual(
            (saturday.weekdays, saturday.time_from, saturday.price_percent, saturday.position),
            ("6", datetime.time(13), D("25"), 10),
        )
        entry = AuditLogEntry.objects.filter(object_id=str(saturday.pk), content_type__model="timesurchargerule")
        self.assertEqual(entry.get().parent_object_id, "1")

    def test_removing_and_ordering_rules(self) -> None:
        # The empty row moved with the arrows (only its place changed) stays an empty row.
        data = self.page_data(
            **{"rules-2-DELETE": "on", "rules-0-position": "5", "rules-3-position": "1", "rules-9-position": "4"}
        )
        response = self.client.post(self.url, data, follow=True)
        self.assertIn("Einstellungen gespeichert.", self.messages_of(response))
        self.assertFalse(TimeSurchargeRule.objects.filter(code="sunday").exists())
        first = TimeSurchargeRule.objects.order_by("position", "id").first()
        self.assertEqual(first.kind, "holiday")
        self.assertEqual(TimeSurchargeRule.objects.count(), 8)

    def test_a_rule_without_its_values_is_refused(self) -> None:
        data = self.page_data(**{"rules-9-name": "Samstag", "rules-9-kind": "weekday"})
        page = self.assert_ok(self.client.post(self.url, data))
        self.assertIn("Wähl mindestens einen Wochentag.", page)
        self.assertFalse(TimeSurchargeRule.objects.filter(name="Samstag").exists())

    def test_own_holidays_and_no_german_ones(self) -> None:
        data = self.page_data(
            german_holidays=None,
            **{
                "holidays-0-name": "Nationalfeiertag",
                "holidays-0-kind": "yearly",
                "holidays-0-day": "26",
                "holidays-0-month": "10",
            },
        )
        response = self.client.post(self.url, data, follow=True)
        self.assertIn("Einstellungen gespeichert.", self.messages_of(response))
        self.assertFalse(TimeSurchargeSettings.load().german_holidays)
        holiday = OwnHoliday.objects.get()
        self.assertEqual((holiday.name, holiday.day, holiday.month), ("Nationalfeiertag", 26, 10))
        listed = self.assert_ok(response).split('id="holidays"')[1]
        self.assertIn("Nationalfeiertag", listed)
        self.assertIn("eigener", listed)
        self.assertNotIn("Ostermontag", listed)
        self.assertIn("nur eigene Feiertage", listed)
        # Easter Monday by its distance from Easter Sunday.
        data = self.page_data(
            **{"holidays-1-name": "Ostermontag", "holidays-1-kind": "easter", "holidays-1-easter_offset": "1"}
        )
        response = self.client.post(self.url, data, follow=True)
        self.assertIn("Ostermontag", self.assert_ok(response).split('id="holidays"')[1])

    def test_the_button_sets_the_rules_of_the_law(self) -> None:
        for row in TimeSurchargeRule.objects.all():
            row.delete()
        TimeSurchargeRule.objects.create(name="Samstag", kind="weekday", weekdays="6", price_percent=D("20"))
        response = self.client.post(reverse("core:time_surcharges_section_3b"), follow=True)
        self.assertIn(
            "Die Regeln nach § 3b EStG sind eingestellt. Die Feiertage sind geblieben, wie sie waren.",
            self.messages_of(response),
        )
        self.assertEqual(TimeSurchargeRule.objects.count(), 9)
        self.assertFalse(TimeSurchargeRule.objects.filter(name="Samstag").exists())
        self.assertEqual(self.client.get(reverse("core:time_surcharges_section_3b")).status_code, 405)

    def test_only_who_may_change_the_settings(self) -> None:
        for role in ("Projektleitung", "Nur-Lesen"):
            with self.subTest(role=role):
                browser = self.browser_for(role.lower(), role)
                self.assertEqual(browser.post(reverse("core:time_surcharges_section_3b")).status_code, 403)
        self.assertEqual(TimeSurchargeRule.objects.count(), 9)
