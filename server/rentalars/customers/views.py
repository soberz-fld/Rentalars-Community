# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views of the customers module."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Level, Module, module_required, request_rights, require
from rentalars.core.history import describe
from rentalars.core.listing import paginate
from rentalars.core.models import AuditLogEntry
from rentalars.core.uploads import document_response
from rentalars.customers import greetings, services
from rentalars.customers.forms import ContactForm, CustomerAddressForm, CustomerForm, VenueForm
from rentalars.customers.models import Contact, Customer, CustomerAddress, GreetingStyle, Venue
from rentalars.customers.tables import CUSTOMER_TABLE, VENUE_TABLE
from rentalars.projects.access import visible_projects
from rentalars.projects.family_labels import whole_first


@module_required(Module.CUSTOMERS)
def customer_list(request: HttpRequest) -> HttpResponse:
    """All customers with search."""
    customers = Customer.objects.annotate(project_count=Count("projects"))
    text = request.GET.get("q", "").strip()
    if text:
        customers = customers.filter(
            Q(name__icontains=text) | Q(number__icontains=text) | Q(city__icontains=text) | Q(email__icontains=text)
        )
    if not request.GET.get("inactive"):
        customers = customers.filter(is_active=True)
    table = CUSTOMER_TABLE.state(request)
    customers = table.order(customers)
    if table.wants_csv:
        return table.csv_response(customers, _("Customers"))
    page = paginate(request, customers)
    return render(request, "customers/list.html", {"page": page, "table": table, "rows": table.rows(page), "q": text})


@module_required(Module.CUSTOMERS)
def customer_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """One customer with contacts, all projects (KND-007) and the material kept here (PRD-043)."""
    customer = get_object_or_404(Customer, pk=pk)
    rights = request_rights(request)
    # AUT-016: of the customer's projects, those the user may see.
    projects = (
        # PRJ-044: every part right after its whole project.
        whole_first(
            visible_projects(rights, request.user, customer.projects.select_related("parent")).order_by("-start")
        )
        if rights.can_read(Module.PROJECTS)
        else None
    )
    # PRD-043: the material the customer keeps here – for those who may see the products.
    if rights.can_read(Module.PRODUCTS):
        from rentalars.products.services import customer_material

        material = customer_material(customer)
    else:
        material = None
    # KND-004: each contact shows the greeting its mails begin with.
    from rentalars.core.i18n import document_language

    language = document_language()
    contacts = list(customer.contacts.all())
    for contact in contacts:
        contact.greeting_line = greetings.greeting(contact, language)  # type: ignore[attr-defined]
    from rentalars.documents.free import customer_panel

    return render(
        request,
        "customers/detail.html",
        {
            "customer": customer,
            "outgoing": customer_panel(rights, customer),  # Documents with or without a project
            "contacts": contacts,
            "addresses": customer.addresses.all(),
            "projects": projects,
            "material": material,
            "history": describe(list(AuditLogEntry.for_object(customer)[:30]), rights),
        },
    )


@module_required(Module.CUSTOMERS, Level.WRITE)
def customer_edit(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    """Create or edit a customer."""
    customer = get_object_or_404(Customer, pk=pk) if pk else None
    if customer is not None and customer.is_anonymised:
        messages.error(request, _("This customer was anonymised and can no longer be edited."))
        return redirect("customers:detail", pk=customer.pk)
    form = CustomerForm(request.POST or None, instance=customer, rights=request_rights(request))
    duplicates: list[services.PossibleDuplicate] = []
    if request.method == "POST" and form.is_valid():
        if customer is None and not form.cleaned_data.get("confirm_duplicate"):
            # KND-008: a possible duplicate needs a second, conscious "yes".
            duplicates = services.find_duplicates(form.cleaned_data["name"], form.cleaned_data["email"])
        if not duplicates:
            saved = services.save_customer(form.save(commit=False))
            messages.success(request, _("Customer saved."))
            return redirect("customers:detail", pk=saved.pk)
    return render(request, "customers/form.html", {"form": form, "customer": customer, "duplicates": duplicates})


def _created(field: str, pk: int, label: str) -> HttpResponse:
    """The answer of a dialog that created something: close it, and tell the form what was created (PRJ-070)."""
    response = HttpResponse(status=204)
    response["HX-Trigger"] = json.dumps(
        {"closeDialog": True, "objectCreated": {"field": field, "id": pk, "label": label}}
    )
    return response


@module_required(Module.CUSTOMERS, Level.WRITE)
def customer_quick_create(request: HttpRequest) -> HttpResponse:
    """A new customer in a dialog of the project form, with the questions of the customer management (PRJ-070).

    ``?name=`` takes over what was typed in the customer field; ``?field=``
    names the field of the form that receives the new customer.
    """
    field = request.GET.get("field", "customer")
    form = CustomerForm(
        request.POST or None, initial={"name": request.GET.get("name", "")}, rights=request_rights(request)
    )
    # A customer created in the middle of planning a project is in use at once. The dialog shows no
    # "active" box, and a box that is not sent counts as unticked: it created deactivated customers.
    form.fields.pop("is_active", None)
    duplicates: list[services.PossibleDuplicate] = []
    if request.method == "POST" and form.is_valid():
        if not form.cleaned_data.get("confirm_duplicate"):
            # KND-008: as on the page, a possible duplicate needs a second, conscious "yes".
            duplicates = services.find_duplicates(form.cleaned_data["name"], form.cleaned_data["email"])
        if not duplicates:
            saved = services.save_customer(form.save(commit=False))
            return _created(field, saved.pk, saved.name)
    return render(
        request,
        "customers/_quick_create.html",
        {"form": form, "duplicates": duplicates, "action": request.get_full_path()},
    )


@module_required(Module.CUSTOMERS, Level.WRITE)
def venue_quick_create(request: HttpRequest) -> HttpResponse:
    """A new venue in a dialog of the project form (PRJ-070)."""
    field = request.GET.get("field", "venue_site")
    form = VenueForm(request.POST or None, request.FILES or None, initial={"name": request.GET.get("name", "")})
    if request.method == "POST" and form.is_valid():
        saved = services.save_venue(form.save(commit=False))
        return _created(field, saved.pk, saved.name)
    return render(request, "customers/_venue_quick_create.html", {"form": form, "action": request.get_full_path()})


def venue_suggest(request: HttpRequest) -> JsonResponse:
    """Suggestions for the venue field of the project form (PRJ-070)."""
    rights = request_rights(request)
    require(rights.can_read(Module.CUSTOMERS) or rights.can_read(Module.PROJECTS))
    text = request.GET.get("q", "").strip()
    venues = Venue.objects.filter(is_active=True)
    if text:
        venues = venues.filter(Q(name__icontains=text) | Q(city__icontains=text))
    results: list[dict[str, Any]] = [
        {"id": venue.pk, "label": venue.name, "hint": venue.city} for venue in venues.order_by("name")[:12]
    ]
    if text and rights.can_write(Module.CUSTOMERS):
        results.append(
            {
                "id": "",
                "label": _("Create “%(name)s” as a new venue") % {"name": text},
                "create_url": f"{reverse('customers:venue_quick_create')}?{urlencode({'name': text})}",
                "create": True,
            }
        )
    return JsonResponse(results, safe=False)


@module_required(Module.CUSTOMERS)
def customer_duplicates(request: HttpRequest) -> HttpResponse:
    """The customers that resemble the one being typed in, as a page fragment (KND-008)."""
    duplicates = services.find_duplicates(request.GET.get("name", ""), request.GET.get("email", ""))
    return render(request, "customers/_duplicates.html", {"duplicates": duplicates, "live": True})


@require_POST
@module_required(Module.CUSTOMERS, Level.DELETE)
def customer_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a customer without projects (KND-010)."""
    customer = get_object_or_404(Customer, pk=pk)
    try:
        services.delete_customer(customer)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect("customers:detail", pk=pk)
    messages.success(request, _("Customer deleted."))
    return redirect("customers:list")


@require_POST
@module_required(Module.CUSTOMERS, Level.DELETE)
def customer_anonymise(request: HttpRequest, pk: int) -> HttpResponse:
    """Erase the personal data of a customer and keep the projects (KND-010)."""
    customer = get_object_or_404(Customer, pk=pk)
    services.anonymise_customer(customer)
    messages.success(request, _("The personal data of this customer was erased."))
    return redirect("customers:detail", pk=pk)


@module_required(Module.CUSTOMERS, Level.DELETE)
def customer_export(request: HttpRequest, pk: int) -> HttpResponse:
    """Everything stored about a customer as a file, for a request for information (NFA-009)."""
    customer = get_object_or_404(Customer, pk=pk)
    exported = services.export_customer(customer, rights=request_rights(request), user=request.user)
    body = json.dumps(exported, ensure_ascii=False, indent=2)
    response = HttpResponse(body, content_type="application/json; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="kunde-{customer.number}.json"'
    return response


@module_required(Module.CUSTOMERS, Level.WRITE)
def contact_edit(request: HttpRequest, customer_pk: int, pk: int | None = None) -> HttpResponse:
    """Create or edit a contact person (KND-004)."""
    customer = get_object_or_404(Customer, pk=customer_pk)
    contact = get_object_or_404(Contact, pk=pk, customer=customer) if pk else Contact(customer=customer)
    form = ContactForm(request.POST or None, instance=contact)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Contact saved."))
        return redirect("customers:detail", pk=customer.pk)
    # KND-004: the preview line starts with what the form holds (the instance follows the form while it is checked).
    line = greetings.greeting(contact) if contact.last_name or contact.name else ""
    return render(
        request, "customers/contact_form.html", {"form": form, "customer": customer, "contact": contact, "line": line}
    )


@module_required(Module.CUSTOMERS, Level.WRITE)
def contact_quick_create(request: HttpRequest, customer_pk: int) -> HttpResponse:
    """A new contact person of the customer in a dialog of the project form (PRJ-140).

    The choice "Neuer Ansprechpartner …" of the contact field opens it. The dialog asks for the name and the ways to reach the
    person; the greeting and "primary contact" are left to the page of the customer (the first contact of a customer
    becomes the primary one by itself). ``?field=`` names the field of the form that receives the new contact.
    """
    customer = get_object_or_404(Customer, pk=customer_pk)
    field = request.GET.get("field", "contact")
    form = ContactForm(request.POST or None, instance=Contact(customer=customer))
    for name in ("is_primary", "greeting_style", "greeting_text"):
        form.fields.pop(name)
    if request.method == "POST" and form.is_valid():
        # A second click or a repeated send of the same person adds nobody twice: the contact that exists is used.
        new = form.instance  # tidied by the validation: the parts of the name
        same = Contact.objects.filter(
            customer=customer,
            first_name__iexact=new.first_name or "",
            last_name__iexact=new.last_name or "",
            email__iexact=new.email or "",
        ).first()
        saved = same if same is not None else form.save()
        return _created(field, saved.pk, saved.name)
    return render(
        request,
        "customers/_contact_quick_create.html",
        {"form": form, "customer": customer, "action": request.get_full_path()},
    )


@module_required(Module.CUSTOMERS, Level.WRITE)
def contact_greeting_preview(request: HttpRequest) -> HttpResponse:
    """The greeting line of the contact being typed, as a page fragment (KND-004; htmx).

    Nothing is stored: the fields of the form are read from the query and put into an unsaved contact.
    """
    style = request.GET.get("greeting_style", "")
    contact = Contact(
        salutation=request.GET.get("salutation", "")[:40],
        first_name=request.GET.get("first_name", "")[:100],
        last_name=request.GET.get("last_name", "")[:100],
        greeting_style=style if style in GreetingStyle.values else GreetingStyle.FORMAL,
        greeting_text=request.GET.get("greeting_text", "")[:200],
    )
    contact.tidy_names()
    line = greetings.greeting(contact) if contact.last_name else ""
    return render(request, "customers/_greeting_preview.html", {"line": line})


@require_POST
@module_required(Module.CUSTOMERS, Level.WRITE)
def contact_delete(request: HttpRequest, customer_pk: int, pk: int) -> HttpResponse:
    """Delete a contact person."""
    get_object_or_404(Contact, pk=pk, customer_id=customer_pk).delete()
    messages.success(request, _("Contact deleted."))
    return redirect("customers:detail", pk=customer_pk)


@module_required(Module.CUSTOMERS, Level.WRITE)
def address_edit(request: HttpRequest, customer_pk: int, pk: int | None = None) -> HttpResponse:
    """Create or edit a further billing or delivery address (KND-005)."""
    customer = get_object_or_404(Customer, pk=customer_pk)
    address = get_object_or_404(CustomerAddress, pk=pk, customer=customer) if pk else CustomerAddress(customer=customer)
    form = CustomerAddressForm(request.POST or None, instance=address)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Address saved."))
        return redirect("customers:detail", pk=customer.pk)
    return render(request, "customers/address_form.html", {"form": form, "customer": customer, "address": address})


@require_POST
@module_required(Module.CUSTOMERS, Level.WRITE)
def address_delete(request: HttpRequest, customer_pk: int, pk: int) -> HttpResponse:
    """Delete a further address; projects that named it fall back to the customer's own address."""
    get_object_or_404(CustomerAddress, pk=pk, customer_id=customer_pk).delete()
    messages.success(request, _("Address deleted."))
    return redirect("customers:detail", pk=customer_pk)


def customer_suggest(request: HttpRequest) -> JsonResponse:
    """Suggestions for the customer search field of the project form.

    AUT-034: for who reads customers, edits projects (and chooses their customer) or sees the
    customers of all projects – not for whoever only reads assigned projects, such as the crew, who could list
    every customer by name otherwise.
    """
    from rentalars.projects.tables import may_see_customers

    rights = request_rights(request)
    require(rights.can_read(Module.CUSTOMERS) or rights.can_write(Module.PROJECTS) or may_see_customers(rights))
    text = request.GET.get("q", "").strip()
    customers = Customer.objects.filter(is_active=True)
    if text:
        customers = customers.filter(Q(name__icontains=text) | Q(number__icontains=text) | Q(city__icontains=text))
    results: list[dict[str, Any]] = [
        {"id": customer.pk, "label": customer.name, "hint": f"{customer.number} {customer.city}".strip()}
        for customer in customers.order_by("name")[:12]
    ]
    if text and rights.can_write(Module.CUSTOMERS):
        # PRJ-070: the last suggestion creates the customer right from the project form.
        results.append(
            {
                "id": "",
                "label": _("Create “%(name)s” as a new customer") % {"name": text},
                "create_url": f"{reverse('customers:quick_create')}?{urlencode({'name': text})}",
                "create": True,
            }
        )
    return JsonResponse(results, safe=False)


# --- Venues (KND-009) ---------------------------------------------------------------------


@module_required(Module.CUSTOMERS)
def venue_list(request: HttpRequest) -> HttpResponse:
    """All venues with search."""
    venues = Venue.objects.annotate(project_count=Count("projects"))
    text = request.GET.get("q", "").strip()
    if text:
        venues = venues.filter(Q(name__icontains=text) | Q(city__icontains=text) | Q(street__icontains=text))
    if not request.GET.get("inactive"):
        venues = venues.filter(is_active=True)
    table = VENUE_TABLE.state(request)
    venues = table.order(venues)
    if table.wants_csv:
        return table.csv_response(venues, _("Venues"))
    page = paginate(request, venues)
    return render(
        request, "customers/venue_list.html", {"page": page, "table": table, "rows": table.rows(page), "q": text}
    )


@module_required(Module.CUSTOMERS)
def venue_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """One venue with its notes and the projects that take place there."""
    venue = get_object_or_404(Venue, pk=pk)
    rights = request_rights(request)
    projects = (
        visible_projects(rights, request.user, venue.projects.select_related("parent")).order_by("-start")[:50]
        if rights.can_read(Module.PROJECTS)
        else None
    )
    return render(
        request,
        "customers/venue_detail.html",
        {
            "venue": venue,
            "projects": projects,
            "history": describe(list(AuditLogEntry.for_object(venue)[:30]), rights),
        },
    )


@module_required(Module.CUSTOMERS, Level.WRITE)
def venue_edit(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    """Create or edit a venue."""
    venue = get_object_or_404(Venue, pk=pk) if pk else None
    form = VenueForm(request.POST or None, request.FILES or None, instance=venue)
    if request.method == "POST" and form.is_valid():
        saved = services.save_venue(form.save(commit=False))
        messages.success(request, _("Venue saved."))
        return redirect("customers:venue_detail", pk=saved.pk)
    return render(request, "customers/venue_form.html", {"form": form, "venue": venue})


@require_POST
@module_required(Module.CUSTOMERS, Level.DELETE)
def venue_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a venue that is not in use."""
    venue = get_object_or_404(Venue, pk=pk)
    try:
        services.delete_venue(venue)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect("customers:venue_detail", pk=pk)
    messages.success(request, _("Venue deleted."))
    return redirect("customers:venue_list")


@module_required(Module.CUSTOMERS)
def venue_hall_plan(request: HttpRequest, pk: int) -> HttpResponse:
    """The hall plan of a venue, delivered after the rights were checked (NFA-007)."""
    venue = get_object_or_404(Venue, pk=pk)
    if not venue.hall_plan:
        raise Http404
    return document_response(venue.hall_plan.name, venue.hall_plan.name.rsplit("/", 1)[-1])
