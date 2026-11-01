# SPDX-License-Identifier: GPL-3.0-or-later
"""Maps: route links to Google Maps (UIX-033), a zoomable OpenStreetMap map after a click (UIX-034) and the
trips of a project with their route links (PRJ-097).

Requirement: route links to Google Maps, a zoomable map, automatic routes; decided: maps from OpenStreetMap, route links to
Google Maps. No test reaches the internet: the geocoder is ``tests.geocoder_fake``.
"""

from __future__ import annotations

import datetime
import socket
import tempfile
import urllib.error
from decimal import Decimal as D  # noqa: N817
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.test import override_settings

from rentalars.accounts.rights import Rights, rights_of
from rentalars.config import ConfigurationError, MapsConfig, load_config
from rentalars.core import geocoding, maps
from rentalars.core.models import AddressPosition, AuditLogEntry, CompanyProfile, PositionSource
from rentalars.customers.models import AddressKind, Customer, CustomerAddress, CustomerKind, Venue
from rentalars.customers.services import anonymise_customer, save_customer
from rentalars.masterdata.models import Supplier
from rentalars.projects import services
from rentalars.projects.models import LineVariant, PhaseKind, ProjectPhase
from rentalars.projects.trips import TripKind, places_of, trip_document, trips_of
from tests.geocoder_fake import FakeGeocoder
from tests.helpers import ALL_RIGHTS, RentalarsTestCase, add_line, at, make_project, make_stock, make_user

WAREHOUSE = "Industriestraße 5, 12345 Musterstadt"
HALL = "Hallenweg 3, 12345 Musterstadt"
NORD = "Verleihstraße 9, 54321 Nordstadt"


def request_of(user: object, rights: Rights | None = None) -> SimpleNamespace:
    """A request as ``map_for`` asks it: the user and the rights."""
    return SimpleNamespace(user=user, _rentalars_rights=rights if rights is not None else rights_of(user))


def company(
    street: str = "Hafen 1", postal_code: str = "12345", city: str = "Musterstadt", warehouse: str = ""
) -> None:
    profile = CompanyProfile.load()
    profile.name = "Bühnentechnik Muster"
    profile.street, profile.postal_code, profile.city = street, postal_code, city
    profile.warehouse_address = warehouse
    profile.save()


class ConfigurationTests(RentalarsTestCase):
    """UIX-034: tile server, geocoder and attribution are settings of the configuration file."""

    def write(self, text: str) -> Path:
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: [path.unlink() for path in folder.iterdir()] and folder.rmdir())
        path = folder / "rentalars.conf"
        path.write_text("[rentalars]\nenvironment = development\n" + text, encoding="utf-8")
        return path

    def test_without_a_section_the_servers_of_openstreetmap_are_used(self) -> None:
        """UIX-034: OpenStreetMap by default."""
        config = load_config(self.write("")).maps
        self.assertEqual(config.tile_url, "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
        self.assertEqual(config.geocoder_url, "https://nominatim.openstreetmap.org/search")
        self.assertEqual(config.attribution_url, "https://www.openstreetmap.org/copyright")
        self.assertTrue(config.enabled)

    def test_own_servers_and_switching_maps_off(self) -> None:
        """UIX-034: an own server can be used; an empty tile_url switches maps off."""
        config = load_config(
            self.write(
                "[maps]\ntile_url = https://tiles.example.de/{z}/{x}/{y}.png\n"
                "geocoder_url = https://geo.example.de/search\nattribution = © Beispiel\nmax_zoom = 30\n"
            )
        ).maps
        self.assertEqual(config.tile_url, "https://tiles.example.de/{z}/{x}/{y}.png")
        self.assertEqual(config.geocoder_url, "https://geo.example.de/search")
        self.assertEqual(config.attribution, "© Beispiel")
        self.assertEqual(config.max_zoom, 22)
        self.assertFalse(load_config(self.write("[maps]\ntile_url =\n")).maps.enabled)

    def test_an_address_without_scheme_is_refused(self) -> None:
        """UIX-034: a typo must not lead to requests that go nowhere."""
        with self.assertRaises(ConfigurationError):
            load_config(self.write("[maps]\ngeocoder_url = nominatim.example.de\n"))
        with self.assertRaises(ConfigurationError):
            load_config(self.write("[maps]\nmax_zoom = viel\n"))


class RouteLinkTests(RentalarsTestCase):
    """UIX-033: the link into the route planning of Google Maps."""

    def test_destination_only_starts_where_the_viewer_is(self) -> None:
        """UIX-033: without origin Google Maps starts at the viewer's position."""
        url = maps.route_url("Hauptstraße 1, 12345 Musterstadt")
        self.assertTrue(url.startswith("https://www.google.com/maps/dir/?api=1&destination="))
        self.assertEqual(
            parse_qs(urlsplit(url).query), {"api": ["1"], "destination": ["Hauptstraße 1, 12345 Musterstadt"]}
        )
        self.assertNotIn("+", url)  # spaces as %20

    def test_waypoints(self) -> None:
        """PRJ-097: stops in order, destination; at most nine stops. UIX-033: never a start."""
        url = maps.route_url(WAREHOUSE, waypoints=[NORD, "", HALL])
        query = parse_qs(urlsplit(url).query)
        self.assertNotIn("origin", query)
        self.assertEqual(query["destination"], [WAREHOUSE])
        self.assertEqual(query["waypoints"], [f"{NORD}|{HALL}"])
        many = maps.route_url("Ziel", waypoints=[f"Stopp {number}" for number in range(12)])
        self.assertEqual(len(parse_qs(urlsplit(many).query)["waypoints"][0].split("|")), 9)

    def test_no_destination_no_link(self) -> None:
        """UIX-033: an empty address has no link."""
        self.assertEqual(maps.route_url("  "), "")

    def test_one_line_and_key(self) -> None:
        """UIX-034: one key per address, whatever the spaces and the case."""
        self.assertEqual(maps.one_line("Hauptstraße  1", " 12345 Musterstadt", ""), "Hauptstraße 1, 12345 Musterstadt")
        self.assertEqual(
            maps.address_key("Hauptstraße 1,  12345 MUSTERSTADT"), maps.address_key("hauptstraße 1, 12345 musterstadt")
        )
        self.assertNotEqual(maps.address_key("Hauptstraße 1"), maps.address_key("Hauptstraße 2"))

    def test_warehouse_is_the_company_address_unless_set(self) -> None:
        """PRJ-097: the warehouse address is a setting; empty – the company's address."""
        company()
        self.assertEqual(maps.warehouse_address(), "Hafen 1, 12345 Musterstadt, Deutschland")
        company(warehouse=f"  {WAREHOUSE} ")
        self.assertEqual(maps.warehouse_address(), WAREHOUSE)

    def test_the_country_alone_is_no_address(self) -> None:
        """PRJ-097: a company without street and city has no address to start from – not "Deutschland"."""
        profile = CompanyProfile.load()
        profile.street, profile.postal_code, profile.city, profile.country = "", "", "", "Deutschland"
        profile.warehouse_address = ""
        profile.save()
        self.assertEqual(maps.warehouse_address(), "")

    def test_supplier_address(self) -> None:
        """UIX-033: a supplier has an address of its own."""
        supplier = Supplier.objects.create(
            name="Verleih Nord", street="Verleihstraße 9", postal_code="54321", city="Nordstadt"
        )
        self.assertEqual(supplier.address_one_line, NORD)
        self.assertEqual(Supplier.objects.create(name="Ohne").address_one_line, "")

    def test_tile_origin_for_the_content_security_policy(self) -> None:
        """UIX-034: the image source of a page with a map – with a wildcard for {s}."""
        self.assertEqual(maps.tile_origin(), "https://tile.openstreetmap.org")
        with override_settings(RENTALARS_MAPS=MapsConfig(tile_url="https://{s}.tiles.example.de:8443/{z}/{x}/{y}.png")):
            self.assertEqual(maps.tile_origin(), "https://*.tiles.example.de:8443")


class GeocoderTests(RentalarsTestCase):
    """UIX-034: the server asks Nominatim – mocked here."""

    def test_a_hit(self) -> None:
        """UIX-034: the first hit with its position; the request names Rentalars."""
        with FakeGeocoder({HALL: ("52.5200001", "13.4049999")}) as geocoder:
            found = geocoding.look_up(HALL)
        self.assertEqual((found.latitude, found.longitude), (D("52.520000"), D("13.405000")))
        self.assertIn("Rentalars/", geocoder.headers["User-Agent"])
        query = parse_qs(urlsplit(geocoder.urls[0]).query)
        self.assertEqual(query["format"], ["jsonv2"])
        self.assertEqual(query["limit"], ["1"])

    def test_nothing_found(self) -> None:
        """UIX-034: an empty answer is "not found", not an error."""
        with FakeGeocoder():
            self.assertIsNone(geocoding.look_up("Nirgendwo 1"))

    def test_errors(self) -> None:
        """UIX-034: busy, broken or unreachable – an error with a German text, nothing kept."""
        cases = [
            FakeGeocoder(status=429),
            FakeGeocoder(status=503),
            FakeGeocoder(body=b"<html>"),
            FakeGeocoder(body=b'[{"lat": "x", "lon": "1"}]'),
            FakeGeocoder(body=b'[{"lat": "91", "lon": "1"}]'),
        ]
        with self.assertLogs("rentalars.core.geocoding", "WARNING"):  # an error status is noted in the log
            for fake in cases:
                with self.subTest(status=fake.status, body=fake.body), fake, self.assertRaises(geocoding.GeocoderError):
                    geocoding.look_up(HALL)

    def test_network_problems_are_named(self) -> None:
        """UIX-034: no answer at all – the real ``_send`` turns it into a readable error."""
        timeout = urllib.error.URLError(TimeoutError())
        with (
            mock.patch.object(geocoding._OPENER, "open", side_effect=timeout),
            self.assertRaisesRegex(geocoding.GeocoderError, "10"),
        ):
            geocoding._send("https://geo.example/search?q=x", {})
        unknown = urllib.error.URLError(socket.gaierror())
        with (
            mock.patch.object(geocoding._OPENER, "open", side_effect=unknown),
            self.assertRaises(geocoding.GeocoderError),
        ):
            geocoding._send("https://geo.example/search?q=x", {})

    def test_switched_off(self) -> None:
        """UIX-034: without geocoder_url nothing is asked."""
        with (
            override_settings(RENTALARS_MAPS=MapsConfig(geocoder_url="")),
            FakeGeocoder() as geocoder,
            self.assertRaises(geocoding.GeocoderError),
        ):
            geocoding.look_up(HALL)
        self.assertEqual(geocoder.questions, [])

    def test_one_request_per_second_across_processes(self) -> None:
        """UIX-034: the usage policy of Nominatim – the time of the last request is kept in a locked file."""
        folder = Path(tempfile.mkdtemp())
        waits: list[float] = []
        with (
            override_settings(DATA_DIR=folder),
            mock.patch.object(geocoding, "_sleep", waits.append),
            mock.patch.object(geocoding, "_last_request", 0.0),
        ):
            geocoding._wait_turn()
            geocoding._wait_turn()
        self.assertEqual(len(waits), 1)
        self.assertTrue(0 < waits[0] <= 1.0)
        self.assertTrue((folder / "geocoder.lock").read_text())
        (folder / "geocoder.lock").unlink()
        folder.rmdir()


class LocateTests(RentalarsTestCase):
    """UIX-034: positions are asked for once per address and kept."""

    def setUp(self) -> None:
        super().setUp()
        self.admin = make_user("admin", superuser=True)
        self.venue = Venue.objects.create(
            name="Stadthalle", street="Hallenweg 3", postal_code="12345", city="Musterstadt"
        )

    def page(self, target: str = "venue", pk: int | None = None, user: object = None) -> maps.MapPage:
        return maps.map_for(request_of(user or self.admin), target, pk if pk is not None else self.venue.pk)

    def test_asked_once_and_kept(self) -> None:
        """UIX-034: the second opening asks nobody."""
        with FakeGeocoder({HALL: ("52.1", "13.2")}) as geocoder:
            page = self.page()
            maps.locate(page)
            maps.locate(self.page())
        self.assertEqual(geocoder.questions, [HALL])
        place = page.places[0]
        self.assertTrue(place.is_located)
        self.assertEqual(place.source, PositionSource.FOUND)
        self.assertEqual(AddressPosition.objects.get().found_name, f"{HALL} (gefunden)")

    def test_not_found_is_kept_too(self) -> None:
        """UIX-034: an address the geocoder does not know is not asked again by itself."""
        with FakeGeocoder() as geocoder:
            maps.locate(self.page())
            page = self.page()
            maps.locate(page)
        self.assertEqual(len(geocoder.questions), 1)
        self.assertEqual(page.places[0].source, PositionSource.NOT_FOUND)
        self.assertFalse(page.places[0].is_located)

    def test_a_failure_keeps_nothing(self) -> None:
        """UIX-034: should the geocoder not answer, the page says so and the next opening asks again."""
        with FakeGeocoder(error=geocoding.GeocoderError("Die Kartensuche ist nicht erreichbar.")):
            page = self.page()
            maps.locate(page)
        self.assertEqual(page.problems, ["Die Kartensuche ist nicht erreichbar."])
        self.assertFalse(AddressPosition.objects.exists())

    def test_at_most_five_questions_per_opening(self) -> None:
        """UIX-034: one per second – a map with many new addresses fills up over two openings."""
        customer = save_customer(Customer(name="Viele Adressen", street="Weg 0", city="Ort"))
        for number in range(1, 7):
            CustomerAddress.objects.create(customer=customer, street=f"Weg {number}", city="Ort")
        with FakeGeocoder() as geocoder:
            page = self.page("customer", customer.pk)
            maps.locate(page)
            self.assertEqual(len(geocoder.questions), 5)
            self.assertEqual(len(page.problems), 1)
            maps.locate(self.page("customer", customer.pk))
        self.assertEqual(len(geocoder.questions), 7)

    def test_the_same_address_is_one_position(self) -> None:
        """UIX-034: a venue and a customer at the same address share one position."""
        customer = save_customer(
            Customer(name="Halle e. V.", street="Hallenweg 3", postal_code="12345", city="Musterstadt")
        )
        with FakeGeocoder({HALL: ("52.1", "13.2")}) as geocoder:
            maps.locate(self.page())
            page = self.page("customer", customer.pk)
            maps.locate(page)
        self.assertEqual(len(geocoder.questions), 1)
        self.assertTrue(page.places[0].is_located)

    def test_without_geocoder_the_position_is_set_by_hand(self) -> None:
        """UIX-034: geocoder_url empty – nothing is asked, the page says what to do."""
        with override_settings(RENTALARS_MAPS=MapsConfig(geocoder_url="")), FakeGeocoder() as geocoder:
            page = self.page()
            maps.locate(page)
        self.assertEqual(geocoder.questions, [])
        self.assertIn("von Hand", page.problems[0])

    def test_map_data_for_the_page_script(self) -> None:
        """UIX-034: tiles, attribution "© OpenStreetMap-Mitwirkende", Leaflet from this server, numbered places."""
        with FakeGeocoder({HALL: ("52.1", "13.2")}):
            page = self.page()
            maps.locate(page)
        data = maps.map_data(page)
        self.assertEqual(data["tiles"], "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
        self.assertEqual(data["attribution"], "© OpenStreetMap-Mitwirkende")
        self.assertTrue(data["leaflet"]["js"].startswith("/static/vendor/leaflet/leaflet.js"))
        self.assertEqual(
            data["places"],
            [
                {
                    "key": maps.address_key(HALL),
                    "number": 1,
                    "label": "Stadthalle",
                    "address": HALL,
                    "lat": 52.1,
                    "lon": 13.2,
                }
            ],
        )


class CorrectionTests(LocateTests):
    """UIX-034: a position is corrected by hand – it then holds for every record with that address."""

    def test_set_by_hand_and_logged(self) -> None:
        """UIX-034: the position replaces what was found; the venue's history says so."""
        with FakeGeocoder({HALL: ("52.1", "13.2")}):
            page = self.page()
            maps.locate(page)
        maps.set_position(page, maps.address_key(HALL), "52,51", " 13.39 ", user=self.admin)
        position = AddressPosition.objects.get()
        self.assertEqual((position.latitude, position.longitude, position.source), (D("52.51"), D("13.39"), "manual"))
        self.assertEqual(position.updated_by, self.admin)
        entry = AuditLogEntry.objects.get(event="map.position_set")
        self.assertEqual(entry.object_id, str(self.venue.pk))
        self.assertEqual(entry.changes["address"], HALL)

    def test_values_are_checked(self) -> None:
        """UIX-034: numbers within their range, an address of this map."""
        page = self.page()
        key = maps.address_key(HALL)
        for latitude, longitude in (("91", "10"), ("50", "-181"), ("Nord", "10")):
            with self.subTest(latitude=latitude, longitude=longitude), self.assertRaises(ValidationError):
                maps.set_position(page, key, latitude, longitude, user=self.admin)
        with self.assertRaises(ValidationError):
            maps.set_position(page, maps.address_key("Anderswo 1"), "50", "10", user=self.admin)
        self.assertFalse(AddressPosition.objects.exists())

    def test_only_who_may_change_the_record(self) -> None:
        """UIX-034: correcting needs the right to change the venue (Kunden: bearbeiten)."""
        reader = make_user("leser", roles=("Nur-Lesen",))
        page = self.page(user=reader)
        self.assertFalse(page.can_correct)
        with self.assertRaises(PermissionDenied):
            maps.set_position(page, maps.address_key(HALL), "50", "10", user=reader)
        with self.assertRaises(PermissionDenied):
            maps.forget_position(page, maps.address_key(HALL), user=reader)

    def test_forget_asks_again(self) -> None:
        """UIX-034: "Neu suchen lassen" forgets the position; the next opening asks the geocoder."""
        with FakeGeocoder() as geocoder:
            page = self.page()
            maps.locate(page)
            maps.forget_position(page, maps.address_key(HALL), user=self.admin)
            self.assertFalse(AddressPosition.objects.exists())
            maps.locate(self.page())
        self.assertEqual(len(geocoder.questions), 2)
        self.assertTrue(AuditLogEntry.objects.filter(event="map.position_forgotten").exists())


class RightsTests(LocateTests):
    """UIX-034: who sees which map."""

    def test_targets(self) -> None:
        """Venue and customer: Kunden; supplier: Projekte, Material or Verwaltung; company: Verwaltung."""
        store = make_user("lager", roles=("Lager",))
        supplier = Supplier.objects.create(
            name="Verleih Nord", street="Verleihstraße 9", postal_code="54321", city="Nordstadt"
        )
        with self.assertRaises(PermissionDenied):
            self.page(user=store)
        page = self.page("supplier", supplier.pk, user=store)
        self.assertEqual([place.address for place in page.places], [NORD])
        self.assertTrue(page.can_correct)  # Lager writes material and may add suppliers (PRJ-101)
        with self.assertRaises(PermissionDenied):
            self.page("company", 1, user=store)
        with self.assertRaises(Http404):
            self.page("planet", 1)
        with self.assertRaises(Http404):
            self.page("venue", 999_999)

    def test_company_with_the_warehouse(self) -> None:
        """PRJ-097: the company and – if it differs – the warehouse."""
        company(warehouse=WAREHOUSE)
        page = self.page("company", 1)
        self.assertEqual(
            [place.address for place in page.places], ["Hafen 1, 12345 Musterstadt, Deutschland", WAREHOUSE]
        )
        self.assertEqual(page.places[1].label, "Lager")

    def test_customer_with_further_addresses(self) -> None:
        """UIX-033: the route to a delivery address starts at the warehouse, to a billing address where one is."""
        company(warehouse=WAREHOUSE)
        customer = save_customer(
            Customer(name="Kulturamt", street="Rathausplatz 1", postal_code="12345", city="Musterstadt")
        )
        CustomerAddress.objects.create(
            customer=customer, kind=AddressKind.DELIVERY, label="Lager Nord", street="Nordweg 2", city="Musterstadt"
        )
        CustomerAddress.objects.create(
            customer=customer, kind=AddressKind.BILLING, street="Postfach 1", city="Musterstadt"
        )
        page = self.page("customer", customer.pk)
        self.assertEqual([place.label for place in page.places], ["Kulturamt", "Rechnungsadresse", "Lager Nord"])
        # UIX-033: every route starts where the viewer is, also to a delivery address.
        for place in page.places:
            self.assertNotIn("origin=", place.route_url)

    def test_project_map_for_the_crew(self) -> None:
        """PRJ-097: crew sees the map of a project it is planned in; correcting needs edit access."""
        from tests.helpers import make_person, plan

        project = make_project(venue_site=self.venue)
        crew = make_user("crew", roles=("Crew",))
        with self.assertRaises(Http404):
            self.page("project", project.pk, user=crew)
        plan(project, "Bühnentechnik", make_person("Kim Crew", user=crew))
        page = self.page("project", project.pk, user=crew)
        self.assertFalse(page.can_correct)
        self.assertIn(HALL, [place.address for place in page.places])
        self.assertTrue(self.page("project", project.pk).can_correct)


class CleanupTests(LocateTests):
    """UIX-034, KND-010: positions are personal data where the address is a person's."""

    def test_anonymising_a_customer_removes_its_positions(self) -> None:
        """KND-010: the positions of its main and further addresses go with the address."""
        private = save_customer(
            Customer(name="Miriam Krause", kind=CustomerKind.PRIVATE, street="Gartenweg 4", city="Neudorf")
        )
        CustomerAddress.objects.create(customer=private, street="Feldweg 1", city="Neudorf")
        with FakeGeocoder({"Gartenweg 4, Neudorf": ("51", "10"), "Feldweg 1, Neudorf": ("51.1", "10.1")}):
            maps.locate(self.page("customer", private.pk))
            maps.locate(self.page())
        self.assertEqual(AddressPosition.objects.count(), 3)
        anonymise_customer(private)
        self.assertEqual(list(AddressPosition.objects.values_list("address", flat=True)), [HALL])

    def test_daily_maintenance_removes_unused_positions(self) -> None:
        """UIX-034: a changed address leaves its old position behind – removed at night."""
        with FakeGeocoder({HALL: ("52.1", "13.2")}):
            maps.locate(self.page())
        AddressPosition.objects.create(key=maps.address_key("Alte Straße 1"), address="Alte Straße 1", source="found")
        project = make_project(venue="Messe, Halle 7")
        ProjectPhase.objects.create(
            project=project, kind=PhaseKind.SETUP, start=at(10, 8), end=at(10, 12), location="Zelt am See"
        )
        for address in ("Messe, Halle 7", "Zelt am See"):
            AddressPosition.objects.create(key=maps.address_key(address), address=address, source="found")
        self.assertEqual(maps.delete_unused_positions(), 1)
        self.assertEqual(
            sorted(AddressPosition.objects.values_list("address", flat=True)),
            sorted([HALL, "Messe, Halle 7", "Zelt am See"]),
        )


class TripTests(RentalarsTestCase):
    """PRJ-097: the trips of a project, determined from its phases and addresses."""

    def setUp(self) -> None:
        super().setUp()
        company(warehouse=WAREHOUSE)
        self.hall = Venue.objects.create(
            name="Stadthalle", street="Hallenweg 3", postal_code="12345", city="Musterstadt"
        )
        self.project = make_project(venue_site=self.hall, start=at(10, 8), end=at(13, 18))
        self.nord = Supplier.objects.create(
            name="Verleih Nord", street="Verleihstraße 9", postal_code="54321", city="Nordstadt"
        )
        self.spots = make_stock("L-080", 2, "Spot")
        self.line = add_line(self.project, self.spots, 4).line

    def phase(self, kind: str, start: datetime.datetime, end: datetime.datetime, **fields: object) -> ProjectPhase:
        return ProjectPhase.objects.create(project=self.project, kind=kind, start=start, end=end, **fields)

    def subrent(self, supplier: Supplier | None = None, *, picked_up: bool = True, **fields: object) -> None:
        line = services.accept_subrental_suggestion(
            self.line, self.spots, 2, rights=ALL_RIGHTS, supplier=supplier or self.nord
        )
        services.update_line(line, rights=ALL_RIGHTS, picked_up_at_supplier=picked_up, **fields)

    def test_setup_and_teardown_there_and_back(self) -> None:
        """PRJ-097: warehouse → venue and back at setup and at teardown, each with a route link."""
        self.phase(PhaseKind.SETUP, at(10, 8), at(10, 16))
        self.phase(PhaseKind.EVENT, at(11, 18), at(11, 23))
        self.phase(PhaseKind.TEARDOWN, at(12, 0), at(12, 4))
        trips = trips_of(self.project)
        self.assertEqual(
            [(trip.kind, trip.title, trip.start) for trip in trips],
            [
                (TripKind.TO_VENUE, "Fahrt zum Aufbau", at(10, 8)),
                (TripKind.FROM_VENUE, "Rückfahrt vom Aufbau", at(10, 16)),
                (TripKind.TO_VENUE, "Fahrt zum Abbau", at(12, 0)),
                (TripKind.FROM_VENUE, "Rückfahrt vom Abbau", at(12, 4)),
            ],
        )
        # UIX-033: the route links start where the viewer is; the trip still names its start.
        query = parse_qs(urlsplit(trips[0].route_url).query)
        self.assertEqual((query.get("origin"), query["destination"]), (None, [HALL]))
        query = parse_qs(urlsplit(trips[1].route_url).query)
        self.assertEqual((query.get("origin"), query["destination"]), (None, [WAREHOUSE]))
        self.assertEqual((trips[0].origin.address, trips[1].origin.address), (WAREHOUSE, HALL))
        self.assertEqual([trip.problems for trip in trips], [[], [], [], []])

    def test_pickups_at_packing_and_returns_at_the_follow_up_work(self) -> None:
        """PRJ-097: subrentals "wird beim Lieferanten abgeholt" – one round trip over all such suppliers."""
        sued = Supplier.objects.create(name="Licht Süd", street="Südring 1", postal_code="11111", city="Südstadt")
        self.subrent()
        self.subrent(sued)
        self.subrent(Supplier.objects.create(name="Bringt selbst"), picked_up=False)
        self.phase(PhaseKind.LOADING, at(9, 8), at(9, 14))
        self.phase(PhaseKind.AFTERCARE, at(13, 9), at(13, 12))
        trips = trips_of(self.project)
        self.assertEqual([trip.kind for trip in trips], [TripKind.PICKUP, TripKind.RETURN])
        self.assertEqual(trips[0].title, "Abholung bei den Lieferanten")
        self.assertEqual(trips[1].title, "Rückgabe bei den Lieferanten")
        self.assertEqual([stop.label for stop in trips[0].stops], ["Verleih Nord", "Licht Süd"])
        query = parse_qs(urlsplit(trips[0].route_url).query)
        self.assertNotIn("origin", query)  # UIX-033: from where the viewer is, over the stops
        self.assertEqual(query["destination"], [WAREHOUSE])
        self.assertEqual(query["waypoints"], [f"{NORD}|Südring 1, 11111 Südstadt"])
        self.assertEqual(trips[1].start, at(13, 9))

    def test_pickups_without_packing_phase_at_the_period_of_the_subrentals(self) -> None:
        """PRJ-097: no phase "Packen" or "Nachbereitung" – at the start and the end of the subrentals."""
        self.subrent()
        trips = trips_of(self.project)
        self.assertEqual(
            [(trip.kind, trip.start, trip.phase) for trip in trips],
            [
                (TripKind.PICKUP, at(10, 8), None),
                (TripKind.RETURN, at(13, 18), None),
            ],
        )

    def test_optional_subrentals_and_unmarked_ones_make_no_trip(self) -> None:
        """PRJ-097: only what is really fetched – no optional lines, nothing the supplier brings."""
        add_line(
            self.project,
            services.default_subrental_product(),
            1,
            title="Nebelmaschine",
            supplier=self.nord,
            picked_up_at_supplier=True,
            variant=LineVariant.OPTIONAL,
        )
        self.subrent(picked_up=False)
        self.assertEqual(trips_of(self.project), [])

    def test_the_venue_of_a_phase(self) -> None:
        """PRJ-097: phase venue, project venue, phase place, project venue text, delivery address – in this order."""
        other = Venue.objects.create(name="Zelt", street="Seeweg 1", city="Seedorf")
        self.phase(PhaseKind.SETUP, at(10, 8), at(10, 9), venue_site=other)
        self.phase(PhaseKind.TEARDOWN, at(12, 8), at(12, 9), location="Halle 3")
        destinations = [trip.destination.address for trip in trips_of(self.project) if trip.kind == TripKind.TO_VENUE]
        self.assertEqual(destinations, ["Seeweg 1, Seedorf", HALL])
        self.project.venue_site = None
        self.project.venue = "Messe Köln"
        self.project.save()
        destinations = [trip.destination.address for trip in trips_of(self.project) if trip.kind == TripKind.TO_VENUE]
        self.assertEqual(destinations, ["Seeweg 1, Seedorf", "Halle 3"])
        ProjectPhase.objects.filter(location="Halle 3").update(location="")
        destinations = [trip.destination.address for trip in trips_of(self.project) if trip.kind == TripKind.TO_VENUE]
        self.assertEqual(destinations, ["Seeweg 1, Seedorf", "Messe Köln"])
        self.project.venue = ""
        self.project.delivery_address = CustomerAddress.objects.create(
            customer=self.project.customer,
            kind=AddressKind.DELIVERY,
            street="Lieferweg 2",
            postal_code="12345",
            city="Musterstadt",
        )
        self.project.save()
        destinations = [trip.destination.address for trip in trips_of(self.project) if trip.kind == TripKind.TO_VENUE]
        self.assertEqual(destinations, ["Seeweg 1, Seedorf", "Lieferweg 2, 12345 Musterstadt"])

    def test_what_is_missing_is_named(self) -> None:
        """PRJ-097: a warehouse without address, a supplier without address, a phase without venue."""
        company(street="", postal_code="", city="")
        profile = CompanyProfile.load()
        profile.country = ""
        profile.save()
        self.project.venue_site = None
        self.project.save()
        self.subrent(Supplier.objects.create(name="Ohne Adresse"))
        self.phase(PhaseKind.SETUP, at(10, 8), at(10, 9))
        trips = trips_of(self.project)
        pickup = next(trip for trip in trips if trip.kind == TripKind.PICKUP)
        self.assertIn(
            "Die Anschrift des Lagers fehlt (Einstellungen → Firmendaten und Grundeinstellungen).", pickup.problems
        )
        self.assertIn("Der Lieferant Ohne Adresse hat noch keine Anschrift.", pickup.problems)
        to_venue = next(trip for trip in trips if trip.kind == TripKind.TO_VENUE)
        self.assertEqual(to_venue.route_url, "")
        self.assertIn("Phase und Projekt nennen keinen Veranstaltungsort mit Anschrift.", to_venue.problems)

    def test_places_for_the_map_and_the_api(self) -> None:
        """PRJ-097: warehouse, venue, suppliers – each address once; without trips the venue of the project."""
        self.assertEqual([place.address for place in places_of(self.project)], [WAREHOUSE, HALL])
        self.subrent()
        self.phase(PhaseKind.SETUP, at(10, 8), at(10, 9))
        self.phase(PhaseKind.TEARDOWN, at(12, 8), at(12, 9))
        self.assertEqual([place.address for place in places_of(self.project)], [WAREHOUSE, NORD, HALL])
        document = trip_document(next(trip for trip in trips_of(self.project) if trip.kind == TripKind.PICKUP))
        self.assertEqual(document["kind"], TripKind.PICKUP)
        self.assertEqual(document["stops"], [{"label": "Verleih Nord", "note": "Lieferant", "address": NORD}])
        self.assertTrue(document["route_url"].startswith("https://www.google.com/maps/dir/?api=1"))

    def test_bounded_queries(self) -> None:
        """PRJ-097: the trips cost the same few queries, however many phases and subrentals."""
        for day in range(9, 13):
            self.phase(PhaseKind.SETUP, at(day, 8), at(day, 9))
        for _number in range(4):
            self.subrent(Supplier.objects.create(name=f"Lieferant {_number}", city="Irgendwo"))
        CompanyProfile.load()
        # Company profile, phases with venues, subrentals with suppliers; and the trips changed by hand (PRJ-111).
        with self.assertNumQueries(4):
            trips_of(self.project)
