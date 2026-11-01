# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "cases": further statuses of a service case (PRJ-112) and the automations for them (ADM-013)."""

from __future__ import annotations

import datetime

from django.core.exceptions import ValidationError

from rentalars.automations import engine
from rentalars.automations.models import Action, Automation, AutomationRun, Communication, Recipient, RunStatus, Trigger
from rentalars.chat.services import post_message
from rentalars.core.models import AuditLogEntry
from rentalars.mail.models import Direction, MailKind, ProjectMail
from rentalars.mail.services import reassign
from rentalars.notifications.models import Kind, Notification
from rentalars.projects import service_cases
from rentalars.projects.follow_up import clear_follow_up, notify_due_follow_ups, set_follow_up
from rentalars.projects.models import CaseStatus, CaseWaitingFor, Project
from rentalars.timetracking.services import is_open_service_case
from tests.helpers import RentalarsTestCase, at, make_customer, make_project, make_user, set_clock

DAY = datetime.date(2027, 3, 3)
TIME = datetime.time(14, 30)


def follow_up(user: object, on: datetime.date = DAY, at_time: datetime.time | None = None) -> dict[str, object]:
    return {"on": on, "at": at_time, "user": user, "note": "Rückruf abwarten"}


class CaseCase(RentalarsTestCase):
    """A service case of Paula, open, with a customer."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.case = service_cases.create_case(
            name="Spot flackert", customer=make_customer(), manager=self.paula, user=self.paula
        )

    def reload(self) -> Project:
        return Project.objects.get(pk=self.case.pk)


class StatusTests(CaseCase):
    """PRJ-112: waiting, waiting to close and backlog – only together with a follow-up."""

    def test_waiting_needs_a_follow_up_and_what_it_waits_for(self) -> None:
        """PRJ-112: "Warten auf Rückmeldung/Aktion/Materiallieferung" requires the follow-up (day; time optional)."""
        with self.assertRaises(ValidationError) as caught:
            service_cases.set_case_status(self.case, CaseStatus.WAITING, waiting_for="reply", by=self.paula)
        self.assertIn("follow_up_on", caught.exception.message_dict)
        with self.assertRaises(ValidationError) as caught:
            service_cases.set_case_status(self.case, CaseStatus.WAITING, follow_up=follow_up(self.paula))
        self.assertIn("case_waiting_for", caught.exception.message_dict)
        case = self.reload()
        self.assertEqual((case.case_status, case.follow_up_on), (CaseStatus.OPEN, None))
        service_cases.set_case_status(
            case, CaseStatus.WAITING, waiting_for=CaseWaitingFor.DELIVERY, follow_up=follow_up(None), by=self.paula
        )
        case = self.reload()
        self.assertEqual((case.case_status, case.case_waiting_for), ("waiting", "delivery"))
        self.assertEqual((case.follow_up_on, case.follow_up_at, case.follow_up_user), (DAY, None, self.paula))
        self.assertEqual(case.follow_up_note, "Rückruf abwarten")
        self.assertEqual(case.case_status_label, "wartet auf Materiallieferung")
        # Leaving "waiting" forgets what it waited for; the follow-up stays.
        service_cases.set_case_status(case, CaseStatus.IN_PROGRESS)
        case = self.reload()
        self.assertEqual((case.case_status, case.case_waiting_for, case.follow_up_on), ("in_progress", "", DAY))
        self.assertEqual(case.case_status_label, "in Arbeit")

    def test_waiting_to_close_needs_day_and_time(self) -> None:
        """PRJ-112: "Warten auf Schließen" requires the input of day and time (stored as the follow-up, PRJ-109)."""
        with self.assertRaises(ValidationError) as caught:
            service_cases.set_case_status(self.case, CaseStatus.CLOSING, follow_up=follow_up(self.paula))
        self.assertEqual(list(caught.exception.message_dict), ["follow_up_at"])
        service_cases.set_case_status(self.case, CaseStatus.CLOSING, follow_up=follow_up(self.paula, at_time=TIME))
        case = self.reload()
        self.assertEqual((case.case_status, case.follow_up_on, case.follow_up_at), ("closing", DAY, TIME))
        # Moving the follow-up of such a case keeps the time required.
        with self.assertRaises(ValidationError) as caught:
            set_follow_up(case, on=DAY, user=self.paula)
        self.assertIn("follow_up_at", caught.exception.message_dict)

    def test_a_refused_follow_up_keeps_the_old_status(self) -> None:
        """PRJ-112: status and follow-up are saved together or not at all."""
        crew = make_user("kai", roles=("Crew",))  # may not open the case
        with self.assertRaises(ValidationError):
            service_cases.set_case_status(self.case, CaseStatus.BACKLOG, follow_up=follow_up(crew))
        case = self.reload()
        self.assertEqual((case.case_status, case.follow_up_on), (CaseStatus.OPEN, None))

    def test_the_change_log_notes_status_and_reason(self) -> None:
        """PRJ-112: the history of the case shows the new status and what it waits for."""
        service_cases.set_case_status(
            self.case, CaseStatus.WAITING, waiting_for="reply", follow_up=follow_up(self.paula), by=self.paula
        )
        entry = (
            AuditLogEntry.objects.filter(content_type__model="project", object_id=str(self.case.pk))
            .filter(changes__has_key="case_status")
            .latest("pk")
        )
        self.assertEqual(entry.changes["case_status"], ["open", "waiting"])
        self.assertEqual(entry.changes["case_waiting_for"], ["", "reply"])

    def test_done_with_the_follow_up_opens_a_waiting_case_again(self) -> None:
        """PRJ-112: without its follow-up a case cannot wait – "done" on the follow-up opens it again."""
        service_cases.set_case_status(self.case, CaseStatus.BACKLOG, follow_up=follow_up(self.paula))
        case = self.reload()
        self.assertTrue(clear_follow_up(case))
        case = self.reload()
        self.assertEqual((case.case_status, case.follow_up_on), (CaseStatus.OPEN, None))

    def test_times_on_every_case_not_done(self) -> None:
        """PRJ-112, ZEI-024: times can be recorded on a waiting case or one in the backlog – not on a done one."""
        service_cases.set_case_status(self.case, CaseStatus.BACKLOG, follow_up=follow_up(self.paula))
        self.assertTrue(is_open_service_case(self.reload()))
        service_cases.set_case_status(self.case, CaseStatus.DONE)
        self.assertFalse(is_open_service_case(self.reload()))


class DashboardTests(CaseCase):
    """PRJ-112: a case in the backlog is not on the dashboards until its follow-up is due – only in the list."""

    def setUp(self) -> None:
        super().setUp()
        service_cases.set_case_status(self.case, CaseStatus.BACKLOG, follow_up=follow_up(self.paula))
        self.other = service_cases.create_case(name="Kabel", customer=self.case.customer, manager=self.paula)
        service_cases.set_case_status(
            self.other, CaseStatus.CLOSING, follow_up=follow_up(self.paula, at_time=TIME), by=self.paula
        )

    def test_off_the_dashboards_until_due(self) -> None:
        """PRJ-112: a case in the backlog is not shown on the dashboards until due, only in the list of service cases."""
        hidden = Project.objects.filter(service_cases.off_dashboards())
        self.assertEqual(list(hidden), [self.case])
        # The list of service cases shows every case not done – the backlog too.
        listed = service_cases.case_list(Project.objects.all())
        self.assertEqual({case.pk for case in listed}, {self.case.pk, self.other.pk})
        # Once the follow-up is due, the case is back on the dashboards.
        set_clock(at(3, 9))
        self.assertFalse(Project.objects.filter(service_cases.off_dashboards()).exists())

    def test_start_page_my_area_and_planning(self) -> None:
        """PRJ-112: start page ("Meine Servicefälle"), Mein Bereich → Servicefälle, Planung → Wiedervorlagen."""
        self.client.force_login(self.paula)
        home = self.client.get("/")
        self.assertEqual([case.pk for case in home.context["own_cases"]], [self.other.pk])
        planning = self.client.get("/schedule/follow-ups/")
        self.assertNotContains(planning, "Spot flackert")
        self.assertContains(planning, "Kabel")
        planning = self.client.get("/schedule/follow-ups/?backlog=1")
        self.assertContains(planning, "Spot flackert")
        listed = self.client.get("/projects/service-cases/")
        self.assertContains(listed, "Spot flackert")
        self.assertContains(listed, ">zurückgestellt<")
        set_clock(at(3, 9))
        self.client.force_login(self.paula)  # again: the clock moved past the idle time of the session
        home = self.client.get("/")
        self.assertIn(self.case.pk, [case.pk for case in home.context["own_cases"]])

    def test_no_notification_before_the_follow_up_is_due(self) -> None:
        """PRJ-112: the follow-up of a case in the backlog notifies only when it is due."""
        notify_due_follow_ups()
        self.assertFalse(Notification.objects.filter(kind=Kind.FOLLOW_UP).exists())
        set_clock(at(3, 15))
        Automation.objects.update(is_active=False)
        notify_due_follow_ups()
        self.assertEqual(Notification.objects.filter(kind=Kind.FOLLOW_UP).count(), 2)


class DefaultRuleTests(CaseCase):
    """ADM-013, PRJ-112: the three default rules – close when due, open again on communication, backlog open."""

    def close_at(self, case: Project, day: datetime.date = DAY, time: datetime.time = TIME) -> Project:
        service_cases.set_case_status(case, CaseStatus.CLOSING, follow_up=follow_up(self.paula, day, time))
        return self.reload()

    def test_the_rules_are_there_and_active(self) -> None:
        """ADM-013: the default rules are entered as automations – created by the migration, active."""
        # Adds the rule of the defect reports (tests/unit/test_085_defects.py).
        rules = Automation.objects.exclude(trigger=Trigger.DEFECT).order_by("pk")
        self.assertEqual(
            [(rule.trigger, rule.status, rule.action, rule.new_case_status, rule.is_active) for rule in rules],
            [
                ("case_follow_up", "closing", "case_status", "done", True),
                ("case_communication", "closing", "case_status", "open", True),
                ("case_follow_up", "backlog", "case_status", "open", True),
            ],
        )
        self.assertEqual(rules[0].name, "Wartet auf Schließen: zum Termin schließen")
        for rule in rules:
            self.assertEqual(rule.problems(), {})

    def test_closed_at_the_time_set(self) -> None:
        """PRJ-112: a case waiting to close is closed at the time set if nothing changes in it until then."""
        self.close_at(self.case)
        set_clock(at(3, 14, 29))
        with self.captureOnCommitCallbacks(execute=True):
            notify_due_follow_ups()
        self.assertEqual(self.reload().case_status, CaseStatus.CLOSING)
        set_clock(at(3, 14, 30))
        with self.captureOnCommitCallbacks(execute=True):
            notify_due_follow_ups()
            notify_due_follow_ups()
        case = self.reload()
        self.assertEqual((case.case_status, case.follow_up_on), (CaseStatus.DONE, None))
        run = AutomationRun.objects.get(trigger=Trigger.CASE_FOLLOW_UP)
        self.assertEqual(run.status, RunStatus.DONE)
        self.assertEqual(run.detail, f"Status von {case.number}: wartet auf Schließen → erledigt")
        entry = AuditLogEntry.objects.filter(object_id=str(case.pk), changes__has_key="case_status").latest("pk")
        self.assertEqual(entry.actor_label, "Automation „Wartet auf Schließen: zum Termin schließen“")

    def test_communication_opens_it_again(self) -> None:
        """PRJ-112: a change reopens it – a mail in, a mail out or a chat message."""
        # EML-055: open, as mails of a service case come in – the field's own default is the lock,
        # and the subject of a mail with lock stays out of the run (tests/unit/test_092_review_mail.py).
        for number, make in enumerate(
            (
                lambda case: ProjectMail.objects.create(
                    project=case,
                    message_key="k-in",
                    message_id="<in@x>",
                    subject="Re: Spot",
                    sender_address="a@b.example",
                    locked=False,
                ),
                lambda case: ProjectMail.objects.create(
                    project=case, message_key="k-out", message_id="<out@x>", direction=Direction.OUTGOING
                ),
                lambda case: post_message(case, user=self.paula, text="Lampe ist bestellt"),
            )
        ):
            case = self.close_at(self.reload())
            with self.captureOnCommitCallbacks(execute=True):
                make(case)
            case = self.reload()
            self.assertEqual(case.case_status, CaseStatus.OPEN, number)
            # The follow-up stays – a reminder to look at the case again.
            self.assertEqual((case.follow_up_on, case.follow_up_at), (DAY, TIME))
        runs = AutomationRun.objects.filter(trigger=Trigger.CASE_COMMUNICATION).order_by("pk")
        self.assertEqual([run.status for run in runs], [RunStatus.DONE] * 3)
        self.assertIn("Mail von a@b.example: Re: Spot", runs[0].event)
        self.assertIn("Chatnachricht von", runs[2].event)

    def test_not_communication(self) -> None:
        """PRJ-112: automatic replies, delivery failures and an open case are left alone; a moved mail counts."""
        case = self.close_at(self.case)
        project = make_project("Messe")
        with self.captureOnCommitCallbacks(execute=True):
            ProjectMail.objects.create(project=case, message_key="k1", message_id="<1@x>", kind=MailKind.AUTO_REPLY)
            mail = ProjectMail.objects.create(project=project, message_key="k2", message_id="<2@x>", subject="Ware")
        self.assertEqual(self.reload().case_status, CaseStatus.CLOSING)
        with self.captureOnCommitCallbacks(execute=True):
            reassign(ProjectMail.objects.get(pk=mail.pk), case, user=self.paula)
        self.assertEqual(self.reload().case_status, CaseStatus.OPEN)
        # In "open" the rule's condition does not hold: nothing is recorded.
        with self.captureOnCommitCallbacks(execute=True):
            post_message(self.reload(), user=self.paula, text="Noch da?")
        self.assertEqual(AutomationRun.objects.filter(trigger=Trigger.CASE_COMMUNICATION).count(), 1)

    def test_what_a_rule_does_is_no_communication(self) -> None:
        """ADM-013 loop protection: a chat message written while a rule is carried out starts no rule."""
        case = self.close_at(self.case)
        token = engine._RUNNING.set(True)
        try:
            self.assertEqual(engine.case_communication(case, kind=Communication.CHAT, key="x", who="x", text="x"), [])
        finally:
            engine._RUNNING.reset(token)
        self.assertEqual(len(engine.case_communication(case, kind=Communication.CHAT, key="x", who="x", text="x")), 1)

    def test_backlog_open_again_when_due(self) -> None:
        """PRJ-112: a case in the backlog is set to open when its follow-up date is reached; the follow-up stays due."""
        service_cases.set_case_status(self.case, CaseStatus.BACKLOG, follow_up=follow_up(self.paula))
        set_clock(at(3, 8))
        with self.captureOnCommitCallbacks(execute=True):
            notify_due_follow_ups()
        case = self.reload()
        self.assertEqual((case.case_status, case.follow_up_on), (CaseStatus.OPEN, DAY))
        # Reopened, it is an ordinary due follow-up: the reminder goes out (it is back on the dashboards).
        self.assertTrue(Notification.objects.filter(kind=Kind.FOLLOW_UP, user=self.paula).exists())

    def test_changed_in_the_meantime_is_left_out(self) -> None:
        """ADM-013: the run checks the case again – another status, or a moved follow-up, leave it alone."""
        self.close_at(self.case)
        set_clock(at(3, 15))
        notify_due_follow_ups()  # recorded, not carried out yet (no commit in the test)
        service_cases.set_case_status(self.reload(), CaseStatus.IN_PROGRESS)
        engine.run_pending()
        run = AutomationRun.objects.get(trigger=Trigger.CASE_FOLLOW_UP)
        self.assertEqual(run.status, RunStatus.SKIPPED)
        self.assertEqual(run.detail, "Der Servicefall ist jetzt „in Arbeit“, nicht mehr „wartet auf Schließen“.")
        self.assertEqual(self.reload().case_status, CaseStatus.IN_PROGRESS)

    def test_switched_off_does_nothing(self) -> None:
        """ADM-013: the rules can be switched off – the follow-up is then notified as usual (PRJ-112)."""
        Automation.objects.update(is_active=False)
        self.close_at(self.case)
        set_clock(at(3, 15))
        with self.captureOnCommitCallbacks(execute=True):
            notify_due_follow_ups()
        self.assertEqual(self.reload().case_status, CaseStatus.CLOSING)
        self.assertFalse(AutomationRun.objects.exists())
        self.assertTrue(Notification.objects.filter(kind=Kind.FOLLOW_UP, user=self.paula).exists())

    def test_no_reminder_when_the_rule_closes_the_case(self) -> None:
        """PRJ-112: while the rule closes a case waiting to close, its due follow-up sends no reminder besides."""
        self.close_at(self.case)
        set_clock(at(3, 15))
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(notify_due_follow_ups(), 1)
        self.assertEqual(self.reload().case_status, CaseStatus.DONE)
        self.assertFalse(Notification.objects.filter(kind=Kind.FOLLOW_UP).exists())

    def test_the_rules_run_with_nobody_to_notify(self) -> None:
        """PRJ-112: the trigger does not depend on the notification – no user, no responsible person."""
        other = service_cases.create_case(name="Kabel", customer=self.case.customer)
        service_cases.set_case_status(other, CaseStatus.BACKLOG, follow_up=follow_up(self.paula))
        self.close_at(self.case)
        # The user of both follow-ups is gone (``SET_NULL``); neither case has a responsible person.
        Project.objects.filter(pk__in=[self.case.pk, other.pk]).update(follow_up_user=None, manager=None)
        set_clock(at(3, 15))
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(notify_due_follow_ups(), 2)
            self.assertEqual(notify_due_follow_ups(), 0)  # once per follow-up
        self.assertEqual(self.reload().case_status, CaseStatus.DONE)
        self.assertEqual(Project.objects.get(pk=other.pk).case_status, CaseStatus.OPEN)
        self.assertFalse(Notification.objects.filter(kind=Kind.FOLLOW_UP).exists())
        self.assertEqual(AutomationRun.objects.filter(trigger=Trigger.CASE_FOLLOW_UP, status=RunStatus.DONE).count(), 2)


class RuleTests(RentalarsTestCase):
    """ADM-013: triggers, conditions and the action of the service cases in the rule editor's checks."""

    def test_problems_and_normalise(self) -> None:
        rule = Automation(name="x", trigger=Trigger.CASE_COMMUNICATION, action=Action.CASE_STATUS, status="closing")
        rule.normalise()
        self.assertIn("new_case_status", rule.problems())
        rule.new_case_status = "waiting"  # needs a follow-up a rule cannot choose
        self.assertIn("new_case_status", rule.problems())
        rule.new_case_status = "closing"
        self.assertIn("new_case_status", rule.problems())
        rule.new_case_status = "open"
        rule.communication = Communication.MAIL_IN
        self.assertEqual(rule.problems(), {})
        rule.status = "confirmed"  # a status of a project
        self.assertIn("status", rule.problems())
        # Another trigger drops the condition of the case; another action the new status.
        rule.trigger, rule.action, rule.recipient, rule.status = Trigger.FOLLOW_UP, Action.NOTIFY, Recipient.MANAGER, ""
        rule.normalise()
        self.assertEqual((rule.communication, rule.new_case_status), ("", ""))
        self.assertEqual(rule.problems(), {})
        rule.action = Action.CASE_STATUS
        self.assertIn("action", rule.problems())

    def test_only_one_kind_of_communication(self) -> None:
        """ADM-013: the condition "which communication" – a mail received only."""
        manager = make_user("paula", roles=("Projektleitung",))
        case = service_cases.create_case(name="Spot", customer=make_customer(), manager=manager)
        Automation.objects.all().delete()
        Automation.objects.create(
            name="Mail",
            trigger=Trigger.CASE_COMMUNICATION,
            communication=Communication.MAIL_IN,
            action=Action.NOTIFY,
            recipient=Recipient.MANAGER,
            subject="{projekt}: {kommunikation} ({status})",
        )
        with self.captureOnCommitCallbacks(execute=True):
            post_message(case, user=manager, text="intern")
            # EML-055: open, as mails of a service case come in; one with lock is named without subject.
            ProjectMail.objects.create(
                project=case,
                message_key="m",
                message_id="<m@x>",
                subject="Hilfe",
                sender_address="k@x.example",
                locked=False,
            )
        notification = Notification.objects.get(kind=Kind.AUTOMATION)
        self.assertEqual(notification.title, f"{case.number} Spot: Mail von k@x.example: Hilfe (offen)")
        # the notification opens the Überblick – adapted.
        self.assertEqual(notification.url, f"/projects/{case.number}/overview/")


class LanguageTests(RentalarsTestCase):
    """UIX-029, PRJ-112: the notifications of the service cases in each recipient's own language."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))  # German, the installation's language
        self.fred = make_user("fred", roles=("Projektleitung",))
        self.fred.language = "en"
        self.fred.save()

    def titles(self, kind: str) -> dict[str, str]:
        return {row.user.username: row.title for row in Notification.objects.filter(kind=kind).select_related("user")}

    def test_responsible_and_participant(self) -> None:
        """PRJ-090, PRJ-108: "is yours now" and "you take part" – each in his language."""
        from rentalars.personnel.models import JobFunction
        from tests.helpers import make_person

        case = service_cases.create_case(name="Spot", customer=make_customer(), manager=self.fred, user=self.paula)
        self.assertEqual(self.titles(Kind.PROJECT_CHANGE), {"fred": f"Service case {case.number} Spot is yours now"})
        light = JobFunction.objects.create(name="Licht")
        for user in (self.paula, self.fred):
            service_cases.add_participant(
                case, make_person(user.username, user=user), job_function=light, note="Leiter"
            )
        titles = self.titles(Kind.SERVICE_CASE)
        self.assertEqual(titles["fred"], f"You take part in service case {case.number} Spot")
        self.assertEqual(titles["paula"], f"Du bist am Servicefall {case.number} Spot beteiligt")
        bodies = {row.user.username: row.body for row in Notification.objects.filter(kind=Kind.SERVICE_CASE)}
        self.assertEqual(bodies, {"fred": "As: Licht\nLeiter", "paula": "Als: Licht\nLeiter"})

    def test_automation_without_a_title_of_its_own(self) -> None:
        """ADM-013, PRJ-112: a notification of a rule of the service cases without a title: in each language."""
        case = service_cases.create_case(name="Spot", customer=make_customer(), manager=self.paula)
        service_cases.set_case_status(
            case, CaseStatus.WAITING, waiting_for="reply", follow_up=follow_up(self.paula), by=self.paula
        )
        Automation.objects.all().delete()
        for user in (self.paula, self.fred):
            Automation.objects.create(
                name=user.username,
                trigger=Trigger.CASE_COMMUNICATION,
                action=Action.NOTIFY,
                recipient=Recipient.USER,
                user=user,
            )
        with self.captureOnCommitCallbacks(execute=True):
            # EML-055: open, as mails of a service case come in; one with lock is named without subject.
            ProjectMail.objects.create(
                project=case,
                message_key="m",
                message_id="<m@x>",
                subject="Hilfe",
                sender_address="k@x.example",
                locked=False,
            )
        self.assertEqual(
            self.titles(Kind.AUTOMATION),
            {
                "paula": f"{case.number} Spot (wartet auf Rückmeldung): Mail von k@x.example: Hilfe",
                "fred": f"{case.number} Spot (Waiting for a reply): Mail from k@x.example: Hilfe",
            },
        )
        # The list of runs keeps the installation's language.
        self.assertEqual(
            AutomationRun.objects.first().event,
            f"{case.number} Spot (wartet auf Rückmeldung): Mail von k@x.example: Hilfe",
        )
        # The follow-up's day in the reader's language, too.
        text = engine.case_event_text(
            Trigger.CASE_FOLLOW_UP,
            {"case": "1 Spot", "case_status": "closing", "follow_up_on": "2027-03-03", "follow_up_at": "14:30"},
        )
        from rentalars.core.i18n import written_for

        self.assertIn("wartet auf Schließen", written_for(text, self.paula))
        self.assertIn("Waiting to close", written_for(text, self.fred))
