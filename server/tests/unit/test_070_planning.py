# SPDX-License-Identifier: GPL-3.0-or-later
"""Planning wishes: colours, defaults, the material utilization in hours, shortages, required fields.

* VFG-027 – the deployments of the personnel plan and of a person's timeline
  take the colours of their legend: firm, option, inquiry; requested.
* VFG-028 – the timeline, the personnel plan and the material utilization
  open with four days in hours; the calendar with the week.
* VFG-029 – the material utilization in hour columns: the peak per column,
  neighbouring columns with the same figures joined.
* PRJ-098 – what an open shortage says among the open items.
* UIX-035 – the filters that mark required fields, and what the product form
  marks.
"""

from __future__ import annotations

import datetime
import itertools
from decimal import Decimal

from django import forms
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext

from rentalars.accounts.rights import Rights
from rentalars.availability.engine import ProductShortage
from rentalars.availability.services import OpenShortage, utilization, utilization_in_periods
from rentalars.core.forms import StyledForm, mark_required
from rentalars.core.templatetags.rentalars import condition_holds, marks_required, required_condition
from rentalars.products.forms import ProductForm
from rentalars.projects.models import CrewLine, ProjectStatus
from rentalars.schedule import services
from rentalars.schedule.services import Scale
from rentalars.schedule.timelines import person_timeline
from tests.helpers import RentalarsTestCase, add_line, at, make_person, make_project, make_stock, plan

D = Decimal


def scale_of(default_days: int = 0, **query: str) -> tuple[Scale, dict]:
    request = RequestFactory().get("/schedule/timeline/", query)
    return services.scale_from_request(request, default_weeks=2, default_days=default_days)


class DeploymentColourTests(RentalarsTestCase):
    """VFG-027: a deployment is firm (orange), an option (yellow) or still an inquiry (grey)."""

    def test_the_classes_follow_the_legend(self) -> None:
        anna = make_person("Anna Becker", rates={"Lichttechnik": "35.00"})
        line = plan(make_project("Stadtfest"), "Lichttechnik", anna, start=at(10, 8), end=at(10, 18))
        for status in ProjectStatus.values:
            with self.subTest(status=status):
                line.project.status = status
                self.assertEqual(services.crew_bar_css(line), f"crew status-{status}")
        line.request_status = "requested"
        self.assertEqual(services.crew_bar_css(line), f"crew status-{line.project.status} requested")

    def test_the_personnel_plan_and_the_timeline_of_the_person_use_them(self) -> None:
        anna = make_person("Anna Becker", rates={"Lichttechnik": "35.00"})
        plan(make_project("Anfrage", status=ProjectStatus.INQUIRY), "Lichttechnik", anna, start=at(2, 8), end=at(2, 18))
        line = plan(make_project("Stadtfest"), "Lichttechnik", anna, start=at(4, 8), end=at(4, 18))
        CrewLine.objects.filter(pk=line.pk).update(request_status="requested")
        days = services.day_range(at(1).date(), 7)
        (row,) = services.personnel_rows(type(anna).objects.filter(pk=anna.pk), Scale(days=days))
        self.assertEqual([bar.css for bar in row.bars], ["crew status-inquiry", "crew status-confirmed requested"])
        timeline = person_timeline(anna, days, set())
        self.assertEqual(
            [bar.css for bar in timeline.rows[0].bars], ["crew status-inquiry", "crew status-confirmed requested"]
        )


class DefaultDaysTests(RentalarsTestCase):
    """VFG-028: four days unless asked otherwise; an address naming weeks keeps its weeks."""

    def test_four_days_are_the_default(self) -> None:
        self.assertEqual(services.DEFAULT_DAYS, 4)

    def test_an_address_without_days_and_weeks_shows_the_default_days(self) -> None:
        scale, navigation = scale_of(default_days=4, **{"from": "2027-03-10"})
        self.assertEqual(
            (scale.hours, len(scale.days), navigation["zoom"], navigation["first"]), (3, 20, 4, at(10).date())
        )
        self.assertEqual(navigation["day_count"], 4)

    def test_weeks_and_days_named_in_the_address_win(self) -> None:
        scale, navigation = scale_of(default_days=4, weeks="2", **{"from": "2027-03-08"})
        self.assertEqual((scale.hours, len(scale.days), navigation["zoom"]), (24, 14, 0))
        scale, navigation = scale_of(default_days=4, days="7", **{"from": "2027-03-08"})
        self.assertEqual((scale.hours, navigation["zoom"]), (6, 7))

    def test_without_a_default_the_weeks_stay(self) -> None:
        scale, navigation = scale_of(**{"from": "2027-03-08"})
        self.assertEqual((scale.hours, len(scale.days), navigation["zoom"]), (24, 14, 0))


class PeriodsTests(RentalarsTestCase):
    """VFG-029: the hour columns as periods on the wall clock."""

    def test_every_column_is_a_period(self) -> None:
        scale, _navigation = scale_of(days="4", **{"from": "2027-03-10"})
        periods = scale.periods
        self.assertEqual(len(periods), scale.columns)
        # VFG-033: two spans of four days before and after the chosen ones.
        self.assertEqual(periods[0], (at(2), at(2, 3)))
        self.assertEqual(periods[-1], (at(21, 21), at(22)))
        self.assertTrue(all(end == following[0] for (_start, end), following in itertools.pairwise(periods)))

    def test_the_day_the_clocks_change(self) -> None:
        scale, _navigation = scale_of(days="1", **{"from": "2027-03-28"})
        periods = scale.periods
        self.assertEqual(len(periods), 120)  # VFG-033: five days
        # 02:00 does not exist on the 28th: the column from 02 to 03 o'clock is empty, the day has 23 hours.
        day = [end.astimezone(datetime.UTC) - start.astimezone(datetime.UTC) for start, end in periods[48:72]]
        self.assertEqual(sum(day, datetime.timedelta()), datetime.timedelta(hours=23))


class UtilizationInHoursTests(RentalarsTestCase):
    """VFG-029: the reserved quantity per hour column; the same queries as per day."""

    def setUp(self) -> None:
        super().setUp()
        self.spot = make_stock("L-020", 10, "Moving Head Spot")
        add_line(make_project("Vortrag", start=at(10, 8), end=at(10, 12)), self.spot, 4)
        add_line(make_project("Messe", start=at(10, 10), end=at(10, 20)), self.spot, 3)
        add_line(make_project("Gala", start=at(10, 14), end=at(10, 22), status=ProjectStatus.OPTION), self.spot, 5)

    def test_the_peak_of_each_period(self) -> None:
        periods = [(at(10, hour), at(10, hour) + datetime.timedelta(hours=2)) for hour in range(6, 24, 2)]
        loads = utilization_in_periods([self.spot.pk], periods)[self.spot.pk]
        self.assertEqual([load.firm for load in loads], [0, 4, 7, 3, 3, 3, 3, 0, 0])
        self.assertEqual([load.optional for load in loads], [0, 0, 0, 0, 5, 5, 5, 5, 0])
        self.assertEqual((loads[2].start, loads[2].end, loads[2].day), (at(10, 10), at(10, 12), at(10).date()))
        self.assertEqual(loads[2].level, "used")  # 7 of 10: below 80 %
        # The whole day as one period gives what the utilization of the day gives.
        (day,) = utilization([self.spot.pk], [at(10).date()])[self.spot.pk]
        (whole,) = utilization_in_periods([self.spot.pk], [(at(10), at(11))])[self.spot.pk]
        self.assertEqual((whole.firm, whole.optional), (day.firm, day.optional))

    def test_as_many_queries_as_for_days(self) -> None:
        scale, _navigation = scale_of(days="10", **{"from": "2027-03-08"})
        with CaptureQueriesContext(connection) as hours:
            services.utilization_rows([self.spot], scale)
        with CaptureQueriesContext(connection) as days:
            utilization([self.spot.pk], scale.days)
        self.assertEqual(len(hours), len(days))

    def test_neighbouring_columns_with_the_same_figures_are_one_cell(self) -> None:
        scale, _navigation = scale_of(days="1", **{"from": "2027-03-10"})
        ((product, runs),) = services.utilization_rows([self.spot], scale)
        self.assertEqual(product, self.spot)
        used = [
            (run.first, run.last, run.load.firm, run.load.optional)
            for run in runs
            if run.load.firm or run.load.optional
        ]
        # One-hour columns; the 10th begins with column 49 (VFG-033: two days before it):
        # 08–10 4, 10–12 7, 12–14 3, 14–20 3 + 5, 20–22 0 + 5.
        self.assertEqual(used, [(57, 58, 4, 0), (59, 60, 7, 0), (61, 62, 3, 0), (63, 68, 3, 5), (69, 70, 0, 5)])
        self.assertEqual(runs[0].first, 1)
        self.assertEqual(runs[-1].last, scale.columns)
        self.assertEqual(sum(run.last - run.first + 1 for run in runs), scale.columns)
        self.assertEqual(runs[1].style, "grid-column: 57 / 59")
        self.assertEqual(runs[1].period, "Mi 10.03. 08:00–10:00")
        self.assertEqual(runs[1].stock, 10)
        self.assertEqual(runs[0].period, "Mo 08.03. 00:00 – Mi 10.03. 08:00")

    def test_a_run_up_to_midnight(self) -> None:
        run = services.LoadRun(first=1, last=2, load=None, start=at(10, 18), end=at(11))
        self.assertEqual(run.period, "Mi 10.03. 18:00–24:00")

    def test_the_week_modes_keep_one_load_per_day(self) -> None:
        scale, _navigation = scale_of(weeks="1", **{"from": "2027-03-08"})
        ((_product, loads),) = services.utilization_rows([self.spot], scale)
        self.assertEqual([load.day for load in loads], scale.days)
        # Per day: the firm peak, and what the options add at the busiest moment (3 + 5 against 7).
        self.assertEqual((loads[2].firm, loads[2].optional), (7, 1))


class OpenShortageTextTests(RentalarsTestCase):
    """PRJ-098: how many pieces are missing, how many of them are subrented."""

    def shortage(self, **fields: int) -> OpenShortage:
        detail = ProductShortage(product_id=1, required=4, stock=2, firm=0, optional=0, own_project=0, **fields)
        return OpenShortage(project=None, line=None, product=None, detail=detail)  # type: ignore[arg-type]

    def test_open_and_subrented(self) -> None:
        partly = self.shortage(covered=2, shortage=2, shortage_without_cover=4)
        self.assertEqual((partly.quantity, partly.missing_before_cover, partly.subrented), (2, 4, 2))
        open_only = self.shortage(covered=0, shortage=2, shortage_without_cover=2)
        self.assertEqual((open_only.missing_before_cover, open_only.subrented), (2, 0))


class _Choice(StyledForm):
    kind = forms.ChoiceField(choices=[("rental", "rental"), ("sale", "sale")])
    internal = forms.BooleanField(required=False)
    name = forms.CharField()
    price = forms.DecimalField(required=False)
    note = forms.CharField(required=False)
    owner = forms.CharField(required=False)


class RequiredMarkTests(RentalarsTestCase):
    """UIX-035: what counts as required, and when a condition holds."""

    def test_required_always_and_under_a_condition(self) -> None:
        form = _Choice(initial={"kind": "rental"})
        mark_required(form.fields["owner"])
        mark_required(form.fields["price"], "kind=rental")
        self.assertEqual(required_condition(form["name"]), "always")
        self.assertEqual(required_condition(form["owner"]), "always")
        self.assertEqual(form.fields["owner"].widget.attrs["aria-required"], "true")
        self.assertEqual(required_condition(form["price"]), "kind=rental")
        self.assertEqual(required_condition(form["note"]), "")
        self.assertTrue(marks_required(form))
        self.assertFalse(marks_required(None))
        # The validation stays as it was.
        self.assertFalse(form.fields["owner"].required)
        self.assertFalse(form.fields["price"].required)

    def test_conditions_with_and_and_or(self) -> None:
        form = _Choice(data={"kind": "sale", "name": "x"})
        price = form["price"]
        self.assertFalse(condition_holds(price, "kind=rental"))
        self.assertTrue(condition_holds(price, "kind=rental|sale"))
        self.assertTrue(condition_holds(price, "internal="))
        self.assertFalse(condition_holds(price, "internal=on"))
        self.assertFalse(condition_holds(price, "kind=sale&internal=on"))
        self.assertTrue(condition_holds(price, "kind=sale&internal="))
        self.assertTrue(condition_holds(price, "kind=rental;kind=sale&internal="))
        self.assertTrue(condition_holds(price, "missing=1"))  # a field the form does not have

    def test_the_product_form_marks_what_the_product_requires(self) -> None:
        form = ProductForm(rights=Rights.everything())
        attrs = {name: form.fields[name].widget.attrs.get("data-require-if", "") for name in form.fields}
        # PER-037: a service may wait for its price; PRD-045: incidental costs need one.
        # LOG-005: and a trailer billed per day.
        self.assertEqual(
            attrs["price"],
            "kind=rental|kit|surcharge|subrental|incidental;kind=vehicle&vehicle_type=trailer&trailer_billing=day",
        )
        self.assertEqual(attrs["sale_price"], "kind=sale")
        self.assertEqual(attrs["surcharge_percent"], "surcharge_type=percent")
        self.assertEqual(attrs["rental_scale"], "rental_scale_mode=custom")
        self.assertTrue(attrs["owner"].startswith("category="))
        self.assertFalse(form.fields["price"].required)
        without_prices = ProductForm(rights=Rights(module_levels={"products": 3}, special_rights=frozenset()))
        self.assertNotIn("price", without_prices.fields)
