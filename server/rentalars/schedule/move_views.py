# SPDX-License-Identifier: GPL-3.0-or-later
"""The dialog that confirms a dragged appointment (VFG-026).

Dropping a bar in a timeline – or pressing Enter after moving it with the
arrow keys, or clicking a bar of the timeline on the tab "Zeitplanung" –
opens this dialog over the page (``app.js``). It names what is moved, its
former and its new times – both can still be changed in the fields – and
what follows (``schedule.moves.preview_move``): the crew moving along and
who is asked again (PRJ-080, PER-034), the rental period that would cover
a phase (PRJ-100), the material missing with a new rental period (PRJ-012),
the schedule that follows a rental period moved as a whole. A change of the
times asks the server again for this part of the dialog only.

VFG-031: the same dialog confirms a deployment (crew line) dragged in
the personnel plan (``what=crew&line=<id>``): its new times, the planned
hours that follow, whether the person is asked again and the warnings at the
new times.

PRJ-121: a deployment dragged on "Zeitplanung"
(``from=course``) may take its phase – or the open places of its job function
– along (``moves.followers_of``); the dialog says what and why, with the box
"follow", ticked at first.

"Verschieben" saves (``schedule.moves.perform_move``) and shows what was done;
closing that view loads the page again. Without the page script the same
form is a page of its own, which leads back to the timeline (``next``).
"""

from __future__ import annotations

import json
from typing import Any

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext

from rentalars.accounts.rights import Level, Module, module_required, request_rights
from rentalars.core.forms import StyledForm
from rentalars.projects.access import ProjectAccess, project_for
from rentalars.projects.models import CrewLine, Project, ProjectPhase
from rentalars.schedule import moves


class MoveForm(StyledForm):
    """The new times and the answers of the dialog (VFG-026).

    ``sent`` tells a form that came back from the dialog – where an unticked
    box sends nothing – from the first call, which ticks the boxes.
    """

    start = forms.DateTimeField(label=gettext_lazy("From"))
    end = forms.DateTimeField(label=gettext_lazy("Until"))
    move_crew = forms.BooleanField(label=gettext_lazy("Move the crew of this phase along"), required=False)
    with_schedule = forms.BooleanField(
        label=gettext_lazy("Move the event, the phases and the crew along"), required=False
    )
    extend = forms.BooleanField(label=gettext_lazy("Extend the rental period"), required=False)
    #: PRJ-121: the phase – or the open places of the job function – follow the deployment.
    follow = forms.BooleanField(label=gettext_lazy("Move along what follows"), required=False)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # IDs of their own: the page under the dialog may have fields called "start" and "end" as well.
        kwargs.setdefault("auto_id", "move-%s")
        super().__init__(*args, **kwargs)
        for name in ("move_crew", "with_schedule", "extend", "follow"):
            self.fields[name].widget.attrs["aria-describedby"] = f"move-{name}-help"

    def clean(self) -> dict[str, Any]:
        """The end after the start."""
        data = super().clean()
        if data.get("start") and data.get("end") and data["end"] <= data["start"]:
            self.add_error("end", _("The end must be after the start."))
        return data


def _moment(value: Any) -> str:
    return moves.wall_clock(value) if value is not None else ""


def _target(project: Project, values: Any) -> tuple[str, ProjectPhase | None, CrewLine | None]:
    """What the address names: the rental period, the event, a phase or a crew line of the project."""
    what = values.get("what", "")
    if what not in moves.KINDS:
        raise Http404
    phase = None
    if what == moves.CREW:
        line_id = str(values.get("line", ""))
        if not line_id.isdigit():
            raise Http404
        line = get_object_or_404(
            CrewLine.objects.select_related("job_function", "person", "phase", "project"),
            pk=int(line_id),
            project=project,
        )
        return what, None, line
    if what == moves.PHASE:
        phase_id = str(values.get("phase", ""))
        if not phase_id.isdigit():
            raise Http404
        phase = get_object_or_404(ProjectPhase.objects.select_related("venue_site"), pk=int(phase_id), project=project)
    elif what == moves.EVENT and project.event_start is None:
        raise Http404
    return what, phase, None


def _from_course(values: Any) -> bool:
    """PRJ-121: the move comes from "Zeitplanung" – a deployment may take its phase along."""
    return values.get("from") == "course"


def _next_url(request: HttpRequest, values: Any, project: Project) -> str:
    """Where the page without script leads back to: the timeline it came from, else the project's schedule."""
    target = str(values.get("next", ""))
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return reverse("projects:course", args=[project.pk])


def _form(values: Any, old: tuple[Any, Any]) -> MoveForm:
    """The form: what was sent, else the former times and every box ticked but the extension."""
    sent = "sent" in values
    data = {
        "start": values.get("start") or _moment(old[0]),
        "end": values.get("end") or _moment(old[1]),
        "move_crew": values.get("move_crew") if sent else "on",
        "with_schedule": values.get("with_schedule") if sent else "on",
        "extend": values.get("extend") if sent else "",
        "follow": values.get("follow") if sent else "on",  # PRJ-121: only on "Zeitplanung" (_from_course)
    }
    return MoveForm({name: value for name, value in data.items() if value})  # an unticked box is left out


@module_required(Module.PROJECTS, Level.WRITE)
def move(request: HttpRequest, pk: int) -> HttpResponse:
    """Confirm a move of the rental period, the event, a phase or a crew line of a project, and do it (VFG-026).

    ``GET`` with ``what`` (``period``, ``event``, ``phase`` and ``phase``, ``crew`` and ``line`` – VFG-031),
    ``start`` and ``end`` (``2027-03-10T14:15``; without them the present
    times) shows the dialog; with the header ``HX-Target: move-consequences``
    only its part with the consequences. ``POST`` moves. Whoever may not edit
    the project gets "not allowed" (AUT-025); a closed project says so
    (PRJ-009).
    """
    project = project_for(request, pk, ProjectAccess.EDIT, queryset=Project.objects.select_related("parent"))
    values = request.POST if request.method == "POST" else request.GET
    what, phase, line = _target(project, values)
    probe = moves.MoveRequest(
        project=project, what=what, phase=phase, crew_line=line, start=project.start, end=project.end
    )
    old = (probe.old_start, probe.old_end)
    form = _form(values, old)
    rights = request_rights(request)
    in_dialog = bool(request.headers.get("HX-Request"))
    preview = None
    if form.is_valid():
        move_request = moves.MoveRequest(
            project=project,
            what=what,
            phase=phase,
            crew_line=line,
            start=form.cleaned_data["start"],
            end=form.cleaned_data["end"],
            move_crew=form.cleaned_data["move_crew"],
            with_schedule=form.cleaned_data["with_schedule"],
            extend=form.cleaned_data["extend"],
            # PRJ-121: offered for a deployment on "Zeitplanung" only; elsewhere nothing follows it.
            follow=form.cleaned_data["follow"] if what == moves.CREW and _from_course(values) else None,
        )
        if request.method == "POST":
            try:
                outcome = moves.perform_move(move_request, rights=rights, user=request.user)
            except ValidationError as error:
                form.add_error(None, error)
            else:
                return _done(request, outcome, in_dialog=in_dialog, next_url=_next_url(request, values, project))
        preview = moves.preview_move(move_request, rights=rights, user=request.user)
    context = {
        "project": project,
        "what": what,
        "phase": phase,
        "line": line,
        "name": moves.label_of(project, what, phase, line),
        "old_text": moves.period_text(*old),
        "form": form,
        "preview": preview,
        "action": reverse("schedule:move", args=[project]),
        "next": _next_url(request, values, project),
        "from_course": _from_course(values),  # PRJ-121: kept in the form for the box "follow"
        # Without the page script the form is a page of its own; its consequences still come back in parts.
        "page": not in_dialog or bool(values.get("page")),
    }
    if request.headers.get("HX-Target") == "move-consequences":
        return render(request, "schedule/_move_consequences.html", {**context, "partial": True})
    if in_dialog:
        return render(request, "schedule/_move_dialog.html", context)
    return render(request, "schedule/move.html", context)


def notes_of(outcome: moves.MoveOutcome) -> list[tuple[str, str]]:
    """What a move did, as message level and text – the same words as the forms use (PRJ-080, PER-034, PRJ-100)."""
    notes: list[tuple[str, str]] = []
    for change in outcome.changes:
        notes.append(
            (
                "success",
                _("%(what)s: now %(new)s (before %(old)s).")
                % {"what": change.label, "new": change.after, "old": change.before},
            )
        )
    if outcome.material_lines:
        notes.append(
            (
                "info",
                ngettext(
                    "%(count)d material line had the former rental period and took the new one.",
                    "%(count)d material lines had the former rental period and took the new one.",
                    outcome.material_lines,
                )
                % {"count": outcome.material_lines},
            )
        )
    if outcome.hours_after is not None:
        notes.append(("info", hours_note(outcome)))
    # PRJ-121: a deployment that took its phase or open places along counts those, not itself.
    along = len(outcome.crew) - 1 if outcome.move.what == moves.CREW else len(outcome.crew)
    if along > 0:
        notes.append(
            (
                "info",
                ngettext(
                    "%(count)d crew line moved along.",
                    "%(count)d crew lines moved along.",
                    along,
                )
                % {"count": along},
            )
        )
    if outcome.vehicle_lines:  # LOG-001: with a phase that followed a deployment (PRJ-121)
        notes.append(
            (
                "info",
                ngettext(
                    "%(count)d vehicle booking moved along with the phase.",
                    "%(count)d vehicle bookings moved along with the phase.",
                    outcome.vehicle_lines,
                )
                % {"count": outcome.vehicle_lines},
            )
        )
    for change in outcome.asked_again:
        if change.asked_again:
            text = _("%(person)s was asked again for the new times.") % {"person": change.who}
        else:
            text = _("The times changed: the line is “asked” again. Enter the answer of %(person)s when it comes.") % {
                "person": change.who
            }
        notes.append(("info", text))
    for change in outcome.with_warnings:
        notes.extend(("warning", f"{change.who}: {warning}") for warning in change.warnings)
    notes.extend(("warning", text) for text in outcome.warnings)  # PRJ-005: event end after "material back by"
    if outcome.shortage_grew:
        count = outcome.shortage_after or 0
        notes.append(
            (
                "warning",
                ngettext(
                    "With the new rental period %(count)d piece is missing. See the lines marked in red.",
                    "With the new rental period %(count)d pieces are missing. See the lines marked in red.",
                    count,
                )
                % {"count": count},
            )
        )
    return notes


def hours_note(outcome: moves.MoveOutcome) -> str:
    """VFG-031: the planned hours of a moved deployment followed its period (PRJ-023)."""
    from django.utils.formats import number_format

    return _("Planned hours: now %(new)s (before %(old)s).") % {
        "new": number_format(outcome.hours_after, decimal_pos=2),
        "old": number_format(outcome.hours_before, decimal_pos=2),
    }


def _done(request: HttpRequest, outcome: moves.MoveOutcome, *, in_dialog: bool, next_url: str) -> HttpResponse:
    """What was done: in the dialog – the page is loaded again when it closes –, or as messages on the timeline."""
    notes = notes_of(outcome)
    if not in_dialog:
        for level, text in notes:
            getattr(messages, level)(request, text)
        return redirect(next_url)
    response = render(
        request,
        "schedule/_move_done.html",
        {"name": outcome.move.name, "notes": notes, "project": outcome.project},
    )
    # app.js loads the page again when the dialog is closed, and puts the focus back on the bar.
    response["HX-Trigger"] = json.dumps({"timelineMoved": {"key": outcome.move.key}})
    return response
