# SPDX-License-Identifier: GPL-3.0-or-later
"""API for lines of the planning: several lines at once (PRJ-082), alternatives (PRJ-083), subrentals
as parts of their line (PRJ-084), the MVR file kept with the project (PRJ-086)."""

from __future__ import annotations

import json
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile

from rentalars.accounts.models import Role
from rentalars.masterdata.models import Supplier
from rentalars.packing.models import PackEntry, Packlist
from rentalars.products.models import BillingMode
from rentalars.projects import mvr
from rentalars.projects.models import GroupKind, LineVariant, MaterialLine, ProjectFile, SubrentalStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import add_group, add_line, make_product, make_project, make_stock
from tests.unit.test_mvr_import import ROBIN, sample_plot

D = Decimal


def flat(article_number: str, price: str = "100.00") -> object:
    """A product billed as a flat price."""
    return make_product(article_number, price=price, billing_mode=BillingMode.FLAT)


class BulkApiTests(ApiTestCase):
    """``POST /projects/{id}/material-lines/bulk`` (PRJ-082)."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.light = add_group(self.project, "Licht")
        self.spot = add_line(self.project, flat("L-010"), 2, group=self.light).line
        self.wash = add_line(self.project, flat("L-020", "50.00"), 4, group=self.light).line
        self.loose = add_line(self.project, flat("K-010", "5.00"), 10).line
        self.url = f"{API}/projects/{self.project.pk}/material-lines/bulk"

    def test_optional_for_several_lines(self) -> None:
        response = self.admin.post(
            self.url, {"lines": [self.spot.pk, self.wash.pk], "action": "optional"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.json(),
            # ``warnings`` names discounts above the maximum of a line (PER-026); here there are none.
            {
                "action": "optional",
                "changed": [self.spot.pk, self.wash.pk],
                "unchanged": [],
                "skipped": [],
                "warnings": [],
            },
        )
        self.assertEqual(
            set(MaterialLine.objects.filter(variant=LineVariant.OPTIONAL).values_list("pk", flat=True)),
            {self.spot.pk, self.wash.pk},
        )

    def test_alternative_move_discount_and_delete(self) -> None:
        body = self.admin.post(
            self.url, {"lines": [self.wash.pk], "action": "alternative", "alternative_to": self.spot.pk}, format="json"
        ).json()
        self.assertEqual(body["changed"], [self.wash.pk])
        self.wash.refresh_from_db()
        self.assertEqual(self.wash.alternative_to, self.spot)
        self.admin.post(self.url, {"lines": [self.loose.pk], "action": "move", "group": self.light.pk}, format="json")
        self.loose.refresh_from_db()
        self.assertEqual(self.loose.group, self.light)
        self.admin.post(self.url, {"lines": [self.loose.pk], "action": "move", "group": None}, format="json")
        self.loose.refresh_from_db()
        self.assertIsNone(self.loose.group)
        self.admin.post(
            self.url, {"lines": [self.spot.pk], "action": "discount", "discount_percent": "7.5"}, format="json"
        )
        self.spot.refresh_from_db()
        self.assertEqual(self.spot.discount_percent, D("7.5"))
        deleted = self.admin.post(self.url, {"lines": [self.spot.pk], "action": "delete"}, format="json").json()
        self.assertEqual(deleted["changed"], [self.spot.pk])
        # The alternative to the deleted line stays as an option.
        self.wash.refresh_from_db()
        self.assertEqual((self.wash.variant, self.wash.alternative_to), (LineVariant.OPTIONAL, None))

    def test_skipped_lines_are_named(self) -> None:
        packlist = Packlist.objects.create(project=self.project)
        PackEntry.objects.create(packlist=packlist, line=self.wash, product=self.wash.product, issued_quantity=D("1"))
        body = self.admin.post(
            self.url, {"lines": [self.spot.pk, self.wash.pk], "action": "delete"}, format="json"
        ).json()
        self.assertEqual(body["changed"], [self.spot.pk])
        self.assertEqual(len(body["skipped"]), 1)
        self.assertEqual((body["skipped"][0]["line"], body["skipped"][0]["title"]), (self.wash.pk, "4 × Produkt L-020"))
        self.assertIn("ausgegeben", body["skipped"][0]["reason"])

    def test_wrong_requests(self) -> None:
        self.assert_error(
            self.admin.post(self.url, {"lines": [], "action": "optional"}, format="json"), 400, "validation_error"
        )
        self.assert_error(
            self.admin.post(self.url, {"lines": [self.spot.pk], "action": "paint"}, format="json"),
            400,
            "validation_error",
        )
        self.assert_error(
            self.admin.post(self.url, {"lines": [self.spot.pk], "action": "alternative"}, format="json"),
            400,
            "validation_error",
        )
        other = add_line(make_project("Anderes"), flat("L-030"), 1).line
        self.assert_error(
            self.admin.post(self.url, {"lines": [self.spot.pk, other.pk], "action": "optional"}, format="json"),
            400,
            "validation_error",
        )

    def test_rights(self) -> None:
        reader = self.client_for("nora", "Nur-Lesen")
        self.assertEqual(
            reader.post(self.url, {"lines": [self.spot.pk], "action": "optional"}, format="json").status_code, 403
        )
        Role.objects.create(name="Planung ohne Preise", module_levels={"projects": 2})
        planner = self.client_for("paul", "Planung ohne Preise")
        self.assertEqual(
            planner.post(self.url, {"lines": [self.spot.pk], "action": "optional"}, format="json").status_code, 200
        )
        self.assert_error(
            planner.post(
                self.url, {"lines": [self.spot.pk], "action": "discount", "discount_percent": "5"}, format="json"
            ),
            400,
            "validation_error",
        )


class AlternativeFieldApiTests(ApiTestCase):
    """PRJ-083: ``alternative_to`` of material lines and groups."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.light = add_group(self.project, "Licht")
        self.sound = add_group(self.project, "Ton")
        self.spot = add_line(self.project, flat("L-010"), 2, group=self.light).line
        self.wash = add_line(self.project, flat("L-020", "50.00"), 4, group=self.light).line
        self.base = f"{API}/projects/{self.project.pk}"

    def test_lines(self) -> None:
        changed = self.admin.patch(
            f"{self.base}/material-lines/{self.wash.pk}", {"alternative_to": self.spot.pk}, format="json"
        )
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual((changed.json()["variant"], changed.json()["alternative_to"]), ("alternative", self.spot.pk))
        listed = self.admin.get(f"{self.base}/material-lines").json()
        self.assertEqual(next(line for line in listed if line["id"] == self.wash.pk)["alternative_to"], self.spot.pk)
        normal = self.admin.patch(f"{self.base}/material-lines/{self.wash.pk}", {"variant": ""}, format="json").json()
        self.assertIsNone(normal["alternative_to"])
        other = add_line(make_project("Anderes"), flat("L-030"), 1).line
        self.assert_error(
            self.admin.patch(f"{self.base}/material-lines/{self.wash.pk}", {"alternative_to": other.pk}, format="json"),
            400,
            "validation_error",
            "alternative_to",
        )
        self.assert_error(
            self.admin.patch(
                f"{self.base}/material-lines/{self.wash.pk}", {"alternative_to": self.wash.pk}, format="json"
            ),
            400,
            "validation_error",
        )

    def test_price_overview(self) -> None:
        self.admin.patch(f"{self.base}/material-lines/{self.wash.pk}", {"alternative_to": self.spot.pk}, format="json")
        self.admin.patch(f"{self.base}/groups/{self.sound.pk}", {"alternative_to": self.light.pk}, format="json")
        body = self.admin.get(f"{self.base}/price-overview").json()
        light = next(group for group in body["groups"] if group["group"] == self.light.pk)
        wash = next(line for line in light["lines"] if line["title"] == "Produkt L-020")
        self.assertEqual((wash["variant"], wash["alternative_to"]), ("alternative", self.spot.pk))
        sound = next(group for group in body["groups"] if group["group"] == self.sound.pk)
        self.assertEqual(sound["alternative_to"], self.light.pk)

    def test_groups(self) -> None:
        changed = self.admin.patch(
            f"{self.base}/groups/{self.sound.pk}", {"alternative_to": self.light.pk}, format="json"
        )
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual((changed.json()["kind"], changed.json()["alternative_to"]), ("alternative", self.light.pk))
        created = self.admin.post(
            f"{self.base}/groups", {"name": "Video", "alternative_to": self.light.pk}, format="json"
        ).json()
        self.assertEqual(created["kind"], GroupKind.ALTERNATIVE)
        cleared = self.admin.patch(f"{self.base}/groups/{self.sound.pk}", {"kind": "optional"}, format="json").json()
        self.assertIsNone(cleared["alternative_to"])


class SubrentalApiTests(ApiTestCase):
    """PRJ-084: accepting a subrental with status, supplier and purchase price – no rental price."""

    def test_status(self) -> None:
        project = make_project()
        spots = make_stock("L-010", 4, "Spot", price="20.00")
        line = add_line(project, spots, 6).line
        supplier = Supplier.objects.create(name="Verleih Nord")
        url = f"{API}/projects/{project.pk}/shortages/accept"
        response = self.admin.post(
            url,
            {
                "line": line.pk,
                "product": spots.pk,
                "quantity": 2,
                "supplier": supplier.pk,
                "purchase_price": "12.50",
                "status": "ordered",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual((body["subrental_status"], body["covers_line"]), (SubrentalStatus.ORDERED, line.pk))
        # The customer pays the line, not the subrental: the total stays 6 × 20,00 × 1,5.
        totals = self.admin.get(f"{API}/projects/{project.pk}/totals").json()
        self.assertEqual((totals["net_total"], totals["subrental_cost"]), ("180.00", "25.00"))
        self.assert_error(
            self.admin.post(
                url, {"line": line.pk, "product": spots.pk, "quantity": 1, "status": "lost"}, format="json"
            ),
            400,
            "validation_error",
        )


class MvrFileApiTests(ApiTestCase):
    """PRJ-086: the API keeps the file when it adds the lines."""

    def test_kept_file(self) -> None:
        spot = make_product("L-010", "Robe Robin T1 Profile", price="80.00")
        project = make_project()
        url = f"{API}/projects/{project.pk}/mvr"
        upload = SimpleUploadedFile("Stadtfest.mvr", sample_plot(), content_type="application/zip")
        preview = self.admin.post(url, {"file": upload}, format="multipart")
        self.assertEqual(preview.status_code, 200)
        self.assertFalse(ProjectFile.objects.filter(project=project).exists())  # a preview writes nothing
        upload = SimpleUploadedFile("Stadtfest.mvr", sample_plot(), content_type="application/zip")
        mapping = json.dumps({mvr.type_key(ROBIN, "Mode 1 - Standard 16 bit"): spot.pk})
        added = self.admin.post(url, {"file": upload, "mapping": mapping}, format="multipart")
        self.assertEqual(added.status_code, 201, added.content)
        kept = ProjectFile.objects.get(project=project)
        self.assertEqual(added.json()["kept_file"], {"id": kept.pk, "name": kept.original_name})
        self.assertRegex(kept.original_name, r"^\d{8}-\d{6}_Stadtfest\.mvr$")
