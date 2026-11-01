# SPDX-License-Identifier: GPL-3.0-or-later
"""The storage spot of an item inside its storage location (MAT-080).

The requirement: a short mark for the place within the storage location – e.g.
1-A-1 for shelf or area 1, bay A, height 1, so two digits, one letter, one digit.
The mark is short on purpose: it is shown next to the storage location in
lists and on the packing list, where there is no room for long texts.

The rule
--------
Text that looks like such a mark is written the one way, whatever was typed:
``1a1``, ``1 a 1``, ``01.a.1`` and ``1-A-1`` all become ``01-A-1`` – so that
sorting and searching find the same place however it was typed. Any other
short text (``Box 4``) is kept as typed, with its spaces tidied; the field
holds at most :data:`SPOT_LENGTH` characters.
"""

from __future__ import annotations

import re

#: The longest storage spot: ``01-A-1`` needs six, a short text up to twelve.
SPOT_LENGTH = 12

#: Two digits (the first may be left out), one letter, one digit – separated by a dash, dot, slash, space or nothing.
_MARK = re.compile(r"^(\d{1,2})\s*[-./ ]?\s*([A-Za-z])\s*[-./ ]?\s*(\d)$")


def normalise_spot(text: str | None) -> str:
    """The storage spot as it is stored: ``1a1`` → ``01-A-1``; other short text as typed, tidied."""
    text = " ".join((text or "").split())
    mark = _MARK.match(text)
    if mark is None:
        return text
    return f"{int(mark.group(1)):02d}-{mark.group(2).upper()}-{mark.group(3)}"
