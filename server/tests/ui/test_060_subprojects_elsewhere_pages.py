# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages beyond the planning of a part (PRJ-029, PRJ-044, PRJ-047, PRJ-048, PRJ-060, PRJ-076).

Duplicating and saving as template, the calendar and the timelines, the
search, the start page, the shortages, the time entry, the deployment view
and the correspondence – each names a part as part of its whole project.
"""

from __future__ import annotations

import re
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, ProjectScope, SpecialRight
from rentalars.mail.models import ProjectMail
from rentalars.projects import services
from rentalars.projects.models import Project, ProjectAccessLevel, ProjectMembership, ProjectPhase
from rentalars.projects.project_templates import save_as_template
from tests.helpers import (
    ALL_RIGHTS,
    add_line,
    at,
    make_customer,
    make_person,
    make_project,
    make_stock,
    make_user,
    plan,
)
from tests.ui.base import UiTestCase, form_data
from tests.ui.test_accessibility import problems_of


def make_family(name: str = "Stadtfest", *, day: int = 9) -> tuple[Project, Project, Project]:
    """A whole project from ``day`` with two stages, the second taking over six spots from the first."""
    customer = make_customer("Stadt Musterstadt")
    whole = make_project(name, start=at(day, 12), end=at(day + 5, 18), customer=customer)
    market = services.create_subproject(whole, name="Bühne Marktplatz", start=at(day + 1, 8), end=at(day + 3, 8))
    park = services.create_subproject(whole, name="Bühne Schlosspark", start=at(day + 3, 12), end=at(day + 5, 12))
    return whole, market, park


class FamilyPagesTestCase(UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.whole, self.market, self.park = make_family()
        self.spot = make_stock("L-100", 6, "Spot")
        self.source = add_line(self.market, self.spot, 6).line
        self.taken = services.take_over_line(self.source, self.park, rights=ALL_RIGHTS).line

    def external(self, username: str, **levels: str) -> object:
        """A browser of a user limited to assigned projects, with memberships ``{"whole": "edit", …}``."""
        role = Role.objects.get_or_create(
            name="Bühnenleitung extern",
            defaults={
                "module_levels": {Module.PROJECTS: int(Level.WRITE)},
                "project_scope": ProjectScope.ASSIGNED,
                "special_rights": [SpecialRight.CORRESPONDENCE_READ],
            },
        )[0]
        user = make_user(username)
        user.roles.set([role])
        for name, level in levels.items():
            ProjectMembership.objects.create(project=getattr(self, name), user=user, level=level)
        return self.browser_of(user)


class DuplicatePagesTests(FamilyPagesTestCase):
    """PRJ-029: with the subprojects, or a part as a new part or a project of its own."""

    def test_a_whole_project_with_its_parts(self) -> None:
        url = reverse("projects:duplicate", args=[self.whole.pk])
        page = self.client.get(url)
        self.assertIn("mit Teilprojekten", self.assert_ok(page))
        data = form_data(page, containing="with_subprojects", start="2028-03-09T12:00", end="2028-03-14T18:00")
        self.assertEqual(data["with_subprojects"], "on")
        response = self.client.post(url, data, follow=True)
        copy = Project.objects.filter(parent__isnull=True, start__year=2028).get()
        self.assertEqual(copy.subprojects.count(), 2)
        self.assertIn(f"Mit den Teilprojekten {copy.number}-1, {copy.number}-2.", self.messages_of(response))
        taken = copy.subprojects.get(name="Bühne Schlosspark").material_lines.get()
        self.assertEqual(taken.taken_over_from.project.parent, copy)

    def test_a_plain_project_has_no_choice_about_parts(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:duplicate", args=[make_project("Messe").pk])))
        self.assertNotIn("with_subprojects", page)
        self.assertNotIn("as_subproject", page)

    def test_a_part_as_new_part_of_the_same_whole_project(self) -> None:
        url = reverse("projects:duplicate", args=[self.park.pk])
        page = self.client.get(url)
        self.assertIn(f"als neues Teilprojekt von {self.whole.number} Stadtfest", self.assert_ok(page))
        data = form_data(page, containing="as_subproject", name="Bühne Hof")
        data.update(start="2027-03-01T12:00", end="2027-03-02T12:00")
        refused = self.assert_ok(self.client.post(url, data))
        self.assertIn("innerhalb des Mietzeitraums", refused)
        self.assertFalse(Project.objects.filter(name="Bühne Hof").exists())
        data.update(start="2027-03-13T12:00", end="2027-03-14T12:00")
        self.client.post(url, data)
        part = Project.objects.get(name="Bühne Hof")
        self.assertEqual((part.parent, part.number), (self.whole, f"{self.whole.number}-3"))

    def test_a_part_as_a_project_of_its_own(self) -> None:
        url = reverse("projects:duplicate", args=[self.park.pk])
        data = form_data(self.client.get(url), containing="as_subproject", name="Hoffest", as_subproject=None)
        data.update(start="2027-04-12T12:00", end="2027-04-14T12:00")
        response = self.client.post(url, data, follow=True)
        project = Project.objects.get(name="Hoffest")
        self.assertIsNone(project.parent)
        self.assertIsNone(project.material_lines.get().taken_over_from)
        self.assertIn(
            "1 aus einem anderen Teilprojekt übernommene Position ist in der Kopie eine normale Position.",
            self.messages_of(response),
        )

    def test_without_the_right_to_edit_the_whole_project_a_project_of_its_own(self) -> None:
        browser = self.external("erik", park=ProjectAccessLevel.EDIT)
        url = reverse("projects:duplicate", args=[self.park.pk])
        page = browser.get(url)
        self.assertIn("Die Kopie wird ein eigenständiges Projekt", self.assert_ok(page))
        self.assertNotIn("as_subproject", page.content.decode())
        data = form_data(page, containing="start", name="Eriks Bühne")
        browser.post(url, data)
        project = Project.objects.get(name="Eriks Bühne")
        self.assertIsNone(project.parent)
        self.assertTrue(ProjectMembership.objects.filter(project=project, user__username="erik").exists())


class TemplatePagesTests(FamilyPagesTestCase):
    """PRJ-076: a template of a whole project keeps its own content only; a part can start from a template."""

    def test_the_dialog_of_a_whole_project_says_what_is_left_out(self) -> None:
        dialog = self.assert_ok(self.htmx("get", reverse("projects:template_create", args=[self.whole.pk])))
        self.assertIn("Teilprojekte gehören nicht zur Vorlage; speichere sie einzeln als Vorlage.", dialog)
        part = self.assert_ok(self.htmx("get", reverse("projects:template_create", args=[self.park.pk])))
        self.assertNotIn("Teilprojekte gehören nicht zur Vorlage", part)

    def test_a_part_from_a_template(self) -> None:
        template = save_as_template(self.park, name="Bühne", rights=ALL_RIGHTS)
        url = reverse("projects:subproject_create", args=[self.whole.pk])
        page = self.client.get(url)
        data = form_data(page, containing="template", name="Bühne Hof", template=str(template.pk))
        data.update(start="2027-03-13T12:00", end="2027-03-14T12:00")
        self.client.post(url, data)
        part = Project.objects.get(name="Bühne Hof")
        line = part.material_lines.get()
        self.assertEqual((line.product, line.quantity, line.taken_over_from), (self.spot, Decimal("6"), None))
        self.assertEqual((line.start, line.end), (part.start, part.end))


class SchedulePagesTests(FamilyPagesTestCase):
    """PRJ-028, VFG-019 to VFG-022 with PRJ-044 and PRJ-060."""

    PATHS = (
        "/schedule/?view=month&month=2027-03",
        "/schedule/?view=week&week=2027-03-08",
        "/schedule/timeline/?weeks=2&from=2027-03-08",
        "/schedule/timeline/?days=2&from=2027-03-12",
        "/schedule/personnel/?weeks=2&from=2027-03-08",
    )

    def test_calendar_and_timeline_name_the_whole_project(self) -> None:
        month = self.assert_ok(self.client.get("/schedule/", {"view": "month", "month": "2027-03"}))
        self.assertIn("Bühne Marktplatz (Stadtfest)", month)
        self.assertIn(f"Teil von {self.whole.number} Stadtfest", month)
        week = self.assert_ok(self.client.get("/schedule/", {"view": "week", "week": "2027-03-08"}))
        self.assertIn("Bühne Schlosspark (Stadtfest)", week)
        make_project("Weinfest", start=at(10, 8), end=at(11, 8))
        timeline = self.assert_ok(self.client.get("/schedule/timeline/", {"weeks": "2", "from": "2027-03-08"}))
        numbers = re.findall(
            r'<div class="tl-label[^"]*"[^>]*>(?:<span[^>]*>↳</span> )?<a href="[^"]*">([^<]*)</a>', timeline
        )
        self.assertEqual(numbers[:3], [self.whole.number, self.market.number, self.park.number])
        self.assertEqual(timeline.count('class="tl-label is-part"'), 2)

    def test_the_product_timeline_shows_the_take_over(self) -> None:
        page = self.assert_ok(
            self.client.get(reverse("products:timeline", args=[self.spot.pk]), {"from": "2027-03-08", "weeks": "2"})
        )
        self.assertIn("6× übernommen", page)
        self.assertIn(f"übernommen von {self.market.number}", page)
        self.assertIn(f"Teil von {self.whole.number} Stadtfest", page)

    def fill(self, count: int) -> None:
        for number in range(count):
            _whole, _market, park = make_family(f"Fest {number}", day=1 + number % 10)
            ProjectPhase.objects.create(project=park, start=park.start, end=park.end)
            person = make_person(f"Person{number} Test", rates={"Stagehand": "20.00"})
            plan(park, "Stagehand", person, start=park.start, end=park.end)

    def test_no_findings_and_no_more_queries_with_more_parts(self) -> None:
        def counts() -> list[int]:
            result = []
            for path in self.PATHS:
                with CaptureQueriesContext(connection) as queries:
                    self.assert_ok(self.client.get(path))
                result.append(len(queries))
            return result

        # VFG-028: the session remembers days or weeks only when the choice changes; a first round writes it.
        counts()
        self.fill(2)
        few = counts()
        self.fill(6)
        self.assertEqual(counts(), few)
        found = []
        for path in self.PATHS:
            found += [f"{path}: {problem}" for problem in problems_of(self.assert_ok(self.client.get(path)))]
        self.assertEqual(found, [], "\n".join(found))


class SearchStartAndShortagesPagesTests(FamilyPagesTestCase):
    """UIX-002, UIX-003, PRJ-047, PRJ-057: parts say whose part they are."""

    def test_search_and_start_page(self) -> None:
        search = self.assert_ok(self.client.get(reverse("core:search"), {"q": "Bühne"}))
        self.assertIn(f"Teil von {self.whole.number} Stadtfest · Stadt Musterstadt", search)
        home = self.assert_ok(self.client.get(reverse("core:home")))
        self.assertIn(f"Teil von {self.whole.number} Stadtfest", home)

    def test_the_customer_lists_the_parts_after_their_whole_project(self) -> None:
        wine = make_project("Weinfest", start=at(11, 8), end=at(12, 8), customer=self.whole.customer)
        page = self.assert_ok(self.client.get(reverse("customers:detail", args=[self.whole.customer_id])))
        # Newest first – the whole project by its own start, its parts right after it.
        order = [page.index(f">{project.number} ") for project in (wine, self.whole, self.market, self.park)]
        self.assertEqual(order, sorted(order))
        self.assertIn(f"Teil von {self.whole.number} Stadtfest", page)

    def test_a_shortage_caused_by_another_part_leads_to_the_whole_project(self) -> None:
        cable = make_stock("K-100", 4, "Kabel")
        cable.buffer_after_hours = Decimal("24")
        cable.save()
        add_line(self.market, cable, 4)
        add_line(self.park, cable, 4)
        page = self.assert_ok(self.client.get(reverse("availability:shortages")))
        self.assertIn("davon belegt durch andere Teilprojekte: 4", page)
        self.assertIn(reverse("projects:family", args=[self.park.pk]), page)
        self.assertEqual(problems_of(page), [])


class CrewPagesTests(FamilyPagesTestCase):
    """PRJ-048: deployments and times of a part belong to the part and name the whole project."""

    def setUp(self) -> None:
        super().setUp()
        self.carla_user = make_user("carla", roles=("Crew",))
        self.carla = make_person("Carla Crew", user=self.carla_user, rates={"Stagehand": "20.00"})
        plan(self.park, "Stagehand", self.carla, start=at(12, 12), end=at(12, 20))
        self.browser = self.browser_of(self.carla_user)

    def test_the_deployment_view_names_the_whole_project(self) -> None:
        page = self.assert_ok(self.browser.get(reverse("projects:deployment", args=[self.park.pk])))
        self.assertIn("Gesamtprojekt", page)
        self.assertIn(f"{self.whole.number} Stadtfest", page)
        # The overview of the whole project is not for crew: no link to it.
        self.assertNotIn(reverse("projects:family", args=[self.park.pk]), page)
        self.assertEqual(problems_of(page), [])

    def test_the_quick_time_entry_offers_the_part_with_its_whole_project(self) -> None:
        dialog = self.assert_ok(self.htmx("get", reverse("timetracking:quick"), client=self.browser))
        self.assertIn(f"{self.park.number} Bühne Schlosspark (Stadtfest)", dialog)


class CorrespondencePagesTests(FamilyPagesTestCase):
    """EML-019 with PRJ-044, PRJ-049: the whole project lists the mails of its parts, marked."""

    def setUp(self) -> None:
        super().setUp()
        for key, project, subject in (
            ("w", self.whole, "Gesamtplanung"),
            ("m", self.market, "Bühnenplan Marktplatz"),
            ("p", self.park, "Bühnenplan Schlosspark"),
        ):
            ProjectMail.objects.create(project=project, message_key=key * 64, message_id=f"<{key}@x>", subject=subject)

    def test_the_whole_project_lists_the_mails_of_its_parts(self) -> None:
        url = reverse("mail:project_mails", args=[self.whole.pk])
        page = self.assert_ok(self.client.get(url, {"view": "list"}))
        for subject in ("Gesamtplanung", "Bühnenplan Marktplatz", "Bühnenplan Schlosspark"):
            self.assertIn(subject, page)
        park_mail = ProjectMail.objects.get(project=self.park)
        self.assertIn(reverse("mail:detail", args=[self.park.pk, park_mail.pk]), page)
        self.assertIn(f'<span class="badge part-mail" title="Bühne Schlosspark">{self.park.number}</span>', page)
        conversation = self.assert_ok(self.client.get(url, {"view": "conversation"}))
        self.assertIn(
            reverse("mail:detail", args=[self.market.pk, ProjectMail.objects.get(project=self.market).pk]), conversation
        )
        self.assertEqual(problems_of(page), [])
        # A part lists its own mails only.
        part = self.assert_ok(self.client.get(reverse("mail:project_mails", args=[self.park.pk]), {"view": "list"}))
        self.assertNotIn("Gesamtplanung", part)
        self.assertNotIn("Bühnenplan Marktplatz", part)

    def test_mails_of_parts_without_access_stay_hidden(self) -> None:
        browser = self.external("erik", whole=ProjectAccessLevel.READ, park=ProjectAccessLevel.NONE)
        # EML-055: Erik reads the correspondence without the price right – the open messages.
        ProjectMail.objects.update(locked=False)
        page = self.assert_ok(browser.get(reverse("mail:project_mails", args=[self.whole.pk]), {"view": "list"}))
        self.assertIn("Bühnenplan Marktplatz", page)
        self.assertNotIn("Bühnenplan Schlosspark", page)
