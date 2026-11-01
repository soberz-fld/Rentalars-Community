# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages, area "communication": the chat in the project (UIX-010), Einstellungen → Automationen (ADM-013).

UIX-010
    The tab "Chat" on every project page – for the crew with the deployment
    view too –, the page with the note who reads along, writing with and
    without htmx, changing and deleting within 15 minutes, the list of
    messages fetched in place, the refusal for whoever cannot open the
    project. The chat page is one of the pages measured for NFA-012.
ADM-013
    The list of rules and runs, the form with its checks, switching on and
    off, deleting; the rights of the settings; the mail log names the
    automatic answer.
"""

from __future__ import annotations

from django.db import connection
from django.test.utils import CaptureQueriesContext

from rentalars.automations.models import Action, Automation, AutomationRun, Recipient, RunStatus, Trigger
from rentalars.chat import services as chat
from rentalars.chat.models import ChatMessage
from rentalars.mail.fetching import fetch_mail
from rentalars.projects.models import ProjectStatus
from tests.helpers import at, make_person, make_project, make_user, plan, set_clock
from tests.mailbox import capture_smtp, configure_mailbox, mailbox, make_mail
from tests.ui.base import UiTestCase, form_data

AUTOMATIONS = "/administration/automations/"


class ChatPageTests(UiTestCase):
    """UIX-010: the chat of a project in the browser."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.crew_user = make_user("anna", roles=("Crew",))
        self.anna = make_person("Anna Becker", user=self.crew_user)
        plan(self.project, "Tontechnik", self.anna)
        self.url = f"/projects/{self.project.number}/chat/"

    def test_the_tab_on_every_project_page(self) -> None:
        text = self.assert_ok(self.client.get(f"/projects/{self.project.number}/"))
        self.assertIn(
            f'<a href="{self.url}">Chat<span class="badge accent hidden" data-chat-unread="{self.project.pk}"', text
        )
        # Stock refresh: the planning page also watches the stock figures of its availability column.
        self.assertIn(
            f'data-watch="notifications,project:{self.project.pk},chat:{self.project.pk},stock:{self.project.pk}"', text
        )
        crew = self.browser_of(self.crew_user)
        text = self.assert_ok(crew.get(f"/projects/{self.project.number}/deployment/"))
        self.assertIn(f'href="{self.url}"', text)

    def test_the_page_says_who_reads_along(self) -> None:
        text = self.assert_ok(self.client.get(self.url))
        self.assertIn("<title>Chat 2027-0001", text.replace("\n", " "))
        self.assertIn('aria-current="page">Chat', text)
        self.assertIn(
            "Alle, die dieses Projekt öffnen können, lesen hier mit – auch die eingeplante Crew über den Überblick.",
            text,
        )
        self.assertIn("2 Personen lesen mit", text)
        self.assertIn('data-chat-mention="Anna Becker"', text)
        self.assertIn('<span class="badge">Crew</span>', text)
        self.assertIn('admin <span class="muted">(du)</span>', text)
        self.assertIn("Noch keine Nachrichten.", text)
        self.assertIn(
            "Mit @ und einem Namen erwähnst du jemanden – die Person wird benachrichtigt. Strg+Enter sendet.", text
        )

    def test_write_without_and_with_htmx(self) -> None:
        response = self.client.post(self.url, {"text": "Kabel liegen bereit @Anna Becker"})
        message = ChatMessage.objects.get()
        self.assertRedirects(response, f"{self.url}#m{message.pk}", fetch_redirect_response=False)
        response = self.htmx("post", self.url, {"text": "Zweite Nachricht"})
        self.assertEqual(response["HX-Trigger"], "chatSent")
        text = self.assert_ok(response)
        self.assertIn("Zweite Nachricht", text)
        self.assertIn('<strong class="mention">@Anna Becker</strong>', text)
        self.assertNotIn("<html", text)
        # Empty: the list again, with the reason; nothing stored.
        response = self.htmx("post", self.url, {"text": "  "})
        self.assertNotIn("HX-Trigger", response)
        self.assertIn('role="alert"', self.assert_ok(response))
        self.assertEqual(ChatMessage.objects.count(), 2)
        response = self.client.post(self.url, {"text": ""})
        self.assertEqual(response.status_code, 200)

    def test_others_left_own_right_and_changing_within_minutes(self) -> None:
        other = chat.post_message(self.project, user=self.crew_user, text="Ich bin um 8 da")
        own = chat.post_message(self.project, user=self.admin_user, text="Gut")
        text = self.assert_ok(self.client.get(self.url))
        self.assertIn(f'<li class="bubble is-in" id="m{other.pk}">', text)
        self.assertIn(f'<li class="bubble is-out" id="m{own.pk}">', text)
        self.assertIn(f"/chat/{own.pk}/edit/", text)
        self.assertNotIn(f"/chat/{other.pk}/edit/", text)
        self.assertIn("Montag, 01.03.2027", text)
        response = self.htmx("post", f"{self.url}{own.pk}/edit/", {"text": "Sehr gut"})
        self.assertIn("Sehr gut", self.assert_ok(response))
        self.assertIn("· geändert", self.assert_ok(response))
        # Somebody else's message: refused.
        self.assertEqual(self.htmx("post", f"{self.url}{other.pk}/edit/", {"text": "x"}).status_code, 403)
        set_clock(at(1, 8, 20))
        text = self.assert_ok(self.client.get(self.url))
        self.assertNotIn(f"/chat/{own.pk}/edit/", text)
        response = self.client.post(f"{self.url}{own.pk}/delete/", follow=True)
        self.assertIn(
            "Eine Nachricht lässt sich nur in den ersten 15 Minuten nach dem Schreiben ändern.",
            self.messages_of(response),
        )
        set_clock(at(1, 8))
        self.htmx("post", f"{self.url}{own.pk}/delete/")
        self.assertFalse(ChatMessage.objects.filter(pk=own.pk).exists())

    def test_the_crew_reads_and_writes_and_others_do_not_see_it(self) -> None:
        crew = self.browser_of(self.crew_user)
        self.assert_ok(crew.get(self.url))
        crew.post(self.url, {"text": "Von der Crew"})
        self.assertEqual(ChatMessage.objects.get().author, self.crew_user)
        stranger = self.browser_for("otto", "Crew")
        self.assertEqual(stranger.get(self.url).status_code, 404)
        self.assertEqual(stranger.post(self.url, {"text": "x"}).status_code, 404)
        # Without the module "projects" not even the address answers.
        self.assertEqual(self.browser_for("ohne").get(self.url).status_code, 403)

    def test_the_messages_alone_and_reading(self) -> None:
        chat.post_message(self.project, user=self.crew_user, text="Neu")
        self.assertEqual(chat.unread_count(self.project, self.admin_user), 1)
        text = self.assert_ok(self.client.get(f"{self.url}messages/"))
        self.assertIn('<div class="chat-list" data-stamp="', text)
        self.assertIn("Neu", text)
        self.assertEqual(chat.unread_count(self.project, self.admin_user), 0)

    def test_older_messages(self) -> None:
        for number in range(102):
            ChatMessage.objects.create(
                project=self.project, author=self.crew_user, author_name="Anna", text=f"N{number}"
            )
        text = self.assert_ok(self.client.get(self.url))
        self.assertIn("Ältere Nachrichten", text)
        first = ChatMessage.objects.order_by("pk")[2]
        self.assertIn(f"?before={first.pk}", text)
        older = self.assert_ok(self.client.get(f"{self.url}?before={first.pk}"))
        self.assertIn(">N0<", older)
        self.assertNotIn("Ältere Nachrichten", older)

    def test_bounded_number_of_queries(self) -> None:
        for number in range(30):
            chat.post_message(
                self.project, user=self.crew_user if number % 2 else self.admin_user, text=f"@Anna Becker {number}"
            )
        with CaptureQueriesContext(connection) as queries:
            self.assert_ok(self.client.get(self.url))
        self.assertLess(len(queries), 45)


class AutomationPageTests(UiTestCase):
    """ADM-013: Einstellungen → Automationen."""

    def setUp(self) -> None:
        super().setUp()
        # Without the default rules of the service cases (PRJ-112), which every installation gets.
        Automation.objects.all().delete()

    def test_the_way_in_and_the_empty_page(self) -> None:
        self.assertIn(f'<a href="{AUTOMATIONS}">Automationen</a>', self.assert_ok(self.client.get("/administration/")))
        text = self.assert_ok(self.client.get(AUTOMATIONS))
        self.assertIn("<h1>Automationen</h1>", text)
        self.assertIn("Noch keine Automationen.", text)
        self.assertIn("Neue Automation", text)

    def test_create_an_answer_to_inquiries(self) -> None:
        box = configure_mailbox(process_untagged=True)
        response = self.client.get(f"{AUTOMATIONS}new/")
        text = self.assert_ok(response)
        self.assertIn("Eingangsbestätigung: {betreff}", text)
        self.assertIn("Guten Tag {name},", text)
        self.assertIn('data-show-when="action:notify;recipient:user"', text)
        self.assertIn("<code>{postfach}</code>", text)
        data = form_data(
            response, "reply_text", name="Eingangsbestätigung", trigger="inquiry", action="reply", mailbox=str(box.pk)
        )
        response = self.client.post(f"{AUTOMATIONS}new/", data, follow=True)
        self.assertIn("Die Automation „Eingangsbestätigung“ ist gespeichert.", self.messages_of(response))
        rule = Automation.objects.get()
        self.assertEqual(
            (rule.trigger, rule.action, rule.mailbox, rule.subject),
            ("inquiry", "reply", box, "Eingangsbestätigung: {betreff}"),
        )
        self.assertTrue(rule.text.startswith("Guten Tag {name},"))
        self.assertEqual(rule.created_by, self.admin_user)
        text = self.assert_ok(response)
        self.assertIn("Eine Mail ohne Projektkennung kommt an", text)
        self.assertIn("im Postfach Projekte", text)
        self.assertIn("Die Mail beantworten", text)

    def test_what_does_not_fit_is_refused(self) -> None:
        response = self.client.get(f"{AUTOMATIONS}new/")
        data = form_data(response, "reply_text", name="Falsch", trigger="project_status", action="reply")
        text = self.assert_ok(self.client.post(f"{AUTOMATIONS}new/", data))
        self.assertIn(
            "Bei diesem Auslöser sind möglich: einen offenen Punkt im Projekt notieren",
            text.replace("jemanden benachrichtigen, ", ""),
        )
        data.update(action="notify", recipient="user", status="")
        text = self.assert_ok(self.client.post(f"{AUTOMATIONS}new/", data))
        self.assertIn("Wähle den Status.", text)
        self.assertIn("Wähle, wer benachrichtigt wird.", text)
        data.update(action="open_item", item_text="", status="confirmed")
        self.assertIn("Schreib, was zu tun ist.", self.assert_ok(self.client.post(f"{AUTOMATIONS}new/", data)))
        self.assertFalse(Automation.objects.exists())

    def test_notify_and_what_does_not_belong_is_emptied(self) -> None:
        lena = make_user("lena", roles=("Projektleitung",))
        response = self.client.get(f"{AUTOMATIONS}new/")
        data = form_data(
            response,
            "reply_text",
            name="Absage",
            trigger="crew_answer",
            answer="declined",
            action="notify",
            recipient="user",
            user=str(lena.pk),
            notify_title="{antwort} von {person}",
            status="confirmed",
        )
        self.client.post(f"{AUTOMATIONS}new/", data)
        rule = Automation.objects.get()
        self.assertEqual(
            (rule.answer, rule.user, rule.subject, rule.text, rule.status),
            ("declined", lena, "{antwort} von {person}", "", ""),
        )
        text = self.assert_ok(self.client.get(f"{AUTOMATIONS}{rule.pk}/"))
        self.assertIn('value="{antwort} von {person}"', text)
        data = form_data(self.client.get(f"{AUTOMATIONS}{rule.pk}/"), "notify_title", recipient="asked_by")
        self.client.post(f"{AUTOMATIONS}{rule.pk}/", data)
        rule.refresh_from_db()
        self.assertEqual((rule.recipient, rule.user), (Recipient.ASKED_BY, None))

    def test_switch_and_delete_and_the_runs(self) -> None:
        manager = make_user("lena", roles=("Projektleitung",))
        rule = Automation.objects.create(
            name="Bestätigt melden",
            trigger=Trigger.PROJECT_STATUS,
            status=ProjectStatus.CONFIRMED,
            action=Action.NOTIFY,
            recipient=Recipient.MANAGER,
        )
        with self.captureOnCommitCallbacks(execute=True):
            make_project(manager=manager)
        text = self.assert_ok(self.client.get(AUTOMATIONS))
        self.assertIn("Bestätigt melden", text)
        self.assertIn("Erledigt", text)
        self.assertIn("Benachrichtigt: lena", text)
        self.assertIn(f'href="?automation={rule.pk}#runs">1</a>', text)
        self.assertIn("2027-0001 Stadtfest: Bestätigt", text)
        self.assertIn(">1</a>", self.assert_ok(self.client.get(f"{AUTOMATIONS}?automation={rule.pk}&status=done")))
        self.assertIn("Noch keine Ausführungen.", self.assert_ok(self.client.get(f"{AUTOMATIONS}?status=failed")))
        response = self.client.post(f"{AUTOMATIONS}{rule.pk}/toggle/", follow=True)
        self.assertIn("Die Automation „Bestätigt melden“ ist ausgeschaltet.", self.messages_of(response))
        rule.refresh_from_db()
        self.assertFalse(rule.is_active)
        response = self.client.post(f"{AUTOMATIONS}{rule.pk}/delete/", follow=True)
        self.assertIn(
            "Die Automation „Bestätigt melden“ ist gelöscht. Ihre Ausführungen bleiben in der Liste.",
            self.messages_of(response),
        )
        text = self.assert_ok(response)
        self.assertIn('Bestätigt melden <span class="muted small">(gelöscht)</span>', text)
        self.assertEqual(AutomationRun.objects.get().status, RunStatus.DONE)

    def test_rights(self) -> None:
        viewer = self.browser_for("nur", "Nur-Lesen")
        self.assertEqual(viewer.get(AUTOMATIONS).status_code, 403)
        crew = self.browser_for("anna", "Crew")
        self.assertEqual(crew.get(f"{AUTOMATIONS}new/").status_code, 403)

    def test_the_mail_log_names_the_automatic_answer(self) -> None:
        configure_mailbox(process_untagged=True)
        Automation.objects.create(name="Danke", trigger=Trigger.INQUIRY, action=Action.REPLY, text="Danke")
        with mailbox(make_mail("Anfrage Juni")), capture_smtp(), self.captureOnCommitCallbacks(execute=True):
            fetch_mail(force=True)
        text = self.assert_ok(self.client.get("/administration/mail/log/?kind=automatic"))
        self.assertIn("automatische Antwort", text)
        self.assertIn("AW: Anfrage Juni", text)
