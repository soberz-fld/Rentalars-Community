# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests: crew lines – planning people, their price and their cost (PRJ-019 ff., PER-006, PER-018)."""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.personnel import services as personnel
from rentalars.personnel.models import Absence, AbsenceKind
from rentalars.products.models import BillingMode, ProductKind
from rentalars.projects import crew
from rentalars.projects import services as projects
from rentalars.projects.models import CrewBilling, ProjectStatus, suggested_hours
from rentalars.projects.planning import build_planning
from rentalars.projects.pricing import compute_project_prices
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_line,
    at,
    job_function,
    make_person,
    make_product,
    make_project,
    plan,
    record_time,
)

D = Decimal

#: A planner who may neither see prices nor costs, nor plan outside the job functions.
PLAIN = Rights(module_levels={"projects": 2, "personnel": 2})


class SuggestedHoursTests(RentalarsTestCase):
    """PRJ-023, PRJ-073: the planned hours start as the length of the period."""

    def test_a_short_period_is_worked_through(self) -> None:
        self.assertEqual(suggested_hours(at(13, 8), at(13, 14)), D("6.00"))
        self.assertEqual(suggested_hours(at(13, 8), at(13, 23, 30)), D("15.50"))
        self.assertEqual(suggested_hours(at(13, 8), at(14)), D("16.00"))

    def test_minutes_are_rounded_to_quarter_hours(self) -> None:
        self.assertEqual(suggested_hours(at(13, 8), at(13, 9, 10)), D("1.25"))

    def test_a_long_period_is_worked_through_as_well(self) -> None:
        """PRJ-073: Friday 10:00 to Sunday 18:00 are 56 hours."""
        self.assertEqual(suggested_hours(at(12, 10), at(14, 18)), D("56.00"))
        self.assertEqual(suggested_hours(at(13, 8), at(14, 0, 15)), D("16.25"))

    def test_a_missing_or_reversed_period_suggests_nothing(self) -> None:
        self.assertEqual(suggested_hours(None, at(13)), D("0"))
        self.assertEqual(suggested_hours(at(13), at(12)), D("0"))


class PlanningPeopleTests(RentalarsTestCase):
    """PRJ-019 to PRJ-021, PER-006."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", start=at(12, 10), end=at(14, 18))
        self.sound = job_function("Tontechnik", price="45.00", guide="32.00")
        self.hand = job_function("Stagehand", price="28.00", guide="18.00")
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00", "Stagehand": "20.00"})

    def test_a_crew_line_has_job_function_and_period(self) -> None:
        line = plan(self.project, self.sound, self.anna, start=at(13, 8), end=at(13, 22))
        self.assertEqual((line.job_function, line.person), (self.sound, self.anna))
        self.assertEqual((line.start, line.end), (at(13, 8), at(13, 22)))
        self.assertEqual(line.planned_hours, D("14.00"))
        self.assertEqual(line.title, "Tontechnik, Stunde")
        self.assertEqual(line.service_product, self.sound.service_product)

    def test_without_period_the_line_covers_the_project(self) -> None:
        line = plan(self.project, self.sound, self.anna)
        self.assertEqual((line.start, line.end), (self.project.start, self.project.end))
        # PRJ-073: the whole length of the period.
        self.assertEqual(line.planned_hours, D("56.00"))

    def test_open_places_are_planned_first_and_filled_later(self) -> None:
        """PRJ-020: "2 × stagehand, Saturday 08–14"."""
        lines = crew.add_crew_lines(
            self.project, rights=ALL_RIGHTS, job_function=self.hand, count=2, start=at(13, 8), end=at(13, 14)
        )
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(line.is_vacant and line.planned_hours == D("6.00") for line in lines))
        self.assertEqual(build_planning(self.project).open_places, 2)

        filled = crew.update_crew_line(lines[0], rights=ALL_RIGHTS, person=self.anna)
        self.assertEqual(filled.person, self.anna)
        self.assertEqual(filled.hourly_rate, D("20.00"))
        self.assertEqual(build_planning(self.project).open_places, 1)

    def test_a_person_fills_one_place_only(self) -> None:
        with self.assertRaises(ValidationError) as raised:
            crew.add_crew_lines(self.project, rights=ALL_RIGHTS, job_function=self.hand, person=self.anna, count=2)
        self.assertIn("count", raised.exception.message_dict)

    def test_the_number_of_places_per_step_is_limited(self) -> None:
        for count in (0, 51):
            with self.assertRaises(ValidationError):
                crew.add_crew_lines(self.project, rights=ALL_RIGHTS, job_function=self.hand, count=count)

    def test_the_rate_is_copied_from_person_and_function_and_stays(self) -> None:
        """PRJ-021, PER-007: a later change of the person's rate does not reach the line."""
        line = plan(self.project, self.sound, self.anna)
        self.assertEqual(line.hourly_rate, D("35.00"))
        personnel.set_rate(self.anna, self.sound, D("38.00"), datetime.date(2027, 3, 1))
        line.refresh_from_db()
        self.assertEqual(line.hourly_rate, D("35.00"))
        self.assertEqual(plan(self.project, self.sound, self.anna).hourly_rate, D("38.00"))

    def test_the_rate_is_the_one_valid_on_the_day_of_the_deployment(self) -> None:
        personnel.set_rate(self.anna, self.sound, D("38.00"), datetime.date(2027, 3, 13))
        self.assertEqual(
            plan(self.project, self.sound, self.anna, start=at(12, 10), end=at(12, 18)).hourly_rate, D("35")
        )
        self.assertEqual(
            plan(self.project, self.sound, self.anna, start=at(13, 10), end=at(13, 18)).hourly_rate, D("38")
        )

    def test_the_rate_can_be_overwritten_with_the_right(self) -> None:
        line = plan(self.project, self.sound, self.anna, hourly_rate=D("40.00"))
        self.assertEqual(line.hourly_rate, D("40.00"))
        costs_only = Rights(module_levels={"projects": 2}, special_rights=frozenset({SpecialRight.PERSONNEL_COSTS}))
        self.assertEqual(crew.update_crew_line(line, rights=costs_only, hourly_rate=D("42.00")).hourly_rate, D("42"))

    def test_prices_and_costs_need_their_rights(self) -> None:
        """AUT-019."""
        line = plan(self.project, self.sound, self.anna)
        for change in (
            {"hourly_rate": D("1")},
            {"cost_flat_rate": D("1")},
            {"unit_price": D("1")},
            {"billing": "flat"},
        ):
            with self.assertRaises(ValidationError, msg=change):
                crew.update_crew_line(line, rights=PLAIN, **change)
        # Everything else is open to the planner.
        changed = crew.update_crew_line(
            line, rights=PLAIN, meeting_point="Rampe", note="Sprinter", planned_hours=D("9")
        )
        self.assertEqual((changed.meeting_point, changed.note, changed.planned_hours), ("Rampe", "Sprinter", D("9")))

    def test_a_person_is_planned_only_in_their_own_job_functions(self) -> None:
        """PER-006."""
        rigging = job_function("Rigging")
        with self.assertRaises(ValidationError) as raised:
            crew.add_crew_lines(self.project, rights=PLAIN, job_function=rigging, person=self.anna)
        self.assertIn("person", raised.exception.message_dict)
        self.assertEqual(self.project.crew_lines.count(), 0)

    def test_with_the_special_right_a_person_can_be_planned_outside_their_functions(self) -> None:
        """PER-006: the deviation is possible; PRJ-022: and it is pointed out."""
        rigging = job_function("Rigging")
        may_deviate = Rights(
            module_levels={"projects": 2}, special_rights=frozenset({SpecialRight.PLAN_ANY_JOB_FUNCTION})
        )
        (line,) = crew.add_crew_lines(self.project, rights=may_deviate, job_function=rigging, person=self.anna)
        self.assertIsNone(line.hourly_rate)
        warnings = crew.crew_warnings([line])[line.pk]
        self.assertEqual(len(warnings), 1)
        self.assertIn("Rigging", warnings[0])

    def test_deactivated_people_and_functions_cannot_be_planned(self) -> None:
        personnel.set_person_active(self.anna, active=False)
        with self.assertRaises(ValidationError):
            plan(self.project, self.sound, self.anna)
        self.hand.is_active = False
        self.hand.save()
        with self.assertRaises(ValidationError):
            plan(self.project, self.hand)

    def test_a_new_person_brings_their_own_rate(self) -> None:
        kai = make_person("Kai Kurz", rates={"Tontechnik": "30.00"})
        line = plan(self.project, self.sound, self.anna)
        self.assertEqual(crew.update_crew_line(line, rights=ALL_RIGHTS, person=kai).hourly_rate, D("30.00"))

    def test_taking_the_person_away_opens_the_place_again(self) -> None:
        line = plan(self.project, self.sound, self.anna, cost_flat_rate=D("300.00"))
        opened = crew.update_crew_line(line, rights=ALL_RIGHTS, person=None)
        self.assertTrue(opened.is_vacant)
        self.assertIsNone(opened.hourly_rate)
        self.assertIsNone(opened.cost_flat_rate)

    def test_a_new_job_function_brings_its_price_and_the_persons_rate(self) -> None:
        line = plan(self.project, self.sound, self.anna)
        changed = crew.update_crew_line(line, rights=ALL_RIGHTS, job_function=self.hand)
        self.assertEqual(
            (changed.unit_price, changed.hourly_rate, changed.title), (D("28.00"), D("20.00"), "Stagehand, Stunde")
        )

    def test_planned_hours_follow_a_new_period_until_somebody_types_them(self) -> None:
        line = plan(self.project, self.hand, start=at(13, 8), end=at(13, 14))
        moved = crew.update_crew_line(line, rights=ALL_RIGHTS, end=at(13, 18))
        self.assertEqual(moved.planned_hours, D("10.00"))
        typed = crew.update_crew_line(moved, rights=ALL_RIGHTS, planned_hours=D("7.50"))
        again = crew.update_crew_line(typed, rights=ALL_RIGHTS, end=at(13, 20))
        self.assertEqual(again.planned_hours, D("7.50"))

    def test_a_closed_project_takes_no_changes(self) -> None:
        """PRJ-009."""
        line = plan(self.project, self.sound, self.anna)
        self.project.status = ProjectStatus.CLOSED
        self.project.save()
        self.project.refresh_from_db()
        with self.assertRaises(ValidationError):
            plan(self.project, self.hand)
        line.refresh_from_db()
        with self.assertRaises(ValidationError):
            crew.update_crew_line(line, rights=ALL_RIGHTS, note="zu spät")
        with self.assertRaises(ValidationError):
            crew.delete_crew_line(line)

    def test_unknown_fields_are_refused(self) -> None:
        line = plan(self.project, self.sound, self.anna)
        with self.assertRaises(ValidationError):
            crew.update_crew_line(line, rights=ALL_RIGHTS, position=7)


class CrewPriceTests(RentalarsTestCase):
    """PRJ-051, PRJ-052, PRJ-061, PER-008, PER-018: price for the customer, cost for the company."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest")
        self.sound = job_function("Tontechnik", price="45.00", guide="32.00")
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})

    def price(self, line: object) -> crew.CrewPrice:
        return next(price for price in crew.price_crew_lines(self.project) if price.line == line)

    def test_by_plan_the_planned_hours_are_charged(self) -> None:
        line = plan(self.project, self.sound, self.anna, planned_hours=D("8"), billing=CrewBilling.PLAN)
        price = self.price(line)
        self.assertEqual((price.amount, price.cost), (D("360.00"), D("280.00")))
        self.assertFalse(price.is_estimate)
        # PER-036: a new line of a service by the hour is billed by effort – an estimate until times come.
        self.assertTrue(self.price(plan(self.project, self.sound, self.anna, planned_hours=D("8"))).is_estimate)

    def test_the_price_can_be_overwritten_on_the_line(self) -> None:
        line = plan(self.project, self.sound, self.anna, planned_hours=D("8"), unit_price=D("50.00"))
        self.assertEqual(self.price(line).amount, D("400.00"))

    def test_a_flat_customer_price_ignores_the_hours(self) -> None:
        """PER-018: the service product is billed "flat"."""
        day = make_product(
            "D-050",
            "Systemtechniker, Tagespauschale",
            price="420.00",
            kind=ProductKind.SERVICE,
            billing_mode=BillingMode.FLAT,
        )
        function = job_function("Videotechnik")
        function.service_product = day
        function.save()
        tom = make_person("Tom Richter", rates={"Videotechnik": "38.00"})
        line = plan(self.project, function, tom, planned_hours=D("10"))
        self.assertEqual(line.billing, CrewBilling.FLAT)
        price = self.price(line)
        self.assertEqual((price.amount, price.cost), (D("420.00"), D("380.00")))
        self.assertIsNone(price.charged_hours)

    def test_a_flat_rate_for_the_person_ignores_the_hours_too_and_both_sides_are_independent(self) -> None:
        line = plan(self.project, self.sound, self.anna, planned_hours=D("8"), cost_flat_rate=D("300.00"))
        price = self.price(line)
        self.assertEqual((price.amount, price.cost), (D("360.00"), D("300.00")))
        crew.update_crew_line(line, rights=ALL_RIGHTS, planned_hours=D("12"))
        self.assertEqual(self.price(line).cost, D("300.00"))

    def test_an_open_place_costs_the_guide_value_of_its_function(self) -> None:
        """PRJ-052."""
        line = plan(self.project, self.sound, planned_hours=D("8"))
        price = self.price(line)
        self.assertEqual((price.amount, price.cost), (D("360.00"), D("256.00")))
        self.assertTrue(price.cost_is_guide)

    def test_by_effort_the_planned_hours_stand_in_until_times_are_approved(self) -> None:
        """PRJ-061."""
        line = plan(
            self.project,
            self.sound,
            self.anna,
            planned_hours=D("8"),
            billing=CrewBilling.EFFORT,
            start=at(10, 8),
            end=at(10, 20),
        )
        price = self.price(line)
        self.assertEqual((price.amount, price.is_estimate), (D("360.00"), True))

        entry = record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 17, 30), submit=True)
        self.assertTrue(self.price(line).is_estimate)  # handed in is not approved

        record_time(self.anna, self.project, self.sound, at(11, 8), at(11, 9), submit=True)
        from rentalars.timetracking import services as times

        times.approve_entries([entry], rights=ALL_RIGHTS, user=None)
        price = self.price(line)
        self.assertEqual((price.approved_hours, price.amount, price.is_estimate), (D("9.50"), D("427.50"), False))
        self.assertEqual(price.actual_cost, D("332.50"))

    def test_a_function_without_service_product_gives_a_line_without_price(self) -> None:
        line = plan(self.project, "Fahrer", planned_hours=D("4"))
        self.assertEqual((line.unit_price, line.title, self.price(line).amount), (D("0"), "Fahrer", D("0.00")))

    def test_crew_is_part_of_the_project_sums(self) -> None:
        """PRJ-038: a block of its own with a subtotal; tax and totals include it."""
        add_line(self.project, make_product("L-010", "LED-Scheinwerfer", price="20.00"), 5, rental_days=1)
        plan(self.project, self.sound, self.anna, planned_hours=D("8"))
        plan(self.project, self.sound, planned_hours=D("2"), billing=CrewBilling.EFFORT)
        prices = compute_project_prices(self.project)
        self.assertEqual(prices.personnel_total, D("450.00"))
        self.assertEqual(prices.net_total, D("550.00"))
        self.assertEqual(prices.tax_total, D("104.50"))
        self.assertEqual(prices.gross_total, D("654.50"))
        self.assertEqual(prices.personnel_cost, D("344.00"))
        self.assertEqual(prices.contribution_margin, D("206.00"))
        self.assertTrue(prices.has_estimates)
        self.assertEqual(len(prices.crew), 2)

    def test_a_percentage_surcharge_on_the_whole_project_includes_the_crew(self) -> None:
        night = make_product(
            "A-002", "Nachtzuschlag", kind="surcharge", surcharge_type="percent", surcharge_percent="10", price=None
        )
        plan(self.project, self.sound, self.anna, planned_hours=D("8"))
        surcharge = add_line(self.project, night, 1).line
        projects.set_surcharge_targets(surcharge, [{"type": "project"}])
        prices = compute_project_prices(self.project)
        self.assertEqual(prices.surcharges_total, D("36.00"))
        self.assertEqual(prices.net_total, D("396.00"))


class CrewWarningTests(RentalarsTestCase):
    """PRJ-022: double booking, absence, job function – the planner is told, nothing is blocked."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest")
        self.other = make_project("Jazznacht")
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00", "Stagehand": "20.00"})

    def warnings(self, project: object) -> dict[int, list[str]]:
        return crew.crew_warnings(crew.load_crew_lines(project))

    def test_no_warning_when_all_is_well(self) -> None:
        plan(self.project, "Tontechnik", self.anna, start=at(10, 8), end=at(10, 18))
        plan(self.other, "Tontechnik", self.anna, start=at(10, 18), end=at(10, 23))  # touching, not overlapping
        self.assertEqual(self.warnings(self.project), {})

    def test_double_booking_in_another_project(self) -> None:
        line = plan(self.project, "Tontechnik", self.anna, start=at(10, 8), end=at(10, 18))
        plan(self.other, "Tontechnik", self.anna, start=at(10, 16), end=at(10, 23))
        (warning,) = self.warnings(self.project)[line.pk]
        self.assertIn(
            f"Projekt {self.other.number}", warning
        )  # By number only – the reader may not open the other project (AUT-016)
        self.assertIn("10.03. 16:00", warning)

    def test_double_booking_within_the_same_project(self) -> None:
        first = plan(self.project, "Tontechnik", self.anna, start=at(10, 8), end=at(10, 18))
        second = plan(self.project, "Stagehand", self.anna, start=at(10, 12), end=at(10, 14))
        warnings = self.warnings(self.project)
        self.assertIn("Stagehand", warnings[first.pk][0])
        self.assertIn("Tontechnik", warnings[second.pk][0])

    def test_cancelled_projects_do_not_count(self) -> None:
        plan(self.project, "Tontechnik", self.anna)
        plan(self.other, "Tontechnik", self.anna)
        self.other.status = ProjectStatus.CANCELLED
        self.other.save()
        self.assertEqual(self.warnings(self.project), {})

    def test_overlap_with_an_absence(self) -> None:
        line = plan(self.project, "Tontechnik", self.anna)
        personnel.save_absence(Absence(person=self.anna, kind=AbsenceKind.VACATION, start=at(11), end=at(20)))
        (warning,) = self.warnings(self.project)[line.pk]
        self.assertIn("Urlaub", warning)

    def test_open_places_never_warn(self) -> None:
        plan(self.project, "Tontechnik")
        plan(self.project, "Tontechnik")
        self.assertEqual(self.warnings(self.project), {})

    def test_number_of_queries_does_not_grow_with_the_lines(self) -> None:
        """NFA-014."""
        for number in range(10):
            person = make_person(f"Person Nr{number}", rates={"Stagehand": "18.00"})
            plan(self.project, "Stagehand", person)
            plan(self.other, "Stagehand", person)
        lines = crew.load_crew_lines(self.project)
        # Other lines, absences, availability marks (PER-021), job functions of the people.
        with self.assertNumQueries(4):
            warnings = crew.crew_warnings(lines)
        self.assertEqual(len(warnings), 10)


class TimesAndCrewLinesTests(RentalarsTestCase):
    """ZEI-021, PRJ-026: approved times count towards the line of the same person and job function."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest")
        self.sound = job_function("Tontechnik", price="45.00")
        self.hand = job_function("Stagehand", price="28.00")
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00", "Stagehand": "20.00"})

    def test_planned_and_worked_hours_stand_side_by_side(self) -> None:
        line = plan(self.project, self.sound, self.anna, planned_hours=D("8"), start=at(10, 8), end=at(10, 18))
        record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 17), break_minutes=30, approve=True)
        (price,) = crew.price_crew_lines(self.project)
        self.assertEqual(price.line, line)
        self.assertEqual((price.planned_hours, price.approved_hours), (D("8.00"), D("8.50")))

    def test_only_approved_times_count(self) -> None:
        plan(self.project, self.sound, self.anna, planned_hours=D("8"))
        record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 12))
        record_time(self.anna, self.project, self.sound, at(10, 13), at(10, 17), submit=True)
        self.assertEqual(crew.price_crew_lines(self.project)[0].approved_hours, D("0"))

    def test_with_two_lines_the_time_goes_to_the_one_of_its_day(self) -> None:
        friday = plan(self.project, self.sound, self.anna, start=at(10, 8), end=at(10, 18))
        saturday = plan(self.project, self.sound, self.anna, start=at(11, 8), end=at(11, 18))
        entry = record_time(self.anna, self.project, self.sound, at(11, 9), at(11, 12), approve=True)
        self.assertEqual(entry.crew_line, saturday)
        self.assertEqual(crew.matching_crew_line(self.project, self.anna, self.sound, at(10, 9)), friday)

    def test_times_without_matching_line_are_shown_in_the_project(self) -> None:
        plan(self.project, self.sound, self.anna)
        record_time(self.anna, self.project, self.hand, at(10, 8), at(10, 12), approve=True)
        record_time(self.anna, self.project, self.hand, at(11, 8), at(11, 10), approve=True)
        (bundle,) = crew.unassigned_times(self.project)
        self.assertEqual((bundle.person, bundle.job_function, bundle.hours), (self.anna, self.hand, D("6.00")))
        self.assertEqual(len(build_planning(self.project).loose_times), 1)

    def test_loose_times_can_be_counted_towards_an_existing_line(self) -> None:
        place = plan(self.project, self.hand, planned_hours=D("6"), billing=CrewBilling.EFFORT)
        record_time(self.anna, self.project, self.hand, at(10, 8), at(10, 12), approve=True)
        self.assertEqual(crew.assign_times(self.project, self.anna, self.hand, place), 1)
        self.assertEqual(crew.unassigned_times(self.project), [])
        self.assertEqual(crew.price_crew_lines(self.project)[0].amount, D("112.00"))

    def test_times_are_not_put_on_the_line_of_another_person(self) -> None:
        kai = make_person("Kai Kurz", rates={"Stagehand": "18.00"})
        line = plan(self.project, self.hand, kai)
        record_time(self.anna, self.project, self.hand, at(10, 8), at(10, 12), approve=True)
        with self.assertRaises(ValidationError):
            crew.assign_times(self.project, self.anna, self.hand, line)
        with self.assertRaises(ValidationError):
            crew.assign_times(make_project("Jazznacht"), self.anna, self.hand, line)

    def test_loose_times_can_become_a_line_of_their_own(self) -> None:
        record_time(self.anna, self.project, self.hand, at(10, 8), at(10, 12), approve=True)
        record_time(self.anna, self.project, self.hand, at(11, 8), at(11, 10), approve=True)
        line = crew.adopt_times_as_line(self.project, self.anna, self.hand, rights=ALL_RIGHTS)
        self.assertEqual((line.person, line.planned_hours, line.billing), (self.anna, D("6.00"), CrewBilling.EFFORT))
        self.assertEqual((line.start, line.end), (at(10, 8), at(11, 10)))
        self.assertEqual(line.hourly_rate, D("20.00"))
        (price,) = crew.price_crew_lines(self.project)
        self.assertEqual((price.approved_hours, price.amount), (D("6.00"), D("168.00")))
        with self.assertRaises(ValidationError):
            crew.adopt_times_as_line(self.project, self.anna, self.hand, rights=ALL_RIGHTS)

    def test_planning_a_person_later_collects_their_loose_times(self) -> None:
        record_time(self.anna, self.project, self.hand, at(10, 8), at(10, 12), approve=True)
        place = plan(self.project, self.hand)
        crew.update_crew_line(place, rights=ALL_RIGHTS, person=self.anna)
        self.assertEqual(crew.unassigned_times(self.project), [])

    def test_deleting_a_line_sets_its_times_loose_again(self) -> None:
        line = plan(self.project, self.sound, self.anna)
        record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 12), approve=True)
        crew.delete_crew_line(line)
        self.assertEqual(len(crew.unassigned_times(self.project)), 1)

    def test_planned_against_recorded_hours_per_function_and_person(self) -> None:
        """PRJ-026."""
        plan(self.project, self.sound, self.anna, planned_hours=D("8"))
        plan(self.project, self.hand, planned_hours=D("6"))
        plan(self.project, self.hand, planned_hours=D("6"))
        record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 17), approve=True)
        record_time(self.anna, self.project, self.sound, at(11, 8), at(11, 10), submit=True)
        record_time(self.anna, self.project, self.hand, at(11, 12), at(11, 13))
        rows = [
            (
                row["job_function"].name,
                row["person"].name if row["person"] else None,
                row["planned"],
                row["approved"],
                row["pending"],
            )
            for row in crew.planned_and_actual(self.project)
        ]
        self.assertEqual(
            rows,
            [
                ("Stagehand", None, D("12.00"), D("0"), D("0")),
                ("Stagehand", "Anna Becker", D("0"), D("0"), D("1.00")),
                ("Tontechnik", "Anna Becker", D("8.00"), D("9.00"), D("2.00")),
            ],
        )
