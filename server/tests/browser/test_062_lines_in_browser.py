# SPDX-License-Identifier: GPL-3.0-or-later
"""In a real browser: choosing several lines (PRJ-082), the buttons "optional" and "Alternative" (PRJ-083), the
subrental below its line (PRJ-084) – and an accessibility check of the planning with lines chosen."""

from __future__ import annotations

from decimal import Decimal
from unittest import SkipTest

from rentalars.projects.models import LineVariant, MaterialLine
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path


class SelectionInBrowserTests(BrowserTestCase):
    """PRJ-082: tick lines, the bar appears and counts, one action changes all of them."""

    def bar(self) -> object:
        return self.page.locator("[data-selection-bar]")

    def test_choose_with_the_keyboard_and_make_optional(self) -> None:
        group = self.project.groups.get(name="Licht Front-Traverse")
        lines = list(group.lines.order_by("position", "id"))
        self.open_planning()
        self.assertFalse(self.bar().is_visible())
        first = self.page.locator(f'tr[data-line="{lines[0].pk}"] [data-select-line]')
        first.focus()
        self.page.keyboard.press("Space")
        self.assertTrue(self.bar().is_visible())
        self.assertEqual(self.text_of("[data-selection-bar] .selection-count"), "1 Position gewählt")
        # "All of this group" ticks the rest and is then ticked itself.
        all_box = self.group("Licht Front-Traverse").locator("[data-select-all]")
        self.assertTrue(all_box.evaluate("box => box.indeterminate") or len(lines) == 1)
        all_box.check()
        self.assertEqual(self.text_of("[data-selection-bar] .selection-count"), f"{len(lines)} Positionen gewählt")
        self.bar().locator("button[value=optional]").click()
        self.settle()
        self.assertEqual(
            {line.variant for line in MaterialLine.objects.filter(pk__in=[line.pk for line in lines])},
            {LineVariant.OPTIONAL},
        )
        self.assertIn("sind jetzt optional", self.text_of("#planning-messages"))
        # The parts were sent again with empty boxes: the bar is gone.
        self.assertFalse(self.bar().is_visible())

    def test_clear_and_delete_with_the_question(self) -> None:
        line = MaterialLine.objects.filter(project=self.project, product__article_number="K-005").first()
        self.open_planning()
        box = self.page.locator(f'tr[data-line="{line.pk}"] [data-select-line]')
        box.check()
        self.bar().locator("[data-selection-clear]").click()
        self.assertFalse(self.bar().is_visible())
        self.assertFalse(box.is_checked())
        box.check()
        self.bar().locator("button[value=delete]").click()
        self.confirm()
        self.settle()
        self.assertFalse(MaterialLine.objects.filter(pk=line.pk).exists())
        self.assertEqual(self.page.locator(f'tr[data-line="{line.pk}"]').count(), 0)

    def test_alternative_for_the_chosen_lines(self) -> None:
        group = self.project.groups.get(name="Licht Rear-Traverse")
        chosen = list(group.lines.order_by("position", "id"))
        target = MaterialLine.objects.filter(project=self.project, product__article_number="L-010").first()
        self.open_planning()
        for line in chosen:
            self.page.locator(f'tr[data-line="{line.pk}"] [data-select-line]').check()
        self.bar().locator("button", has_text="Als Alternative zu").click()
        dialog = self.page.locator("#dialog[open]")
        dialog.wait_for()
        dialog.locator("select[name=alternative_to]").select_option(str(target.pk))
        dialog.locator("button[type=submit]").click()
        dialog.wait_for(state="detached")
        self.settle()
        self.assertEqual(set(target.alternatives.values_list("pk", flat=True)), {line.pk for line in chosen})
        self.assertIn("Alternative zu", self.text_of(f'tr[data-line="{chosen[0].pk}"]'))


class IconsInBrowserTests(BrowserTestCase):
    """PRJ-083 and PRJ-084: the buttons of a line, and the subrental as a part of its line."""

    def test_optional_button_switches(self) -> None:
        line = MaterialLine.objects.filter(project=self.project, product__article_number="K-005").first()
        self.open_planning()
        button = self.page.locator(f'tr[data-line="{line.pk}"] button[aria-label="Optional"]')
        self.assertEqual(button.get_attribute("aria-pressed"), "false")
        button.click()
        self.settle()
        button = self.page.locator(f'tr[data-line="{line.pk}"] button[aria-label="Optional"]')
        self.assertEqual(button.get_attribute("aria-pressed"), "true")
        line.refresh_from_db()
        self.assertEqual(line.variant, LineVariant.OPTIONAL)
        button.click()
        self.settle()
        line.refresh_from_db()
        self.assertEqual(line.variant, "")

    def test_subrent_in_a_dialog_and_see_it_below_the_line(self) -> None:
        line = MaterialLine.objects.filter(project=self.project, product__article_number="L-010").first()
        line.quantity = Decimal(16)
        line.save()
        self.open_planning()
        self.page.locator(f'tr[data-line="{line.pk}"] form[hx-get*="subrent"] button').click()
        dialog = self.page.locator("#dialog[open]")
        dialog.wait_for()
        self.assertEqual(dialog.locator("input[name=unit_price]").count(), 0)
        # PRJ-101: "bestellt" needs the supplier – typed with suggestions.
        supplier = dialog.locator("[data-typeahead-input]")
        supplier.click()
        supplier.press_sequentially("Rent", delay=20)
        dialog.locator('[role=option]:has-text("Rent-All Verleih")').wait_for()
        supplier.press("Enter")
        dialog.locator("select[name=status]").select_option("ordered")
        dialog.locator("button[type=submit]").click()
        dialog.wait_for(state="detached")
        self.settle()
        sub_row = self.page.locator(f'tr[data-line="{line.pk}"] + tr.covering-row')
        self.assertIn("zugemietet", " ".join(sub_row.inner_text().split()))
        self.assertIn("bestellt", sub_row.inner_text())


class AccessibilityOfTheChoiceTests(BrowserTestCase):
    """NFA-025 with axe-core: the planning with lines chosen and the bar open, and the dialog "Alternative"."""

    bypass_csp = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = _axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()

    def run_axe(self) -> list[str]:
        self.page.add_script_tag(path=str(self.axe))
        return self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            WCAG_AA,
        )

    def test_no_findings(self) -> None:
        self.open_planning()
        self.page.locator("[data-select-line]").first.check()
        self.page.locator("[data-selection-bar]").wait_for()
        findings = [f"planning with a line chosen: {finding}" for finding in self.run_axe()]
        self.page.locator("button[aria-label='Alternative zu einer anderen Position …']").first.click()
        self.page.locator("#dialog[open]").wait_for()
        findings += [f"dialog Alternative: {finding}" for finding in self.run_axe()]
        self.assertEqual(findings, [], "\n".join(findings))
