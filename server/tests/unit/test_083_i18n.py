# SPDX-License-Identifier: GPL-3.0-or-later
"""German and English (UIX-029): languages per user and per company, formats, texts written for each reader,
documents to customers, start data, the manual.
"""

from __future__ import annotations

import datetime
import tempfile
from decimal import Decimal
from pathlib import Path

from django.core import mail
from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.utils import translation

from rentalars.accounts import services as account_services
from rentalars.accounts.forms import ResetPasswordForm
from rentalars.accounts.models import Role, User
from rentalars.automations.engine import fill, placeholders_of
from rentalars.automations.models import Trigger
from rentalars.core import i18n, manual, start_data
from rentalars.core.i18n import LazyCall, LocalText, file_name, local_pattern
from rentalars.core.models import CompanyProfile
from rentalars.core.money import format_decimal, format_money, parse_decimal
from rentalars.documents import services as document_services
from rentalars.documents.content import unit_code
from rentalars.documents.models import DocumentKind, DocumentTemplate
from rentalars.documents.pdf import render_html
from rentalars.documents.xrechnung import build_xml
from rentalars.mail.signature import render_signature
from rentalars.masterdata.models import Category, DocumentType, StorageLocation, Unit
from rentalars.notifications.models import Kind, Notification
from rentalars.notifications.services import notify
from rentalars.personnel.models import JobFunction
from tests.helpers import RentalarsTestCase, make_person, make_user
from tests.unit.test_062_documents import stadtfest


def in_english(user: User) -> User:
    user.language = "en"
    user.save(update_fields=["language"])
    return user


class PatternTests(SimpleTestCase):
    """UIX-029: German date patterns become British ones while English is active; German stays as it was."""

    def test_german_stays(self) -> None:
        with translation.override("de"):
            for pattern in ("d.m.Y", "D d.m. H:i", "%d.%m.%Y %H:%M", "Y-m-d", "H:i"):
                self.assertEqual(local_pattern(pattern), pattern)

    def test_english_writes_day_and_month_with_slashes(self) -> None:
        with translation.override("en"):
            self.assertEqual(local_pattern("d.m.Y"), "d/m/Y")
            self.assertEqual(local_pattern("D d.m.y H:i"), "D d/m/y H:i")
            self.assertEqual(local_pattern("D d.m. H:i"), "D d/m H:i")
            self.assertEqual(local_pattern("l, j. F"), "l, j F")
            self.assertEqual(local_pattern("j."), "j")
            self.assertEqual(local_pattern("%d.%m.%Y %H:%M"), "%d/%m/%Y %H:%M")
            self.assertEqual(local_pattern("%d.%m. %H:%M"), "%d/%m %H:%M")
            # Machine formats and patterns without day and month are left alone.
            for pattern in ("Y-m-d", "c", "H:i", "F Y", "Y-m-d\\TH:i", "%Y%m%d"):
                self.assertEqual(local_pattern(pattern), pattern)

    def test_the_date_filter_of_every_template(self) -> None:
        template = Template('{{ day|date:"d.m.Y" }} {{ moment|date:"D d.m. H:i" }} {{ day|date:"Y-m-d" }}')
        context = Context({"day": datetime.date(2026, 10, 16), "moment": datetime.datetime(2026, 10, 16, 14, 30)})
        with translation.override("de"):
            self.assertEqual(template.render(context), "16.10.2026 Fr 16.10. 14:30 2026-10-16")
        with translation.override("en"):
            self.assertEqual(template.render(context), "16/10/2026 Fri 16/10 14:30 2026-10-16")

    def test_django_formats_are_british(self) -> None:
        from django.utils import formats

        with translation.override("en"):
            self.assertEqual(formats.date_format(datetime.date(2026, 10, 16), "SHORT_DATE_FORMAT"), "16/10/2026")
            self.assertEqual(formats.time_format(datetime.time(14, 30)), "14:30")


class NumberTests(SimpleTestCase):
    """UIX-029: decimal point and thousands comma in English; German as before."""

    def test_money(self) -> None:
        with translation.override("de"):
            self.assertEqual(format_money(Decimal("1234.5")), "1.234,50 €")
            self.assertEqual(format_money(Decimal("-3")), "-3,00 €")
        with translation.override("en"):
            self.assertEqual(format_money(Decimal("1234.5")), "€1,234.50")
            self.assertEqual(format_money(Decimal("-3")), "-€3.00")
            self.assertEqual(format_money(Decimal("1234.5"), currency=""), "1,234.50")

    def test_numbers_and_their_reading(self) -> None:
        with translation.override("de"):
            self.assertEqual(format_decimal(Decimal("1.5")), "1,5")
            self.assertEqual(parse_decimal("1.234,5"), Decimal("1234.5"))
        with translation.override("en"):
            self.assertEqual(format_decimal(Decimal("1.5")), "1.5")
            self.assertEqual(parse_decimal("1,234.5"), Decimal("1234.5"))
        template = Template("{% load rentalars %}{{ count|thousands }}")
        with translation.override("en"):
            self.assertEqual(template.render(Context({"count": 20115})), "20,115")
        with translation.override("de"):
            self.assertEqual(template.render(Context({"count": 20115})), "20.115")

    def test_a_decimal_field_accepts_the_format_shown(self) -> None:
        from rentalars.core.forms import SetupForm

        with translation.override("en"):
            field = SetupForm().fields["default_tax_rate"]
            self.assertEqual(field.clean("19.5"), Decimal("19.5"))
        with translation.override("de"):
            field = SetupForm().fields["default_tax_rate"]
            self.assertEqual(field.clean("19,5"), Decimal("19.5"))


class LanguageOfRequestTests(RentalarsTestCase):
    """UIX-029: the user's language; without login the browser's; else the installation's."""

    def request(self, header: str = "", user: User | None = None, path: str = "/") -> object:
        from django.contrib.auth.models import AnonymousUser

        request = RequestFactory().get(path, HTTP_ACCEPT_LANGUAGE=header)
        request.user = user or AnonymousUser()
        return request

    def test_browser(self) -> None:
        self.assertEqual(i18n.request_language(self.request("en-GB,en;q=0.9,de;q=0.5")), "en")
        self.assertEqual(i18n.request_language(self.request("fr-FR,de;q=0.4,en;q=0.8")), "en")
        self.assertEqual(i18n.request_language(self.request("de-AT")), "de")
        self.assertEqual(i18n.request_language(self.request("fr, es")), "de")  # the installation's
        self.assertEqual(i18n.request_language(self.request("")), "de")

    def test_user(self) -> None:
        user = make_user("bea")
        self.assertEqual(i18n.request_language(self.request("en", user)), "de")  # pages: the installation's
        self.assertEqual(i18n.request_language(self.request("en", user, "/api/v1/me")), "en")  # API: the client's
        in_english(user)
        self.assertEqual(i18n.request_language(self.request("de", user)), "en")
        self.assertEqual(i18n.request_language(self.request("de", user, "/api/v1/me")), "en")

    @override_settings(LANGUAGE_CODE="en")
    def test_installation_language(self) -> None:
        self.assertEqual(i18n.installation_language(), "en")
        self.assertEqual(i18n.request_language(self.request("fr")), "en")


class TextsForEachReaderTests(RentalarsTestCase):
    """UIX-029: a notification is written in the language of each user who gets it – the e-mail as well."""

    def test_notification_in_two_languages(self) -> None:
        german, english = make_user("dora"), in_english(make_user("ed"))
        with translation.override("de"):
            notify(
                [german, english],
                Kind.SYSTEM_ERROR,
                LocalText(translation.gettext_lazy("Ready: %(task)s"), task="Export"),
                body=LocalText(
                    translation.gettext_lazy("Last successful fetch: %(when)s"),
                    when=LazyCall(i18n.format_date, datetime.date(2027, 3, 1)),
                ),
            )
        self.assertEqual(Notification.objects.get(user=german).title, "Fertig: Export")
        self.assertEqual(Notification.objects.get(user=english).title, "Ready: Export")
        self.assertEqual(Notification.objects.get(user=english).body, "Last successful fetch: 01/03/2027")
        self.assertEqual(Notification.objects.get(user=german).body, "Letzter erfolgreicher Abruf: 01.03.2027")

    def test_the_mail_of_a_notification(self) -> None:
        english = in_english(make_user("ed"))
        with translation.override("de"), self.captureOnCommitCallbacks(execute=True):
            notify([english], Kind.SYSTEM_ERROR, "Hallo")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("You can switch these messages off", mail.outbox[0].body)

    def test_invitation_and_password_link_in_the_users_language(self) -> None:
        with translation.override("de"):
            user = account_services.invite_user(username="fred", email="fred@example.de", language="en")
        self.assertEqual(user.language, "en")
        self.assertEqual(mail.outbox[-1].subject, "Your access to Rentalars")
        mail.outbox.clear()
        with translation.override("de"):
            form = ResetPasswordForm({"email": "fred@example.de"})
            self.assertTrue(form.is_valid())
            form.save(
                domain_override="rentalars.example.com",
                email_template_name="accounts/email/password_reset.txt",
                subject_template_name="accounts/email/password_reset_subject.txt",
            )
        self.assertEqual(mail.outbox[-1].subject, "Reset your Rentalars password")

    def test_background_task_in_the_language_of_who_started_it(self) -> None:
        from rentalars.core import jobs

        english = in_english(make_user("ed"))
        seen_languages.clear()
        jobs.register("i18n-test", "tests.unit.test_083_i18n:record_language")
        with self.settings(JOBS_RUN_INLINE=True), translation.override("de"):
            jobs.start_job("i18n-test", {}, user=english, title="Test")
        self.assertEqual(seen_languages, ["en"])
        self.assertEqual(Notification.objects.filter(user=english).first().title, "Ready: Test")

    def test_file_names(self) -> None:
        with translation.override("de"):
            self.assertEqual(file_name("timesheet", extension="pdf"), "Stundenzettel.pdf")
        with translation.override("en"):
            self.assertEqual(file_name("price_overview", "2027-0042", extension="csv"), "Price-overview-2027-0042.csv")


seen_languages: list[str] = []


def record_language(job: object) -> str:
    """A background task that notes the language it runs in."""
    seen_languages.append(translation.get_language())
    return ""


class PlaceholderTests(RentalarsTestCase):
    """UIX-029: the English names of the placeholders work as well as the German ones."""

    def test_automations(self) -> None:
        values = {"firma": "Licht & Ton", "datum": "01.03.2027", "projekt": "2027-0001 Stadtfest"}
        self.assertEqual(fill("{firma}, {datum}: {projekt}", values), "Licht & Ton, 01.03.2027: 2027-0001 Stadtfest")
        self.assertEqual(fill("{company}, {date}: {project}", values), "Licht & Ton, 01.03.2027: 2027-0001 Stadtfest")
        self.assertEqual(fill("{unknown}", values), "{unknown}")

    def test_the_form_offers_the_names_of_the_language(self) -> None:
        with translation.override("de"):
            self.assertIn("{firma}", [token for token, _label in placeholders_of(Trigger.INQUIRY)])
        with translation.override("en"):
            tokens = [token for token, _label in placeholders_of(Trigger.INQUIRY)]
            self.assertIn("{company}", tokens)
            self.assertIn("{sender}", tokens)
            self.assertNotIn("{firma}", tokens)

    def test_signature(self) -> None:
        user = make_user("gina")  # every account has its person (AUT-026)
        user.person.first_name = "Gina"
        user.person.save()
        CompanyProfile.objects.update_or_create(pk=1, defaults={"name": "Licht und Ton"})
        signature = render_signature(user, "{vorname} – {first_name}, {company}")
        self.assertEqual(signature.text, "Gina – Gina, Licht und Ton")


class DocumentLanguageTests(RentalarsTestCase):
    """UIX-029: documents to customers in the language of the company's documents; typed texts stay."""

    def setUp(self) -> None:
        super().setUp()
        self.festival = stadtfest()
        profile = CompanyProfile.load()
        profile.document_language = "en"
        profile.save()

    def test_an_offer_in_english_while_the_user_works_in_german(self) -> None:
        with translation.override("de"):
            content = document_services.build_content(
                self.festival.project, DocumentKind.OFFER, number="AN-1", issued_on=datetime.date(2027, 3, 1)
            )
            html = render_html(content, document_services.template_for(DocumentKind.OFFER))
            self.assertEqual(translation.get_language(), "de")  # the user's language is untouched
        self.assertIn("Total net", html)
        self.assertIn("Date of service", html)
        self.assertNotIn("Summe netto", html)
        self.assertIn('lang="en-GB"', html)
        self.assertIn("01/03/2027", html)
        self.assertIn("Licht", html)  # the group as typed
        details = "".join(position.details for section in content.sections for position in section.positions)
        self.assertIn("10/03/2027 08:00", details)  # the crew line, written the British way

    def test_start_texts_in_english_typed_templates_stay_as_typed(self) -> None:
        DocumentTemplate.objects.filter(kind=DocumentKind.OFFER).delete()
        self.assertEqual(document_services.template_for(DocumentKind.OFFER).title, "Quotation")
        DocumentTemplate.objects.filter(kind=DocumentKind.ORDER_CONFIRMATION).update(title="Auftragsbestätigung")
        content = document_services.build_content(
            self.festival.project, DocumentKind.ORDER_CONFIRMATION, number="AB-1", issued_on=datetime.date(2027, 3, 1)
        )
        self.assertEqual(content.title, "Auftragsbestätigung")

    def test_the_electronic_invoice_keeps_its_codes(self) -> None:
        content = document_services.build_content(
            self.festival.project, DocumentKind.INVOICE, number="RE-1", issued_on=datetime.date(2027, 3, 1)
        )
        with translation.override("en"):
            english = build_xml(content).decode()
        with translation.override("de"):
            german = build_xml(content).decode()
        for code in ('currencyID="EUR"', "<cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode>", "2027-03-01"):
            self.assertIn(code, english)
            self.assertIn(code, german)
        self.assertEqual(english.count("unitCode="), german.count("unitCode="))
        self.assertIn("Payable by", english)

    def test_unit_codes_of_english_abbreviations(self) -> None:
        for german, english in (("Stk.", "pcs."), ("Std.", "h"), ("Tag", "day"), ("psch.", "flat"), ("Set", "kit")):
            self.assertEqual(unit_code(german), unit_code(english))


class StartDataTests(RentalarsTestCase):
    """UIX-029: the start data of a new installation in English – only records that still have their start names."""

    def test_to_english_and_back(self) -> None:
        Role.objects.filter(name="Lager").update(description="Unser Lager")  # changed by the company: kept
        renamed = start_data.localise("en")
        self.assertGreater(renamed, 20)
        self.assertTrue(Role.objects.filter(name="Freelancer").exists())
        self.assertTrue(Role.objects.filter(name="Lager").exists())
        self.assertTrue(Unit.objects.filter(name="Piece (rental)", abbreviation="pcs.").exists())
        self.assertEqual(Category.objects.get(parent__isnull=True, code="T").name, "Sound")
        self.assertTrue(StorageLocation.objects.filter(name="Main warehouse").exists())
        self.assertTrue(DocumentType.objects.filter(name="Stage plan").exists())
        function = JobFunction.objects.get(name="Lighting technician")
        self.assertEqual(function.service_product.name, "Lighting technician")
        start_data.localise("de")
        self.assertTrue(Role.objects.filter(name="Freie Kraft").exists())
        self.assertEqual(Category.objects.get(parent__isnull=True, code="T").name, "Ton")

    def test_a_freelancer_gets_the_english_role(self) -> None:
        start_data.localise("en")
        person = make_person("Hans Frei", kind="freelancer")
        self.assertEqual(list(person.user.roles.values_list("name", flat=True)), ["Freelancer"])

    def test_the_setup_in_english(self) -> None:
        from rentalars.core.models import SystemSettings
        from rentalars.core.setup import complete_setup
        from rentalars.projects.models import ProjectTemplate

        SystemSettings.objects.filter(pk=1).update(setup_completed=False)
        administrator = complete_setup(
            {
                "company_name": "Light & Sound Ltd",
                "language": "en",
                "username": "boss",
                "email": "boss@example.com",
                "password": "a-long-password-1",
                "project_prefix": "{year}-",
                "project_next": 1,
                "customer_next": 10001,
                "material_next": 1,
                "default_tax_rate": Decimal("19"),
            }
        )
        self.assertEqual(administrator.language, "en")
        self.assertEqual(CompanyProfile.load().document_language, "en")
        self.assertTrue(administrator.roles.filter(name="Administrator").exists())
        self.assertTrue(ProjectTemplate.objects.filter(name=start_data.DRY_HIRE_ENGLISH_NAME).exists())
        self.assertTrue(Role.objects.filter(name="Project management").exists())


class ManualTests(SimpleTestCase):
    """UIX-029: the manual from the packaged Markdown, cleaned, with the anchors GitHub gives."""

    def test_anchors(self) -> None:
        self.assertEqual(manual.github_slug("1. Das Wichtigste in fünf Minuten"), "1-das-wichtigste-in-fünf-minuten")
        self.assertEqual(manual.github_slug("Die Seite „Fehlbestände“"), "die-seite-fehlbestände")

    def test_cleaned_with_contents_and_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base / "docs/handbuch").mkdir(parents=True)
            (base / "docs/handbuch/benutzerhandbuch.md").write_text(
                "# Handbuch\n\n## 1. Anfang\n\nText mit [Link](#1-anfang) und [Datei](../betrieb/import.md).\n\n"
                "<script>alert(1)</script>\n\n| a | b |\n|---|---|\n| 1 | 2 |\n",
                encoding="utf-8",
            )
            with override_settings(BASE_DIR=base):
                # Manual chapters: the manual is split into chapters; this one holds everything below "## 1.".
                english = manual.manual_for("en")
                chapter = english.chapter(1)
                self.assertTrue(english.fallback)
                self.assertIn('id="1-anfang"', chapter.html)
                self.assertIn('href="#1-anfang"', chapter.html)
                self.assertNotIn("<script", chapter.html)
                self.assertNotIn("import.md", chapter.html)
                self.assertIn('<table tabindex="0">', chapter.html)  # scrollable on a phone, reachable by keyboard
                self.assertEqual(chapter.toc[0]["id"], "1-anfang")
                (base / "docs/en").mkdir()
                (base / "docs/en/user-manual.md").write_text("# Manual\n\n## 1. Start\n", encoding="utf-8")
                english = manual.manual_for("en")
                self.assertFalse(english.fallback)
                self.assertIn('id="1-start"', english.chapter(1).html)


class TableHeadingTests(SimpleTestCase):
    """UIX-029: every column heading of every list is lazy – written when a page is shown, in its reader's
    language, never translated once when the module is loaded (hidden headings "Actions", "Choose" were German).
    """

    def test_every_heading_is_lazy(self) -> None:
        import importlib
        import pkgutil

        from django.apps import apps
        from django.urls import get_resolver
        from django.utils.functional import Promise

        from rentalars.core.tables import REGISTRY

        get_resolver().url_patterns  # noqa: B018 – loads every view and with it every table
        for config in apps.get_app_configs():
            if config.name.startswith("rentalars."):
                for module in pkgutil.iter_modules([config.path]):
                    if "table" in module.name:
                        importlib.import_module(f"{config.name}.{module.name}")
        self.assertGreater(len(REGISTRY), 25)
        eager = [
            f"{key}.{column.key}: {column.label!r}"
            for key, definition in REGISTRY.items()
            if not key.startswith("test_")  # tables other tests define for themselves
            for column in definition.columns
            if not isinstance(column.label, Promise) and any(letter.isalpha() for letter in str(column.label))
        ]
        self.assertEqual(eager, [])
        actions = next(column for column in REGISTRY["automation_rules"].columns if column.key == "actions")
        with translation.override("en"):
            self.assertIn(">Actions<", str(actions.label))
        with translation.override("de"):
            self.assertIn(">Aktionen<", str(actions.label))


class ReviewedTextsTests(SimpleTestCase):
    """UIX-029, English review: times without "o'clock", an automation's name in the reader's quotation
    marks, times of day in the history without seconds.
    """

    def test_time_of_day(self) -> None:
        from django.utils import timezone

        from rentalars.schedule.services import clock_text

        moment = timezone.make_aware(datetime.datetime(2027, 3, 10, 8, 0))
        with translation.override("en"):
            self.assertEqual(clock_text(moment), "8:00")
        with translation.override("de"):
            self.assertEqual(clock_text(moment), "8:00 Uhr")

    def test_automation_as_author(self) -> None:
        from rentalars.core.history import actor_text

        with translation.override("en"):
            self.assertEqual(actor_text("Automation „Angebot nachfassen“"), "Automation “Angebot nachfassen”")
            self.assertEqual(actor_text("anna"), "anna")
        with translation.override("de"):
            self.assertEqual(actor_text("Automation “Follow up”"), "Automation „Follow up“")

    def test_time_in_the_history(self) -> None:
        from rentalars.core.history import _display, _Lookup
        from rentalars.projects.models import Project

        self.assertEqual(_display(Project, "follow_up_at", "17:30:00", _Lookup())[1], "17:30")
