# SPDX-License-Identifier: GPL-3.0-or-later
"""API for taking over a lighting plot from an MVR file into a project (PRJ-077, API-002).

``POST /projects/{id}/mvr`` does what the page "Lighting plot from MVR" does,
in one or two calls:

1. Send only the ``file``: the answer lists the fixture types of the plot
   with their counts and the suggested products. Nothing is written.
2. Send the file again with ``mapping``: the lines are added (status 201)
   and the chosen products are remembered for the next plot. The
   file is kept in the files of the project as
   ``yyyymmdd-hhmmss_<name>.mvr`` (PRJ-086); ``kept_file`` names it, or is
   ``null`` with a warning if the file is too large for files of projects.

The same rights apply as for adding a line: write access to projects and
the right to edit this project.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Module
from rentalars.api.views import ModuleAPIView, body_of
from rentalars.products.models import Product
from rentalars.projects import mvr
from rentalars.projects.access import ProjectAccess, project_for
from rentalars.projects.mvr_views import validate_mvr_upload

SUGGESTIONS = inline_serializer(
    "MvrSuggestion",
    {
        "product": serializers.IntegerField(),
        "article_number": serializers.CharField(),
        "name": serializers.CharField(),
        "score": serializers.IntegerField(help_text="Similarity in percent; 100 for a remembered choice."),
        "source": serializers.ChoiceField(choices=["remembered", "remembered_mode", "similar"]),
        "reason": serializers.CharField(),
    },
    many=True,
)

FIXTURE_TYPES = inline_serializer(
    "MvrFixtureType",
    {
        "key": serializers.CharField(help_text="GDTF file and mode; the key of ``mapping``."),
        "gdtf_spec": serializers.CharField(),
        "mode": serializers.CharField(),
        "manufacturer": serializers.CharField(),
        "model": serializers.CharField(),
        "label": serializers.CharField(),
        "count": serializers.IntegerField(),
        "element": serializers.CharField(help_text="The kind of MVR object, e.g. Fixture or Truss."),
        "examples": serializers.ListField(child=serializers.CharField()),
        "named_by_gdtf": serializers.BooleanField(),
        "suggestions": SUGGESTIONS,
        "suggested": serializers.IntegerField(allow_null=True, help_text="The product preselected on the page."),
    },
    many=True,
)

PLOT = inline_serializer(
    "MvrPlot",
    {
        "file": serializers.CharField(),
        "fixtures": serializers.IntegerField(),
        "skipped": serializers.IntegerField(help_text="Objects without GDTF file, not counted."),
        "types": FIXTURE_TYPES,
        "group": serializers.IntegerField(allow_null=True, required=False),
        "lines": serializers.ListField(child=serializers.IntegerField(), required=False),
        "warnings": serializers.ListField(child=serializers.CharField(), required=False),
        "kept_file": inline_serializer(
            "MvrKeptFile",
            {"id": serializers.IntegerField(), "name": serializers.CharField()},
            required=False,
            allow_null=True,
            help_text="PRJ-086: the file in the files of the project, after the lines were added.",
        ),
    },
)


def _yes(value: Any, default: bool) -> bool:
    if value in (None, ""):
        return default
    return str(value).lower() not in {"false", "0", "no", "nein"}


def _quantity(value: Any, default: int) -> Decimal:
    if value in (None, ""):
        return Decimal(default)
    try:
        quantity = Decimal(str(value).replace(",", "."))
    except InvalidOperation as error:
        raise ValidationError({"mapping": _("“%(value)s” is not a number.") % {"value": value}}) from error
    if quantity <= 0 or not quantity.is_finite():
        raise ValidationError({"mapping": _("The quantity must be more than 0.")})
    return quantity


def parse_mapping(text: str, plot: mvr.Plot) -> dict[str, mvr.Choice]:
    """Read ``mapping``: ``{type key: product ID | {"product": ID, "quantity": n} | null}``.

    A type that is missing or maps to ``null`` is not taken over; the
    quantity defaults to the count of the plot.

    Raises:
        ValidationError: Not JSON, an unknown type or product.
    """
    try:
        entries = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValidationError({"mapping": _("The mapping is not valid JSON.")}) from error
    if not isinstance(entries, dict):
        raise ValidationError({"mapping": _("The mapping is not valid JSON.")})
    choices: dict[str, mvr.Choice] = {}
    for key, entry in entries.items():
        fixture_type = plot.type(key)
        if fixture_type is None:
            raise ValidationError({"mapping": _("The plot has no fixture type “%(key)s”.") % {"key": key}})
        if entry is None:
            continue
        details = entry if isinstance(entry, dict) else {"product": entry}
        product_id = details.get("product")
        product = Product.objects.filter(pk=product_id).first() if str(product_id).isdigit() else None
        if product is None:
            raise ValidationError({"mapping": _("There is no product %(id)s.") % {"id": product_id}})
        choices[key] = mvr.Choice(product=product, quantity=_quantity(details.get("quantity"), fixture_type.count))
    return choices


class MvrImportView(ModuleAPIView):
    """``POST /projects/{id}/mvr`` – read an MVR lighting plot and add its fixtures as lines (PRJ-077).

    Multipart fields:

    * ``file`` – the MVR file (required, at most 200 MB).
    * ``mapping`` – optional JSON: ``{"<type key>": <product ID>}``, or
      ``{"<type key>": {"product": <ID>, "quantity": <n>}}``; ``null``
      skips a type. Without it the answer only lists the types with their
      suggestions. With it the lines are added.
    * ``group`` – the ID of a group of the project for the lines, or
      ``none`` for "without group". Without it a new group is created.
    * ``group_name`` – the name of that new group; default "MVR" and the
      file name.
    * ``remember`` – remember the products for the types (default true).
    """

    module = Module.PROJECTS
    parser_classes: ClassVar[list[Any]] = [MultiPartParser, FormParser]

    @extend_schema(
        request=inline_serializer(
            "MvrImportRequest",
            {
                "file": serializers.FileField(),
                "mapping": serializers.CharField(required=False),
                "group": serializers.CharField(required=False),
                "group_name": serializers.CharField(required=False),
                "remember": serializers.BooleanField(default=True),
            },
        ),
        responses={200: PLOT, 201: PLOT},
    )
    def post(self, request: Request, project_pk: int) -> Response:
        """Read the plot; with ``mapping`` also add the lines."""
        project = project_for(request, project_pk, ProjectAccess.EDIT)
        data = body_of(request)
        uploaded = request.FILES.get("file")
        if uploaded is None:
            raise ValidationError({"file": _("Please send the MVR file.")})
        try:
            validate_mvr_upload(uploaded)
            plot = mvr.read_plot(uploaded, uploaded.name)
        except ValidationError as error:
            raise ValidationError({"file": error.messages}) from error
        body = plot.as_dict()
        suggestions = mvr.suggest(plot.types)
        for entry in body["types"]:
            offered = suggestions.get(entry["key"], [])
            preselected = mvr.preselection(offered)
            entry["suggestions"] = [suggestion.as_dict() for suggestion in offered]
            entry["suggested"] = preselected.product_id if preselected else None
        if not data.get("mapping"):
            return Response(body, status=status.HTTP_200_OK)

        choices = parse_mapping(str(data["mapping"]), plot)
        group = None
        group_name = ""
        group_value = str(data.get("group") or "").strip()
        if group_value.lower() == "none":
            pass
        elif group_value:
            group = project.groups.filter(pk=int(group_value)).first() if group_value.isdigit() else None
            if group is None:
                raise ValidationError({"group": _("Choose one of the groups of this project.")})
        else:
            group_name = str(data.get("group_name") or "") or mvr.default_group_name(plot.file_name)
        result = mvr.take_over(
            project,
            plot,
            choices,
            rights=self.rights,
            group=group,
            new_group_name=group_name,
            remember=_yes(data.get("remember"), True),
        )
        body["group"] = result.group.pk if result.group else None
        body["lines"] = [line.line.pk for line in result.lines]
        body["warnings"] = result.warnings
        body["kept_file"] = None
        try:
            kept = mvr.keep_file(project, uploaded, user=request.user)
        except ValidationError as error:
            body["warnings"].append(
                _("The MVR file was not kept in the files of the project: %(reason)s")
                % {"reason": " ".join(error.messages)}
            )
        else:
            body["kept_file"] = {"id": kept.pk, "name": kept.original_name}
        return Response(body, status=status.HTTP_201_CREATED)
