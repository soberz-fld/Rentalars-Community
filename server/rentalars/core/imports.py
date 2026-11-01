# SPDX-License-Identifier: GPL-3.0-or-later
"""The imports of Rentalars and how they run in the background (IMP-001, NFA-041).

Four lists can be imported: material, products, customers and people. Each
module registers its import as an :class:`ImportKind` – the fields it can
fill, the right it needs, the function that does the work – and the browser,
the API and the command on the server share everything else: the upload, the
column mapping, the dry run, the report.

In the browser a dry run and an import both run as a task in the background
(``core.jobs``), so a long list never keeps a page waiting or runs into the
time limit of a request (NFA-041). The uploaded file waits in
``DATA_DIR/imports`` until the import is done or another file is chosen.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from rentalars.core.tabular import ImportField, ImportFileError, Progress, Table, read_table


@dataclass(frozen=True)
class ImportOption:
    """A choice that applies to the whole file, e.g. whether its prices are net or gross (IMP-014).

    The page shows it as a selection in step 2 next to the column mapping,
    the API takes it as a form field of the same ``key``, and the task in the
    background keeps it with its parameters.
    """

    key: str
    label: Any
    #: ``[(value, label), …]`` – or a function returning them, for choices that come from the database.
    choices: Any
    #: The value when nothing is chosen; a function for a value from the database.
    default: Any = ""
    help_text: Any = ""

    def choice_list(self) -> list[tuple[str, Any]]:
        """The choices as ``(value, label)`` pairs, values as text."""
        choices = self.choices() if callable(self.choices) else self.choices
        return [(str(value), label) for value, label in choices]

    def default_value(self) -> str:
        """The value used when none or an unknown one is given."""
        default = self.default() if callable(self.default) else self.default
        return str(default)


@dataclass(frozen=True)
class ImportKind:
    """One list that can be imported."""

    key: str
    #: Shown as heading of the import page, e.g. "Import products".
    title: Any
    #: The module whose write right the import needs.
    module: str
    fields: tuple[ImportField, ...]
    #: ``run(table, mapping, *, dry_run, actor, rights, progress)`` → a report with ``ok`` and ``as_dict()``.
    run: Callable[..., Any]
    #: Explains the file in step 1 of the import page.
    introduction: Any = ""
    #: The page that lists what was imported (a URL name).
    list_url: str = ""
    #: The command on the server for long lists.
    command: str = "rentalars import_data"
    #: How the report is shown.
    report_template: str = "core/_import_report.html"
    #: Page head and tabs above the import, if the module has its own.
    head_template: str = ""
    #: IMP-014: choices for the whole file; ``run`` then gets them as ``options``.
    options: tuple[ImportOption, ...] = ()

    def clean_options(self, given: dict[str, Any] | None) -> dict[str, str]:
        """Every option of the kind with a valid value: the one given, else the default (IMP-014)."""
        given = given or {}
        cleaned = {}
        for option in self.options:
            value = str(given.get(option.key, "") or "")
            allowed = {choice for choice, _label in option.choice_list()}
            cleaned[option.key] = value if value in allowed else option.default_value()
        return cleaned


_KINDS: dict[str, ImportKind] = {}


def register(kind: ImportKind) -> None:
    """Make an import known; called by the modules when they are ready."""
    _KINDS[kind.key] = kind


def get(key: str) -> ImportKind:
    """The import with this key.

    Raises:
        LookupError: There is none.
    """
    try:
        return _KINDS[key]
    except KeyError as error:
        raise LookupError(key) from error


def kinds() -> list[ImportKind]:
    """All imports in a fixed order."""
    order = ["material", "products", "customers", "people"]
    return sorted(_KINDS.values(), key=lambda kind: order.index(kind.key) if kind.key in order else len(order))


# --- The uploaded file between the steps -------------------------------------------------


def upload_directory() -> Path:
    """The folder that holds uploaded import files between the steps."""
    directory = Path(settings.DATA_DIR) / "imports"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def store_upload(uploaded: Any) -> str:
    """Keep an uploaded file under a random name; returns that name."""
    name = secrets.token_hex(16) + Path(uploaded.name).suffix.lower()
    with (upload_directory() / name).open("wb") as target:
        for chunk in uploaded.chunks():
            target.write(chunk)
    return name


def stored_path(name: str) -> Path:
    """Where a stored file is; the name cannot leave the folder."""
    return upload_directory() / Path(name).name


def discard(name: str) -> None:
    """Remove a stored file."""
    stored_path(name).unlink(missing_ok=True)


def delete_old_uploads(days: int = 2) -> int:
    """Remove files of imports that were never finished (daily maintenance); returns how many.

    Only files uploaded through the browser or the API are removed – they carry
    a random name of 32 hexadecimal digits (:func:`store_upload`). A file an
    operator put into the folder for ``import_data`` stays.
    """
    import re
    import time

    limit = time.time() - days * 86400
    uploaded = re.compile(r"^[0-9a-f]{32}\.(xlsx|csv)$")
    count = 0
    for path in upload_directory().iterdir():
        if path.is_file() and uploaded.match(path.name) and path.stat().st_mtime < limit:
            path.unlink(missing_ok=True)
            count += 1
    return count


# --- Running ---------------------------------------------------------------------------


def run(
    kind: ImportKind,
    table: Table,
    mapping: dict[str, int | None],
    *,
    dry_run: bool,
    user: Any,
    rights: Any = None,
    progress: Progress | None = None,
    options: dict[str, Any] | None = None,
) -> Any:
    """Run an import or its dry run with the rights of ``user`` and return the report.

    ``options`` are the choices of the kind (IMP-014); a kind without any is called as before.
    """
    from rentalars.accounts.rights import rights_of

    arguments: dict[str, Any] = {"dry_run": dry_run, "actor": user or "system:import"}
    if progress is not None:
        arguments["progress"] = progress
    if kind.options:
        arguments["options"] = kind.clean_options(options)
    return kind.run(table, mapping, rights=rights if rights is not None else rights_of(user), **arguments)


def start(
    kind: ImportKind,
    file_name: str,
    original: str,
    mapping: dict[str, int | None],
    *,
    dry_run: bool,
    user: Any,
    sheet: str = "",
    keep_file: bool = True,
    options: dict[str, Any] | None = None,
) -> Any:
    """Start a dry run or an import as a task in the background (NFA-041); returns the task.

    Args:
        kind: The import.
        file_name: The stored file (:func:`store_upload`).
        original: The name the file had, for messages.
        mapping: Which column feeds which field.
        dry_run: Only check.
        user: Who started it; the import runs with this user's rights.
        sheet: The worksheet of an XLSX file; empty: the first.
        keep_file: Keep the file after a dry run, for the import that follows
            (the browser). The API sends the file again each time.
        options: The choices of the kind for the whole file (IMP-014).
    """
    from rentalars.core.jobs import start_job

    title = (_("Dry run: %(file)s") if dry_run else _("Import: %(file)s")) % {"file": original}
    return start_job(
        "import",
        {
            "kind": kind.key,
            "file": file_name,
            "original": original,
            "sheet": sheet,
            "mapping": mapping,
            "dry_run": dry_run,
            "keep_file": keep_file,
            "options": kind.clean_options(options) if kind.options else {},
        },
        user=user,
        title=f"{kind.title} – {title}",
    )


def run_job(job: Any) -> str:
    """The background task: read the stored file, import, keep the report with the task."""
    from rentalars.core.jobs import report_progress

    params = job.params
    kind = get(params["kind"])
    try:
        table = read_table(stored_path(params["file"]), params["original"], sheet=params.get("sheet") or None)
    except (ImportFileError, OSError) as error:
        job.result = {"report": None, "error": str(error)}
        raise
    finally:
        if not params.get("keep_file", True):
            discard(params["file"])
    report_progress(job, 5)
    mapping = {key: (int(index) if index is not None else None) for key, index in params["mapping"].items()}
    report = run(
        kind,
        table,
        mapping,
        dry_run=params["dry_run"],
        user=job.created_by,
        progress=lambda percent: report_progress(job, percent),
        options=params.get("options") or {},
    )
    job.result = {"report": report.as_dict()}
    if not params["dry_run"] and report.ok:
        discard(params["file"])
    if not report.ok:
        count = len(report.errors)
        return ngettext("%(count)s error – nothing was written.", "%(count)s errors – nothing was written.", count) % {
            "count": count
        }
    if params["dry_run"]:
        return _("The dry run found no errors.")
    return _("The import is complete.")
