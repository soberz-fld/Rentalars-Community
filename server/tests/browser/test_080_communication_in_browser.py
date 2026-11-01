# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser, area "communication": the chat in the project (UIX-010), automations (ADM-013).

* The chat: writing empties the field and shows the message at once; "@" offers the people who read along
  (keyboard: arrows, Enter); a message of somebody else comes in place through the change polling
  (UIX-020) – without loading the page and without losing what is typed; the tab of every project page
  shows the unread count.
* The form of an automation shows only the fields of the chosen trigger and action and offers only the
  actions that fit.
* On a phone without horizontal scrolling and checked with axe-core (NFA-025): the chat with messages and
  the open list of suggestions, the list of automations with runs, the form.
"""

from __future__ import annotations

from unittest import SkipTest

from rentalars.accounts.models import User
from rentalars.automations.models import Action, Automation, Recipient, Trigger
from rentalars.chat import services as chat
from rentalars.chat.models import ChatMessage
from rentalars.projects import services
from rentalars.projects.models import ProjectStatus
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.helpers import ALL_RIGHTS, make_person, make_user, plan


class ChatInBrowserTests(BrowserTestCase):
    """UIX-010: writing, mentioning, following the others."""

    watch_changes = True

    def setUp(self) -> None:
        super().setUp()
        self.anna = User.objects.get(username="anna")
        self.ben_user = make_user("ben", roles=("Crew",))
        plan(self.project, "Tontechnik", make_person("Ben Krüger", user=self.ben_user))
        self.ben_user.refresh_from_db()
        self.url = f"/projects/{self.project.number}/chat/"

    def ask_now(self) -> None:
        """The page asks every 20 seconds, and at once when it becomes visible again."""
        self.page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")

    def test_write_with_a_mention_by_keyboard(self) -> None:
        self.open(self.url)
        self.settle()
        field = self.page.locator("#chat-text")
        field.click()
        field.press_sequentially("Hallo @Ben K", delay=20)
        option = self.page.locator("#chat-suggestions [role=option]", has_text="Ben Krüger")
        option.wait_for()
        self.assertEqual(field.get_attribute("aria-activedescendant"), "chat-suggestion-0")
        field.press("Enter")
        self.assertEqual(field.input_value(), "Hallo @Ben Krüger ")
        self.assertTrue(self.page.locator("#chat-suggestions").is_hidden())
        field.press_sequentially("bitte Kabel mitbringen", delay=10)
        field.press("Control+Enter")
        self.page.locator(".chat-log .bubble.is-out", has_text="bitte Kabel mitbringen").wait_for()
        self.settle()
        self.assertEqual(field.input_value(), "")
        self.assertEqual(self.page.locator(".chat-log .mention").inner_text(), "@Ben Krüger")
        message = ChatMessage.objects.get()
        self.assertEqual(list(message.mentioned.all()), [self.ben_user])

    def test_mention_from_the_list_of_readers(self) -> None:
        self.open(self.url)
        self.page.locator(".chat-readers summary").click()
        self.page.locator(".chat-readers [data-chat-mention='Ben Krüger']").click()
        self.assertEqual(self.page.locator("#chat-text").input_value(), "@Ben Krüger ")

    def test_messages_of_others_come_in_place(self) -> None:
        self.open(self.url)
        self.settle()
        field = self.page.locator("#chat-text")
        field.click()
        field.press_sequentially("Ich schreibe gerade", delay=10)
        self.page.evaluate("window.notReloaded = true")
        chat.post_message(self.project, user=self.ben_user, text="Bin um acht da")
        self.ask_now()
        self.page.locator(".chat-log .bubble.is-in", has_text="Bin um acht da").wait_for()
        self.assertTrue(self.page.evaluate("window.notReloaded === true"))
        # Screen readers hear it: the list is replaced, a live region names author and text (UIX-010).
        announced = " ".join(self.page.locator("[data-chat-announce]").text_content().split())
        self.assertTrue(announced.startswith("Neue Nachricht von "), announced)
        self.assertTrue(announced.endswith(": Bin um acht da"), announced)
        self.assertEqual(field.input_value(), "Ich schreibe gerade")
        self.assertTrue(self.page.locator("#changed-note").is_hidden())

    def test_the_tab_shows_the_unread_count(self) -> None:
        chat.post_message(self.project, user=self.ben_user, text="Eins")
        chat.post_message(self.project, user=self.ben_user, text="Zwei")
        self.open_planning()
        badge = self.page.locator(f"[data-chat-unread='{self.project.pk}']")
        badge.wait_for()
        self.assertEqual(" ".join(badge.text_content().split()), "2 ungelesen")
        # A new message elsewhere: the count grows, the planning stays as it is.
        self.page.evaluate("window.notReloaded = true")
        chat.post_message(self.project, user=self.ben_user, text="Drei")
        self.ask_now()
        self.page.wait_for_function(
            f"() => document.querySelector(\"[data-chat-unread='{self.project.pk}']\").textContent.startsWith('3')"
        )
        self.assertTrue(self.page.evaluate("window.notReloaded === true"))
        self.page.locator(".tabs a", has_text="Chat").click()
        self.page.locator(".chat-log").wait_for()
        self.assertTrue(self.page.locator(f"[data-chat-unread='{self.project.pk}']").is_hidden())
        self.assertEqual(chat.unread_count(self.project, self.anna), 0)

    def test_change_and_delete_own_message(self) -> None:
        own = chat.post_message(self.project, user=self.anna, text="Tippfeler")
        self.open(self.url)
        bubble = self.page.locator(f"#m{own.pk}")
        bubble.locator("summary", has_text="Ändern").click()
        bubble.locator("textarea").fill("Tippfehler")
        bubble.get_by_role("button", name="Speichern").click()
        self.page.locator(f"#m{own.pk} .bubble-text", has_text="Tippfehler").wait_for()
        self.settle()
        self.assertIn("geändert", self.page.locator(f"#m{own.pk} time").inner_text())
        self.page.locator(f"#m{own.pk}").get_by_role("button", name="Löschen").click()
        self.confirm()
        self.page.locator(".chat-list .empty").wait_for()
        self.assertFalse(ChatMessage.objects.exists())


class AutomationFormInBrowserTests(BrowserTestCase):
    """ADM-013: the form shows what belongs to the chosen trigger and action."""

    def test_fields_follow_trigger_and_action(self) -> None:
        self.open("/administration/automations/new/")
        form = self.page.locator("form[data-automation-form]")
        reply = form.locator("[data-show-when='action:reply']")
        mailbox = form.locator("[data-show-when='trigger:inquiry']").first
        self.assertTrue(reply.is_hidden())
        self.assertTrue(mailbox.is_hidden())
        form.locator("#id_trigger").select_option("inquiry")
        self.assertTrue(mailbox.is_visible())
        form.locator("#id_action").select_option("reply")
        self.assertTrue(reply.is_visible())
        self.assertEqual(form.locator("#id_reply_subject").input_value(), "Eingangsbestätigung: {betreff}")
        # A status allows no answer by mail: the action falls back to one that fits.
        form.locator("#id_trigger").select_option("project_status")
        self.assertEqual(form.locator("#id_action").input_value(), "notify")
        self.assertTrue(form.locator("#id_action option[value=reply]").is_disabled())
        self.assertTrue(reply.is_hidden())
        self.assertTrue(form.locator("#id_user").is_visible())
        form.locator("#id_recipient").select_option("manager")
        self.assertTrue(form.locator("#id_user").is_hidden())
        self.assertTrue(form.locator("#id_recipient option[value=asked_by]").is_disabled())
        form.locator("#id_name").fill("Bestätigt")
        form.locator("#id_status").select_option("confirmed")
        form.locator("#id_notify_title").fill("{projekt} ist bestätigt")
        with self.page.expect_navigation():
            form.get_by_role("button", name="Automation speichern").click()
        # By name: on a fresh database the automations of the start data are there as well (order of the tests).
        rule = Automation.objects.get(name="Bestätigt")
        self.assertEqual(
            (rule.trigger, rule.status, rule.action, rule.recipient, rule.subject),
            ("project_status", "confirmed", "notify", "manager", "{projekt} ist bestätigt"),
        )


class CommunicationOnAPhoneTests(BrowserTestCase):
    """UIX-010, ADM-013: the new pages on a phone, with axe-core."""

    bypass_csp = True

    def check(self, path: str, *, then: object = None) -> None:
        axe = _axe_path()
        if axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        self.page.set_viewport_size({"width": 375, "height": 800})
        self.open(path)
        self.page.wait_for_load_state("networkidle")
        if callable(then):
            then()
        width = self.page.evaluate("document.scrollingElement.scrollWidth")
        self.assertLessEqual(width, 375, path)
        self.page.add_script_tag(path=str(axe))
        findings = self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            WCAG_AA,
        )
        self.assertEqual(findings, [], "\n".join(findings))

    def test_chat(self) -> None:
        anna = User.objects.get(username="anna")
        ben = make_user("ben", roles=("Crew",))
        plan(self.project, "Tontechnik", make_person("Ben Krüger", user=ben))
        ben.refresh_from_db()
        chat.post_message(self.project, user=ben, text="Bin um acht da. Lageplan: https://example.org/plan")
        chat.post_message(
            self.project, user=anna, text="@Ben Krüger danke, und bitte die lange Kabeltrommel mitbringen"
        )

        def suggestions() -> None:
            self.page.locator(".chat-readers summary").click()
            field = self.page.locator("#chat-text")
            field.click()
            field.press_sequentially("@B", delay=20)
            self.page.locator("#chat-suggestions [role=option]").first.wait_for()

        self.check(f"/projects/{self.project.number}/chat/", then=suggestions)

    def test_automations(self) -> None:
        anna = User.objects.get(username="anna")
        Automation.objects.create(
            name="Bestätigt melden",
            trigger=Trigger.PROJECT_STATUS,
            status=ProjectStatus.CONFIRMED,
            action=Action.NOTIFY,
            recipient=Recipient.USER,
            user=anna,
        )
        project = services.create_project(
            name="Neu",
            customer=self.project.customer,
            start=self.project.start,
            end=self.project.end,
            status=ProjectStatus.OPTION,
        )
        services.change_status(project, ProjectStatus.CONFIRMED, rights=ALL_RIGHTS)
        from rentalars.automations.engine import run_pending

        run_pending()
        self.check("/administration/automations/")
        self.check("/administration/automations/new/")
        rule = Automation.objects.get(name="Bestätigt melden")  # the start data may bring others (order of the tests)
        self.check(f"/administration/automations/{rule.pk}/")
