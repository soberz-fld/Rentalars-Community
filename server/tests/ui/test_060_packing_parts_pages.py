# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser tests: packlists of subprojects, the packlist of the whole project, handovers (PRJ-048, PRJ-060)."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, ProjectScope
from rentalars.packing.models import Handover, PackEntry, PacklistStatus
from rentalars.packing.services import get_packlist, issue
from rentalars.projects import services
from rentalars.projects.models import Project, ProjectAccessLevel, ProjectMembership, ProjectStatus
from tests.helpers import ALL_RIGHTS, add_line, at, make_customer, make_project, make_stock, make_user
from tests.ui.base import UiTestCase, forms_of


class PartsPacklistPageTestCase(UiTestCase):
    """A festival with two stages; the six spots of the first go on to the second."""

    def setUp(self) -> None:
        super().setUp()
        self.whole = make_project("Stadtfest", start=at(9, 12), end=at(14, 18), customer=make_customer("Stadt"))
        self.market = services.create_subproject(self.whole, name="Bühne Marktplatz", start=at(10, 8), end=at(12, 8))
        self.park = services.create_subproject(self.whole, name="Bühne Schlosspark", start=at(12, 12), end=at(14, 12))
        self.spot = make_stock("L-100", 6, "Spot")
        self.cable = make_stock("K-005", 20, "XLR-Kabel 5 m")
        self.power = make_stock("S-100", 1, "Stromverteiler")
        add_line(self.whole, self.power, 1)
        self.source = add_line(self.market, self.spot, 6).line
        add_line(self.market, self.cable, 10)
        self.taking = services.take_over_line(self.source, self.park, rights=ALL_RIGHTS).line
        add_line(self.park, self.cable, 4)
        self.market_url = reverse("packing:packlist", args=[self.market.pk])
        self.park_url = reverse("packing:packlist", args=[self.park.pk])
        self.family_url = reverse("packing:family", args=[self.whole.pk])

    def handover_form(self, page: Any) -> Any:
        """The form that books the handover on the Schlosspark's packlist."""
        return next(form for form in forms_of(page) if form.target.endswith("/handover/"))

    def book(self, quantity: str | None = None, client: Any = None) -> str:
        """Book the arrival of spots the way the packlist page does."""
        form = self.handover_form(self.client.get(self.park_url))
        data = dict(form.data)
        if quantity is not None:
            data["quantity"] = quantity
        return self.assert_ok(self.htmx("post", form.target, data, client=client))


class TakeoverOnThePacklistTests(PartsPacklistPageTestCase):
    """PRJ-060: both packlists show the pieces; the later one books their arrival."""

    def test_both_pages_name_the_other_stage(self) -> None:
        market = self.assert_ok(self.client.get(self.market_url))
        self.assertIn(f"6 gehen weiter an {self.park.number} Bühne Schlosspark", market)
        park = self.assert_ok(self.client.get(self.park_url))
        self.assertIn(f"Übernahme aus {self.market.number} Bühne Marktplatz", park)
        self.assertIn("nicht aus dem Lager", park)
        # Only the cables are packed in the warehouse.
        self.assertIn("0 von 4 Stück sind gepackt", park)
        self.assertIn("6 Stück kommen aus anderen Teilprojekten", park)
        self.assertIn("Übergabe buchen", park)

    def test_booking_partly_and_the_rest(self) -> None:
        issue(get_packlist(self.market))
        page = self.book("4")
        self.assertIn("4 von 6 übergeben", page)
        self.assertIn("4 × L-100 aus", page)
        page = self.book()
        self.assertIn(f"2 aus {self.market.number} angekommen", page)
        self.assertEqual(PackEntry.objects.get(line=self.source).handed_over_quantity, 6)
        # PCK-025: the cables of the Schlosspark are still in the warehouse – the stage keeps its status.
        self.assertEqual(Project.objects.get(pk=self.park.pk).status, ProjectStatus.CONFIRMED_OPEN)
        self.assertIn("bis alles ausgegeben ist", page)
        market = self.assert_ok(self.client.get(self.market_url))
        self.assertIn("6 übergeben", market)

    def test_taking_back_a_booking(self) -> None:
        issue(get_packlist(self.market))
        page = self.book()
        undo = next(
            form for form in forms_of(self.client.get(self.park_url)) if form.target.endswith("/undo-handover/")
        )
        page = self.assert_ok(self.htmx("post", undo.target, undo.data))
        self.assertIn("Die Übergabe wurde zurückgenommen.", page)
        self.assertFalse(Handover.objects.exists())
        self.assertEqual(get_packlist(self.park).status, PacklistStatus.OPEN)

    def test_a_refused_booking_is_explained(self) -> None:
        page = self.book()
        self.assertIn("ist noch nicht ausgegeben", page)
        self.assertFalse(Handover.objects.exists())

    def test_whoever_works_only_on_the_later_stage_cannot_book(self) -> None:
        """PRJ-049: the handover changes the packlist of the earlier stage as well."""
        issue(get_packlist(self.market))
        Role.objects.create(
            name="Bühnencrew",
            module_levels={Module.PROJECTS: int(Level.READ), Module.PACKING: int(Level.WRITE)},
            project_scope=ProjectScope.ASSIGNED,
        )
        crew = make_user("bert", roles=("Bühnencrew",))
        ProjectMembership.objects.create(project=self.park, user=crew, level=ProjectAccessLevel.READ)
        page = self.book(client=self.browser_of(crew))
        self.assertIn("musst du auch die Packliste von", page)
        self.assertFalse(Handover.objects.exists())

    def test_the_earlier_stage_completes_its_return_after_the_handover(self) -> None:
        packlist = get_packlist(self.market)
        issue(packlist)
        action = reverse("packing:action", args=[self.market.pk, "return-all"])
        self.htmx("post", action, {"view_mode": "return"})
        refused = self.client.post(reverse("packing:action", args=[self.market.pk, "complete-return"]), follow=True)
        self.assertIn(f"warten noch auf ihre Übergabe an {self.park.number}", self.assert_ok(refused))
        self.book()
        done = self.client.post(reverse("packing:action", args=[self.market.pk, "complete-return"]), follow=True)
        self.assertIn("Die Rücknahme ist abgeschlossen.", self.assert_ok(done))
        self.assertEqual(Project.objects.get(pk=self.market.pk).status, ProjectStatus.RETURNED)


class FamilyPacklistPageTests(PartsPacklistPageTestCase):
    """PRJ-048: the whole project with all its parts, read-only, on screen and on paper."""

    def test_reached_from_every_part(self) -> None:
        for url in (self.market_url, self.park_url, reverse("packing:packlist", args=[self.whole.pk])):
            self.assertIn(f'href="{self.family_url}"', self.assert_ok(self.client.get(url)))
        response = self.client.get(reverse("packing:family", args=[self.park.pk]))
        self.assertRedirects(response, self.family_url)

    def test_part_by_part(self) -> None:
        issue(get_packlist(self.market))
        page = self.assert_ok(self.client.get(self.family_url + "?view=parts"))
        self.assertIn("Gesamtprojekt mit allen Teilprojekten", page)
        for text in ("Stromverteiler", "Bühne Marktplatz", "Bühne Schlosspark", "Nur zum Lesen"):
            self.assertIn(text, page)
        self.assertIn("16 / 16", page)  # the Marktplatz is issued completely
        self.assertIn("Übernahme: 0 von 6 angekommen", page)
        self.assertNotIn("hx-post", page)  # read-only

    def test_summed_up_by_article(self) -> None:
        page = self.assert_ok(self.client.get(self.family_url + "?view=articles"))
        self.assertIn("Nach Artikel zusammengefasst", page)
        self.assertIn(f"{self.market.number}: 10", page)
        self.assertIn(f'{self.park.number}: 6 <span class="muted">(übernommen)</span>', page)
        # The choice is remembered.
        self.assertIn("Aus dem Lager", self.assert_ok(self.client.get(self.family_url)))

    def test_a_hidden_part_is_left_out_and_counted(self) -> None:
        Role.objects.create(
            name="Bühnenleitung extern",
            module_levels={Module.PROJECTS: int(Level.READ), Module.PACKING: int(Level.READ)},
            project_scope=ProjectScope.ASSIGNED,
        )
        external = make_user("erik", roles=("Bühnenleitung extern",))
        ProjectMembership.objects.create(project=self.whole, user=external, level=ProjectAccessLevel.READ)
        ProjectMembership.objects.create(project=self.park, user=external, level=ProjectAccessLevel.NONE)
        page = self.assert_ok(self.browser_of(external).get(self.family_url))
        self.assertIn("1 Teilprojekt ist nicht enthalten", page)
        self.assertIn(reverse("packing:packlist", args=[self.market.pk]), page)
        self.assertNotIn(self.park_url, page)
        self.assertNotIn(f"<h2>{self.park.number} Bühne Schlosspark</h2>", page)

    def test_without_the_packlist_of_the_whole_project_there_is_no_way_in(self) -> None:
        Role.objects.create(
            name="Bühnenleitung extern",
            module_levels={Module.PROJECTS: int(Level.READ), Module.PACKING: int(Level.READ)},
            project_scope=ProjectScope.ASSIGNED,
        )
        external = make_user("erik", roles=("Bühnenleitung extern",))
        ProjectMembership.objects.create(project=self.park, user=external, level=ProjectAccessLevel.READ)
        browser = self.browser_of(external)
        self.assertNotIn(self.family_url, self.assert_ok(browser.get(self.park_url)))
        self.assertEqual(browser.get(self.family_url).status_code, 404)

    def test_printed(self) -> None:
        for view in ("parts", "articles"):
            response = self.client.get(reverse("packing:family_pdf", args=[self.whole.pk]) + f"?view={view}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "application/pdf")
            self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertIn(f"Packliste-{self.whole.number}-gesamt.pdf", response["Content-Disposition"])

    def test_a_project_without_parts_has_no_link(self) -> None:
        alone = make_project("Firmenfeier")
        page = self.assert_ok(self.client.get(reverse("packing:packlist", args=[alone.pk])))
        self.assertNotIn("Gesamtprojekt mit allen Teilprojekten", page)
