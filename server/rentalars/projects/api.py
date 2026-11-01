# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the projects module: projects, groups, lines, totals, shortages (chapter 8)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import django_filters
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, prefetch_related_objects
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, NotFound
from rest_framework.permissions import SAFE_METHODS
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.api import UserSerializer
from rentalars.accounts.models import User
from rentalars.accounts.rights import Level, Module, SpecialRight, request_rights
from rentalars.api.serializers import ExpandableFieldsMixin, RestrictedFieldsMixin
from rentalars.api.views import ModuleAPIView, ModuleViewSet, body_of
from rentalars.availability.engine import LineAvailability
from rentalars.availability.services import open_shortages, subrental_lines
from rentalars.core.history import describe
from rentalars.core.models import AuditLogEntry
from rentalars.customers.api import ContactSerializer, CustomerSerializer
from rentalars.masterdata.models import Supplier
from rentalars.material.models import MaterialItem
from rentalars.personnel.models import JobFunction, Person
from rentalars.products.models import Product
from rentalars.projects import crew, field_changes, services, template_content
from rentalars.projects import numbers as project_numbers
from rentalars.projects.access import (
    ProjectAccess,
    access_level,
    access_of_many,
    may_plan_crew,
    module_level_in,
    note_access,
    note_case_work,
    person_of,
    project_for,
    readable_projects,
    visible_projects,
)
from rentalars.projects.case_work import CaseWorkPermission
from rentalars.projects.discounts import crew_discount_warning, group_discount_warning
from rentalars.projects.duplicate import duplicate_project
from rentalars.projects.files import files_for_crew
from rentalars.projects.follow_up import FILTER_CHOICES as FOLLOW_UP_CHOICES
from rentalars.projects.follow_up import filter_projects as filter_follow_ups
from rentalars.projects.grouptree import GroupTree
from rentalars.projects.logistics_api import vehicle_line_document
from rentalars.projects.models import (
    INHERITED_FIELDS,
    CrewLine,
    Group,
    MaterialLine,
    Project,
    ProjectAccessLevel,
    ProjectKind,
    ProjectMembership,
    ProjectPhase,
    ProjectStatus,
    ProjectTemplate,
    SubrentalStatus,
    VehicleLine,
)
from rentalars.projects.period_warnings import project_warnings
from rentalars.projects.planning import PlannedLine, Planning, build_planning
from rentalars.projects.pricing import LinePrice, ProjectPrices, compute_project_prices
from rentalars.projects.tables import may_see_customers
from rentalars.projects.template_content_api import TemplateContentActions

# --- Helpers that turn calculated values into JSON ------------------------------

#: PRJ-113: moments as every other moment of the API – ISO 8601 in the time zone of the installation.
_MOMENT = serializers.DateTimeField()


def change_times_document(project: Project, keys: tuple[str, ...]) -> dict[str, Any]:
    """PRJ-113, PRJ-114: ``field_changed_at`` – these keys with the moment of their last change."""
    times = field_changes.times_of(project)
    return {key: _MOMENT.to_representation(times[key]) for key in keys}


def sees_availability(context: dict[str, Any]) -> bool:
    """AUT-032: whether the caller of a serializer may see the availability of material (special right).

    Without a request in the context – inside the application – it is shown.
    """
    request = context.get("request")
    return request is None or request_rights(request).has(SpecialRight.AVAILABILITY)


def availability_document(availability: LineAvailability) -> dict[str, Any]:
    """The availability verdict of a line (PRJ-012, PRJ-013)."""
    return {
        "status": availability.status,
        "shortage": availability.shortage_total,
        "excess_cover": availability.excess_cover_total,
        "details": [
            {
                "product": detail.product_id,
                "required": detail.required,
                "covered_by_subrental": detail.covered,
                "from_stock": detail.from_stock,
                "shortage": detail.shortage,
                "stock": detail.stock,
                "firm": detail.firm,
                "optional": detail.optional,
                "own_project": detail.own_project,
                "free": detail.free,
                "via": detail.via,
            }
            for detail in availability.details
        ],
    }


def price_document(price: LinePrice) -> dict[str, Any]:
    """The calculated price of a line (PRD-035: days, factor and result are shown)."""
    return {
        "rental_days": price.rental_days,
        "rental_days_from": price.rental_days_source or None,
        "scale_factor": price.scale_factor,
        "scale_is_outdated": price.scale_is_outdated,
        "amount_before_discount": price.base_amount,
        "discount": price.discount_amount,
        # PER-026: the discount as it applies, cut to the maximum of the job function.
        "discount_percent": price.discount_percent,
        "max_discount_percent": price.max_discount_percent,
        "discount_is_capped": price.discount_is_capped,
        "amount": price.amount,
        # PRJ-075: optional and alternative lines are priced, but not added up.
        "counts_toward_total": price.counts,
        # PRJ-096: the customer's own material, taken along without charge.
        "is_customer_material": price.is_customer_material,
        "is_estimate": price.is_estimate,
        "surcharge_base": price.surcharge_base,
        "surcharge_refers_to": price.surcharge_target_labels,
    }


def crew_document(
    price: crew.CrewPrice, warnings: list[str] | None = None, *, with_prices: bool, with_costs: bool
) -> dict[str, Any]:
    """A crew line with what was calculated for it (PRJ-019, PRJ-051, PRJ-061).

    The price for the customer needs the price right; hourly rate, day rate,
    flat rate and costs need the right for personnel costs (AUT-019). Since
    ``phase`` (PRJ-080), ``days`` – as typed in, empty for "the
    calendar days of the period" – and ``period_days`` (PER-029); with the
    price right ``charged_days`` for a line billed per day. The
    request: ``request_status``, the period asked for (``requested_start``,
    ``requested_end``) and ``times_changed_since_request`` (PER-033). Since
    PER-041: ``request_status`` may be ``firm``: planned firmly, without request.

    The service product with its article number
    (``service_product_article_number``, PRD-044) and the hour tiers per day
    (PER-035): with the price right ``hours_limit``,
    ``unit_price_above_limit`` and, of the charged hours, ``normal_hours`` and
    ``hours_above_limit``; with the right for personnel costs
    ``hourly_rate_above_limit``, ``cost_hours_above_limit`` and
    ``cost_rate_above_limit``.

    The surcharges for night, Sunday and holidays (PER-009): with
    the price right ``time_surcharges_on_price``, ``time_surcharges`` (one
    entry per kind: ``kind``, ``label``, ``percent``, ``hours``, ``amount``)
    and ``time_surcharge_amount`` – part of ``amount_before_discount``; with
    the right for personnel costs ``time_surcharges_on_cost``,
    ``cost_time_surcharges``, ``cost_time_surcharge_amount`` (part of
    ``cost``) and ``actual_cost_time_surcharges``,
    ``actual_cost_time_surcharge_amount`` (part of ``actual_cost``).

    PER-040: an entry is one kind of surcharge – the rules of the
    same name and percentage; ``kind`` is the kind for the rules of
    § 3b EStG (``night``, ``night_after_midnight``, ``sunday``, ``holiday``,
    ``high_holiday``), else ``custom``; ``rule`` the id of its first rule.
    """
    line = price.line
    document: dict[str, Any] = {
        "id": line.pk,
        "project": line.project_id,
        "job_function": line.job_function_id,
        "job_function_name": line.job_function.name,
        "person": line.person_id,
        "person_name": line.person.name if line.person_id else None,
        "is_vacant": line.is_vacant,
        "phase": line.phase_id,
        "start": line.start,
        "end": line.end,
        "planned_hours": line.planned_hours,
        "approved_hours": price.approved_hours,
        "days": line.days,
        "period_days": line.period_days,
        "meeting_point": line.meeting_point,
        "note": line.note,
        "service_product": line.service_product_id,
        "service_product_article_number": line.service_product.article_number if line.service_product_id else None,
        "title": line.title,
        "billing": line.billing,
        "warnings": warnings or [],
        # PER-016; PER-033: the request with the period asked for, and whether the times changed since.
        "request_status": line.request_status,
        "requested_at": line.requested_at,
        "answered_at": line.answered_at,
        "answer_note": line.answer_note,
        "requested_start": line.requested_start,
        "requested_end": line.requested_end,
        "times_changed_since_request": line.times_changed_since_request,
        # LOG-008: the vehicle of the project the person travels with, and whether they drive it.
        "vehicle_line": line.vehicle_line_id,
        "is_driver": line.is_driver,
    }
    if with_prices:
        document.update(
            unit_price=line.unit_price,
            tax_rate=line.tax_rate_id,
            charged_hours=price.charged_hours,
            charged_days=price.days,
            # PER-026: the line's discount as typed in, as it applies, and the maximum of the job function.
            discount_percent=line.discount_percent,
            effective_discount_percent=price.discount_percent,
            max_discount_percent=price.max_discount_percent,
            discount_is_capped=price.discount_is_capped,
            amount_before_discount=price.base_amount,
            discount=price.discount_amount,
            amount=price.amount,
            is_estimate=price.is_estimate,
            # PER-035: the limit of hours per day as on the line, and how the charged hours split at it.
            hours_limit=line.hours_limit,
            unit_price_above_limit=line.unit_price_above_limit,
            normal_hours=price.normal_hours,
            hours_above_limit=price.hours_above_limit if price.hours_limit is not None else None,
            # PER-009: the surcharges for night, Sunday and holidays – switched on the line, part of the amount
            # before the discount, by kind.
            time_surcharges_on_price=line.time_surcharges_on_price,
            time_surcharges=[part.as_dict() for part in price.time_surcharges],
            time_surcharge_amount=price.time_surcharge_amount,
        )
    if with_costs:
        document.update(
            hourly_rate=line.hourly_rate,
            daily_rate=line.daily_rate,
            cost_flat_rate=line.cost_flat_rate,
            cost=price.cost,
            cost_is_guide_value=price.cost_is_guide,
            # PER-029: per day the cost is days × day rate; without any day rate hours × hourly rate.
            cost_per_day=price.cost_per_day,
            cost_rate=price.cost_rate,
            actual_cost=price.actual_cost,
            # PER-035: the person's rate from the limit, and the planned hours costed with it.
            hourly_rate_above_limit=line.hourly_rate_above_limit,
            cost_hours_above_limit=price.cost_hours_above_limit,
            cost_rate_above_limit=price.cost_rate_above_limit,
            # PER-009: the surcharges on the planned cost and on what the approved times cost, by kind.
            time_surcharges_on_cost=line.time_surcharges_on_cost,
            cost_time_surcharges=[part.as_dict() for part in price.cost_time_surcharges],
            cost_time_surcharge_amount=price.cost_time_surcharge_amount,
            actual_cost_time_surcharges=[part.as_dict() for part in price.actual_cost_time_surcharges],
            actual_cost_time_surcharge_amount=price.actual_cost_time_surcharge_amount,
        )
    return document


def crew_by_phase_rows(shares: list[crew.PhaseShare], *, with_costs: bool) -> list[dict[str, Any]]:
    """The personnel by phase and job function, for the price overview (PRJ-088); costs need their right (AUT-019)."""
    rows = []
    for share in shares:
        functions = []
        for row in share.functions:
            entry: dict[str, Any] = {
                "job_function": row.job_function.pk,
                "name": row.job_function.name,
                "places": row.places,
                "hours": row.hours,
                "days": row.days,
                "flat": row.flat,
                "amount": row.amount,
            }
            if with_costs:
                entry.update(cost=row.cost, margin=row.margin)
            functions.append(entry)
        block: dict[str, Any] = {
            "phase": share.phase.pk if share.phase is not None else None,
            "label": share.label,
            "start": share.phase.start if share.phase is not None else None,
            "end": share.phase.end if share.phase is not None else None,
            "functions": functions,
            "subtotal": share.amount,
        }
        if with_costs:
            block.update(cost=share.cost, margin=share.margin)
        rows.append(block)
    return rows


def totals_document(prices: ProjectPrices, *, with_costs: bool, with_personnel_costs: bool = False) -> dict[str, Any]:
    """The sums of a project (PRJ-024, PRJ-034).

    Costs of subrentals need the purchase price right, costs of personnel
    the right for personnel costs; the contribution margin – net minus all
    costs – needs both, because it would give one of them away (AUT-019).
    """
    document: dict[str, Any] = {
        "groups": [
            {
                "group": group.group.pk,
                "name": group.group.name,
                "kind": group.group.kind,
                "lines_total": group.lines_total,
                "discount": group.discount,
                "surcharges": group.surcharges_total,
                "subtotal": group.subtotal,
                "counts_toward_total": group.counts_toward_total,
                # PER-026: what the maximum discounts of its lines took back from the group's discount.
                "discount_limited_by": group.cap_excess,
                # PRJ-037: where the group stands; a parent's subtotal includes its subgroups.
                "parent": group.group.parent_id,
                "depth": group.depth,
            }
            for group in prices.groups
        ],
        "groups_total": prices.groups_total,
        "without_group_total": prices.ungrouped_total,
        "personnel_total": prices.personnel_total,
        # PER-009: of it, the surcharges for night, Sunday and holidays, before discounts.
        "personnel_time_surcharges": prices.personnel_time_surcharges,
        # LOG-009: vehicles and trailers, after their discounts.
        "logistics_total": prices.logistics_total,
        "surcharges_total": prices.surcharges_total,
        "optional_total": prices.optional_total,
        # PRJ-075: optional and alternative lines, not part of the total.
        "optional_lines_total": prices.optional_lines_total,
        "alternative_lines_total": prices.alternative_lines_total,
        "material_before_discount": prices.material_before_discount,
        "discount_total": prices.discount_total,
        # PRJ-123: the sum before the project's overall discount, and what it takes off (0 without one).
        "net_before_overall_discount": prices.net_before_overall_discount,
        "overall_discount": prices.overall_discount,
        "net_total": prices.net_total,
        "tax": [
            {
                "tax_rate": tax.tax_rate.pk,
                "name": tax.tax_rate.name,
                "rate": tax.tax_rate.rate,
                "net": tax.net,
                "tax": tax.tax,
            }
            for tax in prices.tax_lines
        ],
        "tax_total": prices.tax_total,
        "gross_total": prices.gross_total,
        "has_estimates": prices.has_estimates,
        "lines_with_outdated_scale": prices.outdated_scale_lines,
        "lines_with_limited_discount": prices.capped_discount_lines,
    }
    if with_costs:
        document["subrental_cost"] = prices.subrental_cost
        document["logistics_cost"] = prices.logistics_cost  # LOG-010
    if with_personnel_costs:
        document["personnel_cost"] = prices.personnel_cost
        document["personnel_actual_cost"] = prices.personnel_actual_cost
        # ZEI-019: approved expenses and travel costs of the crew; the margin subtracts them.
        document["expenses_cost"] = prices.expenses_cost
    if with_costs and with_personnel_costs:
        document["contribution_margin"] = prices.contribution_margin
    return document


# --- Serializers ----------------------------------------------------------------


class ProjectSerializer(ExpandableFieldsMixin, serializers.ModelSerializer):
    """A project (PRJ-003). The status is changed with ``POST /projects/{id}/status``.

    ``access`` tells what the caller may do in this project: ``deployment``,
    ``read`` or ``edit`` (AUT-025). With ``deployment`` – crew planned in the
    project – only the fields of the deployment view are delivered: no
    customer, no contact data of the customer's side beyond the contact on
    site, no notes, nothing about prices (AUT-023).
    """

    suggested_rental_days = serializers.IntegerField(read_only=True)
    effective_rental_days = serializers.IntegerField(read_only=True)
    allowed_next_statuses = serializers.ListField(child=serializers.CharField(), read_only=True)
    access = serializers.SerializerMethodField()
    #: PRJ-044: the parts of a whole project.
    subprojects = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    #: PRJ-105: the follow-up – day, note and user are read-only here; ``/projects/{id}/follow-up`` changes them.
    follow_up_user_name = serializers.SerializerMethodField()
    follow_up_is_due = serializers.BooleanField(read_only=True)
    template = serializers.PrimaryKeyRelatedField(
        queryset=ProjectTemplate.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
        help_text="Only when creating: fill the new project from this template (PRJ-076).",
    )
    # PRJ-107: "Als Projekt anlegen" from Projekte → Anfragen.
    inquiry = serializers.IntegerField(
        write_only=True,
        required=False,
        help_text="Only when creating: the mail without project tag (Projekte → Anfragen) that goes into the project.",
    )
    #: PRJ-113: when each field last changed – key → moment (``projects.field_changes``).
    field_changed_at = serializers.SerializerMethodField()
    changed_at = serializers.DateTimeField(
        write_only=True,
        required=False,
        help_text=(
            "PATCH (PRJ-113): when the change was made, ISO 8601 with time zone. Each field sent counts only if "
            "this is later than its time in field_changed_at (equal: the server wins; the future counts as now); "
            "the answer is the project as it is now with `applied`, the keys taken over."
        ),
    )
    #: API-016: names instead of IDs for the crew view – also with the deployment view.
    manager_name = serializers.SerializerMethodField()
    #: PRJ-122: the customer's name – in every role, also with the deployment view; ``null`` without customer.
    customer_name = serializers.SerializerMethodField()
    venue_label = serializers.CharField(read_only=True)
    #: DOK-015: the invoice – for who may see prices; set with ``POST /projects/{id}/invoice-status``.
    invoice_state = serializers.SerializerMethodField()
    #: PRJ-005 (event end; PRJ-127): warnings about the periods, as texts – no error, the change is saved.
    warnings = serializers.SerializerMethodField()

    #: What a caller with the deployment view gets (AUT-025).
    DEPLOYMENT_FIELDS = frozenset(
        {
            "id",
            "number",
            "name",
            "field_changed_at",  # PRJ-113: the keys of these fields only
            "manager_name",  # API-016
            "customer_name",  # PRJ-122
            "venue_label",  # API-016
            "venue_site",
            "venue",
            "manager",
            "status",
            "start",
            "end",
            "event_start",
            "event_end",
            "is_internal",
            "access",
            "parent",
        }
    )

    expandable_fields = {"customer": CustomerSerializer, "contact": ContactSerializer, "manager": UserSerializer}

    class Meta:
        model = Project
        fields = [
            "id",
            "number",
            "name",
            "customer",
            "customer_name",  # PRJ-122
            "is_internal",
            "contact",
            "billing_address",
            "delivery_address",
            "venue_site",
            "venue",
            "manager",
            "status",
            "start",
            "end",
            "event_start",
            "event_end",
            "rental_days",
            "suggested_rental_days",
            "effective_rental_days",
            # PRJ-123: the overall discount, percent or amount – for who may see prices.
            "overall_discount_percent",
            "overall_discount_amount",
            "notes",
            "parent",
            "subprojects",
            "allowed_next_statuses",
            "access",
            "created_at",
            "template",
            "inquiry",  # PRJ-107
            # ADM-012, ADM-014: the number before an update renumbered the project (the one with
            # "P-"), empty for projects created since.
            "former_number",
            # PRJ-105: the follow-up; set and removed with ``PUT``/``DELETE /projects/{id}/follow-up``.
            "follow_up_on",
            # PRJ-109: the time of the reminder ("14:30:00"), ``null`` without one.
            "follow_up_at",
            "follow_up_note",
            "follow_up_user",
            "follow_up_user_name",
            "follow_up_is_due",
            # PRJ-090: "project" or "service_case"; a service case is created and changed under /service-cases.
            "kind",
            "case_status",
            "case_contact",
            # PRJ-113: the companion app's offline changes – the younger change wins.
            "field_changed_at",
            "changed_at",
            # API-016: the names for the crew view.
            "manager_name",
            "venue_label",
            # DOK-015: "issued" ticked by hand, "not_needed", or "" – and what that makes of the invoice.
            "invoice_status",
            "invoice_state",
            # PRJ-005: an event that ends after "Material zurück bis" – read-only, empty if all fits.
            "warnings",
        ]
        read_only_fields = [
            "number",
            "status",
            "created_at",
            "former_number",
            "kind",
            "case_status",
            "case_contact",
            "invoice_status",
        ]

    def _access_of(self, project: Project) -> ProjectAccess:
        """The caller's level in a project; looked up for a whole list at once."""
        known: dict[int, ProjectAccess] = self.context.setdefault("project_access", {})
        if project.pk not in known:
            request = self.context["request"]
            # In a list this serializer is the child of the one that holds the rows.
            listed = getattr(self.parent, "instance", None) if self.parent is not None else None
            rows = listed if isinstance(listed, list) else [project]
            ids = [row.pk for row in rows if getattr(row, "pk", None)] or [project.pk]
            known.update(access_of_many(request_rights(request), request.user, ids))
        return known.get(project.pk, ProjectAccess.NONE)

    @extend_schema_field(serializers.ChoiceField(choices=["deployment", "read", "edit"]))
    def get_access(self, project: Project) -> str:
        """``deployment``, ``read`` or ``edit`` (AUT-025)."""
        return self._access_of(project).name.lower()

    def get_follow_up_user_name(self, project: Project) -> str | None:
        """PRJ-105: the name of the user the follow-up is for, ``null`` without one."""
        return str(project.follow_up_user) if project.follow_up_user_id else None

    @extend_schema_field(serializers.DictField(child=serializers.DateTimeField()))
    def get_field_changed_at(self, project: Project) -> dict[str, Any]:
        """PRJ-113: key → moment of its last change; a service case adds ``case_status`` and ``case_contact``."""
        keys = field_changes.PROJECT_KEYS + (field_changes.CASE_EXTRA_KEYS if project.is_service_case else ())
        return change_times_document(project, keys)

    def get_manager_name(self, project: Project) -> str | None:
        """API-016: the name of the project manager, ``null`` without one."""
        return str(project.manager) if project.manager_id else None

    def get_customer_name(self, project: Project) -> str | None:
        """PRJ-122: the name of the customer, ``null`` without one (an internal project, a case without)."""
        return project.customer.name if project.customer_id else None

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_warnings(self, project: Project) -> list[str]:
        """PRJ-005 (event end; PRJ-127): what to check about the periods – an event that ends after "material back by".

        A warning, never an error: the change is saved. Empty if everything fits; the language is that of the call.
        """
        return project_warnings(project)

    @extend_schema_field(serializers.ChoiceField(choices=["open", "invoiced", "not_needed"], allow_null=True))
    def get_invoice_state(self, project: Project) -> str | None:
        """DOK-015: ``open``, ``invoiced`` or ``not_needed`` – the state of the invoice.

        ``null`` without the price right, and for a project invoiced through
        another one or never: a part, internal, cancelled – or closed before
        Without an invoice in Rentalars (``invoice_status: earlier``).
        """
        from rentalars.documents import invoice_reminders

        request = self.context.get("request")
        if request is None or not request_rights(request).has(SpecialRight.PRICES):
            return None
        invoiced: set[int] | None = self.context.get("invoiced_projects")
        if invoiced is None:
            listed = getattr(self.parent, "instance", None) if self.parent is not None else None
            rows = listed if isinstance(listed, list) else [project]
            ids = [row.pk for row in rows if getattr(row, "pk", None)] or [project.pk]
            # DOK-016: also the service cases a monthly invoice bills.
            invoiced = invoice_reminders.invoiced_ids(ids)
            self.context["invoiced_projects"] = invoiced
        state = invoice_reminders.state_of(project, has_invoice=project.pk in invoiced)
        return state or None

    def to_representation(self, instance: Project) -> dict[str, Any]:
        """With the deployment view only, leave out everything that is not part of it (AUT-023).

        AUT-033, AUT-034: a service case read by someone who may not see customers – working on it
        through ``case_work`` – has no customer, contact, addresses or reporter, as on the page of the case.
        """
        data = super().to_representation(instance)
        if not request_rights(self.context["request"]).has(SpecialRight.PRICES):
            data.pop("overall_discount_percent", None)  # PRJ-123: a price (AUT-019)
            data.pop("overall_discount_amount", None)
        if instance.is_service_case and not may_see_customers(request_rights(self.context["request"])):
            for name in ("customer", "contact", "billing_address", "delivery_address"):
                if name in data:
                    data[name] = None
            if "case_contact" in data:
                data["case_contact"] = ""
        if self._access_of(instance) < ProjectAccess.READ:
            data = {name: value for name, value in data.items() if name in self.DEPLOYMENT_FIELDS}
            # "?expand=manager" would add the account of the manager with e-mail address and roles.
            data["manager"] = instance.manager_id
            # PRJ-113: no time of a change of a field the deployment view does not show (the notes, say).
            data["field_changed_at"] = {
                key: moment for key, moment in data["field_changed_at"].items() if key in self.DEPLOYMENT_FIELDS
            }
        # PRJ-119: the companion app reads them in the detail (``GET /projects/{id}``), not in lists.
        from rentalars.projects.relation_api import add_related

        add_related(data, instance, self.context)
        return data

    @transaction.atomic
    def create(self, validated_data: dict[str, Any]) -> Project:
        """Create the project with the next project number – from a template, if one is named (PRJ-076)."""
        from rentalars.projects.project_templates import apply_template

        template = validated_data.pop("template", None)
        validated_data.pop("changed_at", None)  # PRJ-113: for changes only
        request = self.context["request"]
        discount = {
            name: validated_data.pop(name) for name in services.OVERALL_DISCOUNT_FIELDS if name in validated_data
        }
        parent = validated_data.pop("parent", None)
        unknown = self._inquiry(validated_data.pop("inquiry", None))
        if parent is not None:
            # PRJ-044: a part of a whole project the caller may edit; customer and billing are the whole project's.
            if access_level(request_rights(request), request.user, parent) < ProjectAccess.EDIT:
                raise serializers.ValidationError({"parent": _("You may not add subprojects to this project.")})
            for name in INHERITED_FIELDS:
                validated_data.pop(name, None)
            project = services.create_subproject(parent, **validated_data)
        else:
            project = services.create_project(**validated_data)
        if discount:
            self._set_overall_discount(project, discount)
        if parent is None and request_rights(request).is_limited_to_assigned_projects(Module.PROJECTS):
            # AUT-016: without a membership the creator could not open the new project.
            ProjectMembership.objects.get_or_create(
                project=project, user=request.user, defaults={"level": ProjectAccessLevel.EDIT}
            )
        if template is not None:
            apply_template(template, project, rights=request_rights(request))
        if unknown is not None:
            # PRJ-107: the mail goes into the new project – both or neither.
            from rentalars.mail.imap import MailboxError
            from rentalars.mail.inquiries import take_into

            try:
                take_into(unknown, project)
            except MailboxError as error:
                raise serializers.ValidationError({"inquiry": str(error)}) from error
        return project

    def _inquiry(self, inquiry: int | None) -> Any:
        """PRJ-107: the waiting inquiry a new project is made from; needs the right to write e-mail (EML-042)."""
        if inquiry is None:
            return None
        from rentalars.mail.models import UnknownTagMail

        if not request_rights(self.context["request"]).can_write(Module.EMAIL):
            raise PermissionDenied
        # MAT-057: a defect report becomes a service case, not a project.
        unknown = UnknownTagMail.objects.filter(
            pk=inquiry, resolved_at__isnull=True, tag="", defect_report=None
        ).first()
        if unknown is None:
            raise serializers.ValidationError({"inquiry": _("There is no such inquiry waiting.")})
        return unknown

    def update(self, instance: Project, validated_data: dict[str, Any]) -> Project:
        """Change the project; closed projects are locked (PRJ-009).

        The whole project of a part is fixed once it is created (PRJ-044); on
        a part, customer and billing follow the whole project (PRJ-045).
        """
        validated_data.pop("template", None)
        validated_data.pop("changed_at", None)  # PRJ-113: judged by ``ProjectViewSet.update`` before
        if "parent" in validated_data and validated_data.pop("parent") != instance.parent:
            raise serializers.ValidationError({"parent": _("A project cannot be moved into another one.")})
        discount = {
            name: validated_data.pop(name) for name in services.OVERALL_DISCOUNT_FIELDS if name in validated_data
        }
        # The discount may be refused after the rest was saved (no right to prices, both given): both or neither.
        with transaction.atomic():
            project = services.update_project(instance, **validated_data)
            if discount:
                self._set_overall_discount(project, discount)
        return project

    def _set_overall_discount(self, project: Project, given: dict[str, Any]) -> None:
        """PRJ-123: the overall discount through the service; naming one of the two clears the other."""
        percent = given.get("overall_discount_percent")
        amount = given.get("overall_discount_amount")
        if "overall_discount_percent" not in given:
            percent = None if amount else project.overall_discount_percent
        if "overall_discount_amount" not in given:
            amount = None if percent else project.overall_discount_amount
        services.set_overall_discount(
            project, rights=request_rights(self.context["request"]), percent=percent, amount=amount
        )


class GroupSerializer(RestrictedFieldsMixin, serializers.ModelSerializer):
    """A group of a project (PRJ-014, PRJ-039, PRJ-040).

    PRJ-037: ``parent`` is the group it stands in (``null`` at the top level).
    Setting it moves the group with its lines and subgroups to the end of
    that group's subgroups; ``POST …/groups/{id}/move`` also chooses the
    place. ``position`` counts among the groups with the same parent. A
    group cannot stand in itself or in one of its subgroups, and groups are
    nested at most three levels deep; such a request is answered with a
    validation error on ``parent``.
    """

    parent = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.all(),
        required=False,
        allow_null=True,
        help_text="The group this group stands in; null: the top level (PRJ-037).",
    )
    alternative_to = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.all(),
        required=False,
        allow_null=True,
        help_text=(
            "PRJ-083: for kind alternative, the group it could replace – not itself, not a group above or below "
            "it, not an alternative itself. Naming one makes the group an alternative; another kind clears it."
        ),
    )

    warnings = serializers.SerializerMethodField()

    restricted_fields = {
        "discount_percent": SpecialRight.PRICES,
        "discount_amount": SpecialRight.PRICES,
        "flat_price": SpecialRight.PRICES,
    }

    class Meta:
        model = Group
        fields = [
            "id",
            "project",
            "name",
            "description",
            "parent",
            "position",
            "kind",
            "alternative_to",
            "discount_percent",
            "discount_amount",
            "flat_price",
            "rental_days",
            "warnings",
        ]
        read_only_fields = ["project", "position"]

    def get_warnings(self, group: Group) -> list[str]:
        """After a write, whether the maximum discounts of the group's lines cut its discount or flat price.

        The group keeps what was sent; the sums take the maximum (PER-026). Empty when the group is only read.
        """
        return self.context.get("warnings", {}).get(group.pk, [])

    def validate_parent(self, parent: Group | None) -> Group | None:
        """The parent group must belong to the same project (PRJ-037)."""
        project = self.context.get("project")
        if parent is not None and project is not None and parent.project_id != project.pk:
            raise serializers.ValidationError(_("The parent group belongs to a different project."))
        return parent

    def validate_alternative_to(self, target: Group | None) -> Group | None:
        """The group an alternative could replace must belong to the same project (PRJ-083)."""
        project = self.context.get("project")
        if target is not None and project is not None and target.project_id != project.pk:
            raise serializers.ValidationError(_("The group belongs to a different project."))
        return target


class MaterialLineSerializer(RestrictedFieldsMixin, serializers.ModelSerializer):
    """A material line (PRJ-010) with its availability and – with the price right – its price.

    ``product`` can only be set when the line is created. Price fields are
    prefilled from the product (PRJ-015); sending them needs the price right.

    ``preferred_model`` and ``preferred_item`` name specific material the
    planner would like to have (PRJ-064). They are an internal hint; choosing
    an item sets its model as well.

    ``variant`` makes the line optional or an alternative (PRJ-075): priced,
    but not added up, not invoiced, not packed, reserved only softly.
    ``alternative_to`` names the line an alternative could replace (PRJ-083);
    naming one makes the line an alternative, another ``variant`` clears it.
    Older lines marked "alternative" may name none.
    ``list_price`` is the price of the product when the line took it over
    (PRJ-072); see ``/projects/{id}/old-prices``.
    ``is_customer_material`` marks the customer's own material (PRJ-096):
    planned only in projects of its owner, taken along and never charged –
    no price, no discount, never optional or an alternative.
    """

    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(), required=False, allow_null=True)
    is_customer_material = serializers.BooleanField(read_only=True)
    is_text = serializers.BooleanField(
        required=False,
        help_text=(
            "True creates a text line – a heading or a remark that only carries ``title`` (and ``note`` for "
            "a longer text), without product, quantity, price or availability; ``group`` is allowed. It is printed "
            "on offers, order confirmations, invoices and the price overview and appears nowhere else. Can only be "
            "set when the line is created."
        ),
    )
    alternative_to = serializers.PrimaryKeyRelatedField(
        queryset=MaterialLine.objects.all(),
        required=False,
        allow_null=True,
        help_text=(
            "PRJ-083: the line of the same project an alternative could replace – not itself, not a subrental "
            "that covers a shortage, not an alternative itself."
        ),
    )
    title = serializers.CharField(required=False, max_length=200)
    start = serializers.DateTimeField(required=False)
    end = serializers.DateTimeField(required=False)
    kind = serializers.CharField(read_only=True)
    preferred_items = serializers.PrimaryKeyRelatedField(
        many=True,
        source="wished_items",
        queryset=MaterialItem.objects.all(),
        required=False,
        help_text=(
            "All items the line wishes for, the first one is ``preferred_item``. A line stands for "
            "``quantity`` × ``pieces_per_product`` pieces; each wished item covers one of them, the rest comes from "
            "any item of the product. More wished items than pieces are refused. The price does not depend on it. "
            "Wins over ``preferred_item`` when both are sent."
        ),
    )
    availability = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    warnings = serializers.SerializerMethodField()

    restricted_fields = {
        "unit_price": SpecialRight.PRICES,
        "discount_percent": SpecialRight.PRICES,
        "manual_scale_factor": SpecialRight.PRICES,
        "surcharge_percent": SpecialRight.PRICES,
        "billing_mode": SpecialRight.PRICES,
        "tax_rate": SpecialRight.PRICES,
        "price": SpecialRight.PRICES,
        "list_price": SpecialRight.PRICES,
        "purchase_price": SpecialRight.PURCHASE_PRICES,
    }

    class Meta:
        model = MaterialLine
        fields = [
            "id",
            "project",
            "group",
            "product",
            "kind",
            "is_customer_material",
            "is_text",
            "title",
            "quantity",
            "unit",
            "start",
            "end",
            "position",
            "note",
            "is_sale",
            "billing_mode",
            "unit_price",
            "discount_percent",
            "tax_rate",
            "hours",
            "quantity_is_estimate",
            "rental_days",
            "scale_version",
            "manual_scale_factor",
            "surcharge_percent",
            "supplier",
            "purchase_price",
            "subrental_status",
            "picked_up_at_supplier",  # PRJ-097
            "covers_line",
            "covers_product",
            "preferred_model",
            "preferred_item",
            "preferred_items",
            "variant",
            "alternative_to",
            "taken_over_from",
            "list_price",
            "stock_removed_quantity",
            "availability",
            "price",
            "warnings",
        ]
        read_only_fields = [
            "project",
            "position",
            "scale_version",
            "covers_line",
            "covers_product",
            "stock_removed_quantity",
            "list_price",
        ]
        extra_kwargs = {"tax_rate": {"required": False}, "unit": {"required": False}}

    def get_availability(self, line: MaterialLine) -> dict[str, Any] | None:
        """The verdict calculated for the whole project, or for this line after a write.

        AUT-032: ``null`` without the special right to see the availability of material.
        """
        if not sees_availability(self.context):
            return None
        known = self.context.get("availability", {})
        verdict = known.get(line.pk)
        return availability_document(verdict) if verdict is not None else None

    def get_warnings(self, line: MaterialLine) -> list[str]:
        """What the caller is told about the values just saved, e.g. a discount above the maximum (PER-026).

        Empty when the line is only read. The values stay as sent; the price takes the maximum, see ``price``.
        """
        return self.context.get("warnings", {}).get(line.pk, [])

    def get_price(self, line: MaterialLine) -> dict[str, Any] | None:
        """The calculated price of the line."""
        prices: ProjectPrices | None = self.context.get("prices")
        if prices is None or line.pk not in prices.by_line_id:
            return None
        return price_document(prices.by_line_id[line.pk])

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """A group must belong to the project of the line."""
        project: Project = self.context["project"]
        group = attrs.get("group")
        if group is not None and group.project_id != project.pk:
            raise serializers.ValidationError({"group": _("The group belongs to a different project.")})
        target = attrs.get("alternative_to")
        if target is not None and target.project_id != project.pk:
            raise serializers.ValidationError({"alternative_to": _("The line belongs to a different project.")})
        if self.instance is not None and "product" in attrs and attrs["product"] != self.instance.product:
            raise serializers.ValidationError(
                {"product": _("The product of a line cannot be changed. Delete the line and add a new one.")}
            )
        if self.instance is not None and "is_text" in attrs and attrs["is_text"] != self.instance.is_text:
            raise serializers.ValidationError({"is_text": _("A line cannot become a text line or stop being one.")})
        if attrs.get("is_text") and not attrs.get("title"):
            raise serializers.ValidationError({"title": _("A text line needs a text.")})
        source = attrs.get("taken_over_from")
        if source is not None:
            # PRJ-060, PRJ-049: only from a part whose planning the caller may read.
            request = self.context["request"]
            if access_level(request_rights(request), request.user, source.project) < ProjectAccess.READ:
                raise serializers.ValidationError({"taken_over_from": _("You may not read that line.")})
        return attrs

    def create(self, validated_data: dict[str, Any]) -> MaterialLine:
        """Add the line; the availability check runs in the same protected step (VFG-007)."""
        project: Project = self.context["project"]
        if validated_data.pop("is_text", False):
            # A text line takes only its text, a longer text and its group.
            ignored = set(validated_data) - {"title", "note", "group"}
            if ignored:
                raise serializers.ValidationError(
                    {name: _("A text line has no such field.") for name in sorted(ignored)}
                )
            result = services.add_text_line(
                project,
                title=validated_data["title"],
                note=validated_data.get("note", ""),
                group=validated_data.get("group"),
            )
            self._remember_result(result)
            return result.line
        validated_data.pop("is_text", None)
        self._wished_items(validated_data)
        result = services.add_line(
            project,
            rights=self.rights,
            product=validated_data.pop("product", None),
            quantity=validated_data.pop("quantity", Decimal("1")),
            group=validated_data.pop("group", None),
            start=validated_data.pop("start", None),
            end=validated_data.pop("end", None),
            **validated_data,
        )
        self._remember_result(result)
        return result.line

    def update(self, instance: MaterialLine, validated_data: dict[str, Any]) -> MaterialLine:
        """Change the line and return its new availability."""
        validated_data.pop("product", None)
        validated_data.pop("is_text", None)  # checked in ``validate``: it never changes
        self._wished_items(validated_data)
        result = services.update_line(instance, rights=self.rights, **validated_data)
        self._remember_result(result)
        return result.line

    @staticmethod
    def _wished_items(validated_data: dict[str, Any]) -> None:
        """Hand the wished items to the service under its name ``preferred_items`` (piece share)."""
        if "wished_items" in validated_data:
            validated_data["preferred_items"] = validated_data.pop("wished_items")

    def _remember_result(self, result: services.LineResult) -> None:
        """Keep availability, price and warnings of a saved line for the answer."""
        self.context.setdefault("availability", {})[result.line.pk] = result.availability
        self.context.setdefault("warnings", {})[result.line.pk] = result.warnings
        if self.rights.has(SpecialRight.PRICES):
            self.context["prices"] = compute_project_prices(result.line.project)


class SurchargeTargetSerializer(serializers.Serializer):
    """One thing a percentage surcharge refers to (PRD-031)."""

    type = serializers.ChoiceField(choices=["line", "group", "personnel", "project"])
    id = serializers.IntegerField(required=False, allow_null=True)


class ProjectFilter(django_filters.FilterSet):
    """Filters of the project list (PRJ-027): status, period, customer, project manager."""

    status = django_filters.MultipleChoiceFilter(choices=ProjectStatus.choices)
    since = django_filters.IsoDateTimeFilter(field_name="end", lookup_expr="gte", label="ends at or after")
    until = django_filters.IsoDateTimeFilter(field_name="start", lookup_expr="lte", label="starts at or before")
    q = django_filters.CharFilter(method="filter_search")
    customer = django_filters.NumberFilter(method="filter_customer")
    # PRJ-105: projects with a follow-up.
    follow_up = django_filters.ChoiceFilter(
        choices=FOLLOW_UP_CHOICES,
        method="filter_follow_up",
        label="follow-ups: due (the day has come), mine (for the caller, any day) or any",
    )
    # ADM-012, ADM-014: a number as printed on a document – of today (2026-0042) or former (P-2026-0042).
    number = django_filters.CharFilter(
        method="filter_number",
        label="project number, of today or the former one; the case is ignored",
    )

    class Meta:
        model = Project
        # PRJ-090: ``kind=service_case`` lists the service cases; without ``kind`` only projects are listed.
        fields = ["manager", "parent", "is_internal", "kind"]

    def _knows_customers(self) -> bool:
        """AUT-023: who sees projects only through assignments does not learn whose they are.

        Not even by asking: a search or a filter that looked at the customer
        would answer the question with the length of the list.
        """
        rights = request_rights(self.request)
        return rights.level_everywhere(Module.PROJECTS) >= Level.READ or rights.can_read(Module.CUSTOMERS)

    def filter_search(self, queryset: Any, name: str, value: str) -> Any:
        """Search in number (ADM-012, ADM-014: also the former one), name, venue and the customer name.

        PRJ-122: the customer name in every role, as the name shows in every role.
        """
        condition = (
            project_numbers.matching(value)
            | Q(name__icontains=value)
            | Q(venue__icontains=value)
            | Q(customer__name__icontains=value)  # PRJ-122: the name shows in every role
        )
        return queryset.filter(condition)

    def filter_number(self, queryset: Any, name: str, value: str) -> Any:
        """ADM-012, ADM-014: the project with this number; the number of today wins over a former one."""
        found = project_numbers.project_by_number(value, queryset)
        return queryset.filter(pk=found.pk) if found is not None else queryset.none()

    def filter_customer(self, queryset: Any, name: str, value: Any) -> Any:
        """The projects of one customer."""
        return queryset.filter(customer_id=value) if self._knows_customers() else queryset.none()

    def filter_follow_up(self, queryset: Any, name: str, value: str) -> Any:
        """PRJ-105: follow-ups ``due`` (the day has come), ``mine`` (for the caller) or ``any``; in every status."""
        return filter_follow_ups(queryset, value, self.request.user) if self._knows_customers() else queryset.none()


# --- Views ----------------------------------------------------------------------


def _subrental_status(value: Any) -> str:
    """The status of a new subrental as sent (PRJ-084); PRJ-101: "open" when none is sent."""
    if value in (None, ""):
        return SubrentalStatus.OPEN
    if value not in SubrentalStatus.values:
        raise ValidationError({"status": _("Unknown status.")})
    return str(value)


def planning_document(
    planning: Planning,
    context: dict[str, Any],
    *,
    with_prices: bool,
    with_costs: bool,
    with_personnel_costs: bool = False,
) -> dict[str, Any]:
    """The whole planning of a project as one document: groups, lines, crew, totals."""
    context = {
        **context,
        "project": planning.project,
        "availability": {line.line.pk: line.availability for line in planning.all_lines},
        "prices": planning.prices if with_prices else None,
    }

    def lines(planned: list[PlannedLine]) -> Any:
        return MaterialLineSerializer([line.line for line in planned], many=True, context=context).data

    document: dict[str, Any] = {
        "groups": [
            {**GroupSerializer(group.group, context=context).data, "lines": lines(group.lines)}
            for group in planning.groups
        ],
        "without_group": lines(planning.ungrouped),
        "surcharges": lines(planning.surcharges),
        "crew": [
            crew_document(planned.price, planned.warnings, with_prices=with_prices, with_costs=with_personnel_costs)
            for planned in planning.crew
        ],
        # LOG-001, LOG-009: the vehicle bookings with their trips; costs with the purchase price right.
        "logistics": [
            vehicle_line_document(planned.price, planned.warnings, with_prices=with_prices, with_costs=with_costs)
            for planned in planning.logistics
        ],
        # AUT-032: ``null`` without the special right to see the availability of material.
        "shortage_total": planning.shortage_total if sees_availability(context) else None,
    }
    if with_prices:
        document["totals"] = totals_document(
            planning.prices, with_costs=with_costs, with_personnel_costs=with_personnel_costs
        )
    return document


class DuplicateSerializer(serializers.Serializer):
    """The new project made from an existing one (PRJ-029)."""

    name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    with_material = serializers.BooleanField(default=True)
    with_crew = serializers.BooleanField(default=False)
    with_logistics = serializers.BooleanField(
        default=False, help_text="Copy the vehicle bookings and the vehicles on the trips (LOG-001)."
    )
    # PRJ-029, PRJ-044: whole projects and their parts.
    with_subprojects = serializers.BooleanField(
        default=True, help_text="For a whole project: copy its subprojects as well (not the cancelled ones)."
    )
    as_subproject = serializers.BooleanField(
        default=True,
        help_text=(
            "For a subproject: make the copy a new subproject of the same whole project (needs the right to "
            "edit that); false makes it a project of its own."
        ),
    )


class FollowUpBody(serializers.Serializer):
    """What ``PUT /projects/{id}/follow-up`` takes (PRJ-105, PRJ-109)."""

    follow_up_on = serializers.DateField()
    # PRJ-109: optional time of the reminder; left out or ``null``: none, notified in the morning of the day.
    follow_up_at = serializers.TimeField(required=False, allow_null=True)
    follow_up_user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True), required=False, allow_null=True
    )
    follow_up_note = serializers.CharField(required=False, allow_blank=True, max_length=250)


#: (R3-2) What the overall-discount columns and the target amounts can hold (exclusive upper bounds).
_OVERALL_DISCOUNT_LIMITS = {
    "percent": Decimal("1000"),
    "amount": Decimal("10") ** 8,
    "target_net": Decimal("10") ** 10,
    "target_gross": Decimal("10") ** 10,
}


class ProjectViewSet(ModuleViewSet):
    """``/projects`` – projects with status, planning, totals and history (PRJ)."""

    module = Module.PROJECTS
    # API-016: ``venue_site`` for ``venue_label``.
    queryset = Project.objects.select_related(
        "customer", "contact", "manager", "follow_up_user", "venue_site"
    ).prefetch_related("subprojects")
    serializer_class = ProjectSerializer
    filterset_class = ProjectFilter
    ordering_fields = ["start", "end", "number", "name", "status", "follow_up_on"]
    # PRJ-105: removing a follow-up is a change of the project, not a deletion.
    action_levels = {"history": Level.READ, "follow_up": Level.WRITE}
    #: AUT-033 (PRJ-108): reading a service case and its follow-up are part of working on it (``projects.case_work``).
    permission_classes = (CaseWorkPermission,)
    case_work_actions = ("retrieve", "follow_up")

    def get_queryset(self) -> Any:
        """Only the projects the caller may see (AUT-016, acceptance scenario 6)."""
        projects = visible_projects(self.rights, self.request.user, super().get_queryset())
        if self.action == "list" and not self.request.query_params.get("kind"):
            # PRJ-090: the list is that of the projects; ``kind=service_case`` lists the cases.
            projects = projects.exclude(kind=ProjectKind.SERVICE_CASE)
        return projects

    def get_object(self) -> Project:
        """Load one project and check what the caller may do in it (AUT-025).

        Reading the project itself needs the deployment view; every other
        reading operation (planning, totals, history …) needs "read"; every
        change needs "edit". A project the caller may not see at all is "not
        found", like one that does not exist.
        """
        project = super().get_object()
        access = access_level(self.rights, self.request.user, project)
        if self.action == "retrieve":
            needed = ProjectAccess.DEPLOYMENT
        elif self.request.method in SAFE_METHODS:
            needed = ProjectAccess.READ
        else:
            needed = ProjectAccess.EDIT
        if access < needed:
            # AUT-033 (PRJ-108): the follow-up of a service case for whoever works on it.
            note_case_work(project, self.rights, self.request.user)
            if not (self.action in self.case_work_actions and project.may_work_on_case):
                raise PermissionDenied
        note_access(project, access)
        return project

    def perform_destroy(self, instance: Project) -> None:
        """Only projects that never left the planning stage can be deleted."""
        services.delete_project(instance)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Change the project (``PUT``, ``PATCH``); closed projects are locked (PRJ-009).

        PRJ-113: with ``changed_at`` – when the change was made, ISO
        8601 with its time zone – each field sent counts only if that moment
        is later than the last change of its key in ``field_changed_at``; at
        the same moment the server wins, a moment in the future counts as
        now. Compared and written under the write lock (API-010). The fields
        that do not count are left out; the others are checked and saved (a
        ``PUT`` with fields left out as a ``PATCH`` of the rest; ``changed_at``
        is write-only, so a ``GET`` sent back carries none). The answer is the project as it is now with
        ``applied``: the keys taken over. Without ``changed_at`` everything is
        as before.
        """
        body = body_of(request)
        moment = field_changes.parse_moment(body.get("changed_at"))
        if moment is None:
            return super().update(request, *args, **kwargs)
        project = self.get_object()
        with field_changes.locked(project) as (current, now):
            moment = min(moment, now)
            sent = body.copy()
            sent.pop("changed_at", None)
            writable = {name for name, field in self.get_serializer(current).fields.items() if not field.read_only}
            moments = {
                field_changes.KEY_OF[name]: moment for name in sent if name in writable and name in field_changes.KEY_OF
            }
            applied, older = field_changes.judge(current, moments)
            dropped = [name for name in sent if field_changes.KEY_OF.get(name) in older]
            for name in dropped:
                sent.pop(name)
            if any(name in writable for name in sent):
                # A ``PUT`` from which nothing was dropped is checked as complete, as before.
                partial = bool(kwargs.get("partial")) or bool(dropped)
                serializer = self.get_serializer(current, data=sent, partial=partial)
                serializer.is_valid(raise_exception=True)
                taken = {key: moments[key] for key in applied}
                with field_changes.changes_at(current, taken):
                    self.perform_update(serializer)
                field_changes.note(current, taken)
            answer = {**self.get_serializer(current).data, "applied": applied}
        return Response(answer)

    def _require_prices(self) -> None:
        if not self.rights.has(SpecialRight.PRICES):
            raise PermissionDenied

    @extend_schema(
        request=inline_serializer(
            "InvoiceStatus",
            {"invoice_status": serializers.ChoiceField(choices=["", "issued", "not_needed"])},
        ),
        responses=ProjectSerializer,
    )
    @action(detail=True, methods=["post"], url_path="invoice-status")
    def invoice_status(self, request: Request, pk: str | None = None) -> Response:
        """Tick "Rechnung gestellt" (``issued``), mark "Keine Rechnung" (``not_needed``) or open it again (DOK-015).

        Needs the right to edit the project and to see prices – also on a closed
        project: the mark is bookkeeping, not a change of the project. A part,
        an internal or a cancelled project gets no invoice of its own (400).
        """
        from rentalars.documents.invoice_reminders import set_invoice_status

        if not self.rights.has(SpecialRight.PRICES):
            raise PermissionDenied
        project = self.get_object()
        set_invoice_status(project, str(body_of(request).get("invoice_status", "")), user=request.user)
        return Response(self.get_serializer(project).data)

    @extend_schema(
        request=inline_serializer(
            "OverallDiscountBody",
            {
                "percent": serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True),
                "amount": serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True),
                "target_net": serializers.DecimalField(
                    max_digits=12, decimal_places=2, required=False, allow_null=True
                ),
                "target_gross": serializers.DecimalField(
                    max_digits=12, decimal_places=2, required=False, allow_null=True
                ),
                "dry_run": serializers.BooleanField(required=False),
            },
        ),
        responses=inline_serializer(
            "OverallDiscountResult",
            {
                "overall_discount_percent": serializers.DecimalField(max_digits=9, decimal_places=6, allow_null=True),
                "overall_discount_amount": serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True),
                "net_before_overall_discount": serializers.DecimalField(max_digits=12, decimal_places=2),
                "gross_before_overall_discount": serializers.DecimalField(max_digits=12, decimal_places=2),
                "overall_discount": serializers.DecimalField(max_digits=12, decimal_places=2),
                "net_total": serializers.DecimalField(max_digits=12, decimal_places=2),
                "gross_total": serializers.DecimalField(max_digits=12, decimal_places=2),
                "target": serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True),
                "exact": serializers.BooleanField(),
                "saved": serializers.BooleanField(),
            },
        ),
    )
    @action(detail=True, methods=["post"], url_path="overall-discount")
    def overall_discount(self, request: Request, pk: str | None = None) -> Response:
        """Set the overall discount of the project – by percent, amount or a target amount (PRJ-123).

        Give exactly one of ``percent``, ``amount`` (the discount as before), ``target_net`` or ``target_gross``:
        the total the project should come to after the discount, net or gross. For a target the percentage that gets
        there is calculated (up to six decimals) and stored; it is not calculated again when the project changes
        later. None of the four (or all ``null``) removes the discount. ``dry_run`` only calculates and saves nothing.

        The answer carries the stored percentage or amount, the sums before and after and ``exact``: whether the
        total is the target to the cent (where the rounding of the tax makes a gross target impossible to the cent,
        the nearest amount is stored). 400 for a target above the total without discount, both targets, or a project
        without a total. Needs the right to edit the project and to see prices.
        """
        from rentalars.projects.overall_target import figures_of, prices_without_discount, solve
        from rentalars.projects.pricing import totals_after_overall_discount

        if not self.rights.has(SpecialRight.PRICES):
            raise PermissionDenied
        project = self.get_object()
        # (R3-9) a dry run answers what the real call would answer: not for a closed project.
        services.ensure_editable(project)
        services.ensure_plannable(project)
        body = body_of(request)
        given = {
            name: body.get(name)
            for name in ("percent", "amount", "target_net", "target_gross")
            if body.get(name) not in (None, "")
        }
        if len(given) > 1:
            raise serializers.ValidationError(
                {"detail": _("Use only one of: percentage, amount, target amount net, target amount gross.")}
            )
        values: dict[str, Decimal] = {}
        for name, text in given.items():
            try:
                values[name] = Decimal(str(text).replace(",", "."))
            except InvalidOperation as error:
                raise serializers.ValidationError({name: _("A valid number is required.")}) from error
            # (R3-2) NaN, Infinity and numbers beyond what the columns hold are no numbers here.
            if not values[name].is_finite() or abs(values[name]) >= _OVERALL_DISCOUNT_LIMITS[name]:
                raise serializers.ValidationError({name: _("A valid number is required.")})
            if values[name] < 0:
                raise serializers.ValidationError({name: _("Ensure this value is greater than or equal to 0.")})
        if values.get("percent", Decimal("0")) > 100:
            raise serializers.ValidationError({"percent": _("Ensure this value is less than or equal to 100.")})
        dry_run = str(body.get("dry_run", "")).lower() in {"true", "1", "yes", "on"}
        prices = prices_without_discount(project)
        target: Decimal | None = None
        exact = True
        if "target_net" in values or "target_gross" in values:
            result = solve(project, net=values.get("target_net"), gross=values.get("target_gross"), prices=prices)
            percent, amount, target, exact = result.percent, None, result.target, result.is_exact
            if not dry_run:
                services.set_overall_discount_to_target(
                    project, rights=self.rights, net=values.get("target_net"), gross=values.get("target_gross")
                )
        else:
            percent, amount = values.get("percent") or None, values.get("amount") or None
            if not dry_run:
                services.set_overall_discount(project, rights=self.rights, percent=percent, amount=amount)
        discount, net_total, gross_total = figures_of(prices, percent=percent, amount=amount)
        return Response(
            {
                "overall_discount_percent": percent,
                "overall_discount_amount": amount,
                "net_before_overall_discount": prices.net_before_overall_discount,
                "gross_before_overall_discount": totals_after_overall_discount(prices, Decimal("0"))[1],
                "overall_discount": discount,
                "net_total": net_total,
                "gross_total": gross_total,
                "target": target,
                "exact": exact,
                "saved": not dry_run,
            }
        )

    @extend_schema(
        request=inline_serializer(
            "StatusChange",
            {
                "status": serializers.ChoiceField(choices=ProjectStatus.choices),
                "with_subprojects": serializers.BooleanField(required=False),
                # PRJ-113
                "changed_at": serializers.DateTimeField(
                    required=False,
                    help_text="When the status was changed, ISO 8601 with time zone: it counts only if later than "
                    "field_changed_at.status; the answer then has `applied`. 409 with the project as it is now: "
                    "the change is no longer allowed.",
                ),
            },
        ),
        responses={200: ProjectSerializer, 409: ProjectSerializer},
    )
    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request: Request, pk: str | None = None) -> Response:
        """Move the project to another status (PRJ-008); the change is logged (PRJ-009).

        ``with_subprojects`` moves the parts of a whole project along, where
        the step is allowed for them (PRJ-044). Cancelling a whole project
        always cancels its parts.

        PRJ-113: with ``changed_at`` the change counts only if it is
        later than the last change of the status (``field_changed_at.status``);
        a step no longer allowed when the change arrives is answered with 409
        and the project as it is now.
        """
        project = self.get_object()
        body = body_of(request)
        new_status = str(body.get("status", ""))
        with_parts = str(body.get("with_subprojects", "")).lower() in {"true", "1", "yes", "on"}
        moment = field_changes.parse_moment(body.get("changed_at"))
        if moment is not None:
            return self._status_at(project, new_status, with_parts, moment)
        if with_parts:
            services.change_family_status(project, new_status, rights=self.rights)
        else:
            services.change_status(project, new_status, rights=self.rights)
        return Response(self.get_serializer(project).data)

    def _status_at(self, project: Project, new_status: str, with_parts: bool, moment: Any) -> Response:
        """PRJ-113: a change of the status made at ``moment`` – the younger change wins."""
        with field_changes.locked(project) as (current, now):
            moment = min(moment, now)
            if new_status not in ProjectStatus.values:
                raise ValidationError({"status": _("Unknown status.")})
            if current.is_service_case:
                raise ValidationError(_("A service case has statuses of its own: open, in progress, done."))
            applied, _older = field_changes.judge(current, {"status": moment})
            if applied:
                try:
                    with transaction.atomic(), field_changes.changes_at(current, {"status": moment}):
                        if with_parts:
                            services.change_family_status(current, new_status, rights=self.rights)
                        else:
                            services.change_status(current, new_status, rights=self.rights)
                except ValidationError as error:
                    # Not allowed any more from the status the project has now: 409 with the project as it is.
                    current.refresh_from_db()
                    refusal = {
                        "code": "status_not_allowed",
                        "message": error.messages[0],
                        "fields": {"status": [{"code": "not_allowed", "message": text} for text in error.messages]},
                    }
                    answer = {**self.get_serializer(current).data, "applied": [], "error": refusal}
                    return Response(answer, status=status.HTTP_409_CONFLICT)
                field_changes.note(current, {"status": moment})
            return Response({**self.get_serializer(current).data, "applied": applied})

    @extend_schema(
        methods=["PUT"],
        request=inline_serializer(
            "FollowUp",
            {
                "follow_up_on": serializers.DateField(),
                "follow_up_at": serializers.TimeField(required=False, allow_null=True),
                "follow_up_user": serializers.IntegerField(required=False, allow_null=True),
                "follow_up_note": serializers.CharField(required=False, allow_blank=True, max_length=250),
                # PRJ-113
                "changed_at": serializers.DateTimeField(
                    required=False,
                    help_text="When the follow-up was set, ISO 8601 with time zone: it counts only if later than "
                    "field_changed_at.follow_up; the answer then has `applied`.",
                ),
            },
        ),
        responses=ProjectSerializer,
    )
    @extend_schema(
        methods=["DELETE"],
        request=None,
        responses=ProjectSerializer,
        parameters=[
            OpenApiParameter(
                "changed_at",
                OpenApiTypes.DATETIME,
                description="PRJ-113: when the follow-up was removed (ISO 8601 with time zone, `+` encoded as "
                "%2B); it counts only if later than field_changed_at.follow_up. Also accepted in the body.",
            )
        ],
    )
    @action(detail=True, methods=["put", "delete"], url_path="follow-up")
    def follow_up(self, request: Request, pk: str | None = None) -> Response:
        """Set the follow-up of the project (``PUT``) or remove it – done (``DELETE``) (PRJ-105).

        ``follow_up_on`` is the day, ``follow_up_at`` an optional time
        (PRJ-109), ``follow_up_user`` the user it is for – the caller when left
        out; that user must be able to open the project – and
        ``follow_up_note`` what is to be done. On that day – from that time –
        the user is notified as the user's notification settings say. Possible in every
        status, a closed project too; needs the right to edit the project.

        PRJ-113: with ``changed_at`` (body, or the address for
        ``DELETE``) the change counts only if it is later than the last change
        of the follow-up (``field_changed_at.follow_up``); the answer then
        carries ``applied``.
        """
        from rentalars.projects.follow_up import clear_follow_up, set_follow_up

        project = self.get_object()
        sent = body_of(request)
        moment = field_changes.parse_moment(request.query_params.get("changed_at") or sent.get("changed_at"))
        values: dict[str, Any] = {}
        if request.method != "DELETE":
            body = FollowUpBody(data=sent)
            body.is_valid(raise_exception=True)
            values = body.validated_data
        if moment is not None:
            with field_changes.locked(project) as (current, now):
                moment = min(moment, now)
                applied, _older = field_changes.judge(current, {"follow_up": moment})
                if applied:
                    with field_changes.changes_at(current, {"follow_up": moment}):
                        if request.method == "DELETE":
                            clear_follow_up(current)
                        else:
                            set_follow_up(
                                current,
                                on=values["follow_up_on"],
                                at=values.get("follow_up_at"),
                                note=values.get("follow_up_note", ""),
                                user=values.get("follow_up_user"),
                                by=request.user,
                            )
                    field_changes.note(current, {"follow_up": moment})
                return Response({**self.get_serializer(current).data, "applied": applied})
        if request.method == "DELETE":
            clear_follow_up(project)
            return Response(self.get_serializer(project).data)
        set_follow_up(
            project,
            on=values["follow_up_on"],
            at=values.get("follow_up_at"),
            note=values.get("follow_up_note", ""),
            user=values.get("follow_up_user"),
            by=request.user,
        )
        return Response(self.get_serializer(project).data)

    @extend_schema(responses={200: inline_serializer("Family", {"whole": serializers.IntegerField()})})
    @action(detail=True)
    def family(self, request: Request, pk: str | None = None) -> Response:
        """The whole project with the figures of all its parts and their sum (PRJ-046, PRJ-047).

        Works from the whole project and from every part. Parts the caller
        may not read are left out (``hidden`` counts them); amounts only with
        the price right.
        """
        from rentalars.projects.family import build_family

        family = build_family(self.get_object(), rights=self.rights, user=request.user)
        with_prices = self.rights.has(SpecialRight.PRICES)
        # AUT-032: shortages only with the special right to see the availability of material (else ``null``, []).
        with_availability = self.rights.has(SpecialRight.AVAILABILITY)

        def figures(part: Any) -> dict[str, Any]:
            data = {
                "project": part.project.pk,
                "number": part.project.number,
                "name": part.project.name,
                "status": part.project.status,
                "start": part.project.start,
                "end": part.project.end,
                "own_lines_of_whole": part.is_whole,
                "lines": part.lines,
                "pieces": part.pieces,
                "taken_over_lines": part.takeovers,
                "crew_lines": part.crew_lines,
                "open_places": part.open_places,
                "planned_hours": part.hours,
                "shortage": part.shortage if with_availability else None,
            }
            if with_prices:
                data["net_total"] = part.net_total
                data["gross_total"] = part.gross_total
            return data

        total = figures(family.total)
        for name in ("project", "number", "name", "status", "start", "end", "own_lines_of_whole"):
            total.pop(name)
        return Response(
            {
                "whole": family.whole.pk,
                "parts": [figures(part) for part in family.parts],
                "hidden": family.hidden,
                "total": total,
                "shortages_between_parts": [
                    {
                        "project": shortage.project.pk,
                        "line": shortage.planned.line.pk,
                        "title": shortage.planned.line.title,
                        "missing": shortage.missing,
                        "held_by_other_parts": shortage.held_by_others,
                    }
                    for shortage in (family.shortages if with_availability else [])
                ],
            }
        )

    @extend_schema(request=DuplicateSerializer, responses={201: ProjectSerializer})
    @action(detail=True, methods=["post"])
    def duplicate(self, request: Request, pk: str | None = None) -> Response:
        """Make a new project from this one for another period (PRJ-029).

        Phases move along; material is copied unless ``with_material`` is
        false; the crew comes as open places with ``with_crew``. Reading the
        source is enough – unless the caller only sees assigned projects.

        A whole project comes with its subprojects unless ``with_subprojects``
        is false; a subproject becomes a new subproject of the same whole
        project – which needs the right to edit that – unless
        ``as_subproject`` is false (PRJ-044).
        """
        source = project_for(request, pk or 0, ProjectAccess.READ, queryset=Project.objects.select_related("parent"))
        if self.rights.is_limited_to_assigned_projects(Module.PROJECTS) and source.access < ProjectAccess.EDIT:
            raise PermissionDenied
        serializer = DuplicateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        as_subproject = bool(source.parent_id) and values["as_subproject"]
        if as_subproject and access_level(self.rights, request.user, source.parent) < ProjectAccess.EDIT:
            raise serializers.ValidationError({"as_subproject": _("You may not add subprojects to this project.")})
        copy = duplicate_project(
            source,
            name=values.get("name", ""),
            start=values["start"],
            end=values["end"],
            with_material=values["with_material"],
            with_crew=values["with_crew"],
            with_logistics=values["with_logistics"],
            with_subprojects=values["with_subprojects"],
            as_subproject=as_subproject,
            rights=self.rights,
            user=request.user,
        )
        if self.rights.is_limited_to_assigned_projects(Module.PROJECTS):
            ProjectMembership.objects.get_or_create(
                project=copy, user=request.user, defaults={"level": ProjectAccessLevel.EDIT}
            )
        return Response(self.get_serializer(copy).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses={200: inline_serializer("Planning", {"shortage_total": serializers.IntegerField()})})
    @action(detail=True)
    def planning(self, request: Request, pk: str | None = None) -> Response:
        """Groups and lines with availability and, with the price right, prices and totals."""
        planning = build_planning(self.get_object())
        return Response(
            planning_document(
                planning,
                self.get_serializer_context(),
                with_prices=self.rights.has(SpecialRight.PRICES),
                with_costs=self.rights.has(SpecialRight.PURCHASE_PRICES),
                with_personnel_costs=self.rights.has(SpecialRight.PERSONNEL_COSTS),
            )
        )

    @extend_schema(responses={200: inline_serializer("Totals", {"net_total": serializers.DecimalField(12, 2)})})
    @action(detail=True)
    def totals(self, request: Request, pk: str | None = None) -> Response:
        """The sums of the project (PRJ-024). Needs the price right (AUT-019)."""
        self._require_prices()
        planning = build_planning(self.get_object())
        return Response(
            totals_document(
                planning.prices,
                with_costs=self.rights.has(SpecialRight.PURCHASE_PRICES),
                with_personnel_costs=self.rights.has(SpecialRight.PERSONNEL_COSTS),
            )
        )

    @extend_schema(
        parameters=[
            OpenApiParameter("detail", str, enum=["groups", "lines"], description="Level of detail (PRJ-036)"),
            OpenApiParameter("crew", str, enum=["phases"], description="Personnel by phase and job function (PRJ-088)"),
        ],
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    @action(detail=True, url_path="price-overview/pdf")
    def price_overview_pdf(self, request: Request, pk: str | None = None) -> HttpResponse:
        """The price overview as PDF (DOK-009); ``?detail=groups`` without the lines.

        PRJ-046: a whole project with the parts the caller may read, each as a block, and the sum of all.
        PRJ-088: ``?crew=phases`` breaks the personnel down by phase and job function.
        """
        from rentalars.projects.price_pdf import render_price_overview_pdf

        self._require_prices()
        pdf = render_price_overview_pdf(
            self.get_object(),
            with_lines=request.query_params.get("detail", "lines") != "groups",
            rights=self.rights,
            user=request.user,
            crew_by_phase=request.query_params.get("crew") == "phases",
        )
        return HttpResponse(pdf, content_type="application/pdf")

    @extend_schema(
        parameters=[
            OpenApiParameter("detail", str, enum=["groups", "lines"], description="Level of detail (PRJ-036)"),
            OpenApiParameter("crew", str, enum=["phases"], description="Personnel by phase and job function (PRJ-088)"),
        ],
        responses={(200, "text/csv"): OpenApiTypes.STR},
    )
    @action(detail=True, url_path="price-overview/csv")
    def price_overview_csv(self, request: Request, pk: str | None = None) -> HttpResponse:
        """The price overview as CSV for a spreadsheet program (DOK-009, IMP-005); PRJ-046, PRJ-088 like the PDF."""
        from rentalars.projects.price_pdf import render_price_overview_csv

        self._require_prices()
        text = render_price_overview_csv(
            self.get_object(),
            with_lines=request.query_params.get("detail", "lines") != "groups",
            rights=self.rights,
            user=request.user,
            crew_by_phase=request.query_params.get("crew") == "phases",
        )
        return HttpResponse(text, content_type="text/csv; charset=utf-8")

    @extend_schema(
        parameters=[
            OpenApiParameter("detail", str, enum=["groups", "lines"], description="Level of detail (PRJ-036)"),
            OpenApiParameter(
                "crew", str, enum=["phases"], description="With costs of the personnel by phase (PRJ-088, AUT-019)"
            ),
        ],
        responses={
            200: inline_serializer(
                "PriceOverview",
                {
                    "net_total": serializers.DecimalField(12, 2),
                    "parts": serializers.ListField(child=serializers.DictField()),
                    "family_totals": serializers.DictField(),
                },
            )
        },
    )
    @action(detail=True, url_path="price-overview")
    def price_overview(self, request: Request, pk: str | None = None) -> Response:
        """The price overview as a basis for external quotes (DOK-009, PRJ-035).

        ``?detail=groups`` delivers groups with subtotals only, ``?detail=lines``
        (default) includes every line. Every block carries ``summary``: what it
        contains, in one line, for quotes without lines (PRJ-066). Needs the
        price right.

        PRJ-046: the top level holds the project's own groups and totals as
        always. ``parts`` lists, for a whole project, every part that is not
        cancelled and that the caller may read – number, name, period, its
        groups and totals; ``hidden_parts`` counts those left out for want of
        access, ``cancelled_parts`` names the cancelled ones. ``family_totals``
        is the sum of everything included: net per tax rate added up, the tax
        calculated on that sum. A part names its whole project in
        ``part_of``. A line taken over from another part (PRJ-060) names it in
        ``taken_over_from``; it is not charged.

        PRJ-088: the block ``personnel`` carries ``by_phase`` – per phase
        (``phase`` is ``null`` for the lines without phase) one entry per job
        function with ``places``, ``hours``, ``days``, ``flat`` places and
        ``amount``, and the phase's ``subtotal``. With ``?crew=phases`` and
        the right for personnel costs also ``cost`` and ``margin``, as on the
        page; otherwise the overview names no cost. A line billed per day
        (PER-029) says ``unit: "day"`` and gives its days as ``quantity``.
        """
        from rentalars.projects.family_prices import family_prices

        self._require_prices()
        project = self.get_object()
        overview = family_prices(project, rights=self.rights, user=request.user)
        with_lines = request.query_params.get("detail", "lines") != "groups"
        # PRJ-088, AUT-019: costs only in the breakdown asked for with ``crew=phases``, and only with their right –
        # the usual overview names no cost of anybody (acceptance scenario 15).
        with_personnel_costs = request.query_params.get("crew") == "phases" and self.rights.has(
            SpecialRight.PERSONNEL_COSTS
        )

        def line_rows(planned: list[PlannedLine]) -> list[dict[str, Any]]:
            return [
                {
                    "article_number": line.line.product.article_number if line.line.product else "",
                    "title": line.line.title,
                    "quantity": line.line.quantity,
                    "unit": line.line.unit.abbreviation if line.line.unit else "",
                    "rental_days": line.price.rental_days,
                    "scale_factor": line.price.scale_factor,
                    "unit_price": line.line.unit_price,
                    "discount_percent": line.price.discount_percent,  # PER-026: as it applies
                    "amount": line.price.amount,
                    "is_estimate": line.price.is_estimate,
                    "variant": line.line.variant,  # PRJ-075: "" counts; optional and alternative do not
                    "is_customer_material": line.price.is_customer_material,  # PRJ-096: taken along, not charged
                    "is_text": line.line.is_text,  # A row of text; quantity, price and amount are 0
                    "note": line.line.note if line.line.is_text else "",
                    "alternative_to": line.line.alternative_to_id,  # PRJ-083: the line an alternative replaces
                    # PRJ-060: pieces of another part, charged there.
                    "taken_over_from": {
                        "line": line.line.taken_over_from_id,
                        "project": line.line.taken_over_from.project.number,
                    }
                    if line.line.taken_over_from_id
                    else None,
                }
                for line in planned
                if not line.line.is_covering_subrental
            ]

        def blocks_of(planning: Planning) -> dict[str, Any]:
            """Groups, lines without group, surcharges, personnel and totals of one project."""
            groups = []
            for group in planning.groups:
                entry: dict[str, Any] = {
                    # PRJ-037: in the order of the planning; a parent's subtotal includes its subgroups.
                    "group": group.group.pk,
                    "parent": group.group.parent_id,
                    "path": group.path,
                    "name": group.group.name,
                    "description": group.group.description,
                    "kind": group.group.kind,
                    "alternative_to": group.group.alternative_to_id,  # PRJ-083
                    "subtotal": group.prices.subtotal,
                    "discount": group.prices.discount,
                    "summary": group.summary,
                }
                if with_lines:
                    entry["lines"] = line_rows(group.lines)
                groups.append(entry)
            prices = planning.prices
            blocks: dict[str, Any] = {
                "groups": groups,
                "without_group": {"subtotal": prices.ungrouped_total, "summary": planning.ungrouped_summary},
                "surcharges": {"subtotal": prices.surcharges_total, "summary": planning.surcharges_summary},
                "personnel": {
                    "subtotal": prices.personnel_total,
                    "summary": planning.crew_summary,
                    "by_phase": crew_by_phase_rows(planning.crew_by_phase, with_costs=with_personnel_costs),
                },
                "totals": totals_document(prices, with_costs=False),
            }
            if with_lines:
                blocks["without_group"]["lines"] = line_rows(planning.ungrouped)
                blocks["surcharges"]["lines"] = line_rows(planning.surcharges)
                # PRJ-038: personnel is a block of its own – with what the customer
                # pays, and without the hourly rate of anybody (AUT-019).
                blocks["personnel"]["lines"] = [
                    {
                        "article_number": price.line.service_product.article_number
                        if price.line.service_product
                        else "",
                        "title": price.line.title,
                        "quantity": price.quantity,
                        "unit": {"hour": "h", "day": "day", "flat": ""}[price.unit_kind],
                        "unit_price": price.line.unit_price,
                        # PER-035: the hours beyond the limit of their day and their price; 0 and null without.
                        "hours_above_limit": price.hours_above_limit,
                        "unit_price_above_limit": price.unit_price_above_limit,
                        # PER-009: the surcharges for night, Sunday and holidays in the amount, by kind.
                        "time_surcharges": [part.as_dict() for part in price.time_surcharges],
                        "time_surcharge_amount": price.time_surcharge_amount,
                        "discount_percent": price.discount_percent,  # PER-026: as it applies
                        "amount": price.amount,
                        "is_estimate": price.is_estimate,
                        "from": price.line.start,
                        "to": price.line.end,
                    }
                    for price in prices.crew
                ]
            # LOG-009, LOG-011: the logistics as a block of its own after material and personnel.
            blocks["logistics"] = {"subtotal": prices.logistics_total, "summary": planning.logistics_summary}
            if with_lines:
                blocks["logistics"]["lines"] = [
                    {
                        "article_number": price.line.product.article_number,
                        "title": price.line.label,
                        "quantity": price.quantity,
                        "unit": price.unit_kind,
                        "unit_price": price.unit_price,
                        "days": price.days,
                        "km": price.km_total if price.days is None else None,
                        "surcharge_amount": price.surcharge_total,
                        "discount_percent": price.discount_percent,
                        "amount": price.amount,
                        "is_estimate": price.is_estimate,
                        "from": price.line.start,
                        "to": price.line.end,
                    }
                    for price in prices.logistics
                ]
            return blocks

        totals = overview.totals
        document: dict[str, Any] = {
            "internal_working_document": True,
            "project": {"number": project.number, "name": project.name, "customer": project.customer_name},
            **blocks_of(overview.own.planning),
            "part_of": {"project": project.parent_id, "number": project.parent.number, "name": project.parent.name}
            if project.parent_id
            else None,
            "parts": [
                {
                    "project": block.project.pk,
                    "number": block.project.number,
                    "name": block.project.name,
                    "status": block.project.status,
                    "start": block.project.start,
                    "end": block.project.end,
                    "venue": block.project.venue_label,
                    "heading": block.heading,
                    **blocks_of(block.planning),
                }
                for block in overview.parts
            ],
            "hidden_parts": overview.hidden,
            "cancelled_parts": [part.number for part in overview.cancelled],
            "family_totals": {
                "projects": [member.number for member in overview.projects],
                "net_total": totals.net_total,
                "tax": [
                    {
                        "tax_rate": tax.tax_rate.pk,
                        "name": tax.tax_rate.name,
                        "rate": tax.tax_rate.rate,
                        "net": tax.net,
                        "tax": tax.tax,
                    }
                    for tax in totals.tax_lines
                ],
                "tax_total": totals.tax_total,
                "gross_total": totals.gross_total,
                "optional_total": totals.optional_total,
                "optional_lines_total": totals.optional_lines_total,
                "alternative_lines_total": totals.alternative_lines_total,
                "has_estimates": totals.has_estimates,
            },
        }
        return Response(document)

    @extend_schema(
        responses={200: inline_serializer("ProjectHistory", {"timestamp": serializers.DateTimeField()}, many=True)}
    )
    @action(detail=True)
    def history(self, request: Request, pk: str | None = None) -> Response:
        """Who changed what and when in this project, its groups and lines (PRJ-032).

        EML-055 (API-002): as the page – the subjects of mails and notes only for who may read them.
        """
        from rentalars.mail.history import hide_unreadable
        from rentalars.mail.locks import correspondence_of

        project = self.get_object()
        entries = AuditLogEntry.for_object(project)
        page = self.paginate_queryset(entries)
        history = hide_unreadable(describe(list(page), self.rights), correspondence_of(request, project), project)
        rows = [
            {
                "timestamp": item.entry.timestamp,
                "user": item.actor,
                "object_type": item.object_label,
                "object": item.object_name,
                "action": item.entry.action,
                "summary": item.summary,
                "changes": [
                    {"field": change.name, "label": change.label, "old": change.old, "new": change.new}
                    for change in item.changes
                ],
            }
            for item in history
        ]
        return self.get_paginated_response(rows)

    @extend_schema(
        responses={200: inline_serializer("ProjectShortage", {"shortage": serializers.IntegerField()}, many=True)}
    )
    @action(detail=True)
    def shortages(self, request: Request, pk: str | None = None) -> Response:
        """The open shortages of the project, each with its subrental suggestion (PRJ-054).

        Customer material (PRJ-096) has no suggestion (``null``): nobody else can supply it.
        AUT-032: 403 without the special right to see the availability of material.
        """
        if not self.rights.has(SpecialRight.AVAILABILITY):
            raise PermissionDenied
        planning = build_planning(self.get_object())
        rows = []
        for line in planning.short_lines:
            for shortage in line.shortages:
                rows.append(
                    {
                        "line": line.line.pk,
                        "line_title": line.line.title,
                        "product": shortage.product.pk,
                        "article_number": shortage.product.article_number,
                        "product_name": shortage.product.name,
                        "shortage": shortage.quantity,
                        "from": line.line.start,
                        "to": line.line.end,
                        # PRJ-096: customer material cannot be subrented – no suggestion.
                        "suggestion": None
                        if shortage.product.owner_id
                        else {
                            "line": line.line.pk,
                            "product": shortage.product.pk,
                            "quantity": shortage.quantity,
                        },
                    }
                )
        return Response(rows)

    @extend_schema(
        request=inline_serializer(
            "AcceptSubrental",
            {
                "line": serializers.IntegerField(),
                "product": serializers.IntegerField(),
                "quantity": serializers.IntegerField(min_value=1),
                "supplier": serializers.IntegerField(required=False),
                "purchase_price": serializers.DecimalField(10, 2, required=False),
                "status": serializers.ChoiceField(choices=SubrentalStatus.choices, required=False),
            },
        ),
        responses={201: MaterialLineSerializer},
    )
    @action(detail=True, methods=["post"], url_path="shortages/accept")
    def accept_subrental(self, request: Request, pk: str | None = None) -> Response:
        """Accept a subrental suggestion: creates the linked subrental line (PRJ-054).

        PRJ-084: like the dialog of the planning, it takes supplier, quantity,
        purchase price and ``status`` – no rental price; the subrental is not
        charged, the customer pays the line it covers. PRJ-101: the status is
        "open" unless sent; any other status needs the supplier.
        """
        project = self.get_object()
        line = get_object_or_404(project.material_lines.select_related("product"), pk=body_of(request).get("line"))
        short_product = get_object_or_404(Product, pk=body_of(request).get("product"))
        supplier_id = body_of(request).get("supplier")
        purchase_price = body_of(request).get("purchase_price")
        subrental = services.accept_subrental_suggestion(
            line,
            short_product,
            int(body_of(request).get("quantity") or 0),
            rights=self.rights,
            supplier=get_object_or_404(Supplier, pk=supplier_id) if supplier_id else None,
            purchase_price=Decimal(str(purchase_price)) if purchase_price not in (None, "") else None,
            status=_subrental_status(body_of(request).get("status")),
        )
        context = {**self.get_serializer_context(), "project": project}
        return Response(MaterialLineSerializer(subrental, context=context).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=None, responses={200: inline_serializer("RefreshScales", {"changed_lines": serializers.IntegerField()})}
    )
    @action(detail=True, methods=["post"], url_path="refresh-scales")
    def refresh_scales(self, request: Request, pk: str | None = None) -> Response:
        """Switch the lines of the project to the current state of the rental scales (PRD-037)."""
        self._require_prices()
        return Response({"changed_lines": services.refresh_scale_versions(self.get_object())})

    @extend_schema(
        request=inline_serializer(
            "Arrangement",
            {"layout": serializers.ListField(child=serializers.DictField())},
        ),
        responses={204: None},
    )
    @action(detail=True, methods=["post"])
    def arrange(self, request: Request, pk: str | None = None) -> Response:
        """Store the order of lines and their groups after sorting (PRJ-014).

        Body: ``{"layout": [{"group": 3, "lines": [12, 10, 11]}, {"group": null, "lines": [9]}]}``
        """
        project = self.get_object()
        layout = body_of(request).get("layout")
        if not isinstance(layout, list):
            raise ValidationError({"layout": _("Send the layout as a list of groups with their line IDs.")})
        parsed: list[tuple[int | None, list[int]]] = []
        for entry in layout:
            if not isinstance(entry, dict) or not isinstance(entry.get("lines"), list):
                raise ValidationError({"layout": _("Send the layout as a list of groups with their line IDs.")})
            parsed.append((entry.get("group"), [int(line_id) for line_id in entry["lines"]]))
        services.arrange_lines(project, parsed)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectChildViewSet(ModuleViewSet):
    """Base for resources that live below a project, at ``/projects/{project_pk}/…``."""

    module = Module.PROJECTS
    pagination_class = None
    #: AUT-033 (PRJ-108): the actions that are part of working on a service case – the person responsible and the
    #: people taking part may do them in their case whatever their roles say (``projects.case_work``).
    case_work_actions: tuple[str, ...] = ()
    case_work_kwarg = "project_pk"
    permission_classes = (CaseWorkPermission,)

    def access_needed(self, usual: ProjectAccess) -> ProjectAccess:
        """The access to the project an operation needs; ``usual`` is "read" to read and "edit" to change."""
        return usual

    def get_project(self) -> Project:
        """The project named in the address, for a caller who may do this in it (AUT-016, AUT-025)."""
        if not hasattr(self, "_project"):
            usual = ProjectAccess.READ if self.request.method in SAFE_METHODS else ProjectAccess.EDIT
            self._project = project_for(
                self.request,
                self.kwargs["project_pk"],
                self.access_needed(usual),
                case_work=getattr(self, "action", None) in self.case_work_actions,
            )
        return self._project

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        """Check the access to the project before anything else happens (AUT-016).

        Done here and not in the single operations, so that no operation –
        deleting included – can forget it.
        """
        super().initial(request, *args, **kwargs)
        if "project_pk" in self.kwargs:
            self.get_project()

    def get_serializer_context(self) -> dict[str, Any]:
        """Give serializers the project."""
        context = super().get_serializer_context()
        if "project_pk" in self.kwargs:
            context["project"] = self.get_project()
        return context


class GroupViewSet(ProjectChildViewSet):
    """``/projects/{id}/groups`` (PRJ-014)."""

    queryset = Group.objects.none()
    serializer_class = GroupSerializer

    def get_queryset(self) -> Any:
        """The groups of the project; positions count among the groups with the same parent (PRJ-037)."""
        return Group.objects.filter(project_id=self.kwargs.get("project_pk"))

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """The groups of the project in the order of the planning: a group, its subgroups, the next (PRJ-037)."""
        groups = GroupTree(self.filter_queryset(self.get_queryset())).ordered
        return Response(self.get_serializer(groups, many=True).data)

    def perform_create(self, serializer: Any) -> None:
        """Add the group at the end of the project."""
        serializer.instance = services.add_group(self.get_project(), rights=self.rights, **serializer.validated_data)
        self._warn(serializer, serializer.validated_data)

    def perform_update(self, serializer: Any) -> None:
        """Change the group."""
        serializer.instance = services.update_group(
            serializer.instance, rights=self.rights, **serializer.validated_data
        )
        self._warn(serializer, serializer.validated_data)

    def _warn(self, serializer: Any, values: dict[str, Any]) -> None:
        """If a discount or flat price was sent, say whether the maximum discounts of the lines cut it."""
        if {"discount_percent", "discount_amount", "flat_price"} & set(values):
            warning = group_discount_warning(serializer.instance)
            if warning:
                serializer.context.setdefault("warnings", {})[serializer.instance.pk] = [warning]

    def perform_destroy(self, instance: Group) -> None:
        """Delete the group; ``?lines=delete`` removes its lines too, otherwise they are kept.

        PRJ-037: kept lines and subgroups move up one level into the group's
        place; ``?lines=delete`` deletes the subgroups and their lines as well.
        """
        services.delete_group(instance, keep_lines=self.request.query_params.get("lines") != "delete")

    @extend_schema(
        request=inline_serializer(
            "MoveGroup",
            {
                "parent": serializers.IntegerField(
                    allow_null=True, help_text="The group to move into; null: the top level."
                ),
                "position": serializers.IntegerField(
                    required=False, min_value=1, help_text="Place among the groups there, 1 = first; default: last."
                ),
            },
        ),
        responses={200: GroupSerializer},
    )
    @action(detail=True, methods=["post"])
    def move(self, request: Request, project_pk: str | None = None, pk: str | None = None) -> Response:
        """Move the group with its lines and subgroups into another group or onto the top level (PRJ-037)."""
        group = self.get_object()
        body = body_of(request)
        if "parent" not in body:
            raise ValidationError({"parent": _("Name the group to move into, or null for the top level.")})
        parent = None
        if body["parent"] is not None:
            try:
                parent = self.get_project().groups.filter(pk=int(body["parent"])).first()
            except (TypeError, ValueError):
                parent = None
            if parent is None:
                raise ValidationError({"parent": _("Choose one of the groups of this project.")})
        position = body.get("position")
        if position is not None and (isinstance(position, bool) or not str(position).isdigit() or int(position) < 1):
            raise ValidationError({"position": _("Give the place as a number from 1.")})
        moved = services.move_group(group, parent=parent, position=int(position) if position is not None else None)
        return Response(self.get_serializer(moved).data)

    @extend_schema(
        request=inline_serializer("CopyGroup", {"target_project": serializers.IntegerField(required=False)}),
        responses={201: GroupSerializer},
    )
    @action(detail=True, methods=["post"])
    def copy(self, request: Request, project_pk: str | None = None, pk: str | None = None) -> Response:
        """Copy the group with its lines and subgroups, into the same or another project (PRJ-041, PRJ-037)."""
        group = self.get_object()
        target_id = body_of(request).get("target_project")
        target = project_for(request, target_id, ProjectAccess.EDIT) if target_id else group.project
        copied = services.copy_group(group, target, rights=self.rights)
        return Response(self.get_serializer(copied).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=inline_serializer("GroupOrder", {"groups": serializers.ListField(child=serializers.IntegerField())}),
        responses={204: None},
    )
    @action(detail=False, methods=["post"])
    def reorder(self, request: Request, project_pk: str | None = None) -> Response:
        """Put the groups into the given order."""
        group_ids = body_of(request).get("groups")
        if not isinstance(group_ids, list):
            raise ValidationError({"groups": _("Send the group IDs in the wanted order.")})
        services.reorder_groups(self.get_project(), [int(group_id) for group_id in group_ids])
        return Response(status=status.HTTP_204_NO_CONTENT)


class MaterialLineViewSet(ProjectChildViewSet):
    """``/projects/{id}/material-lines`` (PRJ-010)."""

    queryset = MaterialLine.objects.none()
    serializer_class = MaterialLineSerializer

    def get_queryset(self) -> Any:
        """The lines of the project."""
        return (
            MaterialLine.objects.filter(project_id=self.kwargs.get("project_pk"))
            .select_related("product", "product__category", "tax_rate", "unit", "supplier", "preferred_item")
            .prefetch_related("further_preferred_items")
        )

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """All lines with availability; prices are added for callers with the price right."""
        planning = build_planning(self.get_project())
        context = {
            **self.get_serializer_context(),
            "availability": {line.line.pk: line.availability for line in planning.all_lines},
            "prices": planning.prices if self.rights.has(SpecialRight.PRICES) else None,
        }
        lines = [line.line for line in planning.all_lines]
        # (R3-9) The wished items of all lines in one query (the serializer names the first one).
        prefetch_related_objects([line for line in lines if line.preferred_item_id], "preferred_item")
        return Response(MaterialLineSerializer(lines, many=True, context=context).data)

    def perform_destroy(self, instance: MaterialLine) -> None:
        """Delete the line unless its material is already out."""
        services.delete_line(instance)

    @extend_schema(methods=["get"], responses=SurchargeTargetSerializer(many=True))
    @extend_schema(
        methods=["put"], request=SurchargeTargetSerializer(many=True), responses=SurchargeTargetSerializer(many=True)
    )
    @action(detail=True, methods=["get", "put"], url_path="surcharge-targets")
    def surcharge_targets(self, request: Request, project_pk: str | None = None, pk: str | None = None) -> Response:
        """Read or define what a percentage surcharge refers to (PRD-031, PRD-039)."""
        line = self.get_object()
        if request.method == "PUT":
            serializer = SurchargeTargetSerializer(data=request.data, many=True)
            serializer.is_valid(raise_exception=True)
            services.set_surcharge_targets(line, list(serializer.validated_data))
        return Response(
            [
                {"type": target.target_type, "id": target.target_line_id or target.target_group_id}
                for target in line.surcharge_targets.all()
            ]
        )


class ShortageOverviewView(ModuleAPIView):
    """``GET /shortages`` – all open shortages of running and coming projects (PRJ-057)."""

    module = Module.PROJECTS
    schema_tag = "availability"

    @extend_schema(
        responses={200: inline_serializer("OpenShortage", {"shortage": serializers.IntegerField()}, many=True)}
    )
    def get(self, request: Request) -> Response:
        """List every uncovered shortage with its project and period.

        AUT-032, AUT-031: 403 without the special right to see the availability of material, and for a role with
        the overview only (the role "Crew").
        """
        if not (self.rights.has(SpecialRight.AVAILABILITY) and self.rights.reads_planning):
            raise PermissionDenied
        return Response(
            [
                {
                    "project": shortage.project.pk,
                    "project_number": shortage.project.number,
                    "project_name": shortage.project.name,
                    # PRJ-044, PRJ-047: the whole project of a part, and what its other parts hold.
                    "parent": shortage.project.parent_id,
                    "held_by_other_parts": shortage.held_by_other_parts,
                    "line": shortage.line.pk,
                    "product": shortage.product.pk,
                    "article_number": shortage.product.article_number,
                    "product_name": shortage.product.name,
                    "shortage": shortage.quantity,
                    "from": shortage.line.start,
                    "to": shortage.line.end,
                }
                for shortage in open_shortages(projects=readable_projects(self.rights, request.user))
            ]
        )


class SubrentalOverviewView(ModuleAPIView):
    """``GET /subrentals`` – all subrentals with supplier, period and status (PRJ-057)."""

    module = Module.PROJECTS
    schema_tag = "availability"

    @extend_schema(
        responses={200: inline_serializer("Subrental", {"quantity": serializers.DecimalField(10, 2)}, many=True)}
    )
    def get(self, request: Request) -> Response:
        """List the subrental lines of all projects that are not finished."""
        with_costs = self.rights.has(SpecialRight.PURCHASE_PRICES)
        rows = []
        for line in subrental_lines(readable_projects(self.rights, request.user)):
            row = {
                "line": line.pk,
                "project": line.project_id,
                "project_number": line.project.number,
                "project_name": line.project.name,
                "title": line.title,
                "quantity": line.quantity,
                "supplier": line.supplier_id,
                "supplier_name": line.supplier.name if line.supplier else None,
                "from": line.start,
                "to": line.end,
                "status": line.subrental_status,
                "covers_line": line.covers_line_id,
            }
            if with_costs:
                row["purchase_price"] = line.purchase_price
            rows.append(row)
        return Response(rows)


# --- Crew lines (PRJ-019 ff.) ----------------------------------------------------------------


class CrewLineSerializer(serializers.Serializer):
    """Input for a crew line: who, as what, when (PRJ-019 to PRJ-023, PRJ-051, PRJ-061).

    ``person`` may be empty: an open place to be filled later (PRJ-020);
    ``count`` creates several of them at once. Price fields need the price
    right, ``hourly_rate``, ``daily_rate`` and ``cost_flat_rate`` the right
    for personnel costs (AUT-019). What is delivered back is described by
    ``crew_document``.

    ``phase`` – a phase of the project (PRJ-080); given without
    ``start`` and ``end``, the line takes the phase's period. ``billing``
    ``"day"`` charges per day (PER-029); ``days`` sets the days, empty for
    the calendar days of the period.
    """

    job_function = serializers.PrimaryKeyRelatedField(queryset=JobFunction.objects.all())
    person = serializers.PrimaryKeyRelatedField(queryset=Person.objects.all(), required=False, allow_null=True)
    count = serializers.IntegerField(required=False, min_value=1, max_value=crew.MAX_LINES_PER_STEP)
    phase = serializers.PrimaryKeyRelatedField(
        queryset=ProjectPhase.objects.all(),
        required=False,
        allow_null=True,
        help_text="A phase of this project (PRJ-080); without start and end the line takes its period.",
    )
    start = serializers.DateTimeField(required=False)
    end = serializers.DateTimeField(required=False)
    planned_hours = serializers.DecimalField(max_digits=7, decimal_places=2, min_value=Decimal("0"), required=False)
    days = serializers.IntegerField(
        min_value=1,
        max_value=999,
        required=False,
        allow_null=True,
        help_text="Days charged per day (PER-029); empty: the calendar days of the period.",
    )
    meeting_point = serializers.CharField(max_length=200, required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True)
    title = serializers.CharField(max_length=200, required=False)
    billing = serializers.ChoiceField(choices=["plan", "flat", "effort", "day"], required=False)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"), required=False)
    discount_percent = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=Decimal("0"),
        max_value=Decimal("100"),
        required=False,
        help_text="Needs the price right. The job function may allow less (PER-026); the price then takes its maximum.",
    )
    hourly_rate = serializers.DecimalField(
        max_digits=8, decimal_places=2, min_value=Decimal("0"), required=False, allow_null=True
    )
    daily_rate = serializers.DecimalField(
        max_digits=8,
        decimal_places=2,
        min_value=Decimal("0"),
        required=False,
        allow_null=True,
        help_text="Internal cost per day (PER-029); needs the right for personnel costs.",
    )
    cost_flat_rate = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0"), required=False, allow_null=True
    )
    # PER-035: hour tiers per day; taken from the service product when the line is planned.
    hours_limit = serializers.DecimalField(
        max_digits=4,
        decimal_places=2,
        min_value=Decimal("0.25"),
        max_value=Decimal("23.75"),
        required=False,
        allow_null=True,
        help_text="Hours of one day beyond this cost unit_price_above_limit (PER-035); needs the price right.",
    )
    unit_price_above_limit = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0"),
        required=False,
        allow_null=True,
        help_text="Price per hour beyond the limit of a day (PER-035); needs the price right.",
    )
    hourly_rate_above_limit = serializers.DecimalField(
        max_digits=8,
        decimal_places=2,
        min_value=Decimal("0"),
        required=False,
        allow_null=True,
        help_text="Internal cost of an hour beyond the limit (PER-035); needs the right for personnel costs.",
    )
    # PER-009: surcharges for night, Sunday and holidays; a new line takes them from the settings and the product.
    time_surcharges_on_price = serializers.BooleanField(
        required=False,
        help_text="Surcharges for night, Sunday and holidays on the price (PER-009); needs the price right.",
    )
    time_surcharges_on_cost = serializers.BooleanField(
        required=False,
        help_text="Surcharges for night, Sunday and holidays on the costs (PER-009); needs the right for personnel "
        "costs.",
    )
    # LOG-008: who travels with which motor vehicle of the project, and who drives it.
    vehicle_line = serializers.PrimaryKeyRelatedField(
        queryset=VehicleLine.objects.all(),
        required=False,
        allow_null=True,
        help_text="A motor vehicle booked in this project (LOG-008).",
    )
    is_driver = serializers.BooleanField(required=False, help_text="Drives the vehicle (LOG-008).")
    # PER-041: planned without request – request_status "firm"; false takes it back ("not asked").
    firm = serializers.BooleanField(
        required=False,
        help_text="Plan the person firmly, without request; the person is told. False takes it back.",
    )


class CrewLineViewSet(ProjectChildViewSet):
    """``/projects/{id}/crew-lines`` – the people planned on a project (PRJ-019 ff.).

    Reading needs read access to the project. Changing needs edit access –
    or read access together with write access to personnel, which is how
    personnel planning works (catalogue chapter 4).
    """

    queryset = CrewLine.objects.none()
    serializer_class = CrewLineSerializer
    # Personnel planning reads projects and still plans their crew. So the module
    # level asked here is "read" for every operation; who may change is decided
    # per project in :meth:`_plan`.
    action_levels = dict.fromkeys(
        ("create", "update", "partial_update", "destroy", "unassigned_times", "ask", "answer"), Level.READ
    )

    def access_needed(self, usual: ProjectAccess) -> ProjectAccess:
        """Reading the project is enough; whether the caller may plan crew is checked in :meth:`_plan`.

        Answering a request works with the deployment view: the person
        planned answers for themselves (PER-016).
        """
        if self.action == "answer":
            return ProjectAccess.DEPLOYMENT
        return ProjectAccess.READ

    def get_queryset(self) -> Any:
        """The crew lines of the project in the address."""
        return CrewLine.objects.filter(project_id=self.kwargs.get("project_pk")).select_related(
            "job_function", "person", "service_product", "tax_rate", "phase"
        )

    def _plan(self) -> Project:
        """Return the project for a caller who may change its crew, or refuse."""
        project = self.get_project()
        if not may_plan_crew(self.rights, project.access):
            raise PermissionDenied
        return project

    def _document(self, line: CrewLine) -> dict[str, Any]:
        """One crew line with price, cost and warnings, as far as the caller may see them."""
        approved = crew.approved_hours_by_line(line.project).get(line.pk, crew.NO_TIMES)
        return crew_document(
            crew.price_crew_line(line, approved),
            crew.crew_warnings([line]).get(line.pk, []),
            with_prices=self.rights.has(SpecialRight.PRICES),
            with_costs=self.rights.has(SpecialRight.PERSONNEL_COSTS),
        )

    @extend_schema(responses={200: inline_serializer("CrewLineList", {"id": serializers.IntegerField()}, many=True)})
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """All crew lines of the project with prices, costs and warnings (PRJ-022)."""
        project = self.get_project()
        prices = crew.price_crew_lines(project)
        warnings = crew.crew_warnings([price.line for price in prices])
        return Response(
            [
                crew_document(
                    price,
                    warnings.get(price.line.pk, []),
                    with_prices=self.rights.has(SpecialRight.PRICES),
                    with_costs=self.rights.has(SpecialRight.PERSONNEL_COSTS),
                )
                for price in prices
            ]
        )

    @extend_schema(responses={200: inline_serializer("CrewLineDetail", {"id": serializers.IntegerField()})})
    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """One crew line."""
        return Response(self._document(self.get_object()))

    @extend_schema(responses={201: inline_serializer("CrewLineCreated", {"id": serializers.IntegerField()}, many=True)})
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Plan a person or open places; answers with the created lines (PRJ-019, PRJ-020)."""
        project = self._plan()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        lines = crew.add_crew_lines(
            project,
            rights=self.rights,
            job_function=values.pop("job_function"),
            person=values.pop("person", None),
            count=values.pop("count", 1),
            start=values.pop("start", None),
            end=values.pop("end", None),
            phase=values.pop("phase", None),
            **values,
        )
        documents = [self._document(line) for line in lines]
        if "discount_percent" in values:
            for line, document in zip(lines, documents, strict=True):
                if crew_discount_warning(line):  # See ``update``
                    document["warnings"] = [*document["warnings"], crew_discount_warning(line)]
        return Response(documents, status=status.HTTP_201_CREATED)

    @extend_schema(responses={200: inline_serializer("CrewLineUpdated", {"id": serializers.IntegerField()})})
    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Change a crew line; a new person brings their own hourly rate (PRJ-021)."""
        self._plan()
        line = self.get_object()
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        if "count" in values:
            raise ValidationError({"count": _("The number of places can only be given when planning.")})
        crew.update_crew_line(line, rights=self.rights, **values)
        document = self._document(line)
        if "discount_percent" in values and crew_discount_warning(line):
            # The discount above the maximum of the job function is cut – and said, next to the other warnings.
            document["warnings"] = [*document["warnings"], crew_discount_warning(line)]
        return Response(document)

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Change single fields of a crew line."""
        return self.update(request, *args, **kwargs)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Delete a crew line; times counted towards it stay in the project (ZEI-021)."""
        self._plan()
        crew.delete_crew_line(self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        request=None,
        responses={
            200: inline_serializer(
                "DeploymentAsked",
                {
                    "notified": serializers.BooleanField(),
                    "request_status": serializers.CharField(),
                    "mail_sent": serializers.BooleanField(allow_null=True),
                    "mail_reason": serializers.CharField(),
                },
            )
        },
    )
    def ask(self, request: Request, project_pk: str | None = None, pk: str | None = None) -> Response:
        """Ask the planned person whether they take the deployment (PER-016).

        ``notified`` is false if nobody could be told – no active account and
        no request mail with the buttons to answer by mail (PER-032): the line
        is marked "asked" all the same, and the planner enters the answer.

        PER-033: a line accepted or declined for its current times is not
        asked again (400) – only once its times changed. A request still
        waiting can be sent again.

        EML-048: ``mail_sent`` – ``true`` when the request (or its
        notification) went out by mail, ``false`` with ``mail_reason`` when no
        mail server is set up, ``null`` when no mail was due.
        """
        from rentalars.mail.server import mail_state, request_goes_by_mail

        self._plan()
        line = self.get_object()
        notified = crew.request_deployment(line, user=request.user)
        # EML-048: whether the mail of the request went out – ``null`` when none was due.
        mail = mail_state(sends_mail=request_goes_by_mail(line))
        return Response(
            {
                "notified": notified,
                "request_status": line.request_status,
                "mail_sent": mail["sent"],
                "mail_reason": mail["reason"],
            }
        )

    @extend_schema(
        request=inline_serializer(
            "DeploymentAnswer",
            {"accept": serializers.BooleanField(), "note": serializers.CharField(required=False, allow_blank=True)},
        ),
        responses={200: inline_serializer("DeploymentAnswered", {"request_status": serializers.CharField()})},
    )
    def answer(self, request: Request, project_pk: str | None = None, pk: str | None = None) -> Response:
        """Accept or decline a deployment: the person planned, or a planner for them (PER-016)."""
        project = self.get_project()
        line = self.get_object()
        viewer = person_of(request.user)
        is_own = viewer is not None and line.person_id == viewer.pk
        if not is_own and not may_plan_crew(self.rights, project.access):
            raise PermissionDenied
        body = body_of(request)
        accept = body.get("accept")
        if not isinstance(accept, bool):
            raise ValidationError({"accept": _("Send true to accept or false to decline.")})
        crew.answer_deployment(line, accept=accept, note=str(body.get("note", "")), user=request.user)
        # PER-042: the entry "available" made where the own calendar said "not available" – or null.
        marked = getattr(line, "marked_available", None)
        return Response(
            {
                "request_status": line.request_status,
                "answered_at": line.answered_at,
                "note": line.answer_note,
                "availability_marked": None
                if marked is None
                else {"id": marked.pk, "start": marked.start, "end": marked.end, "state": marked.state},
                "message": crew.available_text(line, own=is_own),
            }
        )

    @extend_schema(
        methods=["get"],
        responses={200: inline_serializer("LooseTimes", {"hours": serializers.DecimalField(8, 2)}, many=True)},
    )
    @extend_schema(
        methods=["post"],
        request=inline_serializer(
            "AssignTimes",
            {
                "person": serializers.IntegerField(),
                "job_function": serializers.IntegerField(),
                "crew_line": serializers.IntegerField(required=False, allow_null=True),
            },
        ),
        responses={200: inline_serializer("AssignTimesDone", {"id": serializers.IntegerField()})},
    )
    def unassigned_times(self, request: Request, project_pk: str | None = None) -> Response:
        """Approved times that count towards no crew line (ZEI-021).

        ``GET`` lists them, bundled by person and job function. ``POST``
        puts one bundle on a crew line (``crew_line``) or, without one, makes
        a new line of it.
        """
        if request.method == "POST":
            project = self._plan()
            body = body_of(request)
            person = get_object_or_404(Person, pk=body.get("person") or 0)
            job_function = get_object_or_404(JobFunction, pk=body.get("job_function") or 0)
            if body.get("crew_line"):
                line = get_object_or_404(project.crew_lines, pk=body["crew_line"])
                crew.assign_times(project, person, job_function, line)
            else:
                line = crew.adopt_times_as_line(project, person, job_function, rights=self.rights)
            return Response(self._document(line))
        return Response(
            [
                {
                    "person": bundle.person.pk,
                    "person_name": bundle.person.name,
                    "job_function": bundle.job_function.pk,
                    "job_function_name": bundle.job_function.name,
                    "hours": bundle.hours,
                    "time_entries": bundle.entry_ids,
                    "from": bundle.earliest,
                    "to": bundle.latest,
                }
                for bundle in crew.unassigned_times(self.get_project())
            ]
        )

    @extend_schema(
        responses={200: inline_serializer("PlannedActual", {"planned": serializers.DecimalField(8, 2)}, many=True)}
    )
    def planned_and_actual(self, request: Request, project_pk: str | None = None) -> Response:
        """Planned against recorded hours per job function and person (PRJ-026)."""
        return Response(
            [
                {
                    "job_function": row["job_function"].pk,
                    "job_function_name": row["job_function"].name,
                    "person": row["person"].pk if row["person"] else None,
                    "person_name": row["person"].name if row["person"] else None,
                    "planned_hours": row["planned"],
                    "approved_hours": row["approved"],
                    "pending_hours": row["pending"],
                }
                for row in crew.planned_and_actual(self.get_project())
            ]
        )


# --- Members and deployment view (AUT-016, AUT-025) -------------------------------------------


class MembershipSerializer(serializers.ModelSerializer):
    """A user's access to one project (AUT-016): ``deployment``, ``read`` or ``edit``; in a subproject also ``none``."""

    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(is_active=True))
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = ProjectMembership
        fields = ["id", "project", "user", "username", "level"]
        read_only_fields = ["project"]


class MembershipViewSet(ProjectChildViewSet):
    """``/projects/{id}/members`` – who is given access to this one project (AUT-016).

    A membership matters for users whose role covers "assigned projects
    only" (AUT-017). Reading the list needs read access to the project,
    changing it edit access.
    """

    queryset = ProjectMembership.objects.none()
    serializer_class = MembershipSerializer
    action_levels = {"destroy": Level.WRITE}

    def get_queryset(self) -> Any:
        """The members of the project in the address."""
        return (
            ProjectMembership.objects.filter(project_id=self.kwargs.get("project_pk"))
            .select_related("user")
            .order_by("user__username")
        )

    def perform_create(self, serializer: Any) -> None:
        """Add a member; a user who is one already gets the new level."""
        project = self.get_project()
        if serializer.validated_data.get("level") == ProjectAccessLevel.NONE and not project.parent_id:
            # PRJ-049: "no access" takes away what the whole project gives – only a part has that.
            raise serializers.ValidationError({"level": _("“No access” is only possible in a subproject.")})
        existing = project.memberships.filter(user=serializer.validated_data["user"]).first()
        if existing is not None:
            existing.level = serializer.validated_data.get("level", existing.level)
            existing.save()
            serializer.instance = existing
        else:
            serializer.save(project=project)


class DeploymentView(ModuleAPIView):
    """``GET /projects/{id}/deployment`` – the deployment view of a project (AUT-025).

    What crew and freelancers get of a project (AUT-023): time, place, the
    contact on site, their own crew lines, the colleagues with the contact
    data those released (PER-019). Nothing about prices or the customer.
    """

    module = Module.PROJECTS

    @extend_schema(responses={200: inline_serializer("Deployment", {"number": serializers.CharField()})})
    def get(self, request: Request, project_pk: int) -> Response:
        """Return the deployment view for the caller."""
        project = project_for(
            request,
            project_pk,
            ProjectAccess.DEPLOYMENT,
            queryset=Project.objects.select_related("contact", "manager", "venue_site"),
        )
        viewer = person_of(request.user)
        sees_all_contacts = project.access >= ProjectAccess.EDIT or self.rights.can_read(Module.PERSONNEL)
        show_own_rate = self.rights.has(SpecialRight.PERSONNEL_COSTS)
        if not show_own_rate:
            from rentalars.core.models import SystemSettings

            show_own_rate = SystemSettings.load().people_see_own_rates
        crew_rows = []
        from rentalars.projects.deployment import CREW_RELATED

        for line in project.crew_lines.select_related(*CREW_RELATED).order_by("start", "position", "id"):
            person = line.person
            is_self = viewer is not None and person is not None and person.pk == viewer.pk
            row: dict[str, Any] = {
                "crew_line": line.pk,
                "job_function": line.job_function.name,
                "person": person.name if person else None,
                "is_me": is_self,
                "start": line.start,
                "end": line.end,
                "meeting_point": line.meeting_point,
                # LOG-008: the vehicle the person travels with, and whether they drive it.
                "vehicle": line.vehicle_line.crew_label if line.vehicle_line_id else None,
                "is_driver": line.is_driver,
                "phone": person.phone if person and (sees_all_contacts or is_self or person.share_phone) else None,
                "email": person.email if person and (sees_all_contacts or is_self or person.share_email) else None,
            }
            if is_self:
                row["note"] = line.note
                row["planned_hours"] = line.planned_hours
                row["request_status"] = line.request_status
                row["answer_note"] = line.answer_note
                if show_own_rate:
                    row["hourly_rate"] = line.hourly_rate
                    row["daily_rate"] = line.daily_rate  # PER-029: the cost of a line billed per day
                    row["flat_rate"] = line.cost_flat_rate
            crew_rows.append(row)
        return Response(
            {
                "id": project.pk,
                "number": project.number,
                "name": project.name,
                "status": project.status,
                "start": project.start,
                "end": project.end,
                "event_start": project.event_start,
                "event_end": project.event_end,
                "venue": project.venue,
                "contact_on_site": (
                    {"name": project.contact.name, "phone": project.contact.phone} if project.contact_id else None
                ),
                "manager": str(project.manager) if project.manager_id else None,
                "can_see_packlist": module_level_in(self.rights, request.user, project, Module.PACKING) >= Level.READ,
                "crew": crew_rows,
                "phases": [
                    {
                        "kind": phase.kind,
                        "label": phase.label,
                        "start": phase.start,
                        "end": phase.end,
                        "place": phase.place,
                    }
                    for phase in project.phases.select_related("venue_site")
                ],
                "venue_site": (
                    {
                        "name": project.venue_site.name,
                        "address": project.venue_site.address_one_line,
                        "contact_name": project.venue_site.contact_name,
                        "contact_phone": project.venue_site.contact_phone,
                        "access_notes": project.venue_site.access_notes,
                        "power_notes": project.venue_site.power_notes,
                    }
                    if project.venue_site_id
                    else None
                ),
                "files": [
                    {
                        "id": item.pk,
                        "title": item.label,
                        "document_type": str(item.document_type or ""),
                        # PRJ-089: what a show file notes.
                        "show_system": item.show_system,
                        "show_version": item.show_version,
                        "is_current_show": item.is_current_show,
                    }
                    for item in files_for_crew(project)
                ],
            }
        )


# --- Project templates (PRJ-076) ---------------------------------------------------------------


class ProjectTemplateSerializer(serializers.ModelSerializer):
    """A project template; its content is read-only and made from a project."""

    counts = serializers.DictField(child=serializers.IntegerField(), read_only=True)

    class Meta:
        model = ProjectTemplate
        fields = ["id", "name", "description", "source_number", "created_by", "created_at", "counts", "content"]
        read_only_fields = ["source_number", "created_by", "created_at", "counts", "content"]

    def to_representation(self, instance: ProjectTemplate) -> dict[str, Any]:
        """The content without prices for who may not see prices (AUT-019)."""
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request is not None and not request_rights(request).has(SpecialRight.PRICES):
            data["content"] = template_content.without_prices(data.get("content") or {})
        return data


class ProjectTemplateViewSet(TemplateContentActions, ModuleViewSet):
    """``/project-templates`` – templates new projects start from (PRJ-076).

    A template is made from a project with ``POST /project-templates`` and
    ``project`` (plus ``material``, ``crew``, ``course``, each true by
    default); it is used with ``template`` when creating a project. Its
    content is changed with the ``/content`` endpoints (PRJ-136).
    """

    module = Module.PROJECTS
    queryset = ProjectTemplate.objects.select_related("created_by").order_by("name")
    serializer_class = ProjectTemplateSerializer
    # "put" only for the actions of the content (the template itself is changed with PATCH).
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    @extend_schema(exclude=True)
    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """``PUT`` is only for the content; the template itself (name, description) is changed with ``PATCH``."""
        if not kwargs.get("partial"):
            raise MethodNotAllowed(request.method or "PUT")
        return super().update(request, *args, **kwargs)

    @extend_schema(
        request=inline_serializer(
            "ProjectTemplateCreate",
            {
                "project": serializers.IntegerField(),
                "name": serializers.CharField(),
                "description": serializers.CharField(required=False),
                "material": serializers.BooleanField(required=False, default=True),
                "crew": serializers.BooleanField(required=False, default=True),
                "course": serializers.BooleanField(required=False, default=True),
                "replace": serializers.BooleanField(required=False, default=False),
            },
        ),
        responses={201: ProjectTemplateSerializer},
    )
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Make a template from a project the caller may read."""
        from rentalars.projects.project_templates import save_as_template

        project_id = request.data.get("project")
        if not str(project_id or "").isdigit():
            raise serializers.ValidationError({"project": ["Name the project the template is made from."]})
        project = get_object_or_404(Project, pk=int(project_id))
        if access_level(self.rights, request.user, project) < ProjectAccess.READ:
            raise NotFound

        def flag(name: str, default: bool) -> bool:
            value = request.data.get(name, default)
            return value if isinstance(value, bool) else str(value).lower() in {"1", "true", "yes", "on"}

        try:
            template = save_as_template(
                project,
                name=str(request.data.get("name", "")),
                description=str(request.data.get("description", "")),
                rights=self.rights,
                user=request.user,
                material=flag("material", True),
                crew=flag("crew", True),
                course=flag("course", True),
                replace=flag("replace", False),
            )
        except ValidationError as error:
            raise serializers.ValidationError(serializers.as_serializer_error(error)) from error
        return Response(self.get_serializer(template).data, status=status.HTTP_201_CREATED)
