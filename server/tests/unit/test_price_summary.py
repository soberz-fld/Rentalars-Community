# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests: the short description of a group's contents in the price overview (PRJ-066)."""

from __future__ import annotations

from decimal import Decimal

from rentalars.masterdata.models import Unit
from rentalars.projects.planning import build_planning
from rentalars.projects.summary import MAX_ITEMS
from tests.helpers import (
    RentalarsTestCase,
    add_group,
    add_line,
    job_function,
    make_person,
    make_product,
    make_project,
    plan,
)


class GroupSummaryTests(RentalarsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest")
        self.group = add_group(self.project, "Licht")
        self.spot = make_product("L-010", "LED-Scheinwerfer RGBW", price="20.00")
        self.truss = make_product("R-010", "Traverse 4-Punkt 2 m", price="9.00")

    def summary(self) -> str:
        return build_planning(self.project).groups[0].summary

    def test_quantities_of_the_same_product_are_added_up(self) -> None:
        add_line(self.project, self.spot, 6, group=self.group)
        add_line(self.project, self.truss, 4, group=self.group)
        add_line(self.project, self.spot, 2, group=self.group)
        self.assertEqual(self.summary(), "8 × LED-Scheinwerfer RGBW, 4 × Traverse 4-Punkt 2 m")

    def test_a_kit_is_named_as_the_kit(self) -> None:
        kit = make_product("T-100", "Aktivbox-Set", kind="kit", billing_mode="daily_kit", price="40.00")
        add_line(self.project, kit, 2, group=self.group)
        self.assertEqual(self.summary(), "2 × Aktivbox-Set")

    def test_units_other_than_pieces(self) -> None:
        metre = Unit.objects.get(name="Angefangener Meter")  # ADM-011: "m"
        flat = Unit.objects.get(name="Pauschal")
        cable = make_product("K-100", "Kabelbrücke", price="3.00", unit=metre)
        transport = make_product(
            "F-001", "Transport Sprinter", price="95.00", unit=flat, kind="incidental", billing_mode="flat"
        )
        add_line(self.project, cable, 50, group=self.group)
        add_line(self.project, transport, 1, group=self.group)
        self.assertEqual(self.summary(), "50 m Kabelbrücke, Transport Sprinter")

    def test_a_group_with_many_things_names_the_most_valuable_in_planning_order(self) -> None:
        for number in range(MAX_ITEMS + 3):
            product = make_product(f"S-{number:03d}", f"Ding {number}", price=str(10 + number))
            add_line(self.project, product, 1, group=self.group)
        summary = self.summary()
        self.assertTrue(summary.endswith("und 3 weitere Positionen"), summary)
        self.assertEqual(
            summary.split(" und ")[0], ", ".join(f"1 × Ding {number}" for number in range(3, MAX_ITEMS + 3))
        )

    def test_an_empty_group_has_no_summary(self) -> None:
        self.assertEqual(self.summary(), "")

    def test_personnel_is_summarized_by_what_is_charged_never_by_who(self) -> None:
        hand = job_function("Stagehand", price="28.00")
        anna = make_person("Anna Becker", rates={"Stagehand": "20.00"})
        plan(self.project, hand, anna, planned_hours=Decimal("8"))
        plan(self.project, hand, planned_hours=Decimal("8"))
        summary = build_planning(self.project).crew_summary
        self.assertEqual(summary, "2 × Stagehand, Stunde")
        self.assertNotIn("Anna", summary)
