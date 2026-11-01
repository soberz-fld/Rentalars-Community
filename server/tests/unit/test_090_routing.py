# SPDX-License-Identifier: GPL-3.0-or-later
"""LOG-017: the kilometres of a trip suggested by a route service – optional, installed afterwards.

The requirement: the route service is optional, can be installed or activated afterwards; if it is not installed,
the kilometres are entered by hand. The catalogue: the kilometres are suggested by a route calculation – through a
service that runs in Germany or at the operator himself (NFA-050) – and can always be changed.

* The operator sets the service up on the server: Routino with the map of OpenStreetMap
  (``sudo rentalars route install``) or an OSRM server of his own or in Germany
  (``sudo rentalars route register``); either writes ``route-local.conf``, which Rentalars reads at every use.
* ``trip_distance`` locates the places of a trip like the maps and asks the service; errors name the place.
* The dialog of a vehicle on a trip asks ``projects:trip_route``; the settings show the service read-only.

No test reaches the internet: Routino's answers were recorded from the real router (3.4.1) on the small map
:data:`GRID_OSM`, the geocoder is ``tests.geocoder_fake``. Where Routino is installed, one test processes that map
and asks the real router, and one runs ``deploy/route.sh`` end to end in a test folder.
"""

from __future__ import annotations

import datetime
import http.server
import json
import os
import shutil
import subprocess
import tempfile
import threading
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest import SkipTest, mock

from django.test import override_settings
from django.urls import reverse

from rentalars.core import routing
from rentalars.core.models import AddressPosition, CompanyProfile, PositionSource
from rentalars.projects import course
from rentalars.projects.models import PhaseKind
from rentalars.projects.trips import trips_of
from tests.api.base import API, ApiTestCase
from tests.geocoder_fake import FakeGeocoder
from tests.helpers import RentalarsTestCase, at, make_project
from tests.ui.base import UiTestCase

ROOT = Path(__file__).resolve().parents[2]
WAREHOUSE = "Industriestraße 5, 12345 Musterstadt"
MARKET = "Marktplatz 1, 12345 Musterstadt"

#: A small map: a square of roads of about 3.4 by 5.6 km near 52° N 13° E with a road through its middle,
#: an island road far off and a footway that motor cars do not use.
GRID_OSM = """<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6" generator="Rentalars test">
  <node id="1" lat="52.0000" lon="13.0000" version="1"/>
  <node id="2" lat="52.0000" lon="13.0500" version="1"/>
  <node id="3" lat="52.0000" lon="13.1000" version="1"/>
  <node id="4" lat="52.0500" lon="13.1000" version="1"/>
  <node id="5" lat="52.0500" lon="13.0500" version="1"/>
  <node id="6" lat="52.0500" lon="13.0000" version="1"/>
  <node id="7" lat="52.1000" lon="13.0500" version="1"/>
  <way id="10" version="1"><nd ref="1"/><nd ref="2"/><nd ref="3"/><tag k="highway" v="primary"/></way>
  <way id="11" version="1"><nd ref="3"/><nd ref="4"/><tag k="highway" v="secondary"/></way>
  <way id="12" version="1"><nd ref="4"/><nd ref="5"/><nd ref="6"/><tag k="highway" v="secondary"/></way>
  <way id="13" version="1"><nd ref="6"/><nd ref="1"/><tag k="highway" v="residential"/></way>
  <way id="14" version="1"><nd ref="2"/><nd ref="5"/><nd ref="7"/><tag k="highway" v="tertiary"/></way>
  <node id="20" lat="52.2000" lon="13.2000" version="1"/>
  <node id="21" lat="52.2000" lon="13.2500" version="1"/>
  <way id="20" version="1"><nd ref="20"/><nd ref="21"/><tag k="highway" v="residential"/></way>
  <way id="21" version="1"><nd ref="1"/><nd ref="5"/><tag k="highway" v="footway"/></way>
</osm>
"""

_HEAD = (
    "# Creator : Routino - http://www.routino.org/\n"
    "# Source : Based on OpenStreetMap data from http://www.openstreetmap.org/\n"
    "# License : http://www.openstreetmap.org/copyright\n"
    "#\n"
    "#Latitude\tLongitude\tSection \tSection \tTotal   \tTotal   \tPoint\tTurn\tBearing\tHighway\n"
    "#        \t         \tDistance\tDuration\tDistance\tDuration\tType \t    \t       \t       \n"
)
#: routino-router … --lat1=52 --lon1=13 --lat2=52.05 --lon2=13.1 --output-text --output-stdout --quiet
TWO_POINTS = _HEAD + (
    " 52.000000\t  13.000000\t 0.000 km\t 0.0 min\t  0.0 km\t   0 min\tWaypt#1\t\t +2\t(null)\n"
    " 52.000000\t  13.100000\t 6.852 km\t 4.3 min\t  6.9 km\t   4 min\tJunct\t -1\t +0\t(null)\n"
    " 52.050000\t  13.100000\t 5.566 km\t 3.8 min\t 12.4 km\t   8 min\tWaypt#2\t\t\t\n"
)
#: … over (52.1, 13.05) to (52.0, 13.1): three waypoints in one call.
THREE_POINTS = _HEAD + (
    " 52.000000\t  13.000000\t 0.000 km\t 0.0 min\t  0.0 km\t   0 min\tWaypt#1\t\t +2\t(null)\n"
    " 52.000000\t  13.050000\t 3.426 km\t 2.1 min\t  3.4 km\t   2 min\tJunct\t -1\t +0\t(null)\n"
    " 52.050000\t  13.050000\t 5.566 km\t 4.2 min\t  9.0 km\t   6 min\tJunct\t +0\t +0\t(null)\n"
    " 52.100000\t  13.050000\t 5.565 km\t 4.2 min\t 14.6 km\t  10 min\tWaypt#2\t +4\t -4\t(null)\n"
    " 52.050000\t  13.050000\t 5.565 km\t 4.2 min\t 20.1 km\t  15 min\tJunct\t -1\t +2\t(null)\n"
    " 52.000000\t  13.100000\t 8.988 km\t 6.1 min\t 29.1 km\t  21 min\tWaypt#3\t\t\t\n"
)
NO_NODE = "Error: Cannot find node close to specified point 2.\n"
NO_SUPER_ROUTE = "Error: Cannot find super-route compatible with profile.\n"


def done(stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    """What ``subprocess.run`` hands back."""
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class RouteFileMixin:
    """A folder for route-local.conf, a router and map data, and the setting that points Rentalars there."""

    def make_folder(self) -> Path:
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)  # type: ignore[attr-defined]
        self.folder = folder
        self.local_file = folder / "route-local.conf"
        override = override_settings(RENTALARS_ROUTE_LOCAL_FILE=str(self.local_file))
        override.enable()
        self.addCleanup(override.disable)  # type: ignore[attr-defined]
        return folder

    def write(self, text: str) -> None:
        self.local_file.write_text(text, encoding="utf-8")

    def write_routino(self, *, region: str = "bayern", data_date: str = "2026-10-15") -> None:
        """A file as "rentalars route install" writes it, with a router and map data that exist."""
        router = self.folder / "routino-router"
        router.write_text("#!/bin/sh\n", encoding="utf-8")
        data = self.folder / "data"
        data.mkdir(exist_ok=True)
        (data / "rentalars-nodes.mem").write_bytes(b"\0")
        self.write(
            '# Written by "rentalars route install".\n[route]\nkind = routino\n'
            f"router = {router}\ndata_dir = {data}\nprefix = rentalars\n"
            "profiles = /usr/share/routino/profiles.xml\ntranslations = /usr/share/routino/translations.xml\n"
            f"region = {region}\ndata_date = {data_date}\ninstalled_at = 2026-10-17T10:00:00+02:00\n"
        )

    def write_osrm(self, url: str = "https://osrm.example.de") -> None:
        self.write(f"[route]\nkind = osrm\nurl = {url}\ninstalled_at = 2026-10-17T10:00:00+02:00\n")


class FakeRouter:
    """Stands in for Routino's router: answers each call from a list, keeps the commands."""

    def __init__(self, *answers: subprocess.CompletedProcess[str] | BaseException) -> None:
        self.answers = list(answers)
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, BaseException):
            raise answer
        return answer


class ConfigurationTests(RouteFileMixin, RentalarsTestCase):
    """LOG-017: Rentalars reads route-local.conf at every use; nothing has to be restarted."""

    def setUp(self) -> None:
        super().setUp()
        self.make_folder()

    def test_without_the_file_there_is_no_route_service(self) -> None:
        self.assertIsNone(routing.route_service())
        self.assertFalse(routing.route_service_enabled())
        with override_settings(RENTALARS_ROUTE_LOCAL_FILE=None, RENTALARS_CONFIG_PATH=None):
            self.assertIsNone(routing.config_file())
            self.assertFalse(routing.route_service_enabled())
        with override_settings(RENTALARS_ROUTE_LOCAL_FILE=None, RENTALARS_CONFIG_PATH="/etc/rentalars/rentalars.conf"):
            self.assertEqual(routing.config_file(), Path("/etc/rentalars/route-local.conf"))

    def test_routino_installed_on_this_server(self) -> None:
        self.write_routino()
        service = routing.route_service()
        assert service is not None
        self.assertEqual((service.kind, service.prefix, service.region), ("routino", "rentalars", "bayern"))
        self.assertEqual(service.data_dir, str(self.folder / "data"))
        self.assertEqual(service.region_label, "Bayern")
        self.assertEqual(service.data_date, datetime.date(2026, 10, 15))
        # The test clock stands at 1 March 2027: 137 days – not yet worth an update.
        self.assertEqual((service.age_days, service.is_old), (137, False))
        self.assertTrue(routing.route_service_enabled())
        self.write_routino(region="germany", data_date="2026-08-01")
        service = routing.route_service()
        assert service is not None
        self.assertEqual((service.region_label, service.age_days, service.is_old), ("Deutschland", 212, True))

    def test_an_osrm_server_with_https_or_on_this_machine(self) -> None:
        self.write_osrm("https://osrm.example.de/")
        service = routing.route_service()
        assert service is not None
        self.assertEqual((service.kind, service.url, service.age_days), ("osrm", "https://osrm.example.de", None))
        self.write_osrm("http://127.0.0.1:5000")
        self.assertTrue(routing.route_service_enabled())
        for refused in ("http://osrm.example.de", "ftp://osrm.example.de", "https://osrm.example.de/?a=b", ""):
            self.write_osrm(refused)
            with self.assertRaises(routing.RouteConfigError):
                routing.route_service()
            self.assertFalse(routing.route_service_enabled())

    def test_unusable_files_are_explained(self) -> None:
        cases = {
            "[other]\nkind = routino\n": "keinen Abschnitt [route]",
            "kind = routino\n": "lässt sich nicht lesen",
            "[route]\nkind = graphhopper\n": "unbekannte Art von Routendienst: „graphhopper“",
            "[route]\nkind = routino\nrouter = /nowhere/routino-router\ndata_dir = /tmp\n": "Router /nowhere/routino",
        }
        for text, expected in cases.items():
            self.write(text)
            with self.assertRaises(routing.RouteConfigError) as caught:
                routing.route_service()
            self.assertIn(expected, str(caught.exception))
            self.assertFalse(routing.route_service_enabled())
        self.write_routino()
        (self.folder / "data" / "rentalars-nodes.mem").unlink()
        with self.assertRaises(routing.RouteConfigError) as caught:
            routing.route_service()
        self.assertIn("Kartendaten", str(caught.exception))
        self.local_file.write_bytes(b"\xff\xfe[route")
        with self.assertRaises(routing.RouteConfigError) as caught:
            routing.route_service()
        self.assertIn("lässt sich nicht lesen", str(caught.exception))
        # The planner learns only that it cannot be used; the reason is for the settings.
        with self.assertLogs("rentalars.core.routing", "WARNING"), self.assertRaises(routing.RouteError) as caught:
            routing.distance_km([(52.0, 13.0), (52.05, 13.1)])
        self.assertIn("gerade nicht nutzbar", str(caught.exception))


class RoutinoTests(RouteFileMixin, RentalarsTestCase):
    """LOG-017: the router on this server, as recorded from Routino 3.4.1."""

    def setUp(self) -> None:
        super().setUp()
        self.make_folder()
        self.write_routino()

    def test_two_points(self) -> None:
        router = FakeRouter(done(TWO_POINTS))
        with mock.patch.object(routing, "_run", router):
            self.assertEqual(routing.distance_km([(52.0, 13.0), (52.05, 13.1)]), Decimal("12.4"))
        command = router.commands[0]
        self.assertEqual(command[0], str(self.folder / "routino-router"))
        for argument in (
            f"--dir={self.folder / 'data'}",
            "--prefix=rentalars",
            "--profiles=/usr/share/routino/profiles.xml",
            "--transport=motorcar",
            "--quickest",
            "--lat1=52.000000",
            "--lon1=13.000000",
            "--lat2=52.050000",
            "--lon2=13.100000",
            "--output-text",
            "--output-stdout",
            "--quiet",
        ):
            self.assertIn(argument, command)

    def test_several_points_in_one_call_summed_and_rounded(self) -> None:
        """LOG-017: the sections 3.426 + 5.566 + 5.565 + 5.565 + 8.988 km = 29.110 km → 29.1 km."""
        router = FakeRouter(done(THREE_POINTS))
        with mock.patch.object(routing, "_run", router):
            km = routing.distance_km([(52.0, 13.0), (52.1, 13.05), (52.0, 13.1)])
        self.assertEqual(km, Decimal("29.1"))
        self.assertEqual(len(router.commands), 1)
        self.assertIn("--lat3=52.000000", router.commands[0])
        self.assertEqual(routing.parse_routino_text(THREE_POINTS), Decimal("29.110"))
        with self.assertRaises(ValueError):
            routing.parse_routino_text(_HEAD)
        self.assertEqual(routing.distance_km([(52.0, 13.0)]), Decimal("0.0"))

    def test_a_place_without_a_road_nearby_is_named(self) -> None:
        router = FakeRouter(done(stderr=NO_NODE, returncode=1))
        with mock.patch.object(routing, "_run", router), self.assertRaises(routing.RouteError) as caught:
            routing.distance_km([(52.0, 13.0), (48.0, 11.0)], labels=["Lager", "Zelt am See"])
        # The map is Bayern's: perhaps the place lies outside.
        self.assertEqual(
            str(caught.exception), "In der Karte des Routendienstes (Bayern) gibt es keine Straße bei „Zelt am See“."
        )

    def test_the_leg_without_a_route_is_named(self) -> None:
        """LOG-017: Routino does not say which leg failed; the legs are asked one by one."""
        router = FakeRouter(
            done(stderr=NO_SUPER_ROUTE, returncode=1),
            done(TWO_POINTS),
            done(stderr=NO_SUPER_ROUTE, returncode=1),
        )
        with mock.patch.object(routing, "_run", router), self.assertRaises(routing.RouteError) as caught:
            routing.distance_km([(52.0, 13.0), (52.05, 13.1), (52.2, 13.2)], labels=["Lager", "Halle", "Insel"])
        self.assertEqual(str(caught.exception), "Zwischen „Halle“ und „Insel“ wurde keine Route gefunden.")
        self.assertEqual(len(router.commands), 3)
        # Two points: no second question.
        router = FakeRouter(done(stderr=NO_SUPER_ROUTE, returncode=1))
        with mock.patch.object(routing, "_run", router), self.assertRaises(routing.RouteError) as caught:
            routing.distance_km([(52.0, 13.0), (52.2, 13.2)])
        self.assertEqual(str(caught.exception), "Zwischen „Punkt 1“ und „Punkt 2“ wurde keine Route gefunden.")
        self.assertEqual(len(router.commands), 1)

    def test_a_router_that_does_not_answer(self) -> None:
        expected = "Der Routendienst hat nicht geantwortet."
        for answer in (
            subprocess.TimeoutExpired(cmd="routino-router", timeout=60),
            FileNotFoundError("routino-router"),
            done(
                stderr="Cannot open file 'x/rentalars-nodes.mem' for reading [No such file or directory].\n",
                returncode=1,
            ),
            done("garbage\n"),
        ):
            with (
                mock.patch.object(routing, "_run", FakeRouter(answer)),
                self.assertLogs("rentalars.core.routing", "WARNING"),
                self.assertRaises(routing.RouteError) as caught,
            ):
                routing.distance_km([(52.0, 13.0), (52.05, 13.1)])
            self.assertIn(expected, str(caught.exception))

    def test_without_a_route_service_the_kilometres_are_typed_in(self) -> None:
        self.local_file.unlink()
        with self.assertRaises(routing.RouteError) as caught:
            routing.distance_km([(52.0, 13.0), (52.05, 13.1)])
        self.assertEqual(
            str(caught.exception), "Es ist kein Routendienst eingerichtet. Bitte die Kilometer von Hand eintragen."
        )


class FakeOsrm:
    """Stands in for ``routing._send``: answers like an OSRM server, keeps the addresses asked."""

    def __init__(self, status: int, answer: Any) -> None:
        self.status = status
        self.body = answer if isinstance(answer, bytes) else json.dumps(answer).encode("utf-8")
        self.urls: list[str] = []

    def __call__(self, url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        self.urls.append(url)
        return self.status, self.body


class OsrmTests(RouteFileMixin, RentalarsTestCase):
    """LOG-017, NFA-050: an OSRM-compatible server the operator runs himself or one hosted in Germany."""

    def setUp(self) -> None:
        super().setUp()
        self.make_folder()
        self.write_osrm()

    def test_the_distance_of_the_route(self) -> None:
        server = FakeOsrm(200, {"code": "Ok", "routes": [{"distance": 118734.5, "duration": 4000.1}]})
        with mock.patch.object(routing, "_send", server):
            km = routing.distance_km([(50.1109, 8.6821), (49.9, 9.1), (49.7913, 9.9534)])
        self.assertEqual(km, Decimal("118.7"))
        self.assertEqual(
            server.urls,
            [
                "https://osrm.example.de/route/v1/driving/8.682100,50.110900;9.100000,49.900000;9.953400,49.791300"
                "?overview=false&steps=false"
            ],
        )

    def test_no_road_and_no_route(self) -> None:
        no_segment = FakeOsrm(
            400, {"code": "NoSegment", "message": "Could not find a matching segment for coordinate 1"}
        )
        with mock.patch.object(routing, "_send", no_segment), self.assertRaises(routing.RouteError) as caught:
            routing.distance_km([(50.1, 8.6), (0.0, 0.0)], labels=["Lager", "Nirgendwo"])
        self.assertEqual(str(caught.exception), "In der Karte des Routendienstes gibt es keine Straße bei „Nirgendwo“.")
        no_route = FakeOsrm(400, {"code": "NoRoute", "message": "Impossible route between points"})
        with mock.patch.object(routing, "_send", no_route), self.assertRaises(routing.RouteError) as caught:
            routing.distance_km([(50.1, 8.6), (54.1, 7.9)], labels=["Lager", "Helgoland"])
        self.assertEqual(str(caught.exception), "Zwischen „Lager“ und „Helgoland“ wurde keine Route gefunden.")

    def test_a_server_that_does_not_answer_properly(self) -> None:
        for status, answer in ((500, b"<html>Bad gateway</html>"), (200, {"code": "InvalidUrl"}), (200, [])):
            with (
                mock.patch.object(routing, "_send", FakeOsrm(status, answer)),
                self.assertLogs("rentalars.core.routing", "WARNING"),
                self.assertRaises(routing.RouteError) as caught,
            ):
                routing.distance_km([(50.1, 8.6), (49.8, 9.9)])
            self.assertIn("Der Routendienst hat nicht geantwortet.", str(caught.exception))

    def test_the_request_to_a_server_on_this_machine(self) -> None:
        """LOG-017: a real request – without a proxy, with the User-Agent of the installation, errors read too."""
        answers = [(200, {"code": "Ok", "routes": [{"distance": 12418.0}]}), (400, {"code": "NoRoute"})]
        seen: list[tuple[str, str]] = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                seen.append((self.path, self.headers.get("User-Agent", "")))
                status, answer = answers.pop(0)
                body = json.dumps(answer).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: Any) -> None:
                return None

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.write_osrm(f"http://127.0.0.1:{server.server_port}")
        with mock.patch.dict(
            os.environ, {"http_proxy": "http://proxy.invalid:3128", "HTTP_PROXY": "http://proxy.invalid:3128"}
        ):
            self.assertEqual(routing.distance_km([(52.0, 13.0), (52.05, 13.1)]), Decimal("12.4"))
            with self.assertRaises(routing.RouteError) as caught:
                routing.distance_km([(52.0, 13.0), (52.2, 13.2)])
        self.assertIn("keine Route gefunden", str(caught.exception))
        self.assertTrue(seen[0][0].startswith("/route/v1/driving/13.000000,52.000000;13.100000,52.050000?"))
        self.assertTrue(seen[0][1].startswith("Rentalars/"))
        # Nobody listens: did not answer.
        server.shutdown()
        server.server_close()
        with self.assertLogs("rentalars.core.routing", "WARNING"), self.assertRaises(routing.RouteError) as caught:
            routing.distance_km([(52.0, 13.0), (52.05, 13.1)])
        self.assertIn("nicht geantwortet", str(caught.exception))


def company_with_warehouse(warehouse: str = WAREHOUSE) -> None:
    profile = CompanyProfile.load()
    profile.name = "Bühnentechnik Muster"
    profile.street, profile.postal_code, profile.city = "Hafen 1", "12345", "Musterstadt"
    profile.warehouse_address = warehouse
    profile.save()


class TripTests(RouteFileMixin, RentalarsTestCase):
    """LOG-017: the kilometres of a trip – warehouse, stops, destination – located like the maps (UIX-034)."""

    def setUp(self) -> None:
        super().setUp()
        self.make_folder()
        self.write_routino()
        company_with_warehouse()
        self.project = make_project("Stadtfest")
        self.phase = course.add_phase(
            self.project, kind=PhaseKind.SETUP, start=at(10, 8), end=at(10, 16), location=MARKET
        )

    def trip(self, key: str = "") -> Any:
        key = key or f"to_venue-{self.phase.pk}"
        return next(trip for trip in trips_of(self.project) if trip.key == key)

    def test_the_trip_to_the_venue(self) -> None:
        router = FakeRouter(done(TWO_POINTS))
        places = {WAREHOUSE: ("52.000000", "13.000000"), MARKET: ("52.050000", "13.100000")}
        with mock.patch.object(routing, "_run", router), FakeGeocoder(places) as geocoder:
            self.assertEqual(routing.trip_distance(self.trip()), Decimal("12.4"))
        self.assertEqual(geocoder.questions, [WAREHOUSE, MARKET])
        self.assertIn("--lat2=52.050000", router.commands[0])
        # Kept for the maps and the next trip: the way back asks nobody.
        self.assertEqual(AddressPosition.objects.filter(source=PositionSource.FOUND).count(), 2)
        router = FakeRouter(done(TWO_POINTS))
        with mock.patch.object(routing, "_run", router), FakeGeocoder(places) as geocoder:
            routing.trip_distance(self.trip(f"from_venue-{self.phase.pk}"))
        self.assertEqual(geocoder.questions, [])
        self.assertIn("--lat1=52.050000", router.commands[0])

    def test_a_position_set_by_hand_counts(self) -> None:
        from rentalars.core.maps import address_key

        for address, lat, lon in ((WAREHOUSE, "52.0", "13.0"), (MARKET, "52.05", "13.1")):
            AddressPosition.objects.create(
                key=address_key(address), address=address, latitude=lat, longitude=lon, source=PositionSource.MANUAL
            )
        with mock.patch.object(routing, "_run", FakeRouter(done(TWO_POINTS))), FakeGeocoder() as geocoder:
            self.assertEqual(routing.trip_distance(self.trip()), Decimal("12.4"))
        self.assertEqual(geocoder.questions, [])

    def test_places_without_address_or_position(self) -> None:
        with FakeGeocoder({WAREHOUSE: ("52.0", "13.0")}), self.assertRaises(routing.RouteError) as caught:
            routing.trip_distance(self.trip())
        self.assertEqual(
            str(caught.exception),
            "Die Adresse von „Marktplatz 1, 12345 Musterstadt“ wurde nicht gefunden. "
            "Bitte ihre Position auf der Karte des Projekts setzen.",
        )
        company_with_warehouse("")
        CompanyProfile.objects.update(street="", postal_code="", city="")
        with FakeGeocoder() as geocoder, self.assertRaises(routing.RouteError) as caught:
            routing.trip_distance(self.trip())
        self.assertEqual(str(caught.exception), "„Lager“ hat noch keine Adresse.")
        self.assertEqual(geocoder.questions, [])

    def test_the_geocoder_does_not_answer(self) -> None:
        with FakeGeocoder(status=429), self.assertRaises(routing.RouteError) as caught:
            routing.trip_distance(self.trip())
        self.assertIn("Kartensuche", str(caught.exception))
        self.assertFalse(AddressPosition.objects.exists())

    def test_without_a_route_service_nobody_is_asked(self) -> None:
        self.local_file.unlink()
        with FakeGeocoder() as geocoder, self.assertRaises(routing.RouteError):
            routing.trip_distance(self.trip())
        self.assertEqual(geocoder.questions, [])


class PageTests(RouteFileMixin, UiTestCase):
    """LOG-017: "Geplante km aus der Route vorschlagen" in the dialog, and the route service in the settings."""

    def setUp(self) -> None:
        super().setUp()
        self.make_folder()
        company_with_warehouse()
        self.project = make_project("Stadtfest")
        self.phase = course.add_phase(
            self.project, kind=PhaseKind.SETUP, start=at(10, 8), end=at(10, 16), location=MARKET
        )
        self.key = f"to_venue-{self.phase.pk}"
        self.url = reverse("projects:trip_route", args=[self.project.pk, self.key])

    def test_without_a_route_service_the_answer_says_so(self) -> None:
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"error": "Es ist kein Routendienst eingerichtet. Bitte die Kilometer von Hand eintragen."}
        )
        dialog = self.htmx("get", reverse("projects:trip_vehicle_add", args=[self.project.pk]) + f"?trip={self.key}")
        self.assertNotIn("data-route-suggest", self.assert_ok(dialog))

    def test_with_a_route_service_the_kilometres(self) -> None:
        self.write_routino()
        places = {WAREHOUSE: ("52.0", "13.0"), MARKET: ("52.05", "13.1")}
        with mock.patch.object(routing, "_run", FakeRouter(done(TWO_POINTS))), FakeGeocoder(places):
            response = self.client.get(self.url)
        self.assertEqual(response.json(), {"km": "12.4"})
        missing = self.client.get(reverse("projects:trip_route", args=[self.project.pk, "to_venue-999999"]))
        self.assertEqual(missing.status_code, 404)
        self.assertIn("error", missing.json())
        # The dialog offers the button; the page script fills "planned_km" (static/js/app.js, LOG-017).
        dialog = self.htmx("get", reverse("projects:trip_vehicle_add", args=[self.project.pk]) + f"?trip={self.key}")
        text = self.assert_ok(dialog)
        self.assertIn(f'data-route-suggest="{self.url}"', text)
        self.assertIn('data-route-target="planned_km"', text)
        self.assertIn('name="planned_km"', text)
        page = self.assert_ok(self.client.get(reverse("core:company_settings")))
        self.assertIn('data-text-route-busy="Routendienst wird gefragt …"', page)
        self.assertIn('data-text-route-done="{km} km laut Route – ein Vorschlag, änderbar."', page)

    def test_only_who_plans_the_logistics_asks(self) -> None:
        self.write_routino()
        # Reads the project, but neither edits it nor maintains the fleet (LOG-001).
        reader = self.browser_for("rita", "Nur-Lesen")
        with FakeGeocoder() as geocoder:
            self.assertEqual(reader.get(self.url).status_code, 403)
        self.assertEqual(geocoder.questions, [])
        # The crew does not even see the project.
        self.assertEqual(self.browser_for("chris", "Crew").get(self.url).status_code, 404)

    def test_the_settings_show_the_route_service(self) -> None:
        url = reverse("core:company_settings")
        text = self.assert_ok(self.client.get(url))
        self.assertIn('<h2 id="route-service-title">Routendienst</h2>', text)
        self.assertIn("nicht eingerichtet", text)
        self.assertIn("Ohne Routendienst werden die Kilometer von Hand eingetragen.", text)
        self.assertIn("sudo rentalars route install --region BUNDESLAND", text)
        self.assertIn("nordrhein-westfalen", text)
        self.write_routino(data_date="2026-08-01")
        text = self.assert_ok(self.client.get(url))
        self.assertIn('<span class="badge green">eingerichtet</span>', text)
        self.assertIn("Routino auf diesem Server", text)
        self.assertIn("Bayern", text)
        self.assertIn("Kartenstand", text)
        self.assertIn("01.08.2026", text)
        self.assertIn("212 Tage alt", text)
        self.assertIn("sudo rentalars route update", text)
        self.write_osrm("https://osrm.example.de")
        text = self.assert_ok(self.client.get(url))
        self.assertIn("OSRM-Routenserver", text)
        self.assertIn("https://osrm.example.de", text)
        self.write("[route]\nkind = graphhopper\n")
        text = self.assert_ok(self.client.get(url))
        self.assertIn("unbekannte Art von Routendienst", text)
        # Who may not see the settings sees nothing of it.
        self.assertEqual(self.browser_for("paula", "Projektleitung").get(url).status_code, 403)


def routino_installed() -> None:
    if not (shutil.which("routino-router") and shutil.which("planetsplitter")):
        raise SkipTest("Routino is not installed")


class RouteApiTests(RouteFileMixin, ApiTestCase):
    """LOG-015, LOG-017: ``GET /projects/{id}/trips/{key}/route`` – the same suggestion for a program (API-014)."""

    def setUp(self) -> None:
        super().setUp()
        self.make_folder()
        company_with_warehouse()
        self.project = make_project("Stadtfest")
        phase = course.add_phase(self.project, kind=PhaseKind.SETUP, start=at(10, 8), end=at(10, 16), location=MARKET)
        self.url = f"{API}/projects/{self.project.pk}/trips/to_venue-{phase.pk}/route"

    def test_the_kilometres_of_a_trip(self) -> None:
        self.write_routino()
        places = {WAREHOUSE: ("52.0", "13.0"), MARKET: ("52.05", "13.1")}
        with mock.patch.object(routing, "_run", FakeRouter(done(TWO_POINTS))), FakeGeocoder(places):
            response = self.admin.get(self.url)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(Decimal(str(response.json()["km"])), Decimal("12.4"))


class RealRoutinoTests(RouteFileMixin, RentalarsTestCase):
    """LOG-017: Routino itself, on the small map – where it is installed."""

    def test_the_real_router(self) -> None:
        routino_installed()
        folder = self.make_folder()
        (folder / "grid.osm").write_text(GRID_OSM, encoding="utf-8")
        data = folder / "data"
        data.mkdir()
        tagging = "/usr/share/routino/tagging-drive.xml"
        subprocess.run(
            ["planetsplitter", f"--dir={data}", "--prefix=rentalars", f"--tagging={tagging}", str(folder / "grid.osm")],
            capture_output=True,
            check=True,
            timeout=60,
        )
        self.write(
            f"[route]\nkind = routino\nrouter = {shutil.which('routino-router')}\ndata_dir = {data}\n"
            "prefix = rentalars\nregion =\n"
        )
        self.assertEqual(routing.distance_km([(52.0, 13.0), (52.05, 13.1)]), Decimal("12.4"))
        self.assertEqual(routing.distance_km([(52.0, 13.0), (52.1, 13.05), (52.0, 13.1)]), Decimal("29.1"))
        with self.assertRaises(routing.RouteError) as caught:
            routing.distance_km([(52.0, 13.0), (48.0, 11.0)], labels=["Lager", "München"])
        self.assertIn("keine Straße bei „München“", str(caught.exception))
        with self.assertRaises(routing.RouteError) as caught:
            routing.distance_km([(52.0, 13.0), (52.2, 13.2)], labels=["Lager", "Insel"])
        self.assertIn("Zwischen „Lager“ und „Insel“ wurde keine Route gefunden.", str(caught.exception))


class OperatorCommandTests(RentalarsTestCase):
    """LOG-017: ``rentalars route install|update|register|remove|status`` (deploy/route.sh)."""

    def run_command(
        self, *arguments: str, memory_kb: int = 16_000_000, **environment: str
    ) -> subprocess.CompletedProcess[str]:
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        (folder / "mem").write_text(f"MemTotal:       {memory_kb} kB\n")
        (folder / "os").write_text('PRETTY_NAME="Ubuntu 24.04.3 LTS"\nID=ubuntu\nVERSION_ID="24.04"\n')
        env = {
            **os.environ,
            "LC_ALL": "C.UTF-8",
            "RENTALARS_LANG": "de",
            "RENTALARS_ROUTE_OS_RELEASE": str(folder / "os"),
            "RENTALARS_ROUTE_DEVICE_MODEL": str(folder / "none"),
            "RENTALARS_ROUTE_MEMINFO": str(folder / "mem"),
            "RENTALARS_ROUTE_ARCH": "amd64",
            **environment,
        }
        return subprocess.run(
            ["bash", str(ROOT / "deploy" / "route.sh"), *arguments],
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
            check=False,
        )

    def test_the_plan_of_a_bundesland(self) -> None:
        result = self.run_command("install", "--region", "bayern", "--dry-run", memory_kb=3_000_000)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("https://download.geofabrik.de/europe/germany/bayern-latest.osm.pbf (etwa 800 MB)", result.stdout)
        self.assertIn("bayern-latest.osm.pbf.md5", result.stdout)
        self.assertIn("planetsplitter-slim --sort-ram-size=256", result.stdout)
        self.assertIn("/opt/rentalars/routes", result.stdout)
        self.assertIn("route-local.conf", result.stdout)
        self.assertIn("Probelauf: nichts wurde verändert.", result.stdout)

    def test_all_of_germany_needs_memory_or_asking_for_it(self) -> None:
        small = self.run_command("install", "--dry-run", memory_kb=3_000_000)
        self.assertEqual(small.returncode, 1)
        self.assertIn("Bitte ein Bundesland wählen, z. B. --region bayern", small.stderr)
        asked = self.run_command("install", "--region", "germany", "--dry-run", memory_kb=3_000_000)
        self.assertEqual(asked.returncode, 0, asked.stderr)
        self.assertIn("Sparmodus", asked.stderr)
        large = self.run_command("install", "--dry-run")
        self.assertEqual(large.returncode, 0, large.stderr)
        self.assertIn("https://download.geofabrik.de/europe/germany-latest.osm.pbf (etwa 4500 MB)", large.stdout)
        self.assertIn("planetsplitter --sort-ram-size=2048", large.stdout)
        self.assertIn("23000 MB frei nötig", large.stdout)
        unknown = self.run_command("install", "--region", "atlantis", "--dry-run")
        self.assertIn("Unbekannte Region: atlantis", unknown.stderr)

    def test_register_takes_https_or_this_machine_only(self) -> None:
        for url, code in (("https://osrm.example.de", 0), ("http://127.0.0.1:5000/", 0), ("http://osrm.example.de", 1)):
            result = self.run_command("register", "--url", url, "--dry-run")
            self.assertEqual(result.returncode, code, url)
        self.assertIn("NFA-050", self.run_command("register", "--url", "https://osrm.example.de", "--dry-run").stdout)

    def test_install_status_and_remove_in_a_test_folder(self) -> None:
        """LOG-017: from a map file to route-local.conf – which Rentalars reads at once – and back."""
        routino_installed()
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        (folder / "etc").mkdir()
        (folder / "etc" / "rentalars.conf").write_text("[rentalars]\n")
        (folder / "grid.osm").write_text(GRID_OSM, encoding="utf-8")
        environment = {
            "RENTALARS_CONFIG": str(folder / "etc" / "rentalars.conf"),
            "RENTALARS_ROUTE_TEST_ROOT": str(folder),
        }
        result = self.run_command("install", "--file", str(folder / "grid.osm"), **environment)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Probefahrt", result.stdout)
        self.assertIn("Fertig.", result.stdout)
        local_file = folder / "etc" / "route-local.conf"
        with override_settings(RENTALARS_ROUTE_LOCAL_FILE=str(local_file)):
            service = routing.route_service()
            assert service is not None
            self.assertEqual(service.kind, "routino")
            self.assertTrue(service.data_dir.startswith(str(folder / "opt" / "rentalars" / "routes" / "data-")))
            self.assertEqual(routing.distance_km([(52.0, 13.0), (52.05, 13.1)]), Decimal("12.4"))
        self.assertTrue((folder / "grid.osm").exists())  # a file of the operator's stays
        status = self.run_command("status", **environment)
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("Routino auf diesem Server", status.stdout)
        self.assertIn("0 Tage alt", status.stdout)
        update = self.run_command("update", **environment)
        self.assertIn("aus einer Datei eingerichtet", update.stderr)
        removed = self.run_command("remove", **environment)
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertFalse(local_file.exists())
        self.assertFalse((folder / "opt" / "rentalars" / "routes").exists())
        self.assertIn("nicht eingerichtet", self.run_command("status", **environment).stdout)

    def test_the_scripts_pass_shellcheck(self) -> None:
        if shutil.which("shellcheck") is None:
            raise SkipTest("shellcheck is not installed")
        result = subprocess.run(
            ["shellcheck", "-x", "deploy/route.sh", "deploy/rentalars"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env={**os.environ, "LANG": "C.UTF-8"},
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        command = (ROOT / "deploy" / "rentalars").read_text(encoding="utf-8")
        self.assertIn('route)         exec bash "${APP_DIR}/deploy/route.sh" "$@"', command)
