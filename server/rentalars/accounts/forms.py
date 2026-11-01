# SPDX-License-Identifier: GPL-3.0-or-later
"""Forms of the accounts module."""

from __future__ import annotations

from typing import Any

from django import forms
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.models import Role, User
from rentalars.accounts.rights import FUTURE_MODULES, Level, Module, ProjectScope, SpecialRight
from rentalars.core.forms import StyledForm, StyledModelForm
from rentalars.core.i18n import LANGUAGE_CHOICES, installation_language


class LoginForm(forms.Form):
    """Name (or e-mail address) and password (AUT-002)."""

    username = forms.CharField(
        label=_("Username or e-mail address"),
        max_length=254,
        widget=forms.TextInput(attrs={"autocomplete": "username", "autofocus": True, "autocapitalize": "none"}),
    )
    password = forms.CharField(
        label=_("Password"), strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "current-password"})
    )


class UserForm(StyledModelForm):
    """Master data and roles of a user. Passwords are never set here (AUT-011)."""

    roles = forms.ModelMultipleChoiceField(
        label=_("Roles"),
        queryset=Role.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text=_("With several roles, the highest right of each module counts."),
    )

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "first_name",
            "last_name",
            "language",
            "roles",
            "valid_until",
            "is_superuser",
            "local_account",  # AUT-029
        ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["language"] = language_field()
        # AUT-029: roles the directory gave are shown apart and cannot be ticked off here.
        self.directory_roles: list[Role] = []
        if self.instance.pk:
            from rentalars.accounts.services import _directory_role_ids

            ids = _directory_role_ids(self.instance)
            self.directory_roles = list(Role.objects.filter(pk__in=ids).order_by("name"))
            self.fields["roles"].queryset = Role.objects.exclude(pk__in=ids)


def language_field() -> forms.ChoiceField:
    """The choice of the interface language: the installation's, German or English (UIX-029)."""
    from django.utils.translation import gettext

    default = dict(LANGUAGE_CHOICES)[installation_language()]
    return forms.ChoiceField(
        label=_("Language"),
        choices=[("", gettext("As the installation (%(language)s)") % {"language": default}), *LANGUAGE_CHOICES],
        required=False,
        help_text=_("The language of the pages, mails and notifications for this user."),
    )


class LanguageForm(StyledModelForm):
    """The own interface language on "My account" (UIX-029)."""

    class Meta:
        model = User
        fields = ["language"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["language"] = language_field()
        self.fields["language"].help_text = _("Pages, mails and notifications for you are written in this language.")


class RoleForm(StyledForm):
    """A role as a matrix: one access level per module, plus special rights (AUT-010, AUT-015)."""

    name = forms.CharField(label=_("Name"), max_length=80)
    description = forms.CharField(label=_("Description"), max_length=250, required=False)
    special_rights = forms.MultipleChoiceField(
        label=_("Special rights"),
        choices=SpecialRight.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text=_("Granted separately, whatever the module rights are."),
    )
    requires_two_factor = forms.BooleanField(
        label=_("Two-factor login required"),
        required=False,
        help_text=_("Users with this role must set up a second factor before they can work."),
    )
    project_scope = forms.ChoiceField(
        label=_("Project access"),
        choices=ProjectScope.choices,
        help_text=_(
            "“Assigned projects only”: the rights on projects and packing lists hold only in projects the user is a "
            "member of or is scheduled for as crew. Crew scheduled for a project sees its deployment view. "
            "“Overview without planning”: in its projects the role opens only the overview, the packing list "
            "and the chat – not the planning, schedule, access or history, whatever a membership says. Service "
            "cases the user is responsible for or takes part in are always open to work on."
        ),
    )

    def __init__(self, *args: Any, instance: Role | None = None, **kwargs: Any) -> None:
        self.instance = instance or Role()
        initial = kwargs.setdefault("initial", {})
        if instance is not None:
            initial.update(
                name=instance.name,
                description=instance.description,
                special_rights=instance.special_rights,
                project_scope=instance.project_scope,
                requires_two_factor=instance.requires_two_factor,
            )
        super().__init__(*args, **kwargs)
        for value, label in Module.choices:
            self.fields[f"module_{value}"] = forms.TypedChoiceField(
                label=label,
                choices=Level.choices,
                coerce=int,
                widget=forms.RadioSelect,
                initial=self.instance.level_of(value),
            )

    @property
    def module_fields(self) -> list[tuple[forms.BoundField, bool]]:
        """The module fields with a flag "arrives in a later stage", for the matrix."""
        return [(self[f"module_{value}"], value in FUTURE_MODULES) for value in Module.values]

    def clean_name(self) -> str:
        """Role names are unique."""
        name = self.cleaned_data["name"].strip()
        if Role.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(_("A role with this name already exists."))
        return name

    def save(self) -> Role:
        """Store the matrix as module levels and special rights of the role."""
        role = self.instance
        role.name = self.cleaned_data["name"]
        role.description = self.cleaned_data["description"]
        role.special_rights = list(self.cleaned_data["special_rights"])
        role.project_scope = self.cleaned_data["project_scope"]
        role.requires_two_factor = self.cleaned_data["requires_two_factor"]
        role.module_levels = {value: self.cleaned_data[f"module_{value}"] for value in Module.values}
        role.full_clean()
        role.save()
        return role


class ApiTokenForm(StyledForm):
    """Name and restrictions of a new API token (AUT-021)."""

    name = forms.CharField(label=_("What is the token for?"), max_length=80)
    read_only = forms.BooleanField(label=_("Read-only"), required=False)
    allowed_modules = forms.MultipleChoiceField(
        label=_("Limit to modules"),
        choices=Module.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text=_("Nothing ticked: all modules you may access."),
    )


class ResetPasswordForm(PasswordResetForm):
    """The form behind "Forgot your password?" (AUT-004), for invited accounts too (AUT-027).

    Django sends the link only to accounts that already have a password. An
    invited user who lost the invitation has none yet – and got nothing. Here
    every active account with that address gets the link.
    """

    def get_users(self, email: str) -> Any:
        """Every active account with this address, with or without a password."""
        from rentalars.accounts.models import User
        from rentalars.accounts.services import password_is_external

        # AUT-029: the password of a directory account lives in the directory.
        return (
            user
            for user in User.objects.filter(email__iexact=email, is_active=True)
            if not user.has_expired and not password_is_external(user)
        )

    def send_mail(
        self, subject_template_name: str, email_template_name: str, context: dict[str, Any], *args: Any, **kwargs: Any
    ) -> None:
        """Write the mail in the language of the account it is for (UIX-029)."""
        from rentalars.core.i18n import for_user

        with for_user(context.get("user")):
            super().send_mail(subject_template_name, email_template_name, context, *args, **kwargs)


class NewPasswordForm(SetPasswordForm):
    """Choose an own password: through the link of an e-mail, or after a one-time password (AUT-027)."""

    def save(self, commit: bool = True) -> Any:
        """Store the password; a one-time password no longer asks for a change."""
        self.user.must_change_password = False
        return super().save(commit=commit)
