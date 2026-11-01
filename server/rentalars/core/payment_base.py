# SPDX-License-Identifier: GPL-3.0-or-later
"""What a payment is, for outgoing and incoming invoices alike (DOK-048).

A payment is a booking: it is not changed and not deleted. A wrong one is *voided* – with a reason, by whom and when –
and stays in the list, but no longer counts. The sums of the invoice, the list of open items and the EÜR (DOK-045)
read the payments that were not voided.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rentalars.core.audit import AuditedModel

#: The largest amount of one payment (a ``Decimal(12, 2)`` field).
MAX_AMOUNT = Decimal("9999999999.99")


class PaymentLockedError(Exception):
    """A payment was to be changed or deleted. A payment is a booking: it is only voided (DOK-051)."""


class PaymentQuerySet(models.QuerySet):  # type: ignore[type-arg]
    """No change in bulk, no delete: the ways around ``save`` and ``delete`` of the model (DOK-051)."""

    def update(self, **kwargs: Any) -> int:
        """Refused; a payment is voided with :func:`rentalars.documents.payments.void`."""
        raise PaymentLockedError("Payments are not changed in bulk.")

    def bulk_update(self, objs: Any, fields: Any, batch_size: int | None = None) -> int:
        """Refused."""
        raise PaymentLockedError("Payments are not changed in bulk.")

    def bulk_create(self, objs: Any, *args: Any, **kwargs: Any) -> list[Any]:
        """New payments only: ``update_conflicts`` would overwrite stored ones."""
        if kwargs.get("update_conflicts"):
            raise PaymentLockedError("Payments are not overwritten.")
        if any(getattr(obj, "pk", None) is not None for obj in objs):
            raise PaymentLockedError("A new payment gets its number from the database.")
        return super().bulk_create(objs, *args, **kwargs)

    def delete(self) -> tuple[int, dict[str, int]]:
        """Refused."""
        raise PaymentLockedError("Payments are not deleted; a wrong one is voided.")


#: What voiding a payment sets – the only fields that may change after the payment was entered, and only once.
VOID_FIELDS = frozenset({"voided_at", "voided_by", "void_reason"})


class PaymentMethod(models.TextChoices):
    """How an invoice was paid."""

    TRANSFER = "transfer", _("bank transfer")
    CASH = "cash", _("cash")
    CARD = "card", _("card")
    DEBIT = "debit", _("direct debit")
    SETOFF = "setoff", _("set off")
    OTHER = "other", _("other")


class PaymentBase(AuditedModel):
    """The fields every payment has; the invoice it belongs to is the field of the subclass."""

    paid_on = models.DateField(_("paid on"))
    #: Negative: money paid back (a refund). Never zero.
    amount = models.DecimalField(
        _("amount"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(-MAX_AMOUNT), MaxValueValidator(MAX_AMOUNT)],
        help_text=_("Gross, as it left or came into the account. A negative amount is a refund."),
    )
    method = models.CharField(_("method"), max_length=10, choices=PaymentMethod.choices, default=PaymentMethod.TRANSFER)
    reference = models.CharField(_("reference"), max_length=200, blank=True, help_text=_("The purpose of the payment."))
    note = models.CharField(_("note"), max_length=250, blank=True)
    created_at = models.DateTimeField(_("entered"), default=timezone.now, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    voided_at = models.DateTimeField(_("voided"), null=True, blank=True, editable=False)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    void_reason = models.CharField(_("reason for voiding"), max_length=250, blank=True)

    objects = PaymentQuerySet.as_manager()

    class Meta:
        abstract = True
        ordering = ["paid_on", "id"]

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save a new payment, or void a payment once; nothing else (DOK-051).

        The services never change a payment, but a script, the shell or the admin pages could. This is the same rule
        where the data is: what was entered stays as it was; the voiding fields are written once, together.

        Raises:
            PaymentLockedError: A stored payment is to be changed other than by voiding it for the first time.
        """
        # Also a "new" payment with a number that exists: Django would write over the stored one.
        if self.pk is not None:
            stored = type(self)._base_manager.filter(pk=self.pk).first()
            if stored is not None:
                if self._state.adding:
                    raise PaymentLockedError("A payment with this number exists; it is not overwritten.")
                self._check_unchanged(stored)
        super().save(*args, **kwargs)

    def _check_unchanged(self, stored: PaymentBase) -> None:
        changed = {
            field.name
            for field in self._meta.concrete_fields
            if not field.primary_key and getattr(self, field.attname) != getattr(stored, field.attname)
        }
        if not changed:
            return
        if stored.voided_at is not None:
            raise PaymentLockedError("A voided payment is not changed.")
        if not changed <= VOID_FIELDS or self.voided_at is None or not (self.void_reason or "").strip():
            raise PaymentLockedError("A payment is not changed; a wrong one is voided with a reason.")

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        """Refused: a payment is a booking."""
        raise PaymentLockedError("Payments are not deleted; a wrong one is voided.")

    @property
    def is_voided(self) -> bool:
        """Whether the payment was voided; it then counts for nothing."""
        return self.voided_at is not None
