# SPDX-License-Identifier: GPL-3.0-or-later
"""The content of a project template can be edited (PRJ-135) – groups, lines, crew places, vehicles, phases.

The service ``projects.template_content`` changes one entry at a time and keeps the references between entries intact.
Each test ends at what counts: a project made from the changed template.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils.translation import gettext

from rentalars.accounts.rights import Rights
from rentalars.products.models import ProductKind, VehicleType
from rentalars.projects import template_content as content
from rentalars.projects.defaults import install_dry_hire_template
from rentalars.projects.models import GroupKind, LineVariant, OpenItem, PhaseKind, ProjectPhase, ProjectTemplate
from rentalars.projects.project_templates import apply_template, save_as_template
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_group,
    add_line,
    at,
    job_function,
    make_product,
    make_project,
    make_stock,
    plan,
)

D = Decimal
NO_PRICES = Rights(module_levels=dict(ALL_RIGHTS.module_levels), special_rights=frozenset())


class Base(RentalarsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.speaker = make_stock("T-001", 10, "Lautsprecher", price="20.00")
        self.cable = make_stock("K-001", 50, "Kabel", price="2.00")
        self.source = make_project("Stadtfest 2027", start=at(10, 12), end=at(12, 12))
        stage = add_group(self.source, "Bühne", discount_percent=D("10"))
        add_group(self.source, "Ton", parent=stage)
        add_line(self.source, self.speaker, 4, group=stage, note="hinten links")
        add_line(self.source, self.cable, 20, group=stage)
        add_line(self.source, None, 1, title="Anfahrt", unit_price=D("80.00"))
        self.tech = job_function("Tontechnik", price="40.00")
        plan(self.source, self.tech, meeting_point="Lager")
        ProjectPhase.objects.create(project=self.source, kind=PhaseKind.SETUP, start=at(10, 14), end=at(10, 18))
        ProjectPhase.objects.create(project=self.source, kind=PhaseKind.CLEANING, start=at(12, 8), end=at(12, 10))
        OpenItem.objects.create(project=self.source, text="Strom klären")
        OpenItem.objects.create(project=self.source, text="Hotel buchen")
        self.template = save_as_template(self.source, name="Stadtfest", rights=ALL_RIGHTS)
        self.data = content.open_for_editing(self.template)

    def reload(self) -> dict:
        return ProjectTemplate.objects.get(pk=self.template.pk).content

    def key_of(self, section: str, **where: object) -> int:
        for entry in self.reload()[section]:
            if all(entry.get(name) == value for name, value in where.items()):
                return entry["key"]
        raise AssertionError(f"no {section} entry {where}")

    def make_project(self) -> object:
        target = make_project("Weinfest", start=at(20, 12, month=4), end=at(22, 12, month=4))
        self.result = apply_template(ProjectTemplate.objects.get(pk=self.template.pk), target, rights=ALL_RIGHTS)
        return target


class KeysTests(Base):
    def test_every_entry_gets_a_key_once(self) -> None:
        for section in content.KEYED:
            keys = [entry["key"] for entry in self.data[section]]
            self.assertEqual(len(keys), len(set(keys)), section)
            self.assertTrue(all(isinstance(key, int) for key in keys), section)
        self.assertEqual(content.open_for_editing(self.template), self.data)

    def test_a_template_without_keys_or_sections_can_be_opened(self) -> None:
        template = install_dry_hire_template()
        data = content.open_for_editing(template)
        self.assertEqual([phase["key"] for phase in data["phases"]], [1, 2, 3, 4])
        self.assertEqual(data["groups"], [])
        bare = ProjectTemplate.objects.create(name="Leer", content={})
        self.assertEqual(content.open_for_editing(bare)["lines"], [])

    def test_the_edited_template_still_applies_as_before(self) -> None:
        target = self.make_project()
        self.assertEqual((self.result.lines, self.result.crew, self.result.phases), (3, 1, 2))
        self.assertEqual(target.groups.count(), 2)


class GroupTests(Base):
    def test_add_a_group_below_another_and_use_it(self) -> None:
        stage = self.key_of("groups", name="Bühne")
        content.add_entry(self.template, content.GROUPS, {"name": "Licht", "parent": stage}, rights=ALL_RIGHTS)
        content.add_entry(self.template, content.GROUPS, {"name": "Strom"}, rights=ALL_RIGHTS)
        names = [(g["name"], g["parent"] is not None) for g in self.reload()["groups"]]
        self.assertEqual(names, [("Bühne", False), ("Ton", True), ("Licht", True), ("Strom", False)])
        target = self.make_project()
        self.assertEqual(sorted(target.groups.values_list("name", flat=True)), ["Bühne", "Licht", "Strom", "Ton"])

    def test_the_depth_is_limited_and_a_circle_is_impossible(self) -> None:
        ton = self.key_of("groups", name="Ton")
        content.add_entry(self.template, content.GROUPS, {"name": "Tief", "parent": ton}, rights=ALL_RIGHTS)
        deep = self.key_of("groups", name="Tief")
        with self.assertRaises(ValidationError):
            content.add_entry(self.template, content.GROUPS, {"name": "Zu tief", "parent": deep}, rights=ALL_RIGHTS)
        stage = self.key_of("groups", name="Bühne")
        with self.assertRaises(ValidationError):
            content.update_entry(
                self.template, content.GROUPS, stage, {"name": "Bühne", "parent": ton}, rights=ALL_RIGHTS
            )
        with self.assertRaises(ValidationError):
            content.update_entry(
                self.template, content.GROUPS, stage, {"name": "Bühne", "parent": stage}, rights=ALL_RIGHTS
            )

    def test_one_price_arrangement_only_and_none_without_the_price_right(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            content.add_entry(
                self.template,
                content.GROUPS,
                {"name": "X", "discount_percent": "5", "flat_price": "100"},
                rights=ALL_RIGHTS,
            )
        self.assertIn("flat_price", caught.exception.message_dict)
        stage = self.key_of("groups", name="Bühne")
        content.update_entry(
            self.template, content.GROUPS, stage, {"name": "Hauptbühne", "discount_percent": "50"}, rights=NO_PRICES
        )
        group = self.reload()["groups"][0]
        self.assertEqual((group["name"], group["discount_percent"]), ("Hauptbühne", "10.00"))  # kept as it was
        content.add_entry(self.template, content.GROUPS, {"name": "Neu", "flat_price": "9"}, rights=NO_PRICES)
        self.assertIsNone(self.reload()["groups"][-1]["flat_price"])
        content.update_entry(
            self.template, content.GROUPS, stage, {"name": "Hauptbühne", "discount_percent": "50"}, rights=ALL_RIGHTS
        )
        self.assertEqual(self.reload()["groups"][0]["discount_percent"], "50.00")

    def test_delete_keeps_the_content_one_level_up(self) -> None:
        stage = self.key_of("groups", name="Bühne")
        content.delete_entry(self.template, content.GROUPS, stage)
        data = self.reload()
        self.assertEqual([(g["name"], g["parent"]) for g in data["groups"]], [("Ton", None)])
        self.assertEqual([line["group"] for line in data["lines"] if line["product"]], [None, None])
        target = self.make_project()
        self.assertEqual(target.material_lines.count(), 3)

    def test_delete_with_content_takes_lines_and_subgroups_along(self) -> None:
        stage = self.key_of("groups", name="Bühne")
        content.delete_entry(self.template, content.GROUPS, stage, with_content=True)
        data = self.reload()
        self.assertEqual(data["groups"], [])
        self.assertEqual([line["title"] for line in data["lines"]], ["Anfahrt"])

    def test_what_an_alternative_replaced_turns_optional_when_it_goes(self) -> None:
        stage = self.key_of("groups", name="Bühne")
        content.add_entry(
            self.template,
            content.GROUPS,
            {"name": "Variante", "kind": GroupKind.ALTERNATIVE, "alternative_to": stage},
            rights=ALL_RIGHTS,
        )
        content.delete_entry(self.template, content.GROUPS, stage, with_content=True)
        variant = self.reload()["groups"][0]
        self.assertEqual((variant["kind"], variant["alternative_to"]), (GroupKind.OPTIONAL, None))

    def test_an_alternative_needs_the_kind_and_a_target_that_is_no_alternative(self) -> None:
        stage = self.key_of("groups", name="Bühne")
        with self.assertRaises(ValidationError):
            content.add_entry(self.template, content.GROUPS, {"name": "A", "alternative_to": stage}, rights=ALL_RIGHTS)
        content.add_entry(
            self.template,
            content.GROUPS,
            {"name": "A", "kind": "alternative", "alternative_to": stage},
            rights=ALL_RIGHTS,
        )
        first = self.key_of("groups", name="A")
        with self.assertRaises(ValidationError):
            content.add_entry(
                self.template,
                content.GROUPS,
                {"name": "B", "kind": "alternative", "alternative_to": first},
                rights=ALL_RIGHTS,
            )

    def test_move_a_group_with_its_subgroups_among_its_siblings(self) -> None:
        content.add_entry(self.template, content.GROUPS, {"name": "Strom"}, rights=ALL_RIGHTS)
        strom = self.key_of("groups", name="Strom")
        content.move_entry(self.template, content.GROUPS, strom, -1)
        self.assertEqual([g["name"] for g in self.reload()["groups"]], ["Strom", "Bühne", "Ton"])
        content.move_entry(self.template, content.GROUPS, strom, -1)  # at the top: nothing happens
        self.assertEqual([g["name"] for g in self.reload()["groups"]], ["Strom", "Bühne", "Ton"])
        stage = self.key_of("groups", name="Bühne")
        content.move_entry(self.template, content.GROUPS, stage, 1)
        self.assertEqual([g["name"] for g in self.reload()["groups"]], ["Strom", "Bühne", "Ton"])  # last at its level
        content.move_entry(self.template, content.GROUPS, strom, 1)
        self.assertEqual([g["name"] for g in self.reload()["groups"]], ["Bühne", "Ton", "Strom"])

    def test_move_a_group_to_another_parent(self) -> None:
        content.add_entry(self.template, content.GROUPS, {"name": "Strom"}, rights=ALL_RIGHTS)
        strom, stage = self.key_of("groups", name="Strom"), self.key_of("groups", name="Bühne")
        content.update_entry(
            self.template, content.GROUPS, strom, {"name": "Strom", "parent": stage}, rights=ALL_RIGHTS
        )
        self.assertEqual(
            [(g["name"], g["parent"]) for g in self.reload()["groups"]],
            [("Bühne", None), ("Ton", stage), ("Strom", stage)],
        )


class LineTests(Base):
    def test_add_a_product_a_free_and_a_text_line(self) -> None:
        stage = self.key_of("groups", name="Bühne")
        content.add_entry(
            self.template,
            content.LINES,
            {"product": self.speaker.pk, "quantity": "3", "group": stage},
            rights=ALL_RIGHTS,
        )
        content.add_entry(
            self.template,
            content.LINES,
            {"title": "Aufbauhilfe", "quantity": "3", "unit_price": "45"},
            rights=ALL_RIGHTS,
        )
        content.add_entry(
            self.template,
            content.LINES,
            {"is_text": True, "title": "Hinweis", "note": "Bitte beachten"},
            rights=ALL_RIGHTS,
        )
        target = self.make_project()
        self.assertEqual(self.result.lines, 6)
        free = target.material_lines.get(title="Aufbauhilfe")
        self.assertEqual((free.quantity, free.unit_price), (D("3"), D("45.00")))
        self.assertTrue(target.material_lines.get(title="Hinweis").is_text)
        self.assertEqual(target.material_lines.filter(product=self.speaker, group__name="Bühne").count(), 2)

    def test_pieces_of_stocked_material_are_whole(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            content.add_entry(
                self.template, content.LINES, {"product": self.speaker.pk, "quantity": "2,5"}, rights=ALL_RIGHTS
            )
        self.assertIn("quantity", caught.exception.message_dict)

    def test_change_a_line_and_the_new_project_follows(self) -> None:
        key = self.key_of("lines", product=self.speaker.pk)
        content.update_entry(
            self.template,
            content.LINES,
            key,
            {"product": self.speaker.pk, "quantity": "8", "note": "vorne"},
            rights=ALL_RIGHTS,
        )
        target = self.make_project()
        line = target.material_lines.get(product=self.speaker)
        self.assertEqual((line.quantity, line.note), (D("8"), "vorne"))

    def test_a_line_has_a_product_or_a_title_and_a_service_is_no_material(self) -> None:
        with self.assertRaises(ValidationError):
            content.add_entry(self.template, content.LINES, {"quantity": "1"}, rights=ALL_RIGHTS)
        service = make_product("S-001", "Beratung", kind=ProductKind.SERVICE)
        with self.assertRaises(ValidationError) as caught:
            content.add_entry(self.template, content.LINES, {"product": service.pk}, rights=ALL_RIGHTS)
        self.assertIn("product", caught.exception.message_dict)
        with self.assertRaises(ValidationError):
            content.add_entry(self.template, content.LINES, {"product": 999999}, rights=ALL_RIGHTS)
        with self.assertRaises(ValidationError):
            content.add_entry(
                self.template, content.LINES, {"product": self.speaker.pk, "quantity": "0"}, rights=ALL_RIGHTS
            )
        with self.assertRaises(ValidationError):
            content.add_entry(
                self.template, content.LINES, {"product": self.speaker.pk, "group": 999}, rights=ALL_RIGHTS
            )

    def test_a_sale_needs_a_sale_price(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            content.add_entry(
                self.template, content.LINES, {"product": self.speaker.pk, "is_sale": True}, rights=ALL_RIGHTS
            )
        self.assertIn("is_sale", caught.exception.message_dict)

    def test_the_price_of_a_free_line_is_only_changed_with_the_price_right(self) -> None:
        key = self.key_of("lines", title="Anfahrt")
        content.update_entry(
            self.template, content.LINES, key, {"title": "Anfahrt weit", "unit_price": "1"}, rights=NO_PRICES
        )
        line = next(e for e in self.reload()["lines"] if e["key"] == key)
        self.assertEqual((line["title"], line["unit_price"]), ("Anfahrt weit", "80.00"))
        content.update_entry(
            self.template, content.LINES, key, {"title": "Anfahrt weit", "unit_price": "95"}, rights=ALL_RIGHTS
        )
        self.assertEqual(self.make_project().material_lines.get(title="Anfahrt weit").unit_price, D("95.00"))

    def test_an_alternative_line_and_its_counterpart(self) -> None:
        main = self.key_of("lines", product=self.speaker.pk)
        content.add_entry(
            self.template,
            content.LINES,
            {"product": self.cable.pk, "variant": LineVariant.ALTERNATIVE, "alternative_to": main},
            rights=ALL_RIGHTS,
        )
        with self.assertRaises(ValidationError):
            content.add_entry(
                self.template, content.LINES, {"product": self.cable.pk, "alternative_to": main}, rights=ALL_RIGHTS
            )
        content.delete_entry(self.template, content.LINES, main)
        replaced = self.reload()["lines"][-1]
        self.assertEqual((replaced["variant"], replaced["alternative_to"]), (LineVariant.OPTIONAL, None))

    def test_move_a_line_among_the_lines_of_its_group(self) -> None:
        speaker = self.key_of("lines", product=self.speaker.pk)
        content.move_entry(self.template, content.LINES, speaker, 1)
        order = [e["product"] for e in self.reload()["lines"] if e["group"] is not None]
        self.assertEqual(order, [self.cable.pk, self.speaker.pk])
        content.move_entry(self.template, content.LINES, speaker, 1)  # last in its group
        self.assertEqual([e["product"] for e in self.reload()["lines"] if e["group"] is not None], order)

    def test_a_line_can_hang_at_the_end_of_the_project(self) -> None:
        key = self.key_of("lines", product=self.cable.pk)
        content.update_entry(
            self.template,
            content.LINES,
            key,
            {"product": self.cable.pk, "quantity": "20", "own_period": True, "anchor": "end", "start": -7200, "end": 0},
            rights=ALL_RIGHTS,
        )
        line = self.make_project().material_lines.get(product=self.cable)
        self.assertEqual((line.start, line.end), (at(22, 10, month=4), at(22, 12, month=4)))
        with self.assertRaises(ValidationError):
            content.update_entry(
                self.template,
                content.LINES,
                key,
                {"product": self.cable.pk, "own_period": True, "start": 10, "end": 5},
                rights=ALL_RIGHTS,
            )


class OtherSectionsTests(Base):
    def test_crew_places(self) -> None:
        content.add_entry(
            self.template,
            content.CREW,
            {
                "job_function": self.tech.pk,
                "planned_hours": "6",
                "meeting_point": "Halle",
                "own_period": True,
                "start": 3600,
                "end": 25200,
            },
            rights=ALL_RIGHTS,
        )
        key = self.key_of("crew", meeting_point="Lager")
        content.update_entry(
            self.template, content.CREW, key, {"job_function": self.tech.pk, "meeting_point": "Hof"}, rights=ALL_RIGHTS
        )
        target = self.make_project()
        self.assertEqual(sorted(target.crew_lines.values_list("meeting_point", flat=True)), ["Halle", "Hof"])
        with self.assertRaises(ValidationError):
            content.add_entry(self.template, content.CREW, {"job_function": 999999}, rights=ALL_RIGHTS)
        with self.assertRaises(ValidationError):
            content.add_entry(self.template, content.CREW, {}, rights=ALL_RIGHTS)

    def test_vehicle_bookings(self) -> None:
        van = make_product(
            "S-900",
            "Sprinter",
            price=None,
            kind=ProductKind.VEHICLE,
            vehicle_type=VehicleType.CAR,
            price_per_km=D("0.8"),
        )
        content.add_entry(
            self.template, content.VEHICLES, {"product": van.pk, "title": "Anfahrt", "note": "früh"}, rights=ALL_RIGHTS
        )
        with self.assertRaises(ValidationError):
            content.add_entry(self.template, content.VEHICLES, {"product": self.speaker.pk}, rights=ALL_RIGHTS)
        target = self.make_project()
        self.assertEqual(self.result.vehicles, 1)
        self.assertEqual(target.vehicle_lines.get().title, "Anfahrt")

    def test_phases_and_the_crew_places_that_name_them(self) -> None:
        content.add_entry(
            self.template,
            content.PHASES,
            {"kind": "event", "title": "Show", "start": 0, "end": 7200},
            rights=ALL_RIGHTS,
        )
        crew = self.key_of("crew", meeting_point="Lager")
        setup = self.key_of("phases", kind=PhaseKind.SETUP)
        content.update_entry(
            self.template, content.CREW, crew, {"job_function": self.tech.pk, "phase": 0}, rights=ALL_RIGHTS
        )
        content.move_entry(self.template, content.PHASES, setup, 1)  # the setup is second now
        self.assertEqual(self.reload()["crew"][0]["phase"], 1)
        content.delete_entry(self.template, content.PHASES, self.key_of("phases", kind=PhaseKind.CLEANING))
        self.assertEqual(self.reload()["crew"][0]["phase"], 0)
        content.delete_entry(self.template, content.PHASES, setup)
        self.assertIsNone(self.reload()["crew"][0]["phase"])
        target = self.make_project()
        self.assertEqual([phase.title for phase in target.phases.all()], ["Show"])

    def test_a_phase_always_has_a_period_and_a_valid_kind(self) -> None:
        with self.assertRaises(ValidationError):
            content.add_entry(
                self.template, content.PHASES, {"kind": "nonsense", "start": 0, "end": 3600}, rights=ALL_RIGHTS
            )
        with self.assertRaises(ValidationError):
            content.add_entry(
                self.template, content.PHASES, {"kind": "event", "start": 100, "end": 100}, rights=ALL_RIGHTS
            )

    def test_open_items_and_notes(self) -> None:
        content.add_entry(self.template, content.OPEN_ITEMS, {"text": "Gema anmelden"}, rights=ALL_RIGHTS)
        content.update_entry(
            self.template,
            content.OPEN_ITEMS,
            0,
            {"text": "Strom klären (Hausmeister)"},
            rights=ALL_RIGHTS,
            expect="Strom klären",
        )
        content.move_entry(self.template, content.OPEN_ITEMS, 2, -1, expect="Gema anmelden")
        self.assertEqual(self.reload()["open_items"], ["Strom klären (Hausmeister)", "Gema anmelden", "Hotel buchen"])
        content.delete_entry(self.template, content.OPEN_ITEMS, 1, expect="Gema anmelden")
        content.set_notes(self.template, notes="Immer Strom prüfen", rental_days="3")
        target = self.make_project()
        self.assertEqual(
            list(target.open_items.values_list("text", flat=True)), ["Strom klären (Hausmeister)", "Hotel buchen"]
        )
        self.assertEqual(target.notes, "Immer Strom prüfen")
        with self.assertRaises(ValidationError):
            content.add_entry(self.template, content.OPEN_ITEMS, {"text": "  "}, rights=ALL_RIGHTS)
        with self.assertRaises(ValidationError):
            content.set_notes(self.template, notes="x", rental_days="0")

    def test_a_page_that_is_out_of_date_changes_nothing(self) -> None:
        key = self.key_of("lines", title="Anfahrt")
        content.delete_entry(self.template, content.LINES, key)
        for action in (
            lambda: content.update_entry(self.template, content.LINES, key, {"title": "x"}, rights=ALL_RIGHTS),
            lambda: content.delete_entry(self.template, content.LINES, key),
            lambda: content.move_entry(self.template, content.LINES, key, 1),
            lambda: content.update_entry(
                self.template, content.OPEN_ITEMS, 0, {"text": "x"}, rights=ALL_RIGHTS, expect="anderer Text"
            ),
            lambda: content.delete_entry(self.template, content.OPEN_ITEMS, 7),
        ):
            with self.assertRaises(KeyError):
                action()
        self.assertEqual(len(self.reload()["lines"]), 2)


class WholeContentTests(Base):
    def test_what_capture_wrote_is_valid_and_unchanged_by_checking(self) -> None:
        checked = content.normalize_content(self.reload(), prices=True)
        target_a = self.make_project()
        before = (target_a.material_lines.count(), target_a.crew_lines.count(), target_a.phases.count())
        ProjectTemplate.objects.filter(pk=self.template.pk).update(content=checked)
        target_b = make_project("Zweites", start=at(20, 12, month=5), end=at(22, 12, month=5))
        apply_template(ProjectTemplate.objects.get(pk=self.template.pk), target_b, rights=ALL_RIGHTS)
        self.assertEqual(
            before, (target_b.material_lines.count(), target_b.crew_lines.count(), target_b.phases.count())
        )

    def test_replace_the_content(self) -> None:
        new = {
            "notes": "Neu",
            "groups": [{"key": 1, "name": "A"}, {"key": 2, "name": "B", "parent": 1}],
            "lines": [{"key": 1, "group": 2, "product": self.speaker.pk, "quantity": "2"}],
            "phases": [{"kind": "event", "start": 0, "end": 3600}],
            "crew": [{"job_function": self.tech.pk, "phase": 0}],
            "open_items": ["Eins"],
        }
        stored = content.replace_content(self.template, new, rights=ALL_RIGHTS)
        self.assertEqual(stored["lines"][0]["group"], 2)
        self.assertEqual(self.template.counts["groups"], 2)
        target = self.make_project()
        self.assertEqual((target.groups.count(), target.material_lines.count(), target.notes), (2, 1, "Neu"))

    def test_a_bad_content_is_refused_as_a_whole_and_nothing_changes(self) -> None:
        before = self.reload()
        bad = [
            {"unknown": 1},
            {"groups": [{"key": 1, "name": "A", "parent": 9}]},
            {"groups": [{"key": 1, "name": "A", "parent": 2}, {"key": 2, "name": "B", "parent": 1}]},
            {"lines": [{"key": 1, "title": "x", "group": 4}]},
            {"lines": [{"key": 1, "product": 999999}]},
            {"crew": [{"job_function": self.tech.pk, "phase": 3}]},
            {"groups": [{"key": 1, "name": "A"}, {"key": 1, "name": "B"}]},
            {"lines": "no list"},
            {"open_items": [5]},
            {"phases": [{"kind": "event", "start": 5, "end": 1}]},
            [],
        ]
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(ValidationError):
                content.replace_content(self.template, raw, rights=ALL_RIGHTS)
        self.assertEqual(self.reload(), before)

    def test_without_the_price_right_prices_stay_as_they_were(self) -> None:
        raw = self.reload()
        for group in raw["groups"]:
            group["discount_percent"] = "99" if group["name"] == "Bühne" else None
        for line in raw["lines"]:
            if line["title"]:
                line["unit_price"] = "1"
        stored = content.replace_content(self.template, raw, rights=NO_PRICES)
        self.assertEqual(next(g for g in stored["groups"] if g["name"] == "Bühne")["discount_percent"], "10.00")
        self.assertEqual(next(e for e in stored["lines"] if e["title"])["unit_price"], "80.00")

    def test_a_change_is_logged(self) -> None:
        from rentalars.core.models import AuditLogEntry

        content.add_entry(self.template, content.OPEN_ITEMS, {"text": "Neu"}, rights=ALL_RIGHTS)
        self.assertTrue(AuditLogEntry.objects.filter(event="project_template.content_changed").exists())

    def test_the_period_in_words(self) -> None:
        self.assertEqual(content.describe_period({"own_period": False}), gettext("whole project"))
        self.assertEqual(
            content.describe_period({"own_period": True, "start": 7200, "end": 28800}),
            gettext("from %(start)s h to %(end)s h after the start") % {"start": "2", "end": "8"},
        )
        self.assertEqual(
            content.describe_period({"own_period": True, "anchor": "end", "start": -10800, "end": -7200}),
            gettext("from %(start)s h to %(end)s h before the end") % {"start": "3", "end": "2"},
        )
