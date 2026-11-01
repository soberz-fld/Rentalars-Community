# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests of the settings wishes: ADM-008, ADM-009, ADM-010, AUT-028.

* ADM-008 – the self-check reads processors, memory, network and running time
  from ``/proc`` (here a made-up one) and warns on little memory or high load.
* ADM-009 – what is encrypted, as the application can see it.
* ADM-010 – the backup from the browser has the layout ``rentalars restore``
  expects, is encrypted the way ``backup.sh`` encrypts when backups are, and
  dumps MariaDB without a password on the command line.
* AUT-028 – which addresses are reads of which records, deduplication,
  filters, retention, and anonymisation of the labels.
"""

from __future__ import annotations

import datetime
import io
import os
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import override_settings
from django.urls import resolve

from rentalars import __version__
from rentalars.core import access_log, backup, selfcheck
from rentalars.core.jobs import delete_old_jobs
from rentalars.core.models import AccessAction, AccessKind, AccessLogEntry, BackgroundJob, JobStatus, SystemSettings
from rentalars.core.resources import NetworkInterface, Resources, read_resources
from tests.helpers import (
    NOW,
    RentalarsTestCase,
    assert_dumped,
    dumped_rows_visible,
    make_customer,
    make_project,
    make_user,
    set_clock,
)

DEPLOY = Path(settings.BASE_DIR) / "deploy"

#: The decryption of deploy/restore.sh (try_key), with the functions of deploy/lib.sh.
RESTORE_DECRYPTION = r"""
set -euo pipefail
source "$1"
archive="$2"; work="$3"
is_encrypted_file "${archive}"
normalized="$(normalize_recovery_key "$4")"
( umask 077; printf '%s\n' "${normalized}" > "${work}/key" )
decrypt_stream "${work}/key" < "${archive}" > "${work}/archive.tar.gz" 2> /dev/null
gzip -t "${work}/archive.tar.gz"
"""

#: The look into the archive of deploy/restore.sh, line by line.
RESTORE_CHECKS = r"""
set -euo pipefail
archive="$1"; work="$2"
gzip -t "${archive}"
contents="$(tar -tzf "${archive}")"
dump_name=""
if grep -qx "database.sql.enc" <<<"${contents}"; then dump_name="database.sql.enc"; elif grep -qx "database.sql" <<<"${contents}"; then dump_name="database.sql"; fi
[[ -n "${dump_name}" ]]
tar -xzOf "${archive}" VERSION
tar -xzf "${archive}" -C "${work}" "${dump_name}" media 2>/dev/null || tar -xzf "${archive}" -C "${work}" "${dump_name}"
"""


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# --- ADM-008 --------------------------------------------------------------------------------------------


class ServerResourceTests(RentalarsTestCase):
    """ADM-008: what the server has and uses, read from /proc."""

    def fake_proc(self) -> Path:
        proc = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, proc)
        write(proc / "loadavg", "0.52 0.48 0.40 1/234 5678\n")
        write(proc / "meminfo", "MemTotal:        8000000 kB\nMemFree:  100 kB\nMemAvailable:    6000000 kB\n")
        write(proc / "uptime", f"{3 * 86400 + 4 * 3600 + 120}.55 1000.00\n")
        write(
            proc / "net" / "dev",
            "Inter-|   Receive\n face |bytes    packets\n"
            "    lo: 100 1 0 0 0 0 0 0 100 1 0 0 0 0 0 0\n"
            "  eth0: 1288490188 10 0 0 0 0 0 0 356515840 20 0 0 0 0 0 0\n"
            "docker0: 5 1 0 0 0 0 0 0 5 1 0 0 0 0 0 0\n",
        )
        write(
            proc / "net" / "if_inet6",
            "20010db8000000000000000000000010 02 40 00 80     eth0\n"
            "fe800000000000000000000000000001 02 40 20 80     eth0\n"
            "00000000000000000000000000000001 01 80 10 80       lo\n",
        )
        # This process is a worker of gunicorn: the master and its three workers are Rentalars.
        write(proc / "self" / "status", "Name:\tpython\nPPid:\t100\nVmRSS:\t   90000 kB\n")
        write(
            proc / "100" / "cmdline",
            "/opt/rentalars/venv/bin/python3\0/opt/rentalars/venv/bin/gunicorn\0rentalars.wsgi\0",
        )
        write(proc / "100" / "status", "PPid:\t1\nVmRSS:\t50000 kB\n")
        write(proc / "100" / "smaps_rollup", "Rss:  50000 kB\nPss:  40000 kB\n")
        for pid, rollup in (("101", "Pss: 30000 kB\n"), ("102", None), ("103", "Pss: 20000 kB\n")):
            write(proc / pid / "status", "PPid:\t100\nVmRSS:\t90000 kB\n")
            if rollup:
                write(proc / pid / "smaps_rollup", rollup)
        write(proc / "200" / "status", "PPid:\t1\nVmRSS:\t999999 kB\n")
        return proc

    def test_everything_is_read_from_proc(self) -> None:
        """ADM-008: cores, load, memory, own memory, network with addresses and traffic, running time."""
        resources = read_resources(self.fake_proc(), ipv4=lambda name: ["192.0.2.10"] if name == "eth0" else [])
        self.assertEqual(resources.load, (0.52, 0.48, 0.40))
        self.assertEqual((resources.memory_total, resources.memory_available), (8000000 * 1024, 6000000 * 1024))
        # Proportional sizes where the kernel tells them (shared pages count once), else the resident size.
        self.assertEqual(resources.own_memory, (40000 + 30000 + 90000 + 20000) * 1024)
        self.assertEqual(resources.own_processes, 4)
        self.assertEqual(
            resources.interfaces,
            [NetworkInterface("eth0", ["192.0.2.10", "2001:db8::10"], 1288490188, 356515840)],
        )
        self.assertAlmostEqual(resources.uptime_seconds, 273720.55)
        self.assertGreaterEqual(resources.cores or 0, 1)
        self.assertEqual(resources.as_dict()["load"], [0.52, 0.48, 0.40])

    def test_without_proc_the_values_are_left_out(self) -> None:
        """ADM-008: on another system nothing breaks – the values are simply missing."""
        empty = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, empty)
        resources = read_resources(empty, ipv4=lambda name: [])
        self.assertIsNone(resources.load)
        self.assertIsNone(resources.memory_total)
        self.assertIsNone(resources.own_memory)
        self.assertEqual(resources.interfaces, [])
        self.assertIsNone(resources.uptime_seconds)
        report = selfcheck.Report()
        with mock.patch("rentalars.core.resources.read_resources", return_value=resources):
            selfcheck._server(report)
        titles = [finding.title for finding in report.findings]
        self.assertNotIn("Arbeitsspeicher", titles)
        self.assertNotIn("Laufzeit", titles)

    def test_self_check_lists_the_server_and_warns(self) -> None:
        """ADM-008: a group "Server"; little memory or a load above twice the cores is a warning."""
        calm = Resources(
            cores=4,
            load=(1.0, 2.0, 1.5),
            memory_total=16 * 1024**3,
            memory_available=8 * 1024**3,
            own_memory=300 * 1024**2,
            own_processes=6,
            hostname="verleih-server",
            interfaces=[NetworkInterface("eth0", ["192.0.2.10"], 5 * 1024**3, 200 * 1024**2)],
            uptime_seconds=3 * 86400 + 4 * 3600,
        )
        with mock.patch("rentalars.core.resources.read_resources", return_value=calm):
            report = selfcheck.run_checks()
        server = dict(report.groups())["Server"]
        lines = {finding.title: finding for finding in server}
        self.assertEqual(lines["Prozessoren"].detail, "4 Kerne · Last 1,00 / 2,00 / 1,50 (1, 5, 15 Minuten)")
        self.assertEqual(lines["Arbeitsspeicher"].detail, "16,0 GB, davon 8,0 GB verfügbar (50 %)")
        self.assertEqual(lines["Speicher von Rentalars"].detail, "300 MB in 6 Prozessen")
        self.assertEqual(lines["Rechnername"].detail, "verleih-server")
        self.assertEqual(lines["Netzwerk eth0"].detail, "192.0.2.10 – empfangen 5,0 GB, gesendet 200 MB seit dem Start")
        self.assertTrue(lines["Laufzeit"].detail.startswith("3 Tage, 4 Stunden – seit "))
        self.assertTrue(all(finding.state == selfcheck.OK for finding in server))
        self.assertIs(report.resources, calm)
        self.assertEqual(selfcheck.summary_for_api(report)["resources"]["hostname"], "verleih-server")

        busy = Resources(cores=2, load=(9.0, 4.5, 3.0), memory_total=8 * 1024**3, memory_available=700 * 1024**2)
        with mock.patch("rentalars.core.resources.read_resources", return_value=busy):
            report = selfcheck.Report()
            selfcheck._server(report)
        states = {finding.title: finding.state for finding in report.findings}
        self.assertEqual(states["Prozessoren"], selfcheck.WARNING)
        self.assertEqual(states["Arbeitsspeicher"], selfcheck.WARNING)
        # The load over one minute alone is no reason: a single PDF drives it up for a moment.
        spike = Resources(cores=2, load=(9.0, 3.0, 1.0))
        with mock.patch("rentalars.core.resources.read_resources", return_value=spike):
            report = selfcheck.Report()
            selfcheck._server(report)
        self.assertEqual(report.findings[0].state, selfcheck.OK)

    def test_sizes_and_durations_read_well(self) -> None:
        """ADM-008: sizes and running times in German."""
        self.assertEqual(selfcheck.size_text(0), "0 KB")
        self.assertEqual(selfcheck.size_text(21_000), "21 KB")
        self.assertEqual(selfcheck.size_text(512 * 1024**2), "512 MB")
        self.assertEqual(selfcheck.size_text(int(7.8 * 1024**3)), "7,8 GB")
        self.assertEqual(selfcheck.duration_text(18 * 60 + 5), "18 Minuten")
        self.assertEqual(selfcheck.duration_text(3600 + 60), "1 Stunde, 1 Minute")
        self.assertEqual(selfcheck.duration_text(86400 + 7200), "1 Tag, 2 Stunden")


# --- ADM-009, ADM-010 ---------------------------------------------------------------------------------


class BackupFolderMixin:
    """A data folder, a configuration file and stored files of their own for each test."""

    encrypt = False

    def setUp(self) -> None:
        super().setUp()  # type: ignore[misc]
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)  # type: ignore[attr-defined]
        self.data = self.folder / "data"
        media = self.data / "media"
        write(media / "company" / "logo.png", "logo")
        write(media / "projects" / "1" / "Bühnenplan.pdf", "%PDF plan")
        write(media / backup.BACKUP_FOLDER / "1-old.tar.gz", "an earlier backup from the browser")
        self.config = self.folder / "rentalars.conf"
        self.write_config(encrypt=self.encrypt)
        override = override_settings(
            DATA_DIR=self.data, MEDIA_ROOT=str(media), RENTALARS_CONFIG_PATH=self.config, SERVE_MEDIA_VIA_NGINX=False
        )
        override.enable()
        self.addCleanup(override.disable)  # type: ignore[attr-defined]

    def write_config(self, *, encrypt: bool) -> None:
        self.config.write_text(
            "[rentalars]\nsecret_key = test\n\n[backup]\nencrypt = " + ("true" if encrypt else "false") + "\n",
            encoding="utf-8",
        )

    def stored(self, job: BackgroundJob) -> Path:
        return Path(settings.MEDIA_ROOT) / job.result_file.name


class EncryptionStateTests(BackupFolderMixin, RentalarsTestCase):
    """ADM-009: what the application can see of the encryption."""

    def test_state_without_encryption(self) -> None:
        state = backup.encryption_state()
        if dumped_rows_visible():
            self.assertIsNone(state.database_encrypted)  # SQLite says nothing
            self.assertEqual(state.database_detail, "SQLite – nur für die Entwicklung")
        else:
            self.assertFalse(state.database_encrypted)  # the MariaDB of the tests is not encrypted
        self.assertFalse(state.backups_encrypted)
        self.assertIsNone(state.last_backup_encrypted)
        self.assertFalse(state.complete)
        self.assertEqual(state.as_dict()["command"], "sudo rentalars encryption enable")

    def test_state_with_encrypted_backups_and_recovery_key(self) -> None:
        self.write_config(encrypt=True)
        write(
            self.data / "backup-status.json",
            '{"time": "2027-03-01T02:30:00+01:00", "file": "/var/backups/rentalars/r.tar.gz.enc", "encrypted": true,'
            ' "size": 1000, "free_mb": 5000}',
        )
        key = self.folder / "recovery-key"
        key.write_text("x\n", encoding="utf-8")
        with mock.patch.object(backup, "RECOVERY_KEY_FILE", key):
            state = backup.encryption_state()
        self.assertTrue(state.backups_encrypted)
        self.assertTrue(state.last_backup_encrypted)
        self.assertTrue(state.recovery_key_exists)
        # On SQLite there is no database server to encrypt; the backups are what counts.
        # The MariaDB of the tests is not encrypted, so there it is not complete.
        self.assertEqual(state.complete, dumped_rows_visible())
        self.assertEqual(backup.last_server_backup()["file"], "/var/backups/rentalars/r.tar.gz.enc")

    def test_the_spellings_of_backup_sh_switch_encryption_on(self) -> None:
        for value, expected in (
            ("true", True),
            ("yes", True),
            ("on", True),
            ("1", True),
            ("false", False),
            ("", False),
        ):
            self.config.write_text(f"[backup]\nencrypt = {value}\n", encoding="utf-8")
            self.assertEqual(backup.backups_are_encrypted(), expected, value)


class WebBackupTests(BackupFolderMixin, RentalarsTestCase):
    """ADM-010: a backup from the browser in the format of ``sudo rentalars backup``."""

    def setUp(self) -> None:
        super().setUp()
        self.user = make_user("chef", superuser=True)
        make_customer("Kulturverein Nordstadt")

    def test_the_archive_has_the_layout_of_backup_sh(self) -> None:
        job = backup.start(self.user)
        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.DONE, job.message)
        self.assertRegex(job.result_name, r"^rentalars-\d{4}-\d\d-\d\d_\d{6}-web\.tar\.gz$")
        self.assertTrue(job.result_file.name.startswith("jobs/backups/"))
        self.assertTrue(job.message.startswith("Die Sicherung ist fertig ("), job.message)
        path = self.stored(job)
        # NGINX (group of the service account) delivers it; nobody else on the server reads it.
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)
        with tarfile.open(path, "r:gz") as archive:
            names = archive.getnames()
            self.assertEqual(names[:3], ["database.sql", "rentalars.conf", "VERSION"])
            self.assertIn("media/company/logo.png", names)
            self.assertIn("media/projects/1/Bühnenplan.pdf", names)
            # Backups inside backups would only double their size.
            self.assertFalse([name for name in names if name.startswith("media/jobs/backups")], names)
            self.assertEqual(archive.extractfile("VERSION").read(), f"{__version__}\n".encode())
            self.assertEqual(archive.getmember("database.sql").mode, 0o600)
            self.assertEqual(archive.getmember("rentalars.conf").mode, 0o600)
            sql = archive.extractfile("database.sql").read().decode("utf-8")
        self.assertIn("CREATE TABLE", sql)
        assert_dumped(self, sql, "Kulturverein Nordstadt")
        self.assertEqual(job.result["files"], 2)  # the earlier backup from the browser is left out
        self.assertFalse(job.result["encrypted"])
        # Nothing is left of the work: no dump, no half archive.
        self.assertEqual(list(self.data.glob(".web-backup-*")), [])

    @mock.patch.dict(os.environ, {"LC_ALL": "C"})
    def test_restore_sh_accepts_the_archive(self) -> None:
        """ADM-010: the checks and the unpacking of deploy/restore.sh, run on the archive."""
        restore = (DEPLOY / "restore.sh").read_text(encoding="utf-8")
        for line in RESTORE_CHECKS.strip().splitlines()[2:]:
            self.assertIn(line.strip(), restore)
        job = backup.start(self.user)
        job.refresh_from_db()
        work = self.folder / "restore"
        work.mkdir()
        result = subprocess.run(
            ["bash", "-c", RESTORE_CHECKS, "restore", str(self.stored(job)), str(work)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f"{__version__}\n")
        assert_dumped(self, (work / "database.sql").read_text(encoding="utf-8"), "Kulturverein Nordstadt")
        self.assertEqual((work / "media" / "company" / "logo.png").read_text(encoding="utf-8"), "logo")

    def test_an_encrypted_backup_never_has_the_dump_in_plain_text_on_the_disk(self) -> None:
        """ "Temporäre Daten ebenfalls schützen" – while the archive is written, the work folder holds only the
        encrypted dump."""
        self.write_config(encrypt=True)
        seen: dict[str, bytes] = {}
        real = backup.write_archive

        def looking(output, work, progress=None, **kwargs):  # type: ignore[no-untyped-def]
            for path in work.iterdir():
                seen[path.name] = path.read_bytes()
            return real(output, work, progress, **kwargs)

        with mock.patch.object(backup, "write_archive", looking):
            job = backup.start(self.user)
        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.DONE, job.message)
        self.assertIn("database.sql.enc", seen)
        self.assertNotIn("database.sql", seen)
        for name, content in seen.items():
            self.assertNotIn(b"CREATE TABLE", content, name)
            self.assertNotIn(b"Kulturverein", content, name)

    def test_an_unencrypted_backup_keeps_the_plain_dump_as_before(self) -> None:
        self.write_config(encrypt=False)
        job = backup.start(self.user)
        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.DONE, job.message)
        self.assertIn("database.sql", backup.verify(self.stored(job), None))

    def test_an_encrypted_backup_opens_with_its_own_key_like_a_nightly_one(self) -> None:
        """ADM-010: with encrypted backups, encrypted as backup.sh does – with a key of its own."""
        self.write_config(encrypt=True)
        job = backup.start(self.user)
        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.DONE, job.message)
        key = backup.key_of(job)
        self.assertRegex(key, r"^[0-9a-f]{4}(-[0-9a-f]{4}){9}$")
        self.assertNotIn(key, str(job.params))  # stored encrypted
        self.assertNotIn(key, job.message)  # the message also goes into notifications
        self.assertTrue(job.result_name.endswith("-web.tar.gz.enc"))
        path = self.stored(job)
        raw = path.read_bytes()
        self.assertTrue(raw.startswith(b"Salted__"))
        self.assertNotIn(b"Kulturverein", raw)
        self.assertIn("database.sql.enc", backup.verify(path, key))  # The dump is encrypted inside as well
        with self.assertRaises(backup.BackupError):
            backup.verify(path, backup.new_key())
        with self.assertRaises(backup.BackupError):
            backup.verify(path, None)

        if shutil.which("openssl"):
            # docs/betrieb/verschluesselung.md: by hand, with nothing but openssl.
            key_file = self.folder / "schluessel.txt"
            key_file.write_text(key + "\n", encoding="utf-8")
            plain = self.folder / "plain.tar.gz"
            subprocess.run(
                ["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-md", "sha256",
                 "-pass", f"file:{key_file}", "-in", str(path), "-out", str(plain)],
                check=True,
            )  # fmt: skip
            with tarfile.open(plain, "r:gz") as archive:
                self.assertEqual(archive.getnames()[0], "database.sql.enc")
                # The dump inside is encrypted with the key too, and is no plain text anywhere in the archive.
                inner = archive.extractfile("database.sql.enc").read()
            self.assertNotIn(b"CREATE TABLE", inner)
            self.assertTrue(inner.startswith(b"Salted__"))
            assert_dumped(self, backup.OpenSSLReader(io.BytesIO(inner), key).read().decode("utf-8"), "Kulturverein")
            # deploy/restore.sh: the key as typed – upper case, with spaces – through lib.sh.
            work = self.folder / "work"
            work.mkdir()
            typed = key.upper().replace("-", " ")
            result = subprocess.run(
                ["bash", "-c", RESTORE_DECRYPTION, "restore", str(DEPLOY / "lib.sh"), str(path), str(work), typed],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with tarfile.open(work / "archive.tar.gz", "r:gz") as archive:
                self.assertIn("media/company/logo.png", archive.getnames())

    def test_writer_and_reader_follow_openssl(self) -> None:
        """ADM-010: what OpenSSLWriter writes, OpenSSLReader reads – in pieces of any size."""
        target = io.BytesIO()
        writer = backup.OpenSSLWriter(target, "0123-4567-89ab-cdef-0123-4567-89ab-cdef-0123-4567")
        data = os.urandom(70_000)
        for start in range(0, len(data), 1000):
            writer.write(data[start : start + 1000])
        writer.finish()
        self.assertEqual(len(target.getvalue()) % 16, 0)
        target.seek(0)
        reader = backup.OpenSSLReader(target, "0123-4567-89ab-cdef-0123-4567-89ab-cdef-0123-4567")
        self.assertEqual(reader.read(10) + reader.read(65_536) + reader.read(), data)

    def test_one_backup_at_a_time_and_enough_space(self) -> None:
        BackgroundJob.objects.create(kind="backup", title="Sicherung", status=JobStatus.RUNNING, created_by=self.user)
        with self.assertRaisesMessage(backup.BackupError, "Es wird schon eine Sicherung geschrieben."):
            backup.start(self.user)
        BackgroundJob.objects.all().delete()
        tiny = shutil._ntuple_diskusage(total=10**9, used=10**9 - 1024, free=1024)  # type: ignore[attr-defined]
        with (
            mock.patch.object(backup.shutil, "disk_usage", return_value=tiny),
            self.assertLogs("rentalars.core.jobs", "ERROR"),
        ):
            job = backup.start(self.user)
        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertIn("Im Datenordner sind nur 0 MB frei", job.message)
        self.assertFalse(job.result_file)

    def test_the_backup_goes_with_the_retention_of_tasks(self) -> None:
        job = backup.start(self.user)
        job.refresh_from_db()
        path = self.stored(job)
        self.assertTrue(path.exists())
        set_clock(NOW + datetime.timedelta(days=SystemSettings.load().retention_jobs_days + 1))
        self.assertEqual(delete_old_jobs(), 1)
        self.assertFalse(path.exists())


class MariaDbDumpTests(BackupFolderMixin, RentalarsTestCase):
    """ADM-010: the dump of MariaDB – with the options of backup.sh and the password in a file of mode 600."""

    def fake_dump(self, *, complete: bool = True) -> Path:
        tools = self.folder / "bin"
        tools.mkdir(exist_ok=True)
        record = self.folder / "record"
        script = tools / "mariadb-dump"
        script.write_text(
            "#!/bin/sh\n"
            f'printf "%s\\n" "$@" > "{record}"\n'
            'options="${1#--defaults-extra-file=}"\n'
            f'stat -c %a "$options" > "{record}.mode"\n'
            f'cat "$options" > "{record}.cnf"\n'
            'echo "CREATE TABLE t (id int);"\n'
            + ('echo "-- Dump completed on 2027-03-01  8:00:00"\n' if complete else ""),
            encoding="utf-8",
        )
        script.chmod(0o755)
        return record

    def database(self, **values: object) -> mock._patch:  # type: ignore[name-defined]
        # Only the access data: the connection of the tests stays as it is.
        return mock.patch.dict(settings.DATABASES["default"], values)

    def test_access_data_go_through_an_option_file(self) -> None:
        record = self.fake_dump()
        work = self.folder / "work"
        work.mkdir()
        with (
            mock.patch.dict(os.environ, {"PATH": f"{self.folder / 'bin'}:{os.environ['PATH']}"}),
            self.database(
                USER="rentalars",
                PASSWORD='p#ss"wo\\rd',
                HOST="db.example.de",
                PORT="3306",
                OPTIONS={"ssl_mode": "VERIFY_IDENTITY", "ssl": {"ca": "/etc/rentalars/database-ca.pem"}},
            ),
        ):
            backup._dump_mariadb(work / "database.sql", work)
        arguments = record.read_text(encoding="utf-8").splitlines()
        self.assertTrue(arguments[0].startswith("--defaults-extra-file="))
        self.assertEqual(
            arguments[1:6],
            ["--single-transaction", "--routines", "--triggers", "--default-character-set=utf8mb4", "--no-tablespaces"],
        )
        self.assertEqual(arguments[-1], str(settings.DATABASES["default"]["NAME"]))
        self.assertFalse([argument for argument in arguments if "p#ss" in argument])
        self.assertEqual(Path(f"{record}.mode").read_text(encoding="utf-8").strip(), "600")
        self.assertEqual(
            Path(f"{record}.cnf").read_text(encoding="utf-8"),
            '[client]\nuser="rentalars"\npassword="p#ss\\"wo\\\\rd"\nhost="db.example.de"\nport=3306\nssl\n'
            'ssl-ca="/etc/rentalars/database-ca.pem"\nssl-verify-server-cert\n',
        )
        # The option file is gone at once; the dump is for the service account only.
        self.assertEqual(sorted(path.name for path in work.iterdir()), ["database.sql"])
        self.assertEqual(stat.S_IMODE((work / "database.sql").stat().st_mode), 0o600)

    def test_a_remote_server_without_tls_and_a_dump_cut_off(self) -> None:
        self.fake_dump(complete=False)
        work = self.folder / "work"
        work.mkdir()
        with (
            mock.patch.dict(os.environ, {"PATH": f"{self.folder / 'bin'}:{os.environ['PATH']}"}),
            self.database(USER="r", PASSWORD="x", HOST="10.0.0.5", PORT="", OPTIONS={}),
        ):
            backup.write_client_file(work / "remote.cnf")
            with self.assertRaisesMessage(backup.BackupError, "unvollständig"):
                backup._dump_mariadb(work / "database.sql", work)
        self.assertIn("skip-ssl\n", (work / "remote.cnf").read_text(encoding="utf-8"))


# --- AUT-028 ---------------------------------------------------------------------------------------------


class AccessReferenceTests(RentalarsTestCase):
    """AUT-028: which address is a read of which record."""

    def reference(self, path: str) -> tuple[str, str] | None:
        return access_log.reference_of(resolve(path))

    def test_pages_of_the_browser(self) -> None:
        project = make_project("Stadtfest")
        number = project.number
        expected = {
            "/customers/5/": ("customer", "5"),
            "/customers/5/edit/": ("customer", "5"),
            "/customers/5/export/": ("customer", "5"),
            "/customers/5/contacts/7/": ("customer", "5"),
            "/customers/venues/5/": None,
            "/customers/": None,
            "/personnel/people/5/": ("person", "5"),
            "/personnel/people/5/timeline/": ("person", "5"),
            "/personnel/people/5/qualifications/3/certificate/": ("person", "5"),
            "/personnel/functions/3/": None,
            f"/projects/{number}/": ("project", str(project.pk)),
            f"/projects/{number}/prices/": ("project", str(project.pk)),
            f"/projects/{number}/prices/pdf/": ("project", str(project.pk)),
            f"/projects/{number}/documents/": ("project", str(project.pk)),
            f"/projects/{number}/packlist/": ("project", str(project.pk)),
            f"/projects/{number}/mails/": ("project", str(project.pk)),
            f"/projects/{number}/mails/9/": ("mail", "9"),
            f"/projects/{number}/mails/9/body/": ("mail", "9"),
            f"/projects/{number}/mails/9/attachments/11/": ("attachment", "11"),
            f"/projects/{number}/files/4/": ("project_file", "4"),
            "/documents/4/pdf/": ("document", "4"),
            "/documents/4/xml/": ("document", "4"),
            "/jobs/3/result/": ("job", "3"),
            "/jobs/3/": None,
            "/products/": None,
            "/me/": None,
        }
        for path, reference in expected.items():
            self.assertEqual(self.reference(path), reference, path)

    def test_addresses_of_the_api(self) -> None:
        expected = {
            "/api/v1/customers/5": ("customer", "5"),
            "/api/v1/customers/5/export": ("customer", "5"),
            "/api/v1/customers/5/contacts": ("customer", "5"),
            "/api/v1/customers": None,
            "/api/v1/people/5": ("person", "5"),
            "/api/v1/people/5/timeline": ("person", "5"),
            "/api/v1/people": None,
            "/api/v1/projects/5": ("project", "5"),
            "/api/v1/projects/5/history": ("project", "5"),
            "/api/v1/projects/5/material-lines": ("project", "5"),
            "/api/v1/projects/5/mails/9": ("mail", "9"),
            "/api/v1/projects/5/mails/9/attachments/11": ("attachment", "11"),
            "/api/v1/projects/5/files/4/content": ("project_file", "4"),
            "/api/v1/documents/4/pdf": ("document", "4"),
            "/api/v1/jobs/3/result": ("job", "3"),
            "/api/v1/projects": None,
            "/api/v1/products/5": None,
        }
        for path, reference in expected.items():
            self.assertEqual(self.reference(path), reference, path)

    def test_records_are_named_for_the_log(self) -> None:
        customer = make_customer("Kulturverein Nordstadt")
        target = access_log.describe("customer", str(customer.pk), make_user("lena"))
        self.assertEqual(target.label, f"{customer.number} Kulturverein Nordstadt")
        project = make_project("Stadtfest", customer=customer)
        self.assertEqual(access_log.describe("project", str(project.pk), None).label, f"{project.number} Stadtfest")
        job = BackgroundJob.objects.create(kind="export", title="Datenexport", result_name="export.zip")
        target = access_log.describe("job", str(job.pk), None)
        self.assertEqual((target.kind, target.label), (AccessKind.FULL_EXPORT, "Datenexport: export.zip"))
        labels = BackgroundJob.objects.create(kind="labels", title="Etiketten")
        self.assertIsNone(access_log.describe("job", str(labels.pk), None))
        self.assertIsNone(access_log.describe("customer", "999999", None))
        self.assertIsNone(access_log.describe("customer", "abc", None))


class AccessLogTests(RentalarsTestCase):
    """AUT-028: writing, deduplicating, filtering, keeping and forgetting."""

    def setUp(self) -> None:
        super().setUp()
        self.user = make_user("lena")
        self.customer = make_customer("Kulturverein Nordstadt")
        self.target = access_log.describe("customer", str(self.customer.pk), self.user)

    def test_the_same_read_within_five_minutes_is_one_entry(self) -> None:
        self.assertIsNotNone(access_log.record_access(self.user, self.target, AccessAction.VIEW, path="/customers/1/"))
        self.assertIsNone(
            access_log.record_access(self.user, self.target, AccessAction.VIEW, path="/customers/1/edit/")
        )
        # Another way of reading counts on its own; a download or export again for another address.
        self.assertIsNotNone(access_log.record_access(self.user, self.target, AccessAction.EXPORT, path="/a?x=1"))
        self.assertIsNotNone(access_log.record_access(self.user, self.target, AccessAction.EXPORT, path="/a?x=2"))
        self.assertIsNone(access_log.record_access(self.user, self.target, AccessAction.EXPORT, path="/a?x=2"))
        set_clock(NOW + datetime.timedelta(minutes=6))
        self.assertIsNotNone(access_log.record_access(self.user, self.target, AccessAction.VIEW, path="/customers/1/"))
        self.assertEqual(AccessLogEntry.objects.filter(action=AccessAction.VIEW).count(), 2)
        entry = AccessLogEntry.objects.first()
        self.assertEqual((entry.user_label, entry.object_type), ("lena", AccessKind.CUSTOMER))

    def test_filters(self) -> None:
        project = make_project("Stadtfest", customer=self.customer)
        project_target = access_log.describe("project", str(project.pk), self.user)
        mail = access_log.Target(AccessKind.MAIL, "9", f"{project.number}: Rider", AccessKind.PROJECT, str(project.pk))
        other = make_user("otto")
        access_log.record_access(self.user, project_target, AccessAction.VIEW)
        access_log.record_access(self.user, mail, AccessAction.VIEW)
        access_log.record_access(other, self.target, AccessAction.API, path="/api/v1/customers/1")

        def found(**filters: object) -> list[str]:
            return sorted(entry.object_type for entry in access_log.filtered_entries(**filters))  # type: ignore[arg-type]

        # A project with what belongs to it – its mails, files and documents.
        self.assertEqual(found(kind="project", object_id=str(project.pk)), ["mail", "project"])
        self.assertEqual(found(kind="mail"), ["mail"])
        self.assertEqual(found(user=other.pk), ["customer"])
        self.assertEqual(found(action="api"), ["customer"])
        self.assertEqual(found(text="Rider"), ["mail"])
        self.assertEqual(found(text="otto"), ["customer"])
        self.assertEqual(found(since=NOW + datetime.timedelta(minutes=1)), [])
        self.assertEqual(found(until=NOW + datetime.timedelta(minutes=1)), ["customer", "mail", "project"])

    def test_entries_go_after_their_retention(self) -> None:
        access_log.record_access(self.user, self.target, AccessAction.VIEW)
        system_settings = SystemSettings.load()
        self.assertEqual(system_settings.retention_access_log_days, 180)
        system_settings.retention_access_log_days = 30
        system_settings.save()
        set_clock(NOW + datetime.timedelta(days=29))
        self.assertEqual(access_log.delete_old_entries(), 0)
        set_clock(NOW + datetime.timedelta(days=31))
        self.assertEqual(access_log.delete_old_entries(), 1)

    def test_the_daily_maintenance_applies_the_retention(self) -> None:
        access_log.record_access(self.user, self.target, AccessAction.VIEW)
        set_clock(NOW + datetime.timedelta(days=181))
        output = io.StringIO()
        with mock.patch("rentalars.core.selfcheck.report_problems", return_value=0):
            call_command("run_daily_maintenance", stdout=output)
        self.assertIn("Deleted 1 access log entries past their retention (AUT-028).", output.getvalue())
        self.assertFalse(AccessLogEntry.objects.exists())

    def test_anonymising_a_customer_leaves_no_name(self) -> None:
        from rentalars.customers.services import anonymise_customer

        access_log.record_access(self.user, self.target, AccessAction.VIEW)
        anonymise_customer(self.customer)
        label = AccessLogEntry.objects.get().label
        self.assertNotIn("Kulturverein", label)
        self.assertIn("Anonymisiert", label)

    def test_anonymising_a_person_leaves_no_name(self) -> None:
        from rentalars.personnel.models import Person
        from rentalars.personnel.privacy import anonymise_person

        reader = make_user("ritaweber")
        person = Person.objects.get(user=reader)
        person.first_name, person.last_name = "Rita", "Weber"
        person.save()
        about = access_log.describe("person", str(person.pk), self.user)
        access_log.record_access(self.user, about, AccessAction.VIEW)
        access_log.record_access(reader, self.target, AccessAction.VIEW)
        anonymise_person(person)
        labels = list(AccessLogEntry.objects.values_list("label", "user_label"))
        self.assertNotIn("Rita", str(labels))
        self.assertNotIn("ritaweber", str(labels))
        self.assertIn((f"{self.customer.number} Kulturverein Nordstadt", f"anonym-{reader.pk}"), labels)


class AccessLogOnDiskTests(BackupFolderMixin, RentalarsTestCase):
    """AUT-028: downloads of files are logged with what they belong to."""

    def test_a_project_file_names_its_project(self) -> None:
        from rentalars.projects.models import ProjectFile

        project = make_project("Stadtfest")
        stored = ProjectFile.objects.create(project=project, original_name="Rider.pdf", size=4)
        stored.file.save("Rider.pdf", ContentFile(b"%PDF"), save=True)
        target = access_log.describe("project_file", str(stored.pk), None)
        self.assertEqual(
            (target.label, target.parent_kind, target.parent_id),
            (f"{project.number}: Rider.pdf", AccessKind.PROJECT, str(project.pk)),
        )
        self.assertTrue(re.match(r"^\d", target.object_id))
