# SPDX-License-Identifier: GPL-3.0-or-later
"""Addresses of the time tracking module."""

from django.urls import path

from rentalars.timetracking import expense_views, views

app_name = "timetracking"

urlpatterns = [
    path("times/", views.my_times, name="my_times"),
    # The quick entry: a dialog that every page can open (ZEI-003).
    path("times/quick/", views.quick_entry, name="quick"),
    path("times/timer/start/", views.timer_start, name="timer_start"),
    path("times/timer/stop/", views.timer_stop, name="timer_stop"),
    path("times/submit/", views.submit, name="submit"),
    # ZEI-024: put the hint at the companion app away.
    path("times/companion-hint/", views.companion_hint_dismiss, name="companion_hint_dismiss"),
    path("times/approval/", views.approval, name="approval"),
    path("times/approval/decide/", views.decide, name="decide"),
    path("times/report/", views.report, name="report"),
    path("times/<int:pk>/", views.entry_edit, name="entry_edit"),
    path("times/<int:pk>/delete/", views.entry_delete, name="entry_delete"),
    path("times/<int:pk>/reopen/", views.entry_reopen, name="entry_reopen"),
    path("times/<int:pk>/assign/", views.entry_assign, name="entry_assign"),
    # ZEI-030 (correction by the approver): correct a time waiting for approval and approve it.
    path("times/<int:pk>/correct/", views.entry_correct, name="entry_correct"),
    # ZEI-019: expenses and travel costs. Approving them is part of "times/approval/"; the report lies
    # below "times/report/", so that it belongs to "Personnel" for approvers and to "My area" otherwise.
    path("times/expenses/", expense_views.my_expenses, name="my_expenses"),
    path("times/expenses/new/", expense_views.expense_new, name="expense_new"),
    path("times/expenses/submit/", expense_views.expense_submit, name="expense_submit"),
    path("times/expenses/<int:pk>/", expense_views.expense_edit, name="expense_edit"),
    path("times/expenses/<int:pk>/delete/", expense_views.expense_delete, name="expense_delete"),
    path("times/expenses/<int:pk>/receipt/", expense_views.expense_receipt, name="expense_receipt"),
    path("times/report/expenses/", expense_views.expense_report, name="expense_report"),
    path("times/report/expenses/reimburse/", expense_views.expense_reimburse, name="expense_reimburse"),
    path("times/report/expenses/<int:pk>/reopen/", expense_views.expense_reopen, name="expense_reopen"),
]
