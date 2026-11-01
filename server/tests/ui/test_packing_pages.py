# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser tests: the packlist page from packing to the completed return (PCK)."""

from __future__ import annotations

from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.material.models import MaterialItem
from rentalars.packing.models import PacklistStatus
from rentalars.packing.services import get_packlist
from rentalars.products.services import set_kit_components
from rentalars.projects.models import Project
from tests.helpers import add_group, add_line, make_item, make_model, make_product, make_project, make_stock
from tests.ui.base import UiTestCase


class PacklistPageTests(UiTestCase):
    """Packing, issue and return by ticking (PCK-009 to PCK-021)."""

    def setUp(self) -> None:
        super().setUp()
        self.cable = make_stock("K-005", 9, "XLR-Kabel 5 m", price="1.50")
        self.rack_product = make_product("T-500", "Funkrack", price="140.00")
        self.rack = make_item(make_model("Funkrack 4 HE", self.rack_product), 500)
        self.project = make_project("Stadtfest")
        sound = add_group(self.project, "Ton FOH")
        self.cable_line = add_line(self.project, self.cable, 3, group=sound).line
        self.rack_line = add_line(self.project, self.rack_product, 1, group=sound).line
        self.url = reverse("packing:packlist", args=[self.project.pk])

    def tick(self, line: object, product: object, quantity: str, mode: str = "pack") -> str:
        """Tick one row the way the packlist page does."""
        response = self.htmx(
            "post",
            reverse("packing:row", args=[self.project.pk]),
            {"line": line.pk, "product": product.pk, "quantity": quantity, "mode": mode},  # type: ignore[attr-defined]
        )
        return self.assert_ok(response)

    def step(self, action: str, **data: str) -> object:
        """Run one step of the packlist."""
        return self.client.post(reverse("packing:action", args=[self.project.pk, action]), data, follow=True)

    def test_page_lists_rows_grouped_and_without_prices(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn("Ton FOH", page)
        self.assertIn("XLR-Kabel 5 m", page)
        self.assertIn("K-005", page)
        self.assertNotIn("1,50", page)
        self.assertNotIn("140,00", page)
        self.assertIn("0 von 4 Stück sind gepackt", page)

    def test_whole_way_by_ticking(self) -> None:
        """Pack → issue → return → done, without choosing or scanning an item."""
        self.assertIn("3 von 4 Stück sind gepackt", self.tick(self.cable_line, self.cable, "3"))
        self.tick(self.rack_line, self.rack_product, "1")
        self.assertEqual(get_packlist(self.project).status, PacklistStatus.PACKED)

        issued = self.step("issue")
        self.assertIn("Unterwegs", self.assert_ok(issued))  # type: ignore[arg-type]
        self.assertEqual(Project.objects.get(pk=self.project.pk).status, "out")
        self.assertEqual(MaterialItem.objects.get(pk=self.rack.pk).status, "in_use")
        self.assertIn("0500", self.assert_ok(self.client.get(self.url)))

        self.tick(self.cable_line, self.cable, "3", mode="return")
        self.tick(self.rack_line, self.rack_product, "1", mode="return")
        done = self.step("complete-return")
        # PRJ-093: the status is no longer called "Zurück".
        self.assertIn("Wieder im Lager", self.assert_ok(done))  # type: ignore[arg-type]
        self.assertEqual(Project.objects.get(pk=self.project.pk).status, "returned")
        self.assertEqual(MaterialItem.objects.get(pk=self.rack.pk).status, "available")

    def test_after_the_issue_nothing_counts_as_missing(self) -> None:
        """PCK-023: material that just went out is "out", not "missing"."""
        self.step("issue", only_packed="0")  # "Alles ausgeben" (PCK-025)
        page = self.assert_ok(self.client.get(self.url))

        self.assertNotIn("is-partial", page)
        self.assertNotIn("is-open", page)
        self.assertNotIn("Fehlmenge", page)
        self.assertEqual(page.count(">unterwegs</span>"), 2)
        # What to do if something does not come back is offered, but folded away.
        self.assertEqual(page.count("Kommt nicht zurück?"), 2)
        self.assertNotIn('<details class="pack-clarify no-print" open>', page)

    def test_a_row_that_came_back_incomplete_asks_what_happened(self) -> None:
        """PCK-016, PCK-023."""
        self.step("issue", only_packed="0")  # "Alles ausgeben" (PCK-025)
        page = self.tick(self.cable_line, self.cable, "2", mode="return")

        self.assertEqual(page.count("is-partial"), 1)
        self.assertIn("2 von 3 zurück", page)
        self.assertIn("1 Stück ist nicht zurück", page)
        self.assertEqual(page.count('<details class="pack-clarify no-print" open>'), 1)
        # The rack was not touched yet and stays plain.
        self.assertIn(">unterwegs</span>", page)

    def test_missing_parts_block_the_return_until_clarified(self) -> None:
        """PCK-019."""
        self.step("issue", only_packed="0")  # "Alles ausgeben" (PCK-025)
        self.tick(self.cable_line, self.cable, "2", mode="return")

        blocked = self.step("complete-return")
        self.assertTrue(self.messages_of(blocked))
        self.assertEqual(Project.objects.get(pk=self.project.pk).status, "out")
        # PCK-023: now the rows that stand in the way are marked, and stay
        # marked while they are worked through.
        page = self.assert_ok(blocked)  # type: ignore[arg-type]
        self.assertEqual(page.count("is-open"), 2)
        self.assertIn('hx-vals=\'{"open": "1"}\'', page)
        ticked = self.htmx(
            "post",
            reverse("packing:row", args=[self.project.pk]),
            {
                "line": self.rack_line.pk,
                "product": self.rack_product.pk,
                "quantity": "1",
                "mode": "return",
                "open": "1",
            },
        )
        self.assertEqual(self.assert_ok(ticked).count("is-open"), 1)

        self.step(
            "resolve-missing",
            line=str(self.cable_line.pk),
            product=str(self.cable.pk),
            note="Kabel beim Kunden, kommt per Post",
        )
        self.assertIn("kommt per Post", self.assert_ok(self.client.get(self.url)))
        self.step("complete-return")
        self.assertEqual(Project.objects.get(pk=self.project.pk).status, "returned")

    def test_tick_all_issue_and_take_back(self) -> None:
        self.htmx("post", reverse("packing:action", args=[self.project.pk, "pack-all"]))
        self.assertEqual(get_packlist(self.project).status, PacklistStatus.PACKED)
        self.step("issue")
        self.step("undo-issue")
        self.assertEqual(Project.objects.get(pk=self.project.pk).status, "confirmed")
        self.step("issue")
        self.htmx("post", reverse("packing:action", args=[self.project.pk, "return-all"]))
        self.step("complete-return")
        self.assertEqual(get_packlist(self.project).status, PacklistStatus.RETURNED)

    def test_typed_nonsense_shows_a_message(self) -> None:
        self.assertIn("Bitte eine Zahl eingeben", self.tick(self.cable_line, self.cable, "drei"))
        unknown = self.step("explode")
        self.assertTrue(self.messages_of(unknown))

    def test_kits_are_resolved_into_their_components(self) -> None:
        """PCK-005 (scenario 14): the packlist shows what is actually packed."""
        speaker = make_stock("T-010", 4, "Aktivbox 12 Zoll")
        stand = make_stock("S-020", 6, "Boxenstativ")
        kit = make_product("T-100", "Aktivbox-Set", kind="kit", billing_mode="daily_kit")
        set_kit_components(kit, [(speaker, 1), (stand, 1)])
        add_line(self.project, kit, 2)

        page = self.assert_ok(self.client.get(self.url))
        self.assertIn("Aktivbox 12 Zoll", page)
        self.assertIn("Boxenstativ", page)
        self.assertIn("aus 2 × Aktivbox-Set", page)

    def test_pdf_download(self) -> None:
        response = self.client.get(reverse("packing:pdf", args=[self.project.pk]))
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_warehouse_role_packs_and_issues(self) -> None:
        warehouse = self.browser_for("luka", "Lager")
        self.assertEqual(warehouse.get(self.url).status_code, 200)
        response = warehouse.post(reverse("packing:action", args=[self.project.pk, "issue"]), {"only_packed": "0"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Project.objects.get(pk=self.project.pk).status, "out")

    def test_reader_of_the_packlist_cannot_tick(self) -> None:
        Role.objects.create(name="Fahrer", module_levels={"packing": 1})
        driver = self.browser_for("fritz", "Fahrer")
        page = self.assert_ok(driver.get(self.url))
        self.assertIn("XLR-Kabel 5 m", page)
        self.assertNotIn("hx-post", page)
        self.assertEqual(driver.post(reverse("packing:action", args=[self.project.pk, "issue"])).status_code, 403)
        self.assertEqual(
            driver.post(reverse("packing:row", args=[self.project.pk]), {"line": self.cable_line.pk}).status_code, 403
        )
