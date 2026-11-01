# SPDX-License-Identifier: GPL-3.0-or-later
"""App configuration of the ``chat`` module."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ChatConfig(AppConfig):
    """The chat of a project, for everybody who can open the project (UIX-010)."""

    name = "rentalars.chat"
    label = "chat"
    verbose_name = _("Chat")

    def ready(self) -> None:
        """Make the conversion of videos known; files of deleted attachments go (UIX-049)."""
        from django.db.models.signals import post_delete

        from rentalars.chat import media
        from rentalars.chat.models import ChatAttachment
        from rentalars.core.jobs import register

        # NFA-076: one conversion at a time on a server – the others wait in line.
        register("chat_video", "rentalars.chat.media:run_job", gate="rentalars.chat.media:conversion_slot")
        post_delete.connect(media.files_deleted, sender=ChatAttachment, dispatch_uid="chat.media.files_deleted")
