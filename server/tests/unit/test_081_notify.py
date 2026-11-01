# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "notify": UIX-039, PRJ-109, VFG-034.

* UIX-039: every kind of notification has a category (Projekt, Personal,
  Material, System); the settings are sorted by it; the choice "In der App"
  is stored per user and kind and given to every notification.
* PRJ-109: a follow-up may have a time; it is due – notified, marked,
  counted, handed to the automations – from that time on.
* VFG-034: the table of every follow-up (the data side; the page is tested in
  ``tests/ui/test_081_notify_pages.py``).
"""

from __future__ import annotations

import datetime

from django.core import mail as django_mail

from rentalars.automations.models import Action, Automation, AutomationRun, Recipient, Trigger
from rentalars.notifications import services
from rentalars.notifications.categories import (
    CATEGORIES,
    CATEGORY_OF,
    Category,
    category_of,
    grouped,
    kinds_in,
    ordered_kinds,
)
from rentalars.notifications.models import COMPANION_BY_DEFAULT, Kind, Notification, Preference
from rentalars.projects.follow_up import (
    clear_follow_up,
    due_for,
    filter_projects,
    notify_due_follow_ups,
    set_follow_up,
    when_text,
)
from rentalars.projects.models import Project, ProjectStatus
from tests.helpers import BERLIN, RentalarsTestCase, make_project, make_user, set_clock


def moment(day: int, hour: int, minute: int = 0) -> datetime.datetime:
    """A moment in March 2027, Berlin time."""
    return datetime.datetime(2027, 3, day, hour, minute, tzinfo=BERLIN)


# --- UIX-039 ----------------------------------------------------------------------------------------------


class CategoryTests(RentalarsTestCase):
    """UIX-039: the category of each kind, and the order of the settings."""

    def test_every_kind_has_a_category_of_its_own(self) -> None:
        """A new kind needs an entry in ``notifications.categories`` – the fallback is only a safety net."""
        self.assertEqual(set(CATEGORY_OF), set(Kind.values))
        self.assertEqual(len(ordered_kinds()), len(Kind.values))

    def test_the_categories_the_user_asked_for(self) -> None:
        self.assertEqual(category_of(Kind.MAIL_PROBLEM), Category.SYSTEM)
        self.assertEqual(category_of(Kind.SYSTEM_ERROR), Category.SYSTEM)
        self.assertEqual(category_of(Kind.CALENDAR_PROBLEM), Category.SYSTEM)
        self.assertEqual(category_of(Kind.JOB_FINISHED), Category.SYSTEM)
        for kind in (
            Kind.DEPLOYMENT_REQUEST,
            Kind.DEPLOYMENT_ANSWER,
            Kind.NEW_MAIL,
            Kind.CHAT_MENTION,
            Kind.FOLLOW_UP,
            Kind.PROJECT_CHANGE,
            Kind.SHORTAGE,
            Kind.AUTOMATION,
        ):
            self.assertEqual(category_of(kind), Category.PROJECT, kind)
        self.assertEqual(category_of(Kind.DEFECT), Category.MATERIAL)
        self.assertEqual(category_of(Kind.LOW_STOCK), Category.MATERIAL)
        self.assertEqual(category_of(Kind.EXPENSE), Category.PERSONNEL)
        self.assertEqual(category_of(Kind.QUALIFICATION_EXPIRY), Category.PERSONNEL)
        self.assertEqual(category_of("something_new"), Category.PROJECT)

    def test_settings_sorted_and_grouped_by_category(self) -> None:
        user = make_user("paula")
        settings = services.preferences_of(user)
        order = [CATEGORIES.index(item["category"]) for item in settings]
        self.assertEqual(order, sorted(order))
        self.assertEqual(settings[0]["kind"], Kind.DEPLOYMENT_REQUEST)
        self.assertEqual(settings[0]["category_label"], "Projekt")
        groups = grouped(settings)
        self.assertEqual([group["label"] for group in groups], ["Projekt", "Personal", "Material", "System"])
        self.assertEqual(sum(len(group["items"]) for group in groups), len(Kind.values))
        self.assertEqual(set(kinds_in(Category.MATERIAL)), {Kind.DEFECT, Kind.LOW_STOCK, Kind.INSPECTION_DUE})


class CompanionChoiceTests(RentalarsTestCase):
    """UIX-039: "In der App" – stored per user and kind, given to every notification."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula")

    def test_defaults_on_for_what_concerns_the_person_directly(self) -> None:
        # Also the notice to people added to a service case (PRJ-108) and the
        # change of one's own deployment (PRJ-118: planned firmly, new times or meeting point, taken off).
        self.assertEqual(
            COMPANION_BY_DEFAULT,
            {Kind.DEPLOYMENT_REQUEST, Kind.CHAT_MENTION, Kind.FOLLOW_UP, Kind.SERVICE_CASE, Kind.DEPLOYMENT_CHANGE},
        )
        choice = {item["kind"]: item["companion"] for item in services.preferences_of(self.paula)}
        self.assertTrue(choice[Kind.DEPLOYMENT_REQUEST])
        self.assertTrue(choice[Kind.FOLLOW_UP])
        self.assertFalse(choice[Kind.PROJECT_CHANGE])
        self.assertFalse(choice[Kind.SYSTEM_ERROR])

    def test_each_notification_carries_the_choice(self) -> None:
        services.notify([self.paula], Kind.FOLLOW_UP, "Wiedervorlage")
        services.notify([self.paula], Kind.PROJECT_CHANGE, "Geändert")
        self.assertTrue(Notification.objects.get(kind=Kind.FOLLOW_UP).companion)
        self.assertFalse(Notification.objects.get(kind=Kind.PROJECT_CHANGE).companion)

    def test_only_in_the_app_is_kept_as_read_in_rentalars(self) -> None:
        services.set_preference(self.paula, Kind.FOLLOW_UP, in_app=False, by_email=False, companion=True)
        django_mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            created = services.notify([self.paula], Kind.FOLLOW_UP, "Wiedervorlage")
        self.assertEqual(created, [])
        notification = Notification.objects.get(kind=Kind.FOLLOW_UP)
        self.assertTrue(notification.companion)
        self.assertIsNotNone(notification.read_at)
        self.assertEqual(django_mail.outbox, [])
        self.assertEqual(services.unread_count(self.paula), 0)

    def test_all_three_off_makes_none(self) -> None:
        services.set_preference(self.paula, Kind.FOLLOW_UP, in_app=False, by_email=False, companion=False)
        services.notify([self.paula], Kind.FOLLOW_UP, "Wiedervorlage")
        self.assertFalse(Notification.objects.exists())

    def test_storing_without_the_app_keeps_its_choice(self) -> None:
        """A client sends no ``companion``; what was chosen stays."""
        services.set_preference(self.paula, Kind.PROJECT_CHANGE, in_app=True, by_email=False, companion=True)
        services.set_preference(self.paula, Kind.PROJECT_CHANGE, in_app=False, by_email=True)
        stored = Preference.objects.get(user=self.paula, kind=Kind.PROJECT_CHANGE)
        self.assertEqual((stored.in_app, stored.by_email, stored.companion), (False, True, True))
        services.set_preference(self.paula, Kind.CHAT_MENTION, in_app=True, by_email=True)
        self.assertTrue(Preference.objects.get(user=self.paula, kind=Kind.CHAT_MENTION).companion)
        # The answer for (in the application, by e-mail) is unchanged.
        self.assertEqual(services.preference(self.paula, Kind.PROJECT_CHANGE), (False, True))


# --- PRJ-109 ----------------------------------------------------------------------------------------------


class FollowUpTimeTests(RentalarsTestCase):
    """PRJ-109: the time of a follow-up – set, shown, due from that time on."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.project = make_project("Firmenfeier", status=ProjectStatus.INQUIRY, manager=self.paula)

    def test_set_with_a_time_and_cleared(self) -> None:
        set_follow_up(
            self.project, on=datetime.date(2027, 3, 3), at=datetime.time(14, 30, 12), note="Anrufen", by=self.paula
        )
        self.project.refresh_from_db()
        self.assertEqual(self.project.follow_up_at, datetime.time(14, 30))
        self.assertEqual(when_text(self.project), "Mi 03.03.2027 um 14:30")
        self.assertTrue(clear_follow_up(self.project))
        self.project.refresh_from_db()
        self.assertIsNone(self.project.follow_up_at)
        self.assertEqual(when_text(self.project), "")

    def test_without_a_time_the_day_counts_as_before(self) -> None:
        set_follow_up(self.project, on=datetime.date(2027, 3, 1), by=self.paula)
        self.assertTrue(self.project.follow_up_is_due)
        self.assertEqual(when_text(self.project), "Mo 01.03.2027")

    def test_due_from_its_time_on(self) -> None:
        """The clock of the tests stands at 1 March 2027, 08:00."""
        set_follow_up(self.project, on=datetime.date(2027, 3, 1), at=datetime.time(14, 30), by=self.paula)
        projects = Project.objects.all()
        self.assertFalse(self.project.follow_up_is_due)
        self.assertEqual(list(filter_projects(projects, "due", self.paula)), [])
        self.assertEqual(list(due_for(self.paula, projects)), [])
        set_clock(moment(1, 14, 30))
        self.assertTrue(self.project.follow_up_is_due)
        self.assertEqual(list(filter_projects(projects, "due", self.paula)), [self.project])
        self.assertEqual(list(due_for(self.paula, projects)), [self.project])
        # A time on a day that is over: due anyway.
        set_follow_up(self.project, on=datetime.date(2027, 2, 27), at=datetime.time(23, 0), by=self.paula)
        set_clock(moment(1, 1))
        self.assertTrue(self.project.follow_up_is_due)

    def test_start_page_order_by_day_and_time(self) -> None:
        other = make_project("Hochzeit", status=ProjectStatus.OPTION, manager=self.paula)
        third = make_project("Messe", status=ProjectStatus.OPTION, manager=self.paula)
        set_follow_up(self.project, on=datetime.date(2027, 3, 1), at=datetime.time(7, 30), by=self.paula)
        set_follow_up(other, on=datetime.date(2027, 3, 1), by=self.paula)
        set_follow_up(third, on=datetime.date(2027, 2, 28), at=datetime.time(18, 0), by=self.paula)
        self.assertEqual(list(due_for(self.paula, Project.objects.all())), [third, other, self.project])

    def test_the_change_log_names_the_time(self) -> None:
        from rentalars.core.models import AuditLogEntry

        set_follow_up(self.project, on=datetime.date(2027, 3, 3), at=datetime.time(9, 15), by=self.paula)
        entry = AuditLogEntry.objects.filter(object_id=str(self.project.pk), action="updated").latest("pk")
        self.assertEqual(entry.changes["follow_up_at"][0], None)
        self.assertTrue(str(entry.changes["follow_up_at"][1]).startswith("09:15"))


class FollowUpTimeNotificationTests(RentalarsTestCase):
    """PRJ-109: the reminder – notification and automation – from the time on, once."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.project = make_project("Firmenfeier", status=ProjectStatus.INQUIRY, manager=self.paula)
        set_follow_up(
            self.project, on=datetime.date(2027, 3, 3), at=datetime.time(14, 30), note="Anrufen", by=self.paula
        )

    def run_at(self, when: datetime.datetime) -> int:
        set_clock(when)
        with self.captureOnCommitCallbacks(execute=True):
            return notify_due_follow_ups()

    def test_from_the_time_on_and_once(self) -> None:
        self.assertEqual(self.run_at(moment(3, 6)), 0)
        self.assertEqual(self.run_at(moment(3, 14, 29)), 0)
        self.assertEqual(self.run_at(moment(3, 14, 30)), 1)
        notification = Notification.objects.get(kind=Kind.FOLLOW_UP)
        self.assertIn("Mi 03.03.2027 um 14:30", notification.body)
        self.assertTrue(notification.companion)
        self.assertEqual(self.run_at(moment(3, 15)), 0)

    def test_an_early_time_before_the_morning(self) -> None:
        set_follow_up(self.project, on=datetime.date(2027, 3, 3), at=datetime.time(5, 0), by=self.paula)
        self.assertEqual(self.run_at(moment(3, 4, 59)), 0)
        self.assertEqual(self.run_at(moment(3, 5)), 1)

    def test_a_new_time_notifies_again(self) -> None:
        self.run_at(moment(3, 15))
        set_follow_up(
            self.project, on=datetime.date(2027, 3, 3), at=datetime.time(17, 0), note="Anrufen", by=self.paula
        )
        self.assertEqual(self.run_at(moment(3, 16)), 0)
        self.assertEqual(self.run_at(moment(3, 17)), 1)
        # Taking the time away: due in the morning of the day – now.
        set_follow_up(self.project, on=datetime.date(2027, 3, 3), note="Anrufen", by=self.paula)
        self.assertEqual(self.run_at(moment(3, 17, 1)), 1)

    def test_the_automation_fires_from_the_time_on(self) -> None:
        rule = Automation.objects.create(
            name="Wiedervorlage als offener Punkt",
            trigger=Trigger.FOLLOW_UP,
            action=Action.NOTIFY,
            recipient=Recipient.FOLLOW_UP_USER,
            text="Wiedervorlage {wiedervorlage}: {notiz}",
        )
        self.run_at(moment(3, 12))
        self.assertFalse(AutomationRun.objects.filter(automation=rule).exists())
        self.run_at(moment(3, 14, 30))
        run = AutomationRun.objects.get(automation=rule)
        self.assertTrue(run.event_key.endswith(":1430"))
        self.assertIn("Mi 03.03.2027 um 14:30", run.event)
