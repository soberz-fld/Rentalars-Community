# SPDX-License-Identifier: GPL-3.0-or-later
"""The form of an automation: "if …, then …" (ADM-013).

Each action has fields of its own – the subject and text of an answer, the
title and text of a notification, the text of an open item – so that the
page can show only those of the chosen action. They are stored in the
``subject`` and ``text`` of the rule. What fits together is checked by the
rule itself (``Automation.problems``), for the browser and the API alike.
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from rentalars.automations.models import (
    CASE_TITLE_LENGTH,
    CASE_TRIGGERS,
    OPEN_ITEM_LENGTH,
    TARGET_CASE_STATUSES,
    Action,
    Automation,
)

#: The answer to an inquiry, as suggested for a new rule.
DEFAULT_REPLY_SUBJECT = _("Confirmation of receipt: {betreff}")
DEFAULT_REPLY_TEXT = _(
    "Hello {name},\n\nthank you for your mail. It has arrived, and we will get back to you as soon as we can.\n\n"
    "Kind regards\n{firma}"
)

#: Where the texts of each action are entered: model field → form field.
TEXT_FIELDS = {
    Action.REPLY: {"subject": "reply_subject", "text": "reply_text"},
    Action.NOTIFY: {"subject": "notify_title", "text": "notify_text"},
    Action.OPEN_ITEM: {"subject": "", "text": "item_text"},
    Action.CASE_STATUS: {"subject": "", "text": ""},  # PRJ-112: the new status only
    # MAT-057: title and description of the new case; the subject of the entry under Anfragen.
    Action.CREATE_CASE: {"subject": "case_title", "text": "case_text"},
    Action.CREATE_INQUIRY: {"subject": "inquiry_subject", "text": ""},
}


def _status_choices() -> list[tuple[str, str]]:
    from rentalars.projects.models import ProjectStatus

    return [("", "–"), *ProjectStatus.choices]


def _case_status_choices() -> list[tuple[str, Any]]:
    """PRJ-112: the condition on the status of a service case – any, or one."""
    from rentalars.projects.models import CaseStatus

    return [("", _("any status")), *CaseStatus.choices]


def _new_case_status_choices() -> list[tuple[str, Any]]:
    """PRJ-112: the statuses a rule can set – those that need no follow-up."""
    from rentalars.projects.models import CaseStatus

    return [("", "–"), *((value, label) for value, label in CaseStatus.choices if value in TARGET_CASE_STATUSES)]


class AutomationForm(forms.ModelForm):
    """A rule with its trigger, condition and action."""

    status = forms.ChoiceField(label=_("Status"), choices=_status_choices, required=False)
    # PRJ-112: for the triggers of the service cases the condition is the status of the case (stored in ``status``).
    case_status = forms.ChoiceField(
        label=_("Status of the service case"),
        choices=_case_status_choices,
        required=False,
        help_text=_("The status the service case has when it happens."),
    )
    new_case_status = forms.ChoiceField(label=_("New status"), choices=_new_case_status_choices, required=False)
    reply_subject = forms.CharField(
        label=_("Subject of the answer"),
        max_length=250,
        required=False,
        help_text=_("Empty: “AW:” and the subject of the mail."),
    )
    reply_text = forms.CharField(
        label=_("Text of the answer"), widget=forms.Textarea(attrs={"rows": 8}), required=False
    )
    notify_title = forms.CharField(
        label=_("Title of the notification"),
        max_length=250,
        required=False,
        help_text=_("One line. Empty: what happened, e.g. the project and its new status."),
    )
    notify_text = forms.CharField(
        label=_("Text of the notification"), widget=forms.Textarea(attrs={"rows": 4}), required=False
    )
    item_text = forms.CharField(label=_("Open item"), max_length=OPEN_ITEM_LENGTH, required=False)
    # MAT-057: the service case made of a defect report.
    case_title = forms.CharField(
        label=_("Title of the service case"),
        max_length=CASE_TITLE_LENGTH,
        required=False,
        help_text=_("Empty: “Defect”, the ID and the short name, e.g. “Defect 0042 SM58”."),
    )
    case_text = forms.CharField(
        label=_("Description of the service case"),
        widget=forms.Textarea(attrs={"rows": 5}),
        required=False,
        help_text=_("Empty: what is defective, the item, where it was found, who reported it and when."),
    )
    case_manager = forms.ModelChoiceField(
        label=_("Responsible"),
        queryset=None,
        required=False,
        help_text=_("Is told that the case is theirs. Empty: nobody yet."),
    )
    inquiry_subject = forms.CharField(
        label=_("Subject in the list of inquiries"),
        max_length=250,
        required=False,
        help_text=_("Empty: “Defect”, the ID, the short name and what is defective."),
    )

    class Meta:
        model = Automation
        fields = [
            "name",
            "is_active",
            "trigger",
            "mailbox",
            "status",
            "answer",
            "communication",  # PRJ-112
            "action",
            "recipient",
            "user",
            "new_case_status",  # PRJ-112
        ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        from rentalars.accounts.models import User
        from rentalars.mail.models import Mailbox

        self.fields["mailbox"].queryset = Mailbox.objects.filter(for_correspondence=True)
        self.fields["mailbox"].empty_label = _("every mailbox that takes them in")
        self.fields["mailbox"].help_text = _(
            "Only mails without project tag that a mailbox takes in as inquiries count (Settings → E-mail)."
        )
        self.fields["trigger"].label = _("What happens")
        self.fields["action"].label = _("What Rentalars does")
        self.fields["user"].queryset = User.objects.filter(is_active=True).order_by(
            "first_name", "last_name", "username"
        )
        self.fields["case_manager"].queryset = self.fields["user"].queryset  # MAT-057
        self.fields["recipient"].required = False
        self.fields["answer"].required = False
        self.fields["communication"].required = False
        rule = self.instance
        if rule.trigger in CASE_TRIGGERS:
            self.initial["case_status"] = rule.status
            self.initial["status"] = ""
        if rule.pk:
            for model_field, form_field in TEXT_FIELDS.get(rule.action, {}).items():
                if form_field:
                    self.initial[form_field] = getattr(rule, model_field)
            if rule.action == Action.CREATE_CASE:
                self.initial["case_manager"] = rule.user_id
                self.initial["user"] = None
        else:
            self.initial.setdefault("reply_subject", str(DEFAULT_REPLY_SUBJECT))
            self.initial.setdefault("reply_text", str(DEFAULT_REPLY_TEXT))

    def _post_clean(self) -> None:
        """Take over the texts of the chosen action, tidy the rule and let it check itself."""
        super()._post_clean()
        rule = self.instance
        data = getattr(self, "cleaned_data", {})
        fields = TEXT_FIELDS.get(rule.action, {})
        rule.subject = (data.get(fields.get("subject") or "", "") or "").strip()
        rule.text = (data.get(fields.get("text") or "", "") or "").strip()
        if rule.trigger in CASE_TRIGGERS:
            rule.status = data.get("case_status", "") or ""  # PRJ-112
        if rule.action == Action.CREATE_CASE:
            rule.user = data.get("case_manager")  # MAT-057: who is responsible for the new case
        rule.normalise()
        for model_field, message in rule.problems().items():
            form_field = fields.get(model_field, model_field) if model_field in ("subject", "text") else model_field
            if model_field == "user" and rule.action == Action.CREATE_CASE:
                form_field = "case_manager"
            if model_field == "status" and rule.trigger in CASE_TRIGGERS:
                form_field = "case_status"
            if form_field in self.fields and form_field not in self.errors:
                self.add_error(form_field, message)
            elif form_field not in self.fields:
                self.add_error(None, message)
