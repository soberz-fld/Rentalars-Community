# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages of the maps: "Route in Google Maps" at every address (UIX-033), the map after "Karte anzeigen"
(UIX-034) and the trips of a project on "Zeitplanung" and "Überblick" (PRJ-097).

The geocoder is ``tests.geocoder_fake``; no page sends anything to another server by itself (NFA-050).
"""

from __future__ import annotations

import io
import json
import re
from html import unescape
from urllib.parse import parse_qs, urlsplit

from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

from rentalars.config import MapsConfig
from rentalars.core import maps
from rentalars.core.models import AddressPosition, AuditLogEntry, CompanyProfile, SystemSettings
from rentalars.customers.models import AddressKind, Customer, CustomerAddress, Venue
from rentalars.customers.services import save_customer
from rentalars.masterdata.models import Supplier
from rentalars.projects import services
from rentalars.projects.models import MaterialLine, PhaseKind, ProjectPhase
from tests.geocoder_fake import FakeGeocoder
from tests.helpers import ALL_RIGHTS, add_line, at, make_person, make_project, make_stock, make_user, plan
from tests.ui.base import UiTestCase, form_data

WAREHOUSE = "Industriestraße 5, 12345 Musterstadt"
HALL = "Hallenweg 3, 12345 Musterstadt"
NORD = "Verleihstraße 9, 54321 Nordstadt"
TILES = "img-src 'self' data: https://tile.openstreetmap.org;"


def links_to_google(html: str) -> list[dict[str, list[str]]]:
    """The queries of all links into Google Maps on a page."""
    found = re.findall(r'href="(https://www\.google\.com/maps/dir/\?[^"]+)"', html)
    return [parse_qs(urlsplit(unescape(url)).query) for url in found]


class MapPagesCase(UiTestCase):
    """A company with a warehouse, a venue, a customer with a delivery address and a supplier."""

    def setUp(self) -> None:
        super().setUp()
        profile = CompanyProfile.load()
        profile.name, profile.street, profile.postal_code, profile.city = (
            "Muster GmbH",
            "Hafen 1",
            "12345",
            "Musterstadt",
        )
        profile.warehouse_address = WAREHOUSE
        profile.save()
        self.hall = Venue.objects.create(
            name="Stadthalle", street="Hallenweg 3", postal_code="12345", city="Musterstadt"
        )
        self.nord = Supplier.objects.create(
            name="Verleih Nord", street="Verleihstraße 9", postal_code="54321", city="Nordstadt", email="d@nord.example"
        )


class RouteLinkPageTests(MapPagesCase):
    """UIX-033: one click into the route planning of Google Maps; nothing leaves before."""

    def test_venue_page(self) -> None:
        """UIX-033: from where one is, in a new tab, without referrer; UIX-034: the button, no request yet."""
        with FakeGeocoder() as geocoder:
            response = self.client.get(reverse("customers:venue_detail", args=[self.hall.pk]))
        html = self.assert_ok(response)
        self.assertEqual(links_to_google(html), [{"api": ["1"], "destination": [HALL]}])
        self.assertIn('class="route-link" href="https://www.google.com/maps/dir/?api=1&amp;destination=', html)
        self.assertIn('target="_blank" rel="noopener noreferrer"', html)
        self.assertIn("Route in Google Maps", html)
        self.assertIn("(öffnet Google Maps in einem neuen Tab)", html)
        self.assertIn("Karte anzeigen", html)
        self.assertIn(f'hx-get="{reverse("core:map", args=["venue", self.hall.pk])}"', html)
        self.assertIn("Erst mit dem Klick geht die Adresse an OpenStreetMap", html)
        self.assertEqual(geocoder.questions, [])
        self.assertFalse(AddressPosition.objects.exists())
        # The page may load map pictures from the tile server – and nothing else from outside.
        self.assertIn(TILES, response["Content-Security-Policy"])
        self.assertNotIn("tile.openstreetmap.org", self.client.get(reverse("projects:list"))["Content-Security-Policy"])

    def test_customer_page(self) -> None:
        """UIX-033: every address from where one is – also a delivery address."""
        customer = save_customer(
            Customer(name="Kulturamt", street="Rathausplatz 1", postal_code="12345", city="Musterstadt")
        )
        CustomerAddress.objects.create(
            customer=customer, kind=AddressKind.DELIVERY, street="Nordweg 2", city="Musterstadt"
        )
        CustomerAddress.objects.create(
            customer=customer, kind=AddressKind.BILLING, street="Postfach 9", city="Musterstadt"
        )
        html = self.assert_ok(self.client.get(reverse("customers:detail", args=[customer.pk])))
        self.assertEqual(
            links_to_google(html),
            [
                {"api": ["1"], "destination": ["Rathausplatz 1, 12345 Musterstadt"]},
                {"api": ["1"], "destination": ["Postfach 9, Musterstadt"]},
                {"api": ["1"], "destination": ["Nordweg 2, Musterstadt"]},
            ],
        )
        self.assertIn(reverse("core:map", args=["customer", customer.pk]), html)

    def test_deployment_view_from_where_one_is(self) -> None:
        """UIX-033: the crew drives from home – the venue without origin; PRJ-097: the trips with the warehouse."""
        project = make_project(venue_site=self.hall)
        html = self.assert_ok(self.client.get(reverse("projects:deployment", args=[project.pk])))
        self.assertIn({"api": ["1"], "destination": [HALL]}, links_to_google(html))

    def test_settings_page(self) -> None:
        """UIX-033, PRJ-097: the company and the warehouse; the settings of the maps."""
        html = self.assert_ok(self.client.get(reverse("core:company_settings")))
        self.assertIn({"api": ["1"], "destination": ["Hafen 1, 12345 Musterstadt, Deutschland"]}, links_to_google(html))
        self.assertIn({"api": ["1"], "destination": [WAREHOUSE]}, links_to_google(html))
        self.assertIn("Route zum Lager", html)
        self.assertIn("Anschrift des Lagers", html)
        self.assertIn("Karten sofort laden", html)
        self.assertIn(reverse("core:map", args=["company", 1]), html)

    def test_settings_are_saved(self) -> None:
        """PRJ-097, UIX-034: warehouse address and "Karten sofort laden" are saved with their forms."""
        page = self.client.get(reverse("core:company_settings"))
        data = form_data(
            page, "company-warehouse_address", **{"company-warehouse_address": "Lagerweg 1, 12345 Musterstadt"}
        )
        self.client.post(reverse("core:company_settings"), data)
        self.assertEqual(CompanyProfile.load().warehouse_address, "Lagerweg 1, 12345 Musterstadt")
        page = self.client.get(reverse("core:company_settings"))
        data = form_data(page, "system-max_upload_mb", **{"system-maps_load_at_once": "on"})
        self.client.post(reverse("core:company_settings"), data)
        self.assertTrue(SystemSettings.load().maps_load_at_once)

    def test_supplier_in_the_master_data(self) -> None:
        """UIX-033: the supplier's address in the master data, with its route link from where one is."""
        html = self.assert_ok(self.client.get(reverse("admin:masterdata_supplier_change", args=[self.nord.pk])))
        for field in ("street", "postal_code", "city", "country"):
            self.assertIn(f'name="{field}"', html)
        self.assertEqual(links_to_google(html), [{"api": ["1"], "destination": [NORD]}])


class MapPageTests(MapPagesCase):
    """UIX-034: the map after the click."""

    def test_load_at_once(self) -> None:
        """UIX-034: with the setting the map is fetched right away – still by the browser, after the page."""
        settings = SystemSettings.load()
        settings.maps_load_at_once = True
        settings.save()
        html = self.assert_ok(self.client.get(reverse("customers:venue_detail", args=[self.hall.pk])))
        self.assertIn('hx-trigger="load"', html)
        self.assertNotIn("Karte anzeigen", html)

    def test_maps_switched_off(self) -> None:
        """UIX-034: tile_url empty – no map, no tile server in the policy; the route link stays."""
        with override_settings(RENTALARS_MAPS=MapsConfig(tile_url="")):
            response = self.client.get(reverse("customers:venue_detail", args=[self.hall.pk]))
            self.assertEqual(self.client.get(reverse("core:map", args=["venue", self.hall.pk])).status_code, 404)
        html = self.assert_ok(response)
        self.assertNotIn("Karte anzeigen", html)
        self.assertIn("Route in Google Maps", html)
        self.assertNotIn("tile.openstreetmap.org", response["Content-Security-Policy"])

    def test_the_map(self) -> None:
        """UIX-034: the click asks for the position once; the map gets tiles, attribution and Leaflet from here."""
        url = reverse("core:map", args=["venue", self.hall.pk])
        with FakeGeocoder({HALL: ("52.1", "13.2")}) as geocoder:
            html = self.assert_ok(self.htmx("get", url))
            self.htmx("get", url)
        self.assertEqual(geocoder.questions, [HALL])
        data = json.loads(unescape(re.search(r'data-map="([^"]+)"', html).group(1)))
        self.assertEqual(data["places"][0]["lat"], 52.1)
        self.assertEqual(data["attribution"], "© OpenStreetMap-Mitwirkende")
        self.assertEqual(data["attributionUrl"], "https://www.openstreetmap.org/copyright")
        self.assertIn("/static/vendor/leaflet/leaflet.js", data["leaflet"]["js"])
        self.assertIn('aria-label="Karte: Stadthalle"', html)
        self.assertIn("Position von OpenStreetMap", html)
        self.assertIn("Position korrigieren", html)
        self.assertIn('href="https://www.google.com/maps/dir/?api=1&amp;destination=', html)
        self.assertEqual(data["referrerPolicy"], "strict-origin-when-cross-origin")  # UIX-034

    def test_correct_and_forget(self) -> None:
        """UIX-034: a position set by hand is saved and logged; wrong values are named; "Neu suchen lassen"."""
        url = reverse("core:map_position", args=["venue", self.hall.pk])
        key = maps.address_key(HALL)
        with FakeGeocoder() as geocoder:
            refused = self.assert_ok(self.htmx("post", url, {"key": key, "latitude": "95", "longitude": "13"}))
            self.assertIn("Gib einen Wert zwischen -90 und 90 ein.", refused)
            self.assertIn('<details class="map-correct" open>', refused)
            saved = self.assert_ok(self.htmx("post", url, {"key": key, "latitude": "52,5", "longitude": "13.4"}))
            self.assertIn("Die Position ist gespeichert. Sie gilt für alles mit dieser Adresse.", saved)
            self.assertIn("Position von Hand gesetzt", saved)
            self.assertEqual(geocoder.questions, [HALL])  # the refused form showed the map, which asked once
            position = AddressPosition.objects.get()
            self.assertEqual(str(position.latitude), "52.500000")
            history = self.assert_ok(self.client.get(reverse("customers:venue_detail", args=[self.hall.pk])))
            self.assertIn(f"Position auf der Karte von Hand gesetzt: {HALL}", history)
            again = self.assert_ok(self.htmx("post", url, {"key": key, "action": "forget"}))
        self.assertIn("Die Position wurde verworfen und neu gesucht.", again)
        self.assertEqual(geocoder.questions, [HALL, HALL])
        self.assertEqual(AddressPosition.objects.get().source, "not_found")
        self.assertIn("Auf der Karte nicht gefunden.", again)

    def test_readers_cannot_correct(self) -> None:
        """UIX-034: who only reads the venue sees the map, not the correction; posting is refused."""
        reader = self.browser_for("leser", "Nur-Lesen")
        with FakeGeocoder({HALL: ("52.1", "13.2")}):
            html = self.assert_ok(self.htmx("get", reverse("core:map", args=["venue", self.hall.pk]), client=reader))
        self.assertNotIn("Position korrigieren", html)
        url = reverse("core:map_position", args=["venue", self.hall.pk])
        response = self.htmx(
            "post", url, {"key": maps.address_key(HALL), "latitude": "1", "longitude": "1"}, client=reader
        )
        self.assertEqual(response.status_code, 403)
        crew = self.browser_for("crew", "Crew")
        self.assertEqual(
            self.htmx("get", reverse("core:map", args=["venue", self.hall.pk]), client=crew).status_code, 403
        )

    def test_geocoder_unreachable(self) -> None:
        """UIX-034: the page says so; the list with the route links is still there."""
        from rentalars.core.geocoding import GeocoderError

        with FakeGeocoder(error=GeocoderError("Die Kartensuche ist nicht erreichbar.")):
            html = self.assert_ok(self.htmx("get", reverse("core:map", args=["venue", self.hall.pk])))
        self.assertIn("Die Kartensuche ist nicht erreichbar.", html)
        self.assertIn("Position noch nicht gesucht.", html)
        self.assertIn("Route in Google Maps", html)


class SubrentalPageTests(MapPagesCase):
    """UIX-033, PRJ-097 on the page "Zumietung bei …"."""

    def test_address_route_map_and_pickup(self) -> None:
        """The supplier's address with the route from the warehouse; "Abholung" per line, saved with the status."""
        project = make_project()
        spots = make_stock("L-080", 2, "Spot")
        line = add_line(project, spots, 4).line
        subrental = services.accept_subrental_suggestion(line, spots, 2, rights=ALL_RIGHTS, supplier=self.nord)
        url = reverse("projects:subrental", args=[project.pk, self.nord.pk])
        html = self.assert_ok(self.client.get(url))
        self.assertIn(NORD, html)
        self.assertEqual(links_to_google(html), [{"api": ["1"], "destination": [NORD]}])  # UIX-033
        self.assertIn(reverse("core:map", args=["supplier", self.nord.pk]), html)
        self.assertIn("<th>Abholung</th>", html)
        self.assertIn('aria-label="Wird beim Lieferanten abgeholt: 2 × Spot"', html)
        data = form_data(self.client.get(url), f"status_{subrental.pk}", **{f"pickup_{subrental.pk}": "on"})
        self.client.post(reverse("projects:subrental_lines", args=[project.pk, self.nord.pk]), data)
        subrental.refresh_from_db()
        self.assertTrue(subrental.picked_up_at_supplier)
        self.assertIn("Status, Abholung und Preise speichern", self.assert_ok(self.client.get(url)))
        reader = self.browser_for("leser", "Nur-Lesen")
        self.assertIn("wird beim Lieferanten abgeholt", self.assert_ok(reader.get(url)))


class LineDialogTests(MapPagesCase):
    """PRJ-097: "Wird beim Lieferanten abgeholt" in the dialog of a subrental line of the planning."""

    def test_the_line_dialog(self) -> None:
        """PRJ-097: the checkbox next to the purchase price; saved with the line."""
        project = make_project()
        spots = make_stock("L-080", 2, "Spot")
        line = add_line(project, spots, 4).line
        subrental = services.accept_subrental_suggestion(line, spots, 2, rights=ALL_RIGHTS, supplier=self.nord)
        url = reverse("projects:line_edit", args=[project.pk, subrental.pk])
        dialog = self.assert_ok(self.htmx("get", url))
        self.assertIn('name="picked_up_at_supplier"', dialog)
        self.assertIn("Wird beim Lieferanten abgeholt", dialog)
        data = form_data(self.htmx("get", url), "subrental_status", picked_up_at_supplier="on")
        self.htmx("post", url, data)
        subrental.refresh_from_db()
        self.assertTrue(subrental.picked_up_at_supplier)


class TripPageTests(MapPagesCase):
    """PRJ-097: "Fahrten" on Zeitplanung and Überblick."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(venue_site=self.hall, start=at(10, 8), end=at(13, 18))
        spots = make_stock("L-080", 2, "Spot")
        line = add_line(self.project, spots, 4).line
        subrental = services.accept_subrental_suggestion(line, spots, 2, rights=ALL_RIGHTS, supplier=self.nord)
        MaterialLine.objects.filter(pk=subrental.pk).update(picked_up_at_supplier=True)
        for kind, start, end in (
            (PhaseKind.LOADING, at(9, 8), at(9, 12)),
            (PhaseKind.SETUP, at(10, 8), at(10, 16)),
            (PhaseKind.TEARDOWN, at(12, 0), at(12, 4)),
            (PhaseKind.AFTERCARE, at(13, 9), at(13, 12)),
        ):
            ProjectPhase.objects.create(project=self.project, kind=kind, start=start, end=end)

    def test_course_page(self) -> None:
        """PRJ-097: six trips with their route links and the map of the places."""
        html = self.assert_ok(self.client.get(reverse("projects:course", args=[self.project.pk])))
        self.assertIn("<h2>Fahrten</h2>", html)
        for title in (
            "Abholung bei den Lieferanten",
            "Fahrt zum Aufbau",
            "Rückfahrt vom Aufbau",
            "Fahrt zum Abbau",
            "Rückfahrt vom Abbau",
            "Rückgabe bei den Lieferanten",
        ):
            self.assertIn(title, html)
        google = links_to_google(html)
        # UIX-033: from where one is; a trip with stops keeps them as waypoints.
        self.assertIn({"api": ["1"], "destination": [WAREHOUSE], "waypoints": [NORD]}, google)
        self.assertIn({"api": ["1"], "destination": [HALL]}, google)
        self.assertIn({"api": ["1"], "destination": [WAREHOUSE]}, google)
        self.assertFalse([link for link in google if "origin" in link])
        self.assertIn(reverse("core:map", args=["project", self.project.pk]), html)
        self.assertIn(
            TILES, self.client.get(reverse("projects:course", args=[self.project.pk]))["Content-Security-Policy"]
        )

    def test_problems_for_the_planner_not_for_the_crew(self) -> None:
        """PRJ-097: what is missing is named on Zeitplanung; drivers see the trips without it."""
        Supplier.objects.filter(pk=self.nord.pk).update(street="", postal_code="", city="")
        html = self.assert_ok(self.client.get(reverse("projects:course", args=[self.project.pk])))
        self.assertIn("Der Lieferant Verleih Nord hat noch keine Anschrift.", html)
        crew_user = make_user("crew", roles=("Crew",))
        plan(self.project, "Bühnentechnik", make_person("Kim Crew", user=crew_user))
        crew = self.browser_of(crew_user)
        overview = self.assert_ok(crew.get(reverse("projects:deployment", args=[self.project.pk])))
        self.assertIn("Fahrt zum Aufbau", overview)
        self.assertNotIn("hat noch keine Anschrift", overview)
        with FakeGeocoder({HALL: ("52.1", "13.2"), WAREHOUSE: ("52.0", "13.0")}):
            fragment = self.assert_ok(
                self.htmx("get", reverse("core:map", args=["project", self.project.pk]), client=crew)
            )
        self.assertIn("Stadthalle", fragment)
        self.assertNotIn("Position korrigieren", fragment)

    def test_no_trips(self) -> None:
        """PRJ-097: without phases – the hint where trips come from, and the venue on the map."""
        project = make_project(venue_site=self.hall)
        html = self.assert_ok(self.client.get(reverse("projects:course", args=[project.pk])))
        self.assertIn("Noch keine Fahrten.", html)
        self.assertIn(reverse("core:map", args=["project", project.pk]), html)


class MaintenanceTests(MapPagesCase):
    """UIX-034: the daily maintenance removes positions no address uses any more."""

    def test_line_of_the_daily_maintenance(self) -> None:
        """UIX-034."""
        AddressPosition.objects.create(key=maps.address_key("Alte Straße 1"), address="Alte Straße 1", source="found")
        output = io.StringIO()
        call_command("run_daily_maintenance", stdout=output)
        self.assertIn("Deleted 1 map positions of addresses no longer used (UIX-034).", output.getvalue())
        self.assertFalse(AddressPosition.objects.exists())
        self.assertFalse(AuditLogEntry.objects.filter(event__startswith="map.").exists())
