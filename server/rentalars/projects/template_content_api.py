# SPDX-License-Identifier: GPL-3.0-or-later
"""API for the content of a project template (PRJ-136).

A mixin of ``ProjectTemplateViewSet``; the work is done by ``projects.template_content``, the same code the pages use.

* ``GET|PUT /project-templates/{id}/content`` – read the content, or replace all of it;
* ``PUT /project-templates/{id}/content/notes`` – the notes and the default rental days;
* ``POST /project-templates/{id}/content/{section}`` – add an entry (answer: its ``key``);
* ``PATCH|DELETE /project-templates/{id}/content/{section}/{key}`` – change (only the fields sent) or delete an entry;
* ``POST /project-templates/{id}/content/{section}/{key}/move`` – one place up or down.

``section`` is ``groups``, ``lines``, ``crew``, ``vehicles``, ``phases`` or ``open_items``. Open items have no key: they
are addressed by their place, and ``expect`` (the text the caller saw) guards against a list that changed meanwhile.
Changing a template needs the right to edit projects – deleting an entry too, it is a change of the template.
"""

from __future__ import annotations

from typing import ClassVar

from django.core.exceptions import ValidationError
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Level, SpecialRight
from rentalars.api.views import body_of
from rentalars.projects import template_content as tc

_SECTIONS = "|".join(tc.SECTIONS)
_SECTION_PARAMETER = OpenApiParameter("section", str, OpenApiParameter.PATH, enum=list(tc.SECTIONS))
_KEY_PARAMETER = OpenApiParameter(
    "key", int, OpenApiParameter.PATH, description="The key of the entry (open items: its place)."
)

_ENTRY = inline_serializer("ProjectTemplateEntry", {"key": serializers.IntegerField()})
_CONTENT = inline_serializer("ProjectTemplateContent", {"version": serializers.IntegerField()})


def _invalid(error: ValidationError) -> serializers.ValidationError:
    return serializers.ValidationError(serializers.as_serializer_error(error))


class TemplateContentActions:
    """The actions that change the content of a template."""

    action_levels: ClassVar[dict[str, int]] = {
        "content": Level.WRITE,
        "content_notes": Level.WRITE,
        "content_add": Level.WRITE,
        "content_entry": Level.WRITE,
        "content_move": Level.WRITE,
    }

    def _section(self, section: str) -> str:
        if section not in tc.SECTIONS:
            raise NotFound
        return section

    def _shown(self, content: dict) -> dict:
        """The content as this caller may see it: prices only for who may see prices."""
        return content if self.rights.has(SpecialRight.PRICES) else tc.without_prices(content)  # type: ignore[attr-defined]

    def _expect(self, request: Request) -> str | None:
        value = request.query_params.get("expect")
        if value is None and hasattr(request.data, "get"):
            value = request.data.get("expect")
        return None if value in (None, "") else str(value)

    # --- The whole content ------------------------------------------------------------------------------------------

    @extend_schema(request=_CONTENT, responses={200: _CONTENT})
    @action(detail=True, methods=["get", "put"], url_path="content")
    def content(self, request: Request, pk: str | None = None) -> Response:
        """Read the content of the template (every entry has a ``key``), or replace all of it (``PUT``).

        ``PUT`` takes the whole content as ``GET`` shows it. It is checked as a whole – references between groups, lines,
        phases, crew places – and nothing is stored if anything is wrong. Prices are only taken from callers who may see
        prices; for others they stay as they were. Keys that are left out are given; entries the body keeps with their key
        keep their place in the references.
        """
        template = self.get_object()  # type: ignore[attr-defined]
        if request.method == "GET":
            return Response(self._shown(tc.open_for_editing(template)))
        try:
            stored = tc.replace_content(template, request.data, rights=self.rights, user=request.user)  # type: ignore[attr-defined]
        except ValidationError as error:
            raise _invalid(error) from error
        return Response(self._shown(stored))

    @extend_schema(
        request=inline_serializer(
            "ProjectTemplateNotes",
            {
                "notes": serializers.CharField(required=False),
                "rental_days": serializers.IntegerField(allow_null=True, required=False),
            },
        ),
        responses={200: _CONTENT},
    )
    @action(detail=True, methods=["put"], url_path="content/notes")
    def content_notes(self, request: Request, pk: str | None = None) -> Response:
        """Set the notes a new project gets and the default rental days (empty: the days follow from the period)."""
        template = self.get_object()  # type: ignore[attr-defined]
        data = body_of(request)
        try:
            tc.set_notes(template, notes=data.get("notes", ""), rental_days=data.get("rental_days"), user=request.user)
        except ValidationError as error:
            raise _invalid(error) from error
        return Response(self._shown(tc.open_for_editing(template)))

    # --- One entry --------------------------------------------------------------------------------------------------

    @extend_schema(
        parameters=[_SECTION_PARAMETER],
        request=inline_serializer("ProjectTemplateEntryInput", {"name": serializers.CharField(required=False)}),
        responses={201: _ENTRY},
    )
    @action(detail=True, methods=["post"], url_path=rf"content/(?P<section>{_SECTIONS})", url_name="content-add")
    def content_add(self, request: Request, pk: str | None = None, section: str = "") -> Response:
        """Add an entry at the end of its section; a group goes below its ``parent``. Answer: the ``key`` of the new entry.

        The fields are those of the entries in the content (``GET .../content``): a group has ``name``, ``parent``,
        ``kind``…; a line ``product`` (or ``title`` for a free line, or ``is_text``), ``quantity``, ``group``…; a crew place
        ``job_function``; a vehicle booking ``product``; a phase ``kind``; an open item ``text``. A period is
        ``own_period`` with ``start`` and ``end`` in seconds from the start of the project (``anchor``: ``"end"`` for seconds
        from its end, negative); a crew place or booking names its ``phase`` by the place of the phase in the list (0 first).
        """
        template = self.get_object()  # type: ignore[attr-defined]
        section = self._section(section)
        try:
            key = tc.add_entry(template, section, dict(body_of(request)), rights=self.rights, user=request.user)  # type: ignore[attr-defined]
        except ValidationError as error:
            raise _invalid(error) from error
        return Response({"key": key}, status=status.HTTP_201_CREATED)

    @extend_schema(
        parameters=[
            _SECTION_PARAMETER,
            _KEY_PARAMETER,
            OpenApiParameter("with_content", bool, description="A group: delete what is in it too."),
            OpenApiParameter("expect", str, description="Open items: the text it had."),
        ],
        request=inline_serializer("ProjectTemplateEntryChange", {"expect": serializers.CharField(required=False)}),
        responses={200: _ENTRY, 204: None},
    )
    @action(
        detail=True,
        methods=["patch", "delete"],
        url_path=rf"content/(?P<section>{_SECTIONS})/(?P<key>\d+)",
        url_name="content-entry",
    )
    def content_entry(self, request: Request, pk: str | None = None, section: str = "", key: str = "") -> Response:
        """Change the fields that are sent (``PATCH``), or delete the entry (``DELETE``).

        A group that is deleted hands its lines and subgroups to its parent; with ``?with_content=true`` they are deleted
        too. A line or group that an alternative replaced turns the alternative into an optional one. Deleting a phase
        takes it off the crew places and bookings that named it. 404 if the entry is gone (or, for an open item, no
        longer has the text ``expect``).
        """
        template = self.get_object()  # type: ignore[attr-defined]
        section = self._section(section)
        number = int(key)
        try:
            if request.method == "DELETE":
                flag = str(request.query_params.get("with_content", "")).lower() in {"1", "true", "yes", "on"}
                tc.delete_entry(
                    template, section, number, user=request.user, with_content=flag, expect=self._expect(request)
                )
                return Response(status=status.HTTP_204_NO_CONTENT)
            content = tc.open_for_editing(template)
            changes = dict(body_of(request))
            expect = changes.pop("expect", None)
            if section == tc.OPEN_ITEMS:
                if number >= len(content[tc.OPEN_ITEMS]):
                    raise KeyError(number)
                tc.update_entry(
                    template,
                    section,
                    number,
                    changes,
                    rights=self.rights,
                    user=request.user,
                    expect=expect,  # type: ignore[attr-defined]
                )
            else:
                tc.index_of(content, section, number)  # 404 if it is gone
                changes.pop("key", None)
                tc.update_entry(
                    template,
                    section,
                    number,
                    changes,
                    rights=self.rights,
                    user=request.user,
                    merge=True,  # type: ignore[attr-defined]
                )
        except KeyError as error:
            raise NotFound from error
        except ValidationError as error:
            raise _invalid(error) from error
        return Response({"key": number})

    @extend_schema(
        parameters=[_SECTION_PARAMETER, _KEY_PARAMETER],
        request=inline_serializer(
            "ProjectTemplateMove",
            {
                "direction": serializers.ChoiceField(choices=["up", "down"]),
                "expect": serializers.CharField(required=False),
            },
        ),
        responses={200: _ENTRY},
    )
    @action(
        detail=True,
        methods=["post"],
        url_path=rf"content/(?P<section>{_SECTIONS})/(?P<key>\d+)/move",
        url_name="content-move",
    )
    def content_move(self, request: Request, pk: str | None = None, section: str = "", key: str = "") -> Response:
        """Move an entry one place up or down among its neighbours (a group with its subgroups). At the end nothing happens."""
        template = self.get_object()  # type: ignore[attr-defined]
        section = self._section(section)
        data = body_of(request)
        direction = data.get("direction")
        if direction not in ("up", "down"):
            raise serializers.ValidationError({"direction": ['Use "up" or "down".']})
        try:
            tc.open_for_editing(template)
            tc.move_entry(
                template,
                section,
                int(key),
                -1 if direction == "up" else 1,
                user=request.user,
                expect=data.get("expect"),
            )
        except KeyError as error:
            raise NotFound from error
        return Response({"key": int(key)})


__all__ = ["TemplateContentActions"]
