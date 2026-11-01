# SPDX-License-Identifier: GPL-3.0-or-later
"""A backup from the browser, and what is encrypted (ADM-009, ADM-010, NFA-015, NFA-067).

**The backup (ADM-010).** "Sicherung jetzt erstellen" in the settings writes
the same file as ``sudo rentalars backup`` (``deploy/backup.sh``), so that
``sudo rentalars restore FILE`` puts it back – a ``.tar.gz`` with

``database.sql``     the whole database (``mariadb-dump``, the same options)
``rentalars.conf``   the configuration file
``VERSION``          the version of Rentalars that wrote it
``media/``           the stored files

It runs as a task in the background (NFA-041) under the service account,
which may read its own database and data folder but nothing of root. The
dump uses the access data of the configuration through an option file of
mode 600 that is removed at once – never a password on the command line.
On SQLite (development) the database is copied with SQLite's backup function
and written out as SQL.

The file lands in ``media/jobs/backups/`` – the place of task results,
delivered by NGINX after the rights check, deleted with the results of
tasks after ``retention_jobs_days``. The nightly backup leaves that folder
out: backups inside backups would only double their size. While it is being
written, nothing of it is in ``media``: the archive is written next to the
data and moved in when complete, so that a nightly backup never meets half
a file. Before it is offered, it is read back completely, like
``backup.sh`` does.

**Encrypted backups.** With ``[backup] encrypt = true`` every backup must be
encrypted. ``backup.sh`` encrypts with the recovery key, which only root can
read (``/etc/rentalars/recovery-key``) – and the application runs without
any right of root on purpose (``NoNewPrivileges``). A backup from the
browser therefore gets **a key of its own**: made for it alone, in the form
of a recovery key, encrypted the very same way (``openssl enc -aes-256-cbc
-pbkdf2 -iter 200000 -md sha256``, see :class:`OpenSSLWriter`). Nothing
unencrypted is written; the key is shown only to whoever made the backup,
and stored encrypted (``core.crypto``) until the task is deleted. Restore::

    sudo rentalars restore FILE.tar.gz.enc --key-file KEYFILE

or without ``--key-file``: the command asks for the key, because the key of
the server does not fit. ``rentalars encryption decrypt-backup`` and the
plain ``openssl`` command of ``docs/betrieb/verschluesselung.md`` work with
the key in the same way.

**What is encrypted (ADM-009).** :func:`encryption_state` collects what the
application can see: whether the database server encrypts its tables,
whether backups are to be encrypted, whether the last backup was, whether a
recovery key exists. Switching it on is a matter of root on the server
(``sudo rentalars encryption enable``) – there is no button for it.
"""

from __future__ import annotations

import configparser
import contextlib
import datetime
import gzip
import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from django.conf import settings
from django.db import connection
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

#: Below ``MEDIA_ROOT``: where backups from the browser are kept until the retention of task results.
BACKUP_FOLDER = "jobs/backups"

#: The cipher of ``deploy/lib.sh`` (BACKUP_CIPHER): AES-256-CBC, key and IV from PBKDF2-SHA256.
PBKDF2_ITERATIONS = 200_000
_MAGIC = b"Salted__"

#: Space that must stay free beyond the estimated size of the backup, in bytes (backup.sh asks for 200 MB).
SPACE_RESERVE = 200 * 1024 * 1024

#: The recovery key of the server; only root may read it, everybody may see whether it exists.
RECOVERY_KEY_FILE = Path("/etc/rentalars/recovery-key")

#: Values that switch ``[backup] encrypt`` on (deploy/lib.sh, backups_encrypted).
_TRUE = {"true", "yes", "on", "1"}

_KEY_FORMAT = re.compile(r"^[0-9a-f]{4}(?:-[0-9a-f]{4}){9}$")


class BackupError(Exception):
    """A backup cannot be made; the message says why and what to do."""


# --- Encryption (ADM-009) ---------------------------------------------------------------------------


def _config() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    path = settings.RENTALARS_CONFIG_PATH
    if path:
        with contextlib.suppress(OSError, configparser.Error):
            parser.read(path, encoding="utf-8")
    return parser


def backups_are_encrypted() -> bool:
    """Whether backups are to be encrypted (``[backup] encrypt``, as ``backup.sh`` reads it)."""
    return _config().get("backup", "encrypt", fallback="false").strip().lower() in _TRUE


def last_server_backup() -> dict[str, Any] | None:
    """What ``backup.sh`` noted about the last backup it wrote (``backup-status.json``), or ``None``."""
    try:
        status = json.loads((Path(settings.DATA_DIR) / "backup-status.json").read_text(encoding="utf-8"))
        status["time"] = datetime.datetime.fromisoformat(status["time"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return status


@dataclass
class EncryptionState:
    """What the application can see of the encryption of database and backups (ADM-009)."""

    #: ``True``/``False`` for MariaDB; ``None`` for SQLite or when the server would not say.
    database_encrypted: bool | None
    #: The key management of MariaDB (``file_key_management``), or why nothing is known.
    database_detail: str
    database_is_local: bool
    backups_encrypted: bool
    #: Whether the last nightly backup was encrypted; ``None`` if none is recorded.
    last_backup_encrypted: bool | None
    recovery_key_exists: bool

    @property
    def complete(self) -> bool:
        """Whether everything that can be encrypted is."""
        database_done = self.database_encrypted is not False or not self.database_is_local
        return self.backups_encrypted and database_done

    def as_dict(self) -> dict[str, Any]:
        """The state for the API."""
        return {
            "database_encrypted": self.database_encrypted,
            "database_detail": self.database_detail,
            "database_is_local": self.database_is_local,
            "backups_encrypted": self.backups_encrypted,
            "last_backup_encrypted": self.last_backup_encrypted,
            "recovery_key_exists": self.recovery_key_exists,
            "complete": self.complete,
            "command": "sudo rentalars encryption enable",
        }


def _database_encryption() -> tuple[bool | None, str]:
    if connection.vendor != "mysql":
        return None, _("SQLite – for development only")
    try:
        with connection.cursor() as cursor:
            # Every account may read these two values (see core.database_account).
            cursor.execute("SELECT @@GLOBAL.innodb_encrypt_tables")
            setting = str(cursor.fetchone()[0] or "")
            cursor.execute(
                "SELECT PLUGIN_NAME FROM information_schema.PLUGINS"
                " WHERE PLUGIN_TYPE = 'ENCRYPTION' AND PLUGIN_STATUS = 'ACTIVE'"
            )
            plugins = ", ".join(str(row[0]) for row in cursor.fetchall())
    except Exception as error:
        return None, str(error)
    return bool(plugins) and setting.upper() in {"ON", "FORCE", "1"}, plugins


def encryption_state() -> EncryptionState:
    """Collect what is encrypted (ADM-009)."""
    encrypted, detail = _database_encryption()
    last = last_server_backup()
    try:
        recovery_key_exists = RECOVERY_KEY_FILE.exists()
    except OSError:
        recovery_key_exists = False
    host = settings.DATABASES["default"].get("HOST") or ""
    return EncryptionState(
        database_encrypted=encrypted,
        database_detail=detail,
        database_is_local=host in {"", "localhost", "127.0.0.1", "::1"},
        backups_encrypted=backups_are_encrypted(),
        last_backup_encrypted=bool(last.get("encrypted")) if last is not None else None,
        recovery_key_exists=recovery_key_exists,
    )


# --- The format of openssl enc ------------------------------------------------------------------------


def new_key() -> str:
    """A key in the form of a recovery key: 40 hexadecimal characters in groups of four (160 bits)."""
    digits = secrets.token_hex(20)
    return "-".join(digits[index : index + 4] for index in range(0, 40, 4))


def _cipher(passphrase: str, salt: bytes) -> Any:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    derived = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, PBKDF2_ITERATIONS, 48)
    return Cipher(algorithms.AES(derived[:32]), modes.CBC(derived[32:]))


class OpenSSLWriter:
    """Writes what it is given encrypted the way ``openssl enc`` does with the options of ``backup.sh``.

    ``openssl enc -e -aes-256-cbc -pbkdf2 -iter 200000 -md sha256 -salt
    -pass file:KEYFILE``: the file starts with ``Salted__`` and eight random
    bytes; key and IV are derived from the first line of the key file with
    PBKDF2-HMAC-SHA256; the data is padded with PKCS#7. ``openssl enc -d``
    with the same options and key file reads it back.
    """

    def __init__(self, target: BinaryIO, passphrase: str) -> None:
        from cryptography.hazmat.primitives import padding

        salt = os.urandom(8)
        self._target = target
        self._encryptor = _cipher(passphrase, salt).encryptor()
        self._padder = padding.PKCS7(128).padder()
        target.write(_MAGIC + salt)

    def write(self, data: bytes) -> int:
        """Encrypt and write a piece."""
        self._target.write(self._encryptor.update(self._padder.update(bytes(data))))
        return len(data)

    def flush(self) -> None:
        """Nothing is held back beyond the current block."""
        self._target.flush()

    def finish(self) -> None:
        """Write the last block with its padding."""
        self._target.write(self._encryptor.update(self._padder.finalize()) + self._encryptor.finalize())
        self._target.flush()


class OpenSSLReader:
    """Reads a file written by ``openssl enc`` (or :class:`OpenSSLWriter`) and returns the plain data."""

    def __init__(self, source: BinaryIO, passphrase: str) -> None:
        from cryptography.hazmat.primitives import padding

        header = source.read(16)
        if len(header) != 16 or not header.startswith(_MAGIC):
            raise BackupError(_("The file is not encrypted the way backups are."))
        self._source = source
        self._decryptor = _cipher(passphrase, header[8:]).decryptor()
        self._unpadder = padding.PKCS7(128).unpadder()
        self._buffer = bytearray()
        self._done = False

    def read(self, size: int = -1) -> bytes:
        """Return up to ``size`` bytes of plain data (all of it for ``-1``)."""
        while not self._done and (size < 0 or len(self._buffer) < size):
            chunk = self._source.read(1024 * 1024)
            if chunk:
                self._buffer += self._unpadder.update(self._decryptor.update(chunk))
            else:
                try:
                    self._buffer += self._unpadder.update(self._decryptor.finalize()) + self._unpadder.finalize()
                except ValueError as error:
                    raise BackupError(_("The key does not fit, or the file is damaged.")) from error
                self._done = True
        if size < 0:
            size = len(self._buffer)
        data = bytes(self._buffer[:size])
        del self._buffer[:size]
        return data


# --- Writing the archive --------------------------------------------------------------------------


def _option_value(value: str) -> str:
    """A value for a MariaDB option file, quoted like ``option_value`` of deploy/lib.sh."""
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_client_file(target: Path) -> None:
    """The access data of the database as a ``[client]`` file of mode 600 (as ``write_client_file`` of lib.sh)."""
    database = settings.DATABASES["default"]
    options = database.get("OPTIONS", {})
    host = str(database.get("HOST") or "")
    lines = ["[client]", f"user={_option_value(database.get('USER') or '')}"]
    lines.append(f"password={_option_value(database.get('PASSWORD') or '')}")
    if host:
        lines.append(f"host={_option_value(host)}")
    if database.get("PORT"):
        lines.append(f"port={database['PORT']}")
    if options.get("ssl_mode"):
        lines.append("ssl")
        ca = (options.get("ssl") or {}).get("ca")
        if ca:
            lines += [f"ssl-ca={_option_value(ca)}", "ssl-verify-server-cert"]
        else:
            lines.append("skip-ssl-verify-server-cert")
    elif host and host not in {"localhost", "127.0.0.1", "::1"}:
        lines.append("skip-ssl")
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def dump_command() -> str:
    """The dump program: ``mariadb-dump``, or ``mysqldump`` of older clients."""
    for name in ("mariadb-dump", "mysqldump"):
        found = shutil.which(name)
        if found:
            return found
    raise BackupError(_("The program mariadb-dump is missing on the server (package mariadb-client)."))


class _DumpSink:
    """Where a dump is written: a file of mode 600, encrypted on the way when there is a key.

    With encrypted backups the dump must not lie on the disk unencrypted, not even for a moment and not in the
    temporary folder: it goes through the cipher into ``database.sql.enc``. The sink keeps the last bytes, with which
    the completeness of the dump is checked.
    """

    def __init__(self, target: Path, key: str | None) -> None:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        self._file = os.fdopen(descriptor, "wb")
        self._writer: Any = OpenSSLWriter(self._file, key) if key else self._file
        self._encrypted = bool(key)
        self.tail = b""

    def write(self, data: bytes) -> None:
        self._writer.write(data)
        self.tail = (self.tail + data)[-256:]

    def close(self) -> None:
        try:
            if self._encrypted:
                self._writer.finish()
        finally:
            self._file.close()


def _dump_mariadb(target: Path, work: Path, key: str | None = None) -> None:
    """The database as ``mariadb-dump`` writes it for ``backup.sh``: a consistent snapshot without locking anybody out."""
    client_file = work / "client.cnf"
    write_client_file(client_file)
    errors = work / "dump.err"
    sink = _DumpSink(target, key)
    try:
        command = [
            dump_command(),
            f"--defaults-extra-file={client_file}",
            "--single-transaction",
            "--routines",
            "--triggers",
            "--default-character-set=utf8mb4",
            # The account has rights on its own database only; tablespaces are not dumped by backup.sh either.
            "--no-tablespaces",
            str(settings.DATABASES["default"]["NAME"]),
        ]
        with errors.open("wb") as error_file:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=error_file)  # noqa: S603
            assert process.stdout is not None
            for chunk in iter(lambda: process.stdout.read(1024 * 1024), b""):  # type: ignore[union-attr]
                sink.write(chunk)
            code = process.wait()
    finally:
        sink.close()
        client_file.unlink(missing_ok=True)
    message = errors.read_text(encoding="utf-8", errors="replace").strip()[:500] if errors.exists() else ""
    errors.unlink(missing_ok=True)
    if code != 0:
        raise BackupError(_("The database could not be backed up: %(error)s") % {"error": message})
    # A dump that ends without this line was cut off; such a backup is worthless (backup.sh).
    if b"Dump completed" not in sink.tail:
        raise BackupError(_("The backup of the database is incomplete. No backup was written."))


def _dump_sqlite(target: Path, work: Path, key: str | None = None) -> None:
    """SQLite (development): a consistent copy with SQLite's backup function, written out as SQL.

    Inside a transaction – a task run at once within a request, as in the
    tests – the backup function would wait for that very transaction
    forever; there the transaction's own view is consistent and is written
    out directly.
    """
    connection.ensure_connection()
    copy_path = work / "copy.sqlite3"
    copy = sqlite3.connect(copy_path)
    sink = _DumpSink(target, key)
    try:
        source = connection.connection
        if not connection.in_atomic_block:
            source.backup(copy)
            source = copy
        for line in source.iterdump():
            sink.write(f"{line}\n".encode())
    finally:
        sink.close()
        copy.close()
        copy_path.unlink(missing_ok=True)


def dump_database(target: Path, work: Path, key: str | None = None) -> None:
    """Write the whole database as SQL into ``target`` (mode 600); encrypted with ``key`` if one is given."""
    if connection.vendor == "mysql":
        _dump_mariadb(target, work, key)
    else:
        _dump_sqlite(target, work, key)


def _media_files() -> Iterator[tuple[Path, str]]:
    """The stored files and folders as (path, name in the archive), without the backups from the browser."""
    root = Path(settings.MEDIA_ROOT)
    excluded = root / BACKUP_FOLDER
    trash = root / ".deleted"
    yield root, "media"
    if not root.is_dir():
        return
    for folder, folders, files in os.walk(root):
        current = Path(folder)
        # Also the browser backups that were moved to the trash (.deleted/<day>/jobs/backups): backups in backups.
        folders[:] = sorted(
            name
            for name in folders
            if current / name != excluded
            and not (current.parent.parent == trash and current.name == "jobs" and name == "backups")
        )
        for name in folders:
            yield current / name, "media/" + (current / name).relative_to(root).as_posix()
        for name in sorted(files):
            yield current / name, "media/" + (current / name).relative_to(root).as_posix()


def _size_of_media() -> int:
    total = 0
    for path, _name in _media_files():
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def _database_size() -> int:
    if connection.vendor == "mysql":
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COALESCE(SUM(DATA_LENGTH + INDEX_LENGTH), 0) FROM information_schema.TABLES"
                " WHERE TABLE_SCHEMA = DATABASE()"
            )
            return int(cursor.fetchone()[0] or 0)
    name = str(settings.DATABASES["default"]["NAME"])
    try:
        return Path(name).stat().st_size
    except OSError:
        return 0


def check_space() -> None:
    """Refuse when the data folder cannot hold the backup: database and files plus a reserve."""
    needed = _database_size() + _size_of_media() + SPACE_RESERVE
    free = shutil.disk_usage(settings.DATA_DIR).free
    if free < needed:
        raise BackupError(
            _("Only %(free)d MB are free in the data folder; the backup needs about %(needed)d MB.")
            % {"free": free // (1024 * 1024), "needed": needed // (1024 * 1024)}
        )


def _add(archive: tarfile.TarFile, path: Path, name: str, *, mode: int | None = None) -> bool:
    """Add one file or folder (not what is inside); returns whether it was a file."""
    info = archive.gettarinfo(str(path), arcname=name)
    if mode is not None:
        info.mode = mode
    if info.isreg():
        with path.open("rb") as handle:
            archive.addfile(info, handle)
        return True
    archive.addfile(info)
    return False


def write_archive(
    output: BinaryIO, work: Path, progress: Callable[[int], None] | None = None, *, dump_name: str = "database.sql"
) -> int:
    """Write the archive in the layout of ``backup.sh`` into ``output``; returns the number of stored files.

    ``database.sql`` (``database.sql.enc`` of an encrypted backup: the dump is encrypted already in the folder
    of the work and again with the whole archive) must already be in ``work``. Files that disappear while
    the archive is written (deleted meanwhile) are left out.
    """
    from rentalars import __version__

    (work / "VERSION").write_text(f"{__version__}\n", encoding="utf-8")
    config = settings.RENTALARS_CONFIG_PATH
    count = 0
    with tarfile.open(fileobj=output, mode="w|gz", format=tarfile.GNU_FORMAT) as archive:
        _add(archive, work / dump_name, dump_name, mode=0o600)
        if config and Path(config).is_file():
            _add(archive, Path(config), "rentalars.conf", mode=0o600)
        _add(archive, work / "VERSION", "VERSION", mode=0o644)
        entries = list(_media_files())
        done = {name for _path, name in entries}
        for position, (path, name) in enumerate(entries):
            try:
                count += _add(archive, path, name)
            except FileNotFoundError:
                continue
            if progress is not None and position % 50 == 0:
                progress(40 + 50 * position // max(len(entries), 1))
        # A file deleted while the archive was written has moved to the trash, which was listed before: take what
        # the trash holds now and the archive does not have yet (the dump still names the file).
        for path, name in _media_files():
            if name in done or not name.startswith("media/.deleted"):
                continue
            try:
                count += _add(archive, path, name)
            except FileNotFoundError:
                continue
    return count


def verify(path: Path, key: str | None) -> list[str]:
    """Read a backup back completely, as ``backup.sh`` does; returns the names in it.

    Raises:
        BackupError: It cannot be decrypted, the compression is damaged, or
            ``database.sql`` is missing.
    """
    names: list[str] = []
    with path.open("rb") as raw:
        source: Any = OpenSSLReader(raw, key) if key else raw
        try:
            with gzip.GzipFile(fileobj=source, mode="rb") as unpacked:
                with tarfile.open(fileobj=unpacked, mode="r|") as archive:
                    names = [member.name for member in archive]
                # To the end of the compressed data: only then is its checksum compared.
                while unpacked.read(1024 * 1024):
                    pass
        except (OSError, EOFError, tarfile.TarError) as error:
            raise BackupError(_("The backup could not be read back: %(error)s") % {"error": error}) from error
    if "database.sql" not in names and "database.sql.enc" not in names:
        raise BackupError(_("The backup could not be read back: database.sql is missing."))
    return names


# --- The task in the background (NFA-041) ----------------------------------------------------------------


def running_backup() -> Any:
    """A backup from the browser that is waiting or running, if there is one."""
    from rentalars.core.models import BackgroundJob, JobStatus

    return BackgroundJob.objects.filter(kind="backup", status__in=[JobStatus.QUEUED, JobStatus.RUNNING]).first()


def start(user: Any) -> Any:
    """Start a backup as a task in the background; returns the task (ADM-010).

    With encrypted backups the key of this backup is made here, so that the
    API can return it at once; it is stored encrypted with the task.

    Raises:
        BackupError: Another backup from the browser is being written.
    """
    from rentalars.core.audit import record_event
    from rentalars.core.crypto import encrypt_secret
    from rentalars.core.jobs import start_job
    from rentalars.core.models import SystemSettings

    if running_backup() is not None:
        raise BackupError(_("A backup is being written already. Wait until it is ready."))
    params: dict[str, Any] = {}
    if backups_are_encrypted():
        params["key"] = encrypt_secret(new_key())
    record_event(SystemSettings.load(), "backup.web", {"by": str(user), "encrypted": bool(params)})
    return start_job("backup", params, user=user, title=_("Backup"))


def key_of(job: Any) -> str | None:
    """The key of an encrypted backup from the browser, for the one who made it; ``None`` if it is not encrypted."""
    from rentalars.core.crypto import SecretUnreadableError, decrypt_secret

    token = (job.params or {}).get("key")
    if not token:
        return None
    try:
        return decrypt_secret(token)
    except SecretUnreadableError:
        return None


def run_job(job: Any) -> str:
    """The background task: dump, pack, encrypt if asked, read back, move into place."""
    from rentalars.core.crypto import encrypt_secret
    from rentalars.core.jobs import report_progress

    key = key_of(job)
    if key is None and backups_are_encrypted():
        # Encryption was switched on after the start: then this backup is encrypted too.
        key = new_key()
        job.params = {**job.params, "key": encrypt_secret(key)}
    if key is not None and not _KEY_FORMAT.match(key):
        raise BackupError(_("The key of the backup cannot be read any more."))
    report_progress(job, 2, _("Checking the free space …"))
    check_space()
    data_dir = Path(settings.DATA_DIR)
    work = Path(tempfile.mkdtemp(prefix=".web-backup-", dir=data_dir))
    try:
        report_progress(job, 5, _("Backing up the database …"))
        dump_name = "database.sql.enc" if key else "database.sql"
        dump_database(work / dump_name, work, key)
        report_progress(job, 40, _("Packing the files …"))
        partial = work / "archive.partial"
        descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as raw:
            if key is None:
                files = write_archive(raw, work, lambda percent: report_progress(job, percent), dump_name=dump_name)
            else:
                # Straight through the cipher: no unencrypted archive on the disk, not even for a moment.
                writer = OpenSSLWriter(raw, key)
                files = write_archive(
                    writer,  # type: ignore[arg-type]
                    work,
                    lambda percent: report_progress(job, percent),
                    dump_name=dump_name,
                )
                writer.finish()
        (work / dump_name).unlink()
        report_progress(job, 92, _("Reading the backup back …"))
        verify(partial, key)
        stamp = timezone.localtime().strftime("%Y-%m-%d_%H%M%S")
        name = f"rentalars-{stamp}-web.tar.gz" + (".enc" if key else "")
        relative = f"{BACKUP_FOLDER}/{job.pk}-{secrets.token_hex(8)}.tar.gz" + (".enc" if key else "")
        final = Path(settings.MEDIA_ROOT) / relative
        final.parent.mkdir(parents=True, exist_ok=True)
        final.parent.chmod(0o750)
        size = partial.stat().st_size
        # NGINX (group of the service account) delivers it after the check of the rights.
        partial.chmod(0o640)
        os.replace(partial, final)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    job.result_file.name = relative
    job.result_name = name
    job.result = {"size": size, "files": files, "encrypted": key is not None, "file_name": name}
    from rentalars.core.selfcheck import size_text

    summary = ngettext("%(size)s, %(count)d file", "%(size)s, %(count)d files", files) % {
        "size": size_text(size),
        "count": files,
    }
    if key is not None:
        return _(
            "The backup is ready (%(summary)s). It is encrypted with a key of its own;"
            " you find it under Settings → Backup and encryption."
        ) % {"summary": summary}
    return _("The backup is ready (%(summary)s).") % {"summary": summary}
