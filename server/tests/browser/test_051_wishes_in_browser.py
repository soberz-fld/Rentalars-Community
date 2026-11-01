# SPDX-License-Identifier: GPL-3.0-or-later
"""In a real browser: the interface wishes that live in the page script.

* UIX-017 – on a phone the menu opens below the top bar; its first entries can be tapped.
* UIX-018 – questions before deleting are dialogs of the page; "Cancel" keeps everything.
* UIX-019 – "/" puts the cursor into the quick search.
* UIX-020 – a page that changed elsewhere loads itself again, or says so while somebody types.
* UIX-025 – "until" follows "from", and both are chosen in a calendar.
* PRJ-070 – a customer that does not exist yet is created from the project form.
"""

from __future__ import annotations

from rentalars.customers.models import Customer
from rentalars.products.models import Product
from rentalars.projects import services
from rentalars.projects.models import MaterialLine
from tests.browser.base import BrowserTestCase
from tests.helpers import ALL_RIGHTS


class ProjectFormInBrowserTests(BrowserTestCase):
    def test_until_follows_from_and_the_calendar_sets_both(self) -> None:
        """UIX-025: moving the start moves the end along; the calendar picks first and last day."""
        self.open("/projects/new/")
        start, end = self.page.locator("[name=start]"), self.page.locator("[name=end]")
        self.assertEqual((start.input_value()[11:], end.input_value()[11:]), ("12:00", "12:00"))  # PRJ-068
        start.fill("2027-05-10T12:00")
        start.dispatch_event("change")
        self.assertEqual(end.input_value(), "2027-05-11T12:00")
        self.assertEqual(end.get_attribute("min"), "2027-05-10T12:00")
        end.fill("2027-05-12T18:00")
        end.dispatch_event("change")
        for moved, expected in (("2027-05-20T08:00", "2027-05-22T14:00"), ("2027-05-01T12:00", "2027-05-03T18:00")):
            start.fill(moved)
            start.dispatch_event("change")
            self.assertEqual(end.input_value(), expected)  # the length stays: two days and six hours
        end.fill("2027-05-03T12:00")
        end.dispatch_event("change")

        self.page.locator("button.range-btn").first.click()
        picker = self.page.locator("dialog.range-picker[open]")
        picker.wait_for()
        picker.locator('button[data-day="2027-05-14"]').click()
        picker.locator('button[data-day="2027-05-16"]').click()
        self.assertIn("16.5.2027", picker.locator(".dialog-head").inner_text())
        picker.locator(".dialog-foot .btn").last.click()
        self.assertEqual((start.input_value(), end.input_value()), ("2027-05-14T12:00", "2027-05-16T12:00"))

    def test_a_new_customer_from_the_project_form(self) -> None:
        """PRJ-070: type, choose "create … as a new customer", fill in the dialog, and the field has it."""
        self.open("/projects/new/")
        field = self.page.locator("#id_customer_text")
        field.click()
        field.press_sequentially("Neue Halle GmbH", delay=10)
        self.page.locator("[role=option]", has_text="als neuen Kunden anlegen").click()
        dialog = self.page.locator("dialog#dialog[open]")
        dialog.locator("[name=name]").wait_for()
        self.assertEqual(dialog.locator("[name=name]").input_value(), "Neue Halle GmbH")
        dialog.locator("[name=city]").fill("Musterstadt")
        dialog.locator("button[type=submit]").last.click()
        self.page.wait_for_function("() => !document.querySelector('dialog#dialog[open]')")
        customer = Customer.objects.get(name="Neue Halle GmbH")
        self.assertEqual(self.page.locator("[name=customer]").input_value(), str(customer.pk))
        self.assertEqual(field.input_value(), "Neue Halle GmbH")
        # Created active, so the project can be saved with it.
        self.assertTrue(customer.is_active)


class DialogsAndSearchInBrowserTests(BrowserTestCase):
    def test_cancel_keeps_the_line(self) -> None:
        """UIX-018: the page asks in its own dialog; "Cancel" does nothing."""
        line = MaterialLine.objects.filter(project=self.project).first()
        self.open_planning()
        self.page.locator(f'tr[data-line="{line.pk}"] td.actions form button').click()
        question = self.page.locator("dialog.confirm[open]")
        question.wait_for()
        question.locator(".dialog-foot button").first.click()
        question.wait_for(state="detached")
        self.settle()
        self.assertTrue(MaterialLine.objects.filter(pk=line.pk).exists())

    def test_slash_opens_the_search(self) -> None:
        """UIX-019: the quick search on every page."""
        self.open("/products/")
        self.page.locator("h1").click()
        self.page.keyboard.press("/")
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "nav-search")
        self.page.keyboard.type("Stadtfest")
        self.page.keyboard.press("Enter")
        self.page.wait_for_url("**/search/?q=Stadtfest")


class PhoneMenuInBrowserTests(BrowserTestCase):
    viewport = {"width": 390, "height": 760}

    def test_the_first_entries_of_the_menu_can_be_tapped(self) -> None:
        """UIX-017: the top bar no longer covers the beginning of the menu."""
        self.open("/")
        self.page.locator("[data-toggle-nav]").click()
        first = self.page.locator("#sidebar .nav a").first
        first.wait_for()
        # UIX-045: the menu slides in from the right – measure once it is in place.
        self.page.wait_for_function(
            "() => Math.abs(document.querySelector('#sidebar').getBoundingClientRect().right - window.innerWidth) < 1"
        )
        box = first.bounding_box()
        on_top = self.page.evaluate(
            "([x, y]) => document.elementFromPoint(x, y).closest('a') && document.elementFromPoint(x, y).closest('a').href",
            [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2],
        )
        self.assertTrue(on_top.endswith("/projects/"), on_top)
        width = self.page.evaluate("document.documentElement.scrollWidth")
        self.assertLessEqual(width, 390)


class FollowingChangesInBrowserTests(BrowserTestCase):
    watch_changes = True

    def add_a_line_elsewhere(self) -> MaterialLine:
        product = Product.objects.filter(kind="rental", is_active=True).exclude(material_lines__project=self.project)
        return services.add_line(self.project, rights=ALL_RIGHTS, product=product.first(), quantity=1).line

    def ask_now(self) -> None:
        """The page asks every 20 seconds, and at once when it becomes visible again."""
        self.page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")

    def test_the_page_loads_itself_again(self) -> None:
        """UIX-020: a colleague adds a line; the open planning shows it without pressing reload."""
        self.open_planning()
        self.settle()
        line = self.add_a_line_elsewhere()
        with self.page.expect_navigation():
            self.ask_now()
        self.page.locator(f'tr[data-line="{line.pk}"]').wait_for()

    def test_while_typing_the_page_only_says_so(self) -> None:
        """UIX-020: nobody loses what they are typing."""
        self.open_planning()
        self.settle()
        self.page.locator("form.line-add [data-typeahead-input]").first.click()
        self.page.keyboard.type("Kab")
        self.add_a_line_elsewhere()
        self.ask_now()
        self.page.locator("#changed-note:not(.hidden)").wait_for()
        self.assertEqual(self.page.locator("form.line-add [data-typeahead-input]").first.input_value(), "Kab")
