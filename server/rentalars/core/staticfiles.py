# SPDX-License-Identifier: GPL-3.0-or-later
"""Addresses of static files that change when the file changes (NFA-065).

Style sheet, scripts and icons are delivered with the instruction "keep this
for a week", so that a page does not fetch them again with every click. After
an update of Rentalars the browser would therefore go on using the old style
sheet for days: new parts of a page appear without their styles – numbers
that should be buttons run together into one word.

The cure is an address that belongs to the content: ``/static/css/app.css``
becomes ``/static/css/app.css?v=3f9a1c20d4``, where the part after ``v=`` is
a fingerprint of the file. A changed file has a new address, which no browser
has in its cache; an unchanged file keeps its address and stays cached.

*Rejected:* Django's ``ManifestStaticFilesStorage``, which writes the
fingerprint into the file name. It needs a manifest built by
``collectstatic`` and fails the whole page when a file is missing from it;
for one style sheet, two scripts and an icon file that is more machinery and
more ways to fail than the problem deserves.
"""

from __future__ import annotations

import hashlib
import os

from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import StaticFilesStorage

#: Fingerprints by file, each with the modification time it was taken at.
#: Reading and hashing a file once per server process is enough; the time is
#: compared so that a developer who edits a style sheet sees it at once.
_fingerprints: dict[str, tuple[float, str]] = {}


def fingerprint(path: str) -> str:
    """Return a short fingerprint of a file's content, or ``""`` if it cannot be read."""
    try:
        modified = os.stat(path).st_mtime
    except OSError:
        return ""
    known = _fingerprints.get(path)
    if known is not None and known[0] == modified:
        return known[1]
    try:
        with open(path, "rb") as file:
            digest = hashlib.sha256(file.read()).hexdigest()[:10]
    except OSError:
        return ""
    _fingerprints[path] = (modified, digest)
    return digest


class VersionedStaticFilesStorage(StaticFilesStorage):
    """The usual storage for static files, with a fingerprint in every address."""

    def url(self, name: str | None) -> str:
        """Return the address of a static file, followed by ``?v=`` and its fingerprint.

        A file that cannot be found gets its plain address: a missing icon
        must not turn into a page that cannot be shown.
        """
        address = super().url(name)
        if not name or "?" in address or "#" in address:
            return address
        path = self.path(name) if self.location else ""
        if not path or not os.path.exists(path):
            # Not collected (development, tests): look where the file comes from.
            path = finders.find(name) or ""
        stamp = fingerprint(path) if path else ""
        return f"{address}?v={stamp}" if stamp else address
