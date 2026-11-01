# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "settings": ADM-015, EML-046, PRJ-105.

* ADM-015: "Antwort auf Einsatzanfragen" (PER-032) is chosen with the other
  settings under Firmendaten und Grundeinstellungen; it is still kept with the
  mail settings.
* EML-046: every mailbox can be deleted; mails and mail log keep its name.
* PRJ-105: the follow-up ("Wiedervorlage") of a project – set, notified on its
  day, filtered, done.
"""

from __future__ import annotations

import datetime
import io

from django.core import mail as django_mail
from django.core.exceptions import ValidationError
from django.core.management import call_command

from rentalars.core.forms import SystemSettingsForm
from rentalars.core.models import AuditLogEntry, SystemSettings
from rentalars.mail.fetching import fetch_mail
from rentalars.mail.forms import MailRulesForm
from rentalars.mail.log import filtered_entries, record
from rentalars.mail.mailboxes import delete_mailbox, deletion_of, save_mailbox, switch_off_mailbox
from rentalars.mail.models import (
    CrewAnswerMode,
    Direction,
    LogKind,
    LogResult,
    Mailbox,
    MailLogEntry,
    MailSettings,
    ProjectMail,
    UnknownTagMail,
)
from rentalars.notifications.models import Kind, Notification, Preference
from rentalars.projects.follow_up import (
    clear_follow_up,
    due_for,
    filter_projects,
    notify_due_follow_ups,
    set_follow_up,
)
from rentalars.projects.models import Project, ProjectStatus
from tests.helpers import BERLIN, RentalarsTestCase, make_project, make_user, set_clock
from tests.mailbox import FakeMailbox, add_mailbox, configure_mailbox, mailboxes, make_mail


def moment(day: int, hour: int, minute: int = 0) -> datetime.datetime:
    """A moment in March 2027, Berlin time."""
    return datetime.datetime(2027, 3, day, hour, minute, tzinfo=BERLIN)


# --- ADM-015 --------------------------------------------------------------------------------------------


class CrewAnswerSettingTests(RentalarsTestCase):
    """ADM-015: the choice lives in the form of the settings and is stored with the mail settings."""

    def test_the_settings_form_offers_and_stores_it(self) -> None:
        form = SystemSettingsForm(instance=SystemSettings.load(), prefix="system")
        self.assertEqual(form.fields["crew_answers"].initial, CrewAnswerMode.BOTH)
        data = {f"system-{name}": value for name, value in form.initial.items() if value is not None}
        data["system-crew_answers"] = CrewAnswerMode.LINK
        bound = SystemSettingsForm(data, instance=SystemSettings.load(), prefix="system")
        self.assertTrue(bound.is_valid(), bound.errors)
        bound.save()
        self.assertEqual(MailSettings.load().crew_answers, CrewAnswerMode.LINK)

    def test_the_rules_of_the_mailboxes_no_longer_offer_it(self) -> None:
        self.assertNotIn("crew_answers", MailRulesForm().fields)


# --- EML-046 --------------------------------------------------------------------------------------------


class DeleteMailboxTests(RentalarsTestCase):
    """EML-046: deleting keeps the name in mails and log; roles and waiting inquiries go with it."""

    def setUp(self) -> None:
        super().setUp()
        self.projects = configure_mailbox()
        self.info = add_mailbox("Info", "info@verleih.example", process_untagged=True)
        self.project = make_project()

    def fetch(self) -> None:
        with mailboxes(
            {
                "projekte@verleih.example": FakeMailbox(),
                "info@verleih.example": FakeMailbox(
                    make_mail(f"Bühnenplan [RL#{self.project.number}]"),
                    make_mail("Anfrage für Juni", message_id="<juni@kunde.example>"),
                ),
            }
        ):
            fetch_mail(force=True)

    def test_mails_and_log_keep_the_name(self) -> None:
        self.fetch()
        self.assertEqual(ProjectMail.objects.get().mailbox_name, "Info")
        self.assertTrue(MailLogEntry.objects.filter(mailbox=self.info, mailbox_name="Info").exists())
        self.assertEqual(UnknownTagMail.objects.filter(mailbox=self.info).count(), 1)

        self.assertEqual(delete_mailbox(self.info), [])

        mail = ProjectMail.objects.get()
        self.assertEqual((mail.mailbox_id, mail.mailbox_name, mail.mailbox_label), (None, "Info", "Info (gelöscht)"))
        entries = MailLogEntry.objects.filter(mailbox_name="Info")
        self.assertTrue(entries.exists())
        self.assertFalse(entries.exclude(mailbox=None).exists())
        self.assertEqual({entry.mailbox_label for entry in entries}, {"Info (gelöscht)"})
        # What waited in it under Projects → Inquiries leaves the list; on the server it stays.
        self.assertFalse(UnknownTagMail.objects.exists())
        # The log still finds the entries by the name of the deleted mailbox.
        self.assertEqual(filtered_entries(text="info").count(), entries.count())

    def test_a_renamed_mailbox_renames_its_mails_and_log(self) -> None:
        self.fetch()
        self.info.name = "Anfragen"
        save_mailbox(self.info)
        self.assertEqual(ProjectMail.objects.get().mailbox_name, "Anfragen")
        self.assertFalse(MailLogEntry.objects.filter(mailbox=self.info).exclude(mailbox_name="Anfragen").exists())

    def test_every_new_entry_notes_the_name(self) -> None:
        entry = record(
            direction=Direction.OUTGOING,
            kind=LogKind.SYSTEM,
            result=LogResult.SENT,
            subject="Einladung",
            mailbox=self.projects,
        )
        self.assertEqual(entry.mailbox_name, "Projekte")
        self.assertEqual(entry.mailbox_label, "Projekte")
        without = record(direction=Direction.OUTGOING, kind=LogKind.SYSTEM, result=LogResult.SENT, subject="x")
        self.assertEqual((without.mailbox_name, without.mailbox_label), ("", ""))

    def test_what_deleting_would_do(self) -> None:
        self.fetch()
        deletion = deletion_of(self.info)
        self.assertEqual((deletion.mails, deletion.waiting, deletion.blocked), (1, 1, ""))
        self.assertGreaterEqual(deletion.log_entries, 2)
        self.assertEqual(deletion.roles, ["Korrespondenz"])
        self.assertFalse(deletion.needs_successor)
        sender = deletion_of(self.projects)
        self.assertEqual(sender.roles, ["Korrespondenz", "Postausgang der Korrespondenz"])
        self.assertEqual(sender.successors, [self.info])
        # PER-032: the answers to deployment requests by mail go to the mailbox that sends the correspondence.
        self.assertTrue(sender.takes_crew_answers)

    def test_with_several_others_the_one_that_sends_is_chosen(self) -> None:
        other = add_mailbox("Büro", "buero@verleih.example")
        with self.assertRaises(ValidationError) as refused:
            delete_mailbox(self.projects)
        self.assertIn("successor", refused.exception.message_dict)
        self.assertTrue(Mailbox.objects.filter(pk=self.projects.pk).exists())
        notes = delete_mailbox(self.projects, successor=other)
        self.assertEqual(notes, ["„Büro“ versendet jetzt die Korrespondenz."])
        other.refresh_from_db()
        self.info.refresh_from_db()
        self.assertEqual((other.is_outgoing, self.info.is_outgoing), (True, False))

    def test_the_last_mailbox_goes_with_its_roles(self) -> None:
        self.info.delete()
        self.projects.for_system = True
        save_mailbox(self.projects)
        self.assertEqual(delete_mailbox(self.projects), [])
        self.assertFalse(Mailbox.objects.exists())

    def test_switching_off_stays_possible(self) -> None:
        # The mailbox that sends stays on while another of the correspondence is active.
        with self.assertRaises(ValidationError):
            switch_off_mailbox(self.projects)
        switch_off_mailbox(self.info)
        self.info.refresh_from_db()
        self.assertFalse(self.info.is_active)
        self.assertEqual(ProjectMail.objects.filter(mailbox_name="").count(), 0)


# --- PRJ-105 --------------------------------------------------------------------------------------------


class FollowUpTests(RentalarsTestCase):
    """PRJ-105: day, note and user of a follow-up; who may get one; done."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.project = make_project("Firmenfeier", status=ProjectStatus.INQUIRY, manager=self.paula)

    def test_set_for_who_sets_it(self) -> None:
        set_follow_up(self.project, on=datetime.date(2027, 3, 5), note="Angebot nachfassen", by=self.paula)
        self.project.refresh_from_db()
        self.assertEqual(
            (self.project.follow_up_on, self.project.follow_up_note, self.project.follow_up_user),
            (datetime.date(2027, 3, 5), "Angebot nachfassen", self.paula),
        )
        self.assertFalse(self.project.follow_up_is_due)
        # The history of the project shows who set which day.
        entry = AuditLogEntry.objects.filter(object_id=str(self.project.pk), action="updated").latest("pk")
        self.assertEqual(entry.changes["follow_up_on"], [None, "2027-03-05"])
        self.assertEqual(entry.changes["follow_up_user"], [None, self.paula.pk])
        self.assertNotIn("follow_up_notified_at", entry.changes)

    def test_for_somebody_else_who_may_open_the_project(self) -> None:
        vera = make_user("vera", roles=("Projektleitung",))
        set_follow_up(self.project, on=datetime.date(2027, 3, 2), user=vera, by=self.paula)
        self.assertEqual(self.project.follow_up_user, vera)
        crew = make_user("carla", roles=("Crew",))
        with self.assertRaises(ValidationError) as refused:
            set_follow_up(self.project, on=datetime.date(2027, 3, 2), user=crew, by=self.paula)
        self.assertIn("follow_up_user", refused.exception.message_dict)
        vera.is_active = False
        vera.save()
        with self.assertRaises(ValidationError):
            set_follow_up(self.project, on=datetime.date(2027, 3, 2), user=vera, by=self.paula)

    def test_a_day_is_needed_and_the_note_is_short(self) -> None:
        with self.assertRaises(ValidationError) as refused:
            set_follow_up(self.project, on=None, by=self.paula)
        self.assertIn("follow_up_on", refused.exception.message_dict)
        with self.assertRaises(ValidationError) as refused:
            set_follow_up(self.project, on=datetime.date(2027, 3, 2), note="x" * 251, by=self.paula)
        self.assertIn("follow_up_note", refused.exception.message_dict)

    def test_in_every_status_a_closed_project_too(self) -> None:
        Project.objects.filter(pk=self.project.pk).update(status=ProjectStatus.CLOSED)
        self.project.refresh_from_db()
        set_follow_up(self.project, on=datetime.date(2027, 4, 1), note="Rechnung bezahlt?", by=self.paula)
        self.assertTrue(clear_follow_up(self.project))
        self.project.refresh_from_db()
        self.assertEqual(
            (self.project.follow_up_on, self.project.follow_up_note, self.project.follow_up_user), (None, "", None)
        )
        self.assertFalse(clear_follow_up(self.project))

    def test_filters(self) -> None:
        other = make_project("Hochzeit", status=ProjectStatus.OPTION)
        later = make_project("Messe", status=ProjectStatus.CONFIRMED)
        vera = make_user("vera", roles=("Projektleitung",))
        set_follow_up(self.project, on=datetime.date(2027, 3, 1), by=self.paula)
        set_follow_up(other, on=datetime.date(2027, 2, 20), by=vera)
        set_follow_up(later, on=datetime.date(2027, 3, 8), by=self.paula)
        projects = Project.objects.all()
        self.assertEqual(set(filter_projects(projects, "due", self.paula)), {self.project, other})
        self.assertEqual(set(filter_projects(projects, "mine", self.paula)), {self.project, later})
        self.assertEqual(set(filter_projects(projects, "any", self.paula)), {self.project, other, later})
        self.assertEqual(filter_projects(projects, "nonsense", self.paula).count(), projects.count())
        self.assertEqual(list(due_for(self.paula, projects)), [self.project])
        self.assertEqual(list(due_for(vera, projects)), [other])


class FollowUpNotificationTests(RentalarsTestCase):
    """PRJ-105: on its day the user hears of the follow-up – once, from the morning on, as the user wants."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.project = make_project("Firmenfeier", status=ProjectStatus.INQUIRY, manager=self.paula)
        set_follow_up(self.project, on=datetime.date(2027, 3, 3), note="Angebot nachfassen", by=self.paula)

    def run_at(self, when: datetime.datetime) -> int:
        set_clock(when)
        with self.captureOnCommitCallbacks(execute=True):
            return notify_due_follow_ups()

    def test_on_its_day_from_the_morning_on_and_once(self) -> None:
        django_mail.outbox.clear()
        self.assertEqual(self.run_at(moment(2, 23)), 0)
        self.assertEqual(self.run_at(moment(3, 5, 59)), 0)
        self.assertEqual(self.run_at(moment(3, 6)), 1)
        notification = Notification.objects.get(kind=Kind.FOLLOW_UP)
        self.assertEqual(notification.user, self.paula)
        self.assertEqual(notification.title, f"Wiedervorlage: {self.project}")
        self.assertIn("Angebot nachfassen", notification.body)
        self.assertIn("Mi 03.03.2027", notification.body)
        self.assertEqual(notification.project, self.project)
        # By e-mail as well unless switched off (UIX-005).
        self.assertEqual([message.to for message in django_mail.outbox], [["paula@example.de"]])
        self.assertEqual(self.run_at(moment(3, 9)), 0)
        self.assertEqual(Notification.objects.filter(kind=Kind.FOLLOW_UP).count(), 1)

    def test_a_missed_day_is_notified_at_night_too(self) -> None:
        self.assertEqual(self.run_at(moment(5, 1)), 1)

    def test_a_new_day_notifies_again_the_note_alone_does_not(self) -> None:
        self.run_at(moment(3, 7))
        set_follow_up(self.project, on=datetime.date(2027, 3, 3), note="Noch mal anrufen", by=self.paula)
        self.assertEqual(self.run_at(moment(3, 8)), 0)
        set_follow_up(self.project, on=datetime.date(2027, 3, 10), note="Noch mal anrufen", by=self.paula)
        self.assertEqual(self.run_at(moment(10, 6)), 1)

    def test_as_the_user_wants(self) -> None:
        Preference.objects.create(user=self.paula, kind=Kind.FOLLOW_UP, in_app=True, by_email=False)
        django_mail.outbox.clear()
        self.assertEqual(self.run_at(moment(3, 7)), 1)
        self.assertEqual(django_mail.outbox, [])
        self.assertTrue(Notification.objects.filter(kind=Kind.FOLLOW_UP, read_at=None).exists())

    def test_without_its_user_the_manager_hears_of_it(self) -> None:
        vera = make_user("vera", roles=("Projektleitung",))
        set_follow_up(self.project, on=datetime.date(2027, 3, 3), user=vera, by=self.paula)
        vera.is_active = False
        vera.save()
        self.assertEqual(self.run_at(moment(3, 7)), 1)
        self.assertEqual(Notification.objects.get(kind=Kind.FOLLOW_UP).user, self.paula)

    def test_the_minute_timer_notifies(self) -> None:
        set_clock(moment(3, 7))
        with self.captureOnCommitCallbacks(execute=True):
            call_command("run_jobs", stdout=io.StringIO())
        self.assertTrue(Notification.objects.filter(kind=Kind.FOLLOW_UP, user=self.paula).exists())
