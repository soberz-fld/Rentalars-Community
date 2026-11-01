# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the notifications (UIX-005).

* ``GET  /notifications`` – the caller's notifications, newest first (``?unread=1``; UIX-039: ``?category=``,
  ``?companion=1`` – only those for the phone)
* ``POST /notifications/read`` – mark some (``ids``) or all as read
* ``GET/PUT /notifications/preferences`` – which kinds, in the application, by e-mail and (UIX-039) in the
  companion app; UIX-052: every kind a user can switch, named as on the settings page (``label``)
* ``GET/PATCH /settings/notifications`` (VFG-036) – for the whole company: when, how often and how far
  ahead shortages are reported; needs the module "Einstellungen"

UIX-039: every notification and every setting names its category
(``project``, ``personnel``, ``material``, ``system``); ``companion`` says
whether the companion app shows the notification on the phone. The server
only stores that choice – showing it is the app's business.

Every user sees only their own notifications; no module right is needed
(except for the settings of the company).
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from rentalars.accounts.rights import Module
from rentalars.api.pagination import StandardPagination
from rentalars.api.permissions import WritableCaller
from rentalars.api.serializers import CleanModelSerializer
from rentalars.api.views import ModuleAPIView, body_of
from rentalars.core.models import NotificationSettings
from rentalars.notifications import services
from rentalars.notifications.categories import CATEGORIES, category_of, kinds_in
from rentalars.notifications.forms import APPROVAL_FIELDS, INVOICE_FIELDS, SHORTAGE_FIELDS, price_users
from rentalars.notifications.models import ALWAYS_SENT, Kind, Notification
from rentalars.notifications.schedule import next_run


def notification_document(notification: Notification) -> dict[str, Any]:
    """One notification as JSON."""
    return {
        "id": notification.pk,
        "kind": notification.kind,
        # UIX-039: the category of the kind, and whether the companion app shows it on the phone.
        "category": category_of(notification.kind),
        "companion": notification.companion,
        "title": notification.title,
        "body": notification.body,
        "url": notification.url,
        "project": notification.project_id,
        "created_at": notification.created_at,
        "read_at": notification.read_at,
    }


class NotificationListView(APIView):
    """``GET /notifications`` – paginated, with the number of unread ones."""

    permission_classes = [IsAuthenticated]
    schema_tag = "notifications"

    @extend_schema(
        parameters=[
            OpenApiParameter("unread", bool, description="only unread ones"),
            OpenApiParameter("category", str, enum=list(CATEGORIES), description="only this category (UIX-039)"),
            OpenApiParameter("companion", bool, description="only those for the companion app (UIX-039)"),
        ],
        responses={
            200: inline_serializer(
                "Notifications",
                {
                    "count": serializers.IntegerField(),
                    "unread": serializers.IntegerField(help_text="Unread among those category and companion choose."),
                    "unread_total": serializers.IntegerField(help_text="All unread notifications of the caller."),
                },
            )
        },
    )
    def get(self, request: Request) -> Response:
        """The notifications of the caller, newest first, page by page.

        API-016 (mobile app): ``unread`` counts
        the unread ones among those ``category`` and ``companion`` choose –
        with ``?companion=1`` the number for the phone –, ``unread_total``
        all unread ones of the caller (the bell). With ``?unread=1`` the
        pages hold only unread ones, so that older unread ones are reached
        page by page (``next``).
        """
        notifications = Notification.objects.filter(user=request.user).order_by("-created_at", "-id")
        narrowed = False
        category = request.query_params.get("category")
        if category:
            if category not in CATEGORIES:
                raise ValidationError(
                    {"category": _("Unknown category. Choose one of: %(list)s.") % {"list": ", ".join(CATEGORIES)}}
                )
            notifications = notifications.filter(kind__in=kinds_in(category))
            narrowed = True
        if request.query_params.get("companion") in ("1", "true"):
            notifications = notifications.filter(companion=True)
            narrowed = True
        unread = notifications.filter(read_at__isnull=True)
        if request.query_params.get("unread"):
            notifications = unread
        paginator = StandardPagination()
        page = paginator.paginate_queryset(notifications, request, view=self)
        response = paginator.get_paginated_response([notification_document(item) for item in page or []])
        response.data["unread"] = unread.count()
        response.data["unread_total"] = services.unread_count(request.user) if narrowed else response.data["unread"]
        return response


class NotificationReadView(APIView):
    """``POST /notifications/read`` – mark notifications as read."""

    permission_classes = [IsAuthenticated, WritableCaller]
    schema_tag = "notifications"

    @extend_schema(
        request=inline_serializer(
            "NotificationsRead", {"ids": serializers.ListField(child=serializers.IntegerField(), required=False)}
        ),
        responses={200: inline_serializer("NotificationsMarked", {"marked": serializers.IntegerField()})},
    )
    def post(self, request: Request) -> Response:
        """Without ``ids`` all are marked."""
        ids = body_of(request).get("ids")
        if ids is not None and not (isinstance(ids, list) and all(isinstance(item, int) for item in ids)):
            raise ValidationError({"ids": _("Send a list of IDs, or nothing to mark all.")})
        marked = services.mark_read(request.user, ids)
        return Response({"marked": marked, "unread": services.unread_count(request.user)})


class PreferenceSerializer(serializers.Serializer):
    """The choice for one kind of notification.

    UIX-052: every kind a user can switch –
    those of ``ALWAYS_SENT`` are neither listed nor accepted; ``label`` names
    the kind as the settings page does, e.g. the tasks of the AI with
    ``job_finished``.
    """

    kind = serializers.ChoiceField(choices=Kind.choices)
    #: UIX-052: read only – the name of the kind on the settings page.
    label = serializers.CharField(read_only=True)
    #: UIX-039: read only – the category of the kind.
    category = serializers.ChoiceField(choices=CATEGORIES, read_only=True)
    category_label = serializers.CharField(read_only=True)
    in_app = serializers.BooleanField()
    by_email = serializers.BooleanField()
    #: UIX-039: shown on the phone by the companion app; left out, the choice stays as it is.
    companion = serializers.BooleanField(required=False)

    def validate_kind(self, value: str) -> str:
        """UIX-052: a kind that is always sent cannot be switched."""
        if value in ALWAYS_SENT:
            raise serializers.ValidationError(
                _("This notification cannot be switched off: %(reason)s") % {"reason": ALWAYS_SENT[value]}
            )
        return value


class NotificationPreferencesView(APIView):
    """``/notifications/preferences`` – the caller's choice per kind (UIX-005)."""

    permission_classes = [IsAuthenticated, WritableCaller]
    schema_tag = "notifications"

    @extend_schema(responses={200: PreferenceSerializer(many=True)})
    def get(self, request: Request) -> Response:
        """All kinds with the caller's choice; defaults where nothing was chosen."""
        return Response(services.preferences_of(request.user))

    @extend_schema(request=PreferenceSerializer(many=True), responses={200: PreferenceSerializer(many=True)})
    def put(self, request: Request) -> Response:
        """Store the choice for the kinds sent; other kinds stay as they are."""
        serializer = PreferenceSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        for item in serializer.validated_data:
            services.set_preference(
                request.user,
                item["kind"],
                in_app=item["in_app"],
                by_email=item["by_email"],
                companion=item.get("companion"),
            )
        return Response(services.preferences_of(request.user))


# --- VFG-036: Einstellungen → Benachrichtigungen ------------------------------------------------------


class NotificationSettingsSerializer(CleanModelSerializer):
    """When, how often and how far ahead shortages are reported – for the whole company (VFG-036).

    ``shortage_interval``: ``daily``, ``workdays`` (Monday to Friday without
    the holidays of ``/settings/surcharges``), ``weekly`` (on
    ``shortage_weekday``, ISO 1 Monday … 7 Sunday) or ``off``.
    ``shortage_time``: the local time of day of the check.
    ``shortage_lead_weeks``: projects that begin within so many weeks, 1 to
    26. ``shortage_repeat``: false – each shortage once, again only if it
    grows; true – every check reports all open shortages again, the known
    ones in one reminder per project (VFG-036: the default).
    Read only: ``shortage_checked_at`` and ``shortage_reported`` (the last
    check), ``shortage_next_check`` (null when switched off).

    DOK-015, the reminders of invoices not written yet:
    ``invoice_reminders`` on or off, ``invoice_time`` (local time of day),
    ``invoice_first_days`` (days after closing, 0 to 60),
    ``invoice_every_days`` (then again every, 1 to 60), ``invoice_user`` (a
    user who may see prices, reminded besides the project manager, or null),
    ``invoice_service_cases`` (DOK-015: true by default). Read only: ``invoice_checked_at``,
    ``invoice_reminded``, ``invoice_reminders_since`` (projects closed before
    are not reminded of), ``invoice_cases_since`` (service cases
    done before are not reminded of – set whenever ``invoice_service_cases`` is
    switched on, null if never), ``invoice_next_check``.

    The reminders of the times waiting for approval (ZEI-029; ZEI-013):
    ``approval_reminders`` on or off, ``approval_time`` (local time of day),
    ``approval_first_days`` (days after handing in, 0 to 60),
    ``approval_every_days`` (then again every, 1 to 60). Read only:
    ``approval_checked_at``, ``approval_reminded`` (people reminded at the
    last check), ``approval_next_check``.
    """

    shortage_next_check = serializers.DateTimeField(read_only=True, allow_null=True)
    invoice_next_check = serializers.DateTimeField(read_only=True, allow_null=True)
    approval_next_check = serializers.DateTimeField(read_only=True, allow_null=True)

    class Meta:
        model = NotificationSettings
        fields = [
            *SHORTAGE_FIELDS,
            "shortage_checked_at",
            "shortage_reported",
            "shortage_next_check",
            *INVOICE_FIELDS,
            "invoice_checked_at",
            "invoice_reminded",
            "invoice_reminders_since",
            "invoice_cases_since",
            "invoice_next_check",
            *APPROVAL_FIELDS,
            "approval_checked_at",
            "approval_reminded",
            "approval_next_check",
        ]
        read_only_fields = [
            "shortage_checked_at",
            "shortage_reported",
            "invoice_checked_at",
            "invoice_reminded",
            "invoice_reminders_since",
            "invoice_cases_since",
            "approval_checked_at",
            "approval_reminded",
        ]

    def validate_invoice_user(self, value: Any) -> Any:
        """DOK-015: only somebody who may see prices can be reminded of invoices (AUT-019)."""
        if value is not None and not price_users().filter(pk=value.pk).exists():
            raise serializers.ValidationError(_("This user may not see prices or is not active."))
        return value

    def to_representation(self, instance: Any) -> dict[str, Any]:
        """The settings with the moments of the next checks."""
        from rentalars.documents.invoice_reminders import next_run as next_invoice_run
        from rentalars.timetracking.reminders import next_run as next_approval_run

        data = super().to_representation(instance)
        moment = next_run(instance)
        data["shortage_next_check"] = (
            None if moment is None else self.fields["shortage_next_check"].to_representation(moment)
        )
        invoice_moment = next_invoice_run()
        data["invoice_next_check"] = (
            None if invoice_moment is None else self.fields["invoice_next_check"].to_representation(invoice_moment)
        )
        # ZEI-029: when the times waiting for approval are looked at next.
        approval_moment = next_approval_run()
        data["approval_next_check"] = (
            None if approval_moment is None else self.fields["approval_next_check"].to_representation(approval_moment)
        )
        return data


class NotificationSettingsView(ModuleAPIView):
    """``GET/PATCH /settings/notifications`` – when and how far ahead shortages are reported (VFG-036).

    Needs the module "Einstellungen". Changing the time or how often starts the
    schedule anew: the next check is at the next moment of the new schedule.
    """

    module = Module.ADMINISTRATION
    schema_tag = "settings"

    @extend_schema(responses=NotificationSettingsSerializer)
    def get(self, request: Request) -> Response:
        """Return the settings."""
        return Response(NotificationSettingsSerializer(NotificationSettings.load()).data)

    @extend_schema(request=NotificationSettingsSerializer, responses=NotificationSettingsSerializer)
    def patch(self, request: Request) -> Response:
        """Change the values that were sent; everything else stays as it is."""
        current = NotificationSettings.load()
        before = {name: getattr(current, name) for name in services.SCHEDULE_FIELDS}
        serializer = NotificationSettingsSerializer(current, data=body_of(request), partial=True)
        serializer.is_valid(raise_exception=True)
        saved = serializer.save()
        if any(getattr(saved, name) != value for name, value in before.items()):
            services.schedule_changed()
        return Response(NotificationSettingsSerializer(NotificationSettings.objects.get(pk=1)).data)
