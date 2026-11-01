# SPDX-License-Identifier: GPL-3.0-or-later
"""Subprojects everywhere else (PRJ-029, PRJ-044, PRJ-048, PRJ-060, PRJ-076).

The whole project "Stadtfest" (9th–14th) with the stages "Marktplatz"
(10th–12th) and "Schlosspark" (12th–14th), as in ``test_060_subprojects``:
duplicated, saved as template, in the calendar and the timelines, in the
search, the shortages, the time entry and the correspondence.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError

from rentalars.accounts.rights import rights_of
from rentalars.api.models import WebhookDelivery
from rentalars.availability.services import open_shortages, utilization_with_demands
from rentalars.core.search import global_search
from rentalars.mail.fetching import fetch_mail
from rentalars.mail.models import ProjectMail
from rentalars.personnel.calendars import deployment_event, deployment_lines
from rentalars.personnel.models import Person
from rentalars.projects import family_labels, services
from rentalars.projects.duplicate import copy_project
from rentalars.projects.models import CrewLine, MaterialLine, Project, ProjectPhase, ProjectStatus
from rentalars.projects.pricing import compute_project_prices
from rentalars.projects.project_templates import apply_template, save_as_template
from rentalars.schedule import calendars, timelines
from rentalars.schedule import services as services_schedule
from rentalars.schedule.services import Scale
from rentalars.schedule.timelines import product_timeline
from rentalars.timetracking.forms import TimeEntryForm
from tests.helpers import (
    ALL_RIGHTS,
    add_line,
    at,
    make_person,
    make_project,
    make_stock,
    make_user,
    plan,
    record_time,
    set_clock,
)
from tests.mailbox import FakeMailbox, configure_mailbox, make_mail
from tests.unit.test_060_subprojects import FamilyTestCase
from tests.unit.test_060_webhooks import make_hook


class DuplicatingWholeProjectsTests(FamilyTestCase):
    """PRJ-029, PRJ-044: a whole project is copied with its parts, take-overs included."""

    def setUp(self) -> None:
        super().setUp()
        self.spot = make_stock("L-100", 6, "Spot")
        self.power = make_stock("S-100", 1, "Stromverteiler")
        add_line(self.whole, self.power, 1)
        self.source_line = add_line(self.market, self.spot, 6).line
        self.taken = services.take_over_line(self.source_line, self.park, rights=ALL_RIGHTS).line
        ProjectPhase.objects.create(project=self.park, kind="setup", start=at(12, 12), end=at(12, 18))
        plan(self.park, "Stagehand", start=at(12, 12), end=at(12, 20))
        self.paula = make_user("paula")

    def copy(self, **options: object) -> object:
        values = {
            "name": "Stadtfest 2028",
            "start": at(9, 12, year=2028),
            "end": at(14, 18, year=2028),
            "with_crew": True,
            "rights": ALL_RIGHTS,
            "user": self.paula,
            **options,
        }
        return copy_project(self.whole, **values)

    def test_the_parts_come_along_with_their_place_and_length(self) -> None:
        result = self.copy()
        whole = result.project
        self.assertIsNone(whole.parent)
        self.assertEqual([part.name for part in result.parts], ["Bühne Marktplatz", "Bühne Schlosspark"])
        market, park = result.parts
        self.assertEqual((market.number, park.number), (f"{whole.number}-1", f"{whole.number}-2"))
        self.assertEqual((market.start, market.end), (at(10, 8, year=2028), at(12, 8, year=2028)))
        self.assertEqual((park.start, park.end), (at(12, 12, year=2028), at(14, 12, year=2028)))
        self.assertEqual((park.parent, park.customer, park.status), (whole, self.customer, ProjectStatus.INQUIRY))
        self.assertEqual(park.phases.get().start, at(12, 12, year=2028))
        self.assertEqual(CrewLine.objects.get(project=park).start, at(12, 12, year=2028))
        self.assertEqual(whole.material_lines.get().product, self.power)
        # The presets come from the copy of the whole project: its manager is whoever duplicates.
        self.assertEqual((whole.manager, park.manager), (self.paula, self.paula))

    def test_taken_over_lines_take_over_from_the_copies(self) -> None:
        result = self.copy()
        market, park = result.parts
        source = market.material_lines.get()
        taken = park.material_lines.get()
        self.assertEqual(taken.taken_over_from, source)
        self.assertEqual(result.dropped_takeovers, 0)
        # Charged once, as in the original.
        self.assertEqual(compute_project_prices(park).by_line_id[taken.pk].amount, Decimal("0"))
        # The originals are untouched.
        self.taken.refresh_from_db()
        self.assertEqual(self.taken.taken_over_from, self.source_line)

    def test_without_the_parts_only_the_whole_project(self) -> None:
        result = self.copy(with_subprojects=False)
        self.assertEqual(result.parts, [])
        self.assertFalse(result.project.subprojects.exists())

    def test_a_shorter_period_cuts_the_parts(self) -> None:
        result = self.copy(start=at(9, 12, year=2028), end=at(13, 12, year=2028))
        park = result.parts[1]
        self.assertEqual((park.start, park.end), (at(12, 12, year=2028), at(13, 12, year=2028)))

    def test_a_part_keeps_its_own_manager_and_cancelled_parts_stay_behind(self) -> None:
        stage_manager = make_user("sven")
        services.update_project(self.market, manager=stage_manager)
        extra = services.create_subproject(self.whole, name="Bühne abgesagt")
        services.change_status(extra, ProjectStatus.CANCELLED, rights=ALL_RIGHTS)
        result = self.copy()
        self.assertEqual([part.name for part in result.parts], ["Bühne Marktplatz", "Bühne Schlosspark"])
        self.assertEqual(result.parts[0].manager, stage_manager)
        # Of a festival cancelled as a whole, every stage comes along.
        services.change_status(self.whole, ProjectStatus.CANCELLED, rights=ALL_RIGHTS)
        self.whole.refresh_from_db()
        self.assertEqual(
            len(self.copy(name="Stadtfest 2029", start=at(9, 12, year=2029), end=at(14, 18, year=2029)).parts), 3
        )


class DuplicatingPartsTests(FamilyTestCase):
    """PRJ-029, PRJ-044: a part becomes a new part of the same whole project, or a project of its own."""

    def setUp(self) -> None:
        super().setUp()
        self.spot = make_stock("L-100", 10, "Spot")
        self.source_line = add_line(self.market, self.spot, 10).line
        self.taken = services.take_over_line(self.source_line, self.park, rights=ALL_RIGHTS, quantity=4).line

    def copy(self, **options: object) -> object:
        values = {
            "name": "Bühne Hof",
            "start": at(13, 8),
            "end": at(14, 12),
            "rights": ALL_RIGHTS,
            "user": None,
            **options,
        }
        return copy_project(self.park, **values)

    def test_a_new_part_of_the_same_whole_project(self) -> None:
        result = self.copy()
        part = result.project
        self.assertEqual((part.parent, part.number, part.name), (self.whole, f"{self.whole.number}-3", "Bühne Hof"))
        # Six pieces are still left on the source line: the copy takes over too.
        line = part.material_lines.get()
        self.assertEqual((line.taken_over_from, line.quantity), (self.source_line, Decimal("4")))
        self.assertEqual(result.dropped_takeovers, 0)

    def test_a_take_over_that_no_longer_fits_becomes_a_normal_line(self) -> None:
        third = services.create_subproject(self.whole, name="Bühne 3", start=at(13, 8), end=at(14, 8))
        services.take_over_line(self.source_line, third, rights=ALL_RIGHTS, quantity=4)
        result = self.copy()
        line = result.project.material_lines.get()
        self.assertIsNone(line.taken_over_from)
        self.assertEqual(result.dropped_takeovers, 1)
        self.assertGreater(compute_project_prices(result.project).net_total, 0)

    def test_the_period_lies_within_that_of_the_whole_project(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            self.copy(start=at(14, 8), end=at(16, 8))
        self.assertIn("start", caught.exception.message_dict)
        self.assertFalse(Project.objects.filter(name="Bühne Hof").exists())

    def test_a_project_of_its_own(self) -> None:
        result = self.copy(as_subproject=False, start=at(20, 8), end=at(22, 8))
        project = result.project
        self.assertIsNone(project.parent)
        self.assertEqual(project.customer, self.customer)
        self.assertEqual(project.status, ProjectStatus.INQUIRY)
        line = project.material_lines.get()
        self.assertIsNone(line.taken_over_from)
        self.assertEqual(result.dropped_takeovers, 1)
        self.assertFalse(MaterialLine.objects.filter(taken_over_from__project=project).exists())


class TemplatesOfWholeProjectsTests(FamilyTestCase):
    """PRJ-076 with PRJ-044, PRJ-060: a template holds one project; a take-over is a normal line there."""

    def setUp(self) -> None:
        super().setUp()
        self.spot = make_stock("L-100", 6, "Spot")
        add_line(self.whole, make_stock("S-100", 1, "Stromverteiler"), 1)
        self.source_line = add_line(self.market, self.spot, 6).line
        services.take_over_line(self.source_line, self.park, rights=ALL_RIGHTS)

    def test_a_template_of_the_whole_project_keeps_only_its_own_lines(self) -> None:
        template = save_as_template(self.whole, name="Stadtfest", rights=ALL_RIGHTS)
        self.assertEqual(
            [line["product"] for line in template.content["lines"]], [self.whole.material_lines.get().product_id]
        )

    def test_a_taken_over_line_becomes_a_normal_line(self) -> None:
        template = save_as_template(self.park, name="Bühne", rights=ALL_RIGHTS)
        self.assertNotIn("taken_over_from", template.content["lines"][0])
        target = make_project("Weinfest", start=at(20, 12), end=at(22, 12))
        apply_template(template, target, rights=ALL_RIGHTS)
        line = target.material_lines.get()
        self.assertEqual((line.product, line.quantity, line.taken_over_from), (self.spot, 6, None))
        self.assertGreater(compute_project_prices(target).net_total, 0)

    def test_a_template_applied_to_a_part(self) -> None:
        source = make_project("Bühne 2026", start=at(1, 12), end=at(3, 12))
        add_line(source, self.spot, 2, start=at(2, 12), end=at(3, 12))
        template = save_as_template(source, name="Bühne", rights=ALL_RIGHTS)
        part = services.create_subproject(self.whole, name="Bühne Hof", start=at(11, 12), end=at(13, 12))
        result = apply_template(template, part, rights=ALL_RIGHTS)
        self.assertEqual(result.lines, 1)
        line = part.material_lines.get()
        # The place relative to the start of the part, as everywhere (PRJ-029).
        self.assertEqual((line.start, line.end), (at(12, 12), at(13, 12)))


class LabelsTests(FamilyTestCase):
    """PRJ-044: a part is named with its whole project, the same way everywhere."""

    def test_the_words(self) -> None:
        whole = self.whole.number
        self.assertEqual(family_labels.part_of(self.whole), "")
        self.assertEqual(family_labels.part_of(self.market), f"Teil von {whole} Stadtfest")
        self.assertEqual(family_labels.project_label(self.market), f"{whole}-1 Bühne Marktplatz (Stadtfest)")
        self.assertEqual(family_labels.project_label(self.whole), f"{whole} Stadtfest")
        self.assertEqual(family_labels.short_name(self.park), "Bühne Schlosspark (Stadtfest)")

    def test_parts_right_after_their_whole_project(self) -> None:
        between = make_project("Weinfest", start=at(10, 8), end=at(11, 8), customer=self.customer)
        ten = [services.create_subproject(self.whole, name=f"Bühne {number}") for number in range(3, 11)][-1]
        projects = Project.objects.filter(pk__in=[self.whole.pk, self.market.pk, self.park.pk, ten.pk, between.pk])
        ordered = family_labels.whole_first(projects.order_by("start", "number"))
        self.assertEqual(ordered[:3], [self.whole, self.market, self.park])
        self.assertEqual(ordered[3:], [ten, between])
        # A part without its whole project in the list keeps its place.
        self.assertEqual(family_labels.whole_first([between, self.park]), [between, self.park])


class CalendarTests(FamilyTestCase):
    """PRJ-044 in the calendar, the timeline and the personnel plan (PRJ-028, VFG-014, VFG-020 to VFG-022)."""

    def test_month_bars_name_the_whole_project_without_further_queries(self) -> None:
        with self.assertNumQueries(2):
            weeks = calendars.month_weeks(Project.objects.all(), 2027, 3)
        segments = [segment for week in weeks for segment in week.segments if segment.project == self.market]
        self.assertEqual(segments[0].label, "Bühne Marktplatz (Stadtfest)")
        self.assertIn(f"Teil von {self.whole.number} Stadtfest", segments[0].title)
        whole = next(segment for week in weeks for segment in week.segments if segment.project == self.whole)
        self.assertEqual(whole.label, "Stadtfest")

    def test_the_week_names_the_whole_project_without_further_queries(self) -> None:
        ProjectPhase.objects.create(project=self.park, kind="setup", start=at(12, 12), end=at(12, 18))
        with self.assertNumQueries(2):
            grid = calendars.week_grid(Project.objects.all(), at(8).date())
        labels = {segment.label for segment in grid.all_day}
        self.assertIn("Bühne Schlosspark (Stadtfest)", labels)
        phase = next(block for column in grid.columns for block in column.blocks if block.is_phase)
        self.assertEqual(phase.label, "Aufbau · Bühne Schlosspark (Stadtfest)")

    def test_the_timeline_has_the_parts_right_after_their_whole_project(self) -> None:
        make_project("Weinfest", start=at(10, 8), end=at(11, 8), customer=self.customer)
        days = services_schedule.day_range(at(8).date(), 14)
        with self.assertNumQueries(2):
            rows = services_schedule.project_timeline(Project.objects.all(), days)
        self.assertEqual([project.name for project, _bars in rows][:4], [
            "Stadtfest", "Bühne Marktplatz", "Bühne Schlosspark", "Weinfest"
        ])  # fmt: skip
        market_bar = rows[1][1][0]
        self.assertEqual(
            market_bar.title, f"Bestätigt – Preise und Einzelheiten offen · Teil von {self.whole.number} Stadtfest"
        )

    def test_the_personnel_plan_names_the_whole_project(self) -> None:
        anna = make_person("Anna Becker", rates={"Stagehand": "20.00"})
        plan(self.park, "Stagehand", anna, start=at(12, 12), end=at(12, 20))
        days = services_schedule.day_range(at(8).date(), 7)
        with self.assertNumQueries(4):
            (row,) = services_schedule.personnel_rows(Person.objects.filter(pk=anna.pk), Scale(days=days))
        self.assertEqual((row.bars[0].label, row.bars[0].title), (
            f"{self.park.number} Stagehand", "Bühne Schlosspark (Stadtfest) · Fr 12.03., 12:00 Uhr bis 20:00 Uhr"
        ))  # fmt: skip


class ProductTimelineTests(FamilyTestCase):
    """VFG-019 with PRJ-060: taken-over pieces are a bar from the end of the line they come from."""

    def setUp(self) -> None:
        super().setUp()
        self.spot = make_stock("L-100", 6, "Spot")
        self.source_line = add_line(self.market, self.spot, 6).line
        services.take_over_line(self.source_line, self.park, rights=ALL_RIGHTS)
        self.days = services_schedule.day_range(at(8).date(), 9)

    def test_the_take_over_starts_where_the_source_ends(self) -> None:
        visible = {self.market.pk, self.park.pk}
        timeline = product_timeline(self.spot, self.days, visible)
        rows = {row.label: row for row in timeline.rows}
        market = rows[f"{self.market.number} Bühne Marktplatz"]
        park = rows[f"{self.park.number} Bühne Schlosspark"]
        self.assertEqual(park.sublabel, f"Teil von {self.whole.number} Stadtfest")
        (bar,) = park.bars
        # From the 12th (the end of the market's line) to the 14th: one continuous bar.
        self.assertEqual((bar.first, bar.last), (5, 7))
        self.assertEqual(bar.label, "6× übernommen")
        self.assertIn("takeover", bar.css)
        self.assertIn(f"übernommen von {self.market.number}", bar.title)
        self.assertEqual([(bar.first, bar.last, bar.label) for bar in market.bars], [(3, 5, "6×")])
        # Never more than six pieces at a time: the pieces are the same.
        self.assertTrue(all(load.free >= 0 for load in timeline.rows[0].loads))

    def test_one_query_more_only_when_parts_are_among_the_demands(self) -> None:
        _loads, demands = utilization_with_demands([self.spot.pk], self.days)
        with self.assertNumQueries(1):
            self.assertEqual(len(timelines._family_lines(demands[self.spot.pk])), 2)
        other = make_stock("K-100", 4, "Kabel")
        add_line(make_project("Weinfest", start=at(10), end=at(11)), other, 2)
        _loads, demands = utilization_with_demands([other.pk], self.days)
        with self.assertNumQueries(0):
            self.assertEqual(timelines._family_lines(demands[other.pk]), {})


class SearchAndListsTests(FamilyTestCase):
    """PRJ-044, PRJ-047, PRJ-057: the search, the shortages, the time entry name the whole project."""

    def test_the_search_finds_parts_by_the_name_of_the_whole_project(self) -> None:
        (group,) = [
            group for group in global_search("Stadtfest", ALL_RIGHTS, make_user("paula")) if group.kind == "projects"
        ]
        hits = {hit.id: hit for hit in group.hits}
        self.assertEqual(set(hits), {self.whole.pk, self.market.pk, self.park.pk})
        self.assertEqual(hits[self.market.pk].subtitle, f"Teil von {self.whole.number} Stadtfest · Stadt Musterstadt")
        self.assertEqual(hits[self.whole.pk].subtitle, "Stadt Musterstadt")

    def test_a_shortage_caused_by_another_part(self) -> None:
        spot = make_stock("L-100", 6, "Spot")
        spot.buffer_after_hours = Decimal("24")
        spot.save()
        add_line(self.market, spot, 6)
        line = add_line(self.park, spot, 6).line
        shortage = next(item for item in open_shortages(projects=Project.objects.all()) if item.line == line)
        self.assertEqual((shortage.quantity, shortage.held_by_other_parts), (6, 6))
        self.assertEqual(shortage.project.parent, self.whole)

    def test_the_time_entry_offers_the_part_with_its_whole_project(self) -> None:
        user = make_user("carla", roles=("Crew",))
        carla = make_person("Carla Crew", user=user, rates={"Stagehand": "20.00"})
        plan(self.park, "Stagehand", carla, start=at(12, 12), end=at(12, 20))
        form = TimeEntryForm(person=carla, rights=rights_of(user), user=user)
        labels = [label for _group, options in form.fields["project"].choices for _value, label in options]
        self.assertIn(f"{self.park.number} Bühne Schlosspark (Stadtfest)", labels)


class MailOfPartsTests(FamilyTestCase):
    """PRJ-044, EML-009: a mail tagged with the number of a part lands in the part."""

    def test_the_tag_of_a_part(self) -> None:
        configure_mailbox()
        fetch_mail(force=True, opener=FakeMailbox(make_mail(f"Bühnenplan [RL#{self.market.number}]")))
        mail = ProjectMail.objects.get()
        self.assertEqual(mail.project, self.market)
        self.assertEqual(self.market.mail_tag, f"[RL#{self.whole.number}-1]")


class WebhooksOfPartsTests(FamilyTestCase):
    """API-012 with PRJ-044, PRJ-048: events of a part name the whole project."""

    def test_status_change_and_approved_time_of_a_part(self) -> None:
        make_hook("project.status_changed", "time_entry.approved")
        services.change_status(self.park, ProjectStatus.CONFIRMED, rights=ALL_RIGHTS)
        carla = make_person("Carla Crew", rates={"Stagehand": "20.00"})
        plan(self.park, "Stagehand", carla, start=at(12, 12), end=at(12, 20))
        set_clock(at(28, 18))
        record_time(carla, self.park, "Stagehand", at(12, 12), at(12, 20), approve=True)
        expected = {"id": self.whole.pk, "number": self.whole.number}
        for event in ("project.status_changed", "time_entry.approved"):
            delivery = WebhookDelivery.objects.get(event=event)
            self.assertEqual(delivery.data["project"]["id"], self.park.pk, event)
            self.assertEqual(delivery.data["project"]["parent_project"], expected, event)


class DeploymentCalendarTests(FamilyTestCase):
    """PER-023 with PRJ-048: the calendar entry of a deployment in a part names the whole project."""

    def test_summary_and_description(self) -> None:
        carla = make_person("Carla Crew", rates={"Stagehand": "20.00"})
        plan(self.park, "Stagehand", carla, start=at(12, 12), end=at(12, 20))
        (line,) = deployment_lines(carla)
        with self.assertNumQueries(0):
            event = deployment_event(line)
        label = f"{self.park.number} Bühne Schlosspark (Stadtfest)"
        self.assertEqual(str(event["SUMMARY"]), f"Stagehand – {label}")
        self.assertIn(f"Projekt: {label}", str(event["DESCRIPTION"]))
