# SPDX-License-Identifier: GPL-3.0-or-later
"""Login with LDAP or Active Directory as a second authentication backend (AUT-029).

Django asks the backends one after the other (``AUTHENTICATION_BACKENDS``): first the local one
(``EmailOrUsernameBackend``), then this one. So the pages of the login, the second factor (AUT-006), the
protection against guessing (AUT-005) and the security log (AUT-022) stay exactly as they are – the
login only has one more way to say yes. After the directory has said yes, a user with two-factor login
is asked for the code like any other.

The backend answers ``None`` – "not me" – whenever it is switched off, the name is unusable, the account is
a local (emergency) account or has all rights (the directory is asked a dummy question then, to take as long as
for any name), or the directory says no. It leaves a note on the request when the directory
could not be reached (``directory_unavailable``), so that the page can say so.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.backends import BaseBackend
from django.http import HttpRequest

from rentalars.accounts import ldap_sync
from rentalars.accounts.models import LdapSettings, User


class LdapBackend(BaseBackend):
    """Checks a name and password against the directory and keeps the account and its roles in step."""

    def authenticate(
        self,
        request: HttpRequest | None,
        username: str | None = None,
        password: str | None = None,
        **kwargs: Any,
    ) -> User | None:
        """Return the user if the directory accepts name and password and the user may work, else ``None``."""
        if not username or not password:
            return None
        settings = LdapSettings.current()
        if not settings.is_ready:
            return None
        name = username.strip()
        # A local (emergency) account and an account with "has all rights" log in with their own password
        # only: the directory does not decide on them. It is still asked a question and a bind is tried, so that
        # the answer takes as long as for any other name (review: no timing hint for such accounts).
        account = User.objects.filter(username__iexact=name).first()
        if account is not None and (account.local_account or account.is_superuser):
            ldap_sync.equalise_cost(settings, name, password)
            return None
        result = ldap_sync.sign_in(settings, name, password, request=request)
        if request is not None and result.unavailable:
            request.directory_unavailable = True  # type: ignore[attr-defined]
        user = result.user
        if user is None or user.deactivate_if_expired():
            return None
        return user

    def get_user(self, user_id: int) -> User | None:
        """Load the user of a session that was started by this backend: like the local backend does."""
        from rentalars.accounts.backends import EmailOrUsernameBackend

        return EmailOrUsernameBackend().get_user(user_id)
