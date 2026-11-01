# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the chat of a project (UIX-010).

* ``GET /projects/{id}/chat`` – the newest messages, oldest first; ``?before=<id>`` pages back,
  ``?limit=`` (at most 500, default 100)
* ``POST /projects/{id}/chat`` – write a message: ``{"text": "…"}``; ``@Name`` mentions and notifies
* ``GET``/``PATCH``/``PUT``/``DELETE /projects/{id}/chat/{message}`` – one message; the author changes
  or deletes it within 15 minutes
* ``GET /projects/{id}/chat/read`` – the caller's unread count; ``POST`` marks the chat read
  (``{"up_to": <id>}``, else up to the newest)
* ``GET /projects/{id}/chat/readers`` – who reads along: everybody who can open the project
* ``GET /projects/{id}/chat/media/{attachment}`` – a photo or video of the chat; ``…/thumbnail`` its
  preview (UIX-049)

UIX-049: every message names its ``attachments`` – ``[{id, kind: photo|video, state:
processing|ready|failed, url, thumbnail_url, width, height, duration, size, name, failure}]``; ``url``
and ``thumbnail_url`` are set once it is ready. ``POST /projects/{id}/chat`` as ``multipart/form-data``
takes the files in the field ``files`` (repeated) and ``text`` beside them, which may then be empty.
Photos up to 25 MB, videos up to 200 MB, at most 10 files and 500 MB in all; the server makes them
smaller (photos at once, videos in the background – ``state`` is ``processing`` until then).

Everybody who can open the project reads and writes its chat – the crew with
the deployment view as well (AUT-025); a read-only token only reads. The
browser pages call the same functions in ``chat.services`` (API-002).
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field, inline_serializer
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Level
from rentalars.api.views import body_of
from rentalars.chat import media, services
from rentalars.chat.models import ChatAttachment, ChatMessage
from rentalars.projects.access import ProjectAccess
from rentalars.projects.api import ProjectChildViewSet

#: The most messages one call returns.
MAX_LIMIT = 500


class ChatAttachmentSerializer(serializers.ModelSerializer):
    """A photo or video of a message (UIX-049).

    ``url`` and ``thumbnail_url`` (the preview of a photo, the poster frame
    of a video) are addresses of this API, set once ``state`` is ``ready``;
    ``failure`` says why a video could not be made smaller.
    """

    url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    name = serializers.CharField(source="original_name", read_only=True)
    failure = serializers.SerializerMethodField()

    class Meta:
        model = ChatAttachment
        fields = [
            "id",
            "kind",
            "state",
            "url",
            "thumbnail_url",
            "width",
            "height",
            "duration",
            "size",
            "name",
            "failure",
        ]
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.STR)
    def get_url(self, attachment: ChatAttachment) -> str | None:
        """The address of the photo or video, once it is ready."""
        if not attachment.is_ready:
            return None
        return reverse("api:chat-media", args=[attachment.message.project_id, attachment.pk])

    @extend_schema_field(OpenApiTypes.STR)
    def get_thumbnail_url(self, attachment: ChatAttachment) -> str | None:
        """The address of the preview, once it is ready."""
        if not attachment.is_ready or not attachment.thumbnail:
            return None
        return reverse("api:chat-media-thumbnail", args=[attachment.message.project_id, attachment.pk])

    def get_failure(self, attachment: ChatAttachment) -> str:
        """Why the video could not be made smaller, in the caller's language; empty otherwise."""
        return attachment.failure_text if attachment.state == "failed" else ""


class ChatMessageSerializer(serializers.ModelSerializer):
    """A message of the chat. ``can_change``: the caller may still change or delete it."""

    mentioned = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    can_change = serializers.SerializerMethodField()
    attachments = ChatAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = ChatMessage
        fields = [
            "id",
            "project",
            "author",
            "author_name",
            "text",
            "created_at",
            "edited_at",
            "mentioned",
            "can_change",
            "attachments",
        ]
        read_only_fields = ["project", "author", "author_name", "created_at", "edited_at"]

    def get_can_change(self, message: ChatMessage) -> bool:
        """Whether the caller wrote it and the few minutes for changes are not over."""
        return services.can_change(message, self.context["request"].user)


class ChatReadSerializer(serializers.Serializer):
    """``up_to``: read up to this message of the chat; without it, up to the newest (UIX-010)."""

    up_to = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=2**63 - 1)


class ChatViewSet(ProjectChildViewSet):
    """``/projects/{id}/chat`` (UIX-010)."""

    queryset = ChatMessage.objects.none()
    serializer_class = ChatMessageSerializer
    #: Writing in the chat needs no more than opening the project: the crew reads the project and writes here.
    action_levels: ClassVar[dict[str, int]] = {
        "create": Level.READ,
        "update": Level.READ,
        "partial_update": Level.READ,
        "destroy": Level.READ,
        "mark_read": Level.READ,
    }
    #: AUT-033 (PRJ-108): the chat of a service case is part of working on it – also without the module "projects".
    case_work_actions = (
        "list",
        "retrieve",
        "create",
        "update",
        "partial_update",
        "destroy",
        "mark_read",
        "readers",
        "media",
        "thumbnail",
    )

    def access_needed(self, usual: ProjectAccess) -> ProjectAccess:
        """Whoever can open the project – the deployment view is enough (AUT-025)."""
        return ProjectAccess.DEPLOYMENT

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        """A read-only token reads the chat, but does not write (AUT-021)."""
        super().initial(request, *args, **kwargs)
        if request.method not in SAFE_METHODS and getattr(getattr(request, "auth", None), "read_only", False):
            raise PermissionDenied

    def get_queryset(self) -> Any:
        """The messages of the project."""
        return ChatMessage.objects.filter(project_id=self.get_project().pk).prefetch_related("mentioned", "attachments")

    @extend_schema(
        parameters=[
            OpenApiParameter("before", int, description="Only messages older than this one."),
            OpenApiParameter("limit", int, description="How many; at most 500, default 100."),
        ]
    )
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """The newest messages, oldest first."""
        before = request.query_params.get("before", "")
        limit = request.query_params.get("limit", "")
        page = services.messages_of(
            self.get_project(),
            before=int(before) if before.isdigit() else None,
            limit=min(int(limit), MAX_LIMIT) if limit.isdigit() and int(limit) > 0 else services.PAGE_SIZE,
        )
        response = Response(self.get_serializer(page.messages, many=True).data)
        response["X-Has-Older"] = "true" if page.has_older else "false"
        return response

    @extend_schema(
        request={
            "application/json": inline_serializer("ChatMessageNew", {"text": serializers.CharField()}),
            "multipart/form-data": inline_serializer(
                "ChatMessageNewWithFiles",
                {
                    "text": serializers.CharField(required=False, allow_blank=True),
                    "files": serializers.ListField(child=serializers.FileField()),
                },
            ),
        },
        responses={201: ChatMessageSerializer},
    )
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Write a message; who is mentioned with ``@`` is notified. UIX-049: with photos and videos (``files``)."""
        message = services.post_message(
            self.get_project(),
            user=request.user,
            text=str(body_of(request).get("text", "")),
            files=request.FILES.getlist("files"),
        )
        message = self.get_queryset().get(pk=message.pk)
        return Response(self.get_serializer(message).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=inline_serializer("ChatMessageChange", {"text": serializers.CharField()}))
    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Change one's own message within 15 minutes."""
        message = services.edit_message(
            self.get_object(), user=request.user, text=str(body_of(request).get("text", ""))
        )
        return Response(self.get_serializer(message).data)

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Change one's own message within 15 minutes."""
        return self.update(request, *args, **kwargs)

    def perform_destroy(self, instance: ChatMessage) -> None:
        """Delete one's own message within 15 minutes."""
        services.delete_message(instance, user=self.request.user)

    @extend_schema(
        request=ChatReadSerializer,
        responses={200: inline_serializer("ChatReadState", {"unread": serializers.IntegerField()})},
    )
    def mark_read(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """``GET``: the caller's unread messages. ``POST``: read up to ``up_to``, else up to the newest.

        UIX-010: ``up_to`` counts up to the newest message of this
        chat that is not after it – never further; a value that is no number
        is refused (400) instead of marking everything as read.
        """
        project = self.get_project()
        if request.method == "POST":
            serializer = ChatReadSerializer(data=body_of(request))
            serializer.is_valid(raise_exception=True)
            services.mark_read(project, request.user, up_to=serializer.validated_data.get("up_to"))
        return Response({"unread": services.unread_count(project, request.user)})

    @extend_schema(
        responses={
            200: inline_serializer(
                "ChatReader",
                {
                    "id": serializers.IntegerField(),
                    "name": serializers.CharField(),
                    "username": serializers.CharField(),
                    "access": serializers.CharField(),
                },
                many=True,
            )
        }
    )
    def readers(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Who reads along – and can be mentioned: everybody who can open the project."""
        return Response(
            [
                {
                    "id": reader.pk,
                    "name": services.display_name(reader),
                    "username": reader.username,
                    "access": reader.chat_access.name.lower(),
                }
                for reader in services.readers_of(self.get_project())
            ]
        )

    def _attachment(self) -> ChatAttachment:
        """The photo or video of the address, of a message of this project's chat."""
        return get_object_or_404(
            ChatAttachment.objects.select_related("message"),
            pk=self.kwargs["pk"],
            message__project_id=self.get_project().pk,
        )

    @extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY, 404: None})
    def media(self, request: Request, *args: Any, **kwargs: Any) -> HttpResponse:
        """The photo (JPEG) or video (MP4) itself; 404 while a video is being made smaller (UIX-049)."""
        return media.file_response(self._attachment())

    @extend_schema(responses={(200, "image/jpeg"): OpenApiTypes.BINARY, 404: None})
    def thumbnail(self, request: Request, *args: Any, **kwargs: Any) -> HttpResponse:
        """The preview: a small photo, or the poster frame of a video (JPEG; UIX-049)."""
        return media.file_response(self._attachment(), small=True)


LIST = {"get": "list", "post": "create"}
DETAIL = {"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"}

#: Wired into ``api/urls.py``.
urlpatterns = [
    path("projects/<int:project_pk>/chat", ChatViewSet.as_view(LIST), name="chat-list"),
    path(
        "projects/<int:project_pk>/chat/read",
        ChatViewSet.as_view({"get": "mark_read", "post": "mark_read"}),
        name="chat-read",
    ),
    path("projects/<int:project_pk>/chat/readers", ChatViewSet.as_view({"get": "readers"}), name="chat-readers"),
    # UIX-049
    path("projects/<int:project_pk>/chat/media/<int:pk>", ChatViewSet.as_view({"get": "media"}), name="chat-media"),
    path(
        "projects/<int:project_pk>/chat/media/<int:pk>/thumbnail",
        ChatViewSet.as_view({"get": "thumbnail"}),
        name="chat-media-thumbnail",
    ),
    path("projects/<int:project_pk>/chat/<int:pk>", ChatViewSet.as_view(DETAIL), name="chat-detail"),
]
