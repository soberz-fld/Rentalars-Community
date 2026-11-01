# SPDX-License-Identifier: GPL-3.0-or-later
"""The access log: who read which record, when and from where (AUT-028).

The change log says who *changed* what. For the data-protection control it
also matters who *looked at* personal data: a customer, a person, a project
with its mails, files and documents, a list exported as CSV, the full export,
a backup. One entry per access names the user, the time, the IP address, the
kind and key of the record, a short label and how it was read:

``view``      a page of the record was opened
``download``  a file was fetched – a document, an attachment, a project file
``export``    data left as a file: a CSV list, the information for a customer
              or a person, the full export, a backup
``api``       the record was read through the API

**How.** :class:`AccessLogMiddleware` looks at every successful ``GET``
after the view answered: at the name of the address and its arguments.
Projects are found by the argument of the converter ``<project:pk>``, the
project number in the address (UIX-024); everything else by a table of
address names (:data:`NAMED`). Any other answer that is a CSV file counts as
the export of a list. Downloads of the full export and of a backup go
through the address of task results and are recognised by the kind of task.

**Cheap.** Nothing is looked at for static files (NGINX serves them), for
requests of htmx (fragments of a page already logged, and polling), for
lists without export, for anything that is not ``GET`` or did not succeed.
A new read costs one query – it names the record and looks for a recent
entry at once – and one insert; a repeated read costs nothing when this
process saw it, else that one query. The same user reading the same record
the same way within :data:`DEDUPLICATE_WITHIN` is one entry: going through
the tabs of a project is one "opened"; a file fetched twice is one
"downloaded" (a download or export counts again for another address –
another filter of a list).

Not logged: a person's own data (their own profile, their own person page),
and reads by programs on the server (``rentalars export_data``).

Entries are kept for ``retention_access_log_days`` (NFA-011, AUT-028).
When a customer or a person is anonymised, the label of their entries is
replaced (:func:`forget_customer`, :func:`forget_person`).
"""

from __future__ import annotations

import datetime
import logging
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.db.models import Exists, Q, QuerySet
from django.http import FileResponse, HttpRequest, HttpResponse, StreamingHttpResponse
from django.urls import ResolverMatch, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from rentalars.core.models import AccessAction, AccessKind, AccessLogEntry
from rentalars.core.tables import Column, TableDefinition, badge, date_text, grouped_by_day

logger = logging.getLogger(__name__)

#: Reads of the same record by the same user in the same way within this time are one entry.
DEDUPLICATE_WITHIN = datetime.timedelta(minutes=5)

#: The result of a background task (``core:job_result``): which kinds are logged, as what.
JOB_KINDS = {"export": AccessKind.FULL_EXPORT, "backup": AccessKind.BACKUP}

#: Not a kind of its own in the log: a task result becomes "full export" or "backup".
_JOB = "job"

#: Not a kind of its own either: the draft of a document without a project is logged as a read of its customer.
_DRAFT = "draft"

#: Addresses by name: (kind of record, argument with its key). Projects need no entry here.
NAMED: dict[str, tuple[str, str]] = {
    "customers:detail": (AccessKind.CUSTOMER, "pk"),
    "customers:edit": (AccessKind.CUSTOMER, "pk"),
    "customers:export": (AccessKind.CUSTOMER, "pk"),
    "customers:contact_edit": (AccessKind.CUSTOMER, "customer_pk"),
    "customers:address_edit": (AccessKind.CUSTOMER, "customer_pk"),
    "mail:detail": (AccessKind.MAIL, "mail_pk"),
    "mail:body": (AccessKind.MAIL, "mail_pk"),
    "mail:attachment": (AccessKind.ATTACHMENT, "attachment_pk"),
    "projects:file_download": (AccessKind.PROJECT_FILE, "file_pk"),
    "documents:file": (AccessKind.DOCUMENT, "pk"),
    "documents:xml": (AccessKind.DOCUMENT, "pk"),
    # Free outgoing documents; DOK-022: the document of the customer, the draft (and its PDF) of the customer.
    "documents:free_document": (AccessKind.DOCUMENT, "pk"),
    "documents:free_send": (AccessKind.DOCUMENT, "pk"),
    "documents:free_edit": (_DRAFT, "pk"),
    "documents:free_preview": (_DRAFT, "pk"),
    "core:job_result": (_JOB, "pk"),
    "api:project-mail-detail": (AccessKind.MAIL, "mail_pk"),
    "api:mail-attachment": (AccessKind.ATTACHMENT, "attachment_pk"),
    "api:project-file-detail": (AccessKind.PROJECT_FILE, "pk"),
    "api:project-file-content": (AccessKind.PROJECT_FILE, "pk"),
    "api:document-detail": (AccessKind.DOCUMENT, "pk"),
    "api:document-pdf": (AccessKind.DOCUMENT, "pk"),
    "api:document-xml": (AccessKind.DOCUMENT, "pk"),
    "api:job-result": (_JOB, "pk"),
}

#: Addresses that hand out the data of a record as a file: the information of the persons concerned.
EXPORTS = frozenset({"customers:export", "personnel:person_export", "api:customer-export", "api:person-export"})

#: API addresses ``<prefix>…`` with the key in ``pk`` (the router's own names).
_API_PREFIXES = (("customer-", AccessKind.CUSTOMER), ("person-", AccessKind.PERSON), ("project-", AccessKind.PROJECT))

#: API addresses of lists, which are not logged.
_API_LISTS = frozenset({"customer-list", "customer-duplicates", "person-list", "project-list"})


@dataclass(frozen=True)
class Target:
    """The record an access was about, named for the log."""

    kind: str
    object_id: str
    label: str
    parent_kind: str = ""
    parent_id: str = ""
    #: The record is the reader's own (their person): not logged.
    own: bool = False
    #: The same user read it the same way in the last minutes: not logged again.
    recent: bool = False


# --- Which record an address is about ------------------------------------------------------------------


def reference_of(match: ResolverMatch) -> tuple[str, str] | None:
    """The kind and key of the record an address is about, or ``None``.

    Example: ``/projects/2026-0042/prices/`` → ``("project", "42")``;
    ``/api/v1/customers/7/contacts`` → ``("customer", "7")``.
    """
    kwargs = match.kwargs
    named = NAMED.get(match.view_name)
    if named is not None:
        kind, argument = named
        return (kind, str(kwargs[argument])) if argument in kwargs else None
    namespace, _separator, name = match.view_name.partition(":")
    route = str(match.route or "")
    if namespace == "api":
        if "project_pk" in kwargs:
            return AccessKind.PROJECT, str(kwargs["project_pk"])
        if "customer_pk" in kwargs:
            return AccessKind.CUSTOMER, str(kwargs["customer_pk"])
        if "pk" in kwargs and name not in _API_LISTS:
            for prefix, kind in _API_PREFIXES:
                if name.startswith(prefix):
                    return kind, str(kwargs["pk"])
        return None
    if "<project:pk>" in route and "pk" in kwargs:
        return AccessKind.PROJECT, str(kwargs["pk"])
    if route.startswith("personnel/people/<int:pk>/") and "pk" in kwargs:
        return AccessKind.PERSON, str(kwargs["pk"])
    return None


def _key(value: str) -> int | None:
    return int(value) if value.isdigit() else None


def _project_label(number: Any, name: Any) -> str:
    return f"{number} {name}".strip()


def _row(queryset: QuerySet[Any], fields: tuple[str, ...], recent: Any) -> tuple[tuple[Any, ...], bool] | None:
    """The values of one record and – asked in the same query – whether it was read just now.

    ``recent`` is an ``Exists`` of an entry of the last minutes, or ``None``.
    """
    if recent is not None:
        queryset = queryset.annotate(already_logged=recent)
        fields = (*fields, "already_logged")
    row = queryset.values_list(*fields).first()
    if row is None:
        return None
    return (tuple(row[:-1]), bool(row[-1])) if recent is not None else (tuple(row), False)


def _customer(pk: int, user: Any, recent: Any) -> Target | None:
    from rentalars.customers.models import Customer

    found = _row(Customer.objects.filter(pk=pk), ("number", "name"), recent)
    if found is None:
        return None
    (number, name), already = found
    return Target(AccessKind.CUSTOMER, str(pk), f"{number} {name}".strip(), recent=already)


def _person(pk: int, user: Any, recent: Any) -> Target | None:
    from rentalars.personnel.models import Person

    found = _row(Person.objects.filter(pk=pk), ("first_name", "last_name", "user_id"), recent)
    if found is None:
        return None
    (first, last, user_id), already = found
    own = user is not None and user_id == user.pk
    return Target(AccessKind.PERSON, str(pk), f"{first} {last}".strip(), own=own, recent=already)


def _project(pk: int, user: Any, recent: Any) -> Target | None:
    from rentalars.projects.models import Project

    found = _row(Project.objects.filter(pk=pk), ("number", "name"), recent)
    if found is None:
        return None
    (number, name), already = found
    return Target(AccessKind.PROJECT, str(pk), _project_label(number, name), recent=already)


def _mail(pk: int, user: Any, recent: Any) -> Target | None:
    from rentalars.mail.models import ProjectMail

    found = _row(ProjectMail.objects.filter(pk=pk), ("subject", "project_id", "project__number"), recent)
    if found is None:
        return None
    (subject, project_id, number), already = found
    return Target(AccessKind.MAIL, str(pk), f"{number}: {subject}", AccessKind.PROJECT, str(project_id), recent=already)


def _attachment(pk: int, user: Any, recent: Any) -> Target | None:
    from rentalars.mail.models import MailAttachment

    found = _row(
        MailAttachment.objects.filter(pk=pk), ("filename", "mail__project_id", "mail__project__number"), recent
    )
    if found is None:
        return None
    (filename, project_id, number), already = found
    return Target(
        AccessKind.ATTACHMENT, str(pk), f"{number}: {filename}", AccessKind.PROJECT, str(project_id), recent=already
    )


def _project_file(pk: int, user: Any, recent: Any) -> Target | None:
    from rentalars.projects.models import ProjectFile

    found = _row(ProjectFile.objects.filter(pk=pk), ("title", "original_name", "project_id", "project__number"), recent)
    if found is None:
        return None
    (title, name, project_id, number), already = found
    label = f"{number}: {title or name}"
    return Target(AccessKind.PROJECT_FILE, str(pk), label, AccessKind.PROJECT, str(project_id), recent=already)


def _document(pk: int, user: Any, recent: Any) -> Target | None:
    from rentalars.documents.models import Document

    found = _row(
        Document.objects.filter(pk=pk), ("title", "number", "project_id", "project__number", "customer_id"), recent
    )
    if found is None:
        return None
    (title, number, project_id, project_number, customer_id), already = found
    if project_id is None:
        # Free outgoing documents: a document without a project belongs to its customer.
        label = f"{title} {number}"
        return Target(AccessKind.DOCUMENT, str(pk), label, AccessKind.CUSTOMER, str(customer_id or ""), recent=already)
    label = f"{title} {number} ({project_number})"
    return Target(AccessKind.DOCUMENT, str(pk), label, AccessKind.PROJECT, str(project_id), recent=already)


def _draft(pk: int, user: Any, recent: Any) -> Target | None:
    """A draft of a document without a project shows the customer's data; the read is the customer's."""
    from rentalars.documents.models import DocumentDraft

    row = DocumentDraft.objects.filter(pk=pk).values_list("customer_id", "customer__number", "customer__name").first()
    if row is None:
        return None
    customer_id, number, name = row
    return Target(AccessKind.CUSTOMER, str(customer_id), f"{number} {name}".strip())


def _job(pk: int, user: Any, recent: Any) -> Target | None:
    from rentalars.core.models import BackgroundJob

    # The kind of the task decides what it is in the log; a repeated download is found afterwards.
    row = BackgroundJob.objects.filter(pk=pk).values_list("kind", "title", "result_name").first()
    if row is None or row[0] not in JOB_KINDS:
        return None
    kind, title, result_name = row
    return Target(JOB_KINDS[kind], str(pk), f"{title}: {result_name}" if result_name else title)


#: How each kind of record is named for the log; ``None`` if it does not exist (any more).
_DESCRIBE: dict[str, Callable[[int, Any, Any], Target | None]] = {
    AccessKind.CUSTOMER: _customer,
    AccessKind.PERSON: _person,
    AccessKind.PROJECT: _project,
    AccessKind.MAIL: _mail,
    AccessKind.ATTACHMENT: _attachment,
    AccessKind.PROJECT_FILE: _project_file,
    AccessKind.DOCUMENT: _document,
    _JOB: _job,
    _DRAFT: _draft,
}


def describe(kind: str, object_id: str, user: Any, *, recent: Any = None) -> Target | None:
    """Name a record for the log, in one query; ``None`` if it cannot be found.

    With ``recent`` – an ``Exists`` of a recent entry – the same query also
    tells whether this read is a repetition (``Target.recent``).
    """
    key = _key(object_id)
    describer = _DESCRIBE.get(kind)
    if key is None or describer is None:
        return None
    return describer(key, user, recent)


# --- Writing ------------------------------------------------------------------------------------------


def _is_csv(response: HttpResponse) -> bool:
    return str(response.get("Content-Type", "")).startswith("text/csv")


def _is_file(response: HttpResponse) -> bool:
    """Whether an answer is a file rather than a page."""
    return (
        isinstance(response, FileResponse | StreamingHttpResponse)
        or response.has_header("Content-Disposition")
        or response.has_header("X-Accel-Redirect")
    )


def action_of(match: ResolverMatch, response: HttpResponse) -> str:
    """How the record was read: through the API, as an export, as a downloaded file, or on a page."""
    if match.view_name.startswith("api:"):
        return AccessAction.API
    if match.view_name in EXPORTS or _is_csv(response):
        return AccessAction.EXPORT
    if _is_file(response):
        return AccessAction.DOWNLOAD
    return AccessAction.VIEW


def _list_label(response: HttpResponse, match: ResolverMatch) -> str:
    """The name of an exported list: the file name the browser saves it under."""
    disposition = str(response.get("Content-Disposition", ""))
    _before, separator, name = disposition.partition("filename=")
    return name.strip('"; ') if separator else match.view_name


def _recent_entries(user: Any, kind: str, object_id: str, action: str, path: str) -> QuerySet[AccessLogEntry]:
    recent = AccessLogEntry.objects.filter(
        user=user,
        timestamp__gte=timezone.now() - DEDUPLICATE_WITHIN,
        object_type=kind,
        object_id=object_id,
        action=action,
    )
    if action in {AccessAction.DOWNLOAD, AccessAction.EXPORT}:
        recent = recent.filter(path=path)
    return recent


def is_duplicate(user: Any, target: Target, action: str, path: str) -> bool:
    """Whether the same user read the same record the same way within :data:`DEDUPLICATE_WITHIN`."""
    return _recent_entries(user, target.kind, target.object_id, action, path).exists()


def record_access(
    user: Any,
    target: Target,
    action: str,
    *,
    request: HttpRequest | None = None,
    path: str = "",
    deduplicate: bool = True,
) -> AccessLogEntry | None:
    """Write one entry of the access log; ``None`` if it repeats one of the last minutes or is the user's own.

    Called by :class:`AccessLogMiddleware`; other code may call it for
    reads the middleware cannot see.
    """
    from rentalars.accounts.services import client_ip

    if target.own or target.recent:
        return None
    path = path[:300]
    if deduplicate and is_duplicate(user, target, action, path):
        return None
    return AccessLogEntry.objects.create(
        user=user,
        user_label=user.get_username()[:150],
        ip_address=client_ip(request) if request is not None else None,
        action=action,
        object_type=target.kind,
        object_id=target.object_id[:60],
        label=target.label[:200],
        parent_type=target.parent_kind,
        parent_id=target.parent_id[:40],
        path=path,
    )


class _Seen:
    """Reads this process logged in the last minutes – repeated reads then cost no query at all.

    Keyed by the session (or API token) as well: a log-in elsewhere is
    looked up in the database once. Several processes of the application
    server each keep their own; the database answers for the others.
    """

    LIMIT = 4096

    def __init__(self) -> None:
        self._entries: OrderedDict[tuple[Any, ...], datetime.datetime] = OrderedDict()
        self._lock = threading.Lock()

    def recently(self, key: tuple[Any, ...], now: datetime.datetime) -> bool:
        with self._lock:
            seen = self._entries.get(key)
            return seen is not None and now - seen < DEDUPLICATE_WITHIN

    def note(self, key: tuple[Any, ...], now: datetime.datetime) -> None:
        with self._lock:
            self._entries[key] = now
            self._entries.move_to_end(key)
            while len(self._entries) > self.LIMIT:
                self._entries.popitem(last=False)


_seen = _Seen()


def _reader(request: HttpRequest) -> str:
    """Who reads, beyond the user: the session of the browser, or the API token."""
    token = getattr(request, "auth", None)
    if token is not None and getattr(token, "key_prefix", None):
        return f"token:{token.pk}:{token.key_prefix}"
    session = getattr(request, "session", None)
    return f"session:{getattr(session, 'session_key', '') or ''}"


def log_request(request: HttpRequest, response: HttpResponse) -> AccessLogEntry | None:
    """Log the request if it read a record or exported a list (AUT-028); see the module text.

    A repeated read costs no query when this process saw it, else one; a
    new read costs one query to name the record (and to look for a recent
    entry, in the same query) and the insert.
    """
    if request.method != "GET" or response.status_code != 200 or request.headers.get("HX-Request"):
        return None
    match = getattr(request, "resolver_match", None)
    user = getattr(request, "user", None)
    if match is None or not match.view_name or user is None or not user.is_authenticated:
        return None
    reference = reference_of(match)
    if reference is None and not _is_csv(response):
        return None
    action = action_of(match, response)
    path = (request.get_full_path() if action == AccessAction.EXPORT else request.path)[:300]
    if reference is None:
        target = Target(AccessKind.LIST, match.view_name, _list_label(response, match))
        return record_access(user, target, action, request=request, path=path)
    kind, object_id = reference
    now = timezone.now()
    key = (
        _reader(request),
        user.pk,
        kind,
        object_id,
        action,
        path if action in {AccessAction.DOWNLOAD, AccessAction.EXPORT} else "",
    )
    if _seen.recently(key, now):
        return None
    if kind in {_JOB, _DRAFT}:
        target = describe(kind, object_id, user)
        deduplicate = True
    else:
        recent = Exists(_recent_entries(user, kind, object_id, action, path))
        target = describe(kind, object_id, user, recent=recent)
        deduplicate = False
    if target is None:
        return None
    _seen.note(key, now)
    return record_access(user, target, action, request=request, path=path, deduplicate=deduplicate)


class AccessLogMiddleware:
    """Write the access log after each request that read a record (AUT-028).

    A failure to write is logged as an error of the application, but never
    costs the user the page they asked for.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Answer the request, then note the access."""
        response = self.get_response(request)
        try:
            log_request(request, response)
        except Exception:
            logger.exception("The access log could not be written for %s.", request.path)
        return response


# --- Reading, keeping, forgetting ------------------------------------------------------------------------


def filtered_entries(
    *,
    user: int | None = None,
    kind: str = "",
    object_id: str = "",
    action: str = "",
    since: datetime.datetime | None = None,
    until: datetime.datetime | None = None,
    text: str = "",
) -> QuerySet[AccessLogEntry]:
    """The entries that match the filters of the page and the API.

    ``kind`` and ``object_id`` together name one record: its own entries and
    those of what belongs to it (the mails, files and documents of a project).
    ``until`` is exclusive. ``text`` is looked for in the label, the user
    name, the address and the start of the IP address.
    """
    entries = AccessLogEntry.objects.select_related("user")
    if user is not None:
        entries = entries.filter(user_id=user)
    if kind and object_id:
        entries = entries.filter(Q(object_type=kind, object_id=object_id) | Q(parent_type=kind, parent_id=object_id))
    elif kind:
        entries = entries.filter(object_type=kind)
    if action:
        entries = entries.filter(action=action)
    if since is not None:
        entries = entries.filter(timestamp__gte=since)
    if until is not None:
        entries = entries.filter(timestamp__lt=until)
    if text:
        entries = entries.filter(
            Q(label__icontains=text)
            | Q(user_label__icontains=text)
            | Q(path__icontains=text)
            | Q(ip_address__startswith=text)
        )
    return entries


def delete_old_entries(days: int | None = None) -> int:
    """Remove entries after the retention period (NFA-011, AUT-028); returns the number removed."""
    from rentalars.core.models import SystemSettings

    days = days if days is not None else SystemSettings.load().retention_access_log_days
    limit = timezone.now() - datetime.timedelta(days=days)
    deleted, _details = AccessLogEntry.objects.filter(timestamp__lt=limit).delete()
    return deleted


def forget_customer(customer: Any) -> int:
    """After a customer was anonymised: its entries no longer name it (AUT-028, KND-010).

    The entries stay – *that* somebody opened customer 10001 remains on
    record – under the anonymised name. Returns the number of entries.
    """
    return AccessLogEntry.objects.filter(object_type=AccessKind.CUSTOMER, object_id=str(customer.pk)).update(
        label=f"{customer.number} {customer.name}".strip()[:200]
    )


def forget_person(person: Any) -> int:
    """After a person was anonymised: neither the entries about them nor their own reads name them (NFA-009).

    The account of the person is anonymised too (``accounts.services.anonymise_user``);
    its new name replaces the old one in the entries of what the person read.
    Returns the number of entries changed.
    """
    about = AccessLogEntry.objects.filter(object_type=AccessKind.PERSON, object_id=str(person.pk)).update(
        label=str(person.name)[:200]
    )
    by = 0
    if person.user_id:
        by = AccessLogEntry.objects.filter(user_id=person.user_id).update(user_label=person.user.get_username()[:150])
    return about + by


# --- The list on the page (UIX-015, IMP-005) ------------------------------------------------------------


def filter_url(entry: AccessLogEntry) -> str:
    """The address of the log filtered by the record of an entry ("per object a filter link")."""
    return f"{reverse('core:access_log')}?type={entry.object_type}&object={entry.object_id}"


def _object_cell(entry: AccessLogEntry) -> Any:
    return format_html('<a href="{}">{}</a>', filter_url(entry), entry.label or entry.object_id)


def _action_cell(entry: AccessLogEntry) -> Any:
    colour = {AccessAction.EXPORT: "yellow", AccessAction.DOWNLOAD: "accent"}.get(entry.action, "")
    return badge(entry.get_action_display(), colour)


ACCESS_LOG_TABLE = TableDefinition(
    "access_log",
    [
        Column(
            "time",
            pgettext_lazy("access log", "Time"),
            cell=lambda entry: date_text(entry.timestamp),
            text=lambda entry: entry.timestamp,
            # The same moment: the later entry first.
            sort=("timestamp", "id"),
            css="nowrap",
            fixed=True,
            **grouped_by_day("timestamp"),  # UIX-044: every column groups, a moment by its day
        ),
        Column(
            "user",
            _("User"),
            cell=lambda entry: entry.user_label,
            sort=("user_label", "-timestamp"),
            group="user_label",
        ),
        Column(
            "action",
            _("Access"),
            cell=_action_cell,
            text=lambda entry: entry.get_action_display(),
            sort=("action", "-timestamp"),
            group="action",
        ),
        Column(
            "kind",
            _("Kind of object"),
            cell=lambda entry: entry.get_object_type_display(),
            sort=("object_type", "-timestamp"),
            group="object_type",
        ),
        Column(
            "object",
            _("Object"),
            cell=_object_cell,
            text=lambda entry: entry.label,
            sort=("label", "-timestamp"),
            group="label",
        ),
        Column(
            "object_id",
            _("Object ID"),
            cell=lambda entry: entry.object_id,
            sort=("object_id", "-timestamp"),
            default=False,
            group="object_id",
        ),
        Column(
            "ip",
            _("IP address"),
            cell=lambda entry: entry.ip_address or "",
            sort=("ip_address", "-timestamp"),
            group="ip_address",
        ),
        Column(
            "path",
            _("Page address"),
            cell=lambda entry: entry.path,
            sort=("path", "-timestamp"),
            default=False,
            group="path",
        ),
    ],
    default_sort="-time",
)
