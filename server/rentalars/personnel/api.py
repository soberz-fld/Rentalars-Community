# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the personnel module: people, job functions, rates, absences, availability (chapter 8).

Hourly and day rates and guide values for costs are delivered and accepted
only with the right "see hourly rates and personnel costs" (AUT-019, PER-010,
PER-029).
"""

from __future__ import annotations

import datetime
from typing import Any, ClassVar

from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Level, Module, SpecialRight
from rentalars.api.errors import RecordAnonymised
from rentalars.api.serializers import CleanModelSerializer, RestrictedFieldsMixin
from rentalars.api.views import ModuleAPIView, ModuleViewSet
from rentalars.personnel import services
from rentalars.personnel.availability import people_availability
from rentalars.personnel.calendar_api import PersonCalendarActions
from rentalars.personnel.models import Absence, JobFunction, Person, Qualification, QualificationType
from rentalars.personnel.privacy import anonymise_person, export_person
from rentalars.projects.access import visible_projects


class JobFunctionSerializer(RestrictedFieldsMixin, CleanModelSerializer):
    """A job function with its service product (PER-004, PER-008).

    ``max_discount_percent`` is the highest discount any line of the job
    function gets (PER-026): ``null`` no limit, ``0`` never discounted. It
    needs the price right.

    PRD-044: every job function has exactly one service product, and
    every service product one job function. ``service_product`` is therefore
    given, not chosen: a new function gets a service product of its name –
    with ``price`` as its price per hour, if sent (price right) –, renaming a
    function renames a product of the same name, and price, tax rate and hour
    tiers are changed on the product (``/products/{id}``). Sending another
    ``service_product`` is refused. PER-035: ``guide_cost_rate_above_limit``,
    the internal cost of an hour beyond the limit of hours per day.
    """

    service_product = serializers.PrimaryKeyRelatedField(
        read_only=True, help_text="The service product of the function – created with it (PRD-044)."
    )
    service_product_article_number = serializers.CharField(
        source="service_product.article_number", read_only=True, default=None
    )
    price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        required=False,
        allow_null=True,
        write_only=True,
        help_text="Only when creating: the price per hour of the new service product (needs the price right).",
    )

    restricted_fields = {
        "guide_cost_rate": SpecialRight.PERSONNEL_COSTS,
        "guide_daily_cost_rate": SpecialRight.PERSONNEL_COSTS,
        "guide_cost_rate_above_limit": SpecialRight.PERSONNEL_COSTS,
        "max_discount_percent": SpecialRight.PRICES,
        "price": SpecialRight.PRICES,
    }

    class Meta:
        model = JobFunction
        fields = [
            "id",
            "name",
            "service_product",
            "service_product_article_number",
            "price",
            "guide_cost_rate",
            "guide_cost_rate_above_limit",
            "guide_daily_cost_rate",
            "max_discount_percent",
            "is_active",
        ]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """PRD-044: the service product is not chosen; ``price`` only for a new function."""
        sent = self.initial_data.get("service_product") if isinstance(self.initial_data, dict) else None
        current = self.instance.service_product_id if self.instance is not None else None
        if sent not in (None, "") and str(sent) != str(current):
            raise serializers.ValidationError(
                {
                    "service_product": _(
                        "Every job function has its own service product, created with it. Change price, tax rate "
                        "and hour tiers on that product."
                    )
                }
            )
        if self.instance is not None and attrs.get("price") is not None:
            raise serializers.ValidationError(
                {"price": _("Change the price on the service product of the job function.")}
            )
        return attrs

    def create(self, validated_data: dict[str, Any]) -> JobFunction:
        """A new function with its service product (PRD-044)."""
        price = validated_data.pop("price", None)
        return services.save_job_function(JobFunction(**validated_data), price=price)

    def update(self, instance: JobFunction, validated_data: dict[str, Any]) -> JobFunction:
        """Change the function; a product of the same name is renamed along (PRD-044)."""
        validated_data.pop("price", None)
        for name, value in validated_data.items():
            setattr(instance, name, value)
        return services.save_job_function(instance)


class JobFunctionViewSet(ModuleViewSet):
    """``/job-functions`` – what people are planned as (PER-004).

    Every logged-in user may read the list: the forms for crew lines and
    time entries need it. Changing needs write access to personnel.
    """

    module = Module.PERSONNEL
    read_for_all = True
    queryset = JobFunction.objects.select_related("service_product").order_by("name")
    serializer_class = JobFunctionSerializer
    search_fields = ["name"]
    filterset_fields = ["is_active"]
    pagination_class = None

    def perform_destroy(self, instance: JobFunction) -> None:
        """Delete only job functions that nobody has and that were never planned – with their service product."""
        services.delete_job_function(instance)


class PersonSerializer(CleanModelSerializer):
    """A person (PER-002, PER-003) with the account that comes with it (AUT-012, AUT-026)."""

    name = serializers.CharField(read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    job_functions = serializers.SerializerMethodField()
    #: AUT-034: what the person's account may see of finances, personnel data and customer data.
    data_access = serializers.SerializerMethodField(
        help_text="As in /users; each no_access for a person without an account or with a deactivated one."
    )

    class Meta:
        model = Person
        fields = [
            "id",
            "first_name",
            "last_name",
            "name",
            "kind",
            "position",
            "email",
            "phone",
            "commute_km",  # ZEI-027: distance home – company in km, deducted from trips
            "note",
            "company",
            "street",
            "postal_code",
            "city",
            "tax_number",
            "vat_id",
            "user",
            "username",
            "share_phone",
            "share_email",
            "is_active",
            "anonymised_at",
            "job_functions",
            "data_access",  # AUT-034
        ]
        read_only_fields = ["anonymised_at", "user"]

    def get_job_functions(self, person: Person) -> list[int]:
        """The IDs of the job functions the person is assigned to (PER-005)."""
        return sorted({rate.job_function_id for rate in person.rates.all()})

    @extend_schema_field(serializers.DictField(child=serializers.CharField()))
    def get_data_access(self, person: Person) -> dict[str, str]:
        """AUT-034: finances, personnel data, customer data of the person's account (``accounts.data_access``)."""
        from rentalars.accounts.data_access import of_user

        return of_user(person.user if person.user_id else None).as_document()

    def update(self, instance: Person, validated_data: dict[str, Any]) -> Person:
        """L3: ``is_active`` changes the account like the page does – not one's own, not the last administrator."""
        active = validated_data.pop("is_active", None)
        if active is False and instance.user_id and instance.is_active:
            request = self.context.get("request")
            from rentalars.accounts.services import check_may_deactivate

            check_may_deactivate(instance.user, acting_user=getattr(request, "user", None))
        if active is not None:
            validated_data["is_active"] = active
        return super().update(instance, validated_data)


class RateSerializer(serializers.Serializer):
    """Input for assigning a job function, with rates if given (PER-005, PER-007, PER-029).

    Every rate and the day are optional: without a rate the guide value of
    the job function counts, without ``valid_from`` the rates count from
    always.
    """

    job_function = serializers.PrimaryKeyRelatedField(queryset=JobFunction.objects.all())
    hourly_rate = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=0, required=False, allow_null=True)
    daily_rate = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=0, required=False, allow_null=True)
    hourly_rate_above_limit = serializers.DecimalField(
        max_digits=8,
        decimal_places=2,
        min_value=0,
        required=False,
        allow_null=True,
        help_text="PER-035: the cost of an hour beyond the limit of hours per day; empty: the hourly rate.",
    )
    valid_from = serializers.DateField(
        required=False, allow_null=True, help_text="The day the rates apply from; empty: always."
    )


class RateRowSerializer(serializers.Serializer):
    """One row of the rates of a person in a job function (PER-007, PER-029); ``null`` rates: the guide value."""

    hourly_rate = serializers.DecimalField(max_digits=8, decimal_places=2, allow_null=True)
    daily_rate = serializers.DecimalField(max_digits=8, decimal_places=2, allow_null=True)
    hourly_rate_above_limit = serializers.DecimalField(max_digits=8, decimal_places=2, allow_null=True)
    valid_from = serializers.DateField(allow_null=True, help_text="`null`: from always.")


class PersonJobFunctionSerializer(serializers.Serializer):
    """A job function of a person; the rates only with the right for personnel costs (PER-005, PER-010, PER-029).

    For the description only: without that right the rate fields are left
    out, not ``null``.
    """

    job_function = serializers.IntegerField()
    name = serializers.CharField()
    hourly_rate = serializers.DecimalField(max_digits=8, decimal_places=2, allow_null=True, required=False)
    daily_rate = serializers.DecimalField(max_digits=8, decimal_places=2, allow_null=True, required=False)
    hourly_rate_above_limit = serializers.DecimalField(max_digits=8, decimal_places=2, allow_null=True, required=False)
    valid_from = serializers.DateField(allow_null=True, required=False)
    history = RateRowSerializer(many=True, required=False)


class AbsenceSerializer(CleanModelSerializer):
    """An absence of a person (PER-011)."""

    class Meta:
        model = Absence
        fields = ["id", "person", "kind", "start", "end", "note"]
        read_only_fields = ["person"]


class PersonViewSet(PersonCalendarActions, ModuleViewSet):
    """``/people`` – the people who work on projects (PER-001).

    People with crew lines or time entries cannot be deleted; they are
    deactivated (``PATCH`` with ``is_active``) or anonymised.

    The availability calendar and the calendar links of a person
    (PER-021 to PER-023) are actions of their own, see
    :mod:`rentalars.personnel.calendar_api`.
    """

    module = Module.PERSONNEL
    # AUT-034: the roles of the accounts for ``data_access`` in one query.
    queryset = (
        Person.objects.prefetch_related("rates", "user__roles")
        .select_related("user")
        .order_by("last_name", "first_name")
    )
    serializer_class = PersonSerializer
    search_fields = ["first_name", "last_name", "email", "company"]
    filterset_fields = ["kind", "is_active"]
    ordering_fields = ["last_name", "first_name", "kind"]
    action_levels = {
        "anonymise": Level.DELETE,
        "export": Level.DELETE,
        "remove_job_function": Level.WRITE,
        "remove_absence": Level.WRITE,
    }

    def get_queryset(self) -> Any:
        """Filter by job function with ``?job_function=<id>``."""
        people = super().get_queryset()
        function_id = self.request.query_params.get("job_function", "")
        if function_id.isdigit():
            people = people.filter(rates__job_function_id=int(function_id)).distinct()
        return people

    def perform_update(self, serializer: Any) -> None:
        """L8: an anonymised person stays anonymised – the pages refuse it too."""
        if serializer.instance.anonymised_at:
            raise RecordAnonymised
        super().perform_update(serializer)

    def perform_destroy(self, instance: Person) -> None:
        """Delete only people who were never planned and never recorded a time."""
        services.delete_person(instance)

    def _require_rates(self) -> None:
        if not self.rights.has(SpecialRight.PERSONNEL_COSTS):
            raise PermissionDenied

    @extend_schema(methods=["get"], responses=PersonJobFunctionSerializer(many=True))
    @extend_schema(methods=["post"], request=RateSerializer, responses=PersonJobFunctionSerializer(many=True))
    @action(detail=True, methods=["get", "post"], url_path="job-functions")
    def job_functions(self, request: Request, pk: str | None = None) -> Response:
        """The job functions of a person with their hourly and day rates (PER-005, PER-007, PER-029).

        ``GET`` lists the functions; the rates that apply today and their
        history are part of the answer only with the right for personnel
        costs. ``null`` means no own rate: the guide value of the job
        function counts; ``valid_from: null`` means from always. ``POST``
        assigns a function – rates and day are optional – or enters new rates
        from a day on. Rates and day need that right too; without it a
        function is only assigned, without own rates, and rates the person
        has already stay. Existing crew lines and time entries keep their
        rate.
        """
        person = self.get_object()
        if request.method == "POST":
            serializer = RateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
            given = [data.get(name) for name in ("hourly_rate", "daily_rate", "hourly_rate_above_limit", "valid_from")]
            if not self.rights.has(SpecialRight.PERSONNEL_COSTS):
                if any(value is not None for value in given):
                    raise PermissionDenied
                services.assign_job_function(person, data["job_function"])
            else:
                services.set_rate(
                    person,
                    data["job_function"],
                    data.get("hourly_rate"),
                    data.get("valid_from"),
                    daily_rate=data.get("daily_rate"),
                    hourly_rate_above_limit=data.get("hourly_rate_above_limit"),
                )
        with_rates = self.rights.has(SpecialRight.PERSONNEL_COSTS)
        history: dict[int, list[dict[str, Any]]] = {}
        if with_rates:
            for rate in services.rate_history(person):
                history.setdefault(rate.job_function_id, []).append(
                    {
                        "hourly_rate": rate.hourly_rate,
                        "daily_rate": rate.daily_rate,
                        "hourly_rate_above_limit": rate.hourly_rate_above_limit,
                        "valid_from": rate.valid_from,
                    }
                )
        rows = []
        for current in services.current_rates(person):
            row: dict[str, Any] = {"job_function": current.job_function_id, "name": current.job_function.name}
            if with_rates:
                row["hourly_rate"] = current.hourly_rate
                row["daily_rate"] = current.daily_rate
                row["hourly_rate_above_limit"] = current.hourly_rate_above_limit
                row["valid_from"] = current.valid_from
                row["history"] = history.get(current.job_function_id, [])
            rows.append(row)
        return Response(rows)

    @extend_schema(responses={204: None})
    @action(detail=True, methods=["delete"], url_path=r"job-functions/(?P<function_pk>\d+)")
    def remove_job_function(self, request: Request, pk: str | None = None, function_pk: str | None = None) -> Response:
        """Take a job function away from a person, with all its rates (PER-005).

        Without the right for personnel costs only a function without own rates.
        """
        person, job_function = self.get_object(), get_object_or_404(JobFunction, pk=function_pk)
        if not self.rights.has(SpecialRight.PERSONNEL_COSTS) and services.has_own_rates(person, job_function):
            raise PermissionDenied
        services.remove_job_function(person, job_function)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(methods=["get"], responses=AbsenceSerializer(many=True))
    @extend_schema(methods=["post"], request=AbsenceSerializer, responses={201: AbsenceSerializer})
    @action(detail=True, methods=["get", "post"])
    def absences(self, request: Request, pk: str | None = None) -> Response:
        """The absences of a person (PER-011). ``POST`` enters one; clashes with crew lines come back as warnings."""
        person = self.get_object()
        if request.method == "POST":
            serializer = AbsenceSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            absence = Absence(person=person, **serializer.validated_data)
            warnings = services.save_absence(absence)
            data = dict(AbsenceSerializer(absence).data)
            data["warnings"] = warnings
            return Response(data, status=status.HTTP_201_CREATED)
        return Response(AbsenceSerializer(person.absences.all(), many=True).data)

    @extend_schema(responses={204: None})
    @action(detail=True, methods=["delete"], url_path=r"absences/(?P<absence_pk>\d+)")
    def remove_absence(self, request: Request, pk: str | None = None, absence_pk: str | None = None) -> Response:
        """Delete an absence."""
        get_object_or_404(self.get_object().absences, pk=absence_pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(responses={200: inline_serializer("PersonExport", {"exported_at": serializers.DateTimeField()})})
    @action(detail=True)
    def export(self, request: Request, pk: str | None = None) -> Response:
        """Everything stored about a person, for a request for information (NFA-009).

        Needs delete access to personnel and the right for personnel costs:
        the document contains the rates and all times of the person.
        """
        self._require_rates()
        return Response(export_person(self.get_object()))

    @extend_schema(request=None, responses=PersonSerializer)
    @action(detail=True, methods=["post"])
    def anonymise(self, request: Request, pk: str | None = None) -> Response:
        """Erase what identifies a person; deployments and times stay (NFA-009)."""
        person = self.get_object()
        anonymise_person(person)
        return Response(self.get_serializer(person).data)


# --- Qualifications (PER-014) ------------------------------------------------------------------


class QualificationTypeSerializer(CleanModelSerializer):
    """A kind of qualification with its usual validity (PER-014)."""

    class Meta:
        model = QualificationType
        # LOG-012: ``licence_classes`` – the driving licence classes a licence covers.
        fields = ["id", "name", "description", "validity_months", "licence_classes", "is_active"]


class QualificationTypeViewSet(ModuleViewSet):
    """``/qualification-types`` – driving licences, platforms, first aid … (PER-014).

    A type that people have is deactivated, not deleted.
    """

    module = Module.PERSONNEL
    queryset = QualificationType.objects.order_by("name")
    serializer_class = QualificationTypeSerializer
    search_fields = ["name"]
    filterset_fields = ["is_active"]
    pagination_class = None

    def perform_destroy(self, instance: QualificationType) -> None:
        """Refuse to delete a type that people have."""
        if instance.qualifications.exists():
            raise ValidationError(_("People have this qualification. Deactivate it instead."))
        instance.delete()


class QualificationSerializer(CleanModelSerializer):
    """A qualification of a person; the certificate is uploaded as ``document`` (multipart)."""

    document = serializers.FileField(write_only=True, required=False)
    certificate_url = serializers.SerializerMethodField()
    state = serializers.CharField(read_only=True)

    class Meta:
        model = Qualification
        fields = [
            "id",
            "person",
            "qualification_type",
            "detail",
            "acquired_on",
            "valid_until",
            "state",
            "document",
            "document_name",
            "certificate_url",
        ]
        read_only_fields = ["person", "document_name"]

    def get_certificate_url(self, qualification: Qualification) -> str:
        """Where the certificate can be fetched, if one is stored."""
        if not qualification.document:
            return ""
        return f"/api/v1/people/{qualification.person_id}/qualifications/{qualification.pk}/certificate"

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """The checks run in the service; here only the fields."""
        return attrs


def _person(pk: int) -> Person:
    return get_object_or_404(Person, pk=pk)


class PersonQualificationsView(ModuleAPIView):
    """``/people/{id}/qualifications`` (PER-014)."""

    module = Module.PERSONNEL
    parser_classes: ClassVar[list[Any]] = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(responses=QualificationSerializer(many=True))
    def get(self, request: Request, pk: int) -> Response:
        """The qualifications of a person with their state (valid, soon, expired)."""
        rows = _person(pk).qualifications.select_related("qualification_type")
        return Response(QualificationSerializer(rows, many=True).data)

    @extend_schema(request=QualificationSerializer, responses={201: QualificationSerializer})
    def post(self, request: Request, pk: int) -> Response:
        """Record a qualification; without ``valid_until`` the type's validity is counted from ``acquired_on``."""
        serializer = QualificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        document = data.pop("document", None)
        qualification = services.save_qualification(Qualification(person=_person(pk), **data), document=document)
        return Response(QualificationSerializer(qualification).data, status=status.HTTP_201_CREATED)


class PersonQualificationDetailView(ModuleAPIView):
    """``/people/{id}/qualifications/{qualification}`` (PER-014)."""

    module = Module.PERSONNEL
    parser_classes: ClassVar[list[Any]] = [MultiPartParser, FormParser, JSONParser]

    def _get(self, pk: int, qualification_pk: int) -> Qualification:
        return get_object_or_404(
            Qualification.objects.select_related("qualification_type"), pk=qualification_pk, person_id=pk
        )

    @extend_schema(responses=QualificationSerializer)
    def get(self, request: Request, pk: int, qualification_pk: int) -> Response:
        """One qualification."""
        return Response(QualificationSerializer(self._get(pk, qualification_pk)).data)

    @extend_schema(request=QualificationSerializer, responses=QualificationSerializer)
    def patch(self, request: Request, pk: int, qualification_pk: int) -> Response:
        """Change dates or details, or replace the certificate (a renewal)."""
        qualification = self._get(pk, qualification_pk)
        serializer = QualificationSerializer(qualification, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        document = data.pop("document", None)
        for name, value in data.items():
            setattr(qualification, name, value)
        services.save_qualification(qualification, document=document)
        return Response(QualificationSerializer(qualification).data)

    @extend_schema(responses={204: None})
    def delete(self, request: Request, pk: int, qualification_pk: int) -> Response:
        """Remove the qualification with its certificate."""
        services.delete_qualification(self._get(pk, qualification_pk))
        return Response(status=status.HTTP_204_NO_CONTENT)


class PersonQualificationCertificateView(ModuleAPIView):
    """``/people/{id}/qualifications/{qualification}/certificate`` – the stored scan."""

    module = Module.PERSONNEL

    @extend_schema(responses={(200, "application/octet-stream"): bytes})
    def get(self, request: Request, pk: int, qualification_pk: int) -> Any:
        """The file."""
        from django.http import Http404

        from rentalars.core.uploads import document_response

        qualification = get_object_or_404(Qualification, pk=qualification_pk, person_id=pk)
        if not qualification.document:
            raise Http404
        return document_response(qualification.document.name, qualification.document_name or "nachweis.pdf")


class PersonTimelineView(ModuleAPIView):
    """``/people/{id}/timeline`` – deployments, absences, expiring qualifications (PER-020)."""

    module = Module.PERSONNEL

    @extend_schema(
        parameters=[OpenApiParameter("from", datetime.date), OpenApiParameter("weeks", int)],
        responses=inline_serializer("PersonTimeline", {"days": serializers.ListField(child=serializers.DateField())}),
    )
    def get(self, request: Request, pk: int) -> Response:
        """The rows of the timeline with their bars, as on the person's page."""
        from rentalars.accounts.rights import request_rights
        from rentalars.schedule.services import span_from_request
        from rentalars.schedule.timelines import person_timeline, timeline_document

        days, _navigation = span_from_request(request, default_weeks=4)
        visible = set(visible_projects(request_rights(request), request.user).values_list("pk", flat=True))
        return Response(timeline_document(person_timeline(_person(pk), days, visible)))


class PeopleAvailabilityView(ModuleAPIView):
    """``GET /people/availability?from=&to=&job_function=`` – who is free, planned or absent (VFG-009, VFG-010)."""

    module = Module.PERSONNEL

    @extend_schema(
        parameters=[
            OpenApiParameter("from", str, required=True, description="Begin of the period, ISO 8601"),
            OpenApiParameter("to", str, required=True, description="End of the period, ISO 8601"),
            OpenApiParameter(
                "job_function",
                int,
                description="Only people with this job function (VFG-010); without it every active person, also "
                "one without job function",
            ),
        ],
        responses={200: inline_serializer("PersonAvailability", {"status": serializers.CharField()}, many=True)},
    )
    def get(self, request: Request) -> Response:
        """Return every active person with the status in the period; the free ones first.

        Deployments in projects the caller may not see are counted, but
        their project is not named (AUT-016). What the person said about the
        period comes along as ``availability_marks`` (PER-021, PER-022): a
        red mark makes the status ``absent``, a yellow one is a hint. They
        are the availability that counts (PER-027): one at any moment – where
        an own entry and a busy time of the linked calendar meet, the newer
        statement –, and busy times that overlap or touch are one mark.
        """
        start = _moment(request.query_params.get("from", ""), "from")
        end = _moment(request.query_params.get("to", ""), "to")
        if end <= start:
            raise ValidationError({"to": _("The end must be after the start.")})
        function_id = request.query_params.get("job_function", "")
        job_function = get_object_or_404(JobFunction, pk=int(function_id)) if function_id.isdigit() else None
        visible = set(visible_projects(self.rights, request.user).values_list("pk", flat=True))
        return Response(
            [
                {
                    "person": row.person.pk,
                    "name": row.person.name,
                    "kind": row.person.kind,
                    "status": row.status,
                    "absences": [
                        {"kind": absence.kind, "from": absence.start, "to": absence.end} for absence in row.absences
                    ],
                    # PER-021, PER-022: red counts like an absence, yellow is a hint, green puts first.
                    "availability_marks": [
                        {
                            "state": mark.state,
                            "source": mark.source,
                            "from": mark.start,
                            "to": mark.end,
                            "note": mark.note,
                        }
                        for mark in row.marks
                    ],
                    "deployments": [
                        {
                            "project": line.project_id if line.project_id in visible else None,
                            "project_number": line.project.number if line.project_id in visible else None,
                            "job_function": line.job_function_id,
                            "from": line.start,
                            "to": line.end,
                        }
                        for line in row.deployments
                    ],
                }
                for row in people_availability(start, end, job_function=job_function)
            ]
        )


def _moment(text: str, name: str) -> datetime.datetime:
    """Read a point in time from a query parameter; a date alone means the start of that day."""
    value = parse_datetime(text) if text else None
    if value is None and text:
        try:
            value = datetime.datetime.combine(datetime.date.fromisoformat(text), datetime.time())
        except ValueError:
            value = None
    if value is None:
        raise ValidationError({name: _("Give a date or a date with time, e.g. 2027-03-10T08:00.")})
    return timezone.make_aware(value) if timezone.is_naive(value) else value
