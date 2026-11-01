# SPDX-License-Identifier: GPL-3.0-or-later
"""Taking over a lighting plot from an MVR file into a project (PRJ-077).

The lighting designer draws the rig in Vectorworks, grandMA3, Capture or
WYSIWYG and exports it as MVR ("My Virtual Rig", DIN SPEC 15800). Such a
file is a ZIP archive. Its ``GeneralSceneDescription.xml`` lists every
object of the rig; each fixture names the GDTF file that describes its type,
e.g. ``Robe_Lighting@Robin_T1_Profile.gdtf``, and the DMX mode it runs in.
The GDTF files themselves usually travel inside the archive.

What happens here
-----------------
1. :func:`read_plot` counts the objects of the plot per type: GDTF file and
   mode. A readable "manufacturer model" comes from the ``description.xml``
   of the GDTF file in the archive, or else from the name of the GDTF file.
2. :func:`suggest` proposes a product for each type: the one chosen for
   this type before (:class:`~rentalars.products.models.FixtureTypeMapping`),
   or else the products whose names – or whose material models with their
   manufacturers – resemble the type most (:func:`similarity`).
3. :func:`take_over` adds one material line per chosen type with the count
   as quantity, through ``projects.services.add_line`` like every line of
   the planning page – availability and prices work as usual – and
   remembers the choices for the next plot.
4. :func:`keep_file` keeps the file in the files of the project, its name
   starting with the date and time of the import: ``20261013-221530_Rig.mvr``
   (PRJ-086). An MVR file can also be uploaded there by hand.

Safety
------
An uploaded archive is not trusted. Before anything is unpacked, the number
of files and their total size are checked, and only the scene description
and one ``description.xml`` per GDTF file are read, each with a limit of its
own; a "ZIP bomb" fails at those limits. XML with a document type
declaration is refused before it is parsed, because entity declarations in
it can blow up to gigabytes ("billion laughs"). XML that is not UTF-8 –
where such a declaration could hide from that check – is refused too, and
the parser itself stops at any declaration that still gets through
(:func:`parse_xml`). ``defusedxml`` is not a dependency of Rentalars, so
these checks stand in for it.
"""

from __future__ import annotations

import datetime
import difflib
import io
import itertools
import re
import xml.etree.ElementTree as ET
import zipfile
import zlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from functools import cached_property
from pathlib import PurePosixPath
from typing import IO, Any

from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.core.i18n import plural_of
from rentalars.core.tabular import fold
from rentalars.material.models import MaterialModel
from rentalars.products.models import CREW_ONLY_KINDS, LOGISTICS_KINDS, FixtureTypeMapping, Product, ProductKind
from rentalars.projects import services
from rentalars.projects.files import add_file
from rentalars.projects.models import Group, Project, ProjectFile

# --- Limits (PRJ-077) -----------------------------------------------------------------------------

#: The largest MVR file accepted. Plots with the 3D model of a venue can be big.
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
#: The most files an archive may contain (an MVR or a GDTF file).
MAX_MEMBERS = 5000
#: The most all files of an archive may add up to once unpacked, as the archive declares it.
MAX_UNPACKED_BYTES = 2 * 1024 * 1024 * 1024
#: The largest scene description that is read; its tree in memory takes about ten times as much.
MAX_SCENE_BYTES = 20 * 1024 * 1024
#: The largest GDTF file that is opened for its name, and all of them together.
MAX_GDTF_BYTES = 50 * 1024 * 1024
MAX_GDTF_TOTAL_BYTES = 200 * 1024 * 1024
#: The largest ``description.xml`` of a GDTF file that is read.
MAX_DESCRIPTION_BYTES = 10 * 1024 * 1024

SCENE_FILE = "generalscenedescription.xml"

#: Objects of a scene that are equipment, if they name a GDTF file; groups are looked into.
EQUIPMENT = frozenset({"Fixture", "Truss", "Support", "VideoScreen", "Projector", "SceneObject"})
#: How many fixture names of a type are kept as examples.
EXAMPLES = 3

#: Suggestions with at least this similarity are preselected; down to the second value they are offered.
PRESELECT_SCORE = 60
OFFER_SCORE = 35
#: How many products are offered per type.
OFFERED = 4

#: Products that are never suggested: they are no equipment – incidental costs neither (PRD-045).
NOT_EQUIPMENT = (
    ProductKind.SERVICE,
    ProductKind.SURCHARGE,
    ProductKind.SUBRENTAL,
    ProductKind.INCIDENTAL,
    ProductKind.VEHICLE,  # LOG-001
)


def _error(message: str) -> ValidationError:
    return ValidationError(message, code="invalid_mvr")


# --- The plot -------------------------------------------------------------------------------------


def spec_key(spec: str) -> str:
    """The GDTF file name as a key: without folder and ``.gdtf``, in lower case."""
    name = PurePosixPath(spec.replace("\\", "/").strip()).name
    if name.lower().endswith(".gdtf"):
        name = name[:-5]
    return " ".join(name.split()).lower()


def mode_key(mode: str) -> str:
    """The DMX mode as a key: spacing and case do not count."""
    return " ".join(mode.split()).lower()


def type_key(spec: str, mode: str) -> str:
    """The key of a fixture type in forms and in the API: GDTF file and mode."""
    return f"{spec_key(spec)}|{mode_key(mode)}"


def names_from_spec(spec: str) -> tuple[str, str]:
    """Manufacturer and model as the GDTF file name tells them.

    The GDTF Share names its files ``Manufacturer@Model@Revision.gdtf``:
    ``Robe_Lighting@Robin_T1_Profile.gdtf`` gives ("Robe Lighting", "Robin
    T1 Profile"). A name without "@" is taken as the model.
    """
    name = PurePosixPath(spec.replace("\\", "/").strip()).name
    if name.lower().endswith(".gdtf"):
        name = name[:-5]
    parts = [" ".join(part.replace("_", " ").split()) for part in name.split("@")]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return "", parts[0]


@dataclass
class FixtureType:
    """One type of the plot: a GDTF file in one mode, and how often it occurs."""

    spec: str
    mode: str
    manufacturer: str
    model: str
    count: int = 0
    #: The kind of object in the MVR file, e.g. "Fixture" or "Truss".
    element: str = "Fixture"
    #: Fixture IDs and names of the first few, to recognise the type.
    examples: list[str] = field(default_factory=list)
    #: Whether manufacturer and model come from the GDTF file itself.
    named_by_gdtf: bool = False

    @property
    def key(self) -> str:
        """The key of the type, see :func:`type_key`."""
        return type_key(self.spec, self.mode)

    @property
    def label(self) -> str:
        """Manufacturer and model, e.g. "Robe Lighting Robin T1 Profile"."""
        return " ".join(part for part in (self.manufacturer, self.model) if part) or self.spec

    def as_dict(self) -> dict[str, Any]:
        """The type as plain data, for the session and the API."""
        return {
            "key": self.key,
            "gdtf_spec": self.spec,
            "mode": self.mode,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "label": self.label,
            "count": self.count,
            "element": self.element,
            "examples": self.examples,
            "named_by_gdtf": self.named_by_gdtf,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FixtureType:
        """The type from :meth:`as_dict`."""
        return cls(
            spec=data["gdtf_spec"],
            mode=data["mode"],
            manufacturer=data["manufacturer"],
            model=data["model"],
            count=int(data["count"]),
            element=data.get("element", "Fixture"),
            examples=list(data.get("examples", [])),
            named_by_gdtf=bool(data.get("named_by_gdtf")),
        )


@dataclass
class Plot:
    """What an MVR file contains, counted per fixture type."""

    file_name: str
    types: list[FixtureType]
    #: Objects of the scene without GDTF file (trusses as plain geometry, people, set pieces).
    skipped: int = 0

    @property
    def fixture_count(self) -> int:
        """All counted objects."""
        return sum(fixture_type.count for fixture_type in self.types)

    def type(self, key: str) -> FixtureType | None:
        """The type with this key, if the plot has it."""
        return next((fixture_type for fixture_type in self.types if fixture_type.key == key), None)

    def as_dict(self) -> dict[str, Any]:
        """The plot as plain data, for the session and the API."""
        return {
            "file": self.file_name,
            "fixtures": self.fixture_count,
            "skipped": self.skipped,
            "types": [fixture_type.as_dict() for fixture_type in self.types],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Plot:
        """The plot from :meth:`as_dict`."""
        return cls(
            file_name=data["file"],
            types=[FixtureType.from_dict(entry) for entry in data["types"]],
            skipped=int(data.get("skipped", 0)),
        )


# --- Reading the archive safely ------------------------------------------------------------------


class _DeclarationError(Exception):
    """The XML declares a document type."""


class _SafeTreeBuilder(ET.TreeBuilder):
    """A tree builder that stops at a document type declaration (defence in depth, see :func:`parse_xml`)."""

    def doctype(self, name: str, pubid: str | None, system: str | None) -> None:
        """Refuse every DTD: entity declarations live in it."""
        raise _DeclarationError(name)


_DECLARATION = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)


def parse_xml(raw: bytes) -> ET.Element:
    """Parse XML that came from outside, refusing document type declarations.

    Python's own XML parser expands entities, so a few hundred bytes of
    nested entity declarations would grow to gigabytes. MVR and GDTF never
    use a DTD; a file with one is refused before parsing. Files in an
    encoding other than UTF-8 (UTF-16 shows as zero bytes) would hide the
    declaration from that check, so they are refused too – MVR prescribes
    UTF-8 – and the parser stops at any declaration that still gets
    through.

    Raises:
        ValidationError: The XML is not acceptable or not readable.
    """
    if _DECLARATION.search(raw):
        raise _error(_("The file contains a document type declaration, which is not accepted for safety reasons."))
    if b"\x00" in raw[:4]:
        raise _error(_("The XML file is not in UTF-8."))
    parser = ET.XMLParser(target=_SafeTreeBuilder())  # noqa: S314 - DTDs refused above and in the builder
    try:
        parser.feed(raw)
        return parser.close()
    except _DeclarationError as error:
        raise _error(
            _("The file contains a document type declaration, which is not accepted for safety reasons.")
        ) from error
    except ET.ParseError as error:
        raise _error(_("The XML of the file cannot be read: %(error)s") % {"error": error}) from error


def _check_archive(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    """Refuse archives with too many files or too much content before anything is unpacked."""
    members = archive.infolist()
    if len(members) > MAX_MEMBERS:
        raise _error(_("The archive contains more than %(count)s files.") % {"count": MAX_MEMBERS})
    if sum(member.file_size for member in members) > MAX_UNPACKED_BYTES:
        raise _error(_("Unpacked, the archive would be larger than %(size)s MB.") % {"size": MAX_UNPACKED_BYTES >> 20})
    return members


def _read_member(archive: zipfile.ZipFile, member: zipfile.ZipInfo, limit: int) -> bytes:
    """Unpack one file of an archive, at most ``limit`` bytes – whatever its header claims.

    Raises:
        ValidationError: The file is larger, encrypted or damaged.
    """
    if member.file_size > limit:
        raise _error(
            _("The file %(name)s in the archive is larger than %(size)s MB.")
            % {"name": member.filename, "size": limit >> 20}
        )
    try:
        with archive.open(member) as handle:
            data = handle.read(limit + 1)
    except (zipfile.BadZipFile, zlib.error, NotImplementedError, RuntimeError, OSError, EOFError) as error:
        raise _error(_("The file %(name)s in the archive cannot be read.") % {"name": member.filename}) from error
    if len(data) > limit:
        raise _error(
            _("The file %(name)s in the archive is larger than %(size)s MB.")
            % {"name": member.filename, "size": limit >> 20}
        )
    return data


def _open_archive(source: IO[bytes]) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(source)
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, EOFError) as error:
        raise _error(_("The file is not an MVR file: MVR files are ZIP archives.")) from error


def local(tag: Any) -> str:
    """The name of an XML element without namespace: ``{urn:x}Fixture`` → ``Fixture``."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def value_of(element: ET.Element, name: str) -> str:
    """An attribute or child element of an object, whichever the file uses; any case, any namespace."""
    wanted = name.lower()
    for attribute, text in element.attrib.items():
        if local(attribute).lower() == wanted:
            return text.strip()
    for child in element:
        if local(child.tag).lower() == wanted:
            return (child.text or "").strip()
    return ""


def _children(element: ET.Element, name: str) -> Iterator[ET.Element]:
    return (child for child in element if local(child.tag) == name)


def _objects(element: ET.Element) -> Iterator[ET.Element]:
    """All objects below a layer: the content of its ChildList, and of the ChildLists of groups (GroupObject)."""
    for child_list in _children(element, "ChildList"):
        for child in child_list:
            yield child
            # Groups hold objects in a ChildList of their own; MVR 1.6 allows that for other objects too.
            yield from _objects(child)


def read_plot(source: IO[bytes], file_name: str) -> Plot:
    """Read an MVR file and count its fixtures per type (PRJ-077).

    Args:
        source: The file, opened for reading in binary mode and seekable.
        file_name: The name of the file, for messages and the group name.

    Raises:
        ValidationError: The file is no MVR file, too large, unsafe, or holds no fixture with a GDTF file.
    """
    archive = _open_archive(source)
    with archive:
        members = _check_archive(archive)
        scenes = [member for member in members if PurePosixPath(member.filename).name.lower() == SCENE_FILE]
        if not scenes:
            raise _error(_("The file contains no GeneralSceneDescription.xml, so it is not an MVR file."))
        scene_file = min(scenes, key=lambda member: member.filename.count("/"))
        root = parse_xml(_read_member(archive, scene_file, MAX_SCENE_BYTES))
        if local(root.tag) != "GeneralSceneDescription":
            raise _error(_("The scene description of the file is not one of MVR."))
        types: dict[str, FixtureType] = {}
        skipped = 0
        for scene in _children(root, "Scene"):
            for layers in _children(scene, "Layers"):
                for layer in _children(layers, "Layer"):
                    for element in _objects(layer):
                        kind = local(element.tag)
                        if kind not in EQUIPMENT:
                            continue  # groups (their content comes on its own), focus points
                        spec = value_of(element, "GDTFSpec")
                        if not spec:
                            skipped += 1
                            continue
                        mode = value_of(element, "GDTFMode")
                        key = type_key(spec, mode)
                        fixture_type = types.get(key)
                        if fixture_type is None:
                            manufacturer, model = names_from_spec(spec)
                            fixture_type = types[key] = FixtureType(spec, mode, manufacturer, model, element=kind)
                        fixture_type.count += 1
                        if len(fixture_type.examples) < EXAMPLES:
                            example = " ".join(
                                part for part in (value_of(element, "FixtureID"), value_of(element, "name")) if part
                            )
                            if example:
                                fixture_type.examples.append(example)
        if not types:
            raise _error(_("The plot contains no fixture with a GDTF file."))
        _name_from_gdtf(archive, members, types.values())
    ordered = sorted(types.values(), key=lambda fixture_type: (fixture_type.label.lower(), mode_key(fixture_type.mode)))
    return Plot(file_name=file_name, types=ordered, skipped=skipped)


def _name_from_gdtf(archive: zipfile.ZipFile, members: list[zipfile.ZipInfo], types: Any) -> None:
    """Take manufacturer and model from the GDTF files in the archive, where they can be read.

    A GDTF file is a ZIP archive itself; its ``description.xml`` names the
    type: ``<FixtureType Manufacturer="Robe Lighting" LongName="Robin T1
    Profile" Name="T1 Profile">``. Whatever cannot be read keeps the name
    from the file name – the plot is usable all the same.
    """
    by_key = {spec_key(member.filename): member for member in members if member.filename.lower().endswith(".gdtf")}
    budget = MAX_GDTF_TOTAL_BYTES
    names: dict[str, tuple[str, str] | None] = {}
    for fixture_type in types:
        key = spec_key(fixture_type.spec)
        if key not in names:
            names[key] = None
            member = by_key.get(key)
            if member is not None and member.file_size <= min(MAX_GDTF_BYTES, budget):
                budget -= member.file_size
                try:
                    names[key] = _gdtf_names(_read_member(archive, member, MAX_GDTF_BYTES))
                except ValidationError:
                    names[key] = None
        found = names[key]
        if found is not None:
            fixture_type.manufacturer = found[0] or fixture_type.manufacturer
            fixture_type.model = found[1] or fixture_type.model
            fixture_type.named_by_gdtf = True


def _gdtf_names(data: bytes) -> tuple[str, str] | None:
    """Manufacturer and model from the ``description.xml`` of a GDTF file, or ``None``."""
    archive = _open_archive(io.BytesIO(data))
    with archive:
        members = _check_archive(archive)
        description = next((member for member in members if member.filename.lower() == "description.xml"), None)
        if description is None:
            return None
        root = parse_xml(_read_member(archive, description, MAX_DESCRIPTION_BYTES))
    fixture = next((child for child in root if local(child.tag) == "FixtureType"), None)
    if fixture is None:
        return None
    manufacturer = value_of(fixture, "Manufacturer")
    model = value_of(fixture, "LongName") or value_of(fixture, "Name")
    return (manufacturer, model) if manufacturer or model else None


# --- Suggestions -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Text:
    """A name prepared for comparing: its words and its letters without spaces.

    Letters and digits count as separate words, so "T1", "T-1" and "T 1"
    all hold the words ``t`` and ``1``.
    """

    #: The words in their order.
    tokens: tuple[str, ...]

    @classmethod
    def of(cls, text: str) -> Text:
        """Prepare a text."""
        return cls(tuple(re.findall(r"[a-z]+|\d+", fold(text))))

    @cached_property
    def words(self) -> frozenset[str]:
        """The words as a set."""
        return frozenset(self.tokens)

    @cached_property
    def compact(self) -> str:
        """The letters and digits without spaces: "Sky Panel S60-C" is ``skypanels60c``."""
        return "".join(self.tokens)

    @cached_property
    def numbers(self) -> frozenset[str]:
        """The numbers in the name; they tell models apart."""
        return frozenset(token for token in self.tokens if token.isdigit())

    @cached_property
    def anchors(self) -> frozenset[str]:
        """Words for finding candidates at all: those of two letters or more, and a letter with its number.

        "T-1", "T 1" and "T1" all have the anchor ``t1``.
        """
        anchors = {token for token in self.tokens if len(token) >= 2}
        anchors.update(
            first + second for first, second in itertools.pairwise(self.tokens) if first.isalpha() != second.isalpha()
        )
        return frozenset(anchors)

    def without(self, words: frozenset[str]) -> Text:
        """The text without some words, e.g. without the name of the manufacturer; never empty."""
        rest = tuple(token for token in self.tokens if token not in words)
        return Text(rest) if rest else self


def similarity(wanted: Text, other: Text) -> float:
    """How much ``other`` resembles the name ``wanted``, from 0 to 1 (PRJ-077).

    Three parts count the same: the share of common words (Dice
    coefficient), the likeness of the letters without spaces (``difflib``),
    and how many words of ``wanted`` occur in ``other``. So "Robin T1
    Profile" against "T1 Profile Robin" and "SkyPanel S60-C" against "Sky
    Panel S60C" come out high, and "MAC Aura XB Washlight" beats "MAC Aura"
    for "MAC Aura XB". Numbers tell models apart: if each name has a number
    the other lacks ("S30" and "S60", "Source Four 26°" and "36°"), 30
    points are taken off, so such a product is offered but not preselected.
    """
    if not wanted.tokens or not other.tokens:
        return 0.0
    common = wanted.words & other.words
    words = 2 * len(common) / (len(wanted.words) + len(other.words))
    letters = difflib.SequenceMatcher(None, wanted.compact, other.compact, autojunk=False).ratio()
    covered = len(common) / len(wanted.words)
    score = (words + letters + covered) / 3
    if wanted.numbers - other.numbers and other.numbers - wanted.numbers:
        score -= 0.3
    return max(score, 0.0)


@dataclass
class Suggestion:
    """A product proposed for a fixture type."""

    product_id: int
    article_number: str
    name: str
    #: Similarity in percent; 100 for a remembered choice.
    score: int
    #: ``remembered`` (this type in this mode), ``remembered_mode`` (this type in another mode) or ``similar``.
    source: str
    #: What resembled the type, e.g. "model Robe Robin T1 Profile".
    reason: str = ""

    @property
    def label(self) -> str:
        """Article number and name, as in the product search."""
        return f"{self.article_number} {self.name}"

    @property
    def preselected(self) -> bool:
        """Whether the suggestion is good enough to be chosen without asking."""
        return self.source != "similar" or self.score >= PRESELECT_SCORE

    def as_dict(self) -> dict[str, Any]:
        """The suggestion as plain data, for the API."""
        return {
            "product": self.product_id,
            "article_number": self.article_number,
            "name": self.name,
            "score": self.score,
            "source": self.source,
            "reason": self.reason,
        }


@dataclass
class _Candidate:
    product_id: int
    text: Text
    manufacturer: Text | None
    reason: str


def _candidates() -> tuple[dict[int, Product], list[_Candidate]]:
    """All active products, and what a fixture type is compared with: names of equipment and its models.

    Customer material (PRD-043) is no candidate: it belongs to one customer, a mapping is for every plot.
    """
    products = {
        product.pk: product
        for product in Product.objects.filter(is_active=True, owner__isnull=True).only(
            "pk", "article_number", "name", "kind"
        )
    }
    equipment = [product for product in products.values() if product.kind not in NOT_EQUIPMENT]
    candidates = [_Candidate(product.pk, Text.of(product.name), None, "") for product in equipment]
    models = MaterialModel.objects.filter(default_product_id__in=[product.pk for product in equipment]).select_related(
        "manufacturer"
    )
    for model in models.only("name", "short_name", "default_product_id", "manufacturer__name"):
        manufacturer = model.manufacturer.name if model.manufacturer else ""
        reason = _("model %(name)s") % {"name": " ".join(part for part in (manufacturer, model.name) if part)}
        maker = Text.of(manufacturer) if manufacturer else None
        for text in {model.name, model.short_name, f"{manufacturer} {model.name}".strip()}:
            if text:
                candidates.append(_Candidate(model.default_product_id, Text.of(text), maker, reason))
    return products, candidates


def _similar(
    fixture_type: FixtureType,
    candidates: list[_Candidate],
    index: dict[str, list[int]],
) -> dict[int, tuple[float, str]]:
    """The best similarity per product for one fixture type, with what matched.

    The model names are compared without the words of the manufacturer, so
    that "Ayrton Diablo" is not taken for "Ayrton Domino". The manufacturer
    counts on its own: named in the product or set at the material model,
    it adds 10 points; a different manufacturer at the model takes 15 off.
    """
    maker = Text.of(fixture_type.manufacturer)
    maker_words = frozenset(word for word in maker.words if len(word) >= 3)
    model = Text.of(fixture_type.model).without(maker_words)
    # Only candidates that share a word worth the name are compared at all.
    anchors = model.anchors | Text.of(fixture_type.label).anchors
    positions = {position for anchor in anchors for position in index.get(anchor, ())}
    best: dict[int, tuple[float, str]] = {}
    for position in sorted(positions):
        candidate = candidates[position]
        score = similarity(model, candidate.text.without(maker_words))
        if candidate.manufacturer is not None and maker_words:
            shared = maker_words & candidate.manufacturer.words
            agreement = 1.0 if shared else similarity(maker, candidate.manufacturer)
            if agreement >= 0.6:
                score += 0.1
            elif agreement < 0.3:
                score -= 0.15
        elif maker_words & candidate.text.words:
            score += 0.1
        score = min(max(score, 0.0), 1.0)
        if score > best.get(candidate.product_id, (0.0, ""))[0]:
            best[candidate.product_id] = (score, candidate.reason)
    return best


def suggest(types: list[FixtureType]) -> dict[str, list[Suggestion]]:
    """Propose products for fixture types, the best first (PRJ-077).

    A product chosen for the same type before comes first (score 100);
    then the most similar products with at least :data:`OFFER_SCORE`
    percent, up to :data:`OFFERED` in all.

    Returns:
        ``{type key: [suggestions]}``; an empty list where nothing fits.
    """
    products, candidates = _candidates()
    index: dict[str, list[int]] = {}
    for position, candidate in enumerate(candidates):
        for anchor in candidate.text.anchors:
            index.setdefault(anchor, []).append(position)
    remembered: dict[tuple[str, str], FixtureTypeMapping] = {}
    # PRD-044: a remembered service is no longer offered – it is planned with the crew.
    plannable = [pk for pk, product in products.items() if product.kind not in CREW_ONLY_KINDS | LOGISTICS_KINDS]
    for mapping in FixtureTypeMapping.objects.filter(
        gdtf_spec__in={spec_key(fixture_type.spec) for fixture_type in types}, product_id__in=plannable
    ).order_by("updated_at"):
        remembered[(mapping.gdtf_spec, mapping.gdtf_mode)] = mapping
        remembered[(mapping.gdtf_spec, "*")] = mapping  # the latest for any mode

    result: dict[str, list[Suggestion]] = {}
    for fixture_type in types:
        offered: list[Suggestion] = []
        spec = spec_key(fixture_type.spec)
        mapping = remembered.get((spec, mode_key(fixture_type.mode)))
        source = "remembered"
        if mapping is None:
            mapping, source = remembered.get((spec, "*")), "remembered_mode"
        if mapping is not None:
            product = products[mapping.product_id]
            offered.append(Suggestion(product.pk, product.article_number or "", product.name, 100, source))
        ranked = sorted(_similar(fixture_type, candidates, index).items(), key=lambda entry: (-entry[1][0], entry[0]))
        for product_id, (score, reason) in ranked:
            if len(offered) >= OFFERED or score * 100 < OFFER_SCORE:
                break
            if any(suggestion.product_id == product_id for suggestion in offered):
                continue
            product = products[product_id]
            offered.append(
                Suggestion(
                    product.pk, product.article_number or "", product.name, round(score * 100), "similar", reason
                )
            )
        result[fixture_type.key] = offered
    return result


def preselection(suggestions: list[Suggestion]) -> Suggestion | None:
    """The suggestion that is chosen unless the user decides otherwise: remembered, or similar enough."""
    first = suggestions[0] if suggestions else None
    return first if first is not None and first.preselected else None


# --- Adding the lines ---------------------------------------------------------------------------------


@dataclass
class Choice:
    """What to do with one fixture type: which product, how many."""

    product: Product
    quantity: Decimal


@dataclass
class TakeOverResult:
    """What :func:`take_over` added."""

    group: Group | None
    lines: list[services.LineResult] = field(default_factory=list)
    #: "… was added, but 2 piece(s) are missing in this period." and the like (PRJ-013) – the shortages only for
    #: whom may see the availability of material (AUT-032).
    warnings: list[str] = field(default_factory=list)


def kept_file_name(file_name: str, moment: datetime.datetime | None = None) -> str:
    """The name an imported MVR file gets in the files of the project (PRJ-086).

    The local date and time of the import come first, so that the plots of a
    project stand in the order they came in and never clash:
    ``20261013-221530_Rig Stadtfest.mvr``.
    """
    local = timezone.localtime(moment or timezone.now())
    name = PurePosixPath(file_name.replace("\\", "/")).name or "plot.mvr"
    return f"{local:%Y%m%d-%H%M%S}_{name}"[:255]


def keep_file(project: Project, uploaded: Any, *, user: Any) -> ProjectFile:
    """Keep an imported MVR file in the files of the project (PRJ-086).

    Stored like any file of the project (PRJ-007, NFA-007): without a
    document type and not visible to the crew – the planner can change both
    in the files on the tab "Documents" (PRJ-079).

    Raises:
        ValidationError: The project is closed, or the file is larger than
            files of projects may be.
    """
    if hasattr(uploaded, "seek"):
        uploaded.seek(0)
    return add_file(project, File(uploaded, name=kept_file_name(getattr(uploaded, "name", "") or "")), user=user)


def default_group_name(file_name: str) -> str:
    """The name of the new group: "MVR" and the file name without ``.mvr``."""
    stem = PurePosixPath(file_name.replace("\\", "/")).name
    if stem.lower().endswith(".mvr"):
        stem = stem[:-4]
    return f"MVR {stem}".strip()[:120]


def take_over(
    project: Project,
    plot: Plot,
    choices: dict[str, Choice],
    *,
    rights: Rights,
    group: Group | None = None,
    new_group_name: str = "",
    remember: bool = True,
) -> TakeOverResult:
    """Add a material line for every fixture type with a chosen product (PRJ-077).

    All lines are added or none: a deactivated product, say, stops the whole
    step. Each line goes through ``services.add_line``, so availability,
    prices and the customer's discount are those of every other line.

    Args:
        project: The project; the caller has checked the right to edit it.
        plot: The plot read by :func:`read_plot`.
        choices: ``{type key: choice}``; types without choice are skipped.
        rights: The rights of the caller.
        group: An existing group of the project to add the lines to.
        new_group_name: Create a group of this name for the lines instead;
            both empty: the lines go to "without group".
        remember: Remember the products for the types (:class:`FixtureTypeMapping`).

    Raises:
        ValidationError: No product chosen, the project is closed, or a line cannot be added.
    """
    chosen = [(fixture_type, choices[fixture_type.key]) for fixture_type in plot.types if fixture_type.key in choices]
    if not chosen:
        raise ValidationError(_("Choose a product for at least one fixture type."), code="nothing_chosen")
    if group is not None and group.project_id != project.pk:
        raise ValidationError(_("The group belongs to another project."), code="invalid")
    with transaction.atomic():
        if group is None and new_group_name.strip():
            group = services.add_group(project, rights=rights, name=new_group_name.strip()[:120])
        result = TakeOverResult(group=group)
        sees_shortage = rights.has(SpecialRight.AVAILABILITY)  # AUT-032 (availability as a special right)
        for fixture_type, choice in chosen:
            line = services.add_line(
                project, rights=rights, product=choice.product, quantity=choice.quantity, group=group
            )
            result.lines.append(line)
            if sees_shortage and line.availability.status == "short":
                result.warnings.append(
                    ngettext(
                        "%(title)s was added, but %(count)d piece is missing in this period.",
                        "%(title)s was added, but %(count)d pieces are missing in this period.",
                        plural_of(line.availability.shortage_total),
                    )
                    % {"title": line.line.title, "count": line.availability.shortage_total}
                )
            if remember:
                FixtureTypeMapping.objects.update_or_create(
                    gdtf_spec=spec_key(fixture_type.spec),
                    gdtf_mode=mode_key(fixture_type.mode),
                    defaults={
                        "product": choice.product,
                        "label": fixture_type.label[:250],
                        "updated_at": timezone.now(),
                    },
                )
    return result
