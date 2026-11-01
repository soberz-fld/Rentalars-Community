# SPDX-License-Identifier: GPL-3.0-or-later
"""Business logic for customers: numbering, deactivation, anonymisation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import ProtectedError, Q
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.core.audit import record_event
from rentalars.core.models import NumberRange, NumberRangeKey
from rentalars.customers.models import Customer

#: Text that replaces the name of an anonymised customer.
ANONYMISED_NAME = "Anonymisiert"


def save_customer(customer: Customer) -> Customer:
    """Validate and save a customer; new customers receive their number (KND-003)."""
    if not customer.number:
        # Numbers already in use are skipped – after the counter was set back, say.
        while True:
            _value, customer.number = NumberRange.allocate(NumberRangeKey.CUSTOMER)
            if not Customer.objects.filter(number=customer.number).exists():
                break
    customer.full_clean()
    customer.save()
    return customer


def delete_customer(customer: Customer) -> None:
    """Delete a customer that has no projects (KND-010).

    Raises:
        ValidationError: The customer has projects and can only be
            deactivated or anonymised.
    """
    if customer.owned_products.exists():
        # PRD-043: the customer's material is in the warehouse.
        raise ValidationError(
            _("This customer owns material in the warehouse and cannot be deleted. Deactivate the customer instead.")
        )
    try:
        customer.delete()
    except ProtectedError as error:
        blocking = {type(item).__name__ for item in error.protected_objects}
        if blocking and blocking <= {"Document", "DocumentDraft"} and not customer.projects.exists():
            # Only documents made in Accounting (or their drafts) stand in the way.
            raise ValidationError(
                _(
                    "This customer has outgoing documents or drafts and cannot be deleted. Deactivate or anonymise "
                    "the customer instead."
                )
            ) from error
        raise ValidationError(
            _("This customer has projects and cannot be deleted. Deactivate or anonymise the customer instead.")
        ) from error


@transaction.atomic
def anonymise_customer(customer: Customer) -> None:
    """Erase the personal data of a customer but keep the projects (KND-010).

    Name, address, contact data and note are overwritten, all contact persons
    are deleted, and the customer is deactivated. The customer number and the
    link to the projects stay, so that sums and history of old projects
    remain complete. The step cannot be undone.

    The change log would otherwise still contain the old values, so the
    logged field values of this customer and its contacts are removed too.
    The mails of the customer's projects, and every mail from or to one of
    its addresses, are deleted (EML-031).
    """
    from django.contrib.contenttypes.models import ContentType

    from rentalars.core.audit import AuditedModel
    from rentalars.core.models import AuditLogEntry
    from rentalars.customers.models import Contact, CustomerAddress
    from rentalars.mail.services import delete_mails_of_customer

    customer_type = ContentType.objects.get_for_model(Customer)
    contact_type = ContentType.objects.get_for_model(Contact)
    address_type = ContentType.objects.get_for_model(CustomerAddress)
    contact_ids = [str(pk) for pk in customer.contacts.values_list("pk", flat=True)]
    address_ids = [str(pk) for pk in customer.addresses.values_list("pk", flat=True)]

    # EML-031: the correspondence with the customer goes too – before the
    # contacts, whose addresses find the mails.
    delete_mails_of_customer(customer)
    # The summaries by AI of his projects carry the same content; they go with it (not regenerated).
    from rentalars.ai.auto import forget_customer

    forget_customer(customer)

    # An unfinished document without a project would still hold the name and address (the issued ones
    # stay, as the documents of projects do).
    from rentalars.documents.free import discard_drafts_of

    draft_ids, line_ids = _draft_ids_of(customer)
    discard_drafts_of(customer)

    # UIX-034: where the customer's addresses lie on the map is personal data as well.
    from rentalars.core.maps import forget_addresses, one_line

    forget_addresses(
        one_line(street, f"{postal_code} {city}", country)
        for street, postal_code, city, country in [
            (customer.street, customer.postal_code, customer.city, customer.country),
            *customer.addresses.values_list("street", "postal_code", "city", "country"),
        ]
    )

    # Contacts are removed without individual log entries: the entries would
    # repeat the very names that are being erased.
    customer.contacts.all().delete()
    customer.addresses.all().delete()

    customer.name = f"{ANONYMISED_NAME} ({customer.number})"
    customer.name_addition = ""
    customer.street = ""
    customer.postal_code = ""
    customer.city = ""
    customer.country = ""
    customer.email = ""
    customer.phone = ""
    customer.note = ""
    customer.vat_id = ""
    customer.tax_number = ""
    customer.buyer_reference = ""
    customer.is_active = False
    customer.anonymised_at = timezone.now()
    # Skip the field-by-field log for this save; an event is logged instead.
    super(AuditedModel, customer).save()
    customer._audit_snapshot = customer._audit_values()
    # DOK-016: monthly statements – drafts go, the others lose their activity texts; the log the old name.
    from rentalars.documents.statements import anonymise_statements

    anonymise_statements(customer)

    AuditLogEntry.objects.filter(content_type=customer_type, object_id=str(customer.pk)).update(
        changes={}, object_repr=customer.name
    )
    # AUT-028: the access log names the customer by its new name only.
    from rentalars.core.access_log import forget_customer

    forget_customer(customer)
    AuditLogEntry.objects.filter(content_type=contact_type, object_id__in=contact_ids).update(
        changes={}, object_repr=ANONYMISED_NAME
    )
    AuditLogEntry.objects.filter(content_type=address_type, object_id__in=address_ids).update(
        changes={}, object_repr=ANONYMISED_NAME
    )
    _scrub_draft_entries(customer, draft_ids, line_ids)
    # The buyer's name of a used sale from stock is the customer's name; the sale stays as a record.
    from rentalars.material.sales import forget_customer as forget_buyer

    forget_buyer(customer)
    record_event(customer, "customer.anonymised")


def _draft_ids_of(customer: Customer) -> tuple[set[str], set[str]]:
    """The IDs of the customer's drafts and of their lines, as the change log writes them; before the drafts go."""
    from rentalars.documents.models import DocumentDraft, DraftLine

    draft_ids = {str(pk) for pk in DocumentDraft.objects.filter(customer=customer).values_list("pk", flat=True)}
    line_ids = {str(pk) for pk in DraftLine.objects.filter(draft__customer=customer).values_list("pk", flat=True)}
    return draft_ids, line_ids


def _scrub_draft_entries(customer: Customer, draft_ids: set[str], line_ids: set[str]) -> None:
    """Take the personal data out of the change log of the customer's drafts and their lines (KND-010).

    The log of a draft names the customer in its title and holds the reference, the texts and the titles and notes
    of its lines. The entries stay – *that* a draft was made remains on record – without the values.
    """
    from django.contrib.contenttypes.models import ContentType

    from rentalars.core.models import AuditLogEntry
    from rentalars.documents.models import DocumentDraft, DraftLine

    draft_type = ContentType.objects.get_for_model(DocumentDraft)
    line_type = ContentType.objects.get_for_model(DraftLine)
    customer_type = ContentType.objects.get_for_model(Customer)
    # Drafts and lines name the customer as their audit parent, so those of drafts thrown away long ago are found too.
    of_the_customer = Q(parent_content_type=customer_type, parent_object_id=str(customer.pk))
    AuditLogEntry.objects.filter(
        Q(content_type=draft_type) & (of_the_customer | Q(object_id__in=draft_ids))
        | Q(content_type=line_type) & (of_the_customer | Q(object_id__in=line_ids))
    ).update(changes={}, object_repr=ANONYMISED_NAME)


def export_customer(customer: Customer, *, rights: Any = None, user: Any = None) -> dict[str, object]:
    """Collect everything stored about a customer as one JSON-compatible document (NFA-009).

    For requests for information: master data, contact persons, the
    projects of the customer with their periods, and the documents
    made for him without a project and his drafts, each with number, kind,
    date, reference and total. The prices of the positions are not part of
    it – they describe the company's offer, not the person.

    Review: the AI summaries of his projects are part of it only for an exporter who may read them on
    the project's page (the project, every message including those with lock, so the price right too); how many
    were left out is said in ``ai_summaries_withheld``. Without ``rights`` none is given.
    """
    summaries, withheld = _ai_summaries(customer, rights, user)
    return {
        "exported_at": timezone.now().isoformat(),
        "customer": {
            "number": customer.number,
            "kind": customer.get_kind_display(),
            "name": customer.name,
            "name_addition": customer.name_addition,
            "street": customer.street,
            "postal_code": customer.postal_code,
            "city": customer.city,
            "country": customer.country,
            "email": customer.email,
            "phone": customer.phone,
            "note": customer.note,
            "vat_id": customer.vat_id,
            "tax_number": customer.tax_number,
            "buyer_reference": customer.buyer_reference,
            "payment_terms_days": customer.payment_terms_days,
            "active": customer.is_active,
            "created_at": customer.created_at.isoformat(),
        },
        "addresses": [
            {
                "kind": address.get_kind_display(),
                "label": address.label,
                "lines": address.address_lines,
            }
            for address in customer.addresses.all()
        ],
        "contacts": [
            {
                "salutation": contact.salutation,
                "name": contact.name,
                # KND-004: the parts of the name and the greeting of mails are personal data as well.
                "first_name": contact.first_name,
                "last_name": contact.last_name,
                "greeting_style": contact.get_greeting_style_display(),
                "greeting_text": contact.greeting_text,
                "position": contact.position,
                "email": contact.email,
                "phone": contact.phone,
            }
            for contact in customer.contacts.all()
        ],
        # Documents made in Accounting without a project, and the drafts not yet issued.
        "documents": _documents_without_project(customer),
        "drafts": _drafts(customer),
        # The summaries by AI of his projects are stored about him as well (erased with him, see anonymise).
        "ai_summaries": summaries,
        "ai_summaries_withheld": withheld,
        "projects": [
            {
                "number": project.number,
                "name": project.name,
                "status": project.get_status_display(),
                "from": project.start.isoformat(),
                "until": project.end.isoformat(),
                "venue": project.venue,
            }
            for project in customer.projects.order_by("start")
        ],
    }


def _ai_summaries(customer: Customer, rights: Any, user: Any) -> tuple[list[dict[str, object]], int]:
    """The stored AI summaries of the customer's projects that the exporter may read, and how many he may not.

    A summary carries the content of mails, notes and chat messages; it is shown on the project's page only to
    someone who reads every part it covers, and only with the right to read messages with lock (EML-055). The
    export follows the same rule, and so do the earlier versions of a summary.
    """
    from django.core.exceptions import PermissionDenied

    from rentalars.ai.models import AISummary
    from rentalars.ai.summary import shown_summary
    from rentalars.mail.services import require_mail_read_all

    rows = list(
        AISummary.objects.filter(project__customer=customer).select_related("project").order_by("project__number")
    )
    allowed = rights is not None
    if allowed:
        try:
            require_mail_read_all(rights)
        except PermissionDenied:
            allowed = False
    found: list[dict[str, object]] = []
    for row in rows:
        shown = shown_summary(row.project, rights=rights, user=user) if allowed else None
        if shown is None or shown.summary is None:
            continue
        found.append(
            {
                "project": row.project.number,
                "created_at": row.created_at.isoformat(),
                "model": row.model,
                "provider": row.provider_label,
                "automatic": row.is_automatic,
                "text": row.text,
                "earlier_versions": [
                    {
                        "created_at": version.created_at.isoformat(),
                        "model": version.model,
                        "automatic": version.is_automatic,
                        "text": version.text,
                    }
                    for version in shown.versions
                ],
            }
        )
    return found, len(rows) - len(found)


def _documents_without_project(customer: Customer) -> list[dict[str, object]]:
    """Number, kind, date, total (gross) and reference of the documents made in Accounting for the customer."""
    from rentalars.documents.models import Document

    found = (
        Document.objects.filter(customer=customer, project__isnull=True).defer("content").order_by("issued_on", "id")
    )
    return [
        {
            "number": document.number,
            "kind": document.get_kind_display(),
            "date": document.issued_on.isoformat(),
            "total": str(document.gross_total) if document.gross_total is not None else None,
            "reference": document.reference,
        }
        for document in found
    ]


def _drafts(customer: Customer) -> list[dict[str, object]]:
    """Kind, date, total (gross) and reference of the customer's open drafts; they have no number yet."""
    from rentalars.documents import free
    from rentalars.documents.models import DocumentDraft

    return [
        {
            "number": "",
            "kind": draft.get_kind_display(),
            "date": (draft.issued_on or timezone.localtime(draft.created_at).date()).isoformat(),
            "total": str(free.calculate(free.lines_of(draft)).gross_total),
            "reference": draft.reference,
        }
        for draft in DocumentDraft.objects.filter(customer=customer).order_by("created_at", "id")
    ]


# --- Possible duplicates (KND-008) -------------------------------------------------------------

#: Legal forms and filler words that do not tell two customers apart.
_LEGAL_FORMS = frozenset(
    {
        "gmbh", "mbh", "ag", "kg", "ohg", "gbr", "ug", "ev", "eg", "co", "und", "inc", "ltd", "llc", "se",
        "haftungsbeschränkt", "the", "der", "die", "das",
    }
)  # fmt: skip


def normalised_name(name: str) -> str:
    """A customer name reduced to what identifies it: lower case, no legal form, no punctuation, no single letters.

    "Stadtwerke Musterstadt GmbH & Co. KG" and "stadtwerke  musterstadt" both
    become ``stadtwerke musterstadt``.
    """
    words = re.findall(r"[\w]+", name.lower())
    return " ".join(word for word in words if word not in _LEGAL_FORMS and len(word) > 1)


@dataclass
class PossibleDuplicate:
    """A customer that may be the one being created (KND-008)."""

    customer: Customer
    reason: str


def find_duplicates(name: str, email: str = "", *, exclude_pk: int | None = None) -> list[PossibleDuplicate]:
    """Customers that may be the same as a new one: same name or same e-mail address (KND-008).

    Names count as the same when they agree after :func:`normalised_name`,
    or when one begins with the other and the shorter has at least eight
    letters ("Stadtwerke Musterstadt" and "Stadtwerke Musterstadt
    Veranstaltungen"). An e-mail address counts when it belongs to the
    customer or one of its contacts. Anonymised customers are left out.
    """
    from rentalars.customers.models import Contact

    found: dict[int, PossibleDuplicate] = {}
    wanted = normalised_name(name or "")
    words = sorted(wanted.split(), key=len, reverse=True)
    if words:
        # The longest words find the candidates; whether one is "the same" is decided below.
        condition = Q()
        for word in words[:3]:
            condition |= Q(name__icontains=word)
        candidates = Customer.objects.filter(condition, anonymised_at__isnull=True)
        if exclude_pk:
            candidates = candidates.exclude(pk=exclude_pk)
        for candidate in candidates[:300]:
            other = normalised_name(candidate.name)
            shorter, longer = sorted((wanted, other), key=len)
            if other == wanted or (len(shorter) >= 8 and longer.startswith(shorter)):
                found[candidate.pk] = PossibleDuplicate(candidate, _("similar name"))
    address = (email or "").strip()
    if address:
        same = Customer.objects.filter(email__iexact=address, anonymised_at__isnull=True)
        contact_customers = Contact.objects.filter(email__iexact=address).values_list("customer_id", flat=True)
        same = same | Customer.objects.filter(pk__in=contact_customers, anonymised_at__isnull=True)
        if exclude_pk:
            same = same.exclude(pk=exclude_pk)
        for candidate in same.distinct()[:50]:
            if candidate.pk in found:
                found[candidate.pk].reason = _("similar name and same e-mail address")
            else:
                found[candidate.pk] = PossibleDuplicate(candidate, _("same e-mail address"))
    return sorted(found.values(), key=lambda duplicate: duplicate.customer.name.lower())


# --- Venues (KND-009) -----------------------------------------------------------------------


def save_venue(venue: Any) -> Any:
    """Check and store a venue."""
    venue.full_clean()
    venue.save()
    return venue


def delete_venue(venue: Any) -> None:
    """Delete a venue that no project and no phase names; otherwise deactivate it instead.

    Raises:
        ValidationError: The venue is in use.
    """
    if venue.projects.exists() or venue.phases.exists():
        raise ValidationError(_("Projects name this venue. Deactivate it instead of deleting it."))
    hall_plan = venue.hall_plan
    venue.delete()
    if hall_plan:
        hall_plan.delete(save=False)
