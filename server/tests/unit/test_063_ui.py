# SPDX-License-Identifier: GPL-3.0-or-later
"""The tag that folds filters away (UIX-030), the credit (UIX-031) and the company name of the menu (UIX-032)."""

from __future__ import annotations

from django.contrib.auth.models import AnonymousUser
from django.template import Context, Template, TemplateSyntaxError
from django.test import RequestFactory

from rentalars import CREDIT_NAME, CREDIT_URL
from rentalars.accounts.backends import EmailOrUsernameBackend
from rentalars.core.context_processors import _company_name, application
from rentalars.core.models import CompanyProfile, end_request_cache, start_request_cache
from tests.helpers import RentalarsTestCase, make_user


class FilterPanelTagTests(RentalarsTestCase):
    """UIX-030: {% filterpanel %} – the button, the summary and the fields in one pattern."""

    def render(self, source: str, **context: object) -> str:
        return Template("{% load rentalars %}" + source).render(Context(context))

    def test_button_summary_and_fields(self) -> None:
        html = self.render(
            '{% filterpanel key %}<select name="status"><option value="">{{ all }}</option></select>{% endfilterpanel %}',
            key="projects",
            all="All & more",
        )
        self.assertIn('data-filter-toggle="projects"', html)
        self.assertIn('aria-controls="filter-panel-projects"', html)
        self.assertIn('aria-describedby="filter-summary-projects"', html)
        self.assertIn(
            '<span class="filter-summary" id="filter-summary-projects" data-filter-summary hidden></span>', html
        )
        self.assertIn(
            '<div class="filter-panel" id="filter-panel-projects" data-filter-panel><select name="status">'
            '<option value="">All &amp; more</option></select></div>',
            html,
        )
        self.assertRegex(html, r'<use href="/static/img/icons\.svg[^"#]*#filter">')
        self.assertLess(html.index("data-filter-toggle"), html.index("data-filter-summary"))
        self.assertLess(html.index("data-filter-summary"), html.index("data-filter-panel"))

    def test_the_context_stays_as_it_was(self) -> None:
        html = self.render('{% filterpanel "a" %}{{ key }}{% endfilterpanel %}{{ filter_key }}|{{ key }}', key="k")
        self.assertIn("data-filter-panel>k</div>", html)
        self.assertTrue(html.endswith("|k"))

    def test_the_key_is_required(self) -> None:
        with self.assertRaises(TemplateSyntaxError):
            Template("{% load rentalars %}{% filterpanel %}{% endfilterpanel %}")


class CompanyNameTests(RentalarsTestCase):
    """UIX-032: the user of a session brings the company name along – no query of its own, never out of date."""

    def name_company(self, name: str) -> None:
        company = CompanyProfile.load()
        company.name = name
        company.save()

    def test_in_the_query_of_the_user(self) -> None:
        user = make_user("ida")
        self.name_company("Lichtwerk GmbH")
        with self.assertNumQueries(1):
            loaded = EmailOrUsernameBackend().get_user(user.pk)
            self.assertEqual(loaded.menu_company_name, "Lichtwerk GmbH")
            self.assertTrue(hasattr(loaded, "_person_cache"))  # the person still comes along
        self.name_company("Tonwerk GmbH")
        self.assertEqual(EmailOrUsernameBackend().get_user(user.pk).menu_company_name, "Tonwerk GmbH")

    def test_context_takes_it_from_the_user(self) -> None:
        self.name_company("Lichtwerk & Ton GmbH")
        request = RequestFactory().get("/")
        request.user = EmailOrUsernameBackend().get_user(make_user("ida", superuser=True).pk)
        request.session = {}
        with self.assertNumQueries(0):
            self.assertEqual(_company_name(request), "Lichtwerk & Ton GmbH")

    def test_a_user_that_came_another_way_reads_it_once_when_shown(self) -> None:
        self.name_company("Lichtwerk GmbH")
        request = RequestFactory().get("/")
        request.user = make_user("ida", superuser=True)
        token = start_request_cache()
        try:
            with self.assertNumQueries(0):
                name = _company_name(request)
            with self.assertNumQueries(1):
                self.assertEqual(str(name), "Lichtwerk GmbH")
            with self.assertNumQueries(0):
                self.assertEqual(str(_company_name(request)), "Lichtwerk GmbH")
        finally:
            end_request_cache(token)


class CreditContextTests(RentalarsTestCase):
    """UIX-031: the credit in the values every template gets, with and without login."""

    def test_credit_for_everybody(self) -> None:
        request = RequestFactory().get("/login/")
        request.user = AnonymousUser()
        values = application(request)
        self.assertEqual(values["rentalars_credit"], {"name": CREDIT_NAME, "url": CREDIT_URL})
        self.assertNotIn("company_name", values)
        request.user = make_user("ida", superuser=True)
        request.session = {}
        self.assertEqual(application(request)["rentalars_credit"], {"name": CREDIT_NAME, "url": CREDIT_URL})
