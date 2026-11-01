# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser, area "times": hints at conspicuous times (ZEI-018), expenses and travel costs (ZEI-019).

* The expense dialog with scripts: the kilometres appear only for a trip, a photo of the receipt goes along with the
  form, the confirmation names the amount, and "My expenses" fetches itself again when the dialog closes; the
  deployment view loads itself again after an expense.
* The quick time entry points out a long working day in its confirmation and saves the time all the same.
* On a phone without horizontal scrolling and checked with axe-core (NFA-025): "My expenses" and its dialog, the
  report of expenses, the approval with times, hints and expenses, "My times" and the hours report with hints.
"""

from __future__ import annotations

import datetime
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest import SkipTest

from django.test import override_settings

from rentalars.accounts.rights import Rights
from rentalars.timetracking import expenses
from rentalars.timetracking.models import Expense, ExpenseKind
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.browser.test_time_in_browser import TimeInBrowserTestCase
from tests.helpers import NOW, record_time
from tests.unit.test_080_times import picture

ALL = Rights.everything()


class TimesInBrowserCase(TimeInBrowserTestCase):
    """Anna Becker of the sample data is the logged-in administrator; receipts go to a folder of their own."""

    def setUp(self) -> None:
        super().setUp()
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        media = override_settings(MEDIA_ROOT=folder.name, SERVE_MEDIA_VIA_NGINX=False)
        media.enable()
        self.addCleanup(media.disable)
        self.folder = Path(folder.name)

    def spend(self, amount: str = "14.00", **more) -> Expense:
        values = {"kind": ExpenseKind.MEALS, "date": NOW.date(), "project": self.today, **more}
        return expenses.create_expense(person=self.anna, amount=Decimal(amount), rights=ALL, user=None, **values)

    def yesterday_long(self) -> None:
        """A long day yesterday and a short rest before this morning (ZEI-018)."""
        yesterday = NOW - datetime.timedelta(days=1)
        record_time(
            self.anna,
            self.today,
            "Lager",
            yesterday.replace(hour=11),
            yesterday.replace(hour=23, minute=30),
            break_minutes=30,
            submit=True,
        )


class ExpenseDialogInBrowserTests(TimesInBrowserCase):
    """ZEI-019: the dialog with scripts, on "My expenses" and in the deployment view."""

    def test_a_trip_by_kilometre_and_a_meal_with_a_photo(self) -> None:
        self.open("/times/expenses/")
        self.page.get_by_role("link", name="Spesen erfassen").click()
        dialog = self.dialog()
        dialog.wait_for()
        kilometres = dialog.locator("[name=kilometres]")
        # Only for a trip. The dialog's script hides the field right after the dialog is swapped in – wait for it
        # rather than read the state at once (it failed under load in the full run).
        kilometres.wait_for(state="hidden", timeout=5000)
        dialog.locator("[name=kind]").select_option("travel")
        kilometres.wait_for(state="visible", timeout=5000)
        kilometres.fill("84")
        dialog.locator("[name=note]").fill("Lager – Marktplatz und zurück")
        dialog.get_by_role("button", name="Spesen speichern").click()
        self.settle()
        self.assertIn("25,20 €", dialog.inner_text())
        self.assertIn("84 km × 0,30 €", dialog.inner_text())

        dialog.get_by_role("link", name="Weitere Spesen").click()
        self.settle()
        dialog.locator("[name=amount]").fill("12,40")
        dialog.locator("[name=receipt]").set_input_files(
            {"name": "beleg.jpg", "mimeType": "image/jpeg", "buffer": picture(1600, 1200)}
        )
        dialog.get_by_role("button", name="Spesen speichern").click()
        self.settle()
        self.assertIn("mit Beleg", dialog.inner_text())
        dialog.get_by_role("button", name="Fertig").click()
        self.settle()
        listed = self.text_of("#my-expenses")
        self.assertIn("25,20 €", listed)
        self.assertIn("12,40 €", listed)
        self.assertIn("37,60 €", listed)  # the sum of the month
        receipt = Expense.objects.get(amount=Decimal("12.40")).receipt
        self.assertTrue((self.folder / receipt.name).is_file())

    def test_the_deployment_view_loads_itself_again(self) -> None:
        self.open(f"/projects/{self.show.pk}/deployment/")
        self.assertIn("Für dieses Projekt sind noch keine Spesen erfasst.", self.page.inner_text("main"))
        self.page.locator("section", has_text="Meine Spesen in diesem Projekt").get_by_role(
            "link", name="Spesen erfassen"
        ).click()
        dialog = self.dialog()
        dialog.wait_for()
        dialog.locator("[name=kind]").select_option("parking")
        dialog.locator("[name=amount]").fill("6")
        dialog.get_by_role("button", name="Spesen speichern").click()
        self.settle()
        with self.page.expect_navigation():
            dialog.get_by_role("button", name="Fertig").click()
        self.assertIn("Parken/Maut", self.page.inner_text("main"))
        self.assertEqual(Expense.objects.get().project, self.show)


class HintInBrowserTests(TimesInBrowserCase):
    """ZEI-018: the quick entry says it at once – and has saved the time."""

    def test_the_confirmation_points_out_a_short_rest(self) -> None:
        self.yesterday_long()
        self.open("/times/")
        self.page.locator(".page-head").get_by_role("link", name="Zeit erfassen").click()
        self.dialog().wait_for()
        self.page.select_option("#dialog [name=project]", str(self.today.pk))
        self.settle()
        self.record("06:00", "07:30")
        text = self.dialog().inner_text()
        self.assertIn("Zeit erfasst", text)
        self.assertIn("Bitte prüfen:", text)
        self.assertIn("Kurze Ruhezeit: 6,5 Stunden seit dem Ende um 23:30", text)


class TimesOnAPhoneTests(TimesInBrowserCase):
    """ZEI-018, ZEI-019: the new pages and parts on a phone, with axe-core (NFA-025)."""

    bypass_csp = True

    def check(self, path: str, *, then: str = "") -> None:
        axe = _axe_path()
        if axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        self.page.set_viewport_size({"width": 375, "height": 800})
        self.open(path)
        self.page.wait_for_load_state("networkidle")
        if then:
            self.page.locator(then).first.click()
            self.page.locator("dialog#dialog[open]").wait_for()
            self.settle()
        width = self.page.evaluate("document.scrollingElement.scrollWidth")
        self.assertLessEqual(width, 375, path)
        self.page.add_script_tag(path=str(axe))
        findings = self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            WCAG_AA,
        )
        self.assertEqual(findings, [], "\n".join(findings))

    def some_expenses(self) -> None:
        trip = self.spend("25.20", kind=ExpenseKind.TRAVEL, note="Lager – Marktplatz und zurück, Rückweg über die A7")
        meal = self.spend("14.00", submit=True)
        expenses.submit_expenses([trip], rights=ALL, user=None)
        expenses.approve_expenses([trip], rights=ALL, user=None)
        self.assertEqual(meal.status, "submitted")

    def test_my_expenses(self) -> None:
        self.some_expenses()
        self.check("/times/expenses/")

    def test_the_dialog(self) -> None:
        self.some_expenses()
        self.check("/times/expenses/", then=".page-head a.btn")
        self.page.locator("#dialog [name=kind]").select_option("travel")
        self.assertTrue(self.page.locator("#dialog [name=kilometres]").is_visible())

    def test_the_report_of_expenses(self) -> None:
        self.some_expenses()
        self.check("/times/report/expenses/")

    def test_the_approval_with_hints_and_expenses(self) -> None:
        self.some_expenses()
        self.yesterday_long()
        self.check("/times/approval/")
        text = self.page.inner_text("main")
        self.assertIn("Spesen und Fahrtkosten", text)
        self.assertIn("Langer Arbeitstag", text)

    def test_the_box_for_all_follows_the_rows_of_the_approval(self) -> None:
        """V14: ticking a row off takes the tick of "all" away; ticking "all" ticks every row again."""
        self.yesterday_long()
        two_days = NOW - datetime.timedelta(days=4)
        record_time(
            self.anna,
            self.today,
            "Lager",
            two_days.replace(hour=9),
            two_days.replace(hour=13),
            break_minutes=0,
            submit=True,
        )
        self.open("/times/approval/")
        self.page.wait_for_load_state("networkidle")
        every = self.page.locator("[data-select-all]")
        rows = self.page.locator("[data-select-line]")
        self.assertGreaterEqual(rows.count(), 2)
        self.assertTrue(every.is_checked())
        rows.first.uncheck()
        self.assertFalse(every.is_checked())
        self.assertTrue(every.evaluate("box => box.indeterminate"))
        every.check()
        self.assertEqual(self.page.locator("[data-select-line]:checked").count(), rows.count())
        every.uncheck()
        self.assertEqual(self.page.locator("[data-select-line]:checked").count(), 0)

    def test_my_times_and_the_report_with_hints(self) -> None:
        self.yesterday_long()
        self.check("/times/?week=2027-02-28")  # yesterday, Sunday, closes the week before
        self.assertIn("Langer Arbeitstag", self.page.inner_text("main"))
        self.check("/times/report/?since=2027-02-01")
        self.assertIn("1 Eintrag hat einen Hinweis", self.page.inner_text("main"))
