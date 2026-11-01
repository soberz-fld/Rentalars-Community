# SPDX-License-Identifier: GPL-3.0-or-later
"""Reads the single configuration file of an installation (NFA-032).

Everything an operator may need to adjust lives in one INI file, by default
``/etc/rentalars/rentalars.conf``. The settings module turns the values read
here into Django settings. Keeping the parsing separate has two reasons:

* the file format can be explained and tested without Django, and
* secrets never appear in the source code (NFA-008).

If no configuration file exists, Rentalars starts in *development* mode with
an SQLite database inside the source directory. That makes the quick start in
the README work without any preparation, and it cannot happen by accident on a
server because the installation script always writes the file.

Example file::

    [rentalars]
    url = https://rentalars.example.de
    secret_key = a-long-random-string
    data_dir = /var/lib/rentalars

    [database]
    name = rentalars
    user = rentalars
    password = secret

    [email]
    host = smtp.example.de
    user = rentalars@example.de
    password = secret
    from_address = rentalars@example.de

    [backup]
    keep_days = 14

The section ``[backup]`` is read by the backup script (``deploy/backup.sh``),
not by the application; it is listed here because this is the one file an
operator looks into. The section ``[maps]`` (UIX-034) names the servers of
map pictures and positions; without it those of OpenStreetMap are used. The
section ``[network]`` (NFA-071) names internal networks, addresses and host
names that calendars, webhooks and mail servers entered in the interface may
reach (``allow_internal = 192.168.1.0/24, nas.local``). A production server
refuses to start with an ``http://`` address unless ``allow_http = yes``
says that this is meant (NFA-073). A commented copy of the file with every
option is ``deploy/rentalars.conf.example``.
"""

from __future__ import annotations

import configparser
import ipaddress
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

#: Where the installation script writes the configuration.
DEFAULT_CONFIG_PATH = Path("/etc/rentalars/rentalars.conf")

#: Environment variable that points to a different configuration file.
CONFIG_ENVIRONMENT_VARIABLE = "RENTALARS_CONFIG"

#: The directory that contains ``manage.py``.
SOURCE_DIR = Path(__file__).resolve().parent.parent

#: Only used when no configuration file exists (development and tests).
DEVELOPMENT_SECRET_KEY = "development-only-key-do-not-use-on-a-server"  # noqa: S105 - not a secret: only used without a configuration file


class ConfigurationError(Exception):
    """The configuration file is missing a required value or is malformed."""


@dataclass(frozen=True)
class DatabaseConfig:
    """Connection data for the database (section ``[database]``)."""

    engine: str = "sqlite"
    name: str = ""
    user: str = ""
    password: str = ""
    host: str = ""
    port: str = ""
    #: Encrypt the connection to the database server (NFA-066).
    tls: bool = False
    #: The CA certificate the server's certificate is checked against, name included.
    tls_ca: str = ""

    @property
    def is_local(self) -> bool:
        """Whether the database is the MariaDB on this server (and not another server's)."""
        return self.host in {"", "localhost", "127.0.0.1", "::1"}


#: UIX-034: the tile server of OpenStreetMap; the browser loads the map pictures from here.
OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
#: UIX-034: Nominatim, the search of OpenStreetMap; the server asks it once per address where it lies.
OSM_GEOCODER_URL = "https://nominatim.openstreetmap.org/search"
#: UIX-034: where the licence of the map data is explained; linked from the attribution of every map.
OSM_COPYRIGHT_URL = "https://www.openstreetmap.org/copyright"


@dataclass(frozen=True)
class MapsConfig:
    """Maps at addresses (section ``[maps]``, UIX-034).

    ``tile_url`` is the template of the map pictures, loaded by the browser
    (``{z}``, ``{x}``, ``{y}`` and optionally ``{s}``); empty switches maps
    off – the route links to Google Maps stay. ``geocoder_url`` is a search
    that answers like Nominatim (``?q=…&format=jsonv2``); empty: positions
    are only set by hand. ``attribution`` replaces "© OpenStreetMap-Mitwirkende"
    for tiles of another provider. Both servers can be one's own.
    """

    tile_url: str = OSM_TILE_URL
    geocoder_url: str = OSM_GEOCODER_URL
    attribution: str = ""
    attribution_url: str = OSM_COPYRIGHT_URL
    max_zoom: int = 19

    @property
    def enabled(self) -> bool:
        """Whether maps are shown at all."""
        return bool(self.tile_url)


@dataclass(frozen=True)
class EmailConfig:
    """Outgoing e-mail (section ``[email]``); empty host means "print to log"."""

    host: str = ""
    port: int = 587
    user: str = ""
    password: str = ""
    use_tls: bool = True
    use_ssl: bool = False
    from_address: str = "rentalars@localhost"


@dataclass(frozen=True)
class NetworkConfig:
    """Connections to addresses entered in the interface (section ``[network]``, NFA-071).

    ``allow_internal`` lists what calendars, webhooks and mail servers of
    mailboxes may reach although it is internal: networks
    (``192.168.1.0/24``), single addresses (``10.0.0.5``) and host names
    (``nas.local``), separated by commas. Empty: nothing internal.
    """

    allow_internal: tuple[str, ...] = ()


@dataclass(frozen=True)
class GatewayConfig:
    """The link to a Rentalars Gateway (section ``[gateway]``); every value is optional.

    ``local`` says where the link service carries out the requests of the apps: the Unix socket of the
    application server (a path, the default on a server) or ``http://127.0.0.1:8000`` (development). The
    address of the gateway itself is not here: ``rentalars gateway connect`` stores it with the keys.
    """

    local: str = ""
    #: How many requests the service fetches and carries out at the same time (at least 3).
    workers: int = 4
    #: How far the clock of a device may be off, in seconds (the gateway's own window is 180).
    time_window: int = 180
    #: Answers larger than this many MiB are replaced by an error (the gateway's limit is 12).
    max_response_mib: int = 12
    #: A request that takes longer than this many seconds is ended with 504.
    call_timeout: int = 60


@dataclass(frozen=True)
class Config:
    """All values of the configuration file with their defaults applied."""

    environment: str
    url: str
    secret_key: str
    debug: bool
    data_dir: Path
    language: str = "de"
    time_zone: str = "Europe/Berlin"
    password_reset_hours: int = 72
    serve_media_via_nginx: bool = False
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    email: EmailConfig = field(default_factory=EmailConfig)
    maps: MapsConfig = field(default_factory=MapsConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    #: The link to the Rentalars Gateway (``[gateway]``).
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    #: NFA-073: a production server answers only over HTTPS unless this says otherwise (``allow_http = yes``).
    allow_http: bool = False
    #: Further host names and addresses the application answers to besides :attr:`host_name`
    #: (``allowed_hosts = 192.168.1.50, rentalars.local``); ``.example.de`` also allows all names below it.
    allowed_hosts: tuple[str, ...] = ()
    #: Whether the addresses of this server itself are answered to as well, so that a changed IP address
    #: needs no entry (``allow_own_addresses = no`` switches it off).
    allow_own_addresses: bool = True
    source: Path | None = None

    @property
    def is_production(self) -> bool:
        """Whether the strict security settings for a real server apply."""
        return self.environment == "production"

    @property
    def host_name(self) -> str:
        """The host part of :attr:`url`, e.g. ``rentalars.example.de``."""
        return urlparse(self.url).hostname or "localhost"

    @property
    def uses_https(self) -> bool:
        """Whether the configured address starts with ``https://``."""
        return urlparse(self.url).scheme == "https"


def find_config_path() -> Path | None:
    """Return the configuration file to use, or ``None`` for development mode.

    The environment variable wins over the default location so that several
    environments (development, test, production) can live on one machine
    (NFA-017).
    """
    from_environment = os.environ.get(CONFIG_ENVIRONMENT_VARIABLE)
    if from_environment:
        path = Path(from_environment)
        if not path.is_file():
            raise ConfigurationError(f"{CONFIG_ENVIRONMENT_VARIABLE} points to {path}, but that file does not exist.")
        return path
    if DEFAULT_CONFIG_PATH.is_file():
        return DEFAULT_CONFIG_PATH
    return None


def _is_known_secret_key(value: str) -> bool:
    """Whether a key is the placeholder of ``deploy/rentalars.conf.example`` or the development key – both public."""
    lowered = value.strip().lower()
    return lowered.startswith("replace-with") or lowered in {DEVELOPMENT_SECRET_KEY, "a-long-random-string", "changeme"}


def load_config(path: Path | None = None) -> Config:
    """Read the configuration file and return it with defaults applied.

    Args:
        path: The file to read. ``None`` looks it up with
            :func:`find_config_path`.

    Returns:
        The configuration. Without a file this is the development
        configuration: SQLite, debug mode, e-mails printed to the console.

    Raises:
        ConfigurationError: A production configuration lacks ``secret_key`` or
            database credentials. Starting without them would be insecure, so
            the application refuses to start instead of guessing.
    """
    if path is None:
        path = find_config_path()
    if path is None:
        return _development_config()

    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(path, encoding="utf-8")
    except configparser.Error as error:
        raise ConfigurationError(f"{path} is not a valid configuration file: {error}") from error

    general = parser["rentalars"] if parser.has_section("rentalars") else {}
    environment = general.get("environment", "production").strip().lower()
    if environment not in {"production", "development", "test"}:
        raise ConfigurationError(f"{path}: environment must be production, development or test, not {environment!r}.")

    secret_key = general.get("secret_key", "").strip()
    if not secret_key:
        if environment == "production":
            raise ConfigurationError(f"{path}: [rentalars] secret_key is required.")
        secret_key = DEVELOPMENT_SECRET_KEY
    elif environment == "production" and _is_known_secret_key(secret_key):
        # S4: the key of the example file, or the one of the development mode, is public. The stored passwords
        # (mail, LDAP, two-factor keys) are encrypted with a key derived from it, and the proofs of the gateway signed.
        raise ConfigurationError(
            f"{path}: [rentalars] secret_key is the placeholder of the example file (or a key that is public). "
            "Make one: openssl rand -hex 48"
        )

    database = _read_database(parser, path, environment)
    email = _read_email(parser)
    default_data_dir = "/var/lib/rentalars" if environment == "production" else str(SOURCE_DIR / "var")
    url = general.get("url", "http://localhost:8000").strip().rstrip("/")
    # NFA-073: on a production server passwords and sessions never travel unencrypted by mistake.
    allow_http = _to_bool(general.get("allow_http", "false"))
    if environment == "production" and urlparse(url).scheme != "https" and not allow_http:
        raise ConfigurationError(
            f"{path}: [rentalars] url must start with https:// on a production server. "
            "Only an installation that is reached without encryption on purpose may say allow_http = yes."
        )

    return Config(
        environment=environment,
        url=url,
        secret_key=secret_key,
        debug=_to_bool(general.get("debug", "false")) and environment != "production",
        data_dir=Path(general.get("data_dir", default_data_dir).strip()),
        language=general.get("language", "de").strip(),
        time_zone=general.get("time_zone", "Europe/Berlin").strip(),
        password_reset_hours=int(general.get("password_reset_hours", "72")),
        serve_media_via_nginx=_to_bool(
            general.get("serve_media_via_nginx", "true" if environment == "production" else "false")
        ),
        database=database,
        email=email,
        maps=_read_maps(parser),
        network=_read_network(parser),
        gateway=_read_gateway(parser, path),
        allow_http=allow_http,
        allowed_hosts=_read_allowed_hosts(general),
        allow_own_addresses=_to_bool(general.get("allow_own_addresses", "true")),
        source=path,
    )


def _development_config() -> Config:
    """Return the configuration used when no file exists."""
    return Config(
        environment="development",
        url="http://localhost:8000",
        secret_key=DEVELOPMENT_SECRET_KEY,
        debug=True,
        data_dir=SOURCE_DIR / "var",
        database=DatabaseConfig(engine="sqlite", name=str(SOURCE_DIR / "var" / "development.sqlite3")),
    )


def _read_database(parser: configparser.ConfigParser, path: Path, environment: str) -> DatabaseConfig:
    """Read the ``[database]`` section; production must use MariaDB (NFA-001)."""
    section = parser["database"] if parser.has_section("database") else {}
    engine = section.get("engine", "mariadb").strip().lower()
    if engine not in {"mariadb", "sqlite"}:
        raise ConfigurationError(f"{path}: [database] engine must be mariadb or sqlite.")
    if engine == "sqlite":
        if environment == "production":
            raise ConfigurationError(f"{path}: a production installation needs MariaDB, not SQLite.")
        name = section.get("name", str(SOURCE_DIR / "var" / "development.sqlite3")).strip()
        return DatabaseConfig(engine="sqlite", name=name)

    name = section.get("name", "rentalars").strip()
    user = section.get("user", "rentalars").strip()
    password = section.get("password", "")
    if environment == "production" and not password:
        raise ConfigurationError(f"{path}: [database] password is required.")
    # The administrator of the database server is never used, whatever the
    # installation was told (NFA-066). The self-check also refuses any other
    # account with rights beyond the one database.
    if environment == "production" and user.lower() == "root":
        raise ConfigurationError(
            f"{path}: [database] user must not be root. Rentalars needs a user with rights on its own database only."
        )
    tls_ca = section.get("tls_ca", "").strip()
    return DatabaseConfig(
        engine="mariadb",
        name=name,
        user=user,
        password=password,
        host=section.get("host", "").strip(),
        port=section.get("port", "").strip(),
        tls=_to_bool(section.get("tls", "false")) or bool(tls_ca),
        tls_ca=tls_ca,
    )


def _read_email(parser: configparser.ConfigParser) -> EmailConfig:
    """Read the ``[email]`` section; every value is optional."""
    section = parser["email"] if parser.has_section("email") else {}
    return EmailConfig(
        host=section.get("host", "").strip(),
        port=int(section.get("port", "587")),
        user=section.get("user", "").strip(),
        password=section.get("password", ""),
        use_tls=_to_bool(section.get("use_tls", "true")),
        use_ssl=_to_bool(section.get("use_ssl", "false")),
        from_address=section.get("from_address", "rentalars@localhost").strip(),
    )


def _read_maps(parser: configparser.ConfigParser) -> MapsConfig:
    """Read the ``[maps]`` section (UIX-034); without it the servers of OpenStreetMap are used."""
    section = parser["maps"] if parser.has_section("maps") else {}
    try:
        max_zoom = int(section.get("max_zoom", "19"))
    except ValueError as error:
        raise ConfigurationError("[maps] max_zoom must be a whole number.") from error
    for name in ("tile_url", "geocoder_url", "attribution_url"):
        value = section.get(name, "").strip()
        if value and not value.startswith(("https://", "http://")):
            raise ConfigurationError(f"[maps] {name} must start with https:// or http://.")
    return MapsConfig(
        tile_url=section.get("tile_url", OSM_TILE_URL).strip(),
        geocoder_url=section.get("geocoder_url", OSM_GEOCODER_URL).strip(),
        attribution=section.get("attribution", "").strip(),
        attribution_url=section.get("attribution_url", OSM_COPYRIGHT_URL).strip(),
        max_zoom=max(1, min(max_zoom, 22)),
    )


def _read_network(parser: configparser.ConfigParser) -> NetworkConfig:
    """Read the ``[network]`` section (NFA-071); without it nothing internal is allowed."""
    section = parser["network"] if parser.has_section("network") else {}
    entries = tuple(entry.strip() for entry in section.get("allow_internal", "").split(",") if entry.strip())
    for entry in entries:
        try:
            ipaddress.ip_network(entry, strict=False)
            continue
        except ValueError:
            pass
        labels = entry.lower().rstrip(".").split(".")
        if not all(label and len(label) <= 63 and label.replace("-", "").isalnum() for label in labels):
            raise ConfigurationError(
                f"[network] allow_internal: {entry!r} is neither a network, an address nor a host name."
            )
    return NetworkConfig(allow_internal=entries)


def _read_gateway(parser: configparser.ConfigParser, path: Path) -> GatewayConfig:
    """Read the ``[gateway]`` section; without it the defaults apply."""
    section = parser["gateway"] if parser.has_section("gateway") else {}

    def number(name: str, default: int, low: int, high: int) -> int:
        try:
            value = int(section.get(name, str(default)))
        except ValueError as error:
            raise ConfigurationError(f"{path}: [gateway] {name} must be a whole number.") from error
        return max(low, min(value, high))

    local = section.get("local", "").strip()
    if local and not local.startswith(("/", "http://127.0.0.1", "http://localhost", "http://[::1]")):
        raise ConfigurationError(
            f"{path}: [gateway] local must be the path of the application's socket or an http://127.0.0.1:PORT address."
        )
    return GatewayConfig(
        local=local,
        workers=number("workers", 4, 3, 16),
        time_window=number("time_window", 180, 30, 900),
        max_response_mib=number("max_response_mib", 12, 1, 12),
        call_timeout=number("call_timeout", 60, 5, 85),
    )


def _read_allowed_hosts(general: Any) -> tuple[str, ...]:
    """Read ``[rentalars] allowed_hosts``: host names, IP addresses, ``.example.de`` for all names below it.

    Anything else is refused at the start – a ``*`` (every host), an address with ``http://``, a path or a port –
    because a wrong entry would otherwise either do nothing or open the application to every host name.
    """
    entries: list[str] = []
    for raw in general.get("allowed_hosts", "").split(","):
        entry = raw.strip().lower()
        if not entry:
            continue
        name = entry.removeprefix(".")
        try:
            address = ipaddress.ip_address(name.strip("[]"))
        except ValueError:
            labels = name.rstrip(".").split(".")
            if not all(label and len(label) <= 63 and label.replace("-", "").isalnum() for label in labels):
                raise ConfigurationError(
                    f"[rentalars] allowed_hosts: {entry!r} is neither a host name nor an IP address "
                    "(no http://, no port, no path, no *)."
                ) from None
            # Django compares without a trailing dot.
            entries.append(entry.rstrip("."))
            continue
        if name != entry:
            raise ConfigurationError(f"[rentalars] allowed_hosts: {entry!r} - a leading dot is for host names only.")
        # An IPv6 address is written in brackets in a request ("[::1]"), in its short canonical form.
        entries.append(f"[{address}]" if address.version == 6 else str(address))
    return tuple(entries)


def _to_bool(value: str) -> bool:
    """Interpret the usual spellings of yes and no in configuration files."""
    return value.strip().lower() in {"1", "true", "yes", "on", "ja"}
