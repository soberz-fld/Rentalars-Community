# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser tests: products, kits, availability query and rental scales (PRD, VFG-011)."""

from __future__ import annotations

from decimal import Decimal

from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.masterdata.models import RentalScale
from rentalars.products.models import KitComponent, Product
from tests.helpers import add_line, at, category, make_product, make_project, make_stock
from tests.ui.base import UiTestCase, form_data


class ProductPageTests(UiTestCase):
    """Creating and maintaining products (PRD-007 to PRD-030)."""

    def test_choosing_the_category_prefills_number_and_presets(self) -> None:
        """PRD-010, PRD-030."""
        make_product("K-005")
        page = self.client.get(reverse("products:create"), {"category": category("K").pk})
        data = form_data(page)
        self.assertEqual(data["article_number"], "K-006")
        self.assertEqual(data["kind"], "rental")
        self.assertEqual(data["billing_mode"], "daily_piece")

        response = self.client.post(reverse("products:create"), {**data, "name": "XLR-Kabel 10 m", "price": "2.00"})

        product = Product.objects.get(article_number="K-006")
        self.assertRedirects(response, reverse("products:detail", args=[product.pk]))
        self.assertEqual(product.price, Decimal("2.00"))
        transport = form_data(self.client.get(reverse("products:create"), {"category": category("F").pk}))
        self.assertEqual(transport["article_number"], "F-001")
        self.assertNotEqual(transport["kind"], "rental")

    def test_wrong_article_number_is_explained_at_the_field(self) -> None:
        page = self.client.get(reverse("products:create"), {"category": category("K").pk})
        response = self.client.post(
            reverse("products:create"), form_data(page, name="Kabel", price="1", article_number="L-001")
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("article_number", response.context["form"].errors)
        self.assertFalse(Product.objects.filter(name="Kabel").exists())

    def test_list_searches_and_shows_stock(self) -> None:
        make_stock("K-005", 9, "XLR-Kabel 5 m")
        make_product("L-010", "LED-Scheinwerfer")
        page = self.assert_ok(self.client.get(reverse("products:list"), {"q": "xlr"}))
        self.assertIn("K-005", page)
        self.assertNotIn("L-010", page)
        self.assertIn(">9 Stk.<", page)

    def test_detail_shows_assigned_material_and_availability_in_a_period(self) -> None:
        """PRD-026, VFG-011."""
        cable = make_stock("K-005", 9, "XLR-Kabel 5 m")
        project = make_project("Stadtfest", start=at(10), end=at(12))
        add_line(project, cable, 6)

        page = self.assert_ok(
            self.client.get(
                reverse("products:detail", args=[cable.pk]), {"start": "2027-03-11T00:00", "end": "2027-03-13T00:00"}
            )
        )
        self.assertIn("Modell K-005", page)
        self.assertIn("Stadtfest", page)
        self.assertIn(project.number, page)
        verdict = self.client.get(
            reverse("products:detail", args=[cable.pk]), {"start": "2027-03-11T00:00", "end": "2027-03-13T00:00"}
        ).context["availability"]
        self.assertEqual((verdict.stock.plannable, verdict.firm, verdict.free), (9, 6, 3))

    def test_deactivate_reactivate_and_delete(self) -> None:
        """PRD-024."""
        product = make_product("K-005")
        self.client.post(reverse("products:set_active", args=[product.pk]), {"active": "0"})
        product.refresh_from_db()
        self.assertFalse(product.is_active)
        self.client.post(reverse("products:set_active", args=[product.pk]), {"active": "1"})
        product.refresh_from_db()
        self.assertTrue(product.is_active)
        add_line(make_project(), product, 1)
        blocked = self.client.post(reverse("products:delete", args=[product.pk]), follow=True)
        self.assertTrue(Product.objects.filter(pk=product.pk).exists())
        self.assertTrue(self.messages_of(blocked))
        unused = make_product("K-006")
        self.client.post(reverse("products:delete", args=[unused.pk]))
        self.assertFalse(Product.objects.filter(pk=unused.pk).exists())

    def test_without_price_right_the_form_has_no_price_fields(self) -> None:
        """AUT-019."""
        product = make_product("K-005", price="1.50")
        Role.objects.create(name="Werkstatt", module_levels={"products": 2})
        workshop = self.browser_for("willi", "Werkstatt")
        edit = reverse("products:edit", args=[product.pk])
        page = workshop.get(edit)
        data = form_data(page)
        self.assertNotIn("price", data)
        self.assertNotIn("1,50", self.assert_ok(workshop.get(reverse("products:detail", args=[product.pk]))))

        workshop.post(edit, {**data, "name": "XLR-Kabel 5 m", "price": "0.01"})
        product.refresh_from_db()
        self.assertEqual(product.name, "XLR-Kabel 5 m")
        self.assertEqual(product.price, Decimal("1.50"))

    def test_product_suggestions_for_the_planning_field(self) -> None:
        make_stock("K-005", 9, "XLR-Kabel 5 m")
        inactive = make_product("K-006", "XLR-Kabel 6 m")
        inactive.is_active = False
        inactive.save()
        results = self.client.get(reverse("products:suggest"), {"q": "xlr"}).json()
        self.assertEqual([result["label"] for result in results], ["K-005 XLR-Kabel 5 m"])
        self.assertEqual(
            self.client.get(reverse("products:suggest"), {"q": "K-00"}).json()[0]["id"],
            Product.objects.get(article_number="K-005").pk,
        )


class KitPageTests(UiTestCase):
    """Kits (PRD-020 to PRD-022)."""

    def test_components_are_added_and_removed_on_the_product_page(self) -> None:
        kit = make_product("T-100", "Aktivbox-Set", kind="kit", billing_mode="daily_kit")
        speaker = make_product("T-010", "Aktivbox")
        url = reverse("products:component_add", args=[kit.pk])

        self.client.post(url, {"component": speaker.pk, "quantity": 2})
        self.client.post(url, {"component": speaker.pk, "quantity": 1})

        component = KitComponent.objects.get(kit=kit)
        self.assertEqual((component.component, component.quantity), (speaker, 3))
        page = self.assert_ok(self.client.get(reverse("products:detail", args=[kit.pk])))
        self.assertIn("T-010", page)
        own = self.client.post(url, {"component": kit.pk, "quantity": 1}, follow=True)
        self.assertEqual(KitComponent.objects.filter(kit=kit).count(), 1)
        self.assertTrue(self.messages_of(own))
        self.client.post(reverse("products:component_remove", args=[kit.pk, component.pk]))
        self.assertFalse(KitComponent.objects.filter(kit=kit).exists())


class RentalScalePageTests(UiTestCase):
    """Rental scales as editable tables (PRD-015, PRD-037)."""

    def test_table_is_edited_as_rows_of_days_and_factor(self) -> None:
        scale = RentalScale.objects.get(is_default=True)
        url = reverse("products:scale_edit", args=[scale.pk])
        page = self.client.get(url)
        data = form_data(
            page,
            days_0=1,
            factor_0="1.0",
            days_1=2,
            factor_1="1.6",
            days_2=7,
            factor_2="4.0",
            extra_day_increment="0.4",
            # ADM-011: the default scale has seven rows; the rows 4 to 7 are emptied.
            **{f"{name}_{index}": "" for index in range(3, 7) for name in ("days", "factor")},
        )
        version_before = scale.current_version.number

        response = self.client.post(url, data)

        self.assertRedirects(response, reverse("products:scale_list"))
        scale.refresh_from_db()
        table = scale.current_version.as_table()
        self.assertEqual(scale.current_version.number, version_before + 1)
        self.assertEqual(table.factor_for(2), Decimal("1.600"))
        # Days that are not listed use the next smaller row; beyond the table the increment applies.
        self.assertEqual(table.factor_for(5), Decimal("1.600"))
        self.assertEqual(table.factor_for(9), Decimal("4.800"))
        self.assertIn("1,6", self.assert_ok(self.client.get(reverse("products:scale_list"))))

    def test_half_filled_row_is_rejected(self) -> None:
        url = reverse("products:scale_create")
        response = self.client.post(url, form_data(self.client.get(url), name="Lichtstaffel", days_0=1, factor_0=""))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(RentalScale.objects.filter(name="Lichtstaffel", versions__isnull=False).exists())

    def test_editing_scales_needs_the_special_right(self) -> None:
        manager = self.browser_for("paula", "Projektleitung")
        self.assertEqual(manager.get(reverse("products:scale_list")).status_code, 200)
        self.assertEqual(manager.get(reverse("products:scale_create")).status_code, 403)
