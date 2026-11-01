# SPDX-License-Identifier: GPL-3.0-or-later
"""Addresses of the core module."""

from django.urls import path

from rentalars.core import address_views, bulk, import_views, map_views, settings_views, surcharge_views, views
from rentalars.core.about import about_text_page, about_text_view, about_view
from rentalars.core.changes import changes_view
from rentalars.core.manual import manual_anchors_view, manual_chapter_view, manual_guide_view, manual_view

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("search/", views.search, name="search"),
    path("bulk/csv/", bulk.bulk_csv, name="bulk_csv"),  # Chosen rows of any table as CSV
    path("manual/", manual_view, name="manual"),  # UIX-029
    # Manual chapters: one page per chapter; the anchors serve the forwarding of old addresses.
    path("manual/anchors/", manual_anchors_view, name="manual_anchors"),
    path("manual/<int:number>/", manual_chapter_view, name="manual_chapter"),
    path("manual/guides/<slug:key>/", manual_guide_view, name="manual_guide"),  # The operating guides
    path("changes/", changes_view, name="changes"),  # UIX-020
    path("about/", about_view, name="about"),  # UIX-062: the legal notices, also without login
    path("about/<slug:name>.txt", about_text_view, name="about_text"),
    path("about/<slug:name>/", about_text_page, name="about_page"),  # V21: as a page of the program
    path("setup/", views.setup, name="setup"),
    path("administration/", views.administration, name="administration"),
    path("administration/settings/", views.company_settings, name="company_settings"),
    path("administration/number-ranges/", views.number_ranges, name="number_ranges"),
    path("administration/audit-log/", views.audit_log, name="audit_log"),
    path("administration/self-check/", views.self_check, name="self_check"),
    # Access log (AUT-028), backup and encryption (ADM-009, ADM-010).
    path("administration/access-log/", settings_views.access_log_page, name="access_log"),
    path("administration/backup/", settings_views.backup_page, name="backup"),
    path("administration/backup/start/", settings_views.backup_start, name="backup_start"),
    path("administration/backup/<int:pk>/", settings_views.backup_job, name="backup_job"),
    # IMP-006: the full export of all data is a part of "Sicherung" (NFA-074).
    path("administration/backup/export/", settings_views.full_export, name="full_export"),
    # PER-009: surcharges for night, Sunday and holidays.
    path("administration/surcharges/", surcharge_views.time_surcharges, name="time_surcharges"),
    # PER-040: the button "Nach § 3b EStG einstellen".
    path(
        "administration/surcharges/section-3b/",
        surcharge_views.time_surcharges_section_3b,
        name="time_surcharges_section_3b",
    ),
    # ADM-016: server address and certificate – prepared here, applied by a command on the server.
    path("administration/server-address/", address_views.server_address_page, name="server_address"),
    path(
        "administration/server-address/<slug:token>/discard/",
        address_views.server_address_discard,
        name="server_address_discard",
    ),
    path("media/<path:path>", views.media_file, name="media"),
    path("tables/<slug:key>/columns/", views.table_columns, name="table_columns"),
    path("import/<slug:key>/", import_views.import_page, name="import"),
    # IMP-017: the list of an import as CSV in the import's format.
    path("import/<slug:key>/export/", import_views.import_format_export, name="import_export"),
    path("jobs/", views.job_list, name="jobs"),
    path("jobs/<int:pk>/", views.job_detail, name="job"),
    path("jobs/<int:pk>/result/", views.job_result, name="job_result"),
    # UIX-034: the map of an address after "Karte anzeigen", and a position set by hand.
    path("maps/<slug:target>/<int:pk>/", map_views.map_part, name="map"),
    path("maps/<slug:target>/<int:pk>/position/", map_views.map_position, name="map_position"),
]
