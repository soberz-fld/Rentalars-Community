# SPDX-License-Identifier: GPL-3.0-or-later
"""The form of a trip changed or added by hand (PRJ-111)."""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from rentalars.core.forms import StyledForm
from rentalars.core.maps import MAX_WAYPOINTS
from rentalars.projects.trips import Trip


class TripForm(StyledForm):
    """Departure, start, stops, destination, title and note of a trip (PRJ-111).

    Changing a trip Rentalars determines, the form starts with its current
    values; what stays as determined keeps following the phases, and an
    empty start or destination keeps the determined one
    (``trip_changes.change_trip``). A trip of one's own needs both. The
    stops are typed one per line.
    """

    title = forms.CharField(label=_("Title"), max_length=120, required=False)
    start = forms.DateTimeField(label=_("Departure"))
    origin = forms.CharField(label=_("Start"), max_length=250, required=False, help_text=_("An address in one line."))
    stops = forms.CharField(
        label=_("Stops"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    destination = forms.CharField(
        label=_("Destination"), max_length=250, required=False, help_text=_("An address in one line.")
    )
    note = forms.CharField(
        label=_("Note"),
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text=_("Visible to the drivers in the overview."),
    )

    def __init__(self, *args: Any, trip: Trip | None = None, **kwargs: Any) -> None:
        if trip is not None:
            kwargs.setdefault("initial", {}).update(
                {
                    "title": trip.title,
                    "start": trip.start,
                    "origin": trip.origin.address,
                    "stops": "\n".join(stop.address for stop in trip.stops),
                    "destination": trip.destination.address,
                    "note": trip.note,
                }
            )
        super().__init__(*args, **kwargs)
        self.fields["stops"].help_text = gettext(
            "One address per line, in the order of the trip; at most %(count)d."
        ) % {"count": MAX_WAYPOINTS}
        for field in self.fields.values():
            field.widget.attrs.setdefault("autocomplete", "off")  # no earlier entries of the browser (UIX-014)

    def stop_list(self) -> list[str]:
        """The stops typed in, one per line."""
        return [line.strip() for line in self.cleaned_data.get("stops", "").splitlines() if line.strip()]

    def values(self) -> dict[str, Any]:
        """What ``trip_changes.change_trip`` and ``add_trip`` take."""
        data = self.cleaned_data
        return {
            "title": data["title"],
            "start": data["start"],
            "origin": data["origin"],
            "stops": self.stop_list(),
            "destination": data["destination"],
            "note": data["note"],
        }
