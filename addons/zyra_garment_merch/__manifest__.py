{
    "name": "Zyra Garment — Merchandising",
    "version": "18.0.1.0.0",
    "summary": "Production orders with the size and colour grid, samples and fit measurements, "
               "buyer approval cards and the time and action plan",
    "description": "Merchandising for the Zyra garment ERP. See README.md for the contract "
                   "(production order progress API) other modules rely on.",
    "author": "Pearlsoft Technologies",
    "category": "Manufacturing/Garment",
    "license": "OPL-1",
    "depends": [
        "zyra_garment_base",
        "zyra_garment_theme",
        "zyra_techpack",
        "sale_management",
        "sale_mrp",
    ],
    "data": [
        "security/zyra_garment_merch_security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "data/garment_tna_template_data.xml",
        "report/merch_reports.xml",
        "report/garment_order_breakdown_report.xml",
        "report/garment_sample_reports.xml",
        "report/garment_approval_report.xml",
        "views/garment_order_views.xml",
        "views/garment_sample_views.xml",
        "views/garment_approval_views.xml",
        "views/garment_tna_views.xml",
        "views/garment_style_views.xml",
        "views/sale_order_views.xml",
        "views/menus.xml",
    ],
    "demo": [
        "demo/merch_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "zyra_garment_merch/static/src/**/*",
        ],
    },
    "installable": True,
}
