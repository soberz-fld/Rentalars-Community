# SPDX-License-Identifier: GPL-3.0-or-later
"""In the browser: the map after "Karte anzeigen" (UIX-034) with Leaflet from this server, the correction of a
position by click and by typing, the trips of a project with their map (PRJ-097) – and axe-core on all of it.

The map pictures come from this test server (a picture of ``static/``), the geocoder is ``tests.geocoder_fake``:
the base class fails every test that asks another server for anything (NFA-050).
"""

from __future__ import annotations

from unittest import SkipTest

from django.test import override_settings

from rentalars.config import MapsConfig
from rentalars.core.models import AddressPosition, CompanyProfile
from rentalars.customers.models import Venue
from rentalars.projects.models import PhaseKind, ProjectPhase
from rentalars.projects.trips import trips_of
from tests.browser.base import BrowserTestCase
from tests.browser.test_accessibility_in_browser import WCAG_AA, _axe_path
from tests.geocoder_fake import FakeGeocoder

WAREHOUSE = "Industriestraße 5, 12345 Musterstadt"
HALL = "Hallenweg 3, 12345 Musterstadt"


class MapsInBrowserTests(BrowserTestCase):
    """UIX-034 and PRJ-097 where only a browser shows them; no finding of axe-core."""

    bypass_csp = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.axe = _axe_path()
        if cls.axe is None:
            raise SkipTest("axe-core is not at hand (see tests/browser/test_accessibility_in_browser.py).")
        super().setUpClass()

    def axe_findings(self, within: str = "") -> list[str]:
        """What axe-core finds on the page, or only within the elements a selector names."""
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_function("() => document.getAnimations().every(a => a.playState !== 'running')")
        if not self.page.evaluate("() => typeof axe !== 'undefined'"):
            self.page.add_script_tag(path=str(self.axe))
        return self.page.evaluate(
            "async ([tags, within]) => (await axe.run(within ? {include: [[within]]} : document,"
            " {runOnly: {type: 'tag', values: tags}})).violations"
            ".map(v => v.id + ' (' + v.impact + '): ' + v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | '))",
            [WCAG_AA, within],
        )

    def setUp(self) -> None:
        super().setUp()
        # The map pictures come from this server: a small picture of the static files for every tile.
        tiles = f"{self.live_server_url}/static/img/favicon-32.png?{{z}}/{{x}}/{{y}}"
        self.enterContext(
            override_settings(RENTALARS_MAPS=MapsConfig(tile_url=tiles, geocoder_url="https://geo.example/search"))
        )
        self.geocoder = self.enterContext(FakeGeocoder({HALL: ("52.0", "11.0"), WAREHOUSE: ("52.02", "11.05")}))
        profile = CompanyProfile.load()
        profile.warehouse_address = WAREHOUSE
        profile.save()
        self.hall = Venue.objects.create(
            name="Stadthalle", street="Hallenweg 3", postal_code="12345", city="Musterstadt"
        )

    def show_map(self) -> None:
        self.page.get_by_role("button", name="Karte anzeigen").click()
        self.page.locator(".map-canvas.leaflet-container .map-pin").first.wait_for()
        self.settle()

    def test_the_map_of_a_venue(self) -> None:
        """UIX-034: nothing before the click; then Leaflet from here, the marker, tiles and the attribution."""
        self.open(f"/customers/venues/{self.hall.pk}/")
        self.settle()
        self.assertEqual(self.geocoder.questions, [])
        self.assertFalse(self.page.evaluate("() => typeof window.L !== 'undefined'"))
        self.assertEqual(self.axe_findings(), [])
        self.show_map()
        self.assertEqual(self.geocoder.questions, [HALL])
        self.assertEqual(self.page.locator(".map-pin").count(), 1)
        self.assertGreater(self.page.locator(".leaflet-tile-loaded").count(), 0)
        self.assertIn("© OpenStreetMap-Mitwirkende", self.text_of(".leaflet-control-attribution"))
        self.assertEqual(self.page.locator(".leaflet-control-zoom-in").get_attribute("title"), "Vergrößern")
        # The focus went to the map, not back to the top of the page.
        self.assertEqual(self.page.evaluate("() => document.activeElement.className"), "map-frame")
        # Zooming with the buttons works.
        zoom = self.page.evaluate("() => document.querySelector('.map-canvas').mapInstance.getZoom()")
        self.page.locator(".leaflet-control-zoom-out").click()
        self.page.wait_for_function(f"() => document.querySelector('.map-canvas').mapInstance.getZoom() < {zoom}")
        self.assertEqual(self.axe_findings(".map-box"), [])

    def test_correct_the_position_by_click_and_by_typing(self) -> None:
        """UIX-034: a click into the map fills the fields; typed coordinates are saved as well."""
        self.open(f"/customers/venues/{self.hall.pk}/")
        self.show_map()
        self.page.locator(".map-correct summary").click()
        self.assertEqual(self.axe_findings(".map-box"), [])
        before = self.page.input_value("[data-map-latitude]")
        box = self.page.locator(".map-canvas").bounding_box()
        self.page.mouse.click(box["x"] + 40, box["y"] + box["height"] - 40)
        self.page.wait_for_function(f"() => document.querySelector('[data-map-latitude]').value !== '{before}'")
        clicked = float(self.page.input_value("[data-map-latitude]"))
        self.assertLess(clicked, 52.0)
        self.page.get_by_role("button", name="Position speichern").click()
        self.page.get_by_text("Die Position ist gespeichert.").wait_for()
        self.settle()
        position = AddressPosition.objects.get(address=HALL)
        self.assertEqual(position.source, "manual")
        self.assertAlmostEqual(float(position.latitude), clicked, places=5)
        # By keyboard: type the coordinates.
        self.page.locator(".map-correct summary").click()
        self.page.fill("[data-map-latitude]", "52,3")
        self.page.fill("[data-map-longitude]", "11.3")
        self.page.locator("[data-map-longitude]").press("Enter")
        self.page.get_by_text("Die Position ist gespeichert.").wait_for()
        self.settle()
        position.refresh_from_db()
        self.assertEqual((str(position.latitude), str(position.longitude)), ("52.300000", "11.300000"))
        self.assertEqual(self.page.locator(".map-pin").count(), 1)

    def test_the_trips_of_a_project(self) -> None:
        """PRJ-097: the trips on "Zeitplanung" and "Überblick" with route links and a map of warehouse and venue."""
        self.project.venue_site = self.hall
        self.project.save()
        ProjectPhase.objects.create(
            project=self.project,
            kind=PhaseKind.SETUP,
            start=self.project.start,
            end=self.project.start.replace(hour=16),
        )
        self.open(f"/projects/{self.project.pk}/course/")
        trips = self.page.locator("#trips")
        trips.wait_for()
        self.assertIn("Fahrt zum Aufbau", self.text_of("#trips"))
        # The sample project brings phases of its own (setup and teardown): every trip has its link.
        self.assertEqual(trips.locator("a.route-link[target=_blank]").count(), len(trips_of(self.project)))
        self.assertEqual(self.axe_findings("#trips"), [])
        trips.get_by_role("button", name="Karte anzeigen").click()
        trips.locator(".map-pin").nth(1).wait_for()
        self.settle()
        self.assertEqual(trips.locator(".map-pin").count(), 2)
        self.assertEqual(self.axe_findings("#trips"), [])
        self.open(f"/projects/{self.project.pk}/deployment/")
        self.assertIn("Rückfahrt vom Aufbau", self.text_of("#trips"))
        self.assertEqual(self.axe_findings("#trips"), [])


class MapUnderThePolicyInBrowserTests(BrowserTestCase):
    """UIX-034, NFA-006: the map works under the content security policy of the page – no inline script needed."""

    def test_map_with_the_policy_of_the_page(self) -> None:
        """UIX-034: Leaflet and its style sheet load from this server; the page shows the marker."""
        tiles = f"{self.live_server_url}/static/img/favicon-32.png?{{z}}/{{x}}/{{y}}"
        self.enterContext(override_settings(RENTALARS_MAPS=MapsConfig(tile_url=tiles)))
        self.enterContext(FakeGeocoder({HALL: ("52.0", "11.0")}))
        hall = Venue.objects.create(name="Stadthalle", street="Hallenweg 3", postal_code="12345", city="Musterstadt")
        self.open(f"/customers/venues/{hall.pk}/")
        self.page.get_by_role("button", name="Karte anzeigen").click()
        self.page.locator(".map-canvas.leaflet-container .map-pin").wait_for()
        self.settle()
        self.assertGreater(self.page.locator(".leaflet-tile-loaded").count(), 0)
        # tearDown: no console error (a refused script or style would be one), no request to another server.
