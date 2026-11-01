# SPDX-License-Identifier: GPL-3.0-or-later
"""Smaller additions made while putting the parts together (MAT-061, PRJ-118)."""

from __future__ import annotations

import io
import os
import time

from django.core.management import call_command

from rentalars.material.purchases import PENDING_DAYS, pending_directory
from tests.helpers import RentalarsTestCase


class OldPurchaseInvoicesTests(RentalarsTestCase):
    """An invoice uploaded for "Kauf einpflegen" and never saved goes with the daily maintenance (MAT-061)."""

    def test_the_daily_maintenance_removes_them(self) -> None:
        folder = pending_directory()
        old, new, other = folder / f"{'a' * 32}.pdf", folder / f"{'b' * 32}.pdf", folder / "notes.txt"
        for path in (old, new, other):
            path.write_bytes(b"%PDF-1.4")
        past = time.time() - (PENDING_DAYS + 1) * 86400
        os.utime(old, (past, past))
        os.utime(other, (past, past))
        out = io.StringIO()
        call_command("run_daily_maintenance", stdout=out)
        self.assertIn("Deleted 1 invoices of purchases that were never saved.", out.getvalue())
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())
        self.assertTrue(other.exists())  # not one of ours


class OneMessageForAMoveTests(RentalarsTestCase):
    """A rental period moved with its schedule (VFG-026): the people planned hear of it once (PRJ-118)."""

    def test_two_phases_and_the_new_period_make_one_message_per_person(self) -> None:
        from rentalars.notifications.models import Kind, Notification
        from rentalars.projects import course, crew
        from rentalars.schedule.moves import PERIOD, MoveRequest, apply_move
        from tests.helpers import ALL_RIGHTS, at, make_person, make_project, make_user, plan

        project = make_project("Stadtfest", start=at(10, 8), end=at(12, 20))
        setup = course.add_phase(project, kind="setup", start=at(10, 8), end=at(10, 18))
        show = course.add_phase(project, kind="event", start=at(11, 10), end=at(11, 23))
        anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        tom = make_person("Tom Richter", rates={"Tontechnik": "30.00"})
        for phase in (setup, show):
            line = plan(project, "Tontechnik", anna, phase=phase, start=phase.start, end=phase.end)
            crew.update_crew_line(line, rights=ALL_RIGHTS, firm=True)
        # Tom is planned without phase and not asked; his line moves along as well.
        plan(project, "Tontechnik", tom, start=at(12, 8), end=at(12, 12))
        Notification.objects.all().delete()

        apply_move(
            MoveRequest(project=project, what=PERIOD, start=at(17, 8), end=at(19, 20)),
            rights=ALL_RIGHTS,
            user=make_user("paula"),
        )
        anna_got = list(Notification.objects.filter(user=anna.user).values_list("kind", flat=True))
        self.assertEqual(anna_got, [Kind.DEPLOYMENT_CHANGE])
        tom_got = list(Notification.objects.filter(user=tom.user).values_list("kind", flat=True))
        self.assertEqual(tom_got, [Kind.DEPLOYMENT_CHANGE])


class ReviewFindingsTests(RentalarsTestCase):
    """Found by the independent review and fixed while merging."""

    def test_asked_again_for_the_new_times_is_the_one_message_of_a_move(self) -> None:
        """PRJ-118, PER-034: an accepted line moved with the schedule – the new request, not also "neuer Zeitraum"."""
        from rentalars.notifications.models import Kind, Notification
        from rentalars.projects import crew
        from rentalars.schedule.moves import PERIOD, MoveRequest, apply_move
        from tests.helpers import ALL_RIGHTS, at, make_person, make_project, make_user, plan

        project = make_project("Stadtfest", start=at(10, 8), end=at(12, 20))
        anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"})
        line = plan(project, "Tontechnik", anna, start=at(11, 8), end=at(11, 18))
        crew.request_deployment(line, user=None)
        crew.answer_deployment(line, accept=True, user=None)
        Notification.objects.all().delete()
        apply_move(
            MoveRequest(project=project, what=PERIOD, start=at(17, 8), end=at(19, 20)),
            rights=ALL_RIGHTS,
            user=make_user("paula"),
        )
        got = list(Notification.objects.filter(user=anna.user).values_list("kind", flat=True))
        self.assertEqual(got, [Kind.DEPLOYMENT_REQUEST])

    def test_a_line_renting_a_sale_product_from_before_is_taken_over(self) -> None:
        """PRD-047, PRJ-060: the update removed the rental price of a sale product that a line had rented."""
        from rentalars.products.models import Product, ProductKind
        from rentalars.projects import services
        from rentalars.projects.models import MaterialLine
        from tests.helpers import ALL_RIGHTS, add_line, at, make_project, make_stock

        whole = make_project("Stadtfest", start=at(9, 12), end=at(14, 18))
        market = services.create_subproject(whole, name="Markt", start=at(10, 8), end=at(12, 8))
        park = services.create_subproject(whole, name="Park", start=at(12, 12), end=at(14, 12))
        product = make_stock("V-100", 6, "Gaffa")
        source = add_line(market, product, 6).line
        # As the update leaves it: a sale product without rental price, the old line still renting it.
        Product.objects.filter(pk=product.pk).update(kind=ProductKind.SALE, price=None, sale_price="9.00")
        source = MaterialLine.objects.get(pk=source.pk)
        taken = services.take_over_line(source, park, rights=ALL_RIGHTS).line
        self.assertEqual((taken.taken_over_from_id, taken.quantity, taken.is_sale), (source.pk, 6, False))

    def test_going_back_from_0030_firm_becomes_accepted(self) -> None:
        """PER-041: the older state does not know "firm"; the step back makes it "accepted"."""
        import importlib

        from django.apps import apps

        from rentalars.projects import crew
        from rentalars.projects.models import CrewLine, RequestStatus
        from tests.helpers import ALL_RIGHTS, at, make_person, make_project, plan

        step = importlib.import_module("rentalars.projects.migrations.0030_crew_firm_091")
        project = make_project("Stadtfest", start=at(10, 8), end=at(12, 20))
        line = plan(project, "Tontechnik", make_person("Anna Becker", rates={"Tontechnik": "35.00"}))
        crew.update_crew_line(line, rights=ALL_RIGHTS, firm=True)
        step.firm_to_accepted(apps, None)
        line = CrewLine.objects.get(pk=line.pk)
        self.assertEqual(line.request_status, RequestStatus.ACCEPTED)
        self.assertEqual((line.requested_start, line.requested_end), (line.start, line.end))
