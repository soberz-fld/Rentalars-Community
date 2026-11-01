# SPDX-License-Identifier: GPL-3.0-or-later
"""In a real browser: the contact person dialog of the project form and the photos of a model.

* PRJ-140 – "+ Neuer Ansprechpartner …" in the contact field opens a dialog; saving closes it and chooses the new contact.
* MAT-090 – photos are added to a model, shown as previews that really load, and removed after a question.
"""

from __future__ import annotations

import io
import re

from PIL import Image

from rentalars.customers.models import Contact, Customer
from rentalars.material.models import MaterialFile, MaterialModel
from tests.browser.base import BrowserTestCase


def jpeg_file(path, width: int = 1200, height: int = 800) -> str:
    """A photo on disk for the upload field."""
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (20, 40, 220)).save(buffer, "JPEG")
    path.write_bytes(buffer.getvalue())
    return str(path)


class ContactDialogInBrowserTests(BrowserTestCase):
    def test_a_new_contact_person_from_the_project_form(self) -> None:
        """PRJ-140: choose the last entry, fill in the dialog, and the field has the new person; the project keeps it."""
        customer = Customer.objects.filter(contacts__isnull=False).first()
        self.open(f"/projects/new/?customer={customer.pk}")
        select = self.page.locator("select[name=contact]")
        before = select.input_value()
        select.select_option(label="+ Neuer Ansprechpartner …")
        dialog = self.page.locator("dialog#dialog[open]")
        dialog.locator("[name=last_name]").wait_for()
        # The list went back to what it showed; the choice itself is no value.
        self.assertEqual(select.input_value(), before)
        dialog.locator("[name=first_name]").fill("Berta")
        dialog.locator("[name=last_name]").fill("Klein")
        dialog.locator("button[type=submit]").last.click()
        self.page.wait_for_function("() => !document.querySelector('dialog#dialog[open]')")
        contact = Contact.objects.get(last_name="Klein", customer=customer)
        self.assertEqual(select.input_value(), str(contact.pk))
        self.assertEqual(select.locator("option:checked").inner_text(), "Berta Klein")
        # The new entry stands before "+ Neuer Ansprechpartner …", which is still the last one.
        options = select.locator("option").all_inner_texts()
        self.assertEqual(options[-1], "+ Neuer Ansprechpartner …")
        self.assertEqual(options[-2], "Berta Klein")

    def test_a_missing_last_name_is_asked_for_in_the_dialog(self) -> None:
        customer = Customer.objects.filter(contacts__isnull=False).first()
        self.open(f"/projects/new/?customer={customer.pk}")
        self.page.locator("select[name=contact]").select_option(label="+ Neuer Ansprechpartner …")
        dialog = self.page.locator("dialog#dialog[open]")
        dialog.locator("[name=first_name]").fill("Berta")
        dialog.locator("button[type=submit]").last.click()
        self.settle()
        self.assertIn("Nachname", dialog.inner_text())
        self.assertFalse(Contact.objects.filter(first_name="Berta").exists())


class PhotosInBrowserTests(BrowserTestCase):
    def test_add_look_at_and_remove_photos_of_a_model(self) -> None:
        import tempfile
        from pathlib import Path

        model = MaterialModel.objects.first()
        self.open(f"/material/models/{model.pk}/")
        with tempfile.TemporaryDirectory() as folder:
            files = [jpeg_file(Path(folder) / "a.jpg"), jpeg_file(Path(folder) / "b.jpg", 800, 1200)]
            self.page.set_input_files("input[name=photos]", files)
            self.page.locator("#photos button[type=submit]").click()
            self.page.wait_for_url(f"**/material/models/{model.pk}/#photos")
        grid = self.page.locator("#photos .photo-grid img")
        self.assertEqual(grid.count(), 2)
        # The previews load (a broken picture has no width) and are small.
        self.page.wait_for_function(
            "() => [...document.querySelectorAll('#photos img')].every(i => i.complete && i.naturalWidth > 0)"
        )
        sizes = self.page.evaluate(
            "() => [...document.querySelectorAll('#photos img')].map(i => Math.max(i.naturalWidth, i.naturalHeight))"
        )
        self.assertTrue(all(0 < size <= 640 for size in sizes), sizes)
        self.assertEqual(MaterialFile.objects.filter(material_model=model).count(), 2)
        # The head of the page shows the first photo.
        self.assertEqual(self.page.locator(".head-with-picture img.thumb").count(), 1)
        self.page.locator("#photos li").first.locator("button", has_text="entfernen").click()
        self.confirm()
        self.page.wait_for_function("() => document.querySelectorAll('#photos .photo-grid img').length === 1")
        self.settle()
        self.assertEqual(MaterialFile.objects.filter(material_model=model).count(), 1)


class PhotosOnAPhoneInBrowserTests(BrowserTestCase):
    viewport = {"width": 390, "height": 760}

    def test_the_pages_do_not_scroll_sideways(self) -> None:
        import tempfile
        from pathlib import Path

        from rentalars.material import services
        from rentalars.material.models import MaterialItem

        item = MaterialItem.objects.first()
        with tempfile.TemporaryDirectory() as folder:
            for number in range(5):
                path = Path(folder) / f"{number}.jpg"
                jpeg_file(path)
                with open(path, "rb") as handle:
                    from django.core.files.uploadedfile import SimpleUploadedFile

                    upload = SimpleUploadedFile(path.name, handle.read(), "image/jpeg")
                    services.add_file(item.material_model, upload, kind="picture")
                    services.add_file(
                        item, SimpleUploadedFile(path.name, path.read_bytes(), "image/jpeg"), kind="picture"
                    )
                # The test server shares one database connection between its threads: ten previews asked for at once would
        # trip over each other. The layout does not depend on the picture, so the browser gets a stand-in.
        stand_in = io.BytesIO()
        Image.new("RGB", (640, 480), (20, 40, 220)).save(stand_in, "JPEG")
        self.page.route(
            re.compile(r"/material/files/\d+/small/"),
            lambda route: route.fulfill(status=200, content_type="image/jpeg", body=stand_in.getvalue()),
        )
        for path in (
            f"/material/items/{item.pk}/",
            f"/material/models/{item.material_model_id}/",
            f"/material/items/{item.pk}/files/",
        ):
            self.open(path)
            self.page.wait_for_load_state("networkidle")
            width = self.page.evaluate(
                "() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]"
            )
            self.assertLessEqual(width[0], width[1] + 1, (path, width))
