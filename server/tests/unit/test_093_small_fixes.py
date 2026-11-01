# SPDX-License-Identifier: GPL-3.0-or-later
"""Small faults found while building, outside the wishes (NFA-025, PER-023, PRD-050, PCK-005, MAT-070).

* the help text of a form field is named by its ``aria-describedby`` (``tests/unit/test_093_aria.py`` crawls
  every page; here the shared field template);
* the subscription link of a person writes its refresh time as a duration ("PT30M"), which calendar programs read;
* a product page names a sale "verkauft" instead of a date in the year 9000;
* the page margin of a PDF prints "&" in a project name as "&", not as "u0026".
"""

from __future__ import annotations

import io
import re

from django.template import Context, Template
from django.urls import reverse

from rentalars.personnel import calendars
from rentalars.products.models import ProductKind
from tests.helpers import add_line, make_items, make_model, make_person, make_product, make_project
from tests.ui.base import UiTestCase


class HelpTextTests(UiTestCase):
    """NFA-025: Django's ``aria-describedby="<id>_helptext"`` finds the help of the shared field template."""

    def test_the_help_carries_the_id_the_field_names(self) -> None:
        page = self.assert_ok(self.client.get(reverse("customers:create")))
        names = re.findall(r'aria-describedby="([^"]+)"', page)
        self.assertTrue(names)
        for name in " ".join(names).split():
            self.assertIn(f'id="{name}"', page)


class FeedTests(UiTestCase):
    """PER-023: the refresh time of a person's calendar is a duration."""

    def test_the_published_ttl_is_a_duration(self) -> None:
        anna = make_person("Anna Becker")
        token = calendars.renew_calendar_token(anna)
        response = self.client.get(f"/calendar-feed/{anna.pk}/{token}.ics")
        self.assertEqual(response.status_code, 200)
        text = response.content.decode()
        self.assertIn("X-PUBLISHED-TTL:PT30M", text)
        self.assertNotIn("0:30:00", text)


class SoldTests(UiTestCase):
    """PRD-050: a sold piece is "verkauft" on the product page – its demand ends in the year 9000."""

    def test_the_sale_is_named(self) -> None:
        product = make_product("V-001", "Gaffa-Band", price=None, kind=ProductKind.SALE, sale_price="12.00")
        make_items(make_model("Gaffa", product), 5)
        add_line(make_project("Stadtfest"), product, 2, is_sale=True)
        page = self.assert_ok(self.client.get(reverse("products:detail", args=[product.pk])))
        self.assertRegex(page, r"\d\d\.\d\d\. \d\d:\d\d – verkauft</td>")
        self.assertNotIn("– 01.01. 01:00", page)  # the year 9000


class CssStringTests(UiTestCase):
    """PCK-005: text in a CSS string of a PDF – the footer of the packing list."""

    def test_the_filter(self) -> None:
        rendered = Template('{% load rentalars %}"{{ text|css_string }}"').render(
            Context({"text": 'Müller & Söhne "X" \\ <b>'})
        )
        self.assertEqual(rendered, '"Müller \\26  Söhne \\22 X\\22  \\5c  \\3c b\\3e "')

    def test_the_packing_list_prints_the_ampersand(self) -> None:
        from pypdf import PdfReader

        project = make_project("Licht & Ton")
        response = self.client.get(reverse("packing:pdf", args=[project.pk]))
        self.assertEqual(response.status_code, 200)
        content = b"".join(response.streaming_content) if hasattr(response, "streaming_content") else response.content
        text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(content)).pages)
        self.assertIn("Licht & Ton", text)
        self.assertNotIn("u0026", text)


class DueCountTests(UiTestCase):
    """MAT-070: the count of due audits for the tab "Offene Punkte" equals the list of due items."""

    def test_the_count_equals_the_list(self) -> None:
        import datetime

        from django.utils import timezone

        from rentalars.material import audits
        from rentalars.material.audit_models import ItemAudit
        from rentalars.material.models import MaterialItem

        items = make_items(make_model("Stativ"), 6)
        old = timezone.now() - datetime.timedelta(days=3 * 365)
        MaterialItem.objects.filter(pk__in=[item.pk for item in items[:4]]).update(created_at=old)
        ItemAudit.objects.create(item=items[0], audited_at=old)  # audited long ago: due
        ItemAudit.objects.create(item=items[1], audited_at=old)
        ItemAudit.objects.create(item=items[1], audited_at=timezone.now())  # audited again since: not due
        ItemAudit.objects.create(item=items[4], audited_at=timezone.now())  # new and audited: not due
        # items[2], items[3]: old, never audited – due; items[5]: new, never audited – not due.
        self.assertEqual(audits.due_count(), audits.due_items().count())
        self.assertEqual(audits.due_count(), 3)
        settings_row = audits.audit_settings()
        settings_row.interval_months = 0
        self.assertEqual(audits.due_count(settings_row=settings_row), 0)
