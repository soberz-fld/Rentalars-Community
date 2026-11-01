# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages, area "notify": UIX-039, PRJ-109, VFG-034.

* UIX-039: Benachrichtigungen → Einstellungen grouped by category with the
  column "In der App"; the list of notifications filters by category.
* PRJ-109: the time of a follow-up in its dialog, the head of the project,
  the start page and the list of projects.
* VFG-034: Planung → Wiedervorlagen – the table, its filters, CSV, grouping,
  "Verschieben" and "Erledigt", who sees what.
"""

from __future__ import annotations

import datetime

from django.urls import reverse

from rentalars.notifications import services
from rentalars.notifications.models import Kind, Notification, Preference
from rentalars.projects import service_cases
from rentalars.projects.follow_up import set_follow_up
from rentalars.projects.models import ProjectStatus
from tests.helpers import make_customer, make_project, make_user, set_clock
from tests.ui.base import UiTestCase, form_data

PREFERENCES = "/account/notifications/"
NOTIFICATIONS = "/notifications/"
FOLLOW_UPS = "/schedule/follow-ups/"


# --- UIX-039 ----------------------------------------------------------------------------------------------


class NotificationSettingsPageTests(UiTestCase):
    """UIX-039: the settings grouped by category, with the third column "In der App"."""

    def test_grouped_with_the_app_column(self) -> None:
        text = self.assert_ok(self.client.get(PREFERENCES))
        self.assertIn('<th scope="col">In Rentalars</th>', text)
        self.assertIn('<th scope="col">Per E-Mail</th>', text)
        self.assertIn('<th scope="col">In der App</th>', text)
        headings = [
            text.index(f'scope="rowgroup" id="category-{name}"')
            for name in ("project", "personnel", "material", "system")
        ]
        self.assertEqual(headings, sorted(headings))
        # Within "Projekt" the deployment request first; the mail problem under "System".
        self.assertLess(text.index('name="deployment_request-app"'), text.index('name="project_change-app"'))
        self.assertGreater(text.index('name="mail_problem-app"'), headings[3])
        self.assertIn('name="follow_up-companion" value="1" checked', text)
        self.assertNotIn('name="system_error-companion" value="1" checked', text)
        self.assertIn("Rentalars Companion", text)

    def test_saved(self) -> None:
        data = form_data(self.client.get(PREFERENCES), "follow_up-app")
        data.pop("follow_up-companion", None)
        data["project_change-companion"] = "1"
        response = self.client.post(PREFERENCES, data, follow=True)
        self.assertIn("Benachrichtigungseinstellungen gespeichert.", self.messages_of(response))
        stored = dict(Preference.objects.filter(user=self.admin_user).values_list("kind", "companion"))
        self.assertFalse(stored[Kind.FOLLOW_UP])
        self.assertTrue(stored[Kind.PROJECT_CHANGE])
        self.assertTrue(stored[Kind.DEPLOYMENT_REQUEST])


class NotificationListPageTests(UiTestCase):
    """UIX-039: the list of notifications names the category and filters by it."""

    def setUp(self) -> None:
        super().setUp()
        services.notify([self.admin_user], Kind.FOLLOW_UP, "Wiedervorlage: Firmenfeier")
        services.notify([self.admin_user], Kind.MAIL_PROBLEM, "Postfach nicht erreichbar")
        Notification.objects.filter(kind=Kind.MAIL_PROBLEM).update(read_at=self.now())

    def now(self) -> datetime.datetime:
        from django.utils import timezone

        return timezone.now()

    def test_filter_by_category(self) -> None:
        text = self.assert_ok(self.client.get(NOTIFICATIONS))
        self.assertIn("Wiedervorlage: Firmenfeier", text)
        self.assertIn("Postfach nicht erreichbar", text)
        self.assertIn('<td data-label="Kategorie">Projekt</td>', text)
        self.assertIn('<td data-label="Kategorie">System</td>', text)
        self.assertIn('<option value="system">System</option>', text)
        text = self.assert_ok(self.client.get(f"{NOTIFICATIONS}?category=system"))
        self.assertNotIn("Wiedervorlage: Firmenfeier", text)
        self.assertIn("Postfach nicht erreichbar", text)
        self.assertIn('<option value="system" selected>System</option>', text)
        # The tabs keep the category; "Ungelesen" and "System" together find nothing.
        self.assertIn('href="/notifications/?unread=1&amp;category=system"', text)
        text = self.assert_ok(self.client.get(f"{NOTIFICATIONS}?category=system&unread=1"))
        self.assertIn("Keine Benachrichtigungen in dieser Kategorie.", text)
        # An unknown category shows everything.
        self.assertIn("Wiedervorlage: Firmenfeier", self.assert_ok(self.client.get(f"{NOTIFICATIONS}?category=x")))


# --- PRJ-109 ----------------------------------------------------------------------------------------------


class FollowUpTimePageTests(UiTestCase):
    """PRJ-109: the time in the dialog and wherever the follow-up shows."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.project = make_project("Firmenfeier", status=ProjectStatus.INQUIRY, manager=self.paula)
        self.page = reverse("projects:detail", args=[self.project.pk])
        self.dialog = reverse("projects:follow_up", args=[self.project.pk])

    def test_set_with_a_time_in_the_dialog(self) -> None:
        dialog = self.assert_ok(self.htmx("get", self.dialog))
        self.assertIn('type="time" name="follow_up_at"', dialog)
        self.assertIn("Uhrzeit", dialog)
        data = form_data(
            self.htmx("get", self.dialog),
            "follow_up_on",
            follow_up_on="2027-03-01",
            follow_up_at="14:30",
            follow_up_user=str(self.paula.pk),
            follow_up_note="Anrufen",
        )
        response = self.htmx("post", self.dialog, data)
        self.assertEqual(response.status_code, 204)
        self.project.refresh_from_db()
        self.assertEqual(self.project.follow_up_at, datetime.time(14, 30))
        text = self.assert_ok(self.client.get(self.page))
        self.assertIn("<strong>Wiedervorlage am Mo 01.03.2027 um 14:30</strong> für paula", text)
        # 08:00 on the clock of the tests: not yet due.
        self.assertNotIn('<span class="badge yellow">fällig</span>', text)
        set_clock(datetime.datetime(2027, 3, 1, 14, 30, tzinfo=self.project.start.tzinfo))
        self.client.force_login(self.admin_user)  # again: the clock moved past the idle time of the session
        self.assertIn('<span class="badge yellow">fällig</span>', self.assert_ok(self.client.get(self.page)))
        # Changing it again shows the time; emptying the field takes the time away.
        dialog = self.assert_ok(self.htmx("get", self.dialog))
        self.assertIn('value="14:30"', dialog)
        data["follow_up_at"] = ""
        self.htmx("post", self.dialog, data)
        self.project.refresh_from_db()
        self.assertIsNone(self.project.follow_up_at)

    def test_start_page_and_lists(self) -> None:
        set_follow_up(self.project, on=datetime.date(2027, 2, 28), at=datetime.time(9, 15), by=self.paula)
        start = self.assert_ok(self.browser_of(self.paula).get("/"))
        self.assertIn("So 28.02. um 09:15", start)
        projects = self.assert_ok(self.client.get("/projects/?follow_up=any&cols=name,follow_up"))
        self.assertIn("Wiedervorlage am 28.02.2027 um 09:15 für paula", projects)
        case = service_cases.create_case(name="Reparatur", manager=self.paula)
        set_follow_up(case, on=datetime.date(2027, 3, 4), at=datetime.time(11, 0), by=self.paula)
        self.assertIn("um 11:00", self.assert_ok(self.client.get("/projects/service-cases/")))


# --- VFG-034 ----------------------------------------------------------------------------------------------


class FollowUpTabTests(UiTestCase):
    """VFG-034: Planung → Wiedervorlagen."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.vera = make_user("vera", roles=("Projektleitung",))
        customer = make_customer("Stadtwerke")
        self.due = make_project("Firmenfeier", status=ProjectStatus.INQUIRY, manager=self.paula, customer=customer)
        self.later = make_project("Hochzeit", status=ProjectStatus.OPTION)
        self.case = service_cases.create_case(name="Reparatur Mischpult", manager=self.vera)
        self.without = make_project("Messe", status=ProjectStatus.CONFIRMED)
        set_follow_up(self.due, on=datetime.date(2027, 2, 26), note="Angebot nachfassen", by=self.paula)
        set_follow_up(self.later, on=datetime.date(2027, 3, 9), at=datetime.time(14, 30), by=self.paula)
        set_follow_up(self.case, on=datetime.date(2027, 3, 1), at=datetime.time(16, 0), note="Rückruf", by=self.vera)

    def test_the_last_tab_of_planning(self) -> None:
        text = self.assert_ok(self.client.get(FOLLOW_UPS))
        tabs = text[text.index('<nav class="tabs"') : text.index("</nav>", text.index('<nav class="tabs"'))]
        self.assertTrue(tabs.rstrip().endswith('aria-current="page">Wiedervorlagen</a>'))
        self.assertIn('href="/schedule/follow-ups/"', self.assert_ok(self.client.get("/schedule/")))
        # Reached from the navigation: no "Zurück" (UIX-011, UIX-041).
        self.assertNotIn(">Zurück<", text)

    def test_every_follow_up_with_day_time_whom_note_project_status(self) -> None:
        text = self.assert_ok(self.client.get(FOLLOW_UPS))
        for heading in ("Tag", "Uhrzeit", "Für", "Notiz", "Projekt", "Art", "Status", "Aktionen"):
            self.assertIn(f">{heading}", text)
        self.assertIn("Fr 26.02.2027", text)
        self.assertIn("14:30", text)
        self.assertIn("Angebot nachfassen", text)
        self.assertIn(f"{self.case.number} Reparatur Mischpult", text)
        self.assertIn(reverse("projects:case_detail", args=[self.case.pk]), text)
        self.assertIn("Servicefall", text)
        self.assertNotIn("Messe", text)
        # Sorted by day and time: 26.02., 01.03. 16:00, 09.03.
        self.assertLess(text.index("Firmenfeier"), text.index("Reparatur Mischpult"))
        self.assertLess(text.index("Reparatur Mischpult"), text.index("Hochzeit"))
        # Only the first is due at 08:00 on 1 March; the case of today at 16:00 is not yet.
        self.assertEqual(text.count('<span class="badge yellow">fällig</span>'), 1)

    def test_filters(self) -> None:
        def shown(query: str, client=None) -> set[str]:
            text = self.assert_ok((client or self.client).get(f"{FOLLOW_UPS}?{query}"))
            return {name for name in ("Firmenfeier", "Hochzeit", "Reparatur Mischpult") if name in text}

        self.assertEqual(shown(""), {"Firmenfeier", "Hochzeit", "Reparatur Mischpult"})
        self.assertEqual(shown("due=1"), {"Firmenfeier"})
        self.assertEqual(shown("since=2027-03-01&until=2027-03-05"), {"Reparatur Mischpult"})
        self.assertEqual(shown("who=mine", self.browser_of(self.vera)), {"Reparatur Mischpult"})
        self.assertEqual(shown("who=mine", self.browser_of(self.paula)), {"Firmenfeier", "Hochzeit"})
        set_clock(datetime.datetime(2027, 3, 1, 16, 0, tzinfo=self.due.start.tzinfo))
        self.client.force_login(self.admin_user)  # again: the clock moved past the idle time of the session
        self.assertEqual(shown("due=1"), {"Firmenfeier", "Reparatur Mischpult"})

    def test_csv_and_grouping(self) -> None:
        response = self.client.get(f"{FOLLOW_UPS}?format=csv&cols=all")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8-sig")
        header = content.splitlines()[0]
        self.assertIn("Tag;Uhrzeit;Für;Notiz;Projekt", header)
        self.assertNotIn("Aktionen", header)
        self.assertIn("26.02.2027", content)
        self.assertIn("Stadtwerke", content)
        text = self.assert_ok(self.client.get(f"{FOLLOW_UPS}?group=user"))
        self.assertIn('<option value="user" selected>', text)
        self.assertIn("table-group", text)

    def test_move_and_done_as_from_the_project(self) -> None:
        text = self.assert_ok(self.client.get(FOLLOW_UPS))
        dialog = reverse("projects:follow_up", args=[self.due.pk])
        done = reverse("projects:follow_up_done", args=[self.due.pk])
        self.assertIn(f'hx-get="{dialog}?next=%2Fschedule%2Ffollow-ups%2F"', text)
        self.assertIn(f'form="follow-up-done" formaction="{done}"', text)
        self.assertIn('<form method="post" id="follow-up-done">', text)
        response = self.client.post(done, {"next": FOLLOW_UPS}, follow=True)
        self.assertEqual(response.redirect_chain[-1][0], FOLLOW_UPS)
        self.due.refresh_from_db()
        self.assertIsNone(self.due.follow_up_on)
        # Moved in the dialog, back to the table.
        data = form_data(
            self.htmx("get", f"{reverse('projects:follow_up', args=[self.later.pk])}?next={FOLLOW_UPS}"),
            "follow_up_on",
            follow_up_on="2027-03-12",
            follow_up_at="10:00",
        )
        response = self.htmx("post", reverse("projects:follow_up", args=[self.later.pk]), data)
        self.assertEqual(response["HX-Redirect"], FOLLOW_UPS)
        self.later.refresh_from_db()
        self.assertEqual(
            (self.later.follow_up_on, self.later.follow_up_at), (datetime.date(2027, 3, 12), datetime.time(10))
        )

    def test_who_sees_what(self) -> None:
        # A reader sees every follow-up, without the buttons.
        reader = make_user("nora", roles=("Nur-Lesen",))
        text = self.assert_ok(self.browser_of(reader).get(FOLLOW_UPS))
        self.assertIn("Firmenfeier", text)
        self.assertNotIn('form="follow-up-done"', text)
        # Crew sees projects only through deployments – and no follow-ups of others (AUT-023).
        crew = make_user("carla", roles=("Crew",))
        text = self.assert_ok(self.browser_of(crew).get(FOLLOW_UPS))
        self.assertNotIn("Firmenfeier", text)
        self.assertIn("Deine Wiedervorlagen zu Projekten und Servicefällen.", text)
        self.assertNotIn('id="f-who"', text)
        # Without the module "Projekte" no page.
        stranger = make_user("lea", roles=("Lager",))
        self.assertEqual(self.browser_of(stranger).get(FOLLOW_UPS).status_code, 200)
        nobody = make_user("ole")
        self.assertIn(self.browser_of(nobody).get(FOLLOW_UPS).status_code, (302, 403))
