# SPDX-License-Identifier: GPL-3.0-or-later
"""In a real browser: recording times, the stopwatch, planning crew, the dark theme.

ZEI-003 (quick, from every page, usable on a phone), ZEI-005, PRJ-019 ff., UIX-008.
"""

from __future__ import annotations

import datetime
from typing import ClassVar

from rentalars.personnel.models import JobFunction, Person
from rentalars.projects.models import CrewLine, Project
from rentalars.timetracking.models import TimeEntry
from tests.browser.base import BrowserTestCase
from tests.helpers import NOW, plan, record_time


class TimeInBrowserTestCase(BrowserTestCase):
    """The logged-in administrator is Anna Becker of the sample data, planned on a project that runs today."""

    def setUp(self) -> None:
        super().setUp()
        # The logged-in "anna" is Anna Becker of the demo data. Every account is a person
        # (AUT-026): the account's own person makes room for her.
        user_id = self.page_user_id()
        Person.objects.filter(user_id=user_id).delete()
        Person.objects.filter(last_name="Becker").update(user_id=user_id)
        self.anna = Person.objects.get(last_name="Becker")
        self.sound = JobFunction.objects.get(name="Tontechniker")  # PER-037: the job functions of the start data
        self.today = Project.objects.get(name="Lager und Werkstatt")
        self.show = Project.objects.get(name="Jazznacht")
        # A deployment that runs right now, so that the quick entry has a best guess (ZEI-006).
        Project.objects.filter(pk=self.show.pk).update(
            start=NOW - datetime.timedelta(hours=2), end=NOW + datetime.timedelta(hours=10)
        )
        self.show.refresh_from_db()
        self.show.crew_lines.all().delete()
        plan(self.show, self.sound, self.anna)

    def page_user_id(self) -> int:
        from rentalars.accounts.models import User

        return User.objects.get(username="anna").pk

    def dialog(self) -> object:
        return self.page.locator("#dialog[open]")

    def record(self, begin: str, end: str) -> None:
        """Fill begin and end in the open quick entry and save."""
        self.page.fill("#dialog [name=begin]", begin)
        self.page.fill("#dialog [name=end]", end)
        self.page.locator("#dialog button[type=submit]", has_text="Zeit speichern").click()
        self.settle()


class QuickEntryInBrowserTests(TimeInBrowserTestCase):
    """Acceptance scenario 5 with scripts running."""

    def test_record_from_the_planning_page_without_leaving_it(self) -> None:
        self.open_planning()
        address = self.page.url
        self.page.locator(".sidebar-action a").click()
        self.dialog().wait_for()
        # Today's project and its job function are prefilled (ZEI-006).
        self.assertEqual(self.page.input_value("#dialog [name=project]"), str(self.show.pk))
        self.assertEqual(self.page.input_value("#dialog [name=job_function]"), str(self.sound.pk))

        self.record("06:00", "08:00")
        self.assertIn("Zeit erfasst", self.text_of("#dialog"))
        self.assertIn("2 Std.", self.text_of("#dialog"))
        self.assertEqual(self.page.url, address)  # still the same page
        entry = TimeEntry.objects.get(project=self.show)
        self.assertEqual((entry.person, float(entry.hours), entry.status), (self.anna, 2.0, "submitted"))

        # "Another time" brings the form back in the same dialog; an overlap is refused there.
        self.page.locator("#dialog a", has_text="Weitere Zeit").click()
        self.settle()
        self.record("07:30", "07:50")
        self.assertIn("überschneidet sich", self.text_of("#dialog"))
        self.assertEqual(self.page.input_value("#dialog [name=begin]"), "07:30")
        self.assertEqual(TimeEntry.objects.filter(project=self.show).count(), 1)

        self.page.locator("#dialog button", has_text="Abbrechen").click()
        self.assertEqual(self.page.locator("#dialog[open]").count(), 0)
        self.assertEqual(self.page.url, address)

    def test_another_project_brings_its_own_job_functions_and_keeps_what_was_typed(self) -> None:
        """ZEI-007."""
        self.open("/")
        self.page.locator(".sidebar-action a").click()
        self.dialog().wait_for()
        self.page.fill("#dialog [name=begin]", "06:00")
        self.page.select_option("#dialog [name=project]", str(self.today.pk))
        self.settle()
        self.assertEqual(self.page.input_value("#dialog [name=project]"), str(self.today.pk))
        self.assertEqual(self.page.input_value("#dialog [name=begin]"), "06:00")
        offered = self.page.locator("#dialog [name=job_function] option").all_inner_texts()
        self.assertEqual(offered, ["Lager", "Stagehand", "Tontechniker"])

    def test_my_times_refresh_themselves_after_recording(self) -> None:
        self.open("/times/")
        self.assertIn("Keine Zeiten in dieser Woche", self.text_of("#my-times"))
        self.page.locator(".page-head a", has_text="Zeit erfassen").click()
        self.dialog().wait_for()
        self.record("06:00", "08:00")
        self.page.locator("#dialog button", has_text="Fertig").click()
        self.settle()
        times = self.text_of("#my-times")
        self.assertIn("06:00 – 08:00", times)
        self.assertIn("Jazznacht", times)
        self.assertIn("eingereicht", times)

    def test_the_report_loads_again_after_a_correction_in_the_dialog(self) -> None:
        entry = record_time(self.anna, self.show, self.sound, NOW - datetime.timedelta(hours=2), NOW, submit=True)
        self.open("/times/report/?since=2027-03-01")
        self.assertIn("06:00 – 08:00", self.text_of("main"))
        self.page.locator(f'button[hx-get="/times/{entry.pk}/"]').click()
        self.dialog().wait_for()
        self.page.fill("#dialog [name=end]", "07:00")
        with self.page.expect_navigation():
            self.page.locator("#dialog button[type=submit]").click()
        self.assertIn("06:00 – 07:00", self.text_of("main"))

    def test_the_stopwatch_counts_and_stops(self) -> None:
        """ZEI-005."""
        self.open("/")
        self.page.locator(".sidebar-action a").click()
        self.dialog().wait_for()
        self.page.locator("#dialog button", has_text="Stoppuhr starten").click()
        self.settle()
        self.assertIn("Stoppuhr läuft", self.text_of("#dialog"))
        entry = TimeEntry.objects.get(end__isnull=True)
        self.assertEqual(entry.person, self.anna)
        # The display counts up by itself: hours, minutes and seconds since the start.
        self.page.wait_for_function(
            "() => /^\\d+:\\d\\d:\\d\\d$/.test(document.querySelector('#dialog [data-timer-since]').textContent)"
        )

        TimeEntry.objects.filter(pk=entry.pk).update(start=NOW - datetime.timedelta(hours=1))
        self.page.locator("#dialog button", has_text="Stoppen").click()
        self.settle()
        self.assertIn("Zeit erfasst", self.text_of("#dialog"))
        entry.refresh_from_db()
        self.assertEqual(float(entry.hours), 1.0)


class QuickEntryOnAPhoneTests(TimeInBrowserTestCase):
    """ZEI-003, UIX-001: the same on a screen 360 pixels wide."""

    viewport: ClassVar[dict[str, int]] = {"width": 360, "height": 740}

    def test_the_clock_in_the_top_bar_opens_the_quick_entry(self) -> None:
        self.open(f"/projects/{self.show.pk}/deployment/")
        self.page.locator('.topbar-actions a[aria-label="Zeit erfassen"]').click()
        self.dialog().wait_for()

        # The dialog fits the screen, and begin and end stand side by side.
        box = self.page.locator("#dialog").bounding_box()
        self.assertGreaterEqual(box["x"], 0)
        self.assertLessEqual(box["x"] + box["width"], 360)
        begin = self.page.locator("#dialog [name=begin]").bounding_box()
        end = self.page.locator("#dialog [name=end]").bounding_box()
        self.assertEqual(round(begin["y"]), round(end["y"]))
        self.assertLess(begin["x"] + begin["width"], end["x"] + 1)
        self.assertEqual(self.page.evaluate("document.documentElement.scrollWidth"), 360)

        self.record("06:00", "08:00")
        self.assertIn("Zeit erfasst", self.text_of("#dialog"))
        self.page.locator("#dialog button", has_text="Fertig").click()
        # The deployment view lists own times and loads again once the dialog is closed.
        self.page.wait_for_function("() => document.body.innerText.includes('06:00 – 08:00')")

    def test_without_the_dialog_the_quick_entry_is_a_page_that_fits_too(self) -> None:
        self.open("/times/quick/")
        self.assertEqual(self.page.evaluate("document.documentElement.scrollWidth"), 360)
        self.page.fill("[name=begin]", "06:00")
        self.page.fill("[name=end]", "07:00")
        self.page.locator("button[type=submit]", has_text="Zeit speichern").click()
        self.settle()
        self.assertIn("Zeit erfasst", self.text_of("main"))
        # "Done" leads to my times, because there is no dialog to close.
        self.page.locator("button", has_text="Fertig").click()
        self.page.wait_for_url("**/times/")


class CrewInBrowserTests(BrowserTestCase):
    """PRJ-019 ff.: planning people on the planning page."""

    def test_plan_fill_and_edit_a_crew_line(self) -> None:
        self.open_planning()
        block = self.page.locator("#planning-crew")
        before = block.locator("tbody tr").count()
        net_before = self.text_of("#planning-totals")

        hand = JobFunction.objects.get(name="Stagehand")
        block.locator("form.crew-add [name=job_function]").select_option(str(hand.pk))
        block.locator("form.crew-add button[type=submit]").click()
        self.settle()
        self.assertEqual(self.page.locator("#planning-crew tbody tr").count(), before + 1)
        self.assertNotEqual(self.text_of("#planning-totals"), net_before)  # the totals followed

        line = CrewLine.objects.filter(project=self.project, person__isnull=True).order_by("-pk").first()
        row = self.page.locator(f'#planning-crew tr[data-crew-line="{line.pk}"]')
        row.locator("button[aria-label='Personalposition bearbeiten']").click()
        self.page.locator("#dialog[open]").wait_for()
        # From and until side by side (UIX-014).
        start = self.page.locator("#dialog [name=start]").bounding_box()
        end = self.page.locator("#dialog [name=end]").bounding_box()
        self.assertEqual(round(start["y"]), round(end["y"]))

        lea = Person.objects.get(last_name="Vogel")
        self.page.select_option("#dialog [name=person]", str(lea.pk))
        self.page.fill("#dialog [name=meeting_point]", "Bühneneingang")
        self.page.locator("#dialog button[type=submit]").click()
        self.settle()
        self.assertEqual(self.page.locator("#dialog[open]").count(), 0)
        line.refresh_from_db()
        self.assertEqual((line.person, line.meeting_point), (lea, "Bühneneingang"))
        text = self.text_of(f'#planning-crew tr[data-crew-line="{line.pk}"]')
        self.assertIn("Lea Vogel", text)
        self.assertIn("Bühneneingang", text)
        # Lea is already planned at the same time in this project: the planner is told (PRJ-022).
        self.assertIn("doppelt eingeplant", text)


class DarkThemeInBrowserTests(BrowserTestCase):
    """UIX-008: dark, in the house colours, and still readable."""

    @staticmethod
    def luminance(colour: str) -> float:
        channels = [int(part) / 255 for part in colour[colour.index("(") + 1 : colour.index(")")].split(",")[:3]]
        linear = [value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    def contrast(self, first: str, second: str) -> float:
        lighter, darker = sorted((self.luminance(first), self.luminance(second)), reverse=True)
        return (lighter + 0.05) / (darker + 0.05)

    def style(self, selector: str, name: str) -> str:
        return str(self.page.evaluate("([s, n]) => getComputedStyle(document.querySelector(s))[n]", [selector, name]))

    def test_pages_are_dark_with_the_house_orange_as_the_one_accent(self) -> None:
        self.open_planning()
        self.assertEqual(self.page.get_attribute("html", "data-theme"), "dark")
        background = self.style("body", "backgroundColor")
        self.assertLess(self.luminance(background), 0.02)
        self.assertEqual(self.style(".sidebar-action .btn", "backgroundColor"), "rgb(238, 89, 31)")  # #EE591F
        self.assertEqual(self.style("body", "color"), "rgb(238, 238, 238)")  # #EEEEEE

    def test_text_keeps_enough_contrast(self) -> None:
        """NFA-023: 4.5 to 1 for running text, measured on what the browser really paints."""
        self.open_planning()
        pairs = {
            "text on the page": ("body", "body"),
            "text in a panel": ("section.group", "section.group"),
            "muted text": (".muted", "section.group"),
            "label on the orange button": (".sidebar-action .btn", ".sidebar-action .btn"),
            "navigation": (".nav a", ".sidebar"),
            "table head": (".table th", ".table thead tr"),
        }
        for name, (text, surface) in pairs.items():
            colour = self.style(text, "color")
            behind = self.style(surface, "backgroundColor")
            if behind in ("rgba(0, 0, 0, 0)", "transparent"):
                behind = self.style("body", "backgroundColor")
            self.assertGreaterEqual(self.contrast(colour, behind), 4.5, f"{name}: {colour} on {behind}")

    def test_quantity_fields_do_not_offer_earlier_entries(self) -> None:
        """UIX-014."""
        self.open_planning()
        for field in self.page.locator("form.line-add input.qty").all():
            self.assertEqual(field.get_attribute("autocomplete"), "off")
