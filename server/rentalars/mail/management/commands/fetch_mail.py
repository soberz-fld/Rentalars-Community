# SPDX-License-Identifier: GPL-3.0-or-later
"""Command ``fetch_mail``: fetch new mails of every mailbox of the correspondence (EML-005, EML-041).

The timer ``rentalars-mail.timer`` starts it every minute; the command itself
fetches a mailbox only when the interval of the mail settings is over since
its last fetch (default two minutes). ``--now`` fetches at once. A mailbox
that fails does not stop the others; the exit status tells that one failed.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from rentalars.mail.fetching import fetch_mail


class Command(BaseCommand):
    """Fetches the mailboxes of the correspondence when they are due."""

    help = "Fetches new mails of the mailboxes of the correspondence and assigns them to projects by their tag."

    def add_arguments(self, parser: CommandParser) -> None:
        """``--now``: do not wait for the interval."""
        parser.add_argument("--now", action="store_true", help="fetch even if the interval is not over")

    def handle(self, *args: Any, **options: Any) -> None:
        """Fetch and report one line per mailbox; a problem sets the exit status."""
        result = fetch_mail(force=options["now"])
        if result.skipped:
            self.stdout.write(result.skipped)
            return
        for part in result.mailboxes:
            self.stdout.write(
                _(
                    "%(mailbox)s: %(looked_at)d new mails looked at; %(assigned)d assigned, "
                    "%(unknown)d with an unknown tag, %(inquiries)d inquiries."
                )
                % {
                    "mailbox": part.mailbox,
                    "looked_at": part.looked_at,
                    "assigned": len(part.imported),
                    "unknown": len(part.unknown),
                    "inquiries": len(part.inquiries),
                }
            )
            if part.crew_answers:
                # PER-032: answers to deployment requests by reply mail.
                self.stdout.write(
                    ngettext(
                        "%(count)d answer to a deployment request by mail.",
                        "%(count)d answers to deployment requests by mail.",
                        part.crew_answers,
                    )
                    % {"count": part.crew_answers}
                )
        if result.error:
            self.stderr.write(result.error)
            raise SystemExit(1)
