# SPDX-License-Identifier: GPL-3.0-or-later
"""Price offers of freelancers for a deployment request (PER-038).

The requirement: own price offers of freelancers are integrated (optional).

* The feature is off until the company switches it on; then nothing about the request changes for anybody.
* A freelancer asked for a deployment may answer with a price (per hour, per day or in total) within the limits
  of the settings; the company accepts, rejects or counters, for at most N rounds.
* An accepted offer sets the cost rate of exactly that crew line, with a marker and a trace in the history; the
  price for the customer does not change. It stops applying when the rate is changed by hand, the line gets
  another person, or - for a total - new times are asked for.
* Offers are personnel costs: a freelancer sees their own only, the company only with the right (AUT-019).
* Browser pages and the API do the same through ``personnel.offers`` (API-002).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.core.models import AuditLogEntry, SystemSettings
from rentalars.notifications.models import Kind, Notification, Preference
from rentalars.personnel import offers
from rentalars.personnel.models import EmploymentKind
from rentalars.personnel.offer_models import OfferSettings, OfferSide, OfferStatus, OfferUnit, PriceOffer, ReleaseReason
from rentalars.projects import crew
from rentalars.projects.access import access_level
from rentalars.projects.models import CrewBilling, RequestStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    RentalarsTestCase,
    at,
    job_function,
    make_person,
    make_project,
    make_user,
    plan,
    set_clock,
)
from tests.ui.base import UiTestCase

D = Decimal


def switch_on(**values: object) -> OfferSettings:
    """Switch the feature on (it is off by default), with some settings changed."""
    current = OfferSettings.load()
    current.enabled = True
    for name, value in values.items():
        setattr(current, name, value)
    current.save()
    return current


class OffersTestCase(RentalarsTestCase):
    """A project with a manager, a freelancer with an account planned on a line and asked for the deployment."""

    def setUp(self) -> None:
        super().setUp()
        self.manager = make_user("paula", roles=("Projektleitung",))
        self.manager.first_name, self.manager.last_name = "Paula", "Planer"
        self.manager.save()
        self.account = make_user("frieda", roles=("Freie Kraft",))
        # People see their own rates unless switched off (PER-010); the tests of privacy start from "off".
        system = SystemSettings.load()
        system.people_see_own_rates = False
        system.save()
        self.project = make_project("Stadtfest", manager=self.manager)
        self.person = make_person("Frieda Frei", user=self.account, kind=EmploymentKind.FREELANCER)
        self.function = job_function("Tontechnik", price="60.00", guide="30.00")
        self.line = plan(self.project, self.function, self.person, start=at(10, 10), end=at(10, 18))
        self.line.hourly_rate = D("30.00")
        self.line.save()
        self.company = offers.Acting(user=self.manager, planner=True)
        self.own = offers.Acting(user=self.account, own=True)

    def ask(self) -> None:
        """Ask the person for the deployment."""
        crew.request_deployment(self.line, user=self.manager)
        self.line.refresh_from_db()

    def offer(self, amount: str = "40.00", unit: str = OfferUnit.HOUR, **fields: object) -> PriceOffer:
        """The freelancer makes an offer."""
        return offers.make_offer(self.line, acting=self.own, amount=D(amount), unit=unit, **fields)

    def fresh(self) -> None:
        self.line.refresh_from_db()

    def told(self, user: object, kind: str) -> list[Notification]:
        return list(Notification.objects.filter(user=user, kind=kind))


class SwitchTests(OffersTestCase):
    """The feature is optional and off by default."""

    def test_off_by_default(self) -> None:
        self.assertFalse(OfferSettings.load().enabled)
        self.assertFalse(offers.is_enabled())
        self.ask()
        with self.assertRaises(ValidationError):
            self.offer()
        self.assertEqual(PriceOffer.objects.count(), 0)

    def test_nothing_changes_for_the_request_when_off(self) -> None:
        self.ask()
        crew.answer_deployment(self.line, accept=True, user=self.account)
        self.fresh()
        self.assertEqual(self.line.request_status, RequestStatus.ACCEPTED)
        self.assertEqual(self.line.hourly_rate, D("30.00"))

    def test_the_defaults_when_switched_on(self) -> None:
        current = switch_on()
        self.assertEqual((current.also_temporary, current.min_percent, current.max_percent), (False, None, None))
        self.assertEqual(current.max_rounds, 4)

    def test_who_may_offer(self) -> None:
        switch_on()
        employee = make_person("Emil Fest", kind=EmploymentKind.EMPLOYEE)
        temp = make_person("Tina Aushilfe", kind=EmploymentKind.TEMPORARY)
        self.assertTrue(offers.person_may_offer(self.person))
        self.assertFalse(offers.person_may_offer(employee))
        self.assertFalse(offers.person_may_offer(temp))
        switch_on(also_temporary=True)
        self.assertTrue(offers.person_may_offer(temp))
        self.assertFalse(offers.person_may_offer(employee))
        self.assertFalse(offers.person_may_offer(None))

    def test_an_employee_is_refused(self) -> None:
        switch_on()
        employee = make_person("Emil Fest", kind=EmploymentKind.EMPLOYEE)
        line = plan(self.project, self.function, employee, start=at(11, 10), end=at(11, 18))
        crew.request_deployment(line, user=self.manager)
        with self.assertRaises(ValidationError):
            offers.make_offer(line, acting=self.company, amount=D("40"), unit=OfferUnit.HOUR)

    def test_settings_are_validated(self) -> None:
        current = OfferSettings.load()
        current.min_percent, current.max_percent = D("120"), D("100")
        with self.assertRaises(ValidationError):
            current.full_clean()
        current.min_percent, current.max_percent = None, None
        current.max_rounds = 11
        with self.assertRaises(ValidationError):
            current.full_clean()
        current.max_rounds = 0
        with self.assertRaises(ValidationError):
            current.full_clean()


class MakeOfferTests(OffersTestCase):
    """The freelancer names a price instead of accepting."""

    def setUp(self) -> None:
        super().setUp()
        switch_on()
        self.ask()

    def test_the_offer_is_stored_with_the_rate_of_that_time(self) -> None:
        offer = self.offer("42.50", message="Wegen des Nachtdienstes", valid_until=datetime.date(2027, 3, 5))
        self.assertEqual(
            (offer.round, offer.side, offer.amount, offer.unit, offer.status, offer.currency),
            (1, OfferSide.FREELANCER, D("42.50"), OfferUnit.HOUR, OfferStatus.OPEN, "EUR"),
        )
        self.assertEqual((offer.reference_amount, offer.person, offer.author), (D("30.00"), self.person, self.account))
        self.assertEqual(offer.valid_until, datetime.date(2027, 3, 5))
        self.assertEqual(offers.open_offer(self.line), offer)
        self.fresh()
        self.assertEqual(self.line.request_status, RequestStatus.REQUESTED)

    def test_the_stored_rate_is_not_changed_by_an_offer(self) -> None:
        self.offer()
        self.fresh()
        self.assertEqual(self.line.hourly_rate, D("30.00"))

    def test_a_total_and_a_day(self) -> None:
        total = self.offer("500.00", OfferUnit.TOTAL)
        self.assertEqual(total.reference_amount, D("240.00"))  # 8 hours at 30
        offers.withdraw_offer(total, acting=self.own)
        with self.assertRaises(ValidationError) as raised:
            self.offer("300.00", OfferUnit.DAY)  # a line billed by effort is not offered per day
        self.assertIn("unit", raised.exception.message_dict)

    def test_a_line_billed_per_day_takes_day_or_total(self) -> None:
        self.line.billing = CrewBilling.DAY
        self.line.daily_rate = D("240.00")
        self.line.save()
        self.assertEqual(offers.unit_choices(self.line), [OfferUnit.DAY, OfferUnit.TOTAL])
        with self.assertRaises(ValidationError):
            self.offer("40.00", OfferUnit.HOUR)
        self.assertEqual(self.offer("260.00", OfferUnit.DAY).reference_amount, D("240.00"))

    def test_only_one_offer_waits_at_a_time(self) -> None:
        self.offer()
        with self.assertRaises(ValidationError):
            self.offer("41.00")

    def test_the_request_must_wait_for_an_answer(self) -> None:
        crew.answer_deployment(self.line, accept=False, user=self.account)
        self.fresh()
        with self.assertRaises(ValidationError):
            self.offer()

    def test_a_line_not_asked_yet_takes_no_offer(self) -> None:
        other = plan(self.project, self.function, self.person, start=at(12, 10), end=at(12, 18))
        with self.assertRaises(ValidationError):
            offers.make_offer(other, acting=self.own, amount=D("40"), unit=OfferUnit.HOUR)

    def test_values_are_checked(self) -> None:
        cases = {
            "amount": [D("0"), D("-5"), D("100000000"), D("12.345"), D("NaN"), D("Infinity")],
        }
        for value in cases["amount"]:
            with self.subTest(amount=value), self.assertRaises(ValidationError):
                self.offer(str(value))
        with self.assertRaises(ValidationError) as raised:
            self.offer(currency="USD")
        self.assertIn("currency", raised.exception.message_dict)
        with self.assertRaises(ValidationError) as raised:
            self.offer(message="x" * 501)
        self.assertIn("message", raised.exception.message_dict)
        with self.assertRaises(ValidationError) as raised:
            self.offer(valid_until=datetime.date(2027, 2, 1))
        self.assertIn("valid_until", raised.exception.message_dict)
        with self.assertRaises(ValidationError) as raised:
            self.offer(unit="week")
        self.assertIn("unit", raised.exception.message_dict)
        self.assertEqual(PriceOffer.objects.count(), 0)

    def test_the_longest_values_fit(self) -> None:
        offer = self.offer("99999999.99", OfferUnit.TOTAL, message="x" * 500)
        self.assertEqual(len(offer.message), 500)

    def test_the_limits_of_the_settings(self) -> None:
        switch_on(min_percent=D("90"), max_percent=D("150"))
        for amount in ("26.99", "45.01"):
            with self.subTest(amount=amount), self.assertRaises(ValidationError) as raised:
                self.offer(amount)
            self.assertIn("amount", raised.exception.message_dict)
        self.assertEqual(self.offer("27.00").amount, D("27.00"))
        offers.withdraw_offer(offers.open_offer(self.line), acting=self.own)
        self.assertEqual(self.offer("45.00").amount, D("45.00"))

    def test_one_limit_alone_and_none(self) -> None:
        switch_on(min_percent=None, max_percent=D("110"))
        self.assertEqual(offers.limits_for(self.line, OfferUnit.HOUR), (None, D("33.00")))
        switch_on(min_percent=D("50"), max_percent=None)
        self.assertEqual(offers.limits_for(self.line, OfferUnit.HOUR), (D("15.00"), None))
        switch_on(min_percent=None, max_percent=None)
        self.assertEqual(offers.limits_for(self.line, OfferUnit.HOUR), (None, None))
        self.assertEqual(self.offer("9999.00").amount, D("9999.00"))

    def test_no_stored_rate_no_limit(self) -> None:
        switch_on(max_percent=D("100"))
        self.line.hourly_rate = None
        self.function.guide_cost_rate = None
        self.function.save()
        self.line.save()
        self.line.refresh_from_db()
        self.assertIsNone(offers.reference_amount(self.line, OfferUnit.HOUR))
        offer = self.offer("500.00")
        self.assertIsNone(offer.reference_amount)

    def test_the_message_does_not_give_the_rate_away_to_who_may_not_know_it(self) -> None:
        switch_on(max_percent=D("100"))
        with self.assertRaises(ValidationError) as raised:
            self.offer("31.00")
        self.assertNotIn("30,00", " ".join(raised.exception.message_dict["amount"]))
        # With the right the range is named.
        planner_user = self.manager
        offers.PriceOffer.objects.all().delete()
        with self.assertRaises(ValidationError) as raised:
            offers.make_offer(
                self.line, acting=offers.Acting(user=planner_user, planner=True), amount=D("31"), unit=OfferUnit.HOUR
            )
        self.assertIn("30,00", " ".join(raised.exception.message_dict["amount"]))

    def test_nobody_else_may_make_an_offer(self) -> None:
        stranger = make_user("stefan", roles=("Freie Kraft",))
        with self.assertRaises(PermissionDenied):
            offers.make_offer(self.line, acting=offers.Acting(user=stranger), amount=D("40"), unit=OfferUnit.HOUR)

    def test_a_planner_enters_an_offer_made_by_phone(self) -> None:
        offer = offers.make_offer(self.line, acting=self.company, amount=D("38.00"), unit=OfferUnit.HOUR)
        self.assertEqual((offer.author, offer.side), (self.manager, OfferSide.FREELANCER))

    def test_a_closed_project_takes_no_offer(self) -> None:
        from rentalars.projects.models import ProjectStatus

        self.project.status = ProjectStatus.CLOSED
        self.project.save()
        with self.assertRaises(ValidationError):
            self.offer()

    def test_at_most_so_many_offers_an_hour(self) -> None:
        from rentalars.personnel import offer_models

        switch_on(max_rounds=10)
        for _number in range(offer_models.MAX_ACTIONS_PER_HOUR):
            PriceOffer.objects.create(
                line=self.line,
                person=self.person,
                round=1,
                side=OfferSide.FREELANCER,
                author=self.account,
                amount=D("40"),
                status=OfferStatus.WITHDRAWN,
                requested_at=None,
            )
        with self.assertRaises(ValidationError):
            self.offer()


class NotificationTests(OffersTestCase):
    """The right people are told, in their language, unless they switched it off."""

    def setUp(self) -> None:
        super().setUp()
        switch_on()
        self.ask()

    def test_the_company_is_told_of_an_offer_but_not_the_freelancer(self) -> None:
        self.offer("42.50", message="Nachtdienst")
        (note,) = self.told(self.manager, Kind.PRICE_OFFER)
        self.assertIn("Preisangebot von Frieda Frei", note.title)
        self.assertIn("42,50", note.title)
        self.assertEqual(note.body, "Nachtdienst")
        self.assertEqual(note.url, reverse("projects:detail", args=[self.project.pk]))
        self.assertEqual(self.told(self.account, Kind.PRICE_OFFER), [])

    def test_the_acting_user_is_not_told(self) -> None:
        offers.make_offer(self.line, acting=self.company, amount=D("38"), unit=OfferUnit.HOUR)
        self.assertEqual(self.told(self.manager, Kind.PRICE_OFFER), [])

    def test_the_freelancer_is_told_of_the_answer(self) -> None:
        offer = self.offer()
        offers.reject_offer(offer, acting=self.company, note="Zu teuer")
        (note,) = self.told(self.account, Kind.PRICE_OFFER_ANSWER)
        self.assertIn("abgelehnt", note.title)
        self.assertEqual(note.body, "Zu teuer")
        self.assertEqual(note.url, reverse("projects:deployment", args=[self.project.pk]))

    def test_a_counter_offer_tells_the_freelancer_and_the_answer_the_company(self) -> None:
        offer = self.offer("50.00")
        counter = offers.counter_offer(offer, acting=self.company, amount=D("40.00"), message="Letzter Preis")
        (note,) = self.told(self.account, Kind.PRICE_OFFER_ANSWER)
        self.assertIn("Gegenangebot", note.title)
        self.assertEqual(note.body, "Letzter Preis")
        offers.accept_offer(counter, acting=self.own)
        titles = [n.title for n in self.told(self.manager, Kind.PRICE_OFFER)]
        self.assertTrue(
            any("Frieda Frei hat das Gegenangebot" in title and "angenommen" in title for title in titles), titles
        )

    def test_a_user_who_switched_it_off_gets_nothing(self) -> None:
        Preference.objects.create(user=self.manager, kind=Kind.PRICE_OFFER, in_app=False, by_email=False)
        self.offer()
        self.assertEqual(self.told(self.manager, Kind.PRICE_OFFER), [])

    def test_somebody_without_the_right_to_see_costs_is_not_told(self) -> None:
        """The amount is in the message: a project manager role without the right for personnel costs does not get it."""
        from rentalars.accounts.models import Role

        role = Role.objects.get(name="Projektleitung")
        role.special_rights = [r for r in role.special_rights if r != SpecialRight.PERSONNEL_COSTS]
        role.save()
        self.manager.refresh_from_db()
        self.offer()
        self.assertEqual(self.told(self.manager, Kind.PRICE_OFFER), [])

    def test_the_kinds_are_in_the_settings_of_the_user(self) -> None:
        from rentalars.notifications.services import switchable_kinds

        self.assertTrue({Kind.PRICE_OFFER, Kind.PRICE_OFFER_ANSWER} <= set(switchable_kinds()))


class AcceptTests(OffersTestCase):
    """Accepting an offer: a yes to the deployment, at that price, for exactly this line."""

    def setUp(self) -> None:
        super().setUp()
        switch_on()
        self.ask()

    def cost(self) -> Decimal:
        self.fresh()
        return crew.price_crew_line(self.line).cost

    def test_hourly(self) -> None:
        offer = self.offer("45.00")
        self.assertEqual(self.cost(), D("240.00"))
        before = crew.price_crew_line(self.line).amount
        offers.accept_offer(offer, acting=self.company, note="Einverstanden")
        self.fresh()
        offer.refresh_from_db()
        self.assertEqual(self.line.request_status, RequestStatus.ACCEPTED)
        self.assertEqual(self.line.hourly_rate, D("45.00"))
        self.assertEqual(self.cost(), D("360.00"))
        self.assertEqual(crew.price_crew_line(self.line).amount, before)  # the customer's price does not change
        self.assertEqual(
            (offer.status, offer.applied, offer.previous_hourly_rate), (OfferStatus.ACCEPTED, True, D("30.00"))
        )
        self.assertEqual((offer.decided_by, offer.decision_note), (self.manager, "Einverstanden"))
        self.assertEqual(offers.applied_offer(self.line), offer)

    def test_the_answer_does_not_carry_the_price(self) -> None:
        offers.accept_offer(self.offer("45.00"), acting=self.company)
        self.fresh()
        self.assertNotIn("45", self.line.answer_note)
        self.assertEqual(self.line.answer_note, "Zugesagt nach einem Preisangebot.")

    def test_per_day(self) -> None:
        self.line.billing = CrewBilling.DAY
        self.line.daily_rate = D("240.00")
        self.line.save()
        offer = self.offer("280.00", OfferUnit.DAY)
        offers.accept_offer(offer, acting=self.company)
        self.fresh()
        self.assertEqual((self.line.daily_rate, offer.reference_amount), (D("280.00"), D("240.00")))
        self.assertEqual(self.cost(), D("280.00"))

    def test_in_total(self) -> None:
        offer = self.offer("400.00", OfferUnit.TOTAL)
        offers.accept_offer(offer, acting=self.company)
        self.fresh()
        self.assertEqual(self.line.cost_flat_rate, D("400.00"))
        self.assertEqual(self.cost(), D("400.00"))

    def test_other_lines_of_the_person_keep_their_rate(self) -> None:
        other = plan(self.project, self.function, self.person, start=at(12, 10), end=at(12, 18))
        other.hourly_rate = D("30.00")
        other.save()
        offers.accept_offer(self.offer("45.00"), acting=self.company)
        other.refresh_from_db()
        self.assertEqual(other.hourly_rate, D("30.00"))

    def test_the_hour_limit_rate_follows(self) -> None:
        self.line.hourly_rate_above_limit = D("35.00")
        self.line.save()
        offers.accept_offer(self.offer("45.00"), acting=self.company)
        self.fresh()
        self.assertIsNone(self.line.hourly_rate_above_limit)

    def test_the_trace_in_the_history_of_the_line(self) -> None:
        offers.accept_offer(self.offer("45.00"), acting=self.company)
        event = AuditLogEntry.objects.get(event=offers.EVENT_APPLIED)
        self.assertEqual(event.object_id, str(self.line.pk))

    def test_the_freelancer_is_told_and_the_request_answered_as_always(self) -> None:
        offers.accept_offer(self.offer("45.00"), acting=self.company)
        (note,) = self.told(self.account, Kind.PRICE_OFFER_ANSWER)
        self.assertIn("angenommen", note.title)

    def test_the_freelancer_cannot_accept_their_own_offer(self) -> None:
        offer = self.offer()
        with self.assertRaises(PermissionDenied):
            offers.accept_offer(offer, acting=self.own)

    def test_a_second_answer_is_refused(self) -> None:
        offer = self.offer()
        offers.accept_offer(offer, acting=self.company)
        for action in (offers.accept_offer, offers.reject_offer):
            with self.subTest(action=action.__name__), self.assertRaises(ValidationError):
                action(offer, acting=self.company)

    def test_an_offer_that_ran_out_cannot_be_accepted(self) -> None:
        offer = self.offer(valid_until=datetime.date(2027, 3, 3))
        set_clock(at(4, 9))
        self.assertTrue(PriceOffer.objects.get(pk=offer.pk).has_run_out)
        self.assertIsNone(offers.open_offer(self.line))
        with self.assertRaises(ValidationError):
            offers.accept_offer(offer, acting=self.company)
        # ... and the freelancer can make a new one.
        self.assertEqual(self.offer("41.00").round, 2)

    def test_the_last_day_still_holds(self) -> None:
        offer = self.offer(valid_until=datetime.date(2027, 3, 1))
        offers.accept_offer(offer, acting=self.company)
        self.assertEqual(offer.status, OfferStatus.ACCEPTED)

    def test_a_later_offer_replaces_an_earlier_applied_one(self) -> None:
        offers.accept_offer(self.offer("45.00"), acting=self.company)
        # The person is asked again after new times and offers again.
        crew.update_crew_line(self.line, rights=Rights.everything(), start=at(10, 9))
        self.fresh()
        self.assertEqual(self.line.request_status, RequestStatus.REQUESTED)
        second = self.offer("50.00")
        offers.accept_offer(second, acting=self.company)
        self.fresh()
        second.refresh_from_db()
        first = PriceOffer.objects.get(round=1)
        self.assertEqual(self.line.hourly_rate, D("50.00"))
        self.assertEqual((first.applied, first.release_reason), (False, ReleaseReason.REVOKED))
        self.assertEqual(second.previous_hourly_rate, D("30.00"))  # the stored rate, not the earlier offer


class RejectCounterTests(OffersTestCase):
    """Rejecting, countering, the rounds."""

    def setUp(self) -> None:
        super().setUp()
        switch_on(max_rounds=3)
        self.ask()

    def test_reject_keeps_the_request_open_and_the_freelancer_can_offer_again(self) -> None:
        offer = self.offer("80.00")
        offers.reject_offer(offer, acting=self.company, note="Zu teuer")
        self.fresh()
        offer.refresh_from_db()
        self.assertEqual((offer.status, offer.decision_note), (OfferStatus.REJECTED, "Zu teuer"))
        self.assertEqual(self.line.request_status, RequestStatus.REQUESTED)
        self.assertEqual(self.line.hourly_rate, D("30.00"))
        self.assertEqual(self.offer("40.00").round, 2)

    def test_the_negotiation_log(self) -> None:
        first = self.offer("60.00")
        second = offers.counter_offer(first, acting=self.company, amount=D("35.00"), message="Mehr nicht")
        third = offers.counter_offer(second, acting=self.own, amount=D("38.00"))
        self.assertEqual([o.round for o in offers.negotiation(self.line)], [1, 2, 3])
        self.assertEqual(
            [(o.side, o.status) for o in offers.negotiation(self.line)],
            [
                (OfferSide.FREELANCER, OfferStatus.COUNTERED),
                (OfferSide.COMPANY, OfferStatus.COUNTERED),
                (OfferSide.FREELANCER, OfferStatus.OPEN),
            ],
        )
        self.assertEqual(third.unit, OfferUnit.HOUR)  # the unit of the proposal answered
        self.assertEqual(offers.rounds_used(self.line), 3)

    def test_no_counter_after_the_last_round(self) -> None:
        switch_on(max_rounds=2)
        first = self.offer("60.00")
        second = offers.counter_offer(first, acting=self.company, amount=D("35.00"))
        with self.assertRaises(ValidationError):
            offers.counter_offer(second, acting=self.own, amount=D("38.00"))
        # Only accepting or rejecting is left.
        offers.reject_offer(second, acting=self.own)
        self.assertEqual(second.status, OfferStatus.REJECTED)
        with self.assertRaises(ValidationError):
            self.offer("38.00")

    def test_the_company_counter_is_not_limited_the_freelancers_is(self) -> None:
        switch_on(max_percent=D("150"))
        first = self.offer("40.00")
        second = offers.counter_offer(first, acting=self.company, amount=D("20.00"))  # below, not checked
        self.assertEqual(second.amount, D("20.00"))
        with self.assertRaises(ValidationError):
            offers.counter_offer(second, acting=self.own, amount=D("46.00"))
        self.assertEqual(offers.counter_offer(second, acting=self.own, amount=D("45.00")).amount, D("45.00"))

    def test_the_freelancer_accepts_the_counter(self) -> None:
        first = self.offer("60.00")
        second = offers.counter_offer(first, acting=self.company, amount=D("36.00"))
        offers.accept_offer(second, acting=self.own)
        self.fresh()
        second.refresh_from_db()
        self.assertEqual((self.line.request_status, self.line.hourly_rate), (RequestStatus.ACCEPTED, D("36.00")))
        self.assertTrue(second.applied)

    def test_the_freelancer_cannot_answer_their_own_offer_or_the_company_its_counter(self) -> None:
        first = self.offer("60.00")
        with self.assertRaises(PermissionDenied):
            offers.counter_offer(first, acting=self.own, amount=D("55.00"))
        second = offers.counter_offer(first, acting=self.company, amount=D("36.00"))
        with self.assertRaises(PermissionDenied):
            offers.accept_offer(second, acting=offers.Acting(user=make_user("stefan"), own=False, planner=False))
        # The company cannot accept its own counter-offer, a stranger neither.
        with self.assertRaises(ValidationError):
            offers.accept_offer(first, acting=self.company)  # already answered

    def test_withdraw(self) -> None:
        first = self.offer("60.00")
        offers.withdraw_offer(first, acting=self.own)
        self.assertEqual(first.status, OfferStatus.WITHDRAWN)
        (note,) = [n for n in self.told(self.manager, Kind.PRICE_OFFER) if "zurückgezogen" in n.title]
        self.assertIn("Frieda Frei", note.title)
        with self.assertRaises(ValidationError):
            offers.withdraw_offer(first, acting=self.own)

    def test_the_company_withdraws_its_counter(self) -> None:
        first = self.offer("60.00")
        second = offers.counter_offer(first, acting=self.company, amount=D("36.00"))
        with self.assertRaises(PermissionDenied):
            offers.withdraw_offer(second, acting=self.own)
        offers.withdraw_offer(second, acting=self.company)
        self.assertEqual(second.status, OfferStatus.WITHDRAWN)

    def test_a_new_request_starts_a_new_negotiation(self) -> None:
        first = self.offer("60.00")
        set_clock(at(1, 9))
        self.ask()
        first.refresh_from_db()
        self.assertEqual(first.status, OfferStatus.LAPSED)
        self.assertEqual(offers.negotiation(self.line), [])
        self.assertEqual(self.offer("40.00").round, 1)

    def test_an_answer_without_a_price_ends_the_negotiation(self) -> None:
        first = self.offer("60.00")
        crew.answer_deployment(self.line, accept=True, user=self.account)
        first.refresh_from_db()
        self.assertEqual(first.status, OfferStatus.LAPSED)
        self.fresh()
        self.assertEqual(self.line.hourly_rate, D("30.00"))
        self.assertIsNone(offers.applied_offer(self.line))

    def test_taking_the_request_back_ends_the_negotiation(self) -> None:
        first = self.offer("60.00")
        crew.update_crew_line(self.line, rights=Rights.everything(), person=None)
        first.refresh_from_db()
        self.assertEqual(first.status, OfferStatus.LAPSED)


class ReleaseTests(OffersTestCase):
    """An accepted offer stops applying when it no longer fits the line."""

    def setUp(self) -> None:
        super().setUp()
        switch_on()
        self.ask()
        self.accepted = self.offer("45.00")
        offers.accept_offer(self.accepted, acting=self.company)
        self.fresh()

    def released(self) -> PriceOffer:
        self.accepted.refresh_from_db()
        return self.accepted

    def test_the_marker(self) -> None:
        self.assertEqual(offers.applied_offer(self.line), self.accepted)

    def test_a_rate_changed_by_hand_ends_it(self) -> None:
        crew.update_crew_line(self.line, rights=Rights.everything(), hourly_rate=D("48.00"))
        self.fresh()
        self.assertEqual(self.line.hourly_rate, D("48.00"))
        self.assertEqual((self.released().applied, self.released().release_reason), (False, ReleaseReason.MANUAL))
        self.assertIsNone(offers.applied_offer(self.line))

    def test_another_person_ends_it_and_gets_the_rate_of_their_own(self) -> None:
        other = make_person("Otto Neu", kind=EmploymentKind.FREELANCER, rates={"Tontechnik": "28.00"})
        crew.update_crew_line(self.line, rights=Rights.everything(), person=other)
        self.fresh()
        self.assertEqual((self.released().applied, self.released().release_reason), (False, ReleaseReason.PERSON))
        self.assertNotEqual(self.line.hourly_rate, D("45.00"))

    def test_other_changes_keep_it(self) -> None:
        crew.update_crew_line(self.line, rights=Rights.everything(), note="Bitte pünktlich")
        self.assertTrue(self.released().applied)

    def test_a_total_ends_with_new_times_a_rate_stays(self) -> None:
        offers.release_offer(self.released(), reason=ReleaseReason.REVOKED, restore=True)
        self.fresh()
        self.assertEqual(self.line.hourly_rate, D("30.00"))  # restored
        # Ask again for a total.
        crew.update_crew_line(self.line, rights=Rights.everything(), start=at(10, 9))
        self.fresh()
        total = self.offer("400.00", OfferUnit.TOTAL)
        offers.accept_offer(total, acting=self.company)
        self.fresh()
        self.assertEqual(self.line.cost_flat_rate, D("400.00"))
        crew.update_crew_line(self.line, rights=Rights.everything(), end=at(10, 20))
        self.fresh()
        total.refresh_from_db()
        self.assertEqual((total.applied, total.release_reason), (False, ReleaseReason.TIMES))
        self.assertIsNone(self.line.cost_flat_rate)  # the rate before comes back

    def test_the_release_is_traced(self) -> None:
        crew.update_crew_line(self.line, rights=Rights.everything(), hourly_rate=D("48.00"))
        self.assertTrue(AuditLogEntry.objects.filter(event=offers.EVENT_RELEASED).exists())


class PrivacyTests(OffersTestCase):
    """Offers are personnel costs (AUT-019)."""

    def setUp(self) -> None:
        super().setUp()
        switch_on()
        self.ask()

    def test_who_acts_for_whom(self) -> None:
        self.project.access = access_level(self.manager.rights, self.manager, self.project)
        mine = offers.acting_for(self.manager, self.manager.rights, self.project, self.line)
        self.assertEqual((mine.own, mine.planner), (False, True))
        self.project.access = access_level(self.account.rights, self.account, self.project)
        theirs = offers.acting_for(self.account, self.account.rights, self.project, self.line)
        self.assertEqual((theirs.own, theirs.planner), (True, False))
        stranger = make_user("stefan", roles=("Freie Kraft",))
        make_person("Stefan Fremd", user=stranger, kind=EmploymentKind.FREELANCER)
        nothing = offers.acting_for(stranger, stranger.rights, self.project, self.line)
        self.assertFalse(nothing.allowed)

    def test_a_planner_without_the_cost_right_is_nobody_here(self) -> None:
        reader = make_user("lena", roles=("Lager",))  # reads projects, no personnel costs
        self.project.access = access_level(reader.rights, reader, self.project)
        self.assertFalse(offers.acting_for(reader, reader.rights, self.project, self.line).allowed)

    def test_the_rate_is_known_to_the_company_and_to_who_may_see_their_own_rates(self) -> None:
        self.assertTrue(offers.may_know_own_rates(self.manager))
        self.assertFalse(offers.may_know_own_rates(self.account))
        system = SystemSettings.load()
        system.people_see_own_rates = True
        system.save()
        self.assertTrue(offers.may_know_own_rates(self.account))


# --- Pages -------------------------------------------------------------------------------------------------------


class SettingsPageTests(UiTestCase):
    """Einstellungen → Preisangebote."""

    def test_default_off_and_save(self) -> None:
        page = self.client.get(reverse("personnel:offer_settings"))
        self.assertContains(page, "Preisangebote freier Kräfte")
        self.assertFalse(OfferSettings.load().enabled)
        response = self.client.post(
            reverse("personnel:offer_settings"),
            {"enabled": "on", "min_percent": "80", "max_percent": "130", "max_rounds": "4"},
        )
        self.assertEqual(response.status_code, 302)
        current = OfferSettings.load()
        self.assertEqual(
            (current.enabled, current.min_percent, current.max_percent, current.max_rounds),
            (True, D("80"), D("130"), 4),
        )
        self.assertFalse(current.also_temporary)

    def test_a_wrong_limit_is_shown(self) -> None:
        page = self.client.post(
            reverse("personnel:offer_settings"),
            {"enabled": "on", "min_percent": "150", "max_percent": "100", "max_rounds": "3"},
        )
        self.assertContains(page, "Das höchste Angebot darf nicht unter dem niedrigsten liegen.")
        self.assertFalse(OfferSettings.load().enabled)

    def test_only_the_administration_reads_it(self) -> None:
        crew_browser = self.browser_for("frieda", "Freie Kraft")
        self.assertEqual(crew_browser.get(reverse("personnel:offer_settings")).status_code, 403)
        reader = self.browser_for("rita", "Nur-Lesen")
        self.assertEqual(reader.get(reverse("personnel:offer_settings")).status_code, 403)


class PagesTestCase(UiTestCase, OffersTestCase):
    """The pages of an offer: the freelancer's deployment view, the planning, the overview."""

    def setUp(self) -> None:
        super().setUp()
        switch_on()
        self.ask()
        self.manager_browser = self.browser_of(self.manager)
        self.freelancer = self.browser_of(self.account)

    def url(self, name: str, *extra: int) -> str:
        return reverse(f"personnel:{name}", args=[self.project.number, self.line.pk, *extra])


class FreelancerPageTests(PagesTestCase):
    def test_the_deployment_view_offers_the_button(self) -> None:
        page = self.freelancer.get(reverse("projects:deployment", args=[self.project.number]))
        self.assertContains(page, "Preisangebot machen")
        self.assertContains(page, self.url("offer_make"))

    def test_nothing_when_switched_off(self) -> None:
        current = OfferSettings.load()
        current.enabled = False
        current.save()
        page = self.freelancer.get(reverse("projects:deployment", args=[self.project.number]))
        self.assertNotContains(page, "Preisangebot")

    def test_make_an_offer(self) -> None:
        form = self.freelancer.get(self.url("offer_make"))
        self.assertContains(form, "Preisangebot machen")
        self.assertNotContains(form, "30,00")  # the stored rate is not shown to who may not know it
        response = self.freelancer.post(
            self.url("offer_make"), {"amount": "42.50", "unit": "hour", "message": "Nachts"}
        )
        self.assertRedirects(response, reverse("projects:deployment", args=[self.project.number]))
        (offer,) = PriceOffer.objects.all()
        self.assertEqual((offer.amount, offer.message), (D("42.50"), "Nachts"))
        page = self.freelancer.get(reverse("projects:deployment", args=[self.project.number]))
        self.assertContains(page, "wartet auf Antwort")
        self.assertContains(page, "Angebot zurückziehen")

    def test_errors_are_shown_at_the_field(self) -> None:
        switch_on(max_percent=D("120"))
        page = self.freelancer.post(self.url("offer_make"), {"amount": "99.00", "unit": "hour"})
        self.assertContains(page, "außerhalb")
        self.assertNotContains(page, "30,00")
        self.assertEqual(PriceOffer.objects.count(), 0)

    def test_the_freelancer_may_see_the_rate_when_the_setting_says_so(self) -> None:
        system = SystemSettings.load()
        system.people_see_own_rates = True
        system.save()
        self.assertContains(self.freelancer.get(self.url("offer_make")), "30,00")

    def test_a_stranger_gets_403(self) -> None:
        stranger = self.browser_for("stefan", "Freie Kraft")
        self.assertEqual(stranger.get(self.url("offer_make")).status_code, 404)
        offer = self.offer()
        other = make_person(
            "Stefan Fremd", user=make_user("stefan2", roles=("Freie Kraft",)), kind=EmploymentKind.FREELANCER
        )
        plan(self.project, self.function, other, start=at(11, 10), end=at(11, 18))
        in_project = self.browser_of(other.user)
        for name in ("offer_accept", "offer_reject", "offer_withdraw"):
            with self.subTest(name):
                response = in_project.post(self.url(name, offer.pk))
                self.assertEqual(response.status_code, 403)
        self.assertEqual(in_project.get(self.url("offer_make")).status_code, 403)

    def test_get_does_not_change_anything(self) -> None:
        offer = self.offer()
        for name in ("offer_accept", "offer_reject", "offer_withdraw"):
            self.assertEqual(self.freelancer.get(self.url(name, offer.pk)).status_code, 405)
        offer.refresh_from_db()
        self.assertEqual(offer.status, OfferStatus.OPEN)

    def test_withdraw(self) -> None:
        offer = self.offer()
        self.freelancer.post(self.url("offer_withdraw", offer.pk))
        offer.refresh_from_db()
        self.assertEqual(offer.status, OfferStatus.WITHDRAWN)

    def test_answer_a_counter(self) -> None:
        counter = offers.counter_offer(self.offer("60.00"), acting=self.company, amount=D("36.00"))
        page = self.freelancer.get(reverse("projects:deployment", args=[self.project.number]))
        self.assertContains(page, "Gegenangebot annehmen")
        self.freelancer.post(self.url("offer_accept", counter.pk))
        self.fresh()
        self.assertEqual((self.line.request_status, self.line.hourly_rate), (RequestStatus.ACCEPTED, D("36.00")))

    def test_counter_page(self) -> None:
        counter = offers.counter_offer(self.offer("60.00"), acting=self.company, amount=D("36.00"))
        self.assertContains(self.freelancer.get(self.url("offer_counter", counter.pk)), "Dein Gegenangebot")
        self.freelancer.post(self.url("offer_counter", counter.pk), {"amount": "38.00", "unit": "hour"})
        self.assertEqual(PriceOffer.objects.count(), 3)

    def test_the_start_page_points_at_the_open_counter(self) -> None:
        offers.counter_offer(self.offer("60.00"), acting=self.company, amount=D("36.00"))
        self.assertContains(self.freelancer.get("/"), "Gegenangebot")


class CompanyPageTests(PagesTestCase):
    def test_the_planning_shows_the_offer_next_to_the_stored_rate(self) -> None:
        self.offer("42.50", message="Nachts")
        page = self.manager_browser.get(reverse("projects:detail", args=[self.project.number]))
        self.assertContains(page, "Preisangebot</span>")
        self.assertContains(page, "42,50")
        self.assertContains(page, "hinterlegt: 30,00")
        self.assertContains(page, "Nachts")
        self.assertContains(page, self.url("offer_accept", PriceOffer.objects.get().pk))

    def test_the_planning_without_the_cost_right_shows_nothing(self) -> None:
        self.offer("42.50")
        reader = self.browser_for("lena", "Lager")
        page = reader.get(reverse("projects:detail", args=[self.project.number]))
        self.assertNotContains(page, "Preisangebot")
        self.assertNotContains(page, "42,50")

    def test_accept_in_the_planning_with_htmx(self) -> None:
        offer = self.offer("45.00")
        response = self.manager_browser.post(self.url("offer_accept", offer.pk), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.fresh()
        self.assertEqual((self.line.request_status, self.line.hourly_rate), (RequestStatus.ACCEPTED, D("45.00")))
        page = self.manager_browser.get(reverse("projects:detail", args=[self.project.number]))
        self.assertContains(page, "data-offer-mark")
        self.assertContains(page, "Angebot angenommen")
        self.assertContains(page, "hinterlegt: 30,00")

    def test_reject_and_counter(self) -> None:
        offer = self.offer("60.00")
        self.manager_browser.post(self.url("offer_reject", offer.pk), {"note": "Zu teuer"})
        offer.refresh_from_db()
        self.assertEqual((offer.status, offer.decision_note), (OfferStatus.REJECTED, "Zu teuer"))
        second = self.offer("55.00")
        self.assertContains(self.manager_browser.get(self.url("offer_counter", second.pk)), "Dein Gegenangebot")
        self.manager_browser.post(self.url("offer_counter", second.pk), {"amount": "40.00", "unit": "hour"})
        self.assertEqual(PriceOffer.objects.filter(side=OfferSide.COMPANY).count(), 1)

    def test_a_manager_without_the_cost_right_cannot_decide(self) -> None:
        offer = self.offer("45.00")
        planner_without = make_user("pia", roles=("Projektleitung",))
        from rentalars.accounts.models import Role

        role = Role.objects.create(
            name="Plant ohne Kosten", module_levels={"projects": 2, "personnel": 1}, special_rights=[]
        )
        planner_without.roles.set([role])
        from rentalars.projects.models import ProjectMembership

        ProjectMembership.objects.create(project=self.project, user=planner_without, level="edit")
        browser = self.browser_of(planner_without)
        self.assertEqual(browser.post(self.url("offer_accept", offer.pk)).status_code, 403)

    def test_the_overview(self) -> None:
        self.offer("42.50")
        page = self.manager_browser.get(reverse("personnel:offer_list"))
        self.assertContains(page, "Preisangebote")
        self.assertContains(page, "Frieda Frei")
        self.assertContains(page, "42,50")
        self.assertContains(page, "Stadtfest")
        offers.reject_offer(PriceOffer.objects.get(), acting=self.company)
        self.assertContains(
            self.manager_browser.get(reverse("personnel:offer_list")), "Kein Angebot wartet auf Antwort."
        )
        self.assertContains(self.manager_browser.get(reverse("personnel:offer_list"), {"show": "all"}), "42,50")

    def test_the_overview_is_for_who_sees_costs(self) -> None:
        self.offer("42.50")
        self.assertEqual(self.freelancer.get(reverse("personnel:offer_list")).status_code, 403)
        self.assertEqual(self.browser_for("lena", "Lager").get(reverse("personnel:offer_list")).status_code, 403)

    def test_a_closed_overview_without_the_feature_still_shows_old_offers(self) -> None:
        self.offer("42.50")
        current = OfferSettings.load()
        current.enabled = False
        current.save()
        page = self.manager_browser.get(reverse("personnel:offer_list"), {"show": "all"})
        self.assertContains(page, "ausgeschaltet")
        self.assertContains(page, "42,50")

    def mail_to_the_freelancer(self) -> tuple[str, str]:
        """Ask again; the text and the html part of the mail to the freelancer."""
        from django.core import mail as django_mail

        from tests.mailbox import configure_mailbox

        configure_mailbox()  # the mail with the buttons to answer by mail is the one that carries the hint
        self.line = type(self.line).objects.get(pk=self.line.pk)  # with the person and account as they are now
        django_mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            crew.request_deployment(self.line, user=self.manager)
        (message,) = [m for m in django_mail.outbox if m.alternatives]  # the request with the buttons
        return message.body, message.alternatives[0][0]

    def test_the_mail_points_to_the_offer_in_german_and_english(self) -> None:
        """The request mail names the way to an offer, only while the feature is on (additive, PER-032)."""
        self.person.email = "frieda@crew.example"
        self.person.save()
        link = f"/projects/{self.project.number}/crew/{self.line.pk}/offer/"
        text, html = self.mail_to_the_freelancer()
        self.assertIn("Du möchtest deinen eigenen Preis nennen? Das geht in Rentalars:", text)
        self.assertIn(link, text)
        self.assertIn(link, html)
        self.account.language = "en"
        self.account.save()
        text, html = self.mail_to_the_freelancer()
        self.assertIn("Want to name your own price? You can make an offer in Rentalars:", text)
        self.assertIn(link, html)

    def test_the_mail_is_as_before_when_off_or_for_an_employee(self) -> None:
        self.person.email = "frieda@crew.example"
        self.person.save()
        current = OfferSettings.load()
        current.enabled = False
        current.save()
        text, html = self.mail_to_the_freelancer()
        self.assertNotIn("Preis nennen", text + html)
        self.assertNotIn("/offer/", text + html)
        switch_on()
        self.person.kind = EmploymentKind.EMPLOYEE
        self.person.save()
        text, html = self.mail_to_the_freelancer()
        self.assertNotIn("/offer/", text + html)


class LoginTests(UiTestCase):
    def test_anonymous_is_sent_to_login(self) -> None:
        self.client.logout()
        self.assertEqual(self.client.get(reverse("personnel:offer_list")).status_code, 302)
        self.assertEqual(self.client.get(reverse("personnel:offer_settings")).status_code, 302)


# --- API -----------------------------------------------------------------------------------------------------------


class OfferApiTestCase(ApiTestCase, OffersTestCase):
    """Every operation of the API of the offers (API-002, API-014)."""

    def setUp(self) -> None:
        super().setUp()
        self.company_client = self.client_of(self.manager)
        self.freelancer_client = self.client_of(self.account)

    def base(self) -> str:
        return f"{API}/projects/{self.project.pk}/crew-lines/{self.line.pk}/offers"


class ApiSettingsTests(OfferApiTestCase):
    def test_get_and_patch(self) -> None:
        got = self.admin.get(f"{API}/settings/price-offers")
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.json()["enabled"], False)
        patched = self.admin.patch(
            f"{API}/settings/price-offers", {"enabled": True, "min_percent": "80", "max_rounds": 5}, format="json"
        )
        self.assertEqual(patched.status_code, 200, patched.content)
        self.assertEqual((patched.json()["enabled"], patched.json()["max_rounds"]), (True, 5))
        self.assertTrue(OfferSettings.load().enabled)

    def test_validation(self) -> None:
        for body in (
            {"max_rounds": 0},
            {"max_rounds": 11},
            {"min_percent": "-1"},
            {"min_percent": "x"},
            {"enabled": "maybe"},
        ):
            with self.subTest(body=body):
                self.assert_error(
                    self.admin.patch(f"{API}/settings/price-offers", body, format="json"), 400, "validation_error"
                )
        self.assert_error(
            self.admin.patch(
                f"{API}/settings/price-offers", {"min_percent": "150", "max_percent": "100"}, format="json"
            ),
            400,
            "validation_error",
        )

    def test_rights(self) -> None:
        self.assertEqual(self.freelancer_client.get(f"{API}/settings/price-offers").status_code, 403)
        self.assertEqual(self.company_client.get(f"{API}/settings/price-offers").status_code, 403)
        reader = self.client_for("rita", "Nur-Lesen")
        self.assertEqual(reader.get(f"{API}/settings/price-offers").status_code, 403)
        self.assertEqual(
            reader.patch(f"{API}/settings/price-offers", {"enabled": True}, format="json").status_code, 403
        )
        self.assertFalse(OfferSettings.load().enabled)
        self.assertEqual(anonymous_client().get(f"{API}/settings/price-offers").status_code, 401)


def anonymous_client():
    from rest_framework.test import APIClient

    return APIClient()


class ApiExchangeTests(OfferApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        switch_on()
        self.ask()

    def test_get_before_any_offer(self) -> None:
        got = self.freelancer_client.get(self.base())
        self.assertEqual(got.status_code, 200)
        body = got.json()
        self.assertEqual((body["enabled"], body["can_offer"], body["offers"], body["rounds_used"]), (True, True, [], 0))
        self.assertEqual(body["units"], ["hour", "total"])

    def test_the_whole_negotiation(self) -> None:
        made = self.freelancer_client.post(
            self.base(), {"amount": "60.00", "unit": "hour", "message": "Nachts"}, format="json"
        )
        self.assertEqual(made.status_code, 201, made.content)
        first = made.json()
        self.assertEqual((first["amount"], first["status"], first["side"]), ("60.00", "open", "freelancer"))
        self.assertIsNone(first["reference_amount"])  # the freelancer does not see the stored rate
        company_view = self.company_client.get(self.base()).json()
        self.assertEqual(company_view["offers"][0]["reference_amount"], "30.00")
        self.assertEqual(company_view["offers"][0]["percent_of_reference"], "200.0")
        self.assertFalse(company_view["can_offer"])
        countered = self.company_client.post(
            f"{self.base()}/{first['id']}/counter", {"amount": "40.00", "message": "Mehr nicht"}, format="json"
        )
        self.assertEqual(countered.status_code, 200, countered.content)
        second = countered.json()
        self.assertEqual((second["side"], second["unit"], second["round"]), ("company", "hour", 2))
        accepted = self.freelancer_client.post(f"{self.base()}/{second['id']}/accept", {}, format="json")
        self.assertEqual(accepted.status_code, 200, accepted.content)
        self.assertEqual((accepted.json()["applied"], accepted.json()["request_status"]), (True, "accepted"))
        self.fresh()
        self.assertEqual(self.line.hourly_rate, D("40.00"))

    def test_reject_and_withdraw(self) -> None:
        first = self.freelancer_client.post(self.base(), {"amount": "60.00", "unit": "hour"}, format="json").json()
        rejected = self.company_client.post(f"{self.base()}/{first['id']}/reject", {"note": "Nein"}, format="json")
        self.assertEqual(
            (rejected.status_code, rejected.json()["status"], rejected.json()["decision_note"]),
            (200, "rejected", "Nein"),
        )
        second = self.freelancer_client.post(self.base(), {"amount": "50.00", "unit": "total"}, format="json").json()
        withdrawn = self.freelancer_client.post(f"{self.base()}/{second['id']}/withdraw", {}, format="json")
        self.assertEqual((withdrawn.status_code, withdrawn.json()["status"]), (200, "withdrawn"))

    def test_accept_by_the_company(self) -> None:
        first = self.freelancer_client.post(self.base(), {"amount": "45.00", "unit": "hour"}, format="json").json()
        accepted = self.company_client.post(f"{self.base()}/{first['id']}/accept", {"note": "Ok"}, format="json")
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["reference_amount"], "30.00")
        line = self.company_client.get(f"{API}/projects/{self.project.pk}/crew-lines").json()
        self.assertTrue(line)

    def test_validation_errors(self) -> None:
        bad = [
            {"amount": "abc", "unit": "hour"},
            {"amount": "-1", "unit": "hour"},
            {"amount": "0", "unit": "hour"},
            {"amount": "12.345", "unit": "hour"},
            {"amount": "100000000.00", "unit": "hour"},
            {"amount": "10", "unit": "week"},
            {"amount": "10", "unit": "hour", "currency": "USD"},
            {"amount": "10", "unit": "hour", "currency": "EURO"},
            {"amount": "10", "unit": "hour", "message": "x" * 501},
            {"amount": "10", "unit": "hour", "valid_until": "2027-01-01"},
            {"amount": "10", "unit": "hour", "valid_until": "morgen"},
            {"amount": "10"},
            {"unit": "hour"},
            {"amount": "NaN", "unit": "hour"},
        ]
        for body in bad:
            with self.subTest(body=body):
                response = self.freelancer_client.post(self.base(), body, format="json")
                self.assert_error(response, 400, "validation_error")
        self.assertEqual(PriceOffer.objects.count(), 0)

    def test_limits_over_the_api(self) -> None:
        switch_on(min_percent=D("90"), max_percent=D("150"))
        response = self.freelancer_client.post(self.base(), {"amount": "100", "unit": "hour"}, format="json")
        error = self.assert_error(response, 400, "validation_error", "amount")
        self.assertNotIn("30,00", str(error))
        self.assertEqual(
            self.freelancer_client.post(self.base(), {"amount": "40", "unit": "hour"}, format="json").status_code, 201
        )

    def test_conflicts(self) -> None:
        first = self.freelancer_client.post(self.base(), {"amount": "45.00", "unit": "hour"}, format="json").json()
        self.assert_error(
            self.freelancer_client.post(self.base(), {"amount": "46.00", "unit": "hour"}, format="json"),
            400,
            "validation_error",
        )
        self.assertEqual(
            self.company_client.post(f"{self.base()}/{first['id']}/accept", {}, format="json").status_code, 200
        )
        for action in ("accept", "reject", "withdraw"):
            with self.subTest(action):
                self.assert_error(
                    self.company_client.post(f"{self.base()}/{first['id']}/{action}", {}, format="json"),
                    400,
                    "validation_error",
                )
        self.assert_error(
            self.company_client.post(f"{self.base()}/{first['id']}/counter", {"amount": "30"}, format="json"),
            400,
            "validation_error",
        )

    def test_off_means_400(self) -> None:
        current = OfferSettings.load()
        current.enabled = False
        current.save()
        self.assert_error(
            self.freelancer_client.post(self.base(), {"amount": "45", "unit": "hour"}, format="json"),
            400,
            "validation_error",
        )
        self.assertFalse(self.freelancer_client.get(self.base()).json()["can_offer"])

    def test_privacy(self) -> None:
        first = self.freelancer_client.post(self.base(), {"amount": "45.00", "unit": "hour"}, format="json").json()
        stranger = make_person(
            "Stefan Fremd", user=make_user("stefan", roles=("Freie Kraft",)), kind=EmploymentKind.FREELANCER
        )
        plan(self.project, self.function, stranger, start=at(11, 10), end=at(11, 18))
        other = self.client_of(stranger.user)
        self.assertEqual(other.get(self.base()).status_code, 403)
        self.assertEqual(other.post(self.base(), {"amount": "45", "unit": "hour"}, format="json").status_code, 403)
        for action in ("accept", "reject", "counter", "withdraw"):
            with self.subTest(action):
                self.assertEqual(
                    other.post(f"{self.base()}/{first['id']}/{action}", {"amount": "30"}, format="json").status_code,
                    403,
                )
        self.assertEqual(
            self.freelancer_client.post(f"{self.base()}/{first['id']}/accept", {}, format="json").status_code, 403
        )
        nobody = self.client_for("nobody")
        self.assertEqual(nobody.get(self.base()).status_code, 403)
        reader = self.client_for("lena", "Lager")
        self.assertEqual(reader.get(self.base()).status_code, 403)
        self.assertEqual(anonymous_client().get(self.base()).status_code, 401)
        self.assertEqual(self.company_client.get(f"{self.base()}/9999/accept").status_code, 405)
        self.assertEqual(self.company_client.post(f"{self.base()}/9999/accept", {}, format="json").status_code, 404)

    def test_the_line_of_another_project_is_not_reachable(self) -> None:
        other = make_project("Andere", manager=self.manager)
        self.assertEqual(
            self.company_client.get(f"{API}/projects/{other.pk}/crew-lines/{self.line.pk}/offers").status_code, 404
        )

    def test_the_right_for_costs_is_needed_to_decide(self) -> None:
        first = self.freelancer_client.post(self.base(), {"amount": "45.00", "unit": "hour"}, format="json").json()
        from rentalars.accounts.models import Role
        from rentalars.projects.models import ProjectMembership

        role = Role.objects.create(
            name="Plant ohne Kosten", module_levels={"projects": 2, "personnel": 1}, special_rights=[]
        )
        user = make_user("pia")
        user.roles.set([role])
        ProjectMembership.objects.create(project=self.project, user=user, level="edit")
        client = self.client_of(user)
        self.assertEqual(client.post(f"{self.base()}/{first['id']}/accept", {}, format="json").status_code, 403)
        self.assertEqual(client.get(self.base()).status_code, 403)


class ApiOverviewTests(OfferApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        switch_on()
        self.ask()

    def test_price_offers(self) -> None:
        self.freelancer_client.post(self.base(), {"amount": "45.00", "unit": "hour"}, format="json")
        got = self.company_client.get(f"{API}/price-offers")
        self.assertEqual(got.status_code, 200)
        (item,) = got.json()
        self.assertEqual(
            (item["crew_line"], item["person_name"], item["waiting"], item["can_decide"]),
            (self.line.pk, "Frieda Frei", True, True),
        )
        self.assertEqual(item["offers"][0]["reference_amount"], "30.00")
        offers.reject_offer(PriceOffer.objects.get(), acting=self.company)
        self.assertEqual(self.company_client.get(f"{API}/price-offers").json(), [])
        self.assertEqual(len(self.company_client.get(f"{API}/price-offers", {"show": "all"}).json()), 1)

    def test_price_offers_need_the_cost_right(self) -> None:
        self.assertEqual(self.freelancer_client.get(f"{API}/price-offers").status_code, 403)
        self.assertEqual(self.client_for("lena", "Lager").get(f"{API}/price-offers").status_code, 403)
        self.assertEqual(anonymous_client().get(f"{API}/price-offers").status_code, 401)

    def test_own_offers(self) -> None:
        self.freelancer_client.post(self.base(), {"amount": "45.00", "unit": "hour"}, format="json")
        got = self.freelancer_client.get(f"{API}/people/me/offers")
        self.assertEqual(got.status_code, 200)
        (item,) = got.json()
        self.assertEqual(item["offers"][0]["amount"], "45.00")
        self.assertIsNone(item["offers"][0]["reference_amount"])
        self.assertNotIn("can_decide", item)
        # Not the offers of others.
        other = self.client_of(
            make_person(
                "Stefan Fremd", user=make_user("stefan", roles=("Freie Kraft",)), kind=EmploymentKind.FREELANCER
            ).user
        )
        self.assertEqual(other.get(f"{API}/people/me/offers").json(), [])
        self.assertEqual(anonymous_client().get(f"{API}/people/me/offers").status_code, 401)

    def test_own_offers_with_the_setting_for_own_rates(self) -> None:
        self.freelancer_client.post(self.base(), {"amount": "45.00", "unit": "hour"}, format="json")
        system = SystemSettings.load()
        system.people_see_own_rates = True
        system.save()
        (item,) = self.freelancer_client.get(f"{API}/people/me/offers").json()
        self.assertEqual(item["offers"][0]["reference_amount"], "30.00")

    def test_a_token_user_without_a_person_gets_404(self) -> None:
        user = make_user("ohne")
        person_model = type(self.person)
        person_model.objects.filter(user=user).delete()
        self.assertEqual(self.client_of(user).get(f"{API}/people/me/offers").status_code, 404)

    def test_the_planning_api_follows_the_offer(self) -> None:
        offer = self.freelancer_client.post(self.base(), {"amount": "45.00", "unit": "hour"}, format="json").json()
        self.company_client.post(f"{self.base()}/{offer['id']}/accept", {}, format="json")
        lines = self.company_client.get(f"{API}/projects/{self.project.pk}/crew-lines").json()
        rows = lines["results"] if isinstance(lines, dict) else lines
        row = next(item for item in rows if item["id"] == self.line.pk)
        self.assertIn(row.get("hourly_rate"), ("45.00", 45.0, D("45.00")))
