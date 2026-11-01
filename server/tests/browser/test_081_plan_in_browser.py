# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "plan", in the browser – with axe-core: a deployment dragged in the personnel plan and confirmed in
the dialog (VFG-031); the conflict filled red, every availability hatched, exact times in the hover (VFG-032); hourly
lines where the width allows and the wider scroll range (VFG-033); a time range marked in the week of the
availability calendar with the mouse and by tapping (PER-039)."""

from __future__ import annotations

from typing import ClassVar

from rentalars.personnel.models import AvailabilityMark, Person
from rentalars.projects.models import CrewLine
from tests.browser.base import BrowserTestCase
from tests.browser.test_071_planning_in_browser import AxeMixin
from tests.helpers import at, make_person, make_project, plan

PERSONNEL = "/schedule/personnel/?days=4&from=2027-03-09"

#: Pixels of the row of a bar for so many minutes, measured in the page (the columns follow the window).
PIXELS = """([key, minutes]) => {
  const bar = document.querySelector(`[data-tl-key="${key}"]`);
  const panel = bar.closest('[data-tl-zoom]');
  const total = Number(panel.dataset.columns) * Number(panel.dataset.hours) * 60;
  return bar.closest('.tl-row').getBoundingClientRect().width / total * minutes;
}"""


class PersonnelPlanInTheBrowserTests(AxeMixin, BrowserTestCase):
    """VFG-031, VFG-032, VFG-033 on Planung → Personalplan."""

    viewport: ClassVar[dict[str, int]] = {"width": 1920, "height": 1000}

    def setUp(self) -> None:
        super().setUp()
        self.paul = make_person("Paul Weber", rates={"Stagehand": "20.00"})
        self.job = make_project("Firmenfeier", start=at(10, 8), end=at(12, 18))
        self.line = plan(self.job, "Stagehand", self.paul, start=at(10, 9), end=at(10, 13))
        AvailabilityMark.objects.create(person=self.paul, start=at(10, 12), end=at(10, 16), state="unavailable")
        AvailabilityMark.objects.create(person=self.paul, start=at(11, 8), end=at(11, 12), state="available")
        AvailabilityMark.objects.create(person=self.paul, start=at(11, 14), end=at(11, 18), state="limited")

    def test_drag_a_deployment(self) -> None:
        self.open(PERSONNEL)
        self.assertEqual(self.axe_findings(".personnel-plan"), [])
        key = f"crew-{self.line.pk}"
        bar = self.page.locator(f'[data-tl-key="{key}"]')
        bar.scroll_into_view_if_needed()
        box = bar.bounding_box()
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        distance = self.page.evaluate(PIXELS, [key, 180])
        self.page.mouse.move(x, y)
        self.page.mouse.down()
        self.page.mouse.move(x + distance / 2, y, steps=4)
        self.page.mouse.move(x + distance, y, steps=4)
        self.assertEqual(self.page.locator(".tl-ghost").count(), 1)
        self.page.mouse.up()
        self.page.locator("#dialog[open] .move-form").wait_for()
        dialog = self.text_of("#dialog")
        self.assertIn("Einsatz von Paul Weber als Stagehand verschieben", dialog)
        self.assertIn("Neu: Mi 10.03. 12:00 – 16:00", dialog)
        self.assertIn("nicht verfügbar", dialog)  # the warning at the new times (PRJ-022)
        self.assertEqual(self.axe_findings("#dialog"), [])
        self.page.locator("#move-foot button[type=submit]").click()
        self.page.locator("#dialog[open] [role=status]").wait_for()
        with self.page.expect_navigation():
            self.page.locator("#dialog [data-close-dialog]").click()
        self.page.wait_for_load_state("networkidle")
        line = CrewLine.objects.get(pk=self.line.pk)
        self.assertEqual((line.start, line.end), (at(10, 12), at(10, 16)))
        self.assertEqual(self.page.evaluate("document.activeElement.dataset.tlKey"), key)

    def test_conflict_hatching_and_hover(self) -> None:
        self.open(PERSONNEL)
        conflict = self.page.locator(f'[data-tl-key="crew-{self.line.pk}"]')
        red = self.page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--red').trim()")
        background = conflict.evaluate("bar => getComputedStyle(bar).backgroundColor")
        self.assertEqual(
            background,
            self.page.evaluate(
                f"(() => {{ const s = document.createElement('span'); s.style.color = '{red}'; document.body.append(s); const c = getComputedStyle(s).color; s.remove(); return c; }})()"
            ),
        )
        self.assertEqual(conflict.evaluate("bar => getComputedStyle(bar).outlineStyle"), "none")
        self.assertIn("Mi 10.03., 9:00 Uhr bis 13:00 Uhr", conflict.get_attribute("title"))
        for state in ("available", "limited", "unavailable"):
            with self.subTest(state=state):
                image = self.page.locator(f".tl-avail .tl-bar.is-{state}").first.evaluate(
                    "bar => getComputedStyle(bar).backgroundImage"
                )
                self.assertIn("repeating-linear-gradient", image)
        # Text on the red fill is readable (axe's colour contrast on the plan, both bars and legend).
        self.assertEqual(self.axe_findings(".plan-legend"), [])

    def test_hourly_lines_where_the_width_allows_and_the_wider_range(self) -> None:
        self.open(PERSONNEL)
        panel = self.page.locator("[data-tl-zoom]")
        self.assertEqual(panel.get_attribute("data-columns"), "160")
        line = "g => getComputedStyle(g).getPropertyValue('--tl-hour-line').trim()"
        self.assertNotEqual(self.page.locator(".tl-grid").evaluate(line), "")
        # It opens on the chosen days, two spans of days to scroll into on each side.
        start = panel.evaluate("p => p.scrollLeft")
        width = panel.evaluate(
            "p => (p.querySelector('.tl-grid').scrollWidth - p.querySelector('.tl-label').offsetWidth) / 5"
        )
        self.assertAlmostEqual(start / width, 2, delta=0.05)
        self.page.set_viewport_size({"width": 900, "height": 900})
        self.assertEqual(self.page.locator(".tl-grid").evaluate(line), "")
        self.open("/schedule/personnel/?days=10&from=2027-03-09")
        self.page.set_viewport_size({"width": 1920, "height": 1000})
        self.assertEqual(self.page.locator(".tl-grid").evaluate(line), "")  # 10 days: an hour is too narrow


class MarkingATimeRangeInTheBrowserTests(AxeMixin, BrowserTestCase):
    """PER-039: a range of hours over one or several days, by dragging or by tapping start and end."""

    URL = "/me/availability/?view=week&week=2027-03-08"

    def setUp(self) -> None:
        super().setUp()
        self.person = Person.objects.get(user__username="anna")

    def show_hours_from(self, hour: int) -> None:
        """The week in view, scrolled inside to the hour."""
        scroller = self.page.locator(".wk-scroll")
        scroller.scroll_into_view_if_needed()
        scroller.evaluate(f"s => {{ s.scrollTop = s.querySelector('.wk-col').offsetHeight * {hour} / 24; }}")

    def point(self, day: str, minutes: int) -> tuple[float, float]:
        box = self.page.locator(f'.wk-col[data-day="{day}"]').bounding_box()
        return box["x"] + box["width"] / 2, box["y"] + box["height"] * (minutes + 7) / 1440

    def test_drag_over_three_days(self) -> None:
        self.open(self.URL)
        self.show_hours_from(8)
        x, y = self.point("2027-03-08", 9 * 60)
        x2, y2 = self.point("2027-03-10", 13 * 60 + 15)
        self.page.mouse.move(x, y)
        self.page.mouse.down()
        self.page.mouse.move((x + x2) / 2, (y + y2) / 2, steps=5)
        self.page.mouse.move(x2, y2, steps=5)
        self.page.mouse.up()
        self.assertEqual(self.page.locator(".wk-select").count(), 3)
        self.assertEqual(self.page.input_value('input[name="start_day"]'), "2027-03-08")
        self.assertEqual(self.page.input_value('input[name="end_day"]'), "2027-03-10")
        self.assertTrue(self.page.is_checked('input[name="with_times"]'))
        self.assertEqual(self.page.input_value('input[name="start_time"]'), "09:00")
        self.assertEqual(self.page.input_value('input[name="end_time"]'), "13:30")
        said = self.text_of("[data-avail-selection]")
        self.assertIn("Gewählt: Montag, 8. März bis Mittwoch, 10. März, an jedem Tag 9:00 bis 13:30 Uhr.", said)
        self.assertEqual(self.axe_findings("#availability"), [])
        with self.page.expect_navigation():
            self.page.locator(".avail-btn.unavailable").click()
        marks = AvailabilityMark.objects.filter(person=self.person).order_by("start")
        self.assertEqual(
            [(mark.start, mark.end, mark.state) for mark in marks],
            [(at(day, 9), at(day, 13, 30), "unavailable") for day in (8, 9, 10)],
        )

    def test_tap_start_and_end(self) -> None:
        """On a phone a finger scrolls; tapping the start and then the end marks the range (30-minute steps)."""
        self.open(self.URL)
        tap = """([day, minutes]) => {
          const column = document.querySelector(`.wk-col[data-day="${day}"]`);
          const box = column.getBoundingClientRect();
          const init = {bubbles: true, pointerId: 7, pointerType: 'touch', isPrimary: true, button: 0,
                        clientX: box.left + box.width / 2, clientY: box.top + box.height * (minutes + 7) / 1440};
          column.dispatchEvent(new PointerEvent('pointerdown', init));
          column.dispatchEvent(new PointerEvent('pointerup', init));
        }"""
        self.page.evaluate(tap, ["2027-03-12", 18 * 60])
        self.assertIn(
            "Beginn: Freitag, 12. März, 18:00 Uhr. Tippe jetzt das Ende an.", self.text_of("[data-avail-selection]")
        )
        self.page.evaluate(tap, ["2027-03-12", 23 * 60 + 40])
        self.assertEqual(self.page.input_value('input[name="start_day"]'), "2027-03-12")
        self.assertEqual(self.page.input_value('input[name="end_day"]'), "2027-03-12")
        self.assertEqual(self.page.input_value('input[name="start_time"]'), "18:00")
        self.assertEqual(self.page.input_value('input[name="end_time"]'), "00:00")  # until midnight
        self.assertIn("Gewählt: Freitag, 12. März, 18:00 bis 24:00 Uhr.", self.text_of("[data-avail-selection]"))
        self.page.fill('input[name="note"]', "Konzert")
        with self.page.expect_navigation():
            self.page.locator(".avail-btn.limited").click()
        (mark,) = AvailabilityMark.objects.filter(person=self.person)
        self.assertEqual((mark.start, mark.end, mark.state, mark.note), (at(12, 18), at(13), "limited", "Konzert"))

    def test_a_day_head_means_whole_days_again(self) -> None:
        self.open(self.URL)
        self.show_hours_from(8)
        x, y = self.point("2027-03-09", 10 * 60)
        self.page.mouse.move(x, y)
        self.page.mouse.down()
        self.page.mouse.move(x, y + 60, steps=5)
        self.page.mouse.up()
        self.assertTrue(self.page.is_checked('input[name="with_times"]'))
        self.page.locator('.wk-dayhead[data-avail-day="2027-03-11"]').click()
        self.assertEqual(self.page.locator(".wk-select").count(), 0)
        self.assertFalse(self.page.is_checked('input[name="with_times"]'))
        self.assertEqual(self.page.input_value('input[name="start_day"]'), "2027-03-11")
