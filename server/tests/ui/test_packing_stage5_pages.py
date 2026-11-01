# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser tests of the packlists of stage 5 (PCK-004, PCK-008, PCK-013, PCK-015, PCK-017, PCK-018, PCK-022)."""

from __future__ import annotations

import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from rentalars.material.models import ItemStatus, MaterialItem
from rentalars.packing import services
from rentalars.packing.models import Allocation, Packlist, PacklistStatus
from rentalars.projects.models import MaterialLine
from tests.helpers import add_line, make_project, make_stock
from tests.ui.base import UiTestCase


def png_file() -> SimpleUploadedFile:
    """A tiny real PNG image."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (238, 89, 31)).save(buffer, format="PNG")
    return SimpleUploadedFile("defekt.png", buffer.getvalue(), content_type="image/png")


class PacklistStage5Tests(UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest")
        self.cables = make_stock("K-005", 10, "XLR-Kabel")
        self.lights = make_stock("L-010", 4, "PAR 64")
        self.cable_line = add_line(self.project, self.cables, 6).line
        self.light_line = add_line(self.project, self.lights, 2).line
        self.url = reverse("packing:packlist", args=[self.project.pk])

    def test_second_packlist_with_its_lines_and_pdf(self) -> None:
        self.client.post(reverse("packing:packlist_create", args=[self.project.pk]), {"title": "LKW 2"})
        truck = Packlist.objects.get(title="LKW 2")
        lines_page = self.assert_ok(self.client.get(reverse("packing:packlist_lines", args=[self.project.pk])))
        self.assertIn("LKW 2", lines_page)
        main = services.get_packlist(self.project)
        self.client.post(
            reverse("packing:packlist_lines", args=[self.project.pk]),
            {f"line-{self.cable_line.pk}": main.pk, f"line-{self.light_line.pk}": truck.pk},
        )
        page = self.assert_ok(self.client.get(reverse("packing:packlist_detail", args=[self.project.pk, truck.pk])))
        self.assertIn("PAR 64", page)
        self.assertNotIn("XLR-Kabel", page)
        pdf = self.client.get(reverse("packing:packlist_pdf", args=[self.project.pk, truck.pk]))
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        base = reverse("packing:packlist_detail", args=[self.project.pk, truck.pk])
        self.client.post(base + "edit/", {"title": "LKW 3", "note": "Rampe 2"})
        truck.refresh_from_db()
        self.assertEqual((truck.title, truck.note), ("LKW 3", "Rampe 2"))
        self.client.post(base + "delete/")
        self.assertFalse(Packlist.objects.filter(pk=truck.pk).exists())

    def test_partial_issue_and_return(self) -> None:
        self.client.post(
            reverse("packing:row", args=[self.project.pk]),
            {"mode": "pack", "line": self.cable_line.pk, "product": self.cables.pk, "quantity": "4"},
        )
        self.client.post(reverse("packing:action", args=[self.project.pk, "issue"]), {"only_packed": "1"})
        packlist = services.get_packlist(self.project)
        self.assertEqual(packlist.status, PacklistStatus.PARTLY_ISSUED)
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn("Alles ausgeben", page)  # PCK-025: "Ausgeben" books what is ticked, this the rest
        self.assertIn("4 von 6 ausgegeben", page)
        returned = self.assert_ok(self.client.get(self.url, {"mode": "return"}))
        self.assertIn("4 von 6 ausgegeben", returned)
        self.client.post(
            reverse("packing:row", args=[self.project.pk]),
            {"mode": "return", "line": self.cable_line.pk, "product": self.cables.pk, "quantity": "4"},
        )
        self.client.post(reverse("packing:action", args=[self.project.pk, "issue"]), {"only_packed": "0"})
        packlist.refresh_from_db()
        self.assertEqual(packlist.status, PacklistStatus.ISSUED)

    def test_choose_items_in_the_dialog(self) -> None:
        dialog = self.assert_ok(
            self.client.get(
                reverse("packing:items", args=[self.project.pk]),
                {"line": self.light_line.pk, "product": self.lights.pk},
                HTTP_HX_REQUEST="true",
            )
        )
        self.assertIn("Exemplare für L-010", dialog)
        first, second = MaterialItem.objects.for_product(self.lights.pk).order_by("inventory_number")[:2]
        self.client.post(
            reverse("packing:action", args=[self.project.pk, "choose-items"]),
            {"line": self.light_line.pk, "product": self.lights.pk, "items": [first.pk, second.pk]},
        )
        self.assertEqual(Allocation.objects.filter(issued_at__isnull=True).count(), 2)
        self.assertIn(first.display_id, self.assert_ok(self.client.get(self.url)))

    def test_order_contents_and_changes(self) -> None:
        page = self.assert_ok(self.client.get(self.url, {"order": "category", "contents": "1"}))
        self.assertIn("Inhalt der Behälter ausblenden", page)
        self.assertIn(">Kabel<", page.replace("</div>", "<").replace('<div class="pack-kit">', ">"))
        self.client.post(
            reverse("packing:row", args=[self.project.pk]),
            {"mode": "pack", "line": self.cable_line.pk, "product": self.cables.pk, "quantity": "6"},
        )
        MaterialLine.objects.filter(pk=self.cable_line.pk).update(quantity=8)
        self.assertIn("Die Planung hat sich seit Packbeginn geändert", self.assert_ok(self.client.get(self.url)))
        self.client.post(reverse("packing:action", args=[self.project.pk, "acknowledge-changes"]))
        self.assertNotIn("seit Packbeginn geändert", self.assert_ok(self.client.get(self.url)))

    def test_addendum_and_defect_on_return(self) -> None:
        tape = make_stock("V-001", 20, "Gaffa")
        response = self.client.post(
            reverse("packing:action", args=[self.project.pk, "add-material"]),
            {"product": tape.pk, "quantity": "3"},
            follow=True,
        )
        self.assertIn("V-001 als Nachtrag ergänzt.", self.messages_of(response))
        self.assertTrue(MaterialLine.objects.get(product=tape).is_addendum)
        self.client.post(reverse("packing:action", args=[self.project.pk, "issue"]), {"only_packed": "0"})
        light = MaterialItem.objects.for_product(self.lights.pk).first()
        response = self.client.post(
            reverse("packing:action", args=[self.project.pk, "report-defect"]),
            {"item": light.display_id, "description": "Lampe flackert", "photo": png_file()},
            follow=True,
        )
        self.assertIn(
            f"Defekt von {light.display_id} gemeldet. Das Lager hat Bescheid bekommen.", self.messages_of(response)
        )
        light.refresh_from_db()
        self.assertEqual(light.status, ItemStatus.DEFECTIVE)
