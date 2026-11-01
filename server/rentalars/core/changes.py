# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages that follow changes by themselves (UIX-020).

A mail arrives, a colleague adds a line, the warehouse packs: whoever has the
project open should see it without pressing "reload". The page asks every
twenty seconds (``app.js``) whether what it shows has changed, and loads
itself again if so – unless the user is typing or a dialog is open; then it
only says that there is something new.

What a page shows is named by *keys*. The question costs one or two
indexed queries per open page, whatever the amount of data:

``project:<pk>``
    The project and everything below it: lines, crew, packlists, mails,
    files, documents. All of these write the change log with the project as
    their parent, so the newest entry of the log tells whether anything
    changed (``AuditLogEntry`` with ``parent`` = the project).
``mail:unknown``
    The list of mails with an unknown tag (EML-014) and inquiries – since
    Also those noted by hand and changed (EML-053).
``notifications``
    The user's own notifications; the answer also carries the count of the
    unread ones for the bell, so that it is right on every page.
``chat:<pk>``
    UIX-010: the chat of a project, on every page of a project:
    ``<content>~<unread>`` (``chat.services.stamp``). A new message does not
    load a page again – the script fills the unread count into the tab
    "Chat", and the chat itself fetches its messages in place.
``packing:<pk>``
    UIX-020, PCK-027: the ticks on the packlists of a project, on
    the packlist pages. A tick changes no field of the change log – up to
    A packlist page did not follow what a colleague or the app
    ticked. The stamp is the sum of the rows' versions and their count
    (``PackEntry.version`` counts every change of a ticked quantity).
``stock:<pk>``
    Stock refresh: the figures of the availability on the planning page – models, items, products, kits and the
    lines of all projects. A changed stamp makes the page fetch only the availability cells in place, never a reload
    (``rentalars.projects.stock_watch``).

Every stamp counts changes rather than timing them (UIX-010): a time
in whole seconds misses a second change within the same second.

The user's own changes do not reload the page: after every request that
changed something, the script takes over the new state as the one it shows.

PER-033: taking over the new state must not swallow what somebody
else changed in the meantime – the answer to a deployment request that came
by mail a few seconds before the planner saved a line, which then stood on
"asked" until the page was loaded by hand. So the stamp of a project reads
``<newest change>.<newest change by somebody else>``: after one's own
change the script takes over the first part, and loads the page again if
the second part moved. Changes by the same user elsewhere – another tab,
the app – still reload the page with the next regular question.
"""

from __future__ import annotations

from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.db.models import Max, Q
from django.http import HttpRequest, JsonResponse

#: URL namespaces whose pages belong to one project, recognised by the ``pk`` of the address.
PROJECT_NAMESPACES = frozenset({"projects", "mail", "packing", "documents", "chat"})

#: Pages of a project that are not about one project (lists, forms for a new one).
_NOT_ONE_PROJECT = frozenset({"projects:list", "projects:create", "projects:open_items"})

#: Most keys one request may ask about.
MAX_KEYS = 8


def watch_keys(request: HttpRequest) -> list[str]:
    """The keys of what the page of this request shows (for ``data-watch`` in base.html)."""
    match = getattr(request, "resolver_match", None)
    keys = ["notifications"]
    if match is None:
        return keys
    if match.namespace in PROJECT_NAMESPACES and match.view_name not in _NOT_ONE_PROJECT and "pk" in match.kwargs:
        keys.append(f"project:{match.kwargs['pk']}")
        if match.route.startswith("projects/"):
            # UIX-010: the unread count of the chat for the tab of every project page.
            keys.append(f"chat:{match.kwargs['pk']}")
            if match.view_name == "projects:detail":
                # Stock refresh: a model linked to a product in another tab changes the figures here.
                keys.append(f"stock:{match.kwargs['pk']}")
            if match.namespace == "packing":
                # UIX-020, PCK-027: ticks of others – a colleague, the app – reload the packlist.
                keys.append(f"packing:{match.kwargs['pk']}")
    elif match.view_name == "mail:unknown_list":
        keys.append("mail:unknown")
    return keys


def _project_stamp(pk: int, user: Any) -> str:
    from rentalars.accounts.rights import rights_of
    from rentalars.core.models import AuditLogEntry
    from rentalars.projects.access import ProjectAccess, access_level
    from rentalars.projects.models import Project

    project = Project.objects.filter(pk=pk).first()
    if project is None:
        return "gone"
    if access_level(rights_of(user), user, project) < ProjectAccess.DEPLOYMENT:
        return ""
    project_type = ContentType.objects.get_for_model(Project)
    found = AuditLogEntry.objects.filter(
        Q(content_type=project_type, object_id=str(pk)) | Q(parent_content_type=project_type, parent_object_id=str(pk))
    ).aggregate(newest=Max("pk"), others=Max("pk", filter=~Q(actor_id=getattr(user, "pk", None))))
    # PER-033: "<newest change>.<newest change by somebody else>" – see the module docstring.
    return f"{found['newest'] or 0}.{found['others'] or 0}"


def _chat_stamp(pk: int, user: Any) -> str:
    """UIX-010: the chat of a project for whoever can open the project, else nothing."""
    from rentalars.accounts.rights import rights_of
    from rentalars.chat.services import stamp
    from rentalars.projects.access import ProjectAccess, access_level
    from rentalars.projects.models import Project

    project = Project.objects.filter(pk=pk).first()
    if project is None or access_level(rights_of(user), user, project) < ProjectAccess.DEPLOYMENT:
        return ""
    return stamp(pk, user)


def _packing_stamp(pk: int, user: Any) -> str:
    """UIX-020, PCK-027: the ticks on the packlists of a project – ``<sum of versions>-<rows>``.

    For whoever can open the project, else nothing. Without "." in the stamp,
    the script does not count it after the page's own change (PER-033): one's
    own tick does not reload the page; the ticks of others do with the next
    regular question.
    """
    from django.db.models import Count, Sum

    from rentalars.accounts.rights import rights_of
    from rentalars.packing.models import PackEntry
    from rentalars.projects.access import ProjectAccess, access_level
    from rentalars.projects.models import Project

    project = Project.objects.filter(pk=pk).first()
    if project is None or access_level(rights_of(user), user, project) < ProjectAccess.DEPLOYMENT:
        return ""
    found = PackEntry.objects.filter(packlist__project_id=pk).aggregate(versions=Sum("version"), rows=Count("pk"))
    return f"{found['versions'] or 0}-{found['rows']}"


def _unknown_mail_stamp(user: Any) -> str:
    from rentalars.accounts.rights import Module, rights_of
    from rentalars.mail.models import UnknownTagMail

    if not rights_of(user).can_read(Module.EMAIL):
        return ""
    from django.db.models import Count, Sum

    # EML-053: inquiries noted by hand count their changes (``version``); one taken off the list or
    # deleted changes the count of the waiting ones – one query for all of it.
    found = UnknownTagMail.objects.aggregate(
        newest=Max("pk"),
        rows=Count("pk"),
        waiting=Count("pk", filter=Q(resolved_at__isnull=True)),
        versions=Sum("version"),
    )
    return f"{found['newest'] or 0}-{found['rows']}-{found['waiting']}-{found['versions'] or 0}"


def stamps(keys: list[str], user: Any) -> dict[str, str]:
    """For each key the state it has now: any text that changes when the content changes.

    Unknown keys, and keys the user may not read, give an empty text.
    """
    from rentalars.notifications.services import unread_count

    result: dict[str, str] = {}
    for key in keys[:MAX_KEYS]:
        kind, _colon, ident = key.partition(":")
        if kind == "project" and ident.isdigit():
            result[key] = _project_stamp(int(ident), user)
        elif kind == "chat" and ident.isdigit():
            result[key] = _chat_stamp(int(ident), user)
        elif kind == "packing" and ident.isdigit():
            result[key] = _packing_stamp(int(ident), user)
        elif kind == "stock" and ident.isdigit():
            from rentalars.projects.stock_watch import stock_stamp

            result[key] = stock_stamp(int(ident), user)
        elif key == "mail:unknown":
            result[key] = _unknown_mail_stamp(user)
        elif key == "notifications":
            result[key] = str(unread_count(user))
        else:
            result[key] = ""
    return result


def changes_view(request: HttpRequest) -> JsonResponse:
    """``GET /changes/?keys=project:42,notifications`` – the state of what a page shows (UIX-020)."""
    keys = [key for key in request.GET.get("keys", "").split(",") if key]
    found = stamps(keys, request.user)
    response = JsonResponse({"stamps": found, "unread": int(found.get("notifications") or 0)})
    response["Cache-Control"] = "no-store"
    return response
