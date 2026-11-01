# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser tests: my times, quick entry, stopwatch, approval, hours report (chapter 5.9).

Together with ``tests/api/test_time_api.py`` these are the proof of ZEI-001: a
simple recording of hours is part of the application.
"""

from __future__ import annotations

import datetime
import re
from decimal import Decimal

from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.timetracking.models import TimeEntry
from tests.helpers import (
    LATER,
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
from tests.ui.base import UiTestCase, form_data

D = Decimal


class TimePageTestCase(UiTestCase):
    """Anna (crew) is planned as sound engineer on the Stadtfest; Paula manages projects."""

    def setUp(self) -> None:
        super().setUp()
        # The tests record the hours of 10 March afterwards (ZEI-022). Log in again
        # at the new time: a session from four weeks earlier has run out.
        set_clock(LATER)
        self.client.force_login(self.admin_user)
        self.project = make_project("Stadtfest", start=at(10), end=at(12))
        self.sound = job_function("Tontechnik", price="45.00")
        self.hand = job_function("Stagehand", price="28.00")
        self.anna_user = make_user("anna", roles=("Crew",))
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00", "Stagehand": "20.00"}, user=self.anna_user)
        self.line = plan(self.project, self.sound, self.anna, start=at(10, 8), end=at(10, 20))
        self.crew = self.browser_of(self.anna_user)
        self.manager = self.browser_for("paula", "Projektleitung")
        self.quick = reverse("timetracking:quick")


class QuickEntryTests(TimePageTestCase):
    """ZEI-003 to ZEI-007, ZEI-009 – see also acceptance scenario 5."""

    def test_the_form_asks_for_little(self) -> None:
        """ZEI-003, ZEI-004: project, job function, day, begin, end, break, note – and nothing else.

        ZEI-025: besides, folded away, the further job functions of the period with their hours.
        """
        dialog = self.htmx("get", self.quick, client=self.crew)
        data = form_data(dialog)
        self.assertEqual(
            {name for name in data if not name.startswith("part_")},
            {"project", "job_function", "day", "break_minutes", "note", "submit"} | {"begin", "end"} & set(data),
        )
        text = self.assert_ok(dialog)
        self.assertIn('<details class="time-parts">', text)  # closed until needed
        for name in ("begin", "end"):
            self.assertIn(f'name="{name}"', text)
        self.assertRegex(text, r'(?s)<div class="form-row pair keep">.*?name="begin".*?name="end"')
        self.assertIn('type="time"', text)
        self.assertNotIn('name="person"', text)  # her own times: nobody to choose

    def test_only_her_job_functions_are_offered(self) -> None:
        """ZEI-007."""
        text = self.assert_ok(self.htmx("get", self.quick, client=self.crew))
        self.assertIn(">Tontechnik</option>", text)
        self.assertIn(">Stagehand</option>", text)
        self.assertNotIn(">Rigging</option>", text)

    def test_choosing_another_project_keeps_what_was_typed(self) -> None:
        warehouse = make_internal_project("Lager")
        again = self.htmx(
            "get",
            self.quick,
            {"project": warehouse.pk, "day": "2027-03-01", "begin": "06:00", "note": "Kabel"},
            client=self.crew,
        )
        text = self.assert_ok(again)
        self.assertIn(f'<option value="{warehouse.pk}" selected>', text)
        self.assertIn('value="06:00"', text)
        self.assertIn('value="Kabel"', text)

    def test_save_a_time_and_see_it_under_my_times(self) -> None:
        dialog = self.htmx("get", self.quick, {"project": self.project.pk}, client=self.crew)
        saved = self.htmx(
            "post",
            self.quick,
            form_data(dialog, day="2027-03-10", begin="08:00", end="16:30", break_minutes="30", note="Aufbau"),
            client=self.crew,
        )
        self.assertIn("Zeit erfasst", self.assert_ok(saved))
        entry = TimeEntry.objects.get()
        self.assertEqual(
            (entry.start, entry.end, entry.hours, entry.note, entry.status),
            (at(10, 8), at(10, 16, 30), D("8.00"), "Aufbau", "submitted"),
        )
        self.assertEqual((entry.hourly_rate, entry.crew_line), (D("35.00"), self.line))

        week = self.assert_ok(self.crew.get(reverse("timetracking:my_times"), {"week": "2027-03-10"}))
        for shown in (
            "Woche vom 08.03. bis 14.03.2027",
            "08:00 – 16:30",
            "30 Min. Pause",
            "Stadtfest",
            "eingereicht",
            "280,00",
            "Summe der Woche",
        ):
            self.assertIn(shown, week)

    def test_an_end_before_the_begin_means_the_next_day(self) -> None:
        """ZEI-009: over midnight."""
        dialog = self.htmx("get", self.quick, {"project": self.project.pk}, client=self.crew)
        self.htmx("post", self.quick, form_data(dialog, day="2027-03-10", begin="22:00", end="02:15"), client=self.crew)
        entry = TimeEntry.objects.get()
        self.assertEqual((entry.start, entry.end, entry.hours), (at(10, 22), at(11, 2, 15), D("4.25")))

    def test_without_the_tick_the_entry_is_not_handed_in(self) -> None:
        dialog = self.htmx("get", self.quick, {"project": self.project.pk}, client=self.crew)
        saved = self.htmx(
            "post",
            self.quick,
            form_data(dialog, day="2027-03-10", begin="08:00", end="12:00", submit=None),
            client=self.crew,
        )
        self.assertIn("Noch nicht eingereicht", self.assert_ok(saved))
        self.assertEqual(TimeEntry.objects.get().status, "recorded")
        page = self.assert_ok(self.crew.get(reverse("timetracking:my_times")))
        self.assertIn("Noch nicht eingereicht", page)
        self.assertIn("Alle einreichen", page)
        self.crew.post(reverse("timetracking:submit"))
        self.assertEqual(TimeEntry.objects.get().status, "submitted")

    def test_missing_times_are_pointed_out_in_the_dialog(self) -> None:
        dialog = self.htmx("get", self.quick, client=self.crew)
        answer = self.htmx("post", self.quick, form_data(dialog), client=self.crew)
        self.assertIn("Dieses Feld ist zwingend erforderlich", self.assert_ok(answer))
        self.assertEqual(TimeEntry.objects.count(), 0)

    def test_the_quick_entry_also_works_as_a_page_of_its_own(self) -> None:
        """For a bookmark on the phone, or a browser without scripts."""
        page = self.crew.get(self.quick, {"project": self.project.pk})
        text = self.assert_ok(page)
        self.assertIn("<html", text)
        self.assertIn(f'action="{self.quick}"', text)
        saved = self.crew.post(
            self.quick, form_data(page, containing="begin", day="2027-03-10", begin="08:00", end="12:00")
        )
        text = self.assert_ok(saved)
        self.assertIn("<html", text)
        self.assertIn("Zeit erfasst", text)
        self.assertEqual(TimeEntry.objects.count(), 1)

    def test_every_account_can_record(self) -> None:
        """AUT-026: an account from the user administration is a person and records its own times."""
        loose = self.browser_for("lose", "Crew")
        dialog = self.assert_ok(self.htmx("get", self.quick, client=loose))
        self.assertNotIn("mit keiner Person verknüpft", dialog)
        self.assertIn('name="begin"', dialog)
        self.assertNotIn("mit keiner Person verknüpft", self.assert_ok(loose.get(reverse("timetracking:my_times"))))

    def test_nothing_to_book_on_is_said_plainly(self) -> None:
        user = make_user("neu", roles=("Crew",))
        make_person("Nina Neu", rates={"Stagehand": "18.00"}, user=user)
        browser = self.browser_of(user)
        dialog = self.htmx("get", self.quick, client=browser)
        text = self.assert_ok(dialog)
        self.assertIn("Du bist in keinem Projekt eingeplant", text)
        self.assertIn('<option value="none" selected>', text)
        # The time can be recorded all the same – without project (ZEI-023).
        saved = self.htmx(
            "post", self.quick, form_data(dialog, day="2027-03-10", begin="08:00", end="12:00"), client=browser
        )
        self.assertIn("Ohne Projekt lässt sich die Zeit noch nicht freigeben", self.assert_ok(saved))
        self.assertIsNone(TimeEntry.objects.get(person__user=user).project)

    def test_recording_for_somebody_else_needs_the_right(self) -> None:
        """ZEI-011."""
        dialog = self.htmx("get", self.quick, {"person": self.anna.pk, "project": self.project.pk}, client=self.manager)
        self.assertIn("Zeit erfassen – Anna Becker", self.assert_ok(dialog))
        self.htmx(
            "post", self.quick, form_data(dialog, day="2027-03-10", begin="08:00", end="12:00"), client=self.manager
        )
        self.assertEqual(TimeEntry.objects.get().person, self.anna)

        kai_user = make_user("kai", roles=("Crew",))
        kai = make_person("Kai Kurz", rates={"Stagehand": "18.00"}, user=kai_user)
        plan(self.project, self.hand, kai)
        # Anna names Kai – and still gets the form for herself.
        dialog = self.htmx("get", self.quick, {"person": kai.pk}, client=self.crew)
        self.assertNotIn("Kai Kurz", self.assert_ok(dialog))
        self.htmx(
            "post",
            self.quick,
            form_data(dialog, day="2027-03-10", begin="13:00", end="14:00") | {"person": kai.pk},
            client=self.crew,
        )
        self.assertEqual(TimeEntry.objects.filter(person=kai).count(), 0)

    def test_time_tracking_needs_the_module(self) -> None:
        warehouse = self.browser_for("luka", "Lager")
        for name in ("timetracking:my_times", "timetracking:quick", "timetracking:report", "timetracking:approval"):
            self.assertEqual(warehouse.get(reverse(name)).status_code, 403, name)
        self.assertNotIn("Zeit erfassen", self.assert_ok(warehouse.get(reverse("core:home"))))


class StopwatchPageTests(TimePageTestCase):
    """ZEI-005."""

    def test_start_shows_the_running_stopwatch_and_stop_saves_the_entry(self) -> None:
        dialog = self.htmx("get", self.quick, {"project": self.project.pk}, client=self.crew)
        running = self.htmx("post", reverse("timetracking:timer_start"), form_data(dialog), client=self.crew)
        text = self.assert_ok(running)
        self.assertIn("Stoppuhr läuft", text)
        self.assertIn('data-timer-since="2027-03-28T18:00:00+02:00"', text)
        self.assertIn("Stoppuhr läuft", self.assert_ok(self.crew.get(reverse("timetracking:my_times"))))

        TimeEntry.objects.update(start=LATER - datetime.timedelta(hours=3))
        stopped = self.htmx(
            "post", reverse("timetracking:timer_stop"), form_data(running, break_minutes="15"), client=self.crew
        )
        self.assertIn("Zeit erfasst", self.assert_ok(stopped))
        entry = TimeEntry.objects.get()
        self.assertEqual((entry.hours, entry.break_minutes, entry.status), (D("2.75"), 15, "submitted"))

    def test_a_second_start_is_refused_with_a_message(self) -> None:
        dialog = self.htmx("get", self.quick, client=self.crew)
        self.htmx("post", reverse("timetracking:timer_start"), form_data(dialog), client=self.crew)
        again = self.htmx("post", reverse("timetracking:timer_start"), form_data(dialog), client=self.crew)
        self.assertIn("Die Stoppuhr läuft seit", self.assert_ok(again))
        self.assertEqual(TimeEntry.objects.count(), 1)


class MyTimesTests(TimePageTestCase):
    """ZEI-012, ZEI-014, ZEI-016."""

    def test_correct_an_open_entry_in_the_dialog(self) -> None:
        entry = record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 12), submit=True)
        url = reverse("timetracking:entry_edit", args=[entry.pk])
        dialog = self.htmx("get", url, client=self.crew)
        self.assertIn('value="08:00"', self.assert_ok(dialog))
        saved = self.htmx("post", url, form_data(dialog, end="13:30", note="länger"), client=self.crew)
        self.assertEqual(saved.status_code, 204)
        self.assertEqual(saved["HX-Trigger"], "timesChanged, closeDialog")
        entry.refresh_from_db()
        self.assertEqual((entry.end, entry.hours, entry.note), (at(10, 13, 30), D("5.50"), "länger"))

    def test_an_overlap_stays_in_the_dialog(self) -> None:
        record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 12))
        second = record_time(self.anna, self.project, self.sound, at(10, 13), at(10, 15))
        url = reverse("timetracking:entry_edit", args=[second.pk])
        answer = self.htmx(
            "post", url, form_data(self.htmx("get", url, client=self.crew), begin="11:00"), client=self.crew
        )
        self.assertIn("überschneidet sich", self.assert_ok(answer))

    def test_delete_an_open_entry_but_not_an_approved_one(self) -> None:
        open_entry = record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 12))
        approved = record_time(self.anna, self.project, self.sound, at(11, 8), at(11, 12), approve=True)
        self.crew.post(reverse("timetracking:entry_delete", args=[open_entry.pk]))
        refused = self.crew.post(reverse("timetracking:entry_delete", args=[approved.pk]), follow=True)
        self.assertIn("gesperrt", " ".join(self.messages_of(refused)))
        self.assertEqual(list(TimeEntry.objects.all()), [approved])
        # The dialog for an approved entry answers with the lock, not with a form that could be sent.
        url = reverse("timetracking:entry_edit", args=[approved.pk])
        answer = self.htmx("post", url, form_data(self.htmx("get", url, client=self.crew), note="x"), client=self.crew)
        self.assertIn("gesperrt", self.assert_ok(answer))

    def test_a_rejected_entry_shows_its_reason_and_can_be_corrected(self) -> None:
        entry = record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 12), submit=True)
        approval = self.manager.get(reverse("timetracking:approval"))
        self.manager.post(
            reverse("timetracking:decide"),
            form_data(approval, containing="entry") | {"decision": "reject", "reason": "Ende war 11 Uhr"},
        )
        page = self.assert_ok(self.crew.get(reverse("timetracking:my_times")))
        self.assertIn("Zurückgegeben: Ende war 11 Uhr", page)
        url = reverse("timetracking:entry_edit", args=[entry.pk])
        dialog = self.htmx("get", url, client=self.crew)
        self.assertIn("Ende war 11 Uhr", self.assert_ok(dialog))
        self.htmx("post", url, form_data(dialog, end="11:00", submit="on"), client=self.crew)
        entry.refresh_from_db()
        self.assertEqual((entry.status, entry.hours, entry.rejection_reason), ("submitted", D("3.00"), ""))

    def test_nobody_opens_the_entry_of_somebody_else(self) -> None:
        kai_user = make_user("kai", roles=("Crew",))
        make_person("Kai Kurz", user=kai_user)
        entry = record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 12))
        kai = self.browser_of(kai_user)
        self.assertEqual(kai.get(reverse("timetracking:entry_edit", args=[entry.pk])).status_code, 404)
        self.assertEqual(kai.post(reverse("timetracking:entry_delete", args=[entry.pk])).status_code, 404)
        self.assertTrue(TimeEntry.objects.filter(pk=entry.pk).exists())

    def test_weeks_can_be_paged_and_refresh_themselves(self) -> None:
        record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 12))
        this_week = self.assert_ok(self.crew.get(reverse("timetracking:my_times")))
        self.assertIn("Woche vom 22.03. bis 28.03.2027", this_week)
        self.assertIn("Keine Zeiten in dieser Woche", this_week)
        self.assertIn("?week=2027-03-15", this_week)
        fragment = self.assert_ok(
            self.htmx("get", reverse("timetracking:my_times"), {"week": "2027-03-08"}, client=self.crew)
        )
        self.assertNotIn("<html", fragment)
        self.assertIn('hx-trigger="timesChanged from:body"', fragment)
        self.assertIn("Stadtfest", fragment)

    def test_own_amounts_are_hidden_when_switched_off(self) -> None:
        """PER-010."""
        from rentalars.core.models import SystemSettings

        record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 12))
        week = {"week": "2027-03-10"}
        self.assertIn("140,00", self.assert_ok(self.crew.get(reverse("timetracking:my_times"), week)))
        settings = SystemSettings.load()
        settings.people_see_own_rates = False
        settings.save()
        self.assertNotIn("140,00", self.assert_ok(self.crew.get(reverse("timetracking:my_times"), week)))


class ApprovalPageTests(TimePageTestCase):
    """ZEI-012, ZEI-013."""

    def setUp(self) -> None:
        super().setUp()
        self.kai = make_person("Kai Kurz", rates={"Stagehand": "18.00"})
        self.first = record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 16), submit=True)
        self.second = record_time(self.kai, self.project, self.hand, at(10, 8), at(10, 14), submit=True)
        self.url = reverse("timetracking:approval")

    def test_waiting_times_are_listed_by_project(self) -> None:
        page = self.assert_ok(self.manager.get(self.url))
        for shown in ("Stadtfest", "Anna Becker", "Kai Kurz", "14 Std.", "280,00", "nicht eingeplant"):
            self.assertIn(shown, page)

    def test_approve_all_ticked_at_once(self) -> None:
        """ZEI-013: every entry is ticked when the page opens; one click approves them all."""
        page = self.manager.get(self.url)
        self.assertEqual(self.assert_ok(page).count('name="entry" value='), 2)
        # UIX-040: the column chooser has ticked boxes of its own; counted are the ticks of the entries.
        self.assertEqual(len(re.findall(r'name="entry" value="\d+" checked', self.assert_ok(page))), 2)
        done = self.manager.post(
            reverse("timetracking:decide"),
            {"entry": [self.first.pk, self.second.pk], "decision": "approve"},
            follow=True,
        )
        self.assertIn("2 Zeiteinträge freigegeben", " ".join(self.messages_of(done)))
        self.assertEqual(TimeEntry.objects.filter(status="approved").count(), 2)
        self.assertIn("Nichts wartet auf Freigabe", self.assert_ok(done))

    def test_approve_a_single_entry(self) -> None:
        done = self.manager.post(
            reverse("timetracking:decide"), {"entry": [self.first.pk], "decision": "approve"}, follow=True
        )
        self.assertIn("1 Zeiteintrag freigegeben", " ".join(self.messages_of(done)))
        self.assertEqual(TimeEntry.objects.get(pk=self.second.pk).status, "submitted")

    def test_send_back_needs_a_reason(self) -> None:
        refused = self.manager.post(
            reverse("timetracking:decide"), {"entry": [self.first.pk], "decision": "reject", "reason": ""}, follow=True
        )
        self.assertIn("Gib an, warum", " ".join(self.messages_of(refused)))
        self.assertEqual(TimeEntry.objects.get(pk=self.first.pk).status, "submitted")
        self.manager.post(
            reverse("timetracking:decide"), {"entry": [self.first.pk], "decision": "reject", "reason": "Pause fehlt"}
        )
        self.assertEqual(TimeEntry.objects.get(pk=self.first.pk).rejection_reason, "Pause fehlt")

    def test_nothing_ticked_is_said(self) -> None:
        answer = self.manager.post(reverse("timetracking:decide"), {"decision": "approve"}, follow=True)
        self.assertIn("Hake zuerst die Einträge an", " ".join(self.messages_of(answer)))

    def test_the_filter_survives_the_decision(self) -> None:
        answer = self.manager.post(
            reverse("timetracking:decide"),
            {"entry": [self.first.pk], "decision": "approve", "query": f"person={self.anna.pk}"},
        )
        self.assertRedirects(answer, f"{self.url}?person={self.anna.pk}")

    def test_crew_neither_sees_the_page_nor_decides(self) -> None:
        self.assertEqual(self.crew.get(self.url).status_code, 403)
        self.assertEqual(
            self.crew.post(
                reverse("timetracking:decide"), {"entry": [self.first.pk], "decision": "approve"}
            ).status_code,
            403,
        )
        self.assertNotIn("Freigeben", self.assert_ok(self.crew.get(reverse("timetracking:my_times"))))
        self.assertEqual(TimeEntry.objects.get(pk=self.first.pk).status, "submitted")

    def test_take_back_an_approval_from_the_report(self) -> None:
        self.manager.post(reverse("timetracking:decide"), {"entry": [self.first.pk], "decision": "approve"})
        report = reverse("timetracking:report") + "?since=2027-03-01"
        self.assertIn("entsperren", self.assert_ok(self.manager.get(report)))
        answer = self.manager.post(reverse("timetracking:entry_reopen", args=[self.first.pk]), {"next": report})
        self.assertRedirects(answer, report)
        self.assertEqual(TimeEntry.objects.get(pk=self.first.pk).status, "submitted")

    def test_the_way_back_cannot_be_bent_to_another_site(self) -> None:
        self.manager.post(reverse("timetracking:decide"), {"entry": [self.first.pk], "decision": "approve"})
        answer = self.manager.post(
            reverse("timetracking:entry_reopen", args=[self.first.pk]), {"next": "https://example.org/phish"}
        )
        self.assertRedirects(answer, reverse("timetracking:report"), fetch_redirect_response=False)


class ReportPageTests(TimePageTestCase):
    """ZEI-015 to ZEI-017."""

    def setUp(self) -> None:
        super().setUp()
        self.kai = make_person("Kai Kurz", rates={"Stagehand": "18.00"})
        record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 16), approve=True)
        record_time(self.anna, self.project, self.hand, at(11, 8), at(11, 12), submit=True)
        record_time(self.kai, self.project, self.hand, at(10, 8), at(10, 14), approve=True)
        self.url = reverse("timetracking:report")
        self.march = {"since": "2027-03-01", "until": "2027-03-31"}

    def test_sums_by_person_with_amounts(self) -> None:
        page = self.assert_ok(self.manager.get(self.url, self.march))
        table = page[page.index("<tbody>") : page.index("</tbody>")]
        self.assertLess(table.index("Becker, Anna"), table.index("Kurz, Kai"))
        for shown in (">12<", "360,00", ">6<", "108,00", ">18<", "468,00"):
            self.assertIn(shown, table)

    def test_grouping_and_filters(self) -> None:
        by_function = self.assert_ok(self.manager.get(self.url, {**self.march, "group_by": "job_function"}))
        table = by_function[by_function.index("<tbody>") : by_function.index("</tbody>")]
        self.assertIn("Stagehand", table)
        self.assertIn(">10<", table)
        only_anna = self.assert_ok(
            self.manager.get(self.url, {**self.march, "person": self.anna.pk, "group_by": "day"})
        )
        table = only_anna[only_anna.index("<tbody>") : only_anna.index("</tbody>")]
        self.assertIn("10.03.2027", table)
        self.assertIn("11.03.2027", table)
        self.assertNotIn("Kurz", table)
        approved = self.assert_ok(self.manager.get(self.url, {**self.march, "status": "approved"}))
        self.assertIn(">14<", approved[approved.index("<tbody>") : approved.index("</tbody>")])

    def test_without_a_filter_the_current_month_is_shown(self) -> None:
        record_time(self.anna, make_internal_project("Lager"), self.hand, at(1, 6, month=2), at(1, 8, month=2))
        page = self.assert_ok(self.manager.get(self.url))
        self.assertIn("Ohne Filter: der laufende Monat", page)
        self.assertNotIn("01.02.2027", page)
        self.assertIn("10.03.2027", page)

    def test_files_of_the_unfiltered_page_hold_the_same_month(self) -> None:
        """ZEI-017: CSV and PDF of the page as first shown – not every entry there is."""
        record_time(self.anna, make_internal_project("Lager"), self.hand, at(1, 6, month=2), at(1, 8, month=2))
        rows = self.manager.get(self.url, {"format": "csv"}).content.decode("utf-8-sig").strip().splitlines()
        self.assertEqual(len(rows), 4)
        self.assertNotIn("01.02.2027", "\n".join(rows))
        page = self.assert_ok(self.manager.get(self.url, {"format": "csv"}))
        self.assertIn("10.03.2027", page)
        pdf = self.manager.get(self.url, {"format": "pdf"})
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_the_list_of_entries_is_shown_page_by_page(self) -> None:
        """NFA-012: a month of a hundred people must not become a page of megabytes; the sums cover everything."""
        for day in range(1, 31):
            record_time(self.kai, self.project, self.hand, at(day, 18), at(day, 20), approve=True)
        first = self.assert_ok(self.manager.get(self.url, {"per_page": 25}))
        listed = first[first.index("Die Einträge") :]
        self.assertEqual(listed.count("<tr>") - 1, 25)  # the head row and 25 entries
        self.assertIn("33 Einträge, Seite 1 von 2", first)
        self.assertIn(">78<", first)  # total hours: 12 + 6 + 30 × 2
        second = self.assert_ok(self.manager.get(self.url, {"per_page": 25, "page": 2}))
        self.assertIn("Seite 2 von 2", second)
        self.assertIn("Ohne Filter: der laufende Monat", second)
        self.assertNotIn("page=", second[second.index("format=csv") - 200 : second.index("format=csv")])

    def test_a_timesheet_with_too_many_entries_is_refused_with_advice(self) -> None:
        from unittest import mock

        with mock.patch("rentalars.timetracking.pdf.MAX_TIMESHEET_ENTRIES", 2):
            response = self.manager.get(self.url, {**self.march, "format": "pdf"}, follow=True)
            page = self.assert_ok(response)
            self.assertIn("3 Einträge umfassen", page)
            self.assertIn("eingrenzen", page)
            self.assertTrue(
                self.manager.get(self.url, {**self.march, "person": self.kai.pk, "format": "pdf"}).content.startswith(
                    b"%PDF"
                )
            )

    def test_everybody_gets_the_report_of_their_own_times(self) -> None:
        """ZEI-016."""
        page = self.assert_ok(self.crew.get(self.url, self.march))
        self.assertIn("Anna Becker", page)
        self.assertNotIn("Kai Kurz", page)
        self.assertNotIn("Kurz, Kai", page)
        self.assertIn("360,00", page)
        self.assertNotIn("entsperren", page)

    def test_csv_export(self) -> None:
        """ZEI-017."""
        response = self.manager.get(self.url, {**self.march, "format": "csv"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/csv"))
        self.assertIn("Stunden.csv", response["Content-Disposition"])
        rows = response.content.decode("utf-8-sig").strip().splitlines()
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0].split(";")[:4], ["Person", "Projektnummer", "Projekt", "Funktion"])
        self.assertIn(
            "Becker, Anna;"
            + self.project.number
            + ";Stadtfest;Tontechnik;10.03.2027;08:00;16:00;0;8;freigegeben;35,00;280,00;",
            rows[1],
        )

    def test_csv_without_the_cost_right_has_no_rates_of_others(self) -> None:
        Role.objects.create(
            name="Crewchef", module_levels={"projects": 1, "time_tracking": 2}, special_rights=["approve_times"]
        )
        text = (
            self.browser_for("chris", "Crewchef")
            .get(self.url, {**self.march, "format": "csv"})
            .content.decode("utf-8-sig")
        )
        self.assertIn("Kurz, Kai", text)
        self.assertNotIn("18,00", text)
        self.assertNotIn("108,00", text)

    def test_timesheet_pdf(self) -> None:
        """ZEI-017."""
        response = self.manager.get(self.url, {**self.march, "person": self.anna.pk, "format": "pdf"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_timesheet_names_person_period_hours_and_a_line_to_sign(self) -> None:
        from rentalars.accounts.rights import Rights
        from rentalars.timetracking import services
        from rentalars.timetracking.pdf import render_timesheet_html

        report = services.hours_report(
            TimeEntry.objects.filter(person=self.anna), group_by="person", rights=Rights.everything(), user=None
        )
        html = render_timesheet_html(report, "01.03.2027 – 31.03.2027")
        for shown in (
            "Stundenzettel",
            "01.03.2027 – 31.03.2027",
            "Becker, Anna",
            "Stadtfest",
            "08:00",
            "16:00",
            "12",
            "Datum, Unterschrift",
        ):
            self.assertIn(shown, html)
        self.assertNotRegex(html, r"https?://")  # NFA-050: nothing is loaded from other servers


class FutureAndWithoutProjectPageTests(TimePageTestCase):
    """ZEI-022 and ZEI-023 on the pages."""

    def test_the_dialog_refuses_hours_that_are_not_over_yet(self) -> None:
        dialog = self.htmx("get", self.quick, {"project": self.project.pk}, client=self.crew)
        refused = self.htmx(
            "post", self.quick, form_data(dialog, day="2027-03-28", begin="17:00", end="19:00"), client=self.crew
        )
        text = self.assert_ok(refused)
        self.assertIn("Das Ende liegt in der Zukunft (jetzt ist es 28.03. 18:00)", text)
        self.assertIn('value="19:00"', text)
        self.assertEqual(TimeEntry.objects.count(), 0)

    def test_record_without_project_from_the_dialog(self) -> None:
        dialog = self.htmx("get", self.quick, {"project": "none"}, client=self.crew)
        text = self.assert_ok(dialog)
        self.assertIn('<option value="none" selected>später zuordnen</option>', text)
        self.assertIn(">Tontechnik</option>", text)  # her own functions only
        self.htmx("post", self.quick, form_data(dialog, day="2027-03-10", begin="08:00", end="12:00"), client=self.crew)
        entry = TimeEntry.objects.get()
        self.assertIsNone(entry.project)
        week = self.assert_ok(self.crew.get(reverse("timetracking:my_times"), {"week": "2027-03-10"}))
        self.assertIn("ohne Projekt", week)

    def test_the_approval_page_asks_for_the_project_first(self) -> None:
        entry = record_time(self.anna, None, self.sound, at(10, 8), at(10, 12), submit=True)
        url = reverse("timetracking:approval")
        page = self.assert_ok(self.manager.get(url))
        group = page[page.index("Ohne Projekt") :]
        self.assertIn("erst freigeben, wenn sie zu einem Projekt gehören", group)
        self.assertIn(f'form="assign-{entry.pk}"', group)
        self.assertIn(f">{self.project.number} Stadtfest</option>", group)
        self.assertNotIn("Angehakte freigeben", group[: group.index("</form>")])

        answer = self.manager.post(
            reverse("timetracking:entry_assign", args=[entry.pk]),
            {"project": self.project.pk, "next": url},
            follow=True,
        )
        self.assertIn("gehört jetzt zu", " ".join(self.messages_of(answer)))
        entry.refresh_from_db()
        self.assertEqual(entry.project, self.project)
        self.manager.post(reverse("timetracking:decide"), {"entry": [entry.pk], "decision": "approve"})
        entry.refresh_from_db()
        self.assertEqual(entry.status, "approved")

    def test_approving_without_project_is_refused_with_advice(self) -> None:
        entry = record_time(self.anna, None, self.sound, at(10, 8), at(10, 12), submit=True)
        answer = self.manager.post(
            reverse("timetracking:decide"), {"entry": [entry.pk], "decision": "approve"}, follow=True
        )
        self.assertIn("hat noch kein Projekt", " ".join(self.messages_of(answer)))

    def test_the_report_can_be_filtered_to_times_without_project(self) -> None:
        record_time(self.anna, None, self.sound, at(10, 8), at(10, 12))
        record_time(self.anna, self.project, self.sound, at(11, 8), at(11, 10))
        page = self.assert_ok(
            self.manager.get(reverse("timetracking:report"), {"project": "none", "since": "2027-03-01"})
        )
        table = page[page.index("<tbody>") : page.index("</tbody>")]
        self.assertIn(">4<", table)
        self.assertNotIn(">6<", table)
