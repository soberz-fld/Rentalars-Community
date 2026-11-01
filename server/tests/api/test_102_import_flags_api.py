# SPDX-License-Identifier: GPL-3.0-or-later
"""The status "import error" over the API – readable and filterable, never settable."""

from __future__ import annotations

from rentalars.material.models import ItemStatus, MaterialItem
from tests.api.base import API, ApiTestCase
from tests.helpers import make_items, make_model, make_product
from tests.unit.test_importer import HEAD, run


class ImportErrorStatusApiTests(ApiTestCase):
    """MAT-020: only the import sets it."""

    def test_nobody_sets_it_over_the_api(self) -> None:
        item = make_items(make_model("Kabel", make_product("K-005")))[0]
        patched = self.admin.patch(f"{API}/material-items/{item.pk}", {"status": "import_error"}, format="json")
        self.assertEqual(patched.status_code, 400)
        bulk = self.admin.post(
            f"{API}/material-items/bulk-update", {"items": [item.pk], "status": "import_error"}, format="json"
        )
        self.assertEqual(bulk.status_code, 400)
        self.assertEqual(MaterialItem.objects.get(pk=item.pk).status, ItemStatus.AVAILABLE)

    def test_it_is_listed_and_can_be_filtered(self) -> None:
        run(f"{HEAD};Kaufpreis\n310;Empfänger;Ton;neun\n311;Sender;Ton;1,00\n")
        listed = self.admin.get(f"{API}/material-items", {"status": "import_error"}).json()
        results = listed["results"] if isinstance(listed, dict) else listed
        self.assertEqual([row["inventory_number"] for row in results], [310])
        self.assertEqual(results[0]["status"], "import_error")
        self.assertIn("Kaufpreis: neun", results[0]["note"])

    def test_a_flagged_item_can_be_released_over_the_api(self) -> None:
        run(f"{HEAD};Kaufpreis\n310;Empfänger;Ton;neun\n")
        item = MaterialItem.objects.get(inventory_number=310)
        released = self.admin.patch(f"{API}/material-items/{item.pk}", {"status": "available"}, format="json")
        self.assertEqual(released.status_code, 200)
        self.assertEqual(MaterialItem.objects.get(pk=item.pk).status, ItemStatus.AVAILABLE)
