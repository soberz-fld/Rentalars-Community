# SPDX-License-Identifier: GPL-3.0-or-later
"""Messages "with lock" and open messages of the correspondence (EML-055; EML-029, AUT-033).

The requirement: messages of the correspondence can be marked "with lock" (internal and public), which controls whether the crew may read the message or only those with the right to see financial data. Decided: open for the crew; new messages start with the lock.

Who reads what
--------------
Reading the correspondence of a project *at all* is decided as in ``projects.case_work``: read
access to the project and the special right "read correspondence" – or, in a service case, working on it as the
person responsible or somebody taking part. This is called the *basis* here.

* A message **with lock** is read by those with the basis who also have the special right "See prices and
  calculation" (``SpecialRight.PRICES``) – the people who may see financial data.
* An **open** message is read by everybody with the basis and, in addition, by the **crew**: the users whose
  person is planned in a crew line of the project and who see the project – the deployment view is enough, also
  for a role "overview without planning" (AUT-031). The crew only reads. Only a
  confirmed line counts – accepted, or planned firmly (:data:`CONFIRMED_REQUESTS`); a line not asked, not answered
  or declined lets the person open the project as before, but not its correspondence.

So whoever reads the correspondence without the price right reads its open messages only – in a service case he
works on, he answers those.

Who writes and locks
--------------------
* Writing mails and notes: the basis and the right to write, as in ``projects.case_work`` – never the
  crew by being planned.
* Setting or taking away the lock: who may write and sees prices (:attr:`Correspondence.may_lock`). He chooses
  it for every new mail, answer and note; the choice starts as the mail settings say for the project or case.
* How new messages start – received, written, noted, inquiries taken over, the first mail of a case made from a
  mail – is a setting (:func:`default_lock`): in projects with lock, in service cases open (correspondence in
  projects is always confidential, in service cases normally not). A message moved between a case and a
  project keeps its state.
* An answer to a message with lock starts with the lock (:func:`answer_lock`) – it quotes that message; a mail
  coming in as an answer to a message with lock of the same project is stored with the lock (:func:`answers_locked`).
* A writer without the price right writes open messages: with a lock he could not read his own message
  (:meth:`Correspondence.new_lock`).

A message the user may not read does not exist for him (404) – in the lists, on its pages, its attachments, in
the API, the search, the subrental pages and the notifications. Summaries by AI read every message; they are for
those who read every message (``ai``).

Taking the lock away tells the crew who could not read the message before (:func:`tell_crew`), once per message
and person.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.db.models import QuerySet
from django.urls import reverse
from django.utils.translation import gettext_lazy

from rentalars.accounts.rights import Level, Rights, SpecialRight, request_rights, rights_of
from rentalars.core.i18n import LocalText
from rentalars.mail.models import ProjectMail
from rentalars.projects.access import ProjectAccess, access_level, person_of, works_on_case
from rentalars.projects.models import RequestStatus


class Reach(enum.IntEnum):
    """How much of the correspondence of a project a user reads (EML-055)."""

    NONE = 0
    #: The open messages only: the crew, or a reader without the price right.
    OPEN = 1
    #: Open messages and those with lock.
    ALL = 2


@dataclass(frozen=True)
class Correspondence:
    """What a user may do with the correspondence of one project (EML-055; EML-029, AUT-033)."""

    reach: Reach = Reach.NONE
    #: Reads the correspondence: the correspondence right, or working on the service case.
    basis: bool = False
    #: Writes mails and notes (the basis and the right to write; never the crew by being planned).
    may_write: bool = False
    #: Sets and takes away the lock: may write and sees prices.
    may_lock: bool = False

    @property
    def reads_any(self) -> bool:
        """Whether the user reads any of the correspondence – the tab "Korrespondenz"."""
        return self.reach >= Reach.OPEN

    @property
    def reads_all(self) -> bool:
        """Whether the user reads every message, also those with lock."""
        return self.reach >= Reach.ALL

    def may_read(self, mail: ProjectMail) -> bool:
        """Whether the user reads this message of the project – and its attachments."""
        return self.reach >= (Reach.ALL if mail.locked else Reach.OPEN)

    def readable(self, mails: QuerySet[ProjectMail]) -> QuerySet[ProjectMail]:
        """Narrow mails of the project to those the user reads."""
        if self.reach >= Reach.ALL:
            return mails
        if self.reach >= Reach.OPEN:
            return mails.filter(locked=False)
        return mails.none()

    def new_lock(self, wanted: bool | None, project: Any) -> bool:
        """The lock of a new message by this user: his choice, else the default of the project; open if he cannot lock."""
        if not self.may_lock:
            return False
        return default_lock(project) if wanted is None else bool(wanted)


#: Nothing of the correspondence.
NOTHING = Correspondence()


def default_lock(project: Any) -> bool:
    """Whether a new message of this project or service case starts with the lock – the mail settings say."""
    from rentalars.mail.models import MailSettings

    settings = MailSettings.load()
    return settings.lock_new_in_cases if project.is_service_case else settings.lock_new_in_projects


def answer_lock(answer_to: ProjectMail | None, project: Any) -> bool:
    """How a new mail starts: as an answer to a message with lock with the lock, else :func:`default_lock`.

    EML-055: an answer quotes the message it answers – started open, it would let the crew read what
    was locked. The writer may still take the lock off (``Correspondence.new_lock``).
    """
    if answer_to is not None and answer_to.locked:
        return True
    return default_lock(project)


def answers_locked(project: Any, keys: Iterable[str]) -> bool:
    """Whether a mail coming in answers a message with lock of this project – by In-Reply-To or References.

    EML-055: such an answer is stored with the lock (``mail.fetching.import_mail``).
    """
    keys = [key for key in keys if key]
    if not keys or project.pk is None:
        return False
    return ProjectMail.objects.filter(project_id=project.pk, message_key__in=keys, locked=True).exists()


#: EML-055: a crew line counts for the correspondence once the person takes the deployment – accepted, or
#: planned firmly (``CrewLine.is_confirmed``); not asked, asked without answer or declined does not.
CONFIRMED_REQUESTS = (RequestStatus.ACCEPTED, RequestStatus.FIRM)


def planned_in(user: Any, project: Any) -> bool:
    """Whether the person of the user is planned in a confirmed crew line of this project (AUT-018) – "the crew".

    EML-055: only a line the person accepted or was planned on firmly counts (:data:`CONFIRMED_REQUESTS`).
    Who opens the project (the deployment view) does not change with it.
    """
    person = person_of(user)
    return (
        person is not None
        and project.pk is not None
        and project.crew_lines.filter(person=person, request_status__in=CONFIRMED_REQUESTS).exists()
    )


def correspondence_for(
    rights: Rights,
    user: Any,
    project: Any,
    *,
    access: ProjectAccess | None = None,
    works: bool | None = None,
    may_work: bool | None = None,
) -> Correspondence:
    """What the user may do with the correspondence of the project; see the rules at the top of this module.

    Args:
        rights: The rights of the user (of the request, or ``rights_of`` for a notification).
        user: The user.
        project: The project or service case.
        access: The user's access to the project, if known (``project_for`` writes it onto the project).
        works: Whether the user works on the service case, if known (``note_case_work``).
        may_work: Whether he may change it as somebody working on it, if known.
    """
    if not getattr(user, "is_authenticated", False):
        return NOTHING
    if access is None:
        access = access_level(rights, user, project)
    if access == ProjectAccess.NONE:
        return NOTHING
    if works is None:
        works = rights.case_work >= Level.READ and works_on_case(user, project)
    if may_work is None:
        may_work = works and rights.case_work >= Level.WRITE
    reads_right = rights.has(SpecialRight.CORRESPONDENCE_READ)
    basis = (access >= ProjectAccess.READ and reads_right) or bool(works)
    if basis:
        prices = rights.has(SpecialRight.PRICES)
        # As ``projects.case_work.may_write_correspondence``: both rights – or changing the service case one works on.
        writes = (reads_right and rights.has(SpecialRight.CORRESPONDENCE_WRITE)) or bool(may_work)
        return Correspondence(
            reach=Reach.ALL if prices else Reach.OPEN, basis=True, may_write=writes, may_lock=writes and prices
        )
    if access >= ProjectAccess.DEPLOYMENT and planned_in(user, project):
        return Correspondence(reach=Reach.OPEN)
    return NOTHING


def correspondence_of(request: Any, project: Any) -> Correspondence:
    """:func:`correspondence_for` the user of a request – kept on the project object for the request."""
    known = getattr(project, "_correspondence", None)
    if known is not None and known[0] == id(request):
        return known[1]
    found = correspondence_for(
        request_rights(request),
        request.user,
        project,
        access=getattr(project, "access", None),
        works=getattr(project, "works_on_case", None),
        may_work=getattr(project, "may_work_on_case", None),
    )
    project._correspondence = (id(request), found)
    return found


def readers(mail: ProjectMail, users: Iterable[Any]) -> list[Any]:
    """Of these users those who read the message – for the notifications about it."""
    project = mail.project
    return [
        user for user in users if user is not None and correspondence_for(rights_of(user), user, project).may_read(mail)
    ]


def crew_of(project: Any) -> list[Any]:
    """The active users of the people planned in the project with a confirmed line – the crew of the correspondence.

    EML-055: as:func:`planned_in` – only accepted or firm lines; the notifications of changes to the project
    keep telling everybody planned (``notifications.services.crew_users``).
    """
    from rentalars.accounts.models import User

    if project.pk is None:
        return []
    # One filter: the project and the request status are those of the same crew line.
    users = User.objects.filter(
        is_active=True,
        person__crew_lines__project=project,
        person__crew_lines__request_status__in=CONFIRMED_REQUESTS,
    )
    return list(users.distinct())


@transaction.atomic
def set_lock(mail: ProjectMail, locked: bool, *, user: Any = None) -> bool:
    """Put the lock on a message or take it away (EML-055); the change log of the project notes it.

    The caller checked :attr:`Correspondence.may_lock`. Taking the lock away tells the crew (:func:`tell_crew`).

    Returns:
        Whether the message changed.
    """
    locked = bool(locked)
    if mail.locked == locked:
        return False
    mail.locked = locked
    mail.save(update_fields=["locked"])
    if not locked:
        tell_crew(mail, exclude=user)
    return True


def tell_crew(mail: ProjectMail, *, exclude: Any = None) -> int:
    """Tell the crew about a message that is open now – those who could not read it before, once each.

    The notification is the one of a new mail (``Kind.NEW_MAIL``), so that each person decides in the settings
    how it reaches him. A message opened, locked and opened again is told only once.

    Returns:
        How many people were told.
    """
    from rentalars.notifications.models import Kind, Notification
    from rentalars.notifications.services import notify

    project = mail.project
    url = reverse("mail:detail", args=[project, mail.pk])
    crew = [
        user
        for user in crew_of(project)
        if correspondence_for(rights_of(user), user, project).reach == Reach.OPEN
        and (exclude is None or user.pk != exclude.pk)
    ]
    told = set(
        Notification.objects.filter(kind=Kind.NEW_MAIL, url=url, user__in=[user.pk for user in crew]).values_list(
            "user_id", flat=True
        )
    )
    crew = [user for user in crew if user.pk not in told]
    if not crew:
        return 0
    # UIX-029: written for each recipient in his language.
    notify(
        crew,
        Kind.NEW_MAIL,
        LocalText(
            gettext_lazy("New message for the crew of %(project)s: %(subject)s"),
            project=project,
            subject=mail.display_subject,
        ),
        body=LocalText(gettext_lazy("From %(sender)s"), sender=mail.sender_label or mail.sender_name),
        url=url,
        project=project,
    )
    return len(crew)
