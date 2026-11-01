# SPDX-License-Identifier: GPL-3.0-or-later
"""In a real browser: the planning page of a project (PRJ-010 ff., UIX-009)."""

from __future__ import annotations

from decimal import Decimal

from rentalars.projects.models import Group, MaterialLine
from tests.browser.base import BrowserTestCase


class PlanningInBrowserTests(BrowserTestCase):
    """Lines and groups change on the page without loading it again."""

    def test_adding_a_line_replaces_only_the_touched_parts(self) -> None:
        """NFA-013: the answer is a patch; everything else on the page stays as it is."""
        self.open_planning()
        gross_before = self.text_of("#planning-totals tr.grand")
        # A mark on a group the change does not touch: it must survive.
        self.page.evaluate("document.querySelector('section.is-optional').dataset.mark = 'still here'")
        front = self.group("Licht Front-Traverse")

        self.choose_product(front, "R-010")
        front.locator("form.line-add input[name=quantity]").fill("2")
        front.locator("form.line-add button[type=submit]").click()
        self.settle()

        self.assertEqual(front.locator("tr[data-line]").count(), 3)
        self.assertNotEqual(self.text_of("#planning-totals tr.grand"), gross_before)
        self.assertEqual(self.page.evaluate("document.querySelector('section.is-optional').dataset.mark"), "still here")
        # The replaced group is fully alive again: search field, sorting, no leftovers of the patch.
        self.assertEqual(front.locator("[data-typeahead-input]").input_value(), "")
        self.assertEqual(front.locator("[data-typeahead][data-ready]").count(), 1)
        self.assertEqual(front.locator("tbody[data-sortable][data-ready]").count(), 1)
        self.assertEqual(self.page.locator("[hx-swap-oob]").count(), 0)
        # The other group with the same trusses was refreshed too: 6 + 2 are now planned "elsewhere".
        rear = self.group("Licht Rear-Traverse")
        self.assertIn("frei", " ".join(rear.locator("tr[data-line]").nth(1).inner_text().split()))

    def test_line_dialog_shows_availability_while_typing_saves_and_closes(self) -> None:
        """PRJ-012, PRJ-013."""
        line = MaterialLine.objects.get(project=self.project, product__article_number="K-005")
        self.open_planning()
        row = self.page.locator(f'tr[data-line="{line.pk}"]')

        row.locator("button[aria-label='Position bearbeiten']").click()
        dialog = self.page.locator("dialog[open]")
        dialog.wait_for()
        # The dialog holds the form – and the availability inside it, not instead of it.
        dialog.locator("#line-availability .avail").wait_for()
        self.assertIn("frei", dialog.locator("#line-availability").inner_text())
        self.assertEqual(dialog.locator("[name=quantity]").count(), 1)

        dialog.locator("[name=quantity]").fill("26")
        dialog.locator("#line-availability .avail.short").wait_for()
        self.assertIn("6", dialog.locator("#line-availability .avail").inner_text())
        # Leaving the field asks for the availability once more. The test server shares one SQLite connection
        # between its threads, so that request must not meet the saving one (a real server has a connection each).
        dialog.locator("[name=quantity]").blur()
        self.page.wait_for_load_state("networkidle")

        dialog.locator("button[type=submit]").click()
        self.settle()
        # The answer to the last keystroke may still be on its way when the form is sent; wait for the close.
        self.page.wait_for_function("() => !document.querySelector('dialog[open]')", timeout=5000)
        self.settle()

        self.assertEqual(self.page.locator("dialog[open]").count(), 0)
        self.assertIn("Fehlmenge 6", " ".join(row.inner_text().split()))
        self.assertIn("Es fehlen 6 Stück", self.text_of("#planning-notes"))
        line.refresh_from_db()
        self.assertEqual(line.quantity, 26)

        # PRJ-054: take the suggested subrental; the shortage is covered. The suggestion
        # asks in a dialog (PRJ-084), and the subrental is shown as a part of the line, in the row below it.
        row.locator("form button", has_text="zumieten").click()
        dialog.wait_for()
        dialog.locator("button[type=submit]").click()
        self.page.wait_for_function("() => !document.querySelector('dialog[open]')", timeout=5000)
        self.settle()
        part = self.page.locator(f'tr[data-line="{line.pk}"] + tr.covering-row')
        self.assertIn("davon 6 zugemietet", " ".join(part.inner_text().split()))
        self.assertNotIn("Es fehlen", self.text_of("#planning-notes"))

    def test_hints_are_fetched_again_when_a_second_change_overtakes_the_first(self) -> None:
        """PRJ-013: the hint about missing pieces must not stop at the state between two changes.

        The hints are fetched after every change. A second change can be
        announced while that fetch is under way. htmx then queues one more
        fetch – and drops it if the block has meanwhile been replaced by the
        first answer. The block therefore exchanges only its content (see
        _planning_notes.html); with a block that replaces itself this test
        sees one fetch instead of two.
        """
        line = MaterialLine.objects.get(project=self.project, product__article_number="K-005")
        self.open_planning()
        self.settle()
        self.assertNotIn("Es fehlen", self.text_of("#planning-notes"))
        MaterialLine.objects.filter(pk=line.pk).update(quantity=26)
        fetches: list[str] = []
        self.page.on(
            "request", lambda request: fetches.append(request.url) if "/planning/notes/" in request.url else None
        )

        # Two changes announced in the same instant, three later while the answers come in.
        announce = "() => document.body.dispatchEvent(new Event('planningChanged'))"
        self.page.evaluate(f"() => {{ ({announce})(); ({announce})(); }}")
        self.settle()

        self.assertEqual(len(fetches), 2)
        self.assertIn("Es fehlen 6 Stück", self.text_of("#planning-notes"))
        # The block is still the one that listens: a later change reaches it too.
        MaterialLine.objects.filter(pk=line.pk).update(quantity=20)
        self.page.evaluate(announce)
        self.settle()
        self.assertEqual(len(fetches), 3)
        self.assertNotIn("Es fehlen", self.text_of("#planning-notes"))

    def test_line_dialog_with_an_error_stays_open(self) -> None:
        line = MaterialLine.objects.get(project=self.project, product__article_number="K-005")
        self.open_planning()
        self.page.locator(f'tr[data-line="{line.pk}"] button[aria-label="Position bearbeiten"]').click()
        dialog = self.page.locator("dialog[open]")
        dialog.wait_for()

        dialog.locator("[name=end]").fill("2020-01-01T08:00")
        dialog.locator("button[type=submit]").click()
        self.settle()

        self.assertEqual(self.page.locator("dialog[open]").count(), 1)
        self.assertEqual(dialog.locator(".errorlist, .field-error, .message.error").count() > 0, True)
        dialog.locator("[data-close-dialog]").first.click()
        self.assertEqual(self.page.locator("dialog[open]").count(), 0)

    def test_deleting_a_line(self) -> None:
        line = MaterialLine.objects.get(project=self.project, product__article_number="T-030")
        self.open_planning()
        self.page.locator(f'tr[data-line="{line.pk}"] td.actions form button').click()
        self.confirm()  # the page asks; the test says yes
        self.settle()
        self.assertEqual(self.page.locator(f'tr[data-line="{line.pk}"]').count(), 0)
        self.assertFalse(MaterialLine.objects.filter(pk=line.pk).exists())

    def test_groups_are_added_edited_copied_and_deleted(self) -> None:
        """PRJ-014, PRJ-039, PRJ-041."""
        self.open_planning()
        sections = self.page.locator("#planning section.group")
        count = sections.count()

        self.page.fill("input.group-name", "Backline")
        self.page.locator("form:has(input.group-name) button[type=submit]").click()
        self.settle()
        self.assertEqual(sections.count(), count + 1)
        backline = self.group("Backline")

        self.choose_product(backline, "K-020")
        backline.locator("form.line-add button[type=submit]").click()
        self.settle()
        self.assertEqual(backline.locator("tr[data-line]").count(), 1)

        backline.locator(".group-head button[aria-label='Teilgruppe bearbeiten']").click()
        dialog = self.page.locator("dialog[open]")
        dialog.wait_for()
        dialog.locator("[name=discount_percent]").fill("10")
        dialog.locator("button[type=submit]").click()
        self.settle()
        self.assertEqual(self.page.locator("dialog[open]").count(), 0)
        self.assertIn("Gruppenrabatt", backline.inner_text())
        self.assertEqual(Group.objects.get(name="Backline").discount_percent, Decimal("10"))

        backline.locator(".group-head form").first.locator("button").click()  # copy
        self.settle()
        self.assertEqual(sections.count(), count + 2)

        self.group("Backline").last.locator(".group-head form").last.locator("button").click()  # delete
        self.confirm()
        self.settle()
        self.assertEqual(sections.count(), count + 1)

    def test_line_without_product(self) -> None:
        """PRJ-017."""
        self.open_planning()
        self.page.locator("button", has_text="Position ohne Produkt").click()
        dialog = self.page.locator("dialog[open]")
        dialog.wait_for()
        dialog.locator("[name=title]").fill("Bühnenpodest vom Veranstalter")
        dialog.locator("[name=quantity]").fill("4")
        dialog.locator("[name=unit_price]").fill("12,50")
        dialog.locator("button[type=submit]").click()
        self.settle()
        # The answer to the last keystroke may still be on its way when the form is sent; wait for the close.
        self.page.wait_for_function("() => !document.querySelector('dialog[open]')", timeout=5000)
        self.settle()

        self.assertEqual(self.page.locator("dialog[open]").count(), 0)
        self.assertIn("Bühnenpodest vom Veranstalter", self.page.inner_text("#group-none"))
        self.assertIn("50,00", self.page.inner_text("#group-none"))

    def test_dragging_a_line_into_another_group(self) -> None:
        """PRJ-014: the order is stored and survives a reload."""
        line = MaterialLine.objects.get(project=self.project, product__article_number="T-500")
        target = Group.objects.get(project=self.project, name="Licht Rear-Traverse")
        self.open_planning()
        self.settle()
        handle = self.page.locator(f'tr[data-line="{line.pk}"] td.drag')
        destination = self.page.locator(f"#group-{target.pk} tr[data-line]").first

        # Both ends of the way must be on the screen: a pointer outside the
        # window drags nothing. Put the middle between them in the middle.
        self.page.evaluate(
            """([from, to]) => {
                const a = document.querySelector(from).getBoundingClientRect();
                const b = document.querySelector(to).getBoundingClientRect();
                const middle = (Math.min(a.top, b.top) + Math.max(a.bottom, b.bottom)) / 2;
                window.scrollBy(0, middle - window.innerHeight / 2);
            }""",
            [f'tr[data-line="{line.pk}"] td.drag', f"#group-{target.pk} tr[data-line]"],
        )
        start = handle.bounding_box()
        end = destination.bounding_box()
        assert start and end
        height = self.page.viewport_size["height"]
        for box in (start, end):
            self.assertTrue(
                box["y"] >= 0 and box["y"] + box["height"] <= height, "the sample project outgrew the window"
            )
        self.page.mouse.move(start["x"] + start["width"] / 2, start["y"] + start["height"] / 2)
        self.page.mouse.down()
        self.page.mouse.move(end["x"] + 60, end["y"] + end["height"] / 2, steps=25)
        # The browser reports a drag in its own time. Letting go before the row
        # has arrived would test the speed of the test, not the sorting.
        in_target = f'#group-{target.pk} tr[data-line="{line.pk}"]'
        for nudge in range(40):
            if self.page.locator(in_target).count():
                break
            self.page.mouse.move(end["x"] + 60 + nudge % 2, end["y"] + end["height"] / 2 + nudge % 3)
            self.page.wait_for_timeout(50)
        self.assertEqual(self.page.locator(in_target).count(), 1, "the row did not follow the pointer")
        with self.page.expect_response(lambda response: "/arrange" in response.url):
            self.page.mouse.up()
        self.settle()

        line.refresh_from_db()
        self.assertEqual(line.group, target)
        self.open_planning()
        self.assertEqual(self.page.locator(f'#group-{target.pk} tr[data-line="{line.pk}"]').count(), 1)

    def test_moving_a_line_with_the_keyboard(self) -> None:
        """NFA-025: the handle is a button; the arrow keys move the line, and the focus stays on it."""
        self.open_planning()
        self.settle()
        body = self.page.locator("tbody[data-sortable]").filter(has=self.page.locator("tr[data-line]").nth(1)).first
        rows = body.locator("tr[data-line]")
        first, second = rows.nth(0).get_attribute("data-line"), rows.nth(1).get_attribute("data-line")
        rows.nth(1).locator(".drag-handle").focus()
        with self.page.expect_response(lambda response: "/arrange" in response.url):
            self.page.keyboard.press("ArrowUp")
        self.settle()
        self.page.wait_for_function(
            "(line) => document.activeElement && document.activeElement.closest('tr[data-line]')"
            " && document.activeElement.closest('tr[data-line]').dataset.line === line",
            arg=second,
            timeout=5000,
        )
        moved = MaterialLine.objects.get(pk=int(second))
        stayed = MaterialLine.objects.get(pk=int(first))
        self.assertLess(moved.position, stayed.position)

    def test_status_list_and_tabs(self) -> None:
        self.open_planning()
        # PRJ-078: the status is a list in the head of the project, not a row of buttons.
        self.assertIn("Unterwegs", self.page.locator("#status-choice").inner_text())
        self.page.locator("a", has_text="Preisübersicht").click()
        self.assertIn("Summe netto", self.page.inner_text("main"))
        self.page.locator("a", has_text="Verlauf").click()
        self.assertIn("angelegt", self.page.inner_text("main").lower())


class PlanningOnAPhoneTests(BrowserTestCase):
    """NFA-022: usable from 360 pixels width, without scrolling sideways."""

    viewport = {"width": 360, "height": 740}

    def test_pages_fit_the_width_of_a_phone(self) -> None:
        pages = ["/", "/projects/", f"/projects/{self.project.pk}/", f"/projects/{self.project.pk}/packlist/"]
        pages += ["/material/", "/products/", "/customers/", "/shortages/", "/account/"]
        for path in pages:
            with self.subTest(page=path):
                self.open(path)
                width = self.page.evaluate("document.scrollingElement.scrollWidth")
                self.assertLessEqual(width, 360, f"{path} is {width} pixels wide")
