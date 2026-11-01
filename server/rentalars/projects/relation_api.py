# SPDX-License-Identifier: GPL-3.0-or-later
"""API of related projects and service cases (PRJ-119; API-002).

``GET /projects/{id}/relations``
    The projects and cases related to this one – a project or a service
    case –, as the box "Verwandt" lists them: ``id`` (of the relation),
    ``number``, and for one the caller may open ``project`` (its ID),
    ``name``, ``kind``, ``status``, ``status_label`` and the ``note``; for one
    the caller may not open ``accessible: false`` and the number only, the
    rest ``null`` or empty (AUT-016). Needs read access to the project.

``POST /projects/{id}/relations``
    Relates another one: ``project`` (its ID) or ``number``, and an optional
    ``note`` (200 characters). Needs edit access to this one and read access
    to the other one; whole projects and service cases only. 201 with the
    relation as ``GET`` lists it; 400 if the other one is the same, a
    subproject, related already, or not found among those the caller may read.

``DELETE /projects/{id}/relations/{relation}``
    Ends the relation – with edit access to this one and read access to the
    other one, as linking. Both histories note it.

The companion app reads the same list in the detail of a project or case
(``related`` in ``GET /projects/{id}`` and ``GET /service-cases/{id}``).
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Level, Module, request_rights
from rentalars.api.views import ModuleAPIView, body_of
from rentalars.projects import relations
from rentalars.projects.access import ProjectAccess, access_level, project_for
from rentalars.projects.models import Project, ProjectRelation

_RELATION = inline_serializer(
    "ProjectRelation",
    {
        "id": serializers.IntegerField(),
        "project": serializers.IntegerField(allow_null=True),
        "number": serializers.CharField(),
        "name": serializers.CharField(allow_null=True),
        "kind": serializers.CharField(allow_null=True),
        "status": serializers.CharField(allow_null=True),
        "status_label": serializers.CharField(allow_null=True),
        "accessible": serializers.BooleanField(),
        "note": serializers.CharField(),
        "created_at": serializers.DateTimeField(),
    },
)


class RelationRequestSerializer(serializers.Serializer):
    """What ``POST /projects/{id}/relations`` takes."""

    project = serializers.IntegerField(required=False, allow_null=True, help_text="The ID of the other one.")
    number = serializers.CharField(
        required=False, allow_blank=True, help_text="Or its number (a former number works as well)."
    )
    note = serializers.CharField(required=False, allow_blank=True, max_length=relations.NOTE_LENGTH)


def related_document(project: Project, request: Request, rights: Any) -> list[dict[str, Any]]:
    """The related projects of ``project`` for the caller, as the API and the companion app deliver them."""
    return [relations.entry_document(entry) for entry in relations.related_entries(project, rights, request.user)]


def add_related(data: dict[str, Any], project: Project, context: dict[str, Any]) -> None:
    """Put ``related`` into the detail of a project or a service case – for the companion app.

    Only in the detail (``retrieve``), never in a list – it would cost queries per row (NFA-014) –, and only for a
    caller who reads the project or works on the case, as the box "Verwandt" (not with the deployment view only).
    ``project.access`` is the level the view noted on the project it loaded.
    """
    request = context.get("request")
    if request is None or getattr(context.get("view"), "action", None) != "retrieve" or project.parent_id:
        return
    if getattr(project, "access", ProjectAccess.NONE) < ProjectAccess.READ and not getattr(
        project, "works_on_case", False
    ):
        return
    data["related"] = related_document(project, request, request_rights(request))


def _linking_project(request: Request, project_pk: int) -> Project:
    """The project at hand for a change of its relations: edit access, a whole project or a case."""
    project = project_for(request, project_pk, ProjectAccess.EDIT, queryset=Project.objects.select_related("parent"))
    if not relations.may_link_from(project):
        raise PermissionDenied(_("A subproject is related through its whole project."))
    return project


class ProjectRelationsView(ModuleAPIView):
    """``/projects/{id}/relations`` – list and link related projects and service cases (PRJ-119)."""

    module = Module.PROJECTS

    @extend_schema(responses={200: _RELATION})
    def get(self, request: Request, project_pk: int) -> Response:
        """The related projects and cases; one the caller may not open with its number only (AUT-016)."""
        project = project_for(request, project_pk, ProjectAccess.READ)
        return Response(related_document(project, request, self.rights))

    @extend_schema(request=RelationRequestSerializer, responses={201: _RELATION})
    def post(self, request: Request, project_pk: int) -> Response:
        """Relate another project or service case – one the caller may read."""
        project = _linking_project(request, project_pk)
        serializer = RelationRequestSerializer(data=body_of(request))
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        other = None
        if values.get("project"):
            other = Project.objects.filter(pk=values["project"]).first()
            if other is not None and access_level(self.rights, request.user, other) < ProjectAccess.READ:
                other = None
        elif values.get("number", "").strip():
            other = relations.other_for(self.rights, request.user, values["number"])
        else:
            raise serializers.ValidationError({"project": _("Name the project or service case: its ID or number.")})
        if other is None:
            raise serializers.ValidationError(
                {"project": _("There is no project or service case with this number that you may see.")}
            )
        relation = relations.link(project, other, note=values.get("note", ""), user=request.user)
        entry = next(
            entry
            for entry in relations.related_entries(project, self.rights, request.user)
            if entry.relation.pk == relation.pk
        )
        return Response(relations.entry_document(entry), status=status.HTTP_201_CREATED)


class ProjectRelationView(ModuleAPIView):
    """``/projects/{id}/relations/{relation}`` – end a relation (PRJ-119)."""

    module = Module.PROJECTS
    #: Unlinking changes the project, it deletes nothing of it: "write" is enough, as for linking.
    action_levels: ClassVar[dict[Any, int]] = {None: Level.WRITE}

    @extend_schema(responses={204: None})
    def delete(self, request: Request, project_pk: int, pk: int) -> Response:
        """End the relation; needs read access to the other one, as linking does – also from a subproject."""
        project = project_for(request, project_pk, ProjectAccess.EDIT)
        relation = get_object_or_404(
            ProjectRelation.objects.filter(Q(first=project) | Q(second=project)).select_related("first", "second"),
            pk=pk,
        )
        if access_level(self.rights, request.user, relation.other_than(project)) < ProjectAccess.READ:
            raise PermissionDenied(_("You may not read the related project."))
        relations.unlink(relation, seen_from=project)
        return Response(status=status.HTTP_204_NO_CONTENT)
