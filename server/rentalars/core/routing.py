# SPDX-License-Identifier: GPL-3.0-or-later
"""The route service: the kilometres of a trip as a suggestion (LOG-017, NFA-050).

The decision: the route service is optional – it can be installed and switched on, also afterwards. Without it the
kilometres are entered by hand. Without a route
service the planner types the kilometres of a vehicle on a trip in by hand;
with one, the dialog of the vehicle offers a button that fills in the
planned kilometres – a suggestion, always changeable.

The operator sets the service up on the server (``deploy/route.sh``):

* ``sudo rentalars route install --region bayern`` installs the router
  Routino with the map of OpenStreetMap for Germany or one Bundesland on
  this server – positions never leave it;
* ``sudo rentalars route register --url https://…`` names an
  OSRM-compatible routing server the operator runs himself or one hosted in
  Germany (NFA-050).

Either writes ``route-local.conf`` next to the configuration file
(``/etc/rentalars/route-local.conf``)::

    [route]
    kind = routino
    router = /usr/bin/routino-router
    data_dir = /opt/rentalars/routes/data-20261017-a1b2
    prefix = rentalars
    profiles = /usr/share/routino/profiles.xml
    translations = /usr/share/routino/translations.xml
    region = bayern
    data_date = 2026-10-15
    installed_at = 2026-10-17T10:00:00+02:00

or ``kind = osrm`` with ``url = https://…``. Only root can write the file.
Rentalars reads it at every use, like ``ai-local.conf`` – nothing has to be
restarted. The address of an OSRM server is the operator's, like the map
servers of the configuration file, so it does not pass the network guard of
addresses typed into forms (NFA-071, ``core.network``); a server on this
machine is reached without a proxy, like the local AI.

The places of a trip are located with the geocoding of the maps
(``core.geocoding``, UIX-034): a position kept in ``AddressPosition`` –
found once or set by hand on a map – is used as it is; a missing one is
asked for and kept.

:func:`_run` (Routino) and :func:`_send` (OSRM) are the only places that run
a program or touch the network; the tests replace them.
"""

from __future__ import annotations

import configparser
import datetime
import http.client
import ipaddress
import json
import logging
import re
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

#: The name of the file next to the configuration file.
FILE_NAME = "route-local.conf"
SECTION = "route"
KINDS = ("routino", "osrm")

#: Seconds Routino may take for one trip; a route across Germany takes a few on a small server.
ROUTINO_TIMEOUT = 60
#: Seconds an OSRM server may take to answer.
OSRM_TIMEOUT = 15
#: The largest answer read from an OSRM server; a route without geometry is a few kilobytes.
MAX_BYTES = 1024 * 1024
#: Routino takes at most 99 waypoints in one call; a trip has far fewer.
MAX_POINTS = 99
#: How many addresses one suggestion asks the geocoder about at most (one per second, as the maps do).
LOOKUPS_PER_REQUEST = 5
#: From this age on (days) the panel suggests "sudo rentalars route update": roads change.
OLD_AFTER_DAYS = 180

#: The operator's commands, shown on the settings page (deploy/route.sh).
INSTALL_COMMAND = "sudo rentalars route install --region BUNDESLAND"
REGISTER_COMMAND = "sudo rentalars route register --url https://…"
UPDATE_COMMAND = "sudo rentalars route update"
REMOVE_COMMAND = "sudo rentalars route remove"

#: The regions of ``rentalars route install --region``: the extracts of Geofabrik for Germany and its Länder.
REGIONS = {
    "germany": "",
    "baden-wuerttemberg": "Baden-Württemberg",
    "bayern": "Bayern",
    "berlin": "Berlin",
    "brandenburg": "Brandenburg",
    "bremen": "Bremen",
    "hamburg": "Hamburg",
    "hessen": "Hessen",
    "mecklenburg-vorpommern": "Mecklenburg-Vorpommern",
    "niedersachsen": "Niedersachsen",
    "nordrhein-westfalen": "Nordrhein-Westfalen",
    "rheinland-pfalz": "Rheinland-Pfalz",
    "saarland": "Saarland",
    "sachsen": "Sachsen",
    "sachsen-anhalt": "Sachsen-Anhalt",
    "schleswig-holstein": "Schleswig-Holstein",
    "thueringen": "Thüringen",
}

#: A distance of Routino's text output: "6.852 km".
_KM = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*km\s*$")
#: Routino's error for a waypoint without a road nearby: "Cannot find node close to specified point 2."
_NO_NODE = re.compile(r"Cannot find node close to specified point (\d+)")
#: OSRM's message for a coordinate without a road nearby: "Could not find a matching segment for coordinate 1".
_NO_SEGMENT = re.compile(r"coordinate (\d+)")


@dataclass(frozen=True)
class RouteService:
    """What the operator's command wrote about the route service."""

    #: ``routino`` – installed on this server – or ``osrm`` – a routing server named by "register".
    kind: str
    router: str = ""
    data_dir: str = ""
    prefix: str = "rentalars"
    profiles: str = ""
    translations: str = ""
    url: str = ""
    #: The region of the map (``bayern``, ``germany``), empty for a file of the operator's.
    region: str = ""
    data_date: datetime.date | None = None
    installed_at: str = ""
    #: The file it was read from.
    source: str = ""

    @property
    def region_label(self) -> str:
        """The region as people read it: "Bayern", "Deutschland"."""
        if self.region == "germany":
            return _("Germany")
        return REGIONS.get(self.region, self.region)

    @property
    def age_days(self) -> int | None:
        """How many days old the map data are; ``None`` if unknown or for an OSRM server."""
        if self.data_date is None:
            return None
        return max(0, (timezone.localdate() - self.data_date).days)

    @property
    def is_old(self) -> bool:
        """Whether the map data are old enough to suggest an update."""
        age = self.age_days
        return age is not None and age >= OLD_AFTER_DAYS


class RouteConfigError(Exception):
    """The file exists but cannot be used; ``str(error)`` says why (for the settings page)."""


class RouteError(Exception):
    """No kilometres could be had; ``str(error)`` is a text for the planner."""


class _NoRoadError(Exception):
    """The router knows no road near the waypoint with this index (0 = the first)."""

    def __init__(self, index: int) -> None:
        super().__init__(index)
        self.index = index


class _NoRouteError(Exception):
    """The router found no route between the waypoints; which leg it was is not said."""


# --- The file of the operator's command -------------------------------------------------------------------


def config_file() -> Path | None:
    """Where the operator's command writes about the route service; ``None`` without a configuration file."""
    explicit = getattr(settings, "RENTALARS_ROUTE_LOCAL_FILE", None)
    if explicit:
        return Path(explicit)
    config = getattr(settings, "RENTALARS_CONFIG_PATH", None)
    if not config:
        return None
    return Path(config).parent / FILE_NAME


def acceptable_url(url: str) -> bool:
    """Whether an OSRM server may be named: https, or http on this machine only (NFA-050)."""
    try:
        parts = urlsplit(url)
        parts.port  # noqa: B018 - raises on a bad port
    except ValueError:
        return False
    host = (parts.hostname or "").lower().rstrip(".")
    if not host or parts.query or parts.fragment or parts.username or parts.password:
        return False
    if parts.scheme == "https":
        return True
    return parts.scheme == "http" and _is_loopback(host)


def _is_loopback(host: str) -> bool:
    """Whether a host name or address is this machine: ``localhost``, 127.0.0.0/8 or ``::1``."""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _date(text: str) -> datetime.date | None:
    """A date as the command writes it (2026-10-15); ``None`` if missing or unreadable."""
    try:
        return datetime.date.fromisoformat(text.strip()) if text.strip() else None
    except ValueError:
        return None


def route_service() -> RouteService | None:
    """The route service as the operator set it up; ``None`` if there is none.

    Raises:
        RouteConfigError: The file is there, but unreadable, of an unknown
            kind, or names a router, map data or address that cannot be used.
    """
    path = config_file()
    if path is None or not path.is_file():
        return None
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(path, encoding="utf-8")
    except (OSError, configparser.Error, UnicodeDecodeError) as error:
        raise RouteConfigError(_("%(file)s cannot be read: %(error)s") % {"file": path, "error": error}) from error
    if not parser.has_section(SECTION):
        raise RouteConfigError(_("%(file)s has no section [route].") % {"file": path})
    section = parser[SECTION]
    kind = section.get("kind", "").strip().lower()
    common = {
        "region": section.get("region", "").strip(),
        "data_date": _date(section.get("data_date", "")),
        "installed_at": section.get("installed_at", "").strip(),
        "source": str(path),
    }
    if kind == "osrm":
        url = section.get("url", "").strip().rstrip("/")
        if not acceptable_url(url):
            raise RouteConfigError(
                _("%(file)s names no usable address of a routing server: https, or http on this machine only.")
                % {"file": path}
            )
        return RouteService(kind=kind, url=url, **common)
    if kind == "routino":
        router = section.get("router", "").strip()
        data_dir = section.get("data_dir", "").strip()
        prefix = section.get("prefix", "rentalars").strip() or "rentalars"
        if not router.startswith("/") or not Path(router).is_file():
            raise RouteConfigError(
                _("The router %(router)s named in %(file)s is missing. Set the route service up again.")
                % {"router": router or "–", "file": path}
            )
        if not data_dir.startswith("/") or not (Path(data_dir) / f"{prefix}-nodes.mem").is_file():
            raise RouteConfigError(
                _("The map data in %(folder)s named in %(file)s are missing. Set the route service up again.")
                % {"folder": data_dir or "–", "file": path}
            )
        return RouteService(
            kind=kind,
            router=router,
            data_dir=data_dir,
            prefix=prefix,
            profiles=section.get("profiles", "").strip(),
            translations=section.get("translations", "").strip(),
            **common,
        )
    raise RouteConfigError(
        _("%(file)s names an unknown kind of route service: “%(kind)s”.") % {"file": path, "kind": kind or "–"}
    )


def route_service_or_none() -> RouteService | None:
    """Like :func:`route_service`, but an unusable file counts as "not set up"."""
    try:
        return route_service()
    except RouteConfigError:
        return None


def route_service_enabled() -> bool:
    """Whether the dialogs offer kilometres from the route (LOG-017); otherwise they are typed in by hand."""
    return route_service_or_none() is not None


def _service() -> RouteService:
    """The route service to ask; a planner-readable error without one."""
    try:
        service = route_service()
    except RouteConfigError as error:
        logger.warning("Route service unusable: %s", error)
        raise RouteError(_("The route service cannot be used at the moment; the settings show why.")) from error
    if service is None:
        raise RouteError(_("No route service is set up. Enter the kilometres by hand."))
    return service


# --- Distances --------------------------------------------------------------------------------------------


def distance_km(points: Sequence[tuple[float, float]], *, labels: Sequence[str] | None = None) -> Decimal:
    """The kilometres of a route over the points in their order (LOG-017).

    One leg per consecutive pair of points, summed and rounded to 0.1 km;
    the route is the quickest for a motor car.

    Args:
        points: Latitude and longitude of each point, in the order driven.
        labels: The name of each point for error texts ("Lager", "Stadthalle");
            without them the points are numbered.

    Raises:
        RouteError: No route service is set up, it does not answer, a point
            lies far from any road or no route connects two points.
    """
    service = _service()
    points = [(float(lat), float(lon)) for lat, lon in points]
    names = list(labels) if labels is not None and len(labels) == len(points) else []
    if not names:
        names = [_("point %(number)d") % {"number": number} for number in range(1, len(points) + 1)]
    if len(points) < 2:
        return Decimal("0.0")
    if len(points) > MAX_POINTS:
        raise RouteError(_("A route can have at most %(count)d places.") % {"count": MAX_POINTS})
    try:
        km = _kilometres(service, points)
    except _NoRoadError as error:
        raise _no_road(service, names[min(error.index, len(names) - 1)]) from error
    except _NoRouteError as error:
        if len(points) == 2:
            raise _no_route(names[0], names[1]) from error
        km = None
    if km is None:
        # Which leg has no route? Asked one by one, so that the text can name the two places.
        for index in range(len(points) - 1):
            try:
                _kilometres(service, points[index : index + 2])
            except _NoRoadError as error:
                raise _no_road(service, names[index + min(error.index, 1)]) from error
            except _NoRouteError as error:
                raise _no_route(names[index], names[index + 1]) from error
        raise _no_route(names[0], names[-1])
    return km.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _no_road(service: RouteService, name: str) -> RouteError:
    """The text for a place far from any road – with the region of the map, which it may lie outside."""
    if service.kind == "routino" and service.region and service.region != "germany":
        return RouteError(
            _("There is no road near “%(place)s” in the map of the route service (%(region)s).")
            % {"place": name, "region": service.region_label}
        )
    return RouteError(_("There is no road near “%(place)s” in the map of the route service.") % {"place": name})


def _no_route(start: str, end: str) -> RouteError:
    """The text for two places no road connects."""
    return RouteError(_("No route was found between “%(start)s” and “%(end)s”.") % {"start": start, "end": end})


def _did_not_answer() -> RouteError:
    """The text for a service that cannot be asked; the details go to the log."""
    return RouteError(_("The route service did not answer. Try again later or enter the kilometres by hand."))


def _kilometres(service: RouteService, points: Sequence[tuple[float, float]]) -> Decimal:
    """The kilometres over the points, unrounded; :class:`_NoRoadError` and :class:`_NoRouteError` name what is missing."""
    if service.kind == "osrm":
        return _osrm_kilometres(service, points)
    return _routino_kilometres(service, points)


# --- Routino on this server -------------------------------------------------------------------------------


def routino_command(service: RouteService, points: Sequence[tuple[float, float]]) -> list[str]:
    """The call of Routino's router for the quickest route of a motor car over the points, as plain text."""
    command = [service.router, f"--dir={service.data_dir}", f"--prefix={service.prefix}"]
    if service.profiles:
        command.append(f"--profiles={service.profiles}")
    if service.translations:
        command.append(f"--translations={service.translations}")
    command += ["--transport=motorcar", "--quickest"]
    for number, (lat, lon) in enumerate(points, start=1):
        command += [f"--lat{number}={lat:.6f}", f"--lon{number}={lon:.6f}"]
    command += ["--output-text", "--output-stdout", "--quiet"]
    return command


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run the router; replaced in the tests."""
    return subprocess.run(  # noqa: S603 - the router named by root in route-local.conf, arguments as a list
        command, capture_output=True, encoding="utf-8", errors="replace", timeout=ROUTINO_TIMEOUT, check=False
    )


def parse_routino_text(text: str) -> Decimal:
    """The kilometres of Routino's text output (``--output-text``): the sum of its sections.

    Every line of a junction or waypoint carries the distance of its section
    and the total so far; the sections have three decimals, the total one.

    Raises:
        ValueError: The text holds no route.
    """
    total = Decimal(0)
    lines = 0
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        distances = [match.group(1) for field in line.split("\t") if (match := _KM.match(field))]
        if len(distances) < 2:
            continue
        total += Decimal(distances[0])
        lines += 1
    if not lines:
        raise ValueError("no route in the output of the router")
    return total


def _routino_kilometres(service: RouteService, points: Sequence[tuple[float, float]]) -> Decimal:
    """Ask Routino's router on this server, all points in one call (it takes up to 99)."""
    try:
        result = _run(routino_command(service, points))
    except subprocess.TimeoutExpired as error:
        logger.warning("The router took longer than %s seconds", ROUTINO_TIMEOUT)
        raise _did_not_answer() from error
    except OSError as error:
        logger.warning("The router cannot be run: %s", error)
        raise _did_not_answer() from error
    if result.returncode != 0:
        message = f"{result.stderr}\n{result.stdout}"
        found = _NO_NODE.search(message)
        if found:
            raise _NoRoadError(int(found.group(1)) - 1)
        if "Cannot find" in message and "route" in message:
            raise _NoRouteError
        logger.warning("The router failed (%s): %s", result.returncode, message.strip()[:500])
        raise _did_not_answer()
    try:
        return parse_routino_text(result.stdout)
    except (ValueError, InvalidOperation) as error:
        logger.warning("The output of the router cannot be read: %s", result.stdout[:500])
        raise _did_not_answer() from error


# --- An OSRM server ---------------------------------------------------------------------------------------


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """A redirection is not followed: the positions are meant for the server the operator named."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        """Do not follow."""
        return None


def osrm_url(service: RouteService, points: Sequence[tuple[float, float]]) -> str:
    """The question for the route over the points, as OSRM takes it: longitude first."""
    coordinates = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)
    return f"{service.url}/route/v1/driving/{coordinates}?overview=false&steps=false"


def _send(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
    """One request to the OSRM server: the status and the body of the answer (also of an error).

    A server on this machine is asked without a proxy, as the local AI is;
    any other through the proxies of the environment, as the geocoder is.

    Raises:
        RouteError: No answer could be had at all.
    """
    from rentalars.core.geocoding import user_agent

    handlers: list[Any] = [_NoRedirects]
    if _is_loopback((urlsplit(url).hostname or "").lower()):
        handlers.insert(0, urllib.request.ProxyHandler({}))
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(url, headers={"User-Agent": user_agent(), **headers})  # noqa: S310 - checked
    try:
        with opener.open(request, timeout=OSRM_TIMEOUT) as response:
            return response.status, response.read(MAX_BYTES)
    except urllib.error.HTTPError as error:
        try:
            return error.code, error.read(MAX_BYTES)
        finally:
            error.close()
    except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError) as error:
        logger.warning("The routing server cannot be reached: %s", error)
        raise _did_not_answer() from error


def _osrm_kilometres(service: RouteService, points: Sequence[tuple[float, float]]) -> Decimal:
    """Ask an OSRM server, all points in one request; it answers in metres."""
    status, body = _send(osrm_url(service, points), {"Accept": "application/json"})
    try:
        answer = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        answer = None
    if not isinstance(answer, dict):
        logger.warning("The routing server answered %s without a route", status)
        raise _did_not_answer()
    code = str(answer.get("code", ""))
    if code == "NoSegment":
        found = _NO_SEGMENT.search(str(answer.get("message", "")))
        raise _NoRoadError(int(found.group(1)) if found else 0)
    if code == "NoRoute":
        raise _NoRouteError
    try:
        if code != "Ok" or status != 200:
            raise ValueError(code)
        metres = Decimal(str(answer["routes"][0]["distance"]))
    except (KeyError, IndexError, TypeError, ValueError, InvalidOperation) as error:
        logger.warning("The routing server answered %s: %s", status, code)
        raise _did_not_answer() from error
    return metres / 1000


# --- Trips ------------------------------------------------------------------------------------------------


def trip_distance(trip: Any) -> Decimal:
    """The kilometres of a trip from its start over its stops to its destination (LOG-017, PRJ-097).

    The places are located as the map of the project locates them – a
    position kept or set by hand is used as it is; a missing one is asked
    for (one per second) and kept.

    Raises:
        RouteError: No route service is set up, a place has no address or
            was not found, or no route is known.
    """
    _service()  # first: without a route service nothing else matters
    places = list(trip.places)
    for place in places:
        if not place.has_address:
            raise RouteError(_("“%(place)s” has no address yet.") % {"place": place.label})
    points = [_position(place) for place in _located(places)]
    return distance_km(points, labels=[place.label for place in places])


def _located(places: list[Any]) -> list[Any]:
    """The places with their positions: kept ones from the database, missing ones from the geocoder (UIX-034)."""
    from rentalars.core import geocoding
    from rentalars.core.maps import LOOKUP_BUDGET_SECONDS, attach_positions
    from rentalars.core.models import AddressPosition, PositionSource

    attach_positions(places)
    asked: dict[str, Any] = {}
    deadline = time.monotonic() + LOOKUP_BUDGET_SECONDS
    for place in places:
        if place.position is not None:
            continue
        if place.key in asked:
            place.position = asked[place.key]
            continue
        if not settings.RENTALARS_MAPS.geocoder_url:
            raise RouteError(
                _("The position of “%(place)s” is not known and no map search is configured: set it on the map.")
                % {"place": place.label}
            )
        if len(asked) >= LOOKUPS_PER_REQUEST or time.monotonic() > deadline:
            raise RouteError(_("Not all addresses could be looked up yet. Try again in a moment."))
        try:
            found = geocoding.look_up(place.address)
        except geocoding.GeocoderError as error:
            raise RouteError(str(error)) from error
        position, _created = AddressPosition.objects.get_or_create(
            key=place.key,
            defaults={
                "address": place.address[:500],
                "latitude": found.latitude if found else None,
                "longitude": found.longitude if found else None,
                "source": PositionSource.FOUND if found else PositionSource.NOT_FOUND,
                "found_name": found.name if found else "",
            },
        )
        asked[place.key] = position
        place.position = position
    return places


def _position(place: Any) -> tuple[float, float]:
    """Latitude and longitude of a located place; a place the geocoder did not find is named."""
    if not place.is_located:
        raise RouteError(
            _("The address of “%(place)s” was not found. Set its position on the map of the project.")
            % {"place": place.label}
        )
    return float(place.position.latitude), float(place.position.longitude)


# --- For the settings page --------------------------------------------------------------------------------


def route_status() -> dict[str, Any]:
    """The route service for the settings page: set up or not, kind, region, age of the map (LOG-017)."""
    status: dict[str, Any] = {
        "service": None,
        "error": "",
        "install_command": INSTALL_COMMAND,
        "register_command": REGISTER_COMMAND,
        "update_command": UPDATE_COMMAND,
        "remove_command": REMOVE_COMMAND,
        "regions": [slug for slug in REGIONS if slug != "germany"],
    }
    try:
        status["service"] = route_service()
    except RouteConfigError as error:
        status["error"] = str(error)
    return status
