# SPDX-License-Identifier: GPL-3.0-or-later
"""Nested groups (PRJ-037): order, depth and names of the groups of a project as a tree.

"Licht > Front-Traverse > Traverse 1": a group can stand inside another
group. The data model has had ``Group.parent`` from the beginning; this
module turns the groups of a project into the tree the pages, the price
calculation, the documents and the packlists walk through.

The rules
---------
* **Depth.** At most :data:`MAX_DEPTH` levels: a top-level group, its
  subgroups and their subgroups. Deeper trees are refused when a group is
  placed (``Group.clean``), so no page has to cope with them.
* **No cycles.** A group can never be placed inside itself or one of its
  own subgroups (``Group.clean``). Should the database ever hold one
  anyway, :class:`GroupTree` shows the groups of the cycle at the top level
  instead of losing them.
* **Order.** ``Group.position`` counts among the siblings – the groups with
  the same parent. The order of the whole project is the order of a book's
  table of contents: a group, then its subgroups, then the next group.
* **Lines in parent groups.** A group may hold lines *and* subgroups:
  "Licht" can contain the lighting desk and the subgroups "Front" and
  "Rear". Its own lines come first, then the subgroups.

Building the tree needs no database query: it works on the groups the
caller has loaded and puts each group's parent into Django's cache, so that
``group.parent`` – and everything that walks up from a group, like
``Group.path`` or ``Group.counts_toward_total`` – asks the database nothing
either (NFA-014).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rentalars.projects.models import Group

#: How many levels deep groups can be nested (PRJ-037): Licht › Front › Traverse 1.
MAX_DEPTH = 3

#: Between the names of a path: "Licht › Front-Traverse".
PATH_SEPARATOR = " › "


class GroupTree:
    """The groups of one project, arranged as a tree (PRJ-037).

    Args:
        groups: The groups of the project, in any order. A group whose
            parent is not among them counts as a top-level group.
    """

    def __init__(self, groups: Iterable[Group]) -> None:
        self.groups: list[Group] = list(groups)
        self.by_id: dict[int, Group] = {group.pk: group for group in self.groups}
        parent_field = type(self.groups[0])._meta.get_field("parent") if self.groups else None
        children: dict[int | None, list[Group]] = defaultdict(list)
        for group in self.groups:
            parent = self.by_id.get(group.parent_id) if group.parent_id else None
            if parent_field is not None and parent is not None:
                # Walking up from a group (path, effective kind) costs no query from now on.
                parent_field.set_cached_value(group, parent)
            children[parent.pk if parent is not None else None].append(group)
        for siblings in children.values():
            siblings.sort(key=lambda group: (group.position, group.pk))
        self._children = children

        #: Every group once, in the order of the planning: parent, its subgroups, next parent.
        self.ordered: list[Group] = []
        #: Depth of each group: 0 for a top-level group.
        self.depth: dict[int, int] = {}
        roots = list(children[None])
        self._walk(roots)
        # A cycle in the data (never created by Rentalars) would hide its groups; show them at the top.
        for group in self.groups:
            if group.pk not in self.depth:
                self._walk([group])
        #: Position of each group in :attr:`ordered`.
        self.index: dict[int, int] = {group.pk: index for index, group in enumerate(self.ordered)}

    def _walk(self, roots: list[Group]) -> None:
        stack: list[tuple[Group, int]] = [(group, 0) for group in reversed(roots)]
        while stack:
            group, depth = stack.pop()
            if group.pk in self.depth:
                continue
            self.depth[group.pk] = depth
            self.ordered.append(group)
            stack.extend((child, depth + 1) for child in reversed(self._children.get(group.pk, [])))

    def __iter__(self) -> Iterator[Group]:
        return iter(self.ordered)

    def __len__(self) -> int:
        return len(self.ordered)

    @property
    def roots(self) -> list[Group]:
        """The top-level groups in their order."""
        return [group for group in self.ordered if self.parent_of(group) is None]

    def parent_of(self, group: Group) -> Group | None:
        """The group's parent, if it is part of the tree."""
        if self.depth.get(group.pk, 0) == 0:
            return None
        return self.by_id.get(group.parent_id) if group.parent_id else None

    def ancestors(self, group: Group) -> list[Group]:
        """The groups above a group, the nearest first."""
        found: list[Group] = []
        current = self.parent_of(group)
        while current is not None and current not in found:
            found.append(current)
            current = self.parent_of(current)
        return found

    def descendants(self, group: Group) -> list[Group]:
        """All groups below a group, in the order of the planning."""
        start = self.index[group.pk]
        depth = self.depth[group.pk]
        found = []
        for other in self.ordered[start + 1 :]:
            if self.depth[other.pk] <= depth:
                break
            found.append(other)
        return found

    def subtree_ids(self, group: Group) -> set[int]:
        """The IDs of a group and all groups below it."""
        return {group.pk} | {other.pk for other in self.descendants(group)}

    def height(self, group: Group) -> int:
        """How many levels a group and its subgroups take: 1 for a group without subgroups."""
        depth = self.depth[group.pk]
        return 1 + max((self.depth[other.pk] - depth for other in self.descendants(group)), default=0)

    def path(self, group: Group) -> str:
        """The names from the top down to the group: "Licht › Front-Traverse"."""
        names = [ancestor.name for ancestor in reversed(self.ancestors(group))]
        return PATH_SEPARATOR.join([*names, group.name])

    def possible_parents(self, group: Group | None) -> list[Group]:
        """The groups a group can be moved into without breaking a rule of PRJ-037.

        Not the group itself, none of its subgroups, and no group so deep
        that the group with its subgroups would go beyond :data:`MAX_DEPTH`.
        ``None`` asks for a new group: every group up to the second-lowest
        level.
        """
        if group is None or group.pk not in self.depth:
            return [other for other in self.ordered if self.depth[other.pk] + 1 < MAX_DEPTH]
        own = self.subtree_ids(group)
        height = self.height(group)
        return [
            other for other in self.ordered if other.pk not in own and self.depth[other.pk] + 1 + height <= MAX_DEPTH
        ]


def ordered_groups(groups: Iterable[Group]) -> list[Group]:
    """The groups in the order of the planning, with their parents cached (see :class:`GroupTree`)."""
    return GroupTree(groups).ordered
