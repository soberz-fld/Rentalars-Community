# SPDX-License-Identifier: GPL-3.0-or-later
"""How fast the AI is, how long a summary will take, and what would make it faster (EML-040).

The local AI reports two speeds: how many tokens of the prompt it *reads*
per second and how many of the answer it *writes* per second (llama.cpp
``timings``). The speed test measures both; every later call updates them
(:func:`rentalars.ai.client.remember_speed`). For a provider the speeds of
its last calls in the log are taken.

From them follow:

* the estimate shown before "Zusammenfassen" – with a warning when it will
  take long – and the limit of the task, a multiple of the estimate;
* the recommendation on Einstellungen → KI: a smaller model below a
  measured speed, and the processor type "host" for a virtual machine that
  hides AVX2 and FMA. Changing the model is the operator's command.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any

from django.utils.translation import gettext as _

from rentalars.ai.client import Endpoint
from rentalars.ai.cpu import CpuReport
from rentalars.ai.models import AICall, AISettings

#: A conservative guess of characters per token for German and English mail text.
CHARS_PER_TOKEN = 3.0
#: Below these speeds (tokens per second) a smaller model is recommended.
SLOW_WRITING = 6.0
SLOW_READING = 30.0
#: An estimate above this many seconds is called long on the page.
LONG_SECONDS = 300
#: The task may take this many times the estimate (and at least :data:`MIN_LIMIT_SECONDS`) before it is stopped.
LIMIT_FACTOR = 3
MIN_LIMIT_SECONDS = 600
#: Without any measurement: the limit of a summary.
UNKNOWN_LIMIT_SECONDS = 3 * 3600
#: The models of "rentalars ai install", smallest first (deploy/ai.sh).
SMALLEST_MODELS = frozenset({"qwen3-1.7b", "qwen2.5-1.5b-instruct"})
SMALL_MODEL_KEY = "qwen3-1.7b"


@dataclass(frozen=True)
class Speed:
    """Reading and writing in tokens per second; either may be unknown."""

    reading: float | None
    writing: float | None
    measured_at: datetime.datetime | None = None

    @property
    def known(self) -> bool:
        """Whether an estimate can be made: the writing speed is the least that is needed."""
        return bool(self.writing)

    @property
    def is_slow(self) -> bool:
        """Slower than a summary should be on this server."""
        return bool((self.writing and self.writing < SLOW_WRITING) or (self.reading and self.reading < SLOW_READING))


def speed_of(endpoint: Endpoint) -> Speed | None:
    """The measured speed of where a use goes; ``None`` if nothing was measured yet."""
    if endpoint.is_local:
        ai_settings = AISettings.load()
        if not ai_settings.local_test_tokens_per_second:
            return None
        if ai_settings.local_test_model and ai_settings.local_test_model != endpoint.model:
            return None  # measured with another model
        return Speed(
            ai_settings.local_test_prompt_per_second,
            ai_settings.local_test_tokens_per_second,
            ai_settings.local_test_at,
        )
    call = (
        AICall.objects.filter(
            provider_label=endpoint.label[:120],
            model=endpoint.model[:200],
            ok=True,
            generation_per_second__isnull=False,
        )
        .order_by("-timestamp")
        .first()
    )
    if call is None:
        return None
    return Speed(call.prompt_per_second, call.generation_per_second, call.timestamp)


@dataclass(frozen=True)
class Estimate:
    """How long something will take, in seconds: expected and at most."""

    seconds: float
    upper: float
    calls: int

    @property
    def minutes(self) -> int:
        """The expected time in whole minutes, at least one."""
        return max(1, round(self.seconds / 60))

    @property
    def is_long(self) -> bool:
        """Long enough to warn before starting."""
        return self.seconds > LONG_SECONDS

    @property
    def limit(self) -> float:
        """When the task is stopped: a multiple of the longest estimate."""
        return max(MIN_LIMIT_SECONDS, LIMIT_FACTOR * self.upper)


def estimate(
    speed: Speed | None, *, prompt_tokens: int, answer_tokens: int, upper_answer_tokens: int, calls: int = 1
) -> Estimate | None:
    """The time of calls that read ``prompt_tokens`` and write ``answer_tokens`` (at most ``upper_answer_tokens``)."""
    if speed is None or not speed.known:
        return None
    writing = float(speed.writing or 1)
    # Without a measured reading speed: reading is usually about eight times faster than writing.
    reading = float(speed.reading or writing * 8)
    overhead = 2.0 * calls
    expected = prompt_tokens / reading + answer_tokens / writing + overhead
    upper = prompt_tokens / reading + upper_answer_tokens / writing + overhead
    return Estimate(seconds=expected, upper=upper, calls=calls)


def limit_of(found: Estimate | None) -> float:
    """The limit of a task: from its estimate, or :data:`UNKNOWN_LIMIT_SECONDS` without one."""
    return found.limit if found is not None else UNKNOWN_LIMIT_SECONDS


@dataclass
class Advice:
    """What the settings page recommends for the local AI."""

    texts: list[str] = field(default_factory=list)
    #: The operator's command that would help, if there is one.
    command: str = ""


def advice(*, model: str, speed: Speed | None, cpu: CpuReport) -> Advice:
    """Processor type "host" when AVX2/FMA are missing; a smaller model below the measured speed (EML-040)."""
    result = Advice()
    if cpu.missing:
        result.texts.append(
            _(
                "The processor does not report %(missing)s: the local AI runs several times slower without them. "
                "In a virtual machine, set the processor type to “host”, e.g. in Proxmox under Hardware → "
                "Processors → Type, then shut the machine down and start it again; the rest happens by itself."
            )
            % {"missing": " ".join(cpu.missing)}
        )
    slow = (speed is not None and speed.is_slow) or bool(cpu.missing)
    if slow and model not in SMALLEST_MODELS:
        result.texts.append(
            _("A smaller model writes about twice as fast, with somewhat simpler summaries: Qwen3 1.7B.")
        )
        result.command = f"sudo rentalars ai install --model {SMALL_MODEL_KEY}"
    elif speed is not None and speed.is_slow and model in SMALLEST_MODELS and not cpu.missing:
        result.texts.append(
            _("This is already the smallest model; only a faster processor makes the summaries quicker.")
        )
    return result


def typical_summary(speed: Speed | None) -> Estimate | None:
    """A typical summary – some 20 mails, about 12,000 characters – for the settings page."""
    return estimate(
        speed, prompt_tokens=int(12_000 / CHARS_PER_TOKEN) + 400, answer_tokens=450, upper_answer_tokens=700
    )


def as_json(found: Estimate | None) -> dict[str, Any] | None:
    """An estimate for the API."""
    if found is None:
        return None
    return {
        "seconds": round(found.seconds),
        "upper_seconds": round(found.upper),
        "limit_seconds": round(found.limit),
        "calls": found.calls,
        "long": found.is_long,
    }
