# SPDX-License-Identifier: GPL-3.0-or-later
"""Reminders of invoices still to be written, and "Rechnung gestellt" (DOK-015).

Requirement: when invoicing is switched on, a closed project reminds regularly to write an invoice. When it is switched off, a
yes/no value "Rechnung gestellt" holds this, so that the user can tick it when the invoice was written in other software.
"""

from __future__ import annotations

import datetime

from django.core.exceptions import ValidationError
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.core.models import NotificationSettings, SystemSettings
from rentalars.documents import invoice_reminders
from rentalars.documents.invoice_reminders import InvoiceState
from rentalars.documents.models import Document, DocumentKind
from rentalars.notifications.models import InvoiceNotice, Kind, Notification
from rentalars.projects import services
from rentalars.projects.models import InvoiceMark, Project, ProjectMembership, ProjectStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_line,
    at,
    make_customer,
    make_internal_project,
    make_person,
    make_project,
    make_stock,
    make_user,
    record_time,
    set_clock,
)
from tests.ui.base import UiTestCase


def close(project: Project) -> Project:
    """Return the material and close the project – now, by the test clock."""
    project.status = ProjectStatus.RETURNED
    project.save()
    services.change_status(project, ProjectStatus.CLOSED, rights=ALL_RIGHTS)
    return Project.objects.get(pk=project.pk)


def bookkeeping(**values: object) -> None:
    """Set the bookkeeping of the reminders (``BOOKKEEPING_FIELDS``) – never written by saving the settings."""
    NotificationSettings.objects.filter(pk=1).update(**values)


def invoices_in_rentalars(on: bool) -> None:
    settings = SystemSettings.load()
    settings.invoices_enabled = on
    settings.save()


def invoice_for(project: Project) -> Document:
    return Document.objects.create(
        project=project,
        kind=DocumentKind.INVOICE,
        number=f"RE-{project.pk}",
        title="Rechnung",
        issued_on=datetime.date(2027, 3, 2),
        file="documents/x.pdf",
        sha256="0" * 64,
    )


class InvoiceCase(RentalarsTestCase):
    """Paula's Stadtfest (one line with a price), closed on 1 March 2027; reminders on since February."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.project = make_project("Stadtfest", manager=self.paula)
        add_line(self.project, make_stock("S-100", 2), 2)
        settings = NotificationSettings.load()
        settings.invoice_reminders = True
        settings.invoice_first_days = 1
        settings.invoice_every_days = 7
        settings.save()
        # The bookkeeping of the check is written by the check alone – as here, by an update of the row.
        bookkeeping(invoice_reminders_since=at(1, 0, month=2), invoice_last_run=at(28, 9, month=2))
        self.project = close(self.project)


class StateTests(InvoiceCase):
    def test_open_until_invoiced_in_rentalars(self) -> None:
        invoices_in_rentalars(True)
        self.assertEqual(invoice_reminders.state_of(self.project), InvoiceState.OPEN)
        self.assertIn(self.project, invoice_reminders.open_projects())
        invoice = invoice_for(self.project)
        self.assertEqual(invoice_reminders.state_of(self.project), InvoiceState.INVOICED)
        self.assertNotIn(self.project, invoice_reminders.open_projects())
        # A cancelled invoice does not count.
        cancellation = Document.objects.create(
            project=self.project,
            kind=DocumentKind.CANCELLATION,
            number="ST-1",
            title="Stornorechnung",
            issued_on=datetime.date(2027, 3, 3),
            file="documents/y.pdf",
            sha256="0" * 64,
        )
        invoice.cancelled_by = cancellation
        invoice.save(update_fields=["cancelled_by"])
        self.assertEqual(invoice_reminders.state_of(self.project), InvoiceState.OPEN)

    def test_ticked_with_invoices_written_elsewhere(self) -> None:
        invoices_in_rentalars(False)
        self.assertEqual(invoice_reminders.state_of(self.project), InvoiceState.OPEN)
        invoice_reminders.set_invoice_status(self.project, InvoiceMark.ISSUED)
        self.assertEqual(invoice_reminders.state_of(self.project), InvoiceState.INVOICED)
        invoice_reminders.set_invoice_status(self.project, InvoiceMark.OPEN)
        invoice_reminders.set_invoice_status(self.project, InvoiceMark.NOT_NEEDED)
        self.assertEqual(invoice_reminders.state_of(self.project), InvoiceState.NOT_NEEDED)
        self.assertNotIn(self.project, invoice_reminders.open_projects())

    def test_no_invoice_of_its_own(self) -> None:
        internal = make_internal_project()
        self.assertEqual(invoice_reminders.state_of(internal), InvoiceState.NONE)
        with self.assertRaises(ValidationError):
            invoice_reminders.set_invoice_status(internal, InvoiceMark.ISSUED)
        with self.assertRaises(ValidationError):
            invoice_reminders.set_invoice_status(self.project, "bezahlt")


class ReminderTests(InvoiceCase):
    def test_first_after_a_day_then_every_week_until_ticked(self) -> None:
        invoices_in_rentalars(False)
        # The day it was closed: not yet.
        self.assertEqual(invoice_reminders.due_projects(at(1, 12)), [])
        self.assertEqual(invoice_reminders.run_due_invoice_reminders(at(2, 9, 1)), 1)
        notice = Notification.objects.get(user=self.paula, kind=Kind.INVOICE_REMINDER)
        self.assertEqual(str(notice.title), f"Rechnung noch zu schreiben: {self.project.number} Stadtfest")
        self.assertIn("„Rechnung gestellt“", str(notice.body))
        # the notice opens the project's Überblick – adapted.
        self.assertEqual(notice.url, reverse("projects:overview", args=[self.project.pk]))
        # Once a day only; the next one a week later.
        self.assertIsNone(invoice_reminders.run_due_invoice_reminders(at(2, 15)))
        self.assertEqual(invoice_reminders.run_due_invoice_reminders(at(3, 9, 1)), 0)
        self.assertEqual(invoice_reminders.run_due_invoice_reminders(at(9, 9, 1)), 1)
        self.assertEqual(InvoiceNotice.objects.get(project=self.project).count, 2)
        invoice_reminders.set_invoice_status(self.project, InvoiceMark.ISSUED)
        self.assertFalse(InvoiceNotice.objects.filter(project=self.project).exists())
        self.assertEqual(invoice_reminders.run_due_invoice_reminders(at(16, 9, 1)), 0)

    def test_counted_in_days_of_the_calendar(self) -> None:
        """Review finding 3: closed in the afternoon – reminded at the next morning's check, not a day later."""
        invoices_in_rentalars(False)
        set_clock(at(1, 17))
        late = make_project("Sommerfest", manager=self.paula)
        add_line(late, make_stock("S-200", 2), 1)
        late = close(late)
        self.assertEqual(invoice_reminders.due_projects(at(1, 17, 30)), [])
        self.assertEqual(invoice_reminders.due_projects(at(2, 9, 1)), [self.project, late])

    def test_0_days_at_the_next_check(self) -> None:
        """0: at the next check after closing – the same day for the project closed at 8:00."""
        settings = NotificationSettings.load()
        settings.invoice_first_days = 0
        settings.save()
        self.assertEqual(invoice_reminders.due_projects(at(1, 9, 1)), [self.project])

    def test_service_cases_with_work_recorded(self) -> None:
        """Review finding 4: a case has no lines – what there is to charge are the times recorded on it."""
        from rentalars.projects import service_cases
        from rentalars.projects.models import CaseStatus

        settings = NotificationSettings.load()
        settings.invoice_service_cases = True
        settings.save()
        idle = service_cases.create_case(name="Nur angeschaut", customer=make_customer("Theater"), manager=self.paula)
        worked = service_cases.create_case(name="Spot repariert", customer=make_customer("Kino"), manager=self.paula)
        record_time(make_person("Tom"), worked, "Techniker", at(1, 9), at(1, 11))
        for case in (idle, worked):
            service_cases.set_case_status(case, CaseStatus.DONE, by=self.paula)
        due = invoice_reminders.due_projects(at(5, 9, 1))
        self.assertIn(worked, due)
        self.assertNotIn(idle, due)
        self.assertIn(self.project, due)

    def test_with_invoices_in_rentalars_the_reminder_leads_to_the_invoice(self) -> None:
        invoices_in_rentalars(True)
        invoice_reminders.run_due_invoice_reminders(at(2, 9, 1))
        notice = Notification.objects.get(user=self.paula, kind=Kind.INVOICE_REMINDER)
        self.assertTrue(notice.url.startswith(reverse("documents:list", args=[self.project.pk])))
        self.assertIn("Erstelle die Rechnung in Rentalars", str(notice.body))

    def test_projects_closed_before_the_update_are_left_alone(self) -> None:
        bookkeeping(invoice_reminders_since=at(1, 9))
        self.assertEqual(invoice_reminders.due_projects(at(5, 9)), [])

    def test_nothing_to_charge_nothing_to_remind(self) -> None:
        free = close(make_project("Umsonst", manager=self.paula))
        self.assertIn(free, invoice_reminders.open_projects())
        self.assertNotIn(free, invoice_reminders.due_projects(at(5, 9)))

    def test_only_who_may_see_prices(self) -> None:
        crew = make_user("kai", roles=("Crew",))
        settings = NotificationSettings.load()
        settings.invoice_user = crew
        settings.save()
        self.assertEqual(invoice_reminders.recipients_of(self.project), [self.paula])

    def test_only_who_may_read_the_project(self) -> None:
        """Review finding 9: a reminder names the project – not to somebody limited to other projects."""
        Role.objects.create(
            name="Büro extern",
            module_levels={"projects": 2},
            special_rights=["prices"],
            project_scope="assigned",
        )
        office = make_user("olga", roles=("Büro extern",))
        settings = NotificationSettings.load()
        settings.invoice_user = office
        settings.save()
        self.assertEqual(invoice_reminders.recipients_of(self.project), [self.paula])
        ProjectMembership.objects.create(project=self.project, user=office, level="read")
        self.assertEqual(invoice_reminders.recipients_of(self.project), [self.paula, office])

    def test_switched_off_nothing(self) -> None:
        settings = NotificationSettings.load()
        settings.invoice_reminders = False
        settings.save()
        self.assertIsNone(invoice_reminders.run_due_invoice_reminders(at(5, 9, 1)))
        self.assertIsNone(invoice_reminders.next_run(at(5, 9, 1)))


class ClosedBeforeTests(InvoiceCase):
    """Review finding 11: projects closed before the update are not "open" – nobody knows about their invoice."""

    def test_neither_open_nor_reminded_until_reopened(self) -> None:
        invoices_in_rentalars(False)
        Project.objects.filter(pk=self.project.pk).update(invoice_status=InvoiceMark.EARLIER)
        project = Project.objects.get(pk=self.project.pk)
        self.assertEqual(invoice_reminders.state_of(project), InvoiceState.NONE)
        self.assertNotIn(project, invoice_reminders.open_projects())
        self.assertEqual(invoice_reminders.due_projects(at(5, 9, 1)), [])
        with self.assertRaises(ValidationError):
            invoice_reminders.set_invoice_status(project, InvoiceMark.EARLIER)
        # An invoice made in Rentalars still counts.
        invoices_in_rentalars(True)
        invoice_for(project)
        self.assertEqual(invoice_reminders.state_of(project), InvoiceState.INVOICED)
        # Opened again, it is followed from now on.
        Document.objects.all().delete()
        services.change_status(project, ProjectStatus.RETURNED, rights=ALL_RIGHTS)
        self.assertEqual(Project.objects.get(pk=project.pk).invoice_status, InvoiceMark.OPEN)


class InvoicePageTests(UiTestCase):
    """The tick box in the head of a project, the filter of the list, the start page, the settings."""

    def setUp(self) -> None:
        super().setUp()
        invoices_in_rentalars(False)
        self.project = make_project("Stadtfest", manager=self.admin_user)
        add_line(self.project, make_stock("S-100", 2), 2)
        self.project = close(self.project)
        bookkeeping(invoice_reminders_since=at(1, 0, month=2))

    def test_tick_invoice_issued(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.project.pk])))
        self.assertIn("Rechnung offen", page)
        self.assertIn('name="invoice_status" value="issued"', page)
        mark = reverse("documents:invoice_mark", args=[self.project.pk])
        self.client.post(mark, {"invoice_status": "issued"})
        self.assertEqual(Project.objects.get(pk=self.project.pk).invoice_status, InvoiceMark.ISSUED)
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.project.pk])))
        self.assertIn("Rechnung gestellt", page)
        # Unticked: open again.
        self.client.post(mark, {})
        self.assertEqual(Project.objects.get(pk=self.project.pk).invoice_status, InvoiceMark.OPEN)
        # Without the price right: refused.
        crew = self.browser_for("kai", "Crew")
        self.assertIn(crew.post(mark, {"invoice_status": "issued"}).status_code, (403, 404))

    def test_list_filter_and_start_page(self) -> None:
        listed = self.assert_ok(self.client.get(reverse("projects:list"), {"invoice": "open"}))
        self.assertIn(self.project.number, listed)
        home = self.assert_ok(self.client.get(reverse("core:home")))
        self.assertIn("Noch zu schreibende Rechnungen", home)
        self.assertIn(f"{reverse('projects:list')}?invoice=open", home)

    def test_the_settings(self) -> None:
        page = self.assert_ok(self.client.get(reverse("notifications:company_settings")))
        self.assertIn("An Rechnungen erinnern", page)
        self.assertIn("Erste Erinnerung nach (Tagen)", page)


class InvoiceApiTests(ApiTestCase):
    def test_invoice_status_and_settings(self) -> None:
        invoices_in_rentalars(False)
        project = make_project("Stadtfest")
        add_line(project, make_stock("S-100", 2), 2)
        project = close(project)
        data = self.admin.get(f"{API}/projects/{project.pk}").json()
        self.assertEqual(data["invoice_state"], "open")
        response = self.admin.post(
            f"{API}/projects/{project.pk}/invoice-status", {"invoice_status": "issued"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.admin.get(f"{API}/projects/{project.pk}").json()["invoice_state"], "invoiced")
        response = self.admin.post(
            f"{API}/projects/{project.pk}/invoice-status", {"invoice_status": "x"}, format="json"
        )
        self.assert_error(response, 400, "validation_error")
        response = self.admin.patch(
            f"{API}/settings/notifications", {"invoice_reminders": True, "invoice_every_days": 3}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["invoice_every_days"], 3)
        self.assertTrue(NotificationSettings.load().invoice_reminders)
