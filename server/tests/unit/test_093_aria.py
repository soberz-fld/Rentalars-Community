# SPDX-License-Identifier: GPL-3.0-or-later
"""Every ``aria-describedby`` and ``aria-labelledby`` names an element that is on the page (NFA-025).

Found while building the electrical inspection (MAT-078): Django 5 points ``aria-describedby`` of a field with a help
text to ``<id>_helptext``, while the shared field template gave the help the id ``<id>_help`` – a screen reader
heard no help text in any form. The crawl of an administrator's pages (as in ``test_092_ui``) now checks every
reference of this kind, in pages and in dialogs.
"""

from __future__ import annotations

import collections
import re

from django.urls import reverse

from tests.ui.base import UiTestCase
from tests.unit.test_092_ui import SKIP, RequiredMarksTests

#: The attributes whose value is a list of ids on the same page.
REFERENCES = re.compile(r'\saria-(describedby|labelledby)="([^"]*)"')
IDS = re.compile(r'\sid="([^"]+)"')


def missing_references(html: str) -> list[str]:
    """The ids that an ``aria-describedby`` or ``aria-labelledby`` of the page names but no element has."""
    known = set(IDS.findall(html))
    missing = []
    for attribute, value in REFERENCES.findall(html):
        missing.extend(f"aria-{attribute} → {name}" for name in value.split() if name not in known)
    return sorted(set(missing))


class AriaReferenceTests(UiTestCase):
    """NFA-025: the crawl of ``RequiredMarksTests`` over pages and dialogs, checking the aria references."""

    LIMIT = RequiredMarksTests.LIMIT
    business_data = RequiredMarksTests.business_data

    def test_every_reference_names_an_element_of_the_page(self) -> None:
        self.business_data()
        self.client.raise_request_exception = False  # a broken page is the business of other tests
        queue = collections.deque([reverse("core:home")])
        seen: set[str] = set()
        problems: dict[str, list[str]] = {}
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
            for prefix, pattern in (("", r'href="(/[^"#]*)"'), ("hx:", r'hx-get="(/[^"#]*)"')):
                for address in re.findall(pattern, html):
                    address = prefix + address.replace("&amp;", "&")
                    if address not in seen and not SKIP.search(address):
                        queue.append(address)
            found = missing_references(html)
            if found:
                problems[url] = found
        self.assertGreater(len(seen), 300)
        self.maxDiff = None
        self.assertEqual(problems, {}, f"references to missing elements ({len(seen)} pages read)")

    def test_the_checker(self) -> None:
        html = '<input aria-describedby="a_helptext a_error"><div id="a_helptext"></div>'
        self.assertEqual(missing_references(html), ["aria-describedby → a_error"])
        self.assertEqual(missing_references('<p id="x"></p><b aria-labelledby="x"></b>'), [])
