# SPDX-License-Identifier: GPL-3.0-or-later
"""Project pages – phase length, tab order, the add forms of the planning, the end of the event.

The requirements:

1. A new phase (in "Zeitplanung" as well as in the planning under "Personal") is by default not longer than 8 hours
   (before, the project period was the start value).
2. As in service cases, "Überblick" is the first tab in projects.
3. The fields in the tab "Planung" of a project are aligned and formatted uniformly.
4. In a project, "Veranstaltung bis" may go at most up to "Material zurück bis", otherwise a warning comes.
"""

from __future__ import annotations

import datetime
import re

from django.urls import reverse

from rentalars.projects import course, services
from rentalars.projects.models import PhaseKind, Project, ProjectPhase
from rentalars.projects.period_warnings import event_after_material_back, project_warnings
from tests.api.base import API, ApiTestCase
from tests.helpers import RentalarsTestCase, at, make_person, make_project, make_user, plan
from tests.ui.base import UiTestCase, form_data
from tests.unit.test_090_logistics import make_fleet

EIGHT_HOURS = datetime.timedelta(hours=8)
WARNING = "Die Veranstaltung endet nach „Material zurück bis“. Prüfe den Zeitraum."


def make_person_line(project: Project, user: object) -> None:
    """Plan the person of ``user`` in the project, so that the user sees its deployment view."""
    plan(project, "Stagehand", make_person("Carla Crew", rates={"Stagehand": "20.00"}, user=user))


def tabs_of(text: str) -> list[str]:
    """The labels of the tabs of a project page."""
    start = text.index('<nav class="tabs"')
    return [label.strip() for label in re.findall(r">([^<>]+)</a>", text[start : text.index("</nav>", start)])]


class PhaseLengthTests(UiTestCase):
    """PRJ-116 (phase length; PRJ-124): a new phase starts with at most eight hours – a default, no limit."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", start=at(12, 8), end=at(14, 20))

    def test_the_guess_is_at_most_eight_hours_and_not_beyond_the_rental_period(self) -> None:
        start, end = course.first_guess(self.project)
        self.assertEqual((start, end), (at(12, 8), at(12, 16)))
        short = make_project("Soundcheck", start=at(20, 12), end=at(20, 14))
        self.assertEqual(course.first_guess(short), (at(20, 12), at(20, 14)))
        night = make_project("Clubnacht", start=at(20, 22), end=at(21, 12))
        self.assertEqual(course.first_guess(night), (at(20, 22), at(21, 6)))  # over midnight within eight hours

    def test_the_last_phase_ends_beyond_eight_hours_before_the_end(self) -> None:
        course.add_phase(self.project, kind=PhaseKind.SETUP, start=at(14, 8), end=at(14, 17))
        # Starts where the latest phase ends; eight hours would reach 01:00 – the rental period ends at 20:00.
        start, end = course.first_guess(self.project)
        self.assertEqual((start, end), (at(14, 17), at(14, 20)))

    def test_the_page_and_the_dialog_start_with_eight_hours(self) -> None:
        for page in (
            self.assert_ok(self.client.get(reverse("projects:phase_create", args=[self.project.pk]))),
            self.assert_ok(self.htmx("get", reverse("projects:phase_dialog", args=[self.project.pk]))),
        ):
            self.assertRegex(
                page, r'name="start"[^>]*value="2027-03-12T08:00"|value="2027-03-12T08:00"[^>]*name="start"'
            )
            self.assertRegex(page, r'name="end"[^>]*value="2027-03-12T16:00"|value="2027-03-12T16:00"[^>]*name="end"')
            self.assertIn("Eine neue Phase beginnt mit höchstens acht Stunden. Du kannst sie länger machen.", page)

    def test_a_longer_phase_can_be_saved(self) -> None:
        page = self.client.get(reverse("projects:phase_create", args=[self.project.pk]))
        data = form_data(page, kind="setup", start="2027-03-12T08:00", end="2027-03-13T20:00")
        response = self.client.post(reverse("projects:phase_create", args=[self.project.pk]), data)
        self.assertEqual(response.status_code, 302, response.content.decode()[:300])
        phase = ProjectPhase.objects.get(project=self.project)
        self.assertEqual((phase.start, phase.end), (at(12, 8), at(13, 20)))

    def test_the_help_is_not_shown_when_a_phase_is_changed(self) -> None:
        phase = course.add_phase(self.project, kind=PhaseKind.SETUP, start=at(12, 8), end=at(12, 12))
        page = self.assert_ok(self.client.get(reverse("projects:phase_edit", args=[self.project.pk, phase.pk])))
        self.assertNotIn("höchstens acht Stunden", page)


class PhaseLengthApiTests(ApiTestCase):
    """The API takes the period as given: no default, no limit (PRJ-116)."""

    def test_a_long_phase_through_the_api(self) -> None:
        project = make_project("Stadtfest", start=at(12, 8), end=at(14, 20))
        response = self.admin.post(
            f"{API}/projects/{project.pk}/phases",
            {"kind": "setup", "start": "2027-03-12T08:00+01:00", "end": "2027-03-14T20:00+01:00"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)


class TabOrderTests(UiTestCase):
    """PRJ-104 (tab order; PRJ-125): "Überblick" is the first tab of a project, as of a service case."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest")

    def test_overview_is_first_in_a_project(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.project.pk])))
        tabs = tabs_of(page)
        self.assertEqual(tabs[:2], ["Überblick", "Planung"])
        self.assertEqual(tabs.count("Überblick"), 1)
        self.assertEqual(tabs[-2:], ["Zugriff", "Verlauf"])

    def test_opening_a_project_leads_to_the_overview(self) -> None:
        response = self.client.get(reverse("projects:overview", args=[self.project.pk]))
        self.assertRedirects(response, reverse("projects:deployment", args=[self.project.pk]))
        page = self.assert_ok(self.client.get(reverse("projects:deployment", args=[self.project.pk])))
        self.assertIn(
            f'href="{reverse("projects:deployment", args=[self.project.pk])}" aria-current="page">Überblick', page
        )

    def test_the_planning_keeps_its_address(self) -> None:
        page = self.assert_ok(self.client.get(f"/projects/{self.project.pk}/"))
        self.assertIn(f'href="{reverse("projects:detail", args=[self.project.pk])}" aria-current="page">Planung', page)

    def test_a_service_case_opens_on_its_overview(self) -> None:
        case = Project.objects.get(pk=self._make_case().pk)
        response = self.client.get(reverse("projects:overview", args=[case.pk]))
        self.assertRedirects(response, reverse("projects:case_detail", args=[case.pk]))

    def _make_case(self) -> Project:
        from rentalars.projects import service_cases
        from tests.helpers import make_customer

        return service_cases.create_case(name="Spot flackert", customer=make_customer("Kunde 095"))

    def test_the_list_and_the_search_lead_to_the_overview(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:list")))
        self.assertIn(f'href="{reverse("projects:overview", args=[self.project.pk])}"', page)

    def test_what_follows_an_action_on_the_planning_stays_on_the_planning(self) -> None:
        response = self.client.post(reverse("projects:set_status", args=[self.project.pk]), {"status": "confirmed"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("projects:detail", args=[self.project.pk]))

    def test_the_deployment_view_only(self) -> None:
        """Whoever sees the deployment view only: "Überblick" first, then packlist and chat."""
        user = make_user("carla", roles=("Crew",))
        make_person_line(self.project, user)
        page = self.assert_ok(self.browser_of(user).get(reverse("projects:deployment", args=[self.project.pk])))
        self.assertEqual(tabs_of(page)[:2], ["Überblick", "Packliste"])  # then "Chat" (with its badge)
        response = self.browser_of(user).get(reverse("projects:overview", args=[self.project.pk]))
        self.assertRedirects(response, reverse("projects:deployment", args=[self.project.pk]))


class AddFormsTests(UiTestCase):
    """Add forms of the planning: the three add forms share one layout and one place for their help."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest")
        make_fleet()
        course.add_phase(self.project, kind=PhaseKind.SETUP, start=at(10, 8), end=at(10, 12))
        self.page = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.project.pk])))

    def form(self, css: str) -> str:
        match = re.search(rf'<form class="[^"]*\b{css}\b[^"]*".*?</form>', self.page, re.S)
        self.assertIsNotNone(match, css)
        return match.group(0)  # type: ignore[union-attr]

    def test_every_add_form_uses_the_shared_layout(self) -> None:
        for css in ("crew-add", "vehicle-add"):
            form = self.form(css)
            self.assertIn("add-row", form.split(">", 1)[0])
            self.assertIn('class="add-actions"', form)
            self.assertIn('data-range-slot="start"', form)
        self.assertIn("add-row", re.search(r'<form class="[^"]*line-add[^"]*"', self.page).group(0))  # type: ignore[union-attr]

    def test_the_help_of_the_phase_is_a_line_below_the_row_and_named_by_the_list(self) -> None:
        for css in ("crew-add", "vehicle-add"):
            form = self.form(css)
            self.assertNotRegex(form, r'<div class="field[^"]*">(?:(?!</div>).)*class="help"')
            help_id = re.search(r'class="add-help" id="([^"]+)"', form)
            self.assertIsNotNone(help_id, css)
            self.assertIn(f'aria-describedby="{help_id.group(1)}"', form)  # type: ignore[union-attr]
            self.assertIn("Mit der Phase wird ihr Zeitraum übernommen.", form)
            self.assertLess(form.index('class="add-actions"'), form.index('class="add-help"'))


class EventEndWarningTests(RentalarsTestCase):
    """PRJ-005 (event end; PRJ-127): the event ends after "Material zurück bis" – a warning."""

    def test_the_rule(self) -> None:
        self.assertFalse(event_after_material_back(at(12, 18), at(12, 18)))  # exactly at the end: fine
        self.assertFalse(event_after_material_back(at(12, 18), at(12, 10)))
        self.assertFalse(event_after_material_back(at(12, 18), None))
        self.assertFalse(event_after_material_back(None, at(12, 18)))
        self.assertTrue(event_after_material_back(at(12, 18), at(12, 19)))
        self.assertFalse(event_after_material_back(at(12, 18), at(12, 19), is_service_case=True))

    def test_warnings_of_a_project(self) -> None:
        project = make_project(
            "Stadtfest", start=at(10, 8), end=at(12, 18), event_start=at(11, 18), event_end=at(11, 23)
        )
        self.assertEqual(project_warnings(project), [])
        project = services.update_project(project, event_end=at(13, 1))  # saved all the same
        self.assertEqual(project_warnings(project), [WARNING])


class EventEndWarningPageTests(UiTestCase):
    """The project form: a hint on the page, a message after saving – both without blocking."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(
            "Stadtfest", start=at(10, 8), end=at(12, 18), event_start=at(11, 18), event_end=at(11, 23)
        )
        self.url = reverse("projects:edit", args=[self.project.pk])

    def hint(self, page: str) -> str:
        return re.search(r"<p class=\"field-warning\"[^>]*>", page).group(0)  # type: ignore[union-attr]

    def test_hidden_while_the_event_fits(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn("hidden", self.hint(page))

    def test_shown_by_the_server_when_it_does_not_fit_and_saving_works(self) -> None:
        page = self.client.get(self.url)
        data = form_data(page, event_start="2027-03-12T10:00", event_end="2027-03-13T02:00")
        response = self.client.post(self.url, data, follow=True)
        self.assertEqual(response.redirect_chain[-1][0], reverse("projects:detail", args=[self.project.pk]))
        self.assertIn(WARNING, self.messages_of(response))
        self.assertIn("Projekt", " ".join(self.messages_of(response)))  # "saved" as well – the warning is no error
        self.project.refresh_from_db()
        self.assertEqual(self.project.event_end, at(13, 2))
        form = self.assert_ok(self.client.get(self.url))
        self.assertNotIn("hidden", self.hint(form))
        self.assertIn(WARNING, form)

    def test_no_message_when_it_fits(self) -> None:
        page = self.client.get(self.url)
        response = self.client.post(self.url, form_data(page, event_end="2027-03-12T18:00"), follow=True)
        self.assertNotIn(WARNING, self.messages_of(response))


class EventEndWarningApiTests(ApiTestCase):
    """PRJ-005 (event end; PRJ-127): ``warnings`` of the project and of a move of the event."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(
            "Stadtfest", start=at(10, 8), end=at(12, 18), event_start=at(11, 18), event_end=at(11, 23)
        )
        self.url = f"{API}/projects/{self.project.pk}"

    def test_the_project_names_its_warnings(self) -> None:
        self.assertEqual(self.admin.get(self.url).json()["warnings"], [])
        response = self.admin.patch(self.url, {"event_end": "2027-03-13T02:00+01:00"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)  # no error: the change is saved
        self.assertEqual(response.json()["warnings"], [WARNING])
        self.assertEqual(self.admin.get(self.url).json()["warnings"], [WARNING])
        fitting = self.admin.patch(self.url, {"event_end": "2027-03-12T18:00+01:00"}, format="json")
        self.assertEqual(fitting.json()["warnings"], [])

    def test_moving_the_event_beyond_the_end(self) -> None:
        body = {"what": "event", "start": "2027-03-12T10:00+01:00", "end": "2027-03-12T23:00+01:00"}
        preview = self.admin.post(f"{self.url}/reschedule/preview", body, format="json").json()
        self.assertEqual(preview["outcome"]["warnings"], [WARNING])
        response = self.admin.post(f"{self.url}/reschedule", body, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["warnings"], [WARNING])
        inside = {"what": "event", "start": "2027-03-12T10:00+01:00", "end": "2027-03-12T16:00+01:00"}
        self.assertEqual(self.admin.post(f"{self.url}/reschedule", inside, format="json").json()["warnings"], [])

    def test_moving_the_rental_period_shorter(self) -> None:
        body = {
            "what": "period",
            "start": "2027-03-10T08:00+01:00",
            "end": "2027-03-11T20:00+01:00",
            "with_schedule": False,
        }
        response = self.admin.post(f"{self.url}/reschedule", body, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.json()["warnings"], [WARNING]
        )  # the event ends at 23:00, the material is back at 20:00


class EventEndMoveDialogTests(UiTestCase):
    """Dragging the event: the confirmation says it, and so does what was done."""

    def test_dialog_and_done(self) -> None:
        project = make_project(
            "Stadtfest", start=at(10, 8), end=at(12, 18), event_start=at(11, 18), event_end=at(11, 23)
        )
        url = reverse("schedule:move", args=[project.pk])
        query = {"what": "event", "start": "2027-03-12T10:00", "end": "2027-03-12T23:00"}
        page = self.assert_ok(self.htmx("get", url, query))
        self.assertIn(WARNING, page)
        done = self.assert_ok(self.htmx("post", url + "?what=event", {**query}))
        self.assertIn(WARNING, done)
