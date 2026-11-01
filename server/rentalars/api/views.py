# SPDX-License-Identifier: GPL-3.0-or-later
"""Base classes for the API views of all modules."""

from __future__ import annotations

from typing import Any, ClassVar

from django.utils.translation import gettext as _
from rest_framework import mixins, viewsets
from rest_framework.exceptions import ParseError
from rest_framework.request import Request
from rest_framework.views import APIView

from rentalars.accounts.rights import Rights, request_rights
from rentalars.api.permissions import ModulePermission


class RightsViewMixin:
    """Gives a view access to the rights of the caller."""

    request: Any

    @property
    def rights(self) -> Rights:
        """The rights of the current request (token restrictions applied)."""
        return request_rights(self.request)


class ModuleViewSet(RightsViewMixin, viewsets.ModelViewSet):
    """A resource with the usual operations: list, read, create, change, delete.

    Subclasses set ``module``; :class:`ModulePermission` then requires read
    access for GET, write access for POST/PUT/PATCH and delete access for
    DELETE (AUT-015).
    """

    module: ClassVar[str | None] = None
    permission_classes: ClassVar[list[Any]] = [ModulePermission]


class ModuleReadOnlyViewSet(RightsViewMixin, viewsets.ReadOnlyModelViewSet):
    """A resource that can only be listed and read."""

    module: ClassVar[str | None] = None
    permission_classes: ClassVar[list[Any]] = [ModulePermission]


class NoDeleteViewSet(
    RightsViewMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """A resource whose records are deactivated, never deleted (AUT-009, MAT-022)."""

    module: ClassVar[str | None] = None
    permission_classes: ClassVar[list[Any]] = [ModulePermission]


class ModuleAPIView(RightsViewMixin, APIView):
    """A single endpoint that is not a list of records, e.g. an availability query."""

    module: ClassVar[str | None] = None
    permission_classes: ClassVar[list[Any]] = [ModulePermission]


def body_of(request: Request) -> dict[str, Any]:
    """Return the body of a request as a mapping of field names to values.

    Every endpoint that reads single values expects a JSON *object* (or form
    fields). A client that sends something else – a list, a bare number –
    gets a clear "malformed request" instead of an internal error.

    Raises:
        ParseError: The body is not an object.
    """
    data = request.data
    if not hasattr(data, "get"):
        raise ParseError(_("The request body must be a JSON object."))
    return data  # type: ignore[return-value]
