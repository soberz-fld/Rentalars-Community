# SPDX-License-Identifier: GPL-3.0-or-later
"""The page that takes over a lighting plot from an MVR file into a project (PRJ-077)."""

from __future__ import annotations

from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.products.models import FixtureTypeMapping
from rentalars.projects import mvr
from rentalars.projects.models import ProjectMembership, ProjectStatus
from tests.helpers import add_group, make_items, make_model, make_product, make_project, make_user
from tests.ui.base import UiTestCase, form_data
from tests.unit.test_mvr_import import ROBIN, SKYPANEL, make_mvr, sample_plot, scene


def upload(name: str = "Stadtfest.mvr", data: bytes | None = None) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, data if data is not None else sample_plot(), content_type="application/zip")


class MvrPageTests(UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.spot = make_product("L-010", "Robe Robin T1 Profile", price="80.00")
        make_items(make_model("Robin T1 Profile", self.spot, manufacturer="Robe"), 6)
        self.panel = make_product("L-020", "LED-Fläche SkyPanel S60", price="60.00")
        self.hazer = make_product("F-001", "Nebelmaschine Unique 2.1")
        self.project = make_project()
        self.url = reverse("projects:mvr_import", args=[self.project.pk])

    def test_upload_assign_and_add(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn("MVR-Datei importieren", page)  # PRJ-086: was "Lichtplot aus einer MVR-Datei übernehmen"
        self.assertIn('accept=".mvr"', page)
        response = self.client.post(self.url, {"step": "upload", "file": upload()})
        self.assertRedirects(response, self.url)

        assignment = self.client.get(self.url)
        text = self.assert_ok(assignment)
        self.assertIn("Stadtfest.mvr · 10 Geräte · 5 Typen", text)
        self.assertIn("2 Objekte ohne GDTF-Datei", text)
        self.assertIn("Robe Lighting Robin T1 Profile", text)
        self.assertIn("Modus Mode 1 - Standard 16 bit", text)
        self.assertIn("z. B. 101 Spot 1, 102 Spot 2, 103 Spot 3", text)
        self.assertIn("% ähnlich", text)
        data = form_data(assignment, containing="key_0")
        order = [data[f"key_{index}"] for index in range(5)]
        robin_1 = order.index(mvr.type_key(ROBIN, "Mode 1 - Standard 16 bit"))
        robin_2 = order.index(mvr.type_key(ROBIN, "Mode 2 - Basic"))
        sky = order.index(mvr.type_key(SKYPANEL, "CCT"))
        hazer = order.index(mvr.type_key("Generic@Hazer.gdtf", "Default"))
        truss = order.index(mvr.type_key("Prolyte@H30V_2m.gdtf", ""))
        # Preselected: the similar products; nothing for the hazer and the truss.
        self.assertEqual(
            [data[f"choice_{index}"] for index in (robin_1, robin_2, sky, hazer, truss)],
            [str(self.spot.pk), str(self.spot.pk), str(self.panel.pk), "skip", "skip"],
        )
        self.assertEqual(
            (data[f"quantity_{robin_1}"], data["group"], data["group_name"]), ("5", "new", "MVR Stadtfest")
        )

        data.update(
            {
                f"choice_{robin_2}": "skip",
                f"choice_{hazer}": "other",
                f"other_{hazer}": str(self.hazer.pk),
                f"quantity_{sky}": "3",
                "step": "apply",
            }
        )
        done = self.client.post(self.url, data, follow=True)
        self.assertRedirects(done, reverse("projects:detail", args=[self.project.pk]))
        self.assertIn("3 Positionen aus Stadtfest.mvr hinzugefügt.", self.messages_of(done))
        group = self.project.groups.get()
        self.assertEqual(group.name, "MVR Stadtfest")
        self.assertEqual(
            sorted((line.product.article_number, line.quantity) for line in group.lines.all()),
            [("F-001", Decimal("1.00")), ("L-010", Decimal("5.00")), ("L-020", Decimal("3.00"))],
        )
        # Remembered for the next plot: the hazer now comes first.
        self.assertEqual(FixtureTypeMapping.objects.count(), 3)
        self.client.post(self.url, {"step": "upload", "file": upload("Zweiter.mvr")})
        again = form_data(self.client.get(self.url), containing="key_0")
        self.assertEqual(again[f"choice_{hazer}"], str(self.hazer.pk))
        self.assertIn("gemerkt", self.assert_ok(self.client.get(self.url)))
        self.client.post(self.url, {"step": "discard"})
        self.assertIn('name="file"', self.assert_ok(self.client.get(self.url)))

    def test_existing_group_and_problems(self) -> None:
        lights = add_group(self.project, "Licht")
        self.client.post(self.url, {"step": "upload", "file": upload()})
        page = self.client.get(self.url)
        data = form_data(page, containing="key_0", group=str(lights.pk), step="apply")
        hazer = [data[f"key_{index}"] for index in range(5)].index(mvr.type_key("Generic@Hazer.gdtf", "Default"))
        data[f"choice_{hazer}"] = "other"
        data[f"other_{hazer}_label"] = "Nebel"
        response = self.client.post(self.url, data)
        text = self.assert_ok(response)
        self.assertIn("Wähl ein Produkt für Generic Hazer oder übernimm den Typ nicht.", self.messages_of(response))
        self.assertIn('value="Nebel"', text)  # what was typed stays
        self.assertFalse(self.project.material_lines.exists())

        data[f"choice_{hazer}"] = "skip"
        data["key_0"] = "something else"
        self.assertIn(
            "Die Seite passt nicht mehr zum Plot. Bitte wähl die Datei noch einmal.",
            self.messages_of(self.client.post(self.url, data)),
        )
        data["key_0"] = form_data(page, containing="key_0")["key_0"]
        self.client.post(self.url, data)
        self.assertEqual(set(lights.lines.values_list("product__article_number", flat=True)), {"L-010", "L-020"})

    def test_wrong_files(self) -> None:
        for name, data, message in (
            ("plot.zip", sample_plot(), "Wähl eine Datei mit der Endung .mvr."),
            ("plot.mvr", b"kein zip", "Die Datei ist keine MVR-Datei: MVR-Dateien sind ZIP-Archive."),
            ("plot.mvr", make_mvr(scene()), "Der Plot enthält kein Gerät mit GDTF-Datei."),
        ):
            text = self.assert_ok(self.client.post(self.url, {"step": "upload", "file": upload(name, data)}))
            self.assertIn(message, text)
        self.assertNotIn(f"mvr_plot_{self.project.pk}", self.client.session)

    def test_rights(self) -> None:
        """Adding lines needs write access to projects and the right to edit this project (AUT-016, AUT-025)."""
        warehouse = self.browser_for("luka", "Lager")
        self.assertEqual(warehouse.get(self.url).status_code, 403)
        role = Role.objects.create(
            name="Projektleitung extern", module_levels={"projects": 2, "products": 1}, project_scope="assigned"
        )
        external = make_user("extern")
        external.roles.set([role])
        browser = self.browser_of(external)
        self.assertEqual(browser.get(self.url).status_code, 404)
        membership = ProjectMembership.objects.create(project=self.project, user=external, level="read")
        self.assertEqual(browser.get(self.url).status_code, 403)
        membership.level = "edit"
        membership.save()
        self.assert_ok(browser.get(self.url))
        self.assertEqual(self.client.get("/projects/9999-9999/mvr/").status_code, 404)

        closed = make_project("Altes Fest", status=ProjectStatus.CLOSED)
        response = self.client.get(reverse("projects:mvr_import", args=[closed.pk]), follow=True)
        self.assertRedirects(response, reverse("projects:detail", args=[closed.pk]))
        self.assertIn("Dieses Projekt ist abgeschlossen", " ".join(self.messages_of(response)))
