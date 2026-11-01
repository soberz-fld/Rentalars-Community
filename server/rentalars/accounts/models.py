# SPDX-License-Identifier: GPL-3.0-or-later
"""Users, roles, API tokens and the record of login attempts (chapter 5.1)."""

from __future__ import annotations

import hashlib
import secrets
from typing import Any, ClassVar

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from rentalars.accounts.rights import Level, Module, ProjectScope, Rights, SpecialRight, rights_of
from rentalars.core.audit import AuditedModel
from rentalars.core.crypto import SecretUnreadableError, decrypt_secret, encrypt_secret
from rentalars.core.i18n import LANGUAGE_CHOICES
from rentalars.core.models import SingletonModel


class Role(AuditedModel):
    """A freely definable bundle of rights (AUT-010).

    ``module_levels`` maps a module to its access level, for example
    ``{"material": 3, "projects": 1}``. Modules that are missing mean "no
    access". ``special_rights`` is a list such as ``["prices"]``.

    The two fields are stored as JSON because the set of modules and special
    rights is defined in the code (``rights.py``), not in the database: a
    table per right would only repeat those constants.
    """

    name = models.CharField(_("name"), max_length=80, unique=True)
    description = models.CharField(_("description"), max_length=250, blank=True)
    module_levels = models.JSONField(_("module rights"), default=dict, blank=True)
    special_rights = models.JSONField(_("special rights"), default=list, blank=True)
    project_scope = models.CharField(
        _("project access"),
        max_length=10,
        choices=ProjectScope.choices,
        default=ProjectScope.ALL,
        help_text=_(
            "“Assigned projects only”: the rights on projects and packing lists hold only in projects the user is a "
            "member of or is scheduled for as crew. “Overview without planning”: there only the overview, the "
            "packing list and the chat."
        ),
    )
    requires_two_factor = models.BooleanField(
        _("two-factor login required"),
        default=False,
        help_text=_("Users with this role must set up a second factor before they can work."),
    )

    class Meta:
        verbose_name = _("role")
        verbose_name_plural = _("roles")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        """Reject unknown modules, levels and special rights."""
        super().clean()
        if not isinstance(self.module_levels, dict):
            raise ValidationError({"module_levels": _("Module rights must be a mapping of module to level.")})
        for module, level in self.module_levels.items():
            if module not in Module.values:
                raise ValidationError({"module_levels": _("Unknown module: %(module)s") % {"module": module}})
            if level not in Level.values:
                raise ValidationError({"module_levels": _("Unknown level: %(level)s") % {"level": level}})
        if not isinstance(self.special_rights, list):
            raise ValidationError({"special_rights": _("Special rights must be a list.")})
        for special_right in self.special_rights:
            if special_right not in SpecialRight.values:
                raise ValidationError(
                    {"special_rights": _("Unknown special right: %(right)s") % {"right": special_right}}
                )
        # Remove "no access" entries and duplicates so that equal roles look equal.
        self.module_levels = {
            module: int(level) for module, level in self.module_levels.items() if int(level) > Level.NONE
        }
        self.special_rights = sorted(set(self.special_rights))

    def level_of(self, module: str) -> int:
        """Return the level this role grants for a module."""
        return int(self.module_levels.get(module, Level.NONE))


class UserManager(BaseUserManager["User"]):
    """Creates users; needed by Django for the ``createsuperuser`` command."""

    use_in_migrations = True

    def create_user(self, username: str, email: str, password: str | None = None, **extra: Any) -> User:
        """Create a normal user. Without a password the account cannot log in yet."""
        if not username:
            raise ValueError("A user needs a username.")
        address = self.normalize_email(email or "").lower() or None
        user = self.model(username=username.strip(), email=address, **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def create_superuser(self, username: str, email: str, password: str | None = None, **extra: Any) -> User:
        """Create an account that has all rights regardless of roles."""
        extra["is_superuser"] = True
        return self.create_user(username, email, password, **extra)

    def get_by_natural_key(self, username: str | None) -> User:
        """Find a user by name, ignoring upper and lower case."""
        return self.get(username__iexact=username)


class User(AuditedModel, AbstractBaseUser):
    """A person who can log in (AUT-002, AUT-009).

    Every account is a person of the personnel, and every person has an
    account (AUT-026): saving a new account creates its person
    (``personnel.models.Person``), saving a new person creates its account.
    Names, e-mail address and "active" are kept the same on both. The
    account holds what concerns logging in – username, password, roles,
    second factor –, the person everything else.

    The class deliberately does not use Django's groups and model permissions.
    Rights come exclusively from :class:`Role` (see ``rights.py``). The three
    methods at the end translate role rights for Django's administration
    interface, which asks questions like "may this user change tax rates?".
    """

    username = models.CharField(
        _("username"),
        max_length=150,
        unique=True,
        validators=[UnicodeUsernameValidator()],
    )
    # Optional: somebody without an address logs in with a one-time password the
    # administration sets (AUT-027). Stored as NULL when empty, so that it stays unique.
    email = models.EmailField(_("e-mail address"), unique=True, null=True, blank=True)
    first_name = models.CharField(_("first name"), max_length=150, blank=True)
    last_name = models.CharField(_("last name"), max_length=150, blank=True)
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("Deactivated users cannot log in; their data and history are kept."),
    )
    is_superuser = models.BooleanField(
        _("has all rights"),
        default=False,
        help_text=_("Emergency access that does not depend on roles. Use sparingly."),
    )
    valid_until = models.DateField(
        _("valid until"),
        null=True,
        blank=True,
        help_text=_("For temporary staff: after this day the account is deactivated automatically. Empty: no limit."),
    )
    date_joined = models.DateTimeField(_("created"), default=timezone.now)
    roles = models.ManyToManyField(Role, verbose_name=_("roles"), blank=True, related_name="users")
    # UIX-029: the language of the interface, of mails and notifications to this user. Empty: the
    # installation's (``language`` in the configuration file).
    language = models.CharField(
        _("language"),
        max_length=5,
        blank=True,
        default="",
        # Also in the database: code written for an older state of the tables (migrations) creates users too.
        db_default="",
        choices=LANGUAGE_CHOICES,
        help_text=_("The language of the pages, mails and notifications for this user."),
    )
    must_change_password = models.BooleanField(
        _("must choose a new password"),
        default=False,
        editable=False,
        help_text=_("Set with a one-time password; the next login asks for a password of the user's own."),
    )

    # LDAP / Active Directory (AUT-029): which entry of the directory the account belongs to, when the
    # directory last confirmed it, whether the directory (and not an administrator) deactivated it, and the flag of
    # an emergency account that the directory never touches.
    ldap_dn = models.CharField(_("directory entry"), max_length=500, blank=True, default="", editable=False)
    ldap_synced_at = models.DateTimeField(_("last confirmed by the directory"), null=True, blank=True, editable=False)
    ldap_deactivated_at = models.DateTimeField(_("deactivated by the directory"), null=True, blank=True, editable=False)
    local_account = models.BooleanField(
        _("local (emergency) account"),
        default=False,
        help_text=_(
            "Logs in with its own password only, even when the directory (LDAP) is switched on; the directory never "
            "changes its roles or deactivates it. For the administrators who must get in when the directory is down."
        ),
    )

    # Two-factor login with an authenticator app (AUT-006). The key is stored
    # encrypted (core.crypto); the recovery codes only as hashes.
    totp_secret_encrypted = models.TextField(blank=True, editable=False)
    totp_enabled_at = models.DateTimeField(_("two-factor login since"), null=True, blank=True, editable=False)
    totp_last_step = models.BigIntegerField(default=0, editable=False)
    recovery_code_hashes = models.JSONField(default=list, blank=True, editable=False)

    objects = UserManager()

    USERNAME_FIELD = "username"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = ["email"]

    audit_exclude = frozenset(
        {
            "password",
            "last_login",
            "totp_secret_encrypted",
            "totp_last_step",
            "recovery_code_hashes",
            "ldap_synced_at",
        }
    )

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["last_name", "first_name", "username"]

    def __str__(self) -> str:
        return self.get_full_name() or self.username

    def clean(self) -> None:
        """Keep usernames and e-mail addresses unique regardless of case."""
        super().clean()
        self.email = (self.email or "").strip().lower() or None
        self.username = (self.username or "").strip()
        others = User.objects.exclude(pk=self.pk)
        if self.username and others.filter(username__iexact=self.username).exists():
            raise ValidationError({"username": _("This username is already taken.")})
        if self.email and others.filter(email__iexact=self.email).exists():
            raise ValidationError({"email": _("This e-mail address is already used by another user.")})

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save the account, and keep its person in step (AUT-026).

        Review, AUT-029: an account that is local (emergency) or has "all rights" is never kept by the
        directory – the link to its entry is cut here, wherever the flag was set (page, API, shell).
        """
        self.email = (self.email or "").strip().lower() or None
        unlink = bool(self.ldap_dn) and (self.local_account or self.is_superuser)
        if unlink:
            self.ldap_dn = ""
            self.ldap_synced_at = None
            self.ldap_deactivated_at = None
            fields = kwargs.get("update_fields")
            if fields is not None:
                kwargs["update_fields"] = {*fields, "ldap_dn", "ldap_synced_at", "ldap_deactivated_at"}
        super().save(*args, **kwargs)
        if unlink and self.pk:
            LdapRoleAssignment.objects.filter(user_id=self.pk).delete()
        if getattr(self, "_person_follows", False):
            # The person is being created right now and links itself (Person.save).
            self._person_follows = False
            return
        shared = {"first_name", "last_name", "email", "is_active"}
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            # Only what was saved is passed on. A login stores only ``last_login`` – nothing
            # the person shares –, and this instance may be older than a change made through the person.
            shared &= set(update_fields)
            if not shared:
                return
        from rentalars.personnel.models import Person

        person = Person.objects.filter(user_id=self.pk).first()
        if person is None:
            person = Person(user=self)
        wanted = {
            "first_name": self.first_name,
            "last_name": self.last_name or (person.last_name if person.pk else "") or self.username,
            "email": self.email or "",
            "is_active": self.is_active,
        }
        if person.pk:
            wanted = {name: value for name, value in wanted.items() if name in shared}
        if person.pk and person.anonymised_at:
            return
        if person.pk is None or any(getattr(person, name) != value for name, value in wanted.items()):
            for name, value in wanted.items():
                setattr(person, name, value)
            person._syncing_account = True
            person.save()

    def get_full_name(self) -> str:
        """First and last name, or an empty text if neither is set."""
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self) -> str:
        """The first name, falling back to the username."""
        return self.first_name or self.username

    @property
    def rights(self) -> Rights:
        """The effective rights of this user (see ``rights.rights_of``)."""
        return rights_of(self)

    @property
    def is_directory_account(self) -> bool:
        """Whether the directory (LDAP) keeps this account: it has an entry there and is no emergency account."""
        return bool(self.ldap_dn) and not self.local_account

    @property
    def has_two_factor(self) -> bool:
        """Whether the user logs in with a second factor (AUT-006)."""
        return self.totp_enabled_at is not None

    @property
    def needs_two_factor(self) -> bool:
        """Whether a role – or the setting for administrators – requires a second factor (AUT-006, NFA-049)."""
        from rentalars.accounts.twofactor import two_factor_required

        return two_factor_required(self)

    @property
    def has_expired(self) -> bool:
        """Whether the day until which the account is valid has passed (AUT-024)."""
        return self.valid_until is not None and self.valid_until < timezone.localdate()

    def deactivate_if_expired(self) -> bool:
        """Deactivate the account once its time is up (AUT-024); returns whether it is now inactive.

        Called wherever an account is about to be used – at login, with every
        request of a session, with every API token – and once a day for all
        accounts. So an expired account is closed even if the nightly job did
        not run, and the user list shows it as deactivated.
        """
        if self.is_active and self.has_expired:
            from rentalars.core.audit import acting_as, record_event

            with acting_as("system:expiry"):
                self.is_active = False
                self.save()
                record_event(self, "user.expired", {"valid_until": self.valid_until.isoformat()})
        return not self.is_active

    # --- Interface expected by Django's administration pages ---------------

    @property
    def is_staff(self) -> bool:
        """Only users with access to the Administration module may open the admin (ADM-007)."""
        return self.rights.can_read(Module.ADMINISTRATION)

    def has_perm(self, perm: str, obj: Any = None) -> bool:
        """Answer Django's model permission question from the role rights.

        Django asks with names like ``"masterdata.change_taxrate"``. The verb
        is mapped to the level of the Administration module: ``view`` needs
        read, ``add`` and ``change`` need write, ``delete`` needs delete.
        """
        codename = perm.split(".", 1)[-1]
        verb = codename.split("_", 1)[0]
        needed = {"view": Level.READ, "add": Level.WRITE, "change": Level.WRITE, "delete": Level.DELETE}
        return self.rights.has_level(Module.ADMINISTRATION, needed.get(verb, Level.DELETE))

    def has_perms(self, perm_list: Any, obj: Any = None) -> bool:
        """Whether all of the given Django permissions are granted."""
        return all(self.has_perm(perm, obj) for perm in perm_list)

    def has_module_perms(self, app_label: str) -> bool:
        """Whether the admin shows an app at all."""
        return self.is_staff


class ApiToken(models.Model):
    """A personal access key for integrations (AUT-021, API-006).

    Only a SHA-256 hash of the key is stored, so a copy of the database does
    not reveal usable keys. The plain key is shown exactly once, right after
    creation. ``key_prefix`` holds its first characters so that users can
    tell their tokens apart.

    A token never has more rights than its user. It can be narrowed to
    read-only access or to certain modules.
    """

    KEY_PREFIX = "rl_"

    user = models.ForeignKey(User, verbose_name=_("user"), on_delete=models.CASCADE, related_name="api_tokens")
    name = models.CharField(_("name"), max_length=80, help_text=_("What the token is used for."))
    key_prefix = models.CharField(_("beginning of the key"), max_length=12)
    key_hash = models.CharField(max_length=64, unique=True)
    read_only = models.BooleanField(_("read-only"), default=False)
    allowed_modules = models.JSONField(
        _("limited to modules"),
        default=list,
        blank=True,
        help_text=_("Empty means: all modules the user may access."),
    )
    created_at = models.DateTimeField(_("created"), default=timezone.now)
    expires_at = models.DateTimeField(_("valid until"), null=True, blank=True)
    last_used_at = models.DateTimeField(_("last used"), null=True, blank=True)
    revoked_at = models.DateTimeField(_("revoked"), null=True, blank=True)

    class Meta:
        verbose_name = _("API token")
        verbose_name_plural = _("API tokens")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.key_prefix}…)"

    @staticmethod
    def hash_key(plain_key: str) -> str:
        """Return the stored form of a key."""
        return hashlib.sha256(plain_key.encode("utf-8")).hexdigest()

    @classmethod
    def create_for_user(
        cls,
        user: User,
        name: str,
        *,
        read_only: bool = False,
        allowed_modules: list[str] | None = None,
        expires_at: Any = None,
    ) -> tuple[ApiToken, str]:
        """Create a token and return it together with its plain key.

        The plain key cannot be recovered later; the caller must show it to
        the user immediately.
        """
        plain_key = cls.KEY_PREFIX + secrets.token_urlsafe(32)
        modules = [module for module in (allowed_modules or []) if module in Module.values]
        token = cls.objects.create(
            user=user,
            name=name,
            key_prefix=plain_key[:10],
            key_hash=cls.hash_key(plain_key),
            read_only=read_only,
            allowed_modules=modules,
            expires_at=expires_at,
        )
        return token, plain_key

    @property
    def is_usable(self) -> bool:
        """Whether the token may still be used: not revoked, not expired, user active."""
        if self.revoked_at is not None or self.user.deactivate_if_expired():
            return False
        return self.expires_at is None or self.expires_at > timezone.now()

    def revoke(self) -> None:
        """Make the token unusable from now on."""
        if self.revoked_at is None:
            self.revoked_at = timezone.now()
            self.save(update_fields=["revoked_at"])

    def restrict(self, rights: Rights) -> Rights:
        """Narrow the rights of the user to what this token allows."""
        return rights.restricted(read_only=self.read_only, allowed_modules=self.allowed_modules)


class LoginAttempt(models.Model):
    """One login attempt, kept to slow down password guessing (AUT-005).

    ``identifier`` is what was typed into the name field, in lower case. Old
    rows are removed by the daily maintenance command.
    """

    identifier = models.CharField(max_length=254, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    successful = models.BooleanField(default=False)

    class Meta:
        verbose_name = _("login attempt")
        verbose_name_plural = _("login attempts")
        ordering = ["-timestamp"]

    def __str__(self) -> str:
        outcome = "ok" if self.successful else "failed"
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.identifier} {outcome}"


class UserSession(models.Model):
    """A login of a user in a browser, so that it can be shown and ended (AUT-008).

    Django keeps the session itself; this row adds who it belongs to, from
    where it came and when it was last used.
    """

    user = models.ForeignKey(User, verbose_name=_("user"), on_delete=models.CASCADE, related_name="browser_sessions")
    session_key = models.CharField(max_length=40, unique=True)
    created_at = models.DateTimeField(_("logged in"), default=timezone.now)
    last_activity = models.DateTimeField(_("last active"), default=timezone.now)
    ip_address = models.GenericIPAddressField(_("IP address"), null=True, blank=True)
    user_agent = models.CharField(_("browser"), max_length=300, blank=True)

    class Meta:
        verbose_name = _("session")
        verbose_name_plural = _("sessions")
        ordering = ["-last_activity"]

    def __str__(self) -> str:
        return f"{self.user} {self.created_at:%Y-%m-%d %H:%M}"


class SecurityEventKind(models.TextChoices):
    """What the security log records (AUT-022)."""

    LOGIN = "login", _("logged in")
    LOGIN_FAILED = "login_failed", _("login failed")
    LOGOUT = "logout", _("logged out")
    TIMEOUT = "timeout", _("logged out after inactivity")
    SECOND_FACTOR_FAILED = "2fa_failed", _("wrong second factor")
    SECOND_FACTOR_ENABLED = "2fa_enabled", _("two-factor login set up")
    SECOND_FACTOR_DISABLED = "2fa_disabled", _("two-factor login switched off")
    RECOVERY_CODE_USED = "recovery_code", _("recovery code used")
    SESSION_ENDED = "session_ended", _("session ended")
    PASSWORD_CHANGED = "password_changed", _("password changed")
    ONE_TIME_PASSWORD = "one_time_password", _("one-time password set")
    # AUT-029 (LDAP): what the directory login does besides the normal login entries.
    LDAP_REFUSED = "ldap_refused", _("directory login refused")
    LDAP_ERROR = "ldap_error", _("directory not reachable")
    LDAP_ACCOUNT = "ldap_account", _("account created or changed by the directory")
    LDAP_ROLES = "ldap_roles", _("roles changed by the directory")
    LDAP_SYNC = "ldap_sync", _("accounts compared with the directory")
    LDAP_TEST = "ldap_test", _("directory login tried by an administrator")


class SecurityEvent(models.Model):
    """One entry of the security log: logins, failed logins, second factor, sessions (AUT-022).

    Changes to users, roles and rights are in the change log (``AuditLogEntry``);
    the page of the security log shows both together.
    """

    kind = models.CharField(_("event"), max_length=20, choices=SecurityEventKind.choices)
    user = models.ForeignKey(
        User, verbose_name=_("user"), null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    identifier = models.CharField(_("entered name"), max_length=254, blank=True)
    ip_address = models.GenericIPAddressField(_("IP address"), null=True, blank=True)
    user_agent = models.CharField(_("browser"), max_length=300, blank=True)
    detail = models.CharField(_("detail"), max_length=250, blank=True)
    timestamp = models.DateTimeField(_("time"), default=timezone.now, db_index=True)

    class Meta:
        verbose_name = _("security event")
        verbose_name_plural = _("security log")
        ordering = ["-timestamp", "-id"]

    def __str__(self) -> str:
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.kind}"


# --- Login with LDAP / Active Directory (AUT-029) -------------------------------------------------------


def has_local_administrator() -> bool:
    """Whether an active local (emergency) account with a password can still change the settings (AUT-029)."""
    for user in User.objects.filter(is_active=True, local_account=True).prefetch_related("roles"):
        if user.has_usable_password() and not user.has_expired and user.rights.can_write(Module.ADMINISTRATION):
            return True
    return False


class GroupMode(models.TextChoices):
    """How the groups of a user are found in the directory (AUT-029)."""

    MEMBER_OF = "member_of", _("Attribute of the user (memberOf)")
    SEARCH = "search", _("Search in the groups")


class LdapSettings(SingletonModel):
    """How Rentalars reaches the directory and finds users and their groups (AUT-029).

    One row. The directory is off until an administrator switches it on.
    The password of the search account is stored encrypted like the mailbox
    passwords (``core.crypto``) and is never shown again. Users are found
    with a filter template in which ``{username}`` is replaced by the typed
    name – escaped, so that nobody can change the filter with it.
    """

    enabled = models.BooleanField(
        _("log in with the directory"),
        default=False,
        help_text=_("Off: only accounts with a password of Rentalars can log in, as before."),
    )
    server_uris = models.TextField(
        _("servers"),
        blank=True,
        help_text=_(
            "One address per line, e.g. ldaps://dc1.example.com or ldap://ldap.example.com:389. Several servers are "
            "tried one after the other."
        ),
    )
    start_tls = models.BooleanField(
        _("encrypt with StartTLS"),
        default=False,
        help_text=_("For addresses with ldap://: switch to an encrypted connection before any password is sent."),
    )
    verify_certificate = models.BooleanField(
        _("check the certificate of the server"),
        default=True,
        help_text=_("Switch this off only for a test: without the check anybody can pose as the server."),
    )
    ca_certificate_path = models.CharField(
        _("file with the CA certificate"),
        max_length=255,
        blank=True,
        help_text=_("Path on the server, e.g. /etc/ssl/certs/company-ca.pem. Empty: the certificates of the system."),
    )
    ca_certificate_pem = models.TextField(
        _("CA certificate (pasted)"),
        blank=True,
        help_text=_("Alternatively paste the certificate of your own certificate authority here (PEM)."),
    )
    timeout_seconds = models.PositiveSmallIntegerField(
        _("timeout in seconds"),
        default=8,
        validators=[MinValueValidator(1), MaxValueValidator(60)],
        help_text=_("How long Rentalars waits for the directory before it gives up."),
    )
    bind_dn = models.CharField(
        _("search account (DN)"),
        max_length=500,
        blank=True,
        help_text=_(
            "The account that looks up users and groups, e.g. cn=rentalars,ou=service,dc=example,dc=com. Empty: "
            "search without logging in (anonymous)."
        ),
    )
    bind_password_encrypted = models.TextField(_("password of the search account"), blank=True, editable=False)
    user_search_base = models.CharField(
        _("search base for users"),
        max_length=500,
        blank=True,
        help_text=_("Where users are searched, e.g. ou=people,dc=example,dc=com."),
    )
    user_search_filter = models.CharField(
        _("filter for users"),
        max_length=500,
        default="(&(objectClass=person)(sAMAccountName={username}))",
        help_text=_(
            "{username} stands for the typed name. OpenLDAP: (&(objectClass=inetOrgPerson)(uid={username})). "
            "Active Directory: (&(objectClass=person)(sAMAccountName={username}))."
        ),
    )
    attribute_username = models.CharField(
        _("attribute: username"), max_length=60, default="sAMAccountName", help_text=_("OpenLDAP: uid.")
    )
    attribute_email = models.CharField(_("attribute: e-mail address"), max_length=60, default="mail")
    attribute_first_name = models.CharField(_("attribute: first name"), max_length=60, default="givenName")
    attribute_last_name = models.CharField(_("attribute: last name"), max_length=60, default="sn")
    group_mode = models.CharField(
        _("find the groups"), max_length=10, choices=GroupMode.choices, default=GroupMode.MEMBER_OF
    )
    member_of_attribute = models.CharField(
        _("attribute with the groups"),
        max_length=60,
        default="memberOf",
        help_text=_("Active Directory and OpenLDAP with the memberOf overlay: memberOf."),
    )
    group_search_base = models.CharField(
        _("search base for groups"),
        max_length=500,
        blank=True,
        help_text=_("Where groups are searched, e.g. ou=groups,dc=example,dc=com."),
    )
    group_search_filter = models.CharField(
        _("filter for groups"),
        max_length=500,
        default="(&(objectClass=groupOfNames)(member={user_dn}))",
        help_text=_(
            "{user_dn} stands for the DN of the user, {username} for the name. OpenLDAP with posixGroup: "
            "(&(objectClass=posixGroup)(memberUid={username}))."
        ),
    )
    allow_local_login = models.BooleanField(
        _("allow login with a local password"),
        default=True,
        help_text=_(
            "On: accounts with a password of Rentalars can still log in with it. Off: only local (emergency) "
            "accounts can; everybody else logs in with the directory."
        ),
    )
    auto_create_users = models.BooleanField(
        _("create accounts at the first login"),
        default=True,
        help_text=_(
            "A user of the directory who has no account yet gets one at the first login – but only if one of the "
            "groups has a role in the table below. Off: only accounts that exist already can log in."
        ),
    )
    link_existing_accounts = models.BooleanField(
        _("link existing accounts by name"),
        default=False,
        help_text=_(
            "Off (safe): a user of the directory whose name equals an existing account of Rentalars that is not "
            "linked yet is refused – an administrator decides. On: such an account is taken over at the first login "
            "and keeps the roles an administrator gave it. Switch this on only if the names of the directory are "
            "trustworthy and nobody can choose a name freely."
        ),
    )
    sync_daily = models.BooleanField(
        _("compare the accounts every night"),
        default=False,
        help_text=_(
            "Every night, roles and names are brought up to date and users who left their groups are deactivated – "
            "without waiting for their next login."
        ),
    )
    last_sync_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_sync_summary = models.CharField(max_length=250, blank=True, editable=False)

    audit_exclude = frozenset({"bind_password_encrypted", "last_sync_at", "last_sync_summary"})

    class Meta:
        verbose_name = _("directory settings")
        verbose_name_plural = _("directory settings")

    def __str__(self) -> str:
        return str(_("Directory settings (LDAP)"))

    @classmethod
    def current(cls) -> LdapSettings:
        """The settings, or the defaults when nothing was saved yet – without writing a row (used at every login)."""
        return cls.objects.filter(pk=1).first() or cls(pk=1)

    # The password is written and read only through these two members.
    def set_bind_password(self, password: str) -> None:
        """Store the password of the search account encrypted."""
        self.bind_password_encrypted = encrypt_secret(password)

    @property
    def bind_password(self) -> str:
        """The password of the search account in clear text; empty if none is stored.

        Raises:
            SecretUnreadableError: It was stored with another ``secret_key``.
        """
        return decrypt_secret(self.bind_password_encrypted)

    @property
    def has_bind_password(self) -> bool:
        """Whether a password is stored (it is never shown again)."""
        return bool(self.bind_password_encrypted)

    @property
    def bind_password_readable(self) -> bool:
        """Whether the stored password can still be decrypted (``secret_key`` unchanged)."""
        try:
            self.bind_password  # noqa: B018 - decrypting is the check
        except SecretUnreadableError:
            return False
        return True

    @property
    def uris(self) -> list[str]:
        """The server addresses, one per line, without empty lines."""
        return [line.strip() for line in self.server_uris.splitlines() if line.strip()]

    @property
    def is_ready(self) -> bool:
        """Whether the directory is switched on and set up so far that a login can be tried."""
        return bool(self.enabled and self.uris and self.user_search_base and self.user_search_filter)

    def clean(self) -> None:
        """Check addresses and filters; a switched-on directory needs the minimum to work (AUT-029)."""
        from rentalars.accounts import ldap_client

        super().clean()
        errors: dict[str, Any] = {}
        for field_name, check in (
            ("server_uris", lambda: ldap_client.validate_server_uris(self.server_uris)),
            ("user_search_filter", lambda: ldap_client.validate_filter(self.user_search_filter, {"{username}"})),
            ("group_search_filter", lambda: ldap_client.validate_group_filter(self.group_search_filter)),
            ("ca_certificate_pem", lambda: ldap_client.validate_pem(self.ca_certificate_pem)),
            ("ca_certificate_path", lambda: ldap_client.validate_ca_path(self.ca_certificate_path)),
        ):
            try:
                check()
            except ValidationError as error:
                errors[field_name] = error.messages
        if self.enabled:
            if not self.uris:
                errors.setdefault("server_uris", _("Enter at least one server."))
            if not self.user_search_base.strip():
                errors["user_search_base"] = _("Enter where users are searched.")
            if not self.attribute_username.strip():
                errors["attribute_username"] = _("Enter the attribute that holds the username.")
            if self.group_mode == GroupMode.SEARCH and not self.group_search_base.strip():
                errors["group_search_base"] = _("Enter where groups are searched.")
            if self.group_mode == GroupMode.MEMBER_OF and not self.member_of_attribute.strip():
                errors["member_of_attribute"] = _("Enter the attribute that holds the groups.")
            if not self.allow_local_login and not has_local_administrator():
                errors["allow_local_login"] = _(
                    "Before local passwords are switched off, an active local (emergency) account with a password of "
                    "its own and the right to change the settings must exist – otherwise nobody could log in when "
                    "the directory is down."
                )
        if errors:
            raise ValidationError(errors)


class LdapGroupMapping(AuditedModel):
    """A group of the directory and the roles its members get (AUT-029).

    ``group`` is the DN of the group (``cn=admins,ou=groups,dc=example,dc=com``)
    or only its name (``admins``, matched against the first part of the DN of
    every group the user is in), without regard to case. A user gets the
    roles of **all** mappings whose group they are in (union). The order is
    given by the priority (the lowest number first): a mapping with "last
    match" stops here – mappings after it do not apply.
    """

    group = models.CharField(
        pgettext_lazy("directory", "group"),
        max_length=480,  # the comparable key adds "dn:" or "name:" and must stay within its 500 characters
        help_text=_(
            "The full DN of the group, e.g. cn=admins,ou=groups,dc=example,dc=com. A bare name (admins) is "
            "accepted but matches a group of that name anywhere in the directory – use it only if you must."
        ),
    )
    group_key = models.CharField(max_length=500, unique=True, editable=False)
    roles = models.ManyToManyField(Role, verbose_name=_("roles"), related_name="ldap_mappings")
    priority = models.PositiveSmallIntegerField(
        _("priority"),
        default=100,
        help_text=_("The lowest number is applied first. Only matters together with “last match”."),
    )
    last_match = models.BooleanField(
        _("last match"),
        default=False,
        help_text=_("If a user is in this group, mappings with a higher number do not apply to that user."),
    )
    note = models.CharField(_("note"), max_length=250, blank=True)

    audit_exclude = frozenset({"group_key"})

    class Meta:
        verbose_name = _("group assignment")
        verbose_name_plural = _("group assignments")
        ordering = ["priority", "group"]

    def __str__(self) -> str:
        return self.group

    @property
    def is_name_only(self) -> bool:
        """Whether only the name of the group is given: it then matches a group of that name in any place."""
        return self.group_key.startswith("name:")

    def clean(self) -> None:
        """Normalise the group and keep it unique regardless of case and spacing."""
        from rentalars.accounts import ldap_client

        super().clean()
        self.group = (self.group or "").strip()
        if not self.group:
            raise ValidationError({"group": _("Enter the group.")})
        self.group_key = ldap_client.group_key(self.group)
        self.check_key_length()
        if LdapGroupMapping.objects.exclude(pk=self.pk).filter(group_key=self.group_key).exists():
            raise ValidationError({"group": _("This group already has an assignment.")})

    def check_key_length(self) -> None:
        """The comparable form (case folded, with its prefix) must fit its column of 500 characters (review R4)."""
        if len(self.group_key) > 500:
            raise ValidationError({"group": _("This group is too long: at most 480 characters.")})

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Keep the comparable form of the group in step."""
        from rentalars.accounts import ldap_client

        self.group = (self.group or "").strip()
        self.group_key = ldap_client.group_key(self.group)
        self.check_key_length()
        super().save(*args, **kwargs)


class LdapRoleAssignment(models.Model):
    """A role that the directory gave a user – it cannot be taken away by hand (AUT-029).

    The role is in ``User.roles`` as well, so that the rights work as ever;
    this row only says who put it there. ``also_manual``: an administrator
    had given the same role before – then it stays when the directory no
    longer grants it.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ldap_role_assignments")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="+")
    also_manual = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "role"], name="ldap_role_once_per_user")]

    def __str__(self) -> str:
        return f"{self.user_id}: {self.role_id}"
