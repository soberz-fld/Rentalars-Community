# SPDX-License-Identifier: GPL-3.0-or-later
"""Calendar links of products, material models and items (VFG-040; VFG-019, PER-023).

The requirement: .ics links per product, model or item. By default no separate calendar is active; on the page of a record the creation of the link can be switched on (and off again).

The link
    By default a record has none. On its page (or through the API) whoever
    may change the record creates one: a secret address with 256 random bits
    (:func:`create_link`), like the subscription link of a person's
    deployments (PER-023). A new link ends the old one at once;
    "deactivate" ends it without a new one (:func:`deactivate_link`). Each of
    the three is an event in the history of the record. The token never
    enters the change log, nor the data export.

Who
    Seeing whether a link is active needs read access to the module of the
    record (products for a product, material for a model or an item);
    changing it – and seeing its address – write access. As the calendar
    holds the bookings with project names, both also need what the timeline
    needs – the special right to see the availability of material (AUT-032)
    – and the right to read every project (AUT-016): otherwise the address
    would show a reader the projects his pages hide from him (:func:`may_see`,
    :func:`may_manage`). The address works without login and lives until
    somebody renews or deactivates it; a reader could not end it, so he does
    not get it (readers with an address they cannot revoke).

What the calendar holds
    What the record's timeline shows, as exact appointments, from
    :data:`FEED_PAST` ago to :data:`FEED_FUTURE` ahead:

    * a **product**: its bookings in projects – one appointment per line with
      quantity, project number and name, status, the period with the buffers
      before and after (as the timeline) – and its blocked items;
    * a **material model**: the same for the product(s) of its items;
    * an **item**: when it is out with a project or chosen for a packing list,
      wished for on a line, travelling with its container or taken out of it,
      blocked, and when an inspection is due (``timelines.item_events``).

    No prices, no customers, no contact data, no places: the address works
    without login, so it holds what the warehouse may know. Every appointment
    has a UID that stays while the booking changes, so calendar programs
    update it instead of adding a second one.

The address works only while the record is in use: a deactivated product or
an item that was retired, sold or lost answers "not found", and saving it so
deactivates the link for good (:func:`subject_archived`). A deleted record
takes its link along.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import secrets
from collections import defaultdict
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models.signals import post_save
from django.http import Http404
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from rentalars.accounts.rights import Level, Module, Rights, SpecialRight
from rentalars.core.audit import record_event
from rentalars.schedule.models import CalendarLink

#: The appointments of a calendar: from this long ago ...
FEED_PAST = datetime.timedelta(days=90)
#: ... to this far ahead.
FEED_FUTURE = datetime.timedelta(days=730)
#: How often calendar programs are asked to read the calendar again.
REFRESH = datetime.timedelta(minutes=30)

PRODUCT, MODEL, ITEM = "product", "model", "item"
#: The kinds of records with a calendar link, as they appear in the address.
KINDS = (PRODUCT, MODEL, ITEM)
#: The field of :class:`CalendarLink` that holds a record of each kind.
_FIELDS = {PRODUCT: "product", MODEL: "material_model", ITEM: "item"}
#: What :func:`link_for_token` loads with the link, so that the calendar asks no more than it must.
_RELATED = {
    PRODUCT: ("product__category",),
    MODEL: ("material_model",),
    ITEM: ("item__material_model__category",),
}

#: The events in the history of the record (``core.history.EVENT_TEXTS``).
CREATED, RENEWED, DEACTIVATED, ENDED = (
    "calendar_link.created",
    "calendar_link.renewed",
    "calendar_link.deactivated",
    "calendar_link.ended",
)


# --- Records and rights ------------------------------------------------------------------------------------


def kind_of(subject: models.Model) -> str:
    """``product``, ``model`` or ``item`` for a record that can have a calendar link."""
    from rentalars.material.models import MaterialItem, MaterialModel
    from rentalars.products.models import Product

    if isinstance(subject, Product):
        return PRODUCT
    if isinstance(subject, MaterialModel):
        return MODEL
    if isinstance(subject, MaterialItem):
        return ITEM
    raise TypeError(f"no calendar link for {type(subject).__name__}")


def module_of(kind: str) -> str:
    """The module whose rights decide about the link of a record of this kind."""
    return Module.PRODUCTS if kind == PRODUCT else Module.MATERIAL


def subject_for(kind: str, pk: Any) -> models.Model:
    """The record of a kind with this ID, or "not found"."""
    from rentalars.material.models import MaterialItem, MaterialModel
    from rentalars.products.models import Product

    queryset: Any = {
        PRODUCT: Product.objects.select_related("category"),
        MODEL: MaterialModel.objects.all(),
        ITEM: MaterialItem.objects.select_related("material_model__category"),
    }.get(kind)
    if queryset is None:
        raise Http404
    try:
        return queryset.get(pk=pk)
    except (queryset.model.DoesNotExist, ValueError, TypeError):
        raise Http404 from None


def may_see(rights: Rights, kind: str) -> bool:
    """Whether someone may see if the calendar link of a record of this kind is active, and what it shows.

    Read access to the module, and what the calendar shows needs anyway:
    the availability of material (AUT-032) and every project (AUT-016).
    The address itself only whoever may also change the link
    (:func:`may_manage`; VFG-040): it works without login, and
    a reader who copied it could not end it.
    """
    return (
        rights.can_read(module_of(kind))
        and rights.has(SpecialRight.AVAILABILITY)
        and rights.level_everywhere(Module.PROJECTS) >= Level.READ
    )


def may_manage(rights: Rights, kind: str) -> bool:
    """Whether someone may create, renew and deactivate the calendar link of a record of this kind – and see its address."""
    return may_see(rights, kind) and rights.can_write(module_of(kind))


def _archived(subject: models.Model) -> bool:
    """Whether the record is out of use: a deactivated product, an item retired, sold or lost."""
    kind = kind_of(subject)
    if kind == PRODUCT:
        return not subject.is_active  # type: ignore[attr-defined]
    if kind == ITEM:
        return subject.is_archived  # type: ignore[attr-defined]
    return False


def unavailable_reason(subject: models.Model) -> str:
    """Why the record cannot get a calendar link, or an empty text if it can."""
    kind = kind_of(subject)
    if kind == PRODUCT:
        if not subject.is_active:  # type: ignore[attr-defined]
            return _("A deactivated product has no calendar link.")
        if not subject.tracks_stock:  # type: ignore[attr-defined]
            return _("This product has no stock of its own; a calendar of it would stay empty.")
    if kind == ITEM and _archived(subject):
        return _("An item that was retired, sold or lost has no calendar link.")
    return ""


def shows(kind: str) -> str:
    """What the calendar of a record of this kind shows, in one or two sentences for its page and the API."""
    if kind == ITEM:
        return _(
            "The calendar shows when this item is out with a project or chosen for a packing list, wished for on "
            "a line, travelling with its container or taken out of it, when it is blocked and when an inspection "
            "is due – with project number, project name and status. Bookings of the product that name no item "
            "are in the calendar of the product."
        )
    if kind == MODEL:
        return _(
            "The calendar shows the bookings of the product of this model in projects – project number and name, "
            "status, quantity and the period with the buffers before and after – and its blocked items."
        )
    return _(
        "The calendar shows the bookings of this product in projects – project number and name, status, quantity "
        "and the period with the buffers before and after – and its blocked items."
    )


# --- Creating, renewing, deactivating ----------------------------------------------------------------------


def link_of(subject: models.Model) -> CalendarLink | None:
    """The calendar link of a record if one works now, else ``None``."""
    link = CalendarLink.objects.filter(**{_FIELDS[kind_of(subject)]: subject}).exclude(token="").first()
    if link is None or _archived(subject):
        return None
    return link


def create_link(subject: models.Model, *, user: Any = None) -> tuple[CalendarLink, bool]:
    """Create the calendar link of a record, or a new one; the old address stops working at once.

    Returns:
        The link and whether it replaced one that worked until now.

    Raises:
        ValidationError: The record cannot have a link (:func:`unavailable_reason`).
    """
    reason = unavailable_reason(subject)
    if reason:
        raise ValidationError(reason)
    field = _FIELDS[kind_of(subject)]
    with transaction.atomic():
        link, _created = CalendarLink.objects.select_for_update().get_or_create(**{field: subject})
        renewed = link.is_active
        link.token = secrets.token_urlsafe(32)
        link.created_at = timezone.now()
        link.created_by = user if getattr(user, "is_authenticated", False) else None
        link.save()
        record_event(subject, RENEWED if renewed else CREATED)
    setattr(link, field, subject)
    return link, renewed


def deactivate_link(subject: models.Model, *, event: str = DEACTIVATED) -> bool:
    """End the calendar link of a record at once; ``False`` if none worked."""
    ended = (
        CalendarLink.objects.filter(**{_FIELDS[kind_of(subject)]: subject})
        .exclude(token="")
        .update(token="", created_at=None, created_by=None)
    )
    if ended:
        record_event(subject, event)
    return bool(ended)


def subject_archived(sender: Any, instance: Any, **kwargs: Any) -> None:
    """A product deactivated, an item retired, sold or lost: its calendar link ends for good."""
    if not kwargs.get("raw") and _archived(instance):
        deactivate_link(instance, event=ENDED)


def connect_signals() -> None:
    """Let products and items end their calendar links when they go out of use (called by the app)."""
    post_save.connect(subject_archived, sender="products.Product", dispatch_uid="calendar_link_product")
    post_save.connect(subject_archived, sender="material.MaterialItem", dispatch_uid="calendar_link_item")


# --- The address -------------------------------------------------------------------------------------------


def _subject_id(link: CalendarLink) -> int:
    """The ID of the record of a link, without loading the record."""
    return link.product_id or link.material_model_id or link.item_id  # type: ignore[return-value]


def _kind_of_link(link: CalendarLink) -> str:
    """The kind of the record of a link, without loading the record."""
    if link.product_id:
        return PRODUCT
    return MODEL if link.material_model_id else ITEM


def feed_path(link: CalendarLink) -> str:
    """The path of the calendar, ``/calendar-feed/item/42/<token>.ics``; empty without a working link."""
    if not link.token:
        return ""
    return reverse("schedule:calendar_link_feed", args=[_kind_of_link(link), _subject_id(link), link.token])


def feed_url(link: CalendarLink) -> str:
    """The full address for calendar programs, or an empty text without a working link."""
    path = feed_path(link)
    return f"{settings.RENTALARS_URL}{path}" if path else ""


def link_for_token(kind: str, pk: int, token: str) -> CalendarLink | None:
    """The working calendar link of a record with this token, or ``None``.

    The token is compared in constant time, and also when there is no link
    at all, so that the time of the answer tells nothing about a guess. A
    record out of use has no working link.
    """
    link = None
    if kind in KINDS:
        link = CalendarLink.objects.filter(**{f"{_FIELDS[kind]}_id": pk}).select_related(*_RELATED[kind]).first()
    stored = link.token if link is not None else ""
    matches = hmac.compare_digest((stored or "-").encode(), (token or "").encode())
    if link is None or not stored or not matches or _archived(link.subject):  # type: ignore[arg-type]
        return None
    return link


# --- The calendar ------------------------------------------------------------------------------------------


def _host() -> str:
    """The host name of the installation, for PRODID and the UIDs (as PER-023)."""
    return urlsplit(settings.RENTALARS_URL).hostname or "rentalars"


def _name(subject: Any, kind: str) -> str:
    """The name of the calendar: ``L-010 LED Par``, the model's name, ``0042 LED Par``."""
    if kind == PRODUCT:
        return f"{subject.article_number} {subject.name}"
    if kind == ITEM:
        return f"{subject.display_id} {subject.material_model.name}"
    return subject.name


@dataclass
class _Appointment:
    """One appointment of the calendar before it is written."""

    key: str
    summary: str
    start: datetime.datetime | datetime.date
    end: datetime.datetime | datetime.date
    details: list[str]
    tentative: bool = False
    url: str = ""


def _project_url(project: Any) -> str:
    """The page of a project; it opens only with a login and the right to see the project."""
    return f"{settings.RENTALARS_URL}{reverse('projects:overview', args=[project])}"


def _period(start: datetime.datetime, end: datetime.datetime) -> tuple[Any, Any]:
    """Whole days if the period runs from midnight to midnight (local time), else the moments."""
    local_start, local_end = timezone.localtime(start), timezone.localtime(end)
    if local_start.time() == datetime.time() and local_end.time() == datetime.time() and local_end > local_start:
        return local_start.date(), local_end.date()
    return start, end


def _project_details(project: Any, status: str) -> list[str]:
    """The first lines of the description: the project (a part with its whole project, PRJ-048) and its status."""
    from rentalars.projects.family_labels import project_label

    return [
        _("Project: %(project)s") % {"project": project_label(project)},
        _("Status: %(status)s") % {"status": status},
    ]


def _booking_appointments(kind: str, product_ids: set[int], start: Any, end: Any) -> list[_Appointment]:
    """The bookings of products in projects and their blocked items (VFG-019): a fixed number of queries.

    The demands are those of the timeline of a product (``AvailabilityEngine.collect_demands``):
    lines of projects with an option or a confirmation, also through kits and containers, their
    periods with the buffers before and after, and the blocked items.
    """
    from rentalars.availability.engine import FAR_FUTURE, AvailabilityEngine, Firmness
    from rentalars.products.models import Product
    from rentalars.projects.family_labels import project_label
    from rentalars.projects.models import Project, ProjectStatus

    engine = AvailabilityEngine()
    infos = engine.product_info(product_ids)
    tracked = {pk for pk in product_ids if infos.get(pk) and infos[pk].tracks_stock}
    if not tracked:
        return []
    demands = [
        demand
        for entries in engine.collect_demands(tracked, start, end).values()
        for demand in entries
        if demand.start < end and demand.end > start
    ]
    projects = {
        project.pk: project
        for project in Project.objects.filter(
            pk__in={demand.project_id for demand in demands if demand.project_id}
        ).select_related("parent")
    }
    names = {}
    if kind == MODEL:
        names = {
            pk: f"{number} {name}"
            for pk, number, name in Product.objects.filter(pk__in=tracked).values_list("pk", "article_number", "name")
        }
    demands.sort(key=lambda demand: (demand.start, demand.product_id, demand.line_id or 0, demand.via))
    seen: dict[str, int] = defaultdict(int)
    appointments = []
    for demand in demands:
        details: list[str] = []
        if demand.via == "blocked":
            # MAT-024: "project number" and "name" of a block are the item and the reason.
            key = f"block-{demand.product_id}-{demand.project_number}-{int(demand.start.timestamp())}"
            summary = _("%(id)s blocked: %(reason)s") % {"id": demand.project_number, "reason": demand.project_name}
            details.append(_("Item: %(id)s") % {"id": demand.project_number})
            details.append(_("Reason: %(reason)s") % {"reason": demand.project_name})
            tentative, url = False, ""
            period = _period(demand.start, demand.end)
        else:
            project = projects.get(demand.project_id)
            if project is None:  # gone between the two questions
                continue
            key = f"line-{demand.line_id}-{demand.product_id}-{demand.via}"
            tentative = demand.firmness == Firmness.SOFT
            status = project.get_status_display()
            if tentative and project.status != ProjectStatus.OPTION:
                status = f"{status}, {_('optional')}"
            label = project_label(project)
            sold = demand.end >= FAR_FUTURE  # a sale occupies its pieces for good (PRD-020)
            if sold and demand.start < start:
                continue  # sold long ago, only not yet taken out of the stock: no appointment of the window
            if sold:
                summary = _("%(quantity)s× sold – %(project)s") % {"quantity": demand.quantity, "project": label}
                day = timezone.localtime(demand.start).date()
                period = (day, day + datetime.timedelta(days=1))
            else:
                summary = f"{demand.quantity}× {label}"
                period = _period(demand.start, demand.end)
            if tentative:
                soft = project.get_status_display() if project.status == ProjectStatus.OPTION else _("optional")
                summary = f"{summary} – {soft}"
            details = _project_details(project, status)
            quantity = _("Quantity: %(quantity)s") % {"quantity": demand.quantity}
            via = {"kit": _("in a kit"), "container": _("inside a container")}.get(demand.via)
            details.append(f"{quantity} ({via})" if via else quantity)
            url = _project_url(project)
        if names:
            details.append(_("Product: %(product)s") % {"product": names.get(demand.product_id, "")})
        # Segments of the same line (PRJ-060) count up; the first keeps the plain key.
        number = seen[key]
        seen[key] += 1
        appointments.append(
            _Appointment(
                key=f"{key}-{number}" if number else key,
                summary=summary,
                start=period[0],
                end=period[1],
                details=details,
                tentative=tentative,
                url=url,
            )
        )
    return appointments


def _item_appointments(item: Any, start: datetime.datetime, end: datetime.datetime) -> list[_Appointment]:
    """What happens to an item, as its timeline shows it (``timelines.item_events``): a fixed number of queries."""
    from rentalars.material.inspections import OVERDUE
    from rentalars.projects.family_labels import project_label
    from rentalars.projects.models import ProjectStatus
    from rentalars.schedule.timelines import item_events

    today = timezone.localdate()
    appointments = []
    for event in item_events([item], start, end).get(item.pk, []):
        if event.kind == "inspection":
            due = event.due
            overdue = due.state == OVERDUE
            day = max(due.due_date or today, today) if overdue else due.due_date
            if day is None or not start.date() <= day <= end.date():
                continue
            text = _("Inspection overdue: %(name)s") if overdue else _("Inspection due: %(name)s")
            when = (
                _("Due on %(date)s") % {"date": date_format(due.due_date, "SHORT_DATE_FORMAT")}
                if due.due_date
                else _("never inspected")
            )
            appointments.append(
                _Appointment(
                    key=event.key,
                    summary=text % {"name": due.inspection_type.name},
                    start=day,
                    end=day + datetime.timedelta(days=1),
                    details=[when],
                )
            )
            continue
        if event.start is None or event.end is None:
            continue
        period = _period(event.start, event.end)
        if event.kind == "blocked":
            appointments.append(
                _Appointment(
                    key=event.key,
                    summary=_("Blocked: %(reason)s") % {"reason": event.reason},
                    start=period[0],
                    end=period[1],
                    details=[_("Reason: %(reason)s") % {"reason": event.reason}],
                )
            )
            continue
        project = event.project
        label = project_label(project)
        if event.kind == "deployment":
            text = _("Out: %(project)s") if event.issued else _("Chosen for the packing list: %(project)s")
            summary = text % {"project": label}
        elif event.kind == "wish":
            summary = _("Wished for: %(project)s") % {"project": label}
        elif event.kind == "container":
            summary = _("In %(id)s: %(project)s") % {"id": event.container, "project": label}
        else:
            summary = _("Taken out of its container for project %(project)s") % {"project": label}
        appointments.append(
            _Appointment(
                key=event.key,
                summary=summary,
                start=period[0],
                end=period[1],
                details=_project_details(project, project.get_status_display()),
                tentative=event.kind == "wish" and project.status in (ProjectStatus.INQUIRY, ProjectStatus.OPTION),
                url=_project_url(project),
            )
        )
    appointments.sort(key=lambda appointment: (str(appointment.start), appointment.key))
    return appointments


def appointments_of(link: CalendarLink, *, now: datetime.datetime | None = None) -> list[_Appointment]:
    """The appointments of the calendar of a link, from :data:`FEED_PAST` ago to :data:`FEED_FUTURE` ahead."""
    from rentalars.material.models import ARCHIVED_STATUSES, MaterialItem

    now = now or timezone.now()
    start, end = now - FEED_PAST, now + FEED_FUTURE
    kind = _kind_of_link(link)
    subject = link.subject
    if kind == ITEM:
        return _item_appointments(subject, start, end)
    if kind == PRODUCT:
        return _booking_appointments(kind, {subject.pk}, start, end)  # type: ignore[union-attr]
    # A model: the product(s) of its items, as the free pieces of its timeline.
    product_ids = set(
        MaterialItem.objects.filter(material_model=subject, product_override__isnull=False)
        .exclude(status__in=ARCHIVED_STATUSES)
        .values_list("product_override_id", flat=True)
        .distinct()
    )
    if subject.default_product_id:  # type: ignore[union-attr]
        product_ids.add(subject.default_product_id)  # type: ignore[union-attr]
    return _booking_appointments(kind, product_ids, start, end)


def _calendar(name: str, description: str) -> Any:
    """An empty calendar with its name, as the calendar of a person's deployments has it (PER-023)."""
    import icalendar

    calendar = icalendar.Calendar()
    calendar.add("PRODID", f"-//Rentalars//{_host()}//DE")
    calendar.add("VERSION", "2.0")
    calendar.add("CALSCALE", "GREGORIAN")
    calendar.add("METHOD", "PUBLISH")
    calendar.add("X-WR-CALNAME", name)
    calendar.add("X-WR-CALDESC", description)
    calendar.add("REFRESH-INTERVAL", REFRESH, parameters={"VALUE": "DURATION"})
    # As a duration ("PT30M"); a bare time span would be written as "0:30:00", which calendar programs ignore.
    calendar.add("X-PUBLISHED-TTL", icalendar.vDuration(REFRESH))
    return calendar


def _event(link: CalendarLink, appointment: _Appointment) -> Any:
    """The calendar event of one appointment, without its time stamp (the ETag must not follow the clock)."""
    import icalendar

    event = icalendar.Event()
    event.add("UID", f"rentalars-{_kind_of_link(link)}{_subject_id(link)}-{appointment.key}@{_host()}")
    event.add("SUMMARY", appointment.summary)
    for name, value in (("DTSTART", appointment.start), ("DTEND", appointment.end)):
        event.add(name, value.astimezone(datetime.UTC) if isinstance(value, datetime.datetime) else value)
    details = list(appointment.details)
    if appointment.url:
        details.append(appointment.url)
        event.add("URL", appointment.url)
    event.add("DESCRIPTION", "\n".join(details))
    event.add("STATUS", "TENTATIVE" if appointment.tentative else "CONFIRMED")
    event.add("TRANSP", "OPAQUE")
    return event


def calendar_of(link: CalendarLink) -> tuple[bytes, str]:
    """The calendar of a link as an .ics file, and its ETag.

    The ETag follows the appointments, not the moment the file was made,
    so that a calendar program that asks again gets "not modified" until
    something changed (as PER-023). Written in the language of the
    installation: nobody is logged in.
    """
    kind = _kind_of_link(link)
    stamp = timezone.now().astimezone(datetime.UTC)
    with translation.override(settings.LANGUAGE_CODE):
        calendar = _calendar(_name(link.subject, kind), shows(kind))
        events = [_event(link, appointment) for appointment in appointments_of(link)]
    fingerprint = hashlib.sha256(calendar.to_ical())
    for event in events:
        fingerprint.update(event.to_ical())
        event.add("DTSTAMP", stamp)
        calendar.add_component(event)
    return calendar.to_ical(), f'"{fingerprint.hexdigest()[:32]}"'
