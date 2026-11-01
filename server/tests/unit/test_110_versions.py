# SPDX-License-Identifier: GPL-3.0-or-later
"""The version the documents name is the version of the program (UIX-059).

These tests read the files that name the version and fail as soon as one of them is left behind by a new version.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from django.test import SimpleTestCase

import rentalars

ROOT = Path(__file__).resolve().parents[2]


def text(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


class VersionNamedEverywhereTests(SimpleTestCase):
    def test_pyproject_and_package_agree(self) -> None:
        project = tomllib.loads(text("pyproject.toml"))["project"]
        self.assertEqual(project["version"], rentalars.__version__)

    def test_manuals_name_the_version_in_their_headline(self) -> None:
        version = rentalars.__version__
        self.assertIn(f"Version {version}", text("docs/handbuch/benutzerhandbuch.md").split("\n", 5)[2])
        self.assertIn(f"version {version}", text("docs/en/user-manual.md").split("\n", 5)[2])

    def test_manuals_name_the_version_in_the_footer_note(self) -> None:
        version = rentalars.__version__
        self.assertIn(f"„Rentalars {version}“", text("docs/handbuch/benutzerhandbuch.md"))
        self.assertIn(f'"Rentalars {version}"', text("docs/en/user-manual.md"))

    def test_readmes_name_the_version(self) -> None:
        version = rentalars.__version__
        self.assertIn(f"**Version {version}.**", text("README.md"))
        self.assertIn(f"**Version {version}.**", text("docs/en/README.md"))
        for name in ("README.md", "docs/en/README.md"):
            self.assertIn(f"rentalars-{version}.tar.gz", text(name), name)

    def test_changelog_starts_with_this_version(self) -> None:
        headings = re.findall(r"^## (\d+\.\d+\.\d+) – ", text("CHANGELOG.md"), re.MULTILINE)
        self.assertEqual(headings[0], rentalars.__version__)

    def test_update_guides_describe_the_update_command(self) -> None:
        self.assertIn("rentalars update", text("docs/betrieb/aktualisierung.md"))
        self.assertIn("rentalars update", text("docs/en/operations/updating.md"))

    def test_catalogue_names_a_version_and_the_requirements_add_up(self) -> None:
        catalogue = text("docs/anforderungen/Rentalars_Anforderungskatalog.md")
        self.assertRegex(catalogue, re.compile(r"^Version \d+\.\d+ · Stand: ", re.MULTILINE))
        counted = re.findall(r"^- [A-Z]{3}-\d{3} \[(MUSS|SOLL|KANN) · [VA] · S\d+\]", catalogue, re.MULTILINE)
        row = re.search(r"\|\s+alle Stufen\s+\|\s+(\d+) \|\s+(\d+) \|\s+(\d+) \|\s+(\d+) \|", catalogue)
        self.assertIsNotNone(row)
        must, should, could, total = (int(group) for group in row.groups())  # type: ignore[union-attr]
        self.assertEqual((counted.count("MUSS"), counted.count("SOLL"), counted.count("KANN")), (must, should, could))
        self.assertEqual(len(counted), total)
