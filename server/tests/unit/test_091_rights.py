# SPDX-License-Identifier: GPL-3.0-or-later
"""Rights and roles – the role "Crew" (AUT-031), availability as a special right (AUT-032), working on service
cases (AUT-033), data access (AUT-034).

The requirements:

1. By default the role Crew does not see "Offene Punkte" (shortages are not its concern), and the planning, time
   planning, access and history of projects are not visible to it. It sees the material in the packing list and the
   phases in "Überblick".
2. Viewing the availability of material is a special right as well; by default the crew does not have it.
3. When a service case is assigned to a person of the role Crew, the person is told that they are responsible for
   it, even though they could neither see nor open it. Rule: crew taking part can do everything needed to work on the case
   (also correspondence, chat, changing the status). Important: correspondence in projects is always confidential,
   in service cases normally not.
4. Personal → Personen and Einstellungen → Nutzer get a column that shows whether the person has access to
   financial details (material prices), to personnel data (data protection) and to customer data (also data
   protection).
"""

from __future__ import annotations

import importlib
import json
from unittest import mock

from django.apps import apps
from django.urls import reverse

from rentalars.accounts import data_access
from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, ProjectScope, SpecialRight, rights_of
from rentalars.chat.models import ChatMessage
from rentalars.core.history import describe
from rentalars.core.models import AuditLogEntry
from rentalars.core.navigation import entries_for
from rentalars.customers.models import Contact
from rentalars.mail.models import ProjectMail
from rentalars.material.models import MaterialModel
from rentalars.notifications.models import Kind, Notification
from rentalars.notifications.services import check_shortages
from rentalars.packing import services as packing
from rentalars.projects import mvr, service_cases
from rentalars.projects.access import ProjectAccess, access_level, access_of_many, readable_projects, visible_projects
from rentalars.projects.models import (
    CaseStatus,
    MaterialLine,
    OpenItem,
    ProjectAccessLevel,
    ProjectMembership,
    ProjectPhase,
    RequestStatus,
)
from tests.api.base import API, ApiTestCase
from tests.api.test_mvr_import_api import mvr_file
from tests.helpers import (
    RentalarsTestCase,
    add_line,
    at,
    make_customer,
    make_items,
    make_model,
    make_person,
    make_product,
    make_project,
    make_stock,
    make_user,
    plan,
)
from tests.ui.base import UiTestCase, form_data
from tests.ui.test_mvr_import_pages import upload
from tests.unit.test_mvr_import import ROBIN

MIGRATION = importlib.import_module("rentalars.accounts.migrations.0008_roles_091")

#: A period for the availability endpoints (ISO 8601 with the time zone).
PERIOD = {"from": "2027-03-10T08:00:00+01:00", "to": "2027-03-12T18:00:00+01:00"}

#: A role like "Projektleitung" – all projects, prices – but without the right to see availability.
PLANNER_WITHOUT_AVAILABILITY = "Planung ohne Verfügbarkeit"


def planner_without_availability() -> Role:
    """A role that reads and plans every project but does not see the availability of material."""
    return Role.objects.create(
        name=PLANNER_WITHOUT_AVAILABILITY,
        module_levels={
            Module.PROJECTS: int(Level.DELETE),
            Module.PACKING: int(Level.WRITE),
            Module.PRODUCTS: int(Level.WRITE),
            Module.MATERIAL: int(Level.READ),
        },
        special_rights=[SpecialRight.PRICES],
    )


def tabs_of(page: str) -> str:
    """The tabs of a project page."""
    start = page.index('<nav class="tabs" aria-label="Projekt"')
    return page[start : page.index("</nav>", start)]


class CrewScene:
    """Carla (role "Crew") is planned on "Stadtfest" – and, as in the earlier setup, a member with "read"."""

    def make_scene(self) -> None:
        self.project = make_project("Stadtfest")
        self.cable = make_stock("K-005", 2, "XLR-Kabel 5 m")
        add_line(self.project, self.cable, 5)  # three missing
        ProjectPhase.objects.create(
            project=self.project, title="Aufbau Halle 3", start=self.project.start, end=at(10, 18)
        )
        self.carla_user = make_user("carla", roles=("Crew",))
        self.carla = make_person("Carla Crew", user=self.carla_user)
        plan(self.project, "Stagehand", self.carla, start=at(10, 8), end=at(10, 16))
        ProjectMembership.objects.create(project=self.project, user=self.carla_user, level=ProjectAccessLevel.READ)


# --- 1. The role "Crew": the overview only -----------------------------------------------------------------


class CrewRuleTests(CrewScene, RentalarsTestCase):
    """Requirement 1 (AUT-031): project access "assigned projects, overview without planning" (``ProjectScope.DEPLOYMENT``)."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()

    def test_the_start_role_crew(self) -> None:
        """New installations: Crew has the overview only and no availability; every other start role has it."""
        crew = Role.objects.get(name="Crew")
        self.assertEqual(crew.project_scope, ProjectScope.DEPLOYMENT)
        self.assertNotIn(SpecialRight.AVAILABILITY, crew.special_rights)
        # AUT-036: "Freie Kraft" sees no availability of material either.
        self.assertNotIn(SpecialRight.AVAILABILITY, Role.objects.get(name="Freie Kraft").special_rights)
        for role in Role.objects.exclude(name__in=["Crew", "Freie Kraft", PLANNER_WITHOUT_AVAILABILITY]):
            self.assertIn(SpecialRight.AVAILABILITY, role.special_rights, role.name)

    def test_a_membership_read_gives_the_overview_only(self) -> None:
        rights = rights_of(self.carla_user)
        self.assertEqual(rights.level(Module.PROJECTS), Level.READ)  # the module shows up …
        self.assertFalse(rights.reads_planning)  # … the planning never opens
        self.assertEqual(access_level(rights, self.carla_user, self.project), ProjectAccess.DEPLOYMENT)
        ProjectMembership.objects.filter(user=self.carla_user).update(level=ProjectAccessLevel.EDIT)
        self.assertEqual(access_level(rights, self.carla_user, self.project), ProjectAccess.DEPLOYMENT)
        self.assertEqual(access_of_many(rights, self.carla_user, [self.project.pk]), {self.project.pk: 1})
        self.assertIn(self.project, visible_projects(rights, self.carla_user))
        self.assertNotIn(self.project, readable_projects(rights, self.carla_user))

    def test_another_role_opens_what_it_opens(self) -> None:
        """Roles add up: a second role for assigned projects that reads the planning opens it again."""
        Role.objects.create(
            name="Bauleitung extern",
            module_levels={Module.PROJECTS: int(Level.WRITE)},
            project_scope=ProjectScope.ASSIGNED,
        )
        self.carla_user.roles.add(Role.objects.get(name="Bauleitung extern"))
        user = type(self.carla_user).objects.get(pk=self.carla_user.pk)
        self.assertEqual(access_level(rights_of(user), user, self.project), ProjectAccess.READ)
        reader = make_user("rita", roles=("Crew", "Nur-Lesen"))
        self.assertEqual(access_level(rights_of(reader), reader, make_project("Jazznacht")), ProjectAccess.READ)

    def test_a_read_only_token_keeps_the_ceiling(self) -> None:
        rights = rights_of(self.carla_user).restricted(read_only=True, allowed_modules=[])
        self.assertFalse(rights.reads_planning)
        self.assertEqual(rights.case_work, Level.READ)
        narrowed = rights_of(make_user("paula", roles=("Projektleitung",))).restricted(
            read_only=True, allowed_modules=[Module.PACKING]
        )
        self.assertFalse(narrowed.reads_planning)
        self.assertEqual(narrowed.case_work, Level.NONE)

    def test_navigation_and_shortage_notifications(self) -> None:
        """No "Fehlbestände" in the navigation; a project managed by Crew reports its shortage to others."""
        starts = [start for link in entries_for(rights_of(self.carla_user)) for _prefix, start in link.starts]
        self.assertNotIn(reverse("availability:shortages"), starts)
        self.project.manager = self.carla_user
        self.project.save()
        paula = make_user("paula", roles=("Projektleitung",))
        check_shortages()
        notified = set(Notification.objects.filter(kind=Kind.SHORTAGE).values_list("user__username", flat=True))
        self.assertNotIn("carla", notified)
        self.assertIn(paula.username, notified)


class CrewPageTests(CrewScene, UiTestCase):
    """Requirement 1 (AUT-031) on the pages: overview, packing list, chat; nothing else of the project: refused, not hidden."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        self.browser = self.browser_of(self.carla_user)

    def test_overview_with_phases_packing_list_and_chat(self) -> None:
        # EML-055: only a confirmed line makes Carla the crew of the correspondence – she accepted.
        self.project.crew_lines.filter(person=self.carla).update(request_status=RequestStatus.ACCEPTED)
        page = self.assert_ok(self.browser.get(reverse("projects:deployment", args=[self.project])))
        self.assertIn("Aufbau Halle 3", page)  # the phases in "Überblick"
        tabs = tabs_of(page)
        # EML-055: the crew planned in the project reads its open messages – the tab "Korrespondenz" is there.
        for shown in ("Überblick", "Packliste", "Chat", "Korrespondenz"):
            self.assertIn(shown, tabs)
        for hidden in ("Planung", "Zeitplanung", "Zugriff", "Verlauf", "Dokumente"):
            self.assertNotIn(hidden, tabs)
        packing = self.assert_ok(self.browser.get(reverse("packing:packlist", args=[self.project])))
        self.assertIn("K-005", packing)  # the material in the packing list
        self.assert_ok(self.browser.get(reverse("chat:project", args=[self.project])))

    def test_planning_schedule_access_and_history_are_refused(self) -> None:
        planning = self.browser.get(reverse("projects:detail", args=[self.project]))
        self.assertRedirects(planning, reverse("projects:deployment", args=[self.project]))
        for name in ("projects:course", "projects:members", "projects:history", "documents:list"):
            self.assertEqual(self.browser.get(reverse(name, args=[self.project])).status_code, 403, name)

    def test_open_items_and_shortages_are_refused(self) -> None:
        tabs = self.assert_ok(self.browser.get(reverse("projects:list")))
        self.assertNotIn("Offene Punkte", tabs)
        for name in ("projects:open_items", "availability:shortages", "schedule:products"):
            self.assertEqual(self.browser.get(reverse(name)).status_code, 403, name)
        home = self.assert_ok(self.browser.get(reverse("core:home")))
        self.assertNotIn("Offene Fehlbestände", home)
        self.assertNotIn("Fehlbestand", home)

    def test_the_role_editor_shows_and_saves_both(self) -> None:
        role = Role.objects.get(name="Freie Kraft")
        url = reverse("accounts:role_edit", args=[role.pk])
        page = self.assert_ok(self.client.get(url))
        self.assertIn("nur zugeordnete Projekte, Überblick ohne Planung", page)
        self.assertIn("Verfügbarkeit von Material sehen", page)
        data = form_data(self.client.get(url), "project_scope", project_scope=ProjectScope.DEPLOYMENT)
        data["special_rights"] = []
        self.client.post(url, data)
        role.refresh_from_db()
        self.assertEqual(role.project_scope, ProjectScope.DEPLOYMENT)
        self.assertEqual(role.special_rights, [])
        data["special_rights"] = [SpecialRight.AVAILABILITY]
        data["project_scope"] = ProjectScope.ASSIGNED
        self.client.post(url, data)
        role.refresh_from_db()
        self.assertEqual((role.project_scope, role.special_rights), (ProjectScope.ASSIGNED, ["availability"]))


class CrewApiTests(CrewScene, ApiTestCase):
    """Requirement 1 (AUT-031) in the API: the same refusals (AUT-020, API-006)."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        self.crew = self.client_of(self.carla_user)

    def test_what_crew_reaches(self) -> None:
        base = f"{API}/projects/{self.project.pk}"
        self.assertEqual(self.crew.get(base).json()["access"], "deployment")
        self.assertEqual(self.crew.get(f"{base}/packlists").status_code, 200)
        self.assertEqual(self.crew.get(f"{base}/chat").status_code, 200)
        for path in (f"{base}/planning", f"{base}/history", f"{base}/members", f"{base}/open-items"):
            self.assertEqual(self.crew.get(path).status_code, 403, path)
        for path in (f"{API}/open-items", f"{API}/shortages", f"{API}/utilization"):
            self.assertEqual(self.crew.get(path).status_code, 403, path)

    def test_the_catalogue_and_a_role_through_the_api(self) -> None:
        catalogue = self.admin.get(f"{API}/permissions").json()
        self.assertIn("deployment", [scope["value"] for scope in catalogue["project_scopes"]])
        self.assertIn("availability", [right["value"] for right in catalogue["special_rights"]])
        role = Role.objects.get(name="Freie Kraft")
        changed = self.admin.patch(f"{API}/roles/{role.pk}", {"project_scope": "deployment"}, format="json")
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual(changed.json()["project_scope"], "deployment")


# --- The data migration -------------------------------------------------------------------------------------


class MigrationTests(RentalarsTestCase):
    """accounts 0008: an older installation – its roles as they were, then the step (AUT-031, AUT-032)."""

    def back_to_090(self) -> None:
        """The roles as an installation had them (the start rights – AUT-036 – taken back)."""
        MIGRATION.back_to_090(apps, None)
        Role.objects.filter(name="Crew").update(special_rights=[])
        Role.objects.filter(name="Lager").update(special_rights=[SpecialRight.PURCHASE_PRICES])

    def test_fresh_crew_and_the_others(self) -> None:
        self.back_to_090()
        crew = Role.objects.get(name="Crew")
        self.assertEqual((crew.project_scope, crew.special_rights), (ProjectScope.ASSIGNED, []))
        MIGRATION.update_roles(apps, None)
        crew.refresh_from_db()
        self.assertEqual((crew.project_scope, crew.special_rights), (ProjectScope.DEPLOYMENT, []))
        for role in Role.objects.exclude(name="Crew"):
            self.assertIn(SpecialRight.AVAILABILITY, role.special_rights, role.name)
        entries = AuditLogEntry.objects.filter(actor_label="Aktualisierung 0.9.1")
        crew_entry = entries.get(object_id=str(crew.pk))
        self.assertEqual(crew_entry.changes, {"project_scope": ["assigned", "deployment"]})
        self.assertEqual(entries.count(), Role.objects.count())
        lager = Role.objects.get(name="Lager")
        self.assertEqual(
            entries.get(object_id=str(lager.pk)).changes,
            {"special_rights": [["purchase_prices"], ["availability", "purchase_prices"]]},
        )

    def test_a_crew_the_company_changed_is_left_alone(self) -> None:
        self.back_to_090()
        crew = Role.objects.get(name="Crew")
        crew.special_rights = [SpecialRight.PRICES]
        crew.save()
        MIGRATION.update_roles(apps, None)
        crew.refresh_from_db()
        self.assertEqual(crew.project_scope, ProjectScope.ASSIGNED)
        self.assertEqual(crew.special_rights, ["availability", "prices"])  # nothing changes for its users
        event = AuditLogEntry.objects.get(event="role.crew_left_as_is")
        self.assertEqual(event.actor_label, "Aktualisierung 0.9.1")
        reader = rights_of(make_user("a", superuser=True))
        self.assertIn("behält ihren Projektzugriff", describe([event], reader)[0].summary)

    def test_crew_with_another_projects_level_is_left_alone(self) -> None:
        self.back_to_090()
        crew = Role.objects.get(name="Crew")
        crew.module_levels = {**crew.module_levels, Module.PROJECTS: int(Level.WRITE)}
        crew.save()
        MIGRATION.update_roles(apps, None)
        crew.refresh_from_db()
        self.assertEqual(crew.project_scope, ProjectScope.ASSIGNED)

    def test_going_back(self) -> None:
        Role.objects.create(name="Eigene Crew", project_scope=ProjectScope.DEPLOYMENT, special_rights=["availability"])
        self.back_to_090()
        self.assertFalse(Role.objects.filter(project_scope=ProjectScope.DEPLOYMENT).exists())
        self.assertFalse(any(SpecialRight.AVAILABILITY in role.special_rights for role in Role.objects.all()))


# --- 2. Availability as a special right ---------------------------------------------------------------------


class AvailabilityScene:
    """A project short of three cables; Petra plans every project but does not see availability."""

    def make_scene(self) -> None:
        planner_without_availability()
        self.project = make_project("Stadtfest")
        self.cable = make_stock("K-005", 2, "XLR-Kabel 5 m")
        self.line = add_line(self.project, self.cable, 5).line
        self.petra = make_user("petra", roles=(PLANNER_WITHOUT_AVAILABILITY,))


class AvailabilityPageTests(AvailabilityScene, UiTestCase):
    """Requirement 2 (AUT-032) on the pages: every place that shows availability, refused or left out."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        self.browser = self.browser_of(self.petra)
        self.paula = self.browser_for("paula", "Projektleitung")

    def test_planning_and_line_dialog(self) -> None:
        url = reverse("projects:detail", args=[self.project])
        self.assertIn("Fehlmenge 3", self.assert_ok(self.paula.get(url)))
        page = self.assert_ok(self.browser.get(url))
        self.assertIn("K-005", page)  # the planning itself is open
        for hidden in ("Fehlmenge", "Es fehlen 3 Stück", "zumieten"):
            self.assertNotIn(hidden, page)
        check = reverse("projects:line_availability", args=[self.project])
        query = {"line": self.line.pk, "quantity": 5, "start": "2027-03-10T08:00", "end": "2027-03-12T18:00"}
        self.assertIn("avail short", self.assert_ok(self.paula.get(check, query)))
        self.assertNotIn("avail", self.assert_ok(self.browser.get(check, query)))

    def test_product_page_timeline_and_utilization(self) -> None:
        detail = reverse("products:detail", args=[self.cable])
        self.assertIn("<h2>Verfügbarkeit</h2>", self.assert_ok(self.paula.get(detail)))
        page = self.assert_ok(self.browser.get(detail))
        self.assertNotIn("<h2>Verfügbarkeit</h2>", page)
        self.assertNotIn(reverse("products:timeline", args=[self.cable]), page)
        self.assertEqual(self.browser.get(reverse("products:timeline", args=[self.cable])).status_code, 403)
        self.assertEqual(self.paula.get(reverse("products:timeline", args=[self.cable])).status_code, 200)
        for name in ("schedule:products", "availability:shortages"):
            self.assertEqual(self.browser.get(reverse(name)).status_code, 403, name)
            self.assertEqual(self.paula.get(reverse(name)).status_code, 200, name)
        model = MaterialModel.objects.get(default_product=self.cable)
        self.assertEqual(self.browser.get(reverse("material:model_timeline", args=[model.pk])).status_code, 403)
        item = model.items.first()
        self.assertEqual(self.browser.get(reverse("material:item_timeline", args=[item.pk])).status_code, 403)

    def test_start_page_and_open_items(self) -> None:
        self.assertIn("Offene Fehlbestände", self.assert_ok(self.paula.get(reverse("core:home"))))
        self.assertNotIn("Offene Fehlbestände", self.assert_ok(self.browser.get(reverse("core:home"))))
        self.assertIn("Fehlbestand: 3", self.assert_ok(self.paula.get(reverse("projects:open_items"))))
        self.assertNotIn("Fehlbestand", self.assert_ok(self.browser.get(reverse("projects:open_items"))))
        tabs = self.assert_ok(self.browser.get(reverse("schedule:calendar")))
        self.assertNotIn(reverse("availability:shortages"), tabs)
        self.assertNotIn(reverse("schedule:products"), tabs)


class AvailabilityApiTests(AvailabilityScene, ApiTestCase):
    """Requirement 2 (AUT-032) in the API."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        self.client_ = self.client_of(self.petra)
        self.paula = self.client_for("paula", "Projektleitung")

    def test_refused_endpoints(self) -> None:
        model = MaterialModel.objects.get(default_product=self.cable)
        refused = [
            (f"{API}/availability", {"products": str(self.cable.pk), **PERIOD}),
            (f"{API}/products/{self.cable.pk}/availability", PERIOD),
            (f"{API}/products/{self.cable.pk}/timeline", {}),
            (f"{API}/material-models/{model.pk}/timeline", {}),
            (f"{API}/material-items/{model.items.first().pk}/timeline", {}),
            (f"{API}/utilization", {"product": self.cable.pk}),
            (f"{API}/shortages", {}),
            (f"{API}/projects/{self.project.pk}/shortages", {}),
        ]
        for path, query in refused:
            self.assertEqual(self.client_.get(path, query).status_code, 403, path)
            self.assertEqual(self.paula.get(path, query).status_code, 200, path)

    def test_the_planning_without_availability(self) -> None:
        url = f"{API}/projects/{self.project.pk}/planning"
        own = self.client_.get(url).json()
        self.assertIsNone(own["shortage_total"])
        self.assertIsNone(own["without_group"][0]["availability"])
        theirs = self.paula.get(url).json()
        self.assertEqual(theirs["shortage_total"], 3)
        self.assertEqual(theirs["without_group"][0]["availability"]["status"], "short")
        line = self.client_.get(f"{API}/projects/{self.project.pk}/material-lines/{self.line.pk}")
        self.assertIsNone(line.json()["availability"])


# --- 3. Working on service cases ----------------------------------------------------------------------------


class CaseScene:
    """Carla (Crew) is responsible for a case, Kai (Crew) takes part; another case is neither's."""

    def make_scene(self) -> None:
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.carla_user = make_user("carla", roles=("Crew",))
        self.carla = make_person("Carla Crew", user=self.carla_user)
        self.kai_user = make_user("kai", roles=("Crew",))
        self.kai = make_person("Kai Kurz", user=self.kai_user)
        customer = make_customer()
        self.case = service_cases.create_case(
            name="Spot flackert", customer=customer, manager=self.carla_user, user=self.paula
        )
        service_cases.add_participant(self.case, self.kai, user=self.paula)
        self.other = service_cases.create_case(
            name="Nebelmaschine", customer=customer, manager=self.paula, user=self.paula
        )
        ProjectMail.objects.create(
            project=self.case,
            direction="in",
            message_key="key-1",
            message_id="<1@x.example>",
            subject="Spot defekt",
            sender_name="Max Muster",
            sender_address="max@stadthalle.example",
            date=at(1, 7),
            text_body="Der Spot flackert.",
            # EML-055: an open message – Crew without the price right reads the open ones only.
            locked=False,
        )


class CaseWorkPageTests(CaseScene, UiTestCase):
    """Requirement 3 (AUT-033) on the pages: responsible and taking part work on the case – and on nothing else."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        self.carla_browser = self.browser_of(self.carla_user)
        self.kai_browser = self.browser_of(self.kai_user)

    def test_the_notification_leads_to_the_case(self) -> None:
        notice = Notification.objects.filter(user=self.carla_user, url__contains="/case/").first()
        page = self.assert_ok(self.carla_browser.get(notice.url))
        self.assertIn("Status setzen", page)
        self.assertIn("Spot defekt", page)  # the latest mails
        tabs = tabs_of(page)
        for shown in ("Überblick", "Korrespondenz", "Chat"):
            self.assertIn(shown, tabs)

    def test_status_fields_open_items_follow_up(self) -> None:
        for browser in (self.carla_browser, self.kai_browser):
            response = browser.post(reverse("projects:case_status", args=[self.case]), {"case_status": "in_progress"})
            self.assertEqual(response.status_code, 302)
        self.case.refresh_from_db()
        self.assertEqual(self.case.case_status, CaseStatus.IN_PROGRESS)
        edit = reverse("projects:case_edit", args=[self.case])
        data = form_data(self.kai_browser.get(edit), "name", name="Spot flackert stark")
        self.assertEqual(self.kai_browser.post(edit, data).status_code, 302)
        self.case.refresh_from_db()
        self.assertEqual(self.case.name, "Spot flackert stark")
        self.kai_browser.post(reverse("projects:open_items_add", args=[self.case]), {"texts": "Ersatzteil bestellen"})
        item = OpenItem.objects.get(project=self.case)
        # The start page names the case, but no box "Offene Punkte" – that page is not Crew's (requirement 1).
        home = self.assert_ok(self.kai_browser.get(reverse("core:home")))
        self.assertIn("Spot flackert stark", home)
        self.assertNotIn(reverse("projects:open_items"), home)
        self.kai_browser.post(reverse("projects:open_item_toggle", args=[self.case, item.pk]), {"done": "1"})
        item.refresh_from_db()
        self.assertTrue(item.is_done)
        follow_up = reverse("projects:follow_up", args=[self.case])
        data = {"follow_up_on": "2027-03-05", "follow_up_user": self.carla_user.pk, "follow_up_note": "anrufen"}
        self.assertEqual(self.carla_browser.post(follow_up, data).status_code, 302)
        self.case.refresh_from_db()
        self.assertEqual(self.case.follow_up_note, "anrufen")

    def test_correspondence_and_chat(self) -> None:
        mails = self.assert_ok(self.kai_browser.get(reverse("mail:project_mails", args=[self.case])))
        self.assertIn("Spot defekt", mails)
        mail = ProjectMail.objects.get(project=self.case)
        self.assert_ok(self.kai_browser.get(reverse("mail:detail", args=[self.case, mail.pk])))
        self.assert_ok(self.carla_browser.get(reverse("mail:compose", args=[self.case])))
        response = self.carla_browser.post(
            reverse("mail:note_create", args=[self.case]),
            {"date": "2027-03-01T07:30", "subject": "Anruf", "text": "Kunde bringt den Spot vorbei."},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ProjectMail.objects.filter(project=self.case, direction="note").exists())
        self.kai_browser.post(reverse("chat:project", args=[self.case]), {"text": "Ich schaue es mir an."})
        self.assertTrue(ChatMessage.objects.filter(project=self.case, author=self.kai_user).exists())

    def test_never_another_case_or_a_project(self) -> None:
        for name in ("projects:case_detail", "mail:project_mails", "chat:project"):
            self.assertEqual(self.carla_browser.get(reverse(name, args=[self.other])).status_code, 404, name)
        refused = self.carla_browser.post(reverse("projects:case_status", args=[self.other]), {"case_status": "done"})
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(self.carla_browser.get(reverse("projects:case_convert", args=[self.case])).status_code, 403)
        # Correspondence of projects stays confidential: Carla planned on a project does not read its mails –
        # EML-055: those with lock; the open ones she reads (read only) – planned firmly (only
        # a confirmed line counts for the correspondence).
        project = make_project("Stadtfest")
        plan(project, "Stagehand", self.carla, start=at(10, 8), end=at(10, 16), firm=True)
        ProjectMail.objects.create(
            project=project, direction="in", message_key="key-p", subject="Angebot", date=at(1, 7), text_body="Preis"
        )
        page = self.assert_ok(self.carla_browser.get(reverse("mail:project_mails", args=[project])))
        self.assertNotIn("Angebot", page)
        self.assertEqual(self.carla_browser.get(reverse("mail:compose", args=[project])).status_code, 403)

    def test_without_the_module_projects(self) -> None:
        """Whoever has no right on projects at all still works on the case they are responsible for."""
        Role.objects.create(name="Werkstatt", module_levels={Module.TIME_TRACKING: int(Level.WRITE)})
        wera = make_user("wera", roles=("Werkstatt",))
        make_person("Wera Werk", user=wera)
        case = service_cases.create_case(name="Kabeltrommel", manager=wera, user=self.paula)
        browser = self.browser_of(wera)
        page = self.assert_ok(browser.get(reverse("projects:case_detail", args=[case])))
        self.assertNotIn("Verlauf", tabs_of(page))
        self.assert_ok(browser.get(reverse("chat:project", args=[case])))
        self.assert_ok(browser.get(reverse("mail:project_mails", args=[case])))
        self.assertIn("Kabeltrommel", self.assert_ok(browser.get(reverse("projects:my_cases"))))
        self.assertIn("Kabeltrommel", self.assert_ok(browser.get(reverse("core:home"))))
        self.assertEqual(browser.get(reverse("projects:list")).status_code, 403)
        self.assertEqual(browser.get(reverse("projects:case_detail", args=[self.case])).status_code, 403)


class CaseWorkApiTests(CaseScene, ApiTestCase):
    """Requirement 3 (AUT-033) in the API – also what the companion app syncs (API-015)."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        self.carla_api = self.client_of(self.carla_user)
        self.kai_api = self.client_of(self.kai_user)

    def test_list_read_change(self) -> None:
        listed = self.carla_api.get(f"{API}/service-cases").json()
        self.assertEqual([row["name"] for row in listed.get("results", listed)], ["Spot flackert"])
        case = f"{API}/service-cases/{self.case.pk}"
        self.assertEqual(self.kai_api.get(case).status_code, 200)
        changed = self.kai_api.patch(case, {"case_status": "in_progress", "notes": "Netzteil?"}, format="json")
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual(changed.json()["case_status"], "in_progress")
        added = self.carla_api.post(f"{case}/participants", {"person": self.carla.pk}, format="json")
        self.assertEqual(added.status_code, 201, added.content)
        follow_up = self.carla_api.put(
            f"{API}/projects/{self.case.pk}/follow-up", {"follow_up_on": "2027-03-05"}, format="json"
        )
        self.assertEqual(follow_up.status_code, 200, follow_up.content)
        self.assertEqual(self.carla_api.get(f"{API}/projects/{self.case.pk}").status_code, 200)

    def test_mails_notes_chat_open_items(self) -> None:
        base = f"{API}/projects/{self.case.pk}"
        self.assertEqual([row["subject"] for row in self.kai_api.get(f"{base}/mails").json()], ["Spot defekt"])
        note = self.kai_api.post(f"{base}/mails/notes", {"text": "Kunde angerufen."}, format="json")
        self.assertEqual(note.status_code, 201, note.content)
        chat = self.kai_api.post(f"{base}/chat", {"text": "Bin dran."}, format="json")
        self.assertEqual(chat.status_code, 201, chat.content)
        item = self.kai_api.post(f"{base}/open-items", {"text": "Ersatzteil"}, format="json")
        self.assertEqual(item.status_code, 201, item.content)

    def test_refusals(self) -> None:
        other = f"{API}/service-cases/{self.other.pk}"
        self.assertIn(self.carla_api.get(other).status_code, (403, 404))
        self.assertEqual(self.carla_api.patch(other, {"case_status": "done"}, format="json").status_code, 403)
        self.assertEqual(self.carla_api.get(f"{API}/projects/{self.other.pk}/mails").status_code, 404)
        case = f"{API}/service-cases/{self.case.pk}"
        self.assertEqual(self.carla_api.delete(case).status_code, 403)
        convert = self.carla_api.post(f"{case}/convert", {"start": "2027-03-10T08:00", "end": "2027-03-11T08:00"})
        self.assertEqual(convert.status_code, 403)
        read_only = self.client_of(self.carla_user, read_only=True)
        self.assertEqual(read_only.get(case).status_code, 200)
        self.assertEqual(read_only.patch(case, {"case_status": "done"}, format="json").status_code, 403)
        packing_only = self.client_of(self.carla_user, allowed_modules=["packing"])
        self.assertEqual(packing_only.get(case).status_code, 403)


# --- 4. Finances, personnel data, customer data -------------------------------------------------------------


class DataAccessTests(UiTestCase):
    """Requirement 4 (AUT-034): three optional columns in Personal → Personen and Einstellungen → Nutzer, and in the API."""

    COLUMNS = "user,finances,personnel_data,customer_data"

    def setUp(self) -> None:
        super().setUp()
        self.luka = make_user("luka", roles=("Lager",))
        self.carla = make_user("carla", roles=("Crew",))
        self.nora = make_user("nora", roles=("Nur-Lesen",))
        self.gone = make_user("gerd", roles=("Projektleitung",))
        self.gone.is_active = False
        self.gone.save()
        self.anna = make_person("Anna Ohnekonto")

    def test_the_answers(self) -> None:
        self.assertEqual(
            data_access.of_user(self.admin_user).as_document(),
            {"finances": "both", "personnel_data": "both", "customer_data": "change"},
        )
        self.assertEqual(
            data_access.of_user(self.luka).as_document(),
            {"finances": "purchase_prices", "personnel_data": "none", "customer_data": "none"},
        )
        self.assertEqual(
            data_access.of_user(self.nora).as_document(),
            {"finances": "both", "personnel_data": "both", "customer_data": "read"},
        )
        self.assertEqual(data_access.of_user(self.carla).finances, "none")
        self.assertEqual(data_access.of_user(self.gone), data_access.NONE_AT_ALL)
        self.assertEqual(data_access.of_user(None), data_access.NONE_AT_ALL)

    def test_user_list(self) -> None:
        url = reverse("accounts:user_list")
        page = self.assert_ok(self.client.get(url, {"cols": self.COLUMNS}))
        for shown in ("Finanzen", "Personaldaten", "Kundendaten", "Einkaufspreise", "Preise und Einkaufspreise"):
            self.assertIn(shown, page)
        self.assertIn("Personen und Stundensätze", page)
        self.assertIn("kein Zugang", page)  # the deactivated account
        self.assertIn("Aus den Rollen des Kontos", page)  # the legend
        self.assertNotIn("Aus den Rollen des Kontos", self.assert_ok(self.client.get(url)))  # off by default
        for extra in ({"sort": "finances"}, {"sort": "-customer_data"}, {"group": "personnel_data"}):
            self.assert_ok(self.client.get(url, {"cols": self.COLUMNS, **extra}))
        csv = self.client.get(url, {"cols": self.COLUMNS, "format": "csv"}).content.decode("utf-8-sig")
        self.assertIn("luka;Einkaufspreise;nein;nein", csv)

    def test_person_list(self) -> None:
        url = reverse("personnel:person_list")
        page = self.assert_ok(self.client.get(url, {"cols": "name,finances,personnel_data,customer_data"}))
        self.assertIn("Ohnekonto", page)
        self.assertIn("kein Zugang", page)
        csv = self.client.get(
            url, {"cols": "name,finances,personnel_data,customer_data", "format": "csv", "sort": "finances"}
        ).content.decode("utf-8-sig")
        self.assertIn("Ohnekonto, Anna;kein Zugang;kein Zugang;kein Zugang", csv)


class DataAccessApiTests(ApiTestCase):
    """Requirement 4 (AUT-034) through the API (API-002): ``data_access`` of ``/users`` and ``/people``."""

    def test_users_and_people(self) -> None:
        luka = make_user("luka", roles=("Lager",))
        anna = make_person("Anna Ohnekonto")
        user = self.admin.get(f"{API}/users/{luka.pk}").json()
        self.assertEqual(
            user["data_access"], {"finances": "purchase_prices", "personnel_data": "none", "customer_data": "none"}
        )
        person = self.admin.get(f"{API}/people/{anna.pk}").json()
        self.assertEqual(set(person["data_access"].values()), {"no_access"})


# --- 2. Availability as a special right: the shortages on the way ----------------------------


#: The rental period of the Stadtfest moved onto the Messe, which takes the two cables (13 to 15 March).
ONTO_THE_MESSE = {"what": "period", "start": "2027-03-13T00:00", "end": "2027-03-15T00:00"}


class ShortageOnTheWayScene(AvailabilityScene):
    """As :class:`AvailabilityScene`; besides, the Messe takes both cables after it, two Robin spots for a plot."""

    def make_scene(self) -> None:
        super().make_scene()
        add_line(make_project("Messe", start=at(13), end=at(15)), self.cable, 2)
        self.spot = make_product("L-010", "Robe Robin T1 Profile", price="80.00")
        make_items(make_model("Robin T1 Profile", self.spot, manufacturer="Robe"), 2)  # the plot wants five


class ShortageOnTheWayPageTests(ShortageOnTheWayScene, UiTestCase):
    """AUT-032: moving on the timeline, the MVR import and adding material while packing say what is
    missing only to whom may see the availability of material – in the pages."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        self.browser = self.browser_of(self.petra)
        self.paula = self.browser_for("paula", "Projektleitung")

    def move(self, client: object, method: str = "get") -> str:
        """The move dialog (``get``) or the move done (``post``), as the timeline sends them."""
        url = reverse("schedule:move", args=[self.project.pk])
        if method == "get":
            return self.assert_ok(self.htmx("get", url, ONTO_THE_MESSE, client=client))
        return self.assert_ok(self.htmx("post", url, {**ONTO_THE_MESSE, "sent": "1"}, client=client))

    def test_the_move_dialog(self) -> None:
        self.assertIn("Mit dem neuen Mietzeitraum fehlen 5 Stück.", self.move(self.paula))
        page = self.move(self.browser)
        self.assertIn("1 Materialposition hat den Mietzeitraum und übernimmt den neuen", page)  # the move itself
        for hidden in ("Mit dem neuen Mietzeitraum", "Wie bisher fehl", "Das Material reicht"):
            self.assertNotIn(hidden, page)

    def test_moving_without_the_right(self) -> None:
        page = self.move(self.browser, "post")
        self.assertIn("1 Materialposition hatte den bisherigen Mietzeitraum und hat den neuen übernommen.", page)
        self.assertNotIn("fehlen", page)
        self.project.refresh_from_db()
        self.assertEqual(self.project.start, at(13))

    def test_moving_with_the_right(self) -> None:
        self.assertIn(
            "Im neuen Mietzeitraum fehlen 5 Stück. Sieh dir die rot markierten Positionen an.",
            self.move(self.paula, "post"),
        )

    def import_plot(self, client: object) -> list[str]:
        """Upload the plot and take it over as preselected (the Robin spots); the messages afterwards."""
        url = reverse("projects:mvr_import", args=[self.project.pk])
        self.assertEqual(client.post(url, {"step": "upload", "file": upload()}).status_code, 302)
        data = form_data(client.get(url), containing="key_0", step="apply")
        return self.messages_of(client.post(url, data, follow=True))

    def test_the_mvr_import(self) -> None:
        added = self.import_plot(self.browser)
        self.assertIn("2 Positionen aus Stadtfest.mvr hinzugefügt.", added)
        self.assertFalse([message for message in added if "fehlen" in message], added)
        self.assertEqual(self.project.material_lines.filter(product=self.spot).count(), 2)
        added = self.import_plot(self.paula)
        self.assertIn("Robe Robin T1 Profile ist hinzugefügt, aber in diesem Zeitraum fehlen 5 Stück.", added)

    def test_adding_material_while_packing(self) -> None:
        url = reverse("packing:action", args=[self.project.pk, "add-material"])
        added = self.messages_of(self.browser.post(url, {"product": self.cable.pk, "quantity": "1"}, follow=True))
        self.assertFalse([message for message in added if "Fehlmenge" in message], added)
        self.assertEqual(MaterialLine.objects.filter(project=self.project, is_addendum=True).count(), 1)
        added = self.messages_of(self.paula.post(url, {"product": self.cable.pk, "quantity": "1"}, follow=True))
        self.assertIn("Fehlmenge: 1 × K-005 sind im Zeitraum nicht frei.", added)


class ShortageOnTheWayApiTests(ShortageOnTheWayScene, ApiTestCase):
    """AUT-032 in the API: without the right ``null`` or left out – and not even counted."""

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        self.client_ = self.client_of(self.petra)
        self.paula = self.client_for("paula", "Projektleitung")

    def test_reschedule(self) -> None:
        url = f"{API}/projects/{self.project.pk}/reschedule"
        body = {**ONTO_THE_MESSE, "start": "2027-03-13T00:00+01:00", "end": "2027-03-15T00:00+01:00"}
        theirs = self.paula.post(f"{url}/preview", body, format="json").json()["outcome"]
        self.assertEqual((theirs["shortage_before"], theirs["shortage_after"]), (3, 5))
        with mock.patch("rentalars.schedule.moves._shortage", side_effect=AssertionError("counted")):
            preview = self.client_.post(f"{url}/preview", body, format="json")
            self.assertEqual(preview.status_code, 200, preview.content)
            outcome = preview.json()["outcome"]
            self.assertEqual(
                (outcome["material_lines"], outcome["shortage_before"], outcome["shortage_after"]), (1, None, None)
            )
            moved = self.client_.post(url, body, format="json")
            self.assertEqual(moved.status_code, 200, moved.content)
            self.assertEqual((moved.json()["shortage_before"], moved.json()["shortage_after"]), (None, None))
        back = {**body, "start": "2027-03-10T00:00+01:00", "end": "2027-03-12T00:00+01:00"}
        theirs = self.paula.post(url, back, format="json").json()
        self.assertEqual((theirs["shortage_before"], theirs["shortage_after"]), (5, 3))

    def test_the_mvr_import(self) -> None:
        url = f"{API}/projects/{self.project.pk}/mvr"
        mapping = json.dumps({mvr.type_key(ROBIN, "Mode 1 - Standard 16 bit"): self.spot.pk})
        own = self.client_.post(url, {"file": mvr_file(), "mapping": mapping}, format="multipart")
        self.assertEqual(own.status_code, 201, own.content)
        self.assertEqual((len(own.json()["lines"]), own.json()["warnings"]), (1, []))
        theirs = self.paula.post(url, {"file": mvr_file(), "mapping": mapping}, format="multipart").json()
        self.assertEqual(
            theirs["warnings"], ["Robe Robin T1 Profile ist hinzugefügt, aber in diesem Zeitraum fehlen 5 Stück."]
        )

    def test_adding_material_while_packing(self) -> None:
        url = f"{API}/projects/{self.project.pk}/packlists/{packing.get_packlist(self.project).pk}/add-material"
        own = self.client_.post(url, {"product": self.cable.pk, "quantity": 1}, format="json")
        self.assertEqual(own.status_code, 200, own.content)
        self.assertEqual(own.json()["hints"], [])
        theirs = self.paula.post(url, {"product": self.cable.pk, "quantity": 1}, format="json").json()
        self.assertEqual(theirs["hints"], ["Fehlmenge: 1 × K-005 sind im Zeitraum nicht frei."])


# --- Review: the customer's side of a service case ----------------------------------------------------------------


class CustomerSideScene(CaseScene):
    """The case scene and a customer the case has nothing to do with, with a contact person."""

    def make_scene(self) -> None:
        super().make_scene()
        self.case.contact = Contact.objects.create(customer=self.case.customer, name="Max Muster")
        self.case.case_contact = "Hausmeister, 0170 1234567"
        self.case.save()
        self.stranger = make_customer("Geheim AG")
        self.stranger_contact = Contact.objects.create(customer=self.stranger, name="Gerda Geheim")

    def assert_unchanged(self) -> None:
        """Customer, contact, "internal" and who reported it are as before."""
        before = (self.case.customer_id, self.case.contact_id, self.case.is_internal, self.case.case_contact)
        self.case.refresh_from_db()
        after = (self.case.customer_id, self.case.contact_id, self.case.is_internal, self.case.case_contact)
        self.assertEqual(after, before)


class CaseCustomerSidePageTests(CustomerSideScene, UiTestCase):
    """AUT-033, AUT-034: working on a case shows no customer – not even through its edit form.

    As Kai (role Crew, no module customers, taking part in his case): ``…/case/edit/?customer=<any
    customer>`` showed the name of that customer and its contact person. Who may not see customers – as the page
    of the case hides them – gets no customer, contact, "internal" or "reported by" in the form, and posting them
    changes nothing. Who may see customers chooses them as before.
    """

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        self.edit = reverse("projects:case_edit", args=[self.case])
        self.kai_browser = self.browser_of(self.kai_user)

    def test_no_customer_through_the_address(self) -> None:
        page = self.assert_ok(self.kai_browser.get(f"{self.edit}?customer={self.stranger.pk}"))
        for hidden in ("Geheim AG", "Gerda Geheim", "Stadtwerke Musterstadt", "Max Muster", "0170 1234567"):
            self.assertNotIn(hidden, page)
        for field in ("customer", "contact", "is_internal", "case_contact"):
            self.assertNotIn(f'name="{field}"', page)
        self.assertIn('name="notes"', page)

    def test_posting_customer_and_contact_changes_nothing(self) -> None:
        data = form_data(self.kai_browser.get(self.edit), "name", name="Spot flackert stark")
        data.update(customer=self.stranger.pk, contact=self.stranger_contact.pk, is_internal="on", case_contact="Gerda")
        self.assertEqual(self.kai_browser.post(self.edit, data).status_code, 302)
        self.assert_unchanged()
        self.assertEqual(self.case.name, "Spot flackert stark")

    def test_who_may_see_customers_chooses_them(self) -> None:
        paula = self.browser_of(self.paula)
        response = paula.get(f"{self.edit}?customer={self.stranger.pk}")
        self.assertIn("Gerda Geheim", self.assert_ok(response))  # the contacts of the customer just chosen (PRJ-070)
        data = form_data(response, "name", customer=self.stranger.pk, contact=self.stranger_contact.pk)
        self.assertEqual(paula.post(self.edit, data).status_code, 302)
        self.case.refresh_from_db()
        self.assertEqual((self.case.customer, self.case.contact), (self.stranger, self.stranger_contact))


class CaseCustomerSideApiTests(CustomerSideScene, ApiTestCase):
    """AUT-033, AUT-034 in the API: ``PATCH /service-cases/{id}`` keeps the customer's side.

    Who may not see customers cannot change customer, contact, "internal" or "reported by" (403, nothing changed);
    the values the case has, sent back as ``GET`` delivered them, pass. Who may see customers changes them.
    """

    def setUp(self) -> None:
        super().setUp()
        self.make_scene()
        self.url = f"{API}/service-cases/{self.case.pk}"
        self.kai_api = self.client_of(self.kai_user)

    def test_refused_without_the_right(self) -> None:
        for change in (
            {"customer": self.stranger.pk},
            {"contact": self.stranger_contact.pk},
            {"customer": self.stranger.pk, "contact": self.stranger_contact.pk, "notes": "egal"},
            {"is_internal": True},
            {"case_contact": "Gerda"},
        ):
            with self.subTest(change):
                self.assertEqual(self.kai_api.patch(self.url, change, format="json").status_code, 403)
                self.assert_unchanged()
        self.assertNotEqual(self.case.notes, "egal")
        # The whole case sent back as it came, with one change of the description: taken.
        sent = {
            name: value
            for name, value in self.kai_api.get(self.url).json().items()
            if name in ("name", "customer", "contact", "is_internal", "case_contact", "notes", "manager")
        }
        echoed = self.kai_api.patch(self.url, {**sent, "notes": "Netzteil getauscht"}, format="json")
        self.assertEqual(echoed.status_code, 200, echoed.content)
        self.assert_unchanged()
        self.assertEqual(self.case.notes, "Netzteil getauscht")

    def test_empty_counts_as_sent_back(self) -> None:
        """The read leaves the customer's side empty for them (below): sent back empty, nothing changes."""
        for echo in ({"customer": None}, {"contact": None}, {"case_contact": ""}):
            with self.subTest(echo):
                self.assertEqual(self.kai_api.patch(self.url, echo, format="json").status_code, 200)
                self.assert_unchanged()

    def test_no_customer_in_what_they_read(self) -> None:
        """``GET /service-cases/{id}`` and ``/projects/{id}?expand=customer,contact`` showed them."""
        case = self.kai_api.get(self.url).json()
        self.assertEqual((case["customer"], case["contact"], case["case_contact"]), (None, None, ""))
        project = self.kai_api.get(f"{API}/projects/{self.case.pk}?expand=customer,contact")
        self.assertEqual(project.status_code, 200, project.content)
        for hidden in ("Max Muster", "0170 1234567"):
            self.assertNotIn(hidden, project.content.decode())
        # PRJ-122: the customer's name shows in every role – the name, not the customer record.
        self.assertEqual(project.json()["customer_name"], "Stadtwerke Musterstadt")
        self.assertIsNone(project.json()["customer"])
        listed = self.kai_api.get(f"{API}/service-cases").json()
        rows = listed["results"] if isinstance(listed, dict) else listed
        self.assertTrue(rows)
        self.assertTrue(all(row["customer"] is None for row in rows))
        # Who may see customers reads them as before.
        self.assertEqual(self.client_of(self.paula).get(self.url).json()["contact"], self.case.contact_id)

    def test_no_customer_suggestions_for_the_crew(self) -> None:
        """AUT-034: reading assigned projects only does not list every customer by name."""
        from django.test import Client

        crew, paula = Client(), Client()
        crew.force_login(self.kai_user)
        paula.force_login(self.paula)
        self.assertIn(crew.get(reverse("customers:suggest"), {"q": "Geheim"}).status_code, (403, 404))
        self.assertEqual(paula.get(reverse("customers:suggest"), {"q": "Geheim"}).status_code, 200)

    def test_who_may_see_customers_changes_them(self) -> None:
        paula = self.client_of(self.paula)
        changed = paula.patch(
            self.url, {"customer": self.stranger.pk, "contact": self.stranger_contact.pk}, format="json"
        )
        self.assertEqual(changed.status_code, 200, changed.content)
        self.case.refresh_from_db()
        self.assertEqual((self.case.customer, self.case.contact), (self.stranger, self.stranger_contact))
