# SPDX-License-Identifier: GPL-3.0-or-later
"""Bulk material built into a case, rack or vehicle (MAT-040).

The requirement: built-in bulk material. Mengenmaterial (cable by the metre, connectors,
screws) can be built into a case, rack, set or vehicle as a bill of material with a quantity:

* what is built in leaves the free stock and returns to it when taken out,
* it shows on the page of the container and of the bulk row, and in the stock of the model (built in against free),
* the packing list names it under the container as a "contains" line, without counting it a second time,
* building in and taking out are written to the history of both items with the user and the time,
* the same through the API.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse

from rentalars.accounts.models import User
from rentalars.availability.stock import stock_of_product
from rentalars.core.models import AuditLogEntry
from rentalars.material import installations
from rentalars.material.history import item_history
from rentalars.material.installed_models import InstalledQuantity
from rentalars.material.models import ItemStatus, MaterialItem
from rentalars.packing import services as packing
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_line,
    make_item,
    make_model,
    make_product,
    make_project,
    make_user,
    unit,
)
from tests.ui.base import UiTestCase


class Rig:
    """A rack case 0500 and a roll of cable 0600 with 100 m, a bag of connectors 0601 with 20 pieces."""

    def prepare(self) -> None:
        self.rack_product = make_product("S-500", "Rack-Case 12 HE")
        self.rack = make_item(make_model("Rack-Case 12 HE", self.rack_product), 500)
        self.cable_product = make_product("K-600", "Kabel 1,5 mm² (Meter)", unit=unit("Meter"))
        self.cable = make_item(make_model("Kabel 1,5 mm²", self.cable_product, bulk=True), 600, quantity=100)
        self.connector_product = make_product("K-601", "Stecker")
        self.connector = make_item(make_model("Stecker", self.connector_product, bulk=True), 601, quantity=20)


class InstallServiceTests(Rig, RentalarsTestCase):
    """MAT-040: building in and taking out change the free stock, nothing else."""

    def setUp(self) -> None:
        super().setUp()
        self.prepare()

    def test_built_in_leaves_the_free_stock_and_comes_back(self) -> None:
        installed = installations.install_quantity(self.rack, self.cable, 10)
        self.cable.refresh_from_db()
        self.assertEqual((installed.quantity, self.cable.quantity), (10, 90))
        # The stock of the product – what the planning and the availability count – is the free quantity.
        self.assertEqual(stock_of_product(self.cable_product.pk).plannable, 90)
        installations.install_quantity(self.rack, self.cable, 5, note="Reserve")
        self.assertEqual(InstalledQuantity.objects.get(container=self.rack, material=self.cable).quantity, 15)
        self.assertEqual(installations.installed_totals([self.cable.pk]), {self.cable.pk: 15})
        taken = installations.remove_quantity(self.rack, self.cable, 4)
        self.cable.refresh_from_db()
        self.assertEqual((taken, self.cable.quantity), (4, 89))
        installations.remove_quantity(self.rack, self.cable)  # the rest
        self.cable.refresh_from_db()
        self.assertEqual(self.cable.quantity, 100)
        self.assertFalse(InstalledQuantity.objects.exists())
        self.assertEqual(stock_of_product(self.cable_product.pk).plannable, 100)

    def test_the_bill_of_material_of_a_container(self) -> None:
        installations.install_quantity(self.rack, self.cable, 10)
        installations.install_quantity(self.rack, self.connector, 4)
        rows = installations.installed_in(self.rack)
        self.assertEqual([(row.material.inventory_number, row.quantity) for row in rows], [(600, 10), (601, 4)])
        self.assertEqual(
            [(row.container.inventory_number, row.quantity) for row in installations.installed_places(self.cable)],
            [(500, 10)],
        )

    def test_refused(self) -> None:
        with self.assertRaises(ValidationError):
            installations.install_quantity(self.rack, self.cable, 101)  # only 100 are free
        with self.assertRaises(ValidationError):
            installations.install_quantity(self.rack, self.cable, 0)
        with self.assertRaises(ValidationError) as caught:
            installations.install_quantity(self.cable, self.connector, 1)  # bulk material is no container
        self.assertIn("Mengenmaterial kann keine anderen Exemplare enthalten", str(caught.exception))
        with self.assertRaises(ValidationError):
            installations.install_quantity(self.rack, self.rack, 1)  # an item of single pieces is not bulk material
        self.cable.status = ItemStatus.DEFECTIVE
        self.cable.status_reason = "Mantel beschädigt"
        self.cable.save()
        with self.assertRaises(ValidationError):
            installations.install_quantity(self.rack, self.cable, 1)
        with self.assertRaises(ValidationError):
            installations.remove_quantity(self.rack, self.connector)  # nothing of it is built in
        installations.install_quantity(self.rack, self.connector, 3)
        with self.assertRaises(ValidationError):
            installations.remove_quantity(self.rack, self.connector, 4)
        self.connector.refresh_from_db()
        self.assertEqual(self.connector.quantity, 17)

    def test_an_archived_container_takes_nothing(self) -> None:
        self.rack.status = ItemStatus.RETIRED
        self.rack.save()
        with self.assertRaises(ValidationError):
            installations.install_quantity(self.rack, self.cable, 1)

    def test_an_item_with_built_in_material_is_not_archived(self) -> None:
        installations.install_quantity(self.rack, self.connector, 4)
        self.rack.status = ItemStatus.RETIRED
        with self.assertRaises(ValidationError) as caught:
            self.rack.full_clean()
        self.assertIn("Mengenmaterial verbaut", str(caught.exception))
        self.rack.status = ItemStatus.AVAILABLE
        self.connector.status = ItemStatus.RETIRED
        with self.assertRaises(ValidationError):
            self.connector.full_clean()

    def test_the_movements_name_who_and_when_in_both_histories(self) -> None:
        user = self.admin_for_log()
        from rentalars.core.audit import acting_as

        with acting_as(user):
            installations.install_quantity(self.rack, self.cable, 10, user=user)
            installations.remove_quantity(self.rack, self.cable, 3, user=user)
        events = AuditLogEntry.for_object(self.rack, include_children=False).filter(event__startswith="item.quantity")
        self.assertEqual(sorted(entry.event for entry in events), ["item.quantity_installed", "item.quantity_removed"])
        row_events = AuditLogEntry.for_object(self.cable, include_children=False).filter(
            event__startswith="item.quantity"
        )
        self.assertEqual(
            sorted(entry.event for entry in row_events), ["item.quantity_built_in", "item.quantity_taken_out"]
        )
        rows = item_history(self.rack, ALL_RIGHTS)
        summaries = [row.summary for row in rows]
        self.assertTrue(any("verbaut" in text for text in summaries), summaries)
        self.assertTrue(all(row.user for row in rows if row.kind == "event"))

    def admin_for_log(self) -> User:
        """A user whose name the history shows."""
        return make_user("lager", roles=())


class PackingListTests(Rig, RentalarsTestCase):
    """MAT-040: the packing list names what is built into a container, and does not count it twice."""

    def setUp(self) -> None:
        super().setUp()
        self.prepare()
        installations.install_quantity(self.rack, self.cable, 10)
        installations.install_quantity(self.rack, self.connector, 4)
        self.project = make_project("Messebau")
        add_line(self.project, self.rack_product, 1)
        add_line(self.project, self.cable_product, 20)  # a line of its own: free stock, besides what sits in the rack

    def test_contains_lines_under_the_rack(self) -> None:
        overview = packing.build_overview(packing.get_packlist(self.project))
        rack_row = next(row for row in overview.rows if row.product == self.rack_product)
        lines = [(line.state, line.quantity, line.display_id) for line in rack_row.contents]
        self.assertEqual(lines, [("built_in", 10, "0600"), ("built_in", 4, "0601")])
        self.assertEqual(rack_row.contents[0].unit, "m")

    def test_not_counted_twice(self) -> None:
        overview = packing.build_overview(packing.get_packlist(self.project))
        cable_row = next(row for row in overview.rows if row.product == self.cable_product)
        self.assertEqual(cable_row.required, Decimal("20"))  # its own line, not 20 + 10
        self.assertEqual(len(overview.rows), 2)
        # The 20 m of the line come out of the free stock of 90 m.
        self.assertEqual(stock_of_product(self.cable_product.pk).plannable, 90)

    def test_the_pdf_lists_them(self) -> None:
        from rentalars.packing.pdf import render_packlist_pdf

        overview = packing.build_overview(packing.get_packlist(self.project))
        self.assertTrue(render_packlist_pdf(overview, show_customer=True).startswith(b"%PDF"))


class BuiltInPageTests(Rig, UiTestCase):
    """MAT-040: the boxes on the pages of the container, the bulk row and the model."""

    def setUp(self) -> None:
        super().setUp()
        self.prepare()

    def test_build_in_and_take_out_on_the_page(self) -> None:
        page = self.assert_ok(self.client.get(reverse("material:item_detail", args=[self.rack.pk])))
        self.assertIn("Verbautes Mengenmaterial", page)
        self.assertIn("In diesem Exemplar ist nichts verbaut", page)
        response = self.client.post(
            reverse("material:built_in_add", args=[self.rack.pk]),
            {"material_number": "0600", "quantity": "12", "note": "Netzkabel"},
            follow=True,
        )
        self.assertIn("12 × 0600 in 0500 verbaut", " ".join(self.messages_of(response)))
        self.cable.refresh_from_db()
        self.assertEqual(self.cable.quantity, 88)
        page = self.assert_ok(self.client.get(reverse("material:item_detail", args=[self.rack.pk])))
        self.assertIn("Netzkabel", page)
        self.assertIn("12 m", page)
        # The bulk row: free, built in, together – and where.
        row_page = self.assert_ok(self.client.get(reverse("material:item_detail", args=[self.cable.pk])))
        self.assertIn("In andere Exemplare verbaut", row_page)
        self.assertIn("0500", row_page)
        # The stock of the model shows free against built in.
        model_page = self.assert_ok(
            self.client.get(reverse("material:model_detail", args=[self.cable.material_model_id]))
        )
        self.assertIn("Verbaut", model_page)
        response = self.client.post(
            reverse("material:built_in_remove", args=[self.rack.pk, self.cable.pk]), {"quantity": "2"}, follow=True
        )
        self.assertIn("2 × 0600", " ".join(self.messages_of(response)))
        self.cable.refresh_from_db()
        self.assertEqual(self.cable.quantity, 90)

    def test_mistakes_are_named(self) -> None:
        response = self.client.post(
            reverse("material:built_in_add", args=[self.rack.pk]),
            {"material_number": "0600", "quantity": "500"},
            follow=True,
        )
        self.assertIn("Nur 100 von 0600 sind frei", " ".join(self.messages_of(response)))
        response = self.client.post(
            reverse("material:built_in_add", args=[self.rack.pk]),
            {"material_number": "9999", "quantity": "1"},
            follow=True,
        )
        self.assertIn("Es gibt kein Exemplar mit der ID", " ".join(self.messages_of(response)))
        response = self.client.post(
            reverse("material:built_in_remove", args=[self.rack.pk, self.cable.pk]), {"quantity": "x"}, follow=True
        )
        self.assertIn("ganze Zahl", " ".join(self.messages_of(response)))

    def test_only_who_may_write_material(self) -> None:
        reader = self.browser_for("lesend", "Nur-Lesen")
        response = reader.post(
            reverse("material:built_in_add", args=[self.rack.pk]), {"material_number": "0600", "quantity": "1"}
        )
        self.assertEqual(response.status_code, 403)
        self.cable.refresh_from_db()
        self.assertEqual(self.cable.quantity, 100)
        # Reading is enough to see the box, not to change it.
        page = self.assert_ok(reader.get(reverse("material:item_detail", args=[self.rack.pk])))
        self.assertNotIn("/built-in/", page)

    def test_the_suggestions_for_bulk_material(self) -> None:
        found = self.client.get(reverse("material:item_suggest"), {"q": "06", "kind": "bulk"}).json()
        self.assertEqual({entry["id"] for entry in found}, {"0600", "0601"})
        self.assertEqual(next(entry for entry in found if entry["id"] == "0601")["hint"], "20 frei")
        containers = self.client.get(reverse("material:item_suggest"), {"q": "05", "kind": "container"}).json()
        self.assertEqual([entry["id"] for entry in containers], ["0500"])


class BuiltInApiTests(Rig, ApiTestCase):
    """MAT-040 through the API: list, build in, take out – with the rights of the material."""

    def setUp(self) -> None:
        super().setUp()
        self.prepare()

    def test_build_in_list_and_take_out(self) -> None:
        url = f"{API}/material-items/{self.rack.pk}/built-in"
        response = self.admin.post(url, {"material": self.cable.pk, "quantity": 10, "note": "Netz"}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["built_in"][0]["quantity"], 10)
        self.assertEqual(body["built_in"][0]["unit"], "m")
        self.assertEqual(body["built_in"][0]["material_id"], "0600")
        listed = self.admin.get(url).json()
        self.assertEqual((listed["is_bulk"], len(listed["built_in"])), (False, 1))
        row = self.admin.get(f"{API}/material-items/{self.cable.pk}/built-in").json()
        self.assertEqual((row["is_bulk"], row["free"], row["built_in_total"]), (True, 90, 10))
        self.assertEqual(row["built_into"][0]["container"], self.rack.pk)
        removed = self.admin.post(f"{url}/{self.cable.pk}/remove", {"quantity": 4}, format="json")
        self.assertEqual(removed.status_code, 200, removed.content)
        self.assertEqual(removed.json()["built_in"][0]["quantity"], 6)
        everything = self.admin.post(f"{url}/{self.cable.pk}/remove", {}, format="json")
        self.assertEqual(everything.json()["built_in"], [])
        self.assertEqual(MaterialItem.objects.get(pk=self.cable.pk).quantity, 100)

    def test_errors_and_rights(self) -> None:
        url = f"{API}/material-items/{self.rack.pk}/built-in"
        self.assert_error(
            self.admin.post(url, {"material": self.cable.pk, "quantity": 1000}, format="json"), 400, "validation_error"
        )
        self.assert_error(
            self.admin.post(url, {"material": self.cable.pk, "quantity": "x"}, format="json"), 400, "validation_error"
        )
        self.assertEqual(self.admin.post(f"{url}/{self.connector.pk}/remove", {}, format="json").status_code, 400)
        nobody = self.client_for("niemand")
        self.assertEqual(nobody.get(url).status_code, 403)
        self.assertEqual(nobody.post(url, {"material": self.cable.pk, "quantity": 1}, format="json").status_code, 403)
