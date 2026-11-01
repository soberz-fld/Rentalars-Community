# SPDX-License-Identifier: GPL-3.0-or-later
"""Accounts and roles from the directory: planning, applying, comparing (AUT-029).

One rule set serves four callers, so they cannot disagree:

* the login (``ldap_backend``): find the account, create or update it, give it the roles of its groups;
* the dry run "Test login for user X" of the settings page and the API: the same plan, nothing written;
* the nightly comparison and ``manage.py ldap_sync`` (:func:`compare_accounts`);
* ``set_user_roles`` of the services, which keeps the roles the directory gave.

The rules:

* A user gets the roles of **all** group assignments whose group they are in (union), in the order of the
  priority; an assignment with "last match" ends the list. The directory never grants "has all rights".
* Roles from the directory are noted (``LdapRoleAssignment``) and cannot be removed by hand; roles an
  administrator gave stay. A role the administrator had given too stays when the directory takes it back.
* A user who is in no group with a role is refused; their account – if the directory keeps it – is deactivated
  (and activated again when they are back in such a group). Accounts an administrator deactivated stay so.
* The directory never touches a local (emergency) account or an account with "has all rights" – found by the
  name or by the linked entry –, and it never deactivates the last account that can change the settings, nor
  takes its administrator role away.
* An account of Rentalars that is not linked to the directory yet is taken over by a user of the same name only
  if the settings say so (``link_existing_accounts``, off by default): a name in the directory
  is not proof of being the same person.
* The comparison stops if it would deactivate more than half of the accounts (a wrong filter, a directory
  that answers with nothing) unless it is told to go on.
"""

from __future__ import annotations

import contextlib
import logging
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.accounts import ldap_client
from rentalars.accounts.ldap_client import DirectoryConfig, DirectoryEntry
from rentalars.accounts.models import (
    LdapGroupMapping,
    LdapRoleAssignment,
    LdapSettings,
    Role,
    SecurityEventKind,
    User,
)
from rentalars.accounts.rights import Level, Module
from rentalars.core.audit import acting_as, record_event

logger = logging.getLogger(__name__)

#: What the security log says (in English, like its other details) when the directory refuses a user.
REASONS = {
    "no_group": "in no group with a role",
    "no_account": "no account and accounts are not created",
    "protected": "account must not be taken over (local account or all rights)",
    "moved": "account must not be taken over: it is linked to another entry (moved in the directory? "
    "an administrator can adopt the new DN)",
    "not_linked": "an account of this name exists but is not linked to the directory (setting "
    "“link existing accounts” is off)",
    "collision": "username equals another account except for case or accents (database collation)",
    "invalid_username": "username not usable",
    "disabled": "account deactivated by an administrator",
    "expired": "account expired",
}

#: A comparison that would deactivate more accounts than this share (and more than 3) stops.
MAX_DEACTIVATION_SHARE = 0.5


# --- Group assignments -------------------------------------------------------------------------------------


@dataclass
class RoleDecision:
    """Which roles the groups of a user give, and by which assignments."""

    roles: list[Role] = field(default_factory=list)
    mappings: list[LdapGroupMapping] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)

    @property
    def role_names(self) -> list[str]:
        """The names of the roles, sorted."""
        return sorted(role.name for role in self.roles)


def decide_roles(groups: list[str]) -> RoleDecision:
    """The roles a user gets from the groups: union over all matching assignments, until a "last match"."""
    decision = RoleDecision(groups=list(groups))
    seen: set[int] = set()
    for mapping in LdapGroupMapping.objects.prefetch_related("roles").order_by("priority", "id"):
        if not any(ldap_client.group_matches(mapping.group_key, group) for group in groups):
            continue
        decision.mappings.append(mapping)
        for role in mapping.roles.all():
            if role.pk not in seen:
                seen.add(role.pk)
                decision.roles.append(role)
        if mapping.last_match:
            break
    decision.roles.sort(key=lambda role: role.name)
    return decision


def managed_role_ids(user: User) -> set[int]:
    """The IDs of the roles the directory gave this user."""
    if not user.pk:
        return set()
    return set(LdapRoleAssignment.objects.filter(user=user).values_list("role_id", flat=True))


# --- The plan for one user ----------------------------------------------------------------------------------


@dataclass
class UserPlan:
    """What the directory says about one user and what would be done with the account.

    ``action`` is one of ``create``, ``link``, ``update``, ``unchanged``, ``deactivate``, ``reactivate`` and
    ``refuse``; ``reason`` (for ``refuse`` and ``deactivate``) is ``no_group``, ``no_account``, ``protected``,
    ``invalid_username``, ``disabled``, ``expired`` or ``not_in_directory``.
    """

    action: str
    username: str = ""
    dn: str = ""
    email: str = ""
    first_name: str = ""
    last_name: str = ""
    user: User | None = None
    decision: RoleDecision = field(default_factory=RoleDecision)
    reason: str = ""
    message: str = ""
    roles_before: list[str] = field(default_factory=list)
    roles_after: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def refused(self) -> bool:
        """Whether the user must not log in."""
        return self.action in {"refuse", "deactivate"}

    def as_document(self) -> dict[str, Any]:
        """The plan as plain data for the page and the API (no password, no user object)."""
        return {
            "action": self.action,
            "reason": self.reason,
            "message": self.message,
            "username": self.username,
            "dn": self.dn,
            "email": self.email,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "account_id": self.user.pk if self.user else None,
            "groups": self.decision.groups,
            "matched_assignments": [mapping.group for mapping in self.decision.mappings],
            "roles_from_directory": self.decision.role_names,
            "roles_before": self.roles_before,
            "roles_after": self.roles_after,
            "notes": self.notes,
        }


def _same_name(first: str, second: str) -> bool:
    """Whether two usernames are the same for Rentalars: Unicode NFC and case, but accents count."""
    return unicodedata.normalize("NFC", first).casefold() == unicodedata.normalize("NFC", second).casefold()


def _accounts_named(username: str) -> list[User]:
    """The accounts the database finds for a name – with MariaDB's collation also ``muller`` for ``müller``."""
    return list(User.objects.filter(username__iexact=username).order_by("pk")[:5])


def _find_account(entry: DirectoryEntry, username: str) -> tuple[User | None, str]:
    """The account that belongs to a directory entry – by its DN, else by the username – and why not, if it must not.

    The second part is ``""`` or ``protected`` (a local account or "has all rights", found by the DN as well as by
    the name), ``moved`` (the account of this name is linked to another entry) or ``collision`` (the database
    takes another account for the same name – accents are ignored by its collation).
    """
    wanted = ldap_client.dn_key(entry.dn)
    for user in User.objects.filter(ldap_dn__iexact=entry.dn).exclude(ldap_dn=""):
        if ldap_client.dn_key(user.ldap_dn) == wanted:
            return user, "protected" if user.local_account or user.is_superuser else ""
    candidates = _accounts_named(username)
    if not candidates:
        return None, ""
    for user in candidates:
        if _same_name(user.username, username):
            if user.local_account or user.is_superuser:
                return user, "protected"
            if user.ldap_dn and ldap_client.dn_key(user.ldap_dn) != wanted:
                return user, "moved"
            return user, ""
    return candidates[0], "collision"


def _valid_username(username: str) -> bool:
    try:
        UnicodeUsernameValidator()(username)
    except ValidationError:
        return False
    return len(username) <= 150


def plan_for(entry: DirectoryEntry, groups: list[str], config: DirectoryConfig, settings: LdapSettings) -> UserPlan:
    """Decide, without writing anything, what the directory login of an entry does to the accounts."""
    username = entry.first(config.attribute_username)
    plan = UserPlan(
        action="refuse",
        username=username,
        dn=entry.dn,
        email=entry.first(config.attribute_email).lower(),
        first_name=entry.first(config.attribute_first_name)[:150],
        last_name=entry.first(config.attribute_last_name)[:150],
        decision=decide_roles(groups),
    )
    if plan.email:
        try:
            validate_email(plan.email)
        except ValidationError:
            plan.notes.append(_("“%(email)s” is not an e-mail address and is not taken over.") % {"email": plan.email})
            plan.email = ""
    if not username:
        plan.reason = "invalid_username"
        plan.message = _("The entry %(dn)s has no value in the attribute “%(attribute)s” (the username).") % {
            "dn": entry.dn,
            "attribute": config.attribute_username,
        }
        return plan
    if not _valid_username(username):
        plan.reason = "invalid_username"
        plan.message = _(
            "The username “%(name)s” has characters that Rentalars does not allow (letters, digits and @ . + - _ only)."
        ) % {"name": username}
        return plan

    for mapping in plan.decision.mappings:
        if mapping.is_name_only:
            plan.notes.append(
                _(
                    "The assignment “%(group)s” names the group only by its name: it matches a group of that name "
                    "anywhere in the directory. Use the full DN."
                )
                % {"group": mapping.group}
            )
    user, blocked = _find_account(entry, username)
    plan.user = user
    if blocked:
        plan.reason = blocked
        name = user.username if user else username
        plan.message = {
            "protected": _(
                "An account “%(name)s” exists that the directory must not take over (local account or “has all "
                "rights”)."
            ),
            "moved": _(
                "The account “%(name)s” is linked to another entry of the directory. If the user was moved there, "
                "an administrator can adopt the new entry."
            ),
            "collision": _(
                "The name is too close to the account “%(name)s” (it differs only in accents or capital letters, "
                "which the database does not tell apart)."
            ),
        }[blocked] % {"name": name}
        return plan
    if user is not None and not user.ldap_dn and not settings.link_existing_accounts:
        plan.reason = "not_linked"
        plan.message = _(
            "An account “%(name)s” exists in Rentalars that is not linked to the directory. Linking by name is "
            "switched off in the settings, so the login is refused."
        ) % {"name": user.username}
        return plan
    if user is not None:
        plan.roles_before = sorted(user.roles.values_list("name", flat=True))

    if not plan.decision.roles:
        plan.reason = "no_group"
        plan.message = _("%(name)s is in none of the groups that have roles assigned.") % {"name": username}
        if user is not None and user.ldap_dn and user.is_active:
            plan.action = "deactivate"
        return plan

    if user is None:
        if not settings.auto_create_users:
            plan.reason = "no_account"
            plan.message = _("%(name)s has no account in Rentalars, and accounts are not created at the login.") % {
                "name": username
            }
            return plan
        plan.action = "create"
        plan.roles_after = plan.decision.role_names
        if plan.email and User.objects.filter(email__iexact=plan.email).exists():
            plan.notes.append(
                _("The e-mail address %(email)s is used by another account and is not taken over.")
                % {"email": plan.email}
            )
            plan.email = ""
        return plan

    # An existing account.
    if user.has_expired:
        plan.reason = "expired"
        plan.message = _("The account of %(name)s has expired.") % {"name": username}
        return plan
    if not user.is_active and not (user.ldap_deactivated_at and user.ldap_dn):
        plan.reason = "disabled"
        plan.message = _("The account of %(name)s was deactivated by an administrator.") % {"name": username}
        return plan

    plan.action = "link" if not user.ldap_dn else "update"
    if not user.is_active:
        plan.action = "reactivate"
    final = _final_roles(user, plan.decision.roles)
    plan.roles_after = sorted(role.name for role in final[0])
    if plan.email and User.objects.filter(email__iexact=plan.email).exclude(pk=user.pk).exists():
        plan.notes.append(
            _("The e-mail address %(email)s is used by another account and is not taken over.") % {"email": plan.email}
        )
        plan.email = ""
    changed = (
        plan.action in {"link", "reactivate"}
        or plan.roles_after != plan.roles_before
        or user.ldap_dn != entry.dn
        or (plan.email and plan.email != (user.email or ""))
        or (plan.first_name and plan.first_name != user.first_name)
        or (plan.last_name and plan.last_name != user.last_name)
    )
    if not changed:
        plan.action = "unchanged"
    return plan


def _final_roles(user: User, desired: list[Role]) -> tuple[list[Role], dict[int, bool]]:
    """The roles of an account after the directory spoke, and for each directory role whether it was also manual.

    Manual roles stay; roles of the directory are exactly ``desired``; a role the directory gave before and
    that an administrator had given as well (``also_manual``) stays when the directory takes it back.
    """
    assignments = {a.role_id: a for a in LdapRoleAssignment.objects.filter(user=user)}
    current = {role.pk: role for role in user.roles.all()}
    keep = {pk: role for pk, role in current.items() if pk not in assignments or assignments[pk].also_manual}
    also_manual = {}
    for role in desired:
        also_manual[role.pk] = role.pk in current and (role.pk not in assignments or assignments[role.pk].also_manual)
        keep[role.pk] = role
    return sorted(keep.values(), key=lambda role: role.name), also_manual


# --- Applying a plan ----------------------------------------------------------------------------------------


def _audit(kind: str, user: User | None, detail: str, *, identifier: str = "", request: Any = None) -> None:
    from rentalars.accounts import services

    services.record_security_event(kind, user=user, identifier=identifier, request=request, detail=detail)


def _is_administrator_set(roles: list[Role]) -> bool:
    return any(role.level_of(Module.ADMINISTRATION) >= Level.WRITE for role in roles)


def apply_plan(plan: UserPlan, config: DirectoryConfig, *, request: Any = None) -> User | None:
    """Write what the plan says; returns the account (``None`` if there is none or it was deactivated).

    Everything is attributed to ``system:ldap`` in the change log and noted in the security log. The last
    account that can change the settings is neither deactivated nor loses its administrator role.
    """
    from rentalars.accounts import services

    if plan.action in {"refuse", "unchanged"} and plan.user is None:
        return None
    with transaction.atomic(), acting_as("system:ldap"):
        user = plan.user
        now = timezone.now()
        if plan.action == "deactivate" and user is not None:
            if services._is_last_administrator(user):
                plan.notes.append(
                    _("%(name)s is the last account that can change the settings and stays active.")
                    % {"name": user.username}
                )
                _audit(SecurityEventKind.LDAP_ACCOUNT, user, "not deactivated: last administrator", request=request)
                return None
            user.is_active = False
            user.ldap_deactivated_at = now
            user.save()
            record_event(user, "user.ldap_deactivated", {"reason": plan.reason})
            _audit(SecurityEventKind.LDAP_ACCOUNT, user, f"deactivated: {plan.reason}", request=request)
            return None
        if plan.action in {"refuse"}:
            return None

        created = False
        if plan.action == "create":
            user = User(
                username=plan.username,
                email=plan.email or None,
                first_name=plan.first_name,
                last_name=plan.last_name,
                ldap_dn=plan.dn[:500],
                ldap_synced_at=now,
            )
            user.set_unusable_password()
            user.full_clean()
            try:
                with transaction.atomic():
                    user.save()
            except IntegrityError as error:  # a name the collation of the database takes for another one (MariaDB)
                raise ValidationError(_("This username is already taken.")) from error
            created = True
            record_event(user, "user.ldap_created", {"dn": plan.dn, "roles": plan.decision.role_names})
            _audit(SecurityEventKind.LDAP_ACCOUNT, user, "created", request=request)
        assert user is not None
        if not created:
            changes: list[str] = []
            if not user.ldap_dn:
                changes.append("linked")
                record_event(user, "user.ldap_linked", {"dn": plan.dn})
            if user.ldap_dn != plan.dn[:500]:
                user.ldap_dn = plan.dn[:500]
            if plan.email and (user.email or "") != plan.email:
                user.email = plan.email
            if plan.first_name and user.first_name != plan.first_name:
                user.first_name = plan.first_name
            if plan.last_name and user.last_name != plan.last_name:
                user.last_name = plan.last_name
            if not user.is_active:
                user.is_active = True
                user.ldap_deactivated_at = None
                changes.append("reactivated")
                record_event(user, "user.ldap_reactivated", {"dn": plan.dn})
            user.ldap_synced_at = now
            user.save()
            if changes:
                _audit(SecurityEventKind.LDAP_ACCOUNT, user, ", ".join(changes), request=request)
        else:
            plan.user = user
        _apply_roles(user, plan, request=request)
        return user


def _apply_roles(user: User, plan: UserPlan, *, request: Any = None) -> None:
    """Make the roles of the account what the directory says, keeping the manual ones."""
    from rentalars.accounts import services

    final, also_manual = _final_roles(user, plan.decision.roles)
    before = sorted(user.roles.values_list("name", flat=True))
    after = sorted(role.name for role in final)
    if before != after and not _is_administrator_set(final) and services._is_last_administrator(user):
        plan.notes.append(
            _("%(name)s is the last account that can change the settings and keeps the administrator role.")
            % {"name": user.username}
        )
        _audit(SecurityEventKind.LDAP_ROLES, user, "kept: last administrator", request=request)
        final = list(user.roles.all())
        after = before
    user.roles.set(final)
    wanted = {role.pk for role in plan.decision.roles}
    LdapRoleAssignment.objects.filter(user=user).exclude(role_id__in=wanted).delete()
    for role in plan.decision.roles:
        LdapRoleAssignment.objects.update_or_create(
            user=user, role=role, defaults={"also_manual": also_manual.get(role.pk, False)}
        )
    user._rights_cache = None
    user._roles_cache = None
    plan.roles_after = after
    if before != after:
        details = {"before": before, "after": after, "groups": plan.decision.groups[:20]}
        record_event(user, "user.ldap_roles_changed", details)
        _audit(
            SecurityEventKind.LDAP_ROLES,
            user,
            f"{', '.join(before) or '-'} -> {', '.join(after) or '-'}",
            request=request,
        )


# --- The login ----------------------------------------------------------------------------------------------


@dataclass
class LoginResult:
    """The outcome of a directory login: the account, or why there is none (``why`` for administrators)."""

    user: User | None = None
    why: str = ""
    unavailable: bool = False


def sign_in(settings: LdapSettings, username: str, password: str, *, request: Any = None) -> LoginResult:
    """Check name and password against the directory and bring the account up to date (AUT-029).

    Returns a result without account when the name is unknown, the password is wrong, the user is in no group
    with a role, the account is closed – and when the directory cannot be reached (``unavailable``). The reasons
    reach the security log, never the user.
    """
    try:
        name = ldap_client.normalise_username(username)
    except ValueError:
        return LoginResult(why="unusable name")
    if not password:
        return LoginResult(why="empty password")
    try:
        config = DirectoryConfig.from_settings(settings)
        connection = ldap_client.open_service_connection(config)
    except ldap_client.DirectoryError as error:
        return _unavailable(error, name, request)
    try:
        entry = ldap_client.find_user(config, connection, name)
        if entry is None:
            _dummy_bind(config, password)  # costs what a known name costs
            return LoginResult(why="unknown name")
        if not ldap_client.check_password(config, entry.dn, password):
            return LoginResult(why="wrong password")
        groups = ldap_client.groups_of(config, connection, entry)
    except ldap_client.DirectoryError as error:
        return _unavailable(error, name, request)
    finally:
        ldap_client.close(connection)

    plan = plan_for(entry, groups, config, settings)
    try:
        user = apply_plan(plan, config, request=request)
    except ValidationError as error:
        _audit(
            SecurityEventKind.LDAP_REFUSED,
            None,
            f"data not usable: {error.messages}"[:250],
            identifier=name,
            request=request,
        )
        return LoginResult(why="data not usable")
    if plan.refused or user is None or not user.is_active:
        _audit(
            SecurityEventKind.LDAP_REFUSED,
            plan.user,
            REASONS.get(plan.reason, plan.reason or "refused"),
            identifier=name,
            request=request,
        )
        return LoginResult(why=plan.reason or "refused")
    return LoginResult(user=user)


def _dummy_bind(config: DirectoryConfig, password: str) -> None:
    """A bind that cannot succeed, for the time it takes; whatever goes wrong is of no interest."""
    with contextlib.suppress(ldap_client.DirectoryError):
        ldap_client.check_password(config, f"cn=rentalars-no-such-user,{config.user_search_base}", password)


def equalise_cost(settings: LdapSettings, username: str, password: str) -> None:
    """For a name the directory must not decide on (local account, "all rights"): the same round trip as for any name.

    Without it the answer would be faster for exactly those names and tell an attacker which accounts are
    emergency or superuser accounts. Nothing of the result is used.
    """
    try:
        name = ldap_client.normalise_username(username)
        config = DirectoryConfig.from_settings(settings)
        connection = ldap_client.open_service_connection(config)
    except (ValueError, ldap_client.DirectoryError):
        return
    try:
        ldap_client.find_user(config, connection, name)
        _dummy_bind(config, password)
    except ldap_client.DirectoryError:
        return
    finally:
        ldap_client.close(connection)


def _unavailable(error: ldap_client.DirectoryError, name: str, request: Any) -> LoginResult:
    logger.warning("Directory login for %r failed: %s", name, error.code)
    _audit(SecurityEventKind.LDAP_ERROR, None, f"{error.code}: {error}"[:250], identifier=name, request=request)
    return LoginResult(why=error.code, unavailable=True)


# --- Dry run: "Test login for user X" -----------------------------------------------------------------------


def preview_login(
    settings: LdapSettings, username: str, password: str = "", *, request: Any = None, acting_user: Any = None
) -> dict[str, Any]:
    """What a login of this name would do – found entry, attributes, groups, roles – and nothing written.

    With a password the bind of the user is tried too; the password is used once and not kept. That makes the dry
    run a way to test passwords, so every use is noted in the security log, and a test with a
    password counts against the same limit as a login: after too many wrong passwords for a name it is refused.

    Raises:
        DirectoryError: The directory could not be asked (``code`` ``throttled``: too many wrong passwords).
        ValueError: The name is unusable.
    """
    from rentalars.accounts import services

    name = ldap_client.normalise_username(username)
    address = services.client_ip(request) if request is not None else None
    actor = str(acting_user) if acting_user is not None else ""
    if password and services.is_locked_out(name, address):
        _audit(
            SecurityEventKind.LDAP_TEST,
            None,
            f"by {actor}: refused, too many wrong passwords",
            identifier=name,
            request=request,
        )
        raise ldap_client.DirectoryError(
            "throttled", _("Too many wrong passwords were tried for this name. Wait a few minutes.")
        )
    outcome = "directory not asked"
    try:
        config = DirectoryConfig.from_settings(settings)
        connection = ldap_client.open_service_connection(config)
        try:
            entry = ldap_client.find_user(config, connection, name)
            if entry is None:
                outcome = "user not found"
                return {"found": False, "message": _("The directory knows no user “%(name)s”.") % {"name": name}}
            groups = ldap_client.groups_of(config, connection, entry)
        finally:
            ldap_client.close(connection)
        plan = plan_for(entry, groups, config, settings)
        document = plan.as_document()
        password_ok = ldap_client.check_password(config, entry.dn, password) if password else None
        if password:
            outcome = "user found, password " + ("accepted" if password_ok else "refused")
            if not password_ok:
                services.record_login_attempt(name, address, successful=False)
        else:
            outcome = "user found"
        document.update(
            {
                "found": True,
                "attributes": {
                    "username": entry.first(config.attribute_username),
                    "email": entry.first(config.attribute_email),
                    "first_name": entry.first(config.attribute_first_name),
                    "last_name": entry.first(config.attribute_last_name),
                },
                "password_checked": bool(password),
                "password_ok": password_ok,
            }
        )
        return document
    except ldap_client.DirectoryError as error:
        outcome = f"directory error {error.code}"
        raise
    finally:
        _audit(SecurityEventKind.LDAP_TEST, None, f"by {actor}: {outcome}", identifier=name, request=request)


def adopt_dn(settings: LdapSettings, username: str, *, request: Any = None) -> dict[str, Any]:
    """An administrator confirms that the account of this name now belongs to the entry at its new place.

    For a user who was moved to another part of the directory (the DN changed): the login refuses the account,
    because it is linked to the old entry and a name alone is no proof. Here the link is moved to the entry the
    directory finds for the name – but only if the old entry is gone, and never for a local account or one with
    "has all rights".

    Raises:
        DirectoryError: The directory could not be asked.
        ValidationError: There is nothing to adopt, or it must not be done (the text says why).
        ValueError: The name is unusable.
    """
    name = ldap_client.normalise_username(username)
    config = DirectoryConfig.from_settings(settings)
    connection = ldap_client.open_service_connection(config)
    try:
        entry = ldap_client.find_user(config, connection, name)
        user, blocked = _find_account(entry, entry.first(config.attribute_username) or name) if entry else (None, "")
        old_exists = bool(user and user.ldap_dn and ldap_client.entry_exists(config, connection, user.ldap_dn))
    finally:
        ldap_client.close(connection)
    if entry is None:
        raise ValidationError(_("The directory knows no user “%(name)s”.") % {"name": name})
    if blocked != "moved" or user is None:
        raise ValidationError(_("The account of this user is not linked to another entry: there is nothing to adopt."))
    if old_exists:
        raise ValidationError(
            _("The old entry %(dn)s still exists in the directory. Remove or rename it there first.")
            % {"dn": user.ldap_dn}
        )
    old = user.ldap_dn
    with transaction.atomic():
        user.ldap_dn = entry.dn[:500]
        user.ldap_synced_at = timezone.now()
        user.save()
        record_event(user, "user.ldap_dn_adopted", {"old": old, "new": entry.dn})
        _audit(SecurityEventKind.LDAP_ACCOUNT, user, "entry adopted by an administrator", request=request)
    return {"account_id": user.pk, "username": user.username, "old_dn": old, "dn": entry.dn}


def warnings_for(settings: LdapSettings) -> list[str]:
    """What an administrator should see on the settings page and in the API about unsafe settings."""
    found = []
    plain = ldap_client.unencrypted_uris(settings.uris, settings.start_tls)
    if plain:
        found.append(
            _(
                "Not encrypted: passwords travel in the open to %(servers)s. Use ldaps:// or switch on StartTLS "
                "for ldap:// addresses."
            )
            % {"servers": ", ".join(plain)}
        )
    if not settings.verify_certificate:
        found.append(_("The certificate of the server is not checked: anybody can pose as the directory."))
    names = list(LdapGroupMapping.objects.filter(group_key__startswith="name:").values_list("group", flat=True))
    if names:
        found.append(
            _(
                "These assignments name the group only by its name and match a group of that name anywhere in the "
                "directory: %(groups)s. Use the full DN."
            )
            % {"groups": ", ".join(names[:5]) + (" …" if len(names) > 5 else "")}
        )
    if settings.link_existing_accounts:
        found.append(
            _(
                "Existing accounts are taken over by a user of the directory with the same name, together with the "
                "roles an administrator gave them. Only keep this on if nobody can choose a name freely."
            )
        )
    return found


# --- Comparison of all accounts -----------------------------------------------------------------------------


@dataclass
class SyncReport:
    """The result of a comparison of the accounts with the directory."""

    applied: bool
    plans: list[UserPlan] = field(default_factory=list)
    stopped: str = ""
    kept: int = 0

    @property
    def counts(self) -> dict[str, int]:
        """How many accounts per kind of action."""
        counts: dict[str, int] = {}
        for plan in self.plans:
            counts[plan.action] = counts.get(plan.action, 0) + 1
        return counts

    def as_document(self) -> dict[str, Any]:
        """Plain data for the page and the API."""
        return {
            "applied": self.applied,
            "stopped": self.stopped,
            "counts": self.counts,
            "accounts": [plan.as_document() for plan in self.plans if plan.action != "unchanged"],
        }

    def summary(self) -> str:
        """One line for the settings page."""
        parts = ", ".join(f"{count} {action}" for action, count in sorted(self.counts.items()))
        prefix = "" if self.applied else "(dry run) "
        return (prefix + (self.stopped or parts or "no accounts"))[:250]


def compare_accounts(settings: LdapSettings, *, apply: bool = False, force: bool = False) -> SyncReport:
    """Compare every account that belongs to the directory with it; with ``apply`` write the differences.

    Accounts are looked up by their username; one that is gone from the directory or in no group with a role
    is deactivated, the others get new names, address and roles. Nothing is created here. If more than half
    of the accounts would be deactivated, nothing is written unless ``force``.

    Raises:
        DirectoryError: The directory could not be asked – then nothing is changed.
    """
    config = DirectoryConfig.from_settings(settings)
    accounts = list(
        User.objects.exclude(ldap_dn="").filter(local_account=False, is_superuser=False).order_by("username")
    )
    report = SyncReport(applied=False)
    connection = ldap_client.open_service_connection(config)
    try:
        for user in accounts:
            entry = ldap_client.find_user(config, connection, user.username)
            if entry is None:
                plan = UserPlan(
                    action="deactivate" if user.is_active else "unchanged",
                    username=user.username,
                    dn=user.ldap_dn,
                    user=user,
                    reason="not_in_directory",
                    message=_("%(name)s is no longer in the directory.") % {"name": user.username},
                    roles_before=sorted(user.roles.values_list("name", flat=True)),
                )
            else:
                plan = plan_for(entry, ldap_client.groups_of(config, connection, entry), config, settings)
                plan.user = plan.user or user
            report.plans.append(plan)
    finally:
        ldap_client.close(connection)

    deactivations = sum(1 for plan in report.plans if plan.action == "deactivate")
    if deactivations > 3 and deactivations > len(accounts) * MAX_DEACTIVATION_SHARE and not force:
        report.stopped = _(
            "Stopped: %(count)s of %(total)s accounts would be deactivated. That looks like a wrong filter or a "
            "directory without answer. Check the settings, or run the comparison with --force."
        ) % {"count": deactivations, "total": len(accounts)}
        return report
    if apply:
        for plan in report.plans:
            if plan.action in {"deactivate", "reactivate", "update", "link"}:
                apply_plan(plan, config)
            elif plan.action == "refuse" and plan.user is not None:
                continue
        report.applied = True
        _record_sync(settings, report)
    return report


def _record_sync(settings: LdapSettings, report: SyncReport) -> None:
    """Note the result on the settings and in the security log."""
    summary = report.summary()
    LdapSettings.objects.filter(pk=settings.pk).update(last_sync_at=timezone.now(), last_sync_summary=summary)
    settings.last_sync_at = timezone.now()
    settings.last_sync_summary = summary
    _audit(SecurityEventKind.LDAP_SYNC, None, summary)


def sync_nightly() -> str:
    """The nightly comparison, if switched on (daily maintenance); returns a line for its output."""
    settings = LdapSettings.load()
    if not (settings.is_ready and settings.sync_daily):
        return "Directory (LDAP): not switched on for the nightly comparison."
    try:
        report = compare_accounts(settings, apply=True)
    except ldap_client.DirectoryError as error:
        _audit(SecurityEventKind.LDAP_ERROR, None, f"{error.code}: {error}"[:250])
        return f"Directory (LDAP): comparison failed ({error.code})."
    except Exception:  # Review R4: whatever goes wrong here must not stop the rest of the daily maintenance
        logger.exception("The nightly comparison with the directory failed.")
        with contextlib.suppress(Exception):
            _audit(SecurityEventKind.LDAP_ERROR, None, "comparison failed: unexpected error, see the log")
        return "Directory (LDAP): comparison failed (unexpected error, see the log)."
    return f"Directory (LDAP): {report.summary()}"
