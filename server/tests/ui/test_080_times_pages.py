# SPDX-License-Identifier: GPL-3.0-or-later
"""On the pages, area "times": hints at conspicuous times (ZEI-018), expenses and travel costs (ZEI-019).

* ZEI-018: the hints appear when a time is entered (the confirmation of the quick entry, "My times"), in the
  approval and in the report with its CSV file and timesheet – and never stop anything.
* ZEI-019: "My expenses" with the dialog, a receipt photo and a trip by kilometre; approval together with the
  times; the report per month and person with "reimbursed" and CSV; the costs in the totals of the planning; the
  settings.
"""

from __future__ import annotations

import datetime
from decimal import Decimal as D  # noqa: N817

from django.urls import reverse
from django.utils import translation

from rentalars.core.models import SystemSettings
from rentalars.notifications.models import Notification
from rentalars.timetracking import expenses
from rentalars.timetracking.models import Expense, ExpenseKind, TimeEntry, TimeEntryStatus
from tests.helpers import LATER, at, job_function, make_person, make_project, make_user, plan, record_time, set_clock
from tests.ui.base import UiTestCase, form_data
from tests.unit.test_080_times import PDF, MediaMixin, picture, upload


class TimesPageCase(MediaMixin, UiTestCase):
    """Anna (crew) is planned as sound engineer on the Stadtfest; Paula manages projects. Late March 2027."""

    def setUp(self) -> None:
        super().setUp()
        set_clock(LATER)
        self.client.force_login(self.admin_user)
        self.project = make_project("Stadtfest", start=at(10), end=at(12))
        self.sound = job_function("Tontechnik", price="45.00")
        self.anna_user = make_user("anna", roles=("Crew",))
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"}, user=self.anna_user)
        plan(self.project, self.sound, self.anna, start=at(9, 6), end=at(12, 23))
        self.crew = self.browser_of(self.anna_user)
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.manager = self.browser_of(self.paula)

    def spend(self, amount: str = "14.00", *, kind: str = ExpenseKind.MEALS, submit: bool = True, **more) -> Expense:
        values = {"date": datetime.date(2027, 3, 10), "project": self.project, **more}
        return expenses.create_expense(
            person=self.anna,
            kind=kind,
            amount=D(amount),
            rights=self.anna_user.rights,
            user=self.anna_user,
            submit=submit,
            **values,
        )


# --- ZEI-018 ---------------------------------------------------------------------------------------------------------


class HintPageTests(TimesPageCase):
    """ZEI-018: shown when entering, in the approval and the report; never blocking."""

    def test_the_quick_entry_points_out_a_long_day_and_saves_it_all_the_same(self) -> None:
        """ZEI-018: the hint is shown when entering and never blocks."""
        quick = reverse("timetracking:quick")
        dialog = self.htmx("get", quick, {"project": self.project.pk}, client=self.crew)
        saved = self.assert_ok(
            self.htmx(
                "post",
                quick,
                form_data(dialog, day="2027-03-10", begin="07:00", end="19:30", break_minutes="45"),
                client=self.crew,
            )
        )
        self.assertIn("Zeit erfasst", saved)
        self.assertIn("Bitte prüfen:", saved)
        self.assertIn("Langer Arbeitstag: 11,75 Stunden Arbeit (mehr als 10).", saved)
        self.assertIn("Die Zeit ist gespeichert.", saved)
        self.assertEqual(TimeEntry.objects.get().status, TimeEntryStatus.SUBMITTED)

    def test_an_ordinary_day_has_no_hint(self) -> None:
        quick = reverse("timetracking:quick")
        dialog = self.htmx("get", quick, {"project": self.project.pk}, client=self.crew)
        saved = self.assert_ok(
            self.htmx(
                "post",
                quick,
                form_data(dialog, day="2027-03-10", begin="08:00", end="16:30", break_minutes="30"),
                client=self.crew,
            )
        )
        self.assertNotIn("Bitte prüfen", saved)
        self.assertNotIn("time-hint", saved)

    def test_my_times_show_the_hints_of_the_week(self) -> None:
        """ZEI-018."""
        record_time(self.anna, self.project, self.sound, at(10, 14), at(10, 23), break_minutes=45, submit=True)
        record_time(self.anna, self.project, self.sound, at(11, 7), at(11, 12), submit=True)
        week = self.assert_ok(self.crew.get(reverse("timetracking:my_times"), {"week": "2027-03-10"}))
        self.assertIn("Kurze Ruhezeit: 8 Stunden seit dem Ende um 23:00 am 10.03. (weniger als 11).", week)

    def test_the_approval_shows_the_hints_and_approves_anyway(self) -> None:
        """ZEI-018: in the approval; approving stays possible."""
        entry = record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 15), submit=True)
        page = self.assert_ok(self.manager.get(reverse("timetracking:approval")))
        self.assertIn("Kurze Pause: 7 Stunden Arbeit mit 0 Minuten Pause (mindestens 30).", page)
        self.manager.post(reverse("timetracking:decide"), {"entry": [entry.pk], "decision": "approve"})
        entry.refresh_from_db()
        self.assertEqual(entry.status, TimeEntryStatus.APPROVED)

    def test_the_report_counts_and_filters_the_hints(self) -> None:
        """ZEI-018: in the report, with "only entries with hints", the CSV file and the timesheet."""
        record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 19), break_minutes=45, approve=True)
        record_time(self.anna, self.project, self.sound, at(12, 8), at(12, 12), approve=True)
        url = reverse("timetracking:report")
        page = self.assert_ok(self.manager.get(url, {"since": "2027-03-01"}))
        self.assertIn("1 Eintrag hat einen Hinweis", page)
        self.assertIn("Langer Arbeitstag: 10,25 Stunden Arbeit (mehr als 10).", page)
        self.assertIn("with_hints=on", page)
        only = self.assert_ok(self.manager.get(url, {"since": "2027-03-01", "with_hints": "on"}))
        self.assertIn("10.03.2027", only)
        self.assertNotIn("12.03.2027", only)
        rows = (
            self.manager.get(url, {"since": "2027-03-01", "format": "csv"})
            .content.decode("utf-8-sig")
            .strip()
            .splitlines()
        )
        self.assertTrue(rows[0].endswith(";Notiz;Hinweise"))
        self.assertTrue(rows[1].endswith(";Langer Arbeitstag: 10,25 Stunden Arbeit (mehr als 10)."))
        self.assertTrue(rows[2].endswith(";;"))

    def test_the_timesheet_prints_the_hints(self) -> None:
        from rentalars.accounts.rights import Rights
        from rentalars.timetracking import services
        from rentalars.timetracking.pdf import render_timesheet_html

        record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 19), break_minutes=45, approve=True)
        report = services.hours_report(TimeEntry.objects.all(), rights=Rights.everything(), user=None)
        self.assertIn("Hinweis: Langer Arbeitstag", render_timesheet_html(report, "März 2027"))

    def test_the_limits_are_settings(self) -> None:
        """ZEI-018: under Einstellungen → Firmendaten und Grundeinstellungen, with the defaults of the act."""
        page = self.assert_ok(self.client.get(reverse("core:company_settings")))
        for shown in (
            "Hinweis: Arbeitstag länger als … Stunden",
            "Hinweis: Pause nötig ab mehr als … Stunden Arbeit",
            "Hinweis: Ruhezeit zwischen zwei Arbeitstagen kürzer als … Stunden",
            "Fahrtkosten je Kilometer",
        ):
            self.assertIn(shown, page)
        data = form_data(self.client.get(reverse("core:company_settings")), containing="system-time_hint_day_hours")
        self.assertEqual(
            (data["system-time_hint_day_hours"], data["system-time_hint_rest_hours"], data["system-expense_km_rate"]),
            ("10,0", "11,0", "0,30"),
        )
        data.update({"system-time_hint_day_hours": "8", "system-expense_km_rate": "0,38", "form": "system"})
        self.client.post(reverse("core:company_settings"), data)
        settings = SystemSettings.load()
        self.assertEqual((settings.time_hint_day_hours, settings.expense_km_rate), (D("8"), D("0.38")))


# --- ZEI-019 ---------------------------------------------------------------------------------------------------------


class RecordExpensePageTests(TimesPageCase):
    """ZEI-019: expenses are entered by the person (also on the phone) or by the office."""

    def test_record_with_a_photo_of_the_receipt(self) -> None:
        """ZEI-019: the dialog – project, kind, day, amount, note, receipt."""
        url = reverse("timetracking:expense_new")
        dialog = self.htmx("get", url, client=self.crew)
        text = self.assert_ok(dialog)
        for shown in ("Spesen erfassen", "Verpflegung", "Fahrt", "Übernachtung", "Parken/Maut", "Sonstiges"):
            self.assertIn(shown, text)
        self.assertIn('accept="image/jpeg,image/png,application/pdf"', text)
        self.assertIn('hx-encoding="multipart/form-data"', text)
        self.assertIn('data-show-if="kind=travel"', text)
        data = form_data(dialog, kind="meals", date="2027-03-10", amount="14,50", note="Mittag Aufbau")
        data["receipt"] = upload("beleg.jpg", picture(800, 600))
        saved = self.assert_ok(self.htmx("post", url, data, client=self.crew))
        self.assertIn("Spesen erfasst", saved)
        self.assertIn("14,50 €", saved)
        self.assertIn("mit Beleg", saved)
        expense = Expense.objects.get()
        self.assertEqual(
            (expense.person, expense.project, expense.amount, expense.status),
            (self.anna, self.project, D("14.50"), TimeEntryStatus.SUBMITTED),
        )
        self.assertTrue(expense.receipt)

    def test_a_trip_by_kilometre(self) -> None:
        """ZEI-019: kilometres × 0,30 €; the amount stays empty."""
        url = reverse("timetracking:expense_new")
        dialog = self.htmx("get", url, client=self.crew)
        self.assertIn("× 0,30 € je Kilometer ergibt den Betrag.", self.assert_ok(dialog))
        data = form_data(dialog, kind="travel", date="2027-03-10", kilometres="84", amount="")
        saved = self.assert_ok(self.htmx("post", url, data, client=self.crew))
        self.assertIn("25,20 €", saved)
        self.assertIn("84 km × 0,30 €", saved)

    def test_missing_amount_stays_in_the_dialog(self) -> None:
        url = reverse("timetracking:expense_new")
        dialog = self.htmx("get", url, client=self.crew)
        again = self.assert_ok(self.htmx("post", url, form_data(dialog, kind="travel", amount=""), client=self.crew))
        self.assertIn("Gib die Kilometer der Fahrt ein oder den Betrag eines Tickets.", again)
        again = self.assert_ok(self.htmx("post", url, form_data(dialog, kind="parking", amount=""), client=self.crew))
        self.assertIn("Gib den Betrag ein.", again)
        self.assertFalse(Expense.objects.exists())

    def test_a_text_file_is_no_receipt(self) -> None:
        """NFA-007."""
        url = reverse("timetracking:expense_new")
        data = form_data(self.htmx("get", url, client=self.crew), amount="5,00")
        data["receipt"] = upload("beleg.jpg", b"<html>no</html>")
        again = self.assert_ok(self.htmx("post", url, data, client=self.crew))
        self.assertIn("Ein Beleg ist ein Foto (JPEG oder PNG) oder eine PDF-Datei.", again)
        self.assertFalse(Expense.objects.exists())

    def test_without_scripts_the_dialog_is_a_page(self) -> None:
        url = reverse("timetracking:expense_new")
        page = self.assert_ok(self.crew.get(url))
        self.assertIn("<h1>Spesen</h1>", page)
        self.assertIn('enctype="multipart/form-data"', page)
        data = form_data(self.crew.get(url), amount="8,00")
        self.assertIn("Spesen erfasst", self.assert_ok(self.crew.post(url, data)))

    def test_the_project_comes_preselected_from_the_deployment_view(self) -> None:
        """ZEI-019: the deployment view of the crew has "Spesen erfassen" and lists the own expenses."""
        self.spend(note="Parkhaus Markt", kind=ExpenseKind.PARKING, amount="6.00")
        page = self.assert_ok(self.crew.get(reverse("projects:deployment", args=[self.project.pk])))
        self.assertIn("Meine Spesen in diesem Projekt", page)
        self.assertIn(f"{reverse('timetracking:expense_new')}?project={self.project.pk}", page)
        self.assertIn("Parkhaus Markt", page)
        self.assertIn("data-reload-after-expenses", page)

    def test_after_a_time_the_expenses_are_one_click_away(self) -> None:
        quick = reverse("timetracking:quick")
        dialog = self.htmx("get", quick, {"project": self.project.pk}, client=self.crew)
        saved = self.assert_ok(
            self.htmx("post", quick, form_data(dialog, day="2027-03-10", begin="08:00", end="12:00"), client=self.crew)
        )
        self.assertIn(f"{reverse('timetracking:expense_new')}?project={self.project.pk}", saved)

    def test_the_office_records_for_somebody_else(self) -> None:
        """ZEI-019, ZEI-011."""
        url = reverse("timetracking:expense_new")
        own = self.assert_ok(self.htmx("get", url, client=self.crew))
        self.assertNotIn('id="expense-person"', own)  # the crew records for herself only
        dialog = self.htmx("get", url, {"person": self.anna.pk, "amount": "20,00"}, client=self.manager)
        text = self.assert_ok(dialog)
        self.assertIn("Spesen erfassen – Anna Becker", text)
        # The office chooses the person; another one loads the dialog again and keeps what was typed.
        self.assertIn('id="expense-person"', text)
        self.assertIn(f'<option value="{self.anna.pk}" selected>Becker, Anna</option>', text)
        self.assertIn('value="20,00"', text)
        self.htmx("post", url, form_data(dialog, amount="20,00"), client=self.manager)
        self.assertEqual(Expense.objects.get().person, self.anna)
        refused = self.htmx("get", url, {"person": self.anna.pk}, client=self.browser_for("kai", "Crew"))
        self.assertNotIn("Anna Becker", refused.content.decode())


class MyExpensesPageTests(TimesPageCase):
    """ZEI-019: the own expenses month by month, correct, delete, hand in."""

    def test_the_month_with_its_sum(self) -> None:
        self.spend("14.00")
        self.spend("6.00", kind=ExpenseKind.PARKING, date=datetime.date(2027, 3, 11))
        self.spend("9.00", date=datetime.date(2027, 2, 20))
        page = self.assert_ok(self.crew.get(reverse("timetracking:my_expenses"), {"month": "2027-03"}))
        self.assertIn("Spesen im März 2027", page)
        self.assertIn("Summe des Monats", page)
        self.assertIn("20,00 €", page)
        self.assertNotIn("9,00 €", page)
        self.assertIn('aria-current="page">Meine Spesen', page)
        self.assertIn("format=csv", page)

    def test_correct_in_the_dialog_and_delete(self) -> None:
        expense = self.spend("14.00", submit=False)
        url = reverse("timetracking:expense_edit", args=[expense.pk])
        dialog = self.htmx("get", url, client=self.crew)
        self.assertIn("Spesen bearbeiten", self.assert_ok(dialog))
        answer = self.htmx("post", url, form_data(dialog, amount="16,00"), client=self.crew)
        self.assertEqual(answer.status_code, 204)
        self.assertIn("expensesChanged", answer["HX-Trigger"])
        expense.refresh_from_db()
        # Not handed in before, and the tick was not set: it stays with her.
        self.assertEqual((expense.amount, expense.status), (D("16.00"), TimeEntryStatus.RECORDED))
        self.crew.post(reverse("timetracking:expense_delete", args=[expense.pk]))
        self.assertFalse(Expense.objects.exists())

    def test_hand_in_all_open(self) -> None:
        self.spend(submit=False)
        page = self.assert_ok(self.crew.get(reverse("timetracking:my_expenses")))
        self.assertIn("Noch nicht eingereicht", page)
        done = self.crew.post(reverse("timetracking:expense_submit"), follow=True)
        self.assertIn("1 Spesenposten zur Freigabe eingereicht.", " ".join(self.messages_of(done)))
        self.assertEqual(Expense.objects.get().status, TimeEntryStatus.SUBMITTED)

    def test_the_receipt_is_shown_only_to_who_may_see_the_expense(self) -> None:
        """NFA-007: no plain address; the rights are checked."""
        expense = self.spend(receipt=upload("hotel.pdf", PDF, "application/pdf"))
        url = reverse("timetracking:expense_receipt", args=[expense.pk])
        own = self.crew.get(url)
        self.assertEqual(own.status_code, 200)
        self.assertEqual(b"".join(own.streaming_content), PDF)
        self.assertIn("sandbox", own["Content-Security-Policy"])
        self.assertEqual(self.manager.get(url).status_code, 200)
        self.assertEqual(self.browser_for("kai", "Crew").get(url).status_code, 404)

    def test_approved_expenses_are_locked(self) -> None:
        expense = self.spend()
        expenses.approve_expenses([expense], rights=self.paula.rights, user=self.paula)
        page = self.assert_ok(self.crew.get(reverse("timetracking:my_expenses"), {"month": "2027-03"}))
        self.assertNotIn(reverse("timetracking:expense_edit", args=[expense.pk]), page)
        answer = self.crew.get(reverse("timetracking:expense_edit", args=[expense.pk]), follow=True)
        self.assertIn("Freigegebene Spesen sind gesperrt", " ".join(self.messages_of(answer)))

    def test_somebody_elses_expense_cannot_be_opened(self) -> None:
        expense = self.spend()
        kai = self.browser_for("kai", "Crew")
        self.assertEqual(kai.get(reverse("timetracking:expense_edit", args=[expense.pk])).status_code, 404)
        self.assertEqual(kai.post(reverse("timetracking:expense_delete", args=[expense.pk])).status_code, 404)


class ExpenseApprovalPageTests(TimesPageCase):
    """ZEI-019: expenses are approved like times – on the same page, decided with the same buttons."""

    def test_times_and_expenses_of_a_project_together(self) -> None:
        entry = record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 16), break_minutes=30, submit=True)
        expense = self.spend(kind=ExpenseKind.TRAVEL, amount="49.90", note="Bahn")
        page = self.assert_ok(self.manager.get(reverse("timetracking:approval")))
        self.assertIn("Spesen und Fahrtkosten", page)
        self.assertIn(f'name="expense" value="{expense.pk}" checked', page)
        self.assertIn("kein Beleg", page)
        self.assertIn("49,90 €", page)
        done = self.manager.post(
            reverse("timetracking:decide"),
            {"entry": [entry.pk], "expense": [expense.pk], "decision": "approve"},
            follow=True,
        )
        said = " ".join(self.messages_of(done))
        self.assertIn("1 Zeiteintrag freigegeben", said)
        self.assertIn("1 Spesenposten freigegeben.", said)
        expense.refresh_from_db()
        self.assertEqual(expense.status, TimeEntryStatus.APPROVED)

    def test_expenses_alone_and_sent_back(self) -> None:
        expense = self.spend()
        page = self.assert_ok(self.manager.get(reverse("timetracking:approval")))
        self.assertNotIn("Std.</strong>", page)
        refused = self.manager.post(
            reverse("timetracking:decide"), {"expense": [expense.pk], "decision": "reject", "reason": ""}, follow=True
        )
        self.assertIn("Gib an, warum", " ".join(self.messages_of(refused)))
        self.manager.post(
            reverse("timetracking:decide"), {"expense": [expense.pk], "decision": "reject", "reason": "Beleg fehlt"}
        )
        expense.refresh_from_db()
        self.assertEqual((expense.status, expense.rejection_reason), (TimeEntryStatus.REJECTED, "Beleg fehlt"))
        self.assertTrue(Notification.objects.filter(user=self.anna_user, body="Beleg fehlt").exists())
        own = self.assert_ok(self.crew.get(reverse("timetracking:my_expenses")))
        self.assertIn("Zurückgegeben: Beleg fehlt", own)

    def test_the_filter_by_project_holds_for_expenses(self) -> None:
        self.spend()
        other = make_project("Messe", start=at(14), end=at(16))
        plan(other, self.sound, self.anna, start=at(14, 8), end=at(14, 18))
        record_time(self.anna, other, self.sound, at(14, 8), at(14, 12), submit=True)
        page = self.assert_ok(self.manager.get(reverse("timetracking:approval"), {"project": other.pk}))
        self.assertIn("Messe", page)
        self.assertNotIn("Spesen und Fahrtkosten", page)
        page = self.assert_ok(self.manager.get(reverse("timetracking:approval"), {"project": self.project.pk}))
        self.assertIn("Spesen und Fahrtkosten", page)


class ExpenseReportPageTests(TimesPageCase):
    """ZEI-019: report and CSV per month and person; marked as reimbursed."""

    def setUp(self) -> None:
        super().setUp()
        self.meal = self.spend("14.00")
        self.trip = expenses.create_expense(
            person=self.anna,
            project=self.project,
            kind=ExpenseKind.TRAVEL,
            date=datetime.date(2027, 3, 11),
            kilometres=D("84"),
            rights=self.anna_user.rights,
            user=self.anna_user,
            submit=True,
        )
        expenses.approve_expenses([self.meal, self.trip], rights=self.paula.rights, user=self.paula)
        self.url = reverse("timetracking:expense_report")

    def test_sums_per_month_and_person(self) -> None:
        page = self.assert_ok(self.manager.get(self.url, {"since": "2027-03-01"}))
        for shown in ("März 2027", "Becker, Anna", "39,20 €", "Zu erstatten", "Verpflegung 14,00 €", "Fahrt 25,20 €"):
            self.assertIn(shown, page)
        self.assertIn('aria-current="page">Spesen', page)

    def test_mark_as_reimbursed(self) -> None:
        """ZEI-019: marked as reimbursed; the person is told."""
        page = self.manager.get(self.url, {"since": "2027-03-01"})
        self.assertIn("Angekreuzte als erstattet markieren", self.assert_ok(page))
        done = self.manager.post(
            reverse("timetracking:expense_reimburse"),
            {"expense": [self.meal.pk], "reimbursed_on": "2027-03-27", "query": "since=2027-03-01"},
            follow=True,
        )
        self.assertIn("1 Spesenposten als erstattet markiert.", " ".join(self.messages_of(done)))
        self.meal.refresh_from_db()
        self.assertEqual(self.meal.reimbursed_on, datetime.date(2027, 3, 27))
        self.assertIn("erstattet", self.assert_ok(done))
        self.assertTrue(Notification.objects.filter(user=self.anna_user, title__contains="erstattet").exists())
        outstanding = self.assert_ok(self.manager.get(self.url, {"status": "outstanding"}))
        self.assertNotIn("14,00 €", outstanding.split("Die Spesen")[1])
        # Taken back, it waits again.
        self.manager.post(reverse("timetracking:expense_reopen", args=[self.meal.pk]), {"query": ""})
        self.meal.refresh_from_db()
        self.assertIsNone(self.meal.reimbursed_on)

    def test_csv(self) -> None:
        """ZEI-019: report and CSV per month and person.

        UIX-040: the list is a table of ``core.tables``; its CSV file has all columns.
        """
        response = self.manager.get(self.url, {"since": "2027-03-01", "format": "csv", "cols": "all"})
        self.assertIn("spesen-", response["Content-Disposition"])
        rows = response.content.decode("utf-8-sig").strip().splitlines()
        with translation.override("de"):
            before = expenses.expenses_csv(expenses.expense_report(Expense.objects.all()))
        self.assertEqual(rows, before.lstrip("\ufeff").strip().splitlines())
        self.assertEqual(len(rows), 3)
        self.assertTrue(
            rows[1].startswith(f"03/2027;Becker, Anna;{self.project.number};Stadtfest;10.03.2027;Verpflegung")
        )

    def test_crew_sees_only_her_own_and_marks_nothing(self) -> None:
        kai = make_person("Kai Kurz", rates={"Tontechnik": "30.00"})
        plan(self.project, self.sound, kai, start=at(10, 8), end=at(10, 20))
        expenses.create_expense(
            person=kai,
            project=self.project,
            kind=ExpenseKind.MEALS,
            date=datetime.date(2027, 3, 10),
            amount=D("77.00"),
            rights=self.paula.rights,
            user=self.paula,
        )
        page = self.assert_ok(self.crew.get(self.url, {"since": "2027-03-01"}))
        self.assertIn("39,20 €", page)
        self.assertNotIn("77,00", page)
        self.assertNotIn("als erstattet markieren", page)
        self.assertEqual(
            self.crew.post(reverse("timetracking:expense_reimburse"), {"expense": [self.meal.pk]}).status_code, 403
        )

    def test_the_project_shows_the_costs_and_the_profit(self) -> None:
        """ZEI-019, PRJ-025: in the totals of the planning, for who may see personnel costs."""
        page = self.assert_ok(self.manager.get(reverse("projects:detail", args=[self.project.pk])))
        self.assertIn("Spesen und Fahrtkosten (freigegeben)", page)
        self.assertIn("39,20 €", page)
        self.assertIn(f"{self.url}?project={self.project.pk}", page)
        crew_page = self.crew.get(reverse("projects:deployment", args=[self.project.pk])).content.decode()
        self.assertNotIn("(freigegeben)", crew_page)
