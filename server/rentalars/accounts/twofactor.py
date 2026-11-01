# SPDX-License-Identifier: GPL-3.0-or-later
"""Two-factor login with an authenticator app (AUT-006, NFA-049).

After the password, the user types the six-digit code their app shows – any
app for "TOTP" (RFC 6238) works: FreeOTP, Aegis, Google or Microsoft
Authenticator, a password manager. The app and Rentalars share a random key,
set up once by scanning a QR code; from it both compute a new code every 30
seconds. Nothing leaves the server for that, no text message is sent.

Rules:

* Each user may switch it on for themselves. A role can require it
  (``Role.requires_two_factor``), and a system setting requires it for
  everybody with rights on the administration (NFA-049). Whoever must have
  it and has not set it up yet can do nothing but set it up.
* A code is accepted from the previous, the current and the next 30-second
  step (clocks differ a little) – and each code only once.
* Ten recovery codes are shown once when it is set up, for a lost phone.
  Each works once. They are stored as hashes only.
* An administrator can switch it off for a user who lost phone and codes;
  the user then sets it up again.

The shared key is stored encrypted (``core.crypto``).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from rentalars.accounts.rights import Level, Module
from rentalars.core.crypto import decrypt_secret, encrypt_secret

if TYPE_CHECKING:
    from rentalars.accounts.models import User

#: Seconds per code (RFC 6238 default; every app uses it).
STEP_SECONDS = 30
DIGITS = 6
#: Steps before and after the current one that are accepted.
TOLERANCE_STEPS = 1
RECOVERY_CODE_COUNT = 10


# --- The algorithm (RFC 4226 and RFC 6238) ------------------------------------------------


def new_secret() -> str:
    """A new shared key: 160 random bits in Base32, as the apps expect it."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _key_bytes(secret: str) -> bytes:
    padded = secret.upper() + "=" * (-len(secret) % 8)
    return base64.b32decode(padded)


def code_at(secret: str, step: int) -> str:
    """The code of one 30-second step (HOTP with SHA-1, as all apps compute it)."""
    digest = hmac.new(_key_bytes(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10**DIGITS).zfill(DIGITS)


def current_step(now: float | None = None) -> int:
    """The number of the current 30-second step."""
    return int((time.time() if now is None else now) // STEP_SECONDS)


def matching_step(secret: str, code: str, *, now: float | None = None) -> int | None:
    """The step a code belongs to, if it is one of the accepted steps."""
    code = "".join(character for character in code if character.isdigit())
    if len(code) != DIGITS:
        return None
    step = current_step(now)
    for candidate in range(step - TOLERANCE_STEPS, step + TOLERANCE_STEPS + 1):
        if hmac.compare_digest(code_at(secret, candidate), code):
            return candidate
    return None


def provisioning_uri(secret: str, account: str, issuer: str) -> str:
    """The address the QR code holds: ``otpauth://totp/…``."""
    label = quote(f"{issuer}:{account}")
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}"
        f"&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}"
    )


def qr_code_svg(uri: str) -> str:
    """The QR code of an address as inline SVG – made here, not by a service on the internet (NFA-050)."""
    import segno

    return str(segno.make(uri, error="m").svg_inline(scale=5, border=2, dark="#000000", light="#ffffff"))


# --- Recovery codes ------------------------------------------------------------------------------


def _hash_recovery_code(code: str) -> str:
    normalized = "".join(character for character in code.lower() if character.isalnum())
    return hashlib.sha256(normalized.encode("ascii", "ignore")).hexdigest()


def new_recovery_codes() -> list[str]:
    """Ten codes like ``k4m9-x2pq``: easy to write down, one use each."""
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    codes = []
    for _index in range(RECOVERY_CODE_COUNT):
        raw = "".join(secrets.choice(alphabet) for _position in range(8))
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes


# --- Per user ------------------------------------------------------------------------------------------


def roles_of(user: User) -> list[Any]:
    """The roles of a user, read once per request (``rights_of`` uses the same list)."""
    cached = getattr(user, "_roles_cache", None)
    if cached is None:
        cached = list(user.roles.all())
        user._roles_cache = cached  # type: ignore[attr-defined]
    return cached


def two_factor_required(user: User) -> bool:
    """Whether a role, or the setting for administrators, requires a second factor for this user."""
    from rentalars.core.models import SystemSettings

    if any(role.requires_two_factor for role in roles_of(user)):
        return True
    if SystemSettings.load().two_factor_for_administrators:
        return bool(user.is_superuser or user.rights.has_level(Module.ADMINISTRATION, Level.WRITE))
    return False


def secret_of(user: User) -> str:
    """The shared key of a user (empty without two-factor login)."""
    return decrypt_secret(user.totp_secret_encrypted)


@transaction.atomic
def verify_code(user: User, code: str) -> bool:
    """Check a code of the app – or a recovery code – and use it up.

    A code from the app is accepted only once: a step that was used before
    (or an earlier one) is refused, so that a code seen over somebody's
    shoulder cannot be used again.
    """
    from rentalars.accounts.models import SecurityEventKind, User
    from rentalars.accounts.services import record_security_event

    locked = User.objects.select_for_update().get(pk=user.pk)
    if not locked.has_two_factor:
        return False
    step = matching_step(secret_of(locked), code)
    if step is not None and step > locked.totp_last_step:
        locked.totp_last_step = step
        locked.save(update_fields=["totp_last_step"])
        user.totp_last_step = step
        return True
    hashed = _hash_recovery_code(code)
    if hashed in (locked.recovery_code_hashes or []):
        locked.recovery_code_hashes = [value for value in locked.recovery_code_hashes if value != hashed]
        locked.save(update_fields=["recovery_code_hashes"])
        user.recovery_code_hashes = locked.recovery_code_hashes
        record_security_event(
            SecurityEventKind.RECOVERY_CODE_USED,
            user=locked,
            detail=ngettext(
                "%(count)d recovery code left", "%(count)d recovery codes left", len(locked.recovery_code_hashes)
            )
            % {"count": len(locked.recovery_code_hashes)},
        )
        return True
    return False


def enable(user: User, secret: str, code: str) -> list[str]:
    """Switch two-factor login on, after the user proved that the app has the key.

    Returns:
        The recovery codes, to be shown exactly once.

    Raises:
        ValidationError: The code does not match the key.
    """
    from rentalars.accounts.models import SecurityEventKind
    from rentalars.accounts.services import record_security_event
    from rentalars.core.audit import record_event

    step = matching_step(secret, code)
    if step is None:
        raise ValidationError(_("The code does not match. Check that the clock of the phone is right and try again."))
    codes = new_recovery_codes()
    user.totp_secret_encrypted = encrypt_secret(secret)
    user.totp_enabled_at = timezone.now()
    user.totp_last_step = step
    user.recovery_code_hashes = [_hash_recovery_code(code) for code in codes]
    user.save()
    record_security_event(SecurityEventKind.SECOND_FACTOR_ENABLED, user=user)
    record_event(user, "user.two_factor_enabled", {})
    return codes


def disable(user: User, *, by: User | None = None) -> None:
    """Switch two-factor login off – by the user, or by an administrator for a lost phone."""
    from rentalars.accounts.models import SecurityEventKind
    from rentalars.accounts.services import record_security_event
    from rentalars.core.audit import record_event

    user.totp_secret_encrypted = ""
    user.totp_enabled_at = None
    user.totp_last_step = 0
    user.recovery_code_hashes = []
    user.save()
    detail = "" if by is None or by.pk == user.pk else _("by %(name)s") % {"name": by}
    record_security_event(SecurityEventKind.SECOND_FACTOR_DISABLED, user=user, detail=detail)
    record_event(user, "user.two_factor_disabled", {"by": str(by) if by else ""})


# --- During login ---------------------------------------------------------------------------------------

#: The session key under which the half-finished login waits for the code.
PENDING_SESSION_KEY = "rentalars_pending_login"
#: How long the code may take after the password, in seconds.
PENDING_SECONDS = 300
#: Wrong codes in a row before the password has to be entered again.
MAX_CODE_ATTEMPTS = 5


def remember_pending_login(request: HttpRequest, user: User, next_url: str, identifier: str = "") -> None:
    """The password was right; the code is still missing. Nobody is logged in yet.

    ``identifier`` is the name as it was typed (it can be the e-mail address): failed passwords were counted under it,
    so the success is noted under it as well.
    """
    request.session[PENDING_SESSION_KEY] = {
        "identifier": identifier,
        "user": user.pk,
        "since": time.time(),
        "next": next_url,
        "attempts": 0,
        "backend": getattr(user, "backend", "rentalars.accounts.backends.EmailOrUsernameBackend"),
    }


def pending_login(request: HttpRequest) -> dict[str, Any] | None:
    """The half-finished login of this browser, if it is still fresh."""
    pending = request.session.get(PENDING_SESSION_KEY)
    if not pending or time.time() - pending.get("since", 0) > PENDING_SECONDS:
        return None
    return dict(pending)


def forget_pending_login(request: HttpRequest) -> None:
    """End a half-finished login."""
    request.session.pop(PENDING_SESSION_KEY, None)


# --- Making it a requirement --------------------------------------------------------------------------------

#: Paths that stay open for a user who must set up the second factor first.
_OPEN_PREFIXES = ("/account/two-factor/", "/logout/", "/static/", "/api/", "/login/", "/favicon.ico")


#: Paths that stay open for a user who must choose a new password first.
_OPEN_FOR_NEW_PASSWORD = ("/account/new-password/", "/logout/", "/static/", "/login/", "/favicon.ico")


class PasswordChangeRequiredMiddleware:
    """After a one-time password, every page leads to choosing an own password (AUT-027)."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Let the request through, or redirect it to the page for the new password."""
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and user.must_change_password
            and not request.path.startswith(_OPEN_FOR_NEW_PASSWORD)
        ):
            if request.path.startswith("/api/"):
                # The uniform error format of the API (API-008).
                message = _("Choose a new password in the browser first.")
                return JsonResponse(
                    {"error": {"code": "password_change_required", "message": str(message), "fields": {}}},
                    status=403,
                )
            return redirect("accounts:new_password")
        return self.get_response(request)


class TwoFactorRequiredMiddleware:
    """Send users who must use a second factor, but have not set it up, to the setup page (AUT-006)."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Let the request through, or redirect it to the setup of the second factor."""
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and not user.has_two_factor
            and not request.path.startswith(_OPEN_PREFIXES)
            and required_for_session(request, user)
        ):
            return redirect("accounts:two_factor_setup")
        return self.get_response(request)


#: The answer "must this user use a second factor?" is kept in the session this long.
REQUIREMENT_RECHECK_SECONDS = 600
_REQUIREMENT_KEY = "rentalars_2fa_required"


def required_for_session(request: HttpRequest, user: Any) -> bool:
    """Whether the user must use a second factor – checked at login and then every ten minutes.

    Every page asks; looking at the roles each time would cost a query per
    page. A role that newly requires the second factor takes effect within
    ten minutes, or at the next login.
    """
    cached = request.session.get(_REQUIREMENT_KEY)
    if cached and time.time() - cached[1] < REQUIREMENT_RECHECK_SECONDS:
        return bool(cached[0])
    required = bool(user.needs_two_factor)
    request.session[_REQUIREMENT_KEY] = (required, time.time())
    return required
