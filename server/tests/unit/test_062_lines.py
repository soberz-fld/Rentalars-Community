# SPDX-License-Identifier: GPL-3.0-or-later
"""Lines of the planning: several at once (PRJ-082), alternatives (PRJ-083), subrentals as parts of
their line (PRJ-084), the MVR file kept with the project (PRJ-086)."""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from rentalars.accounts.rights import rights_of
from rentalars.core.audit import acting_as
from rentalars.core.models import AuditLogEntry
from rentalars.core.uploads import validate_document_upload
from rentalars.documents.content import build_priced, only_groups
from rentalars.masterdata.models import Supplier
from rentalars.packing.models import PackEntry, Packlist
from rentalars.products.models import BillingMode
from rentalars.projects import mvr, services
from rentalars.projects.duplicate import duplicate_project
from rentalars.projects.lines import (
    BulkAction,
    alternative_choices,
    change_lines,
    duplicate_line,
    group_alternative_choices,
)
from rentalars.projects.models import GroupKind, LineVariant, MaterialLine, ProjectStatus, SubrentalStatus
from rentalars.projects.planning import build_planning
from rentalars.projects.price_pdf import render_price_overview_csv
from rentalars.projects.pricing import compute_project_prices
from rentalars.projects.project_templates import apply_template, save_as_template
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    add_group,
    add_line,
    at,
    make_product,
    make_project,
    make_stock,
    make_user,
)
from tests.unit.test_mvr_import import sample_plot

D = Decimal


def flat(article_number: str, price: str = "100.00") -> object:
    """A product billed as a flat price: amounts are quantity × price."""
    return make_product(article_number, price=price, billing_mode=BillingMode.FLAT)


class LinesTestCase(RentalarsTestCase):
    """A project with two groups and a few lines."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.light = add_group(self.project, "Licht")
        self.sound = add_group(self.project, "Ton")
        self.spot = add_line(self.project, flat("L-010"), 2, group=self.light).line
        self.wash = add_line(self.project, flat("L-020", "50.00"), 4, group=self.light).line
        self.speaker = add_line(self.project, flat("T-010", "80.00"), 2, group=self.sound).line
        self.loose = add_line(self.project, flat("K-010", "5.00"), 10).line

    def refreshed(self, *lines: MaterialLine) -> list[MaterialLine]:
        for line in lines:
            line.refresh_from_db()
        return list(lines)


class BulkChangeTests(LinesTestCase):
    """PRJ-082: one thing done with several lines, each through the service for a single line."""

    def test_optional_and_normal_again(self) -> None:
        result = change_lines(self.project, [self.spot.pk, self.wash.pk], BulkAction.OPTIONAL, rights=ALL_RIGHTS)
        self.assertEqual(result.changed_ids, [self.spot.pk, self.wash.pk])
        self.assertEqual({line.variant for line in self.refreshed(self.spot, self.wash)}, {LineVariant.OPTIONAL})
        # Already optional: unchanged, not skipped.
        again = change_lines(self.project, [self.spot.pk], BulkAction.OPTIONAL, rights=ALL_RIGHTS)
        self.assertEqual((again.changed, again.skipped, again.unchanged), ([], [], [again.unchanged[0]]))
        back = change_lines(self.project, [self.spot.pk, self.wash.pk], BulkAction.NORMAL, rights=ALL_RIGHTS)
        self.assertEqual(len(back.changed), 2)
        self.assertEqual({line.variant for line in self.refreshed(self.spot, self.wash)}, {LineVariant.NORMAL})
        # The planning shows again what counts.
        self.assertEqual(compute_project_prices(self.project).net_total, D("200") + D("200") + D("160") + D("50"))

    def test_the_history_names_every_line(self) -> None:
        user = make_user("bea")
        with acting_as(user):
            change_lines(self.project, [self.spot.pk, self.wash.pk], BulkAction.OPTIONAL, rights=ALL_RIGHTS)
        entries = AuditLogEntry.objects.filter(
            content_type__model="materialline", object_id__in=[str(self.spot.pk), str(self.wash.pk)]
        )
        changed = {entry.object_id for entry in entries if "variant" in entry.changes and entry.actor == user}
        self.assertEqual(changed, {str(self.spot.pk), str(self.wash.pk)})

    def test_alternative_to_a_line(self) -> None:
        result = change_lines(
            self.project,
            [self.wash.pk, self.spot.pk, self.speaker.pk],
            BulkAction.ALTERNATIVE,
            rights=ALL_RIGHTS,
            alternative_to=self.spot,
        )
        self.assertEqual(sorted(result.changed_ids), sorted([self.wash.pk, self.speaker.pk]))
        self.assertEqual([skipped.line for skipped in result.skipped], [self.spot])
        wash, speaker = self.refreshed(self.wash, self.speaker)
        self.assertEqual((wash.variant, wash.alternative_to), (LineVariant.ALTERNATIVE, self.spot))
        self.assertEqual(speaker.alternative_to, self.spot)
        # Normal again: nothing to replace any more.
        change_lines(self.project, [self.wash.pk], BulkAction.NORMAL, rights=ALL_RIGHTS)
        self.wash.refresh_from_db()
        self.assertEqual((self.wash.variant, self.wash.alternative_to), ("", None))

    def test_alternative_needs_a_line_that_may_be_replaced(self) -> None:
        with self.assertRaises(ValidationError):
            change_lines(self.project, [self.wash.pk], BulkAction.ALTERNATIVE, rights=ALL_RIGHTS)
        change_lines(self.project, [self.wash.pk], BulkAction.ALTERNATIVE, rights=ALL_RIGHTS, alternative_to=self.spot)
        self.wash.refresh_from_db()
        with self.assertRaises(ValidationError):  # an alternative itself
            change_lines(
                self.project, [self.speaker.pk], BulkAction.ALTERNATIVE, rights=ALL_RIGHTS, alternative_to=self.wash
            )
        other = add_line(make_project("Anderes"), flat("L-030"), 1).line
        with self.assertRaises(ValidationError):
            change_lines(
                self.project, [self.speaker.pk], BulkAction.ALTERNATIVE, rights=ALL_RIGHTS, alternative_to=other
            )

    def test_move_into_a_subgroup_and_out_of_all_groups(self) -> None:
        front = add_group(self.project, "Front", parent=self.light)
        result = change_lines(
            self.project, [self.spot.pk, self.speaker.pk], BulkAction.MOVE, rights=ALL_RIGHTS, group=front
        )
        self.assertEqual(len(result.changed), 2)
        self.assertEqual({line.group for line in self.refreshed(self.spot, self.speaker)}, {front})
        self.assertLessEqual({self.light.pk, self.sound.pk, front.pk}, result.group_ids)
        change_lines(self.project, [self.spot.pk], BulkAction.MOVE, rights=ALL_RIGHTS, group=None)
        self.spot.refresh_from_db()
        self.assertIsNone(self.spot.group)

    def test_discount_needs_the_price_right(self) -> None:
        result = change_lines(
            self.project, [self.spot.pk, self.wash.pk], BulkAction.DISCOUNT, rights=ALL_RIGHTS, discount_percent=D("10")
        )
        self.assertEqual(len(result.changed), 2)
        self.assertEqual({line.discount_percent for line in self.refreshed(self.spot, self.wash)}, {D("10")})
        reader = rights_of(make_user("carl"))
        with self.assertRaises(ValidationError):
            change_lines(self.project, [self.spot.pk], BulkAction.DISCOUNT, rights=reader, discount_percent=D("5"))
        with self.assertRaises(ValidationError):
            change_lines(
                self.project, [self.spot.pk], BulkAction.DISCOUNT, rights=ALL_RIGHTS, discount_percent=D("120")
            )

    def test_delete_skips_issued_material_and_names_it(self) -> None:
        packlist = Packlist.objects.create(project=self.project)
        PackEntry.objects.create(packlist=packlist, line=self.wash, product=self.wash.product, issued_quantity=D("2"))
        result = change_lines(self.project, [self.spot.pk, self.wash.pk], BulkAction.DELETE, rights=ALL_RIGHTS)
        self.assertEqual(result.changed_ids, [self.spot.pk])
        self.assertEqual([skipped.line.pk for skipped in result.skipped], [self.wash.pk])
        self.assertIn("ausgegeben", result.skipped[0].reason)
        self.assertEqual(result.skipped[0].label, "4 × Produkt L-020")
        self.assertFalse(MaterialLine.objects.filter(pk=self.spot.pk).exists())
        self.assertTrue(MaterialLine.objects.filter(pk=self.wash.pk).exists())

    def test_issued_material_does_not_become_optional(self) -> None:
        packlist = Packlist.objects.create(project=self.project)
        PackEntry.objects.create(packlist=packlist, line=self.wash, product=self.wash.product, issued_quantity=D("1"))
        result = change_lines(self.project, [self.spot.pk, self.wash.pk], BulkAction.OPTIONAL, rights=ALL_RIGHTS)
        self.assertEqual(result.changed_ids, [self.spot.pk])
        self.assertEqual([skipped.line for skipped in result.skipped], [self.wash])

    def test_lines_of_another_project_are_refused(self) -> None:
        other = add_line(make_project("Anderes"), flat("L-030"), 1).line
        with self.assertRaises(ValidationError):
            change_lines(self.project, [self.spot.pk, other.pk], BulkAction.OPTIONAL, rights=ALL_RIGHTS)
        with self.assertRaises(ValidationError):
            change_lines(self.project, [], BulkAction.OPTIONAL, rights=ALL_RIGHTS)
        with self.assertRaises(ValidationError):
            change_lines(self.project, [self.spot.pk], "paint", rights=ALL_RIGHTS)

    def test_closed_projects_are_refused(self) -> None:
        self.project.status = ProjectStatus.CLOSED
        self.project.save()
        with self.assertRaises(ValidationError):
            change_lines(self.project, [self.spot.pk], BulkAction.OPTIONAL, rights=ALL_RIGHTS)


class BulkRulesOfSpecialLinesTests(RentalarsTestCase):
    """PRJ-082 with PRJ-060 and PRJ-084: what cannot be done with taken-over pieces and covering subrentals."""

    def setUp(self) -> None:
        super().setUp()
        self.whole = make_project("Festival", start=at(9, 12), end=at(14, 18))
        self.market = services.create_subproject(self.whole, name="Marktplatz", start=at(10, 8), end=at(12, 8))
        self.park = services.create_subproject(self.whole, name="Schlosspark", start=at(12, 12), end=at(14, 12))
        self.spots = make_stock("L-010", 6, "Spot")
        self.source = add_line(self.market, self.spots, 6).line
        self.taken = services.take_over_line(self.source, self.park, rights=ALL_RIGHTS).line

    def test_a_line_others_take_over_from_stays_counted(self) -> None:
        result = change_lines(self.market, [self.source.pk], BulkAction.OPTIONAL, rights=ALL_RIGHTS)
        self.assertEqual([skipped.line for skipped in result.skipped], [self.source])
        self.assertIn("Teilprojekte", result.skipped[0].reason)

    def test_taken_over_pieces_get_no_discount(self) -> None:
        result = change_lines(
            self.park, [self.taken.pk], BulkAction.DISCOUNT, rights=ALL_RIGHTS, discount_percent=D("5")
        )
        self.assertEqual(result.skipped[0].reason, "wird nicht berechnet")

    def test_works_in_a_subproject(self) -> None:
        extra = add_line(self.park, make_product("L-020", "Wash"), 2).line
        result = change_lines(self.park, [extra.pk], BulkAction.OPTIONAL, rights=ALL_RIGHTS)
        self.assertEqual(result.changed_ids, [extra.pk])

    def test_a_covering_subrental_follows_its_line(self) -> None:
        line = add_line(self.whole, self.spots, 8).line
        subrental = services.accept_subrental_suggestion(line, self.spots, 2, rights=ALL_RIGHTS)
        group = add_group(self.whole, "Licht")
        alone = change_lines(self.whole, [subrental.pk], BulkAction.MOVE, rights=ALL_RIGHTS, group=group)
        self.assertEqual([skipped.line for skipped in alone.skipped], [subrental])
        both = change_lines(self.whole, [line.pk, subrental.pk], BulkAction.MOVE, rights=ALL_RIGHTS, group=group)
        self.assertEqual(both.changed_ids, [line.pk])
        subrental.refresh_from_db()
        self.assertEqual(subrental.group, group)
        optional = change_lines(self.whole, [subrental.pk], BulkAction.OPTIONAL, rights=ALL_RIGHTS)
        self.assertEqual([skipped.line for skipped in optional.skipped], [subrental])
        discount = change_lines(
            self.whole, [subrental.pk], BulkAction.DISCOUNT, rights=ALL_RIGHTS, discount_percent=D("5")
        )
        self.assertEqual(len(discount.skipped), 1)


class AlternativeRulesTests(LinesTestCase):
    """PRJ-083: an alternative names the line or group it could replace."""

    def test_the_model_checks_the_reference(self) -> None:
        self.wash.alternative_to = self.spot
        with self.assertRaises(ValidationError):  # not an alternative
            self.wash.full_clean()
        self.wash.variant = LineVariant.ALTERNATIVE
        self.wash.full_clean()
        self.wash.alternative_to = self.wash
        with self.assertRaises(ValidationError):
            self.wash.full_clean()

    def test_naming_what_it_replaces_makes_a_line_an_alternative(self) -> None:
        services.update_line(self.wash, rights=ALL_RIGHTS, alternative_to=self.spot)
        self.wash.refresh_from_db()
        self.assertEqual(self.wash.variant, LineVariant.ALTERNATIVE)
        services.update_line(self.wash, rights=ALL_RIGHTS, variant=LineVariant.OPTIONAL)
        self.wash.refresh_from_db()
        self.assertIsNone(self.wash.alternative_to)

    def test_deleting_what_it_replaces_makes_the_alternative_optional(self) -> None:
        services.update_line(self.wash, rights=ALL_RIGHTS, alternative_to=self.spot)
        services.delete_line(self.spot)
        self.wash.refresh_from_db()
        self.assertEqual((self.wash.variant, self.wash.alternative_to), (LineVariant.OPTIONAL, None))

    def test_groups(self) -> None:
        services.update_group(self.sound, rights=ALL_RIGHTS, alternative_to=self.light)
        self.sound.refresh_from_db()
        self.assertEqual((self.sound.kind, self.sound.alternative_to), (GroupKind.ALTERNATIVE, self.light))
        front = add_group(self.project, "Front", parent=self.light)
        with self.assertRaises(ValidationError):  # below it
            services.update_group(front, rights=ALL_RIGHTS, alternative_to=self.light)
        with self.assertRaises(ValidationError):  # an alternative itself
            services.update_group(front, rights=ALL_RIGHTS, alternative_to=self.sound)
        # Front can name neither the group above it nor an alternative; Ton can name both lighting groups.
        self.assertEqual(group_alternative_choices(front), [])
        self.assertEqual([pk for pk, _label in group_alternative_choices(self.sound)], [self.light.pk, front.pk])
        # Optional again: nothing to replace.
        services.update_group(self.sound, rights=ALL_RIGHTS, kind=GroupKind.OPTIONAL)
        self.sound.refresh_from_db()
        self.assertIsNone(self.sound.alternative_to)

    def test_deleting_a_group_makes_its_alternatives_optional(self) -> None:
        services.update_group(self.sound, rights=ALL_RIGHTS, alternative_to=self.light)
        services.delete_group(self.light, keep_lines=False)
        self.sound.refresh_from_db()
        self.assertEqual((self.sound.kind, self.sound.alternative_to), (GroupKind.OPTIONAL, None))

    def test_the_choices_of_the_dialog(self) -> None:
        services.update_line(self.wash, rights=ALL_RIGHTS, alternative_to=self.spot)
        choices = alternative_choices(self.project, excluded={self.speaker.pk})
        self.assertEqual(
            choices,
            [
                ("Licht", [(self.spot.pk, "2 × Produkt L-010")]),
                ("Ohne Teilgruppe", [(self.loose.pk, "10 × Produkt K-010")]),
            ],
        )

    def test_copies_name_the_copies_of_what_they_replace(self) -> None:
        services.update_line(self.wash, rights=ALL_RIGHTS, alternative_to=self.spot)
        services.update_line(self.speaker, rights=ALL_RIGHTS, alternative_to=self.spot)
        # A line copied: the copy replaces the same line.
        copy = duplicate_line(self.wash, rights=ALL_RIGHTS).line
        self.assertEqual(copy.alternative_to, self.spot)
        # A group copied within the project: alternatives inside name the copies.
        group_copy = services.copy_group(self.light, self.project, rights=ALL_RIGHTS)
        copied = {line.title: line for line in group_copy.lines.all()}
        self.assertEqual(copied["Produkt L-020"].alternative_to, copied["Produkt L-010"])
        # Into another project: the speaker's counterpart stays behind – the copy becomes optional.
        other = make_project("Anderes")
        services.copy_group(self.sound, other, rights=ALL_RIGHTS)
        moved = other.material_lines.get()
        self.assertEqual((moved.variant, moved.alternative_to), (LineVariant.OPTIONAL, None))

    def test_a_duplicated_project_keeps_the_pairs(self) -> None:
        services.update_line(self.speaker, rights=ALL_RIGHTS, alternative_to=self.spot)
        services.update_group(self.sound, rights=ALL_RIGHTS, alternative_to=self.light)
        copy = duplicate_project(
            self.project, name="Kopie", start=at(20), end=at(22), rights=ALL_RIGHTS, user=None, with_material=True
        )
        speaker = copy.material_lines.get(title="Produkt T-010")
        self.assertEqual(speaker.alternative_to, copy.material_lines.get(title="Produkt L-010"))
        self.assertEqual(copy.groups.get(name="Ton").alternative_to, copy.groups.get(name="Licht"))

    def test_a_template_keeps_the_pairs(self) -> None:
        services.update_line(self.speaker, rights=ALL_RIGHTS, alternative_to=self.spot)
        services.update_group(self.sound, rights=ALL_RIGHTS, alternative_to=self.light)
        template = save_as_template(self.project, name="Mit Alternativen", rights=ALL_RIGHTS)
        target = make_project("Neu", start=at(20), end=at(22))
        apply_template(template, target, rights=ALL_RIGHTS)
        speaker = target.material_lines.get(title="Produkt T-010")
        self.assertEqual(speaker.alternative_to, target.material_lines.get(title="Produkt L-010"))
        self.assertEqual(target.groups.get(name="Ton").alternative_to, target.groups.get(name="Licht"))


class PlanningAndDocumentsTests(LinesTestCase):
    """PRJ-083 and PRJ-084 in the planning, the price calculation and the offer."""

    def test_the_planning_knows_what_an_alternative_replaces(self) -> None:
        services.update_line(self.wash, rights=ALL_RIGHTS, alternative_to=self.spot)
        services.update_group(self.sound, rights=ALL_RIGHTS, alternative_to=self.light)
        planning = build_planning(self.project)
        wash = next(planned for planned in planning.all_lines if planned.line.pk == self.wash.pk)
        self.assertEqual(wash.alternative_label, "2 × Produkt L-010")
        sound = next(group for group in planning.groups if group.group.pk == self.sound.pk)
        self.assertEqual(sound.alternative_to, self.light)

    def test_the_offer_names_the_position(self) -> None:
        services.update_line(self.wash, rights=ALL_RIGHTS, alternative_to=self.spot)
        content = build_priced(
            self.project, "offer", title="Angebot", number="A-1", issued_on=datetime.date(2027, 3, 1)
        )
        positions = {position.title: position for section in content.sections for position in section.positions}
        self.assertEqual(positions["Produkt L-010"].number, "1")
        self.assertEqual(positions["Produkt L-020"].variant_label, "Alternative zu Pos. 1")
        # DOK-013: only groups – the counted spotlight is summed up, so it is named by title.
        grouped = only_groups(content)
        positions = {position.title: position for section in grouped.sections for position in section.positions}
        self.assertNotIn("Produkt L-010", positions)
        self.assertEqual(positions["Produkt L-020"].variant_label, "Alternative zu „2 × Produkt L-010“")

    def test_the_price_overview_file_names_it(self) -> None:
        services.update_line(self.wash, rights=ALL_RIGHTS, alternative_to=self.spot)
        text = render_price_overview_csv(self.project, with_lines=True, rights=ALL_RIGHTS, user=None)
        self.assertIn("Produkt L-020 (Alternative zu „2 × Produkt L-010“)", text)

    def test_an_alternative_group_in_the_offer(self) -> None:
        services.update_group(self.sound, rights=ALL_RIGHTS, alternative_to=self.light)
        content = build_priced(
            self.project, "offer", title="Angebot", number="A-1", issued_on=datetime.date(2027, 3, 1)
        )
        sound = next(section for section in content.sections if section.title == "Ton")
        self.assertTrue(sound.optional)
        self.assertEqual(sound.alternative_to, "Alternative zu „Licht“")


class SubrentalAsPartOfTheLineTests(RentalarsTestCase):
    """PRJ-084: a subrental that covers a shortage is shown below its line and costs the customer nothing."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.light = add_group(self.project, "Licht")
        self.spots = make_stock("L-010", 4, "Spot", price="20.00")
        self.line = add_line(self.project, self.spots, 6, group=self.light).line

    def test_status_and_purchase_price_but_no_price_for_the_customer(self) -> None:
        before = compute_project_prices(self.project)
        subrental = services.accept_subrental_suggestion(
            self.line,
            self.spots,
            2,
            rights=ALL_RIGHTS,
            purchase_price=D("15.00"),
            status=SubrentalStatus.ORDERED,
            # PRJ-101: a status other than "open" needs the supplier.
            supplier=Supplier.objects.create(name="Verleih Nord"),
        )
        self.assertEqual((subrental.subrental_status, subrental.unit_price), (SubrentalStatus.ORDERED, D("0")))
        after = compute_project_prices(self.project)
        self.assertEqual(after.net_total, before.net_total)
        self.assertEqual(after.by_line_id[subrental.pk].amount, D("0"))
        self.assertEqual(after.subrental_cost, D("30.00"))

    def test_the_planning_shows_it_below_its_line_wherever_it_stands(self) -> None:
        subrental = services.accept_subrental_suggestion(self.line, self.spots, 2, rights=ALL_RIGHTS)
        sound = add_group(self.project, "Ton")
        MaterialLine.objects.filter(pk=subrental.pk).update(group=sound)  # as in older data
        planning = build_planning(self.project)
        light = next(group for group in planning.groups if group.group.pk == self.light.pk)
        main = next(planned for planned in light.lines if planned.line.pk == self.line.pk)
        self.assertEqual([part.line.pk for part in main.covering], [subrental.pk])
        self.assertTrue(main.covering[0].is_sub_row)
        self.assertIn(subrental.pk, [planned.line.pk for planned in planning.all_lines])

    def test_it_moves_with_its_line(self) -> None:
        subrental = services.accept_subrental_suggestion(self.line, self.spots, 2, rights=ALL_RIGHTS)
        sound = add_group(self.project, "Ton")
        services.update_line(self.line, rights=ALL_RIGHTS, group=sound)
        subrental.refresh_from_db()
        self.assertEqual(subrental.group, sound)
        services.arrange_lines(self.project, [(None, [self.line.pk])])
        subrental.refresh_from_db()
        self.assertIsNone(subrental.group)


class MvrFileTests(RentalarsTestCase):
    """PRJ-086: the imported MVR file is kept in the files of the project; MVR files can be uploaded by hand."""

    def test_the_name_starts_with_the_local_date_and_time(self) -> None:
        moment = timezone.make_aware(datetime.datetime(2026, 10, 13, 22, 15, 30))
        self.assertEqual(mvr.kept_file_name("Rig Stadtfest.mvr", moment), "20261013-221530_Rig Stadtfest.mvr")
        self.assertEqual(mvr.kept_file_name("C:\\Plots\\Rig.mvr", moment), "20261013-221530_Rig.mvr")

    def test_keep_file(self) -> None:
        project = make_project()
        user = make_user("bea")
        uploaded = SimpleUploadedFile("Rig.mvr", sample_plot(), content_type="application/zip")
        uploaded.read()  # read once, as the import does
        kept = mvr.keep_file(project, uploaded, user=user)
        self.assertRegex(kept.original_name, r"^\d{8}-\d{6}_Rig\.mvr$")
        self.assertEqual((kept.document_type, kept.visible_to_crew, kept.uploaded_by), (None, False, user))
        self.assertEqual(kept.size, len(sample_plot()))
        with kept.file.open("rb") as handle:
            self.assertEqual(handle.read(), sample_plot())

    def test_mvr_is_an_allowed_document(self) -> None:
        validate_document_upload(SimpleUploadedFile("Rig.mvr", b"PK\x03\x04", content_type="application/zip"))
