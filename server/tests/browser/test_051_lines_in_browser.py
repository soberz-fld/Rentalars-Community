# SPDX-License-Identifier: GPL-3.0-or-later
"""In a real browser: the hints above the planning and the copy of a line (PRJ-072, PRJ-075).

The bug of PRJ-072 lived only in the browser: the form "switch to the current
scale" sat inside the hints, inherited their ``hx-select`` and put the hints
alone in place of the planning.
"""

from __future__ import annotations

from decimal import Decimal

from rentalars.masterdata.models import RentalScale
from rentalars.projects.models import MaterialLine, ProjectStatus
from tests.browser.base import BrowserTestCase


class PlanningHintsInBrowserTests(BrowserTestCase):
    """PRJ-072: after a hint is dealt with, the planning stays whole – without reloading."""

    def sections(self) -> int:
        return self.page.locator("#planning section.group").count()

    def test_switching_to_the_current_scale_keeps_the_planning(self) -> None:
        RentalScale.objects.get(is_default=True).publish(
            [(1, Decimal("1")), (2, Decimal("2"))], extra_day_increment=Decimal("1")
        )
        self.open_planning()
        sections = self.sections()
        hint = self.page.locator("#planning-notes form", has_text="Staffel")
        hint.locator("button[type=submit]").click()
        self.settle()
        self.assertEqual(self.sections(), sections)
        self.assertEqual(self.page.locator("#planning-totals").count(), 1)
        self.assertEqual(self.page.locator("#planning-notes form", has_text="Staffel").count(), 0)
        self.assertEqual(self.page.locator("#planning").count(), 1)

    def test_taking_over_new_prices_keeps_the_planning(self) -> None:
        self.project.status = ProjectStatus.INQUIRY
        self.project.save()
        line = MaterialLine.objects.filter(project=self.project, product__price__isnull=False, is_sale=False).first()
        assert line is not None
        line.product.price += Decimal("1.00")
        line.product.save()
        self.open_planning()
        sections = self.sections()
        self.page.locator(".price-hint button[name=scope]").click()
        self.confirm()  # B3: taking over new prices rewrites other records – it asks first
        self.settle()
        self.assertEqual(self.sections(), sections)
        self.assertEqual(self.page.locator(".price-hint").count(), 0)
        line.refresh_from_db()
        self.assertEqual(line.unit_price, line.product.price)


class DuplicateLineInBrowserTests(BrowserTestCase):
    """PRJ-075: the copy appears right below its line, the page stays alive."""

    def test_duplicate_a_line(self) -> None:
        line = MaterialLine.objects.get(project=self.project, product__article_number="K-005")
        self.open_planning()
        row = self.page.locator(f'tr[data-line="{line.pk}"]')
        row.locator("button[aria-label='Position duplizieren']").click()
        self.settle()
        copy = MaterialLine.objects.filter(project=self.project, product__article_number="K-005").exclude(pk=line.pk)
        self.assertEqual(copy.count(), 1)
        following = self.page.locator(f'tr[data-line="{line.pk}"] + tr')
        self.assertEqual(following.get_attribute("data-line"), str(copy.get().pk))
        self.assertEqual(self.page.locator("[hx-swap-oob]").count(), 0)
