#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check that every library Rentalars ships with has a licence compatible with GPL-3.0-or-later (NFA-053).

Run it inside the Python environment of the project::

    python scripts/check_licenses.py            # check, exit code 1 if something is wrong
    python scripts/check_licenses.py --markdown # print the table for THIRD-PARTY.md

What is checked

* every library named in ``requirements.txt``: its licence is read from the
  installed package and must be on the list of accepted licences below;
* every bundled front-end file in ``static/vendor`` and ``static/fonts``: it
  must be listed in ``BUNDLED_FILES`` and its licence text must lie next to it;
* ``THIRD-PARTY.md``: it must name every library with the version and licence
  found here, so that the file in the package cannot fall behind.

A library whose licence cannot be recognised fails the check on purpose: a
person has to look at it and either add its licence to the list or replace
the library. Licences that add conditions beyond the GPL – above all the
AGPL – are rejected (catalogue NFA-053).
"""

from __future__ import annotations

import importlib.metadata
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Licences that may be combined with a program under GPL-3.0-or-later.
#: Keys are lower-case fragments looked for in the licence text of a package.
ACCEPTED = {
    "bsd": "BSD",
    "mit": "MIT",
    "isc": "ISC",
    "0bsd": "0BSD",
    "apache-2.0": "Apache-2.0",
    "apache software license": "Apache-2.0",
    "psf-2.0": "PSF-2.0",
    "python software foundation": "PSF-2.0",
    "gpl-2.0-or-later": "GPL-2.0-or-later",
    "gplv2+": "GPL-2.0-or-later",
    "gpl-3.0": "GPL-3.0",
    # LGPL may be combined with GPL-3.0-or-later; ldap3 (login with LDAP, AUT-029) is LGPL-3.0.
    "lgpl": "LGPL",
    "mpl": "MPL",
    "ofl": "OFL-1.1",
    "hpnd": "HPND",
    "mit-cmu": "MIT-CMU (HPND)",
    "mit-0": "MIT-0",
}

#: Fragments that make a licence unacceptable, whatever else it says.
REJECTED = ("agpl", "affero", "sspl", "server side public", "commons clause", "proprietary", "busl", "business source")

#: Front-end files shipped inside the package: file pattern -> (name, licence, licence file).
BUNDLED_FILES = {
    "static/vendor/htmx.min.js": ("htmx", "0BSD", "static/vendor/htmx.LICENSE"),
    "static/vendor/sortable.min.js": ("SortableJS", "MIT", "static/vendor/sortable.LICENSE"),
    # UIX-034: the map at addresses – script, style sheet and its pictures, from npm (leaflet@1.9.4).
    "static/vendor/leaflet/**/*.*": ("Leaflet", "BSD-2-Clause", "static/vendor/leaflet/LICENSE"),
    "static/fonts/*.woff2": ("Barlow (font family)", "OFL-1.1", "static/fonts/OFL.txt"),
    # MAT-065: the font of the labels small, large and cable – Arial's metrics, shipped unmodified.
    "static/fonts/LiberationSans-Regular.ttf": (
        "Liberation Sans (font)",
        "OFL-1.1",
        "static/fonts/LiberationSans-OFL.txt",
    ),
}


def required_packages() -> list[str]:
    """Return the package names listed in ``requirements.txt``."""
    names = []
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
            names.append(re.split(r"[=<>!~ \[]", line, maxsplit=1)[0])
    return names


def licence_text_of(package: str) -> str:
    """Collect everything the installed package says about its licence."""
    metadata = importlib.metadata.metadata(package)
    parts = [metadata.get("License-Expression") or "", (metadata.get("License") or "").splitlines()[0:1]]
    classifiers = [value for value in metadata.get_all("Classifier") or [] if value.startswith("License ::")]
    flat = [parts[0], *parts[1], *classifiers]
    return " | ".join(part for part in flat if part)


def judge(text: str) -> tuple[bool, str]:
    """Return whether a licence text is acceptable and the recognised licence names."""
    lowered = text.lower()
    if any(fragment in lowered for fragment in REJECTED):
        return False, text
    # Whole words only: "mit" must not be found inside "limited".
    recognised = sorted(
        {
            name
            for fragment, name in ACCEPTED.items()
            if re.search(rf"(?<![a-z0-9]){re.escape(fragment)}(?![a-z])", lowered)
        }
    )
    return bool(recognised), ", ".join(recognised) if recognised else text or "unknown"


def check_packages() -> tuple[list[tuple[str, str, str]], list[str]]:
    """Check the Python libraries; return table rows and problems."""
    rows, problems = [], []
    for package in required_packages():
        try:
            version = importlib.metadata.version(package)
            text = licence_text_of(package)
        except importlib.metadata.PackageNotFoundError:
            problems.append(f"{package}: not installed – run 'pip install -r requirements.txt' first")
            continue
        accepted, licence = judge(text)
        rows.append((package, version, licence))
        if not accepted:
            problems.append(
                f"{package} {version}: licence not accepted or not recognised: {text or 'no licence stated'}"
            )
    return rows, problems


def check_bundled_files() -> tuple[list[tuple[str, str, str]], list[str]]:
    """Check the front-end files shipped in ``static``; return table rows and problems."""
    rows, problems = [], []
    known_files: set[Path] = set()
    for pattern, (name, licence, licence_file) in BUNDLED_FILES.items():
        matches = sorted(ROOT.glob(pattern))
        known_files.update(matches)
        if not matches:
            problems.append(f"{pattern}: listed as bundled but not found")
        if not (ROOT / licence_file).is_file():
            problems.append(f"{name}: the licence text {licence_file} is missing")
        known_files.add(ROOT / licence_file)
        rows.append((name, pattern, licence))
    for folder in ("static/vendor", "static/fonts"):
        # Files in sub-folders count as well (Leaflet brings its pictures in "images").
        for path in sorted((ROOT / folder).rglob("*")):
            if path.is_file() and path not in known_files:
                problems.append(f"{path.relative_to(ROOT)}: a bundled file that is not listed in BUNDLED_FILES")
    return rows, problems


def markdown_tables(package_rows: list[tuple[str, str, str]], bundled_rows: list[tuple[str, str, str]]) -> str:
    """Return the two tables of THIRD-PARTY.md."""
    lines = ["| Library | Version | Licence |", "|---|---|---|"]
    lines += [f"| {name} | {version} | {licence} |" for name, version, licence in package_rows]
    lines += ["", "| Bundled file | Path | Licence |", "|---|---|---|"]
    lines += [f"| {name} | `{pattern}` | {licence} |" for name, pattern, licence in bundled_rows]
    return "\n".join(lines)


def check_third_party_file(tables: str) -> list[str]:
    """Check that THIRD-PARTY.md names every library with its present version and licence."""
    path = ROOT / "THIRD-PARTY.md"
    if not path.is_file():
        return ["THIRD-PARTY.md is missing"]
    published = path.read_text(encoding="utf-8")
    missing = [line for line in tables.splitlines() if line and line not in published]
    if missing:
        return [
            "THIRD-PARTY.md is out of date; replace its tables with the output of "
            f"'python scripts/check_licenses.py --markdown' (first difference: {missing[0]})"
        ]
    return []


def main() -> int:
    """Run the check and print the result."""
    package_rows, package_problems = check_packages()
    bundled_rows, bundled_problems = check_bundled_files()
    tables = markdown_tables(package_rows, bundled_rows)

    if "--markdown" in sys.argv:
        print(tables)
        return 0

    problems = package_problems + bundled_problems + check_third_party_file(tables)
    for problem in problems:
        print(f"LICENCE PROBLEM  {problem}")
    if problems:
        return 1
    print(f"Licences ok: {len(package_rows)} Python libraries, {len(bundled_rows)} bundled front-end components.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
