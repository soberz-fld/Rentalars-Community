# SPDX-License-Identifier: GPL-3.0-or-later
"""API for the course of a project: phases, open items, files (stage 4).

* ``/projects/{id}/phases`` – setup, event, teardown … with time and place (PRJ-006), and their crew (PRJ-080)
* ``/projects/{id}/open-items`` – what is still open after "Confirmed – details open" (PRJ-059)
* ``/open-items`` – all projects with open items (PRJ-059, scenario 20)
* ``/projects/{id}/files`` – stage plans, riders, contracts (PRJ-007); ``…/content`` hands one out

Duplicating a project (PRJ-029) is ``POST /projects/{id}/duplicate`` in ``projects.api``.

The browser pages (``projects.course_views``) and these views call the same
functions in ``projects.course`` and ``projects.files`` (API-002).
"""

from __future__ import annotations

from typing import Any

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_field, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Level, Module, request_rights
from rentalars.api.views import ModuleAPIView, body_of
from rentalars.core.uploads import document_response
from rentalars.customers.models import Venue
from rentalars.masterdata.models import DocumentType, Supplier
from rentalars.personnel.models import JobFunction
from rentalars.projects import course, files, staffing
from rentalars.projects.access import ProjectAccess, readable_projects
from rentalars.projects.api import ProjectChildViewSet
from rentalars.projects.models import OpenItem, ProjectFile, ProjectPhase, ProjectStatus, SupplierDocumentKind

# --- Phases (PRJ-006) --------------------------------------------------------------------------


class RentalPeriodSuggestionSerializer(serializers.Serializer):
    """PRJ-100: the rental period that would cover the phase."""

    start = serializers.DateTimeField()
    end = serializers.DateTimeField()


class PhaseSerializer(serializers.ModelSerializer):
    """One phase of a project: kind, time, and where – a venue or a free place.

    PRJ-080: ``crew_lines`` names the crew lines of the phase. ``move_crew``
    (only when changing; default true) moves them along with a new period,
    see ``crew.move_with_phase``; the answer then names the lines that moved
    in ``moved_crew_lines``.

    PRJ-100: ``outside_rental_period`` says whether the phase begins before or
    ends after the rental period of the project. ``rental_period_suggestion``
    is the rental period that would cover it – what the pages offer to extend
    to – or ``null``: within the period, or a phase of the kind ``planning``,
    which never asks. The API never extends the rental period by itself; a
    client that wants to does so with ``PATCH /projects/{id}`` (``start``,
    ``end``), with the checks of any change of the period.
    """

    venue_site = serializers.PrimaryKeyRelatedField(queryset=Venue.objects.all(), required=False, allow_null=True)
    label = serializers.CharField(read_only=True)
    crew_lines = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    move_crew = serializers.BooleanField(
        write_only=True,
        required=False,
        default=True,
        help_text="When the period changes: move the crew lines of the phase along (PRJ-080).",
    )
    #: PRJ-120: job functions with places – creating the phase plans that many open places in it.
    places = serializers.ListField(
        child=inline_serializer(
            "PhasePlaces",
            {
                "job_function": serializers.PrimaryKeyRelatedField(queryset=JobFunction.objects.filter(is_active=True)),
                "places": serializers.IntegerField(min_value=1, max_value=staffing.MAX_PLACES),
            },
        ),
        write_only=True,
        required=False,
        max_length=staffing.MAX_ROWS,
        help_text="Only when creating: job functions with their places; the phase gets that many open places.",
    )
    outside_rental_period = serializers.SerializerMethodField(
        help_text="The phase begins before or ends after the rental period of the project (PRJ-100)."
    )
    rental_period_suggestion = serializers.SerializerMethodField(
        help_text="The rental period that would cover the phase; null within it or for the kind `planning` (PRJ-100)."
    )

    class Meta:
        model = ProjectPhase
        fields = [
            "id",
            "kind",
            "title",
            "label",
            "start",
            "end",
            "venue_site",
            "location",
            "notes",
            "crew_lines",
            "move_crew",
            "places",
            "outside_rental_period",
            "rental_period_suggestion",
        ]

    def _project(self, phase: ProjectPhase) -> Any:
        """The project of the phase – the one of the address, loaded once for all phases of the answer."""
        project = self.context.get("project")
        return project if project is not None and project.pk == phase.project_id else phase.project

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_outside_rental_period(self, phase: ProjectPhase) -> bool:
        """PRJ-100: whether the phase lies partly outside the rental period."""
        return course.lies_outside_rental_period(phase, self._project(phase))

    @extend_schema_field(RentalPeriodSuggestionSerializer(allow_null=True))
    def get_rental_period_suggestion(self, phase: ProjectPhase) -> dict[str, Any] | None:
        """PRJ-100: the rental period the pages would suggest, or ``None``."""
        suggestion = course.rental_period_suggestion(phase, self._project(phase))
        if suggestion is None:
            return None
        return RentalPeriodSuggestionSerializer({"start": suggestion.start, "end": suggestion.end}).data


class PhaseViewSet(ProjectChildViewSet):
    """``/projects/{id}/phases`` (PRJ-006). Reading needs read access, changing edit access."""

    queryset = ProjectPhase.objects.none()
    serializer_class = PhaseSerializer

    def get_queryset(self) -> Any:
        """The phases of the project in their order of time, with their crew lines (PRJ-080)."""
        return (
            ProjectPhase.objects.filter(project_id=self.kwargs.get("project_pk"))
            .select_related("venue_site")
            .prefetch_related("crew_lines")
        )

    def perform_create(self, serializer: Any) -> None:
        """Add the phase – with ``places``, and that many open places in it (PRJ-120)."""
        values = dict(serializer.validated_data)
        values.pop("move_crew", None)
        rows = [staffing.FunctionPlaces(row["job_function"], row["places"]) for row in values.pop("places", None) or []]
        serializer.instance, _lines = staffing.add_phase_with_places(
            self.get_project(), rows, rights=request_rights(self.request), **values
        )

    @extend_schema(
        responses={
            200: inline_serializer(
                "PhaseChanged",
                {
                    "id": serializers.IntegerField(),
                    "moved_crew_lines": serializers.ListField(child=serializers.IntegerField()),
                },
            )
        }
    )
    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Change the phase; with ``move_crew`` (default) its crew lines follow a new period (PRJ-080)."""
        phase = self.get_object()
        serializer = self.get_serializer(phase, data=request.data, partial=kwargs.pop("partial", False))
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        move_crew = values.pop("move_crew", True)
        change = course.update_phase(phase, move_crew=move_crew, **values)
        data = dict(self.get_serializer(self.get_queryset().get(pk=change.phase.pk)).data)
        data["moved_crew_lines"] = [line.pk for line in change.moved_crew_lines]
        return Response(data)

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Change single fields of the phase."""
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def perform_destroy(self, instance: ProjectPhase) -> None:
        """Remove the phase; its crew lines stay, without phase (PRJ-080)."""
        course.delete_phase(instance)


# --- Open items (PRJ-059) ----------------------------------------------------------------------


class OpenItemSerializer(serializers.ModelSerializer):
    """An open item. ``is_done`` ticks it off; who did it and when is noted."""

    done_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = OpenItem
        fields = ["id", "text", "is_done", "done_at", "done_by", "created_at"]
        read_only_fields = ["done_at", "created_at"]


class OpenItemViewSet(ProjectChildViewSet):
    """``/projects/{id}/open-items`` (PRJ-059).

    ``POST`` takes ``text`` for one item or ``texts`` for several. When the
    last item of a project in "Confirmed – details open" is ticked off, the
    answer says ``suggest_confirmation: true`` (acceptance scenario 20).
    """

    queryset = OpenItem.objects.none()
    serializer_class = OpenItemSerializer
    #: AUT-033 (PRJ-108): the open items of a service case are part of working on it.
    case_work_actions = ("list", "retrieve", "create", "update", "partial_update", "destroy")

    def get_queryset(self) -> Any:
        """The open items of the project, open ones first."""
        return OpenItem.objects.filter(project_id=self.kwargs.get("project_pk")).select_related("done_by")

    @extend_schema(
        request=inline_serializer(
            "OpenItemsNew",
            {
                "text": serializers.CharField(required=False),
                "texts": serializers.ListField(child=serializers.CharField(), required=False),
            },
        ),
        responses={201: OpenItemSerializer(many=True)},
    )
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Note one or more open items."""
        body = body_of(request)
        texts = body.get("texts")
        if not isinstance(texts, list):
            texts = [str(body.get("text", ""))]
        items = course.add_open_items(self.get_project(), [str(text) for text in texts])
        return Response(self.get_serializer(items, many=True).data, status=status.HTTP_201_CREATED)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Change the text, or tick the item off (``is_done``)."""
        item = self.get_object()
        serializer = self.get_serializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        if "text" in values:
            course.update_open_item(item, values["text"])
        if "is_done" in values and values["is_done"] != item.is_done:
            course.set_open_item_done(item, done=values["is_done"], user=request.user)
        data = dict(self.get_serializer(item).data)
        data["suggest_confirmation"] = course.suggests_confirmation(self.get_project())
        return Response(data)

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Change single fields."""
        return self.update(request, *args, **kwargs)

    def perform_destroy(self, instance: OpenItem) -> None:
        """Remove an item noted by mistake."""
        course.delete_open_item(instance)


class OpenItemOverviewView(ModuleAPIView):
    """``GET /open-items`` – the projects with open items, with the items (PRJ-059, scenario 20)."""

    module = Module.PROJECTS

    @extend_schema(
        responses={200: inline_serializer("OpenItemOverview", {"project": serializers.IntegerField()}, many=True)}
    )
    def get(self, request: Request) -> Response:
        """Projects that still have something open, sorted by start.

        AUT-031 (Crew): refused (403) to a role with the overview only, as the page "Offene Punkte".
        """
        from rentalars.accounts.rights import require

        rights = request_rights(request)
        require(rights.reads_planning)
        projects = course.projects_with_open_items(readable_projects(rights, request.user))
        rows = []
        for project in projects:
            rows.append(
                {
                    "project": project.pk,
                    "number": project.number,
                    "name": project.name,
                    "status": project.status,
                    "start": project.start,
                    "end": project.end,
                    "open_count": project.open_count,
                    "done_count": project.done_count,
                    "items": [
                        {"id": item.pk, "text": item.text} for item in project.open_items.all() if not item.is_done
                    ],
                    "suggest_confirmation": project.status == ProjectStatus.CONFIRMED_OPEN
                    and project.open_count == 0
                    and project.done_count > 0,
                }
            )
        return Response(rows)


# --- Files (PRJ-007) ---------------------------------------------------------------------------


class ProjectFileSerializer(serializers.ModelSerializer):
    """A file of a project. Upload it as ``file`` in a multipart request."""

    file = serializers.FileField(write_only=True, required=True)
    document_type = serializers.PrimaryKeyRelatedField(
        queryset=DocumentType.objects.all(), required=False, allow_null=True
    )
    visible_to_crew = serializers.BooleanField(required=False, allow_null=True, default=None)
    # PRJ-089: a new show file is the current one of its console unless ``false`` is sent.
    is_current_show = serializers.BooleanField(required=False, allow_null=True, default=None)
    uploaded_by = serializers.StringRelatedField(read_only=True)
    from_mail = serializers.SerializerMethodField()
    # PRJ-106: a document of a supplier of subrentals – offer, order confirmation, delivery note, invoice, other.
    supplier = serializers.PrimaryKeyRelatedField(queryset=Supplier.objects.all(), required=False, allow_null=True)
    supplier_document_kind = serializers.ChoiceField(
        choices=SupplierDocumentKind.choices, required=False, allow_blank=True
    )

    class Meta:
        model = ProjectFile
        fields = [
            "id",
            "title",
            "file",
            "original_name",
            "size",
            "document_type",
            "visible_to_crew",
            "uploaded_by",
            "uploaded_at",
            "from_mail",
            "supplier",
            "supplier_document_kind",
            # PRJ-089: a show file notes console or software, version and whether it is the current show.
            "show_system",
            "show_version",
            "is_current_show",
        ]
        read_only_fields = ["original_name", "size", "uploaded_at"]

    def get_from_mail(self, project_file: ProjectFile) -> int | None:
        """The mail the file was taken from (EML-021), if any."""
        attachment = project_file.source_attachment
        return attachment.mail_id if attachment is not None else None


class ProjectFileChangeSerializer(serializers.ModelSerializer):
    """What can be changed of a stored file."""

    document_type = serializers.PrimaryKeyRelatedField(
        queryset=DocumentType.objects.all(), required=False, allow_null=True
    )
    supplier = serializers.PrimaryKeyRelatedField(queryset=Supplier.objects.all(), required=False, allow_null=True)

    class Meta:
        model = ProjectFile
        fields = [
            "title",
            "document_type",
            "visible_to_crew",
            "supplier",
            "supplier_document_kind",
            "show_system",
            "show_version",
            "is_current_show",
        ]


class ProjectFileViewSet(ProjectChildViewSet):
    """``/projects/{id}/files`` (PRJ-007).

    Whoever may read the project sees all its files; crew with the
    deployment view only those marked ``visible_to_crew`` (AUT-023).
    PRJ-106: a document of a supplier of subrentals names ``supplier`` and
    ``supplier_document_kind``; ``?supplier=`` lists the documents of one.
    """

    queryset = ProjectFile.objects.none()
    serializer_class = ProjectFileSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    action_levels = {"content": Level.READ}

    def access_needed(self, usual: ProjectAccess) -> ProjectAccess:
        """Reading works with the deployment view; the list is then limited."""
        return ProjectAccess.DEPLOYMENT if usual == ProjectAccess.READ else usual

    def get_serializer_class(self) -> Any:
        """Changing uses the smaller serializer: the content of a file is not replaced."""
        if self.action in {"update", "partial_update"}:
            return ProjectFileChangeSerializer
        return ProjectFileSerializer

    def get_queryset(self) -> Any:
        """All files – or, with the deployment view only, those for the crew."""
        project = self.get_project()
        queryset = ProjectFile.objects.filter(project=project).select_related(
            "document_type", "uploaded_by", "source_attachment"
        )
        if project.access < ProjectAccess.READ:
            queryset = queryset.filter(visible_to_crew=True)
        supplier = str(self.request.query_params.get("supplier", ""))
        if supplier.isdigit():
            queryset = queryset.filter(supplier_id=int(supplier))  # PRJ-106: the documents of one supplier
        return queryset

    def perform_create(self, serializer: Any) -> None:
        """Store the uploaded file (NFA-007 rules for type and size)."""
        values = serializer.validated_data
        serializer.instance = files.add_file(
            self.get_project(),
            values["file"],
            user=self.request.user,
            title=values.get("title", ""),
            document_type=values.get("document_type"),
            visible_to_crew=values.get("visible_to_crew"),
            supplier=values.get("supplier"),
            supplier_document_kind=values.get("supplier_document_kind", "") if values.get("supplier") else "",
            # PRJ-089: a show file; console guessed from the ending, current unless said otherwise.
            show_system=values.get("show_system", ""),
            show_version=values.get("show_version", ""),
            is_current_show=values.get("is_current_show"),
        )

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Change title, document type or visibility."""
        project_file = self.get_object()
        serializer = ProjectFileChangeSerializer(project_file, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        files.update_file(project_file, **serializer.validated_data)
        return Response(ProjectFileSerializer(project_file, context=self.get_serializer_context()).data)

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Change single fields."""
        return self.update(request, *args, **kwargs)

    def perform_destroy(self, instance: ProjectFile) -> None:
        """Remove the file from the project and from the disk."""
        files.delete_file(instance)

    @extend_schema(responses={(200, "application/octet-stream"): bytes})
    @action(detail=True)
    def content(self, request: Request, project_pk: str | None = None, pk: str | None = None) -> Any:
        """The file itself."""
        project_file = self.get_object()
        return document_response(project_file.file.name, project_file.original_name)
