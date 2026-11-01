# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the maps (API-014): route links at addresses (UIX-033), the places of a map with their positions
and a position set by hand (UIX-034), the trips of a project and subrentals picked up at the supplier (PRJ-097).

The geocoder is ``tests.geocoder_fake``.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from rentalars.core import maps
from rentalars.core.models import AddressPosition, AuditLogEntry, CompanyProfile
from rentalars.customers.models import AddressKind, Customer, CustomerAddress, Venue
from rentalars.customers.services import save_customer
from rentalars.masterdata.models import Supplier
from rentalars.projects import services
from rentalars.projects.models import PhaseKind, ProjectPhase
from tests.api.base import API, ApiTestCase
from tests.geocoder_fake import FakeGeocoder
from tests.helpers import ALL_RIGHTS, add_line, at, make_person, make_project, make_stock, make_user, plan

WAREHOUSE = "Industriestraße 5, 12345 Musterstadt"
HALL = "Hallenweg 3, 12345 Musterstadt"
NORD = "Verleihstraße 9, 54321 Nordstadt"


def query_of(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query)


class MapApiCase(ApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        profile = CompanyProfile.load()
        profile.street, profile.postal_code, profile.city = "Hafen 1", "12345", "Musterstadt"
        profile.save()
        self.hall = Venue.objects.create(
            name="Stadthalle", street="Hallenweg 3", postal_code="12345", city="Musterstadt"
        )
        self.nord = Supplier.objects.create(
            name="Verleih Nord", street="Verleihstraße 9", postal_code="54321", city="Nordstadt"
        )


class SettingsAndRouteApiTests(MapApiCase):
    """UIX-033, PRJ-097, UIX-034 in the existing resources."""

    def test_warehouse_and_maps_setting(self) -> None:
        """PRJ-097: the warehouse address; UIX-034: "Karten sofort laden" – both in /settings."""
        response = self.admin.patch(
            f"{API}/settings",
            {"company": {"warehouse_address": WAREHOUSE}, "system": {"maps_load_at_once": True}},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["company"]["warehouse_address"], WAREHOUSE)
        self.assertTrue(response.json()["system"]["maps_load_at_once"])

    def test_route_links_of_venues_customers_and_suppliers(self) -> None:
        """UIX-033: ``route_url`` to venue, supplier and delivery address – from where the viewer is."""
        venue = self.admin.get(f"{API}/venues/{self.hall.pk}").json()
        self.assertEqual(query_of(venue["route_url"]), {"api": ["1"], "destination": [HALL]})
        customer = save_customer(Customer(name="Kulturamt", street="Rathausplatz 1", city="Musterstadt"))
        document = self.admin.get(f"{API}/customers/{customer.pk}").json()
        self.assertEqual(
            query_of(document["route_url"]), {"api": ["1"], "destination": ["Rathausplatz 1, Musterstadt"]}
        )
        CustomerAddress.objects.create(
            customer=customer, kind=AddressKind.DELIVERY, street="Nordweg 2", city="Musterstadt"
        )
        addresses = self.admin.get(f"{API}/customers/{customer.pk}/addresses").json()
        self.assertNotIn("origin", query_of(addresses[0]["route_url"]))
        supplier = self.admin.get(f"{API}/suppliers/{self.nord.pk}").json()
        self.assertNotIn("origin", query_of(supplier["route_url"]))
        self.assertEqual((supplier["street"], supplier["city"]), ("Verleihstraße 9", "Nordstadt"))
        self.assertEqual(query_of(supplier["route_url"])["destination"], [NORD])

    def test_supplier_address_is_written(self) -> None:
        """UIX-033: the address of a supplier through /suppliers."""
        response = self.admin.patch(
            f"{API}/suppliers/{self.nord.pk}", {"street": "Neue Straße 1", "postal_code": "54321"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.nord.refresh_from_db()
        self.assertEqual(self.nord.address_one_line, "Neue Straße 1, 54321 Nordstadt")


class MapApiTests(MapApiCase):
    """UIX-034: ``/maps/{target}/{id}`` and its positions."""

    def test_read_a_map(self) -> None:
        """UIX-034: places with route link and position; missing positions are looked up once."""
        with FakeGeocoder({HALL: ("52.1", "13.2")}) as geocoder:
            response = self.admin.get(f"{API}/maps/venue/{self.hall.pk}")
            self.admin.get(f"{API}/maps/venue/{self.hall.pk}")
        self.assertEqual(response.status_code, 200, response.content)
        document = response.json()
        self.assertEqual(geocoder.questions, [HALL])
        self.assertEqual((document["target"], document["id"], document["title"]), ("venue", self.hall.pk, "Stadthalle"))
        self.assertTrue(document["can_correct"])
        place = document["places"][0]
        self.assertEqual((place["address"], place["position"], place["latitude"]), (HALL, "found", "52.100000"))
        self.assertEqual(place["key"], maps.address_key(HALL))
        self.assertTrue(place["route_url"].startswith("https://www.google.com/maps/dir/?api=1"))

    def test_company_and_project(self) -> None:
        """PRJ-097: the company (id 1) with the warehouse; a project with the places of its trips."""
        profile = CompanyProfile.load()
        profile.warehouse_address = WAREHOUSE
        profile.save()
        with FakeGeocoder():
            company = self.admin.get(f"{API}/maps/company/1").json()
            project = make_project(venue_site=self.hall)
            places = self.admin.get(f"{API}/maps/project/{project.pk}").json()["places"]
        self.assertEqual([place["note"] for place in company["places"]], ["Firma", "Lager"])
        self.assertEqual([place["address"] for place in places], [WAREHOUSE, HALL])
        self.assertEqual(self.admin.get(f"{API}/maps/planet/1").status_code, 404)

    def test_set_and_forget_a_position(self) -> None:
        """UIX-034: PUT sets it by hand (logged), DELETE forgets it; wrong values are refused."""
        key = maps.address_key(HALL)
        url = f"{API}/maps/venue/{self.hall.pk}/positions/{key}"
        self.assert_error(
            self.admin.put(url, {"latitude": "100", "longitude": "13"}, format="json"),
            400,
            "validation_error",
            "latitude",
        )
        response = self.admin.put(url, {"latitude": 52.5, "longitude": "13.4"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["places"][0]["position"], "manual")
        self.assertEqual(AddressPosition.objects.get().source, "manual")
        self.assertTrue(AuditLogEntry.objects.filter(event="map.position_set", object_id=str(self.hall.pk)).exists())
        response = self.admin.delete(url)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["places"][0]["position"], "unknown")
        self.assertFalse(AddressPosition.objects.exists())
        self.assert_error(
            self.admin.put(
                f"{API}/maps/venue/{self.hall.pk}/positions/{'0' * 64}", {"latitude": 1, "longitude": 1}, format="json"
            ),
            400,
            "validation_error",
        )

    def test_rights(self) -> None:
        """UIX-034: reading needs the record; correcting needs the right to change it."""
        reader = self.client_for("leser", "Nur-Lesen")
        key = maps.address_key(HALL)
        with FakeGeocoder():
            self.assertFalse(reader.get(f"{API}/maps/venue/{self.hall.pk}").json()["can_correct"])
        self.assertEqual(
            reader.put(
                f"{API}/maps/venue/{self.hall.pk}/positions/{key}", {"latitude": 1, "longitude": 1}, format="json"
            ).status_code,
            403,
        )
        self.assertEqual(reader.delete(f"{API}/maps/venue/{self.hall.pk}/positions/{key}").status_code, 403)
        crew = self.client_for("crew", "Crew")
        self.assertEqual(crew.get(f"{API}/maps/venue/{self.hall.pk}").status_code, 403)
        self.assertEqual(crew.get(f"{API}/maps/company/1").status_code, 403)


class TripApiTests(MapApiCase):
    """PRJ-097: ``/projects/{id}/trips`` and the pickup of subrentals."""

    def setUp(self) -> None:
        super().setUp()
        self.project = make_project(venue_site=self.hall, start=at(10, 8), end=at(13, 18))
        self.spots = make_stock("L-080", 2, "Spot")
        line = add_line(self.project, self.spots, 4).line
        self.subrental = services.accept_subrental_suggestion(
            line, self.spots, 2, rights=ALL_RIGHTS, supplier=self.nord
        )
        ProjectPhase.objects.create(project=self.project, kind=PhaseKind.SETUP, start=at(10, 8), end=at(10, 16))

    def test_trips(self) -> None:
        """PRJ-097: warehouse → venue and back, with route links; the crew reads them too."""
        response = self.admin.get(f"{API}/projects/{self.project.pk}/trips")
        self.assertEqual(response.status_code, 200, response.content)
        trips = response.json()
        self.assertEqual([trip["kind"] for trip in trips], ["to_venue", "from_venue"])
        self.assertEqual(trips[0]["title"], "Fahrt zum Aufbau")
        self.assertEqual(trips[0]["destination"], {"label": "Stadthalle", "note": "Veranstaltungsort", "address": HALL})
        self.assertEqual(query_of(trips[0]["route_url"])["destination"], [HALL])
        crew_user = make_user("crew", roles=("Crew",))
        crew = self.client_of(crew_user)
        self.assertEqual(crew.get(f"{API}/projects/{self.project.pk}/trips").status_code, 404)
        plan(self.project, "Bühnentechnik", make_person("Kim Crew", user=crew_user))
        self.assertEqual(len(crew.get(f"{API}/projects/{self.project.pk}/trips").json()), 2)

    def test_pickup_through_the_subrental_api(self) -> None:
        """PRJ-097: ``picked_up_at_supplier`` in PATCH /projects/{id}/subrentals/{supplier} – and the trips follow."""
        url = f"{API}/projects/{self.project.pk}/subrentals/{self.nord.pk}"
        self.assert_error(
            self.admin.patch(url, {"lines": [{"id": self.subrental.pk, "picked_up_at_supplier": "ja"}]}, format="json"),
            400,
            "validation_error",
        )
        response = self.admin.patch(
            url, {"lines": [{"id": self.subrental.pk, "picked_up_at_supplier": True}]}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["lines"][0]["picked_up_at_supplier"])
        self.assertEqual(response.json()["supplier"]["city"], "Nordstadt")
        kinds = [trip["kind"] for trip in self.admin.get(f"{API}/projects/{self.project.pk}/trips").json()]
        self.assertEqual(kinds, ["pickup", "to_venue", "from_venue", "return"])
        pickup = self.admin.get(f"{API}/projects/{self.project.pk}/trips").json()[0]
        self.assertEqual(query_of(pickup["route_url"])["waypoints"], [NORD])

    def test_pickup_through_the_line_api(self) -> None:
        """PRJ-097: the field of the material line."""
        url = f"{API}/projects/{self.project.pk}/material-lines/{self.subrental.pk}"
        self.assertFalse(self.admin.get(url).json()["picked_up_at_supplier"])
        response = self.admin.patch(url, {"picked_up_at_supplier": True}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.subrental.refresh_from_db()
        self.assertTrue(self.subrental.picked_up_at_supplier)
