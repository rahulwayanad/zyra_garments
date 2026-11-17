{
    "name": "Zyra Garment — Sewing",
    "version": "18.0.1.0.0",
    "summary": "Sewing lines, operation bulletins, line balancing, coupon scans with operator earnings, "
               "offline-safe scan replay, hourly line board and daily line summary",
    "description": "Sewing floor for the Zyra garment ERP. See README.md.",
    "author": "Pearlsoft Technologies",
    "category": "Manufacturing/Garment",
    "license": "OPL-1",
    "depends": [
        "zyra_garment_base",
        "zyra_garment_theme",
        "zyra_garment_merch",
        "zyra_garment_cutting",
        "hr",
        "mrp",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/zyra_garment_sewing_security.xml",
        "views/garment_line_views.xml",
        "views/garment_bulletin_views.xml",
        "data/sewing_data.xml",
        "views/garment_scan_views.xml",
        "views/garment_line_day_views.xml",
        "views/sewing_client_actions.xml",
        "wizard/line_balancing_views.xml",
        "views/menus.xml",
    ],
    "demo": [
        "demo/sewing_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "zyra_garment_sewing/static/src/**/*",
        ],
    },
    "installable": True,
}
