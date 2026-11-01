# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views of the chat of a project (UIX-010).

The tab "Chat" of a project, for everybody who can open the project – crew
with the deployment view included (AUT-025). Writing works without
JavaScript (a form that reloads the page); with it, htmx exchanges only the
messages, and the change polling (UIX-020) fetches new messages of others
in place (``app.js``, block "Chat in the project").

UIX-049: the form takes photos and videos as well; the chat shows
them inline, delivered by :func:`media_file` to whoever may read the chat.
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext_lazy
from django.views.decorators.http import require_POST

from rentalars.chat import media, services
from rentalars.chat.models import EDIT_MINUTES, MAX_LENGTH, ChatAttachment, ChatMessage
from rentalars.projects.access import ProjectAccess, project_for
from rentalars.projects.case_work import case_work_required
from rentalars.projects.models import Project


class MessageForm(forms.Form):
    """One message."""

    text = forms.CharField(
        label=pgettext_lazy("chat", "Message"),
        max_length=MAX_LENGTH,
        # UIX-049: a message with photos or videos needs no text; chat.services says when one is missing.
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "maxlength": MAX_LENGTH, "autocomplete": "off"}),
    )


def _project(request: HttpRequest, pk: int) -> Project:
    """The project for the chat: whoever can open it at all (AUT-025)."""
    return project_for(
        request,
        pk,
        ProjectAccess.DEPLOYMENT,
        queryset=Project.objects.select_related("customer", "manager", "parent", "venue_site"),
    )


def _before(request: HttpRequest) -> int | None:
    value = request.GET.get("before", "")
    return int(value) if value.isdigit() else None


def _media_limits() -> dict[str, int]:
    """The limits of uploads, for the form and its script (UIX-049)."""
    return {
        "max_files": media.MAX_FILES,
        "max_photo_mb": media.MAX_PHOTO_BYTES // 1048576,
        "max_video_mb": media.MAX_VIDEO_BYTES // 1048576,
        "max_message_mb": media.MAX_MESSAGE_BYTES // 1048576,
        "photo_side": media.PHOTO_LONGEST_SIDE,
    }


def _messages_context(request: HttpRequest, project: Project, *, error: str = "") -> dict[str, Any]:
    """What the list of messages needs; marks the chat as read for the user."""
    page = services.messages_of(project, before=_before(request))
    now = timezone.now()
    for message in page.messages:
        message.changeable = services.can_change(message, request.user, now)
        message.is_own = message.author_id == request.user.pk
    if not _before(request):
        services.mark_read(project, request.user, up_to=page.messages[-1].pk if page.messages else 0)
    return {
        "project": project,
        "page": page,
        "stamp": services.stamp(project.pk, request.user).split("~", 1)[0],
        "edit_minutes": EDIT_MINUTES,
        "chat_error": error,
    }


def _fragment(request: HttpRequest, project: Project, *, error: str = "", sent: bool = False) -> HttpResponse:
    response = render(request, "chat/_messages.html", _messages_context(request, project, error=error))
    if sent:
        # app.js empties the field once the message is in.
        response["HX-Trigger"] = "chatSent"
    return response


@case_work_required()  # AUT-033: also whoever works on the service case (PRJ-108)
def chat_page(request: HttpRequest, pk: int) -> HttpResponse:
    """The chat of a project; ``POST`` writes a message (UIX-010)."""
    project = _project(request, pk)
    form = MessageForm(request.POST or None)
    error = file_error = ""
    if request.method == "POST":
        if form.is_valid():
            try:
                message = services.post_message(
                    project,
                    user=request.user,
                    text=form.cleaned_data["text"],
                    files=request.FILES.getlist("files"),  # UIX-049: photos and videos
                )
            except ValidationError as problem:
                error = " ".join(problem.messages)
                found = problem.message_dict if hasattr(problem, "error_dict") else {}
                if "files" in found:
                    file_error = " ".join(found["files"])
                else:
                    form.add_error("text", problem.messages[0] if problem.messages else error)
            else:
                if request.headers.get("HX-Request"):
                    return _fragment(request, project, sent=True)
                return redirect(reverse("chat:project", args=[project]) + f"#m{message.pk}")
        else:
            error = " ".join(" ".join(errors) for errors in form.errors.values())
        if request.headers.get("HX-Request"):
            return _fragment(request, project, error=error)
    readers = services.readers_of(project)
    context = _messages_context(request, project)
    context.update(
        tab="chat",
        form=form,
        readers=[
            {
                "name": services.display_name(reader),
                # Reads along through the deployment view only: the crew (AUT-025).
                "is_crew": reader.chat_access == ProjectAccess.DEPLOYMENT,
                "is_me": reader.pk == request.user.pk,
            }
            for reader in readers
        ],
        max_length=MAX_LENGTH,
        file_error=file_error,
        videos_possible=media.videos_possible(),
        **_media_limits(),
    )
    return render(request, "chat/chat.html", context)


@case_work_required()  # AUT-033: also whoever works on the service case (PRJ-108)
def chat_messages(request: HttpRequest, pk: int) -> HttpResponse:
    """Only the messages – fetched by the page when the change polling reports new ones (UIX-020)."""
    project = _project(request, pk)
    return _fragment(request, project)


def _own_message(request: HttpRequest, pk: int, message_pk: int) -> tuple[Project, ChatMessage]:
    project = _project(request, pk)
    message = get_object_or_404(ChatMessage, pk=message_pk, project=project)
    return project, message


def _after_change(request: HttpRequest, project: Project, error: str = "") -> HttpResponse:
    if request.headers.get("HX-Request"):
        return _fragment(request, project, error=error)
    if error:
        from django.contrib import messages

        messages.error(request, error)
    return redirect("chat:project", pk=project.pk)


@require_POST
@case_work_required()  # AUT-033: also whoever works on the service case (PRJ-108)
def message_edit(request: HttpRequest, pk: int, message_pk: int) -> HttpResponse:
    """Change one's own message within a few minutes (UIX-010)."""
    project, message = _own_message(request, pk, message_pk)
    try:
        services.edit_message(message, user=request.user, text=request.POST.get("text", ""))
    except ValidationError as problem:
        return _after_change(request, project, " ".join(problem.messages))
    return _after_change(request, project)


@require_POST
@case_work_required()  # AUT-033: also whoever works on the service case (PRJ-108)
def message_delete(request: HttpRequest, pk: int, message_pk: int) -> HttpResponse:
    """Delete one's own message within a few minutes (UIX-010)."""
    project, message = _own_message(request, pk, message_pk)
    try:
        services.delete_message(message, user=request.user)
    except ValidationError as problem:
        return _after_change(request, project, " ".join(problem.messages))
    return _after_change(request, project)


@case_work_required(kwarg="project_pk")  # AUT-033: also whoever works on the service case (PRJ-108)
def media_file(request: HttpRequest, project_pk: int, pk: int, small: bool = False) -> HttpResponse:
    """A photo or video of the chat – or its preview –, for whoever may read the chat (UIX-049).

    The same rule as the chat itself: whoever can open the project, the crew
    with the deployment view included (AUT-025), and whoever works on the
    service case (AUT-033). Anybody else gets "not found".

    The address names the project by ``project_pk``, not ``pk``: the pictures
    belong to reading the chat, which the access log notes already as the
    project opened (AUT-028) – not once more for every preview.
    """
    project = _project(request, project_pk)
    attachment = get_object_or_404(ChatAttachment, pk=pk, message__project=project)
    return media.file_response(attachment, small=small)
