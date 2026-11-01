# SPDX-License-Identifier: GPL-3.0-or-later
"""Subrentals per supplier: the supplier of a subrental line and the page "Zumietung bei …" (PRJ-101, PRJ-106).

PRJ-101 – the supplier of a subrental
    In the dialogs of a subrental the supplier is typed with suggestions
    (:func:`supplier_suggestions`); a name that is not known yet can be
    created right there, in a dialog of its own. The status starts "open";
    every other status needs a supplier (``MaterialLine.clean``).

PRJ-106 – one page per project and supplier
    What is subrented from one supplier for one project, in one place: the
    lines with status and purchase prices, the documents of the supplier
    (offer, order confirmation, delivery note, invoice …, kept as files of
    the project), and the correspondence with the supplier (the mails of the
    project from and to its address, ``mail.suppliers``). The page is
    reached from the subrental line in the planning, from the subrentals
    under Planung → Fehlbestände, and from the supplier in the master data.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, QuerySet
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Module, Rights, SpecialRight
from rentalars.core.money import ZERO, money
from rentalars.masterdata.models import Supplier
from rentalars.products.models import ProductKind
from rentalars.projects.models import MaterialLine, Project, ProjectFile, SubrentalStatus, SupplierDocumentKind

#: How many suggestions the supplier field offers at most.
SUGGESTIONS = 12


# --- PRJ-101: the supplier field ---------------------------------------------------------------------


def may_create_supplier(rights: Rights) -> bool:
    """Who plans subrentals, buys material or keeps the master data may add a supplier (PRJ-101)."""
    return any(rights.can_write(module) for module in (Module.PROJECTS, Module.MATERIAL, Module.ADMINISTRATION))


def may_see_suppliers(rights: Rights) -> bool:
    """Who may look at suppliers outside a project: the master data and the material, and those who plan with them.

    Reading projects alone is not enough: the roles "Crew" and "Freie Kraft" read the projects they are assigned to, and
    suppliers (addresses, contact persons) are not theirs to see (security fix, S10).
    """
    return rights.can_read(Module.MATERIAL) or rights.can_read(Module.ADMINISTRATION) or may_create_supplier(rights)


def supplier_suggestions(text: str, *, rights: Rights) -> list[dict[str, Any]]:
    """Suppliers for the type-ahead field: name, contact person or address contain the text (PRJ-101).

    The last suggestion offers to create a supplier of the typed name –
    unless one of exactly that name exists already.
    """
    text = text.strip()
    suppliers = Supplier.objects.filter(is_active=True)
    if text:
        suppliers = suppliers.filter(Q(name__icontains=text) | Q(contact__icontains=text) | Q(email__icontains=text))
    found = list(suppliers.order_by("name")[:SUGGESTIONS])
    results: list[dict[str, Any]] = [
        {"id": supplier.pk, "label": supplier.name, "hint": supplier.contact or supplier.email} for supplier in found
    ]
    exists = Supplier.objects.filter(name__iexact=text).exists() if text else True
    if not exists and may_create_supplier(rights):
        results.append(
            {
                "id": "",
                "label": _("Create “%(name)s” as a new supplier") % {"name": text},
                "create_url": f"{reverse('projects:supplier_quick_create')}?{urlencode({'name': text})}",
                "create": True,
            }
        )
    return results


def create_supplier(supplier: Supplier) -> Supplier:
    """Store a new supplier from the dialog (PRJ-101); a name differing only in case is refused."""
    if Supplier.objects.filter(name__iexact=supplier.name.strip()).exclude(pk=supplier.pk).exists():
        raise ValidationError({"name": _("There is a supplier of this name already.")})
    supplier.name = supplier.name.strip()
    supplier.full_clean()
    supplier.save()
    return supplier


# --- PRJ-106: the page per project and supplier ------------------------------------------------------


def subrental_lines(project: Project, supplier: Supplier) -> QuerySet[MaterialLine]:
    """The subrentals of a project from one supplier, in the order of their period."""
    return (
        project.material_lines.filter(supplier=supplier, product__kind=ProductKind.SUBRENTAL)
        .select_related("product", "unit", "covers_line", "covers_product", "group")
        .order_by("start", "position", "pk")
    )


def supplier_files(project: Project, supplier: Supplier) -> QuerySet[ProjectFile]:
    """The documents of a supplier among the files of a project, newest first."""
    return project.files.filter(supplier=supplier).select_related("uploaded_by")


def suppliers_of(project: Project) -> list[Supplier]:
    """The suppliers that have something to do with a project: subrentals, documents or linked mails."""
    from rentalars.mail.models import ProjectMail

    ids = set(
        project.material_lines.filter(product__kind=ProductKind.SUBRENTAL, supplier__isnull=False).values_list(
            "supplier_id", flat=True
        )
    )
    ids.update(project.files.filter(supplier__isnull=False).values_list("supplier_id", flat=True))
    ids.update(
        ProjectMail.objects.filter(project=project, supplier__isnull=False).values_list("supplier_id", flat=True)
    )
    return list(Supplier.objects.filter(pk__in=ids).order_by("name"))


@dataclass
class SubrentalRow:
    """A subrental line on the page, with what it costs."""

    line: MaterialLine
    purchase_cost: Decimal | None
    #: The fields of status and purchase price, for whoever may change them (``SubrentalLinesForm``).
    status_field: Any = None
    price_field: Any = None
    #: PRJ-097: the field "picked up at the supplier".
    pickup_field: Any = None


@dataclass
class SubrentalPage:
    """What the page "Zumietung bei …" shows (PRJ-106)."""

    project: Project
    supplier: Supplier
    rows: list[SubrentalRow] = field(default_factory=list)
    files: list[ProjectFile] = field(default_factory=list)
    #: ``None`` without the right to read correspondence.
    mails: list[Any] | None = None
    purchase_total: Decimal = ZERO

    @property
    def status_counts(self) -> list[tuple[str, int]]:
        """How many lines stand at each status, in the order of the statuses."""
        counts = Counter(row.line.subrental_status or SubrentalStatus.OPEN for row in self.rows)
        return [(str(label), counts[value]) for value, label in SubrentalStatus.choices if value in counts]


def build_page(project: Project, supplier: Supplier, *, rights: Rights) -> SubrentalPage:
    """Collect lines, documents and mails of a supplier in a project."""
    from rentalars.mail.services import may_read_mail
    from rentalars.mail.suppliers import mails_with

    page = SubrentalPage(project=project, supplier=supplier)
    for line in subrental_lines(project, supplier):
        cost = money(line.quantity * line.purchase_price) if line.purchase_price is not None else None
        page.rows.append(SubrentalRow(line=line, purchase_cost=cost))
        if cost is not None and line.counts_toward_total:
            page.purchase_total += cost
    page.files = list(supplier_files(project, supplier))
    if may_read_mail(rights):
        mails = mails_with(project, supplier)
        if not rights.has(SpecialRight.PRICES):
            mails = mails.filter(locked=False)  # EML-055: those with lock only with the price right
        page.mails = list(mails.select_related("sent_by").order_by("-date", "-id"))
    return page


@transaction.atomic
def update_lines(
    project: Project, supplier: Supplier, values: dict[int, dict[str, Any]], *, rights: Rights
) -> list[MaterialLine]:
    """Change status and purchase price of several subrentals of a supplier at once (PRJ-106).

    Args:
        project: The project.
        supplier: The supplier; only its lines in the project are changed.
        values: Per line ID the new ``subrental_status`` and/or ``purchase_price``.
        rights: The rights of the caller; purchase prices need their right.

    Returns:
        The lines that changed.

    Raises:
        ValidationError: A line is not one of the supplier's, a value is
            invalid, or the purchase price right is missing. Nothing is saved
            then.
    """
    from rentalars.projects.services import update_line

    lines = {line.pk: line for line in subrental_lines(project, supplier)}
    changed = []
    for pk, wanted in values.items():
        line = lines.get(pk)
        if line is None:
            raise ValidationError(_("The line %(id)s is no subrental of this supplier.") % {"id": pk})
        changes = {name: value for name, value in wanted.items() if getattr(line, name) != value}
        if "purchase_price" in changes and not rights.has(SpecialRight.PURCHASE_PRICES):
            raise ValidationError(_("You do not have the right to set purchase prices."))
        if changes:
            update_line(line, rights=rights, **changes)
            changed.append(line)
    return changed


def add_document(
    project: Project,
    supplier: Supplier,
    uploaded: Any,
    *,
    kind: str,
    title: str = "",
    user: Any,
) -> ProjectFile:
    """Keep a document of a supplier with the project: offer, order confirmation, invoice … (PRJ-106).

    It is a file of the project like any other – listed on the tab
    "Documents" too, marked with its supplier and kind – and never shown to
    the crew.
    """
    from rentalars.projects.files import add_file

    if kind not in SupplierDocumentKind.values:
        raise ValidationError({"supplier_document_kind": _("Unknown kind of document.")})
    return add_file(
        project,
        uploaded,
        user=user,
        title=title,
        visible_to_crew=False,
        supplier=supplier,
        supplier_document_kind=kind,
    )
