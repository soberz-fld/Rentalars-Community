# SPDX-License-Identifier: GPL-3.0-or-later
"""The project tag in the subject of a mail: ``[RL#2026-0042]`` (EML-009, EML-010, EML-011).

The tag consists of square brackets, a prefix (default ``RL``, set in the
system settings), a hash sign and the project number. It is found anywhere
in the subject, whatever the case, with spaces inside the brackets and
behind "AW:", "Re:" or "WG:"::

    >>> find_numbers("AW: Bühnenplan [rl# 2026-0042]", prefix="RL")
    ['2026-0042']

ADM-012, ADM-014: mails sent earlier carry the project number of
that time, ``[RL#P-2026-0042]``. A reply to such a mail still lands in its
project: :func:`find_numbers` gives a former number as the number of today
(``rentalars.projects.numbers``).
"""

from __future__ import annotations

import re
from functools import lru_cache

DEFAULT_PREFIX = "RL"


def current_prefix() -> str:
    """The prefix set in the system settings (EML-009)."""
    from rentalars.core.models import SystemSettings

    return SystemSettings.load().mail_tag_prefix or DEFAULT_PREFIX


@lru_cache(maxsize=16)
def _pattern(prefix: str) -> re.Pattern[str]:
    return re.compile(rf"\[\s*{re.escape(prefix)}\s*#\s*([^\]\s][^\]]*?)\s*\]", re.IGNORECASE)


def _written(subject: str, prefix: str) -> list[str]:
    """The numbers in the tags of a subject as they are written, without spaces."""
    return [re.sub(r"\s+", "", match) for match in _pattern(prefix).findall(subject or "")]


def find_numbers(subject: str, *, prefix: str | None = None) -> list[str]:
    """All project numbers named by tags in a subject, in their order.

    ADM-012, ADM-014: a project's former number is given as its number of
    today (``P-2026-0042`` → ``2026-0042``); a number of today or an unknown
    number as it is written. One query for all tags of the subject, none if
    no tag can name a former number (``PRJ-…``).
    """
    from rentalars.projects.numbers import numbers_of_today

    return numbers_of_today(_written(subject, prefix or current_prefix()))


def tag_for(number: str, *, prefix: str | None = None) -> str:
    """The tag of a project number: ``[RL#2026-0042]``."""
    return f"[{prefix or current_prefix()}#{number}]"


def subject_with_tag(subject: str, number: str, *, prefix: str | None = None) -> str:
    """The subject with the project's tag at the end – unless it carries the tag already (EML-011).

    ADM-012, ADM-014: a tag with the project's former number – in the answer
    to an older mail – is replaced by the tag of today.
    """
    prefix = prefix or current_prefix()
    written = _written(subject, prefix)
    if any(found.lower() == number.lower() for found in written):
        return subject
    tag = tag_for(number, prefix=prefix)
    from rentalars.projects.numbers import numbers_of_today

    of_today = numbers_of_today(written)
    old = {found for found, today in zip(written, of_today, strict=True) if found != today and today == number}
    if old:
        replaced = _pattern(prefix).sub(
            lambda match: tag if re.sub(r"\s+", "", match.group(1)) in old else match.group(0), subject
        )
        return replaced.strip()
    return f"{subject.strip()} {tag}".strip()
