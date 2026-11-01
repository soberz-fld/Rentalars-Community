# SPDX-License-Identifier: GPL-3.0-or-later
"""Load before the first request what every request needs (NFA-012).

A fresh server process answers its first request slowly: Django reads the
URL table, the language file and each template only when they are first
asked for. Measured on the page of a project with 500 lines: 1.1 seconds
for the first request of a process, 0.45 for every later one. The
application server starts a fresh process after every restart and replaces
each process after 2,000 requests, so some user meets that first request
every day.

The application server therefore loads the application once, before it
splits into its worker processes (``--preload`` in
deploy/systemd/rentalars.service), and :func:`warm_up` does the reading at
that moment. The workers inherit the result.

Nothing here may talk to the database: a connection opened before the split
would be shared by all workers and garble their conversations with MariaDB.

The second half is :func:`set_startup_objects_aside`. Python looks through
all objects in memory from time to time to find garbage that refers to
itself. After the start that means about 100,000 objects – templates, URL
table, classes – that will never be garbage, and looking through them took
90 to 230 milliseconds, in the middle of whatever request was running at
that moment. That pause, not the work of the request, was what pushed
"add a line" over its half second now and then (NFA-013).
"""

from __future__ import annotations

import gc
import logging
from pathlib import Path

from django.conf import settings
from django.template import engines
from django.urls import get_resolver
from django.utils import translation

logger = logging.getLogger(__name__)


def warm_up() -> int:
    """Read URL table, language file and all own templates into memory.

    A failure is logged and otherwise ignored: this only saves time, and the
    application must start without it.

    Returns:
        The number of templates loaded (0 after a failure).
    """
    try:
        # The URL table in both directions; this also imports every view and API module.
        get_resolver().reverse_dict  # noqa: B018 – reading the property fills it
        with translation.override(settings.LANGUAGE_CODE):
            translation.gettext("Projects")
        return _load_templates()
    except Exception:
        logger.exception("Warm-up failed; the first requests will be slower.")
        return 0


def _load_templates() -> int:
    """Compile every template of the project; Django keeps compiled templates in memory."""
    engine = engines["django"]
    loaded = 0
    # Only the directories named in the settings: the templates of libraries
    # (admin, API browser) are rarely used and are loaded when needed.
    for directory in engine.engine.dirs:
        root = Path(directory)
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix in {".html", ".txt"}:
                engine.get_template(path.relative_to(root).as_posix())
                loaded += 1
    return loaded


def set_startup_objects_aside() -> None:
    """Tell Python's garbage collector to leave alone what exists right now.

    Call this once, after :func:`warm_up`. Everything loaded up to then stays
    for the life of the process anyway; set aside, it is no longer looked
    through when the collector searches for garbage, which makes those
    searches short (see the top of this module). Garbage that requests
    produce is found as before.
    """
    gc.collect()
    gc.freeze()
