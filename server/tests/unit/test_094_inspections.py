# SPDX-License-Identifier: GPL-3.0-or-later
"""Inspections – the visual check as a tick box, day and inspector filled in, mass inspections and the link to the
types (MAT-081, MAT-082, MAT-083; API-002, API-014).

Requirements: the field "Sichtprüfung" is a checkbox, not a dropdown; a new inspection fills in the date (today) and the inspector
(the current user); mass inspections under Materialverwaltung → Prüfungen select several items to start an inspection, with date and
inspector filled in and, for a DGUV inspection, the test device entered once for all; the tab "Prüfungen" links to the management of
the inspection types.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.material import services
from rentalars.material.models import Inspection, ItemStatus, MaterialItem
from tests.api.base import API, ApiTestCase
from tests.helpers import RentalarsTestCase, make_item
from tests.ui.base import UiTestCase, form_data
from tests.unit.test_093_dguv import TODAY, good_values, setup_dguv

BATCH = "material:inspection_batch"


class VisualCheckBoxTests(UiTestCase):
    """MAT-081: the visual check is a tick box; unticked means "not passed"."""

    def setUp(self) -> None:
        super().setUp()
        setup_dguv(self)
        self.url = reverse("material:item_inspections", args=[self.cable.pk])

    def test_a_tick_box_and_the_form_starts_with_today_and_the_user(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn('<input type="checkbox" name="visual_check_passed"', page)
        self.assertNotIn('<select name="visual_check_passed"', page)
        self.assertIn('name="date" value="2027-03-01"', page)
        self.assertIn(
            f'name="inspector" value="{self.admin_user.get_full_name() or self.admin_user.get_username()}"', page
        )

    def test_ticked_and_unticked(self) -> None:
        data = form_data(
            self.client.get(self.url),
            containing="inspector",
            inspection_type=self.electric.pk,
            visual_check_passed="on",
            pe_resistance_ohm="0,12",
            insulation_resistance_mohm="250",
            function_test_passed="yes",
            result="passed",
        )
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        self.assertIs(Inspection.objects.get().visual_check_passed, True)
        Inspection.objects.all().delete()
        MaterialItem.objects.filter(pk=self.cable.pk).update(status=ItemStatus.AVAILABLE)
        del data["visual_check_passed"]
        self.client.post(self.url, data)
        self.assertEqual(Inspection.objects.count(), 0)  # not passed: "passed" needs a reason in the note
        data["note"] = "Nachgemessen, Gehäuse geprüft"
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        self.assertIs(Inspection.objects.get().visual_check_passed, False)


class BatchServiceTests(RentalarsTestCase):
    """MAT-082: the service – the same rules per item, all or nothing, the test device once."""

    def setUp(self) -> None:
        super().setUp()
        setup_dguv(self)
        self.second = make_item(self.cable_model, 43, serial_number="SN-4712")

    def entry(self, item: MaterialItem, **changes: Any) -> services.BatchEntry:
        values = good_values(test_device="")
        return services.BatchEntry(item=item, result="", electrical={**values, **changes})

    def test_test_device_once_and_result_by_the_values(self) -> None:
        recorded = services.record_inspections(
            [self.entry(self.cable), self.entry(self.second, pe_resistance_ohm=Decimal("0.9"))],
            self.electric,
            date=TODAY,
            inspector="E. Fachkraft",
            test_device="Benning ST 760",
        )
        self.assertEqual([i.test_device for i in recorded], ["Benning ST 760"] * 2)
        self.assertEqual([i.result for i in recorded], ["passed", "failed"])
        self.assertEqual(MaterialItem.objects.get(pk=self.second.pk).status, ItemStatus.DEFECTIVE)

    def test_all_or_nothing(self) -> None:
        bad = services.BatchEntry(
            item=self.second, result="passed", electrical=good_values(pe_resistance_ohm=Decimal("0.9"))
        )
        with self.assertRaises(services.BatchInspectionError) as caught:
            services.record_inspections(
                [self.entry(self.cable), bad], self.electric, date=TODAY, inspector="E", test_device="X"
            )
        self.assertEqual(list(caught.exception.by_item), [self.second.pk])
        self.assertIn("note", caught.exception.by_item[self.second.pk])
        self.assertEqual(Inspection.objects.count(), 0)

    def test_common_errors(self) -> None:
        for kwargs, field in (
            ({"inspector": " "}, "inspector"),
            ({"date": TODAY + datetime.timedelta(days=3)}, "date"),
        ):
            arguments: dict[str, Any] = {"date": TODAY, "inspector": "E", "test_device": "X"} | kwargs
            with self.assertRaises(services.BatchInspectionError) as caught:
                services.record_inspections([self.entry(self.cable)], self.electric, **arguments)
            self.assertIn(field, caught.exception.common)
        with self.assertRaises(services.ValidationError):
            services.record_inspections([], self.electric, date=TODAY, inspector="E")

    def test_another_inspection_needs_a_result(self) -> None:
        with self.assertRaises(services.BatchInspectionError):
            services.record_inspections([services.BatchEntry(item=self.cable)], self.visual, date=TODAY, inspector="E")
        recorded = services.record_inspections(
            [
                services.BatchEntry(item=self.cable, result="passed"),
                services.BatchEntry(item=self.second, result="passed"),
            ],
            self.visual,
            date=TODAY,
            inspector="E",
        )
        self.assertEqual(len(recorded), 2)


class BatchPageTests(UiTestCase):
    """MAT-082: choosing in the list, the form, the result."""

    def setUp(self) -> None:
        super().setUp()
        setup_dguv(self)
        self.second = make_item(self.cable_model, 43, serial_number="SN-4712")
        self.url = reverse(BATCH)

    def start(self, *items: MaterialItem, **extra: Any) -> str:
        return self.assert_ok(self.client.post(self.url, {"items": [i.pk for i in items], **extra}))

    def test_the_list_offers_the_choice_and_the_link_to_the_types(self) -> None:
        page = self.assert_ok(self.client.get(reverse("material:inspections")))
        self.assertIn(f'action="{self.url}"', page)
        self.assertIn('data-bulk-bar="items"', page)
        self.assertIn(f'href="{reverse("admin:material_inspectiontype_changelist")}"', page)
        reader = self.browser_for("rita", "Nur-Lesen")
        page = self.assert_ok(reader.get(reverse("material:inspections")))
        self.assertNotIn(f'action="{self.url}"', page)  # reading is not enough to inspect
        Role.objects.create(name="Ohne Verwaltung", module_levels={"material": 2})
        clerk = self.browser_for("karl", "Ohne Verwaltung")
        page = self.assert_ok(clerk.get(reverse("material:inspections")))
        self.assertNotIn("inspectiontype", page)  # no right on the administration: no link

    def test_the_form_asks_day_inspector_and_test_device_once(self) -> None:
        page = self.start(self.cable, self.second, type=self.electric.pk)
        self.assertIn('name="date" value="2027-03-01"', page)
        self.assertEqual(page.count('name="test_device"'), 1)
        self.assertEqual(page.count('name="visual"'), 2)
        self.assertIn(f'<option value="{self.electric.pk}" selected>', page)
        self.assertIn(f'name="i{self.cable.pk}-pe_resistance_ohm"', page)

    def test_recording(self) -> None:
        base = {
            "items": [self.cable.pk, self.second.pk],
            "save": "1",
            "inspection_type": self.electric.pk,
            "date": "2027-03-01",
            "inspector": "E. Fachkraft",
            "test_device": "Benning ST 760",
        }
        row = {
            "result": "",
            "pe_resistance_ohm": "0,12",
            "insulation_resistance_mohm": "250",
            "function_test_passed": "yes",
        }
        data = dict(base, visual=[self.cable.pk])
        for item in (self.cable, self.second):
            data.update({f"i{item.pk}-{name}": value for name, value in row.items()})
            data[f"i{item.pk}-protection_class"] = "I"
            data[f"i{item.pk}-cord_length_m"] = "10"
        response = self.client.post(self.url, data, follow=True)
        page = self.assert_ok(response)
        self.assertIn("2 Prüfungen erfasst.", page)
        done = {i.item_id: i for i in Inspection.objects.all()}
        self.assertEqual(done[self.cable.pk].result, "passed")
        self.assertEqual(done[self.second.pk].result, "failed")  # no tick on its visual check
        self.assertEqual({i.test_device for i in done.values()}, {"Benning ST 760"})

    def test_errors_keep_everything_and_name_the_item(self) -> None:
        data: dict[str, Any] = {
            "items": [self.cable.pk, self.second.pk],
            "save": "1",
            "inspection_type": self.electric.pk,
            "date": "2027-03-01",
            "inspector": "E. Fachkraft",
            "test_device": "X",
            "visual": [self.cable.pk, self.second.pk],
        }
        for item in (self.cable, self.second):
            data.update(
                {
                    f"i{item.pk}-result": "passed",
                    f"i{item.pk}-pe_resistance_ohm": "0,9" if item == self.second else "0,12",
                    f"i{item.pk}-insulation_resistance_mohm": "250",
                    f"i{item.pk}-function_test_passed": "yes",
                    f"i{item.pk}-protection_class": "I",
                    f"i{item.pk}-cord_length_m": "10",
                }
            )
        page = self.assert_ok(self.client.post(self.url, data))
        self.assertEqual(Inspection.objects.count(), 0)
        self.assertIn('value="0,9"', page)
        self.assertIn("RPE", page)
        data["inspector"] = ""
        page = self.assert_ok(self.client.post(self.url, data))
        self.assertEqual(Inspection.objects.count(), 0)
        self.assertIn("field-error", page.replace("errorlist", "field-error"))

    def test_other_inspection_and_only_what_all_have_in_common(self) -> None:
        other = make_item(self.cable_model, 44)
        lamp = make_item(self.lamp_model(), 1)
        page = self.start(self.cable, other)
        self.assertIn(">E-Check<", page)
        self.assertIn(">Sichtkontrolle<", page)
        response = self.client.post(self.url, {"items": [self.cable.pk, lamp.pk]}, follow=True)
        self.assertIn("haben keine Prüfung gemeinsam", self.assert_ok(response))
        data = {
            "items": [self.cable.pk, other.pk],
            "save": "1",
            "inspection_type": self.visual.pk,
            "date": "2027-03-01",
            "inspector": "E",
            f"i{self.cable.pk}-result": "passed",
            f"i{other.pk}-result": "failed",
            f"i{other.pk}-note": "Stecker lose",
        }
        self.assert_ok(self.client.post(self.url, data, follow=True))
        self.assertEqual(
            {i.item_id: i.result for i in Inspection.objects.all()}, {self.cable.pk: "passed", other.pk: "failed"}
        )

    def lamp_model(self) -> Any:
        from tests.helpers import make_model, make_product

        return make_model("Lampe", make_product("L-100"), category_code="L")

    def test_nothing_chosen_and_rights(self) -> None:
        self.assertIn("mindestens ein Exemplar", self.assert_ok(self.client.post(self.url, {}, follow=True)))
        self.assertEqual(self.client.get(self.url).status_code, 405)
        reader = self.browser_for("rita", "Nur-Lesen")
        self.assertEqual(reader.post(self.url, {"items": [self.cable.pk]}).status_code, 403)
        warehouse = self.browser_for("luka", "Lager")
        self.assertEqual(warehouse.post(self.url, {"items": [self.cable.pk]}).status_code, 200)


class BatchApiTests(ApiTestCase):
    """MAT-082, API-002, API-014: ``POST /material-items/inspections/batch``."""

    def setUp(self) -> None:
        super().setUp()
        setup_dguv(self)
        self.second = make_item(self.cable_model, 43, serial_number="SN-4712")
        self.url = f"{API}/material-items/inspections/batch"

    def test_record_and_errors(self) -> None:
        body: dict[str, Any] = {
            "inspection_type": self.electric.pk,
            "date": "2027-03-01",
            "inspector": "E. Fachkraft",
            "test_device": "Benning ST 760",
            "items": [
                {
                    "item": self.cable.pk,
                    "visual_check_passed": True,
                    "pe_resistance_ohm": "0.12",
                    "insulation_resistance_mohm": 250,
                    "function_test_passed": True,
                },
                {
                    "item": self.second.pk,
                    "result": "passed",
                    "visual_check_passed": True,
                    "pe_resistance_ohm": "0.9",
                    "insulation_resistance_mohm": 250,
                    "function_test_passed": True,
                },
            ],
        }
        refused = self.admin.post(self.url, body, format="json")
        error = self.assert_error(refused, 400, "validation_error", "items[1].note")  # the second item, the field
        self.assertEqual(list(error["fields"]), ["items[1].note"])
        self.assertEqual(Inspection.objects.count(), 0)
        body["items"][1]["result"] = "failed"
        created = self.admin.post(self.url, body, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual([i["result"] for i in created.json()], ["passed", "failed"])
        self.assertEqual({i["test_device"] for i in created.json()}, {"Benning ST 760"})
        self.assertEqual(created.json()[0]["protection_class"], "I")  # from the item

    def test_other_errors(self) -> None:
        body = {"inspection_type": self.visual.pk, "date": "2027-03-01", "inspector": "E"}
        twice = {"item": self.cable.pk, "result": "passed"}
        self.assert_error(
            self.admin.post(self.url, {**body, "items": [twice, twice]}, format="json"),
            400,
            "validation_error",
            "items",
        )
        self.assert_error(
            self.admin.post(self.url, {**body, "items": [{"item": 999999, "result": "passed"}]}, format="json"),
            400,
            "validation_error",
            "items",
        )
        self.assert_error(
            self.admin.post(self.url, {**body, "items": []}, format="json"), 400, "validation_error", "items"
        )
        self.assert_error(
            self.admin.post(self.url, {**body, "inspector": " ", "items": [twice]}, format="json"),
            400,
            "validation_error",
            "inspector",
        )
        self.assertEqual(
            self.admin.post(self.url, {**body, "inspection_type": 99999, "items": [twice]}, format="json").status_code,
            404,
        )
        ok = self.admin.post(self.url, {**body, "items": [twice]}, format="json")
        self.assertEqual(ok.status_code, 201, ok.content)

    def test_rights(self) -> None:
        body = {
            "inspection_type": self.visual.pk,
            "date": "2027-03-01",
            "inspector": "E",
            "items": [{"item": self.cable.pk, "result": "passed"}],
        }
        self.assertEqual(self.client_for("rita", "Nur-Lesen").post(self.url, body, format="json").status_code, 403)
        self.assertEqual(self.client_for("luka", "Lager").post(self.url, body, format="json").status_code, 201)
