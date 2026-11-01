# SPDX-License-Identifier: GPL-3.0-or-later
"""API: taking over a lighting plot from an MVR file into a project (PRJ-077)."""

from __future__ import annotations

import json
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile

from rentalars.products.models import FixtureTypeMapping
from rentalars.projects import mvr
from tests.api.base import API, ApiTestCase
from tests.helpers import add_group, make_items, make_model, make_product, make_project
from tests.unit.test_mvr_import import ROBIN, SKYPANEL, sample_plot


def mvr_file(name: str = "Stadtfest.mvr", data: bytes | None = None) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, data if data is not None else sample_plot(), content_type="application/zip")


class MvrApiTests(ApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.spot = make_product("L-010", "Robe Robin T1 Profile", price="80.00")
        make_items(make_model("Robin T1 Profile", self.spot, manufacturer="Robe"), 6)
        self.panel = make_product("L-020", "LED-Fläche SkyPanel S60")
        self.project = make_project()
        self.url = f"{API}/projects/{self.project.pk}/mvr"
        self.robin = mvr.type_key(ROBIN, "Mode 1 - Standard 16 bit")
        self.sky = mvr.type_key(SKYPANEL, "CCT")

    def test_read_then_add(self) -> None:
        analysis = self.admin.post(self.url, {"file": mvr_file()}, format="multipart")
        self.assertEqual(analysis.status_code, 200, analysis.content)
        body = analysis.json()
        self.assertEqual(
            (body["file"], body["fixtures"], body["skipped"], len(body["types"])), ("Stadtfest.mvr", 10, 2, 5)
        )
        robin = next(entry for entry in body["types"] if entry["key"] == self.robin)
        self.assertEqual(
            (robin["manufacturer"], robin["model"], robin["count"]), ("Robe Lighting", "Robin T1 Profile", 5)
        )
        self.assertEqual((robin["suggested"], robin["suggestions"][0]["source"]), (self.spot.pk, "similar"))
        self.assertFalse(self.project.material_lines.exists())

        added = self.admin.post(
            self.url,
            {
                "file": mvr_file(),
                "mapping": json.dumps({self.robin: self.spot.pk, self.sky: {"product": self.panel.pk, "quantity": 4}}),
            },
            format="multipart",
        )
        self.assertEqual(added.status_code, 201, added.content)
        group = self.project.groups.get(pk=added.json()["group"])
        self.assertEqual(group.name, "MVR Stadtfest")
        self.assertEqual(
            sorted((line.product_id, line.quantity) for line in group.lines.all()),
            sorted([(self.spot.pk, Decimal("5.00")), (self.panel.pk, Decimal("4.00"))]),
        )
        self.assertEqual(sorted(added.json()["lines"]), sorted(group.lines.values_list("pk", flat=True)))
        self.assertEqual(FixtureTypeMapping.objects.count(), 2)
        again = self.admin.post(self.url, {"file": mvr_file()}, format="multipart").json()
        sky = next(entry for entry in again["types"] if entry["key"] == self.sky)
        self.assertEqual(
            sky["suggestions"][0], {**sky["suggestions"][0], "product": self.panel.pk, "source": "remembered"}
        )

    def test_existing_group_or_none_and_not_remembered(self) -> None:
        lights = add_group(self.project, "Licht")
        mapping = json.dumps({self.robin: self.spot.pk})
        response = self.admin.post(
            self.url,
            {"file": mvr_file(), "mapping": mapping, "group": str(lights.pk), "remember": "false"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(lights.lines.count(), 1)
        self.assertFalse(FixtureTypeMapping.objects.exists())
        loose = self.admin.post(self.url, {"file": mvr_file(), "mapping": mapping, "group": "none"}, format="multipart")
        self.assertIsNone(loose.json()["group"])
        self.assertEqual(self.project.material_lines.filter(group__isnull=True).count(), 1)

    def test_errors_and_rights(self) -> None:
        self.assert_error(self.admin.post(self.url, {}, format="multipart"), 400, "validation_error", "file")
        self.assert_error(
            self.admin.post(self.url, {"file": mvr_file("plot.mvr", b"nope")}, format="multipart"),
            400,
            "validation_error",
            "file",
        )
        for mapping in ("{", json.dumps({"unknown|type": self.spot.pk}), json.dumps({self.robin: 999999})):
            self.assert_error(
                self.admin.post(self.url, {"file": mvr_file(), "mapping": mapping}, format="multipart"),
                400,
                "validation_error",
                "mapping",
            )
        self.assert_error(
            self.admin.post(
                self.url,
                {"file": mvr_file(), "mapping": json.dumps({self.robin: None}), "group": "424242"},
                format="multipart",
            ),
            400,
            "validation_error",
            "group",
        )
        nothing = self.admin.post(
            self.url, {"file": mvr_file(), "mapping": json.dumps({self.robin: None})}, format="multipart"
        )
        self.assert_error(nothing, 400, "validation_error")
        self.assertFalse(self.project.groups.exists())
        warehouse = self.client_for("luka", "Lager")
        self.assert_error(warehouse.post(self.url, {"file": mvr_file()}, format="multipart"), 403, "permission_denied")
        other = make_project("Anderes Fest")
        self.assertEqual(
            self.admin.post(
                f"{API}/projects/{other.pk + 1000}/mvr", {"file": mvr_file()}, format="multipart"
            ).status_code,
            404,
        )
