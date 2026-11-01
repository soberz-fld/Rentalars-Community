# SPDX-License-Identifier: GPL-3.0-or-later
"""Talking to calendar servers: reading .ics links and writing into CalDAV calendars (PER-022, PER-023).

Only the standard library is used (``urllib``): Rentalars needs a handful of
requests, not an HTTP framework.

Safety rules for addresses that people enter
--------------------------------------------
* Only ``http://`` and ``https://`` – also after a redirection. ``webcal://``,
  which calendar programs hand out for subscriptions, is read as
  ``https://``.
* Every request gives up after :data:`TIMEOUT` seconds without an answer
  and after twice that time in total; an answer larger than
  :data:`MAX_BYTES` is refused.
* What a server answers is never shown to anybody. Errors are short texts
  that name the kind of problem (no answer, login refused, not found) and
  never the address, which may be a secret link.
* Credentials go only to exactly the scheme, host and port they were
  entered for (NFA-072): a redirection to any other host – also of the
  same domain – or from https to http loses them, and an address the
  server names in its answer (principal, calendar home, calendar) on
  another host is not asked at all. The only exceptions are the providers
  in :data:`CREDENTIAL_PARTNERS`: iCloud hands calendars out from
  ``p52-caldav.icloud.com`` when ``caldav.icloud.com`` is asked.
* Every connection goes through :mod:`rentalars.core.network` (NFA-071):
  internal addresses – loopback, private networks, this server … – are
  refused unless the operator allows them (``[network] allow_internal``),
  the connection goes to the address that was checked, and every
  redirection is checked again before it is followed.

CalDAV (PER-023)
----------------
:class:`CalDAVCalendar` writes one event per file, ``PUT`` with
``If-None-Match: *`` for a new one and ``If-Match: <ETag>`` for a change,
and ``DELETE`` for what is gone. Rentalars owns these events: if somebody
changed one on the phone (the server answers 412), Rentalars' version is
written over it. Google Calendar is not supported: its CalDAV access needs
OAuth.

The address may be the calendar itself or just the server
(``https://caldav.icloud.com``, ``https://cloud.example.de/remote.php/dav``):
:meth:`CalDAVCalendar.find_collection` then looks for the calendar
"Rentalars" of the account (RFC 6764 and RFC 4791 discovery) and creates it
if there is none.
"""

from __future__ import annotations

import base64
import http.client
import re
import secrets
import socket
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from email.message import Message
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree

from django.utils.translation import gettext as _

from rentalars import __version__
from rentalars.core.network import BlockedAddressError, check_entered_host, open_url

#: Seconds to wait for an answer.
TIMEOUT = 15

#: The largest answer read, in bytes (5 MB): a calendar of several years is far smaller.
MAX_BYTES = 5 * 1024 * 1024

#: How many redirections are followed.
MAX_REDIRECTS = 5

USER_AGENT = f"Rentalars/{__version__} (calendar)"

DAV = "DAV:"
CALDAV = "urn:ietf:params:xml:ns:caldav"

#: The name of the calendar Rentalars looks for, or creates, when only the server is given.
CALENDAR_NAME = "Rentalars"


class CalendarHttpError(Exception):
    """A calendar could not be read or written.

    ``str(error)`` is a short text for the person concerned; it never
    contains the address or anything the server answered.
    """

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class Answer:
    """What a server answered."""

    status: int
    headers: Message
    body: bytes
    url: str


def normalise_url(url: str) -> str:
    """Tidy an address that was entered: no spaces, ``webcal://`` read as ``https://``."""
    url = (url or "").strip()
    if url.lower().startswith("webcal://"):
        url = "https://" + url[len("webcal://") :]
    return url


def check_url(url: str) -> None:
    """Refuse everything but ``http://`` and ``https://`` with a host – and internal IP addresses (NFA-071).

    Raises:
        CalendarHttpError: The address cannot be used.
    """
    parts = urlsplit(url)
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise CalendarHttpError(_("Only addresses beginning with https:// or http:// can be used."))
    try:
        # NFA-071: an internal IP address or localhost is refused at once; a name when it is used.
        check_entered_host(parts.hostname)
    except BlockedAddressError as error:
        raise CalendarHttpError(str(error)) from error


#: NFA-072: providers that hand an account out from other hosts of their own. Credentials entered for a
#: host matching the first pattern may also go – over https on the standard port – to a host matching the
#: second. Every other host gets them only if it is exactly the one they were entered for.
CREDENTIAL_PARTNERS: tuple[tuple[re.Pattern[str], re.Pattern[str]], ...] = (
    # iCloud: caldav.icloud.com answers with the partition of the account, e.g. p52-caldav.icloud.com.
    (re.compile(r"(p\d{1,3}-)?caldav\.icloud\.com"), re.compile(r"p\d{1,3}-caldav\.icloud\.com")),
)

_DEFAULT_PORTS = {"http": 80, "https": 443}


def _origin(url: str) -> tuple[str, str, int | None]:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    try:
        port = parts.port
    except ValueError:
        port = None
    return scheme, (parts.hostname or "").lower().rstrip("."), port or _DEFAULT_PORTS.get(scheme)


def _may_send_credentials(entered: str, target: str) -> bool:
    """Whether the credentials entered for one address may go to another (NFA-072).

    Exactly the same scheme, host and port – or a partner host of a known
    provider (:data:`CREDENTIAL_PARTNERS`) over https.
    """
    first, second = _origin(entered), _origin(target)
    if not first[1]:
        return False
    if first == second:
        return True
    if first[0] != "https" or second[0] != "https" or first[2] != 443 or second[2] != 443:
        return False
    return any(left.fullmatch(first[1]) and right.fullmatch(second[1]) for left, right in CREDENTIAL_PARTNERS)


class _KeepRedirects(urllib.request.HTTPRedirectHandler):
    """Hand redirections back to the caller, who checks the target before following it."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        """Do not follow on our own."""
        return None


def _network_problem(error: BaseException) -> str:
    """Name the kind of network problem, without addresses."""
    reason: Any = getattr(error, "reason", error)
    if isinstance(reason, BlockedAddressError):
        # NFA-071: an internal address the operator did not allow – a text of its own, never the address.
        return str(reason)
    if isinstance(reason, TimeoutError | socket.timeout):
        text = _("no answer within %(seconds)d seconds") % {"seconds": TIMEOUT}
    elif isinstance(reason, socket.gaierror):
        text = _("the server name is unknown")
    elif isinstance(reason, ConnectionRefusedError):
        text = _("the connection was refused")
    elif isinstance(reason, ssl.SSLError | ssl.CertificateError):
        text = _("the secure connection failed (certificate)")
    else:
        text = _("the connection failed")
    return _("The server cannot be reached: %(problem)s.") % {"problem": text}


def _read(response: Any, deadline: float) -> bytes:
    """Read an answer up to :data:`MAX_BYTES` and the deadline."""
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = response.read(65536)
        if not chunk:
            return b"".join(chunks)
        size += len(chunk)
        if size > MAX_BYTES:
            raise CalendarHttpError(
                _("The answer is larger than %(megabytes)d MB.") % {"megabytes": MAX_BYTES // (1024 * 1024)}
            )
        if time.monotonic() > deadline:
            raise CalendarHttpError(_network_problem(TimeoutError()))
        chunks.append(chunk)


def request(
    method: str,
    url: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    credentials: tuple[str, str] | None = None,
    credentials_for: str | None = None,
) -> Answer:
    """Send one request, follow redirections under the rules of the module, and return the answer.

    Errors of the server (4xx, 5xx) come back as answers; only when no
    answer could be had at all is an exception raised.

    Args:
        method: The HTTP method.
        url: The address.
        body: What is sent, if anything.
        headers: Further headers.
        credentials: User name and password for HTTP basic authentication.
        credentials_for: The address the credentials were entered for
            (NFA-072); ``url`` if not given.

    Raises:
        CalendarHttpError: The address is not allowed, the server cannot be
            reached, the answer is too large, or there are too many
            redirections.
    """
    entered = credentials_for or url
    deadline = time.monotonic() + 2 * TIMEOUT
    for _attempt in range(MAX_REDIRECTS + 1):
        check_url(url)
        prepared = urllib.request.Request(url, data=body, method=method)  # noqa: S310 - scheme checked above
        prepared.add_header("User-Agent", USER_AGENT)
        for name, value in (headers or {}).items():
            prepared.add_header(name, value)
        if credentials is not None and _may_send_credentials(entered, url):
            token = base64.b64encode(f"{credentials[0]}:{credentials[1]}".encode()).decode("ascii")
            prepared.add_header("Authorization", f"Basic {token}")
        try:
            # NFA-071: only checked addresses, each redirection checked again on the next round.
            with open_url(prepared, timeout=TIMEOUT, handlers=[_KeepRedirects]) as response:
                status, answer_headers = response.status, response.headers
                data = _read(response, deadline)
        except urllib.error.HTTPError as error:
            status, answer_headers = error.code, error.headers
            try:
                data = _read(error, deadline)
            except (OSError, http.client.HTTPException):
                data = b""
            finally:
                error.close()
        except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError) as error:
            raise CalendarHttpError(_network_problem(error)) from error
        location = answer_headers.get("Location") if answer_headers else None
        if status in (301, 302, 303, 307, 308) and location:
            url = urljoin(url, location)
            if status == 303:
                method, body = "GET", None
            continue
        return Answer(status=status, headers=answer_headers, body=data, url=url)
    raise CalendarHttpError(_("Too many redirections."))


def fetch_calendar(url: str) -> bytes:
    """Read an .ics calendar from an address (PER-022).

    Raises:
        CalendarHttpError: See :func:`request`; also when the server refuses
            or does not know the address.
    """
    answer = request("GET", normalise_url(url), headers={"Accept": "text/calendar, */*;q=0.5"})
    if answer.status in (401, 403):
        raise CalendarHttpError(
            _("Access to the calendar was refused – is the link still valid?"), status=answer.status
        )
    if answer.status in (404, 410):
        raise CalendarHttpError(_("There is no calendar at this address (any more)."), status=answer.status)
    if not 200 <= answer.status < 300:
        raise CalendarHttpError(
            _("The calendar server answered with error %(status)d.") % {"status": answer.status}, status=answer.status
        )
    return answer.body


# --- CalDAV (PER-023) ------------------------------------------------------------------------------


@dataclass
class _Resource:
    """One ``<response>`` of a PROPFIND answer."""

    url: str
    types: set[str] = field(default_factory=set)
    name: str = ""
    principal: str = ""
    home: str = ""
    components: set[str] = field(default_factory=set)

    @property
    def is_calendar(self) -> bool:
        return f"{{{CALDAV}}}calendar" in self.types

    @property
    def takes_events(self) -> bool:
        return not self.components or "VEVENT" in self.components


_PROPFIND = (
    b'<?xml version="1.0" encoding="utf-8"?>'
    b'<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop>'
    b"<d:resourcetype/><d:displayname/><d:current-user-principal/><c:calendar-home-set/>"
    b"<c:supported-calendar-component-set/>"
    b"</d:prop></d:propfind>"
)

_MKCALENDAR = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<c:mkcalendar xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:set><d:prop>'
    f"<d:displayname>{CALENDAR_NAME}</d:displayname>"
    '<c:supported-calendar-component-set><c:comp name="VEVENT"/></c:supported-calendar-component-set>'
    "</d:prop></d:set></c:mkcalendar>"
).encode()


def _with_slash(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path if parts.path.endswith("/") else parts.path + "/"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


class CalDAVCalendar:
    """A calendar on a CalDAV server that Rentalars writes deployments into (PER-023)."""

    def __init__(self, url: str, username: str, password: str) -> None:
        self.url = _with_slash(normalise_url(url))
        #: NFA-072: the address the credentials were entered for; they go only there (and to partners).
        self.entered = self.url
        self.credentials = (username, password)

    # --- Plumbing -------------------------------------------------------------------------------

    def _send(
        self, method: str, url: str, *, body: bytes | None = None, headers: dict[str, str] | None = None
    ) -> Answer:
        if not _may_send_credentials(self.entered, url):
            # NFA-072: the server named an address on another host (principal, calendar home, calendar).
            raise CalendarHttpError(
                _(
                    "The calendar server refers to another server. Rentalars sends the login only to the server "
                    "it was entered for – enter the address of the calendar on that server."
                )
            )
        return request(
            method, url, body=body, headers=headers, credentials=self.credentials, credentials_for=self.entered
        )

    @staticmethod
    def _fail(answer: Answer) -> CalendarHttpError:
        status = answer.status
        if status == 401:
            text = _(
                "The calendar server refused the login. Check username and password – many servers want an "
                "app password here."
            )
        elif status == 403:
            text = _("The calendar server does not allow this. Check that the calendar may be written.")
        elif status in (404, 410):
            text = _("The calendar was not found. Check the address.")
        elif status == 405:
            text = _("The address does not lead to a CalDAV calendar.")
        elif status == 507:
            text = _("The calendar server has no room left.")
        else:
            text = _("The calendar server answered with error %(status)d.") % {"status": status}
        return CalendarHttpError(text, status=status)

    def _propfind(self, url: str, depth: int) -> list[_Resource]:
        answer = self._send(
            "PROPFIND",
            url,
            body=_PROPFIND,
            headers={"Depth": str(depth), "Content-Type": "application/xml; charset=utf-8"},
        )
        if answer.status != 207:
            raise self._fail(answer)
        try:
            root = ElementTree.fromstring(answer.body)  # noqa: S314 - expat refuses entity expansion attacks
        except ElementTree.ParseError as error:
            raise CalendarHttpError(_("The address does not lead to a CalDAV calendar.")) from error
        resources = []
        for item in root.iter(f"{{{DAV}}}response"):
            href = item.findtext(f"{{{DAV}}}href", default="").strip()
            resource = _Resource(url=urljoin(answer.url, href) if href else answer.url)
            for propstat in item.iter(f"{{{DAV}}}propstat"):
                if " 200 " not in f" {propstat.findtext(f'{{{DAV}}}status', default='')} ":
                    continue
                for prop in propstat.iter(f"{{{DAV}}}prop"):
                    kinds = prop.find(f"{{{DAV}}}resourcetype")
                    if kinds is not None:
                        resource.types |= {child.tag for child in kinds}
                    resource.name = (prop.findtext(f"{{{DAV}}}displayname") or resource.name or "").strip()
                    for tag, attribute in (
                        (f"{{{DAV}}}current-user-principal", "principal"),
                        (f"{{{CALDAV}}}calendar-home-set", "home"),
                    ):
                        target = prop.find(f"{tag}/{{{DAV}}}href")
                        if target is not None and (target.text or "").strip():
                            setattr(resource, attribute, urljoin(answer.url, target.text.strip()))
                    components = prop.find(f"{{{CALDAV}}}supported-calendar-component-set")
                    if components is not None:
                        resource.components |= {comp.get("name", "").upper() for comp in components}
            resources.append(resource)
        if not resources:
            raise CalendarHttpError(_("The address does not lead to a CalDAV calendar."))
        return resources

    # --- Finding the calendar -------------------------------------------------------------------

    def find_collection(self) -> str:
        """Return the address of the calendar to write into; see the module description.

        The calendar found is stored as the person's address and gets the
        credentials from then on – so it must lie on the server they were
        entered for (NFA-072), whatever the server answered.

        Raises:
            CalendarHttpError: The server cannot be reached, refuses the
                login, no calendar can be found or created, or the one found
                lies on another server.
        """
        found = self._find_collection()
        if not _may_send_credentials(self.entered, found):
            raise CalendarHttpError(
                _(
                    "The calendar server refers to another server. Rentalars sends the login only to the server "
                    "it was entered for – enter the address of the calendar on that server."
                )
            )
        return found

    def _find_collection(self) -> str:
        url = self.url
        tried_well_known = False
        for _step in range(4):
            resources = self._propfind(url, 0)
            here = resources[0]
            if here.is_calendar:
                if not here.takes_events:
                    raise CalendarHttpError(_("This calendar cannot hold appointments (only tasks, for example)."))
                return _with_slash(here.url)
            home = here.home
            if not home and here.principal:
                home = self._propfind(here.principal, 0)[0].home
            if home:
                return self._calendar_in(_with_slash(home))
            if tried_well_known:
                break
            url, tried_well_known = urljoin(url, "/.well-known/caldav"), True
        raise CalendarHttpError(_("No calendar was found at this address. Enter the address of a calendar."))

    def _calendar_in(self, home: str) -> str:
        """Find the calendar "Rentalars" in the calendar home of the account, or create it."""
        for resource in self._propfind(home, 1):
            if resource.is_calendar and resource.takes_events and resource.name.casefold() == CALENDAR_NAME.casefold():
                return _with_slash(resource.url)
        target = urljoin(home, f"rentalars-{secrets.token_hex(4)}/")
        answer = self._send("MKCALENDAR", target, body=_MKCALENDAR, headers={"Content-Type": "application/xml"})
        if answer.status not in (200, 201):
            raise CalendarHttpError(
                _(
                    "There is no calendar “Rentalars” in this account, and it could not be created. Create it on "
                    "the server and enter its address."
                ),
                status=answer.status,
            )
        return target

    # --- Writing --------------------------------------------------------------------------------

    def put(self, name: str, data: bytes, *, etag: str = "", new: bool = False) -> str:
        """Write one event file; returns the new ETag ("" if the server does not tell).

        Args:
            name: The file name in the calendar, e.g. ``rentalars-crewline-12_host.ics``.
            data: The calendar object (one VEVENT).
            etag: The ETag Rentalars got when it wrote the file last time.
            new: Rentalars has not written the file before.

        Raises:
            CalendarHttpError: The server refused it.
        """
        headers = {"Content-Type": "text/calendar; charset=utf-8"}
        if new:
            headers["If-None-Match"] = "*"
        elif etag:
            headers["If-Match"] = etag
        answer = self._send("PUT", self.url + name, body=data, headers=headers)
        if answer.status == 412:
            # The server has another version – written by Rentalars before, or changed on a phone.
            # Rentalars owns these events: its version wins.
            answer = self._send("PUT", self.url + name, body=data, headers={"Content-Type": headers["Content-Type"]})
        if not 200 <= answer.status < 300:
            raise self._fail(answer)
        return answer.headers.get("ETag", "") if answer.headers else ""

    def delete(self, name: str, *, etag: str = "") -> None:
        """Remove one event file; one that is gone already is fine.

        Raises:
            CalendarHttpError: The server refused it.
        """
        answer = self._send("DELETE", self.url + name, headers={"If-Match": etag} if etag else None)
        if answer.status == 412:
            answer = self._send("DELETE", self.url + name)
        if answer.status in (404, 410) or 200 <= answer.status < 300:
            return
        raise self._fail(answer)
