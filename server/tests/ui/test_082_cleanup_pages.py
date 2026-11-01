# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages, area "clean-up": a failing mail shows its message (EML-024), every heading of every list sorts
(UIX-015, UIX-040), the filters say what is filtered while folded (UIX-038), English anchors (NFA-061).
"""

from __future__ import annotations

import re
from unittest import mock

from django.core.exceptions import ValidationError
from django.urls import reverse

from rentalars.customers.models import Venue
from rentalars.mail import log
from rentalars.mail.models import Direction, LogKind, LogResult
from rentalars.masterdata.models import Category, StorageLocation
from rentalars.projects.models import ProjectStatus
from tests.helpers import at, make_items, make_model, make_person, make_product, make_project, record_time
from tests.mailbox import configure_mailbox
from tests.ui.base import UiTestCase, form_data
from tests.ui.test_080_times_pages import TimesPageCase
from tests.ui.test_081_ui_pages import TableToolsEverywhereTests
from tests.unit.test_062_documents import stadtfest

CHOOSER_COLUMN = re.compile(r'name="columns" value="([\w-]+)"')
HEADING = re.compile(r'<th class="[^"]*"(?: aria-sort="\w+")? scope="col">(.{0,40})')
#: A heading that is no link: a column of buttons or tick boxes (see the unit test), or the tick box to choose all.
NO_DATA = ('<input type="checkbox"', '<span class="visually-hidden">', "Aktionen<")


class ComposeErrorTests(UiTestCase):
    """EML-024: "'ComposeForm' object has no attribute '_update_errors'" – a message instead."""

    def setUp(self) -> None:
        super().setUp()
        configure_mailbox()
        self.project = make_project("Stadtfest")
        self.url = reverse("mail:compose", args=[self.project.pk])

    def post(self, error: ValidationError) -> str:
        data = form_data(self.client.get(self.url), "subject")
        data.update(to="kunde@example.de", subject="Angebot", body="Anbei das Angebot.")
        with mock.patch("rentalars.mail.views.send_project_mail", side_effect=error):
            response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_an_error_of_a_field_shows_at_the_field(self) -> None:
        page = self.post(ValidationError({"to": "Der Server hat die Adresse abgelehnt."}))
        self.assertIn("Der Server hat die Adresse abgelehnt.", page)
        self.assertIn("Angebot", page)  # what was written stays

    def test_an_error_of_a_field_the_form_does_not_have_shows_on_top(self) -> None:
        page = self.post(ValidationError({"uploads": "Die Datei ist zu groß."}))
        self.assertIn("Die Datei ist zu groß.", page)

    def test_an_error_without_field(self) -> None:
        page = self.post(ValidationError("Senden ist nicht eingerichtet."))
        self.assertIn("Senden ist nicht eingerichtet.", page)


class EveryHeadingSortsTests(TableToolsEverywhereTests):
    """UIX-015, UIX-040: with every column shown, every heading is a link and every sort works both ways."""

    PAGES = (*TableToolsEverywhereTests.PAGES, "products:scale_list")
    # The tests run in their own module; only the set-up is shared.
    test_every_list_has_columns_csv_and_sortable_headings = None  # type: ignore[assignment]
    test_csv_of_the_view_and_with_all_columns = None  # type: ignore[assignment]
    test_group_by_is_offered_where_a_column_can_group = None  # type: ignore[assignment]

    def setUp(self) -> None:
        super().setUp()
        # Rows in the lists the set-up leaves empty, so that every sort runs on the database.
        product = make_product("K-100", "XLR 10 m")
        make_items(make_model("XLR-Kabel 10 m", product), 2)
        make_person("Ben Braun")
        Venue.objects.create(name="Stadthalle", city="Musterstadt", power_notes="CEE 63 A")
        log.record(
            direction=Direction.OUTGOING,
            kind=LogKind.PROJECT,
            result=LogResult.SENT,
            sender="info@verleih.example",
            recipients="kunde@example.de",
            subject="Angebot",
            user=self.admin_user,
        )
        self.client.get(reverse("customers:list"), {"format": "csv"})  # an entry of the access log

    def test_every_column_sorts_both_ways(self) -> None:
        for name in self.PAGES:
            if name in self.WITHOUT_ROWS_HERE:
                continue
            page = self.assert_ok(self.client.get(reverse(name), {"cols": "all"}))
            columns = CHOOSER_COLUMN.findall(page)
            with self.subTest(page=name):
                self.assertTrue(columns)
                for heading in HEADING.findall(page):
                    if not heading.startswith('<a href="?'):
                        self.assertTrue(heading.startswith(NO_DATA), heading)
            for key in columns:
                for sort in (key, f"-{key}"):
                    with self.subTest(page=name, sort=sort):
                        text = self.assert_ok(self.client.get(reverse(name), {"cols": "all", "sort": sort}))
                        self.assertIn('<table class="table', text)
                        self.assertIn('aria-sort="', text)

    def test_csv_sorted_by_a_computed_column(self) -> None:
        response = self.client.get(reverse("projects:list"), {"format": "csv", "cols": "all", "sort": "-net_total"})
        self.assertEqual(response.status_code, 200)


class ProjectSumsSortTests(UiTestCase):
    """UIX-015: the sums of the project list sort – in Python, over the whole list."""

    def setUp(self) -> None:
        super().setUp()
        self.big = stadtfest().project
        self.small = make_project("Kleines Fest", status=ProjectStatus.CONFIRMED)
        self.url = reverse("projects:list")

    def numbers(self, sort: str) -> list[str]:
        page = self.assert_ok(self.client.get(self.url, {"cols": "number,net_total", "sort": sort}))
        return re.findall(r">(\d{4}-\d{4,})<", page)

    def test_by_the_net_total(self) -> None:
        ascending = self.numbers("net_total")
        self.assertLess(ascending.index(self.small.number), ascending.index(self.big.number))
        descending = self.numbers("-net_total")
        self.assertLess(descending.index(self.big.number), descending.index(self.small.number))

    def test_a_list_too_long_says_so(self) -> None:
        with mock.patch("rentalars.core.tables.PYTHON_SORT_MAX_ROWS", 1):
            page = self.assert_ok(self.client.get(self.url, {"cols": "number,net_total", "sort": "net_total"}))
        self.assertIn("Zum Sortieren nach „Summe netto“ darf die Liste höchstens 1 Zeilen haben", page)
        # The list keeps its default order (by the start, not shown here): no heading is marked as sorting.
        self.assertNotIn("aria-sort=", page)


class MasterDataListTests(UiTestCase):
    """UIX-015, UIX-038 in the lists of the master data."""

    def test_the_path_of_storage_locations_sorts_by_the_tree(self) -> None:
        hall = StorageLocation.objects.create(name="Halle")
        StorageLocation.objects.create(name="Regal B", parent=hall)
        StorageLocation.objects.create(name="Aussenlager")
        StorageLocation.objects.create(name="Regal A", parent=hall)
        url = reverse("admin:masterdata_storagelocation_changelist")
        page = self.assert_ok(self.client.get(url, {"o": "0"}))
        self.assertIn("Name", page)
        rows = re.findall(r'<th class="field-path"><a href="[^"]+">([^<]+)</a>', page)
        expected = ["Aussenlager", "Halle", "Halle &gt; Regal A", "Halle &gt; Regal B"]
        self.assertEqual([row for row in rows if row in expected], expected)
        page = self.assert_ok(self.client.get(url, {"o": "-0"}))
        rows = re.findall(r'<th class="field-path"><a href="[^"]+">([^<]+)</a>', page)
        self.assertEqual([row for row in rows if row in expected], list(reversed(expected)))

    def test_the_filters_are_folded_and_name_what_is_chosen(self) -> None:
        Category.objects.create(name="Testkategorie", code="Q", is_active=False)
        url = reverse("admin:masterdata_category_changelist")
        page = self.assert_ok(self.client.get(url))
        self.assertIn('<details data-list-filter="', page)
        self.assertNotIn("<details data-filter-title=", page)
        self.assertNotRegex(page, r'<details data-list-filter="[^"]*"[^>]* open')
        page = self.assert_ok(self.client.get(url, {"is_active__exact": "0"}))
        self.assertRegex(page, r'<details data-list-filter="[^"]+" class="is-active">')
        self.assertRegex(page, r'Nach [^<:]+: <strong class="filter-chosen">Nein</strong>')

    def test_the_groups_of_django_sort_by_name(self) -> None:
        from django.contrib.auth.models import Group

        Group.objects.create(name="Lager")
        page = self.assert_ok(self.client.get(reverse("admin:auth_group_changelist")))
        self.assertIn('class="sortable column-name', page)


class FilterButtonTests(UiTestCase):
    """UIX-038: the button carries the text for the count of active filters; nothing is remembered."""

    def test_the_text_for_the_count(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:list")))
        self.assertIn('data-filter-active="# aktiv"', page)


class EnglishAnchorTests(UiTestCase):
    """NFA-061: the parts of the backup page have English anchors."""

    def test_backup_and_encryption(self) -> None:
        page = self.assert_ok(self.client.get(reverse("core:administration")))
        self.assertIn(f'href="{reverse("core:backup")}#backup"', page)
        self.assertIn(f'href="{reverse("core:backup")}#encryption"', page)


ANY_HEADING = re.compile(r'<th(?: class="[^"]*")?(?: aria-sort="\w+")? scope="col">(.{0,40})')


class ReportSumsSortTests(TimesPageCase):
    """UIX-015: the sums above the entries of the hours report sort by every heading."""

    def setUp(self) -> None:
        super().setUp()
        record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 19), break_minutes=45, approve=True)
        record_time(self.anna, self.project, self.sound, at(12, 8), at(12, 12), approve=True)
        self.url = reverse("timetracking:report")

    def days(self, **query: str) -> list[str]:
        page = self.assert_ok(self.manager.get(self.url, {"since": "2027-03-01", "group_by": "day", **query}))
        sums = page[page.index('<table class="table stack">') :]
        return re.findall(r"<tr><td>(\d\d\.03\.2027)</td>", sums[: sums.index("</table>")])

    def test_every_heading_is_a_link_and_sorts(self) -> None:
        page = self.assert_ok(self.manager.get(self.url, {"since": "2027-03-01", "group_by": "day"}))
        for heading in ANY_HEADING.findall(page):
            self.assertTrue(heading.startswith(('<a href="?', *NO_DATA)), heading)
        self.assertIn("sums_sort=hours", page)
        self.assertEqual(self.days(), ["10.03.2027", "12.03.2027"])
        self.assertEqual(self.days(sums_sort="-label"), ["12.03.2027", "10.03.2027"])
        self.assertEqual(self.days(sums_sort="hours"), ["12.03.2027", "10.03.2027"])
        self.assertEqual(self.days(sums_sort="-hours"), ["10.03.2027", "12.03.2027"])
        self.assertEqual(self.days(sums_sort="entries"), ["10.03.2027", "12.03.2027"])
