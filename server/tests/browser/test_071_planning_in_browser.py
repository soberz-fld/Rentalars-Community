# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: bars that stand out from the background and labels that end at their bar (VFG-030), the
timeline of a project on the tab "Zeitplanung" (PRJ-103), filters folded on a wide screen (UIX-038) – with
axe-core on these pages."""

from __future__ import annotations

from unittest import SkipTest

from rentalars.projects import course
from rentalars.projects.models import CrewLine, Project, ProjectStatus
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.helpers import at, make_person, make_project, plan

#: Every bar of the timelines within a selector: its frame against the first opaque background behind it
#: (WCAG 1.4.11 – contrast of graphical objects), and whether its text is cut at its end.
BARS = """(selector) => {
  const rgb = (text) => {
    const numbers = (text.match(/[\\d.]+/g) || []).map(Number);
    if (text.startsWith('color(')) { return [numbers[0] * 255, numbers[1] * 255, numbers[2] * 255, numbers.length > 3 ? numbers[3] : 1]; }
    return [numbers[0], numbers[1], numbers[2], numbers.length > 3 ? numbers[3] : 1];
  };
  const luminance = ([r, g, b]) => {
    const [R, G, B] = [r, g, b].map((v) => { v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
    return 0.2126 * R + 0.7152 * G + 0.0722 * B;
  };
  const behind = (element) => {
    for (let node = element.parentElement; node; node = node.parentElement) {
      const colour = rgb(getComputedStyle(node).backgroundColor);
      if (colour[3] > 0.99) { return colour; }
    }
    return [255, 255, 255, 1];
  };
  // The width the label would need, measured on a copy outside the bar: the bar itself cuts it.
  const textWidth = (bar) => {
    const probe = document.createElement('span');
    probe.style.cssText = 'position:absolute;visibility:hidden;white-space:nowrap';
    probe.style.font = getComputedStyle(bar).font;
    probe.textContent = bar.textContent.trim();
    document.body.append(probe);
    const width = probe.getBoundingClientRect().width + parseFloat(getComputedStyle(bar).paddingLeft);
    probe.remove();
    return width;
  };
  return [...document.querySelectorAll(selector)].map((bar) => {
    const style = getComputedStyle(bar);
    const edge = luminance(rgb(style.borderTopColor)), ground = luminance(behind(bar));
    const rect = bar.getBoundingClientRect();
    const right = document.elementFromPoint(rect.right + 3, rect.top + rect.height / 2);
    return {
      bar: bar.className + ' "' + bar.textContent.trim() + '"',
      ratio: (Math.max(edge, ground) + 0.05) / (Math.min(edge, ground) + 0.05),
      opacity: Number(style.opacity),
      frame: style.borderTopStyle !== 'none' && parseFloat(style.borderTopWidth) >= 1
        && style.borderRightStyle !== 'none' && style.borderBottomStyle !== 'none',
      overflows: textWidth(bar) > bar.clientWidth + 1,
      cut: style.overflowX === 'clip' && style.textOverflow === 'ellipsis',
      titled: (bar.getAttribute('title') || '').includes(bar.textContent.trim()),
      beyond: right ? right === bar || bar.contains(right) : false,
      visible: rect.width > 0 && rect.right <= window.innerWidth - 4,
    };
  });
}"""


class AxeMixin:
    """axe-core on the page as it is, or on a part of it."""

    bypass_csp = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = _axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()  # type: ignore[misc]

    def axe_findings(self, within: str = "") -> list[str]:
        page = self.page  # type: ignore[attr-defined]
        page.wait_for_load_state("networkidle")
        if not page.evaluate("() => typeof axe !== 'undefined'"):
            page.add_script_tag(path=str(self.axe))
        return page.evaluate(
            "async ([tags, within]) => (await axe.run(within ? {include: [[within]]} : document,"
            " {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            [WCAG_AA, within],
        )


class BarsOnTheBackgroundTests(AxeMixin, BrowserTestCase):
    """VFG-030: a bar of every status can be told from the background, in both themes; no label runs over."""

    def setUp(self) -> None:
        super().setUp()
        self.anna = make_person("Anna Krause", rates={"Lichttechnik": "35.00"})
        statuses = [
            ProjectStatus.INQUIRY,
            ProjectStatus.OPTION,
            ProjectStatus.CONFIRMED_OPEN,
            ProjectStatus.CONFIRMED,
            ProjectStatus.OUT,
            ProjectStatus.RETURNED,
            ProjectStatus.CLOSED,
            ProjectStatus.CANCELLED,
        ]
        for index, status in enumerate(statuses):
            start = at(9, 6 + index * 2)
            project = make_project(
                f"Sehr lange Bezeichnung einer Veranstaltung Nummer {index}", start=start, end=at(9, 9 + index * 2)
            )
            line = plan(project, "Lichttechnik", self.anna, start=start, end=at(9, 9 + index * 2))
            Project.objects.filter(pk=project.pk).update(status=status)
            if status == ProjectStatus.OPTION:
                CrewLine.objects.filter(pk=line.pk).update(request_status="requested")
        # A long one that begins before the days shown and lasts beyond them.
        make_project("Lager und Werkstatt", start=at(8, 8), end=at(12, 18), status=ProjectStatus.INQUIRY)

    def check(self, selector: str, label: str) -> None:
        for theme in ("dark", "light"):
            self.page.evaluate(f"() => {{ document.documentElement.dataset.theme = '{theme}'; }}")
            bars = self.page.evaluate(BARS, selector)
            self.assertTrue(bars, f"{label}: no bars")
            for bar in bars:
                with self.subTest(page=label, theme=theme, bar=bar["bar"]):
                    self.assertTrue(bar["frame"], bar)
                    self.assertGreaterEqual(round(bar["ratio"], 2), 3.0, bar)
                    self.assertEqual(bar["opacity"], 1)
                    self.assertTrue(bar["cut"], bar)
                    if bar["overflows"]:
                        self.assertTrue(bar["titled"], bar)
                        if bar["visible"]:
                            self.assertFalse(bar["beyond"], bar)
            self.assertTrue(any(bar["overflows"] for bar in bars), f"{label}: no long label to try")

    def test_timeline_and_personnel_plan_in_hours_and_weeks(self) -> None:
        self.open("/schedule/timeline/?days=2&from=2027-03-09&all=1")
        self.check(".panel.timeline .tl-row .tl-bar", "timeline, days")
        self.assertEqual(self.axe_findings(".panel.timeline"), [])
        self.open("/schedule/timeline/?weeks=1&from=2027-03-08&all=1")
        self.check(".panel.timeline .tl-row .tl-bar", "timeline, weeks")
        self.open("/schedule/personnel/?days=2&from=2027-03-09")
        self.check(".personnel-plan .tl-deploy .tl-bar", "personnel plan")
        self.assertEqual(self.axe_findings(".personnel-plan"), [])

    def test_the_timelines_of_a_person_and_of_a_product(self) -> None:
        self.open(f"/personnel/people/{self.anna.pk}/timeline/?from=2027-03-08&weeks=1")
        self.check(".panel.timeline .tl-row .tl-bar", "person")
        self.open("/products/L-010/timeline/?from=2027-03-08&weeks=2")
        bars = self.page.evaluate(BARS, ".panel.timeline .tl-row .tl-bar")
        for bar in bars:
            with self.subTest(bar=bar["bar"]):
                self.assertGreaterEqual(round(bar["ratio"], 2), 3.0, bar)
                self.assertTrue(bar["cut"], bar)

    def test_the_text_of_a_bar_begun_before_the_view_stays_beside_the_names(self) -> None:
        """clip, not hidden: the text of a cut bar still sticks next to the names when the bar began earlier."""
        self.open("/schedule/timeline/?days=1&from=2027-03-10&all=1")
        found = self.page.evaluate(
            """() => {
              const panel = document.querySelector('[data-tl-zoom]');
              const names = panel.querySelector('.tl-label').getBoundingClientRect().right;
              const bar = [...panel.querySelectorAll('.tl-row .tl-bar')].find((b) => b.getBoundingClientRect().left < names - 20
                && b.getBoundingClientRect().right > names + 80);
              return bar ? {names, text: bar.querySelector('.tl-text').getBoundingClientRect().left} : null;
            }"""
        )
        self.assertIsNotNone(found)
        self.assertGreaterEqual(found["text"], found["names"])


class ProjectTimelineTests(AxeMixin, BrowserTestCase):
    """PRJ-103: the timeline on the tab "Zeitplanung" – scrolls in hours, loads the next span, passes axe-core."""

    def setUp(self) -> None:
        super().setUp()
        course.add_phase(
            self.project,
            kind="rehearsal",
            title="Probe mit Band und Technik",
            start=self.project.start,
            end=self.project.start + (self.project.end - self.project.start) / 6,
        )
        self.url = f"/projects/{self.project.pk}/course/"

    def test_the_timeline_of_the_sample_project(self) -> None:
        self.open(self.url)
        timeline = self.page.locator(".course-timeline")
        labels = self.page.locator(".project-timeline .tl-label:not(.head)").all_inner_texts()
        for label in ("Mietzeitraum", "Packen", "Aufbau", "Probe mit Band und Technik", "Anna Becker", "Lea Vogel"):
            self.assertTrue(any(label in text for text in labels), (label, labels))
        self.assertTrue(any(text.startswith("Stagehand") and "offen" in text for text in labels), labels)
        # Opened on the rental period, the hours before and after it to scroll to.
        self.assertGreater(self.page.evaluate("document.querySelector('[data-tl-zoom]').scrollLeft"), 0)
        self.assertIn("Stagehand", timeline.locator(".tl-bar.crew").first.get_attribute("title"))
        bars = self.page.evaluate(BARS, ".project-timeline .tl-row .tl-bar")
        self.assertTrue(all(bar["cut"] and round(bar["ratio"], 2) >= 3 for bar in bars), bars)
        self.assertEqual(self.axe_findings(), [])
        self.page.evaluate("() => { document.documentElement.dataset.theme = 'light'; }")
        self.page.wait_for_timeout(400)  # the buttons change their colours with a short transition
        bars = self.page.evaluate(BARS, ".project-timeline .tl-row .tl-bar")
        self.assertTrue(all(round(bar["ratio"], 2) >= 3 for bar in bars), bars)
        self.assertEqual(self.axe_findings(".course-timeline"), [])

    def test_scrolling_to_the_end_loads_the_next_days(self) -> None:
        self.open(self.url)
        before = self.text_of("[data-tl-range]")
        self.page.evaluate(
            "() => { const panel = document.querySelector('[data-tl-zoom]'); panel.scrollLeft = panel.scrollWidth; }"
        )
        self.page.wait_for_url("**/course/?from=*")
        self.page.wait_for_function(f"document.querySelector('[data-tl-range]').textContent.trim() !== {before!r}")
        # Still days in hours, the phases and the crew still there.
        self.assertEqual(self.page.locator("[data-tl-zoom]").count(), 1)
        self.assertGreater(self.page.locator(".project-timeline .tl-label.phase").count(), 3)
        self.page.locator(".tl-zoom a", has_text="Wochen").click()
        self.page.wait_for_url("**/course/?*weeks=*")
        self.assertEqual(self.page.locator("[data-tl-zoom]").count(), 0)
        self.assertTrue(self.page.is_visible("#f-weeks"))
        self.assertGreater(self.page.locator(".project-timeline .tl-label.person").count(), 2)

    def test_on_a_phone(self) -> None:
        self.page.set_viewport_size({"width": 360, "height": 740})
        self.open(self.url)
        self.assertLessEqual(self.page.evaluate("document.scrollingElement.scrollWidth"), 360)
        self.assertEqual(self.axe_findings(".course-timeline"), [])


class FiltersFoldedOnAWideScreenTests(AxeMixin, BrowserTestCase):
    """UIX-038: the filters of a list start folded on a wide screen too."""

    def test_folded_at_first(self) -> None:
        for path in ("/products/", "/material/", "/personnel/"):
            with self.subTest(path=path):
                self.open(path)
                toggle = self.page.locator("[data-filter-toggle]")
                self.assertEqual(toggle.get_attribute("aria-expanded"), "false")
                panel = toggle.get_attribute("aria-controls")
                self.assertFalse(
                    self.page.locator(f"#{panel} select, #{panel} input:not([type=hidden])").first.is_visible()
                )
                self.assertEqual(self.axe_findings(), [])
