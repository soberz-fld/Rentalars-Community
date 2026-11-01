# SPDX-License-Identifier: GPL-3.0-or-later
"""The API tests that live next to their feature are part of ``tests.api`` as well (R4-5; API-014).

Since 0.9.x many API tests sit in ``tests/unit`` (and a few in ``tests/acceptance``), beside the tests of the feature
they belong to. API-014 ("every operation of the API is reached successfully by a test") is checked by
``rentalars/testing.py`` when all of ``tests.api`` runs – and that run did not see those tests, so it listed
operations as untested that a test does reach.

This module makes them visible: it imports every test class that is an :class:`~tests.api.base.ApiTestCase` from
those folders, so ``manage.py test tests.api`` runs them too. Nothing runs twice in a full run (``manage.py test
tests``): Django's runner removes tests that appear more than once. New API tests need no entry here – any module
of ``tests/unit`` or ``tests/acceptance`` that mentions ``ApiTestCase`` is found.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

from tests.api.base import ApiTestCase

#: The packages beside ``tests/api`` in which API tests are kept.
MIRRORED_PACKAGES = ("tests.unit", "tests.acceptance")


def mirrored_cases() -> dict[str, type[ApiTestCase]]:
    """The test classes of the mirrored packages that talk to the API, by a unique name."""
    found: dict[str, type[ApiTestCase]] = {}
    for package_name in MIRRORED_PACKAGES:
        package = importlib.import_module(package_name)
        for module_info in pkgutil.iter_modules(package.__path__):
            if not module_info.name.startswith("test"):
                continue
            source = Path(package.__path__[0]) / f"{module_info.name}.py"
            if not source.is_file() or "ApiTestCase" not in source.read_text(encoding="utf-8"):
                continue  # most modules have nothing to do with the API: do not import them for nothing
            module = importlib.import_module(f"{package_name}.{module_info.name}")
            for name, value in vars(module).items():
                if isinstance(value, type) and issubclass(value, ApiTestCase) and value.__module__ == module.__name__:
                    found[f"{module_info.name}__{name}"] = value
    return found


globals().update(mirrored_cases())
