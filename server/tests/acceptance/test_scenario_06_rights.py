# SPDX-License-Identifier: GPL-3.0-or-later
"""Acceptance scenario 6 – Rechte (catalogue chapter 11).

The four statements of the scenario, each as a test:

* a module without access is invisible and refused by the API,
* a user with "assigned projects only" sees only those in list, search and API,
* a user without the price right sees projects without prices and hourly rates,
* a crew member with a crew line sees the deployment data and the packlist of
  the project, but neither prices nor correspondence.

Correspondence itself arrives with the e-mail module of a later stage; what
is checked here is that the special rights for it are not part of any level
of project access (AUT-025).
"""

from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Module, SpecialRight, rights_of
from rentalars.projects.models import ProjectAccessLevel, ProjectMembership
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    add_group,
    add_line,
    job_function,
    make_person,
    make_product,
    make_project,
    make_user,
    plan,
)


class Scenario06Rights(ApiTestCase):
    """AUT-015 to AUT-020, AUT-023, AUT-025, NFA-010."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest Hauptbühne", rental_days=1)
        front = add_group(self.project, "Licht Front-Traverse")
        add_line(self.project, make_product("L-010", "LED-Scheinwerfer", price="23.45"), 4, group=front)

    def test_module_without_access_is_invisible_and_refused_by_the_api(self) -> None:
        """The warehouse role has no access to customers."""
        user = make_user("luka", roles=("Lager",))
        self.client.force_login(user)

        page = self.client.get(reverse("core:home")).content.decode()
        self.assertIn("Materialverwaltung", page)
        self.assertIn(f'href="{reverse("products:list")}"', page)
        self.assertNotIn(reverse("customers:list"), page)
        self.assertNotIn(reverse("core:administration"), page)

        # Hiding the link is not enough (AUT-020): the page and the API refuse too.
        self.assertEqual(self.client.get(reverse("customers:list")).status_code, 403)
        self.assert_error(self.client_of(user).get(f"{API}/customers"), 403, "permission_denied")
        self.assert_error(
            self.client_of(user).post(f"{API}/customers", {"name": "Neu"}, format="json"), 403, "permission_denied"
        )

    def test_user_without_price_right_sees_projects_without_prices(self) -> None:
        Role.objects.create(name="Planung", module_levels={Module.PROJECTS: 2, Module.PACKING: 1})
        user = make_user("pia", roles=("Planung",))
        self.client.force_login(user)

        planning = self.client.get(reverse("projects:detail", args=[self.project.pk])).content.decode()
        self.assertIn("Licht Front-Traverse", planning)
        self.assertIn("LED-Scheinwerfer", planning)
        self.assertNotIn("23,45", planning)
        self.assertNotIn("93,80", planning)
        self.assertEqual(self.client.get(reverse("projects:price_overview", args=[self.project.pk])).status_code, 403)

        api = self.client_of(user).get(f"{API}/projects/{self.project.pk}/planning")
        self.assertEqual(api.status_code, 200)
        self.assertNotIn("23.45", api.content.decode())
        self.assertNotIn("93.80", api.content.decode())
        self.assertNotIn("totals", api.json())

        # … and without hourly rates: a person planned at 35.00 shows, the rate does not.
        plan(
            self.project,
            job_function("Tontechnik", price="45.00"),
            make_person("Anna Becker", rates={"Tontechnik": "35.00"}),
        )
        planning = self.client.get(reverse("projects:detail", args=[self.project.pk])).content.decode()
        self.assertIn("Anna Becker", planning)
        for hidden in ("35,00", "45,00"):
            self.assertNotIn(hidden, planning)
        crew_lines = self.client_of(user).get(f"{API}/projects/{self.project.pk}/crew-lines").json()
        self.assertEqual(crew_lines[0]["person_name"], "Anna Becker")
        for hidden in ("hourly_rate", "cost", "unit_price", "amount"):
            self.assertNotIn(hidden, crew_lines[0])

    def test_same_page_shows_prices_with_the_price_right(self) -> None:
        """The counterpart: the amounts are there for those who may see them."""
        self.client.force_login(self.admin_user)
        planning = self.client.get(reverse("projects:detail", args=[self.project.pk])).content.decode()
        self.assertIn("23,45", planning)
        self.assertIn("93,80", planning)

    def test_personnel_module_is_invisible_and_refused_without_the_right(self) -> None:
        """The warehouse role has no access to personnel."""
        person = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        user = make_user("luka", roles=("Lager",))
        self.client.force_login(user)
        page = self.client.get(reverse("core:home")).content.decode()
        self.assertNotIn(reverse("personnel:person_list"), page)
        self.assertNotIn(">Personal<", page.replace("</svg>", ">"))
        for name, arguments in (
            ("personnel:person_list", []),
            ("personnel:person_detail", [person.pk]),
            ("personnel:availability", []),
            ("personnel:job_function_list", []),
        ):
            self.assertEqual(self.client.get(reverse(name, args=arguments)).status_code, 403, name)
        api = self.client_of(user)
        for address in ("people", f"people/{person.pk}", f"people/{person.pk}/job-functions", "people/availability"):
            self.assert_error(api.get(f"{API}/{address}"), 403, "permission_denied")
        self.assert_error(api.post(f"{API}/people", {"last_name": "Neu"}, format="json"), 403, "permission_denied")

    def test_user_with_assigned_projects_only_sees_just_those_in_list_search_and_api(self) -> None:
        """AUT-016, AUT-017: the same answer everywhere."""
        other = make_project("Jazznacht im Hafen")
        crew = make_user("carla", roles=("Crew",))
        rights = rights_of(crew)
        self.assertTrue(rights.is_limited_to_assigned_projects())

        # Not assigned to anything yet: no project anywhere. Fail closed.
        self.client.force_login(crew)
        self.assertNotIn("Stadtfest", self.client.get(reverse("projects:list")).content.decode())
        self.assertEqual(self.client.get(reverse("projects:detail", args=[self.project.pk])).status_code, 404)
        api = self.client_of(crew)
        self.assertEqual(api.get(f"{API}/projects").json()["results"], [])
        self.assertEqual(api.get(f"{API}/search", {"q": "Stadtfest"}).json()["results"], [])

        # Assigned as a member of one project: that one, and only that one.
        ProjectMembership.objects.create(project=self.project, user=crew, level=ProjectAccessLevel.READ)
        listed = self.client.get(reverse("projects:list")).content.decode()
        self.assertIn("Stadtfest Hauptbühne", listed)
        self.assertNotIn("Jazznacht", listed)
        found = self.client.get(reverse("core:search"), {"q": "a"}).content.decode()
        self.assertIn("Stadtfest Hauptbühne", found)
        self.assertNotIn("Jazznacht", found)
        self.assertEqual([row["id"] for row in api.get(f"{API}/projects").json()["results"]], [self.project.pk])
        hits = api.get(f"{API}/search", {"q": "a"}).json()["results"]
        self.assertEqual([hit["id"] for group in hits for hit in group["hits"]], [self.project.pk])
        self.assertEqual(self.client.get(reverse("projects:detail", args=[other.pk])).status_code, 404)
        self.assertEqual(api.get(f"{API}/projects/{other.pk}").status_code, 404)
        self.assertEqual(api.get(f"{API}/projects/{other.pk}/planning").status_code, 404)

    def test_crew_member_with_a_crew_line_sees_deployment_and_packlist_but_no_prices(self) -> None:
        """AUT-018, AUT-023, AUT-025."""
        crew = make_user("carla", roles=("Crew",))
        person = make_person("Carla Crew", rates={"Stagehand": "20.00"}, user=crew)
        plan(self.project, job_function("Stagehand", price="28.00"), person, meeting_point="Rampe")
        self.client.force_login(crew)

        deployment = self.client.get(reverse("projects:deployment", args=[self.project.pk]))
        self.assertEqual(deployment.status_code, 200)
        page = deployment.content.decode()
        self.assertIn("Stagehand", page)
        self.assertIn("Rampe", page)
        packlist = self.client.get(reverse("packing:packlist", args=[self.project.pk]))
        self.assertEqual(packlist.status_code, 200)
        self.assertIn("LED-Scheinwerfer", packlist.content.decode())

        for text in (page, packlist.content.decode()):
            for hidden in ("23,45", "93,80", "28,00"):
                self.assertNotIn(hidden, text)
        self.assertEqual(self.client.get(reverse("projects:price_overview", args=[self.project.pk])).status_code, 403)
        api = self.client_of(crew)
        self.assert_error(api.get(f"{API}/projects/{self.project.pk}/planning"), 403, "permission_denied")
        self.assert_error(api.get(f"{API}/projects/{self.project.pk}/totals"), 403, "permission_denied")
        # Neither prices nor writing correspondence come with any level of project access; reading it is a
        # right of the role (AUT-036) – the open messages of its cases, never those with a lock (EML-055).
        rights = rights_of(crew)
        for right in (SpecialRight.PRICES, SpecialRight.CORRESPONDENCE_WRITE):
            self.assertFalse(rights.has(right), right)
        self.assertTrue(rights.has(SpecialRight.CORRESPONDENCE_READ))

    def test_a_second_role_for_all_projects_still_opens_them(self) -> None:
        both = make_user("paula", roles=("Crew", "Projektleitung"))
        self.assertTrue(rights_of(both).can_write(Module.PROJECTS))
