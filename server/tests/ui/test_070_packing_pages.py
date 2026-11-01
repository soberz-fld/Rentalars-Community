# SPDX-License-Identifier: GPL-3.0-or-later
"""Page tests, helper "packing".

PCK-028: "Packen/Ausgabe" and "Rücknahme" – the return is ticked, then
booked with "Rücknahme buchen", also while the rest is still packed and
issued. PCK-029: the bar of the packlist with its legend in words, also for
the parts of a whole project. PCK-030: the parts of a whole project as
sub-tabs of the packlist.
"""

from __future__ import annotations

import re

from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, ProjectScope
from rentalars.packing import services
from rentalars.packing.models import PacklistStatus
from rentalars.projects import services as project_services
from rentalars.projects.models import ProjectAccessLevel, ProjectMembership, ProjectStatus
from tests.helpers import (
    add_line,
    at,
    make_customer,
    make_item,
    make_model,
    make_product,
    make_project,
    make_stock,
    make_user,
)
from tests.ui.base import UiTestCase, forms_of


class PackingPageTestCase(UiTestCase):
    """Ten cables and a single rack on the packlist of a confirmed project."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest")
        self.cable = make_stock("K-005", 12, "XLR-Kabel")
        self.rack = make_product("T-500", "Funkrack")
        make_item(make_model("Funkrack 4 HE", self.rack), 500)
        self.cable_line = add_line(self.project, self.cable, 10).line
        self.rack_line = add_line(self.project, self.rack, 1).line
        self.packlist = services.get_packlist(self.project)
        self.url = reverse("packing:packlist", args=[self.project.pk])

    def tick(self, line: object, quantity: int, mode: str = "pack") -> str:
        return self.assert_ok(
            self.htmx(
                "post",
                reverse("packing:row", args=[self.project.pk]),
                {
                    "mode": mode,
                    "view_mode": mode,
                    "line": line.pk,
                    "product": line.product_id,
                    "quantity": str(quantity),
                },  # type: ignore[attr-defined]
            )
        )

    def issue(self) -> None:
        self.client.post(reverse("packing:action", args=[self.project.pk, "issue"]), {"only_packed": "1"})

    def row_of(self, page: str, article_number: str) -> str:
        rows = re.findall(r'<li class="pack-row.*?</li>', page, flags=re.S)
        return next(row for row in rows if f'<span class="artno">{article_number}</span>' in row)

    def pack_bar(self, page: str) -> str:
        return page[page.index('class="pack-bar') :]

    def legend(self, page: str) -> list[str]:
        block = re.search(r'<ul class="pack-legend[^"]*"[^>]*>(.*?)</ul>', page, flags=re.S)
        assert block is not None
        return [re.sub(r"<[^>]+>", "", item).strip() for item in re.findall(r"<li>(.*?)</li>", block.group(1))]


class PartialReturnPageTests(PackingPageTestCase):
    """PCK-028."""

    def test_the_two_views_of_a_partly_issued_packlist(self) -> None:
        self.tick(self.cable_line, 6)
        self.issue()
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn(">Packen/Ausgabe</a>", page)
        self.assertIn(">Rücknahme</a>", page)
        self.assertNotIn("Rest packen", page)
        page = self.assert_ok(self.client.get(self.url + "?mode=return"))
        bar = self.pack_bar(page)
        self.assertIn("Hake ab, was zurückgekommen ist.", bar)
        self.assertRegex(bar, r'<button class="btn" type="submit" aria-describedby="take-back-ready" disabled>')
        self.assertIn("Alles ist zurück", bar)
        self.assertIn("Ausgabe zurücknehmen", bar)

    def test_tick_book_and_issue_the_rest(self) -> None:
        self.tick(self.cable_line, 6)
        self.issue()
        page = self.tick(self.cable_line, 4, mode="return")
        row = self.row_of(page, "K-005")
        self.assertIn("4 von 6 zurück", row)
        self.assertIn("4 noch nicht gebucht", row)
        self.assertIn("4 abgehakte Stück kommen zurück.", self.pack_bar(page))
        self.assertNotIn("Ausgabe zurücknehmen", self.pack_bar(page))  # something is back already
        take_back = next(
            form for form in forms_of(self.client.get(self.url + "?mode=return")) if form.action.endswith("/take-back/")
        )
        response = self.client.post(take_back.action, {})
        self.assertRedirects(response, self.url + "?mode=return", fetch_redirect_response=False)
        page = self.assert_ok(self.client.get(self.url + "?mode=return"))
        self.assertIn("4 Stück sind zurückgenommen.", page)
        row = self.row_of(page, "K-005")
        self.assertIn("4 von 6 zurückgenommen", row)
        self.assertIn('min="4"', row)  # the tick does not go below what is taken back
        # Packing goes on: the 4 that came back are done, the other 4 still go out.
        row = self.row_of(self.assert_ok(self.client.get(self.url + "?mode=pack")), "K-005")
        self.assertIn("6 von 10 ausgegeben", row)
        self.assertIn('min="6"', row)
        self.tick(self.cable_line, 10)
        self.tick(self.rack_line, 1)
        self.issue()
        self.assertEqual(services.get_packlist(self.project).status, PacklistStatus.ISSUED)

    def test_booking_everything_completes_the_return(self) -> None:
        self.tick(self.cable_line, 10)
        self.tick(self.rack_line, 1)
        self.issue()
        self.htmx("post", reverse("packing:action", args=[self.project.pk, "return-all"]), {"view_mode": "return"})
        response = self.client.post(reverse("packing:action", args=[self.project.pk, "take-back"]), follow=True)
        self.assertIn("Alles ist zurück. Die Rücknahme ist abgeschlossen.", self.messages_of(response))
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, ProjectStatus.RETURNED)
        page = self.assert_ok(response)
        self.assertIn("is-taken-back", self.row_of(page, "K-005"))

    def test_completing_by_hand_is_offered_below_the_rows(self) -> None:
        self.tick(self.cable_line, 10)
        self.issue()
        page = self.assert_ok(self.client.get(self.url + "?mode=return"))
        self.assertNotIn("complete-return/", self.pack_bar(page))
        self.assertIn("Kläre fehlende Teile an ihrer Zeile und schließ dann die Rücknahme ab.", page)
        self.assertIn("complete-return/", page)

    def test_nothing_ticked_is_explained(self) -> None:
        self.tick(self.cable_line, 10)
        self.issue()
        response = self.client.post(reverse("packing:action", args=[self.project.pk, "take-back"]), follow=True)
        self.assertIn(
            "Es ist nichts als zurück abgehakt, was noch nicht gebucht ist. Hake ab, was zurückgekommen ist.",
            self.messages_of(response),
        )


class BarPageTests(PackingPageTestCase):
    """PCK-029: the bar and its legend in words and numbers."""

    def test_legend(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        self.assertEqual(self.legend(page), ["11 im Lager"])
        self.tick(self.cable_line, 8)
        self.issue()
        self.tick(self.cable_line, 9)
        self.tick(self.cable_line, 5, mode="return")
        services.take_back(services.get_packlist(self.project))
        page = self.tick(self.cable_line, 7, mode="return")
        self.assertEqual(
            self.legend(page),
            ["5 zurückgenommen", "2 zurück abgehakt", "1 ausgegeben", "1 gepackt", "2 im Lager"],
        )
        self.assertRegex(
            page, r'<div class="pack-progress" aria-hidden="true"><span class="is-back" style="width: 45\.45%">'
        )
        self.assertIn('aria-label="Wo die Stücke sind"', page)
        self.assertNotIn('role="progressbar"', page)


class FamilyTabsPageTests(UiTestCase):
    """PCK-030: a whole project with its parts – the parts as sub-tabs of every packlist of the family."""

    def setUp(self) -> None:
        super().setUp()
        self.whole = make_project("Stadtfest", start=at(9, 12), end=at(14, 18), customer=make_customer("Stadt"))
        self.market = project_services.create_subproject(
            self.whole, name="Bühne Marktplatz", start=at(10, 8), end=at(12, 8)
        )
        self.park = project_services.create_subproject(
            self.whole, name="Bühne Schlosspark", start=at(12, 12), end=at(14, 12)
        )
        add_line(self.market, make_stock("K-005", 20, "XLR-Kabel"), 10)
        self.urls = {
            project.pk: reverse("packing:packlist", args=[project.pk])
            for project in (self.whole, self.market, self.park)
        }
        self.family_url = reverse("packing:family", args=[self.whole.pk])

    def tabs(self, page: str) -> list[tuple[str, str, bool]]:
        nav = re.search(r'<nav class="tabs sub no-print pack-tabs"[^>]*>(.*?)</nav>', page, flags=re.S)
        assert nav is not None
        return [
            (href, re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip(), "aria-current" in rest)
            for href, rest, text in re.findall(r'<a href="([^"]+)"([^>]*)>(.*?)</a>', nav.group(1), flags=re.S)
        ]

    def test_every_packlist_of_the_family_names_all_parts(self) -> None:
        page = self.assert_ok(self.client.get(self.urls[self.market.pk]))
        self.assertEqual(
            [(href, current) for href, _label, current in self.tabs(page)],
            [
                (self.urls[self.whole.pk], False),
                (self.urls[self.market.pk], True),
                (self.urls[self.park.pk], False),
                (self.family_url, False),
            ],
        )
        labels = [label for _href, label, _current in self.tabs(page)]
        self.assertEqual(labels[:3], ["Stadtfest", "Bühne Marktplatz offen", "Bühne Schlosspark"])
        self.assertEqual(labels[3], "Alle zusammen")
        self.assertIn('aria-label="Packlisten des Gesamtprojekts und seiner Teile"', page)
        family = self.assert_ok(self.client.get(self.family_url))
        self.assertEqual([current for _href, _label, current in self.tabs(family)], [False, False, False, True])
        # The address of the packlist of the whole project stays as it was.
        self.assertEqual(self.family_url, f"/projects/{self.whole.number}/packlist/family/")

    def test_several_packlists_of_the_part_have_a_tab_each(self) -> None:
        truck = services.create_packlist(self.market, title="LKW 2")
        page = self.assert_ok(self.client.get(self.urls[self.market.pk]))
        labels = [label for _href, label, _current in self.tabs(page)]
        self.assertIn("Bühne Marktplatz: Packliste offen", labels)
        self.assertIn("Bühne Marktplatz: LKW 2 offen", labels)
        self.assertIn(reverse("packing:packlist_detail", args=[self.market.pk, truck.pk]), page)

    def test_parts_the_user_may_not_see_are_left_out(self) -> None:
        Role.objects.create(
            name="Bühnenleitung extern",
            module_levels={Module.PROJECTS: int(Level.READ), Module.PACKING: int(Level.READ)},
            project_scope=ProjectScope.ASSIGNED,
        )
        external = make_user("erik", roles=("Bühnenleitung extern",))
        ProjectMembership.objects.create(project=self.whole, user=external, level=ProjectAccessLevel.READ)
        ProjectMembership.objects.create(project=self.park, user=external, level=ProjectAccessLevel.NONE)
        page = self.assert_ok(self.browser_of(external).get(self.urls[self.market.pk]))
        hrefs = [href for href, _label, _current in self.tabs(page)]
        self.assertEqual(hrefs, [self.urls[self.whole.pk], self.urls[self.market.pk], self.family_url])

    def test_a_project_on_its_own_keeps_its_tabs(self) -> None:
        alone = make_project("Firmenfeier")
        page = self.assert_ok(self.client.get(reverse("packing:packlist", args=[alone.pk])))
        self.assertIn('aria-label="Packlisten"', page)
        self.assertNotIn("Alle zusammen", page)

    def test_the_family_shows_the_bar_of_every_part(self) -> None:
        page = self.assert_ok(self.client.get(self.family_url))
        self.assertIn('<div class="pack-progress is-small" aria-hidden="true">', page)
        self.assertNotIn("<progress", page)
