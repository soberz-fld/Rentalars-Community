# SPDX-License-Identifier: GPL-3.0-or-later
"""The LDAP login against a real OpenLDAP server (AUT-029) – opt-in.

The other tests use ``ldap3``'s mock directory. This module starts ``slapd`` (OpenLDAP) from the operating system
in a temporary folder, on 127.0.0.1 and a free port, with the ``memberOf`` overlay and a self-signed
certificate, and lets the real connection code of Rentalars talk to it: TLS with a certificate check against the
host name (``ldaps://`` and StartTLS), the bind with the search account, searches, a user's own bind, the
``memberOf`` groups of the overlay and the groups found by a search.

It runs only if ``RENTALARS_SLAPD=1`` is set and ``slapd`` is installed (``/usr/sbin/slapd``; Debian/Ubuntu:
``apt install slapd``); otherwise it is skipped:

    RENTALARS_SLAPD=1 python manage.py test tests.unit.test_100_ldap_slapd

What it does not cover (nobody has such a server here): Active Directory (``sAMAccountName``, nested groups,
referrals), a directory behind a real company CA.
"""

from __future__ import annotations

import datetime
import ipaddress
import os
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from django.contrib.auth import authenticate
from django.test import RequestFactory

from rentalars.accounts import ldap_client
from rentalars.accounts.models import LdapGroupMapping, LdapSettings, Role, SecurityEvent, SecurityEventKind, User
from tests.helpers import RentalarsTestCase

SLAPD = shutil.which("slapd") or "/usr/sbin/slapd"
SCHEMA = Path("/etc/ldap/schema")
MODULES = Path("/usr/lib/ldap")
SUFFIX = "dc=example,dc=com"
ADMIN_DN = f"cn=admin,{SUFFIX}"
ADMIN_PASSWORD = "root-secret"
SERVICE_DN = f"cn=search,{SUFFIX}"
SERVICE_PASSWORD = "search-secret"

ENABLED = os.environ.get("RENTALARS_SLAPD") == "1" and Path(SLAPD).exists() and SCHEMA.exists()


def free_port() -> int:
    """A TCP port nobody listens on."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def self_signed(folder: Path) -> str:
    """A certificate for ``localhost`` / 127.0.0.1; the key and the certificate are written to ``folder``."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=2))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    pem = certificate.public_bytes(serialization.Encoding.PEM)
    (folder / "cert.pem").write_bytes(pem)
    (folder / "key.pem").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()
        )
    )
    return pem.decode()


LDIF = f"""dn: {SUFFIX}
objectClass: top
objectClass: dcObject
objectClass: organization
o: Example
dc: example

dn: ou=people,{SUFFIX}
objectClass: organizationalUnit
ou: people

dn: ou=groups,{SUFFIX}
objectClass: organizationalUnit
ou: groups

dn: {SERVICE_DN}
objectClass: organizationalRole
objectClass: simpleSecurityObject
cn: search
userPassword: {SERVICE_PASSWORD}

dn: uid=anna,ou=people,{SUFFIX}
objectClass: inetOrgPerson
uid: anna
cn: Anna Beispiel
givenName: Anna
sn: Beispiel
mail: anna@example.com
userPassword: anna-pw

dn: uid=bernd,ou=people,{SUFFIX}
objectClass: inetOrgPerson
uid: bernd
cn: Bernd Planer
givenName: Bernd
sn: Planer
mail: bernd@example.com
userPassword: bernd-pw

dn: cn=rentalars-admins,ou=groups,{SUFFIX}
objectClass: groupOfNames
cn: rentalars-admins
member: uid=anna,ou=people,{SUFFIX}

dn: cn=rentalars-planners,ou=groups,{SUFFIX}
objectClass: groupOfNames
cn: rentalars-planners
member: uid=bernd,ou=people,{SUFFIX}
"""


@unittest.skipUnless(ENABLED, "set RENTALARS_SLAPD=1 and install slapd to run the OpenLDAP integration test")
class OpenLdapTests(RentalarsTestCase):
    """The real connection code against a real OpenLDAP."""

    process: subprocess.Popen[bytes]
    folder: Path
    port: int
    cert_pem: str

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.folder = Path(tempfile.mkdtemp(prefix="rentalars-slapd-"))
        cls.port = free_port()
        cls.cert_pem = self_signed(cls.folder)
        (cls.folder / "data").mkdir()
        config = f"""
include {SCHEMA}/core.schema
include {SCHEMA}/cosine.schema
include {SCHEMA}/inetorgperson.schema
include {SCHEMA}/nis.schema
pidfile {cls.folder}/slapd.pid
modulepath {MODULES}
moduleload back_mdb
moduleload memberof
TLSCertificateFile {cls.folder}/cert.pem
TLSCertificateKeyFile {cls.folder}/key.pem
database mdb
suffix "{SUFFIX}"
rootdn "{ADMIN_DN}"
rootpw {ADMIN_PASSWORD}
directory {cls.folder}/data
index objectClass eq
overlay memberof
memberof-group-oc groupOfNames
memberof-member-ad member
memberof-memberof-ad memberOf
memberof-refint true
access to attrs=userPassword by anonymous auth by * none
access to * by dn.exact="{SERVICE_DN}" read by self read by * none
"""
        (cls.folder / "slapd.conf").write_text(config)
        # People first, then the groups: the memberOf overlay writes the attribute when a group is added.
        (cls.folder / "load.ldif").write_text(LDIF)
        cls.process = subprocess.Popen(
            [
                SLAPD,
                "-f",
                str(cls.folder / "slapd.conf"),
                "-h",
                f"ldap://127.0.0.1:{cls.port} ldaps://127.0.0.1:{cls.port + 1}",
                "-d",
                "0",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        cls.ldaps_port = cls.port + 1
        for _attempt in range(50):
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", cls.port)) == 0:
                    break
            time.sleep(0.1)
        else:
            cls.tearDownClass()
            raise RuntimeError("slapd did not start")
        subprocess.run(
            [
                "ldapadd",
                "-x",
                "-H",
                f"ldap://127.0.0.1:{cls.port}",
                "-D",
                ADMIN_DN,
                "-w",
                ADMIN_PASSWORD,
                "-f",
                str(cls.folder / "load.ldif"),
            ],
            check=True,
            capture_output=True,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        process = getattr(cls, "process", None)
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        shutil.rmtree(cls.folder, ignore_errors=True)
        super().tearDownClass()

    def configure(self, **changes: Any) -> LdapSettings:
        """Switch the directory login on for the OpenLDAP of this test (ldaps, certificate checked by name)."""
        settings = LdapSettings.load()
        values: dict[str, Any] = {
            "enabled": True,
            "server_uris": f"ldaps://localhost:{self.ldaps_port}",
            "ca_certificate_pem": self.cert_pem,
            "bind_dn": SERVICE_DN,
            "user_search_base": f"ou=people,{SUFFIX}",
            "user_search_filter": "(&(objectClass=inetOrgPerson)(uid={username}))",
            "attribute_username": "uid",
            "group_mode": "member_of",
            "timeout_seconds": 5,
        }
        values.update(changes)
        for name, value in values.items():
            setattr(settings, name, value)
        settings.set_bind_password(SERVICE_PASSWORD)
        settings.save()
        for group, role in (("rentalars-admins", "Administrator"), ("rentalars-planners", "Projektleitung")):
            mapping, _created = LdapGroupMapping.objects.get_or_create(group=f"cn={group},ou=groups,{SUFFIX}")
            mapping.roles.set(Role.objects.filter(name=role))
        return settings

    def login(self, username: str, password: str) -> User | None:
        """Ask the authentication backends like the login page does."""
        request = RequestFactory().post("/login/")
        request.session = {}  # type: ignore[assignment]
        return authenticate(request, username=username, password=password)

    def test_login_over_ldaps_with_the_member_of_overlay(self) -> None:
        self.configure()
        user = self.login("anna", "anna-pw")
        assert user is not None
        self.assertEqual(sorted(user.roles.values_list("name", flat=True)), ["Administrator"])
        self.assertEqual((user.first_name, user.last_name, user.email), ("Anna", "Beispiel", "anna@example.com"))
        self.assertEqual(user.ldap_dn, f"uid=anna,ou=people,{SUFFIX}")
        self.assertIsNone(self.login("anna", "wrong"))
        self.assertIsNone(self.login("anna", ""))
        self.assertIsNone(self.login("anna)(uid=*", "x"))

    def test_login_with_groups_found_by_a_search(self) -> None:
        self.configure(
            group_mode="search",
            group_search_base=f"ou=groups,{SUFFIX}",
            group_search_filter="(&(objectClass=groupOfNames)(member={user_dn}))",
        )
        user = self.login("bernd", "bernd-pw")
        assert user is not None
        self.assertEqual(sorted(user.roles.values_list("name", flat=True)), ["Projektleitung"])

    def test_the_certificate_is_checked_against_the_host_name(self) -> None:
        """Without the CA certificate, or for a name the certificate does not carry, the connection is refused."""
        self.configure(ca_certificate_pem="")
        self.assertIsNone(self.login("anna", "anna-pw"))
        self.assertTrue(
            SecurityEvent.objects.filter(kind=SecurityEventKind.LDAP_ERROR, detail__startswith="tls").exists()
        )
        SecurityEvent.objects.all().delete()
        # A host given as an IP address is refused even though the IP is in the certificate: ldap3 compares only
        # names (DNS entries) – so the servers must be entered with their names (documented for the operator).
        self.configure(server_uris=f"ldaps://127.0.0.1:{self.ldaps_port}")
        self.assertIsNone(self.login("anna", "anna-pw"))
        self.assertTrue(
            SecurityEvent.objects.filter(kind=SecurityEventKind.LDAP_ERROR, detail__startswith="tls").exists()
        )
        self.configure(server_uris=f"ldaps://localhost:{self.ldaps_port}")  # the name is in the certificate: accepted
        self.assertIsNotNone(self.login("anna", "anna-pw"))
        self.configure(verify_certificate=False, ca_certificate_pem="")
        self.assertIsNotNone(self.login("anna", "anna-pw"))

    def test_start_tls(self) -> None:
        self.configure(server_uris=f"ldap://localhost:{self.port}", start_tls=True)
        self.assertIsNotNone(self.login("anna", "anna-pw"))
        self.configure(server_uris=f"ldap://localhost:{self.port}", start_tls=True, ca_certificate_pem="")
        self.assertIsNone(self.login("anna", "anna-pw"))

    def test_a_wrong_search_account_password_and_a_wrong_base(self) -> None:
        settings = self.configure()
        settings.set_bind_password("nope")
        settings.save()
        self.assertIsNone(self.login("anna", "anna-pw"))
        self.assertTrue(
            SecurityEvent.objects.filter(kind=SecurityEventKind.LDAP_ERROR, detail__contains="service_bind").exists()
        )
        self.configure(user_search_base=f"ou=nowhere,{SUFFIX}")
        report = ldap_client.check_connection(ldap_client.DirectoryConfig.from_settings(LdapSettings.load()))
        self.assertFalse(report.ok)

    def test_connection_test_and_the_unencrypted_warning(self) -> None:
        self.configure()
        report = ldap_client.check_connection(ldap_client.DirectoryConfig.from_settings(LdapSettings.load()))
        self.assertTrue(report.ok, report.steps)
        self.configure(server_uris=f"ldap://localhost:{self.port}")
        report = ldap_client.check_connection(ldap_client.DirectoryConfig.from_settings(LdapSettings.load()))
        self.assertFalse(report.ok)  # works, but the connection is not encrypted

    def test_a_server_that_is_not_there(self) -> None:
        self.configure(server_uris=f"ldaps://localhost:{free_port()}")
        self.assertIsNone(self.login("anna", "anna-pw"))
        self.assertTrue(
            SecurityEvent.objects.filter(kind=SecurityEventKind.LDAP_ERROR, detail__startswith="unreachable").exists()
        )
