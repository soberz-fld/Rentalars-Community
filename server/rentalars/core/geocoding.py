# SPDX-License-Identifier: GPL-3.0-or-later
"""Asking the geocoder where an address lies (UIX-034).

The geocoder is Nominatim, the search of OpenStreetMap – or any server that
answers like it, named in ``[maps] geocoder_url`` of the configuration file.
Rentalars asks it from the server, never from the browser, and only for an
address the map is opened for (``core.maps``); the answer is kept, so every
address is asked for once.

The usage policy of the public Nominatim server
(https://operations.osmfoundation.org/policies/nominatim/) is kept:

* at most one request per second – across all processes of the
  installation (a lock file in the data directory),
* a User-Agent that names the application – and the address
  of the installation (:func:`user_agent`), so that the operators of the
  public server can tell installations apart and reach the right one,
* no search while typing: addresses are only looked up when a map is shown,
  never as suggestions in an address field.

:func:`_send` is the only place that touches the network; the tests replace
it (and :data:`_sleep`).
"""

from __future__ import annotations

import contextlib
import fcntl
import http.client
import json
import logging
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from django.conf import settings
from django.utils.translation import gettext as _

from rentalars import __version__

logger = logging.getLogger(__name__)

#: Seconds to wait for an answer.
TIMEOUT = 10

#: The public Nominatim takes one request per second and application.
MIN_INTERVAL = 1.0

#: The largest answer read; one hit is a few hundred bytes.
MAX_BYTES = 256 * 1024

USER_AGENT = f"Rentalars/{__version__} (maps)"


def user_agent() -> str:
    """The User-Agent of a request: the application and the origin of the installation (UIX-034).

    ``Rentalars/<version> (maps; +https://verleih.example)``; only the scheme and host of ``[rentalars] url``,
    never a path. Without a usable address the application alone.
    """
    parsed = urllib.parse.urlsplit(str(getattr(settings, "RENTALARS_URL", "") or ""))
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return USER_AGENT
    host = parsed.netloc.rpartition("@")[2]  # never access data, should the address carry any
    return f"Rentalars/{__version__} (maps; +{parsed.scheme}://{host})"


class GeocoderError(Exception):
    """The geocoder could not be asked; ``str(error)`` is a German text for the page."""


@dataclass(frozen=True)
class Found:
    """The answer for one address: its position, or ``None`` if the geocoder knows no such place."""

    latitude: Decimal
    longitude: Decimal
    name: str


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """A redirection is not followed: the address is meant for the configured server only."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        """Do not follow."""
        return None


_OPENER = urllib.request.build_opener(_NoRedirects)

#: Replaced in the tests, which must not wait.
_sleep = time.sleep

_turn = threading.Lock()
#: When this process last asked; used when the lock file cannot be written.
_last_request = 0.0


def _wait_turn() -> None:
    """Keep :data:`MIN_INTERVAL` between two requests of the whole installation.

    The time of the last request is kept in a small file of the data
    directory, locked while it is read and written: the workers of the
    application server are separate processes. Without a writable data
    directory at least the threads of this process wait for each other.
    """
    global _last_request
    with _turn:
        handle = None
        with contextlib.suppress(OSError):
            settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
            handle = open(settings.DATA_DIR / "geocoder.lock", "a+", encoding="ascii")  # noqa: SIM115
        try:
            last = _last_request
            if handle is not None:
                fcntl.flock(handle, fcntl.LOCK_EX)
                handle.seek(0)
                with contextlib.suppress(ValueError):
                    last = max(last, float(handle.read().strip() or 0))
            pause = last + MIN_INTERVAL - time.time()
            if pause > 0:
                _sleep(min(pause, MIN_INTERVAL))
            _last_request = time.time()
            if handle is not None:
                handle.seek(0)
                handle.truncate()
                handle.write(f"{_last_request:.3f}")
                handle.flush()
        finally:
            if handle is not None:
                handle.close()  # closing releases the lock


def _send(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
    """One request to the geocoder: the status and the body of the answer.

    Raises:
        GeocoderError: No answer could be had at all.
    """
    prepared = urllib.request.Request(url, headers=headers)  # noqa: S310 - the address is given by the operator
    try:
        with _OPENER.open(prepared, timeout=TIMEOUT) as response:
            return response.status, response.read(MAX_BYTES)
    except urllib.error.HTTPError as error:
        error.close()
        return error.code, b""
    except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError) as error:
        raise GeocoderError(_network_problem(error)) from error


def _network_problem(error: BaseException) -> str:
    reason: Any = getattr(error, "reason", error)
    if isinstance(reason, TimeoutError | socket.timeout):
        return _("The map search did not answer within %(seconds)d seconds.") % {"seconds": TIMEOUT}
    if isinstance(reason, socket.gaierror):
        return _("The map search cannot be reached: the server name is unknown.")
    if isinstance(reason, ssl.SSLError | ssl.CertificateError):
        return _("The map search cannot be reached: the secure connection failed.")
    return _("The map search cannot be reached.")


def search_url(address: str) -> str:
    """The address of the question for one address, as Nominatim takes it."""
    base = settings.RENTALARS_MAPS.geocoder_url
    query = urllib.parse.urlencode(
        {"q": address, "format": "jsonv2", "limit": "1", "accept-language": settings.LANGUAGE_CODE}
    )
    return f"{base}{'&' if '?' in base else '?'}{query}"


def _coordinate(value: Any, limit: int) -> Decimal:
    number = Decimal(str(value)).quantize(Decimal("0.000001"))
    if not -limit <= number <= limit:
        raise InvalidOperation
    return number


def look_up(address: str) -> Found | None:
    """Ask the geocoder where an address lies.

    Returns:
        The first hit, or ``None`` if the geocoder knows no such place.

    Raises:
        GeocoderError: The geocoder is switched off, cannot be reached or
            answers with an error; nothing is known then.
    """
    if not settings.RENTALARS_MAPS.geocoder_url:
        raise GeocoderError(_("No map search is configured."))
    _wait_turn()
    status, body = _send(search_url(address), {"User-Agent": user_agent(), "Accept": "application/json"})
    if status == 429:
        raise GeocoderError(_("The map search is busy. Try again in a minute."))
    if status != 200:
        logger.warning("Geocoder answered %s", status)
        raise GeocoderError(_("The map search answered with an error (%(status)s).") % {"status": status})
    try:
        hits = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GeocoderError(_("The answer of the map search cannot be read.")) from error
    if not isinstance(hits, list) or not hits:
        return None
    hit = hits[0]
    if not isinstance(hit, dict):
        raise GeocoderError(_("The answer of the map search cannot be read."))
    try:
        return Found(
            latitude=_coordinate(hit.get("lat"), 90),
            longitude=_coordinate(hit.get("lon"), 180),
            name=str(hit.get("display_name") or "")[:300],
        )
    except (InvalidOperation, ValueError, TypeError) as error:
        raise GeocoderError(_("The answer of the map search cannot be read.")) from error
