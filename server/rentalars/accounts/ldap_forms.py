# SPDX-License-Identifier: GPL-3.0-or-later
"""Forms of the directory settings and of the group assignments (AUT-029)."""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from rentalars.accounts import ldap_client
from rentalars.accounts.models import LdapGroupMapping, LdapSettings, Role
from rentalars.core.audit import record_event
from rentalars.core.forms import StyledForm, StyledModelForm

#: Values a click on "Fill in for OpenLDAP" or "… for Active Directory" proposes (AUT-029).
PRESETS: dict[str, dict[str, Any]] = {
    "openldap": {
        "user_search_filter": "(&(objectClass=inetOrgPerson)(uid={username}))",
        "attribute_username": "uid",
        "attribute_email": "mail",
        "attribute_first_name": "givenName",
        "attribute_last_name": "sn",
        "group_mode": "search",
        "group_search_filter": "(&(objectClass=groupOfNames)(member={user_dn}))",
        "member_of_attribute": "memberOf",
    },
    "ad": {
        "user_search_filter": "(&(objectClass=person)(sAMAccountName={username}))",
        "attribute_username": "sAMAccountName",
        "attribute_email": "mail",
        "attribute_first_name": "givenName",
        "attribute_last_name": "sn",
        "group_mode": "member_of",
        "member_of_attribute": "memberOf",
    },
}


def servers_of(text: str) -> set[tuple[str, int]]:
    """Host and port of every address in a list of server addresses (unusable lines are left out)."""
    found = set()
    for line in (text or "").splitlines():
        try:
            host, port, _use_ssl = ldap_client.parse_uri(line)
        except ValueError:
            continue
        found.add((host.lower(), port))
    return found


def apply_password_change(
    settings: LdapSettings, *, old_uris: str, old_bind_dn: str, new_password: str | None, remove: bool = False
) -> str:
    """Decide what happens to the stored password of the search account after a change of the settings.

    A new password replaces the old one; ``remove`` deletes it. A password given for one server never goes
    to another: when a server was added that was not there before, or the search account (DN) changed, and no
    new password comes with it, the stored password is deleted (as for the AI key, ADM-017, NFA-072).

    Returns:
        ``"stored"``, ``"removed"``, ``"removed_moved"`` or ``""`` (nothing changed).
    """
    if new_password:
        settings.set_bind_password(new_password)
        return "stored"
    if remove and settings.has_bind_password:
        settings.bind_password_encrypted = ""
        return "removed"
    if settings.has_bind_password and (
        not servers_of(settings.server_uris) <= servers_of(old_uris) or settings.bind_dn.strip() != old_bind_dn.strip()
    ):
        settings.bind_password_encrypted = ""
        return "removed_moved"
    return ""


def note_password_change(settings: LdapSettings, change: str) -> None:
    """Write the change of the password (never the password) into the change log."""
    if change:
        record_event(settings, f"ldap.bind_password_{change}")


class LdapSettingsForm(StyledModelForm):
    """All settings of the directory login on one page; the password of the search account is write-only."""

    bind_password = forms.CharField(
        label=_("Password of the search account"),
        required=False,
        strip=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text=_("Leave it empty to keep the stored password. It is stored encrypted and never shown again."),
    )
    remove_bind_password = forms.BooleanField(label=_("Remove the stored password"), required=False)

    class Meta:
        model = LdapSettings
        fields = [
            "enabled",
            "server_uris",
            "start_tls",
            "verify_certificate",
            "ca_certificate_path",
            "ca_certificate_pem",
            "timeout_seconds",
            "bind_dn",
            "user_search_base",
            "user_search_filter",
            "attribute_username",
            "attribute_email",
            "attribute_first_name",
            "attribute_last_name",
            "group_mode",
            "member_of_attribute",
            "group_search_base",
            "group_search_filter",
            "allow_local_login",
            "auto_create_users",
            "link_existing_accounts",
            "sync_daily",
        ]
        widgets = {
            "server_uris": forms.Textarea(
                attrs={
                    "rows": 3,
                    "spellcheck": "false",
                    "autocomplete": "off",
                    "placeholder": "ldaps://dc1.example.com",
                }
            ),
            "ca_certificate_pem": forms.Textarea(
                attrs={"rows": 5, "spellcheck": "false", "autocomplete": "off", "class": "mono"}
            ),
            "bind_dn": forms.TextInput(attrs={"spellcheck": "false", "autocomplete": "off"}),
            "user_search_base": forms.TextInput(attrs={"spellcheck": "false", "autocomplete": "off"}),
            "user_search_filter": forms.TextInput(attrs={"spellcheck": "false", "autocomplete": "off"}),
            "group_search_base": forms.TextInput(attrs={"spellcheck": "false", "autocomplete": "off"}),
            "group_search_filter": forms.TextInput(attrs={"spellcheck": "false", "autocomplete": "off"}),
            "ca_certificate_path": forms.TextInput(attrs={"spellcheck": "false", "autocomplete": "off"}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._old_uris = self.instance.server_uris
        self._old_bind_dn = self.instance.bind_dn
        self.key_outcome = ""
        for name in ("attribute_username", "attribute_email", "attribute_first_name", "attribute_last_name"):
            self.fields[name].widget.attrs.update({"spellcheck": "false", "autocomplete": "off"})
        if not self.instance.has_bind_password:
            del self.fields["remove_bind_password"]

    def save(self, commit: bool = True) -> LdapSettings:
        """Store the settings; decide what happens to the password (see :func:`apply_password_change`)."""
        settings = super().save(commit=False)
        # The model form already put the new values in; the decision about the password needs the old ones.
        self.key_outcome = apply_password_change(
            settings,
            old_uris=self._old_uris,
            old_bind_dn=self._old_bind_dn,
            new_password=self.cleaned_data.get("bind_password") or None,
            remove=bool(self.cleaned_data.get("remove_bind_password")),
        )
        if commit:
            settings.save()
            note_password_change(settings, self.key_outcome)
        return settings


class LdapMappingForm(StyledModelForm):
    """A group of the directory and the roles its members get."""

    roles = forms.ModelMultipleChoiceField(
        label=_("Roles"),
        queryset=Role.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        help_text=_("Members of the group get all of these roles, together with those of their other groups."),
    )

    class Meta:
        model = LdapGroupMapping
        fields = ["group", "roles", "priority", "last_match", "note"]
        widgets = {
            "group": forms.TextInput(
                attrs={
                    "spellcheck": "false",
                    "autocomplete": "off",
                    "placeholder": "cn=admins,ou=groups,dc=example,dc=com",
                }
            )
        }

    def save(self, commit: bool = True) -> LdapGroupMapping:
        """Store the assignment and write a change of its roles into the change log."""
        # The model form saves the roles itself (they are in ``Meta.fields``): note what they were before.
        before = sorted(self.instance.roles.values_list("name", flat=True)) if self.instance.pk else []
        mapping = super().save(commit=commit)
        if commit:
            note_mapping_roles(mapping, before)
        return mapping


def note_mapping_roles(mapping: LdapGroupMapping, before: list[str]) -> None:
    """Write a change of the roles of an assignment into the change log."""
    after = sorted(mapping.roles.values_list("name", flat=True))
    if before != after:
        record_event(mapping, "ldap_mapping.roles_changed", {"before": before, "after": after})


def set_mapping_roles(mapping: LdapGroupMapping, roles: Any) -> None:
    """Replace the roles of an assignment; a change is noted in the change log."""
    before = sorted(mapping.roles.values_list("name", flat=True))
    mapping.roles.set(roles)
    note_mapping_roles(mapping, before)


class PreviewLoginForm(StyledForm):
    """A name (and, if wished, the password) for the dry run "Test login for user"."""

    username = forms.CharField(
        label=_("User name"),
        max_length=ldap_client.MAX_USERNAME_LENGTH,
        widget=forms.TextInput(attrs={"autocomplete": "off", "autocapitalize": "none", "spellcheck": "false"}),
    )
    password = forms.CharField(
        label=_("Password (optional)"),
        required=False,
        strip=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text=_("Only if the password should be checked as well. It is used once and not stored."),
    )
