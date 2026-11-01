# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages, pickers: the picker texts (UIX-036), the periods hatched in the calendars and the layout of the
project form (PRJ-099), and the question whether to extend the rental period for a phase beyond it (PRJ-100)."""

from __future__ import annotations

import html
import json
import re

from django.urls import reverse

from rentalars.notifications.models import Notification
from rentalars.projects import course, services
from rentalars.projects.models import Project, ProjectPhase, ProjectStatus
from tests.helpers import add_line, at, make_project, make_stock, make_user
from tests.ui.base import UiTestCase, form_data


def marks_of(page: str) -> list[dict]:
    """The periods named in ``data-calendar-marks`` (PRJ-099)."""
    found = re.search(r'data-calendar-marks="([^"]*)"', page)
    return json.loads(html.unescape(found.group(1))) if found else []


class PickerTextsAndLayoutTests(UiTestCase):
    """UIX-036 and PRJ-099 in the HTML the server sends."""

    def test_every_page_carries_the_texts_of_the_picker(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:list")))
        for text in (
            'data-text-pick-date="Datum wählen"',
            'data-text-pick-date-time="Datum und Uhrzeit wählen"',
            'data-text-pick-time="Uhrzeit wählen"',
            'data-text-hour="Stunde"',
            'data-text-minute="Minute"',
            'data-text-clock-hint="Erst die Stunde antippen, dann die Minute."',
            'data-text-today="Heute"',
            'data-text-now="Jetzt"',
            'data-text-clear="Leeren"',
        ):
            self.assertIn(text, page)
        # UIX-036: the fields keep their types – typing, the server and the API stay as they are.
        self.assertIn('type="date"', page)

    def test_the_project_form_lays_out_both_periods_alike(self) -> None:
        """PRJ-099: from, until and a place for the calendar button in one row – in both boxes."""
        page = self.assert_ok(self.client.get(reverse("projects:create")))
        boxes = re.findall(r'<div class="period-fields">(.*?)\n      </div>', page, re.S)
        self.assertEqual(len(boxes), 2)
        self.assertIn('name="start"', boxes[0])
        self.assertIn('name="end"', boxes[0])
        self.assertIn('data-range-slot="start"', boxes[0])
        self.assertIn('name="event_start"', boxes[1])
        self.assertIn('name="event_end"', boxes[1])
        self.assertIn('data-range-slot="event_start"', boxes[1])
        self.assertIn('name="rental_days"', boxes[1])
        self.assertLess(boxes[1].index("data-range-slot"), boxes[1].index('name="rental_days"'))
        self.assertEqual(
            marks_of(page),
            [
                {"kind": "rental", "label": "Mietzeitraum", "fields": ["start", "end"]},
                {"kind": "event", "label": "Veranstaltung", "fields": ["event_start", "event_end"]},
            ],
        )

    def test_the_phase_forms_mark_the_periods_of_the_project(self) -> None:
        """PRJ-099: on the page "Zeitplanung" and in the dialog over the crew planning."""
        project = make_project(start=at(12, 12), end=at(14, 18), event_start=at(13, 10), event_end=at(13, 23))
        expected = [
            {"kind": "rental", "label": "Mietzeitraum", "start": "2027-03-12T12:00", "end": "2027-03-14T18:00"},
            {"kind": "event", "label": "Veranstaltung", "start": "2027-03-13T10:00", "end": "2027-03-13T23:00"},
        ]
        page = self.assert_ok(self.client.get(reverse("projects:phase_create", args=[project.pk])))
        self.assertEqual(marks_of(page), expected)
        dialog = self.assert_ok(self.htmx("get", reverse("projects:phase_dialog", args=[project.pk])))
        self.assertEqual(marks_of(dialog), expected)
        without_event = make_project("Jazznacht", start=at(20, 12), end=at(21, 12))
        page = self.assert_ok(self.client.get(reverse("projects:phase_create", args=[without_event.pk])))
        self.assertEqual([mark["kind"] for mark in marks_of(page)], ["rental"])


class ExtendTheRentalPeriodPageTests(UiTestCase):
    """PRJ-100 on the page "Zeitplanung": ask after saving, change only after "Extend"."""

    def setUp(self) -> None:
        super().setUp()
        self.manager = make_user("paula")
        self.project = make_project(start=at(12, 12), end=at(14, 18), manager=self.manager)
        self.create = reverse("projects:phase_create", args=[self.project.pk])
        self.course = reverse("projects:course", args=[self.project.pk])

    def save_phase(self, kind: str, start: str, end: str, url: str | None = None) -> object:
        url = url or self.create
        data = form_data(self.client.get(url), "kind", kind=kind, title="", start=start, end=end)
        return self.client.post(url, data)

    def test_a_phase_within_the_rental_period_asks_nothing(self) -> None:
        answer = self.save_phase("setup", "2027-03-12T12:00", "2027-03-12T20:00")
        self.assertRedirects(answer, self.course)

    def test_a_phase_beyond_it_leads_to_the_question(self) -> None:
        answer = self.save_phase("setup", "2027-03-11T14:00", "2027-03-11T20:00")
        phase = ProjectPhase.objects.get()
        self.assertRedirects(answer, f"{self.course}?extend={phase.pk}")
        page = self.assert_ok(self.client.get(answer["Location"]))
        self.assertIn("Mietzeitraum erweitern?", page)
        self.assertIn("Die Phase „Aufbau“ (Do 11.03. 14:00 – Do 11.03. 20:00) liegt außerhalb des Mietzeitraums", page)
        self.assertIn("(Fr 12.03. 12:00 – So 14.03. 18:00)", page)
        self.assertIn("Mietzeitraum auf Do 11.03. 14:00 – So 14.03. 18:00 erweitern?", page)
        self.assertIn(f'action="{reverse("projects:phase_extend_period", args=[self.project.pk, phase.pk])}"', page)
        self.assertIn(">Erweitern</button>", page)
        self.assertIn(f'href="{self.course}">Nicht erweitern</a>', page)
        # Nothing changed yet.
        self.project.refresh_from_db()
        self.assertEqual(self.project.start, at(12, 12))

    def test_changing_a_phase_asks_as_well(self) -> None:
        phase = course.add_phase(self.project, kind="teardown", start=at(14, 12), end=at(14, 18))
        answer = self.save_phase(
            "teardown",
            "2027-03-14T12:00",
            "2027-03-15T09:00",
            reverse("projects:phase_edit", args=[self.project.pk, phase.pk]),
        )
        self.assertRedirects(answer, f"{self.course}?extend={phase.pk}")

    def test_planning_and_meetings_never_ask(self) -> None:
        answer = self.save_phase("planning", "2027-02-20T10:00", "2027-02-20T12:00")
        self.assertRedirects(answer, self.course)
        phase = ProjectPhase.objects.get()
        self.assertNotIn("Mietzeitraum erweitern?", self.assert_ok(self.client.get(f"{self.course}?extend={phase.pk}")))

    def test_extend(self) -> None:
        product = make_stock("S-001", 2)
        line = add_line(self.project, product, 1).line
        phase = course.add_phase(self.project, kind="setup", start=at(11, 14), end=at(11, 20))
        answer = self.client.post(
            reverse("projects:phase_extend_period", args=[self.project.pk, phase.pk]), follow=True
        )
        self.assertRedirects(answer, self.course)
        self.assertIn("Mietzeitraum erweitert: Do 11.03. 14:00 – So 14.03. 18:00.", self.messages_of(answer))
        self.assertNotIn("Mietzeitraum erweitern?", answer.content.decode())
        self.project.refresh_from_db()
        line.refresh_from_db()
        self.assertEqual((self.project.start, self.project.end), (at(11, 14), at(14, 18)))
        self.assertEqual(line.start, at(11, 14))
        # UIX-005: as after a new period in the project form.
        self.assertTrue(Notification.objects.filter(user=self.manager, project=self.project).exists())

    def test_a_shortage_through_the_longer_period_is_named(self) -> None:
        product = make_stock("S-001", 2)
        before = make_project("Vorher", start=at(10, 12), end=at(11, 18))
        add_line(before, product, 2)
        add_line(self.project, product, 2)
        phase = course.add_phase(self.project, kind="setup", start=at(11, 14), end=at(11, 20))
        answer = self.client.post(
            reverse("projects:phase_extend_period", args=[self.project.pk, phase.pk]), follow=True
        )
        texts = self.messages_of(answer)
        self.assertIn("Im neuen Mietzeitraum fehlen 2 Stück. Sieh dir die rot markierten Positionen an.", texts)

    def test_the_usual_checks_refuse(self) -> None:
        part = services.create_subproject(self.project, name="Bühne", start=at(13, 8), end=at(14, 12))
        phase = course.add_phase(part, kind="setup", start=at(11, 14), end=at(11, 20))
        page = self.assert_ok(self.client.get(reverse("projects:course", args=[part.pk]), {"extend": phase.pk}))
        # Asked for, but the whole project comes first: no "Extend".
        self.assertIn(f"Gesamtprojekts {self.project.number}", page)
        self.assertNotIn(">Erweitern</button>", page)
        answer = self.client.post(reverse("projects:phase_extend_period", args=[part.pk, phase.pk]), follow=True)
        self.assertTrue(any("Gesamtprojekts" in text for text in self.messages_of(answer)))
        part.refresh_from_db()
        self.assertEqual(part.start, at(13, 8))

    def test_a_closed_project_is_not_changed(self) -> None:
        phase = course.add_phase(self.project, kind="setup", start=at(11, 14), end=at(11, 20))
        Project.objects.filter(pk=self.project.pk).update(status=ProjectStatus.CLOSED)
        self.assertNotIn("Mietzeitraum erweitern?", self.assert_ok(self.client.get(self.course, {"extend": phase.pk})))
        self.client.post(reverse("projects:phase_extend_period", args=[self.project.pk, phase.pk]))
        self.project.refresh_from_db()
        self.assertEqual(self.project.start, at(12, 12))

    def test_only_for_whoever_may_edit_the_project(self) -> None:
        phase = course.add_phase(self.project, kind="setup", start=at(11, 14), end=at(11, 20))
        reader = self.browser_for("nora", "Nur-Lesen")
        self.assertNotIn("Mietzeitraum erweitern?", self.assert_ok(reader.get(self.course, {"extend": phase.pk})))
        answer = reader.post(reverse("projects:phase_extend_period", args=[self.project.pk, phase.pk]))
        self.assertIn(answer.status_code, (403, 404))
        self.assertEqual(
            self.client.get(reverse("projects:phase_extend_period", args=[self.project.pk, phase.pk])).status_code, 405
        )
        self.project.refresh_from_db()
        self.assertEqual(self.project.start, at(12, 12))


class ExtendTheRentalPeriodDialogTests(UiTestCase):
    """PRJ-100 in the dialog for a new phase over the crew planning (PRJ-094)."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(start=at(12, 12), end=at(14, 18))
        self.dialog = reverse("projects:phase_dialog", args=[self.project.pk])

    def test_within_the_period_the_dialog_closes_as_before(self) -> None:
        answer = self.htmx(
            "post", self.dialog, {"kind": "setup", "start": "2027-03-12T12:00", "end": "2027-03-12T20:00"}
        )
        self.assertEqual(answer.status_code, 204)
        self.assertNotIn("keepDialog", json.loads(answer["HX-Trigger"])["phaseCreated"])

    def test_beyond_it_the_dialog_asks(self) -> None:
        answer = self.htmx(
            "post", self.dialog, {"kind": "setup", "start": "2027-03-11T14:00", "end": "2027-03-11T20:00"}
        )
        page = self.assert_ok(answer)
        phase = ProjectPhase.objects.get()
        created = json.loads(answer["HX-Trigger"])["phaseCreated"]
        self.assertEqual((created["id"], created["keepDialog"]), (phase.pk, True))
        self.assertIn('<h2 id="phase-dialog-title">Mietzeitraum erweitern?</h2>', page)
        self.assertIn(f'hx-post="{reverse("projects:phase_extend_period", args=[self.project.pk, phase.pk])}"', page)
        self.assertIn('hx-target="closest dialog"', page)
        self.assertIn('<button type="submit" class="btn" autofocus>Erweitern</button>', page)
        self.assertIn("data-close-dialog>Nicht erweitern</button>", page)

    def test_extend_from_the_dialog(self) -> None:
        phase = course.add_phase(self.project, kind="setup", start=at(11, 14), end=at(11, 20))
        answer = self.htmx("post", reverse("projects:phase_extend_period", args=[self.project.pk, phase.pk]))
        page = self.assert_ok(answer)
        self.assertEqual(answer["HX-Trigger"], "rentalPeriodChanged")
        self.assertIn("Mietzeitraum erweitert: Do 11.03. 14:00 – So 14.03. 18:00.", page)
        self.assertIn("data-close-dialog autofocus>Schließen</button>", page)
        self.project.refresh_from_db()
        self.assertEqual(self.project.start, at(11, 14))

    def test_a_refusal_stays_in_the_dialog(self) -> None:
        part = services.create_subproject(self.project, name="Bühne", start=at(13, 8), end=at(14, 12))
        phase = course.add_phase(part, kind="setup", start=at(11, 14), end=at(11, 20))
        answer = self.htmx("post", reverse("projects:phase_extend_period", args=[part.pk, phase.pk]))
        page = self.assert_ok(answer)
        self.assertNotIn("HX-Trigger", answer)
        self.assertIn("Der Mietzeitraum bleibt, wie er war", page)
        self.assertIn('class="message error"', page)
