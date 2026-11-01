# SPDX-License-Identifier: GPL-3.0-or-later
"""Rights checks of the API – the same rights as in the browser (AUT-020, API-006)."""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request

from rentalars.accounts.rights import Level, Module, request_rights

#: Marker for views that only need a login, e.g. "my own tokens".
AUTHENTICATED_ONLY = "authenticated-only"


def level_for_method(method: str) -> int:
    """Map an HTTP method to the module level it needs (AUT-015).

    Reading needs "read", deleting needs "delete", everything else "write".
    """
    if method in SAFE_METHODS:
        return Level.READ
    if method == "DELETE":
        return Level.DELETE
    return Level.WRITE


READ_ONLY_MESSAGE = _("This token is read-only. It changes nothing.")


def is_read_only_token(request: Request) -> bool:
    """Whether the call is made with a read-only API token (AUT-021)."""
    return bool(getattr(getattr(request, "auth", None), "read_only", False))


class WritableCaller(BasePermission):
    """Refuses changing calls (everything but GET/HEAD/OPTIONS) made with a read-only token.

    Views that only need a login (``IsAuthenticated`` or :data:`AUTHENTICATED_ONLY`) do not look at the module
    levels, which are what narrows a read-only token (security fix, S9). Without this class such a token
    could still revoke tokens and sessions or change the notification settings of its user.
    """

    message = READ_ONLY_MESSAGE

    def has_permission(self, request: Request, view: Any) -> bool:
        """Allow reading; allow changing only if the token is not read-only."""
        return request.method in SAFE_METHODS or not is_read_only_token(request)


class ModulePermission(BasePermission):
    """Allows a request if the caller has the needed level in the view's module.

    A view declares its module::

        class ProductViewSet(ModuleViewSet):
            module = Module.PRODUCTS

    Optional view attributes refine the check:

    ``action_levels``
        ``{"anonymise": Level.DELETE}`` – a level for a named action that
        differs from the HTTP method's default.
    ``read_for_all``
        ``True`` lets every logged-in user read (used for master data that
        every form needs, such as units), while writing still needs the
        module level.
    ``alternative_modules``
        Further modules whose level is accepted as well. Example: suppliers
        belong to the master data, but warehouse staff with write access to
        Material may maintain them too.

    A view without ``module`` is refused: forgetting the declaration must
    not open an endpoint.
    """

    def has_permission(self, request: Request, view: Any) -> bool:
        """Check login and module level."""
        if not request.user or not request.user.is_authenticated:
            return False
        module = getattr(view, "module", None)
        if module is None:
            return False
        if module == AUTHENTICATED_ONLY:
            if request.method not in SAFE_METHODS and is_read_only_token(request):
                self.message = READ_ONLY_MESSAGE
                return False
            return True
        rights = request_rights(request)
        if request.method in SAFE_METHODS and getattr(view, "read_for_all", False):
            return True
        action = getattr(view, "action", None)
        needed = getattr(view, "action_levels", {}).get(action, level_for_method(request.method or "GET"))
        if rights.has_level(module, needed):
            return True
        return any(rights.has_level(other, needed) for other in getattr(view, "alternative_modules", ()))


__all__ = [
    "AUTHENTICATED_ONLY",
    "Level",
    "Module",
    "ModulePermission",
    "WritableCaller",
    "is_read_only_token",
    "level_for_method",
]
