# SPDX-License-Identifier: GPL-3.0-or-later
"""Photos are made anew (NFA-084); photos of models and items (MAT-090).

The requirements: pictures and videos are always rendered anew so that they are efficient in storage and metadata is
minimal; pictures keep the location data; video is rendered at 720p at most. Models and items can store photos.

* One module (``rentalars.core.photos``) makes every photo anew: upright, at most 2048 pixels, JPEG; the place (latitude,
  longitude, altitude) stays; device, time, direction, comment and XMP are removed. A preview of 640 pixels has no
  place and no device (only the colour profile, if it is small).
* The photo of a defect report, a receipt, a photo of a model or item and a picture attached as a manual or other file
  go through it; documents (PDF), a copy of an invoice and the mail attachments are kept as received.
* Models and items have a panel "Fotos" with an upload of several photos, previews that open the whole photo, a head
  picture; an item shows the photos of its model, too. Whoever may only read cannot add or remove.
* The API names the preview of a photo.
"""

from __future__ import annotations

import io
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import ExifTags, Image

from rentalars.core import photos
from rentalars.material import services
from rentalars.material.models import MaterialFile, MaterialFileKind
from tests.api.base import API, ApiTestCase
from tests.helpers import make_items, make_model, make_product
from tests.ui.base import UiTestCase

GPS_KEYS = {
    ExifTags.GPS.GPSLatitudeRef,
    ExifTags.GPS.GPSLatitude,
    ExifTags.GPS.GPSLongitudeRef,
    ExifTags.GPS.GPSLongitude,
    ExifTags.GPS.GPSAltitudeRef,
    ExifTags.GPS.GPSAltitude,
}


def jpeg(width: int = 3000, height: int = 2000, *, place: bool = True, device: bool = True) -> bytes:
    """A photo as a phone writes it, with the place, the time of the place, the direction, device and comment."""
    image = Image.new("RGB", (width, height), (20, 40, 220))
    exif = Image.Exif()
    if device:
        exif[ExifTags.Base.Make] = "Testphone"
        exif[ExifTags.Base.DateTime] = "2027:03:01 10:00:00"
    if place:
        gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
        gps[ExifTags.GPS.GPSLatitudeRef] = "N"
        gps[ExifTags.GPS.GPSLatitude] = (52.0, 31.0, 12.0)
        gps[ExifTags.GPS.GPSLongitudeRef] = "E"
        gps[ExifTags.GPS.GPSLongitude] = (13.0, 24.0, 18.0)
        gps[ExifTags.GPS.GPSAltitudeRef] = 0
        gps[ExifTags.GPS.GPSAltitude] = 34.0
        gps[ExifTags.GPS.GPSDateStamp] = "2027:03:01"
        gps[ExifTags.GPS.GPSImgDirection] = 90.0
    out = io.BytesIO()
    image.save(out, "JPEG", exif=exif, comment=b"Geheimer Kommentar", xmp=b"<x:xmpmeta>Ort</x:xmpmeta>")
    return out.getvalue()


def png(width: int = 40, height: int = 30) -> bytes:
    out = io.BytesIO()
    Image.new("RGBA", (width, height), (0, 0, 0, 0)).save(out, "PNG")
    return out.getvalue()


def upload(content: bytes, name: str = "IMG_0001.jpg", content_type: str = "image/jpeg") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type)


def exif_of(content: bytes) -> tuple[dict[int, object], dict[int, object]]:
    """The tags of the photo and its place."""
    exif = Image.open(io.BytesIO(content)).getexif()
    return dict(exif), dict(exif.get_ifd(ExifTags.IFD.GPSInfo))


class PhotoRenderingTests(UiTestCase):
    """The same rule for every photo (MAT-090)."""

    def test_place_stays_everything_else_goes(self) -> None:
        rendered = photos.render_photo_upload(upload(jpeg()))
        tags, gps = exif_of(rendered.photo)
        self.assertEqual(set(gps), GPS_KEYS)
        self.assertEqual(tuple(gps[ExifTags.GPS.GPSLatitude]), (52.0, 31.0, 12.0))
        self.assertEqual(gps[ExifTags.GPS.GPSLatitudeRef], "N")
        self.assertEqual(float(gps[ExifTags.GPS.GPSAltitude]), 34.0)
        self.assertEqual(set(tags) - {ExifTags.Base.GPSInfo}, set())
        raw = rendered.photo
        for secret in (b"Testphone", b"Geheimer Kommentar", b"xmpmeta", b"2027:03:01"):
            self.assertNotIn(secret, raw)
        self.assertEqual((rendered.width, rendered.height), (2048, 1365))

    def test_the_preview_has_no_metadata_at_all(self) -> None:
        rendered = photos.render_photo_upload(upload(jpeg()))
        tags, gps = exif_of(rendered.thumbnail)
        self.assertEqual((tags, gps), ({}, {}))
        self.assertEqual(max(Image.open(io.BytesIO(rendered.thumbnail)).size), 640)

    def test_a_small_photo_is_made_anew_too(self) -> None:
        original = jpeg(300, 200)
        rendered = photos.render_photo_upload(upload(original))
        self.assertEqual((rendered.width, rendered.height), (300, 200))
        self.assertNotIn(b"Testphone", rendered.photo)
        self.assertEqual(set(exif_of(rendered.photo)[1]), GPS_KEYS)

    def test_a_photo_without_a_place_gets_none(self) -> None:
        rendered = photos.render_photo_upload(upload(jpeg(place=False)))
        self.assertEqual(exif_of(rendered.photo), ({}, {}))

    def test_an_implausible_place_is_dropped(self) -> None:
        image = Image.new("RGB", (50, 50), (1, 2, 3))
        exif = Image.Exif()
        gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
        gps[ExifTags.GPS.GPSLatitudeRef] = "N"
        gps[ExifTags.GPS.GPSLatitude] = (200.0, 0.0, 0.0)
        gps[ExifTags.GPS.GPSLongitudeRef] = "E"
        gps[ExifTags.GPS.GPSLongitude] = (13.0, 0.0, 0.0)
        out = io.BytesIO()
        image.save(out, "JPEG", exif=exif)
        rendered = photos.render_photo_upload(upload(out.getvalue()))
        self.assertEqual(exif_of(rendered.photo)[1], {})

    def test_a_png_becomes_a_jpeg(self) -> None:
        rendered = photos.render_photo_upload(upload(png(), "bild.png", "image/png"))
        self.assertEqual(Image.open(io.BytesIO(rendered.photo)).format, "JPEG")

    def test_whatever_is_not_a_photo_is_refused(self) -> None:
        with self.assertRaises(photos.PhotoError):
            photos.render_photo_upload(upload(b"%PDF-1.4\n%%EOF\n", "x.jpg"))

    def test_a_receipt_keeps_the_place_and_nothing_else(self) -> None:
        from rentalars.timetracking.expenses import prepare_receipt

        stored = prepare_receipt(upload(jpeg(), "beleg.jpg"))
        content = stored[0].read()
        self.assertEqual(set(exif_of(content)[1]), GPS_KEYS)
        self.assertNotIn(b"Testphone", content)


class DefectPhotoTests(UiTestCase):
    def test_the_photo_of_a_report_is_made_anew(self) -> None:
        item = make_items(make_model("Kabel", make_product("K-005")))[0]
        report = services.report_defect(item, "Stecker lose", photo=upload(jpeg()), user=self.admin_user)
        content = report.photo.read()
        self.assertEqual(set(exif_of(content)[1]), GPS_KEYS)
        self.assertNotIn(b"Testphone", content)
        self.assertLessEqual(max(Image.open(io.BytesIO(content)).size), 2048)


class PhotoPanelTests(UiTestCase):
    """Photos of a model and of an item (MAT-090)."""

    def setUp(self) -> None:
        super().setUp()
        self.model = make_model("Scheinwerfer", make_product("L-010"), category_code="L")
        self.item = make_items(self.model)[0]
        self.model_url = reverse("material:model_photos", args=[self.model.pk])
        self.item_url = reverse("material:item_photos", args=[self.item.pk])

    def test_upload_several_photos_to_a_model(self) -> None:
        response = self.client.post(
            self.model_url, {"photos": [upload(jpeg(), "a.jpg"), upload(png(), "b.png", "image/png")]}, follow=True
        )
        page = self.assert_ok(response)
        self.assertIn("2 Fotos gespeichert", page)
        stored = MaterialFile.objects.filter(material_model=self.model)
        self.assertEqual(stored.count(), 2)
        for photo in stored:
            self.assertEqual(photo.kind, MaterialFileKind.PICTURE)
            self.assertTrue(photo.original_name.endswith(".jpg"))
            self.assertTrue(photo.thumbnail)
        self.assertIn(reverse("material:file_small", args=[stored[0].pk]), page)
        self.assertIn('id="photos"', page)

    def test_the_preview_and_the_whole_photo_are_delivered(self) -> None:
        self.client.post(self.model_url, {"photos": upload(jpeg())})
        photo = MaterialFile.objects.get()
        small = self.client.get(reverse("material:file_small", args=[photo.pk]))
        whole = self.client.get(reverse("material:file", args=[photo.pk]))
        self.assertEqual((small.status_code, whole.status_code), (200, 200))
        small_size = Image.open(io.BytesIO(b"".join(small.streaming_content))).size
        whole_size = Image.open(io.BytesIO(b"".join(whole.streaming_content))).size
        self.assertEqual(max(small_size), 640)
        self.assertEqual(max(whole_size), 2048)

    def test_a_photo_before_0_11_9_has_no_preview_and_is_delivered_whole(self) -> None:
        self.client.post(self.model_url, {"photos": upload(jpeg(400, 300))})
        photo = MaterialFile.objects.get()
        photo.thumbnail.delete(save=True)
        small = self.client.get(reverse("material:file_small", args=[photo.pk]))
        self.assertEqual(small.status_code, 200)

    def test_the_head_shows_the_first_photo_an_item_shows_that_of_its_model(self) -> None:
        self.client.post(self.model_url, {"photos": upload(jpeg(), "modell.jpg")})
        model_photo = MaterialFile.objects.get()
        item_page = self.assert_ok(self.client.get(reverse("material:item_detail", args=[self.item.pk])))
        self.assertIn(reverse("material:file_small", args=[model_photo.pk]), item_page)
        self.assertIn("Fotos des Modells", item_page)
        self.client.post(self.item_url, {"photos": upload(jpeg(), "exemplar.jpg")})
        own = MaterialFile.objects.get(item=self.item)
        head = self.assert_ok(self.client.get(reverse("material:item_timeline", args=[self.item.pk])))
        self.assertIn(reverse("material:file_small", args=[own.pk]), head)
        self.assertNotIn(reverse("material:file_small", args=[model_photo.pk]), head)

    def test_a_photo_of_the_item_is_not_on_the_model(self) -> None:
        self.client.post(self.item_url, {"photos": upload(jpeg())})
        own = MaterialFile.objects.get()
        page = self.assert_ok(self.client.get(reverse("material:model_detail", args=[self.model.pk])))
        self.assertNotIn(reverse("material:file_small", args=[own.pk]), page)
        self.assertIn("Noch keine Fotos", page)

    def test_remove_a_photo_removes_the_files(self) -> None:
        self.client.post(self.item_url, {"photos": upload(jpeg(400, 300))})
        photo = MaterialFile.objects.get()
        paths = [Path(photo.file.path), Path(photo.thumbnail.path)]
        self.assertTrue(all(path.exists() for path in paths))
        response = self.client.post(reverse("material:file_delete", args=[photo.pk]), follow=True)
        self.assertEqual(
            response.redirect_chain[-1][0], reverse("material:item_detail", args=[self.item.pk]) + "#photos"
        )
        self.assertIn("Foto entfernt", self.assert_ok(response))
        self.assertFalse(MaterialFile.objects.exists())
        self.assertFalse(any(path.exists() for path in paths))

    def test_a_document_is_removed_from_the_tab_files(self) -> None:
        manual = services.add_file(self.model, upload(b"%PDF-1.4\n%%EOF\n", "a.pdf", "application/pdf"), kind="manual")
        response = self.client.post(reverse("material:file_delete", args=[manual.pk]))
        self.assertRedirects(
            response, reverse("material:model_files", args=[self.model.pk]), fetch_redirect_response=False
        )

    def test_what_is_not_a_photo_is_told_by_name(self) -> None:
        response = self.client.post(
            self.model_url,
            {"photos": [upload(b"MZ", "virus.jpg"), upload(jpeg(400, 300), "gut.jpg")]},
            follow=True,
        )
        page = self.assert_ok(response)
        self.assertIn("virus.jpg", page)
        self.assertIn("1 Foto gespeichert", page)
        self.assertEqual(MaterialFile.objects.count(), 1)

    def test_nothing_chosen_and_too_many(self) -> None:
        self.assertIn("Wähle mindestens ein Foto", self.assert_ok(self.client.post(self.model_url, {}, follow=True)))
        many = [upload(png(), f"{number}.png", "image/png") for number in range(21)]
        page = self.assert_ok(self.client.post(self.model_url, {"photos": many}, follow=True))
        self.assertIn("Höchstens 20 Fotos auf einmal", page)
        self.assertFalse(MaterialFile.objects.exists())

    def test_the_tab_files_has_no_photos_and_no_kind_picture(self) -> None:
        self.client.post(self.model_url, {"photos": upload(jpeg(400, 300), "modellfoto.jpg")})
        page = self.assert_ok(self.client.get(reverse("material:model_files", args=[self.model.pk])))
        self.assertNotIn("modellfoto.jpg", page)
        self.assertNotIn('value="picture"', page)
        item_files = self.assert_ok(self.client.get(reverse("material:item_files", args=[self.item.pk])))
        self.assertNotIn("modellfoto.jpg", item_files)

    def test_whoever_may_only_read_sees_the_photos_but_cannot_change_them(self) -> None:
        self.client.post(self.model_url, {"photos": upload(jpeg(400, 300))})
        photo = MaterialFile.objects.get()
        reader = self.browser_for("rita", "Nur-Lesen")
        page = self.assert_ok(reader.get(reverse("material:model_detail", args=[self.model.pk])))
        self.assertIn(reverse("material:file_small", args=[photo.pk]), page)
        self.assertNotIn(self.model_url, page)
        self.assertNotIn(reverse("material:file_delete", args=[photo.pk]), page)
        self.assertEqual(reader.post(self.model_url, {"photos": upload(jpeg(400, 300))}).status_code, 403)
        self.assertEqual(reader.post(self.item_url, {"photos": upload(jpeg(400, 300))}).status_code, 403)
        self.assertEqual(reader.post(reverse("material:file_delete", args=[photo.pk])).status_code, 403)
        self.assertEqual(MaterialFile.objects.count(), 1)

    def test_get_is_not_allowed_and_anonymous_is_sent_to_the_login(self) -> None:
        self.assertEqual(self.client.get(self.model_url).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.post(self.model_url, {}).status_code, 302)


class ReviewFixTests(UiTestCase):
    """What the independent review found."""

    def setUp(self) -> None:
        super().setUp()
        self.model = make_model("Scheinwerfer", make_product("L-010"), category_code="L")
        self.item = make_items(self.model)[0]

    def test_a_deleted_row_takes_its_files_from_the_disk_when_it_is_committed(self) -> None:
        photo = services.add_file(self.item, upload(jpeg(400, 300)), kind=MaterialFileKind.PICTURE)
        paths = [Path(photo.file.path), Path(photo.thumbnail.path)]
        with self.captureOnCommitCallbacks(execute=True):
            photo.delete()
        self.assertFalse(any(path.exists() for path in paths))

    def test_a_file_that_another_row_still_shows_stays(self) -> None:
        photo = services.add_file(self.item, upload(jpeg(400, 300)), kind=MaterialFileKind.PICTURE)
        MaterialFile.objects.create(
            item=self.item, kind=MaterialFileKind.OTHER, original_name="zweite.jpg", file=photo.file.name
        )
        path = Path(photo.file.path)
        with self.captureOnCommitCallbacks(execute=True):
            photo.delete()
        self.assertTrue(path.exists())

    def test_deleting_the_item_removes_its_photos(self) -> None:
        photo = services.add_file(self.item, upload(jpeg(400, 300)), kind=MaterialFileKind.PICTURE)
        path = Path(photo.file.path)
        with self.captureOnCommitCallbacks(execute=True):
            services.delete_item(self.item)
        self.assertFalse(MaterialFile.objects.exists())
        self.assertFalse(path.exists())

    def test_deleting_a_model_removes_its_files(self) -> None:
        """On MariaDB Django empties the owner of a file first, which the rule "one owner" forbids (found there)."""
        model = make_model("Leuchte", make_product("L-011"), category_code="L")
        stored = services.add_file(model, upload(jpeg(400, 300)), kind=MaterialFileKind.PICTURE)
        path = Path(stored.file.path)
        with self.captureOnCommitCallbacks(execute=True):
            model.delete()
        self.assertFalse(MaterialFile.objects.filter(pk=stored.pk).exists())
        self.assertFalse(path.exists())

    def test_a_picture_as_manual_or_other_file_is_made_anew_but_an_invoice_stays(self) -> None:
        other = services.add_file(self.model, upload(jpeg(), "Aufbau.jpg"), kind=MaterialFileKind.MANUAL)
        self.assertEqual((other.kind, other.original_name), (MaterialFileKind.MANUAL, "Aufbau.jpg"))
        self.assertTrue(other.thumbnail)
        content = other.file.read()
        self.assertNotIn(b"Testphone", content)
        self.assertEqual(max(Image.open(io.BytesIO(content)).size), 2048)
        scan = services.add_file(self.model, upload(jpeg(), "Rechnung.jpg"), kind=MaterialFileKind.INVOICE)
        self.assertFalse(scan.thumbnail)
        self.assertIn(b"Testphone", scan.file.read())

    def test_a_png_as_other_file_gets_the_ending_jpg(self) -> None:
        stored = services.add_file(self.model, upload(png(), "Plan.png", "image/png"), kind=MaterialFileKind.OTHER)
        self.assertEqual(stored.original_name, "Plan.jpg")

    def test_the_first_photo_uploaded_is_the_head_picture(self) -> None:
        from rentalars.material.photo_views import head_picture

        first = services.add_file(self.model, upload(jpeg(300, 200), "a.jpg"), kind=MaterialFileKind.PICTURE)
        services.add_file(self.model, upload(jpeg(300, 200), "b.jpg"), kind=MaterialFileKind.PICTURE)
        rights = self.admin_user.rights if hasattr(self.admin_user, "rights") else None
        from rentalars.accounts.rights import Rights

        rights = rights or Rights.for_user(self.admin_user)
        self.assertEqual(head_picture(self.model, rights).pk, first.pk)

    def test_a_16_bit_grey_picture_is_not_white(self) -> None:
        grey = Image.new("I;16", (20, 20), 30000)
        out = io.BytesIO()
        grey.save(out, "PNG")
        rendered = photos.render_photo_upload(upload(out.getvalue(), "g.png", "image/png"))
        value = Image.open(io.BytesIO(rendered.photo)).convert("L").getpixel((5, 5))
        self.assertTrue(80 < value < 150, value)

    def test_a_large_colour_profile_is_dropped_a_small_one_stays(self) -> None:
        def with_profile(size: int) -> bytes:
            out = io.BytesIO()
            Image.new("RGB", (30, 30), (9, 9, 9)).save(out, "JPEG", icc_profile=b"x" * size)
            return out.getvalue()

        small = photos.render_photo_upload(upload(with_profile(2000)))
        large = photos.render_photo_upload(upload(with_profile(photos.MAX_ICC_BYTES + 1000)))
        self.assertIn("icc_profile", Image.open(io.BytesIO(small.photo)).info)
        self.assertNotIn("icc_profile", Image.open(io.BytesIO(large.photo)).info)

    def test_heic_is_told_by_name(self) -> None:
        heic = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00heicmif1"
        with self.assertRaises(photos.PhotoError) as caught:
            photos.render_photo_upload(upload(heic, "IMG.heic", "image/heic"))
        self.assertIn("HEIC", str(caught.exception))

    def test_a_receipt_is_refused_as_gif_and_is_limited_in_pixels(self) -> None:
        from django.core.exceptions import ValidationError

        from rentalars.timetracking.expenses import prepare_receipt

        out = io.BytesIO()
        Image.new("RGB", (20, 20)).save(out, "GIF")
        with self.assertRaises(ValidationError):
            prepare_receipt(upload(out.getvalue(), "b.gif", "image/gif"))
        content = prepare_receipt(upload(jpeg(3000, 1000), "b.jpg"))[0].read()
        self.assertEqual(max(Image.open(io.BytesIO(content)).size), 2000)

    def test_a_png_a_webp_and_a_second_photo_keep_the_place_where_the_format_can_carry_it(self) -> None:
        exif = Image.Exif()
        exif[ExifTags.Base.Make] = "Testphone"  # without a tag of its own the block would not be written
        gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
        gps[ExifTags.GPS.GPSLatitudeRef] = "N"
        gps[ExifTags.GPS.GPSLatitude] = (52.0, 31.0, 12.0)
        gps[ExifTags.GPS.GPSLongitudeRef] = "E"
        gps[ExifTags.GPS.GPSLongitude] = (13.0, 24.0, 18.0)
        for form, kind in (("PNG", "image/png"), ("WEBP", "image/webp")):
            out = io.BytesIO()
            Image.new("RGB", (60, 40), (5, 5, 5)).save(out, form, exif=exif)
            rendered = photos.render_photo_upload(upload(out.getvalue(), f"x.{form.lower()}", kind))
            self.assertEqual(set(exif_of(rendered.photo)[1]), {1, 2, 3, 4}, form)

    def test_nineteen_good_photos_and_one_bad_one(self) -> None:
        url = reverse("material:model_photos", args=[self.model.pk])
        files = [upload(png(), f"{number}.png", "image/png") for number in range(19)] + [upload(b"MZ", "kaputt.jpg")]
        page = self.assert_ok(self.client.post(url, {"photos": files}, follow=True))
        self.assertIn("kaputt.jpg", page)
        self.assertEqual(MaterialFile.objects.count(), 19)

    def test_the_preview_of_a_picture_is_for_whoever_may_see_the_item_only(self) -> None:
        photo = services.add_file(self.model, upload(jpeg(400, 300)), kind=MaterialFileKind.PICTURE)
        reader = self.browser_for("rita", "Nur-Lesen")
        self.assertEqual(reader.get(reverse("material:file_small", args=[photo.pk])).status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("material:file_small", args=[photo.pk])).status_code, 302)


class PhotoApiTests(ApiTestCase):
    """The API names the preview of a photo (API-002)."""

    def test_the_preview_of_a_photo(self) -> None:
        model = make_model("Scheinwerfer", make_product("L-010"), category_code="L")
        response = self.admin.post(
            f"{API}/material-models/{model.pk}/files", {"file": upload(jpeg()), "kind": "picture"}, format="multipart"
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["thumbnail_url"], f"/api/v1/material-files/{body['id']}/thumbnail")
        small = self.admin.get(body["thumbnail_url"])
        self.assertEqual(small.status_code, 200)
        self.assertEqual(max(Image.open(io.BytesIO(b"".join(small.streaming_content))).size), 640)
        whole = Image.open(
            io.BytesIO(b"".join(self.admin.get(f"{API}/material-files/{body['id']}/content").streaming_content))
        )
        self.assertEqual(max(whole.size), 2048)
        self.assertEqual(set(dict(whole.getexif().get_ifd(ExifTags.IFD.GPSInfo))), GPS_KEYS)

    def test_a_document_has_no_preview(self) -> None:
        model = make_model("Scheinwerfer", make_product("L-010"), category_code="L")
        manual = services.add_file(model, upload(b"%PDF-1.4\n%%EOF\n", "a.pdf", "application/pdf"), kind="manual")
        listed = self.admin.get(f"{API}/material-files/{manual.pk}").json()
        self.assertIsNone(listed["thumbnail_url"])
        self.assert_error(self.admin.get(f"{API}/material-files/{manual.pk}/thumbnail"), 404, "not_found")

    def test_a_reader_may_see_the_preview(self) -> None:
        model = make_model("Scheinwerfer", make_product("L-010"), category_code="L")
        photo = services.add_file(model, upload(jpeg(400, 300)), kind="picture")
        reader = self.client_for("rita", "Nur-Lesen")
        self.assertEqual(reader.get(f"{API}/material-files/{photo.pk}/thumbnail").status_code, 200)
