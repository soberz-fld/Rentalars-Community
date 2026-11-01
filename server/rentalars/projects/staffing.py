# SPDX-License-Identifier: GPL-3.0-or-later
"""Personnel for a phase, function by function (PRJ-120; PRJ-080, PRJ-094).

The requirement: when personnel is assigned to phases, ask first for the job function(s), then for the places per function, and then for the people – as when creating items; a new phase can already name functions with places.

How it works
------------
* A **new phase** can name job functions with their places ("Bühnenhelfer
  × 4, Licht × 1"); saving it plans that many open places in the phase, with
  its period (:func:`add_phase_with_places`).
* **"Personal für diese Phase"** asks first for the job functions with their
  places, then for one person per place (:func:`staff_phase`). It starts with
  the open places the phase has, per function – so the places named when the
  phase was created are filled, not planned twice:

  - a person chosen fills an open place of that function in the phase first;
    places beyond the open ones are added as new crew lines;
  - a place left empty stays – or becomes – an open place;
  - open places of the phase that the rows do not speak for stay as they are.

  Every line has the period of the phase, as before; the rules of the crew
  lines hold as everywhere (``crew.add_crew_lines``, ``crew.update_crew_line``):
  the person must have the job function unless the planner may plan outside
  them (PER-006), rates are copied (PRJ-021), "planned firmly" plans the people
  chosen without request (PER-041), and each person is told once
  (``crew_changes.one_notice_per_person``, PRJ-118).

:func:`person_hints` names, for the people offered, what the warnings of the
crew (PRJ-022) would say at the period of the phase – planned elsewhere,
absent, not available –, as the crew add form tells it after planning.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Rights
from rentalars.personnel.models import JobFunction, Person
from rentalars.projects import course, crew
from rentalars.projects.models import CrewLine, Project, ProjectPhase

#: How many rows "Funktion + Plätze" a form takes.
MAX_ROWS = 10

#: How many places one row may have – as many as one step of the crew add form plans (``crew.MAX_LINES_PER_STEP``).
MAX_PLACES = crew.MAX_LINES_PER_STEP


@dataclass
class FunctionPlaces:
    """One row: a job function, its places and – for the dialog – the person of each place (``None``: open)."""

    job_function: JobFunction
    places: int
    people: list[Person | None] = field(default_factory=list)


def open_places_of(phase: ProjectPhase) -> OrderedDict[int, list[CrewLine]]:
    """The open places of a phase by job function, in their order (one query)."""
    found: OrderedDict[int, list[CrewLine]] = OrderedDict()
    for line in (
        phase.crew_lines.filter(person__isnull=True)
        .select_related("job_function", "project", "phase", "service_product")
        .order_by("start", "position", "pk")
    ):
        found.setdefault(line.job_function_id, []).append(line)
    return found


def open_rows(phase: ProjectPhase) -> list[FunctionPlaces]:
    """The rows "Personal für diese Phase" starts with: one per job function with open places in the phase."""
    return [FunctionPlaces(lines[0].job_function, len(lines)) for lines in open_places_of(phase).values()]


def check_rows(rows: list[FunctionPlaces]) -> None:
    """The rows must make sense: places between 1 and :data:`MAX_PLACES`, no more people than places, nobody twice.

    Raises:
        ValidationError: With the job function and what is wrong.
    """
    if len(rows) > MAX_ROWS:
        raise ValidationError(_("At most %(count)d job functions at once.") % {"count": MAX_ROWS})
    for row in rows:
        if row.places < 1 or row.places > MAX_PLACES:
            raise ValidationError(
                _("%(function)s: between 1 and %(maximum)d places.")
                % {"function": row.job_function.name, "maximum": MAX_PLACES}
            )
        chosen = [person for person in row.people if person is not None]
        if len(row.people) > row.places:
            raise ValidationError(_("%(function)s: more people than places.") % {"function": row.job_function.name})
        seen: set[int] = set()
        for person in chosen:
            if person.pk in seen:
                raise ValidationError(
                    _("%(person)s is chosen twice for %(function)s.")
                    % {"person": person.name, "function": row.job_function.name}
                )
            seen.add(person.pk)


@transaction.atomic
def staff_phase(
    phase: ProjectPhase, rows: list[FunctionPlaces], *, rights: Rights, firm: bool = False
) -> list[CrewLine]:
    """Plan the places of a phase function by function – see the module description (PRJ-120).

    Args:
        phase: The phase; its project is the one planned.
        rows: Job function, places and the person of each place.
        rights: The rights of the planner (prices and costs are not touched; PER-006 is).
        firm: Plan the people chosen firmly, without request (PER-041); open places stay open.

    Returns:
        The crew lines planned or filled, in the order of the rows.

    Raises:
        ValidationError: :func:`check_rows`, or a rule of the crew lines (a closed project, a person without the job
            function, a deactivated function …) – then nothing is planned.
    """
    from rentalars.projects.crew_changes import one_notice_per_person

    check_rows(rows)
    if firm and not any(person is not None for row in rows for person in row.people):
        raise ValidationError({"firm": _("Plan a person first; an open place cannot be planned firmly.")})
    project: Project = phase.project
    pools = open_places_of(phase)
    planned: list[CrewLine] = []
    with one_notice_per_person():
        for row in rows:
            pool = pools.get(row.job_function.pk, [])
            covered = pool[: row.places]  # the open places this row speaks for
            del pool[: row.places]
            people = [person for person in row.people if person is not None]
            for person in people:
                if covered:
                    line = covered.pop(0)
                    changes: dict[str, Any] = {"person": person}
                    if firm:
                        changes["firm"] = True
                    planned.append(crew.update_crew_line(line, rights=rights, **changes))
                else:
                    planned += crew.add_crew_lines(
                        project, rights=rights, job_function=row.job_function, person=person, phase=phase, firm=firm
                    )
            missing = row.places - len(people) - len(covered)
            if missing > 0:
                planned += crew.add_crew_lines(
                    project, rights=rights, job_function=row.job_function, count=missing, phase=phase
                )
    return planned


@transaction.atomic
def add_phase_with_places(
    project: Project, rows: list[FunctionPlaces], *, rights: Rights, **fields: Any
) -> tuple[ProjectPhase, list[CrewLine]]:
    """Add a phase and plan the open places its rows name, with its period (PRJ-120; PRJ-006).

    Raises:
        ValidationError: The phase or a row is refused; then neither is saved.
    """
    phase = course.add_phase(project, **fields)
    lines = staff_phase(phase, rows, rights=rights) if rows else []
    return phase, lines


def person_hints(phase: ProjectPhase, job_function: JobFunction, people: list[Person]) -> dict[int, str]:
    """What the crew warnings (PRJ-022) would say of each person at the period of the phase – empty: nothing.

    The warnings of a probe line per person that is never saved; the queries
    do not grow with the number of people (``crew.crew_warnings``).
    """
    probes = []
    for person in people:
        probe = CrewLine(
            project=phase.project,
            job_function=job_function,
            person=person,
            start=phase.start,
            end=phase.end,
            phase=phase,
        )
        probe.pk = -person.pk  # a key of its own that no saved line has
        probes.append(probe)
    warnings = crew.crew_warnings(probes)
    return {person.pk: " ".join(warnings.get(-person.pk, [])) for person in people}
