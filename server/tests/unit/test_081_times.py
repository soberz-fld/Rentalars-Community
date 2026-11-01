# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "times": requirements from use.

* ZEI-025: several job functions in one period of time, each with its share of the hours – stored as one time entry
  per part, linked by ``period_key``, so that sums, reports, approval and costs work on the parts as on any entry.
  Surcharges are spread over the parts by their hours; hints, the overlap check and the stopwatch treat the period
  once; approving or rejecting acts on the whole period.
* ZEI-024: everybody who records times can book them on an open service case – the cases one takes part in first –
  with every job function.
* ZEI-026: "My times" shows the hourly pay (a day rate where the deployment is paid per day), and an approved time
  can be copied as a block per part.
"""

from __future__ import annotations

from decimal import Decimal as D  # noqa: N817

from django.core.exceptions import ValidationError

from rentalars.personnel import services as personnel_services
from rentalars.projects import service_cases
from rentalars.projects.crew import approved_hours_by_line, price_crew_line
from rentalars.projects.models import CaseStatus, CrewBilling, PhaseKind, ProjectPhase
from rentalars.projects.time_surcharges import current_rules, entry_pieces
from rentalars.timetracking import display, services
from rentalars.timetracking.hints import HintKind, hints_for
from rentalars.timetracking.models import TimeEntry, TimeEntryStatus
from rentalars.timetracking.services import Part
from tests.helpers import (
    ALL_RIGHTS,
    LATER,
    RentalarsTestCase,
    at,
    job_function,
    make_person,
    make_project,
    make_user,
    plan,
    record_time,
    set_clock,
)
from tests.unit.test_080_projects import SplitCase


class PeriodCase(RentalarsTestCase):
    """Anna is planned on the Stadtfest for light (setup, 08–12) and sound (event, 12–20) on 10 March 2027."""

    def setUp(self) -> None:
        super().setUp()
        set_clock(LATER)
        self.project = make_project("Stadtfest", start=at(10), end=at(12))
        self.light = job_function("Licht", price="40.00")
        self.sound = job_function("Tontechnik", price="45.00")
        self.anna = make_person("Anna Becker", rates={"Licht": "30.00", "Tontechnik": "35.00"})
        self.setup = ProjectPhase.objects.create(
            project=self.project, kind=PhaseKind.SETUP, start=at(10, 8), end=at(10, 12)
        )
        self.light_line = plan(self.project, self.light, self.anna, start=at(10, 8), end=at(10, 12), phase=self.setup)
        self.sound_line = plan(self.project, self.sound, self.anna, start=at(10, 12), end=at(10, 20))

    def divide(self, *parts: Part, start=None, end=..., break_minutes: int = 30, submit: bool = True) -> TimeEntry:
        return services.create_entry(
            person=self.anna,
            project=self.project,
            job_function=parts[0].job_function,
            start=start or at(10, 8),
            end=at(10, 16, 30) if end is ... else end,
            break_minutes=break_minutes,
            rights=ALL_RIGHTS,
            user=None,
            submit=submit,
            parts=list(parts),
        )


class DividedPeriodTests(PeriodCase):
    """ZEI-025: recording, its rules and what it changes nowhere else."""

    def test_a_period_in_two_job_functions_is_two_entries_whose_hours_add_up(self) -> None:
        """ZEI-025: 08:00–16:30, 30 minutes break = 8 hours: light 3, sound the rest."""
        first = self.divide(Part(self.light, D("3"), self.light_line), Part(self.sound, None))
        parts = list(TimeEntry.objects.order_by("id"))
        self.assertEqual(len(parts), 2)
        self.assertEqual(first, parts[0])
        self.assertEqual([part.hours for part in parts], [D("3.00"), D("5.00")])
        self.assertEqual({part.period_key for part in parts}, {first.period_key})
        self.assertIsNotNone(first.period_key)
        self.assertEqual([part.crew_line for part in parts], [self.light_line, self.sound_line])
        # Each part keeps its own rate (ZEI-008) – and the period's times and break.
        self.assertEqual([part.hourly_rate for part in parts], [D("30.00"), D("35.00")])
        self.assertEqual(
            {(part.start, part.end, part.break_minutes) for part in parts}, {(at(10, 8), at(10, 16, 30), 30)}
        )
        self.assertEqual([part.period_hours for part in parts], [D("8.00"), D("8.00")])
        self.assertEqual({part.status for part in parts}, {TimeEntryStatus.SUBMITTED})
        # Saving again keeps the share (the model would otherwise count begin to end).
        parts[0].save()
        parts[0].refresh_from_db()
        self.assertEqual(parts[0].hours, D("3.00"))

    def test_an_entry_without_parts_behaves_as_before(self) -> None:
        """ZEI-025: an entry without parts behaves as before."""
        entry = record_time(self.anna, self.project, self.sound, at(10, 12), at(10, 20))
        self.assertIsNone(entry.period_key)
        self.assertEqual(entry.hours, D("8.00"))
        self.assertEqual(entry.crew_line, self.sound_line)

    def test_the_hours_must_add_up(self) -> None:
        """ZEI-025: the parts add up to the worked hours."""
        cases = [
            ((Part(self.light, D("3")), Part(self.sound, D("4"))), "ergeben 3+4"),
            ((Part(self.light, None), Part(self.sound, None)), "two open"),
            ((Part(self.light, D("8")), Part(self.sound, None)), "nothing left"),
            ((Part(self.light, D("0")), Part(self.sound, None)), "zero"),
            ((Part(self.sound, D("3")), Part(self.sound, None)), "twice"),
        ]
        for parts, label in cases:
            with self.subTest(label), self.assertRaises(ValidationError) as caught:
                self.divide(*parts)
            self.assertIn("parts", caught.exception.message_dict)
        self.assertFalse(TimeEntry.objects.exists())
        with self.assertRaises(ValidationError) as caught:
            self.divide(Part(self.light, D("3")), Part(self.sound, D("4")))
        self.assertIn("ergeben 7", " ".join(caught.exception.messages))

    def test_share_hours_gives_the_rest_to_the_open_part(self) -> None:
        self.assertEqual(
            services.share_hours([Part(self.light, D("2.25")), Part(self.sound)], D("8")), [D("2.25"), D("5.75")]
        )

    def test_a_crew_line_must_be_the_persons_in_this_project_and_function(self) -> None:
        """ZEI-025: a chosen suggestion must fit."""
        tom = make_person("Tom Richter", rates={"Licht": "25.00"})
        toms_line = plan(self.project, self.light, tom, start=at(10, 8), end=at(10, 12))
        for line, function in ((toms_line, self.light), (self.light_line, self.sound)):
            with self.subTest(line=line.pk), self.assertRaises(ValidationError):
                self.divide(Part(function, D("3"), line), Part(self.sound if function == self.light else self.light))

    def test_the_period_is_checked_once_for_overlaps(self) -> None:
        """ZEI-025: the parts do not overlap each other; the period overlaps other entries as a whole."""
        self.divide(Part(self.light, D("3")), Part(self.sound))
        with self.assertRaises(ValidationError) as caught:
            record_time(self.anna, self.project, self.sound, at(10, 16), at(10, 18))
        self.assertIn("überschneidet sich", " ".join(caught.exception.messages))
        record_time(self.anna, self.project, self.sound, at(10, 16, 30), at(10, 18))  # right after it: fine

    def test_a_running_stopwatch_cannot_be_divided(self) -> None:
        """ZEI-025: the stopwatch treats the period once – it is divided after it was stopped."""
        with self.assertRaises(ValidationError):
            self.divide(Part(self.light, D("3")), Part(self.sound), end=None)
        set_clock(at(10, 9))
        timer = services.start_timer(
            person=self.anna, project=self.project, job_function=self.light, rights=ALL_RIGHTS, user=None
        )
        set_clock(at(10, 17))
        stopped = services.stop_timer(person=self.anna, rights=ALL_RIGHTS, user=None, break_minutes=0)
        self.assertEqual(stopped.pk, timer.pk)
        kept = services.save_period(
            stopped, parts=[Part(self.light, D("3"), self.light_line), Part(self.sound)], rights=ALL_RIGHTS, user=None
        )
        self.assertEqual([part.hours for part in kept], [D("3.00"), D("5.00")])
        self.assertEqual(kept[0].pk, timer.pk)


class ChangingAPeriodTests(PeriodCase):
    """ZEI-025: correcting a divided period, and dividing or joining again."""

    def test_new_times_keep_the_proportion(self) -> None:
        """ZEI-025: times of a part changed alone change the period; the shares follow in proportion."""
        first = self.divide(Part(self.light, D("3")), Part(self.sound))
        second = TimeEntry.objects.exclude(pk=first.pk).get()
        services.update_entry(second, rights=ALL_RIGHTS, user=None, end=at(10, 14, 30))  # 6 hours now
        hours = list(TimeEntry.objects.order_by("id").values_list("hours", "end"))
        self.assertEqual(hours, [(D("2.25"), at(10, 14, 30)), (D("3.75"), at(10, 14, 30))])

    def test_the_job_function_of_one_part_changes_alone_and_reads_its_rate_again(self) -> None:
        """ZEI-025, ZEI-008."""
        first = self.divide(Part(self.light, D("3")), Part(self.sound))
        stage = job_function("Stagehand")
        personnel_services.set_rate(self.anna, stage, D("20.00"), at(1, month=1).date())
        services.update_entry(first, rights=ALL_RIGHTS, user=None, job_function=stage)
        parts = list(TimeEntry.objects.order_by("id"))
        self.assertEqual([part.job_function for part in parts], [stage, self.sound])
        self.assertEqual([part.hourly_rate for part in parts], [D("20.00"), D("35.00")])
        self.assertEqual([part.hours for part in parts], [D("3.00"), D("5.00")])

    def test_dividing_an_entry_and_joining_it_again(self) -> None:
        """ZEI-025: save_period reuses the rows; one part makes the entry undivided again."""
        entry = record_time(self.anna, self.project, self.light, at(10, 8), at(10, 16, 30), break_minutes=30)
        kept = services.save_period(
            entry,
            parts=[Part(self.light, D("2"), self.light_line), Part(self.sound, D("4")), Part(self.light, None)],
            rights=ALL_RIGHTS,
            user=None,
        )
        self.assertEqual(kept[0].pk, entry.pk)
        self.assertEqual([part.hours for part in kept], [D("2.00"), D("4.00"), D("2.00")])
        self.assertEqual(TimeEntry.objects.count(), 3)
        joined = services.save_period(kept[1], parts=[Part(self.sound)], rights=ALL_RIGHTS, user=None)
        self.assertEqual(len(joined), 1)
        self.assertEqual(TimeEntry.objects.count(), 1)
        alone = TimeEntry.objects.get()
        self.assertEqual(
            (alone.pk, alone.period_key, alone.hours, alone.job_function), (entry.pk, None, D("8.00"), self.sound)
        )

    def test_deleting_a_part_deletes_the_period(self) -> None:
        first = self.divide(Part(self.light, D("3")), Part(self.sound), submit=False)
        services.delete_entry(TimeEntry.objects.exclude(pk=first.pk).get(), rights=ALL_RIGHTS, user=None)
        self.assertFalse(TimeEntry.objects.exists())


class ApprovingAPeriodTests(PeriodCase):
    """ZEI-025: "approving or rejecting acts on the whole period"."""

    def test_approving_one_part_approves_the_period(self) -> None:
        first = self.divide(Part(self.light, D("3")), Part(self.sound))
        changed = services.approve_entries([first], rights=ALL_RIGHTS, user=None)
        self.assertEqual(changed, 2)
        self.assertEqual(set(TimeEntry.objects.values_list("status", flat=True)), {TimeEntryStatus.APPROVED})
        services.take_back_approval(first, rights=ALL_RIGHTS, user=None)
        self.assertEqual(set(TimeEntry.objects.values_list("status", flat=True)), {TimeEntryStatus.SUBMITTED})

    def test_rejecting_one_part_rejects_the_period_and_handing_in_takes_both(self) -> None:
        first = self.divide(Part(self.light, D("3")), Part(self.sound))
        second = TimeEntry.objects.exclude(pk=first.pk).get()
        self.assertEqual(services.reject_entries([second], "Bitte prüfen", rights=ALL_RIGHTS, user=None), 2)
        self.assertEqual(set(TimeEntry.objects.values_list("status", flat=True)), {TimeEntryStatus.REJECTED})
        first.refresh_from_db()
        self.assertEqual(services.submit_entries([first], rights=ALL_RIGHTS, user=None), 2)

    def test_approved_parts_count_towards_their_crew_lines(self) -> None:
        """ZEI-025: each part counts towards its own crew line, at its own rate – no second code path."""
        first = self.divide(Part(self.light, D("3"), self.light_line), Part(self.sound))
        services.approve_entries([first], rights=ALL_RIGHTS, user=None)
        approved = approved_hours_by_line(self.project)
        self.assertEqual(approved[self.light_line.pk].hours, D("3.00"))
        self.assertEqual(approved[self.sound_line.pk].hours, D("5.00"))
        self.assertEqual(approved[self.light_line.pk].cost, D("90.00"))
        self.assertEqual(approved[self.sound_line.pk].cost, D("175.00"))
        price = price_crew_line(self.sound_line, approved[self.sound_line.pk])
        self.assertEqual(price.approved_hours, D("5.00"))

    def test_surcharges_are_spread_over_the_parts_by_their_hours(self) -> None:
        """ZEI-025 with PER-009: a night period in two parts has the surcharges of the whole, split by hours."""
        start, end = at(13, 20), at(14, 4)  # Saturday 20:00 to Sunday 04:00, 8 hours
        rules = current_rules()
        whole = entry_pieces([(start, end, D("8"), D("30"))], rules)
        parts = entry_pieces([(start, end, D("3"), D("30"))], rules) + entry_pieces(
            [(start, end, D("5"), D("30"))], rules
        )

        def by_kind(pieces) -> dict:
            sums: dict = {}
            for piece in pieces:
                sums[piece.kinds] = sums.get(piece.kinds, D("0")) + piece.hours
            return {kinds: round(hours, 6) for kinds, hours in sums.items()}

        self.assertEqual(by_kind(parts), by_kind(whole))
        self.assertGreater(len(by_kind(whole)), 1)


class HintsOfAPeriodTests(PeriodCase):
    """ZEI-025 with ZEI-018: the hints treat the period once."""

    def test_the_break_counts_once(self) -> None:
        """08:00–19:00 with 30 minutes: 10.5 hours – a long day, and 30 minutes are short for more than 9 hours."""
        first = self.divide(Part(self.light, D("4")), Part(self.sound), end=at(10, 19))
        parts = list(TimeEntry.objects.order_by("id"))
        hints = hints_for(parts)
        for part in parts:
            kinds = {hint.kind for hint in hints[part.pk]}
            self.assertEqual(kinds, {HintKind.LONG_DAY, HintKind.SHORT_BREAK}, part)
        self.assertIn("10,5 Stunden Arbeit mit 30 Minuten Pause", hints[first.pk][1].message)

    def test_an_ordinary_divided_day_has_no_hint(self) -> None:
        self.divide(Part(self.light, D("3")), Part(self.sound))
        self.assertEqual(hints_for(TimeEntry.objects.all()), {})


class ServiceCaseTests(RentalarsTestCase):
    """ZEI-024: times on open service cases, by everybody who records times, with every job function."""

    def setUp(self) -> None:
        super().setUp()
        set_clock(LATER)
        self.user = make_user("anna", roles=("Crew",))
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"}, user=self.user)
        self.rigging = job_function("Rigging")
        self.repair = service_cases.create_case(name="Scheinwerfer flackert")
        self.question = service_cases.create_case(name="Frage zur Anleitung")
        self.closed = service_cases.create_case(name="Erledigt")
        service_cases.set_case_status(self.closed, CaseStatus.DONE)

    def test_open_cases_are_offered_those_one_takes_part_in_first(self) -> None:
        service_cases.add_participant(self.question, self.anna, job_function=self.rigging)
        choices = services.project_choices(self.anna, self.user.rights, self.user, service_cases=True)
        cases = [choice for choice in choices if choice.reason == "service_case"]
        self.assertEqual([choice.project for choice in cases], [self.question, self.repair])
        self.assertTrue(cases[0].takes_part)
        self.assertEqual(cases[0].job_function, self.rigging)
        self.assertFalse(cases[1].takes_part)
        self.assertNotIn(self.closed, [choice.project for choice in choices])
        # Without the switch the list stays as before (expenses, approval).
        plain = services.project_choices(self.anna, self.user.rights, self.user)
        self.assertNotIn("service_case", {choice.reason for choice in plain})

    def test_every_job_function_can_be_booked_spontaneously(self) -> None:
        """ZEI-024: without being planned, in a job function that is not one's own."""
        self.assertIn(self.rigging, services.job_functions_for(self.anna, self.repair))
        entry = services.create_entry(
            person=self.anna,
            project=self.repair,
            job_function=self.rigging,
            start=at(20, 9),
            end=at(20, 11),
            rights=self.user.rights,
            user=self.user,
        )
        self.assertEqual((entry.project, entry.hours, entry.crew_line), (self.repair, D("2.00"), None))

    def test_a_done_case_takes_no_more_times_from_people_who_cannot_see_it(self) -> None:
        with self.assertRaises(ValidationError):
            services.create_entry(
                person=self.anna,
                project=self.closed,
                job_function=self.rigging,
                start=at(20, 9),
                end=at(20, 11),
                rights=self.user.rights,
                user=self.user,
            )


class PayAndClipboardTests(PeriodCase):
    """ZEI-026: hourly pay or day rate, and the text to copy."""

    def test_hourly_pay_and_a_day_rate(self) -> None:
        """ZEI-026: a deployment paid per day shows its day rate once per day and line."""
        hourly = record_time(self.anna, self.project, self.light, at(10, 8), at(10, 12))
        daily_line = plan(
            self.project,
            self.sound,
            self.anna,
            start=at(11, 8),
            end=at(11, 22),
            billing=CrewBilling.DAY,
            daily_rate=D("280.00"),
        )
        morning = record_time(self.anna, self.project, self.sound, at(11, 8), at(11, 12))
        evening = record_time(self.anna, self.project, self.sound, at(11, 18), at(11, 22))
        self.assertEqual((morning.crew_line, evening.crew_line), (daily_line, daily_line))
        entries = list(TimeEntry.objects.select_related("crew_line").order_by("start"))
        total = display.attach_pay(entries)
        self.assertEqual(
            [(entry.pay_kind, entry.pay_rate, entry.pay_amount, entry.pay_in_day_rate) for entry in entries],
            [
                ("hourly", D("30.00"), D("120.00"), False),
                ("daily", D("280.00"), D("280.00"), False),
                ("daily", D("280.00"), D("0"), True),
            ],
        )
        self.assertEqual(total, D("400.00"))
        self.assertEqual(entries[0].pk, hourly.pk)

    def test_the_block_to_copy(self) -> None:
        """ZEI-026: product of the job function, date with dots, project, phase – with real tabs; one per part."""
        first = self.divide(Part(self.light, D("3"), self.light_line), Part(self.sound))
        services.approve_entries([first], rights=ALL_RIGHTS, user=None)
        parts = list(TimeEntry.objects.select_related("project", "job_function", "crew_line").order_by("id"))
        display.attach_clipboard(parts)
        number = self.project.number
        self.assertEqual(
            parts[0].copy_text,
            "Licht, Stunde\n\tDatum: 2027.03.10\n\tProjekt: "
            f"{number} - Stadtfest\n\tAktivität: Aufbau\n"
            "Tontechnik, Stunde\n\tDatum: 2027.03.10\n\tProjekt: "
            f"{number} - Stadtfest\n\tAktivität: ",
        )
        self.assertEqual(parts[1].copy_text, "")  # the block of the period is at its first part

    def test_only_approved_times_can_be_copied(self) -> None:
        entry = record_time(self.anna, self.project, self.sound, at(10, 12), at(10, 20), submit=True)
        display.attach_clipboard([entry])
        self.assertEqual(entry.copy_text, "")

    def test_mark_periods(self) -> None:
        self.divide(Part(self.light, D("3")), Part(self.sound))
        single = record_time(self.anna, self.project, self.sound, at(11, 12), at(11, 14))
        entries = list(TimeEntry.objects.order_by("start", "id"))
        display.mark_periods(entries)
        self.assertEqual([(entry.part_number, entry.part_count) for entry in entries], [(1, 2), (2, 2), (0, 0)])
        self.assertEqual(entries[2], single)


class SplittingAProjectTests(SplitCase):
    """ZEI-025 with PRJ-050: dividing a project afterwards keeps a divided period in one project."""

    def setUp(self) -> None:
        super().setUp()
        set_clock(LATER)
        self.anna = make_person("Anna Becker", rates={"Lichttechnik": "30.00", "Tontechnik": "35.00"})
        self.light = plan(self.project, "Lichttechnik", self.anna, start=at(10, 8), end=at(10, 12))
        self.sound = plan(self.project, "Tontechnik", self.anna, start=at(10, 12), end=at(10, 20))
        self.first = services.create_entry(
            person=self.anna,
            project=self.project,
            job_function=self.light.job_function,
            start=at(10, 8),
            end=at(10, 16, 30),
            break_minutes=30,
            rights=ALL_RIGHTS,
            user=None,
            submit=True,
            parts=[Part(self.light.job_function, D("3"), self.light), Part(self.sound.job_function, None, self.sound)],
        )
        services.approve_entries([self.first], rights=ALL_RIGHTS, user=None)

    def test_tearing_a_period_apart_is_refused_with_the_reason(self) -> None:
        for crew in ({self.light.pk: self.market.pk}, {self.light.pk: self.market.pk, self.sound.pk: self.park.pk}):
            with self.subTest(crew=crew), self.assertRaises(ValidationError) as caught:
                self.split(self.market, self.park, crew=crew)
            self.assertIn(
                "Die Zeit von Anna Becker am 10.03.2027 von 08:00 bis 16:30 ist aufgeteilt auf Lichttechnik, "
                "Tontechnik.",
                " ".join(caught.exception.messages),
            )
        self.assertFalse(self.project.subprojects.exists())
        self.assertEqual(set(TimeEntry.objects.values_list("project", flat=True)), {self.project.pk})

    def test_a_period_whose_crew_lines_go_together_moves_whole(self) -> None:
        (market,) = self.split(self.market, crew={self.light.pk: self.market.pk, self.sound.pk: self.market.pk})
        parts = list(TimeEntry.objects.order_by("id"))
        self.assertEqual({part.project for part in parts}, {market})
        self.assertEqual([part.hours for part in parts], [D("3.00"), D("5.00")])
        self.assertEqual({part.status for part in parts}, {TimeEntryStatus.APPROVED})

    def test_a_period_that_stays_at_the_whole_project_does_not_stop_the_split(self) -> None:
        (market,) = self.split(self.market)
        self.assertEqual(set(TimeEntry.objects.values_list("project", flat=True)), {self.project.pk})
        self.assertEqual(market.parent, self.project)
