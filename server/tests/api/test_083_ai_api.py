# SPDX-License-Identifier: GPL-3.0-or-later
"""API tests, area "ai": the overview and the AI summary of the correspondence (EML-040, EML-044), the reply
draft and the settings, interfaces and call log of the AI (ADM-017). Every operation is called (API-014)."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.test import override_settings

from rentalars.ai.models import AICall, AIProvider, AISettings, AISummary, Source
from rentalars.core.models import BackgroundJob
from tests.ai_fake import FakeModelServer, write_local_file
from tests.api.base import API, ApiTestCase
from tests.helpers import make_customer, make_project
from tests.unit.test_083_ai import add_mail


class AIApiTestCase(ApiTestCase):
    """A project with mails, the file of the local AI and the fake model server."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project("Stadtfest", customer=make_customer("Kulturamt"))
        add_mail(self.project, "Angebot", "Können Sie uns ein Angebot für den 12.06.2027 schicken?")
        add_mail(self.project, "Re: Angebot", "Anbei das Angebot über 2.380,00 €.", incoming=False, days=1)
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        self.local_file = folder / "ai-local.conf"
        override = override_settings(RENTALARS_AI_LOCAL_FILE=str(self.local_file))
        override.enable()
        self.addCleanup(override.disable)
        self.fake = FakeModelServer().__enter__()
        self.addCleanup(self.fake.__exit__)
        write_local_file(self.local_file, self.fake.url)

    def switch(self, use: str, source: str) -> None:
        ai_settings = AISettings.load()
        setattr(ai_settings, f"{use}_source", source)
        ai_settings.save()


class CorrespondenceSummaryApiTests(AIApiTestCase):
    """EML-040, EML-044: ``/projects/{id}/correspondence-summary``."""

    def url(self) -> str:
        return f"{API}/projects/{self.project.pk}/correspondence-summary"

    def test_the_overview_without_ai(self) -> None:
        """EML-044: the overview is always there; no summary yet; summaries off."""
        data = self.admin.get(self.url()).json()
        self.assertEqual((data["overview"]["mail_count"], data["overview"]["received"]), (2, 1))
        self.assertEqual(data["overview"]["dates"][0]["date"], "2027-06-12")
        self.assertEqual(data["overview"]["amounts"][0]["text"], "2.380,00 €")
        self.assertEqual(
            data["overview"]["questions"][0]["text"], "Können Sie uns ein Angebot für den 12.06.2027 schicken?"
        )
        self.assertIsNone(data["summary"])
        self.assertFalse(data["switched_on"])

    def test_summarise_and_read_it(self) -> None:
        """EML-040: POST starts the task (202); GET then gives the text, marked as made by AI, with model and date."""
        self.switch("summary", Source.LOCAL)
        response = self.admin.post(self.url(), {"include_chat": True}, format="json")
        self.assertEqual(response.status_code, 202, response.content)
        job = BackgroundJob.objects.get(pk=response.json()["job"])
        self.assertEqual(job.status, "done")
        data = self.admin.get(self.url()).json()
        self.assertTrue(data["summary"]["made_by_ai"])
        self.assertEqual(data["summary"]["model"], "qwen2.5-1.5b-instruct")
        self.assertTrue(data["summary"]["include_chat"])
        self.assertFalse(data["summary"]["stale"])
        self.assertIn("Überblick", data["summary"]["text"])

    def test_off_or_without_right(self) -> None:
        """EML-040: switched off – 409 with the reason; without the correspondence right – 403."""
        self.assert_error(self.admin.post(self.url(), {}, format="json"), 409, "ai_unavailable")
        storage = self.client_for("luka", "Lager")
        self.assert_error(storage.get(self.url()), 403, "permission_denied")
        self.assertFalse(AISummary.objects.exists())


class ReplyDraftApiTests(AIApiTestCase):
    """ADM-017: ``POST /projects/{id}/mails/reply-draft``."""

    def test_a_draft_arrives_in_the_job(self) -> None:
        """ADM-017: 202 and the task; ``/jobs/{id}`` holds the draft in ``result.text``."""
        self.switch("draft", Source.LOCAL)
        mail = self.project.mails.filter(direction="in").first()
        response = self.admin.post(
            f"{API}/projects/{self.project.pk}/mails/reply-draft", {"answer_to": mail.pk}, format="json"
        )
        self.assertEqual(response.status_code, 202, response.content)
        job = self.admin.get(f"{API}/jobs/{response.json()['job']}").json()
        self.assertEqual(job["status"], "done")
        self.assertIn("Der Aufbau am Freitag passt.", job["result"]["text"])
        self.assertEqual(job["result"]["mail"], mail.pk)

    def test_off_at_first_and_only_for_writers(self) -> None:
        """ADM-017: off by default (409); read-only users may not (403)."""
        url = f"{API}/projects/{self.project.pk}/mails/reply-draft"
        self.assert_error(self.admin.post(url, {}, format="json"), 409, "ai_unavailable")
        self.switch("draft", Source.LOCAL)
        reader = self.client_for("nora", "Nur-Lesen")
        self.assert_error(reader.post(url, {}, format="json"), 403, "permission_denied")


class SettingsApiTests(AIApiTestCase):
    """ADM-017, EML-040: ``/ai/settings``, ``/ai/local/speed-test``, ``/ai/providers``, ``/ai/calls``."""

    def test_settings_read_and_changed(self) -> None:
        """ADM-017: per use off, local or a provider; the state of the local AI; later: template suggestions."""
        data = self.admin.get(f"{API}/ai/settings").json()
        self.assertEqual((data["summary"], data["draft"], data["template_suggestions"]), ("off", "off", "later"))
        self.assertTrue(data["local"]["installed"])
        self.assertTrue(data["local"]["reachable"])
        self.assertEqual(data["local"]["model_licence"], "Apache-2.0")
        provider = AIProvider.objects.create(name="Ollama", base_url=self.fake.url, model="qwen")
        data = self.admin.patch(f"{API}/ai/settings", {"summary": "local", "draft": f"p{provider.pk}"}, format="json")
        self.assertEqual(data.status_code, 200, data.content)
        ai_settings = AISettings.load()
        self.assertEqual((ai_settings.summary_source, ai_settings.draft_provider), (Source.LOCAL, provider))
        self.assert_error(
            self.admin.patch(f"{API}/ai/settings", {"summary": "p999"}, format="json"),
            400,
            "validation_error",
            "summary",
        )
        planner = self.client_for("paula", "Projektleitung")
        self.assert_error(planner.get(f"{API}/ai/settings"), 403, "permission_denied")

    def test_speed_test(self) -> None:
        """EML-040: a test prompt to the local AI; the speed is kept."""
        response = self.admin.post(f"{API}/ai/local/speed-test")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["tokens_per_second"], 12.5)
        self.assertIsNotNone(AISettings.load().local_test_at)
        self.local_file.unlink()
        self.assert_error(self.admin.post(f"{API}/ai/local/speed-test"), 409, "ai_unavailable")

    def test_providers(self) -> None:
        """ADM-017: create, list, read, change, delete; the key is never read back; internal needs the operator."""
        created = self.admin.post(
            f"{API}/ai/providers",
            {"name": "Cloud", "base_url": "https://api.example.com/v1/", "model": "gpt-x", "api_key": "sk-geheim"},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        body = created.json()
        self.assertNotIn("api_key", body)
        self.assertTrue(body["has_api_key"])
        self.assertTrue(body["leaves_company"])
        self.assertEqual(body["base_url"], "https://api.example.com/v1")
        pk = body["id"]
        self.assertEqual(AIProvider.objects.get(pk=pk).api_key, "sk-geheim")
        self.assertEqual([item["name"] for item in self.admin.get(f"{API}/ai/providers").json()["results"]], ["Cloud"])
        self.assertNotIn("sk-geheim", self.admin.get(f"{API}/ai/providers/{pk}").content.decode())
        changed = self.admin.patch(f"{API}/ai/providers/{pk}", {"model": "gpt-y"}, format="json")
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual(AIProvider.objects.get(pk=pk).api_key, "sk-geheim")
        replaced = self.admin.put(
            f"{API}/ai/providers/{pk}",
            {"name": "Cloud", "base_url": "https://api.example.com/v1", "model": "gpt-z", "api_key": ""},
            format="json",
        )
        self.assertEqual(replaced.status_code, 200, replaced.content)
        self.assertFalse(replaced.json()["has_api_key"])
        with override_settings(RENTALARS_NETWORK_ALLOW_INTERNAL=()):
            refused = self.admin.post(
                f"{API}/ai/providers", {"name": "Intern", "base_url": "http://10.0.0.5/v1", "model": "x"}, format="json"
            )
            self.assert_error(refused, 400, "validation_error", "base_url")
        ai_settings = AISettings.load()
        ai_settings.summary_source, ai_settings.summary_provider = Source.PROVIDER, AIProvider.objects.get(pk=pk)
        ai_settings.save()
        self.assertEqual(self.admin.delete(f"{API}/ai/providers/{pk}").status_code, 204)
        self.assertEqual(AISettings.load().summary_source, Source.OFF)

    def test_the_key_does_not_follow_a_changed_server(self) -> None:
        """ADM-017: PATCH of base_url alone removes the stored key and says so."""
        provider = AIProvider(name="Cloud", base_url="https://api.example.com/v1", model="gpt-x")
        provider.api_key = "sk-SECRET"
        provider.save()
        with FakeModelServer() as attacker:
            response = self.admin.patch(f"{API}/ai/providers/{provider.pk}", {"base_url": attacker.url}, format="json")
            self.assertEqual(response.status_code, 200, response.content)
            self.assertFalse(response.json()["has_api_key"])
            self.assertIn("API-Schlüssel entfernt", response.json()["api_key_removed"])
            provider.refresh_from_db()
            self.assertEqual(provider.api_key, "")
            ai_settings = AISettings.load()
            ai_settings.draft_source, ai_settings.draft_provider = Source.PROVIDER, provider
            ai_settings.save()
            self.admin.post(f"{API}/projects/{self.project.pk}/mails/reply-draft", {}, format="json")
            self.assertTrue(attacker.requests)
            self.assertNotIn("Authorization", attacker.requests[-1]["headers"])
        response = self.admin.patch(
            f"{API}/ai/providers/{provider.pk}",
            {"base_url": "https://other.example.com/v1", "api_key": "sk-NEW"},
            format="json",
        )
        self.assertEqual(response.json()["api_key_removed"], "")
        provider.refresh_from_db()
        self.assertEqual(provider.api_key, "sk-NEW")

    def test_the_call_log(self) -> None:
        """ADM-017: the calls without content."""
        AICall.objects.create(use="summary", provider_label="Lokale KI", model="qwen", request_chars=10)
        data = self.admin.get(f"{API}/ai/calls").json()
        self.assertEqual(data[0]["use"], "summary")
        self.assertEqual(data[0]["request_chars"], 10)
        self.assertNotIn("text", data[0])
