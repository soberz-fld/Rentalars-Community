# SPDX-License-Identifier: GPL-3.0-or-later
"""Planning: moving appointments by dragging them in a timeline (VFG-026) and invoices that can be switched
off (DOK-014)."""

from __future__ import annotations

import datetime

from django.core import mail
from django.core.exceptions import ValidationError
from django.test import RequestFactory

from rentalars.accounts.models import Role
from rentalars.accounts.rights import rights_of
from rentalars.core.models import AuditLogEntry, SystemSettings
from rentalars.documents import datev, lexware, services
from rentalars.documents.models import AccountingSettings, Document, DocumentKind
from rentalars.notifications.models import Kind, Notification
from rentalars.projects import course
from rentalars.projects import services as project_services
from rentalars.projects.models import (
    CrewLine,
    PhaseKind,
    Project,
    ProjectAccessLevel,
    ProjectMembership,
    ProjectStatus,
    RequestStatus,
)
from rentalars.projects.templatetags.project_actions import suggested_document
from rentalars.schedule import moves
from rentalars.schedule import services as schedule_services
from rentalars.schedule.moves import EVENT, PERIOD, PHASE, MoveRequest
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_line,
    at,
    make_person,
    make_project,
    make_stock,
    make_user,
    plan,
    ready_for_invoices,
)


def _move(
    project: Project, what: str, start: datetime.datetime, end: datetime.datetime, **options: object
) -> MoveRequest:
    phase = options.pop("phase", None)
    return MoveRequest(project=project, what=what, phase=phase, start=start, end=end, **options)  # type: ignore[arg-type]


class MovePhaseTests(RentalarsTestCase):
    """VFG-026: a phase dragged to other times – its crew along (PRJ-080), asked again (PER-034), PRJ-100."""

    def setUp(self) -> None:
        super().setUp()
        self.manager = make_user("lea")
        self.project = make_project(start=at(10, 8), end=at(12, 18), manager=self.manager)
        self.setup = course.add_phase(self.project, kind=PhaseKind.SETUP, start=at(10, 14), end=at(10, 20))
        self.anna = make_person("Anna Becker", rates={"Lichttechnik": "35.00"}, user=make_user("anna"))
        self.ben = make_person("Ben Kraus", rates={"Lichttechnik": "30.00"})
        self.whole = plan(self.project, "Lichttechnik", self.anna, phase=self.setup)
        self.part = plan(self.project, "Lichttechnik", self.ben, phase=self.setup, start=at(10, 16), end=at(10, 20))
        CrewLine.objects.filter(pk=self.whole.pk).update(
            request_status=RequestStatus.ACCEPTED, requested_start=at(10, 14), requested_end=at(10, 20)
        )

    def test_the_crew_moves_along_and_the_accepted_person_is_asked_again(self) -> None:
        outcome = moves.perform_move(
            _move(self.project, PHASE, at(10, 15), at(10, 21), phase=self.setup), rights=ALL_RIGHTS
        )
        self.setup.refresh_from_db()
        self.assertEqual((self.setup.start, self.setup.end), (at(10, 15), at(10, 21)))
        whole, part = CrewLine.objects.get(pk=self.whole.pk), CrewLine.objects.get(pk=self.part.pk)
        # The line with the period of the phase takes the new one; the other moves by as much as the start.
        self.assertEqual((whole.start, whole.end), (at(10, 15), at(10, 21)))
        self.assertEqual((part.start, part.end), (at(10, 17), at(10, 21)))
        self.assertEqual(whole.request_status, RequestStatus.REQUESTED)
        self.assertEqual({change.line.pk for change in outcome.asked_again}, {self.whole.pk})
        self.assertEqual([change.kind for change in outcome.changes], [PHASE])
        self.assertIsNone(outcome.shortage_after)  # a phase reserves nothing

    def test_without_the_crew(self) -> None:
        moves.perform_move(
            _move(self.project, PHASE, at(10, 15), at(10, 21), phase=self.setup, move_crew=False), rights=ALL_RIGHTS
        )
        whole = CrewLine.objects.get(pk=self.whole.pk)
        self.assertEqual((whole.start, whole.end, whole.request_status), (at(10, 14), at(10, 20), "accepted"))

    def test_the_preview_changes_nothing(self) -> None:
        entries, notifications = AuditLogEntry.objects.count(), Notification.objects.count()
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            preview = moves.preview_move(
                _move(self.project, PHASE, at(10, 15), at(10, 21), phase=self.setup), rights=ALL_RIGHTS
            )
        self.assertEqual(callbacks, [])
        self.assertTrue(preview.is_possible)
        self.assertEqual(len(preview.outcome.crew), 2)
        self.assertEqual([change.who for change in preview.outcome.asked_again], ["Anna Becker"])
        self.assertEqual(preview.phase_crew, 2)
        self.setup.refresh_from_db()
        self.assertEqual((self.setup.start, self.setup.end), (at(10, 14), at(10, 20)))
        self.assertEqual(CrewLine.objects.get(pk=self.whole.pk).request_status, RequestStatus.ACCEPTED)
        self.assertEqual((AuditLogEntry.objects.count(), Notification.objects.count()), (entries, notifications))
        self.assertEqual(mail.outbox, [])

    def test_no_new_request_when_the_setting_is_off(self) -> None:
        settings = SystemSettings.load()
        settings.ask_again_on_new_times = False
        settings.save()
        outcome = moves.perform_move(
            _move(self.project, PHASE, at(10, 15), at(10, 21), phase=self.setup), rights=ALL_RIGHTS
        )
        self.assertEqual(outcome.asked_again, [])

    def test_beyond_the_rental_period_the_extension_is_offered_and_done_only_when_ticked(self) -> None:
        move = _move(self.project, PHASE, at(9, 18), at(10, 2), phase=self.setup)
        preview = moves.preview_move(move, rights=ALL_RIGHTS)
        self.assertTrue(preview.can_extend)
        self.assertEqual((preview.suggestion.start, preview.suggestion.end), (at(9, 18), at(12, 18)))
        self.assertEqual(preview.material_note[0], "success")
        self.project.refresh_from_db()
        self.assertEqual(self.project.start, at(10, 8))
        moves.perform_move(move, rights=ALL_RIGHTS)
        self.project.refresh_from_db()
        self.assertEqual(self.project.start, at(10, 8))  # not ticked: only the phase moved
        self.setup.refresh_from_db()
        outcome = moves.perform_move(
            _move(self.project, PHASE, at(9, 17), at(10, 2), phase=self.setup, extend=True), rights=ALL_RIGHTS
        )
        self.project.refresh_from_db()
        self.assertTrue(outcome.extended)
        self.assertEqual(self.project.start, at(9, 17))
        self.assertTrue(outcome.changes_rental_period)

    def test_a_planning_meeting_never_asks(self) -> None:
        meeting = course.add_phase(self.project, kind=PhaseKind.PLANNING, start=at(3, 10), end=at(3, 11))
        preview = moves.preview_move(_move(self.project, PHASE, at(2, 10), at(2, 11), phase=meeting), rights=ALL_RIGHTS)
        self.assertIsNone(preview.suggestion)
        self.assertTrue(preview.is_possible)

    def test_a_part_waits_for_its_whole_project(self) -> None:
        part = project_services.create_subproject(self.project, name="Bühne 2", start=at(10, 8), end=at(12, 18))
        phase = course.add_phase(part, kind=PhaseKind.SETUP, start=at(10, 10), end=at(10, 12))
        preview = moves.preview_move(_move(part, PHASE, at(9, 10), at(9, 12), phase=phase), rights=ALL_RIGHTS)
        self.assertEqual(preview.suggestion.blocked_by, self.project)
        self.assertFalse(preview.can_extend)
        self.assertTrue(preview.is_possible)

    def test_the_rules(self) -> None:
        with self.assertRaises(ValidationError):
            moves.check_move(_move(self.project, PHASE, at(10, 15), at(10, 15), phase=self.setup))
        other = make_project("Messe")
        foreign = course.add_phase(other, kind=PhaseKind.SETUP, start=at(10, 8), end=at(10, 9))
        with self.assertRaises(ValidationError):
            moves.check_move(_move(self.project, PHASE, at(10, 15), at(10, 16), phase=foreign))
        with self.assertRaises(ValidationError):
            moves.check_move(_move(self.project, EVENT, at(10, 15), at(10, 16)))  # no event period
        Project.objects.filter(pk=self.project.pk).update(status=ProjectStatus.CLOSED)
        self.project.refresh_from_db()
        preview = moves.preview_move(
            _move(self.project, PHASE, at(10, 15), at(10, 21), phase=self.setup), rights=ALL_RIGHTS
        )
        self.assertFalse(preview.is_possible)
        self.assertIn("abgeschlossen", " ".join(preview.errors))

    def test_unchanged_times_offer_nothing_to_do(self) -> None:
        preview = moves.preview_move(
            _move(self.project, PHASE, at(10, 14), at(10, 20), phase=self.setup), rights=ALL_RIGHTS
        )
        self.assertFalse(preview.is_possible)
        self.assertIsNone(preview.outcome)


class MoveRentalPeriodTests(RentalarsTestCase):
    """VFG-026: the rental period dragged – as a whole with the schedule, or at one end."""

    def setUp(self) -> None:
        super().setUp()
        self.manager = make_user("lea")
        self.project = make_project(
            start=at(10, 8), end=at(12, 18), manager=self.manager, event_start=at(11, 18), event_end=at(11, 23)
        )
        self.setup = course.add_phase(self.project, kind=PhaseKind.SETUP, start=at(10, 14), end=at(10, 20))
        self.anna = make_person("Anna Becker", rates={"Lichttechnik": "35.00"}, user=make_user("anna"))
        self.ben = make_person("Ben Kraus", rates={"Lichttechnik": "30.00"})
        self.in_phase = plan(self.project, "Lichttechnik", self.anna, phase=self.setup)
        self.without = plan(self.project, "Lichttechnik", self.ben, start=at(11, 17), end=at(11, 23))
        self.stock = make_stock("L-080", 4)
        self.line = add_line(self.project, self.stock, 2).line
        self.own = add_line(self.project, self.stock, 1, start=at(10, 8), end=at(11, 8)).line

    def test_moved_as_a_whole_the_schedule_follows(self) -> None:
        move = _move(self.project, PERIOD, at(11, 8), at(13, 18))
        self.assertTrue(move.offers_schedule)
        outcome = moves.perform_move(move, rights=ALL_RIGHTS, user=self.manager)
        self.project.refresh_from_db()
        self.setup.refresh_from_db()
        self.assertEqual((self.project.start, self.project.end), (at(11, 8), at(13, 18)))
        self.assertEqual((self.project.event_start, self.project.event_end), (at(12, 18), at(12, 23)))
        self.assertEqual((self.setup.start, self.setup.end), (at(11, 14), at(11, 20)))
        self.assertEqual(CrewLine.objects.get(pk=self.in_phase.pk).start, at(11, 14))
        self.assertEqual(CrewLine.objects.get(pk=self.without.pk).start, at(12, 17))
        self.line.refresh_from_db()
        self.own.refresh_from_db()
        self.assertEqual((self.line.start, self.line.end), (at(11, 8), at(13, 18)))  # had the period: follows
        self.assertEqual((self.own.start, self.own.end), (at(10, 8), at(11, 8)))  # a period of its own: stays
        self.assertEqual(outcome.material_lines, 1)
        self.assertEqual([change.kind for change in outcome.changes], [PERIOD, EVENT, PHASE])
        self.assertEqual(len(outcome.crew), 2)
        self.assertEqual((outcome.shortage_before, outcome.shortage_after), (0, 0))
        # UIX-005: the people of the project hear of the new period, as after the project form. PRJ-118: Anna, whose
        # lines moved, hears of them instead – one message with her new times, not a second one "neuer Zeitraum".
        told = Notification.objects.filter(user=self.anna.user)
        self.assertEqual(list(told.values_list("kind", flat=True)), [Kind.DEPLOYMENT_CHANGE])
        self.assertFalse(told.filter(title__contains="neuer Zeitraum").exists())

    def test_without_the_schedule(self) -> None:
        moves.perform_move(
            _move(self.project, PERIOD, at(11, 8), at(13, 18), with_schedule=False),
            rights=ALL_RIGHTS,
            user=self.manager,
        )
        self.setup.refresh_from_db()
        self.project.refresh_from_db()
        self.assertEqual(self.setup.start, at(10, 14))
        self.assertEqual(self.project.event_start, at(11, 18))
        # Her lines stayed: the crew hears of the new period (UIX-005).
        self.assertTrue(Notification.objects.filter(user=self.anna.user, title__contains="neuer Zeitraum").exists())

    def test_one_end_changes_only_the_period(self) -> None:
        move = _move(self.project, PERIOD, at(10, 8), at(13, 12))
        self.assertFalse(move.offers_schedule)
        preview = moves.preview_move(move, rights=ALL_RIGHTS)
        self.assertEqual(preview.schedule_changes, [])
        outcome = moves.perform_move(move, rights=ALL_RIGHTS)
        self.assertEqual([change.kind for change in outcome.changes], [PERIOD])
        self.setup.refresh_from_db()
        self.assertEqual(self.setup.start, at(10, 14))
        self.line.refresh_from_db()
        self.assertEqual(self.line.end, at(13, 12))

    def test_the_preview_counts_the_material_missing(self) -> None:
        other = make_project("Messe", start=at(13, 8), end=at(14, 18))
        add_line(other, self.stock, 3)
        preview = moves.preview_move(_move(self.project, PERIOD, at(12, 8), at(14, 18)), rights=ALL_RIGHTS)
        self.assertEqual((preview.outcome.shortage_before, preview.outcome.shortage_after), (0, 1))
        self.assertEqual(preview.material_note[0], "warning")
        self.project.refresh_from_db()
        self.assertEqual(self.project.start, at(10, 8))

    def test_the_event_alone(self) -> None:
        outcome = moves.perform_move(_move(self.project, EVENT, at(11, 19), at(11, 23, 45)), rights=ALL_RIGHTS)
        self.project.refresh_from_db()
        self.assertEqual((self.project.start, self.project.event_start), (at(10, 8), at(11, 19)))
        self.assertEqual([change.kind for change in outcome.changes], [EVENT])

    def test_the_parts_of_a_whole_project_move_along(self) -> None:
        part = project_services.create_subproject(self.project, name="Bühne 2", start=at(11, 8), end=at(12, 12))
        phase = course.add_phase(part, kind=PhaseKind.SETUP, start=at(11, 9), end=at(11, 10))
        outcome = moves.perform_move(_move(self.project, PERIOD, at(11, 8), at(13, 18)), rights=ALL_RIGHTS)
        part.refresh_from_db()
        phase.refresh_from_db()
        self.assertEqual((part.start, part.end), (at(12, 8), at(13, 12)))
        self.assertEqual(phase.start, at(12, 9))
        self.assertIn("part", [change.kind for change in outcome.changes])

    def test_a_part_stays_within_its_whole_project(self) -> None:
        part = project_services.create_subproject(self.project, name="Bühne 2", start=at(11, 8), end=at(12, 12))
        preview = moves.preview_move(_move(part, PERIOD, at(12, 8), at(13, 12)), rights=ALL_RIGHTS)
        self.assertFalse(preview.is_possible)
        with self.assertRaises(ValidationError):
            moves.perform_move(_move(part, PERIOD, at(12, 8), at(13, 12)), rights=ALL_RIGHTS)
        part.refresh_from_db()
        self.assertEqual(part.start, at(11, 8))


class MovableTests(RentalarsTestCase):
    """VFG-026: who may drag what, and the bars of the timelines."""

    def setUp(self) -> None:
        super().setUp()
        self.open = make_project("Offen", start=at(10, 8), end=at(12, 18))
        self.closed = make_project("Zu", start=at(10, 8), end=at(12, 18))
        Project.objects.filter(pk=self.closed.pk).update(status=ProjectStatus.CLOSED)
        self.closed.refresh_from_db()

    def test_who_may_move(self) -> None:
        projects = [self.open, self.closed]
        self.assertEqual(moves.movable_project_ids(ALL_RIGHTS, None, projects), {self.open.pk})
        reader = make_user("rita", roles=("Nur-Lesen",))
        self.assertEqual(moves.movable_project_ids(rights_of(reader), reader, projects), set())
        Role.objects.create(name="Bühnenmeister", module_levels={"projects": 2}, project_scope="assigned")
        limited = make_user("bernd", roles=("Bühnenmeister",))
        self.assertEqual(moves.movable_project_ids(rights_of(limited), limited, projects), set())
        ProjectMembership.objects.create(project=self.open, user=limited, level=ProjectAccessLevel.EDIT)
        with self.assertNumQueries(1):
            self.assertEqual(moves.movable_project_ids(rights_of(limited), limited, projects), {self.open.pk})

    def test_bars_of_the_timeline_in_hours_only(self) -> None:
        phase = course.add_phase(self.open, kind=PhaseKind.SETUP, start=at(10, 14), end=at(10, 20))
        request = RequestFactory().get("/", {"days": "2", "from": "2027-03-10"})
        scale, _navigation = schedule_services.scale_from_request(request)
        rows = dict(
            schedule_services.project_timeline(Project.objects.all(), scale, movable=lambda shown: {self.open.pk})
        )
        bars = rows[self.open]
        self.assertEqual(bars[0].move.key, f"period-{self.open.pk}")
        self.assertEqual((bars[0].move.start, bars[0].move.end), ("2027-03-10T08:00", "2027-03-12T18:00"))
        self.assertEqual(bars[1].move.key, f"phase-{phase.pk}")
        self.assertIn(f"/schedule/move/{self.open.number}/?what=phase&phase={phase.pk}", bars[1].move.url)
        self.assertIn('data-tl-move="', bars[1].move.attrs)
        self.assertIn("is-start", bars[1].move.grips)
        self.assertTrue(all(bar.move is None for bar in rows[self.closed]))
        weeks = schedule_services.project_timeline(
            Project.objects.all(),
            schedule_services.day_range(datetime.date(2027, 3, 8), 7),
            movable=lambda shown: {self.open.pk},
        )
        self.assertTrue(all(bar.move is None for _project, bars in weeks for bar in bars))

    def test_an_end_beyond_the_columns_has_no_grip(self) -> None:
        request = RequestFactory().get("/", {"days": "1", "from": "2027-03-11"})
        scale, _navigation = schedule_services.scale_from_request(request)
        long = make_project("Lang", start=at(1, 8), end=at(25, 18))
        movable = moves.movable(long, PERIOD, long.start, long.end, scale)
        self.assertFalse(movable.start_shown)
        self.assertFalse(movable.end_shown)
        self.assertNotIn("tl-grip", movable.grips)


class InvoicesSwitchedOffTests(RentalarsTestCase):
    """DOK-014: "use Rentalars as accounting software" – on by default; off, no invoice, no cancellation, no accounting."""

    def setUp(self) -> None:
        super().setUp()
        self.customer = ready_for_invoices()
        self.project = make_project(customer=self.customer, status=ProjectStatus.RETURNED)
        add_line(self.project, make_stock("L-081", 2), 1)
        self.invoice = services.create_document(self.project, DocumentKind.INVOICE)

    def _switch_off(self) -> None:
        settings = SystemSettings.load()
        settings.invoices_enabled = False
        settings.save()

    def test_on_by_default(self) -> None:
        self.assertTrue(SystemSettings.load().invoices_enabled)
        self.assertIn(DocumentKind.INVOICE, services.makeable_kinds())

    def test_off_no_invoice_and_no_cancellation(self) -> None:
        self._switch_off()
        self.assertNotIn(DocumentKind.INVOICE, services.makeable_kinds())
        self.assertIn(DocumentKind.OFFER, services.makeable_kinds())
        self.assertEqual(services.check_can_make(self.project, DocumentKind.INVOICE), [services.invoices_off_message()])
        with self.assertRaisesMessage(ValidationError, "Rentalars als Buchhaltungsprogramm verwenden"):
            services.create_document(self.project, DocumentKind.INVOICE)
        with self.assertRaises(ValidationError):
            services.preview(self.project, DocumentKind.INVOICE)
        with self.assertRaises(ValidationError):
            services.cancel_invoice(self.invoice)
        self.assertIsNone(Document.objects.get(pk=self.invoice.pk).cancelled_by_id)
        # Other documents are made as before; the invoice made before stays.
        offer = services.create_document(self.project, DocumentKind.OFFER)
        self.assertEqual(offer.kind, DocumentKind.OFFER)
        self.assertTrue(services.verify(self.invoice))

    def test_off_no_handing_over_and_no_export(self) -> None:
        accounting = AccountingSettings.load()
        accounting.set_lexware_api_key("key")
        accounting.lexware_enabled = True
        accounting.datev_consultant_number, accounting.datev_client_number = 1001, 1
        accounting.save()
        self._switch_off()
        with self.assertRaisesMessage(ValidationError, "Rentalars als Buchhaltungsprogramm verwenden"):
            lexware.request_transfer(self.invoice)
        with self.assertRaisesMessage(ValidationError, "Rentalars als Buchhaltungsprogramm verwenden"):
            datev.check_period(accounting, datetime.date(2027, 3, 1), datetime.date(2027, 3, 31))

    def test_off_the_head_suggests_no_invoice(self) -> None:
        self._switch_off()
        kinds = services.makeable_kinds()
        self.assertIsNone(suggested_document(ProjectStatus.RETURNED, kinds))
        self.assertEqual(suggested_document(ProjectStatus.OUT, kinds), DocumentKind.DELIVERY_NOTE)

    def test_a_project_is_closed_without_an_invoice(self) -> None:
        self._switch_off()
        project = make_project("Ohne Rechnung", customer=self.customer, status=ProjectStatus.RETURNED)
        project_services.change_status(project, ProjectStatus.CLOSED, rights=ALL_RIGHTS)
        self.assertEqual(Project.objects.get(pk=project.pk).status, ProjectStatus.CLOSED)
