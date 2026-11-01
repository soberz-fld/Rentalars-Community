# SPDX-License-Identifier: GPL-3.0-or-later
"""Packing for whole projects and their subprojects (PRJ-048, PRJ-060).

Every subproject is a project of its own with its own packlists: it is
packed, issued and returned on its own, and its status follows its packlists
(``packing.services``). This module adds what concerns several parts at once.

The packlist of the whole project (PRJ-048)
-------------------------------------------
:func:`build_family_packlist` puts the packlists of the whole project and of
every part together – part by part, or summed up per article for the
warehouse – with the progress of each part. It is read-only: packing, issue
and return stay with each part. Parts whose packlist the user may not see
are left out and counted (PRJ-049).

Material that moves on from one part to the next (PRJ-060)
----------------------------------------------------------
Line T of part B takes over the pieces of line S of part A
(``MaterialLine.taken_over_from``). Both packlists show it: A's row says how
many pieces go on to B, B's row says where they come from. B does not pack
them in the warehouse, issuing B leaves them alone, and no free item is
allocated for them.

When the pieces arrive at B, the *handover* is booked on B's packlist
(:func:`hand_over`), in parts if need be:

* for A the pieces count as back (``PackEntry.handed_over_quantity``): A can
  complete its return without them;
* for B they count as issued: B's packlist is out from then on – B's project
  once everything of it is out (PCK-025) – and B returns them to the
  warehouse as usual;
* the item allocations of S move to T where it is beyond doubt which items
  went: every piece still with A goes, A returned none of them to the
  warehouse, and all of S's pieces went to this one row. The history of an
  item then shows both parts (MAT-025). Otherwise nothing is noted, as
  everywhere in packing (PCK-020).

Booking needs write access to the packlists of both parts.

A handover can be taken back (:func:`undo_handover`) while neither B's nor
A's packlist is returned and none of its pieces is back in the warehouse or
gone on further; the latest booking of a row first.

Pieces still waiting for their handover when A is returned count as missing
for A (PCK-019): "everything is back" leaves them out, and A's return cannot
be completed until they are handed over, ticked as back after all, or
clarified. After A's return, nothing more can be handed over from A.

Deleting line T or clearing its source makes it an ordinary line again;
handovers booked before stay booked.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from rentalars.accounts.rights import Level, Module, Rights
from rentalars.api import webhooks
from rentalars.core.audit import record_event
from rentalars.core.i18n import plural_of
from rentalars.packing import services
from rentalars.packing.models import Allocation, Handover, PackEntry, Packlist, PacklistStatus
from rentalars.products.models import Product
from rentalars.projects.access import ProjectAccess, access_level, module_level_in
from rentalars.projects.family import members
from rentalars.projects.models import Project, ProjectStatus

ZERO = Decimal("0")

#: How the packlist of the whole project is shown: part by part, or summed up per article (PRJ-048).
VIEW_PARTS, VIEW_ARTICLES = "parts", "articles"
VIEWS = (VIEW_PARTS, VIEW_ARTICLES)


def packing_level_in(rights: Rights, user: Any, project: Project) -> int:
    """The user's level of "packing" in a project's packlist; ``NONE`` if the packlist is hidden from them.

    The rule of ``projects.access.packlist_project_for`` (AUT-025, PRJ-049),
    without a request: whoever sees the project, or has "packing" for all
    projects, sees its packlist as far as the role reads "packing".
    """
    if (
        access_level(rights, user, project) == ProjectAccess.NONE
        and rights.level_everywhere(Module.PACKING) < Level.READ
    ):
        return Level.NONE
    return module_level_in(rights, user, project, Module.PACKING)


def _name(project: Project) -> str:
    """Number and name of a project, for texts."""
    return f"{project.number} {project.name}"


# --- The packlist of the whole project (PRJ-048) ------------------------------------------------------


@dataclass
class PackFigures:
    """How far the packing of one part – or of all of them – got (PRJ-048)."""

    #: Pieces to pack in the warehouse and how many of them are ticked.
    required: Decimal = ZERO
    packed: Decimal = ZERO
    #: Pieces issued from the warehouse.
    issued: Decimal = ZERO
    #: Pieces out with the part (from the warehouse or handed over to it) and how many of them are back.
    out: Decimal = ZERO
    back: Decimal = ZERO
    #: PRJ-060: pieces taken over from other parts, and how many of them arrived.
    taken_over: Decimal = ZERO
    handed_in: Decimal = ZERO
    #: PRJ-060: pieces later parts take over from this one, and how many went on.
    passing_on: Decimal = ZERO
    handed_on: Decimal = ZERO

    def add(self, other: PackFigures) -> None:
        """Add the figures of another part."""
        for name in self.__dataclass_fields__:
            setattr(self, name, getattr(self, name) + getattr(other, name))

    @property
    def packed_percent(self) -> int:
        """Packing progress from 0 to 100."""
        return int(self.packed * 100 / self.required) if self.required else 0

    @property
    def issued_percent(self) -> int:
        """Issue progress from 0 to 100."""
        return int(self.issued * 100 / self.required) if self.required else 0

    @property
    def back_percent(self) -> int:
        """Return progress from 0 to 100."""
        return int(self.back * 100 / self.out) if self.out else 0


def figures_of(overviews: list[services.PackOverview]) -> PackFigures:
    """Count what the packlists of one part hold (PRJ-048)."""
    figures = PackFigures()
    for overview in overviews:
        figures.required += overview.required_total
        figures.packed += overview.packed_total
        figures.out += overview.issued_total
        figures.back += overview.returned_total
        for row in overview.rows:
            if row.is_takeover:
                figures.taken_over += row.required
                figures.handed_in += min(row.issued, row.required)
            else:
                figures.issued += min(row.issued, row.required)
            figures.passing_on += sum((passing.planned for passing in row.passes_on), ZERO)
            figures.handed_on += row.handed_over
    return figures


@dataclass
class PartPacking:
    """The packlists of one part, or of the whole project's own lines (PRJ-048)."""

    project: Project
    #: True for the whole project's own lines (central power, production office).
    is_whole: bool
    overviews: list[services.PackOverview] = field(default_factory=list)

    @property
    def figures(self) -> PackFigures:
        """Progress of the part's packlists."""
        return figures_of(self.overviews)

    @property
    def rows(self) -> list[services.PackRow]:
        """All rows of all its packlists."""
        return [row for overview in self.overviews for row in overview.rows]

    @property
    def bar(self) -> services.ProgressBar:
        """PCK-029: the pieces of the part in the five states of the packlist bar."""
        total = services.ProgressBar()
        for overview in self.overviews:
            total.add(overview.bar)
        return total


@dataclass
class ArticleShare:
    """What one part needs of an article (PRJ-048)."""

    project: Project
    quantity: Decimal
    #: The pieces come from another part, not from the warehouse (PRJ-060).
    is_takeover: bool


@dataclass
class ArticleSum:
    """One article over all parts, for the warehouse (PRJ-048).

    Pieces taken over from another part are counted apart: they do not come
    from the warehouse again (PRJ-060). ``issued`` and ``returned`` are
    movements of the warehouse: out of it, and back into it.
    """

    product: Product
    from_warehouse: Decimal = ZERO
    taken_over: Decimal = ZERO
    packed: Decimal = ZERO
    issued: Decimal = ZERO
    returned: Decimal = ZERO
    shares: list[ArticleShare] = field(default_factory=list)

    @property
    def is_packed(self) -> bool:
        """Whether every piece from the warehouse is ticked."""
        return self.from_warehouse > ZERO and self.packed >= self.from_warehouse


@dataclass
class ArticleSection:
    """The articles of one category (PCK-004)."""

    title: str
    articles: list[ArticleSum]


@dataclass
class FamilyPacklist:
    """The packlists of a whole project and all its parts the user may see (PRJ-048)."""

    whole: Project
    parts: list[PartPacking] = field(default_factory=list)
    #: Parts whose packlist the user may not see; they are left out (PRJ-049).
    hidden: int = 0

    @property
    def figures(self) -> PackFigures:
        """The progress of all parts shown together."""
        total = PackFigures()
        for part in self.parts:
            total.add(part.figures)
        return total

    @property
    def bar(self) -> services.ProgressBar:
        """PCK-029: the pieces of all parts shown, in the five states of the packlist bar."""
        total = services.ProgressBar()
        for part in self.parts:
            total.add(part.bar)
        return total

    @property
    def subprojects(self) -> list[PartPacking]:
        """The parts without the whole project's own lines."""
        return [part for part in self.parts if not part.is_whole]

    @property
    def articles(self) -> list[ArticleSum]:
        """Every article over all parts shown, by category and article number."""
        by_product: dict[int, ArticleSum] = {}
        for part in self.parts:
            shares: dict[tuple[int, bool], Decimal] = defaultdict(lambda: ZERO)
            for row in part.rows:
                article = by_product.setdefault(row.product.pk, ArticleSum(product=row.product))
                if row.is_takeover:
                    article.taken_over += row.required
                else:
                    article.from_warehouse += row.required
                    article.packed += min(row.packed, row.required)
                    article.issued += row.issued
                article.returned += min(row.returned, row.issued)
                shares[(row.product.pk, row.is_takeover)] += row.required
            for (product_id, is_takeover), quantity in shares.items():
                by_product[product_id].shares.append(
                    ArticleShare(project=part.project, quantity=quantity, is_takeover=is_takeover)
                )
        return sorted(
            by_product.values(),
            key=lambda article: (article.product.category.path.lower(), article.product.article_number),
        )

    @property
    def article_sections(self) -> list[ArticleSection]:
        """The articles in sections per category, the way through the warehouse (PCK-004)."""
        sections: list[ArticleSection] = []
        for article in self.articles:
            title = article.product.category.path
            if not sections or sections[-1].title != title:
                sections.append(ArticleSection(title=title, articles=[]))
            sections[-1].articles.append(article)
        return sections


def build_family_packlist(project: Project, *, rights: Rights, user: Any) -> FamilyPacklist:
    """The packlists of the whole project of ``project`` and of all its parts the user may see (PRJ-048).

    The whole project's own lines come first, then the parts by number. A
    part is left out – and counted in ``hidden`` – where the user may not see
    its packlist (``packlist_project_for`` semantics per part, PRJ-049).
    """
    everything = members(project)
    family = FamilyPacklist(whole=everything[0])
    for member in everything:
        if packing_level_in(rights, user, member) < Level.READ:
            family.hidden += 1
            continue
        family.parts.append(
            PartPacking(
                project=member,
                is_whole=member.pk == family.whole.pk,
                overviews=[services.build_overview(packlist) for packlist in services.packlists_of(member)],
            )
        )
    return family


# --- Handing material over from one part to the next (PRJ-060) ---------------------------------------


@transaction.atomic
def hand_over(
    packlist: Packlist,
    line_id: int,
    product_id: int,
    quantity: Decimal | None = None,
    *,
    user: Any = None,
    rights: Rights | None = None,
) -> Handover:
    """Book that pieces taken over from another subproject have arrived (PRJ-060).

    Args:
        packlist: B's packlist with the takeover row.
        line_id: The line T of the row.
        product_id: The product of the row (a component for a kit).
        quantity: How many pieces arrived; all that are expected and still
            out with A if not given. Can be fewer: the rest follows later.
        user: Who books.
        rights: The rights of the caller; then the packlist of A must be
            writable as well (AUT-016, PRJ-049).

    Returns:
        The booking.

    Raises:
        ValidationError: The row takes over nothing, A's material is not out
            (any more), more pieces than expected or than A still has, B is
            finished, or the caller may not change A's packlist.
    """
    project = packlist.project
    if packlist.status == PacklistStatus.RETURNED:
        raise ValidationError(_("The return of this packing list is complete."))
    if project.status in {ProjectStatus.CANCELLED, ProjectStatus.CLOSED, ProjectStatus.RETURNED}:
        raise ValidationError(_("Material cannot be handed over to a project that is cancelled or finished."))
    overview = services.build_overview(packlist)
    row = services.find_row(overview, line_id, product_id)
    if row.takeover_from is None:
        raise ValidationError(_("This row does not take over material from another subproject."))
    source_line = row.takeover_from
    source_project = source_line.project
    if rights is not None and packing_level_in(rights, user, source_project) < Level.WRITE:
        raise ValidationError(
            _("To book the handover you also need to be allowed to work on the packing list of %(project)s.")
            % {"project": _name(source_project)}
        )
    source_packlist = services.packlist_of_line(source_line)
    source = (
        PackEntry.objects.select_for_update()
        .filter(packlist=source_packlist, line=source_line, product_id=product_id)
        .first()
    )
    if source is None or source.issued_quantity <= ZERO:
        raise ValidationError(
            _("The material of %(project)s has not been issued yet. It can be handed over once it is out.")
            % {"project": _name(source_project)}
        )
    if not source_packlist.is_out:
        raise ValidationError(
            _("The return of %(project)s is complete; nothing more can be handed over from there.")
            % {"project": _name(source_project)}
        )
    with_source = source.issued_quantity - source.returned_quantity - source.handed_over_quantity
    awaiting = row.awaiting_handover
    if awaiting <= ZERO:
        raise ValidationError(_("Every piece of this row has been handed over."))
    if with_source <= ZERO:
        raise ValidationError(
            _("None of these pieces is still out with %(project)s: they are back in the warehouse or went on.")
            % {"project": _name(source_project)}
        )
    quantity = min(awaiting, with_source) if quantity is None else Decimal(quantity)
    if quantity <= ZERO:
        raise ValidationError({"quantity": _("Enter a quantity above zero.")})
    if quantity > awaiting:
        raise ValidationError(
            {
                "quantity": ngettext(
                    "Only %(count)s more piece is expected from %(project)s.",
                    "Only %(count)s more pieces are expected from %(project)s.",
                    plural_of(awaiting),
                )
                % {"count": services._number(awaiting), "project": _name(source_project)}
            }
        )
    if quantity > with_source:
        raise ValidationError(
            {
                "quantity": ngettext(
                    "Only %(count)s piece of it is still out with %(project)s.",
                    "Only %(count)s pieces of it are still out with %(project)s.",
                    plural_of(with_source),
                )
                % {"count": services._number(with_source), "project": _name(source_project)}
            }
        )

    services._start_packing(packlist, overview)
    target = PackEntry.objects.select_for_update().get(pk=services._entry_for(packlist, row).pk)
    now = timezone.now()
    handover = Handover.objects.create(
        source=source, target=target, quantity=quantity, handed_over_at=now, handed_over_by=user
    )
    source.handed_over_quantity += quantity
    source.updated_by = user
    source.save()
    target.issued_quantity += quantity
    target.packed_quantity = max(target.packed_quantity, target.issued_quantity)
    target.updated_by = user
    target.save()
    _move_allocations(handover, now)
    services._close_allocations_if_back(source, now)
    _out_after_handover(packlist, now, user)

    details = {"quantity": services._number(quantity), "product": row.product.article_number}
    record_event(packlist, "packlist.handed_over", {**details, "project": source_project.number})
    record_event(source_packlist, "packlist.handed_on", {**details, "project": project.number})
    webhooks.record(  # API-012
        "packing.handed_over",
        packlist,
        from_packlist=source_packlist,
        product=row.product,
        quantity=quantity,
        undone=False,
    )
    return handover


def _move_allocations(handover: Handover, now: Any) -> None:
    """Move the items noted for A's row to B's row where it is beyond doubt which went (PRJ-060, PCK-021).

    That is the case when the booking takes every piece still with A, A
    returned none of them to the warehouse, and every handover of A's row
    went to this one row of B. The allocation at A is closed and a new one
    opened at B, together with the contents of a container (MAT-037): the
    history of the item shows both parts (MAT-025). The item stays in use.
    """
    source, target = handover.source, handover.target
    if source.returned_quantity > ZERO or source.handed_over_quantity < source.issued_quantity:
        return
    if Handover.objects.filter(source=source).exclude(target=target).exists():
        return
    for allocation in source.allocations.filter(
        with_container__isnull=True, issued_at__isnull=False, returned_at__isnull=True
    ).select_related("item"):
        allocation.returned_at = now
        allocation.save()
        moved = Allocation.objects.create(entry=target, item=allocation.item, issued_at=now, handover=handover)
        for content in allocation.contents.filter(returned_at__isnull=True).select_related("item"):
            content.returned_at = now
            content.save()
            Allocation.objects.create(entry=target, item=content.item, issued_at=now, with_container=moved)


def _out_after_handover(packlist: Packlist, now: Any, user: Any) -> None:
    """B's packlist is out as soon as taken-over pieces arrived; B's project follows (PRJ-060, PCK-018).

    It is "issued" if nothing is left to issue from the warehouse, else
    "partly issued": the rest can be packed and issued as usual. B's project
    becomes "out" once everything of it is out (PCK-025).
    """
    if packlist.status in {PacklistStatus.OPEN, PacklistStatus.IN_PROGRESS, PacklistStatus.PACKED}:
        overview = services.build_overview(packlist)
        complete = all(row.is_fully_issued for row in overview.warehouse_rows)
        packlist.status = PacklistStatus.ISSUED if complete else PacklistStatus.PARTLY_ISSUED
        packlist.issued_at = packlist.issued_at or now
        packlist.issued_by = packlist.issued_by or user
        packlist.save()
    services._project_after_packlists(packlist.project)


@transaction.atomic
def undo_handover(handover: Handover, *, user: Any = None, rights: Rights | None = None) -> None:
    """Take back a handover booked by mistake (PRJ-060).

    The pieces are with A again: missing there until they come back or are
    handed over anew. Items that moved to B are noted at A again.

    Raises:
        ValidationError: B's or A's return is complete, a later handover of
            the same pieces exists, pieces of it are back in the warehouse or
            went on further already, or the caller may not change A's
            packlist.
    """
    target = (
        PackEntry.objects.select_for_update().select_related("packlist__project", "product").get(pk=handover.target_id)
    )
    source = PackEntry.objects.select_for_update().select_related("packlist__project").get(pk=handover.source_id)
    packlist, source_packlist = target.packlist, source.packlist
    if rights is not None and packing_level_in(rights, user, source_packlist.project) < Level.WRITE:
        raise ValidationError(
            _("To take back the handover you also need to be allowed to work on the packing list of %(project)s.")
            % {"project": _name(source_packlist.project)}
        )
    if packlist.status == PacklistStatus.RETURNED:
        raise ValidationError(
            _("The return of this packing list is complete. The handover can no longer be taken back.")
        )
    if not source_packlist.is_out:
        raise ValidationError(
            _("The return of %(project)s is complete. The handover can no longer be taken back.")
            % {"project": _name(source_packlist.project)}
        )
    if Handover.objects.filter(source=source, pk__gt=handover.pk).exists():
        raise ValidationError(_("These pieces were handed over again later. Take back the later handover first."))
    quantity = handover.quantity
    if target.issued_quantity - quantity < target.returned_quantity + target.handed_over_quantity:
        raise ValidationError(
            _("Pieces of this handover are back in the warehouse or went on already. Correct that first.")
        )

    # The items as they were before the booking: open at A again, unless an item is somewhere else by now.
    for allocation in source.allocations.filter(
        returned_at=handover.handed_over_at, issued_at__isnull=False
    ).select_related("item"):
        elsewhere = (
            Allocation.objects.filter(item=allocation.item, returned_at__isnull=True)
            .exclude(handover=handover)
            .exclude(with_container__handover=handover)
            .exists()
        )
        if elsewhere:
            continue
        allocation.returned_at = None
        allocation.save()
        services._set_in_use(allocation.item)
    handover.delete()  # its allocations at B go with it (with their contents)
    source.handed_over_quantity -= quantity
    source.updated_by = user
    source.save()
    target.issued_quantity -= quantity
    target.packed_quantity = max(target.packed_quantity - quantity, target.issued_quantity)
    target.updated_by = user
    target.save()
    if not packlist.entries.filter(issued_quantity__gt=0).exists():
        # Nothing of B's packlist is out any more: back to packing.
        packlist.status = PacklistStatus.PACKED
        packlist.issued_at = None
        packlist.issued_by = None
        packlist.save()
        services._derive_packing_status(packlist)
    services._project_after_packlists(packlist.project)

    details = {"quantity": services._number(quantity), "product": target.product.article_number}
    record_event(packlist, "packlist.handover_undone", {**details, "project": source_packlist.project.number})
    record_event(source_packlist, "packlist.handover_undone", {**details, "project": packlist.project.number})
    webhooks.record(  # API-012
        "packing.handed_over",
        packlist,
        from_packlist=source_packlist,
        product=target.product,
        quantity=quantity,
        undone=True,
    )
