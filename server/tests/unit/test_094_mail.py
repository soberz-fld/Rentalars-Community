# SPDX-License-Identifier: GPL-3.0-or-later
"""An answer to a deployment request by mail is moved into the folder (PER-043).

The requirement: answers with the unambiguous code are also moved automatically into the folder of the mailbox.
It is moved into the folder for assigned mails whenever the mailbox does not delete or leave mails.
"""

from __future__ import annotations

from unittest import mock

from rentalars.mail.imap import ImapMailbox
from rentalars.mail.models import AfterAssignment
from tests.unit.test_063_crewmail import CrewMailTestCase, answer_mail


class AnswerFilingTests(CrewMailTestCase):
    """PER-043: where the answer goes, by the setting of the mailbox."""

    def setUp(self) -> None:
        super().setUp()
        self.ask()
        self.request = self.request_message()

    def answer_with(self, after: str, folder: str = "Rentalars") -> None:
        self.mailbox.after_assignment = after
        self.mailbox.done_folder = folder
        self.mailbox.save()
        result = self.fetch(answer_mail(self.request))
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.crew_answers, 1)

    def test_with_only_mark_as_read_it_is_moved_too(self) -> None:
        self.answer_with(AfterAssignment.READ)
        self.assertEqual((self.box.inbox, len(self.box.done), self.box.read), ({}, 1, []))

    def test_without_a_folder_set_the_default_folder_is_taken(self) -> None:
        self.answer_with(AfterAssignment.READ, folder="")
        self.assertEqual((self.box.inbox, len(self.box.done)), ({}, 1))

    def test_if_the_folder_is_the_inbox_it_is_only_marked_as_read(self) -> None:
        self.answer_with(AfterAssignment.READ, folder="inbox")
        self.assertEqual((len(self.box.inbox), len(self.box.done), len(self.box.read)), (1, 0, 1))

    def test_move_stays_move(self) -> None:
        self.answer_with(AfterAssignment.MOVE)
        self.assertEqual((self.box.inbox, len(self.box.done)), ({}, 1))

    def test_delete_and_leave_are_kept(self) -> None:
        self.answer_with(AfterAssignment.DELETE)
        self.assertEqual((self.box.inbox, len(self.box.deleted), len(self.box.done)), ({}, 1, 0))

    def test_leave_changes_nothing(self) -> None:
        self.answer_with(AfterAssignment.KEEP)
        self.assertEqual((len(self.box.inbox), len(self.box.kept), len(self.box.done)), (1, 1, 0))


class ImapAnswerTests(CrewMailTestCase):
    """PER-043: the IMAP connection moves an answer under "only mark as read", a normal assigned mail it does not."""

    def connection(self) -> mock.Mock:
        settings = mock.Mock(after_assignment=AfterAssignment.READ, done_folder="", inbox_folder="INBOX")
        connection = ImapMailbox(settings)
        connection.imap = mock.Mock()
        connection.imap.uid.return_value = ("OK", [b""])
        connection.imap.create.return_value = ("OK", [b""])
        connection.capabilities = {"MOVE", "UIDPLUS"}
        return connection

    def test_an_answer_is_moved_into_the_default_folder(self) -> None:
        connection = self.connection()
        connection.file_away(42, answer=True)
        self.assertEqual(
            connection.imap.uid.call_args_list,
            [mock.call("STORE", "42", "+FLAGS", "(\\Seen)"), mock.call("MOVE", "42", '"Rentalars"')],
        )

    def test_another_assigned_mail_is_only_marked_as_read(self) -> None:
        connection = self.connection()
        connection.file_away(42)
        self.assertEqual(connection.imap.uid.call_args_list, [mock.call("STORE", "42", "+FLAGS", "(\\Seen)")])
