{
    "name": "Zyra Garment — Materials",
    "version": "18.0.1.0.0",
    "summary": "Fabric and trim bookings per production order, fabric rolls as stock lots, "
               "4-point fabric inspection with a tablet screen",
    "description": "Materials for the Zyra garment ERP: fabric bookings, roll board, 4-point inspection. "
                   "See README.md for models and what other modules can rely on.",
    "author": "Pearlsoft Technologies",
    "category": "Manufacturing/Garment",
    "license": "OPL-1",
    "depends": [
        "zyra_garment_merch",
        "zyra_garment_theme",
        "purchase_stock",
    ],
    "data": [
        "security/zyra_garment_materials_security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "report/materials_reports.xml",
        "views/garment_fabric_booking_views.xml",
        "views/stock_lot_views.xml",
        "views/garment_fabric_inspection_views.xml",
        "views/garment_order_views.xml",
        "views/menus.xml",
    ],
    "demo": [
        "demo/materials_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "zyra_garment_materials/static/src/inspection_tablet/**/*",
        ],
        "web.assets_tests": [
            "zyra_garment_materials/static/src/tests/**/*",
        ],
    },
    "installable": True,
}
