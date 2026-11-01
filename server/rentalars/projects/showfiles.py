# SPDX-License-Identifier: GPL-3.0-or-later
"""Show files as project files (PRJ-089).

A show file is a project file of a document type marked "show files"
(``DocumentType.is_showfile``, the start data call it "Showfile"). It notes
the console or software it belongs to and the version it was saved with,
and which file of a console is the current show:

* An uploaded file whose ending is that of a show file (``core.showfiles``)
  and that came without a document type gets the type "Showfile"; the
  console follows from the ending where it is unambiguous (``.esf3d`` is
  Eos; ``.shw`` may be Hog 4, MagicQ or an X32/M32 and is chosen by hand).
* A new show file is the current one of its console; the one before keeps
  its place in the list, without the mark. The mark can be moved back.
* The type "Showfile" is visible to the crew: the people planned see the
  show files in the deployment view (AUT-023), like a stage plan.

Files are handed out as downloads (``core.uploads.document_response``); a
show file is never opened in the browser.
"""

from __future__ import annotations

import json
from typing import Any

from django import forms
from django.db.models import QuerySet

from rentalars.core.showfiles import SHOWFILE_EXTENSIONS, guess_system, is_showfile_name
from rentalars.masterdata.models import DocumentType
from rentalars.projects.models import ProjectFile


def showfile_type() -> DocumentType | None:
    """The active document type for show files, if there is one."""
    return DocumentType.objects.filter(is_showfile=True, is_active=True).order_by("position", "pk").first()


def is_show(project_file: ProjectFile) -> bool:
    """Whether a project file is a show file: its document type says so."""
    document_type = project_file.document_type
    return document_type is not None and document_type.is_showfile


def prepare_upload(name: str, document_type: Any, show_system: str) -> tuple[Any, str]:
    """The document type and console of a new upload (PRJ-089).

    A file with the ending of a show file and no document type becomes a
    "Showfile"; the console is guessed from the ending unless one is given.
    """
    if document_type is None and is_showfile_name(name):
        document_type = showfile_type()
    if document_type is not None and document_type.is_showfile and not show_system.strip():
        show_system = guess_system(name)
    return document_type, show_system.strip()[:80]


def same_console(project_file: ProjectFile) -> QuerySet[ProjectFile]:
    """The other show files of the same project and console (the console's name, case ignored)."""
    return (
        ProjectFile.objects.filter(
            project_id=project_file.project_id,
            document_type__is_showfile=True,
            show_system__iexact=project_file.show_system,
        )
        .exclude(pk=project_file.pk)
        .order_by("pk")
    )


def mark_current(project_file: ProjectFile) -> None:
    """Make a show file the current one of its console; the others of that console lose the mark.

    Saved one by one, so that the change log notes each change (PRJ-032).
    """
    for other in same_console(project_file).filter(is_current_show=True):
        other.is_current_show = False
        other.save(update_fields=["is_current_show"])


def clean_show_fields(project_file: ProjectFile) -> None:
    """A file that is no show file keeps no console, version or mark."""
    if not is_show(project_file):
        project_file.show_system = ""
        project_file.show_version = ""
        project_file.is_current_show = False


# --- Forms ---------------------------------------------------------------------------------------


class DocumentTypeSelect(forms.Select):
    """The choice of the document type; the types for show files carry ``data-showfile`` (PRJ-089).

    The page shows the fields of a show file only while such a type is
    chosen (``static/js/app.js``, block PRJ-089); without script they stay
    visible.
    """

    def create_option(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Mark the options of show file types."""
        option = super().create_option(*args, **kwargs)
        instance = getattr(option.get("value"), "instance", None)
        if instance is not None and getattr(instance, "is_showfile", False):
            option.setdefault("attrs", {})["data-showfile"] = "1"
        return option


def endings_map() -> str:
    """For the upload field: every show file ending with its console, empty where it is not unambiguous (JSON)."""
    return json.dumps({ending: guess_system(f"x{ending}") for ending in sorted(SHOWFILE_EXTENSIONS)})
