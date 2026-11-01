# SPDX-License-Identifier: GPL-3.0-or-later
"""One error format for the whole API (API-008).

Every error answer looks like this::

    {
      "error": {
        "code": "validation_error",
        "message": "Die Eingabe ist ungültig.",
        "fields": {
          "article_number": [
            {"code": "invalid", "message": "Diese Artikelnummer ist bereits vergeben."}
          ]
        }
      }
    }

``code`` is meant for programs and never changes with the language;
``message`` is meant for people. ``fields`` is only present for validation
errors and names the offending input fields; errors that concern no single
field are listed under ``"_"``.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import ProtectedError
from django.http import Http404
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

#: Key for validation errors that do not belong to a single field.
GENERAL_ERRORS_KEY = "_"


class RecordAnonymised(exceptions.APIException):
    """L8: a customer or person who was anonymised cannot be filled with data again (409)."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "anonymised"
    default_detail = gettext_lazy("This record was anonymised and can no longer be changed.")


def error_response(code: str, message: str, http_status: int, fields: dict[str, Any] | None = None) -> Response:
    """Build an error answer in the uniform format."""
    body: dict[str, Any] = {"code": code, "message": message}
    if fields is not None:
        body["fields"] = fields
    return Response({"error": body}, status=http_status)


def _field_errors_from_drf(detail: Any) -> dict[str, list[dict[str, str]]]:
    """Flatten the nested error structure of the REST framework."""
    fields: dict[str, list[dict[str, str]]] = {}

    def collect(name: str, value: Any) -> None:
        if isinstance(value, dict):
            for key, inner in value.items():
                inner_name = key if name == "" else f"{name}.{key}"
                collect(GENERAL_ERRORS_KEY if key == "non_field_errors" and name == "" else inner_name, inner)
        elif isinstance(value, list):
            for position, inner in enumerate(value):
                if isinstance(inner, dict | list):
                    collect(f"{name}[{position}]" if name else GENERAL_ERRORS_KEY, inner)
                else:
                    collect(name, inner)
        else:
            code = getattr(value, "code", "invalid") or "invalid"
            fields.setdefault(name or GENERAL_ERRORS_KEY, []).append({"code": str(code), "message": str(value)})

    collect("", detail)
    return fields


def _field_errors_from_django(error: DjangoValidationError) -> dict[str, list[dict[str, str]]]:
    """Convert the validation error raised by models and services."""
    fields: dict[str, list[dict[str, str]]] = {}
    if hasattr(error, "error_dict"):
        for name, errors in error.error_dict.items():
            key = GENERAL_ERRORS_KEY if name == "__all__" else name
            for single in errors:
                for message in single.messages:
                    fields.setdefault(key, []).append({"code": single.code or "invalid", "message": str(message)})
    else:
        for single in error.error_list:
            for message in single.messages:
                fields.setdefault(GENERAL_ERRORS_KEY, []).append(
                    {"code": single.code or "invalid", "message": str(message)}
                )
    return fields


def _summary(fields: dict[str, list[dict[str, str]]]) -> str:
    """Use the single general message as summary, otherwise a generic sentence."""
    general = fields.get(GENERAL_ERRORS_KEY, [])
    if len(fields) == 1 and len(general) == 1:
        return general[0]["message"]
    return _("The input is invalid.")


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Turn any exception raised in an API view into the uniform error format.

    Business rules live in models and services and raise Django's
    ``ValidationError``. They are translated here, so that the API reports
    them exactly like its own input errors – with the field they belong to.
    """
    if isinstance(exc, DjangoValidationError):
        fields = _field_errors_from_django(exc)
        return error_response("validation_error", _summary(fields), status.HTTP_400_BAD_REQUEST, fields)
    if isinstance(exc, ProtectedError):
        return error_response(
            "in_use",
            _("The record is in use and cannot be deleted. Deactivate it instead."),
            status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, exceptions.ValidationError):
        fields = _field_errors_from_drf(exc.detail)
        return error_response("validation_error", _summary(fields), status.HTTP_400_BAD_REQUEST, fields)
    if isinstance(exc, Http404 | exceptions.NotFound):
        return error_response("not_found", _("The requested record does not exist."), status.HTTP_404_NOT_FOUND)
    if isinstance(exc, PermissionDenied | exceptions.PermissionDenied):
        return error_response(
            "permission_denied", _("You do not have the right to do this."), status.HTTP_403_FORBIDDEN
        )

    response = drf_exception_handler(exc, context)
    if response is None:
        return None  # an unexpected error: Django logs it and answers with 500
    if isinstance(exc, exceptions.NotAuthenticated | exceptions.AuthenticationFailed):
        code = "not_authenticated"
    elif isinstance(exc, exceptions.MethodNotAllowed):
        code = "method_not_allowed"
    elif isinstance(exc, exceptions.Throttled):
        code = "throttled"
    elif isinstance(exc, exceptions.ParseError | exceptions.UnsupportedMediaType):
        code = "malformed_request"
    else:
        code = getattr(exc, "default_code", "error")
    message = str(getattr(exc, "detail", "")) or _("The request could not be processed.")
    answer = error_response(code, message, response.status_code)
    for header, value in response.items():
        if header.lower() in {"www-authenticate", "retry-after"}:
            answer[header] = value
    return answer
