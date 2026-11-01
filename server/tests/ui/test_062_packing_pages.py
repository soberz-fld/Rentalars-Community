# SPDX-License-Identifier: GPL-3.0-or-later
"""Page tests of the issue per article (PCK-025): the pack bar, a partly issued packlist, the start page."""

from __future__ import annotations

import re

from django.urls import reverse

from rentalars.packing import services
from rentalars.packing.models import PacklistStatus
from rentalars.packing.pdf import render_packlist_html
from rentalars.projects.models import ProjectStatus
from tests.helpers import add_line, at, make_item, make_model, make_product, make_project, make_stock
from tests.ui.base import UiTestCase, forms_of


class PartlyIssuedPageTests(UiTestCase):
    """Six cables, two lights and a single rack on the packlist of a confirmed project."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest")
        self.cables = make_stock("K-005", 10, "XLR-Kabel")
        self.lights = make_stock("L-010", 4, "PAR 64")
        self.rack = make_product("T-500", "Funkrack")
        make_item(make_model("Funkrack 4 HE", self.rack), 500)
        self.cable_line = add_line(self.project, self.cables, 6).line
        self.light_line = add_line(self.project, self.lights, 2).line
        self.rack_line = add_line(self.project, self.rack, 1).line
        self.url = reverse("packing:packlist", args=[self.project.pk])

    def tick(self, line: object, quantity: int) -> None:
        self.htmx(
            "post",
            reverse("packing:row", args=[self.project.pk]),
            {"mode": "pack", "line": line.pk, "product": line.product_id, "quantity": str(quantity)},  # type: ignore[attr-defined]
        )

    def issue_form(self, page_response: object, only_packed: str) -> dict[str, str]:
        """The data of the form behind "Ausgeben" (1) or "Alles ausgeben" (0)."""
        for form in forms_of(page_response):
            if form.action.endswith("/issue/") and form.data.get("only_packed") == only_packed:
                return {name: value for name, value in form.data.items() if name != "csrfmiddlewaretoken"}
        raise AssertionError(f"No issue form with only_packed={only_packed} on the page.")

    def pack_bar(self, page: str) -> str:
        return page[page.index('class="pack-bar') :]

    def row_of(self, page: str, article_number: str) -> str:
        """The HTML of the packlist row of a product."""
        rows = re.findall(r'<li class="pack-row.*?</li>', page, flags=re.S)
        return next(row for row in rows if f'<span class="artno">{article_number}</span>' in row)

    def test_issue_is_only_possible_once_something_is_ticked(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        bar = self.pack_bar(page)
        self.assertIn("Hake ab, was rausgeht.", bar)
        self.assertRegex(bar, r'<button class="btn" type="submit" aria-describedby="issue-ready" disabled>')
        self.assertIn("Alles ausgeben", bar)
        self.assertNotIn("Nur Abgehaktes ausgeben", bar)
        self.tick(self.cable_line, 4)
        bar = self.pack_bar(self.assert_ok(self.client.get(self.url)))
        self.assertIn("4 abgehakte Stück gehen raus.", bar)
        self.assertNotIn("disabled", bar)

    def test_issue_the_ticked_rows_and_pack_on(self) -> None:
        self.tick(self.cable_line, 4)
        self.tick(self.rack_line, 1)
        response = self.client.post(
            reverse("packing:action", args=[self.project.pk, "issue"]),
            self.issue_form(self.client.get(self.url), "1"),
            follow=True,
        )
        self.assertIn("Das abgehakte Material ist ausgegeben; der Rest kann folgen.", self.messages_of(response))
        page = self.assert_ok(response)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, ProjectStatus.CONFIRMED)
        self.assertEqual(services.get_packlist(self.project).status, PacklistStatus.PARTLY_ISSUED)
        # The page stays in packing mode and says what is out and what the project waits for.
        self.assertIn("Teilweise ausgegeben: 5 von 9 Stück sind unterwegs. 4 Stück sind noch nicht ausgegeben.", page)
        self.assertIn("Das Projekt bleibt „Bestätigt“, bis alles ausgegeben ist.", page)
        self.assertIn('<span class="badge yellow">teilweise ausgegeben</span>', page)
        # The rack went out in full: no tick any more. The cables went out in part: they are packed on.
        rack_row = self.row_of(page, "T-500")
        self.assertIn("is-issued", rack_row)
        self.assertIn('<span class="badge solid">ausgegeben</span>', rack_row)
        self.assertNotIn("pack-check", rack_row)
        self.assertNotIn("Exemplare wählen", rack_row)
        cable_row = self.row_of(page, "K-005")
        self.assertIn("4 von 6 ausgegeben", cable_row)
        self.assertIn('min="4"', cable_row)
        self.assertIn("pack-check", self.row_of(page, "L-010"))

        self.tick(self.cable_line, 6)
        self.tick(self.light_line, 2)
        response = self.client.post(
            reverse("packing:action", args=[self.project.pk, "issue"]),
            self.issue_form(self.client.get(self.url), "1"),
            follow=True,
        )
        self.assertIn(
            "Das Material ist ausgegeben. Das Projekt steht jetzt auf „Unterwegs“.", self.messages_of(response)
        )
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, ProjectStatus.OUT)

    def test_issue_everything_for_packing_on_paper(self) -> None:
        self.tick(self.cable_line, 2)
        page = self.client.get(self.url)
        self.assertIn(
            "Alles mit voller Menge ausgeben, auch was nicht abgehakt ist?", self.pack_bar(self.assert_ok(page))
        )
        self.client.post(reverse("packing:action", args=[self.project.pk, "issue"]), self.issue_form(page, "0"))
        self.assertEqual(services.get_packlist(self.project).status, PacklistStatus.ISSUED)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, ProjectStatus.OUT)

    def test_everything_ticked_needs_no_second_button(self) -> None:
        self.client.post(reverse("packing:action", args=[self.project.pk, "pack-all"]))
        bar = self.pack_bar(self.assert_ok(self.client.get(self.url)))
        self.assertNotIn("Alles ausgeben", bar)
        self.assertIn("9 abgehakte Stück gehen raus.", bar)

    def test_nothing_ticked_is_explained(self) -> None:
        response = self.client.post(reverse("packing:action", args=[self.project.pk, "issue"]), follow=True)
        self.assertIn(
            "Es ist nichts abgehakt, was noch nicht ausgegeben ist. Hake ab, was rausgeht, oder gib alles aus.",
            self.messages_of(response),
        )
        self.assertEqual(services.get_packlist(self.project).status, PacklistStatus.OPEN)

    def test_taking_back_shows_what_went_out(self) -> None:
        self.tick(self.cable_line, 4)
        services.issue(services.get_packlist(self.project), only_packed=True)
        page = self.assert_ok(self.client.get(self.url, {"mode": "return"}))
        self.assertIn("4 von 6 ausgegeben", self.row_of(page, "K-005"))
        self.assertIn("nicht ausgegeben", self.row_of(page, "L-010"))
        self.assertIn("Alles ist zurück", self.pack_bar(page))

    def test_the_printed_packlist_names_what_is_issued(self) -> None:
        self.tick(self.cable_line, 4)
        self.tick(self.rack_line, 1)
        packlist = services.get_packlist(self.project)
        services.issue(packlist, only_packed=True)
        printed = render_packlist_html(services.build_overview(packlist))
        self.assertIn("4 von 6 ausgegeben", printed)
        self.assertIn('<span class="tag">ausgegeben</span>', printed)

    def test_one_of_two_packlists_issued(self) -> None:
        truck = services.create_packlist(self.project, title="LKW 2")
        services.assign_lines(truck, [self.rack_line.pk])
        truck_url = reverse("packing:packlist_detail", args=[self.project.pk, truck.pk])
        self.htmx(
            "post",
            truck_url + "row/",
            {"mode": "pack", "line": self.rack_line.pk, "product": self.rack.pk, "quantity": "1"},
        )
        response = self.client.post(truck_url + "issue/", {"only_packed": "1"}, follow=True)
        self.assertIn(
            "Das Material dieser Packliste ist ausgegeben. Das Projekt geht auf „Unterwegs“, sobald alles ausgegeben ist.",
            self.messages_of(response),
        )
        self.assertIn(
            "Das Projekt bleibt „Bestätigt“, bis auch das Material seiner anderen Packlisten ausgegeben ist.",
            self.assert_ok(response),
        )


class StartPageTests(UiTestCase):
    """UIX-003, PCK-025: a project whose material is partly out is out at the moment."""

    def setUp(self) -> None:
        super().setUp()
        self.cables = make_stock("K-005", 10, "XLR-Kabel")
        self.project = make_project("Firmenfeier", start=at(1, 6), end=at(1, 20))
        line = add_line(self.project, self.cables, 6).line
        packlist = services.get_packlist(self.project)
        services.set_packed(packlist, line.pk, self.cables.pk, 2)
        services.issue(packlist, only_packed=True)

    def section(self, page: str, title: str) -> str:
        start = page.index(f"<h2>{title}</h2>")
        end = page.find("</section>", start)
        return page[start:end]

    def test_partly_out_is_out_and_expected_back(self) -> None:
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, ProjectStatus.CONFIRMED)
        page = self.assert_ok(self.client.get(reverse("core:home")))
        out = self.section(page, "Gerade unterwegs")
        self.assertIn("Firmenfeier", out)
        self.assertIn('<span class="badge yellow">teilweise ausgegeben</span>', out)
        self.assertIn("Firmenfeier", self.section(page, "Heute zurückerwartet"))
        self.assertNotIn("Firmenfeier", self.section(page, "Steht an"))
        # Something is still to pack: the warehouse sees it there as well.
        self.assertIn("Firmenfeier", self.section(page, "Heute und morgen zu packen"))
