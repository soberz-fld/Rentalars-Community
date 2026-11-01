# SPDX-License-Identifier: GPL-3.0-or-later
"""Divide a project into subprojects afterwards; turn groups into subprojects (PRJ-050).

A project planned in one piece – "Stadtfest" with the top-level groups
"Bühne Marktplatz" and "Bühne Schlosspark" – turns out to need parts of
its own: their own periods, packlists, status. "In Teilprojekte gliedern"
does it in one step:

* The project becomes the whole project. Every chosen top-level group
  becomes a subproject, numbered like every part (``2026-0042-1``,
  ``2026-0042-2``, PRJ-044), named like the group, with the periods of the
  project (rental period, event, rental days), its status, and the presets
  of a new part (contact, venue, project manager, PRJ-045).
* The lines of the group – those of its subgroups included – go to the
  part, and so do the subrentals that cover their shortages (PRJ-054).
  The subgroups become the groups of the part. The group itself dissolves
  into the part, unless something hangs on it: a discount or flat price,
  own rental days, "optional", a description, or a surcharge that refers to
  it – then it stays, as the one group of the part, and every price stays
  the same.
* Crew lines are not in groups (PRJ-038): each stays at the whole project
  or goes with one of the chosen groups, as chosen. A crew line that goes
  takes its time entries along (PRJ-048); its phase, which belongs to the
  whole project, is copied into the part. The crew lines of a period worked
  in several job functions (ZEI-025) must go together, or the split is
  refused (:func:`_keep_periods_together`).
* What is not chosen stays at the whole project – the common lines of
  PRJ-046 (central power, production office) –, and so do the vehicle
  bookings of the logistics (LOG-001; a crew line that goes to a part no
  longer names its vehicle), the documents,
  the mails, the files, the phases, the open items and the follow-up. A
  whole project shows its documents with all parts (PRJ-045, PRJ-046).

On a whole project the same step turns further top-level groups of the
whole project itself into subprojects ("Teilgruppe in Teilprojekt
umwandeln"); its existing parts stay as they are.

When it is not possible:

* for a subproject (one level, PRJ-044) and a service case (PRJ-090);
* when the project is out, back, closed or cancelled – the material has left
  or the project is over;
* for a group whose material is being packed or was issued: the progress of
  a packlist belongs to the packlist of the whole project;
* for a group that is an alternative to something outside it, or the other
  way round (PRJ-083), or whose lines a surcharge outside it refers to, or
  that holds a surcharge referring to something outside it (PRJ-058) – an
  alternative or a surcharge works within one project.

A surcharge of the whole project ("10 % on the project", "on the
personnel") stays at the whole project and from then on counts what stays
there; the page points this out before.

Every step writes the change log: the new parts as created, and an event
at the whole project and at every part that names what went where.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from rentalars.core.audit import record_event
from rentalars.core.i18n import local_pattern
from rentalars.projects.models import (
    CrewLine,
    Group,
    GroupKind,
    MaterialLine,
    Project,
    ProjectPhase,
    ProjectStatus,
    SurchargeTarget,
    SurchargeTargetType,
)

#: The statuses in which a project can be divided: planned, nothing out yet.
SPLITTABLE_STATUSES = frozenset(
    {ProjectStatus.INQUIRY, ProjectStatus.OPTION, ProjectStatus.CONFIRMED_OPEN, ProjectStatus.CONFIRMED}
)


@dataclass
class GroupOption:
    """A top-level group of the project and whether – and how – it can become a subproject."""

    group: Group
    #: Material lines that go with it, those of the subgroups and the covering subrentals included.
    lines: int = 0
    subgroups: int = 0
    #: Why it cannot become a subproject; empty if it can.
    reasons: list[str] = field(default_factory=list)
    #: Why the group stays as a group in the part instead of dissolving into it; empty: it dissolves.
    kept_because: list[str] = field(default_factory=list)

    @property
    def possible(self) -> bool:
        """Whether the group can become a subproject."""
        return not self.reasons

    @property
    def keeps_group(self) -> bool:
        """Whether the group stays as the one group of the new part."""
        return bool(self.kept_because)


@dataclass
class SplitPlan:
    """What dividing a project would do, for the page and the API (PRJ-050)."""

    project: Project
    #: Why the project cannot be divided at all; empty if it can.
    refusal: str = ""
    groups: list[GroupOption] = field(default_factory=list)
    crew_lines: list[CrewLine] = field(default_factory=list)
    #: What the user should know before: surcharges of the whole project that will count less.
    warnings: list[str] = field(default_factory=list)

    @property
    def possible(self) -> bool:
        """Whether at least one group can become a subproject."""
        return not self.refusal and any(option.possible for option in self.groups)


@dataclass
class _Scope:
    """The groups and lines of one top-level group."""

    group_ids: set[int]
    line_ids: set[int]


def _refusal(project: Project) -> str:
    if project.is_service_case:
        return _("A service case has no planning. Turn it into a project first.")
    if project.parent_id:
        return _("A subproject cannot be divided further: there is one level of subprojects.")
    if project.status not in SPLITTABLE_STATUSES:
        return _(
            "Only a project that is still being planned can be divided – not once it is out, back, closed or cancelled."
        )
    return ""


def _scopes(groups: list[Group], lines: list[MaterialLine]) -> dict[int, _Scope]:
    """For each top-level group, its subtree of groups and the lines that would go with it."""
    children: dict[int | None, list[Group]] = defaultdict(list)
    for group in groups:
        children[group.parent_id].append(group)
    top_of: dict[int, int] = {}
    scopes: dict[int, _Scope] = {}
    for top in children[None]:
        scope = _Scope(group_ids=set(), line_ids=set())
        stack = [top]
        while stack:
            current = stack.pop()
            scope.group_ids.add(current.pk)
            top_of[current.pk] = top.pk
            stack.extend(children.get(current.pk, []))
        scopes[top.pk] = scope
    by_pk = {line.pk: line for line in lines}
    for line in lines:
        # PRJ-054: a subrental that covers a shortage goes wherever its line goes.
        anchor = by_pk.get(line.covers_line_id) if line.covers_line_id else line
        if anchor is not None and anchor.group_id is not None and anchor.group_id in top_of:
            scopes[top_of[anchor.group_id]].line_ids.add(line.pk)
    return scopes


def split_plan(project: Project) -> SplitPlan:
    """What the page "In Teilprojekte gliedern" offers for a project (PRJ-050). A handful of queries."""
    from rentalars.packing.models import PackEntry

    plan = SplitPlan(project=project, refusal=_refusal(project))
    if plan.refusal:
        return plan
    groups = list(project.groups.all())
    lines = list(project.material_lines.all())
    plan.crew_lines = list(
        project.crew_lines.select_related("job_function", "person", "phase").order_by("position", "start", "pk")
    )
    scopes = _scopes(groups, lines)
    group_by_pk = {group.pk: group for group in groups}
    line_by_pk = {line.pk: line for line in lines}
    in_use = set(
        PackEntry.objects.filter(line__project=project)
        .filter(
            Q(packed_quantity__gt=0)
            | Q(issued_quantity__gt=0)
            | Q(returned_quantity__gt=0)
            | Q(allocations__isnull=False)
        )
        .values_list("line_id", flat=True)
    )
    targets = list(SurchargeTarget.objects.filter(surcharge_line__project=project))
    surcharge_groups = {target.target_group_id for target in targets if target.target_group_id}
    for line in lines:
        if line.is_percent_surcharge and any(
            target.surcharge_line_id == line.pk
            and target.target_type in (SurchargeTargetType.PROJECT, SurchargeTargetType.PERSONNEL)
            for target in targets
        ):
            plan.warnings.append(
                _(
                    "The surcharge “%(title)s” refers to the whole project. It stays there and counts only what "
                    "stays there."
                )
                % {"title": line.title}
            )
    for top in sorted(
        (group for group in groups if group.parent_id is None), key=lambda group: (group.position, group.pk)
    ):
        scope = scopes[top.pk]
        option = GroupOption(group=top, lines=len(scope.line_ids), subgroups=len(scope.group_ids) - 1)
        inside = scope.line_ids
        if inside & in_use:
            option.reasons.append(_("Material of this group is being packed or was issued."))
        if any(
            (group_by_pk[pk].alternative_to_id and group_by_pk[pk].alternative_to_id not in scope.group_ids)
            for pk in scope.group_ids
        ) or any(group.alternative_to_id in scope.group_ids and group.pk not in scope.group_ids for group in groups):
            option.reasons.append(_("It is an alternative to a group outside it, or the other way round."))
        elif any(
            line_by_pk[pk].alternative_to_id and line_by_pk[pk].alternative_to_id not in inside for pk in inside
        ) or any(line.alternative_to_id in inside and line.pk not in inside for line in lines):
            option.reasons.append(_("A line of it is an alternative to a line outside it, or the other way round."))
        if _surcharge_crosses(targets, inside, scope.group_ids):
            option.reasons.append(_("A surcharge refers across its border."))
        if top.has_price_rule:
            option.kept_because.append(_("discount or flat price"))
        if top.rental_days:
            option.kept_because.append(_("own rental days"))
        if top.kind != GroupKind.NORMAL:
            option.kept_because.append(str(top.get_kind_display()))
        if top.description.strip():
            option.kept_because.append(_("description"))
        if top.pk in surcharge_groups:
            option.kept_because.append(_("a surcharge refers to it"))
        plan.groups.append(option)
    if not plan.groups:
        plan.refusal = _("The project has no groups. Put the lines of each part into a group of its own first.")
    return plan


def _surcharge_crosses(targets: list[SurchargeTarget], inside: set[int], group_ids: set[int]) -> bool:
    """Whether a surcharge inside refers to something outside, or one outside to something inside (PRJ-058)."""
    for target in targets:
        surcharge_inside = target.surcharge_line_id in inside
        if target.target_type == SurchargeTargetType.LINE:
            target_inside = target.target_line_id in inside
        elif target.target_type == SurchargeTargetType.GROUP:
            target_inside = target.target_group_id in group_ids
        else:
            # The whole project or its personnel: inside a part that would mean something else.
            if surcharge_inside:
                return True
            continue
        if surcharge_inside != target_inside:
            return True
    return False


@dataclass
class SplitResult:
    """The new parts, in the order of the groups."""

    parts: list[Project]
    warnings: list[str]


@transaction.atomic
def split_into_subprojects(
    project: Project, group_ids: list[int], crew_moves: dict[int, int] | None = None, *, user: Any = None
) -> SplitResult:
    """Turn top-level groups of a project into subprojects (PRJ-050).

    Args:
        project: The project – without parts yet, or a whole project.
        group_ids: The top-level groups that become subprojects.
        crew_moves: Crew line → the group it goes with; lines not named stay at the whole project.
        user: Who does it (for the change log, which notes the acting user anyway).

    Returns:
        The new parts and the warnings of the plan.

    Raises:
        ValidationError: The project cannot be divided, a group cannot become
            a subproject, or a crew line goes with a group that does not.
    """
    from rentalars.packing.models import LineAssignment, PackEntry
    from rentalars.projects import services

    services.ensure_editable(project)
    # The rows of the project are locked against a second, parallel attempt.
    project = Project.objects.select_for_update().get(pk=project.pk)
    plan = split_plan(project)
    if plan.refusal:
        raise ValidationError(plan.refusal)
    options = {option.group.pk: option for option in plan.groups}
    chosen = [int(pk) for pk in dict.fromkeys(group_ids)]
    if not chosen:
        raise ValidationError(_("Choose at least one group."))
    for pk in chosen:
        option = options.get(pk)
        if option is None:
            raise ValidationError(_("Only top-level groups of this project can become subprojects."))
        if not option.possible:
            raise ValidationError(
                _("“%(name)s” cannot become a subproject: %(reasons)s")
                % {"name": option.group.name, "reasons": " ".join(option.reasons)}
            )
    crew_moves = {int(line): int(group) for line, group in (crew_moves or {}).items()}
    crew_by_pk = {line.pk: line for line in plan.crew_lines}
    for line_pk, group_pk in crew_moves.items():
        if line_pk not in crew_by_pk:
            raise ValidationError(_("The crew line %(id)s does not belong to this project.") % {"id": line_pk})
        if group_pk not in chosen:
            raise ValidationError(_("A crew line can only go with a group that becomes a subproject."))
    _keep_periods_together(project, crew_moves)

    groups = list(project.groups.all())
    lines = list(project.material_lines.all())
    scopes = _scopes(groups, lines)
    line_by_pk = {line.pk: line for line in lines}
    parts: list[Project] = []
    for pk in sorted(chosen, key=lambda key: (options[key].group.position, key)):
        option = options[pk]
        top = option.group
        scope = scopes[pk]
        part = services.create_subproject(
            project,
            name=top.name[:200],
            status=project.status,
            event_start=project.event_start,
            event_end=project.event_end,
            rental_days=project.rental_days,
        )
        moving = sorted(scope.line_ids)
        # Progress records without progress belong to the packlists of the whole project: they go.
        PackEntry.objects.filter(line_id__in=moving).delete()
        LineAssignment.objects.filter(line_id__in=moving).delete()
        if option.keeps_group:
            Group.objects.filter(pk__in=scope.group_ids).update(project=part)
            MaterialLine.objects.filter(pk__in=moving).update(project=part)
        else:
            Group.objects.filter(pk__in=scope.group_ids - {top.pk}).update(project=part)
            Group.objects.filter(pk__in=scope.group_ids, parent_id=top.pk).update(parent=None)
            MaterialLine.objects.filter(pk__in=moving).update(project=part)
            MaterialLine.objects.filter(pk__in=moving, group_id=top.pk).update(group=None)
        # A covering subrental stands with its line (PRJ-054), whatever group it stood in before.
        for line_pk in moving:
            line = line_by_pk[line_pk]
            if line.covers_line_id:
                covered = line_by_pk[line.covers_line_id]
                group_id = None if (covered.group_id == top.pk and not option.keeps_group) else covered.group_id
                MaterialLine.objects.filter(pk=line_pk).update(group_id=group_id)
        if not option.keeps_group:
            # Empty now: its lines and subgroups are in the part. The change log notes it as deleted.
            Group.objects.get(pk=top.pk).delete()
        crew_count = _move_crew(part, [crew_by_pk[line] for line, group in crew_moves.items() if group == pk])
        record_event(
            part,
            "project.split_part",
            {
                "project": project.number,
                "group": top.name,
                "lines": len(moving),
                "crew": crew_count,
            },
        )
        parts.append(part)
    # Covering subrentals of lines that stay, which stood in a group that went, stay with their line.
    for line in lines:
        if line.covers_line_id and line.pk not in {pk for scope in scopes.values() for pk in scope.line_ids}:
            covered = line_by_pk.get(line.covers_line_id)
            if covered is not None and line.group_id != covered.group_id:
                MaterialLine.objects.filter(pk=line.pk).update(group_id=covered.group_id)
    _share_overall_discount(project, parts)
    record_event(project, "project.split", {"parts": [f"{part.number} {part.name}" for part in parts]})
    return SplitResult(parts=parts, warnings=plan.warnings)


def _share_overall_discount(project: Project, parts: list[Project]) -> None:
    """PRJ-123: the parts take over the overall discount, so that no price changes by the split.

    A percentage is the same for every part. An amount is shared in
    proportion to what each project (the whole project with what stays
    there, and each part) adds up to before the discount; the cents that
    do not divide go to the whole project. Whoever splits does not need the
    right to prices: nothing is set, a price just stays where it was.
    """
    from rentalars.projects.pricing import ZERO, compute_project_prices

    percent, amount = project.overall_discount_percent, project.overall_discount_amount
    if not parts or (percent is None and amount is None):
        return
    if percent is not None:
        for part in parts:
            part.overall_discount_percent = percent
            part.save()
        return
    sums = {piece.pk: compute_project_prices(piece).net_before_overall_discount for piece in [project, *parts]}
    total = sum(sums.values(), ZERO)
    if total <= ZERO:
        return
    given = ZERO
    for part in parts:
        share = (amount * sums[part.pk] / total).quantize(
            Decimal("0.01"), rounding=ROUND_DOWN
        )  # never more than the amount
        part.overall_discount_amount = share or None
        part.save()
        given += share
    project.overall_discount_amount = (amount - given) or None
    project.save()


def _keep_periods_together(project: Project, crew_moves: dict[int, int]) -> None:
    """ZEI-025: the parts of one period of time stay in one project – the split is refused otherwise.

    A period worked in several job functions is one time entry per part,
    each counting towards its own crew line. If those crew lines went to
    different projects, one period would be torn apart: its parts approved,
    billed and checked for overlaps in different places. Moving every part
    along with one of them would leave a part pointing at a crew line in
    another project, which is worse for approved and billed times. So the
    split asks for the crew lines of a period to go together; a part
    without crew line stays with the whole project.

    Raises:
        ValidationError: Names the person, the period and the job functions.
    """
    from django.utils import timezone

    from rentalars.timetracking.models import TimeEntry

    destinations: dict[Any, set[int | None]] = defaultdict(set)
    examples: dict[Any, list[TimeEntry]] = defaultdict(list)
    for entry in (
        TimeEntry.objects.filter(project=project, period_key__isnull=False)
        .select_related("person", "job_function")
        .order_by("start", "id")
    ):
        destinations[entry.period_key].add(crew_moves.get(entry.crew_line_id) if entry.crew_line_id else None)
        examples[entry.period_key].append(entry)
    for key, places in destinations.items():
        if len(places) < 2:
            continue
        parts = examples[key]
        start, end = timezone.localtime(parts[0].start), timezone.localtime(parts[0].end)
        raise ValidationError(
            _(
                "The time of %(person)s on %(day)s from %(start)s to %(end)s is divided into %(functions)s. "
                "Its crew lines must stay together – at the whole project or with the same subproject."
            )
            % {
                "person": parts[0].person.name,
                "day": start.strftime(local_pattern("%d.%m.%Y")),
                "start": start.strftime("%H:%M"),
                "end": end.strftime("%H:%M"),
                "functions": ", ".join(part.job_function.name for part in parts),
            }
        )


def _move_crew(part: Project, crew: list[CrewLine]) -> int:
    """Crew lines go to the part with their time entries; their phases are copied into the part (PRJ-048)."""
    from rentalars.timetracking.models import TimeEntry

    if not crew:
        return 0
    copies: dict[int, ProjectPhase] = {}
    for line in crew:
        phase = line.phase
        if phase is not None and phase.pk not in copies:
            copies[phase.pk] = ProjectPhase.objects.create(
                project=part,
                kind=phase.kind,
                title=phase.title,
                start=phase.start,
                end=phase.end,
                venue_site=phase.venue_site,
                location=phase.location,
                notes=phase.notes,
            )
    for line in crew:
        # LOG-008, LOG-019: the vehicles stay with the whole project; a line that goes no longer names one.
        CrewLine.objects.filter(pk=line.pk).update(
            project=part, phase=copies[line.phase_id] if line.phase_id else None, vehicle_line=None, is_driver=False
        )
    TimeEntry.objects.filter(crew_line_id__in=[line.pk for line in crew]).update(project=part)
    return len(crew)


def result_message(result: SplitResult) -> str:
    """The message after dividing, e.g. "2 subprojects created: 2026-0042-1 Bühne Marktplatz, …"."""
    return ngettext(
        "%(count)d subproject created: %(parts)s.",
        "%(count)d subprojects created: %(parts)s.",
        len(result.parts),
    ) % {"count": len(result.parts), "parts": ", ".join(f"{part.number} {part.name}" for part in result.parts)}
