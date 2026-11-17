{
    "name": "Zyra Garment — Quality",
    "version": "18.0.1.0.0",
    "summary": "Inline, end-line and final AQL inspections, DHU, tablet end-line check, CAPA and the "
               "final inspection report; a failed final blocks the shipment",
    "description": "Quality for the Zyra garment ERP. See README.md for the contract "
                   "(garment.order.final_passed / final_inspection_state) other modules rely on.",
    "author": "Pearlsoft Technologies",
    "category": "Manufacturing/Garment",
    "license": "OPL-1",
    "depends": [
        "zyra_garment_base",
        "zyra_garment_theme",
        "zyra_garment_merch",
    ],
    "data": [
        "security/zyra_garment_quality_security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "data/garment_aql_data.xml",
        "report/quality_reports.xml",
        "report/garment_inspection_report.xml",
        "report/garment_capa_report.xml",
        "wizard/garment_inspection_concession_views.xml",
        "views/garment_inspection_views.xml",
        "views/garment_capa_views.xml",
        "views/garment_aql_views.xml",
        "views/garment_order_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
    ],
    "demo": [
        "demo/quality_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "zyra_garment_quality/static/src/**/*",
        ],
        "web.assets_tests": [
            "zyra_garment_quality/static/tests/**/*",
        ],
    },
    "installable": True,
}
