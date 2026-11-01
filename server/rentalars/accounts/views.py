# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views of the accounts module: login, own account, users, roles."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import authenticate, login, update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import translation
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from rentalars.accounts import notices, services, twofactor
from rentalars.accounts.forms import ApiTokenForm, LanguageForm, LoginForm, NewPasswordForm, RoleForm, UserForm
from rentalars.accounts.models import ApiToken, Role, SecurityEvent, SecurityEventKind, User, UserSession
from rentalars.accounts.rights import Level, Module, module_required, request_rights
from rentalars.accounts.sessions import end_session
from rentalars.accounts.tables import ROLE_TABLE, SECURITY_EVENT_TABLE, USER_TABLE
from rentalars.core.i18n import user_language
from rentalars.core.listing import paginate
from rentalars.core.models import CompanyProfile, SystemSettings


def DIRECTORY_UNAVAILABLE_TEXT() -> str:  # noqa: N802 - a text, looked up in the language of the request
    """What the login says when the company directory (LDAP) did not answer (AUT-029)."""
    return _(
        "The company directory could not be reached just now. If your account is kept there, try again later or "
        "ask your administrator."
    )


def login_view(request: HttpRequest) -> HttpResponse:
    """The login page (AUT-001, AUT-002) with protection against guessing (AUT-005)."""
    next_url = request.POST.get("next") or request.GET.get("next") or ""
    if request.user.is_authenticated:
        return redirect("core:home")
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        identifier = form.cleaned_data["username"]
        ip_address = services.client_ip(request)
        if services.is_locked_out(identifier, ip_address):
            form.add_error(None, _("Too many failed attempts. Please wait a few minutes and try again."))
        else:
            user = authenticate(request, username=identifier, password=form.cleaned_data["password"])
            # AUT-005: with two-factor login the success is noted once the code is right (see login_code).
            if user is None or not user.has_two_factor:
                services.record_login_attempt(identifier, ip_address, successful=user is not None)
            if user is None:
                services.record_security_event(SecurityEventKind.LOGIN_FAILED, identifier=identifier, request=request)
                # The message is the same for an unknown name and a wrong
                # password, so that names cannot be found out by trying.
                form.add_error(None, _("Name or password are wrong."))
                if getattr(request, "directory_unavailable", False):  # AUT-029
                    form.add_error(None, DIRECTORY_UNAVAILABLE_TEXT())
            elif user.has_two_factor:
                # AUT-006: the password was right; the code of the app is still missing.
                twofactor.remember_pending_login(request, user, next_url, identifier)
                return redirect("accounts:login_code")
            else:
                login(request, user)
                return _after_login(request, next_url)
    return render(request, "accounts/login.html", {"form": form, "next": next_url})


def _after_login(request: HttpRequest, next_url: str) -> HttpResponse:
    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect("core:home")


def login_code(request: HttpRequest) -> HttpResponse:
    """The second step of the login: the code of the authenticator app (AUT-006)."""
    pending = twofactor.pending_login(request)
    if pending is None:
        twofactor.forget_pending_login(request)
        messages.info(request, _("Please log in again."))
        return redirect("accounts:login")
    user = User.objects.filter(pk=pending["user"], is_active=True).first()
    if user is None:
        twofactor.forget_pending_login(request)
        return redirect("accounts:login")
    error = ""
    if request.method == "POST":
        ip_address = services.client_ip(request)
        if services.is_locked_out(user.username, ip_address):
            twofactor.forget_pending_login(request)
            messages.error(request, _("Too many failed attempts. Please wait a few minutes and try again."))
            return redirect("accounts:login")
        if twofactor.verify_code(user, request.POST.get("code", "")):
            twofactor.forget_pending_login(request)
            services.record_login_attempt(user.username, ip_address, successful=True)
            typed = pending.get("identifier") or ""
            if typed and typed != user.username:  # the failed passwords were counted under the name as typed
                services.record_login_attempt(typed, ip_address, successful=True)
            user.backend = pending["backend"]
            login(request, user)
            return _after_login(request, pending.get("next", ""))
        # A new session starts with a new count of its own – the count of the name is what stops the guessing.
        services.record_login_attempt(user.username, ip_address, successful=False)
        services.record_security_event(SecurityEventKind.SECOND_FACTOR_FAILED, user=user, request=request)
        pending["attempts"] = pending.get("attempts", 0) + 1
        if pending["attempts"] >= twofactor.MAX_CODE_ATTEMPTS:
            twofactor.forget_pending_login(request)
            messages.error(request, _("Too many wrong codes. Please log in again."))
            return redirect("accounts:login")
        request.session[twofactor.PENDING_SESSION_KEY] = pending
        error = _("The code is not right. Use the current code of your app, or a recovery code.")
    return render(request, "accounts/login_code.html", {"error": error})


@login_required
def two_factor_setup(request: HttpRequest) -> HttpResponse:
    """Set up two-factor login: scan the QR code, confirm with a code (AUT-006)."""
    user = request.user
    if user.has_two_factor:
        return render(
            request,
            "accounts/two_factor.html",
            {"required": user.needs_two_factor, "password_external": services.password_is_external(user)},
        )
    secret = request.session.get("rentalars_new_totp_secret") or twofactor.new_secret()
    request.session["rentalars_new_totp_secret"] = secret
    error = ""
    if request.method == "POST":
        try:
            codes = twofactor.enable(user, secret, request.POST.get("code", ""))
        except ValidationError as exception:
            error = " ".join(exception.messages)
        else:
            request.session.pop("rentalars_new_totp_secret", None)
            messages.success(request, _("Two-factor login is set up."))
            return render(request, "accounts/two_factor_codes.html", {"codes": codes})
    issuer = CompanyProfile.load().name or "Rentalars"
    uri = twofactor.provisioning_uri(secret, user.username, f"Rentalars {issuer}" if issuer != "Rentalars" else issuer)
    return render(
        request,
        "accounts/two_factor_setup.html",
        {
            "qr": mark_safe(twofactor.qr_code_svg(uri)),  # noqa: S308 - SVG made by segno from our own data
            "secret": " ".join(secret[index : index + 4] for index in range(0, len(secret), 4)),
            "error": error,
            "required": user.needs_two_factor,
        },
    )


@require_POST
@login_required
def two_factor_disable(request: HttpRequest) -> HttpResponse:
    """Switch two-factor login off – not possible where a role requires it (AUT-006)."""
    user = request.user
    if user.needs_two_factor:
        messages.error(request, _("A role of yours requires two-factor login; it cannot be switched off."))
        return redirect("accounts:two_factor_setup")
    if services.password_is_external(user):
        # AUT-029: the password is not known here – the current code proves it is the owner.
        if not twofactor.verify_code(user, request.POST.get("code", "")):
            messages.error(request, _("The code is not right."))
            return redirect("accounts:two_factor_setup")
    elif not user.check_password(request.POST.get("password", "")):
        messages.error(request, _("The password is not right."))
        return redirect("accounts:two_factor_setup")
    twofactor.disable(user, by=user)
    messages.success(request, _("Two-factor login is switched off."))
    return redirect("accounts:account")


@login_required
def sessions(request: HttpRequest) -> HttpResponse:
    """Where the user is logged in, with the possibility to end each session (AUT-008)."""
    current_key = request.session.session_key
    if request.method == "POST":
        if request.POST.get("all") == "1":
            for item in UserSession.objects.filter(user=request.user).exclude(session_key=current_key):
                end_session(item)
            messages.success(request, _("All other sessions are ended."))
        else:
            item = get_object_or_404(UserSession, pk=request.POST.get("session"), user=request.user)
            if item.session_key == current_key:
                messages.info(request, _("This is the session you are using. Log out instead."))
            else:
                end_session(item)
                messages.success(request, _("The session is ended."))
        return redirect("accounts:sessions")
    return render(
        request,
        "accounts/sessions.html",
        {
            "sessions": UserSession.objects.filter(user=request.user),
            "current_key": current_key,
            "idle_minutes": SystemSettings.load().session_idle_minutes,
        },
    )


@module_required(Module.ADMINISTRATION)
def security_log(request: HttpRequest) -> HttpResponse:
    """Logins, failed logins, second factor, sessions – and changes to users and roles (AUT-022)."""
    from django.contrib.contenttypes.models import ContentType

    from rentalars.core.history import describe
    from rentalars.core.models import AuditLogEntry

    events = SecurityEvent.objects.select_related("user")
    kind = request.GET.get("kind", "")
    if kind in SecurityEventKind.values:
        events = events.filter(kind=kind)
    who = request.GET.get("q", "").strip()
    if who:
        events = events.filter(
            Q(identifier__icontains=who) | Q(user__username__icontains=who) | Q(ip_address__startswith=who)
        )
    # UIX-040: columns, sorting, groups and CSV.
    table = SECURITY_EVENT_TABLE.state(request)
    events = table.order(events)
    if table.wants_csv:
        return table.csv_response(events, _("Security log"))
    page = paginate(request, events)
    from rentalars.accounts.models import LdapGroupMapping, LdapSettings

    types = [
        ContentType.objects.get_for_model(model) for model in (User, Role, ApiToken, LdapSettings, LdapGroupMapping)
    ]  # AUT-029: the directory settings too
    changes = AuditLogEntry.objects.filter(content_type__in=types).order_by("-timestamp")[:50]
    return render(
        request,
        "accounts/security_log.html",
        {
            "page": page,
            "table": table,
            "rows": table.rows(page),
            "kinds": SecurityEventKind.choices,
            "kind": kind,
            "q": who,
            "changes": describe(list(changes), request_rights(request)),
        },
    )


@require_POST
@module_required(Module.ADMINISTRATION, Level.WRITE)
def user_reset_two_factor(request: HttpRequest, pk: int) -> HttpResponse:
    """Switch two-factor login off for a user who lost phone and recovery codes (AUT-006)."""
    user = get_object_or_404(User, pk=pk)
    if user.has_two_factor:
        twofactor.disable(user, by=request.user)
        messages.success(
            request,
            _("Two-factor login of %(user)s is switched off; it is set up again at the next login.") % {"user": user},
        )
    return redirect("accounts:user_edit", pk=pk)


def account(request: HttpRequest) -> HttpResponse:
    """The page "My account": profile, password change and personal API tokens (AUT-021)."""
    password_form = PasswordChangeForm(request.user, request.POST if request.POST.get("form") == "password" else None)
    token_form = ApiTokenForm(request.POST if request.POST.get("form") == "token" else None)
    # UIX-029: the own language of the interface.
    language_form = LanguageForm(
        request.POST if request.POST.get("form") == "language" else None, instance=request.user, prefix="language"
    )
    new_key = None
    if request.method == "POST" and request.POST.get("form") == "language" and language_form.is_valid():
        chosen = language_form.save()
        with translation.override(user_language(chosen)):
            messages.success(request, _("The language was changed."))
        return redirect("accounts:account")
    password_external = services.password_is_external(request.user)  # AUT-029
    if (
        request.method == "POST"
        and request.POST.get("form") == "password"
        and not password_external
        and password_form.is_valid()
    ):
        password_form.save()
        update_session_auth_hash(request, password_form.user)  # keep this browser logged in
        services.record_security_event(SecurityEventKind.PASSWORD_CHANGED, user=request.user, request=request)
        notices.credentials_changed(request.user, notices.PASSWORD)  # AUT-030
        messages.success(request, _("Your password was changed."))
        return redirect("accounts:account")
    if request.method == "POST" and request.POST.get("form") == "token" and token_form.is_valid():
        _token, new_key = ApiToken.create_for_user(
            request.user,
            token_form.cleaned_data["name"],
            read_only=token_form.cleaned_data["read_only"],
            allowed_modules=list(token_form.cleaned_data["allowed_modules"]),
        )
        token_form = ApiTokenForm()
    return render(
        request,
        "accounts/account.html",
        {
            "password_form": password_form,
            "token_form": token_form,
            "language_form": language_form,
            "tokens": ApiToken.objects.filter(user=request.user),
            "password_external": password_external,
            "new_key": new_key,
            # AUT-012: the person in personnel this account belongs to, if any.
            "own_person": getattr(request.user, "person", None),
        },
    )


@require_POST
def token_revoke(request: HttpRequest, pk: int) -> HttpResponse:
    """Revoke one of the user's own API tokens."""
    get_object_or_404(ApiToken, pk=pk, user=request.user).revoke()
    messages.success(request, _("The token was revoked."))
    return redirect("accounts:account")


# --- Users (AUT-009, AUT-011) ---------------------------------------------------


@module_required(Module.ADMINISTRATION)
def user_list(request: HttpRequest) -> HttpResponse:
    """All user accounts with their roles."""
    # Accounts whose time is up show as deactivated here even before the nightly job ran (AUT-024).
    services.deactivate_expired_accounts()
    users = User.objects.prefetch_related("roles")
    text = request.GET.get("q", "").strip()
    if text:
        users = (
            users.filter(username__icontains=text)
            | users.filter(email__icontains=text)
            | users.filter(last_name__icontains=text)
        )
    table = USER_TABLE.state(request)
    users = table.order(users)
    if table.wants_csv:
        return table.csv_response(users, _("Users"))
    page = paginate(request, users)
    return render(
        request, "accounts/user_list.html", {"page": page, "table": table, "rows": table.rows(page), "q": text}
    )


@module_required(Module.ADMINISTRATION, Level.WRITE)
def user_create(request: HttpRequest) -> HttpResponse:
    """Invite a new user by e-mail; the user sets the password personally (AUT-011)."""
    form = UserForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            user = services.invite_user(
                username=form.cleaned_data["username"],
                email=form.cleaned_data["email"],
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
                roles=form.cleaned_data["roles"],
                language=form.cleaned_data.get("language", ""),
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            if form.cleaned_data["is_superuser"]:
                user.is_superuser = True
                user.save()
            if user.email:
                from rentalars.mail.server import warn_without_server

                # EML-048: without a mail server the invitation went nowhere; the page says so.
                if warn_without_server(request):
                    messages.success(request, _("%(user)s was created.") % {"user": user})
                    return redirect("accounts:user_edit", pk=user.pk)
                messages.success(request, _("%(user)s was invited by e-mail.") % {"user": user})
                return redirect("accounts:user_list")
            # AUT-027: without an address the way in is a one-time password.
            messages.success(
                request, _("%(user)s was created. Without an e-mail address, set a one-time password.") % {"user": user}
            )
            return redirect("accounts:user_edit", pk=user.pk)
    return render(request, "accounts/user_form.html", {"form": form, "is_new": True})


@module_required(Module.ADMINISTRATION, Level.WRITE)
def user_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """Change master data and roles of a user."""
    user = get_object_or_404(User, pk=pk)
    form = UserForm(request.POST or None, instance=user)
    if request.method == "POST" and form.is_valid():
        roles = form.cleaned_data.pop("roles")
        edited = form.save(commit=False)
        edited.save()
        services.set_user_roles(edited, [*roles, *form.directory_roles])  # AUT-029: the directory's roles stay
        messages.success(request, _("User saved."))
        return redirect("accounts:user_list")
    return render(
        request,
        "accounts/user_form.html",
        {
            "form": form,
            "is_new": False,
            "edited_user": user,
            "password_external": services.password_is_external(user),  # AUT-029
        },
    )


@require_POST
@module_required(Module.ADMINISTRATION, Level.WRITE)
def user_set_active(request: HttpRequest, pk: int) -> HttpResponse:
    """Deactivate or reactivate a user (AUT-009)."""
    user = get_object_or_404(User, pk=pk)
    try:
        services.set_user_active(user, active=request.POST.get("active") == "1", acting_user=request.user)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, _("User saved."))
    return redirect("accounts:user_edit", pk=user.pk)


@require_POST
@module_required(Module.ADMINISTRATION, Level.WRITE)
def user_send_invitation(request: HttpRequest, pk: int) -> HttpResponse:
    """Send the link for setting a password again."""
    user = get_object_or_404(User, pk=pk, is_active=True)
    try:
        services.send_invitation(user)
    except ValidationError as error:  # AUT-029: the password lives in the directory
        messages.error(request, " ".join(error.messages))
        return redirect("accounts:user_edit", pk=user.pk)
    from rentalars.mail.server import warn_without_server

    if not warn_without_server(request):  # EML-048
        messages.success(request, _("The invitation was sent to %(email)s.") % {"email": user.email})
    return redirect("accounts:user_edit", pk=user.pk)


@require_POST
@module_required(Module.ADMINISTRATION, Level.WRITE)
def user_one_time_password(request: HttpRequest, pk: int) -> HttpResponse:
    """Set a one-time password and show it once; the next login asks for an own one (AUT-027)."""
    user = get_object_or_404(User, pk=pk)
    try:
        password = services.set_one_time_password(user, acting_user=request.user)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect("accounts:user_edit", pk=user.pk)
    return render(request, "accounts/one_time_password.html", {"edited_user": user, "password": password})


@login_required
def new_password(request: HttpRequest) -> HttpResponse:
    """Choose an own password – required after a one-time password (AUT-027)."""
    form = NewPasswordForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        replaced = form.user.has_usable_password()  # AUT-030: a first password replaces nothing
        form.save()
        update_session_auth_hash(request, form.user)
        services.record_security_event("password_changed", user=form.user, request=request)
        if replaced:
            notices.credentials_changed(form.user, notices.PASSWORD)
        messages.success(request, _("Your password is set."))
        return redirect("core:home")
    return render(request, "accounts/new_password.html", {"form": form, "required": request.user.must_change_password})


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    """Choose a new password with the link from the e-mail (AUT-004, AUT-027).

    AUT-030: a password that replaces one is noticed to the account's
    address and noted in the security log. The link of an invitation sets the
    first password – that replaces nothing and sends no notice.
    """

    form_class = NewPasswordForm
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")

    def form_valid(self, form: NewPasswordForm) -> HttpResponse:
        """Store the password; then the security log and the notice."""
        replaced = form.user.has_usable_password()
        response = super().form_valid(form)
        services.record_security_event(
            SecurityEventKind.PASSWORD_CHANGED,
            user=form.user,
            request=self.request,
            detail="reset by link" if replaced else "first password by link",
        )
        if replaced:
            notices.credentials_changed(form.user, notices.PASSWORD_RESET)
        return response


# --- Roles (AUT-010) --------------------------------------------------------------


@module_required(Module.ADMINISTRATION)
def role_list(request: HttpRequest) -> HttpResponse:
    """All roles with the number of users that have them; a table with columns, sorting, CSV (UIX-040)."""
    table = ROLE_TABLE.state(request)
    roles = table.order(Role.objects.annotate(user_count=Count("users")))
    if table.wants_csv:
        return table.csv_response(roles, _("Roles"))
    page = table.paginate(roles)  # UIX-050 (UIX-012)
    return render(
        request, "accounts/role_list.html", {"roles": page, "table": table, "rows": table.rows(page), "page": page}
    )


@module_required(Module.ADMINISTRATION, Level.WRITE)
def role_edit(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    """Create or change a role with the rights matrix."""
    role = get_object_or_404(Role, pk=pk) if pk else None
    form = RoleForm(request.POST or None, instance=role)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Role saved."))
        return redirect("accounts:role_list")
    return render(request, "accounts/role_form.html", {"form": form, "role": role})


@require_POST
@module_required(Module.ADMINISTRATION, Level.DELETE)
def role_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a role that no user has any more (ADM-006)."""
    role = get_object_or_404(Role, pk=pk)
    if role.users.exists():
        messages.error(request, _("This role is still assigned to users and cannot be deleted."))
    else:
        role.delete()
        messages.success(request, _("Role deleted."))
    return redirect("accounts:role_list")
