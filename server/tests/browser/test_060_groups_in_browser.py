# SPDX-License-Identifier: GPL-3.0-or-later
"""In a real browser: nested groups on the planning page (PRJ-037, UIX-009, NFA-025).

The sample project gets a group "Licht" around its two lighting groups. The
tests drag "Ton FOH" into it and check the sums, move it with the keyboard,
fold subgroups away and choose the parent group in the dialog.
"""

from __future__ import annotations

from decimal import Decimal

from rentalars.projects.models import Group
from rentalars.projects.planning import build_planning
from rentalars.projects.services import move_group
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import AccessibilityInBrowserTests
from tests.helpers import add_group


def nest_lighting(test: BrowserTestCase) -> dict[str, Group]:
    """Put "Licht Front-Traverse" and "Licht Rear-Traverse" into a new group "Licht" with 5 % discount."""
    groups = {group.name: group for group in test.project.groups.all()}
    light = add_group(test.project, "Licht", discount_percent=Decimal("5"))
    move_group(light, parent=None, position=1)
    move_group(groups["Licht Front-Traverse"], parent=light)
    move_group(groups["Licht Rear-Traverse"], parent=light)
    groups["Licht"] = light
    return groups


def money(amount: Decimal) -> str:
    """An amount as the German page shows it: 1.234,50."""
    whole, cents = f"{amount:.2f}".split(".")
    return f"{int(whole):,}".replace(",", ".") + "," + cents


class NestedGroupsInBrowserTests(BrowserTestCase):
    """Drag, keys, folding, dialog – and the page stays in step with the server."""

    def setUp(self) -> None:
        super().setUp()
        self.groups = nest_lighting(self)

    def node(self, group: Group) -> str:
        return f'[data-group-node="{group.pk}"]'

    def handle(self, group: Group) -> object:
        return self.page.locator(f"{self.node(group)} > section [data-group-handle]")

    def parent_in_page(self, group: Group) -> str:
        """The data-parent of the list the group's node stands in."""
        return self.page.evaluate(f"document.querySelector('{self.node(group)}').parentElement.dataset.parent")

    def subtotal_text(self, group: Group) -> str:
        return " ".join(self.page.inner_text(f"#group-total-{group.pk}").split())

    def test_dragging_a_group_into_another_one_adds_it_to_the_sums(self) -> None:
        sound, light, rear = self.groups["Ton FOH"], self.groups["Licht"], self.groups["Licht Rear-Traverse"]
        self.open_planning()
        self.settle()
        before = build_planning(self.project).prices.by_group_id[light.pk].subtotal
        self.assertIn(money(before), self.subtotal_text(light))

        # Fold the long groups away, so that the way from the handle to the target fits the window.
        for group in (self.groups["Licht Front-Traverse"], rear, sound):
            self.page.evaluate(
                f"document.querySelector('#group-{group.pk} table.lines').style.display = 'none';"
                f"document.querySelector('#group-{group.pk} form.line-add').style.display = 'none'"
            )
        handle = self.handle(sound)
        handle.scroll_into_view_if_needed()
        start = handle.bounding_box()
        target = self.page.locator(f"#group-{rear.pk} .group-head").bounding_box()
        assert start and target
        self.page.mouse.move(start["x"] + start["width"] / 2, start["y"] + start["height"] / 2)
        self.page.mouse.down()
        self.page.mouse.move(start["x"] + start["width"] / 2, start["y"] - 10, steps=5)
        inside = f"#group-children-{light.pk} > {self.node(sound)}"
        for nudge in range(60):
            if self.page.locator(inside).count():
                break
            target = self.page.locator(f"#group-{rear.pk} .group-head").bounding_box()
            assert target
            self.page.mouse.move(target["x"] + 80 + nudge % 2, target["y"] + 4 + nudge % 3, steps=3)
            self.page.wait_for_timeout(50)
        self.assertEqual(self.page.locator(inside).count(), 1, "the group did not follow the pointer")
        with self.page.expect_response(lambda response: "/move/" in response.url):
            self.page.mouse.up()
        self.settle()

        sound.refresh_from_db()
        self.assertEqual(sound.parent, light)
        after = build_planning(self.project).prices.by_group_id[light.pk].subtotal
        self.assertGreater(after, before)
        self.assertIn(money(after), self.subtotal_text(light))
        self.assertEqual(self.parent_in_page(sound), str(light.pk))
        # A reload shows the same.
        self.open_planning()
        self.assertEqual(self.parent_in_page(sound), str(light.pk))

    def test_moving_a_group_with_the_keyboard(self) -> None:
        """NFA-025: right into the group above, left out again, up and down among the siblings."""
        sound, light, fog = self.groups["Ton FOH"], self.groups["Licht"], self.groups["Nebel und Effekte"]
        self.open_planning()
        self.settle()

        def press(key: str) -> None:
            with self.page.expect_response(lambda response: "/move/" in response.url):
                self.page.keyboard.press(key)
            self.settle()
            self.page.wait_for_function(
                "(id) => document.activeElement && document.activeElement.matches('[data-group-handle]')"
                " && document.activeElement.closest('[data-group-node]').dataset.groupNode === id",
                arg=str(sound.pk),
                timeout=5000,
            )

        self.handle(sound).focus()
        press("ArrowRight")
        sound.refresh_from_db()
        self.assertEqual((sound.parent, sound.position), (light, 3))
        self.assertEqual(self.parent_in_page(sound), str(light.pk))
        press("ArrowUp")
        sound.refresh_from_db()
        self.assertEqual(sound.position, 2)
        press("ArrowLeft")
        sound.refresh_from_db()
        self.assertEqual((sound.parent, sound.position), (None, 2))
        press("ArrowDown")
        sound.refresh_from_db()
        fog.refresh_from_db()
        self.assertEqual((sound.position, fog.position), (3, 2))
        # Nothing above the first group: the key does nothing and sends nothing.
        self.handle(light).focus()
        self.page.keyboard.press("ArrowUp")
        self.page.wait_for_timeout(200)
        light.refresh_from_db()
        self.assertEqual(light.position, 1)

    def test_too_deep_is_refused_with_a_message(self) -> None:
        light, front = self.groups["Licht"], self.groups["Licht Front-Traverse"]
        inner = add_group(self.project, "Traverse 1", parent=front)
        move_group(light, parent=None, position=2)  # behind "Ton FOH"
        self.open_planning()
        self.settle()
        # "Licht" with two levels below it cannot go into "Ton FOH": the server says so, nothing moves.
        self.handle(light).focus()
        with self.page.expect_response(lambda response: "/move/" in response.url):
            self.page.keyboard.press("ArrowRight")
        self.settle()
        self.assertIn("höchstens 3 Ebenen", self.text_of("#planning-messages"))
        light.refresh_from_db()
        inner.refresh_from_db()
        self.assertEqual((light.parent, inner.parent), (None, front))
        self.assertEqual(self.parent_in_page(light), "")

    def test_subgroups_fold_away_and_stay_folded_after_changes(self) -> None:
        light, front = self.groups["Licht"], self.groups["Licht Front-Traverse"]
        self.open_planning()
        self.settle()
        toggle = self.page.locator(f'[data-group-toggle="{light.pk}"]')
        self.assertEqual(toggle.get_attribute("aria-expanded"), "true")
        toggle.click()
        self.assertEqual(toggle.get_attribute("aria-expanded"), "false")
        self.assertFalse(self.page.locator(f"#group-children-{light.pk}").is_visible())
        # The subtotal with the subgroups stays in sight.
        self.assertTrue(self.page.locator(f"#group-total-{light.pk}").is_visible())

        # A change that patches "Licht" keeps it folded.
        self.choose_product(self.page.locator(f"#group-{light.pk}"), "K-020")
        self.page.locator(f"#group-{light.pk} form.line-add button[type=submit]").click()
        self.settle()
        self.assertEqual(self.page.locator(f"#group-{light.pk} tr[data-line]").count(), 1)
        self.assertEqual(self.page.locator(f'[data-group-toggle="{light.pk}"]').get_attribute("aria-expanded"), "false")
        self.assertFalse(self.page.locator(f"#group-children-{light.pk}").is_visible())
        # … and so does loading the page again.
        self.open_planning()
        self.assertFalse(self.page.locator(f"#group-{front.pk}").is_visible())
        self.page.locator(f'[data-group-toggle="{light.pk}"]').click()
        self.assertTrue(self.page.locator(f"#group-{front.pk}").is_visible())

    def test_choosing_the_parent_group_in_the_dialog(self) -> None:
        sound, light = self.groups["Ton FOH"], self.groups["Licht"]
        self.open_planning()
        self.page.locator(f"#group-{sound.pk} .group-head button[aria-label='Teilgruppe bearbeiten']").click()
        dialog = self.page.locator("dialog[open]")
        dialog.wait_for()
        dialog.locator("[name=parent]").select_option(label="Licht")
        dialog.locator("button[type=submit]").click()
        self.settle()
        self.page.wait_for_function("() => !document.querySelector('dialog[open]')", timeout=5000)
        sound.refresh_from_db()
        self.assertEqual(sound.parent, light)
        self.assertEqual(self.parent_in_page(sound), str(light.pk))
        self.assertEqual(self.page.locator(f"#group-{sound.pk} h4").inner_text(), "Ton FOH")

    def test_a_new_group_inside_another_and_lines_dragged_into_it(self) -> None:
        light = self.groups["Licht"]
        self.open_planning()
        self.page.fill("input.group-name", "Floor")
        self.page.select_option("select.group-parent", label="in Licht")
        self.page.locator("form:has(input.group-name) button[type=submit]").click()
        self.settle()
        floor = Group.objects.get(name="Floor")
        self.assertEqual(floor.parent, light)
        self.assertEqual(self.parent_in_page(floor), str(light.pk))
        # The new subgroup takes lines like any group, and its parent's sum grows with them.
        before = self.subtotal_text(light)
        self.choose_product(self.page.locator(f"#group-{floor.pk}"), "L-020")
        self.page.locator(f"#group-{floor.pk} form.line-add button[type=submit]").click()
        self.settle()
        self.assertEqual(self.page.locator(f"#group-{floor.pk} tr[data-line]").count(), 1)
        self.assertNotEqual(self.subtotal_text(light), before)
        expected = build_planning(self.project).prices.by_group_id[light.pk].subtotal
        self.assertIn(money(expected), self.subtotal_text(light))


class NestedGroupsOnAPhoneTests(BrowserTestCase):
    """UIX-017: three levels of groups still fit the width of a phone."""

    viewport = {"width": 360, "height": 740}

    def test_three_levels_fit_the_width_of_a_phone(self) -> None:
        groups = nest_lighting(self)
        add_group(self.project, "Floor", parent=groups["Licht Rear-Traverse"])
        for path in (f"/projects/{self.project.pk}/", f"/projects/{self.project.pk}/prices/"):
            with self.subTest(page=path):
                self.open(path)
                width = self.page.evaluate("document.scrollingElement.scrollWidth")
                self.assertLessEqual(width, 360, f"{path} is {width} pixels wide")


class NestedGroupsAccessibilityTests(AccessibilityInBrowserTests):
    """NFA-025: the planning and the price overview with nested groups, checked with axe-core."""

    def setUp(self) -> None:
        super().setUp()
        nest_lighting(self)

    def pages(self) -> list[str]:
        return [f"/projects/{self.project.pk}/", f"/projects/{self.project.pk}/prices/"]
