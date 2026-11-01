# SPDX-License-Identifier: GPL-3.0-or-later
"""Sessions of the users: ending after inactivity, showing and ending them (AUT-008).

* After the time set in the system settings without any request, a session
  ends; the next page shows the login with a note why (AUT-008).
* Every login is noted as a :class:`~rentalars.accounts.models.UserSession`
  with browser and address. On "My account" users see where they are logged
  in and can end any of those sessions – the browser there is logged out at
  its next request.

The time of the last activity is written at most once a minute, so that not
every click costs a write to the database.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable
from typing import Any

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.sessions.models import Session
from django.dispatch import receiver
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

#: How often the last activity is written, at most.
ACTIVITY_WRITE_INTERVAL = datetime.timedelta(minutes=1)
_ACTIVITY_KEY = "rentalars_last_activity"


def _client_ip(request: HttpRequest) -> str | None:
    from rentalars.accounts.services import client_ip

    return client_ip(request)


@receiver(user_logged_in)
def note_login(sender: Any, request: HttpRequest | None, user: Any, **kwargs: Any) -> None:
    """Note the new session and log the login (AUT-008, AUT-022)."""
    from rentalars.accounts.models import SecurityEventKind, UserSession
    from rentalars.accounts.services import record_security_event

    if request is None:
        return
    if not request.session.session_key:
        request.session.save()
    UserSession.objects.update_or_create(
        session_key=request.session.session_key,
        defaults={
            "user": user,
            "created_at": timezone.now(),
            "last_activity": timezone.now(),
            "ip_address": _client_ip(request),
            "user_agent": request.headers.get("User-Agent", "")[:300],
        },
    )
    request.session[_ACTIVITY_KEY] = timezone.now().timestamp()
    # AUT-006: whether a second factor is required is decided at login and kept for a while.
    from rentalars.accounts.twofactor import required_for_session

    if not user.has_two_factor:
        required_for_session(request, user)
    record_security_event(SecurityEventKind.LOGIN, user=user, request=request)


@receiver(user_logged_out)
def note_logout(sender: Any, request: HttpRequest | None, user: Any, **kwargs: Any) -> None:
    """Remove the noted session and log the logout."""
    from rentalars.accounts.models import SecurityEventKind, UserSession
    from rentalars.accounts.services import record_security_event

    if request is None:
        return
    if request.session.session_key:
        UserSession.objects.filter(session_key=request.session.session_key).delete()
    if user is not None and not getattr(request, "_rentalars_timeout", False):
        record_security_event(SecurityEventKind.LOGOUT, user=user, request=request)


def end_session(user_session: Any, *, by: Any = None) -> None:
    """End a session from elsewhere: the browser is logged out at its next request (AUT-008)."""
    from rentalars.accounts.models import SecurityEventKind
    from rentalars.accounts.services import record_security_event

    Session.objects.filter(session_key=user_session.session_key).delete()
    record_security_event(
        SecurityEventKind.SESSION_ENDED,
        user=user_session.user,
        detail=f"{user_session.ip_address or ''} {user_session.user_agent[:120]}".strip(),
    )
    user_session.delete()


def idle_limit() -> datetime.timedelta:
    """The time without activity after which a session ends (system setting)."""
    from rentalars.core.models import SystemSettings

    return datetime.timedelta(minutes=SystemSettings.load().session_idle_minutes)


class SessionActivityMiddleware:
    """End idle sessions and keep the time of the last activity (AUT-008)."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Log out an idle session; note the activity of an active one."""
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and hasattr(request, "session"):
            now = timezone.now()
            last = request.session.get(_ACTIVITY_KEY)
            if last is not None and now - datetime.datetime.fromtimestamp(last, tz=datetime.UTC) > idle_limit():
                return self._time_out(request, user)
            if last is None or now - datetime.datetime.fromtimestamp(last, tz=datetime.UTC) > ACTIVITY_WRITE_INTERVAL:
                request.session[_ACTIVITY_KEY] = now.timestamp()
                if request.session.session_key:
                    from rentalars.accounts.models import UserSession

                    UserSession.objects.filter(session_key=request.session.session_key).update(last_activity=now)
        return self.get_response(request)

    def _time_out(self, request: HttpRequest, user: Any) -> HttpResponse:
        from rentalars.accounts.models import SecurityEventKind
        from rentalars.accounts.services import record_security_event

        record_security_event(SecurityEventKind.TIMEOUT, user=user, request=request)
        request._rentalars_timeout = True  # type: ignore[attr-defined]
        logout(request)
        if request.path.startswith("/api/"):
            return self.get_response(request)
        messages.info(request, _("You were logged out after a time without activity. Please log in again."))
        return redirect(f"{reverse('accounts:login')}?next={request.path}")
