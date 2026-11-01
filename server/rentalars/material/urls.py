# SPDX-License-Identifier: GPL-3.0-or-later
"""Addresses of the material module."""

from django.urls import path

from rentalars.material import (
    asset_views,  # depreciation, used sale from stock
    audit_views,
    fleet_views,
    installed_views,
    item_views,
    label_views,
    photo_views,  # photos of models and items
    purchase_views,
    scan_views,
    views,
)

app_name = "material"

urlpatterns = [
    path("material/", views.item_list, name="item_list"),
    path("material/items/suggest/", views.item_suggest, name="item_suggest"),
    path("material/items/jump/", views.item_jump, name="item_jump"),  # MAT-063: open an item by its ID
    path("material/items/<int:pk>/", views.item_detail, name="item_detail"),
    path("material/items/<int:pk>/edit/", views.item_edit, name="item_edit"),
    path("material/items/<int:pk>/status/", views.item_set_status, name="item_set_status"),
    path("material/items/<int:pk>/delete/", views.item_delete, name="item_delete"),
    path("material/items/<int:pk>/contents/add/", views.item_content_add, name="item_content_add"),
    path("material/items/<int:pk>/install/", views.item_install, name="item_install"),  # MAT-047
    path(
        "material/items/<int:pk>/contents/<int:content_pk>/remove/",
        views.item_content_remove,
        name="item_content_remove",
    ),
    path("material/models/", views.model_list, name="model_list"),
    path("material/models/new/", views.model_edit, name="model_create"),
    path("material/models/<int:pk>/", views.model_detail, name="model_detail"),
    path("material/models/<int:pk>/edit/", views.model_edit, name="model_edit"),
    path("material/models/<int:pk>/delete/", views.model_delete, name="model_delete"),
    path("material/models/<int:model_pk>/items/new/", views.item_create, name="item_create"),
    path("material/import/", views.material_import, name="import"),
    # Stage 5: the tabs of an item (VFG-019, MAT-031, MAT-017, MAT-023, MAT-025)
    path("material/items/<int:pk>/timeline/", item_views.item_timeline, name="item_timeline"),
    path("material/items/<int:pk>/inspections/", item_views.item_inspections, name="item_inspections"),
    path("material/items/<int:pk>/files/", item_views.item_files, name="item_files"),
    path("material/items/<int:pk>/history/", item_views.item_history_page, name="item_history"),
    path("material/items/<int:pk>/defect/", item_views.item_defect, name="item_defect"),
    path("material/items/<int:pk>/blocks/", item_views.item_block_add, name="item_block_add"),
    path(
        "material/items/<int:pk>/blocks/<int:block_pk>/delete/", item_views.item_block_delete, name="item_block_delete"
    ),
    path("material/items/<int:pk>/take-out/", item_views.item_take_out, name="item_take_out"),
    path("material/items/<int:pk>/put-back/", item_views.item_put_back, name="item_put_back"),
    path("material/items/bulk/", views.item_bulk_update, name="item_bulk_update"),
    path("material/files/<int:pk>/", item_views.material_file, name="file"),
    path("material/items/<int:pk>/photos/", photo_views.item_photos, name="item_photos"),
    path("material/models/<int:pk>/photos/", photo_views.model_photos, name="model_photos"),
    path("material/files/<int:pk>/small/", item_views.material_file_small, name="file_small"),
    path("material/files/<int:pk>/delete/", item_views.material_file_delete, name="file_delete"),
    path("material/defects/<int:pk>/photo/", item_views.defect_photo, name="defect_photo"),
    path("material/inspection-records/<int:pk>/protocol/", item_views.inspection_protocol, name="inspection_protocol"),
    # MAT-078: the live check of an electrical inspection's values, and its printable protocol.
    path("material/items/<int:pk>/inspections/check/", item_views.inspection_check, name="inspection_check"),
    path("material/inspection-records/<int:pk>/report/", item_views.inspection_report, name="inspection_report"),
    path("material/inspections/", views.inspection_overview, name="inspections"),
    # MAT-082: one inspection for several items chosen in the overview.
    path("material/inspections/batch/", views.inspection_batch, name="inspection_batch"),
    path("material/labels/", label_views.labels_page, name="labels"),
    path("material/labels/print/", label_views.labels_print, name="labels_print"),  # MAT-056
    path("material/items/<int:pk>/labels/", label_views.item_labels, name="item_labels"),  # MAT-066
    path("administration/labels/", label_views.label_settings_page, name="label_settings"),  # MAT-056
    path("m/<str:code>", views.item_by_code, name="item_by_code"),
    path("material/scan/", scan_views.scan_resolve, name="scan_resolve"),  # MAT-027, UIX-006
    path("material/models/<int:pk>/timeline/", views.model_timeline, name="model_timeline"),
    path("material/models/<int:pk>/files/", views.model_files, name="model_files"),
    # Typed fields with suggestions (MAT-048, MAT-050, PRD-046), model → product (MAT-051, PRD-046)
    path("material/manufacturers/suggest/", views.manufacturer_suggest, name="manufacturer_suggest"),
    path("material/suppliers/suggest/", views.supplier_suggest, name="supplier_suggest"),
    path("material/suppliers/new/", views.supplier_create, name="supplier_create"),  # MAT-060: in a dialog
    path("material/products/suggest/", views.product_suggest, name="product_suggest"),
    path("material/models/suggest/", views.model_suggest, name="model_suggest"),
    path("material/models/<int:pk>/product/", views.model_create_product, name="model_create_product"),
    path("material/models/assign/", views.model_assign, name="model_assign"),
    # The fleet – list, utilization, vehicle data of an item, a model taken into the fleet (LOG-002 ff.)
    path("material/fleet/", fleet_views.fleet_list, name="fleet"),
    path("material/fleet/utilization/", fleet_views.fleet_utilization, name="fleet_utilization"),
    path("material/items/<int:pk>/vehicle/", fleet_views.vehicle_edit, name="vehicle_edit"),
    path("material/models/<int:pk>/to-fleet/", fleet_views.model_to_fleet, name="model_to_fleet"),
    # MAT-061, MAT-062: many items of several models from one invoice, filled from the invoice if wished
    path("material/purchase/", purchase_views.purchase_page, name="purchase"),
    path("material/purchase/reading/<int:job_pk>/", purchase_views.purchase_reading, name="purchase_reading"),
    path("material/purchase/done/", purchase_views.purchase_done, name="purchase_done"),
    path("material/purchase/models/suggest/", purchase_views.purchase_model_suggest, name="purchase_model_suggest"),
    # MAT-067, MAT-068, MAT-069, MAT-070: the audit mode, to-dos of an item, Offene Punkte, the settings.
    path("material/audit/", audit_views.audit_page, name="audit"),
    path("material/items/<int:pk>/todos/", audit_views.item_todo_add, name="item_todo_add"),
    path("material/todos/<int:pk>/done/", audit_views.todo_done, name="todo_done"),
    path("material/todos/done/", audit_views.todos_done, name="todos_done"),
    path("material/open-points/", audit_views.open_without_product, name="open_without_product"),
    path("material/open-points/to-dos/", audit_views.open_todos, name="open_todos"),
    path("material/open-points/audits/", audit_views.open_audits, name="open_audits"),
    path("administration/audits/", audit_views.audit_settings_page, name="audit_settings"),
    # Depreciation, used sale from stock; "Mit Restbuchwert": the card "Anlagevermögen", the Anlagenspiegel, the sales.
    path("material/items/<int:pk>/asset/", asset_views.item_asset_edit, name="item_asset"),
    path("material/items/<int:pk>/sell/", asset_views.item_sell, name="item_sell"),
    path("accounting/assets/", asset_views.asset_register, name="asset_register"),
    path("accounting/assets/sales/", asset_views.sales_list, name="sales"),
    path("accounting/assets/sales/<int:pk>/", asset_views.sale_detail, name="sale_detail"),
    path("accounting/assets/sales/<int:pk>/cancel/", asset_views.sale_cancel, name="sale_cancel"),
    path("accounting/assets/sales/<int:pk>/invoice/", asset_views.sale_invoice, name="sale_invoice"),
    # Built-in quantity material; MAT-040: bulk material built into a case, rack or vehicle.
    path("material/items/<int:pk>/built-in/", installed_views.built_in_add, name="built_in_add"),
    path(
        "material/items/<int:pk>/built-in/<int:material_pk>/remove/",
        installed_views.built_in_remove,
        name="built_in_remove",
    ),
]
