# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views of the projects module: list, planning, price overview, history.

The planning page changes without full page loads: adding, editing, deleting
and sorting lines each send a small request and get the refreshed planning
back (UIX-009) – after changes of a single line only the parts that were
touched, see :func:`_planning_response`. All of these requests call the same
services as the API (API-002).
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import SimpleLazyObject
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_GET, require_POST

from rentalars.accounts.models import User
from rentalars.accounts.rights import Level, Module, SpecialRight, module_required, request_rights, require
from rentalars.availability.engine import AvailabilityEngine
from rentalars.core.forms import add_validation_error
from rentalars.core.history import describe
from rentalars.core.i18n import file_name, local_pattern, plural_of
from rentalars.core.listing import end_of_day, paginate, placeholder_url, query_date, query_datetime, start_of_day
from rentalars.core.models import AuditLogEntry
from rentalars.core.money import format_decimal, format_money
from rentalars.customers.models import Customer
from rentalars.mail import inquiries as mail_inquiries
from rentalars.mail.imap import MailboxError
from rentalars.material.models import MaterialItem, MaterialModel
from rentalars.notifications.services import project_changed
from rentalars.products.models import Product
from rentalars.projects import list_sums, services
from rentalars.projects import numbers as project_numbers
from rentalars.projects.access import (
    ProjectAccess,
    access_level,
    may_plan_crew,
    may_plan_logistics,
    note_access,
    project_for,
    visible_projects,
)
from rentalars.projects.course import suggests_confirmation
from rentalars.projects.discounts import group_discount_warning, line_discount_warning
from rentalars.projects.forms import (
    CrewAddForm,
    FreeLineForm,
    GroupForm,
    LineForm,
    OverallDiscountForm,
    ProjectForm,
    SubrentalForm,
    default_period,
)
from rentalars.projects.logistics_forms import VehicleAddForm
from rentalars.projects.models import (
    Group,
    MaterialLine,
    Project,
    ProjectAccessLevel,
    ProjectKind,
    ProjectMembership,
    ProjectStatus,
    SubrentalStatus,
)
from rentalars.projects.period_warnings import project_warnings
from rentalars.projects.planning import Planning, build_patch, build_planning
from rentalars.projects.pricing import DaysSource, resolve_rental_days_with_source
from rentalars.projects.project_templates import apply_template
from rentalars.projects.tables import PROJECT_TABLE, may_see_customers


def _error_text(error: ValidationError) -> str:
    """Flatten a validation error into one readable sentence for a message."""
    if hasattr(error, "error_dict"):
        return " ".join(
            message for errors in error.error_dict.values() for single in errors for message in single.messages
        )
    return " ".join(error.messages)


# --- List and master data (PRJ-001, PRJ-027) -----------------------------------------


@module_required(Module.PROJECTS)
def _bulk_context(request: HttpRequest) -> dict[str, Any]:
    """The bar under the list offers the follow-up to who may write projects (``projects.bulk``)."""
    from rentalars.projects import bulk_views

    if not bulk_views.may_change_projects(request):
        return {}
    return {"bulk_may": True, "bulk_fields": bulk_views.empty_bar()}


def project_list(request: HttpRequest) -> HttpResponse:
    """All projects with search and filters: status, period, customer, project manager, follow-up (PRJ-105)."""
    from rentalars.projects.follow_up import FILTER_CHOICES as FOLLOW_UP_CHOICES
    from rentalars.projects.follow_up import FILTERS as FOLLOW_UP_FILTERS
    from rentalars.projects.follow_up import filter_projects as follow_up_filter

    # AUT-016: someone limited to assigned projects sees those and no others.
    rights = request_rights(request)
    projects = visible_projects(rights, request.user).select_related("customer", "manager", "follow_up_user")
    # PRJ-090: the service cases have a list of their own (Projekte → Servicefälle).
    projects = projects.exclude(kind=ProjectKind.SERVICE_CASE)
    # AUT-023: crew and freelancers see their deployments, not who the customer is.
    show_customers = may_see_customers(rights)
    text = request.GET.get("q", "").strip()
    if text:
        # ADM-012, ADM-014: the former number finds the project too.
        # PRJ-122: the customer's name is shown in every role, so it is searched in every role.
        condition = (
            project_numbers.matching(text)
            | Q(name__icontains=text)
            | Q(venue__icontains=text)
            | Q(customer__name__icontains=text)
        )
        projects = projects.filter(condition)
    # PRJ-105: follow-ups due, mine, or all of them – in every status, as a search; for who sees them.
    follow_up = request.GET.get("follow_up", "")
    follow_up = follow_up if show_customers and follow_up in FOLLOW_UP_FILTERS else ""
    if follow_up:
        projects = follow_up_filter(projects, follow_up, request.user)
    # DOK-015: the closed projects whose invoice is still open – for who may see prices.
    from rentalars.documents import invoice_reminders

    invoice = request.GET.get("invoice", "") if rights.has(SpecialRight.PRICES) else ""
    invoice = invoice if invoice == "open" else ""
    if invoice:
        projects = invoice_reminders.open_projects(projects)
    statuses = [status for status in request.GET.getlist("status") if status in ProjectStatus.values]
    if statuses:
        projects = projects.filter(status__in=statuses)
    elif not text and not follow_up and not invoice and not request.GET.get("all"):
        # Everyday view: hide what is over. A search looks everywhere.
        projects = projects.exclude(status__in=[ProjectStatus.CLOSED, ProjectStatus.CANCELLED])
    customer_id = request.GET.get("customer", "") if show_customers else ""
    if customer_id.isdigit():
        projects = projects.filter(customer_id=int(customer_id))
    manager_id = request.GET.get("manager", "")
    if manager_id.isdigit():
        projects = projects.filter(manager_id=int(manager_id))
    since = query_date(request.GET.get("since"))
    until = query_date(request.GET.get("until"))
    if since:
        projects = projects.filter(end__gte=start_of_day(since))
    if until:
        projects = projects.filter(start__lt=end_of_day(until))
    table = PROJECT_TABLE.state(request)
    # PRJ-044: parts name their whole project, whole projects count their parts.
    projects = projects.select_related("venue_site", "contact", "parent").annotate(part_count=Count("subprojects"))
    if "invoice" in table.shown_keys:
        # DOK-015: the number of the valid invoice for the column "Rechnung" – one subquery, only when it is shown.
        projects = invoice_reminders.with_invoice_numbers(projects)
    projects = table.order(projects)
    # PRJ-085: the sums only when one of their columns is shown – for the rows of the page or the file.
    sums = list_sums.wanted(table.shown_keys)
    if table.wants_csv:
        if sums:
            return table.csv_response(list_sums.with_sums(projects, rights=rights, user=request.user), _("Projects"))
        return table.csv_response(projects, _("Projects"))
    page = paginate(request, projects)
    if sums:
        list_sums.attach_sums(list(page), rights=rights, user=request.user)
    if show_customers:
        # PRJ-105: the follow-up shows with the name – to who may know whose project it is (AUT-023).
        for project in page:
            project.shows_follow_up = True
    return render(
        request,
        "projects/list.html",
        {
            "page": page,
            "table": table,
            "rows": table.rows(page),
            "q": text,
            "statuses": ProjectStatus.choices,
            "selected_statuses": statuses,
            "show_customers": show_customers,
            "customers": (
                Customer.objects.filter(projects__isnull=False).distinct().order_by("name") if show_customers else []
            ),
            "managers": User.objects.filter(managed_projects__isnull=False).distinct() if show_customers else [],
            "filters": {
                "customer": customer_id,
                "manager": manager_id,
                "since": request.GET.get("since", ""),
                "until": request.GET.get("until", ""),
                "follow_up": follow_up,
                "invoice": invoice,
            },
            "follow_up_choices": FOLLOW_UP_CHOICES,
            **_bulk_context(request),
        },
    )


@module_required(Module.PROJECTS, Level.WRITE)
def project_edit(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    """Create a project or edit its master data."""
    project = project_for(request, pk, ProjectAccess.EDIT) if pk else None
    if project is not None and project.is_service_case:
        return redirect("projects:case_edit", pk=project.pk)  # PRJ-090
    initial: dict[str, Any] = {}
    if project is None:
        start, end = default_period()
        initial = {"start": start, "end": end, "manager": request.user}
    # PRJ-107: "Als Projekt anlegen" from an inquiry under Projekte → Anfragen; saving takes the mail along.
    unknown = mail_inquiries.inquiry_of(request) if project is None else None
    if unknown is not None:
        initial.update(mail_inquiries.project_initial(unknown))
    if request.GET.get("customer", "").isdigit():
        # A link "new project for this customer" – or the form asking for the contacts and addresses of
        # the customer just chosen (PRJ-070), which it shows in place.
        initial["customer"] = int(request.GET["customer"])
    form = ProjectForm(request.POST or None, instance=project, initial=initial, rights=request_rights(request))
    if request.method == "POST" and form.is_valid():
        data = dict(form.cleaned_data)
        template = data.pop("template", None)
        for name in ("billing_address", "delivery_address"):
            if name in form.fields and form.fields[name].widget.is_hidden:
                # Not offered (the customer was chosen just now): the service takes the customer's defaults.
                data.pop(name, None)
        try:
            if project is None:
                with transaction.atomic():
                    saved = services.create_project(**data)
                    if request_rights(request).is_limited_to_assigned_projects(Module.PROJECTS):
                        # AUT-016: without a membership the creator could not open the new project.
                        ProjectMembership.objects.get_or_create(
                            project=saved, user=request.user, defaults={"level": ProjectAccessLevel.EDIT}
                        )
                    if template is not None:
                        # PRJ-076: the content of the template, with today's prices.
                        applied = apply_template(template, saved, rights=request_rights(request))
                        for text in sorted(set(applied.left_out)):
                            messages.warning(request, _("Left out from the template: %(what)s") % {"what": text})
                    if unknown is not None:
                        mail_inquiries.take_into(unknown, saved)  # PRJ-107: both or neither
            else:
                old_period = (project.start, project.end)
                saved = services.update_project(project, **data)
                if (saved.start, saved.end) != old_period:
                    # UIX-005: a new period concerns everybody planned in the project.
                    project_changed(
                        saved,
                        _("new period %(start)s – %(end)s")
                        % {
                            "start": timezone.localtime(saved.start).strftime(local_pattern("%d.%m. %H:%M")),
                            "end": timezone.localtime(saved.end).strftime(local_pattern("%d.%m. %H:%M")),
                        },
                        actor=request.user,
                        crew_too=True,
                    )
        except ValidationError as error:
            add_validation_error(form, error)
        except MailboxError as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, _("Project %(number)s saved.") % {"number": saved.number})
            for warning in project_warnings(saved):  # PRJ-005 (event end; PRJ-127): saving stays possible
                messages.warning(request, warning)
            if unknown is not None and unknown.is_manual:
                # EML-053: an inquiry noted by hand is a note in the correspondence now.
                messages.success(request, _("The inquiry is a note in the correspondence of the project now."))
            elif unknown is not None:
                messages.success(request, _("The mail is in the project now."))
            return redirect("projects:detail", pk=saved.pk)
    return render(
        request, "projects/form.html", {"form": form, "project": project, "parent": form.parent, "unknown": unknown}
    )


@module_required(Module.PROJECTS, Level.WRITE)
def overall_discount_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """The overall discount of a project in a dialog: percent, amount, or a target amount (PRJ-123).

    Discount target: besides percent and amount the user can type the total the project should come to –
    net or gross, after the discount. The percentage is calculated, stored and named in a message; it is not
    calculated again when the project changes later. ``?preview=1`` answers the live preview of the dialog: what the
    typed values lead to, without saving anything.
    """
    from rentalars.projects.overall_target import prices_without_discount, totals_after_overall_discount

    project = project_for(request, pk, ProjectAccess.EDIT)
    rights = request_rights(request)
    if not rights.has(SpecialRight.PRICES):
        raise PermissionDenied
    if request.method == "GET" and request.GET.get("preview"):
        form = OverallDiscountForm(request.GET, project=project)
        shown = (
            form.figures()
            if form.is_valid()
            else " ".join(message for errors in form.errors.values() for message in errors)
        )
        context = {"error": shown} if isinstance(shown, str) else {"preview": shown}
        return render(request, "projects/_overall_discount_preview.html", context)
    form = OverallDiscountForm(request.POST or None, project=project)
    if request.method == "POST" and form.is_valid():
        try:
            _save_overall_discount(request, project, form, rights)
        except ValidationError as error:
            form.add_error(None, _error_text(error))
        else:
            return _planning_response(request, project, close_dialog=True)
    prices = prices_without_discount(project)
    return render(
        request,
        "projects/_overall_discount_form.html",
        {
            "form": form,
            "title": _("Overall discount"),
            "action": request.path,
            "net_before": prices.net_before_overall_discount,
            "gross_before": totals_after_overall_discount(prices, Decimal("0"))[1],
        },
    )


def _save_overall_discount(request: HttpRequest, project: Project, form: OverallDiscountForm, rights: Any) -> None:
    """Store what the dialog says; for a target amount the message names the percentage and the resulting total."""
    mode = form.chosen()
    data = form.cleaned_data
    if mode in {"target_net", "target_gross"}:
        result = services.set_overall_discount_to_target(
            project,
            rights=rights,
            net=data["target_net"] if mode == "target_net" else None,
            gross=data["target_gross"] if mode == "target_gross" else None,
        )
        percent = format_decimal(result.percent, max_places=6) if result.percent is not None else "0"
        message = _(
            "Overall discount of %(percent)s %% stored. The project now comes to %(net)s net, %(gross)s gross."
        ) % {"percent": percent, "net": format_money(result.net_total), "gross": format_money(result.gross_total)}
        if result.is_exact:
            messages.success(request, message)
        else:
            messages.warning(
                request,
                _("The target %(target)s cannot be reached to the cent; the nearest is %(reached)s.")
                % {"target": format_money(result.target), "reached": format_money(result.reached)}
                + " "
                + message,
            )
        return
    services.set_overall_discount(
        project,
        rights=rights,
        percent=data["percent"] if mode == "percent" else None,
        amount=data["amount"] if mode == "amount" else None,
    )


@require_POST
@module_required(Module.PROJECTS, Level.DELETE)
def project_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a project that never left the planning stage."""
    project = project_for(request, pk, ProjectAccess.EDIT)
    try:
        services.delete_project(project)
    except ValidationError as error:
        messages.error(request, _error_text(error))
        return redirect("projects:detail", pk=pk)
    messages.success(request, _("Project deleted."))
    return redirect("projects:list")


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def project_set_status(request: HttpRequest, pk: int) -> HttpResponse:
    """Change the status of a project (PRJ-008); the change is logged (PRJ-009)."""
    project = project_for(request, pk, ProjectAccess.EDIT)
    kept: list[str] = []
    try:
        if request.POST.get("with_parts") and project.has_subprojects:
            # PRJ-044: the whole project and, where the rules allow it, all its parts.
            kept = services.change_family_status(
                project, request.POST.get("status", ""), rights=request_rights(request)
            )
        else:
            services.change_status(project, request.POST.get("status", ""), rights=request_rights(request))
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, _("Status changed to “%(status)s”.") % {"status": project.get_status_display()})
        if kept:
            messages.warning(
                request,
                _("These subprojects kept their status, the step is not possible for them: %(numbers)s")
                % {"numbers": ", ".join(kept)},
            )
        # UIX-005: the project manager – and, if it concerns them, the crew – hear of it.
        project_changed(
            project,
            _("status “%(status)s”") % {"status": project.get_status_display()},
            actor=request.user,
            crew_too=project.status == ProjectStatus.CANCELLED,
        )
        if project.status == ProjectStatus.CONFIRMED_OPEN and not project.open_items.filter(is_done=False).exists():
            # PRJ-059: what is open is noted right away.
            messages.info(request, _("Note what is still open."))
            return redirect("projects:course", pk=pk)
        if project.reserves_firmly and request_rights(request).has(SpecialRight.AVAILABILITY):  # AUT-032
            shortage = build_planning(project).shortage_total
            if shortage:
                messages.warning(
                    request,
                    ngettext(
                        "The project is short of %(count)d piece. See the lines marked in red.",
                        "The project is short of %(count)d pieces. See the lines marked in red.",
                        plural_of(shortage),
                    )
                    % {"count": shortage},
                )
    # PRJ-078: the status is changed on every tab; the user stays on the tab it was changed on.
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(target)
    return redirect("projects:detail", pk=pk)


# --- Planning page (PRJ-010 ff.) -------------------------------------------------------


@dataclass
class Touched:
    """What a change of a single line touched: its products and groups, before and after.

    From this the answer is cut down to the parts of the planning that can
    look different now (see :func:`rentalars.projects.planning.build_patch`).
    ``None`` among the groups stands for "without group".
    """

    product_ids: set[int | None] = field(default_factory=set)
    group_ids: set[int | None] = field(default_factory=set)
    #: A crew line changed: the block "personnel" is sent again.
    crew: bool = False
    #: LOG-001: a vehicle booking or a vehicle on a trip changed: the block "Logistik" is sent again.
    logistics: bool = False

    def add(self, line: MaterialLine) -> None:
        """Note the present product and group of a line, and what it covers as a subrental."""
        self.product_ids.update({line.product_id, line.covers_product_id})
        if line.covers_line_id:
            self.product_ids.add(line.covers_line.product_id)
            self.group_ids.add(line.covers_line.group_id)
        self.group_ids.add(line.group_id)

    def add_alternatives_of(self, line: MaterialLine) -> None:
        """Note the groups of the lines that are an alternative to this one: they name it (PRJ-083)."""
        self.group_ids.update(line.alternatives.values_list("group_id", flat=True))


def _access(request: HttpRequest, project: Project) -> ProjectAccess:
    """Return what the user may do in a project; ``project_for`` has noted it on the project."""
    access = getattr(project, "access", None)
    if access is None:
        access = access_level(request_rights(request), request.user, project)
        note_access(project, access)
    return access


def _planning_context(request: HttpRequest, project: Project, *, planning: Planning | None = None) -> dict[str, Any]:
    """Everything the planning block needs.

    Args:
        request: The request being answered.
        project: The project.
        planning: The picture of the project, if the caller has built one
            (a patch brings its own, partial one); otherwise the complete
            planning is built here.
    """
    rights = request_rights(request)
    access = _access(request, project)
    can_plan_crew = may_plan_crew(rights, access) and not project.is_locked
    may_see_crew_costs = rights.has(SpecialRight.PERSONNEL_COSTS)
    can_plan_logistics = may_plan_logistics(rights, access) and not project.is_locked
    planning = planning or build_planning(project)
    planning.see_prices = rights.has(SpecialRight.PRICES)  # PRJ-072: prices are part of the product changes then
    return {
        "project": project,
        "planning": planning,
        "can_edit": access >= ProjectAccess.EDIT and not project.is_locked,
        "show_costs": rights.has(SpecialRight.PRICES) and rights.has(SpecialRight.PURCHASE_PRICES),
        # Personnel (PRJ-038): who may plan it, and who may see what it costs (AUT-019).
        "can_plan_crew": can_plan_crew,
        "show_personnel_costs": may_see_crew_costs,
        # The margin is net minus *all* costs; shown without one of the cost
        # rights it would give that cost away.
        "show_margin": (
            rights.has(SpecialRight.PRICES) and rights.has(SpecialRight.PURCHASE_PRICES) and may_see_crew_costs
        ),
        "crew_add_form": CrewAddForm(
            project=project,
            may_plan_any=rights.has(SpecialRight.PLAN_ANY_JOB_FUNCTION),
            # PRJ-094: a new phase from the list – only for whoever may edit the project.
            offer_new_phase=access >= ProjectAccess.EDIT and not project.is_locked,
        )
        if can_plan_crew
        else None,
        # LOG-001: the vehicles – who may book them, who sees their internal costs (LOG-010, AUT-019).
        "can_plan_logistics": can_plan_logistics,
        "show_logistics_costs": rights.has(SpecialRight.PURCHASE_PRICES),
        # Made only where a template shows it – not for the hints fetched after every change of a line (NFA-014).
        "vehicle_add_form": SimpleLazyObject(
            lambda: VehicleAddForm(
                project=project, offer_new_phase=access >= ProjectAccess.EDIT and not project.is_locked
            )
        )
        if can_plan_logistics
        else None,
        # Addresses every row needs, looked up once; the template fills in the line ID.
        "urls": {
            "line_edit": placeholder_url("projects:line_edit", project.pk),
            "line_delete": placeholder_url("projects:line_delete", project.pk),
            "line_duplicate": placeholder_url("projects:line_duplicate", project.pk),  # PRJ-075
            "subrental_accept": placeholder_url("projects:subrental_accept", project.pk),
            # PRJ-106: the page of a subrental's supplier; the template fills in the supplier's ID.
            "subrental_page": placeholder_url("projects:subrental", project.pk),
            # PRJ-082, PRJ-083: several lines at once, and the buttons "optional" and "Alternative" of a line.
            "lines_bulk": reverse("projects:lines_bulk", args=[project.pk]),
            "lines_alternative": reverse("projects:lines_alternative", args=[project.pk]),
            # The article number leads to the product – for whoever may read products; "" otherwise.
            # The template fills in the article number, which is what the address of a product shows.
            "product_page": placeholder_url("products:detail") if rights.can_read(Module.PRODUCTS) else "",
        },
        # On a full page the layout shows the messages; a swapped-in block
        # has to carry them itself.
        "is_fragment": bool(request.headers.get("HX-Request")),
        "days_source_labels": days_source_labels(),
    }


def _planning_response(
    request: HttpRequest, project: Project, *, close_dialog: bool = False, touched: Touched | None = None
) -> HttpResponse:
    """Return the refreshed planning after a change.

    Messages (errors, hints) are part of the answer, so they show up without
    a page load.

    There are two kinds of answer:

    * The **whole block**, which replaces the one on the page. Used when the
      structure changed (groups added, deleted, copied) – and whenever the
      caller does not say what was touched.
    * A **patch** with only the touched groups and the totals, when the
      caller passes ``touched``. Adding the 501st line to a project must
      answer within half a second (NFA-013); judging and sending all 500
      lines again for that would take most of the time and nearly a
      megabyte. The hints about the whole project ("3 pieces are missing")
      are not part of the patch: the answer announces ``planningChanged``,
      and the page then fetches them from :func:`planning_notes`.

    Args:
        request: The request that made the change.
        project: The project.
        close_dialog: Tell the page to close the dialog the change came from.
        touched: What the change touched. ``None`` sends the whole block; an
            empty :class:`Touched` (nothing changed, e.g. after an error)
            sends just messages and totals.
    """
    events = ["closeDialog"] if close_dialog else []
    if touched is None or not request.headers.get("HX-Request"):
        response = render(request, "projects/_planning.html", _planning_context(request, project))
        response["HX-Reswap"] = "outerHTML"
        # PRJ-072: the whole block replaces the whole block, whatever the element that sent the request
        # would select of the answer. A form among the hints once inherited the selection of the hints
        # and replaced the planning with the hints alone.
        response["HX-Reselect"] = "#planning"
    else:
        planning, patch = build_patch(
            project, AvailabilityEngine(), product_ids=touched.product_ids, group_ids=touched.group_ids
        )
        # A crew line names its vehicle, a vehicle counts its people (LOG-008): the two blocks go together.
        patch.crew = patch.logistics = touched.crew or touched.logistics
        context = _planning_context(request, project, planning=planning)
        context["patch"] = patch
        response = render(request, "projects/_planning_patch.html", context)
        # Nothing is put in one place as a whole; the parts find their places by their ids.
        response["HX-Reswap"] = "none"
        events.append("planningChanged")
    # The request may have come from the dialog. The answer belongs to the
    # planning all the same – and the page opens the dialog whenever an
    # answer is addressed to it.
    response["HX-Retarget"] = "#planning"
    if events:
        response["HX-Trigger"] = ", ".join(events)
    return response


@require_GET
@module_required(Module.PROJECTS)
def planning_notes(request: HttpRequest, pk: int) -> HttpResponse:
    """The hints above the planning that speak about all lines (PRJ-013, PRJ-056).

    The planning page asks for them after every change of a line, see
    :func:`_planning_response`.
    """
    project = project_for(request, pk, ProjectAccess.READ)
    return render(request, "projects/_planning_notes.html", _planning_context(request, project))


@require_GET
@module_required(Module.PROJECTS)
def planning_availability(request: HttpRequest, pk: int) -> HttpResponse:
    """The availability of all lines of the planning as it is now (stock refresh).

    An open planning page asks for it when the key ``stock:<pk>`` (``rentalars.projects.stock_watch``) moved – a model
    was linked to a product in another tab, an item was blocked, a colleague planned the same material. The answer
    holds the cells "Availability", the wishes and the hints above the lines, each in a ``<template>``; the script
    puts them in place, so that what the user types stays. Nothing for whoever may not see the availability (AUT-032).
    """
    project = project_for(request, pk, ProjectAccess.READ)
    response = render(request, "projects/_planning_stock.html", _planning_context(request, project))
    response["Cache-Control"] = "no-store"
    return response


@module_required(Module.PROJECTS)
def project_overview(request: HttpRequest, pk: int) -> HttpResponse:
    """Where opening a project leads: its "Überblick", the first tab (PRJ-104, tab order).

    A service case has its own page for it. The planning keeps its address
    (``projects:detail``): the tab, the back links and what follows an action
    on the planning still lead there.
    """
    project = project_for(request, pk, ProjectAccess.DEPLOYMENT)
    if project.is_service_case:
        return redirect("projects:case_detail", pk=project.pk)
    return redirect("projects:deployment", pk=project.pk)


@module_required(Module.PROJECTS)
def project_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """The planning page of a project: groups, lines, availability, prices, totals."""
    from rentalars.timetracking.expenses import approved_expenses_total

    project = project_for(
        request,
        pk,
        ProjectAccess.DEPLOYMENT,
        # ZEI-019: the approved expenses for the totals come with the project – no query of their own.
        queryset=Project.objects.select_related("customer", "contact", "manager", "parent").annotate(
            approved_expenses_total=approved_expenses_total()
        ),
    )
    if project.is_service_case:
        # PRJ-090: a service case has no planning; its page says what it is about.
        return redirect("projects:case_detail", pk=project.pk)
    if project.access < ProjectAccess.READ:
        # Crew sees the deployment view, not the planning (AUT-018, AUT-025).
        return redirect("projects:deployment", pk=project.pk)
    context = _planning_context(request, project)
    if request.headers.get("HX-Request"):
        return render(request, "projects/_planning.html", context)
    if project.is_in_family:
        # PRJ-044: the whole project and its parts, as a strip above the planning.
        from rentalars.projects.family import members

        context["family_members"] = members(project)
    context.update(
        tab="planning",
        suggest_confirmation=suggests_confirmation(project),
        can_change_status=_access(request, project) >= ProjectAccess.EDIT,
    )
    return render(request, "projects/detail.html", context)


def _decimal(text: str, default: str = "1") -> Decimal:
    """Read a typed quantity; accepts the German comma."""
    try:
        return Decimal((text or default).replace(",", "."))
    except InvalidOperation as error:
        raise ValidationError(_("“%(value)s” is not a number.") % {"value": text}) from error


def parse_material_choice(token: str) -> tuple[int, dict[str, Any]]:
    """Read what was picked in the search field for adding a line (PRJ-065).

    The search offers products and, below them, the models and items that
    belong to them. The field sends one of::

        "12"        the product 12
        "12:m34"    the product 12, and of it the model 34
        "12:i56"    the product 12, and of it the item 56

    Returns:
        The product ID and the wish to store on the line (``preferred_model``
        or ``preferred_item``), empty for a plain product.

    Raises:
        ValidationError: The text is none of the three forms, or the model
            or item does not exist.
    """
    product_text, _separator, detail = (token or "").strip().partition(":")
    if not product_text.isdigit() or (detail and (detail[0] not in "mi" or not detail[1:].isdigit())):
        raise ValidationError(_("Choose a product from the list."))
    wish: dict[str, Any] = {}
    if detail.startswith("m"):
        wish["preferred_model"] = MaterialModel.objects.filter(pk=int(detail[1:])).first()
    elif detail.startswith("i"):
        wish["preferred_item"] = (
            MaterialItem.objects.filter(pk=int(detail[1:])).select_related("material_model").first()
        )
    if any(value is None for value in wish.values()):
        raise ValidationError(_("Choose a product from the list."))
    return int(product_text), wish


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def line_add(request: HttpRequest, pk: int) -> HttpResponse:
    """Add a product to a project; the availability shows at once (PRJ-010, PRJ-012).

    The search field also finds models and items; picking one of them adds
    the product and notes the model or item as a wish on the line (PRJ-065).
    """
    project = project_for(request, pk, ProjectAccess.EDIT)
    touched = Touched()
    try:
        product_id, wish = parse_material_choice(request.POST.get("product", ""))
        product = Product.objects.filter(pk=product_id).select_related("category", "unit", "tax_rate").first()
        if product is None:
            raise ValidationError(_("Choose a product from the list."))
        group = project.groups.filter(pk=request.POST.get("group") or 0).first()
        result = services.add_line(
            project,
            rights=request_rights(request),
            product=product,
            quantity=_decimal(request.POST.get("quantity", "")),
            group=group,
            **wish,
        )
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        touched.add(result.line)
        if result.availability.status == "short" and request_rights(request).has(SpecialRight.AVAILABILITY):
            # PRJ-013: saved all the same, but with a clear warning. AUT-032: for who may see availability.
            messages.warning(
                request,
                ngettext(
                    "%(title)s was added, but %(count)d piece is missing in this period.",
                    "%(title)s was added, but %(count)d pieces are missing in this period.",
                    plural_of(result.availability.shortage_total),
                )
                % {"title": result.line.title, "count": result.availability.shortage_total},
            )
    return _planning_response(request, project, touched=touched)


@module_required(Module.PROJECTS, Level.WRITE)
def free_line_add(request: HttpRequest, pk: int) -> HttpResponse:
    """Add a line without product in a dialog (PRJ-017)."""
    project = project_for(request, pk, ProjectAccess.EDIT)
    rights = request_rights(request)
    form = FreeLineForm(request.POST or None, project=project, rights=rights)
    if request.method == "POST" and form.is_valid():
        values = dict(form.cleaned_data)
        try:
            result = services.add_line(
                project,
                rights=rights,
                product=None,
                quantity=values.pop("quantity"),
                group=values.pop("group"),
                **values,
            )
        except ValidationError as error:
            form.add_error(None, _error_text(error))
        else:
            touched = Touched()
            touched.add(result.line)
            return _planning_response(request, project, close_dialog=True, touched=touched)
    return render(
        request,
        "projects/_dialog_form.html",
        {"form": form, "title": _("Line without product"), "action": request.path, "submit_label": _("Add line")},
    )


@module_required(Module.PROJECTS, Level.WRITE)
def line_edit(request: HttpRequest, pk: int, line_pk: int) -> HttpResponse:
    """Edit a line in a dialog: quantity, period, price, discount, subrental data."""
    project = project_for(request, pk, ProjectAccess.EDIT)
    line = get_object_or_404(
        project.material_lines.select_related("product", "group", "tax_rate", "unit", "supplier", "covers_line"),
        pk=line_pk,
    )
    rights = request_rights(request)
    form = LineForm(request.POST or None, line=line, rights=rights)
    if request.method == "POST" and form.is_valid():
        touched = Touched()
        touched.add(line)  # where the line was …
        warnings: list[str] = []
        try:
            # Either everything from the dialog is saved or nothing of it.
            with transaction.atomic():
                changes = form.changes()
                if changes:
                    warnings = services.update_line(line, rights=rights, **changes).warnings
                targets = form.targets()
                if targets is not None:
                    services.set_surcharge_targets(line, targets)
        except ValidationError as error:
            form.add_error(None, _error_text(error))
        else:
            touched.add(line)  # … and where it is now
            touched.add_alternatives_of(line)  # PRJ-083: they name it by quantity and title
            for warning in warnings:
                messages.warning(request, warning)  # A discount above the maximum, cut and said
            return _planning_response(request, project, close_dialog=True, touched=touched)
    return render(
        request,
        "projects/_line_form.html",
        {"form": form, "line": line, "project": project, "action": request.path},
    )


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def line_delete(request: HttpRequest, pk: int, line_pk: int) -> HttpResponse:
    """Delete a line."""
    project = project_for(request, pk, ProjectAccess.EDIT)
    line = get_object_or_404(project.material_lines.select_related("product", "covers_line"), pk=line_pk)
    touched = Touched()
    touched.add(line)
    # Subrentals that covered a shortage of this line lose their reason with it; lines that were an
    # alternative to it become optional (PRJ-083).
    touched.group_ids.update(project.material_lines.filter(covers_line=line).values_list("group_id", flat=True))
    touched.add_alternatives_of(line)
    try:
        services.delete_line(line)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    return _planning_response(request, project, touched=touched)


#: Where the rental days of a line come from, in words (PRJ-062).
def days_source_labels() -> dict[str, str]:
    """Return the explanation for each source of rental days, in the current language."""
    return {
        DaysSource.LINE: _("typed in on this line"),
        DaysSource.PERIOD: _("from the period of this line"),
        DaysSource.GROUP: _("as the group"),
        DaysSource.PROJECT: _("as the project"),
    }


@module_required(Module.PROJECTS)
def line_availability(request: HttpRequest, pk: int) -> HttpResponse:
    """What the values typed into the line dialog mean, while they are being typed.

    Called by the dialog whenever quantity, period or rental days change.
    Answers with

    * the traffic light and the stock figures for the typed values (PRJ-012),
      for products whose availability is checked;
    * the rental days that follow from the typed period (PRJ-062), so that
      nobody has to save first to see what a changed period costs.
    """
    project = project_for(request, pk, ProjectAccess.READ)
    line = project.material_lines.filter(pk=request.GET.get("line") or 0).select_related("product", "group").first()
    product = line.product if line else Product.objects.filter(pk=request.GET.get("product") or 0).first()
    context: dict[str, Any] = {
        "verdict": None,
        # AUT-032: the traffic light only with the special right to see availability; the rental days for everybody.
        "checks_stock": product is not None
        and (product.tracks_stock or product.is_kit)
        and request_rights(request).has(SpecialRight.AVAILABILITY),
    }
    start = query_datetime(request.GET.get("start"))
    end = query_datetime(request.GET.get("end"))
    if start and timezone.is_naive(start):
        start = timezone.make_aware(start)
    if end and timezone.is_naive(end):
        end = timezone.make_aware(end)
    period_is_valid = bool(start and end and end > start)
    try:
        quantity = int(_decimal(request.GET.get("quantity", "")))
    except ValidationError:
        quantity = 0
    if context["checks_stock"] and period_is_valid and quantity > 0:
        verdict = AvailabilityEngine().check_candidate(
            project,
            product,
            quantity,
            start,
            end,
            exclude_line_id=line.pk if line else None,
            group=line.group if line else None,
            is_sale=request.GET.get("is_sale") == "on",
        )
        context["verdict"] = verdict
        context["detail"] = verdict.main
    if line is not None and "discount_percent" in request.GET and request_rights(request).has(SpecialRight.PRICES):
        # A discount above the maximum of the line is told while it is typed, not only after saving.
        typed = request.GET["discount_percent"].strip().replace(",", ".")
        try:
            context["discount_hint"] = line_discount_warning(line, Decimal(typed)) if typed else ""
        except InvalidOperation:
            context["discount_hint"] = ""
        context["has_discount_field"] = True
    if line is not None and line.uses_rental_days and period_is_valid:
        # Ask the pricing rules about the line as it is typed, not as it is stored.
        probe = copy.copy(line)
        probe.start, probe.end, probe.rental_days = start, end, None
        group_id = request.GET.get("group", "")
        group = project.groups.filter(pk=int(group_id)).first() if group_id.isdigit() else None
        automatic, source = resolve_rental_days_with_source(probe, group, project)
        context["days"] = {
            "typed": request.GET.get("rental_days", "").strip().isdigit(),
            "automatic": automatic,
            "source_label": days_source_labels()[source],
        }
    return render(request, "projects/_availability.html", context)


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def arrange(request: HttpRequest, pk: int) -> HttpResponse:
    """Store the order of lines after dragging (PRJ-014)."""
    project = project_for(request, pk, ProjectAccess.EDIT)
    try:
        layout = json.loads(request.body or b"{}").get("layout", [])
        parsed = [(entry.get("group"), [int(line_id) for line_id in entry.get("lines", [])]) for entry in layout]
        services.arrange_lines(project, parsed)
    except (ValueError, AttributeError, TypeError):
        return JsonResponse({"error": "malformed layout"}, status=400)
    except ValidationError as error:
        return JsonResponse({"error": _error_text(error)}, status=400)
    return HttpResponse(status=204)


# --- Groups (PRJ-014, PRJ-039 to PRJ-041) -----------------------------------------------


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def group_add(request: HttpRequest, pk: int) -> HttpResponse:
    """Add a group with the typed name – at the top level, or inside the chosen group (PRJ-037)."""
    project = project_for(request, pk, ProjectAccess.EDIT)
    name = request.POST.get("name", "").strip()
    parent_id = request.POST.get("parent", "")
    try:
        if not name:
            raise ValidationError(_("Give the group a name."))
        parent = project.groups.filter(pk=int(parent_id)).first() if parent_id.isdigit() else None
        if parent_id and parent is None:
            raise ValidationError(_("Choose one of the groups of this project."))
        services.add_group(project, rights=request_rights(request), name=name, parent=parent)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    return _planning_response(request, project)


@module_required(Module.PROJECTS, Level.WRITE)
def group_edit(request: HttpRequest, pk: int, group_pk: int) -> HttpResponse:
    """Edit a group in a dialog: name, kind, discount or flat price, description."""
    project = project_for(request, pk, ProjectAccess.EDIT)
    group = get_object_or_404(Group, pk=group_pk, project=project)
    rights = request_rights(request)
    form = GroupForm(request.POST or None, instance=group, rights=rights)
    if request.method == "POST" and form.is_valid():
        try:
            services.update_group(group, rights=rights, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, _error_text(error))
        else:
            if {"discount_percent", "discount_amount", "flat_price"} & set(form.changed_data):
                # The maximum discounts of its lines may cut the group's discount or flat price – said.
                warning = group_discount_warning(group)
                if warning:
                    messages.warning(request, warning)
            return _planning_response(request, project, close_dialog=True)
    return render(
        request,
        "projects/_dialog_form.html",
        {"form": form, "title": _("Edit group"), "action": request.path, "submit_label": _("Save group")},
    )


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def group_delete(request: HttpRequest, pk: int, group_pk: int) -> HttpResponse:
    """Delete a group; its lines move to "without group" unless they are to be deleted too."""
    project = project_for(request, pk, ProjectAccess.EDIT)
    group = get_object_or_404(Group, pk=group_pk, project=project)
    try:
        services.delete_group(group, keep_lines=request.POST.get("lines") != "delete")
    except ValidationError as error:
        messages.error(request, _error_text(error))
    return _planning_response(request, project)


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def group_copy(request: HttpRequest, pk: int, group_pk: int) -> HttpResponse:
    """Copy a group with its lines, into this or another project (PRJ-041)."""
    project = project_for(request, pk, ProjectAccess.EDIT)
    group = get_object_or_404(Group, pk=group_pk, project=project)
    target_number = request.POST.get("target", "").strip()
    # ADM-012, ADM-014: the former number is understood as well.
    target = project_numbers.project_by_number(target_number) if target_number else project
    if target is not None and access_level(request_rights(request), request.user, target) < ProjectAccess.EDIT:
        target = None  # a project the user may not edit is treated like one that does not exist (AUT-016)
    if target is None:
        messages.error(request, _("There is no project with the number %(number)s.") % {"number": target_number})
        return _planning_response(request, project)
    try:
        services.copy_group(group, target, rights=request_rights(request))
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        if target.pk != project.pk:
            messages.success(request, _("Group copied to project %(number)s.") % {"number": target.number})
    return _planning_response(request, project)


# --- Subrental and scales (PRJ-054, PRD-037) ---------------------------------------------


@module_required(Module.PROJECTS, Level.WRITE)
def subrental_accept(request: HttpRequest, pk: int, line_pk: int) -> HttpResponse:
    """Accept the subrental suggestion for a shortage (PRJ-054) – in a dialog (PRJ-084).

    The button of the suggestion opens a dialog (``GET`` with ``product`` and
    ``quantity``) that asks for supplier, quantity, purchase price and status
    – no rental price: the subrental is a part of the line it covers, and
    the customer pays that line (PRJ-055). Sending it (``POST``) adds the
    subrental. A ``POST`` without the dialog's fields still adds it at once,
    with the status "open" (PRJ-101).
    """
    project = project_for(request, pk, ProjectAccess.EDIT)
    line = get_object_or_404(project.material_lines.select_related("product"), pk=line_pk)
    data = request.POST if request.method == "POST" else request.GET
    product_id = str(data.get("product") or "")
    product = Product.objects.filter(pk=int(product_id)).first() if product_id.isdigit() else None
    rights = request_rights(request)
    from_dialog = request.method == "GET" or data.get("dialog") == "1"
    form = SubrentalForm(
        request.POST or None,
        rights=rights,
        initial={"quantity": data.get("quantity"), "status": SubrentalStatus.OPEN},
    )
    if request.method == "POST":
        if product is None:
            messages.error(request, _("Unknown product."))
            return _planning_response(request, project)
        if form.is_valid():
            values = form.cleaned_data
            try:
                services.accept_subrental_suggestion(
                    line,
                    product,
                    values["quantity"],
                    rights=rights,
                    supplier=values.get("supplier"),
                    purchase_price=values.get("purchase_price"),
                    status=values.get("status") or SubrentalStatus.OPEN,
                )
            except ValidationError as error:
                if not from_dialog:
                    messages.error(request, _error_text(error))
                    return _planning_response(request, project)
                form.add_error(None, _error_text(error))
            else:
                messages.success(request, _("Subrental added. The shortage is covered."))
                return _planning_response(request, project, close_dialog=from_dialog)
        elif not from_dialog:
            messages.error(request, " ".join(message for errors in form.errors.values() for message in errors))
            return _planning_response(request, project)
    return render(
        request,
        "projects/_subrental_form.html",
        {
            "form": form,
            "line": line,
            "product": product,
            "project": project,
            "action": request.path,
        },
    )


@require_POST
@module_required(Module.PROJECTS, Level.WRITE)
def refresh_scales(request: HttpRequest, pk: int) -> HttpResponse:
    """Switch the lines of a project to the current rental scale tables (PRD-037)."""
    require(request_rights(request).has(SpecialRight.PRICES))
    project = project_for(request, pk, ProjectAccess.EDIT)
    try:
        changed = services.refresh_scale_versions(project)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(
            request,
            ngettext(
                "%(count)d line now calculates with the current rental scale.",
                "%(count)d lines now calculate with the current rental scale.",
                changed,
            )
            % {"count": changed},
        )
    return _planning_response(request, project)


# --- Price overview and history (PRJ-035, PRJ-036, DOK-009, PRJ-032) ------------------------


@module_required(Module.PROJECTS)
def price_overview(request: HttpRequest, pk: int) -> HttpResponse:
    """The price overview as a basis for quotes written elsewhere (PRJ-035, DOK-009).

    Shows groups with subtotals, optionally with all lines (PRJ-036). Every
    amount and text can be copied with one click. Needs the price right.

    PRJ-046: a whole project shows its own groups and then every part that
    is not cancelled as a block with its subtotal, and the sum of all; parts
    the user may not read are left out, and the page says how many. A part
    shows just itself, with a hint to the sum in the whole project.

    PRJ-088: ``?crew=phases`` breaks the personnel down by phase and job
    function, at either level of detail; costs and margin of that breakdown
    need the right for personnel costs (AUT-019).
    """
    from rentalars.projects.family_prices import family_prices

    rights = request_rights(request)
    require(rights.has(SpecialRight.PRICES))
    project = project_for(
        request,
        pk,
        ProjectAccess.READ,
        queryset=Project.objects.select_related("customer", "contact", "manager", "parent"),
    )
    overview = family_prices(project, rights=rights, user=request.user)
    return render(
        request,
        "projects/price_overview.html",
        {
            "project": project,
            "overview": overview,
            "planning": overview.own.planning,
            "whole_readable": bool(project.parent_id)
            and access_level(rights, request.user, project.parent) >= ProjectAccess.READ,
            "with_lines": request.GET.get("detail", "lines") != "groups",
            "crew_by_phase": request.GET.get("crew") == "phases",
            "show_personnel_costs": rights.has(SpecialRight.PERSONNEL_COSTS),
            "tab": "prices",
        },
    )


@module_required(Module.PROJECTS)
def price_overview_file(request: HttpRequest, pk: int, file_format: str) -> HttpResponse:
    """The price overview as PDF or CSV, groups only or with all lines (DOK-009, PRJ-036).

    PRJ-046: like the page, with the parts the user may read. PRJ-088:
    ``?crew=phases`` with the personnel by phase and job function.
    """
    from rentalars.projects.price_pdf import render_price_overview_csv, render_price_overview_pdf

    rights = request_rights(request)
    require(rights.has(SpecialRight.PRICES))
    project = project_for(
        request,
        pk,
        ProjectAccess.READ,
        queryset=Project.objects.select_related("customer", "contact", "manager", "parent"),
    )
    with_lines = request.GET.get("detail", "lines") != "groups"
    viewer = {"rights": rights, "user": request.user, "crew_by_phase": request.GET.get("crew") == "phases"}
    if file_format == "csv":
        response = HttpResponse(
            render_price_overview_csv(project, with_lines=with_lines, **viewer), content_type="text/csv; charset=utf-8"
        )
        response["Content-Disposition"] = (
            f'attachment; filename="{file_name("price_overview", project.number, extension="csv")}"'
        )
        return response
    response = HttpResponse(
        render_price_overview_pdf(project, with_lines=with_lines, **viewer), content_type="application/pdf"
    )
    response["Content-Disposition"] = (
        f'inline; filename="{file_name("price_overview", project.number, extension="pdf")}"'
    )
    return response


@module_required(Module.PROJECTS)
def project_history(request: HttpRequest, pk: int) -> HttpResponse:
    """Who changed what and when in this project, its groups and lines (PRJ-032).

    EML-055: the subjects of mails and notes only for who may read them (``mail.history``).
    """
    from rentalars.mail.history import hide_unreadable
    from rentalars.mail.locks import correspondence_of

    project = project_for(request, pk, ProjectAccess.READ, queryset=Project.objects.select_related("customer"))
    page = paginate(request, AuditLogEntry.for_object(project))
    history = describe(list(page.object_list), request_rights(request))
    return render(
        request,
        "projects/history.html",
        {
            "project": project,
            "page": page,
            "history": hide_unreadable(history, correspondence_of(request, project), project),
            "tab": "history",
        },
    )
