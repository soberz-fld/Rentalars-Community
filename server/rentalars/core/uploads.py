# SPDX-License-Identifier: GPL-3.0-or-later
"""Checks for uploaded files and their protected delivery (NFA-007).

Two rules apply to every upload:

1. Type and size are checked before the file is stored.
2. Files are never reachable through a plain URL. A view checks the rights of
   the user and only then hands out the content (see ``protected_file_response``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404, HttpResponse
from django.utils.http import content_disposition_header
from django.utils.translation import gettext_lazy as _

from rentalars.core.pictures import open_picture

#: File name endings accepted for the material import (IMP-007).
IMPORT_EXTENSIONS = frozenset({".xlsx", ".csv"})

#: Image formats accepted for logos. SVG is excluded because it can contain scripts.
IMAGE_FORMATS = frozenset({"PNG", "JPEG"})


def validate_image_upload(uploaded_file: Any) -> None:
    """Accept only PNG or JPEG images up to the configured size.

    The format is determined from the file content, not from the file name:
    a renamed HTML file is rejected.
    """
    from PIL import UnidentifiedImageError

    size = getattr(uploaded_file, "size", 0) or 0
    if size > settings.MAX_IMAGE_UPLOAD_BYTES:
        raise ValidationError(_("The image is too large (at most 2 MB)."))
    try:
        uploaded_file.seek(0)
        # S1: only the decoders of the formats that are allowed – no other format of Pillow reads the file.
        with open_picture(uploaded_file, IMAGE_FORMATS) as image:
            image_format = image.format
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as error:
        raise ValidationError(_("The file is not a valid image.")) from error
    finally:
        uploaded_file.seek(0)
    if image_format not in IMAGE_FORMATS:
        raise ValidationError(_("Only PNG and JPEG images are allowed."))


def validate_import_upload(uploaded_file: Any) -> None:
    """Accept only spreadsheet files (XLSX or CSV) up to the configured size."""
    extension = Path(uploaded_file.name or "").suffix.lower()
    if extension not in IMPORT_EXTENSIONS:
        raise ValidationError(_("Only XLSX and CSV files can be imported."))
    if (uploaded_file.size or 0) > settings.MAX_IMPORT_UPLOAD_BYTES:
        raise ValidationError(_("The file is too large (at most 25 MB)."))


#: File types accepted as documents: project files, hall plans, mail
#: attachments (NFA-007, PRJ-007, EML-028). Formats that a browser would run
#: as a page – HTML, SVG, scripts – and programs are not among them. Since
#: Also lighting plots (``.mvr``, PRJ-086): a ZIP archive like ``.zip``,
#: always downloaded, never shown in the browser.
DOCUMENT_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".txt",
        ".csv",
        ".xlsx",
        ".xls",
        ".docx",
        ".doc",
        ".pptx",
        ".ppt",
        ".odt",
        ".ods",
        ".odp",
        ".zip",
        ".mvr",
        ".dwg",
        ".dxf",
        ".ics",
        ".vcf",
        ".eml",
    }
)

#: Of those, the ones a browser may show itself; everything else is downloaded.
INLINE_EXTENSIONS = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".txt"})


def max_upload_bytes() -> int:
    """The largest document that may be uploaded, as set by the administrators (NFA-007)."""
    from rentalars.core.models import SystemSettings

    return int(SystemSettings.load().max_upload_mb) * 1024 * 1024


def document_type_allowed(name: str) -> bool:
    """Whether a file name has one of the accepted document endings.

    PRJ-089: show files of lighting consoles, media servers and sound
    systems as well – by their ending, ``.show.gz`` included (``core.showfiles``).
    """
    from rentalars.core.showfiles import is_showfile_name

    return Path(name or "").suffix.lower() in DOCUMENT_EXTENSIONS or is_showfile_name(name)


def validate_document_upload(uploaded_file: Any) -> None:
    """Accept only the document types of :data:`DOCUMENT_EXTENSIONS` and show files up to the configured size."""
    from rentalars.core.showfiles import endings_text

    name = getattr(uploaded_file, "name", "") or ""
    if not document_type_allowed(name):
        documents = ", ".join(sorted(extension.lstrip(".") for extension in DOCUMENT_EXTENSIONS))
        # PRJ-089: and the show files, named as such.
        raise ValidationError(
            _("Files of this type cannot be stored. Allowed: %(types)s.")
            % {"types": f"{documents}; " + _("show files: %(endings)s") % {"endings": endings_text()}}
        )
    size = getattr(uploaded_file, "size", 0) or 0
    limit = max_upload_bytes()
    if size > limit:
        raise ValidationError(_("The file is too large (at most %(megabytes)d MB).") % {"megabytes": limit // 1048576})


def safe_download_name(name: str) -> str:
    """A file name that can go into a header: no quotes, slashes or line breaks."""
    cleaned = "".join(character for character in name if character not in '"\\/\r\n\t').strip()
    return cleaned or "datei"


def document_response(relative_path: str, name: str) -> HttpResponse:
    """Deliver a stored document: shown in the browser if harmless, downloaded otherwise (NFA-007).

    Shown documents get a ``sandbox`` policy: even a file that is not what
    its name says cannot run anything.
    """
    inline = Path(name).suffix.lower() in INLINE_EXTENSIONS
    response = protected_file_response(relative_path, download_name=None if inline else safe_download_name(name))
    if inline:
        response["Content-Disposition"] = content_disposition_header(False, safe_download_name(name))
        response["Content-Security-Policy"] = "sandbox; default-src 'none'; img-src 'self'; style-src 'unsafe-inline'"
    return response


def protected_file_response(relative_path: str, *, download_name: str | None = None) -> HttpResponse:
    """Deliver a stored file after the caller has checked the rights.

    On a server NGINX sends the file itself, which is faster than Python; the
    application only names it in the ``X-Accel-Redirect`` header. The location
    ``/protected-media/`` is marked ``internal`` in the NGINX configuration
    and cannot be requested from outside.

    Args:
        relative_path: Path below ``MEDIA_ROOT``.
        download_name: If given, the browser saves the file under this name
            instead of displaying it.
    """
    media_root = Path(settings.MEDIA_ROOT).resolve()
    full_path = (media_root / relative_path).resolve()
    # Refuse paths such as "../../etc/passwd" that point outside the media folder.
    if media_root not in full_path.parents or not full_path.is_file():
        raise Http404

    if settings.SERVE_MEDIA_VIA_NGINX:
        response = HttpResponse()
        response["X-Accel-Redirect"] = f"/protected-media/{relative_path}"
        # Let NGINX determine the content type from the file name.
        del response["Content-Type"]
    else:
        response = FileResponse(full_path.open("rb"))
    if download_name:
        response["Content-Disposition"] = content_disposition_header(True, download_name)
    response["X-Content-Type-Options"] = "nosniff"
    return response
