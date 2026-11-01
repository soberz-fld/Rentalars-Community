# SPDX-License-Identifier: GPL-3.0-or-later
"""Request middleware: security header, current actor, setup and login gates."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import HttpRequest, HttpResponse, HttpResponsePermanentRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.encoding import escape_uri_path

from rentalars.core import audit

#: Paths that work without login: the login itself, password reset, the
#: first-run setup and static files. The API is listed because it performs
#: its own authentication (session or token) and answers with JSON errors
#: instead of a redirect to the login page.
PUBLIC_PATH_PREFIXES = (
    "/login/",
    "/logout/",
    "/password-reset/",
    "/setup/",
    "/static/",
    "/api/",
    "/about/",  # UIX-062: the legal notices of the licence
    "/favicon.ico",
    # PER-023: calendar programs subscribe to the deployments with a secret token instead of a login.
    "/calendar-feed/",
)

#: Paths that stay reachable while the first-run setup is not finished.
SETUP_EXEMPT_PREFIXES = ("/setup/", "/static/", "/favicon.ico")


class RequestCacheMiddleware:
    """Read settings rows once per request instead of once per question (NFA-012).

    System settings, mailbox settings and company profile are asked for by
    several middlewares, the page and its templates. They are kept for the
    duration of one request; the next request reads them fresh, so a change
    is seen at once by every worker process.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Keep singleton rows while this request is answered."""
        from rentalars.core.models import end_request_cache, start_request_cache

        token = start_request_cache()
        try:
            return self.get_response(request)
        finally:
            end_request_cache(token)


class ContentSecurityPolicyMiddleware:
    """Send a Content-Security-Policy header with every page (NFA-006).

    The policy allows scripts, styles, fonts and images only from this
    server. Should an attacker manage to smuggle markup into a page, the
    browser will still refuse to run foreign or inline scripts. It also
    guarantees that no page loads anything from third parties (NFA-050).

    The interactive API documentation needs inline scripts to start; it gets
    a slightly wider policy for its own paths only. A page that can show a
    map (UIX-034) allows images from the tile server of the configuration
    file as well (``request.csp_image_sources``, set by ``{% map_box %}``);
    the browser asks it only after the click on "Karte anzeigen".
    """

    DEFAULT_POLICY = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    DOCS_POLICY = DEFAULT_POLICY.replace("script-src 'self'", "script-src 'self' 'unsafe-inline'").replace(
        "img-src 'self' data:", "img-src 'self' data: blob:"
    )

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Add the header unless a view already set its own."""
        response = self.get_response(request)
        if "Content-Security-Policy" not in response:
            is_docs = request.path.startswith("/api/v1/docs")
            policy = self.DOCS_POLICY if is_docs else self.DEFAULT_POLICY
            # UIX-034: a page that can show a map may load its pictures from the tile server – no other page.
            extra = sorted(getattr(request, "csp_image_sources", ()))
            if extra:
                policy = policy.replace("img-src 'self' data:", "img-src 'self' data: " + " ".join(extra), 1)
            response["Content-Security-Policy"] = policy
        # UIX-006: the camera, for scanning labels, only for the pages of this server and no one embedded in them.
        # Review: nothing else of the device is needed – no microphone, position or payment request.
        response.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=(), payment=()")
        return response


class CurrentActorMiddleware:
    """Tell the audit log who is acting during this request (ADM-005)."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Remember the logged-in user for the duration of the request."""
        with audit.acting_as(request.user if request.user.is_authenticated else None):
            return self.get_response(request)


class SetupRequiredMiddleware:
    """Send every visitor to the first-run setup until it is completed (NFA-033).

    Whether the setup is done is read from the database. Once it is, the
    answer can never change back, so it is remembered in memory and costs no
    further queries.
    """

    _completed = False

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    @classmethod
    def reset(cls) -> None:
        """Forget the remembered answer; used by tests."""
        cls._completed = False

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Redirect to the setup if it is still pending."""
        if not type(self)._completed:
            from rentalars.core.models import SystemSettings

            if SystemSettings.load().setup_completed:
                type(self)._completed = True
            elif not request.path.startswith(SETUP_EXEMPT_PREFIXES):
                if request.path.startswith("/api/"):
                    return HttpResponse(
                        '{"error": {"code": "setup_required", "message": "The first-run setup is not completed."}}',
                        status=503,
                        content_type="application/json",
                    )
                return redirect(reverse("core:setup"))
        return self.get_response(request)


class LoginRequiredMiddleware:
    """Make the whole application require a login (AUT-001).

    Protecting everything by default is safer than marking each view: a new
    view that someone forgets to protect is still protected.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> Any:
        """Redirect anonymous visitors to the login page."""
        if request.user.is_authenticated or request.path.startswith(PUBLIC_PATH_PREFIXES):
            return self.get_response(request)
        return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)


class FormerNumberRedirectMiddleware:
    """ADM-012, ADM-014: an address with a former project number leads to the address of today.

    An address like ``/projects/P-2026-0042/prices/`` becomes ``/projects/2026-0042/prices/`` with a permanent redirect,
    so that browsers and bookmarks learn the new address. The project converter accepts the former number and notes it
    (:func:`rentalars.core.converters.former_numbers_in_address`); requests
    that send something (POST and alike) are answered at the old address,
    as a redirect would turn them into a GET.

    Placed before the trail of pages ("Back"), which then only ever sees the
    address of today.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Pass the request on; the work is done in :meth:`process_view`."""
        return self.get_response(request)

    def process_view(
        self, request: HttpRequest, view: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> HttpResponse | None:
        """Redirect a page request whose address used a former project number."""
        if request.method not in ("GET", "HEAD"):
            return None
        from rentalars.core.converters import former_numbers_in_address

        former = former_numbers_in_address()
        if not former:
            return None
        segments = request.path.split("/")
        path = "/".join(former.get(segment, segment) for segment in segments)
        if path == request.path:
            return None
        query = request.META.get("QUERY_STRING", "")
        return HttpResponsePermanentRedirect(escape_uri_path(path) + (f"?{query}" if query else ""))
