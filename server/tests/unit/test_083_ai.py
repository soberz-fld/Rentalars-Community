# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests, area "ai": the local AI and the summary of the correspondence (EML-040, EML-044), the
interface for further uses (ADM-017), and the operator's command ``rentalars ai`` (dry run, shellcheck)."""

from __future__ import annotations

import datetime
import hashlib
import itertools
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest import SkipTest

from django.conf import settings
from django.test import override_settings
from django.utils import timezone, translation

from rentalars.ai import client, correspondence, drafts, summary
from rentalars.ai.client import AIError
from rentalars.ai.local import LocalConfigError, local_server
from rentalars.ai.models import AICall, AIProvider, AISettings, AISummary, Source, Use
from rentalars.ai.overview import amounts_in, dates_in, overview_of, questions_in
from rentalars.chat.models import ChatMessage
from rentalars.mail.models import Direction, MailAttachment, ProjectMail
from tests.ai_fake import FakeModelServer, write_local_file
from tests.helpers import RentalarsTestCase, make_customer, make_project, make_user

ROOT = Path(settings.BASE_DIR)
_KEYS = itertools.count(1)


def add_mail(
    project: object,
    subject: str,
    text: str,
    *,
    incoming: bool = True,
    days: int = 0,
    sender: tuple[str, str] = ("Jana Berg", "jana@kulturamt.example"),
) -> ProjectMail:
    """A mail of a project, received (from Jana Berg) or sent, ``days`` after 1 March 2027."""
    number = next(_KEYS)
    return ProjectMail.objects.create(
        project=project,
        direction=Direction.INCOMING if incoming else Direction.OUTGOING,
        subject=subject,
        text_body=text,
        message_id=f"<m{number}@test>",
        message_key=hashlib.sha256(f"m{number}".encode()).hexdigest(),
        sender_name=sender[0] if incoming else "Verleih",
        sender_address=sender[1] if incoming else "projekte@verleih.example",
        to_addresses="projekte@verleih.example" if incoming else f"{sender[0]} <{sender[1]}>",
        date=timezone.now() + datetime.timedelta(days=days),
    )


class AITestCase(RentalarsTestCase):
    """A project with three mails, a file for the local AI, and the fake model server."""

    def setUp(self) -> None:
        super().setUp()
        self.user = make_user("paula", roles=("Projektleitung",))
        self.project = make_project("Stadtfest", customer=make_customer("Kulturamt"))
        add_mail(self.project, "Angebot", "Hallo,\nkönnen Sie uns ein Angebot für den 12.06.2027 schicken?\nJana")
        add_mail(
            self.project,
            "Re: Angebot",
            "Anbei das Angebot über 2.380,00 €.\n\n> Hallo,\n> können Sie",
            incoming=False,
            days=1,
        )
        add_mail(self.project, "Re: Angebot", "Danke! Passt der Aufbau am Donnerstag? Wer ist vor Ort?", days=2)
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        self.local_file = folder / "ai-local.conf"
        settings_override = override_settings(RENTALARS_AI_LOCAL_FILE=str(self.local_file))
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        self.fake = FakeModelServer().__enter__()
        self.addCleanup(self.fake.__exit__)

    def install_local(self, **options: object) -> None:
        write_local_file(self.local_file, self.fake.url, **options)  # type: ignore[arg-type]

    def use(self, use: str, source: str, provider: AIProvider | None = None) -> None:
        ai_settings = AISettings.load()
        setattr(ai_settings, f"{use}_source", source)
        setattr(ai_settings, f"{use}_provider", provider)
        ai_settings.save()


class LocalServerFileTests(AITestCase):
    """EML-040: the operator's file says where the local AI listens; only an address on this machine counts."""

    def test_without_the_file_the_local_ai_is_not_installed(self) -> None:
        """EML-040: no file, no local AI – and the use says so instead of failing."""
        self.assertIsNone(local_server())
        self.use("summary", Source.LOCAL)
        with self.assertRaisesMessage(AIError, "nicht installiert"):
            client.endpoint_for(Use.SUMMARY)

    def test_the_file_of_the_command_is_read(self) -> None:
        """EML-040: address, model, context and the server as ``rentalars ai install`` writes them."""
        self.install_local(context=4096)
        server = local_server()
        assert server is not None
        self.assertEqual(server.url, self.fake.url)
        self.assertEqual(server.model, "qwen2.5-1.5b-instruct")
        self.assertEqual(server.context, 4096)
        self.assertEqual(server.model_licence, "Apache-2.0")

    def test_an_address_elsewhere_is_refused(self) -> None:
        """EML-040, NFA-071: the "local" AI may not point to another machine – the guard is passed only for loopback."""
        write_local_file(self.local_file, "http://192.168.1.20:8080/v1")
        with self.assertRaisesMessage(LocalConfigError, "127.0.0.1"):
            local_server()
        self.local_file.write_text("[other]\nurl = x\n", encoding="utf-8")
        with self.assertRaisesMessage(LocalConfigError, "[local_ai]"):
            local_server()

    @override_settings(RENTALARS_NETWORK_ALLOW_INTERNAL=())
    def test_the_local_ai_needs_no_allow_internal(self) -> None:
        """EML-040, NFA-071: the operator installed it – reached on loopback without ``allow_internal``."""
        self.install_local()
        self.use("summary", Source.LOCAL)
        endpoint = client.endpoint_for(Use.SUMMARY)
        self.assertTrue(endpoint.is_local)
        self.assertEqual(client.available_models(endpoint), ["qwen2.5-1.5b-instruct"])


class ProviderTests(AITestCase):
    """ADM-017: OpenAI-compatible interfaces, off at first, through the network guard."""

    def provider(self, url: str | None = None, **fields: object) -> AIProvider:
        provider = AIProvider(name="Ollama", base_url=url or self.fake.url, model="qwen2.5-1.5b-instruct", **fields)
        provider.save()
        return provider

    def test_every_use_is_off_at_first(self) -> None:
        """ADM-017, EML-040: nothing is switched on in a new installation."""
        ai_settings = AISettings.load()
        self.assertEqual((ai_settings.summary_source, ai_settings.draft_source), (Source.OFF, Source.OFF))
        for use in (Use.SUMMARY, Use.DRAFT):
            self.assertFalse(client.is_switched_on(use))
            with self.assertRaises(AIError):
                client.endpoint_for(use)

    def test_the_api_key_is_stored_encrypted_and_sent_as_bearer(self) -> None:
        """ADM-017: the key is encrypted in the database and goes only into the Authorization header."""
        provider = self.provider()
        provider.api_key = "sk-geheim-123"
        provider.save()
        stored = AIProvider.objects.values_list("api_key_encrypted", flat=True).get(pk=provider.pk)
        self.assertNotIn("sk-geheim", stored)
        self.fake.api_key = "sk-geheim-123"
        self.use("draft", Source.PROVIDER, provider)
        endpoint = client.endpoint_for(Use.DRAFT)
        client.chat(endpoint, [{"role": "user", "content": "Hallo"}], use=Use.DRAFT)
        self.assertEqual(self.fake.requests[-1]["headers"]["Authorization"], "Bearer sk-geheim-123")

    def test_a_wrong_key_is_named_and_logged(self) -> None:
        """ADM-017: a refusal is a clear text, and the failed call is in the log."""
        self.fake.api_key = "richtig"
        provider = self.provider()
        provider.api_key = "falsch"
        provider.save()
        with self.assertRaisesMessage(AIError, "API-Schlüssel abgelehnt"):
            client.chat(client.provider_endpoint(provider), [{"role": "user", "content": "x"}], use=Use.DRAFT)
        call = AICall.objects.get()
        self.assertFalse(call.ok)
        self.assertIn("401", call.error)

    @override_settings(RENTALARS_NETWORK_ALLOW_INTERNAL=())
    def test_an_internal_provider_needs_allow_internal(self) -> None:
        """ADM-017, NFA-071: a provider on this machine or in the network is an address typed in – the guard applies."""
        provider = self.provider()
        endpoint = client.provider_endpoint(provider)
        self.assertFalse(endpoint.is_local)
        with self.assertRaisesMessage(AIError, "internes Netz"):
            client.chat(endpoint, [{"role": "user", "content": "x"}], use=Use.DRAFT)
        self.assertEqual(self.fake.requests, [])
        from django.core.exceptions import ValidationError

        with self.assertRaisesMessage(ValidationError, "internes Netz"):
            client.validate_base_url("http://192.168.1.30:11434/v1")
        with self.assertRaisesMessage(ValidationError, "Benutzername und Passwort"):
            client.validate_base_url("https://user:pw@api.example.com/v1")

    def test_a_cloud_service_is_recognised(self) -> None:
        """ADM-017: an address on the internet gets the warning; internal ones and allowed names do not."""
        self.assertTrue(client.address_leaves_company("https://api.openai.com/v1"))
        self.assertFalse(client.address_leaves_company("http://127.0.0.1:11434/v1"))
        self.assertFalse(client.address_leaves_company("http://192.168.1.30:11434/v1"))
        self.assertFalse(client.address_leaves_company("http://ki.firma.local/v1"))
        with override_settings(RENTALARS_NETWORK_ALLOW_INTERNAL=("ki.example.de",)):
            self.assertFalse(client.address_leaves_company("https://ki.example.de/v1"))

    def test_mail_content_goes_only_to_the_server_of_the_use(self) -> None:
        """EML-040: the summary goes to the local AI – never to a provider that also exists."""
        with FakeModelServer() as other:
            self.use("draft", Source.PROVIDER, self.provider(url=other.url))
            self.install_local()
            self.use("summary", Source.LOCAL)
            summary.start(self.project, user=self.user, rights=_rights(self.user))
            self.assertEqual(other.requests, [])
        self.assertTrue(self.fake.chats)


def _rights(user: object) -> object:
    from rentalars.accounts.rights import rights_of

    return rights_of(user)


class CallLogTests(AITestCase):
    """ADM-017: every call is logged – use, provider, model, duration, sizes – never the content."""

    def test_the_log_holds_no_content(self) -> None:
        """ADM-017: neither the question nor the answer is stored in the log."""
        self.install_local()
        self.use("summary", Source.LOCAL)
        answer = client.chat(
            client.endpoint_for(Use.SUMMARY),
            [{"role": "user", "content": "Geheimer Inhalt der Mail"}],
            use=Use.SUMMARY,
            user=self.user,
            project=self.project,
        )
        call = AICall.objects.get()
        self.assertEqual(
            (call.use, call.model, call.is_local, call.ok), ("summary", "qwen2.5-1.5b-instruct", True, True)
        )
        # The local AI gets Qwen3's "/no_think" as a system message as well (EML-040).
        self.assertEqual(call.request_chars, len("Geheimer Inhalt der Mail") + len("/no_think"))
        self.assertEqual(call.response_chars, len(answer.text))
        self.assertEqual(call.user, self.user)
        values = " ".join(str(value) for value in AICall.objects.values().get().values())
        self.assertNotIn("Geheimer", values)
        self.assertNotIn(answer.text[:20], values)

    def test_old_entries_are_removed(self) -> None:
        """ADM-017: the log keeps a year."""
        AICall.objects.create(use="test", provider_label="x", timestamp=timezone.now() - datetime.timedelta(days=400))
        self.install_local()
        client.speed_test(client.local_endpoint(local_server()))  # type: ignore[arg-type]
        self.assertEqual(AICall.objects.count(), 1)

    def test_thinking_is_cut_off(self) -> None:
        """EML-040: Qwen3 may "think" first; only the answer counts – and thinking is switched off for local AI."""
        self.fake.think = True
        self.install_local()
        answer = client.speed_test(client.local_endpoint(local_server()))  # type: ignore[arg-type]
        self.assertEqual(answer.text, "Frühling, Sommer, Herbst, Winter")
        self.assertEqual(self.fake.chats[-1]["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(answer.tokens_per_second, 12.5)


class SummaryTests(AITestCase):
    """EML-040: the summary in the background, stored with the newest mail it covers, written in the user's language."""

    def setUp(self) -> None:
        super().setUp()
        self.install_local()
        self.use("summary", Source.LOCAL)

    def test_a_summary_is_stored_with_model_and_newest_mail(self) -> None:
        """EML-040: the task stores the text, model, provider, date and the newest mail it covers."""
        job = summary.start(self.project, user=self.user, rights=_rights(self.user))
        job.refresh_from_db()
        self.assertEqual(job.status, "done", job.message)
        stored = AISummary.objects.get(project=self.project)
        self.assertIn("Überblick", stored.text)
        self.assertEqual((stored.model, stored.is_local, stored.mail_count), ("qwen2.5-1.5b-instruct", True, 3))
        self.assertEqual(stored.newest_mail_id, self.project.mails.order_by("-date").first().pk)
        self.assertEqual(stored.created_by, self.user)
        prompt = self.fake.chats[-1]["messages"][-1]["content"]
        self.assertIn("Passt der Aufbau am Donnerstag?", prompt)
        # Quoted earlier mails are left out (EML-036).
        self.assertNotIn("> können Sie", prompt)
        self.assertIn("German", self.fake.chats[-1]["messages"][0]["content"])

    def test_the_summary_is_written_in_the_users_language(self) -> None:
        """EML-040, UIX-029: started in English, the model is asked for English."""
        with translation.override("en"):
            summary.start(self.project, user=self.user, rights=_rights(self.user))
        self.assertIn("British English", self.fake.chats[-1]["messages"][0]["content"])
        self.assertEqual(AISummary.objects.get().language, "en")

    def test_a_new_mail_makes_it_out_of_date(self) -> None:
        """EML-040: "veraltet" once a newer mail arrived; how many are not in it."""
        summary.start(self.project, user=self.user, rights=_rights(self.user))
        shown = summary.shown_summary(self.project, rights=_rights(self.user), user=self.user)
        self.assertFalse(shown.stale)
        add_mail(self.project, "Noch was", "Können wir eine Stunde früher anfangen?", days=3)
        shown = summary.shown_summary(self.project, rights=_rights(self.user), user=self.user)
        self.assertTrue(shown.stale)
        self.assertEqual(shown.new_mails, 1)

    def test_deleting_a_covered_mail_deletes_the_summary(self) -> None:
        """EML-040, EML-031: the summary carries the mail's content – it goes with the mail."""
        summary.start(self.project, user=self.user, rights=_rights(self.user))
        self.project.mails.first().delete()
        self.assertFalse(AISummary.objects.exists())

    def test_long_correspondence_is_summarised_in_parts(self) -> None:
        """EML-040: more than the context holds – parts, then the summary of the parts; each call fits the model."""
        write_local_file(self.local_file, self.fake.url, context=2048)
        for day in range(4, 12):
            add_mail(self.project, f"Tag {day}", ("Bühne und Licht wie besprochen. " * 40).strip(), days=day)
        summary.start(self.project, user=self.user, rights=_rights(self.user))
        prompts = [chat["messages"][-1]["content"] for chat in self.fake.chats]
        parts = [prompt for prompt in prompts if prompt.startswith("This is part ")]
        self.assertGreater(len(parts), 1)
        self.assertIn("summaries of consecutive parts", prompts[-1])
        budget = summary.budget_chars(client.endpoint_for(Use.SUMMARY))
        for prompt in prompts:
            self.assertLess(len(prompt), budget + 1200)
        self.assertEqual(AISummary.objects.get().parts, len(prompts))

    def test_the_chat_is_included_on_request(self) -> None:
        """EML-040: "optional chat" – only when asked for."""
        ChatMessage.objects.create(project=self.project, author_name="Paula", text="Kran ist bestellt.")
        summary.start(self.project, user=self.user, rights=_rights(self.user))
        self.assertNotIn("Kran ist bestellt", self.fake.chats[-1]["messages"][-1]["content"])
        summary.start(self.project, user=self.user, rights=_rights(self.user), include_chat=True)
        self.assertIn("Kran ist bestellt", self.fake.chats[-1]["messages"][-1]["content"])
        self.assertTrue(AISummary.objects.get().include_chat)

    def test_a_failure_fails_the_task_and_keeps_the_old_summary(self) -> None:
        """EML-040: the local AI not answering – the task fails with the reason; nothing is overwritten."""
        summary.start(self.project, user=self.user, rights=_rights(self.user))
        before = AISummary.objects.get().text
        self.fake.status = 500
        job = summary.start(self.project, user=self.user, rights=_rights(self.user))
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertIn("mit einem Fehler geantwortet (HTTP 500)", job.message)
        self.assertEqual(AISummary.objects.get().text, before)

    def test_switched_off_or_without_mails_nothing_starts(self) -> None:
        """EML-040: off – a clear refusal; no mails – nothing to summarise."""
        empty = make_project("Leer", customer=make_customer("Niemand"))
        with self.assertRaisesMessage(AIError, "keine Mails"):
            summary.start(empty, user=self.user, rights=_rights(self.user))
        self.use("summary", Source.OFF)
        with self.assertRaisesMessage(AIError, "ausgeschaltet"):
            summary.start(self.project, user=self.user, rights=_rights(self.user))


class DraftTests(AITestCase):
    """ADM-017: a reply draft from the thread, for the starter only."""

    def test_the_draft_answers_the_newest_received_mail(self) -> None:
        """ADM-017: the thread up to the mail goes to the provider of drafts; the draft stays with the task."""
        self.install_local()
        self.use("draft", Source.LOCAL)
        job = drafts.start(self.project, user=self.user)
        job.refresh_from_db()
        self.assertEqual(job.status, "done", job.message)
        self.assertIn("Der Aufbau am Freitag passt", job.result["text"])
        self.assertEqual(job.result["mail"], self.project.mails.filter(direction="in").order_by("-date").first().pk)
        prompt = self.fake.chats[-1]["messages"][-1]["content"]
        self.assertIn("Wer ist vor Ort?", prompt)
        self.assertIn("Jana Berg", prompt)

    def test_off_by_default(self) -> None:
        """ADM-017: no provider for drafts at first."""
        with self.assertRaisesMessage(AIError, "ausgeschaltet"):
            drafts.start(self.project, user=self.user)


class OverviewTests(AITestCase):
    """EML-044: the short overview without AI – always available."""

    def test_the_overview_of_the_mails(self) -> None:
        """EML-044: participants, number, first and last, dates, amounts, open questions, attachments, last writer."""
        last = self.project.mails.order_by("-date").first()
        MailAttachment.objects.create(mail=last, file="mail/x.pdf", filename="Bühnenplan.pdf", size=10)
        overview = overview_of([self.project.pk])
        self.assertEqual((overview.mail_count, overview.received, overview.sent), (3, 2, 1))
        self.assertTrue(overview.last_is_incoming)
        self.assertIn("Jana Berg", overview.last_writer)
        self.assertEqual([item.date for item in overview.dates], [datetime.date(2027, 6, 12)])
        self.assertEqual([item.text for item in overview.amounts], ["2.380,00 €"])
        # The questions of the three newest mails, newest first.
        self.assertEqual(
            [item.text for item in overview.questions],
            [
                "Passt der Aufbau am Donnerstag?",
                "Wer ist vor Ort?",
                "können Sie uns ein Angebot für den 12.06.2027 schicken?",
            ],
        )
        self.assertEqual([item.filename for item in overview.attachments], ["Bühnenplan.pdf"])
        self.assertEqual(overview.writers[0].written, 2)

    def test_dates_amounts_and_questions_in_text(self) -> None:
        """EML-044: German, British and ISO dates; euro amounts; a date inside a question does not cut it."""
        sent = datetime.date(2027, 3, 1)
        found = [
            value
            for _text, value in dates_in("am 3.4., 12.03.27, 2027-05-01, 05/06/2027, 12. März, Version 1.2.3", sent)
        ]
        self.assertEqual(
            found,
            [
                datetime.date(2027, 4, 3),
                datetime.date(2027, 3, 12),
                datetime.date(2027, 6, 5),
                datetime.date(2027, 5, 1),
                datetime.date(2027, 3, 12),
            ],
        )
        self.assertEqual(
            amounts_in("1.234,56 € und EUR 500, 2.000,- Euro, € 12.50"),
            ["1.234,56 €", "EUR 500", "2.000,- Euro", "€ 12.50"],
        )
        self.assertEqual(
            questions_in("Hallo. Geht es am 12.06.2027 um 8 Uhr? Danke."), ["Geht es am 12.06.2027 um 8 Uhr?"]
        )

    def test_a_whole_project_takes_the_parts_its_reader_may_read(self) -> None:
        """EML-044, PRJ-044: the mails of the parts belong to the whole project's correspondence."""
        part = make_project("Stadtfest Bühne 2", customer=self.project.customer)
        part.parent = self.project
        part.save()
        self.project.refresh_from_db()
        add_mail(part, "Bühne 2", "Strom?", days=5)
        ids = correspondence.project_ids_for(_rights(self.user), self.user, self.project)
        self.assertEqual(ids, [self.project.pk, part.pk])
        self.assertEqual(overview_of(ids).mail_count, 4)


class ExportTests(RentalarsTestCase):
    """ADM-017: the full export leaves the API key of an interface out."""

    def test_the_key_is_not_exported(self) -> None:
        from rentalars.core.export import SECRET_FIELDS

        self.assertIn("api_key_encrypted", SECRET_FIELDS["ai.aiprovider"])


class OperatorCommandTests(RentalarsTestCase):
    """EML-040: ``sudo rentalars ai install`` – the plan of a dry run on made-up systems; shellcheck."""

    def run_command(self, *arguments: str, **environment: str) -> subprocess.CompletedProcess[str]:
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        (folder / "os-ubuntu").write_text('PRETTY_NAME="Ubuntu 24.04.3 LTS"\nID=ubuntu\nVERSION_ID="24.04"\n')
        (folder / "os-debian").write_text('PRETTY_NAME="Debian GNU/Linux 13 (trixie)"\nID=debian\nVERSION_ID="13"\n')
        (folder / "model-pi").write_bytes(b"Raspberry Pi 5 Model B Rev 1.0\x00")
        (folder / "mem4").write_text("MemTotal:        3884000 kB\n")
        (folder / "mem8").write_text("MemTotal:        8000000 kB\n")
        (folder / "mem1").write_text("MemTotal:        1000000 kB\n")
        # The processor is read as well – here 4 cores with AVX2 and FMA, not those of the test machine.
        (folder / "cpuinfo").write_text(
            "".join(
                f"processor\t: {n}\nphysical id\t: 0\ncore id\t\t: {n}\nflags\t\t: sse avx2 fma\n\n" for n in range(4)
            )
        )
        env = {
            **os.environ,
            "RENTALARS_LANG": "de",
            "RENTALARS_AI_OS_RELEASE": str(folder / "os-ubuntu"),
            "RENTALARS_AI_DEVICE_MODEL": str(folder / "none"),
            "RENTALARS_AI_MEMINFO": str(folder / "mem8"),
            "RENTALARS_AI_ARCH": "amd64",
            "RENTALARS_AI_CORES": "4",
            "RENTALARS_AI_PACKAGE": "no",
            "RENTALARS_AI_CPUINFO": str(folder / "cpuinfo"),
        }
        env.update({key: value.replace("{folder}", str(folder)) for key, value in environment.items()})
        return subprocess.run(
            ["bash", str(ROOT / "deploy" / "ai.sh"), *arguments],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
            check=False,
        )

    def test_a_raspberry_pi_with_4_gb_gets_the_small_model_built_from_source(self) -> None:
        """EML-040: ≤ 4 GB → Qwen2.5 1.5B; Raspberry Pi OS has no package → llama.cpp b8681 built, commit checked."""
        result = self.run_command(
            "install",
            "--dry-run",
            RENTALARS_AI_OS_RELEASE="{folder}/os-debian",
            RENTALARS_AI_DEVICE_MODEL="{folder}/model-pi",
            RENTALARS_AI_MEMINFO="{folder}/mem4",
            RENTALARS_AI_ARCH="arm64",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        # The small model is Qwen3 1.7B now (Qwen2.5 1.5B still on request); one thread per core.
        self.assertIn("Qwen3 1.7B (Q4_K_M) – Lizenz Apache-2.0", result.stdout)
        self.assertIn("d2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5", result.stdout)
        self.assertIn("aus dem Quelltext gebaut: llama.cpp b8681, Commit 506200cf8b5c", result.stdout)
        self.assertIn("127.0.0.1:8093, --threads 4, MemoryMax=3G, Nice=10", result.stdout)
        self.assertIn("Probelauf: nichts wurde verändert.", result.stdout)

    def test_8_gb_and_a_package_give_the_larger_model_from_the_distribution(self) -> None:
        """EML-040: 8 GB → Qwen3 4B; where the distribution has llama.cpp-tools (Ubuntu 26.04) it is used."""
        result = self.run_command("install", "--dry-run", "--port", "8099", RENTALARS_AI_PACKAGE="yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Qwen3 4B (Q4_K_M)", result.stdout)
        self.assertIn("7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5", result.stdout)
        self.assertIn("Paket llama.cpp-tools der Distribution", result.stdout)
        self.assertIn("127.0.0.1:8099", result.stdout)

    def test_too_little_memory_and_wrong_options_are_refused(self) -> None:
        """EML-040: below 1.5 GB no model; a register address elsewhere is refused."""
        result = self.run_command("install", "--dry-run", RENTALARS_AI_MEMINFO="{folder}/mem1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Arbeitsspeicher", result.stderr)
        result = self.run_command("register", "--dry-run", "--url", "http://192.168.1.5:11434/v1", "--model", "x")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("auf diesem Rechner laufen", result.stderr)
        # A line break in the model name would add lines of its own to ai-local.conf.
        result = self.run_command(
            "register", "--dry-run", "--url", "http://127.0.0.1:11434/v1", "--model", "x\nurl = http://evil"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--model: nur Buchstaben", result.stderr)
        result = self.run_command(
            "register", "--dry-run", "--url", "http://127.0.0.1:11434/v1", "--model", "qwen2.5:1.5b"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_command("remove", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("/opt/rentalars/ai", result.stdout)

    def test_the_scripts_pass_shellcheck(self) -> None:
        """EML-040: deploy/ai.sh and the command "rentalars" pass shellcheck."""
        if shutil.which("shellcheck") is None:
            raise SkipTest("shellcheck is not installed")
        result = subprocess.run(
            ["shellcheck", "-x", "deploy/ai.sh", "deploy/rentalars"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env={**os.environ, "LANG": "C.UTF-8"},
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_the_service_is_bound_to_this_machine_and_limited(self) -> None:
        """EML-040: 127.0.0.1, no network but this machine, own user without rights, Nice, MemoryMax; no start without install."""
        unit = (ROOT / "deploy" / "systemd" / "rentalars-ai.service").read_text(encoding="utf-8")
        for line in (
            "--host 127.0.0.1",
            "DynamicUser=yes",
            "IPAddressDeny=any",
            "IPAddressAllow=localhost",
            "Nice=10",
            "MemoryMax=",
            "ConditionPathExists=/etc/rentalars/ai-local.env",
        ):
            self.assertIn(line, unit)
        command = (ROOT / "deploy" / "rentalars").read_text(encoding="utf-8")
        self.assertIn('ai)            exec bash "${APP_DIR}/deploy/ai.sh" "$@"', command)
