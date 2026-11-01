# SPDX-License-Identifier: GPL-3.0-or-later
"""Addresses of the projects module."""

from django.urls import path

from rentalars.projects import (
    bulk_views,
    case_views,
    course_views,
    crew_views,
    family_views,
    follow_up_views,
    group_views,
    legacy_views,
    line_views,
    logistics_views,
    mvr_views,
    my_deployments,
    relation_views,
    report_views,
    split_views,
    staffing_views,
    subrental_views,
    template_content_views,
    template_views,
    trip_views,
    views,
)

app_name = "projects"

urlpatterns = [
    path("projects/", views.project_list, name="list"),
    # PRJ-115, MAT-053: "Auswertung" – profitability of the projects and of the material.
    path("reports/", report_views.profitability_page, name="report"),
    path("reports/material/", report_views.material_report_page, name="report_material"),
    path("material/items/<int:item_pk>/revenue/", report_views.item_revenue_part, name="item_revenue"),
    # MAT-058: the same for a model, over all its items.
    path("material/models/<int:model_pk>/revenue/", report_views.model_revenue_part, name="model_revenue"),
    path("projects/open-items/", course_views.open_items_overview, name="open_items"),
    # Service cases (PRJ-090) – before the addresses of a single project, which take any number.
    path("projects/service-cases/", case_views.case_list, name="cases"),
    # Actions on the ticked rows of the lists (projects.bulk).
    path("projects/bulk/", bulk_views.projects_action, name="bulk_projects"),
    path("projects/service-cases/bulk/", bulk_views.cases_action, name="bulk_cases"),
    path("projects/service-cases/new/", case_views.case_create, name="case_create"),
    path("projects/<project:pk>/case/", case_views.case_detail, name="case_detail"),
    path("projects/<project:pk>/case/edit/", case_views.case_edit, name="case_edit"),
    path("projects/<project:pk>/case/status/", case_views.case_status, name="case_status"),
    path("projects/<project:pk>/case/customer-pdf/", case_views.case_customer_pdf, name="case_customer_pdf"),
    path("projects/<project:pk>/case/convert/", case_views.case_convert, name="case_convert"),
    # People taking part in a service case (PRJ-108); the own cases under "My area".
    path("projects/<project:pk>/case/participants/", case_views.participant_add, name="case_participant_add"),
    path(
        "projects/<project:pk>/case/participants/<int:participant_pk>/remove/",
        case_views.participant_remove,
        name="case_participant_remove",
    ),
    path("me/service-cases/", case_views.my_cases, name="my_cases"),
    # My area → Meine Einsätze, the first tab (UIX-043).
    path("me/deployments/", my_deployments.my_deployments, name="my_deployments"),
    # Divide a project into subprojects, turn groups into subprojects (PRJ-050).
    path("projects/<project:pk>/split/", split_views.split, name="split"),
    # PRJ-076: project templates.
    path("projects/templates/", template_views.template_list, name="templates"),
    path("projects/templates/<int:template_pk>/", template_views.template_edit, name="template_edit"),
    path("projects/templates/<int:template_pk>/delete/", template_views.template_delete, name="template_delete"),
    # PRJ-135: the content of a template.
    path(
        "projects/templates/<int:template_pk>/content/",
        template_content_views.template_content,
        name="template_content",
    ),
    path(
        "projects/templates/<int:template_pk>/content/notes/", template_content_views.notes_form, name="template_notes"
    ),
    path(
        "projects/templates/<int:template_pk>/content/<str:section>/add/",
        template_content_views.entry_form,
        name="template_entry_add",
    ),
    path(
        "projects/templates/<int:template_pk>/content/<str:section>/<int:key>/edit/",
        template_content_views.entry_form,
        name="template_entry_edit",
    ),
    path(
        "projects/templates/<int:template_pk>/content/<str:section>/<int:key>/delete/",
        template_content_views.entry_delete,
        name="template_entry_delete",
    ),
    path(
        "projects/templates/<int:template_pk>/content/<str:section>/<int:key>/move/",
        template_content_views.entry_move,
        name="template_entry_move",
    ),
    path("projects/new/", views.project_edit, name="create"),
    path("projects/<project:pk>/", views.project_detail, name="detail"),
    # PRJ-104 (tab order; PRJ-125): where opening a project leads – the "Überblick", the first tab.
    path("projects/<project:pk>/overview/", views.project_overview, name="overview"),
    path("projects/<project:pk>/edit/", views.project_edit, name="edit"),
    path("projects/<project:pk>/delete/", views.project_delete, name="delete"),
    path("projects/<project:pk>/status/", views.project_set_status, name="set_status"),
    # PRJ-105: the follow-up ("Wiedervorlage").
    path("projects/<project:pk>/follow-up/", follow_up_views.follow_up_edit, name="follow_up"),
    path("projects/<project:pk>/follow-up/done/", follow_up_views.follow_up_done, name="follow_up_done"),
    path("projects/<project:pk>/prices/", views.price_overview, name="price_overview"),
    path(
        "projects/<project:pk>/prices/pdf/",
        views.price_overview_file,
        {"file_format": "pdf"},
        name="price_overview_pdf",
    ),
    path(
        "projects/<project:pk>/prices/csv/",
        views.price_overview_file,
        {"file_format": "csv"},
        name="price_overview_csv",
    ),
    path("projects/<project:pk>/history/", views.project_history, name="history"),
    # Requests of the planning page that answer with the refreshed planning block.
    path("projects/<project:pk>/lines/add/", views.line_add, name="line_add"),
    path("projects/<project:pk>/lines/add-free/", views.free_line_add, name="free_line_add"),
    # A line that only carries a text (heading, remark).
    path("projects/<project:pk>/lines/add-text/", line_views.text_line_add, name="text_line_add"),
    path("projects/<project:pk>/lines/availability/", views.line_availability, name="line_availability"),
    path("projects/<project:pk>/lines/<int:line_pk>/", views.line_edit, name="line_edit"),
    path("projects/<project:pk>/lines/<int:line_pk>/delete/", views.line_delete, name="line_delete"),
    path("projects/<project:pk>/lines/<int:line_pk>/subrent/", views.subrental_accept, name="subrental_accept"),
    path("projects/<project:pk>/arrange/", views.arrange, name="arrange"),
    path("projects/<project:pk>/planning/notes/", views.planning_notes, name="planning_notes"),
    path("projects/<project:pk>/planning/availability/", views.planning_availability, name="planning_availability"),
    path("projects/<project:pk>/overall-discount/", views.overall_discount_edit, name="overall_discount"),
    path("projects/<project:pk>/groups/add/", views.group_add, name="group_add"),
    path("projects/<project:pk>/groups/<int:group_pk>/", views.group_edit, name="group_edit"),
    path("projects/<project:pk>/groups/<int:group_pk>/delete/", views.group_delete, name="group_delete"),
    path("projects/<project:pk>/groups/<int:group_pk>/copy/", views.group_copy, name="group_copy"),
    # PRJ-037: move a group into another one, out to the top level, or among its siblings.
    path("projects/<project:pk>/groups/<int:group_pk>/move/", group_views.group_move, name="group_move"),
    path("projects/<project:pk>/refresh-scales/", views.refresh_scales, name="refresh_scales"),
    # People of the project: crew lines (PRJ-019 ff.), deployment view (AUT-025), members (AUT-016).
    path("projects/<project:pk>/crew/add/", crew_views.crew_add, name="crew_add"),
    path("projects/<project:pk>/crew/times/", crew_views.crew_times, name="crew_times"),
    # PRJ-117: several crew lines at once – plan firmly, ask, delete; values in a dialog.
    path("projects/<project:pk>/crew/bulk/", crew_views.crew_bulk, name="crew_bulk"),
    path("projects/<project:pk>/crew/bulk/edit/", crew_views.crew_bulk_edit, name="crew_bulk_edit"),
    path("projects/<project:pk>/crew/<int:line_pk>/", crew_views.crew_edit, name="crew_edit"),
    path("projects/<project:pk>/crew/<int:line_pk>/delete/", crew_views.crew_delete, name="crew_delete"),
    # LOG-001 ff.: the block "Logistik" – vehicle bookings and the vehicles on the trips.
    path("projects/<project:pk>/logistics/add/", logistics_views.vehicle_add, name="vehicle_add"),
    path("projects/<project:pk>/logistics/<int:line_pk>/", logistics_views.vehicle_edit, name="vehicle_edit"),
    path(
        "projects/<project:pk>/logistics/<int:line_pk>/delete/", logistics_views.vehicle_delete, name="vehicle_delete"
    ),
    path("projects/<project:pk>/logistics/trips/new/", logistics_views.trip_vehicle_add, name="trip_vehicle_add"),
    path(
        "projects/<project:pk>/logistics/trips/<int:use_pk>/",
        logistics_views.trip_vehicle_edit,
        name="trip_vehicle_edit",
    ),
    path(
        "projects/<project:pk>/logistics/trips/<int:use_pk>/delete/",
        logistics_views.trip_vehicle_delete,
        name="trip_vehicle_delete",
    ),
    # LOG-017: the kilometres of a trip from the route service, if it is set up.
    path("projects/<project:pk>/logistics/route/<slug:key>/", logistics_views.trip_route, name="trip_route"),
    path("projects/<project:pk>/deployment/", crew_views.deployment, name="deployment"),
    path("projects/<project:pk>/members/", crew_views.members, name="members"),
    path("projects/<project:pk>/members/<int:membership_pk>/remove/", crew_views.member_remove, name="member_remove"),
    # PRJ-119: the box "Verwandt" of the overview and of a service case – suggest, link, unlink.
    path("projects/<project:pk>/related/suggest/", relation_views.relation_suggest, name="relation_suggest"),
    path("projects/<project:pk>/related/add/", relation_views.relation_add, name="relation_add"),
    path(
        "projects/<project:pk>/related/<int:relation_pk>/remove/",
        relation_views.relation_remove,
        name="relation_remove",
    ),
    path("projects/<project:pk>/crew/<int:line_pk>/request/", crew_views.crew_request, name="crew_request"),
    path("projects/<project:pk>/crew/<int:line_pk>/answer/", crew_views.crew_answer, name="crew_answer"),
    # Course of the project (PRJ-006, PRJ-059), files (PRJ-007), duplicating (PRJ-029).
    path("projects/<project:pk>/course/", course_views.course_page, name="course"),
    path("projects/<project:pk>/phases/new/", course_views.phase_edit, name="phase_create"),
    # PRJ-094: a new phase in a dialog over the crew planning.
    path("projects/<project:pk>/phases/new/dialog/", course_views.phase_dialog, name="phase_dialog"),
    path("projects/<project:pk>/phases/<int:phase_pk>/", course_views.phase_edit, name="phase_edit"),
    path("projects/<project:pk>/phases/<int:phase_pk>/delete/", course_views.phase_delete, name="phase_delete"),
    # PRJ-100: "Extend" – the rental period grows to cover a phase beyond it.
    path(
        "projects/<project:pk>/phases/<int:phase_pk>/extend-period/",
        course_views.phase_extend_period,
        name="phase_extend_period",
    ),
    # PRJ-080: plan personnel for one phase, from the page "Zeitplanung" – function by function (PRJ-120), then the
    # people of the places, with the people suggested while typing.
    path("projects/<project:pk>/phases/<int:phase_pk>/crew/", staffing_views.phase_staffing, name="phase_crew_add"),
    path("projects/<project:pk>/phases/<int:phase_pk>/people/", staffing_views.phase_people, name="phase_people"),
    # Trips changed, removed, reset or added by hand (PRJ-111).
    path("projects/<project:pk>/trips/new/", trip_views.trip_add, name="trip_add"),
    path("projects/<project:pk>/trips/<slug:key>/", trip_views.trip_edit, name="trip_edit"),
    path("projects/<project:pk>/trips/<slug:key>/remove/", trip_views.trip_remove, name="trip_remove"),
    path("projects/<project:pk>/trips/<slug:key>/reset/", trip_views.trip_reset, name="trip_reset"),
    path("projects/<project:pk>/open-items/add/", course_views.open_items_add, name="open_items_add"),
    path(
        "projects/<project:pk>/open-items/<int:item_pk>/done/", course_views.open_item_toggle, name="open_item_toggle"
    ),
    path(
        "projects/<project:pk>/open-items/<int:item_pk>/delete/", course_views.open_item_delete, name="open_item_delete"
    ),
    path("projects/<project:pk>/files/", course_views.files_page, name="files"),
    path("projects/<project:pk>/files/<int:file_pk>/", course_views.file_download, name="file_download"),
    path("projects/<project:pk>/files/<int:file_pk>/edit/", course_views.file_edit, name="file_edit"),
    path("projects/<project:pk>/files/<int:file_pk>/delete/", course_views.file_delete, name="file_delete"),
    path("projects/<project:pk>/duplicate/", course_views.duplicate, name="duplicate"),
    path("projects/<project:pk>/save-as-template/", template_views.template_create, name="template_create"),
    # PRJ-077: take over a lighting plot from an MVR file.
    path("projects/<project:pk>/mvr/", mvr_views.mvr_import, name="mvr_import"),
    # Duplicate a line (PRJ-075), take over new prices of the products (PRJ-072).
    path("projects/<project:pk>/lines/<int:line_pk>/duplicate/", line_views.line_duplicate, name="line_duplicate"),
    # Several lines at once (PRJ-082); optional and alternative lines and groups (PRJ-083).
    path("projects/<project:pk>/lines/bulk/", line_views.lines_bulk, name="lines_bulk"),
    path("projects/<project:pk>/lines/alternative/", line_views.lines_alternative, name="lines_alternative"),
    path("projects/<project:pk>/groups/<int:group_pk>/kind/", group_views.group_kind, name="group_kind"),
    path(
        "projects/<project:pk>/groups/<int:group_pk>/alternative/",
        group_views.group_alternative,
        name="group_alternative",
    ),
    path("projects/<project:pk>/changes/update/", line_views.changes_update, name="changes_update"),
    # Subprojects (PRJ-044 ff.) and material taken over between them (PRJ-060).
    path("projects/<project:pk>/subprojects/new/", family_views.subproject_create, name="subproject_create"),
    path("projects/<project:pk>/parts/", family_views.family_overview, name="family"),
    path("projects/<project:pk>/lines/take-over/", family_views.takeover, name="takeover"),
    # The supplier of a subrental with suggestions and "create" (PRJ-101); the page per project and
    # supplier with lines, documents and correspondence, and the supplier of a mail (PRJ-106).
    path("projects/suppliers/suggest/", subrental_views.supplier_suggest, name="supplier_suggest"),
    path("projects/suppliers/new/", subrental_views.supplier_quick_create, name="supplier_quick_create"),
    path("projects/<project:pk>/subrentals/<int:supplier_pk>/", subrental_views.subrental_page, name="subrental"),
    path(
        "projects/<project:pk>/subrentals/<int:supplier_pk>/lines/",
        subrental_views.subrental_lines_update,
        name="subrental_lines",
    ),
    path(
        "projects/<project:pk>/subrentals/<int:supplier_pk>/documents/",
        subrental_views.subrental_document_add,
        name="subrental_document_add",
    ),
    path("projects/<project:pk>/mails/<int:mail_pk>/supplier/", subrental_views.mail_supplier, name="mail_supplier"),
    # "Altprojekte importieren" in Buchhaltung – old projects from the PDF invoices of the old system.
    path("accounting/legacy/", legacy_views.overview, name="legacy"),
    path("accounting/legacy/<int:pk>/", legacy_views.batch_page, name="legacy_batch"),
    path("accounting/legacy/<int:pk>/progress/", legacy_views.batch_progress, name="legacy_progress"),
    path("accounting/legacy/<int:pk>/undo/", legacy_views.batch_undo, name="legacy_undo"),
    path("accounting/legacy/items/<int:pk>/pdf/", legacy_views.item_pdf, name="legacy_pdf"),
]
