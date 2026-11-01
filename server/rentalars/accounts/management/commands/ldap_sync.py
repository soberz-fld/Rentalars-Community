# SPDX-License-Identifier: GPL-3.0-or-later
"""Command ``ldap_sync``: compare the accounts with the directory (LDAP), safe by default (AUT-029).

Without options nothing is changed – the command only says what it would do (``--dry-run`` is the default)::

    sudo rentalars ldap_sync                 # what would change
    sudo rentalars ldap_sync --apply         # do it

For every account the directory keeps, the command looks the user up: names, e-mail address and roles are brought
up to date, and an account whose user is gone from the directory or in no group with a role is deactivated (and
activated again, if the directory had deactivated it and the user is back). Nobody is created here – accounts
are created at the first login. Local (emergency) accounts are never touched, and neither is the last account
that can change the settings.

If more than half of the accounts would be deactivated, nothing is written (a wrong filter, a directory that
answers with nothing) unless ``--force`` is given. The nightly comparison (setting "compare the accounts every
night", part of ``run_daily_maintenance``) uses the same function and has no ``--force``.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from rentalars.accounts import ldap_client, ldap_sync
from rentalars.accounts.models import LdapSettings


class Command(BaseCommand):
    """Compare the accounts with the directory."""

    help = (
        "Compares the accounts of the directory (LDAP) with it; shows the differences, writes them only with --apply."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        """``--apply``, ``--dry-run`` and ``--force``."""
        parser.add_argument("--apply", action="store_true", help="write the differences (default: only show them)")
        parser.add_argument("--dry-run", action="store_true", help="only show the differences (this is the default)")
        parser.add_argument(
            "--force", action="store_true", help="with --apply: also when more than half would be deactivated"
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run the comparison and print one line per account that differs."""
        if options["apply"] and options["dry_run"]:
            raise CommandError("Use either --apply or --dry-run, not both.")
        settings = LdapSettings.load()
        if not settings.is_ready:
            raise CommandError(
                "The directory login is not switched on and set up (Einstellungen → Verzeichnis (LDAP))."
            )
        try:
            report = ldap_sync.compare_accounts(settings, apply=options["apply"], force=options["force"])
        except ldap_client.DirectoryError as error:
            raise CommandError(f"The directory could not be asked ({error.code}): {error}") from error
        for plan in report.plans:
            if plan.action == "unchanged":
                continue
            line = f"{plan.username}: {plan.action}"
            if plan.reason:
                line += f" ({plan.reason})"
            if plan.roles_before != plan.roles_after:
                line += f"  roles {', '.join(plan.roles_before) or '-'} -> {', '.join(plan.roles_after) or '-'}"
            self.stdout.write(line)
        if report.stopped:
            raise CommandError(report.stopped)
        verb = "Applied" if report.applied else "Dry run (nothing written, use --apply)"
        self.stdout.write(f"{verb}: {report.summary()}")
