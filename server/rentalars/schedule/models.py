# SPDX-License-Identifier: GPL-3.0-or-later
"""Records of the planning module: the calendar links of products, models and items (VFG-040).

The overviews of the planning module are
read from projects, material and people. The calendar link is the first
record: a secret address that calendar programs subscribe to, one per
product, material model or item, created on its page (VFG-019).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _


class CalendarLink(models.Model):
    """The secret iCalendar address of one product, material model or item (VFG-040).

    Exactly one of ``product``, ``material_model`` and ``item`` is set. The
    row stays when the link is deactivated – ``token`` is then empty –, so a
    new link of the same record keeps the address prefix and only the token
    changes. It goes with its record when that is deleted.

    Not an :class:`~rentalars.core.audit.AuditedModel`: the token works like
    a password and never enters the change log. Creating, renewing and
    deactivating are written as events into the history of the record
    itself (``schedule.calendar_links``), where readers of the record look.
    """

    product = models.OneToOneField(
        "products.Product",
        verbose_name=_("product"),
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="calendar_link",
    )
    material_model = models.OneToOneField(
        "material.MaterialModel",
        verbose_name=_("material model"),
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="calendar_link",
    )
    item = models.OneToOneField(
        "material.MaterialItem",
        verbose_name=_("item"),
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="calendar_link",
    )
    #: 256 random bits, URL-safe; empty while no link is active.
    token = models.CharField(max_length=64, blank=True, editable=False)
    #: When and by whom the link that works now was created.
    created_at = models.DateTimeField(_("created"), null=True, blank=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("created by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )

    class Meta:
        verbose_name = _("calendar link")
        verbose_name_plural = _("calendar links")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(product__isnull=False, material_model__isnull=True, item__isnull=True)
                    | Q(product__isnull=True, material_model__isnull=False, item__isnull=True)
                    | Q(product__isnull=True, material_model__isnull=True, item__isnull=False)
                ),
                name="calendar_link_one_subject",
            )
        ]

    def __str__(self) -> str:
        return str(self.subject)

    @property
    def subject(self) -> models.Model | None:
        """The product, material model or item the link belongs to."""
        return self.product or self.material_model or self.item

    @property
    def is_active(self) -> bool:
        """Whether a link was created and not deactivated since."""
        return bool(self.token)
