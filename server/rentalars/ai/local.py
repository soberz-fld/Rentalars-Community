# SPDX-License-Identifier: GPL-3.0-or-later
"""The local AI: a language model server on this machine, installed by the operator (EML-040, EML-044).

``sudo rentalars ai install`` (``deploy/ai.sh``) installs llama.cpp's
``llama-server`` with a small model as the service ``rentalars-ai``, bound to
127.0.0.1, and writes where it listens into ``ai-local.conf`` next to the
configuration file (``/etc/rentalars/ai-local.conf``)::

    [local_ai]
    url = http://127.0.0.1:8093/v1
    model = qwen2.5-1.5b-instruct
    model_name = Qwen2.5 1.5B Instruct (Q4_K_M)
    model_licence = Apache-2.0
    context = 8192
    threads = 3
    server = llama.cpp b8681 (Ubuntu package)
    installed_at = 2026-10-16T10:00:00+02:00

``sudo rentalars ai register --url … --model …`` writes the same for a
server the operator runs himself on this machine (Ollama, LM Studio).

Only root can write the file. Rentalars reads it at every use – nothing has
to be restarted – and accepts only an address on this machine (loopback):
that is why the network guard (NFA-071) lets the connection through without
``allow_internal`` – the operator installed this server, nobody typed its
address into a form.
"""

from __future__ import annotations

import configparser
import ipaddress
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from django.utils.translation import gettext as _

#: The name of the file next to the configuration file.
FILE_NAME = "ai-local.conf"
SECTION = "local_ai"
DEFAULT_CONTEXT = 4096


@dataclass(frozen=True)
class LocalServer:
    """What the operator's command wrote about the local AI."""

    url: str
    model: str
    model_name: str = ""
    model_licence: str = ""
    context: int = DEFAULT_CONTEXT
    threads: int = 0
    server: str = ""
    installed_at: str = ""
    #: The file it was read from.
    source: str = ""
    #: "llama.cpp" – installed by "rentalars ai install" – or "other" – a server named by "register"
    #: (Ollama, LM Studio). An older file has no such line: its "server" says it.
    kind: str = "llama.cpp"
    #: The physical cores of the processor and what it lacks for speed (AVX2, FMA), as the command found.
    physical_cores: int = 0

    @property
    def label(self) -> str:
        """The model as people read it."""
        return self.model_name or self.model


class LocalConfigError(Exception):
    """The file exists but cannot be used; ``str(error)`` says why (for the settings page)."""


def config_file() -> Path | None:
    """Where the operator's command writes about the local AI; ``None`` without a configuration file."""
    explicit = getattr(settings, "RENTALARS_AI_LOCAL_FILE", None)
    if explicit:
        return Path(explicit)
    config = getattr(settings, "RENTALARS_CONFIG_PATH", None)
    if not config:
        return None
    return Path(config).parent / FILE_NAME


def is_loopback_url(url: str) -> bool:
    """Whether an address leads to this machine only: ``localhost``, 127.0.0.0/8 or ``::1``."""
    try:
        parts = urlsplit(url)
        parts.port  # noqa: B018 - raises on a bad port
    except ValueError:
        return False
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme not in {"http", "https"} or not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def local_server() -> LocalServer | None:
    """The local AI as the operator installed it; ``None`` if it is not installed.

    Raises:
        LocalConfigError: The file is there, but unreadable or names no
            address on this machine.
    """
    path = config_file()
    if path is None or not path.is_file():
        return None
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(path, encoding="utf-8")
    except (OSError, configparser.Error, UnicodeDecodeError) as error:
        raise LocalConfigError(_("%(file)s cannot be read: %(error)s") % {"file": path, "error": error}) from error
    if not parser.has_section(SECTION):
        raise LocalConfigError(_("%(file)s has no section [local_ai].") % {"file": path})
    section = parser[SECTION]
    url = section.get("url", "").strip().rstrip("/")
    model = section.get("model", "").strip()
    if not url or not model:
        raise LocalConfigError(_("%(file)s names no address or no model.") % {"file": path})
    if not is_loopback_url(url):
        raise LocalConfigError(
            _("%(file)s names an address that is not on this machine; the local AI must listen on 127.0.0.1.")
            % {"file": path}
        )

    def number(key: str, default: int) -> int:
        try:
            return max(0, int(section.get(key, str(default)).strip() or default))
        except ValueError:
            return default

    return LocalServer(
        url=url,
        model=model,
        model_name=section.get("model_name", "").strip(),
        model_licence=section.get("model_licence", "").strip(),
        context=number("context", DEFAULT_CONTEXT) or DEFAULT_CONTEXT,
        threads=number("threads", 0),
        server=section.get("server", "").strip(),
        installed_at=section.get("installed_at", "").strip(),
        source=str(path),
        kind=_kind(section.get("server_kind", ""), section.get("server", "")),
        physical_cores=number("physical_cores", 0),
    )


def _kind(written: str, server: str) -> str:
    """``llama.cpp`` or ``other``; an older file without ``server_kind`` is known by its ``server`` line."""
    written = written.strip().lower()
    if written in {"llama.cpp", "other"}:
        return written
    return "llama.cpp" if server.strip().lower().startswith("llama.cpp") else "other"


def local_server_or_none() -> LocalServer | None:
    """Like :func:`local_server`, but an unusable file counts as "not installed"."""
    try:
        return local_server()
    except LocalConfigError:
        return None
