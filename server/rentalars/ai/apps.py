# SPDX-License-Identifier: GPL-3.0-or-later
"""App configuration of the ``ai`` module (EML-040, EML-044, ADM-017)."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AiConfig(AppConfig):
    """Summaries of the correspondence and the interface to language models."""

    name = "rentalars.ai"
    label = "ai"
    verbose_name = _("AI")

    def ready(self) -> None:
        """Make the background tasks known and forget summaries of deleted mails (NFA-041, EML-040)."""
        from django.db.models.signals import post_delete

        from rentalars.ai import signals
        from rentalars.chat.models import ChatMessage
        from rentalars.core.jobs import register
        from rentalars.mail.models import ProjectMail

        register("ai_summary", "rentalars.ai.summary:run_job")
        register("ai_draft", "rentalars.ai.drafts:run_job")
        register("ai_invoice", "rentalars.ai.invoices:run_job")  # MAT-062
        register("ai_incoming_invoice", "rentalars.ai.invoices:run_register_job")  # Incoming invoices
        register("ai_auto_summaries", "rentalars.ai.auto:run_job")  # The nightly summaries
        post_delete.connect(signals.mail_deleted, sender=ProjectMail, dispatch_uid="ai.mail_deleted")
        # Review: a summary that read the chat forgets it when a message of the chat is deleted.
        post_delete.connect(signals.chat_message_deleted, sender=ChatMessage, dispatch_uid="ai.chat_message_deleted")
