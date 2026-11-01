# SPDX-License-Identifier: GPL-3.0-or-later
"""Addresses of the mail module."""

from django.urls import path

from rentalars.mail import views

app_name = "mail"

urlpatterns = [
    # Correspondence of a project (EML-019 ff.).
    path("projects/<project:pk>/mails/", views.project_mails, name="project_mails"),
    path("projects/<project:pk>/mails/new/", views.compose, name="compose"),
    # EML-026, EML-052: the preview of the signature of the sender chosen while writing (htmx).
    path("projects/<project:pk>/mails/new/signature/", views.compose_signature, name="compose_signature"),
    # EML-051: notes in the correspondence.
    path("projects/<project:pk>/mails/note/", views.note_create, name="note_create"),
    path("projects/<project:pk>/mails/<int:mail_pk>/note/", views.note_edit, name="note_edit"),
    path("projects/<project:pk>/mails/<int:mail_pk>/", views.mail_detail, name="detail"),
    path("projects/<project:pk>/mails/<int:mail_pk>/body/", views.mail_body, name="body"),
    path("projects/<project:pk>/mails/<int:mail_pk>/assign/", views.reassign, name="reassign"),
    path("projects/<project:pk>/mails/<int:mail_pk>/delete/", views.mail_delete, name="delete"),
    # EML-055: put the lock on a message or take it away.
    path("projects/<project:pk>/mails/<int:mail_pk>/lock/", views.mail_lock, name="lock"),
    path(
        "projects/<project:pk>/mails/<int:mail_pk>/attachments/<int:attachment_pk>/",
        views.attachment,
        name="attachment",
    ),
    path(
        "projects/<project:pk>/mails/<int:mail_pk>/attachments/<int:attachment_pk>/to-files/",
        views.attachment_to_files,
        name="attachment_to_files",
    ),
    # Projects → Inquiries (EML-014, EML-042) – below /projects/, where the tab is (NFA-074).
    path("projects/inquiries/", views.unknown_list, name="unknown_list"),
    path("projects/inquiries/<int:pk>/assign/", views.unknown_assign, name="unknown_assign"),
    path("projects/inquiries/<int:pk>/dismiss/", views.unknown_dismiss, name="unknown_dismiss"),
    # PRJ-107: several off the list at once, and projects suggested for the field "Project number".
    path("projects/inquiries/dismiss/", views.unknown_dismiss_many, name="unknown_dismiss_many"),
    path("projects/inquiries/projects/", views.project_suggestions, name="project_suggestions"),
    # EML-053: inquiries noted by hand. ``inquiry_pk``, not ``pk``: below the mail module ``pk`` names a
    # project (``core.changes.watch_keys``).
    path("projects/inquiries/new/", views.inquiry_create, name="inquiry_create"),
    path("projects/inquiries/<int:inquiry_pk>/edit/", views.inquiry_edit, name="inquiry_edit"),
    path("projects/inquiries/<int:inquiry_pk>/delete/", views.inquiry_delete, name="inquiry_delete"),
    # The address suggestions of the recipient fields (EML-037).
    path("projects/mail-addresses/", views.address_suggestions, name="address_suggestions"),
    # In the settings: mailboxes, rules, signature and mail log (EML-002, EML-034, EML-035, EML-039, EML-041).
    # ``mailbox_pk``, not ``pk``: below the mail module ``pk`` always names a project.
    path("administration/mail/", views.mailbox_settings, name="settings"),
    # Fetching now (EML-005) – a button of the settings.
    path("administration/mail/fetch/", views.fetch_now, name="fetch_now"),
    path("administration/mail/mailboxes/new/", views.mailbox_edit, name="mailbox_create"),
    path("administration/mail/mailboxes/<int:mailbox_pk>/", views.mailbox_edit, name="mailbox_edit"),
    path("administration/mail/mailboxes/<int:mailbox_pk>/delete/", views.mailbox_delete, name="mailbox_delete"),
    path("administration/mail/mailboxes/<int:mailbox_pk>/check/", views.mailbox_check, name="mailbox_check"),
    # EML-047: the further addresses (aliases) of a mailbox.
    path(
        "administration/mail/mailboxes/<int:mailbox_pk>/addresses/new/",
        views.mailbox_address_edit,
        name="address_create",
    ),
    path(
        "administration/mail/mailboxes/<int:mailbox_pk>/addresses/<int:address_pk>/",
        views.mailbox_address_edit,
        name="address_edit",
    ),
    path(
        "administration/mail/mailboxes/<int:mailbox_pk>/addresses/<int:address_pk>/delete/",
        views.mailbox_address_delete,
        name="address_delete",
    ),
    # EML-026: the signature of one mailbox.
    path(
        "administration/mail/mailboxes/<int:mailbox_pk>/signature/",
        views.mailbox_signature_edit,
        name="mailbox_signature",
    ),
    path("administration/mail/signature/", views.signature_edit, name="signature"),
    path("administration/mail/signature/preview/", views.signature_preview, name="signature_preview"),
    path("administration/mail/log/", views.mail_log, name="log"),
]
