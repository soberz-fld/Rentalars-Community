# SPDX-License-Identifier: GPL-3.0-or-later
"""In a real browser: packing, kits, material import and the search (PCK, PRD-022, IMP, UIX)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from openpyxl import Workbook

from rentalars.material.models import MaterialItem
from rentalars.packing.models import Packlist
from rentalars.products.models import KitComponent, Product
from tests.browser.base import BrowserTestCase


class PackingInBrowserTests(BrowserTestCase):
    """Tick, issue, take back (PCK-003 ff., PCK-020)."""

    def test_pack_issue_and_return(self) -> None:
        self.open(f"/projects/{self.project.pk}/packlist/")
        rows = self.page.locator("#packlist li.pack-row")
        total = rows.count()
        self.assertGreater(total, 5)

        # One tick packs the whole row …
        rows.first.locator("button.tick").click()
        self.settle()
        self.assertEqual(self.page.locator("#packlist li.pack-row.is-done").count(), 1)
        # … a typed quantity packs a part of it.
        second = rows.nth(1)
        second.locator("input[type=number]").fill("2")
        second.locator("input[type=number]").dispatch_event("change")
        self.settle()
        self.assertEqual(rows.nth(1).locator("input[type=number]").input_value(), "2")
        self.assertEqual(self.page.locator("#packlist li.pack-row.is-done").count(), 1)

        self.page.locator("button", has_text="Alle Zeilen abhaken").click()
        self.settle()
        self.assertEqual(self.page.locator("#packlist li.pack-row.is-done").count(), total)

        with self.page.expect_navigation():  # PCK-025: "Ausgeben" books what is ticked – here every row
            self.page.get_by_role("button", name="Ausgeben", exact=True).click()
        self.page.wait_for_load_state("networkidle")
        self.assertEqual(Packlist.objects.get(project=self.project).status, "issued")
        self.assertIn("Unterwegs", self.page.inner_text("main"))

        self.page.locator("button", has_text="Alles ist zurück").click()
        self.settle()
        self.page.locator("button", has_text="Rücknahme abschließen").click()
        self.page.wait_for_load_state("networkidle")
        self.assertEqual(Packlist.objects.get(project=self.project).status, "returned")

    def test_packlist_as_pdf(self) -> None:
        response = self.page.request.get(f"{self.live_server_url}/projects/{self.project.pk}/packlist/pdf/")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertTrue(response.body().startswith(b"%PDF"))


class ProductsAndMaterialInBrowserTests(BrowserTestCase):
    """Forms that react to what is chosen in them."""

    def test_kit_component_is_found_by_typing(self) -> None:
        """PRD-022."""
        kit = Product.objects.get(article_number="T-100")
        before = KitComponent.objects.filter(kit=kit).count()
        self.open(f"/products/{kit.pk}/")
        form = self.page.locator("form.line-add")

        self.choose_product(form, "K-020")
        form.locator("button[type=submit]").click()
        self.page.wait_for_load_state("networkidle")

        self.assertEqual(KitComponent.objects.filter(kit=kit).count(), before + 1)
        self.assertIn("K-020", self.page.inner_text("main"))

    def test_product_form_shows_the_fields_that_fit_the_kind(self) -> None:
        self.open("/products/new/")
        surcharge_field = self.page.locator("[name=surcharge_percent]")
        self.assertFalse(surcharge_field.is_visible())
        self.page.select_option("[name=kind]", "surcharge")
        self.page.select_option("[name=surcharge_type]", "percent")
        self.assertTrue(surcharge_field.is_visible())

    def test_import_in_three_steps(self) -> None:
        """IMP-003, IMP-009: upload, check the columns, dry run, import."""
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["ID", "Artikelname", "Kategorie", "Seriennummer", "Kaufpreis"])
        sheet.append([9001, "Stagebox 16/4", "Ton", "SB-1", "480,00"])
        sheet.append([9002, "Stagebox 16/4", "Ton", "SB-2", "480,00"])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bestand.xlsx"
            workbook.save(path)
            self.open("/material/import/")
            self.page.set_input_files("input[type=file]", str(path))
            self.page.locator("button", has_text="Datei hochladen").click()
            self.page.wait_for_load_state("networkidle")

        self.assertEqual(self.page.locator("select[name=map_inventory_number] option:checked").inner_text(), "ID")
        self.page.locator("button", has_text="Probelauf").click()
        self.page.wait_for_load_state("networkidle")
        self.assertIn("Ergebnis des Probelaufs", self.page.inner_text("main"))
        self.assertFalse(MaterialItem.objects.filter(inventory_number=9001).exists())

        self.page.locator("button", has_text="Jetzt importieren").click()
        self.page.wait_for_load_state("networkidle")
        self.assertIn("Der Import ist abgeschlossen", self.page.inner_text("main"))
        self.assertEqual(MaterialItem.objects.filter(inventory_number__in=[9001, 9002]).count(), 2)

    def test_api_documentation_works_and_stays_on_this_server(self) -> None:
        """API-004, NFA-050. Requests to other servers fail every test of this folder (see base.py)."""
        self.open("/api/v1/docs/")
        self.page.locator(".opblock").first.wait_for()
        self.assertGreater(self.page.locator(".opblock").count(), 5)
        self.assertIn("Rentalars API", self.page.inner_text("body"))
        # The field that narrows the list down: only the projects remain.
        self.page.fill("input.operation-filter-input", "projects")
        self.page.wait_for_timeout(300)
        tags = self.page.eval_on_selector_all(".opblock-tag", "tags => tags.map(tag => tag.dataset.tag)")
        self.assertEqual(tags, ["projects"])

    def test_search_from_the_start_page(self) -> None:
        self.open("/")
        self.page.fill("input[type=search]", "Stadtfest")
        self.page.keyboard.press("Enter")
        self.page.wait_for_load_state("networkidle")
        self.assertIn("Stadtfest Hauptbühne", self.page.inner_text("main"))


class GettingAroundTests(BrowserTestCase):
    """Finding the way back and choosing the length of a list, clicked like a user would (UIX-011, UIX-012)."""

    def test_back_leads_to_the_list_as_it_was_even_after_saving(self) -> None:
        self.open("/material/")
        self.page.locator(".page-sizes a", has_text="25").click()
        self.page.locator(".pagination a", has_text="Weiter").click()
        self.page.wait_for_load_state("networkidle")
        listing = self.page.url
        self.assertTrue(listing.endswith("/material/?per_page=25&page=2"), listing)
        self.assertEqual(self.page.locator("a.back-link").count(), 0)

        self.page.locator("tbody tr a").first.click()
        self.page.get_by_role("link", name="Exemplar bearbeiten", exact=True).click()
        self.page.fill("[name=note]", "geprüft")
        self.page.locator("form button[type=submit]", has_text="Speichern").first.click()
        self.page.wait_for_load_state("networkidle")
        self.assertIn("geprüft", self.page.inner_text("main"))

        self.page.locator("a.back-link").click()
        self.page.wait_for_load_state("networkidle")

        self.assertEqual(self.page.url, listing)
        self.assertEqual(self.page.locator("tbody tr").count(), 25)

    def test_the_chosen_length_is_kept_for_the_next_list(self) -> None:
        self.open("/material/")
        self.assertEqual(self.page.locator("tbody tr").count(), 50)
        self.page.locator(".page-sizes a", has_text="100").click()
        self.page.wait_for_load_state("networkidle")
        self.assertEqual(self.page.locator("tbody tr").count(), 100)

        self.page.locator("nav.tabs a", has_text="Modelle").click()
        self.page.locator("nav.tabs a", has_text="Exemplare").click()
        self.page.wait_for_load_state("networkidle")

        self.assertEqual(self.page.locator("tbody tr").count(), 100)

    def test_back_fits_on_a_phone(self) -> None:
        self.page.set_viewport_size({"width": 360, "height": 740})
        item = MaterialItem.objects.first()
        self.open("/material/")
        self.open(f"/material/items/{item.pk}/")
        # UIX-027: on a phone "Back" is in the bar at the top, left; the link above the page is hidden.
        link = self.page.locator("a.topbar-back")
        box = link.bounding_box()
        assert box
        self.assertLess(box["y"], 20)  # in the bar at the top
        self.assertLess(box["x"], 20)  # and on the left
        self.assertGreaterEqual(box["height"], 36)  # large enough for a finger
        self.assertEqual(link.get_attribute("href"), "/material/")
        self.assertFalse(self.page.locator("main a.back-link").is_visible())
        self.assertLessEqual(self.page.evaluate("document.scrollingElement.scrollWidth"), 360)
