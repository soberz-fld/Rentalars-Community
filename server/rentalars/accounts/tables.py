# SPDX-License-Identifier: GPL-3.0-or-later
"""The list of user accounts as a table with columns to choose (UIX-015, IMP-005)."""

from __future__ import annotations

from typing import Any

from django.db.models import Case, IntegerField, OuterRef, Value, When
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext_lazy as _

from rentalars.accounts import data_access
from rentalars.accounts.models import Role
from rentalars.core.i18n import local_pattern
from rentalars.core.tables import Column, TableDefinition, badge, date_text, first_value, grouped_by_day, link


def _user_name(user: Any) -> Any:
    name = link(reverse("accounts:user_edit", args=[user.pk]), user.username)
    full = user.get_full_name()
    if full:
        return format_html('{}<div class="muted small">{}</div>', name, full)
    return name


def _roles(user: Any) -> Any:
    roles = format_html_join(" ", '<span class="badge">{}</span>', ((role.name,) for role in user.roles.all()))
    if user.is_superuser:
        return format_html("{} {}", roles, badge(_("all rights"), "solid"))
    return roles


def _status_text(user: Any) -> str:
    if not user.is_active:
        return str(_("deactivated"))
    if not user.has_usable_password():
        return str(_("invited"))
    return str(_("active"))


def _status(user: Any) -> Any:
    colour = "" if not user.is_active else ("yellow" if not user.has_usable_password() else "green")
    cell = badge(_status_text(user), colour)
    if user.valid_until:
        until = _("valid until %(date)s") % {"date": user.valid_until.strftime(local_pattern("%d.%m.%Y"))}
        return format_html('{}<div class="muted small">{}</div>', cell, until)
    return cell


USER_TABLE = TableDefinition(
    "users",
    [
        # UIX-044: every column groups – by its field where it shows one, else by the value shown.
        Column(
            "user",
            _("User"),
            cell=_user_name,
            text=lambda user: user.username,
            sort="username",
            fixed=True,
            group="username",
        ),
        Column("email", _("E-mail"), cell=lambda user: user.email, sort=("email", "username"), group="email"),
        Column(
            "roles",
            _("Roles"),
            cell=_roles,
            text=lambda user: ", ".join(role.name for role in user.roles.all()) + (" *" if user.is_superuser else ""),
            # UIX-015: by the first role in the alphabet; who has all rights at the end.
            sort=(
                "is_superuser",
                first_value(Role.objects.filter(users=OuterRef("pk")), "name"),
                "username",
            ),
        ),
        Column(
            "status",
            _("Status"),
            cell=_status,
            text=_status_text,
            sort=("-is_active", "username"),
            group="is_active",  # UIX-040
            group_label=lambda user: _("active") if user.is_active else _("deactivated"),
        ),
        Column(
            "name", _("Name"), cell=lambda user: user.get_full_name(), sort=("last_name", "first_name"), default=False
        ),
        Column(
            "last_login",
            _("Last login"),
            cell=lambda user: date_text(user.last_login),
            text=lambda user: user.last_login,
            sort="last_login",
            css="nowrap",
            default=False,
            **grouped_by_day("last_login"),
        ),
        Column(
            "two_factor",
            _("Two-factor login"),
            cell=lambda user: _("yes") if user.has_two_factor else _("no"),
            text=lambda user: user.has_two_factor,
            # UIX-015: "no" before "yes", as the other yes/no columns.
            sort=(
                Case(When(totp_enabled_at__isnull=True, then=Value(0)), default=Value(1), output_field=IntegerField()),
                "username",
            ),
            default=False,
        ),
        Column(
            "valid_until",
            _("Valid until"),
            cell=lambda user: date_text(user.valid_until),
            text=lambda user: user.valid_until,
            sort=("valid_until", "username"),
            default=False,
            group="valid_until",
        ),
        Column(
            "joined",
            _("Created"),
            cell=lambda user: date_text(user.date_joined),
            text=lambda user: user.date_joined,
            sort="date_joined",
            css="nowrap",
            default=False,
            **grouped_by_day("date_joined"),
        ),
        # AUT-034: finances, personnel data, customer data – what the account may see (accounts/data_access.py).
        *data_access.columns(lambda user: user),
    ],
    default_sort="status",
    row_css=lambda user: "" if user.is_active else "is-muted",
)


# --- Roles and the security log (UIX-040) -------------------------------------------------


ROLE_TABLE = TableDefinition(
    "roles",
    [
        Column(
            "role",
            _("Role"),
            cell=lambda role: link(reverse("accounts:role_edit", args=[role.pk]), role.name),
            text=lambda role: role.name,
            sort="name",
            fixed=True,
            group="name",
        ),
        Column(
            "description",
            _("Description"),
            cell=lambda role: role.description,
            sort=("description", "name"),
            group="description",
        ),
        Column(
            "users",
            _("Users"),
            cell=lambda role: role.user_count,
            sort=("user_count", "name"),
            css="num",
        ),
        # UIX-040: what roles can be grouped by – the reach in the projects (AUT-016) and the second factor.
        Column(
            "project_scope",
            _("Project access"),
            cell=lambda role: role.get_project_scope_display(),
            sort=("project_scope", "name"),
            group="project_scope",
        ),
        Column(
            "two_factor",
            _("Two-factor login required"),
            cell=lambda role: _("yes") if role.requires_two_factor else _("no"),
            text=lambda role: role.requires_two_factor,
            sort=("requires_two_factor", "name"),
            default=False,
            group="requires_two_factor",
        ),
    ],
    default_sort="role",
)

#: The colour of an event: failed logins red, logins green (AUT-022).
EVENT_COLOURS = {"login_failed": "red", "2fa_failed": "red", "login": "green"}


def _event_user(event: Any) -> str:
    return str(event.user) if event.user_id else event.identifier


def _event_detail(event: Any) -> Any:
    agent = event.user_agent if len(event.user_agent) <= 60 else event.user_agent[:59] + "…"
    text = " · ".join(part for part in (event.detail, agent) if part)
    return format_html('<span class="muted small">{}</span>', text) if text else ""


SECURITY_EVENT_TABLE = TableDefinition(
    "security_log",
    [
        Column(
            "time",
            _("Time"),
            cell=lambda event: timezone.localtime(event.timestamp).strftime(local_pattern("%d.%m.%Y %H:%M:%S")),
            text=lambda event: event.timestamp,
            sort="timestamp",
            css="nowrap",
            fixed=True,
            **grouped_by_day("timestamp"),
        ),
        Column(
            "event",
            _("Event"),
            cell=lambda event: badge(event.get_kind_display(), EVENT_COLOURS.get(event.kind, "")),
            text=lambda event: event.get_kind_display(),
            sort=("kind", "-timestamp"),
            group="kind",
            group_label=lambda event: event.get_kind_display(),
        ),
        Column(
            "user",
            _("User"),
            cell=_event_user,
            sort=("user__username", "identifier", "-timestamp"),
            group="user",
        ),
        Column(
            "ip_address",
            _("IP address"),
            cell=lambda event: event.ip_address or "",
            sort=("ip_address", "-timestamp"),
            group="ip_address",
        ),
        Column(
            "detail",
            _("Detail"),
            cell=_event_detail,
            text=lambda event: " · ".join(part for part in (event.detail, event.user_agent) if part),
            sort=("detail", "user_agent", "-timestamp"),
        ),
    ],
    default_sort="-time",
)
