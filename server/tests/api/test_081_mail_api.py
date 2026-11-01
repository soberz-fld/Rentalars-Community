# SPDX-License-Identifier: GPL-3.0-or-later
"""API, area "mail" (API-014).

* EML-047: ``/mail/mailbox-addresses`` – every operation; the addresses in ``/mail/mailboxes``.
* EML-006: ``after_assignment = read``.
* EML-048: ``not_sent`` in the mail log.
* PRJ-107: ``POST /mail/unknown/dismiss`` for several mails; ``POST /projects`` with ``inquiry``.
"""

from __future__ import annotations

from django.core.mail import send_mail
from django.test import override_settings

from rentalars.mail.fetching import fetch_mail
from rentalars.mail.models import Mailbox, MailboxAddress, ProjectMail, UnknownTagMail
from rentalars.projects.models import Project
from tests.api.base import API, ApiTestCase
from tests.helpers import make_customer, make_person, make_project, make_user, plan
from tests.mailbox import FakeMailbox, configure_mailbox, mailboxes, make_mail

ADDRESSES = f"{API}/mail/mailbox-addresses"


class MailboxAddressResourceTests(ApiTestCase):
    """EML-047: list, create, read, change, replace, delete the further addresses of a mailbox."""

    def setUp(self) -> None:
        super().setUp()
        self.box = configure_mailbox()

    def test_every_operation(self) -> None:
        office = make_user("office")
        created = self.admin.post(
            ADDRESSES,
            {
                "mailbox": self.box.pk,
                "address": "Support@Verleih.example",
                "untagged": "service_case",
                "case_manager": office.pk,
                "for_service_cases": True,
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        data = created.json()
        self.assertEqual(
            (data["address"], data["untagged"], data["case_manager"], data["for_service_cases"]),
            ("support@verleih.example", "service_case", office.pk, True),
        )
        pk = data["id"]
        self.assert_error(
            self.admin.post(ADDRESSES, {"mailbox": self.box.pk, "address": "support@verleih.example"}, format="json"),
            400,
            "validation_error",
            "address",
        )
        listed = self.admin.get(ADDRESSES, {"mailbox": self.box.pk})
        self.assertEqual([row["id"] for row in listed.json()["results"]], [pk])
        self.assertEqual(self.admin.get(f"{ADDRESSES}/{pk}").json()["address"], "support@verleih.example")
        # The mailbox names its addresses.
        mailbox = self.admin.get(f"{API}/mail/mailboxes/{self.box.pk}").json()
        self.assertEqual([entry["address"] for entry in mailbox["addresses"]], ["support@verleih.example"])

        # A second address takes the role "only for service cases".
        second = self.admin.post(
            ADDRESSES,
            {"mailbox": self.box.pk, "address": "hilfe@verleih.example", "for_service_cases": True},
            format="json",
        )
        self.assertEqual(second.status_code, 201, second.content)
        self.assertEqual(second.json()["untagged"], "inquiry")
        self.assertFalse(MailboxAddress.objects.get(pk=pk).for_service_cases)

        patched = self.admin.patch(f"{ADDRESSES}/{pk}", {"untagged": "ignore"}, format="json")
        self.assertEqual((patched.status_code, patched.json()["untagged"]), (200, "ignore"))
        replaced = self.admin.put(
            f"{ADDRESSES}/{pk}",
            {"mailbox": self.box.pk, "address": "service@verleih.example", "untagged": "inquiry"},
            format="json",
        )
        self.assertEqual(replaced.status_code, 200, replaced.content)
        self.assertEqual(MailboxAddress.objects.get(pk=pk).address, "service@verleih.example")
        self.assertEqual(self.admin.delete(f"{ADDRESSES}/{pk}").status_code, 204)
        self.assertEqual(list(MailboxAddress.objects.values_list("address", flat=True)), ["hilfe@verleih.example"])

    def test_rights(self) -> None:
        reader = self.client_for("lea", "Nur-Lesen")
        self.assertEqual(reader.get(ADDRESSES).status_code, 403)
        self.assertEqual(
            reader.post(ADDRESSES, {"mailbox": self.box.pk, "address": "x@verleih.example"}, format="json").status_code,
            403,
        )

    def test_only_mark_as_read(self) -> None:
        """EML-006: the new choice of ``after_assignment``."""
        changed = self.admin.patch(
            f"{API}/mail/mailboxes/{self.box.pk}", {"after_assignment": "read", "done_folder": ""}, format="json"
        )
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual(Mailbox.objects.get(pk=self.box.pk).after_assignment, "read")


class InquiryApiTests(ApiTestCase):
    """PRJ-107: several mails off the list at once; a project made from an inquiry takes its mail along."""

    def setUp(self) -> None:
        super().setUp()
        self.box = configure_mailbox(process_untagged=True)
        self.raw = make_mail("Angebot Hoffest", message_id="<h@x.example>")
        with mailboxes({self.box.address: FakeMailbox(self.raw, make_mail("Frage 2"), make_mail("Frage 3"))}):
            fetch_mail(force=True)

    def test_dismissing_several(self) -> None:
        ids = list(UnknownTagMail.objects.exclude(subject="Angebot Hoffest").values_list("pk", flat=True))
        response = self.admin.post(f"{API}/mail/unknown/dismiss", {"ids": ids}, format="json")
        self.assertEqual(response.json(), {"dismissed": 2})
        self.assertEqual(
            self.admin.post(f"{API}/mail/unknown/dismiss", {"ids": ids}, format="json").json(), {"dismissed": 0}
        )
        self.assert_error(
            self.admin.post(f"{API}/mail/unknown/dismiss", {"ids": "1"}, format="json"), 400, "validation_error"
        )
        crew = self.client_for("ben", "Crew")
        self.assertEqual(crew.post(f"{API}/mail/unknown/dismiss", {"ids": ids}, format="json").status_code, 403)

    def test_a_project_from_an_inquiry(self) -> None:
        inquiry = UnknownTagMail.objects.get(subject="Angebot Hoffest")
        body = {
            "name": "Hoffest",
            "customer": make_customer().pk,
            "start": "2027-03-10T08:00:00+01:00",
            "end": "2027-03-12T18:00:00+01:00",
            "inquiry": inquiry.pk,
        }
        with mailboxes({self.box.address: FakeMailbox()}):
            gone = self.admin.post(f"{API}/projects", body, format="json")
        self.assert_error(gone, 400, "validation_error", "inquiry")
        self.assertFalse(Project.objects.filter(name="Hoffest").exists())
        with mailboxes({self.box.address: FakeMailbox(self.raw)}):
            created = self.admin.post(f"{API}/projects", body, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(ProjectMail.objects.get().project_id, created.json()["id"])
        self.assertNotIn("inquiry", created.json())
        self.assert_error(self.admin.post(f"{API}/projects", body, format="json"), 400, "validation_error", "inquiry")


@override_settings(
    EMAIL_BACKEND="rentalars.mail.backends.LoggingEmailBackend",
    EMAIL_INNER_BACKEND="django.core.mail.backends.dummy.EmailBackend",
)
class NotSentApiTests(ApiTestCase):
    """EML-048: the mail log says ``not_sent`` for a system mail without a mail server."""

    def test_the_result(self) -> None:
        send_mail("Dein Zugang", "Hallo", None, ["berta@example.de"])
        (row,) = self.admin.get(f"{API}/mail/log").json()["results"]
        self.assertEqual(row["result"], "not_sent")

    def test_an_invitation_says_it_was_not_sent(self) -> None:
        user = make_user("berta")
        response = self.admin.post(f"{API}/users/{user.pk}/send-invitation")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {"sent": False, "reason": "Nicht versendet – kein Mailserver eingerichtet."})
        created = self.admin.post(f"{API}/users", {"username": "carla", "email": "carla@example.de"}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["invitation"]["sent"], False)
        without = self.admin.post(f"{API}/users", {"username": "dora", "email": ""}, format="json")
        self.assertEqual(without.json()["invitation"], {"sent": None, "reason": ""})

    @override_settings(EMAIL_INNER_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_with_a_server_as_before(self) -> None:
        user = make_user("berta")
        self.assertEqual(self.admin.post(f"{API}/users/{user.pk}/send-invitation").status_code, 204)
        created = self.admin.post(f"{API}/users", {"username": "carla", "email": "carla@example.de"}, format="json")
        self.assertEqual(created.json()["invitation"], {"sent": True, "reason": ""})

    def test_a_deployment_request(self) -> None:
        configure_mailbox()
        project = make_project("Hoffest")
        line = plan(project, "Bühnenbau", make_person("Jörg Müßig", email="joerg@crew.example"))
        asked = self.admin.post(f"{API}/projects/{project.pk}/crew-lines/{line.pk}/request")
        self.assertEqual(asked.status_code, 200, asked.content)
        self.assertEqual(
            (asked.json()["notified"], asked.json()["mail_sent"], asked.json()["mail_reason"]),
            (True, False, "Nicht versendet – kein Mailserver eingerichtet."),
        )
        quiet = plan(project, "Bühnenbau", make_person("Ida Ohnemail"))
        self.assertIsNone(
            self.admin.post(f"{API}/projects/{project.pk}/crew-lines/{quiet.pk}/request").json()["mail_sent"]
        )
