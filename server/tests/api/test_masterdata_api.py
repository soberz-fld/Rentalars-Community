# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests: master data, settings, number ranges, change log (ADM, API-007)."""

from __future__ import annotations

from rentalars.core.models import AuditLogEntry, NumberRange, NumberRangeKey
from rentalars.masterdata.models import Category, RentalScale, Supplier, Unit
from tests.api.base import API, ApiTestCase
from tests.helpers import add_line, category, make_product, make_project


class MasterDataTests(ApiTestCase):
    """Categories, units, tax rates, manufacturers, suppliers, storage locations."""

    def test_every_logged_in_user_reads_master_data_but_only_administrators_change_it(self) -> None:
        reader = self.client_for("nora", "Nur-Lesen")
        self.assertEqual(reader.get(f"{API}/units").status_code, 200)
        self.assertEqual(reader.get(f"{API}/categories").status_code, 200)
        self.assert_error(
            reader.post(f"{API}/units", {"name": "Palette", "abbreviation": "Pal."}, format="json"),
            403,
            "permission_denied",
        )
        response = self.admin.post(f"{API}/units", {"name": "Palette", "abbreviation": "Pal."}, format="json")
        self.assertEqual(response.status_code, 201, response.data)

    def test_main_category_gets_a_unique_code_of_capital_letters(self) -> None:
        """PRD-009: the code is the prefix of the article numbers. Also PRD-029."""
        response = self.admin.post(f"{API}/categories", {"name": "3D-Druck", "code": "P"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["effective_code"], "P")
        duplicate = self.admin.post(f"{API}/categories", {"name": "Pyrotechnik", "code": "P"}, format="json")
        self.assert_error(duplicate, 400, "validation_error", "code")
        lower_case = self.admin.post(f"{API}/categories", {"name": "Pyrotechnik", "code": "p1"}, format="json")
        self.assert_error(lower_case, 400, "validation_error", "code")

    def test_subcategory_inherits_the_code_of_its_main_category(self) -> None:
        cables = category("K")
        response = self.admin.post(f"{API}/categories", {"name": "Audiokabel", "parent": cables.pk}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["effective_code"], "K")
        self.assertEqual(response.data["path"], f"{cables.name} > Audiokabel")

    def test_category_specific_field_is_defined_per_category(self) -> None:
        """MAT-009/MAT-010: e.g. "Länge" in metres for cables."""
        racks = category("R")
        response = self.admin.post(
            f"{API}/category-fields",
            {"category": racks.pk, "label": "Höheneinheiten", "field_type": "number", "unit": "HE"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        fields = self.admin.get(f"{API}/categories/{racks.pk}").data["specific_fields"]
        self.assertEqual([field["label"] for field in fields], ["Höheneinheiten"])

    def test_category_in_use_cannot_be_deleted(self) -> None:
        """ADM-006: used master data is deactivated instead."""
        make_product("K-005")
        response = self.admin.delete(f"{API}/categories/{category('K').pk}")
        self.assert_error(response, 400, "validation_error")
        self.assertTrue(Category.objects.filter(code="K").exists())

    def test_suppliers_may_be_maintained_with_write_access_to_material(self) -> None:
        warehouse = self.client_for("luka", "Lager")
        response = warehouse.post(f"{API}/suppliers", {"name": "Musikhaus Nord"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(Supplier.objects.filter(name="Musikhaus Nord").exists())
        self.assert_error(
            warehouse.post(f"{API}/units", {"name": "Palette", "abbreviation": "Pal."}, format="json"),
            403,
            "permission_denied",
        )

    def test_tax_rates_start_with_19_percent_and_tax_free(self) -> None:
        """PRD-016."""
        rates = {row["name"]: row for row in self.admin.get(f"{API}/tax-rates").data["results"]}
        self.assertEqual(rates["19 %"]["rate"], "19.00")
        self.assertTrue(rates["19 %"]["is_default"])
        self.assertEqual(rates["steuerfrei"]["rate"], "0.00")

    def test_storage_locations_form_a_tree(self) -> None:
        hall = self.admin.post(f"{API}/storage-locations", {"name": "Halle 1"}, format="json").data
        shelf = self.admin.post(f"{API}/storage-locations", {"name": "Regal A", "parent": hall["id"]}, format="json")
        self.assertEqual(shelf.status_code, 201, shelf.data)
        self.assertEqual(shelf.data["path"], "Halle 1 > Regal A")


class ListBehaviourTests(ApiTestCase):
    """All lists page, filter, search and sort the same way (API-007)."""

    def setUp(self) -> None:
        super().setUp()
        for number in range(1, 8):
            Unit.objects.create(name=f"Testeinheit {number}", abbreviation=f"te{number}")

    def test_lists_are_delivered_page_by_page(self) -> None:
        first = self.admin.get(f"{API}/units", {"page_size": 3}).data
        self.assertEqual(len(first["results"]), 3)
        self.assertGreaterEqual(first["count"], 7)
        self.assertIsNotNone(first["next"])
        self.assertIsNone(first["previous"])
        second = self.admin.get(f"{API}/units", {"page_size": 3, "page": 2}).data
        self.assertIsNotNone(second["previous"])
        self.assertFalse({row["id"] for row in first["results"]} & {row["id"] for row in second["results"]})

    def test_page_size_is_capped(self) -> None:
        response = self.admin.get(f"{API}/units", {"page_size": 100000})
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.data["results"]), 500)

    def test_search_filter_and_ordering(self) -> None:
        found = self.admin.get(f"{API}/units", {"search": "Testeinheit 3"}).data
        self.assertEqual([row["name"] for row in found["results"]], ["Testeinheit 3"])
        Unit.objects.filter(name="Testeinheit 3").update(is_active=False)
        inactive = self.admin.get(f"{API}/units", {"is_active": "false"}).data
        self.assertEqual([row["name"] for row in inactive["results"]], ["Testeinheit 3"])
        descending = self.admin.get(f"{API}/units", {"ordering": "-name", "search": "Testeinheit"}).data
        names = [row["name"] for row in descending["results"]]
        self.assertEqual(names, sorted(names, reverse=True))

    def test_unknown_record_answers_in_the_uniform_error_format(self) -> None:
        self.assert_error(self.admin.get(f"{API}/units/999999"), 404, "not_found")

    def test_unknown_page_answers_in_the_uniform_error_format(self) -> None:
        self.assert_error(self.admin.get(f"{API}/units", {"page": 999}), 404, "not_found")

    def test_malformed_json_answers_in_the_uniform_error_format(self) -> None:
        response = self.admin.post(f"{API}/units", "{not json", content_type="application/json")
        self.assert_error(response, 400, "malformed_request")

    def test_body_that_is_not_an_object_answers_in_the_uniform_error_format(self) -> None:
        """A list where an object is expected must not end in an internal error."""
        project = make_project()
        for address in (
            f"{API}/projects/{project.pk}/status",
            f"{API}/projects/{project.pk}/shortages/accept",
            f"{API}/auth/login",
        ):
            response = self.admin.post(address, [1, 2, 3], format="json")
            self.assert_error(response, 400, "malformed_request")

    def test_validation_error_names_the_field(self) -> None:
        response = self.admin.post(f"{API}/units", {"abbreviation": "x"}, format="json")
        error = self.assert_error(response, 400, "validation_error", "name")
        self.assertEqual(error["fields"]["name"][0]["code"], "required")

    def test_method_that_is_not_offered_answers_in_the_uniform_error_format(self) -> None:
        self.assert_error(self.admin.delete(f"{API}/settings"), 405, "method_not_allowed")


class RentalScaleTests(ApiTestCase):
    """Rental scales: days and factors, versioned (PRD-015, PRD-037)."""

    def test_default_scale_is_installed(self) -> None:
        scales = self.admin.get(f"{API}/rental-scales", {"is_default": "true"}).data["results"]
        self.assertEqual(len(scales), 1)
        rows = {row["days"]: row["factor"] for row in scales[0]["current_version"]["rows"]}
        self.assertEqual(rows[1], "1.000")

    def test_publishing_creates_a_new_version_and_needs_the_special_right(self) -> None:
        scale = RentalScale.objects.get(is_default=True)
        body = {"rows": [{"days": 1, "factor": "1.0"}, {"days": 2, "factor": "1.6"}], "extra_day_increment": "0.4"}
        before = scale.current_version.number

        manager = self.client_for("paula", "Projektleitung")
        self.assert_error(
            manager.post(f"{API}/rental-scales/{scale.pk}/publish", body, format="json"), 403, "permission_denied"
        )

        response = self.admin.post(f"{API}/rental-scales/{scale.pk}/publish", body, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["current_version"]["number"], before + 1)
        self.assertEqual(response.data["current_version"]["rows"][1], {"days": 2, "factor": "1.600"})

    def test_scale_used_by_project_lines_cannot_be_deleted(self) -> None:
        product = make_product("L-010", price="20.00")
        add_line(make_project(), product, 1)
        scale = RentalScale.objects.get(is_default=True)
        self.assert_error(self.admin.delete(f"{API}/rental-scales/{scale.pk}"), 400, "validation_error")


class SettingsTests(ApiTestCase):
    """Company data, system settings, number ranges and the change log (ADM-001 to ADM-005)."""

    def test_settings_can_be_read_and_changed_in_parts(self) -> None:
        response = self.admin.patch(
            f"{API}/settings",
            {"company": {"name": "Lichtwerk GmbH"}, "system": {"buffer_before_hours": 4}},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        document = self.admin.get(f"{API}/settings").data
        self.assertEqual(document["company"]["name"], "Lichtwerk GmbH")
        self.assertEqual(document["system"]["buffer_before_hours"], "4.00")

    def test_settings_need_the_administration_module(self) -> None:
        self.assert_error(self.client_for("paula", "Projektleitung").get(f"{API}/settings"), 403, "permission_denied")

    def test_number_range_shows_a_preview_and_can_be_reformatted(self) -> None:
        """ADM-003."""
        ranges = {row["key"]: row for row in self.admin.get(f"{API}/number-ranges").data}
        customers = ranges[NumberRangeKey.CUSTOMER]
        response = self.admin.patch(
            f"{API}/number-ranges/{customers['id']}",
            {"prefix": "KD-", "min_digits": 6, "next_value": 100},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["preview"], "KD-000100")
        created = self.admin.post(f"{API}/customers", {"name": "Stadtwerke"}, format="json")
        self.assertEqual(created.data["number"], "KD-000100")
        self.assertEqual(NumberRange.objects.get(key=NumberRangeKey.CUSTOMER).next_value, 101)

    def test_number_ranges_cannot_be_created_or_deleted(self) -> None:
        self.assertEqual(self.admin.post(f"{API}/number-ranges", {"key": "x"}, format="json").status_code, 405)

    def test_change_log_records_who_changed_what(self) -> None:
        """ADM-005: filter by object, user and period."""
        created = self.admin.post(f"{API}/customers", {"name": "Stadtwerke"}, format="json").data
        self.admin.patch(f"{API}/customers/{created['id']}", {"city": "Musterstadt"}, format="json")
        log = self.admin.get(
            f"{API}/audit-log",
            {"object_type": "customers.customer", "object_id": created["id"], "ordering": "timestamp"},
        ).data
        self.assertEqual([row["action"] for row in log["results"]], ["created", "updated"])
        change = log["results"][1]
        self.assertEqual(change["actor_label"], "admin")
        self.assertEqual(change["changes"]["city"], ["", "Musterstadt"])
        by_user = self.admin.get(f"{API}/audit-log", {"user": self.admin_user.pk}).data
        self.assertGreaterEqual(by_user["count"], 2)
        self.assertEqual(AuditLogEntry.objects.filter(actor=self.admin_user).count(), by_user["count"])

    def test_change_log_cannot_be_altered(self) -> None:
        entry = AuditLogEntry.objects.first()
        assert entry is not None
        self.assertEqual(self.admin.delete(f"{API}/audit-log/{entry.pk}").status_code, 405)
        self.assertEqual(self.admin.patch(f"{API}/audit-log/{entry.pk}", {}, format="json").status_code, 405)

    def test_search_only_covers_modules_the_caller_may_read(self) -> None:
        """UIX-002."""
        self.admin.post(f"{API}/customers", {"name": "Kabelwerk Nord"}, format="json")
        make_product("K-005", "Kabel XLR 5 m")
        everything = self.admin.get(f"{API}/search", {"q": "Kabel"}).data["results"]
        self.assertEqual({group["kind"] for group in everything}, {"customers", "products"})
        warehouse = self.client_for("luka", "Lager").get(f"{API}/search", {"q": "Kabel"}).data["results"]
        self.assertEqual({group["kind"] for group in warehouse}, {"products"})
