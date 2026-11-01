# SPDX-License-Identifier: GPL-3.0-or-later
"""Server address and certificate from the settings (ADM-016).

The application never changes the web server itself: that needs root, which
Rentalars deliberately does not have (ADM-009). The approach chosen: only show
the command. The settings page prepares everything – new host name, where the
certificate comes from, an uploaded certificate with its key – checks what can
be checked from inside the application and shows exactly one command,
``sudo rentalars address apply <token>``, which the operator runs via SSH.
That command (``deploy/address.py``) reads the prepared change through
``manage.py address_change export``, checks everything again itself, backs up,
changes configuration file, NGINX and certificate, restarts and checks the new
address, rolls everything back on any failure and records the result through
``manage.py address_change record``.

This module holds the application's side:

* :func:`current_state` – the address in ``[rentalars] url``, the names and
  the certificate in the NGINX site of the installation, and the certificate
  NGINX actually presents (read through a TLS handshake with this server,
  since the certificate files are readable by root only),
* :func:`normalise_host` and :func:`check_certificate` – the checks of the
  entered name and of an uploaded certificate (key matches, chain, names,
  validity),
* :func:`run_checks` – DNS of the new name and the ports of this server,
* :func:`prepare` – stores the change (model + files in the data folder, the
  key encrypted like other stored secrets and readable by the service user
  only), :func:`export` and :func:`record` – the two ends the command talks to.
"""

from __future__ import annotations

import datetime
import functools
import ipaddress
import os
import re
import secrets
import shutil
import socket
import ssl
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext, pgettext

from rentalars.core.address_models import AddressChange, AddressChangeStatus, CertificateKind
from rentalars.core.crypto import decrypt_secret, encrypt_secret
from rentalars.core.i18n import local_pattern

#: The NGINX site the installation writes (deploy/install.sh, NFA-030).
NGINX_SITE = Path("/etc/nginx/sites-available/rentalars")
#: Certificates of Let's Encrypt live below this folder (certbot).
LETSENCRYPT_DIR = "/etc/letsencrypt/"
#: The port NGINX of the installation speaks HTTPS on; the address has no port of its own.
HTTPS_PORT = 443
#: How long a look at this server may take (TLS handshake, ports), in seconds.
PROBE_SECONDS = 2.0
#: An uploaded certificate file or key larger than this is refused.
MAX_PEM_BYTES = 100_000
#: A certificate that ends within this many days gets a warning.
EXPIRY_WARNING_DAYS = 30
#: The folder below the data folder with the files of prepared changes.
FILES_FOLDER = "address"
CERTIFICATE_FILE = "certificate.pem"
KEY_FILE = "private-key.pem.enc"

#: Used with fullmatch only: "$" would let a trailing line break through.
_LABEL = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?")
#: Names Let's Encrypt never issues for: they are not in the public DNS.
_PRIVATE_SUFFIXES = (".local", ".lan", ".internal", ".home.arpa", ".intranet", ".localdomain", ".corp", ".home")


class AddressError(ValueError):
    """A prepared change cannot be stored; ``errors`` maps field names to messages."""

    def __init__(self, errors: dict[str, list[str]]) -> None:
        super().__init__("; ".join(message for messages in errors.values() for message in messages))
        self.errors = errors


# --- The name ---------------------------------------------------------------------------------------------


def valid_label(label: str) -> bool:
    """One part of a host name between dots: letters, digits, inner hyphens, at most 63 – nothing after it."""
    return _LABEL.fullmatch(label) is not None


def normalise_host(text: str, *, for_letsencrypt: bool = False) -> str:
    """The host name as it will stand in the configuration and in NGINX, or :class:`AddressError`.

    Accepts ``https://name/`` as well as ``name``; umlauts become their
    ``xn--`` form. A port, a path, an IP address or ``localhost`` are refused.
    """
    host = (text or "").strip().lower()
    for scheme in ("https://", "http://"):
        if host.startswith(scheme):
            host = host[len(scheme) :]
    host = host.rstrip("/").rstrip(".")
    if not host:
        raise AddressError({"host": [_("Enter the new host name, e.g. rentalars.example.com.")]})
    if any(sign in host for sign in ":/@?#") or any(sign.isspace() for sign in host):
        raise AddressError({"host": [_("Only the name, without a port, path or spaces – e.g. rentalars.example.com.")]})
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise AddressError({"host": [_("Enter a name, not an IP address.")]})
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        raise AddressError({"host": [_("This is not a valid host name.")]}) from None
    labels = host.split(".")
    if len(host) > 253 or not all(valid_label(label) for label in labels) or labels[-1].isdigit():
        raise AddressError({"host": [_("This is not a valid host name.")]})
    if host == "localhost" or host.endswith(".localhost"):
        raise AddressError({"host": [_("“localhost” cannot be reached by others. Enter the name people will use.")]})
    if for_letsencrypt and (len(labels) < 2 or host.endswith(_PRIVATE_SUFFIXES)):
        raise AddressError(
            {
                "host": [
                    _(
                        "Let's Encrypt only issues certificates for names in the public DNS. For a name within "
                        "your network, use your own certificate."
                    )
                ]
            }
        )
    return host


def host_of(url: str) -> str:
    """The host part of an address such as ``https://rentalars.example.com``."""
    return (urlsplit(url or "").hostname or "").lower()


# --- Certificates -----------------------------------------------------------------------------------------


@dataclass
class CertificateReport:
    """What :func:`check_certificate` found about an uploaded certificate."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    #: Names, issuer, expiry and fingerprint – shown on the page, stored with the change.
    info: dict[str, Any] = field(default_factory=dict)
    #: The certificate and its chain in the right order (PEM), as NGINX wants them.
    chain_pem: str = ""
    key_pem: str = ""


def _names_of(certificate: Any) -> list[str]:
    from cryptography import x509

    try:
        extension = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    except x509.ExtensionNotFound:
        return []
    return [str(name).lower() for name in extension.value.get_values_for_type(x509.DNSName)]


def name_matches(host: str, names: list[str]) -> bool:
    """Whether a certificate for ``names`` is valid for ``host`` (a wildcard covers exactly one label)."""
    for name in names:
        if name == host:
            return True
        if name.startswith("*.") and "." in host and host.split(".", 1)[1] == name[2:]:
            return True
    return False


def _readable_name(name: Any) -> str:
    """The common name of a subject or issuer, else its organisation, else the whole name."""
    from cryptography.x509.oid import NameOID

    for oid in (NameOID.COMMON_NAME, NameOID.ORGANIZATION_NAME):
        values = name.get_attributes_for_oid(oid)
        if values:
            return str(values[0].value)
    return name.rfc4514_string()


def _is_self_signed(certificate: Any) -> bool:
    if certificate.issuer != certificate.subject:
        return False
    try:
        certificate.verify_directly_issued_by(certificate)
    except Exception:  # any failure means "not signed by itself"
        return False
    return True


def _issued_by(certificate: Any, issuer: Any) -> bool:
    if certificate.issuer != issuer.subject:
        return False
    try:
        certificate.verify_directly_issued_by(issuer)
    except Exception:  # a wrong signature, an unsupported key: not the issuer
        return False
    return True


def certificate_info(certificate: Any, *, now: datetime.datetime | None = None) -> dict[str, Any]:
    """Names, issuer, validity and fingerprint of a certificate, for the page and the API."""
    from cryptography.hazmat.primitives import hashes

    now = now or timezone.now()
    not_after = certificate.not_valid_after_utc
    return {
        "names": _names_of(certificate),
        "subject": _readable_name(certificate.subject),
        "issuer": _readable_name(certificate.issuer),
        "self_signed": _is_self_signed(certificate),
        "not_before": certificate.not_valid_before_utc.isoformat(),
        "not_after": not_after.isoformat(),
        "days_left": (not_after - now).days,
        "fingerprint": certificate.fingerprint(hashes.SHA256()).hex(":").upper(),
    }


@functools.cache
def _system_roots() -> tuple[Any, ...]:
    """The certificate authorities this server trusts (the ca-certificates package), read once per process."""
    from cryptography import x509

    paths = [ssl.get_default_verify_paths().cafile, "/etc/ssl/certs/ca-certificates.crt"]
    for path in paths:
        if path and os.path.isfile(path):
            try:
                # A few old authorities have serial numbers newer libraries only warn about.
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    return tuple(x509.load_pem_x509_certificates(Path(path).read_bytes()))
            except (OSError, ValueError):
                continue
    return ()


def _trusted(leaf: Any, intermediates: list[Any], host: str, now: datetime.datetime) -> bool | None:
    """Whether browsers will trust the certificate: ``None`` if this server has no list of authorities."""
    from cryptography import x509
    from cryptography.x509 import verification

    roots = _system_roots()
    if not roots:
        return None
    try:
        verifier = (
            verification.PolicyBuilder()
            .store(verification.Store(list(roots)))
            .time(now)
            .build_server_verifier(x509.DNSName(host))
        )
        verifier.verify(leaf, intermediates)
    except Exception:  # every refusal of the verifier means "not trusted"
        return False
    return True


def check_certificate(
    certificate_data: bytes, key_data: bytes, host: str, *, now: datetime.datetime | None = None
) -> CertificateReport:
    """Check an uploaded certificate and key for ``host`` (ADM-016).

    Errors stop the preparation: no certificate or no key in PEM form, a key
    with a password, a key that belongs to none of the certificates, a broken
    chain, a name the certificate does not cover, a certificate not yet or no
    longer valid. Warnings do not: the end is near, the intermediate
    certificates are missing, nobody browsers know issued it (an own
    certificate authority of the company is fine). The command on the server
    checks the files again with ``openssl`` before it uses them.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    now = now or timezone.now()
    report = CertificateReport()
    if not certificate_data or len(certificate_data) > MAX_PEM_BYTES:
        report.errors.append(_("Upload the certificate file (PEM, at most 100 kB)."))
    if not key_data or len(key_data) > MAX_PEM_BYTES:
        report.errors.append(_("Upload the private key (PEM, at most 100 kB)."))
    if report.errors:
        return report
    try:
        certificates = x509.load_pem_x509_certificates(certificate_data)
    except ValueError:
        certificates = []
    if not certificates:
        report.errors.append(
            _(
                "The certificate file contains no certificate in PEM format (text beginning with “-----BEGIN CERTIFICATE-----”)."
            )
        )
    if b"PRIVATE KEY" in certificate_data:
        report.errors.append(
            _(
                "The certificate file contains a private key. Upload the key as a separate file and the certificate without it."
            )
        )
    key = None
    try:
        key = serialization.load_pem_private_key(key_data, password=None)
    except TypeError:
        report.errors.append(
            _(
                "The private key is protected by a password. NGINX needs it without a password: openssl pkey -in key.pem -out key-open.pem"
            )
        )
    except Exception:  # every key that cannot be read, whatever the library says
        if b"BEGIN CERTIFICATE" in key_data:
            report.errors.append(
                _("The key file contains a certificate, not a private key. Were the two files swapped?")
            )
        else:
            report.errors.append(_("The key file contains no private key in PEM format."))
    if report.errors or key is None:
        return report
    if isinstance(key, rsa.RSAPrivateKey) and key.key_size < 2048:
        report.errors.append(
            _("The key is too short (%(bits)d bits); browsers require at least 2048.") % {"bits": key.key_size}
        )
    public = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    leaf = next(
        (
            certificate
            for certificate in certificates
            if certificate.public_key().public_bytes(
                serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
            )
            == public
        ),
        None,
    )
    if leaf is None:
        report.errors.append(_("The key does not belong to any certificate in the file."))
        return report
    # The chain: the server's certificate first, then whoever issued it, and so on.
    chain = [leaf]
    rest = [certificate for certificate in certificates if certificate is not leaf]
    while not _is_self_signed(chain[-1]):
        issuer = next((certificate for certificate in rest if _issued_by(chain[-1], certificate)), None)
        if issuer is None:
            break
        chain.append(issuer)
        rest.remove(issuer)
    if rest:
        report.errors.append(
            _(
                "The file contains certificates that do not belong to the chain of the server's certificate "
                "(%(names)s). The chain must lead from the server's certificate to the one that issued it, and so on."
            )
            % {"names": ", ".join(_readable_name(certificate.subject) for certificate in rest)}
        )
    elif chain != certificates:
        report.notes.append(_("The certificates were put into the right order: the server's certificate first."))
    info = certificate_info(leaf, now=now)
    info["chain_length"] = len(chain)
    report.info = info
    names = info["names"]
    if not names:
        report.errors.append(
            _("The certificate names no host names (Subject Alternative Name); browsers require them.")
        )
    elif not name_matches(host, names):
        report.errors.append(
            _("The certificate is valid for %(names)s, not for %(host)s.") % {"names": ", ".join(names), "host": host}
        )
    for certificate in chain:
        if certificate.not_valid_before_utc > now:
            report.errors.append(
                _("%(name)s is only valid from %(date)s.")
                % {"name": _readable_name(certificate.subject), "date": _date(certificate.not_valid_before_utc)}
            )
        elif certificate.not_valid_after_utc < now:
            report.errors.append(
                _("%(name)s expired on %(date)s.")
                % {"name": _readable_name(certificate.subject), "date": _date(certificate.not_valid_after_utc)}
            )
    if not report.errors and info["days_left"] < EXPIRY_WARNING_DAYS:
        report.warnings.append(
            ngettext(
                "The certificate expires in %(days)d day, on %(date)s.",
                "The certificate expires in %(days)d days, on %(date)s.",
                info["days_left"],
            )
            % {"days": info["days_left"], "date": _date(leaf.not_valid_after_utc)}
        )
    if not report.errors:
        if info["self_signed"]:
            report.warnings.append(
                _("The certificate is self-signed: browsers will warn until it is trusted on every device.")
            )
        else:
            trusted = _trusted(leaf, chain[1:], host, now)
            if trusted is False and len(chain) == 1:
                report.warnings.append(
                    _(
                        "The intermediate certificates are missing, or no authority known to browsers issued it. "
                        "Add the intermediate certificates of your provider to the certificate file, after the "
                        "server's certificate."
                    )
                )
            elif trusted is False:
                report.warnings.append(
                    _(
                        "No certificate authority known to browsers issued the certificate. That is fine for an "
                        "authority of your company that is trusted on every device; otherwise browsers will warn."
                    )
                )
    if report.errors:
        return report
    report.chain_pem = "".join(
        certificate.public_bytes(serialization.Encoding.PEM).decode("ascii") for certificate in chain
    )
    report.key_pem = key_data.decode("ascii", errors="replace")
    return report


def _date(moment: datetime.datetime) -> str:
    return timezone.localtime(moment).strftime(local_pattern("%d.%m.%Y"))


# --- What the server has now --------------------------------------------------------------------------------


@dataclass
class SiteInfo:
    """What the NGINX site of the installation says."""

    path: str
    found: bool = False
    server_names: list[str] = field(default_factory=list)
    certificate: str = ""
    private_key: str = ""


def read_site(path: Path | None = None) -> SiteInfo:
    """The names and the certificate files in the NGINX site (readable for the service user)."""
    path = path or NGINX_SITE
    info = SiteInfo(str(path))
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return info
    info.found = True
    for match in re.finditer(r"^\s*server_name\s+([^;]+);", text, re.MULTILINE):
        for name in match.group(1).split():
            if name not in info.server_names and name != "_":
                info.server_names.append(name)
    certificate = re.search(r"^\s*ssl_certificate\s+([^;]+);", text, re.MULTILINE)
    key = re.search(r"^\s*ssl_certificate_key\s+([^;]+);", text, re.MULTILINE)
    info.certificate = certificate.group(1).strip() if certificate else ""
    info.private_key = key.group(1).strip() if key else ""
    return info


def presented_certificate(host: str, port: int = HTTPS_PORT) -> Any | None:
    """The certificate NGINX on this server presents for ``host`` – or ``None`` if nothing answers.

    The certificate files are readable by root only; the handshake with this
    server itself shows the certificate in use, its names and its expiry. The
    connection goes to 127.0.0.1 only, with the name as SNI.
    """
    from cryptography import x509

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        with (
            socket.create_connection(("127.0.0.1", port), timeout=PROBE_SECONDS) as connection,
            context.wrap_socket(connection, server_hostname=host or None) as tls,
        ):
            der = tls.getpeercert(binary_form=True)
    except (OSError, ssl.SSLError, ValueError):
        return None
    if not der:
        return None
    try:
        return x509.load_der_x509_certificate(der)
    except ValueError:
        return None


@dataclass
class CurrentState:
    """The address of the installation as it is now (ADM-016)."""

    url: str
    host: str
    site: SiteInfo
    #: One of :class:`CertificateKind`, or ``"unknown"`` when it cannot be told.
    kind: str
    kind_label: str
    certificate: dict[str, Any] | None
    note: str = ""


KIND_LABELS = {
    "letsencrypt": gettext_lazy("Let's Encrypt, renewed automatically"),
    "selfsigned": gettext_lazy("Self-signed certificate"),
    "own": gettext_lazy("Own certificate"),
    "proxy": gettext_lazy("No certificate of its own: a server in front encrypts (TLS proxy)"),
    "unknown": gettext_lazy("Certificate file of the server (could not be read)"),
}


def current_state(*, site_path: Path | None = None) -> CurrentState:
    """Read address, NGINX site and the presented certificate (ADM-016)."""
    url = str(getattr(settings, "RENTALARS_URL", "") or "")
    host = host_of(url)
    site = read_site(site_path)
    presented = presented_certificate(host) if site.found and site.certificate else None
    certificate = certificate_info(presented) if presented is not None else None
    note = ""
    if not site.found:
        kind = CertificateKind.PROXY.value
        note = _(
            "There is no NGINX site of the installation on this server (%(path)s): Rentalars is probably behind "
            "another server that encrypts, or this is a development installation."
        ) % {"path": site.path}
    elif not site.certificate:
        kind = CertificateKind.PROXY.value
    elif site.certificate.startswith(LETSENCRYPT_DIR):
        kind = CertificateKind.LETSENCRYPT.value
    elif certificate is None:
        kind = "unknown"
        note = _("NGINX did not answer on port 443; the certificate could not be read.")
    elif certificate["self_signed"]:
        kind = CertificateKind.SELF_SIGNED.value
    else:
        kind = CertificateKind.OWN.value
    return CurrentState(url, host, site, kind, str(KIND_LABELS[kind]), certificate, note)


# --- Checks of a new name -------------------------------------------------------------------------------------


def _resolve(host: str) -> list[str]:
    try:
        answers = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        return []
    found: list[str] = []
    for *_rest, address in answers:
        text = str(address[0]).split("%", 1)[0]
        if text not in found:
            found.append(text)
    return found


def _listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=PROBE_SECONDS):
            return True
    except OSError:
        return False


def _check(state: str, title: str, detail: str) -> dict[str, str]:
    return {"state": state, "title": str(title), "detail": str(detail)}


def run_checks(host: str, kind: str, current: CurrentState) -> list[dict[str, str]]:
    """What the application can check about the new name: DNS and the ports of this server (ADM-016).

    Whether the name leads to *this* server can only be said for certain when
    it resolves to an address of one of its interfaces or to the same address
    as the current name; behind a router (NAT) neither need be so, and the
    page then says that it is not sure.
    """
    from rentalars.core.network import _interface_addresses, kind_of

    checks: list[dict[str, str]] = []
    addresses = _resolve(host)
    title = _("DNS of %(host)s") % {"host": host}
    if not addresses:
        state = "error" if kind == CertificateKind.LETSENCRYPT else "warning"
        checks.append(
            _check(
                state,
                title,
                _("The name cannot be resolved (yet). Before the command is run, it must point to this server."),
            )
        )
    else:
        listed = ", ".join(addresses)
        own = {str(address) for address in _interface_addresses()}
        current_addresses = set(_resolve(current.host)) if current.host and current.host != host else set()
        internal = [address for address in addresses if kind_of(address)]
        if own.intersection(addresses):
            checks.append(_check("ok", title, _("Points to this server (%(addresses)s).") % {"addresses": listed}))
        elif current_addresses.intersection(addresses):
            checks.append(
                _check(
                    "ok",
                    title,
                    _("Points to the same address as the current name (%(addresses)s).") % {"addresses": listed},
                )
            )
        else:
            checks.append(
                _check(
                    "warning",
                    title,
                    _(
                        "Points to %(addresses)s. This server does not know that address as its own – behind a "
                        "router (NAT) that is normal. Rentalars cannot tell for sure whether it leads here; please "
                        "check."
                    )
                    % {"addresses": listed},
                )
            )
        if kind == CertificateKind.LETSENCRYPT and len(internal) == len(addresses):
            checks.append(
                _check(
                    "error",
                    _("Let's Encrypt"),
                    _(
                        "The name points to an address within a private network; Let's Encrypt cannot reach it "
                        "from the internet. Use your own certificate."
                    ),
                )
            )
    if not current.site.found:
        checks.append(
            _check("note", _("Ports"), _("Not checked: there is no NGINX site of the installation on this server."))
        )
    else:
        closed = [str(port) for port in (80, HTTPS_PORT) if not _listening(port)]
        if closed:
            checks.append(
                _check(
                    "warning",
                    _("Ports"),
                    _("Nothing answers on port %(ports)s of this server. Is NGINX running?")
                    % {"ports": ", ".join(closed)},
                )
            )
        else:
            checks.append(_check("ok", _("Ports"), _("NGINX answers on ports 80 and 443 of this server.")))
    if kind == CertificateKind.LETSENCRYPT:
        checks.append(
            _check(
                "note",
                _("Port 80 from the internet"),
                _(
                    "Let's Encrypt checks the name through port 80 from the internet. Whether the router lets it "
                    "through cannot be checked from here."
                ),
            )
        )
    return checks


# --- Preparing, exporting, recording ------------------------------------------------------------------------------


def files_dir(change: AddressChange) -> Path:
    """The folder with the uploaded certificate and key of a change."""
    return Path(settings.DATA_DIR) / FILES_FOLDER / change.token


def _write_private(path: Path, text: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "w", encoding="ascii") as target:
        target.write(text)
    os.chmod(path, 0o600)


def _write_files(change: AddressChange, chain_pem: str, key_pem: str) -> None:
    folder = files_dir(change)
    folder.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    folder.mkdir(mode=0o700, exist_ok=True)
    os.chmod(folder, 0o700)
    _write_private(folder / CERTIFICATE_FILE, chain_pem)
    # Encrypted like the password of a mailbox (crypto.py) – and readable by the service user only.
    _write_private(folder / KEY_FILE, encrypt_secret(key_pem))


def remove_files(change: AddressChange) -> None:
    """Delete the uploaded certificate and key of a change (after use, or when it is replaced)."""
    shutil.rmtree(files_dir(change), ignore_errors=True)


def latest() -> AddressChange | None:
    """The newest prepared change, whatever became of it."""
    return AddressChange.objects.select_related("prepared_by").first()


def prepare(
    user: Any,
    *,
    host: str,
    kind: str,
    email: str = "",
    redirect_old: bool = True,
    certificate: bytes = b"",
    private_key: bytes = b"",
    current: CurrentState | None = None,
) -> AddressChange:
    """Check and store a change of the address (ADM-016); an older open one is replaced.

    Raises:
        AddressError: Something entered cannot work; ``errors`` names the fields.
    """
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email

    if kind not in CertificateKind.values:
        raise AddressError({"certificate_kind": [_("Choose where the certificate comes from.")]})
    host = normalise_host(host, for_letsencrypt=kind == CertificateKind.LETSENCRYPT)
    current = current or current_state()
    errors: dict[str, list[str]] = {}
    email = (email or "").strip()
    if kind == CertificateKind.LETSENCRYPT:
        try:
            validate_email(email)
            if email.startswith("-"):  # certbot would take it for an option
                raise ValidationError(email)
        except ValidationError:
            errors["email"] = [_("Let's Encrypt needs an e-mail address for notices about the expiry.")]
    else:
        email = ""
    if kind == CertificateKind.PROXY and host == current.host:
        errors["host"] = [_("This is the current address already; there is nothing to change.")]
    report = CertificateReport()
    if kind == CertificateKind.OWN:
        report = check_certificate(certificate, private_key, host)
        if report.errors:
            errors["certificate"] = report.errors
    if errors:
        raise AddressError(errors)
    checks = run_checks(host, kind, current)
    if kind == CertificateKind.OWN:
        summary = _("Valid for %(names)s until %(date)s, issued by %(issuer)s.") % {
            "names": ", ".join(report.info["names"]),
            "date": _date(datetime.datetime.fromisoformat(report.info["not_after"])),
            "issuer": report.info["issuer"],
        }
        checks.append(_check("ok", pgettext("TLS", "Certificate"), summary))
        checks.extend(_check("warning", pgettext("TLS", "Certificate"), text) for text in report.warnings)
        checks.extend(_check("note", pgettext("TLS", "Certificate"), text) for text in report.notes)
    with transaction.atomic():
        for older in AddressChange.objects.select_for_update().filter(
            status__in=[AddressChangeStatus.PREPARED, AddressChangeStatus.FAILED]
        ):
            older.status = AddressChangeStatus.SUPERSEDED
            older.save(update_fields=["status"])
            remove_files(older)
        change = AddressChange(
            token=secrets.token_hex(8),
            host=host,
            certificate_kind=kind,
            email=email,
            redirect_old=bool(redirect_old) and host != current.host,
            previous_url=current.url,
            certificate_info=report.info,
            checks=checks,
            prepared_by=user if getattr(user, "is_authenticated", False) else None,
        )
        change.save()
        if kind == CertificateKind.OWN:
            _write_files(change, report.chain_pem, report.key_pem)
    return change


def discard(change: AddressChange) -> None:
    """Throw an open change away, with its files."""
    change.status = AddressChangeStatus.DISCARDED
    change.save(update_fields=["status"])
    remove_files(change)


def blocking_errors(change: AddressChange) -> list[str]:
    """The checks that make the command fail – shown so the operator knows before running it."""
    return [check["detail"] for check in change.checks if check.get("state") == "error"]


def steps(change: AddressChange) -> list[str]:
    """What the command will do, in order (ADM-016) – shown under the command."""
    host = change.host
    old = host_of(change.previous_url)
    result = [
        _(
            "Checks the prepared change again itself: the name and – for your own certificate – key, chain, names and validity."
        ),
        _("Backs up the configuration file, the NGINX site and the certificates to /etc/rentalars/address-backup/."),
    ]
    if change.certificate_kind == CertificateKind.LETSENCRYPT:
        result.append(
            _(
                "Requests a certificate for %(host)s from Let's Encrypt (installs certbot if it is missing); it "
                "renews itself. Port 80 must be reachable from the internet."
            )
            % {"host": host}
        )
    elif change.certificate_kind == CertificateKind.SELF_SIGNED:
        result.append(_("Creates a self-signed certificate for %(host)s, valid for 825 days.") % {"host": host})
    elif change.certificate_kind == CertificateKind.OWN:
        result.append(
            _("Installs your certificate and key in /etc/rentalars/tls/%(host)s/ – the key readable by root only.")
            % {"host": host}
        )
    else:
        result.append(_("Leaves the certificates as they are: the server in front must know the new name."))
    result.append(
        _("Sets the address in the configuration file to https://%(host)s and the name in the NGINX site.")
        % {"host": host}
    )
    if change.redirect_old and old and old != host:
        result.append(
            _(
                "Redirects the old address %(old)s to the new one – over HTTPS as long as the old certificate is "
                "valid for it."
            )
            % {"old": old}
        )
    result += [
        _("Checks the NGINX configuration, reloads NGINX and restarts Rentalars – a few seconds without access."),
        _("Checks that https://%(host)s answers. If any step fails, it puts everything back as it was.")
        % {"host": host},
        _("Records the result here."),
    ]
    return result


def export(token: str) -> dict[str, Any]:
    """The prepared change for the command on the server (``manage.py address_change export``).

    Raises:
        AddressChange.DoesNotExist: No open change has this token.
    """
    change = AddressChange.objects.select_related("prepared_by").get(
        token=token, status__in=[AddressChangeStatus.PREPARED, AddressChangeStatus.FAILED]
    )
    certificate = private_key = ""
    if change.certificate_kind == CertificateKind.OWN:
        folder = files_dir(change)
        certificate = (folder / CERTIFICATE_FILE).read_text(encoding="ascii")
        private_key = decrypt_secret((folder / KEY_FILE).read_text(encoding="ascii").strip())
    return {
        "token": change.token,
        "host": change.host,
        "certificate_kind": change.certificate_kind,
        "email": change.email,
        "redirect_old": change.redirect_old,
        "previous_url": change.previous_url,
        "prepared_by": str(change.prepared_by or ""),
        "prepared_at": change.prepared_at.isoformat(),
        "certificate": certificate,
        "private_key": private_key,
    }


def record(
    token: str, *, applied: bool, by: str, message: str = "", details: dict[str, Any] | None = None
) -> AddressChange:
    """Note the result of the command (``manage.py address_change record``).

    After a successful run the uploaded files are deleted: certificate and key
    are then in /etc/rentalars/tls/, and the data folder need not keep a copy.
    """
    with transaction.atomic():
        change = AddressChange.objects.select_for_update().get(token=token)
        change.status = AddressChangeStatus.APPLIED if applied else AddressChangeStatus.FAILED
        change.applied_at = timezone.now()
        change.applied_by = (by or "")[:100]
        change.result_message = (message or "")[:4000]
        change.result = details or {}
        change.save()
    if applied:
        remove_files(change)
    return change
