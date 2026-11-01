# SPDX-License-Identifier: GPL-3.0-or-later
"""Stored files: a deleted file stays for a few days in ``media/.deleted`` (consistent backup).

The nightly backup writes the database first and the files after it. A file that a person deletes in between is
still named by the database in the backup – and would be missing from the files. So a deletion moves the file into
the folder ``.deleted`` of the media folder, which the backup carries along, and the daily maintenance removes it
for good after :data:`KEEP_DAYS` days. Everything the database of a backup names is then in that backup; files that
come later may be in it as well (they belong to no row of the database and do no harm).
"""

from __future__ import annotations

import datetime
import os
import secrets
import shutil
from pathlib import Path

from django.core.files.storage import FileSystemStorage

#: The folder inside the media folder that holds deleted files.
TRASH = ".deleted"
#: How many days a deleted file is kept – more than a backup needs to be written.
KEEP_DAYS = 7


class KeepDeletedStorage(FileSystemStorage):
    """The usual storage, except that ``delete`` moves the file to ``.deleted/<day>/`` instead of removing it."""

    def delete(self, name: str | None) -> None:
        """Move the file into the trash of the day; anything else (a folder, a missing file) is deleted as usual."""
        if not name:
            raise ValueError("The name must be given to delete().")
        path = Path(self.path(name))
        try:
            relative = path.relative_to(self.location)
        except ValueError:
            super().delete(name)
            return
        if relative.parts and relative.parts[0] == TRASH:  # already in the trash: purge removes it
            super().delete(name)
            return
        if not path.is_file():
            super().delete(name)  # a folder or nothing: the usual behaviour
            return
        target = Path(self.location) / TRASH / datetime.date.today().isoformat() / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():  # the same name deleted twice on one day
            target = target.with_name(f"{target.name}.{secrets.token_hex(3)}")
        try:
            os.replace(path, target)
        except FileNotFoundError:
            return


def purge_deleted(*, keep_days: int = KEEP_DAYS, today: datetime.date | None = None) -> int:
    """Remove the days of the trash that are older than ``keep_days``; returns the number of folders removed."""
    from django.conf import settings

    root = Path(settings.MEDIA_ROOT) / TRASH
    if not root.is_dir():
        return 0
    today = today or datetime.date.today()
    removed = 0
    for day in sorted(root.iterdir()):
        try:
            when = datetime.date.fromisoformat(day.name)
        except ValueError:
            continue
        if (today - when).days > keep_days:
            shutil.rmtree(day, ignore_errors=True)
            removed += 1
    return removed
