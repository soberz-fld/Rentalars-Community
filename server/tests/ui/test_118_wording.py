# SPDX-License-Identifier: GPL-3.0-or-later
"""Wording, formats and pages — B5 – B12 and the layout items V8, V14, V17 – V25 of the review."""

from __future__ import annotations

import pathlib
import re

from django.test import SimpleTestCase
from django.urls import reverse
from django.utils import translation

from tests.ui.base import UiTestCase
from tests.ui.test_081_times_pages import PeriodPageCase

ROOT = pathlib.Path(__file__).resolve().parents[2]


class StatusAndTermsTests(SimpleTestCase):
    """B5, B6: statuses and terms say what they mean, in the words of the glossary (docs/dev/glossary)."""

    def test_the_statuses_are_named_without_the_misleading_words(self) -> None:
        from rentalars.packing.models import PacklistStatus
        from rentalars.projects.models import CaseStatus, ProjectStatus

        with translation.override("de"):
            # "zurück" was the word the project status dropped because it read like the Back button.
            self.assertEqual(str(PacklistStatus.RETURNED.label), "zurückgenommen")
            # "Backlog" read as "Rückstand" – a payment in arrears.
            self.assertEqual(str(CaseStatus.BACKLOG.label), "zurückgestellt")
            self.assertEqual(str(ProjectStatus.CONFIRMED_OPEN.label), "Bestätigt – Preise und Einzelheiten offen")
            # The same English word, the other direction: a subrental goes back to the supplier ("zurückgegeben").
            from rentalars.projects.models import SubrentalStatus

            self.assertEqual(str(SubrentalStatus.RETURNED.label), "zurückgegeben")

    def test_a_container_is_not_a_device(self) -> None:
        """ "Gerät" is for electrical devices and fixtures; the case or rack that holds material is the "Behälter"."""
        import polib

        catalogue = polib.pofile(str(ROOT / "locale" / "de" / "LC_MESSAGES" / "django.po"))
        found = []
        for entry in catalogue:
            if entry.obsolete or not re.search("container", entry.msgid, re.IGNORECASE):
                continue
            texts = [entry.msgstr, *entry.msgstr_plural.values()]
            if any("Gerät" in text for text in texts):
                found.append(entry.msgid[:60])
        self.assertEqual(found, [])


class SpellingTests(SimpleTestCase):
    """B8, B9, B12: capital letters, dates and the empty entry of a list are written the same everywhere."""

    def test_nothing_makes_the_rest_of_a_word_small(self) -> None:
        """``str.capitalize()`` writes "Freie kraft"; Django's ``capfirst`` leaves the rest as it is."""
        found = []
        for path in (ROOT / "rentalars").rglob("*.py"):
            if "migrations" in path.parts:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if ".capitalize()" in line:
                    found.append(f"{path.relative_to(ROOT)}:{number}")
        self.assertEqual(found, [])

    def test_no_template_writes_a_year_with_two_digits(self) -> None:
        """ "06.11.26" and "06.11.2026" for the same day on two pages – and "27.09.26 – 27.09.27" is a riddle."""
        found = []
        pattern = re.compile(r"""\|date:["'][^"']*\.y\b[^"']*["']""")
        for path in (ROOT / "templates").rglob("*.html"):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    found.append(f"{path.relative_to(ROOT)}:{number}")
        self.assertEqual(found, [])

    def test_no_date_is_written_in_a_fixed_german_pattern(self) -> None:
        """``strftime("%d.%m.%Y")`` writes the German date to English readers; ``local_pattern`` follows the language."""
        found = []
        pattern = re.compile(r"""strftime\(\s*["']%d\.%m""")
        # The formats of files and a command line are German by their own rule (the text of the module explains it).
        fixed_by_rule = {"i18n.py", "import_exports.py", "datev.py", "gateway.py"}
        for path in (ROOT / "rentalars").rglob("*.py"):
            if "migrations" in path.parts or path.name in fixed_by_rule:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    found.append(f"{path.relative_to(ROOT)}:{number}")
        self.assertEqual(found, [])

    def test_the_hours_in_the_history_are_written_in_the_language_of_the_reader(self) -> None:
        """ "5.50" is what is stored; German readers get "5,5", English readers "5.5"."""
        from rentalars.accounts.rights import Rights
        from rentalars.core.history import describe

        entry = self.entry()
        with translation.override("de"):
            self.assertIn("(5,5 Std.)", describe([entry], Rights())[0].summary)
        with translation.override("en"):
            self.assertIn("(5.5 h)", describe([entry], Rights())[0].summary)

    def entry(self):  # type: ignore[no-untyped-def]
        from types import SimpleNamespace

        from rentalars.core.models import AuditAction
        from rentalars.projects.models import CrewLine

        content_type = SimpleNamespace(model_class=lambda: CrewLine)
        return SimpleNamespace(
            content_type=content_type,
            action=AuditAction.EVENT,
            event="crew_line.adopted_from_times",
            changes={"person": "Anna", "hours": "5.50"},
        )


class EmptyEntryTests(UiTestCase):
    """B12: a list without a choice says "– bitte wählen –", not Django's dashes."""

    def test_the_forms_that_showed_dashes_say_please_choose(self) -> None:
        for name, args in (
            ("projects:create", []),
            ("products:create", []),
            ("documents:free_new", []),
        ):
            try:
                url = reverse(name, args=args)
            except Exception:
                continue
            page = self.client.get(url)
            if page.status_code != 200:
                continue
            self.assertNotIn("---------", page.content.decode(), name)

    def test_the_text_is_translated(self) -> None:
        from django.db.models import fields

        from rentalars.core.choices import replace_dashes

        replace_dashes()
        with translation.override("de"):
            self.assertEqual(str(fields.BLANK_CHOICE_DASH[0][1]), "– bitte wählen –")


class ApprovalSelectAllTests(PeriodPageCase):
    """V14: the approval of times can choose all rows at once and names the project."""

    def test_one_box_chooses_all_and_the_project_is_named(self) -> None:
        self.divide()
        page = self.assert_ok(self.manager.get(reverse("timetracking:approval")))
        self.assertEqual(page.count("data-select-all"), 1)
        self.assertIn("data-select-line", page)
        self.assertIn("Stadtfest", page)


class AboutPagesTests(UiTestCase):
    """V21 – V25: the full texts are pages of the program, with a way back."""

    def test_a_full_text_is_a_page_with_the_viewport(self) -> None:
        self.client.logout()
        for name in ("license", "additional-terms", "third-party"):
            page = self.client.get(reverse("core:about_page", args=[name]))
            self.assertEqual(page.status_code, 200, name)
            html = page.content.decode()
            self.assertIn('name="viewport"', html, name)
            # The way back, which the page had not: to the notices and to the login.
            self.assertIn(reverse("core:about"), html)
            self.assertIn(reverse("accounts:login"), html)

    def test_the_plain_text_stays_where_it_was(self) -> None:
        self.client.logout()
        response = self.client.get(reverse("core:about_text", args=["license"]))
        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")

    def test_an_unknown_text_is_not_found(self) -> None:
        self.assertEqual(self.client.get("/about/unknown/").status_code, 404)

    def test_the_german_notice_says_von_not_by(self) -> None:
        self.client.logout()
        with translation.override("de"):
            page = self.client.get(reverse("core:about"), HTTP_ACCEPT_LANGUAGE="de").content.decode()
        self.assertNotIn("by fld-vt.de", page)
        self.assertIn("von fld-vt.de", page)
        # "§ 7b" must not break between the sign and the number.
        self.assertIn("§ 7b", page)
        self.assertNotIn("§ 7 b", page)


class CustomerContactsTests(UiTestCase):
    """V8: the contacts of a customer are a list under one another in the narrow box, not a table that overflows."""

    def test_contacts_are_a_list(self) -> None:
        from tests.helpers import make_customer

        customer = make_customer("Musik GmbH")
        customer.contacts.create(name="Anna Becker", email="anna@musik.example", phone="030 1")
        page = self.client.get(reverse("customers:detail", args=[customer.pk])).content.decode()
        self.assertIn("Anna Becker", page)
        self.assertIn('class="contact-list"', page)


class HelpBoxTests(UiTestCase):
    """V18: the three explanations on the tab "Zugriff" are one box that folds."""

    def test_one_box_holds_the_explanations(self) -> None:
        from tests.helpers import make_project

        project = make_project("Stadtfest")
        page = self.client.get(reverse("projects:members", args=[project.pk])).content.decode()
        self.assertEqual(page.count('class="help-box"'), 1)
        self.assertNotIn('class="note accent"', page)


class NavigationLabelsTests(UiTestCase):
    """V19 (review): the name read out for "‹ früher" contains what is seen (WCAG 2.5.3 – label in name)."""

    def test_the_week_links_carry_their_visible_text_in_the_name(self) -> None:
        page = self.client.get(reverse("schedule:calendar") + "?view=week").content.decode()
        self.assertIn('‹ früher<span class="visually-hidden"> – vorige Woche</span>', page)
        self.assertIn('später ›<span class="visually-hidden"> – nächste Woche</span>', page)
        self.assertNotIn('aria-label="vorherige Woche"', page)
