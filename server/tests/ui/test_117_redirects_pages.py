# SPDX-License-Identifier: GPL-3.0-or-later
"""S11 of the security review: no form sends the user to another site, whatever it writes in ``next``."""

from __future__ import annotations

from django.urls import reverse

from rentalars.mail.models import UnknownTagMail
from rentalars.projects.models import OpenItem
from tests.helpers import make_person, make_project, plan
from tests.ui.base import UiTestCase

#: Written as a browser reads it: "/\evil.example" is "//evil.example"; the others are other ways around a check.
EVIL = (
    "/\\evil.example",
    "//evil.example",
    "/\t/evil.example",
    "https://evil.example/",
    "\\\\evil.example",
    "javascript:1",
)


class NextOfTheFormTests(UiTestCase):
    """The three places that checked ``next`` by hand now use Django's check."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project()
        self.person = make_person("Anna Becker", rates={"Stagehand": "20.00"})
        self.line = plan(self.project, "Stagehand", self.person)

    def test_crew_answer(self) -> None:
        url = reverse("projects:crew_answer", args=[self.project, self.line.pk])
        default = reverse("projects:deployment", args=[self.project.pk])
        for evil in EVIL:
            with self.subTest(next=evil):
                response = self.client.post(url, {"answer": "accept", "next": evil})
                self.assertRedirects(response, default, fetch_redirect_response=False)
        ours = self.client.post(url, {"answer": "accept", "next": "/projects/?q=1#phases"})
        self.assertEqual(ours["Location"], "/projects/?q=1#phases")

    def test_open_item_toggle(self) -> None:
        item = OpenItem.objects.create(project=self.project, text="Ersatzteil bestellen")
        url = reverse("projects:open_item_toggle", args=[self.project, item.pk])
        for evil in EVIL:
            with self.subTest(next=evil):
                response = self.client.post(url, {"done": "1", "next": evil})
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith("/"), response["Location"])
                self.assertFalse(response["Location"].startswith(("//", "/\\")), response["Location"])
        ours = self.client.post(url, {"done": "0", "next": "/projects/open-items/"})
        self.assertEqual(ours["Location"], "/projects/open-items/")

    def test_mail_back(self) -> None:
        for evil in EVIL:
            with self.subTest(next=evil):
                unknown = UnknownTagMail.objects.create(
                    message_key=f"k{EVIL.index(evil)}", subject="Anfrage", sender="a@kunde.example"
                )
                response = self.client.post(reverse("mail:unknown_dismiss", args=[unknown.pk]), {"next": evil})
                self.assertRedirects(response, reverse("mail:unknown_list"), fetch_redirect_response=False)
