# SPDX-License-Identifier: GPL-3.0-or-later
"""The people in the format of the people import (IMP-017; IMP-001, PER-005).

One row per person with the columns of ``personnel.importer.IMPORT_FIELDS``: the name as "Nachname,
Vorname" and in its two columns, the kind of employment by its German name, contact data, address, tax
number, VAT ID, note, active – and the job functions with the rates that apply today, as the import reads
them (PER-029): ``Licht: 28,00/250,00, Tontechnik: /280,00, Rigging``.

Rates are personnel costs: without the right to see them the column names the functions only, and
importing such a file leaves the rates as they are (PER-007, AUT-017). Anonymised people are left out –
the import would create them anew (NFA-009). Two queries per 2,000 people.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import SpecialRight
from rentalars.core.import_exports import ExportColumn, ImportFormatExport, amount, chunked, label
from rentalars.personnel.models import EmploymentKind, Person, PersonJobFunction
from rentalars.personnel.services import applicable_row

PERSON_VALUES = (
    "pk",
    "first_name",
    "last_name",
    "kind",
    "email",
    "phone",
    "company",
    "street",
    "postal_code",
    "city",
    "tax_number",
    "vat_id",
    "note",
    "is_active",
)


def _function_text(row: PersonJobFunction, *, with_rates: bool) -> str:
    """``Licht: 28,00/250,00`` – the hourly rate after the colon, the day rate after a slash (PER-029)."""
    name = row.job_function.name
    if not with_rates or (row.hourly_rate is None and row.daily_rate is None):
        return name
    daily = f"/{amount(row.daily_rate)}" if row.daily_rate is not None else ""
    return f"{name}: {amount(row.hourly_rate) or ''}{daily}"


def _chunks(rights: Any) -> Iterator[list[dict[str, Any]]]:
    """The people by name, each with its job functions and – with the right – the rates of today."""
    with_rates = rights.has(SpecialRight.PERSONNEL_COSTS)
    today = timezone.localdate()
    people = (
        Person.objects.filter(anonymised_at__isnull=True)
        .order_by("last_name", "first_name", "pk")
        .values(*PERSON_VALUES)
    )
    for chunk in chunked(people.iterator(chunk_size=2000)):
        rows: dict[int, dict[int, list[PersonJobFunction]]] = {}
        for rate in PersonJobFunction.objects.filter(person_id__in=[row["pk"] for row in chunk]).select_related(
            "job_function"
        ):
            rows.setdefault(rate.person_id, {}).setdefault(rate.job_function_id, []).append(rate)
        for row in chunk:
            applying = [applicable_row(history, today) for history in rows.get(row["pk"], {}).values()]
            current = sorted((rate for rate in applying if rate is not None), key=lambda r: r.job_function.name.lower())
            row["functions"] = ", ".join(_function_text(rate, with_rates=with_rates) for rate in current)
        yield chunk


def _name(row: dict[str, Any]) -> str:
    """The name as "Nachname, Vorname", as the list of people shows it; the last name alone without a first name."""
    return f"{row['last_name']}, {row['first_name']}" if row["first_name"] else row["last_name"]


EXPORT = ImportFormatExport(
    key="people",
    name=_("People"),
    columns=(
        ExportColumn("name", _name),
        ExportColumn("first_name", lambda row: row["first_name"]),
        ExportColumn("last_name", lambda row: row["last_name"]),
        ExportColumn("kind", lambda row: label(EmploymentKind, row["kind"])),
        ExportColumn("functions", lambda row: row["functions"]),
        ExportColumn("email", lambda row: row["email"]),
        ExportColumn("phone", lambda row: row["phone"]),
        ExportColumn("company", lambda row: row["company"]),
        ExportColumn("street", lambda row: row["street"]),
        ExportColumn("postal_code", lambda row: row["postal_code"]),
        ExportColumn("city", lambda row: row["city"]),
        ExportColumn("tax_number", lambda row: row["tax_number"]),
        ExportColumn("vat_id", lambda row: row["vat_id"]),
        ExportColumn("note", lambda row: row["note"]),
        ExportColumn("active", lambda row: row["is_active"]),
    ),
    chunks=_chunks,
)
