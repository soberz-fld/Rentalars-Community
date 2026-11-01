# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages of the wishes that are not mail, planning, imports, calendars, settings or lines.

* UIX-016, UIX-019, UIX-020 – logo and icon, the search on every page, pages that follow changes.
* UIX-021 – the dashboard shows every open shortage.
* UIX-022 – no "Back" on the sections of the planning.
* UIX-024 – readable addresses.
* AUT-026, AUT-027 – people are accounts; one-time password.
* PRJ-069, PRJ-070 – the project form: periods, customer and venue by typing, created in a dialog.
* PRJ-076 – project templates.
* MAT-047 – install an item from its own page.
"""

from __future__ import annotations

import json
import re

from django.urls import reverse

from rentalars.accounts.models import Role, User
from rentalars.customers.models import Customer, Venue
from rentalars.material.models import MaterialItem
from rentalars.personnel.models import Person
from rentalars.projects.models import Project, ProjectTemplate
from rentalars.projects.project_templates import save_as_template
from tests.helpers import (
    ALL_RIGHTS,
    add_line,
    at,
    make_customer,
    make_item,
    make_model,
    make_product,
    make_project,
    make_stock,
    make_user,
    plan,
)
from tests.ui.base import UiTestCase, form_data


class EveryPageTests(UiTestCase):
    def test_logo_icon_search_and_watching(self) -> None:
        """UIX-016, UIX-019, UIX-020: on every page."""
        page = self.assert_ok(self.client.get(reverse("projects:list")))
        self.assertIn('class="brand-logo"', page)
        self.assertIn('rel="icon"', page)
        self.assertIn('rel="apple-touch-icon"', page)
        self.assertIn('id="nav-search"', page)
        self.assertIn(f'action="{reverse("core:search")}"', page)
        self.assertIn('data-watch="notifications"', page)
        self.assertIn('id="changed-note"', page)

    def test_the_changes_of_a_project_page(self) -> None:
        """UIX-020: ``/changes/`` answers with the state of what the page shows."""
        project = make_project()
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[project.pk])))
        # UIX-010: the chat of the project as well, for the unread count of its tab.
        # Stock refresh: the planning page also watches the stock figures of its availability column.
        self.assertIn(f'data-watch="notifications,project:{project.pk},chat:{project.pk},stock:{project.pk}"', page)
        url = reverse("core:changes") + f"?keys=notifications,project:{project.pk}"
        before = self.client.get(url).json()
        add_line(project, make_stock("L-001", 2))
        after = self.client.get(url)
        self.assertEqual(after["Cache-Control"], "no-store")
        self.assertNotEqual(before["stamps"][f"project:{project.pk}"], after.json()["stamps"][f"project:{project.pk}"])
        self.assertEqual(after.json()["unread"], 0)

    def test_confirmations_are_dialogs_of_the_page(self) -> None:
        """UIX-018: the texts of the dialog are on the page for the script."""
        page = self.assert_ok(self.client.get(reverse("core:home")))
        self.assertIn('data-text-confirm="Ja, weiter"', page)
        self.assertIn('data-text-cancel="Abbrechen"', page)


class DashboardTests(UiTestCase):
    def test_every_open_shortage_is_shown(self) -> None:
        """UIX-021: also shortages of projects months ahead."""
        product = make_stock("L-001", 1, "Scheinwerfer")
        project = make_project("Herbstfest", start=at(10, 12, month=9), end=at(11, 12, month=9))
        add_line(project, product, 3)
        page = self.assert_ok(self.client.get(reverse("core:home")))
        self.assertIn("Offene Fehlbestände", page)
        self.assertIn("Herbstfest", page)


class BackButtonTests(UiTestCase):
    def test_no_back_on_the_planning(self) -> None:
        """UIX-022: the tabs of the planning are sections of their own."""
        self.client.get(reverse("projects:list"))
        for name in ("schedule:calendar", "schedule:timeline", "schedule:products", "schedule:personnel"):
            page = self.assert_ok(self.client.get(reverse(name)))
            self.assertNotIn('class="back-link', page, name)


class ReadableAddressPageTests(UiTestCase):
    def test_projects_and_products_by_number(self) -> None:
        """UIX-024: the number in the address; old links with the key still work."""
        project = make_project()
        product = make_product("L-010", "Profiler")
        list_page = self.assert_ok(self.client.get(reverse("projects:list")))
        # the list opens the project's Überblick; the Planung tab keeps the plain address – adapted.
        self.assertIn(f'href="/projects/{project.number}/overview/"', list_page)
        self.assert_ok(self.client.get(f"/projects/{project.number}/"))
        self.assert_ok(self.client.get(f"/projects/{project.pk}/"))
        self.assertIn("Profiler", self.assert_ok(self.client.get("/products/L-010/")))
        self.assertEqual(self.client.get("/projects/1999-0001/").status_code, 404)
        self.assertEqual(reverse("products:detail", args=[product.pk]), "/products/L-010/")

    def test_a_long_list_costs_no_query_per_address(self) -> None:
        """NFA-012: after a few lookups the numbers are read at once."""
        for number in range(30):
            make_project(f"Projekt {number}")
        self.client.get(reverse("projects:list"))
        with self.assertNumQueries(self.queries_of_the_list()):
            self.client.get(reverse("projects:list"))

    def queries_of_the_list(self) -> int:
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as captured:
            self.client.get(reverse("projects:list"))
        self.assertLess(len(captured), 30)
        return len(captured)


class PeopleAndAccountsPageTests(UiTestCase):
    def test_a_new_person_can_be_invited(self) -> None:
        """AUT-026: the person form creates the login too, and sends the invitation if asked."""
        from django.core import mail

        response = self.client.get(reverse("personnel:person_create"))
        self.assertNotIn('name="user"', self.assert_ok(response))
        data = form_data(response, "first_name", first_name="Paula", last_name="Neu", email="paula@example.de")
        data["invite"] = "on"
        self.client.post(reverse("personnel:person_create"), data)
        person = Person.objects.get(first_name="Paula")
        self.assertEqual(person.user.username, "paula.neu")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(
            "paula.neu", self.assert_ok(self.client.get(reverse("personnel:person_detail", args=[person.pk])))
        )

    def test_one_time_password(self) -> None:
        """AUT-027: shown once on the page of the user."""
        user = Person.objects.create(first_name="Otto", last_name="Ohne").user
        page = self.assert_ok(self.client.get(reverse("accounts:user_edit", args=[user.pk])))
        self.assertIn(reverse("accounts:user_one_time_password", args=[user.pk]), page)
        page = self.assert_ok(self.client.post(reverse("accounts:user_one_time_password", args=[user.pk])))
        user.refresh_from_db()
        self.assertTrue(user.must_change_password)
        self.assertIn("otto.ohne", page)
        self.assertEqual(self.client.get(reverse("accounts:user_one_time_password", args=[user.pk])).status_code, 405)


class ProjectFormTests(UiTestCase):
    def test_the_periods_are_named_by_what_they_decide(self) -> None:
        """PRJ-069: rental period and event, with an explanation."""
        page = self.assert_ok(self.client.get(reverse("projects:create")))
        self.assertIn("Mietzeitraum: Material ist außer Haus", page)
        self.assertIn("Veranstaltung – für die berechneten Miettage", page)
        self.assertIn("12 Uhr bis 12 Uhr", page)

    def test_customer_and_venue_are_typed(self) -> None:
        """PRJ-070: typing with suggestions instead of a long list."""
        page = self.assert_ok(self.client.get(reverse("projects:create")))
        self.assertIn(f'data-url="{reverse("customers:suggest")}"', page)
        self.assertIn(f'data-url="{reverse("customers:venue_suggest")}"', page)
        self.assertIn('type="hidden" name="customer"', page)

    def test_the_last_suggestion_creates_a_customer(self) -> None:
        """PRJ-070: "Create … as a new customer", for those who may."""
        make_customer("Stadtwerke Musterstadt")
        results = self.client.get(reverse("customers:suggest"), {"q": "Stadtw"}).json()
        self.assertEqual(results[0]["label"], "Stadtwerke Musterstadt")
        self.assertTrue(results[-1]["create"])
        self.assertIn("name=Stadtw", results[-1]["create_url"])
        Role.objects.create(name="Nur Projekte", module_levels={"projects": 1})
        reader = self.browser_for("reader", "Nur Projekte")
        results = reader.get(reverse("customers:suggest"), {"q": "Stadtw"}).json()
        self.assertEqual([result["label"] for result in results], ["Stadtwerke Musterstadt"])

    def test_a_customer_made_in_the_dialog(self) -> None:
        """PRJ-070: the dialog asks what the customer management asks, and tells the form the new customer."""
        url = reverse("customers:quick_create") + "?name=Neue%20Halle%20GmbH"
        page = self.assert_ok(self.htmx("get", url))
        self.assertIn('value="Neue Halle GmbH"', page)
        data = form_data(self.client.get(url), "name")
        response = self.htmx("post", url, data)
        self.assertEqual(response.status_code, 204)
        trigger = json.loads(response["HX-Trigger"])
        customer = Customer.objects.get(name="Neue Halle GmbH")
        self.assertEqual(trigger["objectCreated"], {"field": "customer", "id": customer.pk, "label": customer.name})
        # The dialog has no box "active"; the customer is active, ready for the project.
        self.assertTrue(customer.is_active)

    def test_a_venue_made_in_the_dialog(self) -> None:
        """PRJ-070: the same for the venue."""
        self.assertTrue(self.client.get(reverse("customers:venue_suggest"), {"q": "Halle"}).json()[-1]["create"])
        url = reverse("customers:venue_quick_create") + "?name=Stadthalle"
        data = form_data(self.client.get(url), "name", city="Musterstadt")
        response = self.htmx("post", url, data)
        self.assertEqual(response.status_code, 204)
        venue = Venue.objects.get(name="Stadthalle")
        self.assertEqual(json.loads(response["HX-Trigger"])["objectCreated"]["id"], venue.pk)
        self.assertEqual(self.client.get(reverse("customers:venue_suggest"), {"q": "Muster"}).json()[0]["id"], venue.pk)

    def test_a_new_project_starts_noon_to_noon(self) -> None:
        """PRJ-068: the form suggests 12:00 to 12:00 of the next day."""
        page = self.assert_ok(self.client.get(reverse("projects:create")))
        self.assertIn("T12:00", page)


class ProjectTemplatePageTests(UiTestCase):
    """PRJ-076, which carries out the project templates of PRJ-030."""

    def setUp(self) -> None:
        super().setUp()
        self.speaker = make_stock("T-001", 10, "Lautsprecher")
        self.source = make_project("Stadtfest", start=at(10, 12), end=at(11, 12))
        add_line(self.source, self.speaker, 4)
        plan(self.source, "Tontechnik")

    def test_save_a_project_as_template(self) -> None:
        """PRJ-076: in a dialog of the project page."""
        project_page = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.source.pk])))
        url = reverse("projects:template_create", args=[self.source.pk])
        self.assertIn(url, project_page)
        dialog = self.htmx("get", url)
        self.assertIn('value="Stadtfest"', self.assert_ok(dialog))
        page = self.assert_ok(self.htmx("post", url, form_data(dialog, "name", name="Fest klein")))
        self.assertIn("Die Vorlage „Fest klein“ ist gespeichert.", page)
        template = ProjectTemplate.objects.get()
        self.assertEqual((template.counts["lines"], template.counts["crew"]), (1, 1))
        again = self.assert_ok(self.htmx("post", url, form_data(dialog, "name", name="fest KLEIN")))
        self.assertIn("Eine Vorlage mit diesem Namen gibt es schon.", again)

    def test_a_new_project_from_a_template(self) -> None:
        """PRJ-076: chosen in the form for a new project; the content comes in when saving."""
        template = save_as_template(self.source, name="Fest klein", rights=ALL_RIGHTS)
        response = self.client.get(reverse("projects:create"))
        self.assertIn("Fest klein", self.assert_ok(response))
        data = form_data(
            response,
            "name",
            name="Weinfest",
            template=str(template.pk),
            customer=str(self.source.customer_id),
            start="2027-04-20T12:00",
            end="2027-04-21T12:00",
        )
        response = self.client.post(reverse("projects:create"), data)
        project = Project.objects.get(name="Weinfest")
        self.assertRedirects(response, reverse("projects:detail", args=[project.pk]), fetch_redirect_response=False)
        self.assertEqual(project.material_lines.get().quantity, 4)
        self.assertEqual(project.crew_lines.count(), 1)

    def test_manage_the_templates(self) -> None:
        """PRJ-076: list, rename, delete."""
        template = save_as_template(self.source, name="Fest klein", rights=ALL_RIGHTS)
        self.assertIn(reverse("projects:templates"), self.assert_ok(self.client.get(reverse("projects:list"))))
        page = self.assert_ok(self.client.get(reverse("projects:templates")))
        self.assertIn("Fest klein", page)
        self.assertIn(self.source.number, page)
        url = reverse("projects:template_edit", args=[template.pk])
        self.client.post(url, form_data(self.client.get(url), "name", name="Fest mittel"))
        template.refresh_from_db()
        self.assertEqual(template.name, "Fest mittel")
        self.client.post(reverse("projects:template_delete", args=[template.pk]))
        self.assertFalse(ProjectTemplate.objects.exists())


class InstallFromItemPageTests(UiTestCase):
    def test_install_an_item_from_its_page(self) -> None:
        """MAT-047: "Install in" on the page of the item, like "Add item" on the container."""
        rack = make_item(make_model("Rack", make_product("K-100", "Rack")), 500)
        amp = make_item(make_model("Endstufe", make_product("T-100", "Endstufe")), 501)
        page = self.assert_ok(self.client.get(reverse("material:item_detail", args=[amp.pk])))
        self.assertIn(reverse("material:item_install", args=[amp.pk]), page)
        self.assertLess(page.index("Status"), page.index("Einbauen in"))
        self.client.post(
            reverse("material:item_install", args=[amp.pk]),
            {"container_number": rack.display_id, "connection_type": "loose"},
        )
        self.assertEqual(MaterialItem.objects.get(pk=amp.pk).installed_in_id, rack.pk)
        response = self.client.post(
            reverse("material:item_install", args=[amp.pk]), {"container_number": "99999", "connection_type": "loose"}
        )
        self.assertIn("99999", " ".join(self.messages_of(self.client.get(response["Location"]))))

    def test_label_pdf_in_a_new_tab(self) -> None:
        """MAT-047: the labels open in a tab of their own."""
        model = make_model("Rack", make_product("K-100", "Rack"))
        item = make_item(model, 500)
        options = {"items": item.display_id, "label_format": "a4-24", "code": "qr", "skip": "0"}
        page = self.assert_ok(self.client.get(reverse("material:labels"), options))
        self.assertIn('formtarget="_blank"', page)


class UsersWithoutAddressTests(UiTestCase):
    def test_a_user_without_address(self) -> None:
        """AUT-026: an account may have no e-mail address; it then gets a one-time password."""
        response = self.client.get(reverse("accounts:user_create"))
        data = form_data(response, "username", username="lager", first_name="Lager", last_name="Konto", email="")
        self.client.post(reverse("accounts:user_create"), data)
        user = User.objects.get(username="lager")
        self.assertIsNone(user.email)
        self.assertTrue(Person.objects.filter(user=user).exists())


class SmallerWishesPageTests(UiTestCase):
    def test_position_in_the_company(self) -> None:
        """PER-024: in the form, on the person's page and in the API."""
        url = reverse("personnel:person_create")
        self.client.post(
            url, form_data(self.client.get(url), first_name="Lea", last_name="Licht", position="Leitung Licht")
        )
        person = Person.objects.get(first_name="Lea")
        self.assertEqual(person.position, "Leitung Licht")
        page = self.assert_ok(self.client.get(reverse("personnel:person_detail", args=[person.pk])))
        self.assertIn("Leitung Licht", page)

    def test_cleaning_is_the_last_phase(self) -> None:
        """PRJ-071: the phase "Reinigung" ends the course – followed only by "Sonstiges" (PRJ-092)."""
        from rentalars.projects.models import PhaseKind

        self.assertEqual(PhaseKind.choices[-2:], [("cleaning", "Reinigung"), ("other", "Sonstiges")])
        project = make_project()
        page = self.assert_ok(self.client.get(reverse("projects:phase_create", args=[project.pk])))
        options = page[page.index('name="kind"') :]
        options = options[: options.index("</select>")]
        self.assertEqual(re.findall(r'<option value="(\w+)"', options)[-2:], ["cleaning", "other"], options[-200:])

    def test_documents_come_right_after_the_prices(self) -> None:
        """PRJ-074: the tab "Dokumente" follows "Preisübersicht"."""
        project = make_project()
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[project.pk])))
        tabs = page[page.index('class="tabs') :]
        self.assertLess(tabs.index("Preisübersicht"), tabs.index("Dokumente"))
        # PRJ-080: "Zeitplanung".
        self.assertLess(tabs.index("Dokumente"), tabs.index("Zeitplanung"))

    def test_the_offer_is_a_document(self) -> None:
        """DOK-002 by DOK-010: the offer is the first kind of document a project can make."""
        project = make_project()
        page = self.assert_ok(self.client.get(reverse("documents:list", args=[project.pk])))
        kinds = page[page.index('name="kind"') :]
        self.assertIn('value="offer"', kinds[: kinds.index("</select>")].split("<option")[1])

    def test_own_deployments_as_a_calendar(self) -> None:
        """PER-017 by PER-023: the own deployments as.ics file, from "My area → Availability"."""
        crew = make_user("carla", roles=("Crew",))
        browser = self.browser_of(crew)
        project = make_project("Stadtfest")
        plan(project, "Stagehand", crew.person, start=at(10, 8), end=at(10, 14))
        page = self.assert_ok(browser.get(reverse("personnel:own_availability")))
        self.assertIn(reverse("personnel:own_deployments_ics"), page)
        response = browser.get(reverse("personnel:own_deployments_ics"))
        self.assertEqual(response["Content-Type"].split(";")[0], "text/calendar")
        self.assertIn("Stadtfest", response.content.decode())

    def test_an_invitation_needs_an_address(self) -> None:
        """AUT-027: without an e-mail address the form says to use a one-time password."""
        url = reverse("personnel:person_create")
        data = form_data(self.client.get(url), first_name="Ohne", last_name="Adresse")
        data["invite"] = "on"
        response = self.client.post(url, data, follow=True)
        self.assertIn("keine Einladung gesendet", " ".join(self.messages_of(response)))
