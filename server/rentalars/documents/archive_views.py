# SPDX-License-Identifier: GPL-3.0-or-later
"""Buchhaltung → Archiv: the archive of vouchers, the export for an audit and the procedure documentation (DOK-043, DOK-046).

Rights: as for the EÜR (``outgoing.may_see_euer``): the settings (read) and both price rights – the export holds the whole books.
Checking the archive now needs write access to the settings in addition.
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Module, module_required, request_rights
from rentalars.documents import archive, audit_export, euer, outgoing, procedure
from rentalars.documents.euer_views import require_euer
from rentalars.documents.models import ArchiveRecord, ArchiveStatus

PAGE_SIZE = 100


@module_required(Module.ADMINISTRATION)
def archive_page(request: HttpRequest) -> HttpResponse:
    """The archive: numbers, findings, the list of vouchers; the export and the procedure documentation."""
    require_euer(request)
    rights = request_rights(request)
    status = request.GET.get("status", "")
    records = ArchiveRecord.objects.all()
    if status in ArchiveStatus.values:
        records = records.filter(status=status)
    today = timezone.localdate()
    years = list(range(today.year, today.year - 8, -1))
    return render(
        request,
        "documents/archive.html",
        {
            **outgoing.tabs(rights),
            "tab": "archive",
            "info": archive.summary(),
            "records": list(records[:PAGE_SIZE]),
            "status": status,
            "statuses": ArchiveStatus.choices,
            "years": years,
            "may_check": rights.can_write(Module.ADMINISTRATION),
            "today": today,
        },
    )


@require_POST
@module_required(Module.ADMINISTRATION)
def archive_verify(request: HttpRequest) -> HttpResponse:
    """Register what is new and check the whole archive now."""
    require_euer(request)
    if not request_rights(request).can_write(Module.ADMINISTRATION):
        raise PermissionDenied
    result = archive.run(everything=True)
    if result.problems:
        messages.warning(
            request,
            _("%(checked)d files checked: %(problems)d vouchers changed or missing.")
            % {"checked": result.checked, "problems": result.problems},
        )
    else:
        messages.success(request, _("%(checked)d vouchers checked, no changes found.") % {"checked": result.checked})
    return redirect("documents:archive")


@module_required(Module.ADMINISTRATION)
def audit_export_download(request: HttpRequest) -> HttpResponse:
    """The ZIP for an audit: ``?year=2026`` or ``?year=all``."""
    require_euer(request)
    raw = request.GET.get("year", "")
    year = None if raw == "all" else euer.parse_year(raw, timezone.localdate().year)
    body = audit_export.build(year)
    name = f"pruefexport-{year if year else 'alle'}.zip"
    return FileResponse(body, as_attachment=True, filename=name, content_type="application/zip")


@require_POST
@module_required(Module.ADMINISTRATION)
def audit_export_start(request: HttpRequest) -> HttpResponse:
    """Make the ZIP for an audit as a task in the background and show its progress (DOK-054)."""
    require_euer(request)
    raw = request.POST.get("year", "")
    year = None if raw == "all" else euer.parse_year(raw, timezone.localdate().year)
    job = audit_export.start(year, user=request.user)
    messages.success(request, _("The export is being made. You will be told when it is ready."))
    return redirect("core:job", pk=job.pk)


@module_required(Module.ADMINISTRATION)
def procedure_page(request: HttpRequest) -> HttpResponse:
    """The procedure documentation as a page; ``?format=pdf`` or ``?format=md`` downloads it."""
    require_euer(request)
    kind = request.GET.get("format", "")
    if kind == "pdf":
        response = HttpResponse(procedure.render_pdf(), content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="verfahrensdokumentation.pdf"'
        return response
    if kind == "md":
        response = HttpResponse(procedure.as_markdown(), content_type="text/markdown; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="verfahrensdokumentation.md"'
        return response
    if kind:
        raise Http404
    rights = request_rights(request)
    return render(
        request,
        "documents/procedure.html",
        {**outgoing.tabs(rights), "tab": "archive", "sections": procedure.sections()},
    )


def back_url() -> str:
    """Where the pages return to."""
    return reverse("documents:archive")
