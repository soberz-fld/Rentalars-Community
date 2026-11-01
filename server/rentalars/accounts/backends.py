# SPDX-License-Identifier: GPL-3.0-or-later
"""Login with either the e-mail address or the username (AUT-002)."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.backends import BaseBackend
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q, Subquery
from django.http import HttpRequest

from rentalars.accounts.models import User


def _local_passwords_off() -> bool:
    """Whether the directory is on and "allow login with a local password" is off (AUT-029)."""
    from rentalars.accounts.models import LdapSettings

    settings = LdapSettings.current()
    return bool(settings.enabled and not settings.allow_local_login)


class EmailOrUsernameBackend(BaseBackend):
    """Checks a name-and-password pair against the user table.

    The name may be the username or the e-mail address; upper and lower case
    do not matter. Deactivated users are rejected (AUT-009), and so are
    accounts whose time is up (AUT-024).
    """

    def authenticate(
        self,
        request: HttpRequest | None,
        username: str | None = None,
        password: str | None = None,
        **kwargs: Any,
    ) -> User | None:
        """Return the user if name and password match, otherwise ``None``."""
        if not username or password is None:
            return None
        identifier = username.strip()
        user = User.objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier)).first()
        if user is None:
            # Hash the password anyway. Otherwise the faster answer would tell
            # an attacker that the name does not exist.
            User().set_password(password)
            return None
        # AUT-029: with the directory switched on and local passwords off, only local (emergency)
        # accounts log in with a password of Rentalars.
        if not user.local_account and _local_passwords_off():
            user.check_password(password)  # same time as for a wrong password
            return None
        if user.check_password(password) and not user.deactivate_if_expired():
            return user
        return None

    def get_user(self, user_id: int) -> User | None:
        """Load the user of a session; deactivated users lose their session.

        The person of the account comes along in the same query: nearly
        every page asks for it (``projects.access.person_of``) – the
        navigation shows "My area" only to accounts that are a person.
        So does the company name, which the menu of every page shows
        (UIX-032): always the current one, and without a query of its own.
        """
        from rentalars.core.models import CompanyProfile

        user = (
            User.objects.select_related("person")
            .annotate(menu_company_name=Subquery(CompanyProfile.objects.filter(pk=1).values("name")[:1]))
            .filter(pk=user_id)
            .first()
        )
        if user is None or user.deactivate_if_expired():
            return None
        try:
            user._person_cache = user.person
        except ObjectDoesNotExist:
            user._person_cache = None
        return user
