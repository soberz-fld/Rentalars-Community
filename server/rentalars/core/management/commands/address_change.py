# SPDX-License-Identifier: GPL-3.0-or-later
"""Command ``address_change``: the application's end of ``sudo rentalars address apply`` (ADM-016).

The command on the server (``deploy/address.py``) runs as root; it talks to
the application only through this command, which it runs as the service
user – never the other way round:

    manage.py address_change export TOKEN
        prints the prepared change as JSON (with an uploaded certificate and
        its key, decrypted) – only for a change that is still open
    manage.py address_change record TOKEN --applied --by USER [--message …] [--details JSON]
    manage.py address_change record TOKEN --failed --by USER --message …
        notes the result, which the settings page then shows
"""

from __future__ import annotations

import json
import os
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import translation
from django.utils.translation import gettext as _

from rentalars.core import server_address
from rentalars.core.address_models import AddressChange
from rentalars.core.audit import acting_as


class Command(BaseCommand):
    """Hands a prepared change of the server address to the command on the server and records its result."""

    help = "Exports a prepared change of the server address, or records the result of applying it (ADM-016)."

    def add_arguments(self, parser: CommandParser) -> None:
        """``export TOKEN`` or ``record TOKEN --applied|--failed --by USER``."""
        parser.add_argument("action", choices=["export", "record"])
        parser.add_argument("token")
        result = parser.add_mutually_exclusive_group()
        result.add_argument("--applied", action="store_true")
        result.add_argument("--failed", action="store_true")
        parser.add_argument("--by", default="", help="the account on the server that ran the command")
        parser.add_argument("--message", default="")
        parser.add_argument("--details", default="{}", help="what the command reported, as a JSON object")

    def handle(self, *args: Any, **options: Any) -> None:
        """Do what the action says – in the operator's language (UIX-029: RENTALARS_LANG, from lib.sh)."""
        wanted = os.environ.get("RENTALARS_LANG", "") or settings.LANGUAGE_CODE
        with translation.override("de" if wanted.startswith("de") else "en"):
            self._handle(options)

    def _handle(self, options: dict[str, Any]) -> None:
        token = options["token"]
        if options["action"] == "export":
            try:
                data = server_address.export(token)
            except AddressChange.DoesNotExist:
                raise CommandError(
                    _(
                        "There is no open change of the server address with this token. It may have been applied, "
                        "discarded or replaced by a newer one – the settings page shows the current command."
                    )
                ) from None
            self.stdout.write(json.dumps(data))
            return
        if not (options["applied"] or options["failed"]):
            raise CommandError(_("record needs --applied or --failed."))
        try:
            details = json.loads(options["details"] or "{}")
        except ValueError:
            details = {}
        if not isinstance(details, dict):
            details = {}
        by = options["by"] or "root"
        try:
            with acting_as(f"server:{by}"):
                server_address.record(
                    token, applied=options["applied"], by=by, message=options["message"], details=details
                )
        except AddressChange.DoesNotExist:
            raise CommandError(_("There is no change of the server address with this token.")) from None
        self.stdout.write(_("The result is recorded."))
