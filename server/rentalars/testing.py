# SPDX-License-Identifier: GPL-3.0-or-later
"""The test runner of Rentalars.

It runs the tests like Django's own runner and adds one check at the end:
**every operation of the API must have been called by at least one test**
(API-014: "for every business function there is an automated test through
the API").

How it works: while the tests run, every request that an API view answers
*successfully* is noted as a pair of address name and HTTP method, for example
``("project-list", "POST")``. After the last test the notes are compared with
all operations the API offers. Operations no test reached are listed and make
the run fail.

A refused call does not count. A test that only proves that something is
forbidden has not tested the function itself – and with rights that depend on
the project (AUT-016) there are many such tests.

The check only runs when the whole suite (or all of ``tests.api``) was
executed in one process; with ``--parallel`` or a single test label it is
skipped, because the notes would be incomplete.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.test import runner as django_runner
from django.test.runner import DiscoverRunner, ParallelTestSuite
from django.urls import URLPattern, URLResolver
from rest_framework.views import APIView

#: Addresses that describe the API itself and carry no business function.
DOCUMENTATION_ROUTES = frozenset({"schema", "docs"})

HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def api_operations() -> set[tuple[str, str]]:
    """Return all operations of the API as ``(address name, METHOD)``."""
    from rentalars.api import urls as api_urls

    operations: set[tuple[str, str]] = set()

    def collect(patterns: list[Any]) -> None:
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                collect(pattern.url_patterns)
                continue
            if not isinstance(pattern, URLPattern) or not pattern.name or pattern.name in DOCUMENTATION_ROUTES:
                continue
            callback = pattern.callback
            actions = getattr(callback, "actions", None)
            if actions:  # a viewset: {"get": "list", "post": "create"}
                # The router offers every action; a viewset may refuse some (``http_method_names``).
                allowed = getattr(getattr(callback, "cls", None), "http_method_names", HTTP_METHODS)
                methods = [method for method in actions if method in HTTP_METHODS and method in allowed]
            else:  # a plain view: the methods it implements
                view_class = getattr(callback, "view_class", None) or getattr(callback, "cls", None)
                methods = [method for method in HTTP_METHODS if view_class is not None and hasattr(view_class, method)]
            operations.update((pattern.name, method.upper()) for method in methods)

    collect(api_urls.urlpatterns)
    return operations


def _init_worker_with_own_data(counter: Any, *args: Any, **kwargs: Any) -> None:
    """Start a worker of ``--parallel`` with a data folder of its own.

    The data folder holds the locks that keep two fetches of mail or two
    questions to the map search apart (``mail-fetch.lock``,
    ``geocoder.lock``). Workers sharing one folder took each other's lock:
    a test's fetch then found "a fetch is running already" and fetched
    nothing – now and then, depending on which tests ran at the same time.
    """
    from django.conf import settings

    django_runner._init_worker(counter, *args, **kwargs)
    settings.DATA_DIR = Path(settings.DATA_DIR) / f"test-worker-{django_runner._worker_id}"
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)


class _ParallelTestSuite(ParallelTestSuite):
    """Django's parallel suite, each worker with its own data folder."""

    init_worker = _init_worker_with_own_data


class RentalarsTestRunner(DiscoverRunner):
    """Django's test runner plus the check that every API operation is tested."""

    parallel_test_suite = _ParallelTestSuite

    called: set[tuple[str, str]]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.called = set()
        self._labels: tuple[str, ...] = ()
        self._original_finalize: Any = None

    def run_tests(self, test_labels: Any, **kwargs: Any) -> int:
        """Remember which tests were asked for, then run them."""
        self._labels = tuple(test_labels or ())
        return super().run_tests(test_labels, **kwargs)

    def setup_test_environment(self, **kwargs: Any) -> None:
        """Start noting the API operations the tests reach successfully."""
        super().setup_test_environment(**kwargs)
        called = self.called
        original = APIView.finalize_response
        self._original_finalize = original

        def finalize_response(view: APIView, request: Any, response: Any, *args: Any, **view_kwargs: Any) -> Any:
            match = getattr(request, "resolver_match", None)
            if match is not None and match.url_name and 200 <= response.status_code < 400:
                called.add((match.url_name, str(request.method).upper()))
            return original(view, request, response, *args, **view_kwargs)

        APIView.finalize_response = finalize_response  # type: ignore[method-assign]

    def teardown_test_environment(self, **kwargs: Any) -> None:
        """Stop noting."""
        if self._original_finalize is not None:
            APIView.finalize_response = self._original_finalize  # type: ignore[method-assign]
        super().teardown_test_environment(**kwargs)

    def _covers_whole_api(self) -> bool:
        """Whether this run executed all API tests in a single process."""
        if (
            self.parallel > 1
            or self.tags
            or self.exclude_tags
            or getattr(self, "pattern", None) not in (None, "test*.py")
        ):
            return False
        return not self._labels or any(label in {"tests", "tests.api"} for label in self._labels)

    def suite_result(self, suite: Any, result: Any, **kwargs: Any) -> int:
        """Fail the run if an API operation was never called (API-014)."""
        failures = super().suite_result(suite, result, **kwargs)
        if failures or not self._covers_whole_api():
            return failures
        untested = sorted(api_operations() - self.called)
        if untested:
            self.log("\nAPI operations that no test reached successfully (API-014):")
            for name, method in untested:
                self.log(f"  {method:6} {name}")
            return len(untested)
        self.log(f"All {len(api_operations())} API operations are reached successfully by a test (API-014).")
        return failures
