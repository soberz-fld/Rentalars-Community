# SPDX-License-Identifier: GPL-3.0-or-later
"""API of the directory login: settings, group assignments, tests, comparison (AUT-029; API-002).

All of it needs the module "Administration" (read to look, write to change, delete to delete an assignment):

* ``GET/PATCH /ldap/settings`` – the settings; the password of the search account (``bind_password``) can be
  set, or removed with ``remove_bind_password``, never read (``has_bind_password`` says whether one is stored)
* ``GET/POST /ldap/mappings``, ``GET/PUT/PATCH/DELETE /ldap/mappings/{id}`` – which group gets which roles
* ``POST /ldap/test-connection`` – step by step: servers, encryption, search account, search bases
* ``POST /ldap/test-login`` – a dry run for ``username`` (``password`` optional): found entry, attributes,
  groups, resulting roles; nothing is written
* ``POST /ldap/sync`` – compare the accounts with the directory; ``dry_run`` is true unless given as false
* ``POST /ldap/adopt-dn`` – link the account of a user who was moved in the directory to the new entry
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.exceptions import APIException, Throttled
from rest_framework.request import Request
from rest_framework.response import Response

from rentalars.accounts import ldap_client, ldap_sync
from rentalars.accounts.ldap_forms import apply_password_change, note_password_change, set_mapping_roles
from rentalars.accounts.ldap_views import name_only_warning, password_removed_text
from rentalars.accounts.models import LdapGroupMapping, LdapSettings, Role
from rentalars.accounts.rights import Module
from rentalars.api.serializers import CleanModelSerializer
from rentalars.api.views import ModuleAPIView, ModuleViewSet, body_of

SETTINGS_FIELDS = [
    "enabled",
    "server_uris",
    "start_tls",
    "verify_certificate",
    "ca_certificate_path",
    "ca_certificate_pem",
    "timeout_seconds",
    "bind_dn",
    "user_search_base",
    "user_search_filter",
    "attribute_username",
    "attribute_email",
    "attribute_first_name",
    "attribute_last_name",
    "group_mode",
    "member_of_attribute",
    "group_search_base",
    "group_search_filter",
    "allow_local_login",
    "auto_create_users",
    "link_existing_accounts",
    "sync_daily",
]


class DirectoryUnavailable(APIException):
    """The directory could not be asked (the text is for the administrator who called)."""

    status_code = status.HTTP_502_BAD_GATEWAY
    default_code = "directory_unavailable"
    default_detail = "The directory cannot be reached."


class LdapSettingsSerializer(CleanModelSerializer):
    """The settings; the password of the search account is write-only."""

    bind_password = serializers.CharField(write_only=True, required=False, allow_blank=True, trim_whitespace=False)
    remove_bind_password = serializers.BooleanField(write_only=True, required=False, default=False)
    has_bind_password = serializers.BooleanField(read_only=True)
    last_sync_at = serializers.DateTimeField(read_only=True)
    last_sync_summary = serializers.CharField(read_only=True)
    warnings = serializers.SerializerMethodField(
        help_text="Unsafe settings in plain words: unencrypted servers, name-only group assignments, linking by name."
    )

    class Meta:
        model = LdapSettings
        fields = [
            *SETTINGS_FIELDS,
            "bind_password",
            "remove_bind_password",
            "has_bind_password",
            "last_sync_at",
            "last_sync_summary",
            "warnings",
        ]

    def get_warnings(self, settings: LdapSettings) -> list[str]:
        """Review: what the settings page warns about."""
        return ldap_sync.warnings_for(settings)

    def update(self, instance: LdapSettings, validated_data: dict[str, Any]) -> LdapSettings:
        """Change the settings; the stored password follows the rules of :func:`apply_password_change`."""
        new_password = validated_data.pop("bind_password", None) or None
        remove = bool(validated_data.pop("remove_bind_password", False))
        old_uris, old_bind_dn = instance.server_uris, instance.bind_dn
        for name, value in validated_data.items():
            setattr(instance, name, value)
        outcome = apply_password_change(
            instance, old_uris=old_uris, old_bind_dn=old_bind_dn, new_password=new_password, remove=remove
        )
        instance.full_clean()
        instance.save()
        note_password_change(instance, outcome)
        self.password_outcome = outcome
        return instance


class LdapSettingsView(ModuleAPIView):
    """``/ldap/settings`` – how Rentalars reaches the directory (AUT-029)."""

    module = Module.ADMINISTRATION
    schema_tag = "ldap"

    @extend_schema(responses={200: LdapSettingsSerializer})
    def get(self, request: Request) -> Response:
        """The settings, without the password."""
        return Response(LdapSettingsSerializer(LdapSettings.load()).data)

    @extend_schema(request=LdapSettingsSerializer, responses={200: LdapSettingsSerializer})
    def patch(self, request: Request) -> Response:
        """Change single settings; a change of servers or search account removes the stored password."""
        serializer = LdapSettingsSerializer(LdapSettings.load(), data=body_of(request), partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        data = dict(serializer.data)
        outcome = getattr(serializer, "password_outcome", "")
        if outcome:
            data["password_notice"] = password_removed_text(outcome)
        return Response(data)


class LdapMappingSerializer(CleanModelSerializer):
    """A group and the roles its members get."""

    roles = serializers.PrimaryKeyRelatedField(many=True, queryset=Role.objects.all(), allow_empty=False)
    name_only = serializers.BooleanField(source="is_name_only", read_only=True)
    warning = serializers.SerializerMethodField(help_text="Not empty when the group is named by its name only.")

    class Meta:
        model = LdapGroupMapping
        fields = ["id", "group", "roles", "priority", "last_match", "note", "name_only", "warning"]
        read_only_fields = ["last_match"]  # review R4: set on the page; the table decides by priority

    def get_warning(self, mapping: LdapGroupMapping) -> str:
        """Review: a name-only group matches a group of that name anywhere in the directory."""
        return name_only_warning(mapping) if mapping.is_name_only else ""

    def create(self, validated_data: dict[str, Any]) -> LdapGroupMapping:
        """Create the assignment; the roles are noted in the change log."""
        roles = validated_data.pop("roles")
        mapping = LdapGroupMapping(**validated_data)
        mapping.full_clean()
        mapping.save()
        set_mapping_roles(mapping, roles)
        return mapping

    def update(self, instance: LdapGroupMapping, validated_data: dict[str, Any]) -> LdapGroupMapping:
        """Change the assignment; a change of its roles is noted in the change log."""
        roles = validated_data.pop("roles", None)
        for name, value in validated_data.items():
            setattr(instance, name, value)
        instance.full_clean()
        instance.save()
        if roles is not None:
            set_mapping_roles(instance, roles)
        return instance


class LdapMappingViewSet(ModuleViewSet):
    """``/ldap/mappings`` – the table "group → roles" (AUT-029)."""

    module = Module.ADMINISTRATION
    schema_tag = "ldap"
    queryset = LdapGroupMapping.objects.prefetch_related("roles")
    serializer_class = LdapMappingSerializer
    search_fields = ["group", "note"]


def _config() -> ldap_client.DirectoryConfig:
    """The saved settings as a snapshot; a missing server or search base is a plain 400."""
    settings = LdapSettings.load()
    if not settings.uris or not settings.user_search_base:
        raise serializers.ValidationError(_("Enter and save at least a server and the search base for users first."))
    try:
        return ldap_client.DirectoryConfig.from_settings(settings)
    except ldap_client.DirectoryError as error:
        raise DirectoryUnavailable(str(error)) from error


class LdapTestConnectionView(ModuleAPIView):
    """``POST /ldap/test-connection`` – try the saved settings step by step."""

    module = Module.ADMINISTRATION
    schema_tag = "ldap"

    @extend_schema(
        request=None,
        responses={
            200: inline_serializer(
                "LdapConnectionReport",
                {
                    "ok": serializers.BooleanField(),
                    "steps": serializers.ListField(),
                    "warnings": serializers.ListField(child=serializers.CharField()),
                },
            )
        },
    )
    def post(self, request: Request) -> Response:
        """Servers, encryption, search account, search bases – whatever fails is a step that is not ``ok``."""
        report = ldap_client.check_connection(_config())
        return Response(
            {"ok": report.ok, "steps": report.steps, "warnings": ldap_sync.warnings_for(LdapSettings.load())}
        )


class LdapTestLoginView(ModuleAPIView):
    """``POST /ldap/test-login`` – what a login of this user would find and do; nothing is written."""

    module = Module.ADMINISTRATION
    schema_tag = "ldap"

    @extend_schema(
        request=inline_serializer(
            "LdapTestLoginRequest",
            {"username": serializers.CharField(), "password": serializers.CharField(required=False)},
        ),
        responses={200: inline_serializer("LdapLoginPreview", {"found": serializers.BooleanField()})},
    )
    def post(self, request: Request) -> Response:
        """Found entry, attributes, groups, matching assignments, resulting roles and what the login would do."""
        body = body_of(request)
        _config()
        try:
            preview = ldap_sync.preview_login(
                LdapSettings.load(),
                str(body.get("username", "")),
                str(body.get("password", "") or ""),
                request=request,
                acting_user=request.user,
            )
        except ValueError as error:
            raise serializers.ValidationError({"username": [_("This is not a usable user name.")]}) from error
        except ldap_client.DirectoryError as error:
            if error.code == "throttled":  # Review: the limit of the login counts here too
                raise Throttled(detail=str(error)) from error
            raise DirectoryUnavailable(str(error)) from error
        return Response(preview)


class LdapSyncView(ModuleAPIView):
    """``POST /ldap/sync`` – compare the accounts of the directory with it, like ``manage.py ldap_sync``."""

    module = Module.ADMINISTRATION
    schema_tag = "ldap"

    @extend_schema(
        request=inline_serializer(
            "LdapSyncRequest",
            {"dry_run": serializers.BooleanField(required=False), "force": serializers.BooleanField(required=False)},
        ),
        responses={200: inline_serializer("LdapSyncReport", {"applied": serializers.BooleanField()})},
    )
    def post(self, request: Request) -> Response:
        """``dry_run`` (default true) only reports; with ``dry_run: false`` the differences are written."""
        body = body_of(request)
        _config()
        apply = body.get("dry_run", True) is False
        try:
            report = ldap_sync.compare_accounts(
                LdapSettings.load(), apply=apply, force=bool(body.get("force")) and apply
            )
        except ldap_client.DirectoryError as error:
            raise DirectoryUnavailable(str(error)) from error
        return Response(report.as_document())


class LdapAdoptDnView(ModuleAPIView):
    """``POST /ldap/adopt-dn`` – link an account to the new entry of a user who was moved in the directory."""

    module = Module.ADMINISTRATION
    schema_tag = "ldap"

    @extend_schema(
        request=inline_serializer("LdapAdoptDnRequest", {"username": serializers.CharField()}),
        responses={200: inline_serializer("LdapAdoptDn", {"account_id": serializers.IntegerField()})},
    )
    def post(self, request: Request) -> Response:
        """The old entry must be gone and the account must be a plain one (no local account, no "all rights")."""
        _config()
        try:
            done = ldap_sync.adopt_dn(LdapSettings.load(), str(body_of(request).get("username", "")), request=request)
        except ValueError as error:
            raise serializers.ValidationError({"username": [_("This is not a usable user name.")]}) from error
        except DjangoValidationError as error:
            raise serializers.ValidationError({"username": error.messages}) from error
        except ldap_client.DirectoryError as error:
            raise DirectoryUnavailable(str(error)) from error
        return Response(done)
