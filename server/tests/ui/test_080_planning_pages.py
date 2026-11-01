# SPDX-License-Identifier: GPL-3.0-or-later
"""Planning, in the pages: appointments dragged in a timeline and confirmed in a dialog (VFG-026), invoices
that can be switched off (DOK-014)."""

from __future__ import annotations

import json

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from rentalars.core.models import SystemSettings
from rentalars.documents import services as documents
from rentalars.documents.models import AccountingSettings, Document, DocumentKind
from rentalars.projects import course
from rentalars.projects.models import CrewLine, PhaseKind, Project, ProjectStatus, RequestStatus
from tests.helpers import add_line, at, make_person, make_project, make_stock, plan, ready_for_invoices
from tests.ui.base import UiTestCase
from tests.ui.test_accessibility import problems_of

TIMELINE = "/schedule/timeline/"


def _move_url(project: Project, **query: object) -> str:
    from urllib.parse import urlencode

    return f"{reverse('schedule:move', args=[project.pk])}?{urlencode(query)}"


class TimelineBarsTests(UiTestCase):
    """VFG-026: in "Tage" of Planung → Zeitstrahl the rental period and the phases can be dragged – by editors."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(start=at(10, 8), end=at(12, 18))
        self.phase = course.add_phase(self.project, kind=PhaseKind.SETUP, start=at(10, 14), end=at(10, 20))
        self.closed = make_project("Abgeschlossen", start=at(10, 8), end=at(11, 18))
        Project.objects.filter(pk=self.closed.pk).update(status=ProjectStatus.CLOSED)

    def test_movable_bars_for_an_editor(self) -> None:
        page = self.assert_ok(self.client.get(TIMELINE, {"days": "3", "from": "2027-03-10"}))
        self.assertIn(f'data-tl-move="/schedule/move/{self.project.number}/?what=period"', page)
        self.assertIn(
            f'data-tl-move="/schedule/move/{self.project.number}/?what=phase&amp;phase={self.phase.pk}"', page
        )
        self.assertIn('data-tl-start="2027-03-10T14:00" data-tl-end="2027-03-10T20:00"', page)
        self.assertIn('aria-describedby="tl-move-hint" draggable="false"', page)
        self.assertIn('<span class="tl-grip is-start" aria-hidden="true"></span>', page)
        self.assertIn('id="tl-move-hint"', page)
        self.assertIn("in Schritten von 15 Minuten", page)
        self.assertIn('data-first="2027-03-04" data-hours="2"', page)  # VFG-033: two spans before
        self.assertNotIn(f"/schedule/move/{self.closed.number}/", page)  # PRJ-009: a closed project stays
        # The bar leads to the project with a click (to its Überblick).
        self.assertIn(f'href="/projects/{self.project.number}/overview/" title="Stadtfest', page)
        self.assertEqual(problems_of(page), [])

    def test_not_in_weeks_and_not_for_readers(self) -> None:
        weeks = self.assert_ok(self.client.get(TIMELINE, {"weeks": "1", "from": "2027-03-08"}))
        self.assertNotIn("data-tl-move", weeks)
        self.assertNotIn("tl-move-hint", weeks)
        reader = self.browser_for("rita", "Nur-Lesen")
        page = self.assert_ok(reader.get(TIMELINE, {"days": "3", "from": "2027-03-10"}))
        self.assertIn("Stadtfest", page)
        self.assertNotIn("data-tl-move", page)
        self.assertNotIn("tl-move-hint", page)

    def test_the_queries_do_not_grow_with_the_projects(self) -> None:
        def count() -> int:
            with CaptureQueriesContext(connection) as queries:
                self.assert_ok(self.client.get(TIMELINE, {"days": "3", "from": "2027-03-10"}))
            return len(queries)

        count()  # the first request of the session reads the settings and the session itself
        before = count()
        for index in range(5):
            project = make_project(f"Mehr {index}", start=at(10, 8 + index), end=at(11, 18))
            course.add_phase(project, kind=PhaseKind.SETUP, start=at(10, 9 + index), end=at(10, 12 + index))
        self.assertEqual(count(), before)


class CourseTimelineTests(UiTestCase):
    """VFG-026 on the tab "Zeitplanung": the bars of rental period, event and phases open the dialog."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(start=at(10, 8), end=at(12, 18), event_start=at(11, 18), event_end=at(11, 23))
        self.phase = course.add_phase(self.project, kind=PhaseKind.SETUP, start=at(10, 14), end=at(10, 20))
        plan(self.project, "Stagehand", make_person("Anna Becker", rates={"Stagehand": "20.00"}), phase=self.phase)
        self.url = reverse("projects:course", args=[self.project.pk])

    def test_links_to_the_dialog(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        timeline = page[page.index('<section class="course-timeline"') :]
        timeline = timeline[: timeline.index("</section>")]
        for what in ("period", "event", f"phase&amp;phase={self.phase.pk}"):
            self.assertIn(f'href="/schedule/move/{self.project.number}/?what={what}&amp;next=/projects/', timeline)
        # PRJ-121: the crew bar opens the dialog as well.
        self.assertEqual(timeline.count("data-tl-dialog"), 4)
        self.assertIn('<span class="visually-hidden">Aufbau verschieben: </span>', timeline)
        self.assertIn('<a class="tl-bar crew status-confirmed"', timeline)
        self.assertIn('id="tl-move-hint"', timeline)
        self.assertEqual(problems_of(page), [])

    def test_read_only_and_in_weeks_nothing_moves(self) -> None:
        reader = self.browser_for("rita", "Nur-Lesen")
        self.assertNotIn("data-tl-move", self.assert_ok(reader.get(self.url)))
        self.assertNotIn("data-tl-move", self.assert_ok(self.client.get(self.url, {"weeks": "1"})))


class MoveDialogTests(UiTestCase):
    """VFG-026: the dialog names the former and the new times and what follows; "Verschieben" saves."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(start=at(10, 8), end=at(12, 18))
        self.phase = course.add_phase(self.project, kind=PhaseKind.SETUP, start=at(10, 14), end=at(10, 20))
        self.anna = make_person("Anna Becker", rates={"Stagehand": "20.00"})
        self.line = plan(self.project, "Stagehand", self.anna, phase=self.phase)
        CrewLine.objects.filter(pk=self.line.pk).update(
            request_status=RequestStatus.ACCEPTED, requested_start=at(10, 14), requested_end=at(10, 20)
        )
        self.phase_url = _move_url(self.project, what="phase", phase=self.phase.pk)

    def test_the_dialog_of_a_dragged_phase(self) -> None:
        page = self.assert_ok(
            self.htmx("get", self.phase_url + "&start=2027-03-10T15:00&end=2027-03-10T21:00&next=/schedule/timeline/")
        )
        self.assertIn('<h2 id="move-title">Aufbau verschieben</h2>', page)
        self.assertIn("Bisher:</span> Mi 10.03. 14:00 – 20:00", page)
        self.assertIn("Neu:</strong> Mi 10.03. 15:00 – 21:00", page)
        self.assertIn("Anna Becker (Stagehand): bisher Mi 10.03. 14:00 – 20:00, jetzt Mi 10.03. 15:00 – 21:00", page)
        self.assertIn("<strong>wird erneut angefragt</strong>", page)  # PER-034
        self.assertIn('name="move_crew" aria-describedby="move-move_crew-help" id="move-move_crew" checked', page)
        self.assertIn('value="2027-03-10T15:00"', page)
        self.assertNotIn("disabled", page[page.index('id="move-foot"') :])
        # Nothing has changed yet.
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.start, at(10, 14))

    def test_changed_times_ask_again_for_the_consequences_only(self) -> None:
        response = self.client.get(
            self.phase_url + "&start=2027-03-10T16:00&end=2027-03-10T22:00&sent=1",
            HTTP_HX_REQUEST="true",
            HTTP_HX_TARGET="move-consequences",
        )
        part = self.assert_ok(response)
        self.assertTrue(part.lstrip().startswith('<div id="move-consequences"'))
        self.assertIn('id="move-foot" hx-swap-oob="true"', part)
        # Sent from the dialog, an unticked box stays unticked.
        self.assertNotIn("checked", part)

    def test_the_same_times_offer_nothing_to_move(self) -> None:
        page = self.assert_ok(self.htmx("get", self.phase_url))
        self.assertIn("Die Zeiten sind dieselben wie bisher", page)
        foot = page[page.index('id="move-foot"') :]
        self.assertIn("disabled", foot[: foot.index("</div>")])

    def test_moving(self) -> None:
        response = self.htmx(
            "post",
            reverse("schedule:move", args=[self.project.pk]),
            {
                "what": "phase",
                "phase": self.phase.pk,
                "start": "2027-03-10T15:00",
                "end": "2027-03-10T21:00",
                "move_crew": "on",
                "sent": "1",
            },
        )
        page = self.assert_ok(response)
        self.assertEqual(json.loads(response["HX-Trigger"]), {"timelineMoved": {"key": f"phase-{self.phase.pk}"}})
        self.assertIn("Aufbau verschoben", page)
        self.assertIn("Aufbau: jetzt Mi 10.03. 15:00 – 21:00 (bisher Mi 10.03. 14:00 – 20:00).", page)
        self.assertIn("Anna Becker wurde für die neuen Zeiten neu angefragt.", page)
        self.phase.refresh_from_db()
        self.line.refresh_from_db()
        self.assertEqual((self.phase.start, self.line.start), (at(10, 15), at(10, 15)))

    def test_moving_without_the_crew_and_without_the_script(self) -> None:
        response = self.client.post(
            reverse("schedule:move", args=[self.project.pk]),
            {
                "what": "phase",
                "phase": self.phase.pk,
                "start": "2027-03-10T15:00",
                "end": "2027-03-10T21:00",
                "sent": "1",
                "next": "/schedule/timeline/?days=3",
            },
        )
        self.assertRedirects(response, "/schedule/timeline/?days=3", fetch_redirect_response=False)
        self.line.refresh_from_db()
        self.assertEqual(self.line.start, at(10, 14))
        followed = self.client.get(response["Location"])
        self.assertIn(
            "Aufbau: jetzt Mi 10.03. 15:00 – 21:00 (bisher Mi 10.03. 14:00 – 20:00).", self.messages_of(followed)
        )
        # A foreign address is not followed.
        response = self.client.post(
            reverse("schedule:move", args=[self.project.pk]),
            {
                "what": "phase",
                "phase": self.phase.pk,
                "start": "2027-03-10T16:00",
                "end": "2027-03-10T21:00",
                "sent": "1",
                "next": "https://example.com/",
            },
        )
        self.assertEqual(response["Location"], reverse("projects:course", args=[self.project.pk]))

    def test_a_page_of_its_own_without_the_script(self) -> None:
        page = self.assert_ok(self.client.get(self.phase_url + "&start=2027-03-10T15:00&end=2027-03-10T21:00"))
        self.assertIn("<h1>Termin verschieben</h1>", page)
        self.assertNotIn('hx-post="/schedule/move/', page)
        self.assertIn('name="page" value="1"', page)
        self.assertEqual(problems_of(page), [])

    def test_beyond_the_rental_period(self) -> None:
        page = self.assert_ok(self.htmx("get", self.phase_url + "&start=2027-03-09T18:00&end=2027-03-10T02:00"))
        self.assertIn("Die Phase liegt dann außerhalb des Mietzeitraums", page)
        self.assertIn("Mietzeitraum auf Di 09.03. 18:00 – Fr 12.03. 18:00 erweitern", page)
        self.assertIn("Das Material reicht auch für den neuen Mietzeitraum.", page)
        self.htmx(
            "post",
            reverse("schedule:move", args=[self.project.pk]),
            {
                "what": "phase",
                "phase": self.phase.pk,
                "start": "2027-03-09T18:00",
                "end": "2027-03-10T02:00",
                "sent": "1",
                "extend": "on",
            },
        )
        self.project.refresh_from_db()
        self.assertEqual(self.project.start, at(9, 18))

    def test_the_rental_period_moved_as_a_whole(self) -> None:
        stock = make_stock("L-090", 1)
        add_line(self.project, stock, 1)
        other = make_project("Messe", start=at(13, 8), end=at(14, 18))
        add_line(other, stock, 1)
        page = self.assert_ok(
            self.htmx("get", _move_url(self.project, what="period") + "&start=2027-03-11T08:00&end=2027-03-13T18:00")
        )
        self.assertIn("Veranstaltung, Phasen und Crew mitverschieben", page)
        self.assertIn("Aufbau: bisher Mi 10.03. 14:00 – 20:00, jetzt Do 11.03. 14:00 – 20:00", page)
        self.assertIn("1 Materialposition hat den Mietzeitraum und übernimmt den neuen", page)
        self.assertIn("Mit dem neuen Mietzeitraum fehlt 1 Stück.", page)

    def test_errors(self) -> None:
        page = self.assert_ok(self.htmx("get", self.phase_url + "&start=2027-03-10T15:00&end=2027-03-10T14:00"))
        self.assertIn("Das Ende muss nach dem Beginn liegen.", page)
        Project.objects.filter(pk=self.project.pk).update(status=ProjectStatus.CLOSED)
        page = self.assert_ok(self.htmx("get", self.phase_url + "&start=2027-03-10T15:00&end=2027-03-10T21:00"))
        self.assertIn("Dieses Projekt ist abgeschlossen.", page)
        response = self.htmx(
            "post",
            reverse("schedule:move", args=[self.project.pk]),
            {
                "what": "phase",
                "phase": self.phase.pk,
                "start": "2027-03-10T15:00",
                "end": "2027-03-10T21:00",
                "sent": "1",
            },
        )
        self.assertIn("Dieses Projekt ist abgeschlossen.", self.assert_ok(response))
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.start, at(10, 14))

    def test_who_and_what(self) -> None:
        reader = self.browser_for("rita", "Nur-Lesen")
        self.assertEqual(reader.get(self.phase_url).status_code, 403)
        crew = self.browser_for("chris", "Crew")
        self.assertEqual(crew.get(self.phase_url).status_code, 403)
        self.assertEqual(self.client.get(_move_url(self.project, what="nothing")).status_code, 404)
        self.assertEqual(self.client.get(_move_url(self.project, what="event")).status_code, 404)  # no event
        other = make_project("Messe")
        foreign = course.add_phase(other, kind=PhaseKind.SETUP, start=at(10, 8), end=at(10, 9))
        self.assertEqual(self.client.get(_move_url(self.project, what="phase", phase=foreign.pk)).status_code, 404)


class InvoicesSwitchedOffPageTests(UiTestCase):
    """DOK-014: the setting, and what the pages offer while invoices are switched off."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(customer=ready_for_invoices(), status=ProjectStatus.RETURNED)
        add_line(self.project, make_stock("L-091", 2), 1)
        self.invoice = documents.create_document(self.project, DocumentKind.INVOICE)
        self.documents_url = reverse("documents:list", args=[self.project.pk])

    def _switch(self, on: bool) -> None:
        settings_page = self.client.get(reverse("core:company_settings"))
        self.assertIn("Rentalars als Buchhaltungsprogramm verwenden", self.assert_ok(settings_page))
        # DOK-055: the switch has its own box "Buchhaltung und Rechnungswesen" and its own form.
        self.assertIn("Buchhaltung und Rechnungswesen", self.assert_ok(settings_page))
        data = {"form": "accounting", **({"accounting-invoices_enabled": "on"} if on else {})}
        response = self.client.post(reverse("core:company_settings"), data, follow=True)
        self.assertIn("Einstellungen gespeichert.", self.messages_of(response))
        self.assertEqual(SystemSettings.load().invoices_enabled, on)

    def test_on_as_before(self) -> None:
        page = self.assert_ok(self.client.get(self.documents_url))
        self.assertIn('<option value="invoice"', page)
        self.assertNotIn("data-invoices-off", page)
        accounting = self.assert_ok(self.client.get(reverse("documents:accounting")))
        self.assertIn('id="lexware"', accounting)
        self.assertNotIn('id="invoices-off"', accounting)

    def test_off(self) -> None:
        self._switch(False)
        page = self.assert_ok(self.client.get(self.documents_url))
        self.assertNotIn('<option value="invoice"', page)
        self.assertIn('<option value="offer"', page)
        self.assertIn("Rentalars erstellt keine Rechnungen", page)
        # The invoice made before can be read, not cancelled.
        self.assertIn(reverse("documents:file", args=[self.invoice.pk]), page)
        self.assertNotIn(reverse("documents:cancel", args=[self.invoice.pk]), page)
        self.assertEqual(self.client.get(reverse("documents:file", args=[self.invoice.pk])).status_code, 200)
        # The head suggests no invoice for the returned project.
        self.assertNotIn("Rechnung erstellen", page)
        response = self.client.post(
            reverse("documents:create", args=[self.project.pk]), {"kind": "invoice"}, follow=True
        )
        self.assertTrue(
            any("Rentalars als Buchhaltungsprogramm verwenden" in text for text in self.messages_of(response))
        )
        response = self.client.post(reverse("documents:cancel", args=[self.invoice.pk]), follow=True)
        self.assertTrue(
            any("Rentalars als Buchhaltungsprogramm verwenden" in text for text in self.messages_of(response))
        )
        self.assertEqual(Document.objects.filter(project=self.project).count(), 1)
        # The accounting page says why it is empty; handing over and the export are refused.
        accounting = self.assert_ok(self.client.get(reverse("documents:accounting")))
        self.assertIn('id="invoices-off"', accounting)
        self.assertNotIn('id="lexware"', accounting)
        self.assertNotIn('id="datev-export"', accounting)
        self.assertEqual(problems_of(accounting), [])
        AccountingSettings.objects.update(lexware_enabled=True)
        response = self.client.post(reverse("documents:lexware_transfer", args=[self.invoice.pk]), follow=True)
        self.assertTrue(
            any("Rentalars als Buchhaltungsprogramm verwenden" in text for text in self.messages_of(response))
        )
        response = self.client.get(
            reverse("documents:datev_export"), {"date_from": "2027-03-01", "date_to": "2027-03-31"}, follow=True
        )
        self.assertTrue(
            any("Rentalars als Buchhaltungsprogramm verwenden" in text for text in self.messages_of(response))
        )
        # The project is closed without an invoice.
        response = self.client.post(reverse("projects:set_status", args=[self.project.pk]), {"status": "closed"})
        self.assertEqual(Project.objects.get(pk=self.project.pk).status, ProjectStatus.CLOSED)
        self._switch(True)
        self.assertIn('<option value="invoice"', self.assert_ok(self.client.get(self.documents_url)))
