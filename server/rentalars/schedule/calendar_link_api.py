# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the calendar links of products, material models and items (VFG-040; API-002).

* ``GET /products/{id}/calendar-link`` – the link: ``active``, ``url`` (the
  address for calendar programs, works without login – only for whoever may
  change the link, ``null`` for readers), when and by whom it
  was created, and what the calendar ``shows``;
* ``POST`` – create the link, or a new one: the old address stops working at
  once (``201`` for a new link, ``200`` for a renewed one);
* ``DELETE`` – deactivate it: the address stops working at once (``204``).

The same for ``/material-models/{id}/calendar-link`` and
``/material-items/{id}/calendar-link``. Reading needs read access to the
module of the record (products, or material), the other two – and the
``url`` of a reading – write access; all three also the special right to see
the availability of material and the right to read every project
(``calendar_links.may_see``, ``calendar_links.may_manage``).
"""

from __future__ import annotations

from typing import Any, ClassVar

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Level, Module, require
from rentalars.api.views import ModuleAPIView
from rentalars.schedule import calendar_links
from rentalars.schedule.models import CalendarLink

_LINK = inline_serializer(
    "CalendarLink",
    {
        "active": serializers.BooleanField(),
        "url": serializers.CharField(
            allow_null=True,
            help_text="The address for calendar programs; null without a link, and for whoever may not change it.",
        ),
        "created_at": serializers.DateTimeField(allow_null=True),
        "created_by": serializers.CharField(allow_null=True),
        "shows": serializers.CharField(),
    },
)


def link_document(kind: str, link: CalendarLink | None, *, with_url: bool) -> dict[str, Any]:
    """The calendar link of a record as the API answers it; never the token alone.

    ``with_url``: whether the caller may change the link and so see its address (``calendar_links.may_manage``);
    a reader learns that a link is active, not its address (VFG-040).
    """
    return {
        "active": link is not None,
        "url": calendar_links.feed_url(link) if link is not None and with_url else None,
        "created_at": link.created_at if link is not None else None,
        "created_by": str(link.created_by) if link is not None and link.created_by_id else None,
        "shows": calendar_links.shows(kind),
    }


class _CalendarLinkView(ModuleAPIView):
    """The calendar link of one record; the subclasses name the kind and its module."""

    kind: ClassVar[str] = ""
    #: The module level is checked here, method by method: read for GET, write for POST and DELETE.
    action_levels: ClassVar[dict[Any, int]] = {None: Level.READ}

    def _subject(self, *, manage: bool) -> Any:
        """The record, once the rights to see (or to change) its link are checked."""
        rights = self.rights
        require(calendar_links.may_manage(rights, self.kind) if manage else calendar_links.may_see(rights, self.kind))
        return calendar_links.subject_for(self.kind, self.kwargs["pk"])

    @extend_schema(responses=_LINK)
    def get(self, request: Request, pk: int) -> Response:
        """The calendar link of the record: whether one is active, its address (to who may change it), what it shows."""
        subject = self._subject(manage=False)
        with_url = calendar_links.may_manage(self.rights, self.kind)
        return Response(link_document(self.kind, calendar_links.link_of(subject), with_url=with_url))

    @extend_schema(request=None, responses={200: _LINK, 201: _LINK})
    def post(self, request: Request, pk: int) -> Response:
        """Create the calendar link, or a new one; the old address stops working at once."""
        subject = self._subject(manage=True)
        link, renewed = calendar_links.create_link(subject, user=request.user)
        return Response(
            link_document(self.kind, link, with_url=True),
            status=status.HTTP_200_OK if renewed else status.HTTP_201_CREATED,
        )

    @extend_schema(responses={204: None})
    def delete(self, request: Request, pk: int) -> Response:
        """Deactivate the calendar link; its address stops working at once. Without a link nothing happens."""
        calendar_links.deactivate_link(self._subject(manage=True))
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProductCalendarLinkView(_CalendarLinkView):
    """``/products/{id}/calendar-link`` (VFG-040)."""

    module = Module.PRODUCTS
    kind = calendar_links.PRODUCT


class ModelCalendarLinkView(_CalendarLinkView):
    """``/material-models/{id}/calendar-link`` (VFG-040)."""

    module = Module.MATERIAL
    kind = calendar_links.MODEL


class ItemCalendarLinkView(_CalendarLinkView):
    """``/material-items/{id}/calendar-link`` (VFG-040)."""

    module = Module.MATERIAL
    kind = calendar_links.ITEM
