# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages, area "ui": every table view with columns, sorting, groups and CSV (UIX-040).

UIX-041 (no "Back" on the pages of the navigation) is tested in ``tests/ui/test_back_and_page_size.py``
(``NoBackFromTheNavigationTests``), UIX-042 (one picker symbol) in the browser
(``tests/browser/test_081_ui_in_browser.py``).
"""

from __future__ import annotations

import datetime
import re

from django.urls import reverse

from rentalars.accounts.models import Role, SecurityEvent
from rentalars.api.models import Webhook
from rentalars.automations.models import Automation, AutomationRun, RunStatus
from rentalars.core.models import BackgroundJob
from rentalars.notifications.models import Kind, Notification
from rentalars.projects import service_cases
from rentalars.projects.models import CaseStatus, OpenItem, ProjectStatus, ProjectTemplate
from rentalars.timetracking.models import ExpenseKind
from tests.helpers import at, make_customer, make_project, make_user
from tests.ui.base import UiTestCase
from tests.ui.test_080_times_pages import TimesPageCase

GROUP_ROW = re.compile(r'<tr class="table-group"><th colspan="(\d+)" scope="colgroup">(.*?)</th></tr>', re.S)


def groups_of(text: str) -> list[str]:
    """The headings of the groups of a table, as plain text: ``Offen 2 Einträge``."""
    return [" ".join(re.sub(r"<[^>]+>", " ", heading).split()) for _span, heading in GROUP_ROW.findall(text)]


def csv_rows(response: object) -> list[str]:
    """The lines of a CSV answer."""
    return response.content.decode("utf-8-sig").strip().splitlines()  # type: ignore[attr-defined]


class TableToolsEverywhereTests(UiTestCase):
    """UIX-040: every list page shows "Spalten", "CSV", "CSV mit allen Spalten"; sorting by a heading; CSV works."""

    PAGES = (
        "projects:cases",
        "projects:open_items",
        "projects:templates",
        "material:inspections",
        "timetracking:expense_report",
        "timetracking:my_expenses",
        "automations:list",
        "accounts:role_list",
        "accounts:security_log",
        "webhooks:list",
        "notifications:list",
        "core:jobs",
        # Lists that are tables of core.tables, with "Gruppieren nach".
        "projects:list",
        "material:item_list",
        "material:model_list",
        "products:list",
        "customers:list",
        "customers:venue_list",
        "personnel:person_list",
        "accounts:user_list",
        "mail:log",
        "core:access_log",
    )

    def setUp(self) -> None:
        super().setUp()
        # Something in every list, so that the table and its tools are shown.
        customer = make_customer("Stadtwerke")
        make_project("Stadtfest", customer=customer)
        service_cases.create_case(name="Beamer defekt", customer=customer)
        ProjectTemplate.objects.create(name="Bühne klein", content={"groups": [], "lines": []})
        Automation.objects.create(name="Eingangsbestätigung", trigger="inquiry", action="reply", subject="Danke")
        Webhook.objects.create(url="https://erp.example.de/hook", description="ERP", events=["project.created"])
        Notification.objects.create(user=self.admin_user, kind=Kind.PROJECT_CHANGE, title="Projekt geändert")
        BackgroundJob.objects.create(kind="export", title="Export", created_by=self.admin_user)
        SecurityEvent.objects.create(kind="login", user=self.admin_user, identifier="admin")
        project = make_project("Messe", status=ProjectStatus.CONFIRMED_OPEN)
        OpenItem.objects.create(project=project, text="Strom klären")

    #: Pages whose tools show only with rows; their rows need more than this test sets up (see the classes below).
    WITHOUT_ROWS_HERE = {"material:inspections", "timetracking:expense_report", "timetracking:my_expenses"}

    def test_every_list_has_columns_csv_and_sortable_headings(self) -> None:
        for name in self.PAGES:
            if name in self.WITHOUT_ROWS_HERE:
                continue
            with self.subTest(page=name):
                text = self.assert_ok(self.client.get(reverse(name)))
                self.assertIn('class="table-tools"', text)
                self.assertIn("Spalten", text)
                self.assertIn("CSV mit allen Spalten", text)
                if "<table" in text:
                    self.assertRegex(text, r'<th class="[^"]*"( aria-sort="\w+")? scope="col"><a href="\?[^"]*sort=')

    def test_csv_of_the_view_and_with_all_columns(self) -> None:
        for name in self.PAGES:
            if name == "timetracking:my_expenses":
                continue  # needs an own person with expenses – see MyExpensesTableTests
            with self.subTest(page=name):
                view = self.client.get(reverse(name), {"format": "csv"})
                every = self.client.get(reverse(name), {"format": "csv", "cols": "all"})
                for response in (view, every):
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response["Content-Type"].startswith("text/csv"))
                self.assertGreaterEqual(csv_rows(every)[0].count(";"), csv_rows(view)[0].count(";"))

    def test_group_by_is_offered_where_a_column_can_group(self) -> None:
        for name in self.PAGES:
            if name in self.WITHOUT_ROWS_HERE or name == "accounts:role_list":  # roles: no column to group by
                continue
            with self.subTest(page=name):
                text = self.assert_ok(self.client.get(reverse(name)))
                self.assertIn("Gruppieren nach", text)
                self.assertIn("nicht gruppiert", text)


class GroupingTests(UiTestCase):
    """UIX-040: ``?group=<column>`` – a heading per value with the number of rows; CSV unaffected."""

    def setUp(self) -> None:
        super().setUp()
        self.paula = make_user("paula", roles=("Projektleitung",))
        for number in range(30):
            make_project(
                f"Projekt {number:02d}",
                status=ProjectStatus.CONFIRMED if number % 3 else ProjectStatus.INQUIRY,
            )

    def test_groups_with_their_count_in_the_whole_list(self) -> None:
        text = self.assert_ok(self.client.get(reverse("projects:list"), {"group": "status", "per_page": "25"}))
        headings = groups_of(text)
        # 10 inquiries and 20 confirmed projects in the order of the statuses; the page shows 25 rows, the count is
        # that of the whole list.
        self.assertEqual(headings, ["Anfrage 10 Einträge", "Bestätigt 20 Einträge"])
        self.assertIn('<option value="status" selected>Status</option>', text)
        page_two = self.assert_ok(
            self.client.get(reverse("projects:list"), {"group": "status", "per_page": "25", "page": "2"})
        )
        # A group that goes on on the next page is named again there.
        self.assertEqual(groups_of(page_two), ["Bestätigt 20 Einträge"])

    def test_the_heading_spans_the_shown_columns(self) -> None:
        text = self.assert_ok(self.client.get(reverse("projects:list"), {"group": "status", "cols": "number,name"}))
        # Two shown columns and the column of the tick boxes in front of them.
        self.assertEqual({span for span, _heading in GROUP_ROW.findall(text)}, {"3"})

    def test_sorting_works_inside_the_groups(self) -> None:
        text = self.assert_ok(self.client.get(reverse("projects:list"), {"group": "status", "sort": "-name"}))
        names = re.findall(r">(Projekt \d\d)</a>", text)
        inquiries = [name for name in names if int(name[-2:]) % 3 == 0]
        self.assertEqual(names[: len(inquiries)], sorted(inquiries, reverse=True))
        # The sort links keep the grouping.
        self.assertIn("group=status&amp;sort=", text)

    def test_csv_is_not_grouped(self) -> None:
        plain = csv_rows(self.client.get(reverse("projects:list"), {"format": "csv"}))
        grouped = csv_rows(self.client.get(reverse("projects:list"), {"format": "csv", "group": "status"}))
        self.assertEqual(plain, grouped)

    def test_an_unknown_or_hidden_column_is_ignored(self) -> None:
        # UIX-044: "number" groups now – every shown column does.
        for wish in ("nothing", "<script>"):
            with self.subTest(group=wish):
                text = self.assert_ok(self.client.get(reverse("projects:list"), {"group": wish}))
                self.assertEqual(groups_of(text), [])

    def test_a_column_the_user_may_not_see_cannot_group(self) -> None:
        """AUT-023: crew do not learn the customer's number or contact – not even through a grouping.

        PRJ-122: the customer's name shows in every role, so it groups in every role.
        """
        crew = self.browser_for("kai", "Crew")
        for wish in ("customer__number", "contact"):
            text = crew.get(reverse("projects:list"), {"group": wish}).content.decode()
            self.assertEqual(groups_of(text), [], wish)
            self.assertNotIn(f'<option value="{wish}"', text, wish)
        text = crew.get(reverse("projects:list"), {"group": "customer"}).content.decode()
        self.assertIn('<option value="customer"', text)

    def test_the_choice_keeps_filters_and_sort(self) -> None:
        text = self.assert_ok(self.client.get(reverse("projects:list"), {"q": "Projekt", "sort": "-name"}))
        chooser = text.split('<form method="get" class="group-chooser">', 1)[1].split("</form>", 1)[0]
        self.assertIn('<input type="hidden" name="q" value="Projekt">', chooser)
        self.assertIn('<input type="hidden" name="sort" value="-name">', chooser)
        self.assertIn('<label for="group-projects">Gruppieren nach</label>', chooser)


class ServiceCaseTableTests(UiTestCase):
    """UIX-040 for Projekte → Servicefälle."""

    def setUp(self) -> None:
        super().setUp()
        self.customer = make_customer("Stadtwerke")
        self.broken = service_cases.create_case(name="Beamer defekt", customer=self.customer)
        self.cable = service_cases.create_case(name="Kabel fehlt", case_contact="Herr Meier")
        self.cable.case_status = CaseStatus.IN_PROGRESS
        self.cable.save()
        self.url = reverse("projects:cases")

    def test_columns_sorting_and_grouping_by_status(self) -> None:
        text = self.assert_ok(self.client.get(self.url, {"group": "status", "sort": "subject"}))
        self.assertEqual(groups_of(text), ["offen 1 Eintrag", "in Arbeit 1 Eintrag"])
        self.assertIn("Beamer defekt", text)
        self.assertIn("Herr Meier", text)
        self.assertIn('aria-sort="ascending"', text)

    def test_csv_with_all_columns(self) -> None:
        rows = csv_rows(self.client.get(self.url, {"format": "csv", "cols": "all", "sort": "number"}))
        self.assertTrue(rows[0].startswith("Nummer;Betreff;Kunde oder gemeldet von;Zuständig;Status;"), rows[0])
        self.assertIn("Beamer defekt", rows[1])
        self.assertEqual(len(rows), 3)

    def test_the_filters_still_apply(self) -> None:
        text = self.assert_ok(self.client.get(self.url, {"q": "Kabel"}))
        self.assertIn("Kabel fehlt", text)
        self.assertNotIn("Beamer defekt", text)


class ExpenseTableTests(TimesPageCase):
    """UIX-040 for Personal → Spesen and Mein Bereich → Meine Spesen."""

    def setUp(self) -> None:
        super().setUp()
        self.spend("14.00")
        self.spend("6.00", kind=ExpenseKind.PARKING, date=datetime.date(2027, 3, 11))
        self.spend("9.50", date=datetime.date(2027, 3, 12))

    def test_the_report_groups_by_kind(self) -> None:
        text = self.assert_ok(
            self.client.get(reverse("timetracking:expense_report"), {"since": "2027-03-01", "group": "kind"})
        )
        self.assertEqual(groups_of(text), ["Parken/Maut 1 Eintrag", "Verpflegung 2 Einträge"])
        # The tick boxes for "reimbursed" and the reimbursing stay.
        self.assertIn("Angekreuzte als erstattet markieren", text)

    def test_the_report_sorts_by_amount(self) -> None:
        text = self.assert_ok(
            self.client.get(reverse("timetracking:expense_report"), {"since": "2027-03-01", "sort": "-amount"})
        )
        table = text.split("Die Spesen", 1)[1]
        self.assertLess(table.index("14,00 €"), table.index("9,50 €"))
        self.assertLess(table.index("9,50 €"), table.index("6,00 €"))

    def test_my_expenses_as_a_table_with_csv(self) -> None:
        url = reverse("timetracking:my_expenses")
        text = self.assert_ok(self.crew.get(url, {"month": "2027-03", "group": "kind"}))
        self.assertEqual(groups_of(text), ["Parken/Maut 1 Eintrag", "Verpflegung 2 Einträge"])
        self.assertIn("Summe des Monats: 29,50 €", text)
        rows = csv_rows(self.crew.get(url, {"month": "2027-03", "format": "csv"}))
        self.assertEqual(len(rows), 4)
        self.assertNotIn("Aktionen", rows[0])  # the buttons are no data
        # The part fetches itself again with the same grouping after a change in a dialog.
        self.assertIn("month=2027-03&amp;group=kind", text)

    def test_the_amounts_in_the_file_as_before(self) -> None:
        rows = csv_rows(
            self.client.get(
                reverse("timetracking:expense_report"), {"since": "2027-03-01", "format": "csv", "cols": "day,amount"}
            )
        )
        self.assertEqual(rows, ["Tag;Betrag", "10.03.2027;14,00", "11.03.2027;6,00", "12.03.2027;9,50"])


class AutomationTablesTests(UiTestCase):
    """UIX-040: two tables on one page – rules and runs – sorted and grouped each on its own."""

    def setUp(self) -> None:
        super().setUp()
        # Without the default rules of the service cases (PRJ-112), which every installation gets.
        Automation.objects.all().delete()
        self.reply = Automation.objects.create(name="Antworten", trigger="inquiry", action="reply", subject="Danke")
        self.note = Automation.objects.create(
            name="Bescheid geben", trigger="project_status", status="confirmed", action="notify", recipient="manager"
        )
        for number, status in enumerate((RunStatus.DONE, RunStatus.FAILED, RunStatus.DONE)):
            AutomationRun.objects.create(
                automation=self.reply,
                automation_name="Antworten",
                trigger="inquiry",
                action="reply",
                event_key=f"mail:{number}",
                event=f"Mail {number}",
                status=status,
            )

    def test_the_runs_have_their_own_parameters(self) -> None:
        text = self.assert_ok(self.client.get(reverse("automations:list"), {"runs_group": "result", "sort": "-name"}))
        # In the order of the results: done before failed.
        self.assertEqual(groups_of(text), ["Erledigt 2 Einträge", "Fehlgeschlagen 1 Eintrag"])
        # The rules are sorted by name descending, the runs are not affected.
        self.assertLess(text.index("Bescheid geben"), text.index(">Antworten<"))
        self.assertIn("runs_sort=", text)
        self.assertIn('name="runs_group"', text)

    def test_csv_of_each_table(self) -> None:
        rules = csv_rows(self.client.get(reverse("automations:list"), {"format": "csv"}))
        runs = csv_rows(self.client.get(reverse("automations:list"), {"runs_format": "csv"}))
        self.assertEqual(len(rules), 3)
        self.assertEqual(len(runs), 4)
        self.assertNotIn("Aktionen", rules[0])

    def test_switch_off_and_delete_still_work(self) -> None:
        text = self.assert_ok(self.client.get(reverse("automations:list")))
        self.assertIn(f'form="toggle-{self.reply.pk}"', text)
        self.assertIn(f'id="toggle-{self.reply.pk}"', text)
        self.client.post(reverse("automations:toggle", args=[self.reply.pk]))
        self.reply.refresh_from_db()
        self.assertFalse(self.reply.is_active)


class SmallListsTests(UiTestCase):
    """UIX-040 for roles, the security log, webhooks, templates, notifications and the tasks in the background."""

    def test_roles_with_the_number_of_users(self) -> None:
        role = Role.objects.create(name="Lagerhilfe")
        make_user("luka", roles=("Lagerhilfe",))
        text = self.assert_ok(self.client.get(reverse("accounts:role_list"), {"sort": "-users"}))
        self.assertIn(reverse("accounts:role_edit", args=[role.pk]), text)
        rows = csv_rows(self.client.get(reverse("accounts:role_list"), {"format": "csv", "sort": "role"}))
        self.assertIn("Lagerhilfe;;1;alle Projekte", rows)

    def test_the_security_log_groups_by_event(self) -> None:
        SecurityEvent.objects.create(kind="login", user=self.admin_user)
        SecurityEvent.objects.create(kind="login_failed", identifier="mallory")
        text = self.assert_ok(self.client.get(reverse("accounts:security_log"), {"group": "event"}))
        self.assertEqual(len(groups_of(text)), 2)
        self.assertIn("mallory", text)

    def test_notifications_as_a_table_unread_in_bold(self) -> None:
        Notification.objects.create(user=self.admin_user, kind=Kind.PROJECT_CHANGE, title="Neu")
        Notification.objects.create(
            user=self.admin_user, kind=Kind.PROJECT_CHANGE, title="Gelesen", read_at=datetime.datetime(2027, 1, 1)
        )
        text = self.assert_ok(self.client.get(reverse("notifications:list")))
        self.assertIn('<tr class="unread">', text)
        self.assertIn("Kategorie", text)
        # B's filter by category is still there, now behind the filter button.
        self.assertIn('id="f-category"', text)
        self.assertIn('data-filter-toggle="notifications"', text)

    def test_templates_can_still_be_deleted(self) -> None:
        template = ProjectTemplate.objects.create(name="Bühne", content={"groups": [{}], "lines": [{}, {}]})
        text = self.assert_ok(self.client.get(reverse("projects:templates")))
        self.assertIn("1 Teilgruppen, 2 Positionen", text)
        self.assertIn(f'form="delete-template-{template.pk}"', text)
        self.client.post(reverse("projects:template_delete", args=[template.pk]))
        self.assertFalse(ProjectTemplate.objects.exists())


class ShortageTablesTests(UiTestCase):
    """UIX-040: Planung → Fehlbestände holds three tables; each has its own parameters and its own CSV file."""

    def test_three_files(self) -> None:
        url = reverse("availability:shortages")
        for parameter, heading in (
            ("format", "Projekt;Produkt;Zeitraum;Fehlmenge"),
            ("bottlenecks_format", "Produkt;Fehlen höchstens;Von;Projekte"),
            ("subrentals_format", "Projekt;Was;Lieferant;Zeitraum;Status;Einkaufspreis"),
        ):
            with self.subTest(table=parameter):
                rows = csv_rows(self.client.get(url, {parameter: "csv"}))
                self.assertEqual(rows[0], heading)


class ReviewTablesTests(TimesPageCase):
    """UIX-040 after the review: approving, the hours report, rental scales, roles, the master data lists."""

    def setUp(self) -> None:
        super().setUp()
        from tests.helpers import record_time

        self.first = record_time(self.anna, self.project, self.sound, at(10, 8), at(10, 12), submit=True)
        self.second = record_time(self.anna, self.project, self.sound, at(11, 9), at(11, 17), submit=True)

    def test_approving_sorts_within_the_project_and_has_a_csv(self) -> None:
        url = reverse("timetracking:approval")
        text = self.assert_ok(self.client.get(url, {"sort": "-hours"}))
        self.assertIn("Spalten", text)
        self.assertIn('aria-sort="descending"', text)
        self.assertNotIn("Gruppieren nach", text)  # the page is grouped by project: one form each
        self.assertLess(
            text.index(f'name="entry" value="{self.second.pk}"'), text.index(f'name="entry" value="{self.first.pk}"')
        )
        rows = csv_rows(self.client.get(url, {"format": "csv"}))
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows[0].startswith("Person;Tag;Uhrzeit;Funktion;Stunden"), rows[0])

    def test_the_entries_of_the_report_with_their_own_parameters(self) -> None:
        url = reverse("timetracking:report")
        query = {"since": "2027-03-01", "entries_group": "day", "entries_sort": "-hours"}
        text = self.assert_ok(self.client.get(url, query))
        self.assertEqual(len(groups_of(text)), 2)
        self.assertIn('name="entries_group"', text)
        rows = csv_rows(self.client.get(url, {"since": "2027-03-01", "entries_format": "csv"}))
        self.assertEqual(len(rows), 3)
        # The file of the report (ZEI-017) is still ?format=csv, and the period stays that of the filter.
        report = self.client.get(url, {"since": "2027-03-01", "format": "csv"})
        self.assertEqual(report.status_code, 200)
        default = self.assert_ok(self.client.get(url, {"entries_sort": "hours"}))
        self.assertIn("Ohne Filter: der laufende Monat.", default)

    def test_rental_scales_roles_and_master_data(self) -> None:
        text = self.assert_ok(self.client.get(reverse("products:scale_list")))
        self.assertIn("CSV mit allen Spalten", text)
        self.assertIn("Gruppieren nach", text)
        roles = self.assert_ok(self.client.get(reverse("accounts:role_list"), {"group": "project_scope"}))
        self.assertTrue(groups_of(roles))
        for name in ("category", "unit", "taxrate", "manufacturer", "supplier", "storagelocation", "documenttype"):
            with self.subTest(list=name):
                url = reverse(f"admin:masterdata_{name}_changelist")
                page = self.assert_ok(self.client.get(url))
                self.assertIn("CSV mit allen Spalten", page)
                self.assertIn('class="column-chooser"', page)
                csv = self.client.get(url, {"format": "csv", "cols": "all"})
                self.assertTrue(csv["Content-Type"].startswith("text/csv"))

    def test_master_data_grouped_and_with_chosen_columns(self) -> None:
        url = reverse("admin:masterdata_category_changelist")
        text = self.assert_ok(self.client.get(url, {"group": "is_active", "cols": ["path", "code"]}))
        self.assertTrue(groups_of(text))
        self.assertNotIn("column-has_own_stock", text)  # the column was not chosen
        # Sorting and filter links keep the choice.
        self.assertIn("cols=code", text)
        self.assertIn("group=is_active", text)
        rows = csv_rows(self.client.get(url, {"format": "csv", "cols": ["path", "code"]}))
        self.assertEqual(rows[0].count(";"), 1)
