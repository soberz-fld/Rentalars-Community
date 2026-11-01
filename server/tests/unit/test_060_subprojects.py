# SPDX-License-Identifier: GPL-3.0-or-later
"""Subprojects (PRJ-031, PRJ-044 to PRJ-049) and material that moves between them (PRJ-060).

The example of the catalogue: the whole project "Stadtfest" from the 9th to
the 14th, with the stages "Marktplatz" (10th–12th) and "Schlosspark"
(12th–14th). The same six spotlights serve one stage after the other.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Level, Module, ProjectScope, rights_of
from rentalars.availability.engine import AvailabilityEngine
from rentalars.customers.models import AddressKind, Contact, CustomerAddress
from rentalars.projects import services
from rentalars.projects.access import (
    ProjectAccess,
    access_level,
    access_of_many,
    readable_projects,
    visible_projects,
)
from rentalars.projects.family import build_family, takeover_sources
from rentalars.projects.models import ProjectAccessLevel, ProjectMembership, ProjectStatus
from rentalars.projects.planning import build_planning
from rentalars.projects.pricing import compute_project_prices
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_line,
    at,
    make_customer,
    make_person,
    make_project,
    make_stock,
    make_user,
    plan,
)


class FamilyTestCase(RentalarsTestCase):
    """A whole project with two stages, one after the other."""

    def setUp(self) -> None:
        super().setUp()
        self.customer = make_customer("Stadt Musterstadt")
        self.contact = Contact.objects.create(customer=self.customer, name="Frau Kulturamt")
        self.whole = make_project("Stadtfest", start=at(9, 12), end=at(14, 18), customer=self.customer)
        self.whole.contact = self.contact
        self.whole.venue = "Innenstadt"
        self.whole.save()
        self.market = services.create_subproject(self.whole, name="Bühne Marktplatz", start=at(10, 8), end=at(12, 8))
        self.park = services.create_subproject(self.whole, name="Bühne Schlosspark", start=at(12, 12), end=at(14, 12))


class CreatingSubprojectsTests(FamilyTestCase):
    """PRJ-044, PRJ-045: numbering, what a part inherits and what it takes over as a preset."""

    def test_parts_are_numbered_after_the_whole_project(self) -> None:
        self.assertEqual(self.market.number, f"{self.whole.number}-1")
        self.assertEqual(self.park.number, f"{self.whole.number}-2")
        self.assertEqual(self.whole.family_ids(), [self.whole.pk, self.market.pk, self.park.pk])
        self.assertEqual(self.park.family_ids(), self.whole.family_ids())
        self.assertTrue(self.whole.has_subprojects)
        self.assertTrue(self.market.is_in_family)

    def test_a_part_inherits_customer_and_takes_over_presets(self) -> None:
        self.assertEqual(self.market.customer, self.customer)
        self.assertEqual(self.market.contact, self.contact)
        self.assertEqual(self.market.venue, "Innenstadt")
        self.assertEqual(self.market.manager, self.whole.manager)
        own = services.create_subproject(self.whole, name="Bühne 3", venue="Hof")
        self.assertEqual(own.venue, "Hof")
        self.assertEqual((own.start, own.end), (self.whole.start, self.whole.end))

    def test_a_part_starts_with_a_fitting_status(self) -> None:
        self.assertEqual(self.market.status, ProjectStatus.CONFIRMED_OPEN)
        inquiry = make_project("Anfrage", status=ProjectStatus.INQUIRY)
        self.assertEqual(services.create_subproject(inquiry, name="Teil").status, ProjectStatus.INQUIRY)

    def test_there_is_only_one_level(self) -> None:
        with self.assertRaises(ValidationError):
            services.create_subproject(self.market, name="Unterbühne")

    def test_a_cancelled_whole_project_gets_no_new_parts(self) -> None:
        services.change_status(self.whole, ProjectStatus.CANCELLED, rights=ALL_RIGHTS)
        with self.assertRaises(ValidationError):
            services.create_subproject(self.whole, name="Bühne 3")

    def test_a_part_lies_within_the_period_of_the_whole_project(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            services.create_subproject(self.whole, name="Zu früh", start=at(8, 12), end=at(10, 12))
        self.assertIn("start", caught.exception.message_dict)

    def test_customer_and_billing_cannot_be_changed_on_a_part(self) -> None:
        other = make_customer("Andere GmbH")
        services.update_project(self.market, customer=other, name="Marktplatz")
        self.market.refresh_from_db()
        self.assertEqual((self.market.customer, self.market.name), (self.customer, "Marktplatz"))
        self.market.customer = other
        with self.assertRaises(ValidationError):
            self.market.full_clean()

    def test_a_project_with_parts_cannot_become_a_part(self) -> None:
        other = make_project("Anderes Fest", start=at(1, 12), end=at(20, 12), customer=self.customer)
        self.whole.parent = other
        with self.assertRaises(ValidationError):
            self.whole.full_clean()

    def test_a_whole_project_with_parts_cannot_be_deleted(self) -> None:
        inquiry = make_project("Anfrage", status=ProjectStatus.INQUIRY)
        services.create_subproject(inquiry, name="Teil")
        with self.assertRaises(ValidationError):
            services.delete_project(inquiry)


class ChangingTheWholeProjectTests(FamilyTestCase):
    """PRJ-045: changes of the whole project reach its parts."""

    def test_a_new_customer_reaches_the_parts(self) -> None:
        other = make_customer("Neuer Veranstalter")
        address = CustomerAddress.objects.create(
            customer=other, kind=AddressKind.BILLING, street="Weg 1", city="Ort", is_default=True
        )
        services.update_project(self.whole, customer=other, contact=None)
        self.market.refresh_from_db()
        self.assertEqual(self.market.customer, other)
        self.assertEqual(self.market.billing_address, address)
        # The contact of the former customer does not fit any more.
        self.assertIsNone(self.market.contact)

    def test_moving_the_whole_period_moves_the_parts_and_their_lines(self) -> None:
        spot = make_stock("L-100", 6)
        line = add_line(self.market, spot, 2).line
        week = datetime.timedelta(days=7)
        services.update_project(self.whole, start=self.whole.start + week, end=self.whole.end + week)
        self.market.refresh_from_db()
        line.refresh_from_db()
        self.assertEqual((self.market.start, self.market.end), (at(17, 8), at(19, 8)))
        self.assertEqual((line.start, line.end), (at(17, 8), at(19, 8)))

    def test_shortening_the_period_past_a_part_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            services.update_project(self.whole, end=at(13, 12))
        self.whole.refresh_from_db()
        self.assertEqual(self.whole.end, at(14, 18))


class StatusOfWholeAndPartsTests(FamilyTestCase):
    """PRJ-044: every part has its own status, within the rules of the whole."""

    def test_cancelling_the_whole_project_cancels_its_parts(self) -> None:
        services.change_status(self.whole, ProjectStatus.CANCELLED, rights=ALL_RIGHTS)
        for part in (self.market, self.park):
            part.refresh_from_db()
            self.assertEqual(part.status, ProjectStatus.CANCELLED)

    def test_a_part_of_a_cancelled_whole_cannot_be_taken_up_alone(self) -> None:
        services.change_status(self.whole, ProjectStatus.CANCELLED, rights=ALL_RIGHTS)
        self.market.refresh_from_db()
        with self.assertRaises(ValidationError):
            services.change_status(self.market, ProjectStatus.INQUIRY, rights=ALL_RIGHTS)

    def test_the_whole_project_closes_after_its_parts(self) -> None:
        for project in (self.whole, self.market):
            project.status = ProjectStatus.RETURNED
            project.save()
        with self.assertRaises(ValidationError) as caught:
            services.change_status(self.whole, ProjectStatus.CLOSED, rights=ALL_RIGHTS)
        self.assertIn(self.park.number, " ".join(caught.exception.messages))

    def test_parts_follow_where_the_step_is_allowed(self) -> None:
        self.park.status = ProjectStatus.INQUIRY
        self.park.save()
        kept = services.change_family_status(self.whole, ProjectStatus.OUT, rights=ALL_RIGHTS)
        self.market.refresh_from_db()
        self.assertEqual(self.market.status, ProjectStatus.OUT)
        self.assertEqual(kept, [self.park.number])


class AccessToPartsTests(FamilyTestCase):
    """PRJ-049: access of the whole project holds in its parts and can be limited per part."""

    def setUp(self) -> None:
        super().setUp()
        Role.objects.create(
            name="Bühnenleitung extern",
            module_levels={Module.PROJECTS: int(Level.WRITE)},
            project_scope=ProjectScope.ASSIGNED,
        )
        self.external = make_user("erik", roles=("Bühnenleitung extern",))
        self.rights = rights_of(self.external)

    def level(self, project: object) -> ProjectAccess:
        return access_level(self.rights, self.external, project)

    def assert_lists_agree(self) -> None:
        """Lists, the API's many-at-once and the single answer say the same."""
        projects = [self.whole, self.market, self.park]
        many = access_of_many(self.rights, self.external, [project.pk for project in projects])
        visible = set(visible_projects(self.rights, self.external).values_list("pk", flat=True))
        readable = set(readable_projects(self.rights, self.external).values_list("pk", flat=True))
        for project in projects:
            single = self.level(project)
            self.assertEqual(many[project.pk], single, project.number)
            self.assertEqual(project.pk in visible, single > ProjectAccess.NONE, project.number)
            self.assertEqual(project.pk in readable, single >= ProjectAccess.READ, project.number)

    def test_a_membership_of_the_whole_project_holds_in_its_parts(self) -> None:
        ProjectMembership.objects.create(project=self.whole, user=self.external, level=ProjectAccessLevel.EDIT)
        self.assertEqual(self.level(self.market), ProjectAccess.EDIT)
        self.assertEqual(self.level(self.park), ProjectAccess.EDIT)
        self.assert_lists_agree()

    def test_a_part_can_limit_or_take_away_access(self) -> None:
        ProjectMembership.objects.create(project=self.whole, user=self.external, level=ProjectAccessLevel.EDIT)
        ProjectMembership.objects.create(project=self.market, user=self.external, level=ProjectAccessLevel.READ)
        ProjectMembership.objects.create(project=self.park, user=self.external, level=ProjectAccessLevel.NONE)
        self.assertEqual(self.level(self.whole), ProjectAccess.EDIT)
        self.assertEqual(self.level(self.market), ProjectAccess.READ)
        self.assertEqual(self.level(self.park), ProjectAccess.NONE)
        self.assert_lists_agree()

    def test_a_membership_of_one_part_opens_only_that_part(self) -> None:
        ProjectMembership.objects.create(project=self.park, user=self.external, level=ProjectAccessLevel.EDIT)
        self.assertEqual(self.level(self.park), ProjectAccess.EDIT)
        self.assertEqual(self.level(self.whole), ProjectAccess.NONE)
        self.assertEqual(self.level(self.market), ProjectAccess.NONE)
        self.assert_lists_agree()

    def test_crew_of_a_part_sees_its_deployment_even_without_access(self) -> None:
        crew = make_user("carla", roles=("Crew",))
        person = make_person("Carla Crew", user=crew, rates={"Stagehand": "20.00"})
        ProjectMembership.objects.create(project=self.park, user=crew, level=ProjectAccessLevel.NONE)
        plan(self.park, "Stagehand", person)
        self.assertEqual(access_level(rights_of(crew), crew, self.park), ProjectAccess.DEPLOYMENT)
        self.assertEqual(access_level(rights_of(crew), crew, self.market), ProjectAccess.NONE)

    def test_roles_for_all_projects_are_not_touched(self) -> None:
        manager = make_user("paula", roles=("Projektleitung",))
        ProjectMembership.objects.create(project=self.park, user=manager, level=ProjectAccessLevel.NONE)
        self.assertEqual(access_level(rights_of(manager), manager, self.park), ProjectAccess.EDIT)


class TakingOverMaterialTests(FamilyTestCase):
    """PRJ-060: the same pieces, one stage after the other."""

    def setUp(self) -> None:
        super().setUp()
        self.spot = make_stock("L-100", 6, "Spot")
        self.source = add_line(self.market, self.spot, 6).line

    def take_over(self, quantity: int = 6, project: object = None) -> object:
        return services.take_over_line(self.source, project or self.park, rights=ALL_RIGHTS, quantity=quantity)

    def test_a_line_takes_over_the_pieces_of_an_earlier_part(self) -> None:
        line = self.take_over().line
        self.assertEqual(line.taken_over_from, self.source)
        self.assertEqual((line.product, line.quantity), (self.spot, 6))
        self.assertEqual([candidate.pk for candidate in takeover_sources(self.park)], [])

    def test_not_more_than_the_line_has(self) -> None:
        self.take_over(4)
        with self.assertRaises(ValidationError):
            self.take_over(3)
        self.assertEqual([line.left_to_take_over for line in takeover_sources(self.park)], [2])

    def test_the_source_cannot_shrink_below_what_is_taken_over(self) -> None:
        self.take_over(4)
        with self.assertRaises(ValidationError):
            services.update_line(self.source, rights=ALL_RIGHTS, quantity=Decimal("3"))

    def test_only_from_an_earlier_line_of_the_same_whole_project(self) -> None:
        stranger = make_project("Fremd", start=at(1, 12), end=at(3, 12))
        foreign = add_line(stranger, self.spot, 2).line
        with self.assertRaises(ValidationError):
            services.take_over_line(foreign, self.park, rights=ALL_RIGHTS, quantity=1)
        later = add_line(self.park, self.spot, 2).line
        with self.assertRaises(ValidationError):
            services.take_over_line(later, self.market, rights=ALL_RIGHTS, quantity=1)

    def test_it_is_charged_once(self) -> None:
        line = self.take_over().line
        prices = compute_project_prices(self.park)
        self.assertEqual(prices.by_line_id[line.pk].amount, Decimal("0"))
        self.assertTrue(prices.by_line_id[line.pk].is_takeover)
        self.assertEqual(prices.net_total, Decimal("0"))
        self.assertGreater(compute_project_prices(self.market).net_total, 0)

    def test_the_planning_names_both_ends(self) -> None:
        line = self.take_over().line
        market = build_planning(self.market)
        self.assertEqual([taking.pk for taking in market.all_lines[0].handed_to], [line.pk])
        park = build_planning(self.park)
        self.assertEqual(park.all_lines[0].line.taken_over_from.project, self.market)


class AvailabilityOfTakenOverMaterialTests(FamilyTestCase):
    """PRJ-047, PRJ-060: one continuous reservation, no buffers in between, overlaps are shortages."""

    def setUp(self) -> None:
        super().setUp()
        self.spot = make_stock("L-100", 6, "Spot")
        # A day of buffer after every use: checking and cleaning in the warehouse (VFG-005).
        self.spot.buffer_after_hours = Decimal("24")
        self.spot.save()
        self.source = add_line(self.market, self.spot, 6).line

    def verdict(self, line: object) -> object:
        return AvailabilityEngine().project_availability(line.project, list(line.project.material_lines.all()))[line.pk]

    def test_without_take_over_the_buffer_makes_the_second_stage_short(self) -> None:
        line = add_line(self.park, self.spot, 6).line
        self.assertEqual(self.verdict(line).shortage_total, 6)
        self.assertEqual(self.verdict(line).main.family, 6)

    def test_taken_over_the_pieces_go_straight_on(self) -> None:
        line = services.take_over_line(self.source, self.park, rights=ALL_RIGHTS).line
        self.assertEqual(self.verdict(line).shortage_total, 0)
        self.assertEqual(self.verdict(self.source).shortage_total, 0)
        # The fast check of one line comes to the same verdict as the whole project (VFG-007).
        engine = AvailabilityEngine()
        self.assertEqual(engine.line_availability(line).shortage_total, 0)
        self.assertEqual(engine.line_availability(self.source).shortage_total, 0)

    def test_the_pieces_stay_out_between_the_stages(self) -> None:
        services.take_over_line(self.source, self.park, rights=ALL_RIGHTS)
        between = make_project("Dazwischen", start=at(12, 9), end=at(12, 11), customer=self.customer)
        line = add_line(between, self.spot, 1).line
        self.assertEqual(self.verdict(line).shortage_total, 1)
        free = AvailabilityEngine().availability([self.spot.pk], at(12, 9), at(12, 11), exclude_project_id=between.pk)[
            self.spot.pk
        ]
        self.assertEqual(free.free, 0)

    def test_overlapping_stages_are_short(self) -> None:
        services.update_project(self.park, start=at(11, 12))
        line = services.take_over_line(self.source, self.park, rights=ALL_RIGHTS).line
        self.assertEqual(self.verdict(line).shortage_total, 6)

    def test_an_inquiry_taking_over_does_not_free_the_buffer_of_others(self) -> None:
        """A part that reserves nothing does not take the pieces: the source keeps its buffer for others."""
        services.take_over_line(self.source, self.park, rights=ALL_RIGHTS)
        self.park.status = ProjectStatus.INQUIRY
        self.park.save()
        after = make_project("Danach", start=at(12, 12), end=at(12, 18), customer=self.customer)
        line = add_line(after, self.spot, 1).line
        self.assertEqual(self.verdict(line).shortage_total, 1)


class FamilyOverviewTests(FamilyTestCase):
    """PRJ-046: the whole project shows the sums of all parts, part by part."""

    def test_figures_of_every_part_and_their_sum(self) -> None:
        spot = make_stock("L-100", 6, "Spot")
        add_line(self.whole, make_stock("S-100", 1, "Stromverteiler"), 1)
        source = add_line(self.market, spot, 6).line
        services.take_over_line(source, self.park, rights=ALL_RIGHTS)
        plan(self.park, "Stagehand", planned_hours=Decimal("8"))
        family = build_family(self.market, rights=ALL_RIGHTS, user=make_user("paula", roles=("Projektleitung",)))
        self.assertEqual([part.project for part in family.parts], [self.whole, self.market, self.park])
        whole, market, park = family.parts
        self.assertTrue(whole.is_whole)
        self.assertEqual((market.lines, market.pieces), (1, 6))
        self.assertEqual((park.lines, park.takeovers, park.crew_lines, park.open_places), (1, 1, 1, 1))
        self.assertEqual(family.total.pieces, 13)
        self.assertEqual(family.total.net_total, whole.net_total + market.net_total + park.net_total)
        self.assertEqual(park.hours, Decimal("8"))

    def test_parts_without_access_are_left_out(self) -> None:
        Role.objects.create(
            name="Bühnenleitung extern",
            module_levels={Module.PROJECTS: int(Level.WRITE)},
            project_scope=ProjectScope.ASSIGNED,
        )
        external = make_user("erik", roles=("Bühnenleitung extern",))
        ProjectMembership.objects.create(project=self.whole, user=external, level=ProjectAccessLevel.READ)
        ProjectMembership.objects.create(project=self.park, user=external, level=ProjectAccessLevel.NONE)
        family = build_family(self.whole, rights=rights_of(external), user=external)
        self.assertEqual([part.project for part in family.parts], [self.whole, self.market])
        self.assertEqual(family.hidden, 1)
