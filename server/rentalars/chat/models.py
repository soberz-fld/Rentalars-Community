# SPDX-License-Identifier: GPL-3.0-or-later
"""The chat of a project (UIX-010).

One chat per project – a subproject has its own. Everybody who can open the
project reads and writes it: the office with the planning, and the crew with
the deployment view (AUT-025). The page says so.

* :class:`ChatMessage` – one message with author and time. Its author may
  change or delete it for :data:`EDIT_MINUTES` minutes; a changed message
  says so. ``mentioned`` holds the users named with ``@`` – they were
  notified.
* :class:`ChatReadMark` – up to which message a user has read the chat of a
  project; everything newer by somebody else counts as unread. The mark is
  always a message of that chat, never beyond its newest.
*:class:`ChatAttachment` (UIX-049) – a photo or video of a
  message. The server keeps only a smaller version (``chat.media``): photos
  at most 2048 pixels on the long side without their metadata, videos at
  most 720p. A video is converted in the background; until then its state
  is "processing". A message may then have no text.

Messages are not business data of the project: they are not written to the
change log, and a new message does not make the other pages of the project
load again (UIX-020) – only the chat itself follows them, and the tab shows
the unread count.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

#: How long the author may change or delete a message.
EDIT_MINUTES = 15

#: The longest message.
MAX_LENGTH = 4000


class ChatMessage(models.Model):
    """A message in the chat of a project (UIX-010)."""

    project = models.ForeignKey(
        "projects.Project", verbose_name=_("project"), on_delete=models.CASCADE, related_name="chat_messages"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("author"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    #: The name as it was when the message was written; kept when the account goes.
    author_name = models.CharField(_("name of the author"), max_length=150, blank=True)
    #: UIX-049: empty when the message holds photos or videos only.
    text = models.TextField(_("message"), max_length=MAX_LENGTH, blank=True)
    created_at = models.DateTimeField(_("written"), default=timezone.now)
    edited_at = models.DateTimeField(_("changed"), null=True, blank=True)
    #: UIX-010: counts the changes of the message; the change stamp of the chat sums it up, so
    #: that every change is seen – also two within one second, and the change of an older message.
    revision = models.PositiveIntegerField(default=0, editable=False)
    mentioned = models.ManyToManyField(
        settings.AUTH_USER_MODEL, verbose_name=_("mentioned"), blank=True, related_name="+"
    )

    class Meta:
        verbose_name = _("chat message")
        verbose_name_plural = _("chat messages")
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["project", "id"], name="chat_project_idx")]

    def __str__(self) -> str:
        return f"{self.author_name}: {self.text[:60]}"


class ChatReadMark(models.Model):
    """Up to which message a user has read the chat of a project (UIX-010)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="+")
    last_read_id = models.BigIntegerField(default=0)
    read_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = _("read chat")
        verbose_name_plural = _("read chats")
        constraints = [models.UniqueConstraint(fields=["user", "project"], name="chat_read_once")]

    def __str__(self) -> str:
        return f"{self.user_id}/{self.project_id}: {self.last_read_id}"


class AttachmentKind(models.TextChoices):
    """What a chat attachment is (UIX-049)."""

    PHOTO = "photo", _("photo")
    VIDEO = "video", _("video")


class AttachmentState(models.TextChoices):
    """Where a chat attachment stands: a video is made smaller in the background (UIX-049)."""

    PROCESSING = "processing", _("being made smaller")
    READY = "ready", _("ready")
    FAILED = "failed", _("failed")


def attachment_path(instance: ChatAttachment, filename: str) -> str:
    """Store chat media in a folder per project below ``media/chat``, under a random name (NFA-007).

    The folder lies in the media folder, so the backup holds the files like
    every other stored file.
    """
    import secrets
    from pathlib import Path

    extension = Path(filename).suffix.lower()[:10]
    return f"chat/{instance.message.project_id}/{secrets.token_hex(12)}{extension}"


class ChatAttachment(models.Model):
    """A photo or a video of a chat message, in its smaller version (UIX-049; UIX-010).

    ``file`` is the photo (JPEG, at most 2048 pixels on the long side) or the
    video (H.264/AAC in MP4, at most 720p); ``thumbnail`` a small JPEG – the
    preview of a photo, the poster frame of a video. Both are delivered only
    to whoever may read the chat (``chat.views.media_file``). Until a video is
    converted, ``source`` names the uploaded original in ``DATA_DIR/chat-videos``.
    """

    message = models.ForeignKey(
        ChatMessage, verbose_name=_("chat message"), on_delete=models.CASCADE, related_name="attachments"
    )
    kind = models.CharField(_("kind"), max_length=8, choices=AttachmentKind.choices)
    state = models.CharField(_("state"), max_length=12, choices=AttachmentState.choices, default=AttachmentState.READY)
    file = models.FileField(_("file"), upload_to=attachment_path, blank=True, max_length=200)
    thumbnail = models.FileField(_("preview"), upload_to=attachment_path, blank=True, max_length=200)
    #: The name the file had on the device of the sender.
    original_name = models.CharField(_("file name"), max_length=255, blank=True)
    size = models.PositiveBigIntegerField(_("size"), default=0)
    width = models.PositiveIntegerField(_("width"), null=True, blank=True)
    height = models.PositiveIntegerField(_("height"), null=True, blank=True)
    #: Seconds, for videos.
    duration = models.FloatField(_("duration"), null=True, blank=True)
    #: The uploaded original of a video still to be converted, a file name in ``DATA_DIR/chat-videos``.
    source = models.CharField(max_length=80, blank=True, editable=False)
    #: Why a video could not be converted – a key of ``chat.media.FAILURES``, shown in the reader's language.
    failure = models.CharField(max_length=20, blank=True, editable=False)
    position = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(_("uploaded"), default=timezone.now)

    class Meta:
        verbose_name = _("chat attachment")
        verbose_name_plural = _("chat attachments")
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return f"{self.message_id}/{self.kind}: {self.original_name}"

    @property
    def is_ready(self) -> bool:
        """Whether the file can be shown."""
        return self.state == AttachmentState.READY and bool(self.file)

    @property
    def failure_text(self) -> str:
        """Why the video could not be converted, in the reader's language."""
        from rentalars.chat.media import FAILURES

        return str(FAILURES.get(self.failure) or FAILURES["convert"])
