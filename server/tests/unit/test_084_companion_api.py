# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "companion-api": the change times of the own contact data and the pay of time entries.

* API-015: ``Person.save`` notes when each of phone, e-mail and the two releases changed – on every way, also
  through the account –; the update starts them from the change log.
* API-016: ``attach_pay_kinds`` names hourly, daily and flat pay and "in the day rate" for any choice of entries,
  with the rule of "My times" (ZEI-026).
"""

from __future__ import annotations

from decimal import Decimal as D  # noqa: N817

from django.db import connection
from django.test.utils import CaptureQueriesContext

from rentalars.personnel.models import Person
from rentalars.projects.models import CrewBilling
from rentalars.timetracking import display
from rentalars.timetracking.models import TimeEntry
from tests.helpers import (
    LATER,
    NOW,
    RentalarsTestCase,
    at,
    job_function,
    make_person,
    make_project,
    make_user,
    plan,
    record_time,
    set_clock,
)

MOMENTS = ("phone_changed_at", "email_changed_at", "share_phone_changed_at", "share_email_changed_at")


def moments(person: Person) -> tuple:
    person = Person.objects.get(pk=person.pk)
    return tuple(getattr(person, name) for name in MOMENTS)


class ContactChangeTimeTests(RentalarsTestCase):
    """API-015: the moment of the last change of each contact field."""

    def test_a_new_person_starts_with_its_creation(self) -> None:
        person = make_person("Anna Becker", phone="0170 1")
        self.assertEqual(moments(person), (NOW,) * 4)

    def test_only_a_changed_field_notes_its_moment(self) -> None:
        person = make_person("Anna Becker", phone="0170 1")
        set_clock(at(2, 9))
        person = Person.objects.get(pk=person.pk)
        person.phone = "0170 2"
        person.note = "Kran-Schein"
        person.save()
        self.assertEqual(moments(person), (at(2, 9), NOW, NOW, NOW))
        set_clock(at(3, 9))
        person.save()  # nothing changed: every moment stays
        person.share_email = True
        person.save(update_fields=["share_email"])
        self.assertEqual(moments(person), (at(2, 9), NOW, NOW, at(3, 9)))

    def test_update_fields_decide_what_counts(self) -> None:
        """A field changed in memory but not saved does not note a moment."""
        person = Person.objects.get(pk=make_person("Anna Becker").pk)
        set_clock(at(2, 9))
        person.phone = "0170 9"
        person.save(update_fields=["note"])
        self.assertEqual(moments(person), (NOW,) * 4)
        self.assertEqual(Person.objects.get(pk=person.pk).phone, "")

    def test_the_account_changes_the_e_mail_address(self) -> None:
        """AUT-026: a new address in the user administration is a change of the person's address."""
        user = make_user("anna")
        set_clock(at(2, 9))
        user.email = "anna.becker@example.de"
        user.save()
        person = Person.objects.get(user=user)
        self.assertEqual(person.email, "anna.becker@example.de")
        self.assertEqual(moments(person)[1], at(2, 9))
        self.assertEqual(moments(person)[0], NOW)

    def test_a_given_moment_is_stored(self) -> None:
        """The offline change of the companion app keeps the moment it was made."""
        person = Person.objects.get(pk=make_person("Anna Becker").pk)
        set_clock(at(2, 9))
        person.phone, person.share_phone = "0170 5", True
        person.contact_change_times = {"phone": at(2, 7)}
        person.save()
        self.assertEqual(moments(person)[:3], (at(2, 7), NOW, at(2, 9)))
        self.assertEqual(person.contact_change_times, {})

    def test_an_instance_without_snapshot_asks_the_database(self) -> None:
        person = make_person("Anna Becker", phone="0170 1")
        loaded = Person.objects.only("pk", "user", "phone", "first_name", "last_name", "email", "is_active").get(
            pk=person.pk
        )
        loaded._audit_loaded = None  # as if built without loading
        set_clock(at(2, 9))
        loaded.phone = "0170 1"
        loaded.save(update_fields=["phone"])
        self.assertEqual(moments(person)[0], NOW)
        loaded.phone = "0170 2"
        loaded.save(update_fields=["phone"])
        self.assertEqual(moments(person)[0], at(2, 9))


class PayKindTests(RentalarsTestCase):
    """API-016: hourly, daily and flat pay; "in the day rate" also where the list does not hold the whole day."""

    def setUp(self) -> None:
        super().setUp()
        set_clock(LATER)
        self.project = make_project("Stadtfest", start=at(10), end=at(12))
        self.light, self.sound, self.rig = (job_function(name) for name in ("Licht", "Tontechnik", "Rigging"))
        self.anna = make_person("Anna Becker", rates={"Licht": "30.00", "Tontechnik": "35.00", "Rigging": "40.00"})
        self.daily = plan(
            self.project,
            self.sound,
            self.anna,
            start=at(11, 8),
            end=at(11, 22),
            billing=CrewBilling.DAY,
            daily_rate=D("280.00"),
        )
        plan(self.project, self.rig, self.anna, start=at(12, 8), end=at(12, 18), cost_flat_rate=D("500.00"))
        self.hourly = record_time(self.anna, self.project, self.light, at(10, 8), at(10, 12))
        self.morning = record_time(self.anna, self.project, self.sound, at(11, 8), at(11, 12))
        self.evening = record_time(self.anna, self.project, self.sound, at(11, 18), at(11, 22))
        self.flat = record_time(self.anna, self.project, self.rig, at(12, 8), at(12, 18))

    def test_the_same_as_my_times_for_a_whole_week(self) -> None:
        """ZEI-026: hourly, daily and flat (ZEI-028) as "My times" shows them.

        Changed on purpose: until then "My times" showed the flat-rate deployment by the hour; now it
        names it as the API does, with the flat rate once per deployment (tests/unit/test_090_small.py).
        """
        week = list(TimeEntry.objects.select_related("crew_line").order_by("start", "id"))
        display.attach_pay(week)
        shown = [(entry.pay_kind, entry.pay_in_day_rate) for entry in week]
        fresh = list(TimeEntry.objects.order_by("start", "id"))
        display.attach_pay_kinds(fresh)
        named = [(entry.pay_kind, entry.pay_in_day_rate) for entry in fresh]
        self.assertEqual(shown, [("hourly", False), ("daily", False), ("daily", True), ("flat", False)])
        self.assertEqual(named, shown)

    def test_a_list_without_the_first_entry_of_the_day(self) -> None:
        evening = TimeEntry.objects.get(pk=self.evening.pk)
        display.attach_pay_kinds([evening])
        self.assertEqual((evening.pay_kind, evening.pay_in_day_rate), ("daily", True))
        morning = TimeEntry.objects.get(pk=self.morning.pk)
        display.attach_pay_kinds([morning])
        self.assertEqual((morning.pay_kind, morning.pay_in_day_rate), ("daily", False))

    def test_a_running_stopwatch_and_another_person(self) -> None:
        """Only finished entries of the same person are paid; the running one is in the day rate of the morning."""
        TimeEntry.objects.filter(pk__in=[self.evening.pk, self.flat.pk]).delete()  # a stopwatch runs to "now"
        set_clock(at(11, 14))
        running = record_time(self.anna, self.project, self.sound, at(11, 13), None, crew_line=self.daily)
        display.attach_pay_kinds([running])
        self.assertEqual((running.pay_kind, running.pay_in_day_rate), ("daily", True))
        bert = make_person("Bert Brandt", rates={"Tontechnik": "35.00"})
        set_clock(LATER)
        other = record_time(bert, self.project, self.sound, at(11, 6), at(11, 7))
        display.attach_pay_kinds([other])
        self.assertEqual(other.pay_kind, "hourly")  # not his crew line

    def test_one_query_for_the_days(self) -> None:
        entries = list(TimeEntry.objects.select_related("crew_line").order_by("start"))
        with CaptureQueriesContext(connection) as queries:
            display.attach_pay_kinds(entries)
        self.assertEqual(len(queries.captured_queries), 1)
