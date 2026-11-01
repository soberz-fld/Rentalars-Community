# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the service cases (PRJ-090) and of dividing a project into subprojects (PRJ-050).

``/service-cases``
    The service cases the caller may see: every case not done (PRJ-112) unless
    ``status`` names others; ``q`` searches, ``manager`` filters by the
    person responsible. ``POST`` creates one – with ``inquiry`` from a mail
    without project tag under Projekte → Anfragen, which then goes into the
    case. ``PATCH`` changes what it is about and its status (``case_status``:
    open, in_progress, waiting, closing, backlog, done – PRJ-112: the three
    in between only with the follow-up in the same request, ``waiting`` with
    ``case_waiting_for``, ``closing`` with ``follow_up_at``; else 400).
    ``DELETE`` removes it with its mails and files.

``/service-cases/{id}/participants``, ``/service-cases/{id}/participants/{participant}``
    The people taking part in a case (PRJ-108): ``GET`` lists them,
    ``POST`` adds one (``person``, optional ``job_function`` and ``note``;
    for a person taking part already it changes function and note),
    ``PATCH`` changes function and note, ``DELETE`` takes the person off.
    Every case lists them in ``participants``; ``taking_part=true`` narrows
    the list to the cases the caller's person takes part in.

``POST /service-cases/{id}/convert``
    Turns the case into a project with the rental period given; it keeps
    number, mails, files and history and starts as an inquiry.

``GET /projects/{id}/split``, ``POST /projects/{id}/split``
    What dividing the project would do – the top-level groups, whether each
    can become a subproject and whether it stays a group in it, the crew
    lines –, and doing it: ``groups`` (IDs) become subprojects, ``crew``
    maps crew line IDs to the group they go with.

A service case is a project (``/projects/{id}`` reads it, with ``kind``
"service_case"); the list ``/projects`` leaves service cases out unless
``kind`` is asked for.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.permissions import SAFE_METHODS
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts.models import User
from rentalars.accounts.rights import Level, Module, SpecialRight, request_rights
from rentalars.api.views import ModuleAPIView, ModuleViewSet, body_of
from rentalars.customers.models import Contact, Customer
from rentalars.personnel.models import JobFunction, Person
from rentalars.projects import case_pdf, field_changes, service_cases
from rentalars.projects.access import (
    ProjectAccess,
    access_level,
    note_access,
    note_case_work,
    person_of,
    project_for,
    visible_projects,
    works_on_case,
)
from rentalars.projects.api import ProjectSerializer, change_times_document
from rentalars.projects.case_forms import CUSTOMER_SIDE
from rentalars.projects.case_work import CaseWorkPermission
from rentalars.projects.models import (
    CaseStatus,
    CaseWaitingFor,
    Project,
    ProjectAccessLevel,
    ProjectMembership,
    ServiceCaseParticipant,
)
from rentalars.projects.split import split_into_subprojects, split_plan
from rentalars.projects.tables import may_see_customers


class ParticipantSerializer(serializers.ModelSerializer):
    """A person taking part in a service case (PRJ-108). Not crew planning: no period, no request, no costs."""

    person = serializers.PrimaryKeyRelatedField(queryset=Person.objects.all())
    person_name = serializers.CharField(source="person.name", read_only=True)
    job_function = serializers.PrimaryKeyRelatedField(
        queryset=JobFunction.objects.all(), required=False, allow_null=True
    )
    job_function_name = serializers.CharField(source="job_function.name", read_only=True, default=None)

    class Meta:
        model = ServiceCaseParticipant
        fields = ["id", "person", "person_name", "job_function", "job_function_name", "note", "created_at"]
        read_only_fields = ["created_at"]


class ParticipantChangeSerializer(serializers.Serializer):
    """What can be changed of a person taking part: the job function and the note (PRJ-108)."""

    job_function = serializers.PrimaryKeyRelatedField(
        queryset=JobFunction.objects.all(), required=False, allow_null=True
    )
    note = serializers.CharField(required=False, allow_blank=True, max_length=250)


class CaseStatusChangedAtField(serializers.DateTimeField):
    """PRJ-114: read, the moment the status of a case last changed; sent with ``PATCH``, the moment of its change.

    What is sent is judged by ``ServiceCaseViewSet.update`` before the
    serializer sees the request; here it is only checked and never stored.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(source="*", required=False, **kwargs)

    def to_representation(self, value: Any) -> Any:
        """The whole case comes in (``source="*"``)."""
        return super().to_representation(field_changes.times_of(value)["case_status"])

    def to_internal_value(self, value: Any) -> dict[str, Any]:
        """Check the moment; nothing of it goes into the case."""
        super().to_internal_value(value)
        return {}


class ServiceCaseSerializer(serializers.ModelSerializer):
    """A service case (PRJ-090). ``mail_tag`` goes into the subject of mails that belong to it.

    ``participants``: the people taking part (PRJ-108), changed through ``/service-cases/{id}/participants``.
    """

    #: PRJ-090: required when creating, as for a project; ``null`` is refused when changing. A case of an
    #: earlier version without customer stays readable and can change its status; any other change needs one.
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all(), required=False, allow_null=True)
    contact = serializers.PrimaryKeyRelatedField(queryset=Contact.objects.all(), required=False, allow_null=True)
    case_status = serializers.ChoiceField(choices=CaseStatus.choices, required=False)
    # PRJ-112: "waiting", "closing" and "backlog" only together with the follow-up below; "waiting" with
    # what the case waits for, "closing" with the time. Without a status the follow-up fields set the follow-up.
    case_waiting_for = serializers.ChoiceField(
        choices=CaseWaitingFor.choices,
        required=False,
        allow_blank=True,
        help_text="With case_status “waiting”: reply, action or delivery; empty in every other status.",
    )
    case_status_label = serializers.CharField(read_only=True)
    follow_up_on = serializers.DateField(required=False, allow_null=True)
    follow_up_at = serializers.TimeField(required=False, allow_null=True)
    follow_up_user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True),
        required=False,
        allow_null=True,
        help_text="Whom the follow-up is for; the caller when left out.",
    )
    follow_up_note = serializers.CharField(required=False, allow_blank=True, max_length=250)
    mail_tag = serializers.CharField(read_only=True)
    inquiry = serializers.IntegerField(
        write_only=True,
        required=False,
        help_text="Only when creating: the mail without project tag (Projekte → Anfragen) that goes into the case.",
    )
    participants = ParticipantSerializer(many=True, read_only=True)
    #: PRJ-114: when the status last changed – the same moment as ``field_changed_at.case_status``.
    case_status_changed_at = CaseStatusChangedAtField(
        help_text="When the status last changed. PATCH takes it too (ISO 8601 with time zone): case_status (with "
        "case_waiting_for and the follow-up sent with it) then counts only if this is later than the time stored; "
        "equal: the server wins; the future counts as now. Ignored when creating."
    )
    #: PRJ-113, PRJ-114: when each field last changed – key → moment (``projects.field_changes``).
    field_changed_at = serializers.SerializerMethodField()
    changed_at = serializers.DateTimeField(
        write_only=True,
        required=False,
        help_text=(
            "PATCH (PRJ-113 pattern): when the change was made, ISO 8601 with time zone; each field sent counts "
            "only if this is later than its time in field_changed_at. The answer then has `applied`."
        ),
    )
    #: API-016: the name of the person responsible.
    manager_name = serializers.SerializerMethodField()
    #: PRJ-122: the customer's name – in every role, also for who may not see customers.
    customer_name = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id",
            "number",
            "name",
            "customer",
            "customer_name",  # PRJ-122
            "is_internal",  # MAT-057
            "source_defect",  # MAT-057
            "contact",
            "case_contact",
            "notes",
            "manager",
            "manager_name",  # API-016
            "case_status",
            "case_status_changed_at",  # PRJ-114
            "case_waiting_for",  # PRJ-112
            "case_status_label",  # PRJ-112
            "mail_tag",
            "created_at",
            "follow_up_on",
            "follow_up_at",  # PRJ-109
            "follow_up_user",  # PRJ-112
            "follow_up_note",  # PRJ-112
            "inquiry",
            "participants",  # PRJ-108
            "field_changed_at",  # PRJ-113, PRJ-114
            "changed_at",  # PRJ-113, PRJ-114
        ]
        read_only_fields = ["number", "created_at"]

    @extend_schema_field(serializers.DictField(child=serializers.DateTimeField()))
    def get_field_changed_at(self, case: Project) -> dict[str, Any]:
        """PRJ-113, PRJ-114: key → moment of its last change."""
        return change_times_document(case, field_changes.CASE_KEYS)

    def get_manager_name(self, case: Project) -> str | None:
        """API-016: the name of the person responsible, ``null`` without one."""
        return str(case.manager) if case.manager_id else None

    def get_customer_name(self, case: Project) -> str | None:
        """PRJ-122: the name of the customer, ``null`` without one."""
        return case.customer.name if case.customer_id else None

    def to_representation(self, instance: Project) -> dict[str, Any]:
        """AUT-033, AUT-034: who may not see customers gets no customer, contact or reporter.

        As on the page of the case (``show_customer``): someone working on a case through ``case_work`` reads the
        case, not the customer's data. The fields stay, empty, so that what ``GET`` delivered can be sent back.
        """
        data = super().to_representation(instance)
        if not _sees_customers(self.context):
            data.update(customer=None, contact=None, case_contact="")
        # PRJ-119: in the detail of a case (``GET /service-cases/{id}``), for the companion app.
        from rentalars.projects.relation_api import add_related

        add_related(data, instance, self.context)
        return data


def _sees_customers(context: dict[str, Any]) -> bool:
    """Whether the caller of a serializer may see who the customers are (``tables.may_see_customers``)."""
    view = context.get("view")
    rights = getattr(view, "rights", None)
    if rights is None:
        request = context.get("request")
        rights = request_rights(request) if request is not None else None
    return rights is None or may_see_customers(rights)


#: PRJ-112: the follow-up fields of the API and the names ``service_cases.set_case_status`` takes them by.
FOLLOW_UP_FIELDS = {"follow_up_on": "on", "follow_up_at": "at", "follow_up_user": "user", "follow_up_note": "note"}


def _follow_up_of(values: dict[str, Any]) -> dict[str, Any] | None:
    """Take the follow-up fields out of the values of a request; ``None`` if none was sent."""
    found = {key: values.pop(name) for name, key in FOLLOW_UP_FIELDS.items() if name in values}
    return found or None


def _keep_customer_side(case: Project, values: dict[str, Any]) -> None:
    """AUT-033, AUT-034: who may not see customers does not change the customer's side of a case.

    As in the edit form, which leaves these fields out for them: what the case has already – sent back as ``GET``
    delivered it – is dropped; anything else is refused (403) and nothing of the request is changed.
    """
    # The read leaves these fields empty for them (``ServiceCaseSerializer.to_representation``): empty counts as
    # sent back unchanged as well.
    if any(name in values and values[name] not in (None, "", getattr(case, name)) for name in CUSTOMER_SIDE):
        raise PermissionDenied(
            _("Only who may see customers changes the customer, the contact or who reported a service case.")
        )
    for name in CUSTOMER_SIDE:
        values.pop(name, None)


def _set_follow_up(case: Project, follow_up: dict[str, Any], by: Any) -> None:
    """Set the follow-up alone (PRJ-105); removing it is ``DELETE /projects/{id}/follow-up``."""
    from rentalars.projects.follow_up import set_follow_up

    if follow_up.get("on") is None:
        raise DjangoValidationError({"follow_up_on": _("Choose the day of the follow-up.")})
    set_follow_up(
        case,
        on=follow_up["on"],
        at=follow_up.get("at"),
        note=follow_up.get("note") or "",
        user=follow_up.get("user"),
        by=by,
    )


class ServiceCaseViewSet(ModuleViewSet):
    """``/service-cases`` – service cases (PRJ-090)."""

    module = Module.PROJECTS
    #: PRJ-108: taking somebody off a case is a change of the case, not the deletion of a record.
    action_levels: ClassVar[dict[str, int]] = {"participant": Level.WRITE}
    #: AUT-033 (PRJ-108): the person responsible and the people taking part work on their case – also the companion
    #: app (API-015) –, whatever their roles say; not creating, deleting or converting (``projects.case_work``).
    permission_classes = (CaseWorkPermission,)
    case_work_actions = (
        "list",
        "retrieve",
        "update",
        "partial_update",
        "participants",
        "participant",
        "customer_pdf",
    )
    serializer_class = ServiceCaseSerializer
    queryset = Project.objects.none()

    def get_queryset(self) -> Any:
        """The cases the caller may see; the list by status (default: not done), text and manager."""
        projects = visible_projects(self.rights, self.request.user)
        participants = Prefetch(
            "participants", queryset=ServiceCaseParticipant.objects.select_related("person", "job_function")
        )
        if self.action != "list":
            return (
                service_cases.cases(projects)
                .select_related("customer", "contact", "manager")
                .prefetch_related(participants)
            )
        params = self.request.query_params
        manager = params.get("manager", "")
        found = service_cases.case_list(
            projects,
            statuses=params.getlist("status"),
            text=params.get("q", "").strip(),
            manager=int(manager) if manager.isdigit() else None,
            with_contacts=may_see_customers(request_rights(self.request)),  # PRJ-122: the reporter only here
        )
        if params.get("taking_part", "").lower() in ("1", "true", "yes"):
            # PRJ-108: the cases the caller's person takes part in.
            person = person_of(self.request.user)
            found = found.filter(participants__person=person) if person is not None else found.none()
        return found.prefetch_related(participants)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "status",
                str,
                many=True,
                enum=CaseStatus.values,
                description="default: every status but done (PRJ-112: waiting, closing and backlog included)",
            ),
            OpenApiParameter("q", str, description="number, subject, customer, who reported it, description"),
            OpenApiParameter("manager", int, description="the user responsible"),
            OpenApiParameter("taking_part", bool, description="only the cases the caller's person takes part in"),
        ]
    )
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """The service cases, newest first."""
        return super().list(request, *args, **kwargs)

    def get_object(self) -> Project:
        """One case, with the caller's access: reading needs "read", every change "edit" (AUT-025).

        AUT-033 (PRJ-108): or working on the case, for the actions that are part of it.
        """
        case = super().get_object()
        access = access_level(self.rights, self.request.user, case)
        needed = ProjectAccess.READ if self.request.method in SAFE_METHODS else ProjectAccess.EDIT
        note_case_work(case, self.rights, self.request.user)
        works = self.action in self.case_work_actions and (
            case.may_work_on_case if needed >= ProjectAccess.EDIT else case.works_on_case
        )
        if access < needed and not works:
            raise PermissionDenied
        if needed >= ProjectAccess.EDIT and not works and not self.rights.can_write(Module.PROJECTS):
            raise PermissionDenied  # AUT-033: the module check of a change, for who passed as working on a case
        note_access(case, access)
        return case

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Change a case (``PUT``, ``PATCH``) – with the moments the changes were made, if sent.

        PRJ-114 (mobile app): with ``case_status_changed_at``
        (ISO 8601 with its time zone) the status counts only if that moment is
        later than its last change (``case_status_changed_at``) – together
        with ``case_waiting_for`` and the follow-up sent with it, which belong
        to it. PRJ-113: with ``changed_at`` every field sent counts only if
        that moment is later than the last change of its key in
        ``field_changed_at`` (the status as well, unless
        ``case_status_changed_at`` is sent). At the same moment the server
        wins, a moment in the future counts as now; compared and written under
        the write lock (API-010). The answer is the case as it is now with
        ``applied``: the keys taken over. Without either, nothing changes from
        before.

        ``case_status_changed_at`` is read and written under one name (the
        name the mobile app uses). A client that sends back what ``GET`` delivered
        – the whole case with another status – echoes the stored moment; that
        echo is no moment of a change and counts as not sent, so the status is
        written.
        """
        body = body_of(request)
        moment = field_changes.parse_moment(body.get("changed_at"))
        status_moment = field_changes.parse_moment(body.get("case_status_changed_at"), "case_status_changed_at")
        if moment is None and status_moment is None:
            return super().update(request, *args, **kwargs)
        case = self.get_object()
        with field_changes.locked(case) as (current, now):
            if status_moment is not None and status_moment == field_changes.times_of(current)["case_status"]:
                status_moment = None  # the echo of the stored moment: as if not sent
            sent = body.copy()
            sent.pop("changed_at", None)
            sent.pop("case_status_changed_at", None)
            writable = {name for name, field in self.get_serializer(current).fields.items() if not field.read_only}
            keys = {field_changes.KEY_OF[name] for name in sent if name in writable and name in field_changes.KEY_OF}
            with_status = "case_status" in keys
            moments = {}
            for key in keys:
                # The follow-up sent with a status belongs to it (PRJ-112: some statuses need one).
                own = (
                    (status_moment or moment)
                    if key == "case_status" or (key == "follow_up" and with_status)
                    else moment
                )
                if own is not None:
                    moments[key] = min(own, now)
            applied, older = field_changes.judge(current, moments)
            if with_status and "follow_up" in moments:
                # The same moment as the status, and the same outcome.
                applied = [key for key in applied if key != "follow_up"]
                older = [key for key in older if key != "follow_up"]
                (applied if "case_status" in applied else older).append("follow_up")
            dropped = [name for name in sent if field_changes.KEY_OF.get(name) in older]
            for name in dropped:
                sent.pop(name)
            taken = {key: moments[key] for key in applied}
            if any(name in writable for name in sent):
                # A ``PUT`` from which nothing was dropped is checked as complete, as before.
                partial = bool(kwargs.get("partial")) or bool(dropped)
                serializer = self.get_serializer(current, data=sent, partial=partial)
                serializer.is_valid(raise_exception=True)
                with field_changes.changes_at(current, taken):
                    self.perform_update(serializer)
                field_changes.note(current, taken)
            # Fields sent without a moment of their own are taken as before.
            unjudged = keys - set(moments)
            answer = {**self.get_serializer(current).data, "applied": field_changes.ordered([*taken, *unjudged])}
        return Response(answer)

    def perform_create(self, serializer: Any) -> None:
        """Create the case – from an inquiry, if one is named (needs the right to write e-mail, EML-042).

        A new case is open; a follow-up given is set (PRJ-105, PRJ-112).
        """
        from rentalars.mail.imap import MailboxError
        from rentalars.mail.models import UnknownTagMail

        values = dict(serializer.validated_data)
        inquiry = values.pop("inquiry", None)
        values.pop("case_status", None)
        values.pop("case_waiting_for", None)
        values.pop("changed_at", None)  # PRJ-113: for changes only
        follow_up = _follow_up_of(values)
        with transaction.atomic():
            if inquiry is not None:
                if not self.rights.can_write(Module.EMAIL):
                    raise PermissionDenied
                unknown = UnknownTagMail.objects.filter(pk=inquiry, resolved_at__isnull=True).first()
                if unknown is None:
                    raise serializers.ValidationError({"inquiry": _("There is no such inquiry waiting.")})
                try:
                    case = service_cases.create_from_inquiry(unknown, user=self.request.user, **values)
                except MailboxError as error:
                    raise serializers.ValidationError({"inquiry": str(error)}) from error
            else:
                # PRJ-090: a new case needs a customer, as a project does.
                case = service_cases.create_case(user=self.request.user, customer_required=True, **values)
            if self.rights.is_limited_to_assigned_projects(Module.PROJECTS):
                ProjectMembership.objects.get_or_create(
                    project=case, user=self.request.user, defaults={"level": ProjectAccessLevel.EDIT}
                )
            if follow_up is not None:
                _set_follow_up(case, follow_up, self.request.user)
        serializer.instance = case

    def perform_update(self, serializer: Any) -> None:
        """Change the case; ``case_status`` sets its status.

        PRJ-112: "waiting", "closing" and "backlog" need the follow-up in the
        same request (``follow_up_on``; "closing" also ``follow_up_at``;
        "waiting" also ``case_waiting_for``) – else 400 and nothing changes.
        Follow-up fields without a status set the follow-up alone. Empty
        follow-up fields for a case without a follow-up – the whole case as
        ``GET`` delivered it, sent back – set nothing. Customer,
        contact, "internal" and who reported it only for who may see
        customers (AUT-033, AUT-034; :func:`_keep_customer_side`).
        """
        values = dict(serializer.validated_data)
        values.pop("inquiry", None)
        values.pop("changed_at", None)  # PRJ-113, PRJ-114: judged by ``update`` before
        new_status = values.pop("case_status", None)
        waiting_for = values.pop("case_waiting_for", None)
        follow_up = _follow_up_of(values)
        case = serializer.instance
        if not may_see_customers(self.rights):
            _keep_customer_side(case, values)
        if follow_up is not None and case.follow_up_on is None and not any(follow_up.values()):
            # The echo of "no follow-up" is no follow-up given (else 400).
            follow_up = None
        with transaction.atomic():
            if values:
                service_cases.update_case(case, user=self.request.user, **values)
            if new_status:
                service_cases.set_case_status(
                    case, new_status, waiting_for=waiting_for or "", follow_up=follow_up, by=self.request.user
                )
                return
            if waiting_for is not None:
                raise DjangoValidationError(
                    {"case_waiting_for": _("Send it together with the status “waiting” and the follow-up.")}
                )
            if follow_up is not None:
                _set_follow_up(case, follow_up, self.request.user)

    def perform_destroy(self, instance: Project) -> None:
        """Remove the case with its mails and files (as an inquiry can be deleted, PRJ-008)."""
        from rentalars.projects import services

        services.delete_project(instance)

    # --- PRJ-108: people taking part ------------------------------------------------------------------

    @extend_schema(
        request=ParticipantSerializer,
        responses={200: ParticipantSerializer(many=True), 201: ParticipantSerializer},
    )
    @action(detail=True, methods=["get", "post"])
    def participants(self, request: Request, pk: str | None = None) -> Response:
        """``GET``: the people taking part. ``POST``: add one – or change function and note of one taking part.

        Reading needs read access to the case, adding edit access (``get_object``).
        """
        case = self.get_object()
        if request.method == "GET":
            return Response(ParticipantSerializer(service_cases.participants_of(case), many=True).data)
        serializer = ParticipantSerializer(data=body_of(request))
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        known = case.participants.filter(person=values["person"]).exists()
        participation = service_cases.add_participant(
            case,
            values["person"],
            job_function=values.get("job_function"),
            note=values.get("note", ""),
            user=request.user,
        )
        return Response(
            ParticipantSerializer(participation).data, status=status.HTTP_200_OK if known else status.HTTP_201_CREATED
        )

    @extend_schema(request=ParticipantChangeSerializer, responses={200: ParticipantSerializer, 204: None})
    @action(detail=True, methods=["patch", "delete"], url_path=r"participants/(?P<participant_pk>\d+)")
    def participant(self, request: Request, pk: str | None = None, participant_pk: str | None = None) -> Response:
        """``PATCH``: change job function and note. ``DELETE``: take the person off the case; their times stay."""
        case = self.get_object()
        participation = get_object_or_404(case.participants.select_related("person", "job_function"), pk=participant_pk)
        if request.method == "DELETE":
            service_cases.remove_participant(participation)
            return Response(status=status.HTTP_204_NO_CONTENT)
        serializer = ParticipantChangeSerializer(data=body_of(request), partial=True)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        service_cases.update_participant(
            participation,
            job_function=values.get("job_function", participation.job_function),
            note=values.get("note", participation.note),
        )
        return Response(ParticipantSerializer(participation).data)

    @extend_schema(
        request=None,
        responses={
            201: inline_serializer(
                "ServiceCaseCustomerPdf",
                {
                    "id": serializers.IntegerField(help_text="The ID of the file under the documents of the case."),
                    "title": serializers.CharField(),
                    "file_name": serializers.CharField(),
                    "size": serializers.IntegerField(),
                    "messages": serializers.IntegerField(help_text="Messages without lock that went into the PDF."),
                },
            )
        },
    )
    @action(detail=True, methods=["post"], url_path="customer-pdf")
    def customer_pdf(self, request: Request, pk: str | None = None) -> Response:
        """Make the PDF for the customer – overview and messages without lock – and store it under the documents (PRJ-131).

        Needs edit access to the case and the right to read its correspondence (the special right, or working on the
        case, AUT-033). Every call stores a new file; the earlier ones stay. The file is read at
        ``/projects/{id}/files/{file}`` as every document of a project.
        """
        case = self.get_object()
        if not (self.rights.has(SpecialRight.CORRESPONDENCE_READ) or works_on_case(request.user, case)):
            raise PermissionDenied
        try:
            stored = case_pdf.export_customer_pdf(case, user=request.user, with_contacts=may_see_customers(self.rights))
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.messages) from error
        return Response(
            {
                "id": stored.pk,
                "title": stored.title,
                "file_name": stored.original_name,
                "size": stored.size,
                "messages": case_pdf.open_messages(case).count(),
            },
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        request=inline_serializer(
            "ServiceCaseConversion",
            {
                "start": serializers.DateTimeField(),
                "end": serializers.DateTimeField(),
                "customer": serializers.IntegerField(required=False, allow_null=True),
                "is_internal": serializers.BooleanField(required=False),
                "contact": serializers.IntegerField(required=False, allow_null=True),
                "venue": serializers.CharField(required=False, allow_blank=True),
                "event_start": serializers.DateTimeField(required=False, allow_null=True),
                "event_end": serializers.DateTimeField(required=False, allow_null=True),
            },
        ),
        responses={200: ProjectSerializer},
    )
    @action(detail=True, methods=["post"])
    def convert(self, request: Request, pk: str | None = None) -> Response:
        """Turn the case into a project with these periods; it starts as an inquiry (PRJ-090)."""
        case = self.get_object()
        serializer = ProjectConversionSerializer(data=body_of(request))
        serializer.is_valid(raise_exception=True)
        project = service_cases.convert_to_project(case, **serializer.validated_data)
        note_access(project, access_level(self.rights, request.user, project))
        return Response(ProjectSerializer(project, context=self.get_serializer_context()).data)


class ProjectConversionSerializer(serializers.Serializer):
    """What a service case needs to become a project (PRJ-090)."""

    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all(), required=False, allow_null=True)
    is_internal = serializers.BooleanField(required=False)
    contact = serializers.PrimaryKeyRelatedField(queryset=Contact.objects.all(), required=False, allow_null=True)
    venue = serializers.CharField(required=False, allow_blank=True, max_length=250)
    event_start = serializers.DateTimeField(required=False, allow_null=True)
    event_end = serializers.DateTimeField(required=False, allow_null=True)


# --- PRJ-050: divide a project into subprojects ---------------------------------------------------------


def plan_document(plan: Any) -> dict[str, Any]:
    """What ``GET /projects/{id}/split`` answers."""
    return {
        "possible": plan.possible,
        "refusal": plan.refusal,
        "warnings": plan.warnings,
        "groups": [
            {
                "id": option.group.pk,
                "name": option.group.name,
                "lines": option.lines,
                "subgroups": option.subgroups,
                "possible": option.possible,
                "reasons": option.reasons,
                "stays_a_group": option.keeps_group,
                "stays_a_group_because": option.kept_because,
            }
            for option in plan.groups
        ],
        "crew_lines": [
            {"id": line.pk, "label": str(line), "start": line.start, "end": line.end} for line in plan.crew_lines
        ],
    }


_PLAN_SCHEMA = inline_serializer(
    "SplitPlan",
    {
        "possible": serializers.BooleanField(),
        "refusal": serializers.CharField(),
        "warnings": serializers.ListField(child=serializers.CharField()),
        "groups": serializers.ListField(child=serializers.DictField()),
        "crew_lines": serializers.ListField(child=serializers.DictField()),
    },
)


class SplitView(ModuleAPIView):
    """``/projects/{id}/split`` – divide a project into subprojects, turn groups into subprojects (PRJ-050)."""

    module = Module.PROJECTS

    @extend_schema(responses={200: _PLAN_SCHEMA})
    def get(self, request: Request, project_pk: int) -> Response:
        """What dividing the project would do."""
        project = project_for(request, project_pk, ProjectAccess.READ)
        return Response(plan_document(split_plan(project)))

    @extend_schema(
        request=inline_serializer(
            "SplitRequest",
            {
                "groups": serializers.ListField(child=serializers.IntegerField()),
                "crew": serializers.DictField(child=serializers.IntegerField(), required=False),
            },
        ),
        responses={201: inline_serializer("SplitResult", {"parts": ProjectSerializer(many=True)})},
    )
    def post(self, request: Request, project_pk: int) -> Response:
        """Turn the groups named into subprojects; ``crew`` says which crew line goes with which group."""
        project = project_for(request, project_pk, ProjectAccess.EDIT)
        body = body_of(request)
        groups = body.get("groups") or []
        crew = body.get("crew") or {}
        if not isinstance(groups, list) or not isinstance(crew, dict):
            raise serializers.ValidationError(_("Send “groups” as a list and “crew” as an object."))
        try:
            group_ids = [int(value) for value in groups]
            crew_moves = {int(line): int(group) for line, group in crew.items()}
        except (TypeError, ValueError) as error:
            raise serializers.ValidationError(_("Groups and crew lines are named by their IDs.")) from error
        result = split_into_subprojects(project, group_ids, crew_moves, user=request.user)
        for part in result.parts:
            note_access(part, access_level(self.rights, request.user, part))
        context = {"request": request}
        return Response(
            {
                "parts": ProjectSerializer(result.parts, many=True, context=context).data,
                "warnings": result.warnings,
            },
            status=status.HTTP_201_CREATED,
        )
