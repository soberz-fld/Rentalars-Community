# SPDX-License-Identifier: GPL-3.0-or-later
"""One's own personnel data, absences and deployments over the API – no right on a module needed (API-015).

What "My area" shows a person in the browser (UIX-026) – the tab "Personnel
data" (PER-012, PER-019) and the tab "My deployments" (UIX-043) – for the
companion app and any other client:

=====================================  ==========================================================
``GET /people/me/profile``             phone, e-mail and the two releases, each with the moment of
                                       its last change (``updated_at``); the job functions – with
                                       hourly and day rate only if the person may see them, as in
                                       the browser (PER-010, PER-029) –; the qualifications with
                                       their expiry (PER-014)
``PATCH /people/me/profile``           the four contact fields; with ``changed_at`` the younger
                                       change wins (below)
``GET``/``POST /people/me/absences``   the own absences from 30 days back; enter one (PER-012) –
                                       with ``Idempotency-Key`` as every changing call (API-010)
``DELETE /people/me/absences/{id}``    delete an own absence
``GET /people/me/deployments``         the own crew lines as in "My deployments" (UIX-043): past
                                       ones too, none of cancelled projects; ``ETag`` and
                                       ``If-None-Match`` (304) as every GET
=====================================  ==========================================================

Every endpoint needs a login and an account that is a person (AUT-026; an
account without one gets 404), but no right on a module – everybody keeps
their own data, as in the browser. So the token of the companion app, limited
to ``packing``, ``projects``, ``time_tracking`` and ``email``, reaches all of
it. A read-only token changes nothing (403). The e-mail address is the
account's login address too (AUT-026), where a password reset goes: only a
token without module limits or with the module ``email`` changes it
(review, :func:`may_change_email`); phone and releases any token
that may write.

The younger change wins (``PATCH /people/me/profile``)
-------------------------------------------------------
The server notes when each contact field last changed, on whatever way –
the browser, this API, the user administration, an import
(``Person.save``). A field sent *without* a moment is taken as before. A
field sent *with* one (``changed_at``: one moment for every field sent, or
``{"phone": …, "share_email": …}`` for single fields; ISO 8601 with time
zone) is taken only if that moment is later than the field's stored moment;
otherwise the server's value stays. The rule is that of the offline sync of
packlists (PCK-027) and of the projects (PRJ-113):

* the clock is read once the person is locked;
* a moment in the future counts as that clock ("now");
* at the same moment the server wins;
* comparing and writing are one step: the lock row of API-010 and the row
  of the person are held until the change is stored.

The moment stored for a field taken is the one sent – also when its value
stays the same, so that a later change counts from it (as PRJ-113). The
answer is always the profile as it is now, with ``applied`` – the fields
taken.
"""

from __future__ import annotations

import datetime
from typing import Any

from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.translation import gettext as _
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.api.errors import error_response
from rentalars.api.permissions import AUTHENTICATED_ONLY
from rentalars.api.safeguards import _take_lock as take_write_lock
from rentalars.api.views import ModuleAPIView, body_of
from rentalars.packing.api import ChangeMomentField
from rentalars.personnel import services
from rentalars.personnel.api import AbsenceSerializer
from rentalars.personnel.forms import OwnProfileForm
from rentalars.personnel.models import Absence, Person
from rentalars.projects.access import person_of
from rentalars.projects.models import CrewLine, ProjectStatus

#: The contact fields a person keeps themselves (PER-019), as ``PATCH /people/me/profile`` takes them.
CONTACT_FIELDS = Person.CONTACT_FIELDS

#: PER-012: how far back the own absences are listed, as on the tab "Personnel data".
ABSENCE_DAYS_BACK = 30


def own_person(request: Request) -> Person:
    """The person of the caller's account; 404 for an account without one (AUT-026)."""
    person = person_of(request.user)
    if person is None:
        raise NotFound
    return person


def refuse_read_only(request: Request) -> None:
    """A read-only token changes nothing – not even one's own data."""
    if getattr(getattr(request, "auth", None), "read_only", False):
        raise PermissionDenied


def may_change_email(request: Request) -> bool:
    """Whether the caller may change the e-mail address here – it is the account's login address too (AUT-026).

    Review: the address is where a password reset goes, so a token
    limited to modules may change it only if its modules include ``email``
    (the companion app's token does); otherwise a token for, say, time
    tracking alone could take the account over. A browser session is the
    whole user, and so is a token without module limits. A read-only token
    changes nothing.
    """
    from rentalars.accounts.models import ApiToken
    from rentalars.accounts.rights import Module

    token = getattr(request, "auth", None)
    if not isinstance(token, ApiToken):
        return True
    if token.read_only:
        return False
    modules = [str(module) for module in (token.allowed_modules or [])]
    return not modules or Module.EMAIL.value in modules


def may_see_own_rates(rights: Rights) -> bool:
    """Whether the person sees their own hourly and day rates – the rule of the browser (PER-010, PER-029)."""
    from rentalars.core.models import SystemSettings

    return rights.has(SpecialRight.PERSONNEL_COSTS) or SystemSettings.load().people_see_own_rates


def profile_document(person: Person, rights: Rights, *, email_editable: bool = True) -> dict[str, Any]:
    """The own personnel data as JSON (API-015) – what the tab "Personnel data" shows.

    ``email_editable``: whether this caller may change the e-mail address (:func:`may_change_email`).
    """
    with_rates = may_see_own_rates(rights)
    functions = []
    for current in services.current_rates(person):
        row: dict[str, Any] = {"job_function": current.job_function_id, "name": current.job_function.name}
        if with_rates:
            row["hourly_rate"] = current.hourly_rate
            row["daily_rate"] = current.daily_rate
        functions.append(row)
    return {
        "id": person.pk,
        "name": person.name,
        **{name: getattr(person, name) for name in CONTACT_FIELDS},
        "updated_at": {name: getattr(person, f"{name}_changed_at") for name in CONTACT_FIELDS},
        "email_editable": email_editable,
        "rates_visible": with_rates,
        "job_functions": functions,
        "qualifications": [
            {
                "id": qualification.pk,
                "qualification_type": qualification.qualification_type_id,
                "name": qualification.qualification_type.name,
                "detail": qualification.detail,
                "acquired_on": qualification.acquired_on,
                "valid_until": qualification.valid_until,
                "state": qualification.state,
                "document_name": qualification.document_name if qualification.document else "",
            }
            for qualification in person.qualifications.select_related("qualification_type")
        ],
    }


# --- Description of the answers (OpenAPI) -------------------------------------------------------------


class ContactMomentsSerializer(serializers.Serializer):
    """When each contact field last changed (API-015)."""

    phone = serializers.DateTimeField(allow_null=True)
    email = serializers.DateTimeField(allow_null=True)
    share_phone = serializers.DateTimeField(allow_null=True)
    share_email = serializers.DateTimeField(allow_null=True)


class OwnJobFunctionSerializer(serializers.Serializer):
    """A job function of one's own; the rates only if ``rates_visible`` (PER-010, PER-029)."""

    job_function = serializers.IntegerField()
    name = serializers.CharField()
    hourly_rate = serializers.DecimalField(max_digits=8, decimal_places=2, allow_null=True, required=False)
    daily_rate = serializers.DecimalField(max_digits=8, decimal_places=2, allow_null=True, required=False)


class OwnQualificationSerializer(serializers.Serializer):
    """A qualification of one's own with its expiry (PER-014); ``state``: valid, soon, expired."""

    id = serializers.IntegerField()
    qualification_type = serializers.IntegerField()
    name = serializers.CharField()
    detail = serializers.CharField()
    acquired_on = serializers.DateField(allow_null=True)
    valid_until = serializers.DateField(allow_null=True)
    state = serializers.ChoiceField(choices=["valid", "soon", "expired"])
    document_name = serializers.CharField(help_text="The file of the certificate; empty: none stored.")


class OwnProfileSerializer(serializers.Serializer):
    """The own personnel data (API-015, PER-019); after a ``PATCH`` with ``applied``."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    phone = serializers.CharField()
    email = serializers.CharField()
    share_phone = serializers.BooleanField()
    share_email = serializers.BooleanField()
    updated_at = ContactMomentsSerializer()
    email_editable = serializers.BooleanField(
        help_text="Whether this caller may change the e-mail address: not with a token limited to modules without "
        "`email` (it is the login address too)."
    )
    rates_visible = serializers.BooleanField(help_text="Whether the job functions carry the own rates.")
    job_functions = OwnJobFunctionSerializer(many=True)
    qualifications = OwnQualificationSerializer(many=True)
    applied = serializers.ListField(
        child=serializers.CharField(), required=False, help_text="Only after PATCH: the fields taken."
    )


@extend_schema_field(
    {
        "oneOf": [
            {"type": "string", "format": "date-time"},
            {"type": "object", "additionalProperties": {"type": "string", "format": "date-time"}},
        ],
        "description": "When the change was made, ISO 8601 with time zone: one moment for every field sent, or "
        'one per field, e.g. {"phone": "2026-10-16T09:30:00+02:00"}. Without it the fields are taken as before.',
    }
)
class ChangeTimesField(serializers.Field):
    """``changed_at`` of ``PATCH /people/me/profile``: a moment, or a moment per contact field (API-015)."""

    def to_internal_value(self, data: Any) -> datetime.datetime | dict[str, datetime.datetime]:
        """Read one moment, or a mapping of contact fields to moments."""
        moment = ChangeMomentField()
        if not isinstance(data, dict):
            return moment.run_validation(data)
        errors: dict[str, Any] = {}
        moments: dict[str, datetime.datetime] = {}
        for name, value in data.items():
            if name not in CONTACT_FIELDS:
                errors[name] = [_("This field cannot be changed here.")]
                continue
            try:
                moments[name] = moment.run_validation(value)
            except serializers.ValidationError as error:
                errors[name] = error.detail
        if errors:
            raise serializers.ValidationError(errors)
        return moments

    def to_representation(self, value: Any) -> Any:
        """Not delivered; only read."""
        return value


class OwnProfileChangeSerializer(serializers.Serializer):
    """What ``PATCH /people/me/profile`` takes – each field optional (PER-019, API-015)."""

    phone = serializers.CharField(max_length=60, allow_blank=True, required=False)
    email = serializers.EmailField(max_length=254, allow_blank=True, required=False)
    share_phone = serializers.BooleanField(required=False)
    share_email = serializers.BooleanField(required=False)
    changed_at = ChangeTimesField(required=False, allow_null=True)


class OwnDeploymentProjectSerializer(serializers.Serializer):
    """The project of an own deployment; for a subproject the whole project in ``parent`` (PRJ-046)."""

    id = serializers.IntegerField()
    number = serializers.CharField()
    name = serializers.CharField()
    status = serializers.CharField()
    is_service_case = serializers.BooleanField()
    parent = serializers.IntegerField(allow_null=True)  # type: ignore[assignment]  # a field, not Field.parent
    parent_number = serializers.CharField(allow_null=True)
    parent_name = serializers.CharField(allow_null=True)


class OwnDeploymentSerializer(serializers.Serializer):
    """One crew line of one's own, as a row of "My deployments" (UIX-043)."""

    id = serializers.IntegerField(help_text="The crew line.")
    project = OwnDeploymentProjectSerializer()
    job_function = serializers.IntegerField()
    job_function_name = serializers.CharField()
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    venue_label = serializers.CharField(help_text="The venue of the phase, else of the project; empty if none.")
    meeting_point = serializers.CharField()
    phase = serializers.IntegerField(allow_null=True)
    phase_label = serializers.CharField(allow_null=True)
    planned_hours = serializers.DecimalField(max_digits=6, decimal_places=2)
    note = serializers.CharField()
    request_status = serializers.CharField(
        help_text="Empty: not asked; requested, accepted, declined (PER-016); firm: planned firmly without request "
        "as good as accepted."
    )
    state = serializers.ChoiceField(
        choices=["firm", "option", "inquiry"], help_text="As the colours of the personnel plan (VFG-027)."
    )
    vehicle = serializers.CharField(
        allow_null=True, help_text="LOG-008: the vehicle of the project the person travels with, or null."
    )
    is_driver = serializers.BooleanField(help_text="LOG-008: whether the person drives that vehicle.")


# --- The own profile ------------------------------------------------------------------------------------


class OwnProfileView(ModuleAPIView):
    """``/people/me/profile`` – the own contact data, job functions and qualifications (API-015, PER-019)."""

    module = AUTHENTICATED_ONLY
    schema_tag = "personnel"

    @extend_schema(responses=OwnProfileSerializer)
    def get(self, request: Request) -> Response:
        """The own personnel data, as the tab "Personnel data" of "My area" shows it."""
        return Response(profile_document(own_person(request), self.rights, email_editable=may_change_email(request)))

    @extend_schema(request=OwnProfileChangeSerializer, responses=OwnProfileSerializer)
    def patch(self, request: Request) -> Response:
        """Change phone, e-mail and what colleagues may see (PER-019); with ``changed_at`` the younger change wins.

        Each field sent with a moment is taken only if that moment is later
        than the field's ``updated_at``; at the same moment the server wins,
        a moment in the future counts as now. A field sent without a moment
        is taken as in the browser. Rules of the browser apply to what is
        taken (an e-mail address used by another account is refused, 400).
        A new e-mail address – the account's login address too – needs a
        token without module limits or with the module ``email``; another
        token gets 403 ``token_scope`` and nothing is changed
        (``email_editable`` says it beforehand).
        The answer is the profile as it is now, with ``applied``.
        """
        refuse_read_only(request)
        body = body_of(request)
        unknown = sorted(set(body) - {*CONTACT_FIELDS, "changed_at"})
        if unknown:
            raise DjangoValidationError(
                {
                    name: DjangoValidationError(_("This field cannot be changed here."), code="unknown")
                    for name in unknown
                }
            )
        serializer = OwnProfileChangeSerializer(data=body)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        sent = {name: data[name] for name in CONTACT_FIELDS if name in data}
        times = data.get("changed_at")
        moments = dict(times) if isinstance(times, dict) else dict.fromkeys(sent, times) if times else {}
        own = own_person(request)
        with transaction.atomic():
            # API-010: compare and write in one step – the lock row of the person, then the row itself.
            take_write_lock(f"record:{Person._meta.label_lower}:{own.pk}")
            person = Person.objects.select_for_update().get(pk=own.pk)
            new_email = str(sent.get("email", person.email) or "").strip().lower()
            if new_email != (person.email or "").strip().lower() and not may_change_email(request):
                # Review: the login address only with the module "email" in the token (or none limited).
                message = _(
                    "This token is limited to modules without “E-mail” and cannot change the e-mail address. "
                    "Nothing was changed – change it in the browser or with a token that includes “E-mail”."
                )
                return error_response(
                    "token_scope",
                    message,
                    status.HTTP_403_FORBIDDEN,
                    {"email": [{"code": "token_scope", "message": message}]},
                )
            now = timezone.now()  # the clock, read under the lock
            applied, values, taken_at = [], {}, {}
            for name, value in sent.items():
                moment = moments.get(name)
                if moment is not None:
                    moment = min(moment, now)
                    stored = getattr(person, f"{name}_changed_at")
                    if stored is not None and moment <= stored:
                        continue  # the server's change is not older: it stays
                    taken_at[name] = moment
                values[name] = value
                applied.append(name)
            if values:
                form = OwnProfileForm(
                    data={**{name: getattr(person, name) for name in CONTACT_FIELDS}, **values}, instance=person
                )
                if not form.is_valid():
                    raise DjangoValidationError(form.errors.as_data())
                # A field taken notes the moment sent even if its value stays – a later change counts from it
                # (as PRJ-113); ``Person.save`` notes it for the changed ones.
                for name, moment in taken_at.items():
                    setattr(person, f"{name}_changed_at", moment)
                person.contact_change_times = taken_at
                form.save()
        own.__dict__.update({name: getattr(person, name) for name in CONTACT_FIELDS})
        document = profile_document(person, self.rights, email_editable=may_change_email(request))
        document["applied"] = applied
        return Response(document)


# --- Own absences (PER-012) ----------------------------------------------------------------------------


class OwnAbsencesView(ModuleAPIView):
    """``/people/me/absences`` – the own absences from 30 days back; enter one (PER-012, API-015)."""

    module = AUTHENTICATED_ONLY
    schema_tag = "personnel"

    @extend_schema(responses=AbsenceSerializer(many=True))
    def get(self, request: Request) -> Response:
        """The own absences that ended at most 30 days ago, the earliest first."""
        since = timezone.now() - datetime.timedelta(days=ABSENCE_DAYS_BACK)
        absences = own_person(request).absences.filter(end__gte=since).order_by("start", "id")
        return Response(AbsenceSerializer(absences, many=True).data)

    @extend_schema(
        request=AbsenceSerializer,
        parameters=[OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=False)],
        responses={201: AbsenceSerializer},
    )
    def post(self, request: Request) -> Response:
        """Enter an absence of one's own; own deployments in it come back as ``warnings`` (PER-012, PRJ-022).

        Sent with an ``Idempotency-Key``, a repetition gets the same answer
        and enters nothing more (API-010).
        """
        refuse_read_only(request)
        serializer = AbsenceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        absence = Absence(person=own_person(request), **serializer.validated_data)
        warnings = services.save_absence(absence)
        data = dict(AbsenceSerializer(absence).data)
        data["warnings"] = warnings
        return Response(data, status=status.HTTP_201_CREATED)


class OwnAbsenceDetailView(ModuleAPIView):
    """``/people/me/absences/{id}`` – delete an own absence (PER-012, API-015)."""

    module = AUTHENTICATED_ONLY
    schema_tag = "personnel"

    @extend_schema(responses={204: None})
    def delete(self, request: Request, absence_pk: int) -> Response:
        """Delete an absence of one's own; another person's is not found (404)."""
        refuse_read_only(request)
        get_object_or_404(own_person(request).absences, pk=absence_pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- Own deployments (UIX-043) -------------------------------------------------------------------------


def venue_of(line: CrewLine) -> str:
    """Where the deployment takes place: the phase's venue, the project's, the free texts – as "My deployments"."""
    project, phase = line.project, line.phase if line.phase_id else None
    if phase is not None and phase.venue_site is not None:
        return phase.venue_site.name
    if project.venue_site is not None:
        return project.venue_site.name
    return (phase.location if phase is not None else "") or project.venue or ""


def deployment_document(line: CrewLine) -> dict[str, Any]:
    """One own crew line as JSON (API-015, UIX-043)."""
    from rentalars.projects.my_deployments import firmness

    project, parent = line.project, line.project.parent
    return {
        "id": line.pk,
        "project": {
            "id": project.pk,
            "number": project.number,
            "name": project.name,
            "status": project.status,
            "is_service_case": project.is_service_case,
            "parent": project.parent_id,
            "parent_number": parent.number if parent is not None else None,
            "parent_name": parent.name if parent is not None else None,
        },
        "job_function": line.job_function_id,
        "job_function_name": line.job_function.name,
        "start": line.start,
        "end": line.end,
        "venue_label": venue_of(line),
        "meeting_point": line.meeting_point,
        "phase": line.phase_id,
        "phase_label": line.phase.label if line.phase is not None else None,
        "planned_hours": line.planned_hours,
        "note": line.note,
        "request_status": line.request_status,
        "state": firmness(line),
        # LOG-008: the vehicle the person travels with, as "My deployments" shows it – without its supplier.
        "vehicle": line.vehicle_line.crew_label if line.vehicle_line_id else None,
        "is_driver": line.is_driver,
    }


def _bound(request: Request, name: str, *, end: bool) -> datetime.datetime | None:
    """``from`` or ``to`` as a moment; a day alone is its start – for ``to`` the end of that day."""
    text = (request.query_params.get(name) or "").strip()
    if not text:
        return None
    try:
        # The day first: ``parse_datetime`` would read "2027-03-10" as its midnight.
        day = parse_date(text)
        value = parse_datetime(text) if day is None else None
    except ValueError:  # well formed, but no real day: month 13
        value = day = None
    if day is not None:
        value = datetime.datetime.combine(day + datetime.timedelta(days=1) if end else day, datetime.time.min)
    if value is None:
        raise DjangoValidationError({name: _("Give a date or a date with time, e.g. 2027-03-10T08:00.")})
    return timezone.make_aware(value) if timezone.is_naive(value) else value


class OwnDeploymentsView(ModuleAPIView):
    """``GET /people/me/deployments?from=&to=`` – the own crew lines, as "My deployments" (UIX-043, API-015)."""

    module = AUTHENTICATED_ONLY
    schema_tag = "personnel"

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "from", str, description="Deployments that end after this moment; a day alone: from its start."
            ),
            OpenApiParameter(
                "to", str, description="Deployments that begin before this moment; a day alone: up to its end."
            ),
        ],
        responses=OwnDeploymentSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        """Every crew line of one's own person in the period, the earliest first; without a period all of them.

        Past deployments too; none of cancelled projects. No right on a
        module is needed – everybody sees their own deployments, also in
        projects they may not open otherwise (AUT-025). With
        ``If-None-Match`` and the ``ETag`` of an earlier answer: 304 if
        nothing changed.
        """
        person = own_person(request)
        since, until = _bound(request, "from", end=False), _bound(request, "to", end=True)
        lines = (
            CrewLine.objects.filter(person=person)
            .exclude(project__status=ProjectStatus.CANCELLED)
            .select_related(
                "project__parent",
                "project__venue_site",
                "job_function",
                "phase__venue_site",
                "vehicle_line__item__vehicle",
            )
            .order_by("start", "id")
        )
        if since is not None:
            lines = lines.filter(end__gt=since)
        if until is not None:
            lines = lines.filter(start__lt=until)
        return Response([deployment_document(line) for line in lines])
