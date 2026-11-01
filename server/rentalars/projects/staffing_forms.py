# SPDX-License-Identifier: GPL-3.0-or-later
"""Forms for personnel by job function and places (PRJ-120; see ``projects.staffing``).

Rows "Funktion + Plätze"
    :class:`FunctionRowsMixin` gives a form as many rows as its hidden field
    ``rows`` says (``function_<i>``, ``places_<i>``). "Weitere Funktion" and
    "Entfernen" are buttons that send the form back to the server
    (:func:`edited_rows`), which answers with one row more or less – in the
    dialog and on a page without the page script alike.

One person per place
    :class:`PhaseStaffingForm` adds, for every row whose job function is
    chosen, a field per place (``person_<i>_<n>``) – as "Neue Exemplare" asks
    for a serial number per item. Without the page script these are lists of
    the people with the job function, each named with what the crew warnings
    would say at the period of the phase; in the dialog they are type-ahead
    fields that ask :func:`rentalars.projects.crew_views.phase_people` (the
    template decides). An empty place stays open.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django import forms
from django.forms.utils import ErrorDict
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from rentalars.core.forms import StyledForm
from rentalars.personnel.models import JobFunction, Person
from rentalars.projects.forms import PhaseForm, people_choices
from rentalars.projects.models import ProjectPhase
from rentalars.projects.staffing import MAX_PLACES, MAX_ROWS, FunctionPlaces, person_hints


def _number(value: Any, default: int, *, low: int, high: int) -> int:
    """A whole number from posted text, kept between ``low`` and ``high``; ``default`` for anything else."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _row_keys(data: dict[str, Any], index: int) -> list[str]:
    """The posted keys of one row: its function, its places and the people of its places."""
    return [
        key for key in data if key in (f"function_{index}", f"places_{index}") or key.startswith(f"person_{index}_")
    ]


def edited_rows(data: Any, *, add: bool = False, remove: int | None = None) -> dict[str, Any]:
    """The posted values with one row more (``add``) or without row ``remove`` – "Weitere Funktion", "Entfernen".

    The rows after a removed one move up with their people. One row always stays.
    """
    plain: dict[str, Any] = {key: data.get(key) for key in data}
    count = _number(plain.get("rows"), 1, low=1, high=MAX_ROWS)
    if remove is not None and 0 <= remove < count:
        for key in _row_keys(plain, remove):
            del plain[key]
        for index in range(remove + 1, count):
            for key in _row_keys(plain, index):
                suffix = key.split("_", 2)[-1] if key.startswith("person_") else ""
                if key.startswith("person_"):
                    plain[f"person_{index - 1}_{suffix}"] = plain.pop(key)
                else:
                    plain[f"{key.rsplit('_', 1)[0]}_{index - 1}"] = plain.pop(key)
        count = max(1, count - 1)
    if add and count < MAX_ROWS:
        count += 1
        plain[f"places_{count - 1}"] = "1"
    plain["rows"] = str(count)
    return plain


class FunctionRowsMixin:
    """Rows "Funktion + Plätze" on a form (PRJ-120): as many as ``rows`` says, at most ten.

    Call :meth:`add_function_rows` in ``__init__``. ``initial_rows`` fills an
    unbound form ("Personal für diese Phase" starts with the open places of the
    phase).
    """

    fields: dict[str, forms.Field]
    data: Any
    is_bound: bool
    initial: dict[str, Any]

    def add_function_rows(self, initial_rows: list[FunctionPlaces] | None = None) -> None:
        """Create the fields of the rows; an unbound form gets ``initial_rows`` or one empty row."""
        if self.is_bound:
            count = _number(self.data.get("rows"), 1, low=1, high=MAX_ROWS)
        else:
            rows = (initial_rows or [])[:MAX_ROWS]
            count = max(1, len(rows))
            for index, row in enumerate(rows):
                self.initial[f"function_{index}"] = row.job_function.pk
                self.initial[f"places_{index}"] = row.places
        self.row_count = count
        self.fields["rows"] = forms.IntegerField(widget=forms.HiddenInput, initial=count, required=False)
        self.initial["rows"] = count
        functions = JobFunction.objects.filter(is_active=True).order_by("name")
        for index in range(count):
            self.fields[f"function_{index}"] = forms.ModelChoiceField(
                label=_("Job function"), queryset=functions, required=False, empty_label=_("– choose –")
            )
            self.fields[f"places_{index}"] = forms.IntegerField(
                label=_("Places"), min_value=1, max_value=MAX_PLACES, initial=1, required=False
            )
            self.fields[f"places_{index}"].widget.attrs.update({"inputmode": "numeric", "class": "narrow-number"})

    def without_errors(self) -> Any:
        """Check the values but show no error: the form came back to add or remove a row, or to show the places."""
        self.full_clean()  # type: ignore[attr-defined]
        self._errors = ErrorDict()
        return self

    @property
    def function_rows(self) -> list[tuple[int, forms.BoundField, forms.BoundField]]:
        """Index, function and places of each row – for the templates."""
        return [(index, self[f"function_{index}"], self[f"places_{index}"]) for index in range(self.row_count)]  # type: ignore[index]

    @property
    def can_add_row(self) -> bool:
        """Whether "Weitere Funktion" may add a row."""
        return self.row_count < MAX_ROWS

    def chosen_rows(self) -> list[FunctionPlaces]:
        """The valid rows with a job function, after ``is_valid``; places default to one."""
        cleaned = getattr(self, "cleaned_data", {})
        rows = []
        for index in range(self.row_count):
            function = cleaned.get(f"function_{index}")
            if function is not None:
                rows.append(FunctionPlaces(function, cleaned.get(f"places_{index}") or 1))
        return rows


class PhaseWithPlacesForm(FunctionRowsMixin, PhaseForm):
    """A new phase with optional rows "Funktion + Plätze" – saving plans that many open places (PRJ-120)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.add_function_rows()
        for index in range(self.row_count):
            self.fields[f"function_{index}"].empty_label = _("– none –")


@dataclass
class PlaceGroup:
    """The places of one row, for the second step: the job function and one field per place."""

    index: int
    job_function: JobFunction
    places: int
    names: list[str] = field(default_factory=list)
    #: Person ID → name and what the crew warnings would say (PRJ-022), for the type-ahead fields.
    people: dict[int, tuple[str, str]] = field(default_factory=dict)


class PhaseStaffingForm(FunctionRowsMixin, StyledForm):
    """The dialog "Personal für diese Phase": job functions with places, then one person per place (PRJ-120).

    The first step are the rows; the second the people of their places, made for
    every row whose job function is chosen in the posted values (:attr:`groups`).
    """

    firm = forms.BooleanField(label=gettext_lazy("Planned firmly (without request)"), required=False)

    def __init__(
        self,
        *args: Any,
        phase: ProjectPhase,
        may_plan_any: bool = False,
        initial_rows: list[FunctionPlaces] | None = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("auto_id", "staff-%s")
        super().__init__(*args, **kwargs)
        self.phase = phase
        self.may_plan_any = may_plan_any
        self.add_function_rows(initial_rows)
        self.groups: list[PlaceGroup] = []
        self._add_place_fields()
        for name, form_field in self.fields.items():
            form_field.widget.attrs.setdefault("autocomplete", "off")
            if name.startswith("function_"):
                form_field.widget.attrs["data-staffing-function"] = "1"

    def _row_values(self, index: int) -> tuple[JobFunction | None, int]:
        """The job function and places of a row as sent – or, unbound, as preset – to make its place fields."""
        values = self.data if self.is_bound else self.initial
        value = str(values.get(f"function_{index}") or "")
        function = JobFunction.objects.filter(is_active=True, pk=int(value)).first() if value.isdigit() else None
        return function, _number(values.get(f"places_{index}"), 1, low=1, high=MAX_PLACES)

    def _add_place_fields(self) -> None:
        """One field per place of every row with a job function, with the people who may fill it."""
        for index in range(self.row_count):
            function, places = self._row_values(index)
            if function is None:
                continue
            choices, _functions_of = people_choices(function, include_others=self.may_plan_any)
            people = list(Person.objects.filter(pk__in=[pk for pk, _label in choices]))
            hints = person_hints(self.phase, function, people)
            labels = dict(choices)
            group = PlaceGroup(index=index, job_function=function, places=places)
            group.people = {pk: (labels[pk], hints.get(pk, "")) for pk in labels}
            options = [("", _("– still open –"))] + [
                (pk, f"{label} – {hints[pk]}" if hints.get(pk) else label) for pk, label in choices
            ]
            for place in range(places):
                name = f"person_{index}_{place}"
                self.fields[name] = forms.ModelChoiceField(
                    label=_("%(function)s, place %(place)d") % {"function": function.name, "place": place + 1},
                    queryset=Person.objects.filter(pk__in=list(labels)),
                    required=False,
                )
                self.fields[name].choices = options
                group.names.append(name)
            self.groups.append(group)

    @property
    def place_groups(self) -> list[tuple[PlaceGroup, list[dict[str, Any]]]]:
        """Every group with its places, for the template."""
        return [(group, self.place_rows(group)) for group in self.groups]

    def place_rows(self, group: PlaceGroup) -> list[dict[str, Any]]:
        """The places of a group for the template: field, chosen person and its name (for the type-ahead)."""
        rows = []
        for place, name in enumerate(group.names):
            bound = self[name]
            value = str(bound.value() or "")
            person = int(value) if value.isdigit() and int(value) in group.people else None
            rows.append(
                {
                    "number": place + 1,
                    "field": bound,
                    "person": person,
                    "person_label": group.people[person][0] if person is not None else "",
                }
            )
        return rows

    def clean(self) -> dict[str, Any]:
        """At least one job function; nobody twice in one function; "firmly" only with a person."""
        cleaned = super().clean() or {}
        if not any(cleaned.get(f"function_{index}") for index in range(self.row_count)):
            self.add_error(None, _("Choose at least one job function."))
            return cleaned
        anybody = False
        for group in self.groups:
            seen: set[int] = set()
            for name in group.names:
                person = cleaned.get(name)
                if person is None:
                    continue
                anybody = True
                if person.pk in seen:
                    self.add_error(
                        name,
                        _("%(person)s is chosen twice for %(function)s.")
                        % {"person": person.name, "function": group.job_function.name},
                    )
                seen.add(person.pk)
        if cleaned.get("firm") and not anybody:
            self.add_error("firm", _("Plan a person first; an open place cannot be planned firmly."))
        return cleaned

    def staffed_rows(self) -> list[FunctionPlaces]:
        """The rows with a job function and the person of each place (``None``: open), after ``is_valid``."""
        groups = {group.index: group for group in self.groups}
        rows = []
        for index in range(self.row_count):
            function = self.cleaned_data.get(f"function_{index}")
            if function is None:
                continue
            places = self.cleaned_data.get(f"places_{index}") or 1
            group = groups.get(index)
            people = [self.cleaned_data.get(name) for name in group.names] if group is not None else []
            rows.append(FunctionPlaces(function, places, people[:places]))
        return rows
