# SPDX-License-Identifier: GPL-3.0-or-later
"""Addresses of the planning overviews."""

from django.urls import path

from rentalars.schedule import calendar_link_views, follow_ups, move_views, views

app_name = "schedule"

urlpatterns = [
    path("schedule/", views.calendar, name="calendar"),
    path("schedule/timeline/", views.timeline, name="timeline"),
    path("schedule/products/", views.products, name="products"),
    path("schedule/personnel/", views.personnel, name="personnel"),
    # VFG-034: every follow-up as a table, the last tab of "Planning".
    path("schedule/follow-ups/", follow_ups.follow_ups, name="follow_ups"),
    # VFG-026: the dialog that confirms an appointment dragged in a timeline.
    path("schedule/move/<project:pk>/", move_views.move, name="move"),
    # VFG-040: the calendar link of a product, model or item – changed on its page, read without login
    # (under /calendar-feed/ like the subscription link of a person, PER-023).
    path(
        "schedule/calendar-links/<slug:kind>/<int:pk>/",
        calendar_link_views.calendar_link_change,
        name="calendar_link_change",
    ),
    path(
        "calendar-feed/<slug:kind>/<int:pk>/<slug:token>.ics",
        calendar_link_views.calendar_link_feed,
        name="calendar_link_feed",
    ),
]
