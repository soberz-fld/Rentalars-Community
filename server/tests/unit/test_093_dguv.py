# SPDX-License-Identifier: GPL-3.0-or-later
"""Fields for the electrical inspection after DGUV V3 / DIN VDE 0701-0702 (MAT-077, MAT-078; MAT-030,
MAT-031, IMP-017, API-002).

The requirement: provide fields for the DGUV inspection (electrical devices) on items. Decided: measured values plus
protection class – the protection class at the model or item; an inspection type marked "elektrisch (DGUV V3)" asks
for the visual check, protective-conductor and insulation resistance, protective-conductor and touch current, the
function check and the test device, checks the limits and suggests the result.

* The protection class (I, II, III) at the material model and, where it differs, at the item: pages, forms, the
  item list, the API, the material import and its export in the import format.
* An inspection type marked electrical asks for the measured values; the limits of DIN VDE 0701-0702
  (``material.dguv``) mark values outside them and suggest the result; "bestanden" against the values needs a note.
  A failed inspection sets the item to "defective" and makes it due again, as before.
* The values with their limits in the item's list of inspections and in the API; a printable protocol (PDF).
"""

from __future__ import annotations

import datetime
import io
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.accounts.rights import Rights
from rentalars.core import import_exports
from rentalars.core.models import CompanyProfile
from rentalars.masterdata.models import CategoryField, FieldType
from rentalars.material import dguv, services
from rentalars.material.importer import import_material, read_table, resolve_mapping
from rentalars.material.inspection_report import render_report_html, render_report_pdf
from rentalars.material.inspections import InspectionPlan
from rentalars.material.models import (
    Inspection,
    InspectionResult,
    InspectionType,
    ItemStatus,
    MaterialItem,
    MaterialModel,
    ProtectionClass,
)
from tests.api.base import API, ApiTestCase
from tests.helpers import RentalarsTestCase, category, make_item, make_model, make_product
from tests.ui.base import UiTestCase, form_data

TODAY = datetime.date(2027, 3, 1)  # the test clock


def length_field() -> CategoryField:
    """The category-specific field "Länge" in m of the cables, as the start data of new installations has it."""
    return CategoryField.objects.get_or_create(
        category=category("K"), label="Länge", defaults={"field_type": FieldType.NUMBER, "unit": "m", "position": 1}
    )[0]


def setup_dguv(test: Any) -> None:
    """An electrical inspection "E-Check" for the cables, a 10 m extension lead of class I as item 0042."""
    length_field()
    test.electric = InspectionType.objects.create(name="E-Check", interval_months=12, is_electrical=True)
    test.electric.categories.add(category("K"))
    test.visual = InspectionType.objects.create(name="Sichtkontrolle", interval_months=6)
    test.visual.categories.add(category("K"))
    model = make_model("Schuko-Verlängerung", make_product("K-100"), category_code="K")
    model.set_category_specific_value("10")
    model.protection_class = ProtectionClass.I
    model.save()
    test.cable_model = model
    test.cable = make_item(model, 42, serial_number="SN-4711")


def good_values(**changes: Any) -> dict[str, Any]:
    """The values of a class I device that passes, with a 10 m cord."""
    values: dict[str, Any] = {
        "protection_class": "I",
        "cord_length_m": Decimal("10"),
        "test_device": "Benning ST 760, SN 12345",
        "visual_check_passed": True,
        "pe_resistance_ohm": Decimal("0.12"),
        "insulation_resistance_mohm": Decimal("250"),
        "pe_current_ma": Decimal("0.4"),
        "touch_current_ma": None,
        "function_test_passed": True,
    }
    values.update(changes)
    return values


# --- The limits and the suggestion ------------------------------------------------------------------------------


class LimitTests(RentalarsTestCase):
    """MAT-078: DIN VDE 0701-0702, kept in one place (``dguv.LIMITS``): per protection class, and the length of the cord."""

    def test_protective_conductor_resistance_grows_with_the_cord(self) -> None:
        cases = {
            None: "0.3",  # no length known: the limit of a short cord
            "0": "0.3",
            "5": "0.3",
            "5.01": "0.4",  # every further 7.5 m begun adds 0.1 Ω
            "10": "0.4",
            "12.5": "0.4",
            "12.6": "0.5",
            "20": "0.5",
            "50": "0.9",
            "50.1": "1",  # 1 Ω at most
            "100": "1",
        }
        for length, limit in cases.items():
            with self.subTest(length=length):
                cord = Decimal(length) if length is not None else None
                self.assertEqual(dguv.pe_resistance_limit(cord), Decimal(limit))

    def test_limits_per_protection_class(self) -> None:
        by_name = dguv.MEASUREMENTS_BY_NAME
        expected = {
            "I": {
                "pe_resistance_ohm": "0.3",
                "insulation_resistance_mohm": "1",
                "pe_current_ma": "3.5",
                "touch_current_ma": "0.5",
            },
            "II": {
                "pe_resistance_ohm": None,
                "insulation_resistance_mohm": "2",
                "pe_current_ma": None,
                "touch_current_ma": "0.5",
            },
            "III": {
                "pe_resistance_ohm": None,
                "insulation_resistance_mohm": "0.25",
                "pe_current_ma": None,
                "touch_current_ma": None,
            },
        }
        for protection_class, limits in expected.items():
            for name, limit in limits.items():
                with self.subTest(protection_class=protection_class, measurement=name):
                    found = dguv.limit_for(by_name[name], protection_class, Decimal("3"))
                    self.assertEqual(found, Decimal(limit) if limit is not None else None)
        # The limits are data with their source, read by everything else.
        self.assertEqual(dguv.LIMITS.insulation_resistance_mohm["II"], Decimal("2"))
        self.assertEqual((dguv.LIMITS.pe_current_ma, dguv.LIMITS.touch_current_ma), (Decimal("3.5"), Decimal("0.5")))

    def test_texts_of_a_check(self) -> None:
        check = dguv.evaluate(good_values(pe_resistance_ohm=Decimal("0.52"))).checks[0]
        self.assertEqual((check.value_text, check.limit_text, check.verdict), ("0,52 Ω", "≤ 0,4 Ω", "exceeded"))
        self.assertEqual((check.verdict_text, check.limit_note), ("außerhalb des Grenzwerts", "bei 10 m Leitung"))
        insulation = dguv.evaluate(
            good_values(protection_class="II", pe_resistance_ohm=None, pe_current_ma=None)
        ).checks
        self.assertEqual((insulation[1].limit_text, insulation[1].verdict_text), ("≥ 2 MΩ", "im Grenzwert"))
        self.assertEqual(insulation[0].verdict_text, "nur bei Schutzklasse I")
        self.assertEqual(insulation[3].verdict_text, "nicht gemessen")
        short = dguv.evaluate(good_values(cord_length_m=None)).checks[0]
        self.assertEqual(short.limit_note, "Leitung bis 5 m – gib bei einer längeren die Länge an")


class SuggestionTests(RentalarsTestCase):
    """MAT-078: "bestanden" when the visual inspection passed, no function test failed and every value given is within."""

    def assert_suggests(self, values: dict[str, Any], result: str, reasons: list[str] | None = None) -> None:
        evaluation = dguv.evaluate(values)
        self.assertEqual(evaluation.suggested_result, result)
        if reasons is not None:
            self.assertEqual(evaluation.reasons, reasons)

    def test_passed(self) -> None:
        self.assert_suggests(good_values(), InspectionResult.PASSED, [])
        # A function test that does not apply (a cable) does not count against it, nor R_ISO not measured –
        # only because I_PE was measured instead (dguv.REQUIRED; tests/unit/test_093_review_material.py).
        self.assert_suggests(
            good_values(function_test_passed=None, insulation_resistance_mohm=None), InspectionResult.PASSED, []
        )

    def test_failed_with_the_reasons(self) -> None:
        self.assert_suggests(
            good_values(visual_check_passed=False, pe_current_ma=Decimal("3.6"), function_test_passed=False),
            InspectionResult.FAILED,
            [
                "Sichtprüfung nicht bestanden.",
                "IPE 3,6 mA liegt außerhalb des Grenzwerts ≤ 3,5 mA.",
                "Funktionsprüfung nicht bestanden.",
            ],
        )
        self.assert_suggests(
            good_values(visual_check_passed=None), InspectionResult.FAILED, ["Sichtprüfung nicht erfasst."]
        )

    def test_the_length_of_the_cord_decides(self) -> None:
        self.assert_suggests(good_values(pe_resistance_ohm=Decimal("0.35")), InspectionResult.PASSED)
        self.assert_suggests(
            good_values(pe_resistance_ohm=Decimal("0.35"), cord_length_m=Decimal("5")),
            InspectionResult.FAILED,
            ["RPE 0,35 Ω liegt außerhalb des Grenzwerts ≤ 0,3 Ω."],
        )

    def test_the_protection_class_decides(self) -> None:
        values = {"visual_check_passed": True, "insulation_resistance_mohm": Decimal("1.5")}
        # Review: class I needs R_PE as well – without it the suggestion is "failed" (dguv.REQUIRED).
        self.assert_suggests({**values, "protection_class": "I"}, InspectionResult.FAILED)
        self.assert_suggests({**values, "protection_class": "I", "pe_resistance_ohm": "0,1"}, InspectionResult.PASSED)
        self.assert_suggests({**values, "protection_class": "II"}, InspectionResult.FAILED)
        self.assert_suggests({**values, "protection_class": "III"}, InspectionResult.PASSED)
        self.assert_suggests({**values, "protection_class": "II", "touch_current_ma": "0,6"}, InspectionResult.FAILED)
        # Without the class there are no limits and no suggestion.
        evaluation = dguv.evaluate(values)
        self.assertEqual((evaluation.complete, evaluation.suggested_result), (False, ""))


class CordLengthTests(RentalarsTestCase):
    """MAT-078: the length for the limit comes from the category-specific "Länge" – the item's own value first."""

    def test_from_the_model_and_the_item(self) -> None:
        setup_dguv(self)
        self.assertEqual(dguv.cord_length_of(self.cable), Decimal("10"))
        self.cable.set_field_override(length_field(), "25")
        self.assertEqual(dguv.cord_length_of(self.cable), Decimal("25"))
        lamp = make_item(make_model("PAR 64", category_code="L"), 43)
        self.assertIsNone(dguv.cord_length_of(lamp))

    def test_in_centimetres(self) -> None:
        field = CategoryField.objects.create(
            category=category("L"), label="Kabellänge", field_type=FieldType.NUMBER, unit="cm", position=1
        )
        model = make_model("LED-Leiste", category_code="L")
        model.set_field_value(field, "150")
        model.save()
        self.assertEqual(dguv.cord_length_of(make_item(model, 44)), Decimal("1.5"))


# --- The protection class ---------------------------------------------------------------------------------------


class ProtectionClassTests(RentalarsTestCase):
    """MAT-077: at the model for its items; an item may have its own, which the same as the model's is not."""

    def test_the_item_follows_its_model_unless_it_has_its_own(self) -> None:
        setup_dguv(self)
        self.assertEqual(self.cable.effective_protection_class, "I")
        self.cable.protection_class_override = ProtectionClass.II
        self.cable.full_clean()
        self.cable.save()
        self.assertEqual(MaterialItem.objects.get(pk=self.cable.pk).effective_protection_class, "II")
        self.cable.protection_class_override = ProtectionClass.I  # the model's: no class of its own
        self.cable.full_clean()
        self.assertEqual(self.cable.protection_class_override, "")
        self.assertEqual(make_item(make_model("Mischpult"), 50).effective_protection_class, "")


class ProtectionClassPageTests(UiTestCase):
    """MAT-077: model and item pages and forms, the item list as an optional column, the copy of a model."""

    def setUp(self) -> None:
        super().setUp()
        setup_dguv(self)

    def test_model_form_and_page(self) -> None:
        url = reverse("material:model_edit", args=[self.cable_model.pk])
        page = self.client.get(url)
        self.assertIn('<option value="I" selected>I (Schutzleiter)</option>', self.assert_ok(page))
        self.client.post(url, form_data(page, containing="protection_class", protection_class="II"))
        self.assertEqual(MaterialModel.objects.get(pk=self.cable_model.pk).protection_class, "II")
        detail = self.assert_ok(self.client.get(reverse("material:model_detail", args=[self.cable_model.pk])))
        self.assertIn("<dt>Schutzklasse</dt><dd>II (Schutzisolierung)</dd>", detail)
        copy = self.assert_ok(self.client.get(reverse("material:model_create") + f"?copy={self.cable_model.pk}"))
        self.assertIn('<option value="II" selected>', copy)

    def test_item_form_and_page(self) -> None:
        url = reverse("material:item_edit", args=[self.cable.pk])
        page = self.client.get(url)
        self.assertIn("Leer: wie das Modell – I (Schutzleiter)", self.assert_ok(page))
        response = self.client.post(
            url, form_data(page, containing="protection_class_override", protection_class_override="II")
        )
        self.assertEqual(response.status_code, 302, response.content.decode()[:800])
        self.assertEqual(MaterialItem.objects.get(pk=self.cable.pk).protection_class_override, "II")
        detail = self.assert_ok(self.client.get(reverse("material:item_detail", args=[self.cable.pk])))
        self.assertIn("<dt>Schutzklasse</dt><dd>II (Schutzisolierung) <span", detail)
        self.assertIn("Das Modell sagt: I (Schutzleiter)", detail)
        history = self.assert_ok(self.client.get(reverse("material:item_history", args=[self.cable.pk])))
        self.assertIn("Eigene Schutzklasse: <del>–</del> → II (Schutzisolierung)", history)

    def test_optional_column_of_the_item_list(self) -> None:
        make_item(make_model("Mischpult"), 51)
        page = self.assert_ok(self.client.get(reverse("material:item_list")))
        self.assertNotIn(">Schutzklasse<", page)
        page = self.assert_ok(
            self.client.get(reverse("material:item_list"), {"cols": "id,protection_class", "sort": "-protection_class"})
        )
        self.assertIn("Schutzklasse", page)
        self.assertLess(page.index("0042"), page.index("0051"))  # "I" before none when sorted downwards


# --- Recording an electrical inspection ---------------------------------------------------------------------------


class RecordingTests(RentalarsTestCase):
    """MAT-078: the service – the rules of the values, the note, the consequences of "failed"."""

    def setUp(self) -> None:
        super().setUp()
        setup_dguv(self)

    def record(self, result: str = InspectionResult.PASSED, note: str = "", **values: Any) -> Inspection:
        return services.record_inspection(
            self.cable,
            self.electric,
            date=datetime.date(2027, 2, 26),
            inspector="E. Fachkraft",
            result=result,
            note=note,
            electrical=good_values(**values),
        )

    def test_the_values_are_kept(self) -> None:
        inspection = self.record()
        inspection.refresh_from_db()
        self.assertTrue(inspection.is_electrical)
        self.assertEqual(
            (inspection.protection_class, inspection.pe_resistance_ohm, inspection.test_device),
            ("I", Decimal("0.120"), "Benning ST 760, SN 12345"),
        )
        self.assertEqual(inspection.evaluation.suggested_result, InspectionResult.PASSED)
        self.assertEqual(self.due_dates()["E-Check"], datetime.date(2028, 2, 26))  # the due logic as before

    def due_dates(self) -> dict[str, datetime.date | None]:
        """When the cable is due for each of its inspections."""
        cable = MaterialItem.objects.get(pk=self.cable.pk)
        return {due.inspection_type.name: due.due_date for due in InspectionPlan().dues_for([cable])[cable.pk]}

    def test_passed_against_the_values_needs_a_reason(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            self.record(pe_resistance_ohm=Decimal("0.52"))
        message = caught.exception.message_dict["note"][0]
        self.assertIn(
            "Die Werte sprechen für „fehlgeschlagen“: RPE 0,52 Ω liegt außerhalb des Grenzwerts ≤ 0,4 Ω.", message
        )
        self.assertFalse(Inspection.objects.exists())
        with self.assertRaises(ValidationError) as caught:
            self.record(visual_check_passed=False)
        self.assertIn("note", caught.exception.message_dict)
        inspection = self.record(pe_resistance_ohm=Decimal("0.52"), note="Nachgemessen mit 4-Leiter-Methode: 0,31 Ω")
        self.assertTrue(inspection.passed)
        self.assertEqual(MaterialItem.objects.get(pk=self.cable.pk).status, ItemStatus.AVAILABLE)

    def test_failed_sets_the_item_defective_with_the_reasons_and_due_again(self) -> None:
        self.record(InspectionResult.FAILED, insulation_resistance_mohm=Decimal("0.4"))
        cable = MaterialItem.objects.get(pk=self.cable.pk)
        self.assertEqual(cable.status, ItemStatus.DEFECTIVE)
        self.assertEqual(
            cable.status_reason,
            "Prüfung „E-Check“ am 26.02.2027 nicht bestanden: RISO 0,4 MΩ liegt außerhalb des Grenzwerts ≥ 1 MΩ.",
        )
        self.assertEqual(self.due_dates()["E-Check"], datetime.date(2027, 2, 26))  # due again at once

    def test_the_rules_of_the_values(self) -> None:
        cases = {
            "protection_class": {"protection_class": ""},
            "visual_check_passed": {"visual_check_passed": None},
            "pe_resistance_ohm": {"protection_class": "II", "pe_current_ma": None},  # R_PE only for class I
            "touch_current_ma": {
                "protection_class": "III",
                "pe_resistance_ohm": None,
                "pe_current_ma": None,
                "touch_current_ma": Decimal("0.1"),
            },
            "cord_length_m": {"cord_length_m": Decimal("-1")},
        }
        for field, changes in cases.items():
            with self.subTest(field=field), self.assertRaises(ValidationError) as caught:
                self.record(**changes)
            self.assertIn(field, caught.exception.message_dict)
        with self.assertRaises(ValidationError) as caught:
            self.record(protection_class="II", pe_current_ma=None)
        self.assertEqual(
            caught.exception.message_dict["pe_resistance_ohm"],
            ["Wird nur bei Schutzklasse I gemessen. Lass das Feld bei Schutzklasse II leer."],
        )

    def test_other_inspections_take_no_values(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            services.record_inspection(
                self.cable, self.visual, date=TODAY, inspector="Luka", result="passed", electrical=good_values()
            )
        self.assertIn(
            "Messwerte gibt es nur bei einer elektrischen Prüfung", caught.exception.message_dict["inspection_type"][0]
        )
        inspection = services.record_inspection(
            self.cable,
            self.visual,
            date=TODAY,
            inspector="Luka",
            result="passed",
            electrical={"pe_resistance_ohm": None},
        )
        self.assertFalse(inspection.is_electrical)
        self.assertIsNone(inspection.evaluation)


class InspectionPageTests(UiTestCase):
    """MAT-078: the form with and without scripts – limits next to the values, marks, the suggestion, the note rule."""

    def setUp(self) -> None:
        super().setUp()
        setup_dguv(self)
        self.url = reverse("material:item_inspections", args=[self.cable.pk])

    def test_the_form_starts_with_the_item(self) -> None:
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn("<legend>Elektrische Prüfung (DGUV V3 / DIN VDE 0701-0702)</legend>", page)
        self.assertIn(f'data-show-if="inspection_type={self.electric.pk}"', page)
        self.assertIn('<option value="I" selected>I (Schutzleiter)</option>', page)
        self.assertIn('name="cord_length_m" value="10"', page)
        self.assertIn('<div class="help" id="dguv-pe_resistance_ohm">Grenzwert ≤ 0,4 Ω (bei 10 m Leitung)</div>', page)
        self.assertIn('aria-describedby="dguv-pe_resistance_ohm"', page)
        self.assertIn("Schutzleiterwiderstand R<sub>PE</sub> (Ω)", page)
        self.assertIn("Isolationswiderstand R<sub>ISO</sub> (MΩ)", page)
        self.assertIn('<div class="help" id="dguv-touch_current_ma">Grenzwert ≤ 0,5 mA</div>', page)

    def test_without_scripts_the_values_are_judged_when_sent(self) -> None:
        data = form_data(
            self.client.get(self.url),
            containing="inspector",
            inspection_type=self.electric.pk,
            date="2027-02-26",
            inspector="E. Fachkraft",
            visual_check_passed="yes",
            pe_resistance_ohm="0,52",
            insulation_resistance_mohm="250",
            function_test_passed="yes",
            result="passed",
        )
        page = self.assert_ok(self.client.post(self.url, data))
        self.assertIn("Die Werte sprechen für „fehlgeschlagen“", page)
        self.assertIn('<span class="badge red">außerhalb des Grenzwerts</span>', page)
        self.assertIn('<span class="badge green">im Grenzwert</span>', page)  # R_ISO
        self.assertIn('Vorgeschlagenes Ergebnis:</strong> <span class="badge red">fehlgeschlagen</span>', page)
        self.assertFalse(Inspection.objects.exists())
        data["result"] = "failed"
        response = self.client.post(self.url, data, follow=True)
        page = self.assert_ok(response)
        inspection = Inspection.objects.get()
        self.assertEqual((inspection.pe_resistance_ohm, inspection.result), (Decimal("0.520"), "failed"))
        self.assertEqual(MaterialItem.objects.get(pk=self.cable.pk).status, ItemStatus.DEFECTIVE)
        # The list of inspections shows the values with their limits and the protocol.
        self.assertIn('<summary>Messwerte <span class="badge red">1 außerhalb des Grenzwerts</span></summary>', page)
        self.assertIn("<td>0,52 Ω</td><td>≤ 0,4 Ω", page)
        self.assertIn(reverse("material:inspection_report", args=[inspection.pk]), page)
        self.assertIn("Prüfprotokoll (PDF)", page)

    def test_the_test_device_is_remembered(self) -> None:
        services.record_inspection(
            self.cable,
            self.electric,
            date=TODAY,
            inspector="E",
            result="passed",
            electrical=good_values(test_device="Gossen Secutest, SN 9"),
            user=self.admin_user,
        )
        page = self.assert_ok(self.client.get(self.url))
        self.assertIn('value="Gossen Secutest, SN 9"', page)

    def test_another_type_ignores_the_values(self) -> None:
        data = form_data(
            self.client.get(self.url),
            containing="inspector",
            inspection_type=self.visual.pk,
            date="2027-02-26",
            inspector="Luka",
            pe_resistance_ohm="kaputt",
        )
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        inspection = Inspection.objects.get()
        self.assertEqual((inspection.inspection_type, inspection.is_electrical), (self.visual, False))

    def test_the_live_check(self) -> None:
        data = form_data(
            self.client.get(self.url), containing="inspector", visual_check_passed="yes", pe_resistance_ohm="0,45"
        )
        url = reverse("material:inspection_check", args=[self.cable.pk])
        answer = self.assert_ok(self.htmx("post", url, data))
        self.assertIn('Vorgeschlagenes Ergebnis:</strong> <span class="badge red">fehlgeschlagen</span>', answer)
        self.assertIn("RPE 0,45 Ω liegt außerhalb des Grenzwerts ≤ 0,4 Ω.", answer)
        self.assertIn('<div class="help" id="dguv-pe_resistance_ohm" hx-swap-oob="true">', answer)
        # Review: "bestanden" needs the insulation check as well (dguv.REQUIRED); it was left out here before.
        self.assertIn("Isolationsprüfung fehlt: Isolationswiderstand oder Ableitstrom messen.", answer)
        data["insulation_resistance_mohm"] = "250"
        data["cord_length_m"] = "15"
        answer = self.assert_ok(self.htmx("post", url, data))
        self.assertIn('<span class="badge green">bestanden</span>', answer)
        self.assertIn("Grenzwert ≤ 0,5 Ω (bei 15 m Leitung)", answer)
        data["protection_class"] = ""
        self.assertIn("Wähle die Schutzklasse", self.assert_ok(self.htmx("post", url, data)))

    def test_no_electrical_type_no_fields(self) -> None:
        self.electric.is_electrical = False
        self.electric.save()
        page = self.assert_ok(self.client.get(self.url))
        self.assertNotIn("dguv-", page)
        self.assertEqual(self.client.post(reverse("material:inspection_check", args=[self.cable.pk])).status_code, 404)


class ProtocolTests(UiTestCase):
    """MAT-078: the printable protocol – company, item, date, inspector, test device, values with limits and verdicts."""

    def setUp(self) -> None:
        super().setUp()
        setup_dguv(self)
        company = CompanyProfile.load()
        company.name, company.city = "Licht & Ton GmbH", "Musterstadt"
        company.save()
        self.inspection = services.record_inspection(
            self.cable,
            self.electric,
            date=datetime.date(2027, 2, 26),
            inspector="E. Fachkraft",
            result="passed",
            note="Stecker erneuert",
            electrical=good_values(function_test_passed=None),
        )

    def test_the_html(self) -> None:
        html = render_report_html(self.inspection)
        for text in (
            "Licht &amp; Ton GmbH",
            "Prüfprotokoll",
            "0042",
            "Schuko-Verlängerung",
            "SN-4711",
            "I (Schutzleiter)",
            "26.02.2027",
            "E. Fachkraft",
            "Benning ST 760, SN 12345",
            "Schutzleiterwiderstand R<sub>PE</sub>",
            "0,12 Ω",
            "≤ 0,4 Ω",
            "im Grenzwert",
            "≥ 1 MΩ",
            "entfällt",
            "Bestanden",
            "nächste Prüfung fällig bis 26.02.2028",
            "Stecker erneuert",
        ):
            with self.subTest(text=text):
                self.assertIn(text, html)

    def test_the_pdf_on_the_page(self) -> None:
        self.assertTrue(render_report_pdf(self.inspection).startswith(b"%PDF"))
        response = self.client.get(reverse("material:inspection_report", args=[self.inspection.pk]))
        self.assertEqual((response.status_code, response["Content-Type"]), (200, "application/pdf"))
        self.assertIn('filename="Pruefprotokoll-0042-2027-02-26.pdf"', response["Content-Disposition"])
        other = services.record_inspection(self.cable, self.visual, date=TODAY, inspector="Luka", result="passed")
        self.assertEqual(self.client.get(reverse("material:inspection_report", args=[other.pk])).status_code, 404)


class RightsTests(UiTestCase):
    """MAT-078: as the inspections so far, reading material shows them and the protocol; recording needs write access."""

    def setUp(self) -> None:
        super().setUp()
        setup_dguv(self)
        self.inspection = services.record_inspection(
            self.cable, self.electric, date=TODAY, inspector="E", result="passed", electrical=good_values()
        )

    def test_reader_and_outsider(self) -> None:
        reader = self.browser_for("rita", "Nur-Lesen")
        page = self.assert_ok(reader.get(reverse("material:item_inspections", args=[self.cable.pk])))
        self.assertIn("Messwerte", page)
        self.assertNotIn("dguv-suggestion", page)  # no form
        self.assertEqual(reader.get(reverse("material:inspection_report", args=[self.inspection.pk])).status_code, 200)
        self.assertEqual(
            reader.post(
                reverse("material:inspection_check", args=[self.cable.pk]), {"protection_class": "I"}
            ).status_code,
            403,
        )
        Role.objects.create(name="Ohne Material", module_levels={"projects": 1})
        outsider = self.browser_for("otto", "Ohne Material")
        self.assertEqual(
            outsider.get(reverse("material:inspection_report", args=[self.inspection.pk])).status_code, 403
        )
        warehouse = self.browser_for("luka", "Lager")
        self.assertEqual(
            self.htmx(
                "post", reverse("material:inspection_check", args=[self.cable.pk]), {"protection_class": "I"}, warehouse
            ).status_code,
            200,
        )


# --- Import and export --------------------------------------------------------------------------------------------


def export_text() -> str:
    """The material list in the import format, for all rights."""
    return import_exports.text_of(import_exports.get("material"), Rights.everything())


def run_import(text: str, *, dry_run: bool) -> Any:
    """Import a CSV text as the material import does."""
    table = read_table(io.BytesIO(text.encode("utf-8")), "material.csv")
    return import_material(table, resolve_mapping(table.headers, {}), dry_run=dry_run, rights=Rights.everything())


class ImportExportTests(RentalarsTestCase):
    """MAT-077, IMP-017: the column "Schutzklasse" in the import and in its export, which comes back unchanged."""

    def setUp(self) -> None:
        super().setUp()
        setup_dguv(self)
        # A second item of the class I model with its own class II, and a model without a class whose item has III.
        make_item(self.cable_model, 43, protection_class_override="II")
        lamp = make_item(make_model("Arbeitsleuchte", category_code="L"), 44, protection_class_override="III")
        self.lamp = lamp

    def test_round_trip(self) -> None:
        text = export_text()
        heading = text.lstrip("﻿").split("\r\n", 1)[0].split(";")
        self.assertEqual(heading[-1], "Schutzklasse")
        rows = {line.split(";")[0]: line.split(";")[-1] for line in text.lstrip("﻿").split("\r\n")[1:] if line}
        self.assertEqual((rows["0042"], rows["0043"], rows["0044"]), ("I", "II", "III"))
        report = run_import(text, dry_run=True).as_dict()
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(report["row_counts"], {"new": 0, "changed": 0, "unchanged": 3, "error": 0})

    def test_a_new_list(self) -> None:
        text = (
            "ID;Artikelname;Kategorie;Schutzklasse\r\n"
            "0101;Kabeltrommel 25 m;K;SK I\r\n"
            "0102;Kabeltrommel 25 m;K;1\r\n"
            "0103;Nebelmaschine;L;II\r\n"
            "0104;Nebelmaschine;L;Schutzklasse 1\r\n"
            "0105;Arbeitsleuchte;L;\r\n"
        )
        report = run_import(text, dry_run=False)
        self.assertTrue(report.ok, report.errors)
        drum = MaterialModel.objects.get(name="Kabeltrommel 25 m")
        self.assertEqual(drum.protection_class, "I")  # all its rows agree: the model's
        self.assertEqual(set(drum.items.values_list("protection_class_override", flat=True)), {""})
        fog = MaterialModel.objects.get(name="Nebelmaschine")
        self.assertEqual(fog.protection_class, "")  # its rows disagree: each item its own
        self.assertEqual(
            dict(fog.items.values_list("inventory_number", "protection_class_override")), {103: "II", 104: "I"}
        )
        # A model with a class keeps it; the cell gives the item its own or none.
        self.assertEqual(self.lamp.material_model.protection_class, "")
        self.assertEqual(MaterialItem.objects.get(inventory_number=105).protection_class_override, "")

    def test_an_existing_model_keeps_its_class(self) -> None:
        text = (
            "ID;Artikelname;Kategorie;Schutzklasse\r\n0042;Schuko-Verlängerung;K;II\r\n0043;Schuko-Verlängerung;K;I\r\n"
        )
        report = run_import(text, dry_run=False)
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(MaterialModel.objects.get(pk=self.cable_model.pk).protection_class, "I")
        self.assertEqual(
            dict(self.cable_model.items.values_list("inventory_number", "protection_class_override")),
            {42: "II", 43: ""},
        )

    def test_unknown_class(self) -> None:
        report = run_import("ID;Artikelname;Kategorie;Schutzklasse\r\n0101;Lampe;L;IV\r\n", dry_run=True)
        # IMP-010: a hint, not an error – the item comes in as "Fehler Import".
        self.assertEqual(report.errors, [])
        self.assertEqual(
            [issue.message for issue in report.warnings if issue.row],
            ["„IV“ ist keine Schutzklasse. Schreib I, II oder III."],
        )


# --- The API ------------------------------------------------------------------------------------------------------


class DguvApiTests(ApiTestCase):
    """MAT-077, MAT-078, API-002, API-014: the protection class, the electrical type, recording with values, the
    check, the protocol."""

    def setUp(self) -> None:
        super().setUp()
        setup_dguv(self)

    def test_protection_class_of_model_and_item(self) -> None:
        model_url = f"{API}/material-models/{self.cable_model.pk}"
        self.assertEqual(self.admin.get(model_url).json()["protection_class"], "I")
        response = self.admin.patch(model_url, {"protection_class": "II"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        item_url = f"{API}/material-items/{self.cable.pk}"
        item = self.admin.get(item_url).json()
        self.assertEqual((item["protection_class_override"], item["effective_protection_class"]), ("", "II"))
        item = self.admin.patch(item_url, {"protection_class_override": "III"}, format="json").json()
        self.assertEqual((item["protection_class_override"], item["effective_protection_class"]), ("III", "III"))
        item = self.admin.patch(item_url, {"protection_class_override": "II"}, format="json").json()
        self.assertEqual(item["protection_class_override"], "")  # the model's: none of its own
        self.assert_error(
            self.admin.patch(model_url, {"protection_class": "IV"}, format="json"),
            400,
            "validation_error",
            "protection_class",
        )

    def test_inspection_types_marked_electrical(self) -> None:
        created = self.admin.post(
            f"{API}/inspection-types", {"name": "DGUV V3", "interval_months": 12, "is_electrical": True}, format="json"
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertTrue(self.admin.get(f"{API}/inspection-types/{created.json()['id']}").json()["is_electrical"])

    def test_record_check_and_protocol(self) -> None:
        url = f"{API}/material-items/{self.cable.pk}/inspections"
        body = {
            "inspection_type": self.electric.pk,
            "date": "2027-02-26",
            "inspector": "E. Fachkraft",
            "result": "passed",
            "visual_check_passed": True,
            "pe_resistance_ohm": "0.52",
            "insulation_resistance_mohm": 250,
            "function_test_passed": True,
            "test_device": "Benning ST 760",
        }
        refused = self.assert_error(self.admin.post(url, body, format="json"), 400, "validation_error", "note")
        self.assertIn("RPE 0,52 Ω", refused["fields"]["note"][0]["message"])
        recorded = self.admin.post(url, {**body, "note": "Nachgemessen: 0,31 Ω"}, format="json")
        self.assertEqual(recorded.status_code, 201, recorded.content)
        data = recorded.json()
        # Protection class and cord length were taken from the item.
        self.assertEqual(
            (data["protection_class"], data["cord_length_m"], data["pe_resistance_ohm"]), ("I", "10.00", "0.520")
        )
        values = {value["name"]: value for value in data["evaluation"]["values"]}
        self.assertEqual(
            values["pe_resistance_ohm"],
            {
                "name": "pe_resistance_ohm",
                "symbol": "RPE",
                "unit": "Ω",
                "value": "0.52",
                "limit": "0.4",
                "limit_kind": "max",
                "applies": True,
                "within_limit": False,
                "required_missing": False,  # Review: added
            },
        )
        self.assertFalse(values["pe_current_ma"]["within_limit"] is False)
        self.assertEqual(data["evaluation"]["suggested_result"], "failed")
        self.assertEqual(data["report_url"], f"/api/v1/inspections/{data['id']}/report")
        done = self.admin.get(url).json()["done"]
        self.assertEqual(done[0]["evaluation"]["reasons"], ["RPE 0,52 Ω liegt außerhalb des Grenzwerts ≤ 0,4 Ω."])
        report = self.admin.get(data["report_url"])
        self.assertEqual((report.status_code, report["Content-Type"]), (200, "application/pdf"))
        self.assertTrue(report.content.startswith(b"%PDF"))

        # The check stores nothing. (With R_ISO – "passed" needs the insulation check, dguv.REQUIRED.)
        check_url = f"{url}/check"
        checked = self.admin.post(
            check_url,
            {
                "visual_check_passed": True,
                "pe_resistance_ohm": "0.45",
                "insulation_resistance_mohm": "250",
                "cord_length_m": 15,
            },
            format="json",
        )
        self.assertEqual(checked.status_code, 200, checked.content)
        self.assertEqual((checked.json()["suggested_result"], checked.json()["cord_length_m"]), ("passed", "15"))
        self.assertEqual(Inspection.objects.count(), 1)
        self.assert_error(
            self.admin.post(check_url, {"protection_class": "V"}, format="json"),
            400,
            "validation_error",
            "protection_class",
        )

    def test_multipart_with_protocol_and_the_rules(self) -> None:
        from django.core.files.uploadedfile import SimpleUploadedFile

        url = f"{API}/material-items/{self.cable.pk}/inspections"
        recorded = self.admin.post(
            url,
            {
                "inspection_type": self.electric.pk,
                "date": "2027-02-26",
                "inspector": "E",
                "result": "passed",
                "visual_check_passed": "true",
                "protection_class": "II",
                "insulation_resistance_mohm": "3,5",
                "protocol": SimpleUploadedFile("p.pdf", b"%PDF-1.4\n%%EOF\n", content_type="application/pdf"),
            },
            format="multipart",
        )
        self.assert_error(recorded, 400, "validation_error", "insulation_resistance_mohm")  # a point, as in JSON
        recorded = self.admin.post(
            url,
            {
                "inspection_type": self.electric.pk,
                "date": "2027-02-26",
                "inspector": "E",
                "result": "passed",
                "visual_check_passed": "true",
                "protection_class": "II",
                "insulation_resistance_mohm": "3.5",
            },
            format="multipart",
        )
        self.assertEqual(recorded.status_code, 201, recorded.content)
        self.assertIsNone(recorded.json()["function_test_passed"])  # left out: does not apply
        wrong = self.admin.post(
            url,
            {
                "inspection_type": self.electric.pk,
                "date": "2027-02-26",
                "inspector": "E",
                "result": "passed",
                "visual_check_passed": True,
                "protection_class": "II",
                "pe_resistance_ohm": "0.1",
            },
            format="json",
        )
        self.assert_error(wrong, 400, "validation_error", "pe_resistance_ohm")
        other = self.admin.post(
            url,
            {
                "inspection_type": self.visual.pk,
                "date": "2027-02-26",
                "inspector": "E",
                "result": "passed",
                "pe_resistance_ohm": "0.1",
            },
            format="json",
        )
        self.assert_error(other, 400, "validation_error", "inspection_type")
        plain = self.admin.post(
            url,
            {"inspection_type": self.visual.pk, "date": "2027-02-26", "inspector": "E", "result": "passed"},
            format="json",
        )
        self.assertEqual(plain.status_code, 201, plain.content)
        self.assertEqual((plain.json()["evaluation"], plain.json()["report_url"]), (None, ""))
        self.assertEqual(self.admin.get(f"{API}/inspections/{plain.json()['id']}/report").status_code, 404)

    def test_rights(self) -> None:
        inspection = services.record_inspection(
            self.cable, self.electric, date=TODAY, inspector="E", result="passed", electrical=good_values()
        )
        reader = self.client_for("rita", "Nur-Lesen")
        self.assertEqual(reader.get(f"{API}/inspections/{inspection.pk}/report").status_code, 200)
        self.assertEqual(reader.get(f"{API}/material-items/{self.cable.pk}/inspections").status_code, 200)
        check_url = f"{API}/material-items/{self.cable.pk}/inspections/check"
        self.assertEqual(reader.post(check_url, {"visual_check_passed": True}, format="json").status_code, 403)
        self.assertEqual(
            reader.post(
                f"{API}/material-items/{self.cable.pk}/inspections",
                {"inspection_type": self.electric.pk, "date": "2027-02-26", "inspector": "E", "result": "passed"},
                format="json",
            ).status_code,
            403,
        )
        crew = self.client_for("chris", "Crew")
        self.assertEqual(crew.get(f"{API}/inspections/{inspection.pk}/report").status_code, 403)
        warehouse = self.client_for("luka", "Lager")
        self.assertEqual(warehouse.post(check_url, {"visual_check_passed": True}, format="json").status_code, 200)
