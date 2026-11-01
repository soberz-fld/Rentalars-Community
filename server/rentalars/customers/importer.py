# SPDX-License-Identifier: GPL-3.0-or-later
"""Import of customers from a spreadsheet (IMP-001, IMP-003, IMP-004, IMP-013).

One row per customer. Lists exported from the customer list come back
unchanged, and so do contact exports of bookkeeping programs such as Lexware
(IMP-013): their headings – "Firmenname", "Straße 1", "Ansprechpartner 1
Vorname" and so on – are recognised, and the file may be in Windows-1252
(``core.tabular.decode_text``).

Merging instead of duplicating (IMP-013)
----------------------------------------
Each row looks for the customer it describes, in this order:

1. the **customer number** (IMP-004);
2. the **VAT ID**;
3. the **e-mail address** of the customer or of one of its contacts;
4. the **name**, compared without case, punctuation, legal form and with
   umlauts spelt out: "Müller GmbH" is "MUELLER gmbh". A private person is
   not taken for a company with a legal form in its name or vice versa.

A step that finds several customers narrows them down with the later steps;
if that leaves more than one, the row becomes a new customer and the dry run
says which customers came into question. A customer is found by at most one
row of a file – a second row that looks like it becomes a new customer with
a note, because two rows of one list are two records there.

A customer that is found is updated, never emptied: an empty cell keeps
what Rentalars has. Contacts are added unless one with the same name or
e-mail address exists, which is then completed; a delivery address is added
unless the customer has one with the same street, postal code and city. If a
customer found by its VAT ID, e-mail or name has a different number in the
file, it keeps its number in Rentalars; the report says so. A row without a
match becomes a new customer, with the number of the file if Rentalars does
not know it yet, otherwise with the next number of the number range
(KND-003).

The report names the outcome of every row: new, merged with which customer
and how it was found, or unchanged. The standard discount is only imported
with the right to see prices.

IMP-011: a merged row also lists every field it changes, old → new,
and a row the import cannot take is listed with its errors.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, pgettext

from rentalars.accounts.rights import SpecialRight
from rentalars.core.audit import acting_as, record_event
from rentalars.core.import_rows import CHANGED, ERROR, NEW, UNCHANGED, cells_by_number, label_from, snapshot
from rentalars.core.models import SystemSettings
from rentalars.core.tabular import (
    ImportField,
    ImportIssue,
    ImportReport,
    Progress,
    Table,
    cell_text,
    choice_of,
    fold,
    messages_of,
    no_progress,
    normalise,
    parse_bool,
    parse_decimal,
)
from rentalars.customers.models import AddressKind, Contact, Customer, CustomerAddress, CustomerKind
from rentalars.customers.names import join_name, tidy
from rentalars.customers.services import find_duplicates, normalised_name, save_customer


def _contact_fields(number: int) -> tuple[ImportField, ...]:
    """The columns of a further contact person, as Lexware names them ("Ansprechpartner 1 Vorname")."""
    heading = f"Ansprechpartner {number}"
    return (
        ImportField(f"contact{number}_name", heading, False, (f"ansprechperson {number}",)),
        ImportField(f"contact{number}_salutation", f"{heading} Anrede", False),
        ImportField(f"contact{number}_first_name", f"{heading} Vorname", False),
        ImportField(f"contact{number}_last_name", f"{heading} Nachname", False),
        ImportField(f"contact{number}_email", f"{heading} E-Mail", False, (f"ansprechpartner {number} email",)),
        ImportField(f"contact{number}_phone", f"{heading} Telefon", False),
    )


IMPORT_FIELDS: tuple[ImportField, ...] = (
    ImportField("number", "Nummer", False, ("kundennummer", "kunden-nr.", "kd.-nr.", "number")),
    # IMP-013: without a company name, first and last name make the name of a private person.
    ImportField("name", "Name", False, ("firmenname", "firma", "kunde", "name oder firma", "name")),
    ImportField("first_name", "Vorname", False, ("first name",)),
    ImportField("last_name", "Nachname", False, ("familienname", "last name")),
    ImportField("salutation", "Anrede", False, ("salutation",)),
    ImportField("kind", "Art", False, ("kundenart", "kind")),
    ImportField("name_addition", "Zusatz", False, ("adresszusatz 1", "adresszusatz", "namenszusatz", "abteilung")),
    ImportField(
        "street", "Straße", False, ("straße 1", "strasse 1", "strasse", "straße und hausnummer", "anschrift", "street")
    ),
    ImportField("postal_code", "Postleitzahl", False, ("plz 1", "plz", "postal code")),
    ImportField("city", "Ort", False, ("ort 1", "stadt", "city")),
    ImportField("country", "Land", False, ("land 1", "country")),
    # IMP-013: address 2 of Lexware is the delivery address (KND-005).
    ImportField("delivery_name_addition", "Lieferadresse Zusatz", False, ("adresszusatz 2",)),
    ImportField("delivery_street", "Lieferadresse Straße", False, ("straße 2", "strasse 2", "lieferadresse strasse")),
    ImportField("delivery_postal_code", "Lieferadresse Postleitzahl", False, ("plz 2", "lieferadresse plz")),
    ImportField("delivery_city", "Lieferadresse Ort", False, ("ort 2",)),
    ImportField("delivery_country", "Lieferadresse Land", False, ("land 2",)),
    ImportField("email", "E-Mail", False, ("e-mail 1", "email 1", "e-mail-adresse", "mail", "email")),
    ImportField("email_2", "E-Mail 2", False, ("email 2",)),
    ImportField("phone", "Telefon", False, ("telefon 1", "tel.", "telefonnummer", "phone")),
    ImportField("phone_2", "Telefon 2", False, ("tel. 2",)),
    ImportField(
        "vat_id",
        "USt-IdNr.",
        False,
        ("ust-id", "ustid", "umsatzsteuer-id", "umsatzsteuer id", "ust-idnr", "vat id"),
    ),
    ImportField("tax_number", "Steuernummer", False, ("steuer-nr.", "st.-nr.", "tax number")),
    ImportField("payment_terms_days", "Zahlungsziel (Tage)", False, ("zahlungsziel", "payment terms (days)")),
    ImportField("default_discount_percent", "Standardrabatt %", False, ("rabatt", "standardrabatt")),
    ImportField("note", "Notiz", False, ("bemerkung", "note")),
    # "Kontakt" is the contact person in Lexware; the customer list exports its e-mail and phone
    # under the same heading, which :func:`_is_person_name` tells apart.
    ImportField(
        "contact_name", "Ansprechperson", False, ("kontakt", "ansprechpartner", "ansprechpartnerin", "kontaktperson")
    ),
    # KND-004: the contact person's name in two columns; "Ansprechperson" alone holds the whole name.
    ImportField("contact_first_name", "Ansprechperson Vorname", False, ("ansprechpartner vorname", "kontakt vorname")),
    ImportField(
        "contact_last_name", "Ansprechperson Nachname", False, ("ansprechpartner nachname", "kontakt nachname")
    ),
    ImportField("contact_email", "E-Mail der Ansprechperson", False, ("e-mail ansprechpartner",)),
    ImportField("contact_phone", "Telefon der Ansprechperson", False, ("telefon ansprechpartner",)),
    *_contact_fields(1),
    *_contact_fields(2),
    ImportField("active", "Aktiv", False, ("active",)),
)

LABELS = {import_field.key: import_field.label for import_field in IMPORT_FIELDS}

KIND_WORDS = {
    "firma": CustomerKind.COMPANY,
    "unternehmen": CustomerKind.COMPANY,
    "organisation": CustomerKind.COMPANY,
    "privat": CustomerKind.PRIVATE,
}

TEXT_FIELDS = (
    "name_addition",
    "street",
    "postal_code",
    "city",
    "country",
    "email",
    "phone",
    "vat_id",
    "tax_number",
    "note",
)

#: Columns some programs export that have no place in Rentalars; the report says they were left out.
IGNORED_HEADINGS = ("Lieferantennummer",)

#: Salutations that do not belong to a person.
_NO_SALUTATION = frozenset({"firma", "company", "unternehmen"})

#: Legal forms that mark a name as the name of a company.
_LEGAL_FORM = re.compile(r"\b(gmbh|mbh|ag|kg|kgaa|ohg|gbr|ug|e v|e k|eg|se|inc|ltd|llc|plc|sarl|bv|nv)\b")


class FoundBy:
    """How a row found the customer it describes (IMP-013)."""

    NUMBER = "number"
    VAT_ID = "vat_id"
    EMAIL = "email"
    NAME = "name"


def found_by_text(criterion: str) -> str:
    """The criterion as it is completed in "found by …"."""
    return {
        FoundBy.NUMBER: _("the customer number"),
        FoundBy.VAT_ID: _("the VAT ID"),
        FoundBy.EMAIL: _("the e-mail address"),
        FoundBy.NAME: _("the name"),
    }[criterion]


@dataclass
class RowOutcome:
    """What the import did with one row (IMP-013)."""

    row: int
    name: str
    #: ``created``, ``merged`` or ``unchanged``.
    outcome: str
    customer: str = ""
    #: The name the customer had before, if it was found.
    previous_name: str = ""
    found_by: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        """The outcome in words, e.g. "merged with 10042 „Kulturverein“ (found by the e-mail address)"."""
        if self.outcome == "created":
            return pgettext("import row", "new")
        if self.outcome == "unchanged":
            return pgettext("import row", "unchanged")
        return _("merged with %(number)s “%(name)s” (found by %(criterion)s)") % {
            "number": self.customer,
            "name": self.previous_name,
            "criterion": found_by_text(self.found_by),
        }

    def as_dict(self) -> dict[str, Any]:
        """The outcome as plain data, for the API and for background tasks."""
        return {
            "row": self.row,
            "name": self.name,
            "outcome": self.outcome,
            "customer": self.customer,
            "found_by": self.found_by,
            "text": self.text,
            "notes": self.notes,
        }


@dataclass
class CustomerImportReport(ImportReport):
    """The report of the customer import, with the outcome of every row (IMP-013)."""

    rows: list[RowOutcome] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """The report as plain data; ``rows`` holds one entry per row of the file.

        IMP-011: besides what the customer import named before –
        ``name``, ``outcome``, ``customer``, ``found_by``, ``text`` – every
        row has the keys of all imports (``core.import_rows``): ``label``,
        ``status``, ``changes``, ``notes``, ``errors``. A row with an error
        has the ``outcome`` "error".
        """
        data = super().as_dict()
        outcomes = {outcome.row: outcome for outcome in self.rows}
        rows = []
        for entry in data["rows"]:
            outcome = outcomes.get(entry["row"])
            if outcome is not None and entry["status"] != ERROR:
                rows.append({**outcome.as_dict(), **entry})
            else:
                error = {"name": entry["label"], "outcome": ERROR, "customer": "", "found_by": "", "text": ""}
                rows.append({**error, **entry})
        data["rows"] = rows
        return data


@dataclass
class ContactData:
    """A contact person as one row of the file describes it.

    KND-004: ``first_name`` and ``last_name`` as the file gives them; a file with one name column leaves
    them empty and the name is split by :func:`~rentalars.customers.names.split_name` when the contact is saved.
    """

    name: str
    salutation: str = ""
    email: str = ""
    phone: str = ""
    position: str = ""
    first_name: str = ""
    last_name: str = ""

    @classmethod
    def of(cls, first_name: str, last_name: str, whole: str = "", *, hint: str = "", **others: str) -> ContactData:
        """A contact from the name columns: first and last name if the file has them, else the whole name.

        Only one of the two given: the other is read from the whole name where that has more words ("Anna Berg" in
        the name column and "Berg" as last name: the first name is Anna; ``hint`` is another text that may hold the
        whole name, such as the heading of "Ansprechpartner 1"). A first name alone is the name of the person, so it
        becomes the last name ("Anna" is a contact "Anna", as) – a contact needs a last name.
        """
        if last_name or first_name:
            if not (first_name and last_name):
                first_name, last_name = _complete_parts(first_name, last_name, whole, hint)
            if first_name and not last_name:
                first_name, last_name = "", first_name
            return cls(join_name(first_name, last_name), first_name=first_name, last_name=last_name, **others)
        return cls(whole, **others)


def _complete_parts(first_name: str, last_name: str, *wholes: str) -> tuple[str, str]:
    """The missing one of first and last name, taken from a whole name that contains the given one.

    ``("", "Berg")`` with "Anna Berg" is ("Anna", "Berg"); ``("Anna", "")`` with "Anna Berg" is ("Anna", "Berg").
    Wholes that do not end (or start) with the given part leave the names as they are.
    """
    for whole in wholes:
        words = tidy(whole).split()
        if len(words) < 2:
            continue
        if last_name and not first_name:
            size = len(last_name.split())
            if size < len(words) and fold(" ".join(words[-size:])) == fold(last_name):
                return " ".join(words[:-size]), tidy(last_name)
        elif first_name and not last_name:
            size = len(first_name.split())
            if size < len(words) and fold(" ".join(words[:size])) == fold(first_name):
                return tidy(first_name), " ".join(words[size:])
    return first_name, last_name


@dataclass
class _Match:
    """The customer a row describes, how it was found, and who else came into question."""

    customer: Customer | None = None
    found_by: str = ""
    ambiguous: list[Customer] = field(default_factory=list)


class _Run:
    """The state of one import: rows seen, customers already found, the name index."""

    def __init__(self) -> None:
        #: Customer numbers of the file → the row they first occur in.
        self.numbers: dict[str, int] = {}
        #: Customers a row has found or created → that row; no second row merges into them.
        self.claimed: dict[int, int] = {}
        self._names: dict[str, list[int]] | None = None

    def names(self) -> dict[str, list[int]]:
        """Customers by :func:`name_key`, read once per import."""
        if self._names is None:
            self._names = {}
            for pk, name in Customer.objects.filter(anonymised_at__isnull=True).values_list("pk", "name"):
                key = name_key(name)
                if key:
                    self._names.setdefault(key, []).append(pk)
        return self._names


# --- Comparing ---------------------------------------------------------------------------------


def name_key(name: str) -> str:
    """The key two names of the same customer share (IMP-013).

    Case, spacing, punctuation, legal forms and the spelling of umlauts do
    not count: "Müller GmbH", "Mueller  GmbH" and "MÜLLER" all give
    ``mueller``. Keys shorter than three letters are not used for matching.
    """
    key = fold(normalised_name(name))
    return key if len(key.replace(" ", "")) >= 3 else ""


def has_legal_form(name: str) -> bool:
    """Whether a name carries a legal form such as GmbH, AG or e. V."""
    return bool(_LEGAL_FORM.search(re.sub(r"[.\s&,]+", " ", fold(name))))


def _kinds_compatible(row_kind: str | None, row_name: str, customer: Customer) -> bool:
    """A private person is not taken for a company with a legal form in its name, nor the other way round."""
    if not row_kind or row_kind == customer.kind:
        return True
    return not (has_legal_form(row_name) or has_legal_form(customer.name))


def _is_person_name(text: str) -> bool:
    """Whether a cell can be the name of a contact – not an e-mail address or a phone number."""
    return bool(text) and "@" not in text and any(char.isalpha() for char in text)


def _street_key(street: str) -> str:
    """A street without the difference between "Str." and "Straße", case and spacing."""
    text = fold(street).replace("strasse", "str").replace("str.", "str")
    return re.sub(r"[^a-z0-9]", "", text)


def address_key(street: str, postal_code: str, city: str) -> str:
    """Street, postal code and city as one key; two addresses with the same key are the same (IMP-013)."""
    return "|".join((_street_key(street), re.sub(r"\s", "", postal_code), re.sub(r"[^a-z0-9]", "", fold(city))))


def same_address(first: tuple[str, str, str], second: tuple[str, str, str]) -> bool:
    """Whether two addresses (street, postal code, city) are the same (IMP-013).

    "Hauptstr. 5" is "Hauptstraße 5"; a postal code missing on one side
    does not make a difference – the import fills it in.
    """
    street, postal_code, city = address_key(*first).split("|")
    other_street, other_postal_code, other_city = address_key(*second).split("|")
    if not (street and city) or (street, city) != (other_street, other_city):
        return False
    return not (postal_code and other_postal_code) or postal_code == other_postal_code


def _same_spelling(name: str, other: str) -> bool:
    """Whether two names differ only in case, spacing, punctuation and the spelling of umlauts."""
    return re.sub(r"[^a-z0-9]", "", fold(name)) == re.sub(r"[^a-z0-9]", "", fold(other))


# --- The import ------------------------------------------------------------------------------


def import_customers(
    table: Table,
    mapping: dict[str, int | None],
    *,
    dry_run: bool,
    rights: Any,
    actor: Any = "system:import",
    progress: Progress = no_progress,
) -> CustomerImportReport:
    """Import customers, or only report what the import would do (IMP-001, IMP-013).

    Args:
        table: The rows of the file.
        mapping: Which column feeds which field (``core.tabular.resolve_mapping``).
        dry_run: Do everything, report it, and write nothing.
        rights: The rights of the caller; the standard discount needs the price right.
        actor: Who is named in the change log.
        progress: Told the percentage done, for imports in the background.

    Returns:
        The report. If ``report.ok`` is false, nothing was written.
    """
    report = CustomerImportReport(dry_run=dry_run, rows_read=len(table.rows))
    # IMP-011: the outcome of every row; the discount only for those who may see prices.
    report.log.rights = rights
    report.log.use_labels(cells_by_number(table), label_from(mapping, "number", "name", "first_name", "last_name"))
    mapped = {key for key, index in mapping.items() if index is not None}
    if not mapped & {"name", "first_name", "last_name"}:
        report.errors.append(
            ImportIssue(None, LABELS["name"], _("No column of the file is assigned to this required field."))
        )
    if "default_discount_percent" in mapped and not rights.has(SpecialRight.PRICES):
        report.errors.append(ImportIssue(None, "", _("Importing discounts needs the right to see prices.")))
    if report.errors:
        return report
    headings = {normalise(heading) for heading in table.headers}
    for ignored in IGNORED_HEADINGS:
        if normalise(ignored) in headings:
            report.notes.append(_("The column “%(column)s” is not imported.") % {"column": ignored})

    with acting_as(actor), transaction.atomic():
        run = _Run()
        for position, (number, row) in enumerate(table.numbered_rows()):
            if position % 50 == 0:
                progress(10 + 80 * position // max(len(table.rows), 1))
            _import_row(number, row, mapping, mapped, run, report)
        if not report.errors and not dry_run:
            record_event(
                SystemSettings.load(),
                "import.records",
                {
                    "kind": _("customers"),
                    "created": report.created,
                    "updated": report.updated,
                    "rows": report.rows_read,
                },
            )
        if dry_run or report.errors:
            transaction.set_rollback(True)
    return report


def _row_name(cell: Any, mapped: set[str]) -> tuple[str, str | None]:
    """The name of the customer in a row and the kind it suggests.

    A company name wins. Without one, first and last name make the name of a
    private person (IMP-013).
    """
    company = cell_text(cell("name"))
    person = " ".join(part for part in (cell_text(cell("first_name")), cell_text(cell("last_name"))) if part)
    if company:
        has_person_columns = bool(mapped & {"first_name", "last_name"})
        return company, CustomerKind.COMPANY if has_person_columns else None
    if person:
        return person, CustomerKind.PRIVATE
    return "", None


def _import_row(
    number: int,
    row: list[Any],
    mapping: dict[str, int | None],
    mapped: set[str],
    run: _Run,
    report: CustomerImportReport,
) -> None:
    def cell(key: str) -> Any:
        index = mapping.get(key)
        return row[index] if index is not None and index < len(row) else None

    def problem(key: str, message: str) -> None:
        report.errors.append(ImportIssue(number, LABELS.get(key, ""), message))

    errors_before = len(report.errors)
    customer_number = cell_text(cell("number"))
    if customer_number:
        if customer_number in run.numbers:
            problem(
                "number",
                _("The number %(number)s already occurs in row %(row)s.")
                % {"number": customer_number, "row": run.numbers[customer_number]},
            )
            return
        run.numbers[customer_number] = number
    name, derived_kind = _row_name(cell, mapped)
    if not name:
        problem("name", _("The name is missing."))
        return
    explicit_kind = None
    if "kind" in mapped and cell_text(cell("kind")):
        try:
            explicit_kind = choice_of(cell("kind"), KIND_WORDS, CustomerKind.choices)
        except ValueError as error:
            problem("kind", str(error))
            return
    row_kind = explicit_kind or derived_kind
    vat_id = "".join(cell_text(cell("vat_id")).split()).upper()
    email = cell_text(cell("email"))

    match = _find(customer_number, name, row_kind, vat_id, email, run)
    customer = match.customer
    if customer is not None and match.found_by == FoundBy.NUMBER:
        if customer.is_anonymised:
            problem("number", _("Customer %(number)s is anonymised and is not changed.") % {"number": customer_number})
            return
        if customer.pk in run.claimed:
            problem(
                "number",
                _("Customer %(number)s was already merged with row %(row)s.")
                % {"number": customer_number, "row": run.claimed[customer.pk]},
            )
            return
        if not _plausible(customer, name, vat_id, email):
            # Numbers of another program (Lexware counts from 10001 as well) can meet a different customer.
            report.warnings.append(
                ImportIssue(
                    number,
                    LABELS["number"],
                    _(
                        "In Rentalars, %(number)s is “%(name)s” and has nothing else in common with this row. "
                        "If the numbers of the file come from another program, do not import their column."
                    )
                    % {"number": customer.number, "name": customer.name},
                )
            )
    outcome = RowOutcome(number, name, "created")
    is_new = customer is None
    if customer is None:
        # A number Rentalars does not know yet is taken over (IMP-004).
        customer = Customer(number=customer_number, kind=row_kind or CustomerKind.COMPANY)
    else:
        outcome.customer, outcome.previous_name, outcome.found_by = customer.number, customer.name, match.found_by
        if customer_number and customer_number != customer.number:
            outcome.notes.append(
                _("The file has the number %(file)s; the customer keeps its number %(number)s.")
                % {"file": customer_number, "number": customer.number}
            )
        if explicit_kind:
            customer.kind = explicit_kind
    before = _snapshot(customer)
    old_main = (customer.name_addition, customer.street, customer.postal_code, customer.city, customer.country)

    if is_new or not _same_spelling(customer.name, name):
        # "MÜLLER Bühnentechnik" stays as it is against "Mueller Buehnentechnik"; "Musterstadt GmbH" is news.
        customer.name = name
    # IMP-013: an empty cell never erases what Rentalars knows.
    for key in TEXT_FIELDS:
        value = cell_text(cell(key)) if key in mapped else ""
        if key == "vat_id":
            value = vat_id
        if value:
            setattr(customer, key, value)
    if "payment_terms_days" in mapped:
        text = cell_text(cell("payment_terms_days"))
        if text and not text.isdigit():
            problem("payment_terms_days", _("“%(value)s” is not a whole number.") % {"value": text})
        elif text:
            customer.payment_terms_days = int(text)
    if "default_discount_percent" in mapped:
        try:
            discount = parse_decimal(cell("default_discount_percent"), negative=_("A discount must not be negative."))
        except ValueError as error:
            problem("default_discount_percent", str(error))
        else:
            if discount is not None:
                customer.default_discount_percent = discount
    if "active" in mapped:
        try:
            active = parse_bool(cell("active"))
        except ValueError as error:
            problem("active", str(error))
        else:
            if active is not None:
                customer.is_active = active
    if len(report.errors) > errors_before:
        return

    contacts = _row_contacts(cell, mapped, name, has_company=bool(cell_text(cell("name"))))
    _note_second_ways(customer, cell, mapped, contacts)
    if is_new:
        _warn_about_duplicates(number, customer, match, report)
    try:
        with transaction.atomic():
            changed = is_new or _snapshot(customer) != before
            if changed:
                save_customer(customer)
            run.claimed[customer.pk] = number
            if not is_new and _keep_old_main_address(customer, old_main):
                changed = True
                outcome.notes.append(_("The previous address stays as a further billing address."))
            for contact in contacts:
                result = _merge_contact(customer, contact)
                if result:
                    changed = True
                    outcome.notes.append(result)
            delivery = _merge_delivery_address(customer, cell, mapped)
            if delivery:
                changed = True
                outcome.notes.append(delivery)
    except ValidationError as error:
        for message in messages_of(error, _field_labels()):
            report.errors.append(ImportIssue(number, "", message))
        return
    label = f"{customer.number} {name}".strip()
    if is_new:
        outcome.customer = customer.number
        report.created += 1
        report.log.record(number, label, NEW, outcome.notes)
    elif changed:
        outcome.outcome = "merged"
        report.updated += 1
        # IMP-011: what the merge changes in the customer itself, besides contacts and addresses.
        report.log.record(number, label, CHANGED, outcome.notes)
        report.log.compare(number, Customer, before, _snapshot(customer))
    else:
        outcome.outcome = "unchanged"
        report.unchanged += 1
        report.log.record(number, label, UNCHANGED, outcome.notes)
    report.rows.append(outcome)


def _find(number: str, name: str, kind: str | None, vat_id: str, email: str, run: _Run) -> _Match:
    """Find the customer a row describes: by number, VAT ID, e-mail address or name (IMP-013).

    A step that finds several customers is narrowed down by the later ones;
    if more than one is left, the row matches nobody and the candidates are
    returned for a note.
    """
    if number:
        customer = Customer.objects.filter(number=number).first()
        if customer is not None:
            return _Match(customer, FoundBy.NUMBER)
    available = Customer.objects.filter(anonymised_at__isnull=True).exclude(pk__in=list(run.claimed))
    key = name_key(name)
    email = email.strip().lower()

    # The e-mail address of a contact person counts for companies only: a private person whose
    # address belongs to a contact of a company works there, but is not that company.
    with_contacts = kind != CustomerKind.PRIVATE
    email_condition = Q(email__iexact=email)
    if with_contacts:
        email_condition |= Q(contacts__email__iexact=email)

    def by_email(candidates: list[Customer]) -> list[Customer]:
        return [
            candidate
            for candidate in candidates
            if candidate.email.lower() == email
            or (with_contacts and any(contact.email.lower() == email for contact in candidate.contacts.all()))
        ]

    def by_name(candidates: list[Customer]) -> list[Customer]:
        return [
            candidate
            for candidate in candidates
            if name_key(candidate.name) == key and _kinds_compatible(kind, name, candidate)
        ]

    steps: list[tuple[str, Any]] = []
    if vat_id:
        steps.append((FoundBy.VAT_ID, lambda: list(available.filter(vat_id=vat_id))))
    if email:
        steps.append(
            (
                FoundBy.EMAIL,
                lambda: list(available.filter(email_condition).distinct()),
            )
        )
    if key:
        steps.append(
            (
                FoundBy.NAME,
                lambda: by_name(list(available.filter(pk__in=run.names().get(key, [])))),
            )
        )
    narrowing = {FoundBy.EMAIL: by_email if email else None, FoundBy.NAME: by_name if key else None}
    for position, (criterion, fetch) in enumerate(steps):
        candidates = list({candidate.pk: candidate for candidate in fetch()}.values())
        if not candidates:
            continue
        for later, _fetch in steps[position + 1 :]:
            if len(candidates) == 1:
                break
            narrow = narrowing.get(later)
            narrowed = narrow(candidates) if narrow else []
            if narrowed:
                candidates = narrowed
        if len(candidates) == 1:
            return _Match(candidates[0], criterion)
        return _Match(ambiguous=sorted(candidates, key=lambda candidate: candidate.number))
    return _Match()


def _plausible(customer: Customer, name: str, vat_id: str, email: str) -> bool:
    """Whether a customer found by its number shares anything else with the row: name, VAT ID or e-mail."""
    if (vat_id and customer.vat_id == vat_id) or (email and customer.email.lower() == email.strip().lower()):
        return True
    words = {word for word in name_key(name).split() if len(word) >= 4}
    return bool(words & set(name_key(customer.name).split())) or name_key(name) == name_key(customer.name)


def _warn_about_duplicates(number: int, customer: Customer, match: _Match, report: ImportReport) -> None:
    """Note customers a new one may be the same as (KND-008), or which several fitted (IMP-013)."""
    if match.ambiguous:
        report.warnings.append(
            ImportIssue(
                number,
                "",
                _(
                    "Several customers fit (%(numbers)s), so a new customer is created. Put the customer number "
                    "into the file to merge the row with one of them."
                )
                % {"numbers": ", ".join(candidate.number for candidate in match.ambiguous)},
            )
        )
        return
    for duplicate in find_duplicates(customer.name, customer.email)[:1]:
        report.warnings.append(
            ImportIssue(
                number,
                "",
                _("May be the same as %(number)s %(name)s (%(reason)s).")
                % {
                    "number": duplicate.customer.number,
                    "name": duplicate.customer.name,
                    "reason": duplicate.reason,
                },
            )
        )


# --- Contacts, second ways to reach, addresses (IMP-013) ---------------------------------------


def _row_contacts(cell: Any, mapped: set[str], customer_name: str, *, has_company: bool) -> list[ContactData]:
    """The contact persons a row describes.

    The first is the "Ansprechperson" (Lexware: "Kontakt"); in a row of a
    company, first and last name without one name the contact person, and
    the salutation belongs to it. Then come "Ansprechpartner 1" and "2".
    """
    contacts: list[ContactData] = []
    main = cell_text(cell("contact_name")) if "contact_name" in mapped else ""
    if not _is_person_name(main):
        main = ""
    # KND-004: "Ansprechperson Vorname" and "Nachname" give the parts; a company row's own first and last
    # name do so too, when the contact has no columns of its own.
    main_first = cell_text(cell("contact_first_name")) if "contact_first_name" in mapped else ""
    main_last = cell_text(cell("contact_last_name")) if "contact_last_name" in mapped else ""
    if not (main_first or main_last) and not main and has_company:
        main_first, main_last = cell_text(cell("first_name")), cell_text(cell("last_name"))
    if main_first or main_last or main:
        data = ContactData.of(
            main_first,
            main_last,
            main,
            salutation=_salutation(cell("salutation")) if has_company else "",
            email=cell_text(cell("contact_email")),
            phone=cell_text(cell("contact_phone")),
        )
        if data.name and not _same_spelling(data.name, customer_name):
            contacts.append(data)
    for number in (1, 2):
        prefix = f"contact{number}_"
        first, last = cell_text(cell(prefix + "first_name")), cell_text(cell(prefix + "last_name"))
        composed = join_name(first, last)
        heading = cell_text(cell(prefix + "name"))
        name = composed or (heading if _is_person_name(heading) else "")
        if not name:
            continue
        position = ""
        if composed and heading and not set(fold(composed).split()) <= set(fold(heading).split()):
            # A text that is not the name itself – "Buchhaltung", say – describes the role.
            position = heading
        contacts.append(
            ContactData.of(
                first,
                last,
                name,
                hint=heading if _is_person_name(heading) else "",
                salutation=_salutation(cell(prefix + "salutation")),
                email=cell_text(cell(prefix + "email")),
                phone=cell_text(cell(prefix + "phone")),
                position=position,
            )
        )
    return contacts


def _salutation(value: Any) -> str:
    text = cell_text(value)
    return "" if fold(text) in _NO_SALUTATION else text


def _note_second_ways(customer: Customer, cell: Any, mapped: set[str], contacts: list[ContactData]) -> None:
    """Keep "E-Mail 2" and "Telefon 2" in the note, unless the customer has them already (IMP-013).

    A customer has one e-mail address and one phone number; the second ones
    of the file go into the note, once.
    """
    known = [customer.email, customer.phone, customer.note]
    known += [value for contact in contacts for value in (contact.email, contact.phone)]
    if customer.pk:
        known += [value for contact in customer.contacts.all() for value in (contact.email, contact.phone)]
    known_text = "\n".join(known).casefold()
    lines = []
    for key, template in (
        ("email_2", _("Second e-mail: %(value)s")),
        ("phone_2", _("Second phone: %(value)s")),
    ):
        value = cell_text(cell(key)) if key in mapped else ""
        if value and value.casefold() not in known_text:
            lines.append(template % {"value": value})
    if lines:
        customer.note = "\n".join(part for part in (customer.note.rstrip(), *lines) if part)


def _merge_contact(customer: Customer, data: ContactData) -> str:
    """Add a contact or complete the one with the same name or e-mail address; a note what happened, or ""."""
    existing = next(
        (
            contact
            for contact in customer.contacts.all()
            if _same_spelling(contact.name, data.name) or (data.email and contact.email.lower() == data.email.lower())
        ),
        None,
    )
    if existing is None:
        contact = Contact(
            customer=customer,
            name=data.name,
            first_name=data.first_name,
            last_name=data.last_name,
            salutation=data.salutation,
            email=data.email,
            phone=data.phone,
            position=data.position,
        )
        contact.full_clean()
        contact.save()
        return _("contact %(name)s added") % {"name": data.name}
    changed = False
    for name in ("salutation", "email", "phone", "position"):
        value = getattr(data, name)
        if value and getattr(existing, name) != value:
            setattr(existing, name, value)
            changed = True
    # KND-004: a first name the file knows completes a contact without one – never replaces a name.
    if (
        data.first_name
        and not existing.first_name
        and data.last_name
        and fold(data.last_name) == fold(existing.last_name)
    ):
        existing.first_name = data.first_name
        changed = True
    if not changed:
        return ""
    existing.full_clean()
    existing.save()
    return _("contact %(name)s completed") % {"name": existing.name}


def _keep_old_main_address(customer: Customer, old: tuple[str, str, str, str, str]) -> bool:
    """When the file moves a customer to another street or city, keep the old address (IMP-013).

    A corrected postal code is a correction, not a move, and replaces the old one.
    """
    addition, street, postal_code, city, country = old
    if not (street and city and customer.street and customer.city):
        return False
    if _street_key(street) == _street_key(customer.street) and fold(city) == fold(customer.city):
        return False
    old_address = (street, postal_code, city)
    if any(same_address(old_address, (a.street, a.postal_code, a.city)) for a in customer.addresses.all()):
        return False
    address = CustomerAddress(
        customer=customer,
        kind=AddressKind.BILLING,
        name_addition=addition,
        street=street,
        postal_code=postal_code,
        city=city,
        country=country,
    )
    address.full_clean()
    address.save()
    return True


def _merge_delivery_address(customer: Customer, cell: Any, mapped: set[str]) -> str:
    """Add the delivery address of the row, unless the customer has it already (IMP-013, KND-005)."""
    values = {
        name: cell_text(cell(f"delivery_{name}")) if f"delivery_{name}" in mapped else ""
        for name in ("name_addition", "street", "postal_code", "city", "country")
    }
    if not (values["street"] and values["city"]):
        return ""
    wanted = (values["street"], values["postal_code"], values["city"])
    if same_address(wanted, (customer.street, customer.postal_code, customer.city)):
        return ""
    existing = next(
        (
            address
            for address in customer.addresses.all()
            if same_address(wanted, (address.street, address.postal_code, address.city))
        ),
        None,
    )
    if existing is not None:
        changed = False
        for name in ("name_addition", "postal_code", "country"):
            # The address is the same; only what it lacks is filled in.
            if values[name] and not getattr(existing, name):
                setattr(existing, name, values[name])
                changed = True
        if changed:
            existing.full_clean()
            existing.save()
            return _("delivery address completed")
        return ""
    address = CustomerAddress(
        customer=customer,
        kind=AddressKind.DELIVERY,
        is_default=not customer.addresses.filter(kind=AddressKind.DELIVERY, is_default=True).exists(),
        **values,
    )
    address.full_clean()
    address.save()
    return _("delivery address added")


def _snapshot(customer: Customer) -> dict[str, Any]:
    """The fields the import can change by name, to tell a change and to show it (IMP-011)."""
    return snapshot(
        customer, ("name", "kind", *TEXT_FIELDS, "payment_terms_days", "default_discount_percent", "is_active")
    )


def _field_labels() -> dict[str, str]:
    labels = {model_field.name: str(model_field.verbose_name) for model_field in Customer._meta.fields}
    for model in (Contact, CustomerAddress):
        for model_field in model._meta.fields:
            labels.setdefault(model_field.name, str(model_field.verbose_name))
    return labels


def run_import(table: Table, mapping: dict[str, int | None], **options: Any) -> CustomerImportReport:
    """The customer import as registered in ``core.imports``."""
    return import_customers(table, mapping, **options)


TITLE = gettext_lazy("Import customers")
INTRODUCTION = gettext_lazy(
    "One row per customer with a heading row. A customer that exists already is found by its number, VAT ID, "
    "e-mail address or name and completed, not duplicated; empty cells change nothing. A list exported from the "
    "customer list can be imported again, and so can a contact export from Lexware (CSV)."
)
