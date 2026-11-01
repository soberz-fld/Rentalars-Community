# SPDX-License-Identifier: GPL-3.0-or-later
"""Adjustments to the generated OpenAPI description (API-004)."""

from __future__ import annotations

from typing import Any

from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.openapi import AutoSchema


class RentalarsAutoSchema(AutoSchema):
    """Groups the endpoints by business module in the documentation."""

    def get_tags(self) -> list[str]:
        """Use the view's ``schema_tag`` or its module as the group name."""
        view: Any = self.view
        tag = getattr(view, "schema_tag", None) or getattr(view, "module", None)
        if tag and tag != "authenticated-only":
            return [str(tag)]
        return super().get_tags()


class ApiTokenScheme(OpenApiAuthenticationExtension):  # type: ignore[no-untyped-call]
    """Describes the personal API token in the OpenAPI document (API-006)."""

    target_class = "rentalars.accounts.authentication.ApiTokenAuthentication"
    name = "apiToken"

    def get_security_definition(self, auto_schema: Any) -> dict[str, str]:
        """Tokens travel in the ``Authorization`` header as a bearer token."""
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "rl_…",
            "description": "Personal API token, created under “My account”.",
        }
