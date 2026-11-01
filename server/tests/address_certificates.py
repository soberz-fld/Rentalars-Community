# SPDX-License-Identifier: GPL-3.0-or-later
"""Certificates for the tests of the server address (ADM-016): a small certificate authority made on the spot.

``make_chain("rentalars.example.com")`` gives a root, an intermediate and a
server certificate with its key, all as PEM bytes, valid around the stopped
clock of the tests (or any moment given).
"""

from __future__ import annotations

import datetime
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from unittest import TestCase, mock

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from django.test import override_settings
from django.utils import timezone


@dataclass
class Chain:
    """PEM bytes of a test PKI."""

    root: bytes
    intermediate: bytes
    leaf: bytes
    key: bytes
    other_key: bytes

    @property
    def leaf_and_intermediate(self) -> bytes:
        """What a provider hands out: the server's certificate, then the intermediate one."""
        return self.leaf + self.intermediate


def _name(common: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common)])


def _pem_key(key: ec.EllipticCurvePrivateKey, password: bytes | None = None) -> bytes:
    encryption = serialization.BestAvailableEncryption(password) if password else serialization.NoEncryption()
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, encryption)


def _certificate(
    subject: str,
    key: ec.EllipticCurvePrivateKey,
    issuer: str,
    issuer_key: ec.EllipticCurvePrivateKey,
    *,
    start: datetime.datetime,
    end: datetime.datetime,
    names: list[str] | None,
    ca: bool,
) -> bytes:
    builder = (
        x509.CertificateBuilder()
        .subject_name(_name(subject))
        .issuer_name(_name(issuer))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start)
        .not_valid_after(end)
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
    )
    if names:
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in names]), critical=False)
    return builder.sign(issuer_key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM)


def make_chain(
    host: str = "rentalars.example.com",
    *,
    now: datetime.datetime | None = None,
    days: int = 365,
    names: list[str] | None = None,
    password: bytes | None = None,
    started_days_ago: int = 1,
) -> Chain:
    """A root, an intermediate and a server certificate for ``host`` (or ``names``)."""
    now = now or timezone.now()
    start = now - datetime.timedelta(days=started_days_ago)
    root_key, intermediate_key, leaf_key, other = (ec.generate_private_key(ec.SECP256R1()) for _ in range(4))
    long_end = now + datetime.timedelta(days=3650)
    root = _certificate(
        "Test Root CA", root_key, "Test Root CA", root_key, start=start, end=long_end, names=None, ca=True
    )
    intermediate = _certificate(
        "Test Intermediate CA",
        intermediate_key,
        "Test Root CA",
        root_key,
        start=start,
        end=long_end,
        names=None,
        ca=True,
    )
    leaf = _certificate(
        host,
        leaf_key,
        "Test Intermediate CA",
        intermediate_key,
        start=start,
        end=now + datetime.timedelta(days=days),
        names=[host] if names is None else names,
        ca=False,
    )
    return Chain(root, intermediate, leaf, _pem_key(leaf_key, password), _pem_key(other))


def make_self_signed(
    host: str = "rentalars.example.com", *, now: datetime.datetime | None = None
) -> tuple[bytes, bytes]:
    """A self-signed certificate for ``host`` with its key."""
    now = now or timezone.now()
    key = ec.generate_private_key(ec.SECP256R1())
    certificate = _certificate(
        host,
        key,
        host,
        key,
        start=now - datetime.timedelta(days=1),
        end=now + datetime.timedelta(days=400),
        names=[host],
        ca=False,
    )
    return certificate, _pem_key(key)


def isolate_server_address(test: TestCase, *, addresses: list[str] | None = None) -> Path:
    """Keep a test away from this machine (ADM-016): no NGINX site, no DNS, no ports, files in a temporary folder.

    ``addresses`` is what every name resolves to (none by default). Undone at the end of the test; returns the
    data folder.
    """
    folder = Path(tempfile.mkdtemp(prefix="address083-"))
    test.addCleanup(shutil.rmtree, folder, True)
    for patch in (
        mock.patch("rentalars.core.server_address.NGINX_SITE", folder / "no-nginx-site"),
        mock.patch("rentalars.core.server_address._resolve", return_value=list(addresses or [])),
        mock.patch("rentalars.core.server_address._listening", return_value=True),
        mock.patch("rentalars.core.network._interface_addresses", return_value=set()),
    ):
        patch.start()
        test.addCleanup(patch.stop)
    data = override_settings(DATA_DIR=folder / "data")
    data.enable()
    test.addCleanup(data.disable)
    return folder / "data"
