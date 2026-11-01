# SPDX-License-Identifier: GPL-3.0-or-later
"""Through the API, area "times": hints at time entries (ZEI-018), expenses and travel costs (ZEI-019).

Every new operation is called here at least once with success (API-014): ``/expenses`` with its actions, the
receipt, ``/reports/expenses`` and its CSV file; the ``hints`` of the time entries and the new settings.
"""

from __future__ import annotations

import datetime
from decimal import Decimal as D  # noqa: N817

from rentalars.notifications.models import Kind, Notification
from rentalars.timetracking import expenses
from rentalars.timetracking.models import Expense, ExpenseKind, TimeEntryStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import LATER, at, job_function, make_person, make_project, make_user, plan, record_time, set_clock
from tests.unit.test_080_times import PDF, MediaMixin, picture, upload

EXPENSES = f"{API}/expenses"


class TimesApiCase(MediaMixin, ApiTestCase):
    """Anna (crew) is planned on the Stadtfest; Paula manages projects. Late March 2027."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", start=at(10), end=at(12))
        self.sound = job_function("Tontechnik", price="45.00")
        self.anna_user = make_user("anna", roles=("Crew",))
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"}, user=self.anna_user)
        plan(self.project, self.sound, self.anna, start=at(9, 6), end=at(12, 23))
        self.crew = self.client_of(self.anna_user)
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.manager = self.client_of(self.paula)
        set_clock(LATER)

    def spend(self, amount: str = "14.00", **more) -> Expense:
        values = {"kind": ExpenseKind.MEALS, "date": datetime.date(2027, 3, 10), "project": self.project, **more}
        return expenses.create_expense(
            person=self.anna, amount=D(amount), rights=self.anna_user.rights, user=self.anna_user, **values
        )


class TimeEntryHintApiTests(TimesApiCase):
    """ZEI-018: every time entry of the API names its hints."""

    def test_recording_answers_with_the_hints(self) -> None:
        """ZEI-018: the hint is shown when entering – also in the app; it never blocks."""
        created = self.crew.post(
            f"{API}/time-entries",
            {
                "project": self.project.pk,
                "job_function": self.sound.pk,
                "start": "2027-03-10T07:00:00+01:00",
                "end": "2027-03-10T19:30:00+01:00",
                "break_minutes": 45,
                "submit": True,
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(
            created.json()["hints"],
            [{"kind": "long_day", "message": "Langer Arbeitstag: 11,75 Stunden Arbeit (mehr als 10)."}],
        )
        self.assertEqual(created.json()["status"], "submitted")

    def test_list_report_and_single_entry_carry_the_hints(self) -> None:
        record_time(self.anna, self.project, self.sound, at(10, 14), at(10, 23), break_minutes=45, submit=True)
        morning = record_time(self.anna, self.project, self.sound, at(11, 7), at(11, 12), submit=True)
        listed = {entry["id"]: entry["hints"] for entry in self.manager.get(f"{API}/time-entries").json()["results"]}
        self.assertEqual(listed[morning.pk][0]["kind"], "short_rest")
        self.assertEqual(self.manager.get(f"{API}/time-entries/{morning.pk}").json()["hints"][0]["kind"], "short_rest")
        report = self.manager.get(f"{API}/reports/hours", {"from": "2027-03-01"}).json()
        self.assertEqual([entry["hints"] != [] for entry in report["entries"]], [False, True])
        csv = self.manager.get(f"{API}/reports/hours/csv", {"from": "2027-03-01"}).content.decode("utf-8-sig")
        self.assertIn("Kurze Ruhezeit: 8 Stunden", csv)

    def test_the_limits_and_the_rate_are_settings_of_the_api(self) -> None:
        """ZEI-018, ZEI-019."""
        system = self.admin.get(f"{API}/settings").json()["system"]
        self.assertEqual(
            {name: system[name] for name in ("time_hint_day_hours", "time_hint_rest_hours", "expense_km_rate")},
            {"time_hint_day_hours": "10.0", "time_hint_rest_hours": "11.0", "expense_km_rate": "0.30"},
        )
        changed = self.admin.patch(f"{API}/settings", {"system": {"time_hint_break_minutes": 20}}, format="json")
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertEqual(changed.json()["system"]["time_hint_break_minutes"], 20)


class ExpenseApiTests(TimesApiCase):
    """ZEI-019: record, read, change, delete – JSON or with a receipt as multipart."""

    def test_record_a_meal_with_a_photo(self) -> None:
        created = self.crew.post(
            EXPENSES,
            {
                "project": self.project.pk,
                "kind": "meals",
                "date": "2027-03-10",
                "amount": "14.50",
                "note": "Mittag",
                "submit": "true",
                "receipt": upload("beleg.jpg", picture(900, 600)),
            },
            format="multipart",
        )
        self.assertEqual(created.status_code, 201, created.data)
        expense = created.json()
        self.assertEqual(
            (expense["person"], expense["amount"], expense["status"], expense["has_receipt"]),
            (self.anna.pk, "14.50", "submitted", True),
        )
        receipt = self.crew.get(expense["receipt_url"])
        self.assertEqual(receipt.status_code, 200)
        self.assertTrue(b"".join(receipt.streaming_content).startswith(b"\xff\xd8"))  # a JPEG

    def test_a_trip_by_kilometre_in_json(self) -> None:
        created = self.crew.post(
            EXPENSES,
            {"project": self.project.pk, "kind": "travel", "date": "2027-03-10", "kilometres": "84"},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual((created.json()["km_rate"], created.json()["amount"]), ("0.30", "25.20"))

    def test_mistakes_are_explained(self) -> None:
        """API-008: the uniform error format, the field named."""
        future = self.crew.post(
            EXPENSES, {"project": self.project.pk, "kind": "meals", "date": "2027-04-30", "amount": "5"}, format="json"
        )
        self.assert_error(future, 400, "validation_error", "date")
        bad = self.crew.post(
            EXPENSES,
            {
                "project": self.project.pk,
                "kind": "meals",
                "date": "2027-03-10",
                "amount": "5",
                "receipt": upload("x.jpg", b"nope"),
            },
            format="multipart",
        )
        self.assert_error(bad, 400, "validation_error", "receipt")

    def test_read_change_and_delete(self) -> None:
        expense = self.spend()
        address = f"{EXPENSES}/{expense.pk}"
        self.assertEqual(self.crew.get(address).json()["amount"], "14.00")
        self.assertEqual(self.crew.get(EXPENSES, {"kind": "meals"}).json()["count"], 1)
        self.assertEqual(self.crew.get(EXPENSES, {"kind": "travel"}).json()["count"], 0)
        patched = self.crew.patch(
            address, {"receipt": upload("hotel.pdf", PDF, "application/pdf"), "note": "Hotel"}, format="multipart"
        )
        self.assertEqual(patched.status_code, 200, patched.data)
        self.assertEqual((patched.json()["note"], patched.json()["has_receipt"]), ("Hotel", True))
        put = self.crew.put(
            address,
            {"project": self.project.pk, "kind": "parking", "date": "2027-03-11", "amount": "6.00", "submit": True},
            format="json",
        )
        self.assertEqual(put.status_code, 200, put.data)
        self.assertEqual((put.json()["kind"], put.json()["status"]), ("parking", "submitted"))
        self.assertEqual(self.crew.delete(address).status_code, 204)
        self.assertFalse(Expense.objects.exists())

    def test_others_see_nothing_of_it(self) -> None:
        expense = self.spend()
        kai = self.client_for("kai", "Crew")
        self.assertEqual(kai.get(EXPENSES).json()["count"], 0)
        self.assertEqual(kai.get(f"{EXPENSES}/{expense.pk}").status_code, 404)
        self.assertEqual(kai.get(f"{EXPENSES}/{expense.pk}/receipt").status_code, 404)


class ExpenseApprovalApiTests(TimesApiCase):
    """ZEI-019: submit, approve, send back, reimburse, take back."""

    def test_the_whole_way(self) -> None:
        expense = self.spend()
        ids = {"ids": [expense.pk]}
        self.assertEqual(self.crew.post(f"{EXPENSES}/submit", ids, format="json").json(), {"changed": 1})
        self.assertEqual(self.crew.post(f"{EXPENSES}/approve", ids, format="json").status_code, 403)
        self.assertEqual(self.manager.post(f"{EXPENSES}/approve", ids, format="json").json(), {"changed": 1})
        reimbursed = self.manager.post(f"{EXPENSES}/reimburse", {**ids, "date": "2027-03-27"}, format="json")
        self.assertEqual(reimbursed.json(), {"changed": 1})
        document = self.manager.get(f"{EXPENSES}/{expense.pk}").json()
        self.assertEqual((document["is_reimbursed"], document["reimbursed_on"]), (True, "2027-03-27"))
        self.assertTrue(Notification.objects.filter(user=self.anna_user, kind=Kind.EXPENSE).exists())
        self.assertEqual(self.manager.get(EXPENSES, {"status": "reimbursed"}).json()["count"], 1)
        refused = self.manager.post(f"{EXPENSES}/{expense.pk}/reopen", format="json")
        self.assert_error(refused, 400, "validation_error")
        taken_back = self.manager.post(f"{EXPENSES}/{expense.pk}/take-back-reimbursement", format="json")
        self.assertEqual(taken_back.json()["is_reimbursed"], False)
        self.assertEqual(self.manager.get(EXPENSES, {"status": "outstanding"}).json()["count"], 1)
        reopened = self.manager.post(f"{EXPENSES}/{expense.pk}/reopen", format="json")
        self.assertEqual(reopened.json()["status"], "submitted")

    def test_send_back_with_a_reason(self) -> None:
        expense = self.spend(submit=True)
        without = self.manager.post(f"{EXPENSES}/reject", {"ids": [expense.pk], "reason": ""}, format="json")
        self.assert_error(without, 400, "validation_error", "reason")
        sent_back = self.manager.post(
            f"{EXPENSES}/reject", {"ids": [expense.pk], "reason": "Beleg fehlt"}, format="json"
        )
        self.assertEqual(sent_back.json(), {"changed": 1})
        self.assertEqual(self.crew.get(f"{EXPENSES}/{expense.pk}").json()["rejection_reason"], "Beleg fehlt")

    def test_ids_must_be_a_list_of_numbers(self) -> None:
        self.assert_error(
            self.manager.post(f"{EXPENSES}/approve", {"ids": "1"}, format="json"), 400, "validation_error", "ids"
        )


class ExpenseReportApiTests(TimesApiCase):
    """ZEI-019: per month and person, with sums; as CSV."""

    def test_report_and_csv(self) -> None:
        meal = self.spend("14.00", submit=True)
        self.spend("6.00", kind=ExpenseKind.PARKING, date=datetime.date(2027, 2, 26), submit=True)
        expenses.approve_expenses([meal], rights=self.paula.rights, user=self.paula)
        report = self.manager.get(f"{API}/reports/expenses").json()
        self.assertEqual(
            [(row["month"], row["person_name"], row["total"], row["outstanding"]) for row in report["rows"]],
            [("2027-02", "Anna Becker", "6.00", "0.00"), ("2027-03", "Anna Becker", "14.00", "14.00")],
        )
        self.assertEqual(report["total"], "20.00")
        self.assertEqual(len(report["expenses"]), 2)
        march = self.manager.get(f"{API}/reports/expenses", {"from": "2027-03-01", "to": "2027-03-31"}).json()
        self.assertEqual(march["total"], "14.00")
        csv = self.manager.get(f"{API}/reports/expenses/csv", {"status": "approved"})
        self.assertIn("Spesen.csv", csv["Content-Disposition"])
        rows = csv.content.decode("utf-8-sig").strip().splitlines()
        self.assertEqual(len(rows), 2)
        self.assertIn(";Verpflegung;;;;14,00;", rows[1])  # The column of the way to work (ZEI-027)

    def test_the_project_names_its_expenses_as_costs(self) -> None:
        """ZEI-019, PRJ-025: the totals of the planning in the API."""
        meal = self.spend("30.00", submit=True)
        expenses.approve_expenses([meal], rights=self.paula.rights, user=self.paula)
        totals = self.manager.get(f"{API}/projects/{self.project.pk}/planning").json()["totals"]
        self.assertEqual(totals["expenses_cost"], "30.00")
        self.assertNotIn(
            "expenses_cost",
            self.client_for("lager", "Lager")
            .get(f"{API}/projects/{self.project.pk}/planning")
            .json()
            .get("totals", {}),
        )
        self.assertEqual(TimeEntryStatus.APPROVED, meal.status)
