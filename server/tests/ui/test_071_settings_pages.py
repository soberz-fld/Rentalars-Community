# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages, area "settings": ADM-015, EML-046, PRJ-105.

* ADM-015: Einstellungen → Firmendaten und Grundeinstellungen offers "Antwort
  auf Einsatzanfragen"; the page of the mailboxes names it and links there
  (more in ``tests/ui/test_063_crewmail_pages.py``).
* EML-046: deleting a mailbox asks first and says what follows; the mail log
  keeps its name.
* PRJ-105: the follow-up in the head of the project, its dialog, the start
  page and the list of projects.
"""

from __future__ import annotations

import datetime

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from rentalars.mail.fetching import fetch_mail
from rentalars.mail.models import CrewAnswerMode, Mailbox, MailSettings, ProjectMail
from rentalars.projects.follow_up import set_follow_up
from rentalars.projects.models import Project, ProjectStatus
from tests.helpers import make_project, make_user
from tests.mailbox import FakeMailbox, add_mailbox, configure_mailbox, mailboxes, make_mail
from tests.ui.base import UiTestCase, form_data

SETTINGS = "/administration/settings/"
MAIL = "/administration/mail/"


def delete_page(mailbox: Mailbox) -> str:
    """The confirmation page for deleting a mailbox."""
    return f"{MAIL}mailboxes/{mailbox.pk}/delete/"


class CrewAnswerSettingPageTests(UiTestCase):
    """ADM-015: saving the other settings keeps the choice; the choice is saved with them."""

    def test_saved_with_the_settings(self) -> None:
        data = form_data(self.client.get(SETTINGS), "system-crew_answers", **{"system-buffer_before_hours": "3"})
        self.assertEqual(data["system-crew_answers"], CrewAnswerMode.BOTH)
        data["system-crew_answers"] = CrewAnswerMode.MAIL
        response = self.client.post(SETTINGS, data, follow=True)
        self.assertIn("Einstellungen gespeichert.", self.messages_of(response))
        self.assertEqual(MailSettings.load().crew_answers, CrewAnswerMode.MAIL)
        text = self.assert_ok(response)
        # After the usual times and rules of the page; not in the rules of the mailboxes any more.
        self.assertLess(text.index('name="system-buffer_before_hours"'), text.index('id="crew-answers"'))
        self.assertNotIn('name="crew_answers"', self.assert_ok(self.client.get(MAIL)))


class DeleteMailboxPageTests(UiTestCase):
    """EML-046: the confirmation says what follows; mails and log keep the name."""

    def setUp(self) -> None:
        super().setUp()
        self.projects = configure_mailbox()
        self.info = add_mailbox("Info", "info@verleih.example", process_untagged=True)
        project = make_project()
        with mailboxes(
            {
                "projekte@verleih.example": FakeMailbox(),
                "info@verleih.example": FakeMailbox(
                    make_mail(f"Bühnenplan [RL#{project.number}]"), make_mail("Anfrage für Juni")
                ),
            }
        ):
            fetch_mail(force=True)

    def test_what_follows(self) -> None:
        text = self.assert_ok(self.client.get(delete_page(self.info)))
        self.assertIn("<h1>Postfach „Info“ löschen</h1>", text)
        self.assertIn("1 Mail der Projekte kam über dieses Postfach herein oder ging hinaus.", text)
        self.assertIn("Sie bleibt und nennt weiter „Info“.", text)
        self.assertIn("Das Mail-Protokoll nennt es in", text)
        self.assertIn("1 Anfrage oder Mail mit unbekannter Kennung wartet daraus unter Projekte → Anfragen.", text)
        self.assertIn("Danach hat kein Postfach mehr seine Rollen (Korrespondenz).", text)
        self.assertIn("Nur ausschalten", text)
        self.assertNotIn('name="successor"', text)

    def test_delete_and_the_log_keeps_the_name(self) -> None:
        response = self.client.post(delete_page(self.info), follow=True)
        self.assertIn("Das Postfach „Info“ wurde gelöscht.", self.messages_of(response))
        self.assertFalse(Mailbox.objects.filter(name="Info").exists())
        self.assertEqual(ProjectMail.objects.get().mailbox_name, "Info")
        log = self.assert_ok(self.client.get("/administration/mail/log/?q=Info"))
        self.assertIn("Info (gelöscht)", log)

    def test_the_mailbox_that_sends_names_who_takes_over(self) -> None:
        text = self.assert_ok(self.client.get(delete_page(self.projects)))
        self.assertIn("Danach übernimmt das „Info“.", text)
        self.assertIn("Antworten auf Einsatzanfragen per Mail gehen an dieses Postfach", text)
        buero = add_mailbox("Büro", "buero@verleih.example")
        text = self.assert_ok(self.client.get(delete_page(self.projects)))
        self.assertIn('<select id="id_successor" name="successor" required', text)
        response = self.client.post(delete_page(self.projects), {"successor": str(buero.pk)}, follow=True)
        self.assertIn("„Büro“ versendet jetzt die Korrespondenz.", self.messages_of(response))
        buero.refresh_from_db()
        self.assertTrue(buero.is_outgoing)

    def test_refused_when_no_other_can_send(self) -> None:
        self.info.smtp_host = ""
        self.info.save()
        text = self.assert_ok(self.client.get(delete_page(self.projects)))
        self.assertIn("kein anderes aktives Postfach der Korrespondenz kann senden", text)
        self.assertRegex(text, r'<button class="btn danger" type="submit" disabled>')
        response = self.client.post(delete_page(self.projects))
        self.assertIn('class="note red" role="alert"', self.assert_ok(response))
        self.assertTrue(Mailbox.objects.filter(pk=self.projects.pk).exists())

    def test_only_switch_off(self) -> None:
        response = self.client.post(delete_page(self.info), {"action": "switch_off"}, follow=True)
        self.assertIn("Das Postfach „Info“ wurde ausgeschaltet.", self.messages_of(response))
        self.info.refresh_from_db()
        self.assertFalse(self.info.is_active)

    def test_needs_the_right_to_delete(self) -> None:
        manager = self.browser_for("paula", "Projektleitung")  # writes the module E-mail, may not delete
        self.assertEqual(manager.get(delete_page(self.info)).status_code, 403)
        self.assertEqual(manager.post(delete_page(self.info)).status_code, 403)
        self.assertTrue(Mailbox.objects.filter(pk=self.info.pk).exists())


class FollowUpPageTests(UiTestCase):
    """PRJ-105: set, show and finish a follow-up on the pages of the project."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.project = make_project("Firmenfeier", status=ProjectStatus.INQUIRY, manager=self.paula)
        self.page = reverse("projects:detail", args=[self.project.pk])
        self.dialog = reverse("projects:follow_up", args=[self.project.pk])

    def test_set_in_the_dialog_and_shown_in_the_head(self) -> None:
        head = self.assert_ok(self.client.get(self.page))
        self.assertIn(f'hx-get="{self.dialog}?next=', head)
        dialog = self.assert_ok(self.htmx("get", self.dialog))
        self.assertIn("<h2>Wiedervorlage</h2>", dialog)
        self.assertRegex(dialog, rf'<option value="{self.admin_user.pk}" selected>')  # for who sets it
        data = form_data(
            self.htmx("get", self.dialog),
            "follow_up_on",
            follow_up_on="2027-03-01",
            follow_up_user=str(self.paula.pk),
            follow_up_note="Angebot nachfassen",
        )
        response = self.htmx("post", self.dialog, data)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Redirect"], self.page)
        text = self.assert_ok(self.client.get(self.page))
        self.assertIn("<strong>Wiedervorlage am Mo 01.03.2027</strong> für paula", text)
        self.assertIn('<span class="badge yellow">fällig</span>', text)
        self.assertIn("– Angebot nachfassen", text)
        # Once set, the head offers "Change" and "Done" instead of the button of the actions.
        self.assertNotIn("Wiedervorlage</a>", text)
        self.assertIn(f'action="{self.dialog}done/"', text)

    def test_done(self) -> None:
        set_follow_up(self.project, on=datetime.date(2027, 3, 5), by=self.paula)
        response = self.client.post(f"{self.dialog}done/", {"next": self.page}, follow=True)
        self.assertIn(f"Die Wiedervorlage von {self.project.number} ist erledigt.", self.messages_of(response))
        self.project.refresh_from_db()
        self.assertIsNone(self.project.follow_up_on)
        self.assertNotIn("follow-up-note", self.assert_ok(response))

    def test_without_the_page_script(self) -> None:
        page = self.assert_ok(self.client.get(self.dialog))
        self.assertIn("<h1>Wiedervorlage</h1>", page)
        data = form_data(self.client.get(self.dialog), "follow_up_on", follow_up_on="2027-03-08")
        response = self.client.post(self.dialog, data, follow=True)
        self.assertIn("Wiedervorlage am 08.03.2027 für admin.", self.messages_of(response))
        self.project.refresh_from_db()
        self.assertEqual(self.project.follow_up_user, self.admin_user)

    def test_errors_show_in_the_dialog(self) -> None:
        crew = make_user("carla", roles=("Crew",))
        data = form_data(self.htmx("get", self.dialog), "follow_up_on", follow_up_on="", follow_up_user=str(crew.pk))
        text = self.assert_ok(self.htmx("post", self.dialog, data))
        self.assertIn("Dieses Feld ist zwingend erforderlich.", text)
        data["follow_up_on"] = "2027-03-08"
        text = self.assert_ok(self.htmx("post", self.dialog, data))
        self.assertIn("carla darf dieses Projekt nicht öffnen.", text)
        self.project.refresh_from_db()
        self.assertIsNone(self.project.follow_up_on)

    def test_a_closed_project_gets_one_too(self) -> None:
        Project.objects.filter(pk=self.project.pk).update(status=ProjectStatus.CLOSED)
        data = form_data(self.client.get(self.dialog), "follow_up_on", follow_up_on="2027-04-01")
        self.client.post(self.dialog, data)
        self.project.refresh_from_db()
        self.assertEqual(self.project.follow_up_on, datetime.date(2027, 4, 1))

    def test_rights(self) -> None:
        set_follow_up(self.project, on=datetime.date(2027, 3, 5), note="Rückruf", by=self.paula)
        reader = self.browser_for("nora", "Nur-Lesen")
        text = self.assert_ok(reader.get(self.page))
        self.assertIn("Wiedervorlage am Fr 05.03.2027", text)
        self.assertNotIn(f"{self.dialog}done/", text)
        self.assertEqual(reader.get(self.dialog).status_code, 403)
        self.assertEqual(reader.post(f"{self.dialog}done/").status_code, 403)
        # Crew sees the deployment view only: no follow-up.
        from tests.helpers import make_person, plan

        carla = make_user("carla", roles=("Crew",))
        plan(self.project, "Tontechnik", make_person("Carla Crew", user=carla))
        crew_page = self.assert_ok(self.browser_of(carla).get(reverse("projects:deployment", args=[self.project.pk])))
        self.assertNotIn("Rückruf", crew_page)


class FollowUpOverviewTests(UiTestCase):
    """PRJ-105: the start page shows the user's due follow-ups; the list filters and shows them."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.due = make_project("Firmenfeier", status=ProjectStatus.INQUIRY, manager=self.paula)
        self.later = make_project("Hochzeit", status=ProjectStatus.OPTION)
        self.closed = make_project("Messe", status=ProjectStatus.CONFIRMED)
        Project.objects.filter(pk=self.closed.pk).update(status=ProjectStatus.CLOSED)
        self.closed.refresh_from_db()
        set_follow_up(self.due, on=datetime.date(2027, 2, 26), note="Angebot nachfassen", by=self.paula)
        set_follow_up(self.later, on=datetime.date(2027, 3, 9), by=self.paula)
        set_follow_up(self.closed, on=datetime.date(2027, 3, 1), note="Zahlung prüfen", by=self.admin_user)

    def test_start_page(self) -> None:
        text = self.assert_ok(self.browser_of(self.paula).get("/"))
        self.assertIn("<h2>Deine Wiedervorlagen</h2>", text)
        block = text[text.index("Deine Wiedervorlagen") : text.index("</section>", text.index("Deine Wiedervorlagen"))]
        self.assertIn("Firmenfeier", block)
        self.assertIn("Angebot nachfassen", block)
        self.assertIn('<span class="badge yellow">überfällig</span>', block)
        self.assertNotIn("Hochzeit", block)  # not yet due
        self.assertNotIn("Messe", block)  # for somebody else
        self.assertIn(f'action="{reverse("projects:follow_up_done", args=[self.due.pk])}"', block)
        # VFG-034: "All my follow-ups" leads to Planung → Wiedervorlagen.
        self.assertIn('href="/schedule/follow-ups/?who=mine"', block)
        admin = self.assert_ok(self.client.get("/"))
        self.assertIn("Zahlung prüfen", admin)  # closed projects too
        # A reader without the right to edit sees the follow-up, without "Done".
        reader = make_user("nora", roles=("Nur-Lesen",))
        set_follow_up(self.later, on=datetime.date(2027, 3, 1), user=reader, by=self.paula)
        text = self.assert_ok(self.browser_of(reader).get("/"))
        self.assertIn("Deine Wiedervorlagen", text)
        self.assertNotIn(reverse("projects:follow_up_done", args=[self.later.pk]), text)

    def test_done_from_the_start_page(self) -> None:
        browser = self.browser_of(self.paula)
        done = reverse("projects:follow_up_done", args=[self.due.pk])
        response = browser.post(done, {"next": "/"}, follow=True)
        self.assertEqual(response.redirect_chain[-1][0], "/")
        self.assertNotIn("Deine Wiedervorlagen", self.assert_ok(response))

    def test_list_filters_and_shows_them(self) -> None:
        text = self.assert_ok(self.client.get("/projects/"))
        self.assertIn('<select id="f-follow-up" name="follow_up" data-autosubmit>', text)
        self.assertIn("Wiedervorlage am 26.02.2027 für paula – Angebot nachfassen", text)
        self.assertNotIn("Messe", text)  # closed: hidden in the everyday view
        due = self.assert_ok(self.client.get("/projects/?follow_up=due"))
        self.assertIn("Firmenfeier", due)
        self.assertIn("Messe", due)  # every status
        self.assertNotIn("Hochzeit", due)
        mine = self.assert_ok(self.browser_of(self.paula).get("/projects/?follow_up=mine&sort=follow_up"))
        self.assertLess(mine.index("Firmenfeier"), mine.index("Hochzeit"))
        self.assertNotIn("Messe", mine)
        every = self.assert_ok(self.client.get("/projects/?follow_up=any&cols=number,name,follow_up"))
        self.assertIn("<th", every)
        self.assertIn("Wiedervorlage am 09.03.2027 für paula", every)
        csv = self.client.get("/projects/?follow_up=any&cols=number,name,follow_up&format=csv").content.decode()
        self.assertIn("Wiedervorlage", csv.splitlines()[0])
        self.assertIn("Wiedervorlage am 01.03.2027 für admin – Zahlung prüfen", csv)

    def test_crew_sees_no_follow_ups_in_the_list(self) -> None:
        from tests.helpers import make_person, plan

        carla = make_user("carla", roles=("Crew",))
        plan(self.due, "Tontechnik", make_person("Carla Crew", user=carla))
        text = self.assert_ok(self.browser_of(carla).get("/projects/?follow_up=due"))
        # UIX-040: "Gruppieren nach" repeats the address as hidden fields; the filter itself is not there.
        self.assertNotIn('<select id="f-follow-up" name="follow_up"', text)
        self.assertNotIn("Angebot nachfassen", text)

    def test_queries_do_not_grow_with_the_follow_ups(self) -> None:
        """NFA-014: the user of each follow-up comes with the projects."""
        for path in ("/projects/?follow_up=any", "/", "/api/v1/projects?follow_up=any"):
            with self.subTest(path=path):
                with CaptureQueriesContext(connection) as few:
                    self.assert_ok(self.client.get(path)) if not path.startswith("/api") else self.client.get(path)
                for number in range(6):
                    extra = make_project(f"Projekt {number}", status=ProjectStatus.INQUIRY)
                    set_follow_up(extra, on=datetime.date(2027, 2, 28), user=self.admin_user, by=self.paula)
                with CaptureQueriesContext(connection) as many:
                    self.client.get(path)
                self.assertLessEqual(len(many), len(few) + 1, path)
                Project.objects.filter(name__startswith="Projekt ").delete()

    def test_the_kind_in_the_notification_settings(self) -> None:
        text = self.assert_ok(self.client.get("/account/notifications/"))
        self.assertIn("Wiedervorlage eines Projekts", text)
