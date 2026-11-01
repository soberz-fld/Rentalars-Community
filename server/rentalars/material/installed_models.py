# SPDX-License-Identifier: GPL-3.0-or-later
"""Bulk material built into an item (built-in quantity material; MAT-040).

"Verbautes Mengenmaterial": a rack case holds 10 m of cable and 4 connectors, a vehicle carries a box of
screws. The cable, the connectors and the screws are bulk material (MAT-005): one row of items stands for a
quantity. This table is the bill of material of the container: *how many* of a bulk row sit in *which* item.

The quantity installed is taken out of the free stock of the bulk row (``MaterialItem.quantity``) and put back
when it is removed. Everything that counts, plans, sells or packs bulk material – the stock of the product, the
availability, the packing – reads that quantity and so sees the free stock only, without a change of its own;
the installed quantity is counted here. Imported at the end of ``rentalars/material/models.py`` so that Django
finds the table.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rentalars.core.audit import AuditedModel


class InstalledQuantity(AuditedModel):
    """A quantity of a bulk row built into an item (MAT-040).

    One row per pair of container and bulk row; installing more of the same material raises the quantity.
    The container is any item of individual items (case, rack, vehicle, device) – never bulk material itself.
    Who installed it and when is kept here and, as an event with the quantity, in the history of both items
    (``material.installations``).
    """

    container = models.ForeignKey(
        "material.MaterialItem",
        verbose_name=_("installed in"),
        on_delete=models.PROTECT,
        related_name="installed_quantities",
    )
    material = models.ForeignKey(
        "material.MaterialItem",
        verbose_name=_("bulk material"),
        on_delete=models.PROTECT,
        related_name="installations",
    )
    quantity = models.PositiveIntegerField(_("quantity"), validators=[MinValueValidator(1)])
    note = models.CharField(_("note"), max_length=250, blank=True)
    installed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    installed_at = models.DateTimeField(_("installed"), default=timezone.now, editable=False)

    class Meta:
        verbose_name = _("installed quantity")
        verbose_name_plural = _("installed quantities")
        ordering = ["container_id", "material_id"]
        constraints = [
            models.UniqueConstraint(fields=["container", "material"], name="installed_quantity_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} × {self.material.display_id} in {self.container.display_id}"

    def audit_parent(self) -> models.Model | None:
        """Show changes in the history of the container."""
        return self.container
