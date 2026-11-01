# SPDX-License-Identifier: GPL-3.0-or-later
"""Forms of the mail module: mailboxes and their rules, signature, writing a mail, assigning.

Who may send from an address (EML-052), the sender when writing, and
inquiries noted by hand (EML-053).
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from rentalars.core.forms import StyledForm, StyledModelForm, mark_required
from rentalars.mail.models import Mailbox, MailboxAddress, MailSettings, Untagged
from rentalars.mail.signature import clean_signature
from rentalars.masterdata.models import DocumentType

#: The longest signature, in characters of HTML.
SIGNATURE_MAX_LENGTH = 20000


class MailboxForm(StyledModelForm):
    """A mailbox with its roles (EML-041, EML-001 ff.). Passwords are only ever written, never shown (EML-002)."""

    imap_password = forms.CharField(
        label=_("IMAP password"),
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text=_("Leave empty to keep the stored password."),
    )
    smtp_password = forms.CharField(
        label=_("SMTP password"),
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text=_("Leave empty to keep the stored password."),
    )

    class Meta:
        model = Mailbox
        fields = [
            "name",
            "address",
            "is_active",
            "for_correspondence",
            "is_outgoing",
            "for_system",
            "imap_host",
            "imap_port",
            "imap_security",
            "imap_user",
            "inbox_folder",
            "process_untagged",
            "untagged_since",  # EML-049
            "untagged_unread_only",  # EML-049
            "after_assignment",
            "done_folder",
            "smtp_host",
            "smtp_port",
            "smtp_security",
            "smtp_same_login",
            "smtp_user",
            "sender_roles",  # EML-052
        ]
        widgets = {"sender_roles": forms.CheckboxSelectMultiple}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # UIX-035: what an active mailbox needs for its roles (mail.mailboxes._check_data, Mailbox.clean).
        fetching = "is_active=on&for_correspondence=on"
        for name in ("imap_host", "imap_user"):
            mark_required(self.fields[name], fetching)
        if not self.instance.imap_password_encrypted:  # a stored password is kept when the field stays empty
            mark_required(self.fields["imap_password"], fetching)
        for name in ("smtp_host", "address"):
            mark_required(self.fields[name], "is_active=on&is_outgoing=on;is_active=on&for_system=on")
        mark_required(self.fields["done_folder"], "for_correspondence=on&after_assignment=move")


class MailboxAddressForm(StyledModelForm):
    """A further address of a mailbox with its rule for mails without tag and its role (EML-047)."""

    class Meta:
        model = MailboxAddress
        fields = [
            "address",
            "untagged",
            "untagged_since",  # EML-049
            "untagged_unread_only",  # EML-049
            "for_service_cases",
            "case_manager",
            "sender_roles",  # EML-052
        ]
        widgets = {"sender_roles": forms.CheckboxSelectMultiple}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        from rentalars.accounts.models import User

        self.fields["case_manager"].queryset = User.objects.filter(is_active=True).order_by(
            "first_name", "last_name", "username"
        )
        self.fields["address"].widget.attrs.update({"autocomplete": "off", "spellcheck": "false"})

    def clean_address(self) -> str:
        """Compare addresses in lower case; one address only once per mailbox."""
        address = (self.cleaned_data.get("address") or "").strip().lower()
        mailbox = self.instance.mailbox if self.instance.mailbox_id else None
        if mailbox is not None and mailbox.aliases.filter(address=address).exclude(pk=self.instance.pk).exists():
            raise ValidationError(_("This address is listed for the mailbox already."))
        return address

    def clean(self) -> dict[str, Any]:
        """Nobody is responsible for service cases an address does not make."""
        cleaned = super().clean() or {}
        if cleaned.get("untagged") != Untagged.SERVICE_CASE:
            cleaned["case_manager"] = None
        return cleaned


class MailRulesForm(StyledModelForm):
    """What holds for all mailboxes: fetch interval, size limit, retention (EML-005, EML-028, EML-031).

    EML-038: the sender name is "name | company" for every mail written in
    Rentalars; the stored name is only a fallback and is not offered here.

    ADM-015: how deployment requests are answered (PER-032) is chosen under
    Firmendaten und Grundeinstellungen (``core.forms.SystemSettingsForm``),
    though it is kept with the mail settings.

    EML-055: whether new messages in projects and in service cases start
    with the lock.
    """

    class Meta:
        model = MailSettings
        # EML-055: how new messages of projects and of service cases start.
        fields = [
            "interval_minutes",
            "max_message_mb",
            "retention_days",
            "lock_new_in_projects",
            "lock_new_in_cases",
            "crew_answer_trusted_server",
        ]


class SignatureForm(StyledForm):
    """The signature of everybody, as HTML with placeholders (EML-034)."""

    html = forms.CharField(
        label=pgettext_lazy("mail", "Signature"),
        required=False,
        max_length=SIGNATURE_MAX_LENGTH,
        widget=forms.Textarea(attrs={"rows": 12, "spellcheck": "false", "data-signature-source": ""}),
        help_text=_(
            "Plain text or HTML. Without HTML tags the line breaks are kept. Links, bold text, tables and "
            "pictures from a web address are possible; scripts and forms are removed."
        ),
    )

    def clean_html(self) -> str:
        """Store only cleaned HTML."""
        return clean_signature(self.cleaned_data["html"])


def _address_field(label: Any, *, required: bool = False, help_text: Any = "") -> forms.CharField:
    """A field for one or more addresses; the page suggests addresses while typing (EML-037)."""
    return forms.CharField(
        label=label,
        max_length=1000,
        required=required,
        help_text=help_text,
        widget=forms.TextInput(attrs={"autocomplete": "off", "spellcheck": "false"}),
    )


#: EML-055: what the choice "With lock" means, on the mail form and the note form.
LOCK_HELP = _(
    "Only those who may see prices and calculation read the message. Without lock, the crew planned in the project "
    "reads it as well."
)


class ComposeForm(StyledForm):
    """Writing or answering a mail from a project (EML-024, EML-025, EML-034, EML-037).

    EML-052: with more than one address the writer may use, ``sender``
    chooses among them; another address is refused like an invalid choice.
    Changing it loads the preview of that address's signature (EML-026, htmx).
    """

    sender = forms.ChoiceField(
        label=_("Sender"),
        help_text=_("Recipients see your name and the company with this address; answers come back to it."),
        error_messages={"invalid_choice": _("You may not send from this address.")},
    )
    to = _address_field(_("To"), required=True, help_text=_("Several addresses separated by commas."))
    cc = _address_field(_("CC"))
    bcc = _address_field(_("BCC"), help_text=_("Gets the mail without the other recipients seeing it."))
    # The page says which tag is added (compose.html); no help text of its own.
    subject = forms.CharField(label=_("Subject"), max_length=400)
    body = forms.CharField(label=_("Text"), widget=forms.Textarea(attrs={"rows": 14}))
    signature = forms.BooleanField(label=_("Add the signature"), required=False, initial=True)
    files = forms.MultipleChoiceField(
        label=_("Files of the project"), required=False, widget=forms.CheckboxSelectMultiple
    )
    documents = forms.MultipleChoiceField(label=_("Documents"), required=False, widget=forms.CheckboxSelectMultiple)
    # EML-055: only for who may set the lock; ticked at first ("neu mit Schloss").
    locked = forms.BooleanField(label=_("With lock"), required=False, initial=True, help_text=LOCK_HELP)

    def __init__(
        self,
        *args: Any,
        file_choices: list[tuple[str, str]],
        document_choices: list[tuple[str, str]],
        has_signature: bool = False,
        sender_choices: list[tuple[str, str]] = (),  # type: ignore[assignment]
        signature_url: str = "",
        can_lock: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        if not can_lock:
            del self.fields["locked"]  # EML-055: the message is open – the page says so
        # EML-052: a choice only where there is something to choose; else the default address.
        if len(sender_choices) > 1:
            self.fields["sender"].choices = list(sender_choices)
            if signature_url and has_signature:
                # EML-026: the preview of the signature follows the address chosen (htmx; without scripts the
                # default's).
                self.fields["sender"].widget.attrs.update(
                    {
                        "hx-get": signature_url,
                        "hx-trigger": "change",
                        "hx-target": "#signature-frame",
                        "hx-swap": "outerHTML",
                        "hx-include": "this",
                    }
                )
        else:
            del self.fields["sender"]
        self.fields["files"].choices = file_choices
        self.fields["documents"].choices = document_choices
        if not file_choices:
            del self.fields["files"]
        if not document_choices:
            del self.fields["documents"]
        if not has_signature:
            del self.fields["signature"]
        suggestions = reverse("mail:address_suggestions")
        for name in ("to", "cc", "bcc"):
            self.fields[name].widget.attrs["data-address-suggest"] = suggestions

    def clean(self) -> dict[str, Any]:
        """Check the addresses of all three fields, each with its own message."""
        from rentalars.mail.sending import split_addresses

        cleaned = super().clean() or {}
        for name in ("to", "cc", "bcc"):
            try:
                split_addresses(cleaned.get(name, "") or "")
            except ValidationError:
                self.add_error(name, _("An address is not valid."))
        return cleaned


class AssignForm(StyledForm):
    """Assign a mail to a project by its number (EML-014, EML-015)."""

    project_number = forms.CharField(label=_("Project number"), max_length=30)


class AttachmentToFilesForm(StyledForm):
    """Take an attachment over into the project files (EML-021)."""

    document_type = forms.ModelChoiceField(
        label=_("Document type"), queryset=DocumentType.objects.none(), required=False
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["document_type"].queryset = DocumentType.objects.filter(is_active=True)


class NoteForm(StyledForm):
    """EML-051: a note in the correspondence – what was said, and when."""

    date = forms.DateTimeField(
        label=_("When"),
        help_text=_("When it happened – now, or earlier: the note stands there in the chronology."),
    )
    subject = forms.CharField(
        label=_("Subject"),
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": _("e.g. Phone call with the customer")}),
        help_text=_("Optional. Empty: the first line of the note."),
    )
    text = forms.CharField(
        label=_("Note"),
        max_length=10_000,
        widget=forms.Textarea(attrs={"rows": 8}),
    )
    # EML-055: only when writing a note, for who may set the lock; ticked at first.
    locked = forms.BooleanField(label=_("With lock"), required=False, initial=True, help_text=LOCK_HELP)

    def __init__(self, *args: Any, can_lock: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not can_lock:
            del self.fields["locked"]


class InquiryForm(StyledForm):
    """EML-053: an inquiry noted by hand – a phone call written down for the office.

    The customer is chosen by typing (``customers:suggest``), as in the
    project form. What is needed is checked by ``mail.inquiries``.
    """

    date = forms.DateTimeField(
        label=_("When"), help_text=_("When the inquiry came in – now, or earlier; never in the future.")
    )
    contact_name = forms.CharField(
        label=_("Who"),
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": _("Name of the caller"), "autocomplete": "off"}),
    )
    phone = forms.CharField(
        label=_("Phone"),
        max_length=60,
        required=False,
        widget=forms.TextInput(attrs={"type": "tel", "autocomplete": "off"}),
    )
    contact_email = forms.EmailField(
        label=_("E-mail address"),
        required=False,
        widget=forms.EmailInput(attrs={"autocomplete": "off", "spellcheck": "false"}),
    )
    customer = forms.ModelChoiceField(
        label=_("Customer"),
        queryset=None,
        required=False,
        widget=forms.HiddenInput,
        help_text=_("Optional. Suggested when the inquiry becomes a project or a service case."),
    )
    subject = forms.CharField(
        label=_("Subject"),
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": _("e.g. Two speakers for Friday")}),
    )
    note = forms.CharField(
        label=_("Note"),
        max_length=9_000,
        required=False,
        widget=forms.Textarea(attrs={"rows": 8}),
        help_text=_("What was asked or agreed. Taken over, it becomes a note in the correspondence."),
    )

    def __init__(self, *args: Any, current_customer: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        from rentalars.customers.models import Customer

        customers = Customer.objects.filter(is_active=True)
        if current_customer is not None:
            # The customer noted stays choosable when deactivated since.
            customers = customers | Customer.objects.filter(pk=current_customer.pk)
        self.fields["customer"].queryset = customers

    @property
    def customer_text(self) -> str:
        """What the customer field shows: the name of the chosen customer."""
        from rentalars.customers.models import Customer

        value = self.data.get("customer") if self.is_bound else self.initial.get("customer")
        if hasattr(value, "pk"):
            return value.name
        customer = Customer.objects.filter(pk=value).first() if str(value or "").isdigit() else None
        return customer.name if customer is not None else ""
