# SPDX-License-Identifier: GPL-3.0-or-later
"""Related projects and service cases (PRJ-119).

The requirement: relations between service cases or projects, with a link to each. A project or service case can be related to several others.

The rules
---------
* A relation joins two of them – project and project, project and service
  case, case and case – and holds both ways (``ProjectRelation``, stored
  once). Each can be related to any number of others. A short note may say
  how they belong together.
* Whole projects and service cases only: a subproject is a part of its whole
  project, which is related instead (:func:`check_relatable`).
* Linking and unlinking need edit access to the project at hand and read
  access to the other one (AUT-025) – whoever links must know what they link
  to. Closed projects can be related all the same: a relation is a reference,
  not a change of the planning (PRJ-009 protects the planning) – a complaint
  of today belongs to the job of last year.
* Who sees the list sees every related project; one the reader may not open
  shows its number only – "Projekt 2027-0042 (kein Zugriff)" –, without name,
  status, note or link, as the fleet shows other projects
  (AUT-016, :class:`RelatedEntry`).
* Both sides note linking and unlinking in their history, with the number of
  the other one only (``project.related``, ``project.unrelated``); a deleted
  project is noted on the other side (``project.relation_deleted``,
  ``models._note_relations_of_deleted_project``).
* Duplicating a project does not copy its relations: the copy is a new job,
  related to nothing yet (``projects.duplicate`` copies what it names). A
  service case turned into a project keeps them – it stays the same record.

Pages (``projects.relation_views``), the API (``projects.relation_api``) and
the companion app (``related`` in the detail of a project or case) use the
functions here (API-002).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, QuerySet
from django.urls import reverse
from django.utils.text import capfirst
from django.utils.translation import gettext as _
from rest_framework import serializers

from rentalars.accounts.rights import Rights
from rentalars.core.audit import record_event
from rentalars.projects import numbers as project_numbers
from rentalars.projects.access import ProjectAccess, access_level, access_of_many, readable_projects
from rentalars.projects.models import Project, ProjectKind, ProjectRelation

#: The longest note of a relation.
NOTE_LENGTH = 200

#: How many projects the type-ahead of "Verknüpfen" suggests.
SUGGESTIONS = 12


def pair(one: Project, other: Project) -> tuple[Project, Project]:
    """The two sides in the order they are stored: the smaller ID first."""
    return (one, other) if one.pk < other.pk else (other, one)


def relations_of(project: Project) -> QuerySet[ProjectRelation]:
    """The relations of a project, with both sides loaded (one query)."""
    return (
        ProjectRelation.objects.filter(Q(first=project) | Q(second=project))
        .select_related("first", "second", "first__customer", "second__customer")
        .order_by("created_at", "pk")
    )


def related_ids(project: Project) -> set[int]:
    """The IDs of the projects related to ``project``."""
    return {
        second if first == project.pk else first
        for first, second in ProjectRelation.objects.filter(Q(first=project) | Q(second=project)).values_list(
            "first_id", "second_id"
        )
    }


def check_relatable(project: Project) -> None:
    """A whole project or a service case can be related; a subproject cannot (its whole project is).

    Raises:
        ValidationError: ``project`` is a subproject.
    """
    if project.parent_id is not None:
        raise ValidationError(
            {
                "project": _(
                    "%(number)s is a subproject. Only whole projects and service cases are related; relate its "
                    "whole project %(whole)s."
                )
                % {"number": project.number, "whole": project.parent.number}
            }
        )


@transaction.atomic
def link(project: Project, other: Project, *, note: str = "", user: Any = None) -> ProjectRelation:
    """Relate two projects or service cases (PRJ-119).

    The rights – edit access to ``project``, read access to ``other`` – are
    checked by the caller (:func:`may_link`), as the services of the planning
    leave them to their views.

    Raises:
        ValidationError: The two are the same, one is a subproject, or they
            are related already.
    """
    if other.pk == project.pk:
        raise ValidationError({"project": _("A project cannot be related to itself.")})
    check_relatable(project)
    check_relatable(other)
    first, second = pair(project, other)
    if ProjectRelation.objects.filter(first=first, second=second).exists():
        raise ValidationError({"project": _("%(number)s is related already.") % {"number": other.number}})
    relation = ProjectRelation(
        first=first,
        second=second,
        note=" ".join((note or "").split())[:NOTE_LENGTH],
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    relation.full_clean()
    relation.save()
    # Both histories, each with the number of the other side only (AUT-016).
    record_event(project, "project.related", {"number": other.number})
    record_event(other, "project.related", {"number": project.number})
    return relation


@transaction.atomic
def unlink(relation: ProjectRelation, *, seen_from: Project | None = None) -> None:
    """End a relation; both sides note it in their history (PRJ-119)."""
    first, second = relation.first, relation.second
    relation.delete()
    near, far = (first, second) if seen_from is None or seen_from.pk == first.pk else (second, first)
    record_event(near, "project.unrelated", {"number": far.number})
    record_event(far, "project.unrelated", {"number": near.number})


# --- Who may do what ------------------------------------------------------------------------------------------


def may_link_from(project: Project) -> bool:
    """Whether relations can be changed from this project at all: edit access, and not a subproject.

    ``project.access`` is the level ``project_for`` noted on it.
    """
    return getattr(project, "access", ProjectAccess.NONE) >= ProjectAccess.EDIT and project.parent_id is None


def other_for(rights: Rights, user: Any, number_or_text: str) -> Project | None:
    """The project to link to from what was chosen or typed: "2027-0042" or "2027-0042 Stadtfest".

    The first word counts; a former number finds the project as well
    (ADM-012). ``None`` if there is no such project or the user may not read
    it – the two look the same, as everywhere (AUT-016).
    """
    words = (number_or_text or "").split()
    project = project_numbers.project_by_number(words[0]) if words else None
    if project is None or access_level(rights, user, project) < ProjectAccess.READ:
        return None
    return project


def suggestions(project: Project, rights: Rights, user: Any, text: str) -> list[Project]:
    """The projects and cases "Verknüpfen" suggests for what was typed: number or name.

    Those the user may read, whole projects and cases only, without the
    project itself and those related already; the latest first.
    """
    text = (text or "").strip()
    if not text:
        return []
    return list(
        readable_projects(rights, user)
        .filter(parent__isnull=True)
        .exclude(pk=project.pk)
        .exclude(pk__in=related_ids(project))
        .filter(project_numbers.matching(text) | Q(name__icontains=text))
        .select_related("customer")
        .order_by("-start", "-pk")[:SUGGESTIONS]
    )


# --- What a page or the API shows -----------------------------------------------------------------------------


@dataclass
class RelatedEntry:
    """One related project as the reader may see it (AUT-016).

    ``visible``: the reader may open it – number, name, kind, status, note
    and link are shown. Otherwise only "Projekt 2027-0042 (kein Zugriff)".
    ``readable``: the reader may read it – needed to unlink (as to link).
    """

    relation: ProjectRelation
    project: Project
    visible: bool
    readable: bool

    @property
    def number(self) -> str:
        """The number of the related project – shown to every reader."""
        return self.project.number

    @property
    def label(self) -> str:
        """Number and name, or the number with "no access"."""
        if self.visible:
            return f"{self.project.number} {self.project.name}"
        return _("Project %(number)s (no access)") % {"number": self.project.number}

    @property
    def name(self) -> str | None:
        """The name, for a reader who may open it."""
        return self.project.name if self.visible else None

    @property
    def kind(self) -> str | None:
        """``project`` or ``service_case``, for a reader who may open it."""
        return self.project.kind if self.visible else None

    @property
    def kind_label(self) -> str:
        """The kind as shown – "Projekt" or "Servicefall" –, empty without access."""
        if not self.visible:
            return ""
        return capfirst(str(ProjectKind(self.project.kind).label))

    @property
    def status(self) -> str | None:
        """The status (of the project, or of the case), for a reader who may open it."""
        if not self.visible:
            return None
        return self.project.case_status if self.project.is_service_case else self.project.status

    @property
    def status_label(self) -> str:
        """The status as shown – "Bestätigt", "Wartet auf eine Antwort" (PRJ-112) –, empty without access."""
        if not self.visible:
            return ""
        if self.project.is_service_case:
            return self.project.case_status_label
        return str(self.project.get_status_display())

    @property
    def status_key(self) -> str:
        """The key the badge colour is chosen by (``status_colour``, ``case_colour``)."""
        return self.status or ""

    @property
    def note(self) -> str:
        """The note of the relation – only next to a project the reader may open."""
        return self.relation.note if self.visible else ""

    @property
    def url(self) -> str:
        """The page of the related project or case, for a reader who may open it."""
        if not self.visible:
            return ""
        if self.project.is_service_case:
            return reverse("projects:case_detail", args=[self.project])
        return reverse("projects:overview", args=[self.project])


def related_entries(project: Project, rights: Rights, user: Any) -> list[RelatedEntry]:
    """The projects related to ``project``, each as far as the reader may see it, by number.

    Three queries at most: the relations with both sides, and the access to
    the others (``access.access_of_many``, NFA-014).
    """
    relations = list(relations_of(project))
    if not relations:
        return []
    others = [relation.other_than(project) for relation in relations]
    levels = access_of_many(rights, user, [other.pk for other in others])
    entries = [
        RelatedEntry(
            relation=relation,
            project=other,
            visible=levels.get(other.pk, ProjectAccess.NONE) >= ProjectAccess.DEPLOYMENT,
            readable=levels.get(other.pk, ProjectAccess.NONE) >= ProjectAccess.READ,
        )
        for relation, other in zip(relations, others, strict=True)
    ]
    return sorted(entries, key=lambda entry: entry.project.number)


def entry_document(entry: RelatedEntry) -> dict[str, Any]:
    """One related project for the API and the companion app – the same as the page shows (AUT-016)."""
    return {
        "id": entry.relation.pk,
        "project": entry.project.pk if entry.visible else None,
        "number": entry.number,
        "name": entry.name,
        "kind": entry.kind,
        "status": entry.status,
        "status_label": entry.status_label or None,
        "accessible": entry.visible,
        "note": entry.note,
        # As every moment of the API: ISO 8601 in the time zone of the installation.
        "created_at": serializers.DateTimeField().to_representation(entry.relation.created_at),
    }
