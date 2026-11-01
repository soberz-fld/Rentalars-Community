# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests: crew requests after changed times, and the footer of system mails.

* PER-033 – the answer shows at once: an answer by mail or in the browser
  moves the stamp of the project that open pages ask about, also the part
  "changed by somebody else" that one's own change does not swallow. The
  line remembers the period asked for; "ask again" only after new times.
* PER-034 – new times of a line asked for or accepted ask the person again
  by themselves (editing, moving the phase, API), with the times before –
  unless switched off in the settings; not for declined lines.
* EML-045 – every system mail says that Rentalars sent it, for which company
  and from which address; mails of the correspondence do not.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core import mail as django_mail
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.test import override_settings

from rentalars.accounts import services as account_services
from rentalars.core import changes
from rentalars.core.audit import acting_as
from rentalars.core.models import AuditLogEntry, CompanyProfile, SystemSettings
from rentalars.mail import crew_answers, footer
from rentalars.mail.models import CrewRequestMail
from rentalars.notifications.models import Kind, Notification
from rentalars.notifications.services import notify
from rentalars.projects import course, crew
from rentalars.projects.models import CrewLine, Project, ProjectStatus, RequestStatus
from tests.helpers import (
    ALL_RIGHTS,
    PASSWORD,
    RentalarsTestCase,
    at,
    make_person,
    make_project,
    make_user,
    plan,
)
from tests.mailbox import configure_mailbox
from tests.unit.test_063_crewmail import CrewMailTestCase, answer_mail

LOGGING_BACKEND = "rentalars.mail.backends.LoggingEmailBackend"
LOCMEM_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
FOOTER_START = "Diese Nachricht wurde automatisch von Rentalars"


def stamp(project: Project, user: Any) -> tuple[str, str]:
    """The stamp of a project as an open page sees it: (newest change, newest change by somebody else)."""
    key = f"project:{project.pk}"
    newest, _dot, others = changes.stamps([key], user)[key].partition(".")
    return newest, others


def set_ask_again(value: bool) -> None:
    system = SystemSettings.load()
    system.ask_again_on_new_times = value
    system.save()


# --- PER-033: the answer shows at once -------------------------------------------------------------------


class AnswerMovesTheStampTests(CrewMailTestCase):
    """PER-033: an answer – by mail or in the browser – is a change of the project that open pages see."""

    def setUp(self) -> None:
        super().setUp()
        self.ask()
        self.request = self.request_message()

    def test_an_answer_by_mail_moves_both_parts_of_the_stamp(self) -> None:
        before = stamp(self.project, self.manager)
        self.fetch(answer_mail(self.request))
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.ACCEPTED)
        after = stamp(self.project, self.manager)
        self.assertNotEqual(before[0], after[0])
        self.assertNotEqual(before[1], after[1])

    def test_the_planners_own_change_moves_only_the_first_part(self) -> None:
        """The page takes its own change over silently; what others did in between it still notices."""
        before = stamp(self.project, self.manager)
        with acting_as(self.manager):
            crew.update_crew_line(self.line, rights=ALL_RIGHTS, note="Bitte pünktlich")
        after = stamp(self.project, self.manager)
        self.assertNotEqual(before[0], after[0])
        self.assertEqual(before[1], after[1])
        # Somebody else sees the planner's change as a change by somebody else.
        colleague = make_user("colleague", superuser=True)
        self.assertEqual(stamp(self.project, colleague)[0], after[0])
        self.assertEqual(stamp(self.project, colleague)[1], after[0])

    def test_an_answer_in_the_browser_is_a_change_by_somebody_else(self) -> None:
        before = stamp(self.project, self.manager)
        account = self.person.user
        with acting_as(account):
            crew.answer_deployment(self.line, accept=False, user=account)
        self.assertNotEqual(stamp(self.project, self.manager)[1], before[1])

    def test_the_planning_shows_the_answer_and_no_ask_again(self) -> None:
        self.fetch(answer_mail(self.request))
        self.client.login(username="paula", password=PASSWORD)
        page = self.client.get(f"/projects/{self.project.number}/").content.decode()
        block = page[page.index(f'data-crew-line="{self.line.pk}"') :]
        block = block[: block.index("</tr>")]
        self.assertIn(">zugesagt</span>", block)
        self.assertNotIn("angefragt", block)
        self.assertNotIn("erneut anfragen", block)

    def test_the_changes_view_answers_with_both_parts(self) -> None:
        self.client.login(username="paula", password=PASSWORD)
        answer = self.client.get("/changes/", {"keys": f"project:{self.project.pk}"}).json()
        self.assertRegex(answer["stamps"][f"project:{self.project.pk}"], r"^\d+\.\d+$")


class RequestedPeriodTests(RentalarsTestCase):
    """PER-033: the line remembers the period asked for; an answered line is asked again only after new times."""

    def setUp(self) -> None:
        super().setUp()
        set_ask_again(False)
        self.manager = make_user("paula", roles=("Projektleitung",))
        self.project = make_project("Stadtfest", manager=self.manager)
        self.person = make_person("Anna Becker")
        self.line = plan(self.project, "Tontechnik", self.person, start=at(10, 8), end=at(10, 18))

    def answer(self, *, accept: bool = True) -> None:
        crew.answer_deployment(self.line, accept=accept, user=self.manager)

    def test_the_request_remembers_the_period(self) -> None:
        self.assertFalse(self.line.times_changed_since_request)
        crew.request_deployment(self.line, user=self.manager)
        self.line.refresh_from_db()
        self.assertEqual((self.line.requested_start, self.line.requested_end), (at(10, 8), at(10, 18)))
        self.assertFalse(self.line.times_changed_since_request)

    def test_an_answered_line_is_not_asked_again_for_the_same_times(self) -> None:
        for accept, verb in ((True, "zugesagt"), (False, "abgesagt")):
            with self.subTest(verb):
                crew.request_deployment(self.line, user=self.manager)
                self.answer(accept=accept)
                with self.assertRaises(ValidationError) as raised:
                    crew.request_deployment(self.line, user=self.manager)
                self.assertIn(f"Anna Becker hat für diese Zeiten schon {verb}.", " ".join(raised.exception.messages))
                self.line.refresh_from_db()
                self.assertNotEqual(self.line.request_status, RequestStatus.REQUESTED)
                # Back to the start for the next round.
                crew.update_crew_line(self.line, rights=ALL_RIGHTS, person=None)
                crew.update_crew_line(self.line, rights=ALL_RIGHTS, person=self.person)

    def test_a_waiting_request_can_be_sent_again(self) -> None:
        """E.g. after the address of the person was corrected."""
        crew.request_deployment(self.line, user=self.manager)
        crew.request_deployment(self.line, user=self.manager)
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.REQUESTED)

    def test_after_new_times_the_line_can_be_asked_again(self) -> None:
        crew.request_deployment(self.line, user=self.manager)
        self.answer()
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, start=at(10, 10))
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.ACCEPTED)  # the automation is off here
        self.assertTrue(self.line.times_changed_since_request)
        Notification.objects.all().delete()
        crew.request_deployment(self.line, user=self.manager)
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.REQUESTED)
        self.assertEqual((self.line.requested_start, self.line.requested_end), (at(10, 10), at(10, 18)))
        self.assertFalse(self.line.times_changed_since_request)
        notice = Notification.objects.get(kind=Kind.DEPLOYMENT_REQUEST)
        self.assertTrue(notice.title.startswith("Einsatzanfrage mit neuen Zeiten: "), notice.title)
        self.assertIn(
            "Neue Zeiten: Mi 10.03. 10:00 – Mi 10.03. 18:00 (vorher: Mi 10.03. 08:00 – Mi 10.03. 18:00)", notice.body
        )

    def test_times_changed_back_are_no_change(self) -> None:
        crew.request_deployment(self.line, user=self.manager)
        self.answer()
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, end=at(10, 20))
        self.assertTrue(self.line.times_changed_since_request)
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, end=at(10, 18))
        self.assertFalse(self.line.times_changed_since_request)

    def test_only_the_times_count(self) -> None:
        """Hours, note, meeting point, job function: no new request needed (the request concerned the times only)."""
        crew.request_deployment(self.line, user=self.manager)
        self.answer()
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, planned_hours="6", note="Mit Pause", meeting_point="Tor 3")
        self.assertFalse(self.line.times_changed_since_request)

    def test_a_new_person_starts_without_request(self) -> None:
        crew.request_deployment(self.line, user=self.manager)
        crew.update_crew_line(self.line, rights=ALL_RIGHTS, person=make_person("Ben Krause"))
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.NONE)
        self.assertIsNone(self.line.requested_start)
        self.assertFalse(self.line.times_changed_since_request)


# --- PER-034: new times ask again by themselves -------------------------------------------------------------


class AskAgainOnNewTimesTests(CrewMailTestCase):
    """PER-034: the person agrees to new times, or not."""

    def setUp(self) -> None:
        super().setUp()
        self.ask()
        self.first_request = self.request_message()

    def accept(self) -> None:
        self.fetch(answer_mail(self.first_request))
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.ACCEPTED)

    def move(self, **changes: Any) -> CrewLine:
        """Change the line as the dialog does: loaded fresh, as the planner."""
        django_mail.outbox.clear()
        self.line = CrewLine.objects.select_related("person", "job_function", "project").get(pk=self.line.pk)
        with self.captureOnCommitCallbacks(execute=True), acting_as(self.manager):
            return crew.update_crew_line(self.line, rights=ALL_RIGHTS, **changes)

    def test_the_setting_is_on_by_default(self) -> None:
        self.assertTrue(SystemSettings.load().ask_again_on_new_times)

    def test_an_accepted_line_is_asked_again_with_the_times_before(self) -> None:
        self.accept()
        line = self.move(start=at(10, 10), end=at(12, 2))
        self.assertTrue(line.asked_again)
        line.refresh_from_db()
        self.assertEqual(line.request_status, RequestStatus.REQUESTED)
        self.assertEqual((line.requested_start, line.requested_end), (line.start, line.end))
        self.assertIsNone(line.answered_at)
        self.assertEqual(line.requested_by, self.manager)
        (message,) = [mail for mail in django_mail.outbox if mail.to == ["anna@crew.example"]]
        self.assertTrue(message.subject.startswith("[Rentalars] Einsatzanfrage mit neuen Zeiten: "), message.subject)
        self.assertIn("die Zeiten deines Einsatzes haben sich geändert.", message.body)
        self.assertIn("Neue Zeiten: Mi 10.03.2027 10:00 – Fr 12.03.2027 02:00", message.body)
        self.assertIn("Vorher: Mi 10.03.2027 00:00 – Fr 12.03.2027 00:00", message.body)
        html = message.alternatives[0][0]
        self.assertIn("Neue Zeiten", html)
        self.assertIn("Mi 10.03.2027 00:00 – Fr 12.03.2027 00:00", html)
        self.assertEqual(CrewRequestMail.objects.filter(line=line).count(), 2)
        event = AuditLogEntry.objects.get(event="crew_line.asked_again_new_times")
        self.assertEqual(event.changes["old"], "Mi 10.03. 00:00 – Fr 12.03. 00:00")
        self.assertEqual(event.actor, self.manager)

    def test_the_answer_to_the_former_request_is_not_taken_over(self) -> None:
        """A line still waiting is asked again too; the buttons of the older mail no longer count."""
        self.move(end=at(12, 6))
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.REQUESTED)
        self.fetch(answer_mail(self.first_request))
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.REQUESTED)
        (reply,) = self.replies()
        self.assertIn("Für diesen Einsatz gibt es eine neuere Anfrage.", reply.body)

    def test_a_declined_line_is_not_asked_again_by_itself(self) -> None:
        self.fetch(answer_mail(self.first_request, accept=False))
        line = self.move(start=at(10, 10))
        self.assertFalse(hasattr(line, "asked_again"))
        line.refresh_from_db()
        self.assertEqual(line.request_status, RequestStatus.DECLINED)
        self.assertTrue(line.times_changed_since_request)
        self.assertEqual(self.replies(), [])

    def test_switched_off_nobody_is_asked(self) -> None:
        self.accept()
        set_ask_again(False)
        line = self.move(start=at(10, 10))
        line.refresh_from_db()
        self.assertEqual(line.request_status, RequestStatus.ACCEPTED)
        self.assertTrue(line.times_changed_since_request)
        # PER-041, PRJ-118: not asked – but told the new times ("Einsatz geändert").
        (message,) = self.replies()
        self.assertTrue(message.subject.startswith("[Rentalars] Einsatz geändert: "), message.subject)
        self.assertIn("Neue Zeiten", message.body)

    def test_other_changes_ask_nobody(self) -> None:
        self.accept()
        line = self.move(note="Bitte Werkzeug mitbringen", planned_hours="20")
        line.refresh_from_db()
        self.assertEqual(line.request_status, RequestStatus.ACCEPTED)
        # PER-041, PRJ-118: no request – but the new note is told; the hours are not.
        (message,) = self.replies()
        self.assertTrue(message.subject.startswith("[Rentalars] Einsatz geändert: "), message.subject)
        self.assertIn("Neue Notiz: Bitte Werkzeug mitbringen", message.body)

    def test_not_in_a_cancelled_project(self) -> None:
        self.accept()
        Project.objects.filter(pk=self.project.pk).update(status=ProjectStatus.CANCELLED)
        self.line.refresh_from_db()
        line = self.move(start=at(10, 10))
        line.refresh_from_db()
        self.assertEqual(line.request_status, RequestStatus.ACCEPTED)

    def test_moving_the_phase_with_its_crew_asks_again(self) -> None:
        """PRJ-080: the phase moves its crew; each moved line asked for or accepted is asked again."""
        phase = course.add_phase(self.project, kind="setup", start=self.line.start, end=self.line.end)
        with acting_as(self.manager):
            crew.update_crew_line(self.line, rights=ALL_RIGHTS, phase=phase)
        self.accept()
        django_mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True), acting_as(self.manager):
            change = course.update_phase(phase, move_crew=True, start=at(10, 6), end=at(12, 6))
        (moved,) = change.moved_crew_lines
        self.assertTrue(moved.asked_again)
        moved.refresh_from_db()
        self.assertEqual(moved.request_status, RequestStatus.REQUESTED)
        self.assertEqual(len(self.replies()), 1)

    def test_a_person_told_by_nobody_is_marked_asked(self) -> None:
        """Without address and without an account that can log in, the planner enters the answer (phone)."""
        self.accept()
        self.person.email = ""
        self.person.save()
        # Bypassing the link of person and account (AUT-026): an account that cannot be told.
        type(self.person.user).objects.filter(pk=self.person.user_id).update(is_active=False)
        line = self.move(start=at(10, 10))
        self.assertIs(line.asked_again, False)
        line.refresh_from_db()
        self.assertEqual(line.request_status, RequestStatus.REQUESTED)


# --- EML-045: the footer of every system mail ----------------------------------------------------------


@override_settings(EMAIL_BACKEND=LOGGING_BACKEND, EMAIL_INNER_BACKEND=LOCMEM_BACKEND)
class FooterTests(RentalarsTestCase):
    """EML-045: every mail Rentalars sends by itself names Rentalars, the company and the address."""

    def setUp(self) -> None:
        super().setUp()
        company = CompanyProfile.load()
        company.name = "Musterverleih GmbH"
        company.save()
        self.footer = f"{FOOTER_START} für Musterverleih GmbH versendet: {settings.RENTALARS_URL}"
        django_mail.outbox.clear()

    def assert_footer(self, message: Any) -> None:
        self.assertTrue(message.body.endswith(f"\n\n-- \n{self.footer}\n"), message.body[-300:])
        for content, mimetype in getattr(message, "alternatives", []):
            if mimetype == "text/html":
                self.assertIn("für Musterverleih GmbH versendet:", content)
                self.assertIn(f'<a href="{settings.RENTALARS_URL}"', content)
                self.assertLess(content.index("Musterverleih GmbH versendet"), content.index("</body>"))

    def test_a_notification(self) -> None:
        user = make_user("paula")
        with self.captureOnCommitCallbacks(execute=True):
            notify([user], Kind.SHORTAGE, "Fehlbestand")
        (message,) = django_mail.outbox
        self.assert_footer(message)

    def test_the_invitation_and_the_password_link(self) -> None:
        ben = account_services.invite_user(username="ben", email="ben@example.de")
        (invitation,) = django_mail.outbox
        self.assert_footer(invitation)
        django_mail.outbox.clear()
        ben.set_password(PASSWORD)  # Django sends the link only to accounts with a password
        ben.save()
        self.client.post("/password-reset/", {"email": "ben@example.de"})
        self.assertEqual(len(django_mail.outbox), 1, "the browser form sends the password link")
        self.assert_footer(django_mail.outbox[0])
        # The same link asked for through the API (AUT-004).
        self.client.post("/api/v1/auth/password-reset", {"email": "ben@example.de"}, content_type="application/json")
        self.assertEqual(len(django_mail.outbox), 2, "the API sends the password link")
        self.assert_footer(django_mail.outbox[1])

    def test_a_report_of_an_error_to_the_operators(self) -> None:
        """NFA-018: errors of the application go to the operators as a notification with its mail."""
        from rentalars.notifications.services import notify_operators_of_error

        make_user("admin", superuser=True)
        error = type(
            "Error", (), {"message": "Kaputt", "source": "test", "count": 1, "first_seen": at(1), "last_seen": at(1)}
        )()
        with self.captureOnCommitCallbacks(execute=True):
            notify_operators_of_error(error)
        (message,) = django_mail.outbox
        self.assert_footer(message)

    def test_the_test_mail_of_the_self_check(self) -> None:
        admin = make_user("admin", superuser=True)
        self.client.force_login(admin)
        self.client.post("/administration/self-check/", {"action": "test_mail"})
        (message,) = django_mail.outbox
        self.assert_footer(message)

    def test_the_request_mail_and_the_reply_to_an_answer(self) -> None:
        configure_mailbox()
        manager = make_user("paula")
        project = make_project(manager=manager)
        line = plan(project, "Tontechnik", make_person("Anna Becker", email="anna@crew.example"))
        with self.captureOnCommitCallbacks(execute=True):
            crew.request_deployment(line, user=manager)
        (request,) = django_mail.outbox
        self.assert_footer(request)
        self.assertEqual(len(request.alternatives), 1)
        reply = crew_answers.reply_message(line.person, line, accept=True, reason="", note="", sender="")
        reply.send()
        self.assert_footer(django_mail.outbox[-1])
        self.assertEqual(django_mail.outbox[-1].body.count(FOOTER_START), 1)

    def test_once_even_if_sent_twice(self) -> None:
        message = EmailMessage("Test", "Hallo", None, ["a@example.de"])
        message.send()
        message.send()
        self.assertEqual(django_mail.outbox[-1].body.count(FOOTER_START), 1)

    def test_an_html_only_mail_and_a_mail_without_body_tag(self) -> None:
        message = EmailMessage("Test", "<html><body><p>Hallo</p></BODY></html>", None, ["a@example.de"])
        message.content_subtype = "html"
        message.send()
        body = django_mail.outbox[-1].body
        self.assertRegex(body, r"<p>Hallo</p><p [^>]+>Diese Nachricht wurde automatisch .*</p>\n</BODY></html>$")
        fragment = EmailMultiAlternatives("Test", "Hallo", None, ["a@example.de"])
        fragment.attach_alternative("<p>Hallo</p>", "text/html")
        fragment.send()
        self.assertTrue(django_mail.outbox[-1].alternatives[0][0].startswith("<p>Hallo</p>\n<p "))

    def test_without_a_company_name(self) -> None:
        company = CompanyProfile.load()
        company.name = ""
        company.save()
        EmailMessage("Test", "Hallo", None, ["a@example.de"]).send()
        self.assertTrue(
            django_mail.outbox[-1].body.endswith(f"{FOOTER_START} versendet: {settings.RENTALARS_URL}\n"),
            django_mail.outbox[-1].body,
        )

    def test_the_company_name_is_escaped_in_html(self) -> None:
        self.assertIn("Müller &amp; Söhne", footer.footer_html("Müller & Söhne"))
        self.assertIn("Müller & Söhne", footer.footer_text("Müller & Söhne"))

    def test_not_the_correspondence(self) -> None:
        """Mails of a project are written by a person and carry the signature, not the footer."""
        from rentalars.mail import sending
        from tests.mailbox import capture_smtp

        configure_mailbox()
        user = make_user("paula")
        project = make_project()
        with capture_smtp() as sent:
            sending.send_project_mail(project, to="kunde@example.de", subject="Angebot", body="Hallo", user=user)
        (message,) = sent
        self.assertNotIn(FOOTER_START, message.as_string())

    def test_in_the_mail_log_the_mail_is_noted_as_before(self) -> None:
        from rentalars.mail.models import LogKind, MailLogEntry

        EmailMessage("Test", "Hallo", None, ["a@example.de"]).send()
        self.assertTrue(MailLogEntry.objects.filter(kind=LogKind.SYSTEM, subject="Test").exists())


class HistoryTextTests(RentalarsTestCase):
    """PER-034: the history names the request with new times, and the times before."""

    def test_history_text_of_asking_again(self) -> None:
        from rentalars.core.history import EVENT_TEXTS

        text = str(EVENT_TEXTS["crew_line.asked_again_new_times"]) % {
            "person": "Anna Becker",
            "new": "Mi 10.03. 10:00 – Mi 10.03. 18:00",
            "old": "Mi 10.03. 08:00 – Mi 10.03. 18:00",
        }
        self.assertEqual(
            text,
            "Anna Becker neu angefragt für neue Zeiten: Mi 10.03. 10:00 – Mi 10.03. 18:00 "
            "(vorher: Mi 10.03. 08:00 – Mi 10.03. 18:00)",
        )
