# SPDX-License-Identifier: GPL-3.0-or-later
"""Project numbers without "P-" again (ADM-014): new installations and former numbers.

The requirement: project numbers no longer start with "P-", for future and for existing projects. An older installation
keeps the numbers with "P-" as former numbers
(the update moved them there); they still find their projects. The migrations
are squashed (NFA-077), so the tests set up the state
those updates left behind directly.
"""

from __future__ import annotations

from typing import Any

from rentalars.core.defaults import PROJECT_PREFIX, install_number_ranges
from rentalars.core.forms import SetupForm, SystemSettingsForm
from rentalars.core.models import NumberRange, NumberRangeKey
from rentalars.mail import tags
from rentalars.mail.fetching import fetch_mail
from rentalars.mail.models import AssignedBy, ProjectMail, UnknownTagMail
from rentalars.projects import numbers
from rentalars.projects import services as project_services
from rentalars.projects.models import Project
from tests.helpers import RentalarsTestCase, make_project
from tests.mailbox import FakeMailbox, configure_mailbox, make_mail


def set_project_prefix(prefix: str, **fields: Any) -> None:
    """Give the project range another prefix, as an administrator could have done."""
    NumberRange.objects.filter(key=NumberRangeKey.PROJECT).update(prefix=prefix, **fields)


def project_prefix() -> str:
    return NumberRange.objects.get(key=NumberRangeKey.PROJECT).prefix


def numbers_and_formers(*projects: Project) -> list[tuple[str, str]]:
    rows = dict(Project.objects.values_list("pk", "number"))
    formers = dict(Project.objects.values_list("pk", "former_number"))
    return [(rows[project.pk], formers[project.pk]) for project in projects]


class HistoryMixin:
    """An older installation that went through the update: its numbers afterwards."""

    def projects_of_062(self, prefix: str = "{year}-") -> tuple[Project, Project, Project]:
        """A whole project with a part, and a second project – numbered as in the older installation (2027-0001, 2027-0001-1)."""
        set_project_prefix(prefix)
        whole = make_project("Stadtfest")
        part = project_services.create_subproject(whole, name="Bühne Marktplatz")
        other = make_project("Weinfest")
        return whole, part, other

    def history(self) -> tuple[Project, Project, Project, Project, Project]:
        """The old numbering, where a project with a part is created (P-2027-0003, P-2027-0003-1), then the update.

        After the update every project has today's number again (2027-0001) and the one with "P-" as
        its former number (P-2027-0001).
        """
        whole, part, other = self.projects_of_062()
        newer = make_project("Hafenfest")
        newer_part = project_services.create_subproject(newer, name="Kai")
        projects = (whole, part, other, newer, newer_part)
        for project in projects:
            Project.objects.filter(pk=project.pk).update(former_number=f"P-{project.number}")
            project.refresh_from_db()
        self.assertEqual(
            numbers_and_formers(newer, newer_part), [("2027-0003", "P-2027-0003"), ("2027-0003-1", "P-2027-0003-1")]
        )
        return projects


class NewInstallationTests(RentalarsTestCase):
    """ADM-014: a new installation numbers its projects 2027-0001 again."""

    def test_the_start_data_and_the_setup_form_have_no_p(self) -> None:
        self.assertEqual(PROJECT_PREFIX, "{year}-")
        self.assertEqual(SetupForm().fields["project_prefix"].initial, "{year}-")
        help_text = str(SetupForm().fields["project_prefix"].help_text)
        self.assertIn("2026-0001", help_text)
        self.assertNotIn("P-", help_text)
        NumberRange.objects.filter(key=NumberRangeKey.PROJECT).delete()
        install_number_ranges()
        number_range = NumberRange.objects.get(key=NumberRangeKey.PROJECT)
        self.assertEqual(
            (number_range.prefix, number_range.min_digits, number_range.reset_yearly), ("{year}-", 4, True)
        )

    def test_new_projects_and_their_parts_have_no_p(self) -> None:
        whole = make_project("Stadtfest")
        part = project_services.create_subproject(whole, name="Bühne")
        self.assertEqual((whole.number, part.number), ("2027-0001", "2027-0001-1"))
        self.assertEqual(whole.former_number, "")
        self.assertEqual(whole.mail_tag, "[RL#2027-0001]")

    def test_the_counter_still_starts_again_every_year(self) -> None:
        set_project_prefix("{year}-", current_year=2026, next_value=57)
        self.assertEqual(make_project("Neujahr").number, "2027-0001")
        self.assertEqual(make_project("Zweites").number, "2027-0002")

    def test_the_example_of_the_mail_tag_has_no_p(self) -> None:
        help_text = str(SystemSettingsForm().fields["mail_tag_prefix"].help_text)
        self.assertIn("[RL#2026-0042]", help_text)


class FormerNumberTests(HistoryMixin, RentalarsTestCase):
    """ADM-014: today's number and the former one with "P-" both find the project; today's wins."""

    def test_project_by_number(self) -> None:
        whole, part, _other, newer, _newer_part = self.history()
        for typed, expected in (
            ("2027-0001", whole),
            ("P-2027-0001", whole),
            ("p-2027-0001", whole),
            (" P-2027-0001-1 ", part),
            ("2027-0001-1", part),
            ("P-2027-0003", newer),
            ("2027-0009", None),
            ("P-2027-0009", None),
            ("PRJ-2027-0001", None),
            ("", None),
        ):
            with self.subTest(typed=typed), self.assertNumQueries(1 if typed.strip() else 0):
                self.assertEqual(numbers.project_by_number(typed), expected)

    def test_the_search_finds_both(self) -> None:
        whole, part, _other, _newer, _newer_part = self.history()
        for text in ("2027-0001", "P-2027-0001"):
            with self.subTest(text=text):
                self.assertEqual(list(Project.objects.filter(numbers.matching(text)).order_by("pk")), [whole, part])

    def test_the_number_of_today_wins(self) -> None:
        whole, _part, _other, _newer, _newer_part = self.history()
        set_project_prefix("P-{year}-", next_value=1)
        # The numbers with "P-" that were given are skipped: on paper they still mean their projects.
        newer = make_project("Wieder mit P")
        self.assertEqual(newer.number, "P-2027-0004")
        Project.objects.filter(pk=newer.pk).update(number="P-2027-0001")
        self.assertEqual(numbers.project_by_number("P-2027-0001").pk, newer.pk)
        self.assertEqual(numbers.project_by_number("2027-0001"), whole)
        self.assertEqual(numbers.numbers_of_today(["P-2027-0001", "P-2027-0002"]), ["P-2027-0001", "2027-0002"])

    def test_a_former_number_from_063_still_counts(self) -> None:
        """A project that could not be renamed keeps the former number it was given."""
        whole, _part, _other = self.projects_of_062()
        # Gave "P-" and kept 2026-0042 as former number; "P-" could not be taken away again.
        Project.objects.filter(pk=whole.pk).update(number="P-2027-0001", former_number="2026-0042")
        whole.refresh_from_db()
        self.assertEqual((whole.number, whole.former_number), ("P-2027-0001", "2026-0042"))
        self.assertEqual(numbers.project_by_number("2026-0042"), whole)
        self.assertEqual(numbers.numbers_of_today(["2026-0042"]), ["P-2027-0001"])

    def test_numbers_of_today_asks_once_and_only_when_a_number_can_be_former(self) -> None:
        self.history()
        with self.assertNumQueries(0):
            self.assertEqual(numbers.numbers_of_today(["PRJ-2027-0001", "XY-1", "P-"]), ["PRJ-2027-0001", "XY-1", "P-"])
        with self.assertNumQueries(1):
            self.assertEqual(
                numbers.numbers_of_today(["P-2027-0002", "2027-0001", "1999-0001", "p-2027-0001-1", "PRJ-1"]),
                ["2027-0002", "2027-0001", "1999-0001", "2027-0001-1", "PRJ-1"],
            )

    def test_what_can_be_a_former_number(self) -> None:
        for number, expected in (
            ("2026-0042", True),
            ("P-2026-0042", True),
            ("p-2026-0042-1", True),
            ("0042", True),
            ("PRJ-2026-0042", False),
            ("P-MS-2026-0042", False),
            ("P-", False),
            ("", False),
        ):
            with self.subTest(number=number):
                self.assertEqual(numbers.may_be_former(number), expected)


class MailTagTests(HistoryMixin, RentalarsTestCase):
    """ADM-014: replies to mails sent earlier carry the tag with "P-" – and still land in their project."""

    def fetch(self, *mails: bytes) -> Any:
        return fetch_mail(force=True, opener=FakeMailbox(*mails))

    def test_a_reply_with_the_tag_of_063_lands_in_the_project(self) -> None:
        whole, part, _other, newer, _newer_part = self.history()
        configure_mailbox()
        subjects = {
            "AW: Angebot [RL#P-2027-0001]": whole,
            "AW: Bühnenplan [rl# p-2027-0001-1 ]": part,
            "AW: Rider [RL#P-2027-0003]": newer,
            "AW: Neu [RL#2027-0001]": whole,
        }
        self.fetch(*(make_mail(subject, message_id=f"<m{index}@x.example>") for index, subject in enumerate(subjects)))
        mails = {mail.subject: mail for mail in ProjectMail.objects.all()}
        self.assertEqual({subject: mail.project for subject, mail in mails.items()}, subjects)
        self.assertEqual({mail.assigned_by for mail in mails.values()}, {AssignedBy.TAG})
        self.assertFalse(UnknownTagMail.objects.exists())

    def test_an_unknown_number_with_p_waits_with_its_tag(self) -> None:
        self.history()
        configure_mailbox()
        self.fetch(make_mail("Frage [RL#P-2025-0042]"))
        self.assertEqual(UnknownTagMail.objects.get().tag, "P-2025-0042")

    def test_find_numbers_gives_the_number_of_today(self) -> None:
        self.history()
        self.assertEqual(
            tags.find_numbers("AW: [RL#P-2027-0002] und [RL#2027-0001] und [RL#P-1999-0001]", prefix="RL"),
            ["2027-0002", "2027-0001", "P-1999-0001"],
        )

    def test_the_answer_to_a_mail_of_063_gets_the_tag_of_today(self) -> None:
        whole, _part, other, _newer, _newer_part = self.history()
        self.assertEqual(
            tags.subject_with_tag("AW: Angebot [rl# P-2027-0001] Stadtfest", whole.number, prefix="RL"),
            "AW: Angebot [RL#2027-0001] Stadtfest",
        )
        # The old tag of another project is not touched.
        self.assertEqual(
            tags.subject_with_tag("WG: Angebot [RL#P-2027-0001]", other.number, prefix="RL"),
            "WG: Angebot [RL#P-2027-0001] [RL#2027-0002]",
        )
        with self.assertNumQueries(0):
            self.assertEqual(tags.subject_with_tag("Angebot", whole.number, prefix="RL"), "Angebot [RL#2027-0001]")
