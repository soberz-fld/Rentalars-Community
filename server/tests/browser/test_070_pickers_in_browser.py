# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: one picker for date and time fields with calendar and clock face (UIX-036), the periods
hatched in the calendars and the event box laid out like the rental box (PRJ-099), and the question whether to
extend the rental period for a phase beyond it, in the dialog over the crew planning (PRJ-100)."""

from __future__ import annotations

import datetime
import math
from typing import Any
from unittest import SkipTest

from django.utils import timezone

from rentalars.personnel.models import JobFunction
from rentalars.projects.models import ProjectPhase
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path

PICKER = "dialog.dt-picker[open]"


class PickerSteps:
    """Steps on the picker the tests read like sentences with."""

    page: Any

    def picker_button(self, name: str) -> Any:
        return self.page.locator(f'.dt-wrap:has(input[name="{name}"]) button.dt-btn').first

    def open_picker(self, name: str) -> Any:
        self.picker_button(name).click()
        picker = self.page.locator(PICKER)
        picker.wait_for()
        return picker

    def tap_clock(self, value: int, *, inner: bool = False, minute: bool = False) -> None:
        """Tap a number of the clock face: an hour of the outer or inner ring, or a minute."""
        frame = self.page.locator(f"{PICKER} .dt-clock").bounding_box()
        degrees = value * 6 if minute else (value % 12) * 30
        radius = frame["width"] / 2 * (0.53 if inner else 0.8)
        x = frame["x"] + frame["width"] / 2 + radius * math.sin(math.radians(degrees))
        y = frame["y"] + frame["height"] / 2 - radius * math.cos(math.radians(degrees))
        self.page.mouse.click(x, y)

    def focused(self, script: str = "document.activeElement.outerHTML") -> str:
        return self.page.evaluate(script)


class DateTimePickerTests(PickerSteps, BrowserTestCase):
    """UIX-036 on a field with date and time: the project form."""

    def setUp(self) -> None:
        super().setUp()
        self.start = timezone.localtime(self.project.start)
        self.next_day = (self.start + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        self.open(f"/projects/{self.project.pk}/edit/")

    def test_the_button_takes_the_place_of_the_browser_symbol(self) -> None:
        field = self.page.locator("input[name=start]")
        self.assertEqual(field.get_attribute("type"), "datetime-local")  # typing and the server stay as they are
        button = self.picker_button("start")
        self.assertEqual(button.get_attribute("aria-label"), "Datum und Uhrzeit wählen: Material außer Haus ab")
        self.assertEqual(button.get_attribute("aria-haspopup"), "dialog")
        # The button lies inside the field, at its right end.
        field_box, button_box = field.bounding_box(), button.bounding_box()
        self.assertGreater(button_box["x"], field_box["x"] + field_box["width"] / 2)
        self.assertLessEqual(button_box["x"] + button_box["width"], field_box["x"] + field_box["width"])
        # It covers the place of the browser's own symbol: a click there reaches this button.
        on_top = self.page.evaluate(
            "([x, y]) => document.elementFromPoint(x, y).closest('button') !== null"
            " && document.elementFromPoint(x, y).closest('button').className",
            [button_box["x"] + button_box["width"] / 2, button_box["y"] + button_box["height"] / 2],
        )
        self.assertEqual(on_top, "dt-btn")
        # A click into the field itself keeps it for typing.
        field.click()
        self.assertEqual(self.page.locator(PICKER).count(), 0)

    def test_day_then_hour_then_minute(self) -> None:
        picker = self.open_picker("start")
        self.assertEqual(picker.locator("h2").inner_text(), "Material außer Haus ab")
        picker.locator(f'button[data-day="{self.next_day}"]').click()
        self.tap_clock(9)
        self.assertEqual(picker.locator(".dt-clock").get_attribute("aria-label"), "Minute")  # on to the minute
        self.tap_clock(30, minute=True)
        self.assertEqual(picker.locator(".dt-entry input").nth(0).input_value(), "09")
        self.assertEqual(picker.locator(".dt-entry input").nth(1).input_value(), "30")
        picker.locator(".dialog-foot .btn", has_text="Anwenden").click()
        self.page.locator(PICKER).wait_for(state="detached")
        self.assertEqual(self.page.locator("input[name=start]").input_value(), f"{self.next_day}T09:30")
        # The field said it changed: "until" followed "from" (UIX-025).
        self.assertGreater(self.page.locator("input[name=end]").input_value(), f"{self.next_day}T09:30")
        self.assertEqual(self.focused("document.activeElement.className"), "dt-btn")

    def test_the_inner_ring_and_a_dragged_minute(self) -> None:
        picker = self.open_picker("start")
        self.tap_clock(21, inner=True)
        frame = picker.locator(".dt-clock").bounding_box()
        centre_x, centre_y, radius = (
            frame["x"] + frame["width"] / 2,
            frame["y"] + frame["height"] / 2,
            frame["width"] * 0.4,
        )

        def at_minute(minute: int) -> tuple[float, float]:
            angle = math.radians(minute * 6)
            return centre_x + radius * math.sin(angle), centre_y - radius * math.cos(angle)

        self.page.mouse.move(*at_minute(10))
        self.page.mouse.down()
        self.page.mouse.move(*at_minute(17), steps=6)
        self.page.mouse.up()
        self.assertEqual(picker.locator(".dt-clock").get_attribute("aria-valuetext"), "21:17")
        # A tap takes the nearest five minutes.
        self.tap_clock(33, minute=True)
        self.assertEqual(picker.locator(".dt-clock").get_attribute("aria-valuetext"), "21:35")

    def test_with_the_keyboard_only(self) -> None:
        field = self.page.locator("input[name=start]")
        field.focus()
        self.page.keyboard.press("Alt+ArrowDown")
        self.page.locator(PICKER).wait_for()
        start_day = self.start.strftime("%Y-%m-%d")
        self.assertEqual(self.focused("document.activeElement.dataset.day"), start_day)
        self.page.keyboard.press("ArrowRight")
        self.assertEqual(self.focused("document.activeElement.dataset.day"), self.next_day)
        self.page.keyboard.press("PageDown")  # a month later: the page turns
        self.assertGreater(self.focused("document.activeElement.dataset.day")[:7], self.next_day[:7])
        self.page.keyboard.press("PageUp")
        self.page.keyboard.press("Enter")
        self.assertIn("edge", self.focused("document.activeElement.className"))
        self.page.keyboard.press("Tab")  # to the hour
        self.assertEqual(self.focused("document.activeElement.getAttribute('aria-label')"), "Stunde")
        self.page.keyboard.type("14")  # two digits: on to the minute
        self.assertEqual(self.focused("document.activeElement.getAttribute('aria-label')"), "Minute")
        self.page.keyboard.type("45")
        self.page.keyboard.press("Tab")  # the clock face, a slider
        self.assertEqual(self.focused("document.activeElement.getAttribute('role')"), "slider")
        self.page.keyboard.press("ArrowUp")  # 14:46
        self.page.keyboard.press("PageDown")  # 14:41
        self.page.keyboard.press("Enter")  # takes the time
        self.page.locator(PICKER).wait_for(state="detached")
        self.assertEqual(field.input_value(), f"{self.next_day}T14:41")
        self.assertEqual(self.focused("document.activeElement.name"), "start")

    def test_escape_changes_nothing(self) -> None:
        before = self.page.locator("input[name=start]").input_value()
        picker = self.open_picker("start")
        picker.locator(f'button[data-day="{self.next_day}"]').click()
        self.page.keyboard.press("Escape")
        self.page.locator(PICKER).wait_for(state="detached")
        self.assertEqual(self.page.locator("input[name=start]").input_value(), before)
        self.assertEqual(self.focused("document.activeElement.className"), "dt-btn")

    def test_an_optional_field_can_be_cleared(self) -> None:
        self.assertEqual(self.open_picker("start").locator("button", has_text="Leeren").count(), 0)
        self.page.keyboard.press("Escape")
        self.page.locator("input[name=event_start]").fill(f"{self.next_day}T10:00")
        picker = self.open_picker("event_start")
        picker.locator("button", has_text="Leeren").click()
        self.assertEqual(self.page.locator("input[name=event_start]").input_value(), "")


class DateAndTimeAloneTests(PickerSteps, BrowserTestCase):
    """UIX-036 on a field with a date alone and one with a time alone."""

    def test_a_date_is_taken_with_the_tap_on_the_day(self) -> None:
        self.open("/projects/")
        if not self.page.locator("input[name=since]").is_visible():
            self.page.locator("[data-filter-toggle]").first.click()
        picker = self.open_picker("since")
        self.assertEqual(picker.locator(".dt-clock").count(), 0)
        day = picker.locator("button[data-day]").nth(14)
        chosen = day.get_attribute("data-day")
        day.click()
        self.page.locator(PICKER).wait_for(state="detached")
        self.assertEqual(self.page.locator("input[name=since]").input_value(), chosen)

    def test_a_time_typed_into_the_clock(self) -> None:
        self.open("/times/quick/")
        picker = self.open_picker("begin")
        self.assertEqual(picker.locator("table.range-month").count(), 0)
        self.assertEqual(self.focused("document.activeElement.getAttribute('aria-label')"), "Stunde")
        self.page.keyboard.type("0715")
        self.page.keyboard.press("Enter")
        self.page.locator(PICKER).wait_for(state="detached")
        self.assertEqual(self.page.locator("input[name=begin]").input_value(), "07:15")


class PickerOnAPhoneTests(PickerSteps, BrowserTestCase):
    """UIX-036 at 360 pixels: the dialog fits; date and time take turns."""

    viewport = {"width": 360, "height": 740}

    def test_the_picker_fits_and_goes_on_from_the_day_to_the_time(self) -> None:
        self.open(f"/projects/{self.project.pk}/edit/")
        picker = self.open_picker("start")
        frame = picker.bounding_box()
        self.assertGreaterEqual(frame["x"], 0)
        self.assertLessEqual(frame["x"] + frame["width"], 360)
        self.assertLessEqual(frame["y"] + frame["height"], 740)
        self.assertTrue(picker.locator(".dt-date-pane").is_visible())
        self.assertFalse(picker.locator(".dt-time-pane").is_visible())
        day = (timezone.localtime(self.project.start) + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        picker.locator(f'button[data-day="{day}"]').click()
        self.assertTrue(picker.locator(".dt-time-pane").is_visible())
        self.assertFalse(picker.locator(".dt-date-pane").is_visible())
        self.assertEqual(self.focused("document.activeElement.getAttribute('role')"), "slider")
        self.assertLessEqual(picker.bounding_box()["y"] + picker.bounding_box()["height"], 740)
        self.tap_clock(7)
        self.tap_clock(0, minute=True)
        picker.locator(".dialog-foot .btn", has_text="Anwenden").click()
        self.assertEqual(self.page.locator("input[name=start]").input_value(), f"{day}T07:00")
        self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), 360)


class PeriodsHatchedTests(PickerSteps, BrowserTestCase):
    """PRJ-099: each period picker shows the other period hatched; the event box is laid out like the rental box."""

    def setUp(self) -> None:
        super().setUp()
        self.first = timezone.localtime(self.project.start).date()
        self.days = [(self.first + datetime.timedelta(days=offset)).strftime("%Y-%m-%d") for offset in range(4)]

    def range_picker(self, index: int) -> Any:
        self.page.locator("button.range-btn").nth(index).click()
        picker = self.page.locator("dialog.range-picker[open]")
        picker.wait_for()
        return picker

    def test_rental_and_event_show_each_other(self) -> None:
        self.open(f"/projects/{self.project.pk}/edit/")
        # Nothing to show while the event period is empty.
        picker = self.range_picker(0)
        self.assertEqual(picker.locator(".mark-legend").count(), 0)
        picker.locator(".dialog-foot .btn").first.click()
        self.page.locator("input[name=event_start]").fill(f"{self.days[1]}T10:00")
        self.page.locator("input[name=event_end]").fill(f"{self.days[2]}T23:00")
        picker = self.range_picker(0)
        self.assertEqual(
            picker.locator("button.mark-event").evaluate_all("(days) => days.map((day) => day.dataset.day)"),
            self.days[1:3],
        )
        self.assertEqual(picker.locator("button.mark-rental").count(), 0)  # its own period is the selection
        self.assertIn("Veranstaltung:", picker.locator(".mark-legend").inner_text())
        self.assertIn("Veranstaltung", picker.locator(f'button[data-day="{self.days[1]}"]').get_attribute("aria-label"))
        picker.locator(".dialog-foot .btn").first.click()
        picker = self.range_picker(1)
        self.assertGreaterEqual(picker.locator("button.mark-rental").count(), 3)
        self.assertEqual(picker.locator("button.mark-event").count(), 0)
        self.assertIn("Mietzeitraum:", picker.locator(".mark-legend").inner_text())
        # The single picker of a field shows them as well.
        picker.locator(".dialog-foot .btn").first.click()
        self.assertGreaterEqual(self.open_picker("event_start").locator("button.mark-rental").count(), 3)

    def test_the_event_box_is_laid_out_like_the_rental_box(self) -> None:
        self.open(f"/projects/{self.project.pk}/edit/")
        rental = [self.page.locator(f"input[name={name}]").bounding_box() for name in ("start", "end")]
        event = [self.page.locator(f"input[name={name}]").bounding_box() for name in ("event_start", "event_end")]
        for one, other in zip(rental, event, strict=True):
            self.assertAlmostEqual(one["x"], other["x"], delta=1)
            self.assertAlmostEqual(one["width"], other["width"], delta=1)
        buttons = [self.page.locator("button.range-btn").nth(index).bounding_box() for index in (0, 1)]
        self.assertAlmostEqual(buttons[0]["x"], buttons[1]["x"], delta=1)
        # Each button stands in the row of its fields, as high as they are.
        for button, fields in zip(buttons, (rental, event), strict=True):
            self.assertAlmostEqual(button["y"], fields[0]["y"], delta=1)
            self.assertAlmostEqual(button["height"], fields[0]["height"], delta=2)
        days = self.page.locator("input[name=rental_days]").bounding_box()
        self.assertAlmostEqual(days["x"], event[0]["x"], delta=1)
        self.assertGreater(days["y"], event[0]["y"] + event[0]["height"])

    def test_a_phase_shows_rental_period_and_event(self) -> None:
        self.project.event_start = self.project.start + datetime.timedelta(days=1)
        self.project.event_end = self.project.start + datetime.timedelta(days=1, hours=10)
        self.project.save()
        self.open(f"/projects/{self.project.pk}/phases/new/")
        picker = self.range_picker(0)
        self.assertGreaterEqual(picker.locator("button.mark-rental").count(), 3)
        self.assertEqual(picker.locator("button.mark-event").count(), 1)
        legend = picker.locator(".mark-legend li").all_inner_texts()
        self.assertEqual([text.split(":")[0] for text in legend], ["Mietzeitraum", "Veranstaltung"])
        # UIX-036: the times of the period picker have the clock face as well.
        self.assertEqual(picker.locator(".range-times button.dt-btn").count(), 2)


class ExtendFromTheCrewPlanningTests(BrowserTestCase):
    """PRJ-100 in the dialog "Neue Phase …" over the crew planning (PRJ-094)."""

    def setUp(self) -> None:
        super().setUp()
        self.hand = JobFunction.objects.get(name="Stagehand")
        self.day_before = (timezone.localtime(self.project.start) - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    def new_phase_before_the_rental_period(self) -> Any:
        self.open_planning()
        form = self.page.locator("form.crew-add")
        form.locator("select[name=job_function]").select_option(str(self.hand.pk))
        form.locator("select[name=phase]").select_option("new")
        dialog = self.page.locator("dialog#phase-dialog[open]")
        dialog.wait_for()
        dialog.locator("select[name=kind]").select_option("setup")
        dialog.locator("input[name=title]").fill("Vorbau")
        dialog.locator("input[name=start]").fill(f"{self.day_before}T14:00")
        dialog.locator("input[name=end]").fill(f"{self.day_before}T20:00")
        # PRJ-120: the dialog has rows "Funktion + Plätze" with buttons of their own: "Phase speichern" is in the foot.
        dialog.locator(".dialog-foot button[type=submit]").click()
        dialog.locator("h2", has_text="Mietzeitraum erweitern?").wait_for()
        return dialog

    def test_extend(self) -> None:
        start = self.project.start
        dialog = self.new_phase_before_the_rental_period()
        phase = ProjectPhase.objects.get(project=self.project, title="Vorbau")
        # The phase is saved and chosen already; the question waits with the focus on "Erweitern".
        self.assertEqual(self.page.locator("form.crew-add select[name=phase]").input_value(), str(phase.pk))
        self.assertEqual(self.page.evaluate("document.activeElement.textContent"), "Erweitern")
        self.project.refresh_from_db()
        self.assertEqual(self.project.start, start)
        self.page.keyboard.press("Enter")
        dialog.locator("h2", has_text="Mietzeitraum erweitert").wait_for()
        self.assertIn("Mietzeitraum erweitert:", dialog.inner_text())
        self.project.refresh_from_db()
        self.assertEqual(self.project.start, phase.start)
        self.assertTrue(self.page.locator("#changed-note").is_visible())  # the planning offers the new periods
        dialog.locator("button", has_text="Schließen").click()
        self.page.locator("dialog#phase-dialog[open]").wait_for(state="detached")
        self.assertEqual(self.page.evaluate("document.activeElement.name"), "phase")

    def test_do_not_extend(self) -> None:
        start = self.project.start
        dialog = self.new_phase_before_the_rental_period()
        dialog.locator("button", has_text="Nicht erweitern").click()
        self.page.locator("dialog#phase-dialog[open]").wait_for(state="detached")
        self.project.refresh_from_db()
        self.assertEqual(self.project.start, start)
        self.assertTrue(ProjectPhase.objects.filter(project=self.project, title="Vorbau").exists())
        self.assertEqual(self.page.evaluate("document.activeElement.name"), "phase")


class PickersAccessibilityTests(PickerSteps, BrowserTestCase):
    """NFA-025 with axe-core: the open pickers, the periods hatched, and the question after saving a phase."""

    bypass_csp = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = _axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()

    def run_axe(self) -> list[str]:
        if not self.page.evaluate("typeof axe !== 'undefined'"):
            self.page.add_script_tag(path=str(self.axe))
        return self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            WCAG_AA,
        )

    def test_no_findings(self) -> None:
        self.project.event_start = self.project.start + datetime.timedelta(days=1)
        self.project.event_end = self.project.start + datetime.timedelta(days=1, hours=10)
        self.project.save()
        self.open(f"/projects/{self.project.pk}/edit/")
        findings = [f"project form: {finding}" for finding in self.run_axe()]
        self.open_picker("start")
        findings += [f"date and time: {finding}" for finding in self.run_axe()]
        self.page.locator(f"{PICKER} .dt-clock").focus()
        self.page.keyboard.press("Enter")  # the minutes
        findings += [f"minutes: {finding}" for finding in self.run_axe()]
        self.page.keyboard.press("Escape")
        self.page.locator("button.range-btn").first.click()
        self.page.locator("dialog.range-picker[open]").wait_for()
        findings += [f"period picker: {finding}" for finding in self.run_axe()]
        self.page.keyboard.press("Escape")
        self.open("/times/quick/")
        self.open_picker("begin")
        findings += [f"time alone: {finding}" for finding in self.run_axe()]
        phase = ProjectPhase.objects.create(
            project=self.project,
            kind="setup",
            start=self.project.start - datetime.timedelta(hours=20),
            end=self.project.start - datetime.timedelta(hours=14),
        )
        self.open(f"/projects/{self.project.pk}/course/?extend={phase.pk}")
        findings += [f"question: {finding}" for finding in self.run_axe()]
        self.assertEqual(findings, [], "\n".join(findings))
