# SPDX-License-Identifier: GPL-3.0-or-later
"""LOG-017 in a real browser: "Geplante km aus der Route vorschlagen" fills the planned kilometres.

The button of the dialog of a vehicle on a trip asks the server; the page script writes the kilometres – with a
decimal comma – into "Geplante km" and reads out what happened, without a dialog of the browser. Routino and the
geocoder are stand-ins (tests.unit.test_090_routing), positions are set by hand.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.test import override_settings

from rentalars.core import routing
from rentalars.core.models import AddressPosition, PositionSource
from rentalars.projects import course
from rentalars.projects.models import PhaseKind
from rentalars.projects.trips import trips_of
from tests.browser.base import BrowserTestCase
from tests.helpers import at
from tests.unit.test_090_routing import NO_NODE, TWO_POINTS, FakeRouter, company_with_warehouse, done


class RouteSuggestionInBrowserTests(BrowserTestCase):
    """LOG-017: the suggestion goes into the field and stays changeable."""

    def setUp(self) -> None:
        super().setUp()
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        router = folder / "routino-router"
        router.write_text("#!/bin/sh\n", encoding="utf-8")
        (folder / "data").mkdir()
        (folder / "data" / "rentalars-nodes.mem").write_bytes(b"\0")
        local_file = folder / "route-local.conf"
        local_file.write_text(
            f"[route]\nkind = routino\nrouter = {router}\ndata_dir = {folder / 'data'}\nregion = bayern\n",
            encoding="utf-8",
        )
        override = override_settings(RENTALARS_ROUTE_LOCAL_FILE=str(local_file))
        override.enable()
        self.addCleanup(override.disable)
        company_with_warehouse()  # where the trips start
        trips = trips_of(self.project)
        if not trips:
            course.add_phase(
                self.project,
                kind=PhaseKind.SETUP,
                start=at(10, 8),
                end=at(10, 16),
                location="Marktplatz 1, Musterstadt",
            )
            trips = trips_of(self.project)
        self.trip = trips[0]
        for number, place in enumerate(self.trip.places):
            AddressPosition.objects.update_or_create(
                key=place.key,
                defaults={
                    "address": place.address,
                    "latitude": f"52.{number:02d}",
                    "longitude": "13.0",
                    "source": PositionSource.MANUAL,
                },
            )

    def open_dialog(self) -> None:
        self.open(f"/projects/{self.project.pk}/logistics/trips/new/?trip={self.trip.key}")

    def test_the_button_fills_the_planned_kilometres(self) -> None:
        with mock.patch.object(routing, "_run", FakeRouter(done(TWO_POINTS))):
            self.open_dialog()
            self.page.click("button[data-route-suggest]")
            self.page.wait_for_function(
                "() => document.querySelector('[data-route-status]').textContent.includes('laut Route')"
            )
        self.assertEqual(self.page.input_value("input[name=planned_km]"), "12,4")
        self.assertEqual(self.text_of("[data-route-status]"), "12,4 km laut Route – ein Vorschlag, änderbar.")
        # Always changeable.
        self.page.fill("input[name=planned_km]", "15")
        self.assertEqual(self.page.input_value("input[name=planned_km]"), "15")

    def test_an_error_is_read_out(self) -> None:
        with mock.patch.object(routing, "_run", FakeRouter(done(stderr=NO_NODE, returncode=1))):
            self.open_dialog()
            self.page.fill("input[name=planned_km]", "7")
            self.page.click("button[data-route-suggest]")
            self.page.wait_for_function(
                "() => document.querySelector('[data-route-status]').textContent.includes('keine Straße')"
            )
        self.assertIn("(Bayern) gibt es keine Straße bei", self.text_of("[data-route-status]"))
        self.assertEqual(self.page.input_value("input[name=planned_km]"), "7")
