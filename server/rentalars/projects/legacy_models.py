# SPDX-License-Identifier: GPL-3.0-or-later
"""The records of "Altprojekte importieren": a batch of uploaded invoices and one record per invoice (legacy import; PRJ-130).

The requirement: import old projects from invoices. The user uploads PDF invoices of the old system; Rentalars
reads them (:mod:`rentalars.ai.legacy_invoices`, :mod:`rentalars.projects.legacy_text`), shows a preview that is checked
and corrected, and only after an explicit confirmation creates a closed project and a historic invoice per invoice
(:mod:`rentalars.projects.legacy_import`).

* :class:`LegacyImportBatch` – one upload of one or several PDFs by one user.
* :class:`LegacyImportItem` – one PDF: its hash, the proposal that is edited in the preview, and – once taken
  over – what was created from it (customer, project, invoice), who did it and when. It stays as the provenance
  record; it also serves as the flag that a ``documents.Document`` is a historic invoice (``Document.legacy_item``).
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class ItemState(models.TextChoices):
    """Where one invoice of a batch stands."""

    UPLOADED = "uploaded", _("waiting to be read")
    READING = "reading", _("being read")
    READ = "read", _("to be checked")
    DUPLICATE = "duplicate", _("already imported")
    IMPORTED = "imported", _("taken over")
    SKIPPED = "skipped", _("skipped")
    UNDONE = "undone", _("import undone")


class LegacyImportBatch(models.Model):
    """One upload: the invoices of one go, read by one background task."""

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(_("started"), default=timezone.now)
    #: The task that reads the invoices (``core.jobs``); its progress is shown on the page of the batch.
    job = models.ForeignKey(
        "core.BackgroundJob", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    #: Whether the AI was asked for the invoices (the setting "Reading invoices" was on when the task started).
    used_ai = models.BooleanField(_("read with AI"), default=False)

    class Meta:
        verbose_name = _("import of old invoices")
        verbose_name_plural = _("imports of old invoices")
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"#{self.pk} {self.created_at:%Y-%m-%d %H:%M}"


class LegacyImportItem(models.Model):
    """One invoice PDF of a batch, with the proposal read from it and – after the confirmation – its result."""

    batch = models.ForeignKey(LegacyImportBatch, on_delete=models.CASCADE, related_name="items")
    position = models.PositiveIntegerField(default=0)
    original_name = models.CharField(_("file"), max_length=200)
    #: SHA-256 of the PDF: the same file is never imported twice.
    sha256 = models.CharField(_("checksum"), max_length=64, db_index=True)
    size = models.PositiveIntegerField(default=0)
    #: The kept file below ``DATA_DIR/legacy-invoices`` until the invoice is taken over or dropped.
    stored_name = models.CharField(max_length=60, blank=True)
    state = models.CharField(_("state"), max_length=10, choices=ItemState.choices, default=ItemState.UPLOADED)
    #: What reading said, for the user: no text, a scan, the AI did not answer …
    message = models.CharField(max_length=500, blank=True)
    #: The editable proposal (``legacy_import.Draft.to_json``); empty until the invoice was read.
    proposal = models.JSONField(default=dict, blank=True)
    #: Several invoices of one event can become one project: this one joins the project of another invoice.
    merge_into = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="joined")

    # --- Traceability: what was created from the invoice ---------------------------------------------------
    invoice_number = models.CharField(_("invoice number"), max_length=60, blank=True, db_index=True)
    invoice_date = models.DateField(_("invoice date"), null=True, blank=True)
    customer = models.ForeignKey(
        "customers.Customer", null=True, blank=True, on_delete=models.SET_NULL, related_name="legacy_items"
    )
    #: Set when the customer was created by this import (not an existing one).
    customer_created = models.BooleanField(default=False)
    project = models.ForeignKey(
        "projects.Project", null=True, blank=True, on_delete=models.SET_NULL, related_name="legacy_items"
    )
    document = models.OneToOneField(
        "documents.Document", null=True, blank=True, on_delete=models.SET_NULL, related_name="legacy_item"
    )
    #: The status of the historic invoice: paid or not; the day it was paid, if known.
    paid = models.BooleanField(_("paid"), default=False)
    paid_on = models.DateField(_("paid on"), null=True, blank=True)
    imported_at = models.DateTimeField(_("taken over"), null=True, blank=True)
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    #: The last entry of the change log when the import was done: whatever is logged after it is a later change,
    #: and then the import is no longer undone (``legacy_import.undo_problems``).
    audit_mark = models.PositiveBigIntegerField(default=0)
    undone_at = models.DateTimeField(null=True, blank=True)
    #: Whether the invoice was read by the AI or by the text patterns.
    source = models.CharField(max_length=10, blank=True)

    class Meta:
        verbose_name = _("old invoice")
        verbose_name_plural = _("old invoices")
        ordering = ["batch_id", "position", "id"]

    def __str__(self) -> str:
        return self.invoice_number or self.original_name

    @property
    def is_open(self) -> bool:
        """Whether the invoice can still be checked and taken over."""
        return self.state in {ItemState.READ, ItemState.UPLOADED, ItemState.READING}

    @property
    def is_imported(self) -> bool:
        """Whether the invoice was taken over (and not undone)."""
        return self.state == ItemState.IMPORTED

    def provenance(self) -> dict[str, Any]:
        """Where created objects come from, for the history of the project: number, date, user, time."""
        return {
            "number": self.invoice_number,
            "date": self.invoice_date.isoformat() if self.invoice_date else "",
            "user": str(self.imported_by) if self.imported_by_id else "",
            "at": self.imported_at.isoformat() if self.imported_at else "",
        }
