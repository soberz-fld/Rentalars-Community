# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "plan", in the pages: deployments dragged in the personnel plan and confirmed in the dialog (VFG-031),
exact times, hatching and conflicts in the personnel plan (VFG-032), hourly lines and the wider scroll range
(VFG-033), a time range marked in the week of the availability calendar (PER-039)."""

from __future__ import annotations

from urllib.parse import urlencode

from django.urls import reverse

from rentalars.personnel.models import AvailabilityMark
from rentalars.projects import course
from rentalars.projects.models import CrewLine, PhaseKind, Project, RequestStatus
from tests.helpers import at, make_person, make_project, make_user, plan
from tests.ui.base import UiTestCase
from tests.ui.test_accessibility import problems_of

PERSONNEL = "/schedule/personnel/"


def _move_url(project: Project, **query: object) -> str:
    return f"{reverse('schedule:move', args=[project.pk])}?{urlencode(query)}"


class PersonnelPlanPageTests(UiTestCase):
    """VFG-031, VFG-032, VFG-033 on Planung → Personalplan."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(start=at(10, 8), end=at(12, 18))
        self.anna = make_person("Anna Becker", rates={"Stagehand": "20.00"})
        self.line = plan(self.project, "Stagehand", self.anna, start=at(10, 9), end=at(10, 13, 30))
        AvailabilityMark.objects.create(person=self.anna, start=at(10, 12), end=at(10, 16), state="unavailable")

    def test_movable_deployments_for_an_editor(self) -> None:
        """VFG-031: the deployment bars carry what dragging needs, and the hint how to do it."""
        page = self.assert_ok(self.client.get(PERSONNEL, {"days": "4", "from": "2027-03-09"}))
        self.assertIn(f'data-tl-move="/schedule/move/{self.project.number}/?what=crew&amp;line={self.line.pk}"', page)
        self.assertIn(f'data-tl-key="crew-{self.line.pk}"', page)
        self.assertIn('data-tl-start="2027-03-10T09:00" data-tl-end="2027-03-10T13:30"', page)
        self.assertIn('<span class="tl-grip is-start" aria-hidden="true"></span>', page)
        self.assertIn('id="tl-move-hint"', page)
        # A click leads to the project (to its Überblick).
        self.assertIn(f'href="/projects/{self.project.number}/overview/" title="{self.project.number} Stagehand', page)
        self.assertEqual(problems_of(page), [])

    def test_nothing_moves_in_weeks_or_for_readers(self) -> None:
        weeks = self.assert_ok(self.client.get(PERSONNEL, {"weeks": "2", "from": "2027-03-08"}))
        self.assertNotIn("data-tl-move", weeks)
        self.assertNotIn("tl-move-hint", weeks)
        planner = self.browser_for("pia", "Personaldisposition")
        page = self.assert_ok(planner.get(PERSONNEL, {"days": "4", "from": "2027-03-09"}))
        self.assertIn("Anna Becker", page)
        self.assertNotIn("data-tl-move", page)  # the personnel plan, but no right to change projects

    def test_exact_times_conflicts_and_legend(self) -> None:
        """VFG-032: hover and hidden text with the exact times; the conflict filled red, named in the legend."""
        page = self.assert_ok(self.client.get(PERSONNEL, {"days": "4", "from": "2027-03-09"}))
        self.assertIn("Mi 10.03., 9:00 Uhr bis 13:30 Uhr · Konflikt", page)
        self.assertIn(
            'title="nicht verfügbar: Mi 10.03., 12:00 Uhr bis 16:00 Uhr · Konflikt"><span class="tl-text">nicht '
            'verfügbar</span><span class="visually-hidden">: Mi 10.03., 12:00 Uhr bis 16:00 Uhr · Konflikt</span>',
            page,
        )
        self.assertIn('class="tl-bar crew status-confirmed is-conflict"', page)
        self.assertIn('<span class="tl-bar legend crew status-confirmed is-conflict">Konflikt</span>', page)
        self.assertIn("Die betroffenen Einsätze sind rot ausgefüllt.", page)
        self.assertNotIn("rot umrandet", page)
        self.assertIn("Verfügbarkeiten sind schraffiert.", page)

    def test_hourly_lines_and_scroll_range(self) -> None:
        """VFG-033: the panel says how many days are in view; the grid holds five spans."""
        for path in (PERSONNEL, "/schedule/timeline/", f"/projects/{self.project.number}/course/"):
            with self.subTest(path=path):
                page = self.assert_ok(self.client.get(path, {"days": "4", "from": "2027-03-09"}))
                self.assertIn('data-hours="3" data-span-days="4"', page)
                self.assertIn('style="--cols: 160; --days: 20; --hours: 3; --spans: 5"', page)
                self.assertIn('data-tl-zoom data-focus="64" data-shift="32" data-columns="160"', page)


class MoveDialogOfADeploymentTests(UiTestCase):
    """VFG-031: the dialog of VFG-026 for a deployment: times, hours, asked again, warnings, the phase."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(start=at(10, 8), end=at(12, 18))
        self.phase = course.add_phase(self.project, kind=PhaseKind.SETUP, start=at(10, 14), end=at(10, 20))
        self.anna = make_person("Anna Becker", rates={"Stagehand": "20.00"})
        self.line = plan(self.project, "Stagehand", self.anna, phase=self.phase)
        CrewLine.objects.filter(pk=self.line.pk).update(
            request_status=RequestStatus.ACCEPTED, requested_start=at(10, 14), requested_end=at(10, 20)
        )

    def test_the_dialog(self) -> None:
        url = _move_url(self.project, what="crew", line=self.line.pk, start="2027-03-10T16:00", end="2027-03-10T21:00")
        dialog = self.assert_ok(self.htmx("get", url))
        self.assertIn("Einsatz von Anna Becker als Stagehand verschieben", dialog)
        self.assertIn(f'<input type="hidden" name="line" value="{self.line.pk}">', dialog)
        self.assertIn("Mi 10.03. 14:00 – 20:00", dialog)
        self.assertIn("Mi 10.03. 16:00 – 21:00", dialog)
        self.assertIn("Die geplanten Stunden folgen dem Zeitraum: 5,00 statt 6,00.", dialog)
        self.assertIn("Anna Becker wird für die neuen Zeiten erneut angefragt.", dialog)
        self.assertIn("Zu den neuen Zeiten gibt es keinen Konflikt.", dialog)
        self.assertIn("Der Einsatz gehört zur Phase „Aufbau“; die Phase behält ihre Zeiten.", dialog)
        self.line.refresh_from_db()
        self.assertEqual(self.line.start, at(10, 14))

    def test_moving(self) -> None:
        url = reverse("schedule:move", args=[self.project.pk])
        data = {
            "what": "crew",
            "line": self.line.pk,
            "start": "2027-03-10T16:00",
            "end": "2027-03-10T21:00",
            "sent": "1",
        }
        done = self.assert_ok(self.htmx("post", url, data))
        self.assertIn("Einsatz von Anna Becker als Stagehand: jetzt Mi 10.03. 16:00 – 21:00", done)
        self.assertIn("Geplante Stunden: jetzt 5,00 (bisher 6,00).", done)
        self.assertNotIn("mitverschoben", done)
        self.line.refresh_from_db()
        self.assertEqual((self.line.start, self.line.end), (at(10, 16), at(10, 21)))
        self.assertEqual(self.line.request_status, RequestStatus.REQUESTED)
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.start, at(10, 14))

    def test_without_the_script_and_with_wrong_lines(self) -> None:
        url = _move_url(self.project, what="crew", line=self.line.pk, next="/schedule/personnel/?days=4")
        page = self.assert_ok(self.client.get(url))
        self.assertIn("Einsatz von Anna Becker als Stagehand verschieben", page)
        response = self.client.post(
            reverse("schedule:move", args=[self.project.pk]),
            {
                "what": "crew",
                "line": self.line.pk,
                "start": "2027-03-10T15:00",
                "end": "2027-03-10T21:00",
                "sent": "1",
                "next": "/schedule/personnel/?days=4",
            },
        )
        self.assertRedirects(response, "/schedule/personnel/?days=4", fetch_redirect_response=False)
        other = plan(make_project("Weinfest"), "Stagehand", self.anna)
        self.assertEqual(self.client.get(_move_url(self.project, what="crew", line=other.pk)).status_code, 404)
        self.assertEqual(self.client.get(_move_url(self.project, what="crew", line="x")).status_code, 404)
        reader = self.browser_of(make_user("rita", roles=("Nur-Lesen",)))
        self.assertEqual(reader.get(_move_url(self.project, what="crew", line=self.line.pk)).status_code, 403)


class MarkingATimeRangeTests(UiTestCase):
    """PER-039: the week of the availability calendar can be marked where the availability can be entered."""

    def test_own_week(self) -> None:
        make_person("Admin Konto", user=self.admin_user)
        page = self.assert_ok(self.client.get("/me/availability/", {"view": "week", "week": "2027-03-08"}))
        self.assertIn("data-avail-select", page)
        self.assertIn('data-text-days="Gewählt: {first} bis {last}, an jedem Tag {start} bis {end}."', page)
        self.assertIn('data-text-clock="{time} Uhr"', page)
        self.assertIn('<p class="avail-selection" data-avail-selection aria-live="polite"></p>', page)
        self.assertIn("oder du markierst in den Spalten einen Zeitbereich", page)
        self.assertIn('data-day="2027-03-08"', page)
        self.assertEqual(problems_of(page), [])
        month = self.assert_ok(self.client.get("/me/availability/", {"view": "month", "month": "2027-03"}))
        self.assertNotIn("data-avail-select", month)
        self.assertNotIn("data-avail-selection", month)

    def test_the_week_of_a_person_for_the_planning(self) -> None:
        anna = make_person("Anna Becker", rates={"Stagehand": "20.00"})
        url = f"/personnel/people/{anna.pk}/availability/"
        page = self.assert_ok(self.client.get(url, {"view": "week", "week": "2027-03-08"}))
        self.assertIn("data-avail-select", page)
        # Who may only read the personnel sees the week without marking.
        reader = self.browser_of(make_user("rita", roles=("Nur-Lesen",)))
        response = reader.get(url, {"view": "week", "week": "2027-03-08"})
        if response.status_code == 200:
            self.assertNotIn("data-avail-select", response.content.decode())

    def test_a_marked_range_is_what_the_form_enters(self) -> None:
        """What the script fills in – days and the hours on each – is the form of PER-021 as it was."""
        person = make_person("Admin Konto", user=self.admin_user)
        response = self.client.post(
            "/me/availability/",
            {
                "start_day": "2027-03-08",
                "end_day": "2027-03-10",
                "with_times": "on",
                "start_time": "09:00",
                "end_time": "13:30",
                "note": "",
                "state": "unavailable",
                "view": "week",
                "week": "2027-03-08",
            },
        )
        self.assertEqual(response.status_code, 302)
        marks = AvailabilityMark.objects.filter(person=person).order_by("start")
        self.assertEqual(
            [(mark.start, mark.end, mark.state) for mark in marks],
            [(at(day, 9), at(day, 13, 30), "unavailable") for day in (8, 9, 10)],
        )
