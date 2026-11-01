# SPDX-License-Identifier: GPL-3.0-or-later
"""On the pages, area "service": people taking part in a service case (PRJ-108), the way to work deducted from
trips (ZEI-027), the hints at working times switched on and off in the settings (ZEI-018).
"""

from __future__ import annotations

import datetime
from decimal import Decimal as D  # noqa: N817

from django.urls import reverse

from rentalars.core.models import SystemSettings
from rentalars.notifications.models import Notification
from rentalars.projects import service_cases
from rentalars.projects.models import ServiceCaseParticipant
from rentalars.timetracking import expenses
from rentalars.timetracking.models import ExpenseKind
from tests.helpers import LATER, at, job_function, make_person, make_project, make_user, plan, record_time, set_clock
from tests.ui.base import UiTestCase, form_data


class ServicePageCase(UiTestCase):
    """Paula leads a service case; Kai (crew) is a lighting technician. Late March 2027."""

    def setUp(self) -> None:
        super().setUp()
        set_clock(LATER)
        self.client.force_login(self.admin_user)  # again: the clock moved past the idle time of the session
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.manager = self.browser_of(self.paula)
        self.case = service_cases.create_case(name="Spot flackert", manager=self.paula, user=self.paula)
        self.kai_user = make_user("kai", roles=("Crew",))
        self.kai = make_person("Kai Kurz", user=self.kai_user)
        self.crew = self.browser_of(self.kai_user)
        self.light = job_function("Lichttechnik")


class ParticipantPageTests(ServicePageCase):
    """PRJ-108: the case page lists the people taking part; whoever may change the case adds and removes them."""

    def test_add_and_remove_on_the_case_page(self) -> None:
        """PRJ-108: person, optional job function, note; the trash-can button takes the person off."""
        url = reverse("projects:case_detail", args=[self.case])
        page = self.assert_ok(self.manager.get(url))
        self.assertIn("Beteiligte", page)
        self.assertIn("Noch niemand ist beteiligt.", page)
        data = form_data(self.manager.get(url), "person", person=self.kai.pk, job_function=self.light.pk, note="Leiter")
        response = self.manager.post(reverse("projects:case_participant_add", args=[self.case]), data, follow=True)
        page = self.assert_ok(response)
        self.assertIn("Kai Kurz ist jetzt am Servicefall beteiligt.", self.messages_of(response))
        self.assertIn("Lichttechnik", page)
        self.assertIn("Kai Kurz vom Servicefall nehmen", page)
        self.assertTrue(Notification.objects.filter(user=self.kai_user).exists())
        participation = ServiceCaseParticipant.objects.get()
        response = self.manager.post(
            reverse("projects:case_participant_remove", args=[self.case, participation.pk]), follow=True
        )
        self.assertIn("Kai Kurz ist nicht mehr am Servicefall beteiligt.", self.messages_of(response))
        self.assertFalse(ServiceCaseParticipant.objects.exists())

    def test_readers_see_the_list_without_the_form(self) -> None:
        """PRJ-108: who only reads the case sees who takes part, but changes nothing.

        AUT-033 (decided: crew taking part may do everything needed to work on the case): the crew taking part works on
        the case now – the reader here is the warehouse, which reads every project and takes no part.
        """
        service_cases.add_participant(self.case, self.kai, job_function=self.light, user=self.paula)
        reader = self.browser_for("luka", "Lager")
        page = self.assert_ok(reader.get(reverse("projects:case_detail", args=[self.case])))
        self.assertIn("Kai Kurz", page)
        self.assertNotIn("Person hinzufügen", page)
        self.assertNotIn("vom Servicefall nehmen", page)
        response = reader.post(reverse("projects:case_participant_add", args=[self.case]), {"person": self.kai.pk})
        self.assertEqual(response.status_code, 403)
        # AUT-033: Kai, taking part, has the form (test_091_rights covers what he may do).
        self.assertIn(
            "Person hinzufügen", self.assert_ok(self.crew.get(reverse("projects:case_detail", args=[self.case])))
        )

    def test_the_history_of_the_case_names_the_person(self) -> None:
        """PRJ-108: the change log shows the participation in the history of the case."""
        service_cases.add_participant(self.case, self.kai, job_function=self.light, user=self.paula)
        page = self.assert_ok(self.client.get(reverse("projects:history", args=[self.case])))
        self.assertIn("Kai Kurz", page)


class MyCasesPageTests(ServicePageCase):
    """PRJ-108: My area → Servicefälle and the start page."""

    def test_the_tab_and_the_list(self) -> None:
        """PRJ-108: the case shows under Mein Bereich for those taking part; done cases on request; CSV of the view."""
        service_cases.add_participant(self.case, self.kai, job_function=self.light, note="Leiter", user=self.paula)
        other = service_cases.create_case(name="Nicht meiner")
        url = reverse("projects:my_cases")
        page = self.assert_ok(self.crew.get(url))
        self.assertIn('aria-current="page">Servicefälle</a>', page)
        self.assertIn("Spot flackert", page)
        self.assertIn("beteiligt als Lichttechnik", page)
        self.assertIn("Leiter", page)
        self.assertNotIn(other.name, page)
        service_cases.set_case_status(self.case, "done")
        self.assertIn("Du bist an keinem offenen Servicefall beteiligt.", self.assert_ok(self.crew.get(url)))
        self.assertIn("Spot flackert", self.assert_ok(self.crew.get(url, {"done": "1"})))
        csv = self.crew.get(url, {"done": "1", "format": "csv"})
        self.assertEqual(csv.status_code, 200)
        self.assertIn("Spot flackert", csv.content.decode("utf-8-sig"))
        self.assertIn("Servicefälle", self.assert_ok(self.crew.get(reverse("timetracking:my_times"))))

    def test_the_start_page_lists_the_case(self) -> None:
        """PRJ-108: "My service cases" on the start page has the cases one takes part in, too."""
        service_cases.add_participant(self.case, self.kai, user=self.paula)
        page = self.assert_ok(self.crew.get(reverse("core:home")))
        self.assertIn("Spot flackert", page)
        self.assertIn(reverse("projects:my_cases"), page)


class CommutePageTests(ServicePageCase):
    """ZEI-027: the distance in the personnel form, the calculation in the lists, the switch in the settings."""

    def test_the_personnel_form_and_page(self) -> None:
        """ZEI-027: "Entfernung Wohnung – Betrieb (km)" per person."""
        url = reverse("personnel:person_edit", args=[self.kai.pk])
        page = self.assert_ok(self.client.get(url))
        self.assertIn("Entfernung Wohnung – Betrieb (km)", page)
        response = self.client.post(url, form_data(self.client.get(url), "last_name", commute_km="14,5"))
        self.assertEqual(response.status_code, 302)
        self.kai.refresh_from_db()
        self.assertEqual(self.kai.commute_km, D("14.5"))
        page = self.assert_ok(self.client.get(reverse("personnel:person_detail", args=[self.kai.pk])))
        self.assertIn("14,5 km", page)

    def test_the_calculation_in_my_expenses_and_the_dialog(self) -> None:
        """ZEI-027: "42 km − 28 km Arbeitsweg = 14 km"; the dialog says what is deducted."""
        project = make_project("Stadtfest", start=at(10), end=at(12))
        plan(project, self.light, self.kai, start=at(9, 6), end=at(12, 23))
        self.kai.commute_km = D("14")
        self.kai.save()
        expenses.create_expense(
            person=self.kai,
            project=project,
            kind=ExpenseKind.TRAVEL,
            date=datetime.date(2027, 3, 10),
            kilometres=D("42"),
            rights=self.kai_user.rights,
            user=self.kai_user,
        )
        page = self.assert_ok(self.crew.get(reverse("timetracking:my_expenses")))
        self.assertIn("42 km − 28 km Arbeitsweg = 14 km × 0,30 €", page)
        self.assertIn("4,20 €", page)
        dialog = self.assert_ok(self.htmx("get", reverse("timetracking:expense_new"), client=self.crew))
        self.assertIn("Dein Arbeitsweg hin und zurück (28 km) wird einmal am Tag je Projekt abgezogen.", dialog)

    def test_the_settings(self) -> None:
        """ZEI-027, ZEI-018: both switches in Einstellungen, on by default."""
        page = self.assert_ok(self.client.get(reverse("core:company_settings")))
        self.assertIn("Arbeitsweg von Fahrten abziehen", page)
        self.assertIn("Hinweise zu Arbeitszeiten anzeigen", page)
        data = form_data(self.client.get(reverse("core:company_settings")), "system-time_hint_day_hours")
        data.pop("system-time_hints_enabled", None)
        data.pop("system-expense_deduct_commute", None)
        self.client.post(reverse("core:company_settings"), data)
        settings = SystemSettings.load()
        self.assertEqual((settings.time_hints_enabled, settings.expense_deduct_commute), (False, False))


class HintSwitchPageTests(ServicePageCase):
    """ZEI-018: off, no hint in the entry, "My times", the approval and the report."""

    def test_no_hints_when_switched_off(self) -> None:
        """ZEI-018: with the switch off, there are no hints in the entry, the approval and the report."""
        project = make_project("Stadtfest", start=at(10), end=at(12))
        plan(project, self.light, self.kai, start=at(9, 6), end=at(12, 23))
        record_time(self.kai, project, self.light, at(10, 7), at(10, 20), submit=True)
        report = reverse("timetracking:report")
        self.assertIn("Langer Arbeitstag", self.assert_ok(self.client.get(report, {"person": self.kai.pk})))
        settings = SystemSettings.load()
        settings.time_hints_enabled = False
        settings.save()
        for url in (report, reverse("timetracking:approval")):
            page = self.assert_ok(self.client.get(url, {"person": self.kai.pk}))
            self.assertNotIn("Langer Arbeitstag", page)
            self.assertNotIn("Nur Einträge mit Hinweisen", page)
        self.assertNotIn("Langer Arbeitstag", self.assert_ok(self.crew.get(reverse("timetracking:my_times"))))
