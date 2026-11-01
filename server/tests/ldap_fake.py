# SPDX-License-Identifier: GPL-3.0-or-later
"""An in-process directory for the tests of the LDAP login (AUT-029).

No LDAP server is needed: ``ldap3`` brings a mock strategy (``MOCK_SYNC``) that keeps the entries in memory and
answers searches (with real filter parsing) and binds (``userPassword`` is compared). The tests give the code
this directory through the same *connection factory* the real connections come from
(``ldap_client.using_factory``), so the search, filter, bind and result handling of Rentalars run for real –
only the network and the TLS handshake are missing. What the mock does not know: extensible matches such as the
nested-group rule of Active Directory, the ``memberOf`` overlay of OpenLDAP (the attribute is simply stored on
the user), paged results, referrals and, of course, TLS.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

import ldap3
from ldap3.core.exceptions import LDAPSocketOpenError

from rentalars.accounts import ldap_client
from rentalars.accounts.ldap_client import DirectoryConfig

BASE = "dc=example,dc=com"
SERVICE_DN = f"cn=rentalars,ou=service,{BASE}"
SERVICE_PASSWORD = "service-secret"


class FakeDirectory:
    """Entries in memory, reached through ``MOCK_SYNC`` connections."""

    def __init__(self) -> None:
        self.server = ldap3.Server("fake-directory", get_info=ldap3.NONE)
        self._seed = ldap3.Connection(self.server, client_strategy=ldap3.MOCK_SYNC)
        self._seed.open()
        #: When true, every connection fails as if the server were down.
        self.down = False
        #: The DNs that were bound (never a password) and the filters that were searched with.
        self.binds: list[str] = []
        self.filters: list[str] = []
        for unit in ("people", "groups", "service"):
            self.add(f"ou={unit},{BASE}", objectClass=["top", "organizationalUnit"], ou=unit)
        self.add(SERVICE_DN, userPassword=SERVICE_PASSWORD, objectClass=["person"], cn="rentalars")

    def add(self, dn: str, **attributes: Any) -> None:
        """Add an entry with the given attributes."""
        self._seed.strategy.add_entry(dn, attributes)

    def change(self, dn: str, attribute: str, values: list[str]) -> None:
        """Replace all values of an attribute of an entry (an LDAP modify)."""
        self._seed.modify(dn, {attribute: [(ldap3.MODIFY_REPLACE, values)]})

    def remove(self, dn: str) -> None:
        """Delete an entry."""
        self._seed.delete(dn)

    def add_user(
        self,
        username: str,
        password: str = "pw-of-the-user",
        *,
        ou: str = "people",
        first: str = "",
        last: str = "",
        mail: str | None = None,
        groups: list[str] = (),  # type: ignore[assignment]
        attribute: str = "sAMAccountName",
        **extra: Any,
    ) -> str:
        """Add a user (``objectClass=person``) and return the DN; ``groups`` are DNs for the ``memberOf`` attribute."""
        dn = f"cn={username},ou={ou},{BASE}"
        attributes: dict[str, Any] = {
            "objectClass": ["top", "person", "organizationalPerson", "user"],
            "cn": username,
            attribute: username,
            "userPassword": password,
            "givenName": first,
            "sn": last,
            "mail": mail if mail is not None else f"{username}@example.com",
            **extra,
        }
        if groups:
            attributes["memberOf"] = list(groups)
        attributes = {name: value for name, value in attributes.items() if value not in ("", None)}
        self.add(dn, **attributes)
        return dn

    def add_group(self, name: str, members: list[str] = (), *, ou: str = "groups") -> str:  # type: ignore[assignment]
        """Add a group (``groupOfNames``) and return its DN."""
        dn = f"cn={name},ou={ou},{BASE}"
        self.add(dn, objectClass=["top", "groupOfNames"], cn=name, member=list(members))
        return dn

    def factory(self, config: DirectoryConfig, bind_dn: str, password: str) -> ldap3.Connection:
        """The connection factory: an unbound mock connection on this directory."""
        if self.down:
            raise LDAPSocketOpenError("connection refused (the fake directory is down)")
        connection = ldap3.Connection(
            self.server,
            user=bind_dn or None,
            password=password or None,
            authentication=ldap3.SIMPLE if bind_dn else ldap3.ANONYMOUS,
            client_strategy=ldap3.MOCK_SYNC,
            raise_exceptions=False,
            auto_referrals=False,
        )
        self.binds.append(bind_dn or "(anonymous)")
        original = connection.search

        def recording_search(search_base: str, search_filter: str, *args: Any, **kwargs: Any) -> Any:
            self.filters.append(search_filter)
            return original(search_base, search_filter, *args, **kwargs)

        connection.search = recording_search  # type: ignore[method-assign]
        return connection

    @contextlib.contextmanager
    def active(self) -> Iterator[FakeDirectory]:
        """Let the code under test talk to this directory for the duration of a ``with`` block."""
        with ldap_client.using_factory(self.factory):
            yield self


def standard_directory() -> FakeDirectory:
    """A small company: three groups, four people, one of them in no group."""
    directory = FakeDirectory()
    admins = directory.add_group("rentalars-admins")
    planners = directory.add_group("rentalars-planners")
    crew = directory.add_group("rentalars-crew")
    directory.add_user("anna", "anna-pw", first="Anna", last="Beispiel", groups=[admins])
    directory.add_user("bernd", "bernd-pw", first="Bernd", last="Planer", groups=[planners, crew])
    directory.add_user("carla", "carla-pw", first="Carla", last="Crew", groups=[crew])
    directory.add_user("dieter", "dieter-pw", first="Dieter", last="Draussen")
    return directory
