# SPDX-License-Identifier: GPL-3.0-or-later
"""The form "Change chosen crew lines" (PRJ-117): one value for several crew lines.

What is left empty stays as it is on every line – a list offers "– leave as it is –". A meeting point or a note
is removed with its box "remove". The discount only for who may see prices (AUT-019). The form hands its values to
``crew_bulk.change_crew_lines`` – the service the API calls too (API-002).
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.core.forms import RowLayoutMixin, StyledForm
from rentalars.projects.models import Project

#: The value of a list that means "without": no phase, no vehicle.
NONE = "none"


class CrewBulkForm(RowLayoutMixin, StyledForm):
    """Set meeting point, note, phase, period, hours, vehicle – and the discount – on the chosen crew lines."""

    meeting_point = forms.CharField(label=_("Meeting point"), max_length=200, required=False)
    clear_meeting_point = forms.BooleanField(label=_("Remove the meeting point"), required=False)
    note = forms.CharField(
        label=_("Note"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text=_("Visible to the person in the deployment view. Replaces the note of every chosen line."),
    )
    clear_note = forms.BooleanField(label=_("Remove the note"), required=False)
    phase = forms.ChoiceField(
        label=_("Phase"),
        required=False,
        help_text=_("Without “From” and “Until” the lines take the period of the phase."),
    )
    start = forms.DateTimeField(label=_("From"), required=False)
    end = forms.DateTimeField(label=_("Until"), required=False)
    planned_hours = forms.DecimalField(
        label=_("Planned hours"),
        min_value=0,
        decimal_places=2,
        required=False,
        help_text=_("Empty: hours that follow the period follow the new period, typed-in hours stay."),
    )

    LAYOUT = (
        ("meeting_point", "clear_meeting_point"),
        ("phase",),
        ("start", "end"),
        ("planned_hours", "vehicle_line"),
        ("discount_percent",),
        ("note",),
        ("clear_note",),
    )

    def __init__(self, *args: Any, project: Project, rights: Rights, **kwargs: Any) -> None:
        kwargs.setdefault("auto_id", "crew-bulk-%s")
        super().__init__(*args, **kwargs)
        self.project = project
        keep = ("", _("– leave as it is –"))
        self.phases = {str(phase.pk): phase for phase in project.phases.order_by("start", "pk")}
        self.fields["phase"].choices = [
            keep,
            (NONE, _("without phase")),
            *((key, phase.label) for key, phase in self.phases.items()),
        ]
        # LOG-008: who travels with which motor vehicle of the project.
        self.vehicles = {
            str(vehicle.pk): vehicle
            for vehicle in project.vehicle_lines.filter(product__vehicle_type="car").select_related("item__vehicle")
        }
        if self.vehicles:
            self.fields["vehicle_line"] = forms.ChoiceField(
                label=_("Vehicle"),
                required=False,
                choices=[
                    keep,
                    (NONE, _("– no vehicle –")),
                    *((key, line.label) for key, line in self.vehicles.items()),
                ],
            )
        if rights.has(SpecialRight.PRICES):
            self.fields["discount_percent"] = forms.DecimalField(
                label=_("Discount in percent"), min_value=0, max_value=100, decimal_places=2, required=False
            )
        self.style_fields()
        self.without_browser_history()

    def clean(self) -> dict[str, Any]:
        """At least one value; the end after the start; a value and its "remove" not both."""
        cleaned = super().clean() or {}
        if cleaned.get("start") and cleaned.get("end") and cleaned["end"] <= cleaned["start"]:
            self.add_error("end", _("The end must be after the start."))
        if cleaned.get("clear_meeting_point") and cleaned.get("meeting_point"):
            self.add_error("meeting_point", _("Either a new meeting point, or remove it."))
        if cleaned.get("clear_note") and cleaned.get("note"):
            self.add_error("note", _("Either a new note, or remove it."))
        if not self.errors and not self.values():
            raise forms.ValidationError(_("Choose what to set for the chosen crew lines."))
        return cleaned

    def values(self) -> dict[str, Any]:
        """What to set, as ``crew_bulk.change_crew_lines`` expects it: only what was given."""
        data = self.cleaned_data
        values: dict[str, Any] = {}
        if data.get("clear_meeting_point"):
            values["meeting_point"] = ""
        elif data.get("meeting_point"):
            values["meeting_point"] = data["meeting_point"].strip()
        if data.get("clear_note"):
            values["note"] = ""
        elif data.get("note"):
            values["note"] = data["note"].strip()
        phase = data.get("phase") or ""
        if phase == NONE:
            values["phase"] = None
        elif phase in self.phases:
            values["phase"] = self.phases[phase]
        for name in ("start", "end", "planned_hours", "discount_percent"):
            if data.get(name) is not None:
                values[name] = data[name]
        vehicle = data.get("vehicle_line") or ""
        if vehicle == NONE:
            values["vehicle_line"] = None
        elif vehicle in self.vehicles:
            values["vehicle_line"] = self.vehicles[vehicle]
        return values
