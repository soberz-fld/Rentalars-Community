# SPDX-License-Identifier: GPL-3.0-or-later
"""The switch that keeps the import of old projects quiet (legacy import; PRJ-130).

A project that is created already closed would, like any new project, tell the automations that it "reached a status"
and the webhooks that a project and a document were created – and an automation may send a mail or make a task at
exactly that. An old project taken over from a paper invoice is history, not news: while :func:`quiet` is active, those
two listeners stay silent (``automations.signals``, ``api.webhooks``).

Kept in a module of its own with no imports, so that the listeners can ask without loading the import itself.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_QUIET: ContextVar[bool] = ContextVar("rentalars_legacy_import_quiet", default=False)


def is_quiet() -> bool:
    """Whether an import of old projects is running in this thread: automations and webhooks hear nothing."""
    return _QUIET.get()


@contextmanager
def quiet() -> Iterator[None]:
    """Keep automations and webhooks silent for what is created inside the ``with`` block."""
    token = _QUIET.set(True)
    try:
        yield
    finally:
        _QUIET.reset(token)
