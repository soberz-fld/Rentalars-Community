# SPDX-License-Identifier: GPL-3.0-or-later
"""On the pages, area "shortages": Einstellungen → Benachrichtigungen (VFG-036).

The page sets when, how often and how far ahead shortages are reported and whether known ones are reported again;
it shows the last and the next check. Mein Konto → Benachrichtigungen points to it.
"""

from __future__ import annotations

import datetime

from django.urls import reverse
from django.utils import translation

from rentalars.accounts.models import Role
from rentalars.core.models import NotificationSettings, ShortageInterval
from tests.helpers import at, make_user
from tests.ui.base import UiTestCase

URL = "/administration/notifications/"


def form_data(**values: str) -> dict[str, str]:
    """The fields as the page sends them, with their defaults – and those of the reminders of invoices and of
    times to approve (ZEI-029)."""
    data = {
        "shortage_interval": "daily",
        "shortage_weekday": "1",
        "shortage_time": "04:15",
        "shortage_lead_weeks": "4",
        "invoice_reminders": "on",
        "invoice_time": "09:00",
        "invoice_first_days": "1",
        "invoice_every_days": "7",
        "approval_reminders": "on",
        "approval_time": "08:00",
        "approval_first_days": "1",
        "approval_every_days": "1",
    }
    return data | values


class NotificationSettingsPageTests(UiTestCase):
    """VFG-036: the page of the company's notification settings."""

    def test_the_page_shows_the_defaults(self) -> None:
        self.assertEqual(reverse("notifications:company_settings"), URL)
        page = self.assert_ok(self.client.get(URL))
        self.assertIn("<h1>Benachrichtigungen der Firma</h1>", page)
        self.assertIn('<option value="daily" selected>Jeden Tag</option>', page)
        self.assertIn("An Werktagen (Montag bis Freitag, außer an Feiertagen)", page)
        self.assertIn('<option value="weekly">Einmal in der Woche</option>', page)
        self.assertIn('<option value="off">Nie – ausgeschaltet</option>', page)
        self.assertIn('value="04:15"', page)
        self.assertIn('name="shortage_lead_weeks" value="4"', page)
        # The day of the week only for "Einmal in der Woche".
        self.assertIn('<div data-show-if="shortage_interval=weekly" class="hidden">', page)
        self.assertIn(">Montag</option>", page)
        self.assertIn("Letzte Prüfung</dt>\n        <dd>noch nicht</dd>", page)
        self.assertIn("Di 02.03.2027 04:15", page)  # the next check

    def test_the_settings_hub_links_the_page(self) -> None:
        page = self.assert_ok(self.client.get(reverse("core:administration")))
        self.assertIn(f'<a href="{URL}">Benachrichtigungen</a>', page)
        self.assertIn("Wann und wie weit voraus Fehlbestände gemeldet werden", page)

    def test_save_once_a_week(self) -> None:
        NotificationSettings.objects.filter(pk=1).update(shortage_last_run=at(1, 4, 15))
        response = self.client.post(
            URL,
            form_data(
                shortage_interval="weekly",
                shortage_weekday="5",
                shortage_time="07:30",
                shortage_lead_weeks="8",
                shortage_repeat="on",
            ),
            follow=True,
        )
        self.assertRedirects(response, URL)
        page = self.assert_ok(response)
        settings = NotificationSettings.objects.get(pk=1)
        self.assertEqual(
            (
                settings.shortage_interval,
                settings.shortage_weekday,
                settings.shortage_time,
                settings.shortage_lead_weeks,
                settings.shortage_repeat,
            ),
            (ShortageInterval.WEEKLY, 5, datetime.time(7, 30), 8, True),
        )
        # A new time counts from its next moment: the schedule starts anew now.
        self.assertEqual(settings.shortage_last_run, at(1, 8))
        self.assertIn("Einstellungen gespeichert.", page)
        self.assertIn('name="shortage_lead_weeks" value="8" min="1" inputmode="numeric" max="26"', page)
        self.assertIn('<div data-show-if="shortage_interval=weekly">', page)
        self.assertIn("Fr 05.03.2027 07:30", page)

    def test_only_the_lead_time_keeps_the_schedule(self) -> None:
        NotificationSettings.objects.filter(pk=1).update(shortage_last_run=at(1, 4, 15))
        self.assertRedirects(self.client.post(URL, form_data(shortage_lead_weeks="12")), URL)
        settings = NotificationSettings.objects.get(pk=1)
        self.assertEqual((settings.shortage_lead_weeks, settings.shortage_last_run), (12, at(1, 4, 15)))

    def test_switched_off_and_the_last_check(self) -> None:
        NotificationSettings.objects.filter(pk=1).update(
            shortage_interval="off", shortage_checked_at=at(1, 4, 15), shortage_reported=3
        )
        page = self.assert_ok(self.client.get(URL))
        self.assertIn("Mo 01.03.2027 04:15 – 3 Fehlbestände gemeldet", page)
        self.assertIn("keine – ausgeschaltet", page)

    def test_wrong_values_are_refused(self) -> None:
        response = self.client.post(URL, form_data(shortage_lead_weeks="27", shortage_time=""))
        page = self.assert_ok(response)
        self.assertIn("kleiner oder gleich 26", page)
        self.assertIn("Dieses Feld ist zwingend erforderlich.", page)
        self.assertEqual(NotificationSettings.objects.get(pk=1).shortage_lead_weeks, 4)

    def test_rights(self) -> None:
        """Reading needs the module "Einstellungen"; changing needs writing it."""
        planner = self.browser_for("pia", "Projektleitung")
        self.assertEqual(planner.get(URL).status_code, 403)
        Role.objects.create(name="Datenschutz", module_levels={"administration": 1})
        reader = self.browser_for("dana", "Datenschutz")
        page = self.assert_ok(reader.get(URL))
        self.assertNotIn("Einstellungen speichern", page)
        self.assertEqual(reader.post(URL, form_data(shortage_lead_weeks="8")).status_code, 403)
        self.assertEqual(NotificationSettings.objects.get(pk=1).shortage_lead_weeks, 4)

    def test_in_english(self) -> None:
        english = make_user("emma", superuser=True)
        english.language = "en"
        english.save()
        page = self.assert_ok(self.browser_of(english).get(URL))
        self.assertIn("<h1>Notifications of the company</h1>", page)
        self.assertIn("On working days (Monday to Friday, except holidays)", page)
        self.assertIn("Tue 02/03/2027 04:15", page)
        translation.activate("de")


class PreferencesNoteTests(UiTestCase):
    """VFG-036: Mein Konto → Benachrichtigungen says where the time of the shortages is set."""

    def test_the_note_links_the_settings_for_those_who_may_read_them(self) -> None:
        page = self.assert_ok(self.client.get("/account/notifications/"))
        self.assertIn(
            "Wann und wie weit voraus Fehlbestände gemeldet werden, ist für die ganze Firma eingestellt: "
            f'<a href="{URL}">Einstellungen → Benachrichtigungen</a>.',
            page,
        )
        page = self.assert_ok(self.browser_for("pia", "Projektleitung").get("/account/notifications/"))
        self.assertIn("ist für die ganze Firma eingestellt: Einstellungen → Benachrichtigungen.", page)
        self.assertNotIn(f'href="{URL}"', page)
