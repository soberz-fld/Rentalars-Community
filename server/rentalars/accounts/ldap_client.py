# SPDX-License-Identifier: GPL-3.0-or-later
"""Talking to a directory (LDAP, Active Directory) with ``ldap3`` (AUT-029).

Everything that touches the network or the library lives here, so that the rest of Rentalars
(``ldap_sync``, the backend, the pages and the API) speaks only about :class:`DirectoryEntry`
and :class:`DirectoryError`.

Rules kept here:

* The typed name never becomes part of a filter unescaped (``fill_template`` escapes with
  ``ldap3.utils.conv.escape_filter_chars``; the placeholders are replaced in one pass, so a name that
  looks like a placeholder is not replaced a second time).
* An empty password never reaches the directory: many servers accept a bind with a name and no
  password as an anonymous one – and "log in" the user.
* The servers an administrator typed are connected to at an address that passed the network guard
  (NFA-071, ``core.network``), exactly like mail servers and calendars; the certificate is checked
  against the typed name.
* Passwords are never logged and never part of an error text.
* One *connection factory* creates every connection. Tests replace it by one that returns
  ``ldap3`` connections with the ``MOCK_SYNC`` strategy (``tests/ldap_fake.py``): search, filter,
  bind and result handling then run through the real code.
"""

from __future__ import annotations

import contextlib
import re
import ssl
import unicodedata
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

if TYPE_CHECKING:
    from ldap3 import Connection

    from rentalars.accounts.models import LdapSettings

#: Longest name accepted at the login (the rest is cut off before it reaches a filter).
MAX_USERNAME_LENGTH = 256

#: The placeholders a filter template may contain.
PLACEHOLDER = re.compile(r"\{(username|user_dn)\}")

#: Schemes of a server address.
SCHEMES = ("ldap", "ldaps")


class DirectoryError(Exception):
    """The directory could not be asked, or it answered something unusable.

    ``str(error)`` is for administrators (it may name servers and attributes); the pages show
    users only a general text. ``code`` is stable for tests and the API:
    ``not_configured``, ``blocked``, ``unreachable``, ``tls``, ``service_bind``, ``search``,
    ``ambiguous``, ``entry``.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# --- Names, filters, groups ---------------------------------------------------------------------------------


def normalise_username(value: str) -> str:
    """Bring a typed name into one form: Unicode NFC, without surrounding blanks.

    Raises:
        ValueError: The name is empty, too long or holds control characters.
    """
    text = unicodedata.normalize("NFC", str(value or "")).strip()
    if not text or len(text) > MAX_USERNAME_LENGTH or any(unicodedata.category(c).startswith("C") for c in text):
        raise ValueError("unusable name")
    return text


def escape_value(value: str) -> str:
    """Escape a value for a search filter (RFC 4515): asterisk, brackets, backslash and NUL."""
    from ldap3.utils.conv import escape_filter_chars

    return str(escape_filter_chars(value))


def fill_template(template: str, **values: str) -> str:
    """Replace ``{username}`` and ``{user_dn}`` of a filter template by escaped values, in one pass."""

    def replace(match: re.Match[str]) -> str:
        return escape_value(values.get(match.group(1), ""))

    return PLACEHOLDER.sub(replace, template)


def validate_filter(template: str, required: set[str]) -> None:
    """Check a filter template: balanced and well-formed, and holding the placeholders it needs.

    Raises:
        ValidationError: The filter cannot be used.
    """
    from ldap3.operation.search import parse_filter

    text = (template or "").strip()
    if not text:
        raise ValidationError(_("Enter a filter."))
    for placeholder in required:
        if placeholder not in text:
            raise ValidationError(_("The filter must contain %(placeholder)s.") % {"placeholder": placeholder})
    if "{" in PLACEHOLDER.sub("", text) or "}" in PLACEHOLDER.sub("", text):
        raise ValidationError(_("Only {username} and {user_dn} may be used in braces."))
    try:
        parse_filter(PLACEHOLDER.sub("x", text), None, False, False, None, False)
    except Exception as error:  # the library raises several kinds for a broken filter
        raise ValidationError(_("This is not a valid LDAP filter, e.g. a bracket is missing.")) from error


def validate_group_filter(template: str) -> None:
    """The filter that finds the groups of a user: it must name the user by ``{user_dn}`` or ``{username}``."""
    text = (template or "").strip()
    if not text:
        return  # only needed while the groups are searched; the model checks that
    if "{user_dn}" not in text and "{username}" not in text:
        raise ValidationError(_("The filter must contain {user_dn} or {username}."))
    validate_filter(text, set())


def validate_pem(text: str) -> None:
    """A pasted CA certificate must be PEM and loadable."""
    if not (text or "").strip():
        return
    try:
        ssl.create_default_context().load_verify_locations(cadata=text)
    except (ssl.SSLError, ValueError, TypeError, UnicodeError) as error:  # TypeError: not ASCII (review R4)
        raise ValidationError(
            _("This is not a certificate in PEM format (-----BEGIN CERTIFICATE----- … -----END CERTIFICATE-----).")
        ) from error


def validate_ca_path(path: str) -> None:
    """The path of a CA file must name a readable regular file with certificates (admin-only setting).

    The texts do not say more than needed: nothing of the file's content, no hint about other paths.

    Raises:
        ValidationError: The path is not usable.
    """
    import os
    import stat

    text = (path or "").strip()
    if not text:
        return
    if not os.path.isabs(text) or "\x00" in text:
        raise ValidationError(_("Enter the absolute path of the file, e.g. /etc/ssl/certs/company-ca.pem."))
    try:
        mode = os.stat(text).st_mode
    except OSError as error:
        raise ValidationError(_("There is no such file on the server.")) from error
    if not stat.S_ISREG(mode) or not os.access(text, os.R_OK):
        raise ValidationError(_("This is not a file that Rentalars can read."))
    try:
        ssl.create_default_context().load_verify_locations(cafile=text)
    except (ssl.SSLError, OSError, ValueError) as error:
        raise ValidationError(_("The file holds no certificate in PEM format.")) from error


def unencrypted_uris(uris: Iterable[str], start_tls: bool) -> list[str]:
    """The addresses over which passwords would travel in the open: ``ldap://`` without StartTLS."""
    if start_tls:
        return []
    plain = []
    for uri in uris:
        try:
            if not parse_uri(uri)[2]:
                plain.append(uri.strip())
        except ValueError:
            continue
    return plain


def validate_server_uris(text: str) -> None:
    """Every line is ``ldap://host[:port]`` or ``ldaps://host[:port]``; an internal address needs the operator's leave."""
    from rentalars.core import network

    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            host, _port, _ssl = parse_uri(line)
            network.check_entered_host(host)
        except network.BlockedAddressError as error:
            raise ValidationError(str(error)) from error
        except ValueError as error:
            raise ValidationError(
                _("“%(address)s” is not an address like ldaps://dc1.example.com or ldap://ldap.example.com:389.")
                % {"address": line[:80]}
            ) from error


def parse_uri(uri: str) -> tuple[str, int, bool]:
    """Host, port and whether the connection is encrypted from the start (ldaps) – for one address.

    Raises:
        ValueError: The address is not usable.
    """
    parts = urlsplit(uri.strip())
    scheme = parts.scheme.lower()
    if scheme not in SCHEMES or not parts.hostname or parts.path not in ("", "/") or parts.query or parts.username:
        raise ValueError(uri)
    use_ssl = scheme == "ldaps"
    port = parts.port or (636 if use_ssl else 389)
    return parts.hostname, port, use_ssl


def _unescape_rdn(value: str) -> str:
    r"""The value of a DN part without its escapes (``\\,`` and ``\\2c`` both become a comma)."""
    return re.sub(
        r"\\([0-9a-fA-F]{2}|.)", lambda m: chr(int(m.group(1), 16)) if len(m.group(1)) == 2 else m.group(1), value
    )


def _split_unescaped(text: str, separator: str) -> list[str]:
    parts, current, escaped = [], [], False
    for character in text:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            current.append(character)
            escaped = True
        elif character == separator:
            parts.append("".join(current))
            current = []
        else:
            current.append(character)
    parts.append("".join(current))
    return parts


def _fold(value: str) -> str:
    """Case, Unicode form and runs of blanks do not matter in names of the directory."""
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def dn_parts(dn: str) -> list[tuple[str, str]]:
    """A DN as ``[(type, value), …]`` in comparable form: lower case, NFC, blanks collapsed, escapes resolved.

    Multi-valued parts (``cn=a+uid=b``) are kept as one part per value. A text that is no DN gives ``[]``.
    """
    parts = []
    for rdn in _split_unescaped(unicodedata.normalize("NFC", dn or ""), ","):
        for pair in _split_unescaped(rdn, "+"):
            if "=" not in pair:
                return []
            kind, _equals, value = pair.partition("=")
            if not kind.strip():
                return []
            parts.append((_fold(kind), _fold(_unescape_rdn(value.strip()))))
    return parts


def dn_key(dn: str) -> str:
    """The comparable form of a DN as one text; two spellings of the same DN give the same key."""
    return ",".join(f"{kind}={value}" for kind, value in dn_parts(dn))


def group_key(group: str) -> str:
    """The comparable form of what an administrator typed as "group": a DN, or only the name of the group.

    A DN (several parts) keeps its form as ``dn:…``. A name – ``admins`` or ``cn=admins`` – becomes
    ``name:admins`` and matches the first part of the DN of any group.
    """
    text = (group or "").strip()
    parts = dn_parts(text)
    if len(parts) >= 2:
        return "dn:" + dn_key(text)
    if len(parts) == 1:
        return "name:" + parts[0][1]
    return "name:" + _fold(text)


def group_matches(wanted_key: str, group_dn: str) -> bool:
    """Whether a group DN of the directory is the group an administrator named (by DN or by name)."""
    parts = dn_parts(group_dn)
    if wanted_key.startswith("dn:"):
        return wanted_key == "dn:" + dn_key(group_dn)
    if parts:
        return wanted_key == "name:" + parts[0][1]
    return wanted_key == "name:" + _fold(group_dn)


# --- Entries -------------------------------------------------------------------------------------------------


@dataclass
class DirectoryEntry:
    """A user found in the directory: the DN and the attributes asked for (names in lower case)."""

    dn: str
    attributes: dict[str, list[str]] = field(default_factory=dict)

    def first(self, attribute: str) -> str:
        """The first value of an attribute, NFC-normalised and stripped; empty if there is none."""
        values = self.attributes.get((attribute or "").lower(), [])
        return unicodedata.normalize("NFC", str(values[0])).strip() if values else ""

    def values(self, attribute: str) -> list[str]:
        """All values of an attribute as text."""
        return [str(value) for value in self.attributes.get((attribute or "").lower(), [])]


@dataclass(frozen=True)
class DirectoryConfig:
    """A snapshot of :class:`~rentalars.accounts.models.LdapSettings` for one run, password included."""

    uris: tuple[str, ...]
    start_tls: bool
    verify_certificate: bool
    ca_certificate_path: str
    ca_certificate_pem: str
    timeout_seconds: int
    bind_dn: str
    bind_password: str
    user_search_base: str
    user_search_filter: str
    attribute_username: str
    attribute_email: str
    attribute_first_name: str
    attribute_last_name: str
    group_mode: str
    member_of_attribute: str
    group_search_base: str
    group_search_filter: str

    @classmethod
    def from_settings(cls, settings: LdapSettings) -> DirectoryConfig:
        """Take the values of the settings; the stored password is decrypted here.

        Raises:
            DirectoryError: The password cannot be decrypted (``secret_key`` changed).
        """
        from rentalars.core.crypto import SecretUnreadableError

        try:
            password = settings.bind_password
        except SecretUnreadableError as error:
            raise DirectoryError(
                "service_bind",
                _(
                    "The password of the search account cannot be read any more (the secret key was changed). Enter it again."
                ),
            ) from error
        return cls(
            uris=tuple(settings.uris),
            start_tls=settings.start_tls,
            verify_certificate=settings.verify_certificate,
            ca_certificate_path=settings.ca_certificate_path.strip(),
            ca_certificate_pem=settings.ca_certificate_pem.strip(),
            timeout_seconds=settings.timeout_seconds,
            bind_dn=settings.bind_dn.strip(),
            bind_password=password,
            user_search_base=settings.user_search_base.strip(),
            user_search_filter=settings.user_search_filter.strip(),
            attribute_username=settings.attribute_username.strip(),
            attribute_email=settings.attribute_email.strip(),
            attribute_first_name=settings.attribute_first_name.strip(),
            attribute_last_name=settings.attribute_last_name.strip(),
            group_mode=settings.group_mode,
            member_of_attribute=settings.member_of_attribute.strip(),
            group_search_base=settings.group_search_base.strip(),
            group_search_filter=settings.group_search_filter.strip(),
        )

    @property
    def user_attributes(self) -> list[str]:
        """The attributes read from a user entry."""
        wanted = [self.attribute_username, self.attribute_email, self.attribute_first_name, self.attribute_last_name]
        if self.group_mode == "member_of":
            wanted.append(self.member_of_attribute)
        return sorted({name for name in wanted if name})


# --- The connection factory ------------------------------------------------------------------------------------

#: ``factory(config, bind_dn, password) -> Connection`` – an unbound connection. Tests set another one.
ConnectionFactory = Callable[[DirectoryConfig, str, str], "Connection"]


def _real_factory(config: DirectoryConfig, bind_dn: str, password: str) -> Connection:
    """The real connection: checked addresses, TLS as set, a pool when there are several servers."""
    import ldap3

    from rentalars.core import network

    tls = None
    if any(parse_uri(uri)[2] for uri in config.uris) or config.start_tls:
        tls = ldap3.Tls(
            validate=ssl.CERT_REQUIRED if config.verify_certificate else ssl.CERT_NONE,
            ca_certs_file=config.ca_certificate_path or None,
            ca_certs_data=config.ca_certificate_pem or None,
        )
    servers = []
    for uri in config.uris:
        host, port, use_ssl = parse_uri(uri)
        try:
            answers = network.checked_addresses(host, port)
        except network.BlockedAddressError as error:
            raise DirectoryError("blocked", f"{host}: {error}") from error
        except OSError as error:
            raise DirectoryError(
                "unreachable", _("The server %(host)s is not known: %(error)s") % {"host": host, "error": error}
            ) from error
        for answer in answers[:2]:
            address = str(answer[4][0])
            server_tls = None
            if tls is not None:
                server_tls = ldap3.Tls(
                    validate=tls.validate,
                    ca_certs_file=tls.ca_certs_file,
                    ca_certs_data=tls.ca_certs_data,
                    valid_names=[host],
                    sni=host,
                )
            servers.append(
                ldap3.Server(
                    address,
                    port=port,
                    use_ssl=use_ssl,
                    tls=server_tls,
                    get_info=ldap3.NONE,
                    connect_timeout=config.timeout_seconds,
                )
            )
    if not servers:
        raise DirectoryError("not_configured", _("No server is set."))
    target: Any = servers[0] if len(servers) == 1 else ldap3.ServerPool(servers, ldap3.FIRST, active=True, exhaust=True)
    return ldap3.Connection(
        target,
        user=bind_dn or None,
        password=password or None,
        authentication=ldap3.SIMPLE if bind_dn else ldap3.ANONYMOUS,
        receive_timeout=config.timeout_seconds,
        auto_referrals=False,
        raise_exceptions=False,
        read_only=True,
    )


_factory: ConnectionFactory = _real_factory


@contextlib.contextmanager
def using_factory(factory: ConnectionFactory) -> Iterator[None]:
    """Let ``factory`` create the connections for the duration of a ``with`` block (tests)."""
    global _factory
    before = _factory
    _factory = factory
    try:
        yield
    finally:
        _factory = before


def _failure(error: Exception, config: DirectoryConfig) -> DirectoryError:
    """Turn what the library raised into an error for the administrator – without any password."""
    from ldap3.core import exceptions as ldap_errors

    if isinstance(error, DirectoryError):
        return error
    if isinstance(error, ldap_errors.LDAPCertificateError | ldap_errors.LDAPStartTLSError | ssl.SSLError):
        return DirectoryError(
            "tls", _("The encrypted connection failed or the certificate is not accepted: %(error)s") % {"error": error}
        )
    if isinstance(error, ldap_errors.LDAPSSLConfigurationError):
        return DirectoryError("tls", _("The CA certificate file cannot be used: %(error)s") % {"error": error})
    if isinstance(
        error,
        ldap_errors.LDAPSocketOpenError
        | ldap_errors.LDAPSocketReceiveError
        | ldap_errors.LDAPSocketSendError
        | OSError,
    ):
        return DirectoryError(
            "unreachable",
            _("The directory cannot be reached (%(servers)s): %(error)s")
            % {"servers": ", ".join(config.uris), "error": error},
        )
    return DirectoryError("search", _("The directory answered unexpectedly: %(error)s") % {"error": error})


def _bind(connection: Connection, config: DirectoryConfig) -> bool:
    """Open and bind; StartTLS before the bind where set. Returns the result of the bind."""
    try:
        connection.open()
        if config.start_tls and not any(parse_uri(uri)[2] for uri in config.uris) and not connection.start_tls():
            raise DirectoryError(
                "tls",
                _("The server does not accept StartTLS: %(error)s")
                % {"error": connection.result.get("description", "")},
            )
        return bool(connection.bind())
    except DirectoryError:
        raise
    except Exception as error:
        raise _failure(error, config) from error


def open_service_connection(config: DirectoryConfig) -> Connection:
    """A connection bound with the search account (or anonymous, if none is set).

    Raises:
        DirectoryError: The directory cannot be reached, or the search account is refused.
    """
    if not config.uris:
        raise DirectoryError("not_configured", _("No server is set."))
    if config.bind_dn and not config.bind_password:
        # A bind with a name and no password is an anonymous bind on many servers and would "succeed".
        raise DirectoryError("service_bind", _("The search account has no password. Enter it in the settings."))
    try:
        connection = _factory(config, config.bind_dn, config.bind_password)
    except DirectoryError:
        raise
    except Exception as error:
        raise _failure(error, config) from error
    if not _bind(connection, config):
        description = connection.result.get("description", "") if connection.result else ""
        with contextlib.suppress(Exception):
            connection.unbind()
        raise DirectoryError(
            "service_bind",
            _("The directory refused the search account (%(account)s): %(reason)s. Check DN and password.")
            % {"account": config.bind_dn or _("anonymous"), "reason": description or _("not accepted")},
        )
    return connection


def close(connection: Connection | None) -> None:
    """Log out of the directory; errors on the way out do not matter."""
    if connection is not None:
        with contextlib.suppress(Exception):
            connection.unbind()


def check_password(config: DirectoryConfig, dn: str, password: str) -> bool:
    """Whether ``dn`` can log in with ``password``: a new bind on a connection of its own.

    A wrong password is ``False``; a directory that cannot be reached is an error.

    Raises:
        DirectoryError: The directory could not be asked.
    """
    if not password or not dn:
        return False  # an empty password would be taken as an anonymous bind
    try:
        connection = _factory(config, dn, password)
    except DirectoryError:
        raise
    except Exception as error:
        raise _failure(error, config) from error
    try:
        return _bind(connection, config)
    finally:
        close(connection)


# --- Searching ---------------------------------------------------------------------------------------------------


def _entries(connection: Connection) -> list[DirectoryEntry]:
    """The entries of the last search (referrals left out), attribute names in lower case."""
    found = []
    for item in connection.response or []:
        if item.get("type") != "searchResEntry":
            continue
        attributes = {
            str(name).lower(): value if isinstance(value, list) else [value]
            for name, value in (item.get("attributes") or {}).items()
        }
        found.append(DirectoryEntry(str(item["dn"]), attributes))
    return found


def _search(
    connection: Connection, config: DirectoryConfig, base: str, search_filter: str, attributes: list[str], limit: int
) -> list[DirectoryEntry]:
    import ldap3

    try:
        ok = connection.search(
            base,
            search_filter,
            search_scope=ldap3.SUBTREE,
            attributes=attributes,
            size_limit=limit,
            time_limit=config.timeout_seconds,
        )
    except Exception as error:
        raise _failure(error, config) from error
    result = connection.result or {}
    code = result.get("result", 0)
    if not ok and code == 32:  # noSuchObject
        raise DirectoryError("search", _("The search base “%(base)s” does not exist.") % {"base": base})
    if not ok and code not in (0, 4):  # 4: more than asked for – the entries so far are fine
        raise DirectoryError(
            "search",
            _("The search in “%(base)s” failed: %(reason)s")
            % {"base": base, "reason": result.get("description", code)},
        )
    return _entries(connection)


def find_user(config: DirectoryConfig, connection: Connection, username: str) -> DirectoryEntry | None:
    """The one entry the user filter finds for a name; ``None`` if there is none.

    Raises:
        DirectoryError: Several entries match (the filter is too wide), or the search fails.
    """
    search_filter = fill_template(config.user_search_filter, username=username)
    entries = _search(connection, config, config.user_search_base, search_filter, config.user_attributes, 3)
    if not entries:
        return None
    if len(entries) > 1:
        raise DirectoryError(
            "ambiguous",
            _("The filter for users finds more than one entry for the name “%(name)s”. Make the filter narrower.")
            % {"name": username},
        )
    return entries[0]


def entry_exists(config: DirectoryConfig, connection: Connection, dn: str) -> bool:
    """Whether an entry with exactly this DN exists (a search with the DN as base and scope "base")."""
    import ldap3

    try:
        connection.search(dn, "(objectClass=*)", search_scope=ldap3.BASE, attributes=["1.1"], size_limit=1)
    except Exception as error:
        raise _failure(error, config) from error
    result = connection.result or {}
    if result.get("result", 0) == 32:  # noSuchObject
        return False
    if result.get("result", 0) not in (0, 4):
        raise DirectoryError(
            "search",
            _("The search for %(dn)s failed: %(reason)s") % {"dn": dn, "reason": result.get("description", "")},
        )
    return bool(_entries(connection))


def groups_of(config: DirectoryConfig, connection: Connection, entry: DirectoryEntry) -> list[str]:
    """The DNs of the groups of a user: from an attribute of the user, or by searching the groups."""
    if config.group_mode == "member_of":
        return entry.values(config.member_of_attribute)
    search_filter = fill_template(
        config.group_search_filter, user_dn=entry.dn, username=entry.first(config.attribute_username)
    )
    found = _search(connection, config, config.group_search_base, search_filter, ["cn"], 1000)
    return [group.dn for group in found]


def lookup(config: DirectoryConfig, username: str) -> tuple[DirectoryEntry | None, list[str]]:
    """Find a user and the groups in one go, with the search account (no password of the user involved).

    Raises:
        DirectoryError: The directory could not be asked.
    """
    connection = open_service_connection(config)
    try:
        entry = find_user(config, connection, username)
        return (entry, groups_of(config, connection, entry)) if entry is not None else (None, [])
    finally:
        close(connection)


# --- Test connection ---------------------------------------------------------------------------------------------


@dataclass
class ConnectionReport:
    """What "Test connection" found out, as lines for the page and the API."""

    ok: bool
    steps: list[dict[str, Any]] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        """Add one step of the test."""
        self.steps.append({"step": name, "ok": ok, "detail": detail})
        self.ok = self.ok and ok


def check_connection(config: DirectoryConfig) -> ConnectionReport:
    """Try the settings step by step: servers, encryption, search account, search bases (AUT-029).

    The report never fails with an exception: whatever went wrong is a step that is not ``ok``.
    """
    report = ConnectionReport(ok=True)
    if not config.uris:
        report.add(_("Servers"), False, _("No server is set."))
        return report
    report.add(_("Servers"), True, ", ".join(config.uris))
    plain = unencrypted_uris(config.uris, config.start_tls)
    if plain:
        report.add(
            _("Encryption"),
            False,
            _(
                "The connection is not encrypted (%(servers)s): passwords travel in the open. Use ldaps:// or "
                "switch on StartTLS for ldap:// addresses."
            )
            % {"servers": ", ".join(plain)},
        )
    elif not config.verify_certificate:
        report.add(_("Encryption"), False, _("Encrypted, but the certificate of the server is not checked."))
    else:
        report.add(_("Encryption"), True, _("Encrypted, certificate checked."))
    try:
        connection = open_service_connection(config)
    except DirectoryError as error:
        report.add(_("Connection and search account"), False, str(error))
        return report
    report.add(_("Connection and search account"), True, config.bind_dn or _("anonymous"))
    try:
        for label, base, attribute in (
            (_("Search base for users"), config.user_search_base, config.attribute_username),
            (
                _("Search base for groups"),
                config.group_search_base if config.group_mode == "search" else "",
                "cn",
            ),
        ):
            if not base:
                continue
            try:
                import ldap3

                connection.search(
                    base, "(objectClass=*)", search_scope=ldap3.BASE, attributes=[attribute], size_limit=1
                )
                code = (connection.result or {}).get("result", 0)
                if code == 0:
                    report.add(label, True, base)
                elif code == 32:
                    report.add(label, False, _("“%(base)s” does not exist.") % {"base": base})
                else:
                    report.add(label, False, f"{base}: {(connection.result or {}).get('description', code)}")
            except Exception as error:
                report.add(label, False, str(_failure(error, config)))
    finally:
        close(connection)
    return report
