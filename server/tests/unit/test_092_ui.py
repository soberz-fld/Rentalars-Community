# SPDX-License-Identifier: GPL-3.0-or-later
"""Area "ui": entries per page in every table, required marks, notification texts, options of the calendar.

Four requirements:

1. UIX-050: in every table the number of entries can be chosen, as for the products; besides 25, 50, 100, 200 a number can be typed.
   Existing tables are checked and changed.
2. UIX-051: required fields in forms are always marked with the red asterisk.
3. UIX-005: the texts of notifications in the table overview do not begin with <p> and end with </p>.
4. VFG-039: in Planung → Kalender it can be chosen whether phases of projects and follow-ups are shown.

* Every list that pages offers 25, 50, 100, 200 and a field for any number from 5 to 1,000 (``?per_page=``); a
  number out of bounds is refused with a message; the choice is remembered per user and list
  (``core.listing.paginate``, ``TableState.paginate``), also in the lists of the master data.
* A required field shows the red asterisk at its label – a crawl over the pages of an administrator holds every
  form to it, and to the line "* Pflichtfeld" at its top.
* The text of a notification is plain text with its line breaks – in the table and in the CSV file.
* The calendar shows the phases of the projects (as before) and, when chosen, the follow-ups the user may see.
"""

from __future__ import annotations

import collections
import datetime
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from django.conf import settings
from django.test import RequestFactory
from django.urls import reverse

from rentalars.accounts.models import Role
from rentalars.core.listing import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    MIN_PAGE_SIZE,
    page_size_choice,
    paginate,
    typed_page_size,
)
from rentalars.core.models import TablePreference
from rentalars.core.tables import Column, TableDefinition, plain_text, text_lines
from rentalars.customers.models import Venue
from rentalars.masterdata.models import Unit
from rentalars.notifications.models import Kind, Notification
from rentalars.projects import service_cases
from rentalars.projects.follow_up import set_follow_up
from rentalars.projects.forms import GroupForm
from rentalars.projects.models import ProjectAccessLevel, ProjectMembership, ProjectPhase, ProjectTemplate
from rentalars.schedule.views import CALENDAR_OPTIONS
from tests.helpers import (
    ALL_RIGHTS,
    ASSIGNED_READER,
    RentalarsTestCase,
    add_group,
    add_line,
    at,
    make_customer,
    make_items,
    make_model,
    make_person,
    make_product,
    make_project,
    make_stock,
    make_user,
    plan,
    record_time,
)
from tests.ui.base import UiTestCase

# --- 1. Entries per page in every table -----------------------------------------------------------------------

#: A table with a prefix, as the second table of a page (UIX-040).
PREFIXED = TableDefinition(
    "test_092_prefixed",
    [Column("name", "Name", cell=lambda row: row, sort=lambda row: row)],
    default_sort="name",
    prefix="runs_",
)

PRODUCT_ROW = re.compile(r'<a class="artno" href="/products/K-\d{3}/"')
UNIT_ROW = re.compile(r'<th class="field-name"><a href="/administration/masterdata/masterdata/unit/\d+/change/')


def page_size_form(html: str) -> str:
    """The small form of the foot of a list that takes a typed number of entries per page."""
    found = re.search(r'<form method="get" class="page-size-form">.*?</form>', html, re.S)
    assert found is not None, "no field for the number of entries per page"
    return found.group(0)


class PageSizeRuleTests(RentalarsTestCase):
    """UIX-050: the rules of the choice, without a page: bounds, the address, the memory per list."""

    def request(self, **query: str) -> Any:
        request = RequestFactory().get("/list/", query)
        request.user = self.paul
        return request

    def setUp(self) -> None:
        super().setUp()
        self.paul = make_user("paul")

    def saved(self) -> dict[str, int | None]:
        """What is remembered of Paul: entries per page by list."""
        return dict(TablePreference.objects.filter(user=self.paul).values_list("table", "page_size"))

    def test_any_whole_number_from_5_to_1000(self) -> None:
        self.assertEqual((MIN_PAGE_SIZE, MAX_PAGE_SIZE, DEFAULT_PAGE_SIZE), (5, 1000, 50))
        for typed, expected in (
            ("5", 5),
            ("7", 7),
            (" 333 ", 333),
            ("1000", 1000),
            ("4", None),
            ("1001", None),
            ("0", None),
            ("-25", None),
            ("2.5", None),
            ("abc", None),
            ("", None),
        ):
            with self.subTest(typed=typed):
                self.assertEqual(typed_page_size(typed), expected)

    def test_the_address_decides_and_is_remembered_per_list(self) -> None:
        self.assertEqual(page_size_choice(self.request(per_page="7"), key="products").size, 7)
        self.assertEqual(self.saved(), {"products": 7})
        self.assertEqual(page_size_choice(self.request(), key="products").size, 7)
        self.assertEqual(page_size_choice(self.request(), key="customers").size, DEFAULT_PAGE_SIZE)
        self.assertEqual(page_size_choice(self.request(per_page="100"), key="products").size, 100)
        self.assertEqual(page_size_choice(self.request(), key="products").size, 100)

    def test_a_number_out_of_bounds_is_refused_with_a_message(self) -> None:
        page_size_choice(self.request(per_page="25"), key="products")
        refused = page_size_choice(self.request(per_page="5000"), key="products")
        self.assertEqual(refused.size, 25)  # the list keeps its length
        self.assertEqual(refused.refused, "5000")
        self.assertEqual(
            refused.error,
            "„5000“ geht nicht: Bitte eine ganze Zahl von 5 bis 1.000 Einträgen je Seite eingeben. "
            "Die Liste zeigt 25 Einträge je Seite.",
        )
        self.assertEqual(self.saved(), {"products": 25})

    def test_nothing_is_remembered_without_a_user(self) -> None:
        request = RequestFactory().get("/list/", {"per_page": "7"})
        self.assertEqual(paginate(request, list(range(20))).paginator.per_page, 7)  # API-like requests: no account
        self.assertFalse(TablePreference.objects.exists())

    def test_kept_with_the_column_choice(self) -> None:
        """One row per user and list; resetting the columns of a list keeps its page size, and the other way round."""
        TablePreference.save_columns(self.paul, "products", ["name"])
        TablePreference.save_page_size(self.paul, "products", 7)
        self.assertEqual(TablePreference.columns_of(self.paul, "products"), ["name"])
        TablePreference.save_columns(self.paul, "products", None)  # "Default columns"
        self.assertEqual(self.saved(), {"products": 7})
        self.assertEqual(TablePreference.columns_of(self.paul, "products"), [])  # no choice: the default columns
        TablePreference.save_columns(self.paul, "customers", None)
        self.assertEqual(self.saved(), {"products": 7})

    def test_the_page_carries_what_the_template_needs(self) -> None:
        page = paginate(self.request(q="Kabel", sort="-name", per_page="7", page="2"), list(range(30)))
        paginator = page.paginator
        self.assertEqual((page.number, paginator.per_page, len(page)), (2, 7, 7))
        self.assertEqual(paginator.size_param, "per_page")
        self.assertEqual(paginator.typed_size, "7")  # not one of the links: shown in the field
        self.assertEqual(paginator.kept_parameters, [("q", "Kabel"), ("sort", "-name")])
        self.assertEqual(
            [(size, url, current) for size, url, current in paginator.size_links][:2],
            [(25, "?q=Kabel&sort=-name&per_page=25", False), (50, "?q=Kabel&sort=-name&per_page=50", False)],
        )
        self.assertEqual(page.previous_url, "?q=Kabel&sort=-name&per_page=7&page=1")
        self.assertEqual(page.next_url, "?q=Kabel&sort=-name&per_page=7&page=3")
        self.assertTrue(paginator.offers_sizes)

    def test_a_short_list_offers_no_choice_unless_its_pages_are_shorter_still(self) -> None:
        self.assertFalse(paginate(self.request(), list(range(20))).paginator.offers_sizes)
        self.assertTrue(paginate(self.request(per_page="5"), list(range(20))).paginator.offers_sizes)

    def test_a_table_with_a_prefix_pages_with_its_own_parameters(self) -> None:
        """The machinery of every table (``TableState.paginate``): the second table of a page keeps its own page."""
        request = self.request(runs_per_page="10", runs_page="2", page="3", per_page="25")
        table = PREFIXED.state(request)
        page = table.paginate(table.order([f"R{number:02d}" for number in range(35)]))
        self.assertEqual((page.number, page.paginator.per_page, page[0]), (2, 10, "R10"))
        self.assertEqual(page.paginator.size_param, "runs_per_page")
        self.assertIn(("page", "3"), page.paginator.kept_parameters)  # the page of the other table stays
        self.assertNotIn("runs_page=", page.paginator.size_links[0][1])


class PageSizeListTests(UiTestCase):
    """Several lists: the links, the field, the bounds, the memory per list – and lists that page (UIX-050)."""

    def setUp(self) -> None:
        super().setUp()
        for number in range(30):
            make_product(f"K-{number:03d}", f"Kabel {number} m")
            make_customer(f"Kunde {number:02d}")

    def test_the_product_list_takes_a_typed_number(self) -> None:
        text = self.assert_ok(self.client.get(reverse("products:list"), {"q": "Kabel", "per_page": "7"}))
        self.assertEqual(len(PRODUCT_ROW.findall(text)), 7)
        self.assertIn("Seite 1 von 5", text)
        form = page_size_form(text)
        self.assertIn('<input type="hidden" name="q" value="Kabel">', form)
        self.assertNotIn('name="page"', form)
        self.assertIn('<label for="per-page">Eigene Anzahl</label>', form)
        self.assertIn(
            '<input type="number" id="per-page" name="per_page" min="5" max="1000" step="1" inputmode="numeric" '
            'value="7" aria-describedby="per-page-hint">',
            form,
        )
        self.assertIn(
            '<span id="per-page-hint" class="visually-hidden">Einträge je Seite, von 5 bis 1.000</span>', form
        )
        self.assertIn('<button class="btn secondary small" type="submit">Anzeigen</button>', form)
        # The four numbers stay links; none of them is the current one.
        for size in (25, 50, 100, 200):
            self.assertIn(f'href="?q=Kabel&amp;per_page={size}"', text)

    def test_bounds(self) -> None:
        for wish in ("4", "1001", "abc"):
            with self.subTest(per_page=wish):
                text = self.assert_ok(self.client.get(reverse("products:list"), {"q": "Kabel", "per_page": wish}))
                self.assertEqual(len(PRODUCT_ROW.findall(text)), 30)  # the default of 50 shows all 30
                form = page_size_form(text)
                self.assertIn(f'value="{wish}" aria-describedby="per-page-hint" aria-invalid="true"', form)
                self.assertIn(
                    f'<span id="per-page-hint" class="error" role="alert">„{wish}“ geht nicht: Bitte eine ganze Zahl '
                    "von 5 bis 1.000 Einträgen je Seite eingeben. Die Liste zeigt 50 Einträge je Seite.</span>",
                    form,
                )
        text = self.assert_ok(self.client.get(reverse("products:list"), {"q": "Kabel", "per_page": "1000"}))
        self.assertEqual(len(PRODUCT_ROW.findall(text)), 30)
        self.assertNotIn("geht nicht", text)

    def test_remembered_per_user_and_list(self) -> None:
        cables = reverse("products:list") + "?q=Kabel"  # the start data hold service products as well
        self.client.get(cables, {"per_page": "7"})
        self.assertEqual(len(PRODUCT_ROW.findall(self.assert_ok(self.client.get(cables)))), 7)
        customers = self.assert_ok(self.client.get(reverse("customers:list")))
        self.assertIn('<strong aria-current="true">50</strong>', customers)  # another list keeps its own
        self.assertNotIn('class="page-size-form"', customers.split("<strong aria-current")[0][-200:])
        # Remembered with the account: after logging in again, in another browser, too.
        again = self.browser_of(self.admin_user)
        self.assertEqual(len(PRODUCT_ROW.findall(self.assert_ok(again.get(cables)))), 7)
        # Another user has nothing remembered.
        other = self.browser_of(make_user("olga", superuser=True))
        self.assertEqual(len(PRODUCT_ROW.findall(self.assert_ok(other.get(cables)))), 30)
        # The address wins and is remembered in its turn; one of the links counts like a typed number.
        self.assertEqual(len(PRODUCT_ROW.findall(self.assert_ok(self.client.get(cables + "&per_page=25")))), 25)
        self.assertEqual(len(PRODUCT_ROW.findall(self.assert_ok(self.client.get(cables)))), 25)

    def test_lists_that_page_since_092(self) -> None:
        """Roles, project templates, rental scales, job functions, webhooks page their rows."""
        for number in range(12):
            Role.objects.create(name=f"Rolle {number:02d}")
            ProjectTemplate.objects.create(name=f"Vorlage {number:02d}", description="Zeile 1\nZeile 2")
        for name, row in (
            ("accounts:role_list", r'href="/administration/roles/\d+/"'),
            ("projects:templates", r'href="/projects/templates/\d+/content/"'),
        ):
            with self.subTest(page=name):
                text = self.assert_ok(self.client.get(reverse(name), {"per_page": "5"}))
                self.assertEqual(len(re.findall(row, text)), 5, name)
                self.assertIn('<input type="number" id="per-page" name="per_page"', text)
                self.assertIn("Seite 1 von", text)
        for name in ("products:scale_list", "personnel:job_function_list", "webhooks:list", "projects:open_items"):
            with self.subTest(page=name):
                self.assert_ok(self.client.get(reverse(name), {"per_page": "5"}))

    def test_the_lists_of_the_master_data(self) -> None:
        for number in range(12):
            Unit.objects.create(name=f"Einheit {number:02d}", abbreviation=f"E{number:02d}")
        url = "/administration/masterdata/masterdata/unit/"
        text = self.assert_ok(self.client.get(url, {"per_page": "5"}))
        self.assertEqual(len(UNIT_ROW.findall(text)), 5)
        self.assertIn('<input type="number" id="per-page-admin" name="per_page" min="5" max="1000"', text)
        self.assertIn('value="5" aria-describedby="per-page-admin-hint"', text)
        self.assertIn('<a href="?per_page=25" aria-label="25 Einträge je Seite">25</a>', text)
        # The links of the list (sorting, pages) keep the choice; it is remembered for the list.
        self.assertIn("per_page=5", re.search(r'class="paginator">(.*?)</p>', text, re.S).group(1))
        again = self.assert_ok(self.client.get(url))
        self.assertEqual(len(UNIT_ROW.findall(again)), 5)
        refused = self.assert_ok(self.client.get(url, {"per_page": "2"}))
        self.assertIn("„2“ geht nicht", refused)


class EveryTableTests(RentalarsTestCase):
    """Every template that shows a table of ``core.tables`` shows the foot with the choice – or says why not.

    A new table gets the choice by paging with ``TableState.paginate`` (or ``core.listing.paginate``) and
    showing ``core/_pagination.html`` below it; this test holds every template to that.
    """

    #: Templates with tables that do not page, by design, and how many.
    NOT_PAGED = {
        # One form per project with its sum and its buttons: a page would part a project's times (ZEI-013).
        "timetracking/approval.html": 1,
        # The own expenses of one month with the sum of the month: the month is the page (ZEI-019).
        "timetracking/_my_expenses.html": 1,
        # The rules of the automations stand above their runs, which page; there are few, and they fill the filter.
        "automations/list.html": 1,
    }

    TABLE = re.compile(r'\{% include "core/_table.html"(?: with ([^%]*))?\s*%\}')
    FOOT = re.compile(r'\{% include "core/_pagination.html"(?: with ([^%]*))?\s*%\}')

    @staticmethod
    def names(pattern: re.Pattern[str], text: str, parameter: str) -> set[str]:
        """The tables (``table=…``) or pages (``page=…``) a template includes – one name per table shown."""
        found = set()
        for arguments in pattern.findall(text):
            given = re.search(rf"\b{parameter}=(\S+)", arguments or "")
            found.add(given.group(1) if given else parameter)
        return found

    def test_tables_and_feet(self) -> None:
        root = Path(settings.BASE_DIR) / "templates"
        missing = {}
        for path in sorted(root.rglob("*.html")):
            text = path.read_text(encoding="utf-8")
            tables = self.names(self.TABLE, text, "table")
            feet = self.names(self.FOOT, text, "page")
            name = str(path.relative_to(root))
            if tables and len(tables) - len(feet) != self.NOT_PAGED.get(name, 0):
                missing[name] = (sorted(tables), sorted(feet))
        self.assertEqual(missing, {}, "tables without the choice of entries per page (core/_pagination.html)")


# --- 2. Required fields marked ----------------------------------------------------------------------------------


class RequiredMarks(HTMLParser):
    """The controls of a page that must be filled in, whether their label shows the asterisk, and the note."""

    CONTROLS = {"input", "select", "textarea"}
    SKIPPED_TYPES = {"hidden", "submit", "button", "image", "reset"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.labels: dict[str, list[str]] = {}
        self.controls: list[dict[str, Any]] = []
        self.forms: list[dict[str, Any]] = []
        self._open: list[dict[str, Any]] = []  # labels, legends and first cells of rows being read
        self._form: list[dict[str, Any]] = []
        self._fieldsets: list[dict[str, Any]] = []
        self._rows: list[dict[str, Any]] = []

    def _collect(self, text: str) -> None:
        for collector in self._open:
            collector["html"].append(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {name: value or "" for name, value in attrs}
        self._collect(self.get_starttag_text() or "")
        if self._form and "required-note" in a.get("class", ""):
            self._form[-1]["note"] = True
        if tag == "form":
            form = {"method": a.get("method", "get").lower(), "required": False, "note": False}
            form["action"] = a.get("action", "") or a.get("hx-post", "")
            self._form.append(form)
            self.forms.append(form)
        elif tag == "fieldset":
            self._fieldsets.append({"legend": {"html": [], "tag": "legend"}})
        elif tag == "legend" and self._fieldsets:
            self._open.append(self._fieldsets[-1]["legend"])
        elif tag == "tr":
            self._rows.append({"cell": None})
        elif tag in ("td", "th") and self._rows and self._rows[-1]["cell"] is None:
            self._rows[-1]["cell"] = {"html": [], "tag": tag}
            self._open.append(self._rows[-1]["cell"])
        elif tag == "label":
            # With its own tag: Django's administration marks the label itself (class "required", admin.css).
            self._open.append({"for": a.get("for", ""), "html": [self.get_starttag_text() or ""], "tag": "label"})
        elif tag in self.CONTROLS and not (tag == "input" and a.get("type", "text") in self.SKIPPED_TYPES):
            required = "required" in a or a.get("aria-required") == "true" or "data-require-if" in a
            form = self._form[-1] if self._form else None
            if form is not None and required and "data-require-if" not in a:
                form["required"] = True
            self.controls.append(
                {
                    "tag": tag,
                    "id": a.get("id", ""),
                    "name": a.get("name", ""),
                    "type": a.get("type", ""),
                    "required": required,
                    "method": form["method"] if form else ("post" if a.get("form") else ""),
                    "wrapped": next((each for each in reversed(self._open) if each["tag"] == "label"), None),
                    "fieldset": self._fieldsets[-1] if self._fieldsets else None,
                    "row": self._rows[-1] if self._rows else None,
                }
            )

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        self._collect(f"</{tag}>")
        if tag in ("label", "legend", "td", "th"):
            for index in range(len(self._open) - 1, -1, -1):
                if self._open[index]["tag"] == tag:
                    closed = self._open.pop(index)
                    if tag == "label" and closed.get("for"):
                        self.labels.setdefault(closed["for"], []).append("".join(closed["html"]))
                    break
        elif tag == "fieldset" and self._fieldsets:
            self._fieldsets.pop()
        elif tag == "tr" and self._rows:
            self._rows.pop()
        elif tag == "form" and self._form:
            self._form.pop()

    def handle_data(self, data: str) -> None:
        self._collect(data)

    def problems(self) -> list[str]:
        """Required controls without the asterisk at their label, and forms with such fields but without the note.

        A group of radio buttons carries the mark at its legend – or at the first cell of its row (the rights of a
        role); every other control at its label.
        """
        found = []
        for control in self.controls:
            if not control["required"] or control["method"] == "get":
                continue
            texts = []
            if control["type"] == "radio":
                if control["fieldset"] is not None and control["fieldset"]["legend"]["html"]:
                    texts.append("".join(control["fieldset"]["legend"]["html"]))
                elif control["row"] is not None and control["row"]["cell"] is not None:
                    texts.append("".join(control["row"]["cell"]["html"]))
            if not texts:
                texts = list(self.labels.get(control["id"], [])) if control["id"] else []
                if control["wrapped"] is not None:
                    texts.append("".join(control["wrapped"]["html"]))
            if not any('class="required' in text for text in texts):
                found.append(f"no asterisk: {control['tag']} {control['name']} – {(texts or ['no label'])[0][:80]}")
        found += [
            f"no “* Pflichtfeld”: form {form['action'] or '(this page)'}"
            for form in self.forms
            if form["method"] == "post" and form["required"] and not form["note"]
        ]
        return list(dict.fromkeys(found))


def required_problems(html: str) -> list[str]:
    """What the page lacks of the marks of required fields."""
    checker = RequiredMarks()
    checker.feed(html)
    return checker.problems()


#: Pages the crawl does not follow: they change something, deliver files, or repeat a list in another order.
#: Django's own page to change the password of the administration is left out: the own password is changed under
#: "Mein Konto".
SKIP = re.compile(
    r"logout|delete|remove|revoke|/media/|\.pdf|\.csv|\.ics|\.zip|\.xml|/export|download|/api/|/static/|/file|"
    r"attachment|/raw|calendar-feed|preview|/print|/history/|password_change|/manual/|/audit-log/|/security-log/|"
    r"/changes|/suggest|[?&](page|sort|q|view|month|week|day|start|span|per_page|group|cols|format|order|contents|"
    r"weeks|days|since|until|status)="
)


class RequiredMarksTests(UiTestCase):
    """UIX-051 (UIX-035) for every form: the crawl of an administrator's pages, dialogs included (``hx-get``)."""

    LIMIT = 700

    def business_data(self) -> None:
        """A little of everything, so that the pages of records and their dialogs are reached."""
        customer = make_customer("Stadtwerke Musterstadt")
        project = make_project("Stadtfest", customer=customer)
        add_line(project, make_stock("K-001", 3, "XLR-Kabel 5 m"), 2)
        person = make_person("Anna Becker", rates={"Tontechnik": "35.00"}, user=self.admin_user)
        plan(project, "Tontechnik", person)
        ProjectPhase.objects.create(project=project, start=at(9, 8), end=at(9, 16))
        set_follow_up(project, on=datetime.date(2027, 3, 3), note="Nachfassen", by=self.admin_user)
        service_cases.create_case(
            name="Spot flackert", customer=customer, manager=self.admin_user, user=self.admin_user
        )
        record_time(person, project, "Tontechnik", at(10, 8), at(10, 16))
        make_items(make_model("Stativ"), 3)
        Venue.objects.create(name="Stadthalle", street="Markt 1", city="Musterstadt")

    def test_every_required_field_is_marked(self) -> None:
        self.business_data()
        self.client.raise_request_exception = False  # a broken page is the business of other tests
        queue = collections.deque([reverse("core:home")])
        seen: set[str] = set()
        problems: dict[str, list[str]] = {}
        forms = 0
        while queue and len(seen) < self.LIMIT:
            url = queue.popleft()
            if url in seen:
                continue
            seen.add(url)
            dialog = url.startswith("hx:")
            response = self.client.get(url[3:], HTTP_HX_REQUEST="true") if dialog else self.client.get(url)
            if response.status_code != 200 or "text/html" not in response.get("Content-Type", ""):
                continue
            html = response.content.decode()
            forms += html.count('method="post"')
            for prefix, pattern in (("", r'href="(/[^"#]*)"'), ("hx:", r'hx-get="(/[^"#]*)"')):
                for address in re.findall(pattern, html):
                    address = prefix + address.replace("&amp;", "&")
                    if address not in seen and not SKIP.search(address):
                        queue.append(address)
            found = required_problems(html)
            if found:
                problems[url] = found
        self.assertGreater(len(seen), 300)
        self.assertGreater(forms, 150)
        self.maxDiff = None
        self.assertEqual(problems, {}, f"required fields without their mark ({len(seen)} pages read)")

    def test_the_checker_finds_what_it_looks_for(self) -> None:
        unmarked = '<form method="post"><label for="a">Name</label><input id="a" name="a" required></form>'
        self.assertEqual(
            required_problems(unmarked),
            ['no asterisk: input a – <label for="a">Name</label>', "no “* Pflichtfeld”: form (this page)"],
        )
        marked = (
            '<form method="post"><p class="required-note" aria-hidden="true"><span class="required">*</span> '
            'Pflichtfeld</p><label for="a">Name <span class="required" aria-hidden="true">*</span></label>'
            '<input id="a" name="a" required><fieldset><legend>Art <span class="required" aria-hidden="true">*'
            '</span></legend><input type="radio" name="k" id="k0" required><label for="k0">eins</label></fieldset>'
            "</form>"
        )
        self.assertEqual(required_problems(marked), [])
        self.assertEqual(required_problems('<form method="get"><input name="q" required></form>'), [])

    def test_the_mark_is_hidden_from_screen_readers_which_hear_required_at_the_field(self) -> None:
        text = self.assert_ok(self.client.get(reverse("customers:create")))
        label = re.search(r'<label for="id_name">.*?</label>', text).group(0)
        self.assertIn('<span class="required" aria-hidden="true">*</span>', label)
        self.assertRegex(text, r'<input type="text" name="name"[^>]* required id="id_name"')
        self.assertIn(
            '<p class="required-note" aria-hidden="true"><span class="required">*</span> Pflichtfeld</p>', text
        )

    def test_fields_written_by_hand_and_groups(self) -> None:
        """The pages the crawl found without marks: by hand, radio buttons, the rights of a role."""
        project = make_project("Stadtfest")
        texts = {
            "related": self.assert_ok(self.client.get(reverse("projects:deployment", args=[project]))),
            "two-factor": self.assert_ok(self.client.get(reverse("accounts:two_factor_setup"))),
            "settings": self.assert_ok(self.client.get(reverse("core:company_settings"))),
            "role": self.assert_ok(self.client.get(reverse("accounts:role_create"))),
        }
        self.assertIn(
            'Projekt oder Servicefall <span class="required" aria-hidden="true">*</span></label>', texts["related"]
        )
        self.assertIn(
            'Der Code, den die App jetzt zeigt <span class="required" aria-hidden="true">*</span>', texts["two-factor"]
        )
        self.assertIn(
            'Antwort auf Einsatzanfragen <span class="required" aria-hidden="true">*</span></legend>', texts["settings"]
        )
        self.assertIn('<td>Material <span class="required" aria-hidden="true">*</span>', texts["role"])
        for name, text in texts.items():
            with self.subTest(page=name):
                self.assertEqual(required_problems(text), [])

    def test_the_forms_of_the_master_data(self) -> None:
        """Django marks the label with the class "required"; admin.css draws the asterisk; the note is at the top."""
        text = self.assert_ok(self.client.get("/administration/masterdata/masterdata/unit/add/"))
        self.assertIn('<label class="required" for="id_name">', text)
        self.assertIn(
            '<p class="required-note" aria-hidden="true"><span class="required">*</span> Pflichtfeld</p>', text
        )
        css = (Path(settings.BASE_DIR) / "static/css/admin.css").read_text(encoding="utf-8")
        self.assertIn('form label.required::after { content: " *"; content: " *" / ""; color: var(--error-fg); }', css)

    def test_fields_required_only_in_some_cases(self) -> None:
        """Required by the rules of the form only for a choice: the asterisk shows while the choice holds."""
        project = make_project("Stadtfest")
        group = add_group(project, "Licht")
        form = GroupForm(instance=group, rights=ALL_RIGHTS)
        self.assertEqual(form.fields["alternative_to"].widget.attrs["data-require-if"], "kind=alternative")
        dialog = self.assert_ok(self.htmx("get", reverse("projects:group_edit", args=[project.pk, group.pk])))
        self.assertIn('data-show-if="kind=alternative">*</span>', dialog)


# --- 3. Notification texts --------------------------------------------------------------------------------------


class NotificationTextTests(UiTestCase):
    """UIX-005: the text of a notification as plain text with its line breaks – no "<p>…</p>" to read."""

    def setUp(self) -> None:
        super().setUp()
        self.notification = Notification.objects.create(
            user=self.admin_user,
            kind=Kind.values[0],
            title="Neue Anfrage",
            body="Bitte prüfen:\nBühne & Licht\n\n<b>Sofort</b> erledigen",
        )

    def test_in_the_table(self) -> None:
        text = self.assert_ok(self.client.get(reverse("notifications:list")))
        self.assertIn('<div class="muted small">Bitte prüfen:<br>Bühne &amp; Licht<br><br>Sofort erledigen</div>', text)
        self.assertNotIn("&lt;p&gt;", text)
        self.assertNotIn("&lt;b&gt;", text)

    def test_in_the_csv_file(self) -> None:
        response = self.client.get(reverse("notifications:list"), {"format": "csv", "cols": "all"})
        rows = response.content.decode("utf-8").lstrip("﻿").splitlines()
        self.assertEqual(rows[0].split(";")[:2], ["Benachrichtigung", "Text"])
        self.assertIn("Neue Anfrage;Bitte prüfen: Bühne & Licht Sofort erledigen;", rows[1])
        self.assertNotIn("<", response.content.decode("utf-8"))
        # The text is a column of its own, switched off unless chosen: the table shows it below the title.
        self.assertNotIn(">Text</a></th>", self.assert_ok(self.client.get(reverse("notifications:list"))))

    def test_the_helpers(self) -> None:
        self.assertEqual(plain_text("<p>Eins &amp; zwei</p>"), "Eins & zwei")
        self.assertEqual(str(text_lines("<p>Eins</p>\n<script>x</script>zwei")), "Eins<br>xzwei")
        self.assertEqual(str(text_lines("a < b\nc")), "a &lt; b<br>c")

    def test_the_description_of_a_project_template_alike(self) -> None:
        ProjectTemplate.objects.create(name="Bühne klein", description="Zeile 1\nZeile 2")
        text = self.assert_ok(self.client.get(reverse("projects:templates")))
        self.assertIn('<div class="muted small">Zeile 1<br>Zeile 2</div>', text)
        self.assertNotIn("&lt;p&gt;", text)

    def test_elsewhere_the_text_was_plain_already(self) -> None:
        """The start page names the title only; the API gives the text as it is stored – plain text."""
        home = self.assert_ok(self.client.get(reverse("core:home")))
        self.assertIn("Neue Anfrage", home)
        self.assertNotIn("&lt;p&gt;", home)


# --- 4. Options of the calendar ---------------------------------------------------------------------------------


class CalendarOptionsTests(UiTestCase):
    """VFG-039: Planning → Calendar: "Phasen der Projekte" (on by default) and "Wiedervorlagen" (off by default)."""

    def setUp(self) -> None:
        super().setUp()
        self.customer = make_customer()
        # The test clock stands at Monday, 1 March 2027.
        self.project = make_project("Stadtfest", start=at(2, 8), end=at(4, 18), customer=self.customer)
        ProjectPhase.objects.create(project=self.project, start=at(1, 9), end=at(1, 12))
        set_follow_up(
            self.project,
            on=datetime.date(2027, 3, 3),
            at=datetime.time(14, 30),
            note="Angebot nachfassen",
            by=self.admin_user,
        )
        self.case = service_cases.create_case(
            name="Spot flackert", customer=self.customer, manager=self.admin_user, user=self.admin_user
        )
        set_follow_up(self.case, on=datetime.date(2027, 3, 4), by=self.admin_user)

    def calendar(self, client: Any = None, **query: str) -> str:
        return self.assert_ok((client or self.client).get(reverse("schedule:calendar"), query))

    def test_defaults_and_the_form(self) -> None:
        self.assertEqual(CALENDAR_OPTIONS, {"phases": True, "follow_ups": False})
        text = self.calendar(view="week")
        self.assertIn("wk-event status-confirmed phase", text)
        for mark in ('class="wk-event follow-up', 'class="wk-bar follow-up', 'class="follow-up-mark"'):
            self.assertNotIn(mark, text)
        form = re.search(r'<form method="get" class="calendar-options">.*?</form>', text, re.S).group(0)
        self.assertIn('<legend class="visually-hidden">Im Kalender auch zeigen</legend>', form)
        self.assertIn(
            '<input type="hidden" name="phases" value="0"><label class="check"><input type="checkbox" name="phases" '
            'value="1" checked data-autosubmit> Phasen der Projekte</label>',
            form,
        )
        self.assertIn(
            '<input type="hidden" name="follow_ups" value="0"><label class="check"><input type="checkbox" '
            'name="follow_ups" value="1" data-autosubmit> Wiedervorlagen</label>',
            form,
        )
        self.assertIn('<input type="hidden" name="week" value="2027-03-01">', form)
        self.assertIn("<noscript>", form)  # without scripts the form is sent with a button

    def test_without_phases(self) -> None:
        # What the form sends with the tick box cleared: only the hidden 0.
        for view in ("week", "month"):
            with self.subTest(view=view):
                text = self.calendar(view=view, phases="0")
                self.assertNotIn(' phase"', text)
                self.assertNotIn('class="phase-mark"', text)
        # Remembered for the session; ticked again it shows them.
        self.assertNotIn("wk-event status-confirmed phase", self.calendar(view="week"))
        week = self.client.get(reverse("schedule:calendar") + "?view=week&phases=0&phases=1").content.decode()
        self.assertIn("wk-event status-confirmed phase", week)

    def test_follow_ups_in_the_week(self) -> None:
        text = self.calendar(view="week", follow_ups="1")
        timed = re.search(r'<a class="wk-event follow-up"[^>]*>.*?</a>', text, re.S).group(0)
        # a follow-up opens the project's Überblick – adapted.
        self.assertIn(f'href="{reverse("projects:overview", args=[self.project])}"', timed)
        self.assertIn('<span class="time">Wiedervorlage 14:30</span>', timed)
        self.assertIn(f"{self.project.number} Stadtfest", timed)
        self.assertIn('<span class="meta">Angebot nachfassen</span>', timed)
        self.assertIn("--start: 14.500", timed)
        # Without a time: in the all-day strip of its day, leading to the service case.
        whole_day = re.search(r'<a class="wk-bar follow-up[^"]*"[^>]*>.*?</a>', text, re.S).group(0)
        self.assertIn(f'href="{reverse("projects:case_detail", args=[self.case.pk])}"', whole_day)
        self.assertIn("grid-column: 4 / 5", whole_day)  # Thursday
        self.assertIn('<span class="time">Wiedervorlage</span>', whole_day)
        self.assertIn("Wiedervorlage eines Projekts oder Servicefalls", text)  # the legend
        self.assertIn('name="follow_ups" value="1" checked', text)

    def test_follow_ups_in_the_month_and_remembered(self) -> None:
        self.calendar(view="month", follow_ups="1")
        text = self.calendar(view="month", month="2027-03")  # remembered for the session
        # the project mark opens the Überblick – adapted.
        marks = re.findall(r'<a class="follow-up-mark" href="([^"]+)" title="([^"]+)">([^<]+)</a>', text)
        self.assertEqual(
            [(href, label) for href, _title, label in marks],
            [
                (reverse("projects:overview", args=[self.project]), f"Wiedervorlage 14:30 · {self.project.number}"),
                (reverse("projects:case_detail", args=[self.case.pk]), f"Wiedervorlage · {self.case.number}"),
            ],
        )
        self.assertIn("Angebot nachfassen", marks[0][1])
        self.assertNotIn("follow-up-mark", self.calendar(view="month", month="2027-03", follow_ups="0"))

    def test_rights(self) -> None:
        """Only the follow-ups of projects the user may see; without knowing the customers only the own ones."""
        fritz = make_user("fritz", roles=(ASSIGNED_READER,))  # AUT-036: members, not the customers
        own = make_project("Firmenfeier", start=at(3, 8), end=at(3, 22), customer=self.customer)
        for project in (self.project, own):
            ProjectMembership.objects.create(project=project, user=fritz, level=ProjectAccessLevel.READ)
        set_follow_up(own, on=datetime.date(2027, 3, 2), note="Rückruf", user=fritz, by=self.admin_user)
        hidden = make_project("Messe", start=at(2, 8), end=at(5, 18), customer=self.customer)
        ProjectPhase.objects.create(project=hidden, start=at(1, 13), end=at(1, 15))
        set_follow_up(hidden, on=datetime.date(2027, 3, 2), note="Geheim", by=self.admin_user)
        text = self.calendar(self.browser_of(fritz), view="week", follow_ups="1")
        self.assertIn("Rückruf", text)  # his own follow-up
        self.assertNotIn("Angebot nachfassen", text)  # a follow-up for somebody else in a project he works in
        self.assertNotIn("Geheim", text)
        self.assertNotIn(hidden.number, text)  # neither the project nor its phase
        self.assertNotIn(reverse("projects:case_detail", args=[self.case.pk]), text)
        self.assertEqual(text.count("wk-event status-confirmed phase"), 1)  # the phase of his project
        # Whoever knows the customers of all projects sees every follow-up of them.
        text = self.calendar(self.browser_for("paula", "Projektleitung"), view="week", follow_ups="1")
        for note in ("Rückruf", "Angebot nachfassen", "Geheim"):
            self.assertIn(note, text)
        self.assertIn(reverse("projects:case_detail", args=[self.case.pk]), text)

    def test_crew_sees_the_phases_of_its_deployments(self) -> None:
        """The deployment view (AUT-031) shows the phases in the overview of a project – and in the calendar."""
        carla = make_user("carla", roles=("Crew",))
        plan(self.project, "Tontechnik", make_person("Carla Crew", user=carla, rates={"Tontechnik": "30.00"}))
        text = self.calendar(self.browser_of(carla), view="week", follow_ups="1")
        self.assertIn("wk-event status-confirmed phase", text)
        self.assertNotIn("Angebot nachfassen", text)  # the follow-up is for somebody else
        self.assertNotIn('class="wk-event status-confirmed phase', self.calendar(self.browser_of(carla), phases="0"))
