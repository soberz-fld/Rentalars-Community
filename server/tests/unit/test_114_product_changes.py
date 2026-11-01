# SPDX-License-Identifier: GPL-3.0-or-later
"""Changes of products in projects that are not confirmed yet (PRJ-072, PRJ-137, PRJ-138).

* The line remembers what it took over (``product_seen``) and the changes of the product are found: name, unit, tax
  rate, billing mode and price.
* Taking over, keeping the own values, "all that are not set by hand", the price right, crew lines.
* The people of the project are told once, not for confirmed projects and not for a new product.
"""

from __future__ import annotations

import datetime
import importlib
from decimal import Decimal

from django.apps import apps as django_apps

from rentalars.accounts.rights import Rights
from rentalars.masterdata.models import TaxRate
from rentalars.notifications.models import Kind, Notification
from rentalars.products.models import BillingMode, ProductKind, SurchargeType
from rentalars.projects.duplicate import duplicate_project
from rentalars.projects.models import MaterialLine, ProjectAccessLevel, ProjectMembership, ProjectStatus
from rentalars.projects.product_changes import (
    changes_of_product,
    count_changes,
    product_changes,
    take_over_changes,
)
from rentalars.projects.product_notice import tell_projects_about
from rentalars.projects.services import change_status, update_line
from tests.helpers import ALL_RIGHTS, RentalarsTestCase, add_line, at, job_function, make_project, make_user, plan, unit

D = Decimal

NO_PRICES = Rights(module_levels=dict(ALL_RIGHTS.module_levels), special_rights=frozenset())


class ProductChangeBase(RentalarsTestCase):
    """An inquiry with one line of a lamp."""

    def setUp(self) -> None:
        super().setUp()
        from tests.unit.test_051_lines import flat

        self.project = make_project(status=ProjectStatus.INQUIRY)
        self.lamp = flat("L-010", "20.00", name="Lampe")
        self.line = add_line(self.project, self.lamp, 4).line

    def change(self, **fields: object) -> None:
        for name, value in fields.items():
            setattr(self.lamp, name, value)
        self.lamp.save()

    def only_change(self):  # type: ignore[no-untyped-def]
        [found] = product_changes(self.project, ALL_RIGHTS)
        return found


class FindingChangesTests(ProductChangeBase):
    def test_a_new_line_remembers_its_product(self) -> None:
        self.assertEqual(
            self.line.product_seen,
            {
                "name": "Lampe",
                "unit": self.lamp.unit_id,
                "tax_rate": self.lamp.tax_rate_id,
                "billing_mode": BillingMode.FLAT,
            },
        )
        self.assertEqual(product_changes(self.project, ALL_RIGHTS), [])

    def test_a_new_name_is_found_and_taken_over(self) -> None:
        self.change(name="Lampe LED")
        found = self.only_change()
        [part] = found.fields
        self.assertEqual((part.field, part.old, part.new, part.by_hand), ("name", "Lampe", "Lampe LED", False))
        self.assertIsNone(found.price)
        result = take_over_changes(self.project, rights=ALL_RIGHTS, automatic=True)
        self.assertEqual((result.taken_over, result.kept), (1, 0))
        self.line.refresh_from_db()
        self.assertEqual((self.line.title, self.line.product_seen["name"]), ("Lampe LED", "Lampe LED"))
        self.assertEqual(product_changes(self.project, ALL_RIGHTS), [])

    def test_unit_and_tax_rate_are_found_with_their_names(self) -> None:
        meter = unit("Meter")
        reduced = TaxRate.objects.create(name="Ermäßigt", rate=D("7"))
        self.change(unit=meter, tax_rate=reduced)
        found = self.only_change()
        self.assertEqual(sorted(found.field_names), ["tax_rate", "unit"])
        take_over_changes(self.project, rights=ALL_RIGHTS, keys=[found.key])
        self.line.refresh_from_db()
        self.assertEqual((self.line.unit, self.line.tax_rate), (meter, reduced))
        self.assertEqual(product_changes(self.project, ALL_RIGHTS), [])

    def test_billing_mode_is_followed_by_a_rented_line(self) -> None:
        from tests.helpers import make_product

        rented = make_product("L-020", price="15.00", billing_mode=BillingMode.DAILY_PER_PIECE)
        line = add_line(self.project, rented, 2).line
        rented.billing_mode = BillingMode.FLAT
        rented.save()
        [found] = [c for c in product_changes(self.project, ALL_RIGHTS) if c.line.pk == line.pk]
        self.assertEqual(found.field_names, ["billing_mode"])
        take_over_changes(self.project, rights=ALL_RIGHTS, automatic=True)
        line.refresh_from_db()
        self.assertEqual(line.billing_mode, BillingMode.FLAT)

    def test_price_and_texts_come_together_and_the_discount_stays(self) -> None:
        update_line(self.line, rights=ALL_RIGHTS, discount_percent=D("10"))
        self.change(name="Lampe LED", price=D("25.00"))
        found = self.only_change()
        self.assertEqual((found.field_names, found.price.new_price), (["name"], D("25.00")))
        take_over_changes(self.project, rights=ALL_RIGHTS, automatic=True)
        self.line.refresh_from_db()
        self.assertEqual(
            (self.line.title, self.line.unit_price, self.line.discount_percent), ("Lampe LED", D("25.00"), D("10.00"))
        )

    def test_a_title_changed_by_hand_is_not_taken_over_automatically(self) -> None:
        update_line(self.line, rights=ALL_RIGHTS, title="Lampe für Bühne")
        self.assertEqual(product_changes(self.project, ALL_RIGHTS), [])  # the product did not change
        self.change(name="Lampe LED")
        found = self.only_change()
        self.assertTrue(found.set_by_hand)
        self.assertEqual(take_over_changes(self.project, rights=ALL_RIGHTS, automatic=True).taken_over, 0)
        self.line.refresh_from_db()
        self.assertEqual(self.line.title, "Lampe für Bühne")
        # Taking it over line by line works, and so does keeping the own title.
        self.assertEqual(take_over_changes(self.project, rights=ALL_RIGHTS, keep=[found.key]).kept, 1)
        self.line.refresh_from_db()
        self.assertEqual((self.line.title, self.line.product_seen["name"]), ("Lampe für Bühne", "Lampe LED"))
        self.assertEqual(product_changes(self.project, ALL_RIGHTS), [])
        self.change(name="Lampe LED 2")
        found = self.only_change()
        self.assertEqual(take_over_changes(self.project, rights=ALL_RIGHTS, keys=[found.key]).taken_over, 1)
        self.line.refresh_from_db()
        self.assertEqual(self.line.title, "Lampe LED 2")

    def test_everything_takes_over_lines_set_by_hand_too(self) -> None:
        update_line(self.line, rights=ALL_RIGHTS, unit_price=D("18.00"))
        self.change(price=D("25.00"))
        self.assertEqual(take_over_changes(self.project, rights=ALL_RIGHTS, automatic=True).taken_over, 0)
        self.assertEqual(take_over_changes(self.project, rights=ALL_RIGHTS, everything=True).taken_over, 1)
        self.line.refresh_from_db()
        self.assertEqual(self.line.unit_price, D("25.00"))

    def test_taking_over_and_keeping_the_same_line_is_refused(self) -> None:
        from django.core.exceptions import ValidationError

        self.change(name="Lampe LED")
        found = self.only_change()
        with self.assertRaises(ValidationError):
            take_over_changes(self.project, rights=ALL_RIGHTS, keys=[found.key], keep=[found.key])

    def test_lines_without_memory_count_as_set_by_hand(self) -> None:
        MaterialLine.objects.filter(pk=self.line.pk).update(product_seen={})
        self.assertEqual(product_changes(self.project, ALL_RIGHTS), [])  # equal to the product: nothing to point out
        self.change(name="Lampe LED")
        found = self.only_change()
        self.assertTrue(found.fields[0].by_hand)

    def test_a_confirmed_project_is_not_pointed_out(self) -> None:
        change_status(self.project, ProjectStatus.CONFIRMED, rights=ALL_RIGHTS)
        self.change(name="Lampe LED")
        self.project.refresh_from_db()
        self.assertEqual(count_changes(self.project, ALL_RIGHTS), 0)
        self.assertEqual(len(product_changes(self.project, ALL_RIGHTS)), 1)  # on request it is still known

    def test_confirmed_with_details_open_is_still_pointed_out(self) -> None:
        """PRJ-072: "Bestätigt – Einzelheiten offen" is not fully confirmed – the changes are pointed out."""
        change_status(self.project, ProjectStatus.CONFIRMED_OPEN, rights=ALL_RIGHTS)
        self.change(name="Lampe LED")
        self.project.refresh_from_db()
        self.assertEqual(count_changes(self.project, ALL_RIGHTS), 1)
        self.assertEqual({project.pk for project in changes_of_product(self.lamp, ALL_RIGHTS)}, {self.project.pk})
        result = take_over_changes(self.project, rights=ALL_RIGHTS, automatic=True)
        self.assertEqual(result.taken_over, 1)

    def test_a_text_line_and_a_line_without_product_are_left_alone(self) -> None:
        from rentalars.projects.services import add_text_line

        add_text_line(self.project, title="Bühne")
        add_line(self.project, None, 1, title="Eigene Position")
        self.change(name="Lampe LED")
        self.assertEqual(len(product_changes(self.project, ALL_RIGHTS)), 1)

    def test_a_duplicated_project_keeps_the_memory(self) -> None:
        self.change(name="Lampe LED")
        copy = duplicate_project(
            self.project, name="Kopie", start=at(20), end=at(22), rights=ALL_RIGHTS, user=None, with_material=True
        )
        [found] = product_changes(copy, ALL_RIGHTS)
        self.assertEqual(found.field_names, ["name"])
        self.assertFalse(found.fields[0].by_hand)


class ReviewTests(ProductChangeBase):
    def test_the_same_name_typed_by_hand_is_no_difference(self) -> None:
        update_line(self.line, rights=ALL_RIGHTS, title="Lampe LED")
        self.change(name="Lampe LED")
        self.assertEqual(product_changes(self.project, ALL_RIGHTS), [])

    def test_a_billing_mode_that_cannot_be_applied_stops_asking(self) -> None:
        from tests.helpers import make_product

        rented = make_product("L-020", price="15.00", billing_mode=BillingMode.DAILY_PER_PIECE)
        line = add_line(self.project, rented, 2).line
        rented.billing_mode = BillingMode.FLAT
        rented.price = None
        rented.save()
        self.assertEqual([c.line.pk for c in product_changes(self.project, ALL_RIGHTS)], [line.pk])
        take_over_changes(self.project, rights=ALL_RIGHTS, automatic=True)
        self.assertEqual(product_changes(self.project, ALL_RIGHTS), [])

    def test_the_percentage_of_a_surcharge_follows_the_product(self) -> None:
        from rentalars.projects.models import MaterialLine as Line
        from tests.helpers import make_product

        night = make_product(
            "A-002",
            "Nachtzuschlag",
            price=None,
            kind=ProductKind.SURCHARGE,
            surcharge_type=SurchargeType.PERCENT,
            surcharge_percent=D("25"),
        )
        line = add_line(self.project, night, 1).line
        self.assertEqual(D(line.product_seen["surcharge_percent"]), D("25"))
        self.assertEqual([c for c in product_changes(self.project, ALL_RIGHTS) if c.line.pk == line.pk], [])
        night.surcharge_percent = D("30")
        night.save()
        [found] = [c for c in product_changes(self.project, ALL_RIGHTS) if c.line.pk == line.pk]
        self.assertEqual(
            (found.field_names, found.fields[0].old, found.fields[0].new), (["surcharge_percent"], "25 %", "30 %")
        )
        self.assertEqual([c for c in product_changes(self.project, NO_PRICES) if c.line.pk == line.pk], [])
        take_over_changes(self.project, rights=ALL_RIGHTS, automatic=True)
        self.assertEqual(Line.objects.get(pk=line.pk).surcharge_percent, D("30.00"))


class PriceRightTests(ProductChangeBase):
    def test_prices_are_looked_at_only_with_the_price_right(self) -> None:
        self.change(price=D("25.00"))
        self.assertEqual(product_changes(self.project, NO_PRICES), [])
        self.assertEqual(product_changes(self.project, None), [])
        self.assertEqual(len(product_changes(self.project, ALL_RIGHTS)), 1)

    def test_without_the_price_right_the_texts_come_along_and_the_price_stays_pending(self) -> None:
        self.change(price=D("25.00"), name="Lampe LED")
        [found] = product_changes(self.project, NO_PRICES)
        self.assertEqual((found.field_names, found.price), (["name"], None))
        take_over_changes(self.project, rights=NO_PRICES, automatic=True)
        self.line.refresh_from_db()
        self.assertEqual((self.line.title, self.line.unit_price), ("Lampe LED", D("20.00")))
        [rest] = product_changes(self.project, ALL_RIGHTS)  # the price is still waiting for who may take it
        self.assertEqual((rest.field_names, rest.price.new_price), ([], D("25.00")))


class CrewLineTests(RentalarsTestCase):
    def test_a_crew_line_follows_the_price_of_its_service_product(self) -> None:
        project = make_project(status=ProjectStatus.OPTION)
        function = job_function("Tontechnik", price="40.00")
        line = plan(project, function)
        function.service_product.price = D("45.00")
        function.service_product.save()
        [found] = product_changes(project, ALL_RIGHTS)
        self.assertEqual((found.key, found.field_names, found.price.new_price), (f"c{line.pk}", [], D("45.00")))
        self.assertEqual(product_changes(project, NO_PRICES), [])
        take_over_changes(project, rights=ALL_RIGHTS, automatic=True)
        line.refresh_from_db()
        self.assertEqual(line.unit_price, D("45.00"))


class OfAProductTests(ProductChangeBase):
    def test_changes_of_product_and_only_product(self) -> None:
        from tests.unit.test_051_lines import flat

        other_product = flat("L-011", "10.00", name="Kabel")
        other_line = add_line(self.project, other_product, 1).line
        second = make_project(status=ProjectStatus.OPTION)
        add_line(second, self.lamp, 1)
        confirmed = make_project(status=ProjectStatus.CONFIRMED)
        add_line(confirmed, self.lamp, 1)
        other_product.name = "Kabel 5 m"
        other_product.save()
        self.change(name="Lampe LED")
        found = changes_of_product(self.lamp, ALL_RIGHTS)
        self.assertEqual({project.pk for project in found}, {self.project.pk, second.pk})  # not the confirmed one
        take_over_changes(self.project, rights=ALL_RIGHTS, automatic=True, only_product=self.lamp)
        other_line.refresh_from_db()
        self.line.refresh_from_db()
        self.assertEqual((self.line.title, other_line.title), ("Lampe LED", "Kabel"))


class MigrationTests(RentalarsTestCase):
    def test_lines_that_equal_their_product_get_a_memory_and_the_others_do_not(self) -> None:
        from tests.unit.test_051_lines import flat

        project = make_project(status=ProjectStatus.INQUIRY)
        product = flat("L-030", "10.00", name="Spot")
        same = add_line(project, product, 1).line
        edited = add_line(project, product, 1).line
        MaterialLine.objects.filter(pk__in=[same.pk, edited.pk]).update(product_seen={})
        MaterialLine.objects.filter(pk=edited.pk).update(title="Spot für die Bühne")
        migration = importlib.import_module("rentalars.projects.migrations.0036_product_seen_0114")
        migration.note_what_was_taken_over(django_apps, None)
        same.refresh_from_db()
        edited.refresh_from_db()
        self.assertEqual(same.product_seen["name"], "Spot")
        self.assertNotIn("name", edited.product_seen)
        self.assertEqual(edited.product_seen["unit"], product.unit_id)


class NotificationTests(ProductChangeBase):
    def setUp(self) -> None:
        super().setUp()
        self.manager = make_user("manager")
        self.editor = make_user("editor")
        self.reader = make_user("reader")
        self.project.manager = self.manager
        self.project.save()
        ProjectMembership.objects.create(project=self.project, user=self.editor, level=ProjectAccessLevel.EDIT)
        ProjectMembership.objects.create(project=self.project, user=self.reader, level=ProjectAccessLevel.READ)

    def notices(self) -> list[Notification]:
        return list(Notification.objects.filter(kind=Kind.PRODUCT_CHANGE).order_by("user__username"))

    def test_saving_a_changed_product_tells_manager_and_editors_once(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            self.change(name="Lampe LED")
        found = self.notices()
        self.assertEqual([n.user.username for n in found], ["editor", "manager"])
        self.assertEqual(found[0].project, self.project)
        self.assertIn("Lampe LED", found[0].title)
        self.assertTrue(found[0].url.endswith("#product-changes"))
        self.assertNotIn("25", found[0].body)
        # A second change while the first is unread: nobody is told again.
        with self.captureOnCommitCallbacks(execute=True):
            self.change(price=D("25.00"))
        self.assertEqual(len(self.notices()), 2)
        # After reading, and after the quiet hour, the next change is told again.
        long_ago = self.project.created_at - datetime.timedelta(days=1)
        Notification.objects.filter(kind=Kind.PRODUCT_CHANGE).update(read_at=long_ago, created_at=long_ago)
        with self.captureOnCommitCallbacks(execute=True):
            self.change(price=D("26.00"))
        self.assertEqual(len(self.notices()), 4)

    def test_a_product_that_changed_nothing_for_the_project_tells_nobody(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            self.change(description="Neu beschrieben")
        self.assertEqual(self.notices(), [])

    def test_saving_a_product_without_a_followed_change_tells_nobody(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            self.change(is_active=False)
            self.change(note="Neu")
        self.assertEqual(self.notices(), [])

    def test_nobody_is_told_again_within_the_quiet_hour_even_if_read(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            self.change(name="Lampe LED")
        Notification.objects.filter(kind=Kind.PRODUCT_CHANGE).update(read_at=self.project.created_at)
        with self.captureOnCommitCallbacks(execute=True):
            self.change(name="Lampe LED 2")
        self.assertEqual(len(self.notices()), 2)

    def test_a_price_change_is_not_told_to_who_may_not_see_prices(self) -> None:
        from rentalars.accounts.models import Role

        Role.objects.create(name="Planung ohne Preise", module_levels={"projects": 2})
        planner = make_user("planer", roles=("Planung ohne Preise",))
        ProjectMembership.objects.create(project=self.project, user=planner, level=ProjectAccessLevel.EDIT)
        with self.captureOnCommitCallbacks(execute=True):
            self.change(price=D("25.00"))
        self.assertNotIn("planer", [n.user.username for n in self.notices()])
        with self.captureOnCommitCallbacks(execute=True):
            self.change(name="Lampe LED")  # a name everybody sees
        self.assertIn("planer", [n.user.username for n in self.notices()])

    def test_a_project_with_details_open_is_told(self) -> None:
        """PRJ-138: the notification also goes for "Bestätigt – Einzelheiten offen"."""
        change_status(self.project, ProjectStatus.CONFIRMED_OPEN, rights=ALL_RIGHTS)
        with self.captureOnCommitCallbacks(execute=True):
            self.change(name="Lampe LED")
        self.assertTrue(self.notices())

    def test_confirmed_projects_and_new_products_tell_nobody(self) -> None:
        from tests.unit.test_051_lines import flat

        change_status(self.project, ProjectStatus.CONFIRMED, rights=ALL_RIGHTS)
        with self.captureOnCommitCallbacks(execute=True):
            self.change(name="Lampe LED")
            flat("L-040", "10.00")
        self.assertEqual(self.notices(), [])

    def test_the_function_returns_how_many_projects_were_told(self) -> None:
        self.change(name="Lampe LED")
        self.assertEqual(tell_projects_about(self.lamp.pk), 1)
        self.assertEqual(tell_projects_about(self.lamp.pk), 0)  # unread notices are waiting
        self.assertEqual(tell_projects_about(0), 0)

    def test_a_failing_notification_never_reaches_the_person_who_saved(self) -> None:
        from unittest import mock

        with (
            mock.patch("rentalars.projects.product_notice.tell_projects_about", side_effect=RuntimeError("boom")),
            self.assertLogs("rentalars.projects.product_notice", level="ERROR"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.change(name="Lampe LED")  # saved, no error
        self.lamp.refresh_from_db()
        self.assertEqual(self.lamp.name, "Lampe LED")

    def test_the_kind_can_be_switched_off_like_any_other(self) -> None:
        from rentalars.notifications import services

        services.set_preference(self.manager, Kind.PRODUCT_CHANGE, in_app=False, by_email=False)
        with self.captureOnCommitCallbacks(execute=True):
            self.change(name="Lampe LED")
        self.assertEqual([n.user.username for n in self.notices()], ["editor"])


_ = ProductKind  # (kept for readers: the kinds a product can have)
