# SPDX-License-Identifier: GPL-3.0-or-later
"""The configurable password policy (AUT-003)."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.utils.translation import ngettext


class ConfiguredMinimumLengthValidator:
    """Requires the minimum length set in the system settings.

    Django's own length validator takes its limit from the settings file. An
    administrator should be able to change the policy in the browser, so this
    validator reads the limit from the database each time.
    """

    def _minimum(self) -> int:
        from rentalars.core.models import SystemSettings

        return int(SystemSettings.load().password_min_length)

    def validate(self, password: str, user: Any = None) -> None:
        """Raise ``ValidationError`` if the password is too short."""
        minimum = self._minimum()
        if len(password) < minimum:
            raise ValidationError(
                ngettext(
                    "The password must contain at least %(minimum)d character.",
                    "The password must contain at least %(minimum)d characters.",
                    minimum,
                ),
                code="password_too_short",
                params={"minimum": minimum},
            )

    def get_help_text(self) -> str:
        """Describe the rule for the password form."""
        minimum = self._minimum()
        return ngettext(
            "Your password must contain at least %(minimum)d character.",
            "Your password must contain at least %(minimum)d characters.",
            minimum,
        ) % {"minimum": minimum}
