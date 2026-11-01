# SPDX-License-Identifier: GPL-3.0-or-later
"""Business logic for accounts: login protection, invitations, role changes.

Browser views and API views both call these functions (API-002).
"""

from __future__ import annotations

import datetime
from collections.abc import Iterable
from typing import Any

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import gettext as _

from rentalars.accounts.models import LoginAttempt, Role, User
from rentalars.core.audit import record_event
from rentalars.core.models import CompanyProfile, SystemSettings

#: An IP address may fail this many times more often than a single account
#: before it is blocked. Several colleagues may share one office address.
IP_ATTEMPT_FACTOR = 4

#: Login attempts older than this are deleted by the daily maintenance.
LOGIN_ATTEMPT_RETENTION = datetime.timedelta(days=30)


# --- Protection against password guessing (AUT-005) -------------------------


def normalise_identifier(identifier: str) -> str:
    """Bring a typed login name into the form used for counting attempts."""
    return identifier.strip().lower()[:254]


def is_locked_out(identifier: str, ip_address: str | None) -> bool:
    """Tell whether further login attempts are currently refused.

    Rule: after ``login_max_attempts`` failed attempts for the same name
    within ``login_lockout_minutes``, the name is blocked until the oldest of
    those failures is older than the lockout period. A successful login
    clears the count. The same applies per IP address with a higher limit.

    Example with the defaults (5 attempts, 15 minutes): five wrong passwords
    at 10:00 block the account until 10:15, even for the right password.
    """
    system_settings = SystemSettings.load()
    window_start = timezone.now() - datetime.timedelta(minutes=system_settings.login_lockout_minutes)
    recent = LoginAttempt.objects.filter(timestamp__gte=window_start)

    by_name = recent.filter(identifier=normalise_identifier(identifier))
    last_success = by_name.filter(successful=True).order_by("-timestamp").first()
    failures = by_name.filter(successful=False)
    if last_success is not None:
        failures = failures.filter(timestamp__gt=last_success.timestamp)
    if failures.count() >= system_settings.login_max_attempts:
        return True

    if ip_address:
        ip_failures = recent.filter(ip_address=ip_address, successful=False).count()
        if ip_failures >= system_settings.login_max_attempts * IP_ATTEMPT_FACTOR:
            return True
    return False


def record_login_attempt(identifier: str, ip_address: str | None, *, successful: bool) -> None:
    """Remember a login attempt for :func:`is_locked_out`."""
    LoginAttempt.objects.create(
        identifier=normalise_identifier(identifier),
        ip_address=ip_address or None,
        successful=successful,
    )


def record_security_event(
    kind: str,
    *,
    user: User | None = None,
    identifier: str = "",
    request: Any = None,
    detail: str = "",
) -> None:
    """Write one entry of the security log (AUT-022)."""
    from rentalars.accounts.models import SecurityEvent

    SecurityEvent.objects.create(
        kind=kind,
        user=user if user is not None and user.pk else None,
        identifier=(identifier or (user.username if user is not None else ""))[:254],
        ip_address=client_ip(request) if request is not None else None,
        user_agent=request.headers.get("User-Agent", "")[:300] if request is not None else "",
        detail=str(detail)[:250],
    )


def delete_old_security_events(days: int | None = None) -> int:
    """Remove entries of the security log after the retention period (NFA-011); returns the number removed.

    The period is set in the administration (``retention_security_log_days``, a year unless changed).
    """
    from rentalars.accounts.models import SecurityEvent
    from rentalars.core.models import SystemSettings

    days = days if days is not None else SystemSettings.load().retention_security_log_days
    limit = timezone.now() - datetime.timedelta(days=days)
    deleted, _details = SecurityEvent.objects.filter(timestamp__lt=limit).delete()
    return deleted


def delete_old_login_attempts() -> int:
    """Remove attempts that no longer matter; returns the number deleted."""
    deleted, _details = LoginAttempt.objects.filter(timestamp__lt=timezone.now() - LOGIN_ATTEMPT_RETENTION).delete()
    return deleted


def deactivate_expired_accounts() -> int:
    """Deactivate all accounts whose "valid until" has passed (AUT-024); returns how many."""
    expired = User.objects.filter(is_active=True, valid_until__lt=timezone.localdate())
    return sum(1 for user in expired if user.deactivate_if_expired())


def client_ip(request: Any) -> str | None:
    """Return the address of the browser.

    NGINX sits in front of the application and passes the real address in
    ``X-Forwarded-For``. The header is only trusted in production, where the
    application listens on a local socket that outsiders cannot reach.
    """
    if settings.RENTALARS_ENVIRONMENT == "production":
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[-1].strip() or None
    return request.META.get("REMOTE_ADDR") or None


# --- Users, invitations, roles (AUT-009 to AUT-011) --------------------------


def password_setup_url(user: User) -> str:
    """Build the one-time link with which a user sets a (new) password.

    The link contains a token derived from the user's current password hash
    and last login. It stops working once the password was set, and after
    ``PASSWORD_RESET_TIMEOUT`` at the latest (AUT-004).
    """
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    path = reverse("accounts:password_reset_confirm", kwargs={"uidb64": uid, "token": token})
    return f"{settings.RENTALARS_URL}{path}"


def send_invitation(user: User) -> str:
    """E-mail the invitation link to a new user and return the link (AUT-011); in the user's language (UIX-029)."""
    from rentalars.core.i18n import for_user

    with for_user(user):
        return _send_invitation(user)


def _send_invitation(user: User) -> str:
    if password_is_external(user):
        raise ValidationError(_("The password of this user lives in the directory (LDAP). Rentalars sets none."))
    link = password_setup_url(user)
    company = CompanyProfile.load()
    context = {
        "user": user,
        "link": link,
        "company_name": company.name or "Rentalars",
        "valid_hours": settings.PASSWORD_RESET_TIMEOUT // 3600,
    }
    send_mail(
        subject=_("Your access to Rentalars"),
        message=render_to_string("accounts/email/invitation.txt", context),
        from_email=None,
        recipient_list=[user.email],
        fail_silently=False,
    )
    return link


@transaction.atomic
def invite_user(
    *,
    username: str,
    email: str,
    first_name: str = "",
    last_name: str = "",
    roles: Iterable[Role] = (),
    send_email: bool = True,
    language: str = "",
) -> User:
    """Create a user without a password and send the invitation (AUT-011).

    The new user chooses the password personally through the link in the
    e-mail; an administrator never knows it.

    Raises:
        ValidationError: Username or e-mail address are already in use.
    """
    user = User(
        username=username, email=email or None, first_name=first_name, last_name=last_name, language=language or ""
    )
    user.set_unusable_password()
    user.full_clean()
    user.save()
    set_user_roles(user, roles)
    if send_email and user.email:
        send_invitation(user)
    record_event(user, "user.invited", {"email": user.email})
    return user


def set_user_roles(user: User, roles: Iterable[Role]) -> None:
    """Replace the roles of a user and log the change.

    Many-to-many changes do not pass through ``save()``, so the audit log is
    written here explicitly.
    """
    new_roles = list(roles)
    # AUT-029: the roles the directory gave stay; taking one away by hand is refused.
    given = list(Role.objects.filter(pk__in=_directory_role_ids(user)))
    missing = [role.name for role in given if role not in new_roles]
    if missing:
        raise ValidationError(
            _("The roles %(roles)s come from the directory (LDAP) and cannot be taken away here.")
            % {"roles": ", ".join(sorted(missing))}
        )
    before = sorted(user.roles.values_list("name", flat=True))
    after = sorted(role.name for role in new_roles)
    if before == after:
        return
    user.roles.set(new_roles)
    user._rights_cache = None
    user._roles_cache = None
    record_event(user, "user.roles_changed", {"before": before, "after": after})


def _directory_role_ids(user: User) -> set[int]:
    """The IDs of the roles the directory (LDAP) gave this user (AUT-029)."""
    from rentalars.accounts.models import LdapRoleAssignment

    if not user.pk:
        return set()
    return set(LdapRoleAssignment.objects.filter(user=user).values_list("role_id", flat=True))


def password_is_external(user: User) -> bool:
    """Whether the password of this account lives in the directory, so that Rentalars sets none (AUT-029).

    True for an account the directory keeps – but only while the directory is switched on. Once
    it is switched off, nobody asks it any more; an account without a password of its own can then be given one
    by the usual invitation (or a one-time password), so that it is not stranded.
    """
    from rentalars.accounts.models import LdapSettings

    if not user.is_directory_account:
        return False
    return LdapSettings.current().is_ready


def check_may_deactivate(user: User, *, acting_user: User | None = None) -> None:
    """Refuse to deactivate one's own account or the last one with access to the settings (AUT-009).

    Raises:
        ValidationError: One of the two.
    """
    if acting_user is not None and acting_user.pk == user.pk:
        raise ValidationError(_("You cannot deactivate your own account."))
    if _is_last_administrator(user):
        raise ValidationError(_("The last account with access to the settings cannot be deactivated."))


def set_user_active(user: User, *, active: bool, acting_user: User | None = None) -> None:
    """Activate or deactivate a user (AUT-009).

    Deactivating keeps all data and history but ends the ability to log in.
    API tokens stop working at once because they check ``user.is_active``.

    Raises:
        ValidationError: A user tried to deactivate the own account, or the
            last account with access to the administration would be lost.
    """
    if not active:
        check_may_deactivate(user, acting_user=acting_user)
    if user.is_active != active:
        user.is_active = active
        if active:
            user.ldap_deactivated_at = None  # AUT-029: an administrator decides now, not the directory
        user.save()


@transaction.atomic
def anonymise_user(user: User) -> None:
    """Erase what identifies the holder of an account, and close the account (NFA-009).

    Accounts are never deleted (AUT-009): the change log refers to them.
    What can go is everything that says *who* it was:

    * user name, e-mail address and names are overwritten ("anonym-17"),
    * the password is removed, the roles are taken away, API tokens revoked,
    * recorded login attempts under the old name are deleted,
    * the change log keeps *that* somebody did something, under the new name,
      and loses the logged values of the account itself.

    Called when the person an account belongs to is anonymised
    (``personnel.privacy.anonymise_person``).
    """
    from django.contrib.contenttypes.models import ContentType

    from rentalars.core.audit import AuditedModel
    from rentalars.core.models import AuditLogEntry

    replacement = f"anonym-{user.pk}"
    identifiers = [user.username.lower(), *([user.email.lower()] if user.email else [])]
    LoginAttempt.objects.filter(identifier__in=identifiers).delete()
    for token in user.api_tokens.all():
        token.revoke()
    user.roles.clear()
    user.ldap_role_assignments.all().delete()  # AUT-029: no link to the directory is kept
    user.ldap_dn = ""
    user.ldap_synced_at = None
    user.ldap_deactivated_at = None
    user.username = replacement
    user.email = f"{replacement}@example.invalid"
    user.first_name = ""
    user.last_name = ""
    user.is_active = False
    user.valid_until = None
    user.set_unusable_password()
    # Saved without the field-by-field log, which would repeat what is being erased.
    super(AuditedModel, user).save()
    user._audit_snapshot = user._audit_values()
    user._audit_loaded = None

    user_type = ContentType.objects.get_for_model(User)
    AuditLogEntry.objects.filter(content_type=user_type, object_id=str(user.pk)).update(
        changes={}, object_repr=replacement
    )
    AuditLogEntry.objects.filter(actor=user).update(actor_label=replacement)
    record_event(user, "user.anonymised")


def _is_last_administrator(user: User) -> bool:
    """Whether ``user`` is the only active account that can manage users."""
    from rentalars.accounts.rights import Module

    if not user.rights.can_write(Module.ADMINISTRATION):
        return False
    for other in User.objects.filter(is_active=True).exclude(pk=user.pk).prefetch_related("roles"):
        if other.rights.can_write(Module.ADMINISTRATION):
            return False
    return True


# --- One-time passwords (AUT-027) ---------------------------------------------


def one_time_password() -> str:
    """A password that is easy to read out and type: four groups of letters and digits."""
    import secrets as _secrets

    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return "-".join("".join(_secrets.choice(alphabet) for _ in range(4)) for _ in range(4))


def set_one_time_password(user: User, *, acting_user: User | None = None) -> str:
    """Give an account a password for its next login only (AUT-027).

    For the emergency – the mail with the link does not arrive, or the person
    has no e-mail address. The administrator hands the password over; at the
    next login the user must choose an own one before anything else.

    Returns:
        The password, to be shown once to the administrator.

    Raises:
        ValidationError: The account is deactivated.
    """
    if not user.is_active:
        raise ValidationError(_("This user is deactivated and cannot log in."))
    if password_is_external(user):
        raise ValidationError(_("The password of this user lives in the directory (LDAP). Rentalars sets none."))
    replaced = user.has_usable_password()  # AUT-030: for an account that never had a password, no notice
    password = one_time_password()
    user.set_password(password)
    user.must_change_password = True
    user.save()
    record_event(user, "user.one_time_password", {"by": str(acting_user) if acting_user else ""})
    record_security_event("one_time_password", user=user, detail=str(acting_user or ""))
    if replaced:
        from rentalars.accounts import notices

        notices.credentials_changed(user, notices.ONE_TIME_PASSWORD, by=acting_user)
    return password
