# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views of the products module: products, kits, availability, rental scales."""

from __future__ import annotations

import datetime
from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, SpecialRight, module_required, request_rights, require
from rentalars.availability.engine import AvailabilityEngine
from rentalars.availability.stock import NO_STOCK, stock_of_products
from rentalars.core.forms import add_validation_error
from rentalars.core.history import describe
from rentalars.core.listing import paginate
from rentalars.core.models import AuditLogEntry
from rentalars.customers.models import Customer
from rentalars.masterdata.models import Category, RentalScale
from rentalars.material.models import MaterialItem, MaterialModel
from rentalars.material.numbering import id_range_for_prefix
from rentalars.products import services
from rentalars.products.forms import AvailabilityQueryForm, KitComponentForm, ProductForm, RentalScaleForm
from rentalars.products.models import KitComponent, Product, ProductKind
from rentalars.products.scale_tables import SCALE_TABLE
from rentalars.products.tables import PRODUCT_TABLE, attach_stock
from rentalars.projects.access import ProjectAccess, access_level, readable_projects, visible_projects
from rentalars.projects.models import Project
from rentalars.projects.product_changes import changes_of_product, take_over_changes

#: The product page shows the utilisation of the coming days by default.
DEFAULT_QUERY_DAYS = 14


def _is_number(text: str) -> bool:
    """Whether the text is a whole number of ASCII digits (``"²".isdigit()`` is true, ``int("²")`` fails)."""
    return text.isascii() and text.isdigit()


@module_required(Module.PRODUCTS)
def product_list(request: HttpRequest) -> HttpResponse:
    """All products with search by article number, name, GTIN and category (PRD-025).

    Columns can be chosen and sorted (UIX-015); the filtered list comes as CSV (IMP-005).
    """
    products = Product.objects.select_related("category__parent", "unit", "tax_rate", "owner")
    text = request.GET.get("q", "").strip()
    if text:
        products = products.filter(
            Q(article_number__icontains=text)
            | Q(name__icontains=text)
            | Q(gtin__icontains=text)
            | Q(category__name__icontains=text)
        )
    category_id = request.GET.get("category", "")
    if category_id.isascii() and category_id.isdigit():
        products = products.filter(category_id__in=Category.objects.descendant_ids(int(category_id)))
    kind = request.GET.get("kind", "")
    if kind in ProductKind.values:
        products = products.filter(kind=kind)
    # PRD-043: "own material", "customer material", or the material of one customer.
    owner = request.GET.get("owner", "")
    if owner == "own":
        products = products.filter(owner__isnull=True)
    elif owner == "customers":
        products = products.filter(owner__isnull=False)
    elif owner.isascii() and owner.isdigit():
        products = products.filter(owner_id=int(owner))
    if not request.GET.get("inactive"):
        products = products.filter(is_active=True)
    if request.GET.get("below_minimum"):
        # PRD-020: what has to be re-ordered.
        from rentalars.material.services import low_stock_products

        products = products.filter(pk__in=[entry.product.pk for entry in low_stock_products()])
    table = PRODUCT_TABLE.state(request)
    products = table.order(products)
    if table.wants_csv:
        return table.csv_response(attach_stock(list(products)), _("Products"))
    page = paginate(request, products)
    attach_stock(page.object_list)
    return render(
        request,
        "products/list.html",
        {
            "page": page,
            "table": table,
            "rows": table.rows(page),
            "q": text,
            "categories": Category.objects.in_tree_order(),
            "category_id": category_id,
            "kinds": ProductKind.choices,
            "kind": kind,
            "owner": owner,
            "owners": Customer.objects.filter(owned_products__isnull=False).distinct().order_by("name"),
        },
    )


def _unconfirmed_changes(request: HttpRequest, product: Product) -> list[dict[str, Any]]:
    """PRJ-072: the projects not yet confirmed whose lines have not taken over what changed at the product.

    Only projects the user may read are named (AUT-016). Each entry holds the project, its changed lines of this
    product and whether the user may take the changes over there.
    """
    rights = request_rights(request)
    found = changes_of_product(product, rights)
    if not found:
        return []
    visible = set(
        readable_projects(rights, request.user)
        .filter(pk__in=[project.pk for project in found])
        .values_list("pk", flat=True)
    )
    return [
        {
            "project": project,
            "changes": changes,
            "can_edit": not project.is_locked and access_level(rights, request.user, project) >= ProjectAccess.EDIT,
        }
        for project, changes in found.items()
        if project.pk in visible
    ]


@module_required(Module.PRODUCTS)
def product_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """One product: master data, assigned material, stock and utilisation (PRD-026, VFG-011; PRD-050)."""
    product = get_object_or_404(
        Product.objects.select_related("category", "unit", "tax_rate", "rental_scale", "owner"), pk=pk
    )
    rights = request_rights(request)

    now = timezone.localtime().replace(minute=0, second=0, microsecond=0)
    initial = {"start": now, "end": now + datetime.timedelta(days=DEFAULT_QUERY_DAYS)}
    # Product number in the planning: coming from a project, the period of the project is asked first.
    from_project = _project_of_query(request, rights)
    if from_project is not None:
        initial = {"start": timezone.localtime(from_project.start), "end": timezone.localtime(from_project.end)}
    query_form = AvailabilityQueryForm(request.GET if "start" in request.GET else None, initial=initial)
    if query_form.is_bound and query_form.is_valid():
        start, end = query_form.cleaned_data["start"], query_form.cleaned_data["end"]
    else:
        start, end = initial["start"], initial["end"]
    # AUT-032: the availability – and with it who occupies the product – only with the special right.
    sees_availability = rights.has(SpecialRight.AVAILABILITY)
    availability = (
        AvailabilityEngine().availability([product.pk], start, end)[product.pk] if sees_availability else None
    )

    # AUT-016: the projects that occupy the product are named only to those who may see them.
    occupying = {demand.project_id for demand in availability.occupiers} if availability is not None else set()
    visible_ids = set(visible_projects(rights, request.user).filter(pk__in=occupying).values_list("pk", flat=True))

    context: dict[str, Any] = {
        "product": product,
        "availability": availability,
        "visible_project_ids": visible_ids,
        "from_project": from_project,
        "query_form": query_form,
        "query_start": start,
        "query_end": end,
        "models": MaterialModel.objects.filter(default_product=product).select_related("manufacturer"),
        "items": MaterialItem.objects.for_product(product.pk)
        .select_related("material_model", "installed_in")
        .order_by("inventory_number")[:200],
        "components": product.components.select_related("component"),
        "used_in_kits": KitComponent.objects.filter(component=product).select_related("kit"),
        "component_form": KitComponentForm(),
        "effective_scale": product.effective_rental_scale(),
        # PRD-044: a service belongs to one job function; the page links to it.
        "service_job_function": product.service_job_function if product.kind == ProductKind.SERVICE else None,
        "history": describe(list(AuditLogEntry.for_object(product)[:30]), rights),
        "low_stock": _low_stock(product),
        "tab": "product",
        # PRD-051 (VFG-025): the product chosen there, over the period chosen here.
        "utilization_url": _utilization_url(product, rights, start, end),
        # PRJ-072: projects not yet confirmed that have not taken over the changes of this product.
        "unconfirmed_changes": _unconfirmed_changes(request, product),
    }
    return render(request, "products/detail.html", context)


def _project_of_query(request: HttpRequest, rights: Any) -> Any:
    """The project named in ``?project=`` if the user may read it, else ``None`` (product number in the planning; PRJ-126).

    The planning links its article numbers to the product page with the project; the page then asks for the
    project's rental period first and names the project with a way back. A number that is not a number, a project
    that does not exist and one the user may not read are all ignored alike – nothing is told about it (AUT-016).
    """
    wanted = request.GET.get("project", "")
    if not (wanted.isascii() and wanted.isdigit()) or len(wanted) > 9:  # "²".isdigit() is true, int("²") fails
        return None
    project = Project.objects.filter(pk=int(wanted)).first()
    if project is None or access_level(rights, request.user, project) < ProjectAccess.READ:
        return None
    return project


def _utilization_url(product: Product, rights: Any, start: datetime.datetime, end: datetime.datetime) -> str:
    """The address of "Planung → Materialauslastung" with this product and period, or "" (PRD-051; VFG-025).

    Only for products the utilization shows – with stock of their own, or
    kits – and for users who may open it: project rights in all projects and
    read access to products, as ``schedule.views.products`` asks.
    """
    from rentalars.schedule.services import utilization_address

    if not (product.tracks_stock or product.is_kit):
        return ""
    if not rights.can_read(Module.PROJECTS) or rights.is_limited_to_assigned_projects(Module.PROJECTS):
        return ""
    if not rights.has(SpecialRight.AVAILABILITY):
        return ""  # AUT-032: the utilization needs the special right to see availability
    return utilization_address(product.pk, start, end)


def _low_stock(product: Product) -> Any:
    """The shortfall below the minimum stock, or ``None`` (PRD-020)."""
    if not product.minimum_stock:
        return None
    from rentalars.material.services import LowStock

    stock = stock_of_products([product.pk]).get(product.pk, NO_STOCK).operational
    return LowStock(product, stock, product.minimum_stock) if stock < product.minimum_stock else None


@module_required(Module.PRODUCTS)
def product_timeline(request: HttpRequest, pk: int) -> HttpResponse:
    """Free pieces per day and which project takes how many (VFG-019)."""
    from rentalars.schedule.services import span_from_request
    from rentalars.schedule.timelines import product_timeline as build

    require(request_rights(request).has(SpecialRight.AVAILABILITY))  # AUT-032: availability as a special right
    product = get_object_or_404(Product.objects.select_related("category", "unit", "owner"), pk=pk)
    days, navigation = span_from_request(request, default_weeks=4)
    visible = set(visible_projects(request_rights(request), request.user).values_list("pk", flat=True))
    return render(
        request,
        "products/timeline.html",
        {
            "product": product,
            "timeline": build(product, days, visible),
            "low_stock": _low_stock(product),
            "tab": "timeline",
            **navigation,
        },
    )


@module_required(Module.PRODUCTS, Level.WRITE)
def product_edit(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    """Create or edit a product.

    For a new product, choosing the category reloads the form with the
    presets of that category and the next free article number (PRD-010,
    PRD-030). PRD-046: the kind is asked before the category; ``?kind=``
    keeps it and puts the categories that preset it first.

    PRD-048: ``?duplicate=`` names a product the new one
    is made from – the form is filled with its values and the next free
    article number of its category (``services.duplicate_values``); nothing
    is saved before "Save product". A category chosen afterwards brings its
    next article number, the rest stays as copied. Saving takes over the
    components of a kit as well.

    PRD-049: in the form of an existing
    product – such as the one "Create as product" made from a model
    (MAT-051) – choosing another category replaces the article number
    (``article_number_field``).
    """
    product = get_object_or_404(Product, pk=pk) if pk else None
    rights = request_rights(request)
    source = _duplicate_source(request) if product is None else None
    initial: dict[str, Any] = {}
    category = None
    if product is None and _is_number(request.GET.get("category", "")):
        category = Category.objects.filter(pk=int(request.GET["category"])).first()
        if category is not None:
            initial = {"category": category, **services.presets_for_category(category)}
    if source is not None:
        initial = services.duplicate_values(source, rights)
        if category is not None:
            initial.update(category=category, article_number=services.suggest_article_number(category))
    if product is None and _is_number(request.GET.get("owner", "")):
        # PRD-043: "add material" on the customer's page – the category for customer material and the owner set.
        initial.update(services.presets_for_owner(int(request.GET["owner"]), initial.get("category") or category))
    kind = request.GET.get("kind", "")
    if product is None and kind in ProductKind.values and (source is None or kind != source.kind):
        # PRD-046: the kind is chosen first and stays when the category is chosen after it.
        initial.update(services.presets_for_kind(kind, initial.get("category")))
    form = ProductForm(request.POST or None, instance=product, initial=initial, rights=rights)
    if source is not None:
        # Choosing kind or category reloads the form; the copy stays a copy (static/js/app.js, PRD-046).
        form.fields["kind"].widget.attrs["data-reload-fields"] += " duplicate"
    if request.method == "POST" and form.is_valid():
        candidate = form.save(commit=False)
        try:
            if source is not None:
                services.save_duplicate(candidate, source, rights)
            else:
                services.save_product(candidate, rights)
        except ValidationError as error:
            add_validation_error(form, error)
        else:
            messages.success(request, _("Product %(number)s saved.") % {"number": candidate.article_number})
            if product is not None:
                _warn_of_unconfirmed_projects(request, candidate)
            return redirect("products:detail", pk=candidate.pk)
    context = {"form": form, "product": product, "duplicate_of": source}
    if source is not None and source.is_kit:
        context["duplicate_components"] = source.components.select_related("component")
    return render(request, "products/form.html", context)


def _warn_of_unconfirmed_projects(request: HttpRequest, product: Product) -> None:
    """PRJ-072: after a change, say in how many projects not yet confirmed the product is out of date."""
    count = len(_unconfirmed_changes(request, product))
    if count:
        messages.warning(
            request,
            ngettext(
                "%(count)d project that is not fully confirmed yet has lines that differ from this product. "
                "Check them below and take the changes over.",
                "%(count)d projects that are not fully confirmed yet have lines that differ from this product. "
                "Check them below and take the changes over.",
                count,
            )
            % {"count": count},
        )


def _duplicate_source(request: HttpRequest) -> Product | None:
    """PRD-048: the product named by ``duplicate`` – in the address, or sent with the form."""
    value = request.POST.get("duplicate") or request.GET.get("duplicate", "")
    return Product.objects.select_related("category").filter(pk=int(value)).first() if _is_number(value) else None


@module_required(Module.PRODUCTS, Level.WRITE)
def article_number_field(request: HttpRequest, pk: int) -> HttpResponse:
    """The field "article number" of a product's form for the category chosen in it (PRD-049; PRD-008, PRD-010).

    Asked by the form of an existing product when its category changes –
    above all the product "Create as product" made from a model (MAT-051),
    which starts with the next number of the model's category. The number
    the product has stays while it fits the category, else the next free
    number of the chosen category is proposed (``services.article_number_for``);
    nothing is saved. An article number used in projects still needs the
    special right to be changed when saving (PRD-011).
    """
    product = get_object_or_404(Product, pk=pk)
    value = request.GET.get("category", "")
    category = Category.objects.filter(pk=int(value)).first() if _is_number(value) else None
    number = services.article_number_for(category, product) if category is not None else product.article_number
    form = ProductForm(instance=product, initial={"article_number": number}, rights=request_rights(request))
    return render(request, "products/_article_number.html", {"form": form, "product": product})


@require_POST
@module_required(Module.PRODUCTS, Level.WRITE)
def product_take_over_changes(request: HttpRequest, pk: int) -> HttpResponse:
    """Take over the changes of the product in the projects that are not confirmed yet (PRJ-072).

    ``project`` names one project (several times: several projects); without it every project the user may edit
    is taken. Lines with a value set by hand stay as they are - the planning of the project decides on them.
    Prices come along only for who has the price right.
    """
    product = get_object_or_404(Product, pk=pk)
    rights = request_rights(request)
    wanted = {int(value) for value in request.POST.getlist("project") if _is_number(value)}
    lines_done = projects_done = 0
    for entry in _unconfirmed_changes(request, product):
        project = entry["project"]
        if not entry["can_edit"] or (wanted and project.pk not in wanted):
            continue
        try:
            result = take_over_changes(project, rights=rights, automatic=True, only_product=product)
        except ValidationError:
            continue
        if result.taken_over:
            projects_done += 1
            lines_done += result.taken_over
    if lines_done:
        messages.success(
            request,
            ngettext(
                "%(lines)d line in %(projects)d project now has the current values of this product.",
                "%(lines)d lines in %(projects)d projects now have the current values of this product.",
                lines_done,
            )
            % {"lines": lines_done, "projects": projects_done},
        )
    else:
        messages.info(request, _("Nothing to take over: the lines with values set by hand stay as they are."))
    return redirect("products:detail", pk=product.pk)


@require_POST
@module_required(Module.PRODUCTS, Level.WRITE)
def product_set_active(request: HttpRequest, pk: int) -> HttpResponse:
    """Deactivate or reactivate a product (PRD-024)."""
    product = get_object_or_404(Product, pk=pk)
    product.is_active = request.POST.get("active") == "1"
    product.save()
    messages.success(request, _("Product %(number)s saved.") % {"number": product.article_number})
    return redirect("products:detail", pk=product.pk)


@require_POST
@module_required(Module.PRODUCTS, Level.DELETE)
def product_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a product that was never used; used products are deactivated (PRD-024)."""
    product = get_object_or_404(Product, pk=pk)
    if (
        product.is_used_in_projects()
        or product.material_models.exists()
        or product.override_items.exists()
        or product.used_in_kits.exists()
    ):
        messages.error(request, _("This product is in use. Deactivate it instead of deleting it."))
        return redirect("products:detail", pk=product.pk)
    function = product.service_job_function
    if function is not None:
        # PRD-044: the service product goes only together with its job function.
        messages.error(
            request,
            _(
                "This is the service product of the job function %(function)s. Delete the job function under "
                "Personnel → Job functions; its service product goes with it."
            )
            % {"function": function.name},
        )
        return redirect("products:detail", pk=product.pk)
    product.delete()
    messages.success(request, _("Product deleted."))
    return redirect("products:list")


@require_POST
@module_required(Module.PRODUCTS, Level.WRITE)
def component_add(request: HttpRequest, pk: int) -> HttpResponse:
    """Add a component to a kit, or raise its quantity (PRD-022)."""
    kit = get_object_or_404(Product, pk=pk, kind=ProductKind.KIT)
    form = KitComponentForm(request.POST)
    if form.is_valid():
        components = [
            (component.component, component.quantity) for component in kit.components.select_related("component")
        ]
        components.append((form.cleaned_data["component"], form.cleaned_data["quantity"]))
        try:
            services.set_kit_components(kit, components)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, _("Component added."))
    else:
        messages.error(request, _("Choose a product from the list and enter a quantity."))
    return redirect("products:detail", pk=kit.pk)


@require_POST
@module_required(Module.PRODUCTS, Level.WRITE)
def component_remove(request: HttpRequest, pk: int, component_pk: int) -> HttpResponse:
    """Remove a component from a kit."""
    component = get_object_or_404(KitComponent, pk=component_pk, kit_id=pk)
    component.delete()
    messages.success(request, _("Component removed."))
    return redirect("products:detail", pk=pk)


def product_suggest(request: HttpRequest) -> JsonResponse:
    """Suggestions for product search fields: active products by number or name.

    Used when adding lines to a project, so read access to projects is
    enough; ``?kind=`` narrows the suggestions, ``?exclude_kind=`` leaves
    kinds out.

    With ``?with_material=1`` the search also looks at the material behind
    the products (PRJ-065): a model name ("Cordial CPM") or the ID or serial
    number of an item ("0042") leads to the product it belongs to. Such a
    suggestion carries the model or item in its ``id`` – see
    ``projects.views.parse_material_choice`` – and names it in ``detail``.

    PRD-043, PRJ-096: customer material is offered only with ``?project=``
    naming a project of its owner (a subproject has the customer of its
    whole project), or with ``?owner=`` for the components of a kit of
    customer material; everywhere else only own material is.
    """
    rights = request_rights(request)
    require(rights.can_read(Module.PRODUCTS) or rights.can_read(Module.PROJECTS))
    text = request.GET.get("q", "").strip()
    owner_id = _owner_for_suggestions(request)
    products = Product.objects.filter(is_active=True).select_related("unit")
    products = (
        products.filter(Q(owner__isnull=True) | Q(owner_id=owner_id))
        if owner_id
        else products.filter(owner__isnull=True)
    )
    if text:
        products = products.filter(Q(article_number__icontains=text) | Q(name__icontains=text) | Q(gtin=text))
    if request.GET.get("kind") in ProductKind.values:
        products = products.filter(kind=request.GET["kind"])
    excluded = [kind for kind in request.GET.get("exclude_kind", "").split(",") if kind in ProductKind.values]
    if excluded:
        products = products.exclude(kind__in=excluded)
    products = list(products.order_by("article_number")[:12])
    stocks = stock_of_products([product.pk for product in products])
    results: list[dict[str, Any]] = []
    for product in products:
        stock = stocks.get(product.pk)
        hint = f"{stock.plannable} {product.unit.abbreviation}" if stock else product.get_kind_display()
        if product.owner_id:
            hint = _("customer material, %(stock)s") % {"stock": hint}  # PRJ-096
        results.append({"id": product.pk, "label": f"{product.article_number} {product.name}", "hint": hint})
    if text and request.GET.get("with_material"):
        results.extend(_material_suggestions(text, owner_id))
    return JsonResponse(results, safe=False)


def _owner_for_suggestions(request: HttpRequest) -> int | None:
    """The customer whose material the product search may offer: that of the project in ``?project=`` (PRJ-096).

    Only a project the user may see counts; any other value offers own material only. The components of a
    kit of customer material name its owner in ``?owner=`` (PRD-043).
    """
    owner = request.GET.get("owner", "")
    if _is_number(owner) and request_rights(request).can_read(Module.PRODUCTS):
        return int(owner)
    project_id = request.GET.get("project", "")
    if not _is_number(project_id):
        return None
    visible = visible_projects(request_rights(request), request.user).filter(pk=int(project_id))
    return visible.values_list("customer_id", flat=True).first()


#: How many models and how many items the product search adds to its suggestions.
MATERIAL_SUGGESTIONS = 6


def _material_suggestions(text: str, owner_id: int | None = None) -> list[dict[str, Any]]:
    """Find models and items for the product search and say which product each leads to (PRJ-065).

    Only material that can be planned is offered: the product must exist and
    be active, and an item must not be archived. Customer material only of
    ``owner_id`` (PRJ-096).
    """
    results: list[dict[str, Any]] = []
    models = (
        MaterialModel.objects.filter(Q(name__icontains=text) | Q(short_name__icontains=text))
        .filter(default_product__is_active=True)
        .filter(Q(default_product__owner__isnull=True) | Q(default_product__owner_id=owner_id))
        .exclude(default_product__kind=ProductKind.VEHICLE)  # LOG-001: vehicles go under "Logistik"
        .select_related("default_product")
        .order_by("name")[:MATERIAL_SUGGESTIONS]
    )
    for model in models:
        product = model.default_product
        results.append(
            {
                "id": f"{product.pk}:m{model.pk}",
                "label": f"{product.article_number} {product.name}",
                "detail": _("Model %(name)s") % {"name": model.name},
                "hint": _("model"),
            }
        )

    items = MaterialItem.objects.not_archived().select_related(
        "material_model", "material_model__default_product", "product_override"
    )
    id_range = id_range_for_prefix(text)
    if id_range is not None:
        # While an ID is being typed, offer every ID that starts with the digits so far.
        items = items.filter(Q(inventory_number__range=id_range) | Q(serial_number__icontains=text))
    else:
        items = items.filter(serial_number__icontains=text)
    for item in items.order_by("inventory_number")[:MATERIAL_SUGGESTIONS]:
        product = item.product
        if product is None or not product.is_active or product.owner_id not in (None, owner_id):
            continue
        if product.kind == ProductKind.VEHICLE:
            continue  # LOG-001: booked under "Logistik", not as material
        detail = _("Item %(id)s, %(model)s") % {"id": item.display_id, "model": item.material_model.display_short_name}
        if item.serial_number:
            detail += ", " + _("serial no. %(serial)s") % {"serial": item.serial_number}
        results.append(
            {
                "id": f"{product.pk}:i{item.pk}",
                "label": f"{product.article_number} {product.name}",
                "detail": detail,
                "hint": _("item") if item.is_operational else item.get_status_display(),
            }
        )
    return results


# --- Rental scales (PRD-015) ---------------------------------------------------------


@module_required(Module.PRODUCTS)
def scale_list(request: HttpRequest) -> HttpResponse:
    """All rental scales with their current tables – a table of core.tables (UIX-040)."""
    can_edit = request_rights(request).has(SpecialRight.EDIT_RENTAL_SCALES)
    table = SCALE_TABLE.state(request)
    scales = table.order(RentalScale.objects.prefetch_related("categories"))
    if table.wants_csv:
        return table.csv_response(scales, _("Rental scales"))
    page = table.paginate(scales)  # UIX-050 (UIX-012)
    scales = list(page)
    for scale in scales:
        scale.can_edit = can_edit  # the name leads to the form only for who may change scales
    return render(
        request,
        "products/scale_list.html",
        {"scales": scales, "table": table, "rows": table.rows(scales), "page": page, "can_edit": can_edit},
    )


def scale_edit(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    """Create a rental scale or edit its table (PRD-015).

    Saving a changed table creates a new version. Existing project lines keep
    calculating with the version they were created with (PRD-037).
    """
    require(request_rights(request).has(SpecialRight.EDIT_RENTAL_SCALES))
    scale = get_object_or_404(RentalScale, pk=pk) if pk else None
    form = RentalScaleForm(request.POST or None, instance=scale)
    if request.method == "POST" and form.is_valid():
        saved = form.instance
        saved.name = form.cleaned_data["name"]
        saved.is_default = form.cleaned_data["is_default"]
        saved.is_active = form.cleaned_data["is_active"]
        saved.save()
        try:
            saved.publish(
                form.cleaned_data["rows"],
                extra_day_increment=form.cleaned_data["extra_day_increment"],
                created_by=request.user,
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, _("Rental scale saved. New project lines calculate with this table."))
            return redirect("products:scale_list")
    return render(request, "products/scale_form.html", {"form": form, "scale": scale})
