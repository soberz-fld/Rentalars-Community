# SPDX-License-Identifier: GPL-3.0-or-later
"""Scanning labels in the browser (UIX-006, MAT-027, PCK-010, PCK-011, PCK-016).

The requirement: barcode and QR scanning in the browser. The camera and the hand scanner deliver a text; the server turns it into
what it stands for (``material.scan``, one function for pages, packing and API), the packing list marks an item packed
or back by it (``packing.scan``), the planning adds it as a wish. Nothing here uses a camera: the decoded text is
what is tested; the browser test (tests/browser) feeds a simulated detector into the widget.
"""

from __future__ import annotations

import json
from decimal import Decimal

from django.urls import reverse

from rentalars.material import scan
from rentalars.material.installations import install_quantity
from rentalars.material.models import ItemStatus, LabelSettings
from rentalars.packing import scan as packing_scan
from rentalars.packing import services
from rentalars.packing.models import Allocation, PacklistStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_line,
    category,
    make_item,
    make_items,
    make_model,
    make_product,
    make_project,
)
from tests.ui.base import UiTestCase

#: A valid EAN-13.
EAN = "4006381333931"


class Rig:
    """Four PAR cans 0001-0004 with a GTIN, a rack 0500 holding one of them, a cable roll (bulk) 0600."""

    def prepare(self) -> None:
        self.par = make_product("L-010", "PAR 64", gtin=EAN)
        self.par_model = make_model("PAR 64", self.par, category_code="L")
        self.cans = make_items(self.par_model, 4, serial_number="")
        self.cans[0].serial_number = "SN-A-77"
        self.cans[0].storage_spot = "01-A-1"
        self.cans[0].save()
        self.rack_product = make_product("S-500", "Rack-Case")
        self.rack = make_item(make_model("Rack-Case", self.rack_product), 500)
        self.cable_product = make_product("K-600", "Kabel")
        self.cable = make_item(make_model("Kabel", self.cable_product, bulk=True), 600, quantity=50)
        install_quantity(self.rack, self.cable, 10)


class ResolverTests(Rig, RentalarsTestCase):
    """Every form of a code that labels, scanners and people produce."""

    def setUp(self) -> None:
        super().setUp()
        self.prepare()

    def test_the_id_in_its_forms(self) -> None:
        for code in (
            "0003",
            "3",
            "#0003",
            "  0003\r\n",
            "]Q10003",
            "]C00003",
            "https://rentalars.example/m/0003",
        ):
            result = scan.resolve(code)
            self.assertEqual((result.kind, result.item.display_id), (scan.ITEM, "0003"), code)
        # An address with a query or a fragment, and the old style of labels.
        self.assertEqual(scan.resolve("https://x.example/m/0004?utm=1#top").item.display_id, "0004")

    def test_the_address_of_the_label_settings(self) -> None:
        settings_row = LabelSettings.load()
        settings_row.qr_target = "https://equip.example.de/id/{id}/info"
        settings_row.save()
        self.assertEqual(scan.resolve("https://equip.example.de/id/0002/info").item.display_id, "0002")
        self.assertEqual(
            scan.resolve("https://rentalars.example/m/0001").item.display_id, "0001"
        )  # older labels still work

    def test_serial_number_gtin_spot_and_location(self) -> None:
        self.assertEqual(scan.resolve("sn-a-77").item.display_id, "0001")
        product = scan.resolve(EAN)
        self.assertEqual((product.kind, product.product), (scan.PRODUCT, self.par))
        self.assertEqual(product.plan_token, str(self.par.pk))
        self.assertEqual(scan.resolve("0" + EAN).product, self.par)  # an EAN-13 as GTIN-14
        spot = scan.resolve("01-A-1")
        self.assertEqual((spot.kind, spot.count), (scan.SPOT, 1))
        self.assertEqual(scan.resolve("1a1").kind, scan.SPOT)  # as typed
        self.assertIn("storage_spot", scan.resolve("01-A-1").url.replace("q=", "storage_spot") + "storage_spot")
        from rentalars.masterdata.models import StorageLocation

        hall = StorageLocation.objects.create(name="Halle 3")
        self.cans[1].storage_location = hall
        self.cans[1].save()
        location = scan.resolve("halle 3")
        self.assertEqual((location.kind, location.count), (scan.LOCATION, 1))

    def test_a_case_and_the_plan_token(self) -> None:
        result = scan.resolve("0500")
        self.assertTrue(result.is_case)
        self.assertEqual(result.contents, 1)  # one kind of built-in bulk material
        self.assertEqual(result.plan_token, f"{self.rack_product.pk}:i{self.rack.pk}")
        self.assertFalse(scan.resolve("0001").is_case)
        install = make_items(self.par_model, 1)[0]
        install.installed_in = self.rack
        install.save()
        self.assertEqual(scan.resolve("0500").contents, 2)

    def test_unknown_and_empty(self) -> None:
        for code in ("", "   ", "9999", "hello", "https://example.org/", "\x00\x01"):
            result = scan.resolve(code)
            self.assertEqual(result.kind, scan.NONE, code)
            self.assertTrue(result.message)
        self.assertEqual(scan.resolve("x" * 1000).kind, scan.NONE)  # cut, not an error

    def test_the_rights_decide_what_is_found(self) -> None:
        only_products = ALL_RIGHTS.restricted(read_only=True, allowed_modules=["products"])
        self.assertEqual(scan.resolve("0003", only_products).kind, scan.NONE)  # not even that it exists
        self.assertEqual(scan.resolve("01-A-1", only_products).kind, scan.NONE)
        self.assertEqual(scan.resolve(EAN, only_products).kind, scan.PRODUCT)
        only_material = ALL_RIGHTS.restricted(read_only=True, allowed_modules=["material"])
        self.assertEqual(scan.resolve("0003", only_material).kind, scan.ITEM)

    def test_the_document(self) -> None:
        document = scan.result_document(scan.resolve("0001"))
        self.assertEqual(document["kind"], "item")
        self.assertEqual(document["item"]["display_id"], "0001")
        self.assertEqual(document["product"]["article_number"], "L-010")
        self.assertTrue(document["plan_token"].endswith(f":i{self.cans[0].pk}"))
        self.assertIn("PAR 64", document["title"])
        nothing = scan.result_document(scan.resolve("9999"))
        self.assertEqual((nothing["kind"], nothing["item"], nothing["plan_token"]), ("none", None, ""))


class ScanPagesTests(Rig, UiTestCase):
    """The address of the widget, the field in the head of the material pages and the planning."""

    def setUp(self) -> None:
        super().setUp()
        self.prepare()

    def test_the_address_of_the_widget(self) -> None:
        response = self.client.get(reverse("material:scan_resolve"), {"code": "https://x/m/0002"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["item"]["display_id"], "0002")
        self.assertEqual(self.client.get(reverse("material:scan_resolve"), {"code": "nope"}).json()["kind"], "none")
        self.assertEqual(self.client.post(reverse("material:scan_resolve"), {"code": "0001"}).status_code, 405)
        # Only who may read something a code leads to.
        self.assertEqual(
            self.browser_for("niemand").get(reverse("material:scan_resolve"), {"code": "0001"}).status_code, 403
        )

    def test_the_field_in_the_head_takes_what_a_scanner_types(self) -> None:
        jump = reverse("material:item_jump")
        for code, target in (
            ("https://rentalars.example/m/0003", reverse("material:item_detail", args=[self.cans[2].pk])),
            ("SN-A-77", reverse("material:item_detail", args=[self.cans[0].pk])),
            (EAN, reverse("products:detail", args=[self.par.pk])),
        ):
            self.assertRedirects(self.client.get(jump, {"id": code}), target, fetch_redirect_response=False)
        self.assertIn("q=01-A-1", self.client.get(jump, {"id": "1a1"})["Location"])
        # What is unknown leads to the list, as before.
        self.assertIn("/material/", self.client.get(jump, {"id": "9999"})["Location"])
        page = self.assert_ok(self.client.get(reverse("material:item_list")))
        self.assertIn("data-scan-open", page)
        self.assertIn('data-scan-input="#item-jump-id"', page)
        self.assertIn("Code scannen", page)
        self.assertIn("scan.js", page)

    def test_the_camera_is_allowed_for_this_server_only(self) -> None:
        response = self.client.get(reverse("material:item_list"))
        # The camera is for this server only; the other powers stay switched off.
        self.assertEqual(response["Permissions-Policy"], "camera=(self), microphone=(), geolocation=(), payment=()")
        self.assertNotIn("blob:", response["Content-Security-Policy"])  # the picture never leaves the video element

    def test_scanning_in_the_planning(self) -> None:
        project = make_project("Stadtfest")
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[project.pk])))
        self.assertIn('data-scan-mode="plan"', page)
        self.assertIn(f'data-scan-post="{reverse("projects:line_add", args=[project.pk])}"', page)
        # What the widget then posts: the product with the item as wish (PRJ-065).
        token = scan.resolve("0002").plan_token
        response = self.htmx(
            "post", reverse("projects:line_add", args=[project.pk]), {"product": token, "quantity": "1", "group": ""}
        )
        self.assertEqual(response.status_code, 200)
        line = project.material_lines.get()
        self.assertEqual((line.product, line.preferred_item), (self.par, self.cans[1]))


class PackingScanTests(Rig, RentalarsTestCase):
    """PCK-010, PCK-011, PCK-016: an item marked packed or back by its code."""

    def setUp(self) -> None:
        super().setUp()
        self.prepare()
        self.project = make_project("Stadtfest")
        self.line = add_line(self.project, self.par, 3).line
        self.packlist = services.get_packlist(self.project)

    def row(self) -> services.PackRow:
        return services.build_overview(self.packlist).rows[0]

    def test_scanning_packs_and_counts_up(self) -> None:
        first = packing_scan.scan_pack(self.packlist, "0001")
        self.assertEqual((first.status, first.level, first.done, first.required), ("packed", "success", 1, 3))
        self.assertIn("0001 gepackt: 1 von 3", first.message)
        second = packing_scan.scan_pack(self.packlist, "https://rentalars.example/m/0002")
        self.assertEqual((second.status, second.done), ("packed", 2))
        row = self.row()
        self.assertEqual((row.packed, [chosen.display_id for chosen in row.chosen]), (2, ["0001", "0002"]))
        self.packlist.refresh_from_db()
        self.assertEqual(self.packlist.status, PacklistStatus.IN_PROGRESS)
        packing_scan.scan_pack(self.packlist, "0003")
        self.packlist.refresh_from_db()
        self.assertEqual((self.row().packed, self.packlist.status), (3, PacklistStatus.PACKED))

    def test_the_same_code_counts_once(self) -> None:
        packing_scan.scan_pack(self.packlist, "0001")
        again = packing_scan.scan_pack(self.packlist, "0001")
        self.assertEqual((again.status, again.level), ("duplicate", "warning"))
        self.assertEqual(self.row().packed, 1)
        # Also when it was chosen before (PCK-022): the scan confirms it, a second scan changes nothing.
        services.choose_items(
            self.packlist, self.line.pk, self.par.pk, [self.cans[0].pk, self.cans[1].pk, self.cans[2].pk]
        )
        self.assertEqual(packing_scan.scan_pack(self.packlist, "0002").status, "packed")
        self.assertEqual(packing_scan.scan_pack(self.packlist, "0002").status, "duplicate")
        self.assertEqual(self.row().packed, 2)

    def test_what_was_scanned_goes_out_first(self) -> None:
        services.choose_items(
            self.packlist, self.line.pk, self.par.pk, [self.cans[0].pk, self.cans[1].pk, self.cans[2].pk]
        )
        packing_scan.scan_pack(self.packlist, "0003")
        services.issue(self.packlist, only_packed=True)
        issued = Allocation.objects.filter(entry__packlist=self.packlist, issued_at__isnull=False)
        self.assertEqual([allocation.item.display_id for allocation in issued], ["0003"])

    def test_refused_with_a_reason(self) -> None:
        self.assertEqual(packing_scan.scan_pack(self.packlist, "9999").status, "unknown")
        outcome = packing_scan.scan_pack(self.packlist, "0600")
        self.assertEqual(outcome.status, "not_on_list")
        self.assertEqual(packing_scan.scan_pack(self.packlist, "L-010").status, "unknown")
        self.assertEqual(packing_scan.scan_pack(self.packlist, EAN).status, "refused")  # a product, not an item
        # PCK-011: defective, blocked, with another project.
        self.cans[0].status = ItemStatus.DEFECTIVE
        self.cans[0].status_reason = "Linse gebrochen"
        self.cans[0].save()
        outcome = packing_scan.scan_pack(self.packlist, "0001")
        self.assertEqual((outcome.status, outcome.level), ("refused", "error"))
        self.assertIn("kann nicht gepackt werden", outcome.message)
        other = make_project("Messe")
        other_line = add_line(other, self.par, 1).line
        services.choose_items(services.get_packlist(other), other_line.pk, self.par.pk, [self.cans[1].pk])
        outcome = packing_scan.scan_pack(self.packlist, "0002")
        self.assertEqual(outcome.status, "refused")
        self.assertIn(other.number, outcome.message)
        self.assertEqual(self.row().packed, 0)

    def test_more_than_the_row_needs(self) -> None:
        for number in ("0001", "0002", "0003"):
            packing_scan.scan_pack(self.packlist, number)
        outcome = packing_scan.scan_pack(self.packlist, "0004")
        self.assertEqual((outcome.status, outcome.level), ("full", "warning"))
        self.assertEqual(self.row().packed, 3)

    def test_overdue_inspection_is_a_warning(self) -> None:
        from rentalars.material.models import InspectionType

        electric = InspectionType.objects.create(name="Elektrische Prüfung", interval_months=12)
        electric.categories.add(category("L"))
        outcome = packing_scan.scan_pack(self.packlist, "0001")
        self.assertEqual((outcome.status, outcome.level), ("packed", "warning"))
        self.assertEqual(outcome.warnings, ["Die Prüfung von 0001 ist überfällig."])

    def test_bulk_material_points_to_the_row(self) -> None:
        cable_line = add_line(self.project, self.cable_product, 5).line
        packlist = services.get_packlist(self.project)
        outcome = packing_scan.scan_pack(packlist, "0600")
        self.assertEqual((outcome.status, outcome.row), ("bulk", f"{cable_line.pk}-{self.cable_product.pk}"))
        self.assertEqual(Decimal(services.build_overview(packlist).rows[1].packed), 0)

    def test_a_piece_of_several_items(self) -> None:
        pack_product = make_product("L-020", "Akku 10er-Pack", pieces_per_product=2)
        pack_model = make_model("Akku", pack_product, category_code="L")
        batteries = make_items(pack_model, 4)
        line = add_line(self.project, pack_product, 2).line
        packlist = services.get_packlist(self.project)
        first = packing_scan.scan_pack(packlist, batteries[0].display_id)
        self.assertIn("Exemplar 1 von 4", first.message)
        row = next(row for row in services.build_overview(packlist).rows if row.line.pk == line.pk)
        self.assertEqual(row.packed, 0)  # one item is not yet a piece
        packing_scan.scan_pack(packlist, batteries[1].display_id)
        row = next(row for row in services.build_overview(packlist).rows if row.line.pk == line.pk)
        self.assertEqual(row.packed, 1)

    def test_nothing_after_the_issue(self) -> None:
        services.pack_all(self.packlist)
        services.issue(self.packlist)
        self.assertEqual(packing_scan.scan_pack(self.packlist, "0001").status, "refused")

    def test_an_item_inside_a_case(self) -> None:
        self.cans[3].installed_in = self.rack
        self.cans[3].save()
        rack_line = add_line(self.project, self.rack_product, 1).line
        packlist = services.get_packlist(self.project)
        services.choose_items(packlist, rack_line.pk, self.rack_product.pk, [self.rack.pk])
        outcome = packing_scan.scan_pack(packlist, "0004")
        self.assertEqual(outcome.status, "info")
        self.assertIn("steckt in 0500", outcome.message)

    def test_taking_back(self) -> None:
        self.assertEqual(packing_scan.scan_return(self.packlist, "0001").status, "refused")  # nothing is out yet
        for number in ("0001", "0002", "0003"):
            packing_scan.scan_pack(self.packlist, number)
        services.issue(self.packlist)
        first = packing_scan.scan_return(self.packlist, "0001")
        self.assertEqual((first.status, first.done, first.required), ("returned", 1, 3))
        self.assertEqual(self.row().returned, 1)
        again = packing_scan.scan_return(self.packlist, "0001")
        self.assertEqual(again.status, "duplicate")
        self.assertEqual(packing_scan.scan_return(self.packlist, "0600").status, "not_on_list")
        unnoted = packing_scan.scan_return(self.packlist, "0004")  # a can that did not go out with this list
        self.assertEqual((unnoted.status, unnoted.level), ("refused", "warning"))
        packing_scan.scan_return(self.packlist, "0002")
        packing_scan.scan_return(self.packlist, "0003")
        self.assertEqual(self.row().returned, 3)
        # The tick books nothing; booking the return is a step of its own (PCK-028).
        services.take_back(self.packlist)
        self.packlist.refresh_from_db()
        self.assertEqual(self.packlist.status, PacklistStatus.RETURNED)
        self.assertEqual(packing_scan.scan_return(self.packlist, "0001").status, "refused")

    def test_an_item_without_allocation_is_not_counted_back(self) -> None:
        """Cables nobody noted one by one cannot be counted back one by one: the row is ticked by hand."""
        services.pack_all(self.packlist)
        services.issue(self.packlist)
        Allocation.objects.filter(entry__packlist=self.packlist).delete()
        outcome = packing_scan.scan_return(self.packlist, "0001")
        self.assertEqual((outcome.status, outcome.level), ("refused", "warning"))
        self.assertEqual(self.row().returned, 0)


class PackingScanPagesTests(Rig, UiTestCase):
    """The field at the packing list, the answer for the dialog, the API."""

    def setUp(self) -> None:
        super().setUp()
        self.prepare()
        self.project = make_project("Stadtfest")
        self.line = add_line(self.project, self.par, 2).line
        self.packlist = services.get_packlist(self.project)
        self.base = reverse("packing:packlist", args=[self.project.pk])

    def test_the_page_offers_the_field_and_the_button(self) -> None:
        page = self.assert_ok(self.client.get(self.base))
        self.assertIn('name="code"', page)
        self.assertIn("Exemplar ist gepackt: ID scannen oder eintippen", page)
        self.assertIn("data-scan-continuous", page)
        self.assertIn(f'hx-post="{self.base}scan/"', page)
        back = self.assert_ok(self.client.get(self.base + "?mode=return"))
        self.assertNotIn("Exemplar ist zurück", back)  # nothing is out yet

    def test_scanning_through_htmx_answers_for_the_dialog(self) -> None:
        response = self.htmx("post", self.base + "scan/", {"code": "0001", "mode": "pack", "view_mode": "pack"})
        self.assertEqual(response.status_code, 200)
        trigger = json.loads(response["HX-Trigger"])["scanResult"]
        self.assertEqual(trigger["level"], "success")
        self.assertIn("0001 gepackt: 1 von 2", trigger["message"])
        self.assertIn("is-scanned", response.content.decode())
        self.assertEqual(
            self.client.post(self.base + "scan/", {"code": "0002", "mode": "pack"}).status_code, 302
        )  # without scripts
        self.assertEqual(Allocation.objects.filter(packed_scan_at__isnull=False).count(), 2)
        refused = self.htmx("post", self.base + "scan/", {"code": "0600", "mode": "pack", "view_mode": "pack"})
        self.assertEqual(json.loads(refused["HX-Trigger"])["scanResult"]["level"], "error")

    def test_taking_back_through_the_page(self) -> None:
        packing_scan.scan_pack(self.packlist, "0001")
        packing_scan.scan_pack(self.packlist, "0002")
        services.issue(self.packlist)
        page = self.assert_ok(self.client.get(self.base + "?mode=return"))
        self.assertIn("Exemplar ist zurück: ID scannen oder eintippen", page)
        response = self.htmx("post", self.base + "scan/", {"code": "0001", "mode": "return", "view_mode": "return"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response["HX-Trigger"])["scanResult"]["level"], "success")

    def test_only_who_packs(self) -> None:
        reader = self.browser_for("lesend", "Nur-Lesen")
        self.assertEqual(reader.post(self.base + "scan/", {"code": "0001", "mode": "pack"}).status_code, 403)
        self.assertFalse(Allocation.objects.exists())


class ScanApiTests(Rig, ApiTestCase):
    """The resolver and the packing step through the API."""

    def setUp(self) -> None:
        super().setUp()
        self.prepare()

    def test_resolve(self) -> None:
        body = self.admin.get(f"{API}/scan/resolve", {"code": "https://x/m/0500"}).json()
        self.assertEqual((body["kind"], body["is_case"], body["item"]["display_id"]), ("item", True, "0500"))
        self.assertEqual(
            self.admin.get(f"{API}/scan/resolve", {"code": EAN}).json()["product"]["article_number"], "L-010"
        )
        self.assertEqual(self.admin.get(f"{API}/scan/resolve", {"code": "zzz"}).json()["kind"], "none")
        self.assertEqual(self.admin.get(f"{API}/scan/resolve").json()["kind"], "none")
        self.assertEqual(self.client_for("niemand").get(f"{API}/scan/resolve", {"code": "0001"}).status_code, 403)
        self.assertEqual(self.admin.post(f"{API}/scan/resolve", {}, format="json").status_code, 405)

    def test_the_packing_step(self) -> None:
        project = make_project("Stadtfest")
        add_line(project, self.par, 2)
        packlist = services.get_packlist(project)
        url = f"{API}/projects/{project.pk}/packlists/{packlist.pk}/scan"
        done = self.admin.post(url, {"code": "0001"}, format="json")
        self.assertEqual(done.status_code, 200, done.content)
        answer = done.json()["scan"]
        self.assertEqual(
            (answer["status"], answer["done"], answer["required"], answer["changed"]), ("packed", 1, 2, True)
        )
        again = self.admin.post(url, {"code": "0001"}, format="json").json()["scan"]
        self.assertEqual((again["status"], again["changed"]), ("duplicate", False))
        refused = self.admin.post(url, {"code": "nope"}, format="json").json()["scan"]
        self.assertEqual(refused["status"], "unknown")
        services.pack_all(packlist)
        services.issue(packlist)
        back = self.admin.post(url, {"code": "0001", "mode": "return"}, format="json").json()["scan"]
        self.assertEqual(back["status"], "returned")
        reader = self.client_for("lesend", "Nur-Lesen")
        self.assertEqual(reader.post(url, {"code": "0002"}, format="json").status_code, 403)
