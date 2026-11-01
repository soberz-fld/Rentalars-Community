# SPDX-License-Identifier: GPL-3.0-or-later
"""Errors of the application: counted, kept and reported to the operators (NFA-018).

Every error that is logged with level ERROR – above all an unexpected error
in a request, which the user sees as "something went wrong" – goes three
ways:

1. into the service log, as always (``journalctl -u rentalars``);
2. into :class:`~rentalars.core.models.ErrorRecord`: one row per kind of
   error, with how often and when it occurred, shown in the self-check;
3. to the operators – everybody who may change the administration – as a
   notification in the application and by e-mail (UIX-005). The same error
   is reported again at most once a day, with its count.

The handler never raises: an error while recording an error must not hide
the original one. While it records, it ignores what it logs itself.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import threading
import traceback
from datetime import timedelta

from django.conf import settings
from django.http import HttpRequest, HttpResponse

#: The same error is reported to the operators again after this time at the earliest.
REPORT_AGAIN_AFTER = timedelta(hours=24)

_busy = threading.local()


def _signature(record: logging.LogRecord) -> tuple[str, str, str]:
    """What identifies a kind of error: logger, exception type and place; plus a readable source and message."""
    message = record.getMessage().splitlines()[0][:500] if record.getMessage() else ""
    place = record.name
    if record.exc_info and record.exc_info[1] is not None:
        error = record.exc_info[1]
        frames = traceback.extract_tb(record.exc_info[2]) if record.exc_info[2] else []
        last = frames[-1] if frames else None
        place = f"{last.filename.rsplit('/', 2)[-1]}:{last.lineno}" if last else record.name
        message = f"{type(error).__name__}: {error}"[:500]
        key = f"{record.name}|{type(error).__name__}|{place}"
    else:
        key = f"{record.name}|{record.levelname}|{message[:200]}"
    return hashlib.sha256(key.encode("utf-8", "replace")).hexdigest(), place, message


class OperatorHandler(logging.Handler):
    """A logging handler that counts errors and reports them to the operators (NFA-018)."""

    def emit(self, record: logging.LogRecord) -> None:
        """Record the error; never raise."""
        if getattr(_busy, "active", False):
            return
        _busy.active = True
        try:
            # Recording an error must never cause another one.
            with contextlib.suppress(Exception):
                self._record(record)
        finally:
            _busy.active = False

    def _record(self, record: logging.LogRecord) -> None:
        from django.apps import apps
        from django.db.models import F
        from django.utils import timezone

        if not apps.ready:
            return
        from rentalars.core.models import ErrorRecord

        signature, place, message = _signature(record)
        details = ""
        if record.exc_info:
            details = "".join(traceback.format_exception(*record.exc_info))[-8000:]
        request = getattr(record, "request", None)
        if request is not None:
            details = f"{getattr(request, 'method', '')} {getattr(request, 'path', '')}\n{details}"
        now = timezone.now()
        error, created = ErrorRecord.objects.get_or_create(
            signature=signature,
            defaults={
                "source": place[:200],
                "message": message,
                "details": details,
                "first_seen": now,
                "last_seen": now,
            },
        )
        if not created:
            ErrorRecord.objects.filter(pk=error.pk).update(
                count=F("count") + 1, last_seen=now, details=details or error.details
            )
            error.refresh_from_db()
        if error.reported_at is None or now - error.reported_at > REPORT_AGAIN_AFTER:
            ErrorRecord.objects.filter(pk=error.pk).update(reported_at=now)
            from rentalars.notifications.services import notify_operators_of_error

            notify_operators_of_error(error)


def bad_request(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    """The page for a request Django refuses as 400 (``handler400``); a clear one for an unknown host name (ADM-016).

    Whoever opens Rentalars under an address it does not answer to – typically after the IP address of the server
    changed – used to see only "Bad Request". Now the page says which address arrived and what to do. It is made
    without the usual page frame, session, rights and context processors (one of them could ask for the host again): nothing here may ask for the host (that is what failed), and
    nobody is known yet. The address is shown escaped; the configured address is no secret – it is in every mail.
    """
    from django.core.exceptions import DisallowedHost
    from django.template.loader import render_to_string
    from django.utils import translation

    language = translation.get_language_from_request(request, check_path=False)
    with translation.override(language):
        if isinstance(exception, DisallowedHost):
            context = {
                "host": (request.META.get("HTTP_HOST") or "")[:200] or "–",
                "known_url": settings.RENTALARS_URL,
                "own_addresses_on": getattr(settings, "RENTALARS_ALLOW_OWN_ADDRESSES", True),
            }
            return HttpResponse(render_to_string("400_host.html", context), status=400)
        return HttpResponse(render_to_string("400.html"), status=400)
