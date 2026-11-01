# SPDX-License-Identifier: GPL-3.0-or-later
"""On the pages, area "cases": further statuses of a service case (PRJ-112) and the rules for them in
Einstellungen → Automationen (ADM-013).
"""

from __future__ import annotations

import datetime

from django.urls import reverse

from rentalars.automations.models import Automation
from rentalars.projects import service_cases
from rentalars.projects.models import CaseStatus, Project
from tests.helpers import make_customer, make_user
from tests.ui.base import UiTestCase


class CasePageCase(UiTestCase):
    """Paula leads an open service case."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.manager = self.browser_of(self.paula)
        self.case = service_cases.create_case(
            name="Spot flackert", customer=make_customer(), manager=self.paula, user=self.paula
        )
        self.status_url = reverse("projects:case_status", args=[self.case])

    def reload(self) -> Project:
        return Project.objects.get(pk=self.case.pk)


class StatusDialogTests(CasePageCase):
    """PRJ-112: choosing "waiting", "waiting to close" or "backlog" opens the follow-up dialog first."""

    def test_the_case_page_offers_every_status(self) -> None:
        """PRJ-112: the list of statuses on the case page, sent in the background into the dialog."""
        page = self.assert_ok(self.manager.get(reverse("projects:case_detail", args=[self.case])))
        for label in ("offen", "in Arbeit", "wartet", "wartet auf Schließen", "zurückgestellt", "erledigt"):
            self.assertIn(f">{label}</option>", page)
        self.assertIn(f'hx-post="{self.status_url}" hx-target="#dialog"', page)
        self.assertIn('data-follow-up-statuses="waiting,closing,backlog" data-saved="open"', page)
        self.assertIn('aria-describedby="case-status-hint"', page)
        self.assertIn(
            "Wählst du „wartet“, „wartet auf Schließen“ oder „zurückgestellt“, öffnet sich die Wiedervorlage", page
        )

    def test_waiting_opens_the_dialog_and_saves_with_the_follow_up(self) -> None:
        """PRJ-112: the requirement: the existing dialog "Wiedervorlage" opens by itself and has to be filled in."""
        dialog = self.assert_ok(self.htmx("post", self.status_url, {"case_status": "waiting"}, self.manager))
        self.assertIn("<h2>Wiedervorlage</h2>", dialog)
        self.assertIn("Wartet auf", dialog)
        self.assertIn("Materiallieferung", dialog)
        self.assertIn("Auf „wartet“ setzen", dialog)
        self.assertNotIn("<html", dialog)
        self.assertEqual(self.reload().case_status, CaseStatus.OPEN)  # nothing saved yet
        # Without the day and the reason: the dialog again, with the errors.
        data = {"case_status": "waiting", "with_follow_up": "1", "follow_up_user": self.paula.pk}
        dialog = self.assert_ok(self.htmx("post", self.status_url, data, self.manager))
        self.assertIn("Dieses Feld ist zwingend erforderlich.", dialog)
        self.assertEqual(self.reload().case_status, CaseStatus.OPEN)
        data.update(follow_up_on="2027-03-05", case_waiting_for="reply", follow_up_note="Angebot Ersatzteil")
        response = self.htmx("post", self.status_url, data, self.manager)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Redirect"], reverse("projects:case_detail", args=[self.case]))
        case = self.reload()
        self.assertEqual((case.case_status, case.case_waiting_for), ("waiting", "reply"))
        self.assertEqual((case.follow_up_on, case.follow_up_user), (datetime.date(2027, 3, 5), self.paula))
        page = self.assert_ok(self.manager.get(reverse("projects:case_detail", args=[self.case])))
        self.assertIn("wartet auf Rückmeldung", page)
        self.assertIn("Wiedervorlage am", page)

    def test_waiting_to_close_needs_the_time_and_works_without_script(self) -> None:
        """PRJ-112: the requirement: day and time have to be entered – the dialog as a page of its own without the script."""
        page = self.assert_ok(self.manager.post(self.status_url, {"case_status": "closing"}))
        self.assertIn("<h1>Wiedervorlage</h1>", page)
        self.assertIn("Schließen am", page)
        self.assertIn("Tut sich bis zum Tag und zur Uhrzeit unten nichts im Servicefall", page)
        data = {"case_status": "closing", "with_follow_up": "1", "follow_up_on": "2027-03-05"}
        data["follow_up_user"] = self.paula.pk
        page = self.assert_ok(self.manager.post(self.status_url, data))
        self.assertIn("Dieses Feld ist zwingend erforderlich.", page)
        self.assertEqual(self.reload().case_status, CaseStatus.OPEN)
        data["follow_up_at"] = "16:00"
        response = self.manager.post(self.status_url, data, follow=True)
        self.assertIn("Der Servicefall ist jetzt „wartet auf Schließen“.", self.messages_of(response))
        self.assertEqual(self.reload().follow_up_at, datetime.time(16, 0))

    def test_a_plain_status_is_set_at_once(self) -> None:
        """PRJ-090: open, in progress, done need no dialog."""
        response = self.htmx("post", self.status_url, {"case_status": "in_progress"}, self.manager)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.reload().case_status, CaseStatus.IN_PROGRESS)

    def test_follow_up_done_opens_the_case_again(self) -> None:
        """PRJ-112: "done" on the follow-up of a case in the backlog: open again, and the page says so."""
        service_cases.set_case_status(
            self.case, CaseStatus.BACKLOG, follow_up={"on": datetime.date(2027, 3, 9), "user": self.paula}
        )
        response = self.manager.post(reverse("projects:follow_up_done", args=[self.case.pk]), follow=True)
        self.assertIn("Der Servicefall ist jetzt „offen“.", self.messages_of(response))
        self.assertEqual(self.reload().case_status, CaseStatus.OPEN)

    def test_readers_cannot(self) -> None:
        """PRJ-112: setting a status needs the right to change the case."""
        crew = self.browser_for("kai", "Crew")
        self.assertEqual(crew.post(self.status_url, {"case_status": "backlog"}).status_code, 403)


class ListTests(CasePageCase):
    """PRJ-112: the lists – badge, default filter, the backlog."""

    def setUp(self) -> None:
        super().setUp()
        service_cases.set_case_status(
            self.case, CaseStatus.BACKLOG, follow_up={"on": datetime.date(2027, 3, 9), "user": self.paula}
        )

    def test_service_cases_list_shows_the_backlog(self) -> None:
        """PRJ-112: the requirement: shown only in the list of service cases – every case not done by default, filter by status."""
        page = self.assert_ok(self.manager.get(reverse("projects:cases")))
        self.assertIn("Alle nicht erledigten", page)
        self.assertIn("Spot flackert", page)
        self.assertIn('<span class="badge ">zurückgestellt</span>', page)
        page = self.assert_ok(self.manager.get(reverse("projects:cases") + "?status=open"))
        self.assertNotIn("Spot flackert", page)
        page = self.assert_ok(self.manager.get(reverse("projects:cases") + "?status=backlog"))
        self.assertIn("Spot flackert", page)

    def test_my_area_on_request(self) -> None:
        """PRJ-112: Mein Bereich → Servicefälle leaves the backlog out unless asked for."""
        from tests.helpers import make_person

        make_person("Paula Peters", user=self.paula)
        page = self.assert_ok(self.manager.get(reverse("projects:my_cases")))
        self.assertIn("auch Zurückgestellte", page)
        self.assertNotIn("Spot flackert", page)
        page = self.assert_ok(self.manager.get(reverse("projects:my_cases") + "?backlog=1"))
        self.assertIn("Spot flackert", page)


class AutomationFormTests(UiTestCase):
    """ADM-013: the rules of the service cases in Einstellungen → Automationen."""

    def test_the_default_rules_are_listed(self) -> None:
        page = self.assert_ok(self.client.get(reverse("automations:list")))
        self.assertIn("Wartet auf Schließen: zum Termin schließen", page)
        self.assertIn("Die Wiedervorlage eines Servicefalls ist fällig", page)
        self.assertIn("im Status „wartet auf Schließen“", page)
        self.assertIn("Den Status des Servicefalls setzen", page)
        self.assertIn("auf „erledigt“", page)

    def test_create_a_rule(self) -> None:
        """ADM-013: trigger "new communication", condition status and kind, action "set the status"."""
        page = self.assert_ok(self.client.get(reverse("automations:create")))
        self.assertIn('data-show-when="trigger:case_follow_up,case_communication"', page)
        self.assertIn('data-show-when="action:case_status"', page)
        data = {
            "name": "Wartet: Antwort öffnet",
            "is_active": "on",
            "trigger": "case_communication",
            "case_status": "waiting",
            "communication": "mail_in",
            "action": "case_status",
            "new_case_status": "",
        }
        page = self.assert_ok(self.client.post(reverse("automations:create"), data))
        self.assertIn("Wähle den neuen Status: offen, in Arbeit oder erledigt.", page)
        data["new_case_status"] = "waiting"  # needs a follow-up: not offered
        page = self.assert_ok(self.client.post(reverse("automations:create"), data))
        self.assertIn("waiting ist keine gültige Auswahl", page)
        data["new_case_status"] = "open"
        response = self.client.post(reverse("automations:create"), data)
        self.assertEqual(response.status_code, 302)
        rule = Automation.objects.get(name="Wartet: Antwort öffnet")
        self.assertEqual(
            (rule.trigger, rule.status, rule.communication, rule.action, rule.new_case_status),
            ("case_communication", "waiting", "mail_in", "case_status", "open"),
        )
        page = self.assert_ok(self.client.get(reverse("automations:edit", args=[rule.pk])))
        self.assertIn('<option value="waiting" selected>wartet</option>', page)
