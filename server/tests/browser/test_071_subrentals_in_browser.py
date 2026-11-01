# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: a new supplier from the dialog of a subrental, in a dialog over it (PRJ-101); the page
"Zumietung bei …" (PRJ-106) – and axe-core on both."""

from __future__ import annotations

from unittest import SkipTest

from rentalars.masterdata.models import Supplier
from rentalars.projects import services
from rentalars.projects.models import MaterialLine
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.helpers import ALL_RIGHTS, add_line, at, make_project, make_stock


class SubrentalsInBrowserTests(BrowserTestCase):
    """PRJ-101 and PRJ-106 where only a browser shows them; no finding of axe-core."""

    bypass_csp = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = _axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()

    def axe_findings(self, within: str = "") -> list[str]:
        """What axe-core finds on the page, or only within the elements a selector names."""
        self.page.wait_for_load_state("networkidle")
        # Colours in the middle of a transition (120 ms on buttons) are no finding.
        self.page.wait_for_function("() => document.getAnimations().every(a => a.playState !== 'running')")
        if not self.page.evaluate("() => typeof axe !== 'undefined'"):
            self.page.add_script_tag(path=str(self.axe))
        return self.page.evaluate(
            "async ([tags, within]) => (await axe.run(within ? {include: [[within]]} : document,"
            " {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            [WCAG_AA, within],
        )

    def setUp(self) -> None:
        super().setUp()
        self.gala = make_project("Gala 071", start=at(20, 8), end=at(21, 22))
        spots = make_stock("L-071", 2, "Profilscheinwerfer")
        line = add_line(self.gala, spots, 5).line
        self.subrental = services.accept_subrental_suggestion(line, spots, 3, rights=ALL_RIGHTS)

    def open_subrental_dialog(self) -> None:
        self.open(f"/projects/{self.gala.pk}/")
        self.page.locator(f'tr[data-covering="{self.subrental.pk}"] button[aria-label="Zumietung bearbeiten"]').click()
        self.page.locator("#dialog[open] #id_supplier_text").wait_for()

    def test_a_new_supplier_from_the_dialog_of_the_subrental(self) -> None:
        """PRJ-101: "… als neuen Lieferanten anlegen" opens over the line's dialog; the line dialog keeps its input."""
        self.open_subrental_dialog()
        self.page.fill("#dialog #id_note", "Bitte mit Irisblende")
        field = self.page.locator("#id_supplier_text")
        field.click()
        field.press_sequentially("Licht-Pool", delay=20)
        create = self.page.locator('#dialog [role=option]:has-text("als neuen Lieferanten anlegen")')
        create.wait_for()
        create.click()
        nested = self.page.locator("#create-dialog[open]")
        nested.wait_for()
        self.assertTrue(self.page.evaluate("() => document.getElementById('dialog').open"))
        self.assertEqual(nested.locator("#id_name").input_value(), "Licht-Pool")
        self.assertEqual(self.axe_findings("#create-dialog"), [])
        # Escape closes only the dialog on top; the supplier field gets the focus back.
        self.page.keyboard.press("Escape")
        nested.wait_for(state="detached")
        self.assertTrue(self.page.evaluate("() => document.getElementById('dialog').open"))
        self.assertEqual(self.page.evaluate("() => document.activeElement.id"), "id_supplier_text")

        # Typed on, the offer to create comes again.
        field.press_sequentially(" Nord", delay=20)
        create = self.page.locator('#dialog [role=option]:has-text("„Licht-Pool Nord“ als neuen Lieferanten anlegen")')
        create.wait_for()
        create.click()
        nested.wait_for()
        nested.locator("#id_email").fill("dispo@licht-pool.example")
        nested.locator("button[type=submit]").click()
        self.page.wait_for_function("() => !document.getElementById('create-dialog').open")
        supplier = Supplier.objects.get(name__startswith="Licht-Pool")
        self.assertEqual(self.page.locator("#id_supplier").input_value(), str(supplier.pk))
        self.assertEqual(field.input_value(), supplier.name)
        self.assertEqual(self.page.locator("#dialog #id_note").input_value(), "Bitte mit Irisblende")
        self.page.select_option("#id_subrental_status", "requested")
        self.assertEqual(self.axe_findings("#dialog"), [])
        self.page.locator("#dialog button[type=submit]").click()
        self.page.wait_for_function("() => !document.getElementById('dialog').open")
        self.settle()
        self.subrental.refresh_from_db()
        self.assertEqual((self.subrental.supplier, self.subrental.subrental_status), (supplier, "requested"))
        self.assertEqual(self.subrental.note, "Bitte mit Irisblende")
        link = self.page.locator(f'tr[data-covering="{self.subrental.pk}"] a', has_text=supplier.name)
        self.assertEqual(link.get_attribute("href"), f"/projects/{self.gala.number}/subrentals/{supplier.pk}/")

    def test_an_existing_supplier_and_the_status(self) -> None:
        """PRJ-101: a suggestion is chosen with the keyboard; "angefragt" without supplier is refused."""
        nord = Supplier.objects.create(name="Verleih Nord", email="dispo@nord.example")
        self.open_subrental_dialog()
        self.page.select_option("#id_subrental_status", "requested")
        self.page.locator("#dialog button[type=submit]").click()
        self.page.locator("#dialog .has-error #id_subrental_status").wait_for()
        field = self.page.locator("#id_supplier_text")
        field.click()
        field.press_sequentially("Nord", delay=20)
        self.page.locator('#dialog [role=option]:has-text("Verleih Nord")').wait_for()
        field.press("Enter")
        self.assertEqual(self.page.locator("#id_supplier").input_value(), str(nord.pk))
        self.page.locator("#dialog button[type=submit]").click()
        self.page.wait_for_function("() => !document.getElementById('dialog').open")
        self.settle()
        self.assertEqual(MaterialLine.objects.get(pk=self.subrental.pk).supplier, nord)

    def test_the_page_of_the_subrental(self) -> None:
        """PRJ-106: lines, documents, correspondence – readable, and no finding of axe-core, dark and light."""
        nord = Supplier.objects.create(name="Verleih Nord", contact="Herr Maier", email="dispo@nord.example")
        services.update_line(self.subrental, rights=ALL_RIGHTS, supplier=nord, subrental_status="ordered")
        self.open(f"/shortages/?supplier={nord.pk}")
        self.page.locator("#subrentals a", has_text="Verleih Nord").click()
        self.page.wait_for_url(f"**/projects/{self.gala.number}/subrentals/{nord.pk}/")
        self.assertIn("Zumietung bei Verleih Nord", self.text_of("main"))
        # The pointer that clicked the link would hover a button of the new page.
        self.page.mouse.move(0, 0)
        self.page.wait_for_timeout(300)
        self.assertEqual(self.page.locator(f"#id_status_{self.subrental.pk}").input_value(), "ordered")
        self.assertEqual(self.axe_findings(), [])
        self.page.evaluate("() => { document.documentElement.dataset.theme = 'light'; }")
        self.assertEqual(self.axe_findings("main"), [])
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.assertLessEqual(
            self.page.evaluate("() => document.documentElement.scrollWidth"),
            self.page.evaluate("() => window.innerWidth"),
        )
