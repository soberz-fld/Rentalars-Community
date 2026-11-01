# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages with nested groups (PRJ-037): planning, group dialog, moving, patches, price overview, packlist."""

from __future__ import annotations

import re
from decimal import Decimal

from django.urls import reverse

from rentalars.core.demo import create_demo_data
from rentalars.products.models import Product
from rentalars.projects.models import Group, MaterialLine, Project
from rentalars.projects.services import move_group, update_group
from tests.helpers import ALL_RIGHTS, add_group, add_line, make_product, make_project
from tests.ui.base import UiTestCase, form_data
from tests.ui.test_project_pages import planning_parts

D = Decimal


class PlanningPageTests(UiTestCase):
    """The planning shows the tree: indented subgroups, deeper headings, subtotals with subgroups."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(rental_days=1)
        self.light = add_group(self.project, "Licht", discount_percent=D("5"))
        self.front = add_group(self.project, "Front", parent=self.light)
        self.truss = add_group(self.project, "Traverse 1", parent=self.front)
        self.effects = add_group(self.project, "Effekte", kind="optional")
        self.laser = add_group(self.project, "Laser", parent=self.effects)
        lamp = make_product("L-010", "PAR 64", price="100.00", billing_mode="flat")
        add_line(self.project, lamp, 2, group=self.light)
        add_line(self.project, lamp, 3, group=self.truss)
        add_line(self.project, lamp, 1, group=self.laser)
        self.detail = reverse("projects:detail", args=[self.project.pk])

    def test_the_tree_on_the_planning_page(self) -> None:
        page = self.assert_ok(self.client.get(self.detail))
        # Each subgroup sits in the list of subgroups of its parent.
        children_of_light = page[page.index(f'id="group-children-{self.light.pk}"') :]
        self.assertLess(
            children_of_light.index(f'id="group-{self.front.pk}"'),
            children_of_light.index(f'id="group-{self.truss.pk}"'),
        )
        self.assertIn("<h3>Licht</h3>", page)
        self.assertIn("<h4>Front</h4>", page)
        self.assertIn("<h5>Traverse 1</h5>", page)
        # Subtotals with subgroups: Licht 200 + 300 = 500 less 5 % = 475.
        total = planning_parts(page)[f"group-total-{self.light.pk}"]
        self.assertIn("Zwischensumme Licht mit Untergruppen", total)
        self.assertIn("475,00", total)
        self.assertIn("Gruppenrabatt", total)
        self.assertNotIn(f'id="group-total-{self.truss.pk}"', page)
        self.assertIn("Zwischensumme Effekte mit Untergruppen (nicht Teil der Projektsumme)", page)
        self.assertIn("optional wie die Obergruppe", page)
        # Moving and folding: a handle per group and a toggle for each group with subgroups.
        self.assertEqual(page.count("data-group-handle"), 5)
        self.assertIn(f'aria-controls="group-children-{self.light.pk}"', page)
        self.assertNotIn(f'aria-controls="group-children-{self.truss.pk}"', page)
        self.assertIn("Teilgruppe „Licht › Front“ verschieben", page)
        # The question before deleting says what happens.
        self.assertIn("Ihre Positionen und Untergruppen wandern in die Teilgruppe „Licht“.", page)
        # The new group can go straight into a group – but not below the second level.
        options = re.findall(r'<option value="(\d+)">in ([^<]+)</option>', page)
        self.assertEqual([name for _value, name in options], ["Licht", "Licht › Front", "Effekte", "Effekte › Laser"])

    def test_a_group_is_added_into_another(self) -> None:
        response = self.htmx(
            "post", reverse("projects:group_add", args=[self.project.pk]), {"name": "Rear", "parent": self.light.pk}
        )
        self.assert_ok(response)
        rear = Group.objects.get(name="Rear")
        self.assertEqual((rear.parent, rear.position), (self.light, 2))
        refused = self.htmx(
            "post", reverse("projects:group_add", args=[self.project.pk]), {"name": "Tief", "parent": self.truss.pk}
        )
        self.assertIn("höchstens 3 Ebenen", refused.content.decode())
        self.assertFalse(Group.objects.filter(name="Tief").exists())

    def test_the_group_dialog_offers_only_allowed_parents(self) -> None:
        url = reverse("projects:group_edit", args=[self.project.pk, self.front.pk])
        dialog = self.assert_ok(self.htmx("get", url))
        # Only the list of parents: the dialog also asks what an alternative could replace (PRJ-083).
        parents = dialog[dialog.index('name="parent"') :]
        parents = parents[: parents.index("</select>")]
        choices = re.findall(r'<option value="(\d*)"[^>]*>([^<]+)</option>', parents)
        names = [name for value, name in choices if value]
        # Front has a subgroup: only top-level groups can take it.
        self.assertEqual(names, ["Licht", "Effekte"])
        self.assertIn("Übergeordnete Teilgruppe", dialog)
        response = self.htmx("post", url, form_data(self.htmx("get", url), parent=self.effects.pk))
        self.assertEqual(response["HX-Trigger"], "closeDialog")
        self.front.refresh_from_db()
        self.assertEqual((self.front.parent, self.front.position), (self.effects, 2))
        # The truss went along and is optional now, like everything in "Effekte".
        self.truss.refresh_from_db()
        self.assertEqual(self.truss.effective_kind, "optional")

    def test_moving_by_dragging_or_the_keyboard(self) -> None:
        url = reverse("projects:group_move", args=[self.project.pk, self.effects.pk])
        response = self.htmx("post", url, {"parent": self.light.pk, "position": "1"})
        self.assertEqual(response["HX-Reswap"], "outerHTML")
        self.effects.refresh_from_db()
        self.assertEqual((self.effects.parent, self.effects.position), (self.light, 1))
        # Back to the top, at the first place.
        self.htmx("post", url, {"parent": "", "position": "1"})
        self.assertEqual(
            [group.name for group in self.project.groups.filter(parent=None).order_by("position")], ["Effekte", "Licht"]
        )
        # Too deep: refused with a message, nothing changes.
        refused = self.htmx("post", url, {"parent": self.front.pk})
        self.assertIn("höchstens 3 Ebenen", refused.content.decode())
        self.effects.refresh_from_db()
        self.assertIsNone(self.effects.parent)
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_lines_move_into_a_subgroup_by_dragging(self) -> None:
        line = self.project.material_lines.get(group=self.light)
        layout = {"layout": [{"group": self.truss.pk, "lines": [line.pk]}]}
        response = self.client.post(
            reverse("projects:arrange", args=[self.project.pk]), layout, content_type="application/json"
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(MaterialLine.objects.get(pk=line.pk).group, self.truss)

    def test_the_line_dialog_names_groups_with_their_path(self) -> None:
        line = self.project.material_lines.get(group=self.light)
        dialog = self.assert_ok(self.htmx("get", reverse("projects:line_edit", args=[self.project.pk, line.pk])))
        self.assertIn("Licht › Front › Traverse 1</option>", dialog)

    def test_price_overview_csv_and_pdf(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:price_overview", args=[self.project.pk])))
        light = page[page.index(f'data-price-group="{self.light.pk}"') :]
        self.assertLess(light.index("mit Untergruppen"), light.index(f'data-price-group="{self.front.pk}"'))
        self.assertIn("<h4>", light)
        groups_only = self.assert_ok(
            self.client.get(reverse("projects:price_overview", args=[self.project.pk]), {"detail": "groups"})
        )
        self.assertIn("Enthält:", groups_only)
        csv = self.client.get(reverse("projects:price_overview_csv", args=[self.project.pk])).content.decode()
        self.assertIn("Licht › Front › Traverse 1", csv)
        pdf = self.client.get(reverse("projects:price_overview_pdf", args=[self.project.pk]))
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_packlist_and_distribution_name_the_path(self) -> None:
        cable = make_product("K-005", "Kabel")
        add_line(self.project, cable, 2, group=self.truss)
        page = self.assert_ok(self.client.get(reverse("packing:packlist_lines", args=[self.project.pk])))
        self.assertIn("Licht › Front › Traverse 1", page)


class NestedPatchTests(UiTestCase):
    """NFA-013 with PRJ-037: after a change in a subgroup the page equals a full reload, part by part."""

    def setUp(self) -> None:
        super().setUp()
        create_demo_data()
        self.project = Project.objects.get(name="Stadtfest Hauptbühne")
        self.detail = reverse("projects:detail", args=[self.project.pk])
        self.groups = {group.name: group for group in self.project.groups.all()}
        self.light = add_group(self.project, "Licht", discount_percent=D("5"))
        move_group(self.groups["Licht Front-Traverse"], parent=self.light)
        move_group(self.groups["Licht Rear-Traverse"], parent=self.light)
        self.inner = add_group(self.project, "Floor", parent=self.groups["Licht Rear-Traverse"])
        add_line(self.project, Product.objects.get(article_number="L-020"), 1, group=self.inner)

    def page(self) -> dict[str, str]:
        return planning_parts(self.assert_ok(self.client.get(self.detail)))

    def assert_patch_brings_the_page_up_to_date(self, before: dict[str, str], response: object) -> set[str]:
        self.assertEqual(response["HX-Reswap"], "none")  # type: ignore[index]
        patch = planning_parts(self.assert_ok(response))
        patch.update(
            planning_parts(self.assert_ok(self.htmx("get", reverse("projects:planning_notes", args=[self.project.pk]))))
        )
        after = self.page()
        for key, html in after.items():
            if key in patch:
                self.assertEqual(patch[key], html, f"{key} in the patch differs from the reloaded page")
            else:
                self.assertEqual(before[key], html, f"{key} changed, but was not sent again")
        self.assertLessEqual(set(patch), set(after))
        return set(patch)

    def test_a_change_deep_down_refreshes_every_subtotal_above(self) -> None:
        line = self.project.material_lines.get(group=self.inner)
        url = reverse("projects:line_edit", args=[self.project.pk, line.pk])
        before = self.page()
        response = self.htmx("post", url, form_data(self.htmx("get", url), quantity="2"))
        sent = self.assert_patch_brings_the_page_up_to_date(before, response)
        rear = self.groups["Licht Rear-Traverse"]
        self.assertLessEqual({f"group-total-{self.light.pk}", f"group-total-{rear.pk}"}, sent)
        self.assertNotEqual(before[f"group-total-{self.light.pk}"], self.page()[f"group-total-{self.light.pk}"])

    def test_every_line_of_the_nested_groups_leaves_nothing_outdated(self) -> None:
        nested = MaterialLine.objects.filter(project=self.project, group__parent__isnull=False).select_related(
            "product"
        )
        for line in nested:
            with self.subTest(line=line.title):
                url = reverse("projects:line_edit", args=[self.project.pk, line.pk])
                before = self.page()
                response = self.htmx("post", url, form_data(self.htmx("get", url), quantity=str(line.quantity + 1)))
                self.assert_patch_brings_the_page_up_to_date(before, response)

    def test_adding_a_line_to_the_parent_and_moving_a_line_out(self) -> None:
        before = self.page()
        response = self.htmx(
            "post",
            reverse("projects:line_add", args=[self.project.pk]),
            {"product": Product.objects.get(article_number="R-010").pk, "quantity": "1", "group": self.light.pk},
        )
        self.assert_patch_brings_the_page_up_to_date(before, response)
        line = self.project.material_lines.get(group=self.inner)
        url = reverse("projects:line_edit", args=[self.project.pk, line.pk])
        before = self.page()
        response = self.htmx("post", url, form_data(self.htmx("get", url), group=self.groups["Ton FOH"].pk))
        self.assert_patch_brings_the_page_up_to_date(before, response)

    def test_a_flat_price_above_with_a_maximum_discount_below(self) -> None:
        """PER-026: the cap of a line in one subgroup depends on the lines of the others."""
        from tests.helpers import add_line_before_071, job_function

        sound = job_function("Tontechnik-Max", price="45.00")  # PRD-044: with its own service product
        engineer = sound.service_product
        sound.max_discount_percent = D("1")
        sound.save()
        update_group(self.light, rights=ALL_RIGHTS, discount_percent=None, flat_price=D("500.00"))
        add_line_before_071(self.project, engineer, 2, group=self.groups["Licht Front-Traverse"])
        line = self.project.material_lines.get(group=self.inner)
        url = reverse("projects:line_edit", args=[self.project.pk, line.pk])
        before = self.page()
        response = self.htmx("post", url, form_data(self.htmx("get", url), quantity="5"))
        self.assert_patch_brings_the_page_up_to_date(before, response)
