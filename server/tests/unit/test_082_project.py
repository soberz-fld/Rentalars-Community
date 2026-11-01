# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "project": trips changed, removed and added by hand (PRJ-111), the customer of a service case
(PRJ-090), the crew on the timeline of Zeitplanung as in the personnel plan (VFG-035), the filters of
"Meine Einsätze" (UIX-043)."""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from rentalars.core.audit import acting_as
from rentalars.core.models import CompanyProfile
from rentalars.personnel.models import Absence, AvailabilityMark
from rentalars.projects import course, service_cases, trip_changes
from rentalars.projects.models import CaseStatus, PhaseKind, ProjectStatus, RequestStatus, TripAdjustment
from rentalars.projects.my_deployments import DeploymentFilterForm, filtered_lines, firmness
from rentalars.projects.trips import TripKind, computed_trips, trips_of
from rentalars.schedule import course_timeline
from rentalars.schedule.services import scale_from_request
from tests.helpers import RentalarsTestCase, at, make_customer, make_person, make_project, make_user, plan

WAREHOUSE = "Hafenstraße 1, 12345 Musterstadt"


def _scale(first: str = "2027-03-09", days: int = 4) -> object:
    scale, _navigation = scale_from_request(SimpleNamespace(GET={"from": first, "days": str(days)}))
    return scale


class TripCase(RentalarsTestCase):
    """A project with setup and teardown at the Stadthalle, from a warehouse in Musterstadt."""

    def setUp(self) -> None:
        super().setUp()
        profile = CompanyProfile.load()
        profile.warehouse_address = WAREHOUSE
        profile.save()
        self.user = make_user("paula")
        self.project = make_project(start=at(10, 8), end=at(12, 20), venue="Stadthalle, Marktplatz 1, Musterstadt")
        self.setup = course.add_phase(self.project, kind=PhaseKind.SETUP, start=at(10, 8), end=at(10, 16))
        self.teardown = course.add_phase(self.project, kind=PhaseKind.TEARDOWN, start=at(12, 14), end=at(12, 20))

    def keys(self, **kwargs: object) -> list[str]:
        return [trip.key for trip in trips_of(self.project, **kwargs)]


class TripKeyTests(TripCase):
    """PRJ-111: every determined trip has a key that its adjustment refers to."""

    def test_keys_of_the_determined_trips(self) -> None:
        self.assertEqual(
            self.keys(),
            [
                f"to_venue-{self.setup.pk}",
                f"from_venue-{self.setup.pk}",
                f"to_venue-{self.teardown.pk}",
                f"from_venue-{self.teardown.pk}",
            ],
        )
        self.assertEqual({trip.key for trip in computed_trips(self.project)}, set(self.keys()))

    def test_without_adjustments_one_query_more_than_before(self) -> None:
        with CaptureQueriesContext(connection) as determined:
            computed_trips(self.project)
        with CaptureQueriesContext(connection) as adjusted:
            trips_of(self.project)
        self.assertEqual(len(adjusted), len(determined) + 1)


class ChangeTripTests(TripCase):
    """PRJ-111: what is changed is stored, what stays as determined keeps following the phases."""

    def test_only_what_differs_is_stored(self) -> None:
        key = f"to_venue-{self.setup.pk}"
        trip = next(trip for trip in trips_of(self.project) if trip.key == key)
        adjustment = trip_changes.change_trip(
            self.project,
            key,
            user=self.user,
            start=trip.start,  # as determined
            origin=WAREHOUSE,  # as determined
            stops=["Baumarkt, Industriestraße 5, Musterstadt"],
            destination="Stadthalle, Lieferzufahrt Nord, Musterstadt",
            title=trip.title,
            note="Rampe hinten, Schlüssel beim Hausmeister",
        )
        self.assertIsNone(adjustment.start)
        self.assertEqual(adjustment.origin, "")
        self.assertEqual(adjustment.title, "")
        self.assertEqual(adjustment.stops, ["Baumarkt, Industriestraße 5, Musterstadt"])
        self.assertEqual(adjustment.changed_by, self.user)
        # The phase moves: the departure follows it, the changed destination stays.
        course.update_phase(self.setup, start=at(10, 10), end=at(10, 18))
        trip = next(trip for trip in trips_of(self.project) if trip.key == key)
        self.assertEqual(trip.start, at(10, 10))
        self.assertTrue(trip.is_changed)
        self.assertEqual(trip.destination.address, "Stadthalle, Lieferzufahrt Nord, Musterstadt")
        self.assertEqual([stop.address for stop in trip.stops], ["Baumarkt, Industriestraße 5, Musterstadt"])
        self.assertEqual(trip.note, "Rampe hinten, Schlüssel beim Hausmeister")
        self.assertEqual(trip.problems, [])

    def test_the_route_link_follows_the_change(self) -> None:
        """PRJ-111, UIX-033: the link names the changed destination and stops (from where the viewer is)."""
        key = f"from_venue-{self.teardown.pk}"
        trip_changes.change_trip(
            self.project, key, stops=["Wertstoffhof, Am Kanal 2, Musterstadt"], destination="Lager 2, Musterstadt"
        )
        trip = next(trip for trip in trips_of(self.project) if trip.key == key)
        query = parse_qs(urlparse(trip.route_url).query)
        self.assertEqual(query["destination"], ["Lager 2, Musterstadt"])
        self.assertEqual(query["waypoints"], ["Wertstoffhof, Am Kanal 2, Musterstadt"])

    def test_changed_back_to_the_determined_values_is_reset(self) -> None:
        key = f"to_venue-{self.setup.pk}"
        trip_changes.change_trip(self.project, key, note="Rampe")
        self.assertEqual(TripAdjustment.objects.count(), 1)
        self.assertIsNone(trip_changes.change_trip(self.project, key, note=""))
        self.assertFalse(TripAdjustment.objects.exists())

    def test_a_title_of_its_own_and_too_many_stops(self) -> None:
        key = f"to_venue-{self.setup.pk}"
        trip_changes.change_trip(self.project, key, title="Bühne liefern")
        self.assertEqual(next(trip for trip in trips_of(self.project) if trip.key == key).title, "Bühne liefern")
        with self.assertRaises(ValidationError) as caught:
            trip_changes.change_trip(self.project, key, stops=[f"Halt {number}" for number in range(10)])
        self.assertIn("stops", caught.exception.message_dict)

    def test_an_unknown_trip_and_a_closed_project(self) -> None:
        with self.assertRaises(ValidationError):
            trip_changes.change_trip(self.project, "to_venue-999999", note="x")
        self.project.status = ProjectStatus.CLOSED
        self.project.save()
        with self.assertRaises(ValidationError):
            trip_changes.change_trip(self.project, f"to_venue-{self.setup.pk}", note="x")
        self.assertFalse(TripAdjustment.objects.exists())

    def test_the_change_is_in_the_history_of_the_project(self) -> None:
        """PRJ-111, PRJ-032: logged as a change of the project."""
        from rentalars.core.models import AuditLogEntry

        with acting_as(self.user):
            trip_changes.change_trip(self.project, f"to_venue-{self.setup.pk}", note="Rampe")
        self.assertTrue(
            AuditLogEntry.objects.filter(
                parent_object_id=str(self.project.pk), object_repr__contains="to_venue"
            ).exists()
        )


class RemoveAndResetTripTests(TripCase):
    """PRJ-111: a removed trip stays removed – however the phases change – until it is reset."""

    def test_removed_stays_removed(self) -> None:
        key = f"from_venue-{self.setup.pk}"
        trip_changes.remove_trip(self.project, key, user=self.user)
        self.assertNotIn(key, self.keys())
        course.update_phase(self.setup, start=at(10, 9), end=at(10, 17))
        self.assertNotIn(key, self.keys())
        removed = [trip for trip in trips_of(self.project, with_removed=True) if trip.is_removed]
        self.assertEqual([trip.key for trip in removed], [key])
        trip = trip_changes.reset_trip(self.project, key)
        self.assertEqual((trip.key, trip.is_removed, trip.is_changed), (key, False, False))
        self.assertIn(key, self.keys())
        self.assertFalse(TripAdjustment.objects.exists())

    def test_reset_undoes_every_change(self) -> None:
        key = f"to_venue-{self.teardown.pk}"
        trip_changes.change_trip(self.project, key, destination="Anderswo 1", note="x")
        trip = trip_changes.reset_trip(self.project, key)
        self.assertEqual(trip.destination.address, "Stadthalle, Marktplatz 1, Musterstadt")
        self.assertEqual(trip.note, "")

    def test_a_removed_phase_leaves_its_adjustment_without_effect(self) -> None:
        trip_changes.change_trip(self.project, f"to_venue-{self.teardown.pk}", note="Rampe")
        course.delete_phase(self.teardown)
        self.assertEqual(len(trips_of(self.project)), 2)
        self.assertEqual(TripAdjustment.objects.count(), 1)


class OwnTripTests(TripCase):
    """PRJ-111: a trip added by hand – e.g. a second delivery."""

    def test_add_change_remove(self) -> None:
        adjustment = trip_changes.add_trip(
            self.project,
            user=self.user,
            start=at(11, 9),
            origin=WAREHOUSE,
            destination="Stadthalle, Marktplatz 1, Musterstadt",
            stops=["  Getränkehandel,   Ring 3 ", ""],
            title="Nachlieferung Kabel",
            note="Kiste 4",
        )
        key = f"own-{adjustment.pk}"
        trips = trips_of(self.project)
        own = next(trip for trip in trips if trip.key == key)
        self.assertEqual(
            (own.kind, own.title, own.is_own, own.is_changed), (TripKind.OWN, "Nachlieferung Kabel", True, False)
        )
        self.assertEqual([stop.address for stop in own.stops], ["Getränkehandel, Ring 3"])
        # In the order of time: between the trips of the setup and of the teardown.
        self.assertEqual([trip.key for trip in trips].index(key), 2)
        trip_changes.change_trip(self.project, key, start=at(11, 10), origin=WAREHOUSE, destination="Lager 2")
        own = next(trip for trip in trips_of(self.project) if trip.key == key)
        self.assertEqual((own.start, own.destination.address, own.stops), (at(11, 10), "Lager 2", []))
        with self.assertRaises(ValidationError):
            trip_changes.reset_trip(self.project, key)
        trip_changes.remove_trip(self.project, key)
        self.assertNotIn(key, self.keys(with_removed=True))
        self.assertFalse(TripAdjustment.objects.exists())

    def test_departure_start_and_destination_are_needed(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            trip_changes.add_trip(self.project, start=None, origin="", destination="")
        self.assertEqual(set(caught.exception.message_dict), {"start", "origin", "destination"})


class ServiceCaseCustomerTests(RentalarsTestCase):
    """PRJ-090: a service case needs a customer, like a project; older cases stay valid until edited."""

    def test_created_with_the_customer_required(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            service_cases.create_case(name="Spot flackert", customer_required=True)
        self.assertIn("customer", caught.exception.message_dict)
        case = service_cases.create_case(name="Spot flackert", customer=make_customer(), customer_required=True)
        self.assertEqual(case.case_status, CaseStatus.OPEN)

    def test_an_older_case_without_customer_asks_for_one_when_edited(self) -> None:
        old = service_cases.create_case(name="Kabel defekt", case_contact="Herr Meier")  # as made earlier
        old.full_clean()  # still valid
        service_cases.set_case_status(old, CaseStatus.IN_PROGRESS)  # the status changes without customer
        with self.assertRaises(ValidationError) as caught:
            service_cases.update_case(old, notes="Stecker getauscht")
        self.assertIn("customer", caught.exception.message_dict)
        service_cases.update_case(old, notes="Stecker getauscht", customer=make_customer())
        old.refresh_from_db()
        self.assertEqual(old.notes, "Stecker getauscht")

    def test_the_description_stays_optional(self) -> None:
        case = service_cases.create_case(name="Frage", customer=make_customer(), customer_required=True, notes="")
        service_cases.update_case(case, notes="")


class CrewPictureTests(RentalarsTestCase):
    """VFG-035: conflicts, warnings and availability on the timeline of a project, as in the personnel plan."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Firmenfeier", start=at(10, 8), end=at(12, 18))
        self.other = make_project("Messe", start=at(10, 8), end=at(10, 20))
        self.anna = make_person("Anna Becker", rates={"Stagehand": "20.00"})
        self.ben = make_person("Ben Wolf", rates={"Stagehand": "20.00"})
        self.overlapping = plan(self.project, "Stagehand", self.anna, start=at(10, 9), end=at(10, 13))
        plan(self.other, "Stagehand", self.anna, start=at(10, 12), end=at(10, 15))
        self.calm = plan(self.project, "Stagehand", self.ben, start=at(11, 9), end=at(11, 13))
        self.open = plan(self.project, "Stagehand", None, start=at(11, 9), end=at(11, 13))
        AvailabilityMark.objects.create(person=self.ben, start=at(11, 14), end=at(11, 18), state="limited")
        Absence.objects.create(person=self.ben, kind="vacation", start=at(12), end=at(13))
        self.lines = list(self.project.crew_lines.select_related("job_function", "person"))

    def test_conflicts_in_three_queries(self) -> None:
        with CaptureQueriesContext(connection) as queries:
            picture = course_timeline.crew_picture(self.lines, _scale(), with_availability=True)
        self.assertLessEqual(len(queries), 3)
        self.assertEqual(picture.involved, {self.overlapping.pk})
        self.assertEqual(picture.warnings, {self.anna.pk: ["double_booking"]})
        self.assertEqual(
            sorted(bar.css for bar in picture.availability[self.ben.pk]), ["absence", "availability is-limited"]
        )

    def test_rows_coloured_and_titled_as_in_the_personnel_plan(self) -> None:
        scale = _scale()
        picture = course_timeline.crew_picture(self.lines, scale, with_availability=True)
        rows = course_timeline.course_rows(self.project, [], self.lines, scale, crew=picture)
        anna = next(row for row in rows if row.label == "Anna Becker")
        self.assertEqual(anna.bars[0].css, "crew status-confirmed is-conflict")
        self.assertEqual(anna.bars[0].title, "Anna Becker · Stagehand · Mi 10.03., 9:00 Uhr bis 13:00 Uhr · Konflikt")
        self.assertTrue(anna.conflict)
        self.assertEqual(anna.warning_text, "Einsätze überschneiden sich")
        ben = next(row for row in rows if row.label == "Ben Wolf")
        self.assertFalse(ben.conflict)
        self.assertEqual(len(ben.availability), 2)
        open_row = next(row for row in rows if row.kind == "open")
        self.assertIsNone(open_row.availability)
        self.assertEqual(open_row.bars[0].css, "crew open-place")

    def test_without_the_right_to_read_the_personnel_no_availability(self) -> None:
        scale = _scale()
        picture = course_timeline.crew_picture(self.lines, scale, with_availability=False)
        self.assertIsNone(picture.availability)
        rows = course_timeline.course_rows(self.project, [], self.lines, scale, crew=picture)
        self.assertTrue(all(row.availability is None for row in rows))
        self.assertIn("is-conflict", next(row for row in rows if row.label == "Anna Becker").bars[0].css)

    def test_a_cancelled_project_is_no_conflict(self) -> None:
        self.other.status = ProjectStatus.CANCELLED
        self.other.save()
        picture = course_timeline.crew_picture(self.lines, _scale(), with_availability=False)
        self.assertEqual(picture.involved, set())

    def test_the_legend_of_the_personnel_plan(self) -> None:
        self.assertEqual(
            [label for _css, label in course_timeline.crew_legend(self.project)],
            ["fest", "Option", "Projekt-Anfrage", "angefragt", "Konflikt", "abgesagt", "offen"],
        )


class MyDeploymentFilterTests(RentalarsTestCase):
    """UIX-043: the filters of My area → Meine Einsätze."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_person("Anna Becker", rates={"Stagehand": "20.00"})
        self.past = plan(
            make_project("Gestern", start=at(1, 8, month=2), end=at(2, 18, month=2)), "Stagehand", self.anna
        )
        self.firm = plan(make_project("Stadtfest"), "Stagehand", self.anna)
        option = make_project("Hochzeit", start=at(20), end=at(21), status=ProjectStatus.OPTION)
        self.option = plan(option, "Stagehand", self.anna)
        self.option.request_status = RequestStatus.REQUESTED
        self.option.save()
        cancelled = make_project("Abgesagt", start=at(22), end=at(23), status=ProjectStatus.CANCELLED)
        plan(cancelled, "Stagehand", self.anna)
        self.own = self.anna.crew_lines.exclude(project__status=ProjectStatus.CANCELLED)

    def lines(self, **data: str) -> list[int]:
        form = DeploymentFilterForm(data, projects=[])
        return sorted(line.pk for line in filtered_lines(self.own, form))

    def test_period(self) -> None:
        self.assertEqual(self.lines(), sorted([self.firm.pk, self.option.pk]))
        self.assertEqual(self.lines(period="past"), [self.past.pk])
        self.assertEqual(self.lines(period="all"), sorted([self.past.pk, self.firm.pk, self.option.pk]))
        self.assertEqual(self.lines(period="all", since="2027-03-15", until="2027-03-31"), [self.option.pk])

    def test_state_request_and_project(self) -> None:
        self.assertEqual(self.lines(state="firm"), [self.firm.pk])
        self.assertEqual(self.lines(state="option"), [self.option.pk])
        self.assertEqual(self.lines(request="requested"), [self.option.pk])
        self.assertEqual(self.lines(request="none"), [self.firm.pk])
        form = DeploymentFilterForm({"project": str(self.firm.project_id)}, projects=[self.firm.project])
        self.assertEqual([line.pk for line in filtered_lines(self.own, form)], [self.firm.pk])
        self.assertEqual((firmness(self.firm), firmness(self.option)), ("firm", "option"))

    def test_a_date_that_is_no_date_filters_nothing_but_the_period(self) -> None:
        self.assertEqual(self.lines(since="31.02."), sorted([self.firm.pk, self.option.pk]))

    def test_the_period_is_twelve_hours_lenient_as_on_the_start_page(self) -> None:
        """A deployment that ended two hours ago still counts as coming."""
        from tests.helpers import clock

        recent = plan(
            make_project("Eben", start=clock() - datetime.timedelta(hours=8), end=clock()), "Stagehand", self.anna
        )
        self.assertIn(recent.pk, self.lines())


class ConflictFlagTests(RentalarsTestCase):
    """Review (VFG-032, VFG-035): the red fill and "Konflikt" in the hover come from the one flag."""

    def test_the_bar_marks_both(self) -> None:
        from rentalars.schedule.services import Bar

        bar = Bar(first=1, last=2, label="x", css="crew status-confirmed", title="Mi 10.03.", conflict=True)
        self.assertEqual((bar.css, bar.title), ("crew status-confirmed is-conflict", "Mi 10.03. · Konflikt"))
        calm = Bar(first=1, last=2, label="x", css="crew", title="Mi 10.03.")
        self.assertEqual((calm.css, calm.title), ("crew", "Mi 10.03."))

    def test_class_and_hover_agree_everywhere(self) -> None:
        """An overlap with another project's deployment, an absence, "nicht verfügbar" – in all three plans."""
        from rentalars.personnel.models import Person
        from rentalars.schedule import services, timelines

        anna = make_person("Anna Becker", rates={"Stagehand": "20.00"})
        mine = make_project("Eins", start=at(10, 8), end=at(12, 20))
        other = make_project("Zwei", start=at(10, 8), end=at(12, 20))
        plan(mine, "Stagehand", anna, start=at(10, 9), end=at(10, 13))
        plan(other, "Stagehand", anna, start=at(10, 12), end=at(10, 15))
        plan(mine, "Stagehand", anna, start=at(11, 9), end=at(11, 11))
        AvailabilityMark.objects.create(person=anna, start=at(11, 10), end=at(11, 12), state="unavailable")
        plan(mine, "Stagehand", anna, start=at(12, 17), end=at(12, 19))
        Absence.objects.create(person=anna, kind="vacation", start=at(12, 18), end=at(13))
        for scale in (_scale(), _scale("2027-03-10", 1)):
            bars = []
            for row in services.personnel_rows(Person.objects.filter(pk=anna.pk), scale):
                bars += row.bars + row.availability
            lines = list(mine.crew_lines.select_related("job_function", "person"))
            picture = course_timeline.crew_picture(lines, scale, with_availability=True)
            for row in course_timeline.course_rows(mine, [], lines, scale, crew=picture):
                bars += row.bars + (row.availability or [])
            self.assertGreaterEqual(sum("is-conflict" in bar.css for bar in bars), 6)
            for bar in bars:
                with self.subTest(bar=bar.title):
                    self.assertEqual("is-conflict" in bar.css.split(), bar.title.endswith("Konflikt"))
        timeline = timelines.person_timeline(anna, [at(day).date() for day in range(9, 14)], {mine.pk, other.pk})
        self.assertTrue(any("is-conflict" in bar.css for row in timeline.rows for bar in row.bars))
        for row in timeline.rows:
            for bar in row.bars:
                self.assertEqual("is-conflict" in bar.css.split(), bar.title.endswith("Konflikt"))
