# SPDX-License-Identifier: GPL-3.0-or-later
"""Forms of the time tracking module."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import Rights
from rentalars.core.forms import RowLayoutMixin, StyledForm, mark_required
from rentalars.core.money import format_decimal, format_money
from rentalars.personnel.models import JobFunction, Person
from rentalars.projects.family_labels import project_label
from rentalars.projects.models import CrewLine, Project
from rentalars.timetracking import services
from rentalars.timetracking.models import (
    MAX_EXPENSE_AMOUNT,
    MAX_KILOMETRES,
    Expense,
    ExpenseKind,
    TimeEntry,
    TimeEntryStatus,
)

#: The value of the choice "without project" in the project selection (ZEI-023).
WITHOUT_PROJECT = "none"

#: Headings of the groups in the project selection, by the reason a project is offered (ZEI-006).
REASON_LABELS = {
    "now": _("Planned right now"),
    "planned": _("Planned"),
    "internal": _("Internal"),
    "other": _("Other projects"),
    # ZEI-024: open service cases, those the person takes part in first.
    "service_case": _("Service cases"),
}

#: ZEI-025: the value of a crew line in the job function selection, "line:<id>"; a job function is its ID.
LINE_PREFIX = "line:"

#: ZEI-025: how many rows for further job functions of the period the form offers at least.
PART_ROWS = 3

#: ZEI-025: the most rows for further job functions.
MAX_PART_ROWS = 12


class TimeEntryForm(RowLayoutMixin, StyledForm):
    """Record or correct a time entry with few entries (ZEI-003, ZEI-004).

    Asked for: project, job function, day, begin, end, break, note. The
    project list starts with the projects the person is planned in right now,
    and the job function is prefilled from the crew line (ZEI-006). An end
    before the begin means "the next day" (ZEI-009: over midnight). At the
    end of the list stands "without project – assign later" (ZEI-023); then
    only the person's own job functions are offered.

    ZEI-007: the job function selection is never empty – besides the
    person's own and planned job functions, those of the project's crew, and
    for somebody without any of these every active job function
    (``services.job_functions_for``).

    ZEI-024: the open service cases are offered too, with every job function.

    ZEI-025: the job function selection suggests the person's crew lines in
    the project first, with their phase and times ("Licht – Aufbau, Fr
    16.10. 08:00–12:00"), then the job functions. Further job functions of
    the same period, each with its hours, divide the period
    (``part_<n>_function``, ``part_<n>_hours``); the job function above gets
    the hours that are left.

    The form does not save by itself: :meth:`values` returns what
    ``timetracking.services`` expects – the same functions the API uses.
    """

    project = forms.ChoiceField(label=_("Project"))
    job_function = forms.ChoiceField(label=_("Job function"))
    day = forms.DateField(label=_("Day"))
    begin = forms.TimeField(label=_("Begin"))
    end = forms.TimeField(label=_("End"), help_text=_("Earlier than the begin: the next day."))
    break_minutes = forms.IntegerField(
        label=_("Break (minutes)"), min_value=0, max_value=600, initial=0, required=False
    )
    note = forms.CharField(label=_("Note"), max_length=250, required=False)
    submit = forms.BooleanField(
        label=_("Hand in for approval right away"),
        required=False,
        initial=True,
        help_text=_("Without the tick the entry stays with you until you hand it in."),
    )

    LAYOUT = (("project",), ("job_function",), ("day",), ("begin", "end"), ("break_minutes",), ("note",), ("submit",))

    def __init__(
        self,
        *args: Any,
        person: Person,
        rights: Rights,
        user: Any,
        entry: TimeEntry | None = None,
        project_id: int | str | None = None,
        **kwargs: Any,
    ) -> None:
        self.person = person
        self.entry = entry
        initial = kwargs.setdefault("initial", {})
        choices = services.project_choices(person, rights, user, service_cases=True)
        known = {choice.project.pk: choice for choice in choices}
        #: ZEI-025: the parts of the entry's period, the first one being the entry shown above.
        self.period = services.period_of(entry) if entry is not None else []
        if entry is not None:
            first = self.period[0]
            start, end = timezone.localtime(first.start), timezone.localtime(first.end) if first.end else None
            initial.update(
                project=str(first.project_id) if first.project_id else WITHOUT_PROJECT,
                day=start.date(),
                begin=start.time(),
                end=end.time() if end else None,
                break_minutes=first.break_minutes,
                note=first.note,
                submit=first.status == TimeEntryStatus.SUBMITTED,
            )
            if first.project_id and first.project_id not in known:
                # The project of an old entry may no longer be among the suggestions.
                known[first.project_id] = services.ProjectChoice(first.project, "other")
                choices.append(known[first.project_id])
        super().__init__(*args, **kwargs)

        # The project: from the data sent, the address, the entry – or the best guess (ZEI-006).
        selected = str(self.data.get("project") or project_id or initial.get("project") or "")
        selected_id = int(selected) if selected.isdigit() and int(selected) in known else None
        # ZEI-024: a service case the person does not take part in is never the guess.
        likely = [choice for choice in choices if choice.reason != "service_case" or choice.takes_part]
        if selected_id is None and likely and selected != WITHOUT_PROJECT:
            selected_id = likely[0].project.pk
        self.selected = known.get(selected_id) if selected_id else None

        grouped: dict[str, list[tuple[str, str]]] = {}
        for choice in choices:
            # PRJ-048: "2026-0042-1 Bühne Marktplatz (Stadtfest)" – a part with the name of its whole project.
            grouped.setdefault(str(REASON_LABELS[choice.reason]), []).append(
                (str(choice.project.pk), project_label(choice.project))
            )
        grouped[str(_("Without project"))] = [(WITHOUT_PROJECT, str(_("assign later")))]
        #: Nothing to choose but "without project" – the dialog says so (ZEI-023).
        self.only_without_project = not likely
        self.fields["project"].choices = list(grouped.items())
        self.projects = {choice.project.pk: choice.project for choice in choices}
        self.initial["project"] = str(selected_id) if selected_id else WITHOUT_PROJECT

        project = self.selected.project if self.selected else None
        functions = services.job_functions_for(person, project)
        lines = services.crew_lines_for(person, project)
        self.functions = {str(function.pk): function for function in functions}
        self.lines = {f"{LINE_PREFIX}{line.pk}": line for line in lines}
        function_options = [(str(function.pk), function.name) for function in functions]
        if lines:
            # ZEI-025: the deployments of the person first, with phase and times.
            options: list[Any] = [
                (
                    str(_("Planned for you")),
                    [(key, services.crew_line_label(line)) for key, line in self.lines.items()],
                ),
                (str(_("Job functions")), function_options),
            ]
        else:
            options = function_options
        # No "---------" to tap away: one of the person's job functions is always preselected (ZEI-003).
        self.fields["job_function"].choices = options
        if entry is not None:
            self.initial["job_function"] = self._value_of(self.period[0])
        elif not self.is_bound or "job_function" not in self.initial:
            # The job function of the deployment in progress (ZEI-006); its crew line is found from the time.
            preset = self.selected.job_function if self.selected and self.selected.job_function else None
            self.initial["job_function"] = str(preset.pk) if preset else (str(functions[0].pk) if functions else None)

        # ZEI-025: further job functions of the same period, each with its hours.
        sent_rows = sum(1 for name in self.data if name.startswith("part_") and name.endswith("_function"))
        self.part_rows = min(max(PART_ROWS, len(self.period), sent_rows), MAX_PART_ROWS)
        part_options = [("", str(_("– none –"))), *options]
        for index in range(self.part_rows):
            self.fields[f"part_{index}_function"] = forms.ChoiceField(
                label=_("Further job function %(number)s") % {"number": index + 1},
                choices=part_options,
                required=False,
            )
            self.fields[f"part_{index}_hours"] = forms.DecimalField(
                label=_("Hours of job function %(number)s") % {"number": index + 1},
                required=False,
                min_value=Decimal("0.01"),
                max_value=Decimal("24"),
                decimal_places=2,
            )
        for index, part in enumerate(self.period[1:]):
            self.initial[f"part_{index}_function"] = self._value_of(part)
            self.initial[f"part_{index}_hours"] = part.hours
        self.initial.setdefault("day", timezone.localdate())
        self.style_fields()
        self.without_browser_history()

    def _value_of(self, entry: TimeEntry) -> str:
        """ZEI-025: the value of an entry's job function in the selection – its crew line where that is offered."""
        key = f"{LINE_PREFIX}{entry.crew_line_id}"
        return key if entry.crew_line_id and key in self.lines else str(entry.job_function_id)

    def _resolve(self, value: str) -> tuple[JobFunction | None, CrewLine | None]:
        """ZEI-025: job function and crew line of a value of the selection."""
        if value in self.lines:
            line = self.lines[value]
            return line.job_function, line
        return self.functions.get(value), None

    def rows(self) -> list[list[forms.BoundField]]:
        """The fields row by row – without the further job functions, which the dialog shows by themselves."""
        return [row for row in super().rows() if not row[0].name.startswith("part_")]

    def part_fields(self) -> list[tuple[forms.BoundField, forms.BoundField]]:
        """ZEI-025: the rows for further job functions: (job function, hours)."""
        return [(self[f"part_{index}_function"], self[f"part_{index}_hours"]) for index in range(self.part_rows)]

    @property
    def has_parts(self) -> bool:
        """ZEI-025: whether further job functions are given – the dialog then shows them open."""
        if self.is_bound:
            return any(
                self.data.get(f"part_{index}_function") or self.data.get(f"part_{index}_hours")
                for index in range(self.part_rows)
            )
        return len(self.period) > 1

    def clean(self) -> dict[str, Any]:
        """Build start and end from day and times; an end before the begin lies on the next day.

        ZEI-025: the further job functions become the parts of the period;
        the job function above gets the hours that are left.
        """
        cleaned = super().clean() or {}
        day, begin, end = cleaned.get("day"), cleaned.get("begin"), cleaned.get("end")
        if day and begin and end:
            zone = timezone.get_current_timezone()
            start_at = datetime.datetime.combine(day, begin, tzinfo=zone)
            end_at = datetime.datetime.combine(day, end, tzinfo=zone)
            if end_at <= start_at:
                end_at += datetime.timedelta(days=1)
            cleaned["start_at"], cleaned["end_at"] = start_at, end_at
        project_id = cleaned.get("project")
        cleaned["project_object"] = None
        if project_id and str(project_id).isdigit():
            cleaned["project_object"] = (
                self.projects.get(int(project_id)) or Project.objects.filter(pk=project_id).first()
            )
        function, line = self._resolve(str(cleaned.get("job_function") or ""))
        if function is None and "job_function" not in self.errors:
            self.add_error("job_function", _("Choose the job function."))
        cleaned["job_function_object"], cleaned["crew_line"] = function, line
        further = []
        for index in range(self.part_rows):
            value, hours = cleaned.get(f"part_{index}_function"), cleaned.get(f"part_{index}_hours")
            if not value and hours is None:
                continue
            if not value:
                self.add_error(f"part_{index}_function", _("Choose the job function of these hours."))
                continue
            if hours is None:
                if f"part_{index}_hours" not in self.errors:
                    self.add_error(f"part_{index}_hours", _("Enter the hours of this job function."))
                continue
            part_function, part_line = self._resolve(value)
            if part_function is not None:
                further.append(services.Part(part_function, hours, part_line))
        cleaned["parts"] = [services.Part(function, None, line), *further] if further and function else None
        return cleaned

    def values(self) -> dict[str, Any]:
        """Return the entry as ``timetracking.services.create_entry`` and ``update_entry`` expect it."""
        data = self.cleaned_data
        return {
            "project": data.get("project_object"),
            "job_function": data["job_function_object"],
            "crew_line": data.get("crew_line"),
            "parts": data.get("parts"),
            "start": data["start_at"],
            "end": data["end_at"],
            "break_minutes": data.get("break_minutes") or 0,
            "note": data.get("note", ""),
        }

    def period_values(self) -> dict[str, Any]:
        """ZEI-025: the entry as ``timetracking.services.save_period`` expects it – with its parts."""
        values = self.values()
        parts = values.pop("parts") or [services.Part(values["job_function"], None, values["crew_line"])]
        del values["job_function"], values["crew_line"]
        return {**values, "parts": parts}


class CorrectionForm(TimeEntryForm):
    """ZEI-030: a time waiting for approval, corrected and approved in one step.

    The fields of the entry dialog – project, job function, day, begin, end,
    break, note – without "hand in" and without "without project": an
    approved time belongs to a project. The period is not divided here: the
    job function is that of this entry – for a part of a period divided into
    job functions that of this part –, times, break, project and note hold
    for the whole period (ZEI-025). ``correction()`` returns what
    ``services.correct_and_approve`` expects – the function the API uses.
    """

    LAYOUT = (("project",), ("job_function",), ("day",), ("begin", "end"), ("break_minutes",), ("note",))

    def __init__(self, *args: Any, entry: TimeEntry, rights: Rights, user: Any, **kwargs: Any) -> None:
        super().__init__(*args, person=entry.person, rights=rights, user=user, entry=entry, **kwargs)
        del self.fields["submit"]
        for index in range(self.part_rows):
            del self.fields[f"part_{index}_function"], self.fields[f"part_{index}_hours"]
        self.part_rows = 0
        self.fields["project"].choices = [
            (label, options)
            for label, options in self.fields["project"].choices
            if not any(value == WITHOUT_PROJECT for value, _label in options)
        ]
        self.initial["job_function"] = self._value_of(entry)

    def clean(self) -> dict[str, Any]:
        """As the entry dialog; the project is required."""
        cleaned = super().clean()
        if cleaned.get("project_object") is None and "project" not in self.errors:
            self.add_error("project", _("An approved time belongs to a project. Choose it."))
        return cleaned

    def correction(self) -> dict[str, Any]:
        """The corrected values as ``services.correct_and_approve`` expects them."""
        values = self.values()
        values.pop("parts", None)
        return values


def _project_choices(choices: list[services.ProjectChoice]) -> list[tuple[str, list[tuple[str, str]]]]:
    """The projects of the selection grouped by why they are offered (ZEI-006), as choices of a field."""
    grouped: dict[str, list[tuple[str, str]]] = {}
    for choice in choices:
        grouped.setdefault(str(REASON_LABELS[choice.reason]), []).append(
            (str(choice.project.pk), project_label(choice.project))
        )
    return list(grouped.items())


class ExpenseForm(RowLayoutMixin, StyledForm):
    """Record or correct an expense with few entries, also on the phone (ZEI-019).

    Asked for: project, kind, day, amount – or the kilometres of a trip with
    the own car, which give the amount –, a note and a photo of the receipt.
    The projects are offered as in the quick time entry: first those the
    person is planned in right now (ZEI-006).

    The form does not save by itself: :meth:`values` returns what
    ``timetracking.expenses`` expects – the same functions the API uses.
    """

    project = forms.ChoiceField(label=_("Project"))
    kind = forms.ChoiceField(label=_("Kind"), choices=ExpenseKind.choices)
    date = forms.DateField(label=_("Day"))
    kilometres = forms.DecimalField(
        label=_("Kilometres"),
        required=False,
        min_value=Decimal("0.1"),
        max_value=MAX_KILOMETRES,
        decimal_places=1,
    )
    amount = forms.DecimalField(
        label=_("Amount in euros"),
        required=False,
        min_value=Decimal("0.01"),
        max_value=MAX_EXPENSE_AMOUNT,
        decimal_places=2,
    )
    note = forms.CharField(
        label=_("Note"),
        max_length=250,
        required=False,
        help_text=_("What it was, e.g. “Warehouse – town hall and back”."),
    )
    receipt = forms.FileField(
        label=_("Receipt"),
        required=False,
        help_text=_("A photo or a PDF file. On a phone you can take the photo right away."),
        widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png,application/pdf"}),
    )
    remove_receipt = forms.BooleanField(label=_("Remove the receipt"), required=False)
    submit = forms.BooleanField(
        label=_("Hand in for approval right away"),
        required=False,
        initial=True,
        help_text=_("Without the tick the expense stays with you until you hand it in."),
    )

    LAYOUT = (
        ("project",),
        ("kind", "date"),
        ("kilometres", "amount"),
        ("note",),
        ("receipt",),
        ("remove_receipt",),
        ("submit",),
    )

    def __init__(
        self,
        *args: Any,
        person: Person,
        rights: Rights,
        user: Any,
        expense: Expense | None = None,
        project_id: int | str | None = None,
        **kwargs: Any,
    ) -> None:
        from rentalars.core.models import SystemSettings

        self.person = person
        self.expense = expense
        initial = kwargs.setdefault("initial", {})
        choices = services.project_choices(person, rights, user)
        known = {choice.project.pk: choice for choice in choices}
        if expense is not None:
            initial.update(
                project=str(expense.project_id),
                kind=expense.kind,
                date=expense.date,
                kilometres=expense.kilometres,
                amount=expense.amount,
                note=expense.note,
                submit=expense.status == TimeEntryStatus.SUBMITTED,
            )
            if expense.project_id not in known:
                known[expense.project_id] = services.ProjectChoice(expense.project, "other")
                choices.append(known[expense.project_id])
        super().__init__(*args, **kwargs)
        selected = str(self.data.get("project") or project_id or initial.get("project") or "")
        selected_id = int(selected) if selected.isdigit() and int(selected) in known else None
        if selected_id is None and choices:
            selected_id = choices[0].project.pk
        self.fields["project"].choices = _project_choices(choices)
        self.initial["project"] = str(selected_id) if selected_id else ""
        self.projects = {choice.project.pk: choice.project for choice in choices}
        #: Nothing to book on: the dialog says so.
        self.nothing_to_book = not choices
        self.initial.setdefault("date", timezone.localdate())
        rate = expense.km_rate if expense is not None and expense.km_rate is not None else None
        rate = rate if rate is not None else SystemSettings.load().expense_km_rate
        #: The rate per kilometre a trip of this form is calculated with; the dialog names it.
        self.km_rate = rate
        self.fields["kilometres"].help_text = _("× %(rate)s per kilometre gives the amount.") % {
            "rate": format_money(rate)
        }
        if person.commute_km and SystemSettings.load().expense_deduct_commute:
            # ZEI-027: the way to work there and back is deducted once a day per project.
            self.fields["kilometres"].help_text += " " + _(
                "Your way to work there and back (%(kilometres)s km) is deducted once a day per project."
            ) % {"kilometres": format_decimal(person.commute_km * 2, max_places=1)}
        # UIX-035: the amount is required except for a trip, which may give kilometres instead.
        mark_required(self.fields["amount"], "kind=meals|lodging|parking|other")
        if expense is None or not expense.receipt:
            del self.fields["remove_receipt"]
        self.style_fields()
        self.without_browser_history()

    def clean(self) -> dict[str, Any]:
        """A trip needs kilometres or an amount; everything else an amount."""
        cleaned = super().clean() or {}
        kind, kilometres, amount = cleaned.get("kind"), cleaned.get("kilometres"), cleaned.get("amount")
        if kind == ExpenseKind.TRAVEL:
            if kilometres is None and amount is None and "kilometres" not in self.errors:
                self.add_error("kilometres", _("Enter the kilometres of the trip, or the amount of a ticket."))
        else:
            cleaned["kilometres"] = None
            if amount is None and "amount" not in self.errors:
                self.add_error("amount", _("Enter the amount."))
        project_id = str(cleaned.get("project") or "")
        cleaned["project_object"] = (
            self.projects.get(int(project_id)) or Project.objects.filter(pk=project_id).first()
            if project_id.isdigit()
            else None
        )
        if cleaned["project_object"] is None and "project" not in self.errors:
            self.add_error("project", _("Choose the project."))
        return cleaned

    def values(self) -> dict[str, Any]:
        """Return the expense as ``timetracking.expenses.create_expense`` and ``update_expense`` expect it."""
        data = self.cleaned_data
        kilometres = data.get("kilometres")
        return {
            "project": data["project_object"],
            "kind": data["kind"],
            "date": data["date"],
            "kilometres": kilometres,
            "amount": data.get("amount") if kilometres is None else None,
            "note": data.get("note", ""),
        }


#: The statuses the expense report can be narrowed to (ZEI-019): those of times, and two of reimbursement.
EXPENSE_STATUS_FILTERS = (
    ("", _("All except rejected")),
    *TimeEntryStatus.choices,
    ("outstanding", _("approved, not reimbursed yet")),
    ("reimbursed", _("reimbursed")),
)


class ExpenseFilterForm(StyledForm):
    """The filter of the expense report (ZEI-019): person, project, kind, period, status."""

    person = forms.ModelChoiceField(
        label=_("Person"), queryset=Person.objects.none(), required=False, empty_label=_("All")
    )
    project = forms.ModelChoiceField(
        label=_("Project"), queryset=Project.objects.none(), required=False, empty_label=_("All")
    )
    kind = forms.ChoiceField(label=_("Kind"), required=False, choices=[("", _("All")), *ExpenseKind.choices])
    since = forms.DateField(label=_("From"), required=False)
    until = forms.DateField(label=_("Until"), required=False)
    status = forms.ChoiceField(label=_("Status"), required=False, choices=EXPENSE_STATUS_FILTERS)

    def __init__(self, *args: Any, people: Any, projects: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["person"].queryset = people
        self.fields["project"].queryset = projects
        self.fields["project"].label_from_instance = project_label


class ReportFilterForm(StyledForm):
    """The filter of the hours report (ZEI-015): person, project, job function, period, status."""

    person = forms.ModelChoiceField(
        label=_("Person"), queryset=Person.objects.none(), required=False, empty_label=_("All")
    )
    # A choice, not a model choice: "without project" is one of the options (ZEI-023).
    project = forms.ChoiceField(label=_("Project"), required=False)
    job_function = forms.ModelChoiceField(
        label=_("Job function"), queryset=JobFunction.objects.all(), required=False, empty_label=_("All")
    )
    since = forms.DateField(label=_("From"), required=False)
    until = forms.DateField(label=_("Until"), required=False)
    status = forms.ChoiceField(
        label=_("Status"), required=False, choices=[("", _("All except rejected")), *TimeEntryStatus.choices]
    )
    group_by = forms.ChoiceField(
        label=_("Add up by"),
        required=False,
        choices=[
            ("person", _("person")),
            ("project", _("project")),
            ("job_function", _("job function")),
            ("day", _("day")),
        ],
    )
    # ZEI-018: only the entries with a hint – a long working day, a short break or rest.
    with_hints = forms.BooleanField(label=_("Only entries with hints"), required=False)

    def __init__(self, *args: Any, people: Any, projects: Any, **kwargs: Any) -> None:
        from rentalars.core.models import SystemSettings

        super().__init__(*args, **kwargs)
        if not SystemSettings.load().time_hints_enabled:
            # ZEI-018: hints switched off in the settings – nothing to narrow to.
            del self.fields["with_hints"]
        self.fields["person"].queryset = people
        self.fields["project"].choices = [
            ("", _("All")),
            (WITHOUT_PROJECT, _("without project")),
            *((str(project.pk), project_label(project)) for project in projects),
        ]
