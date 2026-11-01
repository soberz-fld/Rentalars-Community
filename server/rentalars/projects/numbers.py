# SPDX-License-Identifier: GPL-3.0-or-later
"""Project numbers of today and former ones (ADM-012, ADM-014).

The history of the numbers:

* A project number read ``2026-0042``, its parts ``2026-0042-1``;
* Put "P-" in front (ADM-012): ``P-2026-0042``, the number before was
  kept in ``Project.former_number``;
* Took "P-" away again (ADM-014): ``2026-0042`` once more, and the
  number with "P-" is the former number now.

One former number per project is enough: a project from before "P-" was put in front is
called again what documents of that time show, and the former number is
what documents and mails of the time with "P-" show. A project the migration
could not rename (its new number was taken) keeps its number and its former
number, both still valid.

The former number is printed on documents already sent and stands in the
subjects of mails, so it keeps working:

* the address ``/projects/P-2026-0042/`` leads permanently to the address of
  today (``core.converters``, ``core.middleware.FormerNumberRedirectMiddleware``);
* a reply whose subject carries ``[RL#P-2026-0042]`` lands in the project
  (``mail.tags.find_numbers``);
* the search, the project list, the API and the forms that take a project
  number find the project by it.

The number of today always wins: should a project have, as its number of
today, what is the former number of another one, it is the project meant.
The case is ignored, as MariaDB compares numbers.

Only the two migrations ever set a former number, and only of two shapes:
without letters (``2026-0042``) or "P-" and no further letters
(``P-2026-0042``). Any other text – a number of a scheme with letters
such as ``PRJ-2026-0042`` – cannot be a former number and costs no query.
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import reduce
from operator import or_
from typing import TYPE_CHECKING, Any

from django.db.models import Case, IntegerField, Q, Value, When

if TYPE_CHECKING:
    from rentalars.projects.models import Project

#: What was once put in front of the project numbers and taken away again.
OLD_PREFIX = "P-"


def may_be_former(number: str) -> bool:
    """Whether ``number`` can be the former number of a project.

    Not empty, and without letters apart from a leading "P-" (in any case):
    ``2026-0042`` and ``P-2026-0042`` can,
    ``PRJ-2026-0042`` cannot.
    """
    rest = number[len(OLD_PREFIX) :] if number[: len(OLD_PREFIX)].upper() == OLD_PREFIX else number
    return bool(rest) and not any(char.isalpha() for char in rest)


def matching(text: str) -> Q:
    """For searches: the projects whose number of today or former number contains ``text``."""
    return Q(number__icontains=text) | Q(former_number__icontains=text)


def project_by_number(number: str, queryset: Any = None) -> Project | None:
    """The project with this number – of today, else the former one; the case is ignored.

    One query: the number of today is sorted before a former number.

    Args:
        number: What was typed or found, e.g. ``2026-0042`` or ``P-2026-0042``.
        queryset: Where to look; all projects if not given.
    """
    from rentalars.projects.models import Project

    number = (number or "").strip()
    if not number:
        return None
    projects = queryset if queryset is not None else Project.objects.all()
    if not may_be_former(number):
        return projects.filter(number__iexact=number).first()
    today_first = Case(When(number__iexact=number, then=Value(0)), default=Value(1), output_field=IntegerField())
    return (
        projects.filter(Q(number__iexact=number) | Q(former_number__iexact=number)).order_by(today_first, "pk").first()
    )


def numbers_of_today(numbers: Iterable[str]) -> list[str]:
    """``numbers`` in their order, each former project number replaced by the number of today.

    A number that is a project's number of today, or no project's number at
    all, stays as it is written; the case is ignored. One query at most, and
    none if no number can be a former one.
    """
    numbers = list(numbers)
    wanted = sorted({number for number in numbers if may_be_former(number)})
    if not wanted:
        return numbers
    from rentalars.projects.models import Project

    condition = reduce(or_, (Q(number__iexact=number) | Q(former_number__iexact=number) for number in wanted))
    rows = list(Project.objects.filter(condition).order_by("pk").values_list("number", "former_number"))
    of_today = {number.lower() for number, _former in rows}
    renamed: dict[str, str] = {}
    for number, former in rows:
        if former:
            renamed.setdefault(former.lower(), number)
    return [number if number.lower() in of_today else renamed.get(number.lower(), number) for number in numbers]
