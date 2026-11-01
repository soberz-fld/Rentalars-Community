# SPDX-License-Identifier: GPL-3.0-or-later
"""Packlists, issue and return (chapter 5.8).

A packlist is not a copy of the project's material lines. Its rows are derived
from the lines whenever the packlist is shown (see ``packing.services``), so a
changed line is reflected at once. What *is* stored here is the progress:
how much of each row has been packed, issued and returned.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rentalars.core.audit import AuditedModel
from rentalars.material.models import MaterialItem
from rentalars.products.models import Product
from rentalars.projects.models import MaterialLine, Project


class PacklistStatus(models.TextChoices):
    """The packing status of a packlist (PCK-014), extended by "partly issued" and "returned"."""

    OPEN = "open", _("open")
    IN_PROGRESS = "in_progress", _("in progress")
    PACKED = "packed", _("packed")
    PARTLY_ISSUED = "partly_issued", _("partly issued")
    ISSUED = "issued", _("issued")
    RETURNED = "returned", _("returned")


#: Statuses in which material of the packlist is out (PCK-018).
OUT_STATUSES = frozenset({PacklistStatus.PARTLY_ISSUED.value, PacklistStatus.ISSUED.value})


def material_out(project_field: str = "pk") -> models.Exists:
    """PCK-025, PCK-028: whether material of a project is out – also while the project is not "out" yet.

    Material that was issued is out regardless of the project status: lists
    of what is out and the availability ask this instead of the status. Use
    it in ``annotate`` or ``filter`` on a query of projects, or with
    ``project_field="project_id"`` on one of material lines.

    PCK-028: a packlist that is issued counts only as long as
    pieces of it are out by the books: issued and neither booked back nor
    handed over to another subproject. Sold pieces never come back and do
    not count.
    """
    return models.Exists(
        PackEntry.objects.filter(
            packlist__project_id=models.OuterRef(project_field),
            packlist__status__in=OUT_STATUSES,
            issued_quantity__gt=models.F("taken_back_quantity") + models.F("handed_over_quantity"),
        ).filter(models.Q(line__isnull=True) | models.Q(line__is_sale=False))
    )


def taken_back_of(line_field: str = "pk", product_field: str = "product_id") -> dict[str, models.Expression]:
    """PCK-028: what of a material line was booked back early, for ``annotate`` on a query of lines.

    Returns ``taken_back`` (pieces of the line's own product), ``taken_back_at``
    (when the latest of them was booked) and ``kit_taken_back`` (whether pieces
    of other products – the components of a kit – were booked back). The
    availability engine frees these pieces at once (``availability.engine``).
    """
    own = PackEntry.objects.filter(
        line_id=models.OuterRef(line_field), product_id=models.OuterRef(product_field), taken_back_quantity__gt=0
    )
    return {
        "taken_back": models.Subquery(own.values("taken_back_quantity")[:1]),
        "taken_back_at": models.Subquery(own.values("taken_back_at")[:1]),
        "kit_taken_back": models.Exists(
            PackEntry.objects.filter(line_id=models.OuterRef(line_field), taken_back_quantity__gt=0).exclude(
                product_id=models.OuterRef(product_field)
            )
        ),
    }


class Packlist(AuditedModel):
    """A packlist of a project (PCK-001, PCK-008).

    A project has one packlist to begin with, which takes every line. More
    can be added – per group, per trade, per vehicle, per loading date; each
    line then belongs to one of them (:class:`LineAssignment`), and each is
    packed, issued and returned on its own. Lines that were not given to a
    packlist land on the first one, the *main* packlist.
    """

    project = models.ForeignKey(Project, verbose_name=_("project"), on_delete=models.CASCADE, related_name="packlists")
    title = models.CharField(
        _("title"), max_length=120, blank=True, help_text=_("e.g. “Truck 1”, “Light”, “Thursday”.")
    )
    loading_at = models.DateTimeField(_("loading"), null=True, blank=True)
    note = models.CharField(_("note"), max_length=250, blank=True)
    #: LOG-001: the vehicle of the project's logistics this list is loaded into – a hint on the list.
    vehicle_line = models.ForeignKey(
        "projects.VehicleLine",
        verbose_name=_("vehicle"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="packlists",
    )
    status = models.CharField(_("status"), max_length=14, choices=PacklistStatus.choices, default=PacklistStatus.OPEN)
    #: PCK-015: from here on, changed lines are highlighted.
    packing_started_at = models.DateTimeField(_("packing started"), null=True, blank=True)
    issued_at = models.DateTimeField(_("issued at"), null=True, blank=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    returned_at = models.DateTimeField(_("returned at"), null=True, blank=True)
    returned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(_("created"), default=timezone.now, editable=False)

    class Meta:
        verbose_name = _("packing list")  # UIX-029: "packlist" was no English word
        verbose_name_plural = _("packing lists")
        ordering = ["project", "id"]

    def __str__(self) -> str:
        return f"{_('Packing list')} {self.project.number}"

    def audit_parent(self) -> models.Model | None:
        """Show packing events in the history of the project (PRJ-032)."""
        return self.project

    @property
    def is_issued(self) -> bool:
        """Whether material of this packlist has left the warehouse (all or part of it)."""
        return self.status in {PacklistStatus.PARTLY_ISSUED, PacklistStatus.ISSUED, PacklistStatus.RETURNED}

    @property
    def is_out(self) -> bool:
        """Whether the packlist is issued and its return not complete: returns can be ticked and booked.

        PCK-028: the pieces may all be back by the books already – e.g. a
        partly issued packlist whose issued pieces came back while the rest
        waits for its issue. Whether pieces are out is :func:`material_out`.
        """
        return self.status in OUT_STATUSES

    @property
    def can_be_packed(self) -> bool:
        """Whether ticking "packed" is still possible: before everything is issued (PCK-018)."""
        return self.status in {
            PacklistStatus.OPEN,
            PacklistStatus.IN_PROGRESS,
            PacklistStatus.PACKED,
            PacklistStatus.PARTLY_ISSUED,
        }

    @property
    def label(self) -> str:
        """The title, or "packlist" for an untitled one."""
        return self.title or str(_("Packing list"))


#: PCK-027: the quantities whose last change is noted, each with the field that holds the moment.
CHANGE_TIME_FIELDS = (("packed_quantity", "packed_changed_at"), ("returned_quantity", "returned_changed_at"))


class PackEntry(models.Model):
    """The progress of one packlist row: packed, issued, ticked as back, taken back.

    A row is identified by the material line and the product to pack. For a
    normal line both belong together; for a kit line there is one entry per
    component product (PCK-005).

    Quantities are plain numbers. No scan and no choice of an individual item
    is ever needed (PCK-020): three cables are issued with one tick.

    Ticking and booking (PCK-025, PCK-028): ``packed_quantity`` is what is
    ticked while packing, ``issued_quantity`` what "issue" booked out of the
    warehouse. In the same way ``returned_quantity`` is what is ticked as
    back, ``taken_back_quantity`` what "book the return" booked back into the
    warehouse. Every quantity counts pieces, and each includes the next:
    packed ≥ issued, issued ≥ returned ≥ taken back. A piece that was taken
    back is done for this project: it is never issued again here.

    PCK-027: ``packed_changed_at`` and ``returned_changed_at`` hold when the
    two ticked quantities last changed – on whatever way: ticking, "tick
    all", "issue everything", a handover, "changes are dealt with", the
    offline sync. :meth:`save` notes it; a quantity that stays the same keeps
    its time. The sync stores the moment of the change on the phone instead
    of now (``change_time``).

    PCK-027: ``version`` counts the changes of these two quantities,
    on the same ways – one more with every save that changes one of them. The
    sync compares it with the version the phone saw (``base_version``); the
    rows show it. Bookings that change neither quantity (issue, take-back,
    the snapshot when packing starts) leave it alone: they would make every
    offline change of the row a conflict, and the limits of ticking
    (PCK-028) guard against them anyway. Writers of the two quantities lock
    the row (``select_for_update``) so that the count has no gaps or doubles.
    """

    packlist = models.ForeignKey(Packlist, on_delete=models.CASCADE, related_name="entries")
    #: Empty once the line was deleted; the entry stays while it still matters (PCK-015).
    line = models.ForeignKey(MaterialLine, null=True, on_delete=models.SET_NULL, related_name="pack_entries")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    #: PCK-015: what the row said when packing started, to highlight later changes.
    title_snapshot = models.CharField(max_length=250, blank=True)
    required_snapshot = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    packed_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    issued_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    #: PCK-016, PCK-028: ticked as back – not booked yet unless ``taken_back_quantity`` says so.
    returned_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    #: PCK-028: booked back into the warehouse ("book the return"); free again for other projects.
    taken_back_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    #: PCK-028: when pieces of the row were booked back last.
    taken_back_at = models.DateTimeField(null=True, blank=True)
    #: PRJ-060: pieces that went straight on to another subproject instead of back to the warehouse.
    #: They count as back for this row; the sum of the row's :class:`Handover` bookings as source.
    handed_over_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    #: PCK-019: missing parts were clarified (lost, charged, found later …).
    missing_resolved = models.BooleanField(default=False)
    missing_note = models.CharField(max_length=250, blank=True)
    #: PCK-027: when the packed and the returned quantity last changed.
    packed_changed_at = models.DateTimeField(null=True, blank=True)
    returned_changed_at = models.DateTimeField(null=True, blank=True)
    #: PCK-027: the server-side version of the two ticked quantities; see the class documentation.
    version = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = _("packing list entry")
        verbose_name_plural = _("packing list entries")
        constraints = [
            models.UniqueConstraint(fields=["packlist", "line", "product"], name="pack_entry_unique"),
        ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        #: PCK-027: the moment to note for a changed quantity instead of now (the offline sync).
        self.change_time: datetime.datetime | None = None
        # A new entry starts from the defaults; one loaded from the database from what it holds.
        self._saved_quantities: dict[str, Decimal | None] = (
            dict.fromkeys((name for name, _time in CHANGE_TIME_FIELDS), Decimal("0")) if self._state.adding else {}
        )

    def __str__(self) -> str:
        return f"{self.product.article_number} ({self.packed_quantity})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save; a changed packed or returned quantity notes the moment of its change (PCK-027).

        Such a change also counts the ``version`` up by one (PCK-027).
        """
        noted = []
        for quantity_field, time_field in CHANGE_TIME_FIELDS:
            before = self._saved_quantities.get(quantity_field)
            now = self.__dict__.get(quantity_field)
            if before is None or now is None or Decimal(now) == Decimal(before):
                continue
            setattr(self, time_field, self.change_time or timezone.now())
            noted.append(time_field)
        if noted:
            self.version = (self.version or 0) + 1
            noted.append("version")
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and noted:
            kwargs["update_fields"] = {*update_fields, *noted}
        super().save(*args, **kwargs)
        self._remember_quantities()
        self.change_time = None

    @classmethod
    def from_db(cls, db: str | None, field_names: Any, values: Any) -> PackEntry:
        """Remember the quantities as loaded, to tell a change on saving (PCK-027)."""
        entry = super().from_db(db, field_names, values)
        entry._remember_quantities()
        return entry

    def refresh_from_db(self, *args: Any, **kwargs: Any) -> None:
        """Reload, and take the reloaded quantities as the saved state (PCK-027)."""
        super().refresh_from_db(*args, **kwargs)
        self._remember_quantities()

    def _remember_quantities(self) -> None:
        # A deferred field is not in __dict__; its change cannot be told and is not noted.
        self._saved_quantities = {name: self.__dict__.get(name) for name, _time in CHANGE_TIME_FIELDS}

    @property
    def missing_quantity(self) -> Decimal:
        """What was issued but has neither come back nor gone on to another subproject (PCK-016, PRJ-060)."""
        return max(self.issued_quantity - self.returned_quantity - self.handed_over_quantity, Decimal("0"))

    @property
    def out_quantity(self) -> Decimal:
        """PCK-028: what is out by the books – issued, not taken back, not handed over."""
        return max(self.issued_quantity - self.taken_back_quantity - self.handed_over_quantity, Decimal("0"))


class Allocation(models.Model):
    """A concrete item that went out with a project (PCK-021, catalogue 7.2 "Materialzuteilung").

    Allocations are optional. They arise automatically where the choice is
    unambiguous – a product with a single item, or the whole stock of a
    product going out – and are the basis for the deployment history of an
    item (MAT-025). Where no allocation exists, nothing is blocked (PCK-022).

    Rule from catalogue 7.3: an item is never in two allocations that are
    open at the same time. ``packing.services`` checks this before creating
    one.
    """

    entry = models.ForeignKey(PackEntry, on_delete=models.CASCADE, related_name="allocations")
    item = models.ForeignKey(MaterialItem, on_delete=models.PROTECT, related_name="allocations")
    #: Empty while the item is chosen but not yet issued (PCK-022).
    issued_at = models.DateTimeField(null=True, blank=True, default=timezone.now)
    returned_at = models.DateTimeField(null=True, blank=True)
    #: MAT-037: content that went out (and comes back) with its container.
    with_container = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="contents")
    #: PRJ-060: the item came with this handover from another subproject; taking it back removes the allocation.
    handover = models.ForeignKey(
        "Handover", null=True, blank=True, on_delete=models.CASCADE, related_name="allocations"
    )
    #: PCK-010: when the item was scanned while packing – the scan chose it for the row and counted it.
    packed_scan_at = models.DateTimeField(null=True, blank=True)
    #: PCK-016: when the item was scanned while taking back – counted once, however often the code is read.
    returned_scan_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("item allocation")
        verbose_name_plural = _("item allocations")
        ordering = ["-issued_at"]
        indexes = [models.Index(fields=["item", "returned_at"], name="allocation_item_open_idx")]

    def __str__(self) -> str:
        return f"{self.item.display_id} → {self.entry.packlist.project.number}"

    @property
    def is_open(self) -> bool:
        """Whether the item is chosen or still out."""
        return self.returned_at is None

    @property
    def is_chosen_only(self) -> bool:
        """Chosen for the row, not issued yet (PCK-022)."""
        return self.issued_at is None


class Handover(models.Model):
    """Pieces that went straight from one subproject to the next (PRJ-060).

    Line T of part B takes over the pieces of line S of part A
    (``MaterialLine.taken_over_from``). When the pieces arrive at B, the
    handover is booked on B's packlist: for A they count as back
    (``source.handed_over_quantity``), for B as issued
    (``target.issued_quantity``). One record per booking, so that a booking
    can be taken back; see ``packing.subprojects``.
    """

    #: A's row: the entry of line S.
    source = models.ForeignKey(PackEntry, on_delete=models.CASCADE, related_name="handovers_out")
    #: B's row: the entry of line T.
    target = models.ForeignKey(PackEntry, on_delete=models.CASCADE, related_name="handovers_in")
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    handed_over_at = models.DateTimeField(default=timezone.now)
    handed_over_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = _("handover")
        verbose_name_plural = _("handovers")
        ordering = ["handed_over_at", "id"]

    def __str__(self) -> str:
        return f"{self.quantity} {self.source_id} → {self.target_id}"


class LineAssignment(models.Model):
    """Which packlist a material line goes on, if not the main one (PCK-008)."""

    line = models.OneToOneField(MaterialLine, on_delete=models.CASCADE, related_name="packlist_assignment")
    packlist = models.ForeignKey(Packlist, on_delete=models.CASCADE, related_name="assignments")

    class Meta:
        verbose_name = _("packing list assignment")
        verbose_name_plural = _("packing list assignments")

    def __str__(self) -> str:
        return f"{self.line_id} → {self.packlist_id}"


class Extraction(models.Model):
    """A loose item taken out of its container for one project (MAT-042).

    While the project runs, the item does not travel with the container: it
    counts as free for other projects (``availability.engine``), and the
    packlist of the container lists it as missing content.
    """

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="extractions")
    item = models.ForeignKey(MaterialItem, on_delete=models.CASCADE, related_name="extractions")
    #: The container the item was in when it was taken out.
    container = models.ForeignKey(MaterialItem, null=True, on_delete=models.SET_NULL, related_name="+")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = _("extracted content")
        verbose_name_plural = _("extracted contents")
        constraints = [models.UniqueConstraint(fields=["project", "item"], name="extraction_once_per_project")]

    def __str__(self) -> str:
        return f"{self.item_id} out of {self.container_id} for {self.project_id}"


class SyncReceipt(models.Model):
    """A change from the phone that the sync judged, by the change ID the phone gave it (PCK-027).

    If the answer to a sync is lost, the phone sends the same changes again.
    A change whose ID is known for the caller is not judged a second time:
    it gets the outcome it got the first time (``packing.offline``). The IDs
    belong to one user; receipts older than ``offline.RECEIPT_DAYS`` days
    are deleted by the next sync.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    change_id = models.CharField(max_length=64)
    packlist = models.ForeignKey(Packlist, on_delete=models.CASCADE, related_name="+")
    #: The row as plain numbers: the line may be deleted meanwhile.
    line = models.BigIntegerField()
    product = models.BigIntegerField()
    field = models.CharField(max_length=10)
    #: With the row and field: what makes a change sent again the same change (``offline._fingerprint``).
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    base_version = models.PositiveIntegerField(null=True, blank=True)
    outcome = models.CharField(max_length=10)
    message = models.CharField(max_length=250, blank=True)
    #: The reason code of the outcome (``needs_project_write`` …), so a change sent again gets it too.
    reason = models.CharField(max_length=30, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = _("synchronised change")
        verbose_name_plural = _("synchronised changes")
        constraints = [models.UniqueConstraint(fields=["user", "change_id"], name="sync_receipt_once")]

    def __str__(self) -> str:
        return f"{self.user_id}/{self.change_id}: {self.outcome}"
