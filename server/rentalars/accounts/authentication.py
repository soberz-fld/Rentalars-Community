# SPDX-License-Identifier: GPL-3.0-or-later
"""Token authentication for the API (API-006, AUT-021)."""

from __future__ import annotations

import datetime

from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from rest_framework import authentication, exceptions
from rest_framework.request import Request

from rentalars.accounts.models import ApiToken, User
from rentalars.core.audit import set_current_actor
from rentalars.core.i18n import api_language
from rentalars.gateway_link import binding as gateway_binding

#: ``last_used_at`` is refreshed at most this often to avoid a write per request.
LAST_USED_RESOLUTION = datetime.timedelta(minutes=1)


class ApiTokenAuthentication(authentication.BaseAuthentication):
    """Accepts ``Authorization: Bearer rl_…`` (or ``Token rl_…``).

    On success ``request.user`` is the owner of the token and ``request.auth``
    is the token itself. The rights check later narrows the user's rights to
    what the token allows (see ``rights.request_rights``).
    """

    keywords = ("bearer", "token")

    def authenticate(self, request: Request) -> tuple[User, ApiToken] | None:
        """Return user and token, ``None`` if no token was sent, or raise if it is invalid."""
        header = authentication.get_authorization_header(request).decode("latin-1")
        parts = header.split()
        if len(parts) != 2 or parts[0].lower() not in self.keywords:
            return None

        token = (
            ApiToken.objects.select_related("user", "gateway_binding__device")
            .filter(key_hash=ApiToken.hash_key(parts[1]))
            .first()
        )
        if token is None or not token.is_usable:
            raise exceptions.AuthenticationFailed(_("The API token is invalid, expired or revoked."))
        # GWS-041: a token that was issued through a device of the gateway works only through that device.
        if not gateway_binding.check_token(request, token):
            raise exceptions.AuthenticationFailed(_("The API token is invalid, expired or revoked."))

        now = timezone.now()
        if token.last_used_at is None or now - token.last_used_at > LAST_USED_RESOLUTION:
            ApiToken.objects.filter(pk=token.pk).update(last_used_at=now)

        # Changes made through the API are attributed to the token's owner.
        set_current_actor(token.user)
        # UIX-029: messages and errors in the owner's language, else in the one the client asks for.
        translation.activate(api_language(token.user, request))
        return token.user, token

    def authenticate_header(self, request: Request) -> str:
        """Tell clients which scheme to use; makes failures answer with 401 instead of 403."""
        return "Bearer"
