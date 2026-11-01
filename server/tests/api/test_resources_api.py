# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests: every resource can be created, read, replaced, changed and deleted (API-003).

The simple resources share one life cycle, so they are tested from one table.
Resources with business rules have their own tests in the other files of this
package; here only the operations those tests do not reach are exercised.
"""

from __future__ import annotations

from typing import Any

from django.core import mail

from rentalars.accounts.models import Role
from rentalars.core.models import AuditLogEntry, NumberRange, NumberRangeKey
from rentalars.material.models import MaterialItem
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    add_group,
    add_line,
    category,
    make_customer,
    make_item,
    make_model,
    make_product,
    make_project,
    make_user,
)


class SimpleResourceLifeCycleTests(ApiTestCase):
    """Create → list → read → replace → change → delete, for each simple resource."""

    def cases(self) -> list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any]]]:
        """Rows of ``(address, body to create, body to replace with, body to change with)``."""
        cables = category("K")
        return [
            (
                "units",
                {"name": "Palette", "abbreviation": "Pal."},
                {"name": "Europalette", "abbreviation": "EPal."},
                {"abbreviation": "EP"},
            ),
            (
                "tax-rates",
                {"name": "7 %", "rate": "7.00"},
                {"name": "7 % ermäßigt", "rate": "7.00"},
                {"is_active": False},
            ),
            ("manufacturers", {"name": "Cordial"}, {"name": "Cordial GmbH"}, {"is_active": False}),
            (
                "suppliers",
                {"name": "Musikhaus Nord"},
                {"name": "Musikhaus Nord GmbH", "customer_number": "4711"},
                {"note": "Rabatt 5 %"},
            ),
            ("storage-locations", {"name": "Halle 1"}, {"name": "Halle 1 Nord"}, {"is_active": False}),
            ("rental-scales", {"name": "Lichtstaffel"}, {"name": "Lichtstaffel 2027"}, {"is_active": False}),
            (
                "category-fields",
                {"category": cables.pk, "label": "Querschnitt", "field_type": "number", "unit": "mm²"},
                {"category": cables.pk, "label": "Leiterquerschnitt", "field_type": "number", "unit": "mm²"},
                {"position": 5},
            ),
            (
                "categories",
                {"name": "3D-Druck", "code": "P"},
                {"name": "3D-Druck und Prototypen", "code": "P"},
                {"buffer_after_hours": "2.00"},
            ),
            (
                "roles",
                {"name": "Werkstatt", "module_levels": {"material": 2}},
                {"name": "Werkstatt Nord", "module_levels": {"material": 3}},
                {"description": "Reparaturen"},
            ),
        ]

    def test_life_cycle(self) -> None:
        for address, create, replace, change in self.cases():
            with self.subTest(resource=address):
                url = f"{API}/{address}"
                created = self.admin.post(url, create, format="json")
                self.assertEqual(created.status_code, 201, created.content)
                record = created.json()
                for name, value in create.items():
                    self.assertEqual(record[name], value)

                listed = self.admin.get(url, {"page_size": 500}).json()
                self.assertIn(record["id"], [row["id"] for row in listed["results"]])
                self.assertEqual(self.admin.get(f"{url}/{record['id']}").json()["id"], record["id"])

                replaced = self.admin.put(f"{url}/{record['id']}", replace, format="json")
                self.assertEqual(replaced.status_code, 200, replaced.content)
                for name, value in replace.items():
                    self.assertEqual(replaced.json()[name], value)

                changed = self.admin.patch(f"{url}/{record['id']}", change, format="json")
                self.assertEqual(changed.status_code, 200, changed.content)
                for name, value in change.items():
                    self.assertEqual(changed.json()[name], value)

                self.assertEqual(self.admin.delete(f"{url}/{record['id']}").status_code, 204)
                self.assert_error(self.admin.get(f"{url}/{record['id']}"), 404, "not_found")

    def test_every_write_is_recorded_in_the_change_log(self) -> None:
        """ADM-005: create, change and delete each leave an entry that can be read back."""
        unit = self.admin.post(f"{API}/units", {"name": "Palette", "abbreviation": "Pal."}, format="json").json()
        self.admin.patch(f"{API}/units/{unit['id']}", {"abbreviation": "EP"}, format="json")
        self.admin.delete(f"{API}/units/{unit['id']}")
        entries = AuditLogEntry.objects.filter(content_type__model="unit", object_id=str(unit["id"])).order_by(
            "timestamp"
        )
        self.assertEqual([entry.action for entry in entries], ["created", "updated", "deleted"])
        detail = self.admin.get(f"{API}/audit-log/{entries[1].pk}").json()
        self.assertEqual(detail["changes"]["abbreviation"], ["Pal.", "EP"])
        self.assertEqual(detail["actor_label"], "admin")


class RemainingOperationTests(ApiTestCase):
    """Reads and full replacements of the resources that carry business rules."""

    def test_material_model_and_item(self) -> None:
        cables = category("K")
        model = self.admin.post(
            f"{API}/material-models", {"name": "Cordial CPM 5 FM", "category": cables.pk}, format="json"
        ).json()
        url = f"{API}/material-models/{model['id']}"
        self.assertEqual(self.admin.get(url).json()["item_count"], 0)
        self.assertEqual(
            self.admin.put(url, {"name": "Cordial CPM 5 FM-FLEX", "category": cables.pk}, format="json").json()["name"],
            "Cordial CPM 5 FM-FLEX",
        )
        self.assertEqual(self.admin.patch(url, {"short_name": "CPM5"}, format="json").json()["short_name"], "CPM5")
        self.assertEqual(
            [row["id"] for row in self.admin.get(f"{API}/material-models", {"search": "CPM"}).json()["results"]],
            [model["id"]],
        )

        item = self.admin.post(f"{API}/material-items", {"material_model": model["id"]}, format="json").json()
        listed = self.admin.get(f"{url}/items").json()
        self.assertEqual([row["display_id"] for row in listed["results"]], ["0001"])
        replaced = self.admin.put(
            f"{API}/material-items/{item['id']}", {"material_model": model["id"], "note": "Stecker neu"}, format="json"
        )
        self.assertEqual(replaced.status_code, 200, replaced.content)
        self.assertEqual(replaced.json()["note"], "Stecker neu")

        # MAT-022: a model with items stays; an item without any deployment may be deleted.
        self.assert_error(self.admin.delete(url), 409, "in_use")
        self.assertEqual(self.admin.delete(f"{API}/material-items/{item['id']}").status_code, 204)
        self.assertEqual(self.admin.delete(url).status_code, 204)

    def test_item_that_was_out_is_archived_instead_of_deleted(self) -> None:
        """MAT-022."""
        product = make_product("T-500")
        rack = make_item(make_model("Funkrack", product), 500)
        project = make_project()
        add_line(project, product, 1)
        packlist = self.admin.get(f"{API}/projects/{project.pk}/packlists").json()[0]
        self.admin.post(  # PCK-025: everything, nothing was ticked
            f"{API}/projects/{project.pk}/packlists/{packlist['id']}/issue", {"only_packed": False}, format="json"
        )
        self.assert_error(self.admin.delete(f"{API}/material-items/{rack.pk}"), 400, "validation_error")
        self.assertTrue(MaterialItem.objects.filter(pk=rack.pk).exists())

    def test_product_replace_and_components_read(self) -> None:
        kit = make_product("T-100", kind="kit", billing_mode="daily_kit")
        self.assertEqual(self.admin.get(f"{API}/products/{kit.pk}/components").json(), [])
        body = {
            "article_number": "T-100",
            "name": "Aktivbox-Set",
            "category": kit.category_id,
            "unit": kit.unit_id,
            "tax_rate": kit.tax_rate_id,
            "kind": "kit",
            "billing_mode": "daily_kit",
            "price": "40.00",
        }
        replaced = self.admin.put(f"{API}/products/{kit.pk}", body, format="json")
        self.assertEqual(replaced.status_code, 200, replaced.content)
        self.assertEqual(replaced.json()["name"], "Aktivbox-Set")
        self.assertEqual(replaced.json()["price"], "40.00")

    def test_customer_and_contact(self) -> None:
        customer = make_customer("Stadtwerke")
        url = f"{API}/customers/{customer.pk}"
        self.assertEqual(self.admin.get(url).json()["name"], "Stadtwerke")
        self.assertEqual(
            self.admin.put(url, {"name": "Stadtwerke Musterstadt GmbH"}, format="json").json()["name"],
            "Stadtwerke Musterstadt GmbH",
        )
        contact = self.admin.post(f"{url}/contacts", {"name": "Petra Beispiel"}, format="json").json()
        contact_url = f"{url}/contacts/{contact['id']}"
        self.assertEqual(self.admin.get(contact_url).json()["name"], "Petra Beispiel")
        self.assertEqual(
            self.admin.put(contact_url, {"name": "Petra Muster"}, format="json").json()["name"], "Petra Muster"
        )
        self.assertEqual(
            self.admin.patch(contact_url, {"phone": "0123 456"}, format="json").json()["phone"], "0123 456"
        )
        self.assertEqual(self.admin.delete(contact_url).status_code, 204)
        self.assertEqual(self.admin.get(f"{url}/contacts").json(), [])

    def test_project_group_and_line(self) -> None:
        customer = make_customer()
        project = make_project(customer=customer)
        lamp = make_product("L-010", price="20.00")
        base = f"{API}/projects/{project.pk}"
        body = {
            "name": "Stadtfest Nebenbühne",
            "customer": customer.pk,
            "start": project.start.isoformat(),
            "end": project.end.isoformat(),
        }
        self.assertEqual(self.admin.put(base, body, format="json").json()["name"], "Stadtfest Nebenbühne")

        group = add_group(project, "Front")
        group_url = f"{base}/groups/{group.pk}"
        self.assertEqual(self.admin.get(group_url).json()["name"], "Front")
        self.assertEqual(
            self.admin.put(group_url, {"name": "Front-Traverse"}, format="json").json()["name"], "Front-Traverse"
        )
        self.assertEqual(self.admin.patch(group_url, {"kind": "optional"}, format="json").json()["kind"], "optional")

        line = add_line(project, lamp, 2, group=group).line
        line_url = f"{base}/material-lines/{line.pk}"
        self.assertEqual(self.admin.get(line_url).json()["quantity"], "2.00")
        replaced = self.admin.put(
            line_url, {"quantity": "3", "title": "LED-Scheinwerfer RGBW", "note": "mit Torblende"}, format="json"
        )
        self.assertEqual(replaced.status_code, 200, replaced.content)
        self.assertEqual(replaced.json()["quantity"], "3.00")
        self.assertEqual(replaced.json()["note"], "mit Torblende")
        self.assertEqual(self.admin.get(f"{line_url}/surcharge-targets").json(), [])
        self.assertEqual(self.admin.delete(line_url).status_code, 204)
        self.assertEqual(self.admin.get(f"{base}/material-lines").json(), [])

    def test_number_range_read_and_replace(self) -> None:
        number_range = NumberRange.objects.get(key=NumberRangeKey.PROJECT)
        url = f"{API}/number-ranges/{number_range.pk}"
        document = self.admin.get(url).json()
        self.assertEqual(document["key"], NumberRangeKey.PROJECT)
        document.update(prefix="P", min_digits=5, next_value=42)
        replaced = self.admin.put(url, document, format="json")
        self.assertEqual(replaced.status_code, 200, replaced.content)
        self.assertTrue(replaced.json()["preview"].endswith("00042"))

    def test_user_read_replace_and_invitation(self) -> None:
        user = make_user("berta")
        url = f"{API}/users/{user.pk}"
        self.assertEqual(self.admin.get(url).json()["username"], "berta")
        listed = self.admin.get(f"{API}/users", {"search": "bert"}).json()["results"]
        self.assertEqual([row["username"] for row in listed], ["berta"])
        role = Role.objects.get(name="Lager")
        replaced = self.admin.put(
            url,
            {"username": "berta", "email": "berta@example.de", "first_name": "Berta", "roles": [role.pk]},
            format="json",
        )
        self.assertEqual(replaced.status_code, 200, replaced.content)
        self.assertEqual(replaced.json()["full_name"], "Berta")
        self.assertEqual(replaced.json()["roles"], [role.pk])
        self.assertEqual(self.admin.post(f"{url}/send-invitation").status_code, 204)
        self.assertEqual(mail.outbox[-1].to, ["berta@example.de"])
        self.admin.post(f"{url}/deactivate")
        self.assert_error(self.admin.post(f"{url}/send-invitation"), 400, "validation_error")

    def test_rental_scale_without_table_can_be_created_and_filled(self) -> None:
        scale = self.admin.post(f"{API}/rental-scales", {"name": "Tonstaffel"}, format="json").json()
        self.assertIsNone(scale["current_version"])
        published = self.admin.post(
            f"{API}/rental-scales/{scale['id']}/publish",
            {"rows": [{"days": 1, "factor": "1.0"}, {"days": 3, "factor": "2.0"}], "extra_day_increment": "0.25"},
            format="json",
        ).json()
        self.assertEqual(published["current_version"]["number"], 1)
        self.assertEqual(
            self.admin.get(f"{API}/rental-scales/{scale['id']}").json()["current_version"]["rows"][1]["factor"], "2.000"
        )
