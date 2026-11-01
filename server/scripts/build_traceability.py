#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build ``docs/dev/traceability.md``: which requirement is implemented and tested where (NFA-057).

Every business rule in the code names the requirement it implements, e.g.
"VFG-002". This script collects those mentions and sets them against the
requirements catalogue::

    python scripts/build_traceability.py           # write the file
    python scripts/build_traceability.py --check   # fail if the file is out of date

The result has one row per requirement of the stages built so far, with the
places in the code and the tests that mention it. Requirements of these
stages that nothing mentions are listed separately – as a to-do list, or as
a reminder to add the missing reference.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOGUE = ROOT / "docs" / "anforderungen" / "Rentalars_Anforderungskatalog.md"
TARGET = ROOT / "docs" / "dev" / "traceability.md"

#: The stages that are implemented; requirements of later stages are only counted.
BUILT_STAGES = ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9")

REQUIREMENT_LINE = re.compile(r"^- ([A-Z]{3}-\d{3}) \[(MUSS|SOLL|KANN) · ([VA]) · (S\d+)\] (.*)$")
REQUIREMENT_ID = re.compile(r"\b([A-Z]{3}-\d{3})\b")

#: Where requirement IDs are looked for, and under which heading they are reported.
CODE_FOLDERS = ("rentalars", "templates", "static/js", "static/css", "deploy", "scripts")
TEST_FOLDERS = ("tests",)
#: Requirements about documentation and process are met by documents, not by code.
DOCUMENT_PATHS = ("docs/dev", "docs/betrieb", "docs/handbuch", "README.md", "CHANGELOG.md", "pyproject.toml", ".github")
SKIPPED_PARTS = {"migrations", "__pycache__", "vendor"}
TEXT_SUFFIXES = {
    ".py",
    ".html",
    ".txt",
    ".js",
    ".css",
    ".sh",
    ".conf",
    ".cnf",
    ".service",
    ".timer",
    ".example",
    ".md",
    ".toml",
    ".yml",
    "",
}


def read_requirements() -> dict[str, dict[str, str]]:
    """Read ID, priority, stage and the first sentence of every requirement from the catalogue."""
    requirements: dict[str, dict[str, str]] = {}
    lines = CATALOGUE.read_text(encoding="utf-8").splitlines()
    for number, line in enumerate(lines):
        match = REQUIREMENT_LINE.match(line)
        if not match:
            continue
        identifier, priority, origin, stage, text = match.groups()
        # A requirement runs over several indented lines; take enough for a short summary.
        for following in lines[number + 1 : number + 4]:
            if not following.startswith("  "):
                break
            text += " " + following.strip()
        summary = re.split(r"(?<=[.:;])\s", text, maxsplit=1)[0]
        requirements[identifier] = {"priority": priority, "origin": origin, "stage": stage, "summary": summary[:150]}
    return requirements


def find_mentions(folders: tuple[str, ...]) -> dict[str, list[str]]:
    """Return for each requirement ID the files (below the given folders) that mention it."""
    mentions: dict[str, set[str]] = defaultdict(set)
    for folder in folders:
        start = ROOT / folder
        candidates = [start] if start.is_file() else sorted(start.rglob("*"))
        for path in candidates:
            if not path.is_file() or path.suffix not in TEXT_SUFFIXES or SKIPPED_PARTS & set(path.parts):
                continue
            if path == TARGET:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for identifier in set(REQUIREMENT_ID.findall(text)):
                mentions[identifier].add(str(path.relative_to(ROOT)))
    return {identifier: sorted(files) for identifier, files in mentions.items()}


def shorten(files: list[str], limit: int = 4) -> str:
    """Show a few file names and say how many more there are."""
    shown = ", ".join(f"`{name}`" for name in files[:limit])
    return shown + (f" and {len(files) - limit} more" if len(files) > limit else "")


def build() -> str:
    """Build the text of the traceability file."""
    requirements = read_requirements()
    in_code = find_mentions(CODE_FOLDERS)
    in_tests = find_mentions(TEST_FOLDERS)
    in_documents = find_mentions(DOCUMENT_PATHS)
    named = set(in_code) | set(in_tests) | set(in_documents)

    # Since catalogue 0.33 stage S10 has built requirements (SOLL) next to those only kept as KANN.
    built = {
        key: value
        for key, value in requirements.items()
        if value["stage"] in BUILT_STAGES or (value["stage"] == "S10" and value["priority"] != "KANN")
    }
    referenced = [key for key in built if key in named]
    unreferenced = [key for key in built if key not in named]
    # Things that merely look like an ID ("SHA-256") are not reported as unknown.
    areas_of_catalogue = {key.split("-")[0] for key in requirements}
    unknown = sorted(key for key in named - set(requirements) if key.split("-")[0] in areas_of_catalogue)

    out = [
        "# Traceability: requirements, code and tests",
        "",
        "Generated by `scripts/build_traceability.py` – do not edit by hand. `scripts/check.sh` fails if this",
        "file is out of date.",
        "",
        "Each row is one requirement of the catalogue (`docs/anforderungen/Rentalars_Anforderungskatalog.md`)",
        "from the stages built so far (in S10 those that are not KANN), with the files that name it. The",
        "summaries are quoted from the",
        "catalogue and therefore German. To find the exact place, search the file for the ID (NFA-057).",
        "",
        f"- Requirements in the catalogue: {len(requirements)}",
        f"- Of these built (stages {', '.join(BUILT_STAGES[:-1])} and {BUILT_STAGES[-1]}, and the SOLL of S10): {len(built)}",
        f"- Named in code, tests or documents: {len(referenced)}",
        f"- Not named anywhere: {len(unreferenced)} (listed at the end)",
        "",
    ]
    areas: dict[str, list[str]] = defaultdict(list)
    for key in built:
        areas[key.split("-")[0]].append(key)
    for area in sorted(areas):
        out += [
            f"## {area}",
            "",
            "| ID | Priority | Stage | Requirement (catalogue) | Code | Tests | Documents |",
            "|---|---|---|---|---|---|---|",
        ]
        for key in sorted(areas[area]):
            requirement = built[key]
            out.append(
                f"| {key} | {requirement['priority']} | {requirement['stage']} | {requirement['summary'].replace('|', '/')} "
                f"| {shorten(in_code.get(key, [])) or '–'} | {shorten(in_tests.get(key, [])) or '–'} "
                f"| {shorten(in_documents.get(key, []), 2) or '–'} |"
            )
        out.append("")

    out += ["## Requirements of the built stages that nothing names", ""]
    if unreferenced:
        out += [
            "These are either implemented without a reference (then the reference is missing) or still open.",
            "See `docs/dev/decisions.md` for the known gaps.",
            "",
            "| ID | Priority | Stage | Requirement (catalogue) |",
            "|---|---|---|---|",
        ]
        out += [
            f"| {key} | {built[key]['priority']} | {built[key]['stage']} | {built[key]['summary'].replace('|', '/')} |"
            for key in sorted(unreferenced)
        ]
    else:
        out.append("None.")
    out.append("")
    if unknown:
        out += ["## IDs named in the code that the catalogue does not contain", "", ", ".join(unknown), ""]
    return "\n".join(out)


def main() -> int:
    """Write the file, or compare it with what would be written."""
    text = build()
    if "--check" in sys.argv:
        if not TARGET.is_file() or TARGET.read_text(encoding="utf-8") != text:
            print("docs/dev/traceability.md is out of date. Run: python scripts/build_traceability.py")
            return 1
        print("Traceability file is up to date.")
        return 0
    TARGET.write_text(text, encoding="utf-8")
    print(f"Wrote {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
