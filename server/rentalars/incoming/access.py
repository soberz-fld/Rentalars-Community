# SPDX-License-Identifier: GPL-3.0-or-later
"""Who may see and change incoming invoices (DOK-023, DOK-024).

An incoming invoice is made of purchase prices, so the register is open to whoever may see purchase prices
(AUT-019) and read the material (the invoices become items of it); changing, reading with AI and booking in need
write access to the material as well, deleting the delete level – exactly as for the items the invoices make.
The settings (limit of a low-value asset, standard useful life) are settings: the module "Administration".
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied

from rentalars.accounts.rights import Module, SpecialRight


def may_see(rights: Any) -> bool:
    """Whether the register is open to these rights: purchase prices and the material to read."""
    return rights.has(SpecialRight.PURCHASE_PRICES) and rights.can_read(Module.MATERIAL)


def may_change(rights: Any) -> bool:
    """Whether invoices may be uploaded, changed and booked in: the register, and write access to the material."""
    return may_see(rights) and rights.can_write(Module.MATERIAL)


def may_delete(rights: Any) -> bool:
    """Whether invoices may be deleted: the register, and the delete level of the material."""
    return may_see(rights) and rights.can_delete(Module.MATERIAL)


def require_see(rights: Any) -> None:
    """Refuse (403) unless the register is open to these rights."""
    if not may_see(rights):
        raise PermissionDenied


def require_change(rights: Any) -> None:
    """Refuse (403) unless these rights may change invoices."""
    if not may_change(rights):
        raise PermissionDenied
