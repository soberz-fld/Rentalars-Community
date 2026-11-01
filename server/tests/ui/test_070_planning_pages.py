# SPDX-License-Identifier: GPL-3.0-or-later
"""In the pages: planning (VFG-027 to VFG-029), shortages among the open items (PRJ-098), required fields
(UIX-035), the buttons of the mailboxes and the link to the API documentation (UIX-037)."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import connection
from django.test.utils import CaptureQueriesContext

from rentalars.accounts.models import Role
from rentalars.core.demo import create_demo_data
from rentalars.customers.models import Customer
from rentalars.material.models import MaterialItem, MaterialModel
from rentalars.personnel.models import Person
from rentalars.projects.models import CrewLine, OpenItem, Project, ProjectStatus
from rentalars.projects.services import accept_subrental_suggestion
from tests.helpers import ALL_RIGHTS, add_line, at, make_person, make_project, make_stock, plan
from tests.mailbox import add_mailbox
from tests.ui.base import UiTestCase, form_data
from tests.ui.test_accessibility import problems_of


def _tab_names(page: str) -> list[str]:
    tabs = page[page.index('<nav class="tabs" aria-label="Planung">') :]
    return re.findall(r"<a [^>]*>([^<]+)</a>", tabs[: tabs.index("</nav>")])


class PlanningDefaultsTests(UiTestCase):
    """VFG-028: the order of the tabs, the week in the calendar, four days on the timelines."""

    def test_the_tabs_in_their_order(self) -> None:
        page = self.assert_ok(self.client.get("/schedule/timeline/"))
        self.assertEqual(
            _tab_names(page),
            ["Kalender", "Zeitstrahl", "Materialauslastung", "Personalplan", "Fehlbestände", "Wiedervorlagen"],
        )
        products = self.assert_ok(self.client.get("/schedule/products/"))
        self.assertIn("<title>Materialauslastung – Rentalars</title>", products)
        self.assertNotIn(">Auslastung<", products)
        # Without the right to see all projects: no utilization and no shortages, the personnel plan stays; since
        # The follow-ups too, showing only one's own (VFG-034).
        Role.objects.create(
            name="Projektleitung extern", module_levels={"projects": 3, "personnel": 1}, project_scope="assigned"
        )
        limited = self.browser_for("erik", "Projektleitung extern")
        self.assertEqual(
            _tab_names(self.assert_ok(limited.get("/schedule/"))),
            ["Kalender", "Zeitstrahl", "Personalplan", "Wiedervorlagen"],
        )

    def test_the_calendar_opens_with_the_week(self) -> None:
        page = self.assert_ok(self.client.get("/schedule/"))
        self.assertIn("data-week-grid", page)
        week, month = page.index(">Woche</a>"), page.index(">Monat</a>")
        self.assertLess(week, month)
        self.assertIn('<a class="btn secondary small is-active" href="?view=week" aria-current="true">Woche</a>', page)
        # An address that names the month shows the month; the choice of the session still counts.
        self.assertIn('class="month-cal"', self.assert_ok(self.client.get("/schedule/", {"month": "2027-03"})))
        self.assert_ok(self.client.get("/schedule/", {"view": "month"}))
        self.assertIn('class="month-cal"', self.assert_ok(self.client.get("/schedule/")))

    def test_timeline_personnel_plan_and_utilization_open_with_four_days(self) -> None:
        make_stock("L-020", 4, "Moving Head Spot")
        for path in ("/schedule/timeline/", "/schedule/personnel/", "/schedule/products/?q=Moving"):
            with self.subTest(path=path):
                page = self.assert_ok(self.client.get(path))
                # Three-hour columns: four days, two spans before and two after (VFG-033) – 160
                # columns, 32 in view.
                self.assertIn('data-tl-zoom data-focus="64" data-shift="32" data-columns="160"', page)
                self.assertIn('<option value="4" selected>4</option>', page)
                self.assertIn('aria-current="true">Tage</a>', page)

    def test_the_session_keeps_days_or_weeks_as_chosen(self) -> None:
        self.assert_ok(self.client.get("/schedule/timeline/", {"days": "6", "from": "2027-03-10"}))
        page = self.assert_ok(self.client.get("/schedule/personnel/"))
        self.assertIn('<option value="6" selected>6</option>', page)
        weeks = self.assert_ok(self.client.get("/schedule/personnel/", {"weeks": "2", "from": "2027-03-08"}))
        self.assertIn('href="?weeks=2&amp;from=2027-03-08&amp;days=6">Tage</a>', weeks)
        again = self.assert_ok(self.client.get("/schedule/timeline/"))
        self.assertIn('aria-current="true">Wochen</a>', again)
        self.assertNotIn("data-tl-zoom", again)


class UtilizationInHoursPageTests(UiTestCase):
    """VFG-029: the material utilization with the same span as the timeline and the personnel plan."""

    def setUp(self) -> None:
        super().setUp()
        self.spot = make_stock("L-020", 10, "Moving Head Spot")
        self.wash = make_stock("L-021", 6, "Moving Head Wash")
        add_line(make_project("Vortrag", start=at(10, 8), end=at(10, 12)), self.spot, 4)
        add_line(make_project("Messe", start=at(10, 10), end=at(12, 20)), self.wash, 3)

    def test_one_day_in_hour_columns(self) -> None:
        page = self.assert_ok(
            self.client.get(
                "/schedule/products/", {"product": self.spot.pk, "q": "L-020", "days": "1", "from": "2027-03-10"}
            )
        )
        self.assertIn("is-hourly", page)
        self.assertIn('title="Mi 10.03., 08:00–09:00">08</div>', page)
        self.assertIn(
            '<div class="tl-load used" style="grid-column: 57 / 61" title="Mi 10.03. 08:00–12:00: 4 von 10 fest '
            'reserviert, 0 als Option"><span class="tl-text">4</span></div>',
            page,
        )
        # The control of the span, as on the timeline; moving on keeps the product.
        self.assertIn('<select id="f-days" name="days" data-autosubmit>', page)
        self.assertIn(f'data-later-url="?product={self.spot.pk}&amp;q=L-020&amp;days=1&amp;from=2027-03-11"', page)
        # VFG-025: the suggestions stay; the span goes along with a search or a category.
        self.assertIn('<div class="typeahead" data-typeahead data-url="/products/suggest/', page)
        self.assertIn('<input type="hidden" name="days" value="1" form="f-search">', page)
        self.assertIn('<input type="hidden" name="from" value="2027-03-10" form="f-by-category">', page)
        self.assertEqual(problems_of(page), [])

    def test_weeks_of_days_as_before(self) -> None:
        page = self.assert_ok(
            self.client.get("/schedule/products/", {"q": "Moving", "weeks": "1", "from": "2027-03-08"})
        )
        self.assertNotIn("is-hourly", page)
        self.assertEqual(page.count('<div class="tl-load '), 14)  # two products, seven days
        self.assertIn('title="Mi 10.03.: 4 von 10 fest reserviert, 0 als Option">4</div>', page)
        self.assertIn('<input type="hidden" name="weeks" value="1" form="f-search">', page)

    def test_as_many_queries_for_ten_days_in_hours_as_for_two_weeks(self) -> None:
        def queries(**query: str) -> int:
            with CaptureQueriesContext(connection) as captured:
                self.assert_ok(self.client.get("/schedule/products/", {"q": "Moving", "from": "2027-03-08", **query}))
            return len(captured)

        queries(weeks="2")  # the first visit of the session writes the choice
        weeks = queries(weeks="2")
        queries(days="10")
        self.assertEqual(queries(days="10"), weeks)


class DeploymentColoursPageTests(UiTestCase):
    """VFG-027: the bars of the personnel plan and their legend, larger and in colour."""

    def test_bars_and_legend(self) -> None:
        anna = make_person("Anna Becker", rates={"Lichttechnik": "35.00"})
        inquiry = make_project("Hochzeit", start=at(10, 8), end=at(10, 22), status=ProjectStatus.INQUIRY)
        plan(inquiry, "Lichttechnik", anna, start=at(10, 8), end=at(10, 20))
        line = plan(make_project("Stadtfest"), "Lichttechnik", anna, start=at(11, 8), end=at(11, 20))
        CrewLine.objects.filter(pk=line.pk).update(request_status="requested")
        page = self.assert_ok(self.client.get("/schedule/personnel/", {"weeks": "1", "from": "2027-03-08"}))
        self.assertIn('<a class="tl-bar crew status-inquiry" style="grid-column: 3 / 4;', page)
        self.assertIn('<a class="tl-bar crew status-confirmed requested" style="grid-column: 4 / 5;', page)
        self.assertIn(
            '<span class="tl-bar legend crew status-confirmed">fest</span> <span class="tl-bar legend crew '
            'status-option">Option</span> <span class="tl-bar legend crew status-inquiry">Projekt-Anfrage</span> '
            '<span class="tl-bar legend crew status-confirmed requested">angefragt</span>',
            page,
        )
        timeline = self.assert_ok(self.client.get(f"/personnel/people/{anna.pk}/timeline/", {"from": "2027-03-08"}))
        self.assertIn('class="tl-bar crew status-inquiry"', timeline)
        self.assertIn('<span class="tl-bar legend crew status-inquiry">Projekt-Anfrage</span>', timeline)

    def test_the_style_sheet_fills_the_bars(self) -> None:
        text = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(encoding="utf-8")
        self.assertIn(
            "background: color-mix(in srgb, var(--status) 30%, var(--surface-raised)); border-left-width: 6px", text
        )
        self.assertIn(".tl-bar.crew { --status: var(--accent); }", text)
        self.assertIn(".tl-bar.crew.status-option { --status: var(--yellow); }", text)
        self.assertIn(".tl-bar.crew.status-inquiry { --status: var(--line-strong); }", text)


class OpenShortagesPageTests(UiTestCase):
    """PRJ-098: the shortages not resolved yet among the open items, as further points of their project."""

    def setUp(self) -> None:
        super().setUp()
        self.spot = make_stock("L-020", 2, "Moving Head Spot")
        self.festival = make_project("Stadtfest", start=at(10, 8), end=at(12, 22), status=ProjectStatus.CONFIRMED_OPEN)
        OpenItem.objects.create(project=self.festival, text="Stromanschluss klären")
        self.short_line = add_line(self.festival, self.spot, 4).line
        self.gala = make_project("Gala", start=at(20, 8), end=at(21, 22))
        self.gala_line = add_line(self.gala, self.spot, 6).line
        accept_subrental_suggestion(self.gala_line, self.spot, 2, rights=ALL_RIGHTS)

    def test_shortages_are_further_points(self) -> None:
        page = self.assert_ok(self.client.get("/projects/open-items/"))
        self.assertIn("<div>• Stromanschluss klären</div>", page)
        self.assertIn(
            f'<div class="open-shortage">• <a href="/projects/{self.festival.number}/#line-{self.short_line.pk}">'
            "Fehlbestand: 2 × Moving Head Spot</a></div>",
            page,
        )
        # A project with a shortage only is listed as well; the subrented part is named.
        self.assertIn(f"{self.gala.number} Gala", page)
        self.assertIn(
            f'<a href="/projects/{self.gala.number}/#line-{self.gala_line.pk}">Fehlbestand: 4 × Moving Head Spot '
            "(2 zugemietet, 2 offen)</a>",
            page,
        )
        self.assertLess(page.index("Stadtfest"), page.index("Gala"))
        self.assertNotIn("noch nichts notiert", page)
        self.assertEqual(problems_of(page), [])
        # The link leads to the line: the row carries the anchor.
        planning = self.assert_ok(self.client.get(f"/projects/{self.festival.number}/"))
        self.assertIn(f'<tr data-line="{self.short_line.pk}" id="line-{self.short_line.pk}"', planning)

    def test_only_for_who_may_read_the_planning(self) -> None:
        Role.objects.create(name="Projektleitung extern", module_levels={"projects": 3}, project_scope="assigned")
        browser = self.browser_for("erik", "Projektleitung extern")
        page = self.assert_ok(browser.get("/projects/open-items/"))
        self.assertNotIn("Fehlbestand", page)
        self.assertNotIn("Gala", page)

    def test_projects_without_shortages_add_no_queries(self) -> None:
        def queries() -> int:
            with CaptureQueriesContext(connection) as captured:
                self.assert_ok(self.client.get("/projects/open-items/"))
            return len(captured)

        before = queries()
        for number in range(5):
            project = make_project(f"Projekt {number}", start=at(14, 8), end=at(14, 22))
            OpenItem.objects.create(project=project, text="Technik klären")
            add_line(project, make_stock(f"K-{number:03d}", 10), 1)
        self.assertEqual(queries(), before)


VOID = {"input", "br", "img", "meta", "link", "hr", "source", "col", "wbr", "area", "base", "embed", "param", "track"}


class _Forms(HTMLParser):
    """The forms of a page that are sent with POST: their fields, the labels of the fields and their notes."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[dict[str, Any]] = []
        self.labels: dict[str, dict[str, Any]] = {}
        self.form: dict[str, Any] | None = None
        self.label: dict[str, Any] | None = None
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name: value or "" for name, value in attrs}
        classes = attributes.get("class", "").split()
        if tag == "form":
            self.form = {"method": attributes.get("method", "get"), "action": attributes.get("action", ""), "notes": 0}
            self.form["fields"] = []
            self.forms.append(self.form)
        if "required-note" in classes and self.form is not None:
            self.form["notes"] += 1
        if tag == "label":
            self.label = {"marked": False}
            if attributes.get("for"):
                self.labels[attributes["for"]] = self.label
        if tag == "span" and "required" in classes and self.label is not None:
            self.label["marked"] = True
            self.label["hidden_from_readers"] = attributes.get("aria-hidden") == "true"
        if tag in {"input", "select", "textarea"} and self.form is not None:
            kind = attributes.get("type", "text") if tag == "input" else tag
            if kind not in {"hidden", "submit", "button", "reset", "image", "checkbox", "radio"}:
                self.form["fields"].append(
                    {
                        "id": attributes.get("id", ""),
                        "name": attributes.get("name", ""),
                        "required": "required" in attributes
                        or attributes.get("aria-required") == "true"
                        or bool(attributes.get("data-require-if")),
                    }
                )
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self.form = None
        if tag == "label":
            self.label = None


def required_problems(page: str) -> list[str]:
    """UIX-035: required fields without asterisk, asterisks the field does not tell, forms without the note."""
    parser = _Forms()
    parser.feed(page)
    problems = []
    for form in parser.forms:
        if form["method"].lower() != "post":
            continue
        marked = 0
        for field in form["fields"]:
            label = parser.labels.get(field["id"], {})
            if label.get("marked"):
                marked += 1
                if not label.get("hidden_from_readers"):
                    problems.append(f"{field['name']}: the asterisk is read out")
            if field["required"] and not label.get("marked"):
                problems.append(f"{field['name']}: required without asterisk")
        if marked and form["notes"] != 1:
            problems.append(f"form {form['action']}: {form['notes']} notes on the asterisk")
    return problems


class RequiredFieldsPageTests(UiTestCase):
    """UIX-035: every required field is marked, the asterisk explained once per form."""

    def test_the_price_of_a_new_product(self) -> None:
        page = self.assert_ok(self.client.get("/products/new/"))
        self.assertEqual(
            page.count('<p class="required-note" aria-hidden="true"><span class="required">*</span> Pflichtfeld</p>'), 1
        )
        # LOG-005: a trailer billed per day needs its day price as well.
        required_if = "kind=rental|kit|surcharge|subrental|incidental;kind=vehicle&amp;vehicle_type=trailer&amp;trailer_billing=day"
        self.assertIn(
            f'Preis (netto) <span class="required" aria-hidden="true" data-show-if="{required_if}">*</span></label>',
            page,
        )
        self.assertIn(f'data-require-if="{required_if}"', page)
        # The sale price is required for sale products only: the asterisk waits for that choice.
        self.assertIn('<span class="required hidden" aria-hidden="true" data-show-if="kind=sale">*</span>', page)
        sale = self.assert_ok(self.client.post("/products/new/", {"kind": "sale", "name": "Gaffa"}))
        self.assertIn('<span class="required" aria-hidden="true" data-show-if="kind=sale">*</span>', sale)

    def test_the_rules_stay(self) -> None:
        page = self.client.get("/products/new/")
        data = form_data(page, name="Nebelmaschine", kind="rental", price="")
        answer = self.assert_ok(self.client.post("/products/new/", data))
        # PRD-047: a rental product needs its price – a sale price is no longer an option.
        self.assertIn('id="id_price_error"><li>Gib den Preis an.', answer)

    def test_the_customer_of_a_project(self) -> None:
        page = self.assert_ok(self.client.get("/projects/new/"))
        self.assertIn('<span class="required" aria-hidden="true" data-show-if="is_internal=">*</span>', page)
        self.assertRegex(page, r'<input type="search" id="id_customer_text"[^>]*data-require-if="is_internal="')

    def test_the_mailbox(self) -> None:
        page = self.assert_ok(self.client.get("/administration/mail/mailboxes/new/"))
        self.assertIn('data-show-if="is_active=on&amp;for_correspondence=on">*</span>', page)
        self.assertIn('data-show-if="is_active=on&amp;is_outgoing=on;is_active=on&amp;for_system=on">*</span>', page)
        self.assertIn('data-show-if="for_correspondence=on&amp;after_assignment=move">*</span>', page)

    def test_every_form_marks_its_required_fields(self) -> None:
        create_demo_data()
        project = Project.objects.get(name="Stadtfest Hauptbühne")
        item = MaterialItem.objects.first()
        model = MaterialModel.objects.first()
        person = Person.objects.exclude(user=self.admin_user).first()
        customer = Customer.objects.first()
        product = project.material_lines.filter(product__isnull=False).first().product
        add_mailbox("Projekte", "projekte@verleih.example")
        paths = [
            "/projects/new/",
            f"/projects/{project.pk}/edit/",
            f"/projects/{project.pk}/",
            f"/projects/{project.pk}/lines/{project.material_lines.first().pk}/",
            f"/projects/{project.pk}/phases/new/",
            f"/projects/{project.pk}/course/",
            f"/projects/{project.pk}/subprojects/new/",
            f"/projects/{project.pk}/save-as-template/",
            f"/projects/{project.pk}/mvr/",
            f"/projects/{project.pk}/documents/",
            f"/projects/{project.pk}/mails/new/",
            f"/projects/{project.pk}/members/",
            "/products/new/",
            f"/products/{product.pk}/edit/",
            "/administration/scales/new/",
            "/material/models/new/",
            f"/material/models/{model.pk}/edit/",
            f"/material/models/{model.pk}/items/new/",
            f"/material/items/{item.pk}/edit/",
            f"/material/items/{item.pk}/",
            "/customers/new/",
            f"/customers/{customer.pk}/edit/",
            f"/customers/{customer.pk}/contacts/new/",
            f"/customers/{customer.pk}/addresses/new/",
            "/customers/venues/new/",
            "/personnel/functions/new/",
            "/personnel/people/new/",
            f"/personnel/people/{person.pk}/edit/",
            f"/personnel/people/{person.pk}/qualifications/new/",
            f"/personnel/people/{person.pk}/",
            f"/personnel/people/{person.pk}/availability/",
            "/me/",
            "/administration/settings/",
            "/administration/users/new/",
            "/administration/roles/new/",
            "/administration/mail/",
            "/administration/mail/mailboxes/new/",
            "/administration/webhooks/new/",
            "/administration/accounting/",
            "/account/",
            "/import/customers/",
            "/material/",
            "/me/availability/",
            f"/projects/{project.pk}/phases/new/dialog/",
            f"/projects/{project.pk}/crew/{project.crew_lines.first().pk}/",
            "/times/quick/",
        ]
        # Dialogs that the page loads in the background.
        dialogs = {
            f"/projects/{project.pk}/phases/new/dialog/",
            f"/projects/{project.pk}/crew/{project.crew_lines.first().pk}/",
            "/times/quick/",
        }
        found = []
        for path in paths:
            page = self.assert_ok(self.client.get(path, **({"HTTP_HX_REQUEST": "true"} if path in dialogs else {})))
            found += [f"{path}: {problem}" for problem in required_problems(page)]
        self.assertEqual(found, [], "\n".join(found))


class SmallThingsPageTests(UiTestCase):
    """The buttons of a mailbox side by side; UIX-037: the API documentation in a tab of its own."""

    def test_the_buttons_of_a_mailbox_share_a_row(self) -> None:
        add_mailbox("Projekte", "projekte@verleih.example")
        page = self.assert_ok(self.client.get("/administration/mail/"))
        self.assertRegex(
            page, r'<div class="cell-buttons">\s*<form method="post" action="[^"]+/check/" class="inline-form">'
        )

    def test_the_api_documentation_opens_in_a_new_tab(self) -> None:
        for path in ("/administration/", "/administration/webhooks/"):
            with self.subTest(path=path):
                page = self.assert_ok(self.client.get(path))
                self.assertRegex(
                    page, r'<a [^>]*href="/api/v1/docs/?" target="_blank" rel="noopener"[^>]*>API-Dokumentation</a>'
                )
