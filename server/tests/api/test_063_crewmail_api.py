# SPDX-License-Identifier: GPL-3.0-or-later
"""API: answering a deployment request by reply mail (PER-032).

* ``GET/PATCH /mail/settings`` – ``crew_answers`` (``link``, ``mail``,
  ``both``) and the read-only ``crew_answer_address``.
* ``POST /projects/{id}/crew-lines/{line}/request`` – the request goes as a
  mail with the buttons; ``notified`` is true.
* ``GET /mail/log?result=crew_answer`` – answers by mail in the mail log.
"""

from __future__ import annotations

from django.core import mail as django_mail

from rentalars.mail.models import CrewAnswerMode, CrewRequestMail, MailSettings
from rentalars.projects.models import RequestStatus
from tests.api.base import API, ApiTestCase
from tests.helpers import make_person, make_project, make_user, plan
from tests.mailbox import FakeMailbox, configure_mailbox, mailboxes
from tests.unit.test_063_crewmail import answer_mail, mailto_links

SETTINGS = f"{API}/mail/settings"


class CrewAnswerSettingApiTests(ApiTestCase):
    """PER-032: the setting in ``/mail/settings``."""

    def test_read_and_change(self) -> None:
        data = self.admin.get(SETTINGS).json()
        self.assertEqual((data["crew_answers"], data["crew_answer_address"]), ("both", None))
        configure_mailbox()
        response = self.admin.patch(SETTINGS, {"crew_answers": "mail"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            (response.json()["crew_answers"], response.json()["crew_answer_address"]),
            ("mail", "projekte@verleih.example"),
        )
        self.assertEqual(MailSettings.load().crew_answers, CrewAnswerMode.MAIL)

    def test_an_unknown_value_is_refused(self) -> None:
        response = self.admin.patch(SETTINGS, {"crew_answers": "fax"}, format="json")
        self.assert_error(response, 400, "validation_error", "crew_answers")
        self.assertEqual(MailSettings.load().crew_answers, CrewAnswerMode.BOTH)

    def test_the_address_cannot_be_written(self) -> None:
        configure_mailbox()
        response = self.admin.patch(SETTINGS, {"crew_answer_address": "x@example.org"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["crew_answer_address"], "projekte@verleih.example")

    def test_only_with_write_access_to_e_mail(self) -> None:
        crew = self.client_for("ben", "Crew")
        self.assertEqual(crew.get(SETTINGS).status_code, 403)
        self.assertEqual(crew.patch(SETTINGS, {"crew_answers": "link"}, format="json").status_code, 403)
        self.assertEqual(MailSettings.load().crew_answers, CrewAnswerMode.BOTH)


class RequestAndAnswerApiTests(ApiTestCase):
    """PER-032: asking through the API sends the request mail; the answer by mail shows in the mail log."""

    def test_ask_and_find_the_answer_in_the_log(self) -> None:
        mailbox = configure_mailbox()
        manager = make_user("paula", roles=("Projektleitung",))
        project = make_project(manager=manager)
        line = plan(project, "Tontechnik", make_person("Anna Becker", email="anna@crew.example"))
        django_mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            asked = self.client_of(manager).post(f"{API}/projects/{project.pk}/crew-lines/{line.pk}/request")
        self.assertEqual(asked.status_code, 200, asked.content)
        # EML-048: the answer also says whether the request mail went out.
        self.assertEqual(
            asked.json(), {"notified": True, "request_status": "requested", "mail_sent": True, "mail_reason": ""}
        )
        (message,) = django_mail.outbox
        self.assertEqual(set(mailto_links(message)), {"Zusagen", "Absagen"})
        self.assertTrue(CrewRequestMail.objects.filter(line=line).exists())

        with (
            self.captureOnCommitCallbacks(execute=True),
            mailboxes({mailbox.address: FakeMailbox(answer_mail(message, note="Gern"))}),
        ):
            fetched = self.admin.post(f"{API}/mail/fetch")
        self.assertEqual(fetched.status_code, 200, fetched.content)
        line.refresh_from_db()
        self.assertEqual((line.request_status, line.answer_note), (RequestStatus.ACCEPTED, "Gern"))

        log = self.admin.get(f"{API}/mail/log", {"result": "crew_answer"}).json()
        (entry,) = log["results"]
        self.assertEqual(
            (entry["direction"], entry["kind"], entry["result"], entry["detail"], entry["project_number"]),
            ("in", "project", "crew_answer", "Zusage", project.number),
        )
