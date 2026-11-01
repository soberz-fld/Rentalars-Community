# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages of stage 4 with their scripts running: deployment requests, the mail frame, the course."""

from __future__ import annotations

from rentalars.mail.fetching import fetch_mail
from rentalars.mail.models import ProjectMail
from rentalars.projects.models import CrewLine
from tests.browser.base import BrowserTestCase
from tests.helpers import make_person, plan
from tests.mailbox import FakeMailbox, configure_mailbox, make_mail


class Stage4InBrowserTests(BrowserTestCase):
    """PER-016, EML-027, PRJ-059."""

    def test_ask_a_person_and_enter_the_answer_on_the_planning_page(self) -> None:
        line = plan(self.project, "Stagehand", make_person("Rita Rufbereit"))
        self.open_planning()
        crew_row = self.page.locator("tr", has_text="Rita Rufbereit")
        crew_row.locator("button", has_text="anfragen").click()
        self.settle()
        self.assertIn("angefragt", self.page.locator("tr", has_text="Rita Rufbereit").inner_text())
        self.page.locator("tr", has_text="Rita Rufbereit").locator("button", has_text="eintragen: zugesagt").click()
        self.settle()
        self.assertIn("zugesagt", self.page.locator("tr", has_text="Rita Rufbereit").inner_text())
        self.assertEqual(CrewLine.objects.get(pk=line.pk).request_status, "accepted")

    def test_a_mail_is_shown_in_its_frame_without_loading_anything_from_outside(self) -> None:
        configure_mailbox()
        box = FakeMailbox(
            make_mail(
                f"Bühnenplan [RL#{self.project.number}]",
                html='<p>Der <b>Bühnenplan</b> folgt.</p><img src="https://tracker.example/p.gif">'
                "<script>document.body.innerHTML='gehackt'</script>",
            )
        )
        fetch_mail(force=True, opener=box)
        mail = ProjectMail.objects.get()
        self.open(f"/projects/{self.project.pk}/mails/{mail.pk}/")
        frame = self.page.frame_locator("iframe.mail-frame")
        frame.locator("b", has_text="Bühnenplan").wait_for()
        self.assertNotIn("gehackt", frame.locator("body").inner_text())
        self.assertIn("1 Bild von einem anderen Server wurde zurückgehalten.", self.text_of("main"))
        # tearDown checks that no request went to tracker.example (NFA-050).

    def test_note_and_tick_off_open_items(self) -> None:
        self.open(f"/projects/{self.project.pk}/course/")
        self.page.fill("[name=texts]", "Aufbauzeiten\nStrom")
        self.page.locator("button", has_text="Notieren").click()
        self.page.wait_for_load_state()
        items = self.page.locator("ul.checklist li")
        self.assertEqual(items.count(), 2)
        items.first.locator("button.check-btn").click()
        self.page.wait_for_load_state()
        self.assertEqual(self.page.locator("ul.checklist li.done").count(), 1)
        self.page.locator("ul.checklist li").nth(1).locator("button[aria-label=Entfernen]").click()
        with self.page.expect_navigation():
            self.confirm()
        self.page.wait_for_load_state()
        self.assertEqual(self.page.locator("ul.checklist li").count(), 1)
