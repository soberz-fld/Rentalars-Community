# SPDX-License-Identifier: GPL-3.0-or-later
"""Forms of the AI settings (EML-040, ADM-017)."""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from rentalars.ai import auto, privacy
from rentalars.ai.client import AIError, validate_base_url
from rentalars.ai.models import AIProvider, AISettings, Source
from rentalars.core.forms import StyledForm, StyledModelForm
from rentalars.projects.models import CaseStatus, ProjectStatus


def source_choices() -> list[tuple[str, str]]:
    """Off, the local AI, and every provider of the list (``p<id>``)."""
    choices = [(Source.OFF.value, str(Source.OFF.label)), (Source.LOCAL.value, str(Source.LOCAL.label))]
    choices += [(f"p{provider.pk}", provider.name) for provider in AIProvider.objects.order_by("name")]
    return choices


def encode_source(source: str, provider: AIProvider | None) -> str:
    """The value of the choice for a stored source."""
    if source == Source.PROVIDER and provider is not None:
        return f"p{provider.pk}"
    return source if source in {Source.OFF, Source.LOCAL} else Source.OFF


def decode_source(value: str) -> tuple[str, AIProvider | None]:
    """A chosen value as ``(source, provider)``."""
    if value.startswith("p") and value[1:].isdigit():
        provider = AIProvider.objects.filter(pk=int(value[1:])).first()
        if provider is not None:
            return Source.PROVIDER, provider
    return (value, None) if value in {Source.OFF, Source.LOCAL} else (Source.OFF, None)


class UsesForm(StyledForm):
    """Which provider serves which use (EML-040, ADM-017)."""

    summary = forms.ChoiceField(
        label=_("Summary of the correspondence"),
        help_text=_(
            "Who summarises the mails of a project. The mails go there and nowhere else. The short overview "
            "without AI is always there."
        ),
    )
    draft = forms.ChoiceField(
        label=_("Reply draft for mails"),
        help_text=_("In “Write mail”, the AI suggests a reply from the mails so far; you check it and send it."),
    )
    # MAT-062: the text of an uploaded invoice goes there.
    invoice = forms.ChoiceField(
        label=_("Reading invoices"),
        help_text=_(
            "In “Enter a purchase”, the AI reads an uploaded invoice (PDF with text) and suggests supplier, number, "
            "date and positions; you check every row before anything is created. Off: only number, date and "
            "supplier are taken from the text."
        ),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        choices = source_choices()
        self.fields["summary"].choices = choices
        self.fields["draft"].choices = choices
        self.fields["invoice"].choices = choices

    @classmethod
    def for_settings(cls, data: Any, ai_settings: AISettings) -> UsesForm:
        """The form with the stored choices."""
        return cls(
            data,
            initial={
                "summary": encode_source(ai_settings.summary_source, ai_settings.summary_provider),
                "draft": encode_source(ai_settings.draft_source, ai_settings.draft_provider),
                "invoice": encode_source(ai_settings.invoice_source, ai_settings.invoice_provider),
            },
        )

    def apply(self, ai_settings: AISettings) -> None:
        """Write the choices into the settings (the caller saves)."""
        ai_settings.summary_source, ai_settings.summary_provider = decode_source(self.cleaned_data["summary"])
        ai_settings.draft_source, ai_settings.draft_provider = decode_source(self.cleaned_data["draft"])
        ai_settings.invoice_source, ai_settings.invoice_provider = decode_source(self.cleaned_data["invoice"])


class ProviderForm(StyledModelForm):
    """An OpenAI-compatible interface (ADM-017). The API key can be set or removed, never read."""

    api_key = forms.CharField(
        label=_("API key"),
        required=False,
        strip=True,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text=_("Leave it empty to keep the stored key. Local servers usually need none."),
    )
    remove_api_key = forms.BooleanField(label=_("Remove the stored key"), required=False)

    class Meta:
        model = AIProvider
        fields = ["name", "base_url", "model", "timeout_seconds", "context_tokens"]
        widgets = {
            "base_url": forms.TextInput(
                attrs={
                    "inputmode": "url",
                    "spellcheck": "false",
                    "autocomplete": "off",
                    "placeholder": "https://api.example.com/v1",
                }
            ),
            "model": forms.TextInput(attrs={"spellcheck": "false", "autocomplete": "off"}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._old_base_url = self.instance.base_url if self.instance.pk else ""
        self.key_removed = False
        self.fields["base_url"].validators.append(validate_base_url)
        self.fields["base_url"].help_text = _(
            "Where the interface answers, usually ending in /v1 – e.g. http://192.168.1.30:11434/v1 for Ollama in "
            "the company network. Internal addresses only if the operator allows them in the configuration file."
        )
        if not (self.instance.pk and self.instance.has_api_key):
            del self.fields["remove_api_key"]

    def clean_base_url(self) -> str:
        """Without a slash at the end."""
        return self.cleaned_data["base_url"].strip().rstrip("/")

    def save(self, commit: bool = True) -> AIProvider:
        """Store the provider; a new key replaces the old one, "remove" removes it.

        A changed server (scheme, host or port) without a new key removes the
        stored key – it never goes to another server (ADM-017); ``key_removed`` says so.
        """
        new_url = self.cleaned_data["base_url"]
        provider = super().save(commit=False)
        # The model form already put the new address in; the key decision needs the old one.
        provider.base_url = self._old_base_url
        new_key = self.cleaned_data.get("api_key") or ("" if self.cleaned_data.get("remove_api_key") else None)
        self.key_removed = provider.take_address(new_url, new_key=new_key)
        if commit:
            provider.save()
        return provider


#: The classes of data that can be taken out of texts, in words.
PRIVACY_CHOICES = [
    (privacy.IBAN, _("Bank data: IBAN")),
    (privacy.CARD, _("Bank data: card numbers")),
    (privacy.SECRET, _("Secrets: passwords, tokens, keys in links")),
    (privacy.EMAIL, _("E-mail addresses")),
    (privacy.PHONE, _("Phone numbers")),
]


class AutoSettingsForm(StyledModelForm):
    """The automatic summaries – off until opted in – and the caps and data classes of all summaries.

    Switching on needs a ticked confirmation that names the provider; it is asked again when the provider of the
    summaries is another one than the one agreed to (``rentalars.ai.auto.consent_holds``).
    """

    privacy_remove = forms.MultipleChoiceField(
        label=_("Taken out of every text before it goes to the AI"),
        choices=PRIVACY_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text=_(
            "Applies to summaries by hand and to the automatic ones. Recognised by their shape; names, street "
            "addresses and what is said in free text cannot be recognised."
        ),
    )
    auto_project_statuses = forms.MultipleChoiceField(
        label=_("Projects in these statuses"),
        choices=ProjectStatus.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    auto_case_statuses = forms.MultipleChoiceField(
        label=_("Service cases in these statuses"),
        choices=CaseStatus.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    consent = forms.BooleanField(
        label=_("I have read what goes to the provider and agree"),
        required=False,
        help_text=_("Needed to switch the automatic summaries on, and again if the provider of the summaries changes."),
    )

    class Meta:
        model = AISettings
        fields = [
            "auto_enabled",
            "auto_window_start",
            "auto_window_end",
            "auto_max_per_run",
            "auto_token_budget",
            "auto_project_statuses",
            "auto_case_statuses",
            "auto_min_interval_hours",
            "auto_min_mails",
            "auto_keep_versions",
            "auto_include_notes",
            "auto_include_chat",
            "auto_include_locked",
            "send_attachment_names",
            "privacy_remove",
            "max_input_chars",
            "manual_per_hour",
        ]
        labels = {
            "auto_enabled": _("Make automatic summaries every night"),
            "auto_include_notes": _("Read notes written into the correspondence"),
            "auto_include_chat": _("Read the chat of the project"),
            "auto_include_locked": _("Read messages with lock"),
            "send_attachment_names": _("Send the names of attached files"),
        }
        help_texts = {
            "auto_enabled": _(
                "Off until you switch it on. Then a project or service case that has new mails since its last "
                "summary gets a new one at night. Nothing is sent before."
            ),
            "auto_include_locked": _(
                "In projects every message starts with the lock, so the job would read nothing there if this is off. "
                "The summary is shown only to those who read all messages."
            ),
        }

    def __init__(self, *args: Any, user: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["auto_window_start"].required = True
        self.fields["auto_window_end"].required = True

    def clean(self) -> dict[str, Any]:
        """Switching on (or on for another provider) needs the confirmation; the window and the caps must make sense."""
        cleaned = super().clean()
        if cleaned.get("auto_enabled") and not self.errors:
            instance = self.instance
            needs = (
                not instance.auto_enabled
                or auto.consent_state(instance) in {"changed", "unavailable"}
                or not instance.auto_consent_key
            )
            if needs:
                try:
                    from rentalars.ai.client import endpoint_for
                    from rentalars.ai.models import Use

                    endpoint_for(Use.SUMMARY)
                except AIError as error:
                    raise forms.ValidationError(
                        _("Automatic summaries need a provider for the summaries first: %(reason)s")
                        % {"reason": error},
                        code="no_provider",
                    ) from error
                if not cleaned.get("consent"):
                    self.add_error("consent", _("Confirm what goes to the provider to switch the summaries on."))
        return cleaned

    def save(self, commit: bool = True) -> AISettings:
        """Store the settings; record who agreed to what when the summaries are switched on (or on for a new provider)."""
        settings_row = super().save(commit=False)
        if settings_row.auto_enabled:
            if not self.initial.get("auto_enabled") or self.cleaned_data.get("consent"):
                auto.switch_on(settings_row, self.user)
        else:
            auto.switch_off(settings_row)
        if commit:
            settings_row.save()
        return settings_row
