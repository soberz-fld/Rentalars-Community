# SPDX-License-Identifier: GPL-3.0-or-later
"""The events a webhook can be told about, and what each one sends (API-012).

Every delivery is one JSON document, sent by ``POST`` with
``Content-Type: application/json``::

    {
      "version": 1,
      "id": "3f2b8f4e-…",                 # the delivery ID, also in X-Rentalars-Delivery
      "event": "project.status_changed",  # also in X-Rentalars-Event
      "timestamp": "2027-03-01T08:00:00+01:00",
      "data": {…}
    }

``timestamp`` is the moment of the change. ``version`` grows only with an
incompatible change; fields may be added to ``data`` at any time, so a
receiver ignores what it does not know. The ``id`` stays the same on every
attempt of a delivery: a receiver that gets it twice (a lost answer) takes
it once. Deliveries are not guaranteed to arrive in the order of the
changes; ``timestamp`` gives the order.

What an event contains
----------------------
Only what identifies the object and the change: never prices, costs or
rates, and personal data only where the event is about a person (the
person of a time entry: ID and name). Whoever needs more fetches the object
through the API (``api_url``) with a token, where the usual rights apply.
Times are ISO 8601 with offset, days ``YYYY-MM-DD``, quantities and hours
text with two decimals (``"12.00"``), as in the API (NFA-003).

The building blocks:

``project``
    ``id``, ``number``, ``name``, ``status``, ``is_internal``,
    ``customer`` (``{"id", "number"}``; ``null`` for an internal project),
    ``parent_project`` (``{"id", "number"}`` of the main project of a
    subproject, else ``null``), ``start`` and ``end`` (the reservation
    period), ``event_start`` and ``event_end`` (``null`` if not set),
    ``api_url``.
``packlist``
    ``id``, ``title`` (empty for an untitled packlist), ``status``
    (``open`` … ``partly_issued``, ``issued``, ``returned``), ``issued_at``,
    ``returned_at``, ``api_url`` and ``counts``: ``rows`` (rows with issued
    material), ``issued``, ``returned``, ``sold`` (issued as sale, never
    comes back) and ``outstanding`` (issued − sold − returned − handed over
    to another subproject, PRJ-060).
``time_entry``
    ``id``, ``person`` (``{"id", "name"}``), ``job_function``
    (``{"id", "name"}``), ``crew_line`` (ID or ``null``), ``start``,
    ``end``, ``break_minutes``, ``hours``, ``status``, ``decided_at``,
    ``api_url``.
``document``
    ``id``, ``kind`` (``offer``, ``order_confirmation``, ``delivery_note``,
    ``invoice``, ``cancellation``, ``crew_sheet``), ``number``, ``title``,
    ``issued_on``, ``due_on``, ``valid_until``, ``cancels`` (the invoice a
    cancellation cancels, ``{"id", "number"}``, else ``null``), ``api_url``,
    ``pdf_url``. No amounts: they are prices.

The events and their ``data``:

``project.created``
    ``{"project"}`` – a project was created (in any status).
``project.status_changed``
    ``{"project", "old_status", "new_status"}`` – by hand (PRJ-008) or
    because material was issued or came back (PCK-019): to ``out`` once
    everything of the project is out (PCK-025).
``packing.issued``
    ``{"packlist", "project", "complete"}`` – material of a packlist was
    issued (PCK-014). ``complete`` is ``false`` while part of the packlist
    is still in the warehouse (PCK-018, PCK-025); the rest is a further
    ``packing.issued`` later. The project is "out" only once everything of
    it is out: until then ``project.status`` is the one it had (e.g.
    ``confirmed``).
``packing.issue_undone``
    ``{"packlist", "project"}`` – an issue booked by mistake was taken back.
``packing.returned``
    ``{"packlist", "project", "complete"}`` – material came back: a row was
    ticked as returned (in the browser, through the API or by the sync of
    the app), "all returned" was ticked, or the return was completed
    (PCK-016, PCK-019) – by hand, or by booking the return once nothing
    is out any more (PCK-028). ``complete`` is ``true`` only for the
    last: the packlist is "returned". ``counts`` tells how much is ticked
    as back.
``packing.handed_over``
    ``{"packlist", "project", "from_packlist", "from_project", "product",
    "quantity", "undone"}`` – pieces taken over from another subproject
    arrived there and were booked on ``packlist`` (PRJ-060): for
    ``from_packlist`` they count as back, for ``packlist`` as issued.
    ``product`` is ``{"id", "article_number"}``. ``undone`` is ``true``
    when such a booking was taken back.
``time_entry.approved``
    ``{"time_entry", "project"}`` – one event per approved entry (ZEI-012).
``time_entry.approval_withdrawn``
    ``{"time_entry", "project"}`` – an approval was taken back; the entry
    is "submitted" again and may change.
``document.created``
    ``{"document", "project"}`` – a document was stored for good (DOK-003
    ff.), e.g. an invoice. A cancellation is a document of its own.
    ``project`` is ``null`` for a document made in Accounting without a
    project.
``ping``
    ``{"webhook", "message"}`` – sent by "Send test"; cannot be chosen.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

TWO_PLACES = Decimal("0.01")


# --- Converting values the way the API does --------------------------------------------------------


def _moment(value: Any) -> str | None:
    """A point in time as the API writes it: ISO 8601 in the installation's time zone."""
    if value is None:
        return None
    from rest_framework.fields import DateTimeField

    return DateTimeField().to_representation(value)


def _day(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _quantity(value: Any) -> str:
    """A quantity as text with two decimals – never a float (NFA-003)."""
    return str(Decimal(value or 0).quantize(TWO_PLACES))


def _absolute(path: str) -> str:
    """An address of this installation as another system reaches it."""
    return f"{settings.RENTALARS_URL.rstrip('/')}{path}"


# --- Building blocks ---------------------------------------------------------------------------------


def project_data(project: Any) -> dict[str, Any]:
    """The compact project of every event (see the module description)."""
    customer = project.customer if project.customer_id else None
    parent = project.parent if project.parent_id else None
    return {
        "id": project.pk,
        "number": project.number,
        "name": project.name,
        "status": project.status,
        # PRJ-090: "project" or "service_case".
        "kind": project.kind,
        "is_internal": project.is_internal,
        "customer": {"id": customer.pk, "number": customer.number} if customer is not None else None,
        # Subprojects (PRJ-043): the main project, so that a receiver can file the event there.
        "parent_project": {"id": parent.pk, "number": parent.number} if parent is not None else None,
        "start": _moment(project.start),
        "end": _moment(project.end),
        "event_start": _moment(project.event_start),
        "event_end": _moment(project.event_end),
        "api_url": _absolute(reverse("api:project-detail", kwargs={"pk": project.pk})),
    }


def packlist_data(packlist: Any) -> dict[str, Any]:
    """A packlist with how much is out and back – counts only, no items, no prices."""
    from django.db.models import Count, Q, Sum

    totals = packlist.entries.filter(issued_quantity__gt=0).aggregate(
        rows=Count("id"),
        issued=Sum("issued_quantity"),
        returned=Sum("returned_quantity"),
        sold=Sum("issued_quantity", filter=Q(line__is_sale=True)),
        handed_over=Sum("handed_over_quantity"),  # PRJ-060: went on to another subproject
    )
    issued, returned, sold, handed_over = (
        Decimal(totals[name] or 0) for name in ("issued", "returned", "sold", "handed_over")
    )
    return {
        "id": packlist.pk,
        "title": packlist.title,
        "status": packlist.status,
        "issued_at": _moment(packlist.issued_at),
        "returned_at": _moment(packlist.returned_at),
        "counts": {
            "rows": totals["rows"] or 0,
            "issued": _quantity(issued),
            "returned": _quantity(returned),
            "sold": _quantity(sold),
            "outstanding": _quantity(max(issued - sold - returned - handed_over, Decimal(0))),
        },
        "api_url": _absolute(
            reverse("api:packlist-detail", kwargs={"project_pk": packlist.project_id, "packlist_pk": packlist.pk})
        ),
    }


def time_entry_data(entry: Any) -> dict[str, Any]:
    """A time entry: who, what, when, how long – without rate and amount (AUT-019, PER-010)."""
    return {
        "id": entry.pk,
        "person": {"id": entry.person_id, "name": entry.person.name},
        "job_function": {"id": entry.job_function_id, "name": entry.job_function.name},
        "crew_line": entry.crew_line_id,
        "start": _moment(entry.start),
        "end": _moment(entry.end),
        "break_minutes": entry.break_minutes,
        "hours": _quantity(entry.hours),
        "status": entry.status,
        "decided_at": _moment(entry.decided_at),
        "api_url": _absolute(reverse("api:time-entry-detail", kwargs={"pk": entry.pk})),
    }


def document_data(document: Any) -> dict[str, Any]:
    """A stored document without its amounts (they are prices, AUT-019)."""
    from rentalars.documents.models import Document

    cancels = None
    cancelled_number = (document.content or {}).get("cancels_number") if isinstance(document.content, dict) else None
    if cancelled_number:
        # The link itself is set right after the cancellation is stored; the content already names the invoice.
        cancelled_id = Document.objects.filter(number=cancelled_number).values_list("pk", flat=True).first()
        cancels = {"id": cancelled_id, "number": cancelled_number}
    return {
        "id": document.pk,
        "kind": document.kind,
        "number": document.number,
        "title": document.title,
        "issued_on": _day(document.issued_on),
        "due_on": _day(document.due_on),
        "valid_until": _day(document.valid_until),
        "cancels": cancels,
        "api_url": _absolute(reverse("api:document-detail", kwargs={"pk": document.pk})),
        "pdf_url": _absolute(reverse("api:document-pdf", kwargs={"pk": document.pk})),
    }


# --- The events --------------------------------------------------------------------------------------


def _project_created(project: Any) -> dict[str, Any]:
    return {"project": project_data(project)}


def _project_status_changed(project: Any, *, old_status: str, new_status: str) -> dict[str, Any]:
    return {"project": project_data(project), "old_status": old_status, "new_status": new_status}


def _packing(packlist: Any) -> dict[str, Any]:
    return {"packlist": packlist_data(packlist), "project": project_data(packlist.project)}


def _packing_issued(packlist: Any) -> dict[str, Any]:
    from rentalars.packing.models import PacklistStatus

    return {**_packing(packlist), "complete": packlist.status == PacklistStatus.ISSUED}


def _packing_returned(packlist: Any) -> dict[str, Any]:
    from rentalars.packing.models import PacklistStatus

    return {**_packing(packlist), "complete": packlist.status == PacklistStatus.RETURNED}


def _packing_handed_over(
    packlist: Any, *, from_packlist: Any, product: Any, quantity: Any, undone: bool = False
) -> dict[str, Any]:
    """PRJ-060: pieces went straight from one subproject (``from_packlist``) to the next (``packlist``)."""
    return {
        **_packing(packlist),
        "from_packlist": packlist_data(from_packlist),
        "from_project": project_data(from_packlist.project),
        "product": {"id": product.pk, "article_number": product.article_number},
        "quantity": _quantity(quantity),
        "undone": undone,
    }


def _time_entry(entry: Any) -> dict[str, Any]:
    return {
        "time_entry": time_entry_data(entry),
        "project": project_data(entry.project) if entry.project_id else None,
    }


def _document_created(document: Any) -> dict[str, Any]:
    # Free outgoing documents: a document made in Accounting has no project.
    return {
        "document": document_data(document),
        "project": project_data(document.project) if document.project_id else None,
    }


def _ping(webhook: Any) -> dict[str, Any]:
    return {
        "webhook": {"id": webhook.pk, "events": list(webhook.events)},
        "message": "Rentalars is calling. This is a test.",
    }


@dataclass(frozen=True)
class EventType:
    """One kind of event: its name, how it is shown, how its ``data`` is built, and an example."""

    name: str
    #: Shown in the settings (German).
    label: Any
    #: For the API description.
    description: str
    build: Callable[..., dict[str, Any]]
    example: dict[str, Any] = field(default_factory=dict)


_PROJECT_EXAMPLE: dict[str, Any] = {
    "id": 12,
    "number": "2027-0012",
    "name": "Stadtfest",
    "status": "confirmed",
    "kind": "project",
    "is_internal": False,
    "customer": {"id": 3, "number": "10003"},
    "parent_project": None,
    "start": "2027-03-10T12:00:00+01:00",
    "end": "2027-03-12T12:00:00+01:00",
    "event_start": "2027-03-11T18:00:00+01:00",
    "event_end": "2027-03-11T23:30:00+01:00",
    "api_url": "https://rentalars.example.de/api/v1/projects/12",
}

_PACKLIST_EXAMPLE: dict[str, Any] = {
    "id": 7,
    "title": "",
    "status": "issued",
    "issued_at": "2027-03-10T09:12:00+01:00",
    "returned_at": None,
    "counts": {"rows": 14, "issued": "52.00", "returned": "0.00", "sold": "4.00", "outstanding": "48.00"},
    "api_url": "https://rentalars.example.de/api/v1/projects/12/packlists/7",
}

_TIME_ENTRY_EXAMPLE: dict[str, Any] = {
    "id": 81,
    "person": {"id": 5, "name": "Carla Crew"},
    "job_function": {"id": 2, "name": "Lichttechnik"},
    "crew_line": 33,
    "start": "2027-03-11T14:00:00+01:00",
    "end": "2027-03-12T00:30:00+01:00",
    "break_minutes": 30,
    "hours": "10.00",
    "status": "approved",
    "decided_at": "2027-03-14T10:05:00+01:00",
    "api_url": "https://rentalars.example.de/api/v1/time-entries/81",
}

_DOCUMENT_EXAMPLE: dict[str, Any] = {
    "id": 40,
    "kind": "invoice",
    "number": "RE-2027-0040",
    "title": "Rechnung",
    "issued_on": "2027-03-15",
    "due_on": "2027-03-29",
    "valid_until": None,
    "cancels": None,
    "api_url": "https://rentalars.example.de/api/v1/documents/40",
    "pdf_url": "https://rentalars.example.de/api/v1/documents/40/pdf",
}

EVENTS: dict[str, EventType] = {
    event.name: event
    for event in (
        EventType(
            "project.created",
            _("Project created"),
            "A project was created.",
            _project_created,
            {"project": {**_PROJECT_EXAMPLE, "status": "inquiry"}},
        ),
        EventType(
            "project.status_changed",
            _("Project status changed"),
            "The status of a project changed – by hand, or because material was issued or came back.",
            _project_status_changed,
            {"project": _PROJECT_EXAMPLE, "old_status": "option", "new_status": "confirmed"},
        ),
        EventType(
            "packing.issued",
            _("Material issued"),
            "Material of a packlist was issued; complete is false while part of it is still in the warehouse.",
            _packing_issued,
            {"packlist": _PACKLIST_EXAMPLE, "project": {**_PROJECT_EXAMPLE, "status": "out"}, "complete": True},
        ),
        EventType(
            "packing.issue_undone",
            _("Issue taken back"),
            "An issue booked by mistake was taken back.",
            _packing,
            {
                "packlist": {
                    **_PACKLIST_EXAMPLE,
                    "status": "packed",
                    "issued_at": None,
                    "counts": {"rows": 0, "issued": "0.00", "returned": "0.00", "sold": "0.00", "outstanding": "0.00"},
                },
                "project": _PROJECT_EXAMPLE,
            },
        ),
        EventType(
            "packing.returned",
            _("Material returned"),
            "Material of a packlist came back (a row, all of it, or the return was completed: complete is true).",
            _packing_returned,
            {
                "packlist": {
                    **_PACKLIST_EXAMPLE,
                    "status": "returned",
                    "returned_at": "2027-03-13T11:40:00+01:00",
                    "counts": {
                        "rows": 14,
                        "issued": "52.00",
                        "returned": "48.00",
                        "sold": "4.00",
                        "outstanding": "0.00",
                    },
                },
                "project": {**_PROJECT_EXAMPLE, "status": "returned"},
                "complete": True,
            },
        ),
        EventType(
            "packing.handed_over",
            _("Material handed over between subprojects"),
            "Pieces taken over from another subproject arrived there (PRJ-060); undone is true when taken back.",
            _packing_handed_over,
            {
                "packlist": {
                    **_PACKLIST_EXAMPLE,
                    "id": 9,
                    "status": "partly_issued",
                    "counts": {"rows": 1, "issued": "6.00", "returned": "0.00", "sold": "0.00", "outstanding": "6.00"},
                    "api_url": "https://rentalars.example.de/api/v1/projects/14/packlists/9",
                },
                "project": {
                    **_PROJECT_EXAMPLE,
                    "id": 14,
                    "number": "2027-0012-2",
                    "name": "Bühne Schlosspark",
                    "status": "out",
                    "parent_project": {"id": 12, "number": "2027-0012"},
                    "api_url": "https://rentalars.example.de/api/v1/projects/14",
                },
                "from_packlist": {
                    **_PACKLIST_EXAMPLE,
                    "id": 8,
                    "api_url": "https://rentalars.example.de/api/v1/projects/13/packlists/8",
                },
                "from_project": {
                    **_PROJECT_EXAMPLE,
                    "id": 13,
                    "number": "2027-0012-1",
                    "name": "Bühne Marktplatz",
                    "status": "out",
                    "parent_project": {"id": 12, "number": "2027-0012"},
                    "api_url": "https://rentalars.example.de/api/v1/projects/13",
                },
                "product": {"id": 31, "article_number": "L-100"},
                "quantity": "6.00",
                "undone": False,
            },
        ),
        EventType(
            "time_entry.approved",
            _("Time entry approved"),
            "A time entry was approved; one event per entry.",
            _time_entry,
            {"time_entry": _TIME_ENTRY_EXAMPLE, "project": _PROJECT_EXAMPLE},
        ),
        EventType(
            "time_entry.approval_withdrawn",
            _("Approval of a time entry taken back"),
            "The approval of a time entry was taken back; the entry is submitted again and may change.",
            _time_entry,
            {
                "time_entry": {**_TIME_ENTRY_EXAMPLE, "status": "submitted", "decided_at": None},
                "project": _PROJECT_EXAMPLE,
            },
        ),
        EventType(
            "document.created",
            _("Document created"),
            "A document was stored for good, e.g. an invoice or a cancellation. Without amounts.",
            _document_created,
            {"document": _DOCUMENT_EXAMPLE, "project": {**_PROJECT_EXAMPLE, "status": "returned"}},
        ),
        EventType(
            "ping",
            _("Test"),
            "Sent by “Send test”; it cannot be chosen.",
            _ping,
            {
                "webhook": {"id": 1, "events": ["project.status_changed"]},
                "message": "Rentalars is calling. This is a test.",
            },
        ),
    )
}

PING = "ping"

#: The events a webhook can choose, in the order of the catalogue.
SUBSCRIBABLE: tuple[str, ...] = tuple(name for name in EVENTS if name != PING)


def choices() -> list[tuple[str, Any]]:
    """The events to choose from, for forms."""
    return [(name, EVENTS[name].label) for name in SUBSCRIBABLE]


def build(event: str, subject: Any, **details: Any) -> dict[str, Any]:
    """The ``data`` of an event about ``subject``."""
    return EVENTS[event].build(subject, **details)
