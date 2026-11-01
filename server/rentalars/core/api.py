# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the core module: settings, number ranges, change log (chapter 8)."""

from __future__ import annotations

import datetime
from typing import Any

import django_filters
from django.utils import timezone
from django.utils.translation import gettext as _
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, serializers, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from rentalars.accounts.rights import Module
from rentalars.api.serializers import CleanModelSerializer
from rentalars.api.views import ModuleAPIView, RightsViewMixin, body_of
from rentalars.core.history import describe, visible_changes
from rentalars.core.models import (
    AccessAction,
    AccessKind,
    AuditLogEntry,
    CompanyProfile,
    NumberRange,
    SystemSettings,
)
from rentalars.core.search import global_search
from rentalars.material import numbering


class CompanyProfileSerializer(CleanModelSerializer):
    """The company's own data (ADM-001). The logo is uploaded in the browser."""

    class Meta:
        model = CompanyProfile
        fields = [
            "name",
            "street",
            "postal_code",
            "city",
            "country",
            "phone",
            "email",
            "website",
            "tax_number",
            "vat_id",
            "bank_name",
            "iban",
            "bic",
            "register_details",
            "payment_terms_days",
            "warehouse_address",  # PRJ-097
            "document_language",  # UIX-029
        ]


class SystemSettingsSerializer(CleanModelSerializer):
    """The settings an administrator can change (ADM-004)."""

    class Meta:
        model = SystemSettings
        fields = [
            "buffer_before_hours",
            "buffer_after_hours",
            "default_start_time",
            "default_end_time",
            "password_min_length",
            "login_max_attempts",
            "login_lockout_minutes",
            "session_idle_minutes",
            "two_factor_for_administrators",
            "max_upload_mb",
            "maps_load_at_once",  # UIX-034
            "mail_tag_prefix",
            "people_see_own_rates",
            "ask_again_on_new_times",  # PER-034
            "invoices_enabled",  # DOK-014
            # ZEI-018: hints at conspicuous time entries; ZEI-019: travel costs per kilometre.
            "time_hints_enabled",  # ZEI-018: all hints on or off
            "time_hint_day_hours",
            "time_hint_break_hours",
            "time_hint_break_minutes",
            "time_hint_long_break_hours",
            "time_hint_long_break_minutes",
            "time_hint_rest_hours",
            "expense_km_rate",
            "expense_deduct_commute",  # ZEI-027
            "api_requests_per_minute",
            "retention_security_log_days",
            "retention_change_log_days",
            "retention_notifications_days",
            "retention_jobs_days",
            "retention_access_log_days",
        ]
        # ADM-014: the example of the tag with a project number of today.


class SettingsSerializer(serializers.Serializer):
    """Company profile and system settings in one document."""

    company = CompanyProfileSerializer()
    system = SystemSettingsSerializer()


class SettingsView(ModuleAPIView):
    """``GET/PATCH /settings`` – company profile and system settings."""

    module = Module.ADMINISTRATION
    schema_tag = "settings"

    def _document(self) -> dict[str, Any]:
        return {
            "company": CompanyProfileSerializer(CompanyProfile.load()).data,
            "system": SystemSettingsSerializer(SystemSettings.load()).data,
        }

    @extend_schema(responses=SettingsSerializer)
    def get(self, request: Request) -> Response:
        """Return both groups of settings."""
        return Response(self._document())

    @extend_schema(request=SettingsSerializer, responses=SettingsSerializer)
    def patch(self, request: Request) -> Response:
        """Change the values that were sent; everything else stays as it is."""
        parts = (
            ("company", CompanyProfileSerializer, CompanyProfile.load()),
            ("system", SystemSettingsSerializer, SystemSettings.load()),
        )
        serializers_to_save = []
        for key, serializer_class, instance in parts:
            if key in body_of(request):
                serializer = serializer_class(instance, data=body_of(request)[key], partial=True)
                serializer.is_valid(raise_exception=True)
                serializers_to_save.append(serializer)
        for serializer in serializers_to_save:
            serializer.save()
        return Response(self._document())


class NumberRangeSerializer(CleanModelSerializer):
    """A number range with a preview of its next number (ADM-003)."""

    preview = serializers.CharField(read_only=True)

    class Meta:
        model = NumberRange
        fields = ["id", "key", "prefix", "min_digits", "start_value", "next_value", "reset_yearly", "preview"]
        read_only_fields = ["key"]


class NumberRangeViewSet(
    RightsViewMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """``/number-ranges`` – the ranges are fixed; their format and counter can be changed."""

    module = Module.ADMINISTRATION
    schema_tag = "settings"
    queryset = NumberRange.objects.all()
    serializer_class = NumberRangeSerializer
    pagination_class = None

    def perform_update(self, serializer: Any) -> None:
        """Save and forget the cached width of material IDs."""
        serializer.save()
        numbering.reset_cache()


class AuditLogFilter(django_filters.FilterSet):
    """Filters of the change log: object, user and period (ADM-005)."""

    object_type = django_filters.CharFilter(method="filter_object_type", help_text="e.g. projects.project")
    object_id = django_filters.CharFilter(field_name="object_id")
    user = django_filters.NumberFilter(field_name="actor_id")
    since = django_filters.IsoDateTimeFilter(field_name="timestamp", lookup_expr="gte")
    until = django_filters.IsoDateTimeFilter(field_name="timestamp", lookup_expr="lte")

    class Meta:
        model = AuditLogEntry
        fields = ["action", "event"]

    def filter_object_type(self, queryset: Any, name: str, value: str) -> Any:
        """Filter by ``app.model``."""
        app_label, _separator, model = value.partition(".")
        return queryset.filter(content_type__app_label=app_label, content_type__model=model.lower())


class AuditLogSerializer(serializers.ModelSerializer):
    """One entry of the change log."""

    object_type = serializers.SerializerMethodField()
    changes = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()

    class Meta:
        model = AuditLogEntry
        fields = [
            "id",
            "timestamp",
            "actor",
            "actor_label",
            "action",
            "event",
            "object_type",
            "object_id",
            "object_repr",
            "changes",
            "summary",
        ]

    def get_object_type(self, entry: AuditLogEntry) -> str:
        """``app.model`` of the changed object."""
        return f"{entry.content_type.app_label}.{entry.content_type.model}"

    def get_changes(self, entry: AuditLogEntry) -> dict[str, Any]:
        """The raw changes without the values the caller may not see (AUT-019)."""
        return visible_changes(entry, self.context["rights"])

    def get_summary(self, entry: AuditLogEntry) -> str:
        """A readable one-line description."""
        return describe([entry], self.context["rights"])[0].summary


class AuditLogViewSet(RightsViewMixin, viewsets.ReadOnlyModelViewSet):
    """``/audit-log`` – the system-wide change log (ADM-005)."""

    module = Module.ADMINISTRATION
    schema_tag = "settings"
    queryset = AuditLogEntry.objects.select_related("actor", "content_type")
    serializer_class = AuditLogSerializer
    filterset_class = AuditLogFilter
    ordering_fields = ["timestamp"]
    search_fields = ["object_repr", "actor_label"]

    def get_serializer_context(self) -> dict[str, Any]:
        """Pass the caller's rights to the serializer."""
        context = super().get_serializer_context()
        context["rights"] = self.rights
        return context


class SearchView(RightsViewMixin, APIView):
    """``GET /search?q=…`` – the global search across modules (UIX-002).

    Only modules the caller may read are searched; the answer never mentions
    the others.
    """

    permission_classes = [IsAuthenticated]
    schema_tag = "search"

    @extend_schema(
        parameters=[OpenApiParameter("q", str, required=True, description="Search text")],
        responses={
            200: inline_serializer(
                "SearchResult",
                {
                    "results": inline_serializer(
                        "SearchGroup",
                        {
                            "kind": serializers.CharField(),
                            "label": serializers.CharField(),
                            "hits": inline_serializer(
                                "SearchHit",
                                {
                                    "id": serializers.IntegerField(),
                                    "title": serializers.CharField(),
                                    "subtitle": serializers.CharField(),
                                },
                                many=True,
                            ),
                        },
                        many=True,
                    )
                },
            )
        },
    )
    def get(self, request: Request) -> Response:
        """Return the hits grouped by kind of record."""
        groups = global_search(request.query_params.get("q", ""), self.rights, request.user)
        return Response(
            {
                "results": [
                    {
                        "kind": group.kind,
                        "label": group.label,
                        "hits": [{"id": hit.id, "title": hit.title, "subtitle": hit.subtitle} for hit in group.hits],
                    }
                    for group in groups
                ]
            }
        )


class SelfCheckView(ModuleAPIView):
    """``GET /self-check`` – the state of the installation (NFA-037, NFA-049, ADM-008).

    The same checks as the page "Self-check" and the command ``rentalars
    selfcheck``: versions, the server, database, files, mail, backup, space,
    security. ``state`` is ``ok``, ``note``, ``warning`` or ``error`` per
    finding and overall. ``resources`` gives what the server has and uses as
    numbers – bytes and seconds; a value the server does not tell is
    ``null`` (ADM-008). Needs read access to the administration.
    """

    module = Module.ADMINISTRATION
    schema_tag = "administration"

    @extend_schema(
        responses={
            200: inline_serializer(
                "SelfCheck",
                {
                    "state": serializers.CharField(),
                    "findings": inline_serializer(
                        "SelfCheckFinding",
                        {
                            "group": serializers.CharField(),
                            "title": serializers.CharField(),
                            "state": serializers.CharField(),
                            "detail": serializers.CharField(),
                        },
                        many=True,
                    ),
                    "resources": inline_serializer(
                        "ServerResources",
                        {
                            "cores": serializers.IntegerField(allow_null=True),
                            "load": serializers.ListField(
                                child=serializers.FloatField(), allow_null=True, help_text="1, 5 and 15 minutes"
                            ),
                            "memory_total": serializers.IntegerField(allow_null=True),
                            "memory_available": serializers.IntegerField(allow_null=True),
                            "own_memory": serializers.IntegerField(allow_null=True),
                            "own_processes": serializers.IntegerField(),
                            "hostname": serializers.CharField(),
                            "interfaces": inline_serializer(
                                "NetworkInterface",
                                {
                                    "name": serializers.CharField(),
                                    "addresses": serializers.ListField(child=serializers.CharField()),
                                    "received_bytes": serializers.IntegerField(allow_null=True),
                                    "sent_bytes": serializers.IntegerField(allow_null=True),
                                },
                                many=True,
                            ),
                            "uptime_seconds": serializers.FloatField(allow_null=True),
                        },
                        allow_null=True,
                    ),
                },
            )
        }
    )
    def get(self, request: Request) -> Response:
        """Run the checks."""
        from rentalars.core.selfcheck import run_checks, summary_for_api

        return Response(summary_for_api(run_checks()))


# --- Data protection and operation: access log, encryption, backup (AUT-028, ADM-009, ADM-010) ----------


def _moment(value: str, *, end: bool = False) -> datetime.datetime | None:
    """A day ``2027-03-01`` or a moment ``2027-03-01T08:00``; for ``end`` a day counts up to its end."""
    from django.utils.dateparse import parse_date, parse_datetime

    from rentalars.core.listing import end_of_day, start_of_day

    if not value:
        return None
    try:
        moment = parse_datetime(value)
        if moment is not None:
            return moment if timezone.is_aware(moment) else timezone.make_aware(moment)
        day = parse_date(value)
    except ValueError:
        day = None
    if day is None:
        raise ValidationError(
            {"since" if not end else "until": _("Give a day as 2027-03-01 or a time as 2027-03-01T08:00.")}
        )
    return end_of_day(day) if end else start_of_day(day)


def _access_document(entry: Any) -> dict[str, Any]:
    return {
        "id": entry.pk,
        "timestamp": entry.timestamp,
        "user": entry.user_id,
        "username": entry.user_label,
        "ip_address": entry.ip_address,
        "action": entry.action,
        "object_type": entry.object_type,
        "object_id": entry.object_id,
        "label": entry.label,
        "parent_type": entry.parent_type,
        "parent_id": entry.parent_id,
        "path": entry.path,
    }


class AccessLogView(ModuleAPIView):
    """``GET /access-log`` – who read which record, when and from where (AUT-028).

    One entry per access: ``action`` is ``view`` (a page was opened),
    ``download`` (a file was fetched), ``export`` (data left as a file) or
    ``api``. Filters: ``user`` (ID), ``object_type`` and ``object_id`` (one
    record together with what belongs to it – the mails, files and documents
    of a project), ``action``, ``since`` and ``until`` (a day ``2027-03-01``
    or a moment), ``q`` (label, user name, address, start of the IP address).
    Newest first, 50 per page. Needs read access to the administration.
    """

    module = Module.ADMINISTRATION
    schema_tag = "administration"

    @extend_schema(
        parameters=[
            OpenApiParameter("user", int, description="ID of the user who read."),
            OpenApiParameter("object_type", str, enum=AccessKind.values),
            OpenApiParameter("object_id", str, description="Key of the record; with object_type."),
            OpenApiParameter("action", str, enum=AccessAction.values),
            OpenApiParameter("since", str, description="From this day or moment on."),
            OpenApiParameter("until", str, description="Up to and including this day, or up to this moment."),
            OpenApiParameter("q", str, description="Found in label, user name, address or IP address."),
        ],
        responses={
            200: inline_serializer(
                "AccessLog",
                {
                    "count": serializers.IntegerField(),
                    "results": inline_serializer(
                        "AccessLogEntry",
                        {
                            "id": serializers.IntegerField(),
                            "timestamp": serializers.DateTimeField(),
                            "user": serializers.IntegerField(allow_null=True),
                            "username": serializers.CharField(),
                            "ip_address": serializers.CharField(allow_null=True),
                            "action": serializers.CharField(),
                            "object_type": serializers.CharField(),
                            "object_id": serializers.CharField(),
                            "label": serializers.CharField(),
                            "parent_type": serializers.CharField(),
                            "parent_id": serializers.CharField(),
                            "path": serializers.CharField(),
                        },
                        many=True,
                    ),
                },
            )
        },
    )
    def get(self, request: Request) -> Response:
        """The entries, paginated."""
        from rentalars.api.pagination import StandardPagination
        from rentalars.core.access_log import filtered_entries

        params = request.query_params
        kind = str(params.get("object_type", ""))
        if kind and kind not in AccessKind.values:
            raise ValidationError({"object_type": _("Unknown kind of object.")})
        action = str(params.get("action", ""))
        if action and action not in AccessAction.values:
            raise ValidationError({"action": _("Unknown kind of access.")})
        user = str(params.get("user", ""))
        entries = filtered_entries(
            user=int(user) if user.isdigit() else None,
            kind=kind,
            object_id=str(params.get("object_id", "")).strip() if kind else "",
            action=action,
            since=_moment(str(params.get("since", ""))),
            until=_moment(str(params.get("until", "")), end=True),
            text=str(params.get("q", "")).strip(),
        ).order_by("-timestamp", "-id")
        paginator = StandardPagination()
        page = paginator.paginate_queryset(entries, request, view=self)
        return paginator.get_paginated_response([_access_document(entry) for entry in page or []])


class EncryptionView(ModuleAPIView):
    """``GET /encryption`` – what is encrypted (ADM-009, NFA-067).

    Whether the database server encrypts its tables (``null`` on SQLite or
    when the server does not say), whether new backups are encrypted, whether
    the last nightly backup was, whether a recovery key exists. Switching it
    on is done on the server, as root: ``command`` names the command – it
    changes the settings of MariaDB and restarts it, which the application
    may not do. Needs read access to the administration.
    """

    module = Module.ADMINISTRATION
    schema_tag = "administration"

    @extend_schema(
        responses={
            200: inline_serializer(
                "Encryption",
                {
                    "database_encrypted": serializers.BooleanField(allow_null=True),
                    "database_detail": serializers.CharField(),
                    "database_is_local": serializers.BooleanField(),
                    "backups_encrypted": serializers.BooleanField(),
                    "last_backup_encrypted": serializers.BooleanField(allow_null=True),
                    "recovery_key_exists": serializers.BooleanField(),
                    "complete": serializers.BooleanField(),
                    "command": serializers.CharField(),
                },
            )
        }
    )
    def get(self, request: Request) -> Response:
        """The state of the encryption."""
        from rentalars.core.backup import encryption_state

        return Response(encryption_state().as_dict())


# --- Tasks in the background (NFA-041) ----------------------------------------------------------


class JobSerializer(serializers.Serializer):
    """A task in the background with its state."""

    id = serializers.IntegerField()
    kind = serializers.CharField()
    title = serializers.CharField()
    status = serializers.CharField()
    progress = serializers.IntegerField()
    message = serializers.CharField()
    result_name = serializers.CharField()
    result_url = serializers.SerializerMethodField()
    #: What the task found, e.g. ``{"report": …}`` of an import (IMP-003).
    result = serializers.JSONField()
    created_at = serializers.DateTimeField()
    finished_at = serializers.DateTimeField(allow_null=True)

    def get_result_url(self, job: Any) -> str:
        """Where the result can be fetched once it is there."""
        return f"/api/v1/jobs/{job.pk}/result" if job.result_file else ""


def _own_job(request: Request, pk: int) -> Any:
    from django.http import Http404
    from django.shortcuts import get_object_or_404

    from rentalars.core.models import BackgroundJob

    job = get_object_or_404(BackgroundJob, pk=pk)
    # Only the one who started it: a result can hold the data of everybody (the full export, IMP-006).
    if job.created_by_id is None or job.created_by_id != request.user.pk:
        raise Http404
    return job


class JobView(APIView):
    """``/jobs/{id}``: how far a task got (NFA-041). Only for the one who started it, or administrators."""

    permission_classes = [IsAuthenticated]
    schema_tag = "jobs"

    @extend_schema(responses=JobSerializer)
    def get(self, request: Request, pk: int) -> Response:
        """The state of the task."""
        return Response(JobSerializer(_own_job(request, pk)).data)


class JobResultView(APIView):
    """``/jobs/{id}/result``: the file the task made."""

    permission_classes = [IsAuthenticated]
    schema_tag = "jobs"

    @extend_schema(responses={(200, "application/octet-stream"): bytes})
    def get(self, request: Request, pk: int) -> Any:
        """The file."""
        from django.http import Http404

        from rentalars.core.uploads import document_response

        job = _own_job(request, pk)
        if not job.result_file:
            raise Http404
        return document_response(job.result_file.name, job.result_name or "ergebnis")


class FullExportView(RightsViewMixin, APIView):
    """``POST /exports/full`` – start the full export of all data (IMP-006).

    Only for administrators (administration with delete right). The answer
    is the task (status 202); ``/jobs/{id}/result`` delivers the ZIP file
    when it is done.
    """

    permission_classes = [IsAuthenticated]
    schema_tag = "jobs"

    @extend_schema(request=None, responses={202: JobSerializer})
    def post(self, request: Request) -> Response:
        """Start the export in the background."""
        from rest_framework import status
        from rest_framework.exceptions import PermissionDenied

        from rentalars.core import export

        if not self.rights.can_delete(Module.ADMINISTRATION):
            raise PermissionDenied
        job = export.start(request.user)
        job.refresh_from_db()
        return Response(JobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class BackupJobSerializer(JobSerializer):
    """A backup made through the API or in the browser, with the key of an encrypted one (ADM-010)."""

    key = serializers.SerializerMethodField(
        help_text="The key of this backup if backups are encrypted, else null. Keep it apart from the file."
    )
    encrypted = serializers.SerializerMethodField()

    def get_key(self, job: Any) -> str | None:
        """The key, for the one who made the backup."""
        from rentalars.core.backup import key_of

        return key_of(job)

    def get_encrypted(self, job: Any) -> bool:
        """Whether the backup is (or will be) encrypted."""
        return bool((job.params or {}).get("key")) or bool((job.result or {}).get("encrypted"))


class BackupView(RightsViewMixin, APIView):
    """``/backups`` – a backup in the format of ``sudo rentalars backup`` for download (ADM-010).

    ``POST`` starts it in the background and answers with the task (status
    202); ``/jobs/{id}`` tells how far it got, and ``/jobs/{id}/result``
    delivers the ``.tar.gz`` when it is done – to the one who started it
    only. ``sudo rentalars restore FILE`` puts it back on the server. When
    backups are encrypted, the file is ``.tar.gz.enc``, encrypted like the
    nightly backup but with a key of its own: ``key`` in the answer
    (``--key-file`` of ``rentalars restore``). ``GET`` lists the caller's own
    backups of the last days. Only for administrators (administration with
    delete right), like the full export.
    """

    permission_classes = [IsAuthenticated]
    schema_tag = "jobs"

    def _check(self) -> None:
        from rest_framework.exceptions import PermissionDenied

        if not self.rights.can_delete(Module.ADMINISTRATION):
            raise PermissionDenied

    @extend_schema(responses=BackupJobSerializer(many=True))
    def get(self, request: Request) -> Response:
        """The own backups, newest first."""
        from rentalars.core.models import BackgroundJob

        self._check()
        jobs = BackgroundJob.objects.filter(kind="backup", created_by=request.user)[:20]
        return Response(BackupJobSerializer(jobs, many=True).data)

    @extend_schema(request=None, responses={202: BackupJobSerializer})
    def post(self, request: Request) -> Response:
        """Start the backup in the background."""
        from rest_framework import status
        from rest_framework.exceptions import ValidationError as BadRequest

        from rentalars.core import backup

        self._check()
        try:
            job = backup.start(request.user)
        except backup.BackupError as error:
            raise BadRequest({"backup": [str(error)]}) from error
        job.refresh_from_db()
        return Response(BackupJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)
