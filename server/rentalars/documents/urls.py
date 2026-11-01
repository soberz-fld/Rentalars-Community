# SPDX-License-Identifier: GPL-3.0-or-later
"""Addresses of the documents module."""

from django.urls import path

from rentalars.documents import (
    accounting_views,
    archive_views,
    bank_views,
    euer_views,
    free_views,
    outgoing_views,
    payment_views,
    statement_views,
    template_views,
    views,
)

app_name = "documents"

urlpatterns = [
    path("projects/<project:pk>/documents/", views.document_list, name="list"),
    path("projects/<project:pk>/documents/preview/", views.document_preview, name="preview"),
    path("projects/<project:pk>/documents/new/", views.document_create, name="create"),
    path("documents/<int:pk>/pdf/", views.document_file, name="file"),
    path("documents/<int:pk>/xml/", views.document_xml, name="xml"),
    path("documents/<int:pk>/cancel/", views.document_cancel, name="cancel"),
    path("documents/<int:pk>/credit/", views.document_credit, name="credit"),  # A partial credit note
    # DOK-015: "Rechnung gestellt" and "Keine Rechnung".
    path("projects/<project:pk>/invoice/", views.invoice_mark, name="invoice_mark"),
    # PRJ-081: the deployment view of a project as PDF "Einsatzübersicht".
    path("projects/<project:pk>/deployment/pdf/", views.deployment_pdf, name="deployment_pdf"),
    # DOK-011, DOK-012: handing invoices to the accounting.
    path("documents/<int:pk>/lexware/", accounting_views.lexware_transfer, name="lexware_transfer"),
    path("administration/accounting/", accounting_views.accounting, name="accounting"),
    path("administration/accounting/lexware/check/", accounting_views.lexware_check, name="lexware_check"),
    path("administration/accounting/datev/", accounting_views.datev_export, name="datev_export"),
    path("administration/accounting/datev/preview/", accounting_views.datev_preview, name="datev_preview"),
    # DOK-019, DOK-020: the main entry "Buchhaltung" – the outgoing documents first.
    path("accounting/documents/", outgoing_views.outgoing_list, name="outgoing"),
    path("accounting/documents/download/", outgoing_views.outgoing_download, name="outgoing_download"),
    # DOK-048, DOK-042: payments, open items and the check of the e-invoice.
    path("accounting/documents/<int:pk>/payments/", payment_views.document_payments, name="payments"),
    path("accounting/documents/<int:pk>/check/", payment_views.document_check, name="check"),
    path("accounting/open-items/", payment_views.open_items, name="open_items"),
    # DOK-050: bank statements
    path("accounting/bank/", bank_views.bank_page, name="bank"),
    path("accounting/bank/upload/", bank_views.bank_upload, name="bank_upload"),
    path("accounting/bank/<int:pk>/book/", bank_views.bank_book, name="bank_book"),
    path("accounting/bank/<int:pk>/ignore/", bank_views.bank_ignore, name="bank_ignore"),
    path("accounting/bank/<int:pk>/restore/", bank_views.bank_restore, name="bank_restore"),
    path("accounting/euer/", euer_views.euer_page, name="euer"),  # DOK-045
    path("accounting/archive/", archive_views.archive_page, name="archive"),  # DOK-043
    path("accounting/archive/verify/", archive_views.archive_verify, name="archive_verify"),
    path("accounting/archive/export/", archive_views.audit_export_download, name="audit_export"),  # DOK-046
    path("accounting/archive/export/start/", archive_views.audit_export_start, name="audit_export_start"),  # DOK-054
    path("accounting/archive/procedure/", archive_views.procedure_page, name="procedure"),
    # Outgoing documents without a project – the dialog, the draft with its lines, the issued document.
    path("accounting/documents/new/", free_views.free_new, name="free_new"),
    path("accounting/documents/drafts/<int:pk>/", free_views.free_edit, name="free_edit"),
    path("accounting/documents/drafts/<int:pk>/lines/add/", free_views.free_line_add, name="free_line_add"),
    path(
        "accounting/documents/drafts/<int:pk>/lines/<int:line_pk>/edit/",
        free_views.free_line_edit,
        name="free_line_edit",
    ),
    path(
        "accounting/documents/drafts/<int:pk>/lines/<int:line_pk>/delete/",
        free_views.free_line_delete,
        name="free_line_delete",
    ),
    path(
        "accounting/documents/drafts/<int:pk>/lines/<int:line_pk>/move/",
        free_views.free_line_move,
        name="free_line_move",
    ),
    path("accounting/documents/drafts/<int:pk>/preview/", free_views.free_preview, name="free_preview"),
    path("accounting/documents/drafts/<int:pk>/issue/", free_views.free_issue, name="free_issue"),
    path("accounting/documents/drafts/<int:pk>/delete/", free_views.free_delete, name="free_delete"),
    path("accounting/documents/<int:pk>/", free_views.free_document, name="free_document"),
    path("accounting/documents/<int:pk>/send/", free_views.free_send, name="free_send"),
    path("accounting/documents/<int:pk>/cancel/", free_views.free_cancel, name="free_cancel"),
    # DOK-016: Buchhaltung → Monatsabrechnung – the monthly statements of service cases per customer.
    # DOK-019: moved from "Projekte" (/projects/service-cases/monthly/); NFA-074: no redirect from the old addresses.
    path("accounting/monthly/", statement_views.statement_overview, name="statements"),
    path("accounting/monthly/new/", statement_views.statement_create, name="statement_create"),
    path("accounting/monthly/<int:pk>/", statement_views.statement_detail, name="statement"),
    path("accounting/monthly/<int:pk>/delete/", statement_views.statement_delete, name="statement_delete"),
    path(
        "accounting/monthly/<int:pk>/jobs/<int:job_pk>/",
        statement_views.statement_job,
        name="statement_job",
    ),
    # DOK-018: the default texts of the document templates in English or German.
    path(
        "administration/document-templates/default-texts/",
        template_views.template_defaults,
        name="template_defaults",
    ),
]
