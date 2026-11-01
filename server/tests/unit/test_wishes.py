# SPDX-License-Identifier: GPL-3.0-or-later
"""A line can ask for a specific model or item (PRJ-064, PRJ-065, PCK-024)."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from rentalars.material.models import ItemStatus, MaterialItem
from rentalars.material.services import install_item, set_status
from rentalars.packing.models import Allocation
from rentalars.packing.services import build_overview, get_packlist, issue
from rentalars.projects.models import MaterialLine, ProjectStatus
from rentalars.projects.planning import build_planning, load_lines
from rentalars.projects.services import update_line
from rentalars.projects.wishes import load_wishes
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_line,
    at,
    make_items,
    make_model,
    make_product,
    make_project,
)
from tests.ui.base import UiTestCase, form_data


class _Desks:
    """Two models of mixing desk behind one product, three desks in all."""

    def make_desks(self) -> None:
        self.desk = make_product("T-100", "Digitalpult 32 Kanal", price="120.00")
        self.old_model = make_model("Yamaha QL5", self.desk)
        self.new_model = make_model("Yamaha DM7", self.desk)
        self.old_desk, self.second_old_desk = make_items(self.old_model, 2)
        (self.new_desk,) = make_items(self.new_model, 1)
        self.project = make_project("Stadtfest")


class WishRuleTests(_Desks, RentalarsTestCase):
    """What may be wished for, and what the line remembers."""

    def setUp(self) -> None:
        super().setUp()
        self.make_desks()

    def test_an_item_fixes_its_model(self) -> None:
        line = add_line(self.project, self.desk, 1, preferred_item=self.new_desk).line
        self.assertEqual(line.preferred_model, self.new_model)

    def test_a_model_alone_can_be_wished_for(self) -> None:
        line = add_line(self.project, self.desk, 2, preferred_model=self.old_model).line
        self.assertEqual((line.preferred_model, line.preferred_item), (self.old_model, None))

    def test_material_of_another_product_is_refused(self) -> None:
        cable = make_product("K-005", "XLR-Kabel 5 m")
        cable_model = make_model("Cordial CPM 5 FM", cable)
        (cable_item,) = make_items(cable_model, 1)
        with self.assertRaisesMessage(ValidationError, "gehört nicht zum Produkt T-100"):
            add_line(self.project, self.desk, 1, preferred_item=cable_item)
        with self.assertRaisesMessage(ValidationError, "gehört nicht zum Produkt T-100"):
            add_line(self.project, self.desk, 1, preferred_model=cable_model)

    def test_an_item_that_belongs_to_the_product_individually_counts(self) -> None:
        """PRD-003: an item can name another product than its model."""
        other = make_product("T-200", "Pult anderer Hersteller", price="90.00")
        (stray,) = make_items(make_model("Allen & Heath SQ-6", other), 1, product_override=self.desk)
        line = add_line(self.project, self.desk, 1, preferred_item=stray).line
        self.assertEqual(line.preferred_item, stray)
        # … and its model can be wished for too, because one of its items belongs to the product.
        add_line(self.project, self.desk, 1, preferred_model=stray.material_model)

    def test_only_products_with_stock_can_carry_a_wish(self) -> None:
        service = make_product("N-001", "Transport", kind="incidental", billing_mode="flat")  # PRD-045
        with self.assertRaisesMessage(ValidationError, "eigenem Bestand"):
            add_line(self.project, service, 1, preferred_item=self.new_desk)

    def test_taking_back_the_item_takes_back_the_model_it_implied(self) -> None:
        line = add_line(self.project, self.desk, 1, preferred_item=self.new_desk).line
        update_line(line, rights=ALL_RIGHTS, preferred_item=None)
        line.refresh_from_db()
        self.assertEqual((line.preferred_item, line.preferred_model), (None, None))

    def test_a_wish_never_changes_the_availability(self) -> None:
        """VFG-002: availability counts products. A wish is a hint, not a second reservation system."""
        set_status(self.new_desk, ItemStatus.DEFECTIVE, reason="Fader 3 defekt")
        result = add_line(self.project, self.desk, 2, preferred_item=self.new_desk)
        self.assertEqual(result.availability.status, "ok")


class WishWarningTests(_Desks, RentalarsTestCase):
    """A wish that cannot be met is pointed out (PRJ-064)."""

    def setUp(self) -> None:
        super().setUp()
        self.make_desks()

    def warnings(self, line: MaterialLine) -> list[str]:
        planning = build_planning(line.project)
        return next(planned.wish.warnings for planned in planning.all_lines if planned.line.pk == line.pk)

    def test_a_wish_that_can_be_met_has_no_warning(self) -> None:
        line = add_line(self.project, self.desk, 1, preferred_item=self.new_desk).line
        self.assertEqual(self.warnings(line), [])
        planned = build_planning(self.project).all_lines[0]
        self.assertEqual(planned.wish.label, f"Exemplar {self.new_desk.display_id} (Yamaha DM7)")

    def test_a_defective_item(self) -> None:
        line = add_line(self.project, self.desk, 1, preferred_item=self.new_desk).line
        set_status(self.new_desk, ItemStatus.DEFECTIVE, reason="Netzteil")
        self.assertEqual(self.warnings(line), [f"Exemplar {self.new_desk.display_id} ist defekt."])

    def test_an_item_that_only_travels_with_its_container(self) -> None:
        rack = make_items(make_model("Rack 12 HE", make_product("T-500", "Funkrack")), 1)[0]
        install_item(self.new_desk, rack)
        line = add_line(self.project, self.desk, 1, preferred_item=self.new_desk).line
        self.assertIn(f"fest in {rack.display_id} verbaut", self.warnings(line)[0])

    def test_the_same_item_wanted_twice_at_the_same_time(self) -> None:
        line = add_line(self.project, self.desk, 1, preferred_item=self.new_desk).line
        other = make_project("Messe", start=at(11), end=at(14))
        other_line = add_line(other, self.desk, 1, preferred_item=self.new_desk).line

        self.assertEqual(
            self.warnings(line),
            [f"Exemplar {self.new_desk.display_id} ist zur selben Zeit auch gewünscht: {other.number}."],
        )
        self.assertIn(self.project.number, self.warnings(other_line)[0])

    def test_wishes_at_other_times_or_of_projects_that_reserve_nothing_do_not_count(self) -> None:
        line = add_line(self.project, self.desk, 1, preferred_item=self.new_desk).line
        later = make_project("Später", start=at(20), end=at(22))
        add_line(later, self.desk, 1, preferred_item=self.new_desk)
        inquiry = make_project("Nur angefragt", status=ProjectStatus.INQUIRY)
        add_line(inquiry, self.desk, 1, preferred_item=self.new_desk)
        self.assertEqual(self.warnings(line), [])

    def test_two_lines_of_one_project_compete_as_well(self) -> None:
        first = add_line(self.project, self.desk, 1, preferred_item=self.new_desk).line
        add_line(self.project, self.desk, 1, preferred_item=self.new_desk)
        self.assertIn("zur selben Zeit auch gewünscht", self.warnings(first)[0])

    def test_more_pieces_of_a_model_wanted_than_fit_for_use(self) -> None:
        line = add_line(self.project, self.desk, 2, preferred_model=self.old_model).line
        self.assertEqual(self.warnings(line), [])

        other = make_project("Messe", start=at(11), end=at(14))
        add_line(other, self.desk, 1, preferred_model=self.old_model)
        self.assertEqual(
            self.warnings(line),
            ["Vom Modell Yamaha QL5 sind zur selben Zeit 3 Stück gewünscht, einsatzfähig sind aber nur 2."],
        )

    def test_projects_without_wishes_cost_no_extra_query(self) -> None:
        """NFA-014."""
        add_line(self.project, self.desk, 1)
        lines = load_lines(self.project)
        with self.assertNumQueries(0):
            self.assertEqual(load_wishes(self.project, lines), {})

    def test_the_number_of_queries_does_not_grow_with_the_number_of_wishes(self) -> None:
        """NFA-014."""
        for _index in range(2):
            add_line(self.project, self.desk, 1, preferred_item=self.new_desk)
        lines = load_lines(self.project)
        with CaptureQueriesContext(connection) as few:
            load_wishes(self.project, lines)
        for _index in range(6):
            add_line(self.project, self.desk, 1, preferred_model=self.old_model)
        lines = load_lines(self.project)
        with CaptureQueriesContext(connection) as many:
            load_wishes(self.project, lines)
        self.assertEqual(len(many), len(few))


class WishOnThePacklistTests(_Desks, RentalarsTestCase):
    """The warehouse sees the wish, and the issue notes the wished item (PCK-024)."""

    def setUp(self) -> None:
        super().setUp()
        self.make_desks()

    def test_the_packlist_names_the_wish(self) -> None:
        add_line(self.project, self.desk, 1, preferred_item=self.new_desk)
        add_line(self.project, self.desk, 1, preferred_model=self.old_model)
        rows = build_overview(get_packlist(self.project)).rows
        self.assertEqual(
            [row.wish for row in rows], [f"Exemplar {self.new_desk.display_id} (Yamaha DM7)", "Modell Yamaha QL5"]
        )

    def test_the_wished_item_is_noted_as_issued(self) -> None:
        """One of three desks goes out. Without the wish nobody could tell which (PCK-020)."""
        add_line(self.project, self.desk, 1, preferred_item=self.new_desk)
        issue(get_packlist(self.project))

        self.assertEqual([allocation.item for allocation in Allocation.objects.all()], [self.new_desk])
        self.assertEqual(MaterialItem.objects.get(pk=self.new_desk.pk).status, ItemStatus.IN_USE)
        self.assertEqual(MaterialItem.objects.get(pk=self.old_desk.pk).status, ItemStatus.AVAILABLE)

    def test_a_wished_item_that_is_out_elsewhere_is_not_noted_twice(self) -> None:
        other = make_project("Messe", start=at(11), end=at(14))
        add_line(other, self.desk, 1, preferred_item=self.new_desk)
        issue(get_packlist(other))

        add_line(self.project, self.desk, 1, preferred_item=self.new_desk)
        issue(get_packlist(self.project))

        self.assertEqual(Allocation.objects.filter(item=self.new_desk).count(), 1)

    def test_a_defective_wished_item_is_not_noted(self) -> None:
        add_line(self.project, self.desk, 1, preferred_item=self.new_desk)
        set_status(self.new_desk, ItemStatus.DEFECTIVE, reason="Display dunkel")
        issue(get_packlist(self.project))
        self.assertFalse(Allocation.objects.exists())


class WishPagesTests(_Desks, UiTestCase):
    """Choosing specific material in the browser (PRJ-064, PRJ-065)."""

    def setUp(self) -> None:
        super().setUp()
        self.make_desks()
        self.new_desk.serial_number = "DM7-0815"
        self.new_desk.save()

    def suggest(self, text: str) -> list[dict[str, str]]:
        return self.client.get(reverse("products:suggest"), {"q": text, "with_material": "1"}).json()

    def add(self, token: str) -> str:
        response = self.htmx(
            "post",
            reverse("projects:line_add", args=[self.project.pk]),
            {"product": token, "quantity": "1", "group": ""},
        )
        return self.assert_ok(response)

    def test_the_search_finds_a_model_by_its_name(self) -> None:
        results = self.suggest("yamaha dm")
        self.assertEqual(
            results,
            [
                {
                    "id": f"{self.desk.pk}:m{self.new_model.pk}",
                    "label": "T-100 Digitalpult 32 Kanal",
                    "detail": "Modell Yamaha DM7",
                    "hint": "Modell",
                }
            ],
        )

    def test_the_search_finds_an_item_by_id_and_by_serial_number(self) -> None:
        by_id = self.suggest(self.new_desk.display_id)
        self.assertEqual(by_id[0]["id"], f"{self.desk.pk}:i{self.new_desk.pk}")
        self.assertEqual(by_id[0]["detail"], f"Exemplar {self.new_desk.display_id}, Yamaha DM7, Serien-Nr. DM7-0815")
        by_serial = self.suggest("0815")
        self.assertEqual([result["id"] for result in by_serial], [f"{self.desk.pk}:i{self.new_desk.pk}"])

    def test_products_still_come_first_and_plain_searches_stay_plain(self) -> None:
        results = self.suggest("digitalpult")
        self.assertEqual(results[0]["id"], self.desk.pk)
        plain = self.client.get(reverse("products:suggest"), {"q": "yamaha"}).json()
        self.assertEqual(plain, [])

    def test_archived_items_and_inactive_products_are_not_offered(self) -> None:
        set_status(self.new_desk, ItemStatus.DEFECTIVE, reason="Totalschaden")
        set_status(self.new_desk, ItemStatus.RETIRED, reason="Totalschaden")
        self.assertEqual(self.suggest(self.new_desk.display_id), [])
        self.desk.is_active = False
        self.desk.save()
        self.assertEqual(self.suggest("yamaha"), [])

    def test_picking_a_model_or_an_item_adds_the_product_with_the_wish(self) -> None:
        text = self.add(f"{self.desk.pk}:i{self.new_desk.pk}")
        line = MaterialLine.objects.get(project=self.project)
        self.assertEqual(
            (line.product, line.preferred_item, line.preferred_model), (self.desk, self.new_desk, self.new_model)
        )
        self.assertIn(f"Wunsch: Exemplar {self.new_desk.display_id} (Yamaha DM7)", text)

        self.add(f"{self.desk.pk}:m{self.old_model.pk}")
        second = MaterialLine.objects.filter(project=self.project).latest("id")
        self.assertEqual((second.preferred_model, second.preferred_item), (self.old_model, None))

    def test_nonsense_from_the_search_field_is_a_message_not_a_crash(self) -> None:
        for token in ("x", f"{self.desk.pk}:q1", f"{self.desk.pk}:i", f"{self.desk.pk}:i999999", ":m1"):
            self.assertIn("Wähle ein Produkt", self.add(token), token)
        self.assertFalse(MaterialLine.objects.exists())

    def test_the_wish_is_set_and_removed_in_the_line_dialog(self) -> None:
        line = add_line(self.project, self.desk, 1).line
        url = reverse("projects:line_edit", args=[self.project.pk, line.pk])
        dialog = self.htmx("get", url)
        page = self.assert_ok(dialog)
        self.assertIn("Bestimmtes Modell", page)
        self.assertIn("Bestimmtes Exemplar (ID)", page)
        self.assertIn(f"/material/items/suggest/?product={self.desk.pk}", page)

        response = self.htmx("post", url, form_data(dialog, preferred_item_number=self.new_desk.display_id))
        self.assertIn(f"Wunsch: Exemplar {self.new_desk.display_id}", self.assert_ok(response))
        line.refresh_from_db()
        self.assertEqual((line.preferred_item, line.preferred_model), (self.new_desk, self.new_model))

        # Removing the item leaves the model that the dialog still shows.
        self.htmx("post", url, form_data(self.htmx("get", url), preferred_item_number=""))
        line.refresh_from_db()
        self.assertEqual((line.preferred_item, line.preferred_model), (None, self.new_model))

        self.htmx("post", url, form_data(self.htmx("get", url), preferred_model=""))
        line.refresh_from_db()
        self.assertIsNone(line.preferred_model)

    def test_item_and_model_must_agree_in_the_dialog(self) -> None:
        line = add_line(self.project, self.desk, 1, preferred_item=self.new_desk).line
        url = reverse("projects:line_edit", args=[self.project.pk, line.pk])
        response = self.htmx("post", url, form_data(self.htmx("get", url), preferred_model=str(self.old_model.pk)))
        self.assertIn("gehört zum Modell Yamaha DM7", self.assert_ok(response))

        unknown = self.htmx("post", url, form_data(self.htmx("get", url), preferred_item_number="9999"))
        self.assertIn("Es gibt kein Exemplar mit der ID 9999", self.assert_ok(unknown))

    def test_lines_without_stock_have_no_wish_fields(self) -> None:
        service = make_product("N-001", "Transport", kind="incidental", billing_mode="flat")  # PRD-045
        line = add_line(self.project, service, 1).line
        dialog = self.assert_ok(self.htmx("get", reverse("projects:line_edit", args=[self.project.pk, line.pk])))
        self.assertNotIn("Bestimmtes Modell", dialog)

    def test_item_suggestions_can_be_narrowed_to_one_product(self) -> None:
        cable_item = make_items(make_model("Cordial CPM 5 FM", make_product("K-005", "XLR-Kabel 5 m")), 1)[0]
        url = reverse("material:item_suggest")
        everything = [result["id"] for result in self.client.get(url, {"q": "0"}).json()]
        self.assertIn(cable_item.display_id, everything)
        of_desk = [result["id"] for result in self.client.get(url, {"q": "0", "product": self.desk.pk}).json()]
        self.assertEqual(of_desk, [self.old_desk.display_id, self.second_old_desk.display_id, self.new_desk.display_id])

    def test_the_wish_shows_on_the_packlist_page(self) -> None:
        add_line(self.project, self.desk, 1, preferred_item=self.new_desk)
        page = self.assert_ok(self.client.get(reverse("packing:packlist", args=[self.project.pk])))
        self.assertIn(f"Wunsch: Exemplar {self.new_desk.display_id} (Yamaha DM7)", page)
