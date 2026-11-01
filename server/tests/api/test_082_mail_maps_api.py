# SPDX-License-Identifier: GPL-3.0-or-later
"""API, area "mail-maps" (API-014).

* EML-049: ``untagged_since`` and ``untagged_unread_only`` in ``/mail/mailboxes`` and ``/mail/mailbox-addresses`` –
  set to the moment of switching on when not sent, kept when sent, ``null`` while switched off.
* UIX-033: the ``route_url`` of venues, customer addresses, suppliers, maps and trips names no start.
"""

from __future__ import annotations

import datetime
from urllib.parse import parse_qs, urlsplit

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from rentalars.core.models import CompanyProfile
from rentalars.customers.models import AddressKind, Customer, CustomerAddress, Venue
from rentalars.customers.services import save_customer
from rentalars.masterdata.models import Supplier
from rentalars.projects.models import PhaseKind, ProjectPhase
from tests.api.base import API, ApiTestCase
from tests.geocoder_fake import FakeGeocoder
from tests.helpers import NOW, make_project
from tests.mailbox import configure_mailbox

MAILBOXES = f"{API}/mail/mailboxes"
ADDRESSES = f"{API}/mail/mailbox-addresses"


class CutoffApiTests(ApiTestCase):
    """EML-049 through the API."""

    def setUp(self) -> None:
        super().setUp()
        self.box = configure_mailbox(process_untagged=False)

    def test_mailbox(self) -> None:
        url = f"{MAILBOXES}/{self.box.pk}"
        document = self.admin.get(url).json()
        self.assertEqual((document["untagged_since"], document["untagged_unread_only"]), (None, False))
        switched = self.admin.patch(url, {"process_untagged": True}, format="json")
        self.assertEqual(switched.status_code, 200, switched.content)
        self.assertEqual(parse_datetime(switched.json()["untagged_since"]), timezone.now())
        given = "2027-02-01T09:00:00+01:00"
        changed = self.admin.patch(url, {"untagged_since": given, "untagged_unread_only": True}, format="json")
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual(parse_datetime(changed.json()["untagged_since"]), parse_datetime(given))
        self.assertTrue(changed.json()["untagged_unread_only"])
        self.assert_error(self.admin.patch(url, {"untagged_since": "gestern"}, format="json"), 400, "validation_error")
        off = self.admin.patch(url, {"process_untagged": False}, format="json")
        self.assertIsNone(off.json()["untagged_since"])
        # Switching on with a moment of one's own keeps it.
        on = self.admin.patch(url, {"process_untagged": True, "untagged_since": given}, format="json")
        self.assertEqual(parse_datetime(on.json()["untagged_since"]), parse_datetime(given))

    def test_address(self) -> None:
        created = self.admin.post(
            ADDRESSES,
            {"mailbox": self.box.pk, "address": "info@verleih.example", "untagged": "inquiry"},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        data = created.json()
        self.assertEqual(parse_datetime(data["untagged_since"]), timezone.now())
        self.assertFalse(data["untagged_unread_only"])
        url = f"{ADDRESSES}/{data['id']}"
        changed = self.admin.patch(url, {"untagged_unread_only": True}, format="json")
        self.assertTrue(changed.json()["untagged_unread_only"])
        ignored = self.admin.patch(url, {"untagged": "ignore"}, format="json")
        self.assertIsNone(ignored.json()["untagged_since"])
        mailbox = self.admin.get(f"{MAILBOXES}/{self.box.pk}").json()
        self.assertIn("untagged_since", mailbox["addresses"][0])

    def test_the_schema_names_the_fields(self) -> None:
        schema = self.admin.get(f"{API}/schema", {"format": "json"}).json()
        for name in ("Mailbox", "MailboxAddress"):
            properties = schema["components"]["schemas"][name]["properties"]
            self.assertEqual(properties["untagged_since"]["format"], "date-time")
            self.assertTrue(properties["untagged_since"]["nullable"])
            self.assertEqual(properties["untagged_unread_only"]["type"], "boolean")


def query_of(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query)


class RouteApiTests(ApiTestCase):
    """UIX-033: no ``route_url`` of the API names a start."""

    def setUp(self) -> None:
        super().setUp()
        profile = CompanyProfile.load()
        profile.warehouse_address = "Industriestraße 5, 12345 Musterstadt"
        profile.save()
        self.hall = Venue.objects.create(
            name="Stadthalle", street="Hallenweg 3", postal_code="12345", city="Musterstadt"
        )
        self.nord = Supplier.objects.create(name="Verleih Nord", street="Nordweg 1", city="Nordstadt")

    def test_records(self) -> None:
        venue = self.admin.get(f"{API}/venues/{self.hall.pk}").json()
        self.assertEqual(
            query_of(venue["route_url"]), {"api": ["1"], "destination": ["Hallenweg 3, 12345 Musterstadt"]}
        )
        supplier = self.admin.get(f"{API}/suppliers/{self.nord.pk}").json()
        self.assertEqual(query_of(supplier["route_url"]), {"api": ["1"], "destination": ["Nordweg 1, Nordstadt"]})
        customer = save_customer(Customer(name="Kulturamt", street="Rathausplatz 1", city="Musterstadt"))
        CustomerAddress.objects.create(customer=customer, kind=AddressKind.DELIVERY, street="Lagerweg 2", city="X")
        addresses = self.admin.get(f"{API}/customers/{customer.pk}/addresses").json()
        self.assertEqual(query_of(addresses[0]["route_url"]), {"api": ["1"], "destination": ["Lagerweg 2, X"]})
        with FakeGeocoder():
            places = self.admin.get(f"{API}/maps/venue/{self.hall.pk}").json()["places"]
        self.assertNotIn("origin", query_of(places[0]["route_url"]))

    def test_trips_keep_their_stops(self) -> None:
        project = make_project(venue_site=self.hall)
        ProjectPhase.objects.create(
            project=project, kind=PhaseKind.SETUP, start=NOW, end=NOW + datetime.timedelta(hours=4)
        )
        trips = self.admin.get(f"{API}/projects/{project.pk}/trips").json()
        self.assertTrue(trips)
        for trip in trips:
            self.assertNotIn("origin", query_of(trip["route_url"]))
        self.assertEqual(trips[0]["origin"]["address"], "Industriestraße 5, 12345 Musterstadt")
