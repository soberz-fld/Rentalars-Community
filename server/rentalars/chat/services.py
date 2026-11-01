# SPDX-License-Identifier: GPL-3.0-or-later
"""The chat of a project: who reads it, writing, changing, mentions, unread messages (UIX-010).

Who reads and writes
--------------------
Everybody who can open the project (AUT-025): the office with the planning
and the crew with the deployment view – a person planned in a crew line
reads the chat of that project, of no other. :func:`readers_of` finds them
for the list "Wer mitliest" and for mentions, with the same rules as
``projects.access.access_level``, but for all users at once in four
queries instead of two per user.

Mentions
--------
``@Anna Becker`` – or ``@anna``, the user name – in a message names a
reader. The longest names are looked for first, and a name found blocks
its place: ``@Anna Becker`` never also mentions a user called ``anna``.
Who is mentioned is notified (``chat_mention``, in the application and by
e-mail as the user's settings say, UIX-005) – once: changing the message
notifies only those mentioned anew. Somebody who cannot open the project is
not mentioned; the name stays plain text.

Unread
------
:class:`~rentalars.chat.models.ChatReadMark` keeps the newest message a user
has seen. Opening the chat moves the mark; messages of others after it are
unread. The count reaches every project page through the change polling
(UIX-020, :func:`stamp`): the page asks anyway, so the tab costs the page
itself no query.

Photos and videos (UIX-049)
----------------------------------
A message may carry photos and videos – and then needs no text. They are
checked and made smaller by ``chat.media``; a video in the background, the
message says so until it is done. A notification about a message names
them ("1 Foto") – instead of the text when there is none.

Browser views and API call these functions alike (API-002).
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, F, Max, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from rentalars.chat import media
from rentalars.chat.models import EDIT_MINUTES, MAX_LENGTH, AttachmentKind, ChatMessage, ChatReadMark
from rentalars.core.i18n import LazyCall, LocalText

if TYPE_CHECKING:
    from rentalars.accounts.models import User
    from rentalars.projects.models import Project

#: How many messages the chat shows at once; older ones follow with "Ältere Nachrichten".
PAGE_SIZE = 100


# --- Who reads along ---------------------------------------------------------------------------


def display_name(user: Any) -> str:
    """The name a user is shown and mentioned by: first and last name, else the user name."""
    return (user.get_full_name() or "").strip() or user.username


def readers_of(project: Project) -> list[User]:
    """Every active user who can open the project – and so reads its chat (UIX-010, AUT-025).

    Each user carries ``chat_access``, the level in the project: ``DEPLOYMENT``
    for crew who see only the deployment view.

    The rules of ``projects.access.access_level`` for all users at once: a
    role for all projects; or a role for assigned projects with a membership
    of the project (of a subproject: its own, else that of the whole
    project, PRJ-049) or a crew line in it (the deployment view, AUT-018).
    AUT-031: a role for "overview only" gives the deployment view at most
    (``role_limit``); the person responsible for a service case and the
    people taking part in it read its chat whatever their roles say.
    """
    from rentalars.accounts.models import User
    from rentalars.accounts.rights import Level, Module, rights_of
    from rentalars.projects.access import _MEMBERSHIP_ACCESS, ProjectAccess, _from_module_level, role_limit
    from rentalars.projects.models import CrewLine, ProjectMembership

    users = list(User.objects.filter(is_active=True).prefetch_related("roles").order_by("username"))
    project_ids = [project.pk] + ([project.parent_id] if project.parent_id else [])
    memberships: dict[int, dict[int, str]] = {}
    for user_id, project_id, level in ProjectMembership.objects.filter(project_id__in=project_ids).values_list(
        "user_id", "project_id", "level"
    ):
        memberships.setdefault(user_id, {})[project_id] = level
    crew = set(
        CrewLine.objects.filter(project=project, person__user__isnull=False).values_list("person__user_id", flat=True)
    )
    # AUT-033 (PRJ-108): who works on a service case – the person responsible and the people taking part.
    workers: set[int] = set()
    if project.is_service_case:
        workers = set(project.participants.filter(person__user__isnull=False).values_list("person__user_id", flat=True))
        if project.manager_id:
            workers.add(project.manager_id)
    readers = []
    for user in users:
        rights = rights_of(user)
        everywhere = _from_module_level(rights.level_everywhere(Module.PROJECTS))
        access = everywhere
        if rights.is_limited_to_assigned_projects(Module.PROJECTS):
            own = memberships.get(user.pk, {})
            level = own.get(project.pk, own.get(project.parent_id or 0))
            assigned = _MEMBERSHIP_ACCESS.get(level or "", ProjectAccess.NONE)
            if assigned < ProjectAccess.DEPLOYMENT and user.pk in crew:
                assigned = ProjectAccess.DEPLOYMENT
            access = max(everywhere, min(role_limit(rights), assigned))
        if access < ProjectAccess.READ and user.pk in workers and rights.case_work >= Level.READ:
            access = ProjectAccess.READ
        if access >= ProjectAccess.DEPLOYMENT:
            user.chat_access = access
            readers.append(user)
    readers.sort(key=lambda user: display_name(user).lower())
    return readers


# --- Mentions ------------------------------------------------------------------------------------------


def mentioned_in(text: str, readers: list[User]) -> list[User]:
    """The readers a text mentions with ``@name`` or ``@username`` (UIX-010).

    Longer names are looked for first; a name found blanks its place, so that
    ``@Anna Becker`` does not mention the user ``anna`` as well. An ``@`` inside
    a word – a mail address – mentions nobody.
    """
    tokens: list[tuple[str, User]] = []
    for user in readers:
        for name in {display_name(user), user.username}:
            if name:
                tokens.append((name, user))
    tokens.sort(key=lambda token: -len(token[0]))
    working = text
    found: dict[int, User] = {}
    for name, user in tokens:
        pattern = re.compile(r"(?<![\w@.])@" + re.escape(name) + r"(?![\w])", re.IGNORECASE)
        match = pattern.search(working)
        if match is None:
            continue
        found.setdefault(user.pk, user)
        working = pattern.sub(lambda hit: " " * len(hit.group(0)), working)
    return list(found.values())


def notification_body(message: ChatMessage, photos: int = 0, videos: int = 0) -> str | LocalText:
    """The text of a notification about a message: its text, and what it carries (UIX-049).

    "1 Foto" alone when the message has no text; otherwise the text with
    "(2 Fotos, 1 Video)" below it – in the language of each reader (UIX-029).
    """
    text = message.text[:1000]
    if not photos and not videos:
        return text
    carried = LazyCall(media.summary, photos, videos)
    if not text:
        return LocalText("%(media)s", media=carried)
    return LocalText("%(text)s\n(%(media)s)", text=text, media=carried)


def _notify_mentions(message: ChatMessage, users: list[User], author: Any, *, photos: int = 0, videos: int = 0) -> None:
    """Tell the mentioned users (UIX-005, kind ``chat_mention``)."""
    if not users:
        return
    from rentalars.notifications.models import Kind
    from rentalars.notifications.services import notify

    project = message.project
    notify(
        users,
        Kind.CHAT_MENTION,
        # UIX-029: in the language of each one mentioned.
        LocalText(
            gettext_lazy("%(author)s mentioned you in the chat of %(project)s"),
            author=message.author_name,
            project=project,
        ),
        body=notification_body(message, photos, videos),
        url=reverse("chat:project", args=[project]) + f"#m{message.pk}",
        project=project,
        exclude=author,
    )


# --- Writing --------------------------------------------------------------------------------------


def _clean(text: str, *, may_be_empty: bool = False) -> str:
    """The text as stored; ``may_be_empty``: the message carries photos or videos (UIX-049)."""
    text = (text or "").replace("\r\n", "\n").strip()
    if not text and not may_be_empty:
        raise ValidationError({"text": _("Write a message first.")})
    if len(text) > MAX_LENGTH:
        raise ValidationError({"text": _("A message may have at most %(count)d characters.") % {"count": MAX_LENGTH}})
    return text


def post_message(
    project: Project, *, user: Any, text: str, readers: list[User] | None = None, files: Sequence[Any] = ()
) -> ChatMessage:
    """Write a message into the chat of a project and notify the mentioned (UIX-010).

    UIX-049: ``files`` are uploaded photos and videos; with them
    the text may be empty. They are checked and photos made smaller before
    the message is written – outside its transaction –, videos in the
    background afterwards.

    The caller has checked that the user can open the project.

    Raises:
        ValidationError: The text is empty or too long (``text``); a file is
            not accepted (``files``, see ``chat.media.prepare_files``).
    """
    files = [uploaded for uploaded in files if uploaded]
    text = _clean(text, may_be_empty=bool(files))
    prepared = media.prepare_files(files) if files else []
    try:
        return _write(project, user=user, text=text, readers=readers, prepared=prepared)
    except BaseException:
        media.discard(prepared)
        raise


@transaction.atomic
def _write(
    project: Project, *, user: Any, text: str, readers: list[User] | None, prepared: Sequence[Any]
) -> ChatMessage:
    """Store a message with its checked files, notify the mentioned, mark it read for its author."""
    message = ChatMessage.objects.create(project=project, author=user, author_name=display_name(user)[:150], text=text)
    attached = media.attach(message, prepared) if prepared else []
    try:
        mentioned = mentioned_in(text, readers if readers is not None else readers_of(project))
        if mentioned:
            message.mentioned.set(mentioned)
        kinds = [item.kind for item in prepared]
        _notify_mentions(
            message,
            [person for person in mentioned if person.pk != user.pk],
            user,
            photos=kinds.count(AttachmentKind.PHOTO),
            videos=kinds.count(AttachmentKind.VIDEO),
        )
        # One's own message is read.
        mark_read(project, user, up_to=message.pk)
    except BaseException:
        # The message is not written: its stored photos go as well (the waiting videos go in post_message).
        media.remove_stored(attached)
        raise
    return message


def can_change(message: ChatMessage, user: Any, now: datetime.datetime | None = None) -> bool:
    """Whether the user may still change or delete the message: the author, within :data:`EDIT_MINUTES`."""
    if message.author_id is None or message.author_id != getattr(user, "pk", None):
        return False
    return (now or timezone.now()) - message.created_at <= datetime.timedelta(minutes=EDIT_MINUTES)


def _check_change(message: ChatMessage, user: Any) -> None:
    if message.author_id != getattr(user, "pk", None):
        raise PermissionDenied(_("Only the author can change a message."))
    if not can_change(message, user):
        raise ValidationError(
            _("A message can only be changed within %(minutes)d minutes after writing.") % {"minutes": EDIT_MINUTES}
        )


@transaction.atomic
def edit_message(message: ChatMessage, *, user: Any, text: str) -> ChatMessage:
    """Change one's own message within :data:`EDIT_MINUTES` minutes; new mentions are notified (UIX-010).

    Raises:
        PermissionDenied: The user did not write it.
        ValidationError: Too late, or the text is empty or too long.
    """
    _check_change(message, user)
    # UIX-049: a message with photos or videos may lose its text.
    text = _clean(text, may_be_empty=message.attachments.exists())
    if text == message.text:
        return message
    message.text = text
    message.edited_at = timezone.now()
    # UIX-010: counted in the database, so that two changes at once both count.
    message.revision = F("revision") + 1
    message.save(update_fields=["text", "edited_at", "revision"])
    message.refresh_from_db(fields=["revision"])
    before = set(message.mentioned.values_list("pk", flat=True))
    mentioned = mentioned_in(text, readers_of(message.project))
    message.mentioned.set(mentioned)
    _notify_mentions(
        message, [person for person in mentioned if person.pk not in before and person.pk != user.pk], user
    )
    return message


def delete_message(message: ChatMessage, *, user: Any) -> None:
    """Delete one's own message within :data:`EDIT_MINUTES` minutes (UIX-010).

    Its photos and videos go with it (UIX-049; ``chat.media.files_deleted``).

    Raises:
        PermissionDenied: The user did not write it.
        ValidationError: Too late.
    """
    _check_change(message, user)
    message.delete()


# --- Reading ------------------------------------------------------------------------------------------


@dataclass
class Page:
    """Messages of a chat as shown: oldest first, and whether older ones exist."""

    messages: list[ChatMessage]
    has_older: bool


def messages_of(project: Project, *, before: int | None = None, limit: int = PAGE_SIZE) -> Page:
    """The newest ``limit`` messages of a chat (before the message ``before``), oldest first."""
    rows = (
        ChatMessage.objects.filter(project=project)
        .select_related("author")
        .prefetch_related("mentioned", "attachments")  # UIX-049: photos and videos
    )
    if before:
        rows = rows.filter(pk__lt=before)
    newest_first = list(rows.order_by("-pk")[: limit + 1])
    has_older = len(newest_first) > limit
    messages = list(reversed(newest_first[:limit]))
    media.expire_stuck(messages)
    return Page(messages=messages, has_older=has_older)


def mark_read(project: Project, user: Any, *, up_to: int | None = None) -> int:
    """Note that the user has read the chat up to a message – the newest without ``up_to``; returns it.

    UIX-010: ``up_to`` is taken down to the newest message *of this
    chat* that is not after it – an ID beyond the newest message, or of
    another chat, never marks messages as read that are written later. The
    mark only moves forward.
    """
    if not getattr(user, "pk", None):
        return 0
    messages = ChatMessage.objects.filter(project=project)
    if up_to is not None:
        messages = messages.filter(pk__lte=up_to)
    up_to = messages.aggregate(newest=Max("pk"))["newest"] or 0
    mark, created = ChatReadMark.objects.get_or_create(
        user=user, project=project, defaults={"last_read_id": up_to, "read_at": timezone.now()}
    )
    if not created and up_to > mark.last_read_id:
        # Only forward, also when two requests mark at once.
        ChatReadMark.objects.filter(pk=mark.pk, last_read_id__lt=up_to).update(
            last_read_id=up_to, read_at=timezone.now()
        )
    return max(up_to, mark.last_read_id)


def _unread_filter(project_id: int, user: Any) -> Q:
    mark = ChatReadMark.objects.filter(project_id=project_id, user_id=user.pk).values("last_read_id")[:1]
    return Q(pk__gt=Coalesce(Subquery(mark), 0)) & ~Q(author_id=user.pk)


def unread_count(project: Project, user: Any) -> int:
    """How many messages of others the user has not seen in the chat of a project."""
    return ChatMessage.objects.filter(project=project).filter(_unread_filter(project.pk, user)).count()


def stamp(project_id: int, user: Any) -> str:
    """The state of a chat for the change polling (UIX-020): ``<content>~<unread>``, one query.

    The part before ``~`` changes with every new, changed or deleted message;
    the part after it is the user's unread count, for the tab of every project page.

    UIX-010: changes are counted, not timed – ``<newest>-<count>-<sum
    of revisions>``. With the newest time of change in whole seconds
    alone, a second change within the same second, or the change of a
    message older than the last changed one, did not move the stamp. A new
    message moves the newest ID, a deleted one the count, a change the sum.
    """
    found = ChatMessage.objects.filter(project_id=project_id).aggregate(
        newest=Max("pk"),
        count=Count("pk"),
        revisions=Sum("revision"),
        unread=Count("pk", filter=_unread_filter(project_id, user)),
    )
    return f"{found['newest'] or 0}-{found['count']}-{found['revisions'] or 0}~{found['unread']}"


def forget_author(user: Any, name: str) -> int:
    """NFA-009: the messages of an anonymised person name the new name; returns how many."""
    return ChatMessage.objects.filter(author_id=getattr(user, "pk", None)).update(author_name=name[:150])
