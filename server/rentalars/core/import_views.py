# SPDX-License-Identifier: GPL-3.0-or-later
"""The import page shared by material, products, customers and people (IMP-001 to IMP-003, NFA-041).

Three steps: choose the file, assign the columns and make a dry run, import.
Dry run and import run as a task in the background; the page shows how far
the task got and then its report. The uploaded file is kept on the server
between the steps; the session only remembers its random name and the task.

IMP-011: below the result the page lists every row of the file –
new, changed (old → new), unchanged, error – 200 to a page, with a filter by
outcome and a search for row, ID or name. Filter, search and page are part
of the address (``?show=changed&q=0310&page=2``), so they survive a reload
and work without scripts. The report of a finished import keeps its address
too (``?job=…``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Page
from django.http import Http404, HttpRequest, HttpResponse
from django.http.response import HttpResponseBase
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from rentalars.accounts.rights import request_rights
from rentalars.core import import_rows, imports
from rentalars.core.listing import paginate
from rentalars.core.models import BackgroundJob, JobStatus
from rentalars.core.tabular import ImportFileError, read_table, resolve_mapping, suggest_mapping
from rentalars.core.uploads import validate_import_upload


class ImportUploadForm(forms.Form):
    """Step 1 of an import: choose the file."""

    file = forms.FileField(label=_("File (XLSX or CSV)"))


def _session_key(kind: imports.ImportKind) -> str:
    return f"import_{kind.key}"


def _discard(request: HttpRequest, kind: imports.ImportKind) -> None:
    """Forget the file of an import that is finished or abandoned, and remove it."""
    stored = request.session.pop(_session_key(kind), None)
    if stored:
        imports.discard(stored["file"])


def _refresh() -> HttpResponse:
    """Tell htmx to show the whole page anew."""
    response = HttpResponse("")
    response["HX-Refresh"] = "true"
    return response


# --- IMP-011: the rows of the report ------------------------------------------------------

#: Rows shown on one page of the list.
ROWS_PER_PAGE = 200

#: Everything but the unchanged rows – the filter shown first when there are other rows.
CHANGES = "changes"
ALL = "all"

#: The outcome of a row in words, for the badge in the list.
OUTCOME_LABELS = {
    import_rows.NEW: pgettext_lazy("import row", "new"),
    import_rows.CHANGED: pgettext_lazy("import row", "changed"),
    import_rows.UNCHANGED: pgettext_lazy("import row", "unchanged"),
    import_rows.ERROR: pgettext_lazy("import row", "error"),
}

#: The choices of the filter, in their order.
FILTER_LABELS = {
    CHANGES: _("All except unchanged"),
    ALL: _("All"),
    import_rows.NEW: _("New"),
    import_rows.CHANGED: _("Changed"),
    import_rows.UNCHANGED: _("Unchanged"),
    import_rows.ERROR: _("Errors"),
}


def _row_matches(row: dict[str, Any], show: str, search: str) -> bool:
    """Whether a row of the report passes the filter and the search (row number, ID or name)."""
    if show == CHANGES and row["status"] == import_rows.UNCHANGED:
        return False
    if show not in (CHANGES, ALL) and row["status"] != show:
        return False
    if not search:
        return True
    # A number is a row of the file as well – unless it starts with 0 like an ID ("0310").
    is_row = search.isdigit() and not search.startswith("0") and row["row"] == int(search)
    return is_row or search in row["label"].casefold()


def row_list(request: HttpRequest, report: dict[str, Any], *, job: int | None = None) -> dict[str, Any] | None:
    """The rows of a report for the page: filtered, searched, one page of 200 (IMP-011).

    ``?show=`` picks the outcome (default: all but the unchanged rows if
    there are others, else all), ``?q=`` searches row number, ID and name,
    ``?page=`` turns the pages. ``job`` is kept in the filter of a finished
    import, whose report has an address of its own. A report from before
    Has no rows: ``None``.
    """
    rows = report.get("rows")
    if rows is None:
        return None
    counts = {**import_rows.count([]), **(report.get("row_counts") or import_rows.count(rows))}
    total = len(rows)
    default = CHANGES if counts[import_rows.UNCHANGED] and total > counts[import_rows.UNCHANGED] else ALL
    show = request.GET.get("show", "")
    if show not in FILTER_LABELS:
        show = default
    search = request.GET.get("q", "").strip()[:100]
    folded = search.casefold()
    selected = [row for row in rows if _row_matches(row, show, folded)]
    # UIX-050 (UIX-012): 200 rows a page unless the user chose another number.
    page: Page[Any] = paginate(request, selected, default=ROWS_PER_PAGE)
    amounts = {CHANGES: total - counts[import_rows.UNCHANGED], ALL: total, **counts}
    return {
        "page": page,
        "show": show,
        "show_label": FILTER_LABELS[show],
        "q": search,
        "job": job,
        "choices": [(value, label, amounts[value]) for value, label in FILTER_LABELS.items()],
        "outcomes": OUTCOME_LABELS,
        "total": total,
        # The material import checks the other rows only when no row has an error (IMP-009).
        "incomplete": bool(report.get("errors")) and total < (report.get("rows_read") or 0),
    }


def import_page(request: HttpRequest, key: str) -> HttpResponse:
    """The import of one list; ``key`` is ``material``, ``products``, ``customers`` or ``people``."""
    try:
        kind = imports.get(key)
    except LookupError as error:
        raise Http404 from error
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login

        return redirect_to_login(request.get_full_path())
    if not request_rights(request).can_write(kind.module):
        raise PermissionDenied
    context: dict[str, Any] = {"kind": kind}
    session_key = _session_key(kind)
    stored = request.session.get(session_key)
    step = request.POST.get("step", "")

    if request.method == "GET" and request.GET.get("job", "").isdigit():
        # IMP-011: the report of a finished import, with filter and pages in its address.
        done = _finished_import(request, kind, int(request.GET["job"]))
        if done is not None:
            report = (done.result or {}).get("report") or {}
            context.update({"report": report, "finished": True, "rows": row_list(request, report, job=done.pk)})
            return render(request, "core/import.html", context)

    if request.method == "POST" and step == "upload":
        form = ImportUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded = form.cleaned_data["file"]
            try:
                validate_import_upload(uploaded)
            except ValidationError as error:
                form.add_error("file", error)
            else:
                _discard(request, kind)
                request.session[session_key] = {"file": imports.store_upload(uploaded), "original": uploaded.name}
                return redirect(request.path)
        return render(request, "core/import.html", {**context, "upload_form": form})

    if request.method == "POST" and step == "discard":
        _discard(request, kind)
        return redirect(request.path)

    if not stored:
        return render(request, "core/import.html", {**context, "upload_form": ImportUploadForm()})

    job = None
    if stored.get("job"):
        job = BackgroundJob.objects.filter(pk=stored["job"], created_by=request.user).first()
    if job is not None and job.is_finished and request.method == "GET":
        report = (job.result or {}).get("report")
        if report and report["ok"] and not job.params["dry_run"]:
            if request.headers.get("HX-Request"):
                # The progress block noticed the end: the whole page shows the result.
                return _refresh()
            # Done: the file was removed by the task. IMP-011: the report keeps an address of its own,
            # so that its rows can be filtered and paged.
            request.session.pop(session_key, None)
            return redirect(f"{request.path}?job={job.pk}")

    try:
        table = _file_summary(request, kind, stored)
    except (ImportFileError, OSError) as error:
        _discard(request, kind)
        messages.error(request, str(error))
        return redirect(request.path)
    stored = request.session[session_key]

    mapping = suggest_mapping(table.headers, kind.fields)
    # IMP-014: the choices for the whole file – as last chosen for this file, else the defaults.
    chosen = kind.clean_options(stored.get("options"))
    if request.method == "POST" and step in {"check", "import"}:
        overrides = {field.key: request.POST.get(f"map_{field.key}", "") for field in kind.fields}
        chosen = kind.clean_options({option.key: request.POST.get(f"opt_{option.key}", "") for option in kind.options})
        try:
            mapping = resolve_mapping(table.headers, overrides, kind.fields)
        except ImportFileError as error:
            messages.error(request, str(error))
        else:
            job = imports.start(
                kind,
                stored["file"],
                stored["original"],
                mapping,
                dry_run=step == "check",
                user=request.user,
                options=chosen,
            )
            request.session[session_key] = {**stored, "job": job.pk, "options": chosen}
            return redirect(request.path)

    if job is not None:
        if request.headers.get("HX-Request"):
            # The progress block asks every two seconds; when the task is done the whole page is shown anew.
            if job.is_finished:
                return _refresh()
            return render(request, "core/_import_job.html", {"kind": kind, "job": job})
        mapping = {key: (int(index) if index is not None else None) for key, index in job.params["mapping"].items()}
        chosen = kind.clean_options(job.params.get("options"))
        context["job"] = job
        if job.is_finished:
            report = (job.result or {}).get("report")
            if job.status == JobStatus.FAILED or report is None:
                messages.error(request, job.message or str(_("The task failed.")))
            else:
                context["report"] = report
                context["rows"] = row_list(request, report)

    context.update(
        {
            "original_name": stored["original"],
            "table": table,
            "sample": table.sample,
            "mapping_rows": [(field, mapping.get(field.key)) for field in kind.fields],
            "option_rows": [(option, chosen.get(option.key, "")) for option in kind.options],
        }
    )
    return render(request, "core/import.html", context)


@dataclass(frozen=True)
class FileSummary:
    """What the page shows of an uploaded file: headings, first rows, number of rows (IMP-011)."""

    headers: list[str]
    #: The first rows, every value as the text the page shows (``None`` for an empty cell).
    sample: list[list[str | None]]
    count: int


def _file_summary(request: HttpRequest, kind: imports.ImportKind, stored: dict[str, Any]) -> FileSummary:
    """Headings, first rows and length of the uploaded file – read once, then kept in the session.

    IMP-011: the list of rows is turned over page by page; reading a
    file of 20,000 rows each time (seconds for XLSX) would make every page
    slow. The file itself is still checked to exist.

    Raises:
        ImportFileError: The file cannot be read (any more).
        OSError: The file is gone.
    """
    path = imports.stored_path(stored["file"])
    summary = stored.get("summary")
    if summary is not None:
        if not path.exists():
            raise ImportFileError(str(_("The uploaded file is no longer there. Please upload it again.")))
        return FileSummary(summary["headers"], summary["sample"], summary["count"])
    table = read_table(path, stored["original"])
    sample = [[None if value in (None, "") else str(value) for value in row] for row in table.sample()]
    request.session[_session_key(kind)] = {
        **stored,
        "summary": {"headers": table.headers, "sample": sample, "count": len(table.rows)},
    }
    return FileSummary(table.headers, sample, len(table.rows))


def _finished_import(request: HttpRequest, kind: imports.ImportKind, pk: int) -> BackgroundJob | None:
    """A finished import of this list by this user, whose report is shown with ``?job=`` (IMP-011)."""
    job = BackgroundJob.objects.filter(pk=pk, kind="import", created_by=request.user).first()
    if job is None or not job.is_finished or job.params.get("kind") != kind.key or job.params.get("dry_run"):
        return None
    report = (job.result or {}).get("report")
    return job if report and report.get("ok") else None


def import_format_export(request: HttpRequest, key: str) -> HttpResponseBase:
    """The list of an import as a CSV file in the import's format (IMP-017; IMP-005).

    Next to the import under Settings → Import and export and on the import page. Reading the module is
    enough, as for the CSV file of the list; columns of prices, purchase prices and rates only with their
    right (``core.import_exports``). The file is written while it is sent, also for 20,000 items.
    """
    from rentalars.core import import_exports

    try:
        export = import_exports.get(key)
    except LookupError as error:
        raise Http404 from error
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login

        return redirect_to_login(request.get_full_path())
    rights = request_rights(request)
    if not rights.can_read(export.kind.module):
        raise PermissionDenied
    return import_exports.response(export, rights)
