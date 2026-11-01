# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests, area "ai" (EML-040, ADM-017): thinking off for certain, streaming with a limit on silence
instead of the whole answer, measured reading and writing speed, the estimate and limit of a summary, the processor
check (AVX2/FMA, physical cores) and the model choice of ``rentalars ai install``."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import override_settings

from rentalars.ai import client, speed, summary
from rentalars.ai.client import AIError, Endpoint, Progress
from rentalars.ai.cpu import parse_cpuinfo
from rentalars.ai.local import local_server
from rentalars.ai.models import AICall, AIProvider, AISettings, Source, Use
from tests.ai_fake import FakeModelServer, write_local_file
from tests.helpers import RentalarsTestCase, make_user
from tests.unit.test_083_ai import AITestCase, add_mail

ROOT = Path(settings.BASE_DIR)

#: A virtual machine: Proxmox with the default processor type – no AVX2, no FMA.
PROXMOX_CPUINFO = "\n\n".join(
    f"processor\t: {number}\nvendor_id\t: GenuineIntel\nmodel name\t: QEMU Virtual CPU version 2.5+\n"
    f"physical id\t: 0\nsiblings\t: 4\ncore id\t\t: {number}\ncpu cores\t: 4\n"
    "flags\t\t: fpu sse sse2 ssse3 sse4_1 sse4_2 popcnt aes hypervisor lahf_lm\n"
    for number in range(4)
)
#: A server with hyper-threading: 8 logical processors on 4 cores, AVX2 and FMA.
HOST_CPUINFO = "\n\n".join(
    f"processor\t: {number}\nmodel name\t: AMD Ryzen 5 PRO 4650G\nphysical id\t: 0\ncore id\t\t: {number % 4}\n"
    "flags\t\t: fpu sse sse2 avx avx2 fma bmi2\n"
    for number in range(8)
)
#: A Raspberry Pi 5: ARM, NEON always there, no core ids.
PI_CPUINFO = (
    "\n\n".join(
        f"processor\t: {number}\nBogoMIPS\t: 108.00\nFeatures\t: fp asimd evtstrm aes crc32\n" for number in range(4)
    )
    + "\n\nModel\t\t: Raspberry Pi 5 Model B Rev 1.0\n"
)


def local(url: str, *, timeout: float = 180, kind: str = "llama.cpp", model: str = "qwen3-1.7b") -> Endpoint:
    """The local AI at ``url`` with a silence limit of ``timeout`` seconds."""
    return Endpoint(
        base_url=url,
        model=model,
        label="Lokale KI",
        is_local=True,
        timeout=timeout,
        context_tokens=8192,
        server_kind=kind,
    )


class ProcessorTests(RentalarsTestCase):
    """EML-040: AVX2/FMA and physical cores from /proc/cpuinfo."""

    def test_the_proxmox_default_processor(self) -> None:
        """EML-040: a virtual machine without AVX2 and FMA – four cores, four threads."""
        report = parse_cpuinfo(PROXMOX_CPUINFO, machine="x86_64")
        self.assertEqual((report.logical, report.physical, report.threads), (4, 4, 4))
        self.assertEqual(report.missing, ["AVX2", "FMA"])
        self.assertTrue(report.in_vm)

    def test_hyper_threading_counts_physical_cores(self) -> None:
        """EML-040: one thread per physical core, not per logical processor."""
        report = parse_cpuinfo(HOST_CPUINFO, machine="x86_64")
        self.assertEqual((report.logical, report.physical, report.threads), (8, 4, 4))
        self.assertEqual(report.missing, [])
        self.assertFalse(report.in_vm)

    def test_a_raspberry_pi_lacks_nothing(self) -> None:
        """EML-040: on ARM the AVX2 check does not apply."""
        report = parse_cpuinfo(PI_CPUINFO, machine="aarch64")
        self.assertFalse(report.is_x86)
        self.assertEqual(report.missing, [])
        self.assertEqual(report.model, "Raspberry Pi 5 Model B Rev 1.0")
        self.assertEqual(report.physical, 4)


class StreamingTests(AITestCase):
    """EML-040: streamed answers, a limit on silence, thinking off."""

    def test_the_answer_streams_with_progress_and_speeds(self) -> None:
        """EML-040: reading progress, then words; reading and writing speed kept from the server's timings."""
        self.install_local()
        heard: list[Progress] = []
        answer = client.chat(
            local(self.fake.url, model="qwen2.5-1.5b-instruct"),
            [{"role": "system", "content": "Fasse zusammen."}, {"role": "user", "content": "x " * 300}],
            use=Use.SUMMARY,
            stream=True,
            progress=heard.append,
        )
        self.assertIn("Überblick", answer.text)
        self.assertEqual((answer.prompt_per_second, answer.tokens_per_second), (80.0, 12.5))
        self.assertEqual(heard[0].phase, "reading")
        self.assertEqual(heard[-1].phase, "writing")
        self.assertEqual(heard[-1].words, len(answer.text.split()))
        body = self.fake.chats[-1]
        self.assertTrue(body["stream"])
        self.assertTrue(body["return_progress"])
        call = AICall.objects.get()
        self.assertEqual((call.prompt_per_second, call.generation_per_second), (80.0, 12.5))
        ai_settings = AISettings.load()
        self.assertEqual(
            (ai_settings.local_test_prompt_per_second, ai_settings.local_test_tokens_per_second), (80.0, 12.5)
        )

    def test_thinking_is_switched_off_and_cut_off(self) -> None:
        """EML-040: enable_thinking false, "/no_think" in the system message; thoughts never reach the text."""
        self.fake.think = True
        self.fake.reasoning_field = True
        heard: list[Progress] = []
        answer = client.chat(
            local(self.fake.url),
            [{"role": "system", "content": "Fasse zusammen."}, {"role": "user", "content": "Mails"}],
            use=Use.SUMMARY,
            stream=True,
            progress=heard.append,
        )
        self.assertNotIn("think", answer.text.lower())
        self.assertNotIn("Hmm", answer.text)
        self.assertIn("thinking", [state.phase for state in heard])
        body = self.fake.chats[-1]
        self.assertEqual(body["chat_template_kwargs"], {"enable_thinking": False})
        self.assertTrue(body["messages"][0]["content"].endswith("/no_think"))
        self.assertNotIn("reasoning_effort", body)

    def test_ollama_gets_its_own_switch(self) -> None:
        """EML-040: a registered server (Ollama) gets reasoning_effort "none" as well."""
        client.chat(local(self.fake.url, kind="other"), [{"role": "user", "content": "x"}], use=Use.DRAFT, stream=True)
        body = self.fake.chats[-1]
        self.assertEqual(body["reasoning_effort"], "none")
        self.assertEqual(body["messages"][0], {"role": "system", "content": "/no_think"})

    def test_a_provider_gets_only_the_openai_interface(self) -> None:
        """ADM-017: no llama.cpp fields and no "/no_think" for a cloud model that is not Qwen."""
        provider = AIProvider.objects.create(name="Cloud", base_url=self.fake.url, model="gpt-x")
        client.chat(
            client.provider_endpoint(provider), [{"role": "system", "content": "S"}], use=Use.DRAFT, stream=True
        )
        body = self.fake.chats[-1]
        self.assertNotIn("chat_template_kwargs", body)
        self.assertNotIn("return_progress", body)
        self.assertEqual(body["messages"][0]["content"], "S")

    def test_a_server_that_refuses_the_extra_fields_is_asked_again_without(self) -> None:
        """EML-040: HTTP 400 for unknown fields – once more with the plain OpenAI interface."""
        self.fake.refuse_extras = True
        answer = client.chat(local(self.fake.url), [{"role": "user", "content": "x"}], use=Use.DRAFT, stream=True)
        self.assertIn("Überblick", answer.text)
        self.assertEqual(len(self.fake.chats), 2)
        self.assertNotIn("chat_template_kwargs", self.fake.chats[-1])

    def test_a_slow_answer_is_fine_while_words_keep_coming(self) -> None:
        """EML-040: the limit is silence, not the whole answer – 3 s of answer with a 1 s limit."""
        self.fake.answer = " ".join(["Wort"] * 10)
        self.fake.delay_between = 0.3
        started = time.monotonic()
        answer = client.chat(
            local(self.fake.url, timeout=1), [{"role": "user", "content": "x"}], use=Use.DRAFT, stream=True,
            first_token_seconds=2,
        )  # fmt: skip
        self.assertGreater(time.monotonic() - started, 2.5)
        self.assertEqual(answer.text.split(), ["Wort"] * 10)

    def test_silence_ends_it(self) -> None:
        """EML-040: no word for longer than the limit – stopped with a clear text, logged as failed."""
        self.fake.stall_after = 2
        with self.assertRaisesMessage(AIError, "nicht rechtzeitig geantwortet"):
            client.chat(
                local(self.fake.url, timeout=1), [{"role": "user", "content": "x"}], use=Use.DRAFT, stream=True,
                first_token_seconds=2,
            )  # fmt: skip
        self.assertFalse(AICall.objects.get().ok)

    def test_no_first_word_in_time(self) -> None:
        """EML-040: before the first word the reading time counts – here 1 s, the server needs 3."""
        self.fake.delay_first = 3
        with self.assertRaisesMessage(AIError, "nicht rechtzeitig geantwortet"):
            client.chat(
                local(self.fake.url, timeout=1), [{"role": "user", "content": "x"}], use=Use.DRAFT, stream=True,
                first_token_seconds=1,
            )  # fmt: skip

    def test_reading_progress_does_not_use_up_the_time_for_the_first_word(self) -> None:
        """EML-040: progress, then 3 s of reading with 1 s silence allowed – the 30 s for the first
        word count, not the silence."""
        self.fake.delay_first = 3
        answer = client.chat(
            local(self.fake.url, timeout=1), [{"role": "user", "content": "x"}], use=Use.DRAFT, stream=True,
            first_token_seconds=30,
        )  # fmt: skip
        self.assertIs(self.fake.chats[-1]["return_progress"], True)  # the progress events came before the pause
        self.assertIn("Überblick", answer.text)

    def test_progress_does_not_lengthen_the_time_for_the_first_word(self) -> None:
        """EML-040: progress, then no word within the 2 s for the first word – stopped after those
        2 s, not after the 1 s of silence."""
        self.fake.delay_first = 6
        started = time.monotonic()
        with self.assertRaisesMessage(AIError, "nicht rechtzeitig geantwortet"):
            client.chat(
                local(self.fake.url, timeout=1), [{"role": "user", "content": "x"}], use=Use.DRAFT, stream=True,
                first_token_seconds=2,
            )  # fmt: skip
        self.assertGreater(time.monotonic() - started, 1.8)
        self.assertIs(self.fake.chats[-1]["return_progress"], True)

    def test_the_deadline_ends_it(self) -> None:
        """EML-040: past the limit of the task it stops, even while words come."""
        self.fake.answer = " ".join(["Wort"] * 40)
        self.fake.delay_between = 0.1
        with self.assertRaisesMessage(AIError, "länger gebraucht als erwartet"):
            client.chat(
                local(self.fake.url, timeout=5), [{"role": "user", "content": "x"}], use=Use.DRAFT, stream=True,
                deadline=time.monotonic() + 1,
            )  # fmt: skip


class SpeedTestTests(AITestCase):
    """EML-040: the speed test measures reading and writing apart, not from the cache."""

    def test_reading_and_writing(self) -> None:
        self.install_local()
        answer = client.speed_test(client.local_endpoint(local_server()))  # type: ignore[arg-type]
        self.assertEqual((answer.prompt_per_second, answer.tokens_per_second), (80.0, 12.5))
        body = self.fake.chats[-1]
        self.assertIs(body["cache_prompt"], False)
        self.assertGreater(len(body["messages"][-1]["content"]), 1000)


class EstimateTests(AITestCase):
    """EML-040: the estimate before a summary, and the limit of the task that follows from it."""

    def setUp(self) -> None:
        super().setUp()
        self.install_local()
        self.use("summary", Source.LOCAL)
        self.endpoint = client.endpoint_for(Use.SUMMARY)

    def measured(self, reading: float, writing: float) -> None:
        AISettings.load()
        AISettings.objects.filter(pk=1).update(
            local_test_prompt_per_second=reading, local_test_tokens_per_second=writing, local_test_model=""
        )

    def test_no_estimate_without_a_measurement(self) -> None:
        """EML-040: unknown speed – no estimate, and the limit of the task is the generous default."""
        self.assertIsNone(summary.estimate_for([self.project.pk], self.endpoint))
        self.assertEqual(speed.limit_of(None), speed.UNKNOWN_LIMIT_SECONDS)

    def test_the_users_virtual_machine(self) -> None:
        """EML-040: reading 5 and writing 1.5 tokens per second – a long summary, a warning, a limit far above it."""
        self.measured(5, 1.5)
        for day in range(3, 13):
            add_mail(self.project, f"Tag {day}", "Bühne und Licht wie besprochen. " * 30, days=day)
        found = summary.estimate_for([self.project.pk], self.endpoint)
        assert found is not None
        self.assertTrue(found.is_long)
        self.assertGreater(found.seconds, 600)
        self.assertGreaterEqual(found.limit, 3 * found.upper)

    def test_a_fast_server(self) -> None:
        """EML-040: reading 300 and writing 25 tokens per second – a short summary, no warning."""
        self.measured(300, 25)
        found = summary.estimate_for([self.project.pk], self.endpoint)
        assert found is not None
        self.assertFalse(found.is_long)
        self.assertEqual(found.calls, 1)
        self.assertEqual(found.limit, speed.MIN_LIMIT_SECONDS)

    def test_long_correspondence_counts_every_call(self) -> None:
        """EML-040: parts and the final summary each cost time."""
        write_local_file(self.local_file, self.fake.url, context=2048)
        self.measured(50, 10)
        endpoint = client.endpoint_for(Use.SUMMARY)
        for day in range(4, 12):
            add_mail(self.project, f"Tag {day}", ("Bühne und Licht wie besprochen. " * 40).strip(), days=day)
        found = summary.estimate_for([self.project.pk], endpoint)
        assert found is not None
        self.assertGreater(found.calls, 2)

    def test_the_task_stops_at_its_limit(self) -> None:
        """EML-040: the job fails with a clear text when it runs past the limit derived from the estimate."""
        self.fake.answer = " ".join(["Wort"] * 60)
        self.fake.delay_between = 0.1
        user = make_user("lina", roles=("Projektleitung",))
        from rentalars.accounts.rights import rights_of

        with mock.patch("rentalars.ai.speed.limit_of", return_value=1):
            job = summary.start(self.project, user=user, rights=rights_of(user))
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertIn("länger gebraucht als erwartet", job.message)

    def test_progress_says_what_it_does(self) -> None:
        """EML-040: "liest die Mails … %" and "schreibt … N Wörter" while the summary is written."""
        heard: list[tuple[int, str]] = []
        result = summary.summarise(
            ["--- Mail\nPasst der Aufbau am Donnerstag?"],
            project_name="Stadtfest",
            endpoint=self.endpoint,
            language="de",
            progress=lambda percent, message: heard.append((percent, message)),
        )
        self.assertIn("Überblick", result.text)
        messages = [message for _percent, message in heard]
        self.assertTrue(any(message.startswith("liest die Mails") for message in messages))
        self.assertRegex(messages[-1], r"^schreibt … \d+ Wörter$")
        self.assertEqual(self.fake.chats[-1]["max_tokens"], summary.ANSWER_TOKENS)


class AdviceTests(RentalarsTestCase):
    """EML-040: what the settings page recommends."""

    def test_proxmox_without_avx2(self) -> None:
        """EML-040: the processor type "host", and the smaller model."""
        found = speed.advice(
            model="qwen3-4b", speed=speed.Speed(5, 1.5), cpu=parse_cpuinfo(PROXMOX_CPUINFO, machine="x86_64")
        )
        self.assertIn("„host“", found.texts[0])
        self.assertIn("Proxmox", found.texts[0])
        self.assertEqual(found.command, "sudo rentalars ai install --model qwen3-1.7b")

    def test_slow_below_the_threshold(self) -> None:
        """EML-040: below the measured speed the smaller model; already the smallest – a faster processor."""
        host = parse_cpuinfo(HOST_CPUINFO, machine="x86_64")
        self.assertEqual(
            speed.advice(model="qwen3-4b", speed=speed.Speed(40, 4), cpu=host).command.split()[-1], "qwen3-1.7b"
        )
        self.assertEqual(speed.advice(model="qwen3-4b", speed=speed.Speed(200, 15), cpu=host).texts, [])
        smallest = speed.advice(model="qwen3-1.7b", speed=speed.Speed(20, 3), cpu=host)
        self.assertEqual(smallest.command, "")
        self.assertIn("schnelleren Prozessor", smallest.texts[0])


class OperatorCommandTests(RentalarsTestCase):
    """EML-040: ``rentalars ai install`` chooses model and threads by memory, cores and processor."""

    def run_command(
        self, *arguments: str, cpuinfo: str, memory_kb: int, arch: str = "amd64", **environment: str
    ) -> subprocess.CompletedProcess[str]:
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        (folder / "cpuinfo").write_text(cpuinfo)
        (folder / "mem").write_text(f"MemTotal:       {memory_kb} kB\n")
        (folder / "os").write_text('PRETTY_NAME="Ubuntu 26.04 LTS"\nID=ubuntu\nVERSION_ID="26.04"\n')
        env = {
            **os.environ,
            "RENTALARS_LANG": "de",
            "RENTALARS_AI_OS_RELEASE": str(folder / "os"),
            "RENTALARS_AI_DEVICE_MODEL": str(folder / "none"),
            "RENTALARS_AI_MEMINFO": str(folder / "mem"),
            "RENTALARS_AI_CPUINFO": str(folder / "cpuinfo"),
            "RENTALARS_AI_ARCH": arch,
            "RENTALARS_AI_PACKAGE": "yes",
            **environment,
        }
        return subprocess.run(
            ["bash", str(ROOT / "deploy" / "ai.sh"), *arguments], capture_output=True, text=True, env=env, timeout=60,
            check=False,
        )  # fmt: skip

    def test_the_users_virtual_machine(self) -> None:
        """EML-040: 8 GB, 4 cores, no AVX2 – Qwen3 1.7B, 4 threads, and the Proxmox hint."""
        result = self.run_command("install", "--dry-run", cpuinfo=PROXMOX_CPUINFO, memory_kb=8_000_000)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Qwen3 1.7B (Q4_K_M) – Lizenz Apache-2.0", result.stdout)
        self.assertIn("d2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5", result.stdout)
        self.assertIn("4 physische Kerne, 4 logische, virtuelle Maschine", result.stdout)
        self.assertIn("FEHLT: AVX2 FMA", result.stdout)
        self.assertIn("--threads 4, MemoryMax=3G", result.stdout)
        self.assertIn("Prozessortyp auf „host“", result.stderr + result.stdout)

    def test_a_fast_server_gets_the_larger_model(self) -> None:
        """EML-040: 8 GB, 4 physical cores (8 logical), AVX2 and FMA – Qwen3 4B with 4 threads."""
        result = self.run_command("install", "--dry-run", cpuinfo=HOST_CPUINFO, memory_kb=16_000_000)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Qwen3 4B (Q4_K_M)", result.stdout)
        self.assertIn("4 physische Kerne, 8 logische", result.stdout)
        self.assertIn("--threads 4,", result.stdout)
        self.assertNotIn("FEHLT", result.stdout)

    def test_a_raspberry_pi_gets_the_compact_model(self) -> None:
        """EML-040: a Pi 5 with 8 GB – Qwen3 1.7B; and --model switches the model explicitly."""
        result = self.run_command(
            "install", "--dry-run", cpuinfo=PI_CPUINFO, memory_kb=8_000_000, arch="arm64",
            RENTALARS_AI_DEVICE_MODEL=str(self._pi_model()),
            RENTALARS_AI_OS_RELEASE=str(self._debian()),
        )  # fmt: skip
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Qwen3 1.7B", result.stdout)
        self.assertNotIn("AVX2", result.stdout)
        forced = self.run_command(
            "install", "--dry-run", "--model", "qwen3-4b", cpuinfo=PROXMOX_CPUINFO, memory_kb=8_000_000
        )
        self.assertIn("Qwen3 4B", forced.stdout)

    def test_status_names_the_processor(self) -> None:
        """EML-040: ``rentalars ai status`` – processor and the warning, also before anything is installed."""
        result = self.run_command("status", cpuinfo=PROXMOX_CPUINFO, memory_kb=8_000_000)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("FEHLT: AVX2 FMA", result.stdout)
        self.assertIn("Proxmox", result.stdout + result.stderr)

    def _pi_model(self) -> Path:
        path = Path(tempfile.mkdtemp()) / "model"
        self.addCleanup(shutil.rmtree, path.parent, True)
        path.write_bytes(b"Raspberry Pi 5 Model B Rev 1.0\x00")
        return path

    def _debian(self) -> Path:
        path = Path(tempfile.mkdtemp()) / "os"
        self.addCleanup(shutil.rmtree, path.parent, True)
        path.write_text('PRETTY_NAME="Debian GNU/Linux 13 (trixie)"\nID=debian\nVERSION_ID="13"\n')
        return path


@override_settings(RENTALARS_AI_CPUINFO="")
class LocalFileTests(RentalarsTestCase):
    """EML-040: the file of the local AI says which kind of server it is."""

    def test_kind_from_the_file_and_from_a_file_of_083(self) -> None:
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        path = folder / "ai-local.conf"
        with override_settings(RENTALARS_AI_LOCAL_FILE=str(path)):
            write_local_file(path, "http://127.0.0.1:8093/v1", kind="other")
            self.assertEqual(local_server().kind, "other")  # type: ignore[union-attr]
            write_local_file(path, "http://127.0.0.1:8093/v1")  # No server_kind, "llama.cpp b8681 (test)"
            self.assertEqual(local_server().kind, "llama.cpp")  # type: ignore[union-attr]


#: llama-server of the Ubuntu 26.04 package (8681), as far as "refresh" asks it.
FAKE_LLAMA_SERVER = """#!/bin/sh
case "$1" in
    --version) echo "version: 8681 (506200cf)" ;;
    --help) printf '%s\\n' "-rea,  --reasoning [on|off|auto]   Use reasoning/thinking in the chat" \\
        "--reasoning-budget N   token budget for thinking" "--jinja, --no-jinja" "--webui, --no-webui" ;;
esac
"""

#: What "rentalars ai install" wrote earlier: no server_kind, threads = cores – 1, thinking only by budget.
CONF_083 = """# Written by "rentalars ai install" on 2026-10-01T10:00:00+02:00.
[local_ai]
url = {url}
model = {alias}
model_name = Qwen3 4B (Q4_K_M)
model_licence = Apache-2.0
context = 8192
threads = 3
server = llama.cpp 8681+dfsg-1 (Paket)
installed_at = 2026-10-01T10:00:00+02:00
"""
ENV_083 = """# Written by "rentalars ai install" – read by rentalars-ai.service.
AI_MODEL=/opt/rentalars/ai/models/Qwen3-4B-Q4_K_M.gguf
AI_ALIAS={alias}
AI_PORT=8093
AI_THREADS=3
AI_CONTEXT=8192
AI_EXTRA=--jinja --no-webui --reasoning-budget 0
"""


class RefreshTests(RentalarsTestCase):
    """EML-040: ``rentalars ai refresh`` – after every update, without downloading or changing the model."""

    def setUp(self) -> None:
        super().setUp()
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        for folder in ("etc/rentalars", "opt/rentalars/ai/bin", "opt/rentalars/ai/models", "bin"):
            (self.root / folder).mkdir(parents=True)
        (self.root / "etc/rentalars/rentalars.conf").write_text("[rentalars]\n")
        server = self.root / "opt/rentalars/ai/bin/llama-server"
        server.write_text(FAKE_LLAMA_SERVER)
        server.chmod(0o755)
        systemctl = self.root / "bin/systemctl"
        systemctl.write_text(f'#!/bin/sh\necho "$*" >> {self.root}/systemctl.log\nexit 0\n')
        systemctl.chmod(0o755)
        (self.root / "opt/rentalars/ai/models/Qwen3-4B-Q4_K_M.gguf").write_text("the model")
        self.fake = FakeModelServer(models=("qwen3-4b",)).__enter__()
        self.addCleanup(self.fake.__exit__)

    def install_083(self, alias: str = "qwen3-4b", *, built_with: str | None = None) -> None:
        """A local AI as installed before (and, with ``built_with``, as a build is recorded)."""
        conf = CONF_083.format(url=self.fake.url, alias=alias)
        if built_with is not None:
            conf += f"server_kind = llama.cpp\nbuilt_with = {built_with}\n"
        self.conf.write_text(conf)
        self.env.write_text(ENV_083.format(alias=alias))
        limits = self.root / "etc/systemd/system/rentalars-ai.service.d/50-limits.conf"
        limits.parent.mkdir(parents=True, exist_ok=True)
        limits.write_text("[Service]\nMemoryMax=5G\nCPUQuota=300%\n")

    @property
    def conf(self) -> Path:
        return self.root / "etc/rentalars/ai-local.conf"

    @property
    def env(self) -> Path:
        return self.root / "etc/rentalars/ai-local.env"

    def calls(self) -> str:
        log = self.root / "systemctl.log"
        return log.read_text() if log.exists() else ""

    def refresh(self, *arguments: str, cpuinfo: str = HOST_CPUINFO) -> subprocess.CompletedProcess[str]:
        (self.root / "cpuinfo").write_text(cpuinfo)
        (self.root / "meminfo").write_text("MemTotal:        8000000 kB\n")
        env = {
            **os.environ,
            "RENTALARS_LANG": "de",
            "RENTALARS_AI_TEST_ROOT": str(self.root),
            "RENTALARS_CONFIG": str(self.root / "etc/rentalars/rentalars.conf"),
            "RENTALARS_AI_SYSTEMCTL": str(self.root / "bin/systemctl"),
            "RENTALARS_AI_CPUINFO": str(self.root / "cpuinfo"),
            "RENTALARS_AI_MEMINFO": str(self.root / "meminfo"),
            "RENTALARS_AI_DEVICE_MODEL": str(self.root / "no-device"),
            "RENTALARS_AI_ARCH": "amd64",
        }
        return subprocess.run(
            ["bash", str(ROOT / "deploy" / "ai.sh"), "refresh", *arguments],
            capture_output=True, text=True, env=env, timeout=120, check=False,
        )  # fmt: skip

    def test_nothing_installed_says_nothing(self) -> None:
        """EML-040: no local AI – exit 0, not a word."""
        result = self.refresh()
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_a_registered_server_is_left_alone(self) -> None:
        """EML-040: Ollama registered by the operator – not ours to change, not a word."""
        write_local_file(self.conf, self.fake.url, kind="other")
        result = self.refresh()
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
        self.assertEqual(self.calls(), "")

    def test_an_installation_of_083_takes_over_the_settings(self) -> None:
        """EML-040: threads per physical core, thinking off, the new lines – the model stays; one restart."""
        self.install_083()
        result = self.refresh()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Lokale KI: Einstellungen übernommen (Nachdenken aus, 4 Threads).", result.stdout)
        env = self.env.read_text()
        self.assertIn("AI_THREADS=4\n", env)
        self.assertIn("AI_EXTRA=--jinja --no-webui --reasoning off --reasoning-budget 0\n", env)
        self.assertIn("AI_MODEL=/opt/rentalars/ai/models/Qwen3-4B-Q4_K_M.gguf\n", env)
        conf = self.conf.read_text()
        for line in ("server_kind = llama.cpp", "physical_cores = 4", "threads = 4", "model = qwen3-4b"):
            self.assertIn(line + "\n", conf)
        limits = (self.root / "etc/systemd/system/rentalars-ai.service.d/50-limits.conf").read_text()
        self.assertIn("MemoryMax=5G", limits)
        self.assertIn("CPUQuota=400%", limits)
        self.assertEqual(
            self.calls().splitlines(),
            ["daemon-reload", "is-enabled --quiet rentalars-ai.service", "restart rentalars-ai.service"],
        )
        self.assertEqual((self.root / "opt/rentalars/ai/models/Qwen3-4B-Q4_K_M.gguf").read_text(), "the model")
        self.assertNotIn("install --model", result.stdout)  # 8 GB, 4 cores, AVX2: Qwen3 4B is right

    def test_unchanged_means_no_restart(self) -> None:
        """EML-040: a second refresh changes nothing and restarts nothing."""
        self.install_083()
        self.refresh()
        (self.root / "systemctl.log").unlink()
        result = self.refresh()
        self.assertIn("Lokale KI: unverändert.", result.stdout)
        self.assertEqual(self.calls(), "")

    def test_the_users_virtual_machine_gets_hints_not_changes(self) -> None:
        """EML-040: without AVX2 – the smaller model is recommended with its command, and the "host" hint."""
        self.install_083()
        result = self.refresh(cpuinfo=PROXMOX_CPUINFO)
        self.assertEqual(result.returncode, 0)
        self.assertIn("sudo rentalars ai install --model qwen3-1.7b", result.stdout)
        self.assertIn("Prozessortyp auf „host“", result.stdout + result.stderr)
        self.assertIn("AI_ALIAS=qwen3-4b", self.env.read_text())

    def test_a_build_without_avx2_on_a_processor_with_it(self) -> None:
        """EML-040: a build of 24.04 made before "host" – it says to build again; the package never needs it."""
        self.install_083(built_with="none")
        self.assertIn("sudo rentalars ai install --rebuild", self.refresh().stdout)
        self.install_083(built_with="package")
        self.assertNotIn("--rebuild", self.refresh().stdout)

    def test_a_broken_local_ai_never_fails_the_update(self) -> None:
        """EML-040: something missing – a warning, exit 0."""
        self.install_083()
        (self.root / "opt/rentalars/ai/bin/llama-server").unlink()
        result = self.refresh()
        self.assertEqual(result.returncode, 0)
        self.assertIn("Einstellungen nicht übernommen", result.stderr)
        self.assertEqual(self.calls(), "")

    def test_the_lock_is_where_only_root_may_write(self) -> None:
        """EML-040: the lock is in /run, not in /run/lock – a link planted there to a file of root's
        no longer empties that file."""
        self.install_083()
        victim = self.root / "etc/rentalars/precious"
        victim.write_text("keep me")
        planted = self.root / "run/lock/rentalars-ai-refresh.lock"
        planted.parent.mkdir(parents=True)
        planted.symlink_to(victim)
        result = self.refresh()
        self.assertIn("Einstellungen übernommen", result.stdout, result.stderr)
        self.assertEqual(victim.read_text(), "keep me")
        lock = self.root / "run/rentalars-ai-refresh.lock"
        self.assertTrue(lock.is_file() and not lock.is_symlink())

    def test_root_runs_no_llama_server_somebody_else_could_change(self) -> None:
        """EML-040: root asks llama-server "--help" only if it and every folder above it belong to
        root alone – otherwise it is not run, nothing changes, and the update goes on."""
        server = self.root / "opt/rentalars/ai/bin/llama-server"
        ran = self.root / "ran"
        server.write_text(FAKE_LLAMA_SERVER.replace("#!/bin/sh\n", f"#!/bin/sh\ntouch {ran}\n", 1))
        server.chmod(0o755)
        elsewhere = self.root / "tmp"
        elsewhere.mkdir()
        elsewhere.chmod(0o1777)
        (elsewhere / "llama-server").write_text(server.read_text())
        (elsewhere / "llama-server").chmod(0o755)

        def writable_by_all() -> None:
            server.chmod(0o777)

        def folder_writable_by_all() -> None:
            server.parent.chmod(0o777)

        def owned_by_somebody_else() -> None:
            os.chown(server, 65534, 65534)

        def link_into_a_folder_for_all() -> None:
            server.unlink()
            server.symlink_to(elsewhere / "llama-server")

        for name, spoil in (
            ("program writable by all", writable_by_all),
            ("folder writable by all", folder_writable_by_all),
            ("program of another user", owned_by_somebody_else),
            ("link into /tmp", link_into_a_folder_for_all),
        ):
            with self.subTest(name):
                self.install_083()
                spoil()
                result = self.refresh()
                self.assertEqual(result.returncode, 0)
                self.assertIn("wird nicht ausgeführt", result.stderr)
                self.assertIn("Einstellungen nicht übernommen", result.stderr)
                self.assertFalse(ran.exists(), "llama-server was run")
                self.assertIn("AI_THREADS=3\n", self.env.read_text())
                self.assertEqual(self.calls(), "")
                # As it was, for the next case: a program of root's, in folders of root's – run, taken over.
                if server.is_symlink():
                    server.unlink()
                    server.write_text((elsewhere / "llama-server").read_text())
                os.chown(server, 0, 0)
                server.chmod(0o755)
                server.parent.chmod(0o755)
        self.install_083()
        self.assertIn("Einstellungen übernommen", self.refresh().stdout)
        self.assertTrue(ran.exists())

    def test_root_writes_no_file_in_a_folder_somebody_else_could_change(self) -> None:
        """EML-040: the configuration folder writable by others – nothing written, nothing run."""
        self.install_083()
        (self.root / "etc/rentalars").chmod(0o777)
        result = self.refresh()
        self.assertEqual(result.returncode, 0)
        self.assertIn("gehört nicht allein root", result.stderr)
        self.assertIn("AI_THREADS=3\n", self.env.read_text())
        self.assertEqual(self.calls(), "")

    def test_dry_run(self) -> None:
        """EML-040: --dry-run shows the change and makes none."""
        self.install_083()
        result = self.refresh("--dry-run")
        self.assertIn("3 → 4", result.stdout)
        self.assertIn("AI_THREADS=3", self.env.read_text())

    def test_update_and_timer_run_it(self) -> None:
        """EML-040: "rentalars update" runs refresh after success (not on rollback); the timer at every start."""
        update = (ROOT / "deploy" / "update.sh").read_text(encoding="utf-8")
        call = 'bash "${APP_DIR}/deploy/ai.sh" refresh || true'
        self.assertIn(call, update)
        self.assertGreater(update.index(call), update.index("# --- Step 5: go back if anything failed"))
        self.assertLess(update.index(call), update.index("Done. Rentalars ${new_version} is running."))
        self.assertNotIn("ai.sh refresh", update[: update.index("# --- Step 1: prerequisites")])
        timer = (ROOT / "deploy" / "systemd" / "rentalars-ai-refresh.timer").read_text(encoding="utf-8")
        self.assertIn("OnActiveSec=1min", timer)
        service = (ROOT / "deploy" / "systemd" / "rentalars-ai-refresh.service").read_text(encoding="utf-8")
        self.assertIn("ExecStart=/bin/bash /opt/rentalars/app/deploy/ai.sh refresh", service)
        self.assertIn("ConditionPathExists=/etc/rentalars/ai-local.env", service)
