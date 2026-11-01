# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages for the lines of the planning: PRJ-082, PRJ-083, PRJ-084, PRJ-086, "Gewinn aus dem Projekt" (PRJ-087)."""

from __future__ import annotations

import re
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.core.demo import create_demo_data
from rentalars.masterdata.models import Supplier
from rentalars.products.models import BillingMode, Product
from rentalars.projects import services
from rentalars.projects.models import GroupKind, LineVariant, MaterialLine, Project, ProjectFile, SubrentalStatus
from tests.helpers import ALL_RIGHTS, add_group, add_line, make_product, make_project, make_stock
from tests.ui import test_project_pages
from tests.ui.base import UiTestCase, form_data, forms_of
from tests.unit.test_mvr_import import sample_plot

D = Decimal


def flat(article_number: str, price: str = "100.00") -> Product:
    """A product billed as a flat price."""
    return make_product(article_number, price=price, billing_mode=BillingMode.FLAT)


def row_of(page: str, line: MaterialLine) -> str:
    """The table row of a line on the planning page."""
    row = page[page.index(f'data-line="{line.pk}"') :]
    return row[: row.index("</tr>")]


class PlanningLinesTestCase(UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.light = add_group(self.project, "Licht")
        self.sound = add_group(self.project, "Ton")
        self.spot = add_line(self.project, flat("L-010"), 2, group=self.light).line
        self.wash = add_line(self.project, flat("L-020", "50.00"), 4, group=self.light).line
        self.speaker = add_line(self.project, flat("T-010", "80.00"), 2, group=self.sound).line
        self.detail = reverse("projects:detail", args=[self.project.pk])
        self.bulk = reverse("projects:lines_bulk", args=[self.project.pk])


class SelectionPageTests(PlanningLinesTestCase):
    """PRJ-082: boxes to choose lines, a box per section for all of them, and the bar of actions."""

    def test_editors_see_boxes_and_the_bar(self) -> None:
        page = self.assert_ok(self.client.get(self.detail))
        self.assertIn('id="line-selection"', page)
        self.assertIn("data-selection-bar hidden", page)
        row = row_of(page, self.spot)
        self.assertIn(f'name="lines" value="{self.spot.pk}" form="line-selection"', row)
        self.assertIn('aria-label="Position auswählen: 2 × Produkt L-010"', row)
        self.assertIn('aria-label="Alle Positionen dieser Teilgruppe auswählen"', page)
        bar = page[page.index('id="line-selection"') :]
        bar = bar[: bar.index("</form>")]
        for text in ("Optional", "Nicht mehr optional", "Als Alternative zu …", "Verschieben", "Rabatt setzen"):
            self.assertIn(text, bar)
        self.assertIn('data-confirm="Die gewählten Positionen löschen?"', bar)
        # Every group can be chosen as the place to move to, also a subgroup; and "without group".
        self.assertIn('<option value="none">ohne Teilgruppe</option>', bar)
        self.assertIn(f'<option value="{self.light.pk}">Licht</option>', bar)

    def test_readers_see_neither(self) -> None:
        reader = self.browser_for("nora", "Nur-Lesen")
        page = self.assert_ok(reader.get(self.detail))
        self.assertNotIn("line-selection", page)
        self.assertNotIn("data-select-line", page)

    def test_without_the_price_right_there_is_no_discount_field(self) -> None:
        Role.objects.create(name="Planung ohne Preise", module_levels={"projects": 2})
        planner = self.browser_for("paul", "Planung ohne Preise")
        page = self.assert_ok(planner.get(self.detail))
        self.assertIn('id="line-selection"', page)
        self.assertNotIn('name="discount_percent"', page)

    def test_optional_for_several_lines(self) -> None:
        response = self.htmx("post", self.bulk, {"lines": [self.spot.pk, self.speaker.pk], "action": "optional"})
        text = self.assert_ok(response)
        self.assertEqual(response["HX-Reswap"], "none")  # the touched groups are sent again
        self.assertIn("2 Positionen sind jetzt optional.", text)
        self.assertIn(f'id="group-{self.light.pk}"', text)
        self.assertIn(f'id="group-{self.sound.pk}"', text)
        self.assertEqual(
            set(MaterialLine.objects.filter(variant=LineVariant.OPTIONAL).values_list("pk", flat=True)),
            {self.spot.pk, self.speaker.pk},
        )

    def test_move_discount_and_delete(self) -> None:
        self.htmx("post", self.bulk, {"lines": [self.spot.pk, self.wash.pk], "action": "move", "group": self.sound.pk})
        self.assertEqual(
            set(self.sound.lines.values_list("pk", flat=True)), {self.spot.pk, self.wash.pk, self.speaker.pk}
        )
        nothing = self.assert_ok(self.htmx("post", self.bulk, {"lines": [self.spot.pk], "action": "move", "group": ""}))
        self.assertIn("Wähle die Teilgruppe, in die die Positionen kommen.", nothing)
        self.htmx("post", self.bulk, {"lines": [self.spot.pk], "action": "move", "group": "none"})
        self.spot.refresh_from_db()
        self.assertIsNone(self.spot.group)
        text = self.assert_ok(
            self.htmx("post", self.bulk, {"lines": [self.wash.pk], "action": "discount", "discount_percent": "12,5"})
        )
        self.assertIn("1 Position hat jetzt 12,5 % Rabatt.", text)
        self.wash.refresh_from_db()
        self.assertEqual(self.wash.discount_percent, D("12.5"))
        text = self.assert_ok(self.htmx("post", self.bulk, {"lines": [self.spot.pk, self.wash.pk], "action": "delete"}))
        self.assertIn("2 Positionen gelöscht.", text)
        self.assertEqual(list(self.project.material_lines.values_list("pk", flat=True)), [self.speaker.pk])

    def test_lines_that_cannot_be_changed_are_named(self) -> None:
        subrental = services.accept_subrental_suggestion(self.spot, self.spot.product, 1, rights=ALL_RIGHTS)
        text = self.assert_ok(
            self.htmx("post", self.bulk, {"lines": [self.wash.pk, subrental.pk], "action": "optional"})
        )
        self.assertIn("1 Position ist jetzt optional.", text)
        self.assertIn("Unverändert geblieben: 1 × Produkt L-010 (deckt die Fehlmenge einer anderen Position", text)

    def test_the_bulk_request_needs_write_access(self) -> None:
        reader = self.browser_for("nora", "Nur-Lesen")
        response = self.htmx("post", self.bulk, {"lines": [self.spot.pk], "action": "optional"}, client=reader)
        self.assertEqual(response.status_code, 403)
        self.spot.refresh_from_db()
        self.assertEqual(self.spot.variant, "")


class IconPageTests(PlanningLinesTestCase):
    """PRJ-083: the buttons "optional" and "Alternative" of lines and groups."""

    def test_the_optional_button_switches_and_shows_its_state(self) -> None:
        row = row_of(self.assert_ok(self.client.get(self.detail)), self.spot)
        self.assertIn('aria-pressed="false"', row)
        self.assertIn(f'hx-vals=\'{{"lines": "{self.spot.pk}", "action": "optional"}}\'', row)
        self.htmx("post", self.bulk, {"lines": self.spot.pk, "action": "optional"})
        row = row_of(self.assert_ok(self.client.get(self.detail)), self.spot)
        self.assertIn('aria-pressed="true"', row)
        self.assertIn('"action": "normal"', row)
        # Order of the buttons: optional, alternative, edit, copy, delete.
        labels = re.findall(r'class="icon-btn[^"]*"[^>]*aria-label="([^"]+)"', row)
        self.assertEqual(
            labels,
            [
                "Optional",
                "Alternative zu einer anderen Position …",
                "Position bearbeiten",
                "Position duplizieren",
                "Position löschen",
            ],
        )

    def test_the_alternative_dialog(self) -> None:
        url = reverse("projects:lines_alternative", args=[self.project.pk])
        dialog = self.assert_ok(self.htmx("get", f"{url}?lines={self.wash.pk}"))
        self.assertIn("Diese Position wird eine Alternative:", dialog)
        self.assertIn("4 × Produkt L-020", dialog)
        self.assertIn(f'<option value="{self.spot.pk}">2 × Produkt L-010</option>', dialog)
        self.assertNotIn(f'<option value="{self.wash.pk}">', dialog)
        self.assertIn('<optgroup label="Licht">', dialog)
        # Required.
        refused = self.assert_ok(self.htmx("post", url, {"lines": self.wash.pk, "alternative_to": ""}))
        self.assertIn("Wähle die Position, die diese ersetzen könnte.", refused)
        done = self.htmx("post", url, {"lines": self.wash.pk, "alternative_to": self.spot.pk})
        self.assertIn("closeDialog", done["HX-Trigger"])
        self.wash.refresh_from_db()
        self.assertEqual((self.wash.variant, self.wash.alternative_to), (LineVariant.ALTERNATIVE, self.spot))
        row = row_of(self.assert_ok(self.client.get(self.detail)), self.wash)
        self.assertIn("Alternative zu „2 × Produkt L-010“", row)

    def test_the_dialog_for_several_lines(self) -> None:
        url = reverse("projects:lines_alternative", args=[self.project.pk])
        dialog = self.assert_ok(self.htmx("get", f"{url}?lines={self.wash.pk}&lines={self.speaker.pk}"))
        self.assertIn("Diese 2 Positionen werden Alternativen:", dialog)
        self.htmx("post", url, {"lines": [self.wash.pk, self.speaker.pk], "alternative_to": self.spot.pk})
        self.assertEqual(self.spot.alternatives.count(), 2)

    def test_the_edit_dialog_asks_what_an_alternative_replaces(self) -> None:
        url = reverse("projects:line_edit", args=[self.project.pk, self.wash.pk])
        dialog = self.assert_ok(self.htmx("get", url))
        self.assertIn('data-show-if="variant=alternative"', dialog)
        refused = self.assert_ok(self.htmx("post", url, form_data(self.htmx("get", url), variant="alternative")))
        self.assertIn("Wähle die Position, die diese ersetzen könnte.", refused)
        self.htmx("post", url, form_data(self.htmx("get", url), variant="alternative", alternative_to=self.spot.pk))
        self.wash.refresh_from_db()
        self.assertEqual(self.wash.alternative_to, self.spot)

    def test_group_buttons(self) -> None:
        page = self.assert_ok(self.client.get(self.detail))
        head = page[page.index(f'id="group-{self.sound.pk}"') :]
        head = head[: head.index("</div>")]
        self.assertIn('aria-label="Optionale Teilgruppe"', head)
        self.assertIn('aria-label="Alternative zu einer anderen Teilgruppe …"', head)
        self.htmx("post", reverse("projects:group_kind", args=[self.project.pk, self.sound.pk]), {"kind": "optional"})
        self.sound.refresh_from_db()
        self.assertEqual(self.sound.kind, GroupKind.OPTIONAL)
        url = reverse("projects:group_alternative", args=[self.project.pk, self.sound.pk])
        dialog = self.assert_ok(self.htmx("get", url))
        self.assertIn("„Ton“ als Alternative", dialog)
        self.htmx("post", url, {"alternative_to": self.light.pk})
        self.sound.refresh_from_db()
        self.assertEqual((self.sound.kind, self.sound.alternative_to), (GroupKind.ALTERNATIVE, self.light))
        page = self.assert_ok(self.client.get(self.detail))
        self.assertIn("Alternative zu „Licht“", page)
        self.htmx("post", reverse("projects:group_kind", args=[self.project.pk, self.sound.pk]), {"kind": "normal"})
        self.sound.refresh_from_db()
        self.assertEqual((self.sound.kind, self.sound.alternative_to), (GroupKind.NORMAL, None))

    def test_price_overview_names_what_an_alternative_replaces(self) -> None:
        services.update_line(self.wash, rights=ALL_RIGHTS, alternative_to=self.spot)
        services.update_group(self.sound, rights=ALL_RIGHTS, alternative_to=self.light)
        page = self.assert_ok(self.client.get(reverse("projects:price_overview", args=[self.project.pk])))
        self.assertIn("Alternative zu „2 × Produkt L-010“", page)
        self.assertIn("Alternative zu „Licht“", page)


class SubrentalPageTests(UiTestCase):
    """PRJ-084: the subrental as a part of its line – asked for without a rental price, shown below the line."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.group = add_group(self.project, "Licht")
        self.spots = make_stock("L-010", 4, "Spot", price="20.00")
        self.line = add_line(self.project, self.spots, 6, group=self.group).line
        self.supplier = Supplier.objects.create(name="Verleih Nord")
        self.detail = reverse("projects:detail", args=[self.project.pk])
        self.url = reverse("projects:subrental_accept", args=[self.project.pk, self.line.pk])

    def test_the_suggestion_opens_a_dialog_without_rental_price(self) -> None:
        offer = next(form for form in forms_of(self.client.get(self.detail)) if form.data.get("quantity") == "2")
        self.assertEqual(offer.attributes["hx-get"], self.url)
        dialog = self.assert_ok(self.htmx("get", self.url, offer.data))
        for name in ("quantity", "supplier", "purchase_price", "status"):
            self.assertIn(f'name="{name}"', dialog)
        self.assertNotIn('name="unit_price"', dialog)
        self.assertIn("keinen eigenen Mietpreis", dialog)
        data = form_data(self.htmx("get", self.url, offer.data), containing="quantity")
        data.update(supplier=self.supplier.pk, purchase_price="12,50", status=SubrentalStatus.ORDERED)
        done = self.htmx("post", self.url, data)
        self.assertIn("closeDialog", done["HX-Trigger"])
        subrental = MaterialLine.objects.get(covers_line=self.line)
        self.assertEqual(
            (subrental.quantity, subrental.supplier, subrental.purchase_price, subrental.subrental_status),
            (D("2"), self.supplier, D("12.50"), SubrentalStatus.ORDERED),
        )

    def test_shown_below_the_line_without_a_price(self) -> None:
        services.accept_subrental_suggestion(
            self.line, self.spots, 2, rights=ALL_RIGHTS, supplier=self.supplier, purchase_price=D("12.50")
        )
        subrental = MaterialLine.objects.get(covers_line=self.line)
        page = self.assert_ok(self.client.get(self.detail))
        self.assertNotIn(f'data-line="{subrental.pk}"', page)  # no line of its own
        after_line = page[page.index(f'data-line="{self.line.pk}"') :]
        sub_row = after_line[after_line.index("</tr>") :]
        sub_row = sub_row[: sub_row.index("</tr>", 6)]
        self.assertIn(f'data-covering="{subrental.pk}"', sub_row)
        self.assertIn("davon 2 zugemietet", sub_row)
        # PRJ-106: the supplier leads to the page of its subrentals; PRJ-101: a new subrental is "open".
        page_url = reverse("projects:subrental", args=[self.project.pk, self.supplier.pk])
        self.assertIn(f'bei <a href="{page_url}">Verleih Nord</a>', sub_row)
        self.assertIn("offen", sub_row)
        self.assertIn("EK 12,50 € je Stk. (25,00 €)", sub_row)
        self.assertNotIn("nicht berechnet", sub_row)
        # The total is the line's price: 6 × 20,00 × 1,5.
        self.assertIn("180,00", page)

    def test_the_edit_dialog_has_no_price_fields(self) -> None:
        subrental = services.accept_subrental_suggestion(self.line, self.spots, 2, rights=ALL_RIGHTS)
        dialog = self.assert_ok(self.htmx("get", reverse("projects:line_edit", args=[self.project.pk, subrental.pk])))
        for name in ("unit_price", "discount_percent", "rental_days", "manual_scale_factor", "variant", "group"):
            self.assertNotIn(f'name="{name}"', dialog)
        for name in ("quantity", "supplier", "subrental_status", "purchase_price"):
            self.assertIn(f'name="{name}"', dialog)
        self.assertIn("Teil der Position „6 × Spot“", dialog)


class SubrentalPatchTests(UiTestCase):
    """PRJ-082 and PRJ-084 against a full reload, on the sample data (as ``PlanningPatchTests``).

    The module is imported, not the class: a test class among the names of this module would run here again.
    """

    def setUp(self) -> None:
        super().setUp()
        create_demo_data()
        self.project = Project.objects.get(name="Stadtfest Hauptbühne")
        self.detail = reverse("projects:detail", args=[self.project.pk])
        self.groups = {group.name: group for group in self.project.groups.all()}

    page = test_project_pages.PlanningPatchTests.page
    line = test_project_pages.PlanningPatchTests.line
    assert_patch_brings_the_page_up_to_date = (
        test_project_pages.PlanningPatchTests.assert_patch_brings_the_page_up_to_date
    )
    notes = test_project_pages.PlanningPatchTests.notes
    group_ids_in = test_project_pages.PlanningPatchTests.group_ids_in

    def test_several_lines_at_once(self) -> None:
        front = self.line("L-010", "Licht Front-Traverse")
        foh = self.line("K-005", "Ton FOH")
        before = self.page()
        response = self.htmx(
            "post",
            reverse("projects:lines_bulk", args=[self.project.pk]),
            {"lines": [front.pk, foh.pk], "action": "optional"},
        )
        sent = self.assert_patch_brings_the_page_up_to_date(before, response)
        self.assertLessEqual({"Licht Front-Traverse", "Ton FOH"}, self.group_ids_in(sent))

    def test_moving_lines_into_another_group(self) -> None:
        foh = self.line("K-005", "Ton FOH")
        before = self.page()
        response = self.htmx(
            "post",
            reverse("projects:lines_bulk", args=[self.project.pk]),
            {"lines": [foh.pk], "action": "move", "group": self.groups["Nebel und Effekte"].pk},
        )
        sent = self.assert_patch_brings_the_page_up_to_date(before, response)
        self.assertLessEqual({"Ton FOH", "Nebel und Effekte"}, self.group_ids_in(sent))

    def test_an_alternative_shows_the_new_title_of_its_counterpart(self) -> None:
        front = self.line("L-010", "Licht Front-Traverse")
        foh = self.line("K-005", "Ton FOH")
        services.update_line(foh, rights=ALL_RIGHTS, alternative_to=front)
        url = reverse("projects:line_edit", args=[self.project.pk, front.pk])
        before = self.page()
        response = self.htmx("post", url, form_data(self.htmx("get", url), quantity="5"))
        sent = self.assert_patch_brings_the_page_up_to_date(before, response)
        self.assertIn("Ton FOH", self.group_ids_in(sent))


class PlanningAreaPageTests(PlanningLinesTestCase):
    """PRJ-086 and the new name of the contribution margin."""

    def test_the_row_below_the_material(self) -> None:
        page = self.assert_ok(self.client.get(self.detail))
        actions = page[page.index('class="planning-actions') :]
        actions = actions[: actions.index("</div>")]
        order = [
            actions.index(text) for text in ("Teilgruppe hinzufügen", "Position ohne Produkt", "MVR-Datei importieren")
        ]
        self.assertEqual(order, sorted(order))
        # Right after the lines without group, before the personnel.
        self.assertLess(page.index('id="group-none"'), page.index('class="planning-actions'))
        self.assertNotIn("Lichtplot importieren", page)

    def test_profit_instead_of_contribution_margin(self) -> None:
        page = self.assert_ok(self.client.get(self.detail))
        self.assertIn("Gewinn aus dem Projekt", page)
        self.assertNotIn("Deckungsbeitrag", page)


class MvrFilePageTests(UiTestCase):
    """PRJ-086: the MVR file goes into the files of the project; MVR files can be uploaded there by hand."""

    def setUp(self) -> None:
        super().setUp()
        self.spot = make_product("L-010", "Robin T1 Profile", price="80.00")
        self.project = make_project()
        self.url = reverse("projects:mvr_import", args=[self.project.pk])

    def upload(self, name: str = "Stadtfest.mvr") -> SimpleUploadedFile:
        return SimpleUploadedFile(name, sample_plot(), content_type="application/zip")

    def test_the_file_is_kept_with_a_time_stamp(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn("<title>MVR-Datei importieren", page)
        self.client.post(self.url, {"step": "upload", "file": self.upload()})
        kept = ProjectFile.objects.get(project=self.project)
        self.assertRegex(kept.original_name, r"^\d{8}-\d{6}_Stadtfest\.mvr$")
        self.assertFalse(kept.visible_to_crew)
        data = form_data(self.client.get(self.url), containing="key_0")
        done = self.client.post(self.url, {**data, "step": "apply"}, follow=True)
        self.assertIn(f"Die MVR-Datei liegt in den Dateien des Projekts: {kept.original_name}", self.messages_of(done))
        files = self.assert_ok(self.client.get(reverse("documents:list", args=[self.project.pk])))
        self.assertIn(kept.original_name, files)

    def test_choosing_another_file_removes_it_again(self) -> None:
        self.client.post(self.url, {"step": "upload", "file": self.upload()})
        self.assertEqual(ProjectFile.objects.filter(project=self.project).count(), 1)
        self.client.post(self.url, {"step": "discard"})
        self.assertFalse(ProjectFile.objects.filter(project=self.project).exists())

    def test_upload_by_hand_in_the_files_tab(self) -> None:
        url = reverse("projects:files", args=[self.project.pk])
        page = self.client.get(reverse("documents:list", args=[self.project.pk]))
        data = form_data(page, containing="title")
        data["file"] = self.upload("Rig.mvr")
        self.client.post(url, data)
        self.assertEqual(ProjectFile.objects.get(project=self.project).original_name, "Rig.mvr")


class DemoDataTests(UiTestCase):
    """The sample project keeps working with the new planning."""

    def test_the_sample_planning(self) -> None:
        create_demo_data()
        project = Project.objects.get(name="Stadtfest Hauptbühne")
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[project.pk])))
        self.assertIn("data-select-line", page)
