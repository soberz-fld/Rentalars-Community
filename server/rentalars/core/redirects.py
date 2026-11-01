# SPDX-License-Identifier: GPL-3.0-or-later
"""Where a form sends the user back to: only to a page of this site (security fix, S11)."""

from __future__ import annotations

from django.http import HttpRequest
from django.utils.http import url_has_allowed_host_and_scheme


def safe_next_url(request: HttpRequest, target: str | None = None) -> str:
    """The address in ``next`` of the form, when it is an address of this site, else an empty text.

    Browsers read a slash followed by a backslash and a host name like two slashes and go to another site, which a check
    for "begins with a slash, not with two" does not see. Django's own check knows these forms.
    """
    candidate = request.POST.get("next", "") if target is None else target
    if candidate.startswith("/") and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return ""
