# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages for the project numbers without "P-" (ADM-014): setup, old addresses, searches, forms."""

from __future__ import annotations

from django.db import connection
from django.db.models import F, Value
from django.db.models.functions import Concat
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from rentalars.core.middleware import SetupRequiredMiddleware
from rentalars.core.models import NumberRange, NumberRangeKey, SystemSettings
from rentalars.mail.fetching import fetch_mail
from rentalars.mail.models import ProjectMail, UnknownTagMail
from rentalars.projects.models import Project, ProjectStatus
from tests.helpers import add_group, make_project
from tests.mailbox import configure_mailbox, mailbox, make_mail
from tests.ui.base import UiTestCase, form_data
from tests.ui.test_setup_and_login import SETUP_ANSWERS
from tests.unit.test_070_numbers import HistoryMixin


class SetupPageTests(UiTestCase):
    """ADM-014: the first-run setup proposes {year}- again."""

    def test_the_setup_proposes_the_year_and_new_projects_get_it(self) -> None:
        system_settings = SystemSettings.load()
        system_settings.setup_completed = False
        system_settings.save()
        SetupRequiredMiddleware.reset()
        self.addCleanup(SetupRequiredMiddleware.reset)
        self.client.logout()
        token = system_settings.new_setup_token()
        page = self.client.get(reverse("core:setup"), {"token": token})
        text = self.assert_ok(page)
        self.assertIn('value="{year}-"', text)
        self.assertIn("wird durch das laufende Jahr ersetzt: 2026-0001.", text)
        self.assertNotIn("P-2026", text)
        self.client.post(reverse("core:setup"), form_data(page, **SETUP_ANSWERS))
        self.assertTrue(SystemSettings.load().setup_completed)
        self.assertEqual(NumberRange.objects.get(key=NumberRangeKey.PROJECT).prefix, "{year}-")
        self.assertEqual(make_project().number, "2027-0001")

    def test_the_number_ranges_show_the_next_number_without_p(self) -> None:
        page = self.assert_ok(self.client.get(reverse("core:number_ranges")))
        self.assertIn("<strong>2027-0001</strong>", page)

    def test_the_examples_of_the_mail_tag_have_no_p(self) -> None:
        page = self.assert_ok(self.client.get(reverse("core:company_settings")))
        self.assertIn("Die Kennung lautet mit dem Präfix RL [RL#2026-0042].", page)
        self.assertNotIn("P-2026", page)
        configure_mailbox()
        self.assertIn("[RL#2026-0042]", self.assert_ok(self.client.get("/projects/inquiries/")))


class OldAddressTests(HistoryMixin, UiTestCase):
    """ADM-014: /projects/P-2027-0001/ – printed or bookmarked earlier – leads to the address of today."""

    def setUp(self) -> None:
        super().setUp()
        self.whole, self.part, self.other, self.newer, self.newer_part = self.history()

    def test_addresses_with_p_redirect_permanently(self) -> None:
        for old, new in (
            ("/projects/P-2027-0001/", "/projects/2027-0001/"),
            ("/projects/P-2027-0001-1/", "/projects/2027-0001-1/"),
            ("/projects/P-2027-0002/prices/?tab=1", "/projects/2027-0002/prices/?tab=1"),
            ("/projects/P-2027-0003/", "/projects/2027-0003/"),
            ("/projects/p-2027-0003-1/", "/projects/2027-0003-1/"),
        ):
            with self.subTest(old=old):
                response = self.client.get(old)
                self.assertEqual(response.status_code, 301)
                self.assertEqual(response["Location"], new)
        self.assert_ok(self.client.get("/projects/P-2027-0001/", follow=True))
        # The address of today and the bare key are not redirected.
        self.assertEqual(self.client.get("/projects/2027-0001/").status_code, 200)
        self.assertEqual(self.client.get(f"/projects/{self.whole.pk}/").status_code, 200)
        self.assertEqual(self.client.get("/projects/P-2027-0099/").status_code, 404)

    def test_the_new_address_is_not_revealed_without_login(self) -> None:
        response = Client().get("/projects/P-2027-0001/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/?next=/projects/P-2027-0001/", response["Location"])

    def test_a_form_sent_to_the_old_address_still_works(self) -> None:
        Project.objects.filter(pk=self.other.pk).update(status=ProjectStatus.INQUIRY)
        response = self.client.post("/projects/P-2027-0002/status/", {"status": ProjectStatus.OPTION})
        self.assertEqual(response.status_code, 302)
        self.other.refresh_from_db()
        self.assertEqual(self.other.status, ProjectStatus.OPTION)

    def test_the_project_names_its_former_number(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:detail", args=[self.whole.pk])))
        self.assertIn("2027-0001", page)
        self.assertIn("(früher P-2027-0001)", page)
        self.assertIn("[RL#2027-0001]", page)
        self.assertNotIn("[RL#P-", page)
        newer = make_project("Neu")
        self.assertEqual(newer.number, "2027-0004")
        self.assertNotIn("früher", self.assert_ok(self.client.get(reverse("projects:detail", args=[newer.pk]))))


class FindByOldNumberTests(HistoryMixin, UiTestCase):
    """ADM-014: the search, the project list and the forms that take a number understand the number with "P-"."""

    def setUp(self) -> None:
        super().setUp()
        self.whole, self.part, self.other, self.newer, self.newer_part = self.history()

    def test_the_search_finds_the_number_with_p(self) -> None:
        page = self.assert_ok(self.client.get(reverse("core:search"), {"q": "P-2027-0002"}))
        self.assertIn("2027-0002 Weinfest", page)
        self.assertNotIn("Stadtfest", page)

    def test_the_project_list_finds_the_number_with_p(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:list"), {"q": "P-2027-0001-1"}))
        self.assertIn("2027-0001-1", page)
        self.assertNotIn("Weinfest", page)

    def test_a_group_is_copied_to_a_project_named_by_its_number_with_p(self) -> None:
        group = add_group(self.whole, "Licht")
        self.htmx("post", reverse("projects:group_copy", args=[self.whole.pk, group.pk]), {"target": "P-2027-0002"})
        self.assertEqual(list(self.other.groups.values_list("name", flat=True)), ["Licht"])

    def test_a_waiting_mail_is_taken_over_with_the_number_with_p(self) -> None:
        configure_mailbox()
        with mailbox(make_mail("Frage [RL#2099-0001]", message_id="<u1@x.example>")):
            fetch_mail(force=True)
            entry = UnknownTagMail.objects.get()
            response = self.client.post(f"/projects/inquiries/{entry.pk}/assign/", {"project_number": "P-2027-0002"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ProjectMail.objects.get().project, self.other)


def give_former_numbers() -> None:
    """Every project without a former number gets "P-" and its number as one.

    NFA-077: the update itself is a squashed migration now; the tests set the result directly.
    """
    Project.objects.filter(former_number="").update(former_number=Concat(Value("P-"), F("number")))


class QueryTests(UiTestCase):
    """ADM-014: former numbers cost no query per row of a list (NFA-012)."""

    def queries_of(self, path: str) -> int:
        with CaptureQueriesContext(connection) as queries:
            self.assert_ok(self.client.get(path))
        return len(queries)

    def test_the_project_list_and_the_search_need_as_many_queries_for_more_projects(self) -> None:
        pages = ("/projects/?q=2027", "/search/?q=2027", "/projects/?q=P-2027")
        # More than the three projects whose numbers the converter of the addresses looks up one by one.
        for _index in range(5):
            make_project()
        give_former_numbers()
        for path in pages:
            self.client.get(path)  # what is done once per session or process
        few = [self.queries_of(path) for path in pages]
        for _index in range(10):
            make_project()
        give_former_numbers()
        self.assertEqual(Project.objects.exclude(former_number="").count(), 15)
        self.assertEqual([self.queries_of(path) for path in pages], few)
