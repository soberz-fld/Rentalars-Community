# SPDX-License-Identifier: GPL-3.0-or-later
"""The chosen outgoing documents as one ZIP file (Buchhaltung → Ausgangsbelege, ``outgoing_download``).

The requirement: the chosen outgoing documents ("Ausgangsbelege") can be downloaded.
"""

from __future__ import annotations

import io
import tempfile
import zipfile

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import override_settings
from django.urls import reverse

from rentalars.documents.models import Document
from rentalars.documents.outgoing_tables import OUTGOING_TABLE
from tests.ui.base import UiTestCase
from tests.unit.test_091_accounting import DocumentsSetup

MEDIA = tempfile.mkdtemp(prefix="rentalars-test-media-")
NAME = f"sel_{OUTGOING_TABLE.key}"


@override_settings(MEDIA_ROOT=MEDIA)
class DownloadTests(DocumentsSetup, UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        for document in (self.offer, self.order):
            default_storage.save(document.file.name, ContentFile(b"%PDF-1.7 " + document.number.encode()))
        Document.objects.filter(pk=self.order.pk).update(
            xml_file="documents/AB-2027-0001.xml"
        )  # documents are immutable
        default_storage.save("documents/AB-2027-0001.xml", ContentFile(b"<Invoice/>"))
        self.url = reverse("documents:outgoing_download")

    def post(self, ids: list[int], client=None):
        return (client or self.client).post(
            self.url, {"table": OUTGOING_TABLE.key, "next": "/accounting/documents/", NAME: ids}
        )

    def test_the_list_offers_the_download(self) -> None:
        page = self.assert_ok(self.client.get(reverse("documents:outgoing")))
        self.assertIn("Gewählte Belege herunterladen (ZIP)", page)
        self.assertIn(f'name="{NAME}" value="{self.offer.pk}"', page)

    def test_the_chosen_documents_come_as_one_zip_with_pdf_and_xrechnung(self) -> None:
        response = self.post([self.offer.pk, self.order.pk])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertIn("Ausgangsbelege-", response["Content-Disposition"])
        with zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content))) as archive:
            self.assertEqual(sorted(archive.namelist()), ["AB-2027-0001.pdf", "AB-2027-0001.xml", "AN-2027-0001.pdf"])
            self.assertEqual(archive.read("AN-2027-0001.pdf"), b"%PDF-1.7 AN-2027-0001")
            self.assertEqual(archive.read("AB-2027-0001.xml"), b"<Invoice/>")

    def test_a_missing_file_and_an_unknown_key_are_named_not_hidden(self) -> None:
        response = self.post([self.offer.pk, self.delivery.pk, 99999])
        self.assertEqual(response.status_code, 200)  # the offer is packed; the delivery note has no file stored
        with zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content))) as archive:
            self.assertEqual(archive.namelist(), ["AN-2027-0001.pdf"])
        texts = self.messages_of(self.client.get(reverse("documents:outgoing")))
        self.assertTrue(any("LS-2027-0001.pdf" in text and "99999" in text for text in texts), texts)

    def test_nothing_chosen_and_nothing_to_pack_go_back_with_a_hint(self) -> None:
        for ids, word in (([], "mindestens eine Zeile"), ([self.delivery.pk], "nichts packen")):
            response = self.post(ids)
            self.assertEqual(response.status_code, 302)
            texts = self.messages_of(self.client.get(reverse("documents:outgoing")))
            self.assertTrue(any(word in text for text in texts), texts)

    def test_only_who_may_see_the_documents_downloads_them(self) -> None:
        from tests.helpers import make_user

        nobody = make_user("nina")
        self.assertEqual(self.post([self.offer.pk], self.browser_of(nobody)).status_code, 403)
        self.assertEqual(self.client.get(self.url).status_code, 405)
