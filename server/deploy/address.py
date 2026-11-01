# SPDX-License-Identifier: GPL-3.0-or-later
"""The command "sudo rentalars address": apply a change of the server address (ADM-016).

    sudo rentalars address apply TOKEN             show the plan, ask, apply
    sudo rentalars address apply TOKEN --dry-run   only check and show the plan; nothing changes
    sudo rentalars address apply TOKEN --yes       do not ask

The change – new host name, where the certificate comes from, an uploaded
certificate with its key – is prepared in the browser under Einstellungen →
Serveradresse und Zertifikat, which shows exactly this command with its
TOKEN. The application never gets root rights; this command, run by the
operator via SSH, does what needs them:

 1. It reads the prepared change from the application (manage.py
    address_change export, run as the service user) and checks everything
    again itself – never trusting what it reads: host name, kind, e-mail
    address, the certificate with openssl (key matches, chain, name, validity).
 2. It backs up the configuration file, the NGINX site and /etc/rentalars/tls
    to /etc/rentalars/address-backup/<time>-<token>/.
 3. It gets the certificate: Let's Encrypt (certbot, HTTP check through port
    80), self-signed (openssl), or the uploaded one; installs it in
    /etc/rentalars/tls/<host>/ (the key readable by root only) – or leaves the
    certificates alone when a server in front encrypts.
 4. It writes the new name and certificate into the NGINX site and the
    address into the configuration file ([rentalars] url, from which the
    application also takes the host names it answers to). The old name can be
    kept as a redirect to the new one: over HTTP always, over HTTPS as long as
    the old certificate is valid for it.
 5. nginx -t, reload NGINX, restart Rentalars, and check that the new address
    answers with the new certificate.
 6. On any failure it puts every file back, reloads and restarts again, and
    says what went wrong. The result – success or the error – is recorded
    (manage.py address_change record) and shown on the settings page.

Run by the command "rentalars" (deploy/rentalars) with the system's Python,
isolated (python3 -I), as root. Only the standard library and openssl.
"""

from __future__ import annotations

import configparser
import contextlib
import datetime
import difflib
import fcntl
import ipaddress
import itertools
import json
import os
import re
import shutil
import socket
import ssl
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

KINDS = ("letsencrypt", "selfsigned", "own", "proxy")


def kind_text(kind: str) -> str:
    """Where the certificate comes from, in the operator's language."""
    return {
        "letsencrypt": "Let's Encrypt",
        "selfsigned": t("selbst erstelltes Zertifikat", "self-signed certificate"),
        "own": t("eigenes Zertifikat", "own certificate"),
        "proxy": t(
            "ein Server davor verschlüsselt (Zertifikate bleiben)", "a server in front encrypts (certificates stay)"
        ),
    }[kind]


#: Patterns are used with fullmatch only: "$" would let a trailing line break through. The local part of
#: an e-mail address never starts with "-", so that certbot cannot take it for an option.
TOKEN_PATTERN = re.compile(r"[0-9a-f]{16,32}")
LABEL_PATTERN = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?")
EMAIL_PATTERN = re.compile(
    r"[A-Za-z0-9.!#%&*+/=?^_`{|}~][A-Za-z0-9.!#%&*+/=?^_`{|}~-]*@[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}"
)
PEM_BLOCK = re.compile(r"-----BEGIN CERTIFICATE-----\r?\n[A-Za-z0-9+/=\r\n]+-----END CERTIFICATE-----")
#: What the export may be at most; a certificate chain and a key fit easily.
MAX_EXPORT_BYTES = 1_000_000
#: Self-signed certificates: as long as install.sh makes them.
SELF_SIGNED_DAYS = 825
#: The section of the NGINX site with the old names that point to the new one.
REDIRECTS_BEGIN = "# >>> Old addresses, redirected to the current one (sudo rentalars address, ADM-016)"
REDIRECTS_END = "# <<< Old addresses"
REDIRECT_MARK = "# redirect: "


class AddressFailureError(Exception):
    """Something does not fit; the text says what, in the operator's language."""


@dataclass(frozen=True)
class Paths:
    """Where things are on a server installed by deploy/install.sh."""

    config_file: Path = Path(os.environ.get("RENTALARS_CONFIG") or "/etc/rentalars/rentalars.conf")
    config_dir: Path = Path("/etc/rentalars")
    nginx_site: Path = Path("/etc/nginx/sites-available/rentalars")
    acme_root: Path = Path("/var/www/rentalars-acme")
    letsencrypt_live: Path = Path("/etc/letsencrypt/live")
    app_dir: Path = Path("/opt/rentalars/app")
    venv_python: Path = Path("/opt/rentalars/venv/bin/python")
    #: In /run, which only root may write to – not /run/lock, which everybody may (ADM-016).
    lock_file: Path = Path("/run/rentalars-address.lock")
    service_user: str = "rentalars"

    @property
    def tls_dir(self) -> Path:
        """The certificates Rentalars installs itself."""
        return self.config_dir / "tls"

    @property
    def backup_root(self) -> Path:
        """Where the files from before each change are kept."""
        return self.config_dir / "address-backup"

    @property
    def lib(self) -> Path:
        """The shared helpers of the server scripts."""
        return self.app_dir / "deploy" / "lib.sh"


@dataclass(frozen=True)
class Change:
    """A prepared change, checked."""

    token: str
    host: str
    kind: str
    email: str
    redirect_old: bool
    prepared_by: str
    certificate: str
    private_key: str


# --- Output in the style of lib.sh ----------------------------------------------------------------------


def operator_language() -> str:
    """UIX-029: ``de`` when RENTALARS_LANG, else LC_ALL, LC_MESSAGES or LANG starts with "de"; else ``en`` (lib.sh)."""
    for name in ("RENTALARS_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(name, "")
        if value:
            return "de" if value.startswith("de") else "en"
    return "en"


def shown(text: str) -> str:
    """An untrusted text as it may appear on root's terminal: control characters (C0, C1, …) escaped."""
    return "".join(
        character if character.isprintable() else character.encode("unicode_escape").decode("ascii")
        for character in text
    )


def t(german: str, english: str) -> str:
    """The German or the English text, as the operator reads (lib.sh, t)."""
    return german if operator_language() == "de" else english


def say(text: str) -> None:
    """A heading."""
    print(f"\n\033[1m==> {text}\033[0m", flush=True)


def note(text: str = "") -> None:
    """A line under a heading."""
    print(f"    {text}", flush=True)


def warn(text: str) -> None:
    """Something to know that does not stop the command."""
    print(f"\n\033[1;33m{t('Achtung:', 'Warning:')}\033[0m {text}", file=sys.stderr, flush=True)


def error(text: str) -> None:
    """What stopped the command."""
    print(f"\n\033[1;31m{t('Fehler:', 'Error:')}\033[0m {text}", file=sys.stderr, flush=True)


# --- Checks of what the application hands over --------------------------------------------------------------


def valid_host(host: str) -> bool:
    """A host name as the settings page stores it: lower case, ASCII (xn--), no IP address, no port."""
    if not isinstance(host, str) or not host or len(host) > 253 or host != host.lower():
        return False
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return False
    labels = host.split(".")
    return host != "localhost" and all(LABEL_PATTERN.fullmatch(label) for label in labels) and not labels[-1].isdigit()


def host_of(url: str) -> str:
    """The host part of an address."""
    return (urlsplit(url or "").hostname or "").lower()


def parse_change(text: str, token: str) -> Change:
    """Check the export of the application; nothing in it is trusted (ADM-016)."""
    if len(text.encode("utf-8")) > MAX_EXPORT_BYTES:
        raise AddressFailureError(
            t(
                "Die vorbereitete Änderung ist unerwartet groß; sie wird nicht verwendet.",
                "The prepared change is unexpectedly large; it is not used.",
            )
        )
    try:
        data = json.loads(text)
    except ValueError:
        raise AddressFailureError(
            t(
                "Die Anwendung hat keine lesbare Änderung geliefert.",
                "The application did not deliver a readable change.",
            )
        ) from None
    if not isinstance(data, dict):
        raise AddressFailureError(
            t(
                "Die Anwendung hat keine lesbare Änderung geliefert.",
                "The application did not deliver a readable change.",
            )
        )

    def text_of(name: str) -> str:
        value = data.get(name, "")
        if not isinstance(value, str):
            raise AddressFailureError(
                t(f"Die vorbereitete Änderung ist fehlerhaft ({name}).", f"The prepared change is faulty ({name}).")
            )
        return value

    if text_of("token") != token:
        raise AddressFailureError(
            t(
                "Die Anwendung hat eine andere Änderung geliefert als die verlangte.",
                "The application delivered another change than the one asked for.",
            )
        )
    host = text_of("host")
    if not valid_host(host):
        raise AddressFailureError(
            t(f"'{shown(host[:80])}' ist kein gültiger Hostname.", f"'{shown(host[:80])}' is not a valid host name.")
        )
    kind = text_of("certificate_kind")
    if kind not in KINDS:
        raise AddressFailureError(
            t(
                f"Unbekannte Herkunft des Zertifikats: {shown(kind[:40])}",
                f"Unknown source of the certificate: {shown(kind[:40])}",
            )
        )
    email = text_of("email")
    if kind == "letsencrypt" and not EMAIL_PATTERN.fullmatch(email):
        raise AddressFailureError(
            t("Für Let's Encrypt fehlt eine gültige E-Mail-Adresse.", "Let's Encrypt needs a valid e-mail address.")
        )
    if kind == "letsencrypt" and "." not in host:
        raise AddressFailureError(
            t(
                "Let's Encrypt stellt nur Zertifikate für Namen im öffentlichen DNS aus.",
                "Let's Encrypt only issues certificates for names in the public DNS.",
            )
        )
    certificate, private_key = text_of("certificate"), text_of("private_key")
    if kind == "own":
        if not PEM_BLOCK.search(certificate):
            raise AddressFailureError(
                t(
                    "Die vorbereitete Änderung enthält kein Zertifikat im PEM-Format.",
                    "The prepared change contains no certificate in PEM format.",
                )
            )
        if "PRIVATE KEY-----" not in private_key or "CERTIFICATE" in private_key:
            raise AddressFailureError(
                t(
                    "Die vorbereitete Änderung enthält keinen privaten Schlüssel im PEM-Format.",
                    "The prepared change contains no private key in PEM format.",
                )
            )
    redirect_old = data.get("redirect_old", False)
    prepared_by = re.sub(r"[^\w .@+-]", "", text_of("prepared_by"))[:80]
    return Change(
        token,
        host,
        kind,
        email if kind == "letsencrypt" else "",
        redirect_old is True,
        prepared_by,
        certificate if kind == "own" else "",
        private_key if kind == "own" else "",
    )


def split_pem(text: str) -> list[str]:
    """The certificates of a PEM file, each as one block."""
    return [match.group(0).replace("\r\n", "\n") + "\n" for match in PEM_BLOCK.finditer(text)]


Runner = Callable[..., subprocess.CompletedProcess[str]]


def run_command(
    args: Sequence[str], *, check: bool = True, input_text: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run a program without a shell; its output is captured."""
    result = subprocess.run(  # noqa: S603 - fixed programs, arguments checked before
        list(args), input=input_text, capture_output=True, text=True, check=False
    )
    if check and result.returncode != 0:
        message = (result.stderr or result.stdout).strip().splitlines()
        raise AddressFailureError(
            t("{program} meldet: {text}", "{program} reports: {text}").format(
                program=args[0], text=shown(" ".join(message[-3:])) or t("Fehler ", "error ") + str(result.returncode)
            )
        )
    return result


def _openssl_date(text: str) -> datetime.datetime:
    value = text.split("=", 1)[1].strip()
    return datetime.datetime.strptime(" ".join(value.split()), "%b %d %H:%M:%S %Y %Z").replace(tzinfo=datetime.UTC)


def check_certificate_files(certificate: Path, private_key: Path, host: str, run: Runner = run_command) -> list[str]:
    """Check certificate and key with openssl before NGINX gets them; return warnings, raise :class:`AddressFailureError`."""
    blocks = split_pem(certificate.read_text(encoding="ascii", errors="replace"))
    if not blocks:
        raise AddressFailureError(
            t(
                "Die Zertifikatsdatei enthält kein Zertifikat im PEM-Format.",
                "The certificate file contains no certificate in PEM format.",
            )
        )
    leaf_key = run(["openssl", "x509", "-in", str(certificate), "-noout", "-pubkey"], check=False)
    own_key = run(["openssl", "pkey", "-in", str(private_key), "-pubout", "-passin", "pass:"], check=False)
    if own_key.returncode != 0:
        raise AddressFailureError(
            t(
                "Der private Schlüssel lässt sich nicht lesen (PEM, ohne Passwort).",
                "The private key cannot be read (PEM, without password).",
            )
        )
    if leaf_key.returncode != 0 or leaf_key.stdout.strip() != own_key.stdout.strip():
        raise AddressFailureError(
            t(
                "Der Schlüssel passt nicht zum ersten Zertifikat der Datei.",
                "The key does not match the first certificate in the file.",
            )
        )
    names = run(["openssl", "x509", "-in", str(certificate), "-noout", "-checkhost", host], check=False)
    if "does match" not in names.stdout or "NOT match" in names.stdout:
        raise AddressFailureError(
            t(f"Das Zertifikat gilt nicht für {host}.", f"The certificate is not valid for {host}.")
        )
    with tempfile.TemporaryDirectory() as work:
        parts = []
        for index, block in enumerate(blocks):
            part = Path(work) / f"{index}.pem"
            part.write_text(block, encoding="ascii")
            parts.append(part)
            dates = run(["openssl", "x509", "-in", str(part), "-noout", "-startdate", "-enddate"], check=False)
            if dates.returncode != 0:
                raise AddressFailureError(
                    t(
                        f"Zertifikat {index + 1} der Datei lässt sich nicht lesen.",
                        f"Certificate {index + 1} in the file cannot be read.",
                    )
                )
            start, end = (_openssl_date(line) for line in dates.stdout.strip().splitlines()[:2])
            now = datetime.datetime.now(datetime.UTC)
            if start > now:
                raise AddressFailureError(
                    t(
                        f"Zertifikat {index + 1} der Datei gilt erst ab {start:%d.%m.%Y}.",
                        f"Certificate {index + 1} in the file is only valid from {start:%d/%m/%Y}.",
                    )
                )
            if end < now:
                raise AddressFailureError(
                    t(
                        f"Zertifikat {index + 1} der Datei ist am {end:%d.%m.%Y} abgelaufen.",
                        f"Certificate {index + 1} in the file expired on {end:%d/%m/%Y}.",
                    )
                )
        # The chain: every certificate is signed by the next one.
        for current, issuer in itertools.pairwise(parts):
            linked = run(
                [
                    "openssl",
                    "verify",
                    "-no-CAfile",
                    "-no-CApath",
                    "-partial_chain",
                    "-trusted",
                    str(issuer),
                    str(current),
                ],
                check=False,
            )
            if linked.returncode != 0:
                raise AddressFailureError(
                    t(
                        "Die Kette ist unterbrochen: ein Zertifikat ist nicht vom folgenden ausgestellt.",
                        "The chain is broken: a certificate was not issued by the next one.",
                    )
                )
    warnings = []
    end = run(["openssl", "x509", "-in", str(certificate), "-noout", "-checkend", str(30 * 86400)], check=False)
    if end.returncode != 0:
        warnings.append(
            t("Das Zertifikat läuft in weniger als 30 Tagen ab.", "The certificate expires in less than 30 days.")
        )
    return warnings


# --- Configuration file and NGINX site ------------------------------------------------------------------------


def read_url(config_file: Path) -> str:
    """``[rentalars] url`` of the configuration file."""
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(config_file, encoding="utf-8")
    return parser.get("rentalars", "url", fallback="")


@dataclass
class Site:
    """What the NGINX site says: text, names, certificate of the application's server."""

    text: str
    certificate: str = ""
    private_key: str = ""
    names: list[str] = field(default_factory=list)

    @property
    def ipv6(self) -> bool:
        """Whether the site listens on IPv6 (render_nginx_site removes it on servers without)."""
        return "listen [::]" in self.text


def split_site(text: str) -> tuple[str, str]:
    """The site without the section of old addresses, and that section's content."""
    begin, end = text.find(REDIRECTS_BEGIN), text.find(REDIRECTS_END)
    if begin < 0 or end < begin:
        return text, ""
    section = text[begin + len(REDIRECTS_BEGIN) : end]
    rest = text[:begin].rstrip("\n") + "\n" + text[end + len(REDIRECTS_END) :].lstrip("\n")
    return rest, section


def read_site(path: Path) -> Site | None:
    """The NGINX site of the installation, or ``None`` without one."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    main, _section = split_site(text)
    site = Site(text)
    certificate = re.search(r"^\s*ssl_certificate\s+([^;]+);", main, re.MULTILINE)
    key = re.search(r"^\s*ssl_certificate_key\s+([^;]+);", main, re.MULTILINE)
    site.certificate = certificate.group(1).strip() if certificate else ""
    site.private_key = key.group(1).strip() if key else ""
    for match in re.finditer(r"^\s*server_name\s+([^;]+);", main, re.MULTILINE):
        site.names += [name for name in match.group(1).split() if name not in site.names]
    return site


def redirect_block(
    old_host: str, target: str, *, certificate: str, private_key: str, ipv6: bool, acme_root: Path
) -> str:
    """The servers of NGINX that send an old name to the new address."""
    six80 = "    listen [::]:80;\n" if ipv6 else ""
    block = (
        f"{REDIRECT_MARK}{old_host}\n"
        "server {\n"
        "    listen 80;\n"
        f"{six80}"
        f"    server_name {old_host};\n"
        "    location /.well-known/acme-challenge/ {\n"
        f"        root {acme_root};\n"
        "    }\n"
        "    location / {\n"
        f"        return 301 https://{target}$request_uri;\n"
        "    }\n"
        "}\n"
    )
    if certificate and private_key:
        six443 = "    listen [::]:443 ssl;\n" if ipv6 else ""
        block += (
            "server {\n"
            "    listen 443 ssl;\n"
            f"{six443}"
            f"    server_name {old_host};\n"
            f"    ssl_certificate     {certificate};\n"
            f"    ssl_certificate_key {private_key};\n"
            "    server_tokens off;\n"
            f"    return 301 https://{target}$request_uri;\n"
            "}\n"
        )
    return block


def edit_site(
    text: str,
    *,
    old_host: str,
    new_host: str,
    certificate: str | None = None,
    private_key: str | None = None,
    redirect: str | None = None,
    acme_root: Path = Paths.acme_root,
) -> str:
    """The NGINX site with the new name, certificate and redirects (ADM-016).

    Only the lines of the application's servers that name ``old_host`` and the
    certificate lines that name the current files change; whatever else an
    administrator put into the site stays. ``redirect`` is a ready block from
    :func:`redirect_block` for the old name, or ``None``.

    Raises:
        AddressFailureError: The site does not name the old host (it was changed by hand).
    """
    main, section = split_site(text)
    site = read_site_text(main)
    if old_host != new_host:
        replaced = 0

        def rename(match: re.Match[str]) -> str:
            nonlocal replaced
            names = match.group(2).split()
            if old_host not in names:
                return match.group(0)
            replaced += 1
            renamed: list[str] = []
            for name in names:
                name = new_host if name == old_host else name
                if name not in renamed:
                    renamed.append(name)
            return f"{match.group(1)}{' '.join(renamed)};"

        main = re.sub(r"^(\s*server_name\s+)([^;]+);", rename, main, flags=re.MULTILINE)
        if not replaced:
            raise AddressFailureError(
                t(
                    f"In der NGINX-Konfiguration steht der bisherige Name {old_host} nicht bei server_name. "
                    "Sie wurde wohl von Hand geändert; bitte die Datei prüfen (sudo rentalars nginx-site).",
                    f"The NGINX configuration does not name the previous name {old_host} at server_name. "
                    "It was probably changed by hand; please check the file (sudo rentalars nginx-site).",
                )
            )
    if certificate is not None and private_key is not None:
        if not site.certificate:
            raise AddressFailureError(
                t(
                    "Die NGINX-Konfiguration hat kein Zertifikat (ssl_certificate); HTTPS fehlt dort.",
                    "The NGINX configuration has no certificate (ssl_certificate); HTTPS is missing there.",
                )
            )
        main = re.sub(
            rf"^(\s*ssl_certificate\s+){re.escape(site.certificate)};",
            lambda match: f"{match.group(1)}{certificate};",
            main,
            flags=re.MULTILINE,
        )
        main = re.sub(
            rf"^(\s*ssl_certificate_key\s+){re.escape(site.private_key)};",
            lambda match: f"{match.group(1)}{private_key};",
            main,
            flags=re.MULTILINE,
        )
    # The old addresses: one block each, all pointing to the new one.
    blocks: dict[str, str] = {}
    for part in section.split(REDIRECT_MARK)[1:]:
        name = part.split("\n", 1)[0].strip()
        if valid_host(name):
            blocks[name] = REDIRECT_MARK + part.strip("\n") + "\n"
    blocks.pop(new_host, None)
    for name, block in list(blocks.items()):
        blocks[name] = re.sub(
            r"return 301 https://[^$\s]+\$request_uri;", f"return 301 https://{new_host}$request_uri;", block
        )
    if redirect is not None and old_host != new_host:
        blocks[old_host] = redirect
    if not blocks:
        return main
    body = "\n".join(blocks[name] for name in sorted(blocks))
    return f"{main.rstrip(chr(10))}\n\n{REDIRECTS_BEGIN}\n{body}{REDIRECTS_END}\n"


def read_site_text(text: str) -> Site:
    """Like :func:`read_site`, for a text."""
    site = Site(text)
    certificate = re.search(r"^\s*ssl_certificate\s+([^;]+);", text, re.MULTILINE)
    key = re.search(r"^\s*ssl_certificate_key\s+([^;]+);", text, re.MULTILINE)
    site.certificate = certificate.group(1).strip() if certificate else ""
    site.private_key = key.group(1).strip() if key else ""
    return site


# --- Applying -------------------------------------------------------------------------------------------------------


def write_file(path: Path, text: str, mode: int) -> None:
    """Write a file in one step (a temporary file next to it, then renamed), with its mode."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            target.write(text)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def replace_content(path: Path, text: str) -> None:
    """Write into an existing file, so that it keeps its owner and mode (configuration, NGINX site)."""
    with open(path, "w", encoding="utf-8") as target:
        target.write(text)


@dataclass
class Applier:
    """Applies one checked change, with backup and rollback (ADM-016)."""

    change: Change
    paths: Paths = field(default_factory=Paths)
    run: Runner = run_command
    by: str = "root"
    #: Without systemd (a container, a chroot) nothing can be reloaded or restarted.
    services: bool = True
    backup_dir: Path | None = None
    url_before: str = ""
    site_before: Site | None = None
    warnings: list[str] = field(default_factory=list)
    #: The certificate NGINX will present for the new name, to compare after the restart.
    expected_certificate: str = ""
    redirect_https: bool = False

    # --- What there is now and what will be ---------------------------------------------------------------

    def read_current(self) -> None:
        """The address and the NGINX site before the change."""
        if not self.paths.config_file.is_file():
            raise AddressFailureError(f"{self.paths.config_file} fehlt. Ist Rentalars installiert?")
        self.url_before = read_url(self.paths.config_file)
        if not host_of(self.url_before):
            raise AddressFailureError(
                t(
                    f"In {self.paths.config_file} steht unter [rentalars] keine Adresse (url).",
                    f"{self.paths.config_file} has no address (url) under [rentalars].",
                )
            )
        self.site_before = read_site(self.paths.nginx_site)
        if self.site_before is None and self.change.kind != "proxy":
            raise AddressFailureError(
                t(
                    f"{self.paths.nginx_site} fehlt: Ohne das NGINX der Installation lässt sich nur der Name ändern "
                    '("Ein Server davor verschlüsselt").',
                    f"{self.paths.nginx_site} is missing: without the NGINX of the installation only the name can "
                    'change ("A server in front encrypts").',
                )
            )
        if self.site_before is not None and self.change.kind != "proxy" and not self.site_before.certificate:
            raise AddressFailureError(
                t(
                    "Die NGINX-Konfiguration hat kein Zertifikat (ssl_certificate); HTTPS fehlt dort.",
                    "The NGINX configuration has no certificate (ssl_certificate); HTTPS is missing there.",
                )
            )

    @property
    def old_host(self) -> str:
        """The name before the change."""
        return host_of(self.url_before)

    def target_files(self) -> tuple[str, str]:
        """Certificate and key the application's server will use."""
        host = self.change.host
        if self.change.kind == "letsencrypt":
            live = self.paths.letsencrypt_live / host
            return str(live / "fullchain.pem"), str(live / "privkey.pem")
        if self.change.kind in ("selfsigned", "own"):
            folder = self.paths.tls_dir / host
            return str(folder / "certificate.pem"), str(folder / "private-key.pem")
        return (self.site_before.certificate, self.site_before.private_key) if self.site_before else ("", "")

    def old_certificate_fits(self) -> bool:
        """Whether the current certificate may serve the redirect of the old name over HTTPS."""
        site = self.site_before
        if site is None or not site.certificate or not Path(site.certificate).is_file():
            return False
        # Two calls: with -checkend, openssl does not print the result of -checkhost.
        names = self.run(
            ["openssl", "x509", "-in", site.certificate, "-noout", "-checkhost", self.old_host], check=False
        )
        valid = self.run(["openssl", "x509", "-in", site.certificate, "-noout", "-checkend", "86400"], check=False)
        return names.returncode == 0 and "does match" in names.stdout and valid.returncode == 0

    def redirect(self) -> str | None:
        """The NGINX block of the old name, if it is redirected."""
        site = self.site_before
        if site is None or not self.change.redirect_old or self.old_host in ("", self.change.host):
            return None
        self.redirect_https = self.old_certificate_fits()
        return redirect_block(
            self.old_host,
            self.change.host,
            certificate=site.certificate if self.redirect_https else "",
            private_key=site.private_key if self.redirect_https else "",
            ipv6=site.ipv6,
            acme_root=self.paths.acme_root,
        )

    def new_site(self, *, keep_certificate: bool = False) -> str:
        """The NGINX site after the change."""
        assert self.site_before is not None
        certificate, private_key = (
            (None, None) if keep_certificate or self.change.kind == "proxy" else self.target_files()
        )
        return edit_site(
            self.site_before.text,
            old_host=self.old_host,
            new_host=self.change.host,
            certificate=certificate,
            private_key=private_key,
            redirect=self.redirect(),
            acme_root=self.paths.acme_root,
        )

    def plan(self) -> list[str]:
        """What the command will do, for the operator."""
        host, kind = self.change.host, self.change.kind
        certificate, private_key = self.target_files()
        lines = [
            t("Adresse:      ", "Address:      ") + f"{self.url_before}  →  https://{host}",
            t("Zertifikat:   ", "Certificate:  ") + kind_text(kind),
        ]
        if kind == "letsencrypt":
            lines.append(
                t(
                    f"              certbot (Webroot, Port 80) für {host}, E-Mail {self.change.email}",
                    f"              certbot (webroot, port 80) for {host}, e-mail {self.change.email}",
                )
            )
        if certificate:
            lines.append(f"              {certificate}")
            lines.append(f"              {private_key}")
        if self.site_before is None:
            lines.append(
                t(
                    "NGINX:        keine Konfiguration der Installation – nur die Adresse ändert sich",
                    "NGINX:        no configuration of the installation – only the address changes",
                )
            )
        elif self.change.redirect_old and self.old_host not in ("", host):
            how = (
                t("über HTTP und HTTPS", "over HTTP and HTTPS")
                if self.old_certificate_fits()
                else t(
                    "über HTTP (das alte Zertifikat passt nicht mehr)", "over HTTP (the old certificate no longer fits)"
                )
            )
            lines.append(
                t(
                    f"Alte Adresse: {self.old_host} leitet auf die neue weiter, {how}",
                    f"Old address:  {self.old_host} redirects to the new one, {how}",
                )
            )
        lines.append(
            t(
                f"Sicherung:    {self.paths.backup_root}/<Zeit>-{self.change.token[:8]}/",
                f"Backup:       {self.paths.backup_root}/<time>-{self.change.token[:8]}/",
            )
        )
        if self.change.prepared_by:
            lines.append(
                t(f"Vorbereitet:  von {self.change.prepared_by}", f"Prepared:     by {self.change.prepared_by}")
            )
        return lines

    def site_diff(self) -> list[str]:
        """How the NGINX site will change (- now, + new)."""
        if self.site_before is None:
            return []
        try:
            new = self.new_site()
        except AddressFailureError as error:
            return [t(f"(nicht darstellbar: {error})", f"(cannot be shown: {error})")]
        return list(
            difflib.unified_diff(
                self.site_before.text.splitlines(), new.splitlines(), "bisher", "neu", lineterm="", n=1
            )
        )

    # --- Changing the server ------------------------------------------------------------------------------------

    def back_up(self) -> Path:
        """Copy configuration, NGINX site and certificates aside, readable by root only."""
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        folder = self.paths.backup_root / f"{stamp}-{self.change.token[:8]}"
        self.paths.backup_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        folder.mkdir(mode=0o700)
        shutil.copy2(self.paths.config_file, folder / "rentalars.conf")
        if self.paths.nginx_site.is_file():
            shutil.copy2(self.paths.nginx_site, folder / "nginx-site")
        if self.paths.tls_dir.is_dir():
            shutil.copytree(self.paths.tls_dir, folder / "tls", symlinks=True)
        self.backup_dir = folder
        return folder

    def restore(self) -> None:
        """Put every file back as it was before the change."""
        folder = self.backup_dir
        if folder is None:
            return
        shutil.copyfile(folder / "rentalars.conf", self.paths.config_file)
        if (folder / "nginx-site").is_file():
            shutil.copyfile(folder / "nginx-site", self.paths.nginx_site)
        if self.paths.tls_dir.is_dir():
            shutil.rmtree(self.paths.tls_dir)
        if (folder / "tls").is_dir():
            shutil.copytree(folder / "tls", self.paths.tls_dir, symlinks=True)

    def install_certificate(self) -> None:
        """Get or install the certificate of the new name (not for Let's Encrypt, see :meth:`letsencrypt`)."""
        certificate, private_key = (Path(path) for path in self.target_files())
        if self.change.kind == "own":
            self.paths.tls_dir.mkdir(mode=0o750, exist_ok=True)
            certificate.parent.mkdir(mode=0o750, exist_ok=True)
            write_file(certificate, "".join(split_pem(self.change.certificate)), 0o644)
            write_file(private_key, self.change.private_key.strip() + "\n", 0o600)
        elif self.change.kind == "selfsigned":
            self.paths.tls_dir.mkdir(mode=0o750, exist_ok=True)
            certificate.parent.mkdir(mode=0o750, exist_ok=True)
            host = self.change.host
            self.run(
                [
                    "openssl", "req", "-x509", "-newkey", "rsa:3072", "-nodes", "-days", str(SELF_SIGNED_DAYS),
                    "-subj", f"/CN={host}", "-addext", f"subjectAltName=DNS:{host}",
                    "-keyout", str(private_key), "-out", str(certificate),
                ]
            )  # fmt: skip
            os.chmod(private_key, 0o600)
            os.chmod(certificate, 0o644)

    def letsencrypt(self) -> None:
        """NGINX answers for the new name on port 80 first, then certbot gets the certificate."""
        if shutil.which("certbot") is None:
            note("certbot fehlt; es wird installiert.")
            self.run(["apt-get", "install", "-y", "-qq", "--no-install-recommends", "certbot"])
        self.write_site(self.new_site(keep_certificate=True))
        self.reload_nginx()
        self.paths.acme_root.mkdir(mode=0o755, parents=True, exist_ok=True)
        self.run(
            [
                "certbot", "certonly", "--non-interactive", "--agree-tos", f"--email={self.change.email}",
                "--webroot", "--webroot-path", str(self.paths.acme_root), "-d", self.change.host,
                "--cert-name", self.change.host, "--deploy-hook", "systemctl reload nginx",
            ]
        )  # fmt: skip

    def write_site(self, text: str) -> None:
        """Write the NGINX site and let NGINX check it."""
        replace_content(self.paths.nginx_site, text)
        # Not adapt_nginx_site: the lines of the application's servers keep their form, and the redirect
        # servers listen without HTTP/2 on purpose – NGINX 1.24 warns when a second server repeats "http2".
        self.run(["nginx", "-t", "-q"])

    def reload_nginx(self) -> None:
        """Reload NGINX (start it if it is not running)."""
        if self.services:
            self.run(["systemctl", "reload-or-restart", "nginx"])

    def set_url(self) -> None:
        """``[rentalars] url`` – the application takes its host names from it, too (ALLOWED_HOSTS)."""
        self.run(
            [
                "bash", "-c", 'source "$1"; config_set "$2" rentalars url "$3"', "address",
                str(self.paths.lib), str(self.paths.config_file), f"https://{self.change.host}",
            ]
        )  # fmt: skip

    def restart_rentalars(self) -> None:
        """Restart the application: the new address counts from its next start on (links in mails too)."""
        if self.services:
            self.run(["systemctl", "restart", "rentalars"])

    def application_answers(self) -> bool:
        """The application answers on its socket for the new name (lib.sh, application_answers)."""
        result = self.run(
            ["bash", "-c", 'source "$1"; application_answers', "address", str(self.paths.lib)], check=False
        )
        return result.returncode == 0

    def https_answers(self) -> str:
        """Ask NGINX for the login page under the new name; return what is wrong, or ``""``."""
        expected = ""
        if self.expected_certificate and Path(self.expected_certificate).is_file():
            blocks = split_pem(Path(self.expected_certificate).read_text(encoding="ascii", errors="replace"))
            expected = blocks[0] if blocks else ""
        problem = ""
        for _attempt in range(10):
            problem = https_check(self.change.host, expected)
            if not problem:
                return ""
            time.sleep(2)
        return problem

    def apply(self) -> None:
        """Do it; on any failure put everything back and raise :class:`AddressFailureError`."""
        self.back_up()
        note(t(f"Sicherung: {self.backup_dir}", f"Backup: {self.backup_dir}"))
        try:
            if self.change.kind == "letsencrypt":
                say(t("Zertifikat von Let's Encrypt", "Certificate from Let's Encrypt"))
                self.letsencrypt()
            elif self.change.kind in ("selfsigned", "own"):
                say(t("Zertifikat", "Certificate"))
                self.install_certificate()
            self.expected_certificate = self.target_files()[0]
            if self.site_before is not None:
                say("NGINX")
                self.write_site(self.new_site())
            say(t("Konfigurationsdatei", "Configuration file"))
            self.set_url()
            if not self.services:
                warn(
                    t(
                        "systemd läuft hier nicht (Container oder chroot): NGINX und Rentalars werden nicht neu "
                        "geladen, und die neue Adresse wird nicht geprüft.",
                        "systemd is not running here (container or chroot): NGINX and Rentalars are not reloaded, "
                        "and the new address is not checked.",
                    )
                )
                return
            say(t("NGINX neu laden, Rentalars neu starten", "Reloading NGINX, restarting Rentalars"))
            self.reload_nginx()
            self.restart_rentalars()
            if not self.application_answers():
                raise AddressFailureError(
                    t(
                        "Rentalars antwortet nach dem Neustart nicht. Die Meldungen: journalctl -u rentalars",
                        "Rentalars does not answer after the restart. The messages: journalctl -u rentalars",
                    )
                )
            if self.site_before is not None:
                problem = self.https_answers()
                if problem:
                    raise AddressFailureError(problem)
        except (AddressFailureError, OSError, subprocess.SubprocessError) as error:
            self.roll_back()
            raise AddressFailureError(
                t(f"{error} – alles wurde zurückgesetzt.", f"{error} – everything was put back.")
            ) from error

    def roll_back(self) -> None:
        """Files back, NGINX reloaded, Rentalars restarted – as before the command."""
        say(t("Zurücksetzen", "Putting everything back"))
        try:
            self.restore()
        except OSError as error:
            warn(
                t(
                    f"Nicht alles ließ sich zurückkopieren ({error}). Die Sicherung liegt in {self.backup_dir}.",
                    f"Not everything could be copied back ({error}). The backup is in {self.backup_dir}.",
                )
            )
        if not self.services:
            return
        if self.paths.nginx_site.is_file():
            if self.run(["nginx", "-t", "-q"], check=False).returncode == 0:
                self.run(["systemctl", "reload-or-restart", "nginx"], check=False)
            else:
                warn(
                    t(
                        f"NGINX nimmt auch die alte Konfiguration nicht an; bitte prüfen. Die Sicherung: {self.backup_dir}",
                        f"NGINX does not accept the old configuration either; please check. The backup: {self.backup_dir}",
                    )
                )
        self.run(["systemctl", "restart", "rentalars"], check=False)
        if not self.application_answers():
            warn(
                t(
                    "Rentalars antwortet auch nach dem Zurücksetzen nicht. Die Meldungen: journalctl -u rentalars",
                    "Rentalars does not answer after putting everything back either. The messages: journalctl -u rentalars",
                )
            )


def https_check(host: str, expected_pem: str, port: int = 443) -> str:
    """The login page through NGINX on this server under ``host``; ``""`` if it answers with the expected certificate."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        with (
            socket.create_connection(("127.0.0.1", port), timeout=10) as connection,
            context.wrap_socket(connection, server_hostname=host) as tls,
        ):
            presented = tls.getpeercert(binary_form=True) or b""
            request = (
                f"GET /login/ HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\nUser-Agent: rentalars-address\r\n\r\n"
            )
            tls.sendall(request.encode("ascii"))
            answer = tls.recv(200).decode("latin-1", errors="replace")
    except (OSError, ssl.SSLError) as error:
        return f"https://{host} antwortet auf diesem Server nicht ({error})."
    if expected_pem and presented != ssl.PEM_cert_to_DER_cert(expected_pem):
        return t(
            f"NGINX zeigt für {host} nicht das neue Zertifikat.",
            f"NGINX does not present the new certificate for {host}.",
        )
    status = answer.split(" ", 2)[1] if answer.count(" ") >= 2 else ""
    if status not in ("200", "302"):
        return f"https://{host}/login/ antwortet mit {status or 'nichts Lesbarem'}."
    return ""


# --- Talking to the application ----------------------------------------------------------------------------------


def manage(paths: Paths, run: Runner, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """A management command of the application, as the service user (lib.sh, manage)."""
    return run(
        [
            "runuser", "-u", paths.service_user, "--", "env", f"RENTALARS_CONFIG={paths.config_file}",
            f"RENTALARS_LANG={operator_language()}",
            str(paths.venv_python), str(paths.app_dir / "manage.py"), *arguments,
        ],
        check=check,
    )  # fmt: skip


def load_change(paths: Paths, run: Runner, token: str) -> Change:
    """Read the prepared change from the application and check it."""
    result = manage(paths, run, "address_change", "export", token, check=False)
    if result.returncode != 0:
        lines = (result.stderr or result.stdout).strip().splitlines()
        # What the service user's process says is not trusted: no control characters reach root's terminal.
        raise AddressFailureError(
            shown(lines[-1][:300])
            if lines
            else t("Die Anwendung kennt diese Änderung nicht.", "The application does not know this change.")
        )
    return parse_change(result.stdout, token)


def record(
    paths: Paths, run: Runner, change: Change, *, applied: bool, by: str, message: str, details: dict[str, object]
) -> None:
    """Note the result in the application; the settings page shows it."""
    result = manage(
        paths,
        run,
        "address_change", "record", change.token, "--applied" if applied else "--failed",
        "--by", by, "--message", message[:2000], "--details", json.dumps(details),
        check=False,
    )  # fmt: skip
    if result.returncode != 0:
        warn(
            t(
                "Das Ergebnis ließ sich in Rentalars nicht vermerken; die Einstellungsseite zeigt es daher nicht.",
                "The result could not be recorded in Rentalars; the settings page therefore does not show it.",
            )
        )


def systemd_running() -> bool:
    """Whether systemd runs this machine (not so in a container or a chroot)."""
    return Path("/run/systemd/system").is_dir()


@contextlib.contextmanager
def locked(path: Path) -> Iterator[None]:
    """Only one change of the address at a time."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as problem:
        raise AddressFailureError(
            t(
                f"Die Sperrdatei {path} lässt sich nicht öffnen: {problem}",
                f"The lock file {path} cannot be opened: {problem}",
            )
        ) from None
    with os.fdopen(descriptor, "w", encoding="ascii") as lock:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise AddressFailureError(t(f"{path} ist keine gewöhnliche Datei.", f"{path} is not a regular file."))
        os.fchmod(descriptor, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise AddressFailureError(
                t("Eine andere Änderung der Adresse läuft gerade.", "Another change of the address is running.")
            ) from None
        yield


def usage() -> str:
    """How the command is called, in the operator's language."""
    return t(
        """Aufruf:
    sudo rentalars address apply TOKEN             zeigen, fragen, anwenden
    sudo rentalars address apply TOKEN --dry-run   nur prüfen und zeigen, was geschähe
    sudo rentalars address apply TOKEN --yes       ohne Rückfrage

Die Änderung wird im Browser vorbereitet: Einstellungen → Serveradresse und Zertifikat.
Dort steht der Befehl mit seinem TOKEN.""",
        """Usage:
    sudo rentalars address apply TOKEN             show, ask, apply
    sudo rentalars address apply TOKEN --dry-run   only check and show what would happen
    sudo rentalars address apply TOKEN --yes       do not ask

The change is prepared in the browser: Settings → Server address and certificate.
The command with its TOKEN is shown there.""",
    )


def main(arguments: Sequence[str], paths: Paths | None = None, run: Runner = run_command) -> int:
    """Entry point: ``address apply TOKEN [--dry-run] [--yes]``."""
    paths = paths or Paths()
    words = [word for word in arguments if not word.startswith("--")]
    options = {word for word in arguments if word.startswith("--")}
    if options & {"--help", "-h"} or not words:
        print(usage())
        return 0
    unknown = options - {"--dry-run", "--yes"}
    if words[0] != "apply" or len(words) != 2 or unknown:
        print(usage(), file=sys.stderr)
        return 2
    token = words[1].lower()
    if not TOKEN_PATTERN.fullmatch(token):
        error(
            t(
                "Das ist kein gültiges TOKEN (16 bis 32 Zeichen 0-9 und a-f).",
                "This is not a valid TOKEN (16 to 32 characters 0-9 and a-f).",
            )
        )
        return 2
    if os.geteuid() != 0:
        error(
            t(
                "Dieser Befehl braucht Administratorrechte. Bitte mit sudo starten.",
                "This command needs administrator rights. Please start it with sudo.",
            )
        )
        return 1
    by = re.sub(r"[^\w.@-]", "", os.environ.get("SUDO_USER") or "root")[:60] or "root"
    change: Change | None = None
    try:
        with locked(paths.lock_file):
            change = load_change(paths, run, token)
            applier = Applier(change, paths, run, by, services=systemd_running())
            applier.read_current()
            say(
                t("Serveradresse ändern", "Changing the server address")
                + (
                    t(" – Probelauf, nichts wird verändert", " – dry run, nothing is changed")
                    if "--dry-run" in options
                    else ""
                )
            )
            for line in applier.plan():
                note(line)
            if change.kind == "own":
                with tempfile.TemporaryDirectory() as work:
                    certificate, key = Path(work) / "certificate.pem", Path(work) / "key.pem"
                    write_file(certificate, "".join(split_pem(change.certificate)), 0o600)
                    write_file(key, change.private_key, 0o600)
                    for text in check_certificate_files(certificate, key, change.host, run):
                        warn(text)
                note(
                    t(
                        "Zertifikat:   Schlüssel, Kette, Name und Gültigkeit geprüft",
                        "Certificate:  key, chain, name and validity checked",
                    )
                )
            diff = applier.site_diff()
            if diff:
                note("")
                note(
                    t(
                        "Was sich in der NGINX-Konfiguration ändert (- bisher, + neu):",
                        "What changes in the NGINX configuration (- now, + new):",
                    )
                )
                for line in diff[2:]:
                    note(f"  {line}")
            if "--dry-run" in options:
                note("")
                note(
                    t(
                        "Probelauf: Es wurde nichts verändert. Anwenden: ohne --dry-run.",
                        "Dry run: nothing was changed. To apply: without --dry-run.",
                    )
                )
                return 0
            if "--yes" not in options and sys.stdin.isatty():
                answer = input(
                    t(
                        "    Anwenden? Rentalars ist dabei einige Sekunden nicht erreichbar. [j/N] ",
                        "    Apply? Rentalars cannot be reached for a few seconds. [y/N] ",
                    )
                )
                if answer.strip().lower() not in ("j", "ja", "y", "yes"):
                    note(t("Abgebrochen. Es wurde nichts verändert.", "Cancelled. Nothing was changed."))
                    return 1
            applier.apply()
    except AddressFailureError as failure:
        error(str(failure))
        if change is not None and "--dry-run" not in options:
            record(paths, run, change, applied=False, by=by, message=str(failure), details={})
        return 1
    certificate = applier.expected_certificate
    details: dict[str, object] = {
        "backup": str(applier.backup_dir),
        "certificate": certificate,
        "redirect": applier.old_host if change.redirect_old and applier.site_before is not None else "",
        "redirect_https": applier.redirect_https,
        "services_restarted": applier.services,
    }
    message = (
        ""
        if applier.services
        else t(
            "Ohne systemd: NGINX und Rentalars wurden nicht neu geladen.",
            "Without systemd: NGINX and Rentalars were not reloaded.",
        )
    )
    record(paths, run, change, applied=True, by=by, message=message, details=details)
    say(f"Fertig. Rentalars ist jetzt unter https://{change.host} erreichbar.")
    if change.redirect_old and applier.old_host not in ("", change.host) and applier.site_before is not None:
        note(
            t(
                f"Die alte Adresse {applier.old_host} leitet auf die neue weiter.",
                f"The old address {applier.old_host} redirects to the new one.",
            )
        )
    note(f"Die Dateien von vorher: {applier.backup_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
