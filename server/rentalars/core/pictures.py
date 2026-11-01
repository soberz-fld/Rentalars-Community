# SPDX-License-Identifier: GPL-3.0-or-later
"""Opening pictures of strangers (S1): only with the decoders of the formats that are expected.

``PIL.Image.open`` tries every format it knows: GIF, TIFF, XBM, BMP, SPIDER and a dozen more. Many of the memory errors of
Pillow sit in such rarely used readers, and a file named ``.png`` reaches them as well as a real GIF. Whoever may upload a
picture – also the crew, with a photo in the chat or a receipt – could use that. ``open_picture`` hands Pillow the list of
the formats that may be read; everything else is "not an image".
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

#: The only formats the program ever reads: JPEG (also as MPO, the format of some phones), PNG, GIF, WebP. Everything
#: Pillow knows beyond them is of no use to Rentalars (the pages that print pictures through WeasyPrint need no more).
READABLE_FORMATS = frozenset({"JPEG", "MPO", "PNG", "GIF", "WEBP"})


def restrict_decoders() -> None:
    """Take every other reader out of Pillow, for the whole program (called when the application starts).

    ``open_picture`` names the formats of the place; but code that is not ours – the image fields of Django and of the
    REST framework, WeasyPrint – calls ``Image.open`` without a list, and then every reader Pillow has is tried. After
    this call there are only the five.
    """
    from PIL import Image

    Image.init()  # all readers are registered once; ``init`` does nothing after the first call
    for name in [name for name in Image.OPEN if name not in READABLE_FORMATS]:
        del Image.OPEN[name]
    Image.ID[:] = [name for name in Image.ID if name in Image.OPEN]  # the list that ``open`` walks through


def open_picture(source: Any, formats: Iterable[str]) -> Any:
    """``Image.open(source)`` restricted to ``formats`` (names as ``Image.format``, e.g. ``"PNG"``, ``"MPO"``).

    Raises:
        PIL.UnidentifiedImageError: The file is not a picture of one of these formats.
    """
    from PIL import Image

    Image.init()  # registers all readers; without it a name such as "WEBP" or "MPO" is unknown to ``open`` (KeyError)
    registered = Image.OPEN
    return Image.open(source, formats=sorted(name for name in formats if name in registered))
