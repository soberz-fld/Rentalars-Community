# SPDX-License-Identifier: GPL-3.0-or-later
"""The deployment view of a project as data: for the page, its PDF and a mail (AUT-025, PRJ-081).

What crew and freelancers see of a project (AUT-023): when and where, the
course, the venue, their own crew lines and times, the colleagues on the
same job with the contact data those released (PER-019). The tab
"Deployment" shows it (``projects.crew_views.deployment``), and the PDF
"Einsatzübersicht" prints exactly the same (``documents.deployment``,
PRJ-081) – for the person who opens it.

Who sees which contact data
---------------------------
Project management (edit access) and personnel planning see every phone
number and e-mail address; everybody else those a colleague released for
colleagues, and their own. The PDF that goes along with a mail is
:func:`neutral`: it is not the view of the sender but of any colleague –
no own deployment, no own times, contact data only as released. A mail
leaves the house; a number somebody kept to the office must not go with it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rentalars.accounts.rights import Module, Rights
from rentalars.projects.access import ProjectAccess, access_level, person_of
from rentalars.projects.models import CrewLine, Project

#: What a crew line of the deployment view is loaded with: function, person, and the vehicle (LOG-008).
CREW_RELATED = ("job_function", "person", "vehicle_line", "vehicle_line__item__vehicle", "vehicle_line__supplier")


@dataclass
class CrewRow:
    """One crew line as the deployment view shows it, with the contact data the viewer may see (PER-019)."""

    line: CrewLine
    person: Any
    is_self: bool
    phone: str = ""
    email: str = ""


@dataclass
class DeploymentPicture:
    """Everything the deployment view of one project shows to one viewer (AUT-025)."""

    project: Project
    #: The person linked to the viewer, if any; ``None`` for the neutral view of a mail.
    viewer: Any
    #: Every crew line, in the order of time (PRJ-019).
    rows: list[CrewRow]
    #: The phases of the project (PRJ-006).
    phases: list[Any]
    #: The viewer's own time entries in the project, newest first (ZEI); empty without the right to read them.
    own_entries: list[Any] = field(default_factory=list)
    #: ZEI-019: the viewer's own expenses in the project, newest first; empty without the right to read times.
    own_expenses: list[Any] = field(default_factory=list)
    #: True if the viewer sees every phone number and e-mail address (PER-019).
    sees_all_contacts: bool = False

    @property
    def own_rows(self) -> list[CrewRow]:
        """The viewer's own crew lines."""
        return [row for row in self.rows if row.is_self]


def sees_all_contacts(rights: Rights, access: ProjectAccess) -> bool:
    """PER-019: project management and personnel planning see contact data regardless of the release."""
    return access >= ProjectAccess.EDIT or rights.can_read(Module.PERSONNEL)


def _row(line: CrewLine, *, all_contacts: bool, viewer: Any) -> CrewRow:
    person = line.person
    is_self = viewer is not None and person is not None and person.pk == viewer.pk
    phone = email = ""
    if person is not None:
        if all_contacts or is_self or person.share_phone:
            phone = person.phone
        if all_contacts or is_self or person.share_email:
            email = person.email
    return CrewRow(line=line, person=person, is_self=is_self, phone=phone, email=email)


def deployment_picture(project: Project, *, rights: Rights, user: Any) -> DeploymentPicture:
    """The deployment view of a project for one user (AUT-025, PRJ-081).

    Args:
        project: The project; ``project.access`` if a caller noted it, else
            it is asked here.
        rights: The rights of the user.
        user: The user who looks.
    """
    access = getattr(project, "access", None)
    if access is None:
        access = access_level(rights, user, project)
    viewer = person_of(user)
    all_contacts = sees_all_contacts(rights, access)
    # LOG-008: with the vehicle each person travels with.
    lines = project.crew_lines.select_related(*CREW_RELATED).order_by("start", "position", "id")
    own_entries: list[Any] = []
    own_expenses: list[Any] = []
    if viewer is not None and rights.can_read(Module.TIME_TRACKING):
        own_entries = list(
            project.time_entries.filter(person=viewer).select_related("job_function").order_by("-start", "id")
        )
        from rentalars.timetracking.display import mark_periods

        mark_periods(own_entries)  # ZEI-025: "Teil 1 von 2" at the parts of a divided period
        own_expenses = list(project.expenses.filter(person=viewer).order_by("-date", "-id"))
    return DeploymentPicture(
        project=project,
        viewer=viewer,
        rows=[_row(line, all_contacts=all_contacts, viewer=viewer) for line in lines],
        phases=list(project.phases.select_related("venue_site")),
        own_entries=own_entries,
        own_expenses=own_expenses,
        sees_all_contacts=all_contacts,
    )


def neutral(project: Project) -> DeploymentPicture:
    """The deployment view as any colleague sees it – for a mail (PRJ-081).

    No own deployment and no own times; contact data only as the people
    released them for colleagues (PER-019).
    """
    lines = project.crew_lines.select_related(*CREW_RELATED).order_by("start", "position", "id")
    return DeploymentPicture(
        project=project,
        viewer=None,
        rows=[_row(line, all_contacts=False, viewer=None) for line in lines],
        phases=list(project.phases.select_related("venue_site")),
    )
