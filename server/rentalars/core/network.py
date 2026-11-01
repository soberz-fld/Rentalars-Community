# SPDX-License-Identifier: GPL-3.0-or-later
"""Connections to addresses that people enter in the interface (NFA-071, NFA-072).

Rentalars calls servers whose address a user typed in: calendars to read
(.ics links, PER-022) and to write (CalDAV, PER-023), webhooks (API-012)
and the IMAP and SMTP servers of mailboxes (EML-041). Such an address must
not become a way into the network the server stands in (server-side
request forgery). Every one of these connections therefore goes through
this module:

* The name is resolved here, and every address of the answer is checked.
  Refused are loopback, link-local, private (RFC 1918, ``fc00::/7``),
  shared (CGNAT, ``100.64.0.0/10``), multicast, reserved and unspecified
  addresses, everything else that is not globally reachable, and the
  addresses of this server itself – unless the operator allows them
  (``[network] allow_internal`` in the configuration file, see
  :func:`rentalars.config.load_config`): networks (``192.168.1.0/24``),
  single addresses and host names (``nas.local``). A local NAS or the
  company's Nextcloud with CalDAV is the typical case.
* The connection goes to exactly the address that was checked; there is no
  second lookup a changed DNS answer could slip into (DNS rebinding). TLS
  still checks the certificate against the name.
* Redirections are never followed automatically: the calendar client
  follows them by hand, each target checked again; webhooks do not follow
  them at all.
* If the environment of the service names a proxy for the address, the
  request goes through it as before (the operator's choice). The name is
  checked here all the same; resolving it again is then up to the proxy.

Addresses of the configuration file – the map servers, ``[email]``, the
database – are the operator's and do not pass through here.

Credentials (NFA-072) are the business of the callers: the calendar client
sends them only to exactly the scheme, host and port they were entered for
(:mod:`rentalars.personnel.calendar_client`).
"""

from __future__ import annotations

import functools
import http.client
import imaplib
import ipaddress
import smtplib
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend
from django.utils.translation import gettext as _

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

#: NAT64 prefixes: the last 32 bits are an IPv4 address, which is what counts.
_NAT64 = (ipaddress.ip_network("64:ff9b::/96"), ipaddress.ip_network("64:ff9b:1::/48"))

#: How long the addresses of this server are remembered, in seconds.
OWN_ADDRESSES_SECONDS = 600


class BlockedAddressError(OSError):
    """The address leads into an internal network the operator did not allow (NFA-071).

    ``str(error)`` is a text for the person who entered the address. It
    never names the address the name resolved to: that would tell how the
    internal network is laid out. :attr:`host` and :attr:`address` are for
    the self-check and the log.
    """

    def __init__(self, host: str, address: str = "") -> None:
        super().__init__(
            _(
                "The address leads into an internal network. Rentalars connects there only if the operator "
                "allows it in the configuration file (section [network], allow_internal)."
            )
        )
        self.host = host
        self.address = address


# --- What is internal ---------------------------------------------------------------------------------


def _effective(address: IPAddress) -> IPAddress:
    """The IPv4 address hidden in an IPv6 one (mapped or NAT64), or the address itself."""
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return address.ipv4_mapped
        if any(address in network for network in _NAT64):
            return ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)
    return address


def kind_of(address: str | IPAddress) -> str:
    """Why an address counts as internal: ``loopback``, ``link-local``, ``private`` … – or ``""`` (NFA-071)."""
    ip = _effective(ipaddress.ip_address(address) if isinstance(address, str) else address)
    if ip.is_unspecified:
        return "unspecified"
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        return "link-local"
    if ip.is_multicast:
        return "multicast"
    if isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.ip_network("100.64.0.0/10"):
        return "shared"
    if ip.is_reserved:
        return "reserved"
    if ip.is_private or not ip.is_global:
        return "private"
    return ""


@dataclass(frozen=True)
class Allowance:
    """What the operator allows: networks and host names (``[network] allow_internal``)."""

    networks: tuple[IPNetwork, ...] = ()
    names: frozenset[str] = frozenset()

    def allows_name(self, host: str) -> bool:
        """Whether this host name is allowed whatever it resolves to."""
        return host.lower().rstrip(".") in self.names

    def allows_address(self, address: IPAddress) -> bool:
        """Whether this address lies in an allowed network."""
        candidates = {address, _effective(address)}
        return any(ip.version == network.version and ip in network for ip in candidates for network in self.networks)


def parse_allowance(entries: Iterable[str]) -> Allowance:
    """Split the entries of ``allow_internal`` into networks and host names.

    Raises:
        ValueError: An entry is neither a network, an address nor a host name.
    """
    networks: list[IPNetwork] = []
    names: set[str] = set()
    for raw in entries:
        entry = raw.strip()
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
            continue
        except ValueError:
            pass
        name = entry.lower().rstrip(".")
        labels = name.split(".")
        if not all(label and len(label) <= 63 and label.replace("-", "").isalnum() for label in labels):
            raise ValueError(entry)
        names.add(name)
    return Allowance(tuple(networks), frozenset(names))


def allowance() -> Allowance:
    """The allowance of this installation, from the settings."""
    return _parse_cached(tuple(getattr(settings, "RENTALARS_NETWORK_ALLOW_INTERNAL", ()) or ()))


@functools.lru_cache(maxsize=8)
def _parse_cached(entries: tuple[str, ...]) -> Allowance:
    return parse_allowance(entries)


# --- The addresses of this server --------------------------------------------------------------------

_own_cache: tuple[float, frozenset[IPAddress]] | None = None


def _interface_addresses(proc: Path = Path("/proc")) -> set[IPAddress]:
    """Every address of the network interfaces (Linux), from ``/proc`` and the kernel."""
    from rentalars.core.resources import ipv4_addresses

    found: set[IPAddress] = set()
    try:
        lines = (proc / "net/if_inet6").read_text(encoding="ascii", errors="replace").splitlines()
    except OSError:
        lines = []
    for line in lines:
        fields = line.split()
        if len(fields) >= 6:
            try:
                found.add(ipaddress.IPv6Address(bytes.fromhex(fields[0])))
            except ValueError:
                continue
    try:
        devices = (proc / "net/dev").read_text(encoding="ascii", errors="replace").splitlines()[2:]
    except OSError:
        devices = []
    for line in devices:
        name = line.split(":", 1)[0].strip()
        for text in ipv4_addresses(name) if name else []:
            found.add(ipaddress.IPv4Address(text))
    return found


def _resolved(host: str) -> set[IPAddress]:
    try:
        answers = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        return set()
    result: set[IPAddress] = set()
    for *_rest, sockaddr in answers:
        try:
            result.add(ipaddress.ip_address(str(sockaddr[0]).split("%", 1)[0]))
        except ValueError:
            continue
    return result


def own_addresses() -> frozenset[IPAddress]:
    """The addresses of this server: its interfaces, its host name and the name of its address (NFA-071).

    A public address of the server is not internal by itself, but a request
    to it reaches this server – and with it services that listen only there.
    """
    global _own_cache
    now = time.monotonic()
    if _own_cache is not None and now - _own_cache[0] < OWN_ADDRESSES_SECONDS:
        return _own_cache[1]
    found = _interface_addresses()
    found |= _resolved(socket.gethostname())
    site = getattr(settings, "RENTALARS_URL", "")
    if site:
        host = urllib.parse.urlsplit(site).hostname
        if host:
            found |= _resolved(host)
    addresses = frozenset(found)
    _own_cache = (now, addresses)
    return addresses


# --- The check ---------------------------------------------------------------------------------------


def refusal(host: str, address: IPAddress, *, rules: Allowance | None = None) -> str:
    """Why a connection to ``address`` (for ``host``) is refused – ``""`` if it is allowed (NFA-071)."""
    rules = rules if rules is not None else allowance()
    if address.is_unspecified:
        return "unspecified"
    if rules.allows_name(host) or rules.allows_address(address):
        return ""
    kind = kind_of(address)
    if kind:
        return kind
    if address in own_addresses() or _effective(address) in own_addresses():
        return "own"
    return ""


def checked_addresses(host: str, port: int | None, *, family: int = 0) -> list[tuple[Any, ...]]:
    """Resolve a host and keep only the answers that may be connected to (NFA-071).

    Returns:
        The ``getaddrinfo`` entries of the allowed addresses, in the order
        of the answer.

    Raises:
        socket.gaierror: The name is unknown.
        BlockedAddressError: Every address of the answer is internal.
    """
    name = (host or "").strip().strip("[]")
    if not name:
        raise BlockedAddressError(host)
    answers = socket.getaddrinfo(name, port, family, socket.SOCK_STREAM)
    rules = allowance()
    allowed = []
    first_refused = ""
    for answer in answers:
        sockaddr = answer[4]
        try:
            address = ipaddress.ip_address(str(sockaddr[0]).split("%", 1)[0])
        except ValueError:
            continue
        if refusal(name, address, rules=rules):
            first_refused = first_refused or str(address)
            continue
        allowed.append(answer)
    if not allowed:
        raise BlockedAddressError(name, first_refused)
    return allowed


def check_entered_host(host: str) -> None:
    """The check when an address is entered, without asking DNS: an IP address or ``localhost`` (NFA-071).

    A name is checked when it is used (:func:`create_connection`) – it may
    resolve differently by then anyway.

    Raises:
        BlockedAddressError: The host is a refused address.
    """
    name = (host or "").strip().strip("[]").lower().rstrip(".")
    rules = allowance()
    if name == "localhost" or name.endswith(".localhost"):
        if not (rules.allows_name(name) or rules.allows_address(ipaddress.ip_address("127.0.0.1"))):
            raise BlockedAddressError(name, "127.0.0.1")
        return
    try:
        address = ipaddress.ip_address(name.split("%", 1)[0])
    except ValueError:
        return
    if refusal(name, address, rules=rules):
        raise BlockedAddressError(name, str(address))


def check_host(host: str, port: int | None = None) -> None:
    """Raise :class:`BlockedAddressError` if a host leads only to refused addresses (NFA-071)."""
    checked_addresses(host, port)


def create_connection(
    address: tuple[str, int],
    timeout: float | None = None,
    source_address: tuple[str, int] | None = None,
) -> socket.socket:
    """Like :func:`socket.create_connection`, but only to checked addresses (NFA-071).

    The name is resolved once; the socket connects to exactly one of the
    addresses that passed the check.
    """
    host, port = address
    last_error: OSError | None = None
    for family, kind, protocol, _name, sockaddr in checked_addresses(host, port):
        sock = socket.socket(family, kind, protocol)
        try:
            if timeout is not None and timeout is not getattr(socket, "_GLOBAL_DEFAULT_TIMEOUT", None):
                sock.settimeout(timeout)
            if source_address:
                sock.bind(source_address)
            sock.connect(sockaddr)
            return sock
        except OSError as error:
            last_error = error
            sock.close()
    raise last_error if last_error is not None else OSError("no address to connect to")


# --- HTTP (calendars, webhooks) ----------------------------------------------------------------------


class GuardedHTTPConnection(http.client.HTTPConnection):
    """An HTTP connection that connects only to checked addresses (NFA-071)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._create_connection = create_connection


class GuardedHTTPSConnection(http.client.HTTPSConnection):
    """An HTTPS connection that connects only to checked addresses; the certificate is checked against the name."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._create_connection = create_connection


class GuardedHTTPHandler(urllib.request.HTTPHandler):
    """``http://`` through :class:`GuardedHTTPConnection`."""

    def http_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        """Open the connection to the checked address."""
        return self.do_open(GuardedHTTPConnection, req)


class GuardedHTTPSHandler(urllib.request.HTTPSHandler):
    """``https://`` through :class:`GuardedHTTPSConnection`."""

    def https_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        """Open the connection to the checked address."""
        return self.do_open(GuardedHTTPSConnection, req, context=self._context)


def _is_loopback_name(host: str) -> bool:
    if host.lower().rstrip(".") == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _proxy_applies(prepared: urllib.request.Request) -> bool:
    """Whether the environment of the service names a proxy for this request (``https_proxy`` …)."""
    host = urllib.parse.urlsplit(prepared.full_url).hostname or ""
    if not host or _is_loopback_name(host):
        return False
    proxies = urllib.request.getproxies()
    return prepared.type in proxies and not urllib.request.proxy_bypass(host)


def open_url(prepared: urllib.request.Request, *, timeout: float, handlers: Iterable[Any] = ()) -> Any:
    """Send a request to an address a user entered, under the rules of the module (NFA-071).

    Args:
        prepared: The request.
        timeout: Seconds to wait for the connection and each answer.
        handlers: Further handlers, e.g. one that hands redirections back.

    Raises:
        urllib.error.URLError: As :func:`urllib.request.urlopen`; a refused
            address is a :class:`BlockedAddressError` in ``reason``.
    """
    extra = list(handlers)
    if _proxy_applies(prepared):
        # The proxy resolves the name itself; what Rentalars can do is check its own answer first.
        host = urllib.parse.urlsplit(prepared.full_url).hostname or ""
        try:
            check_host(host)
        except OSError as error:
            raise urllib.error.URLError(error) from error
        opener = urllib.request.build_opener(*extra)
    else:
        opener = urllib.request.build_opener(
            *extra, urllib.request.ProxyHandler({}), GuardedHTTPHandler, GuardedHTTPSHandler
        )
    return opener.open(prepared, timeout=timeout)


# --- Mail servers of mailboxes (IMAP, SMTP) ------------------------------------------------------------


class GuardedIMAP4(imaplib.IMAP4):
    """IMAP with STARTTLS, connected only to a checked address (NFA-071)."""

    def _create_socket(self, timeout: float | None) -> socket.socket:
        return create_connection((self.host, self.port), timeout)


class GuardedIMAP4SSL(imaplib.IMAP4_SSL):
    """IMAP over TLS, connected only to a checked address; the certificate is checked against the name."""

    def _create_socket(self, timeout: float | None) -> socket.socket:
        sock = create_connection((self.host, self.port), timeout)
        return self.ssl_context.wrap_socket(sock, server_hostname=self.host)


@functools.cache
def guarded_smtp_class(base: type[smtplib.SMTP]) -> type[smtplib.SMTP]:
    """``base`` (``smtplib.SMTP`` or ``smtplib.SMTP_SSL``) connecting only to checked addresses (NFA-071).

    Made when it is needed from the class the standard library has then, so
    that a stand-in of the tests is guarded the same way.
    """

    def _get_socket(self: smtplib.SMTP, host: str, port: int, timeout: float) -> socket.socket:
        sock = create_connection((host, port), timeout, self.source_address)
        if isinstance(self, smtplib.SMTP_SSL):
            sock = self.context.wrap_socket(sock, server_hostname=self._host)
        return sock

    return type(f"Guarded{base.__name__}", (base,), {"_get_socket": _get_socket, "__module__": __name__})


def smtp_client(*, use_ssl: bool) -> type[smtplib.SMTP]:
    """The SMTP client class for a mailbox's server: plain (then STARTTLS) or TLS from the start."""
    return guarded_smtp_class(smtplib.SMTP_SSL if use_ssl else smtplib.SMTP)


class GuardedSmtpBackend(EmailBackend):
    """Django's SMTP backend for the system mailbox, connected only to checked addresses (NFA-071, EML-041)."""

    @property
    def connection_class(self) -> type[smtplib.SMTP]:
        """The guarded client class."""
        return smtp_client(use_ssl=bool(self.use_ssl))
