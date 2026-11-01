# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser tests: material models, items, "installed in" and the import in three steps (MAT, IMP)."""

from __future__ import annotations

import re

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.core.models import BackgroundJob
from rentalars.masterdata.models import Manufacturer, Supplier
from rentalars.material.models import MaterialItem, MaterialModel
from rentalars.material.services import install_item
from tests.acceptance.test_scenario_08_import import material_rows, workbook
from tests.helpers import category, make_item, make_items, make_model, make_product
from tests.ui.base import UiTestCase, form_data


class MaterialModelPageTests(UiTestCase):
    """Material models (MAT-011, MAT-015)."""

    def test_create_model_with_new_manufacturer_and_category_specific_value(self) -> None:
        """MAT-048: the manufacturer is typed; a new name creates it – no extra field any more."""
        page = self.client.get(reverse("material:model_create"), {"category": category("K").pk})
        data = form_data(
            page, name="Cordial CPM 5 FM", category=category("K").pk, manufacturer_name="Cordial", category_specific="5"
        )

        response = self.client.post(reverse("material:model_create"), data)

        model = MaterialModel.objects.get(name="Cordial CPM 5 FM")
        self.assertRedirects(response, reverse("material:model_detail", args=[model.pk]))
        self.assertEqual(model.manufacturer, Manufacturer.objects.get(name="Cordial"))
        self.assertEqual(model.category_specific_display, "5 m")
        self.assertIn("5 m", self.assert_ok(self.client.get(reverse("material:model_detail", args=[model.pk]))))
        self.assertIn("Cordial CPM 5 FM", self.assert_ok(self.client.get(reverse("material:model_list"), {"q": "CPM"})))

    def test_edit_and_delete_model(self) -> None:
        model = make_model("Rack 6 HE", category_code="R")
        edit = reverse("material:model_edit", args=[model.pk])
        self.client.post(edit, form_data(self.client.get(edit), short_name="Rack6"))
        model.refresh_from_db()
        self.assertEqual(model.short_name, "Rack6")

        make_item(model, 500)
        blocked = self.client.post(reverse("material:model_delete", args=[model.pk]), follow=True)
        self.assertTrue(MaterialModel.objects.filter(pk=model.pk).exists())
        self.assertTrue(self.messages_of(blocked))
        MaterialItem.objects.all().delete()
        self.client.post(reverse("material:model_delete", args=[model.pk]))
        self.assertFalse(MaterialModel.objects.filter(pk=model.pk).exists())


class MaterialItemPageTests(UiTestCase):
    """Items: creating, the list with its filters, editing, status (MAT-002 to MAT-028)."""

    def setUp(self) -> None:
        super().setUp()
        self.cable = make_model("Cordial CPM 5 FM", make_product("K-005", "XLR-Kabel 5 m"), category_code="K")
        self.rack_model = make_model("Rack 6 HE", category_code="R")

    def test_several_items_in_one_step_get_consecutive_ids(self) -> None:
        url = reverse("material:item_create", args=[self.cable.pk])
        data = form_data(self.client.get(url), count=12, purchase_date="2023-04-12", new_supplier=None)

        response = self.client.post(url, data, follow=True)

        self.assertRedirects(response, reverse("material:model_detail", args=[self.cable.pk]))
        self.assertEqual(MaterialItem.objects.filter(material_model=self.cable).count(), 12)
        self.assertIn("0001", self.messages_of(response)[0])
        self.assertIn("0012", self.messages_of(response)[0])

    def test_single_item_with_a_chosen_id(self) -> None:
        url = reverse("material:item_create", args=[self.rack_model.pk])
        self.client.post(url, form_data(self.client.get(url), count=1, inventory_number="500"))
        self.assertTrue(MaterialItem.objects.filter(inventory_number=500, material_model=self.rack_model).exists())
        taken = self.client.post(url, form_data(self.client.get(url), count=1, inventory_number="0500"))
        self.assertEqual(taken.status_code, 200)
        self.assertEqual(MaterialItem.objects.filter(material_model=self.rack_model).count(), 1)

    def test_list_shows_thirteen_columns_and_filters(self) -> None:
        """MAT-012, MAT-028: one row per item, filter state in the address. Also MAT-007, PRD-005, UIX-004."""
        make_items(self.cable, 3, supplier=Supplier.objects.create(name="Musikhaus Nord"))
        make_item(self.rack_model, 500, serial_number="R-77")
        MaterialItem.objects.filter(inventory_number=2).update(status="defective")

        page = self.assert_ok(self.client.get(reverse("material:item_list")))
        for heading in (
            "ID",
            "Artikelname",
            "Kategorie",
            "Beschreibung",  # MAT-049
            "Verbaut in",
            "Seriennummer",
            "Notiz",
            "Rechnungsdatum",  # MAT-050
            "Kaufnotiz",
            "Einkaufspreis",
            "Gekauft bei",
            "Art.-Nr. Händler",
        ):
            self.assertIn(heading, page)
        for display_id in ("0001", "0002", "0003", "0500"):
            self.assertIn(f">{display_id}<", page)

        only_rack = self.assert_ok(self.client.get(reverse("material:item_list"), {"q": "R-77"}))
        self.assertIn(">0500<", only_rack)
        self.assertNotIn(">0001<", only_rack)
        defective = self.assert_ok(self.client.get(reverse("material:item_list"), {"status": "defective"}))
        self.assertIn(">0002<", defective)
        self.assertNotIn(">0003<", defective)
        without_product = self.assert_ok(self.client.get(reverse("material:item_list"), {"without_product": "1"}))
        self.assertIn(">0500<", without_product)
        self.assertNotIn(">0001<", without_product)
        by_number = self.assert_ok(self.client.get(reverse("material:item_list"), {"sort": "-id"}))
        self.assertLess(by_number.index(">0500<"), by_number.index(">0001<"))

    def test_purchase_prices_are_hidden_without_the_right(self) -> None:
        make_item(self.rack_model, 500, purchase_price="249.00")
        Role.objects.create(name="Werkstatt", module_levels={"material": 2})
        workshop = self.browser_for("willi", "Werkstatt")
        # The purchase columns are off until switched on – ask for them, so that the right is what decides.
        url = reverse("material:item_list") + "?cols=id,purchase_price"
        page = self.assert_ok(workshop.get(url))
        self.assertNotIn("249,00", page)
        self.assertNotIn("Einkaufspreis", page)
        self.assertIn("249,00", self.assert_ok(self.client.get(url)))

    def test_installing_an_item_by_typing_the_id_of_its_container(self) -> None:
        """MAT-033: "Einsatz/Verbindung" takes the ID of another item. Also MAT-035."""
        rack = make_item(self.rack_model, 500)
        receiver = make_item(make_model("Funkempfänger", make_product("T-050"), category_code="T"), 310)
        url = reverse("material:item_edit", args=[receiver.pk])

        response = self.client.post(
            url, form_data(self.client.get(url), installed_in_number="0500", connection_type="fixed")
        )

        self.assertRedirects(response, reverse("material:item_detail", args=[receiver.pk]))
        receiver.refresh_from_db()
        self.assertEqual(receiver.installed_in, rack)
        self.assertIn(">0310<", self.assert_ok(self.client.get(reverse("material:item_detail", args=[rack.pk]))))

        circle = reverse("material:item_edit", args=[rack.pk])
        refused = self.client.post(circle, form_data(self.client.get(circle), installed_in_number="0310"))
        self.assertEqual(refused.status_code, 200)
        self.assertTrue(refused.context["form"].errors)
        unknown = self.client.post(url, form_data(self.client.get(url), installed_in_number="9999"))
        self.assertTrue(unknown.context["form"].errors)

    def test_status_change_and_history(self) -> None:
        """MAT-020, MAT-025, MAT-044: the change, who made it and why are kept."""
        item = make_item(self.rack_model, 500)
        response = self.client.post(
            reverse("material:item_set_status", args=[item.pk]),
            {"status": "defective", "reason": "Rolle vorne links gebrochen"},
            follow=True,
        )
        item.refresh_from_db()
        self.assertEqual((item.status, item.status_reason), ("defective", "Rolle vorne links gebrochen"))
        page = self.assert_ok(response)
        self.assertIn('<span class="status-reason">Rolle vorne links gebrochen</span>', page)
        # The history is a tab of its own since stage 5.
        page = self.assert_ok(self.client.get(reverse("material:item_history", args=[item.pk])))
        self.assertIn("admin", page)
        history = page[page.index('<ul class="history">') :]
        self.assertIn("Grund für den Status", history)
        self.assertIn("Rolle vorne links gebrochen", history)

    def test_defective_needs_a_reason(self) -> None:
        """MAT-044."""
        item = make_item(self.rack_model, 500)
        url = reverse("material:item_set_status", args=[item.pk])
        refused = self.client.post(url, {"status": "defective", "reason": "  "}, follow=True)
        self.assertIn("Der Grund ist bei „defekt“ Pflicht", self.assert_ok(refused))
        item.refresh_from_db()
        self.assertEqual(item.status, "available")
        # Every other status may come without a reason – but it is asked for.
        self.client.post(url, {"status": "blocked"})
        item.refresh_from_db()
        self.assertEqual((item.status, item.status_reason), ("blocked", ""))
        page = self.assert_ok(self.client.get(reverse("material:item_detail", args=[item.pk])))
        self.assertIn('name="reason"', page)
        self.assertIn('data-require-if="status=defective"', page)

    def test_a_defective_item_only_goes_to_repair_or_out_of_the_stock(self) -> None:
        """MAT-045."""
        item = make_item(self.rack_model, 500)
        url = reverse("material:item_set_status", args=[item.pk])
        self.client.post(url, {"status": "defective", "reason": "Deckel verzogen"})
        page = self.assert_ok(self.client.get(reverse("material:item_detail", args=[item.pk])))
        select = page[
            page.index('<select name="status"') : page.index("</select>", page.index('<select name="status"'))
        ]
        self.assertEqual(re.findall(r'value="(\w+)"', select), ["in_repair", "retired", "sold"])

        refused = self.client.post(url, {"status": "available"}, follow=True)
        self.assertIn(
            "Ein defektes Exemplar kann nur auf „in Reparatur“, „ausgemustert“, „verkauft“", self.assert_ok(refused)
        )
        item.refresh_from_db()
        self.assertEqual(item.status, "defective")

        self.client.post(url, {"status": "in_repair", "reason": "bei Tischlerei Holzmann"})
        self.client.post(url, {"status": "available"})
        item.refresh_from_db()
        # The reason belongs to the status it was given for; it does not linger.
        self.assertEqual((item.status, item.status_reason), ("available", ""))

    def test_the_status_is_not_changed_in_the_edit_form(self) -> None:
        """MAT-044: one place changes the status, and that place asks for the reason."""
        item = make_item(self.rack_model, 500)
        form = self.assert_ok(self.client.get(reverse("material:item_edit", args=[item.pk])))
        self.assertNotIn('name="status"', form)

    def test_contents_are_added_and_removed_on_the_page_of_the_container(self) -> None:
        """MAT-046: the relation "installed in" from the other side."""
        rack = make_item(self.rack_model, 500)
        receiver = make_item(make_model("Funkempfänger EW-D", category_code="T"), 310)
        page = self.assert_ok(self.client.get(reverse("material:item_detail", args=[rack.pk])))
        self.assertIn("In diesem Exemplar ist nichts verbaut.", page)
        self.assertIn(f"/material/items/suggest/?not_in={rack.pk}", page)

        added = self.client.post(
            reverse("material:item_content_add", args=[rack.pk]),
            {"item_number": "0310", "connection_type": "loose"},
            follow=True,
        )
        self.assertIn("0310 ist jetzt in 0500 verbaut.", self.assert_ok(added))
        receiver.refresh_from_db()
        self.assertEqual((receiver.installed_in, receiver.connection_type), (rack, "loose"))
        # Both histories tell about it.
        self.assertIn("0310", self.assert_ok(added))

        removed = self.client.post(reverse("material:item_content_remove", args=[rack.pk, receiver.pk]), follow=True)
        self.assertIn("0310 wurde aus 0500 herausgenommen.", self.assert_ok(removed))
        receiver.refresh_from_db()
        self.assertIsNone(receiver.installed_in)

    def test_contents_cannot_form_a_circle(self) -> None:
        """MAT-034, MAT-046: no loops, whichever side the relation is entered from."""
        rack = make_item(self.rack_model, 500)
        case = make_item(make_model("Transportcase groß", category_code="R"), 600)
        module = make_item(make_model("Funkempfänger EW-D", category_code="T"), 310)
        install_item(rack, case)  # the rack stands in the case
        install_item(module, rack)  # the receiver sits in the rack

        def add(container: MaterialItem, number: str) -> str:
            response = self.client.post(
                reverse("material:item_content_add", args=[container.pk]),
                {"item_number": number, "connection_type": "fixed"},
                follow=True,
            )
            return self.assert_ok(response)

        self.assertIn("Ein Exemplar kann nicht in sich selbst verbaut sein.", add(rack, "0500"))
        # The case into the rack: the rack is in the case already.
        self.assertIn("Kreisbezug: 0500 ist selbst in 0600 verbaut.", add(rack, "0600"))
        # Two levels: the case into the receiver that sits in the rack that stands in the case.
        self.assertIn("Kreisbezug", add(module, "0600"))
        self.assertIn("Es gibt kein Exemplar mit der ID 9999", add(rack, "9999"))
        case.refresh_from_db()
        self.assertIsNone(case.installed_in)

    def test_an_item_that_sits_elsewhere_is_not_pulled_out_by_a_typo(self) -> None:
        """MAT-046."""
        rack = make_item(self.rack_model, 500)
        other_rack = make_item(self.rack_model, 501)
        receiver = make_item(make_model("Funkempfänger EW-D", category_code="T"), 310)
        install_item(receiver, other_rack)
        response = self.client.post(
            reverse("material:item_content_add", args=[rack.pk]),
            {"item_number": "0310", "connection_type": "fixed"},
            follow=True,
        )
        self.assertIn("0310 ist bereits in 0501 verbaut.", self.assert_ok(response))
        receiver.refresh_from_db()
        self.assertEqual(receiver.installed_in, other_rack)
        # Taking out what is not in there is refused as well.
        refused = self.client.post(reverse("material:item_content_remove", args=[rack.pk, receiver.pk]), follow=True)
        self.assertIn("0310 ist nicht in 0500 verbaut.", self.assert_ok(refused))

    def test_only_direct_contents_can_be_taken_out_and_archived_items_contain_nothing(self) -> None:
        rack = make_item(self.rack_model, 500)
        case = make_item(make_model("Transportcase groß", category_code="R"), 600)
        module = make_item(make_model("Funkempfänger EW-D", category_code="T"), 310)
        install_item(rack, case)
        install_item(module, rack)
        page = self.assert_ok(self.client.get(reverse("material:item_detail", args=[case.pk])))
        self.assertIn(reverse("material:item_content_remove", args=[case.pk, rack.pk]), page)
        self.assertNotIn(reverse("material:item_content_remove", args=[case.pk, module.pk]), page)

        spare = make_item(self.rack_model, 502, status="retired")
        archived = self.assert_ok(self.client.get(reverse("material:item_detail", args=[spare.pk])))
        self.assertNotIn(reverse("material:item_content_add", args=[spare.pk]), archived)

    def test_suggestions_for_contains_leave_out_the_container_and_what_is_in_it(self) -> None:
        rack = make_item(self.rack_model, 500)
        inside = make_item(self.rack_model, 501)
        make_item(self.rack_model, 502)
        install_item(inside, rack)
        results = self.client.get(reverse("material:item_suggest"), {"q": "05", "not_in": rack.pk}).json()
        self.assertEqual([result["id"] for result in results], ["0502"])
        everything = self.client.get(reverse("material:item_suggest"), {"q": "05"}).json()
        self.assertEqual([result["hint"] for result in everything], ["verfügbar", "in 0500", "verfügbar"])

    def test_item_suggestions_for_the_installed_in_field(self) -> None:
        """MAT-034."""
        make_item(self.rack_model, 500)
        make_item(self.rack_model, 501)
        make_item(self.rack_model, 50)

        def suggested(text: str) -> list[str]:
            return [result["id"] for result in self.client.get(reverse("material:item_suggest"), {"q": text}).json()]

        # While an ID is typed, every ID starting with the digits so far is offered.
        self.assertEqual(suggested("05"), ["0500", "0501"])
        self.assertEqual(suggested("0500"), ["0500"])
        self.assertEqual(suggested("005"), ["0050"])
        self.assertEqual(suggested("Rack"), ["0050", "0500", "0501"])

    def test_delete_only_for_items_created_by_mistake(self) -> None:
        item = make_item(self.rack_model, 500)
        self.client.post(reverse("material:item_delete", args=[item.pk]))
        self.assertFalse(MaterialItem.objects.filter(pk=item.pk).exists())

    def test_read_only_user_sees_no_edit_controls_and_cannot_post(self) -> None:
        item = make_item(self.rack_model, 500)
        reader = self.browser_for("nora", "Nur-Lesen")
        page = self.assert_ok(reader.get(reverse("material:item_detail", args=[item.pk])))
        self.assertNotIn(reverse("material:item_edit", args=[item.pk]), page)
        self.assertEqual(reader.get(reverse("material:item_edit", args=[item.pk])).status_code, 403)
        self.assertEqual(
            reader.post(reverse("material:item_set_status", args=[item.pk]), {"status": "lost"}).status_code, 403
        )


class ImportPageTests(UiTestCase):
    """The import in the browser: file, column mapping with dry run, import (IMP-002, IMP-003, IMP-009)."""

    def upload(self, rows: list[list[object]]) -> None:
        file = SimpleUploadedFile(
            "bestand.xlsx",
            workbook(rows).getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response = self.client.post(reverse("material:import"), {"step": "upload", "file": file})
        self.assertRedirects(response, reverse("material:import"))

    def test_three_steps(self) -> None:
        self.upload(material_rows(60))

        mapping_page = self.client.get(reverse("material:import"))
        text = self.assert_ok(mapping_page)
        self.assertIn("bestand.xlsx", text)
        self.assertIn("60 Zeilen", text)
        data = form_data(mapping_page, containing="map_inventory_number")
        # The recognised column is preselected: "Artikelname" is the second column of the file.
        self.assertEqual(data["map_name"], "1")

        dry_run = self.client.post(reverse("material:import"), {**data, "step": "check"}, follow=True)
        report = self.assert_ok(dry_run)
        self.assertIn("Ergebnis des Probelaufs", report)
        self.assertIn("60 neu", report)
        self.assertEqual(MaterialItem.objects.count(), 0)

        done = self.client.post(reverse("material:import"), {**data, "step": "import"}, follow=True)
        self.assertIn("Der Import ist abgeschlossen", self.assert_ok(done))
        self.assertEqual(MaterialItem.objects.count(), 60)
        # The uploaded file is gone; the page offers a new upload.
        self.assertIn('name="file"', self.assert_ok(self.client.get(reverse("material:import"))))

    def test_errors_are_listed_with_their_row_and_nothing_is_written(self) -> None:
        rows = material_rows(30)
        rows[9][0] = "12a"  # an ID that is no number (a wrong date would only be a hint)
        self.upload(rows)
        data = form_data(self.client.get(reverse("material:import")), containing="map_inventory_number")

        response = self.client.post(reverse("material:import"), {**data, "step": "import"}, follow=True)

        text = self.assert_ok(response)
        self.assertIn("Zeile 11", text)
        self.assertIn("12a", text)
        self.assertEqual(MaterialItem.objects.count(), 0)

    @override_settings(MAX_IMPORT_ROWS_PER_REQUEST=20)
    def test_a_long_list_runs_in_the_background(self) -> None:
        """NFA-041: dry run and import are tasks in the background, so the length of a request is no limit."""
        self.upload(material_rows(21))
        data = form_data(self.client.get(reverse("material:import")), containing="map_inventory_number")
        self.client.post(reverse("material:import"), {**data, "step": "check"})
        job = BackgroundJob.objects.get()
        self.assertEqual((job.kind, job.status, job.result["report"]["items_created"]), ("import", "done", 21))
        # While a task runs, the page asks for its progress; once it is done the page is shown anew.
        polled = self.htmx("get", reverse("material:import"))
        self.assertEqual(polled["HX-Refresh"], "true")
        BackgroundJob.objects.filter(pk=job.pk).update(status="running", progress=40)
        running = self.assert_ok(self.client.get(reverse("material:import")))
        self.assertIn("Probelauf läuft", running)
        self.assertIn('hx-trigger="every 2s"', running)
        self.assertIn("40 %", self.assert_ok(self.htmx("get", reverse("material:import"))))
        self.assertEqual(MaterialItem.objects.count(), 0)

        # The import itself, as on a server: the page asks while it runs and then shows the result once.
        BackgroundJob.objects.filter(pk=job.pk).update(status="done", progress=100)
        with self.settings(JOBS_RUN_INLINE=False), self.captureOnCommitCallbacks(execute=False):
            self.client.post(reverse("material:import"), {**data, "step": "import"})
        from rentalars.core.jobs import run_waiting_jobs

        self.assertEqual(run_waiting_jobs(), 1)
        self.assertEqual(self.htmx("get", reverse("material:import"))["HX-Refresh"], "true")
        # IMP-011: the finished import moves to an address of its own (?job=…), so that the list of its
        # rows can be filtered and paged; hence follow=True.
        self.assertIn(
            "Der Import ist abgeschlossen",
            self.assert_ok(self.client.get(reverse("material:import"), follow=True)),
        )
        self.assertEqual(MaterialItem.objects.count(), 21)
        self.assertIn('name="file"', self.assert_ok(self.client.get(reverse("material:import"))))

    def test_file_can_be_replaced(self) -> None:
        self.upload(material_rows(5))
        self.client.post(reverse("material:import"), {"step": "discard"})
        self.assertIn('name="file"', self.assert_ok(self.client.get(reverse("material:import"))))

    def test_other_files_are_refused(self) -> None:
        file = SimpleUploadedFile("bestand.pdf", b"%PDF-1.4", content_type="application/pdf")
        response = self.client.post(reverse("material:import"), {"step": "upload", "file": file})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["upload_form"].errors)
