# SPDX-License-Identifier: GPL-3.0-or-later
"""The API and the project numbers without "P-" again (ADM-014): new numbers, the number with "P-" in filters and mail."""

from __future__ import annotations

from rentalars.mail.models import ProjectMail, UnknownTagMail
from tests.api.base import API, ApiTestCase
from tests.helpers import make_project
from tests.mailbox import configure_mailbox, mailbox, make_mail
from tests.unit.test_070_numbers import HistoryMixin


class NewNumberApiTests(ApiTestCase):
    """ADM-014: a project created through the API is numbered 2027-0002 – without "P-"."""

    def test_new_project_has_no_p_and_no_former_number(self) -> None:
        customer = make_project().customer
        body = {"name": "Neu", "customer": customer.pk, "start": "2027-03-10T08:00", "end": "2027-03-12T18:00"}
        response = self.admin.post(f"{API}/projects", body, format="json")
        self.assertEqual(response.status_code, 201, response.json())
        self.assertEqual((response.json()["number"], response.json()["former_number"]), ("2027-0002", ""))

    def test_the_description_shows_examples_without_p(self) -> None:
        schema = self.admin.get(f"{API}/schema?format=json").json()
        settings = schema["components"]["schemas"]["SystemSettings"]["properties"]["mail_tag_prefix"]
        self.assertIn("[RL#2026-0042]", settings["description"])
        number_filter = next(
            parameter
            for parameter in schema["paths"]["/api/v1/projects"]["get"]["parameters"]
            if parameter["name"] == "number"
        )
        self.assertIn("former", number_filter["description"])


class FormerNumberApiTests(HistoryMixin, ApiTestCase):
    """ADM-014: programs that stored a number with "P-" still find the project."""

    def setUp(self) -> None:
        super().setUp()
        self.whole, self.part, self.other, self.newer, self.newer_part = self.history()

    def numbers_of(self, **query: str) -> list[str]:
        response = self.admin.get(f"{API}/projects", query)
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.json()
        rows = rows["results"] if isinstance(rows, dict) else rows
        return sorted(row["number"] for row in rows)

    def test_the_number_filter_takes_the_number_of_today_or_the_one_with_p(self) -> None:
        self.assertEqual(self.numbers_of(number="2027-0001"), ["2027-0001"])
        self.assertEqual(self.numbers_of(number="P-2027-0001"), ["2027-0001"])
        self.assertEqual(self.numbers_of(number="p-2027-0001"), ["2027-0001"])
        self.assertEqual(self.numbers_of(number="P-2027-0001-1"), ["2027-0001-1"])
        self.assertEqual(self.numbers_of(number="P-2027-0003"), ["2027-0003"])
        self.assertEqual(self.numbers_of(number="P-2027-0099"), [])

    def test_the_search_finds_the_number_with_p(self) -> None:
        self.assertEqual(self.numbers_of(q="P-2027-0001"), ["2027-0001", "2027-0001-1"])

    def test_the_former_number_is_shown_and_cannot_be_changed(self) -> None:
        url = f"{API}/projects/{self.whole.pk}"
        self.assertEqual(self.admin.get(url).json()["former_number"], "P-2027-0001")
        response = self.admin.patch(url, {"former_number": "X", "number": "Y"}, format="json")
        self.assertEqual(response.status_code, 200, response.json())
        self.whole.refresh_from_db()
        self.assertEqual((self.whole.number, self.whole.former_number), ("2027-0001", "P-2027-0001"))

    def test_a_waiting_mail_is_taken_over_with_the_number_with_p(self) -> None:
        configure_mailbox()
        with mailbox(make_mail("Frage zu [RL#2099-0999]", message_id="<m2@stadtwerke.example>")):
            self.admin.post(f"{API}/mail/fetch")
            entry = UnknownTagMail.objects.get()
            response = self.admin.post(
                f"{API}/mail/unknown/{entry.pk}/assign", {"project_number": "P-2027-0002"}, format="json"
            )
        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual(ProjectMail.objects.get(pk=response.json()["mail"]).project, self.other)
