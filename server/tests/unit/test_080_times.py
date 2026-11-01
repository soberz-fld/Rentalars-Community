# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "times": hints at conspicuous time entries (ZEI-018), expenses and travel costs per project (ZEI-019).

The requirement: personnel – expenses, and hints for conspicuous times.

* ZEI-018: a long working day (more than 10 hours), a short break (more than 6 hours of work: 30 minutes, more than
  9 hours: 45 minutes) and a short rest (less than 11 hours) are pointed out – never blocking; the limits are
  settings.
* ZEI-019: expenses per project – meals, a trip by kilometre or with a ticket, a night, parking, other – with a photo
  of the receipt; approved like times, marked as reimbursed, part of the project's costs; a report per month and
  person.
"""

from __future__ import annotations

import datetime
import io
import tempfile
from decimal import Decimal as D  # noqa: N817
from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Rights
from rentalars.core.models import AuditLogEntry, SystemSettings
from rentalars.notifications.models import Kind, Notification
from rentalars.personnel.privacy import anonymise_person, export_person
from rentalars.projects.list_sums import attach_sums
from rentalars.projects.models import ProjectStatus
from rentalars.projects.pricing import compute_project_prices
from rentalars.timetracking import expenses
from rentalars.timetracking.hints import HintKind, HintLimits, hints_for, working_days
from rentalars.timetracking.models import Expense, ExpenseKind, TimeEntryStatus
from tests.helpers import (
    ALL_RIGHTS,
    LATER,
    RentalarsTestCase,
    at,
    job_function,
    make_internal_project,
    make_person,
    make_project,
    make_user,
    plan,
    record_time,
    set_clock,
)

PDF = b"%PDF-1.4\n1 0 obj << >> endobj\n%%EOF\n"


def picture(width: int = 3000, height: int = 2000, *, image_format: str = "JPEG", orientation: int = 0) -> bytes:
    """A photo as a phone takes it: large, with the name of the camera and – if given – the turn to show it upright."""
    from PIL import Image

    image = Image.new("RGB", (width, height), (200, 30, 30))
    exif = Image.Exif()
    exif[0x010F] = "Telefonhersteller"  # Make
    exif[0x0110] = "Modell 12"  # Model
    if orientation:
        exif[0x0112] = orientation
    stored = io.BytesIO()
    if image_format == "JPEG":
        image.save(stored, format="JPEG", exif=exif.tobytes())
    else:
        image.save(stored, format=image_format)
    return stored.getvalue()


def upload(name: str, content: bytes, content_type: str = "image/jpeg") -> SimpleUploadedFile:
    """An uploaded file, as the browser or the app sends it."""
    return SimpleUploadedFile(name, content, content_type=content_type)


class MediaMixin:
    """Receipts land in a folder of their own that is removed after the test."""

    def setUp(self) -> None:
        super().setUp()  # type: ignore[misc]
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)  # type: ignore[attr-defined]
        media = override_settings(MEDIA_ROOT=folder.name, SERVE_MEDIA_VIA_NGINX=False)
        media.enable()
        self.addCleanup(media.disable)  # type: ignore[attr-defined]
        self.media_root = folder.name


class TimesCase(RentalarsTestCase):
    """Anna, sound engineer, planned on the Stadtfest; the warehouse as an internal project. Late March 2027."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", start=at(10), end=at(12))
        self.sound = job_function("Tontechnik", price="45.00")
        self.anna_user = make_user("anna", roles=("Crew",))
        self.anna = make_person("Anna Becker", rates={"Tontechnik": "35.00"}, user=self.anna_user)
        plan(self.project, self.sound, self.anna, start=at(9, 6), end=at(12, 23))
        self.warehouse = make_internal_project("Lager")
        set_clock(LATER)

    def work(self, start: datetime.datetime, end: datetime.datetime, *, pause: int = 0, project=None, **more):
        """A time of Anna as sound engineer, handed in."""
        return record_time(
            self.anna, project or self.project, self.sound, start, end, break_minutes=pause, submit=True, **more
        )

    def kinds(self, entry) -> list[str]:
        return [hint.kind for hint in hints_for([entry]).get(entry.pk, [])]


# --- ZEI-018: hints at conspicuous time entries -------------------------------------------------------------------


class LongDayTests(TimesCase):
    """ZEI-018: more than 10 hours of work on one working day."""

    def test_more_than_ten_hours_is_pointed_out(self) -> None:
        """ZEI-018: 08:00–20:00 with 45 minutes of break is 11.25 hours."""
        entry = self.work(at(10, 8), at(10, 20), pause=45)
        hints = hints_for([entry])[entry.pk]
        self.assertEqual([hint.kind for hint in hints], [HintKind.LONG_DAY])
        self.assertEqual(hints[0].message, "Langer Arbeitstag: 11,25 Stunden Arbeit (mehr als 10).")

    def test_ten_hours_exactly_is_no_hint(self) -> None:
        """ZEI-018: "more than" 10 hours."""
        entry = self.work(at(10, 8), at(10, 18, 45), pause=45)
        self.assertEqual(self.kinds(entry), [])

    def test_a_morning_and_an_evening_are_one_working_day(self) -> None:
        """ZEI-018: load-in 06–12, show 18–23: one working day of 11 hours; the six hours between are a break."""
        load_in = self.work(at(10, 6), at(10, 12))
        show = self.work(at(10, 18), at(10, 23))
        self.assertEqual(self.kinds(load_in), [HintKind.LONG_DAY])
        self.assertEqual(self.kinds(show), [HintKind.LONG_DAY])

    def test_entries_of_other_projects_count_too(self) -> None:
        """ZEI-018: the working day of a person is one, whatever project the hours belong to."""
        self.work(at(10, 6), at(10, 11), project=self.warehouse)
        evening = self.work(at(10, 12), at(10, 18, 30), pause=30)
        self.assertIn(HintKind.LONG_DAY, self.kinds(evening))

    def test_the_limit_is_a_setting_and_0_switches_it_off(self) -> None:
        """ZEI-018: the limits are settings with these defaults."""
        entry = self.work(at(10, 8), at(10, 17, 30), pause=45)
        self.assertEqual(self.kinds(entry), [])
        settings = SystemSettings.load()
        settings.time_hint_day_hours = D("8")
        settings.save()
        self.assertEqual(self.kinds(entry), [HintKind.LONG_DAY])
        settings.time_hint_day_hours = D("0")
        settings.save()
        self.assertEqual(self.kinds(entry), [])


class BreakTests(TimesCase):
    """ZEI-018: more than 6 hours need 30 minutes of break, more than 9 hours 45 minutes."""

    def test_six_and_a_half_hours_with_15_minutes_of_break(self) -> None:
        """ZEI-018."""
        entry = self.work(at(10, 8), at(10, 14, 45), pause=15)
        hints = hints_for([entry])[entry.pk]
        self.assertEqual([hint.kind for hint in hints], [HintKind.SHORT_BREAK])
        self.assertEqual(hints[0].message, "Kurze Pause: 6,5 Stunden Arbeit mit 15 Minuten Pause (mindestens 30).")

    def test_more_than_nine_hours_need_45_minutes(self) -> None:
        """ZEI-018: 30 minutes are enough up to 9 hours, not beyond."""
        enough = self.work(at(10, 8), at(10, 17, 30), pause=30)
        self.assertEqual(self.kinds(enough), [])
        longer = self.work(at(11, 7), at(11, 17), pause=30)
        hints = hints_for([longer])[longer.pk]
        self.assertEqual([hint.kind for hint in hints], [HintKind.SHORT_BREAK])
        self.assertIn("(mindestens 45)", hints[0].message)

    def test_the_gap_between_two_entries_is_a_break(self) -> None:
        """ZEI-018: entries store one number of break minutes; the gaps between the entries of the day count too."""
        morning = self.work(at(10, 8), at(10, 12))
        afternoon = self.work(at(10, 12, 30), at(10, 15, 30))
        self.assertEqual(self.kinds(morning), [])
        self.assertEqual(self.kinds(afternoon), [])

    def test_a_gap_shorter_than_15_minutes_is_no_break(self) -> None:
        """ZEI-018: the act counts breaks of at least 15 minutes."""
        self.work(at(10, 8), at(10, 12))
        afternoon = self.work(at(10, 12, 10), at(10, 15, 30))
        self.assertEqual(self.kinds(afternoon), [HintKind.SHORT_BREAK])

    def test_the_break_limits_are_settings(self) -> None:
        """ZEI-018."""
        entry = self.work(at(10, 8), at(10, 14, 45), pause=15)
        settings = SystemSettings.load()
        settings.time_hint_break_minutes = 0
        settings.save()
        self.assertEqual(self.kinds(entry), [])
        settings.time_hint_break_minutes = 15
        settings.time_hint_break_hours = D("5")
        settings.save()
        self.assertEqual(self.kinds(entry), [])


class RestTests(TimesCase):
    """ZEI-018: less than 11 hours between two working days."""

    def test_nine_hours_of_rest_are_pointed_out_at_the_later_day(self) -> None:
        """ZEI-018."""
        evening = self.work(at(10, 14), at(10, 23), pause=45)
        morning = self.work(at(11, 8), at(11, 12))
        self.assertEqual(self.kinds(evening), [])
        hints = hints_for([morning])[morning.pk]
        self.assertEqual([hint.kind for hint in hints], [HintKind.SHORT_REST])
        self.assertEqual(
            hints[0].message, "Kurze Ruhezeit: 9 Stunden seit dem Ende um 23:00 am 10.03. (weniger als 11)."
        )

    def test_a_night_shift_and_the_next_afternoon(self) -> None:
        """ZEI-018: 22:00–06:00 is one working day although it ends on the next date; 14:00 is a new one."""
        night = self.work(at(10, 22), at(11, 6), pause=45)
        afternoon = self.work(at(11, 14), at(11, 18))
        self.assertEqual(self.kinds(night), [])
        self.assertEqual(self.kinds(afternoon), [HintKind.SHORT_REST])

    def test_a_short_gap_after_midnight_is_a_break(self) -> None:
        """ZEI-018: 18:00–23:00 and 00:30–03:00 belong to one working day; no rest is missing."""
        self.work(at(10, 18), at(10, 23))
        after_midnight = self.work(at(11, 0, 30), at(11, 3))
        self.assertEqual(self.kinds(after_midnight), [])

    def test_eleven_hours_and_more_are_enough(self) -> None:
        """ZEI-018."""
        self.work(at(10, 14), at(10, 21), pause=30)
        morning = self.work(at(11, 8), at(11, 12))
        self.assertEqual(self.kinds(morning), [])

    def test_rejected_entries_and_a_running_stopwatch_do_not_count(self) -> None:
        """ZEI-018: what was sent back is wrong; a running stopwatch has no end yet."""
        evening = self.work(at(10, 14), at(10, 23), pause=45)
        from rentalars.timetracking import services

        services.reject_entries([evening], "falscher Tag", rights=ALL_RIGHTS, user=None)
        morning = self.work(at(11, 8), at(11, 12))
        self.assertEqual(self.kinds(morning), [])
        self.assertEqual(hints_for([evening]), {})

    def test_working_days_are_formed_per_person(self) -> None:
        """ZEI-018: see the module description of ``timetracking.hints``."""
        entries = [
            self.work(at(10, 6), at(10, 12)),
            self.work(at(10, 18), at(10, 23)),
            self.work(at(11, 0, 30), at(11, 3)),
            self.work(at(11, 14), at(11, 18)),
        ]
        days = working_days(entries, HintLimits())
        self.assertEqual([len(day.entries) for day in days], [3, 1])


class HintQueryTests(TimesCase):
    """ZEI-018: the hints of a whole list cost one query (and the settings)."""

    def test_one_query_for_any_number_of_entries(self) -> None:
        entries = [self.work(at(day, 8), at(day, 19)) for day in range(2, 9)]
        SystemSettings.load()
        with self.assertNumQueries(2):  # the settings and the entries around
            found = hints_for(entries)
        self.assertEqual(len(found), 7)


# --- ZEI-019: expenses and travel costs ------------------------------------------------------------------------------


class ExpenseCase(MediaMixin, TimesCase):
    """Paula approves; the crew records."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        self.crew_rights = self.anna_user.rights

    def spend(self, kind: str = ExpenseKind.MEALS, *, amount: str | None = "14.00", **more) -> Expense:
        """An expense of Anna on the Stadtfest, recorded by herself."""
        values = {"date": datetime.date(2027, 3, 10), "project": self.project, **more}
        return expenses.create_expense(
            person=self.anna,
            kind=kind,
            amount=D(amount) if amount is not None else None,
            rights=self.crew_rights,
            user=self.anna_user,
            **values,
        )


class RecordingExpenseTests(ExpenseCase):
    """ZEI-019: kind, date, amount, note – by the person or the office."""

    def test_the_person_records_her_own(self) -> None:
        """ZEI-019."""
        expense = self.spend(note="Mittagessen Aufbau", submit=True)
        self.assertEqual(
            (expense.kind, expense.amount, expense.status, expense.note, expense.person),
            (ExpenseKind.MEALS, D("14.00"), TimeEntryStatus.SUBMITTED, "Mittagessen Aufbau", self.anna),
        )
        self.assertTrue(AuditLogEntry.objects.filter(object_id=str(expense.pk)).exists())  # ZEI-014

    def test_without_the_tick_it_stays_with_her(self) -> None:
        self.assertEqual(self.spend().status, TimeEntryStatus.RECORDED)

    def test_nothing_in_the_future(self) -> None:
        """ZEI-019, as ZEI-022."""
        with self.assertRaises(ValidationError) as caught:
            self.spend(date=datetime.date(2027, 3, 29))
        self.assertIn("date", caught.exception.message_dict)

    def test_only_projects_she_may_book_on(self) -> None:
        """ZEI-019, as ZEI-006: planned, internal or visible."""
        elsewhere = make_project("Messe", start=at(14), end=at(16))
        with self.assertRaises(ValidationError):
            self.spend(project=elsewhere)
        self.assertEqual(self.spend(project=self.warehouse).project, self.warehouse)

    def test_not_on_a_closed_or_cancelled_project(self) -> None:
        self.project.status = ProjectStatus.CANCELLED
        self.project.save()
        with self.assertRaises(ValidationError):
            self.spend()

    def test_only_for_others_with_the_right(self) -> None:
        """ZEI-019, as ZEI-011: the office records for others."""
        kai = make_person("Kai Kurz", rates={"Tontechnik": "30.00"})
        plan(self.project, self.sound, kai, start=at(10, 8), end=at(10, 20))
        with self.assertRaises(PermissionDenied):
            expenses.create_expense(
                person=kai,
                project=self.project,
                kind=ExpenseKind.PARKING,
                date=datetime.date(2027, 3, 10),
                amount=D("6.00"),
                rights=self.crew_rights,
                user=self.anna_user,
            )
        made = expenses.create_expense(
            person=kai,
            project=self.project,
            kind=ExpenseKind.PARKING,
            date=datetime.date(2027, 3, 10),
            amount=D("6.00"),
            rights=self.paula.rights,
            user=self.paula,
        )
        self.assertEqual(made.person, kai)


class TravelTests(ExpenseCase):
    """ZEI-019: a trip with the own car is kilometres × the rate of the settings (0.30 €)."""

    def test_kilometres_times_the_rate(self) -> None:
        """ZEI-019."""
        trip = self.spend(ExpenseKind.TRAVEL, amount=None, kilometres=D("84"), note="Lager – Marktplatz und zurück")
        self.assertEqual((trip.km_rate, trip.amount), (D("0.30"), D("25.20")))

    def test_the_trip_keeps_its_rate(self) -> None:
        """ZEI-019, as ZEI-008: a later change of the setting does not change recorded trips."""
        trip = self.spend(ExpenseKind.TRAVEL, amount=None, kilometres=D("100"))
        settings = SystemSettings.load()
        settings.expense_km_rate = D("0.38")
        settings.save()
        expenses.update_expense(trip, rights=self.crew_rights, user=self.anna_user, kilometres=D("120"))
        self.assertEqual((trip.km_rate, trip.amount), (D("0.30"), D("36.00")))
        new = self.spend(ExpenseKind.TRAVEL, amount=None, kilometres=D("100"))
        self.assertEqual(new.amount, D("38.00"))

    def test_a_ticket_has_its_amount(self) -> None:
        """ZEI-019: a trip without kilometres – a train ticket – is its amount."""
        ticket = self.spend(ExpenseKind.TRAVEL, amount="49.90")
        self.assertEqual((ticket.kilometres, ticket.km_rate, ticket.amount), (None, None, D("49.90")))

    def test_kilometres_only_for_trips(self) -> None:
        meal = self.spend(ExpenseKind.MEALS, amount="12.00", kilometres=D("30"))
        self.assertEqual((meal.kilometres, meal.km_rate, meal.amount), (None, None, D("12.00")))

    def test_without_kilometres_and_amount_nothing_is_saved(self) -> None:
        with self.assertRaises(ValidationError):
            self.spend(ExpenseKind.TRAVEL, amount=None)


class ReceiptTests(ExpenseCase):
    """ZEI-019, NFA-007: a photo or a PDF; photos upright, small and without their metadata."""

    def stored_image(self, expense: Expense):
        from PIL import Image

        with default_storage.open(expense.receipt.name) as stored:
            image = Image.open(io.BytesIO(stored.read()))
            image.load()
        return image

    def test_a_photo_is_reduced_and_loses_its_metadata(self) -> None:
        """ZEI-019: the photo of a phone, 3000 × 2000 pixels, turned by its EXIF orientation."""
        expense = self.spend(receipt=upload("IMG_0001.HEIC.jpg", picture(orientation=6)))
        self.assertTrue(expense.receipt.name.startswith(f"receipts/{self.anna.pk}/"))
        self.assertTrue(expense.receipt.name.endswith(".jpg"))
        image = self.stored_image(expense)
        self.assertEqual((image.format, image.size), ("JPEG", (1333, 2000)))  # upright, long side 2000
        self.assertEqual(dict(image.getexif()), {})

    def test_png_and_pdf_are_accepted(self) -> None:
        png = self.spend(receipt=upload("beleg.png", picture(400, 300, image_format="PNG"), "image/png"))
        self.assertEqual(self.stored_image(png).format, "JPEG")
        pdf = self.spend(receipt=upload("hotel.pdf", PDF, "application/pdf"))
        self.assertTrue(pdf.receipt.name.endswith(".pdf"))
        with default_storage.open(pdf.receipt.name) as stored:
            self.assertEqual(stored.read(), PDF)

    def test_other_files_are_refused(self) -> None:
        """NFA-007: nothing else, whatever the name says."""
        for name, content in (("beleg.jpg", b"<html><script>alert(1)</script>"), ("beleg.gif", b"GIF89a....")):
            with self.subTest(name=name), self.assertRaises(ValidationError) as caught:
                self.spend(receipt=upload(name, content))
            self.assertIn("Foto (JPEG oder PNG) oder eine PDF-Datei", str(caught.exception))
        self.assertFalse(Expense.objects.exists())

    def test_the_upload_limit_of_the_settings_holds(self) -> None:
        """NFA-007."""
        with (
            mock.patch("rentalars.timetracking.expenses.max_upload_bytes", return_value=1000),
            self.assertRaises(ValidationError) as caught,
        ):
            self.spend(receipt=upload("beleg.jpg", picture(800, 600)))
        self.assertIn("höchstens 0 MB", str(caught.exception))

    def test_replacing_and_deleting_remove_the_old_file(self) -> None:
        """Receipts are personal documents: they leave the disk with their expense."""
        expense = self.spend(receipt=upload("a.jpg", picture(600, 400)))
        first = expense.receipt.name
        with self.captureOnCommitCallbacks(execute=True):
            expenses.update_expense(
                expense, rights=self.crew_rights, user=self.anna_user, receipt=upload("b.pdf", PDF, "application/pdf")
            )
        self.assertFalse(default_storage.exists(first))
        second = expense.receipt.name
        with self.captureOnCommitCallbacks(execute=True):
            expenses.delete_expense(expense, rights=self.crew_rights, user=self.anna_user)
        self.assertFalse(default_storage.exists(second))


class ExpenseApprovalTests(ExpenseCase):
    """ZEI-019: approval like times (ZEI-012, ZEI-013), marked as reimbursed."""

    def test_approve_and_reimburse(self) -> None:
        """ZEI-019."""
        expense = self.spend(submit=True)
        self.assertEqual(expenses.approve_expenses([expense], rights=self.paula.rights, user=self.paula), 1)
        self.assertEqual((expense.status, expense.decided_by), (TimeEntryStatus.APPROVED, self.paula))
        with self.assertRaises(ValidationError):
            expenses.update_expense(expense, rights=self.crew_rights, user=self.anna_user, amount=D("99.00"))
        self.assertEqual(
            expenses.mark_reimbursed(
                [expense], rights=self.paula.rights, user=self.paula, on=datetime.date(2027, 3, 25)
            ),
            1,
        )
        self.assertEqual((expense.reimbursed_on, expense.status_label), (datetime.date(2027, 3, 25), "erstattet"))
        notice = Notification.objects.get(user=self.anna_user, kind=Kind.EXPENSE)
        self.assertEqual(notice.title, "1 Spesenposten erstattet (14,00 €)")

    def test_crew_neither_approves_nor_reimburses(self) -> None:
        """ZEI-013."""
        expense = self.spend(submit=True)
        with self.assertRaises(PermissionDenied):
            expenses.approve_expenses([expense], rights=self.crew_rights, user=self.anna_user)
        with self.assertRaises(PermissionDenied):
            expenses.mark_reimbursed([expense], rights=self.crew_rights, user=self.anna_user)

    def test_only_approved_expenses_are_reimbursed(self) -> None:
        submitted = self.spend(submit=True)
        self.assertEqual(expenses.mark_reimbursed([submitted], rights=self.paula.rights, user=self.paula), 0)
        self.assertIsNone(submitted.reimbursed_on)

    def test_sent_back_with_a_reason_the_person_is_told(self) -> None:
        """ZEI-019, as ZEI-012; UIX-005."""
        expense = self.spend(submit=True)
        with self.assertRaises(ValidationError):
            expenses.reject_expenses([expense], " ", rights=self.paula.rights, user=self.paula)
        expenses.reject_expenses([expense], "Beleg fehlt", rights=self.paula.rights, user=self.paula)
        self.assertEqual((expense.status, expense.rejection_reason), (TimeEntryStatus.REJECTED, "Beleg fehlt"))
        notice = Notification.objects.get(user=self.anna_user, kind=Kind.EXPENSE)
        self.assertEqual((notice.title, notice.body), ("1 Spesenposten zurückgegeben (14,00 €)", "Beleg fehlt"))
        # Corrected, it is "recorded" again and is handed in anew.
        expenses.update_expense(expense, rights=self.crew_rights, user=self.anna_user, note="mit Beleg")
        self.assertEqual(expense.status, TimeEntryStatus.RECORDED)

    def test_taking_back(self) -> None:
        """ZEI-019: a reimbursement set by mistake, then the approval."""
        expense = self.spend(submit=True)
        expenses.approve_expenses([expense], rights=self.paula.rights, user=self.paula)
        expenses.mark_reimbursed([expense], rights=self.paula.rights, user=self.paula)
        with self.assertRaises(ValidationError):
            expenses.take_back_approval(expense, rights=self.paula.rights, user=self.paula)
        expenses.take_back_reimbursement(expense, rights=self.paula.rights, user=self.paula)
        expenses.take_back_approval(expense, rights=self.paula.rights, user=self.paula)
        self.assertEqual((expense.status, expense.reimbursed_on), (TimeEntryStatus.SUBMITTED, None))

    def test_a_crew_chief_sees_only_his_projects(self) -> None:
        """NFA-010: with the right to approve, but for assigned projects only."""
        Role.objects.create(
            name="Crewchef",
            module_levels={"projects": 1, "time_tracking": 2},
            special_rights=["approve_times"],
            project_scope="assigned",
        )
        chris = make_user("chris", roles=("Crewchef",))
        own = self.spend(project=self.warehouse, submit=True)
        festival = self.spend(submit=True)
        visible = set(expenses.visible_expenses(chris.rights, chris))
        self.assertIn(own, visible)  # internal projects belong to everybody (ZEI-010)
        self.assertNotIn(festival, visible)
        with self.assertRaises(PermissionDenied):
            expenses.approve_expenses([festival], rights=chris.rights, user=chris)
        self.assertEqual(set(expenses.visible_expenses(self.crew_rights, self.anna_user)), {own, festival})


class ProjectCostTests(ExpenseCase):
    """ZEI-019, PRJ-025: approved expenses are costs of the project; the profit subtracts them."""

    def test_approved_expenses_are_costs_and_lower_the_profit(self) -> None:
        """ZEI-019."""
        before = compute_project_prices(self.project).contribution_margin
        approved = self.spend(amount="30.00", submit=True)
        self.spend(amount="99.00", submit=True)  # waits: no cost yet
        expenses.approve_expenses([approved], rights=self.paula.rights, user=self.paula)
        prices = compute_project_prices(self.project)
        self.assertEqual(prices.expenses_cost, D("30.00"))
        self.assertEqual(prices.contribution_margin, before - D("30.00"))

    def test_the_planning_page_loads_the_sum_with_the_project(self) -> None:
        """ZEI-019, NFA-014: annotated on the project query, the expenses cost no query of their own."""
        from rentalars.projects.models import Project

        expense = self.spend(amount="30.00", submit=True)
        expenses.approve_expenses([expense], rights=self.paula.rights, user=self.paula)
        project = Project.objects.annotate(approved_expenses_total=expenses.approved_expenses_total()).get(
            pk=self.project.pk
        )
        prices = compute_project_prices(project)
        with self.assertNumQueries(0):
            self.assertEqual(prices.expenses_cost, D("30.00"))
        empty = Project.objects.annotate(approved_expenses_total=expenses.approved_expenses_total()).get(
            pk=self.warehouse.pk
        )
        self.assertEqual(empty.approved_expenses_total, D("0"))

    def test_the_project_list_needs_one_query_for_all_projects(self) -> None:
        """PRJ-085: the sums of a page of projects, the expenses of all of them in one query."""
        expense = self.spend(amount="30.00", submit=True)
        expenses.approve_expenses([expense], rights=self.paula.rights, user=self.paula)
        projects = [self.project, self.warehouse]
        attach_sums(projects, rights=Rights.everything(), user=None)
        with_expenses = self.project.list_sums.profit
        expense.status = TimeEntryStatus.SUBMITTED
        expense.save()
        attach_sums(projects, rights=Rights.everything(), user=None)
        self.assertEqual(self.project.list_sums.profit - with_expenses, D("30.00"))


class ExpenseReportTests(ExpenseCase):
    """ZEI-019: per month and person, with the sums; as CSV."""

    def test_by_month_and_person(self) -> None:
        """ZEI-019."""
        kai = make_person("Kai Kurz", rates={"Tontechnik": "30.00"})
        plan(self.project, self.sound, kai, start=at(10, 8), end=at(10, 20))
        self.spend(amount="10.00", submit=True)
        trip = self.spend(ExpenseKind.TRAVEL, amount=None, kilometres=D("50"), submit=True)
        expenses.create_expense(
            person=kai,
            project=self.project,
            kind=ExpenseKind.LODGING,
            date=datetime.date(2027, 3, 11),
            amount=D("89.00"),
            rights=self.paula.rights,
            user=self.paula,
        )
        february = self.spend(amount="7.50", date=datetime.date(2027, 2, 26), project=self.warehouse)
        expenses.submit_expenses([february], rights=self.crew_rights, user=self.anna_user)
        expenses.approve_expenses([trip, february], rights=self.paula.rights, user=self.paula)
        expenses.mark_reimbursed([february], rights=self.paula.rights, user=self.paula)

        report = expenses.expense_report(Expense.objects.all())
        self.assertEqual(
            [
                (f"{row.month:%m}", row.person.sort_name, row.total, row.reimbursed, row.outstanding)
                for row in report.rows
            ],
            [
                ("02", "Becker, Anna", D("7.50"), D("7.50"), D("0")),
                ("03", "Becker, Anna", D("25.00"), D("0"), D("15.00")),
                ("03", "Kurz, Kai", D("89.00"), D("0"), D("0")),
            ],
        )
        self.assertEqual((report.total, report.reimbursed, report.outstanding), (D("121.50"), D("7.50"), D("15.00")))
        self.assertEqual(
            report.by_kind, [("Verpflegung", D("17.50")), ("Fahrt", D("15.00")), ("Übernachtung", D("89.00"))]
        )
        rows = expenses.expenses_csv(report).lstrip("﻿").splitlines()
        self.assertEqual(
            rows[0],
            "Monat;Person;Projektnummer;Projekt;Tag;Art;Kilometer;Arbeitsweg (km);Satz je Kilometer;Betrag;Notiz;"
            "Beleg;Status;Erstattet am",
        )
        self.assertIn(";Fahrt;50;;0,30;15,00;;nein;freigegeben;", rows[3])  # Way to work (ZEI-027)
        self.assertTrue(rows[1].startswith("02/2027;Becker, Anna;"))
        self.assertTrue(rows[1].endswith(";erstattet;26.03.2027") or "erstattet" in rows[1])


class PrivacyTests(ExpenseCase):
    """NFA-009: the expenses are part of what is told about a person and of what is erased."""

    def test_export_and_anonymise(self) -> None:
        self.spend(note="Hotel mit Anna Becker", submit=True)
        exported = export_person(self.anna)["expenses"]
        self.assertEqual(exported[0]["amount"], "14.00")
        self.assertEqual(exported[0]["note"], "Hotel mit Anna Becker")
        anonymise_person(self.anna)
        expense = Expense.objects.get()
        self.assertEqual((expense.note, expense.amount), ("", D("14.00")))
