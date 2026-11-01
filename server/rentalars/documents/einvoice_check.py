# SPDX-License-Identifier: GPL-3.0-or-later
"""Keeping and repeating the check of e-invoices (DOK-042).

The rules are in :mod:`rentalars.documents.einvoice_rules`. Here the result is stored: for an outgoing document in
``DocumentCheck`` (the document itself never changes, DOK-007), for an incoming invoice in the column ``einvoice_check``.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.documents import einvoice_rules
from rentalars.documents.models import Document, DocumentCheck


def store_report(document: Document, report: einvoice_rules.Report) -> DocumentCheck:
    """Keep the result of a check beside the document (one per document; a new check replaces the old)."""
    check, _created = DocumentCheck.objects.update_or_create(
        document=document,
        defaults={
            "checked_at": timezone.now(),
            "syntax": report.syntax,
            "profile": report.profile,
            "error_count": len(report.errors),
            "warning_count": len(report.warnings),
            "findings": [vars(finding) for finding in report.findings],
            "ruleset": report.ruleset,
        },
    )
    return check


def recheck(document: Document) -> DocumentCheck:
    """Check the XML of a document again, with the rules of today.

    Raises:
        ValidationError: The document has no e-invoice.
    """
    if not document.xml_file:
        raise ValidationError(_("This document has no e-invoice."))
    with document.xml_file.open("rb") as handle:
        report = einvoice_rules.check(handle.read())
    return store_report(document, report)


def check_of(document: Document) -> DocumentCheck | None:
    """The stored check of a document, if there is one."""
    try:
        return document.einvoice_check
    except DocumentCheck.DoesNotExist:
        return None


def report_json(check: DocumentCheck | None) -> dict[str, Any]:
    """The check as the page and the API show it; ``{}`` while there is none."""
    if check is None:
        return {}
    return {
        "syntax": check.syntax,
        "profile": check.profile,
        "ruleset": check.ruleset,
        "checked_at": check.checked_at.isoformat(),
        "ok": check.ok,
        "errors": check.error_count,
        "warnings": check.warning_count,
        "findings": check.findings,
    }


def store_incoming(invoice: Any, data: bytes) -> dict[str, Any]:
    """Check the XML of an incoming invoice and keep the result with it (no refusal: the invoice stays)."""
    report = einvoice_rules.check(data).as_json()
    report["checked_at"] = timezone.now().isoformat()
    invoice.einvoice_check = report
    invoice.save(update_fields=["einvoice_check"])
    return report


def recheck_incoming(invoice: Any) -> dict[str, Any]:
    """Check the XML of an incoming invoice again.

    Raises:
        ValidationError: The invoice has no e-invoice.
    """
    name = invoice.xml_name
    if not name:
        raise ValidationError(_("This invoice has no e-invoice."))
    try:
        with invoice.file.storage.open(name, "rb") as handle:
            data = handle.read()
    except OSError as error:
        raise ValidationError(_("The e-invoice file cannot be opened.")) from error
    return store_incoming(invoice, data)
