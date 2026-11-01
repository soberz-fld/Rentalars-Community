# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the customers module (chapter 8)."""

from __future__ import annotations

from typing import Any, ClassVar

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Level, Module, SpecialRight, request_rights
from rentalars.api.errors import RecordAnonymised
from rentalars.api.serializers import CleanModelSerializer, RestrictedFieldsMixin
from rentalars.api.views import ModuleViewSet
from rentalars.core.maps import one_line, route_url, venue_address
from rentalars.customers import greetings, services
from rentalars.customers.models import Contact, Customer, CustomerAddress, Venue
from rentalars.customers.names import parse_name


def _address_line(record: Customer | CustomerAddress) -> str:
    """UIX-033: street, postal code and city, country in one line."""
    return one_line(record.street, f"{record.postal_code} {record.city}", record.country)


class ContactSerializer(CleanModelSerializer):
    """A contact person of a customer (KND-004).

    ``first_name`` and ``last_name`` (the last name is needed). ``name`` is the full name derived from them;
    clients that know only ``name`` keep working – a ``name`` sent without first and last name is split
    (:func:`~rentalars.customers.names.parse_name`: "Anna Berg" is "Anna" and "Berg"). The greeting of mails to the
    contact is ``greeting_style`` (``formal``, ``personal``, ``custom``) and ``greeting_text`` (for ``custom``);
    ``greeting`` is the resulting line, in the language of the company's documents (read only).
    """

    name = serializers.CharField(
        required=False, max_length=200, help_text="The full name; derived from first and last name."
    )
    greeting = serializers.SerializerMethodField(help_text="The greeting line of mails to this contact.")

    class Meta:
        model = Contact
        fields = [
            "id",
            "customer",
            "salutation",
            "name",
            "first_name",
            "last_name",
            "position",
            "email",
            "phone",
            "is_primary",
            "greeting_style",
            "greeting_text",
            "greeting",
        ]
        read_only_fields = ["customer"]

    def get_greeting(self, contact: Contact) -> str:
        """The greeting line, e.g. "Sehr geehrte Frau Berg,"."""
        return greetings.greeting(contact)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """A bare ``name`` (old clients) is split into first and last name; sent with the parts, they win."""
        attrs = super().validate(attrs)
        name = attrs.pop("name", None)
        if name is None:
            return attrs
        known = self.instance
        if attrs.get("first_name") or attrs.get("last_name"):
            return attrs  # the parts win
        if known is not None and name == known.name:
            return attrs  # the old client sends back the name it read: nothing changed
        parsed = parse_name(name)
        attrs["first_name"], attrs["last_name"] = parsed.first_name, parsed.last_name
        # A leading "Frau" and a remark after a comma are kept where the contact has no salutation or position yet.
        for field, value in (("salutation", parsed.salutation), ("position", parsed.remark)):
            if value and not attrs.get(field, getattr(known, field, "")):
                attrs[field] = value[: Contact._meta.get_field(field).max_length]
        return attrs


class CustomerSerializer(RestrictedFieldsMixin, CleanModelSerializer):
    """A customer (KND-003) with commercial details (KND-006). The customer number is assigned automatically.

    The standard discount is only visible with the price right (AUT-019).
    """

    restricted_fields: ClassVar[dict[str, str]] = {"default_discount_percent": SpecialRight.PRICES}
    #: UIX-033: the link into the route planning of Google Maps, from where the viewer is.
    route_url = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = [
            "id",
            "number",
            "kind",
            "name",
            "name_addition",
            "street",
            "postal_code",
            "city",
            "country",
            "route_url",
            "email",
            "phone",
            "vat_id",
            "tax_number",
            "buyer_reference",
            "payment_terms_days",
            "default_discount_percent",
            "note",
            "is_active",
            "anonymised_at",
        ]
        read_only_fields = ["number", "anonymised_at"]
        # The model tidies "de 123 456 789" before it checks the VAT ID; checking here would refuse it.
        extra_kwargs = {"vat_id": {"validators": []}}

    def create(self, validated_data: dict[str, Any]) -> Customer:
        """Create the customer with the next customer number."""
        return services.save_customer(Customer(**validated_data))

    def get_route_url(self, customer: Customer) -> str:
        """UIX-033: the route to the billing address in Google Maps; empty without an address."""
        return route_url(_address_line(customer))


class CustomerViewSet(ModuleViewSet):
    """``/customers`` – customers with projects cannot be deleted, only deactivated (KND-010)."""

    module = Module.CUSTOMERS
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    search_fields = ["name", "number", "city", "email"]
    filterset_fields = ["kind", "is_active"]
    ordering_fields = ["name", "number", "city"]
    action_levels = {"anonymise": Level.DELETE, "export": Level.DELETE}

    def perform_update(self, serializer: Any) -> None:
        """L8: an anonymised customer stays anonymised – the pages refuse it too."""
        if serializer.instance.is_anonymised:
            raise RecordAnonymised
        super().perform_update(serializer)

    def perform_destroy(self, instance: Customer) -> None:
        """Delete only customers without projects."""
        services.delete_customer(instance)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Create the customer; customers that resemble it are named in ``possible_duplicates`` (KND-008).

        The API does not refuse: a client that wants to ask first calls
        ``/customers/duplicates``.
        """
        response = super().create(request, *args, **kwargs)
        new_id = response.data.get("id")
        duplicates = services.find_duplicates(
            str(request.data.get("name", "")), str(request.data.get("email", "")), exclude_pk=new_id
        )
        response.data["possible_duplicates"] = [_duplicate_document(duplicate) for duplicate in duplicates]
        return response

    @extend_schema(
        parameters=[OpenApiParameter("name", str), OpenApiParameter("email", str)],
        responses={
            200: inline_serializer(
                "PossibleDuplicate",
                {"id": serializers.IntegerField(), "name": serializers.CharField(), "reason": serializers.CharField()},
                many=True,
            )
        },
    )
    @action(detail=False)
    def duplicates(self, request: Request) -> Response:
        """Customers that may be the same as one with this name or e-mail address (KND-008)."""
        found = services.find_duplicates(request.query_params.get("name", ""), request.query_params.get("email", ""))
        return Response([_duplicate_document(duplicate) for duplicate in found])

    @extend_schema(responses={200: inline_serializer("CustomerExport", {"exported_at": serializers.DateTimeField()})})
    @action(detail=True)
    def export(self, request: Request, pk: str | None = None) -> Response:
        """Everything stored about a customer, for a request for information (NFA-009)."""
        return Response(services.export_customer(self.get_object(), rights=request_rights(request), user=request.user))

    @extend_schema(request=None, responses=CustomerSerializer)
    @action(detail=True, methods=["post"])
    def anonymise(self, request: Request, pk: str | None = None) -> Response:
        """Erase the personal data of a customer but keep the projects (KND-010)."""
        customer = self.get_object()
        services.anonymise_customer(customer)
        return Response(self.get_serializer(customer).data)


class ContactViewSet(ModuleViewSet):
    """``/customers/{customer_id}/contacts`` – the contact persons of one customer."""

    module = Module.CUSTOMERS
    queryset = Contact.objects.none()
    serializer_class = ContactSerializer
    pagination_class = None

    def get_customer(self) -> Customer:
        """The customer named in the address."""
        return get_object_or_404(Customer, pk=self.kwargs["customer_pk"])

    def get_queryset(self) -> Any:
        """Only the contacts of that customer."""
        return Contact.objects.filter(customer_id=self.kwargs.get("customer_pk"))

    def perform_create(self, serializer: Any) -> None:
        """Attach the new contact to the customer from the address."""
        serializer.save(customer=self.get_customer())


def _duplicate_document(duplicate: services.PossibleDuplicate) -> dict[str, Any]:
    customer = duplicate.customer
    return {"id": customer.pk, "number": customer.number, "name": customer.name, "reason": str(duplicate.reason)}


class CustomerAddressSerializer(CleanModelSerializer):
    """A further billing or delivery address of a customer (KND-005); ``route_url`` (UIX-033)."""

    route_url = serializers.SerializerMethodField()

    class Meta:
        model = CustomerAddress
        fields = [
            "id",
            "customer",
            "kind",
            "label",
            "name",
            "name_addition",
            "street",
            "postal_code",
            "city",
            "country",
            "route_url",
            "is_default",
        ]
        read_only_fields = ["customer"]

    def get_route_url(self, address: CustomerAddress) -> str:
        """UIX-033: the route in Google Maps, from the viewer's current location."""
        return route_url(_address_line(address))


class CustomerAddressViewSet(ModuleViewSet):
    """``/customers/{customer_id}/addresses`` – the further addresses of one customer (KND-005)."""

    module = Module.CUSTOMERS
    queryset = CustomerAddress.objects.none()
    serializer_class = CustomerAddressSerializer
    pagination_class = None

    def get_queryset(self) -> Any:
        """Only the addresses of that customer."""
        return CustomerAddress.objects.filter(customer_id=self.kwargs.get("customer_pk"))

    def perform_create(self, serializer: Any) -> None:
        """Attach the new address to the customer from the address."""
        serializer.save(customer=get_object_or_404(Customer, pk=self.kwargs["customer_pk"]))


class VenueSerializer(CleanModelSerializer):
    """A venue (KND-009). The hall plan is uploaded in the browser; here it is only named."""

    has_hall_plan = serializers.SerializerMethodField()
    #: UIX-033: the route in Google Maps, from the viewer's current location.
    route_url = serializers.SerializerMethodField()

    class Meta:
        model = Venue
        fields = [
            "id",
            "name",
            "street",
            "postal_code",
            "city",
            "country",
            "contact_name",
            "contact_phone",
            "contact_email",
            "access_notes",
            "power_notes",
            "notes",
            "is_active",
            "has_hall_plan",
            "route_url",
        ]

    def get_has_hall_plan(self, venue: Venue) -> bool:
        """Whether a hall plan is stored."""
        return bool(venue.hall_plan)

    def get_route_url(self, venue: Venue) -> str:
        """UIX-033: the route to the venue in Google Maps, from the viewer's current location."""
        return route_url(venue_address(venue))


class VenueViewSet(ModuleViewSet):
    """``/venues`` – venues as master data (KND-009); a venue in use is deactivated, not deleted."""

    module = Module.CUSTOMERS
    queryset = Venue.objects.all()
    serializer_class = VenueSerializer
    search_fields = ["name", "city", "street"]
    filterset_fields = ["is_active", "city"]
    ordering_fields = ["name", "city"]

    def perform_destroy(self, instance: Venue) -> None:
        """Only venues no project names."""
        services.delete_venue(instance)
