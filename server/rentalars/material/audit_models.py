# SPDX-License-Identifier: GPL-3.0-or-later
"""Audits of material items and the to-dos noted on them (MAT-067, MAT-069).

An audit is a short check of the material: somebody looks at an item
and says "in order" – or notes small things to be done, such as "Label fehlt"
or, on a cable, "Klett fehlt". Three tables:

``AuditSettings``
    Einstellungen → Audits: how long after its last audit an item is due
    again (24 months unless set otherwise; 0 switches audits off) and the
    quick picks offered for to-dos.

``ItemAudit``
    One audit of one item: when, by whom, the result ("in order" or "with
    to-dos") and a note.

``ItemTodo``
    A small thing to be done on an item, noted in an audit or at any time on
    the item's page; open until somebody ticks it done.

When an item is due is worked out in ``material.audits``; nothing about due
dates is stored. Imported at the end of ``rentalars/material/models.py`` so
that Django finds the tables.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rentalars.core.audit import AuditedModel
from rentalars.core.models import SingletonModel

#: The interval of a new installation: every item is looked at once in two years.
DEFAULT_INTERVAL_MONTHS = 24
MAX_INTERVAL_MONTHS = 120

#: The quick picks of a new installation – short, for event technology – in German and in English (UIX-029).
DEFAULT_QUICK_TODOS = ("Label fehlt", "Klett fehlt", "Beschädigt", "Reinigen", "Teile fehlen")
ENGLISH_QUICK_TODOS = ("Label missing", "Velcro missing", "Damaged", "Clean", "Parts missing")
MAX_QUICK_TODOS = 12
QUICK_TODO_MAX_LENGTH = 60

#: The longest text of a to-do.
TODO_MAX_LENGTH = 200


class AuditSettings(SingletonModel):
    """Einstellungen → Audits: the interval and the quick picks for to-dos (MAT-067)."""

    interval_months = models.PositiveSmallIntegerField(
        _("audit interval (months)"),
        default=DEFAULT_INTERVAL_MONTHS,
        validators=[MaxValueValidator(MAX_INTERVAL_MONTHS)],
        help_text=_(
            "An item is due again this long after its last audit; one never audited this long after it was "
            "created in Rentalars. 0: off – no audit is ever due; audits and to-dos can still be noted."
        ),
    )
    quick_todos = models.TextField(
        _("quick picks for to-dos"),
        blank=True,
        default="\n".join(DEFAULT_QUICK_TODOS),
        help_text=_("One per line, at most 12 – offered as buttons in the audit and on the page of an item."),
    )

    class Meta:
        verbose_name = _("audit settings")
        verbose_name_plural = _("audit settings")

    def __str__(self) -> str:
        return str(_("Audit settings"))

    @property
    def is_active(self) -> bool:
        """Whether audits become due at all (an interval above 0)."""
        return self.interval_months > 0

    @property
    def quick_todo_list(self) -> list[str]:
        """The quick picks, one per line of the field, without empty lines and repeats."""
        return split_quick_todos(self.quick_todos)

    def clean(self) -> None:
        """At most 12 quick picks of at most 60 characters; they are stored one per line, tidied up."""
        super().clean()
        picks = split_quick_todos(self.quick_todos or "")
        errors = []
        if len(picks) > MAX_QUICK_TODOS:
            errors.append(_("At most %(count)d quick picks.") % {"count": MAX_QUICK_TODOS})
        too_long = [pick for pick in picks if len(pick) > QUICK_TODO_MAX_LENGTH]
        if too_long:
            errors.append(
                _("A quick pick has at most %(count)d characters: %(pick)s")
                % {"count": QUICK_TODO_MAX_LENGTH, "pick": too_long[0]}
            )
        if errors:
            raise ValidationError({"quick_todos": errors})
        self.quick_todos = "\n".join(picks)


def split_quick_todos(text: str) -> list[str]:
    """The lines of a text as quick picks: stripped, without empty lines and without repeats (any case)."""
    picks: list[str] = []
    seen: set[str] = set()
    for line in (text or "").splitlines():
        pick = " ".join(line.split())
        if pick and pick.casefold() not in seen:
            seen.add(pick.casefold())
            picks.append(pick)
    return picks


class AuditResult(models.TextChoices):
    """What an audit found (MAT-067)."""

    OK = "ok", _("in order")
    TODOS = "todos", _("with to-dos")


class ItemAudit(AuditedModel):
    """One audit of one item: when, by whom, what it found (MAT-067).

    The next one is due ``AuditSettings.interval_months`` after it
    (``material.audits``). "With to-dos" means the audit noted to-dos; they
    point back to it (``ItemTodo.audit``).
    """

    item = models.ForeignKey(
        "material.MaterialItem", verbose_name=_("item"), on_delete=models.CASCADE, related_name="audits"
    )
    audited_at = models.DateTimeField(_("audited"), default=timezone.now)
    audited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("audited by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    result = models.CharField(_("result"), max_length=10, choices=AuditResult.choices, default=AuditResult.OK)
    note = models.CharField(_("note"), max_length=250, blank=True)

    class Meta:
        verbose_name = _("audit")
        verbose_name_plural = _("audits")
        ordering = ["-audited_at", "-id"]
        indexes = [models.Index(fields=["item", "audited_at"], name="item_audit_latest_idx")]

    def __str__(self) -> str:
        return f"{self.item.display_id}: {self.get_result_display()}"

    def audit_parent(self) -> models.Model | None:
        """Show audits in the history of the item."""
        return self.item

    @property
    def is_ok(self) -> bool:
        """Whether the audit found the item in order."""
        return self.result == AuditResult.OK


class ItemTodo(AuditedModel):
    """A small thing to be done on an item, e.g. "Label fehlt" (MAT-069).

    Noted in an audit (``audit``) or at any time on the item's page; open
    until it is ticked done (``done_at``). Open to-dos of items in use show
    under Materialverwaltung → Offene Punkte → Material mit To-Do.
    """

    item = models.ForeignKey(
        "material.MaterialItem", verbose_name=_("item"), on_delete=models.CASCADE, related_name="todos"
    )
    text = models.CharField(_("to-do"), max_length=TODO_MAX_LENGTH)
    audit = models.ForeignKey(
        ItemAudit,
        verbose_name=_("noted in the audit"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="todos",
        editable=False,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("noted by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    created_at = models.DateTimeField(_("noted"), default=timezone.now, editable=False)
    done_at = models.DateTimeField(_("done"), null=True, blank=True, editable=False)
    done_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("done by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )

    class Meta:
        verbose_name = _("to-do")
        verbose_name_plural = _("to-dos")
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["item", "done_at"], name="item_todo_open_idx")]

    def __str__(self) -> str:
        return f"{self.item.display_id}: {self.text}"

    def audit_parent(self) -> models.Model | None:
        """Show to-dos in the history of the item."""
        return self.item

    @property
    def is_open(self) -> bool:
        """Whether the to-do is still to be done."""
        return self.done_at is None

    def clean(self) -> None:
        """A to-do says what is to be done."""
        super().clean()
        self.text = " ".join((self.text or "").split())
        if not self.text:
            raise ValidationError({"text": _("Say what is to be done.")})
