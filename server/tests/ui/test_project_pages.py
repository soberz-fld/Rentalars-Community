# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser tests: project list, planning page with lines and groups, price overview, history (PRJ)."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from unittest import mock

from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.availability.engine import AvailabilityEngine
from rentalars.core.demo import create_demo_data
from rentalars.masterdata.models import RentalScale, Supplier
from rentalars.products.models import Product
from rentalars.projects.models import Group, MaterialLine, Project
from rentalars.projects.planning import build_patch, build_planning
from tests.helpers import add_group, add_line, at, make_customer, make_product, make_project, make_stock
from tests.ui.base import UiTestCase, form_data


class ProjectListAndFormTests(UiTestCase):
    """Project list and master data (PRJ-001 to PRJ-009, PRJ-027)."""

    def test_create_project(self) -> None:
        """PRJ-003."""
        customer = make_customer("Stadt Musterstadt, Kulturamt")
        page = self.client.get(reverse("projects:create"), {"customer": customer.pk})
        data = form_data(
            page,
            name="Stadtfest Hauptbühne",
            customer=customer.pk,
            venue="Marktplatz",
            start="2027-03-10T08:00",
            end="2027-03-12T18:00",
            event_start="2027-03-11T10:00",
            event_end="2027-03-12T01:00",
        )

        response = self.client.post(reverse("projects:create"), data)

        project = Project.objects.get(name="Stadtfest Hauptbühne")
        self.assertRedirects(response, reverse("projects:detail", args=[project.pk]))
        self.assertEqual(project.status, "inquiry")
        self.assertEqual(project.manager, self.admin_user)
        self.assertEqual(project.start, at(10, 8))
        self.assertEqual(project.effective_rental_days, 1)

    def test_end_before_start_is_explained_in_the_form(self) -> None:
        """PRJ-004."""
        customer = make_customer()
        page = self.client.get(reverse("projects:create"))
        response = self.client.post(
            reverse("projects:create"),
            form_data(page, name="Verkehrt", customer=customer.pk, start="2027-03-12T08:00", end="2027-03-10T08:00"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(Project.objects.exists())

    def test_list_hides_finished_projects_until_asked(self) -> None:
        """PRJ-027: the everyday view shows what is still to do; a search looks everywhere."""
        make_project("Stadtfest", start=at(10), end=at(12))
        old = make_project("Altprojekt", start=at(1), end=at(2), status="inquiry")
        Project.objects.filter(pk=old.pk).update(status="cancelled")

        everyday = self.assert_ok(self.client.get(reverse("projects:list")))
        self.assertIn("Stadtfest", everyday)
        self.assertNotIn("Altprojekt", everyday)
        self.assertIn("Altprojekt", self.assert_ok(self.client.get(reverse("projects:list"), {"status": "cancelled"})))
        self.assertIn("Altprojekt", self.assert_ok(self.client.get(reverse("projects:list"), {"q": "alt"})))
        in_period = self.assert_ok(
            self.client.get(reverse("projects:list"), {"since": "2027-03-09", "until": "2027-03-11"})
        )
        self.assertIn("Stadtfest", in_period)

    def test_status_buttons_follow_the_allowed_steps(self) -> None:
        project = make_project(status="inquiry")
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[project.pk])))
        self.assertIn('value="option"', page)
        self.assertNotIn('value="closed"', page)

        self.client.post(reverse("projects:set_status", args=[project.pk]), {"status": "confirmed"})
        project.refresh_from_db()
        self.assertEqual(project.status, "confirmed")
        refused = self.client.post(reverse("projects:set_status", args=[project.pk]), {"status": "closed"}, follow=True)
        project.refresh_from_db()
        self.assertEqual(project.status, "confirmed")
        self.assertTrue(self.messages_of(refused))

    def test_confirming_a_project_with_a_shortage_warns(self) -> None:
        cable = make_stock("K-005", 2)
        project = make_project(status="inquiry")
        add_line(project, cable, 5)
        response = self.client.post(
            reverse("projects:set_status", args=[project.pk]), {"status": "confirmed"}, follow=True
        )
        self.assertTrue(any("3" in message for message in self.messages_of(response)))

    def test_delete_only_in_planning(self) -> None:
        confirmed = make_project()
        self.client.post(reverse("projects:delete", args=[confirmed.pk]))
        self.assertTrue(Project.objects.filter(pk=confirmed.pk).exists())
        inquiry = make_project("Anfrage", status="inquiry")
        self.assertRedirects(self.client.post(reverse("projects:delete", args=[inquiry.pk])), reverse("projects:list"))
        self.assertFalse(Project.objects.filter(pk=inquiry.pk).exists())


#: Where a part of the planning block starts in the HTML of a page. PRJ-037: the subtotal of a group with
#: subgroups (group-total-…) is a part of its own.
PART_START = re.compile(
    r'<(?:section|div) id="(group-\w+|group-total-\d+|planning-messages|planning-notes|planning-surcharges|'
    r'planning-totals)"'
)


def planning_parts(html: str) -> dict[str, str]:
    """Cut the planning block of a page (or a patch) into its parts, keyed by their ids.

    Whatever differs between a part on a full page and the same part in a
    patch without meaning anything is removed: the marker for htmx and the
    one-time messages.
    """
    # The one-time messages first: their live region is a ``div`` of its own.
    html = re.sub(r'<div role="status">\s*<ul class="messages".*?</ul>\s*</div>', "", html, flags=re.DOTALL)
    starts = [(match.start(), match.group(1)) for match in PART_START.finditer(html)]
    parts = {}
    for index, (start, key) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(html)
        text = html[start:end]
        # A part ends with its own closing tag; what follows belongs to the page around it.
        closing = "</section>" if text.startswith("<section") else "</div>"
        text = text[: text.index(closing) + len(closing)]
        text = text.replace(' hx-swap-oob="true"', "")
        parts[key] = re.sub(r"\s+", " ", text).strip()
    return parts


class PlanningPatchTests(UiTestCase):
    """After a change of one line only the touched parts are sent again (NFA-013).

    The risk of sending parts is a page that shows something outdated. Every
    test here therefore compares the page the user has after the patch with
    the page a full reload would give: they must be the same, part by part.
    The sample data has what makes this hard – a kit, an optional group, a
    percentage surcharge, the same product in several groups and a second
    project that competes for a product.
    """

    def setUp(self) -> None:
        super().setUp()
        create_demo_data()
        self.project = Project.objects.get(name="Stadtfest Hauptbühne")
        self.detail = reverse("projects:detail", args=[self.project.pk])
        self.groups = {group.name: group for group in self.project.groups.all()}

    def page(self) -> dict[str, str]:
        """The parts of the planning as a full page load shows them."""
        return planning_parts(self.assert_ok(self.client.get(self.detail)))

    def line(self, article_number: str, group: str | None) -> MaterialLine:
        """The line for a product in a group (``None``: without group)."""
        return self.project.material_lines.get(
            product__article_number=article_number, group=self.groups[group] if group else None
        )

    def assert_patch_brings_the_page_up_to_date(self, before: dict[str, str], response: object) -> set[str]:
        """Check a patch against a full reload and return the ids of the parts it carried."""
        self.assertEqual(response["HX-Reswap"], "none")  # type: ignore[index]
        # Not addressed to the dialog: an answer that goes there opens it (again).
        self.assertEqual(response["HX-Retarget"], "#planning")  # type: ignore[index]
        patch = planning_parts(self.assert_ok(response))
        # The hints about all lines are not in the patch. The answer announces
        # the change, and the page then fetches them with a second request.
        self.assertNotIn("planning-notes", patch)
        self.assertIn("planningChanged", response["HX-Trigger"])  # type: ignore[index]
        patch.update(planning_parts(self.notes()))
        after = self.page()
        for key, html in after.items():
            if key in patch:
                self.assertEqual(patch[key], html, f"{key} in the patch differs from the reloaded page")
            else:
                self.assertEqual(before[key], html, f"{key} changed, but was not sent again")
        self.assertLessEqual(set(patch), set(after))
        self.assertLessEqual(
            {"planning-messages", "planning-notes", "planning-surcharges", "planning-totals"}, set(patch)
        )
        return set(patch)

    def notes(self) -> str:
        """What the page fetches when an answer announces ``planningChanged``."""
        return self.assert_ok(self.htmx("get", reverse("projects:planning_notes", args=[self.project.pk])))

    def group_ids_in(self, sent: set[str]) -> set[str]:
        """The names of the groups among the ids of a patch."""
        names = {f"group-{group.pk}": name for name, group in self.groups.items()}
        names["group-none"] = "Ohne Teilgruppe"
        return {names[key] for key in sent if key.startswith("group-") and not key.startswith("group-total-")}

    def test_adding_a_line_sends_its_group_and_the_groups_that_share_the_product(self) -> None:
        before = self.page()
        truss = Product.objects.get(article_number="R-010")

        response = self.htmx(
            "post",
            reverse("projects:line_add", args=[self.project.pk]),
            {"product": truss.pk, "quantity": "2", "group": self.groups["Ton FOH"].pk},
        )

        sent = self.assert_patch_brings_the_page_up_to_date(before, response)
        # R-010 is planned in both lighting groups; their figures "elsewhere in this project" moved.
        self.assertEqual(self.group_ids_in(sent), {"Ton FOH", "Licht Front-Traverse", "Licht Rear-Traverse"})
        # The answer is a fraction of the page.
        self.assertNotIn("Nebel und Effekte", response.content.decode())  # type: ignore[attr-defined]

    def test_a_component_of_a_kit_touches_the_group_with_the_kit(self) -> None:
        """VFG-008: loose speakers and speaker sets draw on the same stock."""
        before = self.page()
        speaker = Product.objects.get(article_number="T-010")

        response = self.htmx(
            "post", reverse("projects:line_add", args=[self.project.pk]), {"product": speaker.pk, "quantity": "9"}
        )

        sent = self.assert_patch_brings_the_page_up_to_date(before, response)
        self.assertEqual(self.group_ids_in(sent), {"Ohne Teilgruppe", "Ton FOH"})
        self.assertIn("fehl", response.content.decode())  # type: ignore[attr-defined]

    def test_changing_and_deleting_a_line(self) -> None:
        line = self.line("K-005", "Ton FOH")
        url = reverse("projects:line_edit", args=[self.project.pk, line.pk])
        before = self.page()

        response = self.htmx("post", url, form_data(self.htmx("get", url), quantity="30"))

        sent = self.assert_patch_brings_the_page_up_to_date(before, response)
        self.assertEqual(self.group_ids_in(sent), {"Ton FOH"})
        self.assertEqual(response["HX-Trigger"], "closeDialog, planningChanged")  # type: ignore[index]

        before = self.page()
        response = self.htmx("post", reverse("projects:line_delete", args=[self.project.pk, line.pk]))
        sent = self.assert_patch_brings_the_page_up_to_date(before, response)
        self.assertEqual(self.group_ids_in(sent), {"Ton FOH"})
        self.assertFalse(MaterialLine.objects.filter(pk=line.pk).exists())

    def test_a_subrental_follows_the_line_it_covers(self) -> None:
        """PRJ-056: when the covered line shrinks, the hint at the subrental's group must appear."""
        line = self.line("K-005", "Ton FOH")
        url = reverse("projects:line_edit", args=[self.project.pk, line.pk])
        self.htmx("post", url, form_data(self.htmx("get", url), quantity="26"))
        accepted = self.htmx(
            "post",
            reverse("projects:subrental_accept", args=[self.project.pk, line.pk]),
            {"product": line.product_id, "quantity": 6},
        )
        self.assertIn("davon 6 zugemietet", self.assert_ok(accepted))
        subrental = MaterialLine.objects.get(covers_line=line)
        # Move the subrental into another group, so that covered and covering line are apart.
        subrental.group = self.groups["Licht Rear-Traverse"]
        subrental.save()
        before = self.page()

        response = self.htmx("post", url, form_data(self.htmx("get", url), quantity="22"))

        sent = self.assert_patch_brings_the_page_up_to_date(before, response)
        # PRJ-084: the subrental is shown below the line it covers, wherever it stands itself.
        self.assertEqual(self.group_ids_in(sent), {"Ton FOH"})
        self.assertIn("nicht mehr in voller Höhe", self.notes())

    def test_a_percentage_surcharge_follows_the_lines_it_refers_to(self) -> None:
        """PRD-039: the night surcharge refers to both lighting groups."""
        line = self.line("L-010", "Licht Front-Traverse")
        url = reverse("projects:line_edit", args=[self.project.pk, line.pk])
        before = self.page()
        self.assertIn("67,20", before["planning-surcharges"])

        response = self.htmx("post", url, form_data(self.htmx("get", url), quantity="4"))

        self.assert_patch_brings_the_page_up_to_date(before, response)
        # 4 × 20,00 × 1,5 = 120,00 instead of 240,00: the base falls by 120,00, the surcharge by 12,00.
        self.assertIn("55,20", planning_parts(response.content.decode())["planning-surcharges"])  # type: ignore[attr-defined]

    def test_no_line_of_the_sample_project_leaves_anything_outdated_when_it_changes(self) -> None:
        """Every kind of line once: rental, kit, sale, service, surcharge, in normal and optional groups."""
        for line in list(self.project.material_lines.select_related("product")):
            if line.is_percent_surcharge:
                continue  # has no quantity; its targets are covered by the test above
            with self.subTest(line=line.title):
                url = reverse("projects:line_edit", args=[self.project.pk, line.pk])
                before = self.page()
                response = self.htmx("post", url, form_data(self.htmx("get", url), quantity=str(line.quantity + 5)))
                self.assert_patch_brings_the_page_up_to_date(before, response)

    def test_lines_shown_in_a_patch_are_judged_as_in_the_whole_planning(self) -> None:
        """PRJ-042: a patch judges fewer lines, but none of them differently."""
        whole = {planned.line.pk: planned for planned in build_planning(self.project).all_lines}
        sections: list[int | None] = [None, *(group.pk for group in self.groups.values())]
        for section in sections:
            with self.subTest(section=section):
                planning, patch = build_patch(self.project, AvailabilityEngine(), product_ids=[], group_ids=[section])
                shown = [planned for group in patch.groups for planned in group.lines] + planning.surcharges
                shown += planning.ungrouped if patch.ungrouped else []
                self.assertTrue(shown)
                for planned in shown:
                    expected = whole[planned.line.pk]
                    self.assertEqual(planned.availability, expected.availability, planned.line.title)
                    self.assertEqual(planned.shortages, expected.shortages, planned.line.title)
                    self.assertEqual(planned.covered_by, expected.covered_by, planned.line.title)
                    self.assertEqual(planned.price, expected.price, planned.line.title)
        self.assertEqual(
            build_patch(self.project, AvailabilityEngine(), product_ids=[], group_ids=[])[0].prices.gross_total,
            build_planning(self.project).prices.gross_total,
        )

    def test_a_patch_judges_only_the_lines_that_matter(self) -> None:
        """NFA-013: the availability of untouched groups is not calculated again."""
        judged: list[int] = []
        calculate = AvailabilityEngine.project_availability

        def counting(engine: AvailabilityEngine, project: Project, lines: list[MaterialLine], *rest: object) -> object:
            judged.append(len(lines))
            return calculate(engine, project, lines, *rest)  # type: ignore[arg-type]

        fog = Product.objects.get(article_number="L-020")
        with mock.patch.object(AvailabilityEngine, "project_availability", counting):
            response = self.htmx(
                "post",
                reverse("projects:line_add", args=[self.project.pk]),
                {"product": fog.pk, "quantity": "1", "group": self.groups["Licht Rear-Traverse"].pk},
            )
        self.assert_ok(response)
        # Twice: the check of the new line while its product is locked, then the patch.
        self.assertEqual(len(judged), 2)
        self.assertLess(max(judged), self.project.material_lines.count())

    def test_a_partial_planning_refuses_questions_about_all_lines(self) -> None:
        """Otherwise a hint like "nothing is missing" could be made from half the picture."""
        planning, patch = build_patch(self.project, AvailabilityEngine(), product_ids=[], group_ids=[])
        self.assertTrue(planning.partial)
        self.assertEqual(patch.groups, [])
        self.assertFalse(patch.ungrouped)
        for question in ("all_lines", "short_lines", "shortage_total", "excess_cover_lines"):
            with self.assertRaises(RuntimeError, msg=question):
                getattr(planning, question)

    def test_the_hints_need_the_right_to_read_projects(self) -> None:
        url = reverse("projects:planning_notes", args=[self.project.pk])
        self.assertIn('id="planning-notes"', self.assert_ok(self.client.get(url)))
        self.assertEqual(self.client.post(url).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_an_error_sends_the_message_and_no_group(self) -> None:
        before = self.page()
        response = self.htmx(
            "post", reverse("projects:line_add", args=[self.project.pk]), {"product": "", "quantity": "1"}
        )
        sent = self.assert_patch_brings_the_page_up_to_date(before, response)
        self.assertEqual(self.group_ids_in(sent), set())
        self.assertIn("Wähle ein Produkt", response.content.decode())  # type: ignore[attr-defined]

    def test_without_htmx_the_whole_block_comes_back(self) -> None:
        """A plain form post (script blocked, or another client) still gets a complete answer."""
        response = self.client.post(
            reverse("projects:line_add", args=[self.project.pk]),
            {"product": Product.objects.get(article_number="R-010").pk, "quantity": "1"},
        )
        text = self.assert_ok(response)
        self.assertIn('<div id="planning"', text)
        self.assertEqual(set(planning_parts(text)), set(self.page()))

    def test_a_group_discount_shows_only_at_its_own_group(self) -> None:
        group = self.groups["Licht Front-Traverse"]
        group.discount_percent = Decimal("10")
        group.save()
        parts = self.page()
        self.assertIn("Gruppenrabatt", parts[f"group-{group.pk}"])
        for key, html in parts.items():
            if key != f"group-{group.pk}":
                self.assertNotIn("Gruppenrabatt", html, key)


class PlanningPageTests(UiTestCase):
    """The planning page: lines, groups, availability, totals (PRJ-010 to PRJ-042)."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", start=at(10, 8), end=at(12, 18), rental_days=2)
        self.lamp = make_stock("L-010", 6, "LED-Scheinwerfer", price="20.00")
        self.detail = reverse("projects:detail", args=[self.project.pk])

    def add(self, product_id: int, quantity: str = "1", group: Group | None = None) -> object:
        """Add a product through the field on the planning page."""
        return self.htmx(
            "post",
            reverse("projects:line_add", args=[self.project.pk]),
            {"product": product_id, "quantity": quantity, "group": group.pk if group else ""},
        )

    def test_adding_a_product_answers_with_the_refreshed_planning(self) -> None:
        """PRD-001."""
        response = self.add(self.lamp.pk, "4")

        text = self.assert_ok(response)
        # The answer carries the touched parts; each finds its place by its id.
        self.assertEqual(response["HX-Reswap"], "none")
        self.assertIn('<section id="group-none" hx-swap-oob="true"', text)
        self.assertIn('<section id="planning-totals" hx-swap-oob="true"', text)
        self.assertNotIn("<html", text)
        self.assertIn("LED-Scheinwerfer", text)
        # PRJ-063: days and factor stand apart; "2 × 1,5" read like a factor of 3.
        self.assertIn("2 Tage", text)
        self.assertIn("Faktor 1,5", text)
        self.assertNotIn("2 × 1,5", text)
        self.assertIn("120,00", text)
        self.assertIn("frei", text)
        line = MaterialLine.objects.get(project=self.project)
        self.assertEqual(line.quantity, 4)

    def test_overbooking_is_saved_with_a_clear_warning_and_a_subrental_offer(self) -> None:
        """PRJ-013, PRJ-054."""
        response = self.add(self.lamp.pk, "8")

        text = self.assert_ok(response)
        self.assertTrue(MaterialLine.objects.filter(project=self.project, quantity=8).exists())
        self.assertIn("Fehlmenge 2", text)
        self.assertIn("2 × L-010 zumieten", text)
        self.assertIn("fehlen 2", text)

        line = MaterialLine.objects.get(project=self.project)
        accepted = self.htmx(
            "post",
            reverse("projects:subrental_accept", args=[self.project.pk, line.pk]),
            {"product": self.lamp.pk, "quantity": 2},
        )
        text = self.assert_ok(accepted)
        self.assertNotIn("Fehlmenge 2", text)
        self.assertIn("davon 2 zugemietet", text)
        subrental = MaterialLine.objects.get(project=self.project, covers_line=line)
        self.assertEqual(subrental.product.article_number, "E-001")

    def test_adding_nothing_shows_a_message_instead_of_an_error_page(self) -> None:
        response = self.htmx(
            "post", reverse("projects:line_add", args=[self.project.pk]), {"product": "", "quantity": "1"}
        )
        self.assertIn("Wähle ein Produkt", self.assert_ok(response))
        wrong_quantity = self.add(self.lamp.pk, "viele")
        self.assertIn("keine Zahl", self.assert_ok(wrong_quantity))
        self.assertFalse(MaterialLine.objects.exists())

    def test_line_dialog_changes_quantity_period_and_price(self) -> None:
        line = add_line(self.project, self.lamp, 2).line
        url = reverse("projects:line_edit", args=[self.project.pk, line.pk])
        dialog = self.htmx("get", url)
        data = form_data(dialog, quantity="3", unit_price="25.00", discount_percent="10", note="mit Torblende")

        response = self.htmx("post", url, data)

        self.assertEqual(response["HX-Trigger"], "closeDialog, planningChanged")
        line.refresh_from_db()
        self.assertEqual(
            (line.quantity, line.unit_price, line.discount_percent, line.note),
            (3, Decimal("25.00"), Decimal("10"), "mit Torblende"),
        )
        # 3 × 25,00 × 1,5 = 112,50, minus 10 % = 101,25
        self.assertIn("101,25", self.assert_ok(response))

    def test_a_changed_period_changes_the_rental_days_of_the_line(self) -> None:
        """PRJ-062: a line with a period of its own is charged the days of that period."""
        line = add_line(self.project, self.lamp, 4).line
        url = reverse("projects:line_edit", args=[self.project.pk, line.pk])
        dialog = self.htmx("get", url)

        # Out for one day only: 4 × 20,00 × factor 1 = 80,00 instead of 120,00.
        response = self.htmx("post", url, form_data(dialog, start="2027-03-10T08:00", end="2027-03-11T08:00"))

        text = self.assert_ok(response)
        self.assertIn("1 Tag", text)
        self.assertIn("80,00", text)
        self.assertIn("aus dem Zeitraum dieser Position", text)
        line.refresh_from_db()
        self.assertIsNone(line.rental_days)

        # Rental days typed in on the line win over its period.
        self.htmx("post", url, form_data(self.htmx("get", url), rental_days="2"))
        planning = self.assert_ok(self.client.get(self.detail))
        self.assertIn("an dieser Position eingetragen", planning)
        self.assertIn("120,00", planning)

    def test_the_dialog_tells_the_rental_days_while_the_period_is_typed(self) -> None:
        """PRJ-062: nobody has to save first to see what a changed period means."""
        line = add_line(self.project, self.lamp, 1).line
        url = reverse("projects:line_availability", args=[self.project.pk])

        as_project = self.assert_ok(
            self.client.get(
                url, {"line": line.pk, "quantity": "1", "start": "2027-03-10T08:00", "end": "2027-03-12T18:00"}
            )
        )
        self.assertIn('id="id_rental_days_helptext" hx-swap-oob="true"', as_project)
        self.assertIn("Leer: 2 Tage – wie das Projekt.", as_project)

        own_period = self.assert_ok(
            self.client.get(
                url, {"line": line.pk, "quantity": "1", "start": "2027-03-10T08:00", "end": "2027-03-13T09:00"}
            )
        )
        self.assertIn("Leer: 4 Tage – aus dem Zeitraum dieser Position.", own_period)

        typed = self.assert_ok(
            self.client.get(
                url,
                {
                    "line": line.pk,
                    "quantity": "1",
                    "start": "2027-03-10T08:00",
                    "end": "2027-03-13T09:00",
                    "rental_days": "1",
                },
            )
        )
        self.assertIn("Von Hand eingetragen. Leer wären es 4 Tage", typed)

    def test_from_and_until_stand_in_one_row_of_the_dialog(self) -> None:
        """UIX-014."""
        line = add_line(self.project, self.lamp, 1).line
        dialog = self.assert_ok(self.htmx("get", reverse("projects:line_edit", args=[self.project.pk, line.pk])))
        rows = dialog.split('<div class="form-row')
        period_rows = [row for row in rows if 'name="start"' in row]
        self.assertEqual(len(period_rows), 1)
        self.assertTrue(period_rows[0].startswith(" pair"))
        self.assertIn('name="end"', period_rows[0])

    def test_quantity_fields_do_not_offer_earlier_entries(self) -> None:
        """UIX-014: the browser's list of earlier entries only gets in the way in a quantity field."""
        line = add_line(self.project, self.lamp, 1).line
        dialog = self.assert_ok(self.htmx("get", reverse("projects:line_edit", args=[self.project.pk, line.pk])))
        quantity_field = dialog[dialog.index('name="quantity"') - 200 : dialog.index('name="quantity"') + 200]
        self.assertIn('autocomplete="off"', quantity_field)
        page = self.assert_ok(self.client.get(self.detail))
        add_form = page[page.index('class="line-add') : page.index("</form>", page.index('class="line-add'))]
        self.assertEqual(add_form.count('autocomplete="off"'), 3)

    def test_line_dialog_shows_errors_and_stays_open(self) -> None:
        line = add_line(self.project, self.lamp, 2).line
        url = reverse("projects:line_edit", args=[self.project.pk, line.pk])
        response = self.htmx("post", url, form_data(self.htmx("get", url), end="2027-03-09T08:00"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("HX-Trigger", response)
        self.assertTrue(response.context["form"].errors)

    def test_availability_while_typing_in_the_dialog(self) -> None:
        """PRJ-012: the traffic light follows the typed quantity."""
        url = reverse("projects:line_availability", args=[self.project.pk])
        period = {"start": "2027-03-10T08:00", "end": "2027-03-12T18:00"}
        enough = self.assert_ok(self.client.get(url, {"product": self.lamp.pk, "quantity": "6", **period}))
        self.assertIn("frei", enough.lower())
        short = self.assert_ok(self.client.get(url, {"product": self.lamp.pk, "quantity": "9", **period}))
        self.assertIn("fehlen 3", short)
        self.assertEqual(self.client.get(url, {"product": self.lamp.pk, "quantity": "", **period}).status_code, 200)

    def test_free_line_without_product(self) -> None:
        url = reverse("projects:free_line_add", args=[self.project.pk])
        dialog = self.htmx("get", url)
        response = self.htmx(
            "post", url, form_data(dialog, title="Sonderbau Bühnenkante", quantity="1", unit_price="250.00")
        )
        self.assertEqual(response["HX-Trigger"], "closeDialog, planningChanged")
        line = MaterialLine.objects.get(project=self.project)
        self.assertIsNone(line.product)
        self.assertEqual(line.title, "Sonderbau Bühnenkante")
        self.assertIn("250,00", self.assert_ok(response))

    def test_groups_are_added_edited_copied_and_deleted(self) -> None:
        self.htmx("post", reverse("projects:group_add", args=[self.project.pk]), {"name": "Licht Front-Traverse"})
        group = Group.objects.get(project=self.project)
        self.add(self.lamp.pk, "2", group)

        edit = reverse("projects:group_edit", args=[self.project.pk, group.pk])
        response = self.htmx("post", edit, form_data(self.htmx("get", edit), discount_percent="10"))
        self.assertEqual(response["HX-Trigger"], "closeDialog")
        # 2 × 20,00 × 1,5 = 60,00, minus 10 % = 54,00
        self.assertIn("54,00", self.assert_ok(response))

        self.htmx("post", reverse("projects:group_copy", args=[self.project.pk, group.pk]), {"target": ""})
        self.assertEqual(Group.objects.filter(project=self.project).count(), 2)
        self.assertEqual(MaterialLine.objects.filter(project=self.project).count(), 2)

        missing = self.htmx(
            "post", reverse("projects:group_copy", args=[self.project.pk, group.pk]), {"target": "9999-9999"}
        )
        self.assertIn("9999-9999", self.assert_ok(missing))

        self.htmx("post", reverse("projects:group_delete", args=[self.project.pk, group.pk]))
        self.assertEqual(Group.objects.filter(project=self.project).count(), 1)
        self.assertEqual(MaterialLine.objects.filter(project=self.project, group__isnull=True).count(), 1)
        unnamed = self.htmx("post", reverse("projects:group_add", args=[self.project.pk]), {"name": "  "})
        self.assertIn("Namen", self.assert_ok(unnamed))

    def test_dragging_stores_the_new_order(self) -> None:
        """PRJ-014."""
        front = add_group(self.project, "Front")
        rear = add_group(self.project, "Rear")
        first = add_line(self.project, self.lamp, 1, group=front).line
        second = add_line(self.project, self.lamp, 1, group=front).line
        layout = {"layout": [{"group": front.pk, "lines": [second.pk]}, {"group": rear.pk, "lines": [first.pk]}]}

        response = self.client.post(
            reverse("projects:arrange", args=[self.project.pk]), json.dumps(layout), content_type="application/json"
        )

        self.assertEqual(response.status_code, 204)
        first.refresh_from_db()
        self.assertEqual(first.group, rear)
        broken = self.client.post(
            reverse("projects:arrange", args=[self.project.pk]), "kein json", content_type="application/json"
        )
        self.assertEqual(broken.status_code, 400)

    def test_deleting_a_line(self) -> None:
        line = add_line(self.project, self.lamp, 2).line
        response = self.htmx("post", reverse("projects:line_delete", args=[self.project.pk, line.pk]))
        self.assertIn("Noch keine Positionen", self.assert_ok(response))
        self.assertFalse(MaterialLine.objects.exists())

    def test_outdated_scale_is_flagged_and_can_be_switched(self) -> None:
        """PRD-037."""
        add_line(self.project, self.lamp, 4)
        RentalScale.objects.get(is_default=True).publish(
            [(1, Decimal("1")), (2, Decimal("2"))], extra_day_increment=Decimal("1")
        )

        page = self.assert_ok(self.client.get(self.detail))
        self.assertIn("alte Staffel", page)
        self.assertIn("120,00", page)
        switched = self.htmx("post", reverse("projects:refresh_scales", args=[self.project.pk]))
        text = self.assert_ok(switched)
        self.assertNotIn("alte Staffel", text)
        self.assertIn("160,00", text)

    def test_totals_with_tax_and_contribution_margin(self) -> None:
        """PRJ-024, PRJ-055."""
        add_line(self.project, self.lamp, 8)
        line = MaterialLine.objects.get(project=self.project)
        supplier = Supplier.objects.create(name="Verleih Nord")
        self.htmx(
            "post",
            reverse("projects:subrental_accept", args=[self.project.pk, line.pk]),
            {"product": self.lamp.pk, "quantity": 2, "supplier": supplier.pk},
        )
        subrental = MaterialLine.objects.get(covers_line=line)
        url = reverse("projects:line_edit", args=[self.project.pk, subrental.pk])
        self.htmx("post", url, form_data(self.htmx("get", url), purchase_price="30.00"))

        page = self.assert_ok(self.client.get(self.detail))
        self.assertIn("240,00", page)  # 8 × 20,00 × 1,5
        self.assertIn("45,60", page)  # 19 % tax
        self.assertIn("285,60", page)
        self.assertIn("Verleih Nord", page)
        self.assertIn("60,00", page)  # cost of the subrental: 2 × 30,00
        self.assertIn("180,00", page)  # contribution margin

    def test_closed_project_is_read_only(self) -> None:
        add_line(self.project, self.lamp, 2)
        Project.objects.filter(pk=self.project.pk).update(status="closed")
        page = self.assert_ok(self.client.get(self.detail))
        self.assertIn("abgeschlossen und gegen Änderungen geschützt", page)
        self.assertNotIn(reverse("projects:line_add", args=[self.project.pk]), page)
        refused = self.add(self.lamp.pk, "1")
        self.assertIn("abgeschlossen", self.assert_ok(refused))
        self.assertEqual(MaterialLine.objects.count(), 1)

    def test_reader_sees_the_planning_without_any_control(self) -> None:
        add_line(self.project, self.lamp, 2)
        Role.objects.create(name="Zuschauer", module_levels={"projects": 1})
        reader = self.browser_for("zoe", "Zuschauer")
        page = self.assert_ok(reader.get(self.detail))
        self.assertIn("LED-Scheinwerfer", page)
        self.assertNotIn("hx-post", page)
        self.assertNotIn("20,00", page)
        self.assertEqual(
            self.htmx(
                "post", reverse("projects:line_add", args=[self.project.pk]), {"product": self.lamp.pk}, client=reader
            ).status_code,
            403,
        )


class PriceOverviewAndHistoryTests(UiTestCase):
    """Price overview (scenario 9, DOK-009, PRJ-035, PRJ-036) and project history (PRJ-032)."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest 2027")
        flat = {"billing_mode": "flat"}
        self.front = add_group(self.project, "Licht Front-Traverse")
        add_line(self.project, make_product("L-001", "Stufenlinse 1 kW", price="100.00", **flat), 2, group=self.front)
        add_line(self.project, make_product("L-002", "Profiler 750 W", price="60.00", **flat), 2, group=self.front)
        add_line(self.project, make_product("L-003", "Verfolger", price="100.00", **flat), 1, group=self.front)
        self.rear = add_group(self.project, "Licht Rear-Traverse")
        add_line(self.project, make_product("L-004", "Blinder", price="150.00", **flat), 1, group=self.rear)
        add_line(self.project, make_product("L-005", "Fluter", price="80.00", **flat), 2, group=self.rear)
        add_line(self.project, make_product("S-001", "Absperrgitter", price="50.00", **flat), 1)
        self.url = reverse("projects:price_overview", args=[self.project.pk])

    def test_overview_shows_the_same_groups_and_sums_as_the_planning(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        planning = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.project.pk])))
        for text in ("Licht Front-Traverse", "Licht Rear-Traverse", "420,00", "310,00", "50,00", "780,00"):
            self.assertIn(text, page)
            self.assertIn(text, planning)
        self.assertIn("Internes Arbeitsdokument", page)

    def test_detail_view_lists_all_lines_and_the_compact_view_only_groups(self) -> None:
        """PRJ-036."""
        detailed = self.assert_ok(self.client.get(self.url))
        self.assertIn("Stufenlinse 1 kW", detailed)
        self.assertIn("L-005", detailed)
        compact = self.assert_ok(self.client.get(self.url, {"detail": "groups"}))
        self.assertNotIn("L-001", compact)
        self.assertNotIn("100,00", compact)  # no unit prices
        self.assertIn("420,00", compact)
        self.assertIn("780,00", compact)

    def test_the_compact_view_says_roughly_what_each_group_contains(self) -> None:
        """PRJ-066: the customer should know what the money buys, without every line."""
        compact = self.assert_ok(self.client.get(self.url, {"detail": "groups"}))
        front = compact[compact.index("Licht Front-Traverse") : compact.index("Licht Rear-Traverse")]
        self.assertIn("Enthält: 2 × Stufenlinse 1 kW, 2 × Profiler 750 W, 1 × Verfolger", front)
        self.assertIn('data-copy="Enthält: 2 × Stufenlinse 1 kW, 2 × Profiler 750 W, 1 × Verfolger"', front)
        self.assertIn("Enthält: 1 × Blinder, 2 × Fluter", compact)
        self.assertIn("Enthält: 1 × Absperrgitter", compact)  # the lines without group
        detailed = self.assert_ok(self.client.get(self.url))
        self.assertNotIn("Enthält:", detailed)

    def test_amounts_can_be_copied(self) -> None:
        """PRJ-035: every amount carries its plain value for the clipboard."""
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn('data-copy="420,00"', page)
        self.assertIn('data-copy="780,00"', page)
        self.assertIn('data-copy="Stufenlinse 1 kW"', page)

    def test_overview_needs_the_price_right(self) -> None:
        Role.objects.create(name="Planung", module_levels={"projects": 2})
        planner = self.browser_for("pia", "Planung")
        self.assertEqual(planner.get(self.url).status_code, 403)
        planning = self.assert_ok(planner.get(reverse("projects:detail", args=[self.project.pk])))
        self.assertIn("Licht Front-Traverse", planning)
        self.assertNotIn("420,00", planning)
        self.assertNotIn(self.url, planning)

    def test_history_tells_who_changed_what(self) -> None:
        """PRJ-032: changes of the project, its groups and its lines in one list."""
        line = MaterialLine.objects.filter(project=self.project).first()
        assert line is not None
        url = reverse("projects:line_edit", args=[self.project.pk, line.pk])
        self.htmx("post", url, form_data(self.htmx("get", url), quantity="5"))
        self.client.post(reverse("projects:set_status", args=[self.project.pk]), {"status": "out"})

        page = self.assert_ok(self.client.get(reverse("projects:history", args=[self.project.pk])))
        self.assertIn("admin", page)
        self.assertIn("Menge", page)
        self.assertIn("Unterwegs", page)
        self.assertIn("Licht Front-Traverse", page)
