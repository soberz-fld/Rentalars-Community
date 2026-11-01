# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages, area "tables": every shown column can be chosen under "Gruppieren nach" (UIX-044).

Every list page offers its shown columns in their order – not the buttons – and groups by each of them; a list too
long to be grouped in Python says so; the lists of the master data group by every shown column too.
"""

from __future__ import annotations

import re
from dataclasses import replace
from unittest import mock

from django.contrib import admin
from django.urls import reverse

from rentalars.core.admin_tables import TableAdminMixin
from rentalars.core.tables import REGISTRY
from rentalars.masterdata.models import Category, StorageLocation
from rentalars.projects import service_cases
from tests.helpers import at, make_project, record_time
from tests.ui import test_082_cleanup_pages as cleanup
from tests.ui.base import UiTestCase
from tests.ui.test_080_times_pages import TimesPageCase
from tests.ui.test_081_ui_pages import groups_of

#: A "Gruppieren nach" of a page: the id names the table, the name is the parameter (``group``, ``runs_group`` …).
GROUP_SELECT = re.compile(r'<select id="group-([\w-]+)" name="(\w*group)"[^>]*>(.*?)</select>', re.S)
OPTION = re.compile(r'<option value="([\w-]+)"')


def every_column() -> dict[str, str]:
    """Every column of every table of a page – also of a second table with a prefix (``runs_cols`` …)."""
    return {f"{prefix}cols": "all" for prefix in {"", *(table.prefix for table in REGISTRY.values())}}


def group_selects(page: str) -> list[tuple[str, str, list[str]]]:
    """Each "Gruppieren nach" of a page: the table, the parameter and the offered columns in their order."""
    return [(table, name, OPTION.findall(options)) for table, name, options in GROUP_SELECT.findall(page)]


class EveryColumnGroupsTests(cleanup.EveryHeadingSortsTests):
    """UIX-044: with every column shown, each one but buttons is offered in its order and groups the list."""

    # Only the set-up (rows in every list) is shared.
    test_every_column_sorts_both_ways = None  # type: ignore[assignment]
    test_csv_sorted_by_a_computed_column = None  # type: ignore[assignment]

    def test_every_shown_column_is_offered_and_groups(self) -> None:
        for name in self.PAGES:
            if name in self.WITHOUT_ROWS_HERE:
                continue
            page = self.assert_ok(self.client.get(reverse(name), every_column()))
            selects = group_selects(page)
            with self.subTest(page=name):
                self.assertTrue(selects)
            for table_key, parameter, offered in selects:
                table = REGISTRY[table_key]
                expected = [column.key for column in table.columns if column.groupable]
                with self.subTest(page=name, table=table_key):
                    # Every column the user may see is shown with cols=all – and offered in the order of the table.
                    self.assertEqual(offered, [key for key in expected if key in offered])
                    shown = set(cleanup.CHOOSER_COLUMN.findall(page))
                    self.assertEqual(set(offered), {key for key in expected if key in shown})
                for key in offered:
                    with self.subTest(page=name, group=key):
                        text = self.assert_ok(self.client.get(reverse(name), {**every_column(), parameter: key}))
                        self.assertIn(f'<option value="{key}" selected>', text)
                        if table_key in ("automation_runs",):
                            continue  # no runs in this set-up: the table is empty
                        self.assertTrue(groups_of(text), f"{name} grouped by {key}")

    def test_the_choice_follows_the_shown_columns(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:list"), {"cols": "status,name"}))
        [(_table, _parameter, offered)] = group_selects(page)
        self.assertEqual(offered, ["number", "name", "status"])

    def test_a_column_switched_off_stays_chosen(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:list"), {"cols": "name", "group": "status"}))
        [(_table, _parameter, offered)] = group_selects(page)
        self.assertEqual(offered, ["number", "name", "status"])
        self.assertTrue(groups_of(page))


class PythonGroupPageTests(UiTestCase):
    """UIX-044: a computed column groups the list in Python; a list too long says so and stays ungrouped."""

    def setUp(self) -> None:
        super().setUp()
        make_project("Stadtfest", start=at(10), end=at(12))
        make_project("Messe", start=at(10), end=at(12))
        make_project("Kongress", start=at(10), end=at(14))
        self.url = reverse("projects:list")

    def test_grouped_by_the_rental_days(self) -> None:
        page = self.assert_ok(self.client.get(self.url, {"cols": "number,rental_days", "group": "rental_days"}))
        counts = sorted(int(re.search(r"(\d+) Eintr", heading).group(1)) for heading in groups_of(page))
        self.assertEqual(counts, [1, 2])

    def test_a_list_too_long_says_so(self) -> None:
        with mock.patch("rentalars.core.tables.PYTHON_SORT_MAX_ROWS", 2):
            page = self.assert_ok(self.client.get(self.url, {"cols": "number,rental_days", "group": "rental_days"}))
        self.assertIn("Zum Gruppieren nach „Miettage“ darf die Liste höchstens 2 Zeilen haben", page)
        self.assertEqual(groups_of(page), [])

    def test_a_field_groups_however_long_the_list(self) -> None:
        with mock.patch("rentalars.core.tables.PYTHON_SORT_MAX_ROWS", 2):
            page = self.assert_ok(self.client.get(self.url, {"cols": "number,end", "group": "end"}))
        self.assertNotIn("Zum Gruppieren", page)
        self.assertEqual(len(groups_of(page)), 2)  # two days

    def test_the_inquiries_say_so_too(self) -> None:
        from rentalars.mail.models import UnknownTagMail

        for number, subject in enumerate(("Anfrage Bühne", "Anfrage Licht", "Anfrage Ton")):
            UnknownTagMail.objects.create(
                message_key=f"{number:064d}", subject=subject, sender="kunde@example.de", tag=""
            )
        url = reverse("mail:unknown_list")
        with mock.patch("rentalars.core.tables.PYTHON_SORT_MAX_ROWS", 2):
            page = self.assert_ok(self.client.get(url, {"group": "subject"}))
        self.assertEqual(len(groups_of(page)), 3)
        with mock.patch("rentalars.core.tables.PYTHON_SORT_MAX_ROWS", 2):
            # No column of this list groups in Python any more; the notice is there for one that would.
            table = REGISTRY["mail_inquiries"]
            in_python = [replace(column, group=None) if column.key == "subject" else column for column in table.columns]
            with mock.patch.object(table, "columns", in_python):
                page = self.assert_ok(self.client.get(url, {"group": "subject"}))
        self.assertIn("Zum Gruppieren nach „Betreff“", page)


class TimeTablesGroupTests(TimesPageCase):
    """UIX-044: the entries of the hours report group by each column; approving keeps its groups by project."""

    def setUp(self) -> None:
        super().setUp()
        record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 12), approve=True)
        record_time(self.anna, self.project, self.sound, at(11, 9), at(11, 17), submit=True)

    def test_every_column_of_the_entries(self) -> None:
        url = reverse("timetracking:report")
        page = self.assert_ok(self.client.get(url, {"since": "2027-03-01", "entries_cols": "all"}))
        [(table, parameter, offered)] = group_selects(page)
        self.assertEqual(table, "hours_report_entries")
        self.assertIn("time", offered)
        self.assertIn("hours", offered)
        self.assertNotIn("actions", offered)
        for key in offered:
            with self.subTest(group=key):
                text = self.assert_ok(
                    self.client.get(url, {"since": "2027-03-01", "entries_cols": "all", parameter: key})
                )
                self.assertTrue(groups_of(text))

    def test_approving_offers_no_grouping(self) -> None:
        page = self.assert_ok(self.client.get(reverse("timetracking:approval"), {"group": "person"}))
        self.assertNotIn("Gruppieren nach", page)
        self.assertEqual(groups_of(page), [])


class MasterDataGroupPageTests(UiTestCase):
    """UIX-044: the lists of the master data offer every shown column under "Gruppieren nach"."""

    def setUp(self) -> None:
        super().setUp()
        hall = StorageLocation.objects.create(name="Halle")
        StorageLocation.objects.create(name="Regal A", parent=hall)
        Category.objects.create(name="Testkategorie", code="Q")

    def test_every_list_groups_by_each_shown_column(self) -> None:
        for model, model_admin in admin.site._registry.items():
            if not isinstance(model_admin, TableAdminMixin) or not model._default_manager.exists():
                continue
            url = reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_changelist")
            page = self.assert_ok(self.client.get(url))
            select = page.split('<select id="group-admin" name="group">', 1)[1].split("</select>", 1)[0]
            offered = OPTION.findall(select)
            columns = re.findall(r'name="cols" value="(\w+)"', page)
            with self.subTest(model=model._meta.label):
                self.assertEqual(offered[: len(columns)], columns)
            for key in offered:
                with self.subTest(model=model._meta.label, group=key):
                    self.assertTrue(groups_of(self.assert_ok(self.client.get(url, {"group": key}))))

    def test_the_path_of_storage_locations(self) -> None:
        url = reverse("admin:masterdata_storagelocation_changelist")
        page = self.assert_ok(self.client.get(url, {"group": "path"}))
        headings = groups_of(page)
        self.assertIn("Halle > Regal A 1 Eintrag", [heading.replace("&gt;", ">") for heading in headings])


class ServiceCaseGroupTests(UiTestCase):
    """UIX-044 in Projekte → Servicefälle: the subject and the mails group too."""

    def test_by_subject_and_by_mails(self) -> None:
        service_cases.create_case(name="Beamer defekt")
        service_cases.create_case(name="Beamer defekt")
        service_cases.create_case(name="Kabel fehlt")
        url = reverse("projects:cases")
        headings = groups_of(self.assert_ok(self.client.get(url, {"group": "subject"})))
        self.assertEqual(sorted(headings), ["Beamer defekt 2 Einträge", "Kabel fehlt 1 Eintrag"])
        self.assertEqual(len(groups_of(self.assert_ok(self.client.get(url, {"group": "mails"})))), 1)
