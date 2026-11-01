# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages: products changed after the lines took them over (PRJ-072, PRJ-137, PRJ-138, PRJ-139)."""

from __future__ import annotations

from decimal import Decimal

from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.notifications.models import Kind, Notification
from rentalars.projects.models import ProjectStatus
from rentalars.projects.services import update_line
from tests.helpers import ALL_RIGHTS, add_line, make_product, make_project, make_user
from tests.ui.base import UiTestCase, form_data, forms_of

D = Decimal


class ProductChangePagesBase(UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        from tests.unit.test_051_lines import flat

        self.project = make_project(status=ProjectStatus.INQUIRY)
        self.lamp = flat("L-010", "20.00", name="Lampe")
        self.line = add_line(self.project, self.lamp, 4).line
        self.lamp.name = "Lampe LED"
        self.lamp.price = D("25.00")
        self.lamp.save()
        self.detail = reverse("projects:detail", args=[self.project.pk])
        self.update = reverse("projects:changes_update", args=[self.project.pk])

    def notes(self, page: str) -> str:
        start = page.index('id="planning-notes"')
        return page[start : page.index('id="group-', start)]


class PlanningTests(ProductChangePagesBase):
    def test_the_planning_lists_old_and_new_values(self) -> None:
        notes = self.notes(self.assert_ok(self.client.get(self.detail)))
        self.assertIn("1 Position weicht von ihrem Produkt ab", notes)
        self.assertIn("Lampe LED", notes)
        self.assertIn("20,00", notes)
        self.assertIn("25,00", notes)
        self.assertIn("Änderungen übernehmen", notes)

    def test_taking_over_refreshes_the_whole_planning_in_place(self) -> None:
        response = self.htmx("post", self.update, {"scope": "automatic"})
        text = self.assert_ok(response)
        self.assertEqual((response["HX-Retarget"], response["HX-Reswap"]), ("#planning", "outerHTML"))
        self.assertTrue(text.lstrip().startswith('<div id="planning"'))
        self.assertNotIn("weicht von ihrem Produkt ab", text)
        self.assertIn("1 Position hat jetzt die aktuellen Werte ihres Produkts.", text)
        self.line.refresh_from_db()
        self.assertEqual((self.line.title, self.line.unit_price), ("Lampe LED", D("25.00")))

    def test_a_value_set_by_hand_is_kept_line_by_line(self) -> None:
        update_line(self.line, rights=ALL_RIGHTS, title="Lampe für die Bühne")
        notes = self.notes(self.assert_ok(self.client.get(self.detail)))
        self.assertIn("von Hand gesetzt", notes)
        self.assertIn("Eigene Werte behalten", notes)
        keep = next(form for form in forms_of(self.client.get(self.detail)) if "keep" in form.data)
        response = self.htmx("post", keep.target, keep.data)
        self.assertIn("1 Position behält ihre eigenen Werte.", self.assert_ok(response))
        self.line.refresh_from_db()
        self.assertEqual((self.line.title, self.line.unit_price), ("Lampe für die Bühne", D("20.00")))
        self.assertEqual(self.line.list_price, D("25.00"))
        self.assertNotIn("weicht von ihrem Produkt ab", self.notes(self.assert_ok(self.client.get(self.detail))))

    def test_confirmed_with_details_open_shows_the_changes_too(self) -> None:
        """PRJ-072: "Bestätigt – Einzelheiten offen" is not fully confirmed."""
        self.project.status = ProjectStatus.CONFIRMED_OPEN
        self.project.save()
        page = self.assert_ok(self.client.get(self.detail))
        self.assertIn("Bestätigt – Preise und Einzelheiten offen", page)
        self.assertIn("1 Position weicht von ihrem Produkt ab", self.notes(page))

    def test_confirmed_projects_show_nothing(self) -> None:
        self.project.status = ProjectStatus.CONFIRMED
        self.project.save()
        page = self.assert_ok(self.client.get(self.detail))
        self.assertNotIn("weicht von ihrem Produkt ab", page)
        self.assertNotIn("weichen von ihren Produkten ab", page)

    def test_without_the_price_right_the_texts_show_and_the_prices_do_not(self) -> None:
        Role.objects.create(name="Planung ohne Preise", module_levels={"projects": 2, "products": 1})
        planner = self.browser_of(make_user("paula", roles=("Planung ohne Preise",)))
        notes = self.notes(self.assert_ok(planner.get(self.detail)))
        self.assertIn("Lampe LED", notes)
        self.assertNotIn("25,00", notes)
        self.assertNotIn("20,00", notes)
        self.assertEqual(self.htmx("post", self.update, {"scope": "automatic"}, client=planner).status_code, 200)
        self.line.refresh_from_db()
        self.assertEqual((self.line.title, self.line.unit_price), ("Lampe LED", D("20.00")))  # the price waits

    def test_a_reader_may_not_take_over(self) -> None:
        reader = self.browser_for("luka", "Lager")
        self.assertEqual(reader.post(self.update, {"scope": "automatic"}).status_code, 403)


class StaleTabTests(ProductChangePagesBase):
    def test_a_page_opened_before_the_project_was_confirmed_changes_nothing_afterwards(self) -> None:
        self.project.status = ProjectStatus.CONFIRMED
        self.project.save()
        response = self.htmx("post", self.update, {"scope": "automatic"})
        self.assertIn("Dieses Projekt ist bestätigt", self.assert_ok(response))
        self.line.refresh_from_db()
        self.assertEqual((self.line.title, self.line.unit_price), ("Lampe", D("20.00")))


class HintOnEveryPageTests(ProductChangePagesBase):
    def test_the_overview_tab_says_so_and_links_to_the_planning(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:deployment", args=[self.project.pk])))
        self.assertIn("1 Position weicht von ihrem Produkt ab", page)
        self.assertIn(f"{self.detail}#product-changes", page)

    def test_opening_a_project_lands_on_the_hint(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:overview", args=[self.project.pk]), follow=True))
        self.assertIn("weicht von ihrem Produkt ab", page)

    def test_the_planning_has_its_list_and_not_the_short_hint(self) -> None:
        page = self.assert_ok(self.client.get(self.detail))
        self.assertNotIn("data-product-change-hint", page)
        self.assertIn('id="product-changes"', page)

    def test_no_hint_without_changes_or_when_confirmed(self) -> None:
        other = make_project("Ruhig", status=ProjectStatus.INQUIRY)
        add_line(other, make_product("L-099", price="5.00"), 1)
        self.assertNotIn(
            "data-product-change-hint", self.assert_ok(self.client.get(reverse("projects:deployment", args=[other.pk])))
        )
        self.project.status = ProjectStatus.CONFIRMED
        self.project.save()
        page = self.assert_ok(self.client.get(reverse("projects:deployment", args=[self.project.pk])))
        self.assertNotIn("data-product-change-hint", page)


class ProductPageTests(ProductChangePagesBase):
    def setUp(self) -> None:
        super().setUp()
        self.page = reverse("products:detail", args=[self.lamp.pk])
        self.second = make_project("Zweites", status=ProjectStatus.OPTION)
        self.second_line = add_line(self.second, self.lamp, 2).line  # planned after the change: current values
        self.take_over = reverse("products:take_over_changes", args=[self.lamp.pk])

    def test_the_panel_names_the_projects_that_are_behind(self) -> None:
        page = self.assert_ok(self.client.get(self.page))
        self.assertIn("Geplant in Projekten, die noch nicht vollständig bestätigt sind", page)
        panel = page[page.index('id="unconfirmed-changes"') :]
        panel = panel[: panel.index("</section>")]
        self.assertIn(self.project.name, panel)
        self.assertNotIn(self.second.name, panel)  # it took the current values over when it was planned
        self.assertIn("Lampe LED", panel)

    def test_no_panel_when_nothing_is_behind(self) -> None:
        self.client.post(self.take_over)
        self.assertNotIn(
            "Geplant in Projekten, die noch nicht vollständig bestätigt sind",
            self.assert_ok(self.client.get(self.page)),
        )

    def test_take_over_in_all_projects(self) -> None:
        third = make_project("Drittes", status=ProjectStatus.INQUIRY)
        third_line = add_line(third, self.lamp, 1).line
        self.lamp.price = D("30.00")
        self.lamp.save()
        response = self.client.post(self.take_over, follow=True)
        self.assertIn(
            "Positionen in 3 Projekten haben jetzt die aktuellen Werte dieses Produkts.", self.assert_ok(response)
        )
        for line in (self.line, self.second_line, third_line):
            line.refresh_from_db()
            self.assertEqual((line.title, line.unit_price), ("Lampe LED", D("30.00")))

    def test_take_over_in_one_project(self) -> None:
        third = make_project("Drittes", status=ProjectStatus.INQUIRY)
        third_line = add_line(third, self.lamp, 1).line
        self.lamp.name = "Lampe LED 2"
        self.lamp.save()
        self.client.post(self.take_over, {"project": third.pk})
        third_line.refresh_from_db()
        self.line.refresh_from_db()
        self.assertEqual((third_line.title, self.line.title), ("Lampe LED 2", "Lampe"))

    def test_lines_set_by_hand_stay(self) -> None:
        update_line(self.line, rights=ALL_RIGHTS, title="Lampe für die Bühne")
        response = self.client.post(self.take_over, follow=True)
        self.assertIn("Nichts zu übernehmen", self.assert_ok(response))
        self.line.refresh_from_db()
        self.assertEqual(self.line.title, "Lampe für die Bühne")

    def test_projects_the_user_may_not_read_are_not_named(self) -> None:
        Role.objects.create(name="Nur Produkte", module_levels={"products": 2})
        clerk = self.browser_of(make_user("petra", roles=("Nur Produkte",)))
        page = self.assert_ok(clerk.get(self.page))
        self.assertNotIn("Geplant in Projekten, die noch nicht vollständig bestätigt sind", page)
        self.assertNotIn(self.project.name, page)
        clerk.post(self.take_over)
        self.line.refresh_from_db()
        self.assertEqual(self.line.title, "Lampe")

    def test_a_project_known_only_by_its_overview_is_not_named(self) -> None:
        from rentalars.accounts.rights import ProjectScope
        from rentalars.projects.models import ProjectAccessLevel, ProjectMembership

        Role.objects.create(
            name="Crew mit Produkten",
            module_levels={"projects": 1, "products": 2},
            special_rights=["prices"],
            project_scope=ProjectScope.DEPLOYMENT,
        )
        crew = make_user("carla", roles=("Crew mit Produkten",))
        ProjectMembership.objects.create(project=self.project, user=crew, level=ProjectAccessLevel.READ)
        page = self.assert_ok(self.browser_of(crew).get(self.page))
        self.assertNotIn("Geplant in Projekten, die noch nicht vollständig bestätigt sind", page)
        self.assertNotIn("Lampe LED</strong>", page)

    def test_saving_a_product_warns_when_projects_are_behind(self) -> None:
        edit = reverse("products:edit", args=[self.lamp.pk])
        data = form_data(self.client.get(edit), "article_number", price="31.00")
        response = self.client.post(edit, data, follow=True)
        self.assert_ok(response)
        self.assertTrue(
            any(
                "2 noch nicht vollständig bestätigte Projekte haben Positionen" in message
                for message in self.messages_of(response)
            )
        )

    def test_saving_a_product_tells_the_project_manager(self) -> None:
        self.project.manager = make_user("manager")
        self.project.save()
        edit = reverse("products:edit", args=[self.lamp.pk])
        data = form_data(self.client.get(edit), "article_number", price="31.00")
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(edit, data)
        notice = Notification.objects.get(kind=Kind.PRODUCT_CHANGE, user=self.project.manager)
        self.assertEqual(notice.project, self.project)
        self.assertIn("Lampe LED", notice.title)
        # ... and the bell shows it with a link to the list in the planning.
        self.assertTrue(notice.url.endswith(f"{self.detail}#product-changes"))
