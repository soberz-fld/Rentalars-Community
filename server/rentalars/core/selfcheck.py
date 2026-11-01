# SPDX-License-Identifier: GPL-3.0-or-later
"""The self-check of the installation (NFA-037, NFA-049, EML-032, NFA-018).

One list of findings, shown on a page for administrators and printed by the
command ``rentalars selfcheck``:

* versions of Rentalars, Python, Django, MariaDB and the operating system;
* the server: processors and load, memory, network, running time (ADM-008);
  on a Raspberry Pi also the model, and what lies on its SD card (NFA-070);
* the database: connection, state of the tables, the rights of its account
  (NFA-066), encryption (NFA-067);
* file rights of the configuration and the data;
* sending of system mails, and the project mailbox with its last fetch;
* the link to the Rentalars Gateway, if there is one: the last answer of the gateway, the paired apps;
* the last backup and the free space;
* security settings for operation from the internet (NFA-049);
* errors of the application in the last days (NFA-018).

Each finding is "ok", "note", "warning" or "error"; the command ends with a
failing exit status if there is an error. Nothing here changes anything.
"""

from __future__ import annotations

import datetime
import json
import os
import platform
import re
import shutil
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import django
from django.conf import settings
from django.db import connection
from django.utils import formats, timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext, pgettext

from rentalars import __version__
from rentalars.core.i18n import local_pattern

OK, NOTE, WARNING, ERROR = "ok", "note", "warning", "error"
_ORDER = {ERROR: 0, WARNING: 1, NOTE: 2, OK: 3}

#: A backup older than this is a warning, older than twice that an error. The backup runs at
#: 2:30 (up to 2:40); the daily maintenance asks at 4:15. A backup that failed tonight is then
#: 25 h 35 min old at least – and a normal one at any time of the day at most 24 h.
BACKUP_MAX_AGE = datetime.timedelta(hours=25)
#: Free space below these values is a warning or an error (in MB).
SPACE_WARNING_MB = 2048
SPACE_ERROR_MB = 300
#: ADM-008: less available memory than this share of the total is a warning.
MEMORY_WARNING_SHARE = 0.10
#: ADM-008: a load over five minutes above this many times the cores is a warning.
LOAD_WARNING_PER_CORE = 2
#: NFA-070: the model of the device as its firmware names it; only a computer with a device tree,
#: such as a Raspberry Pi, has the file. Tests point it elsewhere.
DEVICE_MODEL = Path("/proc/device-tree/model")
#: NFA-070: the block devices of Linux by their numbers ("179:2"); tests point it elsewhere.
SYS_BLOCK = Path("/sys/dev/block")
#: NFA-070: a Raspberry Pi "with 4 GB" shows about 3.7 GB to the system; below this it has less
#: than the 4 GB it should have (the same limit as deploy/lib.sh, FOUR_GB_IN_MB).
RASPBERRY_PI_MEMORY = 3500 * 1024**2


@dataclass
class Finding:
    """One line of the self-check."""

    group: str
    title: str
    state: str
    detail: str = ""


@dataclass
class Report:
    """All findings, with the worst state."""

    findings: list[Finding] = field(default_factory=list)
    #: What the server has and uses (ADM-008), as read by the check "Server"; for the API.
    resources: Any = None

    def add(self, group: str, title: str, state: str, detail: str = "") -> None:
        """Note one finding."""
        self.findings.append(Finding(str(group), str(title), state, str(detail)))

    @property
    def worst(self) -> str:
        """The worst state of all findings."""
        return min((finding.state for finding in self.findings), key=lambda state: _ORDER[state], default=OK)

    def groups(self) -> list[tuple[str, list[Finding]]]:
        """The findings by group, in the order they were found."""
        result: dict[str, list[Finding]] = {}
        for finding in self.findings:
            result.setdefault(finding.group, []).append(finding)
        return list(result.items())


def report_problems() -> int:
    """Log every error the self-check finds, so that the operators hear of it (NFA-018).

    Run by the daily maintenance after the nightly backup: a backup that did
    not happen, a disk running full, a database user with too many rights
    turn into a notification for the operators – once a day at most, like
    every other error (``core.errors``). Of the backup, warnings count too:
    a single missed night is a warning in the self-check, but worth a
    message. Errors of the application are not reported again; they were
    reported when they happened.

    Returns:
        How many problems were reported.
    """
    import logging

    logger = logging.getLogger("rentalars.selfcheck")
    report = run_checks()
    backup = str(_("Backup"))
    problems = [
        finding
        for finding in report.findings
        if (finding.state == ERROR or (finding.state == WARNING and finding.group == backup))
        and finding.group != str(_("Errors of the application"))
    ]
    for finding in problems:
        logger.error("Self-check: %s – %s: %s", finding.group, finding.title, finding.detail)
    return len(problems)


def run_checks() -> Report:
    """Run all checks; never raises – a failing check is a finding of its own."""
    report = Report()
    for check in (
        _versions,
        _server,
        _database,
        _files,
        _mail,
        _gateway,
        _backup,
        _archive,
        _space,
        _security,
        _network,
        _errors,
    ):
        try:
            check(report)
        except Exception as error:
            report.add(_("Self-check"), check.__name__.strip("_"), ERROR, f"{type(error).__name__}: {error}")
    return report


# --- Versions --------------------------------------------------------------------------------


def _os_name() -> str:
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip('"')
    except OSError:
        pass
    return platform.platform()


def _nginx_version() -> str:
    binary = shutil.which("nginx") or ("/usr/sbin/nginx" if Path("/usr/sbin/nginx").exists() else None)
    if not binary:
        return ""
    try:
        result = subprocess.run([binary, "-v"], capture_output=True, text=True, timeout=5, check=False)  # noqa: S603
    except (OSError, subprocess.SubprocessError):
        return ""
    return (result.stderr or result.stdout).strip().replace("nginx version: ", "")


def _versions(report: Report) -> None:
    group = _("Versions")
    report.add(group, "Rentalars", OK, __version__)
    report.add(group, "Python", OK, platform.python_version())
    report.add(group, "Django", OK, django.get_version())
    report.add(group, _("Operating system"), OK, _os_name())
    nginx = _nginx_version()
    if nginx:
        report.add(group, "NGINX", OK, nginx)
    _ffmpeg(report, group)


def _ffmpeg(report: Report, group: str) -> None:
    """NFA-076: videos in the chat are made smaller with ffmpeg; without it they are refused."""
    from rentalars.chat import media

    if media.videos_possible():
        report.add(group, "ffmpeg", OK, media.ffmpeg_version())
        return
    report.add(
        group,
        "ffmpeg",
        WARNING,
        _(
            "ffmpeg is not installed: videos in the chat are refused, photos work. "
            "Install it with: sudo apt install ffmpeg"
        ),
    )


# --- Server (ADM-008) ----------------------------------------------------------------------------


def size_text(value: int) -> str:
    """Bytes as a short text: ``21 KB``, ``512 MB``, ``7,8 GB``."""
    for unit, size in (("TB", 1024**4), ("GB", 1024**3)):
        if value >= size:
            return f"{formats.number_format(round(value / size, 1), 1)} {unit}"
    if value >= 1024**2:
        return f"{round(value / 1024**2)} MB"
    return f"{max(1, round(value / 1024)) if value else 0} KB"


def duration_text(seconds: float) -> str:
    """A running time in days and hours, or hours and minutes: ``3 days, 4 hours``."""
    minutes = int(seconds // 60)
    days, hours = divmod(minutes // 60, 24)
    if days:
        return ", ".join(
            [
                ngettext("%(count)d day", "%(count)d days", days) % {"count": days},
                ngettext("%(count)d hour", "%(count)d hours", hours) % {"count": hours},
            ]
        )
    parts = [ngettext("%(count)d hour", "%(count)d hours", hours) % {"count": hours}] if hours else []
    parts.append(ngettext("%(count)d minute", "%(count)d minutes", minutes % 60) % {"count": minutes % 60})
    return ", ".join(parts)


def _server(report: Report) -> None:
    """Processors, memory, network and running time of the server (ADM-008).

    Read from ``/proc``; on a system without it the lines are left out. A
    warning when less than a tenth of the memory is available, or when the
    load over five minutes is above twice the number of cores – then
    requests wait for a processor. The load over one minute is not judged:
    a single large task (a PDF, an export) drives it up for a moment.

    On a Raspberry Pi the device comes first (NFA-070).
    """
    from rentalars.core.resources import read_resources

    group = _("Server")
    resources = read_resources()
    report.resources = resources
    model = raspberry_pi_model()
    if model:
        _raspberry_pi(report, group, model, resources.memory_total)
    if resources.cores:
        detail = ngettext("%(count)d core", "%(count)d cores", resources.cores) % {"count": resources.cores}
        state = OK
        if resources.load is not None:
            one, five, fifteen = (formats.number_format(value, 2) for value in resources.load)
            detail += " · " + _("load %(one)s / %(five)s / %(fifteen)s (1, 5, 15 minutes)") % {
                "one": one,
                "five": five,
                "fifteen": fifteen,
            }
            if resources.load[1] > LOAD_WARNING_PER_CORE * resources.cores:
                state = WARNING
                detail += " – " + _("more than twice the number of cores: requests wait for a processor")
        report.add(group, _("Processors"), state, detail)
    if resources.memory_total and resources.memory_available is not None:
        share = resources.memory_available / resources.memory_total
        report.add(
            group,
            _("Memory"),
            WARNING if share < MEMORY_WARNING_SHARE else OK,
            _("%(total)s, of which %(available)s available (%(percent)d %%)")
            % {
                "total": size_text(resources.memory_total),
                "available": size_text(resources.memory_available),
                "percent": round(share * 100),
            },
        )
    if resources.own_memory is not None:
        report.add(
            group,
            _("Memory used by Rentalars"),
            OK,
            ngettext("%(size)s in %(count)d process", "%(size)s in %(count)d processes", resources.own_processes)
            % {"size": size_text(resources.own_memory), "count": resources.own_processes},
        )
    if resources.hostname:
        report.add(group, _("Host name"), OK, resources.hostname)
    for interface in resources.interfaces:
        detail = ", ".join(interface.addresses)
        if interface.received_bytes is not None and interface.sent_bytes is not None:
            detail += " – " + _("received %(received)s, sent %(sent)s since the start") % {
                "received": size_text(interface.received_bytes),
                "sent": size_text(interface.sent_bytes),
            }
        report.add(group, _("Network %(interface)s") % {"interface": interface.name}, OK, detail)
    if resources.uptime_seconds is not None:
        started = timezone.now() - datetime.timedelta(seconds=resources.uptime_seconds)
        report.add(
            group,
            _("Running time"),
            OK,
            _("%(duration)s – since %(when)s")
            % {
                "duration": duration_text(resources.uptime_seconds),
                "when": timezone.localtime(started).strftime(local_pattern("%d.%m.%Y %H:%M")),
            },
        )


# --- Raspberry Pi (NFA-070) --------------------------------------------------------------------------


def raspberry_pi_model() -> str:
    """The model of a Raspberry Pi as its firmware names it; ``""`` on any other computer (NFA-070).

    Example: ``"Raspberry Pi 5 Model B Rev 1.0"``. The firmware ends the name with a zero byte.
    """
    try:
        model = DEVICE_MODEL.read_bytes().rstrip(b"\0").decode("utf-8", "replace").strip()
    except OSError:
        return ""
    return model if model.startswith("Raspberry Pi") else ""


def _block_device_names(device: Path) -> list[str]:
    """A block device of ``/sys`` and every device it is built on (an encrypted or LVM volume)."""
    try:
        device = device.resolve(strict=True)
    except OSError:
        return []
    names = [device.name]
    slaves = device / "slaves"
    if slaves.is_dir():
        for lower in sorted(slaves.iterdir()):
            names += _block_device_names(lower)
    return names


def on_sd_card(path: Path) -> bool:
    """Whether a folder lies on an SD card – or the eMMC of a Compute Module, which wears out alike (NFA-070).

    Found through the device number of the file system and the devices under it, like
    ``places_on_sd_card`` of ``deploy/lib.sh``. ``False`` where it cannot tell.
    """
    try:
        number = os.stat(path).st_dev
    except OSError:
        return False
    names = _block_device_names(SYS_BLOCK / f"{os.major(number)}:{os.minor(number)}")
    return any(name.startswith("mmcblk") for name in names)


def _raspberry_pi(report: Report, group: str, model: str, memory_total: int | None) -> None:
    """The Raspberry Pi, with a note if it has less than 4 GB (NFA-070, NFA-042)."""
    if memory_total and memory_total < RASPBERRY_PI_MEMORY:
        detail = _("%(model)s – less than 4 GB of memory: fewer worker processes, PDFs and backups take longer") % {
            "model": model
        }
        report.add(group, pgettext("self-check", "Device"), NOTE, detail)
    else:
        report.add(group, pgettext("self-check", "Device"), OK, model)


def _sd_card(report: Report) -> None:
    """On a Raspberry Pi: what of Rentalars lies on the SD card (NFA-070).

    The database (if it is on this server), the data folder and the backups. A note, not a
    warning: running from an SD card works, it just may fail one day without warning – the
    installation said so, and the backups should leave the device anyway.
    """
    places: list[tuple[str, Path]] = []
    if connection.vendor == "mysql" and not settings.DATABASES["default"].get("HOST"):
        with connection.cursor() as cursor:
            cursor.execute("SELECT @@datadir")
            places.append((pgettext("on the SD card", "database"), Path(cursor.fetchone()[0])))
    places.append((pgettext("on the SD card", "data folder"), Path(settings.DATA_DIR)))
    try:
        backup_file = json.loads((Path(settings.DATA_DIR) / "backup-status.json").read_text(encoding="utf-8"))["file"]
        places.append((pgettext("on the SD card", "backups"), Path(backup_file).parent))
    except (OSError, ValueError, KeyError, TypeError):
        pass
    on_card = [str(name) for name, path in places if on_sd_card(path)]
    if on_card:
        report.add(
            _("Storage"),
            _("SD card"),
            NOTE,
            _(
                "on the SD card: %(places)s. SD cards wear out under the many small writes of a database and "
                "can fail without warning – an SSD is safer."
            )
            % {"places": ", ".join(on_card)},
        )


# --- Database ----------------------------------------------------------------------------------


def _database(report: Report) -> None:
    from django.db.migrations.executor import MigrationExecutor

    group = _("Database")
    try:
        connection.ensure_connection()
    except Exception as error:
        report.add(group, _("Connection"), ERROR, str(error))
        return
    if connection.vendor != "mysql":
        report.add(group, _("Connection"), NOTE, _("SQLite – for development only"))
    else:
        with connection.cursor() as cursor:
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()[0]
        host = settings.DATABASES["default"].get("HOST")
        if host:
            text = _("MariaDB %(version)s on %(host)s") % {"version": version, "host": host}
        else:
            text = _("MariaDB %(version)s on this server") % {"version": version}
        report.add(group, _("Connection"), OK, text)
    plan = MigrationExecutor(connection).migration_plan(MigrationExecutor(connection).loader.graph.leaf_nodes())
    if plan:
        report.add(
            group,
            _("Tables"),
            ERROR,
            _("%(count)d changes of the tables are missing: python manage.py migrate") % {"count": len(plan)},
        )
    else:
        report.add(group, _("Tables"), OK, _("up to date"))
    if connection.vendor == "mysql":
        _database_account(report, group)


def _database_account(report: Report, group: str) -> None:
    from rentalars.core.database_account import inspect_account

    def query(statement: str) -> list[tuple[str | None, ...]]:
        with connection.cursor() as cursor:
            cursor.execute(statement)
            rows = cursor.fetchall() if cursor.description else []
        return [tuple(None if value is None else str(value) for value in row) for row in rows]

    database = settings.DATABASES["default"]["NAME"]
    expect_tls = bool(settings.DATABASES["default"].get("OPTIONS", {}).get("ssl_mode"))
    inspection = inspect_account(
        query,
        database,
        expect_tls=expect_tls,
        tls_verified=bool(settings.DATABASES["default"].get("OPTIONS", {}).get("ssl")),
    )
    if inspection.is_fit:
        report.add(
            group,
            _("Rights of the database account"),
            OK,
            _("%(user)s: all rights on %(database)s, no others") % {"user": inspection.user, "database": database},
        )
    else:
        for problem in inspection.problems:
            report.add(group, _("Rights of the database account"), ERROR, problem.text(_))
    host = settings.DATABASES["default"].get("HOST") or ""
    if host and host not in {"localhost", "127.0.0.1", "::1"}:
        if inspection.tls_cipher:
            report.add(group, _("Connection encrypted"), OK, inspection.tls_cipher)
        else:
            report.add(
                group,
                _("Connection encrypted"),
                WARNING,
                _("The database is on another server and the connection is not encrypted ([database] tls)."),
            )
    if inspection.encrypts_tables:
        report.add(group, _("Encrypted storage"), OK, inspection.key_management)
    else:
        report.add(group, _("Encrypted storage"), NOTE, _("The database server does not encrypt its files."))


# --- Files ------------------------------------------------------------------------------------------


def _mode(path: Path) -> int | None:
    try:
        return stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return None


def _files(report: Report) -> None:
    from rentalars.config import DEFAULT_CONFIG_PATH

    group = _("Files")
    config = settings.RENTALARS_CONFIG_PATH
    if config:
        mode = _mode(Path(config))
        if mode is not None and mode & 0o007:
            report.add(
                group,
                _("Configuration file"),
                ERROR if settings.RENTALARS_IS_PRODUCTION else NOTE,
                _("%(path)s can be read by every user of the server: chmod 640 %(path)s") % {"path": config},
            )
        else:
            report.add(group, _("Configuration file"), OK, str(config))
    data_dir = Path(settings.DATA_DIR)
    if os.access(data_dir, os.W_OK):
        mode = _mode(data_dir)
        if mode is not None and mode & 0o007:
            report.add(
                group,
                _("Data folder"),
                WARNING if settings.RENTALARS_IS_PRODUCTION else NOTE,
                _("%(path)s is open to every user of the server.") % {"path": data_dir},
            )
        else:
            report.add(group, _("Data folder"), OK, str(data_dir))
    else:
        report.add(group, _("Data folder"), ERROR, _("Rentalars cannot write into %(path)s.") % {"path": data_dir})
    media = Path(settings.MEDIA_ROOT)
    if media.exists() and not os.access(media, os.W_OK):
        report.add(group, _("Uploaded files"), ERROR, _("Rentalars cannot write into %(path)s.") % {"path": media})
    recovery = DEFAULT_CONFIG_PATH.parent / "recovery-key"
    if settings.RENTALARS_IS_PRODUCTION and recovery.exists():
        mode = _mode(recovery)
        if mode is not None and mode & 0o077:
            report.add(
                group,
                _("Recovery key"),
                ERROR,
                _("%(path)s must be readable by root only: chmod 400") % {"path": recovery},
            )


# --- Mail ------------------------------------------------------------------------------------------------


def _mail(report: Report) -> None:
    """System mails and every active mailbox of the correspondence (EML-032, EML-041)."""
    from rentalars.mail.mailboxes import correspondence_mailboxes, system_mailbox
    from rentalars.mail.models import MailSettings

    group = _("E-mail")
    system = system_mailbox()
    if system is not None:
        # EML-041: a mailbox with the role "system" sends instead of [email] of the configuration.
        report.add(
            group,
            _("System mails"),
            OK,
            _("through the mailbox %(mailbox)s (%(host)s:%(port)s)")
            % {"mailbox": system, "host": system.smtp_host, "port": system.smtp_port},
        )
    # The mail log wraps the backend that sends (EML-039); what counts is the one inside.
    elif getattr(settings, "EMAIL_INNER_BACKEND", settings.EMAIL_BACKEND).endswith("smtp.EmailBackend"):
        report.add(
            group,
            _("System mails"),
            OK,
            _("through %(host)s:%(port)s") % {"host": settings.EMAIL_HOST, "port": settings.EMAIL_PORT},
        )
    else:
        # EML-048: it names the missing mail server and where to set one up.
        report.add(
            group,
            _("System mails"),
            WARNING,
            _(
                "No mail server set up: invitations, password links and notifications are not sent. Set up a "
                "mailbox with the role “system mails” under Settings → Mailboxes and signature, or a mail "
                "server in [email] of the configuration."
            ),
        )
    mailboxes = list(correspondence_mailboxes())
    if not mailboxes:
        from rentalars.mail.models import Mailbox

        # A mailbox taken over from the older settings is switched off if fetching was (EML-041).
        state = _("none switched on") if Mailbox.objects.exists() else _("not set up")
        report.add(group, _("Mailboxes"), NOTE, state)
        return
    interval = MailSettings.load().interval_minutes
    for mailbox in mailboxes:
        label = _("Mailbox “%(name)s”") % {"name": mailbox}
        last = (
            timezone.localtime(mailbox.last_success_at).strftime(local_pattern("%d.%m.%Y %H:%M"))
            if mailbox.last_success_at
            else _("never")
        )
        if mailbox.last_error:
            report.add(
                group,
                label,
                ERROR,
                _("%(error)s – last successful fetch: %(when)s") % {"error": mailbox.last_error, "when": last},
            )
            continue
        stale = mailbox.last_success_at is None or timezone.now() - mailbox.last_success_at > datetime.timedelta(
            minutes=max(15, interval * 5)
        )
        report.add(
            group,
            label,
            WARNING if stale else OK,
            _("%(address)s – last successful fetch: %(when)s")
            % {"address": mailbox.address or mailbox.imap_user, "when": last},
        )
    # S2: without the name of the own mail server an answer by mail is only as safe as the sender line.
    settings_row = MailSettings.load()
    _trusted_server_seen(report, group, settings_row)
    if settings_row.crew_answers != "link" and not settings_row.crew_answer_trusted_server.strip():
        report.add(
            group,
            _("Answers to deployment requests by mail"),
            NOTE,
            _(
                "The sender of an answer is not confirmed: a reply mail is no proof of who wrote it. If your mail "
                "server checks senders (DMARC, DKIM), enter its name under Settings → Mailboxes and signature."
            ),
        )


#: The polling service asks the gateway all the time and notes it at least every 10 seconds; a link
#: whose last answer is older than this is not connected (the same limit as ``rentalars gateway status``).
GATEWAY_POLL_MAX_AGE = datetime.timedelta(seconds=90)


def _gateway(report: Report) -> None:
    """The link to the Rentalars Gateway: connected, last answer, paired apps.

    It reads the database only – the self-check does not call the gateway. Without a gateway the apps reach the
    server directly, which is one line of its own.
    """
    from rentalars.gateway_link.models import GatewayDevice, GatewayLink

    group = _("Gateway")
    link = GatewayLink.current()
    if link is None or not link.is_connected:
        report.add(group, _("Gateway link"), OK, _("none – the apps reach the server directly"))
        return
    report.add(group, _("Gateway link"), OK, link.gateway_url)
    now = timezone.now()
    if link.last_poll_at is None:
        report.add(
            group,
            _("Connection"),
            WARNING,
            _("No answer from the gateway yet. Is the service rentalars-gateway-link running?"),
        )
    else:
        age = now - link.last_poll_at
        seconds = int(age.total_seconds())
        if age > GATEWAY_POLL_MAX_AGE:
            report.add(
                group,
                _("Connection"),
                ERROR,
                _(
                    "Not connected: the last answer of the gateway came %(seconds)d seconds ago. Is the service "
                    "rentalars-gateway-link running?"
                )
                % {"seconds": seconds},
            )
        else:
            report.add(
                group,
                _("Connection"),
                OK,
                _("connected, last answer %(seconds)d seconds ago") % {"seconds": seconds},
            )
    if link.last_error:
        when = (
            timezone.localtime(link.last_error_at).strftime(local_pattern("%d.%m.%Y %H:%M"))
            if link.last_error_at
            else ""
        )
        report.add(group, _("Last error"), WARNING, f"{when} {link.last_error}".strip())
    active = GatewayDevice.objects.filter(revoked_at__isnull=True).count()
    revoked = GatewayDevice.objects.filter(revoked_at__isnull=False).count()
    report.add(
        group,
        _("Paired apps"),
        OK,
        _("%(active)d paired, %(revoked)d revoked") % {"active": active, "revoked": revoked},
    )
    if link.move_url:
        report.add(group, _("Move announced"), NOTE, _("announced: %(url)s") % {"url": link.move_url})


def _trusted_server_seen(report: Report, group: str, settings_row: Any) -> None:
    """L9: a name that never confirmed an answer is probably mistyped – every answer by mail is refused then."""
    from rentalars.mail.models import LogResult, MailLogEntry

    if not settings_row.crew_answer_trusted_server.strip():
        return
    since = timezone.now() - datetime.timedelta(days=60)
    entries = MailLogEntry.objects.filter(result=LogResult.CREW_ANSWER, timestamp__gte=since)
    refused = entries.filter(detail__endswith=":unconfirmed").count()
    taken = entries.exclude(detail__contains=":").count()
    if refused >= 3 and not taken:
        report.add(
            group,
            _("Answers to deployment requests by mail"),
            WARNING,
            _(
                "%(count)d answers by mail were refused as unconfirmed and none was taken over. Is the name of the "
                "mail server (%(name)s) the one before the first semicolon in “Authentication-Results” of your mail "
                "server? Look at the header of a received mail."
            )
            % {"count": refused, "name": settings_row.crew_answer_trusted_server},
        )


# --- Backup and space ------------------------------------------------------------------------------------


def _backup(report: Report) -> None:
    group = _("Backup")
    status_file = Path(settings.DATA_DIR) / "backup-status.json"
    try:
        status = json.loads(status_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Every backup by "rentalars backup" (also the one before an update) writes this record,
        # and the installation writes one at once. Without it nothing is known about the last
        # backup – the data folder may have been moved or restored without it.
        state = WARNING if settings.RENTALARS_IS_PRODUCTION else NOTE
        report.add(
            group,
            _("Last backup"),
            state,
            _("none recorded yet – the last backup is not known. Write one now: sudo rentalars backup"),
        )
        return
    written = datetime.datetime.fromisoformat(status["time"])
    age = timezone.now() - written
    when = timezone.localtime(written).strftime(local_pattern("%d.%m.%Y %H:%M"))
    state = OK if age <= BACKUP_MAX_AGE else (WARNING if age <= 2 * BACKUP_MAX_AGE else ERROR)
    report.add(group, _("Last backup"), state, f"{when} – {status.get('file', '')}")
    report.add(
        group,
        _("Encrypted"),
        OK if status.get("encrypted") else NOTE,
        _("yes") if status.get("encrypted") else _("no (sudo rentalars encryption enable)"),
    )
    free = int(status.get("free_mb", 0))
    report.add(group, _("Free space for backups"), _space_state(free), _megabytes(free))


def _archive(report: Report) -> None:
    """DOK-043: files of the archive of vouchers that changed or disappeared are errors."""
    from rentalars.documents import archive

    group = _("Archive of vouchers")
    info = archive.summary()
    if not info["total"]:
        return
    bad = info["changed"] + info["missing"]
    if bad:
        names = ", ".join(r.reference for r in archive.problems()[:5])
        report.add(
            group,
            _("Files checked"),
            ERROR,
            _("%(count)d files changed or missing: %(names)s – see Settings → Accounting → Archive")
            % {"count": bad, "names": names},
        )
    else:
        report.add(group, _("Files checked"), OK, _("%(count)d vouchers, no changes found") % {"count": info["total"]})


def _space_state(free_mb: int) -> str:
    if free_mb < SPACE_ERROR_MB:
        return ERROR
    if free_mb < SPACE_WARNING_MB:
        return WARNING
    return OK


def _megabytes(value: int) -> str:
    return f"{value / 1024:.1f} GB" if value >= 1024 else f"{value} MB"


def _space(report: Report) -> None:
    usage = shutil.disk_usage(settings.DATA_DIR)
    free = usage.free // (1024 * 1024)
    report.add(_("Storage"), _("Free space for data"), _space_state(free), _megabytes(free))
    if raspberry_pi_model():
        _sd_card(report)


# --- Security (NFA-049) -------------------------------------------------------------------------------------


def _security(report: Report) -> None:
    from rentalars.accounts.models import User
    from rentalars.accounts.rights import Level, Module
    from rentalars.core.models import SystemSettings

    group = _("Security")
    if settings.DEBUG:
        report.add(group, _("Debug mode"), ERROR if settings.RENTALARS_IS_PRODUCTION else NOTE, _("switched on"))
    if settings.RENTALARS_IS_PRODUCTION:
        if settings.RENTALARS_URL.startswith("https://"):
            report.add(group, "HTTPS", OK, settings.RENTALARS_URL)
        elif getattr(settings, "RENTALARS_ALLOW_HTTP", False):
            # NFA-073: allowed on purpose in the configuration file.
            report.add(
                group,
                "HTTPS",
                WARNING,
                _(
                    "switched off on purpose (allow_http = yes): passwords and sessions travel unencrypted unless "
                    "a server in front encrypts them"
                ),
            )
        else:
            report.add(group, "HTTPS", ERROR, _("The address does not start with https://"))
        if len(settings.SECRET_KEY) < 50:
            report.add(group, _("Secret key"), ERROR, _("too short; at least 50 characters"))
    system_settings = SystemSettings.load()
    administrators = [
        user
        for user in User.objects.filter(is_active=True).prefetch_related("roles")
        if user.is_superuser or user.rights.has_level(Module.ADMINISTRATION, Level.WRITE)
    ]
    without = [user for user in administrators if not user.has_two_factor]
    if system_settings.two_factor_for_administrators:
        report.add(group, _("Two-factor login for administrators"), OK, _("required"))
    elif without:
        report.add(
            group,
            _("Two-factor login for administrators"),
            WARNING,
            _(
                "not required; without it: %(names)s. Recommended for operation from the internet (Settings → Company data and settings)."
            )
            % {"names": ", ".join(str(user) for user in without[:8])},
        )
    else:
        report.add(group, _("Two-factor login for administrators"), OK, _("all administrators use it"))
    report.add(
        group,
        _("Logout after inactivity"),
        OK if system_settings.session_idle_minutes <= 8 * 60 else NOTE,
        _("%(minutes)d minutes") % {"minutes": system_settings.session_idle_minutes},
    )
    _nginx(report, group)


# --- Connections to addresses entered in the interface (NFA-071) -------------------------------------

#: The most settings looked at; each distinct server name is resolved once.
NETWORK_TARGETS_LIMIT = 500


def _network_kind_text(kind: str) -> str:
    return {
        "loopback": _("this machine (loopback)"),
        "private": _("private network"),
        "link-local": _("link-local network"),
        "shared": _("shared network of the provider (CGNAT)"),
        "multicast": _("multicast"),
        "reserved": _("reserved address"),
        "unspecified": _("unspecified address"),
        "own": _("this server"),
    }.get(kind, kind)


def _network_targets() -> list[tuple[str, str, int | None]]:
    """What the interface makes the server connect to: label, host and port of each setting (NFA-071)."""
    from urllib.parse import urlsplit

    from rentalars.api.models import Webhook
    from rentalars.mail.models import Mailbox
    from rentalars.personnel.models import CalendarFeed, Person

    def host_and_port(url: str) -> tuple[str, int | None]:
        try:
            parts = urlsplit(url)
            return parts.hostname or "", parts.port
        except ValueError:
            return "", None

    limit = NETWORK_TARGETS_LIMIT
    targets: list[tuple[str, str, int | None]] = []
    for feed in CalendarFeed.objects.select_related("person").order_by("pk")[:limit]:
        targets.append((_("Linked calendar of %(person)s") % {"person": feed.person}, *host_and_port(feed.url)))
    for person in Person.objects.exclude(caldav_url="").order_by("pk")[:limit]:
        targets.append((_("CalDAV calendar of %(person)s") % {"person": person}, *host_and_port(person.caldav_url)))
    for webhook in Webhook.objects.filter(is_active=True).order_by("pk")[:limit]:
        host, port = host_and_port(webhook.url)
        # The path of a webhook address may hold a secret; the description or the host names it.
        targets.append((_("Webhook %(name)s") % {"name": webhook.description or host}, host, port))
    for mailbox in Mailbox.objects.filter(is_active=True).order_by("pk")[:limit]:
        if mailbox.imap_host:
            targets.append(
                (_("IMAP server of mailbox %(name)s") % {"name": mailbox}, mailbox.imap_host, mailbox.imap_port)
            )
        if mailbox.smtp_host:
            targets.append(
                (_("SMTP server of mailbox %(name)s") % {"name": mailbox}, mailbox.smtp_host, mailbox.smtp_port)
            )
    # ADM-017: the OpenAI-compatible interfaces of the AI (the operator's local AI is not typed in).
    from rentalars.ai.models import AIProvider

    for provider in AIProvider.objects.order_by("pk")[:limit]:
        targets.append((_("AI interface %(name)s") % {"name": provider.name}, *host_and_port(provider.base_url)))
    return targets


def _network(report: Report) -> None:
    """NFA-071: settings of the interface that lead into an internal network the operator did not allow.

    Nothing is changed or deleted: such a setting fails when it is used,
    until the operator allows the address or somebody changes it.
    """
    import ipaddress

    from rentalars.core import network

    group = _("Connections to other servers")
    outcome: dict[str, str] = {}
    blocked: list[str] = []
    for label, host, port in _network_targets():
        if not host:
            continue
        if host not in outcome:
            try:
                network.checked_addresses(host, port)
                outcome[host] = ""
            except network.BlockedAddressError as error:
                try:
                    kind = network.refusal(host, ipaddress.ip_address(error.address)) if error.address else ""
                except ValueError:
                    kind = ""
                outcome[host] = f"{error.address} – {_network_kind_text(kind)}" if error.address else host
            except (OSError, UnicodeError):
                outcome[host] = ""  # an unknown name is a problem of its own, shown where it is used
        if outcome[host]:
            blocked.append(f"{label}: {host} ({outcome[host]})")
    allowed = ", ".join(getattr(settings, "RENTALARS_NETWORK_ALLOW_INTERNAL", ()) or ())
    if blocked:
        shown = "; ".join(blocked[:10])
        if len(blocked) > 10:
            shown += " " + _("… and %(count)d more") % {"count": len(blocked) - 10}
        report.add(
            group,
            _("Internal addresses"),
            WARNING,
            _(
                "%(list)s. Rentalars does not connect there. Allow the address in the configuration file "
                "([network] allow_internal) or change the setting."
            )
            % {"list": shown},
        )
    else:
        report.add(group, _("Internal addresses"), OK, _("No setting leads into an internal network."))
    report.add(
        group,
        _("Allowed internal addresses"),
        NOTE if allowed else OK,
        allowed or _("none ([network] allow_internal)"),
    )
    # The proxy of the environment resolves names itself: the pinning to the checked address is lost there.
    import urllib.request

    proxies = sorted(scheme for scheme in urllib.request.getproxies() if scheme in {"http", "https"})
    if proxies:
        report.add(
            group,
            _("Proxy"),
            WARNING,
            _(
                "The service uses a proxy for %(schemes)s (environment variables). Rentalars checks the names "
                "beforehand, but the proxy resolves them again itself – against a changed DNS answer only the proxy "
                "protects then. Block internal destinations in the proxy as well, or leave the proxy out "
                "(no_proxy)."
            )
            % {"schemes": ", ".join(proxies)},
        )
    else:
        report.add(group, _("Proxy"), OK, _("none – Rentalars connects directly to the checked address"))


#: What a hardened NGINX site of Rentalars contains (deploy/nginx/rentalars.conf).
NGINX_EXPECTED = (
    ("server_tokens off", "server_tokens off;"),
    ("ssl_protocols TLSv1.2 TLSv1.3", "ssl_protocols TLSv1.2 TLSv1.3;"),
    ("limit_req zone=rentalars_login", "limit_req"),
    ("ssl_reject_handshake on", "ssl_reject_handshake on;"),
    ("client_header_timeout", "client_header_timeout"),
)


#: The site the installation writes; a module value so that the tests can point elsewhere.
NGINX_SITE = Path("/etc/nginx/sites-available/rentalars")


def _nginx(report: Report, group: str) -> None:
    site = NGINX_SITE
    try:
        text = site.read_text(encoding="utf-8")
    except OSError:
        if settings.RENTALARS_IS_PRODUCTION:
            report.add(group, "NGINX", NOTE, _("%(path)s cannot be read; not checked.") % {"path": site})
        return
    _nginx_body_size(report, group, text)
    missing = [label for label, needle in NGINX_EXPECTED if needle not in text]
    if missing:
        report.add(
            group,
            "NGINX",
            WARNING,
            _(
                "The site lacks settings of the current template: %(missing)s. Take the template over "
                "with: sudo rentalars nginx-site (docs/betrieb/betrieb.md)."
            )
            % {"missing": ", ".join(missing)},
        )
    else:
        report.add(group, "NGINX", OK, _("secure settings of the template"))


_BODY_SIZE = re.compile(r"^\s*client_max_body_size\s+(\d+)([kKmMgG]?)\s*;", re.MULTILINE)
_UNIT_MB = {"": 1 / (1024 * 1024), "k": 1 / 1024, "m": 1, "g": 1024}


def _nginx_body_size(report: Report, group: str, text: str) -> None:
    """Whether NGINX lets through the files the settings allow (NFA-007).

    A site from before 0.4 accepts 30 MB; project files may be 50 MB by
    default. NGINX would refuse a larger upload before Rentalars sees it.
    """
    from rentalars.core.models import SystemSettings

    sizes = [int(number) * _UNIT_MB[unit.lower()] for number, unit in _BODY_SIZE.findall(text)]
    if 0 in sizes:
        return  # 0 switches the limit off
    limit = max(sizes, default=1)  # without the setting NGINX takes 1 MB
    allowed = SystemSettings.load().max_upload_mb
    # One megabyte more for the rest of the form around the file.
    if limit < allowed + 1:
        report.add(
            group,
            _("NGINX upload limit"),
            WARNING,
            _(
                "NGINX takes requests up to %(nginx)d MB, the settings allow files of %(allowed)d MB. "
                "Larger uploads fail. Take the template over with: sudo rentalars nginx-site"
            )
            % {"nginx": limit, "allowed": allowed},
        )
        return
    # NFA-076: a video for the chat may be larger than a project file.
    from rentalars.chat.media import MAX_VIDEO_BYTES

    video = MAX_VIDEO_BYTES // (1024 * 1024)
    if limit < video + 1:
        report.add(
            group,
            _("NGINX upload limit"),
            WARNING,
            _(
                "NGINX takes requests up to %(nginx)d MB, videos in the chat may have %(video)d MB. "
                "Larger uploads fail. Take the template over with: sudo rentalars nginx-site"
            )
            % {"nginx": limit, "video": video},
        )


# --- Errors (NFA-018) ------------------------------------------------------------------------------------------


def _errors(report: Report) -> None:
    from rentalars.core.models import ErrorRecord

    group = _("Errors of the application")
    since = timezone.now() - datetime.timedelta(days=7)
    recent = list(ErrorRecord.objects.filter(last_seen__gte=since)[:5])
    if not recent:
        report.add(group, _("Last 7 days"), OK, _("no errors"))
        return
    for error in recent:
        report.add(
            group,
            error.source,
            WARNING,
            _("%(message)s – %(count)d×, last %(when)s")
            % {
                "message": error.message[:200],
                "count": error.count,
                "when": timezone.localtime(error.last_seen).strftime(local_pattern("%d.%m.%Y %H:%M")),
            },
        )


def summary_for_api(report: Report) -> dict[str, Any]:
    """The report as data for the API, with the resources of the server as numbers (ADM-008)."""
    return {
        "state": report.worst,
        "findings": [finding.__dict__ for finding in report.findings],
        "resources": report.resources.as_dict() if report.resources is not None else None,
    }
