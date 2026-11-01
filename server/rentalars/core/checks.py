# SPDX-License-Identifier: GPL-3.0-or-later
"""System checks of the database (Django's check framework, tag ``database``).

NFA-077: the first migrations of each module are squashed into one or two (``0001_squashed_0004_…``, Django's
form). A database of a supported version has them applied – Django sees that every migration they replace is
recorded. A database of an older version has only part of them, and Django would stop with a
``NodeNotFoundError`` that names a migration but not the way out. ``migrate`` runs the checks of the database
before it reads the migrations, so this check stops it first and says so.
"""

from __future__ import annotations

from typing import Any

from django.core.checks import Error, Tags, register
from django.utils.translation import gettext as _

#: The version a database must have at least before it can be brought to this one.
OLDEST_UPDATABLE = "0.9.0"


def partially_applied_squashes(connection: Any) -> list[tuple[str, str]]:
    """The squashed migrations of which the database has some, but not all, of the replaced ones applied."""
    from django.db.migrations.loader import MigrationLoader
    from django.db.migrations.recorder import MigrationRecorder

    recorder = MigrationRecorder(connection)
    if not recorder.has_table():
        return []  # a new database
    applied = set(recorder.applied_migrations())
    loader = MigrationLoader(None, load=False)
    loader.load_disk()
    partial = []
    for key, migration in loader.disk_migrations.items():
        replaced = [tuple(target) for target in migration.replaces or ()]
        done = [target in applied for target in replaced]
        if any(done) and not all(done):
            partial.append(key)
    return sorted(partial)


@register(Tags.database)
def database_not_too_old(app_configs: Any = None, databases: Any = None, **kwargs: Any) -> list[Error]:
    """A database of a version before the oldest updatable one cannot be migrated to this version directly."""
    from django.db import DatabaseError, connections

    errors: list[Error] = []
    for alias in databases or ():
        try:
            partial = partially_applied_squashes(connections[alias])
        except DatabaseError:
            continue  # no database to look at: other checks and the command itself report that
        if partial:
            errors.append(
                Error(
                    _("The database comes from a Rentalars version before %(version)s.")
                    % {"version": OLDEST_UPDATABLE},
                    hint=_("This version cannot update that database directly. Not complete: %(migrations)s")
                    % {"migrations": ", ".join(f"{app}.{name}" for app, name in partial)},
                    id="rentalars.E001",
                )
            )
    return errors
