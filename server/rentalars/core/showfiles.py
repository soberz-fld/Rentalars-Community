# SPDX-License-Identifier: GPL-3.0-or-later
"""Show files of lighting consoles, media servers and sound systems (PRJ-089, NFA-007).

A show file holds what a console or a piece of software was programmed with:
the cues of a lighting desk, the composition of a media server, the scenes
of a mixing desk. Rentalars stores them as project files, so that the
programmer of the next show finds the last state, and the crew sees the file
in the deployment view.

The upload check (NFA-007, ``core.uploads``) lets show files through by the
ending of their name. Every ending below belongs to a data file of its
program; none of them is a program, a script or a page a browser would run,
and project files are always handed out as downloads unless they are PDFs,
pictures or plain text. Shows that are folders (disguise, dLive, Avid VENUE,
Midas PRO …) are uploaded as a ZIP archive, which was allowed before.

Where the endings come from (checked in October 2026):

* from the manufacturers' documentation: ETC Eos ``.esf``, ``.esf2``,
  ``.esf3d``, Cobalt ``.csf``, ColorSource ``.lsf``, USITT ASCII ``.asc``;
  Hog 4 ``.shw``; ChamSys MagicQ ``.shw``, ``.sbk`` (automatic backup),
  ``.xhw`` (show extras), ``.mpr`` (fixture profiles); Yamaha DM7 ``.dm7f``;
  L-Acoustics LA Network Manager ``.preset`` and ``.system``;
* known from practice, without a manufacturer's page at hand: grandMA3
  ``.show``, grandMA2 ``.show.gz``, Avolites Titan ``.avo``, Resolume
  ``.avc``, WATCHOUT ``.watch``, QLab ``.qlab4``/``.qlab5``, Millumin
  ``.millumin``, Yamaha DM3 ``.dm3f``, CL/QL ``.clf``, TF ``.tff``, X32/M32
  ``.scn``, ``.shw``, ``.snp``, ``.chn``, ``.efx``, ``.rou``, DiGiCo ``.ses``,
  d&b R1 ``.dbpr``.

An ending that is missing costs nothing but a ZIP: the show is packed and
uploaded as an archive. Several programs share ``.shw`` (Hog 4, MagicQ,
X32/M32); for such a file the console is chosen by hand.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ShowSystem:
    """A console or a piece of software whose show files are known."""

    name: str
    #: "light", "media" or "sound".
    trade: str
    #: The endings of its show files, lower case with the dot; empty: a folder, uploaded as ZIP.
    extensions: tuple[str, ...] = ()


#: PRJ-089: the usual consoles and programs of event technology, by trade.
SHOW_SYSTEMS: tuple[ShowSystem, ...] = (
    # Light
    ShowSystem("grandMA3", "light", (".show",)),
    ShowSystem("grandMA2", "light", (".show.gz",)),
    ShowSystem("ETC Eos", "light", (".esf", ".esf2", ".esf3d")),
    ShowSystem("ETC Cobalt", "light", (".csf",)),
    ShowSystem("ETC ColorSource", "light", (".lsf",)),
    ShowSystem("USITT ASCII", "light", (".asc",)),
    ShowSystem("Hog 4", "light", (".shw",)),
    ShowSystem("ChamSys MagicQ", "light", (".shw", ".sbk", ".xhw", ".mpr")),
    ShowSystem("Avolites Titan", "light", (".avo",)),
    # Media
    ShowSystem("Resolume Arena", "media", (".avc",)),
    ShowSystem("Resolume Avenue", "media", (".avc",)),
    ShowSystem("WATCHOUT", "media", (".watch",)),
    ShowSystem("QLab", "media", (".qlab4", ".qlab5")),
    ShowSystem("Millumin", "media", (".millumin",)),
    ShowSystem("disguise", "media"),
    # Sound
    ShowSystem("Yamaha DM7", "sound", (".dm7f",)),
    ShowSystem("Yamaha DM3", "sound", (".dm3f",)),
    ShowSystem("Yamaha CL/QL", "sound", (".clf",)),
    ShowSystem("Yamaha TF", "sound", (".tff",)),
    ShowSystem("Midas M32", "sound", (".scn", ".shw", ".snp", ".chn", ".efx", ".rou")),
    ShowSystem("Behringer X32", "sound", (".scn", ".shw", ".snp", ".chn", ".efx", ".rou")),
    ShowSystem("DiGiCo", "sound", (".ses",)),
    ShowSystem("Allen & Heath dLive", "sound"),
    ShowSystem("d&b R1", "sound", (".dbpr",)),
    ShowSystem("L-Acoustics LA Network Manager", "sound", (".preset", ".system")),
)

#: Every ending of a show file, e.g. ``.esf`` or ``.show.gz``.
SHOWFILE_EXTENSIONS: frozenset[str] = frozenset(extension for system in SHOW_SYSTEMS for extension in system.extensions)

#: Endings with more than one dot (``.show.gz``): they are found by the end of the name, not by its last suffix.
_COMPOUND = tuple(sorted((ending for ending in SHOWFILE_EXTENSIONS if ending.count(".") > 1), key=len, reverse=True))


def showfile_extension(name: str) -> str:
    """The show file ending of a file name, or ``""``: ``"Gala.show.gz"`` gives ``".show.gz"``."""
    lower = (name or "").strip().lower()
    for ending in _COMPOUND:
        if lower.endswith(ending) and len(lower) > len(ending):
            return ending
    suffix = Path(lower).suffix
    return suffix if suffix in SHOWFILE_EXTENSIONS else ""


def is_showfile_name(name: str) -> bool:
    """Whether a file name ends like a show file (PRJ-089)."""
    return bool(showfile_extension(name))


def systems_for(name: str) -> list[str]:
    """The consoles or programs a file can come from, by its ending; several for ``.shw``."""
    ending = showfile_extension(name)
    if not ending:
        return []
    return [system.name for system in SHOW_SYSTEMS if ending in system.extensions]


def guess_system(name: str) -> str:
    """The console or program of a show file if its ending tells it unambiguously, else ``""``.

    ``.esf3d`` is Eos, ``.dm7f`` a DM7. ``.shw`` may be Hog 4, MagicQ or an
    X32/M32, and ``.avc`` Resolume Arena or Avenue: those are chosen by hand –
    for Resolume both use the same file, so "Resolume Arena" is taken.
    """
    names = systems_for(name)
    if len(names) == 1:
        return names[0]
    if names and all(entry.startswith("Resolume") for entry in names):
        return names[0]
    return ""


def system_names() -> list[str]:
    """The names to suggest when a console or program is typed in."""
    return [system.name for system in SHOW_SYSTEMS]


def endings_text() -> str:
    """The endings for the help text and the error message: ``asc, avc, … show.gz``."""
    return ", ".join(sorted(ending.lstrip(".") for ending in SHOWFILE_EXTENSIONS))
