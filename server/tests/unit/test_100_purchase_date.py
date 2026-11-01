# SPDX-License-Identifier: GPL-3.0-or-later
"""A purchase date with an unknown day or month ("00.00.2015"). (MAT-088)

The requirement: a purchase date of 00.00.2015 is accepted (day and month 0).

Of an old item people know the year at most. ``MaterialItem.purchase_date`` stays a date – the first day of the period
that is known – and ``MaterialItem.purchase_date_precision`` (``day``, ``month``, ``year``) says how much of it is known
(``material.partial_dates``). Tested here: reading and showing the dates, the model, the forms (German and ISO input),
the lists and the detail page, the import and its export (round trip), the API and the update (migration).
"""

from __future__ import annotations

import csv
import datetime
import io
from typing import Any

from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import translation

from rentalars.accounts.rights import Rights
from rentalars.core import import_exports, imports
from rentalars.core.tabular import read_table, resolve_mapping
from rentalars.material import audits, partial_dates
from rentalars.material.models import MaterialItem
from tests.api.base import API, ApiTestCase
from tests.helpers import RentalarsTestCase, make_item, make_items, make_model, make_user
from tests.ui.base import UiTestCase, form_data

PD = partial_dates.PartialDate
DAY, MONTH, YEAR = partial_dates.DAY, partial_dates.MONTH, partial_dates.YEAR


class ParsingTests(RentalarsTestCase):
    """What can be typed, and what it means."""

    def test_the_forms_that_are_read(self) -> None:
        cases = {
            "12.05.2015": (datetime.date(2015, 5, 12), DAY),
            "12/05/2015": (datetime.date(2015, 5, 12), DAY),
            "2015-05-12": (datetime.date(2015, 5, 12), DAY),
            "1.5.2015": (datetime.date(2015, 5, 1), DAY),  # a complete date stays one, also on the first of the month
            "00.05.2015": (datetime.date(2015, 5, 1), MONTH),
            "0.5.2015": (datetime.date(2015, 5, 1), MONTH),
            "05.2015": (datetime.date(2015, 5, 1), MONTH),
            "2015-05-00": (datetime.date(2015, 5, 1), MONTH),
            "2015-05": (datetime.date(2015, 5, 1), MONTH),
            "00.00.2015": (datetime.date(2015, 1, 1), YEAR),
            "2015-00-00": (datetime.date(2015, 1, 1), YEAR),
            "2015": (datetime.date(2015, 1, 1), YEAR),
            "  00.00.2015 ": (datetime.date(2015, 1, 1), YEAR),
        }
        for text, (date, precision) in cases.items():
            with self.subTest(text):
                parsed = partial_dates.parse(text)
                self.assertEqual((parsed.date, parsed.precision), (date, precision))

    def test_what_is_refused(self) -> None:
        for text in ("", "31.02.2015", "12.13.2015", "00.13.2015", "12.00.2015", "2015-00-12", "15", "215", "20150",
                     "1850", "morgen", "12.05.", "2015-02-30"):  # fmt: skip
            # (R3-10) "12.05.15" is read again as 2015 (the date field before took it): see test_100_fix_r3.
            with self.subTest(text), self.assertRaises(ValueError):
                partial_dates.parse(text)

    def test_the_text_is_shown_as_far_as_it_is_known(self) -> None:
        self.assertEqual(str(PD(datetime.date(2015, 5, 12))), "12.05.2015")
        self.assertEqual(str(PD(datetime.date(2015, 5, 12), MONTH)), "05.2015")
        self.assertEqual(str(PD(datetime.date(2015, 5, 12), YEAR)), "2015")
        with translation.override("en"):
            self.assertEqual(str(PD(datetime.date(2015, 5, 12))), "12/05/2015")
            self.assertEqual(str(PD(datetime.date(2015, 5, 12), MONTH)), "05/2015")
            self.assertEqual(str(PD(datetime.date(2015, 5, 12), YEAR)), "2015")

    def test_the_iso_text_has_zeros_for_what_is_unknown(self) -> None:
        self.assertEqual(PD(datetime.date(2015, 5, 12)).iso, "2015-05-12")
        self.assertEqual(PD(datetime.date(2015, 5, 12), MONTH).iso, "2015-05-00")
        self.assertEqual(PD(datetime.date(2015, 5, 12), YEAR).iso, "2015-00-00")
        self.assertEqual(partial_dates.iso_text(None), "")

    def test_a_partial_date_is_the_first_day_of_its_period(self) -> None:
        """The depreciation (and every sort) can take ``purchase_date`` as it is."""
        self.assertEqual(PD(datetime.date(2015, 5, 12), MONTH).date, datetime.date(2015, 5, 1))
        self.assertEqual(PD(datetime.date(2015, 5, 12), YEAR).date, datetime.date(2015, 1, 1))
        self.assertEqual(partial_dates.coarser(DAY, YEAR), YEAR)
        self.assertEqual(partial_dates.coarser(MONTH, DAY), MONTH)

    def test_the_field_reads_and_shows_the_date_the_way_it_was_typed(self) -> None:
        field = partial_dates.PartialDateField(required=False)
        self.assertIsNone(field.clean(""))
        self.assertEqual(field.clean("00.00.2015"), PD(datetime.date(2015, 1, 1), YEAR))
        self.assertEqual(field.prepare_value(PD(datetime.date(2015, 5, 1), MONTH)), "05.2015")
        self.assertEqual(field.prepare_value(datetime.date(2015, 5, 12)), "12.05.2015")
        with self.assertRaises(ValidationError) as caught:
            field.clean("31.02.2015")
        self.assertIn("00.00.2015", caught.exception.messages[0])


class ModelTests(RentalarsTestCase):
    """The item keeps the date and how much of it is known."""

    def setUp(self) -> None:
        super().setUp()
        self.model = make_model("Cordial CPM 5 FM", category_code="K")

    def test_an_item_without_a_date_is_day_precise(self) -> None:
        item = make_item(self.model, 1)
        self.assertEqual((item.purchase_date, item.purchase_date_precision), (None, DAY))
        self.assertEqual((item.purchase_date_text, item.purchase_date_iso), ("", ""))

    def test_the_date_is_normalised_to_the_first_day_of_the_period(self) -> None:
        item = make_item(self.model, 1, purchase_date=datetime.date(2015, 5, 12), purchase_date_precision=MONTH)
        item.refresh_from_db()
        self.assertEqual((item.purchase_date, item.purchase_date_precision), (datetime.date(2015, 5, 1), MONTH))
        year = make_item(self.model, 2, purchase_date=datetime.date(2015, 5, 12), purchase_date_precision=YEAR)
        self.assertEqual(year.purchase_date, datetime.date(2015, 1, 1))
        self.assertEqual((year.purchase_date_text, year.purchase_date_iso), ("2015", "2015-00-00"))

    def test_no_date_resets_the_precision(self) -> None:
        item = make_item(self.model, 1, purchase_date=datetime.date(2015, 1, 1), purchase_date_precision=YEAR)
        item.purchase_date = None
        item.full_clean()
        item.save()
        item.refresh_from_db()
        self.assertEqual((item.purchase_date, item.purchase_date_precision), (None, DAY))

    def test_a_precision_nobody_knows_counts_as_day(self) -> None:
        self.assertEqual(
            partial_dates.normalised(datetime.date(2015, 5, 12), "decade"), (datetime.date(2015, 5, 12), DAY)
        )
        item = MaterialItem(material_model=self.model, inventory_number=3, purchase_date=datetime.date(2015, 5, 12))
        item.purchase_date_precision = "decade"
        item.clean()
        self.assertEqual(item.purchase_date_precision, DAY)

    def test_the_sheet_of_master_data_shows_it(self) -> None:
        """The PDF of an item (audit report) names the date as far as it is known."""
        item = make_item(self.model, 1, purchase_date=datetime.date(2015, 1, 1), purchase_date_precision=YEAR)
        rows = {str(row.label): row.value for row in audits.master_data(item, Rights.everything())}
        self.assertEqual(rows["Rechnungsdatum"], "2015")


class FormTests(UiTestCase):
    """The forms for new items and for one item: German and ISO input; what is shown comes back as typed."""

    def setUp(self) -> None:
        super().setUp()
        self.model = make_model("Cordial CPM 5 FM", category_code="K")

    def create(self, text: str, **changes: Any) -> Any:
        url = reverse("material:item_create", args=[self.model.pk])
        data = form_data(self.client.get(url), count=1, purchase_date=text, new_supplier=None, **changes)
        return self.client.post(url, data, follow=True)

    def test_new_items_take_a_year_a_month_or_a_day(self) -> None:
        for text, expected in {
            "00.00.2015": (datetime.date(2015, 1, 1), YEAR),
            "00.05.2015": (datetime.date(2015, 5, 1), MONTH),
            "12.05.2015": (datetime.date(2015, 5, 12), DAY),
            "2015-05-12": (datetime.date(2015, 5, 12), DAY),
            "2015-00-00": (datetime.date(2015, 1, 1), YEAR),
        }.items():
            with self.subTest(text):
                MaterialItem.objects.all().delete()
                response = self.create(text)
                self.assertEqual(response.status_code, 200)
                item = MaterialItem.objects.get()
                self.assertEqual((item.purchase_date, item.purchase_date_precision), expected)

    def test_a_date_that_does_not_exist_is_refused_with_a_hint(self) -> None:
        response = self.create("31.02.2015")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MaterialItem.objects.count(), 0)
        self.assertIn("00.00.2015", response.content.decode())

    def test_the_form_of_an_item_shows_what_is_known_and_keeps_it(self) -> None:
        item = make_item(self.model, 1, purchase_date=datetime.date(2015, 1, 1), purchase_date_precision=YEAR)
        url = reverse("material:item_edit", args=[item.pk])
        data = form_data(self.client.get(url), note="geändert")
        self.assertEqual(data["purchase_date"], "2015")  # not "01.01.2015"
        self.client.post(url, data)
        item.refresh_from_db()
        self.assertEqual(
            (item.note, item.purchase_date, item.purchase_date_precision), ("geändert", datetime.date(2015, 1, 1), YEAR)
        )

    def test_the_form_of_an_item_can_make_a_date_complete_or_remove_it(self) -> None:
        item = make_item(self.model, 1, purchase_date=datetime.date(2015, 5, 1), purchase_date_precision=MONTH)
        url = reverse("material:item_edit", args=[item.pk])
        self.client.post(url, form_data(self.client.get(url), purchase_date="17.05.2015"))
        item.refresh_from_db()
        self.assertEqual((item.purchase_date, item.purchase_date_precision), (datetime.date(2015, 5, 17), DAY))
        self.client.post(url, form_data(self.client.get(url), purchase_date=""))
        item.refresh_from_db()
        self.assertEqual((item.purchase_date, item.purchase_date_precision), (None, DAY))

    def test_a_complete_date_on_the_first_of_a_month_stays_complete(self) -> None:
        item = make_item(self.model, 1, purchase_date=datetime.date(2015, 5, 1))
        url = reverse("material:item_edit", args=[item.pk])
        data = form_data(self.client.get(url))
        self.assertEqual(data["purchase_date"], "01.05.2015")
        self.client.post(url, data)
        item.refresh_from_db()
        self.assertEqual(item.purchase_date_precision, DAY)

    def test_the_copy_of_an_item_starts_with_its_date(self) -> None:
        item = make_item(self.model, 1, purchase_date=datetime.date(2015, 1, 1), purchase_date_precision=YEAR)
        page = self.client.get(
            reverse("material:item_create", args=[self.model.pk]), {"copy": item.pk}
        ).content.decode()
        self.assertIn('name="purchase_date"', page)
        self.assertIn('value="2015"', page)


class PagesTests(UiTestCase):
    """The detail page, the model page and the lists show the date as far as it is known and sort it sensibly."""

    def setUp(self) -> None:
        super().setUp()
        self.model = make_model("Cordial CPM 5 FM", category_code="K")
        self.full = make_item(self.model, 1, purchase_date=datetime.date(2015, 1, 1))  # a day: 1 January 2015
        self.year = make_item(self.model, 2, purchase_date=datetime.date(2015, 6, 9), purchase_date_precision=YEAR)
        self.month = make_item(self.model, 3, purchase_date=datetime.date(2015, 3, 20), purchase_date_precision=MONTH)
        self.later = make_item(self.model, 4, purchase_date=datetime.date(2016, 2, 29))
        self.none = make_item(self.model, 5)

    def test_the_detail_page(self) -> None:
        for item, text in ((self.year, "2015"), (self.month, "03.2015"), (self.full, "01.01.2015")):
            with self.subTest(text):
                page = self.assert_ok(self.client.get(reverse("material:item_detail", args=[item.pk])))
                dd = page[page.index("Rechnungsdatum") :]
                self.assertTrue(dd[: dd.index("</dd>")].endswith(f"<dd>{text}"), dd[:120])

    def test_the_model_page(self) -> None:
        page = self.assert_ok(self.client.get(reverse("material:model_detail", args=[self.model.pk])))
        self.assertIn('data-label="Gekauft">2015', page)
        self.assertIn('data-label="Gekauft">03.2015', page)

    def rows(self, sort: str) -> list[list[str]]:
        response = self.client.get(reverse("material:item_list"), {"format": "csv", "cols": "all", "sort": sort})
        self.assertEqual(response.status_code, 200)
        text = b"".join(response.streaming_content).decode() if response.streaming else response.content.decode()
        return list(csv.reader(io.StringIO(text.lstrip("﻿")), delimiter=";"))

    def test_the_csv_of_the_list_has_the_text_as_far_as_it_is_known(self) -> None:
        table = self.rows("purchased")
        column = table[0].index("Rechnungsdatum")
        by_id = {row[0]: row[column] for row in table[1:]}
        self.assertEqual(by_id["0002"], "2015")
        self.assertEqual(by_id["0003"], "03.2015")
        self.assertEqual(by_id["0001"], "01.01.2015")
        self.assertEqual(by_id["0005"], "")

    def test_the_list_sorts_a_year_before_the_dated_items_of_it(self) -> None:
        """A year is the beginning of its year; a month the beginning of its month; undated items come first/last."""
        ascending = [row[0] for row in self.rows("purchased")[1:]]
        self.assertEqual([number for number in ascending if number != "0005"], ["0002", "0001", "0003", "0004"])
        descending = [row[0] for row in self.rows("-purchased")[1:]]
        self.assertEqual([number for number in descending if number != "0005"], ["0004", "0003", "0001", "0002"])

    def test_the_list_page_shows_it(self) -> None:
        page = self.assert_ok(self.client.get(reverse("material:item_list"), {"cols": "all"}))
        self.assertIn(">03.2015<", page)
        self.assertIn(">2015<", page)


class ImportExportTests(RentalarsTestCase):
    """The import takes the partial date; the export writes it back so that the round trip keeps it."""

    HEADER = "ID;Artikelname;Kategorie;Tag des Kaufs\n"

    def setUp(self) -> None:
        super().setUp()
        self.user = make_user("importer", superuser=True)
        self.kind = imports.get("material")

    def run_import(self, text: str, *, dry_run: bool = False) -> dict[str, Any]:
        table = read_table(io.BytesIO(text.encode("utf-8")), "material.csv")
        mapping = resolve_mapping(table.headers, {}, self.kind.fields)
        return imports.run(self.kind, table, mapping, dry_run=dry_run, user=self.user).as_dict()

    def csv(self, *dates: str) -> str:
        return self.HEADER + "".join(f"{index};Kabel;Kabel;{text}\n" for index, text in enumerate(dates, start=1))

    def test_the_import_takes_every_form(self) -> None:
        report = self.run_import(
            self.csv("00.00.2015", "00.05.2015", "12.05.2015", "2015-05-12", "2015", "05.2015", "")
        )
        self.assertTrue(report["ok"], report["errors"])
        found = {
            item.inventory_number: (item.purchase_date, item.purchase_date_precision)
            for item in MaterialItem.objects.all()
        }
        self.assertEqual(found[1], (datetime.date(2015, 1, 1), YEAR))
        self.assertEqual(found[2], (datetime.date(2015, 5, 1), MONTH))
        self.assertEqual(found[3], (datetime.date(2015, 5, 12), DAY))
        self.assertEqual(found[4], (datetime.date(2015, 5, 12), DAY))
        self.assertEqual(found[5], (datetime.date(2015, 1, 1), YEAR))
        self.assertEqual(found[6], (datetime.date(2015, 5, 1), MONTH))
        self.assertEqual(found[7], (None, DAY))

    def test_a_wrong_date_is_a_hint_of_its_row(self) -> None:
        """IMP-010: no error any more – the item comes in as "Fehler Import" with the cell in its note."""
        report = self.run_import(self.csv("00.00.2015", "31.02.2015"), dry_run=True)
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(
            [(issue["row"], issue["column"]) for issue in report["warnings"] if issue["row"]], [(3, "Rechnungsdatum")]
        )
        self.assertEqual(report["items_flagged"], 1)

    def test_a_spreadsheet_date_is_a_complete_date(self) -> None:
        from rentalars.material.importer import _parse_purchase_date

        self.assertEqual(_parse_purchase_date(datetime.date(2015, 1, 1)), PD(datetime.date(2015, 1, 1), DAY))
        self.assertEqual(
            _parse_purchase_date(datetime.datetime(2015, 5, 12, 0, 0)), PD(datetime.date(2015, 5, 12), DAY)
        )

    def test_a_new_import_can_make_a_year_precise_or_the_other_way(self) -> None:
        self.run_import(self.csv("00.00.2015"))
        self.run_import(self.csv("12.05.2015"))
        item = MaterialItem.objects.get(inventory_number=1)
        self.assertEqual((item.purchase_date, item.purchase_date_precision), (datetime.date(2015, 5, 12), DAY))
        report = self.run_import(self.csv("00.00.2015"))
        self.assertEqual(report["row_counts"]["changed"], 1)
        item.refresh_from_db()
        self.assertEqual((item.purchase_date, item.purchase_date_precision), (datetime.date(2015, 1, 1), YEAR))

    def test_only_the_precision_is_a_change(self) -> None:
        """ "00.00.2015" over "01.01.2015" is something new: the same first day, but less known."""
        self.run_import(self.csv("01.01.2015"))
        report = self.run_import(self.csv("00.00.2015"), dry_run=True)
        self.assertEqual(report["row_counts"]["changed"], 1)
        self.assertEqual(self.run_import(self.csv("01.01.2015"), dry_run=True)["row_counts"]["unchanged"], 1)

    def test_the_export_writes_what_the_import_reads(self) -> None:
        model = make_model("Cordial CPM 5 FM", category_code="K")
        make_item(model, 1, purchase_date=datetime.date(2015, 1, 1), purchase_date_precision=YEAR)
        make_item(model, 2, purchase_date=datetime.date(2015, 5, 1), purchase_date_precision=MONTH)
        make_item(model, 3, purchase_date=datetime.date(2015, 5, 12))
        make_item(model, 4)
        text = import_exports.text_of(import_exports.get("material"), Rights.everything())
        table = read_table(io.BytesIO(text.encode("utf-8")), "export.csv")
        column = table.headers.index("Rechnungsdatum")
        self.assertEqual([row[column] for row in table.rows], ["00.00.2015", "00.05.2015", "12.05.2015", ""])
        mapping = resolve_mapping(table.headers, {}, self.kind.fields)
        report = imports.run(self.kind, table, mapping, dry_run=True, user=self.user).as_dict()
        self.assertEqual(report["row_counts"], {"new": 0, "changed": 0, "unchanged": 4, "error": 0})


class ApiTests(ApiTestCase):
    """The API sends and delivers ISO text with zeros, and ``purchase_date_precision``."""

    def setUp(self) -> None:
        super().setUp()
        self.model = make_model("Cordial CPM 5 FM", category_code="K")

    def post(self, value: Any) -> Any:
        return self.admin.post(
            f"{API}/material-items", {"material_model": self.model.pk, "purchase_date": value}, format="json"
        )

    def test_create_with_a_year_a_month_and_a_day(self) -> None:
        for value, (date, precision), shown in (
            ("2015-00-00", (datetime.date(2015, 1, 1), YEAR), "2015-00-00"),
            ("2015-05-00", (datetime.date(2015, 5, 1), MONTH), "2015-05-00"),
            ("2015-05-12", (datetime.date(2015, 5, 12), DAY), "2015-05-12"),
            ("00.00.2015", (datetime.date(2015, 1, 1), YEAR), "2015-00-00"),
            ("2015", (datetime.date(2015, 1, 1), YEAR), "2015-00-00"),
            ("2015-05", (datetime.date(2015, 5, 1), MONTH), "2015-05-00"),
        ):
            with self.subTest(value):
                response = self.post(value)
                self.assertEqual(response.status_code, 201, response.data)
                self.assertEqual(
                    (response.data["purchase_date"], response.data["purchase_date_precision"]), (shown, precision)
                )
                item = MaterialItem.objects.get(pk=response.data["id"])
                self.assertEqual((item.purchase_date, item.purchase_date_precision), (date, precision))

    def test_a_complete_date_reads_exactly_as_before(self) -> None:
        item = make_item(self.model, 7, purchase_date=datetime.date(2023, 4, 12))
        data = self.admin.get(f"{API}/material-items/{item.pk}").data
        self.assertEqual((data["purchase_date"], data["purchase_date_precision"]), ("2023-04-12", "day"))

    def test_no_date_is_null(self) -> None:
        response = self.admin.post(f"{API}/material-items", {"material_model": self.model.pk}, format="json")
        self.assertEqual((response.data["purchase_date"], response.data["purchase_date_precision"]), (None, "day"))
        self.assertEqual(self.post(None).data["purchase_date"], None)

    def test_patch_changes_date_and_precision_and_what_was_read_can_be_sent_back(self) -> None:
        created = self.post("2015-00-00")
        url = f"{API}/material-items/{created.data['id']}"
        shown = self.admin.get(url).data["purchase_date"]
        self.assertEqual(
            self.admin.patch(url, {"purchase_date": shown}, format="json").data["purchase_date"], "2015-00-00"
        )
        month = self.admin.patch(url, {"purchase_date": "2015-05-00"}, format="json")
        self.assertEqual((month.data["purchase_date"], month.data["purchase_date_precision"]), ("2015-05-00", "month"))
        day = self.admin.patch(url, {"purchase_date": "2015-05-12"}, format="json")
        self.assertEqual((day.data["purchase_date"], day.data["purchase_date_precision"]), ("2015-05-12", "day"))
        cleared = self.admin.patch(url, {"purchase_date": None}, format="json")
        self.assertEqual((cleared.data["purchase_date"], cleared.data["purchase_date_precision"]), (None, "day"))

    def test_another_change_leaves_the_partial_date_alone(self) -> None:
        created = self.post("2015-00-00")
        url = f"{API}/material-items/{created.data['id']}"
        changed = self.admin.patch(url, {"note": "Kiste 4"}, format="json")
        self.assertEqual(
            (changed.data["purchase_date"], changed.data["purchase_date_precision"]), ("2015-00-00", "year")
        )

    def test_the_precision_cannot_be_written_alone(self) -> None:
        created = self.post("2015-05-12")
        url = f"{API}/material-items/{created.data['id']}"
        self.admin.patch(url, {"purchase_date_precision": "year"}, format="json")
        self.assertEqual(self.admin.get(url).data["purchase_date_precision"], "day")

    def test_wrong_dates_are_refused(self) -> None:
        for value in ("2015-02-30", "2015-13-00", "2015-00-12", "morgen", 2015, "215"):
            with self.subTest(value):
                self.assert_error(self.post(value), 400, "validation_error", "purchase_date")

    def test_several_items_of_a_model_at_once(self) -> None:
        response = self.admin.post(
            f"{API}/material-models/{self.model.pk}/items", {"count": 3, "purchase_date": "2015-00-00"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            {(row["purchase_date"], row["purchase_date_precision"]) for row in response.data}, {("2015-00-00", "year")}
        )
        wrong = self.admin.post(
            f"{API}/material-models/{self.model.pk}/items", {"count": 2, "purchase_date": "2015-00-12"}, format="json"
        )
        self.assert_error(wrong, 400, "validation_error", "purchase_date")

    def test_sorting_by_the_date(self) -> None:
        make_items(self.model, 1, purchase_date=datetime.date(2016, 1, 1))
        make_items(self.model, 1, purchase_date=datetime.date(2015, 6, 1), purchase_date_precision=YEAR)
        rows = self.admin.get(f"{API}/material-items", {"ordering": "purchase_date"}).data["results"]
        self.assertEqual([row["purchase_date"] for row in rows], ["2015-00-00", "2016-01-01"])

    def test_the_description_names_the_field(self) -> None:
        schema = self.admin.get(f"{API}/schema/", {"format": "json"})
        if schema.status_code == 200:
            text = schema.content.decode()
            self.assertIn("purchase_date_precision", text)


class MigrationTests(TransactionTestCase):
    """The update: old items keep their date, complete; the column can be taken away again."""

    before = [("material", "0011_built_in_quantity_100")]
    after = [("material", "0012_partial_purchase_date_100")]

    def tearDown(self) -> None:
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def migrate(self, targets: list[tuple[str, str]]) -> Any:
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def test_old_items_are_day_precise_and_the_update_can_be_reversed(self) -> None:
        model = make_model("Altes Kabel", category_code="K")
        item = make_item(model, 1, purchase_date=datetime.date(2015, 5, 12))
        old = self.migrate(self.before)
        columns = {
            column.name
            for column in connection.introspection.get_table_description(connection.cursor(), "material_materialitem")
        }
        self.assertNotIn("purchase_date_precision", columns)
        self.assertEqual(
            old.get_model("material", "MaterialItem").objects.get(pk=item.pk).purchase_date, datetime.date(2015, 5, 12)
        )
        new = self.migrate(self.after)
        found = new.get_model("material", "MaterialItem").objects.get(pk=item.pk)
        self.assertEqual((found.purchase_date, found.purchase_date_precision), (datetime.date(2015, 5, 12), "day"))
