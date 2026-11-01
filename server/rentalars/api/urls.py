# SPDX-License-Identifier: GPL-3.0-or-later
"""All addresses of the API, version 1 (API-005).

The path carries the version: ``/api/v1/…``. Incompatible changes will get a
new prefix (``/api/v2/``) next to this one instead of altering it.

Each business module defines its own serializers and views in its ``api``
module (NFA-021); this file only wires them to addresses, following chapter 8
of the requirements catalogue.
"""

from __future__ import annotations

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from rentalars.accounts import api as accounts
from rentalars.accounts import ldap_api as accounts_ldap  # AUT-029
from rentalars.ai import api as ai  # EML-040, EML-044, ADM-017
from rentalars.api import webhook_api
from rentalars.automations import api as automations
from rentalars.chat import api as chat
from rentalars.core import address_api as core_address
from rentalars.core import api as core
from rentalars.core import import_api as core_imports
from rentalars.core import map_api as core_maps
from rentalars.core import surcharge_api as core_surcharges
from rentalars.customers import api as customers
from rentalars.customfields import api as customfields  # MAT-071, MAT-072
from rentalars.documents import (  # DOK-016, DOK-019, DOK-020
    accounting_api,
    bank_api,
    free_api,  # Documents without a project
    outgoing_api,
    payment_api,
    statement_api,
)
from rentalars.documents import api as documents
from rentalars.incoming import api as incoming  # incoming invoices
from rentalars.mail import api as mail
from rentalars.masterdata import api as masterdata
from rentalars.material import api as material
from rentalars.material import asset_api as material_assets  # depreciation, used sale from stock
from rentalars.material import audit_api as material_audits  # MAT-069
from rentalars.material import installed_api as material_installed  # MAT-040
from rentalars.material import item_api as material_items
from rentalars.material import label_api as material_labels  # MAT-056
from rentalars.material import purchase_api as material_purchases  # MAT-061
from rentalars.material import scan_api  # MAT-027, UIX-006
from rentalars.material import vehicle_api as material_vehicles  # LOG-015
from rentalars.notifications import api as notifications
from rentalars.packing import api as packing
from rentalars.personnel import api as personnel
from rentalars.personnel import offer_api as personnel_offers  # PER-038
from rentalars.personnel import own_api as personnel_own  # API-015
from rentalars.products import api as products
from rentalars.products import suggestions_api as product_relations  # PRD-023, VFG-015
from rentalars.projects import access_rows as project_access  # AUT-035
from rentalars.projects import api as projects
from rentalars.projects import (
    bulk_api,
    case_api,
    crew_api,
    legacy_api,  # The import of old projects from invoices
    line_api,
    logistics_api,
    mvr_api,
    product_changes_api,
    subrental_api,
    trip_api,
)
from rentalars.projects import course_api as course
from rentalars.projects import relation_api as project_relations  # PRJ-119
from rentalars.projects import report_api as reports  # PRJ-115, MAT-053
from rentalars.projects import staffing_api as phase_staffing  # PRJ-120
from rentalars.schedule import api as schedule
from rentalars.schedule import calendar_link_api as calendar_links  # VFG-040
from rentalars.schedule import move_api as schedule_moves
from rentalars.timetracking import api as timetracking
from rentalars.timetracking import expense_api as timetracking_expenses

app_name = "api"

router = DefaultRouter(trailing_slash=False)
router.include_root_view = False
router.register("users", accounts.UserViewSet, basename="user")
router.register("roles", accounts.RoleViewSet, basename="role")
router.register("tokens", accounts.ApiTokenViewSet, basename="token")
router.register("categories", masterdata.CategoryViewSet, basename="category")
router.register("category-fields", masterdata.CategoryFieldViewSet, basename="category-field")
# MAT-071, MAT-072: the definitions and fieldsets of the custom fields of items.
router.register("custom-fields", customfields.CustomFieldViewSet, basename="custom-field")
router.register("custom-fieldsets", customfields.FieldsetViewSet, basename="custom-fieldset")
router.register("units", masterdata.UnitViewSet, basename="unit")
router.register("tax-rates", masterdata.TaxRateViewSet, basename="tax-rate")
router.register("tax-accounts", masterdata.TaxAccountViewSet, basename="tax-account")
router.register("manufacturers", masterdata.ManufacturerViewSet, basename="manufacturer")
router.register("suppliers", masterdata.SupplierViewSet, basename="supplier")
router.register("storage-locations", masterdata.StorageLocationViewSet, basename="storage-location")
router.register("rental-scales", masterdata.RentalScaleViewSet, basename="rental-scale")
router.register("number-ranges", core.NumberRangeViewSet, basename="number-range")
router.register("audit-log", core.AuditLogViewSet, basename="audit-log")
router.register("material-models", material.MaterialModelViewSet, basename="material-model")
router.register("material-items", material.MaterialItemViewSet, basename="material-item")
router.register("inspection-types", material_items.InspectionTypeViewSet, basename="inspection-type")
router.register("products", products.ProductViewSet, basename="product")
router.register("customers", customers.CustomerViewSet, basename="customer")
router.register("venues", customers.VenueViewSet, basename="venue")
router.register("projects", projects.ProjectViewSet, basename="project")
router.register("service-cases", case_api.ServiceCaseViewSet, basename="service-case")  # PRJ-090
router.register("project-templates", projects.ProjectTemplateViewSet, basename="project-template")  # PRJ-076
router.register("job-functions", personnel.JobFunctionViewSet, basename="job-function")
router.register("people", personnel.PersonViewSet, basename="person")
router.register("qualification-types", personnel.QualificationTypeViewSet, basename="qualification-type")
router.register("document-templates", documents.DocumentTemplateViewSet, basename="document-template")
router.register("text-blocks", documents.TextBlockViewSet, basename="text-block")
router.register("time-entries", timetracking.TimeEntryViewSet, basename="time-entry")
router.register("expenses", timetracking_expenses.ExpenseViewSet, basename="expense")  # ZEI-019
router.register("webhooks", webhook_api.WebhookViewSet, basename="webhook")  # API-012
router.register("mail/mailboxes", mail.MailboxViewSet, basename="mailbox")  # EML-041
router.register("mail/mailbox-addresses", mail.MailboxAddressViewSet, basename="mailbox-address")  # EML-047
router.register("ai/providers", ai.AIProviderViewSet, basename="ai-provider")  # ADM-017
router.register("ldap/mappings", accounts_ldap.LdapMappingViewSet, basename="ldap-mapping")  # AUT-029

# Resources that live below another resource get their addresses by hand.
LIST = {"get": "list", "post": "create"}
DETAIL = {"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"}

nested = [
    path("customers/<int:customer_pk>/contacts", customers.ContactViewSet.as_view(LIST), name="contact-list"),
    path(
        "customers/<int:customer_pk>/contacts/<int:pk>", customers.ContactViewSet.as_view(DETAIL), name="contact-detail"
    ),
    path("customers/<int:customer_pk>/addresses", customers.CustomerAddressViewSet.as_view(LIST), name="address-list"),
    path(
        "customers/<int:customer_pk>/addresses/<int:pk>",
        customers.CustomerAddressViewSet.as_view(DETAIL),
        name="address-detail",
    ),
    # PRJ-050: divide a project into subprojects, turn groups into subprojects.
    path("projects/<int:project_pk>/split", case_api.SplitView.as_view(), name="project-split"),
    # PRJ-119: related projects and service cases, both ways.
    path(
        "projects/<int:project_pk>/relations",
        project_relations.ProjectRelationsView.as_view(),
        name="project-relation-list",
    ),
    path(
        "projects/<int:project_pk>/relations/<int:pk>",
        project_relations.ProjectRelationView.as_view(),
        name="project-relation-detail",
    ),
    path("projects/<int:project_pk>/groups", projects.GroupViewSet.as_view(LIST), name="group-list"),
    path(
        "projects/<int:project_pk>/groups/reorder",
        projects.GroupViewSet.as_view({"post": "reorder"}),
        name="group-reorder",
    ),
    path("projects/<int:project_pk>/groups/<int:pk>", projects.GroupViewSet.as_view(DETAIL), name="group-detail"),
    path(
        "projects/<int:project_pk>/groups/<int:pk>/copy",
        projects.GroupViewSet.as_view({"post": "copy"}),
        name="group-copy",
    ),
    # PRJ-037: move a group into another one, out to the top level, or among its siblings.
    path(
        "projects/<int:project_pk>/groups/<int:pk>/move",
        projects.GroupViewSet.as_view({"post": "move"}),
        name="group-move",
    ),
    path("projects/<int:project_pk>/material-lines", projects.MaterialLineViewSet.as_view(LIST), name="line-list"),
    path(
        "projects/<int:project_pk>/material-lines/<int:pk>",
        projects.MaterialLineViewSet.as_view(DETAIL),
        name="line-detail",
    ),
    path(
        "projects/<int:project_pk>/material-lines/<int:pk>/surcharge-targets",
        projects.MaterialLineViewSet.as_view({"get": "surcharge_targets", "put": "surcharge_targets"}),
        name="line-surcharge-targets",
    ),
    # Duplicate a line (PRJ-075), old prices of the products (PRJ-072).
    path(
        "projects/<int:project_pk>/material-lines/<int:pk>/duplicate",
        line_api.DuplicateLineView.as_view(),
        name="line-duplicate",
    ),
    path("projects/<int:project_pk>/old-prices", line_api.OldPricesView.as_view(), name="project-old-prices"),
    # What the products changed since the lines took them over (PRJ-072) - names, units, taxes, prices.
    path(
        "projects/<int:project_pk>/product-changes",
        product_changes_api.ProjectProductChangesView.as_view(),
        name="project-product-changes",
    ),
    path(
        "products/<int:pk>/unconfirmed-projects",
        product_changes_api.ProductUnconfirmedProjectsView.as_view(),
        name="product-unconfirmed-projects",
    ),
    # Several lines at once (PRJ-082).
    path("projects/<int:project_pk>/material-lines/bulk", line_api.BulkLinesView.as_view(), name="line-bulk"),
    # Several projects or service cases at once – the follow-up, the status, the person responsible.
    path("projects/bulk", bulk_api.ProjectsBulkView.as_view(), name="project-bulk"),
    path("service-cases/bulk", bulk_api.ServiceCasesBulkView.as_view(), name="service-case-bulk"),
    path("projects/<int:project_pk>/crew-lines", projects.CrewLineViewSet.as_view(LIST), name="crew-line-list"),
    # PRJ-117: several crew lines at once – set values, plan firmly, ask, delete.
    path("projects/<int:project_pk>/crew-lines/bulk", crew_api.CrewBulkView.as_view(), name="crew-line-bulk"),
    path(
        "projects/<int:project_pk>/crew-lines/unassigned-times",
        projects.CrewLineViewSet.as_view({"get": "unassigned_times", "post": "unassigned_times"}),
        name="crew-line-unassigned-times",
    ),
    path(
        "projects/<int:project_pk>/crew-lines/planned-and-actual",
        projects.CrewLineViewSet.as_view({"get": "planned_and_actual"}),
        name="crew-line-planned-and-actual",
    ),
    path(
        "projects/<int:project_pk>/crew-lines/<int:pk>",
        projects.CrewLineViewSet.as_view(DETAIL),
        name="crew-line-detail",
    ),
    path("projects/<int:project_pk>/members", projects.MembershipViewSet.as_view(LIST), name="member-list"),
    # AUT-035: everybody assigned to the project – members, crew, case – with the access that holds.
    path("projects/<int:project_pk>/access", project_access.ProjectAccessListView.as_view(), name="project-access"),
    path(
        "projects/<int:project_pk>/members/<int:pk>",
        projects.MembershipViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="member-detail",
    ),
    path(
        "projects/<int:project_pk>/crew-lines/<int:pk>/request",
        projects.CrewLineViewSet.as_view({"post": "ask"}),
        name="crew-line-request",
    ),
    path(
        "projects/<int:project_pk>/crew-lines/<int:pk>/answer",
        projects.CrewLineViewSet.as_view({"post": "answer"}),
        name="crew-line-answer",
    ),
    # PER-038: price offers of freelancers for a deployment request – the exchange, and the answers to a proposal.
    path(
        "projects/<int:project_pk>/crew-lines/<int:pk>/offers",
        personnel_offers.CrewLineOffersView.as_view(),
        name="crew-line-offers",
    ),
    path(
        "projects/<int:project_pk>/crew-lines/<int:pk>/offers/<int:offer_pk>/accept",
        personnel_offers.AcceptOfferView.as_view(),
        name="crew-line-offer-accept",
    ),
    path(
        "projects/<int:project_pk>/crew-lines/<int:pk>/offers/<int:offer_pk>/reject",
        personnel_offers.RejectOfferView.as_view(),
        name="crew-line-offer-reject",
    ),
    path(
        "projects/<int:project_pk>/crew-lines/<int:pk>/offers/<int:offer_pk>/counter",
        personnel_offers.CounterOfferView.as_view(),
        name="crew-line-offer-counter",
    ),
    path(
        "projects/<int:project_pk>/crew-lines/<int:pk>/offers/<int:offer_pk>/withdraw",
        personnel_offers.WithdrawOfferView.as_view(),
        name="crew-line-offer-withdraw",
    ),
    path("price-offers", personnel_offers.PriceOffersView.as_view(), name="price-offers"),
    path("settings/price-offers", personnel_offers.OfferSettingsView.as_view(), name="settings-price-offers"),
    path("projects/<int:project_pk>/deployment", projects.DeploymentView.as_view(), name="project-deployment"),
    # PRD-023, VFG-015 (accessory and replacement suggestions): the relations of a product, the suggestions of a project.
    path("products/<int:pk>/relations", product_relations.ProductRelationsView.as_view(), name="product-relations"),
    path(
        "products/<int:pk>/relations/<int:relation_pk>",
        product_relations.ProductRelationView.as_view(),
        name="product-relation",
    ),
    path(
        "products/<int:pk>/relations/<int:relation_pk>/move",
        product_relations.ProductRelationMoveView.as_view(),
        name="product-relation-move",
    ),
    path(
        "products/<int:pk>/relations/<int:relation_pk>/remove",
        product_relations.ProductRelationRemoveView.as_view(),
        name="product-relation-remove",
    ),
    path(
        "projects/<int:project_pk>/suggestions",
        product_relations.ProjectSuggestionsView.as_view(),
        name="project-suggestions",
    ),
    path(
        "projects/<int:project_pk>/suggestions/dismiss",
        product_relations.ProjectSuggestionDismissView.as_view(),
        name="project-suggestions-dismiss",
    ),
    path(
        "projects/<int:project_pk>/suggestions/restore",
        product_relations.ProjectSuggestionRestoreView.as_view(),
        name="project-suggestions-restore",
    ),
    path(
        "projects/<int:project_pk>/suggestions/<int:relation_pk>/add",
        product_relations.ProjectSuggestionAddView.as_view(),
        name="project-suggestion-add",
    ),
    # LOG-001 ff., LOG-015: the logistics of a project – vehicle bookings and the vehicles on the trips.
    path(
        "projects/<int:project_pk>/logistics",
        logistics_api.ProjectLogisticsView.as_view(),
        name="project-logistics",
    ),
    path(
        "projects/<int:project_pk>/logistics/<int:pk>",
        logistics_api.VehicleLineView.as_view(),
        name="project-vehicle-line",
    ),
    path(
        "projects/<int:project_pk>/trips/<slug:key>/vehicles",
        logistics_api.TripVehiclesView.as_view(),
        name="project-trip-vehicles",
    ),
    path(
        "projects/<int:project_pk>/trip-vehicles/<int:pk>",
        logistics_api.TripVehicleView.as_view(),
        name="project-trip-vehicle",
    ),
    path(
        "projects/<int:project_pk>/trips/<slug:key>/route",
        logistics_api.TripRouteView.as_view(),
        name="project-trip-route",
    ),
    # PRJ-097: the trips of a project with their route links.
    path("projects/<int:project_pk>/trips", trip_api.ProjectTripsView.as_view(), name="project-trips"),
    # PRJ-111: trips changed, removed, reset or added by hand.
    path("projects/<int:project_pk>/trips/<slug:key>", trip_api.ProjectTripView.as_view(), name="project-trip"),
    path(
        "projects/<int:project_pk>/trips/<slug:key>/reset",
        trip_api.ProjectTripResetView.as_view(),
        name="project-trip-reset",
    ),
    path("projects/<int:project_pk>/mvr", mvr_api.MvrImportView.as_view(), name="project-mvr"),  # PRJ-077
    # Course of a project (PRJ-006, PRJ-059, PRJ-007).
    path("projects/<int:project_pk>/phases", course.PhaseViewSet.as_view(LIST), name="phase-list"),
    path("projects/<int:project_pk>/phases/<int:pk>", course.PhaseViewSet.as_view(DETAIL), name="phase-detail"),
    # PRJ-120: personnel for a phase, function by function – job functions, places, people.
    path(
        "projects/<int:project_pk>/phases/<int:phase_pk>/staffing",
        phase_staffing.PhaseStaffingView.as_view(),
        name="phase-staffing",
    ),
    # VFG-026: moving the rental period, the event or a phase – what it would do, and doing it.
    path(
        "projects/<int:project_pk>/reschedule/preview",
        schedule_moves.ReschedulePreviewView.as_view(),
        name="project-reschedule-preview",
    ),
    path("projects/<int:project_pk>/reschedule", schedule_moves.RescheduleView.as_view(), name="project-reschedule"),
    path("projects/<int:project_pk>/open-items", course.OpenItemViewSet.as_view(LIST), name="open-item-list"),
    path(
        "projects/<int:project_pk>/open-items/<int:pk>",
        course.OpenItemViewSet.as_view(DETAIL),
        name="open-item-detail",
    ),
    path("projects/<int:project_pk>/files", course.ProjectFileViewSet.as_view(LIST), name="project-file-list"),
    path(
        "projects/<int:project_pk>/files/<int:pk>",
        course.ProjectFileViewSet.as_view(DETAIL),
        name="project-file-detail",
    ),
    path(
        "projects/<int:project_pk>/files/<int:pk>/content",
        course.ProjectFileViewSet.as_view({"get": "content"}),
        name="project-file-content",
    ),
    # Correspondence (EML-019 ff.).
    path("projects/<int:project_pk>/mails", mail.ProjectMailListView.as_view(), name="project-mail-list"),
    # EML-040, EML-044, ADM-017: overview and AI summary of the correspondence; a reply draft by AI.
    path(
        "projects/<int:project_pk>/correspondence-summary",
        ai.CorrespondenceSummaryView.as_view(),
        name="project-correspondence-summary",
    ),
    path("projects/<int:project_pk>/mails/reply-draft", ai.ReplyDraftView.as_view(), name="project-mail-reply-draft"),
    # EML-051: a note in the correspondence.
    path("projects/<int:project_pk>/mails/notes", mail.ProjectMailNoteView.as_view(), name="project-mail-note"),
    # EML-052: the addresses the caller may send a mail of the project from.
    path("projects/<int:project_pk>/mails/senders", mail.ProjectMailSendersView.as_view(), name="project-mail-senders"),
    path("ai/settings", ai.AISettingsView.as_view(), name="ai-settings"),
    # AUT-029: login with LDAP / Active Directory.
    path("ldap/settings", accounts_ldap.LdapSettingsView.as_view(), name="ldap-settings"),
    path("ldap/test-connection", accounts_ldap.LdapTestConnectionView.as_view(), name="ldap-test-connection"),
    path("ldap/test-login", accounts_ldap.LdapTestLoginView.as_view(), name="ldap-test-login"),
    path("ldap/sync", accounts_ldap.LdapSyncView.as_view(), name="ldap-sync"),
    path("ldap/adopt-dn", accounts_ldap.LdapAdoptDnView.as_view(), name="ldap-adopt-dn"),
    path("ai/local/speed-test", ai.LocalSpeedTestView.as_view(), name="ai-local-speed-test"),
    path("ai/calls", ai.AICallListView.as_view(), name="ai-call-list"),
    # The automatic AI summaries (opt-in, settings, runs, dry run, run now) and the switch per customer.
    path("ai/auto-summaries", ai.AutoSummariesView.as_view(), name="ai-auto-summaries"),
    path("ai/auto-summaries/runs", ai.AutoSummaryRunListView.as_view(), name="ai-auto-summary-runs"),
    path("ai/auto-summaries/dry-run", ai.AutoSummaryDryRunView.as_view(), name="ai-auto-summary-dry-run"),
    path("ai/auto-summaries/run", ai.AutoSummaryRunNowView.as_view(), name="ai-auto-summary-run"),
    path(
        "customers/<int:customer_pk>/ai-summaries", ai.CustomerAutoSummaryView.as_view(), name="customer-ai-summaries"
    ),
    path(
        "projects/<int:project_pk>/mails/<int:mail_pk>",
        mail.ProjectMailDetailView.as_view(),
        name="project-mail-detail",
    ),
    path(
        "projects/<int:project_pk>/mails/<int:mail_pk>/assign",
        mail.ProjectMailAssignView.as_view(),
        name="project-mail-assign",
    ),
    # EML-055: put the lock on a message or take it away.
    path(
        "projects/<int:project_pk>/mails/<int:mail_pk>/lock",
        mail.ProjectMailLockView.as_view(),
        name="project-mail-lock",
    ),
    # PRJ-106: the supplier of subrentals a mail belongs to; the subrentals of a project per supplier.
    path(
        "projects/<int:project_pk>/mails/<int:mail_pk>/supplier",
        mail.ProjectMailSupplierView.as_view(),
        name="project-mail-supplier",
    ),
    path(
        "projects/<int:project_pk>/subrentals",
        subrental_api.ProjectSubrentalListView.as_view(),
        name="project-subrental-list",
    ),
    path(
        "projects/<int:project_pk>/subrentals/<int:supplier_pk>",
        subrental_api.ProjectSubrentalDetailView.as_view(),
        name="project-subrental-detail",
    ),
    path(
        "projects/<int:project_pk>/mails/<int:mail_pk>/attachments/<int:attachment_pk>",
        mail.MailAttachmentView.as_view(),
        name="mail-attachment",
    ),
    path(
        "projects/<int:project_pk>/mails/<int:mail_pk>/attachments/<int:attachment_pk>/to-files",
        mail.MailAttachmentToFilesView.as_view(),
        name="mail-attachment-to-files",
    ),
    path("projects/<int:project_pk>/packlists", packing.PacklistListView.as_view(), name="packlist-list"),
    # PRJ-048, PRJ-060: the whole project with all its parts; handovers between parts.
    path("projects/<int:project_pk>/packlists/family", packing.FamilyPacklistView.as_view(), name="packlist-family"),
    path(
        "projects/<int:project_pk>/packlists/family/pdf",
        packing.FamilyPacklistPdfView.as_view(),
        name="packlist-family-pdf",
    ),
    path(
        "projects/<int:project_pk>/packlists/<int:packlist_pk>/handovers",
        packing.HandoverListView.as_view(),
        name="packlist-handovers",
    ),
    path(
        "projects/<int:project_pk>/packlists/<int:packlist_pk>/handovers/<int:handover_pk>",
        packing.HandoverDetailView.as_view(),
        name="packlist-handover-detail",
    ),
    path(
        "projects/<int:project_pk>/packlists/<int:packlist_pk>",
        packing.PacklistDetailView.as_view(),
        name="packlist-detail",
    ),
    path(
        "projects/<int:project_pk>/packlists/<int:packlist_pk>/rows",
        packing.PacklistRowView.as_view(),
        name="packlist-rows",
    ),
    path(
        "projects/<int:project_pk>/packlists/<int:packlist_pk>/pdf",
        packing.PacklistPdfView.as_view(),
        name="packlist-pdf",
    ),
    path(
        "projects/<int:project_pk>/packlists/<int:packlist_pk>/lines",
        packing.PacklistLinesView.as_view(),
        name="packlist-lines",
    ),
    path(
        "projects/<int:project_pk>/packlists/<int:packlist_pk>/items",
        packing.PacklistItemsView.as_view(),
        name="packlist-items",
    ),
    # PCK-027: what was ticked on the phone. Before ".../<action>", which would take "sync" for a packing step.
    path(
        "projects/<int:project_pk>/packlists/<int:packlist_pk>/sync",
        packing.PacklistSyncView.as_view(),
        name="packlist-sync",
    ),
    path("projects/<int:project_pk>/documents", documents.ProjectDocumentsView.as_view(), name="project-documents"),
    path(
        "projects/<int:project_pk>/documents/preview",
        documents.ProjectDocumentPreviewView.as_view(),
        name="project-document-preview",
    ),
    # PRJ-081: the deployment view as PDF "Einsatzübersicht".
    path(
        "projects/<int:project_pk>/deployment/pdf",
        documents.DeploymentPdfView.as_view(),
        name="project-deployment-pdf",
    ),
    path("documents/<int:pk>", documents.DocumentDetailView.as_view(), name="document-detail"),
    path("documents/<int:pk>/pdf", documents.DocumentPdfView.as_view(), name="document-pdf"),
    path("documents/<int:pk>/xml", documents.DocumentXmlView.as_view(), name="document-xml"),
    path("documents/<int:pk>/cancel", documents.DocumentCancelView.as_view(), name="document-cancel"),
    path("documents/<int:pk>/credit", documents.DocumentCreditView.as_view(), name="document-credit"),
    # DOK-016: the monthly statements of service cases per customer.
    path("service-statements", statement_api.StatementListView.as_view(), name="service-statement-list"),
    path("service-statements/<int:pk>", statement_api.StatementDetailView.as_view(), name="service-statement-detail"),
    path(
        "service-statements/<int:pk>/invoice",
        statement_api.StatementInvoiceView.as_view(),
        name="service-statement-invoice",
    ),
    path("service-statements/<int:pk>/mark", statement_api.StatementMarkView.as_view(), name="service-statement-mark"),
    # DOK-011, DOK-012: handing invoices to the accounting.
    path("documents/<int:pk>/lexware", accounting_api.DocumentLexwareView.as_view(), name="document-lexware"),
    path("accounting/settings", accounting_api.AccountingSettingsView.as_view(), name="accounting-settings"),
    path("accounting/lexware/check", accounting_api.LexwareCheckView.as_view(), name="accounting-lexware-check"),
    path(
        "accounting/lexware/transfers",
        accounting_api.LexwareTransferListView.as_view(),
        name="accounting-lexware-transfers",
    ),
    path("accounting/datev/bookings", accounting_api.DatevBookingsView.as_view(), name="accounting-datev-bookings"),
    path("accounting/datev/debitors", accounting_api.DatevDebitorsView.as_view(), name="accounting-datev-debitors"),
    # DOK-020 (Buchhaltung): the outgoing documents of all customers and their sums.
    # DOK-042 – DOK-048: payments, open items, the check of e-invoices, EÜR, archive, export for an audit.
    path("documents/<int:pk>/payments", payment_api.DocumentPaymentsView.as_view(), name="document-payments"),
    path("payments/<int:pk>/void", payment_api.PaymentVoidView.as_view(), name="payment-void"),
    path("documents/<int:pk>/validation", payment_api.DocumentValidationView.as_view(), name="document-validation"),
    path(
        "incoming-invoices/<int:pk>/payments",
        payment_api.IncomingPaymentsView.as_view(),
        name="incoming-invoice-payments",
    ),
    path(
        "incoming-payments/<int:pk>/void", payment_api.IncomingPaymentVoidView.as_view(), name="incoming-payment-void"
    ),
    path(
        "incoming-invoices/<int:pk>/validation",
        payment_api.IncomingValidationView.as_view(),
        name="incoming-invoice-validation",
    ),
    path("accounting/open-items", payment_api.OpenItemsView.as_view(), name="accounting-open-items"),
    # DOK-050: bank statements
    path("accounting/bank/imports", bank_api.StatementListView.as_view(), name="accounting-bank-imports"),
    path("accounting/bank/transactions", bank_api.TransactionListView.as_view(), name="accounting-bank-transactions"),
    path(
        "accounting/bank/transactions/<int:pk>/book",
        bank_api.TransactionBookView.as_view(),
        name="accounting-bank-transaction-book",
    ),
    path(
        "accounting/bank/transactions/<int:pk>/ignore",
        bank_api.TransactionIgnoreView.as_view(),
        name="accounting-bank-transaction-ignore",
    ),
    path(
        "accounting/bank/transactions/<int:pk>/restore",
        bank_api.TransactionRestoreView.as_view(),
        name="accounting-bank-transaction-restore",
    ),
    path("accounting/euer", payment_api.EuerView.as_view(), name="accounting-euer"),
    path("accounting/archive", payment_api.ArchiveView.as_view(), name="accounting-archive"),
    path("accounting/archive/verify", payment_api.ArchiveVerifyView.as_view(), name="accounting-archive-verify"),
    path("accounting/audit-export", payment_api.AuditExportView.as_view(), name="accounting-audit-export"),
    path("accounting/procedure", payment_api.ProcedureView.as_view(), name="accounting-procedure"),
    path("accounting/documents", outgoing_api.OutgoingDocumentListView.as_view(), name="accounting-documents"),
    path(
        "accounting/documents/totals",
        outgoing_api.OutgoingDocumentTotalsView.as_view(),
        name="accounting-documents-totals",
    ),
    # Outgoing documents without a project – the draft with its lines, issuing, sending.
    path("accounting/documents/drafts", free_api.DraftListView.as_view(), name="accounting-drafts"),
    path("accounting/documents/drafts/<int:pk>", free_api.DraftDetailView.as_view(), name="accounting-draft"),
    path(
        "accounting/documents/drafts/<int:pk>/lines",
        free_api.DraftLineListView.as_view(),
        name="accounting-draft-lines",
    ),
    path(
        "accounting/documents/drafts/<int:pk>/lines/order",
        free_api.DraftLineOrderView.as_view(),
        name="accounting-draft-lines-order",
    ),
    path(
        "accounting/documents/drafts/<int:pk>/lines/<int:line_pk>",
        free_api.DraftLineDetailView.as_view(),
        name="accounting-draft-line",
    ),
    path(
        "accounting/documents/drafts/<int:pk>/preview",
        free_api.DraftPreviewView.as_view(),
        name="accounting-draft-preview",
    ),
    path(
        "accounting/documents/drafts/<int:pk>/issue", free_api.DraftIssueView.as_view(), name="accounting-draft-issue"
    ),
    path("accounting/documents/<int:pk>/send", free_api.DocumentSendView.as_view(), name="accounting-document-send"),
    path("projects/<int:project_pk>/extractions", packing.ExtractionListView.as_view(), name="extraction-list"),
    path(
        "projects/<int:project_pk>/extractions/<int:extraction_pk>",
        packing.ExtractionDetailView.as_view(),
        name="extraction-detail",
    ),
    path(
        "projects/<int:project_pk>/packlists/<int:packlist_pk>/<slug:action>",
        packing.PacklistActionView.as_view(),
        name="packlist-action",
    ),
]

urlpatterns = [
    path("auth/login", accounts.LoginView.as_view(), name="login"),
    path("auth/logout", accounts.LogoutView.as_view(), name="logout"),
    path("auth/password-reset", accounts.PasswordResetView.as_view(), name="password-reset"),
    path("me", accounts.MeView.as_view(), name="me"),
    # PCK-026: the packlists to take along on the phone.
    path("offline/packlists", packing.OfflinePacklistsView.as_view(), name="offline-packlists"),
    path("permissions", accounts.PermissionCatalogueView.as_view(), name="permissions"),
    path("settings", core.SettingsView.as_view(), name="settings"),
    # UIX-033, UIX-034: the places of a map with route links and positions; a position set by hand.
    path("maps/<slug:target>/<int:pk>", core_maps.MapView.as_view(), name="map-detail"),
    path(
        "maps/<slug:target>/<int:pk>/positions/<str:key>",
        core_maps.MapPositionView.as_view(),
        name="map-position",
    ),
    # PER-009: surcharges for night, Sunday and holidays, and the holidays Rentalars computes.
    path("settings/surcharges", core_surcharges.TimeSurchargeSettingsView.as_view(), name="settings-surcharges"),
    # PER-040: "Nach § 3b EStG einstellen".
    path(
        "settings/surcharges/section-3b",
        core_surcharges.SectionThreeBView.as_view(),
        name="settings-surcharges-section-3b",
    ),
    path("holidays", core_surcharges.HolidaysView.as_view(), name="holidays"),
    path("search", core.SearchView.as_view(), name="search"),
    path("availability", products.AvailabilityView.as_view(), name="availability"),
    path("shortages", projects.ShortageOverviewView.as_view(), name="shortages"),
    path("subrentals", projects.SubrentalOverviewView.as_view(), name="subrentals"),
    path("imports/<slug:kind>", core_imports.ImportView.as_view(), name="import"),
    # IMP-017: the list of an import as CSV in the import's format.
    path("imports/<slug:kind>/export", core_imports.ImportExportView.as_view(), name="import-export"),
    # Stage 5, material. Before the router: "bulk-update" must not be taken for the ID of an item.
    path("material-items/bulk-update", material_items.BulkUpdateView.as_view(), name="material-item-bulk-update"),
    # MAT-082: the same inspection of many items at once.
    path(
        "material-items/inspections/batch",
        material_items.BatchInspectionView.as_view(),
        name="material-item-inspection-batch",
    ),
    path("material-items/<int:pk>/defects", material_items.ItemDefectsView.as_view(), name="material-item-defects"),
    path("material-items/<int:pk>/blocks", material_items.ItemBlocksView.as_view(), name="material-item-blocks"),
    path(
        "material-items/<int:pk>/blocks/<int:block_pk>",
        material_items.ItemBlockDetailView.as_view(),
        name="material-item-block-detail",
    ),
    path(
        "material-items/<int:pk>/inspections",
        material_items.ItemInspectionsView.as_view(),
        name="material-item-inspections",
    ),
    # MAT-078: the measured values of an electrical inspection against their limits; its printable protocol.
    path(
        "material-items/<int:pk>/inspections/check",
        material_items.ItemInspectionCheckView.as_view(),
        name="material-item-inspection-check",
    ),
    path("inspections/<int:pk>/report", material_items.InspectionReportView.as_view(), name="inspection-report"),
    path("material-items/<int:pk>/files", material_items.ItemFilesView.as_view(), name="material-item-files"),
    path("material-items/<int:pk>/take-out", material_items.ItemTakeOutView.as_view(), name="material-item-take-out"),
    path("material-items/<int:pk>/put-back", material_items.ItemPutBackView.as_view(), name="material-item-put-back"),
    path("material-items/<int:pk>/timeline", material_items.ItemTimelineView.as_view(), name="material-item-timeline"),
    # MAT-067, MAT-069: audits and to-dos of items, the open to-dos, the due audits, Einstellungen → Audits.
    path("material-items/<int:pk>/audits", material_audits.ItemAuditsView.as_view(), name="material-item-audits"),
    path("material-items/<int:pk>/todos", material_audits.ItemTodosView.as_view(), name="material-item-todos"),
    path(
        "material-items/<int:pk>/todos/<int:todo_pk>/done",
        material_audits.ItemTodoDoneView.as_view(),
        name="material-item-todo-done",
    ),
    path("material-todos", material_audits.TodoListView.as_view(), name="material-todos"),
    # MAT-070, API-002: several to-dos done at once, as on the page "Material mit To-Do".
    path("material-todos/done", material_audits.TodosDoneView.as_view(), name="material-todos-done"),
    path("material-audits/due", material_audits.DueAuditsView.as_view(), name="material-audits-due"),
    path("audit-settings", material_audits.AuditSettingsView.as_view(), name="audit-settings"),
    path("material-models/<int:pk>/files", material_items.ModelFilesView.as_view(), name="material-model-files"),
    path(
        "material-models/<int:pk>/timeline", material_items.ModelTimelineView.as_view(), name="material-model-timeline"
    ),
    # VFG-040: the secret iCalendar address of a product, model or item – read, create/renew, deactivate.
    path(
        "products/<int:pk>/calendar-link",
        calendar_links.ProductCalendarLinkView.as_view(),
        name="product-calendar-link",
    ),
    path(
        "material-models/<int:pk>/calendar-link",
        calendar_links.ModelCalendarLinkView.as_view(),
        name="material-model-calendar-link",
    ),
    path(
        "material-items/<int:pk>/calendar-link",
        calendar_links.ItemCalendarLinkView.as_view(),
        name="material-item-calendar-link",
    ),
    path("material-files/<int:pk>", material_items.MaterialFileDetailView.as_view(), name="material-file-detail"),
    path(
        "material-files/<int:pk>/content",
        material_items.MaterialFileContentView.as_view(),
        name="material-file-content",
    ),
    path(
        "material-files/<int:pk>/thumbnail",
        material_items.MaterialFileThumbnailView.as_view(),
        name="material-file-thumbnail",
    ),
    path("inspections/due", material_items.DueInspectionsView.as_view(), name="inspections-due"),
    path("labels", material_items.LabelsView.as_view(), name="labels"),
    path("label-settings", material_labels.LabelSettingsView.as_view(), name="label-settings"),  # MAT-056
    # MAT-027, UIX-006 (scanning): what a scanned code stands for.
    path("scan/resolve", scan_api.ScanResolveView.as_view(), name="scan-resolve"),
    # MAT-040 (built-in quantity material): bulk material built into a case, rack or vehicle.
    path(
        "material-items/<int:pk>/built-in", material_installed.ItemBuiltInView.as_view(), name="material-item-built-in"
    ),
    path(
        "material-items/<int:pk>/built-in/<int:material_pk>/remove",
        material_installed.ItemBuiltInRemoveView.as_view(),
        name="material-item-built-in-remove",
    ),
    # Depreciation, used sale from stock; "Mit Restbuchwert": book values, the Anlagenspiegel, sales out of the stock.
    path("material-items/<int:pk>/asset", material_assets.ItemAssetView.as_view(), name="material-item-asset"),
    path(
        "material-items/<int:pk>/sale-preview",
        material_assets.ItemSalePreviewView.as_view(),
        name="material-item-sale-preview",
    ),
    path("material-items/<int:pk>/sell", material_assets.ItemSellView.as_view(), name="material-item-sell"),
    path("asset-register", material_assets.AssetRegisterView.as_view(), name="asset-register"),
    path("asset-register/totals", material_assets.AssetRegisterTotalsView.as_view(), name="asset-register-totals"),
    path("asset-register/csv", material_assets.AssetRegisterCsvView.as_view(), name="asset-register-csv"),
    path("stock-sales", material_assets.StockSalesView.as_view(), name="stock-sales"),
    path("stock-sales/summary", material_assets.StockSalesSummaryView.as_view(), name="stock-sales-summary"),
    path("stock-sales/csv", material_assets.StockSalesCsvView.as_view(), name="stock-sales-csv"),
    path("stock-sales/<int:pk>", material_assets.StockSaleView.as_view(), name="stock-sale"),
    path("stock-sales/<int:pk>/cancel", material_assets.StockSaleCancelView.as_view(), name="stock-sale-cancel"),
    path("stock-sales/<int:pk>/invoice", material_assets.StockSaleInvoiceView.as_view(), name="stock-sale-invoice"),
    # MAT-061, MAT-062: a purchase with many items of several models; an invoice kept and read for it.
    # Incoming invoices: the register of Buchhaltung -> Eingangsrechnungen, as the pages do it.
    path("incoming-invoices", incoming.InvoiceListView.as_view(), name="incoming-invoices"),
    path("incoming-invoices/totals", incoming.InvoiceTotalsView.as_view(), name="incoming-invoices-totals"),
    path("incoming-invoices/<int:pk>", incoming.InvoiceView.as_view(), name="incoming-invoice"),
    path("incoming-invoices/<int:pk>/file", incoming.InvoiceFileView.as_view(), name="incoming-invoice-file"),
    path("incoming-invoices/<int:pk>/xml", incoming.InvoiceXmlView.as_view(), name="incoming-invoice-xml"),
    path("incoming-invoices/<int:pk>/read", incoming.InvoiceReadView.as_view(), name="incoming-invoice-read"),
    path(
        "incoming-invoices/<int:pk>/supplier", incoming.InvoiceSupplierView.as_view(), name="incoming-invoice-supplier"
    ),
    path("incoming-invoices/<int:pk>/costing", incoming.CostingView.as_view(), name="incoming-invoice-costing"),
    path("incoming-invoices/<int:pk>/book", incoming.BookView.as_view(), name="incoming-invoice-book"),
    path(
        "incoming-invoices/<int:pk>/positions", incoming.PositionListView.as_view(), name="incoming-invoice-positions"
    ),
    path(
        "incoming-invoices/<int:pk>/positions/<int:position_pk>",
        incoming.PositionView.as_view(),
        name="incoming-invoice-position",
    ),
    path("incoming-settings", incoming.SettingsView.as_view(), name="incoming-settings"),
    path("purchases", material_purchases.PurchaseView.as_view(), name="purchases"),
    path("purchases/invoices", material_purchases.PurchaseInvoiceView.as_view(), name="purchase-invoices"),
    # Legacy import: old projects from the PDF invoices of the old system, step by step as the pages do it.
    path("legacy-imports", legacy_api.BatchListView.as_view(), name="legacy-imports"),
    path("legacy-imports/<int:pk>", legacy_api.BatchView.as_view(), name="legacy-import"),
    path("legacy-imports/<int:pk>/items/<int:item_pk>", legacy_api.ItemView.as_view(), name="legacy-import-item"),
    path(
        "legacy-imports/<int:pk>/items/<int:item_pk>/skip",
        legacy_api.ItemSkipView.as_view(),
        name="legacy-import-item-skip",
    ),
    path("legacy-imports/<int:pk>/read", legacy_api.ReadView.as_view(), name="legacy-import-read"),
    path("legacy-imports/<int:pk>/preview", legacy_api.PreviewView.as_view(), name="legacy-import-preview"),
    path("legacy-imports/<int:pk>/confirm", legacy_api.ConfirmView.as_view(), name="legacy-import-confirm"),
    path("legacy-imports/<int:pk>/undo", legacy_api.UndoView.as_view(), name="legacy-import-undo"),
    # PRJ-115, MAT-053: profitability of projects and material; what an item earned.
    path("reports/profitability", reports.ProfitabilityReportView.as_view(), name="report-profitability"),
    path("reports/material", reports.MaterialReportView.as_view(), name="report-material"),
    path("material-items/<int:pk>/revenue", reports.ItemRevenueView.as_view(), name="material-item-revenue"),
    # MAT-058: the same for a model, over all its items.
    path("material-models/<int:pk>/revenue", reports.ModelRevenueView.as_view(), name="material-model-revenue"),
    # LOG-015, LOG-016: the fleet – vehicles and trailers, their data and availability; a model into the fleet.
    path("vehicles", material_vehicles.VehicleListView.as_view(), name="vehicle-list"),
    path("vehicles/<int:pk>", material_vehicles.VehicleDetailView.as_view(), name="vehicle-detail"),
    path(
        "vehicles/<int:pk>/availability",
        material_vehicles.VehicleAvailabilityView.as_view(),
        name="vehicle-availability",
    ),
    path(
        "material-models/<int:pk>/to-fleet",
        material_vehicles.ModelToFleetView.as_view(),
        name="material-model-to-fleet",
    ),
    path("jobs/<int:pk>", core.JobView.as_view(), name="job-detail"),
    path("exports/full", core.FullExportView.as_view(), name="full-export"),
    path("jobs/<int:pk>/result", core.JobResultView.as_view(), name="job-result"),
    path("backups", core.BackupView.as_view(), name="backups"),  # ADM-010
    # Before the router: "availability" must not be taken for the ID of a person.
    path("people/availability", personnel.PeopleAvailabilityView.as_view(), name="people-availability"),
    # API-015: the own personnel data, absences and deployments, without a right on a module. Before the
    # router: "me" must not be taken for the ID of a person ("people/me/absences" is not "people/{id}/absences").
    path("people/me/profile", personnel_own.OwnProfileView.as_view(), name="own-profile"),
    path("people/me/absences", personnel_own.OwnAbsencesView.as_view(), name="own-absence-list"),
    path(
        "people/me/absences/<int:absence_pk>",
        personnel_own.OwnAbsenceDetailView.as_view(),
        name="own-absence-detail",
    ),
    path("people/me/deployments", personnel_own.OwnDeploymentsView.as_view(), name="own-deployments"),
    path("people/me/offers", personnel_offers.OwnOffersView.as_view(), name="own-offers"),  # PER-038
    path("people/<int:pk>/timeline", personnel.PersonTimelineView.as_view(), name="person-timeline"),
    path("people/<int:pk>/qualifications", personnel.PersonQualificationsView.as_view(), name="person-qualifications"),
    path(
        "people/<int:pk>/qualifications/<int:qualification_pk>",
        personnel.PersonQualificationDetailView.as_view(),
        name="person-qualification-detail",
    ),
    path(
        "people/<int:pk>/qualifications/<int:qualification_pk>/certificate",
        personnel.PersonQualificationCertificateView.as_view(),
        name="person-qualification-certificate",
    ),
    path("open-items", course.OpenItemOverviewView.as_view(), name="open-item-overview"),
    path("calendar", schedule.CalendarView.as_view(), name="calendar"),
    path("utilization", schedule.UtilizationView.as_view(), name="utilization"),
    path("personnel-plan", schedule.PersonnelPlanView.as_view(), name="personnel-plan"),
    path("mail/unknown", mail.UnknownTagListView.as_view(), name="mail-unknown-list"),
    # EML-053: one entry; an inquiry noted by hand is changed and deleted here.
    path("mail/unknown/<int:pk>", mail.UnknownTagDetailView.as_view(), name="mail-unknown-detail"),
    path("mail/unknown/<int:pk>/assign", mail.UnknownTagAssignView.as_view(), name="mail-unknown-assign"),
    path("mail/unknown/<int:pk>/dismiss", mail.UnknownTagDismissView.as_view(), name="mail-unknown-dismiss"),
    path("mail/unknown/dismiss", mail.UnknownTagDismissManyView.as_view(), name="mail-unknown-dismiss-many"),  # PRJ-107
    path("mail/fetch", mail.FetchNowView.as_view(), name="mail-fetch"),
    path("mail/settings", mail.MailSettingsView.as_view(), name="mail-settings"),
    # Signature, address suggestions, mail log (EML-034, EML-037, EML-039).
    path("mail/signature", mail.MailSignatureView.as_view(), name="mail-signature"),
    path("mail/address-suggestions", mail.AddressSuggestionsView.as_view(), name="mail-address-suggestions"),
    path("mail/log", mail.MailLogView.as_view(), name="mail-log"),
    path("notifications", notifications.NotificationListView.as_view(), name="notification-list"),
    path("notifications/read", notifications.NotificationReadView.as_view(), name="notification-read"),
    path(
        "notifications/preferences",
        notifications.NotificationPreferencesView.as_view(),
        name="notification-preferences",
    ),
    # VFG-036: when, how often and how far ahead shortages are reported (Einstellungen → Benachrichtigungen).
    path("settings/notifications", notifications.NotificationSettingsView.as_view(), name="settings-notifications"),
    path("me/sessions", accounts.SessionListView.as_view(), name="session-list"),
    path("me/sessions/<int:pk>", accounts.SessionDetailView.as_view(), name="session-detail"),
    path("security-log", accounts.SecurityLogView.as_view(), name="security-log"),
    path("self-check", core.SelfCheckView.as_view(), name="self-check"),
    # Who read what (AUT-028), what is encrypted (ADM-009).
    path("access-log", core.AccessLogView.as_view(), name="access-log"),
    path("encryption", core.EncryptionView.as_view(), name="encryption"),
    path("reports/hours", timetracking.HoursReportView.as_view(), name="report-hours"),
    path("reports/hours/csv", timetracking.HoursReportCsvView.as_view(), name="report-hours-csv"),
    path("reports/hours/pdf", timetracking.HoursReportPdfView.as_view(), name="report-hours-pdf"),
    # ZEI-019: expenses per month and person.
    path("reports/expenses", timetracking_expenses.ExpenseReportView.as_view(), name="report-expenses"),
    path("reports/expenses/csv", timetracking_expenses.ExpenseReportCsvView.as_view(), name="report-expenses-csv"),
    # The chat of a project (UIX-010), automations with triggers (ADM-013).
    *chat.urlpatterns,
    *automations.urlpatterns,
    *core_address.urlpatterns,  # ADM-016: server address and certificate
    *nested,
    path("", include(router.urls)),
    # The machine-readable description (OpenAPI 3) and two ways to browse it (API-004).
    path("schema", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api:schema"), name="docs"),
    # Requirement of the mobile app: no redirects under /api/v1 – also not the one from "docs" to "docs/".
    path("docs", SpectacularSwaggerView.as_view(url_name="api:schema")),
]
