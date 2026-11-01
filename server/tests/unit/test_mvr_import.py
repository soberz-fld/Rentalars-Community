# SPDX-License-Identifier: GPL-3.0-or-later
"""Lighting plots from MVR files: reading, suggestions, adding lines (PRJ-077)."""

from __future__ import annotations

import io
import zipfile
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError

from rentalars.products.models import FixtureTypeMapping, Product, ProductKind
from rentalars.projects import mvr
from rentalars.projects.models import ProjectStatus
from tests.helpers import ALL_RIGHTS, RentalarsTestCase, add_group, make_items, make_model, make_product, make_project

ROBIN = "Robe_Lighting@Robin_T1_Profile.gdtf"
SKYPANEL = "ARRI@SkyPanel_S60-C@V4.gdtf"
HAZER = "Generic@Hazer.gdtf"


def fixture(name: str, spec: str, mode: str, fixture_id: str = "", *, tag: str = "Fixture") -> str:
    """A fixture as Vectorworks writes it: GDTFSpec and GDTFMode as child elements."""
    return (
        f'<{tag} name="{name}" uuid="00000000-0000-0000-0000-000000000000"><Matrix>{{1,0,0}}{{0,1,0}}{{0,0,1}}'
        f"{{0,0,0}}</Matrix><GDTFSpec>{spec}</GDTFSpec><GDTFMode>{mode}</GDTFMode>"
        f"<FixtureID>{fixture_id}</FixtureID><UnitNumber>0</UnitNumber></{tag}>"
    )


def group(name: str, *children: str) -> str:
    return f'<GroupObject name="{name}"><Matrix/><ChildList>{"".join(children)}</ChildList></GroupObject>'


def scene(*children: str, namespace: str = "") -> str:
    """A GeneralSceneDescription with one layer holding ``children``."""
    xmlns = f' xmlns="{namespace}"' if namespace else ""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="no" ?>'
        f'<GeneralSceneDescription verMajor="1" verMinor="6"{xmlns}>'
        # Vendor data may contain anything – also elements called "Fixture"; they are not counted.
        f'<UserData><Data provider="Vectorworks">{fixture("vendor", ROBIN, "Mode 1")}</Data></UserData>'
        f'<Scene><AUXData/><Layers><Layer name="Licht"><ChildList>{"".join(children)}</ChildList></Layer></Layers>'
        "</Scene></GeneralSceneDescription>"
    )


def gdtf(manufacturer: str, long_name: str, *, description: str | None = None) -> bytes:
    """A GDTF file: a ZIP archive with description.xml."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "description.xml",
            description
            or (
                '<?xml version="1.0" encoding="UTF-8"?><GDTF DataVersion="1.2">'
                f'<FixtureType Manufacturer="{manufacturer}" LongName="{long_name}" Name="T1" ShortName="T1"/></GDTF>'
            ),
        )
        archive.writestr("thumbnail.png", b"\x89PNG")
    return buffer.getvalue()


def make_mvr(scene_xml: str | bytes, files: dict[str, bytes] | None = None) -> bytes:
    """An MVR file: a ZIP archive with the scene description and further files."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("GeneralSceneDescription.xml", scene_xml)
        for name, data in (files or {}).items():
            archive.writestr(name, data)
    return buffer.getvalue()


def sample_plot() -> bytes:
    """Five Robin T1 in mode 1 (also in nested groups), one in mode 2, two SkyPanels, a hazer, a truss."""
    return make_mvr(
        scene(
            fixture("Spot 1", ROBIN, "Mode 1 - Standard 16 bit", "101"),
            fixture("Spot 2", ROBIN, "Mode 1 - Standard 16 bit", "102"),
            group(
                "Traverse 1",
                fixture("Spot 3", ROBIN, "Mode 1 - Standard 16 bit", "103"),
                group(
                    "Traverse 1 links",
                    fixture("Spot 4", ROBIN, "mode 1 -  standard 16 BIT", "104"),
                    fixture("Spot 5", ROBIN, "Mode 1 - Standard 16 bit", "105"),
                    fixture("Spot 6", ROBIN, "Mode 2 - Basic", "106"),
                ),
                '<Truss name="Traverse 1"><Matrix/><Geometries/></Truss>',
            ),
            fixture("Fläche 1", SKYPANEL, "CCT", "201"),
            fixture("Fläche 2", SKYPANEL, "CCT", "202"),
            fixture("Nebel", HAZER, "Default"),
            fixture("Truss 2m", "Prolyte@H30V_2m.gdtf", "", tag="Truss"),
            '<SceneObject name="Bühne"><Matrix/><Geometries/></SceneObject>',
            '<FocusPoint name="Mitte"><Matrix/></FocusPoint>',
        ),
        {ROBIN: gdtf("Robe Lighting", "Robin T1 Profile"), "Resources/stage.3ds": b"3ds"},
    )


def read(data: bytes, name: str = "plot.mvr") -> mvr.Plot:
    return mvr.read_plot(io.BytesIO(data), name)


class ReadingTests(RentalarsTestCase):
    """PRJ-077: fixtures counted per GDTF file and mode, in layers and nested groups."""

    def test_counts_per_type(self) -> None:
        plot = read(sample_plot())
        summary = [(t.manufacturer, t.model, t.mode, t.count, t.element) for t in plot.types]
        self.assertEqual(
            summary,
            [
                ("ARRI", "SkyPanel S60-C", "CCT", 2, "Fixture"),
                ("Generic", "Hazer", "Default", 1, "Fixture"),
                ("Prolyte", "H30V 2m", "", 1, "Truss"),
                ("Robe Lighting", "Robin T1 Profile", "Mode 1 - Standard 16 bit", 5, "Fixture"),
                ("Robe Lighting", "Robin T1 Profile", "Mode 2 - Basic", 1, "Fixture"),
            ],
        )
        self.assertEqual((plot.fixture_count, plot.skipped), (10, 2))
        robin = plot.type(mvr.type_key(ROBIN, "Mode 1 - Standard 16 bit"))
        self.assertEqual((robin.named_by_gdtf, robin.examples), (True, ["101 Spot 1", "102 Spot 2", "103 Spot 3"]))
        self.assertEqual(robin.key, "robe_lighting@robin_t1_profile|mode 1 - standard 16 bit")
        self.assertFalse(plot.type(mvr.type_key(SKYPANEL, "CCT")).named_by_gdtf)
        self.assertEqual(mvr.Plot.from_dict(plot.as_dict()), plot)

    def test_namespaces_and_attributes(self) -> None:
        """Namespace-agnostic, and GDTFSpec/GDTFMode as attributes are read as well."""
        data = make_mvr(
            scene(
                '<Fixture name="A" GDTFSpec="Martin@MAC_Aura_XB.gdtf" GDTFMode="Mode 1"><Matrix/></Fixture>',
                fixture("B", "Martin@MAC_Aura_XB.gdtf", "Mode 1"),
                namespace="http://www.gdtf-share.com/mvr",
            )
        )
        plot = read(data)
        self.assertEqual([(t.label, t.count) for t in plot.types], [("Martin MAC Aura XB", 2)])

    def test_names(self) -> None:
        self.assertEqual(
            mvr.names_from_spec("Robe_Lighting@Robin_T1_Profile.gdtf"), ("Robe Lighting", "Robin T1 Profile")
        )
        self.assertEqual(mvr.names_from_spec("folder\\ARRI@SkyPanel_S60-C@V4.gdtf"), ("ARRI", "SkyPanel S60-C"))
        self.assertEqual(mvr.names_from_spec("Hazer.gdtf"), ("", "Hazer"))
        self.assertEqual(mvr.default_group_name("Stadtfest Plot.MVR"), "MVR Stadtfest Plot")


class SafetyTests(RentalarsTestCase):
    """PRJ-077: limits against ZIP bombs, no DTDs (billion laughs), clear messages."""

    def assert_refused(self, data: bytes, message: str) -> None:
        with self.assertRaises(ValidationError) as caught:
            read(data)
        self.assertIn(message, " ".join(caught.exception.messages))

    def test_broken_and_foreign_files(self) -> None:
        self.assert_refused(b"PK not really", "keine MVR-Datei")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("scene.xml", scene(fixture("A", ROBIN, "Mode 1")))
        self.assert_refused(buffer.getvalue(), "keine GeneralSceneDescription.xml")
        self.assert_refused(make_mvr("<GeneralSceneDescription><Scene>"), "lässt sich nicht lesen")
        self.assert_refused(make_mvr("<Plot/>"), "nicht aus MVR")
        self.assert_refused(make_mvr(scene('<SceneObject name="Bühne"/>')), "kein Gerät mit GDTF-Datei")

    def test_entities_are_refused(self) -> None:
        bomb = (
            '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;">]>'
            "<GeneralSceneDescription>&lol2;</GeneralSceneDescription>"
        )
        self.assert_refused(make_mvr(bomb), "Dokumenttyp-Deklaration")
        self.assert_refused(make_mvr(bomb.encode("utf-16")), "nicht in UTF-8")
        with self.assertRaises(ValidationError):
            mvr.parse_xml(b"<a/><!-- --><!entity x 'y'>")
        # A GDTF file with a DTD is not read; the type keeps the name from the file name.
        poisoned = gdtf("", "", description=bomb.replace("GeneralSceneDescription", "GDTF"))
        plot = read(make_mvr(scene(fixture("A", ROBIN, "Mode 1")), {ROBIN: poisoned}))
        self.assertEqual((plot.types[0].label, plot.types[0].named_by_gdtf), ("Robe Lighting Robin T1 Profile", False))

    def test_limits(self) -> None:
        data = sample_plot()
        with mock.patch.object(mvr, "MAX_MEMBERS", 2):
            self.assert_refused(data, "mehr als 2 Dateien")
        with mock.patch.object(mvr, "MAX_UNPACKED_BYTES", 1024):
            self.assert_refused(data, "Entpackt wäre das Archiv größer")
        with mock.patch.object(mvr, "MAX_SCENE_BYTES", 1024):
            self.assert_refused(data, "GeneralSceneDescription.xml im Archiv ist größer")
        # A GDTF file over its limit is not opened; reading goes on with the name from the file name.
        with mock.patch.object(mvr, "MAX_GDTF_BYTES", 10):
            self.assertFalse(read(data).type(mvr.type_key(ROBIN, "Mode 2 - Basic")).named_by_gdtf)
        # A small archive with a huge, highly compressed scene stops at the limit before it is unpacked.
        bomb = make_mvr(scene(fixture("A", ROBIN, "Mode 1")) + " " * 5_000_000)
        with mock.patch.object(mvr, "MAX_SCENE_BYTES", 100_000):
            self.assert_refused(bomb, "größer als")


class SuggestionTests(RentalarsTestCase):
    """PRJ-077: remembered choices first, then the most similar products and models."""

    def setUp(self) -> None:
        super().setUp()
        self.spot = make_product("L-010", "Moving Head Profil T1")
        make_model("Robin T1 Profile", self.spot, manufacturer="Robe")
        self.panel = make_product("L-020", "LED-Fläche SkyPanel S60")
        self.profile = make_product("L-030", "Profilscheinwerfer Source Four 26°")
        # The service "Lichttechniker" of the start data (PER-037) resembles a light, but is never suggested.
        self.assertTrue(Product.objects.filter(name="Lichttechniker", kind=ProductKind.SERVICE).exists())
        self.plot = read(sample_plot())

    def suggestions(self, spec: str, mode: str) -> list[mvr.Suggestion]:
        return mvr.suggest(self.plot.types)[mvr.type_key(spec, mode)]

    def test_similar_products_and_models(self) -> None:
        robin = self.suggestions(ROBIN, "Mode 1 - Standard 16 bit")
        self.assertEqual((robin[0].product_id, robin[0].source), (self.spot.pk, "similar"))
        self.assertGreaterEqual(robin[0].score, 90)
        self.assertEqual(robin[0].reason, "Modell Robe Robin T1 Profile")
        self.assertEqual(mvr.preselection(robin), robin[0])
        panel = self.suggestions(SKYPANEL, "CCT")
        self.assertEqual(panel[0].product_id, self.panel.pk)
        self.assertGreaterEqual(panel[0].score, mvr.PRESELECT_SCORE)
        self.assertNotIn(self.profile.pk, [suggestion.product_id for suggestion in panel])
        # Nothing resembles a hazer, and services are never suggested.
        self.assertEqual(self.suggestions(HAZER, "Default"), [])

    def test_the_letters_count_without_spaces(self) -> None:
        self.assertGreater(
            mvr.similarity(mvr.Text.of("SkyPanel S60-C"), mvr.Text.of("Sky Panel S60C")),
            mvr.similarity(mvr.Text.of("SkyPanel S60-C"), mvr.Text.of("SkyPanel S30-C")),
        )
        self.assertIn("t1", mvr.Text.of("Robin T-1").anchors)

    def test_remembered_choice_comes_first(self) -> None:
        FixtureTypeMapping.objects.create(
            gdtf_spec=mvr.spec_key(ROBIN), gdtf_mode=mvr.mode_key("Mode 1 - Standard 16 bit"), product=self.profile
        )
        mode_1 = self.suggestions(ROBIN, "Mode 1 - Standard 16 bit")
        self.assertEqual(
            [(s.product_id, s.source, s.score) for s in mode_1[:2]],
            [
                (self.profile.pk, "remembered", 100),
                (self.spot.pk, "similar", mode_1[1].score),
            ],
        )
        mode_2 = self.suggestions(ROBIN, "Mode 2 - Basic")
        self.assertEqual((mode_2[0].product_id, mode_2[0].source), (self.profile.pk, "remembered_mode"))
        self.assertEqual(mvr.preselection(mode_2), mode_2[0])
        self.profile.is_active = False
        self.profile.save()
        self.assertEqual(self.suggestions(ROBIN, "Mode 1 - Standard 16 bit")[0].product_id, self.spot.pk)


class TakeOverTests(RentalarsTestCase):
    """PRJ-077: one line per chosen type through the services of the planning; choices are remembered."""

    def setUp(self) -> None:
        super().setUp()
        self.spot = make_product("L-010", "Robin T1 Profile", price="80.00")
        make_items(make_model("Robin T1 Profile", self.spot, manufacturer="Robe"), 4)
        self.panel = make_product("L-020", "SkyPanel S60", price="60.00")
        make_items(make_model("SkyPanel S60-C", self.panel, manufacturer="ARRI"), 2)
        self.project = make_project()
        self.plot = read(sample_plot(), "Stadtfest.mvr")
        self.robin = mvr.type_key(ROBIN, "Mode 1 - Standard 16 bit")
        self.sky = mvr.type_key(SKYPANEL, "CCT")

    def test_lines_in_a_new_group(self) -> None:
        choices = {
            self.robin: mvr.Choice(self.spot, Decimal("5")),
            self.sky: mvr.Choice(self.panel, Decimal("2")),
        }
        result = mvr.take_over(self.project, self.plot, choices, rights=ALL_RIGHTS, new_group_name="MVR Stadtfest")
        self.assertEqual(result.group.name, "MVR Stadtfest")
        lines = list(self.project.material_lines.order_by("position"))
        self.assertEqual(
            [(line.product, line.quantity, line.group, line.unit_price) for line in lines],
            [
                (self.panel, Decimal("2.00"), result.group, Decimal("60.00")),
                (self.spot, Decimal("5.00"), result.group, Decimal("80.00")),
            ],
        )
        # Four Robin T1 in stock, five planned: added all the same, with a warning (PRJ-013).
        self.assertEqual(result.warnings, ["Robin T1 Profile ist hinzugefügt, aber in diesem Zeitraum fehlt 1 Stück."])
        remembered = FixtureTypeMapping.objects.get(gdtf_mode=mvr.mode_key("Mode 1 - Standard 16 bit"))
        self.assertEqual(
            (remembered.gdtf_spec, remembered.product, remembered.label),
            ("robe_lighting@robin_t1_profile", self.spot, "Robe Lighting Robin T1 Profile"),
        )

    def test_existing_group_without_remembering(self) -> None:
        lights = add_group(self.project, "Licht")
        mvr.take_over(
            self.project,
            self.plot,
            {self.sky: mvr.Choice(self.panel, Decimal("2"))},
            rights=ALL_RIGHTS,
            group=lights,
            remember=False,
        )
        self.assertEqual(lights.lines.get().product, self.panel)
        self.assertFalse(FixtureTypeMapping.objects.exists())

    def test_all_or_nothing(self) -> None:
        with self.assertRaises(ValidationError):
            mvr.take_over(self.project, self.plot, {}, rights=ALL_RIGHTS, new_group_name="MVR")
        self.panel.is_active = False
        self.panel.save()
        choices = {self.robin: mvr.Choice(self.spot, Decimal("5")), self.sky: mvr.Choice(self.panel, Decimal("2"))}
        with self.assertRaises(ValidationError):
            mvr.take_over(self.project, self.plot, choices, rights=ALL_RIGHTS, new_group_name="MVR")
        self.assertFalse(self.project.material_lines.exists())
        self.assertFalse(self.project.groups.exists())
        self.assertFalse(FixtureTypeMapping.objects.exists())
        closed = make_project("Altes Fest", status=ProjectStatus.CLOSED)
        with self.assertRaises(ValidationError):
            mvr.take_over(closed, self.plot, {self.robin: mvr.Choice(self.spot, Decimal("1"))}, rights=ALL_RIGHTS)
