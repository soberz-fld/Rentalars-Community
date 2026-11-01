# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser tests: everything still works once record IDs have four digits and more.

A template that writes an ID into a hidden field, an option or an attribute
must write it plainly. With Django's automatic thousands separator switched
on, the German pages wrote the ID 1234 as "1.234"; forms then sent back
something that is not an ID. No test noticed, because test databases start
counting at 1 – so this module starts higher.
"""

from __future__ import annotations

from django.template import Context, Template
from django.urls import reverse

from rentalars.masterdata.models import Supplier
from rentalars.material.models import MaterialItem
from rentalars.packing.models import PackEntry, Packlist
from rentalars.projects.models import MaterialLine
from tests.helpers import add_group, add_line, make_customer, make_items, make_model, make_product, make_project
from tests.ui.base import UiTestCase, form_data, forms_of


def renumber(record: object, new_id: int) -> object:
    """Give a record that nothing refers to yet a new, high ID and return it freshly loaded."""
    model = type(record)
    model.objects.filter(pk=record.pk).update(id=new_id)  # type: ignore[attr-defined]
    return model.objects.get(pk=new_id)  # type: ignore[attr-defined]


class LargeIdTests(UiTestCase):
    """IDs of 1,000 and above in pages, forms and addresses."""

    def setUp(self) -> None:
        super().setUp()
        self.customer = renumber(make_customer("Stadt Musterstadt"), 2002)
        self.cable = renumber(make_product("K-005", "XLR-Kabel 5 m", price="1.50"), 5005)
        make_items(make_model("Cordial CPM 5 FM", self.cable), 9)
        project = make_project("Stadtfest", customer=self.customer)
        # PCK-026: a confirmed project gets its main packlist at once; it refers to the old ID. Opening
        # the packlist creates it again.
        Packlist.objects.filter(project=project).delete()
        self.project = renumber(project, 4004)
        self.group = renumber(add_group(self.project, "Ton FOH"), 3003)
        self.line = renumber(add_line(self.project, self.cable, 12, group=self.group).line, 6006)

    def test_numbers_are_written_plainly_unless_a_filter_groups_them(self) -> None:
        template = Template("{% load rentalars %}{{ id }} / {{ count|thousands }} / {{ amount|money }}")
        text = template.render(Context({"id": 12345, "count": 20115, "amount": 1234}))
        self.assertEqual(text, "12345 / 20.115 / 1.234,00 €")

    def test_planning_page_and_its_forms(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.project.pk])))
        self.assertIn('data-line="6006"', page)
        self.assertIn('id="group-3003"', page)
        self.assertIn('data-group="3003"', page)
        self.assertNotRegex(page, r"\b\d\.\d{3}\b(?!,)")  # no "6.006" anywhere; amounts like 1.234,50 are fine

        # The offer to subrent the three missing cables carries the product in a hidden field.
        offer = next(
            form
            for form in forms_of(self.client.get(reverse("projects:detail", args=[self.project.pk])))
            if "quantity" in form.data and "product" in form.data and form.data["quantity"] == "3"
        )
        self.assertEqual(offer.data["product"], "5005")
        self.assertEqual(offer.target, f"/projects/{self.project.number}/lines/6006/subrent/")  # UIX-024
        accepted = self.htmx("post", offer.target, offer.data)
        self.assertIn("davon 3 zugemietet", self.assert_ok(accepted))
        self.assertTrue(MaterialLine.objects.filter(covers_line=self.line, covers_product=self.cable).exists())

    def test_adding_to_a_group_with_a_large_id(self) -> None:
        response = self.htmx(
            "post",
            reverse("projects:line_add", args=[self.project.pk]),
            {"product": self.cable.pk, "quantity": "1", "group": self.group.pk},
        )
        text = self.assert_ok(response)
        self.assertIn('<section id="group-3003" hx-swap-oob="true"', text)
        self.assertEqual(MaterialLine.objects.filter(group=self.group).count(), 2)

    def test_packlist_rows_send_back_their_ids(self) -> None:
        url = reverse("packing:packlist", args=[self.project.pk])
        page = self.client.get(url)
        self.assertIn('value="6006"', self.assert_ok(page))
        row = form_data(page, containing="line")
        self.assertEqual((row["line"], row["product"]), ("6006", "5005"))

        ticked = self.htmx("post", reverse("packing:row", args=[self.project.pk]), {**row, "quantity": "12"})

        self.assert_ok(ticked)
        self.assertEqual(PackEntry.objects.get(line=self.line).packed_quantity, 12)

    def test_filters_of_lists(self) -> None:
        projects = self.assert_ok(self.client.get(reverse("projects:list")))
        self.assertIn('<option value="2002"', projects)
        filtered = self.assert_ok(self.client.get(reverse("projects:list"), {"customer": "2002"}))
        self.assertIn("Stadtfest", filtered)

        supplier = renumber(Supplier.objects.create(name="Musikhaus"), 7007)
        MaterialItem.objects.filter(inventory_number=1).update(supplier=supplier)
        material = self.assert_ok(self.client.get(reverse("material:item_list")))
        self.assertIn('<option value="7007"', material)
        only = self.assert_ok(self.client.get(reverse("material:item_list"), {"supplier": "7007"}))
        self.assertIn(">0001<", only)
        self.assertNotIn(">0002<", only)

    def test_count_of_a_long_list_is_grouped_for_reading(self) -> None:
        model = make_model(
            "Kabelbinder", make_product("V-010", kind="sale", billing_mode="flat", price=None, sale_price="0.10")
        )
        MaterialItem.objects.bulk_create(
            [MaterialItem(inventory_number=10_000 + number, material_model=model) for number in range(1200)]
        )
        page = self.assert_ok(self.client.get(reverse("material:item_list")))
        self.assertIn("1.209 Einträge", page)
        self.assertIn("?page=2", page)
