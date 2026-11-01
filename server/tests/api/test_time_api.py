# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests: time entries, stopwatch, approval, hours report (chapter 5.9)."""

from __future__ import annotations

import datetime

from rentalars.accounts.models import Role
from rentalars.core.models import AuditLogEntry
from rentalars.timetracking.models import TimeEntry
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    LATER,
    NOW,
    at,
    job_function,
    make_internal_project,
    make_person,
    make_project,
    make_user,
    plan,
    record_time,
    set_clock,
)

ENTRIES = f"{API}/time-entries"


class TimeApiTestCase(ApiTestCase):
    """Anna (crew) is planned as sound engineer on the Stadtfest; Paula manages projects."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", start=at(10), end=at(12))
        self.sound = job_function("Tontechnik", price="45.00")
        self.hand = job_function("Stagehand", price="28.00")
        self.anna_user = make_user("anna", roles=("Crew",))
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00", "Stagehand": "20.00"}, user=self.anna_user)
        self.line = plan(self.project, self.sound, self.anna, start=at(10, 8), end=at(10, 20))
        self.crew = self.client_of(self.anna_user)
        self.manager = self.client_for("paula", "Projektleitung")
        # The tests record the hours of 10 March afterwards (ZEI-022).
        set_clock(LATER)

    def body(self, begin: str, end: str | None, **more: object) -> dict[str, object]:
        """A time entry on the Stadtfest as sound engineer; ``begin`` and ``end`` as "10T08:00"."""
        body: dict[str, object] = {
            "project": self.project.pk,
            "job_function": self.sound.pk,
            "start": f"2027-03-{begin}:00+01:00",
            **more,
        }
        if end is not None:
            body["end"] = f"2027-03-{end}:00+01:00"
        return body


class RecordingApiTests(TimeApiTestCase):
    """ZEI-002, ZEI-004, ZEI-007 to ZEI-009."""

    def test_record_read_change_and_delete_an_entry(self) -> None:
        created = self.crew.post(
            ENTRIES, self.body("10T08:00", "10T16:30", break_minutes=30, note="Aufbau FOH"), format="json"
        )
        self.assertEqual(created.status_code, 201, created.data)
        entry = created.json()
        self.assertEqual(
            (entry["person"], entry["person_name"]), (self.anna.pk, "Anna Becker")
        )  # the caller's own person
        self.assertEqual((entry["hours"], entry["status"], entry["crew_line"]), ("8.00", "recorded", self.line.pk))
        self.assertEqual((entry["hourly_rate"], entry["amount"]), ("35.00", "280.00"))  # ZEI-008, PER-010
        address = f"{ENTRIES}/{entry['id']}"

        self.assertEqual(self.crew.get(address).json()["note"], "Aufbau FOH")
        changed = self.crew.patch(address, {"end": "2027-03-10T17:30:00+01:00"}, format="json").json()
        self.assertEqual(changed["hours"], "9.00")
        replaced = self.crew.put(
            address, self.body("10T09:00", "10T12:00", job_function=self.hand.pk, break_minutes=0), format="json"
        ).json()
        self.assertEqual(
            (replaced["hours"], replaced["hourly_rate"], replaced["job_function_name"]), ("3.00", "20.00", "Stagehand")
        )
        self.assertEqual(self.crew.delete(address).status_code, 204)
        self.assertEqual(TimeEntry.objects.count(), 0)
        # ZEI-014: creating, changing and deleting are in the change log, with who did it.
        log = AuditLogEntry.objects.filter(content_type__model="timeentry", object_id=str(entry["id"]))
        self.assertEqual(sorted(row.action for row in log), ["created", "deleted", "updated", "updated"])
        self.assertEqual({row.actor for row in log}, {self.anna_user})

    def test_overlapping_entry_is_refused(self) -> None:
        """Acceptance scenario 5."""
        self.assertEqual(self.crew.post(ENTRIES, self.body("10T08:00", "10T12:00"), format="json").status_code, 201)
        self.assert_error(
            self.crew.post(ENTRIES, self.body("10T11:00", "10T13:00"), format="json"), 400, "validation_error", "start"
        )
        self.assertEqual(self.crew.post(ENTRIES, self.body("10T12:00", "10T13:00"), format="json").status_code, 201)

    def test_end_before_start_and_too_long_entries_are_refused(self) -> None:
        self.assert_error(
            self.crew.post(ENTRIES, self.body("10T12:00", "10T08:00"), format="json"), 400, "validation_error", "end"
        )
        self.assert_error(
            self.crew.post(ENTRIES, self.body("10T08:00", "11T09:00"), format="json"), 400, "validation_error", "end"
        )
        over_midnight = self.crew.post(ENTRIES, self.body("10T22:00", "11T02:15"), format="json")
        self.assertEqual(over_midnight.json()["hours"], "4.25")

    def test_only_job_functions_of_the_person_can_be_booked(self) -> None:
        """ZEI-007."""
        rigging = job_function("Rigging")
        response = self.crew.post(ENTRIES, self.body("10T08:00", "10T12:00", job_function=rigging.pk), format="json")
        self.assert_error(response, 400, "validation_error", "job_function")

    def test_crew_cannot_book_on_projects_they_are_not_planned_in(self) -> None:
        other = make_project("Jazznacht")
        response = self.crew.post(ENTRIES, self.body("10T08:00", "10T12:00", project=other.pk), format="json")
        self.assert_error(response, 400, "validation_error", "project")

    def test_internal_projects_take_times_of_everybody(self) -> None:
        """ZEI-010."""
        warehouse = make_internal_project()
        body = {
            "project": warehouse.pk,
            "job_function": self.hand.pk,
            "start": (NOW - datetime.timedelta(hours=4)).isoformat(),
            "end": NOW.isoformat(),
        }
        created = self.crew.post(ENTRIES, body, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual((created.json()["hours"], created.json()["crew_line"]), ("4.00", None))

    def test_recording_for_others_needs_the_right(self) -> None:
        """ZEI-011."""
        kai_user = make_user("kai", roles=("Crew",))
        kai = make_person("Kai Kurz", rates={"Stagehand": "18.00"}, user=kai_user)
        plan(self.project, self.hand, kai)
        body = self.body("10T08:00", "10T12:00", person=kai.pk, job_function=self.hand.pk)
        self.assert_error(self.crew.post(ENTRIES, body, format="json"), 403, "permission_denied")
        created = self.manager.post(ENTRIES, body, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.json()["person_name"], "Kai Kurz")

    def test_without_person_the_entry_is_the_callers_own(self) -> None:
        """AUT-026: every account is a person – the manager would record for herself, without the function.

        ZEI-007: the job functions of the project's crew may be booked by everybody who books on the
        project, so "Tontechnik" of Anna's crew line would be taken now. "Stagehand" is Anna's own job function,
        but neither the manager's nor one of the project's crew: refused, the entry is the manager's.
        """
        response = self.manager.post(
            ENTRIES, self.body("10T08:00", "10T12:00", job_function=self.hand.pk), format="json"
        )
        self.assert_error(response, 400, "validation_error", "job_function")

    def test_the_person_of_an_entry_cannot_be_changed(self) -> None:
        entry = record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 12))
        kai = make_person("Kai Kurz", rates={"Tontechnik": "30.00"})
        response = self.manager.patch(f"{ENTRIES}/{entry.pk}", {"person": kai.pk}, format="json")
        self.assert_error(response, 400, "validation_error", "person")

    def test_time_tracking_needs_the_module(self) -> None:
        """NFA-010."""
        warehouse = self.client_for("luka", "Lager")
        self.assert_error(warehouse.get(ENTRIES), 403, "permission_denied")
        self.assert_error(
            warehouse.post(ENTRIES, self.body("10T08:00", "10T12:00"), format="json"), 403, "permission_denied"
        )
        self.assert_error(warehouse.get(f"{API}/reports/hours"), 403, "permission_denied")
        reader = make_user("rita", roles=("Nur-Lesen",))
        make_person("Rita Reader", rates={"Tontechnik": "30.00"}, user=reader)
        self.assert_error(
            self.client_of(reader).post(ENTRIES, self.body("10T08:00", "10T12:00"), format="json"),
            403,
            "permission_denied",
        )


class VisibilityApiTests(TimeApiTestCase):
    """ZEI-016, NFA-010, AUT-019."""

    def setUp(self) -> None:
        super().setUp()
        self.kai_user = make_user("kai", roles=("Crew",))
        self.kai = make_person("Kai Kurz", rates={"Stagehand": "18.00"}, user=self.kai_user)
        plan(self.project, self.hand, self.kai)
        self.own = record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 12), submit=True)
        self.others = record_time(self.kai, self.project, self.hand, at(10, 8), at(10, 14), submit=True)

    def test_everybody_sees_their_own_entries(self) -> None:
        listed = self.crew.get(ENTRIES).json()["results"]
        self.assertEqual([row["id"] for row in listed], [self.own.pk])
        self.assertEqual(self.crew.get(f"{ENTRIES}/{self.others.pk}").status_code, 404)
        self.assertEqual(self.crew.patch(f"{ENTRIES}/{self.others.pk}", {"note": "x"}, format="json").status_code, 404)
        self.assertEqual(self.crew.delete(f"{ENTRIES}/{self.others.pk}").status_code, 404)

    def test_with_the_approval_right_all_entries_of_visible_projects_are_listed(self) -> None:
        listed = self.manager.get(ENTRIES).json()["results"]
        self.assertEqual({row["id"] for row in listed}, {self.own.pk, self.others.pk})
        self.assertTrue(all("hourly_rate" in row for row in listed))

    def test_filters(self) -> None:
        record_time(self.anna, self.project, self.hand, at(11, 8), at(11, 10))
        ids = lambda **query: [row["id"] for row in self.manager.get(ENTRIES, query).json()["results"]]  # noqa: E731
        self.assertEqual(ids(person=self.kai.pk), [self.others.pk])
        self.assertEqual(len(ids(job_function=self.hand.pk)), 2)
        self.assertEqual(len(ids(status="recorded")), 1)
        self.assertEqual(len(ids(project=self.project.pk)), 3)
        self.assertEqual(len(ids(**{"from": "2027-03-11"})), 1)
        self.assertEqual(len(ids(to="2027-03-10")), 2)

    def test_approver_without_cost_right_sees_hours_but_no_rates_of_others(self) -> None:
        """AUT-019."""
        Role.objects.create(
            name="Crewchef", module_levels={"projects": 1, "time_tracking": 2}, special_rights=["approve_times"]
        )
        chief = self.client_for("chris", "Crewchef")
        listed = chief.get(ENTRIES).json()["results"]
        self.assertEqual(len(listed), 2)
        self.assertTrue(all("hourly_rate" not in row and "amount" not in row for row in listed))

    def test_own_rate_is_hidden_when_switched_off(self) -> None:
        """PER-010."""
        self.assertIn("hourly_rate", self.crew.get(f"{ENTRIES}/{self.own.pk}").json())
        self.admin.patch(f"{API}/settings", {"system": {"people_see_own_rates": False}}, format="json")
        self.assertNotIn("hourly_rate", self.crew.get(f"{ENTRIES}/{self.own.pk}").json())


class StopwatchApiTests(TimeApiTestCase):
    """ZEI-005."""

    def test_start_look_and_stop(self) -> None:
        self.assertIsNone(self.crew.get(f"{ENTRIES}/timer").json()["running"])
        started = self.crew.post(
            f"{ENTRIES}/timer/start", {"project": self.project.pk, "job_function": self.sound.pk}, format="json"
        )
        self.assertEqual(started.status_code, 201, started.data)
        self.assertTrue(started.json()["is_running"])
        self.assertEqual(self.crew.get(f"{ENTRIES}/timer").json()["running"]["id"], started.json()["id"])

        # A second stopwatch cannot be started while one is running.
        again = self.crew.post(
            f"{ENTRIES}/timer/start", {"project": self.project.pk, "job_function": self.sound.pk}, format="json"
        )
        self.assert_error(again, 400, "validation_error")

        TimeEntry.objects.update(start=LATER - datetime.timedelta(hours=2, minutes=30))
        stopped = self.crew.post(f"{ENTRIES}/timer/stop", {"break_minutes": 30, "submit": True}, format="json")
        self.assertEqual(stopped.status_code, 200, stopped.data)
        self.assertEqual(
            (stopped.json()["hours"], stopped.json()["status"], stopped.json()["is_running"]),
            ("2.00", "submitted", False),
        )
        self.assert_error(self.crew.post(f"{ENTRIES}/timer/stop", {}, format="json"), 400, "validation_error")

    def test_the_stopwatch_of_somebody_else_needs_the_right(self) -> None:
        body = {"project": self.project.pk, "job_function": self.sound.pk, "person": self.anna.pk}
        kai_user = make_user("kai", roles=("Crew",))
        make_person("Kai Kurz", user=kai_user)
        self.assert_error(
            self.client_of(kai_user).post(f"{ENTRIES}/timer/start", body, format="json"), 403, "permission_denied"
        )
        self.assertEqual(self.manager.post(f"{ENTRIES}/timer/start", body, format="json").status_code, 201)
        self.assertEqual(
            self.manager.post(f"{ENTRIES}/timer/stop", {"person": self.anna.pk}, format="json").status_code, 200
        )


class ApprovalApiTests(TimeApiTestCase):
    """ZEI-012, ZEI-013."""

    def test_hand_in_approve_and_lock(self) -> None:
        entry = self.crew.post(ENTRIES, self.body("10T08:00", "10T12:00"), format="json").json()
        self.assertEqual(
            self.crew.post(f"{ENTRIES}/submit", {"ids": [entry["id"]]}, format="json").json(), {"changed": 1}
        )
        self.assertEqual(self.crew.get(f"{ENTRIES}/{entry['id']}").json()["status"], "submitted")

        self.assert_error(
            self.crew.post(f"{ENTRIES}/approve", {"ids": [entry["id"]]}, format="json"), 403, "permission_denied"
        )
        self.assertEqual(
            self.manager.post(f"{ENTRIES}/approve", {"ids": [entry["id"]]}, format="json").json(), {"changed": 1}
        )
        approved = self.crew.get(f"{ENTRIES}/{entry['id']}").json()
        self.assertEqual(approved["status"], "approved")
        self.assertIsNotNone(approved["decided_at"])

        # Locked: neither the person nor the manager changes or deletes it.
        for client in (self.crew, self.manager):
            self.assert_error(
                client.patch(f"{ENTRIES}/{entry['id']}", {"note": "x"}, format="json"), 400, "validation_error"
            )
            self.assert_error(client.delete(f"{ENTRIES}/{entry['id']}"), 400, "validation_error")

    def test_an_entry_can_be_handed_in_while_recording(self) -> None:
        created = self.crew.post(ENTRIES, self.body("10T08:00", "10T12:00", submit=True), format="json")
        self.assertEqual(created.json()["status"], "submitted")

    def test_approve_all_submitted_entries_of_a_project_and_period(self) -> None:
        """ZEI-013: collected per project or period."""
        record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 12), submit=True)
        record_time(self.anna, self.project, self.sound, at(11, 8), at(11, 12), submit=True)
        record_time(self.anna, self.project, self.sound, at(11, 13), at(11, 14))  # not handed in
        first_day = self.manager.post(
            f"{ENTRIES}/approve", {"project": self.project.pk, "from": "2027-03-10", "to": "2027-03-10"}, format="json"
        )
        self.assertEqual(first_day.json(), {"changed": 1})
        self.assertEqual(
            self.manager.post(f"{ENTRIES}/approve", {"project": self.project.pk}, format="json").json(), {"changed": 1}
        )
        self.assertEqual(TimeEntry.objects.filter(status="approved").count(), 2)
        self.assertEqual(TimeEntry.objects.filter(status="recorded").count(), 1)

    def test_reject_with_reason_and_hand_in_again(self) -> None:
        entry = record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 12), submit=True)
        self.assert_error(
            self.manager.post(f"{ENTRIES}/reject", {"ids": [entry.pk]}, format="json"),
            400,
            "validation_error",
            "reason",
        )
        rejected = self.manager.post(
            f"{ENTRIES}/reject", {"ids": [entry.pk], "reason": "Ende war 11 Uhr"}, format="json"
        )
        self.assertEqual(rejected.json(), {"changed": 1})
        seen = self.crew.get(f"{ENTRIES}/{entry.pk}").json()
        self.assertEqual((seen["status"], seen["rejection_reason"]), ("rejected", "Ende war 11 Uhr"))

        corrected = self.crew.patch(
            f"{ENTRIES}/{entry.pk}", {"end": "2027-03-10T11:00:00+01:00", "submit": True}, format="json"
        ).json()
        self.assertEqual(
            (corrected["status"], corrected["hours"], corrected["rejection_reason"]), ("submitted", "3.00", "")
        )

    def test_take_back_an_approval(self) -> None:
        entry = record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 12), approve=True)
        self.assert_error(self.crew.post(f"{ENTRIES}/{entry.pk}/reopen"), 403, "permission_denied")
        reopened = self.manager.post(f"{ENTRIES}/{entry.pk}/reopen")
        self.assertEqual(reopened.status_code, 200, reopened.data)
        self.assertEqual(reopened.json()["status"], "submitted")
        self.assertEqual(
            self.crew.patch(f"{ENTRIES}/{entry.pk}", {"note": "korrigiert"}, format="json").status_code, 200
        )

    def test_the_choice_of_entries_must_be_named(self) -> None:
        self.assert_error(self.manager.post(f"{ENTRIES}/approve", {}, format="json"), 400, "validation_error", "ids")
        self.assert_error(
            self.manager.post(f"{ENTRIES}/approve", {"ids": "alle"}, format="json"), 400, "validation_error", "ids"
        )

    def test_entries_of_invisible_projects_are_not_approved(self) -> None:
        """A crew chief limited to assigned projects approves only there."""
        Role.objects.create(
            name="Crewchef",
            module_levels={"projects": 1, "time_tracking": 2},
            special_rights=["approve_times"],
            project_scope="assigned",
        )
        chief = self.client_for("chris", "Crewchef")
        entry = record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 12), submit=True)
        self.assertEqual(chief.post(f"{ENTRIES}/approve", {"ids": [entry.pk]}, format="json").json(), {"changed": 0})
        self.assertEqual(
            chief.post(f"{ENTRIES}/approve", {"project": self.project.pk}, format="json").json(), {"changed": 0}
        )
        self.assertEqual(TimeEntry.objects.get(pk=entry.pk).status, "submitted")


class ChoicesApiTests(TimeApiTestCase):
    """ZEI-006, ZEI-007: what the entry form offers."""

    def test_current_project_first_with_the_function_of_the_crew_line(self) -> None:
        make_internal_project("Lager")
        make_project("Jazznacht")
        choices = self.crew.get(f"{ENTRIES}/choices").json()
        self.assertEqual(
            [(row["name"], row["reason"]) for row in choices],
            [("Stadtfest", "planned"), ("Lager", "internal"), (None, "without_project")],
        )
        # Without project only her own job functions (ZEI-023).
        self.assertEqual([function["name"] for function in choices[-1]["job_functions"]], ["Stagehand", "Tontechnik"])
        self.assertEqual(choices[0]["suggested_job_function"], self.sound.pk)
        self.assertEqual([function["name"] for function in choices[0]["job_functions"]], ["Stagehand", "Tontechnik"])

    def test_choices_of_somebody_else_need_the_right(self) -> None:
        self.assertEqual(
            self.manager.get(f"{ENTRIES}/choices", {"person": self.anna.pk}).json()[0]["name"], "Stadtfest"
        )
        kai_user = make_user("kai", roles=("Crew",))
        make_person("Kai Kurz", user=kai_user)
        self.assert_error(
            self.client_of(kai_user).get(f"{ENTRIES}/choices", {"person": self.anna.pk}), 403, "permission_denied"
        )


class HoursReportApiTests(TimeApiTestCase):
    """ZEI-015 to ZEI-017."""

    def setUp(self) -> None:
        super().setUp()
        self.kai = make_person("Kai Kurz", rates={"Stagehand": "18.00"})
        plan(self.project, self.hand, self.kai)
        record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 16), approve=True)
        record_time(self.anna, self.project, self.hand, at(11, 8), at(11, 12), submit=True)
        record_time(self.kai, self.project, self.hand, at(10, 8), at(10, 14), approve=True)
        rejected = record_time(self.kai, self.project, self.hand, at(11, 8), at(11, 9), submit=True)
        self.manager.post(f"{ENTRIES}/reject", {"ids": [rejected.pk], "reason": "doppelt"}, format="json")
        self.address = f"{API}/reports/hours"

    def test_sums_by_person_with_amounts(self) -> None:
        report = self.manager.get(self.address).json()
        self.assertEqual(report["group_by"], "person")
        self.assertEqual(
            [(row["label"], row["hours"], row["amount"]) for row in report["rows"]],
            [("Becker, Anna", "12.00", "360.00"), ("Kurz, Kai", "6.00", "108.00")],
        )
        self.assertEqual((report["total_hours"], report["total_amount"]), ("18.00", "468.00"))
        self.assertEqual(len(report["entries"]), 3)  # the rejected one is left out

    def test_grouping_and_filters(self) -> None:
        by_function = self.manager.get(self.address, {"group_by": "job_function"}).json()
        self.assertEqual(
            [(row["label"], row["hours"]) for row in by_function["rows"]],
            [("Stagehand", "10.00"), ("Tontechnik", "8.00")],
        )
        by_day = self.manager.get(self.address, {"group_by": "day", "person": self.anna.pk}).json()
        self.assertEqual(
            [(row["label"], row["hours"]) for row in by_day["rows"]], [("10.03.2027", "8.00"), ("11.03.2027", "4.00")]
        )
        approved = self.manager.get(
            self.address, {"status": "approved", "from": "2027-03-10", "to": "2027-03-10"}
        ).json()
        self.assertEqual(approved["total_hours"], "14.00")
        self.assertEqual(self.manager.get(self.address, {"status": "rejected"}).json()["total_hours"], "1.00")
        self.assertEqual(self.manager.get(self.address, {"project": 999}).json()["total_hours"], "0.00")

    def test_everybody_gets_the_report_of_their_own_times(self) -> None:
        """ZEI-016."""
        report = self.crew.get(self.address, {"person": self.kai.pk}).json()
        self.assertEqual(report["rows"], [])  # Kai's times are not Anna's to see
        own = self.crew.get(self.address).json()
        self.assertEqual((own["total_hours"], own["total_amount"]), ("12.00", "360.00"))

    def test_timesheet_as_pdf(self) -> None:
        """ZEI-017."""
        response = self.manager.get(
            f"{self.address}/pdf", {"person": self.anna.pk, "from": "2027-03-01", "to": "2027-03-31"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_a_timesheet_with_too_many_entries_is_refused(self) -> None:
        """Laying out hundreds of pages would keep the server busy past its time limit."""
        from unittest import mock

        with mock.patch("rentalars.timetracking.pdf.MAX_TIMESHEET_ENTRIES", 1):
            response = self.manager.get(f"{self.address}/pdf", {"from": "2027-03-01", "to": "2027-03-31"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("eingrenzen", response.json()["detail"])

    def test_entries_as_csv_for_a_spreadsheet(self) -> None:
        """ZEI-017: semicolons, decimal commas, one row per entry."""
        response = self.manager.get(f"{self.address}/csv", {"person": self.anna.pk})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/csv"))
        rows = response.content.decode("utf-8-sig").strip().splitlines()
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows[0].startswith("Person;Projektnummer;Projekt;Funktion;Tag;Beginn;Ende;Pause"))
        self.assertIn("Becker, Anna;", rows[1])
        self.assertIn(";10.03.2027;08:00;16:00;0;8;freigegeben;35,00;280,00;", rows[1])

    def test_csv_leaves_out_rates_the_reader_may_not_see(self) -> None:
        """AUT-019."""
        Role.objects.create(
            name="Crewchef", module_levels={"projects": 1, "time_tracking": 2}, special_rights=["approve_times"]
        )
        text = self.client_for("chris", "Crewchef").get(f"{self.address}/csv").content.decode("utf-8-sig")
        self.assertIn("Kurz, Kai", text)
        self.assertNotIn("18,00", text)
        self.assertNotIn("35,00", text)


class FutureAndWithoutProjectApiTests(TimeApiTestCase):
    """ZEI-022 and ZEI-023 through the API."""

    def test_future_times_are_refused(self) -> None:
        response = self.crew.post(
            ENTRIES,
            {
                "project": self.project.pk,
                "job_function": self.sound.pk,
                "start": (LATER - datetime.timedelta(hours=1)).isoformat(),
                "end": (LATER + datetime.timedelta(hours=1)).isoformat(),
            },
            format="json",
        )
        self.assert_error(response, 400, "validation_error", "end")

    def test_record_without_project_assign_it_and_approve(self) -> None:
        created = self.crew.post(ENTRIES, self.body("10T08:00", "10T12:00", project=None, submit=True), format="json")
        self.assertEqual(created.status_code, 201, created.data)
        entry = created.json()
        self.assertEqual((entry["project"], entry["project_number"], entry["crew_line"]), (None, None, None))
        self.assertEqual(
            [row["id"] for row in self.crew.get(ENTRIES, {"project": "none"}).json()["results"]], [entry["id"]]
        )

        refused = self.manager.post(f"{ENTRIES}/approve", {"ids": [entry["id"]]}, format="json")
        self.assert_error(refused, 400, "validation_error", "project")

        assigned = self.manager.post(
            f"{ENTRIES}/{entry['id']}/assign-project", {"project": self.project.pk}, format="json"
        )
        self.assertEqual(assigned.status_code, 200, assigned.data)
        self.assertEqual((assigned.json()["project"], assigned.json()["crew_line"]), (self.project.pk, self.line.pk))
        self.assertEqual(
            self.manager.post(f"{ENTRIES}/approve", {"ids": [entry["id"]]}, format="json").json(), {"changed": 1}
        )

    def test_assigning_a_project_the_person_is_not_planned_in_is_refused(self) -> None:
        entry = record_time(self.anna, None, self.sound, at(10, 8), at(10, 12))
        other = make_project("Jazznacht")
        response = self.crew.post(f"{ENTRIES}/{entry.pk}/assign-project", {"project": other.pk}, format="json")
        self.assert_error(response, 400, "validation_error", "project")

    def test_the_stopwatch_starts_without_project(self) -> None:
        started = self.crew.post(f"{ENTRIES}/timer/start", {"job_function": self.sound.pk}, format="json")
        self.assertEqual(started.status_code, 201, started.data)
        self.assertIsNone(started.json()["project"])

    def test_report_and_csv_name_it_without_project(self) -> None:
        record_time(self.anna, None, self.sound, at(10, 8), at(10, 12))
        report = self.manager.get(f"{API}/reports/hours", {"group_by": "project"}).json()
        self.assertEqual([row["label"] for row in report["rows"]], ["Ohne Projekt"])
        csv = self.manager.get(f"{API}/reports/hours/csv").content.decode("utf-8-sig")
        self.assertIn(";;ohne Projekt;Tontechnik;", csv)
