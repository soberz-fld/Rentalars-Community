# SPDX-License-Identifier: GPL-3.0-or-later
"""Four small requirements – duplicate serial numbers, notes at the job functions, year dropdowns.

1. Creating new items warns about a serial number that already exists – a serial number another item has
   already (any model, retired and sold items too; compared without case and surrounding spaces) is a WARNING: the
   forms ask for "Trotzdem anlegen" / "Trotzdem speichern", the API names it in ``warnings``, the import in its
   preview. Nothing is unique-constrained (MAT-004, MAT-050).
2. Personnel → job functions: a note says that prices are changed under the material management – the guide values of a job
   function are the hourly wage of the planned crew; what the customer pays is changed on the service product
   (PER-008, PRD-044).
3. Dropdowns for years, as in the reports, show more than one following year, ideally three – one helper, ``core.years.year_choices``, three years ahead (PRJ-115, MAT-053).

The fourth requirement (the back button after the browser's back button) is tested in the browser:
``tests/browser/test_095_back_in_browser.py``, and its server side in :class:`TrailFollowsTheReferer` below.
"""

from __future__ import annotations

import html
import io
import re
from typing import Any

from django.test import Client
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.core import trail
from rentalars.core.tabular import read_table
from rentalars.core.years import year_choices
from rentalars.material import serials, services
from rentalars.material.importer import import_material, resolve_mapping
from rentalars.material.models import ItemStatus, MaterialItem
from tests.api.base import API, ApiTestCase
from tests.helpers import (
    ALL_RIGHTS,
    RentalarsTestCase,
    category,
    job_function,
    make_item,
    make_model,
    make_person,
    make_product,
)
from tests.ui.base import UiTestCase, form_data

TOKEN = re.compile(r'name="confirm_serials" id="id_confirm_serials" value="([0-9a-f]+)"')


def token_of(page: str) -> str:
    """The mark of the warnings on a page, which the tick "create anyway" carries."""
    found = TOKEN.search(page)
    assert found, "the page shows no warning about serial numbers"
    return found.group(1)


# --- 1. Serial numbers that exist already ---------------------------------------------------------------------


class SerialClashTests(RentalarsTestCase):
    """The comparison and the wording (duplicate serial numbers; MAT-084)."""

    def setUp(self) -> None:
        super().setUp()
        self.shure = make_model("Shure SM58", category_code="T", manufacturer="Shure")
        self.sennheiser = make_model("Sennheiser e835", category_code="T", manufacturer="Sennheiser")

    def test_other_model_and_the_same_model_are_worded_differently(self) -> None:
        make_item(self.sennheiser, 42, serial_number="4711")
        make_item(self.shure, 7, serial_number="9000")
        other = serials.entry_warnings([("4711", self.shure.pk)])
        self.assertEqual(other, ["Die Seriennummer 4711 gibt es schon: Exemplar 0042 (Modell Sennheiser e835)."])
        same = serials.entry_warnings([("9000", self.shure.pk)])
        self.assertEqual(
            same, ["Die Seriennummer 9000 gibt es schon beim selben Modell: Exemplar 0007 (Modell Shure SM58)."]
        )

    def test_case_and_surrounding_spaces_do_not_matter(self) -> None:
        make_item(self.sennheiser, 42, serial_number="AB-12")
        self.assertEqual(len(serials.entry_warnings([("  ab-12 ", self.shure.pk)])), 1)
        self.assertEqual(serials.entry_warnings([("AB-13", self.shure.pk), ("", self.shure.pk)]), [])

    def test_umlauts_are_compared_by_the_program_not_by_the_collation(self) -> None:
        """(duplicate serial numbers; MAT-084) the same answer on every database: case-folded, not "Muller"."""
        make_item(self.sennheiser, 42, serial_number="MÜLLER-1")
        make_item(self.sennheiser, 43, serial_number="Straße-2")
        make_item(self.sennheiser, 44, serial_number="Mueller-3")
        for typed in ("müller-1", "Müller-1", " MÜLLER-1 "):
            self.assertEqual(len(serials.entry_warnings([(typed, self.shure.pk)])), 1, typed)
        self.assertEqual(len(serials.entry_warnings([("Straße-2", None)])), 1)  # the spelling as stored is found
        self.assertEqual(serials.entry_warnings([("Muller-1", None)]), [])  # a collation might say yes: we say no
        self.assertEqual(serials.entry_warnings([("Muller-3", None)]), [])

    def test_one_query_for_a_hundred_numbers(self) -> None:
        make_item(self.sennheiser, 42, serial_number="Z-77")
        entries = [(f"N-{number}", None) for number in range(100)]
        with self.assertNumQueries(1):
            self.assertEqual(serials.entry_warnings(entries), [])
        expected = serials.find_clashes([("z-77", None)])[0].text
        with self.assertNumQueries(2):  # a hundred and one numbers: two chunks
            self.assertEqual(serials.entry_warnings([*entries, ("z-77", None)]), [expected])

    def test_retired_and_sold_items_count_and_say_so(self) -> None:
        make_item(self.sennheiser, 42, serial_number="OLD-1", status=ItemStatus.RETIRED)
        make_item(self.sennheiser, 43, serial_number="OLD-2", status=ItemStatus.SOLD)
        warnings = serials.entry_warnings([("OLD-1", None), ("OLD-2", None)])
        self.assertEqual(
            warnings,
            [
                "Die Seriennummer OLD-1 gibt es schon: Exemplar 0042 (Modell Sennheiser e835, ausgemustert).",
                "Die Seriennummer OLD-2 gibt es schon: Exemplar 0043 (Modell Sennheiser e835, verkauft).",
            ],
        )

    def test_a_number_given_twice_in_one_entry_and_several_holders(self) -> None:
        self.assertEqual(
            serials.entry_warnings([("X1", self.shure.pk), ("x1", self.shure.pk), ("", None)]),
            ["Die Seriennummer X1 kommt in dieser Eingabe mehrfach vor."],
        )
        for number in (10, 11, 12, 13, 14):
            make_item(self.sennheiser, number, serial_number="MANY")
        (text,) = serials.entry_warnings([("MANY", None)])
        self.assertIn("Exemplar 0010 (Modell Sennheiser e835), Exemplar 0011", text)
        self.assertTrue(text.endswith("und 2 weitere."), text)

    def test_the_item_itself_does_not_count_and_nothing_is_unique(self) -> None:
        item = make_item(self.shure, 5, serial_number="SELF")
        self.assertEqual(serials.entry_warnings([("SELF", self.shure.pk)], exclude=[item.pk]), [])
        self.assertEqual(services.serial_number_warnings(item), [])
        twin = make_item(self.sennheiser, 6, serial_number="SELF")  # no constraint: saving works
        self.assertEqual(len(services.serial_number_warnings(twin)), 1)

    def test_a_number_twice_in_the_list_of_new_items_is_no_error_any_more(self) -> None:
        # before: "The serial number … is given twice." refused the list; now it is a warning of the forms.
        created = services.create_items(self.shure, 2, serial_numbers=["A1", "a1"])
        self.assertEqual([item.serial_number for item in created], ["A1", "a1"])
        self.assertEqual(services.check_serial_numbers(["B", "b"], 2), ["B", "b"])


class NewItemsFormTests(UiTestCase):
    """ "Neue Exemplare": the warning after the first submit, the second one with „Trotzdem anlegen“."""

    def setUp(self) -> None:
        super().setUp()
        self.shure = make_model("Shure SM58", make_product("T-010"), category_code="T")
        self.sennheiser = make_model("Sennheiser e835", category_code="T")
        self.url = reverse("material:item_create", args=[self.shure.pk])

    def submit(self, count: str = "1", serial_numbers: str = "", **more: Any) -> Any:
        data = form_data(self.client.get(self.url), count=count, serial_numbers=serial_numbers, **more)
        return self.client.post(self.url, data)

    def test_another_model_has_the_number_first_warning_then_confirmed(self) -> None:
        make_item(self.sennheiser, 42, serial_number="4711")
        response = self.submit(serial_numbers=" 4711 ")
        page = self.assert_ok(response)
        self.assertIn("Die Seriennummer 4711 gibt es schon: Exemplar 0042 (Modell Sennheiser e835).", page)
        self.assertIn("Trotzdem anlegen", page)
        self.assertEqual(MaterialItem.objects.filter(material_model=self.shure).count(), 0)  # nothing yet
        # what was typed stays in the form
        self.assertEqual(form_data(response)["serial_numbers"], " 4711 ")
        data = form_data(response, confirm_serials=token_of(page))
        confirmed = self.client.post(self.url, data)
        self.assertRedirects(confirmed, reverse("material:model_detail", args=[self.shure.pk]))
        self.assertEqual(
            list(MaterialItem.objects.filter(material_model=self.shure).values_list("serial_number", flat=True)),
            ["4711"],
        )

    def test_the_same_model_is_the_stronger_wording(self) -> None:
        make_item(self.shure, 42, serial_number="X-9")
        page = self.assert_ok(self.submit(serial_numbers="x-9"))
        self.assertIn("Die Seriennummer x-9 gibt es schon beim selben Modell: Exemplar 0042 (Modell Shure SM58).", page)

    def test_retired_items_count(self) -> None:
        make_item(self.sennheiser, 42, serial_number="OLD", status=ItemStatus.RETIRED)
        page = self.assert_ok(self.submit(serial_numbers="old"))
        self.assertIn("(Modell Sennheiser e835, ausgemustert)", page)
        self.assertIn("Ausgemusterte und verkaufte Exemplare zählen mit", page)

    def test_a_number_twice_in_the_same_list(self) -> None:
        response = self.submit(count="2", serial_numbers="Z-1\nz-1")
        page = self.assert_ok(response)
        self.assertIn("Die Seriennummer Z-1 kommt in dieser Eingabe mehrfach vor.", page)
        self.assertEqual(MaterialItem.objects.filter(material_model=self.shure).count(), 0)
        self.client.post(self.url, form_data(response, confirm_serials=token_of(page)))
        self.assertEqual(MaterialItem.objects.filter(material_model=self.shure).count(), 2)

    def test_the_tick_counts_for_these_warnings_only(self) -> None:
        make_item(self.sennheiser, 42, serial_number="4711")
        make_item(self.sennheiser, 43, serial_number="4712")
        page = self.assert_ok(self.submit(serial_numbers="4711"))
        # After the warning the user types another number that clashes too: the old tick does not carry over.
        data = form_data(self.client.get(self.url), serial_numbers="4712", confirm_serials=token_of(page))
        again = self.client.post(self.url, data)
        self.assertIn("Die Seriennummer 4712 gibt es schon", self.assert_ok(again))
        self.assertEqual(MaterialItem.objects.filter(material_model=self.shure).count(), 0)
        # A made-up mark does not either.
        data = form_data(self.client.get(self.url), serial_numbers="4712", confirm_serials="0" * 16)
        self.assertEqual(self.client.post(self.url, data).status_code, 200)

    def test_no_clash_no_question(self) -> None:
        make_item(self.sennheiser, 42, serial_number="4711")
        response = self.submit(serial_numbers="4712")
        self.assertEqual(response.status_code, 302)
        page = self.assert_ok(self.client.get(self.url))
        self.assertNotIn('name="confirm_serials"', page)

    def test_a_clash_in_the_form_for_bulk_material_too(self) -> None:
        make_item(self.sennheiser, 42, serial_number="BULK-1")
        bulk = make_model("Gaffa", bulk=True, category_code="K")
        url = reverse("material:item_create", args=[bulk.pk])
        page = self.assert_ok(self.client.post(url, form_data(self.client.get(url), serial_numbers="BULK-1")))
        self.assertIn("Die Seriennummer BULK-1 gibt es schon", page)


class ItemEditTests(UiTestCase):
    """The same question when an existing item's serial number is changed to a clashing one."""

    def setUp(self) -> None:
        super().setUp()
        self.shure = make_model("Shure SM58", category_code="T")
        self.sennheiser = make_model("Sennheiser e835", category_code="T")
        make_item(self.sennheiser, 42, serial_number="4711")
        self.item = make_item(self.shure, 7, serial_number="OWN-1")
        self.url = reverse("material:item_edit", args=[self.item.pk])

    def test_changed_to_a_clashing_number_asks_first(self) -> None:
        response = self.client.post(self.url, form_data(self.client.get(self.url), serial_number="4711"))
        page = self.assert_ok(response)
        self.assertIn("Die Seriennummer 4711 gibt es schon: Exemplar 0042 (Modell Sennheiser e835).", page)
        self.assertIn("Trotzdem speichern", page)
        self.assertEqual(MaterialItem.objects.get(pk=self.item.pk).serial_number, "OWN-1")
        confirmed = self.client.post(self.url, form_data(response, confirm_serials=token_of(page)))
        self.assertEqual(confirmed.status_code, 302)
        self.assertEqual(MaterialItem.objects.get(pk=self.item.pk).serial_number, "4711")

    def test_an_unchanged_number_is_not_asked_about_again(self) -> None:
        MaterialItem.objects.filter(pk=self.item.pk).update(serial_number="4711")  # clashes already
        response = self.client.post(self.url, form_data(self.client.get(self.url), note="geprüft"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(MaterialItem.objects.get(pk=self.item.pk).note, "geprüft")

    def test_the_own_number_in_another_case_is_no_clash(self) -> None:
        response = self.client.post(self.url, form_data(self.client.get(self.url), serial_number="own-1"))
        self.assertEqual(response.status_code, 302)


class PurchaseFormTests(UiTestCase):
    """ "Kauf einpflegen": per row serial numbers, checked against the stock and against each other."""

    def setUp(self) -> None:
        super().setUp()
        self.shure = make_model("Shure SM58", category_code="T", manufacturer="Shure")
        self.sennheiser = make_model("Sennheiser e835", category_code="T")
        make_item(self.sennheiser, 42, serial_number="4711")
        self.url = reverse("material:purchase")

    def data(self, **row: str) -> dict[str, Any]:
        data = form_data(self.client.get(self.url), containing="pos-TOTAL_FORMS")
        data.update({f"pos-0-{name}": value for name, value in row.items()})
        return {**data, "action": "save"}

    def test_a_number_the_stock_has_is_confirmed_first(self) -> None:
        data = self.data(model_name="Shure SM58", count="1", serial_numbers="4711")
        response = self.client.post(self.url, data)
        page = self.assert_ok(response)
        self.assertIn("Die Seriennummer 4711 gibt es schon: Exemplar 0042 (Modell Sennheiser e835).", page)
        self.assertIn("Trotzdem anlegen", page)
        self.assertEqual(MaterialItem.objects.count(), 1)
        confirmed = self.client.post(self.url, {**data, "confirm_serials": token_of(page)})
        self.assertEqual(confirmed.status_code, 302)
        self.assertEqual(MaterialItem.objects.filter(serial_number="4711").count(), 2)

    def test_a_number_in_two_rows_of_the_purchase(self) -> None:
        data = self.data(model_name="Shure SM58", count="1", serial_numbers="N-1")
        data.update(
            {
                "pos-TOTAL_FORMS": "2",
                "pos-1-model_name": "Sennheiser e835",
                "pos-1-count": "1",
                "pos-1-serial_numbers": "n-1",
            }
        )
        page = self.assert_ok(self.client.post(self.url, data))
        self.assertIn("Die Seriennummer N-1 kommt in dieser Eingabe mehrfach vor.", page)

    def test_a_new_model_can_only_clash_with_other_models(self) -> None:
        data = self.data(model_name="Neues Modell", category=str(category("K").pk), count="1", serial_numbers="4711")
        page = self.assert_ok(self.client.post(self.url, data))
        self.assertIn("Die Seriennummer 4711 gibt es schon: Exemplar 0042", page)
        self.assertNotIn("beim selben Modell", page)


class ApiWarningTests(ApiTestCase):
    """The API creates and names the warnings (``warnings``), as for a single item before."""

    def setUp(self) -> None:
        super().setUp()
        self.shure = make_model("Shure SM58", category_code="T")
        self.sennheiser = make_model("Sennheiser e835", category_code="T")
        make_item(self.sennheiser, 42, serial_number="4711")
        make_item(self.sennheiser, 43, serial_number="OLD", status=ItemStatus.SOLD)

    def test_one_item_of_another_model(self) -> None:
        response = self.admin.post(
            f"{API}/material-items", {"material_model": self.shure.pk, "serial_number": "4711"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            response.data["warnings"], ["Die Seriennummer 4711 gibt es schon: Exemplar 0042 (Modell Sennheiser e835)."]
        )

    def test_several_items_each_names_its_warning(self) -> None:
        response = self.admin.post(
            f"{API}/material-models/{self.shure.pk}/items",
            {"count": 4, "serial_numbers": ["4711", "ok-1", "old", "DOUBLE"]},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        rows = response.data
        self.assertIn("Exemplar 0042", rows[0]["warnings"][0])
        self.assertNotIn("warnings", rows[1])
        self.assertIn("verkauft", rows[2]["warnings"][0])
        self.assertNotIn("warnings", rows[3])

    def test_a_number_twice_in_the_list_is_created_with_warnings(self) -> None:
        response = self.admin.post(
            f"{API}/material-models/{self.shure.pk}/items",
            {"count": 2, "serial_numbers": ["TWIN", "twin"]},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual([len(row.get("warnings", [])) for row in response.data], [1, 1])
        self.assertIn("beim selben Modell", response.data[1]["warnings"][0])

    def test_a_purchase_names_the_clashes_without_the_items_warning_each_other(self) -> None:
        response = self.admin.post(
            f"{API}/purchases",
            {
                "positions": [
                    {"material_model": self.shure.pk, "count": 2, "serial_numbers": ["4711", "FRESH"]},
                    {"material_model": self.sennheiser.pk, "count": 1, "serial_numbers": ["Fresh"]},
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        warnings = response.json()["warnings"]
        self.assertEqual(
            warnings,
            [
                "Die Seriennummer FRESH kommt in dieser Eingabe mehrfach vor.",
                "Die Seriennummer 4711 gibt es schon: Exemplar 0042 (Modell Sennheiser e835).",
            ],
        )

    def test_changing_a_number_to_a_clashing_one_warns(self) -> None:
        item = make_item(self.shure, 7, serial_number="OWN")
        response = self.admin.patch(f"{API}/material-items/{item.pk}", {"serial_number": "4711"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn("Exemplar 0042", response.data["warnings"][0])

    def test_a_duplicate_that_was_there_before_is_not_warned_about_at_every_change(self) -> None:
        """(duplicate serial numbers; MAT-084) as in the browser: only a changed number is asked about."""
        item = make_item(self.shure, 7, serial_number="4711")  # a duplicate of 0042 already
        other = self.admin.patch(f"{API}/material-items/{item.pk}", {"note": "Neue Kapsel"}, format="json")
        self.assertEqual(other.status_code, 200, other.data)
        self.assertNotIn("warnings", other.data)
        same = self.admin.patch(f"{API}/material-items/{item.pk}", {"serial_number": " 4711 "}, format="json")
        self.assertNotIn("warnings", same.data)
        changed = self.admin.patch(f"{API}/material-items/{item.pk}", {"serial_number": "OLD"}, format="json")
        self.assertIn("verkauft", changed.data["warnings"][0])


class ImportWarningTests(RentalarsTestCase):
    """The import preview warns per row; a row for the same item with its own number does not."""

    HEAD = "ID;Artikelname;Kategorie;Seriennummer"

    def run_import(self, text: str, *, dry_run: bool = True) -> Any:
        data = read_table(io.BytesIO(text.encode("utf-8")), "liste.csv")
        return import_material(data, resolve_mapping(data.headers, {}), dry_run=dry_run, rights=ALL_RIGHTS)

    def test_a_new_or_changed_number_that_another_item_has(self) -> None:
        make_item(make_model("Altes Modell", category_code="T"), 900, serial_number="SN-OLD", status=ItemStatus.RETIRED)
        report = self.run_import(
            f"{self.HEAD}\n1;Funkempfänger;Ton;SN-1\n2;Funkempfänger;Ton;sn-1\n3;Funkempfänger;Ton;SN-OLD\n"
            "4;Funkempfänger;Ton;SN-4\n"
        )
        self.assertTrue(report.ok, [str(issue) for issue in report.errors])
        found = {issue.row: issue.message for issue in report.warnings if "Seriennummer" in issue.message}
        self.assertEqual(sorted(found), [2, 3, 4])  # rows of the file: header is row 1
        self.assertIn("gibt es schon beim selben Modell: Exemplar 0002", found[2])
        self.assertIn("Exemplar 0001", found[3])
        self.assertIn("(Modell Altes Modell, ausgemustert)", found[4])
        self.assertEqual(MaterialItem.objects.count(), 1)  # a dry run

    def test_the_same_list_again_warns_about_nothing(self) -> None:
        text = f"{self.HEAD}\n1;Funkempfänger;Ton;SN-1\n2;Funkempfänger;Ton;SN-2\n"
        self.run_import(text, dry_run=False)
        report = self.run_import(text)
        self.assertEqual([issue for issue in report.warnings if "Seriennummer" in issue.message], [])

    def test_swapping_two_numbers_is_no_clash(self) -> None:
        self.run_import(f"{self.HEAD}\n1;Funkempfänger;Ton;A\n2;Funkempfänger;Ton;B\n", dry_run=False)
        report = self.run_import(f"{self.HEAD}\n1;Funkempfänger;Ton;B\n2;Funkempfänger;Ton;A\n")
        self.assertEqual([issue for issue in report.warnings if "Seriennummer" in issue.message], [])


# --- 2. Notes at the job functions ---------------------------------------------------------------------------


class JobFunctionNoteTests(UiTestCase):
    """Personnel → Job functions: the guide values are the hourly wage; the customer's price is on the product."""

    def setUp(self) -> None:
        super().setUp()
        self.function = job_function("Tontechnik", price="85.00", guide="42.00")
        self.product = self.function.service_product

    def test_the_list_says_where_customer_prices_are_changed(self) -> None:
        page = self.assert_ok(self.client.get(reverse("personnel:job_function_list")))
        self.assertIn("Die Preise, die Kunden in Rechnung gestellt werden, änderst du unter Materialverwaltung", page)
        self.assertIn(f'<a href="{reverse("products:list")}?kind=service">Produkte</a>', page)
        self.assertIn("Stundenlohn der eingeplanten Crew – nicht der Preis, den der Kunde zahlt.", page)

    def test_the_form_links_to_the_product_of_the_function(self) -> None:
        page = self.assert_ok(self.client.get(reverse("personnel:job_function_edit", args=[self.function.pk])))
        self.assertIn("änderst du unter Materialverwaltung → Produkte (Produkt der Funktion: ", page)
        self.assertIn(f'<a href="{reverse("products:detail", args=[self.product.pk])}">', page)
        self.assertIn("Stundenlohn der eingeplanten Crew (interner Kostensatz) – nicht der Preis für den Kunden.", page)
        self.assertIn("Interne Kosten je Tag der eingeplanten Crew – nicht der Preis für den Kunden.", page)

    def test_a_new_function_has_the_note_without_a_product_link(self) -> None:
        page = self.assert_ok(self.client.get(reverse("personnel:job_function_create")))
        self.assertIn("änderst du unter Materialverwaltung → Produkte – jede Funktion hat dort ihr", page)
        self.assertNotIn("Produkt der Funktion", page)

    def test_no_link_for_somebody_who_may_not_read_products(self) -> None:
        Role.objects.create(name="Personalwesen", module_levels={"personnel": 2})
        staff = self.browser_for("pia", "Personalwesen")
        for url in (
            reverse("personnel:job_function_list"),
            reverse("personnel:job_function_edit", args=[self.function.pk]),
        ):
            with self.subTest(url=url):
                page = self.assert_ok(staff.get(url))
                self.assertIn("änderst du unter Materialverwaltung → Produkte", page)  # the sentence stays
                self.assertNotIn(reverse("products:list"), page)
                self.assertNotIn(reverse("products:detail", args=[self.product.pk]), page)

    def test_the_guide_values_stay_hidden_without_the_personnel_costs_right(self) -> None:
        Role.objects.create(name="Personalwesen", module_levels={"personnel": 2})
        page = self.assert_ok(
            self.browser_for("pia", "Personalwesen").get(
                reverse("personnel:job_function_edit", args=[self.function.pk])
            )
        )
        self.assertNotIn("Richtwert für interne Kosten", page)
        self.assertNotIn("Stundenlohn der eingeplanten Crew (interner Kostensatz)", page)

    def test_the_person_page_says_the_rates_are_the_hourly_wage(self) -> None:
        person = make_person("Erika Muster")
        page = self.assert_ok(self.client.get(reverse("personnel:person_detail", args=[person.pk])))
        self.assertIn(
            "Die Sätze sind der Stundenlohn der Person – interne Kosten, nicht der Preis für den Kunden.", page
        )


# --- 3. Year dropdowns ---------------------------------------------------------------------------------------


class YearChoicesTests(UiTestCase):
    """The clock stands at 1 March 2027: the dropdowns run up to 2030, the past as before."""

    def test_the_helper(self) -> None:
        self.assertEqual(year_choices(), [2030, 2029, 2028, 2027, 2026, 2025, 2024, 2023, 2022])
        self.assertEqual(year_choices(past=1, ahead=0), [2027, 2026])
        self.assertEqual(year_choices(past=0, ahead=1, selected=2040), [2040, 2028, 2027])  # a chosen year stays
        self.assertEqual(year_choices(selected=2027), year_choices())

    def years_of(self, page: str) -> list[int]:
        select = re.search(r'<select id="f-year".*?</select>', page, re.S)
        assert select
        return [int(year) for year in re.findall(r'<option value="(\d{4})"', select.group(0))]

    def test_the_profitability_report_offers_three_years_ahead(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:report")))
        self.assertEqual(self.years_of(page), [2030, 2029, 2028, 2027, 2026, 2025, 2024, 2023, 2022])
        self.assertIn('<option value="2027" selected>2027</option>', page)  # the current year stays the default

    def test_a_year_from_the_address_is_chosen(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:report") + "?year=2029"))
        self.assertIn('<option value="2029" selected>2029</option>', page)
        self.assertNotIn('<option value="2027" selected>', page)

    def test_the_material_report_offers_the_same_years(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:report_material")))
        self.assertEqual(self.years_of(page), [2030, 2029, 2028, 2027, 2026, 2025, 2024, 2023, 2022])
        self.assertIn('<option value="">Gesamte Zeit</option>', page)
        chosen = self.assert_ok(self.client.get(reverse("projects:report_material") + "?year=2030"))
        self.assertIn('<option value="2030" selected>2030</option>', chosen)

    def test_a_digit_that_is_not_a_number_is_ignored(self) -> None:
        """ "²".isdigit() is true but int("²") fails: ?year=² was a 500."""
        for name in ("projects:report", "projects:report_material"):
            page = self.assert_ok(self.client.get(reverse(name), {"year": "²"}))
            self.assertNotIn('<option value="2028" selected>', page)
        page = self.assert_ok(self.client.get(reverse("projects:report"), {"year": "²", "from": "²", "to": "²"}))
        self.assertIn('<option value="2027" selected>2027</option>', page)


# --- 4. The way back follows the browser (server side) ---------------------------------------------------------


class TrailFollowsTheReferer(UiTestCase):
    """The browser brings a page back from its memory without asking us; the click from it says where the user is."""

    def setUp(self) -> None:
        super().setUp()
        self.first = make_product("K-005", "XLR-Kabel 5 m")
        self.second = make_product("K-006", "XLR-Kabel 10 m")
        self.listing = reverse("products:list")
        self.page_a = reverse("products:detail", args=[self.first.pk])
        self.page_b = reverse("products:detail", args=[self.second.pk])

    def back_of(self, url: str, client: Client | None = None, **headers: str) -> str | None:
        page = (client or self.client).get(url, **headers).content.decode()
        found = re.search(r'<a class="back-link no-print" href="([^"]+)"', page)
        return html.unescape(found.group(1)) if found else None

    def test_without_the_referer_the_old_stale_trail_would_lead_to_the_first_product(self) -> None:
        self.back_of(self.listing)
        self.assertEqual(self.back_of(self.page_a), self.listing)
        # The browser back button shows the list from its memory: no request. The click on product B:
        self.assertEqual(self.back_of(self.page_b), self.page_a)  # no Referer (a bookmark, a mail): as before

    def test_the_click_from_the_list_after_the_browsers_back_button(self) -> None:
        self.back_of(self.listing)
        self.back_of(self.page_a)
        self.assertEqual(self.back_of(self.page_b, HTTP_REFERER=f"http://testserver{self.listing}"), self.listing)
        # ... and the trail really is "list, B" now: from B the way back is the list, from the list nothing.
        self.assertEqual(self.back_of(self.page_a, HTTP_REFERER=f"http://testserver{self.listing}"), self.listing)

    def test_a_list_with_its_filter_is_the_place_to_return_to(self) -> None:
        filtered = self.listing + "?q=XLR&page=2"
        self.back_of(filtered)
        self.back_of(self.page_a)
        self.assertEqual(self.back_of(self.page_b, HTTP_REFERER=f"http://testserver{filtered}"), filtered)

    def test_a_link_from_a_page_that_is_the_end_of_the_trail_changes_nothing(self) -> None:
        self.back_of(self.listing)
        self.back_of(self.page_a)
        self.assertEqual(self.back_of(self.page_b, HTTP_REFERER=f"http://testserver{self.page_a}"), self.page_a)

    def test_a_start_page_not_on_the_trail_begins_it_anew(self) -> None:
        self.back_of(reverse("material:model_list"))
        self.back_of(self.page_a)
        # The user is on the product list (restored by the browser); the cookie knows only the models.
        self.assertEqual(self.back_of(self.page_b, HTTP_REFERER=f"http://testserver{self.listing}"), self.listing)

    def test_other_referers_change_nothing(self) -> None:
        self.back_of(self.listing)
        self.back_of(self.page_a)
        for referer in ("https://elsewhere.example/products/", "/does/not/exist/", "/api/v1/products", ""):
            with self.subTest(referer=referer):
                self.assertEqual(self.back_of(self.page_b, HTTP_REFERER=referer), self.page_a)

    def test_an_encoded_referer_is_found_on_the_trail(self) -> None:
        """(back in the browser; UIX-055) the path of the Referer is compared decoded, like request.path."""
        self.back_of(self.listing)
        self.back_of(self.page_a)
        encoded = "http://testserver/%70roducts/?q=1"  # "/products/"
        self.assertEqual(self.back_of(self.page_b, HTTP_REFERER=encoded), f"{self.listing}?q=1")
        self.assertEqual(
            self.back_of(self.page_a, HTTP_REFERER=f"http://testserver{self.listing}?q=1"), f"{self.listing}?q=1"
        )

    def test_a_long_referer_does_not_fill_the_cookie(self) -> None:
        self.back_of(self.listing)
        self.back_of(self.page_a)
        long_query = "?q=" + "x" * 2000
        # Too long for the cookie with the query: the address is kept without it.
        referer = trail.referring_page(
            self.client.get(self.page_b, HTTP_REFERER=f"http://testserver{self.listing}{long_query}").wsgi_request
        )
        self.assertEqual(referer[1], self.listing)
        # Too long without it: no page at all.
        too_long = "http://testserver/" + "p" * 400 + "/"
        self.assertIsNone(trail.referring_page(self.client.get(self.page_b, HTTP_REFERER=too_long).wsgi_request))
        self.assertEqual(self.back_of(self.page_b, HTTP_REFERER=too_long), self.listing)  # the trail is as it was
        # Eight entries stay small.
        self.client.get(self.page_b, HTTP_REFERER=f"http://testserver{self.listing}{long_query}")
        self.assertLess(len(self.client.cookies["rentalars_trail"].value), 4096)

    def test_the_page_a_click_comes_from_is_resolved_once(self) -> None:
        trail._resolve.cache_clear()
        for _ in range(3):
            self.back_of(self.page_b, HTTP_REFERER=f"http://testserver{self.listing}")
        info = trail._resolve.cache_info()
        self.assertEqual((info.misses, info.hits), (1, 2))

    def test_the_functions(self) -> None:
        self.assertEqual(trail.follow_referer([("a", "/a/")], None), [("a", "/a/")])
        self.assertIsNone(trail.referring_page(self.client.get("/").wsgi_request))
