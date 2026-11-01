# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages of the directory login: settings, group assignments, tests (AUT-029).

In the settings ("Einstellungen → Benutzer und Rechte → Verzeichnis (LDAP)", module "Administration": read to see,
write to change):

* all settings of the connection, the search for users and groups and the behaviour at the login;
* the table of group assignments – which group of the directory gets which roles;
* "Test connection", "Test login for user" (a dry run: found entry, attributes, groups, resulting roles – nothing
  is written) and the comparison of all accounts with the directory, first as a preview.

The tests use the saved settings.
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from rentalars.accounts import ldap_client, ldap_sync
from rentalars.accounts.ldap_forms import PRESETS, LdapMappingForm, LdapSettingsForm, PreviewLoginForm
from rentalars.accounts.models import LdapGroupMapping, LdapSettings, User, has_local_administrator
from rentalars.accounts.rights import Level, Module, module_required, request_rights


def password_removed_text(change: str) -> str:
    """What the page and the API say about the stored password after a change of the settings."""
    return {
        "stored": _("The password of the search account was stored."),
        "removed": _("The stored password of the search account was removed."),
        "removed_moved": _(
            "The servers or the search account changed, so the stored password was removed: it is never sent to "
            "another server. Enter the password again."
        ),
    }.get(change, "")


def name_only_warning(mapping: LdapGroupMapping) -> str:
    """The warning for an assignment that names its group by name only (page and API)."""
    return _(
        "“%(group)s” is only a name: it matches a group of that name anywhere in the directory, also in a part "
        "that others can write to. Use the full DN of the group."
    ) % {"group": mapping.group}


def _may_change(request: HttpRequest) -> bool:
    return request_rights(request).has_level(Module.ADMINISTRATION, Level.WRITE)


def _page(request: HttpRequest, form: LdapSettingsForm | None = None, **extra: Any) -> HttpResponse:
    """The settings page with everything on it; ``extra`` carries the result of a test."""
    settings = LdapSettings.load()
    can_write = _may_change(request)
    if form is None:
        initial = PRESETS.get(request.GET.get("preset", "")) if request.method == "GET" else None
        form = LdapSettingsForm(instance=settings, initial=initial)
    if not can_write:
        for field in form.fields.values():
            field.disabled = True
    mappings = list(LdapGroupMapping.objects.prefetch_related("roles"))
    context = {
        "form": form,
        "settings": settings,
        "mappings": mappings,
        "can_write": can_write,
        "can_delete": request_rights(request).has_level(Module.ADMINISTRATION, Level.DELETE),
        "login_form": PreviewLoginForm(prefix="try"),
        "linked_users": User.objects.exclude(ldap_dn="").filter(local_account=False).count(),
        "local_administrator": has_local_administrator(),
        "password_unreadable": settings.has_bind_password and not settings.bind_password_readable,
        "warnings": ldap_sync.warnings_for(settings),  # unsafe settings are said out loud
        **extra,
    }
    return render(request, "accounts/ldap_settings.html", context)


@module_required(Module.ADMINISTRATION)
def ldap_settings(request: HttpRequest) -> HttpResponse:
    """Look at and change the settings of the directory login."""
    if request.method == "POST":
        if not _may_change(request):
            raise PermissionDenied
        settings = LdapSettings.load()
        form = LdapSettingsForm(request.POST, instance=settings)
        if form.is_valid():
            form.save()
            messages.success(request, _("The settings of the directory login were saved."))
            text = password_removed_text(form.key_outcome)
            if text and form.key_outcome != "stored":
                messages.warning(request, text)
            return redirect("accounts:ldap_settings")
        return _page(request, form)
    return _page(request)


def _ready_config(request: HttpRequest) -> ldap_client.DirectoryConfig | None:
    """The saved settings as a snapshot for a test; ``None`` (with a message) if they are not complete."""
    settings = LdapSettings.load()
    if not settings.uris or not settings.user_search_base:
        messages.error(request, _("Enter and save at least a server and the search base for users first."))
        return None
    try:
        return ldap_client.DirectoryConfig.from_settings(settings)
    except ldap_client.DirectoryError as error:
        messages.error(request, str(error))
        return None


@require_POST
@module_required(Module.ADMINISTRATION, Level.WRITE)
def ldap_test_connection(request: HttpRequest) -> HttpResponse:
    """Try the saved settings step by step: servers, encryption, search account, search bases."""
    config = _ready_config(request)
    if config is None:
        return redirect("accounts:ldap_settings")
    return _page(request, connection_report=ldap_client.check_connection(config))


@require_POST
@module_required(Module.ADMINISTRATION, Level.WRITE)
def ldap_test_login(request: HttpRequest) -> HttpResponse:
    """The dry run: what a login of this user would find and do – nothing is written."""
    form = PreviewLoginForm(request.POST, prefix="try")
    if not form.is_valid():
        return _page(request, login_error=_("Enter the user name."))
    settings = LdapSettings.load()
    if _ready_config(request) is None:
        return redirect("accounts:ldap_settings")
    try:
        preview = ldap_sync.preview_login(
            settings,
            form.cleaned_data["username"],
            form.cleaned_data["password"],
            request=request,
            acting_user=request.user,
        )
    except ldap_client.DirectoryError as error:
        return _page(request, login_error=str(error))
    except ValueError:
        return _page(request, login_error=_("This is not a usable user name."))
    return _page(request, login_preview=preview, login_name=form.cleaned_data["username"])


@require_POST
@module_required(Module.ADMINISTRATION, Level.WRITE)
def ldap_sync_accounts(request: HttpRequest) -> HttpResponse:
    """Compare all accounts of the directory with it: ``preview`` shows the differences, ``apply`` writes them."""
    if _ready_config(request) is None:
        return redirect("accounts:ldap_settings")
    apply = request.POST.get("mode") == "apply"
    try:
        report = ldap_sync.compare_accounts(
            LdapSettings.load(), apply=apply, force=request.POST.get("force") == "1" and apply
        )
    except ldap_client.DirectoryError as error:
        messages.error(request, str(error))
        return redirect("accounts:ldap_settings")
    if apply and report.applied:
        messages.success(request, _("The accounts were compared with the directory and brought up to date."))
        return redirect("accounts:ldap_settings")
    return _page(request, sync_report=report.as_document(), sync_stopped=report.stopped)


@require_POST
@module_required(Module.ADMINISTRATION, Level.WRITE)
def ldap_adopt_dn(request: HttpRequest) -> HttpResponse:
    """Move the link of an account to the new entry of a user who was moved in the directory."""
    name = request.POST.get("username", "")
    try:
        done = ldap_sync.adopt_dn(LdapSettings.load(), name, request=request)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    except ldap_client.DirectoryError as error:
        messages.error(request, str(error))
    except ValueError:
        messages.error(request, _("This is not a usable user name."))
    else:
        messages.success(
            request,
            _("The account “%(name)s” is now linked to the new entry of the directory.") % {"name": done["username"]},
        )
    return redirect("accounts:ldap_settings")


# --- Group assignments ---------------------------------------------------------------------------------------


@module_required(Module.ADMINISTRATION, Level.WRITE)
def ldap_mapping_edit(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    """Create or change the assignment of a group to roles."""
    mapping = get_object_or_404(LdapGroupMapping, pk=pk) if pk else None
    form = LdapMappingForm(
        request.POST or None, instance=mapping, initial={"roles": mapping.roles.all()} if mapping else None
    )
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        messages.success(request, _("The assignment was saved."))
        if saved.is_name_only:
            messages.warning(request, name_only_warning(saved))
        return redirect("accounts:ldap_settings")
    return render(request, "accounts/ldap_mapping_form.html", {"form": form, "mapping": mapping})


@require_POST
@module_required(Module.ADMINISTRATION, Level.DELETE)
def ldap_mapping_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete an assignment; roles users got through it are taken back at their next login."""
    mapping = get_object_or_404(LdapGroupMapping, pk=pk)
    mapping.delete()
    messages.success(request, _("The assignment was deleted. The roles it gave are taken back at the next login."))
    return redirect("accounts:ldap_settings")
