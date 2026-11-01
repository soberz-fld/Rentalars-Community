# SPDX-License-Identifier: GPL-3.0-or-later
"""Uniform paging for all list endpoints (API-007)."""

from __future__ import annotations

from rest_framework.pagination import PageNumberPagination

from rentalars.core.listing import LeanPaginator


class StandardPagination(PageNumberPagination):
    """Lists are delivered page by page.

    ``?page=2`` selects the page, ``?page_size=100`` its size (default 50, at
    most 500). The answer carries ``count``, ``next``, ``previous`` and the
    rows under ``results``.
    """

    #: The same two-step paging as the browser lists use (NFA-012).
    django_paginator_class = LeanPaginator
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500
