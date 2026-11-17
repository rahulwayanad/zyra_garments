{
    "name": "Zyra Garment — Cutting",
    "version": "18.0.1.0.0",
    "summary": "Markers, cut plans with a lay builder, lays on approved rolls, bundles and bundle tickets "
               "with one QR coupon per sewing operation",
    "description": "Cutting room for the Zyra garment ERP. See README.md for the bundle coupon payload "
                   "contract the sewing floor scans.",
    "author": "Pearlsoft Technologies",
    "category": "Manufacturing/Garment",
    "license": "OPL-1",
    "depends": [
        "zyra_garment_base",
        "zyra_garment_theme",
        "zyra_garment_merch",
        "stock",
    ],
    "data": [
        "security/zyra_garment_cutting_security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "report/bundle_ticket_report.xml",
        "views/garment_marker_views.xml",
        "views/garment_cut_plan_views.xml",
        "views/garment_lay_views.xml",
        "views/garment_bundle_views.xml",
        "views/garment_order_views.xml",
        "wizard/cut_plan_builder_views.xml",
        "wizard/marker_import_views.xml",
        "wizard/bundle_wizard_views.xml",
        "views/menus.xml",
    ],
    "demo": [
        "demo/cutting_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "zyra_garment_cutting/static/src/**/*",
        ],
    },
    "installable": True,
}
