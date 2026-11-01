# SPDX-License-Identifier: GPL-3.0-or-later
"""Categories of the notification kinds (UIX-039).

Every kind of notification belongs to one category – "Projekt", "Personal",
"Material" or "System". The category is code, not data: it follows from the
kind and is never stored. The settings page groups the kinds by category in
this order, the list of notifications filters by it, and the API delivers it
with every notification and every setting.

Which kind goes where:

* **Projekt** – what happens in a project or service case and the people
  working on it: deployment requests and their answers, a mention in the
  chat, follow-ups, new mail, changes, shortages, and the messages of
  automations (their triggers are project events: an inquiry, an answer, a
  follow-up, a status).
* **Personal** – what concerns a person as a member of staff rather than a
  project: the own expenses, expiring qualifications; also (ZEI-031, ZEI-029) the own
  times approved, corrected or sent back, and the times waiting for one's
  approval. The change of one's deployment (PRJ-118) is "Projekt", next to
  the requests.
* **Material** – the warehouse: defects, stock below the minimum,
  inspections due.
* **System** – the running of the installation: problems fetching mails,
  errors of the application, a failing own calendar, tasks in the background.
  UIX-052: the finished task comes first and names the tasks of the AI
  (summary, reply draft, reading an invoice): the user had not found it.

A kind added later without an entry here counts as "Projekt" (most new
kinds are), and a test asks for the entry.
"""

from __future__ import annotations

from collections.abc import Iterable

from django.utils.translation import pgettext_lazy

from rentalars.notifications.models import Kind


class Category:
    """The categories, in the order the settings page shows them."""

    PROJECT = "project"
    PERSONNEL = "personnel"
    MATERIAL = "material"
    SYSTEM = "system"


#: ``(value, label)`` in display order: what concerns the user's own work first, the running of the system last.
CATEGORY_CHOICES = (
    (Category.PROJECT, pgettext_lazy("notification category", "Project")),
    (Category.PERSONNEL, pgettext_lazy("notification category", "Personnel")),
    (Category.MATERIAL, pgettext_lazy("notification category", "Material")),
    (Category.SYSTEM, pgettext_lazy("notification category", "System")),
)
CATEGORIES = tuple(value for value, _label in CATEGORY_CHOICES)
_LABELS = dict(CATEGORY_CHOICES)

#: The kinds of each category in the order of the settings page – the most frequent and personal first.
KINDS_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    Category.PROJECT: (
        Kind.DEPLOYMENT_REQUEST,
        Kind.DEPLOYMENT_ANSWER,
        Kind.PRICE_OFFER,  # PER-038
        Kind.PRICE_OFFER_ANSWER,  # PER-038
        Kind.DEPLOYMENT_CHANGE,  # PRJ-118
        Kind.CHAT_MENTION,
        Kind.FOLLOW_UP,
        Kind.SERVICE_CASE,
        Kind.NEW_MAIL,
        Kind.PROJECT_CHANGE,
        Kind.PRODUCT_CHANGE,  # PRJ-072
        Kind.SHORTAGE,
        Kind.INVOICE_REMINDER,  # DOK-015
        Kind.AUTOMATION,
    ),
    Category.PERSONNEL: (
        Kind.TIME_DECISION,  # ZEI-031
        Kind.TIMES_TO_APPROVE,  # ZEI-029
        Kind.EXPENSE,
        Kind.QUALIFICATION_EXPIRY,
    ),
    Category.MATERIAL: (
        Kind.DEFECT,
        Kind.LOW_STOCK,
        Kind.INSPECTION_DUE,
    ),
    Category.SYSTEM: (
        # UIX-052: first – it concerns everybody who starts a task, also of the AI.
        Kind.JOB_FINISHED,
        Kind.MAIL_PROBLEM,
        Kind.CALENDAR_PROBLEM,
        Kind.SYSTEM_ERROR,
    ),
}

#: The category of each kind listed above.
CATEGORY_OF: dict[str, str] = {str(kind): category for category, kinds in KINDS_BY_CATEGORY.items() for kind in kinds}

#: Where a kind without an entry goes.
DEFAULT_CATEGORY = Category.PROJECT


def category_of(kind: str) -> str:
    """The category of a kind of notification (UIX-039)."""
    return CATEGORY_OF.get(str(kind), DEFAULT_CATEGORY)


def category_label(category: str) -> str:
    """The name of a category as shown: "Projekt", "Personal", "Material", "System"."""
    return str(_LABELS.get(category, category))


def kinds_in(category: str) -> list[str]:
    """Every kind of a category, those without an entry included (for the filter of the list)."""
    return [kind for kind in Kind.values if category_of(kind) == category]


def ordered_kinds() -> list[str]:
    """Every kind, by category and within it in the order of :data:`KINDS_BY_CATEGORY`.

    A kind without an entry comes last in its category.
    """
    listed = [str(kind) for kinds in KINDS_BY_CATEGORY.values() for kind in kinds]
    position = {kind: index for index, kind in enumerate(listed)}
    category_rank = {category: index for index, category in enumerate(CATEGORIES)}
    return sorted(
        Kind.values,
        key=lambda kind: (category_rank[category_of(kind)], position.get(kind, len(listed))),
    )


def grouped(items: Iterable[dict]) -> list[dict]:
    """Settings (one dict per kind, with ``category``) grouped by category, for the settings page."""
    groups: dict[str, list[dict]] = {category: [] for category in CATEGORIES}
    for item in items:
        groups.setdefault(item["category"], []).append(item)
    return [
        {"category": category, "label": category_label(category), "items": entries}
        for category, entries in groups.items()
        if entries
    ]
