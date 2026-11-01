# SPDX-License-Identifier: GPL-3.0-or-later
"""Files of a project: stage plans, riders, contracts … (PRJ-007, EML-021).

Uploads follow the rules for uploaded files (NFA-007): only the document
types of ``core.uploads.DOCUMENT_EXTENSIONS``, at most the size set by the
administrators, stored under a random name and handed out only after the
rights were checked (``projects.views`` / ``projects.api``).

Who may read a project sees all its files. In the deployment view the crew
sees only files marked "visible to the crew" – a stage plan, not the
contract (AUT-023).

PRJ-089: show files of consoles, media servers and sound systems
are project files of the type "Showfile" with console, version and the mark
of the current show (``projects.showfiles``).
"""

from __future__ import annotations

from typing import Any

from django.core.files.base import ContentFile
from django.db import transaction

from rentalars.core.uploads import validate_document_upload
from rentalars.projects import showfiles
from rentalars.projects.models import Project, ProjectFile
from rentalars.projects.services import ensure_editable


def add_file(
    project: Project,
    uploaded: Any,
    *,
    user: Any,
    title: str = "",
    document_type: Any = None,
    visible_to_crew: bool | None = None,
    source_attachment: Any = None,
    supplier: Any = None,
    supplier_document_kind: str = "",
    show_system: str = "",
    show_version: str = "",
    is_current_show: bool | None = None,
) -> ProjectFile:
    """Store an uploaded file with a project.

    Args:
        project: The project.
        uploaded: The uploaded file (or any Django ``File``) with ``name`` and ``size``.
        user: Who uploads it.
        title: Optional title; without one the file name is shown.
        document_type: The kind of document (``masterdata.DocumentType``), optional.
        visible_to_crew: Show it in the deployment view; default: as the kind says.
        source_attachment: The mail attachment it was taken from (EML-021).
        supplier: PRJ-106: the supplier of subrentals whose document it is.
        supplier_document_kind: PRJ-106: offer, order confirmation … (``SupplierDocumentKind``).
        show_system: PRJ-089: the console or software of a show file; guessed from the ending if empty.
        show_version: PRJ-089: the version the show was saved with.
        is_current_show: PRJ-089: whether it is the current show of its console; default: yes, for a show file.

    Raises:
        ValidationError: Type or size not allowed, or the project is closed.
    """
    ensure_editable(project)
    validate_document_upload(uploaded)
    # PRJ-089: a show file without a document type becomes a "Showfile", with the console its ending tells.
    document_type, show_system = showfiles.prepare_upload(uploaded.name or "", document_type, show_system)
    if visible_to_crew is None:
        visible_to_crew = bool(document_type and document_type.visible_to_crew)
    project_file = ProjectFile(
        project=project,
        document_type=document_type,
        title=title.strip()[:200],
        original_name=(uploaded.name or "datei").rsplit("/", 1)[-1][:255],
        size=uploaded.size or 0,
        visible_to_crew=visible_to_crew,
        source_attachment=source_attachment,
        uploaded_by=user if getattr(user, "pk", None) else None,
        supplier=supplier,
        supplier_document_kind=supplier_document_kind,
        show_system=show_system,
        show_version=show_version.strip()[:40],
        is_current_show=True if is_current_show is None else is_current_show,
    )
    showfiles.clean_show_fields(project_file)
    project_file.file.save(project_file.original_name, uploaded, save=False)
    try:
        with transaction.atomic():
            project_file.full_clean(exclude=["file"])
            project_file.save()
            if project_file.is_current_show:
                showfiles.mark_current(project_file)
    except Exception:
        project_file.file.delete(save=False)
        raise
    return project_file


def add_file_from_attachment(attachment: Any, *, user: Any, document_type: Any = None, title: str = "") -> ProjectFile:
    """Take a mail attachment over into the files of the mail's project (EML-021)."""
    with attachment.file.open("rb") as handle:
        content = ContentFile(handle.read(), name=attachment.filename)
    return add_file(
        attachment.mail.project,
        content,
        user=user,
        title=title,
        document_type=document_type,
        source_attachment=attachment,
    )


#: What :func:`update_file` changes; PRJ-089: the console, version and mark of a show file.
CHANGEABLE_FIELDS = (
    "title",
    "document_type",
    "visible_to_crew",
    "supplier",
    "supplier_document_kind",
    "show_system",
    "show_version",
    "is_current_show",
)


@transaction.atomic
def update_file(project_file: ProjectFile, **changes: Any) -> ProjectFile:
    """Change title, document type or visibility of a file; PRJ-106: its supplier and the kind of document.

    PRJ-089: of a show file also the console, the version and whether it is
    the current show – marking it takes the mark from the other show files
    of its console.
    """
    ensure_editable(project_file.project)
    if changes.get("supplier", project_file.supplier) is None:
        changes["supplier_document_kind"] = ""
    for name in CHANGEABLE_FIELDS:
        if name in changes:
            value = changes[name]
            setattr(project_file, name, value.strip() if isinstance(value, str) else value)
    showfiles.clean_show_fields(project_file)
    project_file.full_clean(exclude=["file"])
    project_file.save()
    if project_file.is_current_show:
        showfiles.mark_current(project_file)
    return project_file


def delete_file(project_file: ProjectFile) -> None:
    """Remove a file from the project and from the disk."""
    ensure_editable(project_file.project)
    stored = project_file.file
    with transaction.atomic():
        project_file.delete()
    transaction.on_commit(lambda: stored.delete(save=False))


def files_for_crew(project: Project) -> Any:
    """The files the crew may see in the deployment view (AUT-023)."""
    return project.files.filter(visible_to_crew=True).select_related("document_type")
