# SPDX-License-Identifier: GPL-3.0-or-later
"""Uninstall script (uninstall; NFA-078): ``sudo rentalars uninstall [--dry-run|--keep-data|--purge]``.

The requirement: a removal script with three modes: --dry-run shows what would be removed; --keep-data removes the application but keeps the data; --purge also removes the database, backups and configuration, after an explicit confirmation.

The script cannot remove a real server here. ``tests/deploy/test_uninstall.sh`` builds a made-up server in a temporary
folder, with stand-ins for ``systemctl``, ``mariadb``, ``nginx``, ``certbot``, ``getent``, ``userdel`` and the like, and
runs the script against it; this module runs that test and checks what can be checked from outside: the script is in
the package and executable, the command ``rentalars`` knows it, shellcheck passes, and a call without a choice (or with
a wrong one) does nothing and ends with status 2 - this part is safe to run for real, the script stops before it
looks at the system.
"""

from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

ROOT = Path(settings.BASE_DIR)
DEPLOY = ROOT / "deploy"
SCRIPT = DEPLOY / "uninstall.sh"


def run_script(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the real script in German; only for calls that end before it looks at the system."""
    return subprocess.run(
        ["bash", str(SCRIPT), *arguments],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "RENTALARS_LANG": "de"},
        stdin=subprocess.DEVNULL,
        timeout=60,
    )


class UninstallAgainstAMadeUpServerTests(SimpleTestCase):
    """Uninstall: everything the script removes and keeps, per kind, against a made-up server."""

    def test_the_shell_test_with_stand_ins_for_the_system_commands(self) -> None:
        """Usage, --dry-run, --keep-data, --purge, the confirmation, shared databases, links, repeated runs."""
        result = subprocess.run(
            ["bash", str(ROOT / "tests/deploy/test_uninstall.sh")],
            capture_output=True,
            text=True,
            check=False,
            timeout=900,
        )
        self.assertEqual(result.returncode, 0, "\n".join(line for line in result.stdout.splitlines() if "FAIL" in line))
        self.assertRegex(result.stdout, r" 0 failed\.\n?$")
        self.assertGreater(int(result.stdout.rsplit(" cases", 1)[0].split()[-1]), 200)


class UsageIsSafeTests(SimpleTestCase):
    """Uninstall: nothing is removed by default; a wrong call changes nothing and ends with status 2."""

    def test_without_a_choice_it_prints_the_choices_and_does_nothing(self) -> None:
        result = run_script()
        self.assertEqual(result.returncode, 2)
        for choice in ("--dry-run", "--keep-data", "--purge"):
            self.assertIn(choice, result.stdout)
        self.assertIn("Ohne Angabe passiert nichts", result.stdout)

    def test_english_usage(self) -> None:
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "RENTALARS_LANG": "en"},
            stdin=subprocess.DEVNULL,
            timeout=60,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("Without a choice nothing happens", result.stdout)

    def test_wrong_calls_end_with_status_2(self) -> None:
        for arguments in (
            ("--keep-data", "--purge"),
            ("--bogus",),
            ("--keep-data", "--yes-i-really-want-to-delete-everything"),
            ("--backup-to",),
            ("--purge", "--backup-to", "/root", "--no-final-backup"),
        ):
            with self.subTest(arguments=arguments):
                result = run_script(*arguments)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_help_describes_the_three_kinds(self) -> None:
        result = run_script("--help")
        self.assertEqual(result.returncode, 0)
        for text in ("--dry-run", "--keep-data", "--purge", "--yes-i-really-want-to-delete-everything", "--backup-to"):
            self.assertIn(text, result.stdout)

    def test_the_script_requires_root_and_the_test_hooks_cannot_replace_it_on_a_real_system(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('[[ -n "${TEST_ROOT}" ]] || require_root', text)
        # A test root works only with a stand-in for every command that changes the system.
        for stub in ("systemctl", "mariadb", "nginx", "certbot", "getent", "userdel", "groupdel", "gpasswd"):
            self.assertIn(stub, text.split("for stub in ", 1)[1].split(";", 1)[0])
        # Nothing is removed without the check of the path.
        self.assertIn("path_is_safe", text)
        self.assertIn("rm -rf --one-file-system", text)
        self.assertNotRegex(text, r"rm -rf [^-\n]*\$\{[A-Za-z_]+\}/?\s*$")


class UninstallInThePackageTests(SimpleTestCase):
    """Uninstall: the script ships with the package, is executable and is reachable as ``rentalars uninstall``."""

    def test_the_script_is_valid_shell_and_executable(self) -> None:
        self.assertTrue(SCRIPT.is_file())
        self.assertTrue(SCRIPT.stat().st_mode & 0o111, "deploy/uninstall.sh is not executable")
        result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_the_package_includes_it(self) -> None:
        """scripts/build_package.sh packs everything but a list of developer folders; deploy/ is not among them."""
        build = (ROOT / "scripts/build_package.sh").read_text(encoding="utf-8")
        excluded = re.findall(r"--exclude '([^']+)'", build)
        for pattern in excluded:
            self.assertFalse(
                fnmatch.fnmatch("./deploy/uninstall.sh", pattern) or fnmatch.fnmatch("uninstall.sh", pattern),
                f"build_package.sh leaves out deploy/uninstall.sh ({pattern})",
            )
        # The installer makes every script of the version executable, whatever happened to the package on its way.
        self.assertIn('chmod 755 "$1/deploy/"*.sh', (DEPLOY / "lib.sh").read_text(encoding="utf-8"))

    def test_the_command_rentalars_runs_it_from_a_copy_of_itself(self) -> None:
        command = (DEPLOY / "rentalars").read_text(encoding="utf-8")
        self.assertIn("uninstall)", command)
        self.assertIn('cp "${APP_DIR}/deploy/uninstall.sh" "${remover}"', command)
        self.assertIn('RENTALARS_LIB="${APP_DIR}/deploy/lib.sh" exec bash "${remover}" "$@"', command)
        header = command.split("set -euo pipefail", 1)[0]
        self.assertIn("sudo rentalars uninstall", header)
        for choice in ("--dry-run", "--keep-data", "--purge"):
            self.assertIn(choice, header)

    def test_the_command_passes_the_arguments_on(self) -> None:
        """Through the dispatcher: a call without a choice ends with status 2 and the usage."""
        with tempfile.TemporaryDirectory() as temporary:
            fake = Path(temporary) / "opt/rentalars/app/deploy"
            fake.mkdir(parents=True)
            for name in ("lib.sh", "uninstall.sh"):
                shutil.copy(DEPLOY / name, fake / name)
            dispatcher = (
                (DEPLOY / "rentalars")
                .read_text(encoding="utf-8")
                .replace("/opt/rentalars", f"{temporary}/opt/rentalars")
            )
            # lib.sh names /opt/rentalars as constants; the copy of the dispatcher only needs to find it.
            lib = (
                (fake / "lib.sh")
                .read_text(encoding="utf-8")
                .replace(
                    'readonly RENTALARS_HOME="/opt/rentalars"', f'readonly RENTALARS_HOME="{temporary}/opt/rentalars"'
                )
            )
            (fake / "lib.sh").write_text(lib, encoding="utf-8")
            (fake / "rentalars").write_text(dispatcher, encoding="utf-8")
            result = subprocess.run(
                ["bash", str(fake / "rentalars"), "uninstall"],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "RENTALARS_LANG": "de"},
                stdin=subprocess.DEVNULL,
                timeout=60,
            )
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("--purge", result.stdout)

    def test_shellcheck_passes(self) -> None:
        if shutil.which("shellcheck") is None:
            self.skipTest("shellcheck is not installed")
        result = subprocess.run(
            [
                "shellcheck",
                "-x",
                "deploy/uninstall.sh",
                "deploy/rentalars",
                "deploy/lib.sh",
                "tests/deploy/test_uninstall.sh",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "LANG": "C.UTF-8"},
        )
        self.assertEqual(result.returncode, 0, result.stdout)
