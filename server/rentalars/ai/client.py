# SPDX-License-Identifier: GPL-3.0-or-later
"""Talking to language models through the OpenAI-compatible interface (EML-040, ADM-017).

Every server Rentalars uses speaks the same small part of that interface:
``POST {base}/chat/completions`` with a list of messages, and
``GET {base}/models`` to see that it answers. llama.cpp's ``llama-server``,
Ollama, LM Studio, vLLM and the cloud services do.

Where a call may go:

* **The local AI** (:mod:`rentalars.ai.local`): the address the operator's
  command wrote, which must be on this machine (loopback). The connection
  goes there directly, without a proxy and without ``allow_internal`` – the
  operator installed the server (NFA-071).
* **A provider** (:class:`~rentalars.ai.models.AIProvider`): an address an
  administrator typed in. It goes through the network guard like webhooks
  and calendars (:func:`rentalars.core.network.open_url`): an internal
  address needs ``[network] allow_internal``.

Each use names its provider in the settings (:class:`~rentalars.ai.models.AISettings`);
:func:`endpoint_for` never falls back to another one, so mail content goes
nowhere but where the administrator said for that use.

Every call is logged in :class:`~rentalars.ai.models.AICall` – use, provider,
model, duration, sizes – never what was sent or received.
"""

from __future__ import annotations

import contextlib
import datetime
import ipaddress
import json
import re
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.ai.local import LocalConfigError, LocalServer, is_loopback_url, local_server
from rentalars.ai.models import AICall, AIProvider, AISettings, Source, Use

#: How long the call log is kept (ADM-017).
CALL_LOG_DAYS = 365
#: How long the local AI may take for one answer without streaming (the speed test): a small computer is slow.
LOCAL_TIMEOUT_SECONDS = 600
#: How long the local AI may stay silent while it writes (EML-040). Before the first word the time it
#: needs to read the prompt counts as well – see ``first_token_seconds`` of :func:`chat`.
LOCAL_SILENCE_SECONDS = 180
#: Before the first word, when nobody knows yet how fast the server reads.
FIRST_WORD_UNKNOWN_SECONDS = 1800
#: Qwen3's own switch for "answer without thinking first", for servers that ignore ``enable_thinking`` (Ollama).
NO_THINK = "/no_think"
#: How long "is it reachable" waits.
PROBE_TIMEOUT_SECONDS = 5
#: Answers larger than this are refused (a broken or hostile server).
MAX_ANSWER_BYTES = 2 * 1024 * 1024

_THINKING = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class AIError(Exception):
    """A call failed or cannot be made; ``str(error)`` is a text for the user, without mail content."""


@dataclass(frozen=True)
class Endpoint:
    """Where the calls of one use go."""

    base_url: str
    model: str
    label: str
    #: The operator's local AI (:mod:`rentalars.ai.local`) – not a provider typed in, even one on this machine.
    is_local: bool
    timeout: float
    context_tokens: int
    #: Never part of the text form of the object – a log line, a traceback or a debug page must not show it.
    api_key: str = field(default="", repr=False)
    leaves_company: bool = False
    #: The local AI: "llama.cpp" (installed by the command) or "other" (registered: Ollama, LM Studio).
    server_kind: str = ""


@dataclass(frozen=True)
class Answer:
    """What came back from one call."""

    text: str
    seconds: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    #: Writing: tokens of the answer per second.
    tokens_per_second: float | None = None
    #: Reading: tokens of the prompt per second, as the server reports it (llama.cpp ``timings``).
    prompt_per_second: float | None = None


@dataclass(frozen=True)
class Progress:
    """How far an answer got while it streams in (EML-040)."""

    #: "reading" the prompt, "thinking" (a model that thinks despite being told not to), or "writing".
    phase: str
    #: Of the prompt read so far, 0 to 1 – only servers that report it (llama.cpp ``return_progress``).
    read: float | None = None
    words: int = 0


# --- Where calls go ---------------------------------------------------------------------------------


def address_leaves_company(url: str) -> bool:
    """Whether an address lies outside the company's network – a cloud service (ADM-017).

    On this machine, an internal IP address, a name the operator allowed
    (``allow_internal``) or a name of the local network (``.local``,
    ``.lan``, ``.internal``, ``.home.arpa``): inside. Everything else is on
    the internet – the guard refuses internal addresses that are not allowed.
    """
    from rentalars.core.network import allowance, kind_of

    if is_loopback_url(url):
        return False
    try:
        host = (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return True
    if not host:
        return True
    rules = allowance()
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if rules.allows_name(host) or host.endswith((".local", ".lan", ".internal", ".home.arpa", ".intranet")):
            return False
        return "." in host
    return not (kind_of(address) or rules.allows_address(address))


def local_endpoint(server: LocalServer) -> Endpoint:
    """The local AI as an endpoint."""
    return Endpoint(
        base_url=server.url,
        model=server.model,
        label=_("Local AI"),
        is_local=True,
        timeout=LOCAL_SILENCE_SECONDS,
        context_tokens=server.context,
        server_kind=server.kind,
    )


def provider_endpoint(provider: AIProvider) -> Endpoint:
    """A provider of the list as an endpoint.

    Raises:
        AIError: Its API key cannot be decrypted any more.
    """
    from rentalars.core.crypto import SecretUnreadableError

    # The mails and the API key must not cross the internet unencrypted – also for an address stored earlier.
    if urlsplit(provider.base_url).scheme.lower() == "http" and provider.leaves_company:
        raise AIError(
            _("“%(name)s” is reached over the internet without encryption (http://). Use an address with https://.")
            % {"name": provider.name}
        )
    try:
        key = provider.api_key
    except SecretUnreadableError as error:
        raise AIError(
            _("The API key of “%(name)s” cannot be read any more (the secret key changed). Enter it again.")
            % {"name": provider.name}
        ) from error
    return Endpoint(
        base_url=provider.base_url.rstrip("/"),
        model=provider.model,
        label=provider.name,
        # Even on this machine a provider is an address typed in: it goes through the guard (NFA-071).
        is_local=False,
        timeout=provider.timeout_seconds,
        context_tokens=provider.context_tokens,
        api_key=key,
        leaves_company=provider.leaves_company,
    )


def is_switched_on(use: str) -> bool:
    """Whether an administrator chose a provider for this use (it may still be unreachable)."""
    source, _provider = AISettings.load().source_of(use)
    return source != Source.OFF


def endpoint_for(use: str) -> Endpoint:
    """Where the calls of a use go – exactly the one chosen for it, never another (EML-040, ADM-017).

    Raises:
        AIError: The use is switched off, or its local AI is not installed.
    """
    source, provider = AISettings.load().source_of(use)
    if source == Source.LOCAL:
        try:
            server = local_server()
        except LocalConfigError as error:
            raise AIError(str(error)) from error
        if server is None:
            raise AIError(_("The local AI is not installed. The operator installs it on the server."))
        return local_endpoint(server)
    if source == Source.PROVIDER and provider is not None:
        return provider_endpoint(provider)
    raise AIError(_("This use of AI is switched off in the settings."))


# --- Calls --------------------------------------------------------------------------------------------


def _request(endpoint: Endpoint, path: str, body: dict[str, Any] | None = None) -> urllib.request.Request:
    headers = {"Accept": "application/json", "User-Agent": "Rentalars"}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if endpoint.api_key:
        headers["Authorization"] = f"Bearer {endpoint.api_key}"
    return urllib.request.Request(  # noqa: S310 - http(s) only, checked by the form and the local file
        endpoint.base_url.rstrip("/") + path, data=data, headers=headers, method="POST" if body is not None else "GET"
    )


def _open(endpoint: Endpoint, prepared: urllib.request.Request, timeout: float) -> Any:
    """Send a request: to the local AI directly, to a provider through the network guard (NFA-071)."""
    if endpoint.is_local and is_loopback_url(endpoint.base_url):
        # The operator's server on this machine: no proxy, no guard – loopback was checked above.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
        return opener.open(prepared, timeout=timeout)
    from rentalars.core.network import open_url

    return open_url(prepared, timeout=timeout, handlers=[_NoRedirect])


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow a redirection: the text would go to an address nobody checked."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        """Refuse every redirection."""
        return None


def _error_text(error: BaseException, endpoint: Endpoint) -> str:
    """A text for the user about a failed call – never the content."""
    from rentalars.core.network import BlockedAddressError

    if isinstance(error, urllib.error.HTTPError):
        if error.code in {401, 403}:
            return _("%(provider)s refused the API key (HTTP %(code)s).") % {
                "provider": endpoint.label,
                "code": error.code,
            }
        if error.code == 404:
            return _("%(provider)s does not know this address or model (HTTP 404).") % {"provider": endpoint.label}
        if error.code == 429:
            return _("%(provider)s is busy or the limit of the account is reached (HTTP 429).") % {
                "provider": endpoint.label
            }
        return _("%(provider)s answered with an error (HTTP %(code)s).") % {
            "provider": endpoint.label,
            "code": error.code,
        }
    reason = getattr(error, "reason", error)
    if isinstance(reason, BlockedAddressError):
        return str(reason)
    if isinstance(reason, TimeoutError | socket.timeout) or isinstance(error, TimeoutError | socket.timeout):
        return _("%(provider)s did not answer in time.") % {"provider": endpoint.label}
    if isinstance(reason, ConnectionRefusedError):
        if endpoint.is_local:
            return _("The local AI does not answer. Is the service rentalars-ai running?")
        return _("%(provider)s cannot be reached.") % {"provider": endpoint.label}
    return _("%(provider)s cannot be reached.") % {"provider": endpoint.label}


def _read_json(response: Any) -> Any:
    raw = response.read(MAX_ANSWER_BYTES + 1)
    if len(raw) > MAX_ANSWER_BYTES:
        raise ValueError("answer too large")
    return json.loads(raw.decode("utf-8"))


def _log(
    endpoint: Endpoint,
    *,
    use: str,
    started: float,
    request_chars: int,
    answer: Answer | None,
    error: str,
    user: Any,
    project: Any,
    automatic: bool = False,
) -> None:
    """Note the call in the log, and forget entries past :data:`CALL_LOG_DAYS` (ADM-017)."""
    AICall.objects.create(
        use=use,
        provider_label=endpoint.label[:120],
        is_local=endpoint.is_local,
        model=endpoint.model[:200],
        duration_ms=int((time.monotonic() - started) * 1000),
        request_chars=request_chars,
        response_chars=len(answer.text) if answer else 0,
        prompt_tokens=answer.prompt_tokens if answer else None,
        completion_tokens=answer.completion_tokens if answer else None,
        prompt_per_second=answer.prompt_per_second if answer else None,
        generation_per_second=answer.tokens_per_second if answer else None,
        ok=answer is not None,
        error=error[:300],
        automatic=automatic,
        user=user if getattr(user, "pk", None) else None,
        project=project if getattr(project, "pk", None) else None,
    )
    AICall.objects.filter(timestamp__lt=timezone.now() - datetime.timedelta(days=CALL_LOG_DAYS)).delete()


def clean_answer(text: str) -> str:
    """The answer without the "thinking" some models write first (Qwen3: ``<think>…</think>``)."""
    text = _THINKING.sub("", text or "")
    if "<think>" in text.lower():
        # Cut off in the middle of thinking: nothing usable.
        text = text[: text.lower().index("<think>")]
    return text.strip()


def _thinking_off(endpoint: Endpoint, messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Messages with Qwen3's "/no_think" in the system message – for the local AI and Qwen models (EML-040).

    The hard switch is ``enable_thinking: false`` (llama.cpp) and ``--reasoning off`` on the server
    (``deploy/ai.sh``); "/no_think" is the soft one that Ollama's Qwen3 obeys as well.
    """
    if not (endpoint.is_local or "qwen" in endpoint.model.lower()):
        return messages
    result = [dict(message) for message in messages]
    for message in result:
        if message.get("role") == "system":
            if NO_THINK not in message.get("content", ""):
                message["content"] = f"{message.get('content', '').rstrip()} {NO_THINK}"
            return result
    return [{"role": "system", "content": NO_THINK}, *result]


def _extras(endpoint: Endpoint, *, stream: bool) -> dict[str, Any]:
    """Fields beyond the OpenAI interface; dropped once if a server refuses them (HTTP 400)."""
    extras: dict[str, Any] = {}
    if stream:
        extras["stream_options"] = {"include_usage": True}
    if endpoint.is_local:
        # llama.cpp: the hard switch against thinking; while it reads a long prompt, it says how far it got.
        extras["chat_template_kwargs"] = {"enable_thinking": False}
        if stream:
            extras["return_progress"] = True
        if endpoint.server_kind == "other":
            # Ollama: "none" switches thinking off (its OpenAI interface, reasoning_effort).
            extras["reasoning_effort"] = "none"
    return extras


def _set_read_timeout(response: Any, seconds: float) -> None:
    """Change how long reading from the open answer may wait – the silence allowed from now on."""
    sock = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
    if sock is not None:
        with contextlib.suppress(OSError):
            sock.settimeout(max(1.0, seconds))


def _events(response: Any) -> Any:
    """The events of a streamed answer (server-sent events); a whole JSON answer is one event."""
    content_type = str(response.headers.get("Content-Type", ""))
    if "text/event-stream" not in content_type:
        yield _read_json(response)
        return
    received = 0
    for raw in response:
        received += len(raw)
        if received > MAX_ANSWER_BYTES * 4:
            raise ValueError("answer too large")
        line = raw.decode("utf-8", "replace").strip()
        if not line or line.startswith(":") or not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            return
        yield json.loads(payload)


def _speeds(data: dict[str, Any], seconds: float, completion: Any) -> tuple[float | None, float | None]:
    """Reading and writing speed from llama.cpp's ``timings``; writing estimated from the usage otherwise."""
    timings = data.get("timings") or {}
    reading = timings.get("prompt_per_second")
    writing = timings.get("predicted_per_second")
    if writing is None and isinstance(completion, int) and seconds > 0:
        writing = completion / seconds
    as_float = lambda value: float(value) if isinstance(value, int | float) and value > 0 else None  # noqa: E731
    return as_float(reading), as_float(writing)


def _send(
    endpoint: Endpoint,
    body: dict[str, Any],
    extras: dict[str, Any],
    *,
    timeout: float,
) -> Any:
    """Open the request; a server that refuses the extra fields (HTTP 400) is asked once more without them."""
    try:
        return _open(endpoint, _request(endpoint, "/chat/completions", {**body, **extras}), timeout)
    except urllib.error.HTTPError as error:
        if error.code != 400 or not extras:
            raise
    return _open(endpoint, _request(endpoint, "/chat/completions", body), timeout)


def chat(
    endpoint: Endpoint,
    messages: list[dict[str, str]],
    *,
    use: str,
    max_tokens: int = 800,
    temperature: float = 0.2,
    user: Any = None,
    project: Any = None,
    stream: bool = False,
    progress: Any = None,
    first_token_seconds: float | None = None,
    deadline: float | None = None,
    extra_body: dict[str, Any] | None = None,
    automatic: bool = False,
) -> Answer:
    """One answer of the model to a list of messages; the call is logged without content (ADM-017).

    With ``stream`` (EML-040) the answer arrives word by word: the
    limit is then a silence of ``endpoint.timeout`` seconds – before the
    first word ``first_token_seconds``, the time the server needs to read
    the prompt – not the whole answer; ``progress`` is called with a
    :class:`Progress` as it goes; ``deadline`` (``time.monotonic()``) ends
    it for good. Thinking is switched off for the local AI and Qwen models,
    and whatever thinking still comes is left out of the answer.

    Raises:
        AIError: The server cannot be reached, refused, stayed silent too
            long, ran past the deadline or answered nonsense.
    """
    messages = _thinking_off(endpoint, messages)
    body: dict[str, Any] = {
        "model": endpoint.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
        **(extra_body or {}),
    }
    extras = _extras(endpoint, stream=stream)
    request_chars = sum(len(message.get("content", "")) for message in messages)
    started = time.monotonic()
    answer: Answer | None = None
    error_text = ""
    silence = float(endpoint.timeout)
    first = float(first_token_seconds or (FIRST_WORD_UNKNOWN_SECONDS if endpoint.is_local else silence))
    try:
        open_timeout = max(first, silence) if stream else (LOCAL_TIMEOUT_SECONDS if endpoint.is_local else silence)
        if deadline is not None:
            open_timeout = min(open_timeout, max(1.0, deadline - started))
        with _send(endpoint, body, extras, timeout=open_timeout) as response:
            answer = _receive(
                endpoint,
                response,
                started=started,
                silence=silence,
                first_word_by=started + max(first, silence),
                progress=progress,
                deadline=deadline,
            )
    except _DeadlineError:
        error_text = _("%(provider)s took longer than expected; the task was stopped.") % {"provider": endpoint.label}
    except (urllib.error.URLError, OSError) as error:
        error_text = _error_text(error, endpoint)
    except (ValueError, AttributeError, TypeError, IndexError, KeyError):
        error_text = _("%(provider)s gave an answer Rentalars cannot use.") % {"provider": endpoint.label}
    _log(
        endpoint,
        use=use,
        started=started,
        request_chars=request_chars,
        answer=answer,
        error=error_text,
        user=user,
        project=project,
        automatic=automatic,
    )
    if answer is None:
        raise AIError(error_text)
    if endpoint.is_local:
        remember_speed(endpoint, answer)
    return answer


class _DeadlineError(Exception):
    """The answer ran past the deadline of the task."""


def _receive(
    endpoint: Endpoint,
    response: Any,
    *,
    started: float,
    silence: float,
    first_word_by: float,
    progress: Any,
    deadline: float | None,
) -> Answer:
    """Read a whole or streamed answer; see :func:`chat`.

    Until the first word (or thought) arrives, the server is still reading
    the prompt: its progress events (llama.cpp ``prompt_progress``) do not
    use up the time allowed for that – the limit stays ``first_word_by``.
    From the first word on, it is the silence between two pieces.
    """
    text = ""
    thinking = 0
    usage: dict[str, Any] = {}
    final: dict[str, Any] = {}
    writing = False
    for event in _events(response):
        if not isinstance(event, dict):
            raise ValueError("not an object")
        if event.get("error"):
            raise ValueError("error event")
        now = time.monotonic()
        if deadline is not None and now > deadline:
            raise _DeadlineError
        if event.get("usage"):
            usage = event["usage"]
        if event.get("timings"):
            final = event
        choice = (event.get("choices") or [{}])[0] or {}
        if "message" in choice:  # a whole answer
            text = str((choice.get("message") or {}).get("content") or "")
            continue
        delta = choice.get("delta") or {}
        piece = delta.get("content") or ""
        reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
        reading = event.get("prompt_progress")
        if piece or reasoning:
            writing = True
        # Reading: what is left of the time for the first word; writing: the silence between two pieces.
        limit = silence if writing else max(silence, first_word_by - now)
        _set_read_timeout(response, limit if deadline is None else min(limit, deadline - now))
        if piece:
            text += str(piece)
        if reasoning:
            thinking += 1
        if progress is not None:
            lowered = text.lower()
            in_think = "<think>" in lowered and "</think>" not in lowered
            if isinstance(reading, dict) and reading.get("total"):
                done = (reading.get("processed") or 0) / max(1, reading["total"])
                progress(Progress("reading", read=min(1.0, float(done))))
            elif reasoning or (piece and in_think):
                progress(Progress("thinking", read=1.0))
            elif piece:
                progress(Progress("writing", read=1.0, words=len(clean_answer(text).split())))
    seconds = time.monotonic() - started
    cleaned = clean_answer(text)
    if not cleaned:
        raise ValueError("empty answer")
    completion = usage.get("completion_tokens")
    reading_speed, writing_speed = _speeds(final or {"timings": {}}, seconds, completion)
    prompt_tokens = usage.get("prompt_tokens")
    return Answer(
        text=cleaned,
        seconds=seconds,
        prompt_tokens=prompt_tokens if isinstance(prompt_tokens, int) else None,
        completion_tokens=completion if isinstance(completion, int) else None,
        tokens_per_second=writing_speed,
        prompt_per_second=reading_speed,
    )


def remember_speed(endpoint: Endpoint, answer: Answer) -> None:
    """Keep the speed of the local AI up to date from what its calls report (EML-040).

    Only the speed fields are written (no load and save of the whole
    settings: an administrator may change them at the same moment).
    Reading is measured only on a prompt of some length.
    """
    if answer.tokens_per_second is None and answer.prompt_per_second is None:
        return
    current = (
        AISettings.objects.filter(pk=1)
        .values("local_test_tokens_per_second", "local_test_prompt_per_second", "local_test_model")
        .first()
        or {}
    )
    same_model = current.get("local_test_model") in {"", None, endpoint.model}

    def blend(old: float | None, new: float | None) -> float | None:
        if new is None:
            return old if same_model else None
        return round((old + new) / 2, 2) if old and same_model else round(new, 2)

    reading = answer.prompt_per_second if (answer.prompt_tokens or 0) >= 64 else None
    AISettings.load()  # the row exists
    AISettings.objects.filter(pk=1).update(
        local_test_tokens_per_second=blend(current.get("local_test_tokens_per_second"), answer.tokens_per_second),
        local_test_prompt_per_second=blend(current.get("local_test_prompt_per_second"), reading),
        local_test_model=endpoint.model[:200],
        local_test_at=timezone.now(),
    )


def available_models(endpoint: Endpoint, *, timeout: float = PROBE_TIMEOUT_SECONDS) -> list[str]:
    """The models the server offers (``GET /models``) – the check "does it answer".

    Raises:
        AIError: It does not answer, or not as expected.
    """
    try:
        with _open(endpoint, _request(endpoint, "/models"), timeout) as response:
            data = _read_json(response)
        return [str(item.get("id", "")) for item in data.get("data", []) if isinstance(item, dict)]
    except (urllib.error.URLError, OSError) as error:
        raise AIError(_error_text(error, endpoint)) from error
    except (ValueError, AttributeError, TypeError) as error:
        raise AIError(_("%(provider)s gave an answer Rentalars cannot use.") % {"provider": endpoint.label}) from error


#: The text of the speed test – long enough (about 400 tokens) for the reading speed to mean something.
SPEED_TEST_TEXT = (
    "Hallo Frau Berg, vielen Dank für Ihre Anfrage zum Stadtfest am 12. Juni. Für die Hauptbühne planen wir "
    "zwei Line-Arrays mit je acht Elementen, vier Subwoofer, ein digitales Mischpult mit 48 Kanälen und sechs "
    "Monitorwege. Das Licht besteht aus zwölf Moving Heads, acht LED-Flutern und einer Nebelmaschine. Der "
    "Aufbau beginnt am Donnerstag um 8 Uhr, der Abbau am Sonntag nach Veranstaltungsende. Wir brauchen vor Ort "
    "einen Stromanschluss mit 63 Ampere und eine Zufahrt für einen 7,5-Tonner. Das Angebot über 4.850 Euro netto "
    "liegt bei. Bitte bestätigen Sie bis Freitag, ob die Bühne überdacht ist und wer vor Ort Ansprechpartner "
    "ist. Ihre Fragen zur Absicherung der Kabelwege beantworten wir gern telefonisch. Viele Grüße, Paula "
    "Schneider, Projektleitung. Hallo Frau Schneider, danke für das Angebot. Die Bühne ist überdacht, "
    "Ansprechpartner ist Herr Kaya vom Ordnungsamt. Können Sie auch zwei Funkmikrofone für die Begrüßung "
    "mitbringen? Und passt es, wenn der Aufbau erst um 10 Uhr beginnt? Viele Grüße, Jana Berg."
)


def speed_test(endpoint: Endpoint, *, user: Any = None) -> Answer:
    """A test prompt: how fast the model reads and writes (EML-040). Logged as use "test".

    The prompt is not taken from the server's cache (``cache_prompt``), so
    that a second test measures the reading again.

    Raises:
        AIError: As :func:`chat`.
    """
    answer = chat(
        endpoint,
        [
            {"role": "system", "content": "You answer briefly."},
            {
                "role": "user",
                "content": "Name the open questions of this mail exchange in one German sentence.\n\n"
                + SPEED_TEST_TEXT,
            },
        ],
        use=Use.TEST,
        max_tokens=48,
        temperature=0,
        user=user,
        extra_body={"cache_prompt": False} if endpoint.is_local and endpoint.server_kind != "other" else None,
    )
    return answer


# --- Checking an address that is typed in -------------------------------------------------------------


def validate_base_url(value: str) -> None:
    """Accept ``http(s)://host[:port]/path`` without credentials; internal hosts only if allowed (NFA-071).

    An IP address or ``localhost`` is checked here; a name when it is used.
    """
    from rentalars.core.network import BlockedAddressError, check_entered_host

    text = (value or "").strip()
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError as error:
        raise ValidationError(_("This is not a valid address."), code="invalid") from error
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValidationError(_("Only addresses beginning with https:// or http:// can be used."), code="invalid")
    if any(character.isspace() for character in text) or port == 0:
        raise ValidationError(_("This is not a valid address."), code="invalid")
    if parts.username is not None or parts.password is not None:
        raise ValidationError(
            _("Leave user name and password out of the address; enter the key in the field “API key”."),
            code="invalid",
        )
    if parts.query or parts.fragment:
        raise ValidationError(_("The address ends before “?” and “#”."), code="invalid")
    try:
        check_entered_host(parts.hostname)
    except BlockedAddressError as error:
        raise ValidationError(str(error), code="internal") from error
    # Texts and key to a server on the internet only encrypted.
    if parts.scheme.lower() == "http" and address_leaves_company(text):
        raise ValidationError(
            _("An address on the internet must begin with https:// – mails and the key would go unencrypted."),
            code="insecure",
        )
