# SPDX-License-Identifier: GPL-3.0-or-later
"""NFA-025: rules of WCAG 2.1 that can be read off the HTML of every main page.

This test runs with every test run, without a browser. It checks what a
screen reader needs and the HTML alone shows: a language for the page, a
name for every field, button, link and progress bar, a text alternative for
every image, IDs that occur once, one main heading. The full check with axe-core in a browser,
including colour contrast, is ``tests/browser/test_accessibility_in_browser``.
"""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any

from rentalars.core.demo import create_demo_data
from rentalars.customers.models import Customer
from rentalars.material.models import MaterialItem
from rentalars.personnel.models import Person
from rentalars.projects.models import Project
from tests.ui.base import UiTestCase

#: Elements whose name comes from their content.
NAMED_BY_CONTENT = {"a", "button"}
FIELDS = {"input", "select", "textarea"}
NO_LABEL_NEEDED = {"hidden", "submit", "button", "reset", "image"}


class _Checker(HTMLParser):
    """Collects what a page lacks for assistive technology."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.problems: list[str] = []
        self.ids: dict[str, int] = {}
        self.label_targets: set[str] = set()
        self.fields: list[tuple[str, str]] = []
        self.lang = ""
        self.h1 = 0
        #: Open elements that need a name from their content: [tag, attributes, text so far].
        self.open: list[list[Any]] = []
        self.label_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name: value or "" for name, value in attrs}
        if tag == "html":
            self.lang = attributes.get("lang", "")
        if tag == "h1":
            self.h1 += 1
        if "id" in attributes:
            self.ids[attributes["id"]] = self.ids.get(attributes["id"], 0) + 1
        if tag == "label":
            self.label_depth += 1
            if attributes.get("for"):
                self.label_targets.add(attributes["for"])
        if tag == "img" and "alt" not in attributes:
            self.problems.append(f"image without alt: {attributes.get('src', '')}")
        if attributes.get("role") == "progressbar" and not _has_name(attributes):
            self.problems.append("progress bar without a name")
        if tag in FIELDS and attributes.get("type", "text") not in NO_LABEL_NEEDED:
            if not _has_name(attributes) and self.label_depth == 0:
                self.fields.append((attributes.get("id", ""), attributes.get("name", "")))
        if tag in NAMED_BY_CONTENT:
            self.open.append([tag, attributes, ""])
        if tag == "svg" and self.open and attributes.get("aria-hidden") != "true":
            self.open[-1][2] += "svg"

    def handle_endtag(self, tag: str) -> None:
        if tag == "label":
            self.label_depth = max(0, self.label_depth - 1)
        if tag in NAMED_BY_CONTENT and self.open and self.open[-1][0] == tag:
            _tag, attributes, text = self.open.pop()
            if not text.strip() and not _has_name(attributes) and attributes.get("aria-hidden") != "true":
                described = attributes.get("href") or attributes.get("class") or attributes.get("name", "")
                self.problems.append(f"{tag} without a name: {described}")

    def handle_data(self, data: str) -> None:
        for entry in self.open:
            entry[2] += data

    def result(self) -> list[str]:
        problems = list(self.problems)
        if not self.lang:
            problems.append("the page has no language (lang)")
        if self.h1 != 1:
            problems.append(f"{self.h1} main headings (h1) instead of one")
        problems += [f"ID used {count} times: {key}" for key, count in self.ids.items() if count > 1]
        problems += [
            f"field without a label: {name or field_id}"
            for field_id, name in self.fields
            if not field_id or field_id not in self.label_targets
        ]
        return problems


def _has_name(attributes: dict[str, str]) -> bool:
    return bool(attributes.get("aria-label") or attributes.get("aria-labelledby") or attributes.get("title"))


def problems_of(html: str) -> list[str]:
    """What the page lacks."""
    checker = _Checker()
    checker.feed(html)
    checker.close()
    return checker.result()


class AccessibilityTests(UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        create_demo_data()

    def pages(self) -> list[str]:
        project = Project.objects.get(name="Stadtfest Hauptbühne").pk
        item = MaterialItem.objects.filter(material_model__default_product__isnull=False).first()
        product = item.material_model.default_product.pk
        person = Person.objects.first().pk
        customer = Customer.objects.first().pk
        return [
            "/",
            "/projects/",
            "/projects/new/",
            f"/projects/{project}/",
            f"/projects/{project}/edit/",
            f"/projects/{project}/deployment/",
            f"/projects/{project}/packlist/",
            f"/projects/{project}/prices/",
            f"/projects/{project}/documents/",
            f"/projects/{project}/course/",
            f"/projects/{project}/mails/new/",
            "/schedule/?view=month",
            "/schedule/?view=week",
            "/schedule/timeline/",
            "/schedule/personnel/",
            "/products/",
            "/products/new/",
            f"/products/{product}/",
            f"/products/{product}/timeline/",
            "/material/",
            "/material/models/",
            f"/material/items/{item.pk}/",
            f"/material/items/{item.pk}/edit/",
            f"/material/items/{item.pk}/timeline/",
            "/material/inspections/",
            "/material/import/",
            "/customers/",
            "/customers/new/",
            f"/customers/{customer}/",
            "/personnel/",
            "/personnel/people/new/",
            f"/personnel/people/{person}/qualifications/new/",
            f"/personnel/people/{person}/",
            f"/personnel/people/{person}/timeline/",
            "/times/",
            "/times/approval/",
            "/times/report/",
            "/notifications/",
            "/administration/",
            "/administration/settings/",
            "/administration/number-ranges/",
            "/import/customers/",
            "/account/",
            "/search/?q=PAR",
        ]

    def test_main_pages(self) -> None:
        found = []
        for path in self.pages():
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            found += [f"{path}: {problem}" for problem in problems_of(response.content.decode())]
        self.assertEqual(found, [], "\n".join(found))

    def test_login_page(self) -> None:
        self.client.logout()
        self.assertEqual(problems_of(self.client.get("/login/").content.decode()), [])

    def test_the_checker_finds_what_it_looks_for(self) -> None:
        page = (
            '<html><body><h1>A</h1><img src="x.png"><input name="q"><button><svg aria-hidden="true"></svg></button>'
            '<a href="/x"></a><div id="a"></div><div id="a"></div><div role="progressbar"></div></body></html>'
        )
        self.assertEqual(len(problems_of(page)), 7)
