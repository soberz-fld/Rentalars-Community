# SPDX-License-Identifier: GPL-3.0-or-later
"""API of subrentals per supplier (PRJ-106).

``/projects/{id}/subrentals``
    The suppliers the project has to do with: subrentals, documents or
    mails, each with counts.
``/projects/{id}/subrentals/{supplier}``
    What the page "Zumietung bei …" shows: the supplier, its subrental
    lines with status (and purchase prices with their right), its documents
    and – with the right to read correspondence – its mails. ``PATCH``
    changes status and purchase price of several lines at once.

Documents of a supplier are files of the project (``/projects/{id}/files``
with ``supplier`` and ``supplier_document_kind``); which supplier a mail
belongs to is set with ``POST /projects/{id}/mails/{mail}/supplier``.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Module, SpecialRight
from rentalars.api.views import ModuleAPIView, body_of
from rentalars.masterdata.models import Supplier
from rentalars.projects import subrentals
from rentalars.projects.access import ProjectAccess, project_for
from rentalars.projects.models import Project, SubrentalStatus


def supplier_document(supplier: Supplier) -> dict[str, Any]:
    """The supplier with its contact data – and its address with the route from the viewer's location (UIX-033)."""
    from rentalars.core.maps import route_url

    return {
        "id": supplier.pk,
        "name": supplier.name,
        "contact": supplier.contact,
        "email": supplier.email,
        "phone": supplier.phone,
        "customer_number": supplier.customer_number,
        "street": supplier.street,
        "postal_code": supplier.postal_code,
        "city": supplier.city,
        "country": supplier.country,
        "route_url": route_url(supplier.address_one_line),
        "is_active": supplier.is_active,
    }


def page_document(page: subrentals.SubrentalPage, *, with_costs: bool) -> dict[str, Any]:
    """The page of a supplier in a project as JSON."""
    lines = []
    for row in page.rows:
        line = row.line
        entry: dict[str, Any] = {
            "id": line.pk,
            "title": line.title,
            "quantity": line.quantity,
            "unit": line.unit.abbreviation if line.unit_id else None,
            "start": line.start,
            "end": line.end,
            "status": line.subrental_status or SubrentalStatus.OPEN,
            "picked_up_at_supplier": line.picked_up_at_supplier,  # PRJ-097
            "covers_line": line.covers_line_id,
            "variant": line.variant,
        }
        if with_costs:
            entry["purchase_price"] = line.purchase_price
            entry["purchase_cost"] = row.purchase_cost
        lines.append(entry)
    document: dict[str, Any] = {
        "project": page.project.pk,
        "supplier": supplier_document(page.supplier),
        "lines": lines,
        "documents": [
            {
                "id": item.pk,
                "title": item.title,
                "original_name": item.original_name,
                "kind": item.supplier_document_kind,
                "size": item.size,
                "uploaded_at": item.uploaded_at,
            }
            for item in page.files
        ],
        "mails": None
        if page.mails is None
        else [
            {
                "id": mail.pk,
                "direction": mail.direction,
                "subject": mail.subject,
                "date": mail.date,
                "linked": mail.supplier_id == page.supplier.pk,
            }
            for mail in page.mails
        ],
    }
    if with_costs:
        document["purchase_total"] = page.purchase_total
    return document


def _page_project(request: Request, project_pk: int, level: ProjectAccess) -> Project:
    return project_for(request, project_pk, level)


class ProjectSubrentalListView(ModuleAPIView):
    """``GET /projects/{id}/subrentals`` – the suppliers of the project's subrentals (PRJ-106)."""

    module = Module.PROJECTS
    schema_tag = "availability"

    @extend_schema(
        responses={200: inline_serializer("ProjectSubrentalSupplier", {"supplier": serializers.DictField()}, many=True)}
    )
    def get(self, request: Request, project_pk: int) -> Response:
        """Per supplier: how many subrental lines (by status), documents and mails the project has."""
        project = _page_project(request, project_pk, ProjectAccess.READ)
        rows = []
        for supplier in subrentals.suppliers_of(project):
            page = subrentals.build_page(project, supplier, rights=self.rights)
            rows.append(
                {
                    "supplier": supplier_document(supplier),
                    "lines": len(page.rows),
                    "statuses": dict(Counter(row.line.subrental_status or SubrentalStatus.OPEN for row in page.rows)),
                    "documents": len(page.files),
                    "mails": None if page.mails is None else len(page.mails),
                }
            )
        return Response(rows)


class ProjectSubrentalDetailView(ModuleAPIView):
    """``/projects/{id}/subrentals/{supplier}`` – the page "Zumietung bei …" (PRJ-106)."""

    module = Module.PROJECTS
    schema_tag = "availability"

    @extend_schema(responses={200: inline_serializer("ProjectSubrental", {"supplier": serializers.DictField()})})
    def get(self, request: Request, project_pk: int, supplier_pk: int) -> Response:
        """Lines with status, documents and mails of the supplier in the project.

        Purchase prices only with their right, mails only with the right to
        read correspondence (``null`` without it).
        """
        project = _page_project(request, project_pk, ProjectAccess.READ)
        supplier = get_object_or_404(Supplier, pk=supplier_pk)
        page = subrentals.build_page(project, supplier, rights=self.rights)
        return Response(page_document(page, with_costs=self.rights.has(SpecialRight.PURCHASE_PRICES)))

    @extend_schema(
        request=inline_serializer(
            "ProjectSubrentalChange",
            {
                "lines": serializers.ListField(
                    child=inline_serializer(
                        "ProjectSubrentalLineChange",
                        {
                            "id": serializers.IntegerField(),
                            "status": serializers.ChoiceField(choices=SubrentalStatus.choices, required=False),
                            "picked_up_at_supplier": serializers.BooleanField(required=False),
                            "purchase_price": serializers.DecimalField(10, 2, required=False, allow_null=True),
                        },
                    )
                )
            },
        ),
        responses={200: inline_serializer("ProjectSubrentalChanged", {"supplier": serializers.DictField()})},
    )
    def patch(self, request: Request, project_pk: int, supplier_pk: int) -> Response:
        """Change status, pickup (PRJ-097) and purchase price of several of the supplier's lines at once – all or none.

        A status other than "open" needs the line's supplier, which a line of
        this page always has; purchase prices need their right.
        """
        project = _page_project(request, project_pk, ProjectAccess.EDIT)
        supplier = get_object_or_404(Supplier, pk=supplier_pk)
        entries = body_of(request).get("lines")
        if not isinstance(entries, list):
            raise ValidationError({"lines": _("A list of lines is expected.")})
        values: dict[int, dict[str, Any]] = {}
        for entry in entries:
            if not isinstance(entry, dict) or not str(entry.get("id", "")).isdigit():
                raise ValidationError({"lines": _("Every line needs its ID.")})
            wanted: dict[str, Any] = {}
            if "status" in entry:
                if entry["status"] not in SubrentalStatus.values:
                    raise ValidationError({"status": _("Unknown status.")})
                wanted["subrental_status"] = entry["status"]
            if "picked_up_at_supplier" in entry:
                # PRJ-097: fetched at the supplier – a trip of the project.
                if not isinstance(entry["picked_up_at_supplier"], bool):
                    raise ValidationError({"picked_up_at_supplier": _("Expected true or false.")})
                wanted["picked_up_at_supplier"] = entry["picked_up_at_supplier"]
            if "purchase_price" in entry:
                wanted["purchase_price"] = _decimal_or_none(entry["purchase_price"])
            values[int(entry["id"])] = wanted
        subrentals.update_lines(project, supplier, values, rights=self.rights)
        page = subrentals.build_page(project, supplier, rights=self.rights)
        return Response(page_document(page, with_costs=self.rights.has(SpecialRight.PURCHASE_PRICES)))


def _decimal_or_none(value: Any) -> Decimal | None:
    """A purchase price as sent: a number, or ``null`` for none."""
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation as error:
        raise ValidationError({"purchase_price": _("Enter a number.")}) from error
    if number < 0:
        raise ValidationError({"purchase_price": _("The purchase price cannot be negative.")})
    return number
