# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the crew: per phase (PRJ-080), continuous hours (PRJ-073, PRJ-023), per day (PER-029),
the personnel by phase and job function (PRJ-088)."""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError

from rentalars.accounts.rights import Rights
from rentalars.documents.content import _crew_position
from rentalars.personnel import services as personnel
from rentalars.products.models import BillingMode, ProductKind
from rentalars.projects import course, crew
from rentalars.projects.duplicate import copy_project
from rentalars.projects.list_sums import attach_sums
from rentalars.projects.models import CrewBilling, CrewLine, ProjectStatus, calendar_days, suggested_hours
from rentalars.projects.pricing import compute_project_prices
from rentalars.projects.project_templates import apply_template, save_as_template
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    at,
    job_function,
    make_person,
    make_product,
    make_project,
    plan,
)

D = Decimal


def oct_at(day: int, hour: int = 0, minute: int = 0) -> datetime.datetime:
    """A moment in October 2026, the month of the catalogue's example."""
    return at(day, hour, minute, month=10, year=2026)


class ContinuousHoursTests(RentalarsTestCase):
    """PRJ-073, PRJ-023: the suggested hours are end minus start, always."""

    def test_the_customers_example_gives_36_hours(self) -> None:
        """ "Tontechnik, offen, Mo 12.10. 08:00 – Di 13.10. 20:00": 36 hours, not 24."""
        self.assertEqual(suggested_hours(oct_at(12, 8), oct_at(13, 20)), D("36.00"))

    def test_any_length_is_worked_through(self) -> None:
        cases = [
            (at(13, 8), at(13, 14), "6.00"),
            (at(12, 10), at(14, 18), "56.00"),
            (at(12, 12), at(13, 12), "24.00"),
            (at(13, 8), at(13, 9, 10), "1.25"),
            (at(13, 8), at(13, 9, 5), "1.00"),
        ]
        for start, end, hours in cases:
            with self.subTest(start=start, end=end):
                self.assertEqual(suggested_hours(start, end), D(hours))

    def test_the_night_of_the_change_to_summer_time_is_an_hour_shorter(self) -> None:
        """The time that really passes: 27 to 28 March 2027, 22:00 to 06:00, is 7 hours."""
        self.assertEqual(suggested_hours(at(27, 22), at(28, 6)), D("7.00"))

    def test_a_missing_or_reversed_period_suggests_nothing(self) -> None:
        self.assertEqual(suggested_hours(None, at(13)), D("0"))
        self.assertEqual(suggested_hours(at(13), at(12)), D("0"))

    def test_a_new_line_and_a_moved_line_take_the_whole_length(self) -> None:
        project = make_project(start=oct_at(12, 8), end=oct_at(13, 20))
        line = plan(project, job_function("Tontechnik", price="20.00"))
        self.assertEqual(line.planned_hours, D("36.00"))
        moved = crew.update_crew_line(line, rights=ALL_RIGHTS, end=oct_at(14, 20))
        self.assertEqual(moved.planned_hours, D("60.00"))


class CalendarDaysTests(RentalarsTestCase):
    """PER-029: the days a line per day is charged for are the calendar days its period touches."""

    def test_days_touched(self) -> None:
        cases = [
            (oct_at(12, 8), oct_at(13, 20), 2),
            (oct_at(12, 8), oct_at(12, 20), 1),
            (oct_at(17, 22), oct_at(18, 4), 2),
            (oct_at(12, 8), oct_at(13, 0), 1),  # an end at midnight does not touch the new day
            (oct_at(12, 0), oct_at(15, 0), 3),
            (oct_at(13), oct_at(12), 1),
        ]
        for start, end, days in cases:
            with self.subTest(start=start, end=end):
                self.assertEqual(calendar_days(start, end), days)


class CrewPerPhaseTests(RentalarsTestCase):
    """PRJ-080: a crew line can belong to a phase; the phase brings its period."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(start=at(12, 8), end=at(14, 20))
        self.setup = course.add_phase(self.project, kind="setup", start=at(12, 8), end=at(12, 20))
        self.show = course.add_phase(self.project, kind="event", title="Show", start=at(13, 18), end=at(13, 23))
        self.hand = job_function("Stagehand", price="28.00", guide="18.00")
        self.anna = make_person("Anna Becker", rates={"Stagehand": "20.00"})

    def test_planned_for_a_phase_the_line_takes_its_period(self) -> None:
        lines = crew.add_crew_lines(self.project, rights=ALL_RIGHTS, job_function=self.hand, count=2, phase=self.setup)
        for line in lines:
            self.assertEqual(
                (line.phase, line.start, line.end, line.planned_hours), (self.setup, at(12, 8), at(12, 20), D("12.00"))
            )

    def test_a_period_of_its_own_stays(self) -> None:
        line = plan(self.project, self.hand, self.anna, phase=self.setup, start=at(12, 14), end=at(12, 18))
        self.assertEqual((line.phase, line.start, line.end), (self.setup, at(12, 14), at(12, 18)))

    def test_a_phase_of_another_project_is_refused(self) -> None:
        other = make_project("Jazznacht")
        phase = course.add_phase(other, kind="setup", start=at(10, 8), end=at(10, 12))
        with self.assertRaises(ValidationError) as raised:
            plan(self.project, self.hand, phase=phase)
        self.assertIn("phase", raised.exception.message_dict)
        line = plan(self.project, self.hand)
        with self.assertRaises(ValidationError):
            crew.update_crew_line(line, rights=ALL_RIGHTS, phase=phase)

    def test_a_new_phase_brings_its_period_unless_one_is_given(self) -> None:
        line = plan(self.project, self.hand, self.anna)
        moved = crew.update_crew_line(line, rights=ALL_RIGHTS, phase=self.show)
        self.assertEqual((moved.start, moved.end, moved.planned_hours), (at(13, 18), at(13, 23), D("5.00")))
        own = crew.update_crew_line(moved, rights=ALL_RIGHTS, phase=self.setup, start=at(12, 9), end=at(12, 11))
        self.assertEqual((own.phase, own.start, own.end), (self.setup, at(12, 9), at(12, 11)))
        loose = crew.update_crew_line(own, rights=ALL_RIGHTS, phase=None)
        self.assertEqual((loose.phase, loose.start, loose.end), (None, at(12, 9), at(12, 11)))

    def test_removing_the_phase_keeps_the_lines_and_their_periods(self) -> None:
        line = plan(self.project, self.hand, self.anna, phase=self.setup)
        course.delete_phase(self.setup)
        line.refresh_from_db()
        self.assertEqual((line.phase, line.start, line.end), (None, at(12, 8), at(12, 20)))

    def test_the_schedule_lists_the_crew_per_phase(self) -> None:
        first = plan(self.project, self.hand, self.anna, phase=self.setup)
        second = plan(self.project, self.hand, phase=self.show)
        loose = plan(self.project, self.hand, start=at(14, 8), end=at(14, 12))
        phases = list(self.project.phases.all())
        with self.assertNumQueries(1):
            by_phase, without = course.crew_by_phase(self.project, phases)
        self.assertEqual(
            [(entry.phase, entry.lines) for entry in by_phase], [(self.setup, [first]), (self.show, [second])]
        )
        self.assertEqual(without.lines, [loose])


class MovingAPhaseTests(RentalarsTestCase):
    """PRJ-080: moving a phase moves its crew along when asked to."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(start=at(12, 8), end=at(14, 20))
        self.phase = course.add_phase(self.project, kind="setup", start=at(12, 8), end=at(12, 20))
        self.hand = job_function("Stagehand", price="28.00")
        self.anna = make_person("Anna Becker", rates={"Stagehand": "20.00"})
        self.whole = plan(self.project, self.hand, phase=self.phase)
        self.part = plan(self.project, self.hand, self.anna, phase=self.phase, start=at(12, 14), end=at(12, 18))
        self.other = plan(self.project, self.hand, start=at(12, 8), end=at(12, 20))  # same period, no phase

    def periods(self) -> list[tuple[datetime.datetime, datetime.datetime, Decimal]]:
        lines = [self.whole, self.part, self.other]
        for line in lines:
            line.refresh_from_db()
        return [(line.start, line.end, line.planned_hours) for line in lines]

    def test_the_whole_phase_moves_and_its_crew_with_it(self) -> None:
        change = course.update_phase(self.phase, move_crew=True, start=at(12, 10), end=at(12, 22))
        self.assertEqual({line.pk for line in change.moved_crew_lines}, {self.whole.pk, self.part.pk})
        self.assertEqual(
            self.periods(),
            [
                (at(12, 10), at(12, 22), D("12.00")),  # had the phase's period: gets the new one
                (at(12, 16), at(12, 20), D("4.00")),  # moved by the change of the start, length kept
                (at(12, 8), at(12, 20), D("12.00")),  # no phase: untouched
            ],
        )

    def test_a_longer_phase_takes_along_only_the_lines_with_its_period(self) -> None:
        course.update_phase(self.phase, move_crew=True, start=at(12, 8), end=at(13, 2))
        self.assertEqual(self.periods()[:2], [(at(12, 8), at(13, 2), D("18.00")), (at(12, 14), at(12, 18), D("4.00"))])

    def test_typed_hours_stay_and_the_rate_stays(self) -> None:
        crew.update_crew_line(self.part, rights=ALL_RIGHTS, planned_hours=D("3.50"))
        personnel.set_rate(self.anna, self.hand, D("25.00"), datetime.date(2027, 3, 1))
        course.update_phase(self.phase, move_crew=True, start=at(13, 8), end=at(13, 20))
        self.part.refresh_from_db()
        self.assertEqual(
            (self.part.start, self.part.planned_hours, self.part.hourly_rate), (at(13, 14), D("3.50"), D("20.00"))
        )

    def test_without_the_box_the_crew_stays(self) -> None:
        change = course.update_phase(self.phase, move_crew=False, start=at(13, 8), end=at(13, 20))
        self.assertEqual(change.moved_crew_lines, [])
        self.assertEqual(self.periods()[0], (at(12, 8), at(12, 20), D("12.00")))
        self.whole.refresh_from_db()
        self.assertEqual(self.whole.phase, self.phase)

    def test_moved_lines_are_checked_for_double_bookings(self) -> None:
        """PRJ-022: the warnings follow the new period."""
        elsewhere = make_project("Jazznacht")
        plan(elsewhere, self.hand, self.anna, start=at(13, 15), end=at(13, 17))
        self.assertEqual(crew.crew_warnings([self.part]), {})
        moved = course.update_phase(self.phase, move_crew=True, start=at(13, 8), end=at(13, 20)).moved_crew_lines
        warnings = crew.crew_warnings(moved)
        self.assertIn(
            f"Projekt {elsewhere.number}", warnings[self.part.pk][0]
        )  # By number only – the reader may not open the other project (AUT-016)

    def test_a_closed_project_refuses(self) -> None:
        self.project.status = ProjectStatus.CLOSED
        self.project.save()
        self.phase.refresh_from_db()
        with self.assertRaises(ValidationError):
            course.update_phase(self.phase, move_crew=True, start=at(13, 8), end=at(13, 20))


class PerDayTests(RentalarsTestCase):
    """PER-029: crew lines billed per day – days × price for the customer, days × day rate as cost."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(start=oct_at(12, 8), end=oct_at(13, 20))
        self.sound = job_function("Tontechnik", price="40.00", guide="30.00")
        self.sound.guide_daily_cost_rate = D("250.00")
        self.sound.save()
        self.anna = make_person("Anna Becker")
        personnel.set_rate(self.anna, self.sound, D("35.00"), daily_rate=D("280.00"))

    def per_day(self, person: object = None, **fields: object) -> CrewLine:
        return plan(self.project, self.sound, person, billing=CrewBilling.DAY, unit_price=D("400.00"), **fields)

    def price(self, line: CrewLine) -> crew.CrewPrice:
        return next(price for price in crew.price_crew_lines(self.project) if price.line.pk == line.pk)

    def test_days_times_price_and_days_times_day_rate(self) -> None:
        line = self.per_day(self.anna)
        self.assertEqual((line.hourly_rate, line.daily_rate), (D("35.00"), D("280.00")))
        price = self.price(line)
        self.assertEqual((price.days, price.amount, price.cost), (2, D("800.00"), D("560.00")))
        self.assertTrue(price.cost_per_day)
        self.assertFalse(price.cost_is_guide)
        self.assertEqual((price.unit_kind, price.quantity, price.cost_rate), ("day", D("2"), D("280.00")))

    def test_typed_days_count(self) -> None:
        line = self.per_day(self.anna, days=3)
        self.assertEqual((self.price(line).days, self.price(line).amount), (3, D("1200.00")))

    def test_an_open_place_costs_the_day_guide_value(self) -> None:
        price = self.price(self.per_day())
        self.assertEqual((price.cost, price.cost_is_guide, price.cost_per_day), (D("500.00"), True, True))

    def test_without_any_day_rate_the_hours_count(self) -> None:
        self.sound.guide_daily_cost_rate = None
        self.sound.save()
        kai = make_person("Kai Kurz", rates={"Tontechnik": "32.00"})
        price = self.price(self.per_day(kai))
        # 36 hours × 32.00: the hourly rate, as before.
        self.assertEqual(
            (price.amount, price.cost, price.cost_per_day, price.cost_rate),
            (D("800.00"), D("1152.00"), False, D("32.00")),
        )
        self.sound.guide_cost_rate = None
        self.sound.save()
        price = self.price(self.per_day())
        self.assertEqual((price.cost, price.cost_rate, price.cost_is_guide), (D("0"), None, True))

    def test_a_flat_rate_for_the_person_wins(self) -> None:
        price = self.price(self.per_day(self.anna, cost_flat_rate=D("500.00")))
        self.assertEqual((price.cost, price.cost_per_day), (D("500.00"), False))

    def test_the_day_rate_is_fixed_on_the_line(self) -> None:
        """Like the hourly rate (PRJ-021): a later rate of the person does not reach the line."""
        line = self.per_day(self.anna)
        personnel.set_rate(self.anna, self.sound, D("36.00"), datetime.date(2026, 10, 1), daily_rate=D("300.00"))
        line.refresh_from_db()
        self.assertEqual(line.daily_rate, D("280.00"))
        kai = make_person("Kai Kurz")
        personnel.set_rate(kai, self.sound, None, daily_rate=D("260.00"))
        changed = crew.update_crew_line(line, rights=ALL_RIGHTS, person=kai)
        self.assertEqual((changed.hourly_rate, changed.daily_rate), (None, D("260.00")))
        opened = crew.update_crew_line(changed, rights=ALL_RIGHTS, person=None)
        self.assertEqual((opened.hourly_rate, opened.daily_rate), (None, None))

    def test_the_day_rate_needs_the_right_for_personnel_costs(self) -> None:
        line = self.per_day(self.anna)
        plain = Rights(module_levels={"projects": 2})
        with self.assertRaises(ValidationError):
            crew.update_crew_line(line, rights=plain, daily_rate=D("1"))
        self.assertEqual(crew.update_crew_line(line, rights=plain, days=4).days, 4)

    def test_discounts_and_their_maximum_apply(self) -> None:
        """PER-026 as for every crew line."""
        self.sound.max_discount_percent = D("5")
        self.sound.save()
        price = self.price(self.per_day(self.anna, discount_percent=D("10")))
        self.assertEqual((price.base_amount, price.discount_percent, price.amount), (D("800.00"), D("5"), D("760.00")))
        self.assertTrue(price.discount_is_capped)

    def test_a_service_product_billed_per_day_makes_lines_per_day(self) -> None:
        product = make_product(
            "D-077",
            "Systemtechnik, Tag",
            price="450.00",
            kind=ProductKind.SERVICE,
            billing_mode=BillingMode.DAILY_PER_PIECE,
        )
        function = job_function("Systemtechnik")
        function.service_product = product
        function.save()
        line = plan(self.project, function)
        self.assertEqual((line.billing, line.unit_price), (CrewBilling.DAY, D("450.00")))

    def test_project_sums_list_sums_and_planned_hours(self) -> None:
        self.per_day(self.anna)
        plan(self.project, self.sound, self.anna, planned_hours=D("4"), start=oct_at(14, 8), end=oct_at(14, 12))
        prices = compute_project_prices(self.project)
        self.assertEqual((prices.personnel_total, prices.personnel_cost), (D("960.00"), D("700.00")))
        project = self.project.__class__.objects.get(pk=self.project.pk)
        attach_sums([project], rights=ALL_RIGHTS, user=None)
        sums = project.list_sums
        # PRJ-085: the planned hours stay hours – 36 + 4.
        self.assertEqual(
            (sums.personnel_revenue, sums.personnel_cost, sums.planned_hours), (D("960.00"), D("700.00"), D("40.00"))
        )

    def test_on_a_document_the_quantity_is_days(self) -> None:
        position = _crew_position("3", self.price(self.per_day(self.anna)))
        self.assertEqual(
            (position.quantity, str(position.unit), position.unit_code, position.unit_price, position.amount),
            (D("2"), "Tag", "DAY", D("400.00"), D("800.00")),
        )


class BreakdownByPhaseTests(RentalarsTestCase):
    """PRJ-088: the personnel by phase and job function."""

    def test_blocks_rows_and_sums(self) -> None:
        project = make_project(start=at(12, 8), end=at(14, 20))
        setup = course.add_phase(project, kind="setup", start=at(12, 8), end=at(12, 16))
        show = course.add_phase(project, kind="event", title="Show", start=at(13, 18), end=at(13, 23))
        hand = job_function("Stagehand", price="28.00", guide="18.00")
        sound = job_function("Tontechnik", price="40.00", guide="30.00")
        crew.add_crew_lines(project, rights=ALL_RIGHTS, job_function=hand, count=2, phase=setup)
        plan(project, sound, phase=show, billing=CrewBilling.DAY, unit_price=D("400.00"))
        plan(project, sound, phase=show, billing=CrewBilling.FLAT, unit_price=D("300.00"))
        plan(project, hand, start=at(14, 8), end=at(14, 12))
        prices = crew.price_crew_lines(project)
        with self.assertNumQueries(0):
            blocks = crew.breakdown_by_phase(prices)
        self.assertEqual([block.label for block in blocks], ["Aufbau", "Show", "Ohne Phase"])
        (hands,) = blocks[0].functions
        self.assertEqual(
            (hands.job_function, hands.places, hands.hours, hands.amount, hands.cost),
            (hand, 2, D("16.00"), D("448.00"), D("288.00")),
        )
        self.assertEqual(hands.scope, "16 Std.")
        (engineers,) = blocks[1].functions
        self.assertEqual((engineers.places, engineers.days, engineers.flat, engineers.amount), (2, 1, 1, D("700.00")))
        self.assertEqual(engineers.scope, "1 Tag, pauschal")
        self.assertEqual((blocks[2].phase, blocks[2].amount), (None, D("112.00")))
        self.assertEqual(
            sum((block.amount for block in blocks), D("0")), compute_project_prices(project).personnel_total
        )
        self.assertEqual(blocks[0].margin, D("160.00"))


class CopiesKeepThePhaseTests(RentalarsTestCase):
    """PRJ-080 with PRJ-029 and PRJ-076: a copy and a template keep the phase of a crew place."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(start=at(12, 8), end=at(14, 20))
        self.phase = course.add_phase(self.project, kind="setup", start=at(12, 8), end=at(12, 16))
        self.line = plan(self.project, "Stagehand", phase=self.phase, billing=CrewBilling.DAY, days=2)

    def test_duplicating_links_the_copy_of_the_phase(self) -> None:
        copy = copy_project(
            self.project,
            name="Nächstes Jahr",
            start=at(19, 8),
            end=at(21, 20),
            with_crew=True,
            rights=ALL_RIGHTS,
            user=None,
        ).project
        (line,) = copy.crew_lines.all()
        (phase,) = copy.phases.all()
        self.assertEqual((line.phase, line.start, line.days, line.billing), (phase, at(19, 8), 2, CrewBilling.DAY))

    def test_a_template_keeps_the_phase(self) -> None:
        template = save_as_template(self.project, name="Stadtfest", rights=ALL_RIGHTS)
        target = make_project("Neu", start=at(19, 8), end=at(21, 20))
        apply_template(template, target, rights=ALL_RIGHTS)
        (line,) = target.crew_lines.all()
        (phase,) = target.phases.all()
        self.assertEqual((line.phase, line.start, line.end), (phase, at(19, 8), at(19, 16)))
