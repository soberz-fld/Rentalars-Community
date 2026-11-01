# SPDX-License-Identifier: GPL-3.0-or-later
r"""Check patterns of custom fields without catastrophic backtracking (MAT-071, ReDoS).

A check pattern is a regular expression an administrator types; every value
of the field must match it – in the forms, the API, the import (a task in
the background) and when a changed definition is checked against all stored
values. Python's ``re`` backtracks: ``(a+)+`` against 30 letters takes
minutes. The third-party ``regex`` module, which has a time limit, is not
used (no new libraries). Instead three layers:

1. :func:`pattern_problems` refuses, when a pattern is saved, what can
   backtrack catastrophically: nested repetitions whose count can vary
   (``(a+)+``, ``(.*,){5}``, ``(a?){30}``), alternatives inside an open-ended
   repetition (``(ab|a)+``), back-references (``\1``) and patterns longer than
   :data:`MAX_PATTERN_LENGTH`. A repetition with a fixed count inside is
   fine – ``(:[0-9A-F]{2}){5}`` has nothing to try twice –, and so is a small
   bounded nesting such as ``([0-9]{1,3}\.){3}`` (at most
   :data:`MAX_NESTED_WAYS` ways to split a value).
2. :func:`full_match` checks values of at most :data:`MAX_VALUE_LENGTH`
   characters only (the longest a long text may be).
3. :func:`full_match` stops a match after :data:`TIME_LIMIT` seconds with
   ``SIGALRM`` – where it can: in the main thread, where gunicorn's sync
   workers answer requests and ``run_jobs`` runs its tasks
   (``deploy/systemd``). In any other thread it matches without the guard.

A pattern stored before this check keeps working until its field is edited;
layers 2 and 3 apply to it all the same.
"""

from __future__ import annotations

import contextlib
import re
import signal
import threading
import time
from collections.abc import Iterator
from typing import Any

from django.utils.translation import gettext_lazy as _

try:  # Python 3.11 and later
    from re import _constants as sre_constants  # type: ignore[attr-defined]
    from re import _parser as sre_parse  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - older Python
    import sre_constants  # type: ignore[no-redef]
    import sre_parse  # type: ignore[no-redef]

#: The most characters of a check pattern.
MAX_PATTERN_LENGTH = 200
#: Values longer than this are never matched (the longest long text, ``models.LONG_TEXT_LENGTH``).
MAX_VALUE_LENGTH = 4000
#: Seconds one value may take to be matched where the time can be limited (the main thread).
TIME_LIMIT = 0.5
#: The most ways a bounded nested repetition may split a value, e.g. ``(a?){16}`` has 65,536.
MAX_NESTED_WAYS = 100_000

_REPEATS = {sre_constants.MAX_REPEAT, sre_constants.MIN_REPEAT}
if hasattr(sre_constants, "POSSESSIVE_REPEAT"):
    _REPEATS.add(sre_constants.POSSESSIVE_REPEAT)
_BACKREFERENCES = {sre_constants.GROUPREF, sre_constants.GROUPREF_EXISTS}
_UNBOUNDED = sre_constants.MAXREPEAT
#: Larger counts of ways are all "too many"; keeps the numbers small.
_CAP = MAX_NESTED_WAYS * 10

NESTED = _(
    "Nested repetitions such as (a+)+ or (.*,){5} are not allowed – checking a value could take minutes. Write the "
    "repetition out, e.g. [a-z]+ instead of ([a-z]+)+, or use a fixed count inside, e.g. (:[0-9A-F]{2}){5}."
)
ALTERNATION = _(
    "Alternatives inside an open-ended repetition such as (ab|cd)+ are not allowed – checking a value could take "
    "minutes. Give an upper limit, e.g. (ab|cd){1,5}, or use a character class such as [abcd]+."
)
BACKREFERENCE = _("Back-references such as \\1 or (?P=name) are not allowed in a check pattern.")


class PatternTooSlowError(Exception):
    """Matching a value took longer than :data:`TIME_LIMIT` seconds."""


def _children(op: Any, av: Any) -> list[Any]:
    """The sub-patterns below one node of the parsed pattern."""
    if op in _REPEATS:
        return [av[2]]
    if op == sre_constants.SUBPATTERN:
        return [av[3]]
    if op == sre_constants.BRANCH:
        return list(av[1])
    if op in (sre_constants.ASSERT, sre_constants.ASSERT_NOT):
        return [av[1]]
    if op == getattr(sre_constants, "ATOMIC_GROUP", None):
        return [av]
    return []


def _nodes(parsed: Any) -> Iterator[tuple[Any, Any]]:
    """Every node of a parsed (sub-)pattern, depth first."""
    for op, av in parsed:
        yield op, av
        for child in _children(op, av):
            yield from _nodes(child)


def _ways(parsed: Any) -> int:
    """How many ways – at most – the repetitions and alternatives of a sub-pattern can split one value."""
    total = 1
    for op, av in parsed:
        if op in _REPEATS:
            low, high, body = av
            if high == _UNBOUNDED:
                return _CAP
            inner = _ways(body)
            ways = (high - low + 1) * (inner**high if inner > 1 else 1)
        elif op == sre_constants.BRANCH:
            ways = sum(_ways(branch) for branch in av[1])
        else:
            ways = 1
            for child in _children(op, av):
                ways *= _ways(child)
        total = min(_CAP, total * max(ways, 1))
    return total


def _varies(low: int, high: int) -> bool:
    """Whether a repetition can match different counts (``a+``, ``a?``, ``a{1,3}``), not a fixed one (``a{2}``)."""
    return high != low


def pattern_problems(pattern: str) -> list[Any]:
    """Why a check pattern is refused – empty if it is fine (MAT-071).

    The pattern is read with Python's own parser of regular expressions,
    which also reports a pattern that is no valid expression (``re.error``).
    """
    if len(pattern) > MAX_PATTERN_LENGTH:
        return [_("A check pattern may have at most %(count)d characters.") % {"count": MAX_PATTERN_LENGTH}]
    parsed = sre_parse.parse(pattern)
    problems: list[Any] = []
    for op, av in _nodes(parsed):
        if op in _BACKREFERENCES and BACKREFERENCE not in problems:
            problems.append(BACKREFERENCE)
        if op not in _REPEATS:
            continue
        _low, high, body = av
        if high <= 1:
            continue
        inner = [(inner_av[0], inner_av[1]) for inner_op, inner_av in _nodes(body) if inner_op in _REPEATS]
        nested = any(
            _varies(inner_low, inner_high) and (high == _UNBOUNDED or inner_high == _UNBOUNDED)
            for inner_low, inner_high in inner
        )
        if not nested and high != _UNBOUNDED and _ways(body) > 1:
            # A bounded repetition of something with choices: refused when the ways to split a value multiply.
            nested = _ways([(op, av)]) > MAX_NESTED_WAYS
        if nested and NESTED not in problems:
            problems.append(NESTED)
        if high == _UNBOUNDED and ALTERNATION not in problems:
            if any(inner_op == sre_constants.BRANCH for inner_op, _inner in _nodes(body)):
                problems.append(ALTERNATION)
    return problems


@contextlib.contextmanager
def _time_limit(seconds: float) -> Iterator[None]:
    """Raise :class:`PatternTooSlowError` in the block after ``seconds`` – in the main thread only.

    ``SIGALRM`` reaches the main thread alone; elsewhere (``runserver``'s
    threads, for one) the block runs without a limit. A timer someone else set
    is put back afterwards.
    """
    if threading.current_thread() is not threading.main_thread() or not hasattr(signal, "setitimer"):
        yield
        return
    active = True

    def expired(signum: int, frame: Any) -> None:
        if active:
            raise PatternTooSlowError

    previous_handler = signal.signal(signal.SIGALRM, expired)
    previous_delay, previous_interval = signal.setitimer(signal.ITIMER_REAL, seconds)
    started = time.monotonic()
    try:
        yield
    finally:
        active = False
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_delay:
            left = previous_delay - (time.monotonic() - started)
            signal.setitimer(signal.ITIMER_REAL, max(left, 0.001), previous_interval)


def full_match(pattern: str, text: str) -> bool:
    """Whether ``text`` matches ``pattern`` as a whole; a text longer than :data:`MAX_VALUE_LENGTH` never does.

    Raises:
        PatternTooSlowError: Matching took longer than :data:`TIME_LIMIT` seconds.
    """
    if len(text) > MAX_VALUE_LENGTH:
        return False  # the caller refuses such a value as too long before
    compiled = re.compile(pattern)
    with _time_limit(TIME_LIMIT):
        return compiled.fullmatch(text) is not None
