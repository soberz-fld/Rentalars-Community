# SPDX-License-Identifier: GPL-3.0-or-later
"""Which host names the application answers to when the address of the server changes (new IP address; ADM-016).

Django answers only to the host names in ``ALLOWED_HOSTS`` – the one of the configured address, ``localhost`` and
what ``allowed_hosts`` of the configuration adds. That is a protection, but it hit a common case: a server in a
closed network gets another IP address (a new DHCP lease, a moved virtual machine), and whoever opens
``http://192.168.1.50/`` gets an error page and an entry in the error log.

The address of the server itself is no risk: the *Host* header cannot be turned against the application with an
address that belongs to this very machine (an attacker's own domain name never is one). So a request whose host
is an IP address of this server is answered to, without an entry. :class:`OwnAddressHostMiddleware` checks that
only when the host is not allowed yet, so the normal request does not pay for it. The addresses are read from
the system (``/proc/net``, Linux) and kept for half a minute; where they cannot be read, nothing is added.
``allow_own_addresses = no`` switches it off.
"""

from __future__ import annotations

import contextlib
import ipaddress
import logging
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.http.request import split_domain_port

logger = logging.getLogger(__name__)

IPV4_TABLE = Path("/proc/net/fib_trie")
IPV6_TABLE = Path("/proc/net/if_inet6")
#: How long the addresses read from the system are kept, in seconds.
KEEP_SECONDS = 30

_cache: tuple[float, frozenset[str]] | None = None
#: The own addresses already mentioned in the log (at most 64: a client cannot make this grow).
_said: set[str] = set()
_lock = threading.Lock()


def read_addresses(ipv4: Path = IPV4_TABLE, ipv6: Path = IPV6_TABLE) -> frozenset[str]:
    """The IP addresses assigned to this machine, as text, from the tables of the kernel; empty if unreadable."""
    found: set[str] = set()
    with contextlib.suppress(OSError):
        last = ""
        for line in ipv4.read_text(encoding="ascii", errors="replace").splitlines():
            stripped = line.strip()
            if stripped.startswith("|-- "):
                last = stripped[4:].strip()
            elif "/32 host LOCAL" in stripped and last:
                found.add(last)
    with contextlib.suppress(OSError):
        for line in ipv6.read_text(encoding="ascii", errors="replace").splitlines():
            digits = line.split(" ", 1)[0]
            if len(digits) == 32:
                with contextlib.suppress(ValueError):
                    found.add(str(ipaddress.IPv6Address(bytes.fromhex(digits))))
    clean: set[str] = set()
    for text in found:
        with contextlib.suppress(ValueError):
            clean.add(str(ipaddress.ip_address(text)))
    return frozenset(clean)


def own_addresses() -> frozenset[str]:
    """:func:`read_addresses`, kept for :data:`KEEP_SECONDS`."""
    global _cache
    with _lock:
        now = time.monotonic()
        if _cache is None or now - _cache[0] > KEEP_SECONDS:
            _cache = (now, read_addresses())
        return _cache[1]


def forget_addresses() -> None:
    """Throw away the remembered addresses (for tests)."""
    global _cache
    with _lock:
        _cache = None
        _said.clear()


def own_hosts() -> frozenset[str]:
    """The addresses of this server as they appear in a Host header: ``192.168.1.50``, ``[fe80::1]``."""
    return frozenset(f"[{text}]" if ":" in text else text for text in own_addresses())


def is_own_address(host: str) -> bool:
    """Whether a host of a request (``192.168.1.50``, ``192.168.1.50:8000``, ``[fe80::1]``) is an address of this server.

    Only the canonical spelling counts: ``[0::1]`` is not ``[::1]`` for Django's check, and a client must not be
    able to make up spellings.
    """
    name, _port = split_domain_port(host)
    return name in own_hosts()


class AllowedHosts(list):  # type: ignore[type-arg]
    """``ALLOWED_HOSTS`` that also contains the addresses of this server while ``allow_own_addresses`` is on.

    Django goes through the list for every request (``validate_host``); the addresses come from
    :func:`own_hosts`, which keeps them for :data:`KEEP_SECONDS`.
    """

    def __iter__(self) -> Iterator[str]:
        """The fixed names, then – if switched on – the addresses of this server."""
        yield from super().__iter__()
        if getattr(settings, "RENTALARS_ALLOW_OWN_ADDRESSES", True):
            yield from sorted(own_hosts())


class OwnAddressHostMiddleware:
    """Say once in the log when a request comes to an address of this server that is not entered in the configuration."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Log a new own address once, then answer as usual."""
        if getattr(settings, "RENTALARS_ALLOW_OWN_ADDRESSES", True):
            host = request.META.get("HTTP_HOST") or ""
            if host:
                name, _port = split_domain_port(host)
                if name and name not in _said and name not in getattr(settings, "RENTALARS_FIXED_HOSTS", ()):
                    if is_own_address(host) and len(_said) < 64:
                        _said.add(name)
                        logger.info(
                            "Host %s answered to: it is an address of this server (allow_own_addresses). "
                            "Enter it as allowed_hosts to make it permanent for the configuration.",
                            name,
                        )
        return self.get_response(request)


class DisallowedHostHint(logging.Filter):
    """Make the log entry of an unknown host name a one-line warning instead of an error with a traceback (ADM-016).

    Django logs ``DisallowedHost`` at level ERROR with the whole traceback; a scanner that tries addresses would fill
    the service log with it. The line stays – with the name that arrived – and says what to do.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Change the record to a warning without traceback; always keep it."""
        record.levelno = logging.WARNING
        record.levelname = "WARNING"
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True
