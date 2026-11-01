# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: photos and videos in the chat (UIX-049; UIX-010).

* A photo chosen in the form goes with the message: the list comes back with the preview, which loads,
  and the form is empty again.
* A file too large is said before the upload; nothing is sent.
* On a phone the field for the camera shows; no horizontal scrolling; axe-core finds nothing – with a
  photo, a video being made smaller and a failed one in the chat.
"""

from __future__ import annotations

import io
import shutil
import tempfile
from pathlib import Path
from unittest import SkipTest

from django.test import override_settings
from PIL import Image

from rentalars.accounts.models import User
from rentalars.chat.models import ChatAttachment, ChatMessage
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path


def jpeg(width: int, height: int) -> bytes:
    stored = io.BytesIO()
    Image.new("RGB", (width, height), (30, 120, 200)).save(stored, "JPEG")
    return stored.getvalue()


class ChatMediaInBrowserTests(BrowserTestCase):
    """The form with photos and videos – on the desktop and on a phone."""

    bypass_csp = True

    def setUp(self) -> None:
        super().setUp()
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        override = override_settings(DATA_DIR=folder, MEDIA_ROOT=str(folder / "media"), SERVE_MEDIA_VIA_NGINX=False)
        override.enable()
        self.addCleanup(override.disable)
        self.url = f"/projects/{self.project.number}/chat/"

    def axe_findings(self) -> list[str]:
        axe = _axe_path()
        if axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        self.page.wait_for_load_state("networkidle")
        self.page.add_script_tag(path=str(axe))
        return self.page.evaluate(
            "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            WCAG_AA,
        )

    def test_send_a_photo_and_see_it(self) -> None:
        self.open(self.url)
        self.settle()
        self.assertTrue(self.page.locator(".chat-camera").is_hidden(), "the camera field is for phones")
        self.page.locator("#chat-text").fill("Die Bühne")
        self.page.set_input_files(
            "#chat-files", files=[{"name": "buehne.jpg", "mimeType": "image/jpeg", "buffer": jpeg(2400, 1600)}]
        )
        self.page.locator(".chat-form button[type=submit]").click()
        preview = self.page.locator(".chat-log .chat-media img")
        preview.wait_for()
        self.settle()
        self.page.wait_for_function("() => document.querySelector('.chat-media img').naturalWidth > 0")
        self.assertEqual(self.page.evaluate("document.querySelector('.chat-media img').naturalWidth"), 640)
        self.assertEqual(self.page.locator("#chat-files").evaluate("field => field.files.length"), 0)
        attachment = ChatAttachment.objects.get()
        self.assertEqual((attachment.width, attachment.height), (2048, 1365))
        self.assertEqual(self.axe_findings(), [])

    def test_too_large_is_said_before_the_upload(self) -> None:
        self.open(self.url)
        self.settle()
        self.page.locator("[data-chat-form]").evaluate("form => { form.dataset.maxPhotoMb = '0'; }")
        self.page.set_input_files(
            "#chat-files", files=[{"name": "gross.jpg", "mimeType": "image/jpeg", "buffer": jpeg(400, 300)}]
        )
        error = self.page.locator("[data-chat-file-error]")
        error.wait_for()
        self.assertIn("Zu groß: Fotos bis 25 MB, Videos bis 200 MB", error.inner_text())
        self.page.locator(".chat-form button[type=submit]").click()
        self.page.wait_for_timeout(300)
        self.assertFalse(ChatMessage.objects.exists())

    def test_on_a_phone(self) -> None:
        anna = User.objects.get(username="anna")
        message = ChatMessage.objects.create(project=self.project, author=anna, author_name="anna", text="Aufbau")
        ChatAttachment.objects.create(message=message, kind="video", state="processing")
        ChatAttachment.objects.create(message=message, kind="video", state="failed", failure="convert")
        context = self.browser.new_context(
            viewport={"width": 375, "height": 800}, is_mobile=True, has_touch=True, locale="de-DE", bypass_csp=True
        )
        self.addCleanup(context.close)
        cookies = self.page.context.cookies()
        context.add_cookies(cookies)
        self.page = context.new_page()
        self.page.on("pageerror", lambda error: self.problems.append(f"script error: {error}"))
        self.open(self.url)
        self.page.wait_for_load_state("networkidle")
        self.assertTrue(self.page.locator(".chat-camera").is_visible())
        self.assertEqual(self.page.locator("#chat-camera").get_attribute("capture"), "environment")
        self.assertIn("Video wird verkleinert …", self.page.inner_text(".chat-log"))
        self.assertLessEqual(self.page.evaluate("document.scrollingElement.scrollWidth"), 375)
        self.assertEqual(self.axe_findings(), [])
