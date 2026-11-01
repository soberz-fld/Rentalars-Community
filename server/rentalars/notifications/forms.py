# SPDX-License-Identifier: GPL-3.0-or-later
"""Forms of the notifications: Einstellungen → Benachrichtigungen (VFG-036; invoices DOK-015; times ZEI-029)."""

from __future__ import annotations

from typing import Any

from rentalars.core.forms import StyledModelForm
from rentalars.core.models import NotificationSettings
from rentalars.core.notification_settings import MAX_APPROVAL_DAYS, MAX_INVOICE_DAYS, MAX_LEAD_WEEKS

#: VFG-036: the fields of the page in their order; the API has the same.
SHORTAGE_FIELDS = [
    "shortage_interval",
    "shortage_weekday",
    "shortage_time",
    "shortage_lead_weeks",
    "shortage_repeat",
]


#: DOK-015: the reminders of invoices not written yet, in their order; the API has the same.
INVOICE_FIELDS = [
    "invoice_reminders",
    "invoice_time",
    "invoice_first_days",
    "invoice_every_days",
    "invoice_user",
    "invoice_service_cases",
]

#: ZEI-029: the reminders of the times waiting for approval, in their order; API the same.
APPROVAL_FIELDS = [
    "approval_reminders",
    "approval_time",
    "approval_first_days",
    "approval_every_days",
]


class NotificationSettingsForm(StyledModelForm):
    """When and how far ahead shortages are reported (VFG-036); reminders of invoices (DOK-015), of times (ZEI-029)."""

    class Meta:
        model = NotificationSettings
        fields = [*SHORTAGE_FIELDS, *INVOICE_FIELDS, *APPROVAL_FIELDS]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # The browser offers only 1 to 26 weeks; the model checks the same.
        self.fields["shortage_lead_weeks"].widget.attrs.update({"min": 1, "max": MAX_LEAD_WEEKS})
        # DOK-015: only who may see prices can make an invoice or tick the mark (AUT-019).
        self.fields["invoice_user"].queryset = price_users()
        self.fields["invoice_first_days"].widget.attrs.update({"min": 0, "max": MAX_INVOICE_DAYS})
        self.fields["invoice_every_days"].widget.attrs.update({"min": 1, "max": MAX_INVOICE_DAYS})
        # ZEI-029: the reminders of times to approve.
        self.fields["approval_first_days"].widget.attrs.update({"min": 0, "max": MAX_APPROVAL_DAYS})
        self.fields["approval_every_days"].widget.attrs.update({"min": 1, "max": MAX_APPROVAL_DAYS})


def price_users() -> Any:
    """DOK-015: the active users who may see prices – those an invoice reminder can go to."""
    from rentalars.accounts.models import User
    from rentalars.accounts.rights import SpecialRight, rights_of

    users = User.objects.filter(is_active=True).order_by("first_name", "last_name", "username")
    allowed = [user.pk for user in users.prefetch_related("roles") if rights_of(user).has(SpecialRight.PRICES)]
    return users.filter(pk__in=allowed)
