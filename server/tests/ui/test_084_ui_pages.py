# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages, area "ui": the first tab of a service case is "Überblick" (PRJ-090); the correspondence looks the
same in a project and a service case, its block is "Zusammenfassung", the short overview without AI folded
(EML-050); the menu of the phone in the layout of every page (UIX-045)."""

from __future__ import annotations

import re

from django.urls import reverse

from rentalars.ai.models import AISummary
from rentalars.projects import service_cases
from tests.helpers import make_customer, make_project
from tests.ui.base import UiTestCase
from tests.ui.test_080_projects_pages import tabs_of
from tests.unit.test_083_ai import add_mail


def _same_shape(text: str, number: str = "") -> str:
    """The page below the tabs without what differs between two projects of the same mails: number, keys, times."""
    text = text.split('<nav class="tabs"', 1)[1].split("</nav>", 1)[1]  # head and tabs differ on purpose
    if number:
        text = text.replace(number, "N")
    text = re.sub(r"/projects/\d+/", "/projects/N/", text)
    text = re.sub(r"/mails/\d+/", "/mails/N/", text)
    text = re.sub(r'datetime="[^"]+"', 'datetime=""', text)
    return re.sub(r'name="csrfmiddlewaretoken" value="[^"]+"', "", text)


class ServiceCaseTabTests(UiTestCase):
    """PRJ-090 (amended): the first tab of a service case is called "Überblick", no longer "Servicefall"."""

    def setUp(self) -> None:
        super().setUp()
        self.case = service_cases.create_case(name="Beamer flackert", customer=make_customer("Jazzclub"))

    def test_the_first_tab_is_the_overview(self) -> None:
        """PRJ-090: "Überblick" first; the other tabs as before."""
        for name in ("projects:case_detail", "documents:list", "mail:project_mails", "projects:history"):
            with self.subTest(page=name):
                tabs = tabs_of(self.assert_ok(self.client.get(reverse(name, args=[self.case]))))
                self.assertEqual(tabs[0], "Überblick")
                self.assertNotIn("Servicefall", tabs)
                # "Chat" holds a badge and is not among what tabs_of reads.
                self.assertEqual(tabs[1:], ["Dokumente", "Korrespondenz", "Zugriff", "Verlauf"])
        page = self.assert_ok(self.client.get(reverse("projects:case_detail", args=[self.case])))
        self.assertIn(
            f'href="{reverse("projects:case_detail", args=[self.case])}" aria-current="page">Überblick</a>', page
        )
        self.assertIn('<span class="badge accent">Servicefall</span>', page)  # the case still says what it is

    def test_in_english(self) -> None:
        """UIX-029: the msgid is the English tab."""
        self.admin_user.language = "en"
        self.admin_user.save()
        tabs = tabs_of(self.assert_ok(self.client.get(reverse("projects:case_detail", args=[self.case]))))
        self.assertEqual(tabs[0], "Overview")

    def test_a_project_has_its_overview_first(self) -> None:
        """PRJ-104 (tab order): a project's "Überblick" (the deployment view) is the first tab, as in a case."""
        project = make_project("Stadtfest")
        tabs = tabs_of(self.assert_ok(self.client.get(reverse("projects:detail", args=[project.pk]))))
        self.assertEqual(tabs[:2], ["Überblick", "Planung"])
        self.assertEqual(tabs.count("Überblick"), 1)


class CorrespondenceTests(UiTestCase):
    """EML-050: the tab "Korrespondenz" of a project and of a service case, and its block "Zusammenfassung"."""

    MAILS = (
        ("Anfrage", "Können Sie uns ein Angebot für den 12.06.2027 schicken?", True, 0),
        ("Re: Anfrage", "Anbei das Angebot über 2.380,00 €.", False, 1),
        ("Re: Anfrage", "Passt der Aufbau am Donnerstag?", True, 2),
    )

    def setUp(self) -> None:
        super().setUp()
        customer = make_customer("Kulturamt")
        self.project = make_project("Stadtfest", customer=customer)
        self.case = service_cases.create_case(name="Stadtfest", customer=customer)
        for target in (self.project, self.case):
            for subject, text, incoming, days in self.MAILS:
                add_mail(target, subject, text, incoming=incoming, days=days)

    def summary_block(self, target: object) -> str:
        return self.assert_ok(self.htmx("get", reverse("ai:summary", args=[target.pk])))

    def test_the_same_page_in_a_project_and_a_service_case(self) -> None:
        """EML-050: one template – the same blocks and buttons, in the list and in the conversation."""
        for view in ("list", "conversation"):
            with self.subTest(view=view):
                pages = [
                    self.assert_ok(self.client.get(reverse("mail:project_mails", args=[target.pk]) + f"?view={view}"))
                    for target in (self.project, self.case)
                ]
                targets = (self.project, self.case)
                shapes = [_same_shape(page, target.number) for page, target in zip(pages, targets, strict=True)]
                self.assertEqual(shapes[0], shapes[1])
                for page in pages:
                    self.assertIn('id="ai-summary"', page)
                    self.assertIn("Die Zusammenfassung wird geladen …", page)
        blocks = [
            _same_shape('<nav class="tabs"></nav>' + self.summary_block(target), target.number)
            for target in (self.project, self.case)
        ]
        self.assertEqual(blocks[0], blocks[1])

    def test_the_block_is_called_summary_and_the_overview_is_folded(self) -> None:
        """EML-050: "Zusammenfassung" instead of "Überblick"; "Kurzüberblick ohne KI" folded, without AI as well."""
        for target in (self.project, self.case):
            with self.subTest(kind=target.kind):
                block = self.summary_block(target)
                self.assertIn('<h2 id="ai-summary-title">Zusammenfassung</h2>', block)
                self.assertNotIn(">Überblick<", block)
                self.assertIn('<details class="ai-overview">', block)
                self.assertNotIn('<details class="ai-overview" open', block)
                self.assertIn("<summary>Kurzüberblick ohne KI</summary>", block)
                self.assertIn("Passt der Aufbau am Donnerstag?", block)  # there, only folded

    def test_the_summary_by_ai_above_the_folded_overview(self) -> None:
        """EML-040, EML-050: a stored summary stands first, marked as made by AI; the short overview stays folded."""
        for target in (self.project, self.case):
            AISummary.objects.create(
                project=target,
                text="Die Kundin fragt nach dem Aufbau.",
                model="m",
                provider_label="Lokale KI",
                covered_projects=[target.pk],
                mail_count=3,
            )
            with self.subTest(kind=target.kind):
                block = self.summary_block(target)
                self.assertIn('<span class="visually-hidden">Zusammenfassung durch KI</span>', block)
                self.assertIn("von KI erstellt", block)
                self.assertLess(block.index("Die Kundin fragt nach dem Aufbau."), block.index("Kurzüberblick ohne KI"))
                self.assertIn('<details class="ai-overview">', block)

    def test_in_english(self) -> None:
        """UIX-029: the English block."""
        self.admin_user.language = "en"
        self.admin_user.save()
        page = self.assert_ok(self.client.get(reverse("mail:project_mails", args=[self.case.pk])))
        self.assertIn('<h2 id="ai-summary-title">Summary</h2>', page)
        self.assertIn("Loading the summary …", page)
        self.assertIn("<summary>Short overview without AI</summary>", self.summary_block(self.case))


class PhoneMenuMarkupTests(UiTestCase):
    """UIX-045: what the drawer needs on every page – the close button, the dimmed backdrop, the state of the button."""

    def test_on_every_page(self) -> None:
        page = self.assert_ok(self.client.get(reverse("projects:list")))
        self.assertIn('data-toggle-nav aria-controls="sidebar" aria-expanded="false" aria-label="Menü"', page)
        self.assertIn(
            'class="icon-btn nav-close" data-close-nav aria-controls="sidebar" aria-label="Menü schließen"', page
        )
        self.assertIn('<div class="nav-scrim" data-close-nav></div>', page)
        # The close button is the first thing in the menu, the backdrop right after it, before the page.
        self.assertLess(page.index('id="sidebar"'), page.index("nav-close"))
        self.assertLess(page.index("nav-close"), page.index('class="nav"'))
        self.assertLess(page.index('</nav>\n  <div class="nav-scrim"'), page.index('<main class="main"'))
