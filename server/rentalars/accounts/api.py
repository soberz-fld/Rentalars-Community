# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the accounts module: login, own profile, users, roles, tokens (chapter 8)."""

from __future__ import annotations

from typing import Any

from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import ValidationError
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema, extend_schema_field, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

import rentalars
from rentalars.accounts import services, twofactor
from rentalars.accounts.models import ApiToken, Role, SecurityEventKind, User
from rentalars.accounts.rights import FUTURE_MODULES, Level, Module, ProjectScope, SpecialRight, request_rights
from rentalars.api.errors import error_response
from rentalars.api.permissions import AUTHENTICATED_ONLY, ModulePermission, WritableCaller
from rentalars.api.serializers import CleanModelSerializer
from rentalars.api.views import ModuleViewSet, NoDeleteViewSet, RightsViewMixin, body_of
from rentalars.core.i18n import LANGUAGE_CHOICES, local_pattern, user_language
from rentalars.core.i18n import SUPPORTED as SUPPORTED_LANGUAGES

# --- Serializers ----------------------------------------------------------------


class RoleSerializer(CleanModelSerializer):
    """A role with its module levels and special rights (AUT-010)."""

    user_count = serializers.IntegerField(source="users.count", read_only=True)

    class Meta:
        model = Role
        fields = ["id", "name", "description", "module_levels", "special_rights", "project_scope", "user_count"]


class UserSerializer(CleanModelSerializer):
    """A user account. Passwords are never delivered and never set here (AUT-011)."""

    roles = serializers.PrimaryKeyRelatedField(many=True, queryset=Role.objects.all(), required=False)
    full_name = serializers.CharField(source="get_full_name", read_only=True)
    has_password = serializers.BooleanField(source="has_usable_password", read_only=True)
    #: AUT-029: the entry in the directory (LDAP) and the roles that come from it (they cannot be removed here).
    ldap_dn = serializers.CharField(read_only=True)
    directory_roles = serializers.SerializerMethodField(help_text="IDs of the roles the directory (LDAP) gave.")
    #: AUT-034: what the account may see of finances, personnel data and customer data (``accounts.data_access``).
    data_access = serializers.SerializerMethodField(
        help_text="finances: none, purchase_prices, prices, both; personnel_data: none, rates, people, both; "
        "customer_data: none, read, change – each no_access for a deactivated account."
    )

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "is_active",
            "valid_until",
            "is_superuser",
            "language",
            "roles",
            "has_password",
            "date_joined",
            "last_login",
            "data_access",  # AUT-034
            "local_account",  # AUT-029
            "ldap_dn",
            "directory_roles",
        ]
        read_only_fields = ["is_active", "date_joined", "last_login"]

    @extend_schema_field(serializers.ListField(child=serializers.IntegerField()))
    def get_directory_roles(self, user: User) -> list[int]:
        """AUT-029: the roles the directory gave; ``roles`` always includes them."""
        return sorted(services._directory_role_ids(user))

    @extend_schema_field(serializers.DictField(child=serializers.CharField()))
    def get_data_access(self, user: User) -> dict[str, str]:
        """AUT-034: finances, personnel data, customer data – as the columns of the lists show them."""
        from rentalars.accounts.data_access import of_user

        return of_user(user).as_document()

    def create(self, validated_data: dict[str, Any]) -> User:
        """Create the user and send the invitation by e-mail (AUT-011)."""
        roles = validated_data.pop("roles", [])
        validated_data.pop("is_superuser", None)
        local_account = validated_data.pop("local_account", False)  # AUT-029
        user = services.invite_user(roles=roles, **validated_data)
        if local_account:
            user.local_account = True
            user.save()
        return user

    def update(self, instance: User, validated_data: dict[str, Any]) -> User:
        """Change master data and roles; role changes are logged."""
        roles = validated_data.pop("roles", None)
        for name, value in validated_data.items():
            setattr(instance, name, value)
        instance.full_clean()
        instance.save()
        if roles is not None:
            services.set_user_roles(instance, roles)
        return instance


class ApiTokenSerializer(serializers.ModelSerializer):
    """A personal API token; the key itself is only shown once, on creation."""

    class Meta:
        model = ApiToken
        fields = [
            "id",
            "name",
            "key_prefix",
            "read_only",
            "allowed_modules",
            "created_at",
            "expires_at",
            "last_used_at",
            "revoked_at",
        ]
        read_only_fields = ["key_prefix", "created_at", "last_used_at", "revoked_at"]

    def validate_allowed_modules(self, value: Any) -> list[str]:
        """Accept only known module names."""
        if not isinstance(value, list) or any(module not in Module.values for module in value):
            raise serializers.ValidationError(_("Unknown module in the list."))
        return value


# --- Login and own profile ------------------------------------------------------


def _profile(request: Request) -> dict[str, Any]:
    """Describe the logged-in user and what the user may do."""
    rights = request_rights(request)
    user = request.user
    person = getattr(user, "person", None)
    return {
        "id": user.pk,
        "username": user.username,
        "email": user.email,
        "full_name": user.get_full_name(),
        "roles": list(user.roles.values_list("name", flat=True)),
        "module_levels": {module: rights.level(module) for module in Module.values},
        # AUT-017: what holds in every project; lower than "module_levels" for roles
        # that cover assigned projects only.
        "module_levels_everywhere": {module: rights.level_everywhere(module) for module in Module.values},
        "special_rights": sorted(rights.special_rights),
        # AUT-012: the person in personnel this account belongs to; times are recorded for it.
        "person": {"id": person.pk, "name": person.name} if person is not None else None,
        # UIX-029: the language chosen ("" = the installation's) and the one in effect.
        "language": user.language,
        "effective_language": user_language(user),
        # API-016 (mobile app): what the server can, without guessing it from fields.
        "server_version": rentalars.__version__,
    }


class LoginView(APIView):
    """``POST /auth/login`` – start a browser session with name and password (AUT-002)."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    schema_tag = "auth"

    @extend_schema(
        request=inline_serializer(
            "LoginRequest",
            {
                "username": serializers.CharField(),
                "password": serializers.CharField(),
                "code": serializers.CharField(required=False, help_text="Code of the authenticator app (AUT-006)"),
            },
        ),
        responses={200: inline_serializer("Profile", {"username": serializers.CharField()})},
    )
    def post(self, request: Request) -> Response:
        """Check the credentials; too many failures lock the name for a while (AUT-005)."""
        identifier = str(body_of(request).get("username", ""))
        password = str(body_of(request).get("password", ""))
        ip_address = services.client_ip(request)
        if services.is_locked_out(identifier, ip_address):
            return error_response(
                "locked_out",
                _("Too many failed attempts. Please wait a few minutes and try again."),
                status.HTTP_429_TOO_MANY_REQUESTS,
            )
        user = authenticate(request, username=identifier, password=password)
        # AUT-005: with two-factor login the right password is not yet a success – it would clear the
        # failures, and the code could be guessed without end. The success is noted once the code is right.
        awaits_code = user is not None and user.has_two_factor
        if not awaits_code:
            services.record_login_attempt(identifier, ip_address, successful=user is not None)
        if user is None:
            services.record_security_event(SecurityEventKind.LOGIN_FAILED, identifier=identifier, request=request)
            message = _("Name or password are wrong.")
            if getattr(request, "directory_unavailable", False):  # AUT-029
                from rentalars.accounts.views import DIRECTORY_UNAVAILABLE_TEXT

                message = f"{message} {DIRECTORY_UNAVAILABLE_TEXT()}"
            return error_response("invalid_credentials", message, status.HTTP_400_BAD_REQUEST)
        if user.has_two_factor:
            # AUT-006: with two-factor login the code belongs to the same request.
            code = str(body_of(request).get("code", ""))
            if not code:
                return error_response(
                    "code_required", _("Enter the code of your authenticator app."), status.HTTP_400_BAD_REQUEST
                )
            # The name as the account knows it, whatever the person typed (e-mail address, other case): the count
            # of wrong codes must not be dodged by another spelling.
            if services.is_locked_out(user.username, ip_address):
                return error_response(
                    "locked_out",
                    _("Too many failed attempts. Please wait a few minutes and try again."),
                    status.HTTP_429_TOO_MANY_REQUESTS,
                )
            if not twofactor.verify_code(user, code):
                services.record_login_attempt(user.username, ip_address, successful=False)
                services.record_security_event(SecurityEventKind.SECOND_FACTOR_FAILED, user=user, request=request)
                return error_response("invalid_code", _("The code is not right."), status.HTTP_400_BAD_REQUEST)
            services.record_login_attempt(identifier, ip_address, successful=True)
            services.record_login_attempt(user.username, ip_address, successful=True)
        elif user.needs_two_factor:
            # In the browser such a user can do nothing but set it up; the API has no page for that.
            return error_response(
                "two_factor_setup_required",
                _("Your account must use two-factor login. Set it up in the browser first."),
                status.HTTP_403_FORBIDDEN,
            )
        login(request._request, user)
        request.user = user
        return Response(_profile(request))


class LogoutView(APIView):
    """``POST /auth/logout`` – end the browser session."""

    permission_classes = [IsAuthenticated]
    schema_tag = "auth"

    @extend_schema(request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        """Log out."""
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetView(APIView):
    """``POST /auth/password-reset`` – send the reset link by e-mail (AUT-004)."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    schema_tag = "auth"

    @extend_schema(
        request=inline_serializer("PasswordResetRequest", {"email": serializers.EmailField()}),
        responses={204: None},
    )
    def post(self, request: Request) -> Response:
        """Always answer the same, whether the address is known or not.

        A different answer for unknown addresses would let strangers find out
        who has an account.
        """
        from rentalars.accounts.forms import ResetPasswordForm

        # AUT-027: invited accounts too; UIX-029: the mail in the language of the account.
        form = ResetPasswordForm({"email": str(body_of(request).get("email", ""))})
        if form.is_valid():
            form.save(
                request=request,
                use_https=request.is_secure(),
                email_template_name="accounts/email/password_reset.txt",
                subject_template_name="accounts/email/password_reset_subject.txt",
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


#: The answer of ``/me`` (one component for GET and PATCH).
ME_RESPONSE = inline_serializer(
    "Me",
    {
        "username": serializers.CharField(),
        "language": serializers.CharField(),
        "effective_language": serializers.CharField(),
        "server_version": serializers.CharField(help_text="The version of Rentalars, e.g. “1.0.0” (API-016)."),
    },
)


class MeView(APIView):
    """``GET /me`` – the logged-in user with roles and effective rights."""

    permission_classes = [IsAuthenticated]
    schema_tag = "auth"

    @extend_schema(responses={200: ME_RESPONSE})
    def get(self, request: Request) -> Response:
        """Return the profile."""
        return Response(_profile(request))

    @extend_schema(
        request=inline_serializer(
            "MeChange",
            {"language": serializers.ChoiceField(choices=LANGUAGE_CHOICES, allow_blank=True, required=False)},
        ),
        responses={200: ME_RESPONSE},
    )
    def patch(self, request: Request) -> Response:
        """Change the own settings: ``language`` – "de", "en" or "" for the installation's (UIX-029)."""
        if isinstance(request.auth, ApiToken) and request.auth.read_only:
            return error_response(
                "permission_denied", _("You do not have the right to do this."), status.HTTP_403_FORBIDDEN
            )
        body = body_of(request)
        unknown = sorted(set(body) - {"language"})
        if unknown:
            return error_response(
                "validation_error",
                _("The input is invalid."),
                status.HTTP_400_BAD_REQUEST,
                {name: [{"code": "unknown", "message": _("This field cannot be changed here.")}] for name in unknown},
            )
        if "language" in body:
            language = body.get("language")
            if language not in ("", *SUPPORTED_LANGUAGES):
                return error_response(
                    "validation_error",
                    _("The input is invalid."),
                    status.HTTP_400_BAD_REQUEST,
                    {"language": [{"code": "invalid_choice", "message": _("Choose “de”, “en” or nothing.")}]},
                )
            request.user.language = language
            request.user.save(update_fields=["language"])
            translation.activate(user_language(request.user))
        return Response(_profile(request))


class PermissionCatalogueView(APIView):
    """``GET /permissions`` – all modules, levels and special rights a role can grant."""

    permission_classes = [IsAuthenticated]
    schema_tag = "auth"

    @extend_schema(responses={200: inline_serializer("PermissionCatalogue", {"modules": serializers.ListField()})})
    def get(self, request: Request) -> Response:
        """Return the catalogue used to build the role editor."""
        return Response(
            {
                "modules": [
                    {"value": value, "label": str(label), "available": value not in FUTURE_MODULES}
                    for value, label in Module.choices
                ],
                "levels": [{"value": value, "label": str(label)} for value, label in Level.choices],
                "special_rights": [{"value": value, "label": str(label)} for value, label in SpecialRight.choices],
                "project_scopes": [{"value": value, "label": str(label)} for value, label in ProjectScope.choices],
            }
        )


# --- Users, roles, tokens ---------------------------------------------------------


class UserViewSet(NoDeleteViewSet):
    """``/users`` – accounts are created by invitation and deactivated, never deleted (AUT-009)."""

    module = Module.ADMINISTRATION
    queryset = User.objects.prefetch_related("roles").order_by("username")
    serializer_class = UserSerializer
    search_fields = ["username", "email", "first_name", "last_name"]
    filterset_fields = ["is_active"]
    ordering_fields = ["username", "email", "last_name", "date_joined"]

    @extend_schema(request=None, responses=UserSerializer)
    @action(detail=True, methods=["post"])
    def deactivate(self, request: Request, pk: str | None = None) -> Response:
        """Stop a user from logging in; data and history stay."""
        user = self.get_object()
        services.set_user_active(user, active=False, acting_user=request.user)
        return Response(self.get_serializer(user).data)

    @extend_schema(request=None, responses=UserSerializer)
    @action(detail=True, methods=["post"])
    def activate(self, request: Request, pk: str | None = None) -> Response:
        """Let a deactivated user log in again."""
        user = self.get_object()
        services.set_user_active(user, active=True)
        return Response(self.get_serializer(user).data)

    @extend_schema(
        request=None,
        responses={
            204: None,
            200: inline_serializer(
                "InvitationNotSent", {"sent": serializers.BooleanField(), "reason": serializers.CharField()}
            ),
        },
    )
    @action(detail=True, methods=["post"], url_path="send-invitation")
    def send_invitation(self, request: Request, pk: str | None = None) -> Response:
        """Send the link for setting a password again (AUT-011).

        EML-048: ``204`` when the mail went out, as before. Without a
        mail server it cannot: then ``200`` with ``{"sent": false, "reason": …}``.
        """
        from rentalars.mail.server import mail_state

        user = self.get_object()
        if not user.is_active:
            raise ValidationError(_("The user is deactivated."))
        services.send_invitation(user)
        state = mail_state()
        if state["sent"]:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response({"sent": False, "reason": state["reason"]})

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Create the user and send the invitation (AUT-011).

        EML-048: the answer carries ``invitation``: ``{"sent": true}``,
        ``{"sent": false, "reason": …}`` without a mail server, or
        ``{"sent": null}`` for a user without an e-mail address (no mail).
        """
        from rentalars.mail.server import mail_state

        response = super().create(request, *args, **kwargs)
        response.data["invitation"] = mail_state(sends_mail=bool(response.data.get("email")))
        return response

    @extend_schema(request=None, responses=UserSerializer)
    @action(detail=True, methods=["post"], url_path="reset-two-factor")
    def reset_two_factor(self, request: Request, pk: str | None = None) -> Response:
        """Switch two-factor login off for a user who lost phone and recovery codes (AUT-006).

        The user sets it up again at the next login if a role requires it.
        """
        user = self.get_object()
        if user.has_two_factor:
            twofactor.disable(user, by=request.user)
        return Response(self.get_serializer(user).data)


class RoleViewSet(ModuleViewSet):
    """``/roles`` – freely definable roles (AUT-010)."""

    module = Module.ADMINISTRATION
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    search_fields = ["name"]

    def perform_destroy(self, instance: Role) -> None:
        """A role that users still have cannot be deleted (ADM-006)."""
        if instance.users.exists():
            raise ValidationError(_("This role is still assigned to users and cannot be deleted."))
        instance.delete()


class ApiTokenViewSet(
    RightsViewMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """``/tokens`` – a user's own API tokens (AUT-021).

    Creating answers with the key in the field ``key``. It is shown this one
    time only. ``DELETE`` revokes a token.

    A token must not open more than it has itself (security fix):

    * a token limited to modules creates no tokens (403), and under
      ``/tokens`` it sees and revokes only itself – the token of an app on a
      phone cannot reach the others of its user;
    * a token with an expiry creates only tokens that expire no later than
      itself; ``expires_at`` must then be given;
    * a read-only token creates no tokens and changes nothing else of its user either (403; 400 before).
    """

    module = AUTHENTICATED_ONLY
    serializer_class = ApiTokenSerializer
    schema_tag = "auth"
    queryset = ApiToken.objects.none()

    def get_queryset(self) -> Any:
        """Only the caller's own tokens; a token limited to modules sees only itself."""
        tokens = ApiToken.objects.filter(user=self.request.user)
        caller = self.request.auth
        if isinstance(caller, ApiToken) and caller.allowed_modules:
            tokens = tokens.filter(pk=caller.pk)
        return tokens

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Create a token and reveal its key once."""
        caller = request.auth if isinstance(request.auth, ApiToken) else None
        if caller is not None and caller.read_only:
            raise ValidationError(_("A read-only token cannot create tokens."))
        if caller is not None and caller.allowed_modules:
            return error_response(
                "permission_denied",
                _("A token limited to modules cannot create tokens. Create tokens in the browser."),
                status.HTTP_403_FORBIDDEN,
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if caller is not None and caller.expires_at is not None:
            expires_at = serializer.validated_data.get("expires_at")
            if expires_at is None or expires_at > caller.expires_at:
                raise ValidationError(
                    {
                        "expires_at": _("This token expires on %(date)s. A token it creates must expire by then.")
                        % {"date": timezone.localtime(caller.expires_at).strftime(local_pattern("%d.%m.%Y %H:%M"))}
                    }
                )
        token, plain_key = ApiToken.create_for_user(request.user, **serializer.validated_data)
        data = dict(self.get_serializer(token).data)
        data["key"] = plain_key
        return Response(data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance: ApiToken) -> None:
        """Revoke instead of deleting, so that the list still shows what existed."""
        instance.revoke()


# --- Sessions and security log (AUT-008, AUT-022) -------------------------------------------


class SessionListView(RightsViewMixin, APIView):
    """``GET /me/sessions`` – the browsers the caller is logged in with (AUT-008).

    API tokens are no sessions; they are listed under ``/tokens``.
    """

    permission_classes = [IsAuthenticated]
    schema_tag = "auth"

    @extend_schema(responses={200: inline_serializer("Sessions", {"id": serializers.IntegerField()}, many=True)})
    def get(self, request: Request) -> Response:
        """All sessions, the most recently active first."""
        from rentalars.accounts.models import UserSession

        current = getattr(getattr(request, "session", None), "session_key", None)
        return Response(
            [
                {
                    "id": item.pk,
                    "created_at": item.created_at,
                    "last_activity": item.last_activity,
                    "ip_address": item.ip_address,
                    "user_agent": item.user_agent,
                    "is_current": item.session_key == current,
                }
                for item in UserSession.objects.filter(user=request.user)
            ]
        )


class SessionDetailView(RightsViewMixin, APIView):
    """``DELETE /me/sessions/{id}`` – end a session: that browser is logged out at its next request."""

    permission_classes = [IsAuthenticated, WritableCaller]
    schema_tag = "auth"

    @extend_schema(responses={204: None})
    def delete(self, request: Request, pk: int) -> Response:
        """End one session of the caller."""
        from django.shortcuts import get_object_or_404

        from rentalars.accounts.models import UserSession
        from rentalars.accounts.sessions import end_session

        end_session(get_object_or_404(UserSession, pk=pk, user=request.user), by=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SecurityLogView(RightsViewMixin, APIView):
    """``GET /security-log`` – logins, failed logins, second factor, sessions (AUT-022).

    Filters: ``kind``, ``user`` (ID), ``q`` (entered name or address),
    ``since`` (ISO time). The newest entries come first, 50 per page.
    """

    permission_classes = [ModulePermission]
    module = Module.ADMINISTRATION
    schema_tag = "auth"

    @extend_schema(responses={200: inline_serializer("SecurityEvents", {"kind": serializers.CharField()}, many=True)})
    def get(self, request: Request) -> Response:
        """The entries, paginated."""
        from django.db.models import Q
        from django.utils.dateparse import parse_datetime

        from rentalars.accounts.models import SecurityEvent
        from rentalars.api.pagination import StandardPagination

        events = SecurityEvent.objects.select_related("user").order_by("-timestamp", "-id")
        params = request.query_params
        if params.get("kind") in SecurityEventKind.values:
            events = events.filter(kind=params["kind"])
        if str(params.get("user", "")).isdigit():
            events = events.filter(user_id=int(params["user"]))
        if params.get("q"):
            text = params["q"].strip()
            events = events.filter(Q(identifier__icontains=text) | Q(ip_address__startswith=text))
        since = parse_datetime(params.get("since", "") or "")
        if since is not None:
            events = events.filter(timestamp__gte=since)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(events, request, view=self)
        return paginator.get_paginated_response(
            [
                {
                    "id": event.pk,
                    "timestamp": event.timestamp,
                    "kind": event.kind,
                    "user": event.user_id,
                    "username": event.user.username if event.user_id else None,
                    "identifier": event.identifier,
                    "ip_address": event.ip_address,
                    "user_agent": event.user_agent,
                    "detail": event.detail,
                }
                for event in page or []
            ]
        )
