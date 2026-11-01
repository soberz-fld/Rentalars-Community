# SPDX-License-Identifier: GPL-3.0-or-later
"""Import of people from a spreadsheet (IMP-001, IMP-003, IMP-004).

One row per person. A person is found by the e-mail address, or else by
first and last name; found people are updated (IMP-004), the others are
created. The name can come as one column ("Name": "Last name, first name"
as in the exported list, or "First name Last name") or as two columns.

The column "Job functions" lists the functions of a person, separated by
commas: ``Tontechnik, Licht``. A function without rates is assigned without
own rates – the guide values of the function count (PER-029). Rates follow
a colon, the hourly rate and after a slash the day rate:
``Tontechnik: 35,00``, ``Tontechnik: 35,00/280,00``, ``Tontechnik: /280,00``.
Rates are personnel costs; they are only imported with that right (PER-007,
AUT-017). A function the person has gets rates that differ as new rates
from today on; what the row does not name stays. The import never takes a
function away.

IMP-011: the report names what becomes of every row – new, changed
with every field old → new (new job functions, new rates), unchanged, or
the errors of the row. Rates are shown only with the right to see
personnel costs.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from rentalars.accounts.rights import SpecialRight
from rentalars.core.audit import acting_as, record_event
from rentalars.core.import_rows import CHANGED, NEW, UNCHANGED, RowLog, cells_by_number, label_from, snapshot
from rentalars.core.models import SystemSettings
from rentalars.core.tabular import (
    ImportField,
    ImportIssue,
    ImportReport,
    Progress,
    Table,
    cell_text,
    choice_of,
    messages_of,
    no_progress,
    normalise,
    parse_bool,
    parse_decimal,
)
from rentalars.personnel.models import EmploymentKind, JobFunction, Person, PersonJobFunction
from rentalars.personnel.services import current_rates, save_person, set_rate

IMPORT_FIELDS: tuple[ImportField, ...] = (
    ImportField("name", "Name", False, ("name, vorname", "nachname, vorname", "person")),
    ImportField("first_name", "Vorname", False, ("first name",)),
    ImportField("last_name", "Nachname", False, ("familienname", "last name")),
    ImportField("kind", "Art", False, ("beschäftigung", "anstellung", "kind")),
    ImportField("functions", "Funktionen", False, ("funktion", "job functions", "tätigkeiten")),
    ImportField("email", "E-Mail", False, ("e-mail-adresse", "mail", "email")),
    ImportField("phone", "Telefon", False, ("tel.", "mobil", "handy", "phone")),
    ImportField("company", "Firma", False, ("company",)),
    ImportField("street", "Straße", False, ("strasse", "anschrift", "street")),
    ImportField("postal_code", "Postleitzahl", False, ("plz", "postal code")),
    ImportField("city", "Ort", False, ("stadt", "wohnort", "city")),
    ImportField("tax_number", "Steuernummer", False, ("st.-nr.", "tax number")),
    ImportField("vat_id", "USt-IdNr.", False, ("ust-id", "vat id")),
    ImportField("note", "Notiz", False, ("bemerkung", "note")),
    ImportField("active", "Aktiv", False, ("active",)),
)

LABELS = {import_field.key: import_field.label for import_field in IMPORT_FIELDS}

KIND_WORDS = {
    "fest": EmploymentKind.EMPLOYEE,
    "festangestellt": EmploymentKind.EMPLOYEE,
    "angestellt": EmploymentKind.EMPLOYEE,
    "mitarbeiter": EmploymentKind.EMPLOYEE,
    "aushilfe": EmploymentKind.TEMPORARY,
    "minijob": EmploymentKind.TEMPORARY,
    "frei": EmploymentKind.FREELANCER,
    "freelancer": EmploymentKind.FREELANCER,
    "freiberuflich": EmploymentKind.FREELANCER,
}

TEXT_FIELDS = ("email", "phone", "company", "street", "postal_code", "city", "tax_number", "vat_id", "note")


def split_name(text: str) -> tuple[str, str]:
    """``(first name, last name)`` of "Last, First" or "First Last"."""
    text = " ".join(text.split())
    if "," in text:
        last, first = (part.strip() for part in text.split(",", 1))
        return first, last
    if " " in text:
        first, last = text.rsplit(" ", 1)
        return first, last
    return "", text


FunctionRates = tuple[str, Decimal | None, Decimal | None]


def parse_function_rates(text: str) -> list[FunctionRates]:
    """``Tontechnik: 35,00/280,00; Licht`` → ``[("Tontechnik", 35.00, 280.00), ("Licht", None, None)]`` (PER-029).

    After the colon the hourly rate, after a slash the day rate; either may
    be left out: ``Licht: /250,00`` is a day rate only.

    Raises:
        ValueError: A rate is not a number.
    """

    def number(value: str) -> Decimal | None:
        value = value.strip()
        return parse_decimal(value, negative=_("A rate must not be negative.")) if value else None

    result = []
    for part in re.split(r"[,;\n]\s*(?=[^\d\s/])", text):
        part = part.strip()
        if not part:
            continue
        name, _colon, rates = part.partition(":")
        hourly, _slash, daily = rates.partition("/")
        result.append((name.strip(), number(hourly), number(daily)))
    return result


def parse_functions(text: str) -> list[tuple[str, Decimal | None]]:
    """``Tontechnik: 35,00; Licht`` → ``[("Tontechnik", 35.00), ("Licht", None)]`` – the hourly rates only.

    Raises:
        ValueError: A rate is not a number.
    """
    return [(name, hourly) for name, hourly, _daily in parse_function_rates(text)]


def import_people(
    table: Table,
    mapping: dict[str, int | None],
    *,
    dry_run: bool,
    rights: Any,
    actor: Any = "system:import",
    progress: Progress = no_progress,
) -> ImportReport:
    """Import people, or only report what the import would do (IMP-001).

    Returns:
        The report. If ``report.ok`` is false, nothing was written.
    """
    report = ImportReport(dry_run=dry_run, rows_read=len(table.rows))
    # IMP-011: the outcome of every row; rates only for those who may see personnel costs.
    report.log.rights = rights
    report.log.use_labels(cells_by_number(table), label_from(mapping, "name", "first_name", "last_name"))
    mapped = {key for key, index in mapping.items() if index is not None}
    if not mapped & {"name", "last_name"}:
        report.errors.append(
            ImportIssue(None, "", _("Assign a column to “Name” or to “Last name”; a person needs a name."))
        )
        return report

    with acting_as(actor), transaction.atomic():
        functions = {normalise(function.name): function for function in JobFunction.objects.all()}
        may_import_rates = rights.has(SpecialRight.PERSONNEL_COSTS)
        seen: dict[str, int] = {}
        for position, (number, row) in enumerate(table.numbered_rows()):
            if position % 50 == 0:
                progress(10 + 80 * position // max(len(table.rows), 1))
            _import_row(number, row, mapping, mapped, functions, may_import_rates, seen, report)
        if not report.errors and not dry_run:
            record_event(
                SystemSettings.load(),
                "import.records",
                {"kind": _("people"), "created": report.created, "updated": report.updated, "rows": report.rows_read},
            )
        if dry_run or report.errors:
            transaction.set_rollback(True)
    return report


def _find(first_name: str, last_name: str, email: str) -> Person | None:
    """The person a row means: by e-mail address, else by name if that is unique.

    Raises:
        ValueError: Several people have this name and no e-mail address tells them apart.
    """
    people = Person.objects.filter(anonymised_at__isnull=True)
    if email:
        found = people.filter(email__iexact=email).first()
        if found is not None:
            return found
    named = list(people.filter(first_name__iexact=first_name, last_name__iexact=last_name)[:2])
    if len(named) > 1:
        raise ValueError(
            _("There are several people named %(name)s; add the e-mail address to tell them apart.")
            % {"name": f"{first_name} {last_name}".strip()}
        )
    return named[0] if named else None


def _import_row(
    number: int,
    row: list[Any],
    mapping: dict[str, int | None],
    mapped: set[str],
    functions: dict[str, JobFunction],
    may_import_rates: bool,
    seen: dict[str, int],
    report: ImportReport,
) -> None:
    def cell(key: str) -> Any:
        index = mapping.get(key)
        return row[index] if index is not None and index < len(row) else None

    def problem(key: str, message: str) -> None:
        report.errors.append(ImportIssue(number, LABELS.get(key, ""), message))

    errors_before = len(report.errors)
    first_name, last_name = split_name(cell_text(cell("name"))) if "name" in mapped else ("", "")
    if "first_name" in mapped and cell_text(cell("first_name")):
        first_name = cell_text(cell("first_name"))
    if "last_name" in mapped and cell_text(cell("last_name")):
        last_name = cell_text(cell("last_name"))
    if not last_name:
        problem("last_name" if "last_name" in mapped else "name", _("The name is missing."))
        return
    email = cell_text(cell("email")).lower() if "email" in mapped else ""
    key = email or f"{first_name} {last_name}".lower()
    if key in seen:
        problem("name", _("This person already occurs in row %(row)s.") % {"row": seen[key]})
        return
    seen[key] = number
    try:
        person = _find(first_name, last_name, email)
    except ValueError as error:
        problem("name", str(error))
        return
    is_new = person is None
    if person is None:
        person = Person()
    before = _snapshot(person)
    person.first_name, person.last_name = first_name, last_name
    for field_key in TEXT_FIELDS:
        if field_key in mapped:
            setattr(person, field_key, cell_text(cell(field_key)))
    if "kind" in mapped and cell_text(cell("kind")):
        try:
            person.kind = choice_of(cell("kind"), KIND_WORDS, EmploymentKind.choices)
        except ValueError as error:
            problem("kind", str(error))
    if "active" in mapped:
        try:
            active = parse_bool(cell("active"))
        except ValueError as error:
            problem("active", str(error))
        else:
            if active is not None:
                person.is_active = active
    wanted: list[tuple[JobFunction, Decimal | None, Decimal | None]] = []
    if "functions" in mapped:
        try:
            for name, hourly, daily in parse_function_rates(cell_text(cell("functions"))):
                function = functions.get(normalise(name))
                if function is None:
                    problem("functions", _("There is no job function “%(name)s”.") % {"name": name})
                elif (hourly is not None or daily is not None) and not may_import_rates:
                    problem("functions", _("Importing hourly rates needs the right to see personnel costs."))
                else:
                    # PER-029: without rates the function is assigned all the same; the guide values count.
                    wanted.append((function, hourly, daily))
        except ValueError as error:
            problem("functions", str(error))
    if len(report.errors) > errors_before:
        return

    try:
        with transaction.atomic():
            after = _snapshot(person)
            changed = is_new or after != before
            if changed:
                save_person(person)
            assigned = _assign(person, wanted)
    except ValidationError as error:
        for message in messages_of(error):
            report.errors.append(ImportIssue(number, "", message))
        return
    label = f"{person.first_name} {person.last_name}".strip()
    if is_new:
        report.created += 1
        report.log.record(number, label, NEW)
    elif changed or assigned:
        report.updated += 1
        report.log.record(number, label, CHANGED)
        report.log.compare(number, Person, before, after)
        _log_functions(report.log, number, assigned)
    else:
        report.unchanged += 1
        report.log.record(number, label, UNCHANGED)


#: What :func:`_assign` changed: the person's functions before, and per function the rates before and after.
Assigned = list[tuple[list[str], JobFunction, PersonJobFunction | None, Decimal | None, Decimal | None]]


def _assign(person: Person, wanted: list[tuple[JobFunction, Decimal | None, Decimal | None]]) -> Assigned:
    """Give the person the functions of the row; what changed – empty if nothing did (PER-005, PER-029).

    A new function is assigned with the rates of the row, from always – or
    without own rates. A function the person has keeps its rates unless the
    row names others; those apply from today on, and a rate the row does
    not name is taken over from the rates that applied until then.

    Returns:
        IMP-011: per changed function the names of the person's
        functions before, the function, the rate row that applied until then
        (``None`` for a new function) and the new hourly and day rate.
    """
    changes: Assigned = []
    current_rows = current_rates(person) if person.pk else []
    names = [row.job_function.name for row in current_rows]
    applying = {row.job_function_id: row for row in current_rows}
    for function, hourly, daily in wanted:
        current = applying.get(function.pk)
        if current is None:
            set_rate(person, function, hourly, None, daily_rate=daily)
            new_hourly, new_daily = hourly, daily
        else:
            new_hourly = hourly if hourly is not None else current.hourly_rate
            new_daily = daily if daily is not None else current.daily_rate
            if (new_hourly, new_daily) == (current.hourly_rate, current.daily_rate):
                continue
            set_rate(person, function, new_hourly, timezone.localdate(), daily_rate=new_daily)
        changes.append((names, function, current, new_hourly, new_daily))
    return changes


def _log_functions(log: RowLog, row: int, assigned: Assigned) -> None:
    """IMP-011: note the new job functions and the new rates of a changed person.

    The functions are one change, "Licht" → "Licht, Tontechnik"; each rate
    that changes is one more, e.g. "Stundensatz (Tontechnik)". Rates are
    personnel costs: without that right only their names are shown.
    """
    if not assigned:
        return
    before = assigned[0][0]
    added = [function.name for _names, function, current, _hourly, _daily in assigned if current is None]
    if added:
        log.change(
            row,
            Person,
            "functions",
            ", ".join(before),
            ", ".join([*before, *added]),
            label=str(_("Job functions")),
        )
    for _names, function, current, hourly, daily in assigned:
        for name, old, new in (
            ("hourly_rate", current.hourly_rate if current else None, hourly),
            ("daily_rate", current.daily_rate if current else None, daily),
        ):
            if old != new:
                log.change(
                    row,
                    PersonJobFunction,
                    name,
                    old,
                    new,
                    key=f"{name}.{function.pk}",
                    label_format="%(field)s (" + function.name.replace("%", "%%") + ")",
                )


#: The fields of a person the import can change; IMP-011: compared for the preview.
SNAPSHOT_FIELDS = ("first_name", "last_name", "kind", *TEXT_FIELDS, "is_active")


def _snapshot(person: Person) -> dict[str, Any]:
    """The fields the import can change by name, to tell a change and to show it (IMP-011)."""
    return snapshot(person, SNAPSHOT_FIELDS)


def run_import(table: Table, mapping: dict[str, int | None], **options: Any) -> ImportReport:
    """The people import as registered in ``core.imports``."""
    return import_people(table, mapping, **options)


TITLE = gettext_lazy("Import people")
INTRODUCTION = gettext_lazy(
    "One row per person with a heading row. People are found by their e-mail address, or else by their name, "
    "and updated; the others are created. Job functions are listed separated by commas. Own rates follow a "
    "colon, the hourly rate and after a slash the day rate: “Tontechnik: 35,00/280,00, Licht”. Without rates "
    "the guide values of the job function count."
)
