# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages of whole projects and their parts (PRJ-044 to PRJ-049, PRJ-060)."""

from __future__ import annotations

from decimal import Decimal

from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, ProjectScope
from rentalars.projects import services
from rentalars.projects.models import MaterialLine, Project, ProjectAccessLevel, ProjectMembership, ProjectStatus
from tests.helpers import ALL_RIGHTS, add_line, at, make_customer, make_project, make_stock, make_user
from tests.ui.base import UiTestCase, form_data


class SubprojectPagesTestCase(UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.customer = make_customer("Stadt Musterstadt")
        self.whole = make_project("Stadtfest", start=at(9, 12), end=at(14, 18), customer=self.customer)
        self.market = services.create_subproject(self.whole, name="Bühne Marktplatz", start=at(10, 8), end=at(12, 8))


class AddingSubprojectsTests(SubprojectPagesTestCase):
    def test_add_a_part_through_the_form(self) -> None:
        detail = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.whole.pk])))
        url = reverse("projects:subproject_create", args=[self.whole.pk])
        self.assertIn(url, detail)
        page = self.client.get(url)
        text = self.assert_ok(page)
        self.assertIn("Neues Teilprojekt", text)
        self.assertIn("Stadt Musterstadt", text)
        self.assertNotIn('name="customer"', text)
        data = form_data(page, containing="start", name="Bühne Schlosspark")
        data.update(start="2027-03-12T12:00", end="2027-03-14T12:00")
        response = self.client.post(url, data)
        part = Project.objects.get(name="Bühne Schlosspark")
        self.assertRedirects(response, reverse("projects:detail", args=[part.pk]), fetch_redirect_response=False)
        self.assertEqual(
            (part.parent, part.customer, part.number), (self.whole, self.customer, f"{self.whole.number}-2")
        )

    def test_a_period_outside_the_whole_project_is_refused_in_the_form(self) -> None:
        url = reverse("projects:subproject_create", args=[self.whole.pk])
        data = form_data(self.client.get(url), containing="start", name="Zu früh")
        data.update(start="2027-03-01T12:00", end="2027-03-02T12:00")
        text = self.assert_ok(self.client.post(url, data))
        self.assertIn("innerhalb des Mietzeitraums", text)
        self.assertFalse(Project.objects.filter(name="Zu früh").exists())

    def test_a_part_has_no_parts(self) -> None:
        self.assertEqual(self.client.get(reverse("projects:subproject_create", args=[self.market.pk])).status_code, 404)

    def test_editing_a_part_keeps_the_customer(self) -> None:
        url = reverse("projects:edit", args=[self.market.pk])
        page = self.client.get(url)
        self.assertNotIn('name="customer"', self.assert_ok(page))
        data = form_data(page, containing="start", name="Marktplatz")
        self.client.post(url, data)
        self.market.refresh_from_db()
        self.assertEqual((self.market.name, self.market.customer), ("Marktplatz", self.customer))


class FamilyPagesTests(SubprojectPagesTestCase):
    def test_the_overview_with_the_parts_and_their_sum(self) -> None:
        spot = make_stock("L-100", 4, "Spot")
        add_line(self.market, spot, 6)
        page = self.assert_ok(self.client.get(reverse("projects:family", args=[self.market.pk])))
        self.assertIn("Gesamtprojekt", page)
        self.assertIn(self.market.number, page)
        self.assertIn("Gesamtprojekt mit allen Teilen", page)
        self.assertIn("Fehlmenge 2", page)
        # The planning of both shows the strip with the whole project and its parts, and the tab.
        planning = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.whole.pk])))
        self.assertIn('class="family-strip', planning)
        self.assertIn(reverse("projects:family", args=[self.whole.pk]), planning)
        part = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.market.pk])))
        self.assertIn("Teilprojekt", part)

    def test_the_project_list_shows_the_hierarchy(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:list")))
        self.assertIn("1 Teilprojekt", page)
        self.assertIn(f"Teil von {self.whole.number} Stadtfest", page)

    def test_status_for_the_whole_and_its_parts(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.whole.pk])))
        self.assertIn('name="with_parts"', page)
        self.client.post(
            reverse("projects:set_status", args=[self.whole.pk]), {"status": ProjectStatus.OUT, "with_parts": "1"}
        )
        self.market.refresh_from_db()
        self.assertEqual(self.market.status, ProjectStatus.OUT)


class TakeoverPagesTests(SubprojectPagesTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.park = services.create_subproject(self.whole, name="Bühne Schlosspark", start=at(12, 12), end=at(14, 12))
        self.spot = make_stock("L-100", 6, "Spot")
        self.source = add_line(self.market, self.spot, 6).line

    def test_take_over_through_the_dialog(self) -> None:
        url = reverse("projects:takeover", args=[self.park.pk])
        planning = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.park.pk])))
        self.assertIn(url, planning)
        dialog = self.assert_ok(self.htmx("get", url))
        self.assertIn("Spot", dialog)
        response = self.htmx("post", url, {"source": self.source.pk, "quantity": "4"})
        self.assertEqual(response.status_code, 200)
        line = MaterialLine.objects.get(project=self.park)
        self.assertEqual((line.taken_over_from, line.quantity), (self.source, Decimal("4")))
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.park.pk])))
        self.assertIn("übernommen", page)
        self.assertIn("nicht berechnet", page)
        source_page = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.market.pk])))
        self.assertIn(f"4 gehen weiter an {self.park.number}", source_page)

    def test_the_line_dialog_offers_the_source(self) -> None:
        line = add_line(self.park, self.spot, 2).line
        url = reverse("projects:line_edit", args=[self.park.pk, line.pk])
        dialog = self.htmx("get", url)
        self.assertIn('name="taken_over_from"', self.assert_ok(dialog))
        data = form_data(dialog, containing="taken_over_from")
        data["taken_over_from"] = str(self.source.pk)
        self.htmx("post", url, data)
        line.refresh_from_db()
        self.assertEqual(line.taken_over_from, self.source)

    def test_too_many_pieces_are_refused(self) -> None:
        services.take_over_line(self.source, self.park, rights=ALL_RIGHTS, quantity=6)
        url = reverse("projects:takeover", args=[self.park.pk])
        dialog = self.assert_ok(self.htmx("get", url))
        self.assertIn("nichts zu übernehmen", dialog)
        response = self.htmx("post", url, {"source": self.source.pk, "quantity": "1"})
        self.assertEqual(response.status_code, 404)


class MembersOfPartsTests(SubprojectPagesTestCase):
    def test_no_access_is_offered_on_parts_only(self) -> None:
        whole = self.assert_ok(self.client.get(reverse("projects:members", args=[self.whole.pk])))
        self.assertNotIn('value="none"', whole)
        Role.objects.create(
            name="Bühnenleitung extern",
            module_levels={Module.PROJECTS: int(Level.WRITE)},
            project_scope=ProjectScope.ASSIGNED,
        )
        erik = make_user("erik", roles=("Bühnenleitung extern",))
        ProjectMembership.objects.create(project=self.whole, user=erik, level=ProjectAccessLevel.EDIT)
        page = self.client.get(reverse("projects:members", args=[self.market.pk]))
        text = self.assert_ok(page)
        self.assertIn('value="none"', text)
        # AUT-035: one list of everybody with access; the reason names the whole project.
        self.assertIn(f"Mitglied des Gesamtprojekts {self.whole.number}: bearbeiten", text)
        self.assertIn("erik", text)
        data = form_data(page, containing="level", user=str(erik.pk), level="none")
        self.client.post(reverse("projects:members", args=[self.market.pk]), data)
        self.assertEqual(self.browser_of(erik).get(reverse("projects:detail", args=[self.market.pk])).status_code, 404)
        self.assertEqual(self.browser_of(erik).get(reverse("projects:detail", args=[self.whole.pk])).status_code, 200)


class OtherProjectsAreUntouchedTests(UiTestCase):
    def test_a_plain_project_shows_no_family(self) -> None:
        project = make_project()
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[project.pk])))
        self.assertNotIn("family-strip", page)
        self.assertNotIn(reverse("projects:family", args=[project.pk]), page)
        self.assertNotIn(reverse("projects:takeover", args=[project.pk]), page)
        self.assertIn(reverse("projects:subproject_create", args=[project.pk]), page)
