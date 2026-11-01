# SPDX-License-Identifier: GPL-3.0-or-later
"""Planning overviews, notifications, the start page and the self-check in the browser.

PRJ-028, VFG-012 to VFG-014, UIX-003, UIX-005, NFA-018, NFA-037.
"""

from __future__ import annotations

import logging

from django.core import mail

from rentalars.core.errors import OperatorHandler
from rentalars.core.models import ErrorRecord
from rentalars.material import services as material_services
from rentalars.material.models import ItemStatus
from rentalars.notifications.models import Kind, Notification, ShortageNotice
from rentalars.notifications.services import check_shortages, notify
from rentalars.personnel.models import Absence
from rentalars.projects.models import OpenItem, ProjectStatus
from tests.helpers import (
    add_line,
    at,
    make_items,
    make_model,
    make_person,
    make_project,
    make_stock,
    make_user,
    plan,
)
from tests.ui.base import UiTestCase


class SchedulePageTests(UiTestCase):
    """PRJ-028 calendar and timeline, VFG-012 utilization, VFG-014 personnel plan."""

    def test_calendar_and_timeline(self) -> None:
        make_project("Stadtfest")
        make_project("Abgesagt", status=ProjectStatus.CANCELLED)
        text = self.assert_ok(self.client.get("/schedule/", {"month": "2027-03"}))
        self.assertIn("Stadtfest", text)
        self.assertNotIn("Abgesagt", text)
        text = self.assert_ok(self.client.get("/schedule/timeline/", {"from": "2027-03-08", "weeks": "2"}))
        self.assertIn("Stadtfest", text)
        self.assertIn(
            "Abgesagt", self.assert_ok(self.client.get("/schedule/timeline/", {"from": "2027-03-08", "all": "1"}))
        )

    def test_utilization_of_a_product(self) -> None:
        speaker = make_stock("L-001", 4, "Topteil")
        add_line(make_project(), speaker, 6)
        text = self.assert_ok(self.client.get("/schedule/products/", {"q": "Topteil", "from": "2027-03-08"}))
        self.assertIn("Topteil", text)
        self.assertIn("short", text)
        crew = self.browser_for("ben", "Crew")
        self.assertEqual(crew.get("/schedule/products/").status_code, 403)

    def test_personnel_plan_marks_double_bookings(self) -> None:
        anna = make_person("Anna Becker")
        plan(make_project("Stadtfest"), "Stagehand", anna, start=at(10, 8), end=at(10, 18))
        Absence.objects.create(person=anna, start=at(10, 12), end=at(11))
        text = self.assert_ok(self.client.get("/schedule/personnel/", {"from": "2027-03-08", "busy": "1"}))
        self.assertIn("Anna Becker", text)
        self.assertIn("Einsätze überschneiden sich", text)

    def test_shortages_list_by_product(self) -> None:
        speaker = make_stock("L-001", 2, "Topteil")
        add_line(make_project(), speaker, 5)
        text = self.assert_ok(self.client.get("/shortages/", {"by_product": "1"}))
        self.assertIn("Topteil", text)


class NotificationPageTests(UiTestCase):
    """UIX-005 and the events that send notifications."""

    def test_list_open_and_mark_all(self) -> None:
        notify([self.admin_user], Kind.DEFECT, "Defekt: Kabel", url="/material/")
        notify([self.admin_user], Kind.SHORTAGE, "Fehlbestand")
        text = self.assert_ok(self.client.get("/notifications/"))
        self.assertIn("Defekt: Kabel", text)
        first = Notification.objects.get(title="Defekt: Kabel")
        self.assertEqual(self.client.get(f"/notifications/{first.pk}/")["Location"], "/material/")
        first.refresh_from_db()
        self.assertIsNotNone(first.read_at)
        self.client.post("/notifications/read/")
        self.assertFalse(Notification.objects.filter(read_at__isnull=True).exists())

    def test_preferences_switch_mails_off(self) -> None:
        ben = make_user("ben")
        ben.email = "ben@verleih.example"
        ben.save()
        browser = self.browser_of(ben)
        self.assert_ok(browser.get("/account/notifications/"))
        data = {f"{kind}-app": "1" for kind in Kind.values}
        browser.post("/account/notifications/", data)
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            notify([ben], Kind.SHORTAGE, "Fehlbestand: Topteil")
        self.assertEqual(mail.outbox, [])
        self.assertTrue(Notification.objects.filter(user=ben, title="Fehlbestand: Topteil").exists())

    def test_a_defect_is_reported_to_the_warehouse(self) -> None:
        warehouse = make_user("luka", roles=("Lager",))
        model = make_model("Kabel")
        (item,) = make_items(model)
        material_services.set_status(item, ItemStatus.DEFECTIVE, reason="Stecker lose")
        self.assertTrue(Notification.objects.filter(user=warehouse, kind=Kind.DEFECT).exists())

    def test_shortages_are_reported_once(self) -> None:
        manager = make_user("paula", roles=("Projektleitung",))
        speaker = make_stock("L-001", 2, "Topteil")
        add_line(make_project(manager=manager), speaker, 5)
        self.assertEqual(check_shortages(), 1)
        self.assertEqual(check_shortages(), 0)
        self.assertEqual(ShortageNotice.objects.count(), 1)
        self.assertEqual(Notification.objects.filter(user=manager, kind=Kind.SHORTAGE).count(), 1)

    def test_a_status_change_is_announced_to_the_project_people(self) -> None:
        manager = make_user("paula", roles=("Projektleitung",))
        project = make_project(manager=manager, status=ProjectStatus.INQUIRY)
        self.client.post(f"/projects/{project.pk}/status/", {"status": "option"})
        self.assertTrue(Notification.objects.filter(user=manager, kind=Kind.PROJECT_CHANGE).exists())


class StartPageTests(UiTestCase):
    """UIX-003: the start page shows what concerns the user now."""

    def test_project_people_see_open_items_and_shortages(self) -> None:
        project = make_project("Stadtfest", status=ProjectStatus.CONFIRMED_OPEN)
        OpenItem.objects.create(project=project, text="Strom klären")
        add_line(project, make_stock("L-001", 1, "Topteil"), 3)
        text = self.assert_ok(self.client.get("/"))
        self.assertIn("Offene Punkte", text)
        self.assertIn("Stadtfest", text)
        self.assertIn("Offene Fehlbestände", text)  # UIX-021: all of them, not two weeks only

    def test_crew_sees_requests_and_own_deployments(self) -> None:
        ben = make_user("ben", roles=("Crew",))
        project = make_project("Weinfest")
        line = plan(project, "Stagehand", make_person("Ben Schmidt", user=ben))
        self.client.post(f"/projects/{project.pk}/crew/{line.pk}/request/")
        text = self.assert_ok(self.browser_of(ben).get("/"))
        self.assertIn("Du bist angefragt", text)
        self.assertIn("Weinfest", text)
        self.assertNotIn("Fehlbestände", text)


class SelfCheckPageTests(UiTestCase):
    """NFA-037, NFA-018: the self-check page, the test mail and recorded errors."""

    def test_the_page_and_a_test_mail(self) -> None:
        text = self.assert_ok(self.client.get("/administration/self-check/"))
        for group in ("Versionen", "Datenbank", "Sicherung", "Sicherheit"):
            self.assertIn(group, text)
        self.admin_user.email = "admin@verleih.example"
        self.admin_user.save()
        response = self.client.post("/administration/self-check/", {"action": "test_mail"}, follow=True)
        self.assertIn("Eine Testmail ging an admin@verleih.example.", self.messages_of(response))
        self.assertEqual(mail.outbox[-1].to, ["admin@verleih.example"])
        self.assertEqual(self.browser_for("luka", "Lager").get("/administration/self-check/").status_code, 403)

    def test_errors_are_recorded_and_reported_once(self) -> None:
        """NFA-018: an error of the application reaches the operators – once, not a flood."""
        # The handler of the logging configuration, without the console that would only add noise here.
        logger = logging.getLogger("rentalars.test.errors")
        logger.addHandler(OperatorHandler())
        logger.propagate = False
        self.addCleanup(setattr, logger, "handlers", [])
        for _attempt in range(3):
            try:
                raise RuntimeError("Datenbank weg")
            except RuntimeError:
                logger.exception("Something broke")
        record = ErrorRecord.objects.get()
        self.assertEqual(record.count, 3)
        self.assertEqual(Notification.objects.filter(kind=Kind.SYSTEM_ERROR, user=self.admin_user).count(), 1)
        self.assertIn(
            "RuntimeError: Datenbank weg – 3×", self.assert_ok(self.client.get("/administration/self-check/"))
        )
