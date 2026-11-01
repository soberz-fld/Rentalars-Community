# SPDX-License-Identifier: GPL-3.0-or-later
"""The customers in the format of the customer import (IMP-017; IMP-001, IMP-013).

One row per customer with the columns of ``customers.importer.IMPORT_FIELDS``, found again by its customer
number when the file is imported:

* number, name, kind (by its German name), the main address, e-mail, phone, VAT ID, tax number, payment
  terms, note, active;
* the default delivery address under "Lieferadresse …" (KND-005);
* the contacts – the primary one first – under "Ansprechperson" and "Ansprechpartner 1" and "2", each
  with salutation, e-mail and phone. A further contact is named by first and last name, its position
  in "Ansprechpartner N" (the import tells the two apart, IMP-013);
* the standard discount only with the right to see prices (AUT-017).

"Vorname", "Nachname", "E-Mail 2" and "Telefon 2" stay empty: Rentalars keeps one name, one e-mail address
and one phone number per customer. KND-004: the first and last names of the contacts come from the stored
parts (``Contact.first_name``, ``Contact.last_name``); "Ansprechperson Vorname" and "Nachname" hold those of the
first one. A fourth contact, further billing and delivery addresses and the position of the first contact have no
column in the import and are not in the file. Anonymised customers are left out – the import would refuse their
rows (NFA-009). Three queries per 2,000 customers.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from django.utils.translation import gettext_lazy as _

from rentalars.accounts.rights import SpecialRight
from rentalars.core.import_exports import ExportColumn, ImportFormatExport, chunked, label, number
from rentalars.customers.models import AddressKind, Contact, Customer, CustomerAddress, CustomerKind
from rentalars.customers.names import split_name

CUSTOMER_VALUES = (
    "pk",
    "number",
    "name",
    "kind",
    "name_addition",
    "street",
    "postal_code",
    "city",
    "country",
    "email",
    "phone",
    "vat_id",
    "tax_number",
    "payment_terms_days",
    "default_discount_percent",
    "note",
    "is_active",
)

#: How many contacts the import takes: "Ansprechperson", "Ansprechpartner 1" and "Ansprechpartner 2".
CONTACTS = 3

_NO_ADDRESS: dict[str, str] = {"name_addition": "", "street": "", "postal_code": "", "city": "", "country": ""}


def _chunks(rights: Any) -> Iterator[list[dict[str, Any]]]:
    """The customers in the order of their numbers, each with its first contacts and its delivery address."""
    customers = Customer.objects.filter(anonymised_at__isnull=True).order_by("number").values(*CUSTOMER_VALUES)
    for chunk in chunked(customers.iterator(chunk_size=2000)):
        keys = [row["pk"] for row in chunk]
        contacts: dict[int, list[Any]] = {}
        for contact in (
            Contact.objects.filter(customer_id__in=keys)
            .order_by("customer_id", "-is_primary", "last_name", "first_name", "name", "pk")
            .values("customer_id", "name", "first_name", "last_name", "salutation", "position", "email", "phone")
        ):
            contacts.setdefault(contact["customer_id"], []).append(contact)
        addresses: dict[int, dict[str, Any]] = {}
        for address in (
            CustomerAddress.objects.filter(customer_id__in=keys, kind=AddressKind.DELIVERY)
            .order_by("customer_id", "-is_default", "pk")
            .values("customer_id", *_NO_ADDRESS)
        ):
            addresses.setdefault(address["customer_id"], address)
        for row in chunk:
            row["contacts"] = contacts.get(row["pk"], [])[:CONTACTS]
            row["delivery"] = addresses.get(row["pk"], _NO_ADDRESS)
        yield chunk


def _contact(row: dict[str, Any], position: int) -> dict[str, Any]:
    """The contact in this place (0: "Ansprechperson"), or an empty one."""
    contacts = row["contacts"]
    return contacts[position] if position < len(contacts) else {}


def _parts(contact: dict[str, Any]) -> tuple[str, str]:
    """First and last name of a contact as stored (KND-004); joined by a space they give the name again."""
    if contact.get("first_name") or contact.get("last_name"):
        return contact.get("first_name", ""), contact.get("last_name", "")
    return split_name(contact.get("name", ""))


def _contact_columns(number_of_contact: int) -> tuple[ExportColumn, ...]:
    """The columns of "Ansprechpartner 1" or "2": the contact in place 1 or 2 after the first one.

    The name goes to first and last name, so that "Ansprechpartner N" can hold the position – without one,
    it repeats the name, which the import then takes for the name only.
    """
    prefix, place = f"contact{number_of_contact}_", number_of_contact

    def heading(row: dict[str, Any]) -> str:
        contact = _contact(row, place)
        return contact.get("position") or contact.get("name", "")

    return (
        ExportColumn(f"{prefix}name", heading),
        ExportColumn(f"{prefix}salutation", lambda row: _contact(row, place).get("salutation")),
        ExportColumn(f"{prefix}first_name", lambda row: _parts(_contact(row, place))[0]),
        ExportColumn(f"{prefix}last_name", lambda row: _parts(_contact(row, place))[1]),
        ExportColumn(f"{prefix}email", lambda row: _contact(row, place).get("email")),
        ExportColumn(f"{prefix}phone", lambda row: _contact(row, place).get("phone")),
    )


EXPORT = ImportFormatExport(
    key="customers",
    name=_("Customers"),
    columns=(
        ExportColumn("number", lambda row: row["number"]),
        ExportColumn("name", lambda row: row["name"]),
        # One name per customer; a private person's name is in "Name" as well, its kind in "Art".
        ExportColumn("first_name", lambda row: None),
        ExportColumn("last_name", lambda row: None),
        ExportColumn("salutation", lambda row: _contact(row, 0).get("salutation")),
        ExportColumn("kind", lambda row: label(CustomerKind, row["kind"])),
        ExportColumn("name_addition", lambda row: row["name_addition"]),
        ExportColumn("street", lambda row: row["street"]),
        ExportColumn("postal_code", lambda row: row["postal_code"]),
        ExportColumn("city", lambda row: row["city"]),
        ExportColumn("country", lambda row: row["country"]),
        ExportColumn("delivery_name_addition", lambda row: row["delivery"]["name_addition"]),
        ExportColumn("delivery_street", lambda row: row["delivery"]["street"]),
        ExportColumn("delivery_postal_code", lambda row: row["delivery"]["postal_code"]),
        ExportColumn("delivery_city", lambda row: row["delivery"]["city"]),
        ExportColumn("delivery_country", lambda row: row["delivery"]["country"]),
        ExportColumn("email", lambda row: row["email"]),
        ExportColumn("email_2", lambda row: None),
        ExportColumn("phone", lambda row: row["phone"]),
        ExportColumn("phone_2", lambda row: None),
        ExportColumn("vat_id", lambda row: row["vat_id"]),
        ExportColumn("tax_number", lambda row: row["tax_number"]),
        ExportColumn("payment_terms_days", lambda row: row["payment_terms_days"]),
        ExportColumn(
            "default_discount_percent",
            lambda row: number(row["default_discount_percent"]),
            right=SpecialRight.PRICES,
        ),
        ExportColumn("note", lambda row: row["note"]),
        ExportColumn("contact_name", lambda row: _contact(row, 0).get("name")),
        ExportColumn("contact_first_name", lambda row: _parts(_contact(row, 0))[0]),
        ExportColumn("contact_last_name", lambda row: _parts(_contact(row, 0))[1]),
        ExportColumn("contact_email", lambda row: _contact(row, 0).get("email")),
        ExportColumn("contact_phone", lambda row: _contact(row, 0).get("phone")),
        *_contact_columns(1),
        *_contact_columns(2),
        ExportColumn("active", lambda row: row["is_active"]),
    ),
    chunks=_chunks,
)
