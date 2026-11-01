# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages: crew requests after changed times (PER-033, PER-034).

* The block "Personal" of the planning: an answered line offers "erneut
  anfragen" only once its times changed, says so and names the times asked
  for; asking again for the same times is refused.
* The crew dialog and moving a phase with its crew: new times ask the
  person again by themselves, and the planner is told.
* Einstellungen → Allgemein: "Bei geänderten Zeiten neu anfragen".
* The history of the project names the request with new times.
"""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from rentalars.core.models import SystemSettings
from rentalars.projects import course, crew
from rentalars.projects.models import CrewLine, RequestStatus
from tests.helpers import ALL_RIGHTS, at, make_person, make_project, plan
from tests.ui.base import UiTestCase, form_data


def set_ask_again(value: bool) -> None:
    system = SystemSettings.load()
    system.ask_again_on_new_times = value
    system.save()


class CrewRequestInThePlanningTests(UiTestCase):
    """PER-033: "erneut anfragen" only after new times."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest")
        self.anna = make_person("Anna Becker")
        self.line = plan(self.project, "Tontechnik", self.anna, start=at(10, 8), end=at(10, 18))
        self.planning = reverse("projects:detail", args=[self.project.pk])
        self.ask_url = reverse("projects:crew_request", args=[self.project.pk, self.line.pk])
        crew.request_deployment(self.line, user=self.admin_user)

    def request_block(self) -> str:
        page = self.assert_ok(self.client.get(self.planning))
        start = page.index('<div class="sub request">', page.index(f'data-crew-line="{self.line.pk}"'))
        return page[start : page.index("</td>", start)]

    def answer(self, *, accept: bool) -> None:
        crew.answer_deployment(self.line, accept=accept, user=self.admin_user)

    def change_times(self, **changes: Any) -> None:
        crew.update_crew_line(CrewLine.objects.get(pk=self.line.pk), rights=ALL_RIGHTS, **changes)

    def test_an_accepted_line_offers_nothing_more(self) -> None:
        self.answer(accept=True)
        block = self.request_block()
        self.assertIn(">zugesagt</span>", block)
        self.assertNotIn("erneut anfragen", block)
        self.assertNotIn("eintragen", block)
        self.assertNotIn("Zeiten geändert", block)

    def test_a_waiting_request_offers_to_enter_the_answer(self) -> None:
        block = self.request_block()
        self.assertIn(">angefragt</span>", block)
        self.assertIn("eintragen: zugesagt", block)
        self.assertNotIn("erneut anfragen", block)

    def test_after_new_times_the_line_says_so_and_offers_ask_again(self) -> None:
        set_ask_again(False)
        for accept, since in ((True, "seit der Zusage"), (False, "seit der Absage")):
            with self.subTest(since):
                self.line = CrewLine.objects.get(pk=self.line.pk)
                self.answer(accept=accept)
                self.change_times(start=at(10, 10))
                block = self.request_block()
                self.assertIn(
                    f"Zeiten geändert {since} – angefragt war: Mi 10.03. 08:00 – Mi 10.03. 18:00",
                    " ".join(block.split()),
                )
                self.assertIn("erneut anfragen", block)
                response = self.htmx("post", self.ask_url)
                self.assertIn("Anna Becker wurde angefragt.", self.assert_ok(response))
                line = CrewLine.objects.get(pk=self.line.pk)
                self.assertEqual(line.request_status, RequestStatus.REQUESTED)
                self.assertNotIn("Zeiten geändert", self.request_block())
                self.change_times(start=at(10, 8))  # back for the next round, asked again by hand
                crew.request_deployment(CrewLine.objects.get(pk=self.line.pk), user=self.admin_user)

    def test_a_waiting_request_with_new_times_offers_both(self) -> None:
        set_ask_again(False)
        self.change_times(end=at(10, 20))
        block = " ".join(self.request_block().split())
        self.assertIn("Zeiten geändert seit der Anfrage – angefragt war: Mi 10.03. 08:00 – Mi 10.03. 18:00", block)
        self.assertIn("erneut anfragen", block)
        self.assertIn("eintragen: zugesagt", block)

    def test_asking_again_for_the_same_times_is_refused(self) -> None:
        """The button is not there; a request sent all the same is refused with the reason."""
        self.answer(accept=True)
        response = self.htmx("post", self.ask_url)
        self.assertIn("Anna Becker hat für diese Zeiten schon zugesagt.", self.assert_ok(response))
        self.assertEqual(CrewLine.objects.get(pk=self.line.pk).request_status, RequestStatus.ACCEPTED)

    def test_new_times_in_the_dialog_ask_again(self) -> None:
        """PER-034: with the setting on (default), the dialog's new times ask the person again."""
        self.answer(accept=True)
        url = reverse("projects:crew_edit", args=[self.project.pk, self.line.pk])
        dialog = self.htmx("get", url)
        response = self.htmx("post", url, form_data(dialog, start="2027-03-10T09:00"))
        self.assertIn("Anna Becker wurde für die neuen Zeiten neu angefragt.", self.assert_ok(response))
        line = CrewLine.objects.get(pk=self.line.pk)
        self.assertEqual((line.request_status, line.requested_start), (RequestStatus.REQUESTED, at(10, 9)))
        block = self.request_block()
        self.assertIn(">angefragt</span>", block)
        self.assertNotIn("Zeiten geändert", block)

        history = self.assert_ok(self.client.get(reverse("projects:history", args=[self.project.pk])))
        self.assertIn(
            "Anna Becker neu angefragt für neue Zeiten: Mi 10.03. 09:00 – Mi 10.03. 18:00 "
            "(vorher: Mi 10.03. 08:00 – Mi 10.03. 18:00)",
            history,
        )

    def test_other_changes_in_the_dialog_ask_nobody(self) -> None:
        self.answer(accept=True)
        url = reverse("projects:crew_edit", args=[self.project.pk, self.line.pk])
        response = self.htmx("post", url, form_data(self.htmx("get", url), meeting_point="Tor 3"))
        self.assertNotIn("neu angefragt", self.assert_ok(response))
        self.assertEqual(CrewLine.objects.get(pk=self.line.pk).request_status, RequestStatus.ACCEPTED)


class MovingAPhaseAsksAgainTests(UiTestCase):
    """PER-034: moving a phase with its crew asks the accepted person again, and the page says so."""

    def test_the_message_after_saving_the_phase(self) -> None:
        project = make_project("Stadtfest", start=at(12, 8), end=at(14, 20))
        setup = course.add_phase(project, kind="setup", start=at(12, 8), end=at(12, 16))
        anna = make_person("Anna Becker")
        line = plan(project, "Stagehand", anna, phase=setup)
        crew.request_deployment(line, user=self.admin_user)
        crew.answer_deployment(CrewLine.objects.get(pk=line.pk), accept=True, user=self.admin_user)
        url = reverse("projects:phase_edit", args=[project.pk, setup.pk])
        response = self.client.post(
            url, form_data(self.client.get(url), start="2027-03-12T10:00", end="2027-03-12T18:00"), follow=True
        )
        self.assertIn("Anna Becker wurde für die neuen Zeiten neu angefragt.", self.messages_of(response))
        line.refresh_from_db()
        self.assertEqual((line.request_status, line.requested_start), (RequestStatus.REQUESTED, at(12, 10)))


class AskAgainSettingTests(UiTestCase):
    """PER-034: the setting in Einstellungen → Allgemein, on by default."""

    def test_shown_and_saved(self) -> None:
        url = reverse("core:company_settings")
        page = self.client.get(url)
        text = self.assert_ok(page)
        self.assertIn("Bei geänderten Zeiten neu anfragen", text)
        self.assertIn("Ändern sich die Zeiten einer angefragten oder zugesagten Personalposition", text)
        self.assertRegex(text, r'<input type="checkbox" name="system-ask_again_on_new_times"[^>]*checked')
        data = form_data(page, containing="system-buffer_before_hours")
        data.pop("system-ask_again_on_new_times", None)
        data["form"] = "system"
        self.assertRedirects(self.client.post(url, data), url)
        self.assertFalse(SystemSettings.load().ask_again_on_new_times)
