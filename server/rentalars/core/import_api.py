# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the imports: material, products, customers, people (IMP-001 to IMP-004, NFA-041)."""

from __future__ import annotations

import json
from typing import Any, ClassVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from rentalars.api.views import RightsViewMixin, body_of
from rentalars.core import import_rows, imports
from rentalars.core.tabular import ImportFileError, read_table, resolve_mapping
from rentalars.core.uploads import validate_import_upload

KIND_PARAMETER = OpenApiParameter(
    "kind",
    OpenApiTypes.STR,
    OpenApiParameter.PATH,
    enum=["material", "products", "customers", "people"],
    description="Which list is imported.",
)

#: IMP-011: the rows of a report, as the answer and the result of a task in the background hold them.
ROWS_FIELD = inline_serializer(
    "ImportRow",
    {
        "row": serializers.IntegerField(help_text="The number of the row in the file (the heading row is 1)."),
        "label": serializers.CharField(help_text="Short label of the record: ID or article number and name."),
        "status": serializers.ChoiceField(
            choices=list(import_rows.OUTCOMES),
            help_text="new, changed, unchanged or error. An unchanged row has only row, label and status.",
        ),
        "changes": inline_serializer(
            "ImportRowChange",
            {
                "field": serializers.CharField(help_text="The field, e.g. serial_number or model.specification."),
                "label": serializers.CharField(help_text="The field as the pages name it."),
                "old": serializers.CharField(required=False, help_text="The value before, written for reading."),
                "new": serializers.CharField(required=False, help_text="The value after, written for reading."),
                "hidden": serializers.BooleanField(
                    required=False,
                    help_text="True: the caller may not see the values (prices, purchase prices, rates); "
                    "old and new are left out.",
                ),
            },
            many=True,
            required=False,
        ),
        "notes": serializers.ListField(child=serializers.CharField(), required=False),
        "errors": serializers.ListField(
            child=serializers.CharField(), required=False, help_text="Why the row cannot be imported."
        ),
    },
    many=True,
    help_text=(
        "Every row of the file with its outcome (IMP-011). Customers also have name, outcome "
        "(created, merged, unchanged, error), customer, found_by and text. In a material list with errors in "
        "its cells only the rows with errors are listed."
    ),
)


def _yes(value: Any, default: bool) -> bool:
    if value in (None, ""):
        return default
    return str(value).lower() not in {"false", "0", "no", "nein"}


def _options(kind: imports.ImportKind, data: Any) -> dict[str, Any]:
    """IMP-014: the choices for the whole file; an unknown value is refused, a missing one takes the default."""
    given: dict[str, Any] = {}
    for option in kind.options:
        value = data.get(option.key)
        if value in (None, ""):
            continue
        allowed = [choice for choice, _label in option.choice_list()]
        if str(value) not in allowed:
            raise ValidationError({option.key: _("Choose one of: %(values)s.") % {"values": ", ".join(allowed)}})
        given[option.key] = str(value)
    return kind.clean_options(given)


class ImportView(RightsViewMixin, APIView):
    """``/imports/{kind}`` – import a list or try it out (IMP-001 to IMP-004).

    ``GET`` lists the fields the import can fill and the headings it
    recognises. ``POST`` takes the file as ``file`` (multipart).
    ``dry_run`` defaults to true: the answer then reports what would happen
    without writing anything. ``mapping`` is optional JSON such as
    ``{"name": "Gerät"}`` that assigns columns by hand. IMP-014: the
    choices of a list for the whole file are form fields of their own – for
    the material ``prices`` (``net`` or ``gross``) and ``price_tax_rate`` (the
    percentage gross prices include).

    Within the request a file may have up to 5,000 rows
    (``MAX_IMPORT_ROWS_PER_REQUEST``). With ``background`` the import runs as
    a task in the background without that limit: the answer is the task
    (status 202), ``/jobs/{id}`` tells how far it got and holds the report
    in ``result`` when it is done (NFA-041).

    IMP-011: the report lists every row of the file in ``rows`` –
    ``new``, ``changed`` with every changed field old → new, ``unchanged``,
    or ``error`` with its messages – and counts them in ``row_counts``.
    Values the caller may not see (prices, purchase prices, rates) are
    marked ``hidden`` and left out.
    """

    permission_classes: ClassVar[list[Any]] = [IsAuthenticated]
    parser_classes: ClassVar[list[Any]] = [MultiPartParser, FormParser]
    schema_tag = "imports"

    def import_kind(self, key: str, *, write: bool) -> imports.ImportKind:
        """The import, if the caller may use it."""
        try:
            kind = imports.get(key)
        except LookupError as error:
            raise NotFound(_("There is no import “%(kind)s”.") % {"kind": key}) from error
        allowed = self.rights.can_write(kind.module) if write else self.rights.can_read(kind.module)
        if not allowed:
            raise PermissionDenied
        return kind

    @extend_schema(
        parameters=[KIND_PARAMETER],
        responses={
            200: inline_serializer(
                "ImportFields",
                {
                    "key": serializers.CharField(),
                    "label": serializers.CharField(),
                    "required": serializers.BooleanField(),
                    "recognised_headings": serializers.ListField(child=serializers.CharField()),
                },
                many=True,
            )
        },
    )
    def get(self, request: Request, kind: str) -> Response:
        """List the fields the import can fill and the headings it recognises."""
        import_kind = self.import_kind(kind, write=False)
        return Response(
            [
                {
                    "key": field.key,
                    "label": field.label,
                    "required": field.required,
                    "recognised_headings": field.recognised_headings,
                }
                for field in import_kind.fields
            ]
        )

    @extend_schema(
        parameters=[KIND_PARAMETER],
        request=inline_serializer(
            "ImportRequest",
            {
                "file": serializers.FileField(),
                "dry_run": serializers.BooleanField(default=True),
                "mapping": serializers.CharField(required=False),
                "sheet": serializers.CharField(required=False),
                "background": serializers.BooleanField(default=False),
                # IMP-014: choices of the material import for the whole file.
                "prices": serializers.ChoiceField(choices=["net", "gross"], required=False),
                "price_tax_rate": serializers.CharField(required=False),
            },
        ),
        responses={
            200: inline_serializer(
                "ImportReport",
                {
                    "ok": serializers.BooleanField(),
                    # IMP-011: what became of every row of the file.
                    "rows": ROWS_FIELD,
                    "row_counts": inline_serializer(
                        "ImportRowCounts",
                        {outcome: serializers.IntegerField() for outcome in import_rows.OUTCOMES},
                        help_text="How many rows have each outcome.",
                    ),
                },
            ),
            202: inline_serializer("ImportStarted", {"id": serializers.IntegerField()}),
        },
    )
    def post(self, request: Request, kind: str) -> Response:
        """Run the import (or the dry run) and return the report, or start it in the background."""
        from rentalars.core.api import JobSerializer

        import_kind = self.import_kind(kind, write=True)
        data = body_of(request)
        uploaded = request.FILES.get("file")
        if uploaded is None:
            raise ValidationError({"file": _("Please send the file to import.")})
        validate_import_upload(uploaded)
        dry_run = _yes(data.get("dry_run"), True)
        background = _yes(data.get("background"), False)
        try:
            overrides = json.loads(data.get("mapping") or "{}")
        except json.JSONDecodeError as error:
            raise ValidationError({"mapping": _("The column mapping is not valid JSON.")}) from error
        if not isinstance(overrides, dict):
            raise ValidationError({"mapping": _("The column mapping is not valid JSON.")})
        try:
            table = read_table(
                uploaded,
                uploaded.name,
                sheet=data.get("sheet") or None,
                max_rows=None if background else settings.MAX_IMPORT_ROWS_PER_REQUEST,
                command=import_kind.command,
            )
            mapping = resolve_mapping(table.headers, overrides, import_kind.fields)
        except ImportFileError as error:
            raise ValidationError({"file": str(error)}) from error
        options = _options(import_kind, data)
        if background:
            uploaded.seek(0)
            name = imports.store_upload(uploaded)
            job = imports.start(
                import_kind,
                name,
                uploaded.name,
                mapping,
                dry_run=dry_run,
                user=request.user,
                sheet=data.get("sheet") or "",
                keep_file=False,
                options=options,
            )
            job.refresh_from_db()
            return Response(JobSerializer(job).data, status=status.HTTP_202_ACCEPTED)
        report = imports.run(
            import_kind, table, mapping, dry_run=dry_run, user=request.user, rights=self.rights, options=options
        )
        body = report.as_dict()
        body["mapping"] = {key: (table.headers[index] if index is not None else None) for key, index in mapping.items()}
        return Response(body, status=status.HTTP_200_OK if report.ok else status.HTTP_400_BAD_REQUEST)


class ImportExportView(RightsViewMixin, APIView):
    """``GET /imports/{kind}/export`` – the list of an import as CSV in the import's format (IMP-017; API-002).

    The same file as "Export in the import format" under Settings → Import and export: the columns of
    the import with their headings, in plain text (names instead of IDs), semicolons, decimal commas,
    UTF-8 with byte order mark. Sent back to ``POST /imports/{kind}`` it changes nothing. Reading the
    module is enough; columns of prices, purchase prices and rates need their special right and are
    left out without it. The file is written while it is sent, also for 20,000 items.
    """

    permission_classes: ClassVar[list[Any]] = [IsAuthenticated]
    schema_tag = "imports"

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "kind",
                OpenApiTypes.STR,
                OpenApiParameter.PATH,
                enum=["material", "products", "customers", "people"],
                description="Which list is exported.",
            )
        ],
        responses={(200, "text/csv"): OpenApiTypes.STR},
    )
    def get(self, request: Request, kind: str) -> Any:
        """Return the list as CSV with the columns of its import, in plain text; sent back to the import it changes nothing."""
        from rentalars.core import import_exports

        try:
            export = import_exports.get(kind)
        except LookupError as error:
            raise NotFound(_("There is no import “%(kind)s”.") % {"kind": kind}) from error
        if not self.rights.can_read(export.kind.module):
            raise PermissionDenied
        return import_exports.response(export, self.rights)
