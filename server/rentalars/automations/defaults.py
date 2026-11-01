# SPDX-License-Identifier: GPL-3.0-or-later
"""The automations that come with Rentalars, and how to get them back (ADM-019; ADM-013).

Rentalars brings four rules: three for the service cases (PRJ-112) and one for defect reports
(MAT-057). They are rules like any other – changed, switched off and deleted with the same rights
and checks as the company's own rules, in the browser and through the API.

Each carries a stable key (``Automation.default_key``), never only its name: a renamed or changed default is
still known. "Standard-Automationen wiederherstellen" (:func:`restore`) creates the defaults whose key is
missing and leaves every rule that is there alone – changed or not.

Nothing else creates or changes them:

* the migration that brought them ran once (``0001_squashed_0003_defects_085``);
* the start data (``core.defaults.install_defaults``) and no start of Rentalars touch an automation.

A deleted default therefore stays deleted and a changed one stays as it is, through every update.

The values below are how each default came; they never change. A later version that wants another default
brings a new key, so that :func:`is_changed` keeps telling the rules a user changed from those that came so.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import IntegrityError, transaction

from rentalars.automations.models import Action, Automation, Trigger


@dataclass(frozen=True)
class DefaultAutomation:
    """One rule that comes with Rentalars: its key, its names and how it came."""

    key: str
    german: str
    english: str
    trigger: str
    action: str
    #: The condition: for the triggers of the service cases the status of the case (PRJ-112).
    status: str = ""
    new_case_status: str = ""

    def name(self, language: str | None = None) -> str:
        """The name in the language of the installation (or the one given), as a new database gets it."""
        if language is None:
            from rentalars.core.i18n import installation_language

            language = installation_language()
        return self.english if language == "en" else self.german

    def values(self) -> dict[str, Any]:
        """The stored values of the rule as it came – besides its name and whether it is active."""
        return {
            "trigger": self.trigger,
            "mailbox_id": None,
            "status": self.status,
            "answer": "",
            "communication": "",
            "action": self.action,
            "recipient": "",
            "user_id": None,
            "new_case_status": self.new_case_status,
            "subject": "",
            "text": "",
        }


#: The defaults, in the order the list of what is restored names them.
DEFAULTS: tuple[DefaultAutomation, ...] = (
    # PRJ-112: a case waiting to close is closed when its follow-up is due...
    DefaultAutomation(
        key="case_closing_due",
        german="Wartet auf Schließen: zum Termin schließen",
        english="Waiting to close: close at the time set",
        trigger=Trigger.CASE_FOLLOW_UP.value,
        status="closing",
        action=Action.CASE_STATUS.value,
        new_case_status="done",
    ),
    # ... and opened again on new communication;
    DefaultAutomation(
        key="case_closing_communication",
        german="Wartet auf Schließen: bei neuer Kommunikation wieder öffnen",
        english="Waiting to close: open again on new communication",
        trigger=Trigger.CASE_COMMUNICATION.value,
        status="closing",
        action=Action.CASE_STATUS.value,
        new_case_status="open",
    ),
    # a case in the backlog is opened again when its follow-up is due.
    DefaultAutomation(
        key="case_backlog_due",
        german="Rückstand: zur Wiedervorlage wieder öffnen",
        english="Backlog: open again when the follow-up is due",
        trigger=Trigger.CASE_FOLLOW_UP.value,
        status="backlog",
        action=Action.CASE_STATUS.value,
        new_case_status="open",
    ),
    # MAT-057: a defect reported makes a service case.
    DefaultAutomation(
        key="defect_case",
        german="Defektmeldung → Servicefall",
        english="Defect report → service case",
        trigger=Trigger.DEFECT.value,
        action=Action.CREATE_CASE.value,
    ),
)

BY_KEY = {default.key: default for default in DEFAULTS}


def is_changed(rule: Automation) -> bool:
    """Whether a rule that came with Rentalars differs from how it came; ``False`` for the company's own rules.

    Switching it off is no change (the list shows "aus" for that); its name counts as unchanged in German and in
    English, the languages the start data comes in (UIX-029).
    """
    default = BY_KEY.get(rule.default_key or "")
    if default is None:
        return False
    if rule.name not in (default.german, default.english):
        return True
    return any(getattr(rule, field) != value for field, value in default.values().items())


def missing() -> list[DefaultAutomation]:
    """The defaults that are not there (deleted), in the order of :data:`DEFAULTS`."""
    present = set(Automation.objects.filter(default_key__in=BY_KEY).values_list("default_key", flat=True))
    return [default for default in DEFAULTS if default.key not in present]


def restore(user: Any = None) -> list[Automation]:
    """Create the missing defaults as they came, active; leave every rule that is there as it is.

    Found by key, not by name: a rule of the company with the same name is no default, and a renamed default
    is one. Two people restoring at the same moment make each default once (the key is unique).

    Returns:
        The rules created now, in the order of :data:`DEFAULTS`; empty if all were there.
    """
    created = []
    for default in missing():
        rule = Automation(name=default.name(), is_active=True, default_key=default.key, **default.values())
        if user is not None and getattr(user, "is_authenticated", False):
            rule.created_by = user
        try:
            with transaction.atomic():
                rule.save()  # audited as "created" (AuditedModel), by whoever restores
        except IntegrityError:
            continue  # restored by somebody else in the same moment
        created.append(rule)
    return created
