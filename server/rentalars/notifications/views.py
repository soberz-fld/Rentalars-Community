# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser views of the notifications (UIX-005); Einstellungen → Benachrichtigungen (VFG-036)."""

from __future__ import annotations

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST

from rentalars.accounts.rights import Module, module_required, request_rights
from rentalars.core.listing import paginate
from rentalars.core.models import NotificationSettings
from rentalars.documents import invoice_reminders
from rentalars.notifications import services
from rentalars.notifications.categories import (
    CATEGORIES,
    CATEGORY_CHOICES,
    category_label,
    category_of,
    grouped,
    kinds_in,
)
from rentalars.notifications.forms import NotificationSettingsForm
from rentalars.notifications.list_tables import NOTIFICATION_TABLE
from rentalars.notifications.models import Notification
from rentalars.notifications.schedule import next_run
from rentalars.timetracking.reminders import next_run as approval_next_run


def notification_list(request: HttpRequest) -> HttpResponse:
    """The notifications of the user, newest first; unread ones marked.

    UIX-039: ``?category=`` shows one category only (Projekt, Personal,
    Material, System); every notification names its category.
    """
    notifications = Notification.objects.filter(user=request.user)
    if request.GET.get("unread"):
        notifications = notifications.filter(read_at__isnull=True)
    category = request.GET.get("category", "")
    if category in CATEGORIES:
        notifications = notifications.filter(kind__in=kinds_in(category))
    else:
        category = ""
    # UIX-040: a table of core.tables – columns, sorting, groups, CSV (notifications/list_tables.py).
    table = NOTIFICATION_TABLE.state(request)
    notifications = table.order(notifications)
    if table.wants_csv:
        return table.csv_response(notifications, _("Notifications"))
    page = paginate(request, notifications)
    for item in page:
        item.category_label = category_label(category_of(item.kind))
    return render(
        request,
        "notifications/list.html",
        {
            "page": page,
            "table": table,
            "rows": table.rows(page),
            "unread_only": bool(request.GET.get("unread")),
            "category": category,
            "categories": CATEGORY_CHOICES,
        },
    )


def notification_open(request: HttpRequest, pk: int) -> HttpResponse:
    """Mark a notification as read and go where it leads."""
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])
    if notification.url and url_has_allowed_host_and_scheme(notification.url, allowed_hosts={request.get_host()}):
        return redirect(notification.url)
    return redirect("notifications:list")


@require_POST
def mark_all_read(request: HttpRequest) -> HttpResponse:
    """Mark every notification of the user as read."""
    count = services.mark_read(request.user)
    messages.success(
        request,
        ngettext("%(count)d notification marked as read.", "%(count)d notifications marked as read.", count)
        % {"count": count},
    )
    return redirect("notifications:list")


def preferences(request: HttpRequest) -> HttpResponse:
    """Which notifications the user wants, in the application, by e-mail and in the app (UIX-005, UIX-039).

    UIX-039: grouped by category; the third column says whether the companion
    app shows the kind as a notification on the phone. UIX-052: every kind
    but those deliberately always sent.
    """
    if request.method == "POST":
        for kind in services.switchable_kinds():
            services.set_preference(
                request.user,
                kind,
                in_app=request.POST.get(f"{kind}-app") == "1",
                by_email=request.POST.get(f"{kind}-email") == "1",
                companion=request.POST.get(f"{kind}-companion") == "1",
            )
        messages.success(request, _("Notification settings saved."))
        return redirect("notifications:preferences")
    return render(
        request,
        "notifications/preferences.html",
        {"groups": grouped(services.preferences_of(request.user)), "has_email": bool(request.user.email)},
    )


@module_required(Module.ADMINISTRATION)
def company_settings(request: HttpRequest) -> HttpResponse:
    """Einstellungen → Benachrichtigungen: shortages (VFG-036), reminders of invoices (DOK-015) and times (ZEI-029).

    Changing the time or how often starts the schedule anew: the next check
    is at the next moment of the new schedule, never at once for a moment
    already past (``services.schedule_changed``).
    """
    can_write = request_rights(request).can_write(Module.ADMINISTRATION)
    current = NotificationSettings.load()
    form = NotificationSettingsForm(request.POST if request.method == "POST" else None, instance=current)
    if request.method == "POST":
        if not can_write:
            return render(request, "403.html", status=403)
        if form.is_valid():
            form.save()
            if set(form.changed_data) & set(services.SCHEDULE_FIELDS):
                services.schedule_changed()
            messages.success(request, _("Settings saved."))
            return redirect("notifications:company_settings")
    return render(
        request,
        "notifications/company_settings.html",
        {
            "form": form,
            "can_write": can_write,
            "settings": current,
            "next_run": next_run(current),
            "weekly": (form["shortage_interval"].value() or "") == "weekly",
            # DOK-015: when the invoices are looked at next, and how many are open now.
            "invoice_next_run": invoice_reminders.next_run(),
            "invoices_on": invoice_reminders.invoices_on(),
            # ZEI-029: when the times waiting are looked at next.
            "approval_next_run": approval_next_run(),
        },
    )
