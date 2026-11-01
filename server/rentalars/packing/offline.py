# SPDX-License-Identifier: GPL-3.0-or-later
"""Packlists on the phone, without network (PCK-026, PCK-027).

The Android app (chapter 5.16) loads the packlists of the confirmed projects
that are not finished yet, ticks them without network and sends what was
ticked as soon as the server can be reached. This module answers both
sides: which packlists the caller may take along (:func:`offline_projects`),
and how the ticks from the phone are taken over (:func:`apply_changes`).

Which packlists (PCK-026)
-------------------------
Reading the list creates nothing. A project gets its main packlist
when it becomes confirmed – or is created confirmed – however that happens
(:func:`ensure_packlist_on_confirmation`, a signal). A project that still has
none is listed with an empty ``packlists``.

The rule of the sync (PCK-027)
------------------------------
Each row has two quantities that can be ticked: ``packed`` and
``returned``. The server notes for each when it last changed
(``PackEntry.packed_changed_at``, ``returned_changed_at``), on whatever way
it changed, and counts the changes of both in ``PackEntry.version``
. Every row of a packlist shows its ``version``.

*With* ``base_version`` – the version of the row the phone saw when it
loaded the packlist – the version decides: if the row's version
is still the same at the start of the sync, the change counts; if
somebody changed the row in between, it is a ``conflict`` and the server's
state stays – unless the server already has the quantity the phone wants,
then it is ``applied`` with nothing to do. Nothing is silently lost: every
result carries the server's ``version``, quantity and moment of the row
after the sync, so the phone can show the conflict and ask again.

*Without* ``base_version`` (older apps), the moments decide. A change
from the phone carries the moment it was made, in the time of the server
(APP-005). It counts only if it is *later* than the last change of the same
quantity on the server; at the same moment the server wins. The clock rule
:

* The clock of the sync is read once the packlist is locked, so that no
  change of the server that came before the sync is later than it.
* A moment in the future counts as that clock ("now") – a phone whose
  clock runs ahead cannot win against later changes on the server.
* The changes of one sync are taken in the order of their moments; changes
  whose moments both lie in the future keep their order among themselves
  (by the moment the phone gave), and equal moments keep the order of the
  request. Within one sync, a change of a quantity that a change before it
  in this order already set counts as the later one – so of several
  changes of one quantity, the latest remains, also when both lay in the
  future.
* An older change never overrides a newer one: against the server, only a
  strictly later moment counts.

The moment that is stored is never earlier than the one stored before.

Change IDs: a change may carry a ``change_id`` (a UUID, at most 64
characters). The sync notes the outcome per user and ID
(:class:`~rentalars.packing.models.SyncReceipt`); a change sent again with
an ID already judged gets the same outcome, marked ``replayed``, and is
not judged again. Receipts are kept for :data:`RECEIPT_DAYS` days.

A change that counts must still be allowed – with the limits of ticking in
the browser (PCK-028): ``packed`` only before the row went out completely,
from what is issued up to what is needed; ``returned`` only while material
is out, from what is taken back already up to what was issued and not handed
over to another subproject. Anything else is refused with the reason (a packed quantity above the packing list with the code ``needs_project_write``
or ``above_packing_list``, see :data:`NEEDS_PROJECT_WRITE`). The
sync never issues and never books a return: that stays a step in the
browser. ``packing.returned`` goes to the webhooks only if a change raised
a returned quantity – as for a tick in the browser.

The rows of the packlist that a sync touches are locked from the comparison
until the end of the sync (``select_for_update``), so that no change in
between gets lost.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Level, Module, Rights
from rentalars.api import webhooks
from rentalars.packing import services
from rentalars.packing.models import PackEntry, Packlist, SyncReceipt
from rentalars.projects.access import ProjectAccess, access_of_many, assigned_filter, visible_projects
from rentalars.projects.models import FIRM_STATUSES, Project

ZERO = Decimal("0")

#: PCK-026: the projects whose packlists go on the phone – confirmed and not finished.
OFFLINE_STATUSES = FIRM_STATUSES

#: The most changes one sync takes; the app sends at most 400 at a time.
MAX_CHANGES = 1000

#: The two quantities the phone ticks, each with the field that notes its last change.
FIELDS = {"packed": ("packed_quantity", "packed_changed_at"), "returned": ("returned_quantity", "returned_changed_at")}

APPLIED, OLDER, REFUSED, CONFLICT = "applied", "older", "refused", "conflict"
OUTCOMES = (APPLIED, OLDER, REFUSED, CONFLICT)

#: PCK-027: how long the outcome of a change is kept by its change ID.
RECEIPT_DAYS = 30

#: The longest change ID.
MAX_CHANGE_ID = 64


# --- What goes on the phone (PCK-026) -------------------------------------------------------------


@dataclass
class OfflineProject:
    """A project whose packlists the caller may take along, with what the caller may do there."""

    project: Project
    packlists: list[Packlist]
    can_write: bool
    #: PRJ-122: the customer's name – in every role.
    shows_customer: bool
    #: PCK-013: whether the caller may add material while packing (``services.may_add_material``).
    can_add_material: bool = False


def offline_projects(rights: Rights, user: Any) -> list[OfflineProject]:
    """The confirmed projects that are not finished, whose packlist the caller may see (PCK-026).

    The rule is the one of opening a packlist (``projects.access.packlist_project_for``,
    AUT-016, AUT-025): whoever has "packing" for all projects sees every
    packlist; whoever has it for assigned projects only sees those of the
    projects they are assigned to – and needs to see the project at all.
    A handful of queries, however many projects there are (NFA-014). Reads
    only (PCK-026): see the module documentation.
    """
    everywhere = rights.level_everywhere(Module.PACKING)
    in_assigned = rights.level(Module.PACKING)
    projects = Project.objects.filter(status__in=OFFLINE_STATUSES).select_related("customer", "venue_site")
    if everywhere < Level.READ:
        if in_assigned < Level.READ:
            return []
        # Packing only where assigned – and the project must be visible as well.
        projects = visible_projects(rights, user, projects).filter(assigned_filter(user))
    projects = list(projects.order_by("start", "number"))
    if not projects:
        return []
    ids = [project.pk for project in projects]
    access = access_of_many(rights, user, ids)
    assigned: set[int] = set()
    if in_assigned > everywhere:
        assigned = set(Project.objects.filter(pk__in=ids).filter(assigned_filter(user)).values_list("pk", flat=True))
    by_project: dict[int, list[Packlist]] = {project_id: [] for project_id in ids}
    for packlist in Packlist.objects.filter(project_id__in=ids).order_by("id"):
        by_project[packlist.project_id].append(packlist)
    result = []
    for project in projects:
        packlists = by_project[project.pk]
        level = in_assigned if project.pk in assigned else everywhere
        result.append(
            OfflineProject(
                project=project,
                packlists=packlists,
                can_write=level >= Level.WRITE,
                shows_customer=True,
                # PCK-013: the rule of ``services.may_add_material``, from what was read above.
                can_add_material=level >= Level.WRITE
                and (everywhere >= Level.WRITE or access.get(project.pk, ProjectAccess.NONE) >= ProjectAccess.EDIT),
            )
        )
    return result


def ensure_packlist_on_confirmation(
    sender: Any, instance: Project, created: bool = False, raw: bool = False, **kwargs: Any
) -> None:
    """A project that becomes confirmed – or is created so – gets its main packlist (PCK-026).

    Connected to ``post_save`` of the project in ``packing.apps``. Before
    The list for the phone created missing packlists while it was
    read; now they come into being where the status is written, logged in
    the change log like a packlist created by hand. One query for a project
    that has its packlist already, none for a save that leaves the status.
    """
    if raw or instance.status not in OFFLINE_STATUSES:
        return
    update_fields = kwargs.get("update_fields")
    if update_fields is not None and "status" not in update_fields:
        return
    if not created:
        # The values before this save, as the change log keeps them; None for a hand-built object.
        before = instance._audit_before() if hasattr(instance, "_audit_before") else None
        if before and before.get("status") in OFFLINE_STATUSES:
            return
    services.ensure_main_packlists([instance])


# --- Taking over what was ticked on the phone (PCK-027) -------------------------------------------


@dataclass
class Change:
    """One change from the phone: a quantity of a row, and when it was made.

    ``base_version``: the version of the row the phone saw; with it,
    the version decides instead of the moment. ``change_id``: the
    phone's ID of the change, for a replay that is not judged twice.
    """

    line: int
    product: int
    field: str
    quantity: Decimal
    changed_at: datetime.datetime
    base_version: int | None = None
    change_id: str = ""


@dataclass
class Result:
    """What became of one change: ``applied``, ``older``, ``refused`` or ``conflict``, with the reason.

    With the state of the row's quantity on the server after the sync
    (``version``, ``server_quantity``, ``server_changed_at``), the
    ``change_id`` sent, and whether the outcome is that of an earlier sync
    (``replayed``). ``reason`` is a code for programs: ``change_id_reused``
    for a change ID already used for a different change.
    """

    line: int
    product: int
    field: str
    outcome: str
    message: str = ""
    change_id: str = ""
    replayed: bool = False
    version: int = 0
    server_quantity: Decimal = ZERO
    server_changed_at: datetime.datetime | None = None
    reason: str = ""


#: PCK-027: the reason of a change whose ID was already used for a different change.
CHANGE_ID_REUSED = "change_id_reused"

#: The reasons of a packed quantity above the packing list – refused for everybody. More
#: material is added while packing (PCK-013): ``needs_project_write`` for a caller who may not do that (crew, which
#: packs 1:1 what is planned), ``above_packing_list`` for one who may – in the browser or ``…/add-material``.
NEEDS_PROJECT_WRITE = "needs_project_write"
ABOVE_PACKING_LIST = "above_packing_list"


def _fingerprint(packlist_id: int, change: Change) -> tuple[Any, ...]:
    """What makes two changes with one ID the same change: packlist, row, quantity, field and base version."""
    return (packlist_id, change.line, change.product, change.field, Decimal(change.quantity), change.base_version)


@dataclass
class _Sync:
    """The state of one sync while its changes are judged."""

    packlist: Packlist
    overview: services.PackOverview
    rows: dict[tuple[int, int], services.PackRow]
    entries: dict[tuple[int, int], PackEntry]
    #: The version of each row at the start of the sync – what ``base_version`` is compared with.
    start_versions: dict[tuple[int, int], int]
    #: The quantities set by a change of this sync: a later change of the same quantity counts.
    set_here: set[tuple[int, int, str]]
    now: datetime.datetime
    user: Any
    #: Whether the caller may add material (``services.may_add_material``) – it names the reason of a refusal.
    may_add_material: bool = True


def sort_key(change: Change, index: int, now: datetime.datetime) -> tuple[datetime.datetime, datetime.datetime, int]:
    """The order in which the changes of one sync are taken (PCK-027, the clock rule).

    The moment, a future one counted as ``now``; among equal moments – two
    future ones – the moment the phone gave; then the order of the request.
    """
    return (min(change.changed_at, now), change.changed_at, index)


def apply_changes(
    packlist: Packlist, changes: list[Change], *, user: Any = None, may_add_material: bool = True
) -> list[Result]:
    """Take over the changes of one sync; the results in the order of the changes (PCK-027).

    See the module documentation for the rule. Every change is judged on
    its own: one that is refused, older or in conflict does not stop the
    others. ``may_add_material``: whether the caller may add
    material while packing; it decides the ``reason`` of a packed quantity
    above the packing list (:data:`NEEDS_PROJECT_WRITE`,
    :data:`ABOVE_PACKING_LIST`).
    """
    results: list[Result | None] = [None] * len(changes)
    with transaction.atomic():
        packlist = Packlist.objects.select_for_update().get(pk=packlist.pk)
        # The clock of the sync, read under the lock: every change the server took before is not later.
        now = timezone.now()
        receipts = _receipts(user, changes)
        overview = services.build_overview(packlist)
        rows = {(row.line.pk, row.product.pk): row for row in overview.rows}
        lines = {change.line for change in changes if (change.line, change.product) in rows}
        entries = {
            (entry.line_id, entry.product_id): entry
            for entry in PackEntry.objects.select_for_update().filter(packlist=packlist, line_id__in=lines)
        }
        sync = _Sync(
            packlist=packlist,
            overview=overview,
            rows=rows,
            entries=entries,
            start_versions={key: entry.version for key, entry in entries.items()},
            set_here=set(),
            now=now,
            user=user,
            may_add_material=may_add_material,
        )
        judged: dict[str, tuple[tuple[Any, ...], Result]] = {}
        new_receipts: list[SyncReceipt] = []
        packed_applied = returned_more = False
        for index in sorted(range(len(changes)), key=lambda index: sort_key(changes[index], index, now)):
            change = changes[index]
            if change.change_id and change.change_id in judged:
                # The same ID twice in one sync: judged once.
                fingerprint, first = judged[change.change_id]
                results[index] = _replayed(
                    packlist.pk, change, first.outcome, first.message, fingerprint, reason=first.reason
                )
                continue
            receipt = receipts.get(change.change_id) if change.change_id else None
            if receipt is not None:
                results[index] = _replayed(
                    packlist.pk,
                    change,
                    receipt.outcome,
                    receipt.message,
                    (
                        receipt.packlist_id,
                        receipt.line,
                        receipt.product,
                        receipt.field,
                        receipt.quantity,
                        receipt.base_version,
                    ),
                    reason=receipt.reason,
                )
                continue
            key = (change.line, change.product)
            entry = sync.entries.get(key)
            before = getattr(entry, FIELDS[change.field][0]) if entry is not None and change.field in FIELDS else ZERO
            outcome, message, reason = _judge(sync, change)
            result = Result(
                change.line, change.product, change.field, outcome, message, change.change_id, reason=reason
            )
            results[index] = result
            if outcome == APPLIED:
                quantity = getattr(sync.entries[key], FIELDS[change.field][0]) if key in sync.entries else before
                packed_applied = packed_applied or change.field == "packed"
                # As for a tick in the browser: an event only if more came back (API-012).
                returned_more = returned_more or (change.field == "returned" and quantity > before)
            if change.change_id:
                judged[change.change_id] = (_fingerprint(packlist.pk, change), result)
                if getattr(user, "pk", None):
                    new_receipts.append(
                        SyncReceipt(
                            user=user,
                            change_id=change.change_id,
                            packlist=packlist,
                            line=change.line,
                            product=change.product,
                            field=change.field,
                            quantity=change.quantity,
                            base_version=change.base_version,
                            outcome=outcome,
                            message=message[:250],
                            reason=reason,
                            created_at=now,
                        )
                    )
        if packed_applied:
            services._derive_packing_status(packlist)
        if returned_more:
            webhooks.record("packing.returned", packlist)  # API-012, as for a tick in the browser
        if new_receipts:
            SyncReceipt.objects.bulk_create(new_receipts, ignore_conflicts=True)
        SyncReceipt.objects.filter(created_at__lt=now - datetime.timedelta(days=RECEIPT_DAYS)).delete()
        after = {
            (entry.line_id, entry.product_id): entry
            for entry in PackEntry.objects.filter(packlist=packlist, line_id__in={change.line for change in changes})
        }
    final = [result for result in results if result is not None]
    for result in final:
        _add_server_state(result, after.get((result.line, result.product)))
    return final


def _receipts(user: Any, changes: list[Change]) -> dict[str, SyncReceipt]:
    """The receipts of the caller for the change IDs of this sync (PCK-027)."""
    ids = {change.change_id for change in changes if change.change_id}
    if not ids or not getattr(user, "pk", None):
        return {}
    return {receipt.change_id: receipt for receipt in SyncReceipt.objects.filter(user=user, change_id__in=ids)}


def _replayed(
    packlist_id: int, change: Change, outcome: str, message: str, judged: tuple[Any, ...], *, reason: str = ""
) -> Result:
    """The outcome of a change sent again with a known ID (PCK-027).

    ``judged`` is the fingerprint of the change the ID was judged for
    (:func:`_fingerprint`). Only the very same change – packlist, row, field,
    quantity and base version alike – gets the outcome again, with its reason
    code; any difference is refused with the reason
    ``change_id_reused`` and nothing is applied, as an idempotency key used
    for another request (API-010).
    """
    if tuple(judged) != _fingerprint(packlist_id, change):
        return Result(
            change.line,
            change.product,
            change.field,
            REFUSED,
            _("This change ID was already used for another change."),
            change.change_id,
            reason=CHANGE_ID_REUSED,
        )
    return Result(change.line, change.product, change.field, outcome, message, change.change_id, True, reason=reason)


def _add_server_state(result: Result, entry: PackEntry | None) -> None:
    """The state of the row's quantity on the server after the sync (PCK-027)."""
    if entry is None or result.field not in FIELDS:
        return
    quantity_field, time_field = FIELDS[result.field]
    result.version = entry.version
    result.server_quantity = getattr(entry, quantity_field)
    result.server_changed_at = getattr(entry, time_field)


def _judge(sync: _Sync, change: Change) -> tuple[str, str, str]:
    """Compare one change with the server and apply it if it counts; returns outcome, message and reason code."""
    row = sync.rows.get((change.line, change.product))
    if row is None:
        return REFUSED, _("This row is not on the packing list (any more)."), ""
    key = (change.line, change.product)
    quantity_field, time_field = FIELDS[change.field]
    moment = min(change.changed_at, sync.now)
    entry = sync.entries.get(key)
    stored = getattr(entry, time_field) if entry is not None else None
    if change.base_version is not None:
        # The version the phone saw decides, not the moment.
        if change.base_version != sync.start_versions.get(key, 0):
            current = getattr(entry, quantity_field) if entry is not None else ZERO
            if change.quantity == current:
                return APPLIED, "", ""  # the server has what the phone wants
            message = _("Changed on the server in the meantime; there it is %(count)s now.") % {
                "count": services._number(current)
            }
            return CONFLICT, message, ""
        if stored is not None and moment <= stored:
            moment = max(stored, sync.now)  # the stored moment never goes back
    elif (*key, change.field) not in sync.set_here and stored is not None and moment <= stored:
        return OLDER, _("A later change on the server counts."), ""
    elif stored is not None and moment < stored:
        moment = stored  # a later change of this sync with an equal moment
    refusal = _refusal(sync.packlist, row, change, entry)
    if refusal:
        reason = ""
        if change.field == "packed" and change.quantity > row.required and refusal == _needed(row):
            # More than the packing list is material to add (PCK-013) – crew packs 1:1 what is planned.
            if sync.may_add_material:
                reason = ABOVE_PACKING_LIST
            else:
                reason, refusal = NEEDS_PROJECT_WRITE, f"{refusal} {services.may_not_add_material_text()}"
        return REFUSED, refusal, reason
    if change.field == "packed" and sync.packlist.packing_started_at is None:
        services._start_packing(sync.packlist, sync.overview)
    if entry is None:
        created = services._entry_for(sync.packlist, row)
        entry = PackEntry.objects.select_for_update().get(pk=created.pk)
        sync.entries[key] = entry
    # The moment of the phone is kept even if the quantity stays the same: a later change counts from it.
    setattr(entry, time_field, moment)
    setattr(entry, quantity_field, change.quantity)
    entry.change_time = moment
    entry.updated_by = sync.user
    # Only these fields: starting to pack may have noted the row's text and quantity meanwhile (PCK-015).
    entry.save(update_fields=[quantity_field, time_field, "updated_by", "updated_at"])
    sync.set_here.add((*key, change.field))
    return APPLIED, "", ""


def _needed(row: services.PackRow) -> str:
    """The refusal of a packed quantity above the packing list."""
    return _("Only %(count)s are needed.") % {"count": services._number(row.required)}


def _refusal(packlist: Packlist, row: services.PackRow, change: Change, entry: PackEntry | None) -> str:
    """Why a change is not allowed, with the limits of ticking in the browser (PCK-028); ``""`` if it is."""
    issued = entry.issued_quantity if entry is not None else ZERO
    quantity = change.quantity
    if change.field == "packed":
        if not packlist.can_be_packed:
            return _("The material has already been issued. Packing can no longer be changed.")
        if row.is_takeover:
            return _("These pieces come from another subproject, not from the warehouse.")
        if quantity > row.required:
            return _needed(row)
        if quantity < issued:
            return _("%(count)s of it are issued already.") % {"count": services._number(issued)}
        return ""
    if not packlist.is_out:
        return _("Returns can only be booked while the material is out.")
    if row.is_sale:
        return _("Sold material is not returned.")
    taken_back = entry.taken_back_quantity if entry is not None else ZERO
    handed_over = entry.handed_over_quantity if entry is not None else ZERO
    returnable = max(issued - handed_over, ZERO)
    if quantity < taken_back:
        return _("%(count)s of it are taken back already.") % {"count": services._number(taken_back)}
    if quantity > returnable:
        return _("Only %(count)s of it are out.") % {"count": services._number(returnable)}
    return ""
