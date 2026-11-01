# SPDX-License-Identifier: GPL-3.0-or-later
"""Addresses of the personnel module."""

from django.urls import path

from rentalars.personnel import calendar_views, offer_views, views

app_name = "personnel"

urlpatterns = [
    path("personnel/", views.person_list, name="person_list"),
    path("personnel/availability/", views.availability, name="availability"),
    path("personnel/functions/", views.job_function_list, name="job_function_list"),
    path("personnel/functions/new/", views.job_function_edit, name="job_function_create"),
    path("personnel/functions/<int:pk>/", views.job_function_edit, name="job_function_edit"),
    path("personnel/functions/<int:pk>/delete/", views.job_function_delete, name="job_function_delete"),
    path("personnel/people/new/", views.person_edit, name="person_create"),
    path("personnel/people/<int:pk>/", views.person_detail, name="person_detail"),
    path("personnel/people/<int:pk>/edit/", views.person_edit, name="person_edit"),
    path("personnel/people/<int:pk>/active/", views.person_set_active, name="person_set_active"),
    path("personnel/people/<int:pk>/delete/", views.person_delete, name="person_delete"),
    path("personnel/people/<int:pk>/rates/", views.rate_set, name="rate_set"),
    path("personnel/people/<int:pk>/rates/<int:function_pk>/remove/", views.rate_remove, name="rate_remove"),
    path("personnel/people/<int:pk>/absences/", views.absence_add, name="absence_add"),
    path("personnel/people/<int:pk>/absences/<int:absence_pk>/delete/", views.absence_delete, name="absence_delete"),
    path("personnel/people/<int:pk>/export/", views.person_export, name="person_export"),
    path("personnel/people/<int:pk>/timeline/", views.person_timeline, name="person_timeline"),
    # PER-014: qualifications with expiry date and certificate.
    path("personnel/people/<int:pk>/qualifications/new/", views.qualification_edit, name="qualification_create"),
    path(
        "personnel/people/<int:pk>/qualifications/<int:qualification_pk>/",
        views.qualification_edit,
        name="qualification_edit",
    ),
    path(
        "personnel/people/<int:pk>/qualifications/<int:qualification_pk>/delete/",
        views.qualification_delete,
        name="qualification_delete",
    ),
    path(
        "personnel/people/<int:pk>/qualifications/<int:qualification_pk>/certificate/",
        views.qualification_document,
        name="qualification_document",
    ),
    path("personnel/people/<int:pk>/anonymise/", views.person_anonymise, name="person_anonymise"),
    # What a person does for themselves, without access to the personnel module (PER-012, PER-019).
    path("me/", views.own_profile, name="own_profile"),
    path("me/absences/", views.own_absence_add, name="own_absence_add"),
    path("me/absences/<int:absence_pk>/delete/", views.own_absence_delete, name="own_absence_delete"),
    # PER-021 to PER-023: the own availability calendar and the calendar links.
    path("me/availability/", calendar_views.own_availability, name="own_availability"),
    path("me/availability/remove/", calendar_views.own_availability_remove, name="own_availability_remove"),
    path("me/availability/series/<int:series_pk>/", calendar_views.own_series, name="own_series"),
    path("me/availability/series/<int:series_pk>/remove/", calendar_views.own_series_remove, name="own_series_remove"),
    path("me/calendars/feed/", calendar_views.own_feed, name="own_feed"),
    # PER-031: several linked calendars.
    path("me/calendars/feed/<int:feed_pk>/remove/", calendar_views.own_feed_remove, name="own_feed_remove"),
    path("me/calendars/caldav/", calendar_views.own_caldav, name="own_caldav"),
    path("me/calendars/sync/", calendar_views.own_calendar_sync, name="own_calendar_sync"),
    path("me/calendars/subscription/", calendar_views.own_subscription, name="own_subscription"),
    path("me/deployments.ics", calendar_views.own_deployments_ics, name="own_deployments_ics"),
    path("personnel/people/<int:pk>/availability/", calendar_views.person_availability, name="person_availability"),
    path(
        "personnel/people/<int:pk>/availability/mark/",
        calendar_views.person_availability_mark,
        name="person_availability_mark",
    ),
    path(
        "personnel/people/<int:pk>/availability/remove/",
        calendar_views.person_availability_remove,
        name="person_availability_remove",
    ),
    path(
        "personnel/people/<int:pk>/availability/series/<int:series_pk>/",
        calendar_views.person_series,
        name="person_series",
    ),
    path(
        "personnel/people/<int:pk>/availability/series/<int:series_pk>/remove/",
        calendar_views.person_series_remove,
        name="person_series_remove",
    ),
    path("personnel/people/<int:pk>/calendar/", calendar_views.person_feed, name="person_feed"),
    path(
        "personnel/people/<int:pk>/calendar/<int:feed_pk>/remove/",
        calendar_views.person_feed_remove,
        name="person_feed_remove",
    ),
    # PER-038: the price offers of freelancers – make, accept, reject, counter, withdraw; the overview; settings.
    path("projects/<project:pk>/crew/<int:line_pk>/offer/", offer_views.offer_make, name="offer_make"),
    path(
        "projects/<project:pk>/crew/<int:line_pk>/offers/<int:offer_pk>/accept/",
        offer_views.offer_accept,
        name="offer_accept",
    ),
    path(
        "projects/<project:pk>/crew/<int:line_pk>/offers/<int:offer_pk>/reject/",
        offer_views.offer_reject,
        name="offer_reject",
    ),
    path(
        "projects/<project:pk>/crew/<int:line_pk>/offers/<int:offer_pk>/counter/",
        offer_views.offer_counter,
        name="offer_counter",
    ),
    path(
        "projects/<project:pk>/crew/<int:line_pk>/offers/<int:offer_pk>/withdraw/",
        offer_views.offer_withdraw,
        name="offer_withdraw",
    ),
    path("personnel/offers/", offer_views.offer_list, name="offer_list"),
    path("administration/price-offers/", offer_views.offer_settings, name="offer_settings"),
    # Without login, with the secret token (PER-023); see PUBLIC_PATH_PREFIXES.
    path("calendar-feed/<int:pk>/<slug:token>.ics", calendar_views.calendar_feed, name="calendar_feed"),
]
