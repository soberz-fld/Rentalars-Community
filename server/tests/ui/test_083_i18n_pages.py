# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages, area "i18n": German and English (UIX-029) – the own language, the user's language in the user
administration, the language of the documents, the login page following the browser, the manual, and every main
page in English without German left over.
"""

from __future__ import annotations

import collections
import re

from django.test import Client
from django.urls import reverse

from rentalars.accounts.models import User
from rentalars.core import start_data
from rentalars.core.models import AuditLogEntry, CompanyProfile
from rentalars.masterdata.models import Unit
from tests.helpers import add_line, make_customer, make_person, make_product, make_project, plan
from tests.ui.base import UiTestCase, form_data

#: Words that give German away on an English page. Words that are English as well ("Status", "Material",
#: "Personal", "Tag", "Name", "Rider") are not on the list.
GERMAN = re.compile(
    r"[äöüÄÖÜß]|\b(und|oder|nicht|keine|kein|für|mit|bitte|Bitte|Projekte|Kunden|Kunde|Rechnung|Angebot|Lieferschein|"
    r"Einstellungen|Speichern|Löschen|Abbrechen|Zurück|Stück|Woche|Monat|Neue?r?|Bearbeiten|Hinzufügen|Suche|"
    r"Benutzer|Anmelden|Abmelden|Zeitraum|Datum|Lager|Wiedervorlage|offen|erledigt|wählen|alle|Seite|Uhr|heute|"
    r"morgen|Einsatz|Einsätze|Zeiten|Stunden|Spesen|Packliste|Verfügbarkeit|Benachrichtigungen)\b"
)
#: Pages a crawl does not follow: they change something, deliver files, or are the manual (German until the English
#: one is written). The template texts in English or German (DOK-018) show the German default texts on
#: purpose; their English page is checked in tests/unit/test_090_small.py.
SKIP = re.compile(
    r"logout|delete|remove|revoke|/media/|\.pdf|\.csv|\.ics|\.zip|/export|download|/api/|/static/|/file|attachment|"
    r"/raw|calendar-feed|preview|/print|[?&](page|sort|q|view|month|week|day|start|span)=|/changes/|/manual/|"
    r"/audit-log/|/security-log/|/default-texts/|/about/[a-z-]+/"
)
#: What may stay German on an English page: names (a federal state), the DATEV term a field is named by in DATEV,
#: the headings an import recognises in German files (a list in lower case), and the history of a change from the
#: German to the English name ("Name: Lager → Warehouse").
ALLOWED = re.compile(
    r"Baden-Württemberg|Thüringen|Sachkontenlänge|^[a-zäöüß0-9 ,.()/%&+-]*, [a-zäöüß0-9 ,.()/%&+-]*$| → "
)


def english_installation() -> None:
    """Start data in English and a little English business data, as an English company would type it."""
    start_data.localise("en")
    profile = CompanyProfile.load()
    profile.name, profile.city, profile.document_language = "Light & Sound Ltd", "Bristol", "en"
    profile.save()
    customer = make_customer("City Council")
    project = make_project("Summer festival", customer=customer)
    add_line(project, make_product("L-100", "Spotlight"), 4)
    person = make_person("Ann Baker", rates={"Lighting technician": "35.00"})
    plan(project, "Lighting technician", person)
    Unit.objects.filter(name="Stück").update(name="Piece", abbreviation="pcs.")  # of the test helpers
    # A fresh English installation has no history written in German.
    AuditLogEntry.objects.all().delete()


def page_text(html: str) -> str:
    """The visible text of the main part of a page, one element per line."""
    main = html.split('id="content"', 1)[-1]
    main = re.sub(r"<script.*?</script>|<style.*?</style>|<textarea.*?</textarea>", " ", main, flags=re.S)
    main = re.sub(
        r"<(option|td|th|li|a|span|div|p|h\d|label|button|dd|dt|strong|small|summary|legend)\b", r"\n<\1", main
    )
    return re.sub(r"<[^>]+>", " ", main)


class OwnLanguageTests(UiTestCase):
    """UIX-029: "My account" → language; the whole interface follows."""

    def test_switch_to_english_and_back(self) -> None:
        url = reverse("accounts:account")
        page = self.assert_ok(self.client.get(url))
        self.assertIn('lang="de"', page)
        self.assertIn("Mein Konto", page)
        data = form_data(self.client.get(url), "language-language", **{"language-language": "en", "form": "language"})
        response = self.client.post(url, data, follow=True)
        page = self.assert_ok(response)
        self.assertIn('lang="en-GB"', page)
        self.assertIn("My account", page)
        self.assertIn("The language was changed.", page)
        self.assertEqual(User.objects.get(pk=self.admin_user.pk).language, "en")
        self.assertEqual(response["Content-Language"], "en")
        self.assertIn("Settings", self.assert_ok(self.client.get(reverse("core:home"))))  # the menu
        data = form_data(self.client.get(url), "language-language", **{"language-language": "", "form": "language"})
        page = self.assert_ok(self.client.post(url, data, follow=True))
        self.assertIn("Mein Konto", page)  # the installation's language again

    def test_htmx_partials_and_messages_in_the_language(self) -> None:
        self.admin_user.language = "en"
        self.admin_user.save()
        response = self.htmx("get", reverse("timetracking:quick"))
        self.assertEqual(response.status_code, 200)
        self.assertNotRegex(page_text('id="content"' + response.content.decode()), r"\bZeit erfassen\b")

    def test_login_page_follows_the_browser(self) -> None:
        anonymous = Client()
        english = anonymous.get(reverse("accounts:login"), HTTP_ACCEPT_LANGUAGE="en-GB,en;q=0.9")
        self.assertIn("Log in", english.content.decode())
        self.assertIn("Accept-Language", english["Vary"])
        german = anonymous.get(reverse("accounts:login"), HTTP_ACCEPT_LANGUAGE="de-DE")
        self.assertIn("Anmelden", german.content.decode())
        other = anonymous.get(reverse("accounts:login"), HTTP_ACCEPT_LANGUAGE="fr-FR")
        self.assertIn("Anmelden", other.content.decode())  # the installation's language


class AdministrationTests(UiTestCase):
    """UIX-029: the language of a user in the user administration; the language of the documents."""

    def test_invite_a_user_in_english(self) -> None:
        url = reverse("accounts:user_create")
        data = form_data(self.client.get(url), "username", username="tom", email="tom@example.com", language="en")
        self.client.post(url, data)
        user = User.objects.get(username="tom")
        self.assertEqual(user.language, "en")
        from django.core import mail

        self.assertEqual(mail.outbox[-1].subject, "Your access to Rentalars")

    def test_change_the_language_of_a_user(self) -> None:
        other = User.objects.create_user("uta", "uta@example.de", "pw-123456789")
        url = reverse("accounts:user_edit", args=[other.pk])
        page = self.assert_ok(self.client.get(url))
        self.assertIn("Wie die Installation (Deutsch)", page)
        self.client.post(url, form_data(self.client.get(url), "username", language="en"))
        self.assertEqual(User.objects.get(pk=other.pk).language, "en")

    def test_language_of_documents(self) -> None:
        url = reverse("core:company_settings")
        page = self.assert_ok(self.client.get(url))
        self.assertIn("Sprache der Dokumente", page)
        self.assertIn("bleibt, wie du es geschrieben hast", page)
        data = form_data(self.client.get(url), "company-document_language", **{"company-document_language": "en"})
        self.client.post(url, data)
        self.assertEqual(CompanyProfile.load().document_language, "en")


class ManualPageTests(UiTestCase):
    """UIX-029: "Manual" at the foot of the menu opens the manual in the user's language."""

    def test_german_manual_with_contents(self) -> None:
        home = self.assert_ok(self.client.get(reverse("core:home")))
        self.assertIn(f'href="{reverse("core:manual")}"', home)
        # Manual chapters: /manual/ is the table of contents, every chapter has a page of its own.
        page = self.assert_ok(self.client.get(reverse("core:manual")))
        self.assertIn("Dieses Handbuch erklärt die Arbeit mit Rentalars", page)
        self.assertIn('href="/manual/1/"', page)
        self.assertIn("1. Das Wichtigste in fünf Minuten", page)
        chapter = self.assert_ok(self.client.get(reverse("core:manual_chapter", args=[1])))
        self.assertIn('id="1-das-wichtigste-in-fünf-minuten"', chapter)
        self.assertNotIn("<script>alert", chapter)

    def test_english_page(self) -> None:
        self.admin_user.language = "en"
        self.admin_user.save()
        page = self.assert_ok(self.client.get(reverse("core:manual")))
        self.assertIn("<h1>Manual</h1>", page)
        self.assertIn('lang="en-GB"', page)
        self.assertIn("1. The essentials in five minutes", page)


class EnglishPagesTests(UiTestCase):
    """UIX-029: every main page in English, without German left over – a crawl from the start page."""

    LIMIT = 400

    def test_crawl(self) -> None:
        english_installation()
        self.admin_user.language = "en"
        self.admin_user.save()
        queue = collections.deque([reverse("core:home")])
        seen: set[str] = set()
        leftovers: dict[str, str] = {}
        while queue and len(seen) < self.LIMIT:
            url = queue.popleft()
            if url in seen:
                continue
            seen.add(url)
            response = self.client.get(url)
            self.assertLess(response.status_code, 500, url)
            if response.status_code != 200 or "text/html" not in response.get("Content-Type", ""):
                continue
            html = response.content.decode()
            if "<html" in html:  # a partial for a dialog has no html element of its own
                self.assertIn('lang="en', html, url)
            for href in re.findall(r'href="(/[^"#]*)"', html):
                href = href.replace("&amp;", "&")
                if href not in seen and not SKIP.search(href):
                    queue.append(href)
            for line in page_text(html).splitlines():
                line = " ".join(line.split())
                # "EÜR" is the name of the statement in German tax law and stays in an English text
                if line and GERMAN.search(line.replace("EÜR", "EUR")) and not ALLOWED.search(line):
                    leftovers.setdefault(line[:120], url)
        self.assertGreater(len(seen), 60)
        self.maxDiff = None
        self.assertEqual(leftovers, {}, f"German on English pages ({len(seen)} pages read)")
