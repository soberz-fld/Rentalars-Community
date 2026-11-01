# SPDX-License-Identifier: GPL-3.0-or-later
"""In a real browser: scanning labels, accessory and replacement suggestions, built-in bulk material (MAT-027, UIX-006, PCK-010, PCK-011).

Scanning (UIX-006, MAT-027, PCK-010, PCK-016): the dialog of ``static/js/scan.js`` opens, starts "the camera",
reads a code and acts on it. **There is no camera here.** The page gets a simulated ``BarcodeDetector`` (it answers
with the codes the test puts in a queue) and a simulated ``getUserMedia`` (a canvas stream). What is tested is the
widget – opening, permission messages, torch, closing and stopping the stream, typing a code, what the page does
with a code – not the recognition of a real picture in a real lens. The recognition itself belongs to the browser.

The pages are checked with axe-core (NFA-025) like the other browser tests; without axe those tests are skipped.
"""

from __future__ import annotations

from typing import Any
from unittest import SkipTest

from rentalars.material.installations import install_quantity
from rentalars.material.models import MaterialItem
from rentalars.packing import scan as packing_scan
from rentalars.packing import services as packing
from rentalars.packing.models import Allocation, PackEntry
from rentalars.products import suggestions
from rentalars.products.relation_models import RelationKind
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.helpers import add_line, make_item, make_model, make_product, make_project, make_stock

#: A camera that is a canvas, and a detector that reads what the test queues in ``window.__scanQueue``.
FAKE_CAMERA = """
(() => {
  window.__scanQueue = [];
  window.__tracksStopped = 0;
  window.__streams = 0;
  class FakeDetector {
    static async getSupportedFormats() { return ["qr_code", "code_128", "ean_13", "ean_8"]; }
    constructor(options) { this.formats = options.formats; }
    async detect() { const code = window.__scanQueue.shift(); return code ? [{rawValue: code, format: "qr_code"}] : []; }
  }
  window.BarcodeDetector = FakeDetector;
  const getUserMedia = async () => {
    const canvas = document.createElement("canvas");
    canvas.width = 320; canvas.height = 240;
    const context = canvas.getContext("2d");
    let shade = 0;
    setInterval(() => { shade = (shade + 20) % 255; context.fillStyle = "rgb(" + shade + ",80,80)"; context.fillRect(0, 0, 320, 240); }, 60);
    const stream = canvas.captureStream(15);
    const track = stream.getVideoTracks()[0];
    const stop = track.stop.bind(track);
    track.stop = () => { window.__tracksStopped += 1; stop(); };
    track.getCapabilities = () => ({torch: true});
    track.applyConstraints = async (constraints) => { window.__torch = constraints.advanced[0].torch; };
    window.__streams += 1;
    return stream;
  };
  Object.defineProperty(navigator, "mediaDevices", {value: {getUserMedia}, configurable: true});
})();
"""

#: A browser without the detector (Firefox, Safari) – only typing works.
NO_DETECTOR = "delete window.BarcodeDetector;"

#: A page that is not served over HTTPS: the browser gives no camera.
INSECURE = "Object.defineProperty(window, 'isSecureContext', {value: false});"

#: The user says no to the camera.
DENIED = """
Object.defineProperty(navigator, "mediaDevices", {value: {getUserMedia: async () => {
  throw new DOMException("denied", "NotAllowedError");
}}, configurable: true});
class _D { static async getSupportedFormats() { return ["qr_code"]; } async detect() { return []; } }
window.BarcodeDetector = _D;
"""


class ScanInBrowserCase(BrowserTestCase):
    """Helpers for the tests of the scan dialog."""

    def with_camera(self, script: str = FAKE_CAMERA) -> None:
        """Install the simulated camera for the pages that are opened from now on."""
        self.page.add_init_script(script)

    def scan_button(self, scope: str = "main") -> Any:
        return self.page.locator(f"{scope} [data-scan-open]").first

    def open_dialog(self, scope: str = "main") -> Any:
        self.scan_button(scope).click()
        dialog = self.page.locator("dialog.scan-dialog[open]")
        dialog.wait_for()
        return dialog

    def feed(self, code: str) -> None:
        """What the camera reads next."""
        self.page.evaluate("code => window.__scanQueue.push(code)", code)

    def a_demo_item(self) -> MaterialItem:
        return (
            MaterialItem.objects.filter(material_model__default_product__isnull=False)
            .order_by("inventory_number")
            .first()
        )


class ScanLookupInBrowserTests(ScanInBrowserCase):
    """The field in the head of the material pages (MAT-027, MAT-063)."""

    def test_the_camera_reads_a_label_and_the_item_opens(self) -> None:
        item = self.a_demo_item()
        self.with_camera()
        self.open("/material/")
        dialog = self.open_dialog()
        self.page.wait_for_function("() => document.querySelector('.scan-status').textContent.includes('Kamera')")
        self.assertIn("Halte den Code vor die Kamera", self.text_of(".scan-status"))
        self.assertEqual(self.page.evaluate("window.__streams"), 1)
        # The label's QR code holds the address of the item.
        self.feed(f"{self.live_server_url}/m/{item.display_id}")
        self.page.wait_for_url(f"{self.live_server_url}/material/items/{item.pk}/")
        self.assertIn(item.display_id, self.text_of("h1"))
        self.assertTrue(dialog.count() in (0, 1))

    def test_closing_stops_the_camera_and_gives_the_focus_back(self) -> None:
        self.with_camera()
        self.open("/material/")
        self.open_dialog()
        self.page.wait_for_function("() => window.__streams === 1")
        self.page.keyboard.press("Escape")
        self.page.wait_for_selector("dialog.scan-dialog", state="detached")
        self.assertEqual(self.page.evaluate("window.__tracksStopped"), 1)
        self.assertTrue(self.page.evaluate("document.activeElement.hasAttribute('data-scan-open')"))
        # Opened again: a new stream; closed with the button: stopped again.
        self.open_dialog()
        self.page.wait_for_function("() => window.__streams === 2")
        self.page.get_by_role("button", name="Schließen").last.click()
        self.page.wait_for_selector("dialog.scan-dialog", state="detached")
        self.assertEqual(self.page.evaluate("window.__tracksStopped"), 2)

    def test_the_torch(self) -> None:
        self.with_camera()
        self.open("/material/")
        self.open_dialog()
        torch = self.page.get_by_role("button", name="Taschenlampe")
        torch.wait_for()
        self.assertEqual(torch.get_attribute("aria-pressed"), "false")
        torch.click()
        self.page.wait_for_function("() => window.__torch === true")
        self.assertEqual(torch.get_attribute("aria-pressed"), "true")

    def test_typing_always_works_even_without_a_detector(self) -> None:
        item = self.a_demo_item()
        self.with_camera(NO_DETECTOR)
        self.open("/material/")
        self.open_dialog()
        self.assertIn("kann Codes nicht aus dem Kamerabild lesen", self.text_of(".scan-status"))
        field = self.page.get_by_label("Code eintippen oder scannen")
        self.assertTrue(
            field.evaluate("node => node === document.activeElement")
        )  # a hand scanner types into it at once
        field.fill(item.display_id)
        field.press("Enter")  # a hand scanner ends with Enter
        self.page.wait_for_url(f"{self.live_server_url}/material/items/{item.pk}/")

    def test_the_message_without_a_secure_connection(self) -> None:
        self.with_camera(INSECURE)
        self.open("/material/")
        self.open_dialog()
        self.assertIn("HTTPS", self.text_of(".scan-status"))

    def test_the_message_when_the_camera_is_not_allowed_and_typing_still_works(self) -> None:
        self.with_camera(DENIED)
        self.open("/material/")
        self.open_dialog()
        self.page.wait_for_function(
            "() => document.querySelector('.scan-status').textContent.includes('nicht erlaubt')"
        )
        self.page.get_by_label("Code eintippen oder scannen").fill("9999")
        self.page.keyboard.press("Enter")
        self.page.wait_for_url(f"{self.live_server_url}/material/?q=9999")
        self.assertIn("Es gibt kein Exemplar", self.text_of("main .messages"))

    def test_the_same_code_in_front_of_the_camera_is_read_once(self) -> None:
        self.with_camera()
        self.open("/material/")
        self.open_dialog()
        self.page.evaluate(
            "window.__reads = 0; document.addEventListener('scan:code', (event) => { window.__reads += 1; event.preventDefault(); }, true)"
        )
        for _ in range(4):
            self.feed("0001")
        self.page.wait_for_function("() => window.__reads >= 1")
        self.page.wait_for_timeout(600)
        self.assertEqual(self.page.evaluate("window.__reads"), 1)


class ScanPackingInBrowserTests(ScanInBrowserCase):
    """PCK-010, PCK-011, PCK-016: the packing list marks items by their labels."""

    def setUp(self) -> None:
        super().setUp()
        self.par = make_stock("L-910", 4, "Scan-PAR")
        self.cans = list(
            MaterialItem.objects.filter(material_model__default_product=self.par).order_by("inventory_number")
        )
        self.fest = make_project("Scan-Test")
        add_line(self.fest, self.par, 2)
        self.base = f"/projects/{self.fest.pk}/packlist/"

    def test_scanned_items_are_counted_up_and_the_dialog_says_so(self) -> None:
        self.with_camera()
        self.open(self.base)
        self.open_dialog("#packlist")
        self.feed(self.cans[0].display_id)
        self.page.wait_for_function("() => document.querySelector('.scan-status').textContent.includes('1 von 2')")
        self.assertIn("is-success", self.page.get_attribute(".scan-status", "class"))
        self.feed(self.cans[1].display_id)
        self.page.wait_for_function("() => document.querySelector('.scan-status').textContent.includes('2 von 2')")
        # What cannot be packed is said, in red.
        self.cans[2].status = "defective"
        self.cans[2].status_reason = "Lampe gebrochen"
        self.cans[2].save()
        self.feed(self.cans[2].display_id)
        self.page.wait_for_function("() => document.querySelector('.scan-status').classList.contains('is-error')")
        self.assertIn("kann nicht gepackt werden", self.text_of(".scan-status"))
        self.page.keyboard.press("Escape")
        self.page.wait_for_selector("dialog.scan-dialog", state="detached")
        self.settle()
        self.assertEqual(Allocation.objects.filter(packed_scan_at__isnull=False).count(), 2)
        entry = PackEntry.objects.get(packlist__project=self.fest)
        self.assertEqual(entry.packed_quantity, 2)
        self.assertIn("is-done", self.page.locator("#packlist li.pack-row").first.get_attribute("class"))

    def test_typing_the_id_into_the_field_of_the_list(self) -> None:
        self.open(self.base)
        field = self.page.locator("#pack-scan-code")
        field.fill(self.cans[0].display_id)
        field.press("Enter")  # a hand scanner types the ID and presses Enter
        self.page.wait_for_selector("#packlist .messages", state="visible")
        self.assertIn("1 von 2", self.text_of("#packlist .messages"))
        self.assertIn("is-scanned", self.page.locator("#packlist li.pack-row").first.get_attribute("class"))
        # The field is empty and has the focus again: the next item can follow at once.
        self.assertEqual(self.page.locator("#pack-scan-code").input_value(), "")
        self.assertTrue(self.page.evaluate("document.activeElement.id === 'pack-scan-code'"))

    def test_taking_back_by_scanning(self) -> None:
        for can in self.cans[:2]:
            packing_scan.scan_pack(packing.get_packlist(self.fest), can.display_id)
        packing.issue(packing.get_packlist(self.fest))
        self.with_camera()
        self.open(self.base + "?mode=return")
        self.open_dialog("#packlist")
        self.feed(self.cans[0].display_id)
        self.page.wait_for_function("() => document.querySelector('.scan-status').textContent.includes('ist zurück')")
        self.page.keyboard.press("Escape")
        self.settle()
        self.assertEqual(Allocation.objects.filter(returned_scan_at__isnull=False).count(), 1)


class ScanPlanningInBrowserTests(ScanInBrowserCase):
    """UIX-006: an item read from its label is added to the planning as a wish for exactly that item."""

    def test_a_scanned_item_becomes_a_line(self) -> None:
        item = self.a_demo_item()
        before = self.project.material_lines.count()
        self.with_camera()
        self.open_planning()
        self.page.get_by_role("button", name="Exemplare scannen").click()
        self.page.locator("dialog.scan-dialog[open]").wait_for()
        self.feed(item.display_id)
        self.page.wait_for_function("() => document.querySelector('.scan-status').textContent.includes('Hinzugefügt')")
        self.page.keyboard.press("Escape")
        self.settle()
        self.assertEqual(self.project.material_lines.count(), before + 1)
        self.assertEqual(self.project.material_lines.order_by("-pk").first().preferred_item, item)


class SuggestionsInBrowserTests(BrowserTestCase):
    """PRD-023, VFG-015: the hint in the planning; adding and dismissing it."""

    def setUp(self) -> None:
        super().setUp()
        self.speaker = make_stock("S-910", 2, "Scan-Lautsprecher")
        self.cable = make_stock("K-910", 10, "Scan-Kabel")
        self.stand_in = make_stock("S-911", 6, "Scan-Ersatzlautsprecher")
        self.relation = suggestions.add_relation(self.speaker, self.cable, RelationKind.ACCESSORY, is_required=True)
        suggestions.add_relation(self.speaker, self.stand_in, RelationKind.REPLACEMENT)
        self.fest = make_project("Hinweis-Test")
        add_line(self.fest, self.speaker, 3)  # one is missing

    def test_accept_and_dismiss(self) -> None:
        self.open(f"/projects/{self.fest.pk}/")
        panel = self.page.locator("#suggestions")
        panel.get_by_text("Scan-Kabel").wait_for()
        self.assertIn("Scan-Ersatzlautsprecher", panel.inner_text())
        self.assertIn("6 frei", panel.inner_text())
        panel.get_by_role("button", name="Hinzufügen").first.click()
        self.settle()
        self.assertEqual(self.fest.material_lines.filter(product=self.cable).get().quantity, 3)
        self.page.locator("#suggestions").get_by_text("Scan-Kabel").wait_for(state="detached")
        self.page.locator("#suggestions").get_by_role(
            "button", name="Alle Vorschläge in diesem Projekt verwerfen"
        ).click()
        self.page.get_by_role("button", name="Wieder anzeigen").wait_for()
        self.page.get_by_role("button", name="Wieder anzeigen").click()
        self.page.locator("#suggestions").get_by_text("Scan-Ersatzlautsprecher").wait_for()

    def test_the_product_page_manages_the_relations(self) -> None:
        extra = make_stock("T-910", 3, "Scan-Stativ")
        self.open(f"/products/{self.speaker.pk}/")
        panel = self.page.locator("#relations")
        self.choose_product(panel, "Scan-Stativ")
        panel.get_by_role("button", name="Hinzufügen").click()
        self.page.wait_for_load_state("networkidle")
        self.assertIn("Scan-Stativ", self.text_of("#relations"))
        self.assertTrue(self.speaker.relations.filter(related_product=extra).exists())


class StockAccessibilityTests(ScanInBrowserCase):
    """NFA-025: the new boxes, pages and the dialog without a finding of axe-core – wide and on a phone."""

    bypass_csp = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = _axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()

    def findings(self, label: str) -> list[str]:
        self.page.add_script_tag(path=str(self.axe))
        result = self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            WCAG_AA,
        )
        return [f"{label}: {finding}" for finding in result]

    def test_pages(self) -> None:
        speaker = make_stock("S-920", 2, "Axe-Lautsprecher")
        cable = make_stock("K-920", 10, "Axe-Kabel")
        substitute = make_stock("S-921", 5, "Axe-Ersatz")
        suggestions.add_relation(speaker, cable, RelationKind.ACCESSORY, is_required=True, note="Speakon")
        suggestions.add_relation(speaker, substitute, RelationKind.REPLACEMENT)
        fest = make_project("Axe-Test")
        add_line(fest, speaker, 3)
        rack = make_item(make_model("Axe-Rack", make_product("S-922", "Axe-Rack")), 880)
        roll = make_item(make_model("Axe-Rolle", make_product("K-922", "Axe-Rolle"), bulk=True), 881, quantity=40)
        install_quantity(rack, roll, 12)
        cans = list(MaterialItem.objects.filter(material_model__default_product=speaker).order_by("inventory_number"))
        packing_scan.scan_pack(packing.get_packlist(fest), cans[0].display_id)
        model = rack.material_model
        found: list[str] = []
        for width in (1360, 390):
            self.page.set_viewport_size({"width": width, "height": 900})
            for label, address in (
                ("product", f"/products/{speaker.pk}/"),
                ("planning", f"/projects/{fest.pk}/"),
                ("documents", f"/projects/{fest.pk}/documents/"),
                ("packing", f"/projects/{fest.pk}/packlist/"),
                ("rack", f"/material/items/{rack.pk}/"),
                ("bulk row", f"/material/items/{roll.pk}/"),
                ("model", f"/material/models/{model.pk}/"),
                ("items", "/material/"),
            ):
                self.with_camera()
                self.open(address)
                self.settle()
                found += self.findings(f"{label} at {width} px")
                scrolls = self.page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
                self.assertFalse(scrolls, f"{label} at {width} px scrolls sideways")
            # The dialog itself, with the camera running.
            self.with_camera()
            self.open("/material/")
            self.open_dialog()
            self.page.wait_for_function("() => document.querySelector('.scan-status').textContent.includes('Kamera')")
            found += self.findings(f"scan dialog at {width} px")
            self.page.keyboard.press("Escape")
        self.assertEqual(found, [], "\n".join(found))
