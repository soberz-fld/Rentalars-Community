# SPDX-License-Identifier: GPL-3.0-or-later
"""Logic errors L1 – L16 of the review."""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone

from rentalars.personnel.models import Person, Qualification, QualificationType
from rentalars.products.models import ProductKind
from rentalars.projects.planning import build_planning
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    BERLIN,
    RentalarsTestCase,
    add_line,
    at,
    category,
    make_customer,
    make_item,
    make_items,
    make_model,
    make_person,
    make_product,
    make_project,
    plan,
    record_time,
)
from tests.unit.test_090_logistics import LogisticsCase
from tests.unit.test_117_security import CrewMailTestCase

# --- L1 ------------------------------------------------------------------------------------------------------


class AnonymisingACustomerKeepsOtherMailsTests(RentalarsTestCase):
    """L1: "anna@musik.example" is not found inside "hanna@musik.example"."""

    def test_only_whole_addresses_count(self) -> None:
        from rentalars.customers.models import Contact
        from rentalars.customers.services import anonymise_customer
        from rentalars.mail.log import record
        from rentalars.mail.models import Direction, LogKind, LogResult, MailLogEntry, ProjectMail

        customer = make_customer("Musik GmbH")
        Contact.objects.create(customer=customer, name="Anna Berg", email="anna@musik.example")
        other = make_project("Fremdes Fest", customer=make_customer("Andere GmbH"))

        def mail(key: str, **fields: str) -> ProjectMail:
            return ProjectMail.objects.create(
                project=other,
                direction=Direction.INCOMING,
                message_key=key,
                message_id=f"<{key}@x.example>",
                subject=key,
                date=at(1, 7),
                text_body="x",
                **fields,
            )

        stranger = mail("hanna", sender_address="hanna@musik.example", to_addresses="buero@verleih.example")
        by_to = mail("to-hanna", sender_address="buero@verleih.example", to_addresses="Hanna <hanna@musik.example>")
        about = mail("cc-hanna", sender_address="x@y.example", cc_addresses="xanna@musik.example, other@z.example")
        own = mail("anna", sender_address="Anna <ANNA@musik.example>")
        to_anna = mail(
            "to-anna", sender_address="buero@verleih.example", to_addresses="Berg, Anna <anna@musik.example>"
        )
        for sender, recipients in (("hanna@musik.example", "x@y.example"), ("x@y.example", "anna@musik.example")):
            record(
                direction=Direction.INCOMING,
                kind=LogKind.PROJECT,
                result=LogResult.ASSIGNED,
                sender=sender,
                recipients=recipients,
                subject="Log",
            )

        anonymise_customer(customer)

        for kept in (stranger, by_to, about):
            self.assertTrue(ProjectMail.objects.filter(pk=kept.pk).exists(), kept.subject)
        for gone in (own, to_anna):
            self.assertFalse(ProjectMail.objects.filter(pk=gone.pk).exists(), gone.subject)
        self.assertEqual(MailLogEntry.objects.filter(sender="hanna@musik.example").count(), 1)
        self.assertEqual(MailLogEntry.objects.filter(recipients="anna@musik.example").count(), 0)


# --- L2 ------------------------------------------------------------------------------------------------------


class HoursAcrossTheChangeOfTheClockTests(RentalarsTestCase):
    """L2: hours are the time that passes, and they stay the same when the entry is approved."""

    def shift(self, start: datetime.datetime, end: datetime.datetime) -> Decimal:
        person = make_person("Berta Licht", rates={"Tontechnik": "30.00"})
        project = make_project("Nachtschicht", start=start, end=end)
        entry = record_time(person, project, "Tontechnik", start, end, approve=True)
        entry.refresh_from_db()
        return entry.hours

    def test_the_night_the_clock_goes_back_is_nine_hours(self) -> None:
        start = datetime.datetime(2027, 10, 30, 22, 0, tzinfo=BERLIN)
        self.assertEqual(self.shift(start, start.replace(day=31, hour=6)), Decimal("9.00"))

    def test_the_night_the_clock_goes_forward_is_seven_hours(self) -> None:
        start = datetime.datetime(2027, 3, 27, 22, 0, tzinfo=BERLIN)
        self.assertEqual(self.shift(start, start.replace(day=28, hour=6)), Decimal("7.00"))

    def test_the_hours_of_the_function_in_a_divided_period_add_up(self) -> None:
        from rentalars.timetracking.models import hours_between

        start = datetime.datetime(2027, 10, 30, 22, 0, tzinfo=BERLIN)
        end = datetime.datetime(2027, 10, 31, 6, 0, tzinfo=BERLIN)
        self.assertEqual(hours_between(start, end), Decimal("9.00"))
        self.assertEqual(hours_between(start, end, 60), Decimal("8.00"))


# --- L3, L4, L8 (API) ----------------------------------------------------------------------------------------


class AccountRulesInTheApiTests(ApiTestCase):
    """L3: deactivating a person through ``/people`` obeys the rules of the page; L8: anonymised stay anonymised."""

    def test_nobody_deactivates_the_own_account(self) -> None:
        mine = Person.objects.get(user=self.admin_user)
        response = self.admin.patch(f"{API}/people/{mine.pk}", {"is_active": False}, format="json")
        self.assert_error(response, 400, "validation_error")
        mine.refresh_from_db()
        self.assertTrue(mine.is_active)

    def test_the_last_administrator_stays(self) -> None:
        mine = Person.objects.get(user=self.admin_user)
        dora = self.client_for("dora", "Personaldisposition")
        response = dora.patch(f"{API}/people/{mine.pk}", {"is_active": False}, format="json")
        self.assert_error(response, 400, "validation_error")
        self.admin_user.refresh_from_db()
        self.assertTrue(self.admin_user.is_active)

    def test_another_person_can_be_deactivated_and_back(self) -> None:
        anna = make_person("Anna Becker")
        self.assertEqual(
            self.admin.patch(f"{API}/people/{anna.pk}", {"is_active": False}, format="json").status_code, 200
        )
        anna.refresh_from_db()
        anna.user.refresh_from_db()
        self.assertFalse(anna.is_active)
        self.assertFalse(anna.user.is_active)
        self.assertEqual(
            self.admin.patch(f"{API}/people/{anna.pk}", {"is_active": True}, format="json").status_code, 200
        )

    def test_an_anonymised_person_is_not_filled_again(self) -> None:
        anna = make_person("Anna Becker")
        self.assertEqual(self.admin.post(f"{API}/people/{anna.pk}/anonymise").status_code, 200)
        response = self.admin.patch(
            f"{API}/people/{anna.pk}",
            {"first_name": "Anna", "email": "anna@privat.example", "is_active": True},
            format="json",
        )
        self.assert_error(response, 409, "anonymised")
        anna.refresh_from_db()
        self.assertEqual(anna.email, "")

    def test_an_anonymised_customer_is_not_filled_again(self) -> None:
        customer = make_customer("Musik GmbH")
        self.assertEqual(self.admin.post(f"{API}/customers/{customer.pk}/anonymise").status_code, 200)
        response = self.admin.patch(
            f"{API}/customers/{customer.pk}", {"name": "Musik GmbH", "email": "info@musik.example"}, format="json"
        )
        self.assert_error(response, 409, "anonymised")
        customer.refresh_from_db()
        self.assertEqual(customer.email, "")


class DeletingAnItemTests(ApiTestCase):
    """L4: the API refuses what the page refuses."""

    def test_an_item_with_built_in_bulk_material_is_kept(self) -> None:
        from rentalars.material import installations
        from rentalars.material.models import MaterialItem

        product = make_product("K-600", "Kabel")
        row = make_item(make_model("Kabel", product, bulk=True), 600, quantity=10)
        case = make_item(make_model("Case", category_code="T"), 900)
        installations.install_quantity(case, row, 2)
        response = self.admin.delete(f"{API}/material-items/{case.pk}")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertTrue(MaterialItem.objects.filter(pk=case.pk).exists())

    def test_a_plain_item_is_deleted(self) -> None:
        from rentalars.material.models import MaterialItem

        item = make_item(make_model("Case", category_code="T"), 901)
        self.assertEqual(self.admin.delete(f"{API}/material-items/{item.pk}").status_code, 204)
        self.assertFalse(MaterialItem.objects.filter(pk=item.pk).exists())


# --- L5, L6, L7 ----------------------------------------------------------------------------------------------


class SoldBulkMaterialIsNotOutTests(RentalarsTestCase):
    """L5: pieces sold never come back, so they are not "out with projects"."""

    def test_a_sale_leaves_the_rest_free(self) -> None:
        from rentalars.material import installations
        from rentalars.material.models import MaterialItem
        from rentalars.packing import services as packing

        product = make_product("K-610", "Gaffa", kind=ProductKind.SALE, price=None, sale_price=Decimal("5.00"))
        row = make_item(make_model("Gaffa", product, bulk=True), 700, quantity=100)
        project = make_project("Verkauf")
        add_line(project, product, 10, is_sale=True)
        packlist = packing.get_packlist(project)
        packing.pack_all(packlist)
        packing.issue(packlist)
        row = MaterialItem.objects.get(pk=row.pk)
        self.assertEqual(row.quantity, 90)
        self.assertEqual(installations.pieces_out_with_projects(row), 0)
        self.assertEqual(installations.free_quantity(row), 90)


class ForgettingABuyerFindsTheOldTextTests(RentalarsTestCase):
    """B9 (review): the date in the reason of the status "sold" – older versions wrote it as dd.mm.yyyy in every language."""

    def test_an_english_reason_with_the_german_date_is_found(self) -> None:
        from rentalars.customers.models import Customer
        from rentalars.material import sales
        from rentalars.material.models import MaterialItem

        customer = Customer.objects.create(name="Max")
        item = make_item(make_model("Pult 40", category_code="T"), 40, purchase_price=Decimal("100"))
        sales.sell(item, sold_on=datetime.date(2027, 3, 1), net_price=Decimal("50"), customer=customer, buyer_name="")
        item = MaterialItem.objects.get(pk=item.pk)
        item.status_reason = "Sold on 01.03.2027 to Max"  # as written in an older English installation
        item.save()
        customer.name = "Anonym 7"
        sales.forget_customer(customer)
        item.refresh_from_db()
        self.assertNotIn("Max", item.status_reason)
        self.assertEqual(item.status_reason, "Sold on 01.03.2027")


class AnOldFailedInspectionTests(RentalarsTestCase):
    """L6: a failed inspection entered afterwards from the paper files does not make the device defective."""

    def test_only_the_latest_inspection_decides(self) -> None:
        from rentalars.material import services
        from rentalars.material.models import InspectionType, ItemStatus

        item = make_items(make_model("Scheinwerfer", make_product("L-010"), category_code="L"))[0]
        electric = InspectionType.objects.create(name="Elektrische Prüfung", interval_months=12)
        electric.categories.add(category("L"))
        services.record_inspection(
            item, electric, date=datetime.date(2027, 2, 20), inspector="E. Fachkraft", result="passed"
        )
        services.record_inspection(
            item, electric, date=datetime.date(2026, 2, 15), inspector="E. Fachkraft", result="failed"
        )
        item.refresh_from_db()
        self.assertEqual(item.status, ItemStatus.AVAILABLE)
        services.record_inspection(
            item, electric, date=datetime.date(2027, 2, 25), inspector="E. Fachkraft", result="failed"
        )
        item.refresh_from_db()
        self.assertEqual(item.status, ItemStatus.DEFECTIVE)


class DrivingLicenceForTheBookingTests(LogisticsCase):
    """L7: the licence must hold until the booking ends, not only today."""

    def setUp(self) -> None:
        super().setUp()
        self.licence = QualificationType(name="Führerschein B", licence_classes="B")
        self.licence.full_clean()
        self.licence.save()
        self.driver = make_person("Erik")
        plan(self.project, "Fahrer", self.driver, vehicle_line=self.car, is_driver=True)

    def warnings(self, line) -> list[str]:
        planning = build_planning(self.project)
        return next(item.warnings for item in planning.logistics if item.line.pk == line.pk)

    def test_a_licence_that_runs_out_before_the_booking_ends_is_named(self) -> None:
        Qualification.objects.create(
            person=self.driver, qualification_type=self.licence, valid_until=datetime.date(2027, 3, 5)
        )
        texts = self.warnings(self.car)
        self.assertTrue(any("05.03.2027" in text for text in texts), texts)

    def test_a_booking_that_ends_at_midnight_belongs_to_the_day_before(self) -> None:
        """Ending on the 6th at 00:00 is still the 5th: a licence valid until the 5th holds."""
        from rentalars.projects.models import VehicleLine

        VehicleLine.objects.filter(pk=self.car.pk).update(end=at(6, 0))
        self.car.refresh_from_db()
        Qualification.objects.create(
            person=self.driver, qualification_type=self.licence, valid_until=datetime.date(2027, 3, 5)
        )
        self.assertEqual(
            [text for text in self.warnings(self.car) if "driving licence" in text.lower() or "Führerschein" in text],
            [],
        )

    def test_a_licence_that_holds_is_no_warning(self) -> None:
        Qualification.objects.create(
            person=self.driver, qualification_type=self.licence, valid_until=datetime.date(2027, 3, 20)
        )
        self.assertEqual(
            [text for text in self.warnings(self.car) if "driving licence" in text.lower() or "Führerschein" in text],
            [],
        )

    def test_a_licence_without_end_is_no_warning(self) -> None:
        Qualification.objects.create(person=self.driver, qualification_type=self.licence)
        self.assertEqual(
            [text for text in self.warnings(self.car) if "driving licence" in text.lower() or "Führerschein" in text],
            [],
        )


# --- L9 ------------------------------------------------------------------------------------------------------


class NameOfTheMailServerTests(CrewMailTestCase):
    """L9: one word is stored, a typo that can never match is refused, and the self-check notices a name that never fits."""

    def test_only_a_plain_name_is_accepted(self) -> None:
        from rentalars.mail.models import MailSettings

        settings = MailSettings.load()
        for bad in ("mx.example.com; spf=pass", "mx example", 'mx"x', "(mx.example.com)", "me@mx.example.com"):
            settings.crew_answer_trusted_server = bad
            with self.subTest(bad=bad), self.assertRaises(ValidationError) as caught:
                settings.full_clean()
            self.assertIn("crew_answer_trusted_server", caught.exception.message_dict)
        settings.crew_answer_trusted_server = "  mx.example.com "
        settings.full_clean()
        self.assertEqual(settings.crew_answer_trusted_server, "mx.example.com")

    def test_a_name_stored_by_0_11_7_does_not_block_other_settings(self) -> None:
        """A value with a semicolon was allowed before. Saving something else – page or API – must still work."""
        from rentalars.mail import services
        from rentalars.mail.models import MailSettings

        MailSettings.objects.filter(pk=MailSettings.load().pk).update(
            crew_answer_trusted_server="mx.example.com; spf=pass"
        )
        settings = MailSettings.load()
        settings.interval_minutes = 10
        services.save_settings(settings)  # no ValidationError
        self.assertEqual(MailSettings.load().interval_minutes, 10)
        self.assertEqual(MailSettings.load().crew_answer_trusted_server, "mx.example.com; spf=pass")
        # Changing the value is checked as before.
        settings.crew_answer_trusted_server = "mx.example.com; spf=fail"
        with self.assertRaises(ValidationError):
            services.save_settings(settings)

    def test_the_selfcheck_notices_a_name_that_never_confirms(self) -> None:
        from rentalars.core import selfcheck
        from rentalars.mail.models import Direction, LogKind, LogResult, MailLogEntry, MailSettings

        settings = MailSettings.load()
        settings.crew_answer_trusted_server = "mx.typo.example"
        settings.save()

        def warnings() -> list[str]:
            report = selfcheck.Report()
            selfcheck._mail(report)
            return [item.detail for item in report.findings if "mx.typo.example" in item.detail]

        self.assertEqual(warnings(), [])
        for number in range(3):
            MailLogEntry.objects.create(
                direction=Direction.INCOMING,
                kind=LogKind.PROJECT,
                result=LogResult.CREW_ANSWER,
                subject=f"Re: [RA-E-{number}-JA]",
                detail="accepted:unconfirmed",
                timestamp=timezone.now(),
            )
        self.assertEqual(len(warnings()), 1)
        MailLogEntry.objects.create(
            direction=Direction.INCOMING,
            kind=LogKind.PROJECT,
            result=LogResult.CREW_ANSWER,
            subject="Re: [RA-E-9-JA]",
            detail="accepted",
            timestamp=timezone.now(),
        )
        self.assertEqual(warnings(), [])


# --- L10 -----------------------------------------------------------------------------------------------------


class StatusGroupsAreDefinedOnceTests(RentalarsTestCase):
    """L10: the groups of statuses come from ``projects.models`` – no module keeps a list of its own."""

    def test_the_modules_use_the_one_definition(self) -> None:
        from rentalars.packing import offline
        from rentalars.projects import my_deployments, price_updates, profitability
        from rentalars.projects.models import (
            EARNING_STATUSES,
            FIRM_STATUSES,
            ORDER_STATUSES,
            UNSETTLED_STATUSES,
            ProjectStatus,
        )

        self.assertIs(my_deployments.FIRM_STATUSES, ORDER_STATUSES)
        self.assertIs(profitability.ORDER_STATUSES, ORDER_STATUSES)
        self.assertIs(profitability.EARNING_STATUSES, EARNING_STATUSES)
        self.assertIs(offline.OFFLINE_STATUSES, FIRM_STATUSES)
        self.assertIs(price_updates.CHANGE_NOTICE_STATUSES, UNSETTLED_STATUSES)
        self.assertEqual(ORDER_STATUSES, FIRM_STATUSES | {"returned", "closed"})
        self.assertFalse(UNSETTLED_STATUSES & (ORDER_STATUSES - {ProjectStatus.CONFIRMED_OPEN.value}))


# --- L11 -----------------------------------------------------------------------------------------------------


class AnswerNoteOfAnAnonymisedPersonTests(RentalarsTestCase):
    """L11: the free text of an answer to a request goes with the person – also from the change log."""

    def test_answer_note_is_erased(self) -> None:
        from django.contrib.contenttypes.models import ContentType

        from rentalars.core.models import AuditLogEntry
        from rentalars.personnel.privacy import anonymise_person
        from rentalars.projects.models import CrewLine

        person = make_person("Gisela Frei")
        line = plan(make_project("Fest"), "Ton", person)
        CrewLine.objects.filter(pk=line.pk).update(answer_note="Bin bei meiner Mutter Gisela Frei im Krankenhaus")
        entry = AuditLogEntry.objects.create(
            content_type=ContentType.objects.get_for_model(CrewLine),
            object_id=str(line.pk),
            event="update",
            object_repr="Ton: Gisela Frei",
            changes={"answer_note": ["", "Bin bei meiner Mutter Gisela Frei im Krankenhaus"]},
        )
        anonymise_person(person)
        line.refresh_from_db()
        entry.refresh_from_db()
        self.assertEqual(line.answer_note, "")
        self.assertNotIn("answer_note", entry.changes)


# --- L12 -----------------------------------------------------------------------------------------------------


class MovingAProjectWithPartsAcrossTheClockChangeTests(RentalarsTestCase):
    """L12: the parts move along when the whole project is moved over the night of 28 March 2027."""

    def test_the_part_keeps_its_place_on_the_clock(self) -> None:
        from rentalars.projects import services

        whole = make_project("Festival", start=at(26, 8), end=at(30, 18))
        part = services.create_subproject(whole, name="Bühne", start=at(27, 8), end=at(27, 20))
        services.update_project(whole, start=at(27, 8), end=at(31, 18))
        part.refresh_from_db()
        self.assertEqual(
            (part.start.astimezone(BERLIN), part.end.astimezone(BERLIN)),
            (at(28, 8), at(28, 20)),
        )

    def test_two_days_later_is_not_refused(self) -> None:
        from rentalars.projects import services

        whole = make_project("Festival", start=at(26, 8), end=at(30, 18))
        part = services.create_subproject(whole, name="Bühne", start=at(27, 8), end=at(30, 8))
        services.update_project(whole, start=at(28, 8), end=at(1, 18, month=4))
        part.refresh_from_db()
        self.assertEqual(part.start.astimezone(BERLIN), at(29, 8))


# --- L13 – L16 -----------------------------------------------------------------------------------------------


class OverlappingBlocksCountOnceTests(RentalarsTestCase):
    """L13: an item blocked twice at the same time is still one piece."""

    def test_two_overlapping_blocks_of_one_item(self) -> None:
        from rentalars.availability.engine import AvailabilityEngine
        from rentalars.material.models import ItemBlock

        product = make_product("L-020", "Lampe")
        items = make_items(make_model("Lampe", product), 3)
        ItemBlock.objects.create(item=items[0], start=at(10), end=at(13), reason="Linse")
        ItemBlock.objects.create(item=items[0], start=at(11), end=at(15), reason="Kabel")
        answer = AvailabilityEngine().availability([product.pk], at(10), at(15))[product.pk]
        self.assertEqual(answer.free, 2)

    def test_two_items_blocked_at_once_are_two_pieces(self) -> None:
        from rentalars.availability.engine import AvailabilityEngine
        from rentalars.material.models import ItemBlock

        product = make_product("L-021", "Lampe")
        items = make_items(make_model("Lampe", product), 3)
        ItemBlock.objects.create(item=items[0], start=at(10), end=at(13), reason="Linse")
        ItemBlock.objects.create(item=items[1], start=at(11), end=at(15), reason="Kabel")
        answer = AvailabilityEngine().availability([product.pk], at(11), at(13))[product.pk]
        self.assertEqual(answer.free, 1)


class ADeclinedPlaceIsNotPlannedTests(RentalarsTestCase):
    """L14: a person who said no to a request is free for the time."""

    def test_declined_lines_do_not_make_a_person_planned(self) -> None:
        from rentalars.personnel.availability import people_availability
        from rentalars.projects import crew
        from tests.helpers import make_user

        person = make_person("Anna Becker", rates={"Tontechnik": "30.00"})
        project = make_project("Fest")
        line = plan(project, "Tontechnik", person)
        crew.request_deployment(line, user=make_user("kai"))
        status = {row.person.pk: row.status for row in people_availability(at(10), at(12))}
        self.assertEqual(status[person.pk], "planned")
        crew.answer_deployment(line, accept=False, user=None)
        status = {row.person.pk: row.status for row in people_availability(at(10), at(12))}
        self.assertEqual(status[person.pk], "free")


class TemplateListInLocalTimeTests(RentalarsTestCase):
    """L15: a template made at half past midnight shows that day, not the day before."""

    def test_the_date_is_the_local_one(self) -> None:
        from rentalars.projects.template_tables import _created

        class Template:
            created_at = datetime.datetime(2027, 3, 2, 23, 30, tzinfo=datetime.UTC)  # 00:30 in Berlin on 3 March
            created_by_id = None

        self.assertIn("03.03.2027", _created(Template()))


class ContainerContentsAreLockedTogetherTests(RentalarsTestCase):
    """L16: booking a rack locks the products of its loose contents as well."""

    def test_the_lock_covers_the_contents(self) -> None:
        from unittest import mock

        from rentalars.material import services as material_services
        from rentalars.material.models import ConnectionType
        from rentalars.projects import services

        rack_product = make_product("S-610", "Rack")
        cable_product = make_product("K-620", "Kabel")
        rack = make_items(make_model("Rack", rack_product))[0]
        cable = make_items(make_model("Kabel", cable_product))[0]
        material_services.install_item(cable, rack, connection_type=ConnectionType.LOOSE)
        project = make_project("Fest")
        with mock.patch.object(services, "_lock_products", wraps=services._lock_products) as lock:
            add_line(project, rack_product, 1)
        locked = set(lock.call_args.args[0])
        self.assertTrue({rack_product.pk, cable_product.pk} <= locked, locked)
