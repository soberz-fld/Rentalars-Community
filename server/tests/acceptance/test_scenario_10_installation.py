# SPDX-License-Identifier: GPL-3.0-or-later
"""Acceptance scenario 10 – Installation (catalogue chapter 11).

The scenario itself needs a freshly installed Ubuntu server and a person with
a stopwatch; no unit test can replace that. How it was run and with which
result is recorded in ``docs/betrieb/installation.md`` ("Erprobung").

What can be checked automatically is checked here: that the package contains
everything the scenario relies on, and that the pieces fit together – the
service starts the program the installer puts in place, NGINX talks to the
socket the service opens, the update makes its backup before it changes
anything.
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path
from unittest import SkipTest

from django.conf import settings
from django.test import SimpleTestCase

ROOT = Path(settings.BASE_DIR)
DEPLOY = ROOT / "deploy"


def read(name: str) -> str:
    """Read a file of the deploy folder."""
    return (DEPLOY / name).read_text(encoding="utf-8")


class Scenario10Installation(SimpleTestCase):
    """NFA-027 to NFA-036, NFA-042."""

    def test_package_contains_the_server_scripts_and_they_are_valid_shell(self) -> None:
        for name in ("install.sh", "update.sh", "backup.sh", "restore.sh", "rentalars", "lib.sh"):
            path = DEPLOY / name
            self.assertTrue(path.is_file(), name)
            result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, f"{name}: {result.stderr}")
        for name in ("install.sh", "update.sh", "backup.sh", "restore.sh", "rentalars"):
            self.assertTrue((DEPLOY / name).stat().st_mode & 0o111, f"{name} is not executable")

    def test_installer_sets_up_everything_on_one_server(self) -> None:
        """NFA-028, NFA-031: packages, environment, service, database, NGINX, certificate, jobs. Also NFA-008, NFA-029."""
        installer = read("install.sh")
        # The list of packages is in lib.sh (system_packages), for Ubuntu and Raspberry Pi OS (NFA-070).
        self.assertIn('mapfile -t packages < <(system_packages "${SYSTEM_ID}"', installer)
        for package in ("python3-venv", "nginx", "mariadb-server"):
            self.assertIn(package, read("lib.sh"))
        for step in (
            "useradd --system",
            "build_release",
            "CREATE DATABASE IF NOT EXISTS rentalars CHARACTER SET utf8mb4",
            "CREATE USER IF NOT EXISTS 'rentalars'@'localhost'",
            "manage migrate",
            "manage collectstatic",
            "install_units",
            # Every timer the release brings: backup, maintenance, mail fetch (deploy/systemd/*.timer).
            "enable_timers",
            "nginx -t",
            "manage prepare_setup",
        ):
            self.assertIn(step, installer, step)
        # NFA-064: the key for the first-run setup exists before anything answers requests.
        key = installer.index('setup_address="$(manage prepare_setup)"')
        self.assertLess(key, installer.index("systemctl enable --quiet --now rentalars.service"))
        for start_of_nginx in re.finditer(r"systemctl (?:restart|reload|start) nginx", installer):
            self.assertLess(key, start_of_nginx.start())
        self.assertEqual(installer.count("manage prepare_setup"), 1)
        # Secrets are generated on the server, never shipped.
        self.assertIn("openssl rand", installer)
        self.assertNotRegex(installer, r"password\s*=\s*['\"]\w+['\"]")
        # Nothing but NGINX, the application and MariaDB is installed as a service (scenario 10).
        for foreign in ("redis", "rabbitmq", "celery", "elasticsearch", "docker"):
            self.assertNotIn(foreign, installer.lower())

    def test_installer_refuses_to_overwrite_an_installation(self) -> None:
        self.assertIn("Rentalars ist hier schon installiert", read("install.sh"))

    def test_all_three_ways_to_a_certificate_are_supported(self) -> None:
        """NFA-035: automatic renewal, DNS proof without public reachability, own certificate."""
        installer = read("install.sh")
        self.assertRegex(installer, r"certbot certonly .*\n?.*--webroot")
        self.assertIn("--preferred-challenges dns", installer)
        self.assertIn("--dns-${dns_plugin}", installer)
        self.assertIn("--cert", installer)
        self.assertIn("--key", installer)
        self.assertIn('--deploy-hook "systemctl reload nginx"', installer)

    def test_service_starts_what_the_installer_puts_in_place(self) -> None:
        library = read("lib.sh")
        unit = read("systemd/rentalars.service")
        self.assertIn('RENTALARS_HOME="/opt/rentalars"', library)
        self.assertIn("ExecStart=/opt/rentalars/venv/bin/gunicorn rentalars.wsgi:application", unit)
        self.assertIn("WorkingDirectory=/opt/rentalars/app", unit)
        self.assertIn("User=rentalars", unit)
        self.assertIn("RENTALARS_CONFIG=/etc/rentalars/rentalars.conf", unit)
        socket = re.search(r"--bind unix:(\S+)", unit).group(1)  # type: ignore[union-attr]
        self.assertIn(f"server unix:{socket}", read("nginx/rentalars.conf"))
        self.assertIn(f"--unix-socket {socket}", library)

    def test_nginx_speaks_https_and_protects_uploaded_files(self) -> None:
        """NFA-030, NFA-048, NFA-007. Also NFA-005."""
        site = read("nginx/rentalars.conf")
        self.assertIn("listen 443 ssl", site)
        self.assertIn("ssl_protocols TLSv1.2 TLSv1.3;", site)
        self.assertIn("return 301 https://$host$request_uri;", site)
        media = site[site.index("location /protected-media/") :]
        self.assertIn("internal;", media[: media.index("}")])
        self.assertIn("limit_req zone=rentalars_login", site)
        proxy = read("nginx/rentalars-proxy.conf")
        self.assertIn("proxy_set_header X-Forwarded-Proto $scheme;", proxy)
        # The address used for the login lockout is set by NGINX, not taken from the browser.
        self.assertIn("proxy_set_header X-Forwarded-For $remote_addr;", proxy)

    def test_backup_runs_daily_and_holds_database_files_and_configuration(self) -> None:
        """NFA-015."""
        self.assertIn("OnCalendar=*-*-* 02:30:00", read("systemd/rentalars-backup.timer"))
        self.assertIn("Persistent=true", read("systemd/rentalars-backup.timer"))
        self.assertIn(
            "ExecStart=/bin/bash /opt/rentalars/app/deploy/backup.sh", read("systemd/rentalars-backup.service")
        )
        backup = read("backup.sh")
        self.assertIn("mariadb-dump", backup)
        self.assertIn("--single-transaction", backup)
        # The name of the dump is a variable (database.sql, or database.sql.enc for an encrypted backup).
        self.assertRegex(backup, r"tar -czf .* \"\$\{dump_name\}\" rentalars\.conf VERSION .* media")
        self.assertIn('dump_name="database.sql"', backup)
        # The password never appears on a command line.
        self.assertIn("--defaults-extra-file", backup)
        self.assertNotIn("--password", backup)

    def test_update_backs_up_first_and_goes_back_by_itself(self) -> None:
        """NFA-034, NFA-054."""
        update = read("update.sh")
        prerequisites = update.index("check_python_version")
        backup = update.index('backup.sh" --keep)', prerequisites)
        new_release = update.index("build_release")
        stop = update.index('systemctl stop "${SERVICE_NAME}"', new_release)
        migrate = update.index("manage migrate")
        self.assertLess(prerequisites, backup)
        self.assertLess(backup, new_release)
        self.assertLess(new_release, stop)
        self.assertLess(stop, migrate)
        self.assertIn("go_back", update[migrate:])
        self.assertIn("--rollback", update)
        self.assertIn("update)", read("rentalars"))
        self.assertIn("rollback)", read("rentalars"))

    def test_database_and_application_server_are_tuned_for_the_reference_system(self) -> None:
        """NFA-038, NFA-042: 4 cores, 8 GB, at most half of the memory in normal operation. Also NFA-002."""
        database = read("mariadb/60-rentalars.cnf")
        self.assertIn("innodb_buffer_pool_size = 1G", database)
        self.assertIn("character-set-server    = utf8mb4", database)
        self.assertIn("bind-address            = 127.0.0.1", database)
        # One request per process: threads would share the interpreter lock (NFA-013, NFA-039).
        service = read("systemd/rentalars.service")
        # A Raspberry Pi with less than 4 GB gets fewer (NFA-070, lib.sh adapt_workers); the file stays as it is.
        self.assertRegex(service, r"--workers 5 --preload ")
        self.assertNotRegex(service, r"(?m)^\s+--threads")
        # The application gives up on a long request before NGINX does; then its changes are undone for sure.
        patience_of_the_application = int(re.search(r"--timeout (\d+)", service).group(1))  # type: ignore[union-attr]
        patience_of_nginx = int(re.search(r"proxy_read_timeout (\d+)s", read("nginx/rentalars-proxy.conf")).group(1))  # type: ignore[union-attr]
        self.assertLess(patience_of_the_application, patience_of_nginx)

    def test_configuration_is_one_file_with_defaults(self) -> None:
        """NFA-032."""
        example = read("rentalars.conf.example")
        for section in ("[rentalars]", "[database]", "[email]", "[backup]"):
            self.assertIn(section, example)
        required = [line for line in example.splitlines() if line and not line.startswith(("#", "["))]
        self.assertEqual([line.split(" = ")[0] for line in required], ["url", "secret_key", "name", "user", "password"])

    def test_operation_manuals_exist(self) -> None:
        """NFA-047: installation, update, backup and restore are documented for the operator."""
        for name in ("installation.md", "betrieb.md", "aktualisierung.md", "sicherung.md", "import.md"):
            text = (ROOT / "docs" / "betrieb" / name).read_text(encoding="utf-8")
            self.assertGreater(len(text), 1500, name)
        self.assertIn("sudo ./deploy/install.sh", (ROOT / "docs/betrieb/installation.md").read_text(encoding="utf-8"))
        self.assertIn("sudo rentalars update", (ROOT / "docs/betrieb/aktualisierung.md").read_text(encoding="utf-8"))
        self.assertIn("sudo rentalars restore", (ROOT / "docs/betrieb/sicherung.md").read_text(encoding="utf-8"))


#: Runs one function of deploy/lib.sh with an NGINX that claims to have a given version.
ADAPT_SITE = """
set -euo pipefail
source "$1"
pretended_version="$2"
nginx() { echo "nginx version: nginx/${pretended_version} (Ubuntu)" >&2; }
adapt_nginx_site "$3"
"""


class UbuntuVersions(SimpleTestCase):
    """NFA-063: the scripts run on Ubuntu Server 24.04 LTS and on 26.04 LTS.

    The two bring different versions of everything the scripts touch: Python
    3.12 and 3.14, NGINX 1.24 and 1.28, MariaDB 10.11 and 11.8. Where that
    makes a difference, the scripts decide by what is installed. How the
    scripts were run on both systems is recorded in
    ``docs/betrieb/installation.md`` ("Erprobung"); here the decisions
    themselves are tested.
    """

    def site_for(self, nginx_version: str, text: str) -> str:
        """Let ``adapt_nginx_site`` rewrite a site file for an NGINX of the given version."""
        with tempfile.TemporaryDirectory() as folder:
            site = Path(folder) / "site"
            site.write_text(text, encoding="utf-8")
            result = subprocess.run(
                ["bash", "-c", ADAPT_SITE, "adapt", str(DEPLOY / "lib.sh"), nginx_version, str(site)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return site.read_text(encoding="utf-8")

    @staticmethod
    def directives(site: str) -> list[str]:
        """The lines of a site file that decide about HTTP/2, without comments."""
        lines = [line.strip() for line in site.splitlines()]
        return [line for line in lines if line.startswith(("listen", "http2")) and "80" not in line]

    def test_both_versions_are_named_and_older_ones_refused(self) -> None:
        library = read("lib.sh")
        self.assertIn('TESTED_UBUNTU_VERSIONS=("24.04" "26.04")', library)
        self.assertIn("OLDEST_UBUNTU_MAJOR=24", library)
        # The check is the function check_system of lib.sh, which also knows the Raspberry Pi
        # (NFA-070); tests/deploy/test_system.sh runs it with made-up systems (tests/unit/test_080_pi.py).
        check = library[library.index("check_system() {") :]
        check = check[: check.index("\n}\n")]
        self.assertIn("(( major >= OLDEST_UBUNTU_MAJOR ))", check)
        self.assertIn("ist zu alt", check)
        # A version nobody tried is announced, not refused.
        self.assertIn('is_tested_ubuntu "${SYSTEM_VERSION}" ||', check)
        self.assertIn("nicht erprobt", check)
        # The installer checks before it changes anything.
        installer = read("install.sh")
        self.assertLess(installer.index('check_system "${OS_RELEASE_FILE}"'), installer.index("apt-get update"))
        self.assertIn('note "System:       ${SYSTEM_NAME}${SYSTEM_NOTE}"', installer)

    def test_other_versions_are_recognised(self) -> None:
        """An interim release or a future one is not on the list; the two tried ones are."""
        script = 'source "$1"; for v in 22.04 24.04 25.10 26.04 28.04; do is_tested_ubuntu "$v" && echo "$v"; done; tested_ubuntu_versions'
        # UIX-029: the scripts speak the operator's language; German here, as the expectation is.
        result = subprocess.run(
            ["bash", "-c", script, "versions", str(DEPLOY / "lib.sh")],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "RENTALARS_LANG": "de"},
        )
        self.assertEqual(result.stdout.split("\n")[:3], ["24.04", "26.04", "24.04 LTS und 26.04 LTS"], result.stderr)

    def test_an_installation_that_survived_an_ubuntu_upgrade_is_repaired_not_damaged(self) -> None:
        """Its libraries belong to the old Python: the update sets them up again, and there is no way back."""
        library = read("lib.sh")
        self.assertIn('"$1/venv/bin/python" -c "import django"', library)
        updater = read("update.sh")
        rollback = updater[updater.index('if [[ "${1:-}" == "--rollback" ]]') : updater.index("# --- Step 1")]
        # Going back is refused before anything is switched.
        self.assertLess(rollback.index('release_runs "${PREVIOUS_RELEASE}"'), rollback.index("go_back"))
        self.assertIn("es wurde nichts verändert", rollback)
        # A failed update puts the data back without trying to start a program that cannot run.
        self.assertIn('go_back "${previous_release}" "${backup_file}" --no-safety-backup --data-only', updater)
        restore = read("restore.sh")
        self.assertLess(restore.index("if ${data_only}; then"), restore.index("manage migrate --noinput"))
        self.assertIn(
            "Von Ubuntu 24.04 auf 26.04 wechseln", (ROOT / "docs/betrieb/aktualisierung.md").read_text("utf-8")
        )

    def test_the_oldest_python_is_the_one_of_ubuntu_24(self) -> None:
        """NFA-054: Ubuntu 24.04 has Python 3.12, Ubuntu 26.04 has 3.14; the program runs on both."""
        library = read("lib.sh")
        self.assertIn("MIN_PYTHON_MAJOR=3", library)
        self.assertIn("MIN_PYTHON_MINOR=12", library)
        project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('requires-python = ">=3.12"', project)
        # The workflow lives in the repository root, next to the folder of the server; the installation package
        # (which holds only the server) and a copy without hidden folders have none.
        candidates = [folder / ".github/workflows/ci.yml" for folder in (ROOT, ROOT.parent)]
        workflow_file = next((path for path in candidates if path.exists()), None)
        if workflow_file is None:
            raise SkipTest("The CI workflow (.github/workflows/ci.yml) is not in this copy.")
        workflow = workflow_file.read_text(encoding="utf-8")
        self.assertIn('python: "3.12"', workflow)
        self.assertIn('python: "3.14"', workflow)
        self.assertIn('mariadb: "mariadb:10.11"', workflow)
        self.assertIn('mariadb: "mariadb:11.8"', workflow)

    def test_http2_is_written_the_way_the_installed_nginx_understands(self) -> None:
        """NGINX 1.25.1 introduced "http2 on;" and warns about the word on the listen line; 1.24 knows only the word."""
        template = read("nginx/rentalars.conf")
        # The first two lines belong to the server that refuses unknown names (NFA-049).
        refusing = ["listen 443 ssl default_server;", "listen [::]:443 ssl default_server;"]
        old_form = [*refusing, "listen 443 ssl http2;", "listen [::]:443 ssl http2;"]
        new_form = [*refusing, "listen 443 ssl;", "listen [::]:443 ssl;", "http2 on;"]
        for version, expected in (
            ("1.24.0", old_form),
            ("1.25.0", old_form),
            ("1.25.1", new_form),
            ("1.28.3", new_form),
        ):
            with self.subTest(nginx=version):
                site = self.site_for(version, template)
                self.assertEqual(self.directives(site), expected)
                # Doing it again changes nothing.
                self.assertEqual(self.site_for(version, site), site)

    def test_a_site_is_rewritten_when_nginx_changes_under_it(self) -> None:
        """After Ubuntu was upgraded from 24.04 to 26.04, the next update brings the site into the new form."""
        template = read("nginx/rentalars.conf")
        on_ubuntu_24 = self.site_for("1.24.0", template)
        on_ubuntu_26 = self.site_for("1.28.3", on_ubuntu_24)
        self.assertEqual(on_ubuntu_26, self.site_for("1.28.3", template))
        self.assertEqual(self.site_for("1.24.0", on_ubuntu_26), on_ubuntu_24)
        updater = read("update.sh")
        self.assertIn("refresh_server_configuration", updater)
        self.assertIn('adapt_nginx_site "${NGINX_SITE}"', read("lib.sh"))

    def test_a_server_without_ipv6_and_the_site_without_tls_are_handled(self) -> None:
        template = read("nginx/rentalars.conf")
        without_ipv6 = "\n".join(line for line in template.splitlines() if "listen [::]" not in line) + "\n"
        refusing = ["listen 443 ssl default_server;"]
        self.assertEqual(
            self.directives(self.site_for("1.28.3", without_ipv6)), [*refusing, "listen 443 ssl;", "http2 on;"]
        )
        self.assertEqual(self.directives(self.site_for("1.24.0", without_ipv6)), [*refusing, "listen 443 ssl http2;"])
        # The site used while the certificate is fetched has no TLS and must stay as it is.
        http_only = read("nginx/rentalars-http-only.conf")
        for version in ("1.24.0", "1.28.3"):
            self.assertEqual(self.site_for(version, http_only), http_only)

    def test_a_refused_nginx_configuration_is_put_back(self) -> None:
        """A working web server is never traded for a tidy one."""
        library = read("lib.sh")
        refresh = library[library.index("refresh_server_configuration() {") :]
        refresh = refresh[: refresh.index("\n}\n")]
        self.assertLess(refresh.index('cp -p "${NGINX_SITE}" "${keep}/site"'), refresh.index("adapt_nginx_site"))
        self.assertLess(refresh.index("adapt_nginx_site"), refresh.index("nginx -t -q"))
        self.assertIn('cp -p "${keep}/site" "${NGINX_SITE}"', refresh[refresh.index("else") :])

    def test_database_settings_are_known_to_both_mariadb_versions(self) -> None:
        """MariaDB 11.8 warns about settings that 10.11 took silently, and will refuse them one day."""
        settings_file = read("mariadb/60-rentalars.cnf")
        active = [line.split("=")[0].strip() for line in settings_file.splitlines() if line and line[0] not in "#["]
        # Deprecated in MariaDB 11: the default has been "on" for both versions anyway.
        self.assertNotIn("innodb_file_per_table", active)
        self.assertEqual(
            sorted(active),
            sorted(
                [
                    "bind-address",
                    "skip-name-resolve",
                    "character-set-server",
                    "collation-server",
                    "innodb_buffer_pool_size",
                    "innodb_log_file_size",
                    "innodb_flush_log_at_trx_commit",
                    "max_connections",
                    "sql_mode",
                    "innodb_lock_wait_timeout",
                    "slow_query_log",
                    "slow_query_log_file",
                    "long_query_time",
                ]
            ),
            "a new setting must be tried on MariaDB 10.11 and 11.8 before it is added to this list",
        )
        # An installation that still has the line loses it with the next update.
        self.assertIn("innodb_file_per_table", read("lib.sh"))

    def test_nothing_large_is_unpacked_into_the_main_memory(self) -> None:
        """Since Ubuntu 24.10 /tmp is kept in memory."""
        self.assertIn('mktemp -d "${backup_dir}/.restore.XXXXXX"', read("restore.sh"))
        self.assertIn('mktemp -d "${RENTALARS_HOME}/.unpacked.XXXXXX"', read("update.sh"))
        self.assertIn('mktemp -d "${backup_dir}/.in-progress.XXXXXX"', read("backup.sh"))

    def test_the_command_belongs_to_the_installed_version(self) -> None:
        """/usr/local/bin/rentalars runs the command of the release in use; an update writes it anew.

        NFA-069: it is a small script that runs the release's command through bash,
        not a link: a lost execute bit no longer turns it into "command not found".
        """
        self.assertIn("install_cli", read("install.sh"))
        lib = read("lib.sh")
        self.assertIn("exec /bin/bash /opt/rentalars/app/deploy/rentalars", lib)
        self.assertIn("    install_cli\n}", lib)  # refresh_server_configuration ends with it
        # NFA-077: the replacement of the old link at the first call as root is gone – every update writes the script
        # (refresh_server_configuration).
        self.assertNotIn("-L /usr/local/bin/rentalars", read("rentalars"))

    def test_scripts_run_without_their_execute_bit(self) -> None:
        """NFA-069: the scripts call each other through bash; every release gets its execute bits back.

        A new release when it is built, the running one before an update – it is the one that runs again after
        going back –, and the previous one when it is switched on again.
        """
        lib, update = read("lib.sh"), read("update.sh")
        self.assertIn('chmod 755 "$1/deploy/"*.sh "$1/deploy/rentalars"', lib)
        self.assertIn('make_scripts_executable "${release}/app"', lib)
        self.assertLess(
            update.index('make_scripts_executable "$(readlink -f "${APP_DIR}")"'),
            update.index('backup_file="$(bash "${APP_DIR}/deploy/backup.sh" --keep)"'),
        )
        self.assertLess(
            update.index('make_scripts_executable "${previous}/app"'), update.index('activate_release "${previous}"')
        )
        for name in ("rentalars", "update.sh", "install.sh", "encryption.sh", "move-database.sh"):
            text = read(name)
            for line in text.splitlines():
                if '"${APP_DIR}/deploy/' in line and ".sh" in line and "cp " not in line:
                    self.assertIn("bash ", line, f"{name}: {line.strip()}")
        backup_unit = (DEPLOY / "systemd" / "rentalars-backup.service").read_text(encoding="utf-8")
        self.assertIn("ExecStart=/bin/bash /opt/rentalars/app/deploy/backup.sh", backup_unit)
