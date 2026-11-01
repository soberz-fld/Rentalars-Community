# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "project", in the pages: show files in the empty text of the documents (PRJ-089), the customer of
a service case (PRJ-090), the crew on the timeline of Zeitplanung as in the personnel plan (VFG-035), crew lines of a
phase changed on Zeitplanung (PRJ-110), trips changed, removed and added (PRJ-111), My area → Meine Einsätze
(UIX-043)."""

from __future__ import annotations

import datetime

from django.urls import reverse

from rentalars.core.models import CompanyProfile
from rentalars.mail.models import Untagged
from rentalars.personnel.models import Absence, AvailabilityMark
from rentalars.projects import course, service_cases
from rentalars.projects.models import CrewLine, PhaseKind, Project, ProjectStatus, RequestStatus, TripAdjustment
from tests.helpers import at, clock, make_customer, make_person, make_project, make_user, plan
from tests.mailbox import FakeMailbox, configure_mailbox, mailboxes, make_mail
from tests.ui.base import UiTestCase, form_data
from tests.ui.test_accessibility import problems_of
from tests.unit.test_081_mail import alias

WAREHOUSE = "Hafenstraße 1, 12345 Musterstadt"


class DocumentsEmptyTextTests(UiTestCase):
    """PRJ-089: the empty text of the files names the show files."""

    def test_project_and_service_case(self) -> None:
        project = make_project()
        page = self.assert_ok(self.client.get(reverse("documents:list", args=[project])))
        self.assertIn("Bühnenpläne, Rider, Showfiles, Verträge – alles zum Projekt an einem Ort.", page)
        case = service_cases.create_case(name="Spot flackert", customer=make_customer())
        page = self.assert_ok(self.client.get(reverse("documents:list", args=[case])))
        self.assertIn("Bühnenpläne, Rider, Showfiles, Verträge – alles zum Servicefall an einem Ort.", page)


class ServiceCaseCustomerPageTests(UiTestCase):
    """PRJ-090: the customer is required in the form; older cases ask for it when edited."""

    def test_a_new_case_needs_a_customer_the_description_not(self) -> None:
        url = reverse("projects:case_create")
        data = form_data(self.client.get(url), "name", name="Spot flackert", notes="")
        page = self.assert_ok(self.client.post(url, data))
        self.assertIn("Wähle den Kunden des Servicefalls.", page)
        self.assertFalse(Project.objects.filter(kind="service_case").exists())
        data["customer"] = str(make_customer().pk)
        response = self.client.post(url, data, follow=True)
        case = Project.objects.get(kind="service_case")
        self.assertEqual(response.redirect_chain[-1][0], reverse("projects:case_detail", args=[case]))

    def test_an_older_case_shows_the_missing_customer_and_asks_for_it(self) -> None:
        case = service_cases.create_case(name="Kabel defekt", case_contact="Herr Meier")
        page = self.assert_ok(self.client.get(reverse("projects:case_detail", args=[case])))
        self.assertIn('<span class="badge yellow">Kunde fehlt</span>', page)
        edit = reverse("projects:case_edit", args=[case])
        self.assertIn(f'<a href="{edit}">Kunden wählen</a>', page)
        self.assertEqual(problems_of(page), [])
        # The status changes without customer.
        self.client.post(reverse("projects:case_status", args=[case]), {"case_status": "in_progress"})
        case.refresh_from_db()
        self.assertEqual(case.case_status, "in_progress")
        data = form_data(self.client.get(edit), "name", notes="Stecker getauscht")
        self.assertIn("Wähle den Kunden des Servicefalls.", self.assert_ok(self.client.post(edit, data)))
        data["customer"] = str(make_customer().pk)
        self.client.post(edit, data)
        case.refresh_from_db()
        self.assertEqual(case.notes, "Stecker getauscht")
        self.assertNotIn("Kunde fehlt", self.assert_ok(self.client.get(reverse("projects:case_detail", args=[case]))))

    def test_a_reader_sees_that_the_customer_is_missing_but_no_link(self) -> None:
        case = service_cases.create_case(name="Kabel defekt")
        page = self.assert_ok(self.browser_for("lea", "Nur-Lesen").get(reverse("projects:case_detail", args=[case])))
        self.assertIn("Kunde fehlt", page)
        self.assertNotIn("Kunden wählen", page)

    def test_a_case_made_from_a_mail_without_known_customer_is_still_made(self) -> None:
        """PRJ-090, EML-047 (decided): never an inquiry instead – the page says the customer is missing."""
        box = configure_mailbox(process_untagged=True)
        alias(box, "support@verleih.example", untagged=Untagged.SERVICE_CASE)
        mail = make_mail(
            "Beamer flackert",
            sender="Unbekannt <neu@example.org>",
            to="support@verleih.example",
            date=clock() + datetime.timedelta(hours=1),
        )
        with mailboxes({"projekte@verleih.example": FakeMailbox(mail)}), self.captureOnCommitCallbacks(execute=True):
            from rentalars.mail.fetching import fetch_mail

            fetch_mail(force=True)
        case = Project.objects.get(kind="service_case")
        self.assertIsNone(case.customer_id)
        self.assertEqual(case.case_contact, "Unbekannt <neu@example.org>")
        self.assertIn("Kunde fehlt", self.assert_ok(self.client.get(reverse("projects:case_detail", args=[case]))))


class CourseCase(UiTestCase):
    """A project with a setup phase: Anna planned twice at the same time, an open place, Ben on holiday."""

    def setUp(self) -> None:
        super().setUp()
        profile = CompanyProfile.load()
        profile.warehouse_address = WAREHOUSE
        profile.save()
        self.project = make_project(start=at(10, 8), end=at(12, 20), venue="Stadthalle, Marktplatz 1, Musterstadt")
        self.setup = course.add_phase(self.project, kind=PhaseKind.SETUP, start=at(10, 8), end=at(10, 16))
        self.anna = make_person("Anna Becker", rates={"Stagehand": "20.00"})
        self.ben = make_person("Ben Wolf", rates={"Stagehand": "20.00"})
        self.line = plan(self.project, "Stagehand", self.anna, phase=self.setup)
        plan(
            make_project("Messe", start=at(10, 8), end=at(10, 20)),
            "Stagehand",
            self.anna,
            start=at(10, 12),
            end=at(10, 18),
        )
        self.open = plan(self.project, "Stagehand", None, phase=self.setup)
        AvailabilityMark.objects.create(person=self.anna, start=at(10, 6), end=at(10, 8), state="available")
        Absence.objects.create(person=self.ben, kind="vacation", start=at(10), end=at(11))
        self.url = reverse("projects:course", args=[self.project])


class CourseCrewTimelineTests(CourseCase):
    """VFG-035: the crew on the timeline of Zeitplanung as in the personnel plan."""

    def test_colours_conflicts_availability_and_legend(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        timeline = page[page.index('class="course-timeline"') : page.index('id="phases"')]
        self.assertIn('class="tl-bar crew status-confirmed is-conflict"', timeline)
        self.assertIn("Anna Becker · Stagehand · Mi 10.03., 8:00 Uhr bis 16:00 Uhr · Konflikt", timeline)
        self.assertIn('<span class="plan-warning" title="Einsätze überschneiden sich">', timeline)
        self.assertIn('class="tl-row tl-avail"', timeline)
        self.assertIn('class="tl-bar availability is-available"', timeline)
        self.assertIn("<strong>Verfügbarkeit:</strong>", timeline)
        for label in ("fest", "Option", "Projekt-Anfrage", "angefragt", "Konflikt", "abgesagt", "offen"):
            self.assertIn(f">{label}</span>", timeline)
        self.assertIn("Verfügbarkeiten sind schraffiert.", timeline)
        self.assertEqual(problems_of(page), [])

    def test_without_the_right_to_read_the_personnel(self) -> None:
        """The conflict shows, as the warnings of the planning do; the availability needs the personnel."""
        page = self.assert_ok(self.browser_for("luka", "Lager").get(self.url))
        timeline = page[page.index('class="course-timeline"') : page.index('id="phases"')]
        self.assertIn("is-conflict", timeline)
        self.assertNotIn("tl-avail", timeline)
        self.assertNotIn("<strong>Verfügbarkeit:</strong>", timeline)

    def test_queries_bounded(self) -> None:
        """VFG-035, PRJ-110, PRJ-111: a fixed number of queries, whatever the number of people."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self.client.get(self.url)
        with CaptureQueriesContext(connection) as few:
            self.client.get(self.url)
        for number in range(6):
            person = make_person(f"Person {number}", rates={"Stagehand": "20.00"})
            plan(self.project, "Stagehand", person, phase=self.setup)
            Absence.objects.create(person=person, kind="vacation", start=at(10), end=at(11))
        with CaptureQueriesContext(connection) as many:
            self.client.get(self.url)
        self.assertEqual(len(many), len(few))


class PhaseCrewOnCourseTests(CourseCase):
    """PRJ-110: the crew of a phase changed on Zeitplanung – with the crew dialog of the planning."""

    def edit_url(self, line: CrewLine) -> str:
        return reverse("projects:crew_edit", args=[self.project, line.pk]) + "?from=course"

    def test_the_buttons_of_a_line(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        phases = page[page.index('id="phases"') :]
        self.assertIn(f'hx-get="{self.edit_url(self.open)}"', phases)
        self.assertIn('aria-label="Offenen Platz Stagehand besetzen"', phases)
        self.assertIn('aria-label="Stagehand – Anna Becker ändern"', phases)
        self.assertIn(reverse("projects:crew_request", args=[self.project, self.line.pk]), phases)
        self.assertIn(reverse("projects:crew_delete", args=[self.project, self.line.pk]), phases)
        # The warning of the crew dialog (PRJ-022) – with the number only: the reader may not open it.
        self.assertIn("Auch in Projekt 2027-0002 eingeplant", phases)
        self.assertEqual(problems_of(page), [])
        # Reading the project is not planning it.
        reader = self.assert_ok(self.browser_for("luka", "Lager").get(self.url))
        self.assertNotIn(self.edit_url(self.open), reader)
        self.assertNotIn("crew_request", reader)

    def test_fill_an_open_place_with_a_person(self) -> None:
        url = self.edit_url(self.open)
        dialog = self.htmx("get", url)
        self.assertEqual(dialog.status_code, 200)
        self.assertIn('data-href="/projects/', dialog.content.decode())
        data = form_data(dialog, "person", person=str(self.ben.pk))
        response = self.client.post(
            url, data, HTTP_HX_REQUEST="true", HTTP_HX_CURRENT_URL=f"http://testserver{self.url}"
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Refresh"], "true")
        self.open.refresh_from_db()
        self.assertEqual(self.open.person, self.ben)
        page = self.client.get(self.url)
        messages = self.messages_of(page)
        self.assertIn("Personalposition gespeichert.", messages)
        self.assertTrue(any(text.startswith("Ben Wolf: Abwesend") for text in messages))  # the availability check
        self.assertIn("anfragen", self.assert_ok(page)[page.content.decode().index('id="phases"') :])

    def test_without_the_page_script(self) -> None:
        url = self.edit_url(self.line)
        page = self.assert_ok(self.client.get(url))
        self.assertIn("<h1>Stagehand</h1>", page)
        self.assertIn(f'action="{url.replace("&", "&amp;")}"', page)
        data = form_data(self.client.get(url), "planned_hours", start="2027-03-10T09:00", end="2027-03-10T15:00")
        response = self.client.post(url, data)
        self.assertRedirects(response, self.url + "#phases", fetch_redirect_response=False)
        self.line.refresh_from_db()
        self.assertEqual((self.line.start, self.line.end), (at(10, 9), at(10, 15)))

    def test_the_page_of_its_own_leads_back_to_zeitplanung(self) -> None:
        """Review: opened directly, saving leads to Zeitplanung – with the page script too; "Back" as well."""
        url = self.edit_url(self.line)
        page = self.assert_ok(self.client.get(url))  # no trail: opened directly
        self.assertIn(f'class="back-link no-print" href="{self.url}#phases"', page)
        data = form_data(self.client.get(url), "planned_hours", planned_hours="6")
        on_its_own = self.client.post(url, data, HTTP_HX_REQUEST="true", HTTP_HX_CURRENT_URL=f"http://testserver{url}")
        self.assertEqual((on_its_own.status_code, on_its_own["HX-Redirect"]), (204, self.url + "#phases"))
        self.assertNotIn("HX-Refresh", on_its_own)

    def test_ask_answer_and_remove_from_course(self) -> None:
        ask = reverse("projects:crew_request", args=[self.project, self.line.pk])
        response = self.client.post(ask, {"from": "course"}, follow=True)
        self.assertEqual(response.redirect_chain[-1][0], self.url + "#phases")
        self.assertTrue(any("Anna Becker" in text and "angefragt" in text for text in self.messages_of(response)))
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.REQUESTED)
        page = self.assert_ok(response)
        self.assertIn("eintragen: zugesagt", page)
        answer = reverse("projects:crew_answer", args=[self.project, self.line.pk])
        self.client.post(answer, {"answer": "accept", "next": self.url + "#phases"})
        self.line.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.ACCEPTED)
        delete = reverse("projects:crew_delete", args=[self.project, self.open.pk])
        response = self.client.post(delete, {"from": "course"}, follow=True)
        self.assertEqual(response.redirect_chain[-1][0], self.url + "#phases")
        self.assertIn("Personalposition entfernt.", self.messages_of(response))
        self.assertFalse(CrewLine.objects.filter(pk=self.open.pk).exists())

    def test_the_planning_answers_as_before(self) -> None:
        """Without ``from=course`` the dialog answers with the planning block."""
        url = reverse("projects:crew_edit", args=[self.project, self.line.pk])
        data = form_data(self.htmx("get", url), "planned_hours", planned_hours="5")
        response = self.htmx("post", url, data)
        self.assertEqual(response["HX-Retarget"], "#planning")


class TripPageTests(CourseCase):
    """PRJ-111: the trips on Zeitplanung changed, removed, brought back and added."""

    def setUp(self) -> None:
        super().setUp()
        self.key = f"to_venue-{self.setup.pk}"

    def test_change_a_trip_in_the_dialog(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        trips = page[page.index('id="trips"') :]
        edit = reverse("projects:trip_edit", args=[self.project, self.key])
        self.assertIn(f'hx-get="{edit}"', trips)
        self.assertIn(reverse("projects:trip_add", args=[self.project]), trips)
        dialog = self.htmx("get", edit)
        text = dialog.content.decode()
        self.assertIn("Fahrt „Fahrt zum Aufbau“ anpassen", text)
        self.assertIn(WAREHOUSE, text)
        data = form_data(dialog, "destination", destination="Stadthalle, Lieferzufahrt Nord", note="Rampe hinten")
        response = self.client.post(
            edit, data, HTTP_HX_REQUEST="true", HTTP_HX_CURRENT_URL=f"http://testserver{self.url}"
        )
        self.assertEqual((response.status_code, response["HX-Refresh"]), (204, "true"))
        page = self.assert_ok(self.client.get(self.url))
        trips = page[page.index('id="trips"') :]
        self.assertIn('<span class="badge yellow">angepasst</span>', trips)
        self.assertIn("Rampe hinten", trips)
        self.assertIn("Stadthalle%2C%20Lieferzufahrt%20Nord", trips)  # the route link follows
        self.assertIn(">Zurücksetzen</button>", trips)
        self.assertEqual(problems_of(page), [])
        # The drivers see the note in the overview, without buttons.
        overview = self.assert_ok(self.client.get(reverse("projects:deployment", args=[self.project])))
        self.assertIn("Rampe hinten", overview)
        self.assertNotIn(edit, overview)
        response = self.client.post(reverse("projects:trip_reset", args=[self.project, self.key]), follow=True)
        self.assertIn(
            "Fahrt „Fahrt zum Aufbau“ ist wieder so, wie Rentalars sie ermittelt.", self.messages_of(response)
        )
        self.assertFalse(TripAdjustment.objects.exists())

    def test_the_page_of_its_own_leads_back_to_zeitplanung(self) -> None:
        """Review: "Back" on the page of a trip leads to the trips of the project, also opened directly."""
        edit = reverse("projects:trip_edit", args=[self.project, self.key])
        page = self.assert_ok(self.client.get(edit))
        self.assertIn(f'class="back-link no-print" href="{self.url}#trips"', page)
        self.assertIn(f'class="icon-btn topbar-back" href="{self.url}#trips"', page)
        data = form_data(self.client.get(edit), "destination", note="Rampe")
        response = self.client.post(edit, data, HTTP_HX_REQUEST="true", HTTP_HX_CURRENT_URL=f"http://testserver{edit}")
        self.assertEqual(response["HX-Redirect"], self.url + "#trips")

    def test_remove_and_bring_back(self) -> None:
        remove = reverse("projects:trip_remove", args=[self.project, self.key])
        response = self.client.post(remove, follow=True)
        self.assertEqual(response.redirect_chain[-1][0], self.url + "#trips")
        self.assertIn("Fahrt „Fahrt zum Aufbau“ entfernt.", self.messages_of(response))
        page = self.assert_ok(response)
        removed = page[page.index('class="panel-body removed-trips"') :]
        self.assertIn("Entfernte Fahrten", removed)
        self.assertIn(">Zurückholen</button>", removed)
        self.client.post(reverse("projects:trip_reset", args=[self.project, self.key]))
        self.assertNotIn("Entfernte Fahrten", self.assert_ok(self.client.get(self.url)))

    def test_add_a_trip_of_ones_own_without_the_page_script(self) -> None:
        add = reverse("projects:trip_add", args=[self.project])
        page = self.assert_ok(self.client.get(add))
        self.assertIn("<h1>Neue Fahrt</h1>", page)
        data = form_data(self.client.get(add), "destination", title="Nachlieferung", start="2027-03-11T09:00")
        self.assertIn("Gib an, wo die Fahrt beginnt.", self.assert_ok(self.client.post(add, data)))
        data.update(origin=WAREHOUSE, destination="Stadthalle", stops="Baumarkt\nGetränke")
        self.assertRedirects(self.client.post(add, data), self.url + "#trips", fetch_redirect_response=False)
        own = TripAdjustment.objects.get()
        self.assertEqual((own.trip_key, own.stops, own.start), ("", ["Baumarkt", "Getränke"], at(11, 9)))
        trips = self.assert_ok(self.client.get(self.url))
        self.assertIn('<span class="badge">eigene Fahrt</span>', trips)
        self.client.post(reverse("projects:trip_remove", args=[self.project, f"own-{own.pk}"]))
        self.assertFalse(TripAdjustment.objects.exists())

    def test_only_who_may_change_the_project(self) -> None:
        reader = self.browser_for("luka", "Lager")
        page = self.assert_ok(reader.get(self.url))
        self.assertNotIn("Fahrt hinzufügen", page)
        self.assertEqual(reader.get(reverse("projects:trip_edit", args=[self.project, self.key])).status_code, 403)
        self.assertEqual(reader.post(reverse("projects:trip_remove", args=[self.project, self.key])).status_code, 403)
        self.project.status = ProjectStatus.CLOSED
        self.project.save()
        self.assertNotIn("Fahrt hinzufügen", self.assert_ok(self.client.get(self.url)))
        response = self.client.post(reverse("projects:trip_remove", args=[self.project, self.key]), follow=True)
        self.assertIn(
            "Dieses Projekt ist abgeschlossen. Öffne es wieder, bevor du etwas änderst.", self.messages_of(response)
        )


class MyDeploymentsPageTests(UiTestCase):
    """UIX-043: My area → Meine Einsätze, the first tab; My area opens with it."""

    def setUp(self) -> None:
        super().setUp()
        self.user = make_user("carla", roles=("Crew",))
        from rentalars.personnel.models import Person

        self.person = make_person("Carla Brandt", user=self.user, rates={"Stagehand": "20.00"})
        self.assertEqual(Person.objects.get(user=self.user), self.person)
        self.crew = self.browser_of(self.user)
        self.festival = make_project("Stadtfest")
        self.line = plan(self.festival, "Stagehand", self.person, meeting_point="Rampe")
        option = make_project("Hochzeit", start=at(20), end=at(21), status=ProjectStatus.OPTION)
        self.option = plan(option, "Stagehand", self.person)
        plan(make_project("Damals", start=at(1, month=2), end=at(2, month=2)), "Stagehand", self.person)
        self.url = reverse("projects:my_deployments")

    def test_the_first_tab_and_where_my_area_opens(self) -> None:
        home = self.assert_ok(self.crew.get("/"))
        self.assertIn(f'href="{self.url}"', home.split('<ul class="nav">')[1].split("</ul>")[0])
        self.assertIn(f'<a class="btn secondary small" href="{self.url}">Alle meine Einsätze</a>', home)
        page = self.assert_ok(self.crew.get(self.url))
        bar = page.split('<nav class="tabs"', 1)[1].split("</nav>", 1)[0]
        self.assertIn(f'<a href="{self.url}" aria-current="page">Meine Einsätze</a>', bar)
        self.assertLess(bar.index("Meine Einsätze"), bar.index("Verfügbarkeit"))
        self.assertIn("Stadtfest", page)
        self.assertIn("Rampe", page)
        self.assertIn(reverse("projects:deployment", args=[self.festival.pk]), page)
        damals = Project.objects.get(name="Damals")
        self.assertNotIn(reverse("projects:deployment", args=[damals.pk]), page)  # coming deployments by default
        self.assertEqual(problems_of(page), [])

    def test_filters_sorting_groups_and_csv(self) -> None:
        past = self.assert_ok(self.crew.get(self.url, {"period": "past"}))
        self.assertIn(reverse("projects:deployment", args=[Project.objects.get(name="Damals").pk]), past)
        self.assertNotIn(reverse("projects:deployment", args=[self.festival.pk]), past)
        option = self.assert_ok(self.crew.get(self.url, {"state": "option"}))
        self.assertIn(reverse("projects:deployment", args=[self.option.project_id]), option)
        self.assertNotIn(reverse("projects:deployment", args=[self.festival.pk]), option)
        project = self.assert_ok(self.crew.get(self.url, {"project": str(self.festival.pk)}))
        self.assertNotIn(reverse("projects:deployment", args=[self.option.project_id]), project)
        none = self.assert_ok(self.crew.get(self.url, {"request": "declined"}))
        self.assertIn("Kein Einsatz passt zu den Filtern.", none)
        # Every heading sorts; the state as fest, Option, Anfrage.
        for key in ("project", "function", "start", "end", "venue", "meeting_point", "state", "request"):
            with self.subTest(sort=key):
                self.assert_ok(self.crew.get(self.url, {"sort": f"-{key}"}))
        grouped = self.assert_ok(self.crew.get(self.url, {"group": "request", "sort": "state"}))
        table = grouped[grouped.index("<table") :]
        self.assertLess(table.index("Stadtfest"), table.index("Hochzeit"))
        csv = self.crew.get(self.url, {"format": "csv", "period": "all"})
        self.assertEqual(csv.status_code, 200)
        text = csv.content.decode("utf-8-sig")
        self.assertIn("Stadtfest", text)
        self.assertIn("Damals", text)

    def test_only_ones_own(self) -> None:
        other = make_person("Ole Neu", rates={"Stagehand": "20.00"})
        plan(make_project("Fremd"), "Stagehand", other)
        self.assertNotIn("Fremd", self.assert_ok(self.crew.get(self.url, {"period": "all"})))
