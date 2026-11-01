# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages for the crew: per phase and "Zeitplanung" (PRJ-080), per day (PER-029), the price overview by
phase and job function (PRJ-088), continuous hours (PRJ-073)."""

from __future__ import annotations

from decimal import Decimal

from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.personnel import services as personnel
from rentalars.projects import course, crew
from rentalars.projects.models import CrewBilling, CrewLine
from tests.helpers import ALL_RIGHTS, at, job_function, make_person, make_project, plan
from tests.ui.base import UiTestCase, form_data

D = Decimal


class CrewPerPhaseInThePlanningTests(UiTestCase):
    """PRJ-080 in the block "personnel" of the planning."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", start=at(12, 8), end=at(14, 20))
        self.setup = course.add_phase(self.project, kind="setup", start=at(12, 8), end=at(12, 16))
        self.show = course.add_phase(self.project, kind="event", title="Show", start=at(13, 18), end=at(13, 23))
        self.hand = job_function("Stagehand", price="28.00", guide="18.00")
        self.anna = make_person("Anna Becker", rates={"Stagehand": "20.00"})
        self.planning = reverse("projects:detail", args=[self.project.pk])
        self.add = reverse("projects:crew_add", args=[self.project.pk])

    def crew_block(self, text: str) -> str:
        start = text.index('id="planning-crew"')
        return text[start : text.index("</section>", start)]

    def test_the_add_form_offers_the_phases_with_their_periods(self) -> None:
        block = self.crew_block(self.assert_ok(self.client.get(self.planning)))
        self.assertIn('data-fills-period="start,end"', block)
        self.assertIn("Aufbau (Fr 12.03. 08:00 – 16:00)", block)
        self.assertIn('data-start="2027-03-13T18:00" data-end="2027-03-13T23:00"', block)

    def test_without_phases_there_is_no_field(self) -> None:
        """PRJ-094: the field is there, hidden: the page script shows it with “New phase …”."""
        empty = make_project("Jazznacht")
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[empty.pk])))
        block = self.crew_block(page)
        field = block[block.index("data-new-phase-field") - 20 : block.index('data-fills-period="start,end"')]
        self.assertIn("data-new-phase-field hidden", field)
        # Whoever only plans crew (and does not edit the project) gets no field at all.
        planner = self.browser_for("dora", "Personaldisposition")
        page = self.assert_ok(planner.get(reverse("projects:detail", args=[empty.pk])))
        self.assertNotIn("data-fills-period", self.crew_block(page))

    def test_a_phase_chosen_without_the_script_brings_its_period(self) -> None:
        """The page script fills in the period; without it, the untouched period of the project gives way."""
        page = self.client.get(self.planning)
        answer = self.htmx(
            "post",
            self.add,
            form_data(page, containing="job_function", job_function=self.hand.pk, phase=self.show.pk, count="2"),
        )
        block = self.crew_block(self.assert_ok(answer))
        lines = list(CrewLine.objects.all())
        self.assertEqual(len(lines), 2)
        self.assertTrue(
            all((line.phase, line.start, line.end) == (self.show, at(13, 18), at(13, 23)) for line in lines)
        )
        self.assertIn("Phase: Show", block)

    def test_a_period_typed_in_stays(self) -> None:
        page = self.client.get(self.planning)
        self.htmx(
            "post",
            self.add,
            form_data(
                page,
                containing="job_function",
                job_function=self.hand.pk,
                phase=self.setup.pk,
                start="2027-03-12T10:00",
                end="2027-03-12T14:00",
            ),
        )
        line = CrewLine.objects.get()
        self.assertEqual(
            (line.phase, line.start, line.end, line.planned_hours), (self.setup, at(12, 10), at(12, 14), D("4.00"))
        )

    def test_the_dialog_changes_the_phase_and_with_it_the_period(self) -> None:
        line = plan(self.project, self.hand, self.anna)
        url = reverse("projects:crew_edit", args=[self.project.pk, line.pk])
        dialog = self.htmx("get", url)
        self.assertIn('name="phase"', self.assert_ok(dialog))
        self.assertIn('name="days"', dialog.content.decode())
        self.assertIn('name="daily_rate"', dialog.content.decode())
        self.assertEqual(self.htmx("post", url, form_data(dialog, phase=self.setup.pk)).status_code, 200)
        line.refresh_from_db()
        self.assertEqual(
            (line.phase, line.start, line.end, line.planned_hours), (self.setup, at(12, 8), at(12, 16), D("8.00"))
        )


class PerDayInThePlanningTests(UiTestCase):
    """PER-029: a crew line per day in the planning and the deployment view."""

    def test_days_price_and_day_rate_are_shown(self) -> None:
        project = make_project("Stadtfest", start=at(12, 8), end=at(13, 20))
        sound = job_function("Tontechnik", price="40.00")
        anna = make_person("Anna Becker", user=self.admin_user)
        personnel.set_rate(anna, sound, D("35.00"), daily_rate=D("280.00"))
        line = plan(project, sound, anna, billing=CrewBilling.DAY, unit_price=D("400.00"))
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[project.pk])))
        block = page[page.index('id="planning-crew"') :]
        for shown in ("je Tag", "2 Tage", "für 2 Tage", "800,00", "560,00", "280,00 € / Tag", "36"):
            self.assertIn(shown, block)

        url = reverse("projects:crew_edit", args=[project.pk, line.pk])
        dialog = self.htmx("get", url)
        self.assertIn("jetzt 2", self.assert_ok(dialog))
        self.htmx("post", url, form_data(dialog, days="3"))
        line.refresh_from_db()
        self.assertEqual(line.days, 3)

        deployment = self.assert_ok(self.client.get(reverse("projects:deployment", args=[project.pk])))
        self.assertIn("Mein Tagessatz hier: 280,00", deployment)


class SchedulePageTests(UiTestCase):
    """PRJ-080: the page "Zeitplanung" lists per phase who works."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", start=at(12, 8), end=at(14, 20))
        self.setup = course.add_phase(self.project, kind="setup", start=at(12, 8), end=at(12, 16))
        self.show = course.add_phase(self.project, kind="event", title="Show", start=at(13, 18), end=at(13, 23))
        self.hand = job_function("Stagehand", price="28.00")
        self.anna = make_person("Anna Becker", rates={"Stagehand": "20.00"})
        self.page = reverse("projects:course", args=[self.project.pk])

    def phase_part(self, text: str, phase: object) -> str:
        start = text.index(f'data-phase="{phase.pk}"')
        return text[start : text.index("</tbody>", start)]

    def test_the_tab_is_called_time_planning(self) -> None:
        page = self.assert_ok(self.client.get(self.page))
        self.assertIn("<title>Zeitplanung", page)
        tabs = page[page.index('class="tabs') :]
        self.assertIn("Zeitplanung", tabs[: tabs.index("</nav>")])
        self.assertNotIn("Ablauf", page)

    def test_each_phase_lists_its_crew(self) -> None:
        plan(self.project, self.hand, self.anna, phase=self.setup)
        plan(self.project, self.hand, phase=self.setup, start=at(12, 12), end=at(12, 16))
        plan(self.project, self.hand, start=at(14, 8), end=at(14, 12))
        page = self.assert_ok(self.client.get(self.page))
        setup = self.phase_part(page, self.setup)
        self.assertIn("Anna Becker", setup)
        self.assertIn("offen", setup)
        self.assertIn("8 Std.", setup)
        # The period only where it differs from the phase's.
        self.assertEqual(setup.count("Fr 12.03. 12:00 – Fr 12.03. 16:00"), 1)
        self.assertNotIn("Fr 12.03. 08:00 – Fr 12.03. 16:00</span>", setup)
        self.assertIn("Für diese Phase ist noch niemand geplant.", self.phase_part(page, self.show))
        without = page[page.index('id="crew-without-phase"') :]
        self.assertIn("Personal ohne Phase", without)
        self.assertIn("So 14.03. 08:00 – So 14.03. 12:00", without)
        self.assertIn(reverse("projects:phase_crew_add", args=[self.project.pk, self.show.pk]), page)

    def test_who_may_not_plan_sees_the_crew_without_the_button(self) -> None:
        plan(self.project, self.hand, self.anna, phase=self.setup)
        warehouse = self.browser_for("luka", "Lager")
        page = self.assert_ok(warehouse.get(self.page))
        self.assertIn("Anna Becker", page)
        self.assertNotIn("Personal für diese Phase", page)
        url = reverse("projects:phase_crew_add", args=[self.project.pk, self.setup.pk])
        self.assertEqual(warehouse.get(url).status_code, 403)

    def test_plan_personnel_for_a_phase_in_the_dialog(self) -> None:
        # PRJ-120: first the job function with its places, then the person of each place; every line
        # gets the period of the phase – the fields "from" and "until" of the dialog are gone, as is "person" above.
        url = reverse("projects:phase_crew_add", args=[self.project.pk, self.show.pk])
        dialog = self.htmx("get", url)
        text = self.assert_ok(dialog)
        self.assertIn("Personal für Show", text)
        self.assertIn("Sa 13.03. 18:00 – Sa 13.03. 23:00", text)
        data = form_data(dialog, function_0=self.hand.pk, places_0="1", person_0_0=self.anna.pk, save="1")
        answer = self.htmx("post", url, data)
        self.assertEqual((answer.status_code, answer["HX-Redirect"]), (204, f"{self.page}#phases"))
        line = CrewLine.objects.get()
        self.assertEqual(
            (line.phase, line.person, line.start, line.end), (self.show, self.anna, at(13, 18), at(13, 23))
        )

    def test_without_the_script_the_dialog_is_a_page(self) -> None:
        # PRJ-120: rows "job function + places"; "Einplanen" without people plans open places.
        url = reverse("projects:phase_crew_add", args=[self.project.pk, self.setup.pk])
        page = self.client.get(url)
        self.assertIn("<h1>Aufbau</h1>", self.assert_ok(page))
        response = self.client.post(
            url, form_data(page, containing="function_0", function_0=self.hand.pk, places_0="3", save="1")
        )
        self.assertRedirects(response, f"{self.page}#phases", fetch_redirect_response=False)
        self.assertEqual(CrewLine.objects.filter(phase=self.setup, start=at(12, 8), end=at(12, 16)).count(), 3)
        empty = self.client.post(url, form_data(page, containing="function_0", function_0="", save="1"))
        self.assertIn("Wähle mindestens eine Funktion.", self.assert_ok(empty))

    def test_moving_a_phase_asks_and_moves_its_crew(self) -> None:
        whole = plan(self.project, self.hand, self.anna, phase=self.setup)
        url = reverse("projects:phase_edit", args=[self.project.pk, self.setup.pk])
        form = self.client.get(url)
        text = self.assert_ok(form)
        self.assertIn("Crew dieser Phase mitverschieben", text)
        self.assertIn("1 Personalposition gehört zu dieser Phase.", text)
        response = self.client.post(url, form_data(form, start="2027-03-12T10:00", end="2027-03-12T18:00"), follow=True)
        self.assertIn("1 Personalposition wurde mit der Phase verschoben.", self.messages_of(response))
        whole.refresh_from_db()
        self.assertEqual((whole.start, whole.end), (at(12, 10), at(12, 18)))

        # Unticked, the crew stays.
        self.client.post(
            url, form_data(self.client.get(url), start="2027-03-12T12:00", end="2027-03-12T20:00", move_crew=None)
        )
        whole.refresh_from_db()
        self.assertEqual((whole.start, whole.end), (at(12, 10), at(12, 18)))

    def test_a_phase_without_crew_does_not_ask(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:phase_edit", args=[self.project.pk, self.show.pk])))
        self.assertNotIn("mitverschieben", page)

    def test_a_moved_line_that_clashes_is_reported(self) -> None:
        other = make_project("Jazznacht")
        plan(other, self.hand, self.anna, start=at(13, 10), end=at(13, 12))
        plan(self.project, self.hand, self.anna, phase=self.setup)
        url = reverse("projects:phase_edit", args=[self.project.pk, self.setup.pk])
        response = self.client.post(
            url, form_data(self.client.get(url), start="2027-03-13T08:00", end="2027-03-13T16:00"), follow=True
        )
        self.assertTrue(
            any(f"Projekt {other.number}" in message for message in self.messages_of(response))
        )  # By number only – the reader may not open the other project (AUT-016)


class PriceOverviewByPhaseTests(UiTestCase):
    """PRJ-088: the price overview breaks the personnel down by phase and job function."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", start=at(12, 8), end=at(14, 20))
        self.setup = course.add_phase(self.project, kind="setup", start=at(12, 8), end=at(12, 16))
        self.hand = job_function("Stagehand", price="28.00", guide="18.00")
        self.sound = job_function("Tontechnik", price="40.00", guide="30.00")
        crew.add_crew_lines(self.project, rights=ALL_RIGHTS, job_function=self.hand, count=2, phase=self.setup)
        plan(self.project, self.sound, start=at(13, 18), end=at(13, 23))
        self.url = reverse("projects:price_overview", args=[self.project.pk])

    def test_the_switch_and_the_breakdown(self) -> None:
        plain = self.assert_ok(self.client.get(self.url))
        self.assertIn("?detail=lines&amp;crew=phases", plain)
        self.assertNotIn("crew-by-phase", plain)
        page = self.assert_ok(self.client.get(self.url + "?crew=phases"))
        table = page[page.index("crew-by-phase") :]
        table = table[: table.index("</table>")]
        for shown in (
            "Aufbau",
            "Stagehand",
            "16 Std.",
            "448,00",
            "Zwischensumme Aufbau",
            "Ohne Phase",
            "Tontechnik",
            "200,00",
        ):
            self.assertIn(shown, table)
        # The administrator may see personnel costs: 16 h × 18.00 and what remains.
        self.assertIn("288,00", table)
        self.assertIn("160,00", table)
        # The switches keep each other.
        self.assertIn("?detail=groups&amp;crew=phases", page)
        self.assertIn("prices/pdf/?detail=lines&amp;crew=phases", page)
        groups = self.assert_ok(self.client.get(self.url + "?detail=groups&crew=phases"))
        self.assertIn("crew-by-phase", groups)
        self.assertIn("Zwischensumme Aufbau", groups)

    def test_costs_need_their_right(self) -> None:
        Role.objects.create(name="Vertrieb", module_levels={"projects": 2}, special_rights=["prices"])
        sales = self.browser_for("vera", "Vertrieb")
        table = self.assert_ok(sales.get(self.url + "?crew=phases"))
        table = table[table.index("crew-by-phase") :]
        table = table[: table.index("</table>")]
        self.assertIn("448,00", table)
        self.assertNotIn("288,00", table)
        self.assertNotIn("Deckungsbeitrag", table)

    def test_csv_and_pdf(self) -> None:
        csv = self.client.get(reverse("projects:price_overview_csv", args=[self.project.pk]) + "?crew=phases")
        text = csv.content.decode("utf-8-sig")
        self.assertIn("Personal › Aufbau;;2 × Stagehand;16;Std.;;;;;448", text)
        self.assertIn("Personal › Aufbau;;Zwischensumme;;;;;;;448", text)
        self.assertIn("Personal › Ohne Phase;;1 × Tontechnik;5;Std.;;;;;200", text)
        groups = self.client.get(
            reverse("projects:price_overview_csv", args=[self.project.pk]) + "?detail=groups&crew=phases"
        )
        self.assertIn("Personal › Aufbau;2 × Stagehand, 16 Std.;448", groups.content.decode("utf-8-sig"))
        self.assertNotIn("288", text)  # never costs in the files

        from rentalars.projects.price_pdf import render_price_overview_html

        html = render_price_overview_html(self.project, with_lines=True, crew_by_phase=True)
        self.assertIn("2 × Stagehand, 16 Std.", html)
        self.assertIn("crew-phase", html)
        pdf = self.client.get(reverse("projects:price_overview_pdf", args=[self.project.pk]) + "?crew=phases")
        self.assertEqual((pdf.status_code, pdf["Content-Type"]), (200, "application/pdf"))
