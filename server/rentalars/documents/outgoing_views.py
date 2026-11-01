# SPDX-License-Identifier: GPL-3.0-or-later
"""The page Buchhaltung → Ausgangsbelege (DOK-020).

Every document a customer got – offers, order confirmations, delivery notes,
invoices, cancellations – as a table of ``core.tables`` (UIX-015, UIX-040):
columns to choose, filters behind one button (UIX-038), sorting by every
column, groups by every shown column, CSV of the filtered list. Below it the
sums of the filtered documents per kind. For who may see prices and read
every project (``outgoing.may_see``); see :mod:`rentalars.documents.outgoing`.
"""

from __future__ import annotations

import zipfile
from tempfile import SpooledTemporaryFile

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Module, module_required, request_rights
from rentalars.core import bulk
from rentalars.core.listing import paginate
from rentalars.core.uploads import safe_download_name
from rentalars.customers.models import Customer
from rentalars.documents import free, outgoing
from rentalars.documents.models import AccountingSettings
from rentalars.documents.outgoing_tables import OUTGOING_TABLE
from rentalars.documents.services import invoices_enabled
from rentalars.projects.models import Project


@module_required(Module.PROJECTS)
def outgoing_list(request: HttpRequest) -> HttpResponse:
    """Buchhaltung → Ausgangsbelege: the outgoing documents, filtered, sorted, grouped – or as CSV (DOK-020)."""
    rights = request_rights(request)
    if not outgoing.may_see(rights):
        raise PermissionDenied
    filters = outgoing.parse(request.GET)
    filtered = filters.apply(outgoing.documents())
    table = OUTGOING_TABLE.state(request)
    rows = table.order(outgoing.for_list(filtered))
    if table.wants_csv:
        return table.csv_response(rows, _("Outgoing documents"))
    page = paginate(request, rows)
    customers = Customer.objects.filter(pk__in=outgoing.documents().values("customer")).order_by("name")
    return render(
        request,
        "documents/outgoing.html",
        {
            **outgoing.tabs(rights),
            "tab": "outgoing",
            "page": page,
            "table": table,
            "rows": table.rows(page),
            "filters": filters,
            "kind_choices": outgoing.kind_choices(),
            "state_choices": outgoing.state_choices(),
            "origin_choices": outgoing.origin_choices(),  # With or without a project
            # Free outgoing documents: "Neuer Ausgangsbeleg" for whoever may make one.
            "may_make_free": free.may_change(rights),
            "free_drafts": free.drafts_for_list() if free.may_see(rights) else [],
            # DOK-011: the filter by Lexware Office only where invoices are handed over.
            "lexware_choices": outgoing.lexware_choices() if _lexware_on() or filters.lexware else [],
            "customers": customers.only("pk", "name", "number"),
            "project": Project.objects.filter(pk=filters.project).only("pk", "number", "name").first()
            if filters.project
            else None,
            "totals": outgoing.totals(filtered),
            "bulk_extra": "documents/_bulk_outgoing.html",  # Download the chosen documents
        },
    )


#: The most documents in one download – every one is read from the disk and packed.
MAX_DOWNLOAD = 300


@module_required(Module.PROJECTS)
@require_POST
def outgoing_download(request: HttpRequest) -> HttpResponse:
    """The chosen documents as one ZIP file: each PDF, and the XRechnung where the document has one.

    The table's tick boxes post here (``bulk``). Every document goes through the check of a single download – the
    access to its project or the rights of Accounting, the price right, a monthly invoice's cases –; a document
    the user may not open is left out and named.
    """
    from rentalars.documents.views import document_for

    rights = request_rights(request)
    if not outgoing.may_see(rights):
        raise PermissionDenied
    target = bulk.back(request, reverse("documents:outgoing"))
    ids = bulk.chosen_ids(request, OUTGOING_TABLE.key)
    if not ids:
        messages.warning(request, _("Tick at least one row first."))
        return redirect(target)
    if len(ids) > MAX_DOWNLOAD:
        messages.error(request, _("At most %(count)d documents in one download.") % {"count": MAX_DOWNLOAD})
        return redirect(target)
    archive = SpooledTemporaryFile(max_size=25 * 1024 * 1024)  # noqa: SIM115 – handed to the response, which closes it
    left_out: list[str] = []
    packed = 0
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
        for pk in ids:
            try:
                document = document_for(request, pk)
            except (PermissionDenied, Http404):
                left_out.append(str(pk))
                continue
            for field, extension in ((document.file, "pdf"), (document.xml_file, "xml")):
                if not field:
                    continue
                try:
                    with field.open("rb") as handle:
                        zipped.writestr(safe_download_name(f"{document.number}.{extension}"), handle.read())
                except OSError:
                    left_out.append(f"{document.number}.{extension}")
                else:
                    packed += 1
    if not packed:
        archive.close()
        messages.error(request, _("Nothing could be packed: %(left)s") % {"left": ", ".join(left_out)})
        return redirect(target)
    if left_out:
        messages.warning(request, _("Left out (not found or not allowed): %(left)s") % {"left": ", ".join(left_out)})
    archive.seek(0)
    name = f"{_('Outgoing documents')}-{timezone.localdate():%Y-%m-%d}.zip".replace(" ", "-")
    return FileResponse(archive, as_attachment=True, filename=name, content_type="application/zip")


def _lexware_on() -> bool:
    """Whether invoices are handed to Lexware Office (DOK-011) – only while they are made in Rentalars (DOK-014)."""
    return invoices_enabled() and AccountingSettings.load().lexware_enabled
