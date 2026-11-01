# SPDX-License-Identifier: GPL-3.0-or-later
"""Turns raw audit log entries into readable history (MAT-025, PRJ-032, ADM-005).

The log stores field names and raw values (``{"status": ["available",
"defective"]}``). For people this module looks up the field's label, the
label of a choice, and the name behind a foreign key. It also drops the
values a reader is not allowed to see (AUT-019).
"""

from __future__ import annotations

import contextlib
import datetime
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.db import models
from django.utils import formats, timezone
from django.utils.dateparse import parse_date, parse_datetime, parse_time
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext_lazy

from rentalars.accounts.rights import Rights, SpecialRight
from rentalars.core.audit import AuditedModel
from rentalars.core.models import AuditAction, AuditLogEntry
from rentalars.core.money import format_decimal

#: Readable sentences for business events; ``%(name)s`` is filled from the details.
EVENT_TEXTS = {
    "user.invited": gettext_lazy("Invitation sent to %(email)s"),
    "user.roles_changed": gettext_lazy("Roles changed: %(before)s → %(after)s"),
    # AUT-029: login with LDAP / Active Directory (accounts/ldap_sync.py).
    "user.ldap_created": gettext_lazy("Account created at the first login with the directory (LDAP): %(dn)s"),
    "user.ldap_linked": gettext_lazy("Account linked to the directory (LDAP): %(dn)s"),
    "user.ldap_roles_changed": gettext_lazy("Roles changed by the directory (LDAP): %(before)s → %(after)s"),
    "user.ldap_deactivated": gettext_lazy("Account deactivated by the directory (LDAP): %(reason)s"),
    "user.ldap_reactivated": gettext_lazy("Account activated again by the directory (LDAP)"),
    "user.ldap_dn_adopted": gettext_lazy("Account linked to the new entry of the directory (LDAP): %(old)s → %(new)s"),
    "ldap.bind_password_stored": gettext_lazy("Password of the search account (LDAP) set"),
    "ldap.bind_password_removed": gettext_lazy("Password of the search account (LDAP) removed"),
    "ldap.bind_password_removed_moved": gettext_lazy(
        "Password of the search account (LDAP) removed: servers or account changed"
    ),
    "ldap_mapping.roles_changed": gettext_lazy("Roles of the group assignment changed: %(before)s → %(after)s"),
    # AUT-030: the notice "your login details were changed" (accounts/notices.py).
    "user.notice_email": gettext_lazy(
        "E-mail address changed from %(old)s to %(new)s; notice sent to the previous address"
    ),
    "user.notice_password": gettext_lazy("Password changed; notice sent to %(to)s"),
    "user.notice_password_reset": gettext_lazy("Password reset by link; notice sent to %(to)s"),
    "user.notice_one_time_password": gettext_lazy("One-time password set; notice sent to %(to)s"),
    # PCK-013: noted by the update for a role that packs in assigned projects only (accounts/0007).
    "role.no_material_while_packing": gettext_lazy(
        "%(name)s may no longer add material while packing: that needs the right to change the project or to pack "
        "for all projects."
    ),
    # AUT-031 (Crew): noted by the update for a role "Crew" the company had changed (accounts/0008).
    "role.crew_left_as_is": gettext_lazy(
        "%(name)s was changed by the company and keeps its project access: the update gave it the special "
        "right “See availability of material” only."
    ),
    # AUT-036: noted by the update for a role whose start rights the company had changed (accounts/0009).
    "role.defaults_left_as_is": gettext_lazy(
        "%(name)s was changed by the company and keeps its rights: the new start rights apply to a fresh "
        "installation only."
    ),
    "rental_scale.published": gettext_lazy("Table changed (version %(version)s)"),
    "item.content_added": gettext_lazy("Item %(item)s installed"),
    "item.content_removed": gettext_lazy("Item %(item)s removed"),
    # MAT-040 (built-in quantity material): bulk material built into an item or taken out again.
    "item.quantity_installed": gettext_lazy("%(quantity)s × %(item)s built in"),
    "item.quantity_removed": gettext_lazy("%(quantity)s × %(item)s taken out"),
    "item.quantity_built_in": gettext_lazy("%(quantity)s built into %(container)s"),
    "item.quantity_taken_out": gettext_lazy("%(quantity)s taken out of %(container)s"),
    # Used sale from stock: without amounts – the history is read by everyone who reads the material.
    # Review (R1-16): no buyer – the name of a buyer is a customer's personal data, not for every reader of the material.
    "item.sold_from_stock": gettext_lazy("Sold from stock on %(date)s (%(quantity)s)"),
    "item.sale_reversed": gettext_lazy("Sale from stock of %(date)s reversed"),
    # LOG-016: a model planned as material so far became vehicles of the fleet.
    "material_model.taken_into_fleet": gettext_lazy(
        "Taken into the fleet: product %(product)s instead of %(old_product)s"
    ),
    "customer.anonymised": gettext_lazy("Personal data erased"),
    # A summary by AI was made – never its content; "automatic" tells the nightly job from the button.
    "ai.summary_created": gettext_lazy("Summary by AI made on request (%(model)s, %(provider)s)"),
    "ai.summary_created_auto": gettext_lazy("Summary by AI made automatically (%(model)s, %(provider)s)"),
    "line.surcharge_targets_changed": gettext_lazy("Surcharge now refers to: %(targets)s"),
    "line.sold_stock_removed": ngettext_lazy(
        "%(quantity)s sold piece taken out of the stock", "%(quantity)s sold pieces taken out of the stock", "quantity"
    ),
    "group.copied": gettext_lazy("Copied from project %(from_project)s, group “%(from_group)s”"),
    "packlist.issued": gettext_lazy("Material issued"),
    # PRJ-131: the PDF of a service case for the customer was made and stored under "Documents".
    "case.customer_pdf_made": gettext_lazy("PDF for the customer made: %(file)s (%(messages)s messages)"),
    # Items booked in from an incoming invoice (incoming/booking.py).
    "incoming_invoice.booked": gettext_lazy("Booked in from the invoice: %(items)s"),
    "packlist.issue_undone": gettext_lazy("Issue taken back"),
    "packlist.returned": gettext_lazy("Return completed"),
    "packlist.missing_resolved": gettext_lazy("Missing parts clarified: %(quantity)s × %(product)s – %(note)s"),
    "import.material": gettext_lazy("Material import: %(created)s created, %(updated)s updated"),
    "setup.completed": gettext_lazy("First-run setup completed"),
    "user.expired": gettext_lazy("Account deactivated: it was valid until %(valid_until)s"),
    "person.anonymised": gettext_lazy("Personal data erased"),
    "user.anonymised": gettext_lazy("Account closed and personal data erased"),
    "crew_line.times_assigned": gettext_lazy(
        "%(entries)s approved time entries of %(person)s counted towards this line"
    ),
    "crew_line.adopted_from_times": gettext_lazy("Created from the approved times of %(person)s (%(hours)s h)"),
    "time_entry.approval_taken_back": gettext_lazy("Approval taken back"),
    # GWL-011: pairing an app and locking a device out, from the settings.
    "gateway.pairing_offered": gettext_lazy("Pairing code made for an app (%(device)s, valid %(minutes)s minutes)"),
    "gateway.device_revoked": gettext_lazy("App %(device)s of %(user)s locked out of the gateway"),
    # ZEI-030: corrected and approved in one step; the values before in one line.
    "time_entry.corrected": gettext_lazy("Corrected on approval – before: %(before)s; now: %(after)s"),
    # Stage 5
    "item.defect_reported": gettext_lazy("Another defect reported: %(description)s"),
    "item.extracted": gettext_lazy("Taken out of its container for project %(project)s"),
    "project.content_extracted": gettext_lazy("%(item)s taken out of %(container)s for this project"),
    "project.content_extraction_cancelled": gettext_lazy("%(item)s travels with its container again"),
    "item.taken_out": gettext_lazy("Taken out of %(container)s"),
    "item.put_back": gettext_lazy("Put back into %(container)s"),
    "packlist.partly_issued": ngettext_lazy(
        "Material partly issued: %(rows)s row", "Material partly issued: %(rows)s rows", "rows"
    ),
    "packlist.created": gettext_lazy("Packing list “%(title)s” created"),
    "packlist.addendum": gettext_lazy("Added while packing: %(quantity)s × %(product)s"),
    "packlist.defect_reported": gettext_lazy("Defect reported on return: %(item)s – %(description)s"),
    "packlist.items_chosen": gettext_lazy("Items chosen for %(product)s: %(items)s"),
    "packlist.changes_acknowledged": gettext_lazy("Changes of the planning acknowledged on the packing list"),
    # PRJ-060: material that goes straight from one subproject to the next
    "packlist.handed_over": gettext_lazy("Handover from %(project)s: %(quantity)s × %(product)s"),
    "packlist.handed_on": gettext_lazy("Handed over to %(project)s: %(quantity)s × %(product)s"),
    "packlist.handover_undone": gettext_lazy("Handover with %(project)s taken back: %(quantity)s × %(product)s"),
    "document.created": gettext_lazy("%(kind)s %(number)s created"),
    "document.draft_deleted": gettext_lazy("Draft of a %(kind)s without project deleted"),
    "document.sent": gettext_lazy("%(kind)s %(number)s sent to %(to)s"),
    "document.cancelled": gettext_lazy("%(kind)s %(number)s cancelled by %(cancellation)s"),
    "document.credited": gettext_lazy("%(kind)s %(number)s partly credited by %(cancellation)s"),
    "document.transferred": gettext_lazy("%(kind)s %(number)s handed to %(to)s"),  # DOK-011
    "import.records": gettext_lazy("Import of %(kind)s: %(created)s created, %(updated)s updated"),
    "export.full": gettext_lazy("Complete data export written"),
    # ADM-010
    "backup.web": gettext_lazy("Backup started in the browser"),
    # PER-032: the answer to a deployment request came by reply mail; only from the address the request went to.
    "crew_line.answered_by_mail": gettext_lazy("Answer of %(person)s came by reply mail"),
    # No answer from another address is taken over; the entries of the past
    # stay readable.
    "crew_line.answered_by_mail_from_other": gettext_lazy(
        "Answer of %(person)s came by reply mail from %(sender)s – not the address of the person"
    ),
    # PER-033, PER-034: asked again because the times changed – by hand or by itself.
    "crew_line.asked_again_new_times": gettext_lazy("%(person)s asked again for new times: %(new)s (before: %(old)s)"),
    # PER-038: a price offer of a freelancer sets the cost rate of the line, or stops doing so – no amounts.
    "crew_line.offer_applied": gettext_lazy("Price offer of %(person)s accepted: it sets the cost rate (%(unit)s)"),
    "crew_line.offer_released": gettext_lazy("Price offer of %(person)s no longer applies: %(reason)s"),
    # UIX-034: the position of an address on the map, corrected by hand or to be looked up again.
    "map.position_set": gettext_lazy("Position on the map set by hand: %(address)s"),
    "map.position_forgotten": gettext_lazy("Position on the map to be looked up again: %(address)s"),
    # PRJ-050: groups that became subprojects.
    "project.split": gettext_lazy("Divided into subprojects: %(parts)s"),
    "project.split_part": gettext_lazy(
        "Made from the group “%(group)s” of %(project)s: material lines: %(lines)s, crew lines: %(crew)s"
    ),
    # PRJ-090: a service case became a project.
    "service_case.converted": gettext_lazy("Service case turned into a project"),
    # DOK-016: billed with the monthly invoice of service cases that belongs to the first of them.
    "statement.invoiced": gettext_lazy("Billed with the monthly invoice %(number)s (%(month)s)"),
    # EML-051: a note in the correspondence; and the mails removed or moved (EML-015).
    "mail.note_added": gettext_lazy("Note in the correspondence: %(subject)s"),
    "mail.deleted": gettext_lazy("Mail removed from the correspondence: %(subject)s"),
    "mail.reassigned": gettext_lazy("Mail moved from %(from)s to %(to)s: %(subject)s"),
    # EML-053: inquiries noted by hand under Projekte → Anfragen.
    "inquiry.noted": gettext_lazy("Inquiry noted: %(subject)s"),
    "inquiry.changed": gettext_lazy("Inquiry changed: %(subject)s"),
    "inquiry.deleted": gettext_lazy("Inquiry deleted: %(subject)s"),
    # PRJ-119 (projects/relations.py): the number of the other side only (AUT-016).
    "project.related": gettext_lazy("Related to %(number)s"),
    "project.unrelated": gettext_lazy("No longer related to %(number)s"),
    "project.relation_deleted": gettext_lazy("No longer related to %(number)s: it was deleted"),
    # VFG-040 (schedule/calendar_links.py): the token itself is never logged.
    "calendar_link.created": gettext_lazy("Calendar link (iCalendar) created"),
    "calendar_link.renewed": gettext_lazy("New calendar link created; the old address no longer works"),
    "calendar_link.deactivated": gettext_lazy("Calendar link deactivated"),
    "calendar_link.ended": gettext_lazy("Calendar link deactivated: the record is no longer in use"),
    # Projects/legacy_import.py: an old project taken over from its invoices.
    "project.legacy_imported": gettext_lazy("Imported from the invoices %(invoices)s by %(user)s"),
}


@dataclass
class FieldChange:
    """One changed field, ready to display."""

    name: str
    label: str
    old: str
    new: str


@dataclass
class HistoryItem:
    """One audit log entry, ready to display."""

    entry: AuditLogEntry
    summary: str
    changes: list[FieldChange] = field(default_factory=list)
    #: EML-055: a neutral name instead of the stored one, for a reader who may not see that (``mail.history``).
    shown_name: str = ""

    @property
    def object_name(self) -> str:
        """The name of the changed object as the reader sees it: the stored one, unless it is hidden from him."""
        return self.shown_name or self.entry.object_repr

    @property
    def actor(self) -> str:
        """Who made the change, in the reader's language (UIX-029): a stored "Automation „Name“" follows it."""
        return actor_text(self.entry.actor_label)

    @property
    def object_label(self) -> str:
        """The kind of object, e.g. "Materialposition"."""
        model = self.entry.content_type.model_class()
        return str(model._meta.verbose_name) if model else self.entry.content_type.model


#: An automation as the author of a change, stored in the language the installation had then (UIX-029).
_AUTOMATION = re.compile(r"^Automation [„“\"](?P<name>.+)[“”\"]$")


def actor_text(label: str) -> str:
    """The author of an audit log entry for the reader: an automation's name in the reader's quotation marks."""
    match = _AUTOMATION.match(label or "")
    if match:
        return _("Automation “%(name)s”") % {"name": match.group("name")}
    return label


class _Lookup:
    """Remembers looked-up names of related objects while one page is built."""

    def __init__(self) -> None:
        self._names: dict[tuple[type[models.Model], Any], str] = {}

    def name_of(self, model: type[models.Model], pk: Any) -> str:
        """Return the display name of a related object, or its ID if it is gone.

        Some entries hold a readable text instead of an ID – the service product of crew lines and job functions as "D-001 …". Such a value is shown as it
        is instead of breaking the page (ADM-005).
        """
        key = (model, str(pk))
        if key not in self._names:
            try:
                value = model._meta.pk.to_python(pk)
            except (ValidationError, TypeError, ValueError):
                self._names[key] = str(pk)
                return self._names[key]
            related = model._default_manager.filter(pk=value).first()
            self._names[key] = str(related) if related is not None else f"#{pk}"
        return self._names[key]


def visible_changes(entry: AuditLogEntry, rights: Rights) -> dict[str, Any]:
    """Return the raw changes of an entry without the fields the reader may not see."""
    model = entry.content_type.model_class()
    sensitive = getattr(model, "audit_sensitive", {}) if model else {}
    if entry.action == AuditAction.EVENT or not isinstance(entry.changes, dict):
        return entry.changes if isinstance(entry.changes, dict) else {}
    # MAT-071: a model may hide more of one entry (``audit_hidden``) – custom values turned sensitive.
    hidden = model.audit_hidden(entry, rights) if hasattr(model, "audit_hidden") else frozenset()
    return {
        name: values
        for name, values in entry.changes.items()
        if name not in hidden and (name not in sensitive or rights.has(sensitive[name]))
    }


def _display(model: type[models.Model] | None, name: str, value: Any, lookup: _Lookup) -> tuple[str, str]:
    """Return label and readable value for one side of a field change."""
    empty = "–"
    if model is None:
        return name, empty if value in (None, "") else str(value)
    try:
        model_field = model._meta.get_field(name)
    except FieldDoesNotExist:
        return name, empty if value in (None, "") else str(value)
    label = str(getattr(model_field, "verbose_name", name))
    label = label[:1].upper() + label[1:]
    if value in (None, ""):
        return label, empty
    if isinstance(model_field, models.ForeignKey):
        return label, lookup.name_of(model_field.related_model, value)  # type: ignore[arg-type]
    if getattr(model_field, "choices", None):
        return label, str(dict(model_field.flatchoices).get(value, value))  # type: ignore[union-attr]
    if isinstance(model_field, models.BooleanField):
        return label, _("yes") if value else _("no")
    if isinstance(model_field, models.DateTimeField):
        moment = parse_datetime(str(value))
        if moment is not None:
            if timezone.is_aware(moment):
                moment = timezone.localtime(moment)
            return label, formats.date_format(moment, "SHORT_DATETIME_FORMAT")
    if isinstance(model_field, models.DateField):
        day = parse_date(str(value))
        if isinstance(day, datetime.date):
            return label, formats.date_format(day, "SHORT_DATE_FORMAT")
    if isinstance(model_field, models.TimeField):
        # UIX-029: a time of day as hours and minutes ("17:30"), not as stored ("17:30:00").
        time = parse_time(str(value))
        if time is not None:
            return label, time.strftime("%H:%M")
    if isinstance(model_field, models.DecimalField):
        try:
            return label, formats.number_format(Decimal(str(value)), use_l10n=True)
        except InvalidOperation:
            pass
    if isinstance(value, dict | list):
        return label, _("(changed)")
    return label, str(value)


#: Values of event texts that are numbers stored as text (``"5.50"``): written in the language of the reader.
NUMBER_KEYS = frozenset({"hours", "km"})

#: Events that only readers with a special right may read (AUT-019); others see that something changed, not what.
#: Review: a price offer of a freelancer is negotiation of personnel costs – the project's readers
#: need not learn that one took place, with whom, or why it ended.
EVENT_RIGHTS = {
    "crew_line.offer_applied": SpecialRight.PERSONNEL_COSTS,
    "crew_line.offer_released": SpecialRight.PERSONNEL_COSTS,
}


def describe(entries: list[AuditLogEntry], rights: Rights) -> list[HistoryItem]:
    """Prepare audit log entries for display.

    Args:
        entries: The entries, usually one page of a history.
        rights: The rights of the reader; decide which values are shown.
    """
    lookup = _Lookup()
    items: list[HistoryItem] = []
    for entry in entries:
        model = entry.content_type.model_class()
        if entry.action == AuditAction.EVENT:
            needed = EVENT_RIGHTS.get(entry.event)
            if needed is not None and not rights.has(needed):
                items.append(HistoryItem(entry=entry, summary=_("changed (details not visible)")))
                continue
            template = EVENT_TEXTS.get(entry.event)
            details = entry.changes if isinstance(entry.changes, dict) else {}
            printable = {
                key: ", ".join(str(part) for part in value) if isinstance(value, list) else value
                for key, value in details.items()
            }
            for key in NUMBER_KEYS & printable.keys():
                # B9: "5.50" is stored; the reader gets "5,5" (German) or "5.5" (English).
                with contextlib.suppress(InvalidOperation, ValueError):
                    printable[key] = format_decimal(Decimal(str(printable[key])))
            try:
                summary = str(template % printable) if template else entry.event
            except (KeyError, TypeError, ValueError):
                summary = entry.event
            items.append(HistoryItem(entry=entry, summary=summary))
            continue

        item = HistoryItem(entry=entry, summary=str(entry.get_action_display()))
        if entry.action == AuditAction.UPDATED:
            for name, values in visible_changes(entry, rights).items():
                if not isinstance(values, list) or len(values) != 2:
                    continue
                label, old = _display(model, name, values[0], lookup)
                _label, new = _display(model, name, values[1], lookup)
                item.changes.append(FieldChange(name=name, label=label, old=old, new=new))
            if not item.changes:
                # Every changed field is hidden from this reader.
                hidden_only = isinstance(model, type) and issubclass(model, AuditedModel) and bool(entry.changes)
                if hidden_only:
                    item.summary = _("changed (details not visible)")
        items.append(item)
    return items
