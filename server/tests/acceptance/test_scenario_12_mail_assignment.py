# SPDX-License-Identifier: GPL-3.0-or-later
"""Acceptance scenario 12 – E-Mail-Zuordnung (catalogue chapter 11)."""

from rentalars.core.search import global_search
from rentalars.mail.fetching import fetch_mail
from rentalars.mail.models import ProjectMail, UnknownTagMail
from rentalars.mail.sending import send_project_mail
from rentalars.masterdata.models import DocumentType
from rentalars.projects.files import add_file_from_attachment
from rentalars.projects.models import ProjectMembership
from tests.helpers import RentalarsTestCase, make_project, make_user
from tests.mailbox import FakeMailbox, capture_smtp, configure_mailbox, make_mail

PDF = b"%PDF-1.4\n%%EOF\n"


class Scenario12MailAssignment(RentalarsTestCase):
    """EML-005 to EML-015, EML-019 to EML-021, EML-024, EML-029."""

    def setUp(self) -> None:
        super().setUp()
        configure_mailbox()
        self.project = make_project("Stadtfest")
        self.tag = f"[RL#{self.project.number}]"
        self.box = FakeMailbox()

    def fetch(self) -> object:
        return fetch_mail(force=True, opener=self.box)

    def test_tagged_mails_arrive_with_their_attachment(self) -> None:
        self.box.add(make_mail(f"AW: Bühnenplan {self.tag}", attachments=[("buehnenplan.pdf", "application/pdf", PDF)]))
        self.box.add(make_mail(f"Rider [rl# {self.project.number}]"))
        self.fetch()
        mails = self.project.mails.order_by("id")
        self.assertEqual(
            [mail.subject for mail in mails], [f"AW: Bühnenplan {self.tag}", f"Rider [rl# {self.project.number}]"]
        )
        attachment = mails[0].attachments.get()
        with attachment.file.open("rb") as handle:
            self.assertEqual(handle.read(), PDF)
        project_file = add_file_from_attachment(
            attachment, user=None, document_type=DocumentType.objects.get(name="Bühnenplan")
        )
        self.assertEqual(self.project.files.get(), project_file)

    def test_an_answer_with_the_number_of_0_6_3_finds_the_project(self) -> None:
        """ADM-014: the project was renamed from P-2026-0042 to 2026-0042; answers to mails sent earlier still arrive."""
        self.assertFalse(self.project.number.startswith("P-"))
        former = f"P-{self.project.number}"
        self.project.former_number = former
        self.project.save(update_fields=["former_number"])
        self.box.add(make_mail(f"AW: Bühnenplan [RL#{former}]"))
        self.fetch()
        self.assertEqual(self.project.mails.get().subject, f"AW: Bühnenplan [RL#{former}]")
        self.assertFalse(UnknownTagMail.objects.exists())

    def test_untagged_and_unknown_mails_stay_untouched(self) -> None:
        untagged = self.box.add(make_mail("Newsletter"))
        unknown = self.box.add(make_mail("Frage [RL#2026-9999]"))
        self.fetch()
        self.assertEqual(sorted(self.box.inbox), [untagged, unknown])
        self.assertEqual(self.box.fetched, [])  # not even read completely – it stays unread
        self.assertFalse(ProjectMail.objects.exists())
        self.assertEqual(UnknownTagMail.objects.get().tag, "2026-9999")

    def test_assigned_mails_are_filed_away_once(self) -> None:
        raw = make_mail(f"Bühnenplan {self.tag}", message_id="<plan@stadtwerke.example>")
        self.box.add(raw)
        self.fetch()
        self.assertEqual((self.box.inbox, self.box.done), ({}, [raw]))
        self.box.add(raw)  # the same mail once more, e.g. copied back by a mail program
        self.fetch()
        self.assertEqual(ProjectMail.objects.count(), 1)

    def test_the_answer_to_a_sent_mail_finds_its_project(self) -> None:
        with capture_smtp() as sent:
            mail = send_project_mail(
                self.project, to="kunde@stadtwerke.example", subject="Angebot", body="Anbei.", user=None
            )
        self.assertIn(self.tag, sent[0]["Subject"])
        self.box.add(make_mail("AW: Angebot", in_reply_to=mail.message_id))
        result = self.fetch()
        self.assertEqual([item.project for item in result.imported], [self.project])

    def test_who_may_not_see_it_does_not_find_it(self) -> None:
        self.box.add(make_mail(f"Vertrag {self.tag}"))
        self.fetch()
        stranger = make_user("ben", roles=("Crew",))
        no_correspondence = make_user("luka", roles=("Lager",))  # reads projects, no correspondence right
        ProjectMembership.objects.create(project=self.project, user=stranger, level="read")
        manager = make_user("paula", roles=("Projektleitung",))

        def found(user: object) -> list[str]:
            from rentalars.accounts.rights import rights_of

            groups = global_search("Vertrag", rights_of(user), user)
            return [hit.title for group in groups for hit in group.hits if group.kind == "mails"]

        self.assertEqual(found(manager), [f"Vertrag {self.tag}"])
        self.assertEqual(found(no_correspondence), [])
        self.assertEqual(found(stranger), [])
