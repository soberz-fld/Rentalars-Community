# SPDX-License-Identifier: GPL-3.0-or-later
"""App configuration of the ``documents`` module."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class DocumentsConfig(AppConfig):
    """Order confirmation, delivery note, invoice and crew disposition as stored PDF files (chapter 5.10)."""

    name = "rentalars.documents"
    label = "documents"
    verbose_name = _("Documents")

    def ready(self) -> None:
        """Make the background tasks known (NFA-041).

        Handing invoices to Lexware Office (DOK-011); the activity of a service
        case summarised by AI for the monthly statement (DOK-016).
        """
        from rentalars.core.jobs import register

        register("lexware", "rentalars.documents.lexware:run_transfer_job")
        register("statement_activity", "rentalars.documents.statements:run_summary_job")
        # DOK-054: the export for an audit of a large archive.
        register("audit_export", "rentalars.documents.audit_export:run_job")
