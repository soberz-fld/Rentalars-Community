# SPDX-License-Identifier: GPL-3.0-or-later
"""Protection of the API against too many calls, repeated calls and overwriting (API-010, API-011).

Rate limit (API-011)
    Each token may make ``SystemSettings.api_requests_per_minute`` calls per
    minute (600 unless changed; 0 switches the limit off). Calls beyond that
    are answered with 429 "too many requests" and a ``Retry-After`` header.
    The count is kept in the database, so that it holds across all processes
    of the application server. Calls from the browser (the API description,
    pages with a session) are not counted.

Repeated calls (API-010)
    A changing call (POST, PUT, PATCH, DELETE) may carry an
    ``Idempotency-Key`` header – any text of up to 100 characters the client
    makes up, e.g. a UUID. The first call with a key is carried out and its
    answer stored for a day; the same call with the same key again gets that
    answer once more (header ``Idempotent-Replayed: true``) and changes
    nothing. A key belongs to its caller – the token, or the
    user of a browser session – and is looked up only after the caller has
    logged in: a call that does not log in is answered as without a key.
    Before a stored answer is given again, the caller's current rights are
    checked exactly as for a new call (login, module rights, rate limit and
    – where the address names a record – access to it); a caller who lost
    them gets the refusal, not the answer. Many handlers check the access to
    their project only inside; so while the first call runs, every level of
    project access found for its caller (``projects.access.access_level``,
    which every such check goes through) and the access to the project named
    in the address are noted with the stored answer, and a repetition must
    still have at least that much in each project (404 or 403 otherwise). A key used for another call
    (method, address or body differ) is refused with 409
    ``idempotency_key_reused``; while the first call still runs, a second one
    gets 409 ``idempotency_key_in_progress``.

Overwriting (API-010)
    Every answer to a GET carries an ``ETag``: a fingerprint of what was
    delivered. A client that sends it back with ``If-Match`` when it changes
    or deletes the record gets 412 "precondition failed" if somebody else
    changed the record in between – instead of overwriting that change. With
    ``If-None-Match`` a GET answers 304 when nothing changed.

    Comparing and writing are one step: in one transaction, a
    lock row of the record (:class:`~rentalars.api.models.WriteLock`, keyed
    by model and primary key, or by the address where no record can be
    named) is taken and the record's own row is locked (``SELECT … FOR
    UPDATE``); only then is the current state compared and the change
    carried out, and the locks are held until it is committed. Of two
    changes sent with the same ``ETag`` at the same moment, the second waits
    for the first, then finds the record changed and gets 412. On SQLite the
    lock row is a write that holds the database's write lock.

    The browser has no such check: forms save what they are sent.
"""

from __future__ import annotations

import contextlib
import datetime
import hashlib
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import F
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.urls import Resolver404, resolve
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import exceptions
from rest_framework.throttling import BaseThrottle

if TYPE_CHECKING:
    from rest_framework.request import Request
    from rest_framework.views import APIView

API_PREFIX = "/api/"
CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
#: How long the answer to a call with an ``Idempotency-Key`` is kept.
IDEMPOTENCY_TTL = datetime.timedelta(days=1)


# --- Rate limit (API-011) ------------------------------------------------------------


class TokenRateThrottle(BaseThrottle):
    """At most so many calls per token and minute (``SystemSettings.api_requests_per_minute``)."""

    def __init__(self) -> None:
        self.retry_after: float | None = None

    def allow_request(self, request: Any, view: Any) -> bool:
        """Count the call; refuse it if the token used up its minute."""
        from rentalars.accounts.models import ApiToken
        from rentalars.api.models import ApiCallCount
        from rentalars.core.models import SystemSettings

        token = getattr(request, "auth", None)
        if not isinstance(token, ApiToken):
            return True
        limit = SystemSettings.load().api_requests_per_minute
        if not limit:
            return True
        now = timezone.now()
        minute = now.replace(second=0, microsecond=0)
        counted = ApiCallCount.objects.filter(token=token, minute=minute).update(count=F("count") + 1)
        if not counted:
            try:
                with transaction.atomic():
                    ApiCallCount.objects.create(token=token, minute=minute, count=1)
            except IntegrityError:
                # Another process created the row at the same moment.
                ApiCallCount.objects.filter(token=token, minute=minute).update(count=F("count") + 1)
        count = ApiCallCount.objects.filter(token=token, minute=minute).values_list("count", flat=True).first() or 0
        # The middleware below shows limit and rest in the headers of the answer.
        getattr(request, "_request", request).rate_limit = (limit, max(limit - count, 0))
        if count > limit:
            self.retry_after = 60 - now.second
            return False
        return True

    def wait(self) -> float | None:
        """Seconds until the next minute begins."""
        return self.retry_after


def delete_old_call_counts() -> int:
    """Remove counts, stored answers and lock rows that no longer matter (daily maintenance)."""
    from rentalars.api.models import ApiCallCount, IdempotentCall, WriteLock

    now = timezone.now()
    counts, _details = ApiCallCount.objects.filter(minute__lt=now - datetime.timedelta(hours=1)).delete()
    calls, _details = IdempotentCall.objects.filter(created_at__lt=now - IDEMPOTENCY_TTL).delete()
    # API-010: a lock row only matters while a change runs; an old one is taken again when needed.
    locks, _details = WriteLock.objects.filter(taken_at__lt=now - datetime.timedelta(days=1)).delete()
    return counts + calls + locks


# --- Repeated calls and overwriting (API-010) -------------------------------------------------


def _error(status: int, code: str, message: str) -> JsonResponse:
    """An answer in the uniform error format (API-008)."""
    return JsonResponse({"error": {"code": code, "message": message, "fields": {}}}, status=status)


def etag_of(content: bytes) -> str:
    """The fingerprint of an answer, as ``ETag``."""
    return '"' + hashlib.sha256(content).hexdigest()[:32] + '"'


def _scope(user: Any, token: Any) -> str:
    """Whose ``Idempotency-Key`` this is: the token of the call, or the user of the session (API-010)."""
    from rentalars.accounts.models import ApiToken

    if isinstance(token, ApiToken):
        return f"token:{token.pk}"
    return f"user:{user.pk}"


def _fingerprint(request: HttpRequest) -> str:
    """What the call is: method, address with query and a hash of the body (API-010)."""
    digest = hashlib.sha256()
    digest.update(f"{request.method} {request.get_full_path()}\n".encode())
    digest.update(hashlib.sha256(request.body).digest())
    return digest.hexdigest()


class _ViewProbe:
    """The view of the REST framework an API address leads to, set up for one call without running it (API-010).

    It answers what the view would decide before its handler runs – who
    calls, whether the caller may, which record the address names – so that
    a stored answer is given only to whom a new call would be allowed, and
    so that the record can be locked before its version is compared.
    """

    def __init__(self, view: APIView, request: Request) -> None:
        self.view = view
        self.request = request

    @classmethod
    def of(cls, request: HttpRequest) -> _ViewProbe | None:
        """The probe for a call; ``None`` if the address leads to no view of the REST framework."""
        try:
            match = resolve(request.path_info)
        except Resolver404:
            return None
        return cls.for_view(request, match.func, match.args, match.kwargs)

    @classmethod
    def for_view(
        cls, request: HttpRequest, callback: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> _ViewProbe | None:
        """The probe for a call of ``callback`` with these arguments of the address."""
        # Imported here: the settings of the REST framework import this module while its views load.
        from rest_framework.views import APIView

        view_class = getattr(callback, "cls", None)
        if not isinstance(view_class, type) or not issubclass(view_class, APIView):
            return None
        view = view_class(**getattr(callback, "initkwargs", {}))
        actions = getattr(callback, "actions", None)
        if actions:
            # As ViewSetMixin.as_view does it: the handler of each method is the action's.
            actions = dict(actions)
            if "get" in actions and "head" not in actions:
                actions["head"] = actions["get"]
            view.action_map = actions
            for method, action in actions.items():
                setattr(view, method, getattr(view, action))
        view.args, view.kwargs = args, kwargs
        drf_request = view.initialize_request(request, *args, **kwargs)
        view.request = drf_request
        view.headers = view.default_response_headers
        view.format_kwarg = view.get_format_suffix(**kwargs)
        return cls(view, drf_request)

    def caller(self) -> tuple[Any, Any] | None:
        """User and token of the call – ``None`` if it does not log in."""
        try:
            user = self.request.user
        except exceptions.APIException:
            return None
        if user is None or not user.is_authenticated:
            return None
        return user, self.request.auth

    def _names_record(self) -> bool:
        from rest_framework.generics import GenericAPIView

        view = self.view
        lookup = getattr(view, "lookup_url_kwarg", None) or getattr(view, "lookup_field", None)
        return isinstance(view, GenericAPIView) and bool(lookup) and lookup in view.kwargs

    def projects_in_address(self) -> list[int]:
        """The projects the address names: ``project_pk``, or the record of a view of projects (API-010).

        Every API address with a project in its path names it one of these
        two ways (``tests/unit/test_082_security.py`` walks them all).
        """
        from rentalars.projects.models import Project

        view, found = self.view, []
        if "project_pk" in view.kwargs:
            found.append(view.kwargs["project_pk"])
        model = getattr(getattr(view, "queryset", None), "model", None)
        lookup = getattr(view, "lookup_url_kwarg", None) or getattr(view, "lookup_field", None)
        if isinstance(model, type) and issubclass(model, Project) and lookup in view.kwargs:
            found.append(view.kwargs[lookup])
        result = []
        for value in found:
            with contextlib.suppress(TypeError, ValueError):
                result.append(int(value))
        return result

    def check_address_projects(self) -> None:
        """Ask the caller's access to the projects of the address, so that it is noted for the call (API-010)."""
        from rentalars.accounts.rights import request_rights
        from rentalars.projects.access import access_level
        from rentalars.projects.models import Project

        pks = self.projects_in_address()
        if pks:
            rights = request_rights(self.request)
            for project in Project.objects.filter(pk__in=pks):
                access_level(rights, self.request.user, project)

    def _check_project_access(self, used: dict[str, int]) -> None:
        """Raise as ``project_for`` would if the caller lost access the call relied on (API-010).

        A project that is gone does not refuse – the call may have deleted it.
        """
        from rentalars.accounts.rights import request_rights
        from rentalars.projects.access import ProjectAccess, access_level
        from rentalars.projects.models import Project

        if not used:
            return
        rights = request_rights(self.request)
        for project in Project.objects.filter(pk__in=[int(pk) for pk in used]):
            now = access_level(rights, self.request.user, project)
            if now < used[str(project.pk)]:
                raise Http404 if now == ProjectAccess.NONE else PermissionDenied

    def refusal(self, used_access: dict[str, int] | None = None) -> HttpResponse | None:
        """The answer a new call would get before its handler runs; ``None`` if it may go ahead.

        Login, rights of the module, rate limit – the checks of the REST
        framework – and, where the address names a record that still
        exists, the access to it. A record that is gone does not refuse: the
        call that is repeated may have deleted it. ``used_access`` is the
        access to projects the first call relied on (project ID → level,
        noted while it ran): the caller must still have at least that much
        in every one of them – also where the handler checks it only inside.
        """
        view = self.view
        try:
            view.initial(self.request, *view.args, **view.kwargs)
            if self._names_record():
                with contextlib.suppress(exceptions.NotFound, Http404):
                    view.get_object()
            self._check_project_access(used_access or {})
        except Exception as error:  # answered exactly as the view would answer it
            response = view.handle_exception(error)
            response = view.finalize_response(self.request, response, *view.args, **view.kwargs)
            response.render()
            return response
        return None

    def record(self) -> Any:
        """The record the address names, as far as the caller may see it; ``None`` if there is none."""
        if not self._names_record():
            return None
        view = self.view
        try:
            view.perform_authentication(self.request)
            view.check_permissions(self.request)
            return view.get_object()
        except Exception:  # then the address is locked instead; the view answers the call
            return None


def _take_lock(name: str) -> None:
    """Take the lock row of ``name`` for the running transaction; wait while another one holds it (API-010)."""
    from rentalars.api.models import WriteLock

    key = hashlib.sha256(name.encode()).hexdigest()
    now = timezone.now()
    if WriteLock.objects.filter(key=key).update(taken_at=now):
        return
    try:
        with transaction.atomic():
            WriteLock.objects.create(key=key, taken_at=now)
    except IntegrityError:
        # Created at the same moment by another change, which holds it now: wait for it.
        WriteLock.objects.filter(key=key).update(taken_at=now)


class ApiSafeguardMiddleware:
    """``Idempotency-Key``, ``ETag``, ``If-Match`` and ``If-None-Match`` for every API address."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Leave pages alone; protect calls of the API."""
        if not request.path.startswith(API_PREFIX):
            return self.get_response(request)
        response = self._answer(request)
        rate_limit = getattr(request, "rate_limit", None)
        if rate_limit is not None:
            response["X-RateLimit-Limit"], response["X-RateLimit-Remaining"] = (str(value) for value in rate_limit)
        return response

    def _answer(self, request: HttpRequest) -> HttpResponse:
        if request.method in CHANGING_METHODS:
            key = request.headers.get("Idempotency-Key", "").strip()
            if key:
                return self._once(request, key)
            return self._carry_out(request)
        response = self.get_response(request)
        if request.method == "GET":
            return self._tag(request, response)
        return response

    # ETag and If-None-Match ------------------------------------------------------------------

    @staticmethod
    def _tag(request: HttpRequest, response: HttpResponse) -> HttpResponse:
        if (
            response.status_code != 200
            or response.streaming
            or not response.get("Content-Type", "").startswith("application/json")
        ):
            return response
        tag = etag_of(response.content)
        response["ETag"] = tag
        if tag in [value.strip() for value in request.headers.get("If-None-Match", "").split(",")]:
            not_modified = HttpResponse(status=304)
            not_modified["ETag"] = tag
            return not_modified
        return response

    # If-Match ----------------------------------------------------------------------------------

    def _carry_out(self, request: HttpRequest, probe: _ViewProbe | None = None) -> HttpResponse:
        """Carry out a changing call; with ``If-Match`` compare and write in one protected step (API-010)."""
        if not request.headers.get("If-Match"):
            return self.get_response(request)
        if probe is None:
            probe = _ViewProbe.of(request)
        record = probe.record() if probe is not None else None
        with transaction.atomic():
            if record is not None:
                _take_lock(f"record:{record._meta.label_lower}:{record.pk}")
                # The row itself, so that a change by another way (the browser) waits as well.
                list(type(record)._base_manager.select_for_update().filter(pk=record.pk).values_list("pk", flat=True))
            else:
                _take_lock(f"path:{request.path}")
            refused = self._check_version(request)
            if refused is not None:
                return refused
            response = self.get_response(request)
            if response.status_code >= 500:
                transaction.set_rollback(True)
        return response

    def _check_version(self, request: HttpRequest) -> HttpResponse | None:
        """Compare ``If-Match`` with the record as it is now; 412 if it changed meanwhile."""
        current = self._current(request)
        if current is None:
            return None
        wanted = {value.strip() for value in request.headers["If-Match"].split(",")}
        if "*" in wanted or etag_of(current) in wanted:
            return None
        return _error(
            412,
            "precondition_failed",
            _("The record was changed in the meantime. Fetch it again and repeat the change on the current state."),
        )

    def _current(self, request: HttpRequest) -> bytes | None:
        """What a GET of the same address delivers now; ``None`` if there is no such GET."""
        current = HttpRequest()
        current.method = "GET"
        current.path = current.path_info = request.path
        current.META = {
            key: value
            for key, value in request.META.items()
            if key not in {"CONTENT_LENGTH", "CONTENT_TYPE", "HTTP_IF_MATCH", "HTTP_IDEMPOTENCY_KEY"}
        }
        current.META["REQUEST_METHOD"] = "GET"
        current.COOKIES = request.COOKIES
        for attribute in ("session", "user", "_messages", "_force_auth_user", "_force_auth_token"):
            if hasattr(request, attribute):
                setattr(current, attribute, getattr(request, attribute))
        response = self.get_response(current)
        if response.status_code != 200 or response.streaming:
            return None
        return response.content

    # Idempotency-Key ---------------------------------------------------------------------------

    def _once(self, request: HttpRequest, key: str) -> HttpResponse:
        """Carry out a call with a key once; answer repetitions from the store – to the same caller only."""
        from rentalars.api.models import IdempotentCall

        probe = _ViewProbe.of(request)
        caller = probe.caller() if probe is not None else None
        if caller is None:
            # Not logged in: the call is answered as without a key – by a refusal.
            return self._carry_out(request, probe)
        if len(key) > 100:
            return _error(400, "validation_error", _("An Idempotency-Key has at most 100 characters."))
        scope = _scope(*caller)
        fingerprint = _fingerprint(request)
        IdempotentCall.objects.filter(created_at__lt=timezone.now() - IDEMPOTENCY_TTL, scope=scope, key=key).delete()
        try:
            with transaction.atomic():
                stored = IdempotentCall.objects.create(scope=scope, key=key, fingerprint=fingerprint)
        except IntegrityError:
            earlier = IdempotentCall.objects.filter(scope=scope, key=key).first()
            if earlier is None:
                return self._carry_out(request, probe)
            # The same checks as for a new call come first: who lost the right gets the refusal.
            refused = probe.refusal(earlier.project_access) if probe is not None else None
            if refused is not None:
                return refused
            if earlier.status_code is None:
                return _error(409, "idempotency_key_in_progress", _("The call with this key is still running."))
            if earlier.fingerprint != fingerprint:
                return _error(
                    409,
                    "idempotency_key_reused",
                    _("This Idempotency-Key was used for another call. Use a new key for every call."),
                )
            replay = HttpResponse(bytes(earlier.body), status=earlier.status_code, content_type=earlier.content_type)
            if earlier.location:
                replay["Location"] = earlier.location
            replay["Idempotent-Replayed"] = "true"
            return replay
        from rentalars.projects.access import recording_project_access

        try:
            # Note the access to projects the call relies on, for the checks of a repetition.
            with recording_project_access(caller[0]) as used_access:
                if probe is not None:
                    probe.check_address_projects()
                response = self._carry_out(request, probe)
        except Exception:
            stored.delete()
            raise
        if response.status_code >= 500 or response.streaming:
            # A failure is not remembered: the client may try again with the same key.
            stored.delete()
            return response
        stored.status_code = response.status_code
        stored.content_type = response.get("Content-Type", "")[:100]
        stored.location = response.get("Location", "")[:500]
        stored.body = response.content
        stored.project_access = {str(pk): level for pk, level in used_access.items()}
        stored.save()
        return response
