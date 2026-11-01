# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages, area "ai": Einstellungen → KI (EML-040, ADM-017), the overview and the AI summary of the
correspondence (EML-040, EML-044) and "Entwurf vorschlagen" in the mail form (ADM-017)."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.test import override_settings
from django.urls import reverse

from rentalars.ai.models import AICall, AIProvider, AISettings, AISummary, Source
from rentalars.core.models import BackgroundJob
from tests.ai_fake import FakeModelServer, write_local_file
from tests.helpers import make_customer, make_project, make_user
from tests.mailbox import configure_mailbox
from tests.ui.base import UiTestCase, form_data
from tests.unit.test_083_ai import add_mail


class AIPagesTestCase(UiTestCase):
    """A project with mails, a place for the file of the local AI, and the fake model server."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", customer=make_customer("Kulturamt"))
        add_mail(self.project, "Angebot", "Können Sie uns ein Angebot für den 12.06.2027 schicken?")
        add_mail(self.project, "Re: Angebot", "Anbei das Angebot über 2.380,00 €.", incoming=False, days=1)
        add_mail(self.project, "Re: Angebot", "Passt der Aufbau am Donnerstag?", days=2)
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        self.local_file = folder / "ai-local.conf"
        override = override_settings(RENTALARS_AI_LOCAL_FILE=str(self.local_file))
        override.enable()
        self.addCleanup(override.disable)
        self.fake = FakeModelServer().__enter__()
        self.addCleanup(self.fake.__exit__)

    def install_local(self) -> None:
        write_local_file(self.local_file, self.fake.url)

    def use(self, use: str, source: str, provider: AIProvider | None = None) -> None:
        ai_settings = AISettings.load()
        setattr(ai_settings, f"{use}_source", source)
        setattr(ai_settings, f"{use}_provider", provider)
        ai_settings.save()


class SettingsPageTests(AIPagesTestCase):
    """EML-040, ADM-017: Einstellungen → KI."""

    def test_the_settings_link_to_it(self) -> None:
        """EML-040: the page is listed in the settings."""
        text = self.assert_ok(self.client.get(reverse("core:administration")))
        self.assertIn(reverse("ai:settings"), text)
        self.assertIn("Zusammenfassungen der Korrespondenz mit lokaler KI", text)

    def test_without_local_ai_the_command_is_shown(self) -> None:
        """EML-040: not installed – the one command for the operator, everything off."""
        text = self.assert_ok(self.client.get(reverse("ai:settings")))
        self.assertIn("nicht installiert", text)
        self.assertIn("sudo rentalars ai install", text)
        self.assertIn("Zusammenfassungen mit lokaler KI einschalten", text)
        self.assertIn("Vorlagenvorschläge", text)
        self.assertIn("Später:", text)
        self.assertIn("Noch keine Schnittstelle.", text)

    def test_the_installed_local_ai_with_its_speed(self) -> None:
        """EML-040: installed, model, reachable; "Geschwindigkeit messen" keeps the result; the switch."""
        self.install_local()
        text = self.assert_ok(self.client.get(reverse("ai:settings")))
        self.assertIn("installiert", text)
        self.assertIn("antwortet", text)
        self.assertIn("Qwen2.5 1.5B Instruct (Q4_K_M)", text)
        self.assertIn("Lizenz Apache-2.0", text)
        response = self.client.post(reverse("ai:local_speed_test"), follow=True)
        self.assertIn("Die lokale KI hat in", " ".join(self.messages_of(response)))
        self.assertIn("12,5 Token pro Sekunde", self.assert_ok(response))
        response = self.client.post(reverse("ai:local_summaries"), {"on": "1"}, follow=True)
        self.assertEqual(AISettings.load().summary_source, Source.LOCAL)
        self.assertIn("Zusammenfassungen mit lokaler KI ausschalten", self.assert_ok(response))
        self.client.post(reverse("ai:local_summaries"), {"on": "0"})
        self.assertEqual(AISettings.load().summary_source, Source.OFF)

    def test_a_local_ai_that_does_not_answer(self) -> None:
        """EML-040: the file is there but the service is down – said on the page."""
        write_local_file(self.local_file, "http://127.0.0.1:9/v1")
        text = self.assert_ok(self.client.get(reverse("ai:settings")))
        self.assertIn("antwortet nicht", text)
        self.assertIn("Läuft der Dienst rentalars-ai?", text)

    def test_providers_and_uses(self) -> None:
        """ADM-017: an interface with a key that is never shown again; a cloud service is warned about."""
        page = self.client.get(reverse("ai:provider_create"))
        data = form_data(
            page,
            "base_url",
            name="Cloud",
            base_url="https://api.example.com/v1/",
            model="gpt-x",
            api_key="sk-geheim",
        )
        response = self.client.post(reverse("ai:provider_create"), data, follow=True)
        self.assert_ok(response)
        provider = AIProvider.objects.get()
        self.assertEqual((provider.base_url, provider.api_key), ("https://api.example.com/v1", "sk-geheim"))
        text = self.assert_ok(self.client.get(reverse("ai:settings")))
        self.assertIn("Cloud – Daten verlassen das Unternehmen", text)
        self.assertNotIn("sk-geheim", text)
        edit = self.client.get(reverse("ai:provider_edit", args=[provider.pk]))
        self.assertNotIn("sk-geheim", edit.content.decode())
        self.assertIn("Diese Adresse liegt im Internet", edit.content.decode())
        self.client.post(reverse("ai:provider_edit", args=[provider.pk]), form_data(edit, "base_url", model="gpt-y"))
        provider.refresh_from_db()
        self.assertEqual((provider.model, provider.api_key), ("gpt-y", "sk-geheim"))
        page = self.client.get(reverse("ai:settings"))
        response = self.client.post(
            reverse("ai:settings"), form_data(page, "summary", summary=f"p{provider.pk}", draft="local"), follow=True
        )
        text = self.assert_ok(response)
        self.assertIn("„Cloud“ liegt im Internet: Die Mails der Projekte verlassen", text)
        ai_settings = AISettings.load()
        self.assertEqual((ai_settings.summary_source, ai_settings.summary_provider), (Source.PROVIDER, provider))
        self.assertEqual(ai_settings.draft_source, Source.LOCAL)
        self.client.post(reverse("ai:provider_delete", args=[provider.pk]))
        self.assertFalse(AIProvider.objects.exists())
        self.assertEqual(AISettings.load().summary_source, Source.OFF)

    def test_the_key_does_not_follow_a_changed_server(self) -> None:
        """ADM-017: a new host without a new key removes the stored key – it never goes there."""
        provider = AIProvider(name="Cloud", base_url="https://api.example.com/v1", model="gpt-x")
        provider.api_key = "sk-SECRET"
        provider.save()
        url = reverse("ai:provider_edit", args=[provider.pk])
        self.client.post(url, form_data(self.client.get(url), "base_url", base_url="https://api.example.com/v2"))
        provider.refresh_from_db()
        self.assertEqual(provider.api_key, "sk-SECRET")  # same server, other path: the key stays
        with FakeModelServer(models=("gpt-x",)) as attacker:
            data = form_data(self.client.get(url), "base_url", base_url=attacker.url)
            response = self.client.post(url, data, follow=True)
            self.assertIn("wurde der gespeicherte API-Schlüssel entfernt", " ".join(self.messages_of(response)))
            provider.refresh_from_db()
            self.assertEqual((provider.base_url, provider.api_key), (attacker.url, ""))
            self.client.post(reverse("ai:provider_check", args=[provider.pk]))
            self.assertTrue(attacker.requests)
            self.assertNotIn("Authorization", attacker.requests[-1]["headers"])
            data = form_data(
                self.client.get(url), "base_url", base_url="https://other.example.com/v1", api_key="sk-NEW"
            )
            self.client.post(url, data)
            provider.refresh_from_db()
            self.assertEqual(provider.api_key, "sk-NEW")

    @override_settings(RENTALARS_NETWORK_ALLOW_INTERNAL=())
    def test_an_internal_address_needs_the_operator(self) -> None:
        """ADM-017, NFA-071: an internal base URL is refused at the field unless allowed."""
        page = self.client.get(reverse("ai:provider_create"))
        data = form_data(page, "base_url", name="Ollama", base_url="http://192.168.1.30:11434/v1", model="qwen")
        text = self.assert_ok(self.client.post(reverse("ai:provider_create"), data))
        self.assertIn("Die Adresse führt in ein internes Netz.", text)
        self.assertFalse(AIProvider.objects.exists())

    def test_checking_an_interface(self) -> None:
        """ADM-017: "Prüfen" asks for the models."""
        provider = AIProvider.objects.create(name="Ollama", base_url=self.fake.url, model="qwen2.5-1.5b-instruct")
        response = self.client.post(reverse("ai:provider_check", args=[provider.pk]), follow=True)
        self.assertIn("„Ollama“ antwortet.", self.messages_of(response))
        provider.model = "llama3"
        provider.save()
        response = self.client.post(reverse("ai:provider_check", args=[provider.pk]), follow=True)
        self.assertIn("bietet aber das Modell „llama3“ nicht an", " ".join(self.messages_of(response)))

    def test_the_log_of_calls(self) -> None:
        """ADM-017: use, provider, model, duration, sizes – no content."""
        AICall.objects.create(
            use="summary", provider_label="Lokale KI", model="qwen", duration_ms=1234, request_chars=500
        )
        text = self.assert_ok(self.client.get(reverse("ai:calls")))
        self.assertIn("Zusammenfassung der Korrespondenz", text)
        self.assertIn("1234 ms", text)
        self.assertIn("500 / 0", text)

    @override_settings(RENTALARS_NETWORK_ALLOW_INTERNAL=())
    def test_the_self_check_names_an_internal_interface(self) -> None:
        """ADM-017, NFA-071: an interface leading inside appears in the self-check like webhooks and mailboxes."""
        AIProvider.objects.create(name="Ollama", base_url="http://192.168.1.30:11434/v1", model="qwen")
        text = self.assert_ok(self.client.get("/administration/self-check/"))
        self.assertIn("KI-Schnittstelle Ollama", text)
        self.assertIn("192.168.1.30 – privates Netz", text)

    def test_only_the_settings_right_opens_it(self) -> None:
        """EML-040, AUT-015: who may not read the settings gets "not allowed"; read-only may not change."""
        browser = self.browser_for("paula", "Projektleitung")
        self.assertEqual(browser.get(reverse("ai:settings")).status_code, 403)
        self.assertEqual(browser.post(reverse("ai:local_summaries"), {"on": "1"}).status_code, 403)
        self.assertEqual(AISettings.load().summary_source, Source.OFF)


class CorrespondencePageTests(AIPagesTestCase):
    """EML-040, EML-044: the block "Überblick" on the correspondence page of a project and of a service case."""

    def test_the_overview_without_ai(self) -> None:
        """EML-044: always there – also with AI switched off."""
        text = self.assert_ok(self.client.get(reverse("mail:project_mails", args=[self.project.pk])))
        self.assertIn(reverse("ai:summary", args=[self.project.pk]), text)
        text = self.assert_ok(self.htmx("get", reverse("ai:summary", args=[self.project.pk])))
        self.assertIn("Kurzüberblick ohne KI", text)
        self.assertIn("2 empfangen, 1 gesendet", text)
        self.assertIn("12.06.2027", text)
        self.assertIn("2.380,00 €", text)
        self.assertIn("Passt der Aufbau am Donnerstag?", text)
        self.assertIn("empfangen – noch nicht beantwortet", text)
        self.assertIn("Zusammenfassungen mit KI sind ausgeschaltet", text)
        self.assertNotIn(">Zusammenfassen<", text)

    def test_summarise_with_the_local_ai(self) -> None:
        """EML-040: "Zusammenfassen" – in the background; labelled as made by AI with model and date; then out of date."""
        self.install_local()
        self.use("summary", Source.LOCAL)
        url = reverse("ai:summary", args=[self.project.pk])
        page = self.htmx("get", url)
        self.assertIn("Zusammenfassen", self.assert_ok(page))
        text = self.assert_ok(self.htmx("post", url))
        self.assertIn("von KI erstellt", text)
        self.assertIn("Geschrieben vom Modell qwen2.5-1.5b-instruct (Lokale KI) am 01.03.2027", text)
        self.assertIn("Überblick: Die Kundin fragt nach dem Aufbau am Freitag.", text)
        self.assertIn("Neu zusammenfassen", text)
        # EML-050: open right after "Zusammenfassen", folded whenever the block loads again.
        self.assertIn('<details class="ai-result" open>', text)
        self.assertIn('<details class="ai-result">', self.assert_ok(self.htmx("get", url)))
        add_mail(self.project, "Noch was", "Geht auch Samstag?", days=3)
        text = self.assert_ok(self.htmx("get", url))
        self.assertIn("veraltet", text)
        self.assertIn("1 neuere Mail ist nicht in der Zusammenfassung.", text)

    def test_without_htmx_back_to_the_correspondence(self) -> None:
        """EML-040: the button works without JavaScript as well."""
        self.install_local()
        self.use("summary", Source.LOCAL)
        response = self.client.post(reverse("ai:summary", args=[self.project.pk]), follow=True)
        self.assertIn("Die Zusammenfassung wird geschrieben.", " ".join(self.messages_of(response)))
        self.assertTrue(AISummary.objects.exists())

    def test_a_missing_local_ai_is_said(self) -> None:
        """EML-040: switched on but not installed – the reason instead of the button."""
        self.use("summary", Source.LOCAL)
        text = self.assert_ok(self.htmx("get", reverse("ai:summary", args=[self.project.pk])))
        self.assertIn("Die lokale KI ist nicht installiert.", text)

    def test_a_cloud_provider_is_warned_about_on_the_page(self) -> None:
        """EML-040, ADM-017: summaries by a cloud service – the warning next to the button."""
        provider = AIProvider.objects.create(name="Cloud", base_url="https://api.example.com/v1", model="x")
        self.use("summary", Source.PROVIDER, provider)
        text = self.assert_ok(self.htmx("get", reverse("ai:summary", args=[self.project.pk])))
        self.assertIn("„Zusammenfassen“ schickt die Mails an Cloud: Ihr Inhalt verlässt das Unternehmen.", text)

    def test_who_may_not_read_the_correspondence(self) -> None:
        """EML-040: rights – who may read the correspondence; warehouse staff may not."""
        self.install_local()
        self.use("summary", Source.LOCAL)
        storage = self.browser_for("luka", "Lager")
        self.assertEqual(storage.get(reverse("ai:summary", args=[self.project.pk])).status_code, 403)
        self.assertEqual(storage.post(reverse("ai:summary", args=[self.project.pk])).status_code, 403)
        reader = self.browser_for("nora", "Nur-Lesen")
        text = self.assert_ok(self.htmx("post", reverse("ai:summary", args=[self.project.pk]), client=reader))
        self.assertIn("von KI erstellt", text)

    def test_a_summary_of_parts_the_reader_may_not_read_is_hidden(self) -> None:
        """EML-040, PRJ-044: covering a part the reader may not read, the summary is not shown to him."""
        AISummary.objects.create(
            project=self.project,
            text="Geheime Teile",
            model="m",
            provider_label="p",
            covered_projects=[self.project.pk, 999_999],
        )
        reader = self.browser_for("nora", "Nur-Lesen")
        text = self.assert_ok(self.htmx("get", reverse("ai:summary", args=[self.project.pk]), client=reader))
        self.assertNotIn("Geheime Teile", text)
        self.assertIn("Teilprojekte, deren Korrespondenz du nicht lesen darfst", text)

    def test_a_service_case_has_it_too(self) -> None:
        """EML-040: the summary exists in a project and in a service case – the correspondence page of a case."""
        from rentalars.projects.models import ProjectKind

        case = make_project("Lautsprecher defekt", customer=self.project.customer, kind=ProjectKind.SERVICE_CASE)
        add_mail(case, "Defekt", "Der Lautsprecher brummt. Können Sie ihn abholen?")
        self.install_local()
        self.use("summary", Source.LOCAL)
        text = self.assert_ok(self.client.get(reverse("mail:project_mails", args=[case.pk])))
        self.assertIn(reverse("ai:summary", args=[case.pk]), text)
        text = self.assert_ok(self.htmx("post", reverse("ai:summary", args=[case.pk])))
        self.assertIn("von KI erstellt", text)
        self.assertIn("Können Sie ihn abholen?", text)


class DraftPageTests(AIPagesTestCase):
    """ADM-017: "Entwurf vorschlagen" in "Mail schreiben"."""

    def setUp(self) -> None:
        super().setUp()
        configure_mailbox()

    def test_off_by_default(self) -> None:
        """ADM-017: without a provider for drafts there is no button."""
        text = self.assert_ok(self.client.get(reverse("mail:compose", args=[self.project.pk])))
        self.assertNotIn("Entwurf vorschlagen", text)

    def test_a_draft_for_the_answer(self) -> None:
        """ADM-017: the draft from the thread, to take over into the text; only its starter sees it."""
        self.install_local()
        self.use("draft", Source.LOCAL)
        answered = self.project.mails.filter(direction="in").order_by("-date").first()
        page = self.client.get(reverse("mail:compose", args=[self.project.pk]) + f"?answer={answered.pk}")
        text = self.assert_ok(page)
        self.assertIn("Entwurf vorschlagen", text)
        self.assertIn(f'name="answer" value="{answered.pk}"', text)
        text = self.assert_ok(self.htmx("post", reverse("ai:draft", args=[self.project.pk]), {"answer": answered.pk}))
        self.assertIn("Der Aufbau am Freitag passt.", text)
        self.assertIn("In den Text übernehmen", text)
        self.assertIn('aria-controls="id_body"', text)
        job = BackgroundJob.objects.get(kind="ai_draft")
        self.assertEqual(job.params["mail"], answered.pk)
        other = self.browser_for("paula", "Projektleitung")
        self.assertEqual(other.get(reverse("ai:draft_job", args=[self.project.pk, job.pk])).status_code, 404)
        own = self.htmx("get", reverse("ai:draft_job", args=[self.project.pk, job.pk]))
        self.assertIn("Der Aufbau am Freitag passt.", self.assert_ok(own))

    def test_without_javascript_on_a_page_of_its_own(self) -> None:
        """ADM-017: without htmx the draft comes on a page with the way back to the mail."""
        self.install_local()
        self.use("draft", Source.LOCAL)
        text = self.assert_ok(self.client.post(reverse("ai:draft", args=[self.project.pk])))
        self.assertIn("Der Aufbau am Freitag passt.", text)
        self.assertIn("Zurück zur Mail", text)

    def test_who_may_not_write_mails_gets_no_draft(self) -> None:
        """ADM-017: the right to write correspondence."""
        self.install_local()
        self.use("draft", Source.LOCAL)
        reader = self.browser_for("nora", "Nur-Lesen")
        self.assertEqual(reader.post(reverse("ai:draft", args=[self.project.pk])).status_code, 403)
        self.assertFalse(BackgroundJob.objects.filter(kind="ai_draft").exists())


class LanguageTests(AIPagesTestCase):
    """UIX-029, EML-040: the pages in English for a user who chose English."""

    def test_the_settings_page_in_english(self) -> None:
        """UIX-029: the msgids are the English interface; the summary block in English too."""
        user = make_user("emma", superuser=True)
        if not hasattr(user, "language"):
            self.skipTest("no interface language per user in this build")
        user.language = "en"
        user.save()
        browser = self.browser_of(user)
        text = self.assert_ok(browser.get(reverse("ai:settings")))
        self.assertIn("Local AI", text)
        self.assertIn("Switch summaries with local AI on", text)
        self.assertNotIn("Lokale KI", text)
        text = self.assert_ok(self.htmx("get", reverse("ai:summary", args=[self.project.pk]), client=browser))
        self.assertIn("Short overview without AI", text)
        self.assertIn("2 received, 1 sent", text)
        self.assertIn("12/06/2027", text)
