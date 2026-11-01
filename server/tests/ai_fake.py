# SPDX-License-Identifier: GPL-3.0-or-later
"""A stand-in for an OpenAI-compatible language model server in tests (EML-040, ADM-017).

:class:`FakeModelServer` is a small HTTP server on 127.0.0.1 with a free port.
It answers ``GET /v1/models`` and ``POST /v1/chat/completions`` like
llama.cpp's ``llama-server`` (with ``usage`` and ``timings``) and keeps every
request it got, so that a test can see what was sent – and what was not.
EML-040: it streams as well (``stream: true``, server-sent
events, ``prompt_progress`` when asked with ``return_progress``), can think
aloud (``think``: ``<think>`` in the text; ``reasoning_field``:
``reasoning_content`` deltas), wait before the first word (``delay_first``),
between words (``delay_between``) or stop talking (``stall_after`` words),
and refuse fields beyond the OpenAI interface (``refuse_extras``)::

    with FakeModelServer() as server:
        ...  # point the local AI or a provider at server.url
    self.assertEqual(len(server.chats), 2)

No test reaches a real model or a server on the internet.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

#: Fields beyond the OpenAI interface that Rentalars sends to the local AI.
EXTRA_FIELDS = ("chat_template_kwargs", "return_progress", "reasoning_effort", "stream_options", "cache_prompt")


class FakeModelServer:
    """An OpenAI-compatible server that answers from rules instead of a model."""

    def __init__(
        self,
        *,
        models: tuple[str, ...] = ("qwen2.5-1.5b-instruct",),
        answer: str | None = None,
        status: int = 200,
        api_key: str = "",
        think: bool = False,
        reasoning_field: bool = False,
        delay_first: float = 0.0,
        delay_between: float = 0.0,
        stall_after: int | None = None,
        refuse_extras: bool = False,
        prompt_speed: float = 80.0,
    ) -> None:
        self.models = models
        self.answer = answer
        self.status = status
        self.api_key = api_key
        self.think = think
        self.reasoning_field = reasoning_field
        self.delay_first = delay_first
        self.delay_between = delay_between
        self.stall_after = stall_after
        self.refuse_extras = refuse_extras
        self.prompt_speed = prompt_speed
        self._stop = threading.Event()
        #: Every request: ``{"method", "path", "headers", "body"}``.
        self.requests: list[dict[str, Any]] = []
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        """The base URL, as the local AI's file or a provider names it."""
        assert self._server is not None
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    @property
    def chats(self) -> list[dict[str, Any]]:
        """The bodies of the chat requests."""
        return [request["body"] for request in self.requests if request["path"].endswith("/chat/completions")]

    def reply_to(self, body: dict[str, Any]) -> str:
        """The answer to a chat request: a part summary, a final summary, a draft or the test answer."""
        if self.answer is not None:
            return self.answer
        prompt = body["messages"][-1]["content"]
        if prompt.startswith("This is part "):
            number = prompt.split()[3]
            return f"Teil {number}: Aufbau am Freitag, Angebot über 1.200 €."
        if "Draft the reply" in prompt:
            return "Hallo Frau Berg,\n\nvielen Dank für Ihre Nachricht. Der Aufbau am Freitag passt."
        if "four seasons" in prompt or "open questions of this mail exchange" in prompt:
            # The speed test.
            return "Frühling, Sommer, Herbst, Winter"
        return "Überblick: Die Kundin fragt nach dem Aufbau am Freitag.\n- Angebot über 1.200 € ist verschickt."

    def __enter__(self) -> FakeModelServer:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                return

            def _send(self, status: int, data: Any) -> None:
                raw = json.dumps(data).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _note(self, body: Any) -> None:
                fake.requests.append(
                    {"method": self.command, "path": self.path, "headers": dict(self.headers), "body": body}
                )

            def _refused(self) -> bool:
                if fake.status != 200:
                    self._send(fake.status, {"error": {"message": "refused"}})
                    return True
                if fake.api_key and self.headers.get("Authorization") != f"Bearer {fake.api_key}":
                    self._send(401, {"error": {"message": "invalid key"}})
                    return True
                return False

            def do_GET(self) -> None:
                self._note(None)
                if self._refused():
                    return
                if self.path.endswith("/models"):
                    self._send(
                        200, {"object": "list", "data": [{"id": name, "object": "model"} for name in fake.models]}
                    )
                else:
                    self._send(404, {"error": {"message": "not found"}})

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                self._note(body)
                if self._refused():
                    return
                if not self.path.endswith("/chat/completions"):
                    self._send(404, {"error": {"message": "not found"}})
                    return
                if fake.refuse_extras and any(key in body for key in EXTRA_FIELDS):
                    self._send(400, {"error": {"message": "unknown field"}})
                    return
                text = fake.reply_to(body)
                if fake.think:
                    text = "<think>Let me think about the mails.</think>\n" + text
                prompt_chars = sum(len(message.get("content", "")) for message in body.get("messages", []))
                usage = {"prompt_tokens": prompt_chars // 3, "completion_tokens": len(text) // 3}
                timings = {
                    "prompt_n": prompt_chars // 3,
                    "prompt_per_second": fake.prompt_speed,
                    "predicted_n": len(text) // 3,
                    "predicted_per_second": 12.5,
                }
                if body.get("stream"):
                    self._stream(body, text, usage, timings)
                    return
                self._send(
                    200,
                    {
                        "id": "chatcmpl-test",
                        "object": "chat.completion",
                        "model": body.get("model"),
                        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}}],
                        "usage": usage,
                        "timings": timings,
                    },
                )

            def _event(self, data: Any) -> None:
                self.wfile.write(b"data: " + json.dumps(data).encode("utf-8") + b"\n\n")
                self.wfile.flush()

            def _stream(self, body: Any, text: str, usage: Any, timings: Any) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                try:
                    if body.get("return_progress"):
                        total = usage["prompt_tokens"]
                        for processed in (total // 2, total):
                            self._event({"choices": [], "prompt_progress": {"total": total, "processed": processed}})
                    if fake._stop.wait(fake.delay_first):
                        return
                    if fake.reasoning_field:
                        self._event({"choices": [{"delta": {"reasoning_content": "Hmm, the mails …"}}]})
                    for index, word in enumerate(text.split(" ")):
                        if fake.stall_after is not None and index >= fake.stall_after:
                            fake._stop.wait(60)
                            return
                        piece = word if index == 0 else " " + word
                        self._event({"choices": [{"index": 0, "delta": {"content": piece}}]})
                        if fake.delay_between and fake._stop.wait(fake.delay_between):
                            return
                    self._event({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "timings": timings})
                    self._event({"choices": [], "usage": usage})
                    self.wfile.write(b"data: [DONE]\n\n")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        assert self._server is not None
        self._stop.set()
        self._server.shutdown()
        self._server.server_close()


def write_local_file(
    path: Any, url: str, *, model: str = "qwen2.5-1.5b-instruct", context: int = 8192, kind: str = ""
) -> None:
    """Write ``ai-local.conf`` as ``sudo rentalars ai install`` does."""
    from pathlib import Path

    Path(path).write_text(
        "[local_ai]\n"
        f"url = {url}\n"
        f"model = {model}\n"
        "model_name = Qwen2.5 1.5B Instruct (Q4_K_M)\n"
        "model_licence = Apache-2.0\n"
        f"context = {context}\n"
        "threads = 3\n"
        "server = llama.cpp b8681 (test)\n"
        "installed_at = 2027-03-01T08:00:00+01:00\n" + (f"server_kind = {kind}\n" if kind else ""),
        encoding="utf-8",
    )
