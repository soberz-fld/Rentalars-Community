# SPDX-License-Identifier: GPL-3.0-or-later
"""Several crew lines at once (PRJ-117; the material lines have it too, PRJ-082).

The requirement: multiple selection for personnel in the planning too, to set the meeting point or other values on several lines at once.

The lines ticked in the block "Personal" of the planning – or named in ``POST
/projects/{id}/crew-lines/bulk`` (API-002) – get one action (:class:`CrewBulkAction`):

``edit``
    Set the same values on every line: meeting point, note, phase, from, until, planned hours, vehicle – and,
    with the price right, the discount (:data:`EDIT_FIELDS`). What is not given stays. As in the dialog of a line,
    a phase without times brings its period, new times bring new planned hours where they were the suggestion
    (PRJ-023), and a line asked for or accepted is asked again for new times (PER-034).
``firm``
    Plan the people firmly, without request (``crew_changes``). Open places are skipped; lines accepted or planned
    firmly already stay as they are.
``ask``
    Send the deployment requests (PER-016): to lines not asked yet, and to lines whose times changed since. Open
    places and lines planned firmly are skipped; lines asked or answered for their times stay as they are.
``delete``
    Delete the lines; times counted towards them stay in the project (ZEI-021).

Every line goes through the service for a single line (``crew.update_crew_line``, ``crew.request_deployment``,
``crew.delete_crew_line``) with its rules, rights and entry in the history, each in a step of its own: a line the
service refuses is left as it is and named with the reason, the others are changed. The people concerned are told
of changes once per action, whatever the number of their lines (``crew_changes.one_notice_per_person``). A request
(``ask``, or asked again for new times, PER-034) is a message of its own per line, as when asking line by line: each
can be answered for itself (PER-016).

Who may: whoever may change the crew of the project (``access.may_plan_crew``); the discount needs the price
right, as in the dialog (AUT-019).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _
from django.utils.translation import pgettext

from rentalars.accounts.rights import Rights
from rentalars.projects import crew, crew_changes
from rentalars.projects.discounts import capped_lines_warning
from rentalars.projects.models import CrewLine, Project, RequestStatus
from rentalars.projects.services import ensure_editable


class CrewBulkAction:
    """What can be done with several crew lines at once (PRJ-117)."""

    EDIT = "edit"
    FIRM = "firm"
    ASK = "ask"
    DELETE = "delete"

    ALL = (EDIT, FIRM, ASK, DELETE)


#: What ``edit`` can set on several lines at once.
EDIT_FIELDS = ("meeting_point", "note", "phase", "start", "end", "planned_hours", "vehicle_line", "discount_percent")


def crew_line_label(line: CrewLine) -> str:
    """How a message names a line: "Tontechnik – Anna Becker", or "Stagehand – offen" for an open place."""
    return f"{line.title} – {line.person.name if line.person_id else pgettext('crew', 'open')}"


@dataclass
class SkippedCrewLine:
    """A line the action was not done with, and why."""

    line: CrewLine
    reason: str

    @property
    def label(self) -> str:
        """The line as the messages name it."""
        return crew_line_label(self.line)


@dataclass
class CrewBulkResult:
    """What :func:`change_crew_lines` did."""

    action: str
    #: The lines changed, asked or deleted (deleted ones with the values they had).
    changed: list[CrewLine] = field(default_factory=list)
    changed_ids: list[int] = field(default_factory=list)
    #: The lines that were as asked already – planned firmly, asked for these times, the same values.
    unchanged: list[CrewLine] = field(default_factory=list)
    skipped: list[SkippedCrewLine] = field(default_factory=list)
    #: ``ask``: the lines whose person nobody could tell – marked "asked", the answer is entered by hand.
    not_told: list[CrewLine] = field(default_factory=list)
    #: ``edit``: the lines asked again for their new times (PER-034).
    asked_again: list[CrewLine] = field(default_factory=list)
    #: What the user is to be told, e.g. that a discount is above the maximum of some job functions (PER-026).
    warnings: list[str] = field(default_factory=list)


def _check_values(project: Project, values: dict[str, Any], rights: Rights) -> None:
    """Refuse values that no line could take: unknown, foreign, out of range, or without the right."""
    unknown = set(values) - set(EDIT_FIELDS)
    if unknown:
        raise ValidationError(_("These fields cannot be changed: %(fields)s") % {"fields": ", ".join(sorted(unknown))})
    if not values:
        raise ValidationError(_("Choose what to set for the chosen crew lines."))
    crew._check_rights(values.keys(), rights)  # AUT-019: the discount needs the price right
    errors: dict[str, str] = {}
    phase = values.get("phase")
    if phase is not None and phase.project_id != project.pk:
        errors["phase"] = _("Choose a phase of this project.")
    vehicle = values.get("vehicle_line")
    if vehicle is not None and vehicle.project_id != project.pk:
        errors["vehicle_line"] = _("Choose a vehicle booked in this project.")
    if values.get("start") and values.get("end") and values["end"] <= values["start"]:
        errors["end"] = _("The end must be after the start.")
    discount = values.get("discount_percent")
    if "discount_percent" in values and (discount is None or not Decimal(0) <= discount <= Decimal(100)):
        errors["discount_percent"] = _("Enter a discount between 0 and 100 per cent.")
    if values.get("planned_hours") is not None and values["planned_hours"] < 0:
        errors["planned_hours"] = _("Enter the hours as a number of 0 or more.")
    if len(values.get("meeting_point") or "") > 200:
        errors["meeting_point"] = _("At most 200 characters.")
    if errors:
        raise ValidationError(errors)


def _edit_changes(line: CrewLine, values: dict[str, Any]) -> dict[str, Any]:
    """The values that differ from the line – what ``crew.update_crew_line`` gets for it."""
    changes = {}
    for name, value in values.items():
        current = getattr(line, f"{name}_id") if name in ("phase", "vehicle_line") else getattr(line, name)
        wanted = value.pk if hasattr(value, "pk") else value
        if current != wanted:
            changes[name] = value
    return changes


def _rule_against(line: CrewLine, action: str) -> str:
    """Why the action cannot be done with this line at all; "" if it can."""
    if action in (CrewBulkAction.FIRM, CrewBulkAction.ASK) and line.person_id is None:
        return _("is an open place")
    if action == CrewBulkAction.ASK and line.request_status == RequestStatus.FIRM:
        return _("is planned firmly")
    return ""


def _already(line: CrewLine, action: str, values: dict[str, Any]) -> bool:
    """Whether the line is as the action wants it already."""
    if action == CrewBulkAction.FIRM:
        return line.request_status in (RequestStatus.FIRM, RequestStatus.ACCEPTED)
    if action == CrewBulkAction.ASK:
        # Asked, or answered, for its times: asked again only once they change (PER-033).
        return bool(line.request_status) and not line.times_changed_since_request
    if action == CrewBulkAction.EDIT:
        return not _edit_changes(line, values)
    return False


def _apply(line: CrewLine, action: str, values: dict[str, Any], *, rights: Rights, user: Any) -> bool | None:
    """Do the action with one line through the service for a single line; ``ask`` returns whether somebody was told."""
    if action == CrewBulkAction.EDIT:
        crew.update_crew_line(line, rights=rights, **_edit_changes(line, values))
    elif action == CrewBulkAction.FIRM:
        crew.update_crew_line(line, rights=rights, firm=True)
    elif action == CrewBulkAction.ASK:
        return crew.request_deployment(line, user=user)
    else:
        crew.delete_crew_line(line)
    return None


def change_crew_lines(
    project: Project,
    line_ids: list[int],
    action: str,
    *,
    rights: Rights,
    user: Any,
    values: dict[str, Any] | None = None,
) -> CrewBulkResult:
    """Do one thing with several crew lines of a project at once (see the module description).

    Args:
        project: The project; works the same for a subproject.
        line_ids: The IDs of the lines; all must belong to the project.
        action: One of :class:`CrewBulkAction`.
        rights: The rights of the caller.
        user: The caller – who asked (PER-016).
        values: For ``edit``: the values to set, names of :data:`EDIT_FIELDS`; ``phase`` and
            ``vehicle_line`` may be ``None`` ("without phase", "no vehicle").

    Raises:
        ValidationError: The project is closed, the action is unknown, a value is missing, invalid, needs a right
            the caller does not have or belongs to another project, or a line is not one of the project's.
    """
    ensure_editable(project)
    if action not in CrewBulkAction.ALL:
        raise ValidationError(_("Unknown action."))
    values = dict(values or {})
    if action == CrewBulkAction.EDIT:
        _check_values(project, values, rights)
    wanted = {int(line_id) for line_id in line_ids}
    if not wanted:
        raise ValidationError(_("Choose at least one crew line."))
    lines = list(
        project.crew_lines.filter(pk__in=wanted)
        .select_related("job_function", "person__user", "project", "service_product", "tax_rate", "phase")
        .order_by("start", "position", "id")
    )
    if len(lines) != len(wanted):
        raise ValidationError(_("Some of the crew lines do not belong to this project."))
    result = CrewBulkResult(action=action)
    with crew_changes.one_notice_per_person() as pending:
        for line in lines:
            reason = _rule_against(line, action)
            if reason:
                result.skipped.append(SkippedCrewLine(line=line, reason=reason))
                continue
            if _already(line, action, values):
                result.unchanged.append(line)
                continue
            line_id, mark = line.pk, len(pending)
            try:
                with transaction.atomic():
                    told = _apply(line, action, values, rights=rights, user=user)
            except ValidationError as error:
                del pending[mark:]  # the step was undone: nobody is told about it
                result.skipped.append(SkippedCrewLine(line=line, reason=" ".join(error.messages)))
                continue
            result.changed.append(line)
            result.changed_ids.append(line_id)
            if action == CrewBulkAction.ASK and not told:
                result.not_told.append(line)
            if getattr(line, "asked_again", None) is not None:
                result.asked_again.append(line)
    if action == CrewBulkAction.EDIT and values.get("discount_percent") is not None:
        # The lines keep what was typed, the price takes the maximum of the job function – said, with the lines.
        entered = values["discount_percent"]
        capped = [
            (crew_line_label(line), line.job_function.max_discount_percent)
            for line in result.changed
            if line.job_function.max_discount_percent is not None and entered > line.job_function.max_discount_percent
        ]
        warning = capped_lines_warning(entered, capped)
        if warning:
            result.warnings.append(warning)
    return result
