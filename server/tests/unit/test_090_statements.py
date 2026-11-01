# SPDX-License-Identifier: GPL-3.0-or-later
"""The semi-automatic monthly statement of service cases per customer (DOK-016).

The requirement: semi-automatic monthly invoices for service cases per customer, with a summary of the activity.
The invoice follows the setting "Rentalars als Buchhaltungsprogramm verwenden": when the invoices are made in
Rentalars, an invoice draft is created; otherwise a view, like the price overview of projects, from which the values
can be copied to the clipboard quickly for the other software.

* Collected per customer: the service cases done in the month or with approved times or expenses in it – not
  internal ones, not those invoiced otherwise or marked "Keine Rechnung", not those in another draft.
* Per case the times by job function (hours, days, flat; hour tiers), the expenses, free positions, and an activity
  text from description, notes and correspondence – or by the AI.
* Invoices made in Rentalars: one invoice with a section per case, of the first case, billing all of them; they
  count as invoiced, and a cancellation opens them again. Written elsewhere: the values to copy, and "Als
  abgerechnet markieren".
"""

from __future__ import annotations

import datetime
import shutil
import tempfile
from decimal import Decimal
from pathlib import Path

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import override_settings
from django.urls import reverse

from rentalars.core.models import NotificationSettings, SystemSettings
from rentalars.documents import invoice_reminders, statements
from rentalars.documents.invoice_reminders import InvoiceState
from rentalars.documents.models import Document, DocumentKind, MonthlyStatement, StatementStatus
from rentalars.documents.services import cancel_invoice, check_can_make
from rentalars.mail.models import Direction, ProjectMail
from rentalars.masterdata.models import TaxRate
from rentalars.products.models import BillingMode
from rentalars.projects import service_cases
from rentalars.projects.models import CaseStatus, InvoiceMark, Project
from rentalars.timetracking.models import Expense, ExpenseKind, TimeEntryStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    NOW,
    RentalarsTestCase,
    at,
    job_function,
    make_customer,
    make_person,
    make_product,
    make_user,
    ready_for_invoices,
    record_time,
    set_clock,
)
from tests.ui.base import UiTestCase, form_data

MARCH = datetime.date(2027, 3, 1)
FEBRUARY = datetime.date(2027, 2, 1)
D = Decimal


def invoices_in_rentalars(on: bool) -> None:
    settings = SystemSettings.load()
    settings.invoices_enabled = on
    settings.save()


def remind_of_cases() -> None:
    """DOK-015: the invoice of done service cases is followed (also for done service cases, if wanted)."""
    settings = NotificationSettings.load()
    settings.invoice_service_cases = True
    settings.save()


class StatementSetup:
    """Two cases of "Theater am Markt", Tom Fischer doing the sound engineering at 50,00 € an hour."""

    def setUp(self) -> None:
        super().setUp()  # type: ignore[misc]
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.customer = ready_for_invoices(make_customer("Theater am Markt"))
        self.tom = make_person("Tom Fischer")
        self.sound = job_function("Tontechnik", price="50.00")
        self.spot = self.case("Spot flackert", notes="Spot 3 über der Bühne flackert.")
        self.mixer = self.case("Mischpult brummt")

    def case(self, name: str, customer: object = None, **fields: object) -> Project:
        return service_cases.create_case(name=name, customer=customer or self.customer, manager=self.paula, **fields)

    def work(self, case: Project, start: datetime.datetime, end: datetime.datetime, **fields: object) -> object:
        function = fields.pop("function", self.sound)
        person = fields.pop("person", self.tom)
        return record_time(person, case, function, start, end, approve=fields.pop("approve", True), **fields)

    def spend(self, case: Project, day: datetime.date, amount: str = "", **fields: object) -> Expense:
        values = {
            "person": self.tom,
            "project": case,
            "kind": ExpenseKind.PARKING,
            "date": day,
            "amount": D(amount or "0"),
            "status": TimeEntryStatus.APPROVED,
            **fields,
        }
        return Expense.objects.create(**values)

    def done(self, case: Project, when: datetime.datetime | None = None) -> Project:
        if when is not None:
            set_clock(when)
        service_cases.set_case_status(case, CaseStatus.DONE, by=self.paula)
        set_clock(NOW)
        return Project.objects.get(pk=case.pk)

    def statement(self, month: datetime.date = MARCH) -> MonthlyStatement:
        made, _created = statements.create_statement(self.customer, month, user=self.paula)
        return made

    def positions(self, statement: MonthlyStatement, case: Project) -> list[dict]:
        return statements.case_entry(MonthlyStatement.objects.get(pk=statement.pk), case.pk)["positions"]


class CollectTests(StatementSetup, RentalarsTestCase):
    """Which cases a month bills – and which times."""

    def test_times_of_the_month(self) -> None:
        self.work(self.spot, at(3, 9), at(3, 12))  # 3 h
        self.work(self.spot, at(5, 14), at(5, 15, 30))  # 1.5 h
        self.work(self.spot, at(8, 9), at(8, 10), approve=False)  # not approved: not billed
        self.work(self.spot, at(2, 9, month=4), at(2, 10, month=4))  # April: not in March
        found = statements.collect(MARCH, customer=self.customer)
        self.assertEqual([item.case for item in found], [self.spot])
        position = found[0].positions[0]
        self.assertEqual((position["title"], position["quantity"], position["unit_price"]), ("Tontechnik", "4.5", "50"))
        self.assertEqual(statements.amount_of(position), D("225.00"))
        self.assertEqual(position["unit_code"], "HUR")
        self.assertEqual(position["details"], "am 03.03., 05.03.2027")
        # Not in February; April has its own time only.
        self.assertEqual(statements.collect(FEBRUARY, customer=self.customer), [])
        april = statements.collect(datetime.date(2027, 4, 1), customer=self.customer)
        self.assertEqual([item["quantity"] for item in april[0].positions], ["1"])

    def test_done_in_the_month(self) -> None:
        """A case done in the month comes even without times – there may be material to add."""
        self.done(self.spot)  # 1 March
        set_clock(at(15, 9, month=2))
        earlier = self.case("Im Februar erledigt")
        self.done(earlier, at(20, 10, month=2))
        found = statements.collect(MARCH, customer=self.customer)
        self.assertEqual([(item.case, item.done_in_month, item.positions) for item in found], [(self.spot, True, [])])
        self.assertEqual([item.case for item in statements.collect(FEBRUARY, customer=self.customer)], [earlier])

    def test_done_in_the_month_takes_the_earlier_times_not_billed(self) -> None:
        self.work(self.spot, at(20, 9, month=2), at(20, 11, month=2))
        self.done(self.spot)
        found = statements.collect(MARCH, customer=self.customer)
        self.assertEqual(found[0].positions[0]["quantity"], "2")
        # The statement of March tells the invoice the service began in February.
        statement = self.statement()
        content = statements.build_invoice_content(statement, number="X", issued_on=MARCH)
        self.assertEqual(
            (content.service_start, content.service_end), (datetime.date(2027, 2, 20), datetime.date(2027, 3, 31))
        )

    def test_left_out(self) -> None:
        """Internal cases, "Keine Rechnung", "Rechnung gestellt" by hand, an invoice of its own, another draft."""
        internal = service_cases.create_case(name="Eigener Spot", is_internal=True, manager=self.paula)
        free = self.case("Kostenlos")
        ticked = self.case("Schon gestellt")
        own = self.case("Eigene Rechnung")
        other = self.case("Anderer Kunde", customer=make_customer("Kino"))
        for hour, case in enumerate((internal, free, ticked, own, other, self.spot), start=8):
            self.work(case, at(3, hour), at(3, hour, 30))
            self.done(case)
        free.invoice_status = InvoiceMark.NOT_NEEDED
        free.save()
        ticked.invoice_status = InvoiceMark.ISSUED
        ticked.save()
        Document.objects.create(
            project=own,
            kind=DocumentKind.INVOICE,
            number="RE-1",
            title="Rechnung",
            issued_on=MARCH,
            file="documents/x.pdf",
            sha256="0" * 64,
        )
        self.assertEqual([item.case for item in statements.collect(MARCH, customer=self.customer)], [self.spot])
        self.assertEqual([item.case for item in statements.collect(MARCH)], [self.spot, other])
        self.statement()
        # In a draft now: not offered again, not in a second statement.
        self.assertEqual(statements.collect(MARCH, customer=self.customer), [])

    def test_billing_modes_of_the_job_functions(self) -> None:
        """PRD-044: hours, days per person, flat – and a function without price costs 0 with a hint."""
        anna = make_person("Anna Becker")
        daily = job_function("Bühnenmeister")
        product = daily.service_product
        product.price, product.billing_mode = D("400.00"), BillingMode.DAILY_PER_PIECE
        product.save()
        flat = job_function("Anfahrt")
        product = flat.service_product
        product.price, product.billing_mode = D("80.00"), BillingMode.FLAT
        product.save()
        unpriced = job_function("Helfer")
        product = unpriced.service_product
        product.price = None
        product.save()
        for person in (self.tom, anna):
            self.work(self.spot, at(3, 9), at(3, 12), function=daily, person=person)
        self.work(self.spot, at(4, 9), at(4, 10), function=daily)
        self.work(self.spot, at(3, 13), at(3, 14), function=flat)
        self.work(self.spot, at(5, 13), at(5, 14), function=flat)
        self.work(self.spot, at(6, 9), at(6, 11), function=unpriced)
        positions = {item["title"]: item for item in statements.collect(MARCH)[0].positions}
        self.assertEqual(
            (positions["Bühnenmeister"]["quantity"], positions["Bühnenmeister"]["unit_code"]), ("3", "DAY")
        )
        self.assertEqual(statements.amount_of(positions["Bühnenmeister"]), D("1200.00"))
        self.assertEqual(statements.amount_of(positions["Anfahrt"]), D("80.00"))
        self.assertEqual(statements.amount_of(positions["Helfer"]), D("0.00"))
        self.assertIn("keinen Preis", positions["Helfer"]["hint"])

    def test_hours_beyond_the_limit_of_a_day(self) -> None:
        """PER-035: the 11th and 12th hour of a day at the price from the limit."""
        product = self.sound.service_product
        product.hours_limit, product.price_above_limit = D("10"), D("70.00")
        product.save()
        self.work(self.spot, at(3, 8), at(3, 20))  # 12 h
        self.work(self.spot, at(4, 8), at(4, 12))  # 4 h
        positions = statements.collect(MARCH)[0].positions
        self.assertEqual(
            [(item["source"], item["quantity"]) for item in positions], [("time", "14"), ("time_above", "2")]
        )
        self.assertEqual(statements.amount_of(positions[1]), D("140.00"))
        self.assertIn("ab 10 Std. am Tag", positions[1]["title"])

    def test_surcharges_for_night_work(self) -> None:
        """PER-009: with the surcharges on the price, the night hours as the crew lines get them."""
        from rentalars.core.models import TimeSurchargeSettings

        settings = TimeSurchargeSettings.load()
        settings.on_price = True
        settings.save()
        self.work(self.spot, at(3, 20), at(3, 23))
        positions = statements.collect(MARCH)[0].positions
        surcharge = next(item for item in positions if item["source"] == "surcharge")
        self.assertTrue(surcharge["title"].startswith("Zuschläge Tontechnik"))
        self.assertGreater(statements.amount_of(surcharge), D("0"))

    def test_expenses(self) -> None:
        """ZEI-019: each approved expense; a trip with the own car by its kilometres."""
        self.spend(self.spot, datetime.date(2027, 3, 3), "12.50", note="Parkhaus Markt")
        self.spend(
            self.spot,
            datetime.date(2027, 3, 4),
            "12.60",
            kind=ExpenseKind.TRAVEL,
            kilometres=D("42"),
            km_rate=D("0.30"),
        )
        self.spend(self.spot, datetime.date(2027, 3, 5), "99.00", status=TimeEntryStatus.SUBMITTED)
        found = statements.collect(MARCH)
        self.assertEqual([item.case for item in found], [self.spot])
        positions = found[0].positions
        self.assertEqual(
            [(item["title"], item["quantity"], item["unit"], statements.amount_of(item)) for item in positions],
            [("Spesen: Parken/Maut", "1", "pauschal", D("12.50")), ("Spesen: Fahrt", "42", "km", D("12.60"))],
        )
        self.assertIn("Parkhaus Markt", positions[0]["details"])

    def test_a_case_over_several_months_is_billed_month_by_month(self) -> None:
        self.work(self.spot, at(20, 9, month=2), at(20, 11, month=2))
        february = self.statement(FEBRUARY)
        invoices_in_rentalars(False)  # marking is for invoices written elsewhere (DOK-014)
        statements.mark(february, user=self.paula)
        self.work(self.spot, at(3, 9), at(3, 10))
        march = self.statement()
        self.assertEqual([item["quantity"] for item in self.positions(march, self.spot)], ["1"])
        # Done in April: nothing left to bill – every time is in a statement.
        self.done(self.spot, at(2, 9, month=4))
        self.assertEqual(statements.collect(datetime.date(2027, 4, 1), customer=self.customer), [])


class ContentTests(StatementSetup, RentalarsTestCase):
    """The draft: activity, positions, free positions, totals, collecting again."""

    def setUp(self) -> None:
        super().setUp()
        self.work(self.spot, at(3, 9), at(3, 12), note="Leuchtmittel getauscht")
        self.work(self.mixer, at(4, 9), at(4, 10))
        self.draft = self.statement()

    def test_the_draft(self) -> None:
        self.assertEqual(self.draft.status, StatementStatus.DRAFT)
        self.assertEqual(set(self.draft.cases.all()), {self.spot, self.mixer})
        self.assertEqual(self.draft.content["introduction"], "Für die Servicefälle im März 2027 berechnen wir:")
        activity = statements.case_entry(self.draft, self.spot.pk)["activity"]
        # The title only when there is nothing else – the invoice names it above the activity.
        self.assertEqual(statements.case_entry(self.draft, self.mixer.pk)["activity"], "Mischpult brummt")
        self.assertEqual(activity, "Spot 3 über der Bühne flackert.\nLeuchtmittel getauscht")
        # "Entwurf anlegen" again opens the same draft.
        again, created = statements.create_statement(self.customer, MARCH, user=self.paula)
        self.assertEqual((again, created), (self.draft, False))
        # Nothing to bill: refused.
        with self.assertRaises(ValidationError):
            statements.create_statement(make_customer("Kino"), MARCH, user=self.paula)

    def test_activity_from_the_correspondence_of_the_month(self) -> None:
        """EML-051: notes and subjects of the mails of the month – for who may read the correspondence."""
        other = self.case("Bühnenlicht")
        self.work(other, at(5, 9), at(5, 10))
        ProjectMail.objects.create(
            project=other,
            direction=Direction.INCOMING,
            message_key="k1",
            message_id="<1@x>",
            subject="AW: Licht fällt aus",
            date=at(5, 8),
            text_body="…",
        )
        ProjectMail.objects.create(
            project=other,
            direction=Direction.NOTE,
            message_key="k2",
            message_id="",
            subject="Anruf Hausmeister",
            date=at(5, 12),
            text_body="Sicherung getauscht",
        )
        ProjectMail.objects.create(
            project=other,
            direction=Direction.INCOMING,
            message_key="k3",
            message_id="<3@x>",
            subject="Alte Mail",
            date=at(5, 8, month=2),
            text_body="…",
        )
        statements.refresh(self.draft, user=self.paula)
        activity = statements.case_entry(MonthlyStatement.objects.get(pk=self.draft.pk), other.pk)["activity"]
        self.assertIn("Notizen: 05.03. Anruf Hausmeister", activity)
        self.assertIn("Korrespondenz: Licht fällt aus", activity)
        self.assertNotIn("Alte Mail", activity)
        entries = statements.collect(MARCH, case_ids=[other.pk], statement=self.draft)[0].entries
        self.assertNotIn("Korrespondenz", statements.activity_proposal(other, MARCH, entries, correspondence=False))

    def test_change_positions_and_add_free_ones(self) -> None:
        reduced = TaxRate.objects.create(name="7 %", rate=D("7"))
        make_product("V-100", "Leuchtmittel 575 W", price=None, sale_price=D("38.00"), kind="sale", tax_rate=reduced)
        key = self.positions(self.draft, self.spot)[0]["key"]
        statements.update_statement(
            self.draft,
            {
                "introduction": "Im März:",
                "cases": [
                    {
                        "id": self.spot.pk,
                        "activity": "Spot repariert.",
                        "positions": [{"key": key, "quantity": "2.5", "unit_price": "48"}],
                        "add": [
                            {"article_number": "V-100", "quantity": "2"},
                            {"title": "Anfahrt", "quantity": "1", "unit": "psch", "unit_price": "25"},
                        ],
                    }
                ],
            },
            user=self.paula,
        )
        draft = MonthlyStatement.objects.get(pk=self.draft.pk)
        entry = statements.case_entry(draft, self.spot.pk)
        self.assertEqual((entry["activity"], entry["activity_source"]), ("Spot repariert.", "user"))
        time, lamp, trip = entry["positions"]
        self.assertTrue(time["edited"])
        self.assertEqual(statements.amount_of(time), D("120.00"))
        self.assertEqual((lamp["title"], lamp["unit_price"], lamp["tax_name"]), ("Leuchtmittel 575 W", "38", "7 %"))
        self.assertEqual(statements.amount_of(trip), D("25.00"))
        totals = statements.totals_of(draft.content)
        # 120 + 25 + mixer 50 at 19 %, 76 at 7 %: tax per rate, rounded once.
        self.assertEqual(totals.net, D("271.00"))
        self.assertEqual(
            [(share.percent, share.net, share.tax) for share in totals.taxes],
            [(D("19"), D("195.00"), D("37.05")), (D("7"), D("76.00"), D("5.32"))],
        )
        self.assertEqual(totals.gross, D("313.37"))
        # Wrong values are refused, naming the case.
        with self.assertRaisesMessage(ValidationError, self.spot.number):
            statements.update_statement(
                self.draft, {"cases": [{"id": self.spot.pk, "positions": [{"key": key, "quantity": "viel"}]}]}
            )
        with self.assertRaises(ValidationError):
            statements.update_statement(self.draft, {"cases": [{"id": self.spot.pk, "add": [{"title": "Ohne Preis"}]}]})

    def test_remove_and_restore_a_position_and_take_a_case_out(self) -> None:
        key = self.positions(self.draft, self.spot)[0]["key"]
        statements.update_statement(
            self.draft, {"cases": [{"id": self.spot.pk, "positions": [{"key": key, "removed": True}]}]}
        )
        draft = MonthlyStatement.objects.get(pk=self.draft.pk)
        self.assertEqual(statements.totals_of(draft.content).net, D("50.00"))
        statements.update_statement(
            draft, {"cases": [{"id": self.spot.pk, "positions": [{"key": key, "removed": False}]}]}
        )
        statements.update_statement(draft, {"cases": [{"id": self.mixer.pk, "remove": True}]})
        draft = MonthlyStatement.objects.get(pk=self.draft.pk)
        self.assertEqual(list(draft.cases.all()), [self.spot])
        self.assertEqual(statements.totals_of(draft.content).net, D("150.00"))
        # Taken out, the case is free for another statement – and collecting again does not bring it back.
        self.assertEqual([item.case for item in statements.collect(MARCH, customer=self.customer)], [self.mixer])
        statements.refresh(draft)
        self.assertEqual(list(MonthlyStatement.objects.get(pk=draft.pk).cases.all()), [self.spot])

    def test_a_removed_position_is_not_billed_later(self) -> None:
        """It was decided not to charge it: its times stay with the statement."""
        key = self.positions(self.draft, self.mixer)[0]["key"]
        statements.update_statement(
            self.draft, {"cases": [{"id": self.mixer.pk, "positions": [{"key": key, "removed": True}]}]}
        )
        invoices_in_rentalars(False)
        statements.mark(self.draft, user=self.paula)
        self.done(self.mixer, at(2, 9, month=4))
        found = statements.collect(datetime.date(2027, 4, 1), customer=self.customer)
        self.assertEqual(found, [])

    def test_collect_again(self) -> None:
        spot_key = self.positions(self.draft, self.spot)[0]["key"]
        mixer_key = self.positions(self.draft, self.mixer)[0]["key"]
        statements.update_statement(
            self.draft,
            {
                "cases": [
                    {
                        "id": self.spot.pk,
                        "activity": "Mein Text",
                        "positions": [{"key": spot_key, "unit_price": "45"}],
                        "add": [{"title": "Kabel", "unit_price": "9.90"}],
                    },
                    {"id": self.mixer.pk, "positions": [{"key": mixer_key, "unit_price": "40"}]},
                ]
            },
        )
        self.work(self.mixer, at(6, 9), at(6, 11))  # new times for the mixer
        third = self.case("Nebelmaschine")
        self.work(third, at(7, 9), at(7, 10))
        messages = statements.refresh(self.draft)
        self.assertIn(f"Hinzugekommen: {third.number}.", messages)
        draft = MonthlyStatement.objects.get(pk=self.draft.pk)
        spot = statements.case_entry(draft, self.spot.pk)
        self.assertEqual(spot["activity"], "Mein Text")
        self.assertEqual(
            [(item["title"], item["unit_price"]) for item in spot["positions"]],
            [("Tontechnik", "45"), ("Kabel", "9.9")],
        )
        mixer = statements.case_entry(draft, self.mixer.pk)["positions"][0]
        self.assertEqual((mixer["quantity"], mixer["unit_price"]), ("3", "50"))
        self.assertIn("neu berechnet", mixer["hint"])
        self.assertIn(third, draft.cases.all())

    def test_hints_of_times_not_approved(self) -> None:
        self.work(self.spot, at(9, 9), at(9, 10), approve=False)
        self.spend(self.spot, datetime.date(2027, 3, 9), "5.00", status=TimeEntryStatus.SUBMITTED)
        hints = statements.case_hints(self.draft)[self.spot.pk]
        self.assertEqual(len(hints), 2)
        self.assertIn("1 Zeit des Monats ist noch nicht freigegeben", hints[0])

    def test_delete_the_draft(self) -> None:
        statements.delete_statement(self.draft)
        self.assertFalse(MonthlyStatement.objects.exists())
        self.assertEqual(len(statements.collect(MARCH, customer=self.customer)), 2)


class InvoiceTests(StatementSetup, RentalarsTestCase):
    """ "Rentalars als Buchhaltungsprogramm verwenden" on: one invoice with a section per case; the cases count as invoiced."""

    def setUp(self) -> None:
        super().setUp()
        invoices_in_rentalars(True)
        remind_of_cases()
        self.work(self.spot, at(3, 9), at(3, 12))
        self.work(self.mixer, at(4, 9), at(4, 10))
        self.spot, self.mixer = self.done(self.spot), self.done(self.mixer)
        self.draft = self.statement()

    def test_the_invoice(self) -> None:
        self.assertEqual(invoice_reminders.state_of(self.mixer), InvoiceState.OPEN)
        self.assertIn(self.mixer, invoice_reminders.open_projects())
        document = statements.create_invoice(self.draft, user=self.paula)
        self.assertEqual((document.kind, document.project), (DocumentKind.INVOICE, self.spot))
        self.assertTrue(document.number.startswith("RE-"))
        self.assertEqual(set(document.billed_projects.all()), {self.spot, self.mixer})
        self.assertEqual((document.net_total, document.gross_total), (D("200.00"), D("238.00")))
        self.assertTrue(document.xml_file)
        sections = document.content["sections"]
        self.assertEqual(
            [section["title"] for section in sections],
            [f"Servicefall {self.spot.number} – Spot flackert", f"Servicefall {self.mixer.number} – Mischpult brummt"],
        )
        self.assertIn("Spot 3 über der Bühne flackert.", sections[0]["description"])
        self.assertEqual([position["number"] for section in sections for position in section["positions"]], ["1", "2"])
        self.assertEqual(document.content["project"]["number"], f"{self.spot.number}, {self.mixer.number}")
        draft = MonthlyStatement.objects.get(pk=self.draft.pk)
        self.assertEqual((draft.status, draft.invoice), (StatementStatus.INVOICED, document))
        # DOK-015: both cases count as invoiced – the state, the open ones, the column, the dashboard.
        for case in (self.spot, self.mixer):
            self.assertEqual(invoice_reminders.state_of(case), InvoiceState.INVOICED)
        self.assertNotIn(self.mixer, invoice_reminders.open_projects())
        numbers = dict(
            invoice_reminders.with_invoice_numbers(Project.objects.filter(pk=self.mixer.pk)).values_list(
                "pk", "invoice_number"
            )
        )
        self.assertEqual(numbers[self.mixer.pk], document.number)
        self.assertEqual(invoice_reminders.invoiced_ids([self.spot.pk, self.mixer.pk]), {self.spot.pk, self.mixer.pk})
        # A second invoice of a billed case is refused.
        self.assertTrue(check_can_make(self.mixer, DocumentKind.INVOICE))
        # Not a draft any more: no second invoice, no change.
        with self.assertRaises(ValidationError):
            statements.create_invoice(draft)
        with self.assertRaises(ValidationError):
            statements.update_statement(draft, {"introduction": "x"})

    def test_cancelled_the_statement_is_a_draft_and_the_cases_open(self) -> None:
        document = statements.create_invoice(self.draft, user=self.paula)
        cancellation = cancel_invoice(document, user=self.paula)
        draft = MonthlyStatement.objects.get(pk=self.draft.pk)
        self.assertEqual((draft.status, draft.invoice), (StatementStatus.DRAFT, None))
        self.assertEqual(draft.content["cancelled_invoices"][0]["cancellation"], cancellation.number)
        self.assertEqual(invoice_reminders.state_of(self.mixer), InvoiceState.OPEN)
        self.assertIn(self.mixer, invoice_reminders.open_projects())
        again = statements.create_invoice(draft, user=self.paula)
        self.assertNotEqual(again.number, document.number)

    def test_refused(self) -> None:
        # A case invoiced on its own in the meantime.
        Document.objects.create(
            project=self.mixer,
            kind=DocumentKind.INVOICE,
            number="RE-9",
            title="Rechnung",
            issued_on=MARCH,
            file="documents/x.pdf",
            sha256="0" * 64,
        )
        with self.assertRaisesMessage(ValidationError, self.mixer.number):
            statements.create_invoice(self.draft)
        # Invoices written elsewhere (DOK-014): no invoice, no draft PDF.
        invoices_in_rentalars(False)
        with self.assertRaises(ValidationError):
            statements.create_invoice(self.draft)
        with self.assertRaises(ValidationError):
            statements.preview(self.draft)

    def test_preview(self) -> None:
        self.assertTrue(statements.preview(self.draft).startswith(b"%PDF"))
        self.assertFalse(Document.objects.exists())


class MarkTests(StatementSetup, RentalarsTestCase):
    """ "Rentalars als Buchhaltungsprogramm verwenden" off: "Als abgerechnet markieren" ticks "Rechnung gestellt"."""

    def setUp(self) -> None:
        super().setUp()
        invoices_in_rentalars(False)
        remind_of_cases()
        self.work(self.spot, at(3, 9), at(3, 12))
        self.work(self.mixer, at(4, 9), at(4, 10))
        self.spot, self.mixer = self.done(self.spot), self.done(self.mixer)

    def test_mark_and_take_back(self) -> None:
        self.mixer.invoice_status = InvoiceMark.ISSUED  # ticked by hand before – stays ticked
        self.mixer.save()
        draft = statements.create_statement(self.customer, MARCH, user=self.paula)[0]
        self.assertEqual(list(draft.cases.all()), [self.spot])
        statements.update_statement(draft, {"cases": []})
        marked = statements.mark(draft, user=self.paula)
        self.assertEqual((marked.status, marked.marked_by), (StatementStatus.MARKED, self.paula))
        self.assertEqual(Project.objects.get(pk=self.spot.pk).invoice_status, InvoiceMark.ISSUED)
        self.assertEqual(invoice_reminders.state_of(Project.objects.get(pk=self.spot.pk)), InvoiceState.INVOICED)
        with self.assertRaises(ValidationError):
            statements.mark(marked)
        statements.unmark(marked, user=self.paula)
        self.assertEqual(Project.objects.get(pk=self.spot.pk).invoice_status, InvoiceMark.OPEN)
        self.assertEqual(Project.objects.get(pk=self.mixer.pk).invoice_status, InvoiceMark.ISSUED)
        self.assertEqual(MonthlyStatement.objects.get(pk=draft.pk).status, StatementStatus.DRAFT)

    def test_rights(self) -> None:
        """Without the price right nothing (AUT-019); without edit access to a case no change (AUT-016)."""
        from rentalars.accounts.rights import rights_of

        draft = self.statement()
        storeman = make_user("luka", roles=("Lager",))
        self.assertFalse(statements.may_use(rights_of(storeman)))
        reader = make_user("rita", roles=("Nur-Lesen",))
        self.assertTrue(statements.may_use(rights_of(reader)))
        self.assertFalse(statements.may_change(rights_of(reader)))
        statements.check_cases(draft.cases.all(), rights=rights_of(reader), user=reader)
        with self.assertRaises(PermissionDenied):
            statements.check_cases(draft.cases.all(), rights=rights_of(reader), user=reader, edit=True)


class PageTests(StatementSetup, UiTestCase):
    """Buchhaltung → Monatsabrechnung (under Projekte) and the page of a statement."""

    def setUp(self) -> None:
        super().setUp()
        invoices_in_rentalars(True)
        self.work(self.spot, at(3, 9), at(3, 12))
        self.work(self.mixer, at(4, 9), at(4, 10))
        self.overview = reverse("documents:statements")

    def test_overview_and_draft(self) -> None:
        # Buchhaltung: the tab moved from "Projekte" to "Buchhaltung" (tests/unit/test_091_accounting.py).
        page = self.assert_ok(self.client.get(reverse("documents:outgoing")))
        self.assertIn(f'<a href="{self.overview}">Monatsabrechnung</a>', page)
        self.assertNotIn("Monatsabrechnung", self.assert_ok(self.client.get(reverse("projects:cases"))))
        page = self.assert_ok(self.client.get(self.overview, {"month": "2027-03"}))
        self.assertIn("Monatsabrechnung März 2027", page)
        self.assertIn("Theater am Markt", page)
        self.assertIn(self.spot.number, page)
        self.assertIn("200,00 €", page)
        self.assertIn("Entwurf anlegen", page)
        # The previous month first.
        self.assertIn("Monatsabrechnung Februar 2027", self.assert_ok(self.client.get(self.overview)))
        response = self.client.post(
            reverse("documents:statement_create"), {"customer": self.customer.pk, "month": "2027-03"}
        )
        draft = MonthlyStatement.objects.get()
        self.assertRedirects(response, reverse("documents:statement", args=[draft.pk]))
        page = self.assert_ok(self.client.get(reverse("documents:statement", args=[draft.pk])))
        for text in (
            "Tätigkeit",
            "Spot 3 über der Bühne flackert.",
            "Rechnung erstellen",
            "Entwurf als PDF",
            "Summe brutto",
            "Neu einsammeln",
        ):
            self.assertIn(text, page)
        self.assertIn("Entwurf öffnen", self.assert_ok(self.client.get(self.overview, {"month": "2027-03"})))

    def test_edit_on_the_page(self) -> None:
        draft = self.statement()
        url = reverse("documents:statement", args=[draft.pk])
        key = self.positions(draft, self.spot)[0]["key"]
        page = self.client.get(url)
        data = form_data(
            page,
            f"activity-{self.spot.pk}",
            **{
                f"activity-{self.spot.pk}": "Spot repariert",
                f"pos-{self.spot.pk}-{key}-quantity": "2,5",
                f"new-{self.spot.pk}-title": "Leuchtmittel",
                f"new-{self.spot.pk}-unit_price": "38,00",
                "action": f"add:{self.spot.pk}",
            },
        )
        self.assertRedirects(self.client.post(url, data), f"{url}#case-{self.spot.pk}", fetch_redirect_response=False)
        draft = MonthlyStatement.objects.get(pk=draft.pk)
        entry = statements.case_entry(draft, self.spot.pk)
        self.assertEqual(entry["activity"], "Spot repariert")
        self.assertEqual(
            [(item["title"], statements.amount_of(item)) for item in entry["positions"]],
            [("Tontechnik", D("125.00")), ("Leuchtmittel", D("38.00"))],
        )
        page = self.assert_ok(self.client.get(url))
        self.assertIn("213,00 €", page)  # 125 + 38 + 50
        # Remove a position, take it back in, take a case out.
        self.client.post(
            url, form_data(self.client.get(url), f"activity-{self.spot.pk}", action=f"remove:{self.spot.pk}:{key}")
        )
        self.assertTrue(
            statements.case_entry(MonthlyStatement.objects.get(pk=draft.pk), self.spot.pk)["positions"][0]["removed"]
        )
        page = self.assert_ok(self.client.get(url))
        self.assertIn("1 Position entfernt – nicht berechnet", page)
        self.client.post(
            url, form_data(self.client.get(url), f"activity-{self.spot.pk}", action=f"restore:{self.spot.pk}:{key}")
        )
        self.assertFalse(
            statements.case_entry(MonthlyStatement.objects.get(pk=draft.pk), self.spot.pk)["positions"][0]["removed"]
        )
        self.client.post(
            url, form_data(self.client.get(url), f"activity-{self.spot.pk}", action=f"remove_case:{self.mixer.pk}")
        )
        self.assertEqual(list(MonthlyStatement.objects.get(pk=draft.pk).cases.all()), [self.spot])
        # A wrong number is said, nothing is saved.
        response = self.client.post(
            url,
            form_data(
                self.client.get(url),
                f"activity-{self.spot.pk}",
                **{f"pos-{self.spot.pk}-{key}-quantity": "viel", "action": "save"},
            ),
            follow=True,
        )
        self.assertIn("„viel“ ist keine Zahl.", " ".join(self.messages_of(response)))
        # Collect again.
        response = self.client.post(
            url, form_data(self.client.get(url), f"activity-{self.spot.pk}", action="refresh"), follow=True
        )
        self.assertIn("Nichts Neues einzusammeln.", self.messages_of(response))

    def test_preview_and_invoice(self) -> None:
        draft = self.statement()
        url = reverse("documents:statement", args=[draft.pk])
        response = self.client.post(url, form_data(self.client.get(url), f"activity-{self.spot.pk}", action="preview"))
        self.assertEqual(response["Content-Type"], "application/pdf")
        response = self.client.post(
            url, form_data(self.client.get(url), f"activity-{self.spot.pk}", action="invoice"), follow=True
        )
        document = Document.objects.get(kind=DocumentKind.INVOICE)
        self.assertIn(f"Rechnung {document.number} erstellt.", " ".join(self.messages_of(response)))
        page = self.assert_ok(self.client.get(url))
        self.assertIn(f"Rechnung {document.number} vom", page)
        self.assertNotIn("Rechnung erstellen", page)
        # The cases say so; the documents of the second case list the monthly invoice.
        case_page = self.assert_ok(self.client.get(reverse("projects:case_detail", args=[self.mixer.pk])))
        self.assertIn(f"Abgerechnet mit der Monatsrechnung {document.number} (März 2027)", case_page)
        documents = self.assert_ok(self.client.get(reverse("documents:list", args=[self.mixer.pk])))
        self.assertIn(document.number, documents)
        self.assertIn(f"Monatsrechnung der Servicefälle, gehört zu {self.spot.number}", documents)

    def test_copy_view_and_mark_when_invoices_are_written_elsewhere(self) -> None:
        invoices_in_rentalars(False)
        draft = self.statement()
        url = reverse("documents:statement", args=[draft.pk])
        page = self.assert_ok(self.client.get(url))
        self.assertIn("Zum Übertragen in dein Rechnungsprogramm", page)
        self.assertIn('<span class="copy" data-copy="150,00">', page)
        self.assertIn('<span class="copy" data-copy="Tontechnik">', page)
        self.assertIn("data-copy-block=", page)
        self.assertIn("Als abgerechnet markieren", page)
        self.assertNotIn("Rechnung erstellen", page)
        self.client.post(url, form_data(self.client.get(url), f"activity-{self.spot.pk}", action="mark"))
        self.assertEqual(MonthlyStatement.objects.get(pk=draft.pk).status, StatementStatus.MARKED)
        self.assertEqual(Project.objects.get(pk=self.spot.pk).invoice_status, InvoiceMark.ISSUED)
        page = self.assert_ok(self.client.get(url))
        self.assertIn("Markierung zurücknehmen", page)
        case_page = self.assert_ok(self.client.get(reverse("projects:case_detail", args=[self.spot.pk])))
        self.assertIn("Als abgerechnet markiert mit der Monatsabrechnung März 2027", case_page)
        self.client.post(url, {"action": "unmark"})
        self.assertEqual(MonthlyStatement.objects.get(pk=draft.pk).status, StatementStatus.DRAFT)
        self.assertEqual(Project.objects.get(pk=self.spot.pk).invoice_status, InvoiceMark.OPEN)

    def test_delete_the_draft(self) -> None:
        draft = self.statement()
        response = self.client.post(reverse("documents:statement_delete", args=[draft.pk]))
        self.assertRedirects(response, f"{self.overview}?month=2027-03", fetch_redirect_response=False)
        self.assertFalse(MonthlyStatement.objects.exists())

    def test_the_start_page_forgets_the_invoiced_cases(self) -> None:
        """DOK-015: "Noch zu schreibende Rechnungen" – a case billed by the monthly invoice is no longer in it."""
        remind_of_cases()
        self.done(self.mixer)
        home = self.client.get(reverse("core:home"))
        self.assertIn(self.mixer, home.context["open_invoices"])
        statements.create_invoice(self.statement(), user=self.admin_user)
        home = self.client.get(reverse("core:home"))
        self.assertNotIn(self.mixer, home.context.get("open_invoices") or [])

    def test_times_without_a_project_are_named(self) -> None:
        """Idea 5: times in no case stay out – the overview names them to who can assign them (ZEI-023)."""
        record_time(self.tom, None, self.sound, at(9, 9), at(9, 10))
        page = self.assert_ok(self.client.get(self.overview, {"month": "2027-03"}))
        self.assertIn("1 Zeit dieses Monats hat noch kein Projekt", page)
        self.assertIn('<td class="num" data-label="Stunden">4</td>', page)  # 3 + 1 h of the cases, not the 1 h without

    def test_rights(self) -> None:
        draft = self.statement()
        url = reverse("documents:statement", args=[draft.pk])
        storeman = self.browser_for("luka", "Lager")  # no price right
        for address in (self.overview, url):
            self.assertEqual(storeman.get(address).status_code, 403)
        self.assertNotIn("Monatsabrechnung", self.assert_ok(storeman.get(reverse("projects:cases"))))
        reader = self.browser_for("rita", "Nur-Lesen")  # prices, but no writing
        page = self.assert_ok(reader.get(url))
        self.assertNotIn("Rechnung erstellen", page)
        self.assertNotIn(f'name="activity-{self.spot.pk}"', page)
        self.assertEqual(reader.post(url, {"action": "save"}).status_code, 403)
        self.assertEqual(
            reader.post(reverse("documents:statement_create"), {"customer": self.customer.pk}).status_code, 403
        )
        self.assertEqual(reader.post(reverse("documents:statement_delete", args=[draft.pk])).status_code, 403)


class AiTests(StatementSetup, UiTestCase):
    """EML-040: "Mit lokaler KI zusammenfassen" – only with the local AI, always editable afterwards."""

    def setUp(self) -> None:
        super().setUp()
        from rentalars.ai.models import AISettings, Source
        from tests.ai_fake import FakeModelServer, write_local_file

        self.work(self.spot, at(3, 9), at(3, 12), note="Leuchtmittel getauscht")
        self.draft = self.statement()
        self.url = reverse("documents:statement", args=[self.draft.pk])
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        local_file = folder / "ai-local.conf"
        settings_override = override_settings(RENTALARS_AI_LOCAL_FILE=str(local_file))
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        self.fake = FakeModelServer(answer="Das flackernde Scheinwerferlicht wurde repariert.").__enter__()
        self.addCleanup(self.fake.__exit__)
        write_local_file(local_file, self.fake.url)
        ai_settings = AISettings.load()
        ai_settings.summary_source = Source.LOCAL
        ai_settings.save()

    def test_summarise_with_the_local_ai(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn("Mit lokaler KI zusammenfassen", page)
        data = form_data(self.client.get(self.url), f"activity-{self.spot.pk}", action=f"ai:{self.spot.pk}")
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        entry = statements.case_entry(MonthlyStatement.objects.get(pk=self.draft.pk), self.spot.pk)
        self.assertEqual(
            (entry["activity"], entry["activity_source"]), ("Das flackernde Scheinwerferlicht wurde repariert.", "ai")
        )
        prompt = self.fake.chats[-1]["messages"][-1]["content"]
        self.assertIn("Leuchtmittel getauscht", prompt)
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn("von KI", page)
        # The job page of the starter says it is done.
        from rentalars.core.models import BackgroundJob

        job = BackgroundJob.objects.get(kind=statements.JOB_KIND)
        response = self.htmx("get", reverse("documents:statement_job", args=[self.draft.pk, job.pk]))
        self.assertEqual(response.status_code, 204)
        self.assertIn(f"#case-{self.spot.pk}", response["HX-Redirect"])

    def test_not_without_the_right_to_read_the_correspondence(self) -> None:
        from rentalars.accounts.models import Role

        role = Role.objects.create(
            name="Abrechnung", module_levels={"projects": 2, "customers": 1}, special_rights=["prices"]
        )
        user = make_user("bea")
        user.roles.set([role])
        browser = self.browser_of(user)
        self.assertNotIn("Mit lokaler KI zusammenfassen", self.assert_ok(browser.get(self.url)))
        self.assertEqual(browser.post(self.url, {"action": f"ai:{self.spot.pk}"}).status_code, 403)


class StatementApiTests(StatementSetup, ApiTestCase):
    """API-014: every operation of /service-statements."""

    def setUp(self) -> None:
        super().setUp()
        self.work(self.spot, at(3, 9), at(3, 12))
        self.work(self.mixer, at(4, 9), at(4, 10))

    def test_all_operations(self) -> None:
        invoices_in_rentalars(True)
        # DOK-015: "Auch Servicefälle" is on by default; this test switches it on further down to show the difference.
        NotificationSettings.objects.filter(pk=1).update(invoice_service_cases=False)
        response = self.admin.get(f"{API}/service-statements", {"month": "2027-03"})
        self.assertEqual(response.status_code, 200, response.content)
        row = response.json()["customers"][0]
        self.assertEqual(
            (row["customer"], row["net_total"], [case["number"] for case in row["billable_cases"]]),
            (self.customer.pk, "200.00", [self.spot.number, self.mixer.number]),
        )
        response = self.admin.post(
            f"{API}/service-statements", {"customer": self.customer.pk, "month": "2027-03"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        statement = response.json()
        self.assertEqual(
            (statement["status"], statement["net_total"], statement["gross_total"]), ("draft", "200.00", "238.00")
        )
        again = self.admin.post(
            f"{API}/service-statements", {"customer": self.customer.pk, "month": "2027-03"}, format="json"
        )
        self.assertEqual((again.status_code, again.json()["id"]), (200, statement["id"]))
        address = f"{API}/service-statements/{statement['id']}"
        self.assertEqual(self.admin.get(address).json()["cases"][0]["number"], self.spot.number)
        key = statement["cases"][0]["positions"][0]["key"]
        response = self.admin.patch(
            address,
            {
                "cases": [
                    {
                        "id": self.spot.pk,
                        "activity": "Spot repariert",
                        "positions": [{"key": key, "quantity": "2"}],
                        "add": [{"title": "Kabel", "unit_price": "10"}],
                    }
                ],
                "refresh": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        case = response.json()["cases"][0]
        self.assertEqual((case["activity"], case["net_total"]), ("Spot repariert", "110.00"))
        response = self.admin.patch(
            address, {"cases": [{"id": self.spot.pk, "positions": [{"key": key, "quantity": "x"}]}]}, format="json"
        )
        self.assert_error(response, 400, "validation_error")
        response = self.admin.post(f"{address}/invoice", format="json")
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["statement"]["status"], "invoiced")
        self.assertEqual(set(body["invoice"]["billed_projects"]), {self.spot.pk, self.mixer.pk})
        self.assertEqual(
            self.admin.get(f"{API}/projects/{self.mixer.pk}").json()["invoice_state"], None
        )  # not followed
        remind_of_cases()
        self.done(self.mixer)
        self.assertEqual(self.admin.get(f"{API}/projects/{self.mixer.pk}").json()["invoice_state"], "invoiced")
        self.assert_error(self.admin.delete(address), 400, "validation_error")

    def test_mark_and_delete(self) -> None:
        invoices_in_rentalars(False)
        statement = self.admin.post(
            f"{API}/service-statements", {"customer": self.customer.pk, "month": "2027-03"}, format="json"
        ).json()
        address = f"{API}/service-statements/{statement['id']}"
        self.assert_error(self.admin.post(f"{address}/invoice", format="json"), 400, "validation_error")
        response = self.admin.post(f"{address}/mark", {}, format="json")
        self.assertEqual((response.status_code, response.json()["status"]), (200, "marked"))
        self.assertEqual(Project.objects.get(pk=self.spot.pk).invoice_status, InvoiceMark.ISSUED)
        response = self.admin.post(f"{address}/mark", {"marked": False}, format="json")
        self.assertEqual((response.status_code, response.json()["status"]), (200, "draft"))
        self.assertEqual(self.admin.delete(address).status_code, 204)
        self.assertFalse(MonthlyStatement.objects.exists())

    def test_rights(self) -> None:
        statement = self.statement()
        storeman = self.client_for("luka", "Lager")
        self.assertEqual(storeman.get(f"{API}/service-statements").status_code, 403)
        self.assertEqual(storeman.get(f"{API}/service-statements/{statement.pk}").status_code, 403)
        reader = self.client_for("rita", "Nur-Lesen")
        self.assertEqual(reader.get(f"{API}/service-statements/{statement.pk}").status_code, 200)
        self.assertEqual(
            reader.patch(f"{API}/service-statements/{statement.pk}", {"introduction": "x"}, format="json").status_code,
            403,
        )
        self.assertEqual(
            reader.post(f"{API}/service-statements/{statement.pk}/mark", {}, format="json").status_code, 403
        )


# --- Review: the findings, each kept by a test ------------------------------------------------------


def limited_role(**levels: int) -> str:
    """A role for assigned projects only that may see prices – the "Extern" case of the review."""
    from rentalars.accounts.models import Role
    from rentalars.accounts.rights import ProjectScope, SpecialRight

    Role.objects.create(
        name="Extern",
        module_levels={"projects": 2, **levels},
        special_rights=[SpecialRight.PRICES],
        project_scope=ProjectScope.ASSIGNED,
    )
    return "Extern"


def take_back_and_correct(entry: object, **changes: object) -> None:
    """Unlock an approved time, correct it and approve it again (ZEI-012)."""
    from rentalars.timetracking import services as time_services
    from tests.helpers import ALL_RIGHTS, clock_at_least

    time_services.take_back_approval(entry, rights=ALL_RIGHTS, user=None)
    entry.refresh_from_db()  # type: ignore[attr-defined]
    with clock_at_least(at(31, 23)):
        time_services.update_entry(entry, rights=ALL_RIGHTS, user=None, **changes)
    entry.refresh_from_db()  # type: ignore[attr-defined]
    time_services.approve_entries([entry], rights=ALL_RIGHTS, user=None)


class ReviewBillingTests(StatementSetup, RentalarsTestCase):
    """Each time and expense is billed once – month by month, also when it is corrected or moved."""

    def test_a_running_case_gets_a_monthly_invoice_every_month(self) -> None:
        """Finding 1: an earlier monthly invoice does not stop the next month's."""
        invoices_in_rentalars(True)
        self.work(self.spot, at(20, 9, month=2), at(20, 11, month=2))
        february = self.statement(FEBRUARY)
        first = statements.create_invoice(february, user=self.paula)
        self.work(self.spot, at(3, 9), at(3, 10))
        march = self.statement()
        self.assertIn(self.spot, march.cases.all())
        # February cancelled while March is a draft: the case stands in both, with different times (finding 8).
        cancel_invoice(first, user=self.paula)
        self.assertEqual(MonthlyStatement.objects.filter(status=StatementStatus.DRAFT, cases=self.spot).count(), 2)
        second = statements.create_invoice(march, user=self.paula)
        self.assertEqual(second.net_total, D("50.00"))
        again = statements.create_invoice(MonthlyStatement.objects.get(pk=february.pk), user=self.paula)
        self.assertEqual(again.net_total, D("100.00"))
        entries = [claim.time_entry_id for claim in statements.StatementClaim.objects.all()]
        self.assertEqual(len(entries), len(set(entries)), "no time is billed twice")

    def test_a_removed_position_does_not_swallow_later_times(self) -> None:
        """Finding 2: the hour given away stays away; the eight hours of later work are billed."""
        self.work(self.spot, at(3, 9), at(3, 10))
        draft = self.statement()
        key = self.positions(draft, self.spot)[0]["key"]
        statements.update_statement(
            draft, {"cases": [{"id": self.spot.pk, "positions": [{"key": key, "removed": True}]}]}
        )
        self.work(self.spot, at(20, 9), at(20, 17))
        statements.refresh(draft)
        draft = MonthlyStatement.objects.get(pk=draft.pk)
        self.assertEqual(statements.totals_of(draft.content).net, D("400.00"))
        positions = self.positions(draft, self.spot)
        self.assertEqual(sorted((item["quantity"], item["removed"]) for item in positions), [("1", True), ("8", False)])
        self.assertEqual(len({item["key"] for item in positions}), 2)
        # Taken back in: both times billed – collecting again makes one position of them.
        removed = next(item for item in positions if item["removed"])
        statements.update_statement(
            draft, {"cases": [{"id": self.spot.pk, "positions": [{"key": removed["key"], "removed": False}]}]}
        )
        statements.refresh(draft)
        positions = self.positions(draft, self.spot)
        self.assertEqual([(item["quantity"], item["removed"]) for item in positions], [("9", False)])

    def test_removing_the_hours_removes_their_surcharges_too(self) -> None:
        product = self.sound.service_product
        product.hours_limit, product.price_above_limit = D("10"), D("70.00")
        product.save()
        self.work(self.spot, at(3, 8), at(3, 20))
        draft = self.statement()
        hours = next(item for item in self.positions(draft, self.spot) if item["source"] == "time")
        statements.update_statement(
            draft, {"cases": [{"id": self.spot.pk, "positions": [{"key": hours["key"], "removed": True}]}]}
        )
        self.assertTrue(all(item["removed"] for item in self.positions(draft, self.spot)))
        statements.refresh(draft)
        self.assertEqual(statements.totals_of(MonthlyStatement.objects.get(pk=draft.pk).content).net, D("0.00"))

    def test_a_billed_time_cannot_be_unlocked_and_a_moved_one_is_not_billed_twice(self) -> None:
        """Finding 3: the claim follows the time, whatever case it belongs to; the approval stays once billed."""
        invoices_in_rentalars(True)
        entry = self.work(self.spot, at(3, 9), at(3, 12))
        draft = self.statement()
        # While a draft: correct and move it – the draft still bills it, nobody else.
        take_back_and_correct(entry, project=self.mixer)
        self.assertEqual(statements.collect(MARCH, customer=self.customer), [])
        statements.refresh(draft)
        draft = MonthlyStatement.objects.get(pk=draft.pk)
        self.assertEqual([entry_["number"] for entry_ in draft.content["cases"]], [self.spot.number, self.mixer.number])
        self.assertEqual(statements.StatementClaim.objects.filter(time_entry=entry).count(), 1)
        self.assertEqual(statements.totals_of(draft.content).net, D("150.00"))
        statements.update_statement(draft, {"cases": [{"id": self.spot.pk, "remove": True}]})
        statements.create_invoice(draft, user=self.paula)
        from rentalars.timetracking import services as time_services
        from tests.helpers import ALL_RIGHTS

        with self.assertRaisesMessage(ValidationError, "Storniere zuerst die Rechnung"):
            time_services.take_back_approval(entry, rights=ALL_RIGHTS, user=None)

    def test_a_billed_expense_cannot_be_unlocked(self) -> None:
        from rentalars.timetracking import expenses as expense_services
        from tests.helpers import ALL_RIGHTS

        invoices_in_rentalars(False)
        expense = self.spend(self.spot, datetime.date(2027, 3, 3), "12.50")
        position = statements.collect(MARCH)[0].positions[0]
        self.assertIn("als netto übernommen", position["hint"])
        statements.mark(self.statement(), user=self.paula)
        with self.assertRaisesMessage(ValidationError, "Nimm zuerst die Markierung zurück"):
            expense_services.take_back_approval(expense, rights=ALL_RIGHTS, user=None)

    def test_collecting_again_takes_corrected_hours(self) -> None:
        """Finding 4: the same time, corrected from 3 to 5 hours."""
        entry = self.work(self.spot, at(3, 9), at(3, 12))
        draft = self.statement()
        take_back_and_correct(entry, end=at(3, 14))
        self.assertEqual(statements.changed_cases(MonthlyStatement.objects.get(pk=draft.pk)), [self.spot.number])
        statements.refresh(draft)
        self.assertEqual(self.positions(draft, self.spot)[0]["quantity"], "5")
        self.assertEqual(statements.changed_cases(MonthlyStatement.objects.get(pk=draft.pk)), [])

    def test_invoice_and_mark_check_the_cases_again(self) -> None:
        """Finding 5: ticked by hand, "Keine Rechnung", another customer, new times – after the draft was made."""
        invoices_in_rentalars(True)
        self.work(self.spot, at(3, 9), at(3, 10))
        self.work(self.mixer, at(3, 11), at(3, 12))
        draft = self.statement()
        Project.objects.filter(pk=self.spot.pk).update(invoice_status=InvoiceMark.ISSUED)
        with self.assertRaisesMessage(ValidationError, self.spot.number):
            statements.create_invoice(draft, user=self.paula)
        Project.objects.filter(pk=self.spot.pk).update(invoice_status=InvoiceMark.OPEN, customer=make_customer("Kino"))
        Project.objects.filter(pk=self.mixer.pk).update(invoice_status=InvoiceMark.NOT_NEEDED)
        invoices_in_rentalars(False)
        with self.assertRaisesMessage(ValidationError, f"{self.spot.number}, {self.mixer.number}"):
            statements.mark(draft, user=self.paula)
        self.assertEqual(Project.objects.get(pk=self.spot.pk).invoice_status, InvoiceMark.OPEN)
        # Collecting again takes them out.
        messages = statements.refresh(draft)
        self.assertIn("Herausgenommen", messages[0])
        self.assertFalse(MonthlyStatement.objects.get(pk=draft.pk).cases.exists())

    def test_new_times_after_the_draft_stop_the_invoice_until_collected_again(self) -> None:
        invoices_in_rentalars(True)
        self.work(self.spot, at(3, 9), at(3, 10))
        draft = self.statement()
        self.work(self.spot, at(10, 9), at(10, 10))
        with self.assertRaisesMessage(ValidationError, "seit dem Einsammeln geändert"):
            statements.create_invoice(draft, user=self.paula)
        statements.refresh(draft)
        self.assertEqual(statements.create_invoice(draft, user=self.paula).net_total, D("100.00"))

    def test_a_position_without_tax_rate_stops_the_invoice(self) -> None:
        invoices_in_rentalars(True)
        self.work(self.spot, at(3, 9), at(3, 10))
        draft = self.statement()
        draft.content["cases"][0]["positions"][0].update(tax_rate=None, tax_name="", tax_percent="0")
        MonthlyStatement.objects.filter(pk=draft.pk).update(content=draft.content)
        with self.assertRaisesMessage(ValidationError, "Steuerart"):
            statements.create_invoice(draft, user=self.paula)

    def test_marking_only_with_invoices_written_elsewhere(self) -> None:
        """Finding 11: with invoices made in Rentalars the statement is invoiced, not marked."""
        invoices_in_rentalars(True)
        self.work(self.spot, at(3, 9), at(3, 10))
        with self.assertRaisesMessage(ValidationError, "Erstelle die Rechnung"):
            statements.mark(self.statement(), user=self.paula)

    def test_a_billed_case_cannot_be_deleted(self) -> None:
        from rentalars.projects.services import delete_project

        invoices_in_rentalars(True)
        self.work(self.spot, at(3, 9), at(3, 10))
        loose = self.done(self.case("Nur Material"))
        draft = self.statement()
        statements.update_statement(
            draft, {"cases": [{"id": loose.pk, "add": [{"title": "Kabel", "unit_price": "9"}]}]}
        )
        statements.create_invoice(draft, user=self.paula)
        with self.assertRaisesMessage(ValidationError, "Monatsabrechnung"):
            delete_project(loose)

    def test_the_overview_costs_the_same_queries_for_more_cases(self) -> None:
        """Finding 12: no query per case."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from tests.helpers import ALL_RIGHTS

        def queries() -> int:
            with CaptureQueriesContext(connection) as captured:
                statements.overview(MARCH, rights=ALL_RIGHTS, user=self.paula)
            return len(captured)

        for index in range(3):
            case = self.case(f"Fall {index}")
            self.work(case, at(3, 8 + index), at(3, 9 + index))
            self.spend(case, datetime.date(2027, 3, 3), "5.00")
        few = queries()
        for index in range(3, 15):
            case = self.case(f"Fall {index}")
            self.work(case, at(4 + index // 8, 8 + index % 8), at(4 + index // 8, 9 + index % 8))
            self.spend(case, datetime.date(2027, 3, 3), "5.00")
        self.assertLessEqual(queries(), few)

    def test_anonymising_the_customer(self) -> None:
        """Finding 10: drafts go, the others lose their texts, the change log forgets the name."""
        from django.contrib.contenttypes.models import ContentType

        from rentalars.core.models import AuditLogEntry
        from rentalars.customers.services import anonymise_customer

        invoices_in_rentalars(False)
        self.work(self.spot, at(20, 9, month=2), at(20, 10, month=2), note="Frau Erika Mustermann angerufen")
        self.work(self.spot, at(3, 9), at(3, 10))
        february = self.statement(FEBRUARY)
        statements.mark(february, user=self.paula)
        self.statement()  # the draft of March
        anonymise_customer(self.customer)
        self.assertEqual(list(MonthlyStatement.objects.values_list("pk", flat=True)), [february.pk])
        entry = statements.case_entry(MonthlyStatement.objects.get(pk=february.pk), self.spot.pk)
        self.assertEqual(entry["activity"], "")
        self.assertTrue(all(position["details"] == "" for position in entry["positions"]))
        statement_type = ContentType.objects.get_for_model(MonthlyStatement)
        logged = AuditLogEntry.objects.filter(content_type=statement_type).values_list("object_repr", flat=True)
        self.assertTrue(logged)
        self.assertFalse([text for text in logged if "Theater" in text])


class ReviewAccessTests(StatementSetup, UiTestCase):
    """Findings 6, 7, 9 and the message of "Entwurf anlegen": nothing of a case the user may not see."""

    def setUp(self) -> None:
        super().setUp()
        self.work(self.spot, at(3, 9), at(3, 12))
        self.work(self.mixer, at(4, 9), at(4, 10))

    def test_the_monthly_invoice_needs_access_to_every_case(self) -> None:
        """Finding 7: access to the first case alone opens neither the PDF nor the cancellation."""
        from rentalars.projects.models import ProjectAccessLevel, ProjectMembership

        invoices_in_rentalars(True)
        # DOK-015: "Auch Servicefälle" is on by default; then the head of the case shows the state of its invoice –
        # "Rechnung gestellt" without the number of a monthly invoice the user may not open.
        invoice = statements.create_invoice(self.statement(), user=self.paula)
        user = make_user("erik", roles=(limited_role(),))
        ProjectMembership.objects.create(project=invoice.project, user=user, level=ProjectAccessLevel.EDIT)
        browser = self.browser_of(user)
        self.assertEqual(browser.get(reverse("documents:file", args=[invoice.pk])).status_code, 403)
        self.assertEqual(browser.post(reverse("documents:cancel", args=[invoice.pk])).status_code, 403)
        self.assertFalse(Document.objects.get(pk=invoice.pk).cancelled_by_id)
        page = self.assert_ok(browser.get(reverse("documents:list", args=[invoice.project.pk])))
        self.assertNotIn(invoice.number, page)
        # Who may read every case downloads it.
        self.assertEqual(self.client.get(reverse("documents:file", args=[invoice.pk])).status_code, 200)
        # Nor does it go along with a mail of the first case (EML-025).
        from rentalars.accounts.rights import rights_of
        from rentalars.mail.sending import document_choices

        offered = dict(document_choices(rights_of(user), invoice.project, user))
        self.assertNotIn(f"doc:{invoice.pk}", offered)
        self.assertIn(f"doc:{invoice.pk}", dict(document_choices(rights_of(self.paula), invoice.project, self.paula)))

    def test_make_draft_does_not_name_a_case_the_user_may_not_see(self) -> None:
        from rentalars.projects.models import ProjectAccessLevel, ProjectMembership

        user = make_user("erik", roles=(limited_role(customers=1),))
        ProjectMembership.objects.create(project=self.spot, user=user, level=ProjectAccessLevel.EDIT)
        browser = self.browser_of(user)
        response = browser.post(
            reverse("documents:statement_create"), {"customer": self.customer.pk, "month": "2027-03"}, follow=True
        )
        text = " ".join(self.messages_of(response))
        self.assertIn("1 Servicefall, den du nicht sehen darfst", text)
        self.assertNotIn(self.mixer.number, text)
        self.assertFalse(MonthlyStatement.objects.exists())

    def test_the_copy_block_makes_formulas_harmless(self) -> None:
        """Finding 9: CSV injection."""
        invoices_in_rentalars(False)
        draft = self.statement()
        statements.update_statement(
            draft,
            {"cases": [{"id": self.spot.pk, "add": [{"title": '=HYPERLINK("http://x","Kabel")', "unit_price": "1"}]}]},
        )
        text = self.client.get(reverse("documents:statement", args=[draft.pk])).context["copy_text"]
        line = next(row for row in text.splitlines() if "HYPERLINK" in row)
        self.assertIn("\t'=HYPERLINK", line)


class ReviewApiTests(StatementSetup, ApiTestCase):
    """Findings 6 and 11 through the API."""

    def test_an_existing_draft_only_for_who_may_read_all_its_cases(self) -> None:
        from rentalars.projects.models import ProjectAccessLevel, ProjectMembership

        self.work(self.spot, at(3, 9), at(3, 12), note="Tresor im Keller")
        self.work(self.mixer, at(4, 9), at(4, 10))
        draft = self.statement()
        user = make_user("erik", roles=(limited_role(customers=1),))
        ProjectMembership.objects.create(project=self.spot, user=user, level=ProjectAccessLevel.EDIT)
        client = self.client_of(user)
        self.assertEqual(client.get(f"{API}/service-statements/{draft.pk}").status_code, 403)
        response = client.post(
            f"{API}/service-statements", {"customer": self.customer.pk, "month": "2027-03"}, format="json"
        )
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("Tresor", response.content.decode())
        # The document of a monthly invoice the same way.
        invoices_in_rentalars(True)
        invoice = statements.create_invoice(draft, user=self.paula)
        self.assertEqual(client.get(f"{API}/documents/{invoice.pk}").status_code, 403)
        listed = client.get(f"{API}/projects/{invoice.project.pk}/documents").json()
        self.assertNotIn(invoice.number, [document["number"] for document in listed])

    def test_mark_is_refused_while_invoices_are_made_here(self) -> None:
        invoices_in_rentalars(True)
        self.work(self.spot, at(3, 9), at(3, 10))
        statement = self.statement()
        self.assert_error(
            self.admin.post(f"{API}/service-statements/{statement.pk}/mark", {}, format="json"), 400, "validation_error"
        )
