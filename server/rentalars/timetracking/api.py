# SPDX-License-Identifier: GPL-3.0-or-later
"""API of time tracking: entries, stopwatch, approval, report (chapter 8).

The rules are those of the browser pages, because both call
``timetracking.services`` (API-002): everybody records and sees their own
times; recording for others, approving and rejecting need the special right
"approve times and record them for others" (ZEI-011, ZEI-013).
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Level, Module
from rentalars.api.views import ModuleAPIView, ModuleViewSet, body_of
from rentalars.core.i18n import file_name, local_pattern
from rentalars.core.listing import end_of_day, start_of_day
from rentalars.personnel.models import JobFunction, Person
from rentalars.projects.access import person_of
from rentalars.projects.models import CrewLine, Project
from rentalars.timetracking import services
from rentalars.timetracking.display import attach_pay_kinds
from rentalars.timetracking.export import report_csv
from rentalars.timetracking.hints import TimeHint, hint_documents, hints_for
from rentalars.timetracking.models import TimeEntry, TimeEntryStatus
from rentalars.timetracking.pdf import render_timesheet_pdf, timesheet_is_too_long, too_long_message


def filter_by_ids(entries: Any, params: Any) -> Any:
    """Narrow entries by ``person``, ``project`` and ``job_function``; ``project=none`` means without project."""
    for name in ("person", "project", "job_function"):
        value = params.get(name, "")
        if value.isdigit():
            entries = entries.filter(**{f"{name}_id": int(value)})
        elif name == "project" and value == "none":
            entries = entries.filter(project__isnull=True)
    return entries


def entry_document(entry: TimeEntry, *, with_rate: bool, hints: list[TimeHint] | None = None) -> dict[str, Any]:
    """A time entry as JSON (ZEI-004). Rate and amount only where the caller may see them (AUT-019, PER-010).

    ``hints`` (ZEI-018): a long working day, a short break or rest of the
    entry's working day, as ``[{"kind", "message"}]`` – ``long_day``,
    ``short_break``, ``short_rest``. Never blocking; empty for most entries.

    ZEI-025: ``period`` links the parts of a period worked in several job
    functions – each part is an entry with the period's begin, end and
    break and its share in ``hours``; ``period_hours`` are the hours of the
    whole period. Both are ``null`` for an entry that is not divided.

    API-016: with the rate, ``pay_kind`` (``hourly``, ``daily``,
    ``flat``) and ``in_day_rate`` – see :func:`~rentalars.timetracking.display.pay_kind_of`.

    ZEI-028: ``in_flat_rate`` – a further entry of a deployment paid
    flat (``pay_kind: flat``) whose flat rate its first finished entry
    carries, in whatever week that lies; ``false`` for the first entry and
    for every entry not paid flat. "My times" shows the same: the flat rate
    once per deployment, the other entries "in the flat rate".
    """
    document: dict[str, Any] = {
        "id": entry.pk,
        "person": entry.person_id,
        "person_name": entry.person.name,
        "project": entry.project_id,
        "project_number": entry.project.number if entry.project_id else None,
        "job_function": entry.job_function_id,
        "job_function_name": entry.job_function.name,
        "crew_line": entry.crew_line_id,
        "start": entry.start,
        "end": entry.end,
        "break_minutes": entry.break_minutes,
        "hours": entry.hours,
        "note": entry.note,
        "status": entry.status,
        "is_running": entry.is_running,
        "submitted_at": entry.submitted_at,
        "decided_at": entry.decided_at,
        "rejection_reason": entry.rejection_reason,
        "hints": hint_documents(hints or []),
        "period": str(entry.period_key) if entry.period_key else None,
        "period_hours": entry.period_hours if entry.period_key else None,
    }
    if with_rate:
        document["hourly_rate"] = entry.hourly_rate
        document["amount"] = entry.amount
        # API-016 (mobile app): how the entry is paid, as "My times" shows it
        # (ZEI-026) – ``hourly``, ``daily`` or ``flat``; ``in_day_rate``: a further entry of a day already paid
        # by its day rate. Lists note it for all their entries at once (``attach_pay_kinds``).
        if not hasattr(entry, "pay_kind"):
            attach_pay_kinds([entry])
        document["pay_kind"] = entry.pay_kind
        document["in_day_rate"] = entry.pay_in_day_rate
        # ZEI-028: the flat rate counts once per deployment, with its first entry.
        document["in_flat_rate"] = entry.pay_in_flat_rate
    return document


class TimePartSerializer(serializers.Serializer):
    """ZEI-025: one job function of a period with its hours; at most one part may leave ``hours`` out (the rest)."""

    job_function = serializers.PrimaryKeyRelatedField(queryset=JobFunction.objects.all())
    crew_line = serializers.PrimaryKeyRelatedField(queryset=CrewLine.objects.all(), required=False, allow_null=True)
    hours = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)


class TimeEntrySerializer(serializers.Serializer):
    """Input for a time entry (ZEI-004).

    ``person`` may be left out: the entry is then for the person linked to
    the caller's account. ``project`` may be ``null`` or left out: the entry
    is recorded without project and can be approved once one is assigned
    (ZEI-023). ``submit: true`` hands the entry in for approval right away.
    Without ``end`` a stopwatch starts. Begin and end must not lie in the
    future (ZEI-022).

    ZEI-025: ``crew_line`` names the deployment the time counts towards (one
    of ``crew_lines`` in ``/time-entries/choices``); without it the matching
    line is found as before. ``parts`` – two or more ``{job_function,
    crew_line, hours}`` – divide the period into job functions; their hours
    add up to the hours worked, one part may leave them out and gets the
    rest. ``job_function`` is then not needed. An entry without ``parts``
    behaves as before.
    """

    person = serializers.PrimaryKeyRelatedField(queryset=Person.objects.all(), required=False)
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all(), required=False, allow_null=True)
    job_function = serializers.PrimaryKeyRelatedField(queryset=JobFunction.objects.all(), required=False)
    crew_line = serializers.PrimaryKeyRelatedField(queryset=CrewLine.objects.all(), required=False, allow_null=True)
    parts = TimePartSerializer(many=True, required=False)
    start = serializers.DateTimeField()
    end = serializers.DateTimeField(required=False, allow_null=True)
    break_minutes = serializers.IntegerField(required=False, min_value=0, max_value=600)
    note = serializers.CharField(required=False, allow_blank=True, max_length=250)
    submit = serializers.BooleanField(required=False)


class TimeEntryViewSet(ModuleViewSet):
    """``/time-entries`` – recorded hours (ZEI-001 ff.).

    Filters: ``person``, ``project``, ``job_function``, ``status``, ``from``
    and ``to`` (dates). Callers see their own entries; with the right to
    approve also those of others in the projects they may see (NFA-010).
    """

    module = Module.TIME_TRACKING
    serializer_class = TimeEntrySerializer
    queryset = TimeEntry.objects.none()
    # Deleting an own entry that is not approved is part of recording, not a "delete" right.
    action_levels = {"destroy": Level.WRITE}

    def get_queryset(self) -> Any:
        """The entries the caller may see, narrowed by the filters."""
        entries = services.visible_entries(self.rights, self.request.user).select_related(
            "person", "project", "job_function"
        )
        params = self.request.query_params
        entries = filter_by_ids(entries, params)
        if params.get("status") in TimeEntryStatus.values:
            entries = entries.filter(status=params["status"])
        since, until = parse_date(params.get("from", "") or ""), parse_date(params.get("to", "") or "")
        if since:
            entries = entries.filter(start__gte=start_of_day(since))
        if until:
            entries = entries.filter(start__lt=end_of_day(until))
        return entries.order_by("-start", "-id")

    def _document(self, entry: TimeEntry, hints: dict[int, list[TimeHint]] | None = None) -> dict[str, Any]:
        if hints is None:
            hints = hints_for([entry])  # ZEI-018: one entry – its working day is read with one query
        return entry_document(
            entry,
            with_rate=services.may_see_rate_of(self.rights, self.request.user, entry.person),
            hints=hints.get(entry.pk),
        )

    def _person(self, given: Person | None) -> Person:
        """The person an entry is for: the given one, or the caller's own."""
        person = given or person_of(self.request.user)
        if person is None:
            raise ValidationError(
                {"person": _("Your user account is not linked to a person. Name the person the time is for.")}
            )
        return person

    @extend_schema(
        parameters=[
            OpenApiParameter("person", int),
            OpenApiParameter("project", str, description="ID of the project, or ``none`` for entries without project"),
            OpenApiParameter("job_function", int),
            OpenApiParameter("status", str, enum=TimeEntryStatus.values),
            OpenApiParameter("from", str, description="First day, YYYY-MM-DD"),
            OpenApiParameter("to", str, description="Last day, YYYY-MM-DD"),
        ],
        responses={200: inline_serializer("TimeEntryList", {"id": serializers.IntegerField()}, many=True)},
    )
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """List time entries, newest first; each with its ``hints`` (ZEI-018)."""
        page = list(self.paginate_queryset(self.get_queryset()))
        hints = hints_for(page)
        attach_pay_kinds(page)  # API-016: for the whole page at once
        return self.get_paginated_response([self._document(entry, hints) for entry in page])

    @extend_schema(responses={200: inline_serializer("TimeEntryDetail", {"id": serializers.IntegerField()})})
    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """One time entry."""
        return Response(self._document(self.get_object()))

    def _parts(self, values: dict[str, Any]) -> list[services.Part] | None:
        """ZEI-025: the ``parts`` of a request as the services expect them; ``None`` if not given."""
        parts = values.pop("parts", None)
        if parts is None:
            return None
        return [services.Part(part["job_function"], part.get("hours"), part.get("crew_line")) for part in parts]

    def _with_parts(self, entry: TimeEntry) -> dict[str, Any]:
        """The document of an entry; for a divided period with ``parts``, the documents of all its parts (ZEI-025)."""
        rows = getattr(entry, "period_parts", None) or services.period_of(entry)
        hints = hints_for(rows)
        attach_pay_kinds([entry, *(row for row in rows if row is not entry)])  # API-016
        document = self._document(entry, hints)
        if entry.period_key is not None:
            document["parts"] = [self._document(row, hints) for row in rows]
        return document

    @extend_schema(responses={201: inline_serializer("TimeEntryCreated", {"id": serializers.IntegerField()})})
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Record hours (ZEI-004); the hourly rate is fixed on the entry (ZEI-008), overlaps are refused (ZEI-009).

        ZEI-025: with ``parts`` the answer is the first part, and ``parts``
        lists every part of the period.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        parts = self._parts(values)
        if parts:
            values.setdefault("job_function", parts[0].job_function)
        if "job_function" not in values:
            raise ValidationError({"job_function": _("Choose the job function.")})
        entry = services.create_entry(
            person=self._person(values.pop("person", None)),
            rights=self.rights,
            user=request.user,
            project=values.pop("project", None),
            end=values.pop("end", None),
            parts=parts,
            **values,
        )
        return Response(self._with_parts(entry), status=status.HTTP_201_CREATED)

    @extend_schema(responses={200: inline_serializer("TimeEntryUpdated", {"id": serializers.IntegerField()})})
    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Change an entry that is not approved yet (ZEI-012)."""
        entry = self.get_object()
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        if "person" in values and values.pop("person").pk != entry.person_id:
            raise ValidationError(
                {"person": _("The person of an entry cannot be changed. Delete it and record a new one.")}
            )
        submit = values.pop("submit", False)
        parts = self._parts(values)
        if parts is not None:
            # ZEI-025: the job functions of the period replace those it had.
            values.pop("job_function", None)
            values.pop("crew_line", None)
            kept = services.save_period(entry, parts=parts, rights=self.rights, user=request.user, **values)
            entry = next((row for row in kept if row.pk == entry.pk), kept[0])
        else:
            entry = services.update_entry(entry, rights=self.rights, user=request.user, **values)
        if submit:
            services.submit_entries([entry], rights=self.rights, user=request.user)
        return Response(self._with_parts(entry))

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Change single fields of an entry."""
        return self.update(request, *args, **kwargs)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Delete an entry that is not approved yet."""
        services.delete_entry(self.get_object(), rights=self.rights, user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    # --- Stopwatch (ZEI-005) ----------------------------------------------------------------

    @extend_schema(responses={200: inline_serializer("Timer", {"is_running": serializers.BooleanField()})})
    @action(detail=False)
    def timer(self, request: Request) -> Response:
        """The running stopwatch of the caller's person, or ``null`` (ZEI-005)."""
        entry = services.running_timer(person_of(request.user))
        return Response({"running": self._document(entry, {}) if entry else None})

    @extend_schema(
        request=inline_serializer(
            "TimerStart",
            {
                "project": serializers.IntegerField(required=False, allow_null=True),
                "job_function": serializers.IntegerField(required=False),
                "crew_line": serializers.IntegerField(required=False, allow_null=True),
                "person": serializers.IntegerField(required=False),
                "note": serializers.CharField(required=False),
            },
        ),
        responses={201: inline_serializer("TimerStarted", {"id": serializers.IntegerField()})},
    )
    @action(detail=False, methods=["post"], url_path="timer/start")
    def timer_start(self, request: Request) -> Response:
        """Start the stopwatch on a project – or without one (ZEI-023) – and a job function (ZEI-005).

        ZEI-025: ``crew_line`` instead of ``job_function`` names the deployment, and its job function with it.
        """
        body = body_of(request)
        person = self._person(get_object_or_404(Person, pk=body["person"]) if body.get("person") else None)
        crew_line = get_object_or_404(CrewLine, pk=body["crew_line"]) if body.get("crew_line") else None
        job_function = (
            get_object_or_404(JobFunction, pk=body["job_function"])
            if body.get("job_function")
            else (crew_line.job_function if crew_line is not None else get_object_or_404(JobFunction, pk=0))
        )
        entry = services.start_timer(
            person=person,
            project=get_object_or_404(Project, pk=body["project"]) if body.get("project") else None,
            job_function=job_function,
            rights=self.rights,
            user=request.user,
            note=str(body.get("note", "")),
            crew_line=crew_line,
        )
        return Response(self._document(entry, {}), status=status.HTTP_201_CREATED)

    @extend_schema(
        request=inline_serializer(
            "TimerStop",
            {
                "person": serializers.IntegerField(required=False),
                "break_minutes": serializers.IntegerField(required=False),
                "submit": serializers.BooleanField(required=False),
            },
        ),
        responses={200: inline_serializer("TimerStopped", {"id": serializers.IntegerField()})},
    )
    @action(detail=False, methods=["post"], url_path="timer/stop")
    def timer_stop(self, request: Request) -> Response:
        """Stop the stopwatch; the entry ends now (ZEI-005)."""
        body = body_of(request)
        person = self._person(get_object_or_404(Person, pk=body["person"]) if body.get("person") else None)
        try:
            break_minutes = int(body.get("break_minutes") or 0)
        except (TypeError, ValueError) as error:
            raise ValidationError({"break_minutes": _("Enter a number.")}) from error
        entry = services.stop_timer(
            person=person,
            rights=self.rights,
            user=request.user,
            break_minutes=break_minutes,
            submit=bool(body.get("submit")),
        )
        return Response(self._document(entry))

    # --- Approval (ZEI-012, ZEI-013) ------------------------------------------------------------

    def _chosen(self, request: Request) -> list[TimeEntry]:
        """The entries a request names: by ``ids``, or by ``project`` with optional ``from`` and ``to``."""
        body = body_of(request)
        entries = services.visible_entries(self.rights, request.user).select_related(
            "person", "project", "job_function"
        )
        ids = body.get("ids")
        if ids is not None:
            if not isinstance(ids, list) or not all(isinstance(value, int) for value in ids):
                raise ValidationError({"ids": _("Give the IDs as a list of numbers.")})
            return list(entries.filter(pk__in=ids))
        if not body.get("project"):
            raise ValidationError({"ids": _("Name the entries by “ids”, or all submitted entries of a “project”.")})
        entries = entries.filter(project_id=body["project"], status=TimeEntryStatus.SUBMITTED)
        since, until = parse_date(str(body.get("from") or "")), parse_date(str(body.get("to") or ""))
        if since:
            entries = entries.filter(start__gte=start_of_day(since))
        if until:
            entries = entries.filter(start__lt=end_of_day(until))
        return list(entries)

    _CHOICE = inline_serializer(
        "TimeEntryChoice",
        {
            "ids": serializers.ListField(child=serializers.IntegerField(), required=False),
            "project": serializers.IntegerField(required=False),
            "from": serializers.DateField(required=False),
            "to": serializers.DateField(required=False),
            "reason": serializers.CharField(required=False),
        },
    )
    _CHANGED = {200: inline_serializer("TimeEntriesChanged", {"changed": serializers.IntegerField()})}

    @extend_schema(request=_CHOICE, responses=_CHANGED)
    @action(detail=False, methods=["post"])
    def submit(self, request: Request) -> Response:
        """Hand entries in for approval (ZEI-012)."""
        changed = services.submit_entries(self._chosen(request), rights=self.rights, user=request.user)
        return Response({"changed": changed})

    @extend_schema(request=_CHOICE, responses=_CHANGED)
    @action(detail=False, methods=["post"])
    def approve(self, request: Request) -> Response:
        """Approve entries: single ones by ``ids``, or all submitted ones of a project and period (ZEI-013)."""
        changed = services.approve_entries(self._chosen(request), rights=self.rights, user=request.user)
        return Response({"changed": changed})

    @extend_schema(request=_CHOICE, responses=_CHANGED)
    @action(detail=False, methods=["post"])
    def reject(self, request: Request) -> Response:
        """Send entries back with a ``reason`` (ZEI-012)."""
        changed = services.reject_entries(
            self._chosen(request), str(body_of(request).get("reason", "")), rights=self.rights, user=request.user
        )
        return Response({"changed": changed})

    @extend_schema(
        request=inline_serializer("AssignProject", {"project": serializers.IntegerField()}),
        responses={200: inline_serializer("ProjectAssigned", {"id": serializers.IntegerField()})},
    )
    @action(detail=True, methods=["post"], url_path="assign-project")
    def assign_project(self, request: Request, pk: str | None = None) -> Response:
        """Give an entry recorded without project its project, so that it can be approved (ZEI-023).

        Also changes the project of an open entry. The person does it while
        the entry is not approved; an approver for the entries they may see.
        """
        entry = self.get_object()
        project = get_object_or_404(Project, pk=body_of(request).get("project") or 0)
        services.assign_project(entry, project, rights=self.rights, user=request.user)
        return Response(self._document(entry))

    @extend_schema(
        request=inline_serializer(
            "TimeEntryCorrection",
            {
                "project": serializers.IntegerField(required=False),
                "job_function": serializers.IntegerField(required=False),
                "crew_line": serializers.IntegerField(required=False, allow_null=True),
                "start": serializers.DateTimeField(required=False),
                "end": serializers.DateTimeField(required=False),
                "break_minutes": serializers.IntegerField(required=False),
                "note": serializers.CharField(required=False, allow_blank=True),
            },
        ),
        responses={200: inline_serializer("TimeEntryCorrected", {"id": serializers.IntegerField()})},
    )
    @action(detail=True, methods=["post"])
    def correct(self, request: Request, pk: str | None = None) -> Response:
        """Correct a time waiting for approval and approve it in one step (ZEI-030).

        For whoever may approve the entry (ZEI-013): the fields sent change –
        ``project``, ``job_function`` (or ``crew_line``), ``start``, ``end``,
        ``break_minutes``, ``note`` – with the rules of recording; the entry is
        approved, its values before stay in the change log, and the person is
        told. Nothing sent approves it as it is. 400 for an entry that is not
        waiting for approval; 403 without the right, or for a project the
        caller may not approve for.
        """
        entry = self.get_object()
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        for name in ("person", "parts", "submit"):
            if name in values:
                raise ValidationError({name: _("This cannot be changed when correcting a time.")})
        entry = services.correct_and_approve(entry, rights=self.rights, user=request.user, **values)
        return Response(self._with_parts(entry))

    @extend_schema(
        request=None, responses={200: inline_serializer("TimeEntryReopened", {"id": serializers.IntegerField()})}
    )
    @action(detail=True, methods=["post"])
    def reopen(self, request: Request, pk: str | None = None) -> Response:
        """Take back the approval of an entry so that it can be corrected (ZEI-012)."""
        entry = self.get_object()
        services.take_back_approval(entry, rights=self.rights, user=request.user)
        return Response(self._document(entry))

    # --- What can be booked (ZEI-006, ZEI-007) -----------------------------------------------------

    @extend_schema(
        parameters=[OpenApiParameter("person", int, description="Default: the caller's own person")],
        responses={200: inline_serializer("BookableProject", {"project": serializers.IntegerField()}, many=True)},
    )
    @action(detail=False)
    def choices(self, request: Request) -> Response:
        """The projects a person can book on, the most likely first, each with its job functions (ZEI-006, ZEI-007).

        The first project is the one the person is planned in right now;
        ``suggested_job_function`` is the function of that crew line. The last
        entry has ``project: null``: recording without project, with the
        person's own job functions (ZEI-023).

        ZEI-007: ``job_functions`` is never empty – the person's own
        and planned ones first, then those of the project's crew, and for a
        person without job functions on a project without crew every active
        job function.

        ZEI-024: open service cases follow (``reason: "service_case"``,
        ``is_service_case: true``), those the person takes part in first
        (``takes_part``), each with every active job function.

        ZEI-025: ``crew_lines`` are the person's deployments in the project –
        job function, phase and times, and a ``label`` such as "Licht –
        Aufbau, Fr 16.10. 08:00–12:00" – to name as ``crew_line`` of an entry
        or of a part; ``suggested_crew_line`` is the one in progress.
        """
        person_id = request.query_params.get("person", "")
        person = self._person(get_object_or_404(Person, pk=int(person_id)) if person_id.isdigit() else None)
        if not services.may_record_for(self.rights, request.user, person):
            raise PermissionDenied
        choices = services.project_choices(person, self.rights, request.user, service_cases=True)
        lines: dict[int, list[CrewLine]] = {}
        for line in (
            CrewLine.objects.filter(person=person, project_id__in=[choice.project.pk for choice in choices])
            .select_related("job_function", "phase")
            .order_by("start", "id")
        ):
            lines.setdefault(line.project_id, []).append(line)
        every = services.all_job_functions()
        every_function = [{"id": function.pk, "name": function.name} for function in every]

        def functions_of(choice: services.ProjectChoice) -> list[dict[str, Any]]:
            if services.is_open_service_case(choice.project):
                return every_function  # ZEI-024: read once for all cases
            # ZEI-007: never empty – the project's crew functions, else every active one.
            return [
                {"id": function.pk, "name": function.name}
                for function in services.job_functions_for(person, choice.project, every=every)
            ]

        return Response(
            [
                {
                    "project": choice.project.pk,
                    "number": choice.project.number,
                    "name": choice.project.name,
                    "reason": choice.reason,
                    "is_service_case": choice.project.is_service_case,
                    "takes_part": choice.takes_part,
                    "suggested_job_function": choice.job_function.pk if choice.job_function else None,
                    "suggested_crew_line": choice.crew_line.pk if choice.crew_line else None,
                    "job_functions": functions_of(choice),
                    "crew_lines": [
                        {
                            "id": line.pk,
                            "job_function": line.job_function_id,
                            "job_function_name": line.job_function.name,
                            "phase": line.phase.label if line.phase_id else None,
                            "start": line.start,
                            "end": line.end,
                            "label": services.crew_line_label(line),
                        }
                        for line in lines.get(choice.project.pk, [])
                    ],
                }
                for choice in choices
            ]
            + [
                {
                    "project": None,
                    "number": None,
                    "name": None,
                    "reason": "without_project",
                    "is_service_case": False,
                    "takes_part": False,
                    "suggested_job_function": None,
                    "suggested_crew_line": None,
                    "crew_lines": [],
                    "job_functions": [
                        {"id": function.pk, "name": function.name}
                        for function in services.job_functions_for(person, None, every=every)
                    ],
                }
            ]
        )


REPORT_PARAMETERS = [
    OpenApiParameter("person", int),
    OpenApiParameter("project", str, description="ID of the project, or ``none`` for entries without project"),
    OpenApiParameter("job_function", int),
    OpenApiParameter("from", str, description="First day, YYYY-MM-DD. Without from and to: all entries."),
    OpenApiParameter("to", str, description="Last day, YYYY-MM-DD"),
    OpenApiParameter("status", str, enum=TimeEntryStatus.values),
    OpenApiParameter("group_by", str, enum=list(services.GROUPINGS)),
]


class HoursReportView(ModuleAPIView):
    """``GET /reports/hours`` – hours by person, project, job function and period (ZEI-015, ZEI-016).

    Everybody gets a report of their own times (ZEI-016); others' times need
    the right to approve. Amounts are part of the answer where the caller
    may see the rates (AUT-019, PER-010). Rejected entries are left out
    unless asked for with ``status=rejected``.

    The same selection as a file: ``/reports/hours/csv`` and
    ``/reports/hours/pdf`` (ZEI-017).
    """

    module = Module.TIME_TRACKING

    def build_report(self, request: Request) -> tuple[services.HoursReport, str]:
        """Return the report the query asks for and a text that names its period."""
        params = request.query_params
        entries = filter_by_ids(services.visible_entries(self.rights, request.user), params)
        if params.get("status") in TimeEntryStatus.values:
            entries = entries.filter(status=params["status"])
        else:
            entries = entries.exclude(status=TimeEntryStatus.REJECTED)
        since, until = parse_date(params.get("from", "") or ""), parse_date(params.get("to", "") or "")
        if since:
            entries = entries.filter(start__gte=start_of_day(since))
        if until:
            entries = entries.filter(start__lt=end_of_day(until))
        report = services.hours_report(
            entries, group_by=params.get("group_by", "person"), rights=self.rights, user=request.user
        )
        period = " – ".join(day.strftime(local_pattern("%d.%m.%Y")) for day in (since, until) if day)
        return report, period

    @extend_schema(
        parameters=REPORT_PARAMETERS,
        responses={200: inline_serializer("HoursReport", {"total_hours": serializers.DecimalField(10, 2)})},
    )
    def get(self, request: Request) -> Response:
        """Return the sums and the entries behind them."""
        report, _period = self.build_report(request)
        hints = hints_for(report.entries)  # ZEI-018
        attach_pay_kinds(report.entries)  # API-016
        return Response(
            {
                "group_by": report.group_by,
                "total_hours": report.total_hours,
                "total_amount": report.total_amount,
                "rows": [
                    {"label": row.label, "hours": row.hours, "amount": row.amount, "entries": len(row.entries)}
                    for row in report.rows
                ],
                "entries": [
                    entry_document(
                        entry,
                        with_rate=services.may_see_rate_of(self.rights, request.user, entry.person),
                        hints=hints.get(entry.pk),
                    )
                    for entry in report.entries
                ],
            }
        )


class HoursReportCsvView(HoursReportView):
    """``GET /reports/hours/csv`` – the entries of the report as a file for a spreadsheet (ZEI-017)."""

    @extend_schema(parameters=REPORT_PARAMETERS, responses={(200, "text/csv"): str})
    def get(self, request: Request) -> HttpResponse:  # type: ignore[override]
        """Return one row per entry, with semicolons and decimal commas."""
        report, _period = self.build_report(request)
        response = HttpResponse(report_csv(report, self.rights, request.user), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{file_name("hours", extension="csv")}"'
        return response


class HoursReportPdfView(HoursReportView):
    """``GET /reports/hours/pdf`` – the report as a timesheet to print and sign (ZEI-017)."""

    @extend_schema(parameters=REPORT_PARAMETERS, responses={(200, "application/pdf"): bytes, 400: None})
    def get(self, request: Request) -> HttpResponse:  # type: ignore[override]
        """Return the timesheet as a PDF file; 400 if it would hold too many entries (see ``pdf``)."""
        report, period = self.build_report(request)
        if timesheet_is_too_long(report):
            return Response({"detail": too_long_message(report)}, status=status.HTTP_400_BAD_REQUEST)
        response = HttpResponse(render_timesheet_pdf(report, period), content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{file_name("timesheet", extension="pdf")}"'
        return response
